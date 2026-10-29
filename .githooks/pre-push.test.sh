#!/usr/bin/env bash
# Tests for .githooks/pre-push. Run: bash .githooks/pre-push.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# requires: git
#
# REQUIRED, not auto-skipped: every arm below drives a REAL `git push` through a
# REAL installed hook, into a bare repository built for the occasion. Without git
# this suite establishes exactly nothing, and announcing that with `exit 0` would
# have the runner count it as a pass — the same defect core-scripts/verify.test.sh had.
#
# WHY THIS SUITE TRAVELS while core-scripts/cadre.test.sh does not (`.template-exclude`
# spells the general rule: A BENCH TRAVELS NO FURTHER THAN ITS SUBJECT). Its
# subject is `.githooks/pre-push`, which travels; and it asserts nothing that
# belongs to the adopting project — it BUILDS its own bare repo and clone, copies
# the hook into them, and fabricates every stamp it reads. Ten of the nineteen arms
# are self-contained that way. The eleventh reads this repository's index, and it
# reads a path that travels too.
#
# THE PROOF IS FABRICATED, NEVER ASSUMED (L-00000337): the hook is COPIED into the
# fixture and wired with the exact gesture we document (`core.hooksPath .githooks`),
# so a green here means the documented gesture works, not that a hook file exists.
#
# WHAT THIS SUITE CANNOT SEE, NAMED HERE RATHER THAN LEFT AS A HOLE. Every stamp
# below is fabricated by the `stamp()` helper twenty lines down, so NOT ONE arm in
# this file ever reads a stamp that `verify.sh`'s own `stamp_write` produced. A
# field renamed there, a line reordered, a trailing \r — and this suite would stay
# green at 19/19 while the installed hook refused every push in the repository. A
# mechanism whose return channel is never exercised END TO END does not exist
# (L-00000136); citing that lesson in the skill this work delivers while leaving
# its own bench open at both ends would be the same defect one level up.
# THE CHANNEL IS CLOSED IN THE SUITE THAT OWNS THE WRITER: `core-scripts/verify.test.sh`
# arm 14 has a real green `--at` run write a REAL stamp, then hands it to THIS hook
# (copied, installed by the same documented gesture) and asserts the push is
# ALLOWED.
#
# SO READ THIS BEFORE ADDING A FIELD TO THE VALIDATION BELOW. Teaching the hook to
# REQUIRE a new field and updating `stamp()` to fabricate it is one self-consistent
# edit that keeps this file at 19/19 — and MEASURED, it takes `core-scripts/verify.test.sh`
# arm 14 to `FAIL: 14a: THE CHANNEL IS BROKEN`, because `stamp_write` was never
# taught to emit it. That red is the mechanism working, not a flaky bench: change
# `stamp_write` in `core-scripts/verify.sh` in the SAME edit, or do not change the
# validation. (Renaming an EXISTING field is caught earlier, by arm 11a there.)
#
# Every arm names the MUTATION that turns it red (L-00000343): a guard whose
# negative control is not written down is a guard nobody can trust later.
#
# Synchronous throughout — no backgrounded process and no `pgrep` polling
# (L-00000336): `git push` returns when the hook has returned.
#
# THE BENCH BUILDS THE ENVIRONMENT OF WHAT IT LAUNCHES — INHERITED VARIABLE AND
# DEFAULT BRANCH INCLUDED — IT NEVER INHERITS IT.
#
# Third failure of that exact shape on this lot, so it is written down as a bound
# rather than fixed in silence: the bench was measuring something OTHER than what
# it believed, because its environment was not the one it assumed. Here the
# assumption was THE DEFAULT BRANCH NAME. RÉÉCRIT LE 2026-09-14 (T-00000595) :
# les arms de TAMPON poussent désormais `travail`, et les arms 13-19 visent la
# branche PAR DÉFAUT à dessein, parce que `pre-push` y porte une SECONDE règle.
# Le montage `main` ci-dessous reste donc nécessaire — c'est la cible de 13-19.
# La rédaction d'avant disait « ten sites below say `main` — eight
# `push origin main`, plus one `grep refs/heads/main` in arm 2 and one
# `rev-parse refs/heads/main` in arm 4 — and not one of them created it. `git init`
# names the initial branch from `init.defaultBranch`, which is a property of THE
# HOST: `main` on a developer's box configured years ago, `master` on a bare
# `python:3.14-slim` container with git installed on the fly, which is what the
# gate runs. MEASURED red under the gate, and reproduced on the host with
# `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=init.defaultBranch GIT_CONFIG_VALUE_0=master`:
#   FAIL: 1: no diagnostic naming the missing stamp: error: src refspec main does
#   not match any
# Note WHICH assertion caught it, because it is the one arm 1's own comment calls
# the decorative-looking one: the push failed for a reason that had nothing to do
# with the hook, so `PUSH_RC -ne 0` passed VACUOUSLY and only the diagnostic
# assertion noticed. A bench can be red for the right verdict and the wrong reason.
#
# THE RULE IS NOT NEW IN THIS REPOSITORY, ONLY NEW HERE: `core-scripts/run-bash-tests.sh`
# (:160-166) already assigns RBT_MISSING_LOG "UNCONDITIONALLY, NEVER INHERITED",
# because a nested copy of the runner inheriting its parent's log made the parent
# go red over a suite that had passed. Same defect, same fix — the runner learned
# it and the suites it runs had not.
#
# THE FIX FIXES THE BRANCH, it does not read the host's. `git symbolic-ref HEAD
# refs/heads/main` rather than `git init -b main`, and the choice is deliberate:
# `-b` needs git >= 2.28 and would drag a version test plus a fallback into the
# fixture, whereas `symbolic-ref` has been there essentially forever, works on a
# bare repo and on an unborn HEAD, writes no file in the working tree and needs no
# version branch at all. One gesture, no conditional.
# The alternative — push whatever `git symbolic-ref --short HEAD` reports — was
# REJECTED: it makes the branch name a variable in ten places including two
# assertion literals, and it would keep the bench agreeing with whatever the host
# happens to do, which is the very habit that produced this red.
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
# Arm 12's nested run RE-ESTABLISHES the injection the purge above just removed
# (see « THE SIMULATION IS ADDITIVE » at arm 12) — before any git command here.
if [ "${PREPUSH_TEST_NESTED:-0}" = "1" ]; then
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=init.defaultBranch GIT_CONFIG_VALUE_0=master
fi

# Deliberately NOT named ROOT. `.agents/evals/test_adopting_gate.py` treats a
# `ROOT=` binding to the real tree as an anchor and then flags `$ROOT/<stripped
# prefix>` sites; naming it KIT keeps this suite out of that locator entirely
# rather than relying on `.githooks/` never becoming a stripped prefix.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$KIT/.githooks/pre-push"
SELF="$KIT/.githooks/$(basename "${BASH_SOURCE[0]}")"
[ -f "$HOOK" ] || { echo "FAIL: $HOOK not found"; exit 1; }

TMP="$(mktemp -d)"
# Guarded on BASHPID rather than left bare, for the reason measured in
# core-scripts/verify.test.sh: a forked child can run this inherited EXIT trap and
# wipe $TMP mid-run. `$$` is the PARENT's pid in the child and cannot guard it.
TMP_OWNER="${BASHPID:-$$}"
cleanup() {
  if [ "${BASHPID:-$$}" = "$TMP_OWNER" ]; then rm -rf "$TMP"; fi
  return 0
}
trap cleanup EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }
if grep -Fq 'cp .githooks/pre-push .git/hooks/pre-push' "$HOOK"; then
  fail "installation : conseil de copie par-dessus un pre-push existant"
fi
grep -Fq 'hooks; never copy the kit' "$HOOK" \
  || fail "installation : conseil de chainage absent"
grep -Fq "si aucun hook n'est actif : git config core.hooksPath .githooks" "$KIT/core-scripts/verify.sh" \
  || fail "verify : activation proposee sans condition"

# --- throwaway remote + clone -------------------------------------------------
BARE="$TMP/remote.git"
CLONE="$TMP/clone"
git init -q --bare "$BARE"
# THE DEFAULT BRANCH IS CONSTRUCTED HERE, NOT INHERITED FROM THE HOST (header).
# Set on the BARE, which is where `git init` applied `init.defaultBranch`...
git -C "$BARE" symbolic-ref HEAD refs/heads/main
git clone -q "$BARE" "$CLONE"
# ...and again on the CLONE. MEASURED REDUNDANT on git 2.55.0 — cloning the empty
# bare above carried `refs/heads/main` across on its own — and kept anyway, for
# one reason: that carry is a property of the CLONE PROTOCOL, i.e. of the host's
# git, and betting the fixture on it is the exact habit that produced this red.
# Two cheap unconditional gestures, zero inference.
git -C "$CLONE" symbolic-ref HEAD refs/heads/main
# NON-VACUITY, asserted before the first commit rather than discovered at the
# first push: if this ever reports anything but `main`, every `push origin main`
# below would fail on `src refspec main does not match any` — a red that names
# neither the hook nor the cause.
FIXTURE_BRANCH="$(git -C "$CLONE" symbolic-ref --short HEAD)"
[ "$FIXTURE_BRANCH" = "main" ] \
  || fail "setup: the fixture clone is on '$FIXTURE_BRANCH', not main — every arm below would test the refspec, not the hook"
git -C "$CLONE" config user.email t@t
git -C "$CLONE" config user.name t
# Byte-identical checkouts: a global autocrlf=true (the Windows default) would
# hand back a CRLF copy of the hook, which is a different file than the one shipped.
git -C "$CLONE" config core.autocrlf false

# LA BRANCHE DE TRAVAIL DU BANC N'EST PLUS LA BRANCHE PAR DEFAUT (T-00000595).
# `pre-push` porte desormais DEUX familles de regles : le verdict de tampon, et
# « aucun merge vers la branche par defaut sans revue humaine ». Les eprouver a
# travers le MEME ref les rendrait indissociables — un arm de tampon rougirait
# pour une raison de branche, et l'inverse. Les arms de tampon poussent donc
# `travail`, exactement comme le depot lui-meme travaille sur une branche de
# chantier ; la regle de branche par defaut a ses arms propres, 13 a 16.
# Le montage `main` ci-dessus RESTE : le bare a besoin d'une branche par defaut
# CONSTRUITE et non heritee de l'hote, et c'est elle que les arms 13-16 visent.
git -C "$CLONE" checkout -q -b travail
FIXTURE_WORK="$(git -C "$CLONE" symbolic-ref --short HEAD)"
[ "$FIXTURE_WORK" = "travail" ] \
  || fail "setup: la branche de travail est '$FIXTURE_WORK' — les arms de tampon testeraient le refspec, pas le hook"

# THE DOCUMENTED INSTALLATION GESTURE, executed rather than described.
mkdir -p "$CLONE/.githooks"
cp "$HOOK" "$CLONE/.githooks/pre-push"
chmod +x "$CLONE/.githooks/pre-push"
git -C "$CLONE" config core.hooksPath .githooks

STAMP="$CLONE/.agents/state/local/VERIFY_STAMP"
mkdir -p "$(dirname "$STAMP")"

stamp() {  # stamp <sha> <mode> <linux>
  { echo "sha=$1"
    echo "mode=$2"
    echo "linux=$3"
    echo "host=fixture"
    echo "at=fixture"
  } > "$STAMP"
}
no_stamp() { rm -f "$STAMP"; }

commit() {  # commit <text> -> prints the new full sha
  echo "$1" >> "$CLONE/work.txt"
  git -C "$CLONE" add -A
  git -C "$CLONE" commit -qm "$1"
  git -C "$CLONE" rev-parse HEAD
}

# `push <args...>` — never `set -e`-fatal, always captures stderr (the hook's only
# channel). A verification is never truncated: the whole output is kept.
push() {
  set +e
  PUSH_OUT="$(git -C "$CLONE" push "$@" 2>&1)"
  PUSH_RC=$?
  set -e
  return 0
}

C1="$(commit one)"

# 1. NO STAMP AT ALL → refuse. Fail-closed is the whole point: an absent verdict
#    is not a neutral state, it is "nothing here says this was ever verified".
#    TWO mutations redden this arm, and BOTH are written down because they are
#    caught by DIFFERENT assertions. The previous version of this comment claimed
#    the second one SURVIVED — it does not, and the error ran in the reassuring
#    direction: it presented the second assertion as decorative when it is the only
#    thing that kills that mutant. Re-measured on a copy of the hook, not inferred.
#    MUTATION A — the classic fail-open: `[ -f "$STAMP" ] || exit 0` before the ref
#    loop. The push is ACCEPTED and the FIRST assertion fires:
#      FAIL: 1: a push with no stamp must be refused: To …/remote.git
#       * [new branch]      main -> main
#    MUTATION B — default `stamp_ok=1` instead of 0. The push is still REFUSED (the
#    sha comparison below rejects an empty `stamp_sha`), so the first assertion
#    survives; the SECOND, the diagnostic, is what kills it:
#      FAIL: 1: no diagnostic naming the missing stamp: PUSH REFUSED
#      (refs/heads/main): the green verdict covers  but you are pushing 038003ef…
#    Read together they say why both lines are here: THAT a push is refused and
#    WHAT REASON IS PRINTED are two separate guarantees, and a refusal blaming the
#    wrong cause sends the pilot to re-run verify.sh for a stamp that never existed.
no_stamp
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "1: a push with no stamp must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "no verdict stamp" || fail "1: no diagnostic naming the missing stamp: $PUSH_OUT"

# 2. THE STAMP COVERS ANOTHER SHA → refuse, and print BOTH shas plus the ref, or
#    the pilot cannot tell a stale verdict from a wrong branch.
#    MUTATION: compare only the first 7 characters → green.
OTHER_SHA="0123456789abcdef0123456789abcdef01234567"
stamp "$OTHER_SHA" frozen 1
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "2: a stamp for another sha must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "$OTHER_SHA" || fail "2: the refusal does not name the verified sha: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "$C1" || fail "2: the refusal does not name the sha being pushed: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "refs/heads/travail" || fail "2: the refusal does not name the ref: $PUSH_OUT"

# 3. mode=live → refuse. A live-tree run measured something that moves; it is not
#    anchored, and the remedy is the frozen form.
#    MUTATION: drop the `mode=live` branch → green.
stamp "$C1" live 1
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "3: mode=live must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "mode=live" || fail "3: the refusal does not name the mode: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q -- "--at" || fail "3: the refusal does not carry the remedy: $PUSH_OUT"

# 4. POSITIVE CONTROL — and the arm that proves the other ten are not all green by
#    accident. A host-only frozen verdict (linux=0) is ACCEPTED by default, and the
#    uncovered leg is ANNOUNCED. A guard that only ever refuses has not been shown
#    to see anything.
#    MUTATION: refuse on linux=0 unconditionally → red here.
stamp "$C1" frozen 0
push origin travail
[ "$PUSH_RC" -eq 0 ] || fail "4: a host-only frozen verdict must be accepted by default: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "container leg: NOT covered" \
  || fail "4: the uncovered container leg was not announced: $PUSH_OUT"
[ "$(git -C "$BARE" rev-parse refs/heads/travail)" = "$C1" ] || fail "4: the accepted push did not reach the remote"

# 5. OPT-IN STRICTNESS. `verify.requireLinux=true` turns the announcement into a
#    refusal — one line of config, reversible, aligned on ci.yml where ubuntu is
#    the non-blocking leg.
#    MUTATION: read the config as a plain string instead of `--bool` → an operator
#    writing `yes` or `1` would silently get no strictness at all.
C2="$(commit two)"
stamp "$C2" frozen 0
git -C "$CLONE" config --bool verify.requireLinux true
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "5: requireLinux=true with linux=0 must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "requireLinux" || fail "5: the refusal does not name the setting: $PUSH_OUT"

# 6. linux=1 satisfies the strict setting.
#    MUTATION: ignore the `linux=` field → arm 5 and this arm agree, and the field
#    means nothing.
stamp "$C2" frozen 1
push origin travail
[ "$PUSH_RC" -eq 0 ] || fail "6: a linux=1 verdict must satisfy requireLinux: $PUSH_OUT"
git -C "$CLONE" config --unset verify.requireLinux

# 7. A REF DELETION carries an all-zero local sha and pushes no content, so there
#    is nothing to have verified. It must pass with NO stamp on disk at all.
#    MUTATION: drop the all-zero test → deleting a branch becomes impossible
#    whenever the stamp is stale, which is most of the time.
git -C "$CLONE" branch doomed "$C2"
stamp "$C2" frozen 1
push origin doomed
[ "$PUSH_RC" -eq 0 ] || fail "7: setup — pushing the branch to delete failed: $PUSH_OUT"
no_stamp
push origin --delete doomed
[ "$PUSH_RC" -eq 0 ] || fail "7: a ref DELETION must pass with no stamp: $PUSH_OUT"
if git -C "$BARE" rev-parse --verify --quiet refs/heads/doomed >/dev/null; then
  fail "7: the deletion did not actually reach the remote"
fi

# 8. A MALFORMED STAMP IS NOT A WEAKER VERDICT, IT IS NOT A VERDICT. Two shapes,
#    both fail-closed, and the message must distinguish them from "absent" or the
#    pilot re-runs verify.sh for nothing.
#    MUTATION: accept a stamp as soon as `sha=` parses → both shapes go green.
C3="$(commit three)"
#    (a) fields missing.
{ echo "sha=$C3"; } > "$STAMP"
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "8a: a stamp missing mode/linux must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "MALFORMED" || fail "8a: the refusal does not say the stamp is malformed: $PUSH_OUT"
#    (b) a zero-byte file — what a truncated or interrupted write leaves behind.
: > "$STAMP"
push origin travail
[ "$PUSH_RC" -ne 0 ] || fail "8b: an empty stamp must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "MALFORMED" || fail "8b: an empty stamp was not reported as malformed: $PUSH_OUT"

# 9. SEVERAL REFS IN ONE PUSH. `git push --all`, `--tags` and `git push origin a b`
#    all send more than one line, and a hook that read one line would gate the
#    FIRST ref and wave the rest through in silence. Here line 1 is covered by the
#    stamp and line 2 is not: the push must be refused, naming the SECOND ref.
#    MUTATION, MEASURED: add a `break` at the end of the loop body, so only the
#    FIRST ref is examined → this arm goes green while the hole is wide open.
git -C "$CLONE" branch b1 "$C3"
B2_SHA="$(git -C "$CLONE" commit-tree -p "$C3" -m four "$(git -C "$CLONE" rev-parse "$C3^{tree}")")"
git -C "$CLONE" branch b2 "$B2_SHA"
stamp "$C3" frozen 1
push origin b1 b2
[ "$PUSH_RC" -ne 0 ] || fail "9: a multi-ref push whose SECOND ref is unverified must be refused: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "refs/heads/b2" || fail "9: the refusal does not name the offending second ref: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "$B2_SHA" || fail "9: the refusal does not name the second ref's sha: $PUSH_OUT"
if git -C "$BARE" rev-parse --verify --quiet refs/heads/b1 >/dev/null; then
  fail "9: b1 reached the remote although the push was refused as a whole"
fi

# 10. A TAG PUSH IS NOT GATED, AND THE HOOK SAYS SO. For an ANNOTATED tag the local
#     sha is the TAG OBJECT, never a commit, so the 40-hex equality would refuse
#     every tag push without ever explaining why. The hole is DECLARED in the
#     message — an undeclared hole is the one nobody can plan around.
#     MUTATION: delete the `refs/tags/*` case → this arm goes red, which is exactly
#     the day the ceiling changes and the documents must change with it.
git -C "$CLONE" -c user.email=t@t -c user.name=t tag -a v1 -m "release one" "$C3"
TAG_OBJ="$(git -C "$CLONE" rev-parse refs/tags/v1)"
[ "$TAG_OBJ" != "$C3" ] || fail "10: fixture is not an ANNOTATED tag — the arm would prove nothing"
no_stamp
push origin v1
[ "$PUSH_RC" -eq 0 ] || fail "10: an annotated tag push must pass: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "is a tag — NOT gated" || fail "10: the tag hole is not declared in the message: $PUSH_OUT"
[ "$(git -C "$BARE" rev-parse refs/tags/v1)" = "$TAG_OBJ" ] || fail "10: the tag did not reach the remote"

# 11. THE EXECUTABLE BIT IN THE INDEX — the property that actually TRAVELS. The ten
#     arms above measure a COPY of the hook, whose mode comes from the working tree
#     and from `chmod` above; none of them can see a hook committed 100644. On any
#     Unix clone of an adopting project such a hook is SILENTLY INERT: git runs it
#     only if it is executable, and says nothing when it is not.
#     MUTATION: `git update-index --chmod=-x .githooks/pre-push` → red.
MODE="$(git -C "$KIT" ls-files -s .githooks/pre-push | cut -d' ' -f1)"
[ -n "$MODE" ] || fail "11: .githooks/pre-push is not in the index — its mode cannot travel at all"
[ "$MODE" = "100755" ] || fail "11: .githooks/pre-push is tracked as $MODE, not 100755 — the hook ships INERT on Unix clones"

# --- 13-19. « AUCUN MERGE VERS LA BRANCHE PAR DEFAUT SANS REVUE HUMAINE » -----
# T-00000595. PLACES ICI, AVANT L'ARM 12, ET CE N'EST PAS UN DETAIL DE MISE EN
# PAGE : l'arm 12 sort par `exit 0` sur DEUX chemins (run niche, git < 2.31), et
# tant que ces arms etaient APRES, un hote en git ancien rendait un PASS sans
# avoir joue une seule fois la regle neuve. Mesure du binome : garde entierement
# retiree + PREPUSH_TEST_NESTED=1 -> `PASS: pre-push (11/11)`. Corrige : le run
# niche joue desormais 1-11 puis 13-19, et son etiquette dit 18/18.
#
# LA GARDE EST ARMEE PAR UN MARQUEUR (decision pilote du 2026-09-14 : elle
# protege CE depot, pas l'adoptant). Ces arms l'arment donc explicitement, et
# l'arm 13 mesure d'abord qu'elle est INERTE sans lui — c'est le regime que
# l'adoptant recoit.
MAIN_GUARD="$CLONE/.agents/state/gates/PUSH_DEFAUT_PROTEGE"
MAIN_EXIT="$CLONE/.agents/state/gates/PUSH_DEFAUT_AUTORISE"
MAIN_JOURNAL="$CLONE/.agents/state/local/push-defaut-sorties.log"
mkdir -p "$(dirname "$MAIN_EXIT")"

C_MAIN="$(commit vers-la-branche-par-defaut)"
stamp "$C_MAIN" frozen 1

echo "=== 13. SANS marqueur d'armement, la garde est INERTE — le cas de l'adoptant ==="
# LE CONTROLE LE PLUS IMPORTANT DU LOT. Le hook VOYAGE, `.agents/state/` est
# `strip:` de la template : l'adoptant recoit le mecanisme et pas CE marqueur
# (la sync n'y seme que ceux des quatre gardes de pipeline, T-00001093).
# Si cet arm rougit, la garde part armee chez lui et refuse tous ses pushs.
[ ! -f "$MAIN_GUARD" ] || fail "13: le marqueur ne devrait pas exister a ce stade"
push origin travail:main
[ "$PUSH_RC" -eq 0 ] || fail "13: SANS marqueur la garde doit etre INERTE — elle voyagerait armee chez l'adoptant: $PUSH_OUT"
git -C "$BARE" update-ref -d refs/heads/main

echo "=== 14. AVEC le marqueur, le push vers la branche par defaut est REFUSE ==="
printf 'arme pour le banc\n' > "$MAIN_GUARD"
push origin travail:main
[ "$PUSH_RC" -ne 0 ] || fail "14: un push vers la branche par defaut doit etre REFUSE: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "refs/heads/main" || fail "14: le refus ne nomme pas le ref vise: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "revue humaine" || fail "14: le refus ne nomme pas la clause: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "PUSH_DEFAUT_AUTORISE" \
  || fail "14: le refus ne nomme pas sa sortie tracee — une garde sans echappatoire nommee est desarmee dans la semaine: $PUSH_OUT"
[ "$(git -C "$BARE" rev-parse --verify -q refs/heads/main || echo ABSENT)" = "ABSENT" ] \
  || fail "14: le ref a ete cree malgre le refus"

echo "=== 15. CONTROLE NEGATIF : meme sha, meme tampon, autre ref -> passe ==="
push origin travail
[ "$PUSH_RC" -eq 0 ] || fail "15: sinon 14 serait satisfait par un hook qui refuse TOUT: $PUSH_OUT"

echo "=== 16. un marqueur de sortie VIDE ne desarme PAS ==="
# Mesure du binome : un `touch` ouvrait le passage, alors que le refus demande
# d'ECRIRE la raison.
: > "$MAIN_EXIT"
push origin travail:main
[ "$PUSH_RC" -ne 0 ] || fail "16: une sortie VIDE ne doit pas ouvrir le passage: $PUSH_OUT"
[ -f "$MAIN_EXIT" ] || fail "16: une sortie vide ne doit pas etre consommee non plus"
rm -f "$MAIN_EXIT"

echo "=== 17. la sortie n'est PAS consommee quand le push est refuse AILLEURS ==="
# Elle etait consommee DANS la boucle, avant le verdict de tampon : le journal
# inscrivait un merge qui n'avait pas eu lieu, et le pilote perdait son ticket.
printf 'raison du cas 17' > "$MAIN_EXIT"
stamp "0000000000000000000000000000000000000000000000000000000000000000" frozen 1
push origin travail:main
[ "$PUSH_RC" -ne 0 ] || fail "17: le tampon est perime, le push doit etre refuse: $PUSH_OUT"
[ -f "$MAIN_EXIT" ] || fail "17: la sortie a ete CONSOMMEE sur un push refuse — le ticket est brule pour rien"
[ ! -f "$MAIN_JOURNAL" ] \
  || fail "17: le journal porte un merge qui n'a jamais eu lieu: $(cat "$MAIN_JOURNAL")"
echo "$PUSH_OUT" | grep -q "LAISSEE EN PLACE\|LAISSÉE EN PLACE" \
  || fail "17: le hook ne DIT pas que la sortie est laissee en place: $PUSH_OUT"

echo "=== 18. la SORTIE TRACEE ouvre le passage, se CONSOMME et se JOURNALISE ==="
stamp "$C_MAIN" frozen 1
push origin travail:main
[ "$PUSH_RC" -eq 0 ] || fail "18: la sortie tracee doit ouvrir le passage: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "AUTORIS" || fail "18: le passage n'est pas ANNONCE: $PUSH_OUT"
[ ! -f "$MAIN_EXIT" ] || fail "18: la sortie n'a pas ete CONSOMMEE — elle vaudrait pour toujours"
[ -f "$MAIN_JOURNAL" ] || fail "18: aucun journal ecrit — la sortie doit rester VISIBLE"
grep -q "raison du cas 17" "$MAIN_JOURNAL" || fail "18: le journal ne porte pas la RAISON: $(cat "$MAIN_JOURNAL")"
[ "$(git -C "$BARE" rev-parse refs/heads/main)" = "$C_MAIN" ] || fail "18: le push autorise n'a pas atteint le remote"

echo "=== 19. master AUSSI, et la SUPPRESSION de la branche par defaut ==="
# MUTATION MESUREE : reduire le motif a `refs/heads/main)` -> 16/16 VERT sans cet arm.
C_M2="$(commit vers-master)"
stamp "$C_M2" frozen 1
push origin travail:master
[ "$PUSH_RC" -ne 0 ] || fail "19: un push vers refs/heads/master doit etre REFUSE: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "refs/heads/master" || fail "19: le refus ne nomme pas master: $PUSH_OUT"
# La SUPPRESSION sautait le `case` par le `continue` du sha nul — le geste le
# plus destructeur sur cette branche etait le seul qui echappait.
push origin --delete main
[ "$PUSH_RC" -ne 0 ] || fail "19: la SUPPRESSION de la branche par defaut doit etre REFUSEE: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "SUPPRIME" || fail "19: le refus ne dit pas qu'il s'agit d'une suppression: $PUSH_OUT"
[ "$(git -C "$BARE" rev-parse refs/heads/main)" = "$C_MAIN" ] || fail "19: la branche a ete supprimee malgre le refus"

# La garde est DESARMEE pour la suite : l'arm 12 rejoue ce banc en niche, et il
# ne doit pas heriter d'un marqueur pose ici.
rm -f "$MAIN_GUARD" "$MAIN_EXIT"

# 12. THIS BENCH, RUN ON A HOST WHOSE DEFAULT BRANCH IS `master`. The eleven arms
#     above are green on any box configured `init.defaultBranch=main`, and ALL
#     ELEVEN were green here while the gate was red — because they were measuring
#     a fixture built by the host, not by the bench. This is the only cell that
#     builds the hostile host on purpose.
#
#     WITHOUT IT THE FIX IS UNGUARDED IN THE ONE DIRECTION THAT MATTERS: the two
#     `symbolic-ref` lines in the setup could be deleted by a reviewer who checks
#     `git config init.defaultBranch`, sees `main`, and concludes they are dead
#     code — and every arm above would stay green on that reviewer's box, exactly
#     as they did on the box where this lot was written.
#     MUTATION, AND IT IS STATED AT THE STRENGTH IT WAS MEASURED AT, NOT AT THE
#     STRENGTH THAT WOULD READ BETTER. Delete BOTH `symbolic-ref HEAD
#     refs/heads/main` lines → still GREEN on a main-defaulting host (18/18 the
#     old way), RED here, on the setup assertion carried out of the nested run:
#       FAIL: 12: this bench is RED on a host whose default branch is master —
#       which is what the gate container is: FAIL: setup: the fixture clone is on
#       'master', not main — every arm below would test the refspec, not the hook
#     DELETING EITHER LINE ALONE SURVIVES, measured on git 2.55.0, and the survival
#     is the two lines covering for each other: drop the BARE one and the clone's
#     own symbolic-ref repairs HEAD; drop the CLONE one and the clone inherits the
#     bare's symref anyway. So this arm guards THE PAIR, not each line — said
#     plainly rather than left for someone to discover by deleting one and seeing
#     green. On a git whose clone does NOT carry the symref the first mutation
#     would bite on its own; that version-dependence is exactly why both stay.
#
#     THE SIMULATION IS ADDITIVE. `GIT_CONFIG_COUNT`/`KEY_0`/`VALUE_0` injects ONE
#     key and removes nothing — deliberately not a `HOME` override pointing at a
#     fabricated `.gitconfig`, which would ALSO drop the real global config and,
#     in a container running as root over a mounted tree, take `safe.directory`
#     with it: arm 11's `git -C "$KIT" ls-files` would then die on dubious
#     ownership and this arm would be red for a reason of its own making.
#     WHERE IT IS SET (T-00001088): no longer on the nested command line. The
#     FORME A at the top of this file PURGES `GIT_CONFIG_COUNT` with every other
#     inherited git variable, so an injection handed down by this parent would be
#     wiped before the nested run's first git command. The nested run therefore
#     RE-ESTABLISHES it itself, right after the purge, under PREPUSH_TEST_NESTED=1
#     — still one key, still additive.
#
#     Re-entry is guarded — this arm runs THIS FILE — and the nested run REPORTS
#     THE DEFAULT IT ACTUALLY SAW rather than merely announcing that it is nested.
#     That is what makes the arm non-vacuous: the assertion pins the string to
#     `master`, so a simulation that failed to take is red, never a quiet green.
if [ "${PREPUSH_TEST_NESTED:-0}" = "1" ]; then
  echo "PASS: pre-push (18/18, nested with init.defaultBranch=$(git config --get init.defaultBranch 2>/dev/null || echo '<unset>') — arm 12 not re-entered)"
  exit 0
fi

#     The injection needs git >= 2.31. Older git is not a failure of the fix, so it
#     is a NAMED skip and never a red: an arm that cannot build its environment
#     must say so rather than blame the subject.
INJECTED="$(GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=init.defaultBranch GIT_CONFIG_VALUE_0=master \
  git config --get init.defaultBranch 2>/dev/null || true)"
if [ "$INJECTED" != "master" ]; then
  echo "SKIP arm 12: $(git --version) ignores GIT_CONFIG_COUNT (needs >= 2.31) — a master-defaulting host cannot be simulated here"
  echo "PASS: pre-push (18/18, arm 12 skipped)"
  exit 0
fi

set +e
NESTED_OUT="$(PREPUSH_TEST_NESTED=1 bash "$SELF" 2>&1)"
NESTED_RC=$?
set -e
[ "$NESTED_RC" -eq 0 ] \
  || fail "12: this bench is RED on a host whose default branch is master — which is what the gate container is: $NESTED_OUT"
echo "$NESTED_OUT" | grep -q "nested with init.defaultBranch=master" \
  || fail "12: the nested run did not report a master default — the simulation never took and this arm proved nothing: $NESTED_OUT"

# E2: the five files below are fixture material, not reads from the host tree.
# A fresh template tag must pass; a renamed destination governs even when the
# local ref is not a template tag. Every refusal checks the named reason.
mkdir -p "$CLONE/.agents/bin" "$CLONE/.agents/adopter-docs/docs" "$CLONE/docs"
cp "$KIT/.agents/bin/sync_template_docs.py" "$CLONE/.agents/bin/"
cp "$KIT/.agents/bin/sync_template.py" "$CLONE/.agents/bin/"
cp "$KIT/.agents/bin/sync_template_proc.py" "$CLONE/.agents/bin/"
cp "$KIT/.agents/pyrun.sh" "$CLONE/.agents/pyrun.sh"
: > "$CLONE/.agents/IS_THE_KIT"
git -C "$CLONE" checkout -q -b develop
printf '# Adoptant\n' > "$CLONE/.agents/adopter-docs/README.md"
printf '## 1.0.0 — 2026-10-23\n' > "$CLONE/.agents/adopter-docs/CHANGELOG.md"
printf '<html>manuel</html>\n' > "$CLONE/.agents/adopter-docs/docs/usage.html"
SOURCE_SHA="$(commit 'sources de coupe')"
git -C "$CLONE" checkout -q -b template/starter-kit
cp "$CLONE/.agents/adopter-docs/README.md" "$CLONE/README.md"
cp "$CLONE/.agents/adopter-docs/CHANGELOG.md" "$CLONE/CHANGELOG.md"
cp "$CLONE/.agents/adopter-docs/docs/usage.html" "$CLONE/docs/usage.html"
git -C "$CLONE" rm -rq -- .agents/adopter-docs
ANCHOR_SHA="$(commit "chore(template): sync from develop @ $SOURCE_SHA")"
[ -z "$(git -C "$CLONE" ls-tree -r --name-only "$ANCHOR_SHA" -- .agents/adopter-docs/)" ] \
  || fail "E2 fixture : les sources strip: voyagent encore dans le template"
GIT_COMMITTER_DATE='2026-10-23T12:00:00+0200' git -C "$CLONE" tag -a tag-frais -m frais "$ANCHOR_SHA"
push origin tag-frais:refs/tags/template/v1.0.0-2026-10-23
[ "$PUSH_RC" -eq 0 ] || fail "E2 frais : tag refusé : $PUSH_OUT"
echo "$PUSH_OUT" | grep -q 'docs fraîches' || fail "E2 frais : pas de verdict CLI : $PUSH_OUT"
if echo "$PUSH_OUT" | grep -q 'Declared hole'; then fail "E2 frais : message de trou imprimé"; fi
echo 'PASS: E2 tag frais et R1'

printf 'périmé\n' > "$CLONE/README.md"
STALE_SHA="$(commit 'destination périmée')"
push origin "HEAD:refs/tags/template/v1.0.0.dev2-2026-10-23"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'document périmé : README.md' \
  || fail "E2 HEAD renommé : destination périmée non refusée : $PUSH_OUT"
push origin "$STALE_SHA:refs/tags/template/v1.0.0.dev3-2026-10-23"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'document périmé : README.md' \
  || fail "E2 sha renommé : destination périmée non refusée : $PUSH_OUT"
git -C "$CLONE" tag tag-perime "$STALE_SHA"
push origin 'tag-perime:refs/tags/template/v1.0.0.dev4-2026-10-23'
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'document périmé : README.md' \
  || fail "E2 tag local renommé : destination périmée non refusée : $PUSH_OUT"
echo 'PASS: E2 remote_ref, HEAD, sha et tag local'

push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0-2026-10-22"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'date/version du CHANGELOG' \
  || fail "E2 date du nom : discordance non refusée : $PUSH_OUT"
GIT_COMMITTER_DATE='2026-10-22T12:00:00+0200' git -C "$CLONE" tag -a tag-date-fausse -m fausse "$ANCHOR_SHA"
push origin 'tag-date-fausse:refs/tags/template/v1.0.0-2026-10-23'
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'taggerdate' \
  || fail "E2 taggerdate : discordance non refusée : $PUSH_OUT"
echo 'PASS: E2 date du nom et taggerdate R2'

git -C "$CLONE" checkout -q develop
printf 'source plus récente\n' > "$CLONE/.agents/adopter-docs/README.md"
commit 'source après ancre' >/dev/null
git -C "$CLONE" checkout -q template/starter-kit
push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0.dev5-2026-10-23"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'sources adoptant modifiées' \
  || fail "E2 source après ancre : pas de refus : $PUSH_OUT"
echo 'PASS: E2 source modifiée'

DOCS_SCRIPT="$CLONE/.agents/bin/sync_template_docs.py"
cp "$DOCS_SCRIPT" "$TMP/sync_template_docs.py"
printf 'import sys\nsys.exit(2)\n' > "$DOCS_SCRIPT"
push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0.dev6-2026-10-23"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'rc 2' \
  || fail "E2 rc 2 : erreur CLI laissée passer : $PUSH_OUT"
cp "$TMP/sync_template_docs.py" "$DOCS_SCRIPT"
# python3/python/py are STUBS that fail the probe, never absent commands: the
# runner's exported command_not_found_handle would log an absent name and class
# this suite MISSING DEP (core-scripts/run-bash-tests.sh, same pattern as
# .agents/evals/events-wiring.test.sh).
mkdir -p "$TMP/no-python"
ln -s "$(command -v git)" "$TMP/no-python/git"
ln -s "$(command -v bash)" "$TMP/no-python/bash"
for py in python3 python py; do
  printf '%s\n' '#!/bin/sh' 'exit 1' > "$TMP/no-python/$py"
  chmod +x "$TMP/no-python/$py"
done
NO_PY_LINE="refs/heads/template/starter-kit $ANCHOR_SHA refs/tags/template/v1.0.0.dev7-2026-10-23 0000000000000000000000000000000000000000"
set +e
NO_PY_OUT="$(printf '%s\n' "$NO_PY_LINE" | (cd "$CLONE" && PATH="$TMP/no-python" /bin/bash .githooks/pre-push) 2>&1)"
NO_PY_RC=$?
set -e
[ "$NO_PY_RC" -ne 0 ] && echo "$NO_PY_OUT" | grep -q 'PYTHON 3 NOT FOUND' && echo "$NO_PY_OUT" | grep -q 'rc 127' \
  || fail "E2 R3 : pyrun sans Python n'a pas refusé 127 : $NO_PY_OUT"
echo 'PASS: E2 rc 2 et rc 127 R3'

mv "$DOCS_SCRIPT" "$TMP/sync_template_docs.absent.py"
push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0.dev8-2026-10-23"
[ "$PUSH_RC" -ne 0 ] && echo "$PUSH_OUT" | grep -q 'indisponible dans le kit' \
  || fail "E2 script absent dans le kit : pas de refus : $PUSH_OUT"
rm -f "$CLONE/.agents/IS_THE_KIT"
push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0.dev9-2026-10-23"
if echo "$PUSH_OUT" | grep -q 'dans le kit'; then
  fail "E2 adoptant : message du kit imprimé : $PUSH_OUT"
fi
ADOPT_NO_SCRIPT_RC=$PUSH_RC
mv "$TMP/sync_template_docs.absent.py" "$DOCS_SCRIPT"
# Adoptant, script PRÉSENT : le tag retombe sur le chemin de base (tampon), comme
# avant la jambe de fraîcheur — jamais un passage sans contrôle.
push origin "$ANCHOR_SHA:refs/tags/template/v1.0.0.dev10-2026-10-23"
ADOPT_SCRIPT_RC=$PUSH_RC
ADOPT_SCRIPT_OUT=$PUSH_OUT
if echo "$ADOPT_SCRIPT_OUT" | grep -q 'NOT gated in this adopting project'; then
  fail "E2 adoptant : tag laissé passer sans le chemin de base (tampon) : $ADOPT_SCRIPT_OUT"
fi
if echo "$ADOPT_SCRIPT_OUT" | grep -q 'docs fraîches\|fraîcheur du tag'; then
  fail "E2 adoptant : jambe de fraîcheur du kit jouée chez l'adoptant : $ADOPT_SCRIPT_OUT"
fi
[ "$ADOPT_SCRIPT_RC" -eq "$ADOPT_NO_SCRIPT_RC" ] \
  || fail "E2 adoptant : script présent ($ADOPT_SCRIPT_RC) et absent ($ADOPT_NO_SCRIPT_RC) jugés différemment : $ADOPT_SCRIPT_OUT"
# Le chemin de base REFUSE ce commit sans tampon : un passage silencieux (echo retiré) doit rougir.
[ "$ADOPT_SCRIPT_RC" -ne 0 ] && echo "$ADOPT_SCRIPT_OUT" | grep -q 'green verdict covers' \
  || fail "E2 adoptant : tag sans tampon non refusé par le chemin de base : $ADOPT_SCRIPT_OUT"
echo 'PASS: E2 script absent dans le kit et tag adoptant (chemin de base)'

echo "PASS: pre-push (19/19 legacy + E2)"
