#!/usr/bin/env bash
# .agents/security/sca-scan.sh — kit-adapted from security-agents-pack-v2.
# Read-only, multi-ecosystem SCA dispatcher for the security agents and hooks.
#
# Call forms (T-008):
#   sca-scan.sh                 hook/watch path — scan the repo root, reports in
#                               .agents/state/local/sca-reports/ (behavior unchanged from T-007)
#   sca-scan.sh <module-dir>    scan ONE module; reports in .agents/state/local/sca-reports/modules/<slug>/
#                               (exception: the repo root itself reports at the root of sca-reports/,
#                               never modules/root/ — T-00000291; summary.json entries carry the true
#                               path in `reports_dir`)
#   sca-scan.sh --all-modules   discover modules (module_discovery.py: ancestor
#                               collapse for maven/gradle reactors and npm
#                               workspaces), loop the single-module form, write
#                               .agents/state/local/sca-reports/modules/summary.json
#
# - Never mutates the working tree (npm audit runs --package-lock-only;
#   pip-audit runs --no-deps, so it never resolves or builds a dependency set).
#   Python LOCKFILES ARE READ, RANGES ARE REFUSED (T-00000462): poetry.lock,
#   uv.lock and Pipfile.lock already hold exact versions, so py_lock_pins.py
#   TRANSLATES them into pins — no network, no build. `pyproject.toml` and
#   `Pipfile` alone carry RANGES, which only a resolution could pin, so they
#   stay refused and NAMED. Any entry dropped from the audit scope is COUNTED
#   and written on the NOMINAL path, separated by motive (L-00000388).
# - Ecosystems SCANNED: npm, Maven, Gradle, Swift (Package.resolved only — a Podfile.lock alone is NOT scanned), Python (pip-audit,
#   T-00000292) — dependency CVEs (T-008)
#   plus IaC misconfiguration via trivy config (Dockerfile/Terraform/K8s/Helm,
#   T-004 shard 3) — the latter has no single manifest to gate detection on;
#   see the trivy block below.
# - NOT scanned but NAMED when their manifest is present AT THE ROOT LOOKED AT
#   (module root, or repo root on the no-module path of --all-modules): Go, Rust,
#   .NET/C# (csproj/sln down to depth 3), PHP, Ruby (T-00000488:
#   `<eco>: ecosystem not covered in v1`, status `degraded`, never a block, never
#   `scanned`; a manifest in a sub-folder that is not a discovered module is NOT
#   seen; under the hook (SCA_CHANGED_ONLY=1) a change to one of these TRACKED
#   manifests wakes the scan, which names it — a NEW manifest not yet `git add`ed is skipped).
# - Effective gate through waiver_filter.py (repo-level waiver register).
# - Appends one audit line per run to .agents/state/local/sca-reports/audit-log.jsonl.
# - Exit: 0 = effective GO ; 1 = effective NO-GO ; 2 = no ecosystem detected.
#   1 also covers the NO-GO that carry NO verdict at all (fail-closed): a module
#   run of --all-modules that exited outside {0,1,2}, with 2 without its
#   no-ecosystem line, with 1 on a `no verdict obtained` line, or with 1 on
#   waiver_filter's rc=3 line (a scanner report unreadable: gating even in a
#   PROTECTED module — E1); the reports lock
#   held beyond SCA_LOCK_WAIT_SECONDS (a decimal 0..3600 written without a leading
#   zero; anything else: the default); the reports directory not writable; and a
#   run that bash cut short before its verdict (see run_aborted).
#   EXCEPT under SCA_CHANGED_ONLY=1 (hook context): "no ecosystem" exits 0 —
#   Claude Code treats hook exit 2 as a BLOCKING error, which turns the benign
#   "nothing to scan" case into an infinite Stop-hook loop.
set -uo pipefail

# ---- SORTIE PRÉCOCE SOUS COPILOT : LECTURE LOCALE (T-01M4RWC6VHHN479J2A9RRY1BE3)
# Sous AGENTS_HOOK_HOST=copilot SEULEMENT, et sur la seule forme du hook
# (SCA_CHANGED_ONLY=1, aucun argument) : un outil de lecture locale, identifié
# POSITIVEMENT par son nom de premier niveau, ne touche aucun manifeste et sort
# avant tout git, mktemp ou mkdir. Définie ICI, appelée juste après la
# résolution de PY : la fenêtre qui suit le diagnostic « PYTHON 3 NOT FOUND »
# reste celle qu'épingle .agents/evals/test_python_hook_launchers.py. Le nom est
# lu et comparé DANS python, sur la liste OUTILS_LECTURE_COPILOT, copie jumelle
# de celle de .codex/hooks/_common.py (filet :
# .agents/evals/test_copilot_early_exit.py) ; jamais relu comme du shell. Tout
# le reste — l'agentStop (aucun outil), forme groupée ou HYBRIDE (`toolCalls`
# ou `tool_calls` à côté d'un nom listé : un second outil), graphies du nom en
# désaccord, nom vide ou inconnu, charge illisible, python absent, stdin
# terminal — suit le chemin entier, inchangé. La charge, lue sous copilot
# seulement, est réinjectée sur stdin quand le nom n'est pas listé.
sortie_precoce_copilot() {  # "$@" = les arguments du script
  local forme=0 charge
  [ "$#" -eq 0 ] && [ "${SCA_CHANGED_ONLY:-0}" = "1" ] && forme=1
  case "${AGENTS_HOOK_HOST:-}" in
    copilot)
      if [ "$forme" = 1 ] && [ -n "$PY" ] && [ ! -t 0 ]; then
        charge="$(cat; printf x)"
        charge="${charge%x}"
        if printf '%s' "$charge" | "$PY" -c '
# >>> OUTILS_LECTURE_COPILOT (bloc jumeau, 5 copies : test_copilot_early_exit.py)
# Outils de LECTURE LOCALE sous Copilot : leurs arguments ne sortent pas du
# processus local. Liste POSITIVE et close, comparee au nom de premier niveau
# replie (minuscules, espaces otes, tiret vers souligne) ; tout autre nom est
# juge. Les noms exclus, et leur motif : EXCLUS_DE_LA_LISTE du filet.
OUTILS_LECTURE_COPILOT = (
    "view",  # Copilot CLI, mesure (M-P9) : path, view_range
    "grep",  # Copilot CLI, mesure (M-P9) : pattern, paths, output_mode
    "read_agent",  # Copilot CLI, mesure (M-P9) : agent_id, since_turn
    "list_agents",  # Copilot CLI, mesure (M-P9) : include_completed
    "read_file",  # Chat Local, documente, non mesure (U8)
    "file_search",  # Chat Local, documente, non mesure (U8)
    "grep_search",  # Chat Local, documente, non mesure (U8)
    "list_dir",  # Chat Local, documente, non mesure (U8)
)
# <<< OUTILS_LECTURE_COPILOT
import json, sys
try:
    p = json.loads(sys.stdin.read())
except Exception:
    sys.exit(1)
noms = []
if isinstance(p, dict) and "toolCalls" not in p and "tool_calls" not in p:
    for k in ("toolName", "tool_name", "tool", "name"):
        if p.get(k):
            noms.append(str(p[k]).strip().lower().replace("-", "_"))
sys.exit(0 if len(set(noms)) == 1 and noms[0] in OUTILS_LECTURE_COPILOT else 1)
' >/dev/null 2>&1; then
          exit 0
        fi
        # Réinjection par here-string SANS numéro de descripteur (la graphie à
        # descripteur est illisible du SAST), jamais par substitution de
        # processus : test_copilot_early_exit.py (v). Aucun lecteur de stdin en
        # aval ici : un échec de la redirection ne change aucun verdict.
        exec <<<"$charge"
      fi
      ;;
  esac
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY=""
PY_PROBE='import sys; sys.stdout.write(sys.executable); sys.exit(sys.version_info[0] != 3)'
PY_CR="$(printf '\r')"
for c in python3 python; do
  PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
  case "$PY_CANDIDATE" in
    *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
  esac
  if [ -n "$PY_CANDIDATE" ]; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  PY_UNAME=""
  command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"
  case "${OS-}:$PY_UNAME" in
    Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
      PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
      case "$PY_CANDIDATE" in
        *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
      esac
      [ -n "$PY_CANDIDATE" ] && PY="$PY_CANDIDATE"
      ;;
  esac
fi
[ -n "$PY" ] || echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
sortie_precoce_copilot "$@"   # avant tout git, mktemp ou mkdir (définie plus haut)
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ROOT="$(cd "$ROOT" && pwd)"            # canonicalize (Git Bash: git prints C:/..., pwd prints /c/...)
GATE_LEVEL="${SCA_GATE_LEVEL:-high}"   # high | critical
CHANGED_ONLY="${SCA_CHANGED_ONLY:-0}"  # 1 = skip if no manifest changed vs HEAD
WAIVERS="$ROOT/.agents/security/sca-waivers.json"

SOCKET_TIMEOUT_RAW="${SCA_SOCKET_TIMEOUT_SECONDS:-60}"
if [[ "$SOCKET_TIMEOUT_RAW" =~ ^[0-9]+$ ]] &&
   [ "${#SOCKET_TIMEOUT_RAW}" -le 3 ] &&
   [ "$SOCKET_TIMEOUT_RAW" -ge 1 ] && [ "$SOCKET_TIMEOUT_RAW" -le 900 ]; then
  # `10#$X` était la notation qui force la base 10 (pour qu'un « 08 » ne soit
  # pas lu en octal). tree-sitter-bash ne parse PAS `10#$X` — et ici ça ne
  # produisait pas un parse partiel mais un `Syntax error` COMPLET, retirant ce
  # fichier ENTIER du compte des cibles inspectées par la porte SAST.
  # `[ … -ge … ]` compare en DÉCIMAL, donc sans le piège de l'octal : vérifié
  # sur 08, 09, 007, 60 et 900 — mêmes verdicts qu'avec `10#`.
  SOCKET_TIMEOUT_SECONDS="$SOCKET_TIMEOUT_RAW"
else
  SOCKET_TIMEOUT_SECONDS=60
  log_pending_socket_timeout="invalid SCA_SOCKET_TIMEOUT_SECONDS value; using 60 seconds"
fi

have() { command -v "$1" >/dev/null 2>&1; }
log()  { printf '  %s\n' "$*"; }
[ -n "${log_pending_socket_timeout:-}" ] && log "[npm] $log_pending_socket_timeout"

# ---- Dev dependencies: audited in the KIT's own repos, not at consumers ------
# Pilot decision, 2026-08-15 (T-00000199).
#
# MEASURED, and it is the whole reason this switch exists: on the exact
# package-lock that carried a HIGH advisory (nanoid < 3.3.18),
# `npm audit --package-lock-only --omit=dev` answered "found 0 vulnerabilities"
# rc=0, while the same command WITHOUT the flag answered "1 high severity
# vulnerability" rc=1. The flag — not the discovery blind spot closed by
# T-00000197 — is what hid it.
#
# The trade-off cuts both ways, so it is decided per REPOSITORY rather than
# once for everyone: a dev dependency never reaches a consumer's production,
# but a compromised BUILD chain is exactly the supply-chain risk this doctrine
# names in its class 3. The kit maintains its own build chain, so it audits it.
# A consumer project never asked for that toolchain and must not be gated on
# advisories it cannot act on.
#
# The opt-in is a FILE THAT DOES NOT TRAVEL: `strip:` in .template-exclude keeps
# it off the template branch, so it cannot reach an adopting project by
# accident. Same shape as `.agents/protected-paths.local` — the MECHANISM ships
# from main, the CONTENT lives only where it applies. To turn it on in another
# repo the kit is maintained from (op-agentic-builder), create the file there.
DEV_DEPS_OPTIN="$ROOT/.agents/security/audit-dev-deps.local"
if [ -n "${SCA_AUDIT_DEV_DEPS:-}" ]; then
  AUDIT_DEV="$SCA_AUDIT_DEV_DEPS"          # explicit override: tests, one-offs
  DEV_SRC="env SCA_AUDIT_DEV_DEPS"
elif [ -f "$DEV_DEPS_OPTIN" ]; then
  AUDIT_DEV=1
  DEV_SRC="audit-dev-deps.local"
else
  AUDIT_DEV=0
  DEV_SRC="default (no opt-in file)"
fi
if [ "$AUDIT_DEV" = "1" ]; then
  NPM_SCOPE=(); PNPM_SCOPE=()
  SCOPE_LABEL="dev dependencies INCLUDED"
else
  NPM_SCOPE=(--omit=dev); PNPM_SCOPE=(--prod)
  SCOPE_LABEL="production only (--omit=dev)"
fi
# Announced every run: a scope this narrow decided in silence reads, in the
# report, exactly like a scan that found nothing.
log "[npm] scope: $SCOPE_LABEL — $DEV_SRC"

# Optional throttle: for hooks, only run when a dependency manifest changed.
if [ "$CHANGED_ONLY" = "1" ] && git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
  if ! git -C "$ROOT" diff --name-only HEAD 2>/dev/null | \
       grep -Eq '(package(-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|pnpm-workspace\.yaml|pom\.xml|build\.gradle(\.kts)?|Package\.(swift|resolved)|Podfile(\.lock)?|requirements[^/]*\.txt|pyproject\.toml|Pipfile(\.lock)?|poetry\.lock|uv\.lock|Cargo\.(toml|lock)|go\.(mod|sum)|composer\.(json|lock)|Gemfile(\.lock)?|[^/]*\.(csproj|sln)$|Dockerfile[^/]*|\.tf(\.json)?$|\.tfvars(\.json)?$|\.terraform\.lock\.hcl$|docker-compose[^/]*\.ya?ml|(^|/)(k8s|kubernetes|manifests)/|Chart\.yaml)'; then
    echo "SCA: no dependency manifest / IaC file changed — skipping."; exit 0
  fi
fi

# ---- THE REPORTS LOCK, AND THE ONE EXIT TRAP (T-01M4Z39613YVM24WCTWB56N2TH) --
# MEASURED before this block: two runs on the same root shared
# .agents/state/local/sca-reports/ — run A held a HIGH, run B (clean) purged and
# rewrote the reports under it, and A answered GO rc 0, two audit rows GO. One
# run at a time now owns that directory: `mkdir "$L"` is the atomic claim, and
# `$L/owner` says who holds it (pid, host, start identity), written in ONE printf.
#
# EVERY VARIABLE cleanup() reads is assigned HERE, before the trap (set -u: an
# early exit — module dir not found, no Python, lock busy — would otherwise abort
# the cleanup on "unbound variable"). The one exception is its aborted row: ROOT,
# GATE_LEVEL_AUDIT, sanitize_display (and SLUG, scan mode only) are read there
# only on a HELD lock (lock_mine=1), set by lock_acquire after they all exist.
# This is the ONLY `trap … EXIT` of this
# file: a second one REPLACES this one, it does not chain (the trivy block below
# used to own a trap of its own; its temp file is now removed HERE).
ref=''; modlog=''; TRIVY_TMP=''; L=''; steal_held=0; lock_mine=0; lock_ok=0
sca_sig=0; LOCK_MODE=''
MY_PID=''; MY_HOST=''; MY_ST=''
LOCK_OS="$(uname -s 2>/dev/null)"
LOCK_RP=')'   # the stat parenthesis goes through a VALUE, never into the expansion syntax
cleanup() {
  # Only the shell that INSTALLED the trap runs it (L-00000146, the form of
  # semgrep-scan.sh's cleanup): a child that inherits it and is signalled before
  # its exec must not release the lock of a run still in progress. Inert on a
  # bash without BASHPID (3.2), where $$ cannot tell them apart.
  [ "${BASHPID:-$$}" = "$CLEANUP_OWNER" ] || return 0
  # A SECOND TERM or HUP must not cut this body short (GNU timeout signals the
  # run, then its group; a host may repeat its TERM). Measured before this line
  # (exec-critic, a `date` slowed in cleanup's `$(date …)`, arm (f5) of
  # sca-scan-lock.test.sh): the second TERM ran the trap INSIDE cleanup, its
  # `exit 143` ended the run there — .lock and the witness left, no aborted
  # row. Ignored from here on; the run is exiting anyway. KILL still cuts it.
  trap '' TERM HUP
  if [ "$steal_held" = 1 ]; then
    rmdir "$L.steal" 2>/dev/null
    steal_held=0
  fi
  # Released only if it is OURS, re-read on disk: a lock taken over by another
  # run (this one judged dead by mistake) is never removed from under it.
  if [ "$lock_mine" = 1 ]; then
    # A run cut by TERM or HUP (the traps below note it; F2b,
    # T-01M51YJ5GXM101STF0NM586RXN) writes ONE audit row `"reason":"aborted"`, in
    # the mode it took the lock for, BEFORE the release. Only the lock HOLDER
    # writes it: a re-entered module run of --all-modules and a waiter or thief
    # never set lock_mine. Measured before: `$?` is 0 in this trap after a
    # TERM or a HUP (3.2.57 and 5.3.15), so the signal is read from sca_sig,
    # never from a `rc > 128`. Its own printf, run_aborted not factored (that one
    # logs and exits). `${…:-}`: (f3) of sca-scan-lock.test.sh sources this body
    # ALONE, where neither variable is set. KILL and INT write nothing.
    if [ "${sca_sig:-0}" != 0 ]; then
      c_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      if [ "${LOCK_MODE:-}" = "all-modules" ]; then
        printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"NO-GO","reason":"aborted","gate_level":"%s"}\n' \
          "$c_ts" "${GATE_LEVEL_AUDIT:-}" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
      else
        printf '{"ts":"%s","mode":"scan","entry":"sca-scan.sh","module":"%s","verdict":"NO-GO","reason":"aborted","gate_level":"%s"}\n' \
          "$c_ts" "$(sanitize_display "${SLUG:-}")" "${GATE_LEVEL_AUDIT:-}" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
      fi
    fi
    c_pid=''; c_host=''
    { IFS= read -r c_pid && IFS= read -r c_host; } 2>/dev/null < "$L/owner"
    if [ "$c_pid" = "$MY_PID" ] && [ "$c_host" = "$MY_HOST" ]; then
      rm -r "$L" 2>/dev/null
    fi
    lock_mine=0
  fi
  [ -n "$ref" ] && rm -f "$ref"
  [ -n "$modlog" ] && rm -f "$modlog"
  [ -n "$TRIVY_TMP" ] && rm -f "$TRIVY_TMP"
  return 0
}
CLEANUP_OWNER="${BASHPID:-$$}"
trap cleanup EXIT
# TERM and HUP are NOTED, then the run exits with the signal's own code (143,
# 129): cleanup() above reads sca_sig and writes the `aborted` row. Bash runs
# such a trap only BETWEEN commands: a TERM sent to this process ALONE waits for
# the foreground command — under --all-modules, the module run in progress —
# and the lock stays held until then (measured before: the run died at once,
# released the lock while its module still ran, and that module then wrote its
# reports and its row without the lock). A TERM to the whole group is immediate.
# A subshell resets these traps (bash), so only this shell notes the signal.
trap 'sca_sig=143; exit 143' TERM
trap 'sca_sig=129; exit 129' HUP

# lock_start PID: the START identity of a process, or NOTHING. It only answers
# "is this the same process", against pid recycling — never "is it alive".
#   Linux: field 22 of /proc/<pid>/stat (ticks since boot). MEASURED: procps
#     derives `lstart` from btime, which moves when the clock jumps, and a live
#     holder would then read recycled and be stolen; the ticks do not move.
#   elsewhere: `ps -o lstart=` under LC_ALL=C TZ=UTC0 (MEASURED on macOS: a holder
#     started under TZ=Asia/Tokyo and a waiter under TZ=America/New_York read
#     two different lstart without TZ=UTC0). Git Bash/MSYS refuse `ps -o` and
#     answer nothing (T-00000410): the owner is then INDESCRIBABLE, never stolen.
lock_start() {
  local _ls
  case "$LOCK_OS" in
    Linux)
      _ls=''
      IFS= read -r _ls 2>/dev/null < "/proc/$1/stat" || return 0
      _ls=${_ls##*"$LOCK_RP" }
      set -- $_ls
      [ $# -ge 20 ] && printf 'ticks:%s\n' "${20}"
      ;;
    *)
      LC_ALL=C TZ=UTC0 ps -p "$1" -o lstart= 2>/dev/null
      ;;
  esac
  return 0
}

# lock_host: the HOST line of a lock owner. `uname -n`, never $HOSTNAME (inherited
# from the environment: `HOSTNAME=forged bash -c 'echo $HOSTNAME'` prints forged).
# On Linux the PID NAMESPACE is part of it (closing review T6): a holder in another
# pid namespace under the same hostname (a `--uts=host` container, the repo mounted
# in a container that carries the host's hostname) is invisible to `kill -0`, read
# dead, and was TAKEN OVER while alive. With `pid:[<inode>]` appended its lock reads
# foreign: lock-busy, never a theft. A `readlink` that answers nothing (no /proc)
# leaves the bare hostname — the former, open direction (README, « The reports lock »).
lock_host() {
  local _h _ns
  _h="$(uname -n 2>/dev/null)"
  [ -n "$_h" ] || _h='?'
  if [ "$LOCK_OS" = "Linux" ]; then
    _ns="$(readlink /proc/self/ns/pid 2>/dev/null)"
    [ -n "$_ns" ] && _h="$_h $_ns"
  fi
  printf '%s\n' "$_h"
  return 0
}

# lock_alive PID: 0 = alive (or cannot tell), 1 = dead. `kill -0` is the judge,
# never ps. Only `No such process` means dead (rc and text MEASURED under bash
# 3.2.57, 5.3.15 and Linux glibc in C); EPERM (another uid, pid 1), a localized
# or unknown text all read ALIVE — the closed direction: lock-busy, never a theft.
lock_alive() {
  local _m
  _m="$(export LC_ALL=C; kill -0 "$1" 2>&1)" && return 0
  case "$_m" in
    *'No such process'*) return 1 ;;
  esac
  return 0
}

# lock_read: $L/owner into o_pid / o_host / o_st, line by line, `IFS=` kept (the
# macOS lstart carries trailing spaces), NEVER evaluated. 1 = unreadable. The
# order `2>/dev/null <` is measured: the other one leaks "No such file".
lock_read() {
  o_pid=''; o_host=''; o_st=''
  { IFS= read -r o_pid && IFS= read -r o_host && IFS= read -r o_st; } 2>/dev/null < "$L/owner" || return 1
  case "$o_pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -n "$o_host" ]
}

# lock_judge: STATE = unreadable | foreign | dead | undescribed | recycled | held.
lock_judge() {
  local _now
  if ! lock_read; then
    o_pid=''; o_host=''; o_st=''
    STATE=unreadable
    return 0
  fi
  if [ "$o_host" != "$MY_HOST" ]; then STATE=foreign; return 0; fi
  if ! lock_alive "$o_pid"; then STATE=dead; return 0; fi
  if [ -z "$o_st" ]; then STATE=undescribed; return 0; fi
  _now="$(lock_start "$o_pid")"
  if [ -z "$_now" ]; then
    STATE=undescribed
  elif [ "$_now" = "$o_st" ]; then
    STATE=held
  else
    STATE=recycled
  fi
  return 0
}

# lock_busy MODE: the wait is over and the lock is not ours. NOTHING is written
# in the reports directory but ONE audit row; the remedy depends on the LAST
# judgement — a live, described holder is never to be removed, and a live one
# whose start cannot be described only once its pid is checked (closing review T4:
# the orphan-lock remedy used to be printed for it too).
lock_busy() {
  local _ts
  _ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$1" = "all-modules" ]; then
    printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"NO-GO","reason":"lock-busy","gate_level":"%s"}\n' \
      "$_ts" "$GATE_LEVEL_AUDIT" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
  else
    printf '{"ts":"%s","mode":"scan","entry":"sca-scan.sh","module":"%s","verdict":"NO-GO","reason":"lock-busy","gate_level":"%s"}\n' \
      "$_ts" "$(sanitize_display "$SLUG")" "$GATE_LEVEL_AUDIT" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
  fi
  log "SCA GATE (effective, waivers applied): NO-GO — reports lock held by pid ${o_pid:-?} beyond ${lock_wait}s, no verdict obtained (fail-closed)"
  if [ "$STATE" = "held" ]; then
    log "SCA: reports lock held by live pid ${o_pid} — re-run when it ends; do not remove the lock"
  elif [ "$STATE" = "undescribed" ]; then
    log "SCA: reports lock owner pid ${o_pid} is ALIVE (start not describable) — remove the lock only if pid ${o_pid} is not a sca-scan.sh: rm -r .agents/state/local/sca-reports/.lock"
  else
    log "SCA: if no sca-scan.sh is running, remove the orphan lock: rm -r .agents/state/local/sca-reports/.lock .agents/state/local/sca-reports/.lock.steal"
  fi
  exit 1
}

# lock_wait_valid V: 0 when V is a DECIMAL integer of 0..3600 written without a
# leading zero — `0`, or a digit 1-9 followed by at most three digits. `$(( ))`
# reads a leading zero as OCTAL. MEASURED with the former `^[0-9]+$` check, under
# 3.2.57 and 5.3.15: `09` passed it, `$((SECONDS + 09))` aborted, and bash DISCARDED
# lock_acquire — the run went on WITHOUT the lock (rc 0 GO, a live holder's pivot
# overwritten); `010` waited 8 s while announcing "010s".
lock_wait_valid() {
  case "$1" in
    0)
      return 0
      ;;
    [1-9] | [1-9][0-9] | [1-9][0-9][0-9] | [1-9][0-9][0-9][0-9])
      [ "$1" -le 3600 ]
      ;;
    *)
      return 1
      ;;
  esac
}

# lock_changed: 0 when the lock's date DIFFERS from the waiter's witness, NEWER or
# OLDER. `-nt` alone missed a replacement dated EARLIER than the first lock seen
# (MEASURED: a 2015 lock replacing a 2020 one kept the old grace). A witness that
# mktemp could not create reads changed while the lock exists: the grace restarts
# at every turn and nothing owner-less is ever stolen — the closed direction.
lock_changed() { [ "$L" -nt "$ref" ] || [ "$L" -ot "$ref" ]; }

# run_aborted MODE: the run reached a point it reaches ONLY when bash cut it short.
# An expansion error (`$((SECONDS + 09))`) DISCARDS the whole top-level command it
# sits in — MEASURED under 3.2.57 and 5.3.15: the rest of an `if` body, a `;` on
# the same line and a `||` branch included — and bash goes on with the NEXT one.
# So the proof is read on its own top-level line after each lock_acquire call
# (`lock_ok`, and the --all-modules block, which always ends in `exit`): no proof
# = NO-GO with no verdict, never a scan without the lock. ONE audit row, as
# lock_busy. Before it, `--all-modules` cut short fell to "module dir not found:
# --all-modules", rc 2 — the exit code of "no ecosystem", never a NO-GO.
run_aborted() {
  local _ts
  _ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$1" = "all-modules" ]; then
    printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"NO-GO","reason":"aborted","gate_level":"%s"}\n' \
      "$_ts" "$GATE_LEVEL_AUDIT" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
  else
    printf '{"ts":"%s","mode":"scan","entry":"sca-scan.sh","module":"%s","verdict":"NO-GO","reason":"aborted","gate_level":"%s"}\n' \
      "$_ts" "$(sanitize_display "$SLUG")" "$GATE_LEVEL_AUDIT" >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"
  fi
  log "SCA GATE (effective, waivers applied): NO-GO — run cut short by a shell error before its verdict, no verdict obtained (fail-closed)"
  log "SCA: re-run; the shell error is on stderr above"
  exit 1
}

# lock_acquire MODE: take the reports lock, wait for it, or end in lock_busy.
# Called in THIS shell only (never in a subshell: its exit is the run's exit).
lock_acquire() {
  local lock_dflt=600 first='' lock_end snap steal took told_wait=0 told_undesc=0
  L="$ROOT/.agents/state/local/sca-reports/.lock"
  # Identity BEFORE the claim (host: see lock_host).
  MY_PID=$$
  MY_HOST="$(lock_host)"
  MY_ST="$(lock_start "$$")"
  # The wait. The public variable is READ, never reassigned. A hook (CHANGED_ONLY)
  # waits 30 s: the smallest host budget cited is Claude's 60 s, minus a scan.
  [ "$CHANGED_ONLY" = "1" ] && lock_dflt=30
  lock_wait="${SCA_LOCK_WAIT_SECONDS:-}"
  if [ -z "$lock_wait" ]; then
    lock_wait="$lock_dflt"
  elif ! lock_wait_valid "$lock_wait"; then
    log "SCA: invalid SCA_LOCK_WAIT_SECONDS value; using ${lock_dflt} seconds"
    lock_wait="$lock_dflt"
  fi
  # RE-ENTRY: the per-module runs of --all-modules are children of the holder.
  # A child whose SCA_LOCK_OWNER is the live owner on this host takes nothing and
  # releases nothing (lock_mine stays 0). SCA_LOCK_OWNER is INTERNAL.
  if [ -n "${SCA_LOCK_OWNER:-}" ] && lock_read && [ "$o_pid" = "$SCA_LOCK_OWNER" ] \
     && [ "$o_host" = "$MY_HOST" ] && lock_alive "$o_pid"; then
    lock_ok=1
    return 0
  fi
  # A private witness of the moment the waiter last saw an owner-less lock change.
  ref="$(mktemp "${TMPDIR:-/tmp}/scalockref.XXXXXX" 2>/dev/null)" || ref=''
  # The TWO `$(( ))` of lock_acquire: this one (lock_wait is the 600/30 default or
  # passed lock_wait_valid: decimal) and the grace below (`first` is $SECONDS, set
  # in the same branch).
  # Neither can abort; one that ever did is caught by run_aborted at the caller.
  lock_end=$((SECONDS + lock_wait))
  # ONE iteration, and NO `continue` anywhere in it: every path reaches the
  # deadline test, so a steal that keeps failing can never spin past the wait.
  while :; do
    steal=0
    took=0
    # (1) the claim
    if mkdir "$L" 2>/dev/null; then
      # LOCK_MODE BEFORE lock_mine (C12): a signal between the two never writes
      # an aborted row without its mode.
      LOCK_MODE="$1"; lock_mine=1
      printf '%s\n%s\n%s\n' "$MY_PID" "$MY_HOST" "$MY_ST" > "$L/owner"
      SCA_LOCK_OWNER="$MY_PID"
      export SCA_LOCK_OWNER
      lock_ok=1
      return 0
    fi
    # (1b) a reports directory this run cannot write (closing review T5): the claim
    # failed with NO lock in place, so nobody holds it. Measured before: the run
    # read it as a held lock and waited out SCA_LOCK_WAIT_SECONDS (600 s by
    # default). No verdict can be written there: NO-GO at once, fail-closed.
    if [ ! -e "$L" ] && [ ! -w "$ROOT/.agents/state/local/sca-reports" ]; then
      log "SCA GATE (effective, waivers applied): NO-GO — reports directory not writable, no verdict obtained (fail-closed)"
      exit 1
    fi
    # (2) the judgement, and its snapshot
    lock_judge
    snap="$STATE|$o_pid|$o_host|$o_st"
    if [ "$told_wait" = 0 ]; then
      log "SCA: reports lock held by pid ${o_pid:-?} — waiting up to ${lock_wait}s"
      told_wait=1
    fi
    if [ "$STATE" = "undescribed" ] && [ "$told_undesc" = 0 ]; then
      log "SCA: reports lock owner pid ${o_pid} alive but not describable — not taken over"
      told_undesc=1
    fi
    # (3) the grace of an UNREADABLE owner: 40 s (>= 2 x 17 s, the worst Git Bash
    # spawn measured), counted from the first sight, and RESET whenever the lock's
    # date DIFFERS from the witness — newer OR older (lock_changed): a replacement
    # dated in the past (clock skew, a restored tree), even before the first lock
    # seen, restarts it. `touch -r` then copies that date onto the witness, so the
    # next turn compares against the lock now in place.
    if [ "$STATE" = "unreadable" ]; then
      if [ -z "$first" ] || lock_changed; then
        if [ -d "$L" ] && [ -n "$ref" ]; then touch -r "$L" "$ref" 2>/dev/null; fi
        first=$SECONDS
      fi
    else
      first=''
    fi
    case "$STATE" in
      dead|recycled) steal=1 ;;
      unreadable) [ $((SECONDS - first)) -ge 40 ] && steal=1 ;;
    esac
    # (4) the theft, under a mutex, after a RE-JUDGEMENT that must match the snapshot
    if [ "$steal" = 1 ] && mkdir "$L.steal" 2>/dev/null; then
      steal_held=1
      lock_judge
      if [ "$STATE|$o_pid|$o_host|$o_st" = "$snap" ] && [ -d "$L" ]; then
        if [ "$STATE" != "unreadable" ] || ! lock_changed; then
          rm -r "$L" 2>/dev/null && took=1
        fi
      fi
      rmdir "$L.steal" 2>/dev/null
      steal_held=0
      [ "$took" = 1 ] && log "SCA: stale reports lock (pid ${o_pid:-?}) taken over"
    fi
    # (5) ALWAYS the deadline
    [ "$SECONDS" -lt "$lock_end" ] || lock_busy "$1"
    # (6) a fresh theft retries at once; anything else waits a second
    [ "$took" = 1 ] || sleep 1
  done
}

# ---- A FINDING YOU CANNOT ACT ON MUST NOT GATE YOU (T-00000200) -------------
# Pilot decision, 2026-08-15, and it is the condition that makes wider scanning
# safe to ship at all.
#
# Widening coverage to every module is right, and it has a failure mode the kit
# would inflict on its own users: in a CONSUMER project part of the tree is
# PROTECTED — `.agents/bin/` and whatever that project lists in
# `.agents/protected-paths.local` — precisely because it is vendored code they
# must not edit. An advisory landing there is unfixable BY CONSTRUCTION: they
# cannot bump it, so a gate that goes NO-GO on it stays red forever and blocks
# every use of the kit. That is not a security control, it is a denial of
# service delivered by us.
#
# So a module under a protected path is class 3 by construction — non-actionable
# — and the doctrine already says what to do with class 3: LIST AND TRACK, never
# hard-block. It is scanned, its findings are recorded and reported, and it does
# not touch the gate. The way out is upstream (fix it in the kit and re-vendor),
# not a red light on their side.
#
# 0 = protected, 1 = not, 2 = cannot tell. Ambiguity resolves to NOT protected:
# exempting on a guess would silence a real finding, and the stricter branch is
# announced rather than assumed.
protected_module() { "$PY" "$SCRIPT_DIR/protected_module.py" --root "$ROOT" "$1"; }

# announce_degraded FILE: echo the aggregated .degraded reasons once, if any.
# Extracted from the inline gate line (was :623) so the no-ecosystem paths can
# reuse the SAME announcement. `-s` (not `-f`): today .degraded is only ever
# created by `>>`, so an empty file cannot exist — zero behaviour change.
announce_degraded() { [ -s "$1" ] && echo "  COVERAGE DEGRADED: $(paste -sd '; ' "$1")"; }

# sanitize_display STR: make an UNTRUSTED string safe to DISPLAY. Whitelist, not
# blacklist — everything outside `[A-Za-z0-9._/ -]` becomes `?`.
#
# WHY A WHITELIST, measured twice (T-00000488). The scanned repo is a CLIENT's,
# so a file name is untrusted input, and `announce_degraded` above renders the
# reasons JOINED by `paste -sd '; '` — the separator is therefore part of the
# GRAMMAR the reader parses. A first fix here stripped control bytes only, and
# that closed the ESC face (`A\033[1A\033[2KEFFACE.csproj` erased the line above
# on a terminal, CWE-150) while leaving the forgery face WIDE OPEN: a `.csproj`
# named `X); go: scanned, 0 CVE (go.mod present) (z.csproj` produced
#   COVERAGE DEGRADED: dotnet: … (src/App/X); go: scanned, 0 CVE (go.mod present) …
# — an entry claiming Go WAS scanned, byte-for-byte like a real one (compared
# against the genuine `go: ecosystem not covered in v1 (go.mod present)`). And
# it does not stop at the console: `audit_report.py:217-220` builds the Gaps
# `<li>` of the CLIENT HTML report from these same lines, so the false coverage
# claim lands in the deliverable. `html.escape` does not touch `;` or `()`.
# A blacklist also leaked everything >= 0x80 (measured: U+009B CSI and U+202E
# RLO both survived `tr -d '\000-\037\177'` intact).
#
# The machine verdict was never wrong — a status comes from a presence boolean,
# not from this text. It is the HUMAN reading the banner and the report who was
# being lied to, which is exactly what this lot exists to prevent.
#
# Replacing with `?` rather than deleting is deliberate: tampering stays VISIBLE
# instead of being silently erased. Measured identical under bash 3.2.57 and
# 5.3.15; `LC_ALL=C` makes the class byte-wise, so a UTF-8 char outside the set
# becomes one `?` per byte.
#
# BOUND, not a guarantee (L-00000187): this helper protects the call sites NAMED
# here, and nothing else. `.degraded` has 33 writers — RE-COUNTED ON DISK at
# T-01M4XF9JQXK6QJHHBFQZX7AGAJ: 27 `>> "$OUT/.degraded"` + 6 `>> "$deg"`. The raw counts are 28 and
# 7 — ONE hit of each form is the pattern CITATION on the line above, not a
# write, so subtract one from each or the census counts ITSELF. (Measured twice
# at T-00000512: an earlier revision of this very block quoted the pattern a
# second time in the note below, which moved the raw count to 25 and made the
# sentence describing it wrong. A self-referential census is easy to break.)
# It read 22 (16 + 6) before T-00000462, which added SIX: three in the
# python lock sequence (unreadable lock, excluded dependency, lock with no
# registry dependency) and three for the NVD offline posture (two Maven states,
# one Swift). T-00000512 added the 29th: nvd_note_unknown, which names an
# NVD_OFFLINE value it could not read as a truth. T-01M4X6FJG4XZ3ZN2BJCVVEMGXY
# added the 30th and the 31st: the fail-closed gate, which names a waiver_filter
# run that left no fresh effective verdict, and its Python-absent twin, which
# names a waiver_filter that never ran. T-01M4XF9JQXK6QJHHBFQZX7AGAJ added the
# 32nd and the 33rd, both for an absent Python: module discovery not run (the
# --all-modules branch) and locks not read (the python lock block). Both write
# literals of ours only. Re-counted with BOTH readers this file names below —
# `/usr/bin/grep` (BSD 2.6.0-FreeBSD) and GNU grep 3.12, which `grep` resolved
# to on that box through a shell function — and they agreed, 28 and 7.
# OUTSIDE THIS BASH COUNT, by construction: waiver_filter.py appends its own
# reason lines to the same `.degraded` (lot A of T-01M4X7W4M2XCFBK1MSY04X2907,
# widened by T-01M4Z33N54TX0Q7VHBZATFNR4X). It is a Python writer, so no `grep`
# of this file can see it. THREE shapes, all of fixed literals: a report
# unreadable or malformed, named by the literal of its `parsers` table and an
# exception CLASS — `UnrecognisedShape` included, for a readable report no
# parser recognises; an npm tool-error envelope, named by a code from a CLOSED
# list of two (`ENOLOCK`, `ERR_PNPM_AUDIT_NO_LOCKFILE`); and a socket report
# carrying no alert list. Never a path, never a client byte. The module ERROR of
# --all-modules and the reports lock write NO `.degraded` line at all (summary.json
# and the run's own log carry them), so the bash count below does not move.
# A census is RE-COUNTED
# whenever a lot moves it, never adjusted from memory — the "20" an earlier
# revision claimed was simply wrong, and a census nobody can reproduce is worth
# less than no census (L-00000111).
#
# RE-COUNT IT WITH `grep -cF`, NOT `grep -c`. WITHOUT `-F` the answer is
# IMPLEMENTATION-DEPENDENT, and that divergence is the trap. RE-MEASURED at
# T-00000512, same file and same pattern: `/usr/bin/grep` (BSD grep,
# 2.6.0-FreeBSD) reads the `$` of `$OUT` as a LITERAL and returns the same 24
# raw hits, while `ugrep 7.8.4` — what `grep` resolved to on the PATH this was
# first measured on — treats `$` as an end-of-line anchor in ANY position, so
# `$OUT` can never match and the count comes back **0**. An earlier revision of
# this block credited that 0 to BSD grep itself, which BSD grep does NOT do —
# so `type grep` is part of the recount. `-F` makes both readers agree at 24,
# which is the only reason it is the pinned form: a recount command that
# silently reports zero on one reader's PATH is how a census gets "adjusted
# from memory" while looking measured, which is the one failure this block
# exists to prevent.
#
# FOUR of the 33 interpolate a CLIENT-CONTROLLED string, and ALL FOUR are
# sanitized: `rel` in name_uncovered (dotnet, T-00000488), `rel_rf` feeding
# `$unpinned` in the python block (T-00000489), `$NVD_DATA_DIR` in the NVD
# offline states (T-00000462), and `$NVD_OFFLINE`'s unrecognised raw value in
# nvd_note_unknown (T-00000512) — the last TWO arrive from the ENVIRONMENT
# rather than from the filesystem, which makes them no less untrusted.
#
# `$py_other` LOOKS like a fourth and is NOT — it is concatenated from the fixed
# literals of our own enumeration, now TWO of them (pyproject.toml, Pipfile)
# where it used to hold five: T-00000462 moved Pipfile.lock, poetry.lock and
# uv.lock into `py_locks`, which are READ instead of being refused. The client
# controls whether those files EXIST, never one byte of the rendered text, so it
# stays unsanitized BY DESIGN. A decorative call there would advertise a
# coverage that has nothing to cover, and an announced hole that does not exist
# is what stops anyone from seeing the real one.
#
# `$pl_out` is a fifth false alarm and IS sanitized anyway: by the contract of
# py_lock_pins.py it holds two integers of ours, so there is nothing to
# neutralise — the belt is kept because it costs nothing and because a contract
# is only a contract for as long as someone re-measures it.
#
# The remaining 29 writers interpolate no client bytes at all: our own exit
# codes and counts (`$socket_rc`, `$pa_rc`, `$rc`, `$wf_rc`, `$ex_dep`, `$pl_names`,
# `${SOCKET_TIMEOUT_SECONDS}`), `$py_other`'s fixed list, or nothing but a
# literal.
sanitize_display() { printf '%s' "$1" | LC_ALL=C tr -c 'A-Za-z0-9._/ -' '?'; }

# THE AUDIT ROWS carry the gate level through this helper, never raw
# (T-01M4XF9HVVSB16Q2N1M1ZX2MTX, decision S-01M4XWS69W13H8ZATG6PT03W0A). The
# level comes from the CALLER's environment, and audit-log.jsonl is read one
# JSON object per line: measured before this line, a level carrying a newline
# and a second object appended a FORGED `"verdict":"GO"` row after the real
# NO-GO one, and a bare `"` duplicated the `verdict` key (the last one wins).
# `"`, `\` and every control byte are outside the whitelist, so the value can
# no longer leave its string. The RAW `$GATE_LEVEL` still goes to waiver_filter
# and to the npm/pnpm argv: its argparse refusal is what fires the fail-closed
# gate below. The module slug of the single-module row gets the same treatment
# at the printf (a `"` in a directory name made the row unparsable). Bound: the
# SUMMARY counters of that row are NOT passed through here — they are integers
# by waiver_filter's contract, not caller input.
GATE_LEVEL_AUDIT="$(sanitize_display "$GATE_LEVEL")"

# ---- NVD_OFFLINE: a TRUTH, read ONCE (reserve C33, CLOSED by T-00000512) -----
# `${NVD_OFFLINE:+…}` tested for NON-EMPTY, not for TRUE, at FIVE sites — so
# `NVD_OFFLINE=0` turned offline mode ON, the exact opposite of what anyone
# writing `0` means. What made it dangerous was not the inversion itself but its
# SILENCE, and the silence differed per ecosystem: on Maven an air-gapped run at
# least ends up loud (`produced no report` -> degraded), while the Swift block
# has NO no-report branch at all, so `SWIFT_STATUS` stays `scanned`. And OUTSIDE
# strict air-gap — network reachable, internal policy "no NVD" — both ecosystems
# would have gone online without a word.
#
# ONE normalisation, consumed at four sites, rather than four hand-written tests
# that could drift apart: forwarding and posture MUST keep applying the SAME
# predicate, because that coupling is what makes the posture line a truthful
# statement about the argv actually sent.
#
# FAIL-CLOSED IN TODAY'S DIRECTION. True = `1|true|yes`; false = empty|`0`|
# `false`|`no`; ANY OTHER VALUE = ON, which is exactly what this file already did
# — zero regression — but SAID rather than assumed (see nvd_note_unknown). The
# alternative, refusing and exiting, would break an air-gapped `/audit` on a
# typo.
#
# `on` and `off` are DELIBERATELY OUT of the vocabulary. Under a variable named
# `*_OFFLINE`, `off` is the ONE token that collides with the NAME: `NVD_OFFLINE=off`
# can mean "the value off" or "offline mode, off". Deciding that in secret would
# ship, in miniature, the very class of defect this helper removes — so `off`
# falls into the unknown branch and gets NAMED instead.
nvd_offline_norm() {
  # BOTH VARIABLES ASSIGNED UNCONDITIONALLY, FIRST (reserve C6). This file runs
  # under `set -uo pipefail`, so the bare `[ -n "$NVD_OFFLINE_ON" ]` at the two
  # posture sites would kill the script with "unbound variable" if the false
  # branch merely fell through. The `=0` faces of both suites would catch that,
  # but under a MISLEADING "premise" KO — a red that accuses the wrong culprit.
  NVD_OFFLINE_ON=""
  NVD_OFFLINE_RAW_UNKNOWN=""
  local raw low
  raw="${NVD_OFFLINE:-}"
  [ -n "$raw" ] || return 0
  # `tr` + `case`, NOT `${raw,,}`: that lowercase expansion is bash 4 and is a
  # PARSE error under /bin/bash 3.2.57 — the floor bash-parse-oldest.test.sh (p1)
  # holds. `LC_ALL=C` so the fold reads BYTES, not a locale (L-00000342).
  low="$(printf '%s' "$raw" | LC_ALL=C tr 'A-Z' 'a-z')"
  case "$low" in
    1|true|yes) NVD_OFFLINE_ON=1 ;;
    0|false|no) NVD_OFFLINE_ON="" ;;
    *)          NVD_OFFLINE_ON=1; NVD_OFFLINE_RAW_UNKNOWN="$raw" ;;
  esac
}

# nvd_note_unknown ECO: an unrecognised value is treated as offline, and that
# treatment is ANNOUNCED — once per ecosystem that consumed it. A no-op unless
# nvd_offline_norm failed to read the value as a truth, so the recognised values
# keep the `nvd:` line counts the suites pin (1 offline / 0 online).
nvd_note_unknown() {
  [ -n "${NVD_OFFLINE_RAW_UNKNOWN:-}" ] || return 0
  local disp
  # The value arrives from the CALLER'S ENVIRONMENT, so it is untrusted display
  # input exactly like a client file name — this is the FOURTH sanitized
  # interpolation counted in the census above.
  disp="$(sanitize_display "$NVD_OFFLINE_RAW_UNKNOWN")"
  log "[$1] NVD_OFFLINE='$disp' non reconnu — traité comme hors-ligne (vrai : 1/true/yes · faux : 0/false/no)"
  echo "nvd: NVD_OFFLINE='$disp' non reconnu — traité comme hors-ligne (vrai : 1/true/yes · faux : 0/false/no)" >> "$OUT/.degraded"
}

# ---- Ecosystems NOT covered in v1: NAMED, never silent (T-00000488) ----
# For each manifest present at the ROOT LOOKED AT (module root, or repo root on
# the no-module path of --all-modules), THREE writes and nothing else: a log
# line, a `.degraded` reason line, and `<KEY>_STATUS=degraded`. NEVER scanned=1
# — v1 does not scan Go/Rust/.NET/PHP/Ruby, it only refuses to stay silent about
# a manifest it can see. Status is set by an explicit branch per key (no eval,
# no ${key^^} — bash 3.2, sensor bash-parse-oldest.test.sh).
name_uncovered() {
  local d="$1" deg="$2" f rel
  if [ -f "$d/go.mod" ]; then
    log "[go] go.mod present — ecosystem not covered in v1 (NOT scanned) — go coverage DEGRADED"
    echo "go: ecosystem not covered in v1 (go.mod present)" >> "$deg"
    GO_STATUS="degraded"
  fi
  if [ -f "$d/Cargo.toml" ]; then
    log "[rust] Cargo.toml present — ecosystem not covered in v1 (NOT scanned) — rust coverage DEGRADED"
    echo "rust: ecosystem not covered in v1 (Cargo.toml present)" >> "$deg"
    RUST_STATUS="degraded"
  fi
  if [ -f "$d/composer.json" ]; then
    log "[php] composer.json present — ecosystem not covered in v1 (NOT scanned) — php coverage DEGRADED"
    echo "php: ecosystem not covered in v1 (composer.json present)" >> "$deg"
    PHP_STATUS="degraded"
  fi
  # Ruby: lock first, then Gemfile — name whichever is found (one line only).
  if [ -f "$d/Gemfile.lock" ]; then
    log "[ruby] Gemfile.lock present — ecosystem not covered in v1 (NOT scanned) — ruby coverage DEGRADED"
    echo "ruby: ecosystem not covered in v1 (Gemfile.lock present)" >> "$deg"
    RUBY_STATUS="degraded"
  elif [ -f "$d/Gemfile" ]; then
    log "[ruby] Gemfile present — ecosystem not covered in v1 (NOT scanned) — ruby coverage DEGRADED"
    echo "ruby: ecosystem not covered in v1 (Gemfile present)" >> "$deg"
    RUBY_STATUS="degraded"
  fi
  # dotnet is the ONLY one of the five to look BELOW the root: csproj/sln down to
  # depth 3 — src/App/App.csproj (3) is seen, a/b/c/Deep.csproj (4) is NOT
  # (L-00000187). find prints ABSOLUTE paths; only `rel` enters the writes.
  # NUL-safe end to end: a file name may legally contain a NEWLINE (only `/` and
  # NUL are forbidden), so a line-based `sort | head -1` can hand back a FRAGMENT
  # instead of the real path. `head -z` is GNU-only (absent on macOS), hence the
  # read of the first NUL record. Measured: `tr -d '\000' | head -1` would CONCAT
  # every path into one string — the obvious-looking fix is the wrong one.
  f="$(find "$d" -maxdepth 3 -not -path '*/node_modules/*' \( -name '*.csproj' -o -name '*.sln' \) -print0 \
        | LC_ALL=C sort -z | { IFS= read -r -d '' x || true; printf '%s' "$x"; })"
  if [ -n "$f" ]; then
    rel="${f#"$d"/}"
    # SECURITY (class-1 HIGH, T-00000488): `rel` is the ONLY dynamic content the
    # five blocks put into `log`, `.degraded` and — through announce_degraded —
    # stdout (measured on a fixture carrying go.mod + Cargo.toml + composer.json
    # + Gemfile: those four print a LITERAL, `$d` enters none of their writes).
    # The scanned repo is a CLIENT's, so a file name is UNTRUSTED input.
    # Sanitized ONCE, here, before any use — see sanitize_display for the two
    # measured attacks (terminal erasure, and forging a fake `go: scanned` entry
    # that reaches the client HTML report) and for why a whitelist.
    rel="$(sanitize_display "$rel")"
    log "[dotnet] $rel present — ecosystem not covered in v1 (NOT scanned) — dotnet coverage DEGRADED"
    echo "dotnet: ecosystem not covered in v1 ($rel present)" >> "$deg"
    DOTNET_STATUS="degraded"
  fi
}

# ---- --all-modules: discover, loop the single-module form, summarize --------
if [ "${1:-}" = "--all-modules" ]; then
  OUT="$ROOT/.agents/state/local/sca-reports"; mkdir -p "$OUT/modules"
  # The lock covers the WHOLE loop: the per-module runs below re-enter this file
  # as children and see this run as the owner (SCA_LOCK_OWNER), never a rival.
  lock_acquire all-modules
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # PYTHON ABSENT (T-01M4XF9JQXK6QJHHBFQZX7AGAJ, decision S-01M4XWS634J9QWVP7EZPTT2C8Y):
  # module discovery IS a Python program, so without Python it cannot run — and
  # it must not be executed as an empty command either. Measured before this
  # branch: `"$PY" …` with PY="" ran `""`, discovery came back empty, and the run
  # answered `no known ecosystem detected in any module`, rc 2, audit row
  # NO-ECOSYSTEM — on a repo with a requirements.txt. That is a FALSE statement,
  # not a degraded one: nothing was looked at. So the branch sits BEFORE the
  # discovery call and BEFORE the `-eq 0` test below; a mere `[ -n "$PY" ] &&`
  # in front of the call would silence the empty command and keep the lie.
  # Same posture as the single-module form (DEGRADED VISIBLE): never a block,
  # exit 0, but named on the banner, the last line and the audit row. The two
  # verdict files an EARLIER run left are removed — a reader that does not
  # check this run's last line (audit_report.py reads modules/summary.json
  # whenever it exists) would take them, the root pivot included, for today's. `.degraded` is reset FIRST, like the two sibling branches below
  # (reserve C2): an earlier run's reasons must not reach this banner.
  if [ -z "$PY" ]; then
    rm -f "$OUT/.degraded"
    rm -f "$OUT/effective-verdict.json" "$OUT/modules/summary.json"
    echo "module discovery: not run (python absent)" >> "$OUT/.degraded"
    name_uncovered "$ROOT" "$OUT/.degraded"
    announce_degraded "$OUT/.degraded"
    echo "SCA: module discovery not run (python absent) — modules NOT enumerated, NOT scanned."
    printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"DEGRADED","gate_level":"%s","modules":0}\n' \
      "$TS" "$GATE_LEVEL_AUDIT" >> "$OUT/audit-log.jsonl"
    echo "SCA GATE all-modules (effective, waivers applied): GO (DEGRADED — no effective verdict)"
    exit 0
  fi
  MODULES=(); while IFS= read -r _line; do MODULES+=("$_line"); done < <("$PY" "$SCRIPT_DIR/module_discovery.py" --root "$ROOT")
  if [ "${#MODULES[@]}" -eq 0 ]; then
    # T-00000488: /audit reaches THIS branch on a repo with no discovered module
    # (pure Go/Rust/.NET/PHP/Ruby) — name what is here before saying "nothing".
    rm -f "$OUT/.degraded"
    name_uncovered "$ROOT" "$OUT/.degraded"
    announce_degraded "$OUT/.degraded"
    echo "SCA: no known ecosystem detected in any module."
    printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"NO-ECOSYSTEM","modules":0}\n' \
      "$TS" >> "$OUT/audit-log.jsonl"
    [ "$CHANGED_ONLY" = "1" ] && exit 0   # hook context: exit 2 would block the host
    exit 2
  fi
  # T-00000488: the repo root is not a discovered module (e.g. go.mod at root +
  # web/package.json) — name what is at the root before looping over the
  # children. FAMILIES (module_discovery.py) never makes a Go/Rust/.NET/PHP/Ruby
  # module, so the root would otherwise be flagged GO with go.mod named nowhere.
  root_is_module=0
  for line in "${MODULES[@]}"; do
    [ "$(printf '%s' "$line" | cut -f2)" = "." ] && { root_is_module=1; break; }
  done
  if [ "$root_is_module" -eq 0 ]; then
    rm -f "$OUT/.degraded"
    name_uncovered "$ROOT" "$OUT/.degraded"
    announce_degraded "$OUT/.degraded"
  fi
  rows=""; global=0
  # waiver_filter's fail-closed line for rc 3, as the module run's `log` prints it
  # (the FC_RC3 prefix of sca-watch.sh; BRE: the parentheses are literal).
  MOD_RC3_RE='^  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=3, '
  for line in "${MODULES[@]}"; do
    slug="$(printf '%s' "$line" | cut -f1)"
    path="$(printf '%s' "$line" | cut -f2)"
    subs="$(printf '%s' "$line" | cut -f3)"
    folded="$(printf '%s' "$line" | cut -f4)"
    echo "== module $slug ($path, submodules=$subs) =="
    # A MODULE RC OUTSIDE {0,1} IS A VERDICT NOT OBTAINED (T-01M4Z395686TR4M7326AQ8ZPHW).
    # MEASURED before: a module killed by a signal (137), or a bare `exit 3`, read
    # GO — the loop only ever tested `-eq 1`, and summary.json even kept the
    # counters of the pivot an EARLIER run had left in that module. Its stdout is
    # kept (tee, it still streams) because the ONLY rc 2 that means "no
    # ecosystem" is the one that printed that exact line; any other 2 (module dir
    # not found, an `exit 2` from a broken run) is an error too.
    modlog="$(mktemp "$OUT/modules/.modlog.XXXXXX" 2>/dev/null)" || modlog=''
    bash "$0" "$path" | tee "${modlog:-/dev/null}"   # bash "$0": the x-bit is 644 in the index
    rc=${PIPESTATUS[0]}
    err=0; tracked=0
    case "$rc" in
      0|1) ;;
      2)
        if [ -z "$modlog" ] || ! LC_ALL=C grep -Fxq 'SCA: no known ecosystem detected.' "$modlog"; then
          err=1
        fi
        ;;
      *) err=1 ;;
    esac
    # A RAW 1 whose run says it obtained NO verdict (its lock busy, its run cut
    # short, its reports directory not writable) is an error too (closing review
    # T2). Measured before: a protected module's lock-busy run read
    # TRACKED-NOT-GATING, kept an EARLIER run's pivot (active 7), and the run
    # ended GO rc 0. The line is the one `log` prints on stdout, kept by tee.
    if [ "$rc" -eq 1 ] && [ -n "$modlog" ] && LC_ALL=C grep -Fq ', no verdict obtained (fail-closed)' "$modlog"; then
      err=1
    fi
    # A RAW 1 with NO module log (its mktemp refused in modules/) cannot be read:
    # neither line above nor below can be seen, so it is an error too, never the
    # protected substitution (security review MEDIUM; measured before: a
    # protected module's raw 1 read TRACKED-NOT-GATING, GO rc 0, unread). The
    # closed direction: a protected module's REAL findings then gate as well.
    if [ "$rc" -eq 1 ] && [ -z "$modlog" ]; then
      err=1
    fi
    # A RAW 1 whose run printed waiver_filter's fail-closed line for rc 3 — a
    # scanner report present but unreadable, truncated or of an unknown shape —
    # is an error too (E1, T-01M51RFFECAFAAR0CM3NR1GYEC; decision pilote
    # S-01M4XXZ7FMDJ3ZQFDVF2FC9WJZ). Measured before: a protected module whose
    # pip-audit.json was truncated read TRACKED-NOT-GATING, GO rc 0. L-00000180
    # exempts a protected module's FINDINGS (the DoS of a red it cannot fix); an
    # unread report is no finding. The anchor is sca-watch.sh's FC_RC3 prefix,
    # BRE, read under LC_ALL=C. ONLY rc=3 (the branch « non » of the plan's blind
    # spot): an invalid SCA_GATE_LEVEL or an unreadable register (wf_rc 2) in a
    # protected module stays TRACKED-NOT-GATING. RESIDUE, said (L-00000180): an
    # rc 3 that is DETERMINISTIC on vendored code — npm's E401/ENOTFOUND envelope
    # behind an internal mirror (waiver_filter.py keeps it rc 3) — now gates for
    # ever a project whose only npm module is protected, while a readable
    # CRITICAL in that same module stays TRACKED. Its line is NOT the `exited
    # rc=…, no verdict obtained` one: sca-watch's FC_RUN_RE would add the « run
    # interrompu » motif to the « rapport illisible » the module line already gives.
    rc3_noverdict=0
    if [ "$rc" -eq 1 ] && [ "$err" = 0 ] && [ -n "$modlog" ] && LC_ALL=C grep -q -- "$MOD_RC3_RE" "$modlog"; then
      err=1
      rc3_noverdict=1
    fi
    [ -n "$modlog" ] && rm -f "$modlog"
    modlog=''
    # The protected substitution applies to a RAW rc 1 only — never to an error.
    if [ "$err" = 0 ] && [ "$rc" -eq 1 ]; then
      protected_module "$path"; pm=$?
      case "$pm" in
        0) echo "  NOT GATING: '$path' is a protected path in this project — its"
           echo "  findings are TRACKED, not blocking (unfixable here by construction;"
           echo "  the fix belongs upstream, in the kit, then re-vendored)."
           rc=3; tracked=1 ;;
        2) echo "  note: the protected-path guard could not be read — no module is"
           echo "  exempted this run (the stricter branch, said out loud)." ;;
      esac
    fi
    if [ "$rc3_noverdict" = 1 ]; then
      global=1
      log "SCA GATE all-modules (effective, waivers applied): NO-GO — module $(sanitize_display "$slug"): no fresh effective verdict (fail-closed)"
    elif [ "$err" = 1 ]; then
      global=1
      log "SCA GATE all-modules (effective, waivers applied): NO-GO — module $(sanitize_display "$slug") exited rc=$rc, no verdict obtained (fail-closed)"
    elif [ "$rc" -eq 1 ]; then
      global=1
    fi
    rows="${rows}${slug}|${path}|${subs}|${rc}|${err}|${tracked}|${folded}"$'\n'
  done
  rows_file="$OUT/modules/.rows.tmp"
  printf '%s' "$rows" > "$rows_file"
  "$PY" - "$OUT" "$GATE_LEVEL" "$TS" "$ROOT" "$rows_file" <<'PYEOF'
import json, sys
from pathlib import Path
out, gate, ts, root = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
mods = []
totals = {"active_at_gate": 0, "accepted": 0, "pending_review": 0, "overdue_review": 0}
glob_ng = False
for line in Path(sys.argv[5]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    slug, path, subs, rc, err, tracked, folded = line.split("|", 6)
    counters = {}
    # The root module writes to the ROOT of sca-reports (T-00000291), every
    # other module under modules/<slug>/ — read each back from where it wrote.
    mdir = out if slug == "root" else out / "modules" / slug
    vfile = mdir / "effective-verdict.json"
    if err == "1":
        # A run that obtained NO verdict: whatever pivot sits here is an EARLIER
        # run's, and its counters must not reach this summary. Under any rc but 1
        # it is removed, so no reader sees it either. Under a raw 1 (lock busy, cut
        # short) the file is LEFT where it is: a busy lock belongs to another run,
        # and so may that pivot (closing review T2). BOUND, said in the README: a
        # reader still sees that pivot (the /audit HTML lists its findings as
        # active, with no no-verdict line); only this summary ignores it.
        if rc != "1":
            try:
                vfile.unlink()
            except OSError:
                pass
    elif vfile.is_file():
        try:
            counters = json.loads(vfile.read_text(encoding="utf-8")).get("counters", {})
        except ValueError:
            pass
    for k in totals:
        totals[k] += counters.get(k, 0)
    # A RAW "3" is an error (err=1, above). A "3" with err=0 is the loop's own
    # substitution for a NO-GO in a PROTECTED module (T-00000200): the findings
    # are real and kept in the report — they do not gate a project that has no
    # way to act on them.
    if err == "1":
        verdict = "ERROR"
    else:
        verdict = {"0": "GO", "1": "NO-GO", "2": "NO-ECOSYSTEM",
                   "3": "TRACKED-NOT-GATING"}.get(rc, "ERROR")
    if rc == "1" or err == "1":
        glob_ng = True
    gating = err == "1" or tracked != "1"
    dfile = mdir / ".degraded"
    reasons = ([l for l in dfile.read_text(encoding="utf-8").splitlines() if l.strip()]
               if dfile.is_file() else [])
    if err == "1":
        reasons.append(f"module run exited rc={rc} — no verdict obtained")
    # submodule_paths: collapsed for SCAN economy, still real code — the global
    # code review walks these instead of reading only the aggregator root.
    mods.append({"slug": slug, "path": path, "submodules": int(subs),
                 "submodule_paths": [p for p in folded.split(",") if p],
                 "verdict": verdict, "exit_code": int(rc),
                 "gating": gating,
                 "not_gating_reason": ("protected path in this project — "
                                       "unfixable here, fix upstream in the kit"
                                       if not gating else None),
                 "degraded": bool(reasons), "degraded_reasons": reasons,
                 "reports_dir": (".agents/state/local/sca-reports" if slug == "root"
                                 else f".agents/state/local/sca-reports/modules/{slug}"),
                 "counters": counters})
summary = {"generated": ts, "root": root, "gate_level": gate, "modules": mods,
           "global_verdict": "NO-GO" if glob_ng else "GO", "counters_total": totals}
(out / "modules" / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(f"  summary: {len(mods)} module(s) -> .agents/state/local/sca-reports/modules/summary.json")
PYEOF
  rm -f "$rows_file"
  verdict="GO"; [ "$global" -eq 1 ] && verdict="NO-GO"
  printf '{"ts":"%s","mode":"all-modules","entry":"sca-scan.sh","verdict":"%s","gate_level":"%s","modules":%s}\n' \
    "$TS" "$verdict" "$GATE_LEVEL_AUDIT" "${#MODULES[@]}" >> "$OUT/audit-log.jsonl"
  echo "SCA GATE all-modules (effective, waivers applied): $verdict"
  exit "$global"
fi
# FAIL-CLOSED NET, its own top-level line: the block above ENDS in `exit`, so
# `--all-modules` arriving HERE means bash discarded it (see run_aborted).
[ "${1:-}" != "--all-modules" ] || run_aborted all-modules

# ---- The bare form falls back on MISSING COVERAGE, not a missing root manifest
# ---- (T-00000200, corrected T-00000291) -------------------------------------
# The four host hooks all invoke this script with NO argument, and that form
# scans the repository ROOT. Measured on this repo: the automatic gate answered
# "no known ecosystem detected" rc=2 while `--all-modules` found and scanned
# `.agents/ui-src` perfectly well. So any project whose manifests live below the
# root — a front/back monorepo, this repository — was never scanned by the hook.
#
# THE OLD RULE gated the fallback on "no manifest at the root", and that was the
# defect T-00000291 closes: a SINGLE root manifest disabled the fallback
# ENTIRELY, so the commonest multi-module shape — a root `pom.xml`/`package.json`
# beside module manifests, `package.json` + workspaces — had NONE of its
# sub-modules scanned by the hook. It was invisible in THIS repo only because it
# carries no root manifest, so the fallback fired by accident; it was ACTIVE at
# every adopting project that did carry one (L-00000231).
#
# THE RULE NOW: fall back when module discovery finds at least one module whose
# path is not the repository root itself (discovery's field 2 != '.') — a module
# a root scan does not cover. It stays ADDITIVE where the old rule was right: a
# repo whose ONLY module is the root (discovery emits just `.`, workspaces folded
# under it) does not fall back and keeps the exact same scan AND the same report
# paths at the root of `sca-reports`, where the dashboard and `sca-watch.sh` read
# the effective verdict. Only repos getting an incomplete scan change behaviour.
#
# It is safe to widen only because a protected module no longer gates (see
# `protected_module` above): without that, this line would hand every consumer a
# permanent red light on code they are forbidden to edit.
if [ -z "${1:-}" ] && [ "${SCA_ROOT_ONLY:-0}" != "1" ]; then
  # Never execute an empty command: with Python absent, PY is "" and `"$PY" …`
  # RAN one (the bash-tests runner's `MISSING DEP (cmd: ?)`). No Python, no
  # discovery — the same empty result, no fallback, as before.
  discovery=""
  if [ -n "$PY" ]; then
    discovery="$("$PY" "$SCRIPT_DIR/module_discovery.py" --root "$ROOT" 2>/dev/null)"
  fi
  # Modules a root scan would not cover: any discovered module whose path
  # (discovery's tab-separated field 2) is not the repository root itself.
  uncovered="$(printf '%s\n' "$discovery" | awk -F'\t' 'NF>=2 && $2!="."{print $2}')"
  if [ -n "$uncovered" ]; then
    n="$(printf '%s\n' "$uncovered" | awk 'NF{c++}END{print c+0}')"
    echo "SCA: $n module(s) live below the repository root that a root scan would not cover —"
    echo "  falling back to --all-modules (set SCA_ROOT_ONLY=1 to keep the old scope):"
    # Bound (T-00000302 C2): only these PATH lines are unparsed by any machine, so an
    # ANSI-bearing directory name merely dirties a terminal here, never injects. The
    # ANNOUNCE line above (`falling back to --all-modules`) is DIFFERENT — it is pinned
    # by sca-module-gate.test.sh, so it is contract, not free text.
    printf '%s\n' "$uncovered" | while IFS= read -r p; do
      [ -n "$p" ] && echo "    - $p"
    done
    # `bash "$0"`, never a bare `exec "$0"`: every .sh in this repo is mode
    # 100644 in the git index (Windows-authored), so on a REAL POSIX checkout
    # (GitHub Actions) executing the FILE dies with Permission denied — right
    # after the fallback lines above, which is exactly the red T-00000307
    # measured (fallback announced, module never reached, suite over in 1s).
    # Windows ignores the bit and Docker Desktop mounts everything 755, which
    # is why neither dev boxes nor the frozen-clone container ever saw it.
    exec bash "$0" --all-modules
  fi
fi

# ---- Resolve scan target: default repo root, or one module dir --------------
TGT="$ROOT"; SLUG="root"; OUT="$ROOT/.agents/state/local/sca-reports"
if [ -n "${1:-}" ]; then
  if   [ -d "$ROOT/$1" ]; then TGT="$(cd "$ROOT/$1" && pwd)"
  elif [ -d "$1" ];       then TGT="$(cd "$1" && pwd)"
  else echo "SCA: module dir not found: $1"; exit 2; fi
  # The root module — even when reached through the --all-modules loop as
  # `sca-scan.sh .` — writes to the ROOT of sca-reports, not modules/root/, so
  # the dashboard, sca-watch.sh and audit_report.py read one root verdict at the
  # place they already look (T-00000291). Only a genuine sub-module lands under
  # modules/<slug>/.
  if [ "$TGT" = "$ROOT" ]; then
    SLUG="root"; OUT="$ROOT/.agents/state/local/sca-reports"
  else
    rel="${TGT#"$ROOT"/}"; SLUG="${rel//\//__}"
    OUT="$ROOT/.agents/state/local/sca-reports/modules/$SLUG"
  fi
fi
# The lock, BEFORE the first write into the reports: its parent directory first
# (a root without sca-reports/ yet), then the claim, then the module's own dir.
# A child of --all-modules re-enters here and takes nothing (see lock_acquire).
mkdir -p "$ROOT/.agents/state/local/sca-reports"
lock_acquire scan
# FAIL-CLOSED NET, its own top-level line: lock_acquire RETURNED (see run_aborted).
[ "$lock_ok" = 1 ] || run_aborted scan
mkdir -p "$OUT"
rm -f "$OUT/.degraded"   # coverage-degradation marker, rebuilt at each run
# THE SCANNER REPORTS THIS SCRIPT PRODUCES are purged HERE, before any tool runs
# (reserve C5 of plan-critic on T-01M4X7W4M2XCFBK1MSY04X2907). `$OUT` survives
# between runs, and waiver_filter.py reads every name of its `parsers` table
# that it finds in `$OUT` — so a report left by an EARLIER run of a tool that
# did not run THIS time (manifest removed, tool uninstalled, pip-audit skipped
# because no requirement is pinned) was read as today's finding: a stale HIGH
# blocked, and — since waiver_filter fails closed on an unreadable report (rc 3,
# lot A of the same plan) — a stale TRUNCATED one would block every run. This
# single site covers each run AND each module of --all-modules, because the loop
# re-enters this file once per module (`bash "$0" "$path"`). Same idiom as the
# `.degraded` reset above; the in-block removals (socket.json, an empty
# pip-audit.json) stay, they are a second belt for a run that DID start.
# `trivy-image.json`, the sixth name of that table, is NOT purged, BY DESIGN:
# this script never writes it — a project's own image-scan step does, BEFORE
# this gate, and waiver_filter.py (parse_trivy_image, PRODUCER CONTRACT) applies
# the register to it. Purging it here would drop that step's image CVEs and turn
# its red into a silent GO. Bound: that report's freshness belongs to its
# producer; a stale unreadable one keeps the gate red until the producer reruns.
rm -f "$OUT/npm-audit.json" "$OUT/dependency-check-report.json" "$OUT/socket.json" \
      "$OUT/trivy-config.json" "$OUT/pip-audit.json"
scanned=0

# Per-ecosystem status (T-00000018 shard 2, scan.sca item 5): scanned |
# degraded | skipped. Defaults to "skipped" (manifest not present — same
# "normal, not a failure" posture as MCP's `unresolved`, L-00000033/34) and is
# overwritten below as each ecosystem block actually runs. NEVER collapsed
# into one tri-state: "status=scanned" while java/swift never ran would
# write "scanned, clean" for an ecosystem this run never touched — the exact
# L-010 false-GO shape this map exists to prevent.
NPM_STATUS="skipped"; SUPPLY_STATUS="skipped"
MAVEN_STATUS="skipped"; GRADLE_STATUS="skipped"
SWIFT_STATUS="skipped"; IAC_STATUS="skipped"
PYTHON_STATUS="skipped"
# T-00000488 — ecosystems NAMED-but-not-scanned in v1 (see name_uncovered).
GO_STATUS="skipped"; RUST_STATUS="skipped"; DOTNET_STATUS="skipped"
PHP_STATUS="skipped"; RUBY_STATUS="skipped"

# ONE call, HERE, before any ecosystem dispatch — every site that consumes
# NVD_OFFLINE_ON (Maven forwarding + posture, Swift forwarding + posture) is
# below this line. The two paths that re-enter this file do NOT need a second
# call: `--all-modules` runs `bash "$0" "$path"` per module and the coverage
# fallback does `exec bash "$0" --all-modules`, so both are NEW processes that
# come through here again. Re-verified by name at T-00000512.
nvd_offline_norm

echo "== SCA scan @ $TGT =="

# ---- npm / JS ecosystem (Node, Next.js, Angular, RN js side) ----------------
if [ -f "$TGT/package.json" ]; then
  scanned=1
  NPM_STATUS="scanned"
  if   [ -f "$TGT/pnpm-lock.yaml" ] && have pnpm; then
        # `${X[@]+"${X[@]}"}` and NOT `"${X[@]}"` (T-00000837 F3): with
        # audit-dev-deps.local present the SCOPE arrays are EMPTY, and bash 3.2
        # (macOS /bin/bash) + `set -u` kills the subshell BEFORE the audit —
        # npm-audit.json then holds 0 bytes and the verdict read GO. Same idiom
        # as py_reqs below and gitleaks-scan.sh's CFG (T-00000841).
        log "[npm] pnpm audit (lockfile-only) ${PNPM_SCOPE[*]:-+dev}"
        ( cd "$TGT" && pnpm audit ${PNPM_SCOPE[@]+"${PNPM_SCOPE[@]}"} --audit-level="$GATE_LEVEL" --json ) \
          > "$OUT/npm-audit.json" 2>/dev/null || true
  elif have npm; then
        log "[npm] npm audit --package-lock-only ${NPM_SCOPE[*]:-+dev}"
        ( cd "$TGT" && npm audit --package-lock-only ${NPM_SCOPE[@]+"${NPM_SCOPE[@]}"} --audit-level="$GATE_LEVEL" --json ) \
          > "$OUT/npm-audit.json" 2>/dev/null || true
  else  log "[npm] SKIP — no npm/pnpm on PATH — npm coverage DEGRADED"
        echo "npm: no npm/pnpm on PATH" >> "$OUT/.degraded"; NPM_STATUS="degraded"; fi

  # Behavioural / supply-chain layer (typosquat, malicious install scripts).
  # Never let a previous successful report masquerade as this run's result,
  # regardless of which availability/failure branch this run takes.
  rm -f "$OUT/socket.json"
  if have socket; then
        if timeout --version 2>/dev/null | grep -q 'GNU coreutils'; then
          log "[npm] socket scan (behavioural, timeout ${SOCKET_TIMEOUT_SECONDS}s)"
          ( cd "$TGT" && timeout --kill-after=5 "${SOCKET_TIMEOUT_SECONDS}s" \
              socket scan create --json ) > "$OUT/socket.json" 2>/dev/null
          socket_rc=$?
          case "$socket_rc" in
            0) SUPPLY_STATUS="scanned" ;;
            124|137)
              log "[npm] Socket scan timed out after ${SOCKET_TIMEOUT_SECONDS}s — supply-chain layer DEGRADED"
              echo "socket: scan timed out after ${SOCKET_TIMEOUT_SECONDS}s" >> "$OUT/.degraded"
              SUPPLY_STATUS="degraded"
              rm -f "$OUT/socket.json"
              ;;
            *)
              log "[npm] Socket scan failed (exit $socket_rc) — supply-chain layer DEGRADED"
              echo "socket: scan failed (exit $socket_rc)" >> "$OUT/.degraded"
              SUPPLY_STATUS="degraded"
              rm -f "$OUT/socket.json"
              ;;
          esac
        else
          log "[npm] GNU timeout not installed — Socket scan not started — supply-chain layer DEGRADED"
          echo "socket: GNU timeout not installed; scan not started" >> "$OUT/.degraded"
          SUPPLY_STATUS="degraded"
        fi
  else  log "[npm] socket not installed — supply-chain layer DEGRADED"
        # T-00000018 fix: this branch previously logged to stdout only and
        # never fed sca-scan.sh's own .degraded marker — the design doc's
        # scan.sca comment names ":150" as an existing aggregation point,
        # but it wasn't; a per-ecosystem status map built on .degraded alone
        # would have silently shown "supply_chain: scanned" here. Small,
        # in-scope fix (this file is already being wired for scan.sca).
        echo "socket: not installed (supply-chain layer)" >> "$OUT/.degraded"
        SUPPLY_STATUS="degraded"; fi
fi

# ---- Java: Maven (a multi-module reactor scans once from the aggregator) ----
# Ecosystem detection is manifest-based; scanner availability only degrades it.
if [ -f "$TGT/pom.xml" ]; then
  scanned=1
  MAVEN_STATUS="scanned"
  MVN=""
  if   [ -f "$TGT/mvnw" ]; then MVN="sh ./mvnw"
  elif have mvn;           then MVN="mvn"; fi
  if [ -n "$MVN" ]; then
    # aggregate (not check): one consolidated report at the reactor root, so a
    # multi-module build collapsed onto its aggregator yields ONE parseable file.
    # A FLAG, never an expansion that CAN render the value (CWE-532, T-00000512).
    # The line this replaced concatenated TWO expansions of this same variable:
    # a `:+set` (renders `set` when non-empty — correct) immediately followed by
    # a `:-NOT set …` fallback. That second one renders THE VALUE, not the
    # fallback, whenever the variable is non-empty, so the pair printed `set`
    # FOLLOWED BY THE KEY IN CLEAR. Measured with a sentinel:
    # `(NVD_API_KEY setSENT1NEL-… / cached DB)` on stdout, 1 occurrence, on
    # EVERY real run of the Java gate with the key exported — no red face and no
    # mutation needed. The argv-journal redaction in the test stubs is link 2 and
    # does NOT cover this channel: the same run showed 0 occurrences in
    # mvn-dc.log while the console had 1. Two ternaries on one variable can never
    # both be right here; a flag has no second branch to get wrong. The faulty
    # form is NOT quoted verbatim above on purpose — a sweep for it must not
    # match this note. Sweep that finds it, same-variable adjacency:
    #   perl -ne 'while (/\$\{([A-Za-z_]\w*):?\+[^}]*\}\s*\$\{\1:?-/g){print "$ARGV:$.\n"}' <files>
    NVDK="NOT set — first NVD sync may fail/throttle"
    [ -n "${NVD_API_KEY:-}" ] && NVDK="set"
    log "[maven] OWASP dependency-check (aggregate) via $MVN (NVD_API_KEY $NVDK / cached DB)"
    # OFFLINE / AIR-GAPPED FORWARDING (T-00000462). These are the MAVEN PLUGIN's
    # properties, a different surface from the dependency-check CLI's own flags
    # (`--noupdate` and `-d, --data <path>`, the latter documented only under
    # `--advancedHelp`, MEASURED on dependency-check-cli 13.0.0). Do not read one
    # as the other; the Swift block below uses the CLI form.
    #
    # TRAP CLOSED (reserve C33, T-00000512): `$NVD_OFFLINE_ON` is the NORMALISED
    # truth from nvd_offline_norm, not the raw variable — `NVD_OFFLINE=0` no
    # longer turns offline mode ON. `NVD_DATA_DIR` stays on the raw `:+` test
    # BY DESIGN: it is a PATH, so "non-empty" IS its correct semantics (empty =
    # absent), and `NVD_DATA_DIR=0` would forward an absurd `-DdataDirectory=0`
    # that fails loudly into "produced no report" rather than inverting a mode.
    # .dc-start: the target/ pull below takes only a report written by THIS run
    # (critic-opus T5: a stale build's report must never read as today's).
    : > "$OUT/.dc-start"
    ( cd "$TGT" && $MVN -q org.owasp:dependency-check-maven:aggregate \
        -Dformat=JSON -DoutputDirectory="$OUT" -DfailBuildOnCVSS=11 \
        ${NVD_API_KEY:+-DnvdApiKey="$NVD_API_KEY"} \
        ${NVD_OFFLINE_ON:+-DautoUpdate=false} \
        ${NVD_DATA_DIR:+-DdataDirectory="$NVD_DATA_DIR"} ) \
        > "$OUT/mvn-dc.log" 2>&1 || true
    if [ ! -f "$OUT/dependency-check-report.json" ]; then
      # -DoutputDirectory not honored by every plugin version — pull from target/
      dc="$(find "$TGT" -maxdepth 3 -path '*/target/dependency-check-report.json' -newer "$OUT/.dc-start" 2>/dev/null | head -1)"
      if [ -n "$dc" ]; then
        cp "$dc" "$OUT/dependency-check-report.json"
      else
        log "[maven] no dependency-check report produced (see mvn-dc.log) — java coverage DEGRADED"
        echo "maven: dependency-check aggregate produced no report (NVD DB missing? see mvn-dc.log)" >> "$OUT/.degraded"
        MAVEN_STATUS="degraded"
      fi
    fi
    # ---- NVD posture: THREE states, NAMED (T-00000462) ----------------------
    # Placed AFTER the invocation and OUTSIDE the report-present/absent test, so
    # the posture is recorded on BOTH paths: a run that produced a perfect report
    # from a base of unknown age is still a run whose coverage is BOUNDED.
    #
    # A BOUNDED COVERAGE IS `degraded`, and that is the SAME rule this file now
    # applies to an excluded Python dependency. `emit_sca` publishes `java` from
    # JAVA_STATUS, itself derived from MAVEN/GRADLE, so a `.degraded` reason line
    # under a `scanned` status would make the machine verdict contradict the
    # human one — the shape L-00000111 names.
    # SAME PREDICATE AS THE FORWARDING ABOVE — `$NVD_OFFLINE_ON`, never the raw
    # variable. That coupling is the whole point: the posture line is a statement
    # ABOUT the argv actually sent, so the two must not be able to disagree.
    if [ -n "$NVD_OFFLINE_ON" ]; then
      if [ -n "${NVD_DATA_DIR:-}" ]; then
        # State 1 — a pre-seeded base IS present. The scan is real; its freshness
        # is not. `$NVD_DATA_DIR` comes from the caller's environment, so it is
        # UNTRUSTED display input exactly like a client file name.
        log "[maven] NVD_OFFLINE — base hors-ligne ($(sanitize_display "$NVD_DATA_DIR")), aucune synchro NVD — java coverage DEGRADED"
        echo "nvd: base hors-ligne ($(sanitize_display "$NVD_DATA_DIR")), fraîcheur non vérifiée" >> "$OUT/.degraded"
        MAVEN_STATUS="degraded"
      else
        # State 2 — offline and NO base at all: dependency-check has nothing to
        # match against, so an empty finding list means "did not look", not
        # "found nothing". The single most dangerous false GO of this ecosystem.
        log "[maven] NVD_OFFLINE sans NVD_DATA_DIR — couverture Java NON GARANTIE — java coverage DEGRADED"
        echo "nvd: hors-ligne SANS répertoire de base — couverture Java NON GARANTIE" >> "$OUT/.degraded"
        MAVEN_STATUS="degraded"
      fi
      # Reached from states 1 AND 2, and a no-op on a recognised value — so the
      # `nvd:` counts the suites pin stay 1 offline / 0 online, and only an
      # UNRECOGNISED value makes it 2. It sits inside this branch because an
      # unrecognised value is, by construction, one that normalised to ON.
      nvd_note_unknown maven
    fi
    # State 3 — offline mode OFF (unset, or one of 0/false/no): nothing is
    # written, and the absence of a reason line is itself the statement that
    # coverage was not bounded here.
  else
    log "[maven] SKIP — no ./mvnw wrapper and no mvn on PATH — java coverage DEGRADED"
    echo "maven: no ./mvnw wrapper and no mvn on PATH" >> "$OUT/.degraded"
    MAVEN_STATUS="degraded"
  fi
fi

# ---- Java: Gradle ----------------------------------------------------------
if [ -f "$TGT/build.gradle" ] || [ -f "$TGT/build.gradle.kts" ]; then
  scanned=1
  GRADLE_STATUS="scanned"
  GRADLE=""
  if   [ -f "$TGT/gradlew" ]; then GRADLE="sh ./gradlew"
  elif have gradle;           then GRADLE="gradle"; fi
  if [ -n "$GRADLE" ]; then
    # NVD key: the gradle plugin reads it from the BUILD (nvd { apiKey = System.getenv('NVD_API_KEY') }) — no reliable CLI pass-through.
    log "[gradle] dependencyCheckAnalyze via $GRADLE"
    # T-00000462 — SAID, not silently skipped: the offline knobs are NOT
    # forwarded here. The OWASP gradle plugin configures `autoUpdate` and
    # `data.directory` from the BUILD SCRIPT, and there is no reliable CLI
    # pass-through for either, exactly as with the API key just above. An
    # adopter setting NVD_OFFLINE would otherwise believe Gradle honoured it.
    [ -n "${NVD_OFFLINE:-}${NVD_DATA_DIR:-}" ] && \
      log "[gradle] NVD_OFFLINE/NVD_DATA_DIR NON transmis à Gradle (le plugin les lit du build script) — configure-les dans build.gradle"
    : > "$OUT/.dc-start"
    ( cd "$TGT" && $GRADLE -q dependencyCheckAnalyze ) > "$OUT/gradle-dc.log" 2>&1 || true
    # the OWASP gradle plugin writes under build/reports — relocate for the filter;
    # only a report newer than this run's start (critic-opus T5).
    dc="$(find "$TGT" -maxdepth 5 -path '*/build/reports/dependency-check-report.json' -newer "$OUT/.dc-start" 2>/dev/null | head -1)"
    if [ -n "$dc" ]; then
      cp "$dc" "$OUT/dependency-check-report.json"
    else
      log "[gradle] no dependency-check report produced (OWASP plugin missing in the build?) — java coverage DEGRADED"
      echo "gradle: dependencyCheckAnalyze produced no report (OWASP plugin missing in the build?)" >> "$OUT/.degraded"
      GRADLE_STATUS="degraded"
    fi
  else
    log "[gradle] SKIP — no ./gradlew wrapper and no gradle on PATH — java coverage DEGRADED"
    echo "gradle: no ./gradlew wrapper and no gradle on PATH" >> "$OUT/.degraded"
    GRADLE_STATUS="degraded"
  fi
fi

# ---- Swift / iOS (OWASP DC analyzer is EXPERIMENTAL for SPM) ----------------
if [ -f "$TGT/Package.resolved" ] || find "$TGT/ios" -name Package.resolved 2>/dev/null | grep -q .; then
  scanned=1
  if have dependency-check; then
    log "[swift] OWASP dependency-check on Package.resolved (experimental)"
    SWIFT_STATUS="scanned"
    # CLI flags here, NOT the Maven plugin properties used above: `--noupdate`
    # and `-d, --data <path>`. MEASURED on dependency-check-cli 13.0.0 — and the
    # measurement corrected the plan: `--noupdate` appears in `--help`, but
    # `--data` appears ONLY under `--advancedHelp` (line 68 of that output), so
    # a bare `--help` is not enough to confirm the pair. C33 CLOSED here too
    # (T-00000512): `$NVD_OFFLINE_ON` is the normalised truth, so `NVD_OFFLINE=0`
    # no longer forwards `--noupdate`. THIS BLOCK WAS THE WORSE OF THE TWO and it
    # is why the fix could not stay on Maven: there is NO "no report" branch
    # after this call, so `SWIFT_STATUS` stays `scanned` — an inverted knob here
    # produced no report check, no degraded line, no log. Total silence.
    dependency-check --scan "$TGT" --format JSON --out "$OUT" \
      --enableExperimental ${NVD_API_KEY:+--nvdApiKey "$NVD_API_KEY"} \
      ${NVD_OFFLINE_ON:+--noupdate} ${NVD_DATA_DIR:+--data "$NVD_DATA_DIR"} \
      > "$OUT/swift-dc.log" 2>&1 || true
    # Same bounded-coverage rule as Maven, and the SAME predicate as the
    # forwarding two lines up — arms of its own now live in sca-swift.test.sh.
    if [ -n "$NVD_OFFLINE_ON" ]; then
      log "[swift] NVD_OFFLINE — base hors-ligne, fraîcheur non vérifiée — swift coverage DEGRADED"
      echo "nvd: base hors-ligne (swift), fraîcheur non vérifiée" >> "$OUT/.degraded"
      SWIFT_STATUS="degraded"
      nvd_note_unknown swift
    fi
  else
    log "[swift] dependency-check CLI not installed — iOS deps NOT scanned — swift coverage DEGRADED"
    echo "swift: dependency-check CLI not installed" >> "$OUT/.degraded"
    SWIFT_STATUS="degraded"
  fi
fi

# ---- Python (pip-audit, LOCK-ONLY posture: --no-deps, never resolves) --------
# T-00000292 — first case of the general ecosystem rule (see
# docs/design/ADDING_AN_ECOSYSTEM.md).
#
# POSTURE FIXED BY THE PLAN, and it is the whole point of the block: `pip-audit
# -r` RESOLVES the dependency set by default — it downloads and BUILDS sdists,
# i.e. it EXECUTES arbitrary setup.py — which is exactly the mutation the
# dispatcher refuses everywhere else (npm runs --package-lock-only). So
# `--no-deps` is ALWAYS passed: only the versions PINNED (==) in a
# requirements*.txt are audited. Anything that would need resolution is REFUSED
# and NAMED as degraded, never silently resolved:
#   - an UNPINNED requirements file  -> degraded, resolution refused
#   - only pyproject/Pipfile/poetry.lock/uv.lock (no scannable requirements)
#                                     -> degraded, manifest not supported in v1
#   - pip-audit absent               -> degraded, NEVER a block
#   - pip-audit run/network failure  -> degraded
# A requirements file is "pinned" iff every requirement line carries `==`;
# blank/comment/option (-r, --hash, -e, -c) lines don't count against it.
requirements_pinned() {
  local f="$1" line stripped
  while IFS= read -r line || [ -n "$line" ]; do
    stripped="${line%%#*}"
    stripped="$(printf '%s' "$stripped" | tr -d '[:space:]')"
    [ -z "$stripped" ] && continue
    case "$stripped" in
      -*) continue ;;
      *==*) : ;;
      *) return 1 ;;
    esac
  done < "$f"
  return 0
}
py_reqs=()
while IFS= read -r f; do [ -n "$f" ] && py_reqs+=("$f"); done < <(
  find "$TGT" -maxdepth 1 -name 'requirements*.txt' -type f 2>/dev/null | sort)
# T-00000462 — the enumeration SPLITS in two, and the split is the fix for case
# #143. It used to hold FIVE literals, all of them treated as "not supported":
# a project with poetry.lock/uv.lock/Pipfile.lock and NO requirements*.txt was
# never audited, while the run still had a python status to publish.
#   py_locks  — LOCKFILES: exact versions already resolved by the packaging
#               tool, so reading them is a pure translation (py_lock_pins.py).
#   py_other  — pyproject.toml / Pipfile ALONE: version RANGES. Pinning a range
#               requires a RESOLUTION, which downloads and BUILDS sdists — the
#               one mutation this dispatcher refuses everywhere. Still refused,
#               still NAMED, under the literal that :642 has always carried.
# Both stay enumerations of FIXED literals of ours; the client controls whether
# those files exist, never one byte of the rendered text.
py_locks=()
for m in Pipfile.lock poetry.lock uv.lock; do
  [ -f "$TGT/$m" ] && py_locks+=("$TGT/$m")
done
py_other=""
for m in pyproject.toml Pipfile; do
  [ -f "$TGT/$m" ] && py_other="${py_other:+$py_other, }$m"
done
# UNCONDITIONAL, and it must sit HERE — before the entry predicate, so it runs
# even on a root that has no Python at all. `$OUT` SURVIVES between runs (see
# the `rm -f "$OUT/.degraded"` at the top, same idiom): a lock deleted from the
# project between two runs would otherwise leave its pins behind, and the next
# run would audit dependencies the project no longer has while reporting a
# perimeter it never looked at. py_lock_pins.py removes the same file on both of
# its file-less outcomes; the two belts are deliberate and are mutated TOGETHER
# by (L6) of sca-python.test.sh, because one belt alone still cleans up.
rm -f "$OUT/pins-from-locks.txt" "$OUT/py-locks.log"
if [ "${#py_reqs[@]}" -gt 0 ] || [ -n "$py_other" ] || [ "${#py_locks[@]}" -gt 0 ]; then
  scanned=1
  PYTHON_STATUS="scanned"
  if ! have pip-audit; then
    log "[python] pip-audit not installed — Python deps NOT scanned — python coverage DEGRADED"
    echo "python: pip-audit not installed" >> "$OUT/.degraded"
    PYTHON_STATUS="degraded"
  elif [ "${#py_reqs[@]}" -eq 0 ] && [ "${#py_locks[@]}" -eq 0 ]; then
    # Only non-requirements manifests present: not audited in v1 (the lock-only,
    # no-resolution posture has no reader for them here). Named, never silent.
    log "[python] only unsupported manifest(s) present ($py_other) — not audited in v1 — python coverage DEGRADED"
    echo "python: manifest(s) not supported in v1 ($py_other) — no scannable requirements*.txt" >> "$OUT/.degraded"
    PYTHON_STATUS="degraded"
  else
    pin_args=(); unpinned=""
    # `${arr[@]+"${arr[@]}"}` and NOT `"${arr[@]}"`: under `set -u`, bash 3.2
    # (the floor this kit ships against, sensor bash-parse-oldest.test.sh) treats
    # an EMPTY array expansion as an unbound variable and kills the script. In
    # lock-only mode — the very case #143 this lot exists to cover — `py_reqs` IS
    # empty and the flow reaches here, so the guard is not decorative. Same
    # idiom as semgrep-scan.sh:1151/:1208/:1466.
    for rf in ${py_reqs[@]+"${py_reqs[@]}"}; do
      rel_rf="${rf#"$TGT"/}"
      if requirements_pinned "$rf"; then
        # `$rf` stays RAW here BY DESIGN: pin_args is pip-audit's argv, not a
        # display sink — it has to name the file that actually exists on disk.
        pin_args+=(-r "$rf")
      else
        # SECURITY (class-1 HIGH, CWE-117, T-00000489 — same class as the dotnet
        # site at :237): `$rel_rf` is a file name from the CLIENT's repo, so it
        # is UNTRUSTED, and it reaches `log`, `.degraded` and — through
        # announce_degraded's `paste -sd '; '` — the banner and the Gaps <li> of
        # the delivered HTML report.
        #
        # Sanitized PER ELEMENT, BEFORE accumulation, and the PLACEMENT is the
        # whole subtlety — it is NOT the dotnet site's placement, and copying
        # that one by analogy would reopen the hole differently. `$unpinned` is a
        # LIST whose `, ` separator is itself GRAMMAR the reader parses, and `,`
        # is OUTSIDE the whitelist. Measured on this box (bash 3.2.57, BSD tr):
        #   printf 'requirements-a.txt, requirements-b.txt' \
        #     | LC_ALL=C tr -c 'A-Za-z0-9._/ -' '?'
        #   -> requirements-a.txt? requirements-b.txt
        # so sanitizing the JOINED list DESTROYS the separator. Sanitizing each
        # element instead keeps the `, ` (a literal of this script, never passed
        # through tr) while turning a comma inside a NAME into `?` — a forged
        # name cannot pass itself off as a real pair. Sensor: (d3) of
        # sca-python.test.sh, which goes red precisely on the after-join move.
        unpinned="${unpinned:+$unpinned, }$(sanitize_display "$rel_rf")"
      fi
    done
    if [ -n "$unpinned" ]; then
      log "[python] requirements non épinglé — résolution refusée, posture lock-only: $unpinned — python coverage DEGRADED"
      echo "python: requirements non épinglé — résolution refusée, posture lock-only ($unpinned)" >> "$OUT/.degraded"
      PYTHON_STATUS="degraded"
    fi
    # ---- LOCKFILES -> pins (T-00000462, case #143) --------------------------
    # PLACEMENT IS LOAD-BEARING, and it is not a matter of taste. This block sits
    # INSIDE the `else` above, AFTER the `$unpinned` block and BEFORE the
    # `pin_args` test. Moved one level out — past this branch's closing `fi` —
    # the `pin_args=()` reset at the top of the branch would ERASE the pins the
    # locks produced: `pip-audit` would never run, and PYTHON_STATUS would stay
    # `scanned` on a run that scanned nothing. That is the exact false-`scanned`
    # this lot exists to close, reintroduced by a placement.
    if [ "${#py_locks[@]}" -gt 0 ]; then
      pl_names=""
      for lk in "${py_locks[@]}"; do pl_names="${pl_names:+$pl_names, }${lk##*/}"; done
      # ONE call, variadic — NEVER a loop over the locks. `--out` TRUNCATES, so a
      # second call would overwrite the first lock's pins and the run would audit
      # a strictly smaller set than the one it reports.
      # PYTHON ABSENT (T-01M4XF9JQXK6QJHHBFQZX7AGAJ): py_lock_pins.py is NOT
      # launched — never an empty command. Measured before this guard: `"$PY" …`
      # with PY="" ran `""`, rc 127, and the reason line below said the locks were
      # `illisible(s)`, `rc=127` — a HEALTHY lock blamed for a missing reader. The
      # cause is named instead, in the first branch of the chain below, which
      # stays INSIDE this lock block (placement constraint above).
      pl_out=""; rc=0
      if [ -n "$PY" ]; then
        pl_out="$("$PY" "$SCRIPT_DIR/py_lock_pins.py" --out "$OUT/pins-from-locks.txt" "${py_locks[@]}" 2>"$OUT/py-locks.log")"
        rc=$?
      fi
      # FAIL-CLOSED ON THE FORMAT. `$pl_out` is a CONTRACT between two languages
      # (a Python stdout line parsed by this bash), and a contract that drifts
      # must NOT be read in silence: the glob demands the two keys AND a digit
      # after each, so a reworded, reordered or aggregated line lands in (ii)
      # rather than being half-parsed into an empty counter that compares as 0.
      pl_ok=0
      case "$pl_out" in
        'excluded_root='[0-9]*' excluded_dep='[0-9]*) pl_ok=1 ;;
      esac
      if [ -z "$PY" ]; then
        # (0) NOT READ. No pin, so pip-audit does not run on these locks; the
        # perimeter is incomplete and said so. `$pl_names` is our own literals.
        log "[python] locks: $pl_names non lus — python absent (py_lock_pins.py non lancé) — python coverage DEGRADED"
        echo "python: $pl_names non lus (python absent) — py_lock_pins.py non lancé" >> "$OUT/.degraded"
        PYTHON_STATUS="degraded"
      elif [ "$rc" -ne 0 ] || [ "$pl_ok" -eq 0 ]; then
        # (ii) EVERY non-zero rc, whatever it is — a BOUND, never an enumeration
        # (L-00000187): there is no rc this branch leaves untreated. Degrades
        # even when `pin_args` already holds pinned requirements, because the
        # perimeter is incomplete either way. `$pl_names` is built from our own
        # three literals; `$rc` is an integer.
        log "[python] locks: $pl_names illisible(s) — résolution ÉCHOUÉE (pas refusée), rc=$rc — python coverage DEGRADED"
        echo "python: $pl_names illisible(s) — résolution ÉCHOUÉE (pas refusée), rc=$rc, voir py-locks.log" >> "$OUT/.degraded"
        PYTHON_STATUS="degraded"
      elif [ -s "$OUT/pins-from-locks.txt" ]; then
        # (i) NOMINAL. `-s` is trustworthy because the `rm -f` above ran THIS
        # run: the file is fresh by construction, never a survivor.
        pin_args+=(-r "$OUT/pins-from-locks.txt")
        # bash 3.2 expansions only, no `[[`. The format was validated just above.
        ex_root="${pl_out#excluded_root=}"; ex_root="${ex_root%% *}"
        ex_dep="${pl_out##*excluded_dep=}"
        # `grep -c .` and not `wc -l`: it counts NON-EMPTY lines and reads the
        # same number whether or not the file ends with a newline. The contract
        # says it does; the count does not depend on that being true.
        pl_pins="$(LC_ALL=C grep -c . "$OUT/pins-from-locks.txt")"
        # WRITTEN ON THE NOMINAL PATH, ALWAYS, EVEN AT ZERO (L-00000388). An
        # exclusion that leaves no byte here is how a run publishes `scanned`
        # over an AMPUTATED perimeter — the scan really ran, and its status is
        # sincere about what it DID look at, which is what makes it hard to see.
        log "[python] locks ($pl_names): $pl_pins pin(s), $ex_root entrée(s) racine exclue(s) (structurel), $ex_dep dépendance(s) hors registre exclue(s)"
        # AND ONLY `ex_dep` DEGRADES. The root entry is the scanned project
        # itself, not a dependency, so its exclusion is structural and is NOT a
        # coverage hole; counting it here would make every uv project
        # permanently degraded, and a permanent degradation stops being read.
        # `ex_dep` > 0 IS a hole, and it gets the same three writes Java already
        # gets for an offline NVD base — log, reason line, status.
        if [ "$ex_dep" -gt 0 ]; then
          log "[python] $ex_dep dépendance(s) à source non-registre (git/url/path) EXCLUE(S) du périmètre — python coverage DEGRADED"
          echo "python: $ex_dep dépendance(s) à source non-registre EXCLUE(S) du périmètre — couverture BORNÉE" >> "$OUT/.degraded"
          PYTHON_STATUS="degraded"
        fi
      else
        # (iii) rc=0 and NO file: the locks were read perfectly and hold nothing
        # auditable. Not a failure, and not a scanned perimeter either. `$pl_out`
        # is two integers of ours by contract; the belt costs nothing.
        log "[python] locks ($pl_names) lus, aucune dépendance de registre à épingler — python coverage DEGRADED"
        echo "python: locks sans dépendance de registre ($(sanitize_display "$pl_out"))" >> "$OUT/.degraded"
        PYTHON_STATUS="degraded"
      fi
    fi
    if [ "${#pin_args[@]}" -gt 0 ]; then
      log "[python] pip-audit --no-deps (lock-only, no resolution) on pinned requirements"
      # pip-audit exits non-zero WHEN VULNERABILITIES ARE FOUND — that is a
      # finding, not a run failure; the gate comes from waiver_filter reading
      # pip-audit.json, so only an ABSENT/empty report is a degraded run.
      ( cd "$TGT" && pip-audit --no-deps "${pin_args[@]}" -f json ) \
        > "$OUT/pip-audit.json" 2>"$OUT/pip-audit.log"
      pa_rc=$?
      if [ ! -s "$OUT/pip-audit.json" ]; then
        log "[python] pip-audit produced no report (exit $pa_rc; network? see pip-audit.log) — python coverage DEGRADED"
        echo "python: pip-audit run produced no report (exit $pa_rc) — see pip-audit.log" >> "$OUT/.degraded"
        PYTHON_STATUS="degraded"
        rm -f "$OUT/pip-audit.json"
      fi
    fi
  fi
fi

# T-00000488 — name any not-covered ecosystem manifest present at this module root.
name_uncovered "$TGT" "$OUT/.degraded"

# ---- IaC misconfiguration (Dockerfile/Terraform/Kubernetes/Helm) via trivy --
# Unlike the ecosystem blocks above, there is no single manifest to gate on:
# `trivy config` recursively finds and scans IaC files itself (Dockerfile,
# *.tf, docker-compose, k8s manifests, Helm charts) under the scan target — a
# target with at least one such file yields a report with a "Results" key
# (even `"Results":[]`-worth of failures if everything passes); a target with
# NONE yields a bare envelope with no "Results" key at all (see the scanned=1
# gating below — this distinction is what keeps a plain IaC-less module from
# becoming a false GO). Misconfig scanning is OFFLINE (built-in check bundle,
# no vulnerability DB download needed).
if have trivy; then
  log "[iac] trivy config --format json (misconfiguration, offline checks)"
  TRIVY_TMP=""
  # NO trap here: bash has ONE EXIT trap slot, and it belongs to cleanup() (set
  # once, near the top, before the reports lock). cleanup() removes $TRIVY_TMP
  # when it is non-empty. A second `trap ... EXIT` would REPLACE cleanup — the
  # lock would then outlive this run — instead of stacking with it.
  # mktemp (not a $$ name): unpredictable path + 0600 perms while the report
  # briefly sits on disk (CWE-59/377 — same lesson as the gitleaks/semgrep shards).
  TRIVY_TMP="$(mktemp "${TMPDIR:-$OUT}/.trivy-scan.XXXXXX")"
  # `--` marks the end of options: TGT is always a resolved absolute directory
  # here, never user-controlled option-like text, but the guard is free and
  # matches the discipline used everywhere a path reaches a CLI in this kit
  # (CWE-88 argument-injection lesson from the semgrep shard).
  trivy config --quiet --format json --output "$TRIVY_TMP" -- "$TGT" >/dev/null 2>&1
  rc=$?
  # scanned=1 ONLY when trivy actually found IaC file(s) to evaluate — never
  # unconditionally on `have trivy`. Otherwise a target with NO manifest and
  # NO IaC file would still flip scanned=1 just because trivy is installed,
  # turning a legitimate NO-ECOSYSTEM (exit 2) into a false GO — the one thing
  # this dispatcher must never do.
  #
  # A plain non-empty-file check (`-s`) is NOT enough: trivy always writes a
  # valid JSON envelope (SchemaVersion/ArtifactName/...) even when it found
  # ZERO files of any config type to scan — confirmed empirically (v0.72.0):
  # a directory containing only a README.md still yields a ~280-byte non-empty
  # report with no "Results" key at all. The real "did trivy actually scan
  # something" signal is the presence of the top-level "Results" key: it is
  # emitted (even as `"Results":[]` for a scanned-but-all-pass IaC file) iff
  # trivy identified at least one config file to evaluate.
  if [ -s "$TRIVY_TMP" ] && grep -q '"Results"' "$TRIVY_TMP"; then
    scanned=1
    IAC_STATUS="scanned"
    cp "$TRIVY_TMP" "$OUT/trivy-config.json"
  else
    log "[iac] trivy found no IaC file to scan (or the scan produced no report, exit $rc) — IaC coverage DEGRADED"
    echo "trivy: no IaC file found to scan (or scan produced no report, exit $rc)" >> "$OUT/.degraded"
    IAC_STATUS="degraded"
  fi
  rm -f "$TRIVY_TMP"
else
  log "[iac] trivy not installed — IaC misconfiguration coverage DEGRADED"
  echo "trivy: not installed" >> "$OUT/.degraded"
  IAC_STATUS="degraded"
fi

# java collapses maven+gradle: degraded if EITHER sub-tool degraded, scanned
# if EITHER actually ran, skipped only if NEITHER manifest was present.
if   [ "$MAVEN_STATUS" = "degraded" ] || [ "$GRADLE_STATUS" = "degraded" ]; then JAVA_STATUS="degraded"
elif [ "$MAVEN_STATUS" = "scanned" ]  || [ "$GRADLE_STATUS" = "scanned" ];  then JAVA_STATUS="scanned"
else JAVA_STATUS="skipped"; fi

# scan.sca emission (T-00000018 shard 2, item 5) — a PER-ECOSYSTEM status
# map, never one collapsed tri-state (see the vars' own comment above).
emit_sca() {
  # T-00000041 — same host/root propagation as gitleaks-scan.sh's emitter;
  # see the rationale there (registered on 4 hosts, bridge defaults to claude).
  EVT_HOST="${AGENTS_HOOK_HOST:-claude}" CLAUDE_PROJECT_DIR="$ROOT" \
    bash "$ROOT/.claude/hooks/emit-event.sh" scan.sca \
    "status:={\"npm\":\"$NPM_STATUS\",\"supply_chain\":\"$SUPPLY_STATUS\",\"java\":\"$JAVA_STATUS\",\"swift\":\"$SWIFT_STATUS\",\"python\":\"$PYTHON_STATUS\",\"iac\":\"$IAC_STATUS\",\"go\":\"$GO_STATUS\",\"rust\":\"$RUST_STATUS\",\"dotnet\":\"$DOTNET_STATUS\",\"php\":\"$PHP_STATUS\",\"ruby\":\"$RUBY_STATUS\"}" \
    >/dev/null 2>&1 || true
}

echo "== reports in $OUT =="
if [ "$scanned" = "0" ]; then
  announce_degraded "$OUT/.degraded"
  echo "SCA: no known ecosystem detected."
  emit_sca   # still worth a dated fact: every ecosystem legitimately "skipped"
  [ "$CHANGED_ONLY" = "1" ] && exit 0   # hook context: exit 2 would block the host
  exit 2
fi

# ---- Effective gate: normalize findings, apply the waiver register ----------
if [ -n "$PY" ]; then
  summary="$("$PY" "$SCRIPT_DIR/waiver_filter.py" \
              --reports-dir "$OUT" --waivers "$WAIVERS" \
              --root "$TGT" --gate-level "$GATE_LEVEL")"
  gate=$?
else
  # Python absent: the call is NOT executed (never an empty command), and
  # gate takes 127, the rc bash gives a command it cannot find — the value
  # the python-absent branch below has always received.
  summary=""
  gate=127
fi
# FAIL-CLOSED (T-01M4X6FJG4XZ3ZN2BJCVVEMGXY, class-1). The pivot
# effective-verdict.json is FRESH only when waiver_filter returned a verdict it
# knows (rc 0 = GO, rc 1 = NO-GO) AND printed its `SUMMARY ` line, which it
# prints AFTER writing the pivot (waiver_filter.py:331-334) — so the line proves
# the write. Anything else used to fall through to GO, exit 0, with the PREVIOUS
# run's pivot left in place for sca-watch, audit_report and the dashboard to
# read as today's: measured with SCA_GATE_LEVEL=medium (argparse rc 2) on 19
# known HIGH. Now: exit 1 (a code every consumer already reads as a block), the
# stale pivot REMOVED (its absence is what sca-watch.sh, audit_report.py and
# summary.json already handle), the reason NAMED in .degraded before the
# announcement below. Only `$wf_rc` (our own rc) and `$GATE_LEVEL` through
# sanitize_display reach the message.
# PYTHON ABSENT (rectified decision, « DEGRADED VISIBLE »): the call above is
# skipped and gate set to 127, so the pivot is never fresh. The gate does NOT
# block (exit code as before), but the stale pivot is removed the same way and
# `waiver_filter: not run (python absent)` reaches .degraded, hence the
# COVERAGE DEGRADED banner — never again a mute GO with "PYTHON 3 NOT FOUND" on
# stderr as the only signal (measured before this revision).
# Bound: in a PROTECTED module the --all-modules loop turns this exit 1 into
# rc 3 TRACKED-NOT-GATING, like any real finding of that module — EXCEPT under
# wf_rc 3 (a scanner report unreadable, E1): that line is read there, and the
# module is ERROR, gating. Any other wf_rc (2: SCA_GATE_LEVEL invalid or the
# register unreadable; a 1 without its SUMMARY line) keeps the substitution.
# The python-absent run is also NAMED on the two surfaces a reader trusts as a
# verdict (decision S-01M4X99ZY9, DEGRADED VISIBLE, exit 0 unchanged): the last
# line reads `GO (DEGRADED — no effective verdict)`, never a bare `GO`, and the
# audit row says `"verdict":"DEGRADED"`. `no_verdict` (1/0) carries it down.
# This is the single-module form. Under --all-modules without Python the module
# loop is never reached (module discovery needs Python): its own python-absent
# branch, at the top of --all-modules, answers DEGRADED the same way (exit 0,
# banner, last line, audit row) — never NO-ECOSYSTEM (T-01M4XF9JQXK6QJHHBFQZX7AGAJ).
# `wf_rc` (raw rc) and `pivot_fresh` (1/0) stay readable below this block.
# Witness: .agents/security/sca-gate-failclosed.test.sh.
wf_rc="$gate"
pivot_fresh=0
no_verdict=0
if [ "$wf_rc" = "0" ] || [ "$wf_rc" = "1" ]; then
  case "$summary" in
    "SUMMARY "*) pivot_fresh=1 ;;
  esac
fi
if [ "$pivot_fresh" -eq 0 ]; then
  rm -f "$OUT/effective-verdict.json"
  if [ -n "$PY" ]; then
    gate=1
    echo "waiver_filter: no fresh effective verdict (rc $wf_rc)" >> "$OUT/.degraded"
    log "SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=$wf_rc, gate_level=$(sanitize_display "$GATE_LEVEL"), no fresh effective verdict (fail-closed)"
  else
    no_verdict=1
    echo "waiver_filter: not run (python absent)" >> "$OUT/.degraded"
  fi
fi
echo "  $summary   (register: $WAIVERS)"
announce_degraded "$OUT/.degraded"
emit_sca

# ---- Audit line (every run, even CLEAN — silent != invisible) ---------------
# The SUMMARY counters are appended ONLY when waiver_filter printed its
# `SUMMARY ` line. With an empty summary (python absent, or a fail-closed run
# that printed nothing) the old form wrote `"gate_level":"high",""}` — not JSON,
# so dashboard_readers counted the row `malformed` and the run vanished from
# the Security view (measured before this revision).
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
verdict="GO"; [ "$gate" = "1" ] && verdict="NO-GO"
if [ "$verdict" = "GO" ] && [ "$no_verdict" -eq 1 ]; then verdict="DEGRADED"; fi
summary_fields=""
case "$summary" in
  "SUMMARY "*) summary_fields=",\"$(echo "$summary" | sed 's/SUMMARY //; s/ /","/g; s/=/":"/g')\"" ;;
esac
printf '{"ts":"%s","mode":"scan","entry":"sca-scan.sh","module":"%s","verdict":"%s","gate_level":"%s"%s}\n' \
  "$TS" "$(sanitize_display "$SLUG")" "$verdict" "$GATE_LEVEL_AUDIT" "$summary_fields" \
  >> "$ROOT/.agents/state/local/sca-reports/audit-log.jsonl"

[ "$gate" = "1" ] && { echo "SCA GATE (effective, waivers applied): NO-GO"; exit 1; }
[ "$verdict" = "DEGRADED" ] && { echo "SCA GATE (effective, waivers applied): GO (DEGRADED — no effective verdict)"; exit 0; }
echo "SCA GATE (effective, waivers applied): GO"; exit 0
