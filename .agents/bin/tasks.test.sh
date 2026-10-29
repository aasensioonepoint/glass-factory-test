#!/usr/bin/env bash
# Tests for tasks.py. Run: bash .agents/bin/tasks.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# allows-missing: python python3 py
#
# The interpreter probe below EXECUTES each of three names to find one that
# answers `--version`, so on a box carrying only python3 the names `python` and
# `py` legitimately fail to resolve. MEASURED here: `python` is absent and the
# runner's swallowed-127 sensor caught it. Without this line the sensor would
# report a missing dependency for a probe doing exactly its job — the false red
# the opt-out exists to prevent. It is NOT `requires:`, because that header names
# ONE command while this is a three-name ALTERNATIVE; if none of the three
# resolve, the SKIP on the line after is counted by the runner's survey.
set -e
# Byte-wise matching: under a UTF-8 locale this grep fails to match the state
# emoji inside a `.*` regex. The files are UTF-8, the assertions are on bytes.
export LC_ALL=C
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/tasks.py"
PY=""; for c in python python3 py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# T-00000753 : joué DIRECTEMENT, ce banc isole son état machine (le runner le fait déjà, `run-bash-tests.sh`) ;
# une valeur déjà posée est RESPECTÉE. Sous $TMP : nettoyé par le trap ci-dessus.
if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi
STORE="$TMP/.agents/state/board/TASKS.json"
VIEW="$TMP/.agents/state/local/TASKS.md"
fail() { echo "FAIL: $1"; echo "--- store ---"; cat "$STORE" 2>/dev/null; echo "--- view ---"; cat "$VIEW" 2>/dev/null; exit 1; }
tasks() { "$PY" "$SCRIPT" --root "$TMP" "$@"; }
rows() { grep '^| T-' "$VIEW"; }
# The id `new` RETURNED (« TASKS: <id> → pending »), never a predicted one: under the P-<ULID>
# allocator (T-00000726, C2) no value is guessable — rule R-BANCS (i). Empty when `new` fails.
new_id() { tasks new "$@" | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p'; }
# Rule R-BANCS (iii): the PROPERTY, never the counter's value — the id returned is none of the ids
# already seen (second argument, space-separated), and it is not empty.
jamais_vu() {
  case " $2 " in
    *" $1 "*) return 1 ;;
  esac
  [ -n "$1" ]
}

# --- absent board: reads degrade instead of crashing ---------------------
tasks list | grep -q "empty" || fail "list on an absent board should say empty"
[ "$(tasks --statusline)" = "no active task" ] || fail "statusline on an absent board"

# --- new: creates BOTH artefacts and REPORTS the id it allocated ----------
# Captured, never predicted: 8 digits before the P-<ULID> switch (T-00000726), a ULID after it.
A="$(new_id "Auth refresh flow" --owner dev-multi)"
printf '%s\n' "$A" | grep -Eq '^T-([0-9]{8}|[0-9A-HJKMNP-TV-Z]{26})$' \
  || fail "new should report '<id> → pending' with a well-formed id, got: '$A'"
[ -f "$STORE" ] || fail "store not created"
[ -f "$VIEW" ] || fail "view not generated"
grep -q '"state": "pending"' "$STORE" || fail "store should record the state keyword"
grep -q "GENERATED from TASKS.json" "$VIEW" || fail "view should declare itself generated"
rows | grep -q "⚪ pending" || fail "view should render the pending emoji"

B="$(new_id "Rate-limit /login" --owner planner)"
C="$(new_id "Migrate to Prisma 6" --owner modeler)"
[ -n "$B" ] && [ -n "$C" ] || fail "new should report the ids it allocated"
[ "$(rows | wc -l | tr -d ' ')" = "3" ] || fail "expected 3 rendered rows"  # tr: BSD wc pads the count

# --- start: running + the running invariant (no group declared here) ------
tasks start "$A" --stage dev-multi >/dev/null
rows | grep -q "$A .*🟢 running.*dev-multi" || fail "$A should be running with its stage"
tasks start "$B" --stage planner >/dev/null
# `start` NE RÉTROGRADE PLUS (T-01M5F7286N1EYGXAXA5244X86B) : A tourne encore, B prend le focus.
[ "$(rows | grep -c '🟢 running')" = "2" ] || fail "start must demote nobody: both rows running"
rows | grep -q "$A .*🟢 running.*dev-multi" || fail "$A must keep its state and stage"
grep -q "\"task_id\": \"$B\"" "$TMP/.agents/state/local/focus.json" || fail "start should set the clone focus to $B"
# la SORTIE EXPLICITE de running : block sans note (stage gardé) puis unblock
tasks block "$A" >/dev/null && tasks unblock "$A" >/dev/null
rows | grep -q "$A .*⚪ pending" || fail "$A should be pending after its explicit exit"

# --- the store is the source of truth: a changed field is ONE line -------
cp "$STORE" "$TMP/before.json"
tasks stage "$B" security-code-review >/dev/null
CHANGED="$(diff "$TMP/before.json" "$STORE" | grep -c '^[<>]' || true)"
[ "$CHANGED" -le 4 ] || fail "one transition rewrote $CHANGED store lines; expected <= 4"

# --- fixed widths: a long title does NOT reflow the other rows -----------
cp "$VIEW" "$TMP/before.md"
D="$(new_id "A deliberately very long task title that exceeds the column width" --owner dev-mono)"
[ -n "$D" ] || fail "new should report the id it allocated"
diff "$TMP/before.md" "$VIEW" | grep '^<' | grep -q "$A" && fail "a new long-titled task reflowed the $A row"
rows | grep -q "…" || fail "an over-long title should be truncated, not widen the column"

# --- block: reason lands in the stage column -----------------------------
tasks block "$C" --note "pilot decision class-3" >/dev/null
rows | grep -q "$C .*🔴 blocked.*pilot decision class-3" || fail "block should record its reason"

# --- statusline: active task + counters ----------------------------------
# `start` a ouvert le dev au chrono (T-01M5KKFBCXXEVYR8GJPYFEH3C8) : le suffixe ⏱ précède le détail.
SL="$(tasks --statusline)"
case "$SL" in
  "▶ $B · ⏱ dev "[0-9]*"/? · security-code-review · ⏸2 ✓0") ;;
  *) fail "unexpected statusline: $SL" ;;
esac
# sans journal chrono, la ligne d'avant, octet pour octet
mv "$TMP/.agents/state/local/task-chrono" "$TMP/task-chrono.mis-de-cote"
[ "$(tasks --statusline)" = "▶ $B security-code-review · ⏸2 ✓0" ] || fail "statusline without a chrono journal changed"
mv "$TMP/task-chrono.mis-de-cote" "$TMP/.agents/state/local/task-chrono"

# --- retitle: updates the title only, any state, leaves state untouched --
tasks retitle "$C" "Migrate to Prisma 6 (rescoped)" | grep -q "$C retitled" || fail "retitle should confirm the id"
rows | grep -q "$C .*Migrate to Prisma 6 (rescoped)" || fail "retitle should update the title shown in the view"
rows | grep -q "$C .*🔴 blocked" || fail "retitle must not change the task's state"

# --- done: clears the stage, ids are never reused ------------------------
tasks done "$B" --raison "clos par le banc" >/dev/null
rows | grep -q "$B .*✅ done" || fail "$B should be done"
E="$(new_id "After a done" --owner dev-mono)"
jamais_vu "$E" "$A $B $C $D" || fail "a new id must never reuse an id already seen (got '$E')"

# --- sorting: running → blocked → pending → done, NEWEST FIRST within each -
# The running task heads the board; everything after it reads most-recent to
# oldest, so the rows that matter are the ones you land on. D (newer) therefore
# precedes A in the pending group — numerically before the P-<ULID> switch, by
# time after it (T-00000726: every id is CAPTURED, the order is still asserted).
tasks start "$E" --stage dev-mono >/dev/null
ORDER="$(tasks list | grep -oE '^\| T-[0-9A-HJKMNP-TV-Z]+' | tr -d '| ' | tr '\n' ' ')"
[ "$ORDER" = "$E $C $D $A $B " ] || fail "unexpected list order: $ORDER"

# --- the view is disposable: `render` rebuilds it from the store ---------
rm -f "$VIEW"
tasks render >/dev/null
[ -f "$VIEW" ] || fail "render should rebuild the view"
rows | grep -q "$E .*🟢 running" || fail "rebuilt view lost the running task"

# --- a hand-edited view is overwritten, never read -----------------------
printf '| T-999 | ghost | injected by hand | x | x | x |\n' >> "$VIEW"
tasks stage "$E" documenter >/dev/null
if rows | grep -q "T-999"; then fail "a row hand-added to the view survived a write"; fi
tasks list | grep -q "T-999" && fail "the view must never be read back as data"

# --- a malformed store FAILS LOUDLY instead of dropping a task ----------
cp "$STORE" "$TMP/good.json"
"$PY" - "$STORE" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d["tasks"][0]["state"] = "in-progress"   # outside the closed vocabulary
p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
PYEOF
if tasks done "$A" --raison "clos par le banc" 2>"$TMP/err"; then fail "an out-of-vocabulary state should exit non-zero"; fi
grep -q "expected one of" "$TMP/err" || fail "bad state should name the allowed values"
if grep -q "Traceback" "$TMP/err"; then fail "bad state leaked a traceback"; fi

# several running tasks WITHOUT any group are a legitimate board since
# T-01M5F7286N1EYGXAXA5244X86B (the T-00000188 refusal is retired): `list` reads it.
cp "$TMP/good.json" "$STORE"
"$PY" - "$STORE" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
for t in d["tasks"]:
    t["state"] = "running"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
PYEOF
tasks list >"$TMP/out2" 2>"$TMP/err2" || fail "several running tasks without a group must stay readable"
[ "$(grep -c '🟢 running' "$TMP/out2")" -ge 2 ] || fail "every running row should be listed"

# invalid JSON is reported, not swallowed
printf 'not json at all' > "$STORE"
if tasks list 2>"$TMP/err3"; then fail "invalid JSON should exit non-zero"; fi
grep -q "not valid JSON" "$TMP/err3" || fail "invalid JSON should say so"

# --- unknown id is a clean error, not a traceback ------------------------
cp "$TMP/good.json" "$STORE"
if tasks done T-999 --raison "clos par le banc" 2>"$TMP/err4"; then fail "unknown id should exit non-zero"; fi
grep -q "unknown task id" "$TMP/err4" || fail "unknown id should print a readable error"
if grep -q "Traceback" "$TMP/err4"; then fail "unknown id leaked a traceback"; fi

# --- mixed-width ids: legacy 3-digit + new 8-digit sort/mint correctly ---
cat > "$STORE" <<'JSON'
{
  "next_id": 6,
  "tasks": [
    {"id": "T-005", "state": "pending", "task": "legacy 3-digit task", "owner": "dev-mono", "stage": "", "updated": "2026-07-20"},
    {"id": "T-00000016", "state": "pending", "task": "new 8-digit task", "owner": "dev-mono", "stage": "", "updated": "2026-07-25"}
  ]
}
JSON
rm -f "$VIEW"
tasks render >/dev/null
ORDER2="$(tasks list | grep -oE '^\| T-[0-9A-HJKMNP-TV-Z]+' | tr -d '| ' | tr '\n' ' ')"
[ "$ORDER2" = "T-00000016 T-005 " ] || fail "mixed-width ids did not sort numerically: $ORDER2"
# R-BANCS (iii) : a PROPERTY of the id returned, never the counter's value (T-00000726). It reuses no id
# already seen, AND it sorts above every one of them — the newest pending heads its group, whether the
# allocator mints 8 digits (above the max, 16) or a P-<ULID> (above every legacy id).
N="$(new_id "after mixed-width store" --owner dev-mono)"
jamais_vu "$N" "T-005 T-00000016" || fail "allocation after a mixed-width store reused an id already seen (got '$N')"
ORDER3="$(tasks list | grep -oE '^\| T-[0-9A-HJKMNP-TV-Z]+' | tr -d '| ' | tr '\n' ' ')"
[ "$ORDER3" = "$N T-00000016 T-005 " ] \
  || fail "allocation after a mixed-width store must sort above every existing id: $ORDER3"

# --- numeric duplicate: T-005 and T-00000005 collide despite padding -----
cat > "$STORE" <<'JSON'
{
  "next_id": 6,
  "tasks": [
    {"id": "T-005", "state": "pending", "task": "legacy", "owner": "dev-mono", "stage": "", "updated": "2026-07-20"},
    {"id": "T-00000005", "state": "pending", "task": "same numeric id, different padding", "owner": "dev-mono", "stage": "", "updated": "2026-07-25"}
  ]
}
JSON
if tasks list 2>"$TMP/err5"; then fail "a numeric id collision (T-005 vs T-00000005) should exit non-zero"; fi
grep -q "numeric id collision" "$TMP/err5" || fail "numeric id collision should be explained"

# --- delete: removes one row; running needs --force; ids never reused ----
cp "$TMP/good.json" "$STORE"
tasks render >/dev/null
if tasks delete "$E" 2>"$TMP/err6"; then fail "deleting the running task without --force should fail"; fi
grep -q -- "--force" "$TMP/err6" || fail "delete refusal should point at --force"
tasks delete "$A" | grep -q "$A deleted" || fail "delete should confirm the id"
if rows | grep -q "$A "; then fail "deleted task still rendered in the view"; fi
tasks delete "$E" --force | grep -q "$E deleted" || fail "delete --force should remove the running task"
if tasks delete T-999 2>"$TMP/err7"; then fail "deleting an unknown id should exit non-zero"; fi
grep -q "unknown task id" "$TMP/err7" || fail "delete on an unknown id should print a readable error"
F="$(new_id "after delete" --owner dev-mono)"
jamais_vu "$F" "$A $B $C $D $E" || fail "a deleted id must never be reused (got '$F')"

# --- purge: bulk-removes by state; --before filters; --dry-run is a no-op -
cat > "$STORE" <<'JSON'
{
  "next_id": 10,
  "tasks": [
    {"id": "T-00000001", "state": "done", "task": "old done", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000002", "state": "done", "task": "fresh done", "owner": "dev-mono", "stage": "", "updated": "2026-07-20"},
    {"id": "T-00000003", "state": "done", "task": "done without a date", "owner": "dev-mono", "stage": ""},
    {"id": "T-00000004", "state": "pending", "task": "still live", "owner": "dev-mono", "stage": "", "updated": "2026-07-20"}
  ]
}
JSON
tasks purge --dry-run | grep -q "would remove 3" || fail "dry-run should count the 3 done rows"
# Les jugements lisent la LIGNE de tâche (`"id": …`), jamais l'id nu : depuis T-00001058 une
# suppression acquittée garde sa clé `sync_correlations` (`"board_task_id": "<id>"`, tombstoned),
# donc l'id nu reste dans le store après la purge (README, F5).
grep -q '"id": "T-00000001"' "$STORE" || fail "dry-run must not write the store"
tasks purge --before 2026-07-10 | grep -q "purged 1 task(s)" || fail "--before should purge only the old done row"
grep -q '"id": "T-00000001"' "$STORE" && fail "T-00000001 (updated before the cutoff) should be gone"
grep -q '"id": "T-00000002"' "$STORE" || fail "T-00000002 (updated after the cutoff) must survive"
grep -q '"id": "T-00000003"' "$STORE" || fail "a task without an updated stamp must survive a --before purge"
tasks purge | grep -q "purged 2 task(s)" || fail "bare purge should remove the remaining done rows"
tasks purge | grep -q "nothing to purge" || fail "an empty purge should say so"
grep -q '"id": "T-00000004"' "$STORE" || fail "purge must never touch non-done rows"
if tasks purge --state running 2>/dev/null; then fail "purge --state running must be rejected"; fi
if tasks purge --before not-a-date 2>"$TMP/err8"; then fail "a malformed --before should exit non-zero"; fi
grep -q "YYYY-MM-DD" "$TMP/err8" || fail "malformed --before should name the expected format"
P="$(new_id "after purge" --owner dev-mono)"
jamais_vu "$P" "T-00000001 T-00000002 T-00000003 T-00000004" \
  || fail "purge must not rewind id allocation: an id already seen came back (got '$P')"

# --- unblock: the return path to pending (T-00000095) --------------------
# Le store est réécrit à la main ci-dessus par le bloc purge, donc on repart
# d'un état nommé plutôt que d'hériter des lignes précédentes.
cat > "$STORE" <<'JSON'
{
  "next_id": 20,
  "tasks": [
    {"id": "T-00000011", "state": "blocked", "task": "waiting pilot", "owner": "dev-mono", "stage": "pilot decision class-3", "updated": "2026-07-01"},
    {"id": "T-00000012", "state": "running", "task": "en cours", "owner": "dev-mono", "stage": "dev-mono", "updated": "2026-07-01"},
    {"id": "T-00000013", "state": "pending", "task": "en file", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000014", "state": "done", "task": "close", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"}
  ]
}
JSON
tasks unblock T-00000011 | grep -q "T-00000011 → pending" || fail "unblock should confirm the new state"
rows | grep -q "T-00000011 .*⚪ pending" || fail "unblock should land the task in pending"
rows | grep -q "T-00000011 .*pilot decision class-3" && fail "unblock must clear the blocking reason from stage"
grep -q '"updated": "2026-07-01"' "$STORE" && [ "$(grep -c '"updated": "2026-07-01"' "$STORE")" = "3" ] \
  || fail "unblock should stamp updated on the unblocked task only"

# CONTRÔLES NÉGATIFS — sans eux, un `unblock` qui accepterait n'importe quel
# état passerait le cas ci-dessus. Le dangereux est `running` : une démotion
# silencieuse de la seule tâche active est exactement ce que l'invariant
# l'invariant d'exécution existe pour empêcher.
for pair in "T-00000012 running" "T-00000013 pending" "T-00000014 done"; do
  set -- $pair
  if tasks unblock "$1" 2>"$TMP/err9"; then fail "unblock on a $2 task must exit non-zero"; fi
  grep -q "not blocked" "$TMP/err9" || fail "unblock on a $2 task should say it is not blocked"
  grep -q "$2" "$TMP/err9" || fail "the error should name the state it found ($2)"
done
rows | grep -q "T-00000012 .*🟢 running" || fail "a refused unblock must leave the running task untouched"
grep -q '"stage": "dev-mono"' "$STORE" || fail "a refused unblock must not clear anything"

# unblock sur un id inconnu : erreur propre, pas de traceback
if tasks unblock T-99999999 2>"$TMP/err10"; then fail "unblock on an unknown id must exit non-zero"; fi
grep -q "T-99999999" "$TMP/err10" || fail "the unknown-id error should name the id"

# --- list --task / --state : les filtres (T-00000103) --------------------
# Le board fait 34 tâches : `list` nu les déverse toutes, donc l'agent qui veut
# UNE tâche payait le board entier ou parsait le JSON à la main. Store nommé,
# rejoué à la main, plutôt qu'hérité des blocs précédents.
#
# $TODAY est capturé UNE SEULE FOIS et réutilisé dans la fixture ET dans le
# golden (T-00000183). La tâche running doit être FRAÎCHE, sinon l'alerte de
# souffrance s'insère en ligne 2 et le golden vire rouge sans régression — mais
# deux `$(date +%F)` séparés se contrediraient si l'horloge passe minuit entre
# les deux, et ce flake-là est indétectable. Une capture, deux emplois.
TODAY="$(date +%F)"
cat > "$STORE" <<JSON
{
  "next_id": 10,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "en cours", "owner": "dev-mono", "stage": "security-code-review", "updated": "$TODAY"},
    {"id": "T-00000002", "state": "blocked", "task": "attend le pilote", "owner": "planner", "stage": "pilot decision class-3", "updated": "2026-08-02"},
    {"id": "T-00000003", "state": "pending", "task": "en file", "owner": "dev-multi", "stage": "", "updated": "2026-08-03"},
    {"id": "T-00000004", "state": "done", "task": "close", "owner": "dev-mono", "stage": "", "updated": "2026-08-04"}
  ]
}
JSON

# (d) LE CONTRAT LE PLUS IMPORTANT : `list` nu ne bouge pas d'un octet. Les
# board-reporter parsent `list --json` et le nu reste le REPLI des hooks
# SessionStart : depuis T-00000834 ils injectent `list --session` (pending
# bornées, coupe annoncée) et retombent sur le nu si la vue manque —
# session-start.sh par `||`, les session_context.py de Codex et Gemini par
# `getattr(mod, "render_session_board", None) or mod.render_list`.
# La référence ci-dessous est la sortie MESURÉE avant l'ajout des filtres —
# golden littéral, donc une régression future devient rouge ici. Le contrat a
# une exception NOMMÉE depuis T-00000183 : une ligne d'alerte quand la tâche
# running est en souffrance. Le board, lui, ne bouge toujours pas d'un octet —
# c'est ce que ce golden (running fraîche, donc aucune alerte) mesure.
#
# LA LARGEUR DE LA COLONNE `id` EST LUE DANS LE CODE, et c'est la seule (T-00000726) : la bascule
# `P-<ULID>` (C2) la porte de 10 à 28 pour qu'un id NEUF tienne entier (`WIDTHS`, tasks.py), et ce banc
# doit rester vert avant ET après elle. Toutes les autres colonnes, l'ordre et le contenu restent
# LITTÉRAUX ; la largeur elle-même a son témoin à C2 (1(h)), pas ici.
WID="$("$PY" -c 'import importlib.util as u, sys; s = u.spec_from_file_location("tasks_largeur", sys.argv[1]); m = u.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m); print(m.WIDTHS["id"])' "$SCRIPT")"
[ -n "$WID" ] || fail "could not read WIDTHS[id] from tasks.py"
idc() { printf "%-${WID}s" "$1"; }
IDRULE="$(printf "%-$((WID + 2))s" "" | tr ' ' '-')"
cat > "$TMP/list-bare.golden" <<GOLDEN
## TASK BOARD
| $(idc id) | state      | task                                         | owner        | stage                  | updated    |
|$IDRULE|------------|----------------------------------------------|--------------|------------------------|------------|
| $(idc T-00000001) | 🟢 running | en cours                                     | dev-mono     | security-code-review   | $TODAY |
| $(idc T-00000002) | 🔴 blocked | attend le pilote                             | planner      | pilot decision class-3 | 2026-08-02 |
| $(idc T-00000003) | ⚪ pending | en file                                      | dev-multi    | —                      | 2026-08-03 |
| $(idc T-00000004) | ✅ done    | close                                        | dev-mono     | —                      | 2026-08-04 |
GOLDEN
# `tr -d '\r'` sur les DEUX côtés, et pas pour se donner du mou : tasks.py ne
# passe pas `newline="\n"` à reconfigure() (specs.py et ledger.py le font), donc
# son stdout sort en CRLF sur Windows et en LF ailleurs. MESURÉ identique à HEAD
# avant/après ce changement, donc la fin de ligne n'est pas ce qu'on teste ici —
# la colonne, la largeur et l'ordre le sont. Cf. follow-up parité newline.
tasks list | tr -d '\r' > "$TMP/list-bare.out"
tr -d '\r' < "$TMP/list-bare.golden" > "$TMP/list-bare.golden.lf"
diff "$TMP/list-bare.golden.lf" "$TMP/list-bare.out" >/dev/null \
  || fail "a bare \`list\` no longer matches its pre-filter reference output$(printf '\n'; diff "$TMP/list-bare.golden.lf" "$TMP/list-bare.out")"

# (a) --task rend CETTE tâche et pas les autres, tous champs, non tronqués
tasks list --task T-00000002 > "$TMP/one.out" || fail "list --task should exit 0"
grep -q "^## TASK T-00000002$" "$TMP/one.out" || fail "list --task should head the detail block with the id"
grep -q "pilot decision class-3" "$TMP/one.out" || fail "list --task should show the stage field"
grep -q "attend le pilote" "$TMP/one.out" || fail "list --task should show the title"
for other in T-00000001 T-00000003 T-00000004; do
  grep -q "$other" "$TMP/one.out" && fail "list --task T-00000002 leaked $other"
done
# tous ses champs : chaque clé du store est présente, aucune avalée
for field in id state task owner stage updated; do
  grep -q "^$field " "$TMP/one.out" || fail "list --task should print the '$field' field"
done
# non tronqué, là où la table coupe à 44 caractères
tasks retitle T-00000002 "un titre deliberement tres long qui depasse largement la largeur de colonne de la vue" >/dev/null
tasks list --task T-00000002 | grep -q "largeur de colonne de la vue" \
  || fail "list --task must print the title untruncated, unlike the table view"
tasks list --task T-00000002 | grep -q "…" && fail "list --task must not truncate any field"
tasks retitle T-00000002 "attend le pilote" >/dev/null

# formes courtes : alignées sur numeric_id (le primitif d'id déjà utilisé pour
# le tri, l'allocation et la détection de collision), jamais une 2e convention
for short in T-00000002 T-2 2; do
  tasks list --task "$short" | grep -q "^## TASK T-00000002$" \
    || fail "list --task $short should resolve to T-00000002"
done
# un id inconnu reste une ERREUR (comme tout autre verbe), pas un vide
if tasks list --task T-999 2>"$TMP/errf1"; then fail "list --task on an unknown id should exit non-zero"; fi
grep -q "unknown task id" "$TMP/errf1" || fail "list --task on an unknown id should say so"
if grep -q "Traceback" "$TMP/errf1"; then fail "list --task on an unknown id leaked a traceback"; fi

# (b) --state ne rend que les tâches de cet état
tasks list --state blocked > "$TMP/blocked.out" || fail "list --state should exit 0"
grep -q "T-00000002" "$TMP/blocked.out" || fail "list --state blocked should show the blocked task"
for other in T-00000001 T-00000003 T-00000004; do
  grep -q "$other" "$TMP/blocked.out" && fail "list --state blocked leaked $other"
done
# le compte est affiché : il prouve qu'aucune ligne n'a été silencieusement coupée
grep -q "1 task)" "$TMP/blocked.out" || fail "a filtered list should announce how many tasks matched"
tasks list --state pending | grep -q "T-00000003" || fail "list --state pending should show the pending task"
tasks list --state running | grep -q "T-00000001" || fail "list --state running should show the running task"

# (c) les deux combinables
tasks list --task 2 --state blocked | grep -q "^## TASK T-00000002$" \
  || fail "--task and --state together should return the task when both match"

# (f) un filtre sans résultat le DIT — un tableau vide se lirait comme un board vide
tasks list --task 2 --state running > "$TMP/void.out" || fail "an empty filter is not an error"
grep -q "no task matching task=2, state=running" "$TMP/void.out" \
  || fail "an empty filter must name what was asked, not render a void table"
if grep -q '^| T-' "$TMP/void.out"; then fail "an empty filter must not render any row"; fi
tasks done T-00000001 --raison "clos par le banc" >/dev/null
tasks done T-00000002 --raison "clos par le banc" >/dev/null
tasks done T-00000003 --raison "clos par le banc" >/dev/null
tasks list --state blocked | grep -q "no task matching state=blocked" \
  || fail "a state filter matching nothing must say so"

# (e) --state hors vocabulaire : erreur d'USAGE, jamais un résultat vide
if tasks list --state in-progress 2>"$TMP/errf2"; then fail "an out-of-vocabulary --state must exit non-zero"; fi
grep -q "invalid choice" "$TMP/errf2" || fail "an unknown --state should be reported as an invalid choice"
for s in pending running blocked done; do
  grep -q "$s" "$TMP/errf2" || fail "the --state error should name the allowed value '$s'"
done
grep -q "no task matching" "$TMP/errf2" && fail "an unknown --state must not degrade into an empty result"
# et le garde-fou côté fonction, pas seulement côté argparse
"$PY" - "$HERE/tasks.py" "$TMP" <<'PYEOF' || exit 1
import importlib.util, sys
spec = importlib.util.spec_from_file_location("tasks", sys.argv[1])
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
try:
    mod.filter_tasks(mod.load(sys.argv[2]), state="in-progress")
except mod.BoardError as exc:
    assert "expected one of" in str(exc), exc
else:
    print("FAIL: filter_tasks accepted a state outside the closed vocabulary"); sys.exit(1)
PYEOF

# --- alerte : la tâche running en souffrance le DIT (T-00000183) ----------
# Une running oubliée ne se signalait nulle part : l'invariant garantit qu'elle
# est UNE, jamais qu'elle avance. L'alerte voyage sur le `list` nu parce que les
# hooks SessionStart des trois hôtes lisent déjà cette sortie — zéro hook touché.
# La date est calculée par python, pas par `date -d` (absent/incompatible selon
# les plateformes : BSD, Git-Bash), et elle est FRANCHEMENT au-delà du seuil.
STALE8="$("$PY" -c 'import datetime; print((datetime.date.today() - datetime.timedelta(days=8)).isoformat())')"
cat > "$STORE" <<JSON
{
  "next_id": 9,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "oubliee", "owner": "dev-mono", "stage": "dev-mono", "updated": "$STALE8"},
    {"id": "T-00000002", "state": "pending", "task": "en file", "owner": "dev-mono", "stage": "", "updated": "$STALE8"}
  ]
}
JSON
tasks list > "$TMP/stale.out" || fail "a stale running task must not make list exit non-zero"
grep -q "RUNNING STALE" "$TMP/stale.out" || fail "a running task 8 days old must raise the stale alert on a bare list"
grep -q "T-00000001" "$TMP/stale.out" || fail "the stale alert must name the task"
# En LIGNE 2 : sous l'en-tête, au-dessus du tableau — un hook qui coupe la tête
# de la sortie doit la voir, et le board reste intact en dessous.
[ "$(sed -n '1p' "$TMP/stale.out" | tr -d '\r')" = "## TASK BOARD" ] || fail "the header must stay line 1"
sed -n '2p' "$TMP/stale.out" | grep -q "RUNNING STALE" || fail "the stale alert must be line 2, right under the header"
sed -n '3p' "$TMP/stale.out" | grep -q '^| id ' || fail "the table must still follow the alert, unchanged"
# --json est parsé par des machines : jamais de prose dedans (ni sur stdout).
tasks list --json > "$TMP/stale.json" 2>"$TMP/stale.json.err" || fail "list --json should exit 0 with a stale running task"
grep -q "RUNNING STALE" "$TMP/stale.json" && fail "list --json must never carry the stale alert"
grep -q "RUNNING STALE" "$TMP/stale.json.err" && fail "list --json must not leak the stale alert on stderr either"
"$PY" -c 'import json,sys; json.load(open(sys.argv[1],encoding="utf-8"))' "$TMP/stale.json" \
  || fail "list --json must stay parseable when the running task is stale"
# Les lectures étroites non plus : un filtre est une question précise.
tasks list --state running | grep -q "RUNNING STALE" && fail "a filtered list must not carry the stale alert"
tasks --statusline | grep -q "RUNNING STALE" && fail "the statusline must not carry the stale alert"
# Un `updated` illisible AVERTIT au lieu de planter : session-start.sh lit tout
# code de sortie non nul comme un board cassé.
cat > "$STORE" <<'JSON'
{
  "next_id": 9,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "date pourrie", "owner": "dev-mono", "stage": "dev-mono", "updated": "hier"}
  ]
}
JSON
tasks list > "$TMP/badstamp.out" 2>"$TMP/badstamp.err" || fail "an unreadable updated must not make list exit non-zero"
grep -q "Traceback" "$TMP/badstamp.err" && fail "an unreadable updated leaked a traceback"
grep -q "T-00000001" "$TMP/badstamp.out" || fail "an unreadable updated must still warn and name the task"

# --- un filtre explicite ne tronque PAS le backlog done -------------------
# MAX_DONE_SHOWN est une borne de DIGEST pour le board entier. Rendre 3 lignes
# sur 6 à qui demande `--state done` serait la troncature silencieuse que le kit
# interdit — l'inverse du contrat (d), et c'est pourquoi les deux coexistent.
cat > "$STORE" <<'JSON'
{
  "next_id": 9,
  "tasks": [
    {"id": "T-00000001", "state": "done", "task": "d1", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000002", "state": "done", "task": "d2", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000003", "state": "done", "task": "d3", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000004", "state": "done", "task": "d4", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000005", "state": "done", "task": "d5", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000006", "state": "done", "task": "d6", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"}
  ]
}
JSON
[ "$(tasks list | grep -c '^| T-')" = "3" ] || fail "a bare list must keep the 3-row done digest cap"
[ "$(tasks list --state done | grep -c '^| T-')" = "6" ] || fail "an explicit --state done must show all 6 done rows, not the digest cap"
tasks list --state done | grep -q "6 tasks)" || fail "the filtered header should count all 6 matches"

# --- --json : stdout reste parsable, l'absence part sur stderr ------------
# Les board-reporter des quatre hôtes parsent `list --json` : une phrase en
# clair sur stdout casserait le parseur, un stdout muet cacherait l'absence.
[ "$(tasks list --json | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')" = "3" ] \
  || fail "a bare list --json must stay parseable and keep the done cap"
[ "$(tasks list --json --state done | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')" = "6" ] \
  || fail "a filtered list --json must return every match"
tasks list --json --state running 1>"$TMP/void.json" 2>"$TMP/void.err" || fail "an empty --json filter is not an error"
"$PY" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); assert d == [], d' "$TMP/void.json" \
  || fail "an empty --json filter must print a valid, empty JSON array on stdout"
grep -q "no task matching state=running" "$TMP/void.err" \
  || fail "an empty --json filter must announce the absence on stderr"

# --- block/stage : un verbe qui ANNOTE ne doit rien détruire (T-00000103) --
# Mesuré avant correction : `block T-NNN` sans --note écrivait "" dans stage,
# donc la STAGE en vol était effacée et la ligne bloquée n'affichait plus
# aucune raison — un état que le contrat documenté ne peut pas exprimer
# (AGENTS.md : stage = l'étape en vol, OU la raison du blocage si blocked).
cat > "$STORE" <<'JSON'
{
  "next_id": 9,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "en cours", "owner": "dev-mono", "stage": "security-code-review", "updated": "2026-08-01"},
    {"id": "T-00000002", "state": "pending", "task": "en file", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"}
  ]
}
JSON
OUT="$(tasks block T-00000001)"
grep -q '"stage": "security-code-review"' "$STORE" \
  || fail "block without --note must PRESERVE the pipeline stage, not wipe it"
case "$OUT" in
  "TASKS: T-00000001 → blocked"*) ;;
  *) fail "block must keep its TASKS: <id> → blocked prefix; got: $OUT" ;;
esac
case "$OUT" in
  *"no reason recorded"*) ;;
  *) fail "block without --note must SAY that no reason was recorded; got: $OUT" ;;
esac
case "$OUT" in
  *"security-code-review"*) ;;
  *) fail "block without --note should name the stage it kept; got: $OUT" ;;
esac
rows | grep -q "T-00000001 .*🔴 blocked.*security-code-review" \
  || fail "the blocked row should still show the stage it was at"

# stage déjà vide : RIEN à préserver, ni note, ni lien — le cas réellement MUET,
# désormais REFUSÉ (2026-09-12). Il était auparavant ÉCRIT, avec un simple
# « no reason recorded » dans la sortie : un signalement qu'on peut ignorer n'a
# jamais rien empêché, et la ligne bloquée qui en sortait ne portait AUCUNE
# information — rien ne la distinguait d'une ligne en attente, et le contrat
# documenté ne sait même pas exprimer cet état. Les deux autres sources
# d'explication restent admises et sont éprouvées juste au-dessus (étape en vol
# PRÉSERVÉE) et juste en dessous (`--note`), plus le lien `--on` plus loin.
if OUT2="$(tasks block T-00000002 2>"$TMP/errmuet")"; then
  fail "un block MUET — ni note, ni lien, ni etape a preserver — doit etre REFUSE; got: $OUT2"
fi
grep -q 'exige une explication' "$TMP/errmuet" \
  || fail "le refus d'un block muet doit NOMMER ce qui manque; got: $(cat "$TMP/errmuet")"
grep -q -- '--note' "$TMP/errmuet" && grep -q -- '--on' "$TMP/errmuet" \
  || fail "le refus doit pointer les DEUX remedes; got: $(cat "$TMP/errmuet")"
if grep -q "Traceback" "$TMP/errmuet"; then fail "le refus d'un block muet a fuite une trace"; fi
# ET LE REFUS N'A RIEN ÉCRIT — un refus qui laisse l'état à moitié changé serait
# pire que pas de refus du tout.
rows | grep -q "T-00000002 .*pending" \
  || fail "un block refuse ne doit RIEN avoir ecrit; T-00000002 n est plus pending"

# LE CHEMIN DOCUMENTÉ NE BOUGE PAS : `block --note` rend exactement ce qu'il
# rendait (les skills kickoff des quatre hôtes le pilotent).
[ "$(tasks block T-00000001 --note "pilot decision class-3")" = "TASKS: T-00000001 → blocked" ] \
  || fail "block --note must report exactly what it always reported"
grep -q '"stage": "pilot decision class-3"' "$STORE" || fail "block --note must record its reason in stage"
# et l'invariant + le retour par unblock restent intacts
[ "$(rows | grep -c '🟢 running')" = "0" ] || fail "blocking the running task should leave no running row"
tasks unblock T-00000001 | grep -q "T-00000001 → pending" || fail "unblock should still bring a blocked task home"
grep -q '"stage": "pilot decision class-3"' "$STORE" && fail "unblock must still clear the blocking reason"

# --- reassign : l'owner devient réattribuable (T-00000173) ----------------
# Avant, `owner` était en écriture unique (fixé par `new --owner`), donc une
# tâche qui change de nature EN VOL n'avait qu'un endroit pour noter son nouveau
# responsable : le TITRE, qui devenait un fourre-tout (mesuré chez un projet
# consommateur). Store nommé, les 4 états présents, dates passées pour que le
# tampon `updated` soit observable.
TODAY="$("$PY" -c 'import datetime; print(datetime.date.today().isoformat())')"
cat > "$STORE" <<'JSON'
{
  "next_id": 10,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "ecran login", "owner": "dev-mono", "stage": "dev-mono", "updated": "2026-07-01"},
    {"id": "T-00000002", "state": "blocked", "task": "attend le pilote", "owner": "dev-mono", "stage": "pilot decision class-3", "updated": "2026-07-01"},
    {"id": "T-00000003", "state": "pending", "task": "en file", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000004", "state": "done", "task": "close", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"}
  ]
}
JSON
tasks render >/dev/null

# (a) STATE-FREE : marche dans CHAQUE état, `running` INCLUS — c'est le cas
# d'usage principal (un écran cru technique devient du design).
for pair in "T-00000001 running" "T-00000002 blocked" "T-00000003 pending" "T-00000004 done"; do
  set -- $pair
  tasks reassign "$1" planner | grep -q "$1 reassigned to planner" \
    || fail "reassign on a $2 task should confirm the id and the new owner"
done
[ "$(grep -c '"owner": "planner"' "$STORE")" = "4" ] || fail "the 4 reassigned tasks should all be owned by planner"
grep -q '"owner": "dev-mono"' "$STORE" && fail "no task should still carry its previous owner"

# (b) L'ÉTAT ET L'INVARIANT NE BOUGENT PAS : reassign n'écrit jamais `state`.
[ "$(rows | grep -c '🟢 running')" = "1" ] || fail "reassign must leave exactly one running row"
rows | grep -q "T-00000001 .*🟢 running" || fail "reassigning the running task must not change its state"
rows | grep -q "T-00000002 .*🔴 blocked" || fail "reassign must not change a blocked state"
rows | grep -q "T-00000003 .*⚪ pending" || fail "reassign must not change a pending state"
rows | grep -q "T-00000004 .*✅ done" || fail "reassign must not change a done state"
grep -q '"stage": "pilot decision class-3"' "$STORE" || fail "reassign must not touch the stage column"

# (c) `updated` est tamponné...
[ "$(grep -c "\"updated\": \"$TODAY\"" "$STORE")" = "4" ] || fail "reassign should stamp updated on the reassigned task"
grep -q '"updated": "2026-07-01"' "$STORE" && fail "no reassigned task should keep its old updated stamp"

# ...sur la tâche réattribuée SEULEMENT : une réattribution ne date pas ses voisines.
"$PY" - "$STORE" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
for t in d["tasks"]:
    t["updated"] = "2026-07-01"          # on repart d'une base entièrement datée
    if t["id"] == "T-00000002":
        t["owner"] = "dev-mono"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
PYEOF
tasks reassign T-00000002 frontend-fidelity >/dev/null
[ "$(grep -c '"updated": "2026-07-01"' "$STORE")" = "3" ] \
  || fail "reassign should stamp updated on the reassigned task only"

# (d) LA VUE RENDUE reflète le nouveau responsable. La colonne owner fait 12,
# donc un nom long y est TRONQUÉ comme un titre, et reste entier dans
# `list --task` — c'est le contrat de la table, pas une perte.
rows | grep -q "T-00000002 .*frontend-fi…" || fail "the view should show the new owner (truncated at the column width)"
tasks list --task T-00000002 | grep -q "^owner .*frontend-fidelity" \
  || fail "list --task should show the new owner untruncated"

# (e) OWNER VIDE = retour à « non attribué », appel légitime et EXPLICITE
# (argparse passe un positionnel vide tel quel — mesuré), pas une erreur
# d'usage. La vue le rend `—`, exactement comme un `new` sans --owner.
tasks reassign T-00000002 "" | grep -q "owner cleared" \
  || fail 'reassign with an empty owner should SAY the field was cleared'
"$PY" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); t=[x for x in d["tasks"] if x["id"]=="T-00000002"][0]; assert t["owner"]=="", t' "$STORE" \
  || fail "an empty reassign should store an empty owner"
rows | grep -q "T-00000002 .*🔴 blocked.*—" || fail "a cleared owner should render as — in the view"

# (f) id inconnu : erreur BRUYANTE, comme tout autre verbe
if tasks reassign T-99999999 planner 2>"$TMP/errr1"; then fail "reassign on an unknown id must exit non-zero"; fi
grep -q "unknown task id" "$TMP/errr1" || fail "reassign on an unknown id should print a readable error"
grep -q "T-99999999" "$TMP/errr1" || fail "the unknown-id error should name the id"
if grep -q "Traceback" "$TMP/errr1"; then fail "reassign on an unknown id leaked a traceback"; fi
# pas de forme courte pour un verbe d'ÉCRITURE : `reassign 2` ne doit pas
# atteindre T-00000002 par chance numérique (find exact, comme done/delete).
if tasks reassign 2 planner 2>/dev/null; then fail "a write verb must not resolve the short form 2"; fi

# (g) l'owner n'est PAS validé contre une liste d'agents connus, VOLONTAIREMENT :
# `new --owner` prend du texte libre, donc refuser ici créerait une asymétrie où
# la même valeur passe à la création et échoue à la réattribution.
tasks new "texte libre" --owner "n-importe-quoi" >/dev/null
tasks reassign T-00000003 "n-importe-quoi" | grep -q "reassigned to n-importe-quoi" \
  || fail "reassign must accept the same free-text owner that new --owner accepts"

# --- chantier : le regroupement thématique en texte libre (T-00000184) ----
# Le tableau ne dit pas QUELLES tâches forment un même bloc de travail. Le champ
# est OPTIONNEL et ABSENT par défaut : la fixture porte donc une entrée LEGACY
# sans la clé, et chaque lecture ci-dessous doit la traiter comme « sans
# chantier » au lieu de casser. Aucune colonne n'est ajoutée à la table.
cat > "$STORE" <<'JSON'
{
  "next_id": 20,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "login", "owner": "dev-mono", "stage": "dev-mono", "updated": "2026-07-01", "chantier": "auth"},
    {"id": "T-00000002", "state": "pending", "task": "token refresh", "owner": "dev-mono", "stage": "", "updated": "2026-07-01", "chantier": "auth"},
    {"id": "T-00000003", "state": "pending", "task": "facturation", "owner": "dev-mono", "stage": "", "updated": "2026-07-01", "chantier": "billing"},
    {"id": "T-00000004", "state": "pending", "task": "sans groupe", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000005", "state": "done", "task": "mot de passe oublie", "owner": "dev-mono", "stage": "", "updated": "2026-07-01", "chantier": "auth"}
  ]
}
JSON
tasks render >/dev/null

# (a) AUCUNE COLONNE EN PLUS : la table (et donc la vue générée, et donc le
# `list` nu que les hooks SessionStart des trois hôtes lisent) ne bouge pas.
tasks list | grep '^| id ' | grep -q "chantier" && fail "chantier must NOT become a table column"
grep -q "chantier" "$VIEW" && fail "the generated view must not mention chantier"
# ...mais `list --task` le montre, gratuitement (format_detail imprime toute clé
# hors FIELDS), et une tâche SANS la clé n'affiche simplement pas la ligne.
tasks list --task T-00000001 | grep -q "^chantier .*auth" || fail "list --task should show the chantier untruncated"
tasks list --task T-00000004 | grep -q "chantier" && fail "an ungrouped task should not fake a chantier line"

# (b) FILTRE : --chantier X compte et n'emporte que son groupe.
tasks list --chantier auth > "$TMP/ch.out" || fail "list --chantier should exit 0"
[ "$(grep -c '^| T-' "$TMP/ch.out")" = "3" ] || fail "list --chantier auth should show its 3 tasks"
grep -q "chantier=auth (3 tasks)" "$TMP/ch.out" || fail "the filtered header should echo the filter and count"
for other in T-00000003 T-00000004; do
  grep -q "$other" "$TMP/ch.out" && fail "list --chantier auth leaked $other"
done
# le cap `done` ne s'applique pas à un filtre explicite : T-00000005 est là.
grep -q "T-00000005" "$TMP/ch.out" || fail "an explicit --chantier filter must not drop a done row"

# (c) --chantier "" = LES TÂCHES SANS CHANTIER, symétrique de `regroup <id> ""`.
# C'est la seule lecture qui atteint l'entrée legacy, d'où la vérification que
# la clé absente et la chaîne vide sont bien le MÊME ensemble.
tasks list --chantier "" > "$TMP/ch0.out" || fail 'list --chantier "" should exit 0'
[ "$(grep -c '^| T-' "$TMP/ch0.out")" = "1" ] || fail 'list --chantier "" should show the one ungrouped task'
grep -q "T-00000004" "$TMP/ch0.out" || fail 'list --chantier "" should show the legacy task that has no key'
grep -q "sans chantier" "$TMP/ch0.out" || fail 'an empty --chantier must echo back as readable words, not "chantier="'
# texte libre : un groupe inconnu ne matche rien, et le DIT (pas un tableau vide)
tasks list --chantier "jamais vu" | grep -q "no task matching chantier=jamais vu" \
  || fail "an unknown chantier should name what was asked instead of showing an empty board"

# (d) --group : sections alphabétiques, « (sans chantier) » EN DERNIER.
SECTIONS="$(tasks list --group | grep '^### ' | tr '\n' '/')"
[ "$SECTIONS" = "### auth (3)/### billing (1)/### (sans chantier) (1)/" ] \
  || fail "unexpected sections: $SECTIONS"
tasks list --group | grep -q "T-00000004" || fail "the legacy task must appear in the (sans chantier) section"

# (e) --group --state : ON FILTRE PUIS ON SECTIONNE (le cas qui motive le flag :
# « les pending par chantier »). La combinaison est AUTORISÉE — c'est aussi la
# preuve de non-vacuité des refus testés juste en dessous.
tasks list --group --state pending > "$TMP/gp.out" || fail "list --group --state should exit 0"
SECTIONS2="$(grep '^### ' "$TMP/gp.out" | tr '\n' '/')"
[ "$SECTIONS2" = "### auth (1)/### billing (1)/### (sans chantier) (1)/" ] \
  || fail "--group --state should filter THEN section; got: $SECTIONS2"
grep -q "T-00000001" "$TMP/gp.out" && fail "--group --state pending leaked the running task"
grep -q "3 tasks" "$TMP/gp.out" || fail "--group --state should count the filtered set"

# (f) LES COMBINAISONS SANS SENS SONT REFUSÉES, JAMAIS IGNORÉES : un drapeau
# silencieusement jeté fait lire la sortie comme la réponse à la question posée.
for bad in "--json" "--task T-00000001"; do
  if tasks list --group $bad 2>"$TMP/errg"; then fail "list --group $bad must exit non-zero"; fi
  grep -q "does not combine with" "$TMP/errg" || fail "list --group $bad should explain the refusal"
  if grep -q "Traceback" "$TMP/errg"; then fail "list --group $bad leaked a traceback"; fi
done
if tasks list --group --chantier auth 2>"$TMP/errg2"; then fail "list --group --chantier must exit non-zero"; fi
grep -q "does not combine with --chantier" "$TMP/errg2" || fail "the refusal should name --chantier"
grep -q -- "--chantier alone" "$TMP/errg2" || fail "the refusal should point at the flag that answers the question"

# (g) regroup : STATE-FREE, `running` INCLUS — on regroupe justement pendant que
# le travail est en vol. Rien n'écrit `state`, donc l'invariant est hors de portée.
TODAY2="$("$PY" -c 'import datetime; print(datetime.date.today().isoformat())')"
for pair in "T-00000001 running" "T-00000003 pending" "T-00000005 done"; do
  set -- $pair
  tasks regroup "$1" "paiement" | grep -q "$1 regrouped under paiement" \
    || fail "regroup on a $2 task should confirm the id and the new chantier"
done
[ "$(rows | grep -c '🟢 running')" = "1" ] || fail "regroup must leave exactly one running row"
rows | grep -q "T-00000001 .*🟢 running" || fail "regrouping the running task must not change its state"
rows | grep -q "T-00000005 .*✅ done" || fail "regroup must not change a done state"
grep -q '"stage": "dev-mono"' "$STORE" || fail "regroup must not touch the stage column"
[ "$(grep -c "\"updated\": \"$TODAY2\"" "$STORE")" = "3" ] || fail "regroup should stamp updated on the regrouped tasks only"

# (h) chantier VIDE = dégroupement, et la sortie LE DIT (pas une phrase qui
# s'arrête après « under »). La clé est retirée : « sans chantier » garde UNE
# seule forme stockée, celle de l'entrée legacy.
tasks regroup T-00000001 "" | grep -q "chantier cleared" \
  || fail 'regroup with an empty chantier should SAY the field was cleared'
"$PY" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); t=[x for x in d["tasks"] if x["id"]=="T-00000001"][0]; assert "chantier" not in t, t' "$STORE" \
  || fail 'an empty regroup should remove the key, not store ""'
tasks list --chantier "" | grep -q "T-00000001" || fail "an un-grouped task should join the ungrouped filter"
rows | grep -q "T-00000001 .*🟢 running" || fail "un-grouping must not change the task's state"

# (i) id inconnu : erreur BRUYANTE, et pas de forme courte pour un verbe d'ÉCRITURE
if tasks regroup T-99999999 auth 2>"$TMP/errg3"; then fail "regroup on an unknown id must exit non-zero"; fi
grep -q "unknown task id" "$TMP/errg3" || fail "regroup on an unknown id should print a readable error"
if tasks regroup 3 auth 2>/dev/null; then fail "a write verb must not resolve the short form 3"; fi

# (j) texte libre NON VALIDÉ, par symétrie avec la création : refuser ici une
# valeur que `new --chantier` accepte rendrait une tâche impossible à classer.
X="$(new_id "cree avec chantier" --owner planner --chantier "n-importe-quoi")"
[ -n "$X" ] || fail "new --chantier should still allocate normally"
tasks regroup "$X" "encore n'importe quoi" | grep -q "regrouped under encore n'importe quoi" \
  || fail "regroup must accept the same free text new --chantier accepts"
# ...et un `new` SANS --chantier n'écrit pas la clé du tout (id CAPTURÉ, jamais prédit : T-00000726)
Y="$(new_id "cree sans chantier" --owner planner)"
[ -n "$Y" ] || fail "new without --chantier should allocate"
"$PY" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); t=[x for x in d["tasks"] if x["id"]==sys.argv[2]][0]; assert "chantier" not in t, t' "$STORE" "$Y" \
  || fail "new without --chantier must not write the key"

# --- blocked_on : le lien MACHINE entre tâches + libération auto (T-00000182) --
# Une dépendance vivait jusqu'ici dans le TEXTE de `stage`, que rien ne sait
# lire : le bloqueur se fermait, ses dépendantes restaient rouges jusqu'à ce que
# quelqu'un s'en souvienne. Fixture neuve, indépendante des sections au-dessus.
cat > "$STORE" <<'JSON'
{
  "next_id": 10,
  "tasks": [
    {"id": "T-00000001", "state": "pending", "task": "socle auth", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000002", "state": "pending", "task": "ecran login", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"},
    {"id": "T-00000003", "state": "pending", "task": "doc auth", "owner": "documenter", "stage": "documenter", "updated": "2026-07-01"},
    {"id": "T-00000004", "state": "pending", "task": "autre chantier", "owner": "dev-mono", "stage": "", "updated": "2026-07-01"}
  ]
}
JSON
tasks render >/dev/null
has_link() { "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); t=[x for x in d["tasks"] if x["id"]==sys.argv[2]][0]; assert t.get("blocked_on")==(sys.argv[3] or None), t' "$STORE" "$1" "$2"; }

# (a) --note ET --on se composent : la prose pour l'humain, le lien pour la
# machine. Le message annonce le lien SANS perdre son préfixe historique.
tasks block T-00000002 --on T-00000001 --note "attente pilote aussi" > "$TMP/b1.out" || fail "block --on --note should exit 0"
grep -q "^TASKS: T-00000002 → blocked" "$TMP/b1.out" || fail "block --on must keep the TASKS: <id> → blocked prefix"
grep -q "released when T-00000001 is done" "$TMP/b1.out" || fail "block --on should say the release is automatic"
rows | grep -q "T-00000002 .*🔴 blocked.*attente pilote aussi" || fail "the note must still land in the stage column"
has_link T-00000002 T-00000001 || fail "block --on should store blocked_on"

# (b) --on SEUL sur un stage NON VIDE : le stage est PRÉSERVÉ (block ne détruit
# jamais), le lien s'écrit quand même.
tasks block T-00000003 --on T-00000001 >/dev/null || fail "block --on alone should exit 0"
rows | grep -q "T-00000003 .*🔴 blocked.*documenter" || fail "block --on must preserve a non-empty stage"
has_link T-00000003 T-00000001 || fail "block --on alone should store blocked_on"

# (c) --on SEUL sur un stage VIDE : le stage dit POURQUOI (`on T-NNN`) au lieu
# de laisser une ligne bloquée sans information.
tasks block T-00000004 --on T-00000001 >/dev/null
rows | grep -q "T-00000004 .*🔴 blocked.*on T-00000001" || fail "an empty stage should receive 'on T-NNN'"

# (d) `list --task` montre le champ (format_detail imprime toute clé hors FIELDS)
tasks list --task T-00000002 | grep -q "^blocked_on .*T-00000001" || fail "list --task should show blocked_on"

# (e) `done` LIBÈRE, et le DIT : première ligne inchangée (contrat consommateur),
# puis une ligne bruyante par libération. Les libérées atterrissent en `pending`,
# jamais en `running` — l'invariant tient même quand trois tâches sont libérées.
tasks done T-00000001 --raison "clos par le banc" > "$TMP/d1.out" || fail "done on a blocker should exit 0"
[ "$(head -1 "$TMP/d1.out")" = "TASKS: T-00000001 → done" ] || fail "the first line of done must not move"
for freed in T-00000002 T-00000003 T-00000004; do
  grep -q "^TASKS: $freed → pending (was blocked on T-00000001)$" "$TMP/d1.out" \
    || fail "done should announce the release of $freed"
  has_link "$freed" "" || fail "$freed should have lost its blocked_on at release"
done
[ "$(rows | grep -c '⚪ pending')" = "3" ] || fail "the three released tasks should be pending"
[ "$(rows | grep -c '🟢 running')" = "0" ] || fail "a release must never produce a running task"
rows | grep -q "T-00000002 .*⚪ pending.*—" || fail "a released task should have its stage cleared"

# (f) les trois refus, BRUYANTS : un lien qu'aucun `done` ne pourrait libérer est
# refusé au geste, pas découvert plus tard comme une tâche rouge sans raison.
tasks block T-00000002 --on T-00000002 2>"$TMP/e1" && fail "block --on itself must exit non-zero"
grep -q "blocked on itself" "$TMP/e1" || fail "self-blocking should explain the refusal"
tasks block T-00000002 --on T-00000001 2>"$TMP/e2" && fail "block --on a done task must exit non-zero"
grep -q "already done" "$TMP/e2" || fail "blocking on a done task should explain the refusal"
tasks block T-00000002 --on T-99999999 2>"$TMP/e3" && fail "block --on an unknown id must exit non-zero"
grep -q "unknown task id" "$TMP/e3" || fail "an unknown --on should print a readable error"
if grep -q "Traceback" "$TMP/e1" "$TMP/e2" "$TMP/e3"; then fail "a refused block leaked a traceback"; fi
# pas de forme courte : `--on 3` ne doit pas atteindre T-00000003 par chance
tasks block T-00000002 --on 3 2>/dev/null && fail "--on must not resolve the short form 3"
has_link T-00000002 "" || fail "a refused block must not have written a link"

# (g) LE LIEN NE SURVIT PAS À UNE SORTIE DE `blocked` — reproduction du défaut :
# une tâche relancée puis re-bloquée pour une raison HUMAINE ne doit pas être
# libérée par la fermeture de son ANCIEN bloqueur.
tasks block T-00000004 --on T-00000003 >/dev/null
tasks start T-00000004 >/dev/null
has_link T-00000004 "" || fail "start must clear blocked_on when the task leaves blocked"
tasks block T-00000004 --note "attente pilote" >/dev/null
has_link T-00000004 "" || fail "re-blocking with a note must not resurrect the old link"
tasks done T-00000003 --raison "clos par le banc" > "$TMP/d2.out"
grep -q "was blocked on" "$TMP/d2.out" && fail "the old blocker's done must not release a task re-blocked for a human reason"
rows | grep -q "T-00000004 .*🔴 blocked.*attente pilote" || fail "T-00000004 should still be blocked on its human reason"

# (h) SUPPRIMER un bloqueur ne libère PAS (le travail n'a pas été fait) : la
# dépendante reste bloquée, le lien pendant est nettoyé et la sortie L'ANNONCE.
tasks block T-00000004 --on T-00000002 >/dev/null
tasks delete T-00000002 > "$TMP/del.out" || fail "deleting a blocker should exit 0"
[ "$(head -1 "$TMP/del.out")" = "TASKS: T-00000002 deleted" ] || fail "the first line of delete must not move"
grep -q "^warning: T-00000004 was blocked on deleted T-00000002 — still blocked$" "$TMP/del.out" \
  || fail "deleting a blocker should warn about each dangling dependency"
rows | grep -q "T-00000004 .*🔴 blocked" || fail "a deleted blocker must NOT release its dependents"
has_link T-00000004 "" || fail "the dangling blocked_on should have been cleaned"

# (i) un store PORTANT un lien pendant reste LISIBLE : le référent n'a pas à
# exister (une lecture que les hooks SessionStart consomment ne refuse jamais
# l'histoire), mais une valeur structurellement cassée échoue bruyamment.
cat > "$STORE" <<'JSON'
{
  "next_id": 3,
  "tasks": [
    {"id": "T-00000001", "state": "blocked", "task": "orpheline", "owner": "dev-mono", "stage": "on T-00000999", "updated": "2026-07-01", "blocked_on": "T-00000999"}
  ]
}
JSON
tasks list | grep -q "T-00000001" || fail "a dangling blocked_on must not break the board read"
"$PY" -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding="utf-8")); d["tasks"][0]["blocked_on"]=""; json.dump(d,open(p,"w",encoding="utf-8"))' "$STORE"
tasks list 2>"$TMP/e4" && fail "an empty blocked_on must fail loudly"
grep -q "blocked_on" "$TMP/e4" || fail "the invalid blocked_on error should name the field"

# --- writeset / parallel : la garde de DISJONCTION (T-00000188) --------------
# GARDE DE COHÉRENCE, PAS DE SÉCURITÉ : tout ce qui suit prouve que les jeux de
# fichiers DÉCLARÉS sont disjoints ; rien n'observe ce que les agents écrivent
# réellement (l'enforcement observé est T-00000189). Le prédicat lui-même et les
# deux propriétés épinglées sont testés dans `test_tasks.py` ; ici c'est le
# parcours CLI de bout en bout, celui que le pilote tape.
cat > "$STORE" <<'JSON'
{
  "next_id": 4,
  "tasks": [
    {"id": "T-00000001", "state": "pending", "task": "coeur board", "owner": "dev-multi", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000002", "state": "pending", "task": "interface", "owner": "frontend-fidelity", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000003", "state": "pending", "task": "voisine", "owner": "dev-mono", "stage": "", "updated": "2026-08-01"}
  ]
}
JSON
tasks render >/dev/null

# (a) REFUS À LA DÉCLARATION, chaque refus NOMMANT sa clause. Un refus qui ne
# nomme pas sa clause bloque son propre diagnostic. Amendement C22 : `""` et `/`
# peuvent tomber sur « au moins un segment » OU sur « segment non vide » selon
# l'écriture — les deux sont acceptés ici, l'implémentation fixe l'ordre.
#
# GIT BASH RÉÉCRIT LES ARGUMENTS QUI COMMENCENT PAR `/` (MSYS path conversion) :
# `/` arrive au script comme `C:/Program Files/Git/`, donc le cas de test
# mesurerait la clause `no-colon` au lieu de celle qu'il vise — MESURÉ. Les deux
# variables ci-dessous coupent cette conversion pour CET appel seulement, et la
# racine est passée sous une forme que Windows comprend sans conversion. Sur
# Linux `cygpath` n'existe pas et les variables sont inertes : un seul chemin de
# code, dont la branche Windows ne peut simplement pas être prise ailleurs.
ROOTW="$TMP"; SCRIPTW="$SCRIPT"
if command -v cygpath >/dev/null 2>&1; then
  ROOTW="$(cygpath -m "$TMP")"; SCRIPTW="$(cygpath -m "$SCRIPT")"
fi
refuse_writeset() {  # $1 = chemin, $2 = motif de clause attendu (grep -E)
  if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
     "$PY" "$SCRIPTW" --root "$ROOTW" writeset T-00000001 "$1" 2>"$TMP/ws.err" >/dev/null; then
    fail "writeset should have refused '$1'"
  fi
  grep -qE "clause ($2):" "$TMP/ws.err" || fail "refusing '$1' should name its clause; got: $(cat "$TMP/ws.err")"
  grep -q "Canonical form:" "$TMP/ws.err" || fail "refusing '$1' should show a canonical form"
  if grep -q "Traceback" "$TMP/ws.err"; then fail "refusing '$1' leaked a traceback"; fi
}
refuse_writeset ""                 "at-least-one-segment|non-empty-segment"
refuse_writeset "/"                "at-least-one-segment|non-empty-segment"
refuse_writeset 'C:\repo\src\a'    "no-colon"
refuse_writeset "/src/a"           "non-empty-segment"
refuse_writeset '\\srv\share'      "non-empty-segment"
refuse_writeset "src/a/../b"       "no-dot-segment"
refuse_writeset "src//a"           "non-empty-segment"
refuse_writeset 'src/\a'           "non-empty-segment"
refuse_writeset "docs//"           "non-empty-segment"
refuse_writeset "src/a."           "no-trailing-dot-or-space"
refuse_writeset "src/a "           "no-trailing-dot-or-space"
refuse_writeset "src/a:flux"       "no-colon"
refuse_writeset "src/con"          "no-win32-device-name"
refuse_writeset "src/con.txt"      "no-win32-device-name"
grep -q '"writeset"' "$STORE" && fail "a refused declaration must not have written anything"

# (b) NE DOIT PAS refuser — et la déclaration est REVERSIBLE.
tasks writeset T-00000001 "docs/" | grep -q "writeset = 1 path: docs/" || fail "docs/ must be admitted"
tasks writeset T-00000001 "src/a" "src/ab" | grep -q "2 paths" || fail "src/a + src/ab must be admitted together"
tasks writeset T-00000002 "docs/" "Documentation/" >/dev/null || fail "docs/ + Documentation/ must be admitted"
tasks writeset T-00000002 --clear | grep -q "writeset cleared" || fail "--clear should drop the declaration"

# (c) REFUS AU GROUPE : recoupement direct, recoupement à la casse (le cas
# NTFS), et un `blocked_on` entre deux membres.
tasks writeset T-00000001 "src/a/" >/dev/null
tasks writeset T-00000002 "src/a/b.py" >/dev/null
tasks parallel T-00000001 T-00000002 2>"$TMP/pg1" && fail "overlapping writesets must refuse the group"
grep -q "not disjoint" "$TMP/pg1" || fail "the refusal should say the writesets are not disjoint"
grep -q "src/a/" "$TMP/pg1" || fail "the refusal should name the offending path"

tasks writeset T-00000001 "src/A/" >/dev/null
tasks parallel T-00000001 T-00000002 2>"$TMP/pg2" && fail "src/A/ vs src/a/b.py must refuse (the NTFS case)"
grep -q "not disjoint" "$TMP/pg2" || fail "the casefolded overlap should be explained"

tasks writeset T-00000001 "src/a/" >/dev/null
tasks writeset T-00000002 "src/b/" >/dev/null
tasks block T-00000002 --on T-00000001 >/dev/null
tasks parallel T-00000001 T-00000002 2>"$TMP/pg3" && fail "a blocked_on between members must refuse the group"
grep -q "behind that task" "$TMP/pg3" || fail "the refusal should say the task is behind, not parallel"
tasks unblock T-00000002 >/dev/null
grep -q '"parallel_group"' "$STORE" && fail "a refused group must not have been written"

# un membre SANS writeset : la vacuité n'est jamais une preuve
tasks parallel T-00000001 T-00000003 2>"$TMP/pg4" && fail "a member with no writeset must refuse the group"
grep -q "vacuously true" "$TMP/pg4" || fail "the refusal should name the vacuity"

# (d) NE DOIT PAS refuser : writesets disjoints -> groupe, deux `start`, et un
# `list` en sortie 0 (le board reste LISIBLE, c'est le vrai enjeu de `load`).
tasks parallel T-00000001 T-00000002 | grep -q "PG-0001" || fail "disjoint writesets should declare a group"
tasks start T-00000001 --stage dev-multi >/dev/null
tasks start T-00000002 --stage frontend-fidelity >/dev/null
tasks list >/dev/null || fail "a declared parallel group must keep the board readable"
[ "$(rows | grep -c '🟢 running')" = "2" ] || fail "both members of the group should be running"

# (e) AFFICHAGE : focus = la PREMIÈRE du store (ordre de création), suffixe ∥N.
SL2="$(tasks --statusline)"
case "$SL2" in
  "▶ T-00000001 · ⏱ dev "[0-9]*"/? · dev-multi ∥2 · ⏸1 ✓0") ;;
  *) fail "unexpected parallel statusline: $SL2" ;;
esac
# `stage` tolère L'UNE des tâches en cours du groupe (couplage le plus serré)
tasks stage T-00000002 documenter >/dev/null || fail "staging a group member should work"

# (f) DÉMARRER HORS DU GROUPE ne rétrograde plus le groupe (T-01M5F7286N1EYGXAXA5244X86B) :
# trois running, le groupe intact, le focus du clone passe à l'arrivante.
tasks start T-00000003 >/dev/null
[ "$(rows | grep -c '🟢 running')" = "3" ] || fail "starting outside the group must demote nobody"
grep -q '"parallel_group": "PG-0001"' "$STORE" || fail "the group members must keep their group"

# (g) DELETE garde son refus, AU PLURIEL.
tasks delete T-00000003 2>"$TMP/del2" && fail "deleting a running task without --force must exit non-zero"
grep -q "is a running task" "$TMP/del2" || fail "the delete refusal should read in the plural"

# (h) PLUSIEURS GROUPES, OU AUCUN, SOUS DES RUNNING : UN BOARD LÉGITIME (T-01M5F7286N1EYGXAXA5244X86B).
# Constat HIGH de la revue T-00000188 : déclarer un SECOND groupe sur un membre d'un
# groupe VIVANT laissait l'autre membre seul dans l'ancien, et `load()` refusait
# alors tout le board. Le refus est retiré avec la rétrogradation : le même geste
# par le CLI documenté écrit, et chaque verbe relit le board.
cat > "$STORE" <<'JSON'
{
  "next_id": 4,
  "tasks": [
    {"id": "T-00000001", "state": "pending", "task": "un", "owner": "dev", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000002", "state": "pending", "task": "deux", "owner": "dev", "stage": "", "updated": "2026-08-01"},
    {"id": "T-00000003", "state": "pending", "task": "trois", "owner": "dev", "stage": "", "updated": "2026-08-01"}
  ]
}
JSON
tasks writeset T-00000001 "src/un/" >/dev/null
tasks writeset T-00000002 "src/deux/" >/dev/null
tasks writeset T-00000003 "src/trois/" >/dev/null
tasks parallel T-00000001 T-00000002 >/dev/null || fail "the first group should be declared"
tasks start T-00000001 >/dev/null
tasks start T-00000002 >/dev/null
cp "$STORE" "$TMP/live-group.json"

# UN SECOND GROUPE SUR UN MEMBRE VIVANT : déclaré, l'autre membre garde PG-0001.
tasks parallel T-00000001 T-00000003 | grep -q "PG-0002" || fail "a second group over a live member is now declared"
grep -q '"parallel_group": "PG-0001"' "$STORE" || fail "the other live member must keep the first group"
# LE BOARD EST TOUJOURS VIVANT — c'est le vrai enjeu : chaque verbe lit d'abord.
tasks list >/dev/null || fail "list must still work after the second declaration"
[ "$(rows | grep -c '🟢 running')" = "2" ] || fail "both live members should still be running"
tasks --statusline | grep -q "∥2" || fail "the statusline must not report a malformed board"
tasks stage T-00000002 documenter >/dev/null || fail "stage must still work"
tasks done T-00000002 --raison "clos par le banc" >/dev/null || fail "done must still work"

# (i) écrire un writeset RÉTRACTE la preuve qui l'utilisait, et le DIT — membre
# VIVANT compris : c'est le cas motivant (ajouter une sortie GÉNÉRÉE à son writeset).
tasks writeset T-00000001 "src/un/" ".agents/ui/" | grep -q "PG-0002 dropped" \
  || fail "rewriting a live member's writeset should drop the group its proof was computed on"

# (j) `parallel` n'est plus aveugle à l'état : une tâche close ne rejoint rien.
tasks parallel T-00000001 T-00000002 2>"$TMP/pg5" && fail "grouping a done task must exit non-zero"
grep -q "is done" "$TMP/pg5" || fail "the refusal should name the closed task"

# --- depends_on : un ORDRE qui GARDE le start, jamais un ÉTAT (T-00000530,
# S-01M4Z5VMP5E9YN8T6EMDTBAF0T) ----------------------------------------------
# Les faits que seule la CLI peut prouver : le verbe écrit, `done` n'efface
# rien, la lecture inverse répond, et `deps-ready` rend 1 puis 0 quand l'amont
# se ferme. Le reste est couvert par test_tasks.py et test_tasks_amont.py.
D="$TMP/dep"; mkdir -p "$D/.agents/state/board"
dtasks() { "$PY" "$SCRIPT" --root "$D" "$@"; }
# Ids CAPTURÉS, jamais prédits (T-00000726, R-BANCS (i)).
dnew_id() { dtasks new "$@" | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p'; }
AMONT="$(dnew_id "amont")"
AVAL="$(dnew_id "aval")"
[ -n "$AMONT" ] && [ -n "$AVAL" ] || fail "new should report the ids it allocated"

# (a) le verbe écrit, et `list --task` l'affiche SANS changement de code.
dtasks depends "$AVAL" "$AMONT" --motif "amont livre ce que aval consomme" \
  | grep -q "depends_on = 1 dependency" \
  || fail "depends should report what it wrote"
dtasks list --task "$AVAL" | grep -q "depends_on" \
  || fail "format_detail should print depends_on — it prints every key outside FIELDS"
dtasks list --task "$AVAL" | grep -q "$AMONT → " \
  || fail "format_detail should render the depends_motif dict via cell, not a repr"

# (a bis) SANS --motif : refus PROPRE, jamais un AttributeError. Seul témoin du
#         défaut argparse — les bancs Python appellent set_depends en direct,
#         donc avec le défaut "" de la signature, et ne voient jamais le None.
dtasks depends "$AVAL" "$AMONT" 2>"$TMP/dep-nomotif" \
  && fail "depends without --motif must exit non-zero"
grep -q "requires --motif" "$TMP/dep-nomotif" \
  || fail "the refusal should name --motif"
grep -q "Traceback" "$TMP/dep-nomotif" \
  && fail "a missing --motif must be a clean refusal, never an AttributeError"

# (a ter) l'aide d'argparse reste en ASCII PUR : `--help` sort dans parse_args,
#         donc AVANT force_utf8_stdio, et un accent y plante sur cp1252. Un appel
#         par sous-commande (le help= de --motif n'apparaît que dans
#         `depends --help`, celui du positionnel tid dans `depends-show --help`),
#         PLUS l'aide RACINE en entier : T-00000645 y a corrigé le SEUL non-ASCII
#         préexistant (le help= d'`unblock`, une flèche), donc l'aide racine est
#         désormais assertable telle quelle et garde TOUTES les sous-commandes
#         d'un coup, pas seulement les deux qu'on a pensé à nommer.
dtasks depends --help > "$TMP/dep-help-depends" 2>&1 || fail "depends --help must exit zero"
"$PY" -c 'import sys; sys.exit(0 if open(sys.argv[1], encoding="utf-8").read().isascii() else 1)' \
  "$TMP/dep-help-depends" || fail "the --motif help= must stay pure ASCII"
dtasks depends-show --help > "$TMP/dep-help-show" 2>&1 || fail "depends-show --help must exit zero"
"$PY" -c 'import sys; sys.exit(0 if open(sys.argv[1], encoding="utf-8").read().isascii() else 1)' \
  "$TMP/dep-help-show" || fail "the depends-show help= must stay pure ASCII"
dtasks --help > "$TMP/dep-help-root" 2>&1 || fail "root --help must exit zero"
"$PY" -c 'import sys; sys.exit(0 if open(sys.argv[1], encoding="utf-8").read().isascii() else 1)' \
  "$TMP/dep-help-root" || fail "the ROOT --help must stay pure ASCII (it prints before force_utf8_stdio)"
# Les aides que S-01M4Z5VMP5E9YN8T6EMDTBAF0T écrit ou étend : `deps-ready`, et
# `start`/`fournee` qui portent `--sans-dependances` (AIDE_CLI de plan_depends.py).
for verbe in deps-ready start fournee; do
  dtasks "$verbe" --help > "$TMP/dep-help-$verbe" 2>&1 || fail "$verbe --help must exit zero"
  "$PY" -c 'import sys; sys.exit(0 if open(sys.argv[1], encoding="utf-8").read().isascii() else 1)' \
    "$TMP/dep-help-$verbe" || fail "the $verbe --help must stay pure ASCII"
done

# (a quater) `deps-ready` : l'amont ouvert rend 1 et refuse le `start`, en bout de CLI.
rc_ready=0
dtasks deps-ready "$AVAL" > "$TMP/dep-ready-ouvert" 2>&1 || rc_ready=$?
[ "$rc_ready" -eq 1 ] || fail "deps-ready must exit 1 while the upstream is open (rc $rc_ready)"
head -n 1 "$TMP/dep-ready-ouvert" | grep -qx "deps-ready: AMONT_OUVERT" \
  || fail "deps-ready should open with its token line"
dtasks start "$AVAL" 2>"$TMP/dep-start-ouvert" && fail "start must refuse an open upstream"
grep -q "deps-ready: AMONT_OUVERT" "$TMP/dep-start-ouvert" || fail "the start refusal should name the token"

# (b) `done` sur la cible ne change NI l'état de la dépendante NI l'arête.
#     C'est l'asymétrie avec blocked_on, et elle se prouve ici en bout de CLI.
dtasks done "$AMONT" --raison "clos par le banc" >/dev/null
dtasks list --task "$AVAL" | grep -q "pending" \
  || fail "closing a dependency must NOT change the dependent's state"
dtasks list --task "$AVAL" | grep -q "$AMONT" \
  || fail "closing a dependency must NOT erase the edge — satisfaction is computed"
dtasks deps-ready "$AVAL" > "$TMP/dep-ready-clos" 2>&1 || fail "deps-ready must exit 0 once the upstream is done"
head -n 1 "$TMP/dep-ready-clos" | grep -qx "deps-ready: AMONT_CLOS" || fail "a closed upstream reads AMONT_CLOS"

# (c) la lecture inverse répond, et refuse une valeur vide.
dtasks list --depends-on "$AMONT" | grep -q "$AVAL" \
  || fail "--depends-on should answer 'who is behind this one?' even after closure"
dtasks list --depends-on "" 2>"$TMP/dep-err" && fail '--depends-on "" must exit non-zero'
grep -q "no task depends on nothing" "$TMP/dep-err" \
  || fail "the refusal should say why an empty value has no meaning here"

# (d) --motif est RÉPÉTABLE : un motif par arête, dans l'ordre des ids — c'est le
#     TITRE de T-00000645. Deux --motif sur deux ids donnent deux raisons
#     distinctes, et le lecteur n'affiche jamais sur l'une la raison de l'autre.
PORTEUSE="$(dnew_id "porteuse per-edge")"
[ -n "$PORTEUSE" ] || fail "new should report the id it allocated"
dtasks depends "$PORTEUSE" "$AMONT" "$AVAL" \
  --motif "T-1 livre le schema" --motif "T-2 livre le lecteur" \
  | grep -q "depends_on = 2 dependencies" \
  || fail "a repeatable --motif should declare both edges"
dtasks depends-show "$PORTEUSE" > "$TMP/dep-per-edge" 2>&1 \
  || fail "depends-show must exit zero"
grep -q "$AMONT → .*T-1 livre le schema" "$TMP/dep-per-edge" \
  || fail "the edge to T-1 must carry ITS OWN motif"
grep -q "$AVAL → .*T-2 livre le lecteur" "$TMP/dep-per-edge" \
  || fail "the edge to T-2 must carry ITS OWN motif, never T-1's"
# et un compte de motifs ni 1 ni un-par-id est REFUSÉ en nommant le reçu.
dtasks depends "$PORTEUSE" "$AMONT" "$AVAL" \
  --motif "un" --motif "deux" --motif "trois" 2>"$TMP/dep-count" \
  && fail "three motifs for two ids must exit non-zero"
grep -q "received 3" "$TMP/dep-count" \
  || fail "the count refusal must name the received count"
# --clear n'accepte pas de --motif : il ne reste aucune arête à motiver (B-C7).
dtasks depends "$PORTEUSE" --clear --motif "orpheline" 2>"$TMP/dep-clearmotif" \
  && fail "depends --clear --motif must exit non-zero"
grep -q "takes no --motif" "$TMP/dep-clearmotif" \
  || fail "the refusal should say --clear leaves no edge to motivate"

# --- T-00000577 : `start` NE DOIT EFFACER AUCUN `stage` -------------------
# Deux effacements SILENCIEUX vivaient dans le même geste, mesurés le
# 2026-09-13 : celui de la tâche RÉTROGRADÉE (`other.update(stage="")`) et
# celui de la tâche DÉMARRÉE (`--stage` avec `default=""`, écrit par
# `set_state`). Le champ `stage` porte OÙ EN EST une tâche, donc sa mémoire de
# reprise, sur la surface que le SessionStart injecte : le perdre sans un mot
# est la faute que ce banc garde désormais fermée.
cat > "$STORE" <<'JSON'
{
  "next_id": 3,
  "tasks": [
    {"id": "T-00000001", "state": "running", "task": "celle qui tourne", "owner": "dev-mono", "stage": "etape en vol a preserver", "updated": "2026-09-13"},
    {"id": "T-00000002", "state": "pending", "task": "celle qu on demarre", "owner": "dev-mono", "stage": "point d etape anterieur", "updated": "2026-09-13"}
  ]
}
JSON
tasks start T-00000002 >/dev/null
tasks list --task T-00000001 --json | grep -q "etape en vol a preserver" \
  || fail "start a EFFACE le stage de l AUTRE running — sa memoire de reprise"
tasks list --task T-00000002 --json | grep -q "point d etape anterieur" \
  || fail "start a EFFACE le stage de la tache DEMARREE"
# L'ÉTAT DOIT AVOIR CHANGÉ pour la démarrée, sans quoi les deux assertions ci-dessus
# passeraient aussi sur un `start` devenu inerte — et l'AUTRE reste running : `start`
# ne rétrograde plus (T-01M5F7286N1EYGXAXA5244X86B).
tasks list --task T-00000002 --json | grep -q '"state": "running"' \
  || fail "start n a pas demarre la tache"
tasks list --task T-00000001 --json | grep -q '"state": "running"' \
  || fail "start a retrograde la tache qui tournait"
# Et `--stage` explicite doit toujours ÉCRIRE : sans ce contrôle négatif, le
# correctif passerait aussi si `start` avait cessé de poser un stage tout court.
tasks start T-00000001 --stage "dev-multi" >/dev/null
tasks list --task T-00000001 --json | grep -q "dev-multi" \
  || fail "--stage explicite doit ecrire le stage — le correctif l a neutralise"
tasks list --task T-00000002 --json | grep -q "point d etape anterieur" \
  || fail "le start d une autre a efface le stage"

# --- SORTIR DE `blocked` N'EMPORTE PAS SON MOTIF --------------------------
# LE CAS QUI A ATTRAPÉ UNE RÉGRESSION DE T-00000577 : faire de `--stage` absent
# un « ne touche pas » est juste en sortant de `running`, et FAUX en sortant de
# `blocked`, où le champ porte un MOTIF d'attente et non une étape. Mesuré : une
# tâche bloquée sur « attente decision pilote » ressortait `running` en portant
# ce motif, et la statusline l'affichait comme étape de pipeline.
cat > "$STORE" <<'JSON'
{
  "next_id": 2,
  "tasks": [
    {"id": "T-00000001", "state": "blocked", "task": "debloquee par start", "owner": "dev-mono", "stage": "attente decision pilote", "updated": "2026-09-13"}
  ]
}
JSON
tasks start T-00000001 >/dev/null
if tasks list --task T-00000001 --json | grep -q "attente decision pilote"; then
  fail "start depuis blocked garde le MOTIF DE BLOCAGE comme etape en vol"
fi

# --- un SECOND `start` n'efface pas le stage qu'il vient de poser ---------
tasks start T-00000001 --stage "une etape" >/dev/null
tasks start T-00000001 >/dev/null
tasks list --task T-00000001 --json | grep -q "une etape" \
  || fail "un second start sur une tache DEJA running a efface son propre stage"

# --- `--stage ""` EXPLICITE doit vider : c'est la seule porte de sortie de
# `default=None`, et rien d'autre ne la protege d'un futur `if stage:`.
tasks start T-00000001 --stage "" >/dev/null
tasks list --task T-00000001 --json | grep -q '"stage": ""' \
  || fail "--stage vide explicite doit VIDER le champ"

# --- `commit-run-exports` n'est PAS un verbe mutant (T-00000677) -----------
# Assertion sur le LITTERAL `mutating` de tasks.py, pas sur un souvenir : on
# decoupe le bloc `mutating = args.cmd in { ... }` et on prouve que le nouveau
# verbe en est ABSENT, en verifiant que `done` y est (non-vacuite : un decoupage
# vide passerait sinon). Un V3 replay autour du commit des exports produirait de
# nouveaux evenements qui saliraient runs/, et la nuit ne convergerait jamais.
MUT="$(sed -n '/mutating = args.cmd in {/,/} and not/p' "$SCRIPT")"
printf '%s' "$MUT" | grep -q '"done"' \
  || fail "non-vacuite: le bloc mutating extrait ne contient pas 'done'"
if printf '%s' "$MUT" | grep -q '"commit-run-exports"'; then
  fail "commit-run-exports ne doit PAS etre dans l'ensemble mutating de tasks.py"
fi
# T-00000724 — le verbe frere `commit-stores` est HORS de `mutating` lui aussi.
# Existence d'abord : un verbe retire de tasks.py rendrait l'absence VACANTE.
grep -q '"commit-stores"' "$SCRIPT" \
  || fail "existence: le verbe commit-stores est introuvable dans tasks.py"
if printf '%s' "$MUT" | grep -q '"commit-stores"'; then
  fail "commit-stores ne doit PAS etre dans l'ensemble mutating de tasks.py"
fi

echo "PASS: tasks.py"
