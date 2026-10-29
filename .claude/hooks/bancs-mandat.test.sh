#!/usr/bin/env bash
# Isolated witness for the closed BANCS grammar. Run: bash .claude/hooks/bancs-mandat.test.sh
# BANC_MANDAT_HOOK=<path> runs the same witness against another hook file.
# allows-missing: python python3 py
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${BANC_MANDAT_HOOK:-$HERE/bancs-mandat.sh}"
ROOT="$(mktemp -d)"
OUT="$(mktemp -d)"
trap 'rm -rf "$ROOT" "$OUT"' EXIT
mkdir -p "$ROOT/.claude/agents" "$ROOT/.claude/hooks" "$ROOT/t" "$ROOT/events"
mkdir -p "$ROOT/t/test_dir.py"
printf '%s\n' 'BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)' > "$ROOT/.claude/agents/gardee.md"
printf '%s\n' 'libre' > "$ROOT/.claude/agents/libre.md"
printf '%s\n' 'pass' > "$ROOT/t/test_a.py"
printf '%s\n' 'pass' > "$ROOT/t/b.test.sh"
printf '%s\n' 'note' > "$ROOT/t/notes.md"
# One native bench per family of the closed list, and its non-bench twin beside it.
mkdir -p "$ROOT/pkg" "$ROOT/src/test/java" "$ROOT/Api.Tests" "$ROOT/spec" "$ROOT/tests" "$ROOT/src/rs"
for f in pkg/foo_test.go pkg/foo.go src/test/java/FooTest.java src/test/java/FooTests.java src/test/java/FooIT.java \
  src/test/java/Foo.java src/test/java/FooTest.kt src/test/java/Foo.kt Api.Tests/UserServiceTests.cs Api.Tests/UserService.cs \
  spec/user_spec.rb spec/user.rb tests/integration.rs src/rs/lib.rs; do
  printf '%s\n' 'x' > "$ROOT/$f"
done
# The hook owns only the emitter interface; record its calls in this fixture.
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" >> "$AGENTS_EVENTS_DIR/calls"' > "$ROOT/.claude/hooks/emit-event.sh"
N=0
ENC=''
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
payload() {
  # Raw UTF-8 bytes, as the host sends them: an ASCII-escaped payload would hide the encoding cases.
  python3 -c 'import json,sys; sys.stdout.buffer.write(json.dumps({"tool_name":sys.argv[1],"tool_input":{sys.argv[2]:sys.argv[3],"prompt":sys.argv[4]}},ensure_ascii=False).encode("utf-8"))' "$1" "$2" "$3" "$4"
}
check() {
  local label="$1" expected="$2" input="$3" message="${4-}" remedy="${5-BANCS-SANS-BORNE:}" out rc
  set +e
  out="$(printf '%s' "$input" | PYTHONIOENCODING="$ENC" CLAUDE_PROJECT_DIR="$ROOT" AGENTS_EVENTS_DIR="$ROOT/events" bash "$HOOK" 2>&1)"
  rc=$?
  set -e
  LAST="$out"
  [ "$rc" -eq "$expected" ] || fail "$label: rc=$rc expected=$expected; $out"
  if [ -n "$message" ]; then
    [[ "$out" == *"$message"* ]] || fail "$label: expected $message; $out"
  fi
  if [ "$expected" -eq 2 ]; then
    [[ "$out" == *'BLOCKED by hook:'* ]] || fail "$label: missing refusal"
    [[ "$out" == *"$remedy"* ]] || fail "$label: missing exact remedy"
  fi
  if [ "$message" = 'cloture-ouverte' ]; then
    [[ "$out" != *'BANCS-SANS-BORNE:'* ]] || fail "$label: obsolete way-out in remedy; $out"
    [[ "${out#*$'\n'}" == 'referme la clôture' ]] || fail "$label: remedy is not the only remedy line; $out"
    [[ "$out" != *'???'* ]] || fail "$label: fence printed unreadable; $out"
  fi
  N=$((N + 1))
}
agent() { payload Agent subagent_type gardee "$1"; }
good='BANCS: t/test_a.py, t/b.test.sh::cas_x'

# Prose is irrelevant: all seventeen outside-sample phrases have both verdicts.
while IFS= read -r phrase; do
  check "prose avec liste: $phrase" 0 "$(agent "$phrase
$good")"
  check "prose sans liste: $phrase" 2 "$(agent "$phrase")"
done <<'PHRASES'
Do not run the whole suite: the gate does.
Never run every bench of .agents/evals.
Don't run the full test suite.
Ne lance pas tout banc qui lit X : la porte s'en charge.
La porte joue toute la suite apres la fusion.
Le dev a lance les bancs voisins et trouve 3 rouges la derniere fois.
Les bancs voisins ont trouve une regression hier.
tout banc qui utilise find doit epingler sa locale
Contexte : et tout banc qui lit ce fichier a ete corrige en T-12.
Joue aussi les bancs voisins.
Rejoue ensuite tous les bancs qui lisent kickoff.
Lance la suite complete avant de rendre.
Executez la suite entiere.
Make sure the whole suite passes.
Fais tourner les bancs freres.
Verifie que tous les bancs qui epinglent X restent verts.
Rejoue egalement tout banc qui lit planning/SKILL.md.
PHRASES

# Native bench names of the closed list pass; the source file beside each is refused.
for item in pkg/foo_test.go src/test/java/FooTest.java src/test/java/FooTests.java src/test/java/FooIT.java \
  src/test/java/FooTest.kt Api.Tests/UserServiceTests.cs spec/user_spec.rb tests/integration.rs 'pkg/foo_test.go::TestX'; do
  check "banc natif $item" 0 "$(agent "BANCS: $item")"
done
for item in pkg/foo.go src/test/java/Foo.java src/test/java/Foo.kt Api.Tests/UserService.cs spec/user.rb src/rs/lib.rs; do
  check "source native $item" 2 "$(agent "BANCS: $item")" 'pas-un-banc'
done
check 'aucun motivé' 0 "$(agent 'BANCS: aucun | relecture de doctrine')"
check 'sortie tracée' 0 "$(agent 'BANCS-SANS-BORNE: urgence pilote tracee')" 'SORTIE TRACÉE'
grep -qF 'hook.warn guard=bancs-mandat rule=sans-borne path=.claude/agents/gardee.md' "$ROOT/events/calls" || fail 'hook.warn absent'
# Annexe 2.4: a way-out line needs ten characters of reason, the first one decides.
check 'sortie courte + liste' 0 "$(agent 'BANCS-SANS-BORNE: court
BANCS: t/test_a.py')"
check 'sortie courte seule' 2 "$(agent 'BANCS-SANS-BORNE: court')" 'sans-liste'
check 'sortie doublée' 0 "$(agent 'BANCS-SANS-BORNE: urgence pilote tracee
BANCS-SANS-BORNE: seconde raison tracee')" 'SORTIE TRACÉE'
# A way-out next to a BANCS: line is ambiguous, in either order: a relayed line never switches the list off.
check 'sortie + liste ambigu' 2 "$(agent 'Rapport du dev:
BANCS-SANS-BORNE: relayé depuis un rapport de dev
BANCS: t/test_a.py')" 'ambigu'
check 'liste + sortie ambigu' 2 "$(agent 'BANCS: aucun | relecture de doctrine
BANCS-SANS-BORNE: urgence pilote tracee')" 'ambigu'
check 'raison gabarit why' 2 "$(agent 'BANCS: aucun | <why> recopie')" 'raison-gabarit'
# Lines split on \n alone: CRLF is read, a U+2028 separator does not open a line.
check 'fin de ligne CRLF' 0 "$(agent "intro$(printf '\r')
BANCS: t/test_a.py$(printf '\r')")"
check 'séparateur U+2028' 2 "$(agent "intro$(printf '\342\200\250')BANCS: t/test_a.py")" 'sans-liste'
# The payload is read as UTF-8 bytes, whatever the IO encoding of the interpreter.
# The messages leave as UTF-8 too: an escaped TRAC\xc9E or — would not match.
for ENC in ascii cp1252; do
  check "accent sans liste $ENC" 2 "$(agent 'Résumé Á sans liste')" 'sans-liste'
  check "accent avec liste $ENC" 0 "$(agent "Résumé Á
$good")"
  check "sortie tracée $ENC" 0 "$(agent 'BANCS-SANS-BORNE: urgence pilote tracee')" 'SORTIE TRACÉE — bancs-mandat'
  check "charge cassée $ENC" 0 '{broken' 'COVERAGE DEGRADED — bancs-mandat'
done
ENC=''
check 'def libre' 0 "$(payload Agent subagent_type libre 'aucune liste')"
check 'outil Task' 0 "$(payload Task subagent_type gardee "$good")"
for key in subagent_type agent_type subagentType agentType; do
  check "nom $key" 0 "$(payload Agent "$key" gardee "$good")"
done
check 'autre outil' 0 "$(payload Bash subagent_type gardee 'aucune liste')"
check 'charge cassée' 0 '{broken' 'COVERAGE DEGRADED'
check 'nom invalide' 0 "$(payload Agent subagent_type ../x 'aucune liste')"
# No def name under any of the four keys: the guard is inert and says so.
check 'nom absent' 0 "$(payload Agent description gardee 'aucune liste')" 'COVERAGE DEGRADED — bancs-mandat: aucun nom de def'
check 'ligne doublée' 2 "$(agent "BANCS: t/test_a.py
BANCS: t/b.test.sh")"
for item in 't/test_*.py' 't' 't/' 'voisins' 'tout banc qui lit X' '`t/test_a.py`' 't/notes.md' 't/test_absent.py' '../t/test_a.py' './t/test_a.py' 't//test_a.py' '/x/test_a.py' 't/test_a.py::$(x);rm' 't/test_a.py::test_*' 't/test_a.py::-k'; do
  check "item $item" 2 "$(agent "BANCS: $item")"
done
check 'chemin absolu existant' 2 "$(agent "BANCS: $ROOT/t/test_a.py")"
check 'répertoire nommé banc' 2 "$(agent 'BANCS: t/test_dir.py')" 'absent'
check 'raison gabarit aucun' 2 "$(agent 'BANCS: aucun | <pourquoi>')" 'raison-gabarit'
check 'raison gabarit sortie' 2 "$(agent 'BANCS-SANS-BORNE: <pourquoi> exemple')" 'raison-gabarit'
check 'sélecteurs pytest' 0 "$(agent 'BANCS: t/test_a.py::TestX::test_y[a-1]')"
check 'liste clôturée seule' 2 "$(agent '```
BANCS: t/test_a.py
```')"
check 'sortie clôturée seule' 2 "$(agent '```
BANCS-SANS-BORNE: urgence pilote tracee
```')"
check 'gabarit clôturé neutre' 0 "$(agent 'BANCS: t/test_a.py
```
BANCS: <chemin>[::<test>]
```')"
# p4: an excerpt list before an unclosed, indented diff hunk must not arm the mandate.
check 'p4 clôture ouverte dans un diff' 2 "$(agent 'BANCS: t/test_a.py
 ```sh
BANCS: t/b.test.sh')" 'cloture-ouverte' 'referme la clôture'
[ "${LAST%%$'\n'*}" = 'BLOCKED by hook: cloture-ouverte : ligne-2' ] || fail "p4: open fence not named by its line; $LAST"
grep -qF 'hook.deny guard=bancs-mandat rule=cloture-ouverte path=.claude/agents/gardee.md' "$ROOT/events/calls" || fail 'hook.deny cloture-ouverte absent'
# A fence indented by a tab opens a block too: leading blanks of any kind are stripped.
tab_fence="$(printf '\t')"'```sh'
check 'clôture ouverte indentée par tabulation' 2 "$(agent "BANCS: t/test_a.py
$tab_fence
BANCS: t/b.test.sh")" 'cloture-ouverte' 'referme la clôture'
nbsp_fence="$(printf '\302\240')"'```sh'
check 'clôture ouverte indentée par espace insécable' 2 "$(agent "BANCS: t/test_a.py
$nbsp_fence
BANCS: t/b.test.sh")" 'cloture-ouverte' 'referme la clôture'
check 'clôture ouverte avant liste' 2 "$(agent '```
BANCS: t/test_a.py')" 'cloture-ouverte' 'referme la clôture'
[ "${LAST%%$'\n'*}" = 'BLOCKED by hook: cloture-ouverte : ligne-1' ] || fail "avant liste: open fence not named by its line; $LAST"
check 'sortie précoce clôture ouverte' 2 "$(agent 'BANCS-SANS-BORNE: urgence pilote tracee
```sh
BANCS: t/test_a.py')" 'cloture-ouverte' 'referme la clôture'
check 'clôture refermée' 0 "$(agent '```sh
BANCS: t/b.test.sh
```
BANCS: t/test_a.py')"
# NON VU: two paired diff hunks can still hide the real list (residual rc 0).
check 'NON VU deux hunks appariés' 0 "$(agent 'BANCS: t/test_a.py
```sh
BANCS: t/b.test.sh
```sh')"
check 'deux hunks appariés, rien dehors' 2 "$(agent '```sh
BANCS: t/b.test.sh
```sh')" 'sans-liste'
# Several fences: the refusal names the LAST one left open, never the first.
check 'dernière clôture ouverte nommée' 2 "$(agent '```
x
```
BANCS: t/test_a.py
```sh')" 'cloture-ouverte' 'referme la clôture'
[ "${LAST%%$'\n'*}" = 'BLOCKED by hook: cloture-ouverte : ligne-5' ] || fail "plusieurs clôtures: last open fence not named; $LAST"
# ~~~ is a fence too: it hides a list, it is refused left open, and only ~~~ closes it.
check 'clôture tilde ouverte' 2 "$(agent 'BANCS: t/test_a.py
~~~
BANCS: t/b.test.sh')" 'cloture-ouverte' 'referme la clôture'
[ "${LAST%%$'\n'*}" = 'BLOCKED by hook: cloture-ouverte : ligne-2' ] || fail "tilde: open fence not named by its line; $LAST"
check 'liste dans un bloc tilde' 2 "$(agent '~~~
BANCS: t/test_a.py
~~~')" 'sans-liste'
check 'backticks dans un bloc tilde' 0 "$(agent '~~~
```
~~~
BANCS: t/test_a.py')"
check 'tilde dans un bloc backticks' 0 "$(agent '```
~~~
```
BANCS: t/test_a.py')"
# A bench that resolves outside the root, a link loop or a name too long is absent, never a crash.
printf '%s\n' 'pass' > "$OUT/test_out.py"
ln -s "$OUT/test_out.py" "$ROOT/t/test_lien.py"
ln -s test_boucle.py "$ROOT/t/test_boucle.py"
check 'lien sortant' 2 "$(agent 'BANCS: t/test_lien.py')" 'absent'
check 'lien en boucle' 2 "$(agent 'BANCS: t/test_boucle.py')" 'absent'
check 'segment trop long' 2 "$(agent "BANCS: t/$(python3 -c 'print("x" * 300)')/test_a.py")" 'absent'
# A reason is judged on its first 500 characters: a template past them is not seen (bound, said).
long="$(python3 -c 'print("a" * 600)')"
check 'gabarit après 500 sortie' 0 "$(agent "BANCS-SANS-BORNE: $long <pourquoi>")" 'SORTIE TRACÉE'
check 'gabarit après 500 aucun' 0 "$(agent "BANCS: aucun | $long <pourquoi>")"
# An interpreter that cannot even start on its stdin is a refusal (S-01M5YZ6VJN): rc 2,
# blocking bare and passed through by garde-fermee.
DENIES_AVANT="$(grep -c 'hook.deny' "$ROOT/events/calls" || true)"
set +e
out="$(CLAUDE_PROJECT_DIR="$ROOT" AGENTS_EVENTS_DIR="$ROOT/events" bash "$HOOK" < / 2>&1)"
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "stdin répertoire: rc=$rc expected=2; $out"
[[ "$out" == *'BLOCKED by hook: bancs-mandat: erreur interne'* ]] || fail "stdin répertoire: message absent; $out"
N=$((N + 1))
# No python 3 on the PATH: refusal rc 2, remedy named, no hook.deny (S-01M5YZ6VJN).
# PATH of links to /usr/bin and /bin with every python* left out.
NOPY="$OUT/nopy"
mkdir -p "$NOPY"
for f in /usr/bin/* /bin/*; do
  b="${f##*/}"
  case "$b" in
    python*|py) continue ;;
  esac
  [ -e "$NOPY/$b" ] || ln -s "$f" "$NOPY/$b"
done
BASH_ABS="$(command -v bash)"
agent 'BANCS: t/test_a.py' > "$OUT/charge-sans-python"
set +e
out="$(CLAUDE_PROJECT_DIR="$ROOT" AGENTS_EVENTS_DIR="$ROOT/events" PATH="$NOPY" "$BASH_ABS" "$HOOK" < "$OUT/charge-sans-python" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "python absent: rc=$rc expected=2; $out"
[[ "$out" == *'BLOCKED by hook: bancs-mandat: aucun interpréteur python, mandat non lu — refus (S-01M5YZ6VJN)'* ]] \
  || fail "python absent: message absent; $out"
[[ "$out" == *'installer python 3 (python3, python ou py -3)'* ]] || fail "python absent: remède absent; $out"
[ "$(grep -c 'hook.deny' "$ROOT/events/calls" || true)" = "$DENIES_AVANT" ] || fail 'python absent ou erreur interne: hook.deny émis'
N=$((N + 1))
grep -qF 'hook.deny guard=bancs-mandat' "$ROOT/events/calls" || fail 'hook.deny absent'
printf 'bancs-mandat: %s checks passed (%s)\n' "$N" "$HOOK"
