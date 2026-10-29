#!/usr/bin/env bash
# Tests for semgrep-scan.sh — second half (arms (sgc) onward), split out of
# semgrep-scan.test.sh (T-01M55Z3W38NDBXMTZBP81GKA8R) so the two halves run in
# parallel. Run: bash .agents/security/semgrep-scan-git.test.sh — also
# auto-discovered by core-scripts/run-bash-tests.sh. The preamble below is
# RECOPIÉ ON PURPOSE (no shared helper) from semgrep-scan.test.sh: the helpers
# and computed blocks the arms read; change one, change both.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/semgrep-scan.sh"
# SUITE_BASH — the interpreter this suite RESOLVES its runs onto. `${BASH:-…}`
# so `/bin/bash semgrep-scan.test.sh` makes the SCRIPT (and the stubs) run under
# /bin/bash 3.2, not the developer's PATH bash (T-00000477 S2.3): a suite that
# resolves its interpreter by PATH measures the developer's bash, never the one
# that travels. Every `"$SUITE_BASH" "$SCRIPT"` and every stub shebang routes here.
SUITE_BASH="${BASH:-$(command -v bash)}"
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
CFG="$REAL_ROOT/.agents/security/semgrep.yml"
[ -f "$SCRIPT" ] || { echo "FAIL: semgrep-scan.sh not found"; exit 1; }
[ -f "$CFG" ]    || { echo "FAIL: semgrep.yml not found"; exit 1; }

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

# assert_tmpdir — REFUSE a throwaway dir that is empty, equal to the repo/cwd,
# or outside the temp root, BEFORE any `git -C "$dir"` runs on it. An empty
# `$dir` makes `git -C "" init/commit` operate in the CURRENT directory — i.e.
# this live kit repo — which is how a throwaway "init" commit can sweep in-flight
# work across tasks. Same lesson as T-00000303 (a mass operation must refuse the
# input it would corrupt), applied here to the harness itself: fail loudly, never
# a silent fallback into the real tree.
assert_tmpdir() {  # $1 = candidate throwaway dir
  [ -n "$1" ]              || fail "throwaway dir is EMPTY — refusing (git -C '' would hit the live repo)"
  [ "$1" != "$PWD" ]       || fail "throwaway dir == PWD ($1) — refusing"
  [ "$1" != "$REAL_ROOT" ] || fail "throwaway dir == repo root ($1) — refusing"
  case "$1" in
    /tmp/*|/var/folders/*|/private/var/folders/*) : ;;
    *)
      # macOS $TMPDIR ends with a trailing slash (/var/folders/.../T/), so the
      # bare "$TMPDIR"/* pattern doubled the slash and never matched mktemp's
      # output beneath it — normalise the root before comparing.
      _tmproot="${TMPDIR:-/tmp}"; _tmproot="${_tmproot%/}"
      case "$1" in
        "$_tmproot"/*) : ;;
        *) fail "throwaway dir outside temp ($1) — refusing" ;;
      esac ;;
  esac
}

# ---- THE SUITE NEVER RUNS IN THE CALLER'S TREE (T-01M4X9PP7FED0570PMPSYGA0V8) --
# Arms (q), (q2), (t), (u), (v) and (h7) launch the script in the CURRENT
# directory, and the script writes `.agents/state/local/sca-reports/`
# (audit-log.jsonl, semgrep-verdict.json) under the git toplevel it finds THERE:
# measured by the exec-critic, run from the kit's root the suite rewrote the
# kit's own common verdict and audit journal. So before its first run the suite
# moves into a throwaway repo — one commit, `state/local/` ignored, so `--at
# HEAD` and `--since HEAD` still resolve — and removes it at the end. Every other
# path of the suite is absolute (HERE, SCRIPT, REAL_ROOT are resolved above).
SUITE_CWD="$(mktemp -d)"
assert_tmpdir "$SUITE_CWD"
git -C "$SUITE_CWD" init -q
mkdir -p "$SUITE_CWD/.agents"
printf 'state/local/\n' > "$SUITE_CWD/.agents/.gitignore"
git -C "$SUITE_CWD" add -A >/dev/null 2>&1
git -C "$SUITE_CWD" -c user.email="test@test.local" -c user.name="test" -c commit.gpgsign=false \
  commit -qm init >/dev/null 2>&1
git -C "$SUITE_CWD" rev-parse --verify --quiet HEAD >/dev/null 2>&1 \
  || fail "throwaway cwd $SUITE_CWD has no commit — the cwd arms would measure another branch"
cd "$SUITE_CWD" || fail "cannot enter the throwaway cwd $SUITE_CWD"

HAVE_SEMGREP=0; command -v semgrep >/dev/null 2>&1 && HAVE_SEMGREP=1
PY=""; for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
# `sub` carrying an `os.system` sink (verified-red by semgrep.yml's
# python-command-injection-shell-true rule), itself carrying a nested `sub/nested`
# with its OWN sink — so a finding on `sub/nested/nested_vuln.py` PROVES the
# recursion descends past the first boundary. Files written with printf
# (L-00000197); assert_tmpdir guards every throwaway dir (T-00000311); GIT_ISO
# allows the file:// protocol for local-path submodules (git ≥ 2.38).
GIT_ISO="git -c protocol.file.allow=always -c user.name=t -c user.email=t@t.t -c commit.gpgsign=false -c advice.detachedHead=false"
mk_super_sg() {  # echoes the superproject path; a nested submodule is always present
  local nested sub super
  nested="$(mktemp -d)"; sub="$(mktemp -d)"; super="$(mktemp -d)"
  assert_tmpdir "$nested"; assert_tmpdir "$sub"; assert_tmpdir "$super"
  $GIT_ISO init -q "$nested"
  printf 'import os\n\n\ndef nested_run(x):\n    os.system("echo " + x)\n' > "$nested/nested_vuln.py"
  $GIT_ISO -C "$nested" add -A >/dev/null 2>&1
  $GIT_ISO -C "$nested" commit -qm n >/dev/null 2>&1
  $GIT_ISO init -q "$sub"
  printf 'import os\n\n\ndef run(cmd):\n    os.system("echo " + cmd)\n' > "$sub/vuln.py"
  $GIT_ISO -C "$sub" submodule add -q "$nested" nested >/dev/null 2>&1
  $GIT_ISO -C "$sub" add -A >/dev/null 2>&1
  $GIT_ISO -C "$sub" commit -qm s >/dev/null 2>&1
  $GIT_ISO init -q "$super"
  printf 'root\n' > "$super/README.md"
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm r >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule add -q "$sub" sub >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule update -q --init --recursive >/dev/null 2>&1
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm addsub >/dev/null 2>&1
  printf '%s\n' "$super"
}
REPO_ROOT="$(cd "$(dirname "$SCRIPT")/../.." && pwd)"
RULESET="$REAL_ROOT/.agents/security/semgrep.yml"
CANDS_STR="${SUITE_BASH_CANDIDATES-$SUITE_BASH /bin/bash /usr/bin/bash}"
read -r -a CANDS <<< "$CANDS_STR" || true
OLDEST=""; OLDEST_MAJ=""; Z_SEEN=""; Z_SKIPPED=""
for cand in ${CANDS[@]+"${CANDS[@]}"}; do
  if [ ! -x "$cand" ]; then Z_SKIPPED="$Z_SKIPPED $cand(absent)"; continue; fi
  maj="$("$cand" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null)" || maj=""
  case "$maj" in
    ''|*[!0-9]*) Z_SKIPPED="$Z_SKIPPED $cand(sonde-KO)"; continue ;;
  esac
  Z_SEEN="$Z_SEEN $cand:$maj"
  if [ -z "$OLDEST_MAJ" ] || [ "$maj" -lt "$OLDEST_MAJ" ]; then OLDEST_MAJ="$maj"; OLDEST="$cand"; fi
done
ILL_SKIP=""
ILL_PROBE="$(mktemp -d)"; assert_tmpdir "$ILL_PROBE"
mkdir -p "$ILL_PROBE/d"; printf 'x\n' > "$ILL_PROBE/d/f"; printf 'x\n' > "$ILL_PROBE/k"
chmod 000 "$ILL_PROBE/d" "$ILL_PROBE/k"
if [ "$(id -u 2>/dev/null)" = "0" ]; then
  ILL_SKIP="uid 0 (root reads through chmod 000)"
elif [ -e "$ILL_PROBE/d/f" ] || [ -r "$ILL_PROBE/k" ]; then
  ILL_SKIP="chmod 000 still lets this host read"
fi
chmod 755 "$ILL_PROBE/d"; chmod 644 "$ILL_PROBE/k"; rm -rf "$ILL_PROBE"
ill_super_fin() {  # $1 super (from mk_super_sg) — removes it AND its two source repos
  local _s="$1" _sub _nest
  _sub="$(git -C "$_s" config -f .gitmodules --get submodule.sub.url 2>/dev/null)"
  _nest=""
  [ -n "$_sub" ] && _nest="$(git -C "$_sub" config -f .gitmodules --get submodule.nested.url 2>/dev/null)"
  chmod u+rwx "$_s/sub" "$_s/sub/d" "$_s/.git/modules/sub" 2>/dev/null
  rm -rf "$_s"
  case "$_sub" in
    /tmp/*|/var/folders/*|/private/var/folders/*) rm -rf "$_sub" ;;
  esac
  case "$_nest" in
    /tmp/*|/var/folders/*|/private/var/folders/*) rm -rf "$_nest" ;;
  esac
}
# =============================================================================
# (sgc*) (sgl*) (sgk*) (sgt*) (since*) (obj*) (idx*) (hk*) (cfg1) (sgr1) (sgm*)
# WHAT GIT COMMITS IS READ; THE CENSUS RUNS NO CODE OF THE SCANNED REPOSITORY
# T-01M4XY8NC97JBSQP6C28AFD7QP (index + pointe objects), T-01M4XY8PP8VYW0VVCYAAK0VARF
# (a base without a merge base), T-01M4Z24V0J813T40XRW3S4VW67 (cut channels),
# T-01M4Z5T4YQND3S63PW8D4ERN25 (byte sort), T-01M4Z5T5SKZA63MCWM1VRTZ6D8 (hook
# Stop), T-01M4Z5T6N1DN43K5SEC2DNB63M (submodule index), T-01M4Z2DMFTXH6Q40RRA3ZW1PE0
# (the audit line stays JSON).
# =============================================================================
# Every arm below was RED at c2a42ba2 (measured, plan § Couverture). Its check is
# a FUNCTION, replayed on each mutant of the table in a subshell that must FAIL
# (`sg_bras`): a mutant that survives is a FAIL. The table lives in ONE data
# file; an anchor seen other than EXACTLY once is a FAIL, never a SKIP (a mutant
# that mutates nothing is a mute witness), and at the end every mutant of the
# table must have reddened an arm or carry a SAID skip. Execution witnesses are
# MARKER FILES tested with `[ -e ]`; an arm that proves a channel CUT is PAIRED
# with a naked git call that makes the same marker BORN on the same fixture
# (`sg_nu`). Fake gits read the path of the real one from a DATA file beside
# them, never from their own source. `sg_stub`, the semgrep stand-in, reports
# every `os.system` line of the targets it is given, paths NORMALIZED as semgrep
# does (measured: `…/T//x` is reported `…/T/x`), and reads the current
# directory when it is given NO target — as semgrep does (measured).
[ -n "$PY" ] || fail "(sgm) python 3 introuvable pour fabriquer les mutants"
SG_W="$(mktemp -d)"; assert_tmpdir "$SG_W"
SG_T="$SG_W/marks"; SG_MUT="$SG_W/mut"; SG_STUB="$SG_W/stub"
mkdir "$SG_T" "$SG_MUT" "$SG_STUB"
cp "$HERE/scan_verdict.py" "$SG_MUT/scan_verdict.py"
SG_REAL_GIT="$(command -v git)"
SG_G="git -c user.email=t@t.t -c user.name=t -c commit.gpgsign=false -c advice.detachedHead=false -c protocol.file.allow=always -c init.defaultBranch=main"
SG_SINK='import os\ndef f(cmd):\n    os.system("echo " + cmd)\n'
SG_REDS=" "; SG_SKIPPED=" "; SG_S="$SCRIPT"; SG_PATH_DEF="$SG_STUB"; SG_LAST_DIR=""
_sg_v="$(git version 2>/dev/null)"; _sg_v="${_sg_v#git version }"
_sg_maj="${_sg_v%%.*}"; _sg_min="${_sg_v#*.}"; _sg_min="${_sg_min%%.*}"
case "$_sg_maj.$_sg_min" in
  *[!0-9.]*|.*|*.)
    fail "(sg) git version unreadable: '$_sg_v'" ;;
esac
sg_git_ge() {  # $1 major  $2 minor — rc 0 when the bench's git is >= $1.$2
  [ "$_sg_maj" -gt "$1" ] && return 0
  [ "$_sg_maj" -eq "$1" ] && [ "$_sg_min" -ge "$2" ]
}

{ printf '#!%s\n' "$SUITE_BASH"; cat <<'SGSTUB'
# sg_stub: semgrep stand-in for the (sg*) arms — see the section header.
# SG_STUB_EXCL: a target whose path holds it is neither read nor listed in
# paths.scanned, as a rule `paths: exclude` does (M3). SG_STUB_ENVF: the
# GIT_CONFIG_* the stub was launched with are appended there (m2).
# SG_STUB_RAW: the report is that file's bytes, verbatim, rc 0 — the malformed
# reports of the (prs*) arms.
if [ -n "${SG_STUB_RAW:-}" ]; then cat "$SG_STUB_RAW"; exit 0; fi
[ -n "${SG_STUB_SLEEP:-}" ] && sleep "$SG_STUB_SLEEP"
if [ -n "${SG_STUB_ENVF:-}" ]; then
  printf '%s|%s|%s|%s|%s\n' "${GIT_CONFIG_COUNT-}" "${GIT_CONFIG_KEY_0-}" "${GIT_CONFIG_VALUE_0-}" "${GIT_CONFIG_KEY_1-}" "${GIT_CONFIG_VALUE_1-}" >> "$SG_STUB_ENVF"
fi
_dd=0; _res=""; _sc=""; _bad=0; _n=0
_cibles=()
for _a in "$@"; do
  if [ "$_dd" = 1 ]; then _cibles+=("$_a"); fi
  [ "$_a" = "--" ] && _dd=1
done
if [ "${#_cibles[@]}" -eq 0 ]; then
  for _a in *.py; do [ -e "$_a" ] && _cibles+=("$_a"); done
fi
for _a in ${_cibles[@]+"${_cibles[@]}"}; do
  if [ -n "${SG_STUB_EXCL:-}" ]; then
    case "$_a" in
      *"$SG_STUB_EXCL"*)
        continue ;;
    esac
  fi
  if [ ! -r "$_a" ]; then _bad=1; continue; fi
  if [ -n "${SG_STUB_CAPT:-}" ]; then { printf '== %s\n' "$_a"; cat "$_a"; } >> "$SG_STUB_CAPT"; fi
  _p="${_a//\/\//\/}"
  if [ "${SG_STUB_SLASH:-0}" = 1 ]; then _p="${_p//\/i\//\/\/i\/}"; fi
  case "$_a" in
    *.py) : ;;
    *) continue ;;
  esac
  [ -n "$_sc" ] && _sc="$_sc,"
  _sc="$_sc\"$_p\""
  for _l in $(grep -n 'os.system' "$_a" 2>/dev/null | cut -d: -f1); do
    [ -n "$_res" ] && _res="$_res,"
    _res="$_res{\"check_id\":\"sg.sink\",\"path\":\"$_p\",\"start\":{\"line\":$_l},\"extra\":{\"severity\":\"ERROR\",\"message\":\"m\"}}"
  done
done
[ "$_bad" = 1 ] && exit 2
printf '{"results":[%s],"errors":[],"paths":{"scanned":[%s]}}\n' "$_res" "$_sc"
exit 0
SGSTUB
} > "$SG_STUB/semgrep"
chmod +x "$SG_STUB/semgrep"
SG_NOPY="$SG_W/nopy"; mkdir "$SG_NOPY"
for _p in python3 python; do
  { printf '#!/bin/sh\n'; printf 'exit 127\n'; } > "$SG_NOPY/$_p"; chmod +x "$SG_NOPY/$_p"
done

# The mutant TABLE (plan § Tests, closing lines C1-C7): `%%% <name>` opens a
# mutant, `@@@` an anchor (`@@@^`: at a line start), `---` its replacement.
cat > "$SG_W/mut.def" <<'SGMUTDEF'
%%% MC1
@@@^
      if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false
---
      if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
        git -C "$ROOT" -c diff.autoRefreshIndex=false
%%% MC1h
@@@^
        if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
          git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false
---
        if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
          git -C "$ROOT" -c diff.autoRefreshIndex=false
%%% MC2
@@@
"--config-env=filter.$n.clean=GL_VIDE"
---
%%% MC3
@@@^
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty "$SG_BASE" -- 2>/dev/null \
---
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv "$SG_BASE" -- 2>/dev/null \
%%% MC3b
@@@
git -C "$repo" "${GN[@]}" ls-files -z --stage
---
git -C "$repo" ls-files -z --stage
%%% MC4
@@@
opts+=("--config-env=filter.$n.clean=GL_VIDE" "--config-env=filter.$n.process=GL_VIDE" "--config-env=filter.$n.required=GL_FAUX")
---
opts+=(-c "filter.$n.clean=" -c "filter.$n.process=" -c "filter.$n.required=false")
%%% MC5
@@@
 "--config-env=filter.$n.required=GL_FAUX"
---
%%% MC6
@@@^
    unset GIT_CONFIG
---
    :
%%% MC7
@@@^
      if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
---
      if true; then
%%% MC7b
@@@
if [ -n "${vals[$j]}" ]; then
---
if false; then
%%% MC7c
@@@^
    if [ "$rc" -gt 1 ]; then
      rm -f "$lu"
---
    if [ "$rc" -gt 2 ]; then
      rm -f "$lu"
%%% MC8
@@@
 --no-show-signature --format=
---
 --format=
%%% MC9
@@@^
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty "$SG_BASE" -- 2>/dev/null \
---
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=all "$SG_BASE" -- 2>/dev/null \
%%% MX
@@@^
export GIT_NO_LAZY_FETCH=1
---
:
%%% MG
@@@
_ign_ill=$((_ign_ill + n)) ;;
---
_ign_ill=$((_ign_ill + 0)) ;;
%%% MG2
@@@^
  ignores_illisibles "$ROOT/$sub_rel"
---
  :
%%% MGh
@@@
    relever_ignores   # (hook Stop) C1
---
    :   # (hook Stop) C1
%%% MG3
@@@
 --glob-pathspecs ls-files -v -z
---
 ls-files -v -z
%%% MG5
@@@^
      rc=vieux
---
      rc=0
%%% MG6
@@@
cat-file --batch-check -Z > "$lv" 2>/dev/null || rc=$?
---
cat-file --batch-check -Z > "$lv" 2>/dev/null || :
%%% MG8
@@@
ls-files --others --ignored --exclude-standard --directory -z
---
ls-files --others --directory -z
%%% MP1
@@@^
paresseux() {  # $1 = repo dir
---
paresseux() {  # $1 = repo dir
  return 1
%%% MP3
@@@^
  if paresseux "$1"; then
    perte_perimetre "?" "skip-worktree .gitignore file(s) not checked
---
  if false; then
    perte_perimetre "?" "skip-worktree .gitignore file(s) not checked
%%% MPI
@@@^
  if paresseux "$2"; then
---
  if false; then
%%% MPK
@@@^
  paresseux "$ROOT" && return 0
---
%%% MPE
@@@^
    if paresseux "$sub_abs"; then
      continue
    fi
---
    :
%%% MAA
@@@^
arbres_absents() {  # $1 = repo dir
---
arbres_absents() {  # $1 = repo dir
  return 1
%%% MEV
@@@^
  if [ -n "$OUT_LIEN" ] && [ "$_ailleurs" = 0 ]; then
    return 0
  fi
---
%%% MEV2
@@@^
  if [ -L "$ROOT/.agents/state/events" ] && [ "$_ailleurs" = 0 ]; then
---
  if false; then
%%% MEV3
@@@^
evenements_ailleurs() {
---
evenements_ailleurs() {
  return 1
%%% MEV4
@@@^
    if [ "$_p" -ef "$ROOT" ]; then
      return 1
    fi
---
    :
%%% MVD
@@@^
        rm -f "$OUT_DEPOT/semgrep-verdict.json"
---
        :
%%% MK2
@@@^
          [hsmrck]" "*)
            printf '%s\0' "${_rec#??}" ;;
---
          [hsmrck]" "*)
            : ;;
%%% MK3
@@@^
    perte_perimetre "?" "assume-unchanged entries not listed (git ls-files -v failed)"
---
    :
%%% MQ5
@@@
printf '%s\0' "${PROPOSED[@]}" | LC_ALL=C sort -zu
---
printf '%s\0' "${PROPOSED[@]}" | sort -zu
%%% MQ5h
@@@
      } | LC_ALL=C sort -zu )
---
      } | sort -zu )
%%% MQ5a
@@@
printf '%s' "$att_seen" | LC_ALL=C sort -u
---
printf '%s' "$att_seen" | sort -u
%%% MS1
@@@^
    git -C "$ROOT" "${GN[@]}" merge-base "$BASE" HEAD >/dev/null 2>&1 || _mb=$?
---
%%% MS2
@@@^
      SCOPE_NOTE="cible=HEAD-seul (base sans base de fusion) + arbre sale"
      while IFS= read -r -d '' rec && IFS= read -r -d '' f; do
        [ -n "$f" ] || continue
        range_lire "$rec" "$f"
      done < <( files_changed_by HEAD )
---
      SCOPE_NOTE="cible=HEAD-seul (base sans base de fusion) + arbre sale"
%%% MS3
@@@^
    if [ "$_mb" -eq 1 ] && head_is_merge; then
---
    if false; then
%%% MS4
@@@
  git -C "$ROOT" "${GN[@]}" diff --raw -z --no-renames --no-abbrev "$1...HEAD" -- 2>/dev/null \
    || { if [ -n "${SG_SIG:-}" ]; then printf 'since-census\n' >> "$SG_SIG"; fi; }
---
  git -C "$ROOT" "${GN[@]}" diff --raw -z --no-renames --no-abbrev "$1...HEAD" -- 2>/dev/null
%%% MS5
@@@^
    _mb=0
---
    SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
    _mb=0
%%% MS6
@@@^
  index_candidats C "$ROOT/$sub_rel" "$sub_rel/"
---
  :
%%% MS7
@@@^
    elif [ "$_mb" -eq 1 ]; then
---
    elif [ "$_mb" -ge 1 ]; then
%%% MO1
@@@^
  index_candidats C "$ROOT" ""
  _on=""
---
  _on=""
%%% MO2
@@@^
  if [ "$_ok" = 1 ]; then
---
  if false; then
%%% MO3
@@@^
  [ "${#RANGE_P[@]}" -gt 0 ] || return 0
  neutres_racine
---
  return 0
  neutres_racine
%%% MOsw
@@@^
      retenu "${RANGE_P[$i]}" || obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}"
---
      :
%%% MO9
@@@^
  else
    i=0
    while [ "$i" -lt "${#RANGE_P[@]}" ]; do
      obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}"
---
  else
    i=0
    while false; do
      obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}"
%%% MO4
@@@^
reecrire_rapport "$REPORT"
---
:
%%% MO5
@@@^
  if [ "$att_uniq" -ne "${#CIBLES[@]}" ]; then
---
  if [ "$att_uniq" -ne "${#FILES[@]}" ]; then
%%% MO7
@@@^
  if [ -z "$OBJ" ] || ! mkdir "$OBJ/i" "$OBJ/c" 2>/dev/null; then
    perte_perimetre "$tot" "git object(s) not read (index or commit content not scanned)"
---
  if [ -z "$OBJ" ] || ! mkdir "$OBJ/i" "$OBJ/c" 2>/dev/null; then
    :
%%% MO10
@@@^
  [ -n "${OBJ:-}" ] && rm -rf "$OBJ"
---
%%% MO12
@@@^
  while [ "$i" -lt "$tot" ]; do
    case "${etat[$i]}" in
---
  while [ "$i" -lt "$tot" ]; do
    [ "${etat[$i]}" = w ] || OBJ_PATHS+=("$OBJ/${OBJ_K[$i]}/${OBJ_R[$i]}")
    case "${etat[$i]}" in
%%% MO13
@@@
        seen = written.get(rel) == sha
---
        seen = True
%%% MO14
@@@^
    pre=()
    if have timeout; then
      pre=(timeout 1)
---
    j=$((j + 1)); continue
    pre=()
    if have timeout; then
      pre=(timeout 1)
%%% MO15
@@@^
if [ "${#FILES[@]}" -eq 0 ] && [ "${#OBJ_PATHS[@]}" -eq 0 ]; then
---
if false; then
%%% MT1
@@@^
  OBJ="$(mktemp -d "$OUT/semgrep-objs.XXXXXX" 2>/dev/null)" || OBJ=""
---
  OBJ="$(mktemp -d "${TMPDIR:-/tmp}/semgrep-objs.XXXXXX" 2>/dev/null)" || OBJ=""
%%% MO16
@@@^
    [ "$_e" != "$_b" ] || return 0
---
%%% MO17
@@@
[ "$_e" != "$_b" ] || return 0
---
[ "$_e" != "$_b" ] || { perte_perimetre 1 "git object(s) not read (index entry without an extension)"; return 0; }
%%% MO18
@@@^
    OBJ_FILTRE=1
---
    OBJ_FILTRE=0
%%% MOL1
@@@^
  if [ -L "$ROOT/$_ol" ]; then
---
  if false; then
%%% MOL2
@@@^
for _ol in .agents .agents/state .agents/state/local .agents/state/local/sca-reports \
---
for _ol in .agents/state/local/sca-reports \
%%% MOL3
@@@^
           .agents/state/local/sca-reports/audit-log.jsonl \
---
%%% MOL4
@@@^
           .agents/state/local/semgrep-hook .agents/state/local/semgrep-hook/stop-propre; do
---
           .agents/state/local/semgrep-hook/stop-propre; do
%%% MOL5
@@@^
           .agents/state/local/semgrep-hook .agents/state/local/semgrep-hook/stop-propre; do
---
           .agents/state/local/semgrep-hook; do
%%% MOL6
@@@^
           .agents/state/local/semgrep-hook .agents/state/local/semgrep-hook/stop-propre; do
---
           .agents/state/local/semgrep-hook; do
@@@
{ rm -f "$MARKDIR/stop-propre" 2>/dev/null; printf
---
{ printf
%%% MLP
@@@^
  if [ -z "$OUT" ]; then
---
  if true; then
%%% MLPh
@@@^
  if [ -n "$OUT_LIEN" ] && [ -n "$OUT" ]; then
---
  if false; then
%%% MLPc
@@@^
  [ -n "${OUT_PRIVE:-}" ] && rm -rf "$OUT_PRIVE"
---
%%% MLPch
@@@^
  [ -n "${OUT_PRIVE:-}" ] && rm -rf -- "$OUT_PRIVE"
---
%%% MOB1
@@@^
            _fls="$_fls${rec#??}$_nl" ;;
---
            : ;;
%%% MPZ
@@@^
if paresseux "$ROOT"; then
---
if false; then
%%% MPS
@@@^
        if [ "$_PARESSEUX" != 1 ]; then
---
        if true; then
%%% MPN
@@@^
    perte_perimetre "?" "untracked file(s) not enumerated (partial clone, git < 2.45: a skip-worktree .gitignore without its blob would be fetched)"
---
%%% MPD
@@@^
  if paresseux "$ROOT/$sub_rel"; then
---
  if false; then
%%% MM3
@@@^
                manque += 1
---
                pass
%%% MM3s
@@@^
      perte_perimetre "${_r##* }" "git object(s) not scanned while their working-tree twin was (a rule paths: filter judged the machine path)" ;;
---
      : ;;
%%% MSG1
@@@
( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null timeout "${SEMGREP_TIMEOUT:-180}" semgrep
---
( cd "$ROOT" && timeout "${SEMGREP_TIMEOUT:-180}" semgrep
@@@^
  ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null semgrep
---
  ( cd "$ROOT" && semgrep
%%% MSG2
@@@
( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null timeout "${SEMGREP_TIMEOUT:-45}" semgrep
---
( cd "$ROOT" && timeout "${SEMGREP_TIMEOUT:-45}" semgrep
@@@^
    ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null semgrep
---
    ( cd "$ROOT" && semgrep
%%% MORp
@@@^
      case "$f" in
        "$OUT_REL"/*) continue ;;
---
      case "$f" in
        "$OUT_REL"/x) continue ;;
%%% MORh
@@@^
      case "$cand" in
        "$OUT_REL"/*) continue ;;
---
      case "$cand" in
        "$OUT_REL"/x) continue ;;
%%% MNh
@@@^
    relever_neutres
---
    :
%%% MC7h
@@@^
        if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
---
        if true; then
%%% MR0
@@@
show --root --raw
---
show --raw
%%% MR1
@@@^
    if base in v:
---
    if False:
%%% MI1
@@@^
    perte_perimetre 1 "git index of a repository not read (diff-index failed)"
---
%%% MI2
@@@^
      040000)
        _di_vide=$((_di_vide + 1)) ;;
---
      040000)
        : ;;
%%% MI3
@@@^
      perte_perimetre 1 "git index of a repository not read (no empty tree)"
---
      :
%%% MH1
@@@^
    index_candidats C "$ROOT" ""
---
    :
%%% MHC
@@@^
      printf 'obj %s %s\n' "${OBJ_S[$i]}" "${OBJ_L[$i]}"
---
      :
%%% MH2
@@@^
  trap hk_nettoyer EXIT
---
  :
%%% MCL
@@@^
  [ -n "${OBJ:-}" ] && rm -rf "$OBJ"
---
@@@^
  [ -n "${_TMP_FN:-}" ] && rm -f "$_TMP_FN"
---
@@@^
  [ -n "${_TMP_SW:-}" ] && rm -f "$_TMP_SW"
---
%%% MCL1
@@@^
  [ -n "${_TMP_FN:-}" ] && rm -f "$_TMP_FN"
---
%%% MCL2
@@@^
  [ -n "${_TMP_SW:-}" ] && rm -f "$_TMP_SW"
---
%%% MCL3
@@@^
  [ -n "${SG_SIG:-}" ] && rm -f "$SG_SIG"
---
%%% MCL4
@@@^
  [ -n "${SG_LSERR:-}" ] && rm -f "$SG_LSERR"
---
%%% MCL0
@@@^
CLEANUP_OWNER="${BASHPID:-$$}"
trap cleanup EXIT
---
CLEANUP_OWNER="${BASHPID:-$$}"
@@@^
AUDIT_UNPARSED_N=0
---
AUDIT_UNPARSED_N=0
trap cleanup EXIT
%%% MA1
@@@^
  _c="${CFG//\\/\\\\}"
  _c="${_c//\"/\\\"}"
  _c="${_c//"$_nl"/\\n}"
  _c="${_c//"$_tab"/\\t}"
  _c="${_c//"$_cr"/\\r}"
  _c="${_c//[[:cntrl:]]/}"
---
  _c="${CFG//\"/\\\"}"
%%% MA2
@@@^
  _c="${CFG//\\/\\\\}"
---
  _bs='\'; _c="${CFG//"$_bs"/"$_bs$_bs"}"
%%% MUP
@@@^
UNPARSED="$(mktemp "${TMPDIR:-$OUT}/.semgrep-unparsed.XXXXXX")"
---
UNPARSED="$OUT/.semgrep-unparsed.$$"
%%% MNLF
@@@^
  GN+=(--no-lazy-fetch)
---
  :
%%% MXN
@@@^
export GIT_NO_LAZY_FETCH=1
---
:
@@@^
  GN+=(--no-lazy-fetch)
---
  :
%%% MPRC
@@@^
  py_rc=$?
---
  py_rc=0
%%% MPSH
@@@^
  if [ "$_parse_ok" -ne 1 ]; then
---
  if false; then
%%% MPALL
@@@^
  py_rc=$?
---
  py_rc=0
@@@^
  if [ "$_parse_ok" -ne 1 ]; then
---
  if false; then
@@@^
case "$total" in
---
case 0 in
@@@^
  ''|*[!0-9]*)
    # Neither an integer nor a named word
---
  __jamais__)
    # Neither an integer nor a named word
%%% MPMK
@@@^
if [ -z "$LOCFILE" ] || [ -z "$UNPARSED" ]; then
---
if false; then
%%% MPNP
@@@^
  case "$_first" in
---
  case "{" in
%%% MLJ
@@@^
      "0:["*"]")
---
      *)
%%% MPFS
@@@^
    print("MALFORMED"); sys.exit(0)
---
    pass
%%% MPFE
@@@^
    err = d.get("errors")
---
    err = None
%%% MPFP
@@@^
    pth = d.get("paths")
---
    pth = None
%%% MPFC
@@@^
    sc = pth.get("scanned")
---
    sc = None
%%% MPRN
@@@^
  if [ "$_res_ok" -ne 1 ]; then
---
  if false; then
%%% MHFS
@@@^
    degrade("COVERAGE DEGRADED: SAST hook — semgrep report malformed (no 'results' list of objects, or errors/paths mistyped)"); sys.exit(0)
---
    pass
%%% MHFE
@@@^
    errs = doc.get("errors")
---
    errs = None
%%% MHFP
@@@^
    pths = doc.get("paths")
---
    pths = None
%%% MHFC
@@@^
    scn = pths.get("scanned")
---
    scn = None
%%% MHBELT
@@@^
  if [ -z "$rverdict" ]; then
---
  if false; then
%%% MPTR
@@@^
  if [ "$_fin_ok" -ne 1 ]; then
---
  if false; then
SGMUTDEF
SG_MUT_PY='
import sys
src, dst, nom, defs = sys.argv[1:5]
t = open(src, encoding="utf-8").read()
blocs = {}
cur = None
for l in open(defs, encoding="utf-8").read().split("\n"):
    if l.startswith("%%% "):
        cur = l[4:].strip()
        blocs[cur] = []
    elif cur is not None:
        blocs[cur].append(l)
if nom not in blocs:
    sys.exit(4)
segs = []
s = None
for l in blocs[nom]:
    if l in ("@@@", "@@@^"):
        s = [l == "@@@^", [], [], 0]
        segs.append(s)
    elif s is not None:
        if l == "---" and s[3] == 0:
            s[3] = 1
        else:
            s[1 + s[3]].append(l)
if not segs:
    sys.exit(4)
for debut, a, r, ph in segs:
    while r and r[-1] == "":
        r.pop()
    if ph != 1 or not a:
        sys.exit(4)
    a = "\n".join(a)
    r = "\n".join(r)
    if debut:
        a = "\n" + a
        r = ("\n" + r) if r else ""
    if t.count(a) != 1:
        sys.exit(3)
    t = t.replace(a, r, 1)
open(dst, "w", encoding="utf-8").write(t)
'
SG_MUTS="$(grep '^%%% ' "$SG_W/mut.def" | cut -c5-)"
for _m in $SG_MUTS; do
  "$PY" -c "$SG_MUT_PY" "$SCRIPT" "$SG_MUT/$_m.sh" "$_m" "$SG_W/mut.def" \
    || fail "(sgm) mutant $_m : une ancre n'apparaît pas EXACTEMENT une fois — un mutant qui ne mute rien est un témoin muet"
  cmp -s "$SCRIPT" "$SG_MUT/$_m.sh" && fail "(sgm) mutant $_m : identique au script"
  "$SUITE_BASH" -n "$SG_MUT/$_m.sh" 2>/dev/null || fail "(sgm) mutant $_m : ne parse pas — il rougirait pour une autre raison"
done
ok "(sgm) $(printf '%s\n' $SG_MUTS | grep -c .) mutants fabriqués, chaque ancre vue EXACTEMENT une fois, chacun parse"

# ---- runners and checks -----------------------------------------------------
sg_run() {  # $1 script  $2 dir  [args…] — SG_PATH: PATH prefix (default the stub); SG_TMP: TMPDIR (default fresh) -> SG_OUT (2>&1) SG_RC SG_AUDIT SG_LAST_TMP SG_LAST_DIR
  local _s="$1" _d="$2" _p="${SG_PATH-$SG_PATH_DEF}" _t="${SG_TMP:-}"
  shift 2
  if [ -z "$_t" ]; then _t="$(mktemp -d "$SG_W/t.XXXXXX")"; fi
  SG_LAST_TMP="$_t"; SG_LAST_DIR="$_d"; SG_ERR=""
  SG_OUT="$( cd "$_d" && export PATH="${_p:+$_p:}$PATH" TMPDIR="$_t" SEMGREP_CONFIG="$RULESET" && "$SUITE_BASH" "$_s" "$@" 2>&1 )"; SG_RC=$?
  SG_AUDIT="$(tail -1 "$_d/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null)"
}
sg_hook() {  # $1 script  $2 dir  $3 session id -> SG_OUT (stdout) SG_ERR SG_RC SG_AUDIT SG_LAST_TMP SG_LAST_DIR
  local _s="$1" _d="$2" _p="${SG_PATH-$SG_PATH_DEF}" _t="${SG_TMP:-}"
  if [ -z "$_t" ]; then _t="$(mktemp -d "$SG_W/t.XXXXXX")"; fi
  SG_LAST_TMP="$_t"; SG_LAST_DIR="$_d"
  printf '{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"%s"}' "$3" \
    | ( cd "$_d" && export PATH="${_p:+$_p:}$PATH" TMPDIR="$_t" AGENTS_HOOK_HOST=claude SEMGREP_CONFIG="$RULESET" && "$SUITE_BASH" "$_s" --hook --event=stop ) >"$SG_W/ho" 2>"$SG_W/he"
  SG_RC=$?
  SG_OUT="$(cat "$SG_W/ho")"; SG_ERR="$(cat "$SG_W/he")"
  SG_AUDIT="$(tail -1 "$_d/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null)"
}
sg_rc() {
  [ "$SG_RC" -eq "$2" ] || fail "$1 : rc $SG_RC, attendu $2 — sortie : $SG_OUT ${SG_ERR:-}"
}
sg_dit() {
  case "$SG_OUT" in
    *"$2"*)
      return 0 ;;
  esac
  fail "$1 : « $2 » absent — sortie : $SG_OUT"
}
sg_tait() {
  case "$SG_OUT" in
    *"$2"*)
      fail "$1 : « $2 » présent — sortie : $SG_OUT" ;;
  esac
  return 0
}
sg_err() {
  case "$SG_ERR" in
    *"$2"*)
      return 0 ;;
  esac
  fail "$1 : « $2 » absent de stderr — stderr : $SG_ERR"
}
sg_adit() {
  case "$SG_AUDIT" in
    *"$2"*)
      return 0 ;;
  esac
  fail "$1 : audit sans « $2 » : $SG_AUDIT"
}
sg_benin() {  # $1 label — none of the four benign sentences
  sg_tait "$1" 'clean on the diff'; sg_tait "$1" 'nothing to scan'
  sg_tait "$1" "rien à lire, ce n'est pas un aveuglement"; sg_tait "$1" 'couverture portable par attestation'
}
sg_sansverdict() {  # $1 label  $2 repo
  [ -e "$2/.agents/state/local/sca-reports/semgrep-verdict.json" ] && fail "$1 : un verdict commun rendu sur un périmètre incomplet"
  return 0
}
sg_vide() {  # $1 label — the run's TMPDIR holds nothing, and no `semgrep-objs.*` is left under the repo's $OUT
  local _o
  [ -z "$(ls -A "$SG_LAST_TMP" 2>/dev/null)" ] || fail "$1 : TMPDIR non vide après le run : $(ls -A "$SG_LAST_TMP" | tr '\n' ' ')"
  for _o in "$SG_LAST_DIR"/.agents/state/local/sca-reports/semgrep-objs.*; do
    [ -e "$_o" ] && fail "$1 : objets laissés sous \$OUT après le run : $_o"
  done
  return 0
}
sg_marque() { [ -e "$SG_T/$1" ]; }
sg_rm() { rm -f "$SG_T"/*; }
sg_aucune() {  # $1 label  "$@" markers that must NOT be born
  local _l="$1" _k; shift
  for _k in "$@"; do
    sg_marque "$_k" && fail "$_l : le témoin « $_k » est né — un code du dépôt scanné a été EXÉCUTÉ ; sortie : $SG_OUT"
  done
  return 0
}
sg_nu() {  # $1 label  $2 marker  "$@" — the NAKED command that follows MUST make it born
  local _l="$1" _k="$2"; shift 2
  sg_rm
  "$@" >/dev/null 2>&1
  sg_marque "$_k" || fail "$_l : témoin pairé MUET — la commande nue ne fait pas naître « $_k », la fixture ne prouve rien"
  sg_rm
}
sg_bras() {  # $1 label  $2 run fn (reads SG_S)  $3 check fn  [mutants…] — each mutant must redden the check
  local _l="$1" _x="$2" _c="$3" _m; shift 3
  SG_S="$SCRIPT"; "$_x"; "$_c"
  for _m in "$@"; do
    SG_S="$SG_MUT/$_m.sh"; "$_x"
    ( "$_c" ) >/dev/null 2>&1 && fail "(sgm) $_m : le mutant SURVIT à $_l — le bras ne pourrait pas rougir ; sortie : $SG_OUT ${SG_ERR:-}"
    SG_REDS="$SG_REDS$_m "
  done
  SG_S="$SCRIPT"
}
sg_saute() {  # $1 mutant(s)  $2 said reason — a SKIP is said, never silent
  local _m
  for _m in $1; do SG_SKIPPED="$SG_SKIPPED$_m "; done
  echo "  SKIP (sgm) mutant(s) $1 : $2"
}
# Fake gits: $1 = directory name under SG_W; stdin = the body after the `real=` line.
SG_REEL='real="$(cat "$(dirname "$0")/real")"'
sg_fauxgit() {
  mkdir -p "$SG_W/$1"; printf '%s' "$SG_REAL_GIT" > "$SG_W/$1/real"
  { printf '%s\n' '#!/usr/bin/env bash'; printf '%s\n' "$SG_REEL"; cat; } > "$SG_W/$1/git"
  chmod +x "$SG_W/$1/git"
}
# Fixtures: a throwaway repo, `.agents/state/local/` ignored.
sg_repo() {  # -> SG_R, no commit
  SG_R="$(mktemp -d "$SG_W/r.XXXXXX")"; assert_tmpdir "$SG_R"
  $SG_G init -q "$SG_R"
  mkdir -p "$SG_R/.agents"; printf 'state/local/\n' > "$SG_R/.agents/.gitignore"
}
sg_ecrire() {  # $1 path relative to SG_R  $2 printf-format content
  case "$1" in
    */*) mkdir -p "$SG_R/${1%/*}" ;;
  esac
  printf "$2" > "$SG_R/$1"
}
sg_base() {  # sg_repo + "<path> <content>"… committed, then an EMPTY commit (HEAD's own commit changes nothing)
  sg_repo
  while [ "$#" -ge 2 ]; do sg_ecrire "$1" "$2"; shift 2; done
  $SG_G -C "$SG_R" add -A >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -qm base >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -q --allow-empty -m vide >/dev/null 2>&1
}

# ---- (sgc*) THE CENSUS RUNS NO CODE OF THE REPOSITORY (T-01M4Z24V0J813T40XRW3S4VW67)
# Measured at c2a42ba2 (x1/x2/x3, r2/v.sh): the gate AND the hook Stop RAN the
# scanned repository's core.fsmonitor and filter.<d>.clean, at the root and in a
# submodule; `-c` did not neutralize a driver named `a=b`; `git show` ran
# gpg.program under log.showSignature; `=all` hid a gitlink turned into a file.
printf '#!/bin/sh\ntouch "%s/fsmonitor"\nexit 1\n' "$SG_T" > "$SG_W/fsm.sh"
printf '#!/bin/sh\ntouch "%s/fsmonitor-sub"\nexit 1\n' "$SG_T" > "$SG_W/fsm-sub.sh"
printf '#!/bin/sh\ntouch "%s/gpg"\nexit 1\n' "$SG_T" > "$SG_W/gpg.sh"
chmod +x "$SG_W/fsm.sh" "$SG_W/fsm-sub.sh" "$SG_W/gpg.sh"
: > "$SG_W/vide.cfg"
SG_BENIN='def f(cmd):\n    return cmd\n'

sg_fx_fsm() {  # a tracked a.py rewritten with a sink; the repo's core.fsmonitor writes a marker
  sg_base a.py 'x = 1\n'
  git -C "$SG_R" config core.fsmonitor "$SG_W/fsm.sh"
  sg_ecrire a.py "$SG_SINK"
}
sg_x_sgc1()   { sg_fx_fsm; sg_rm; sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc1()  { sg_rc "(sgc1)" 1; sg_aucune "(sgc1)" fsmonitor; }
sg_x_sgc1h()  { sg_fx_fsm; sg_rm; sg_hook "$SG_S" "$SG_R" sgc1h; }
sg_ok_sgc1h() { sg_rc "(sgc1h)" 2; sg_aucune "(sgc1h)" fsmonitor; }
sg_fx_fsm; sg_nu "(sgc1) témoin pairé : le diff nu lance le fsmonitor du dépôt" fsmonitor git -C "$SG_R" diff --name-only HEAD
sg_bras "(sgc1)" sg_x_sgc1 sg_ok_sgc1 MC1
sg_bras "(sgc1h)" sg_x_sgc1h sg_ok_sgc1h MC1h
ok "(sgc1)(sgc1h) core.fsmonitor du dépôt scanné : porte rc 1, Stop rc 2, fsmonitor jamais lancé (témoin pairé : le diff nu le lance) ; MC1/MC1h rougissent"

sg_fx_filtre() {  # a.py rewritten at the SAME size, its index entry RACY (git must read it: the clean filter runs), k.py a sink
  # (exec-critic of 7c78f87f, B1) Under `diff.autoRefreshIndex=false` git reads
  # a.py — and runs the clean filter — only when its index entry is RACY: stat
  # equal to the file's, mtime not older than the index. Left to the clock, that
  # held only when a.py was rewritten in the SAME SECOND as the index write
  # (exec-critic mc6probe: 27/30), so MC6 survived 2 replays of 2 under
  # /bin/bash 3.2. Now forced: a.py's mtime pinned in the future (touch -t)
  # BEFORE the index records it (update-index --refresh, no driver configured
  # yet: no marker), then pinned again after the same-size rewrite;
  # core.checkStat=minimal keeps ctime and inode out of the comparison. Measured
  # (devmulti-sg10/b1probe.sh): the naked census form ran the filter 20/20, the
  # neutralized form 0/20. The paired witness of (sgc6) replays it each run.
  # The pin is 2099 (exec-critic of 03c4ce7a: a 2030 pin stops being in the
  # future on 2030-01-01, and the entry would stop being racy — the paired
  # witness would then fail LOUDLY, never pass in silence).
  sg_base a.py 'x = 1\n' k.py 'y = 1\n' .gitattributes '*.py filter=evil\n'
  git -C "$SG_R" config core.checkStat minimal
  touch -t 209901010000 "$SG_R/a.py"
  git -C "$SG_R" update-index -q --refresh >/dev/null 2>&1
  git -C "$SG_R" config filter.evil.clean "sh -c 'touch $SG_T/clean; cat'"
  sg_ecrire a.py 'x = 2\n'; touch -t 209901010000 "$SG_R/a.py"; sg_ecrire k.py "$SG_SINK"
}
sg_x_sgc2()   { sg_fx_filtre; sg_rm; sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc2()  { sg_rc "(sgc2)" 1; sg_aucune "(sgc2)" clean; sg_tait "(sgc2)" "could not be neutralized"; }
sg_x_sgc2h()  { sg_fx_filtre; sg_rm; sg_hook "$SG_S" "$SG_R" sgc2h; }
sg_ok_sgc2h() { sg_rc "(sgc2h)" 2; sg_aucune "(sgc2h)" clean; }
sg_fx_filtre; sg_nu "(sgc2) témoin pairé : le diff nu lance le filtre clean du dépôt" clean git -C "$SG_R" diff --name-only HEAD
sg_bras "(sgc2)" sg_x_sgc2 sg_ok_sgc2 MC2
sg_bras "(sgc2h)" sg_x_sgc2h sg_ok_sgc2h MC2
ok "(sgc2)(sgc2h) filtre clean du dépôt : diff lancé (k.py trouvé, rc 1 / Stop rc 2), filtre jamais lancé (témoin pairé) ; MC2 rougit"

sg_fx_sub() {  # mk_super_sg; the SUBMODULE's own git dir carries a fsmonitor and a clean filter
  # sub/vuln.py is rewritten at the SAME size (still a sink): a `git status` of
  # the submodule must read it, through ITS clean filter. Measured while writing
  # this arm: the fsmonitor alone does not tell `=dirty` from no option — the
  # `-c core.fsmonitor=false` of "${GN[@]}" reaches the submodule's child too
  # (GIT_CONFIG_PARAMETERS) — the submodule's own filter is what `=dirty` cuts.
  local _gd
  SG_R="$(mk_super_sg)"
  _gd="$(git -C "$SG_R/sub" rev-parse --absolute-git-dir)"
  git --git-dir="$_gd" config core.fsmonitor "$SG_W/fsm-sub.sh"
  git --git-dir="$_gd" config filter.evil.clean "sh -c 'touch $SG_T/clean-sub; cat'"
  printf '*.py filter=evil\n' > "$SG_R/sub/.gitattributes"
  printf 'import os\n\n\ndef run(cmx):\n    os.system("echo " + cmx)\n' > "$SG_R/sub/vuln.py"
}
sg_x_sgc3()  { sg_fx_sub; sg_rm; sg_run "$SG_S" "$SG_R"; ill_super_fin "$SG_R"; }
sg_ok_sgc3() { sg_rc "(sgc3)" 1; sg_aucune "(sgc3)" fsmonitor-sub clean-sub; sg_adit "(sgc3)" "vuln.py"; }
sg_fx_sub; sg_nu "(sgc3) témoin pairé : le diff nu du super-projet lance le fsmonitor du sous-module" fsmonitor-sub git -C "$SG_R" diff --name-only HEAD
ill_super_fin "$SG_R"
sg_bras "(sgc3)" sg_x_sgc3 sg_ok_sgc3 MC3 MC3b
ok "(sgc3) sous-module à fsmonitor + filtre propres : rc 1, sub/vuln.py lu, rien lancé (témoin pairé) ; MC3 (=dirty ôté), MC3b (GN ôté de l'énumération) rougissent"

sg_fx_aeqb() {  # a driver NAMED `a=b`: `-c filter.a=b.clean=` cuts at the first `=` and neutralizes nothing
  sg_base a.py 'x = 1\n' k.py 'y = 1\n' .gitattributes '*.py filter=a=b\n'
  git -C "$SG_R" config 'filter.a=b.clean' "sh -c 'touch $SG_T/clean-eq; cat'"
  sg_ecrire a.py 'x = 2\n'; sg_ecrire k.py "$SG_SINK"
}
sg_x_sgc4()  { sg_fx_aeqb; sg_rm; sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc4() { sg_rc "(sgc4)" 1; sg_aucune "(sgc4)" clean-eq; }
sg_fx_aeqb; sg_nu "(sgc4) témoin pairé : -c filter.a=b.clean= ne neutralise PAS" clean-eq git -c 'filter.a=b.clean=' -C "$SG_R" diff --name-only HEAD
sg_bras "(sgc4)" sg_x_sgc4 sg_ok_sgc4 MC4
ok "(sgc4) pilote nommé a=b : --config-env le neutralise, rc 1, rien lancé (témoin pairé : la forme -c le lance) ; MC4 rougit"

sg_x_sgc5()  { sg_fx_filtre; git -C "$SG_R" config filter.evil.required true; sg_rm; sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc5() { sg_rc "(sgc5)" 1; sg_tait "(sgc5)" "census FAILED"; sg_aucune "(sgc5)" clean; }
sg_bras "(sgc5)" sg_x_sgc5 sg_ok_sgc5 MC5
ok "(sgc5) filter.evil.required=true : k.py listé (rc 1), aucun rc 128 du diff ; MC5 rougit"

sg_x_sgc6()  { sg_fx_filtre; sg_rm; GIT_CONFIG="$SG_W/vide.cfg" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc6() { sg_rc "(sgc6)" 1; sg_aucune "(sgc6)" clean; }
# PAIRED witness (B1): the census's own form, naked (no driver neutralized, no
# stat-only refresh), RUNS the filter on this fixture — the entry is racy, so
# the observable MC6 needs exists on every run, never by the clock.
sg_fx_filtre; sg_nu "(sgc6) témoin pairé : le diff NU sans rafraîchissement d'index (la forme du recensement) lance le filtre — entrée racy forcée" clean \
  git -C "$SG_R" -c core.fsmonitor=false -c diff.autoRefreshIndex=false diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty HEAD --
sg_bras "(sgc6)" sg_x_sgc6 sg_ok_sgc6 MC6
ok "(sgc6) GIT_CONFIG=<vide> exporté : les pilotes sont lus quand même (unset), filtre jamais lancé (témoin pairé : la forme nue du recensement le lance, entrée racy forcée) ; MC6 rougit"

sg_fauxgit ce129 <<'SGF'
for a in "$@"; do
  case "$a" in
    --config-env=*)
      exit 129 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit cedrop <<'SGF'
n=()
for a in "$@"; do
  case "$a" in
    --config-env=*)
      : ;;
    *)
      n+=("$a") ;;
  esac
done
exec "$real" "${n[@]}"
SGF
sg_fauxgit cfg2 <<'SGF'
f=0; ce=0
for a in "$@"; do
  case "$a" in
    --config-env=*)
      ce=1 ;;
    "^filter"*)
      f=1 ;;
  esac
done
[ "$f" = 1 ] && [ "$ce" = 0 ] && exit 2
exec "$real" "$@"
SGF
sg_ok_nonneutre() {  # $1 label — the diff NOT run, the loss said, never a clean
  sg_rc "$1" 0; sg_aucune "$1" clean
  sg_dit "$1" "tracked modified file(s) not enumerated (a filter driver could not be neutralized)"
  sg_adit "$1" '"couverture":"DEGRADED"'; sg_sansverdict "$1" "$SG_R"; sg_benin "$1"
}
sg_x_sgc7()   { sg_fx_filtre; sg_rm; SG_PATH="$SG_W/ce129:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc7()  { sg_ok_nonneutre "(sgc7)"; }
sg_x_sgc7b()  { sg_fx_filtre; sg_rm; SG_PATH="$SG_W/cedrop:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc7b() { sg_ok_nonneutre "(sgc7b)"; }
sg_x_sgc7c()  { sg_fx_filtre; sg_rm; SG_PATH="$SG_W/cfg2:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc7c() { sg_ok_nonneutre "(sgc7c)"; }
sg_x_sgc7h()  { sg_fx_filtre; sg_rm; SG_PATH="$SG_W/ce129:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgc7h; }
sg_ok_sgc7h() {
  sg_rc "(sgc7h)" 0; sg_aucune "(sgc7h)" clean
  sg_dit "(sgc7h)" '"systemMessage": "COVERAGE DEGRADED'; sg_err "(sgc7h)" "could not be neutralized"
}
sg_bras "(sgc7)" sg_x_sgc7 sg_ok_sgc7 MC7
sg_bras "(sgc7b)" sg_x_sgc7b sg_ok_sgc7b MC7b
sg_bras "(sgc7c)" sg_x_sgc7c sg_ok_sgc7c MC7c
sg_bras "(sgc7h)" sg_x_sgc7h sg_ok_sgc7h MC7h MNh
ok "(sgc7)(sgc7b)(sgc7c)(sgc7h) git qui refuse --config-env / l'ignore à la relecture / 1re lecture rc 2 : diff NON lancé, perte dite, DEGRADED, rc 0, aucun verdict ; le Stop le dit aussi ; MC7/MC7b/MC7c/MC7h/MNh rougissent"

sg_fx_sig() {  # a SIGNED root commit; log.showSignature on; gpg.program writes a marker
  local _t _c
  sg_repo; sg_ecrire k.py "$SG_SINK"
  git -C "$SG_R" add k.py
  _t="$(git -C "$SG_R" write-tree)"
  printf 'tree %s\nauthor t <t@t> 1 +0000\ncommitter t <t@t> 1 +0000\ngpgsig -----BEGIN PGP SIGNATURE-----\n \n x\n -----END PGP SIGNATURE-----\n\nsigne\n' "$_t" > "$SG_W/sig.commit"
  _c="$(git -C "$SG_R" hash-object -t commit -w "$SG_W/sig.commit")"
  git -C "$SG_R" update-ref refs/heads/main "$_c"
  git -C "$SG_R" config log.showSignature true
  git -C "$SG_R" config gpg.program "$SG_W/gpg.sh"
}
sg_x_sgc8()  { sg_fx_sig; sg_rm; sg_run "$SG_S" "$SG_R" --at HEAD; }
sg_ok_sgc8() { sg_rc "(sgc8)" 1; sg_aucune "(sgc8)" gpg; }
sg_fx_sig; sg_nu "(sgc8) témoin pairé : git show nu lance gpg.program" gpg git -C "$SG_R" show --name-only HEAD
sg_bras "(sgc8)" sg_x_sgc8 sg_ok_sgc8 MC8
ok "(sgc8) pointe signée + log.showSignature : --at HEAD rc 1, gpg.program jamais lancé (témoin pairé) ; MC8 rougit"

sg_fx_glf() {  # a gitlink KEPT in the index whose working-tree directory became a regular file (sink)
  local _u
  _u="$(mktemp -d "$SG_W/u.XXXXXX")"; $SG_G init -q "$_u"; printf 'y = 1\n' > "$_u/s.py"
  $SG_G -C "$_u" add -A >/dev/null 2>&1; $SG_G -C "$_u" commit -qm s >/dev/null 2>&1
  sg_base README.md 'r\n'
  $SG_G -C "$SG_R" submodule -q add "$_u" tool.py >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -qm sub >/dev/null 2>&1
  # An EMPTY commit on top: the HEAD-alone range must not bring tool.py in by
  # itself — only the TREE diff may list it (measured: without it MC9 survived).
  $SG_G -C "$SG_R" commit -q --allow-empty -m vide >/dev/null 2>&1
  rm -rf "$SG_R/tool.py"; sg_ecrire tool.py "$SG_SINK"
}
sg_x_sgc9()  { sg_fx_glf; sg_run "$SG_S" "$SG_R"; }
sg_ok_sgc9() { sg_rc "(sgc9)" 1; sg_adit "(sgc9)" "tool.py:3"; }
sg_bras "(sgc9)" sg_x_sgc9 sg_ok_sgc9 MC9
ok "(sgc9) gitlink devenu fichier puits : =dirty le liste, rc 1 ; MC9 (=all) rougit"

# ---- (sgl*) PARTIAL CLONES AND SKIP-WORKTREE .gitignore (T-01M4Z24V0J813T40XRW3S4VW67)
# A blob:none clone whose `remote.origin.uploadpack` writes a marker: a lazy
# fetch RUNS that command (measured, pc-gl-suites/r5/sg.sh: hook Stop rc 0 and
# the marker BORN at c2a42ba2). C18 (sg3/sgneg.sh): under the export ALONE the
# `!keep.py` negation of a skip-worktree d/.gitignore without its blob was lost
# and the untracked sink d/keep.py never listed — a mute rc 0 at the Stop.
sg_origine() {  # "<path> <content>"… committed in an origin that serves filters -> SG_O
  SG_O="$(mktemp -d "$SG_W/o.XXXXXX")"; assert_tmpdir "$SG_O"
  $SG_G init -q "$SG_O"; git -C "$SG_O" config uploadpack.allowFilter true
  while [ "$#" -ge 2 ]; do
    case "$1" in
      */*)
        mkdir -p "$SG_O/${1%/*}" ;;
    esac
    printf "$2" > "$SG_O/$1"
    $SG_G -C "$SG_O" add -f -- "$1" >/dev/null 2>&1
    shift 2
  done
  $SG_G -C "$SG_O" commit -qm c0 >/dev/null 2>&1
}
sg_partiel() {  # $1 origin  "$@" sparse patterns -> SG_R: blob:none clone, sparse, lazy marker wired, .agents/ excluded
  local _o="$1"; shift
  SG_R="$(mktemp -d "$SG_W/q.XXXXXX")/q"
  $SG_G clone -q --filter=blob:none --no-checkout "file://$_o" "$SG_R" >/dev/null 2>&1
  git -C "$SG_R" config protocol.file.allow always
  $SG_G -C "$SG_R" sparse-checkout set --no-cone "$@" >/dev/null 2>&1
  $SG_G -C "$SG_R" checkout -q main >/dev/null 2>&1
  printf '.agents/\n' >> "$SG_R/.git/info/exclude"
  git -C "$SG_R" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
}
sg_sans_blob() {  # $1 label  $2 repo  $3 path — the fixture is REFUSED (FAIL, never SKIP) when the blob is present
  local _s
  _s="$(git -C "$2" rev-parse "HEAD:$3" 2>/dev/null)"
  [ -n "$_s" ] || fail "$1 : fixture REFUSÉE — $3 absent de HEAD"
  GIT_NO_LAZY_FETCH=1 git -C "$2" cat-file -e "$_s" 2>/dev/null \
    && fail "$1 : fixture REFUSÉE — le blob de $3 est présent, le bras ne prouverait rien"
  return 0
}
if sg_git_ge 2 45; then
  sg_fx_lazy() {
    sg_origine seed.txt 'seed\n' d/keep.txt 'keep\n' d/.gitignore '*.log\n'
    sg_partiel "$SG_O" /seed.txt /d/keep.txt
    sg_ecrire d/u.py 'x = 1\n'; sg_ecrire d/u.txt 'y\n'
  }
  sg_x_sgl1()   { sg_fx_lazy; sg_rm; sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl1()  { sg_aucune "(sgl1)" lazy; }
  sg_x_sgl1h()  { sg_fx_lazy; sg_rm; sg_hook "$SG_S" "$SG_R" sgl1h; }
  sg_ok_sgl1h() { sg_aucune "(sgl1h)" lazy; }
  sg_fx_lazy; sg_sans_blob "(sgl1)" "$SG_R" d/.gitignore
  sg_nu "(sgl1) témoin pairé : ls-files --others NU, sans l'export, lance l'uploadpack" lazy \
    env -u GIT_NO_LAZY_FETCH git -C "$SG_R" ls-files --others --exclude-standard
  # MXN removes BOTH defenses (the export AND `--no-lazy-fetch` in GN): on this
  # git each one alone refuses the fetch — measured, MX alone (the export only)
  # SURVIVED (sgl1) once the flag rode on GN (closing review 2, F2). MX keeps
  # its place for the (brut) pin, which still refuses it; its arm is said.
  sg_bras "(sgl1)" sg_x_sgl1 sg_ok_sgl1 MXN
  sg_bras "(sgl1h)" sg_x_sgl1h sg_ok_sgl1h MXN
  sg_saute "MX" "git $_sg_v a --no-lazy-fetch : le drapeau passé par GN refuse seul le rapatriement, l'export ôté seul ne peut rougir aucun bras ; MXN (les deux ôtés) porte (sgl1)(sgl1h), l'épingle (brut) refuse MX"
  ok "(sgl1)(sgl1h) clone blob:none, .gitignore skip-worktree sans blob : porte et Stop, uploadpack jamais lancé (témoin pairé) ; MXN rougit"

  # (sgl1n)(sgl1nh) closing review 2, F2 (fixture fxP): a git that ACCEPTS
  # `--no-lazy-fetch` but IGNORES the exported variable. paresseux then judges
  # the clone safe, and before the flag joined GN the gate ran the uploadpack
  # (measured: gate `lazy` born; the Stop alone, on a fresh fixture, too). Now
  # the flag rides on every git that carries GN: neither runs it. MNLF (the
  # flag left out of GN) makes it born at the gate AND at the Stop. The fake
  # reads the real git's path from its data file (sg_fauxgit), never printf'd.
  sg_fauxgit g244 <<'SGF'
for a in "$@"; do [ "$a" = --no-lazy-fetch ] && exec "$real" "$@"; done
unset GIT_NO_LAZY_FETCH
exec "$real" "$@"
SGF
  sg_x_sgl1n()   { sg_fx_lazy; sg_rm; SG_PATH="$SG_W/g244:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl1n()  { sg_aucune "(sgl1n)" lazy; }
  sg_x_sgl1nh()  { sg_fx_lazy; sg_rm; SG_PATH="$SG_W/g244:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl1nh; }
  sg_ok_sgl1nh() { sg_aucune "(sgl1nh)" lazy; }
  sg_fx_lazy; sg_sans_blob "(sgl1n)" "$SG_R" d/.gitignore
  sg_nu "(sgl1n) témoin pairé : sous ce git l'export est INERTE (sans le drapeau)" lazy \
    env GIT_NO_LAZY_FETCH=1 "$SG_W/g244/git" -C "$SG_R" ls-files --others --exclude-standard
  sg_bras "(sgl1n)" sg_x_sgl1n sg_ok_sgl1n MNLF
  sg_bras "(sgl1nh)" sg_x_sgl1nh sg_ok_sgl1nh MNLF
  ok "(sgl1n)(sgl1nh) git qui accepte --no-lazy-fetch mais ignore GIT_NO_LAZY_FETCH, même fixture : porte et Stop, uploadpack jamais lancé (témoin pairé : l'export seul est inerte sous ce git) ; MNLF rougit"

  sg_fx_c18() {  # root `*.py`, `!keep.py` in a skip-worktree d/.gitignore without its blob, untracked sink d/keep.py
    sg_origine seed.txt 'seed\n' .gitignore '*.py\n' d/keep.txt 'keep\n' d/.gitignore '!keep.py\n'
    sg_partiel "$SG_O" /seed.txt /.gitignore /d/keep.txt
    sg_ecrire d/keep.py "$SG_SINK"; sg_ecrire d/other.py 'x\n'
  }
  sg_x_sgl2()   { sg_fx_c18; sg_rm; sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl2()  {
    sg_rc "(sgl2)" 0; sg_dit "(sgl2)" "1 skip-worktree .gitignore file(s) unreadable (partial clone)"
    sg_benin "(sgl2)"; sg_sansverdict "(sgl2)" "$SG_R"; sg_aucune "(sgl2)" lazy
  }
  sg_x_sgl2h()  { sg_fx_c18; sg_rm; sg_hook "$SG_S" "$SG_R" sgl2h; }
  sg_ok_sgl2h() {
    sg_rc "(sgl2h)" 0; sg_dit "(sgl2h)" '"systemMessage": "COVERAGE DEGRADED'
    sg_err "(sgl2h)" "skip-worktree .gitignore"; sg_aucune "(sgl2h)" lazy
  }
  sg_fx_c18; sg_sans_blob "(sgl2)" "$SG_R" d/.gitignore
  # PAIRED witness of C1: WITHOUT the export and the flag (MXN — either one
  # alone refuses the fetch on this git, closing review 2 F2) the same fixture
  # fetches the blob (marker BORN) and the Stop finds d/keep.py (rc 2) — so what
  # the refusal turned into a mute rc 0 was a hidden sink.
  sg_rm; sg_hook "$SG_MUT/MXN.sh" "$SG_R" sgl2h-t
  sg_marque lazy || fail "(sgl2h) témoin pairé MUET : sans l'export ni le drapeau, l'uploadpack devait être lancé"
  [ "$SG_RC" -eq 2 ] || fail "(sgl2h) témoin pairé : sans l'export ni le drapeau, d/keep.py devait être trouvé (rc 2), rc $SG_RC — $SG_ERR"
  sg_bras "(sgl2)" sg_x_sgl2 sg_ok_sgl2 MG
  sg_bras "(sgl2h)" sg_x_sgl2h sg_ok_sgl2h MGh
  ok "(sgl2)(sgl2h) C18 : négation perdue => DEGRADED(1) skip-worktree .gitignore, porte rc 0 sans phrase bénigne ni verdict, Stop rc 0 + systemMessage, jamais muet (témoin pairé : sans l'export, rc 2) ; MG/MGh rougissent"

  sg_fx_c18s() {  # C18 inside a SUBMODULE (a blob:none clone adopted by `submodule add`)
    local _s
    sg_origine seed.txt 'seed\n' .gitignore '*.py\n' d/keep.txt 'keep\n' d/.gitignore '!keep.py\n'
    sg_base README.md 'r\n'; _s="$SG_R"
    $SG_G clone -q --filter=blob:none --no-checkout "file://$SG_O" "$_s/sub" >/dev/null 2>&1
    git -C "$_s/sub" config protocol.file.allow always
    $SG_G -C "$_s/sub" sparse-checkout set --no-cone /seed.txt /.gitignore /d/keep.txt >/dev/null 2>&1
    $SG_G -C "$_s/sub" checkout -q main >/dev/null 2>&1
    $SG_G -C "$_s" submodule add -q "file://$SG_O" sub >/dev/null 2>&1
    $SG_G -C "$_s" commit -qm sub >/dev/null 2>&1
    $SG_G -C "$_s" commit -q --allow-empty -m vide >/dev/null 2>&1
    git -C "$_s/sub" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
    printf "$SG_SINK" > "$_s/sub/d/keep.py"
  }
  sg_x_sgl2s()  { sg_fx_c18s; sg_rm; sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl2s() {
    sg_rc "(sgl2s)" 0; sg_dit "(sgl2s)" "1 skip-worktree .gitignore file(s) unreadable (partial clone)"
    sg_benin "(sgl2s)"; sg_sansverdict "(sgl2s)" "$SG_R"; sg_aucune "(sgl2s)" lazy
  }
  sg_fx_c18s; sg_sans_blob "(sgl2s)" "$SG_R/sub" d/.gitignore
  [ -e "$SG_R/sub/.git" ] || fail "(sgl2s) fixture REFUSÉE : sub n'est pas un sous-module initialisé"
  sg_bras "(sgl2s)" sg_x_sgl2s sg_ok_sgl2s MG2
  ok "(sgl2s) C18 dans un sous-module : DEGRADED(1), rc 0, aucune phrase bénigne, aucun verdict ; MG2 rougit"

  sg_fx_c18n() {  # the C18 layout with NOTHING ignored under d/ (d/u.txt alone): nothing can be hidden
    sg_origine seed.txt 'seed\n' .gitignore '*.py\n' d/keep.txt 'keep\n' d/.gitignore '!keep.py\n'
    sg_partiel "$SG_O" /seed.txt /.gitignore /d/keep.txt
    sg_ecrire d/u.txt 'u\n'
  }
  sg_x_sgl3()  { sg_fx_c18n; sg_rm; sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl3() { sg_rc "(sgl3)" 0; sg_tait "(sgl3)" "COVERAGE DEGRADED"; sg_aucune "(sgl3)" lazy; }
  sg_bras "(sgl3)" sg_x_sgl3 sg_ok_sgl3 MG8
  ok "(sgl3) .gitignore skip-worktree illisible mais aucun non-suivi IGNORÉ sous d/ : aucune ligne DEGRADED ; MG8 rougit"

  sg_x_sgl4()  { sg_fx_c18; sg_rm; GIT_LITERAL_PATHSPECS=1 sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl4() { sg_rc "(sgl4)" 0; sg_dit "(sgl4)" "skip-worktree .gitignore check failed (git rc 128)"; sg_benin "(sgl4)"; }
  sg_bras "(sgl4)" sg_x_sgl4 sg_ok_sgl4 MG3
  ok "(sgl4) GIT_LITERAL_PATHSPECS=1 : le relevé glob refusé, « check failed (git rc 128) » dit, jamais un 0 muet ; MG3 rougit"
else
  echo "  SKIP (sgl1 sgl1h sgl1n sgl1nh sgl2 sgl2h sgl2s sgl3 sgl4) : git $_sg_v < 2.45 — GIT_NO_LAZY_FETCH sans effet ici, la porte le DIT (paresseux)"
  sg_saute "MX MXN MG MGh MG2 MG8 MG3 MNLF" "git $_sg_v < 2.45"
fi

# A git that CANNOT refuse a lazy fetch (no --no-lazy-fetch, the variable
# ignored), like a git < 2.45 — the paresseux branch: no diff, no cat-file, no
# probe batch; the loss is said, never an execution.
sg_fauxgit vieux <<'SGF'
unset GIT_NO_LAZY_FETCH
for a in "$@"; do
  case "$a" in
    --no-lazy-fetch)
      echo "unknown option: --no-lazy-fetch" >&2
      exit 129 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fx_vieux() {  # x.py (a sink) changed by HEAD's commit, OUTSIDE the sparse cone: its blob is absent
  sg_origine seed.txt 'seed\n'
  printf "$SG_SINK" > "$SG_O/x.py"
  $SG_G -C "$SG_O" add x.py >/dev/null 2>&1; $SG_G -C "$SG_O" commit -qm x >/dev/null 2>&1
  sg_partiel "$SG_O" /seed.txt
}
# (closing review B2) the GATE now refuses to enumerate such a root at all.
sg_x_sgl5()  { sg_fx_vieux; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R" --at HEAD; }
sg_ok_sgl5() {
  sg_rc "(sgl5)" 0; sg_dit "(sgl5)" "perimeter not enumerated (partial clone, git < 2.45"
  sg_adit "(sgl5)" '"couverture":"refus de conclure"'
  sg_aucune "(sgl5)" lazy; sg_benin "(sgl5)"
}
sg_fx_vieux; sg_sans_blob "(sgl5)" "$SG_R" x.py
sg_nu "(sgl5) témoin pairé : sous ce git l'export est INERTE" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" cat-file blob "$(git -C "$SG_R" rev-parse HEAD:x.py)"
sg_bras "(sgl5)" sg_x_sgl5 sg_ok_sgl5 MP1
# (sgl5h) the same git at the hook Stop (closing line C1: one hook arm per
# fail-closed branch of the Stop): the census diff is not run, said, never mute.
sg_x_sgl5h()  { sg_fx_vieux; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl5h; }
sg_ok_sgl5h() {
  sg_rc "(sgl5h)" 0; sg_dit "(sgl5h)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(sgl5h)" "tracked modified file(s) not enumerated (partial clone, git < 2.45"; sg_aucune "(sgl5h)" lazy
}
sg_bras "(sgl5h)" sg_x_sgl5h sg_ok_sgl5h MNh
# (sgl5i) the index object of such a clone at the Stop (the gate no longer
# reaches lire_objets for it): never read, the loss « partial clone » said.
sg_x_sgl5i()  { sg_fx_vieux; sg_ecrire n.py 'x = 1\n'; git -C "$SG_R" update-index --add n.py; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl5i; }
sg_ok_sgl5i() {
  sg_rc "(sgl5i)" 0; sg_dit "(sgl5i)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(sgl5i)" "git object(s) not read (partial clone, git < 2.45"; sg_aucune "(sgl5i)" lazy
}
sg_bras "(sgl5i)" sg_x_sgl5i sg_ok_sgl5i MP1
ok "(sgl5) git sans --no-lazy-fetch, clone partiel, --at HEAD : la porte refuse d'énumérer (refus de conclure), uploadpack jamais lancé (témoin pairé) ; (sgl5h) au Stop : diff non lancé, DEGRADED dit ; (sgl5i) objet d'index non lu, dit ; MP1/MNh rougissent"

sg_fx_gp12b() {  # root `d/` ignores d/ (the census never reads d/.gitignore); d/.gitignore skip-worktree without its blob
  sg_origine seed.txt 'seed\n' .gitignore 'd/\n' d/keep.txt 'k\n' d/.gitignore '!keep.log\n'
  sg_partiel "$SG_O" /seed.txt /.gitignore /d/keep.txt
  sg_ecrire d/u.txt 'u\n'
}
# At the hook Stop (the gate refuses such a root before the probe, sgl8).
sg_x_sgl7()  { sg_fx_gp12b; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl7; }
sg_ok_sgl7() {
  sg_rc "(sgl7)" 0; sg_dit "(sgl7)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(sgl7)" "skip-worktree .gitignore file(s) not checked (partial clone, git < 2.45"
  sg_aucune "(sgl7)" lazy
}
sg_fx_gp12b; sg_sans_blob "(sgl7)" "$SG_R" d/.gitignore
sg_bras "(sgl7)" sg_x_sgl7 sg_ok_sgl7 MP3
ok "(sgl7) même git, sonde skip-worktree au Stop : non jouée, « not checked (partial clone, git < 2.45 …) » dit, uploadpack jamais lancé ; MP3 rougit"

# ---- (sgl8)(sgl8h)(sgl9)(sgl10) closing review B2 ---------------------------
# Under a git that cannot refuse a lazy fetch, be913df4 still RAN the
# uploadpack (measured, devsg8/b2.sh, b2stop.sh): `ls-files --others` at the
# gate and at the Stop (it reads a skip-worktree `.gitignore` from its index
# blob), the `--ignored` listing of the skip-worktree probe, the commit diff of
# a treeless clone under `--at HEAD`. Now the gate refuses to enumerate such a
# root, the Stop runs none of them, such a submodule is skipped — each loss
# said, the marker never born; each fixture PAIRED with the naked call that
# makes it born.
sg_fx_lazyv() {  # the (sgl1) layout: d/.gitignore skip-worktree without its blob, untracked d/u.py d/u.txt
  sg_origine seed.txt 'seed\n' d/keep.txt 'keep\n' d/.gitignore '*.log\n'
  sg_partiel "$SG_O" /seed.txt /d/keep.txt
  sg_ecrire d/u.py 'x = 1\n'; sg_ecrire d/u.txt 'y\n'
}
sg_x_sgl8()  { sg_fx_lazyv; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgl8() {
  sg_rc "(sgl8)" 0; sg_dit "(sgl8)" "perimeter not enumerated (partial clone, git < 2.45"
  sg_adit "(sgl8)" '"couverture":"refus de conclure"'
  sg_aucune "(sgl8)" lazy; sg_benin "(sgl8)"; sg_sansverdict "(sgl8)" "$SG_R"
}
sg_x_sgl8h()  { sg_fx_lazyv; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl8h; }
sg_ok_sgl8h() {
  sg_rc "(sgl8h)" 0; sg_dit "(sgl8h)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(sgl8h)" "untracked file(s) not enumerated (partial clone, git < 2.45"
  sg_err "(sgl8h)" "skip-worktree .gitignore file(s) not checked (partial clone, git < 2.45"
  sg_aucune "(sgl8h)" lazy
}
sg_fx_lazyv; sg_sans_blob "(sgl8)" "$SG_R" d/.gitignore
sg_nu "(sgl8) témoin pairé : sous ce git, ls-files --others NU lance l'uploadpack" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" ls-files --others --exclude-standard
sg_fx_lazyv   # a fresh clone: the witness above fetched the blob
sg_nu "(sgl8h) témoin pairé : sous ce git, la liste --ignored NUE de la sonde lance l'uploadpack" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" --literal-pathspecs ls-files --others --ignored --exclude-standard --directory -z -- d
sg_bras "(sgl8)" sg_x_sgl8 sg_ok_sgl8 MPZ
sg_bras "(sgl8h)" sg_x_sgl8h sg_ok_sgl8h MPS MP3 MPN

sg_fx_arbre0() {  # x.py (a sink) committed by HEAD; a TREELESS clone of it: HEAD~1's tree is absent
  sg_origine seed.txt 'seed\n'
  printf "$SG_SINK" > "$SG_O/x.py"
  $SG_G -C "$SG_O" add x.py >/dev/null 2>&1; $SG_G -C "$SG_O" commit -qm x >/dev/null 2>&1
  SG_R="$(mktemp -d "$SG_W/q.XXXXXX")/q"
  $SG_G clone -q --filter=tree:0 "file://$SG_O" "$SG_R" >/dev/null 2>&1
  git -C "$SG_R" config protocol.file.allow always
  printf '.agents/\n' >> "$SG_R/.git/info/exclude"
  git -C "$SG_R" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
}
sg_x_sgl9()   { sg_fx_arbre0; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgl9()  { sg_rc "(sgl9)" 0; sg_dit "(sgl9)" "perimeter not enumerated (partial clone, git < 2.45"; sg_aucune "(sgl9)" lazy; sg_benin "(sgl9)"; }
sg_x_sgl9a()  { sg_fx_arbre0; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R" --at HEAD; }
sg_ok_sgl9a() { sg_rc "(sgl9/at)" 0; sg_dit "(sgl9/at)" "perimeter not enumerated (partial clone, git < 2.45"; sg_aucune "(sgl9/at)" lazy; sg_benin "(sgl9/at)"; }
sg_fx_arbre0
GIT_NO_LAZY_FETCH=1 git -C "$SG_R" cat-file -e "$(git -C "$SG_R" rev-parse HEAD~1)^{tree}" 2>/dev/null \
  && fail "(sgl9) fixture REFUSÉE — l'arbre de HEAD~1 est présent : le clone n'est pas sans arbres"
sg_nu "(sgl9) témoin pairé : sous ce git, le diff NU du commit lance l'uploadpack" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" diff --raw HEAD~1 HEAD --
sg_bras "(sgl9)" sg_x_sgl9 sg_ok_sgl9 MPZ
sg_bras "(sgl9/at)" sg_x_sgl9a sg_ok_sgl9a MPZ

sg_fx_subp() {  # the (sgl2s) layout: a SUBMODULE that is a blob:none clone, d/.gitignore skip-worktree without its blob, an untracked sink
  local _s
  sg_origine seed.txt 'seed\n' .gitignore '*.py\n' d/keep.txt 'keep\n' d/.gitignore '!keep.py\n'
  sg_base README.md 'r\n'; _s="$SG_R"
  $SG_G clone -q --filter=blob:none --no-checkout "file://$SG_O" "$_s/sub" >/dev/null 2>&1
  git -C "$_s/sub" config protocol.file.allow always
  $SG_G -C "$_s/sub" sparse-checkout set --no-cone /seed.txt /.gitignore /d/keep.txt >/dev/null 2>&1
  $SG_G -C "$_s/sub" checkout -q main >/dev/null 2>&1
  $SG_G -C "$_s" submodule add -q "file://$SG_O" sub >/dev/null 2>&1
  $SG_G -C "$_s" commit -qm sub >/dev/null 2>&1
  $SG_G -C "$_s" commit -q --allow-empty -m vide >/dev/null 2>&1
  git -C "$_s/sub" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
  printf "$SG_SINK" > "$_s/sub/d/keep.py"
}
sg_x_sgl10()  { sg_fx_subp; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgl10() {
  sg_rc "(sgl10)" 0; sg_dit "(sgl10)" "submodule file(s) not enumerated (partial clone, git < 2.45"
  sg_aucune "(sgl10)" lazy; sg_benin "(sgl10)"; sg_sansverdict "(sgl10)" "$SG_R"
}
sg_fx_subp; sg_sans_blob "(sgl10)" "$SG_R/sub" d/.gitignore
[ -e "$SG_R/sub/.git" ] || fail "(sgl10) fixture REFUSÉE : sub n'est pas un sous-module initialisé"
sg_nu "(sgl10) témoin pairé : sous ce git, ls-files --others NU du sous-module lance l'uploadpack" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R/sub" ls-files --others --exclude-standard
sg_bras "(sgl10)" sg_x_sgl10 sg_ok_sgl10 MPD
ok "(sgl8)(sgl8h)(sgl9)(sgl10) git sans --no-lazy-fetch : porte (blob:none, défaut ; tree:0, défaut et --at HEAD) refus de conclure, Stop sans ls-files --others ni liste --ignored, sous-module partiel sauté — chaque perte dite, uploadpack jamais lancé (témoins pairés) ; MPZ/MPS/MP3/MPN/MPD rougissent"

# ---- (sgl11h)(sgl12h)(sgl13h) security-code-review of 13a3cebf: the Stop's index
# Under a git that cannot refuse a lazy fetch, 13a3cebf's hook Stop still RAN the
# uploadpack (measured, devsg9/stop.sh): `diff-index --cached HEAD` of the index
# read (index_candidats) reads HEAD's trees — absent from a treeless clone after
# `fetch` + `reset --soft`, a sparse-index one included — and `ls-files -v`
# (K2, the probe's listing) expands a sparse index, reading the tree of each
# directory entry. Now none of them runs on such a root: each loss said, the
# marker never born; each fixture PAIRED with the naked call that makes it born.
# (sgl13h) names an absent tree from the INDEX itself, rewritten in place: the
# scanned `.git` is untrusted — it writes its index as it writes its uploadpack.
sg_bouge() {  # origin SG_O commits a sink OUTSIDE a/; SG_R fetches (commits only) and resets --soft onto it: HEAD's tree is absent
  printf "$SG_SINK" > "$SG_O/b/c/x.py"
  $SG_G -C "$SG_O" add b/c/x.py >/dev/null 2>&1; $SG_G -C "$SG_O" commit -qm x >/dev/null 2>&1
  $SG_G -C "$SG_R" fetch -q origin >/dev/null 2>&1
  $SG_G -C "$SG_R" reset -q --soft origin/main >/dev/null 2>&1
  printf '.agents/\n' >> "$SG_R/.git/info/exclude"
  git -C "$SG_R" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
}
sg_sans_arbre() {  # $1 label — the fixture is REFUSED unless HEAD is the origin's and its tree is absent
  # The tree's id is read in the ORIGIN: `rev-parse 'HEAD^{tree}'` in the clone
  # itself FETCHES that tree (measured, devsg9/dbg11d.sh) — the check would fill it.
  [ "$(git -C "$SG_R" rev-parse HEAD 2>/dev/null)" = "$(git -C "$SG_O" rev-parse HEAD)" ] \
    || fail "$1 : fixture REFUSÉE — HEAD n'a pas suivi l'origine (fetch ou reset --soft manqué)"
  GIT_NO_LAZY_FETCH=1 git -C "$SG_R" cat-file -e "$(git -C "$SG_O" rev-parse 'HEAD^{tree}')" 2>/dev/null \
    && fail "$1 : fixture REFUSÉE — l'arbre de HEAD est présent, le bras ne prouverait rien"
  return 0
}
sg_fx_arbre0r() {  # a TREELESS clone (checked out), then sg_bouge
  sg_origine seed.txt 'seed\n' a/a.py 'a = 1\n' b/c/b.py 'b = 1\n'
  SG_R="$(mktemp -d "$SG_W/q.XXXXXX")/q"
  $SG_G clone -q --filter=tree:0 "file://$SG_O" "$SG_R" >/dev/null 2>&1
  git -C "$SG_R" config protocol.file.allow always
  sg_bouge
}
sg_x_sgl11h()  { sg_fx_arbre0r; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl11h; }
sg_ok_sgl11h() {
  sg_rc "(sgl11h)" 0; sg_dit "(sgl11h)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(sgl11h)" "staged git object(s) not read (partial clone, git < 2.45"; sg_aucune "(sgl11h)" lazy
}
sg_fx_arbre0r; sg_sans_arbre "(sgl11h)"
sg_nu "(sgl11h) témoin pairé : sous ce git, le diff-index NU de l'index lance l'uploadpack" lazy \
  env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" diff-index --cached -z --no-renames HEAD --
sg_bras "(sgl11h)" sg_x_sgl11h sg_ok_sgl11h MPI
if sg_git_ge 2 36; then
  sg_fx_clair() {  # a TREELESS clone, cone a/ WITH a sparse index (b/ one directory entry), then sg_bouge
    SG_R="$(mktemp -d "$SG_W/q.XXXXXX")/q"
    sg_origine seed.txt 'seed\n' a/a.py 'a = 1\n' b/c/b.py 'b = 1\n'
    $SG_G clone -q --filter=tree:0 --no-checkout "file://$SG_O" "$SG_R" >/dev/null 2>&1
    git -C "$SG_R" config protocol.file.allow always
    $SG_G -C "$SG_R" sparse-checkout set --cone --sparse-index a >/dev/null 2>&1
    $SG_G -C "$SG_R" checkout -q main >/dev/null 2>&1
    sg_bouge
  }
  SG_REPOINT_PY='
import hashlib, sys
p, old, new = sys.argv[1:4]
b = open(p, "rb").read()[:-20]
o, n = bytes.fromhex(old), bytes.fromhex(new)
if len(o) != 20 or len(n) != 20 or b.count(o) == 0:
    sys.exit(3)
b = b.replace(o, n)
open(p, "wb").write(b + hashlib.sha1(b).digest())
'
  sg_fx_clairf() {  # sg_fx_clair, its directory entry b/ rewritten to name b/'s NEW tree — absent (trailing checksum recomputed)
    local _ob _nb
    sg_fx_clair
    _nb="$(git -C "$SG_O" rev-parse HEAD:b)"
    _ob="$(GIT_NO_LAZY_FETCH=1 git -C "$SG_R" ls-files --sparse -s -- b/ | cut -d' ' -f2)"
    "$PY" -c "$SG_REPOINT_PY" "$SG_R/.git/index" "$_ob" "$_nb" || fail "(sgl13h) fixture REFUSÉE : l'entrée b/ de l'index n'a pas pu être réécrite"
  }
  sg_clair_ok() {  # $1 label — the fixture is REFUSED unless the index is sparse (b/ a directory entry) and HEAD's tree absent
    case "$(GIT_NO_LAZY_FETCH=1 git -C "$SG_R" ls-files --sparse -s -- b/)" in
      "040000 "*) : ;;
      *) fail "$1 : fixture REFUSÉE — b/ n'est pas une entrée de répertoire d'un index clairsemé" ;;
    esac
    sg_sans_arbre "$1"
  }
  sg_x_sgl12h()  { sg_fx_clair; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl12h; }
  sg_ok_sgl12h() {
    sg_rc "(sgl12h)" 0; sg_dit "(sgl12h)" '"systemMessage": "COVERAGE DEGRADED'
    sg_err "(sgl12h)" "staged git object(s) not read (partial clone, git < 2.45"; sg_aucune "(sgl12h)" lazy
  }
  sg_fx_clair; sg_clair_ok "(sgl12h)"
  sg_nu "(sgl12h) témoin pairé : sous ce git, le diff-index NU d'un index clairsemé lance l'uploadpack" lazy \
    env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" diff-index --cached -z --no-renames HEAD --
  sg_bras "(sgl12h)" sg_x_sgl12h sg_ok_sgl12h MPI
  sg_x_sgl13h()  { sg_fx_clairf; sg_rm; SG_PATH="$SG_W/vieux:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgl13h; }
  sg_ok_sgl13h() {
    sg_rc "(sgl13h)" 0; sg_dit "(sgl13h)" '"systemMessage": "COVERAGE DEGRADED'
    sg_err "(sgl13h)" "staged git object(s) not read (partial clone, git < 2.45"
    sg_err "(sgl13h)" "skip-worktree .gitignore file(s) not checked (partial clone, git < 2.45"
    sg_aucune "(sgl13h)" lazy
  }
  sg_fx_clairf; sg_clair_ok "(sgl13h)"
  GIT_NO_LAZY_FETCH=1 git -C "$SG_R" cat-file -e "$(git -C "$SG_O" rev-parse HEAD:b)" 2>/dev/null \
    && fail "(sgl13h) fixture REFUSÉE — l'arbre que nomme l'entrée b/ est présent"
  sg_nu "(sgl13h) témoin pairé : sous ce git, ls-files -v NU (K2) d'un index clairsemé lance l'uploadpack" lazy \
    env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" ls-files -v -z
  sg_fx_clairf   # a fresh clone: the witness above fetched the tree
  sg_nu "(sgl13h) témoin pairé : sous ce git, la liste -v NUE des .gitignore de la sonde lance l'uploadpack" lazy \
    env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R" --glob-pathspecs ls-files -v -z -- '**/.gitignore'
  sg_bras "(sgl13h)" sg_x_sgl13h sg_ok_sgl13h MPI MPK MP3
  ok "(sgl11h)(sgl12h)(sgl13h) git sans --no-lazy-fetch, au Stop : clone sans arbres et clone clairsemé (index clairsemé) après reset --soft, entrée clairsemée nommant un arbre absent — ni diff-index de l'index ni ls-files -v, chaque perte dite, uploadpack jamais lancé (témoins pairés) ; MPI/MPK/MP3 rougissent"

  # (sgl14) exec-critic of 7c78f87f, B2: at the GATE, an INITIALIZED submodule
  # that is a treeless clone with a sparse index whose entry b/ names an absent
  # tree. 7c78f87f's enumerate_submodules listed its index (`ls-files --stage`,
  # in the producer, before the consumer's skip) and RAN its uploadpack
  # (exec-critic subp.sh, GIT_TRACE). Now the producer tests it before its
  # recursion: the marker never born, no `upload-pack` in GIT_TRACE, the loss
  # said, the top-level sink still found (rc 1: the scan ran). A local
  # throwaway origin (file://), no network.
  sg_fx_subclair() {  # SG_R: superproject, top.py a sink; `sub` an embedded gitlink, treeless + sparse index, b/ naming b/'s NEW tree (absent)
    local _s _ob _nb
    sg_origine seed.txt 'seed\n' a/a.py 'a = 1\n' b/c/b.py 'b = 1\n'
    sg_base top.py 'x = 1\n'; _s="$SG_R"
    $SG_G clone -q --filter=tree:0 --no-checkout "file://$SG_O" "$_s/sub" >/dev/null 2>&1
    git -C "$_s/sub" config protocol.file.allow always
    $SG_G -C "$_s/sub" sparse-checkout set --cone --sparse-index a >/dev/null 2>&1
    $SG_G -C "$_s/sub" checkout -q main >/dev/null 2>&1
    $SG_G -C "$_s" add sub >/dev/null 2>&1
    $SG_G -C "$_s" commit -qm sub >/dev/null 2>&1
    $SG_G -C "$_s" commit -q --allow-empty -m vide >/dev/null 2>&1
    printf "$SG_SINK" > "$SG_O/b/c/x.py"
    $SG_G -C "$SG_O" add b/c/x.py >/dev/null 2>&1; $SG_G -C "$SG_O" commit -qm x >/dev/null 2>&1
    $SG_G -C "$_s/sub" fetch -q origin >/dev/null 2>&1
    _nb="$(git -C "$SG_O" rev-parse HEAD:b)"
    _ob="$(GIT_NO_LAZY_FETCH=1 git -C "$_s/sub" ls-files --sparse -s -- b/ | cut -d' ' -f2)"
    "$PY" -c "$SG_REPOINT_PY" "$_s/sub/.git/index" "$_ob" "$_nb" || fail "(sgl14) fixture REFUSÉE : l'entrée b/ de l'index du sous-module n'a pas pu être réécrite"
    git -C "$_s/sub" config remote.origin.uploadpack "touch '$SG_T/lazy'; git-upload-pack"
    printf "$SG_SINK" > "$_s/top.py"
  }
  sg_x_sgl14()  { sg_fx_subclair; sg_rm; rm -f "$SG_W/sgl14.trace"; GIT_TRACE="$SG_W/sgl14.trace" SG_PATH="$SG_W/vieux:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgl14() {
    sg_rc "(sgl14)" 1; sg_dit "(sgl14)" "submodule file(s) not enumerated (partial clone, git < 2.45"
    sg_dit "(sgl14)" "its index not listed, nested submodules included"; sg_aucune "(sgl14)" lazy
    [ -s "$SG_W/sgl14.trace" ] || fail "(sgl14) GIT_TRACE vide — le témoin de transport ne prouverait rien"
    grep -q 'upload-pack' "$SG_W/sgl14.trace" && fail "(sgl14) GIT_TRACE montre un upload-pack — le transport distant a été appelé"
    return 0
  }
  sg_fx_subclair
  [ "$(git -C "$SG_R" ls-files -s sub | cut -c1-6)" = 160000 ] || fail "(sgl14) fixture REFUSÉE : sub n'est pas un gitlink du super-projet"
  [ -e "$SG_R/sub/.git" ] || fail "(sgl14) fixture REFUSÉE : sub n'est pas un sous-module initialisé"
  case "$(GIT_NO_LAZY_FETCH=1 git -C "$SG_R/sub" ls-files --sparse -s -- b/)" in
    "040000 "*) : ;;
    *) fail "(sgl14) fixture REFUSÉE — b/ n'est pas une entrée de répertoire de l'index clairsemé du sous-module" ;;
  esac
  GIT_NO_LAZY_FETCH=1 git -C "$SG_R/sub" cat-file -e "$(git -C "$SG_O" rev-parse HEAD:b)" 2>/dev/null \
    && fail "(sgl14) fixture REFUSÉE — l'arbre que nomme l'entrée b/ du sous-module est présent"
  sg_nu "(sgl14) témoin pairé : sous ce git, ls-files --stage NU du sous-module (la récursion de l'énumération) lance l'uploadpack" lazy \
    env GIT_NO_LAZY_FETCH=1 "$SG_W/vieux/git" -C "$SG_R/sub" ls-files -z --stage
  sg_bras "(sgl14)" sg_x_sgl14 sg_ok_sgl14 MPE
  ok "(sgl14) porte, git sans --no-lazy-fetch : sous-module initialisé sans arbres, index clairsemé nommant un arbre absent — non descendu (paresseux avant la récursion), perte dite, uploadpack jamais lancé (témoin pairé ; GIT_TRACE sans upload-pack), puits du super-projet trouvé ; MPE rougit"

  # (sga1)(sga1h) exec-critic of 7c78f87f, MAJEUR: a sparse-index entry naming a
  # tree absent from the object store makes `ls-files`, `-v` and `--stage`
  # return rc 0 and OMIT its entries in silence (measured under git 2.55,
  # devmulti-sg10 majprobe.sh / majlocal.sh) — a truncated listing read as
  # complete. Now said, gate and Stop: a named DEGRADED line. The fixture is a
  # LOCAL repository with no promisor (nothing can be fetched): cone a/ with a
  # sparse index, its entry b/ repointed at a tree id that does not exist.
  SG_ARBRE_ABSENT=1111111111111111111111111111111111111111
  sg_fx_absent() {  # SG_R: cone a/ (+ .agents) with a sparse index, entry b/ naming a tree that does not exist; a/k.py an untracked sink
    local _ob
    sg_base seed.txt 'seed\n' a/a.py 'a = 1\n' b/c/b.py 'b = 1\n'
    $SG_G -C "$SG_R" sparse-checkout set --cone --sparse-index a .agents >/dev/null 2>&1
    _ob="$(git -C "$SG_R" ls-files --sparse -s -- b/ | cut -d' ' -f2)"
    "$PY" -c "$SG_REPOINT_PY" "$SG_R/.git/index" "$_ob" "$SG_ARBRE_ABSENT" || fail "(sga1) fixture REFUSÉE : l'entrée b/ de l'index n'a pas pu être réécrite"
    sg_ecrire a/k.py "$SG_SINK"
  }
  sg_x_sga1()   { sg_fx_absent; sg_run "$SG_S" "$SG_R"; }
  sg_ok_sga1()  { sg_dit "(sga1)" "1 sparse-index directory entr(y|ies) naming a tree absent from the object store"; sg_benin "(sga1)"; }
  sg_x_sga1h()  { sg_fx_absent; sg_hook "$SG_S" "$SG_R" sga1h; }
  sg_ok_sga1h() { sg_rc "(sga1h)" 2; sg_err "(sga1h)" "1 sparse-index directory entr(y|ies) naming a tree absent from the object store"; }
  sg_fx_absent
  case "$(git -C "$SG_R" ls-files --sparse -s -- b/)" in
    "040000 $SG_ARBRE_ABSENT "*) : ;;
    *) fail "(sga1) fixture REFUSÉE — b/ n'est pas une entrée clairsemée nommant l'arbre absent" ;;
  esac
  git -C "$SG_R" cat-file -e "$SG_ARBRE_ABSENT" 2>/dev/null && fail "(sga1) fixture REFUSÉE — l'arbre nommé existe"
  # PAIRED witness: the naked `ls-files -v` succeeds (rc 0) and OMITS b/'s entry
  # — the truncation the arm must make said; a/a.py proves the listing ran.
  git -C "$SG_R" ls-files -v -z > "$SG_W/sga1.lv" 2>/dev/null || fail "(sga1) témoin pairé : ls-files -v NU a échoué — la troncature serait dite par son rc, le bras ne prouverait rien"
  tr '\0' '\n' < "$SG_W/sga1.lv" | grep -q 'a/a.py' || fail "(sga1) témoin pairé MUET : a/a.py absent du ls-files -v nu"
  tr '\0' '\n' < "$SG_W/sga1.lv" | grep -q 'b/c/b.py' && fail "(sga1) témoin pairé : ls-files -v NU liste b/c/b.py — aucune troncature, le bras ne prouverait rien"
  sg_bras "(sga1)" sg_x_sga1 sg_ok_sga1 MAA
  sg_bras "(sga1h)" sg_x_sga1h sg_ok_sga1h MAA
  ok "(sga1)(sga1h) entrée d'index clairsemé nommant un arbre absent du magasin (dépôt local, aucun fetch possible) : la liste tronquée de ls-files est DITE (DEGRADED nommé), porte et Stop (témoin pairé : ls-files -v nu rc 0 sans b/) ; MAA rougit"
else
  ok "(sgl11h) git sans --no-lazy-fetch, au Stop : clone sans arbres après reset --soft — diff-index de l'index non lancé, perte dite, uploadpack jamais lancé (témoin pairé) ; MPI rougit"
  echo "  SKIP (sgl12h sgl13h sgl14 sga1 sga1h) : git $_sg_v < 2.36 — ni ls-files --sparse ni set --cone --sparse-index ici"
  sg_saute "MPK MPE MAA" "git $_sg_v < 2.36 (sgl13h sgl14 sga1)"
fi

# (sgl6)(sgl6b) a failed probe is SAID, never a count of 0 (ports of gitleaks gp7b/gp7).
sg_fauxgit bc129 <<'SGF'
for a in "$@"; do
  case "$a" in
    --batch-check)
      exit 129 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit bc128 <<'SGF'
b=0
for a in "$@"; do
  case "$a" in
    --batch-check)
      b=1 ;;
  esac
done
[ "$b" = 1 ] || exec "$real" "$@"
n="$(head -c 1 | wc -c | tr -d " ")"
[ "$n" = 0 ] && exec "$real" "$@" < /dev/null
exit 128
SGF
sg_fx_sw() {  # d/.gitignore `*.tmp` skip-worktree, removed from the disk (blob PRESENT), d/u.txt benign, d/a.tmp ignored
  sg_base d/keep.txt 'keep\n' d/.gitignore '*.tmp\n'
  git -C "$SG_R" update-index --skip-worktree d/.gitignore; rm -f "$SG_R/d/.gitignore"
  sg_ecrire d/u.txt 'benign\n'; sg_ecrire d/a.tmp 'x\n'
}
sg_x_sgl6()   { sg_fx_sw; SG_PATH="$SG_W/bc129:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgl6()  { sg_rc "(sgl6)" 0; sg_dit "(sgl6)" "git < 2.42 : skip-worktree .gitignore not checked"; sg_benin "(sgl6)"; }
sg_x_sgl6b()  { sg_fx_sw; SG_PATH="$SG_W/bc128:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgl6b() { sg_rc "(sgl6b)" 0; sg_dit "(sgl6b)" "skip-worktree .gitignore check failed (git rc 128)"; sg_benin "(sgl6b)"; }
sg_fx_sw; sg_run "$SCRIPT" "$SG_R"
sg_rc "(sgl6) témoin sans faux git" 0; sg_tait "(sgl6) témoin sans faux git" "skip-worktree"
sg_bras "(sgl6)" sg_x_sgl6 sg_ok_sgl6 MG5
sg_bras "(sgl6b)" sg_x_sgl6b sg_ok_sgl6b MG6
ok "(sgl6) sans -Z (rc 129) => « git < 2.42 … not checked » ; (sgl6b) batch-check rc 128 => « check failed (git rc 128) » ; jamais bénin (témoin sans faux git : aucune ligne) ; MG5/MG6 rougissent"

# ---- (sgk*) ASSUME-UNCHANGED ENTRIES (K2) ------------------------------------
sg_x_sgk1() {
  sg_base a.py 'x = 1\n'
  git -C "$SG_R" update-index --assume-unchanged a.py; sg_ecrire a.py "$SG_SINK"
  sg_run "$SG_S" "$SG_R"
}
sg_ok_sgk1() { sg_rc "(sgk1)" 1; sg_adit "(sgk1)" "a.py:3"; }
sg_base a.py 'x = 1\n'; git -C "$SG_R" update-index --assume-unchanged a.py; sg_ecrire a.py "$SG_SINK"
[ -z "$(git -C "$SG_R" diff --name-only HEAD)" ] || fail "(sgk1) témoin : git diff devait TAIRE l'entrée assume-unchanged"
sg_bras "(sgk1)" sg_x_sgk1 sg_ok_sgk1 MK2
sg_fauxgit lsv128 <<'SGF'
case "$*" in
  *" ls-files -v -z")
    exit 128 ;;
esac
exec "$real" "$@"
SGF
sg_x_sgk2()   { sg_base b.py 'x = 1\n'; sg_ecrire b.py 'x = 2\n'; SG_PATH="$SG_W/lsv128:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_sgk2()  { sg_rc "(sgk2)" 0; sg_dit "(sgk2)" "assume-unchanged entries not listed (git ls-files -v failed)"; sg_benin "(sgk2)"; }
sg_x_sgk2h()  { sg_base b.py 'x = 1\n'; sg_ecrire b.py 'x = 2\n'; SG_PATH="$SG_W/lsv128:$SG_STUB" sg_hook "$SG_S" "$SG_R" sgk2h; }
sg_ok_sgk2h() { sg_rc "(sgk2h)" 0; sg_dit "(sgk2h)" '"systemMessage": "COVERAGE DEGRADED'; sg_err "(sgk2h)" "assume-unchanged entries not listed"; }
"$SG_W/lsv128/git" -C "$SG_W" -c core.fsmonitor=false -c core.hooksPath=/dev/null ls-files -v -z >/dev/null 2>&1
[ "$?" -eq 128 ] || fail "(sgk2) autotest du bouchon : 'ls-files -v -z' (argv de la porte) devait rendre 128"
"$SG_W/lsv128/git" -C "$SG_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null --glob-pathspecs ls-files -v -z -- '**/.gitignore' >/dev/null 2>&1 \
  || fail "(sgk2) autotest du bouchon : la sonde des .gitignore devait passer"
sg_bras "(sgk2)" sg_x_sgk2 sg_ok_sgk2 MK3
sg_bras "(sgk2h)" sg_x_sgk2h sg_ok_sgk2h MK3
ok "(sgk1) puits sous --assume-unchanged (que git diff tait) : rc 1 ; (sgk2)(sgk2h) ls-files -v en échec : DEGRADED dit, porte et Stop ; MK2/MK3 rougissent"

# ---- (sgt*) THE PERIMETER IS SORTED IN BYTES (T-01M4Z5T4YQND3S63PW8D4ERN25) --
# Measured (r2/v2.sh): under LC_ALL=fr_FR.UTF-8 `sort -zu` folds a.py and
# a<U+200B>.py into one — `2 scannable`, `clean on the diff.` over the twin sink.
SG_LOC=""
for _l in fr_FR.UTF-8 en_US.UTF-8 C.UTF-8; do
  _n="$(printf 'a.py\0a\342\200\213.py\0' | LC_ALL="$_l" sort -zu 2>/dev/null | tr '\0' '\n' | grep -c .)"
  if [ "$_n" = 1 ]; then SG_LOC="$_l"; break; fi
done
if [ -n "$SG_LOC" ]; then
  sg_fx_jum() { sg_base; sg_ecrire a.py 'x = 1\n'; printf "$SG_SINK" > "$SG_R/a$(printf '\342\200\213').py"; }
  sg_x_sgt1()  { sg_fx_jum; LC_ALL="$SG_LOC" sg_run "$SG_S" "$SG_R"; }
  sg_ok_sgt1() { sg_rc "(sgt1)" 1; sg_dit "(sgt1)" "2 scannable file(s)"; }
  sg_x_sgt2()  { sg_fx_jum; LC_ALL="$SG_LOC" sg_hook "$SG_S" "$SG_R" sgt2; }
  sg_ok_sgt2() { sg_rc "(sgt2)" 2; }
  printf 'a.py\na\342\200\213.py\n' > "$SG_W/att-jum"
  sg_x_sgt3()  { sg_fx_jum; LC_ALL="$SG_LOC" sg_run "$SG_S" "$SG_R" --attest "$SG_W/att-jum"; }
  sg_ok_sgt3() { sg_dit "(sgt3)" "attestation ≡ retenues (2/2)"; }
  sg_bras "(sgt1)" sg_x_sgt1 sg_ok_sgt1 MQ5
  sg_bras "(sgt2)" sg_x_sgt2 sg_ok_sgt2 MQ5h
  sg_bras "(sgt3)" sg_x_sgt3 sg_ok_sgt3 MQ5a
  ok "(sgt1)(sgt2)(sgt3) jumeaux a.py / a<U+200B>.py sous LC_ALL=$SG_LOC (témoin : sort -zu les plie) : porte 2 scannable rc 1, Stop rc 2, attestation ≡ ; MQ5/MQ5h/MQ5a rougissent"
else
  echo "  SKIP (sgt1 sgt2 sgt3) : aucune locale UTF-8 de cette machine ne plie a.py et a<U+200B>.py (sort -zu) — le tri en octets n'a rien à prouver ici"
  sg_saute "MQ5 MQ5h MQ5a" "aucune locale pliante"
fi

# ---- (since*) A BASE WITHOUT A MERGE BASE (T-01M4XY8PP8VYW0VVCYAAK0VARF) ------
# Measured at c2a42ba2 (sg3/d2.sh): `diff o...HEAD` rc 128 in silence —
# `nothing to scan` + CLEAN on a clean tree, `clean on the diff` + a verdict on
# a dirty one, over the COMMITTED sink s.py; @{upstream}=o the same.
sg_fx_d2() {  # main: base, then a committed sink s.py; o: an ORPHAN history
  sg_repo
  $SG_G -C "$SG_R" add -A >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm base >/dev/null 2>&1
  $SG_G -C "$SG_R" checkout -q --orphan o >/dev/null 2>&1
  $SG_G -C "$SG_R" rm -rqf . >/dev/null 2>&1
  printf 'x\n' > "$SG_R/o.txt"; $SG_G -C "$SG_R" add o.txt >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm o >/dev/null 2>&1
  $SG_G -C "$SG_R" checkout -q main >/dev/null 2>&1
  sg_ecrire s.py "$SG_SINK"; $SG_G -C "$SG_R" add s.py >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm sink >/dev/null 2>&1
}
sg_ok_since() {  # $1 label — HEAD alone, said; the committed sink found; no verdict on the loss; TMPDIR empty (one SG_SIG per run)
  sg_rc "$1" 1; sg_dit "$1" "commit(s) since the base not enumerated (no merge base with HEAD; fell back to HEAD alone)"
  sg_tait "$1" "nothing to scan"; sg_sansverdict "$1" "$SG_R"; sg_vide "$1"
}
sg_x_since1()  { sg_fx_d2; sg_run "$SG_S" "$SG_R" --since o; }
sg_ok_since1() { sg_ok_since "(since1)"; }
sg_x_since2()  { sg_fx_d2; sg_ecrire dirty.py 'def g():\n    return 1\n'; sg_run "$SG_S" "$SG_R" --since o; }
sg_ok_since2() { sg_ok_since "(since2)"; }
sg_x_since3()  { sg_fx_d2; git -C "$SG_R" branch -q -u o; sg_run "$SG_S" "$SG_R"; }
sg_ok_since3() { sg_ok_since "(since3)"; }
sg_fx_d2; sg_run "$SCRIPT" "$SG_R" --since main~1
sg_rc "(since1) témoin --since main~1 (une base de fusion existe)" 1
sg_tait "(since1) témoin --since main~1" "no merge base"
# MS5 (a SECOND SG_SIG made before `_mb=0`) rides on (since1), no longer on
# (since4): cleanup() now removes $SG_SIG at the refusal exit of (since4) as
# hk_nettoyer does, so only a path that REPLACES $SG_SIG (the commit census
# below) can orphan the first file — the witness is TMPDIR emptiness.
sg_bras "(since1)" sg_x_since1 sg_ok_since1 MS1 MS2 MS5
sg_bras "(since2)" sg_x_since2 sg_ok_since2 MS1 MS2
sg_bras "(since3)" sg_x_since3 sg_ok_since3 MS1 MS2
ok "(since1)(since2)(since3) base orpheline (--since, arbre propre / sale, @{upstream}) : HEAD seul DIT, rc 1, aucun « nothing to scan », aucun verdict, TMPDIR vide (témoin --since main~1 : rc 1) ; MS1/MS2/MS5 rougissent"

sg_fx_d2m() {  # sg_fx_d2, then HEAD a MERGE
  sg_fx_d2
  $SG_G -C "$SG_R" checkout -q -b x >/dev/null 2>&1
  sg_ecrire y.py 'y = 1\n'; $SG_G -C "$SG_R" add y.py >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm y >/dev/null 2>&1
  $SG_G -C "$SG_R" checkout -q main >/dev/null 2>&1
  sg_ecrire c.py 'c = 1\n'; $SG_G -C "$SG_R" add c.py >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm c >/dev/null 2>&1
  $SG_G -C "$SG_R" merge -q --no-ff -m m x >/dev/null 2>&1
}
sg_x_since4()  { sg_fx_d2m; sg_run "$SG_S" "$SG_R" --since o; }
sg_ok_since4() {
  sg_rc "(since4)" 0; sg_adit "(since4)" '"couverture":"refus de conclure"'
  sg_dit "(since4)" "shares no merge base with HEAD"; sg_vide "(since4)"
}
sg_bras "(since4)" sg_x_since4 sg_ok_since4 MS3
ok "(since4) HEAD fusion + base orpheline : refus de conclure, rc 0, TMPDIR dédié VIDE ; MS3 rougit"

sg_fauxgit trois128 <<'SGF'
case "$*" in
  *"...HEAD"*)
    exit 128 ;;
esac
exec "$real" "$@"
SGF
sg_fauxgit mb128 <<'SGF'
for a in "$@"; do
  case "$a" in
    merge-base)
      exit 128 ;;
  esac
done
exec "$real" "$@"
SGF
sg_ok_since56() {  # $1 label — the range census failed: a refusal to conclude, never a verdict
  sg_rc "$1" 0; sg_adit "$1" '"couverture":"refus de conclure"'
  sg_dit "$1" "committed path(s) since the base (the range census failed)"
  sg_sansverdict "$1" "$SG_R"; sg_benin "$1"
}
sg_x_since5()  { sg_fx_d2; SG_PATH="$SG_W/trois128:$SG_STUB" sg_run "$SG_S" "$SG_R" --since main~1; }
sg_ok_since5() { sg_ok_since56 "(since5)"; }
sg_x_since6()  { sg_fx_d2; SG_PATH="$SG_W/mb128:$SG_STUB" sg_run "$SG_S" "$SG_R" --since main~1; }
sg_ok_since6() { sg_ok_since56 "(since6)"; }
sg_bras "(since5)" sg_x_since5 sg_ok_since5 MS4
sg_bras "(since6)" sg_x_since6 sg_ok_since6 MS7
ok "(since5) diff base...HEAD rc 128 (merge-base rc 0) / (since6) merge-base rc 128 : since-census, refus de conclure, aucun verdict ; MS4/MS7 rougissent"

# ---- (obj*) WHAT GIT COMMITS IS READ (T-01M4XY8NC97JBSQP6C28AFD7QP) -----------
# Measured at c2a42ba2 (sg3/d1.sh, d1b.sh, fx/nohead): D1a (sink indexed, tree
# benign) and D1b (indexed, then removed) read `clean on the diff.` / `rien à
# lire`, rc 0, the commit carried the sink; D1c (committed sink, tree benign)
# read clean by default and under `--at HEAD`.
sg_fx_d1a()    { sg_base; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; sg_ecrire k.py "$SG_BENIN"; }
sg_fx_d1b()    { sg_base; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; rm -f "$SG_R/k.py"; }
sg_fx_nohead() { sg_repo; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; sg_ecrire k.py "$SG_BENIN"; }
sg_ok_index() { sg_rc "$1" 1; sg_adit "$1" '"index:k.py:3'; sg_vide "$1"; }
sg_x_obj1()  { sg_fx_d1a; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj1() { sg_ok_index "(obj1)"; }
sg_x_obj2()  { sg_fx_d1b; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj2() { sg_ok_index "(obj2)"; }
sg_x_obj7()  { sg_fx_nohead; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj7() { sg_ok_index "(obj7)"; }
sg_bras "(obj1)" sg_x_obj1 sg_ok_obj1 MO1 MO10
sg_bras "(obj2)" sg_x_obj2 sg_ok_obj2 MO1
sg_bras "(obj7)" sg_x_obj7 sg_ok_obj7 MO1
ok "(obj1)(obj2)(obj7) puits indexé sous un arbre bénin / indexé puis supprimé / sans commit : rc 1, index:k.py:3, TMPDIR dédié vide ; MO1/MO10 rougissent"

sg_fx_d1c()  { sg_base; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; $SG_G -C "$SG_R" commit -qm sink >/dev/null 2>&1; sg_ecrire k.py "$SG_BENIN"; }
sg_fx_d1cs() { sg_base; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; $SG_G -C "$SG_R" commit -qm sink >/dev/null 2>&1; rm -f "$SG_R/k.py"; }
sg_fx_d1sw() {
  sg_base; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; $SG_G -C "$SG_R" commit -qm sink >/dev/null 2>&1
  git -C "$SG_R" update-index --skip-worktree k.py; rm -f "$SG_R/k.py"
}
sg_ok_commit() { sg_rc "$1" 1; sg_adit "$1" '"commit:k.py:3'; }
sg_x_obj3()   { sg_fx_d1c; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj3()  { sg_ok_commit "(obj3)"; }
sg_x_obj3a()  { sg_fx_d1c; sg_run "$SG_S" "$SG_R" --at HEAD; }
sg_ok_obj3a() { sg_ok_commit "(obj3a)"; }
sg_x_obj3s()  { sg_fx_d1cs; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj3s() { sg_ok_commit "(obj3s)"; }
sg_x_objsw()  { sg_fx_d1sw; sg_run "$SG_S" "$SG_R"; }
sg_ok_objsw() { sg_ok_commit "(obj-sw)"; }
sg_fauxgit lp128 <<'SGF'
for a in "$@"; do
  case "$a" in
    --literal-pathspecs)
      exit 128 ;;
  esac
done
exec "$real" "$@"
SGF
sg_x_obj3x()  { sg_fx_d1c; SG_PATH="$SG_W/lp128:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_obj3x() { sg_ok_commit "(obj3x)"; }
sg_bras "(obj3)" sg_x_obj3 sg_ok_obj3 MO3
sg_bras "(obj3a)" sg_x_obj3a sg_ok_obj3a MO3
sg_bras "(obj3s)" sg_x_obj3s sg_ok_obj3s MO3 MOsw
sg_bras "(obj-sw)" sg_x_objsw sg_ok_objsw MOsw
sg_bras "(obj3x)" sg_x_obj3x sg_ok_obj3x MO9
ok "(obj3)(obj3a)(obj3s)(obj-sw)(obj3x) puits commité sous un arbre bénin / --at HEAD / supprimé / skip-worktree / diff de la pointe en échec (sûr par défaut) : rc 1, commit:k.py:3 ; MO3/MOsw/MO9 rougissent"

# (obj-au)(obj-sw2)(obj-is) closing review B1: a COMMITTED sink rewritten benign,
# unstaged, under an entry git NEVER compares — assume-unchanged,
# skip-worktree kept on the disk, core.ignoreStat=true (which marks every path
# `git add` stages assume-unchanged) — read rc 0, CLEAN at be913df4, by default
# and under --at HEAD (measured, devsg8/drive.sh b1-*): `diff <pointe>` took
# the INDEX copy for the tree. MOB1 (the flagged entries not collected)
# reddens each. Paired witness: `git diff HEAD` is mute on k.py in all three.
sg_fx_b1() {  # $1 = au|sw|is
  sg_base
  if [ "$1" = is ]; then git -C "$SG_R" config core.ignoreStat true; fi
  sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; $SG_G -C "$SG_R" commit -qm sink >/dev/null 2>&1
  case "$1" in
    au)
      git -C "$SG_R" update-index --assume-unchanged k.py ;;
    sw)
      git -C "$SG_R" update-index --skip-worktree k.py ;;
  esac
  sg_ecrire k.py "$SG_BENIN"
}
sg_x_objau()   { sg_fx_b1 au; sg_run "$SG_S" "$SG_R"; }
sg_ok_objau()  { sg_ok_commit "(obj-au)"; }
sg_x_objsw2()  { sg_fx_b1 sw; sg_run "$SG_S" "$SG_R"; }
sg_ok_objsw2() { sg_ok_commit "(obj-sw2)"; }
sg_x_objis()   { sg_fx_b1 is; sg_run "$SG_S" "$SG_R"; }
sg_ok_objis()  { sg_ok_commit "(obj-is)"; }
sg_x_objisa()  { sg_fx_b1 is; sg_run "$SG_S" "$SG_R" --at HEAD; }
sg_ok_objisa() { sg_ok_commit "(obj-is/at)"; }
for _k in au sw is; do
  sg_fx_b1 "$_k"
  [ -z "$(git -C "$SG_R" diff --name-only HEAD)" ] || fail "(obj-$_k) témoin : git diff HEAD devait TAIRE k.py (entrée jamais comparée)"
done
case "$(git -C "$SG_R" ls-files -v k.py)" in
  "h k.py")
    : ;;
  *)
    fail "(obj-is) témoin : core.ignoreStat devait marquer k.py assume-unchanged (h) : $(git -C "$SG_R" ls-files -v k.py)" ;;
esac
sg_bras "(obj-au)" sg_x_objau sg_ok_objau MOB1
sg_bras "(obj-sw2)" sg_x_objsw2 sg_ok_objsw2 MOB1
sg_bras "(obj-is)" sg_x_objis sg_ok_objis MOB1
sg_bras "(obj-is/at)" sg_x_objisa sg_ok_objisa MOB1
ok "(obj-au)(obj-sw2)(obj-is) puits commité, réécrit bénin sans add, sous assume-unchanged / skip-worktree sur le disque / core.ignoreStat (défaut et --at HEAD) : rc 1, commit:k.py:3 (témoin : git diff HEAD muet) ; MOB1 rougit"

sg_x_obj4() {
  sg_repo; sg_ecrire ok.py 'x = 1\n'
  $SG_G -C "$SG_R" add -A >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm ok >/dev/null 2>&1
  sg_run "$SG_S" "$SG_R"
}
sg_ok_obj4() {
  sg_rc "(obj4)" 0; sg_tait "(obj4)" " git object(s)"; sg_dit "(obj4)" "scannable file(s)"
  sg_vide "(obj4)"
  case "$SG_AUDIT" in
    *'"index:'*|*'"commit:'*)
      fail "(obj4) arbre propre, index = HEAD : aucun objet attendu, audit : $SG_AUDIT" ;;
  esac
}
sg_bras "(obj4)" sg_x_obj4 sg_ok_obj4 MO2
sg_x_obj4; sg_hook "$SCRIPT" "$SG_R" obj4h
[ "$SG_RC" -eq 0 ] && [ -z "$SG_OUT" ] || fail "(obj4) Stop nominal sur un arbre propre : muet rc 0 attendu, rc $SG_RC : $SG_OUT"
ok "(obj4) nominal (arbre propre, index = HEAD) : aucun objet, aucune ligne neuve, TMPDIR vide, Stop muet ; MO2 rougit"

sg_x_obj5()  { sg_fx_d1a; sg_run "$SG_S" "$SG_R"; SG_VTXT="$(cat "$SG_R/.agents/state/local/sca-reports/semgrep-verdict.json" 2>/dev/null)"; }
sg_ok_obj5() {
  sg_rc "(obj5)" 1
  case "$SG_OUT$SG_AUDIT$SG_VTXT" in
    *semgrep-objs*|*"$SG_LAST_TMP"*)
      fail "(obj5) un chemin machine a fui (console, audit ou verdict) : $SG_OUT / $SG_AUDIT / $SG_VTXT" ;;
  esac
  case "$SG_VTXT" in
    *'"index:k.py"'*)
      : ;;
    *)
      fail "(obj5) le verdict commun doit nommer index:k.py : $SG_VTXT" ;;
  esac
}
printf 'k.py\n' > "$SG_W/att-k"
sg_x_obj6()  { sg_fx_d1a; sg_run "$SG_S" "$SG_R" --attest "$SG_W/att-k"; }
sg_ok_obj6() { sg_dit "(obj6)" "PARTIELLE"; sg_tait "(obj6)" "couverture portable par attestation"; }
sg_bras "(obj5)" sg_x_obj5 sg_ok_obj5 MO4
sg_bras "(obj6)" sg_x_obj6 sg_ok_obj6 MO5
ok "(obj5) aucun chemin machine au verdict, à l'audit, à la console ; (obj6) attestation sans index:k.py => PARTIELLE ; MO4/MO5 rougissent"

if [ -z "$ILL_SKIP" ]; then
  # The objects live under $OUT (`.agents/state/local/sca-reports`), so THAT
  # directory is made 555 here — a TMPDIR 555 no longer touches them.
  sg_x_obj8() {
    sg_fx_d1a; mkdir -p "$SG_R/.agents/state/local/sca-reports"; chmod 555 "$SG_R/.agents/state/local/sca-reports"
    sg_run "$SG_S" "$SG_R"
    chmod 755 "$SG_R/.agents/state/local/sca-reports"
  }
  sg_ok_obj8() { sg_rc "(obj8)" 0; sg_dit "(obj8)" "git object(s) not read (index or commit content not scanned)"; sg_benin "(obj8)"; }
  sg_bras "(obj8)" sg_x_obj8 sg_ok_obj8 MO7
  ok "(obj8) \$OUT (sca-reports) 555 : objets non écrits, perte dite, rc 0, aucune phrase bénigne ; MO7 rougit"
else
  echo "  SKIP (obj8) : $ILL_SKIP"
  sg_saute "MO7" "$ILL_SKIP"
fi

SG_SHA_X="1111111111111111111111111111111111111111"
sg_x_obj14()  { sg_base; git -C "$SG_R" update-index --add --cacheinfo "100644,$SG_SHA_X,u.py"; sg_ecrire a.py "$SG_SINK"; sg_run "$SG_S" "$SG_R"; }
sg_ok_obj14() { sg_rc "(obj14)" 1; sg_dit "(obj14)" "git object(s) not read"; sg_dit "(obj14)" "SAST couverture: DEGRADED"; }
sg_bras "(obj14)" sg_x_obj14 sg_ok_obj14 MO12
# (obj15) EVERY target is a git object and none can be read: semgrep is NOT
# launched — without the guard it reads the current directory (the stub, as
# semgrep, scans `*.py` there) and finds old.py, OUTSIDE the perimeter. (MO15
# rides here and not on obj8: obj8 keeps a readable tree file, k.py, so
# semgrep runs on it either way.)
sg_x_obj15() {
  sg_repo; sg_ecrire old.py "$SG_SINK"
  $SG_G -C "$SG_R" add -A >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm old >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -q --allow-empty -m vide >/dev/null 2>&1
  git -C "$SG_R" update-index --add --cacheinfo "100644,$SG_SHA_X,u.py"
  sg_run "$SG_S" "$SG_R"
}
sg_ok_obj15() { sg_rc "(obj15)" 0; sg_dit "(obj15)" "git object(s) not read"; sg_benin "(obj15)"; }
sg_bras "(obj15)" sg_x_obj15 sg_ok_obj15 MO15
ok "(obj14) blob d'index absent + a.py puits : rc 1 + DEGRADED « not read » ; (obj15) toutes les cibles sont des objets illisibles : semgrep non lancé, rc 0, perte dite ; MO12/MO15 rougissent"

mkdir -p "$SG_W/ci"; : > "$SG_W/ci/K"
sg_x_objcase() {
  local _b _s
  sg_base
  _b="$(printf 'x = 1\n' | git -C "$SG_R" hash-object -w --stdin)"
  _s="$(printf "$SG_SINK" | git -C "$SG_R" hash-object -w --stdin)"
  git -C "$SG_R" update-index --add --cacheinfo "100644,$_b,K.py"
  git -C "$SG_R" update-index --add --cacheinfo "100644,$_s,k.py"
  sg_run "$SG_S" "$SG_R"
}
sg_ok_objcase() {
  sg_benin "(obj-case)"
  case "$SG_OUT" in
    *"git object(s) not read"*)
      : ;;
    *)
      sg_rc "(obj-case)" 1 ;;
  esac
}
if [ -e "$SG_W/ci/k" ]; then
  sg_bras "(obj-case)" sg_x_objcase sg_ok_objcase MO13
  ok "(obj-case) index K.py bénin + k.py puits sur un système de fichiers insensible à la casse : perte dite ou rc 1, jamais clean ; MO13 rougit"
else
  sg_bras "(obj-case)" sg_x_objcase sg_ok_objcase
  sg_saute "MO13" "système de fichiers sensible à la casse : aucune collision à provoquer"
  ok "(obj-case) index K.py + k.py (sensible à la casse) : jamais clean"
fi

sg_x_obj12() {
  sg_fx_d1a; : > "$SG_W/capt"
  SG_STUB_CAPT="$SG_W/capt" SG_PATH="$SG_NOPY:$SG_STUB" sg_run "$SG_S" "$SG_R"
  SG_CAPT="$(cat "$SG_W/capt")"
}
sg_ok_obj12() {
  sg_rc "(obj12)" 1; sg_dit "(obj12)" "PYTHON 3 NOT FOUND"
  case "$SG_CAPT" in
    *"/i/k.py"*os.system*)
      : ;;
    *)
      fail "(obj12) sans python, le bouchon devait recevoir …/i/k.py porteur du puits : $SG_CAPT" ;;
  esac
}
sg_bras "(obj12)" sg_x_obj12 sg_ok_obj12 MO14
ok "(obj12) sans python : le lecteur shell écrit …/i/k.py, porteur du puits, rc 1 ; MO14 rougit"

# The objects are written under the repository's $OUT, never under TMPDIR (the
# 14 s Stop on 50 staged files of 82d10a60): the stub CAPTURES each target it
# receives, and the object k.py must come from `…/sca-reports/semgrep-objs.*/i/`.
# MT1 (objects back under TMPDIR) reddens it twice: the capture, and the
# trailing slash of TMPDIR that leaves the report paths unrelabelled.
sg_x_obj5t() {
  local _t
  sg_fx_d1a; _t="$(mktemp -d "$SG_W/t.XXXXXX")"; : > "$SG_W/capt5t"
  SG_STUB_CAPT="$SG_W/capt5t" SG_TMP="$_t/" sg_run "$SG_S" "$SG_R"
  SG_VTXT="$(cat "$SG_R/.agents/state/local/sca-reports/semgrep-verdict.json" 2>/dev/null)"
  SG_CAPT="$(grep '^== ' "$SG_W/capt5t")"
}
sg_ok_obj5t() {
  sg_rc "(obj5t)" 1; sg_adit "(obj5t)" '"index:k.py:3'; sg_tait "(obj5t)" "not relabelled"
  case "$SG_OUT$SG_AUDIT$SG_VTXT" in
    *semgrep-objs*)
      fail "(obj5t) TMPDIR à barre finale : un chemin machine a fui : $SG_OUT / $SG_AUDIT" ;;
  esac
  case "$SG_CAPT" in
    *"/.agents/state/local/sca-reports/semgrep-objs."*"/i/k.py"*)
      : ;;
    *)
      fail "(obj5t) l'objet k.py devait être écrit sous \$OUT (sca-reports/semgrep-objs.*), cibles reçues : $SG_CAPT" ;;
  esac
  sg_vide "(obj5t)"
}
sg_bras "(obj5t)" sg_x_obj5t sg_ok_obj5t MT1
sg_x_objr()  { sg_fx_d1a; SG_STUB_SLASH=1 sg_run "$SG_S" "$SG_R"; }
sg_ok_objr() { sg_dit "(obj-r)" "report paths not relabelled (machine paths left)"; sg_sansverdict "(obj-r)" "$SG_R"; }
sg_bras "(obj-r)" sg_x_objr sg_ok_objr MR1
ok "(obj5t) TMPDIR « <dir>/ » : objets écrits sous \$OUT, index:k.py:3, aucun semgrep-objs nulle part ; (obj-r) chemin machine restant => perte dite, aucun verdict ; MT1/MR1 rougissent"

# A concurrent run's objects (or any file) under $OUT are never part of the
# perimeter: with NO `.gitignore` for state/local, a sink planted under
# `sca-reports/semgrep-objs.X/i/` is skipped by OUT_REL at the gate AND at the
# Stop. MORp/MORh (the exclusion defeated) make it scanned: rc 1 / rc 2.
sg_fx_objout() {
  sg_repo; rm -f "$SG_R/.agents/.gitignore"; sg_ecrire a.py 'x = 1\n'
  $SG_G -C "$SG_R" add -A >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm base >/dev/null 2>&1
  sg_ecrire .agents/state/local/sca-reports/semgrep-objs.AUTRE/i/s.py "$SG_SINK"
  sg_ecrire a.py 'x = 2\n'
}
sg_x_objout()   { sg_fx_objout; sg_run "$SG_S" "$SG_R"; }
sg_ok_objout()  { sg_rc "(obj-out)" 0; sg_tait "(obj-out)" "semgrep-objs.AUTRE"; }
sg_x_objouth()  { sg_fx_objout; sg_hook "$SG_S" "$SG_R" objouth; }
sg_ok_objouth() { sg_rc "(obj-out/Stop)" 0; sg_tait "(obj-out/Stop)" "semgrep-objs.AUTRE"; }
sg_bras "(obj-out)" sg_x_objout sg_ok_objout MORp
sg_bras "(obj-out/Stop)" sg_x_objouth sg_ok_objouth MORh
ok "(obj-out) sans .gitignore de state/local, un puits planté sous sca-reports/semgrep-objs.*/ : hors périmètre à la porte (rc 0) et au Stop (rc 0) ; MORp/MORh rougissent"

# SIGINT to the gate's process GROUP (as a Ctrl-C) while a slow git writes the
# objects, or while the census reads the filter drivers / probes the
# `.gitignore`: no `semgrep-objs.*`, `semgrep-filters.*`, `semgrep-sw.*` left.
# Launched by python with SIGINT back to its default BEFORE the launch (a `&` of
# a non-interactive shell ignores it, and bash cannot restore it).
sg_fauxgit lent-batch <<'SGF'
for a in "$@"; do
  case "$a" in
    --batch)
      sleep 5 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit lent-filtres <<'SGF'
for a in "$@"; do
  case "$a" in
    "^filter"*)
      sleep 5 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit lent-sw <<'SGF'
for a in "$@"; do
  case "$a" in
    --ignored)
      sleep 5 ;;
  esac
done
exec "$real" "$@"
SGF
SG_SIGPY='
import glob, os, signal, subprocess, sys, time
script, depot, path, tmp, motif = sys.argv[1:6]
args = sys.argv[6:]
signal.signal(signal.SIGINT, signal.SIG_DFL)
env = dict(os.environ, PATH=path, TMPDIR=tmp)
p = subprocess.Popen([os.environ["SG_BASH"], script] + args, cwd=depot, env=env,
                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
try:
    p.stdin.write(os.environ.get("SG_STDIN", "").encode("utf-8"))
    p.stdin.close()
except OSError:
    pass
vu = False
fin = time.time() + 30
while time.time() < fin and p.poll() is None:
    if glob.glob(os.path.join(tmp, motif)):
        vu = True
        break
    time.sleep(0.05)
if not vu:
    p.kill()
    p.wait()
    print("absent")
    sys.exit(0)
time.sleep(0.3)
os.killpg(p.pid, signal.SIGINT)
p.wait()
time.sleep(0.5)
# SG_RESTE (optional): the patterns checked AFTER the signal, space-separated;
# absent, the trigger pattern itself (every arm written before it, unchanged).
reste = []
for m in os.environ.get("SG_RESTE", "").split() or [motif]:
    reste += glob.glob(os.path.join(tmp, m))
print(("reste " + " ".join(sorted(os.path.basename(r) for r in reste))) if reste else "retire")
'
sg_sigint() {  # $1 script  $2 repo  $3 PATH  $4 pattern  [args…] -> prints absent | reste | retire
  local _t
  _t="$(mktemp -d "$SG_W/si.XXXXXX")"
  SG_BASH="$SUITE_BASH" SEMGREP_CONFIG="$RULESET" AGENTS_HOOK_HOST=claude "$PY" -c "$SG_SIGPY" "$1" "$2" "$3" "$_t" "$4" "${@:5}"
}
# The objects live under the repository's $OUT: their pattern is passed
# ABSOLUTE, and `os.path.join(tmp, <absolute>)` answers the absolute pattern
# itself — so (obj-sig) and (hk3) watch $OUT, and MT1 (objects back under
# TMPDIR) reddens them: nothing is ever seen there (« absent »).
sg_x_objsig()   { sg_fx_d1a; SG_SI="$(sg_sigint "$SG_S" "$SG_R" "$SG_W/lent-batch:$SG_STUB:$PATH" "$SG_R/.agents/state/local/sca-reports/semgrep-objs.*")"; }
sg_ok_objsig()  { [ "$SG_SI" = retire ] || fail "(obj-sig) SIGINT pendant l'écriture des objets : semgrep-objs.* « $SG_SI » (retire attendu)"; }
sg_x_objsigf()  { sg_fx_sw; SG_SI="$(sg_sigint "$SG_S" "$SG_R" "$SG_W/lent-filtres:$SG_STUB:$PATH" 'semgrep-filters.*')"; }
sg_ok_objsigf() { [ "$SG_SI" = retire ] || fail "(obj-sig2) SIGINT pendant le relevé des pilotes : semgrep-filters.* « $SG_SI » (retire attendu)"; }
sg_x_objsigs()  { sg_fx_sw; SG_SI="$(sg_sigint "$SG_S" "$SG_R" "$SG_W/lent-sw:$SG_STUB:$PATH" 'semgrep-sw.*')"; }
sg_ok_objsigs() { [ "$SG_SI" = retire ] || fail "(obj-sig2) SIGINT pendant la sonde skip-worktree : semgrep-sw.* « $SG_SI » (retire attendu)"; }
sg_bras "(obj-sig)" sg_x_objsig sg_ok_objsig MCL MT1
sg_bras "(obj-sig2/filtres)" sg_x_objsigf sg_ok_objsigf MCL1 MCL0
sg_bras "(obj-sig2/sw)" sg_x_objsigs sg_ok_objsigs MCL2
ok "(obj-sig)(obj-sig2) SIGINT au groupe pendant un git lent (objets sous \$OUT, pilotes, sonde) : semgrep-objs.*, semgrep-filters.*, semgrep-sw.* retirés ; MCL/MCL1/MCL2/MCL0/MT1 rougissent"

# (cl-sig) cleanup() removes SG_SIG and SG_LSERR, as hk_nettoyer does (closing
# review, minor 2): extracted ALONE from the script under test into a file,
# SOURCED (never eval'd), and called with both pointing at real files.
cat > "$SG_W/clsig.sh" <<'SGCLSIG'
# clsig.sh <script> <out dir> — cleanup() alone, SG_SIG and SG_LSERR live
set -u
sed -n '/^cleanup()/,/^}/p' "$1" > "$2/cleanup.fn"
. "$2/cleanup.fn"
REPORT=""; LOCFILE=""; UNPARSED=""; CLEANUP_OWNER="${BASHPID:-$$}"
SG_SIG="$2/semgrep-sig.t"; SG_LSERR="$2/semgrep-lserr.t"
: > "$SG_SIG"; : > "$SG_LSERR"
cleanup
SGCLSIG
sg_x_clsig()  { SG_CL_O="$(mktemp -d "$SG_W/cl.XXXXXX")"; "$SUITE_BASH" "$SG_W/clsig.sh" "$SG_S" "$SG_CL_O" >/dev/null 2>&1; }
sg_ok_clsig() {
  grep -q '^cleanup()' "$SG_CL_O/cleanup.fn" 2>/dev/null || fail "(cl-sig) cleanup() introuvable dans le script : le bras ne prouverait rien"
  [ -e "$SG_CL_O/semgrep-sig.t" ] && fail "(cl-sig) cleanup() laisse SG_SIG"
  [ -e "$SG_CL_O/semgrep-lserr.t" ] && fail "(cl-sig) cleanup() laisse SG_LSERR"
  return 0
}
sg_bras "(cl-sig)" sg_x_clsig sg_ok_clsig MCL3 MCL4
ok "(cl-sig) cleanup() extraite seule et sourcée : SG_SIG et SG_LSERR retirés, comme hk_nettoyer ; MCL3/MCL4 rougissent"

# (sig-reel) the REAL gate, never the extracted function: SIGINT to its group
# while a slow `ls-files --others` (the tree census, never the `--ignored`
# probe) runs — SG_SIG, made before the census, and SG_LSERR, made right before
# that ls-files, are BOTH alive then (measured by the exec-critic, r2/mcl4: the
# real script left nothing, MCL3 left `semgrep-sig.*`, MCL4 `semgrep-lserr.*`).
# The launcher waits for `semgrep-lserr.*`, then checks BOTH patterns.
sg_fauxgit lent-autres <<'SGF'
o=0; i=0
for a in "$@"; do
  case "$a" in
    --others)
      o=1 ;;
    --ignored)
      i=1 ;;
  esac
done
[ "$o" = 1 ] && [ "$i" = 0 ] && sleep 5
exec "$real" "$@"
SGF
sg_x_sigreel()  { sg_fx_d1a; SG_SI="$(SG_RESTE='semgrep-sig.* semgrep-lserr.*' sg_sigint "$SG_S" "$SG_R" "$SG_W/lent-autres:$SG_STUB:$PATH" 'semgrep-lserr.*')"; }
sg_ok_sigreel() { [ "$SG_SI" = retire ] || fail "(sig-reel) SIGINT à la porte pendant ls-files --others : semgrep-sig.*/semgrep-lserr.* « $SG_SI » (retire attendu)"; }
sg_bras "(sig-reel)" sg_x_sigreel sg_ok_sigreel MCL3 MCL4
ok "(sig-reel) porte réelle, SIGINT au groupe pendant un ls-files --others lent : ni semgrep-sig.* ni semgrep-lserr.* ne restent ; MCL3/MCL4 rougissent"

# ---- (idx*) THE INDEX OF A SUBMODULE, AND THE FAIL-CLOSED BRANCHES -----------
sg_fx_sm() {  # T-01M4Z5T6N1DN43K5SEC2DNB63M (sg3/r2/sm.sh): a sink staged IN a submodule, its tree benign
  local _u
  _u="$(mktemp -d "$SG_W/u.XXXXXX")"; $SG_G init -q "$_u"; printf 'y = 1\n' > "$_u/s.py"
  $SG_G -C "$_u" add -A >/dev/null 2>&1; $SG_G -C "$_u" commit -qm s >/dev/null 2>&1
  sg_base README.md 'r\n'
  $SG_G -C "$SG_R" submodule -q add "$_u" sub >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -qm sub >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -q --allow-empty -m vide >/dev/null 2>&1
  printf "$SG_SINK" > "$SG_R/sub/s.py"; git -C "$SG_R/sub" add s.py; printf 'y = 2\n' > "$SG_R/sub/s.py"
}
sg_x_idxsm()  { sg_fx_sm; sg_run "$SG_S" "$SG_R"; }
sg_ok_idxsm() { sg_rc "(idx-sm1)" 1; sg_adit "(idx-sm1)" '"index:sub/s.py:3'; }
sg_bras "(idx-sm1)" sg_x_idxsm sg_ok_idxsm MS6
ok "(idx-sm1) puits indexé dans un sous-module sous un arbre bénin : rc 1, index:sub/s.py:3 ; MS6 rougit"

sg_fauxgit di128 <<'SGF'
for a in "$@"; do
  case "$a" in
    diff-index)
      exit 128 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit di040 <<'SGF'
for a in "$@"; do
  case "$a" in
    diff-index)
      printf ':000000 040000 0000000000000000000000000000000000000000 1111111111111111111111111111111111111111 A\0e\0'
      exit 0 ;;
  esac
done
exec "$real" "$@"
SGF
sg_fauxgit ho128 <<'SGF'
h=0; t=0
for a in "$@"; do
  case "$a" in
    hash-object)
      h=1 ;;
    tree)
      t=1 ;;
  esac
done
[ "$h" = 1 ] && [ "$t" = 1 ] && exit 128
exec "$real" "$@"
SGF
sg_x_idxf1()  { sg_base b.py 'x = 1\n'; sg_ecrire b.py 'x = 2\n'; SG_PATH="$SG_W/di128:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_idxf1() {
  sg_rc "(idx-f1)" 0; sg_dit "(idx-f1)" "git index of a repository not read (diff-index failed)"
  sg_sansverdict "(idx-f1)" "$SG_R"; sg_benin "(idx-f1)"
}
sg_x_idxf2()  { sg_base b.py 'x = 1\n'; sg_ecrire b.py 'x = 2\n'; SG_PATH="$SG_W/di040:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_idxf2() { sg_rc "(idx-f2)" 0; sg_dit "(idx-f2)" "1 sparse-index directory entr(y|ies) not expanded"; sg_benin "(idx-f2)"; }
sg_x_idxf3()  { sg_repo; sg_ecrire b.py 'x = 1\n'; SG_PATH="$SG_W/ho128:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_idxf3() { sg_rc "(idx-f3)" 0; sg_dit "(idx-f3)" "git index of a repository not read (no empty tree)"; sg_benin "(idx-f3)"; }
sg_bras "(idx-f1)" sg_x_idxf1 sg_ok_idxf1 MI1
sg_bras "(idx-f2)" sg_x_idxf2 sg_ok_idxf2 MI2
sg_bras "(idx-f3)" sg_x_idxf3 sg_ok_idxf3 MI3
ok "(idx-f1) diff-index rc 128 / (idx-f2) entrée 040000 / (idx-f3) arbre vide incalculable : chacun DIT, rc 0, jamais bénin ; MI1/MI2/MI3 rougissent"

# ---- (sgr1) A ROOT COMMIT UNDER log.showRoot false -----------------------------
sg_x_sgr1() {
  sg_repo; sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py
  $SG_G -C "$SG_R" commit -qm racine >/dev/null 2>&1
  git -C "$SG_R" config log.showRoot false
  sg_run "$SG_S" "$SG_R"; SG_RC1=$SG_RC; SG_OUT1="$SG_OUT"
  sg_run "$SG_S" "$SG_R" --at HEAD
}
sg_ok_sgr1() {
  [ "$SG_RC1" -eq 1 ] || fail "(sgr1) défaut : rc $SG_RC1, attendu 1 — $SG_OUT1"
  sg_rc "(sgr1) --at HEAD" 1
}
sg_bras "(sgr1)" sg_x_sgr1 sg_ok_sgr1 MR0
ok "(sgr1) commit racine porteur du puits, log.showRoot false : défaut ET --at HEAD rc 1 ; MR0 rougit"

# ---- (hk*) THE HOOK STOP READS THE INDEX (T-01M4Z5T5SKZA63MCWM1VRTZ6D8) -------
# Measured at c2a42ba2 (sg3/h1.sh): D1a at the Stop — rc 0, stdout and stderr EMPTY.
sg_x_hk1()  { sg_fx_d1a; sg_hook "$SG_S" "$SG_R" hk1; }
sg_ok_hk1() { sg_rc "(hk1)" 2; sg_err "(hk1)" "index:k.py:3"; }
sg_bras "(hk1)" sg_x_hk1 sg_ok_hk1 MH1
sg_x_hk2() {  # a CLEAN Stop cached, then a sink `git add`ed under the SAME tree bytes
  sg_base; sg_ecrire k.py "$SG_BENIN"
  sg_hook "$SG_S" "$SG_R" hk2a; SG_RC1=$SG_RC; SG_SP=0
  [ -f "$SG_R/.agents/state/local/semgrep-hook/stop-propre" ] && SG_SP=1
  sg_ecrire k.py "$SG_SINK"; git -C "$SG_R" add k.py; sg_ecrire k.py "$SG_BENIN"
  sg_hook "$SG_S" "$SG_R" hk2b
}
sg_ok_hk2() {
  [ "$SG_RC1" -eq 0 ] && [ "$SG_SP" = 1 ] || fail "(hk2) précondition : le 1er Stop CLEAN doit remplir stop-propre (rc $SG_RC1)"
  sg_rc "(hk2)" 2
}
sg_bras "(hk2)" sg_x_hk2 sg_ok_hk2 MHC
sg_x_hk3()  { sg_fx_d1a; SG_SI="$(SG_STDIN='{"hook_event_name":"Stop","session_id":"hk3"}' sg_sigint "$SG_S" "$SG_R" "$SG_W/lent-batch:$SG_STUB:$PATH" "$SG_R/.agents/state/local/sca-reports/semgrep-objs.*" --hook --event=stop)"; }
sg_ok_hk3() { [ "$SG_SI" = retire ] || fail "(hk3) SIGINT au Stop pendant l'écriture des objets : semgrep-objs.* « $SG_SI » (retire attendu)"; }
sg_bras "(hk3)" sg_x_hk3 sg_ok_hk3 MH2
sg_x_hk4() {  # nominal: a benign file STAGED, the clean verdict cached, then served
  sg_base; sg_ecrire k.py 'x = 1\n'; git -C "$SG_R" add k.py
  sg_hook "$SG_S" "$SG_R" hk4a; SG_RC1=$SG_RC
  sg_hook "$SG_S" "$SG_R" hk4b
}
sg_ok_hk4() {
  [ "$SG_RC1" -eq 0 ] || fail "(hk4) 1er Stop sur un indexé bénin : rc 0 attendu, rc $SG_RC1"
  sg_rc "(hk4)" 0; sg_adit "(hk4)" '"mode":"hook-cache"'
}
sg_bras "(hk4)" sg_x_hk4 sg_ok_hk4
ok "(hk1) Stop D1a rc 2, index:k.py:3 ; (hk2) puits indexé sous des octets d'arbre identiques : cache non servi, rc 2 ; (hk3) SIGINT : aucun semgrep-objs.* sous \$OUT ; (hk4) cache toujours servi ; MH1/MHC/MH2 rougissent"

# (hk5) decision S-01M5162VM18MKHE0E8GGT1ZNCK, which re-decides the closing line
# C3 of the plan: an EXTENSION-LESS name in the index is MUTE at the Stop, as at
# the gate — semgrep 1.175 reads no explicit target without an extension (absent
# from paths.scanned, measured by the exec-critic, r2/w/semx). Measured at
# be3c94ed (devsg7/probe-c3): a staged Dockerfile made EVERY Stop DEGRADED and
# cut its clean-verdict cache. (a) beside a covered benign file: the 1st Stop
# CLEAN in mode hook, nothing DEGRADED, the 2nd served by the cache; (c) the
# extension-less names staged ALONE — one is literally `py`, a base name that IS
# a covered extension, where the guard is load-bearing: the mute exit, NO audit
# line at all (rc 0 + an empty stdout cannot tell mute from a CLEAN scan).
# (hk5u) an UNCOVERED extension stays mute, no audit line either.
SG_SHEBANG_SINK='#!/usr/bin/env python3\nimport os\ndef f(cmd):\n    os.system("echo " + cmd)\n'
sg_x_hk5() {
  sg_base; sg_ecrire k.py 'x = 1\n'; sg_ecrire Dockerfile 'FROM scratch\n'
  sg_ecrire tool "$SG_SHEBANG_SINK"; sg_ecrire py "$SG_SINK"
  git -C "$SG_R" add k.py Dockerfile tool py; sg_ecrire tool '#!/usr/bin/env python3\nx = 1\n'
  sg_hook "$SG_S" "$SG_R" hk5a; SG_RC1=$SG_RC; SG_OUT1="$SG_OUT"; SG_ERR1="$SG_ERR"; SG_AUDIT1="$SG_AUDIT"
  sg_hook "$SG_S" "$SG_R" hk5b; SG_RC2=$SG_RC; SG_OUT2="$SG_OUT"; SG_ERR2="$SG_ERR"; SG_AUDIT2="$SG_AUDIT"
  sg_base; sg_ecrire Dockerfile 'FROM scratch\n'; sg_ecrire py "$SG_SINK"
  git -C "$SG_R" add Dockerfile py
  sg_hook "$SG_S" "$SG_R" hk5c
}
sg_ok_hk5() {
  [ "$SG_RC1" -eq 0 ] && [ -z "$SG_OUT1" ] || fail "(hk5a) 1er Stop, sans-extension indexés à côté d'un couvert : rc 0 et stdout vide attendus, rc $SG_RC1 : $SG_OUT1"
  case "$SG_ERR1$SG_ERR2" in
    *"COVERAGE DEGRADED"*)
      fail "(hk5a) une perte dite sur des noms sans extension à l'index : $SG_ERR1 $SG_ERR2" ;;
  esac
  case "$SG_AUDIT1" in
    *'"couverture":"CLEAN"'*'"mode":"hook"'*) : ;;
    *) fail "(hk5a) 1er Stop : audit CLEAN en mode hook attendu : $SG_AUDIT1" ;;
  esac
  [ "$SG_RC2" -eq 0 ] && [ -z "$SG_OUT2" ] || fail "(hk5b) 2e Stop : rc 0 et stdout vide attendus, rc $SG_RC2 : $SG_OUT2"
  case "$SG_AUDIT2" in
    *'"mode":"hook-cache"'*) : ;;
    *) fail "(hk5b) 2e Stop : le cache du verdict propre n'est pas servi : $SG_AUDIT2" ;;
  esac
  sg_rc "(hk5c)" 0
  [ -z "$SG_OUT" ] || fail "(hk5c) sans-extension indexés seuls : stdout vide attendu : $SG_OUT"
  [ -e "$SG_LAST_DIR/.agents/state/local/sca-reports/audit-log.jsonl" ] && fail "(hk5c) sans-extension indexés seuls : une ligne d'audit écrite, ce n'est pas la sortie muette : $SG_AUDIT"
  return 0
}
sg_bras "(hk5)" sg_x_hk5 sg_ok_hk5 MO16 MO17 MO18
sg_x_hk5u()  { sg_base; sg_ecrire notes.txt 'os.system("x")\n'; git -C "$SG_R" add notes.txt; sg_ecrire notes.txt 'n\n'; sg_hook "$SG_S" "$SG_R" hk5u; }
sg_ok_hk5u() {
  [ "$SG_RC" -eq 0 ] && [ -z "$SG_OUT" ] || fail "(hk5u) extension non couverte à l'index : Stop muet rc 0 attendu, rc $SG_RC : $SG_OUT"
  [ -e "$SG_LAST_DIR/.agents/state/local/sca-reports/audit-log.jsonl" ] && fail "(hk5u) extension non couverte : une ligne d'audit écrite, ce n'est pas la sortie muette : $SG_AUDIT"
  return 0
}
sg_bras "(hk5u)" sg_x_hk5u sg_ok_hk5u MO18
ok "(hk5) noms SANS extension à l'index au Stop (Dockerfile, shebang, py) : muets comme à la porte, jamais DEGRADED, cache servi au 2e Stop, seuls : aucune ligne d'audit ; (hk5u) extension non couverte : muet ; MO16/MO17/MO18 rougissent"

# (out-lien) security advice of the closing pass 2: $OUT, or a parent of it under
# ROOT, reached through a SYMBOLIC LINK. Measured with the `[ -L ]` test off
# (devsg7/probe-lien, MOL1): the gate wrote audit-log.jsonl and
# semgrep-verdict.json where the link points, the Stop audit-log.jsonl and
# semgrep-hook/. Closing review M1: be913df4 then REFUSED, rc 0 — one committed
# link turned the SAST off over a committed sink (devsg8/drive.sh m1). Now,
# gate AND Stop SCAN in a private directory: the sink found (rc 1 / rc 2), the
# loss said, the link's TARGET EMPTY, the private directory removed (TMPDIR
# empty). MOL2 (only `sca-reports` tested) reddens the parent case; MLP/MLPh
# (the old refusal), MLPc/MLPch (the private directory left) each one.
sg_fx_lien() {  # $1 = parent|feuille -> SG_R (a sink in the dirty tree), SG_C (the link's target, empty)
  sg_base k.py 'x = 1\n'; sg_ecrire k.py "$SG_SINK"
  SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"
  if [ "$1" = parent ]; then
    mkdir -p "$SG_R/.agents/state"; ln -s "$SG_C" "$SG_R/.agents/state/local"
  else
    mkdir -p "$SG_R/.agents/state/local"; ln -s "$SG_C" "$SG_R/.agents/state/local/sca-reports"
  fi
}
sg_x_lien() {  # $1 = parent|feuille
  sg_fx_lien "$1"; sg_run "$SG_S" "$SG_R"; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"; SG_CP="$(ls -A "$SG_C")"; SG_TP="$(ls -A "$SG_LAST_TMP")"
  sg_fx_lien "$1"; sg_hook "$SG_S" "$SG_R" lien; SG_CH="$(ls -A "$SG_C")"; SG_TH="$(ls -A "$SG_LAST_TMP")"
}
sg_ok_lien() {  # $1 label
  [ "$SG_RCP" -eq 1 ] || fail "$1 porte : rc $SG_RCP, attendu 1 (le puits lu malgré le lien) — $SG_OUTP"
  case "$SG_OUTP" in
    *"audit line and common verdict not kept (report directory is a symbolic link; private directory used)"*) : ;;
    *) fail "$1 porte : perte non dite — $SG_OUTP" ;;
  esac
  [ -z "$SG_CP" ] || fail "$1 porte : écrit derrière le lien : $SG_CP"
  [ -z "$SG_TP" ] || fail "$1 porte : répertoire privé laissé sous TMPDIR : $SG_TP"
  sg_rc "$1 Stop" 2
  sg_err "$1 Stop" "audit line, markers and clean-verdict cache not kept (report directory is a symbolic link; private directory used)"
  [ -z "$SG_CH" ] || fail "$1 Stop : écrit derrière le lien : $SG_CH"
  [ -z "$SG_TH" ] || fail "$1 Stop : répertoire privé laissé sous TMPDIR : $SG_TH"
  return 0
}
sg_x_lienp()  { sg_x_lien parent; }
sg_ok_lienp() { sg_ok_lien "(out-lien/parent)"; }
sg_x_lienf()  { sg_x_lien feuille; }
sg_ok_lienf() { sg_ok_lien "(out-lien/feuille)"; }
sg_bras "(out-lien/parent)" sg_x_lienp sg_ok_lienp MOL1 MOL2 MLP MLPh MLPc MLPch
sg_bras "(out-lien/feuille)" sg_x_lienf sg_ok_lienf MOL1 MLP MLPh
# The critic's scenario: the link COMMITTED together with the sink, --at HEAD.
sg_x_lienat() {
  sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"
  ln -s "$SG_C" "$SG_R/.agents/state"; sg_ecrire k.py "$SG_SINK"
  $SG_G -C "$SG_R" add -f -- k.py .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm sinklien >/dev/null 2>&1
  sg_run "$SG_S" "$SG_R" --at HEAD; SG_CP="$(ls -A "$SG_C")"
}
sg_ok_lienat() {
  sg_rc "(out-lien/at)" 1; sg_dit "(out-lien/at)" "private directory used"
  [ -z "$SG_CP" ] || fail "(out-lien/at) écrit derrière le lien : $SG_CP"
  sg_vide "(out-lien/at)"
}
sg_bras "(out-lien/at)" sg_x_lienat sg_ok_lienat MOL1 MLP
# No private directory can be made (TMPDIR 555): the refusal before any write stays.
if [ -z "$ILL_SKIP" ]; then
  sg_x_lienrefus() {
    local _t
    sg_fx_lien feuille; _t="$(mktemp -d "$SG_W/t.XXXXXX")"; chmod 555 "$_t"
    SG_TMP="$_t" sg_run "$SG_S" "$SG_R"; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"
    SG_TMP="$_t" sg_hook "$SG_S" "$SG_R" lienrefus
    chmod 755 "$_t"; SG_CP="$(ls -A "$SG_C")"
  }
  sg_ok_lienrefus() {
    [ "$SG_RCP" -eq 0 ] || fail "(out-lien/refus) porte : rc $SG_RCP, attendu 0 — $SG_OUTP"
    case "$SG_OUTP" in
      *"no private directory could be made: refused before the census"*) : ;;
      *) fail "(out-lien/refus) porte : refus non dit — $SG_OUTP" ;;
    esac
    sg_rc "(out-lien/refus) Stop" 0
    sg_dit "(out-lien/refus) Stop" "no private directory could be made; refused before any write"
    [ -z "$SG_CP" ] || fail "(out-lien/refus) écrit derrière le lien : $SG_CP"
    return 0
  }
  sg_bras "(out-lien/refus)" sg_x_lienrefus sg_ok_lienrefus
else
  echo "  SKIP (out-lien/refus) : $ILL_SKIP"
fi
ok "(out-lien) .agents/state, .agents/state/local ou sca-reports en lien symbolique (commité avec le puits, --at HEAD compris) : porte rc 1 et Stop rc 2 dans un répertoire privé, perte dite, rien écrit derrière le lien, TMPDIR vide ; sans répertoire privé possible : refus dit ; MOL1/MOL2/MLP/MLPh/MLPc/MLPch rougissent"

# (out-lien/unparsed) closing review 2, F1 (fixture fxU): the PARSE opened
# `$OUT/.semgrep-unparsed.<pid>` "w", which follows a link — a committed link
# at that GUESSABLE name made the gate truncate the file behind it, outside the
# repository (rc 0, `clean on the diff.`, 0 bytes). The name is now mktemp's
# (O_EXCL, random). The link carries the pid of the script under test: `exec`
# keeps the pid of the shell that made it. MUP (the pid name restored)
# truncates the file — the arm reddens.
sg_x_unp() {
  sg_base a.py 'x = 1\n'; sg_ecrire a.py 'x = 1\ny = 2\n'
  mkdir -p "$SG_R/.agents/state/local/sca-reports"
  SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; printf 'INTACT\n' > "$SG_C/victime"
  SG_LAST_TMP="$(mktemp -d "$SG_W/t.XXXXXX")"; SG_ERR=""
  ( cd "$SG_R" && export PATH="$SG_STUB:$PATH" TMPDIR="$SG_LAST_TMP" SEMGREP_CONFIG="$RULESET" SG_UV="$SG_C/victime" \
      && "$SUITE_BASH" -c 'ln -s "$SG_UV" ".agents/state/local/sca-reports/.semgrep-unparsed.$$" && exec "$0" "$1"' "$SUITE_BASH" "$SG_S" ) >"$SG_W/uo" 2>&1
  SG_RC=$?; SG_OUT="$(cat "$SG_W/uo")"
}
sg_ok_unp() {
  [ "$(cat "$SG_C/victime" 2>/dev/null)" = INTACT ] \
    || fail "(out-lien/unparsed) le fichier derrière .semgrep-unparsed.<pid> a été tronqué ou réécrit — sortie : $SG_OUT"
  sg_rc "(out-lien/unparsed)" 0
  return 0
}
sg_bras "(out-lien/unparsed)" sg_x_unp sg_ok_unp MUP
ok "(out-lien/unparsed) lien commité au nom devinable .semgrep-unparsed.<pid> (le pid du script) : le fichier derrière reste INTACT (mktemp, O_EXCL) ; MUP le tronque"

# (out-lien/kit)(out-lien/events) exec-critic of 13a3cebf (ecsg3/m1.sh, replayed
# in devsg9/m1kit.sh): in a KIT-SHAPED repository (emit-event.sh + events.py
# present) the scan EVENT still landed behind a committed `.agents/state` link —
# `<target>/events/<day>.jsonl`, gate and Stop. Now it is not emitted: said in
# the loss line (OUT_LIEN), or in a note for a link at `.agents/state/events`
# itself; the target stays EMPTY. MEV/MEV2 (the skip removed) each make the
# event land there — the paired witness that the emitter of the fixture works.
SG_EMIT="$REPO_ROOT/.claude/hooks/emit-event.sh"; SG_EVPY="$REPO_ROOT/.agents/bin/events.py"
if [ -f "$SG_EMIT" ] && [ -f "$SG_EVPY" ] && [ -n "$PY" ]; then
  sg_kit() {  # SG_R becomes kit-shaped: THIS kit's emitter and events.py, both ignored
    mkdir -p "$SG_R/.claude/hooks" "$SG_R/.agents/bin"
    cp "$SG_EMIT" "$SG_R/.claude/hooks/"; cp "$SG_EVPY" "$SG_R/.agents/bin/"
    printf '.claude/\n.agents/bin/\n' >> "$SG_R/.git/info/exclude"
  }
  sg_x_lienkit() {
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_kit
    ln -s "$SG_C" "$SG_R/.agents/state"; sg_ecrire k.py "$SG_SINK"
    $SG_G -C "$SG_R" add -f -- k.py .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm sinklien >/dev/null 2>&1
    AGENTS_EVENTS_DIR="" sg_run "$SG_S" "$SG_R" --at HEAD; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"; SG_CP="$(ls -A "$SG_C")"
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_kit
    ln -s "$SG_C" "$SG_R/.agents/state"
    $SG_G -C "$SG_R" add -f -- .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm lien >/dev/null 2>&1
    sg_ecrire k.py "$SG_SINK"
    AGENTS_EVENTS_DIR="" sg_hook "$SG_S" "$SG_R" lienkit; SG_CH="$(ls -A "$SG_C")"
  }
  sg_ok_lienkit() {
    [ "$SG_RCP" -eq 1 ] || fail "(out-lien/kit) porte : rc $SG_RCP, attendu 1 — $SG_OUTP"
    case "$SG_OUTP" in
      *"private directory used); scan event not emitted"*) : ;;
      *) fail "(out-lien/kit) porte : l'événement non émis n'est pas dit — $SG_OUTP" ;;
    esac
    [ -z "$SG_CP" ] || fail "(out-lien/kit) porte : écrit derrière le lien : $SG_CP"
    sg_rc "(out-lien/kit) Stop" 2
    sg_err "(out-lien/kit) Stop" "private directory used); scan event not emitted"
    [ -z "$SG_CH" ] || fail "(out-lien/kit) Stop : écrit derrière le lien : $SG_CH"
    return 0
  }
  sg_bras "(out-lien/kit)" sg_x_lienkit sg_ok_lienkit MEV
  sg_x_lienev() {
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_kit
    mkdir -p "$SG_R/.agents/state"; ln -s "$SG_C" "$SG_R/.agents/state/events"; sg_ecrire k.py "$SG_SINK"
    AGENTS_EVENTS_DIR="" sg_run "$SG_S" "$SG_R"; SG_CP="$(ls -A "$SG_C")"
  }
  sg_ok_lienev() {
    sg_rc "(out-lien/events)" 1; sg_dit "(out-lien/events)" "scan event not emitted (.agents/state/events is a symbolic link"
    [ -z "$SG_CP" ] || fail "(out-lien/events) écrit derrière le lien : $SG_CP"
    return 0
  }
  sg_bras "(out-lien/events)" sg_x_lienev sg_ok_lienev MEV2
  # (out-lien/evdir) exec-critic of 7c78f87f, MINEUR: the same committed
  # `.agents/state` link, AGENTS_EVENTS_DIR an ABSOLUTE directory outside the
  # repository — no link of the repository on that path: the event is emitted
  # THERE (gate and Stop), said so, the link target stays EMPTY. MEV3 (the
  # redirection ignored) keeps the event out — the arm reddens.
  sg_x_lienevd() {
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; SG_EVD="$(mktemp -d "$SG_W/evd.XXXXXX")"; sg_kit
    ln -s "$SG_C" "$SG_R/.agents/state"; sg_ecrire k.py "$SG_SINK"
    $SG_G -C "$SG_R" add -f -- k.py .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm sinklien >/dev/null 2>&1
    AGENTS_EVENTS_DIR="$SG_EVD" sg_run "$SG_S" "$SG_R" --at HEAD; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"; SG_CP="$(ls -A "$SG_C")"; SG_EP="$(ls -A "$SG_EVD")"
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; SG_EVD="$(mktemp -d "$SG_W/evd.XXXXXX")"; sg_kit
    ln -s "$SG_C" "$SG_R/.agents/state"
    $SG_G -C "$SG_R" add -f -- .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm lien >/dev/null 2>&1
    sg_ecrire k.py "$SG_SINK"
    AGENTS_EVENTS_DIR="$SG_EVD" sg_hook "$SG_S" "$SG_R" lienevd; SG_CH="$(ls -A "$SG_C")"; SG_EH="$(ls -A "$SG_EVD")"
  }
  sg_ok_lienevd() {
    [ "$SG_RCP" -eq 1 ] || fail "(out-lien/evdir) porte : rc $SG_RCP, attendu 1 — $SG_OUTP"
    case "$SG_OUTP" in
      *"private directory used); scan event emitted to AGENTS_EVENTS_DIR (outside the repository)"*) : ;;
      *) fail "(out-lien/evdir) porte : l'émission vers AGENTS_EVENTS_DIR n'est pas dite — $SG_OUTP" ;;
    esac
    [ -n "$SG_EP" ] || fail "(out-lien/evdir) porte : aucun événement dans AGENTS_EVENTS_DIR — $SG_OUTP"
    [ -z "$SG_CP" ] || fail "(out-lien/evdir) porte : écrit derrière le lien : $SG_CP"
    sg_rc "(out-lien/evdir) Stop" 2
    sg_err "(out-lien/evdir) Stop" "private directory used); scan event emitted to AGENTS_EVENTS_DIR (outside the repository)"
    [ -n "$SG_EH" ] || fail "(out-lien/evdir) Stop : aucun événement dans AGENTS_EVENTS_DIR — $SG_ERR"
    [ -z "$SG_CH" ] || fail "(out-lien/evdir) Stop : écrit derrière le lien : $SG_CH"
    return 0
  }
  sg_bras "(out-lien/evdir)" sg_x_lienevd sg_ok_lienevd MEV3
  # (out-lien/alias) exec-critic of 03c4ce7a, MAJEUR: AGENTS_EVENTS_DIR naming
  # the repository's OWN `.agents/state/events` through a LINKED spelling of
  # ROOT (here a link to SG_R; on macOS `/tmp` for `/private/tmp`) was read as
  # outside by a text prefix, and the event was written behind the committed
  # `.agents/state` link — gate and Stop (devmulti-sg10/alias.sh on 03c4ce7a:
  # `events/<day>.jsonl` behind the link, both). A RELATIVE value, made
  # absolute against the physical cwd (ROOT), likewise. Now judged by identity:
  # nothing behind the link, `not emitted` said. MEV4 (the identity test of the
  # textual ancestors removed) writes behind the link again — the arm reddens.
  sg_lienkit_r() {  # $1 = committed sink (1) or dirty sink (0): SG_R kit-shaped, `.agents/state` a committed link to SG_C, SG_AL a link to SG_R
    sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_kit
    ln -s "$SG_C" "$SG_R/.agents/state"
    if [ "$1" = 1 ]; then sg_ecrire k.py "$SG_SINK"; fi
    $SG_G -C "$SG_R" add -f -- k.py .agents/state >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm lien >/dev/null 2>&1
    if [ "$1" = 0 ]; then sg_ecrire k.py "$SG_SINK"; fi
    SG_AL="$(mktemp -d "$SG_W/al.XXXXXX")/r"; ln -s "$SG_R" "$SG_AL"
  }
  sg_x_lienal() {
    sg_lienkit_r 1
    AGENTS_EVENTS_DIR="$SG_AL/.agents/state/events" sg_run "$SG_S" "$SG_R" --at HEAD; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"; SG_CP="$(ls -A "$SG_C")"
    sg_lienkit_r 1
    AGENTS_EVENTS_DIR=.agents/state/events sg_run "$SG_S" "$SG_R" --at HEAD; SG_RCR=$SG_RC; SG_OUTR="$SG_OUT"; SG_CR="$(ls -A "$SG_C")"
    sg_lienkit_r 0
    AGENTS_EVENTS_DIR="$SG_AL/.agents/state/events" sg_hook "$SG_S" "$SG_R" lienal; SG_CH="$(ls -A "$SG_C")"
  }
  sg_ok_lienal() {
    [ "$SG_RCP" -eq 1 ] || fail "(out-lien/alias) porte : rc $SG_RCP, attendu 1 — $SG_OUTP"
    case "$SG_OUTP" in
      *"private directory used); scan event not emitted"*) : ;;
      *) fail "(out-lien/alias) porte : « scan event not emitted » absent — $SG_OUTP" ;;
    esac
    [ -z "$SG_CP" ] || fail "(out-lien/alias) porte : écrit derrière le lien par un chemin lié vers le dépôt : $SG_CP"
    [ "$SG_RCR" -eq 1 ] || fail "(out-lien/alias) porte, valeur relative : rc $SG_RCR, attendu 1 — $SG_OUTR"
    case "$SG_OUTR" in
      *"private directory used); scan event not emitted"*) : ;;
      *) fail "(out-lien/alias) porte, valeur relative : « scan event not emitted » absent — $SG_OUTR" ;;
    esac
    [ -z "$SG_CR" ] || fail "(out-lien/alias) porte, valeur relative : écrit derrière le lien : $SG_CR"
    sg_rc "(out-lien/alias) Stop" 2
    sg_err "(out-lien/alias) Stop" "private directory used); scan event not emitted"
    [ -z "$SG_CH" ] || fail "(out-lien/alias) Stop : écrit derrière le lien par un chemin lié vers le dépôt : $SG_CH"
    return 0
  }
  sg_bras "(out-lien/alias)" sg_x_lienal sg_ok_lienal MEV4
  ok "(out-lien/kit)(out-lien/events)(out-lien/evdir)(out-lien/alias) dépôt de forme kit (emit-event.sh + events.py), .agents/state commité en lien (porte --at HEAD, Stop) ou .agents/state/events en lien : événement non émis, dit, rien écrit derrière le lien ; AGENTS_EVENTS_DIR absolu hors du dépôt : événement émis LÀ, dit, lien vide ; le propre .agents/state/events du dépôt par un chemin LIÉ ou relatif : non émis, dit, lien vide (porte et Stop) ; MEV/MEV2/MEV3/MEV4 rougissent"
else
  echo "  SKIP (out-lien/kit)(out-lien/events)(out-lien/evdir)(out-lien/alias) : emit-event.sh, events.py ou python absent ici"
  sg_saute "MEV MEV2 MEV3 MEV4" "pas d'émetteur de forme kit ici"
fi

# (out-lien/verdict) exec-critic of 7c78f87f, security advisory: under a link at
# a FIXED name (`audit-log.jsonl`) the gate's `rm` of the previous verdict only
# reached its private directory, and the repository's own STALE
# `semgrep-verdict.json` outlived the run (devmulti-sg10/verdict.sh on 03c4ce7a:
# LEFT). Now removed — the link target untouched; behind a linked DIRECTORY
# (`.agents/state`) a verdict is never deleted. MVD (the removal cut) reddens.
sg_x_lienvd() {
  sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_ecrire k.py "$SG_SINK"
  mkdir -p "$SG_R/.agents/state/local/sca-reports"
  printf '{"stale":true}\n' > "$SG_R/.agents/state/local/sca-reports/semgrep-verdict.json"
  printf 'cible\n' > "$SG_C/audit"; ln -s "$SG_C/audit" "$SG_R/.agents/state/local/sca-reports/audit-log.jsonl"
  AGENTS_EVENTS_DIR="" sg_run "$SG_S" "$SG_R"; SG_RCP=$SG_RC; SG_OUTP="$SG_OUT"
  SG_VP=0; [ -e "$SG_R/.agents/state/local/sca-reports/semgrep-verdict.json" ] && SG_VP=1
  SG_TP="$(cat "$SG_C/audit")"
  sg_base k.py 'x = 1\n'; SG_C="$(mktemp -d "$SG_W/c.XXXXXX")"; sg_ecrire k.py "$SG_SINK"
  mkdir -p "$SG_C/local/sca-reports"; printf '{"derriere":true}\n' > "$SG_C/local/sca-reports/semgrep-verdict.json"
  ln -s "$SG_C" "$SG_R/.agents/state"
  AGENTS_EVENTS_DIR="" sg_run "$SG_S" "$SG_R"
  SG_VD=0; [ -e "$SG_C/local/sca-reports/semgrep-verdict.json" ] && SG_VD=1
}
sg_ok_lienvd() {
  [ "$SG_RCP" -eq 1 ] || fail "(out-lien/verdict) rc $SG_RCP, attendu 1 — $SG_OUTP"
  [ "$SG_VP" = 0 ] || fail "(out-lien/verdict) le semgrep-verdict.json PÉRIMÉ du dépôt survit au run (lien à nom fixe audit-log.jsonl)"
  [ "$SG_TP" = cible ] || fail "(out-lien/verdict) la cible du lien audit-log.jsonl a changé : $SG_TP"
  [ "$SG_VD" = 1 ] || fail "(out-lien/verdict) un verdict DERRIÈRE un répertoire lié (.agents/state) a été supprimé"
  return 0
}
sg_bras "(out-lien/verdict)" sg_x_lienvd sg_ok_lienvd MVD
ok "(out-lien/verdict) lien à nom fixe (audit-log.jsonl) : le semgrep-verdict.json périmé du dépôt retiré, la cible du lien intacte ; derrière .agents/state lié : jamais supprimé ; MVD rougit"

# (out-lien/noms) closing review M2: a committed link at a FIXED name written in
# place — `sca-reports/audit-log.jsonl` (appended by audit), `semgrep-hook` (the
# markers), `semgrep-hook/stop-propre` (truncated by the clean-verdict cache).
# Measured at be913df4 (devsg8/drive.sh m2): the Stop truncated the file behind
# stop-propre. Each name is now tested: a private directory, the victim intact,
# the link kept. MOL3/MOL4/MOL5 drop one name each; MOL6 drops stop-propre AND
# the `rm -f` before the cache write.
sg_fx_nom() {  # $1 = audit|hookdir|propre -> SG_R (a benign dirty tree), SG_V (the victim), SG_L (the link)
  local _l
  sg_base b.py 'x = 1\n'
  case "$1" in
    hookdir)
      SG_V="$(mktemp -d "$SG_W/v.XXXXXX")"; _l=.agents/state/local/semgrep-hook ;;
    audit)
      SG_V="$SG_W/victime.audit"; printf 'VICTIME\n' > "$SG_V"; _l=.agents/state/local/sca-reports/audit-log.jsonl ;;
    *)
      SG_V="$SG_W/victime.propre"; printf 'VICTIME\n' > "$SG_V"; _l=.agents/state/local/semgrep-hook/stop-propre ;;
  esac
  mkdir -p "$SG_R/${_l%/*}"; ln -s "$SG_V" "$SG_R/$_l"; SG_L="$SG_R/$_l"
  $SG_G -C "$SG_R" add -f -- "$_l" >/dev/null 2>&1; $SG_G -C "$SG_R" commit -qm lien >/dev/null 2>&1
  $SG_G -C "$SG_R" commit -q --allow-empty -m vide >/dev/null 2>&1
  sg_ecrire b.py 'x = 2\n'
}
sg_x_nomaudit()  { sg_fx_nom audit; sg_run "$SG_S" "$SG_R"; }
sg_ok_nomaudit() {
  sg_rc "(out-lien/audit-log.jsonl)" 0
  [ "$(cat "$SG_V")" = VICTIME ] || fail "(out-lien/audit-log.jsonl) la victime derrière le lien a changé : $(cat "$SG_V")"
  [ -L "$SG_L" ] || fail "(out-lien/audit-log.jsonl) le lien commité a disparu"
  sg_dit "(out-lien/audit-log.jsonl)" "private directory used"; sg_vide "(out-lien/audit-log.jsonl)"
}
sg_x_nomdir()  { sg_fx_nom hookdir; sg_hook "$SG_S" "$SG_R" nomdir; }
sg_ok_nomdir() {
  [ -z "$(ls -A "$SG_V")" ] || fail "(out-lien/semgrep-hook) écrit derrière le lien : $(ls -A "$SG_V")"
  [ -L "$SG_L" ] || fail "(out-lien/semgrep-hook) le lien commité a disparu"
  sg_err "(out-lien/semgrep-hook)" "private directory used"; sg_vide "(out-lien/semgrep-hook)"
}
sg_x_nompropre()  { sg_fx_nom propre; sg_hook "$SG_S" "$SG_R" nompropre; }
sg_ok_nompropre() {
  [ "$(cat "$SG_V")" = VICTIME ] || fail "(out-lien/stop-propre) la victime derrière le lien a changé : $(cat "$SG_V")"
  [ -L "$SG_L" ] || fail "(out-lien/stop-propre) le lien commité a disparu"
  sg_err "(out-lien/stop-propre)" "private directory used"; sg_vide "(out-lien/stop-propre)"
}
sg_bras "(out-lien/audit-log.jsonl)" sg_x_nomaudit sg_ok_nomaudit MOL3
sg_bras "(out-lien/semgrep-hook)" sg_x_nomdir sg_ok_nomdir MOL4
sg_bras "(out-lien/stop-propre)" sg_x_nompropre sg_ok_nompropre MOL5 MOL6
# The `rm -f` before the cache write, ALONE: with the name test dropped (MOL5)
# the victim stays intact (the link is removed, never followed); without the
# `rm -f` too (MOL6) the cache write truncates it.
sg_ok_rmf() { [ "$(cat "$SG_V")" = VICTIME ] || fail "(out-lien/rm) victime tronquée par l'écriture du cache : $(cat "$SG_V")"; }
SG_S="$SG_MUT/MOL5.sh"; sg_x_nompropre; sg_ok_rmf
SG_S="$SG_MUT/MOL6.sh"; sg_x_nompropre
( sg_ok_rmf ) >/dev/null 2>&1 && fail "(sgm) MOL6 : le mutant SURVIT à (out-lien/rm) — le rm -f avant l'écriture du cache n'est pas témoigné"
SG_S="$SCRIPT"
ok "(out-lien/noms) lien commité sur audit-log.jsonl / semgrep-hook / stop-propre : répertoire privé, victime intacte, lien conservé ; sans le test du nom, le rm -f protège encore la victime (MOL5), sans lui elle est tronquée (MOL6) ; MOL3/MOL4/MOL5/MOL6 rougissent"

# (m3)(m3h) closing review M3: a rule `paths:` filter judges an object on its
# MACHINE path — a rule excluding `.agents/` (here the stub's SG_STUB_EXCL, as
# semgrep does, measured devsg8/m3.sh) left `index:k.py` unscanned while its
# twin k.py was: CLEAN at the gate, a mute Stop. Now a COUNTED loss.
sg_x_m3()   { sg_fx_d1a; SG_STUB_EXCL=/.agents/ sg_run "$SG_S" "$SG_R"; }
sg_ok_m3()  {
  sg_rc "(m3)" 0; sg_dit "(m3)" "1 git object(s) not scanned while their working-tree twin was"
  sg_benin "(m3)"; sg_sansverdict "(m3)" "$SG_R"
}
sg_x_m3h()  { sg_fx_d1a; SG_STUB_EXCL=/.agents/ sg_hook "$SG_S" "$SG_R" m3h; }
sg_ok_m3h() {
  sg_rc "(m3h)" 0; sg_dit "(m3h)" '"systemMessage": "COVERAGE DEGRADED'
  sg_err "(m3h)" "git object(s) not scanned while their working-tree twin was"
}
sg_bras "(m3)" sg_x_m3 sg_ok_m3 MM3 MM3s
sg_bras "(m3h)" sg_x_m3h sg_ok_m3h MM3 MM3s
ok "(m3)(m3h) règle excluant .agents/ : l'objet index:k.py non scanné quand son jumeau l'est => perte comptée, porte sans phrase bénigne ni verdict, Stop DEGRADED ; MM3/MM3s rougissent"

# (m2)(m2h) closing review m2: semgrep runs `git remote get-url` and `git
# ls-remote --get-url` in ROOT (measured, devsg8/m2c.sh): fsmonitor and hooks
# are cut for ITS git too, by GIT_CONFIG_COUNT. The stub records what it got.
sg_x_m2()   { sg_fx_d1a; : > "$SG_W/envf"; SG_STUB_ENVF="$SG_W/envf" sg_run "$SG_S" "$SG_R"; SG_ENVF="$(cat "$SG_W/envf")"; }
sg_ok_m2()  { [ "$SG_ENVF" = "2|core.fsmonitor|false|core.hooksPath|/dev/null" ] || fail "(m2) porte : semgrep lancé sans fsmonitor ni hooks coupés pour son git : « $SG_ENVF »"; }
sg_x_m2h()  { sg_fx_d1a; : > "$SG_W/envf"; SG_STUB_ENVF="$SG_W/envf" sg_hook "$SG_S" "$SG_R" m2h; SG_ENVF="$(cat "$SG_W/envf")"; }
sg_ok_m2h() { [ "$SG_ENVF" = "2|core.fsmonitor|false|core.hooksPath|/dev/null" ] || fail "(m2h) Stop : semgrep lancé sans fsmonitor ni hooks coupés pour son git : « $SG_ENVF »"; }
sg_bras "(m2)" sg_x_m2 sg_ok_m2 MSG1
sg_bras "(m2h)" sg_x_m2h sg_ok_m2h MSG2
ok "(m2)(m2h) semgrep reçoit GIT_CONFIG_COUNT=2 core.fsmonitor=false core.hooksPath=/dev/null, porte et Stop ; MSG1/MSG2 rougissent"

# ---- (prs*) THE PARSE CANNOT FAIL OPEN (security-code-review S-01M52B4FB4) ---
# Measured on d0c2c238: the parser of the report died — a JSON list, a result
# that is not an object, a path carrying a lone surrogate (a REAL finding lost),
# a failed mktemp — and the gate said `clean on the diff.`, rc 0: no `set -e`,
# an empty count defaulted to 0, `[ "" -eq 0 ]` (rc 2) read as "full scope".
# Each guard now names ITS reason and each arm asserts the reason of the layer
# it tests, so removing that layer reddens the arm even where a deeper layer
# still degrades. (prs4) and (prs5) are DIRECT witnesses: the fake python3
# makes the parser exit 7 after a well-formed line (only the rc check holds),
# or prints a stray stdout line before the figures (only the shape check
# holds). MPALL removes every layer — the state of d0c2c238 — and the three
# reports read `clean on the diff.` again. The count check (5) and the scope
# branch are unreached on the unmutated script (the shape check holds first):
# defense in depth, removed by MPALL only. Fakes read the real path from a DATA
# file beside them, as the fake gits; the fake python3 touches ONLY the PARSE
# call (`-` + 3 arguments) and the locations call (`-` + 1 argument) — and, in
# mode hkb, the hook's PHASE B call (the one call that sets HK_REPORT).
# T-01M52EC9PE7758B4ZG95YXMSJN: VALID JSON OF THE WRONG SHAPE. Measured on
# 6fc0450c: `{}`, `{"results":{}}`, errors+paths without results, errors/paths/
# scanned mistyped read `clean on the diff.`, rc 0, audit CLEAN — and `{}`
# without python too; `[]` and `{"results":[1]}` only degraded because the
# parser DIED. (prs1)(prs2)(prs10)-(prs16): the shape test `forme` holds, one
# witness per clause (results, errors, paths, scanned — reserve C1 of the
# plan-critic), each reddened by MPFS and by the mutant of its own clause;
# (prs1)(prs2) lose MPRC/MPALL, which (prs3)(prs4)(prs5) keep. (prs13): guard
# (6) of the no-python branch, MPRN; (prs17): its truncation test, a report cut
# after `{"results":[` with rc 0 (measured on fc6c0aa3: `clean on the diff.`,
# rc 0, audit CLEAN), MPTR. (hrs1)(hrs2): the hook, claude/Stop only
# (sg_hook), a malformed report (MHFS: CLEAN came back and filled stop-propre)
# and a dead PHASE B (MHBELT: stdout empty again). (prsp): the three copies of
# the shape test agree on one corpus.
SG_REAL_PY="$(command -v "$PY")"; SG_REAL_MK="$(command -v mktemp)"
sg_faux() {  # $1 dir under SG_W  $2 command name  $3 real path ; stdin = the body after the `real=` line
  mkdir -p "$SG_W/$1"; printf '%s' "$3" > "$SG_W/$1/real"
  { printf '%s\n' '#!/usr/bin/env bash'; printf '%s\n' "$SG_REEL"; cat; } > "$SG_W/$1/$2"
  chmod +x "$SG_W/$1/$2"
}
sg_faux fauxpy python3 "$SG_REAL_PY" <<'SGF'
if [ "${1:-}" = "-" ] && [ "$#" -eq 4 ]; then
  case "${SG_PY_MODE:-}" in
    rc)
      "$real" "$@"; exit 7 ;;
    bruit)
      printf 'avertissement sur stdout\n'; exec "$real" "$@" ;;
  esac
fi
if [ "${1:-}" = "-" ] && [ "$#" -eq 2 ] && [ "${SG_PY_MODE:-}" = loc ]; then
  exit 3
fi
if [ "${SG_PY_MODE:-}" = hkb ] && [ -n "${HK_REPORT:-}" ]; then
  exit 9
fi
exec "$real" "$@"
SGF
sg_faux fauxmk mktemp "$SG_REAL_MK" <<'SGF'
if [ -n "${SG_MK_FAIL:-}" ]; then
  case "$*" in
    *"$SG_MK_FAIL"*)
      exit 1 ;;
  esac
fi
exec "$real" "$@"
SGF
printf '[]\n' > "$SG_W/r-liste.json"
printf '%s\n' '{"results":[1],"errors":[],"paths":{"scanned":["a.py"]}}' > "$SG_W/r-nonobj.json"
printf '%s\n' '{"results":[{"check_id":"sg.sink","path":"a\udc80.py","start":{"line":3},"extra":{"severity":"ERROR","message":"m"}}],"errors":[],"paths":{"scanned":["a.py"]}}' > "$SG_W/r-surr.json"
sg_fx_prs()  { sg_base a.py 'x = 1\n'; sg_ecrire a.py 'x = 1\ny = 2\n'; }
sg_fx_prsk() { sg_base a.py 'x = 1\n'; sg_ecrire a.py "$SG_SINK"; }
sg_ok_prs_deg() {  # $1 label  $2 the reason of the layer under test
  sg_rc "$1" 0; sg_benin "$1"
  sg_dit "$1" "COVERAGE DEGRADED: semgrep report parse — $2"
  sg_adit "$1" '"verdict":"DEGRADED"'
}
sg_x_prs1()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-liste.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs1() { sg_ok_prs_deg "(prs1) rapport liste" "report malformed"; }
sg_x_prs2()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-nonobj.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs2() { sg_ok_prs_deg "(prs2) résultat non objet" "report malformed"; }
sg_x_prs3()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-surr.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs3() { sg_ok_prs_deg "(prs3) chemin à surrogate" "parser exited 1"; }
sg_x_prs4()  { sg_fx_prs; SG_PY_MODE=rc SG_PATH="$SG_W/fauxpy:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs4() { sg_ok_prs_deg "(prs4) parseur rc 7 après une ligne bien formée" "parser exited 7"; }
sg_x_prs5()  { sg_fx_prsk; SG_PY_MODE=bruit SG_PATH="$SG_W/fauxpy:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs5() { sg_ok_prs_deg "(prs5) ligne parasite avant les chiffres, puits réel" "parser output malformed"; }
sg_x_prs6()  { sg_fx_prs; SG_MK_FAIL=.semgrep-loc. SG_PATH="$SG_W/fauxmk:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs6() { sg_ok_prs_deg "(prs6) mktemp de LOCFILE en échec" "work file not creatable"; }
sg_x_prs7()  { sg_fx_prs; SG_MK_FAIL=.semgrep-unparsed. SG_PATH="$SG_W/fauxmk:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs7() { sg_ok_prs_deg "(prs7) mktemp de UNPARSED en échec" "work file not creatable"; }
sg_x_prs8()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-liste.json" SG_PATH="$SG_NOPY:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs8() { sg_ok_prs_deg "(prs8) sans python, rapport liste" "not a JSON object"; }
sg_x_prs9()  { sg_fx_prsk; SG_PY_MODE=loc SG_PATH="$SG_W/fauxpy:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs9() {
  sg_rc "(prs9)" 1; sg_dit "(prs9)" "finding locations unreadable (parser exited 3)"
  sg_adit "(prs9)" '"locations":[]'
  printf '%s' "$SG_AUDIT" | "$PY" -c 'import json, sys; json.loads(sys.stdin.read())' >/dev/null 2>&1 \
    || fail "(prs9) ligne d'audit non JSON : $SG_AUDIT"
}
printf '%s\n' '{}' > "$SG_W/r-vide.json"
printf '%s\n' '{"results":{}}' > "$SG_W/r-resobj.json"
printf '%s\n' '{"errors":[],"paths":{"scanned":["a.py"]}}' > "$SG_W/r-sansres.json"
printf '%s\n' '{"results":[],"errors":[1],"paths":{"scanned":["a.py"]}}' > "$SG_W/r-err.json"
printf '%s\n' '{"results":[],"errors":[],"paths":[]}' > "$SG_W/r-paths.json"
printf '%s\n' '{"results":[],"errors":[],"paths":{"scanned":[1]}}' > "$SG_W/r-scan.json"
sg_x_prs10()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-vide.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs10() { sg_ok_prs_deg "(prs10) objet vide" "report malformed"; }
sg_x_prs11()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-resobj.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs11() { sg_ok_prs_deg "(prs11) results objet" "report malformed"; }
sg_x_prs12()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-sansres.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs12() { sg_ok_prs_deg "(prs12) errors et paths sans results" "report malformed"; }
sg_x_prs13()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-vide.json" SG_PATH="$SG_NOPY:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs13() { sg_ok_prs_deg "(prs13) sans python, objet vide" "no 'results' list (no Python to parse it)"; }
sg_x_prs14()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-err.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs14() { sg_ok_prs_deg "(prs14) errors non objets" "report malformed"; }
sg_x_prs15()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-paths.json" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs15() { sg_ok_prs_deg "(prs15) paths liste" "report malformed"; }
sg_x_prs16()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-scan.json" sg_run "$SG_S" "$SG_R"; }
printf '%s\n' '{"results":[' > "$SG_W/r-tronque.json"
sg_x_prs17()  { sg_fx_prs; SG_STUB_RAW="$SG_W/r-tronque.json" SG_PATH="$SG_NOPY:$SG_STUB" sg_run "$SG_S" "$SG_R"; }
sg_ok_prs17() { sg_ok_prs_deg "(prs17) sans python, rapport tronqué" "report truncated (no Python to parse it"; }
sg_ok_prs16() { sg_ok_prs_deg "(prs16) scanned non chaînes" "report malformed"; }
sg_forme_stop() {  # $1 label — stdout is ONE line, a JSON object whose key set is {systemMessage} (claude Stop)
  printf '%s' "$SG_OUT" | "$PY" -c 'import json, sys
l = [x for x in sys.stdin.read().splitlines() if x.strip()]
sys.exit(not (len(l) == 1 and set(json.loads(l[0])) == {"systemMessage"}))' >/dev/null 2>&1 \
    || fail "$1 : stdout n'est pas UNE ligne {systemMessage} — stdout : $SG_OUT"
}
sg_x_hrs1() {  # a CLEAN Stop fills stop-propre, then a changed file and a `{}` report
  sg_fx_prs; sg_hook "$SG_S" "$SG_R" hrs1a; SG_RC1=$SG_RC; SG_SP=0
  [ -f "$SG_R/.agents/state/local/semgrep-hook/stop-propre" ] && SG_SP=1
  sg_ecrire a.py 'x = 1\ny = 3\n'
  SG_STUB_RAW="$SG_W/r-vide.json" sg_hook "$SG_S" "$SG_R" hrs1b
}
sg_ok_hrs1() {
  [ "$SG_RC1" -eq 0 ] && [ "$SG_SP" = 1 ] || fail "(hrs1) précondition : le 1er Stop CLEAN doit remplir stop-propre (rc $SG_RC1)"
  sg_rc "(hrs1)" 0
  sg_dit "(hrs1)" '{"systemMessage": "COVERAGE DEGRADED: SAST hook '
  sg_dit "(hrs1)" 'semgrep report malformed'
  sg_err "(hrs1)" 'semgrep report malformed'
  sg_forme_stop "(hrs1)"
  sg_adit "(hrs1)" '"verdict":"DEGRADED"'
  [ -f "$SG_R/.agents/state/local/semgrep-hook/stop-propre" ] && fail "(hrs1) un rapport malformé doit EFFACER stop-propre, jamais le remplir"
  return 0
}
sg_x_hrs2()  { sg_fx_prs; SG_PY_MODE=hkb SG_PATH="$SG_W/fauxpy:$SG_STUB" sg_hook "$SG_S" "$SG_R" hrs2; }
sg_ok_hrs2() {
  sg_rc "(hrs2)" 0
  sg_dit "(hrs2)" '{"systemMessage": "COVERAGE DEGRADED: SAST hook '
  sg_dit "(hrs2)" 'the report phase died before any verdict'
  sg_err "(hrs2)" 'the report phase died before any verdict'
  sg_forme_stop "(hrs2)"
  sg_adit "(hrs2)" '"verdict":"DEGRADED"'
}
sg_bras "(prs1)" sg_x_prs1 sg_ok_prs1 MPFS
sg_bras "(prs2)" sg_x_prs2 sg_ok_prs2 MPFS
sg_bras "(prs10)" sg_x_prs10 sg_ok_prs10 MPFS
sg_bras "(prs11)" sg_x_prs11 sg_ok_prs11 MPFS
sg_bras "(prs12)" sg_x_prs12 sg_ok_prs12 MPFS
sg_bras "(prs13)" sg_x_prs13 sg_ok_prs13 MPRN
sg_bras "(prs14)" sg_x_prs14 sg_ok_prs14 MPFS MPFE
sg_bras "(prs15)" sg_x_prs15 sg_ok_prs15 MPFS MPFP
sg_bras "(prs16)" sg_x_prs16 sg_ok_prs16 MPFS MPFC
sg_bras "(prs17)" sg_x_prs17 sg_ok_prs17 MPTR
sg_bras "(hrs1)" sg_x_hrs1 sg_ok_hrs1 MHFS
sg_bras "(hrs2)" sg_x_hrs2 sg_ok_hrs2 MHBELT
sg_bras "(prs3)" sg_x_prs3 sg_ok_prs3 MPRC MPALL
sg_bras "(prs4)" sg_x_prs4 sg_ok_prs4 MPRC
sg_bras "(prs5)" sg_x_prs5 sg_ok_prs5 MPSH MPALL
sg_bras "(prs6)" sg_x_prs6 sg_ok_prs6 MPMK
sg_bras "(prs7)" sg_x_prs7 sg_ok_prs7 MPMK
sg_bras "(prs8)" sg_x_prs8 sg_ok_prs8 MPNP
sg_bras "(prs9)" sg_x_prs9 sg_ok_prs9 MLJ
ok "(prs) rapport liste, résultat non objet, objet vide, results objet, sans results, errors/paths/scanned mal typés (forme), chemin à surrogate, parseur rc 7, ligne parasite (puits réel), mktemp en échec (LOCFILE, UNPARSED), sans python rapport liste, objet vide ou tronqué : DEGRADED nommé par sa couche, rc 0, aucune phrase bénigne ; lieux illisibles : ligne d'audit JSON, locations [] ; hook Stop malformé ou PHASE B morte : UNE ligne {systemMessage} COVERAGE DEGRADED, stop-propre effacé ; MPFS MPFE MPFP MPFC MPRN MPTR MHFS MHBELT MPRC MPSH MPALL MPMK MPNP MLJ rougissent"

# ---- (prsp) THE THREE COPIES OF THE SHAPE TEST AGREE (plan-critic objection,
# S-01M531N0BT): the gate's `forme`, the hook's `forme_hk` (both in the script,
# extracted BY NAME and executed alone) and scan_verdict.py `_forme_semgrep`
# answer the SAME on one corpus — well-formed reports, and malformed values for
# every clause (not a dict, results, errors, paths, scanned). Each per-clause
# mutant of either copy (MPFE MPFP MPFC MHFE MHFP MHFC) breaks the parity, so
# the arm can redden. Bound, said: `skipped_rules` and `paths.skipped`, checked
# by `_forme_semgrep` alone, are NOT in the corpus (the copies do not read them).
SG_PARITE_PY='
import importlib.util, sys
src, sv = sys.argv[1], sys.argv[2]
t = open(src, encoding="utf-8").read()
def extrait(nom):
    i = t.index("\ndef %s(" % nom) + 1
    corps = []
    for l in t[i:].split("\n"):
        if corps and l.strip() and not l[0].isspace():
            break
        corps.append(l)
    ns = {}
    exec("\n".join(corps), ns)
    return ns[nom]
spec = importlib.util.spec_from_file_location("sg_parite_sv", sv)
mod = importlib.util.module_from_spec(spec)
sys.modules["sg_parite_sv"] = mod
spec.loader.exec_module(mod)
juges = (("forme", extrait("forme")), ("forme_hk", extrait("forme_hk")),
         ("_forme_semgrep", mod._forme_semgrep))
corpus = (
    ({"results": []}, True),
    ({"results": [], "errors": [], "paths": {"scanned": ["a.py"]}}, True),
    ({"results": [{"check_id": "r", "path": "a.py", "start": {"line": 1}}], "errors": None, "paths": None}, True),
    ({"results": [], "errors": [{"type": "x"}], "paths": {}}, True),
    ({"results": [], "paths": {"scanned": None}}, True),
    ([], False), ([1], False), (None, False), ("x", False), (1, False), ({}, False),
    ({"results": {}}, False), ({"results": ""}, False), ({"results": None}, False),
    ({"results": [1]}, False), ({"errors": [], "paths": {"scanned": ["a.py"]}}, False),
    ({"results": [], "errors": [1]}, False), ({"results": [], "errors": {}}, False),
    ({"results": [], "errors": "x"}, False),
    ({"results": [], "paths": []}, False), ({"results": [], "paths": "x"}, False),
    ({"results": [], "paths": {"scanned": [1]}}, False),
    ({"results": [], "paths": {"scanned": "a.py"}}, False),
)
ko = []
for v, attendu in corpus:
    for nom, f in juges:
        if f(v) != attendu:
            ko.append("%s(%r) != %r" % (nom, v, attendu))
if ko:
    print("; ".join(ko)); sys.exit(1)
print(len(corpus))
'
SG_OUT="$("$PY" -c "$SG_PARITE_PY" "$SCRIPT" "$HERE/scan_verdict.py" 2>&1)" \
  || fail "(prsp) les copies du test de forme divergent : $SG_OUT"
_sg_np="$SG_OUT"
for _m in MPFE MPFP MPFC MHFE MHFP MHFC; do
  "$PY" -c "$SG_PARITE_PY" "$SG_MUT/$_m.sh" "$HERE/scan_verdict.py" >/dev/null 2>&1 \
    && fail "(sgm) $_m : le mutant SURVIT à (prsp) — la parité ne pourrait pas rougir"
  SG_REDS="$SG_REDS$_m "
done
ok "(prsp) forme, forme_hk et _forme_semgrep d'accord sur $_sg_np rapports (bien formés et malformés par clause) ; MPFE MPFP MPFC MHFE MHFP MHFC rougissent"

# ---- (cfg1) THE AUDIT LINE STAYS JSON (T-01M4Z2DMFTXH6Q40RRA3ZW1PE0) ----------
# Measured at c2a42ba2 (fx/cfg): `x\"` wrote an INVALID line, `a\b` a valid line
# with a WRONG value, a newline cut the line in two. audit() is extracted ALONE
# (the form of arm (z)) and fed ten values, under SUITE_BASH AND the oldest bash.
cat > "$SG_W/cfg1.sh" <<'SGCFG'
# cfg1.sh <script> <out dir> — audit() alone, one line per value. The extracted
# function is WRITTEN to a temporary file under the out dir, then SOURCED: a
# value is never re-parsed by eval (AGENTS.md § Conventions).
set -u
_fn="$(mktemp "$2/audit.XXXXXX")" || exit 1
sed -n '/^audit()/,/^}/p' "$1" > "$_fn"
. "$_fn"
TS=t; COUVERTURE=CLEAN; FILES=(); PROPOSED=(); OUT="$2"
for v in 'x\"' 'a\b' "$(printf 'l1\nl2')" "$(printf 't\tb')" "$(printf 'c\rr')" 'abc\' "$(printf 's\001h')" "$(printf 'd\177l')" 'x","verdict":"CLEAN' "$(printf '\303\251.yml')"; do
  CFG="$v"
  audit FINDINGS 1 "[]"
done
SGCFG
SG_CFGPY='
import json, sys
exp = ["x\\\"", "a\\b", "l1\nl2", "t\tb", "c\rr", "abc\\", "sh", "dl", "x\",\"verdict\":\"CLEAN", "é.yml"]
L = [l for l in open(sys.argv[1] + "/audit-log.jsonl", encoding="utf-8").read().split("\n") if l]
if len(L) != len(exp):
    print("%d ligne(s) pour %d run(s)" % (len(L), len(exp)))
    sys.exit(1)
for l, e in zip(L, exp):
    d = json.loads(l)
    if d.get("config") != e or d.get("verdict") != "FINDINGS":
        print("config %r attendu %r, verdict %r" % (d.get("config"), e, d.get("verdict")))
        sys.exit(1)
'
sg_x_cfg1()  { SG_CFG_O="$(mktemp -d "$SG_W/c.XXXXXX")"; "$SG_CFG_BASH" "$SG_W/cfg1.sh" "$SG_S" "$SG_CFG_O" >/dev/null 2>&1; }
sg_ok_cfg1() { SG_OUT="$("$PY" -c "$SG_CFGPY" "$SG_CFG_O" 2>&1)" || fail "(cfg1/$SG_CFG_BASH) ligne d'audit fausse : $SG_OUT"; }
SG_CFG_BASH="$SUITE_BASH"; sg_bras "(cfg1)" sg_x_cfg1 sg_ok_cfg1 MA1
if [ -n "$OLDEST" ] && [ "$OLDEST_MAJ" -lt 4 ]; then
  SG_CFG_BASH="$OLDEST"; sg_bras "(cfg1/oldest)" sg_x_cfg1 sg_ok_cfg1 MA1 MA2
  ok "(cfg1) dix valeurs de SEMGREP_CONFIG (x\\\", a\\b, LF, TAB, CR, abc\\, SOH, DEL, forgée, UTF-8) : une ligne JSON chacune, valeur exacte, verdict du run — sous $SUITE_BASH et bash $OLDEST_MAJ ; MA1, MA2 (sous bash $OLDEST_MAJ) rougissent"
else
  sg_saute "MA2" "aucun bash < 4 ici — MA2 (remplacement entre guillemets) n'est faux que sous bash 3.2 (ligne C4)"
  ok "(cfg1) dix valeurs de SEMGREP_CONFIG : une ligne JSON chacune, valeur exacte — sous $SUITE_BASH ; MA1 rougit"
fi
echo "  SKIP (cfg1) valeur de config NON UTF-8 : la ligne d'audit devient illisible (comptée malformée) — borne écrite au README (ligne C7)"

# ---- (brut) PINS: every git call that reads a repository carries "${GN[@]}" ---
SG_BRUTPY='
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
q = chr(39)
for bloc in ("LIRE_INDEX_PY", "RECRIRE_PY"):
    m = re.search(r"\n" + bloc + "=" + q + r".*?\n" + q + r"\n", t, re.S)
    if not m:
        print("bloc " + bloc + " introuvable : le relevé ne sait plus quoi écarter")
        sys.exit(1)
    t = t[:m.start()] + "\n" + t[m.end():]
appel = re.compile(r"(?:^|[;&|(]\s*|\b(?:then|do|if|elif|while|until)\s+(?:!\s*)?|!\s+|\$\(\s*|<\(\s*|xargs -0\s+)git\s")
sousc = re.compile(r"\$\(\s*git\s")
vus = 0
for n, l in enumerate(t.splitlines(), 1):
    s = l.strip()
    if s.startswith("#"):
        continue
    # A MESSAGE line (a loss or a DEGRADED line quoting `(git ls-files …)`) is
    # not a call — the reading of gitleaks (trr15) — except a `$(git …)` it embeds.
    if s.startswith(("echo ", "perte_perimetre ")):
        if not sousc.search(s):
            continue
    elif not appel.search(s):
        continue
    if "rev-parse --show-toplevel" in s:
        continue
    vus += 1
    if "\"${GN[@]}\"" not in s:
        print("git de lecture sans GN : " + s)
        sys.exit(1)
if vus < int(sys.argv[2]):
    print("%d appel(s) vus seulement : le relevé ne voit plus les appels" % vus)
    sys.exit(1)
if t.count("export GIT_NO_LAZY_FETCH=1") != 1:
    print("export GIT_NO_LAZY_FETCH=1 vu %d fois" % t.count("export GIT_NO_LAZY_FETCH=1"))
    sys.exit(1)
print(vus)
'
# 41 = the count measured on the script once this task's channels were cut.
SG_OUT="$("$PY" -c "$SG_BRUTPY" "$SCRIPT" 41 2>&1)" || fail "(brut) $SG_OUT"
"$PY" -c "$SG_BRUTPY" "$SG_MUT/MC3b.sh" 0 >/dev/null 2>&1 && fail "(brut) l'épingle ne mord pas : MC3b (un git sans \"\${GN[@]}\") passe"
"$PY" -c "$SG_BRUTPY" "$SG_MUT/MX.sh" 0 >/dev/null 2>&1 && fail "(brut) l'épingle ne mord pas : MX (export ôté) passe"
ok "(brut) $SG_OUT appels git de lecture, tous par \"\${GN[@]}\" (hors --show-toplevel, programmes python écartés) ; export GIT_NO_LAZY_FETCH=1 exactement une fois ; l'épingle refuse MC3b et MX"

# Every mutant of the table reddened at least one arm, or carries a SAID skip.
for _m in $SG_MUTS; do
  case "$SG_REDS$SG_SKIPPED" in
    *" $_m "*)
      : ;;
    *)
      fail "(sgm) le mutant $_m de la table n'a rougi AUCUN bras et ne porte aucun saut dit" ;;
  esac
done
_sg_sk="${SG_SKIPPED# }"; _sg_sk="${_sg_sk% }"
ok "(sgm) chaque mutant de la table a rougi au moins un bras (sauts dits : ${_sg_sk:-aucun})"
rm -rf "$SG_W"

# The cwd arms wrote into the throwaway repo, never into the caller's tree.
cd / && rm -rf "$SUITE_CWD"

echo "PASS: semgrep-scan-git ($pass check(s); semgrep present=$HAVE_SEMGREP)"
