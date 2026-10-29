#!/usr/bin/env bash
# safe-bash-t-y.test.sh — DEUXIÈME des quatre morceaux de la suite
# de .claude/hooks/safe-bash.sh (scission T-01M4WTYT8M),
# coupe à la bannière « (t) T-00000244 — GARDE 4 ».
# Sections : (t) garde 4 écriture par redirection, (h2bis)(h2ter),
#   (l23)-(l55) T-00000762, (w)(x)(y).
# Les arms sont ceux d'origine, dans l'ordre d'origine : aucun retiré, aucun
# affaibli. La carte des mutants (quel mutant tue quel arm), le mode d'emploi de
# SAFE_BASH_HOOK et la liste des quatre morceaux vivent UNE fois, en tête de
# safe-bash.test.sh. Le prologue ci-dessous est recopié octet pour octet dans les
# quatre morceaux ; (split0) de safe-bash.test.sh compare les copies.
# >>> safe-bash-prologue
# PROLOGUE COMMUN des quatre suites .claude/hooks/safe-bash*.test.sh
# (T-01M4WTYT8M) : le MÊME, octet pour octet, dans chacune ; (split0) de
# safe-bash.test.sh compare les quatre copies. Le modifier ici, c'est le
# modifier dans les QUATRE fichiers.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${SAFE_BASH_HOOK:-$HERE/safe-bash.sh}"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "SKIP: ${0##*/} needs python to build the payloads"; exit 0; fi
# REAL_PY : l'interpréteur RÉSOLU, que les cales des sections (n)(s)(x)(z)
# exécutent derrière leur filtre. Au prologue (T-01M4WTYT8M) : trois des quatre
# morceaux l'emploient, et aucun ne lit l'état qu'un autre a construit.
REAL_PY="$(command -v "$PY")"
# Events from the guard's own emit calls must never land in the real store.
EVTMP="$(mktemp -d)"
export AGENTS_EVENTS_DIR="$EVTMP"
OUTF="$EVTMP/stdout"; ERRF="$EVTMP/stderr"

PASS=0; FAIL=0

# json_payload <command> — la forme PreToolUse réelle.
# WINDOWS (fait mesuré, et la raison pour laquelle ces deux variables sont là) :
# sous Git Bash / MSYS, argv passé à un binaire natif (python.exe) subit une
# TRADUCTION DE CHEMIN — `/bin/rm secrets.txt` arrivait à python comme
# `C:/Program Files/Git/usr/bin/rm secrets.txt`. La suite mesurait alors une
# charge utile réécrite par le shell, pas celle qu'elle décrit : l'arm (h9)
# passait en vert sans que le garde ait jamais vu un `/bin/rm`. Les deux
# variables neutralisent la conversion ; sur Linux (CI) elles sont inertes.
json_payload() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    "$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$1"
}

check() { # check <expected_exit> <label> <command-string>
  expected="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_deny_msg() { # check_deny_msg <motif> <label> <command-string>
  # REFUSÉ, ET POUR LA BONNE RAISON. Le code de sortie seul ne suffit pas
  # (L-00000161) : ce garde porte PLUSIEURS motifs distincts — rm-rf-root,
  # git-wipe-unscoped, git-output-write, git-grep-pager-exec,
  # git-subcommand-hidden, rg-absent-silent-failure, redirect-write-guarded,
  # rm-mv-bypass-checkpoint, depuis T-00000784 redirect-stage-broken et, depuis
  # T-00001090, git-branch-force-delete — donc
  # un arm satisfait par le mauvais d'entre eux serait un faux vert ; c'est
  # exactement ce que la matrice de parité assert de son côté avec ses `motive`.
  # Le compte a été porté de TROIS à CINQ (T-00000227), puis le CHIFFRE a été
  # RETIRÉ (T-00000784, L-00000187) : il était de nouveau périmé — huit règles
  # `deny` quand il en disait cinq — DANS le helper même dont la thèse est « un
  # code de sortie n'est pas un motif ». La liste se relève par grep des
  # `deny <règle>` et du `rule=` de l'étage redirection de safe-bash.sh ; elle
  # n'est close par aucun chiffre.
  motive="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  msg="$(cat "$ERRF")"
  case "$msg" in
    *"$motive"*) if [ "$got" -eq 2 ]; then PASS=$((PASS+1)); echo "PASS: $label"; return; fi;;
  esac
  FAIL=$((FAIL+1))
  echo "FAIL: $label (expected exit 2 carrying <$motive>, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
}

check_silent() { # check_silent <label> <command-string> — laissé passer ET sans
  # un mot sur aucune des deux sorties. C'est l'assertion qui attrape le défaut
  # de T-00000146 : le garde ne doit pas seulement laisser passer une commande
  # qui MENTIONNE une suppression, il ne doit pas non plus la commenter.
  label="$1"; cmd="$2"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

# check_path <PATH> <expected_exit> <label> <command-string>
# Même contrat que `check`, mais joue le hook sous un PATH imposé — la garde
# `rg` se comporte différemment selon que l'outil résout ou non, et un test qui
# hériterait du PATH du poste basculerait de vert à rouge le jour d'une
# installation de ripgrep. Les deux branches sont donc FORCÉES, pas observées.
# La charge utile est sérialisée AVANT la substitution de PATH : c'est le garde
# qu'on déplace, pas le harnais.
check_path() {
  forced_path="$1"; expected="$2"; label="$3"; cmd="$4"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_silent_path() { # check_silent_path <PATH> <label> <command-string>
  forced_path="$1"; label="$2"; cmd="$3"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

assert() { # assert <rc 0=ok> <label>
  if [ "$1" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $2"; else FAIL=$((FAIL+1)); echo "FAIL: $2"; fi
}
# <<< safe-bash-prologue

# =============================================================================
# (t) T-00000244 — GARDE 4 : ÉCRITURE SHELL PAR REDIRECTION. Une écriture `>`,
#   `>>`, `&>`, `N>fichier` vers un fichier SUIVI *OU* PROTÉGÉ contourne le
#   chemin Edit/Write et ses gardes de checkpoint et de mandat. Prédicat MESURÉ
#   dans core-scripts/measure_shell_write_fp.py (FP 0,033 % des exécutés, zéro rouge
#   sur les formes closes). Motif propre : `redirect-write-guarded`, distinct des
#   trois autres — check_deny_msg le vérifie, un arm satisfait par la garde rm/mv
#   serait un faux vert.
#   La clause protégée est LUE du sibling protect-paths.sh par EXTRACTION
#   TEXTUELLE (t3)(t4)(t5) ; la clause git-suivie (t1)(t2)(t9) est indépendante.
#   La branche STRICTE (t13)-(t15) rejoue une COPIE du hook SANS le sibling.
# =============================================================================
# --- clause git-suivie : AGENTS.md est un fichier suivi de CE dépôt ----------
check_deny_msg "redirects a write" "(t1) append to a tracked file"        'echo x >> AGENTS.md'
check_deny_msg "redirects a write" "(t2) truncate a tracked file"         'echo x > AGENTS.md'
# --- clause protégée : les DEUX surfaces de refus du canon (BLOCKED + case) ---
check_deny_msg "redirects a write" "(t3) KICKOFF_REQUIRED (case-folded block)" \
  'printf y > .agents/state/gates/KICKOFF_REQUIRED'
check_deny_msg "redirects a write" "(t4) .mcp.json (MCP case block)"      'echo x > .mcp.json'
check_deny_msg "redirects a write" "(t5) a BLOCKED_PATTERNS prefix"       'echo x > src/legacy/note.md'
# --- formes de PASSE de la table de polarité ---------------------------------
check 0 "(t6) cible absolue hors dépôt PASSE"        'echo x > /tmp/scratch-t244'
check 0 "(t7) DOCTRINE IDIOM: cmd > out 2>&1 PASSE"  'make check > build-t244.out 2>&1'
check 0 "(t8) duplication de descripteur >&2 PASSE"  'echo err >&2'
check 0 "(t8b) N>&M duplication PASSE"                'run 2>&1 | cat'
check_deny_msg "redirects a write" "(t9) 2>fichier suivi est JUGÉ"        'run 2> AGENTS.md'
check 0 "(t10) cible CITÉE invisible PASSE"          'printf y > "spaced t244.txt"'
check 0 "(t11) cible à EXPANSION invisible PASSE"    'cat f > $DEST'
check 0 "(t12) un > DANS une chaîne n est pas une redirection" 'echo "a > b is data"'
# (t9c) LE JUMEAU : le même corps de heredoc à délimiteur CITÉ dont une ligne
# porte `> AGENTS.md` reste DONNÉE (l'étage 0.5 le blanchit avant la garde 4).
check 0 "(t9c) redirection dans un corps de heredoc cité reste DONNÉE" \
  "$(printf 'git commit -F - <<%sMSG%s\necho x > AGENTS.md\nMSG' "'" "'")"
# --- (t13)-(t15) BRANCHE STRICTE : sibling protect-paths.sh ILLISIBLE. Rejeu
#   d'une COPIE du hook dans un dossier SANS le sibling. La clause protégée est
#   ANNONCÉE-ÉTEINTE (COVERAGE DEGRADED sur stderr), MAIS la clause git-suivie
#   survit — jamais une exemption vide. Le hook lit son propre sibling, donc
#   c'est bien l'ABSENCE du garde canonique qui est mesurée.
STRICTD="$EVTMP/redir-strict"; mkdir -p "$STRICTD"
cp "$HERE/safe-bash.sh" "$STRICTD/safe-bash.sh"
cp "$HERE/emit-event.sh" "$STRICTD/emit-event.sh" 2>/dev/null || true
printf '%s' "$(json_payload 'echo x > .mcp.json')" | bash "$STRICTD/safe-bash.sh" >"$OUTF" 2>"$ERRF"
ST_MCP_RC=$?; ST_MCP_ERR="$(cat "$ERRF")"
assert "$([ "$ST_MCP_RC" -eq 0 ] && echo 0 || echo 1)" \
  "(t13) strict: protected-only target ALLOWED when the sibling is unreadable (got $ST_MCP_RC)"
case "$ST_MCP_ERR" in
  *"COVERAGE DEGRADED"*"protected-path clause is OFF"*)
  assert 0 "(t14) strict: the lost protected clause is ANNOUNCED on stderr";;
  *) assert 1 "(t14) strict: COVERAGE DEGRADED naming the protected clause (got: $ST_MCP_ERR)";; esac
printf '%s' "$(json_payload 'echo x >> AGENTS.md')" | bash "$STRICTD/safe-bash.sh" >"$OUTF" 2>"$ERRF"
assert "$([ $? -eq 2 ] && echo 0 || echo 1)" \
  "(t15) strict: the git-tracked clause SURVIVES (append to a tracked file still blocked)"
# (t16)-(t17) LE CANARI DOIT DÉTECTER L'EXTRACTION INCOMPLÈTE, PAS SEULEMENT
#   L'ABSENTE (revue de sécurité, HIGH classe 1). Le sibling est PRÉSENT et
#   LISIBLE mais REFORMATÉ cosmétiquement — `BLOCKED_PATTERNS="…"` requoté en
#   simples — ce qui suffisait à faire retomber la regex sur la ligne du loop et
#   à produire des DÉCHETS comme prefixes pendant que le canari restait vert :
#   `> src/legacy/nouveau` (NON suivi) passait alors SANS refus ET SANS
#   annonce. Ici la même reformulation doit désormais déclencher la branche
#   STRICTE. NON-VACUITÉ : avec le sibling NORMAL, .mcp.json est REFUSÉ (t4), donc
#   son basculement vers ALLOW-annoncé mesure bien le canari et non l'inverse.
STRICT2D="$EVTMP/redir-strict-reformat"; mkdir -p "$STRICT2D"
cp "$HERE/safe-bash.sh" "$STRICT2D/safe-bash.sh"
cp "$HERE/emit-event.sh" "$STRICT2D/emit-event.sh" 2>/dev/null || true
sed "s/^BLOCKED_PATTERNS=\"\(.*\)\"/BLOCKED_PATTERNS='\1'/" "$HERE/protect-paths.sh" > "$STRICT2D/protect-paths.sh"
printf '%s' "$(json_payload 'echo x > .mcp.json')" | bash "$STRICT2D/safe-bash.sh" >"$OUTF" 2>"$ERRF"
RF_RC=$?; RF_ERR="$(cat "$ERRF")"
assert "$([ "$RF_RC" -eq 0 ] && echo 0 || echo 1)" \
  "(t16) reformatted sibling: protected clause OFF, .mcp.json now ALLOWED (got $RF_RC — DENY here would be the fail-open masked)"
case "$RF_ERR" in
  *"COVERAGE DEGRADED"*"protected-path clause is OFF"*)
  assert 0 "(t17) reformatted sibling: the INCOMPLETE extraction is ANNOUNCED (canary fires on garbage prefixes, not only on an absent file)";;
  *) assert 1 "(t17) reformatted sibling: COVERAGE DEGRADED expected (got: $RF_ERR)";; esac
# (t18)-(t19) LA CIBLE DU PoC, DIRECTEMENT (T-00000289). (t16)/(t17) prouvent le
#   canari par un témoin INDIRECT : `.mcp.json` est refusé via le bloc `case` des
#   globs sensibles, dont la regex d'extraction (safe-bash.sh:725) est
#   INDÉPENDANTE de celle de BLOCKED_PATTERNS (:709) — or c'est cette dernière
#   que le reformatage casse. La cible réellement exploitée par le PoC est
#   `src/legacy/`, SOURCÉE de BLOCKED_PATTERNS (protect-paths.sh:19) et NON
#   git-suivie (`git ls-files 'src/*'` = 0, mesuré) : seule la clause protégée
#   peut la refuser, donc l'arm mesure bien CELLE-LÀ et non la clause git-suivie
#   qui, elle, survit — c'est (t15). NON-VACUITÉ croisée, déjà présente : avec le
#   sibling NORMAL, (t5) refuse cette même famille de cible.
printf '%s' "$(json_payload 'echo x > src/legacy/nouveau')" | bash "$STRICT2D/safe-bash.sh" >"$OUTF" 2>"$ERRF"
RF2_RC=$?; RF2_ERR="$(cat "$ERRF")"
assert "$([ "$RF2_RC" -eq 0 ] && echo 0 || echo 1)" \
  "(t18) reformatted sibling: the PoC's OWN target src/legacy/ (NOT git-tracked) is ALLOWED — the protected clause really is OFF (got $RF2_RC)"
case "$RF2_ERR" in
  *"COVERAGE DEGRADED"*"protected-path clause is OFF"*)
  assert 0 "(t19) reformatted sibling: the loss is ANNOUNCED on the PoC's own target too, not only on the MCP witness";;
  *) assert 1 "(t19) reformatted sibling: COVERAGE DEGRADED expected on src/legacy/ (got: $RF2_ERR)";; esac
# (t20)-(t26) LE REFUS DIT COMMENT CHAQUE CIBLE A ÉTÉ JUGÉE (T-00000698). Le
#   verdict de la garde 4 ne bouge pas ; chaque chemin refusé porte désormais
#   `(règle, mode)` avec mode = relative / inside / outside, et une clause
#   anglaise dit la résolution contre la RACINE (jamais un `cd` interne) et le
#   refus d'un nom protégé où qu'il vive, hors dépôt compris — un jeton de
#   credential étant jugé contre la liste de CET hôte. Les listes ont DIFFÉRÉ
#   (`id_rsa` refusé côté Claude seul, `server.key` côté Python seul ; mesuré
#   par l'exec-critic sur b7055f0, puis aligné par le lot T-00000721) ; elles
#   sont ALIGNÉES jeton pour jeton, et la clause le dit. Aucun motif
#   n'épingle un préfixe de chemin (macOS rend `/private/tmp`) ; les cibles hors
#   dépôt vivent sous $EVTMP (mktemp -d, jamais créées : normalize() résout en
#   non-strict), donc aucun résidu partagé entre deux bancs. BORNE dite : un
#   chemin temporaire qui porterait par hasard un jeton de credential (`secret`,
#   `id_rsa`, `.pem`) ferait gagner CE glob-là — le nom du dossier est lu.
#   Côté sh, (t25)/(t26) sont verts AVANT T-00000698 (les globs push_defaut_*
#   sont dans protect-paths.sh depuis T-00000595) : ils épinglent la colonne
#   `mode`, pas la brèche — celle-là est prouvée côté Python (bancs hôte).
#   Ce que (t20b)/(t22b)/(t24b) discriminent, chacun UNE mutation : la clause
#   retirée de l'echo de la garde 4 → (t20b) ROUGE, nulle part ailleurs côté
#   bash ; l'ordre du mode inversé (relative testé avant outside) → (t24) et
#   (t24b) ROUGES.
check_deny_msg "AGENTS.md (git-tracked, relative)" \
  "(t20) a relative target after an internal cd is resolved against the PROJECT ROOT, never the cd — AGENTS.md is tracked THERE" \
  "cd $EVTMP/t698 && echo x > AGENTS.md"
case "$(cat "$ERRF")" in
  *"PROJECT ROOT"*)
  assert 0 "(t20b) the refusal SAYS the root resolution (the clause is present)";;
  *) assert 1 "(t20b) the refusal does not say PROJECT ROOT (got: $(tr '\n' ' ' < "$ERRF"))";; esac
# (t20c) SANS CLAUDE_PROJECT_DIR (correction T-00000698, exec-critic sur b7055f0) :
#   la résolution se fait contre `.` (REDIR_REPO="${CLAUDE_PROJECT_DIR:-.}") et le
#   message le DIT — `PROJECT ROOT (.)`, jamais `PROJECT ROOT ()`. Cible : un
#   marqueur protégé RELATIF, pour que l'arm ne dépende pas du cwd du banc (la
#   clause protégée lit protect-paths.sh à côté du hook, jamais le cwd). `grep -F`
#   plutôt qu'un motif `case` : le pin est une chaîne littérale, parenthèses
#   comprises, sans motif à parser. Mutation nommée : `(${CLAUDE_PROJECT_DIR:-.})`
#   remis en `($CLAUDE_PROJECT_DIR)` dans l'echo de la garde 4 → (t20c) ROUGE,
#   nulle part ailleurs côté bash.
printf '%s' "$(json_payload 'printf y > .agents/state/gates/BINOME_REQUIRED')" | env -u CLAUDE_PROJECT_DIR bash "$HOOK" >"$OUTF" 2>"$ERRF"
T20C_RC=$?
if grep -qF 'PROJECT ROOT (.)' "$ERRF"; then
  assert "$([ "$T20C_RC" -eq 2 ] && echo 0 || echo 1)" "(t20c) without CLAUDE_PROJECT_DIR the refusal says PROJECT ROOT (.), the root it really resolved against (rc $T20C_RC)"
else
  assert 1 "(t20c) without CLAUDE_PROJECT_DIR the refusal must say PROJECT ROOT (.) (got: $(tr '\n' ' ' < "$ERRF"))"
fi
check_silent "(t21) the SAME name, absolute and OUTSIDE the repo, passes silently — the root resolution binds relative targets only" \
  "echo x > $EVTMP/t698/AGENTS.md"
check_deny_msg "(*.agents/state/gates/binome_required, outside)" \
  "(t22) a guard-arming marker OUTSIDE the repo is refused by its own rule, mode outside — wherever it lives" \
  "printf y > $EVTMP/t698/.agents/state/gates/BINOME_REQUIRED"
case "$(cat "$ERRF")" in
  *"judged against the list of THIS host"*)
  assert 0 "(t22b) the refusal SAYS a credential token is judged against THIS host's list — the clause is present, and true on both hook families";;
  *) assert 1 "(t22b) the refusal does not say 'judged against the list of THIS host' (got: $(tr '\n' ' ' < "$ERRF"))";; esac
# (t23) SKIP DIT, JAMAIS MUET (correction T-00000698, A-T1) : sur une racine qui
#   porte une espace ou un guillemet, cet arm est INJOIGNABLE par construction —
#   la cible absolue NUE est coupée à l'espace (la garde lit un préfixe qui n'est
#   pas le fichier, et bash non plus), et la cible CITÉE est invisible à l'étage
#   1 (T-00000720). Mesuré sur un clone sous un chemin avec espace : cet arm
#   était le seul rouge. Le skip nomme la racine et la raison ; le compte
#   PASS/FAIL ne bouge pas.
case "$CLAUDE_PROJECT_DIR" in
  *" "*|*"'"*|*'"'*)
  echo "SKIP: (t23) the inside arm is unreachable on this root <$CLAUDE_PROJECT_DIR>: a space or a quote in the root splits the bare absolute target and makes the quoted one invisible by design (T-00000720)";;
  *)
  check_deny_msg "AGENTS.md (git-tracked, inside)" \
    "(t23) an ABSOLUTE target under the root is the inside case — the only arm that reaches it" \
    "echo x > $CLAUDE_PROJECT_DIR/AGENTS.md";;
esac
check_deny_msg "(*.agents/state/gates/binome_required, outside)" \
  "(t24) a relative prefix that LEAVES the root (../) is outside, never relative — outside is tested first" \
  "printf y > ../t698-jetable/.agents/state/gates/BINOME_REQUIRED"
case "$(cat "$ERRF")" in
  *"binome_required, relative)"*)
  assert 1 "(t24b) a ../ target that leaves the root was labelled relative — the order of the mode test is wrong";;
  *) assert 0 "(t24b) a ../ target that leaves the root is NOT labelled relative";; esac
check_deny_msg "(*.agents/state/gates/push_defaut_autorise, relative)" \
  "(t25) the pilot-only exit of the default-branch guard, relative and git-ignored: refused by the protected clause, mode relative" \
  "printf y > .agents/state/gates/PUSH_DEFAUT_AUTORISE"
check_deny_msg "(*.agents/state/gates/push_defaut_protege, outside)" \
  "(t26) the default-branch arming marker OUTSIDE the repo: refused by its own rule, mode outside — a throwaway clone cannot arm it" \
  "printf y > $EVTMP/t698/.agents/state/gates/PUSH_DEFAUT_PROTEGE"
# (t27)-(t31) LE NOM D'UN MARQUEUR D'ARMEMENT EST REFUSÉ QUELLE QUE SOIT SA FORME
#   (correction T-00000698 — B#1 du binôme de clôture, MESURÉ sur les hooks
#   vivants avant le correctif) : `cd .agents/state/gates && printf y >
#   PUSH_DEFAUT_AUTORISE` et `printf y > ".agents/state/gates/PUSH_DEFAUT_
#   AUTORISE"` sortaient 0 tous deux — le cd cache le RÉPERTOIRE à la résolution
#   contre la racine, la citation rend la cible invisible à l'étage 1. Le NOM ne
#   se cache ni par l'un ni par l'autre : règle `arming-marker-name`, dernier
#   segment replié, liste DÉRIVÉE du bloc `*.agents/state/gates/<nom>)` de
#   protect-paths.sh (jamais une troisième copie). Liste FERMÉE : le cas général
#   — cd ou guillemets pour une cible ORDINAIRE — est T-00000720, pas ce lot, et
#   (t30) le tient tel quel. (t31) : une cible déjà refusée par son CHEMIN n'est
#   pas relistée par son nom. Mutation nommée : `marker_hits` retiré (ou MARKERS
#   vidé) du snippet de l'étage redirection → (t27)(t28)(t29) ROUGES, (t30) et
#   (t31) inchangés.
check_deny_msg "PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)" \
  "(t27) a marker name BARE after an internal cd is refused by its NAME — the cd hid the directory, not the name" \
  'cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE'
check_deny_msg '".agents/state/gates/PUSH_DEFAUT_AUTORISE" (arming-marker-name, quoted)' \
  "(t28) a QUOTED marker path is refused by its name — the one quoted target this guard reads" \
  'printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"'
check_deny_msg '$D/KICKOFF_REQUIRED (arming-marker-name, bare)' \
  "(t29) a marker name under an EXPANDED directory is refused by its name — the last segment is literal" \
  'printf y > $D/KICKOFF_REQUIRED'
check_silent "(t30) NEGATIVE CONTROL: an ordinary untracked name after an internal cd still passes — the general case is T-00000720, not this lot" \
  'cd docs && echo x > notes.txt'
printf '%s' "$(json_payload 'printf y > .agents/state/gates/PUSH_DEFAUT_AUTORISE')" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
T31_RC=$?
case "$(cat "$ERRF")" in
  *"PUSH_DEFAUT_AUTORISE (arming-marker-name"*)
  assert 1 "(t31) a target refused by its PATH must not be listed a second time by its name (got: $(tr '\n' ' ' < "$ERRF"))";;
  *)
  assert "$([ "$T31_RC" -eq 2 ] && echo 0 || echo 1)" "(t31) a target refused by its path is listed ONCE, by its path (rc $T31_RC)";;
esac
# (t32)-(t36) LES QUATRE CONTOURNEMENTS MEDIUM DE LA RÈGLE DE NOM (troisième
#   correction T-00000698 — revue sécurité S-00001921 sur 09a5284, chacun MESURÉ
#   passant sur les hooks vivants avant son correctif) :
#   M1 (Claude seul) `echo ${#x} > "…/PUSH_DEFAUT_AUTORISE"` sortait 0 : `#` après
#      `{` était lu comme tête de commentaire par `marker_hits` (classe STOP), bash
#      écrit le fichier. La tête de mot est désormais blanc, `;`, `&`, `|`, `(`, NL.
#   M2 (3 hôtes) `> ${D}/NOM`, `> $(pwd)/NOM`, backtick : `{`/`(`/backtick
#      coupaient le mot à `$`, rien à comparer ; l'expansion est traversée OPAQUE
#      (`opaque_end`) et le dernier segment littéral jugé. `${X}NOM` passe toujours.
#   M3 (3 hôtes) `>& NOM` avec un mot non numérique ÉCRIT ce fichier (mesuré créé)
#      et était sauté comme `>&N` ; seuls chiffres ou `-` sont une duplication
#      (`fd_dup`), dans `marker_hits` ET dans le scan principal — (t34b) le tient
#      sur un fichier suivi, comme le parseur unique de Python le fait déjà.
#   M4 (Python seul) `>|` coupé comme un tube par la coupe grossière ; sh refusait
#      déjà, (t35) le pin pour que la parité reste mesurée des deux côtés.
#   Mutations nommées : M1 → `head = ch in STOP` rétabli → (t32) ROUGE ;
#   M2 → l'appel `opaque_end` retiré de la boucle de mot → (t33)(t33b) ROUGES ;
#   M3 → `fd_dup` remplacé par `True` → (t34)(t34b) ROUGES ; (t36) inchangés.
check_deny_msg '".agents/state/gates/PUSH_DEFAUT_AUTORISE" (arming-marker-name, quoted)' \
  "(t32) M1: a hash after a brace is NOT a comment head — the name rule reads the redirect that follows" \
  'echo ${#x} > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"'
check_deny_msg '${D}/PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)' \
  "(t33) M2: a braced expanded directory is walked opaquely, the literal last segment is judged" \
  'printf y > ${D}/PUSH_DEFAUT_AUTORISE'
check_deny_msg '$(pwd)/PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)' \
  "(t33b) M2: a command-substituted directory likewise" \
  'printf y > $(pwd)/PUSH_DEFAUT_AUTORISE'
check_deny_msg 'PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)' \
  "(t34) M3: >&word with a non-numeric word is a WRITE to that file, judged by name" \
  'printf y >& PUSH_DEFAUT_AUTORISE'
check_deny_msg 'AGENTS.md (git-tracked, relative)' \
  "(t34b) M3: the same operator on a tracked file is refused by the PATH clause — the two scans keep one grammar" \
  'printf y >& AGENTS.md'
check_deny_msg 'PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)' \
  "(t35) M4: >| after an internal cd — refused here already, pinned so the Python parity stays measured" \
  'cd g && printf y >| PUSH_DEFAUT_AUTORISE'
check_silent "(t36) NEGATIVE CONTROL: \${#x} as data, an expansion glued to the name, fd close/dup/var, an ordinary >| target — all still pass" \
  'echo ${#x} > out-t698.txt; echo x > ${X}PUSH_DEFAUT_AUTORISE; echo err >&2; echo x >&-; echo y >& $fd; ls | wc -l || echo x >| out-t698.txt'

# =============================================================================
# T-00000762 — GARDE 3 ÉTENDUE (`reset --hard`, `stash` sans pathspec), GARDES 5
# (`git … --output`) ET 6 (`git grep -O`), GARDE 1b PAR OPÉRANDE. Chaque bras de
# refus asserte SON motif (L-00000161) : un rc 2 seul serait satisfait par la
# mauvaise garde. Rouges sur la BASE c3b9f07c : l23+ (DENY), w1-w13, w19,
# x1-x11, x20, x25-x30, et le contrôle positif de x-nohit (la passe
# n'existait pas). (x21) N'EST PAS rouge sur la base — correction du relevé
# d'exec-critic, recoupée : l'ancienne sous-chaîne ne trouvait aucun motif de
# liste dans `rm -rf lnk/x`, elle le refusait déjà ; il épingle la comparaison
# du LITTÉRAL, pas un défaut de la base. Mutants nommés (plan § 6, C6), bras
# qui les tuent :
#   M1 branche `reset` retirée de decide_git        -> (l23)-(l29)
#   M3 passe forcée à `OK`                          -> (x1)-(x11)
#   M4 passe forcée à `exit 1` (fail-closed)        -> bras ALLOW (x12)-(x17),
#      (x19), (x22), (x24) et :273-:275 ROUGES ; les DENY restent DENY
#   M4b `git ls-files` neutralisé (sortie vide)      -> (x18)
#   M5 `--output=` exact seul                        -> (w1)
#   M6 `O` retiré de la grappe courte                -> (w9)
#   M7 abréviations retirées                         -> (w13)
#   M10 condition `HIT` retirée                      -> (x-nohit)
#   M-zero clause « targets non vide » retirée       -> (h2bis) SEUL : (h2ter)
#      reste vert sous lui, son `xargs` le refuse par le drapeau `fed`
#      (correction du relevé d'exec-critic, recoupée par le mutant)
#   M-empty filtre des jetons vides retiré           -> (x24)
#   M-anchor ancre RÉSOLUE retirée                   -> (x13)(x23) et :273 sur
#      macOS ; sur Linux les deux ancres coïncident : mutant équivalent, dit
#   M-resolved comparaison du RÉSOLU retirée         -> (x29)
#   M-literal comparaison du LITTÉRAL retirée        -> (x21)
#   M-fed drapeau `fed` retiré                       -> (x25)-(x28)
#   M-norepo branche « not a git repository » retirée -> (x22)
#   M-awk erreur de syntaxe dans l'awk -> COVERAGE DEGRADED, chaque bras DENY
# =============================================================================
# (l23+) effacement git NON SCOPÉ, étendu. PORTÉE GLOBALE comme la règle
# checkout : un dépôt jetable n'est pas distingué (le texte ne dit pas où `cd`
# ou `-C` atterrira). `$f` nu est coupé à `$` par l'étage 2, donc sans pathspec ;
# `"$f"` cité devient `@@`, donc un pathspec.
check_deny_msg "unscoped" "(l23) git reset --hard"                     'git reset --hard'
check_deny_msg "unscoped" "(l24) git reset --hard HEAD"                'git reset --hard HEAD'
check_deny_msg "unscoped" "(l25) git reset --hard HEAD~1"              'git reset --hard HEAD~1'
check_deny_msg "unscoped" "(l26) git reset --hard origin/main"         'git reset --hard origin/main'
check_deny_msg "unscoped" "(l27) git -C <other repo> reset --hard"     'git -C /tmp/jetable reset --hard'
check_deny_msg "unscoped" "(l28) cd <other repo> && git reset --hard"  'cd /tmp/jetable && git reset --hard'
check_deny_msg "unscoped" "(l29) sudo git reset --hard"                'sudo git reset --hard'
check_deny_msg "unscoped" "(l30) git stash, bare"                      'git stash'
check_deny_msg "unscoped" "(l31) git stash push, no pathspec"          'git stash push'
check_deny_msg "unscoped" "(l32) git stash -u"                         'git stash -u'
check_deny_msg "unscoped" "(l33) git stash save wip (save takes no pathspec)" 'git stash save wip'
check_deny_msg "unscoped" "(l34) git stash push -m: the message value is not a pathspec" 'git stash push -m "wip"'
check_deny_msg "unscoped" "(l35) git stash -k"                         'git stash -k'
check_deny_msg "unscoped" "(l36) git stash push -- . (a BROAD pathspec)" 'git stash push -- .'
check_deny_msg "unscoped" "(l37) git stash push -- \$f (bare expansion cut at \$)" 'git stash push -- $f'
check_deny_msg "unscoped" "(l38) --work-tree value skipped: git --work-tree /x checkout ." 'git --work-tree /x checkout .'
check_deny_msg "unscoped" "(l39) --git-dir value skipped: git --git-dir /x/.git restore ." 'git --git-dir /x/.git restore .'
check 0 "(l40) git reset --soft HEAD~1 keeps the tree"          'git reset --soft HEAD~1'
check 0 "(l41) git reset HEAD -- <path> is scoped"              'git reset HEAD -- src/x'
check 0 "(l42) git reset (mixed) keeps the tree"                'git reset'
check 0 "(l43) git reset --keep refuses to lose local edits"    'git reset --keep'
check 0 "(l44) git reset --merge"                               'git reset --merge'
check 0 "(l45) git stash push -- <path> is scoped"              'git stash push -- src/x'
check 0 "(l46) git stash push -m <msg> -- <path> is scoped"     'git stash push -m "wip" -- src/x'
check 0 "(l47) implicit git stash -- <path> is scoped"          'git stash -- src/x'
check 0 "(l48) git stash push -- \"\$f\": a quoted pathspec"    'git stash push -- "$f"'
check 0 "(l49) git stash list"                                  'git stash list'
check 0 "(l50) git stash show -p"                               'git stash show -p'
check 0 "(l51) git stash pop"                                   'git stash pop'
check 0 "(l52) git stash apply"                                 'git stash apply'
check 0 "(l53) git stash drop"                                  'git stash drop'
check 0 "(l54) git stash clear"                                 'git stash clear'
check 0 "(l55) KNOWN GAP: git reset --hard behind nice -n <n> (envelope window, rm/mv only)" 'nice -n 10 git reset --hard'

# (w1)-(w20) GARDE 5 `--output` et GARDE 6 `git grep -O`.
check_deny_msg "--output" "(w1) git show --output=<tracked> overwrites it"   'git show --output=README.md HEAD'
check_deny_msg "--output" "(w2) git log --output=<f> -1"                     'git log --output=/tmp/x -1'
check_deny_msg "--output" "(w3) git log --output <f> (separated value)"      'git log --output /tmp/x'
check_deny_msg "--output" "(w4) git diff --output=<f>"                       'git diff --output=f'
check_deny_msg "--output" "(w5) git stash show --output=<f>"                 'git stash show --output=f'
check_deny_msg "open-files-in-pager" "(w6) git grep -O<cmd> runs <cmd>"       "git grep -O'sh -c id' foo"
check_deny_msg "open-files-in-pager" "(w7) git grep -O bare runs the pager"   'git grep -O foo'
check_deny_msg "open-files-in-pager" "(w8) git grep -Ovim"                    'git grep -Ovim foo'
check_deny_msg "open-files-in-pager" "(w9) git grep -nO: O inside a short cluster" 'git grep -nO foo'
check_deny_msg "open-files-in-pager" "(w10) git grep -iO"                     'git grep -iO foo'
check_deny_msg "open-files-in-pager" "(w11) git grep --open-files-in-pager=less" 'git grep --open-files-in-pager=less foo'
check_deny_msg "open-files-in-pager" "(w12) git grep --open=x (abbreviation)" 'git grep --open=x foo'
check_deny_msg "open-files-in-pager" "(w13) git grep --op=x (shortest abbreviation)" 'git grep --op=x foo'
check 0 "(w14) --output-indicator-new is ANOTHER option (writes nothing)"    'git log --output-indicator-new=x -1'
check 0 "(w15) git grep -e Ofoo: O is the pattern value, nothing runs"       'git grep -e Ofoo'
check 0 "(w16) git grep -o is --only-matching, never --output"               'git grep -o foo'
check 0 "(w17) git grep --or is not --open-files-in-pager"                   'git grep --or -e a -e b'
check 0 "(w18) --output after -- is a path, not an option"                  'git log -- --output'
check_deny_msg "--output" "(w19) git archive --output=<f> (any subcommand, decision 3)" 'git archive --output=x.tar HEAD'
check 0 "(w20) KNOWN GAP: git archive -o <f> writes a file and passes (-o is never read, carried by T-00000764)" 'git archive -o x.tar HEAD'

# (x1)-(x30) GARDE 1b PAR OPÉRANDE. La liste est ANCRÉE : un opérande hors liste
# refuse la commande, même quand un AUTRE opérande est dans la liste.
check_deny_msg "checkpoint" "(x1) rm <tracked> /tmp/x: /tmp/x no longer carries README.md" 'rm README.md /tmp/x'
check_deny_msg "checkpoint" "(x2) mv <tracked> /tmp/x: the source is judged"   'mv README.md /tmp/x'
check_deny_msg "checkpoint" "(x3) rm docs/build/x.md: build/ is not the FIRST component" 'rm docs/build/x.md'
check_deny_msg "checkpoint" "(x4) rm .cache-notes.md: .cache is a component, not a prefix" 'rm .cache-notes.md'
check_deny_msg "checkpoint" "(x5) a substitution glued to a /tmp operand does not carry a second operand" 'rm -rf /tmp/a$(echo x) README.md'
check_deny_msg "checkpoint" "(x6) mv -t <tmp> <tracked>: every operand is judged" 'mv -t /tmp/x README.md'
check_deny_msg "checkpoint" "(x7) PARTIAL dissolution: dist/x passes, \$HOME dissolves"  'rm -rf dist/x $HOME'
check_deny_msg "checkpoint" "(x8) PARTIAL dissolution, quoted"                  'rm -rf dist/x "$HOME"'
check_deny_msg "checkpoint" "(x9) rm -rf /tmp: the anchor itself is not STRICTLY under it" 'rm -rf /tmp'
check_deny_msg "checkpoint" "(x10) find -exec rm: operands come from a pipe"   "find /tmp/x -name '*.o' -exec rm {} \\;"
check_deny_msg "checkpoint" "(x11) rm -rf src/tmp/x: tmp is not the first component" 'rm -rf src/tmp/x'
check 0 "(x12) a quoted /tmp path with a space"                                'rm -rf "/tmp/a b"'
T762_TMP_RESOLVED="$("$PY" -c "from pathlib import Path; print(Path('/tmp').resolve())")"
if [ "$T762_TMP_RESOLVED" = "/private/tmp" ]; then
  check 0 "(x13) /private/tmp/x: the RESOLVED anchor, computed (macOS)"        'rm -rf /private/tmp/x'
else
  check_deny_msg "checkpoint" "(x13) /private/tmp/x is no temp dir here (resolved /tmp = $T762_TMP_RESOLVED)" 'rm -rf /private/tmp/x'
fi
check 0 "(x14) ./node_modules/: the ./ is dropped by construction"             'rm -rf ./node_modules/'
check 0 "(x15) a redirect is not an operand: 2>/dev/null is skipped"           'rm -rf dist/x 2>/dev/null'
check 0 "(x16) rm behind timeout and its duration, allowlisted operand"        'timeout 5 rm -rf /tmp/scratch'
check 0 "(x17) git rm then an allowlisted rm"                                  'git rm -q x && rm -rf /tmp/scratch'
# (x18)(x19)(x21) LE VETO DU SUIVI, dans un dépôt jetable (build/keep.txt
# COMMITÉ), CLAUDE_PROJECT_DIR pointé dessus pour CES bras seuls.
T762_JET="$EVTMP/t762-jetable"
mkdir -p "$T762_JET/build"
printf 'keep\n' > "$T762_JET/build/keep.txt"
git -C "$T762_JET" init -q >/dev/null 2>&1
git -C "$T762_JET" add build/keep.txt >/dev/null 2>&1
git -C "$T762_JET" -c user.email=t@t -c user.name=t commit -qm fixture >/dev/null 2>&1
ln -s /tmp "$T762_JET/lnk"
T762_PROJECT_SAVED="$CLAUDE_PROJECT_DIR"
export CLAUDE_PROJECT_DIR="$T762_JET"
check_deny_msg "checkpoint" "(x18) VETO: build/keep.txt is TRACKED, so the list does not carry it" 'rm build/keep.txt'
check 0 "(x19) the same directory, an untracked file passes"                  'rm build/other.txt'
check_deny_msg "checkpoint" "(x21) lnk -> /tmp: the LITERAL lnk/x is outside the list, whatever it resolves to" 'rm -rf lnk/x'
# (y62)(y63) LE VETO EST INSENSIBLE À LA CASSE (addendum c, passe binôme) : sur
# APFS ou NTFS — insensibles à la casse — `rm build/KEEP.txt` efface le
# `build/keep.txt` SUIVI ; `git ls-files -- :(icase)…` le voit. Sur un système
# sensible à la casse (ext4, la CI ubuntu) c'est un AUTRE fichier, et le veto y
# est un sur-refus nommé, sans effacement possible.
check_deny_msg "checkpoint" "(y62) icase VETO: build/KEEP.txt names the tracked build/keep.txt on a case-insensitive filesystem" 'rm build/KEEP.txt'
check_deny_msg "checkpoint" "(y63) icase VETO: build/keep.TXT, same file on APFS" 'rm build/keep.TXT'
# (x22) un projet SANS git : rc 128 « not a git repository » = rien n'est suivi.
T762_NOGIT="$EVTMP/t762-nogit"
mkdir -p "$T762_NOGIT"
export CLAUDE_PROJECT_DIR="$T762_NOGIT"
check 0 "(x22) no git repository: nothing is tracked, build/x passes"         'rm -rf build/x'
export CLAUDE_PROJECT_DIR="$T762_PROJECT_SAVED"
check_deny_msg "checkpoint" "(h2bis) a bare rm has no operand to judge"        'rm'
check_deny_msg "checkpoint" "(h2ter) rm fed by xargs has no static operand"    'git ls-files | xargs rm -f'
check_deny_msg "LITERAL prefix" "(x20) an operand that starts with an expansion is judged by its LITERAL prefix" 'S=/private/tmp/x; rm -rf "$S/y"'
if [ "$T762_TMP_RESOLVED" = "/private/tmp" ]; then
  check 0 "(x23) the agents' scratchpad under /private/tmp (macOS)"           'rm -rf /private/tmp/claude-502/-Users-x-proj/0000-sess/scratchpad/x'
else
  check_deny_msg "checkpoint" "(x23) /private/tmp/... is no temp dir here"    'rm -rf /private/tmp/claude-502/-Users-x-proj/0000-sess/scratchpad/x'
fi
check 0 "(x24) an escaped quote is not an operand: the rm is seen, its target passes" 'echo \" ; rm -rf .tmp/x \"'
check_deny_msg "pipe" "(x25) ls | xargs rm -f build/x: fed by a pipe"          'ls | xargs rm -f build/x'
check_deny_msg "pipe" "(x26) printf | xargs rm -f build/x: fed by a pipe"      "printf 'src/x' | xargs rm -f build/x"
check_deny_msg "pipe" "(x27) find -exec rm -f build/x: fed by find"            "find . -name '*.o' -exec rm -f build/x {} \\;"
check_deny_msg "pipe" "(x28) parallel rm -f build/x: fed by parallel"          'parallel rm -f build/x'
# (x29) littéral SOUS l'ancre, résolu HORS d'elle : le bras porte le chemin
# DÉVELOPPÉ au moment du banc, et asserte que le refus n'est PAS celui du
# préfixe littéral (sinon il passerait pour la mauvaise raison — réserve R2).
T762_LINKDIR="$(mktemp -d /tmp/t762.XXXXXX)"
ln -s /etc "$T762_LINKDIR/l"
check_deny_msg "checkpoint" "(x29) literal under /tmp/, resolved outside it (symlink to /etc)" "rm -rf $T762_LINKDIR/l/x"
case "$(cat "$ERRF")" in
  *LITERAL*) assert 1 "(x29b) the x29 refusal is not the LITERAL-prefix one";;
  *) assert 0 "(x29b) the x29 refusal is not the LITERAL-prefix one";;
esac
rm -rf "$T762_LINKDIR"
check_deny_msg "checkpoint" "(x30) a NESTED node_modules is outside the anchored list" 'rm -rf packages/ui/node_modules'
# (x-nohit) LA PASSE NE TOURNE QUE SUR `HIT`. Un shim `python3` en tête de PATH
# journalise ses arguments puis `exec` le python RÉEL, résolu AVANT le
# changement de PATH ; le shim inspecte l'argument `-c` (le TEXTE du programme,
# qui porte le marqueur `T762-RMMV-PASS`), jamais stdin (réserve R9).
T762_SHIM="$EVTMP/t762-shim"
mkdir -p "$T762_SHIM"
T762_LOG="$T762_SHIM/argv.log"
printf '#!/bin/sh\n' > "$T762_SHIM/python3"
printf 'printf "%%s\\n" "$@" >> "%s"\n' "$T762_LOG" >> "$T762_SHIM/python3"
printf 'exec "%s" "$@"\n' "$REAL_PY" >> "$T762_SHIM/python3"
chmod +x "$T762_SHIM/python3"
: > "$T762_LOG"
printf '%s' "$(json_payload 'ls -la')" | PATH="$T762_SHIM:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
t762_rc=$?
if [ "$t762_rc" -eq 0 ] && [ -s "$T762_LOG" ] && ! grep -q 'T762-RMMV-PASS' "$T762_LOG"; then t762_ok=0; else t762_ok=1; fi
assert "$t762_ok" "(x-nohit) no rm/mv recognised: the per-operand pass is never launched (rc $t762_rc)"
: > "$T762_LOG"
printf '%s' "$(json_payload 'rm -rf /tmp/x')" | PATH="$T762_SHIM:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
if grep -q 'T762-RMMV-PASS' "$T762_LOG"; then t762_ok=0; else t762_ok=1; fi
assert "$t762_ok" "(x-nohit-ctl) POSITIVE CONTROL: a recognised rm launches the pass (the marker is logged)"

# =============================================================================
# T-00000762, PASSE BINÔME (constats S-00002512, arbitrages S-00002513, addendum
# d'orchestrateur). Chaque bras de refus asserte SON motif. MESURÉ contre le
# garde de la base eb058e8a (SAFE_BASH_HOOK) : 55 rouges — (l21) retourné plus
# haut, (y1)-(y9), (y11)-(y19), (y21)-(y23), (y25)-(y31), (y33)-(y38),
# (y41)-(y43), (y45)(y46), (y48)(y49), (y51), (y54)-(y57), (y60)-(y65) ;
# (y10) (y20) (y24) (y32) (y39) (y40) (y44) (y47) (y50) (y52) (y53) (y58)
# (y59) sont les CONTRÔLES, verts sur la base comme après. Mutants de la
# passe, chacun appliqué sur un clone jetable puis annulé :
#   M-coarse   `(?<![<>])(?!&>)` retiré de la coupe grossière -> (y1)-(y3)
#   M-envfeed  `fed` non posé dans la fenêtre d'enveloppe      -> (y4)-(y6b)
#   M-frames   la fermeture ne restaure plus l'état            -> (y7)(y8)(y11b)
#   M-redir    la cible d'une redirection prend la place       -> (y11)(y14)-(y16)
#   M-exp      tout `$` redevient un séparateur (le nom reste un mot)
#                                                              -> (y9)(y17)(y18)(y65)
#   M-ok       `-ok`/`-okdir` retirés                          -> (y12)(y13)
#   M-mvglued  la destination collée n'est plus lue            -> (y21)-(y23)
#   M-abbrev   gitlong exige le nom exact                      -> (y25)-(y28)
#   M-fromfile `--pathspec-from-file=-` redevient un pathspec  -> (y29)-(y31)
#   M-broad    broadspec réduit à `.` `./` `:/`                -> (y33)-(y36)(l21)
#   M-rawspan  la table des segments cités ignorée (qv = 0), en deux variantes :
#              repli FERMÉ tel qu'écrit (un `@@` lu large)     -> (y39)(y41)(y47)(l48)
#              repli OUVERT (un `@@` lu comme un mot)          -> (y33)(y34)(y37)(y38)
#   M-glue     un `@@` collé redevient un mot                  -> (y41)
#   M-hidden   GITHIDDEN jamais noté                           -> (y42)(y43)
#   M-bound    la tranche n'est plus bornée à `)` ni à ` #`    -> (y48)(y49)(y51)(y64)
#              ((y50) reste vert sous lui : `build/x)` ouvre sur `build`)
#   M-zero     (plus haut) recoupé ici : tue (h2bis), laisse (h2ter) vert
#   M-awk      erreur de syntaxe dans l'awk -> COVERAGE DEGRADED annoncé
#   M-motive   un opérande à expansion redevient « outside »   -> (y54)
#   M-dry      le dry run de `git clean` n'est plus lu         -> (y55)-(y57)
#   M-icase    `:(icase)` retiré du veto                       -> (y62)(y63)
# =============================================================================
# (y1)-(y3) F1 : `&>`, `&>>` et `<&` ne sont pas des séparateurs, ce sont des
# opérateurs de redirection ; la coupe y rejetait `src/a.py` dans un segment à
# part, et le rm passait sur la foi de `build/x`.
check_deny_msg "checkpoint" "(y1) rm build/x &>/dev/null src/a.py: &> is a redirect, src/a.py stays an operand" 'rm build/x &>/dev/null src/a.py'
check_deny_msg "checkpoint" "(y2) rm build/x <&- src/a.py: <& is a redirect"        'rm build/x <&- src/a.py'
check_deny_msg "checkpoint" "(y3) rm build/x &>>/dev/null src/a.py: &>> is a redirect" 'rm build/x &>>/dev/null src/a.py'
# (y4)-(y6b) F2 : l'alimentation survit à une enveloppe qui a ses propres
# arguments devant xargs/parallel.
check_deny_msg "pipe" "(y4) ls | nice -n 10 xargs rm -f build/x"     'ls | nice -n 10 xargs rm -f build/x'
check_deny_msg "pipe" "(y5) ls | timeout 5 xargs rm -f build/x"      'ls | timeout 5 xargs rm -f build/x'
check_deny_msg "pipe" "(y6) ls | sudo -u root xargs rm -f build/x"   'ls | sudo -u root xargs rm -f build/x'
check_deny_msg "pipe" "(y6b) nice -n 10 parallel rm -f build/x"      'nice -n 10 parallel rm -f build/x'
# (y7)-(y11b) addendum a : l'alimentation survit à une substitution de
# processus (le CADRE restaure l'état), à une expansion, à un fichier
# d'arguments, à une redirection en tête — et à un `;` DANS le cadre.
check_deny_msg "pipe" "(y7) xargs -a <(git ls-files) rm -f build/x"     'xargs -a <(git ls-files) rm -f build/x'
check_deny_msg "pipe" "(y8) parallel -a <(git ls-files) rm -f build/x"  'parallel -a <(git ls-files) rm -f build/x'
check_deny_msg "pipe" "(y9) xargs -a \$F rm -f build/x"                 'xargs -a $F rm -f build/x'
check_deny_msg "pipe" "(y10) xargs --arg-file=list.txt rm -f build/x"   'xargs --arg-file=list.txt rm -f build/x'
check_deny_msg "pipe" "(y11) < list.txt xargs rm -f build/x: a leading redirect does not take the command slot" '< list.txt xargs rm -f build/x'
check_deny_msg "pipe" "(y11b) xargs -a <(a; b) rm -f build/x: a ; inside the frame does not lose it" 'xargs -a <(a; b) rm -f build/x'
# (y12)(y13) addendum b : `find -ok`/`-okdir` rouvrent la commande, alimentée.
check_deny_msg "pipe" "(y12) find -ok rm -f build/x: fed by find"     "find . -name x -ok rm -f build/x {} \\;"
check_deny_msg "pipe" "(y13) find -okdir rm -f build/x: fed by find"  "find . -name x -okdir rm -f build/x {} \\;"
# (y14)-(y20) LA CLASSE PRÉEXISTANTE que la marche par séparateurs laissait
# passer rc 0 sur les TROIS hôtes (mesuré au lancement de la passe) : une cible
# de redirection ou une expansion prenait la place de la commande et cachait le
# verbe. (y20) est le contrôle : un `)` que rien n'ouvre (motif de `case`)
# rouvre la commande, comme un `;`.
check_deny_msg "checkpoint" "(y14) < list.txt rm -rf src/x"     '< list.txt rm -rf src/x'
check_deny_msg "checkpoint" "(y15) > out.txt rm -rf src/x"      '> out.txt rm -rf src/x'
check_deny_msg "checkpoint" "(y16) 2>/dev/null rm -rf src/x"    '2>/dev/null rm -rf src/x'
check_deny_msg "checkpoint" "(y17) sudo \$X rm -rf src/x: an expansion takes the command slot, unknown" 'sudo $X rm -rf src/x'
check_deny_msg "checkpoint" "(y18) FOO=\$x rm -rf src/x: the expansion is the assignment's value" 'FOO=$x rm -rf src/x'
check_deny_msg "checkpoint" "(y19) FOO=\"bar\" rm -rf src/x: the quoted run is the assignment's value" 'FOO="bar" rm -rf src/x'
check_deny_msg "checkpoint" "(y65) \$X rm -rf build/x: an expansion in the command slot is an unknown command, its rm is fed" '$X rm -rf build/x'
# (y20) sur DEUX lignes : la clause collée au `in` sur la même ligne est une
# des huit formes que le parseur du SAST ne lit pas (CONVENTIONS_shell.md § 6),
# et le filet la voit même dans une chaîne de banc.
check 0 "(y20) a case pattern (a closing paren nothing opened) reopens the command" 'case $x in
a) rm -rf .tmp/x;; esac'
# (y21)-(y24) F3 : la destination COLLÉE de `mv` est un opérande.
check_deny_msg "checkpoint" "(y21) mv -tsrc build/x: the glued -t destination is judged"  'mv -tsrc build/x'
check_deny_msg "checkpoint" "(y22) mv --target-directory=src build/x"                     'mv --target-directory=src build/x'
check_deny_msg "checkpoint" "(y23) mv --targ=src build/x: an abbreviation"                 'mv --targ=src build/x'
check 0 "(y24) mv -tbuild/y build/x: a glued destination inside the list passes"           'mv -tbuild/y build/x'
# (y25)-(y32) F4 : les abréviations de git (mesurées, git 2.55 : `--h` efface
# déjà comme `--hard`) et la liste lue sur l'entrée standard.
check_deny_msg "unscoped" "(y25) git reset --h (git 2.55 wipes on one letter)" 'git reset --h'
check_deny_msg "unscoped" "(y26) git reset --har HEAD"                          'git reset --har HEAD'
check_deny_msg "unscoped" "(y27) git restore --staged --wo .: --wo is --worktree" 'git restore --staged --wo .'
check_deny_msg "unscoped" "(y28) git stash push --m wip: --m is --message, its value is no pathspec" 'git stash push --m wip'
check_deny_msg "unscoped" "(y29) git stash push --pathspec-from-file=-: a list from a pipe" 'git stash push --pathspec-from-file=-'
check_deny_msg "unscoped" "(y30) git stash push --pathspec-from-file -"         'git stash push --pathspec-from-file -'
check_deny_msg "unscoped" "(y31) git restore --pathspec-from-file=-"            'git restore --pathspec-from-file=-'
check 0 "(y32) git stash push --pathspec-from-file=list.txt: a named list scopes" 'git stash push --pathspec-from-file=list.txt'
# (y33)-(y41) PATHSPECS LARGES, et le pathspec CITÉ lu par la table des
# segments (décision 1) : DIVERGENCE 7 n'a plus de pathspec.
check_deny_msg "unscoped" "(y33) git checkout -- '*' (quoted glob, read through the span table)" "git checkout -- '*'"
check_deny_msg "unscoped" "(y34) git restore ':(top)'"                          "git restore ':(top)'"
check_deny_msg "unscoped" "(y35) git restore ./."                               'git restore ./.'
check_deny_msg "unscoped" "(y36) git stash push -- ':!src/x': an exclude-only pathspec is everything else" "git stash push -- ':!src/x'"
check_deny_msg "unscoped" "(y37) git checkout -- \".\": DIVERGENCE 7 closed for a pathspec" 'git checkout -- "."'
check_deny_msg "unscoped" "(y38) git stash push -- \".\""                       'git stash push -- "."'
check 0 "(y39) git restore \"src/a b.txt\": a quoted PRECISE path passes"        'git restore "src/a b.txt"'
check 0 "(y40) git restore -- src/x: control, a precise path passes"             'git restore -- src/x'
check_deny_msg "unscoped" "(y41) git --git-dir=\"\$d\" restore .: a quoted run GLUED to the option is its value" 'git --git-dir="$d" restore .'
# (y42)-(y47) décision 3 : une expansion NON citée là où git lit sa sous-
# commande est refusée fail-closed ; une VALEUR qui est une expansion ne cache
# rien ; comme pathspec elle est LARGE, et la citer la rend précise.
check_deny_msg "where git reads its subcommand" "(y42) git \$SUB ."            'git $SUB .'
check_deny_msg "where git reads its subcommand" "(y43) git \$(echo reset) --hard" 'git $(echo reset) --hard'
check 0 "(y44) git -C \$d status: an expansion VALUE is skipped as a value"      'git -C $d status'
check_deny_msg "unscoped" "(y45) git -C \$d reset --hard: the value skipped, the wipe seen" 'git -C $d reset --hard'
check_deny_msg "unscoped" "(y46) git checkout \$BRANCH: an unquoted expansion pathspec is broad" 'git checkout $BRANCH'
check 0 "(y47) git checkout \"\$BRANCH\": quoted, it is one word"               'git checkout "$BRANCH"'
# (y48)-(y53) LA TRANCHE PAR OPÉRANDE s'arrête à un `)` non imbriqué et à un
# ` #` de commentaire (régression de la première passe) — jamais à un `}`
# (argument ordinaire pour bash hors position de commande : `rm x } y` efface
# `}` et `y`) ni à un `)` échappé.
check 0 "(y48) rm -rf /tmp/x # clean up: a comment is no operand"                'rm -rf /tmp/x # clean up'
check 0 "(y49) ( rm -rf /tmp/x ): the closing paren is no operand"               '( rm -rf /tmp/x )'
check 0 "(y50) (cd /tmp && rm -rf build/x): idem, after a cd"                    '(cd /tmp && rm -rf build/x)'
check_deny_msg "x (outside)" "(y51) (cd /tmp && rm -rf x): x is judged against the ROOT, never the cd (R1)" '(cd /tmp && rm -rf x)'
check_deny_msg "src/a.py (outside)" "(y52) rm -rf .tmp/x } src/a.py: a } is an argument, not a bound" 'rm -rf .tmp/x } src/a.py'
check_deny_msg "src/a.py (outside)" "(y53) rm -rf .tmp/x\\) src/a.py: an escaped ) is no bound" 'rm -rf .tmp/x\) src/a.py'
check 0 "(y64) rm -rf build/x # src/a.py: what the comment names is not deleted" 'rm -rf build/x # src/a.py'
# (y54) décision 2 : `/tmp/$X` reste refusé, jugé par son préfixe LITTÉRAL.
check_deny_msg "LITERAL prefix" "(y54) rm -rf /tmp/\$X: dissolved, judged by its literal prefix /tmp/" 'rm -rf /tmp/$X'
# (y55)-(y61) décision 5 : le dry run de `git clean` passe, et chaque refus
# d'effacement nomme un remède POSSIBLE pour sa sous-commande.
check 0 "(y55) git clean -n: a dry run deletes nothing"                         'git clean -n'
check 0 "(y56) git clean --dry-run"                                             'git clean --dry-run'
check 0 "(y57) git clean -ndx: n in a cluster"                                  'git clean -ndx'
check_deny_msg "unscoped" "(y58) git clean -fdx: control, still refused"        'git clean -fdx'
check_deny_msg "unscoped" "(y59) git clean -f -e -n: -n is the -e VALUE, no dry run" 'git clean -f -e -n'
check_deny_msg "git clean -n" "(y60) the clean refusal names the dry run as its remedy" 'git clean -fdx'
check_deny_msg "git reset --keep" "(y61) the reset --hard refusal names a remedy that takes no path" 'git reset --hard'

# =============================================================================
# (sb) T-01M5D6XS2SJ6021Y97X3Z7BX8V — les six défauts du lot safe-bash, côté
# Claude (T-01M55CF5, T-01M55BRE, T-01M53RGW, T-01M53HV4, T-01M55TRZ,
# T-01M56ZE6). Plan docs/tasks/T-01M5D6XS2SJ6021Y97X3Z7BX8V-plan.md (rév. 3) et
# son annexe. Chaque témoin rougit contre le hook de bfa51a8f (SAFE_BASH_HOOK) —
# sauf (sb1b), (sb2e), (sb2f), (sb2h), (sb5e), (sb6f), CONTRÔLES déjà refusés
# sur la base, qui tiennent la non-régression. Les (sbNnK) sont les négatifs de
# l annexe, laissés passer sur la base comme au livré. La CARTE DES MUTANTS de
# cette section : en tête de safe-bash.test.sh.
# =============================================================================
# (sb1) ÉTAPE 1 — `$'…'` est une citation ANSI-C : l antislash y échappe.
check_deny_msg "unscoped" "(sb1a) \$'\\'' is ONE span: the reset after it is code" "echo \$'\\'' ; git reset --hard ; echo 'x'"
check_deny_msg "unscoped" "(sb1b) control: the same without the trailing quote" "echo \$'\\'' ; git reset --hard"
check_deny_msg "checkpoint" "(sb1c) \$'\\'' then rm -rf src" "echo \$'\\'' ; rm -rf src ; echo 'x'"
check_deny_msg "git branch -D" "(sb1d) \$'\\'' then git branch -D wt/T-1" "echo \$'\\'' ; git branch -D wt/T-1 ; echo 'x'"
check_deny_msg "git branch -D" "(sb1e) an octal escape decodes to the option (C8b)" "git branch \$'\\055D' wt/T-1"
check_silent "(sb1n) negative: \$'a\\tb' then git status" "echo \$'a\\tb' ; git status"
check_silent "(sb1n2) negative: an escaped apostrophe inside \$'…'" "printf %s \$'it\\'s' ; echo 'x'"
# (sb2) ÉTAPE 2 — dans "…", `$(…)` et backtick NON échappés sont du CODE ; un
# corps de heredoc à délimiteur CITÉ ouvert dans ce `$(…)` reste une DONNÉE
# jusqu à la première ligne qui COMMENCE par le délimiteur (blancs de tête
# retirés) ; les guillemets d un corps NU sont littéraux ; `$X git …` est lu
# comme `sudo $X git …`.
check_deny_msg "unscoped" "(sb2a) a continued comment inside \"\$(…)\" ends at its line: the reset runs" \
  "$(printf 'echo "$(# c \\\ngit reset --hard\n)"')"
check_deny_msg "unscoped" "(sb2b) a quote in a BARE heredoc body is literal: it pairs with nothing" \
  "$(printf 'cat <<EOF\n"\nEOF\necho ok # c \\\ngit reset --hard # "')"
check_deny_msg "git branch -D" "(sb2c) \$X git branch -D wt/T-1 is read like sudo \$X git …" '$X git branch -D wt/T-1'
check_deny_msg "unscoped" "(sb2d) echo \"\$(git reset --hard)\": the substitution runs" 'echo "$(git reset --hard)"'
check_deny_msg "checkpoint" "(sb2d2) echo \"\$(rm -rf src)\"" 'echo "$(rm -rf src)"'
check_deny_msg "unscoped" "(sb2e) control (C13 h2): EOF) closes the quoted body inside \$(…)" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nx\nEOF)"\ngit reset --hard' "'" "'")"
check_deny_msg "unscoped" "(sb2f) control (C13 h1): the body closes at EOF), not at the later EOF" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nx\nEOF)"\ngit reset --hard\nEOF\n#)"' "'" "'")"
check_deny_msg "unscoped" "(sb2g) C14: a BARE delimiter in \$(…): its body runs its own \$(…)" \
  "$(printf 'git commit -m "$(cat <<EOF\nx\n$(git reset --hard)\nEOF\n)"')"
check_deny_msg "unscoped" "(sb2h) C17: <<- and a TAB before EOF) close the quoted body (leading blanks stripped)" \
  "$(printf 'git commit -m "$(cat <<-%sEOF%s\nx\n\tEOF)"\ngit reset --hard\nEOF\n#)"' "'" "'")"
check_deny_msg "unscoped" "(sb2fp) C18 ACCEPTED FALSE POSITIVE: a body line EOFX closes earlier than bash, the rest is analysed" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nEOFX\ngit reset --hard\nEOF\n)"' "'" "'")"
# (sb2j)(sb2k) les formes de C13/C17 dont la substitution SE FERME plus loin
# (`)"` réel, et non `#)"`) : bash ferme le corps à `EOF)"` et EXÉCUTE la ligne
# du milieu (mesuré, bash 5.3 et 3.2, fichier, -c et eval) ; une clôture plus
# tardive blanchirait le reset. (sb2e)(sb2f)(sb2h) n y suffisent pas : leur
# `#)"` laisse la substitution ouverte pour le scanner, qui ARRÊTE alors la
# lecture et analyse tout.
check_deny_msg "unscoped" "(sb2j) C13: the quoted body closes at EOF), the reset after it runs even when a later EOF and ) follow" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nx\nEOF)"\ngit reset --hard\nEOF\n)"' "'" "'")"
check_deny_msg "unscoped" "(sb2k) C17: <<- with a TAB before EOF), same form" \
  "$(printf 'git commit -m "$(cat <<-%sEOF%s\nx\n\tEOF)"\ngit reset --hard\nEOF\n)"' "'" "'")"
sb_deep=""; sb_shut=""; sb_k=0
while [ "$sb_k" -lt 70 ]; do sb_deep="$sb_deep\"\$("; sb_shut="$sb_shut)\""; sb_k=$((sb_k + 1)); done
check_deny_msg "unscoped" "(sb2i) more than 64 nested levels stop the scan: nothing after is hidden" \
  "echo ${sb_deep}x${sb_shut} ; echo \"\$(date)\" ; git reset --hard ; echo \"x\""
# (sb2l) LE COÛT de la lecture récursive : 200 `"$(` imbriqués et jamais
# fermés se lisent en temps BORNÉ (arrêt au premier échec imbriqué, aucune
# relecture spéculative, qui serait exponentielle). Joué sous un délai de 30 s,
# groupe de processus tué au dépassement.
sb_open=""; sb_k=0
while [ "$sb_k" -lt 200 ]; do sb_open="$sb_open\"\$("; sb_k=$((sb_k + 1)); done
printf '%s' "$(json_payload "echo ${sb_open}x")" > "$EVTMP/sb2l.json"
"$PY" -c 'import os, signal, subprocess, sys
p = subprocess.Popen(["bash", sys.argv[1]], stdin=open(sys.argv[2]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
try:
    rc = p.wait(timeout=30)
except subprocess.TimeoutExpired:
    if hasattr(os, "killpg"):
        os.killpg(p.pid, signal.SIGKILL)
    else:
        p.kill()
    p.wait()
    rc = 99
sys.exit(0 if rc == 0 else 1)' "$HOOK" "$EVTMP/sb2l.json"
assert $? "(sb2l) 200 nested unclosed \"\$( are read in bounded time, exit 0"
check_silent "(sb2n) negative: echo \"\$(date) # c\"" 'echo "$(date) # c"'
check_silent "(sb2n2) negative: a quote in a bare heredoc body" "$(printf 'cat <<EOF\nhello "\nEOF\necho ok')"
check_silent "(sb2n3) negative C1a: a QUOTED body inside \$(…) is data" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nfix: x\ngit reset --hard\nEOF\n)"' "'" "'")"
check_silent "(sb2n4) negative C1b: rm -rf in a QUOTED body inside \$(…)" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nfix: x\nrm -rf src\nEOF\n)"' "'" "'")"
check_silent "(sb2n5) negative C9a: an ESCAPED \$( is text" 'echo "\$(git reset --hard)"'
check_silent "(sb2n6) negative C9b: an ESCAPED backtick is text" 'echo "\`git reset --hard\`"'
check_silent "(sb2n6b) negative C9b, spaced: no trailing backslash to mask the option" 'echo "\` git reset --hard \`"'
check_silent "(sb2n7) negative: \$X status" '$X status'
check_silent "(sb2n8) negative: \"\$PY\" -m pytest -q" '"$PY" -m pytest -q'
check_silent "(sb2n9) negative: \$EDITOR README.md" '$EDITOR README.md'
check_silent "(sb2n10) negative: git commit -m \"wip \$(date)\"" 'git commit -m "wip $(date)"'
check_silent "(sb2n11) negative: echo \"\$(git status)\"" 'echo "$(git status)"'
check_silent "(sb2n12) negative: echo \"\$(git log -1) # x\"" 'echo "$(git log -1) # x"'
check_silent "(sb2n13) negative: <<- quoted body inside \$(…), TAB before EOF" \
  "$(printf 'git commit -m "$(cat <<-%sEOF%s\nfix: x\n\tEOF\n)"' "'" "'")"
check_silent "(sb2n14) negative: the quoted text AROUND a substitution stays data" 'git commit -m "wip; git reset --hard $(date)"'
# (sb3) ÉTAPE 3 — les accolades non citées sont DÉVELOPPÉES avant l étage 2
# (liste `{a,b}`, séquence `{x..y[..n]}`), bornées à 256 mots par mot et 1024
# par commande ; au-delà, refus si le segment nomme git/rm/find/xargs ou si
# l accolade tient le mot de commande ou un mot qui le précède.
check_deny_msg "unscoped" "(sb3a) {git,reset,--hard}" '{git,reset,--hard}'
check_deny_msg "git branch -D" "(sb3b) {git,branch,-D} wt/T-1" '{git,branch,-D} wt/T-1'
check_deny_msg "unscoped" "(sb3c) sudo {git,} reset --hard" 'sudo {git,} reset --hard'
check_deny_msg "--output" "(sb3d) git diff --{output=AGENTS.md,}" 'git diff --{output=AGENTS.md,}'
check_deny_msg "unscoped" "(sb3e) C2a: a sequence, git reset --{h..h}ard" 'git reset --{h..h}ard'
check_deny_msg "git branch -D" "(sb3f) C2b: a sequence, git branch -{D..D} wt/T-1" 'git branch -{D..D} wt/T-1'
check_deny_msg "brace expansion in this command cannot be read" "(sb3g) C15: past the bound, the brace holds the command word" '{r{m,},{1..300}} -rf src'
check_deny_msg "unscoped" "(sb3j) git restore {.,}" 'git restore {.,}'
check_deny_msg "checkpoint" "(sb4c) {rm,-rf} src (T-01M53HV4)" '{rm,-rf} src'
check_silent "(sb3n) negative: echo {a,b}" 'echo {a,b}'
check_silent "(sb3n2) negative: ls {src,docs}" 'ls {src,docs}'
check_silent "(sb3n3) negative: git diff --{stat,}" 'git diff --{stat,}'
check_silent "(sb3n4) negative C7n: a QUOTED brace is not expanded" "echo 'a {x,y} b'"
check_silent "(sb3n5) negative: echo {1..300}, past the bound but nothing named" 'echo {1..300}'
check_silent "(sb3n6) negative: cp f{,.bak}" 'cp f{,.bak}'
check_silent "(sb3n7) negative: mkdir -p a/{b,c}" 'mkdir -p a/{b,c}'
check_silent "(sb3n8) negative: {ls,-la} src" '{ls,-la} src'
check_silent "(sb3n10) negative: braces are expanded on the EXECUTABLE text only, never inside quotes" 'git commit -m "a {x,y} ; git reset --hard ."'
# (sb4) ÉTAPE 4 — alias caché (git-subcommand-hidden), option de reset à
# expansion (--hard), `xargs` en tête lu.
check_deny_msg "git ALIAS is defined" "(sb4a) GIT_CONFIG_KEY_0=alias.bd before git" "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D' git bd wt/T-1"
check_deny_msg "git ALIAS is defined" "(sb4a2) C3a: git -c alias.bd=…" "git -c alias.bd='branch -D' bd wt/T-1"
check_deny_msg "git ALIAS is defined" "(sb4a3) C3b: git --config-env=alias.bd=V" 'git --config-env=alias.bd=V bd wt/T-1'
check_deny_msg "git ALIAS is defined" "(sb4a4) C3c: env GIT_CONFIG_KEY_0=alias.bd … git bd" "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D' git bd wt/T-1"
check_deny_msg "git ALIAS is defined" "(sb4a5) GIT_CONFIG_PARAMETERS carrying alias." "GIT_CONFIG_PARAMETERS=\"'alias.bd=branch -D'\" git bd wt/T-1"
check_deny_msg "exported by an EARLIER command" "(sb4a6) the export of an earlier segment is NAMED as a gap (C3d)" 'git -c alias.bd=x bd'
check_silent "(sb4a7) named gap C3d: an alias exported by an earlier segment is not read" "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D'; git bd wt/T-1"
check_deny_msg "unscoped" "(sb4b) git reset \$x: an expansion option may be --hard" 'git reset $x'
check_deny_msg "unscoped" "(sb4d) xargs git checkout --: operands from the pipe" 'xargs git checkout --'
check_deny_msg "unscoped" "(sb4d2) C10a: xargs -0 -r git checkout --" 'xargs -0 -r git checkout --'
check_deny_msg "git branch -D" "(sb4d3) C10b: a branch name fed by xargs counts as wt/" 'printf wt/T-1 | xargs git branch -D'
check_silent "(sb4n) negative: GIT_CONFIG_KEY_0=core.pager + git log" 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=cat git log'
check_silent "(sb4n2) negative: git reset --soft HEAD~1" 'git reset --soft HEAD~1'
check_silent "(sb4n3) negative: xargs git add" 'xargs git add'
check_silent "(sb4n4) negative: xargs -n 1 git status" 'xargs -n 1 git status'
check_silent "(sb4n5) negative: git reset HEAD~1" 'git reset HEAD~1'
check_silent "(sb4n6) negative: git reset --keep HEAD~1" 'git reset --keep HEAD~1'
check_silent "(sb4n7) negative: git reset -- src/a.py" 'git reset -- src/a.py'
check_silent "(sb4n8) negative: git reset -- \"\$f\"" 'git reset -- "$f"'
# (sb5) ÉTAPE 5 — sous find, une primaire décitée/décodée, ou un mot `-…` à
# expansion ou antislash, rouvre la commande ; `git stash #c` est un stash nu ;
# l ANSI-C (étape 1) et l expansion (étape 4) lisent `reset $'--hard'` et
# `reset --hard$x`.
check_deny_msg "pipe" "(sb5a) find . \$'-exec' rm -rf src {} +" "find . \$'-exec' rm -rf src {} +"
check_deny_msg "pipe" "(sb5b) find . -ex\${x}ec rm -rf src {} +" 'find . -ex${x}ec rm -rf src {} +'
check_deny_msg "pipe" "(sb5c) find . -\\exec rm -rf src {} +" 'find . -\exec rm -rf src {} +'
check_deny_msg "pipe" "(sb5c2) find . -e\\xec rm -rf src {} +" 'find . -e\xec rm -rf src {} +'
check_deny_msg "pipe" "(sb5c3) find . \"-exec\" rm -rf src {} +" 'find . "-exec" rm -rf src {} +'
check_deny_msg "unscoped" "(sb5d) git stash #c: the comment ends the words, a bare stash runs" 'git stash #c'
check_deny_msg "unscoped" "(sb5e) control: git stash push {x}>/dev/null" 'git stash push {x}>/dev/null'
check_deny_msg "unscoped" "(sb5f) git reset --hard\$x" 'git reset --hard$x'
check_deny_msg "unscoped" "(sb5g) git reset \$'--hard'" "git reset \$'--hard'"
check_deny_msg "unscoped" "(sb5g2) C8a: git reset \$'\\x2d\\x2dhard'" "git reset \$'\\x2d\\x2dhard'"
check_silent "(sb5n) negative: find . -name '*.o' -print" "find . -name '*.o' -print"
check_silent "(sb5n2) negative: git stash list" 'git stash list'
check_silent "(sb5n3) negative: git stash push -- src/a.py" 'git stash push -- src/a.py'
check_silent "(sb5n4) negative: git stash push -- src/x # note" 'git stash push -- src/x # note'
check_silent "(sb5n5) negative: find … -exec grep -l x {} +" "find . -name '*.o' -exec grep -l x {} +"
check_silent "(sb5n6) negative: only a word that may be -exec reopens the command (find . -name rm -print)" 'find . -name rm -print'
# (sb6) ÉTAPE 6 — le crédit de dry run de `git clean`, option par option.
check_deny_msg "unscoped" "(sb6a) --no-dry-run after -n wins" 'git clean -n --no-dry-run -fd'
check_deny_msg "unscoped" "(sb6b) -e at the end of a cluster takes -n as its value" 'git clean -fde -n'
check_deny_msg "unscoped" "(sb6c) -e\\ -n is ONE word: -n is the exclude pattern" 'git clean -fd -e\ -n'
check_deny_msg "unscoped" "(sb6d) -e \$x -n: an expansion value withdraws the credit" 'git clean -fd -e $x -n'
check_deny_msg "unscoped" "(sb6e) -?n: a glob may match a file -en" 'git clean -f -?n'
check_deny_msg "unscoped" "(sb6f) control: git clean -fd" 'git clean -fd'
check_deny_msg "option by option" "(sb6g) the clean refusal says how the dry run is credited" 'git clean -fd'
check_silent "(sb6n) negative: git clean -n" 'git clean -n'
check_silent "(sb6n2) negative: git clean -nd" 'git clean -nd'
check_silent "(sb6n3) negative: git clean -n -e build" 'git clean -n -e build'
check_silent "(sb6n4) negative: git clean -n -e '*.log'" "git clean -n -e '*.log'"
check_silent "(sb6n5) negative: git clean --dry-run -fd" 'git clean --dry-run -fd'
check_silent "(sb6n6) negative: git clean -fdn" 'git clean -fdn'

# =============================================================================
# (sc) PASSE DE CORRECTION de T-01M5D6XS2S (security-code-review S-01M5DN36WA,
# exec-critic NO_GO) : chaque arm rougit contre le livré 2a619291 et passe
# après son correctif ; la carte des mutants est en tête de safe-bash.test.sh.
# =============================================================================
sc_rep() { # sc_rep <motif> <n> — le motif répété n fois, sans shell de plus
  sc_r=""; sc_k=0
  while [ "$sc_k" -lt "$2" ]; do sc_r="$sc_r$1"; sc_k=$((sc_k + 1)); done
  printf '%s' "$sc_r"
}
# (sc1) F1 — l étage 1.5 ne rend JAMAIS la main à la posture dégradée : un mot
# trop grand, trop profond ou à nombre géant est ILLISIBLE, jamais une panne.
check_deny_msg "cannot be read" "(sc1a) {a,} x1000 then a reset: no COVERAGE DEGRADED" "$(sc_rep '{a,}' 1000) ; git reset --hard"
check_deny_msg "cannot be read" "(sc1b) {a, x1000 b } x1000 then a reset" "$(sc_rep '{a,' 1000)b$(sc_rep '}' 1000) ; git reset --hard"
check_deny_msg "cannot be read" "(sc1c) rm -rf {a,b} x1500" "rm -rf $(sc_rep '{a,b}' 1500)"
check_deny_msg "unscoped" "(sc1d) echo {a,b} x1500 ; git reset --hard: the reset is still read" "echo $(sc_rep '{a,b}' 1500) ; git reset --hard"
check_deny_msg "unscoped" "(sc1e) echo {1..<5000 digits>} ; git reset --hard" "echo {1..$(sc_rep 1 5000)} ; git reset --hard"
check_deny_msg "cannot be read" "(sc1f) rm -rf {1..<5000 digits>}" "rm -rf {1..$(sc_rep 9 5000)}"
# (sc2) F2 — un demi-codet UTF-16 en ANSI-C est INDÉCODABLE (opaque), jamais
# une panne de la table des segments.
check_deny_msg "unscoped" "(sc2a) echo \$'\\uD800' ; git reset --hard" "echo \$'\\uD800' ; git reset --hard"
check_deny_msg "unscoped" "(sc2b) echo \$'\\U0000DC80' ; git reset --hard" "echo \$'\\U0000DC80' ; git reset --hard"
check_deny_msg "unscoped" "(sc2c) rm \$'\\uD800' ; git reset --hard" "rm \$'\\uD800' ; git reset --hard"
check_silent "(sc2n) negative: echo \$'\\u00e9' decodes" "echo \$'\\u00e9'"
# (sc3) F3 — `${…}` et `$((…))` sont lus d un bloc : un `<<'EOF'` qui y vit
# n ouvre aucun corps (et un délimiteur cité qui porte `{`/`}` non plus).
check_deny_msg "unscoped" "(sc3a) \${y:-<<'EOF'} inside \"\$(…)\" opens no body" \
  "$(printf 'echo "$(echo ${y:-<<%sEOF%s}\ngit reset --hard\nEOF})"' "'" "'")"
check_deny_msg "unscoped" "(sc3b) same inside a backtick in \"…\"" \
  "$(printf 'echo "`echo ${y:-<<%sEOF%s}\ngit reset --hard\nEOF}`"' "'" "'")"
check_deny_msg "checkpoint" "(sc3c) same with rm -rf src" \
  "$(printf 'echo "$(echo ${y:-<<%sEOF%s}\nrm -rf src\nEOF})"' "'" "'")"
check_deny_msg "unscoped" "(sc3d) \$((1<<'E')) inside \"\$(…)\" opens no body" \
  "$(printf 'echo "$(echo $((1<<%sE%s))\ngit reset --hard\nE)"' "'" "'")"
check_deny_msg "unscoped" "(sc3e) \${y:-)} does not close the substitution early" 'echo "$(echo ${y:-)} ; git reset --hard)"'
# (sd1) N1 (2e passe) — dans un bloc `${…}`, une citation ANSI-C, une
# substitution ou un backtick (guillemets doubles compris) ARRÊTENT la lecture :
# tout ce qui suit est analysé.
check_deny_msg "unscoped" "(sd1a) \${x:-\$'\\''} then quoted braces: the reset is read" "echo \${x:-\$'\\''} ; echo 'q' ; echo '}' ; echo 'z' ; git reset --hard ; echo 'w'"
check_deny_msg "unscoped" "(sd1b) \${x:-\"\$(echo \"}\" ; reset)\"}" 'echo ${x:-"$(echo "}" ; git reset --hard ; echo "a")"}'
check_deny_msg "unscoped" "(sd1c) same with a backtick" 'echo ${x:-"`echo "}" ; git reset --hard ; echo "a"`"}'
check_silent "(sd1n) negative: echo \${HOME:-/tmp}" 'echo ${HOME:-/tmp}'
# (sc4) F4 — une accolade restée ouverte avant une substitution, un backtick ou
# une arithmétique (que bash garde DANS le mot) rend le mot illisible.
check_deny_msg "cannot be read" "(sc4a) {git,reset,--hard,\$(true)}" '{git,reset,--hard,$(true)}'
check_deny_msg "cannot be read" "(sc4b) {git,reset,--hard,\`true\`}" '{git,reset,--hard,`true`}'
check_deny_msg "cannot be read" "(sc4c) {rm,-rf,src,\$(true)}" '{rm,-rf,src,$(true)}'
check_deny_msg "cannot be read" "(sc4d) {git,reset,--hard,\$((1))}" '{git,reset,--hard,$((1))}'
check_deny_msg "cannot be read" "(sc4e) {git,reset,--hard,<(true)}" '{git,reset,--hard,<(true)}'
check_deny_msg "cannot be read" "(sc4f) {git,reset,--\$(echo hard)}" '{git,reset,--$(echo hard)}'
check_silent "(sc4n) negative: echo {a,\$(date)}, not the command word, nothing named" 'echo {a,$(date)}'
# (sc5) F5 — une enveloppe et ses options ne sont pas le mot de commande.
check_deny_msg "cannot be read" "(sc5a) env {r{m..m},-rf,{1..300}} src" 'env {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5b) command {r{m..m},-rf,{1..300}} src" 'command {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5c) nice -n 5 {r{m..m},-rf,{1..300}} src" 'nice -n 5 {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5d) time {r{m..m},-rf,{1..300}} src" 'time {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5e) sudo -u root {r{m..m},-rf,{1..300}} src" 'sudo -u root {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5f) exec {r{m..m},-rf,{1..300}} src" 'exec {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sc5g) nohup {r{m..m},-rf,{1..300}} src" 'nohup {r{m..m},-rf,{1..300}} src'
check_silent "(sc5n) negative: sudo echo {1..300}" 'sudo echo {1..300}'
# (sd5) 3e passe — un délimiteur de heredoc ouvert dans "$(…)" dont le mot porte
# autre chose que des pièces sûres (`<<$'EOF'`, `<<"E\$F"`, `<<"E\\F"`) n est pas
# modélisé : CHEMIN D ARRÊT, la commande qui suit est analysée.
check_deny_msg "unscoped" "(sd5a) t1: <<\$'EOF' inside \"\$(…)\"" \
  "$(printf 'echo "$(cat <<$%sEOF%s\nx\nEOF\necho hi)" ; git reset --hard ; echo "\n$EOF\n)"' "'" "'")"
check_deny_msg "checkpoint" "(sd5b) t1 with rm -rf src" \
  "$(printf 'echo "$(cat <<$%sEOF%s\nx\nEOF\necho hi)" ; rm -rf src ; echo "\n$EOF\n)"' "'" "'")"
check_deny_msg "unscoped" "(sd5c) v1: <<\"E\\\$F\"" \
  "$(printf 'echo "$(cat <<"E%s$F"\nx\nE$F\necho hi)" ; git reset --hard ; echo "\nE%s$F\n)"' '\' '\')"
check_deny_msg "git branch -D" "(sd5d) v1 with git branch -D wt/T-1" \
  "$(printf 'echo "$(cat <<"E%s$F"\nx\nE$F\necho hi)" ; git branch -D wt/T-1 ; echo "\nE%s$F\n)"' '\' '\')"
check_deny_msg "unscoped" "(sd5e) v4: <<\"E\\\\F\"" \
  "$(printf 'echo "$(cat <<"E%sF"\nx\nE%sF\necho hi)" ; git reset --hard ; echo "\nE%sF\n)"' '\\' '\' '\\')"
# (sd6) 3e passe point 2 — le mot de commande et une option de reset sont lus
# guillemets retirés (morceaux lisibles), comme sur les hôtes python.
check_deny_msg "checkpoint" "(sd6a) r\$'m' -rf src" "r\$'m' -rf src"
check_deny_msg "unscoped" "(sd6b) git reset --\$'hard'" "git reset --\$'hard'"
check_deny_msg "unscoped" "(sd6c) git reset '--hard'" "git reset '--hard'"
check_deny_msg "unscoped" "(sd6d) 'git' reset --hard" "'git' reset --hard"
check_deny_msg "checkpoint" "(sd6e) ''rm -rf src" "''rm -rf src"
check_silent "(sd6n) negative: git commit -m '--hard'" "git commit -m '--hard'"
check_silent "(sd6n2) negative: echo 'rm -rf'" "echo 'rm -rf'"
check_silent "(sd6n3) negative: git reset \"\$f\" (an expansion inside quotes is not read as --hard)" 'git reset "$f"'
# (sd7a) FAUX POSITIF ACCEPTÉ, côté sûr : le corps d un heredoc à délimiteur NU
# dans "$(…)" est analysé — bash n y exécute pas la ligne, la garde la refuse ;
# avec le délimiteur cité (`<<'EOF'`, (sb2n3)) le même corps passe.
check_deny_msg "unscoped" "(sd7a) ACCEPTED FALSE POSITIVE: a BARE heredoc body inside \"\$(…)\" is analysed" \
  "$(printf 'git commit -m "$(cat <<EOF\nfix: x\ngit reset --hard\nEOF\n)"')"
# (sd3) N3 (2e passe) — la table d enveloppes de l étage 2, la durée de
# timeout, les mots réservés, `env -S` et sa valeur.
check_deny_msg "cannot be read" "(sd3a) timeout 5 {r{m..m},-rf,{1..300}} src" 'timeout 5 {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sd3b) ! {r{m..m},-rf,{1..300}} src" '! {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sd3c) then {r{m..m},-rf,{1..300}} src" 'then {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sd3d) eval {r{m..m},-rf,{1..300}} src" 'eval {r{m..m},-rf,{1..300}} src'
check_deny_msg "cannot be read" "(sd3e) env -S x {r{m..m},-rf,{1..300}} src" 'env -S x {r{m..m},-rf,{1..300}} src'
check_silent "(sd3n) negative: timeout 5 echo {1..300}" 'timeout 5 echo {1..300}'
# (sd4) N3b — chrt, taskset, builtin sont des enveloppes pour l étage 2 et la
# passe rm/mv (un `rm` derrière elles passait dès bfa51a8f).
check_deny_msg "checkpoint" "(sd4a) chrt -i 0 rm -rf src" 'chrt -i 0 rm -rf src'
check_deny_msg "checkpoint" "(sd4b) taskset 1 rm -rf src" 'taskset 1 rm -rf src'
check_deny_msg "checkpoint" "(sd4c) builtin rm -rf src" 'builtin rm -rf src'
check_silent "(sd4n) negative: chrt -i 0 ls" 'chrt -i 0 ls'
# (sc8) F8 — l advisory du `)` de `case` dans "$(…)" est NOMMÉ au refus (pas
# fermé) : (sc8c) épingle le trou, il rougira le jour où il se ferme.
check_deny_msg 'the `)` of a `case` pattern ends the substitution early' "(sc8a) the wipe refusal names the case advisory" 'git reset --hard'
check_deny_msg 'the `)` of a `case` pattern inside a quoted' "(sc8b) the branch refusal names it too" 'git branch -D wt/T-1'
check_deny_msg 'the `)` of a `case` pattern inside a quoted' "(sc8b2) the rm refusal names it too" 'rm -rf src'
# (sc8c) sur DEUX lignes : la clause collée au `in` est une des huit formes que
# le parseur du SAST ne lit pas, et le filet la voit même dans une chaîne.
check_silent "(sc8c) NAMED GAP: a case ) inside \"\$(…)\" ends the substitution early" 'echo "$(case x in
x) git reset --hard;; esac)"'
# (sc7) F7 — l étage 1.5 est LINÉAIRE en la longueur du mot : 250 accolades
# ouvertes, chacune suivie de 30 000 caractères (7,5 Mo, charge construite par
# python : argv ne la porterait pas), sous un délai de 20 s ; le balayage
# depuis chaque `{` le dépassait (mesuré : x9 à 3 Mo). Et `echo {` x20000 en
# moins d une seconde (borne de 256 accolades par mot, F1).
"$PY" -c 'import json, os, signal, subprocess, sys, time
cmd = "echo " + ("{" + "a" * 30000) * 250
p = subprocess.Popen(["bash", sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
try:
    p.communicate(json.dumps({"tool_input": {"command": cmd}}).encode(), timeout=20)
    rc = p.returncode
except subprocess.TimeoutExpired:
    if hasattr(os, "killpg"):
        os.killpg(p.pid, signal.SIGKILL)
    else:
        p.kill()
    p.wait()
    rc = 99
sys.exit(0 if rc == 0 else 1)' "$HOOK"
assert $? "(sc7a) a 7.5 MB word with 250 open braces is read in bounded time, exit 0"
# (sc7c) borne RELATIVE (3e passe : une borne absolue rougissait sous une charge
# 1 min de 25) — le grand mot contre un contrôle chronométré dans le même run.
sc_big="echo $(sc_rep '{' 20000) ; git reset --hard"
sc_t0=$("$PY" -c 'import time; print(time.time())')
check_deny_msg "unscoped" "(sc7b0) control: echo x ; git reset --hard" "echo x ; git reset --hard"
sc_t1=$("$PY" -c 'import time; print(time.time())')
check_deny_msg "unscoped" "(sc7b) echo {x20000 ; git reset --hard" "$sc_big"
sc_t2=$("$PY" -c 'import time; print(time.time())')
"$PY" -c 'import sys; a, b, c = map(float, sys.argv[1:]); sys.exit(0 if c - b < 3 * (b - a) + 1 else 1)' "$sc_t0" "$sc_t1" "$sc_t2"
assert $? "(sc7c) echo {x20000 is judged in under 3x a plain command + 1 s (measured 0.3 s vs 0.3 s; 5.4 s at 2a619291)"
# (sc6) F6 — sous bash 3.2 une ligne `)` du corps cité referme `"$(` : la
# suite est analysée (C1a/C1b, sans ligne `)` avant EOF, restent des données).
check_deny_msg "unscoped" "(sc6a) a ) line in the quoted body ends the data (bash 3.2 closes there)" \
  "$(printf 'x="$(cat <<%sEOF%s\n)"\ngit reset --hard\nEOF\n)"' "'" "'")"
check_deny_msg "checkpoint" "(sc6b) same, blanks before the ), then rm -rf src" \
  "$(printf 'x="$(cat <<%sEOF%s\n  )"\nrm -rf src\nEOF\n)"' "'" "'")"
# (sd2) N2 (2e passe) — la ligne `)` du corps cité prend le CHEMIN D ARRÊT
# (jamais une reprise en code) : la suite, après EOF et `)"`, reste analysée.
check_deny_msg "unscoped" "(sd2a) fo1: ) line, EOF, then )\" ; reset" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\n)"\nEOF\n)" ; git reset --hard ; echo "x"' "'" "'")"
check_deny_msg "unscoped" "(sd2b) fo4: a realistic commit message holding a ) line" \
  "$(printf 'git commit -m "$(cat <<%sEOF%s\nfix: x\n)"\nmore\nEOF\n)"\ngit reset --hard\necho "y"' "'" "'")"
check_silent "(sc4n2) negative: a group { ls; }" '{ ls; }'
check_silent "(sc3n) negative: inside \"…\" an arithmetic is no substitution, the next line stays string" \
  "$(printf 'echo "$(( 1 <<%sE%s ))\ngit reset --hard\nE"' "'" "'")"

echo "----------------------------------------"
echo "safe-bash-t-y.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
