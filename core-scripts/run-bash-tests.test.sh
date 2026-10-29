#!/usr/bin/env bash
# Suite for core-scripts/run-bash-tests.sh — the aggregator itself (T-00000198).
#
# Auto-discovered by run-bash-tests.sh, so this file measures its own runner.
# Every case builds a FAKE tree under $TMP holding a copy of the real script at
# `<tree>/core-scripts/run-bash-tests.sh` — the script resolves its root as the parent
# of its own directory, so a copied script IS a complete, isolated fixture.
#
# What is under test is discovery, not aggregation: which *.test.sh the runner
# decides belong to the tree it was asked to verify. The defect that produced
# this suite was a stray `.worktrees/` checkout whose week-old copies were swept
# in, one of them failing against its own root and turning a green tree into
# `VERIFY FAILED — do not push`.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RUNNER="$ROOT/core-scripts/run-bash-tests.sh"
# The SERIAL path, on every machine (case 20) — the parallel path has its own bench.
export CADRE_GATE_JOBS=1
# A vanilla macOS / BSD box has no `timeout`; source the portable shim so the
# `timeout 60 …` guards below work there (the real `timeout` wins where present).
[ -f "$ROOT/.agents/bin/kit-portable.sh" ] && . "$ROOT/.agents/bin/kit-portable.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok()  { echo "  ok: $1"; passed=$((passed + 1)); }
ko()  { echo "  KO: $1"; failed=$((failed + 1)); }

# Build a fixture tree: a copy of the runner + whatever suites the caller adds.
# `$1` = tree name. Echoes the tree path.
make_tree() {
  local tree="$TMP/$1"
  mkdir -p "$tree/core-scripts"
  cp "$RUNNER" "$tree/core-scripts/run-bash-tests.sh"
  echo "$tree"
}

# A passing suite at $1, a failing one if $2 is "fail".
make_suite() {
  mkdir -p "$(dirname "$1")"
  if [ "${2:-pass}" = "fail" ]; then
    printf '#!/usr/bin/env bash\necho "fixture suite: deliberately red"\nexit 1\n' > "$1"
  else
    printf '#!/usr/bin/env bash\necho "fixture suite: green"\nexit 0\n' > "$1"
  fi
}

echo "=== 1. A SUITE OF THE TREE RUNS"
TREE="$(make_tree own)"
make_suite "$TREE/mine.test.sh" pass
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "green tree exits 0" || ko "green tree exited $RC"
grep -q "mine.test.sh" <<<"$OUT" && ok "the tree's own suite is discovered" \
  || ko "the tree's own suite was NOT discovered"

echo
echo "=== 2. A SUITE INSIDE A NESTED CHECKOUT DOES NOT RUN"
# THE DEFECT ITSELF. The nested suite is RED; if discovery still picks it up the
# whole run goes red, which is exactly the false verdict this case exists to ban.
TREE="$(make_tree nested)"
make_suite "$TREE/mine.test.sh" pass
mkdir -p "$TREE/.worktrees/stale/.git"           # `.git` as a DIRECTORY (a clone)
make_suite "$TREE/.worktrees/stale/foreign.test.sh" fail
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a red suite in a nested checkout does not fail this tree" \
  || ko "nested checkout still poisons the verdict (exit $RC)"
grep -q "=== RUN  ./.worktrees/stale/foreign.test.sh" <<<"$OUT" \
  && ko "the foreign suite was EXECUTED" \
  || ok "the foreign suite was not executed"

echo
echo "=== 3. THE SKIP IS ANNOUNCED, NEVER SILENT"
# A bound applied without a word reads as full coverage — the failure mode this
# repo treats as worse than the bound itself.
grep -q "Skipped 1 suite(s) belonging to a nested checkout" <<<"$OUT" \
  && ok "the skip is announced with its count" \
  || ko "the skip was SILENT — it reads as full coverage"
grep -q "foreign.test.sh" <<<"$OUT" \
  && ok "the skipped suite is named" || ko "the skipped suite is not named"
grep -q "nested checkout(s): ./.worktrees/stale" <<<"$OUT" \
  && ok "the nested checkout is named" || ko "the nested checkout is not named"

echo
echo "=== 4. A \`git worktree\` LINK IS A .git FILE, NOT A DIRECTORY"
# `git worktree add` writes a `.git` FILE holding a gitdir pointer. Matching only
# directories would let the most likely nested checkout of all straight through.
TREE="$(make_tree wtfile)"
make_suite "$TREE/mine.test.sh" pass
mkdir -p "$TREE/.worktrees/linked"
printf 'gitdir: /somewhere/.git/worktrees/linked\n' > "$TREE/.worktrees/linked/.git"
make_suite "$TREE/.worktrees/linked/foreign.test.sh" fail
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a .git FILE marks a nested checkout too" \
  || ko "a .git file was not recognised as a nested checkout (exit $RC)"

echo
echo "=== 5. THE EXCLUSION IS OWNERSHIP-BASED, NOT NAME-BASED"
# Excluding `.worktrees/` by name would pass case 2 and leave the class open.
# A manual clone parked anywhere must be excluded on the same rule.
TREE="$(make_tree anyname)"
make_suite "$TREE/mine.test.sh" pass
mkdir -p "$TREE/vendor/someclone/.git"
make_suite "$TREE/vendor/someclone/foreign.test.sh" fail
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a clone outside .worktrees/ is excluded on the same rule" \
  || ko "exclusion is name-based, not ownership-based (exit $RC)"

echo
echo "=== 6. NON-VACUITY — A RED SUITE OF THE TREE STILL FAILS"
# The whole fix narrows discovery. A narrowing that also swallowed real failures
# would be the perfect false green, so prove the runner is still able to go red.
TREE="$(make_tree stillred)"
make_suite "$TREE/mine.test.sh" fail
mkdir -p "$TREE/.worktrees/stale/.git"
make_suite "$TREE/.worktrees/stale/foreign.test.sh" pass
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -ne 0 ] && ok "a red suite OF THE TREE still fails the run" \
  || ko "PERFECT FALSE GREEN: a red suite of the tree passed"
grep -q "Bash test summary: 0 passed / 1 failed / 0 timed out (of 1)" <<<"$OUT" \
  && ok "the summary counts only the tree's own suites" \
  || ko "the summary count is wrong: $(grep 'Bash test summary' <<<"$OUT")"

echo
echo "=== 7. AN EMPTY PERIMETER PASSES, LOUDLY — NEVER SILENTLY"
# CE QUI A CHANGE LE 2026-09-14, ET CE QUI N A PAS CHANGE. Cette section
# exigeait un code retour NON NUL, avec ce motif : << an empty perimeter passing
# silently is the emptiest false green there is >>. L objection visait le
# SILENCE. Decision pilote : ce script VOYAGE (classe CONTRAT), et chez un
# adoptant sans suite bash il faisait rougir le tout premier verify.sh sur un
# depot sain. Le code retour devient 0 ; LE SILENCE RESTE INTERDIT, et les deux
# arms ci-dessous le prouvent ensemble — l un sans l autre laisserait passer
# exactement le faux vert que la redaction d avant combattait.
TREE="$(make_tree empty)"
mkdir -p "$TREE/.worktrees/stale/.git"
make_suite "$TREE/.worktrees/stale/foreign.test.sh" pass
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "un perimetre vide ne fait plus echouer la porte (exit 0)" \
  || ko "un perimetre vide rend encore $RC — l adoptant retrouve son rouge"
grep -q "COVERAGE DEGRADED" <<<"$OUT" \
  && ok "et il l ANNONCE — un exit 0 muet serait le faux vert d origine" \
  || ko "FAUX VERT MUET : exit 0 sans une ligne qui dit la couverture nulle"
# LA FIXTURE CI-DESSUS POSE UNE SUITE ETRANGERE, donc elle mesure le cas
# << tout est ecarte >>, PAS le cas << aucune suite >>. La premiere redaction de
# cet arm les confondait et CERTIFIAIT le silence sur le premier — releve du
# binome du 14/09. Les deux cas sont donc separes ci-dessous.
grep -q "TOUTES écartées comme étrangères" <<<"$OUT" \
  && ok "le cas TOUT-EST-ETRANGER est distingue du cas AUCUNE-SUITE" \
  || ko "FAUX VERT : l arbre porte des suites ecartees et l annonce dit l inverse"
grep -q "foreign.test.sh" <<<"$OUT" \
  && ok "et les suites ecartees sont NOMMEES, pas seulement comptees" \
  || ko "les suites ecartees ne sont pas nommees : on ne peut pas verifier la prune"

# LE CAS REELLEMENT VIDE, sur un arbre SANS aucun checkout imbriqué.
TREE="$(make_tree vraiment_vide)"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "un arbre VRAIMENT vide passe aussi (exit 0)" \
  || ko "un arbre vraiment vide rend $RC"
grep -q "ne prouve RIEN sur cet arbre" <<<"$OUT" \
  && ok "et son annonce nomme ce qui n est PAS prouve" \
  || ko "l annonce ne dit pas ce que le vert ne couvre pas"
grep -q "TOUTES écartées" <<<"$OUT" \
  && ko "CONFUSION : un arbre vide est annonce comme << tout est etranger >>" \
  || ok "et il n est PAS confondu avec le cas tout-est-etranger"

echo
echo "=== 8. A HUNG SUITE IS KILLED, NAMED, AND THE RUN STILL RETURNS (T-00000160)"
# The defect: 74 minutes of silence with live processes, twice in one night. The
# test therefore asserts the RUN ENDS — a case that hangs here fails the suite by
# its own timeout, which is the honest way to test a watchdog.
TREE="$(make_tree hang)"
make_suite "$TREE/quick.test.sh" pass
printf '#!/usr/bin/env bash\nsleep 120\n' > "$TREE/hangs.test.sh"
START=$SECONDS
OUT="$(cd "$TREE" && BASH_TEST_TIMEOUT=3 BASH_TEST_KILL_GRACE=2 \
       timeout 60 bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
ELAPSED=$((SECONDS - START))
[ "$RC" -ne 0 ] && [ "$RC" -ne 124 ] \
  && ok "the run returned a verdict instead of hanging (exit $RC, ${ELAPSED}s)" \
  || ko "the run did not return on its own (exit $RC, ${ELAPSED}s)"
grep -q -- "--- TIMEOUT ./hangs.test.sh" <<<"$OUT" \
  && ok "the hung suite is reported as TIMEOUT, not as a plain FAIL" \
  || ko "the hung suite was not named as a timeout"
grep -q "1 passed / 0 failed / 1 timed out" <<<"$OUT" \
  && ok "the summary counts the timeout in its own column" \
  || ko "wrong summary: $(grep 'Bash test summary' <<<"$OUT")"
grep -q "raise with BASH_TEST_TIMEOUT" <<<"$OUT" \
  && ok "the report says how to raise the limit" || ko "the limit is not actionable"
grep -q -- "--- PASS ./quick.test.sh" <<<"$OUT" \
  && ok "a hang in one suite does not stop the others" \
  || ko "the run stopped at the hung suite"

echo
echo "=== 9. THE WATCHDOG KILLS THE PROCESS TREE, NOT ONLY ITS CHILD"
# AGENTS.md's own lesson: stopping a task stops the process it LAUNCHED, not the
# tree below it. A watchdog that leaves grandchildren behind would let a hung
# semgrep keep a lock — the exact residue that doctrine was written about.
TREE="$(make_tree tree)"
# The grandchild must be findable in `ps` WITHOUT the marker also matching this
# script's own command line, so it is carried in argv[0] via `exec -a`.
MARK="rbtwatchdog$$"
printf '#!/usr/bin/env bash\nbash -c "exec -a %s sleep 120" &\nsleep 120\n' "$MARK" \
  > "$TREE/hangs.test.sh"
(cd "$TREE" && BASH_TEST_TIMEOUT=3 BASH_TEST_KILL_GRACE=2 \
   timeout 60 bash core-scripts/run-bash-tests.sh >/dev/null 2>&1) || true
sleep 3
SURV="$(ps -ef 2>/dev/null | grep "$MARK" | grep -v grep | wc -l)"
[ "$SURV" -eq 0 ] && ok "no grandchild survived the watchdog" \
  || ko "$SURV grandchild(ren) outlived the kill — the tree was not taken down"

echo
echo "=== 10. NO WATCHDOG IS ANNOUNCED, NEVER SILENT"
# A watchdog that vanishes without a word is indistinguishable from one that
# never had to fire. Exercised by naming a binary that cannot resolve — emptying
# PATH instead would take `find` and `sed` down with it and measure nothing but
# the runner's need for a PATH (tried first, exit 127, no line reached).
TREE="$(make_tree nowatchdog)"
make_suite "$TREE/mine.test.sh" pass
OUT="$(cd "$TREE" && BASH_TEST_TIMEOUT_BIN=no-such-timeout-binary \
       bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
grep -q "COVERAGE DEGRADED" <<<"$OUT" && ok "the missing watchdog is announced" \
  || ko "the missing watchdog was SILENT (exit $RC)"
grep -q "no-such-timeout-binary" <<<"$OUT" \
  && ok "the announcement names what is missing" || ko "the announcement is vague"
[ "$RC" -eq 0 ] && ok "a missing watchdog degrades, it does not block the run" \
  || ko "a missing watchdog blocked the run (exit $RC)"
grep -q -- "--- PASS ./mine.test.sh" <<<"$OUT" \
  && ok "suites still run without a watchdog" || ko "no suite ran"

echo
echo "=== 11. A SUITE UNDER THE LIMIT IS UNTOUCHED, AND ITS DURATION IS REPORTED"
TREE="$(make_tree fast)"
make_suite "$TREE/mine.test.sh" pass
OUT="$(cd "$TREE" && BASH_TEST_TIMEOUT=30 bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a quick suite is unaffected by the watchdog" \
  || ko "the watchdog broke a quick suite (exit $RC)"
grep -qE -- "--- PASS ./mine.test.sh \([0-9]+s\)" <<<"$OUT" \
  && ok "each suite reports its duration (which is what sizes the limit)" \
  || ko "no per-suite duration reported"

echo
echo "=== 12. THE DISCOVERY GLOB IS STILL LIVE"
# check-workflow-pins.test.sh § 10 asserts this same glob from the outside: it is
# the only reason any bash suite runs in CI. Asserted here too so a rewrite of
# the discovery block fails in its OWN suite, not only in a distant one.
LIVE="$(grep -v '^\s*#' "$RUNNER" || true)"
grep -q -- "-name '\*\.test\.sh'" <<<"$LIVE" \
  && ok "-name '*.test.sh' is present and uncommented" \
  || ko "the discovery glob is gone or commented — every bash suite is UNWIRED"

echo
echo "=== 13. node_modules IS PRUNED AT EVERY DEPTH, NOT ONLY THE ROOT (T-00000264)"
# A dependency tree carries no .git, so the ownership filter above cannot exclude
# it. A `*.test.sh` inside a NESTED node_modules (here under x/, not at the root)
# must not be discovered — root-only pruning, the old behaviour, would have swept
# it in. The interface gate's own `npm ci` under .agents/ui-src/ creates exactly
# such a tree. It is RED here, so a discovery leak turns the whole run red: the
# false red this case bans, mirror of case 2 for a dependency tree.
TREE="$(make_tree nodemods)"
make_suite "$TREE/mine.test.sh" pass
make_suite "$TREE/x/node_modules/somepkg/foreign.test.sh" fail
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a red suite inside a nested node_modules does not fail this tree" \
  || ko "a nested node_modules suite poisoned the verdict (exit $RC)"
grep -q "=== RUN  ./x/node_modules/somepkg/foreign.test.sh" <<<"$OUT" \
  && ko "the node_modules suite was EXECUTED" \
  || ok "the node_modules suite was not executed"
# Non-vacuity: pruning must not also swallow the tree's own suite.
grep -q -- "--- PASS ./mine.test.sh" <<<"$OUT" \
  && ok "the tree's own suite still runs (the exclusion is not over-broad)" \
  || ko "the tree's own suite was lost — exclusion too broad"

echo
echo "=== 14. A SWALLOWED 127 IS NO LONGER A PASS (T-00000427)"
# THE DEFECT ITSELF, reproduced in one gesture before it was fixed: a suite whose
# ONLY command does not exist printed `--- PASS ./mine.test.sh (0s)`,
# `1 passed / 0 failed`, `All bash suites passed.` and returned rc=0. `set -u`
# without `-e` absorbs the 127, and a runner that judged the rc alone saw green.
#
# The assertion is POSITIVE, on the MISSING DEP line itself. Cases 2 and 13 above
# are `&& ko || ok` shapes, which are true BY VACUITY when the output is empty; a
# case whose whole job is to prove a NEW line appears must assert it is THERE.
#
# Guarded on the sensor: `command_not_found_handle` arrived in bash 4.0 and macOS
# ships /bin/bash 3.2.57, so on that leg this case would false-RED. The skip is
# printed, which the runner itself now counts — the mechanism reports its own
# reduced coverage.
SENSOR=0
SENSOR_PROBE="$(mktemp)"
( RBT_MISSING_LOG="$SENSOR_PROBE"; export RBT_MISSING_LOG
  command_not_found_handle() { printf '%s\n' "$1" >>"$RBT_MISSING_LOG"; return 127; }
  export -f command_not_found_handle
  bash -c 'rbt-sensor-probe-t427' >/dev/null 2>&1 ) || true
[ -s "$SENSOR_PROBE" ] && SENSOR=1
rm -f "$SENSOR_PROBE"

if [ "$SENSOR" -eq 1 ]; then
  TREE="$(make_tree missingdep)"
  printf '#!/usr/bin/env bash\nno-such-cmd-t427 --x 2>/dev/null || true\nexit 0\n' \
    > "$TREE/mine.test.sh"
  OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
  grep -q -- "--- MISSING DEP ./mine.test.sh" <<<"$OUT" \
    && ok "a suite that RAN an absent command is reported MISSING DEP" \
    || ko "the swallowed 127 is still invisible: $(grep -- '--- ' <<<"$OUT")"
  grep -q "no-such-cmd-t427" <<<"$OUT" \
    && ok "the report NAMES the command that could not be resolved" \
    || ko "the missing command is not named"
  [ "$RC" -ne 0 ] && ok "a swallowed 127 turns the run RED (exit $RC)" \
    || ko "PERFECT FALSE GREEN: the run passed on an absent command (exit $RC)"
  grep -q -- "--- PASS ./mine.test.sh" <<<"$OUT" \
    && ko "the suite was ALSO counted as a pass" \
    || ok "it is not counted as a pass as well"
else
  echo "  SKIP: no command_not_found_handle on this bash (pre-4.0) — case 14 and"
  echo "        the case-19 non-vacuity cannot be exercised here."
fi

echo
echo "=== 15. AN AUTO-SKIP IS GREEN, BUT IT IS SAID AND COUNTED (T-00000427)"
# `command -v` is a BUILTIN: it NEVER reaches command_not_found_handle, so the
# sensor of case 14 is STRUCTURALLY blind to this one. MEASURED, and it is the
# whole reason two blindnesses get two mechanisms instead of one. This one is
# closed by READING the suite's captured output, which is plain text.
#
# THIS IS THE CASE THAT MAKES THE ORDERING PROMISE TRUE. 16 of this repo's 33
# suites announce a SKIP and every one of them used to be a bare PASS; without
# this case, closing K2 stays an intention.
TREE="$(make_tree autoskip)"
printf '#!/usr/bin/env bash\ncommand -v no-such-tool-t427 >/dev/null 2>&1 || { echo "SKIP: absent"; exit 0; }\necho "never reached"\n' \
  > "$TREE/mine.test.sh"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "an auto-SKIP stays GREEN — it is reduced coverage, not a failure" \
  || ko "an auto-SKIP was turned into a failure (exit $RC)"
grep -q -- "--- PASS ./mine.test.sh" <<<"$OUT" \
  && ok "it is still a PASS" || ko "it is no longer a PASS"
grep -q "1 SKIP annonc" <<<"$OUT" \
  && ok "the PASS is ANNOTATED with the SKIP the suite announced" \
  || ko "the SKIP is still invisible: $(grep -- '--- PASS' <<<"$OUT")"
grep -q "/ 1 skipping" <<<"$OUT" \
  && ok "the summary COUNTS it in a column of its own" \
  || ko "no skipping counter: $(grep 'Bash test summary' <<<"$OUT")"
grep -q "green, but NOT full coverage" <<<"$OUT" \
  && ok "the summary names the suite that did not fully run" \
  || ko "the skipping suite is not named"

echo
echo "=== 16. NON-VACUITY OF 15 — A SUITE THAT REALLY RAN IS A BARE PASS"
# A counter that fires on every suite says nothing at all. Same shape as 15 with a
# tool that EXISTS: nothing announced, nothing counted.
TREE="$(make_tree noskip)"
printf '#!/usr/bin/env bash\ncommand -v sed >/dev/null 2>&1 || { echo "SKIP: absent"; exit 0; }\necho "real work done"\n' \
  > "$TREE/mine.test.sh"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "the twin is green" || ko "the twin went red (exit $RC)"
grep -qE -- "--- PASS ./mine.test.sh \([0-9]+s\)$" <<<"$OUT" \
  && ok "a suite that really ran gets a BARE PASS, no annotation" \
  || ko "an annotation appeared on a suite with nothing to announce"
grep -q "/ 0 skipping" <<<"$OUT" \
  && ok "the skipping counter stays at zero" \
  || ko "the counter fires on everything: $(grep 'Bash test summary' <<<"$OUT")"

echo
echo "=== 17. NO SENSOR IS ANNOUNCED, AND THE SKIP SURVEY SURVIVES IT"
# Exercised portably by a `bash` shim that strips the exported function before
# exec'ing the REAL binary by absolute path — naming a nonexistent shell would
# measure nothing but the runner's need for a shell (the lesson of case 10), and
# an `env bash` shebang would re-resolve through PATH into the shim itself.
#
# The second half is the half that matters for a night of runs: the SKIP survey is
# PLAIN TEXT, so it must keep working exactly where the sensor cannot. A
# degradation that took the other mechanism down with it would put the macOS leg
# straight back to a bare PASS on all 16 skipping suites.
TREE="$(make_tree nosensor)"
printf '#!/usr/bin/env bash\ncommand -v no-such-tool-t427 >/dev/null 2>&1 || { echo "SKIP: absent"; exit 0; }\n' \
  > "$TREE/mine.test.sh"
REAL_BASH="$(command -v bash)"
mkdir -p "$TREE/fakebin"
printf '#!%s\nunset -f command_not_found_handle\nexec %s "$@"\n' "$REAL_BASH" "$REAL_BASH" \
  > "$TREE/fakebin/bash"
chmod +x "$TREE/fakebin/bash"
OUT="$(cd "$TREE" && PATH="$TREE/fakebin:$PATH" bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
grep -q "COVERAGE DEGRADED: swallowed-127 detection unavailable" <<<"$OUT" \
  && ok "a sensor that cannot work is ANNOUNCED, never silent" \
  || ko "the missing sensor was SILENT — it reads as full coverage"
[ "$RC" -eq 0 ] && ok "a missing sensor degrades, it does not block the run" \
  || ko "a missing sensor blocked the run (exit $RC)"
grep -q "1 SKIP annonc" <<<"$OUT" \
  && ok "the SKIP survey still works WITHOUT the sensor (plain text, bash 3.2 safe)" \
  || ko "the degradation took the SKIP survey down with it"
grep -q "/ 1 skipping" <<<"$OUT" \
  && ok "and it is still counted" || ko "the counter died with the sensor"

echo
echo "=== 18. A DECLARED DEPENDENCY IS JUDGED ONCE, BY THE RUNNER"
# `# requires:` answers the auto-SKIP that made a suite green without proving
# anything: a tool WITHOUT WHICH THE SUITE PROVES NOTHING is declared, and the
# runner declines to run it instead of watching it exit 0. `# optional:` is the
# other half of the same rule — a tool whose absence costs only PART of the proof
# stays green, announced and counted. Turning every scanner red for a missing
# gitleaks would not be the remedy; it would be another false verdict.
TREE="$(make_tree deps)"
printf '#!/usr/bin/env bash\n# requires: no-such-req-t427\necho "REQUIRED-BODY-RAN"\nexit 0\n' \
  > "$TREE/needs.test.sh"
printf '#!/usr/bin/env bash\n# optional: no-such-opt-t427\necho "OPTIONAL-BODY-RAN"\nexit 0\n' \
  > "$TREE/opt.test.sh"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -ne 0 ] && ok "a missing REQUIRED tool turns the run red (exit $RC)" \
  || ko "a suite that can prove nothing still passed (exit $RC)"
grep -q -- "--- MISSING DEP ./needs.test.sh" <<<"$OUT" \
  && ok "the required-tool suite is reported MISSING DEP" \
  || ko "the required tool was not judged"
grep -q "no-such-req-t427" <<<"$OUT" \
  && ok "the refusal NAMES the tool that is missing" || ko "the refusal is vague"
grep -q "REQUIRED-BODY-RAN" <<<"$OUT" \
  && ko "the suite was EXECUTED despite its missing requirement" \
  || ok "it was not run at all — no auto-SKIP left to misread"
grep -q -- "--- PASS ./opt.test.sh" <<<"$OUT" \
  && ok "a missing OPTIONAL tool stays green" \
  || ko "an optional tool was treated as required"
grep -q "optional absent: no-such-opt-t427" <<<"$OUT" \
  && ok "the missing optional tool is announced and named" \
  || ko "the optional absence was silent"
grep -q "OPTIONAL-BODY-RAN" <<<"$OUT" \
  && ok "non-vacuity: the optional suite's body DID run" \
  || ko "neither body ran — the absence assertion above is vacuous"

echo
echo "=== 19. A SUITE MAY DECLARE THAT IT RUNS AN ABSENT COMMAND ON PURPOSE"
# The valve for case 14, and it is not spare machinery: MEASURED on this repo the
# day it landed, FIVE suites legitimately execute a command that cannot resolve —
# three probe an interpreter by trying `python`/`python3`/`py` in turn, two strip
# PATH down to a stub to prove a script DEGRADES rather than blocks. Without the
# opt-out the sensor reds the whole gate on suites doing exactly their job, with
# no escape hatch, and every later run is blocked behind it until a human wakes up.
TREE="$(make_tree allowsmissing)"
printf '#!/usr/bin/env bash\n# allows-missing: no-such-cmd-t427\nno-such-cmd-t427 --x 2>/dev/null || true\nexit 0\n' \
  > "$TREE/mine.test.sh"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "a DECLARED absent command does not red the run" \
  || ko "the opt-out does not work — there is no escape hatch (exit $RC)"
grep -q -- "--- PASS ./mine.test.sh" <<<"$OUT" \
  && ok "the declaring suite is a PASS" || ko "the declaring suite is not a pass"
grep -q "MISSING DEP" <<<"$OUT" \
  && ko "MISSING DEP fired despite the declaration" \
  || ok "no MISSING DEP is reported"
# NON-VACUITY: the opt-out covers the DECLARED NAME, it does not disarm the sensor.
if [ "$SENSOR" -eq 1 ]; then
  printf '#!/usr/bin/env bash\n# allows-missing: some-other-cmd-t427\nno-such-cmd-t427 --x 2>/dev/null || true\nexit 0\n' \
    > "$TREE/mine.test.sh"
  OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
  [ "$RC" -ne 0 ] && ok "an UNDECLARED absent command still reds the run (exit $RC)" \
    || ko "the opt-out is a blanket: any declaration disarms the sensor"
  grep -q "no-such-cmd-t427" <<<"$OUT" \
    && ok "and the undeclared command is the one named" \
    || ko "the wrong command was named"
fi

echo
echo "=== --only <suite> (T-00001044) — ONE discovered suite, never an arbitrary script"
# A night dev checks ITS suite in headless, where the full run would blow the
# turn's timeout. Red on the old runner: it ignored its arguments and ran EVERY
# suite, so the red sibling below turned the run red.
TREE="$(make_tree only)"
make_suite "$TREE/a/mine.test.sh" pass
make_suite "$TREE/b/other.test.sh" fail
printf '#!/usr/bin/env bash\necho "arbitrary"\nexit 0\n' > "$TREE/arbitrary.sh"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --only a/mine.test.sh 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "--only a green suite exits 0 though a red sibling exists" \
  || ko "--only did not isolate the suite (exit $RC)"
grep -q -- "--- PASS ./a/mine.test.sh" <<<"$OUT" && ok "the selected suite ran and passed" \
  || ko "the selected suite did not run"
grep -q "other.test.sh" <<<"$OUT" && ko "the sibling suite was run or listed" \
  || ok "the sibling suite was neither run nor listed"
grep -q "(of 1)" <<<"$OUT" && ok "the summary counts ONE suite" || ko "the summary is not the single-suite one"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --only ./b/other.test.sh 2>&1)"; RC=$?
[ "$RC" -eq 1 ] && ok "--only a red suite exits 1 (./ form accepted)" || ko "--only red suite exited $RC"
for bad in arbitrary.sh nope.test.sh ../x.test.sh; do
  OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --only "$bad" 2>&1)"; RC=$?
  [ "$RC" -eq 2 ] && ok "--only $bad (not a discovered suite) is refused rc 2" \
    || ko "--only $bad exited $RC"
done
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --only 2>&1)"; RC=$?
[ "$RC" -eq 2 ] && ok "--only without a path is refused rc 2" || ko "--only without a path exited $RC"
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --bogus 2>&1)"; RC=$?
[ "$RC" -eq 2 ] && ok "an unknown argument is refused rc 2" || ko "an unknown argument exited $RC"
if [ "$SENSOR" -eq 1 ]; then
  printf '#!/usr/bin/env bash\nno-such-cmd-only-t1044 2>/dev/null || true\nexit 0\n' > "$TREE/a/mine.test.sh"
  OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh --only a/mine.test.sh 2>&1)"; RC=$?
  grep -q "MISSING DEP ./a/mine.test.sh" <<<"$OUT" && [ "$RC" -ne 0 ] \
    && ok "--only keeps the swallowed-127 sensor" || ko "--only lost the 127 sensor (exit $RC)"
fi

echo
echo "=== 20. THIS BENCH MEASURES THE SERIAL PATH ON EVERY MACHINE (binome 7+8, F8)"
# Without the pin at the top, every multi-suite case above ran the serial OR the parallel path depending
# on the machine's core count (auto = cores/2): what this bench proved was machine-dependent, and CI pins
# the serial form. The parallel path has its own bench (run-bash-tests-parallel.test.sh).
TREE="$(make_tree serialpin)"
make_suite "$TREE/a.test.sh" pass
make_suite "$TREE/b.test.sh" pass
OUT="$(cd "$TREE" && bash core-scripts/run-bash-tests.sh 2>&1)"; RC=$?
{ [ "$RC" -eq 0 ] && ! grep -q '^Parallel:' <<<"$OUT"; } \
  && ok "two suites, the bench's own environment: the SERIAL path ran (no Parallel: line)" \
  || ko "the nested runner took the PARALLEL path (exit $RC) — this bench's form depends on the machine"

echo
echo "================================================================"
echo "run-bash-tests: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Discovery: owns its tree, names what it skips, still able to go red."
echo "Judgement: a swallowed 127 is red, an auto-SKIP is green BUT said and counted."
