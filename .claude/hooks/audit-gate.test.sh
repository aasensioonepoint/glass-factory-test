#!/usr/bin/env bash
# Tests for audit-gate.sh (T-00000124 — le garde matchait par SOUS-CHAÎNE et
# refusait toute commande qui MENTIONNE une installation de skill).
# Style : safe-bash.test.sh / stop-reindex.test.sh — bash nu, lignes PASS/FAIL,
# sortie non nulle dès un échec. Chaque cas nourrit le hook avec la vraie forme
# JSON d'un PreToolUse sur stdin ; la charge utile est sérialisée par json.dumps,
# jamais par un printf de format — sinon un payload contenant des guillemets
# fabriquerait un JSON invalide et le test mesurerait le sérialiseur, pas le garde.
# Run: bash .claude/hooks/audit-gate.test.sh
#
# NON-VACUITÉ : `AUDIT_GATE_HOOK=<chemin> bash .claude/hooks/audit-gate.test.sh`
# lance la suite contre un autre exemplaire du garde. C'est ainsi que la mutation
# est prouvée — le mutant qui remet la sous-chaîne large fait rougir l'arm (a1) ;
# le mutant qui ramène l'étage 1 au sed AVEUGLE À L'ÉCHAPPEMENT (T-00000181, sa
# forme d'avant le port de `quoted_spans()`) fait rougir (i1)(i2), et eux seuls ;
# un scanner qui ignorerait tous les backslashes tombe sur (i3), un scanner
# REVENU au balayage LIGNE PAR LIGNE (l'état d'avant T-00000208) sur (i7) ; un
# étage 1 SANS frontière de commentaire — l'état d'avant le correctif du CRITICAL
# de la revue de classe 1, où une apostrophe de commentaire s'appariait avec un
# guillemet de CODE situé plus loin et blanchissait la ligne exécutée — sur (i8) ;
# et le correctif NAÏF qui coupe à tout `#` (donc à `$#` et `${#v}`, en
# élargissant `SEP`) sur (i9), que SEUL ce mutant-là tue. (i10) ne tue pas un
# mutant : il fixe la POLARITÉ choisie — la coupe n'efface pas, elle expose, donc
# un commentaire reste ANALYSÉ et son refus est un faux positif assumé.
# ET LE MUTANT QUE CETTE SUITE NE POUVAIT PAS TUER JUSQU'ICI — le garde SANS
# ÉTAGE 0.5, c'est-à-dire l'état d'avant le CRITICAL n°2 — tombe sur (j1) : cette
# suite n'avait AUCUNE occurrence de heredoc, donc son 63/63 vert ne mesurait
# RIEN sur cette classe et le fail-open a vécu sous un vert. Un compte de PASS ne
# prouve que ce qu'il énonce ; (j2) est sa non-vacuité (la même charge SANS
# heredoc), (j3)(j4) sa paire de polarité (corps cité = donnée <-> corps NU =
# analysé, sinon fail-open), (j5) l'anti-fail-open de la mention citée, (j6) le
# trou nommé qui subsiste, (j7)(j8) la panne annoncée de ce nouvel étage.
# ENFIN, le mutant qui lit le mot délimiteur avec une RE À UNE SEULE PIÈCE CITÉE
# au lieu du PARSEUR DE PIÈCES de bash (T-00000210) tombe sur (k1)(k2)(k3), les
# trois mesurées ROUGES contre l'état d'avant ; le corps qui ne se refermerait
# jamais sur la forme échappée sur (k4), le jeu de caractères non vérifié sur
# (k5), la frontière de mot TAIL retirée sur (k6). La POLARITÉ de l'étage reste
# tenue par (j4) : un corps à délimiteur NU reste ANALYSÉ, le blanchir serait
# fail-open.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${AUDIT_GATE_HOOK:-$HERE/audit-gate.sh}"
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "SKIP: audit-gate.test.sh needs python to build the payloads"; exit 0; fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/.agents/state/gates" "$TMP/events"
LOG="$TMP/.agents/state/gates/AUDIT_LOG"
# Le garde résout AUDIT_LOG et emit-event.sh sous cette racine : le vrai dépôt
# (board, journal d'événements) n'est jamais touché par la suite.
export CLAUDE_PROJECT_DIR="$TMP"
export AGENTS_EVENTS_DIR="$TMP/events"

PASS=0; FAIL=0
STDERR="$TMP/stderr"

# json_payload <command> — la forme PreToolUse réelle. La neutralisation MSYS est
# INLINE ici, sur ce SEUL appel python, jamais un export global (15 suites rouges
# mesurées) : les charges de chemin P1/P5/P11 COMMENCENT par `/`, et sans elle Git
# Bash réécrirait `/usr/local/bin/...` en chemin Windows AVANT que python ne
# sérialise le JSON — la suite mesurerait alors le traducteur d'argv, pas le garde.
json_payload() { MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$1"; }

# check <expected_exit> <label> <command-string>
check() {
  expected="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >/dev/null 2>"$STDERR"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$STDERR")>"
  fi
}

# check_deny_msg <label> <command-string> — REFUSÉ, ET POUR LA BONNE RAISON.
# Le code de sortie seul ne suffit pas (L-00000161) : un 2 peut venir d'un
# plantage du garde autant que de sa décision, et seul le message prouve que
# c'est bien le journal d'audit qui a parlé.
check_deny_msg() {
  label="$1"; cmd="$2"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >/dev/null 2>"$STDERR"
  got=$?
  case "$(cat "$STDERR")" in
    *"BLOCKED by audit gate"*)
      if [ "$got" -eq 2 ]; then PASS=$((PASS+1)); echo "PASS: $label"; return; fi;;
  esac
  FAIL=$((FAIL+1))
  echo "FAIL: $label (expected exit 2 carrying 'BLOCKED by audit gate', got $got) stderr=<$(tr '\n' ' ' < "$STDERR")>"
}

# check_silent <label> <command-string> — laissé passer ET sans un mot sur
# stderr. C'est l'assertion qui attrape la fragilité `xargs` : l'ancien garde
# rendait le ref à `xargs`, qui hurlait « unmatched double quote » sur une
# charge utile citée avant même de décider quoi que ce soit.
check_silent() {
  label="$1"; cmd="$2"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >/dev/null 2>"$STDERR"
  got=$?
  noise="$(tr -d '[:space:]' < "$STDERR")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and empty stderr, got $got) stderr=<$(tr '\n' ' ' < "$STDERR")>"
  fi
}

write_log() { printf '%s\n' "$@" > "$LOG"; }

# En-tête réel du journal (format documenté + lignes de commentaire) : le garde
# doit lire ce format sans se faire piéger par les `#`.
LOG_HEADER_1='# Skill / third-party reference audit log — one line per audited artefact.'
LOG_HEADER_2='# Format: <owner>/<repo>[#<skill>] audit=pass|fail pinned=<sha> date=<YYYY-MM-DD> note=<...>'

# =============================================================================
# (a) L'ARM DE REPRODUCTION, EN PREMIER — une commande qui PARLE de
#     l'installation n'est pas une installation. Mesuré en session le
#     2026-08-06 : l'écriture de board ci-dessous a été refusée.
# =============================================================================
rm -f "$LOG"
check 0 "(a1) REPRO tasks.py new whose title quotes the install command" \
  'python .agents/bin/tasks.py new "corriger le garde: npx skills add bloque une ecriture de board" --stage dev'
check 0 "(a2) ledger add quoting the install command in --text" \
  "python .agents/bin/ledger.py add --category lesson 'garde audit' --text 'npx skills add etait matche par sous-chaine'"
check 0 "(a3) git commit -m mentioning the install command" \
  'git commit -m "fix(hooks): npx skills add ne doit plus matcher par sous-chaine"'
check 0 "(a4) doc append mentioning the install command" \
  "printf '%s\\n' 'run npx skills add <ref> after the audit' >> docs/tech/skills.md"
check 0 "(a5) grep looking for the install command in the tree" \
  "rg -n 'npx skills add' .claude"
check 0 "(a6) install command mentioned mid-sentence, unquoted-but-not-a-command" \
  'echo please do not discuss skills add here'
check 0 "(a7) plain non-install command"                       'npm test'
check 0 "(a8) a word merely ending in npx is not npx"          'gonpx skills add owner/pkg'

# =============================================================================
# (b) UNE VRAIE INSTALLATION SANS `audit=pass` RESTE BLOQUÉE — raison d'être du
#     garde. Journal absent d'abord, puis présent mais sans la bonne ligne.
# =============================================================================
rm -f "$LOG"
check 2 "(b1) npx install, no AUDIT_LOG at all"                'npx skills add owner/pkg'
check 2 "(b2) npx install with options"                        'npx --yes skills add owner/pkg'
check 2 "(b3) npx.cmd install (Windows shim)"                  'npx.cmd --yes skills add owner/pkg'
check 2 "(b4) npm exec install"                                'npm exec skills add owner/pkg'
check 2 "(b5) pnpm dlx install"                                'pnpm dlx skills add owner/pkg'
check 2 "(b6) yarn dlx install"                                'yarn dlx skills add owner/pkg'
check 2 "(b7) bunx install"                                    'bunx skills add owner/pkg'
check 2 "(b8) globally-installed skills CLI at command position" 'skills add owner/pkg'
check 2 "(b9) install chained after &&"                        'cd /tmp && npx skills add owner/pkg'
check 2 "(b10) install chained after ;"                        'true ; npx skills add owner/pkg'
check 2 "(b11) install on a continuation line"                 'echo start
npx skills add owner/pkg'
check 2 "(b12) codex skill install"                            'codex skill install owner/pkg'
check 2 "(b13) gh skill install (two-token ref)"               'gh skill install owner/pkg myskill'
check 2 "(b14) uppercase runner still an install"              'NPX skills add owner/pkg'
write_log "$LOG_HEADER_1" "$LOG_HEADER_2" 'other/pkg audit=pass pinned=deadbeef date=2026-08-06'
check 2 "(b15) AUDIT_LOG holds a pass for a DIFFERENT ref"     'npx skills add owner/pkg'
write_log "$LOG_HEADER_1" 'notowner/pkg audit=pass pinned=deadbeef'
check 2 "(b16) prefix-extension row must not authorise owner/pkg" 'npx skills add owner/pkg'
write_log "$LOG_HEADER_1" '# owner/pkg audit=pass pinned=deadbeef'
check 2 "(b17) a commented-out row is not a pass"              'npx skills add owner/pkg'
write_log "$LOG_HEADER_1" 'owner/pkg audit=passing pinned=deadbeef'
check 2 "(b18) 'audit=passing' is not the field 'audit=pass'"  'npx skills add owner/pkg'

# =============================================================================
# (c) UNE VRAIE INSTALLATION AVEC `audit=pass` PASSE
# =============================================================================
write_log "$LOG_HEADER_1" "$LOG_HEADER_2" \
  'owner/pkg audit=pass pinned=283d5cbc5d11aac1abda058b16ad22c317d54dc0 date=2026-08-06 note=vendored;MIT'
check 0 "(c1) npx install with a matching audit=pass row"       'npx skills add owner/pkg'
check 0 "(c2) same, with a runner option"                       'npx --yes skills add owner/pkg'
check 0 "(c3) audited install chained before another command"    'npx skills add owner/pkg && echo done'
check 0 "(c4) audited install, trailing flag after the ref"      'npx skills add owner/pkg --force'
write_log "$LOG_HEADER_1" "$LOG_HEADER_2" \
  'vercel-labs/agent-skills#react-best-practices audit=pass pinned=7c180d9 date=2026-08-06 note=vendored'
check 0 "(c5) real-world '<owner>/<repo>#<skill>' ref"           'npx skills add vercel-labs/agent-skills#react-best-practices'
write_log "$LOG_HEADER_1" 'owner/pkg myskill audit=pass pinned=deadbeef'
check 0 "(c6) gh two-token ref matched field-by-field"           'gh skill install owner/pkg myskill'

# =============================================================================
# (p) T-00000240 — RUNNER OU CLI GLOBALE QUALIFIÉ PAR UN CHEMIN. Le trou mesuré :
#     `npx skills add x` refusé, mais `/usr/local/bin/npx`, `./node_modules/.bin/npx`
#     et SURTOUT `/usr/local/bin/skills add x` (la CLI globale derrière un chemin)
#     passaient — alors que safe-bash.sh traite déjà correctement `/bin/rm`. Deux
#     édits : `w` fait de `.`, `/`, `-` des frontières gauches des six motifs runner
#     (p1-p3, p7), et un préfixe de chemin `q` est admis devant l'ancre de la CLI
#     globale (p5, p6, p12). Le préfixe ne franchit ni espace ni séparateur, donc
#     les DEUX trous nommés étaient suivis par T-00000256, qui les FERME en
#     élargissant la POSITION DE COMMANDE : un chemin CITÉ (p8) réduit à ` @@ ` à
#     l'étage 1 est reconnu (`@@ add`/`@@ skills add`), un préfixe d'AFFECTATION
#     (p9) est admis entre l'ancre et la CLI. p11 reste ALLOW mais pour une AUTRE
#     raison — son ref est audité — et il est discriminé par p5 (même forme, ref
#     non audité, DENY). Le MOTIF est asserté sur les DENY (L-00000161). p13/p14
#     pinnent que l'élargissement reste ANCRÉ : hors position de commande, ni un
#     `@@` ni un `FOO=` ne déclenche quoi que ce soit.
# =============================================================================
write_log "$LOG_HEADER_1" "$LOG_HEADER_2" 'owner/pkg audit=pass pinned=deadbeef'
check_deny_msg "(p1) absolute-path npx is still the runner npx" \
  '/usr/local/bin/npx skills add other/pkg'
check_deny_msg "(p2) ./node_modules/.bin/npx — the natural JS form" \
  './node_modules/.bin/npx skills add other/pkg'
check_deny_msg "(p3) path-qualified pnpm dlx" \
  '/usr/bin/pnpm dlx skills add other/pkg'
check_deny_msg "(p4) backslash was ALREADY a boundary (no regression)" \
  'C:\tools\npx.cmd skills add other/pkg'
check_deny_msg "(p5) THE HOLE CLOSED: global CLI behind an absolute path" \
  '/usr/local/bin/skills add other/pkg'
check_deny_msg "(p6) global CLI behind a backslash path" \
  'C:\tools\skills.cmd add other/pkg'
check_deny_msg "(p7) my-npx: - is a left boundary, so this is the runner npx" \
  'my-npx skills add other/pkg'
check_deny_msg "(p12) a vertical tab is admitted inside the path prefix" \
  "$(printf 'a\vb/skills add other/pkg')"
check_deny_msg "(p8) HOLE CLOSED (T-00000256): a QUOTED path scrubs to @@ in command position" \
  '"/opt/tools/skills" add other/pkg'
check_deny_msg "(p9) HOLE CLOSED (T-00000256): an assignment prefix does not close command position" \
  'FOO=1 skills add other/pkg'
check_silent "(p11) path-qualified global CLI whose ref IS audited passes" \
  '/usr/local/bin/skills add owner/pkg'
# S3 (T-00000256) — the widening stays ANCHORED to the position of command.
check_silent "(p13) a quoted arg mid-line is NOT command position (echo \"hi\" skills add)" \
  'echo "hi" skills add x'
check_silent "(p14) an assignment mid-sentence opens no command position" \
  'we discuss FOO=1 skills add later'

# =============================================================================
# (d) CHARGES UTILES AVEC GUILLEMETS SIMPLES ET DOUBLES — le garde ne casse pas,
#     et ne dit RIEN (pas de `xargs: unmatched quote`).
# =============================================================================
rm -f "$LOG"
check_silent "(d1) both quote kinds around the install mention" \
  'python .agents/bin/tasks.py new "garde: '"'"'npx skills add'"'"' ne doit pas bloquer" --stage dev'
check_silent "(d2) unbalanced single quote (French apostrophe)" \
  "echo l'index parle de npx.cmd et c'est tout"
check_silent "(d3) nested quotes inside a python -c payload" \
  "python -c \"print('npx skills add owner/pkg')\""
check_silent "(d4) quotes plus shell metacharacters in the payload" \
  'python .agents/bin/ledger.py add --category constraint "audit gate: a mention (e.g. npx skills add x) is data; not an exec" --related T-00000124'
check_silent "(d5) empty command"                               ''
check_silent "(d6) command that is only quotes"                 '"" '"''"

# =============================================================================
# (e) `audit=fail-as-shipped` NE VAUT PAS UN PASS (vraie ligne du dépôt)
# =============================================================================
write_log "$LOG_HEADER_1" "$LOG_HEADER_2" \
  'owner/pkg audit=fail-as-shipped date=2026-08-06 note=39-line-stub-webfetches-its-rules-from-unpinned-main;NOT-installed'
check 2 "(e1) audit=fail-as-shipped does not authorise the install" 'npx skills add owner/pkg'
write_log "$LOG_HEADER_1" 'owner/pkg audit=fail pinned=deadbeef'
check 2 "(e2) audit=fail does not authorise the install"           'npx skills add owner/pkg'
write_log "$LOG_HEADER_1" 'owner/pkg audit=fail-as-shipped note=see-owner/pkg audit=pass-elsewhere'
check 2 "(e3) 'audit=pass' as part of a note field is not a verdict" 'npx skills add owner/pkg'

# =============================================================================
# (f) LIMITE DOCUMENTÉE, pas un oubli : neutraliser les segments cités est ce
#     qui fait passer (a), donc une installation VOLONTAIREMENT cachée dans une
#     chaîne (`bash -c "…"`) échappe au garde. Arm présent pour que ce trou soit
#     visible et change bruyamment s'il est un jour comblé.
# =============================================================================
rm -f "$LOG"
check 0 "(f1) KNOWN GAP: install hidden inside a quoted bash -c" \
  'bash -c "npx skills add owner/pkg"'

# =============================================================================
# (g) LE JOURNAL TEL QU'IL EXISTE VRAIMENT — CRLF (édité sous Windows), tabs,
#     indentation. Le garde compare des CHAMPS, donc rien de tout cela ne doit
#     transformer un pass en refus (ni l'inverse).
# =============================================================================
printf '%s\r\n%s\r\n' "$LOG_HEADER_1" 'owner/pkg audit=pass pinned=deadbeef' > "$LOG"
check 0 "(g1) CRLF AUDIT_LOG still reads as a pass"             'npx skills add owner/pkg'
printf '%s\n' "$LOG_HEADER_1" "$(printf 'owner/pkg\taudit=pass\tpinned=deadbeef')" > "$LOG"
check 0 "(g2) tab-separated row still reads as a pass"          'npx skills add owner/pkg'
printf '%s\n' "$LOG_HEADER_1" '   owner/pkg audit=pass pinned=deadbeef' > "$LOG"
check 0 "(g3) indented row still reads as a pass"               'npx skills add owner/pkg'
printf '%s\n\n%s\n' "$LOG_HEADER_1" 'other/pkg audit=pass' > "$LOG"
check 2 "(g4) blank lines never authorise anything"             'npx skills add owner/pkg'
printf 'owner/pkg audit=pass' > "$LOG"
check 0 "(g5) last row without a trailing newline still counts" 'npx skills add owner/pkg'

# =============================================================================
# (h) T-00000140 — LE GARDE NE DOIT PAS S'EFFACER EN SILENCE. Sans python, la
#     charge utile PreToolUse (du JSON) est illisible : le garde ne voit RIEN et
#     n'a plus rien à bloquer. Il ne DOIT pas bloquer (un garde absent qui
#     bloque fait boucler l'hôte) — mais un garde qui disparaît sans le dire se
#     lit comme un garde qui a vérifié. Python est simulé absent par des shims
#     en tête de PATH qui échouent au `--version` : sed/awk/cat restent
#     disponibles, donc c'est bien l'absence d'INTERPRÉTEUR qui est mesurée.
# =============================================================================
rm -f "$LOG"
STDOUT="$TMP/stdout"
STUB="$TMP/nopy"; mkdir -p "$STUB"
for c in python3 python py; do printf '#!/bin/sh\nexit 127\n' > "$STUB/$c"; chmod +x "$STUB/$c"; done

assert() { # assert <rc 0=ok> <label>
  if [ "$1" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $2"; else FAIL=$((FAIL+1)); echo "FAIL: $2"; fi
}

# La charge utile est construite AVANT, avec le vrai interpréteur : c'est le
# garde qu'on prive de python, pas le harnais.
DEG_PAYLOAD="$(json_payload 'npx skills add owner/pkg')"
printf '%s' "$DEG_PAYLOAD" | PATH="$STUB:$PATH" bash "$HOOK" >"$STDOUT" 2>"$STDERR"
DEG_RC=$?
DEG_OUT="$(cat "$STDOUT")"; DEG_ERR="$(cat "$STDERR")"
assert "$([ "$DEG_RC" -eq 0 ] && echo 0 || echo 1)" \
  "(h1) python absent => exit 0, never a block (got $DEG_RC)"
case "$DEG_ERR" in
  *"COVERAGE DEGRADED"*) assert 0 "(h2) python absent => COVERAGE DEGRADED on stderr";;
  *) assert 1 "(h2) python absent => COVERAGE DEGRADED on stderr (got: $DEG_ERR)";; esac
case "$DEG_OUT" in
  *"COVERAGE DEGRADED"*) assert 0 "(h3) python absent => COVERAGE DEGRADED in the systemMessage";;
  *) assert 1 "(h3) python absent => COVERAGE DEGRADED in the systemMessage (got: $DEG_OUT)";; esac
# Un hook qui rend du JSON cassé sur stdout est un hook dont l'hôte ignore la
# sortie — donc muet à nouveau. La validité du JSON fait partie de l'annonce.
printf '%s' "$DEG_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'systemMessage' in d" 2>/dev/null
assert $? "(h4) the degraded systemMessage is valid JSON carrying systemMessage"

# Python PRÉSENT mais charge utile illisible : même aveuglement, même annonce.
printf '%s' 'this is not json at all' | bash "$HOOK" >"$STDOUT" 2>"$STDERR"
BADJSON_RC=$?
BADJSON="$(cat "$STDERR")$(cat "$STDOUT")"
case "$BADJSON" in
  *"COVERAGE DEGRADED"*) assert "$([ "$BADJSON_RC" -eq 0 ] && echo 0 || echo 1)" \
    "(h5) unreadable JSON payload => exit 0 (got $BADJSON_RC) AND announced";;
  *) assert 1 "(h5) unreadable JSON payload => announced (got: $BADJSON)";; esac

# NON-VACUITÉ de (h2)/(h3)/(h5) : avec python présent et une charge utile
# lisible, la MÊME installation non auditée est BLOQUÉE et ne parle pas de
# dégradation. Sans cet arm, un garde qui crierait COVERAGE DEGRADED en
# permanence — ou qui ne bloquerait plus rien — passerait la suite.
printf '%s' "$DEG_PAYLOAD" | bash "$HOOK" >"$STDOUT" 2>"$STDERR"
OK_RC=$?
OK_ALL="$(cat "$STDERR")$(cat "$STDOUT")"
case "$OK_ALL" in
  *"COVERAGE DEGRADED"*) assert 1 "(h6) python present => NO degradation claim";;
  *) assert "$([ "$OK_RC" -eq 2 ] && echo 0 || echo 1)" \
       "(h6) python present => the same unaudited install is blocked (exit 2, got $OK_RC) and claims no degradation";; esac

# =============================================================================
# (i) T-00000181 — LE CONTOURNEMENT DE CLASSE 1 PAR GUILLEMET ÉCHAPPÉ.
#   L'étage 1 était un sed AVEUGLE À L'ÉCHAPPEMENT. Or `\"` est un guillemet
#   LITTÉRAL pour bash : dans (i1) le shell installe VRAIMENT le skill, mais le
#   sed lisait les deux guillemets échappés comme UN segment cité couvrant le
#   séparateur, le runner et le ref — l'étage 2 ne reconnaissait plus rien et un
#   artefact NON AUDITÉ passait la porte sans que l'AUDIT_LOG soit consulté.
#   Reproduit par la revue de sécurité de T-00000151, laissé ouvert et ÉPINGLÉ
#   dans .agents/evals/test_guard_decision_parity.py (les lignes DIVERGENCE 5),
#   fermé ici par le port de `quoted_spans()`. Le MESSAGE est asserté, pas
#   seulement le code de sortie (L-00000161).
# =============================================================================
rm -f "$LOG"
check_deny_msg "(i1) escaped DOUBLE quotes must not mask the install" \
  'echo \" && npx skills add other/pkg \"'
check_deny_msg "(i2) escaped SINGLE quotes, same bypass" \
  "echo \\' && npx skills add other/pkg \\'"
# (i3) LE CONTRÔLE, et il est ce qui interdit le correctif « ignorer les
# backslashes » : un nombre PAIR de `\` laisse le guillemet ouvrir un VRAI
# segment, donc ceci est bien une MENTION et le garde a raison de se taire.
check_silent "(i3) an EVEN backslash run leaves a genuine quoted segment" \
  'echo \\" && npx skills add other/pkg \\"'
# (i4) CET ARM ÉPINGLAIT UN FAUX POSITIF, et le flip est DÉRIVÉ de bash, pas
# d'un confort de suite (T-00000208). Charge : `echo "unterminated \"` ⏎ `npx
# skills add other/pkg "`. Le `\"` est un guillemet ÉCHAPPÉ à l'intérieur du
# segment double ouvert par le premier `"` : il ne le ferme pas. La chaîne
# CONTINUE donc par-dessus le retour à la ligne jusqu'au `"` final de la ligne 2,
# et le tout est UN SEUL argument d'`echo`. Bash n'installe RIEN ici. Le garde a
# donc raison de se taire ; exiger un DENY revenait à demander un refus sur une
# charge inoffensive. La direction inverse — les charges que bash EXÉCUTE
# vraiment — est mesurée par (i7), et c'est elle qui porte la non-régression.
check_silent "(i4) a double-quoted string CONTINUED across the newline is one echo argument" \
  'echo "unterminated \"
npx skills add other/pkg "'
# (i7) SONDE D'INVERSION MESURÉE — la charge que le balayage par ligne laissait
# passer, et la raison d'être de T-00000208. Bash ouvre un segment SIMPLE à la
# ligne 1 et le ferme à la ligne 2 (il enjambe le retour à la ligne) ; ce qui
# suit — l'installation — est donc du CODE NU, et la fin de ligne est un second
# segment cité. Le scanner par-ligne, lui, ne voyait de la ligne 2 que deux
# apostrophes orphelines, les appariait l'une à l'autre et neutralisait TOUT
# l'intervalle, installation comprise : ALLOW, fail-open, MESURÉ à exit 0 avant
# le correctif. C'est le mutant tueur du retour au par-ligne.
check_deny_msg "(i7) INVERSION: a quote pairing ACROSS the newline must not mask the install" \
  "$(printf "echo 'a\nb' && npx skills add other/pkg && echo 'x'")"
# (i8)-(i10) LA FRONTIÈRE DE COMMENTAIRE DE L'ÉTAGE 1 — le CRITICAL de la revue de
# sécurité de classe 1, et la non-régression qui l'épingle. Le correctif de (i7)
# fermait le fail-open du par-ligne et en OUVRAIT un autre, mesuré par exécution
# contre le hook et non par lecture : un `#` de commentaire portant une
# apostrophe non appariée s'appariait, dans le scan TEXTE ENTIER, avec un vrai
# guillemet situé PLUS LOIN, et blanchissait tout l'intervalle — Y COMPRIS la
# ligne de code suivante, celle que bash exécute. Bash, lui, n'ouvre jamais rien
# avec un guillemet de commentaire : le commentaire s'arrête à sa ligne physique.
#   HEAD (avant le passage au texte entier) -> exit 2, « BLOCKED by audit gate »
#   après le passage au texte entier         -> exit 0, ALLOW muet, et un skill
#                                               NON AUDITÉ s'installait
# (i8) EST LA CHARGE EXACTE DU CRITICAL, et elle tue le mutant « étage 1 sans
# frontière de commentaire », c'est-à-dire le retour à l'état d'avant ce
# correctif. C'est la jumelle de (n8) dans safe-bash.test.sh : les deux suites
# épinglent LA MÊME charge sur LE MÊME scanner dupliqué, donc une divergence
# entre les deux copies rougit d'un côté au moins.
check_deny_msg "(i8) COMMENT BOUNDARY: an apostrophe in a # comment must not mask a later install" \
  "$(printf "# don't run this\nnpx skills add other/pkg && echo 'ok'")"
# (i9) LE CONTRÔLE QUI INTERDIT LE CORRECTIF NAÏF — jumelle de (n10), et sa forme
# est DÉRIVÉE : `$#` et `${#v}` sont des EXPANSIONS, jamais un commentaire, donc
# la clause exige un DÉBUT DE MOT et exclut `$` et `{` de `SEP`. Sur-couper
# n'efface rien (le texte redescend intact, seul l'APPARIEMENT DES GUILLEMETS est
# interrompu), donc le seul dégât possible est un FAUX POSITIF, et c'est lui
# qu'on piège : le segment cité final est de la DONNÉE que bash n'installe pas,
# le garde doit se TAIRE. Si `$` ou `{` entraient dans `SEP`, l'apostrophe
# ouvrante ne serait plus appariée, l'installation citée redeviendrait du code
# aux yeux de l'étage 2, et le garde refuserait une charge inoffensive.
check_silent "(i9) CONTROL: \$# and \${#v} are expansions, never a comment start" \
  'echo $# ${#v} '"'"' ; npx skills add other/pkg'"'"''
# (i10) LE FAUX POSITIF ASSUMÉ, épinglé pour être MESURÉ et non découvert. La
# coupe n'EFFACE pas le commentaire : elle l'exclut seulement de l'appariement
# des guillemets, donc son texte redescend TEL QUEL à l'étage 2 et y est analysé.
# Une forme d'installation écrite dans un commentaire est donc REFUSÉE alors que
# bash ne l'exécute pas. Côté sûr et CHOISI : blanchir le commentaire collerait
# mieux à bash, mais ferait de cette clause une primitive d'EFFACEMENT, et une
# reconnaissance fautive effacerait alors du code. Fail-open contre faux
# positif : on prend le faux positif.
check_deny_msg "(i10) KNOWN FALSE POSITIVE: a comment is analysed, not blanked" \
  '# rappel : npx skills add other/pkg'


# =============================================================================
# (j) L'ÉTAGE 0.5 — UN CORPS DE HEREDOC À DÉLIMITEUR CITÉ EST DE LA DONNÉE
#     (T-00000208, revue de sécurité de classe 1, CRITICAL n°2). Cette suite
#     n'avait AUCUNE occurrence de heredoc avant cette section : le 63/63 vert
#     ne prouvait donc RIEN sur cette classe, et c'est exactement ce qui a permis
#     au trou de vivre sous un vert. Un compte de PASS ne mesure que ce qu'il
#     énonce.
#     LE DÉFAUT, MESURÉ PAR EXÉCUTION : ce garde passait de la commande brute au
#     balayage de guillemets TEXTE ENTIER sans aucun étage heredoc. L'apostrophe
#     de « it's », vivant dans un corps à délimiteur CITÉ — donnée 100 % littérale
#     que bash ne cite ni n'exécute — s'appariait avec le guillemet ouvrant de
#     `echo 'end'` et blanchissait tout l'intervalle, LIGNE D'INSTALLATION RÉELLE
#     COMPRISE. Mesure avant le correctif : exit 0, silencieux, AUDIT_LOG jamais
#     consulté. Après : exit 2 avec le motif du journal d'audit.
#     Les arms vont PAR PAIRES, chacune portant le fail-open que le retrait de sa
#     jumelle rouvrirait — même construction que (m1)-(m7) dans safe-bash.test.sh,
#     sur le MÊME étage dupliqué verbatim, donc une divergence entre les deux
#     copies rougit d'un côté au moins :
#       (j1) la charge du CRITICAL <-> (j2) la MÊME sans heredoc (non-vacuité :
#            sans elle, un garde qui refuserait tout ferait passer (j1))
#       (j3) le corps cité qui PARLE d'une installation est de la donnée
#            <-> (j4) le corps à délimiteur NU développe `$(…)`, donc il reste
#            ANALYSÉ — le blanchir serait fail-open
#       (j5) une mention CITÉE d'un heredoc n'ouvre aucun corps
#       (j6) le TROU NOMMÉ qui subsiste, épinglé pour être mesuré
# =============================================================================
rm -f "$LOG"
# (j1) LA CHARGE EXACTE DU CRITICAL n°2. Tue le mutant « audit-gate sans étage
# 0.5 », c'est-à-dire l'état d'avant ce correctif, et lui seul.
check_deny_msg "(j1) CRITICAL: an apostrophe in a QUOTED heredoc body must not mask a later install" \
  "$(printf 'cat <<%sEOF%s\nit%ss not code\nEOF\nnpx skills add other/pkg\necho %send%s' "'" "'" "'" "'" "'")"
# (j2) LE CONTRÔLE DE NON-VACUITÉ de (j1) : la même charge SANS le heredoc. Si
# (j1) passait au vert parce que le garde refuse désormais trop large, cet arm ne
# le dirait pas — mais son inverse, (j3), si. Les trois se lisent ensemble.
check_deny_msg "(j2) CONTROL: the same payload WITHOUT the heredoc stays denied" \
  "$(printf 'npx skills add other/pkg\necho %send%s' "'" "'")"
# (j3) LA RAISON D'ÊTRE DE L'ÉTAGE, et le faux positif qu'il supprime :
# `git commit -F - <<'EOF' … EOF` est l'idiome que ce dépôt prescrit pour ses
# messages de commit, et l'anglais est plein d'apostrophes. Le corps est de la
# DONNÉE : le garde doit se taire, y compris quand ce corps DÉCRIT l'installation.
check_silent "(j3) a QUOTED heredoc body describing the install is data, not an install" \
  "$(printf 'git commit -F - <<%sMSG%s\nfix(hooks): npx skills add n%setait plus garde\nMSG' "'" "'" "'")"
# (j4) LE FAIL-OPEN QUE (j3) POURRAIT ROUVRIR, et pourquoi l'étage ne retire QUE
# les corps à délimiteur CITÉ : avec un délimiteur NU le shell développe les
# substitutions de commande DANS le corps, donc l'installation s'exécute pour de
# bon. Le corps reste ANALYSÉ, et le garde refuse. Jumelle de (m3).
check_deny_msg "(j4) BARE delimiter: the command substitution in the body really runs" \
  "$(printf 'cat <<EOF > f\n$(npx skills add other/pkg)\nEOF')"
# (j5) ANTI-FAIL-OPEN : un ouvrant de heredoc qui vit DANS un segment cité est une
# MENTION, pas un ouvrant — sinon un texte qui PARLE de heredocs effacerait les
# lignes suivantes. La charge est multi-ligne à dessein : sans ligne suivante il
# n'y a rien à effacer et l'arm serait vacuous. Jumelle de (m4).
check_deny_msg "(j5) a QUOTED mention of a heredoc opener opens no body" \
  "$(printf 'echo "cat <<%sEOF%s"\nnpx skills add other/pkg' "'" "'")"
# (j6) LE TROU NOMMÉ QUI SUBSISTE, épinglé ICI pour que la suite ne revendique
# pas plus que le garde ne tient — jumelle exacte de (m7). Le corps à délimiteur
# NU n'est PAS blanchi, et il a raison de ne pas l'être (cf. (j4)) ; une
# apostrophe qui y vit peut donc encore s'apparier avec une apostrophe de code
# plus loin et neutraliser l'intervalle. ALLOW, mesuré, assumé — tenu par CET arm
# ET par la tâche board T-00000224, nommée par son id parce qu'un id se vérifie
# en une commande là où « versé au board » ne se vérifie pas.
# Le jour où ce trou se comble, cet arm rougit BRUYAMMENT et c'est ce qu'on lui
# demande.
check_silent "(j6) KNOWN GAP: an apostrophe in a BARE heredoc body pairs with a code apostrophe" \
  "$(printf 'cat <<EOF > f\ndon%st do this\nEOF\nnpx skills add other/pkg && echo %sx%s' "'" "'" "'")"
# (i5)-(i6) LA POSTURE DÉGRADÉE DU SCANNER. Même doctrine que (h1)-(h4), mais sur
# une panne DE L'ÉTAGE 1 et non sur l'absence d'interpréteur : si le scanner
# échoue, le garde n'a rien vu — il le DIT et sort 0. Jamais un exit 2 (un garde
# qui bloque quand son instrument casse bloque TOUS les appels Bash et fait
# boucler l'hôte), jamais un fail-open muet.
# LE SHIM EST SÉLECTIF, et c'est ce qui rend l'arm non vacuous : un python qui
# échouerait sur TOUT ferait retomber le garde sur le chemin (h) « pas de
# python », dont l'annonce est la même — l'arm mesurerait alors ce chemin-là.
# Ici seul le programme de l'étage 1 échoue (reconnu à son nom de fonction), la
# lecture JSON passe au vrai interpréteur, et le MOTIF est asserté pour prouver
# que c'est bien la panne du scrub qui est annoncée.
# LE DISCRIMINATEUR A DU ETRE RE-DERIVE (T-00000235) : il etait le NOM DE LA
# FONCTION scrub_spans, qui ne distingue plus rien depuis que l etage 0.5 porte
# la MEME fonction, recopiee verbatim pour son veto. Le shim tuait alors l etage
# 0.5, qui tourne AVANT, et (i5) mesurait sa panne a lui. La cle est desormais
# buf.append, present dans le seul programme de l etage 1. La panne de l etage
# 0.5 reste mesuree a part, par (j7)-(j8) : aucun chemin n est perdu.
SCRUBSTUB="$TMP/scrubfail"; mkdir -p "$SCRUBSTUB"
REAL_PY="$(command -v "$PY")"
for c in python3 python py; do
  cat > "$SCRUBSTUB/$c" <<EOSTUB
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *buf.append*) exit 9;;
esac
exec "$REAL_PY" "\$@"
EOSTUB
  chmod +x "$SCRUBSTUB/$c"
done
SCRUB_PAYLOAD="$(json_payload 'npx skills add other/pkg')"
printf '%s' "$SCRUB_PAYLOAD" | PATH="$SCRUBSTUB:$PATH" bash "$HOOK" >"$STDOUT" 2>"$STDERR"
SCRUB_RC=$?
SCRUB_OUT="$(cat "$STDOUT")"; SCRUB_ERR="$(cat "$STDERR")"
case "$SCRUB_ERR" in
  *"COVERAGE DEGRADED"*"quote scrub failed"*)
    assert "$([ "$SCRUB_RC" -eq 0 ] && echo 0 || echo 1)" \
      "(i5) scrub en panne => COVERAGE DEGRADED nommant le scrub, et exit 0 (got $SCRUB_RC)";;
  *) assert 1 "(i5) scrub en panne => COVERAGE DEGRADED nommant le scrub (got: $SCRUB_ERR)";;
esac
printf '%s' "$SCRUB_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'COVERAGE DEGRADED' in d['systemMessage']" 2>/dev/null
assert $? "(i6) scrub en panne => systemMessage JSON valide portant l'annonce"


# (j7)-(j8) LA POSTURE DÉGRADÉE DE L'ÉTAGE 0.5, strictement symétrique de
# (i5)-(i6). Un étage qui s'ajoute ajoute son mode de panne : si le scanner
# heredoc casse, le garde N'A PAS VU la commande — il le DIT et sort 0, jamais un
# exit 2 (un garde qui bloque quand son instrument casse bloque TOUS les appels
# Bash et fait boucler l'hôte), jamais un fail-open muet. Le shim est SÉLECTIF
# (reconnu au nom `heredoc_delimiter`, propre à cet étage) : la lecture JSON et l'étage 1
# passent au vrai interpréteur, sinon l'arm mesurerait le chemin (h) « pas de
# python », dont l'annonce est la même. Le MOTIF est asserté pour prouver que
# c'est bien la panne de CET étage qui est annoncée.
# LE MARQUEUR EST UN COUPLAGE ASSUMÉ AU CODE DU GARDE, et il a bougé une fois :
# `OPEN_RE` a disparu avec la RE que T-00000210 remplace par un parseur de
# pièces, donc le shim reconnaît désormais `heredoc_delimiter`. Un marqueur périmé
# ne rougit pas tout seul — il rend l'arm VACUOUS, le shim ne coupant plus rien —
# ce qui est exactement pourquoi il est nommé ici plutôt que laissé implicite.
HDSTUB="$TMP/hdfail"; mkdir -p "$HDSTUB"
HD_REAL_PY="$(command -v "$PY")"
for c in python3 python py; do
  cat > "$HDSTUB/$c" <<EOSTUB
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *heredoc_delimiter*) exit 9;;
esac
exec "$HD_REAL_PY" "\$@"
EOSTUB
  chmod +x "$HDSTUB/$c"
done
HD_PAYLOAD="$(json_payload 'npx skills add other/pkg')"
printf '%s' "$HD_PAYLOAD" | PATH="$HDSTUB:$PATH" bash "$HOOK" >"$STDOUT" 2>"$STDERR"
HD_RC=$?
HD_OUT="$(cat "$STDOUT")"; HD_ERR="$(cat "$STDERR")"
case "$HD_ERR" in
  *"COVERAGE DEGRADED"*"heredoc stage failed"*)
    assert "$([ "$HD_RC" -eq 0 ] && echo 0 || echo 1)" \
      "(j7) etage heredoc en panne => COVERAGE DEGRADED le nommant, et exit 0 (got $HD_RC)";;
  *) assert 1 "(j7) etage heredoc en panne => COVERAGE DEGRADED le nommant (got: $HD_ERR)";;
esac
printf '%s' "$HD_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'COVERAGE DEGRADED' in d['systemMessage']" 2>/dev/null
assert $? "(j8) etage heredoc en panne => systemMessage JSON valide portant l'annonce"

# (q13)-(q14) LA POSTURE DÉGRADÉE DE L'ÉTAGE 2 — ex-p13/p14, renommés par
# T-00000419 (homonymes de S3 :221-224) — le scan de FORME D'INSTALLATION
# (T-00000240), strict décalque de (i5)-(i6) et (j7)-(j8). Si awk ne COMPILE pas
# le motif (une classe non terminée sous une sémantique), le garde N'A PAS VU la
# commande : il le DIT et sort 0, jamais un exit 2 (un garde qui bloque quand son
# instrument casse bloque TOUS les appels Bash et fait boucler l'hôte), jamais un
# fail-open muet. À cet étage une sortie VIDE est le cas NORMAL, donc seul le
# STATUT DE SORTIE reste comme symptôme. Le shim est SÉLECTIF sur `RSTART`, présent
# dans le SEUL programme de l'étage 2 (`substr($0, RSTART + RLENGTH)`) et absent de
# celui de l'AUDIT_LOG : l'étage du journal continue de fonctionner, donc l'arm
# n'est pas vacuous. Le MOTIF est asserté pour prouver que c'est bien CETTE panne.
rm -f "$LOG"
write_log "$LOG_HEADER_1" 'owner/pkg audit=pass'
AWKSTUB="$TMP/awkfail"; mkdir -p "$AWKSTUB"
REAL_AWK="$(command -v awk)"
cat > "$AWKSTUB/awk" <<EOSTUB
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *RSTART*) exit 9;;
esac
exec "$REAL_AWK" "\$@"
EOSTUB
chmod +x "$AWKSTUB/awk"
AWK_PAYLOAD="$(json_payload 'npx skills add other/pkg')"
printf '%s' "$AWK_PAYLOAD" | PATH="$AWKSTUB:$PATH" bash "$HOOK" >"$STDOUT" 2>"$STDERR"
AWK_RC=$?
AWK_OUT="$(cat "$STDOUT")"; AWK_ERR="$(cat "$STDERR")"
case "$AWK_ERR" in
  *"COVERAGE DEGRADED"*"install-form scan failed"*)
    assert "$([ "$AWK_RC" -eq 0 ] && echo 0 || echo 1)" \
      "(q13) etage 2 en panne => COVERAGE DEGRADED le nommant, et exit 0 (got $AWK_RC)";;
  *) assert 1 "(q13) etage 2 en panne => COVERAGE DEGRADED le nommant (got: $AWK_ERR)";;
esac
printf '%s' "$AWK_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'COVERAGE DEGRADED' in d['systemMessage']" 2>/dev/null
assert $? "(q14) etage 2 en panne => systemMessage JSON valide portant l'annonce"

# =============================================================================
# (k) T-00000210 — LE MOT DÉLIMITEUR EST UNE CONCATÉNATION DE PIÈCES. Jumelle de
#     la section (r) de safe-bash.test.sh, sur le MÊME étage 0.5 dupliqué
#     VERBATIM dans les deux gardes : c'est la raison d'être de ces arms ici. Une
#     divergence entre les deux copies doit rougir d'AU MOINS un côté, et elle ne
#     le peut que si les deux suites épinglent la même classe sur leur propre
#     garde. (j1)-(j8) l'ont établi pour l'étage lui-même ; (k1)-(k6) l'étendent
#     à la reconnaissance du délimiteur.
#     LE DÉFAUT : la RE `<<-?[ \t]*('W'|"W")` n'admettait qu'UNE pièce,
#     entièrement citée. Bash concatène des pièces citées ET nues puis retire les
#     quotes — `<<\EOF` et `<<E"O"F` valent `EOF`, `<<'A'B` vaut `AB` — et dans
#     les trois cas une pièce au moins est citée, donc le corps est de la DONNÉE
#     littérale. Mesuré AVANT le correctif sur CE garde : (k1)(k2)(k3) sortaient
#     2, c'est-à-dire un message de commit refusé parce qu'il décrit une
#     installation de skill : (j3) par une autre porte.
#     LA POLARITÉ NE BOUGE PAS : le corps n'est blanchi que si AU MOINS UNE PIÈCE
#     EST CITÉE. Le corps à délimiteur NU reste ANALYSÉ, et (j4) le mesure —
#     c'est là que meurt le mutant qui blanchirait les corps nus, pas ici.
#     Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#       parseur ramené à la RE `('W'|"W")`                    -> (k1)(k2)(k3)
#       corps de la forme échappée qui ne se referme jamais    -> (k4)
#       jeu de caractères d'une pièce CITÉE non vérifié        -> (k5)
#       frontière de mot TAIL retirée après la dernière pièce  -> (k6)
#       `quoted` ignoré, corps NU blanchi                      -> (j4)
# =============================================================================
rm -f "$LOG"
# Les trois caractères passent par des VARIABLES, jamais en littéral dans le
# format de printf : `%s` n'interprète pas son argument, alors qu'un backslash
# écrit dans le format y serait une séquence d'échappement. Même précaution que
# la section (o) de safe-bash.test.sh.
KSQ="'"; KDQ='"'; KBS='\'
# (k1)(k2) LES DEUX FORMES DE L'INCIDENT, corps en position de COMMANDE.
check_silent "(k1) a backslash-quoted delimiter <<\\EOF makes its body literal data" \
  "$(printf 'git commit -F - <<%sEOF\nnpx skills add other/pkg\nEOF' "$KBS")"
check_silent "(k2) a partially quoted delimiter <<E\"O\"F makes its body literal data" \
  "$(printf 'git commit -F - <<E%sO%sF\nnpx skills add other/pkg\nEOF' "$KDQ" "$KDQ")"
# (k3) `<<'A'B` : bash attend `AB`. La ligne 4 prouve que la garde ne s'est pas
# tue pour une autre raison que le blanchiment du corps.
check_silent "(k3) <<'A'B closes on AB, and the body in between is data" \
  "$(printf 'cat <<%sA%sB\nnpx skills add other/pkg\nAB\necho ok' "$KSQ" "$KSQ")"
# (k4) LE CODE REPREND APRÈS LA CLÔTURE. Sans cet arm, un parseur qui reconnaît
# `<<\EOF` mais ne referme jamais son corps rendrait (k1) vert pour la mauvaise
# raison — le fail-open exact que (k1) pourrait masquer.
check_deny_msg "(k4) after the closing EOF of a <<\\EOF body, we are code again" \
  "$(printf 'git commit -F - <<%sEOF\ndata\nEOF\nnpx skills add other/pkg' "$KBS")"
# (k5)(k6) LE CÔTÉ D'ERREUR IMPOSÉ : toute non-reconnaissance laisse le corps
# ANALYSÉ. Ce sont des FAUX POSITIFS DÉLIBÉRÉS — bash tient ces corps pour de la
# donnée — assumés parce que le parseur est CLOS : il refuse plus qu'il n'admet,
# et son erreur se paie en ANALYSÉ, jamais en effacement.
check_deny_msg "(k5) a delimiter piece outside the closed charset leaves the body ANALYSED" \
  "$(printf 'cat <<%sE F%s\nnpx skills add other/pkg\nE F' "$KSQ" "$KSQ")"
check_deny_msg "(k6) a missing word boundary after the last piece leaves the body ANALYSED" \
  "$(printf 'cat <<%sA%s$x\nnpx skills add other/pkg\nA' "$KSQ" "$KSQ")"

# (s1)-(s5) L'ÉTAT DE CITATION INTER-LIGNES — T-00000235, le CRITICAL RACINE.
# Jumelles exactes des (s) de `safe-bash.test.sh`, sur l'autre garde et son autre
# motif. L'étage 0.5 décidait ouvreur / pas-ouvreur sur une ligne PHYSIQUE isolée,
# sans mémoire du fait que la ligne est déjà à l'intérieur d'un guillemet ouvert
# PLUS HAUT — état que seul le balayage TEXTE ENTIER de l'étage 1 connaît, et qui
# tourne APRÈS par construction. Il blanchissait donc jusqu'à la fin, effaçant le
# guillemet fermant RÉEL **et** l'installation non auditée qui le suit.
#   RELEVÉ DE PROPAGATION, et c'est ce qui rend ce fichier coupable plutôt que
#   victime : avant la nuit du 2026-08-18 ce garde n'avait AUCUN étage 0.5 et
#   était donc PROTÉGÉ (exit 2). T-00000208 y a porté l'étage verbatim — et le
#   trou avec. Mesuré le 2026-08-19 : exit 0, aucune sortie, ALLOW muet.
check_deny_msg "(s1) ROOT: a heredoc opener INSIDE a string opened on an EARLIER line must not blank the install" \
  "$(printf 'echo %sline1\ncat <<%sX%s\n%s && npx skills add other/pkg' "$KDQ" "$KSQ" "$KSQ" "$KDQ")"
# (s2) LE CONTRÔLE DE NON-VACUITÉ : sans lui, un garde qui refuserait TOUT
# rendrait (s1) vert sans rien mesurer.
check_deny_msg "(s2) NON-VACUITY of (s1): the bare install command is refused" \
  'npx skills add other/pkg'
# (s3) LE CONTRÔLE NÉGATIF ANTI-RÉGRESSION : un heredoc à délimiteur CITÉ, non
# précédé d'une quote ouverte, dont le corps DÉCRIT l'installation, reste de la
# DONNÉE. C'est l'incident FONDATEUR de l'étage 0.5 ; un veto qui sur-tire le
# refuserait et tuerait l'étage entier sans que (s1) s'en aperçoive.
check_silent "(s3) ANTI-REGRESSION: a legitimate quoted-delimiter body is still DATA" \
  "$(printf 'git commit -F - <<%sEOF%s\nnpx skills add other/pkg\nEOF' "$KSQ" "$KSQ")"
# (s4) LA MÊME CHARGE EN CRLF — le piège d'offsets. L'étage 0.5 retire le `\r` de
# CHAQUE ligne au stockage ; si les segments cités étaient calculés sur le texte
# D'ORIGINE et les candidats `<<` repérés sur le texte RECONSTRUIT, les offsets se
# décaleraient d'un caractère par ligne et le veto viserait à côté.
check_deny_msg "(s4) CRLF: the same payload with CRLF endings is refused too (offset alignment)" \
  "$(printf 'echo %sline1\r\ncat <<%sX%s\r\n%s && npx skills add other/pkg' "$KDQ" "$KSQ" "$KSQ" "$KDQ")"
# (s5) LE PRIX NOMMÉ DE LA TROISIÈME COPIE. Les étages 0.5 et 1 sont deux
# programmes python SÉPARÉS : `scrub_spans` est recopiée VERBATIM dans l'étage
# 0.5. Une duplication qu'un test surveille est une duplication ; une duplication
# que personne ne mesure est la prochaine divergence — c'est EXACTEMENT le
# mécanisme qui a produit (s1) ici, par copie fidèle d'un fichier déjà troué.
ag_copies=$(grep -c 'def scrub_spans(text):' "$HOOK")
ag_a="$(awk '/def scrub_spans\(text\):/{n++} n==1{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK")"
ag_b="$(awk '/def scrub_spans\(text\):/{n++} n>=2{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK")"
if [ "$ag_copies" -eq 2 ] && [ -n "$ag_a" ] && [ "$ag_a" = "$ag_b" ]; then
  PASS=$((PASS+1)); echo "PASS: (s5) the two scrub_spans copies (stage 0.5 and stage 1) are byte-identical"
else
  FAIL=$((FAIL+1)); echo "FAIL: (s5) scrub_spans copies differ or are not exactly 2 (found $ag_copies)"
fi

# --- (fb1)-(fb6) T-00000461: `skills_github_fallback.py install` gated in command
# position by its `gate` subcommand. NEW label prefix `fb` — (s1)-(s5) are TAKEN
# above by the inter-line quote-state arms (the plan's "(s1)-(s5) mirror of (g2)"
# collided with them). The fixture carries the fallback script + a policy under
# CLAUDE_PROJECT_DIR, and each arm STRIPS every agent marker of the fallback's own
# AGENT_CALLER_MARKERS tuple (read off its source, never a hand-kept copy) so the
# ONLY marker is the one the HOOK poses itself (AGENTS_HOOK_HOST=claude) — a run
# from Copilot CLI inherits COPILOT_CLI, which would otherwise refuse in its place.
mkdir -p "$TMP/.agents/bin" "$TMP/.agents/security"
cp "$HERE/../../.agents/bin/skills_github_fallback.py" "$TMP/.agents/bin/skills_github_fallback.py"
FB_UNSET=(-u AGENTS_HOOK_HOST)
FB_MARKERS=0
FB_BAD=0
# `tr -d '\r'`: a Windows python prints CRLF, and `env -u "COPILOT_CLI\r"` would unset
# nothing. A name that is not an environment variable name counts in FB_BAD, never in FB_UNSET.
while IFS= read -r fb_marker; do
  [ -n "$fb_marker" ] || continue
  if [[ "$fb_marker" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
    FB_UNSET+=(-u "$fb_marker"); FB_MARKERS=$((FB_MARKERS+1))
  else
    FB_BAD=$((FB_BAD+1))
  fi
done < <("$PY" -c 'import ast, sys
for n in ast.parse(open(sys.argv[1], encoding="utf-8").read()).body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "AGENT_CALLER_MARKERS" for t in n.targets):
        print("\n".join(ast.literal_eval(n.value)))' "$HERE/../../.agents/bin/skills_github_fallback.py" | tr -d '\r')
if [ "$FB_MARKERS" -eq 0 ] || [ "$FB_BAD" -ne 0 ]; then
  FAIL=$((FAIL+1)); echo "FAIL: (fb0) AGENT_CALLER_MARKERS unreadable in skills_github_fallback.py ($FB_MARKERS valid, $FB_BAD malformed)"
else
  PASS=$((PASS+1)); echo "PASS: (fb0) $FB_MARKERS agent markers read off AGENT_CALLER_MARKERS"
fi
FBPOL="$TMP/.agents/security/skills-fallback-policy.json"
fb_policy() {  # $1 = install_mode
  "$PY" -c "import json,sys; p=json.load(open(sys.argv[1])); p['install_mode']=sys.argv[2]; open(sys.argv[3],'w').write(json.dumps(p))" \
    "$HERE/../../.agents/security/skills-fallback-policy.json" "$1" "$FBPOL"
}
check_fb() {  # <expected_rc> <label> <command> <install_mode> [<needle>]
  local exp="$1" label="$2" cmd="$3" mode="$4" needle="${5:-}"
  fb_policy "$mode"
  printf '%s' "$(json_payload "$cmd")" \
    | env "${FB_UNSET[@]}" bash "$HOOK" >/dev/null 2>"$STDERR"
  local got=$?
  if [ "$got" -ne "$exp" ]; then FAIL=$((FAIL+1)); echo "FAIL: $label (rc $got != $exp)"; cat "$STDERR"; return; fi
  if [ -n "$needle" ] && ! grep -q "$needle" "$STDERR"; then
    FAIL=$((FAIL+1)); echo "FAIL: $label (stderr lacks '$needle')"; cat "$STDERR"; return
  fi
  PASS=$((PASS+1)); echo "PASS: $label"
}
SHA40="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
check_fb 2 "(fb1) confirm + no --confirmed-by => INSTALL REQUIRES CONFIRMATION" \
  "python .agents/bin/skills_github_fallback.py install o/r#s@$SHA40" confirm "INSTALL REQUIRES CONFIRMATION"
check_fb 2 "(fb2) confirm + no --confirmed-by => BLOCKED by audit gate" \
  "python .agents/bin/skills_github_fallback.py install o/r#s@$SHA40" confirm "BLOCKED by audit gate"
# (fb3) THE marker case (plan's (s6)): auto mode, so ONLY the hook-posed marker
# refuses --confirmed-by x. MUTATION: remove the AGENTS_HOOK_HOST assignment from
# the stage-2-bis call -> the gate sees no marker, accepts --confirmed-by x,
# rc 0 -> hook exit 0 -> (fb3) reddens. This is what .agents/hooks.json (Gemini +
# Antigravity, no marker passed) needs on the python twins (C10).
check_fb 2 "(fb3) auto + --confirmed-by x => CONFIRMATION REFUSED (marker posed by the hook)" \
  "python .agents/bin/skills_github_fallback.py install o/r#s@$SHA40 --confirmed-by x" auto "CONFIRMATION REFUSED"
check_fb 0 "(fb4) auto + no --confirmed-by => allowed" \
  "python .agents/bin/skills_github_fallback.py install o/r#s@$SHA40" auto ""
check_fb 0 "(fb5) search => allowed (no install)" \
  "python .agents/bin/skills_github_fallback.py search --stacks x" confirm ""
check_silent "(fb6) a QUOTED fallback-install mention is DATA, not gated" \
  "echo 'python .agents/bin/skills_github_fallback.py install o/r#s@$SHA40'"

# --- (t1192a)-(t1192d) T-00001192: the refusal names the kit appender, never a
# shell redirect — where AUDIT_LOG is git-tracked (the kit) safe-bash refuses a
# `>>` into it, so such a remedy could not be run, and elsewhere it skips the
# lock — nor an Edit/Write rewrite, and the bound the message states holds on
# the gate. AUDIT_LOG is rewritten for these arms: the documented header, no entry.
# MUTATIONS: the old `printf ... >> AUDIT_LOG` tail back at the refusal, the tail
# cut to `— then retry.`, the Edit/Write clause dropped from it, or the id
# re-quoted in it (`audit-log '<owner>/…'`) -> (t1192a) red; the awk field test
# comparing the FIRST field by PREFIX (`index($1, expect[1]) == 1`) instead of
# equality, run through AUDIT_GATE_HOOK -> (t1192c) red.
write_log "$LOG_HEADER_1" "$LOG_HEADER_2"
check_fb 2 "(t1192a) the refusal names the kit appender, not a shell redirect" \
  "npx skills add z1192/repo#sk" confirm "skills_github_fallback.py audit-log"
case "$(cat "$STDERR")" in
  *">>"*)
    FAIL=$((FAIL+1)); echo "FAIL: (t1192a) the refusal still prescribes a shell redirect (>>)";;
  *"nor an Edit/Write rewrite"*)
    : ;;
  *)
    FAIL=$((FAIL+1)); echo "FAIL: (t1192a) the refusal no longer bans an Edit/Write rewrite of AUDIT_LOG";;
esac
# The id goes UNQUOTED in the remedy, the same form the resolver defs prescribe:
# a quote around it, single or double, fails this positive pin.
case "$(cat "$STDERR")" in
  *"audit-log <owner>/<repo>#<skill>@<sha> --pass"*)
    : ;;
  *)
    FAIL=$((FAIL+1)); echo "FAIL: (t1192a) the refusal no longer prescribes the appender with the id UNQUOTED";;
esac
# (t1192b) the line the appender writes admits an install whose ref is exactly
# <owner>/<repo>#<skill> — the form the message says it covers. The id is QUOTED
# ON PURPOSE in this FILE: a bare mid-word `#` is valid bash, but semgrep's bash
# parser then drops the WHOLE file (PartialParsing l.40-800, measured, T-00001192)
# and the SAST reads none of it. The bare prescription of the defs is for the
# command line an agent runs, which the gate reads and the SAST never parses.
if "$PY" "$HERE/../../.agents/bin/skills_github_fallback.py" --root "$TMP" audit-log 'z1192/repo#sk@abcdef01' --pass >/dev/null 2>"$STDERR"; then
  check 0 "(t1192b) an appender line admits the exact <owner>/<repo>#<skill> install" \
    "npx skills add z1192/repo#sk"
else
  FAIL=$((FAIL+1)); echo "FAIL: (t1192b) the appender did not write (stderr=<$(tr '\n' ' ' < "$STDERR")>)"
fi
# (t1192c) the bound, held: the same line does NOT cover <owner>/<repo> --skill <x>.
check_deny_msg "(t1192c) an appender line does not cover the --skill form (the stated bound)" \
  "npx skills add z1192/repo --skill sk"
# (t1192d) the fact the resolver defs state — `the gate reads a quoted id as @@
# and the hook refuses the command` — held on the gate (rc 2 below is the code of
# the `gate` subcommand, which the Claude hook relays): in AUTO mode (so confirm
# is not the cause) a QUOTED install id reaches the `gate` subcommand as `@@` and
# is refused, where (fb4) admits the same id bare. If the gate ever reads a quoted
# id right, this arm goes red and the UNQUOTED sentence of the defs is to be revisited.
check_fb 2 "(t1192d) a QUOTED fallback-install id is read as @@ and refused (auto mode)" \
  "python .agents/bin/skills_github_fallback.py install 'o/r#s@$SHA40'" auto "got '@@'"

echo "----------------------------------------"
echo "audit-gate.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
