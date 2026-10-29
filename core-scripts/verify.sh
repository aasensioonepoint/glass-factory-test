#!/usr/bin/env bash
# Run CI's scope before pushing (CI's bare form under CADRE_GATE_JOBS=1).
#
# WHY THIS EXISTS. CI (.github/workflows/ci.yml) runs two commands:
#   bash core-scripts/run-pytest-shards.sh   # pytest's BARE collection (pytest.ini decides the scope); CI pins CADRE_GATE_JOBS=1 = `python -m pytest -q`
#   bash core-scripts/run-bash-tests.sh
# A developer who instead runs `pytest .agents/bin/ .agents/evals/ ...` is
# choosing a DIFFERENT scope than the gate, and the difference is invisible
# until the push goes red. That happened: three pushes in a row failed CI while
# the selected-directory run was green locally.
#
# NO UI GATE — WITHDRAWN BY PILOT DECISION (T-00000505). The interface gate
# (Playwright + axe) never had a step of its own here: it reached this script by
# DISCOVERY — `scripts/ui-gate.test.sh` exercised `scripts/ui-gate.sh`, and
# `core-scripts/run-bash-tests.sh` picked the suite up through its `*.test.sh` glob, so
# the gate rode in on the run-bash-tests.sh leg below. BOTH FILES ARE DELETED, so
# it is gone from this script AND from CI in the same gesture. That is the point
# of the decision: NO verification gate, here or in CI, depends any more on a
# browser, on the npm registry, or on node/npm being on PATH.
#
# THE TOOL STAYS, ONLY THE GATE GOES. `.agents/ui-src/` is still on disk and is
# still the end-to-end coverage/accessibility project delivered by T-00000193.
# Play it BY HAND when you want it, from that directory — `npx playwright test
# e2e/coverage.spec.ts`, npm installing its dependencies at use. Name the spec
# rather than running bare: playwright.config.ts uses testMatch "**/*.spec.ts",
# which would rake in an untracked probe.spec.ts and make the verdict
# unattributable (T-00000203). Nothing below calls it, and nothing here goes red
# if it fails.
#
# One structural fact the withdrawn paragraph carried, KEPT because it is still
# true and still catches people out: under `--at --linux` the frozen clone is
# cleaned ONCE, AT ENTRY (see the checkout step below) — never between the legs,
# which SHARE it.
#
# `--linux` additionally replays both commands inside the same OS family as the
# runner (ubuntu, via docker). Use it whenever the change touches process
# spawning, file locking, path handling or anything else where Windows and POSIX
# genuinely differ — those are the failures a Windows-only run cannot see, and
# the ones this repo produces most (see the WINDOWS_ONLY markers in
# .agents/evals/test_gate_b_launch_probe.py).
#
# `--at <ref>` (typically `--at HEAD`) runs the whole thing on a FROZEN CLONE —
# a sibling local clone detached on that ref — instead of the live tree. Two
# reasons, and the second is the one that matters:
#   - the live tree stays entirely free during the run (the --linux leg mounts
#     the tree read-write for minutes; any save during that window corrupts the
#     measurement, and the container leaves caches behind);
#   - the verdict is ANCHORED TO A SHA. Hence the push rule: you only push a SHA
#     that came back green. Commits landed since? Push the green ancestor, or
#     re-verify the new head. A verdict for "some tree, at some point" is not a
#     verdict.
#
# A CLONE, not a `git worktree`, and that is a measured constraint rather than a
# preference: a linked worktree's `.git` is a POINTER FILE holding an absolute
# HOST path (`gitdir: C:/Users/.../.git/worktrees/<name>`), which means nothing
# once the directory is bind-mounted into the --linux container. Measured, on
# the very first dogfood run of this feature:
#   fatal: not a git repository: /repo/C:/Users/.../.git/worktrees/...-verify
# → FAIL linux replay, for a repo that was perfectly fine. A local clone has a
# real `.git` DIRECTORY and is a self-contained repository, so it mounts as-is;
# `git clone` of a local path hardlinks its objects, so the copy is cheap.
#
# The SHA anchoring is why every git mutation below is error-checked and why the
# clone's identity is proven BEFORE anything destructive touches it: this script
# must never be able to print a verdict for a tree that is not the SHA it names.
# One `--at` run at a time, enforced by a `$WT.lock` DIRECTORY that CARRIES ITS
# HOLDER (`$WT.lock/owner`: pid, take-time) — so a refusal names who holds it and
# since when, and a lock whose pid is dead is reclaimed automatically instead of
# costing a manual `rmdir`. Released by an EXIT trap only — never `exec` the
# inner run (an exec skips the trap and leaks the lock). bash runs that trap on
# an UNTRAPPED SIGTERM or SIGHUP too (measured, bash 5.3.15 and 3.2.57), which
# freed the lock while the inner run the wrapper did not kill was still
# verifying. So TERM and HUP are TRAPPED once the lock is held: bash defers them
# until the running child returns, then exits 143/129 and releases. A kill that
# reaches only the wrapper therefore no longer frees the lock under a verifying
# child, and a second TERM/HUP arriving during the EXIT trap is ignored there.
# Not covered: SIGKILL, or a kill before the trap is set, skips the release —
# the lock leaks, and is reclaimed as stale once its pid is dead.
# The clone is kept between runs, on purpose: reuse is cheap (a fetch and a
# checkout) and a red run stays inspectable.
#
# THE ADOPTING PROJECT'S MODE (T-00001183, pilot decision S-00004119: « c'est le
# build du projet et sous modules qui doivent faire foi »). This file travels.
# In a project that adopted the kit, the kit's own suite is not the verdict:
# the project's build and tests are. One rule, the same in `.githooks/pre-push`
# and in ci.yml's `porte` job: ADOPTANT iff `.agents/IS_THE_KIT` is absent AND
# `.agents/security/module_discovery.py` is present (never the pyproject's
# name). In that mode the three kit steps give way to ONE step,
# `.agents/bin/porte_adoptant.py`, whose verdict comes back through
# `.agents/state/local/PORTE_RESULT`; the stamp then carries `porte=adoptant`,
# the traced `derogation_*`, and `linux=0` (the container leg replays the KIT's
# suite: it has no object here). Under `--at`, the frozen clone's submodules are
# populated FROM THE LIVE TREE, at the gitlink's sha, never from the network —
# `peupler_sous_modules` below.
#
# `--rouges` (T-01M5QBFKM444FB53RM2J1NBB4X, pilot decision S-01M5QBG09B3R1NDJPZATE7NCDT) — after a RED gate,
# replay ONLY the reds it noted (`.agents/state/local/PORTE_ROUGES`), each through its own runner: never a
# verdict, never a stamp, never a chrono row. The full gate stays the only one that lets a push through.
#
# Exit code: 0 iff every command passed.
set -uo pipefail

# PURGE AT ENTRY, EVERY MODE (full gate, `--at` inner and outer, `--rouges`, adoptant gate) — a CLOSED list:
# each of the first five was MEASURED crediting a PASS without playing (BASH_TEST_TIMEOUT_BIN=true,
# a BASH_ENV that exits 0 in every *.test.sh, PYTEST_ADDOPTS=--co under CADRE_GATE_JOBS=1 or `-p <plugin>`,
# PYTEST_PLUGINS=<plugin>, a CADRE_GATE_TIMEOUT_BIN that prints a fake summary); the last two are this
# script's own channels, never inherited. Each one found set is SAID (stderr), never dropped in silence.
# BOUND, an OPEN list: PATH, PYTHONPATH, ENV, exported functions (`BASH_FUNC_*`, and a BASH_ENV — which bash
# sources BEFORE this line — that redefines `unset`: measured, the whole purge cancelled) and the tree's own
# conftest or plugins are NOT purged and NOT covered.
[ -z "${BASH_ENV+x}" ] || echo "verify.sh: réglage purgé à l'entrée : BASH_ENV" >&2
[ -z "${BASH_TEST_TIMEOUT_BIN+x}" ] || echo "verify.sh: réglage purgé à l'entrée : BASH_TEST_TIMEOUT_BIN" >&2
[ -z "${CADRE_GATE_TIMEOUT_BIN+x}" ] || echo "verify.sh: réglage purgé à l'entrée : CADRE_GATE_TIMEOUT_BIN" >&2
[ -z "${PYTEST_ADDOPTS+x}" ] || echo "verify.sh: réglage purgé à l'entrée : PYTEST_ADDOPTS" >&2
[ -z "${PYTEST_PLUGINS+x}" ] || echo "verify.sh: réglage purgé à l'entrée : PYTEST_PLUGINS" >&2
[ -z "${CADRE_GATE_ROUGES_OUT+x}" ] || echo "verify.sh: réglage purgé à l'entrée : CADRE_GATE_ROUGES_OUT" >&2
[ -z "${ROUGES_SEUL+x}" ] || echo "verify.sh: réglage purgé à l'entrée : ROUGES_SEUL" >&2
unset BASH_ENV BASH_TEST_TIMEOUT_BIN CADRE_GATE_TIMEOUT_BIN PYTEST_ADDOPTS PYTEST_PLUGINS CADRE_GATE_ROUGES_OUT ROUGES_SEUL
ROUGES_SEUL=0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

LINUX=0
AT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --linux) LINUX=1; shift ;;
    --rouges) ROUGES_SEUL=1; shift ;;
    --at)
      shift
      [ "$#" -gt 0 ] || { echo "--at requires a <ref> argument" >&2; exit 2; }
      AT="$1"; shift ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: verify.sh [--linux] [--at <ref>]  |  verify.sh --rouges" >&2
      exit 2 ;;
  esac
done
if [ "$ROUGES_SEUL" = "1" ]; then
  if [ -n "$AT" ] || [ "$LINUX" -eq 1 ]; then
    echo "--rouges est seul : ni --at, ni --linux — le rejeu joue l'arbre vivant et ne vaut jamais un verdict" >&2
    exit 2
  fi
  if [ "${VERIFY_INNER:-0}" = "1" ]; then
    echo "--rouges: refusé sous VERIFY_INNER=1 — le rejeu n'est jamais délégué à un clone figé" >&2
    exit 2
  fi
fi

# PORTE_ROUGES — the reds of the last RED full gate, the ONLY input of `--rouges` (format: verification-
# discipline SKILL § `--rouges`). Erased at the ENTRY of every full gate — the live one HERE, right after
# the arguments; `--at` once its lock is held — so a gate killed before its verdict leaves no stale list
# behind; written at a RED verdict only. ROUGES_LISTE is the accumulator, fed by `noter_rouge` for EVERY
# red (ETAPE_ROUGE keeps the first only, untouched); ROUGES_TMP holds the per-step runner files
# (`CADRE_GATE_ROUGES_OUT`), removed by `verify_on_exit`.
PORTE_ROUGES="$ROOT/.agents/state/local/PORTE_ROUGES"
ROUGES_LISTE=""
ROUGES_TMP=""
ROUGES_N=0
_rouges_nl='
'
_rouges_tab="$(printf '\t')"
_rouges_inconnue='?'
if [ "$ROUGES_SEUL" = "0" ] && [ -z "$AT" ]; then
  rm -f "$PORTE_ROUGES"
fi
rouges_tmp_dir() {  # creates ROUGES_TMP once; never called from a command substitution (it sets a global)
  [ -z "$ROUGES_TMP" ] || return 0
  ROUGES_TMP="$(mktemp -d 2>/dev/null)" || ROUGES_TMP=""
  return 0
}
# rouges_accumuler <label> [<runner file>] — one `<kind>TAB<entry>` line per red unit the runner wrote
# (pytest / bash, by a CLOSED table of the two runner labels); a red with no runner line is `etape<TAB><label>`.
rouges_accumuler() {
  local genre="" ligne n=0
  case "$1" in
    "python -m pytest (CI scope, shards)") genre=pytest ;;
    "bash core-scripts/run-bash-tests.sh") genre=bash ;;
  esac
  if [ -n "$genre" ] && [ -n "${2:-}" ] && [ -f "$2" ] && [ ! -L "$2" ]; then
    while IFS= read -r ligne || [ -n "$ligne" ]; do
      [ -n "$ligne" ] || continue
      ROUGES_LISTE="$ROUGES_LISTE$genre$_rouges_tab$ligne$_rouges_nl"
      n=$((n + 1))
    done < "$2"
  fi
  if [ "$n" -eq 0 ]; then
    ROUGES_LISTE="${ROUGES_LISTE}etape$_rouges_tab$1$_rouges_nl"
  fi
  return 0
}
rouges_ecrire() {  # rouges_ecrire <sha> <live|frozen|frozen-linux> — tmp + mv; a failed write only costs the replay
  local dir tmp liste="$ROUGES_LISTE"
  [ -n "$liste" ] || liste="etape$_rouges_tab$_rouges_inconnue$_rouges_nl"
  dir="$(dirname "$PORTE_ROUGES")"
  mkdir -p "$dir" 2>/dev/null || return 0
  tmp="$PORTE_ROUGES.tmp.$$"
  { printf '# porte-rouges v1\nsha=%s\nmode=%s\nat=%s\n' "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    printf '%s' "$liste"
  } > "$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
  mv -f "$tmp" "$PORTE_ROUGES" 2>/dev/null || rm -f "$tmp"
  return 0
}
# rouges_relire <file> <40-hex sha> — the entry lines of the list the `--at` inner run wrote in ITS clone, or
# NOTHING when it is absent, a symlink, over 64 KiB or for another sha (the caller then notes `etape ?`).
# A TRUST BOUNDARY like ETAPE_ROUGE: written by the code of the frozen SHA, read as data, never sourced.
rouges_relire() {
  local f="$1" sha="$2" taille ligne genre r_sha="" corps=""
  [ -f "$f" ] && [ ! -L "$f" ] || return 0
  taille="$(wc -c < "$f" 2>/dev/null | tr -d ' ')" || return 0
  case "$taille" in
    ''|*[!0-9]*) return 0 ;;
  esac
  [ "$taille" -le 65536 ] || return 0
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in
      sha=*) r_sha="${ligne#sha=}" ;;
    esac
    genre="${ligne%%$_rouges_tab*}"
    [ "$genre" != "$ligne" ] || continue
    case "$genre" in
      pytest|bash|etape) corps="$corps$ligne$_rouges_nl" ;;
    esac
  done < "$f"
  [ "$r_sha" = "$sha" ] || return 0
  printf '%s' "$corps"
}

# One observation once the outer gate has taken the --at lock or begun a live
# step. The delegated frozen clone is marked VERIFY_INNER=1 and adds no row.
# CHRONO_ROOT is the SAME rule as the reader, agent_chrono.racine_commune:
# git-dir = common-dir -> --show-toplevel; else (linked worktree) the common
# dir's core.worktree (a submodule's), else the parent of a common dir named
# .git, else its own toplevel (git records no main worktree for a
# --separate-git-dir or bare repository). verify.test.sh arm 11a plays both.
CHRONO_OWNER="${BASHPID:-$$}"
CHRONO_START="$(date +%s 2>/dev/null)" || CHRONO_START=""
CHRONO_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || CHRONO_ISO=""
CHRONO_COMMON="$(git rev-parse --git-common-dir 2>/dev/null)" || CHRONO_COMMON=""
CHRONO_GIT_DIR="$(git rev-parse --absolute-git-dir 2>/dev/null)" || CHRONO_GIT_DIR=""
CHRONO_ROOT=""
if [ -n "$CHRONO_COMMON" ]; then
  CHRONO_COMMON="$(cd "$CHRONO_COMMON" && pwd)" || CHRONO_COMMON=""
  if [ -n "$CHRONO_COMMON" ]; then
    CHRONO_TREE=""
    if [ "$CHRONO_GIT_DIR" != "$CHRONO_COMMON" ]; then
      CHRONO_TREE="$(git config --file "$CHRONO_COMMON/config" --get core.worktree 2>/dev/null)" || CHRONO_TREE=""
    fi
    if [ "$CHRONO_GIT_DIR" = "$CHRONO_COMMON" ]; then
      CHRONO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || CHRONO_ROOT=""
    elif [ -n "$CHRONO_TREE" ]; then
      CHRONO_ROOT="$(cd "$CHRONO_COMMON" && cd "$CHRONO_TREE" && pwd)" || CHRONO_ROOT=""
    elif [ "${CHRONO_COMMON##*/}" = ".git" ]; then
      CHRONO_ROOT="$(cd "$CHRONO_COMMON/.." && pwd)" || CHRONO_ROOT=""
    else
      CHRONO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || CHRONO_ROOT=""
    fi
  fi
fi
CHRONO_LOCK=0
CHRONO_ACTIVE=0
# CHRONO_INFLIGHT=1 while a step (or the delegated `--at` run and its preparation)
# has not returned. In live mode bash runs the EXIT trap on SIGTERM with `$?` =
# the last COMPLETED command, not 143 (measured, bash 5.3); on the --at path TERM
# and HUP are trapped and `$?` is 143/129. Either way a killed gate would record a
# truncated row: a gate killed in flight records NOTHING.
CHRONO_INFLIGHT=0
chrono_write() {  # chrono_write <gate rc>; observation never changes the verdict
  [ "${VERIFY_INNER:-0}" = "1" ] && return 0
  [ "$CHRONO_ACTIVE" = "1" ] || return 0
  [ "$CHRONO_INFLIGHT" = "1" ] && return 0  # killed mid-step: no row, never a false green
  [ -n "$CHRONO_ROOT" ] && [ -n "$CHRONO_START" ] && [ -n "$CHRONO_ISO" ] || return 0
  local end elapsed sha mode path
  end="$(date +%s 2>/dev/null)" || return 0
  elapsed=$((end - CHRONO_START))
  [ "$elapsed" -ge 0 ] || return 0
  sha=""
  if [ -n "$AT" ]; then
    sha="${SHA:-}"
  else
    sha="$(git rev-parse HEAD 2>/dev/null)" || sha=""
  fi
  mode=live
  if [ -n "$AT" ]; then
    mode=frozen
    [ "$LINUX" -eq 0 ] || mode=frozen-linux
  fi
  path="$CHRONO_ROOT/.agents/state/local/porte-chrono.tsv"
  mkdir -p "$(dirname "$path")" 2>/dev/null || return 0
  [ ! -L "$path" ] || return 0  # a symlinked journal is never followed
  # 6th column: `-` on a green gate; on a red one the first red label, or `?`
  # when none was noted (a FATAL exit before the verdict, a stub inner) or when
  # it carries a control character — a tab or a line end would split the row.
  # `?` goes through a variable, the `_inconnu` pattern of the --at branch.
  local etape _etape_inconnue _etape_nette
  _etape_inconnue='?'
  etape=-
  if [ "$1" != "0" ]; then
    etape="$ETAPE_ROUGE"
    _etape_nette="$(printf '%s' "$etape" | LC_ALL=C tr -d '[:cntrl:]')" || _etape_nette=""
    if [ -z "$etape" ] || [ "$_etape_nette" != "$etape" ]; then
      etape="$_etape_inconnue"
    fi
  fi
  (printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$CHRONO_ISO" "$elapsed" "$sha" "$mode" "$1" "$etape" >> "$path") 2>/dev/null || true
  return 0
}
verify_on_exit() {
  local gate_rc="$1"
  [ "${BASHPID:-$$}" = "$CHRONO_OWNER" ] || return 0
  # A SECOND TERM or HUP must not cut this body short: under the --at traps its
  # `exit 143`/`exit 129` would end the run between `rm` and `rmdir`, leaking the
  # lock (the form of .agents/security/sca-scan.sh cleanup(), measured there).
  # Ignored from here on; the run is exiting anyway. KILL still cuts it.
  trap '' TERM HUP
  # The BACKGROUND LEG of the parallel mode (`jambes_jouer`, T-01M60XKFK7MPKZWNHH326ZMW3M), still alive when
  # this run exits (a TERM, a FATAL `exit`): TERM then reaped HERE, before the lock is released, so no later
  # gate takes the lock while a leg of this one still plays. Only a pid this run set and has not reaped yet.
  if [ -n "${JAMBE_PID:-}" ]; then
    kill -TERM "$JAMBE_PID" 2>/dev/null
    wait "$JAMBE_PID" 2>/dev/null
    JAMBE_PID=""
  fi
  chrono_write "$gate_rc"
  # An interrupted parallel run leaves the bash leg's log unread: its partial output goes to stderr
  # before the directory is removed, so a cut run never hides what the leg had printed.
  if [ -n "$ROUGES_TMP" ] && [ -s "$ROUGES_TMP/jambe-bash.log" ]; then
    echo "=== bash core-scripts/run-bash-tests.sh (interrompue — sortie partielle)" >&2
    cat "$ROUGES_TMP/jambe-bash.log" >&2 2>/dev/null
  fi
  if [ -n "$ROUGES_TMP" ]; then rm -rf "$ROUGES_TMP" 2>/dev/null; fi
  if [ "$CHRONO_LOCK" = "1" ]; then lock_release; fi
  return 0
}
# JAMBE_PID — the pid of the background leg while it plays, EMPTY otherwise; set BEFORE the EXIT trap, so
# that under `set -u` an exit before the legs (rc 2, FATAL) can never make verify_on_exit die on an unbound
# name and skip lock_release (measured, T-01M60XKFK7MPKZWNHH326ZMW3M C14). Never inherited.
JAMBE_PID=""
trap 'verify_on_exit "$?"' EXIT

# ------------------------------------------------------------------ fail-fast
# CADRE_GATE_FAIL_FAST (T-01M4WTYT8M, décision pilote S-01M4WTZ1QZQJZZNYRC5YA67AZW)
# — the SAME setting the two runners already honour (prio|all|0), read here at the
# scale of verify.sh's own steps: once a step is red, the following steps and the
# --linux leg are NOT RUN, and said so (`--- NOT RUN <label>`, then a count line
# before the verdict). At this scale `prio` and `all` are the same thing (« ≠ 0 »);
# `0` plays everything. The VERDICT never changes: a red is a red, and a red clears
# the stamp exactly as before — only the time spent after the first red changes.
# Validated HERE, before the lock and the clone: a bad value is rc 2 and no step
# runs. The CI never calls this script (it runs the three commands bare), so CI
# behaviour is untouched.
FF="${CADRE_GATE_FAIL_FAST:-prio}"
case "$FF" in
  prio|all|0)
    : ;;
  *)
    echo "CADRE_GATE_FAIL_FAST='$FF' is invalid — expected prio, all or 0 (0 plays every step)" >&2
    exit 2 ;;
esac

# ---------------------------------------------------------------- the legs
# CADRE_GATE_JAMBES (T-01M60XKFK7MPKZWNHH326ZMW3M) — `auto` (default), `serie` or `parallele`: whether the
# kit's two runner steps (pytest, the bash suites) play ONE AFTER THE OTHER, as they always did, or
# TOGETHER — bash in the background, pytest in the foreground (`jambes_jouer`). `auto` is parallel only on
# the kit's gate, with CADRE_GATE_JOBS empty or `auto` (an explicit value, the CI's `1` included, keeps the
# series), outside MINGW/MSYS/CYGWIN, on 16 cores or more; anywhere else the series, BYTE FOR BYTE (no new
# line). Validated HERE, like CADRE_GATE_FAIL_FAST, before the lock and the clone: a bad value is rc 2 and
# no step runs. Read, then UNSET: no suite inherits it (a bench that plays this script would otherwise get
# the parent's mode); the `--at` delegation hands the value READ to the inner run as a command prefix.
JAMBES="${CADRE_GATE_JAMBES:-auto}"
case "$JAMBES" in
  auto|serie|parallele)
    : ;;
  *)
    echo "CADRE_GATE_JAMBES='$JAMBES' is invalid — expected auto, serie or parallele" >&2
    exit 2 ;;
esac
unset CADRE_GATE_JAMBES
# JAMBES_MODE — the mode this run PLAYS (`serie` until `jambes_decider` says otherwise, on the kit's path);
# JAMBE_PY / JAMBE_SH — the argv of the two deferred legs; JAMBES_JOBS_BASH — the bash leg's job count,
# set under `auto` only. None is inherited.
JAMBES_MODE=serie
JAMBES_COEURS=""
JAMBES_JOBS_BASH=""
JAMBE_PY=()
JAMBE_SH=()

# ----------------------------------------------------------- persisted verdict
# WHY A FILE AND NOT ONLY A PRINTED LINE. `VERIFY OK @ <sha>` went to stdout and
# nowhere else: the return channel was DISCARDED, so the push rule ("only a SHA
# whose verdict came back green may be pushed") stayed a habit nobody could
# mechanise — a mechanism whose return channel is discarded does not exist
# (L-00000136). The stamp below is that channel, and `.githooks/pre-push` is its
# reader.
#
# WHAT IT IS, WITH THE RIGHT WORD: a REMINDER, never a gate. The stamp is local,
# git-ignored (`/.agents/state/local/`) and UNAUTHENTICATED — five lines of
# `printf` fabricate it, and `git push --no-verify` skips the reader entirely. It
# ATTESTS a discipline; it PROVES nothing. "Gate" is reserved for the forge-side
# ruleset (`.github/rulesets/`), which only the pilot can activate.
STAMP="$ROOT/.agents/state/local/VERIFY_STAMP"

# VERIFY_INNER marks the delegated run INSIDE the frozen clone. That run's $ROOT
# is the clone, which `git clean -fdx` wipes at the next run — so a stamp it wrote
# would never be read, and an installation status line it printed would always say
# "NOT installed", about $WT, immediately before the outer's answer about $ROOT.
# Two contradictory status lines in one log are worse than none.
VERIFY_INNER="${VERIFY_INNER:-0}"

# PORTE_LIGNES — the adoptant lines of the stamp (`porte=adoptant`, then each
# traced `derogation_*` and the gate's `avertissement`, if any), filled by
# `porte_lire` from a GREEN `PORTE_RESULT` and
# appended by `stamp_write`. EMPTY on the kit, so the kit's stamp keeps its five
# lines byte for byte. Initialised here, never inherited from the environment.
PORTE_LIGNES=""

# ETAPE_ROUGE — the label of the FIRST red step of this run (`noter_rouge`),
# written as the 6th column of the gate journal by `chrono_write` (T-01M5PVWF7H).
# OBSERVATION ONLY: no verdict reads it. Initialised here, never inherited — a
# value from the environment would name a step this run never failed. Under
# `--at` the inner run hands it back through a FILE of the clone
# (`$WT/.agents/state/local/ETAPE_ROUGE`, wiped by the `clean -fdx` of every
# run), never through a new environment variable.
ETAPE_ROUGE=""
noter_rouge() {  # noter_rouge <label> [<runner file>] — the first red label is kept, later ones are not
  # EVERY red feeds the separate accumulator of PORTE_ROUGES (T-01M5QBFKM444FB53RM2J1NBB4X), before the
  # early return below: ETAPE_ROUGE itself is unchanged.
  rouges_accumuler "$1" "${2:-}"
  [ -z "$ETAPE_ROUGE" ] || return 0
  ETAPE_ROUGE="$1"
  # INNER ONLY: hand the first red label to the outer `--at` run through a file
  # of the clone, written HERE, at the moment it is noted — so a later FATAL
  # `exit 1` (the linux replay's extraction guards) cannot skip it. The outer
  # reads it after the inner returns. Observation: a failed write changes
  # nothing, a symlink there is never followed.
  if [ "$VERIFY_INNER" = "1" ]; then
    _etape_fichier="$ROOT/.agents/state/local/ETAPE_ROUGE"
    if mkdir -p "$(dirname "$_etape_fichier")" 2>/dev/null && [ ! -L "$_etape_fichier" ]; then
      (printf '%s' "$ETAPE_ROUGE" > "$_etape_fichier") 2>/dev/null || true
    fi
  fi
  return 0
}

stamp_write() {  # stamp_write <40-hex sha> <frozen|live> <0|1>
  [ "$VERIFY_INNER" = "1" ] && return 0
  local dir tmp
  dir="$(dirname "$STAMP")"
  mkdir -p "$dir" || return 0
  tmp="$STAMP.tmp.$$"
  { echo "sha=$1"
    echo "mode=$2"
    echo "linux=$3"
    echo "host=$(uname -s 2>/dev/null || echo unknown)"
    echo "at=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    [ -z "$PORTE_LIGNES" ] || printf '%s' "$PORTE_LIGNES"
  } > "$tmp" || { rm -f "$tmp"; return 0; }
  # tmp + `mv -f`, never a truncating rewrite in place: the reader is a hook that
  # may fire at any moment, and a half-written stamp is a MALFORMED stamp, which
  # the hook fail-closes on. `mv` and not `os.replace` semantics debates — this is
  # the same filesystem, same directory.
  mv -f "$tmp" "$STAMP" || { rm -f "$tmp"; return 0; }
  # HISTORIQUE APPEND-ONLY DES VERDICTS VERTS (T-00000592). Le tampon seul ne
  # dit QUE le dernier cycle ; il ne permet donc pas de savoir si une revue
  # appartient au cycle courant ou à un cycle passé. Sans cette borne, la preuve
  # empruntée du binôme ne se périme JAMAIS : dès qu'un chantier a son premier
  # binôme tracé, toute sous-tâche se ferme sans revue neuve.
  #
  # POURQUOI PAS « trace.sha == stamp.sha », qui semblait l'évidence : le binôme
  # passe AVANT la porte, donc la trace naît toujours avec le sha PRÉCÉDENT.
  # Cette règle-là aurait refusé le cas NOMINAL, mesuré à la clôture de
  # T-00000591 — trace @ e5beb66 pendant que le tampon portait 97ab48d.
  # Ce qu'on veut est « la revue est tombée dans le cycle courant », et deux
  # bornes le disent : le tampon PRÉCÉDENT et le tampon COURANT.
  #
  # Toujours `return 0` : un historique qui échoue ne doit jamais faire rougir
  # une porte verte.
  printf 'at=%s\tsha=%s\tmode=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" "$1" "$2" \
    >> "$STAMP.log" 2>/dev/null || true
  return 0
}

stamp_clear() {
  [ "$VERIFY_INNER" = "1" ] && return 0
  rm -f "$STAMP"
  return 0
}

# A hook FILE that exists is not a hook that RUNS, and nothing in a repository
# tells you which of the two you have. This line answers it at the one moment the
# answer is actionable: when a verdict has just been printed.
hook_status_line() {
  [ "$VERIFY_INNER" = "1" ] && return 0
  local hp target
  hp="$(git config --get core.hooksPath 2>/dev/null)" || hp=""
  if [ -n "$hp" ]; then
    case "$hp" in
      # `?:[\\/]*` (classe de caractères contenant un antislash échappé) n'est
      # pas parsé par tree-sitter-bash, et un seul site retire ce fichier
      # ENTIER du compte des cibles inspectées par la porte SAST. Les deux
      # alternatives explicites disent la même chose — `C:/…` ou `C:\…` —
      # vérifié sur /usr/lib, C:/hooks, C:\hooks, .githooks, hooks/x, C:hooks.
      # `\\serveur\partage` — un chemin UNC EST absolu, et il était classé
      # RELATIF : `target` devenait `$ROOT/\\serveur\partage`, un chemin qui
      # n'existe pas, donc la garde pre-push était annoncée ABSENTE alors
      # qu'elle était installée. Défaut PRÉEXISTANT, trouvé le 2026-09-09 en
      # vérifiant l'équivalence de la réécriture ci-dessous sur 18 formes.
      /*|?:/*|?:\\*|\\\\*) target="$hp/pre-push" ;;
      *) target="$ROOT/$hp/pre-push" ;;
    esac
    if [ -f "$target" ]; then
      echo "pre-push guard: installed (core.hooksPath=$hp)"
    else
      echo "pre-push guard: NOT installed — core.hooksPath=$hp holds no pre-push"
    fi
  elif [ -f "$ROOT/.git/hooks/pre-push" ]; then
    echo "pre-push guard: installed (.git/hooks/pre-push)"
  else
    echo "pre-push guard: NOT installed — si aucun hook n'est actif : git config core.hooksPath .githooks"
  fi
  return 0
}

# ------------------------------------------------------------- porte (mode)
# THE RULE, the same here, in `.githooks/pre-push` and in ci.yml's `porte` job
# (T-00001183): ADOPTANT iff the kit's marker is absent AND the module
# discovery the adoptant gate imports is present. Two terms, MEASURED: the
# frozen fixtures of `verify.test.sh` and `pre-push.test.sh` carry neither, and
# must keep playing the kit's path. The name in a pyproject never enters it — an
# adopting project received `name = "cadre-kit"` once (measured on ec-crm-multi).
porte_mode() {  # porte_mode <tree> — prints `adoptant` or `kit`
  if [ ! -f "$1/.agents/IS_THE_KIT" ] && [ -f "$1/.agents/security/module_discovery.py" ]; then
    printf 'adoptant'
  else
    printf 'kit'
  fi
}

# porte_lire — the RETURN CHANNEL of `.agents/bin/porte_adoptant.py`. A green
# step is not enough: `porte=adoptant` reaches the stamp only if PORTE_RESULT
# names THIS tree's sha and says `verdict=OK` — a verdict left by another run,
# or a step that exited 0 without writing one, is RED (fail-closed; a mechanism
# whose return channel is not read does not exist, L-00000136). The
# `derogation_*` keys are copied from a CLOSED list (never `eval`, never
# `source`) and sanitised again here, `LC_ALL=C tr -d '\000-\037\177'` — control
# bytes out, accents kept (`[:print:]` would empty `é`, measured). A key PRESENT
# with a value emptied by that sanitising is RED: a derogation without a reason
# is not a derogation. A derogation that was not taken has NO key.
# `avertissement=` (S-00004278: no script and no module of a known family — build
# and tests NOT verified by the kit) is copied the same way, sanitised, into the
# stamp, so that `.githooks/pre-push` PRINTS it at the push; it is never a
# refusal, and an emptied one is dropped — no verdict changes because of it.
porte_lire() {  # porte_lire <PORTE_RESULT> <40-hex sha> — 0 and PORTE_LIGNES filled iff green
  local f="$1" sha="$2" ligne cle val r_sha="" r_verdict="" lignes="" vides=""
  local _nl='
'
  PORTE_LIGNES=""
  if [ ! -f "$f" ]; then
    echo "porte adoptant: no verdict file ($f) — the gate wrote no verdict, RED" >&2
    return 1
  fi
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in
      sha=*)
        r_sha="$(printf '%s' "${ligne#sha=}" | LC_ALL=C tr -d '\000-\037\177')" ;;
      verdict=*)
        r_verdict="$(printf '%s' "${ligne#verdict=}" | LC_ALL=C tr -d '\000-\037\177')" ;;
      derogation_gardes=*|derogation_module=*|derogation_test=*)
        cle="${ligne%%=*}"
        val="$(printf '%s' "${ligne#*=}" | LC_ALL=C tr -d '\000-\037\177')"
        if [ -z "$val" ]; then
          vides="${vides:+$vides }$cle"
        else
          lignes="$lignes$cle=$val$_nl"
        fi
        ;;
      avertissement=*)
        val="$(printf '%s' "${ligne#avertissement=}" | LC_ALL=C tr -d '\000-\037\177')"
        [ -z "$val" ] || lignes="${lignes}avertissement=$val$_nl"
        ;;
    esac
  done < "$f"
  if [ "$r_sha" != "$sha" ]; then
    echo "porte adoptant: $f names sha '${r_sha:-?}', not this tree's $sha — a verdict for another tree, RED" >&2
    return 1
  fi
  if [ "$r_verdict" != "OK" ]; then
    echo "porte adoptant: $f says verdict='${r_verdict:-?}' — RED" >&2
    return 1
  fi
  if [ -n "$vides" ]; then
    echo "porte adoptant: derogation key(s) with an EMPTY reason after sanitising: $vides — a derogation without a reason is not a derogation, RED" >&2
    return 1
  fi
  PORTE_LIGNES="porte=adoptant$_nl$lignes"
  return 0
}

# ------------------------------------------------- submodules of the --at clone
# T-00001183 (S-00004119, S-00004167). The frozen clone is a `git clone` of the
# live tree, and a clone has NO submodule: an adopting project whose modules
# are submodules would be verified over EMPTY directories — "no module", red at
# every push, or a derogation at every push (measured on ec-crm-multi: discover
# finds 7 entries in the live tree, 1 in the clone). So the clone's submodules
# are POPULATED, at the sha of their GITLINK, FROM THE LIVE TREE, never from the
# network:
#   * each `.gitmodules` path must be the ROOT of an initialised repository in
#     the live tree — `rev-parse --show-prefix` EMPTY, because on an empty
#     directory git climbs to the superproject and `--show-toplevel` would
#     answer the superproject (measured); otherwise a NAMED refusal whose remedy
#     is rooted at the PARENT module (`git -C '<live parent>'`: the remedy
#     without `-C` fails at depth 2 from the root, measured);
#   * the URL the clone uses is SET HERE to that live path — the `.gitmodules`
#     URL is never read;
#   * `GIT_ALLOW_PROTOCOL='file'` closes every other transport for this command
#     (a URL left unrewritten becomes "transport 'https' not allowed", never a
#     network access — measured); `-c protocol.file.allow=always` is a second
#     belt, redundant with it on git 2.55 (measured);
#   * `-c submodule.recurse=false` is the ONLY rampart of the CHILD fetch and
#     checkout that `submodule update` spawns in each module: the four
#     `--no-recurse-submodules` of the `--at` branch protect the PARENT only,
#     while `-c` travels to the children (GIT_CONFIG_PARAMETERS). Under a global
#     `submodule.recurse=true` then `fetch.recurseSubmodules=false`, a NESTED
#     gitlink bump goes red without it (measured, 8 runs); `--checkout`
#     neutralises `submodule.<name>.update=rebase|merge|none`, in config as in
#     `.gitmodules` (measured: 6 green, 6 mutants red). Any OTHER global setting
#     read by a child is BOUNDED, not enumerated: at worst a refusal (the line of
#     defence reads every module's sha), never a false green on module state;
#   * recursion is manual — this function calls itself for each module that
#     carries a `.gitmodules`, so the same command line is re-posed at every
#     level.
# A NO-OP on the kit: no `.gitmodules`, zero git call (measured under GIT_TRACE).
peupler_sous_modules() {  # peupler_sous_modules <clone> <live tree> — 0 populated or nothing to do, 1 named refusal
  local wt="$1" vivant="$2" lignes ligne cle nom chemin src prefixe
  [ -f "$wt/.gitmodules" ] || return 0
  lignes="$(git -C "$wt" config -f .gitmodules --get-regexp '^submodule\..*\.path$')" || lignes=""
  [ -n "$lignes" ] || return 0
  git -C "$wt" submodule init -q \
    || { echo "--at: git submodule init a échoué dans $wt" >&2; return 1; }
  while IFS= read -r ligne; do
    [ -n "$ligne" ] || continue
    # `submodule.<nom>.path <chemin>` porte UNE espace ; une seconde vient du nom
    # ou du chemin, et le découpage ci-dessous les confondrait (remède faux,
    # binôme c4f3 opus F6). Refus nommé AVANT le découpage.
    case "$ligne" in
      *" "*" "*)
        echo "--at: sous-module à espace dans le nom ou le chemin (« $ligne ») — non pris en charge : renommer le sous-module et son chemin sans espace (la porte adoptant refuse aussi tout chemin hors [A-Za-z0-9._/@+-])" >&2
        return 1 ;;
    esac
    cle="${ligne%% *}"
    chemin="${ligne#* }"
    nom="${cle#submodule.}"
    nom="${nom%.path}"
    src="$vivant/$chemin"
    if ! prefixe="$(git -C "$src" rev-parse --show-prefix 2>/dev/null)" || [ -n "$prefixe" ]; then
      echo "--at: sous-module '$chemin' non initialisé dans l'arbre vivant ($src) — remède : git -C '$vivant' submodule update --init -- '$chemin'" >&2
      return 1
    fi
    git -C "$wt" config "submodule.$nom.url" "$src" \
      || { echo "--at: impossible de poser l'URL locale du sous-module '$chemin' dans $wt" >&2; return 1; }
  done <<< "$lignes"
  if ! GIT_ALLOW_PROTOCOL='file' git -C "$wt" -c submodule.recurse=false -c protocol.file.allow=always submodule update -q --checkout --force --no-recommend-shallow; then
    echo "--at: git submodule update a échoué dans $wt (la cause est dans les lignes git ci-dessus ; si c'est un sha épinglé absent ou non annoncé par le module vivant : le rendre accessible depuis une branche ou HEAD de ce module ; si c'est 'failed to unpack tree object' ou 'cannot checkout new HEAD' dans un module : un réglage git GLOBAL lu par les git enfants — submodule.recurse, fetch.recurseSubmodules, submodule.<nom>.update — voir git config --global --get-regexp '^(submodule|fetch)\.' et la section adoptant de verification-discipline ; puis relancer)" >&2
    return 1
  fi
  while IFS= read -r ligne; do
    [ -n "$ligne" ] || continue
    chemin="${ligne#* }"
    if [ -f "$wt/$chemin/.gitmodules" ]; then
      peupler_sous_modules "$wt/$chemin" "$vivant/$chemin" || return 1
    fi
  done <<< "$lignes"
  return 0
}

# peupler_et_verifier — populate, then clean and check, at the ROOT only. The
# clean runs only where `.git/modules` exists, i.e. never on the kit: a REUSED
# clone may hold a stale nested repository or a build artefact inside a module,
# which `git clean -fdx` (one `f`) leaves in place. The `foreach` string is a
# CONSTANT, no value is interpolated into it. LAST LINE OF DEFENCE: any line of
# `submodule status --recursive` that does not start with a space (`-` not
# initialised, `+` not at the gitlink, `U` conflict) is a REFUSAL.
peupler_et_verifier() {  # peupler_et_verifier <clone> <live tree>
  local wt="$1" vivant="$2" etat
  peupler_sous_modules "$wt" "$vivant" || return 1
  [ -d "$wt/.git/modules" ] || return 0
  git -C "$wt" clean -ffdx -q \
    || { echo "--at: git clean -ffdx a échoué dans $wt" >&2; return 1; }
  git -C "$wt" submodule --quiet foreach --recursive 'git clean -ffdxq' \
    || { echo "--at: le nettoyage des sous-modules a échoué dans $wt" >&2; return 1; }
  etat="$(git -C "$wt" submodule status --recursive)" \
    || { echo "--at: git submodule status a échoué dans $wt" >&2; return 1; }
  if printf '%s\n' "$etat" | grep -q '^[^ ]'; then
    echo "--at: refus — un sous-module n'est pas au sha épinglé (ligne de défense : git submodule status --recursive) :" >&2
    printf '%s\n' "$etat" | grep '^[^ ]' >&2
    return 1
  fi
  return 0
}

# base_semgrep_vivant <sha> — the base of the adoptant gate's semgrep, computed on
# the LIVE tree (binôme c4f3 bis, fable F1 / opus T2). In the frozen clone,
# `origin` IS the live tree: its `origin/*` are the live tree's LOCAL branches,
# and its `origin/HEAD` names the branch the live tree had checked out when the
# clone was made, frozen at every reuse — measured: base = HEAD^1, and an `eval`
# in commit 1 of 2 passed the gate. Same order as `base_semgrep` in
# porte_adoptant.py: origin/HEAD resolved, origin/main, origin/master, main,
# master. Prints the merge-base, or nothing (the gate then decides, and says so).
base_semgrep_vivant() {  # base_semgrep_vivant <sha>
  local sha="$1" tete ref base
  tete="$(git -C "$ROOT" symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null)" || tete=""
  for ref in "$tete" refs/remotes/origin/main refs/remotes/origin/master refs/heads/main refs/heads/master; do
    [ -n "$ref" ] || continue
    git -C "$ROOT" rev-parse --verify -q "$ref^{commit}" >/dev/null 2>&1 || continue
    base="$(git -C "$ROOT" merge-base "$sha" "$ref" 2>/dev/null)" || continue
    if [ -n "$base" ]; then
      printf '%s' "$base"
      return 0
    fi
  done
  return 0
}

# ------------------------------------------------------------- --rouges (replay)
# T-01M5QBFKM444FB53RM2J1NBB4X, pilot decision S-01M5QBG09B3R1NDJPZATE7NCDT. Replays the entries of
# PORTE_ROUGES on the LIVE tree, each through ITS runner — never `step`, never a new verdict: no stamp, no
# chrono row, no `VERIFY OK`. It inherits the purge at entry (one place, gate and replay purged alike).
# `pytest` entries: ONE `run-pytest-shards.sh --only …` call (its `--- [i/N]` lines attribute each file);
# `bash` entries: one `run-bash-tests.sh --only` each; `etape` entries: a CLOSED table of the three host
# step labels, replayed whole; anything else (`linux replay`, `porte adoptant`, `?`) is IMPOSSIBLE. No
# credit: green (rc 0) only if every entry was PLAYED by its runner and came back rc 0 — a suite that
# announces a SKIP, a runner that refuses (rc 2), an invalid path, is IMPOSSIBLE and the replay is rc 2 —
# except an `etape` replayed whole, judged on its rc like the gate's step; a pytest collection in error
# (rc 2 with the runner's « la collecte nue rend rc=2 » line) was played and is a FAIL, never IMPOSSIBLE.
rouges_py_ok() {  # the --only rule of run-pytest-shards.sh, checked HERE too: an invalid path never reaches it
  case "$1" in
    -*|/*|*..*) return 1 ;;
  esac
  case "$1" in
    *[!A-Za-z0-9_./-]*) return 1 ;;
  esac
  case "$1" in
    *.py) return 0 ;;
  esac
  return 1
}
rouges_sh_ok() {  # `./<path>.test.sh`, no `..`, a closed charset
  case "$1" in
    ./*) : ;;
    *) return 1 ;;
  esac
  case "$1" in
    *..*) return 1 ;;
  esac
  case "$1" in
    *[!A-Za-z0-9_./@+-]*) return 1 ;;
  esac
  case "$1" in
    *.test.sh) return 0 ;;
  esac
  return 1
}
RJ_PASS=0
RJ_FAIL=0
RJ_IMP=0
rj_impossible() {  # rj_impossible <entry> <cause> [<count>]
  echo "--- REJEU IMPOSSIBLE $1 ($2)"
  RJ_IMP=$((RJ_IMP + ${3:-1}))
}
rj_run() {  # rj_run <output file> <command...> — streamed AND captured; returns the command's rc
  local sortie="$1"
  shift
  CADRE_GATE_FAIL_FAST=0 CADRE_GATE_BASE=none CADRE_GATE_DURATIONS_DIR="$ROUGES_TMP/durees" "$@" < /dev/null 2>&1 | tee "$sortie"
  return "${PIPESTATUS[0]}"
}
rejouer_rouges() {
  local f="$PORTE_ROUGES" verrou taille ligne genre entree entete="" r_sha="" r_mode="" entrees="" n=0 court tete rc k out i
  local -a py=() sh=() et=() pyargs=()
  if [ "$(porte_mode "$ROOT")" = "adoptant" ]; then
    echo "--rouges: sans objet en porte adoptant — joue la porte complète (bash core-scripts/verify.sh --at HEAD)" >&2
    return 2
  fi
  if [ ! -e "$f" ] && [ ! -L "$f" ]; then
    # An `--at` gate erases the list once its lock is held: while that lock exists, the advice is to WAIT
    # for its verdict, never to start a second gate beside it (two gates never run in parallel).
    verrou="${VERIFY_WORKTREE_DIR:-$(cd "$ROOT/.." && pwd)/$(basename "$ROOT")-verify}.lock"
    if [ -e "$verrou" ]; then
      echo "--rouges: une porte --at tient $verrou et a effacé la liste — attends son verdict" >&2
      return 2
    fi
    echo "--rouges: aucune porte rouge mémorisée — joue la porte complète (bash core-scripts/verify.sh)" >&2
    return 2
  fi
  if [ -L "$f" ] || [ ! -f "$f" ]; then
    echo "--rouges: liste illisible ($f n'est pas un fichier ordinaire) — joue la porte complète" >&2
    return 2
  fi
  taille="$(wc -c < "$f" 2>/dev/null | tr -d ' ')" || taille=""
  case "$taille" in
    ''|*[!0-9]*) taille=999999 ;;
  esac
  if [ "$taille" -gt 65536 ]; then
    echo "--rouges: liste illisible ($f dépasse 64 Kio) — joue la porte complète" >&2
    return 2
  fi
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    if [ -z "$entete" ]; then entete="$ligne"; continue; fi
    case "$ligne" in
      sha=*) r_sha="${ligne#sha=}" ;;
      mode=*) r_mode="${ligne#mode=}" ;;
      at=*) : ;;
      '') : ;;
      *) entrees="$entrees$ligne$_rouges_nl"; n=$((n + 1)) ;;
    esac
  done < "$f"
  if [ "$entete" != "# porte-rouges v1" ]; then
    echo "--rouges: liste illisible (en-tête « $entete » inconnu) — joue la porte complète" >&2
    return 2
  fi
  if [ "$n" -eq 0 ]; then
    echo "--rouges: liste vide — aucune entrée à rejouer ; joue la porte complète" >&2
    return 2
  fi
  court="$r_sha"
  case "$r_sha" in
    *[!0-9a-f]*) court="" ;;
  esac
  if [ -z "$court" ] || [ "${#r_sha}" -ne 40 ] || ! git merge-base --is-ancestor "$r_sha" HEAD 2>/dev/null; then
    echo "--rouges: porte d'une autre lignée ($(printf '%.12s' "$r_sha")) — HEAD n'en descend pas ; joue la porte complète" >&2
    return 2
  fi
  court="$(git rev-parse --short "$r_sha" 2>/dev/null)" || court="$r_sha"
  tete="$(git rev-parse --short HEAD 2>/dev/null)" || tete="unknown"
  rouges_tmp_dir
  if [ -z "$ROUGES_TMP" ] || ! mkdir -p "$ROUGES_TMP/durees" 2>/dev/null; then
    echo "--rouges: dossier temporaire introuvable (mktemp -d) — rien n'est rejoué" >&2
    return 2
  fi
  echo "Rejeu des rouges de la porte $court (mode=$r_mode) sur l'arbre vivant @ $tete — $n entrée(s), chacune par son coureur ; PAS un verdict"
  echo
  # Classify FIRST (no child reads the list's stdin), then play.
  while IFS= read -r ligne; do
    [ -n "$ligne" ] || continue
    genre="${ligne%%$_rouges_tab*}"
    entree="${ligne#*$_rouges_tab}"
    if [ "$genre" = "$ligne" ]; then
      rj_impossible "$ligne" "ligne sans genre"
      continue
    fi
    case "$genre" in
      pytest)
        if rouges_py_ok "$entree"; then py+=("$entree"); else rj_impossible "pytest $entree" "chemin non admis"; fi ;;
      bash)
        if rouges_sh_ok "$entree"; then sh+=("$entree"); else rj_impossible "bash $entree" "chemin non admis"; fi ;;
      etape)
        et+=("$entree") ;;
      *)
        rj_impossible "$ligne" "genre inconnu" ;;
    esac
  done <<< "$entrees"
  if [ "${#py[@]}" -gt 0 ]; then
    for i in "${py[@]}"; do pyargs+=(--only "$i"); done
    echo "=== REJEU pytest : bash core-scripts/run-pytest-shards.sh ${pyargs[*]}"
    out="$ROUGES_TMP/rejeu-pytest.out"
    rj_run "$out" bash core-scripts/run-pytest-shards.sh "${pyargs[@]}"
    rc=$?
    # The runner's aggregate line (`pytest: <summary> in Ns (…)`) must count at least one PASSED test: a
    # green made only of skipped tests played nothing — the pytest twin of a bash suite's SKIP.
    # BOUND: it judges the TOTAL of this ONE call, never each file — an all-skipped file listed next to a
    # file that passes IS credited (verify-rouges.test.sh R10c pins it), and xfail or a partial skip are not seen.
    if [ "$rc" -eq 0 ] && ! grep -qE '^pytest: ([^ ]+ )*[1-9][0-9]* passed[, ]' "$out"; then
      rj_impossible "pytest (${#py[@]} fichier(s))" "aucun test joué : tout sauté, ou aucun résumé" "${#py[@]}"
    elif [ "$rc" -eq 0 ]; then
      echo "--- REJEU PASS pytest (${#py[@]} fichier(s))"
      RJ_PASS=$((RJ_PASS + ${#py[@]}))
    elif [ "$rc" -eq 2 ] && grep -q '^run-pytest-shards: la collecte nue rend rc=2' "$out"; then
      # rc 2 of the runner is ALSO a collection in error (a broken import): that file was played and is red.
      echo "--- REJEU FAIL pytest (${#py[@]} fichier(s)) (collecte en erreur, exit 2)"
      RJ_FAIL=$((RJ_FAIL + ${#py[@]}))
    elif [ "$rc" -eq 2 ] || [ "$rc" -eq 5 ]; then
      rj_impossible "pytest (${#py[@]} fichier(s))" "le coureur refuse ou ne collecte rien, rc=$rc" "${#py[@]}"
    else
      echo "--- REJEU FAIL pytest (${#py[@]} fichier(s)) (exit $rc)"
      RJ_FAIL=$((RJ_FAIL + ${#py[@]}))
    fi
    echo
  fi
  for entree in ${sh[@]+"${sh[@]}"}; do
    echo "=== REJEU bash : bash core-scripts/run-bash-tests.sh --only $entree"
    out="$ROUGES_TMP/rejeu-bash.out"
    rj_run "$out" bash core-scripts/run-bash-tests.sh --only "$entree"
    rc=$?
    k="$(sed -n 's/^Bash test summary: .* \([0-9][0-9]*\) skipping.*$/\1/p' "$out" | sed -n '$p')"
    if [ "$rc" -eq 2 ]; then
      rj_impossible "$entree" "refusée par le coureur, rc=2"
    elif [ "$rc" -ne 0 ]; then
      echo "--- REJEU FAIL $entree (exit $rc)"
      RJ_FAIL=$((RJ_FAIL + 1))
    elif [ -z "$k" ]; then
      rj_impossible "$entree" "aucun résumé du coureur"
    elif [ "$k" -ne 0 ]; then
      rj_impossible "$entree" "SKIP annoncé : verte sans avoir joué"
    else
      echo "--- REJEU PASS $entree"
      RJ_PASS=$((RJ_PASS + 1))
    fi
    echo
  done
  for entree in ${et[@]+"${et[@]}"}; do
    out="$ROUGES_TMP/rejeu-etape.out"
    case "$entree" in
      "python -m pytest (CI scope, shards)")
        echo "=== REJEU étape entière : $entree"
        rj_run "$out" bash core-scripts/run-pytest-shards.sh ;;
      "bash core-scripts/run-bash-tests.sh")
        echo "=== REJEU étape entière : $entree"
        rj_run "$out" bash core-scripts/run-bash-tests.sh ;;
      "bash .agents/security/shellcheck-scan.sh")
        echo "=== REJEU étape entière : $entree"
        rj_run "$out" bash .agents/security/shellcheck-scan.sh ;;
      *)
        rj_impossible "étape $entree" "aucun coureur rejouable hors porte complète"
        continue ;;
    esac
    rc=$?
    if [ "$rc" -eq 0 ]; then
      echo "--- REJEU PASS étape $entree"
      RJ_PASS=$((RJ_PASS + 1))
    else
      echo "--- REJEU FAIL étape $entree (exit $rc)"
      RJ_FAIL=$((RJ_FAIL + 1))
    fi
    echo
  done
  k=$((RJ_PASS + RJ_FAIL + RJ_IMP))
  # Every entry of the list is JUDGED once: a count that differs (an entry lost on the way) is never a green.
  if [ "$k" -ne "$n" ]; then
    rj_impossible "liste" "$k entrée(s) jugée(s) pour $n — compte faux, jamais un vert"
  fi
  k="$n"
  if [ "$RJ_IMP" -gt 0 ]; then
    echo "REJEU INCOMPLET @ $tete : $RJ_IMP/$k rouge(s) non rejouable(s) par leur coureur, $RJ_FAIL encore rouge(s) — PAS un verdict, aucun tampon ; joue la porte complète : bash core-scripts/verify.sh"
    return 2
  fi
  if [ "$RJ_FAIL" -gt 0 ]; then
    echo "REJEU ROUGE @ $tete : $RJ_FAIL/$k rouge(s) encore rouge(s) — PAS un verdict, aucun tampon"
    return 1
  fi
  echo "REJEU VERT @ $tete : $k/$k rouge(s) rejouée(s) par leurs coureurs — PAS un verdict, aucun tampon ; push : bash core-scripts/verify.sh --at HEAD --linux"
  return 0
}
if [ "$ROUGES_SEUL" = "1" ]; then
  rejouer_rouges
  exit "$?"
fi

# ---------------------------------------------------------------- frozen mode
# Delegate to a checkout of <ref> and exit. Everything below this block only
# ever sees a live tree (the inner call is made WITHOUT --at, so no recursion).
if [ -n "$AT" ]; then
  # 1. Resolve first: an invalid ref must cost nothing (no lock, no clone).
  SHA="$(git rev-parse --verify --quiet --end-of-options "${AT}^{commit}")" || SHA=""
  if [ -z "$SHA" ]; then
    echo "--at: '$AT' does not resolve to a commit in this repository" >&2
    exit 1
  fi
  SHORT="$(git rev-parse --short "$SHA")" || SHORT="$SHA"

  # 2. A dirty live tree is not an error — but the verdict will not cover it.
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "warning: live tree has uncommitted changes — the verdict covers $SHORT, not your working tree" >&2
  fi

  # 3. Sibling of the repo, never inside it: run-bash-tests.sh discovers suites
  #    by walking the tree, and a nested copy would double every suite.
  WT="${VERIFY_WORKTREE_DIR:-$(cd "$ROOT/.." && pwd)/$(basename "$ROOT")-verify}"

  # 4. One run at a time: two runs sharing a clone would checkout under each
  #    other's feet and both verdicts would be fiction.
  #
  # `mkdir` remains the arbiter — it is the atomic primitive, and creating the
  # directory IS taking the lock. What the directory now also does is SAY WHO
  # HOLDS IT (`$LOCK/owner`), because an empty directory carries no information at
  # all: telling an abandoned lock from a live one came down to the operator's
  # cleverness with `ps`. Measured twice in one evening, both times at the
  # pilot's expense:
  #   - a killed run left its lock behind, and the next run refused with nothing
  #     but "already in progress" — a human had to arbitrate dead vs alive;
  #   - worse, a run believed dead was ALIVE: the harness's stop had killed only
  #     the shell WRAPPER, and the children (the clone's verify.sh, then
  #     run-bash-tests.sh) kept running and kept holding the lock legitimately.
  # So the refusal names the PID and the age of the lock, and a dead holder is
  # reclaimed automatically. An abandoned lock must never cost a manual gesture.
  LOCK="$WT.lock"
  LOCK_OWNER="$LOCK/owner"

  # Is that pid still running? `kill -0` is the usual primitive, and its
  # behaviour under Git-Bash was MEASURED rather than assumed (MINGW64_NT-10.0,
  # bash 5.2.37): `kill` is a shell BUILTIN there and speaks MSYS pids — the same
  # numbering `$$` yields — and it discriminates correctly (self → 0, an exited
  # child → 1, pid 999999 → 1, a live `sleep &` → 0). No fallback is needed on
  # either platform. Two limits, neither of them fixable here:
  #   - a non-numeric or EMPTY argument also returns non-zero, i.e. "dead", so
  #     the caller must validate the pid BEFORE asking — otherwise an unreadable
  #     lock would be declared abandoned and silently stolen;
  #   - on POSIX a live process owned by ANOTHER user answers EPERM, also "dead".
  #     The lock is keyed on a repo path on a dev box, so a foreign owner means a
  #     shared checkout, which this script cannot arbitrate anyway.
  pid_alive() { kill -0 "$1" 2>/dev/null; }

  fmt_elapsed() {  # fmt_elapsed <seconds> -> "1h 02m 05s" / "3m 12s" / "12s"
    local s="$1"
    if [ "$s" -ge 3600 ]; then
      # `$(((s % 3600) / 60))` — parenthèses imbriquées en arithmétique : forme
      # valide que tree-sitter-bash ne parse pas. Deux temps, même résultat.
      local reste=$(( s % 3600 ))
      printf '%dh %02dm %02ds' "$((s / 3600))" "$(( reste / 60 ))" "$((s % 60))"
    elif [ "$s" -ge 60 ]; then
      printf '%dm %02ds' "$((s / 60))" "$((s % 60))"
    else
      printf '%ds' "$s"
    fi
  }

  lock_field() {  # lock_field <key> — empty when the lock says nothing usable
    [ -f "$LOCK_OWNER" ] || return 0
    # `tr -d '\r'`: the file may have been written by a run under a CRLF-happy
    # editor or shell, and a trailing \r turns a pid into a non-number.
    sed -n "s/^$1=//p" "$LOCK_OWNER" 2>/dev/null | head -1 | tr -d '\r'
  }

  # Failing to write the owner does NOT abort the run: the lock is already held
  # (the mkdir succeeded), and a run that verifies is worth more than a run that
  # refuses because it could not annotate itself. Worst case the next refusal
  # falls back to the manual-recovery path.
  lock_write_owner() {
    {
      echo "pid=$$"
      echo "started=$(date +%s 2>/dev/null || echo)"
      echo "started_at=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
      echo "host=$(hostname 2>/dev/null || echo unknown)"
      echo "ref=$AT"
      echo "sha=$SHORT"
    } > "$LOCK_OWNER" 2>/dev/null || true
  }

  # LAST RESORT, kept from the original: the lock exists but cannot be attributed
  # to anyone. No takeover here — stealing a lock we cannot read is exactly the
  # data-loss shape the identity guard below refuses.
  lock_refuse_unreadable() {  # lock_refuse_unreadable <why>
    echo "a --at run is already in progress (lock: $LOCK)" >&2
    echo "      the lock names no usable holder ($1), so alive vs abandoned cannot be decided here" >&2
    echo "      check for a surviving run first (ps), then recover with: rm -f \"$LOCK_OWNER\"; rmdir \"$LOCK\"" >&2
    exit 1
  }

  if ! mkdir "$LOCK" 2>/dev/null; then
    lock_pid="$(lock_field pid)"
    lock_started="$(lock_field started)"
    case "$lock_pid" in
      '' | *[!0-9]*) lock_refuse_unreadable "no numeric pid recorded" ;;
    esac

    now="$(date +%s 2>/dev/null)" || now=""
    case "$lock_started" in
      '' | *[!0-9]*) lock_started="" ;;
    esac
    if [ -n "$now" ] && [ -n "$lock_started" ] && [ "$now" -ge "$lock_started" ]; then
      held="held for $(fmt_elapsed "$((now - lock_started))")"
    else
      held="taken at an unrecorded time"
    fi

    if pid_alive "$lock_pid"; then
      echo "a --at run is already in progress: PID $lock_pid, $held (lock: $LOCK)" >&2
      echo "      that process is ALIVE — note that a stop which kills only the wrapper leaves its children running and holding this lock" >&2
      echo "      wait for it, or stop PID $lock_pid and its children, then re-run" >&2
      exit 1
    fi

    # ABANDONED. The recorded holder is gone, so the lock is stale: say so, take
    # it over, and announce the takeover — silence here would read as a normal
    # start and hide the fact that a previous run died. `mkdir` stays the
    # arbiter: the stale directory is removed and re-created, so if two runs
    # reclaim the same lock in the same instant, exactly one of them wins.
    echo "stale lock abandoned by PID $lock_pid (dead), $held — taking it over (lock: $LOCK)" >&2
    rm -f "$LOCK_OWNER" 2>/dev/null
    rmdir "$LOCK" 2>/dev/null
    if ! mkdir "$LOCK" 2>/dev/null; then
      echo "a --at run is already in progress (lock: $LOCK) — another run claimed the freed lock first" >&2
      exit 1
    fi
  fi
  lock_write_owner
  # The ENTRY of this full gate (the lock is held): the previous red list goes, so a run killed or refused
  # below leaves `--rouges` nothing stale to replay.
  rm -f "$PORTE_ROUGES"

  # RELEASE IS THE HOLDER'S ACT, and that is enforced rather than assumed. Two
  # reasons the naive `trap 'rmdir "$LOCK"' EXIT` is not enough:
  #   - it must now also remove the owner FILE, or `rmdir` refuses a non-empty
  #     directory and every single run leaks its lock;
  #   - a FORKED CHILD of this shell can run this very trap. Measured on this box
  #     while testing this change (Git-Bash MINGW64, bash 5.2.37): a background
  #     job killed shortly after being spawned is killed BEFORE it finishes
  #     exec'ing — MSYS fork emulation is slow — so the victim is still bash, and
  #     it executes the EXIT trap it inherited. 25 firings out of 25 attempts, and
  #     in every one `$$` was the PARENT's pid, so `$$` cannot tell them apart.
  #     `$BASHPID` can: it is the real pid of the current shell process.
  # Hence the guard below. It matters here specifically because this trap DELETES
  # A LOCK: an unguarded one lets a stray child free the lock while the run it
  # protects is still going, which is precisely the class of bug this task exists
  # to close. On a bash without BASHPID (3.x) the guard degrades to inert rather
  # than to wrong, and the owner-pid check still stands.
  LOCK_HOLDER="${BASHPID:-$$}"
  lock_release() {
    [ "${BASHPID:-$$}" = "$LOCK_HOLDER" ] || return 0
    # And do not free a lock that has since been recorded to someone else (a
    # takeover after our own owner write failed). No owner file at all means the
    # write failed but the directory is still ours to remove.
    if [ -f "$LOCK_OWNER" ] && [ "$(lock_field pid)" != "$$" ]; then
      return 0
    fi
    rm -f "$LOCK_OWNER" 2>/dev/null
    rmdir "$LOCK" 2>/dev/null
  }
  # The outer EXIT trap records this gate and releases the lock, in that order.
  CHRONO_LOCK=1
  # Trapped from here only, once the lock is held: bash defers a trapped signal
  # until the running foreground step returns, then the EXIT trap releases the
  # lock (CHRONO_INFLIGHT still 1 while the delegated run is in flight, so no
  # chrono row). Live mode: only the EXIT-trap ignore of verify_on_exit applies.
  # The stamp is cleared IN the trap: its `exit` fires before `rc=$?` below, so
  # the RED-clears-the-stamp branch is never reached, and a previous green stamp
  # of the same SHA would survive a gate killed mid-run.
  trap 'stamp_clear; exit 143' TERM
  trap 'stamp_clear; exit 129' HUP
  CHRONO_ACTIVE=1
  CHRONO_INFLIGHT=1  # cleared once the delegated run returned; a refusal below records no row

  # 5. Prepare the clone.
  if [ ! -e "$WT" ]; then
    git clone -q "$ROOT" "$WT" \
      || { echo "--at: git clone failed ($ROOT -> $WT)" >&2; exit 1; }
  else
    # IDENTITY FIRST. `checkout -f` + `clean -fdx` on an unidentified directory
    # is a data-loss bug waiting for the day $WT collides with something real,
    # so prove it is OUR verification clone before any destructive command.
    # THREE proofs, all of which must pass:
    #   a. `.git` is a DIRECTORY (a real repository, not a worktree pointer file
    #      and not a bare directory of someone else's files);
    #   b. `origin` resolves to THIS repo;
    #   c. the two repositories share their ROOT COMMIT(s).
    # (c) is not belt-and-braces, it closes a real hole (CWE-346): (b) alone is
    # forgeable by CONFIG, with no clone involved and no history in common —
    # `git init "$WT" && git -C "$WT" remote add origin <path to $ROOT>` passes
    # it, after which `clean -fdx` deletes untracked files from a directory this
    # script never created (PoC: a planted precious.txt disappeared). A root
    # commit cannot be forged: a repo either descends from ours or it does not.
    # Multiple roots are legal (independent histories merged, grafts), so the
    # full sorted LISTS are compared, never just the first line; and a $WT with
    # no commit at all makes rev-list fail, which is a refusal, not a pass.
    #
    # Path normalisation, and why the naive compare is wrong: git stores the
    # clone URL in its own Windows form, which on this box came back as
    # `C:/Users/USER~1.NAME/...` — an 8.3 SHORT NAME — while $ROOT in bash is
    # `/c/Users/username/...`. Measured. So both operands go through the SAME
    # two-step canonicaliser: `cygpath -u` when available (Windows form -> POSIX
    # form, a no-op absent on Linux), then `cd … && pwd -P`, which is what
    # actually resolves 8.3 names, symlinks and /tmp-style mount aliases. Two
    # paths are the same directory iff the canonicaliser agrees; a path that
    # cannot be entered yields the empty string and never compares equal.
    canon_dir() {
      local p="${1:-}"
      [ -n "$p" ] || return 0
      case "$p" in
        file://*) p="${p#file://}" ;;
      esac
      if command -v cygpath >/dev/null 2>&1; then
        p="$(cygpath -u "$p" 2>/dev/null || printf '%s' "$p")"
      fi
      # `--` so a path that happens to be `-` is a path, not `cd -`.
      (cd -- "$p" 2>/dev/null && pwd -P) || printf ''
    }
    id_refuse() {  # id_refuse <why>
      echo "--at: $WT exists but is not the verification clone of this repository — refusing to touch it" >&2
      echo "      ($1)" >&2
      echo "      (move it aside, or point VERIFY_WORKTREE_DIR elsewhere)" >&2
      exit 1
    }
    # (a) + (b) — a real repository whose origin is this one.
    wt_origin=""
    if [ -d "$WT/.git" ]; then
      wt_origin="$(git -C "$WT" remote get-url origin 2>/dev/null)" || wt_origin=""
    fi
    wt_origin_c="$(canon_dir "$wt_origin")"
    root_c="$(canon_dir "$ROOT")"
    if [ -z "$wt_origin_c" ] || [ -z "$root_c" ] || [ "$wt_origin_c" != "$root_c" ]; then
      id_refuse "no .git directory, or origin does not point at $ROOT"
    fi
    # (c) — and a shared lineage, which no amount of config can fabricate.
    wt_roots="$(git -C "$WT" rev-list --max-parents=0 HEAD 2>/dev/null | LC_ALL=C sort)" || wt_roots=""
    root_roots="$(git -C "$ROOT" rev-list --max-parents=0 HEAD 2>/dev/null | LC_ALL=C sort)" || root_roots=""
    if [ -z "$wt_roots" ] || [ -z "$root_roots" ] || [ "$wt_roots" != "$root_roots" ]; then
      id_refuse "root commit(s) differ from this repository's — not a clone of it"
    fi
    # Refresh: the clone was made at some earlier point, and $SHA is usually
    # newer than that.
    git -C "$WT" fetch -q --no-recurse-submodules origin \
      || { echo "--at: git fetch failed in $WT" >&2; exit 1; }
  fi

  # `--no-recurse-submodules` on the four fetch/checkout lines (T-00001183): a
  # global `submodule.recurse=true` — a common setting — makes a `checkout`
  # recurse into the clone's modules and FAIL as soon as a gitlink moves to a
  # commit the clone's copy of the module lacks (measured: `cannot checkout new
  # HEAD`), and a recursing `fetch` masks the named refusal of the population
  # step below behind "git fetch failed" (measured). The modules are populated
  # by `peupler_et_verifier`, from the live tree, never by these four commands.
  # No-op on a repository without submodules.
  # Checkout is shared by both paths. A SHA that no ref carries (a fresh commit
  # on a branch the clone predates, a detached HEAD) is not in the clone yet, so
  # ask for it by name before giving up.
  if ! git -C "$WT" checkout --detach -q --no-recurse-submodules -f "$SHA" 2>/dev/null; then
    git -C "$WT" fetch -q --no-recurse-submodules origin "$SHA" \
      || { echo "--at: $SHA is not reachable from $ROOT (unreferenced commit?)" >&2; exit 1; }
    git -C "$WT" checkout --detach -q --no-recurse-submodules -f "$SHA" \
      || { echo "--at: git checkout failed in $WT" >&2; exit 1; }
  fi
  # No-op on a fresh clone, the point of the exercise on a reused one: CI starts
  # from a clean checkout, so this must too.
  git -C "$WT" clean -fdx -q \
    || { echo "--at: git clean failed in $WT" >&2; exit 1; }

  # 6. Last line of defence before anything is allowed to print a verdict.
  wt_head="$(git -C "$WT" rev-parse HEAD 2>/dev/null)" || wt_head=""
  if [ "$wt_head" != "$SHA" ]; then
    # `<unknown>` passe par une variable : des chevrons DANS l'expansion ne se
    # parsent pas (tree-sitter-bash). Message affiché INCHANGÉ.
    _inconnu='<unknown>'
    echo "--at: refusing to report a verdict — $WT is at ${wt_head:-$_inconnu}, expected $SHA" >&2
    exit 1
  fi

  # 6b. Submodules, populated from the LIVE tree at their gitlink's sha (see
  #     `peupler_sous_modules`). A refusal exits HERE, above the stamp — the
  #     asymmetry (2) named below: the stamp of ANOTHER sha stays, harmless. No
  #     derogation covers a population refusal: it carries its own remedy.
  peupler_et_verifier "$WT" "$ROOT" || exit 1
  # The mode is decided on the FROZEN tree, never on the live one: the verdict
  # is about $SHA, and the marker may differ between the two.
  WT_PORTE="$(porte_mode "$WT")"

  # 6c. ADOPTANT: semgrep's base comes from the LIVE tree, passed to the gate as
  #     CADRE_SEMGREP_BASE (see `base_semgrep_vivant`). The clone's
  #     `origin/HEAD` is removed: it names the live tree's checked-out branch,
  #     not a default branch, so a gate left without an imposed base falls to a
  #     FULL scan, said, never to `HEAD^1`. Kit mode: nothing here.
  SEMGREP_BASE=""
  if [ "$WT_PORTE" = "adoptant" ]; then
    git -C "$WT" symbolic-ref --delete refs/remotes/origin/HEAD 2>/dev/null || :
    SEMGREP_BASE="$(base_semgrep_vivant "$SHA")"
    if [ -n "$SEMGREP_BASE" ]; then
      echo "semgrep base (live tree): $SEMGREP_BASE — merge-base of $SHORT with the live tree's default branch"
    else
      echo "semgrep base (live tree): none — no default branch resolves in $ROOT; the gate decides, and says so"
    fi
  fi

  # 7. Run the CLONE's OWN copy (it re-bases itself off BASH_SOURCE, so no cd is
  #    needed here and the live tree keeps its cwd), plain call so the EXIT trap
  #    still releases the lock.
  echo "frozen checkout @ $SHORT ($WT) — live tree stays free"
  #    CADRE_GATE_DURATIONS_DIR — where the two runners keep their measured
  #    durations (contract between lots, T-01M4WTYT8M: this name, this default).
  #    It names the LIVE tree, never the clone: the `git clean -fdx` above would
  #    wipe a table kept under $WT at every gate. An explicit value is honoured.
  #    Prefixed BEFORE `CADRE_SEMGREP_BASE=`, so that substring stays twice here.
  #    CADRE_GATE_JAMBES — the value READ above (then unset here), handed back at the HEAD of the line: the
  #    inner run decides its own legs from it, never from the default (T-01M60XKFK7MPKZWNHH326ZMW3M C10).
  if [ "$LINUX" -eq 1 ]; then
    CADRE_GATE_JAMBES="$JAMBES" CADRE_GATE_DURATIONS_DIR="${CADRE_GATE_DURATIONS_DIR:-$ROOT/.agents/state/local/porte-durees}" CADRE_SEMGREP_BASE="$SEMGREP_BASE" VERIFY_INNER=1 bash "$WT/core-scripts/verify.sh" --linux
  else
    CADRE_GATE_JAMBES="$JAMBES" CADRE_GATE_DURATIONS_DIR="${CADRE_GATE_DURATIONS_DIR:-$ROOT/.agents/state/local/porte-durees}" CADRE_SEMGREP_BASE="$SEMGREP_BASE" VERIFY_INNER=1 bash "$WT/core-scripts/verify.sh"
  fi
  rc=$?
  CHRONO_INFLIGHT=0
  # The inner's first red label, for the 6th column of the journal. A TRUST
  # BOUNDARY: the file was written by the code of the frozen SHA. Read only on
  # a red, only when it exists, never through a symlink, at most 200 bytes;
  # `chrono_write` turns a control character into `?`. Never read by a verdict.
  _etape_fichier="$WT/.agents/state/local/ETAPE_ROUGE"
  if [ "$rc" -ne 0 ] && [ -f "$_etape_fichier" ] && [ ! -L "$_etape_fichier" ]; then
    ETAPE_ROUGE="$(head -c 200 "$_etape_fichier" 2>/dev/null)" || ETAPE_ROUGE=""
  fi
  # The inner's red list, written in ITS clone: a regular file of at most 64 KiB naming $SHA, else `etape ?`.
  if [ "$rc" -ne 0 ]; then
    _rouges_wt="$(rouges_relire "$WT/.agents/state/local/PORTE_ROUGES" "$SHA")"
    if [ -n "$_rouges_wt" ]; then
      ROUGES_LISTE="$_rouges_wt$_rouges_nl"
    else
      ROUGES_LISTE="etape$_rouges_tab$_rouges_inconnue$_rouges_nl"
    fi
  fi
  # THE VERDICT IS PERSISTED HERE, not by the inner run. This branch is the only
  # place that holds BOTH the full 40-hex $SHA (resolved above) and $LINUX, and
  # its $ROOT is the live repository rather than the disposable clone.
  #
  # BOTH OUTCOMES ACT, and the asymmetry that made that necessary was MEASURED:
  # this branch ends at `exit "$rc"` and NEVER reaches the live-tree `rm -f`
  # below, so a RED `--at` used to leave the previous GREEN stamp on disk. Stated
  # no wider than it is true: A STALE GREEN DOES NOT SURVIVE A RED ON THE SAME PATH,
  # nor a TERM/HUP during the run (cleared by the trap set once the lock is held).
  #
  # Two asymmetries REMAIN, named here rather than papered over. (1) A bare green
  # `verify.sh` OVERWRITES a valid `frozen` stamp with `mode=live`; the effect is
  # a REFUSED push carrying its remedy (`--at <sha>`), never a false green — but
  # read it here rather than meet it at a push. (2) A SETUP failure of `--at`
  # exits ABOVE this point and leaves the stamp intact — harmless, because that
  # stamp is bound to a `sha` nothing has moved.
  #
  # ADOPTANT (T-00001183): the inner run's exit code is not the whole verdict —
  # the gate's return channel must name $SHA and say OK (`porte_lire`), and the
  # `linux` bit is 0 whatever `--linux` said: the container leg replays the
  # kit's suite, which is not this project's verdict.
  STAMP_LINUX="$LINUX"
  if [ "$WT_PORTE" = "adoptant" ]; then
    STAMP_LINUX=0
    if [ "$rc" -eq 0 ]; then
      porte_lire "$WT/.agents/state/local/PORTE_RESULT" "$SHA" || { rc=1; noter_rouge "porte adoptant (PORTE_RESULT)"; }
    fi
  fi
  if [ "$rc" -eq 0 ]; then
    stamp_write "$SHA" frozen "$STAMP_LINUX"
  else
    stamp_clear
    if [ "$LINUX" -eq 1 ]; then rouges_ecrire "$SHA" frozen-linux; else rouges_ecrire "$SHA" frozen; fi
  fi
  hook_status_line
  exit "$rc"
fi

failed=0
# NOTRUN — the steps (and the --linux leg) skipped by the fail-fast above. Counted
# so the verdict can say the failure list is NOT complete; never inherited.
NOTRUN=0
# _linux_duree — la durée de la jambe conteneur, en secondes, sous une forme
# prête à coller en fin de ligne. Rend une chaîne VIDE si l'horloge n'a pas pu
# être lue : une mesure absente se dit par le silence, jamais par un zéro, qui
# se relirait comme « instantané ».
#
# ARITHMÉTIQUE PAR `expr`, ET MA JUSTIFICATION D'ORIGINE ÉTAIT TROP LARGE — le
# binôme l'a mesuré. J'écrivais « pas par `$(( … ))` », ce qui aurait condamné
# une forme que ce fichier emploie déjà sans dommage (`$((now - lock_started))`,
# l.312, parse sans souci). LA FORME RÉELLEMENT INTERDITE est la parenthèse
# IMBRIQUÉE — `$(( (a-b)/60 ))` — l'une des huit que le parseur du SAST ne lit
# pas ; et un seul site retire le FICHIER ENTIER du périmètre inspecté, la porte
# annonçant alors `clean` sur un script qu'elle n'a jamais lu (mesuré : 17
# fichiers shell sur 121 étaient hors lecture pour cette raison).
# `expr` reste le choix retenu — prudence assumée sur la surface qui juge toutes
# les autres — mais c'est une PRÉCAUTION, pas une obligation de la règle.
_linux_duree() {
  local _ld_t1 _ld_s
  [ -n "${LINUX_T0:-}" ] || return 0
  _ld_t1="$(date +%s 2>/dev/null)" || return 0
  _ld_s="$(expr "$_ld_t1" - "$LINUX_T0" 2>/dev/null)"
  # LE RC D `expr` N EST PAS UN CANAL DE MESURE, SON STDOUT L EST. POSIX impose
  # le statut 1 quand le RESULTAT vaut zero : le `|| return 0` d origine avalait
  # donc une mesure PARFAITEMENT LUE. Ce n est pas un cas d ecole — `docker run`
  # contre un demon injoignable echoue en 53 ms (mesure du binome), et c est le
  # FAIL le plus frequent de cette jambe. Il s imprimait sans duree, donc sous le
  # signal que ce fichier reserve a << l horloge n a pas pu etre lue >> : deux
  # etats distincts collapsaient sur un seul signal, l invariant meme qu on pose.
  [ -n "$_ld_s" ] || return 0
  # UNE DUREE NEGATIVE EST UN PAS NTP ARRIERE, PAS UNE MESURE. La valeur sert a
  # fixer un plafond ; une negative polluerait le releve. On se tait plutot.
  # PREMIERE CLAUSE SUR SA PROPRE LIGNE — forme imposee. `case X in motif)` sur
  # UNE seule ligne est l une des huit formes de bash VALIDE que le parseur du
  # SAST ne lit pas, et un seul site retire le FICHIER ENTIER du perimetre
  # inspecte. Je l avais ecrite ici meme, dans le fichier qui juge tous les
  # autres, en croyant l eviter — mesure apres coup : `PartialParsing` a cette
  # ligne exacte.
  case "$_ld_s" in
    -*) return 0 ;;
  esac
  printf ' (%ss)' "$_ld_s"
}

# _linux_pull_note — dit si la durée ci-dessus embarque un téléchargement d'image.
_linux_pull_note() {
  # PULLED NE S AFFIRME QUE SUR DEUX LECTURES : absente AVANT, presente APRES.
  # L etat AVANT seul ne suffit pas, parce qu un demon Docker injoignable fait
  # echouer `docker image inspect` AUSSI : << image absente >> et << demon
  # absent >> collapsaient sur la meme valeur. Mesure : sur un demon
  # injoignable, la ligne rendait `FAIL linux replay (0s), image PULLED` — un
  # telechargement de zero seconde, affirme dans le log que la doctrine oblige
  # a lire en entier, et qui DISQUALIFIE la mesure la plus propre (l echec
  # infra en 53 ms) alors que ce lot existe pour derive un plafond.
  # C est le collapsus a deux etats que `_linux_duree` vient de corriger, une
  # ligne plus haut, reproduit ici sans que je le voie.
  [ "${_LINUX_PULLED:-0}" = "1" ] || return 0
  docker image inspect "${IMAGE:-}" >/dev/null 2>&1 || return 0
  printf ', image PULLED (durée non comparable)'
  return 0
}

step() {  # step <label> <command...>
  local label="$1"; shift
  # PARALLEL MODE: the two kit runner steps are DEFERRED — their argv kept, nothing printed — and played
  # together by `jambes_jouer`. A CLOSED table of the two literal labels; any other step plays here.
  if [ "$JAMBES_MODE" = "parallele" ]; then
    case "$label" in
      "python -m pytest (CI scope, shards)") JAMBE_PY=("$@"); return 0 ;;
      "bash core-scripts/run-bash-tests.sh") JAMBE_SH=("$@"); return 0 ;;
    esac
  fi
  echo "=== $label"
  # FAIL-FAST (see CADRE_GATE_FAIL_FAST at the top): a step after a red is NOT
  # RUN, and says so on its own line. `failed` is never reset, so the verdict
  # below is unchanged; only the time after the first red is saved.
  if [ "$failed" -ne 0 ] && [ "$FF" != "0" ]; then
    echo "--- NOT RUN $label (échec rapide ; CADRE_GATE_FAIL_FAST=0 joue tout)"
    NOTRUN=$((NOTRUN + 1))
    echo
    return 0
  fi
  CHRONO_ACTIVE=1
  CHRONO_INFLIGHT=1
  # The runner's return channel for `--rouges`: a fresh file per step, passed as a PREFIX of this one
  # command (never exported to this shell); the two runners read then unset it before any child.
  rouges_tmp_dir
  ROUGES_N=$((ROUGES_N + 1))
  local rouges_f=""
  [ -z "$ROUGES_TMP" ] || rouges_f="$ROUGES_TMP/$ROUGES_N"
  CADRE_GATE_ROUGES_OUT="$rouges_f" "$@"
  local step_rc=$?
  CHRONO_INFLIGHT=0
  if [ "$step_rc" -eq 0 ]; then
    echo "--- PASS $label"
  else
    echo "--- FAIL $label (exit $step_rc)"
    noter_rouge "$label" "$rouges_f"
    failed=1
  fi
  echo
}

# _jambes_uint <value> — 0 iff a non-empty string of digits.
_jambes_uint() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
  esac
  return 0
}
# jambes_coeurs — the online cores, read like run-pytest-shards.sh's ncpu_online: getconf, then nproc,
# then sysctl; unreadable is 1, so `auto` falls back to the series.
jambes_coeurs() {
  local n=""
  if command -v getconf >/dev/null 2>&1; then n="$(getconf _NPROCESSORS_ONLN 2>/dev/null)"; fi
  if ! _jambes_uint "$n" && command -v nproc >/dev/null 2>&1; then n="$(nproc 2>/dev/null)"; fi
  if ! _jambes_uint "$n" && command -v sysctl >/dev/null 2>&1; then n="$(sysctl -n hw.ncpu 2>/dev/null)"; fi
  _jambes_uint "$n" || n=1
  printf '%s' "$n"
}
# jambes_decider — sets JAMBES_MODE from JAMBES (see CADRE_GATE_JAMBES at the top), on the kit's path only.
# Under `auto` and parallel, the bash leg gets CADRE_GATE_JOBS_BASH when exported, else min(4, cores/4) jobs
# (JAMBES_JOBS_BASH); pytest keeps its own.
jambes_decider() {
  case "$JAMBES" in
    serie)
      JAMBES_MODE=serie; return 0 ;;
    parallele)
      JAMBES_MODE=parallele; return 0 ;;
  esac
  JAMBES_MODE=serie
  [ "$PORTE" = "kit" ] || return 0
  case "${CADRE_GATE_JOBS:-}" in
    ''|auto)
      : ;;
    *)
      return 0 ;;
  esac
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      return 0 ;;
  esac
  JAMBES_COEURS="$(jambes_coeurs)"
  [ "$JAMBES_COEURS" -ge 16 ] || return 0
  JAMBES_MODE=parallele
  # An exported CADRE_GATE_JOBS_BASH wins over min(4, cores/4); run-bash-tests.sh validates it (integer
  # <= 64, else rc 2, `auto` included) — one validator, never a second rule here.
  if [ -n "${CADRE_GATE_JOBS_BASH:-}" ]; then
    JAMBES_JOBS_BASH="$CADRE_GATE_JOBS_BASH"
  else
    JAMBES_JOBS_BASH=$((JAMBES_COEURS / 4))
    [ "$JAMBES_JOBS_BASH" -le 4 ] || JAMBES_JOBS_BASH=4
  fi
  return 0
}
# jambes_interrompre <rc> — Ctrl-C (130), HUP (129), or a pytest leg that came back 130/143: the background
# leg ignores SIGINT (an asynchronous job of a non-interactive shell), so it is TERMed and reaped HERE,
# then the run exits with <rc>. CHRONO_INFLIGHT is still 1: no journal row, no stamp.
jambes_interrompre() {
  trap '' INT HUP
  if [ -n "${JAMBE_PID:-}" ]; then
    kill -TERM "$JAMBE_PID" 2>/dev/null
    wait "$JAMBE_PID" 2>/dev/null
    JAMBE_PID=""
  fi
  exit "$1"
}
# jambes_verdict <label> <rc> <argv count> — the `--- PASS|FAIL` line of one leg, and its red noted. A leg
# with an EMPTY argv was never played: rc 127, said so, never a PASS.
jambes_verdict() {
  if [ "$3" -eq 0 ]; then
    echo "--- FAIL $1 (exit 127 : jambe vide)"
    noter_rouge "$1"
    failed=1
  elif [ "$2" -eq 0 ]; then
    echo "--- PASS $1"
  else
    echo "--- FAIL $1 (exit $2)"
    noter_rouge "$1" "${4:-}"
    failed=1
  fi
  echo
}
# jambes_jouer — plays the two deferred legs TOGETHER (a no-op in series). bash in the background, its
# output (stderr merged) into `$ROUGES_TMP/jambe-bash.log`, which verify_on_exit removes with ROUGES_TMP;
# pytest in the foreground, streamed. The journal keeps the series' order — the pytest block, then the
# bash block — and the reds are noted pytest first. Each leg's rc is the `wait` on ITS pid; a missing pid
# is 127. The fail-fast applies as in series: a red pytest leg stops the bash leg (NOT RUN), then the steps
# AFTER the two legs. Without a temporary directory there is
# nowhere to hold the bash leg's output: the two legs then play in series, and the line says so.
jambes_jouer() {
  [ "$JAMBES_MODE" = "parallele" ] || return 0
  local l_py="python -m pytest (CI scope, shards)" l_sh="bash core-scripts/run-bash-tests.sh"
  local n_py="${#JAMBE_PY[@]}" n_sh="${#JAMBE_SH[@]}" f_py="" f_sh="" log rc_py=127 rc
  rouges_tmp_dir
  if [ -z "$ROUGES_TMP" ]; then
    echo "porte: jambes en série (aucun dossier temporaire pour la sortie de la jambe bash)"
    JAMBES_MODE=serie
    if [ "$n_py" -gt 0 ]; then step "$l_py" "${JAMBE_PY[@]}"; else jambes_verdict "$l_py" 127 0; fi
    if [ "$n_sh" -gt 0 ]; then step "$l_sh" "${JAMBE_SH[@]}"; else jambes_verdict "$l_sh" 127 0; fi
    return 0
  fi
  log="$ROUGES_TMP/jambe-bash.log"
  if [ -n "$JAMBES_JOBS_BASH" ]; then
    echo "porte: jambes en parallèle (pytest ∥ bash, $JAMBES_COEURS cœurs, jambe bash à $JAMBES_JOBS_BASH jobs ; CADRE_GATE_JAMBES=serie rend la série)"
  else
    echo "porte: jambes en parallèle (pytest ∥ bash, CADRE_GATE_JAMBES=parallele ; CADRE_GATE_JAMBES=serie rend la série)"
  fi
  echo
  CHRONO_ACTIVE=1
  CHRONO_INFLIGHT=1
  ROUGES_N=$((ROUGES_N + 1))
  f_py="$ROUGES_TMP/$ROUGES_N"
  ROUGES_N=$((ROUGES_N + 1))
  f_sh="$ROUGES_TMP/$ROUGES_N"
  trap 'jambes_interrompre 130' INT
  trap 'jambes_interrompre 129' HUP
  if [ "$n_sh" -gt 0 ]; then
    if [ -n "$JAMBES_JOBS_BASH" ]; then
      CADRE_GATE_ROUGES_OUT="$f_sh" CADRE_GATE_JOBS_BASH="$JAMBES_JOBS_BASH" "${JAMBE_SH[@]}" > "$log" 2>&1 &
    else
      CADRE_GATE_ROUGES_OUT="$f_sh" "${JAMBE_SH[@]}" > "$log" 2>&1 &
    fi
    JAMBE_PID=$!
  fi
  echo "=== $l_py"
  if [ "$n_py" -gt 0 ]; then
    CADRE_GATE_ROUGES_OUT="$f_py" "${JAMBE_PY[@]}"
    rc_py=$?
  fi
  case "$rc_py" in
    130|143)
      jambes_interrompre "$rc_py" ;;
  esac
  jambes_verdict "$l_py" "$rc_py" "$n_py" "$f_py"
  # FAIL-FAST, as in series: a red pytest leg stops the bash leg — TERMed, reaped, its log dropped, and the
  # leg announced NOT RUN (never a PASS, never awaited). CADRE_GATE_FAIL_FAST=0 plays both to the end.
  if [ "$rc_py" -ne 0 ] && [ "$FF" != "0" ] && [ -n "$JAMBE_PID" ]; then
    kill -TERM "$JAMBE_PID" 2>/dev/null
    wait "$JAMBE_PID" 2>/dev/null
    JAMBE_PID=""
    trap - INT HUP
    rm -f "$log"
    CHRONO_INFLIGHT=0
    echo "=== $l_sh"
    echo "--- NOT RUN $l_sh (échec rapide ; CADRE_GATE_FAIL_FAST=0 joue tout)"
    NOTRUN=$((NOTRUN + 1))
    echo
    return 0
  fi
  if [ -n "$JAMBE_PID" ]; then wait "$JAMBE_PID"; rc=$?; JAMBE_PID=""; else rc=127; fi
  trap - INT HUP
  echo "=== $l_sh"
  if [ -f "$log" ]; then cat "$log"; fi
  rm -f "$log"
  jambes_verdict "$l_sh" "$rc" "$n_sh" "$f_sh"
  # Cleared only once the bash verdict is written: a TERM during the `cat` above leaves no green row.
  CHRONO_INFLIGHT=0
  return 0
}

PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then
  echo "no python interpreter on PATH" >&2
  exit 1
fi

echo "Host verification ($("$PY" --version 2>&1), $(uname -s 2>/dev/null || echo windows))"
# The mode, decided on THIS tree and printed — under `--at` this is the frozen
# clone's own copy speaking about the clone (T-00001183).
PORTE="$(porte_mode "$ROOT")"
echo "porte: $PORTE (adoptant iff .agents/IS_THE_KIT absent and .agents/security/module_discovery.py present)"
echo
if [ "$PORTE" = "adoptant" ]; then
  # ONE step: the project's modules and submodules, built and tested, plus the
  # guards over the whole tree. Its absence is RED, named — never a fall back
  # onto the kit's suite, which is not this project's verdict.
  if [ -f "$ROOT/.agents/bin/porte_adoptant.py" ]; then
    step "porte adoptant" "$PY" .agents/bin/porte_adoptant.py
  else
    echo "=== porte adoptant"
    echo "--- FAIL porte adoptant: .agents/bin/porte_adoptant.py is ABSENT — this project's gate does not exist here, RED"
    echo "    remède : synchroniser .agents/bin/porte_adoptant.py avec core-scripts/verify.sh (même commit du kit)"
    noter_rouge "porte adoptant"
    failed=1
    echo
  fi
else
# The kit's three steps stay at column 0, byte for byte: the plan pins them word
# for word, and check-ci-parity.test.sh slices them by `^step`.
# The legs (CADRE_GATE_JAMBES at the top): decided here, on the kit's path; in parallel the first two steps
# are deferred and `jambes_jouer` plays them together — a line that does not start with `step`.
jambes_decider
# Same scope as CI (the bare collection: pytest.ini owns it), played here in parallel units (T-00001122).
step "python -m pytest (CI scope, shards)" bash core-scripts/run-pytest-shards.sh
step "bash core-scripts/run-bash-tests.sh" bash core-scripts/run-bash-tests.sh
jambes_jouer
# La correction du shell — le trou entre `bash -n` (syntaxe seule) et `semgrep`
# (motifs de sécurité). Sans shellcheck sur le PATH : `COVERAGE DEGRADED` et
# exit 0, jamais un faux propre. Détail de l'arbitrage de configuration en tête
# de `.agents/security/shellcheck-scan.sh`.
step "bash .agents/security/shellcheck-scan.sh" bash .agents/security/shellcheck-scan.sh
fi

if [ "$LINUX" -eq 1 ] && [ "$PORTE" = "adoptant" ]; then
  # NO OBJECT in adoptant mode, and no docker call: the container leg replays
  # the KIT's suite (pytest + bash suites), which is not this project's verdict.
  echo "=== linux replay: no object in adoptant mode (it replays the kit's suite) — docker not called, stamp linux=0"
  echo
elif [ "$LINUX" -eq 1 ] && [ "$failed" -ne 0 ] && [ "$FF" != "0" ]; then
  # FAIL-FAST at the scale of the legs: a host leg is already red, so the verdict
  # is already red — the container leg would cost minutes to say nothing new.
  # Placed AFTER the adoptant branch (which never calls docker anyway). The
  # container does NOT receive the setting: inside it, « Both legs ALWAYS run »
  # stays the decided semantics.
  echo "=== linux replay NOT RUN (échec rapide ; CADRE_GATE_FAIL_FAST=0 joue tout)"
  NOTRUN=$((NOTRUN + 1))
  echo
elif [ "$LINUX" -eq 1 ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "=== linux replay SKIPPED: docker not on PATH" >&2
    echo "    (a Windows-only run cannot see POSIX-specific failures)" >&2
    noter_rouge "linux replay"
    failed=1
  else
    echo "=== linux replay (ubuntu image, same deps as the runner)"
    # Mounted read-only would break pytest's cache and the suites' temp writes,
    # so the tree is mounted read-write but the container is thrown away. The
    # apt list and the image tag are EXTRACTED from ci.yml below (D3/D4), not
    # hardcoded: a second copy is a copy that drifts. ci.yml installs
    # `universal-ctags jq`; this leg ADDS `RUNNER_PREINSTALLED` — what the CI leg
    # ALREADY HAS and `python:*-slim` does not — shipped by `ubuntu-latest`
    # (git, nodejs, npm, procps). There USED to be a second route, `--with-deps`
    # under `armed_by=ci` bringing the Chromium shared libraries; T-00000505
    # withdrew the UI gate, so that route and its 21 packages are gone and the
    # label covers the whole list again. A replay
    # without npm is NOT the runner: `events-wiring.test.sh` asserts the npm SCA
    # leg reaches "scanned", which silently degrades to "degraded" with no npm
    # on PATH. Measured: absent npm the bash leg fails here and passes in CI,
    # i.e. the replay lied in the direction that costs the most (a red gate
    # nobody can reproduce upstream). core-scripts/check-ci-parity.sh detects the
    # test-command drift the extraction cannot make impossible (D1/D2/D5).
    # Two Git-Bash/MSYS traps on the same command line:
    #  - `pwd` yields /c/... which the Docker daemon cannot resolve, so the
    #    native form from `pwd -W` is used for the mount source;
    #  - MSYS rewrites container-side absolute paths as if they were host paths,
    #    turning `-w /repo` into `C:/Program Files/Git/repo`. MSYS_NO_PATHCONV=1
    #    disables that rewriting for this one call.
    HOSTPATH="$(pwd -W 2>/dev/null || pwd)"
    # The Python deps are EXTRACTED from ci.yml's own hash-pinned heredoc, not
    # listed here: a second copy is a copy that drifts, and this leg once
    # installed only pip+pytest while CI installed pydantic too — the replay
    # went red on imports CI resolves, a false negative anchored to a SHA
    # (T-00000155). The guard below refuses an empty extraction: a replay that
    # silently installs nothing would lie green-side next time ci.yml moves.
    CI_REQS=".verify-ci-requirements.txt"
    sed -n 's/^[[:space:]]*\([A-Za-z0-9_.-]\{1,\}[=;].*--hash=.*\)$/\1/p' \
      .github/workflows/ci.yml > "$CI_REQS"
    if ! grep -q -- '--hash=' "$CI_REQS"; then
      echo "FATAL: could not extract the hash-pinned requirements from .github/workflows/ci.yml" >&2
      rm -f "$CI_REQS"
      exit 1
    fi

    # D4 — the apt package list is EXTRACTED from ci.yml's own install line, the
    # same discipline as CI_REQS above. Full-comment lines are stripped FIRST so
    # the header prose that MENTIONS `apt-get install` cannot poison the match;
    # then the packages that follow `apt-get install -y` are taken. An empty
    # extraction is FATAL: a replay that installed nothing would lie green-side
    # the next time ci.yml moves. RUNNER_PREINSTALLED is the NAMED supplement the
    # CI leg already has — shipped by `ubuntu-latest` — and that `python:*-slim`
    # lacks; never a silent extra.
    # >>> apt-extract-validate (D4 + D4-SEC) — sliced verbatim and executed by
    #     core-scripts/check-ci-parity.test.sh; keep the markers so the test runs THESE
    #     bytes, not a copy that could drift.
    CI_APT="$(sed -E 's/^[[:space:]]*#.*$//' .github/workflows/ci.yml \
      | sed -n -E 's/^[[:space:]]*(sudo[[:space:]]+)?apt-get[[:space:]]+install[[:space:]]+-y[[:space:]]+(.+)$/\2/p' \
      | head -1)"
    if [ -z "$CI_APT" ]; then
      echo "FATAL: could not extract the apt package list from .github/workflows/ci.yml" >&2
      rm -f "$CI_REQS"
      exit 1
    fi
    # D4-SEC (CWE-78) — every token crosses into the container as $APT_PKGS and is
    # word-split there, so BOUND it to the Debian package-name charset BEFORE any
    # use. A metacharacter smuggled into ci.yml's `apt-get install -y` line
    # (`;`, `$(...)`, backtick, newline, redirection) is a token that fails this
    # bound and is REFUSED here — same FATAL discipline as the anti-empty guards
    # around it — so it can never reach the `bash -c` parser below. Defence in
    # depth: the docker leg no longer splices this value into the script text.
    for _apt_tok in $CI_APT; do
      case "$_apt_tok" in
        [!A-Za-z0-9]* | *[!A-Za-z0-9.+:-]*)
          echo "FATAL: refusing apt token from .github/workflows/ci.yml — not a Debian package name (CWE-78 guard): [$_apt_tok]" >&2
          rm -f "$CI_REQS"
          exit 1 ;;
      esac
    done
    # <<< apt-extract-validate
    # `procps` provides `ps`, and it is INSTALLED rather than declared
    # `# allows-missing:` because two suites BRANCH on its output — the criterion
    # is in `core-scripts/run-bash-tests.sh`: link what a decision depends on, declare
    # what has only an effect. `run-bash-tests.test.sh` counts surviving
    # grandchildren from `ps -ef`; `night_keepawake.test.sh` probes `ps -o args=`
    # and carries a whole branch for a host where it is mute, asserting a closed
    # refusal. Declaring it would pin that blindness as intended.
    # THE 21 CHROMIUM SHARED LIBRARIES THAT USED TO SIT IN THIS LIST ARE GONE
    # (T-00000505). They were here for ONE reason and one only: the UI gate could
    # never take the `ci` route inside this container — the `docker run` below
    # passes ONLY the `-e` it names (APT_PKGS, CADRE_GATE_JOBS,
    # CADRE_GATE_DURATIONS_DIR), so `GITHUB_ACTIONS` never enters — and Playwright
    # therefore installed a browser whose libraries `python:*-slim` does not
    # carry. With the gate withdrawn, this leg launches NO browser, so those 21
    # entries had no remaining consumer and were pure cost paid on every
    # `--linux` run. They are not replaced by anything.
    #
    # WHAT SURVIVES, AND WHY EACH ONE — the list is short enough to justify per
    # entry rather than by label, which is what the removal above made possible:
    #   git     : the container runs `git config --global --add safe.directory`
    #             below, and many suites shell out to `git`.
    #   nodejs  : `core-scripts/cadre.test.sh` parses the showcase page with node, and
    #             SKIPS by name when node is absent — a replay without it would
    #             quietly drop that check.
    #   npm     : the reason stated above — `events-wiring.test.sh` asserts the
    #             npm SCA leg reaches "scanned", which degrades to "degraded"
    #             with no npm on PATH. NOT a UI dependency; it long predates the
    #             gate and outlives it.
    #   procps  : `ps`, per the paragraph just above.
    # If Chromium ever comes back to this leg, regenerate its libraries rather
    # than restoring the deleted literal: in this image, against `.agents/ui-src`,
    #     npm ci --ignore-scripts
    #     ./node_modules/.bin/playwright install-deps --dry-run chromium
    # and copy the `chromium` array of Playwright's nativeDeps table for the
    # container's distro key.
    #   le paquet shellcheck : AJOUTÉ le 2026-09-13 (T-00000574). Un commentaire
    #     qui COMMENCE par le mot « shellcheck » est lu comme une DIRECTIVE et
    #     casse le parseur (SC1073/SC1072) — mesuré sur cette ligne même, par le
    #     scan que cette modification vient de rendre effectif. Sans ce paquet,
    #     `.agents/security/shellcheck-scan.sh` rend `COVERAGE DEGRADED` et
    #     **exit 0** dans le conteneur — la jambe annonçait donc `rc=0` sur une
    #     population qu'elle n'avait jamais lue, et le verdict global disait
    #     « vert, jambe conteneur incluse ». Mesuré dans le log de la porte du
    #     2026-09-12. Sur CE poste la jambe hôte le mesurait (shellcheck présent),
    #     mais faire dépendre la couverture de l'outillage du poste, c'est la
    #     perdre chez le premier adoptant qui ne l'a pas.
    RUNNER_PREINSTALLED="git nodejs npm procps shellcheck"  # preinstalled on ubuntu-latest, absent from python:*-slim
    APT_PKGS="$CI_APT $RUNNER_PREINSTALLED"

    # D3 — the image tag is DERIVED from ci.yml's `python-version:`, so the
    # docker leg tracks the interpreter CI pins instead of a floating `3-slim`.
    # Empty extraction is FATAL; a tag CI never named would fail `docker pull`
    # LOUDLY, which is the safe direction.
    CI_PYVER="$(sed -E 's/^[[:space:]]*#.*$//' .github/workflows/ci.yml \
      | sed -n -E 's/^[[:space:]]*python-version:[[:space:]]*"?([0-9]+(\.[0-9]+)*)"?.*$/\1/p' \
      | head -1)"
    if [ -z "$CI_PYVER" ]; then
      echo "FATAL: could not extract python-version from .github/workflows/ci.yml" >&2
      rm -f "$CI_REQS"
      exit 1
    fi
    IMAGE="python:${CI_PYVER}-slim"

    # CHRONOMÈTRE DE LA JAMBE CONTENEUR — T-00000611, et il PRÉCÈDE le plafond.
    # Le pilote a tranché le COMPORTEMENT au dépassement (COVERAGE DEGRADED +
    # exit 0, jamais failed=1 : un incident réseau ne doit pas produire un rouge
    # non attribuable au commit). LA VALEUR du plafond, elle, n'était pas
    # décidable : aucun relevé de la durée nominale n'existait, cette jambe
    # n'ayant jamais été chronométrée. Poser un `timeout` sur un nombre inventé
    # aurait fabriqué des faux rouges ou n'aurait rien borné du tout — les deux
    # étant pires que l'absence de garde.
    #
    # CE BLOC NE BORNE DONC RIEN. Il MESURE, et il écrit la durée dans le log
    # que la doctrine oblige déjà à lire en entier. Deux ou trois portes
    # suffiront à donner une durée nominale, et c'est ELLE qui fixera le
    # plafond — pas une intuition.
    #
    # `date +%s` plutôt que `$SECONDS` : ce script tourne aussi sous des shells
    # où `SECONDS` n'est pas garanti, et la valeur doit survivre au sous-shell
    # du `if`. Entiers seuls, donc aucune arithmétique parenthésée — forme
    # interdite ici, le parseur du SAST ne la lit pas.
    # LE PREMIER RELEVÉ INCLUT LE `docker pull` DE L'IMAGE, et il faut le DIRE :
    # cette durée existe pour dériver un plafond, et un relevé qui embarque un
    # téléchargement n'est pas comparable aux suivants. On ne pré-chauffe pas —
    # ce serait masquer un coût réel de la porte — on ANNONCE.
    _LINUX_PULLED=1
    docker image inspect "$IMAGE" >/dev/null 2>&1 && _LINUX_PULLED=0
    LINUX_T0="$(date +%s 2>/dev/null)" || LINUX_T0=""

    # $APT_PKGS crosses as a container ENV var, NOT spliced into the script text:
    # closing the single quote to interpolate it would hand its value to the
    # inner `bash -c` as SYNTAX to re-parse (CWE-78). Referenced UNQUOTED inside
    # the single-quoted body on purpose — the word-splitting into one arg per
    # package is intended — but it is no longer re-parsed, and D4-SEC above has
    # already bounded every token to a package-name charset.
    # CADRE_GATE_DURATIONS_DIR crosses as a FIXED path INSIDE the container, outside
    # /repo: the tree is mounted read-write, and the two runners' default table is
    # /repo/.agents/state/local/porte-durees — under a bare `--linux` (no --at) that
    # is the LIVE tree, which the container (root) filled with Linux durations the
    # host runners then read as their own. /tmp/porte-durees dies with `--rm`.
    if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
       docker run --rm -e APT_PKGS="$APT_PKGS" -e CADRE_GATE_JOBS="${CADRE_GATE_JOBS:-1}" -e CADRE_GATE_DURATIONS_DIR=/tmp/porte-durees -v "$HOSTPATH:/repo" -w /repo "$IMAGE" bash -c '
        set -e
        apt-get update -qq >/dev/null
        apt-get install -y -qq --no-install-recommends $APT_PKGS >/dev/null
        git config --global --add safe.directory /repo
        python -m pip install --quiet --require-hashes --only-binary :all: --disable-pip-version-check -r .verify-ci-requirements.txt
        set +e
        # Both legs ALWAYS run: under `set -e` a red pytest aborted the script
        # before the bash suites, so one failure hid the other and the bash leg
        # went unrun for as long as pytest was red. Each rc is kept and the
        # worst one is returned.
        echo "--- bash core-scripts/run-pytest-shards.sh"
        bash core-scripts/run-pytest-shards.sh
        rc_py=$?
        echo "--- bash core-scripts/run-bash-tests.sh"
        bash core-scripts/run-bash-tests.sh
        rc_sh=$?
        echo "--- bash .agents/security/shellcheck-scan.sh"
        bash .agents/security/shellcheck-scan.sh
        rc_sc=$?
        echo "--- linux legs: pytest rc=$rc_py, bash rc=$rc_sh, shellcheck rc=$rc_sc"
        [ "$rc_py" -eq 0 ] && [ "$rc_sh" -eq 0 ] && [ "$rc_sc" -eq 0 ]
      '; then
      echo "--- PASS linux replay$(_linux_duree)$(_linux_pull_note)"
    else
      echo "--- FAIL linux replay$(_linux_duree)$(_linux_pull_note)"
      noter_rouge "linux replay"
      failed=1
    fi
    rm -f "$CI_REQS"
    echo
  fi
fi

# The verdict names the commit it covers: under --at that is the frozen SHA, on
# a live tree it is the current HEAD (informative — uncommitted work is NOT in
# it). Either way, what you may push is a SHA that came back green.
HEAD_SHORT="$(git rev-parse --short HEAD 2>/dev/null)" || HEAD_SHORT=""
[ -n "$HEAD_SHORT" ] || HEAD_SHORT="unknown"
# The stamp carries the FULL sha, never the short one: its reader compares it to
# the 40-hex `<local-sha>` git puts on a pre-push line, and an abbreviated form
# would never match.
HEAD_FULL="$(git rev-parse HEAD 2>/dev/null)" || HEAD_FULL=""

# ADOPTANT (T-00001183): a green step is not the verdict until the gate's return
# channel names THIS sha and says OK; and the `linux` bit is 0 in this mode.
STAMP_LINUX="$LINUX"
if [ "$PORTE" = "adoptant" ]; then
  STAMP_LINUX=0
  if [ "$failed" -eq 0 ]; then
    if [ -z "$HEAD_FULL" ] || ! porte_lire "$ROOT/.agents/state/local/PORTE_RESULT" "$HEAD_FULL"; then
      noter_rouge "porte adoptant (PORTE_RESULT)"
      failed=1
    fi
  fi
fi

if [ "$failed" -ne 0 ]; then
  stamp_clear
  rouges_ecrire "$HEAD_FULL" live
  hook_status_line
  if [ "$NOTRUN" -gt 0 ]; then
    echo "NOT RUN (fail-fast=$FF): $NOTRUN step(s) — the failure list is NOT complete"
  fi
  echo "VERIFY FAILED @ $HEAD_SHORT — do not push."
  exit 1
fi
if [ -n "$HEAD_FULL" ]; then
  stamp_write "$HEAD_FULL" live "$STAMP_LINUX"
else
  stamp_clear
fi
hook_status_line
echo "VERIFY OK @ $HEAD_SHORT — this is what CI will run."
