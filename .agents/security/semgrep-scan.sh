#!/usr/bin/env bash
# .agents/security/semgrep-scan.sh — SAST INPUT for the class-1 code-review gate.
#
# Runs semgrep on the files touched by the current working-tree diff (changed
# + untracked vs HEAD) — never the whole repo, never git history.
#
# PERIMETER MODES (T-00000364):
#   (default)     the working-tree diff: changed + untracked vs HEAD.
#   --at <ref>    the files THAT COMMIT changed (`<ref>~1..<ref>`, root-commit
#                 safe). This exists because the working-tree diff CANNOT see
#                 committed code, and AGENTS.md's nominal order runs the security
#                 gate AFTER the dev stage — which commits. So on the nominal
#                 path the default perimeter is empty BY CONSTRUCTION, and a
#                 gate that reads that as "clean" is a gate that never looked.
#                 `--at HEAD` is the remedy the degraded messages now name.
#
# WHAT GIT COMMITS IS READ TOO (T-01M4XY8NC97JBSQP6C28AFD7QP and its six
# sibling tasks). Beside the working-tree files, the perimeter carries GIT
# OBJECTS, read raw by `git cat-file` and scanned under a LABEL: `index:<rel>`
# (an index entry that differs from HEAD — the root and each reachable
# submodule at the gate, the root alone at the hook Stop; never under `--at`)
# and `commit:<rel>` (a committed path of the target whose working-tree copy
# differs from the POINTE, HEAD or the `--at` ref, or is not a readable file).
# Only the pointe is read, never an intermediate commit. A base with no merge
# base with HEAD degrades and falls back to HEAD alone, said. The census runs
# NO code of the scanned repository through a CLOSED list of cut channels
# (fsmonitor, hooks, filter drivers, external diff, textconv, lazy fetch of a
# partial clone, `log.showSignature`, `log.showRoot`); a channel outside that
# list is NOT declared cut — the list and its bound are in
# README-SECURITY-SCAN-SETUP.md. Never read this as "runs no code".
#
# HONESTY RESERVE — READ THIS BEFORE QUOTING A GREEN FROM THIS SCRIPT. The
# default ruleset is a SMALL, OFFLINE set of real sinks over a BOUNDED list of
# languages — the coverage table at the top of semgrep.yml is the authority on
# what is covered and what is a declared absence — and it does NOT model
# argument injection into a command this repo PRINTS for a human to run (the
# CWE-88 class that L-009 and T-00000330 both landed on). A "clean" verdict here
# is therefore a NARROW coverage, never a quitus: it means those rules found
# nothing on the perimeter that was actually inspected. The scope line printed
# beside the verdict is the part that says how much was looked at. (The rule
# COUNT is deliberately NOT quoted here: a literal here would be a delayed lie
# the day a rule is added — L-00000111/L-00000187.)
#
# This script does not itself gate anything: it is a machine-found candidate
# list that
# `security-code-review` triages. The AGENT decides which findings are truly
# class-1 (HIGH/CRITICAL, non-waivable) per AGENTS.md § Security gate. This
# script implements no exception/acceptance path and applies no filter — that
# concept only exists on the dependency axis (classes 2-3), a different file
# entirely, and is never consulted here.
#
# Config: SEMGREP_CONFIG env var, default `.agents/security/semgrep.yml` — a
# small OFFLINE ruleset (no network needed). Override with a registry ruleset
# for full coverage, e.g. SEMGREP_CONFIG=p/security-audit (needs network).
#
# HOOK MODE (T-00000459, Lot A) — `--hook --event=<post|stop>` is now AVAILABLE.
# REGISTERED by Lot B (T-00000476) on FIVE registries for SIX hosts — coverage
# 3 measured / 0 inherited / 1 assumed / 2 inert-measured: claude and codex
# MEASURED (refusal channel and payload graphy), copilot MEASURED (own branch since
# the 2026-10-12 alignment: tool graphy `create` MEASURED, Stop `decision:block`
# MEASURED at P3, and the post `additionalContext` at the ROOT, typed by the SDK,
# MEASURED reaching the model with a real finding: 2026-10-23, Copilot CLI 1.0.96), kimi ASSUMED (channel by twin, tool
# graphies never measured), gemini INERT-MEASURED (G0, 2026-10-12: `.agents/hooks.json`
# is not read by Gemini CLI 0.63.0 — the hook never fires) and antigravity
# INERT-MEASURED on post (payload without a path — the hook says so) while its
# Stop, IF the host fires it, scans the dirty tree — unmeasured. Never "six hosts covered". The EVENT is read from the FLAG first,
# hook_event_name only as a fall-back, post by default — the script never guesses
# it from a payload graphy no one measured on the host. `--event=post` scans the
# EDITED FILE(S); `--event=stop` scans the DIRTY TREE ONLY (never the commits
# since a base — a Stop that re-blocks on a committed file the session never
# touched is a loop with no exit). The GATE keeps its own default perimeter (the
# target); only the hook narrows to post|stop. ABSENT host marker ≠ UNKNOWN host
# marker: an absent AGENTS_HOOK_HOST defaults to `claude` (the one host whose
# registry cannot carry the variable), an unknown value gets two channels + exit
# 2. The hook's tool-name list is a BOUND, said out loud, never an assumed total.
#
# DEGRADED FORM, PER EVENT: post = ONE object carrying BOTH `systemMessage` and
# `hookSpecificOutput.additionalContext`; stop = `systemMessage` only. IN SERVICE:
# systemMessage on claude PostToolUse (post-edit-check.sh), additionalContext on
# codex PostToolUse (post_edit_check.py). NOT MEASURED, said rather than counted:
# whether codex/copilot/gemini RENDER a systemMessage on PostToolUse, and whether
# any host tolerates the two-key object. A host that ignores both keys turns this
# notice into a silence — this header names that hole instead of claiming six hosts.
#
# Exit codes (mirrors gitleaks-scan.sh's "never a false CLEAN, never a false
# block" discipline; SAST findings are class-1, not class-0):
#   0  clean — OR any announced COVERAGE DEGRADED path (semgrep not on PATH,
#      scan timed out, report unparseable or malformed — valid JSON without a
#      `results` list of objects, or errors/paths mistyped —, perimeter blind;
#      in hook mode also a report phase that died before any verdict). An absent or
#      unmeasured scope is never presented as a false CLEAN. IN HOOK MODE every
#      benign or degraded path is exit 0 too (a hook must never freeze a host):
#      mute (ignored tool, uncovered file, no path), or an announced DEGRADED.
#      A path of the perimeter that could NOT BE READ (behind an unsearchable
#      directory, unreadable, a failed git census, an unreachable submodule) is
#      COUNTED and said, never dropped in silence: COVERAGE DEGRADED, no benign
#      sentence, no common verdict, rc 0, gate AND hook — degrade, never block
#      (pilot decision S-01M4XWS5WEV0DDV98HP04H8K9M, T-01M4X9PP7FED0570PMPSYGA0V8).
#   1  findings present — signal for the calling AGENT to triage (gate mode).
#   2  USAGE error (an unknown option, --at with no ref, a bad --event, --hook
#      combined with a perimeter option); AND, IN HOOK MODE ONLY, a blocking
#      finding on the `claude` or an UNKNOWN host marker (post: stderr re-fed to
#      the model, edit kept on disk; stop: at most once per session, never at
#      the Stop of a Copilot SUB-agent — the root judges the same tree). Envelope
#      hosts (codex|copilot|gemini) get the event-form on stdout + exit 0 instead.
#      Returning 0 on a mistyped flag would hand the caller a "clean" for a
#      perimeter never built — the false CLEAN the rest of this file exists to
#      avoid.
#
# BASH 3.2 PARSABILITY (macOS without Homebrew, where the PATH bash IS 3.2):
# this script MUST parse under bash 3.2 — measured by the suite wherever a
# bash < 4 exists, degradation ANNOUNCED otherwise. FORBIDDEN form: a heredoc
# opened INSIDE a command substitution — bash < 4.4 reads the heredoc body as
# shell and leaves a quote open on an ODD apostrophe count (the T-00000477
# crash).
#
# CORRIGÉ LE 2026-09-09 (T-00000481) — ces trois lignes prescrivaient de
# DÉQUOTER la substitution. C'est mesuré INOPÉRANT : sous /bin/bash 3.2.57, la
# forme déquotée échoue exactement comme la quotée dès que le corps porte un
# nombre IMPAIR d'apostrophes. La quote n'a jamais été la cause. Et la consigne
# a été SUIVIE : trois sites ont été écrits déquotés, invisibles au localisateur
# qui exigeait la quote.
#
# REMÈDE RÉEL : sortir le heredoc de la substitution — l'écrire dans un fichier,
# puis le lire. Une parité paire n'est pas un remède : elle est accidentelle.
# Détail et mesures : .agents/security/bash-parse-oldest.test.sh
set -uo pipefail

# ---- SORTIE PRÉCOCE SOUS COPILOT : LECTURE LOCALE (T-01M4RWC6VHHN479J2A9RRY1BE3)
# Sous AGENTS_HOOK_HOST=copilot SEULEMENT, et sur la seule forme de la
# registration postToolUse (`--hook --event=post`, exactement ces deux
# arguments) : un outil de lecture locale, identifié POSITIVEMENT par son nom
# de premier niveau, n'a rien écrit à scanner et sort avant tout git, mktemp ou
# mkdir. Définie ICI, appelée juste après la résolution de PY : la fenêtre qui
# suit le diagnostic « PYTHON 3 NOT FOUND » reste celle qu'épingle
# .agents/evals/test_python_hook_launchers.py. Le nom est lu et comparé DANS
# python, sur la liste OUTILS_LECTURE_COPILOT, copie jumelle de celle de
# .codex/hooks/_common.py (filet : .agents/evals/test_copilot_early_exit.py) ;
# jamais relu comme du shell. Tout le reste — --event=stop, forme groupée ou
# HYBRIDE (`toolCalls` ou `tool_calls` à côté d'un nom listé : un second
# outil), graphies du nom en désaccord, nom vide ou inconnu, charge illisible,
# python absent, stdin terminal — suit le chemin entier, inchangé. La charge,
# lue sous copilot seulement, est réinjectée sur stdin quand le nom n'est pas
# listé : run_hook_mode la relit entière.
sortie_precoce_copilot() {  # "$@" = les arguments du script
  local forme=0 charge
  if [ "$#" -eq 2 ]; then
    case "$1 $2" in
      "--hook --event=post"|"--event=post --hook") forme=1 ;;
    esac
  fi
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
        # processus : test_copilot_early_exit.py (v). Un exec dont la
        # redirection échoue ne fait pas sortir le script : son échec se lit au
        # statut, et le hook l'ANNONCE sans bloquer ; le scan du Stop reste entier.
        exec <<<"$charge" || echo "COVERAGE DEGRADED: SAST hook - charge copilot non reinjectable sur stdin, appel juge sur une charge vide ; le scan du Stop reste entier" >&2
      fi
      ;;
  esac
}

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
# No lazy fetch for ANY git below (T-01M4Z24V0J813T40XRW3S4VW67, the form of
# gitleaks-scan.sh): in a partial clone, fetching a missing blob RUNS
# `remote.<name>.uploadpack` (measured: the census diff, ls-files --others, a
# cat-file of an index object). A refused fetch fails, and is counted. git >=
# 2.45; older: no effect — see paresseux (README-SECURITY-SCAN-SETUP.md). The
# variable is not trusted alone: `--no-lazy-fetch` is also passed on every git
# call that carries GN, wherever this git has it (GN, below).
export GIT_NO_LAZY_FETCH=1
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ROOT="$(cd "$ROOT" && pwd)"            # canonicalize (Git Bash: git prints C:/..., pwd prints /c/...)
OUT="$ROOT/.agents/state/local/sca-reports"
OUT_DEPOT="$OUT"   # the in-repository path, which both censuses skip even when $OUT becomes private (out_prive)
CFG="${SEMGREP_CONFIG:-.agents/security/semgrep.yml}"  # offline default; override for registry coverage

have() { command -v "$1" >/dev/null 2>&1; }
# ---- $OUT IS NEVER REACHED THROUGH A SYMBOLIC LINK (T-01M4XY8NC97JBSQP6C28AFD7QP)
# The scanned repository is UNTRUSTED, and `.agents/.gitignore` ignores
# `state/local/` as a DIRECTORY only: a committed symbolic link at `.agents`,
# `.agents/state`, `.agents/state/local` or `sca-reports` is checked out like
# any file, and every write below — this mkdir, the removal of the previous
# verdict, the audit line, the git objects, the hook's markers and work files,
# the scan event of a kit-shaped repository (`.agents/state/events/`) —
# would land where the link points, OUTSIDE the repository. Each component
# under ROOT is tested with `[ -L ]` BEFORE this, the first write of the
# script, and so are the two FIXED names written in place (a committed link
# there was measured at be913df4: the Stop truncated the file behind
# `semgrep-hook/stop-propre` and appended a line to the one behind
# `audit-log.jsonl`). A link NEVER makes the scan blind (closing review M1: a
# single committed link turned the gate off): the run goes on in a PRIVATE
# directory (out_prive, made under TMPDIR — the gate after its options, the
# hook after reading its payload), the loss is said (its audit line, its common
# verdict, the hook's markers and clean-verdict cache are not kept, its scan
# event is not emitted — emit_scan), and only
# when that directory cannot be made does the run refuse before any write.
# ROOT itself is not tested (the caller stands there). BOUNDS, said in
# README-SECURITY-SCAN-SETUP.md: a link made AFTER this test is not seen; no
# other FILE under $OUT is tested, because none is written in place at a
# guessable name — each is made by mktemp/mkstemp (O_EXCL, random name) or
# replaced by os.replace (`semgrep-verdict.json`), grep of 2026-10-16 (closing
# review 2, F1: the PARSE's `.semgrep-unparsed.<pid>` was the last one).
OUT_LIEN=""
for _ol in .agents .agents/state .agents/state/local .agents/state/local/sca-reports \
           .agents/state/local/sca-reports/audit-log.jsonl \
           .agents/state/local/semgrep-hook .agents/state/local/semgrep-hook/stop-propre; do
  if [ -L "$ROOT/$_ol" ]; then
    OUT_LIEN="$_ol"
    break
  fi
done
[ -n "$OUT_LIEN" ] || mkdir -p "$OUT"
# out_prive — called only when OUT_LIEN is set: $OUT becomes a fresh private
# directory under TMPDIR (OUT_PRIVE, removed by the EXIT trap of the gate and of
# the hook — never the link path itself, which may resolve OUTSIDE the
# repository), or "" when it cannot be made.
OUT_PRIVE=""
out_prive() {
  local _t
  _t="${TMPDIR:-/tmp}"; _t="${_t%/}"
  OUT_PRIVE="$(mktemp -d "$_t/semgrep-out.XXXXXX" 2>/dev/null)" || OUT_PRIVE=""
  OUT="$OUT_PRIVE"
}
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- options (T-00000364) ----------------------------------------------------
# Pure string handling only: the REF is not validated here but at perimeter-build
# time, where audit()/emit_scan() exist, so an unusable ref degrades through the
# same announced channel as every other failure path instead of dying bare.
# An UNKNOWN option is refused loudly rather than ignored — a silently dropped
# flag makes a caller believe it scanned a perimeter it never scanned.
AT_REF=""
SINCE_BASE=""
ATTEST_FILE=""
AT_SEEN=0
SINCE_SEEN=0
ATTEST_SEEN=0
HOOK=0                # --hook: run as a registered host hook (Lot A of T-00000459)
HOOK_EVENT=""         # --event=<post|stop>: the event the REGISTRATION knows
HOOK_EVENT_SEEN=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --at)
      shift
      [ "$#" -gt 0 ] || { echo "semgrep-scan: --at needs a git ref (e.g. --at HEAD)" >&2; exit 2; }
      AT_REF="$1"; AT_SEEN=1; shift ;;
    --at=*) AT_REF="${1#--at=}"; AT_SEEN=1; shift ;;
    --since)
      shift
      [ "$#" -gt 0 ] || { echo "semgrep-scan: --since needs a git ref (e.g. --since main)" >&2; exit 2; }
      SINCE_BASE="$1"; SINCE_SEEN=1; shift ;;
    --since=*) SINCE_BASE="${1#--since=}"; SINCE_SEEN=1; shift ;;
    --attest)
      shift
      [ "$#" -gt 0 ] || { echo "semgrep-scan: --attest needs a file path" >&2; exit 2; }
      ATTEST_FILE="$1"; ATTEST_SEEN=1; shift ;;
    --attest=*) ATTEST_FILE="${1#--attest=}"; ATTEST_SEEN=1; shift ;;
    --hook) HOOK=1; shift ;;
    --event)
      shift
      [ "$#" -gt 0 ] || { echo "semgrep-scan: --event needs a value (post|stop)" >&2; exit 2; }
      HOOK_EVENT="$1"; HOOK_EVENT_SEEN=1; shift ;;
    --event=*) HOOK_EVENT="${1#--event=}"; HOOK_EVENT_SEEN=1; shift ;;
    --) shift; [ "$#" -eq 0 ] || { echo "semgrep-scan: takes no positional arguments (got '$1')" >&2; exit 2; } ;;
    -h|--help)
      echo "usage: semgrep-scan.sh [--at <git-ref>] [--since <base-ref>]" >&2
      echo "  (default)      perimeter = the TARGET: commits since the base (when it is" >&2
      echo "                 knowable) plus the dirty tree. This is the mode the GATE" >&2
      echo "                 renders its verdict in." >&2
      echo "  --at <ref>     SLICE AUDIT: the files THAT COMMIT changed" >&2
      echo "  --since <base> SLICE AUDIT: the files changed on <base>...HEAD (merge-base)" >&2
      echo "  --attest <f>   verify an ENUMERATIVE attestation against the perimeter" >&2
      echo "  --hook         run as a REGISTERED HOST HOOK: read a JSON payload on" >&2
      echo "                 STDIN, scan, emit per host/event (Lot A of T-00000459)." >&2
      echo "  --event <e>    post|stop — the event the REGISTRATION knows. post scans" >&2
      echo "                 the edited file(s); stop scans the DIRTY TREE only. When" >&2
      echo "                 absent, hook_event_name is the fall-back, else post." >&2
      exit 0 ;;
    *) echo "semgrep-scan: unknown option '$1' (see --help)" >&2; exit 2 ;;
  esac
done

# ---- ONE validator, run AFTER the parse, on the VALUE (T-00000370) -----------
# ARGUMENT INJECTION ON THE REF (CWE-88 — the class L-009 landed on). A ref
# reaches `git rev-parse`, `git diff` and `git show` in REVISION position, and in
# the three-dot form the base is embedded in a SINGLE argument (`$BASE...HEAD`),
# so a leading-dash base turns the whole argument into a git OPTION. Git has no
# `--`-style escape that makes a leading-dash string unambiguously a revision, so
# the only sound guard is to refuse the shape: no legitimate git ref begins with
# `-` (git itself forbids it in refnames).
#
# AND AN EMPTY VALUE IS A MISSING VALUE, never a silent fallback. The previous
# shape carried the arity check INSIDE the `--at` branch, so the glued form
# `--at=` set an empty ref that fell through `[ -n "$AT_REF" ]` and switched the
# perimeter to the dirty tree WITHOUT A WORD — while the header three lines above
# promises the opposite ("a silently dropped flag makes a caller believe it
# scanned a perimeter it never scanned"). A control placed in one parse branch
# guards one entry path out of two; the validation therefore lives here, once,
# after the parse, and applies to both forms of both options. [L-00000268]
validate_ref_option() {  # $1 flag  $2 seen(0|1)  $3 value
  [ "$2" -eq 1 ] || return 0
  case "$3" in
    "") echo "semgrep-scan: $1 needs a git ref — an EMPTY value is a MISSING value, not a silent fall-back to the default perimeter" >&2; exit 2 ;;
    -*) echo "semgrep-scan: $1 ref must not begin with '-' (it would be read as a git OPTION, not a revision — CWE-88): '$3'" >&2; exit 2 ;;
  esac
}
validate_ref_option --at    "$AT_SEEN"    "$AT_REF"
validate_ref_option --since "$SINCE_SEEN" "$SINCE_BASE"
# `--attest` takes a PATH, not a revision, so the leading-dash/CWE-88 half does
# not apply — but the EMPTY-value half does, and for the same reason: a flag
# accepted and then ignored makes a caller believe something was verified.
if [ "$ATTEST_SEEN" -eq 1 ] && [ -z "$ATTEST_FILE" ]; then
  echo "semgrep-scan: --attest needs a file path — an EMPTY value is a MISSING value" >&2
  exit 2
fi

# The two slice options name DIFFERENT slices; taking both would leave the
# perimeter defined by whichever branch happens to run first — a silent choice
# on a security perimeter. Refuse instead.
if [ "$AT_SEEN" -eq 1 ] && [ "$SINCE_SEEN" -eq 1 ]; then
  echo "semgrep-scan: --at and --since name different slices; pass only one" >&2
  exit 2
fi

# ---- --hook / --event validation (T-00000459, Lot A) ------------------------
# The event comes from the FLAG, never guessed from a payload shape no one has
# measured on this host. `--event` without `--hook` is a mistake, a value other
# than post|stop is a mistake, and `--hook` combined with a PERIMETER option
# (--at/--since/--attest) is a mistake — each is refused loudly (exit 2), never
# absorbed into a run whose perimeter would then be ambiguous.
if [ "$HOOK_EVENT_SEEN" -eq 1 ] && [ "$HOOK" -eq 0 ]; then
  echo "semgrep-scan: --event requires --hook" >&2
  exit 2
fi
if [ "$HOOK" -eq 1 ]; then
  if [ "$HOOK_EVENT_SEEN" -eq 1 ]; then
    case "$HOOK_EVENT" in
      post|stop) : ;;
      *) echo "semgrep-scan: --event must be 'post' or 'stop' (got '$HOOK_EVENT')" >&2; exit 2 ;;
    esac
  fi
  if [ "$AT_SEEN" -eq 1 ] || [ "$SINCE_SEEN" -eq 1 ] || [ "$ATTEST_SEEN" -eq 1 ]; then
    echo "semgrep-scan: --hook takes no --at/--since/--attest (they name a DIFFERENT perimeter than the hook's post|stop)" >&2
    exit 2
  fi
fi

# ---- THE OUTPUT CARRIES TWO FIELDS, NOT A FLAT ENUM (T-00000370, C27) --------
# `findings` and `couverture` are ORTHOGONAL: "a sink was found" and "the
# perimeter was fully readable" are different questions, and a perfectly real
# state — A SINK FOUND *AND* A SUBMODULE NOT ENUMERATED — had no rendering in a
# single `CLEAN|FINDINGS|DEGRADED` axis. Collapsing them makes a reader treat one
# as the other: fix the sink and consider the coverage handled, or vice versa.
# BOTH must be routed.
#
# `verdict` KEEPS its name and its vocabulary. dashboard_readers.py histograms it
# (by_verdict), so renaming it would collapse the Security view to "unknown" for
# every record ever written; `couverture` is strictly ADDITIVE (C40).
COUVERTURE="CLEAN"
# Declared here because `audit()` reads their CARDINALS and an early exit (semgrep
# absent) can fire before the perimeter is built — `set -u` would abort otherwise.
FILES=()
PROPOSED=()
# T-01M4X9PP7FED0570PMPSYGA0V8 — the loss accounting of the perimeter, declared
# here for the same `set -u` reason. PERTE_N counts the CALLS of perte_perimetre
# (never its <n>, which may be "?"); PERTE_MSG carries the "<n> <cause>" items;
# SG_SIG is the signal file through which a producer SUBSHELL (`< <( … )`)
# reports what its own variables would lose; SG_INJ / SG_ILL are the per-loop
# counters of classer_chemin, flushed by relever_partition.
PERTE_N=0
PERTE_MSG=""
SG_SIG=""
SG_INJ=0
SG_ILL=0
# Precedence, and it only ever goes UP:
#   refus de conclure  ≻  DEGRADED  ≻  portable par attestation  ≻  CLEAN
# Without it, two categorical rules can both apply to one run (semgrep absent =>
# "portable par attestation" AND an unreadable .py => "DEGRADED") with nothing to
# arbitrate, and the implementer picks — half the time in favour of the green.
couverture_at_least() {
  case "$1" in
    "refus de conclure")
      COUVERTURE="refus de conclure" ;;
    DEGRADED)
      [ "$COUVERTURE" = "refus de conclure" ] || COUVERTURE="DEGRADED" ;;
    "portable par attestation")
      case "$COUVERTURE" in
        "refus de conclure"|DEGRADED) : ;;
        *) COUVERTURE="portable par attestation" ;;
      esac ;;
  esac
}

# ---- AN UNREAD PATH IS NEVER DROPPED IN SILENCE (T-01M4X9PP7FED0570PMPSYGA0V8)
# `[ -f ]` was the ONLY filter between what git listed and what semgrep read, and
# it answers FALSE for two opposite things: a file the change really DELETED
# (nothing to scan) and a file behind a directory this uid cannot SEARCH
# (`chmod 000 d`: content present, possibly a sink). The second was dropped like
# the first, and the gate printed `clean on the diff.` over an unread sink. A
# readable directory holding a 000 file made semgrep exit 2 instead, and every
# finding of the OTHER files was lost in that error. Measured 2026-10-14
# (plan R1-R5). Decision S-01M4XWS5WEV0DDV98HP04H8K9M: a loss DEGRADES, rc 0,
# gate AND hook — it never blocks.
#
# injoignable <racine> <rel> — TRUE iff the nearest EXISTING ancestor of <rel>,
# tested as "<racine>/<ancestor>" (never relative to the cwd: the script may be
# launched from a subdirectory), is a directory without the search bit. No
# existing ancestor, or no `/` left => FALSE (a genuine deletion). Each turn
# strips one component, so the loop terminates.
injoignable() {  # $1 racine (absolute)  $2 path relative to it
  local _p="$2"
  while :; do
    case "$_p" in
      */*) _p="${_p%/*}" ;;
      *) return 1 ;;
    esac
    if [ -e "$1/$_p" ] || [ -L "$1/$_p" ]; then
      [ -d "$1/$_p" ] && [ ! -x "$1/$_p" ]
      return
    fi
  done
}

# perte_perimetre <n> <cause> — the ONE point every loss crosses. It prints a
# COUNT and a cause, never a path (a caller may re-read this stderr). A blocking
# policy would branch HERE, at its end; the pilot decided against it.
perte_perimetre() {  # $1 count (or "?")  $2 cause
  local _sep='; '
  echo "COVERAGE DEGRADED: $1 $2 — not scanned; perimeter INCOMPLETE" >&2
  couverture_at_least "DEGRADED"
  PERTE_N=$((PERTE_N + 1))
  PERTE_MSG="${PERTE_MSG:+$PERTE_MSG$_sep}$1 $2"
}

# classer_chemin <rel> — 0: scan it. 1: do not — a genuine deletion or a
# non-file (silent, as before), or a loss COUNTED: unreachable (SG_INJ) or a
# regular file this uid cannot read (SG_ILL). The unreadable one is REMOVED from
# FILES so the rest is still scanned instead of drowning in semgrep's rc 2.
classer_chemin() {  # $1 path relative to ROOT
  if [ ! -f "$ROOT/$1" ]; then
    if [ -e "$ROOT/$1" ] || [ -L "$ROOT/$1" ]; then
      return 1
    fi
    if injoignable "$ROOT" "$1"; then
      SG_INJ=$((SG_INJ + 1))
    fi
    return 1
  fi
  if [ ! -r "$ROOT/$1" ]; then
    SG_ILL=$((SG_ILL + 1))
    return 1
  fi
  return 0
}

# relever_partition — after each loop that calls classer_chemin: a count > 0
# becomes a loss, then both counters are reset for the next loop.
relever_partition() {
  if [ "$SG_INJ" -gt 0 ]; then
    perte_perimetre "$SG_INJ" "listed path(s) unreachable in the working tree (a parent directory is not searchable)"
  fi
  if [ "$SG_ILL" -gt 0 ]; then
    perte_perimetre "$SG_ILL" "listed file(s) unreadable"
  fi
  SG_INJ=0
  SG_ILL=0
}

# relever_lserr <file> — the stderr of a `git ls-files --others` census. git
# warns there (and still exits 0) when it cannot open a directory: those
# untracked files were never listed. The text of git is never parsed, only its
# lines counted, and the cause stays NEUTRAL (an unreadable core.excludesFile or
# GIT_TRACE write there too). "" = the capture file could not be created: the
# census then ran with 2>/dev/null and that blindness is itself a loss.
relever_lserr() {  # $1 capture file, or ""
  local _n
  if [ -z "$1" ]; then
    perte_perimetre "?" "untracked census stderr not captured (no temp file)"
    return 0
  fi
  [ -s "$1" ] || return 0
  _n="$(wc -l < "$1" | tr -d ' ')"
  case "$_n" in
    ''|0) _n="?" ;;
  esac
  perte_perimetre "$_n" "warning line(s) from git ls-files --others (untracked files may be missing from the perimeter)"
}

# relever_signaux — reads, then REMOVES, $SG_SIG. A producer subshell cannot
# raise PERTE_N or COUVERTURE (its variables die with it, R4), so it appends a
# word there; every word then crosses perte_perimetre HERE, in the main shell.
# An empty $SG_SIG means its mktemp failed: no signal could be heard, a loss.
relever_signaux() {
  local _n
  if [ -z "$SG_SIG" ] || [ ! -f "$SG_SIG" ]; then
    perte_perimetre "?" "perimeter signals unavailable (no signal file)"
    SG_SIG=""
    return 0
  fi
  _n="$(grep -c '^census$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    echo "COVERAGE DEGRADED: dirty-tree census FAILED (git diff) — the working-tree diff was not enumerated; REFUS DE CONCLURE" >&2
    perte_perimetre "?" "working-tree path(s) (the dirty-tree census failed)"
    couverture_at_least "refus de conclure"
  fi
  _n="$(grep -c '^submod-fail$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "$_n" "submodule(s) whose enumeration failed (git ls-files) — REFUS DE CONCLURE"
    couverture_at_least "refus de conclure"
  fi
  _n="$(grep -c '^submod-unreach$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "$_n" "unreachable submodule(s) (a parent directory is not searchable)"
  fi
  _n="$(grep -c '^submod-depth$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "$_n" "submodule(s) beyond the depth bound"
  fi
  # `submod-ls`: the per-submodule `git ls-files -z` (its TRACKED files) failed —
  # an unknown remainder of that submodule never reached the perimeter.
  _n="$(grep -c '^submod-ls$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "$_n" "submodule(s) whose tracked files could not be listed (git ls-files) — REFUS DE CONCLURE"
    couverture_at_least "refus de conclure"
  fi
  # `commit-census`: files_changed_by could read the commit's paths neither by
  # `git diff X~1 X` nor by `git show X` (closing review T3) — a committed sink
  # would be absent from the perimeter, unknown remainder.
  _n="$(grep -c '^commit-census$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "?" "committed path(s) (the commit census failed)"
    couverture_at_least "refus de conclure"
  fi
  # `since-census` (T-01M4XY8PP8VYW0VVCYAAK0VARF): the range `<base>...HEAD`, or
  # the merge base it rests on, could not be read — the commits since the base
  # are an unknown remainder.
  _n="$(grep -c '^since-census$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "?" "committed path(s) since the base (the range census failed)"
    couverture_at_least "refus de conclure"
  fi
  # `k2-census` (T-01M4Z24V0J813T40XRW3S4VW67): `git ls-files -v` failed, so the
  # assume-unchanged entries — which `git diff` never compares — were not added.
  _n="$(grep -c '^k2-census$' "$SG_SIG" 2>/dev/null)"
  if [ "${_n:-0}" -gt 0 ]; then
    perte_perimetre "?" "assume-unchanged entries not listed (git ls-files -v failed)"
  fi
  rm -f "$SG_SIG"
  SG_SIG=""
}

audit() {  # $1 verdict  $2 findings  $3 rule+location-json — one line per run
  case "$1" in
    DEGRADED) couverture_at_least "DEGRADED" ;;
  esac
  # THE MACHINE CHANNEL MUST NOT FAIL BY THE VOID (C25). This append had no
  # guard: an unwritable $OUT (full disk, permissions) lost the line WITHOUT A
  # WORD, and "no trace" became indistinguishable from "the gate never ran" —
  # the exact ambiguity this task kills on the console, rebuilt in the journal.
  # Polarity is ANNOUNCE-ONLY, never a block: the journal is a proof, not a gate.
  # ---- THE RECORD CARRIES ITS OWN PROVENANCE AND ITS POPULATIONS -------------
  # `config` (C17) — WHICH RULESET produced this verdict. Without it two lines
  # that read identically can mean opposite things: the shipped offline ruleset
  # covers six languages, `p/security-audit` covers dozens, and "clean" under the
  # first is not "clean" under the second. A verdict whose provenance is not
  # recorded cannot be compared to the next one, so a coverage regression between
  # two runs is invisible in the very journal built to make it visible.
  #
  # `proposes` / `retains` / `unparsed` (A7) — the PARTITION, not just a total.
  # `retains < proposes` is the ordinary, harmless case (a commit deleted files);
  # `unparsed > 0` is the one that means an unknown remainder was never analysed.
  # A single "N files" figure conflates them and reads as full coverage either
  # way — which is the exact defect this task exists to remove, so the journal
  # must not reintroduce it one field down.
  # `mode`/`event` (T-00000459): "gate" on the normal path, "hook"/<post|stop>
  # when a registration drove this run. Defaulted with `:-` so the audit()
  # extraction harness (test arm (z)) still runs under `set -u` without seeding
  # two more variables — same self-contained-body discipline the rest obeys.
  # `config` is ESCAPED for JSON IN LINE (T-01M4Z2DMFTXH6Q40RRA3ZW1PE0): arm (z)
  # extracts this body ALONE, so its helpers are `local` here. Measured at
  # c2a42ba2: `x\"` wrote an INVALID line, `a\b` a valid line with the WRONG
  # value (`a<BS>`), a newline cut the line in two. Backslash FIRST, then the
  # quote, then LF/TAB/CR as `\n` `\t` `\r`, then every other control byte
  # dropped. The pattern is never quoted: a QUOTED `"$_bs$_bs"` replacement
  # writes `abc"\"` under /bin/bash 3.2 (measured — the mutant MA2).
  local _nl=$'\n' _tab=$'\t' _cr=$'\r' _c
  _c="${CFG//\\/\\\\}"
  _c="${_c//\"/\\\"}"
  _c="${_c//"$_nl"/\\n}"
  _c="${_c//"$_tab"/\\t}"
  _c="${_c//"$_cr"/\\r}"
  _c="${_c//[[:cntrl:]]/}"
  printf '{"ts":"%s","entry":"semgrep-scan.sh","class":1,"waivable":false,"verdict":"%s","couverture":"%s","findings":%s,"config":"%s","mode":"%s","event":"%s","proposes":%s,"retains":%s,"unparsed":%s,"locations":%s}\n' \
    "$TS" "$1" "$COUVERTURE" "$2" "$_c" \
    "${AUDIT_MODE:-gate}" "${AUDIT_EVENT:-}" \
    "${#PROPOSED[@]}" "${#FILES[@]}" "${AUDIT_UNPARSED_N:-0}" "$3" \
    >> "$OUT/audit-log.jsonl" 2>/dev/null \
    || echo "COVERAGE DEGRADED: canal d'audit inécrivable ($OUT/audit-log.jsonl) — la ligne de journal est PERDUE, le verdict lui-même est inchangé" >&2
}

# scan.sast emission (T-00000018 shard 2) — $1 status (scanned|degraded|
# skipped), $2 findings count, $3 rule+location-json (redacted, no snippet).
# NOT emitted when the event would be written where a symbolic link points
# (exec-critic of 13a3cebf, ecsg3/m1.sh: under a committed link `.agents/state`
# the kit-shaped repository's emitter created `<link target>/events/<day>.jsonl`,
# OUTSIDE the repository): a link on $OUT's path (OUT_LIEN — its loss line says
# the event is not emitted) or at `.agents/state/events` itself (said here, a
# note: no path is lost). A link on the EMITTER's own path (`.claude/hooks`,
# `.agents/bin`) is not tested — bound written in README-SECURITY-SCAN-SETUP.md.
# (exec-critic of 7c78f87f, MINEUR) Neither skip applies when AGENTS_EVENTS_DIR
# sends the event along a path that never passes through the repository
# (evenements_ailleurs, by identity): no link of the repository is on that
# path, so the event is emitted there — and the loss lines say so instead of
# `not emitted`.
#
# evenements_ailleurs — rc 0 when the path of AGENTS_EVENTS_DIR never passes
# THROUGH the scanned repository, judged by IDENTITY, never by text (exec-critic
# of 03c4ce7a: a text prefix read `/tmp/…/R/.agents/state/events` as outside
# when ROOT is `/private/tmp/…/R`, and the event was written behind the
# repository's committed `.agents/state` link). The criterion is the PASSAGE,
# not the destination: through a committed link the destination IS outside the
# repository — where the link points. A relative value is made absolute against
# the PHYSICAL cwd (events.py resolves it there; emit-event.sh does not cd).
# (1) every textual ancestor is tested `-ef "$ROOT"` (same inode: any spelling,
# a link of the caller's own included), a dangling link refused; (2) the
# deepest EXISTING ancestor is resolved physically (`cd -P`, `pwd -P`: `..` and
# links resolved by the system, no value re-parsed) and each of ITS ancestors is
# tested the same way; what does not exist yet must carry no `.`/`..`
# component. Any doubt answers "inside": the event is then not emitted, said.
# BOUND (README-SECURITY-SCAN-SETUP.md): a link of the caller's own that points
# at a link INSIDE the repository which leads back outside it is not followed
# hop by hop.
evenements_ailleurs() {
  local _v="${AGENTS_EVENTS_DIR:-}" _p _e _reste="" _a _c
  [ -n "$_v" ] || return 1
  case "$_v" in
    /*)
      : ;;
    *)
      _c="$(pwd -P 2>/dev/null)" || return 1
      [ -n "$_c" ] || return 1
      _v="$_c/$_v" ;;
  esac
  _p="$_v"
  while [ -n "$_p" ]; do
    if [ -L "$_p" ] && [ ! -e "$_p" ]; then
      return 1
    fi
    if [ "$_p" -ef "$ROOT" ]; then
      return 1
    fi
    case "$_p" in
      /)
        _p="" ;;
      */*)
        _p="${_p%/*}"
        [ -n "$_p" ] || _p=/ ;;
      *)
        _p="" ;;
    esac
  done
  _e="$_v"
  while [ ! -d "$_e" ]; do
    _reste="/${_e##*/}$_reste"
    _e="${_e%/*}"
    [ -n "$_e" ] || _e=/
  done
  case "$_reste/" in
    */./*|*/../*)
      return 1 ;;
  esac
  _a="$(cd -P -- "$_e" 2>/dev/null && pwd -P)" || return 1
  while [ -n "$_a" ]; do
    if [ "$_a" -ef "$ROOT" ]; then
      return 1
    fi
    case "$_a" in
      /)
        _a="" ;;
      */*)
        _a="${_a%/*}"
        [ -n "$_a" ] || _a=/ ;;
      *)
        _a="" ;;
    esac
  done
  return 0
}
emit_scan() {
  local _ailleurs=0
  if evenements_ailleurs; then
    _ailleurs=1
  fi
  if [ -n "$OUT_LIEN" ] && [ "$_ailleurs" = 0 ]; then
    return 0
  fi
  if [ -L "$ROOT/.agents/state/events" ] && [ "$_ailleurs" = 0 ]; then
    echo "note: scan event not emitted (.agents/state/events is a symbolic link: it would be written where the link points)" >&2
    return 0
  fi
  # T-00000041 — same host/root propagation as gitleaks-scan.sh's emitter;
  # see the rationale there (registered on 4 hosts, bridge defaults to claude).
  EVT_HOST="${AGENTS_HOOK_HOST:-claude}" CLAUDE_PROJECT_DIR="$ROOT" \
    bash "$ROOT/.claude/hooks/emit-event.sh" scan.sast "status=$1" \
    "counters:={\"findings\":$2}" "locations:=$3" >/dev/null 2>&1 || true
}

# ---- THE CENSUS RUNS NO CODE OF THE SCANNED REPOSITORY (T-01M4Z24V0J813T40XRW3S4VW67)
# Measured at c2a42ba2 on the gate AND the hook Stop: a `core.fsmonitor` command
# and a `filter.<driver>.clean` of the scanned repository's config were RUN by
# the census `git diff` — at the root and inside a submodule — and a partial
# clone ran its `remote.<name>.uploadpack`. The channels below are COPIES of
# gitleaks-scan.sh (no shared helper: each script stays self-contained, the same
# reason as enumerate_submodules). The list of channels cut is CLOSED and its
# bound is written in README-SECURITY-SCAN-SETUP.md; a channel outside it
# (core.sshCommand, an alias) is NOT declared cut.
#
# Every git call that reads a repository carries "${GN[@]}" right after its
# `-C <dir>` (fsmonitor off, hooks off) — the `git -C "…"` form is kept on
# purpose, the (r) pin of the suite reads it; only the header's
# `rev-parse --show-toplevel` stays plain.
GN=(-c core.fsmonitor=false -c core.hooksPath=/dev/null)
# `--no-lazy-fetch` is passed TOO, on every git call that carries GN, wherever
# this git has it (closing review 2, F2): a git that accepts the flag but does
# not honor the exported variable still refuses a lazy fetch in each of our
# processes — measured with such a git (fixture fxP): without this, the gate
# ran the remote's uploadpack. Whether a given git also honors the variable is
# NOT assumed. Cost: one `git version` per run.
if git "${GN[@]}" --no-lazy-fetch version >/dev/null 2>&1; then
  GN+=(--no-lazy-fetch)
fi

# paresseux <repo> : rc 0 when the repository is a PARTIAL clone (a promisor
# remote) and this git cannot refuse a lazy fetch — it has no `--no-lazy-fetch`
# (git < 2.45): there the export above has no effect either, and a missing blob
# would be fetched, RUNNING the remote's uploadpack. The gate then refuses to enumerate such a root, skips such a
# submodule — before ANY git lists it, its index included (enumerate_submodules
# tests it before its recursion); the hook Stop runs NO git that reads a tree or
# an object of it:
# neither the census diff, nor `ls-files --others`, nor `ls-files -v` (K2 and
# the `.gitignore` probe's listing: a SPARSE index expands, reading the tree of
# each directory entry), nor the index diff (`diff-index --cached HEAD` reads
# HEAD's trees — absent from a treeless clone after a `fetch` + `reset --soft`,
# or before any checkout), nor any cat-file — and every loss is said. Measured
# (devsg9, a git that ignores the variable): each of those calls, naked, RAN
# the uploadpack; `rev-parse --verify HEAD`, `hash-object -t tree` and `config`
# did not. The promisor test is ONE `git config` read per repository: a repeat
# on the same repository (the Stop's root, a submodule visited twice) is
# answered from _PZ_DIR/_PZ_RC; `--no-lazy-fetch` is probed ONCE, and only when
# a promisor exists.
_NLF=""; _PZ_DIR=""; _PZ_RC=1
paresseux() {  # $1 = repo dir
  if [ -n "$_PZ_DIR" ] && [ "$1" = "$_PZ_DIR" ]; then
    return "$_PZ_RC"
  fi
  _PZ_DIR="$1"; _PZ_RC=1
  git -C "$1" "${GN[@]}" config --get-regexp '^(remote\..*\.promisor|extensions\.partialclone)$' >/dev/null 2>&1 || return 1
  if [ -z "$_NLF" ]; then
    _NLF=oui
    git "${GN[@]}" --no-lazy-fetch version >/dev/null 2>&1 || _NLF=non
  fi
  [ "$_NLF" = non ] && _PZ_RC=0
  return "$_PZ_RC"
}

# arbres_absents <repo> (exec-critic of 7c78f87f, MAJEUR): rc 0 when the index
# of the repository is SPARSE and N of its directory entries (_AA_N) name a tree
# absent from its object store; rc 1 when none, or when the check is out of
# reach (below); rc 2 when the check itself failed (_AA_N = its git rc).
# Measured under git 2.55 + the no-lazy-fetch export (devmulti-sg10
# majprobe.sh, fixture cr2: entry b/ naming an absent tree): `ls-files`,
# `ls-files -v` and `ls-files --stage` all return rc 0 and OMIT b/'s entries in
# silence — a truncated listing read as complete by enumerate_submodules, K2,
# the skip-worktree probe, a submodule's tracked files and objets_pointe (iii).
# ONE `ls-files --sparse -s` per repository (it lists a directory entry as is,
# never expands it: no tree read), then ONE batch `cat-file` over the entries'
# trees, only when there is one — a healthy sparse index answers `tree`
# (measured, fixture sp), a full index has no such entry. NOT run on a partial
# clone under a git that cannot refuse a lazy fetch (paresseux): the batch would
# FETCH — the callers do not list such a repository at all. A git without
# `ls-files --sparse` (< 2.36: rc 129) is not checked — bound written in
# README-SECURITY-SCAN-SETUP.md. A path holding a newline can only ADD a
# candidate (an absence said that is not one), never hide one. A repeat on the
# same repository is answered from _AA_DIR/_AA_RC.
_AA_DIR=""; _AA_RC=1; _AA_N=0
arbres_absents() {  # $1 = repo dir
  local _sh _l _x _rc=0 _k=0 _t=0
  if [ -n "$_AA_DIR" ] && [ "$1" = "$_AA_DIR" ]; then
    return "$_AA_RC"
  fi
  _AA_DIR="$1"; _AA_RC=1; _AA_N=0
  if paresseux "$1"; then
    return 1
  fi
  _sh="$(git -C "$1" "${GN[@]}" ls-files --sparse -s -z 2>/dev/null | tr '\0' '\n' | sed -n 's/^040000 \([0-9a-f]*\) .*/\1/p')" || _rc=$?
  if [ "$_rc" -eq 129 ]; then
    return 1
  fi
  if [ "$_rc" -ne 0 ]; then
    _AA_RC=2; _AA_N="$_rc"
    return 2
  fi
  [ -n "$_sh" ] || return 1
  _l="$(printf '%s\n' "$_sh" | git -C "$1" "${GN[@]}" cat-file --batch-check='%(objecttype)' 2>/dev/null)" || _rc=$?
  if [ "$_rc" -ne 0 ]; then
    _AA_RC=2; _AA_N="$_rc"
    return 2
  fi
  while IFS= read -r _x; do
    _k=$((_k + 1))
  done <<< "$_sh"
  while IFS= read -r _x; do
    if [ "$_x" = tree ]; then
      _t=$((_t + 1))
    fi
  done <<< "$_l"
  _AA_N=$((_k - _t))
  if [ "$_AA_N" -gt 0 ]; then
    _AA_RC=0
  fi
  return "$_AA_RC"
}

# dire_arbres <repo> — the loss of arbres_absents, said in THIS shell (never
# under a command substitution: perte_perimetre has to reach PERTE_N). A named
# DEGRADED, as the sparse-index entry index_candidats cannot expand: what an
# absent tree hides is an unknown remainder of the index listings, SAID.
dire_arbres() {  # $1 = repo dir
  local _r=0
  arbres_absents "$1" || _r=$?
  case "$_r" in
    0)
      perte_perimetre "$_AA_N" "sparse-index directory entr(y|ies) naming a tree absent from the object store (git ls-files omits their entries in silence: the index listings are incomplete)" ;;
    2)
      perte_perimetre "?" "index listings not verified (sparse-index check failed, git rc $_AA_N: git ls-files may omit entries in silence)" ;;
  esac
  return 0
}

# filtres_neutres <repo> <work file> : a `filter.<driver>.clean` or `.process`
# of the repository's config is a COMMAND, which `git diff` runs on a tracked
# file whose content it has to read. Prints, NUL-separated, the options that
# empty every such driver for ONE git call — `--config-env=` on
# `filter.<n>.clean` and `.process` (GL_VIDE) and `.required` (GL_FAUX), git >=
# 2.31; never `-c`, which cuts a driver named `a=b` at its first `=` (measured)
# — then the record `ok`. The drivers are read in EVERY scope, GIT_CONFIG unset
# (it points `git config` at another file, which `git diff` never reads).
# PROVEN by a re-read with the options applied: the LAST value of every
# clean/process key must be empty; otherwise — or on an older git, which
# refuses --config-env — `ok` is never printed and the caller does not run the
# diff. A SUBSHELL: the unset never leaks. Its work file ($2) is created by the
# CALLER, in _TMP_FN, so that the EXIT trap removes it when a signal stops the
# run. One divergence from gitleaks-scan.sh, said: without a work file ($2
# empty, an unwritable TMPDIR) a repository WITHOUT any driver (`git config`
# rc 1) is still proven neutral — the census is not given up for a file it
# would never have needed; a repository WITH a driver is not.
export GL_VIDE='' GL_FAUX=false
filtres_neutres() {  # $1 = repo dir  $2 = work file (created by the caller, may be "")
  (
    unset GIT_CONFIG
    nl=$'\n'
    lu="$2"
    rc=0
    if [ -z "$lu" ]; then
      git -C "$1" "${GN[@]}" config -z --get-regexp '^filter\..*\.(clean|process)$' >/dev/null 2>&1 || rc=$?
      if [ "$rc" -eq 1 ]; then
        printf 'ok\0'
      fi
      exit 0
    fi
    git -C "$1" "${GN[@]}" config -z --get-regexp '^filter\..*\.(clean|process)$' > "$lu" 2>/dev/null || rc=$?
    if [ "$rc" -gt 1 ]; then
      rm -f "$lu"
      exit 1
    fi
    opts=(); vus="$nl"
    while IFS= read -r -d '' rec; do
      n="${rec%%$'\n'*}"; n="${n#filter.}"
      case "$n" in
        *.clean)
          n="${n%.clean}" ;;
        *.process)
          n="${n%.process}" ;;
      esac
      case "$vus" in
        *"$nl$n$nl"*)
          continue ;;
      esac
      vus="$vus$n$nl"
      opts+=("--config-env=filter.$n.clean=GL_VIDE" "--config-env=filter.$n.process=GL_VIDE" "--config-env=filter.$n.required=GL_FAUX")
    done < "$lu"
    if [ "${#opts[@]}" -gt 0 ]; then
      git ${opts[@]+"${opts[@]}"} -C "$1" "${GN[@]}" config -z --get-regexp '^filter\..*\.(clean|process)$' > "$lu" 2>/dev/null || { rm -f "$lu"; exit 1; }
      cles=(); vals=()
      while IFS= read -r -d '' rec; do
        cles+=("${rec%%$'\n'*}")
        case "$rec" in
          *"$nl"*)
            vals+=("${rec#*$'\n'}") ;;
          *)
            vals+=("(no value)") ;;
        esac
      done < "$lu"
      i=0
      while [ "$i" -lt "${#cles[@]}" ]; do
        j="$i"; k=$((i + 1))
        while [ "$k" -lt "${#cles[@]}" ]; do
          [ "${cles[$k]}" = "${cles[$i]}" ] && j="$k"
          k=$((k + 1))
        done
        if [ -n "${vals[$j]}" ]; then
          rm -f "$lu"
          exit 1
        fi
        i=$((i + 1))
      done
      printf '%s\0' ${opts[@]+"${opts[@]}"}
    fi
    rm -f "$lu"
    printf 'ok\0'
  )
}

# neutres_racine — decided ONCE per run, in THIS shell, before any producer
# `< <( … )` that runs a diff of the working tree: NEUTRES (the options) and
# _neutres_ok (1 = proven neutral), plus _PARESSEUX (1 = a partial clone under a
# git that cannot refuse a lazy fetch). The work file lives in _TMP_FN, which
# the EXIT trap removes when a signal stops the run.
NEUTRES=(); _neutres_ok=0; _PARESSEUX=0; _neutres_vu=0
neutres_racine() {
  local _o
  [ "$_neutres_vu" = 1 ] && return 0
  _neutres_vu=1
  _TMP_FN="$(mktemp "${TMPDIR:-/tmp}/semgrep-filters.XXXXXX" 2>/dev/null)" || _TMP_FN=""
  while IFS= read -r -d '' _o; do
    case "$_o" in
      ok)
        _neutres_ok=1 ;;
      *)
        NEUTRES+=("$_o") ;;
    esac
  done < <(filtres_neutres "$ROOT" "$_TMP_FN")
  [ -n "$_TMP_FN" ] && rm -f "$_TMP_FN"
  _TMP_FN=""
  if paresseux "$ROOT"; then
    _PARESSEUX=1
  fi
  return 0
}

# relever_neutres — the two fail-closed branches of the tree diff, said in THIS
# shell (the diff itself runs in a producer subshell, which cannot raise PERTE_N).
# On a partial clone under a git that cannot refuse a lazy fetch, the hook Stop
# does not run `ls-files --others` either (closing review B2: it reads a
# skip-worktree `.gitignore` from its index blob and FETCHES it — measured with
# a git that ignores the no-lazy-fetch variable): that loss is said here too.
# The first line also covers K2, not run there either (k2_lister). The gate
# never reaches this branch for its root (it refuses to enumerate).
relever_neutres() {
  if [ "$_PARESSEUX" = 1 ]; then
    perte_perimetre "?" "tracked modified file(s) not enumerated (partial clone, git < 2.45: a missing blob would be fetched, running the remote's uploadpack)"
    perte_perimetre "?" "untracked file(s) not enumerated (partial clone, git < 2.45: a skip-worktree .gitignore without its blob would be fetched)"
  elif [ "$_neutres_ok" != 1 ]; then
    perte_perimetre "?" "tracked modified file(s) not enumerated (a filter driver could not be neutralized)"
  fi
}

# ignores_illisibles <repo> (port of gitleaks-scan.sh): a `.gitignore` flagged
# skip-worktree (tag `S`, or `s` when also assume-unchanged, in `ls-files -v`)
# and ABSENT from the disk is read by the census `ls-files --others
# --exclude-standard` from its INDEX blob — which a partial clone may not have:
# under the no-lazy-fetch export git reads it as EMPTY. Measured on this script
# (fixture C18: root `*.py`, `!keep.py` in a skip-worktree `d/.gitignore`
# without its blob, an untracked sink `d/keep.py`): under the export alone the
# negation was lost, `d/keep.py` was never listed, and the run read `nothing to
# scan`, audit CLEAN. Such a file is COUNTED in _ign_ill (one loss line after
# the submodule loop) only when it can hide something: its directory must EXIST
# and hold an untracked path that is IGNORED now — one listing per repo — and
# its blob must be MISSING: ONE batch `cat-file` per repo for every candidate.
# No candidate, no extra process. A git call that fails here is SAID, never read
# as a count of 0; a git older than 2.42 (no NUL-terminated batch-check) is said
# "not checked", and so is a partial clone under a git that cannot refuse the
# fetch — tested FIRST, before ANY listing (paresseux: not even the `ls-files
# -v` of the `.gitignore` entries is run — on a sparse index it expands each
# directory entry, reading its tree, and FETCHED an absent one, measured). Called in THIS shell, never under a
# command substitution: perte_perimetre has to reach PERTE_N. Its work file
# lives in _TMP_SW, which the EXIT trap removes when a signal stops the run.
_ign_ill=0
ignores_illisibles() {  # $1 = repo dir (absolute)
  local lv rec chemin d u i _g _k rc=0 n=0 j=0
  local -a cand=() rep=() unt=() garde=()
  if paresseux "$1"; then
    perte_perimetre "?" "skip-worktree .gitignore file(s) not checked (partial clone, git < 2.45: a missing tree or blob would be fetched, running the remote's uploadpack)"
    return 0
  fi
  _TMP_SW="$(mktemp "${TMPDIR:-/tmp}/semgrep-sw.XXXXXX" 2>/dev/null)" || _TMP_SW=""
  lv="$_TMP_SW"
  if [ -z "$lv" ]; then
    perte_perimetre "?" "skip-worktree .gitignore check failed (no temporary file)"
    return 0
  fi
  # Only the `.gitignore` entries are listed (glob pathspec, root included).
  # Under GIT_LITERAL_PATHSPECS git refuses the glob (rc 128): said below as a
  # failed check, never a silent 0.
  git -C "$1" "${GN[@]}" --glob-pathspecs ls-files -v -z -- '**/.gitignore' > "$lv" 2>/dev/null || rc=$?
  if [ "$rc" -eq 0 ]; then
    while IFS= read -r -d '' rec; do
      case "$rec" in
        [Ss]" "*)
          chemin="${rec#??}"
          case "$chemin" in
            .gitignore|*/.gitignore)
              d="${chemin%/.gitignore}"
              [ "$d" = "$chemin" ] && d=.
              if [ ! -e "$1/$chemin" ] && [ -d "$1/$d" ]; then
                cand+=("$chemin")
                rep+=("$d")
              fi
              ;;
          esac
          ;;
      esac
    done < "$lv"
  fi
  # (The partial-clone test is at the head of the function — closing review B2:
  # the `--ignored` listing below reads the candidate `.gitignore` from its
  # index blob, and under a git that cannot refuse a lazy fetch it would FETCH
  # it; the `ls-files -v` above expands a sparse index.) `=`, never `-eq`: rc
  # may be the word `vieux`.
  if [ "$rc" = 0 ] && [ "${#cand[@]}" -gt 0 ]; then
    git -C "$1" "${GN[@]}" --literal-pathspecs ls-files --others --ignored --exclude-standard --directory -z -- ${rep[@]+"${rep[@]}"} > "$lv" 2>/dev/null || rc=$?
    if [ "$rc" -eq 0 ]; then
      while IFS= read -r -d '' u; do
        unt+=("$u")
      done < "$lv"
      i=0
      while [ "$i" -lt "${#cand[@]}" ]; do
        _g=0
        if [ "${rep[$i]}" = . ]; then
          [ "${#unt[@]}" -gt 0 ] && _g=1
        else
          for u in ${unt[@]+"${unt[@]}"}; do
            case "$u" in
              "${rep[$i]}"/*)
                _g=1
                break ;;
            esac
          done
        fi
        [ "$_g" = 1 ] && garde+=("${cand[$i]}")
        i=$((i + 1))
      done
    fi
  fi
  if [ "$rc" = 0 ] && [ "${#garde[@]}" -gt 0 ]; then
    printf ':0:%s\0' ${garde[@]+"${garde[@]}"} | git -C "$1" "${GN[@]}" cat-file --batch-check -Z > "$lv" 2>/dev/null || rc=$?
    if [ "$rc" -eq 0 ]; then
      while IFS= read -r -d '' rec; do
        j=$((j + 1))
        case "$rec" in
          *" missing")
            n=$((n + 1)) ;;
          [0-9a-f]*" blob "[0-9]*)
            : ;;
          *)
            n=$((n + 1)) ;;
        esac
      done < "$lv"
      _k="${#garde[@]}"
      [ "$j" -lt "$_k" ] && n=$((n + _k - j))
    elif ! git -C "$1" "${GN[@]}" cat-file --batch-check -Z < /dev/null > /dev/null 2>&1; then
      rc=vieux
    fi
  fi
  rm -f "$lv"
  _TMP_SW=""
  case "$rc" in
    0)
      _ign_ill=$((_ign_ill + n)) ;;
    vieux)
      perte_perimetre "?" "git < 2.42 : skip-worktree .gitignore not checked" ;;
    *)
      perte_perimetre "?" "skip-worktree .gitignore check failed (git rc $rc)" ;;
  esac
  return 0
}

# k2_lister — K2 (port of gitleaks-scan.sh): the ROOT index entries flagged
# assume-unchanged (lowercase tag of `ls-files -v`: git never compares their
# working-tree copy, so `git diff` does not list a sink written there), printed
# NUL-separated for the census; a submodule lists ALL its tracked files anyway.
# The tag is matched against a closed list of lowercase letters (no range:
# locale-free); skip-worktree alone (`S`, every sparse checkout) is not added.
# Its rc is the listing's (pipefail): the caller signals `k2-census`. Measured:
# 0,11 s under /bin/bash 3.2 over the 4 047 entries of this kit's index. NOT
# run on a partial clone under a git that cannot refuse a lazy fetch: on a
# sparse index `ls-files -v` expands each directory entry, reading its tree, and
# FETCHED an absent one (measured, devsg9) — rc 0, nothing listed; the loss is
# the `tracked modified file(s) not enumerated` line of relever_neutres, which
# covers the assume-unchanged entries K2 would add.
k2_lister() {
  paresseux "$ROOT" && return 0
  git -C "$ROOT" "${GN[@]}" ls-files -v -z 2>/dev/null \
    | while IFS= read -r -d '' _rec; do
        case "$_rec" in
          [hsmrck]" "*)
            printf '%s\0' "${_rec#??}" ;;
        esac
      done
}

# relever_ignores — the ONE loss line of the skip-worktree `.gitignore` count,
# after every ignores_illisibles call of the run (root and submodules).
relever_ignores() {
  if [ "$_ign_ill" -gt 0 ]; then
    perte_perimetre "$_ign_ill" "skip-worktree .gitignore file(s) unreadable (partial clone) — untracked files they re-include may be missed"
  fi
  _ign_ill=0
}


# ---- Submodule enumeration (T-00000293) -------------------------------------
# gitleaks/semgrep build their perimeter from `git diff HEAD` + `ls-files
# --others`, each path filtered by `[ -f ]`. A gitlink is a DIRECTORY, so that
# filter drops it, and `ls-files --others` never descends across a submodule
# boundary — so an `os.system` COMMITTED inside a submodule is invisible to this
# class-1 SAST input in EVERY git state (measured:
# docs/design/2026-08-22-mesure-scan-sous-modules.md). This enumeration
# re-includes the content of INITIALIZED submodules, recursively.
#
# Per repo, `git ls-files -z --stage` filtered on mode 160000 lists the gitlinks
# NUL-safely (never `submodule status`+awk, which splits a path with a space).
# Descent happens only when `<sub>/.git` EXISTS (`-e`, not `-d`: inside a
# submodule `.git` is a FILE pointer, not a directory) — i.e. only INITIALIZED
# submodules. Depth is bounded, and the bound SAYS SO when it bites. Enumeration
# failure is fail-open AND ANNOUNCED. DUPLICATED from gitleaks-scan.sh on purpose
# (no shared helper — the per-suite grep-scope pins want each script
# self-contained, same reason emit_scan is duplicated) — but the copies have
# DIVERGED, they are no longer verbatim: this one also reports to $SG_SIG
# (T-01M4X9PP7FED0570PMPSYGA0V8). It runs in the SUBSHELL of `< <( … )`, where
# a couverture_at_least is LOST with the subshell (measured, plan R4): a failed
# enumeration, an unreachable submodule and the depth bound each append a word
# to $SG_SIG, which relever_signaux replays in the main shell. Prints each
# initialized submodule's path, relative to ROOT, NUL-separated on stdout;
# notices to stderr.
SUBMODULE_SCAN_DEPTH="${SUBMODULE_SCAN_DEPTH:-8}"
enumerate_submodules() {  # $1 repo-abs  $2 prefix(rel to ROOT, "" at top)  $3 depth
  # `_racine` est LOCAL parce que cette fonction est RÉCURSIVE. Il existe pour
  # sortir les chevrons de la SYNTAXE de l'expansion : `${prefix:-<root>}` est
  # du bash valide que tree-sitter-bash ne parse pas, et un seul site retire ce
  # fichier ENTIER du compte des cibles inspectées par la porte SAST — celle
  # que ce script EST.
  local repo="$1" prefix="$2" depth="$3" lf rc rec mode path sub_rel sub_abs
  local _racine='<root>'
  lf="$(mktemp "${TMPDIR:-/tmp}/submod-ls.XXXXXX")" || return 0
  git -C "$repo" "${GN[@]}" ls-files -z --stage > "$lf" 2>/dev/null; rc=$?
  if [ "$rc" -ne 0 ]; then
    # C23/L-00000186 — one does not NAME a bound one FAILED to enumerate. An
    # enumeration that errored leaves an unknown remainder, so this is a refusal
    # to conclude, which outranks DEGRADED in the precedence order.
    couverture_at_least "refus de conclure"
    if [ -n "${SG_SIG:-}" ]; then printf 'submod-fail\n' >> "$SG_SIG"; fi
    echo "COVERAGE DEGRADED: submodule enumeration failed at '${prefix:-$_racine}' (git ls-files rc=$rc) — submodule content not scanned; REFUS DE CONCLURE" >&2
    rm -f "$lf"; return 0
  fi
  while IFS= read -r -d '' rec; do
    # rec = "<mode> <sha> <stage>\t<path>"; the gitlink mode is 160000.
    mode="${rec%% *}"
    [ "$mode" = "160000" ] || continue
    path="${rec#*$'\t'}"                       # path relative to THIS repo
    if [ -n "$prefix" ]; then sub_rel="$prefix/$path"; else sub_rel="$path"; fi
    sub_abs="$ROOT/$sub_rel"
    if [ ! -e "$sub_abs/.git" ]; then          # -e: .git is a FILE inside a submodule
      # `-e` is FALSE too behind a directory this uid cannot search: that
      # submodule may well be initialized, its content committed — never
      # "not initialized" (measured, plan R3).
      if injoignable "$ROOT" "$sub_rel/.git"; then
        if [ -n "${SG_SIG:-}" ]; then printf 'submod-unreach\n' >> "$SG_SIG"; fi
        echo "semgrep-scan: unreachable submodule '$sub_rel' (a parent directory is not searchable) — content may already be committed, not scanned" >&2
        continue
      fi
      echo "semgrep-scan: submodule '$sub_rel' not initialized — content absent, not scanned" >&2
      continue
    fi
    printf '%s\0' "$sub_rel"                    # this submodule's OWN files get scanned
    if [ "$depth" -ge "$SUBMODULE_SCAN_DEPTH" ]; then
      if [ -n "${SG_SIG:-}" ]; then printf 'submod-depth\n' >> "$SG_SIG"; fi
      echo "COVERAGE DEGRADED: submodule depth bound ($SUBMODULE_SCAN_DEPTH) exceeded at $sub_rel — content not scanned" >&2
      continue                                  # scanned this one, but do not descend further
    fi
    # (exec-critic of 7c78f87f, B2) A submodule that is a partial clone under a
    # git that cannot refuse a lazy fetch (paresseux) is NOT descended: the
    # `ls-files --stage` of the recursion expands a sparse index and FETCHED an
    # absent tree there, running the remote's uploadpack (measured: exec-critic
    # subp.sh, GIT_TRACE) — in THIS producer, before the consumer loop's skip.
    # Tested here, before any git that lists it (paresseux reads its config
    # only); the consumer skips it and says the loss, nested submodules included.
    if paresseux "$sub_abs"; then
      continue
    fi
    enumerate_submodules "$sub_abs" "$sub_rel" "$((depth + 1))"
  done < "$lf"
  rm -f "$lf"
}

# ---- THE COVERED-LANGUAGE SET IS READ FROM THE RULESET, NEVER RE-TYPED -------
# (T-00000364.) The blindness detector below has to answer "does this commit
# carry code this ruleset could say anything about?". Hardcoding a list of
# extensions here would be L-00000187 exactly: an enumeration under a universal
# title, true the day it is written and a delayed lie after the first rule is
# added. So the LANGUAGES come from `$CFG` itself, and only the language ->
# extension MAPPING is written down — a much smaller, much more stable thing.
#
# AND THE MAPPING IS BOUNDED OUT LOUD RATHER THAN ASSUMED TOTAL: a language
# present in the ruleset that this table does not map is ANNOUNCED, never
# silently dropped. Without that line, adding a Go rule would make the detector
# blind to Go while still printing a confident verdict — the fail-open shape.
# COVERED_UNMEASURABLE is the "refuse to conclude" flag (L-00000186: a
# measurement harness lies by the void, and its lie has the shape of a perfect
# green). MEASURED while writing this: pointed at a repo whose ruleset was
# absent, the detector found zero languages, concluded "nothing is covered", and
# printed `nothing to scan (clean working tree)` over a COMMITTED `os.system` —
# the very false green this task exists to remove, reintroduced one level down.
# So the countermeasure sits INSIDE the helper, not in vigilance: when the
# language set cannot be established, the caller must DEGRADE, never conclude.
#
# BOTH HELPERS PUBLISH THROUGH GLOBALS, DELIBERATELY, AND THAT IS NOT A STYLE
# CHOICE. `x="$(f)"` runs f in a SUBSHELL, so a flag f sets is discarded the
# instant it returns — the refusal-to-conclude would be swallowed by the very
# mechanism meant to carry it, and the caller would read a confident 0. So
# `covered_extensions` writes COVERED_EXTS, `count_covered` writes
# COVERED_COUNT, and neither is ever called inside `$( )`.
COVERED_UNMEASURABLE=0
COVERED_EXTS=""
COVERED_COUNT=0
covered_extensions() {  # -> sets COVERED_EXTS (newline-separated), COVERED_UNMEASURABLE
  local langs ext_list="" unmapped="" l
  COVERED_EXTS=""
  # $CFG may be RELATIVE (the default) or ABSOLUTE (SEMGREP_CONFIG override —
  # which is how this script's own test suite points at the real ruleset from a
  # throwaway repo). Resolve both, or the detector reads an empty file and
  # silently claims zero covered languages.
  local cfg_path="$CFG"
  case "$CFG" in
    /*|[A-Za-z]:[/\\]*) : ;; *) cfg_path="$ROOT/$CFG" ;;
  esac
  if [ ! -r "$cfg_path" ]; then
    COVERED_UNMEASURABLE=1
    echo "COVERAGE DEGRADED: ruleset '$CFG' is absent or unreadable — the covered-language set CANNOT be established, so no conclusion is drawn about the perimeter" >&2
    return 0
  fi
  langs="$(sed -n 's/^[[:space:]]*languages:[[:space:]]*\[\(.*\)\].*/\1/p' "$cfg_path" 2>/dev/null \
             | tr ',' '\n' | tr -d ' ' | grep -v '^$' | sort -u)"
  if [ -z "$langs" ]; then
    COVERED_UNMEASURABLE=1
    echo "COVERAGE DEGRADED: ruleset '$CFG' declares no 'languages:' key — the covered-language set CANNOT be established, so no conclusion is drawn about the perimeter" >&2
    return 0
  fi
  while IFS= read -r l; do
    case "$l" in
      python|py)             ext_list="$ext_list py pyi" ;;
      javascript|js)         ext_list="$ext_list js jsx mjs cjs" ;;
      typescript|ts)         ext_list="$ext_list ts tsx mts cts" ;;
      java)                  ext_list="$ext_list java" ;;
      yaml|yml)              ext_list="$ext_list yml yaml" ;;
      go)                    ext_list="$ext_list go" ;;
      ruby|rb)               ext_list="$ext_list rb" ;;
      php)                   ext_list="$ext_list php" ;;
      c|cpp)                 ext_list="$ext_list c cc cpp h hpp" ;;
      csharp|cs)             ext_list="$ext_list cs" ;;
      rust|rs)               ext_list="$ext_list rs" ;;
      bash|sh|shell)         ext_list="$ext_list sh bash" ;;
      generic|regex)         : ;;   # language-agnostic rules: no extension claim
      *)                     unmapped="$unmapped $l" ;;
    esac
  done <<< "$langs"
  if [ -n "$unmapped" ]; then
    echo "COVERAGE DEGRADED: ruleset declares language(s)$unmapped that this script cannot map to file extensions — the blindness check below CANNOT see them" >&2
  fi
  COVERED_EXTS="$(printf '%s\n' $ext_list | sort -u | grep -v '^$')"
  # PARTIAL vs TOTAL failure of the mapping, distinguished rather than merged.
  # Partial (`[python, cobol]`): we can still see .py, the gap on cobol is
  # announced above, and concluding is legitimate. TOTAL (`[cobol]` alone): every
  # declared language is unmapped, so the detector can say NOTHING about what
  # HEAD carries — and a "nothing is covered" there would be indistinguishable
  # from a genuinely uncovered repo. That is unmeasurable, so refuse to conclude.
  if [ -z "$COVERED_EXTS" ] && [ -n "$unmapped" ]; then
    COVERED_UNMEASURABLE=1
    echo "COVERAGE DEGRADED: EVERY language the ruleset declares is unmapped$unmapped — nothing can be concluded about the perimeter" >&2
  fi
}

# count_covered — reads NUL-SEPARATED paths on STDIN, sets COVERED_COUNT to how
# many carry a covered extension.
#
# STDIN AND NUL, BOTH DELIBERATE (T-00000370). It used to take a newline-joined
# string in `$1`, which stopped working the moment the enumerators gained `-z`:
# a command substitution DISCARDS null bytes (bash even warns), so the three
# paths of a three-file commit arrived GLUED into one string and the count came
# back 1 instead of 3 — a coverage figure that under-reports is a false CLEAN
# waiting to happen. Reading NUL from stdin removes the round-trip entirely.
# Callers MUST use a process-substitution redirect (`< <( … )`), never a pipe:
# a pipe puts the loop in a subshell and both COVERED_COUNT and the
# COVERED_UNMEASURABLE flag would be lost on return.
count_covered() {
  local n=0 f e ce
  COVERED_COUNT=0
  covered_extensions
  if [ -z "$COVERED_EXTS" ]; then
    cat >/dev/null 2>&1 || true   # drain stdin so the writer never blocks
    return 0
  fi
  while IFS= read -r -d '' f; do
    [ -n "$f" ] || continue
    e="${f##*.}"
    [ "$e" != "$f" ] || continue            # no dot at all => no extension
    while IFS= read -r ce; do
      [ "$e" = "$ce" ] && { n=$((n + 1)); break; }
    done <<< "$COVERED_EXTS"
  done
  COVERED_COUNT="$n"
}

# files_changed_by <ref> — the paths THAT COMMIT touched. `<ref>~1..<ref>` is the
# normal form; a ROOT commit has no `~1`, so it falls back to `git show`, which
# lists a root commit's files correctly. Never `git diff <ref>` alone: that
# compares the ref to the WORKING TREE, which is the very confusion this option
# exists to remove.
#
# `-z` AND `--no-renames` ON EVERY ENUMERATION (T-00000370). Two git defaults
# corrupt a path list read line-by-line, and both are ON in a stock install:
#   * `core.quotePath=true` prints a non-ASCII path as `"caf\303\251.py"` —
#     quotes and octal escapes included — so `[ -f ]` fails on a file that
#     EXISTS and the partition below would file it under "deleted", exempting a
#     real, covered file from the scan forever. `-z` emits raw bytes instead.
#   * `diff.renames=true` collapses a rename into ONE record carrying TWO paths.
#     MEASURED, because the plan overstated this one and the honest bound matters:
#     with `--name-status` the record is `R100<TAB>old<TAB>new`, and a reader
#     taking one path per record drops the NEW file — the file carrying the new
#     code. With `--name-only`, WHICH IS WHAT THIS SCRIPT USES, git already prints
#     the new path (`autre.py`, `nouveau.py`); only the OLD name is omitted, and an
#     old name is a deleted path that `[ -f ]` would drop anyway. So `--no-renames`
#     here is NOT load-bearing for correctness — it is kept because it is
#     deterministic, faster, also disarms COPY (`C`) detection, and keeps the
#     enumeration correct if this ever moves to `--name-status`. Do not read it as
#     a guard against a bug that this form does not have.
# Both reads failing (T-01M4X9PP7FED0570PMPSYGA0V8, closing review T3: a partial
# clone without its trees offline, a missing parent object) lost the commit's
# files in silence; it now leaves `commit-census` in $SG_SIG — this runs in the
# subshell of `< <( … )` — which relever_signaux turns into a refusal to conclude.
# `--raw -z --no-abbrev` (T-01M4XY8NC97JBSQP6C28AFD7QP): each record is now
# `:<mode> <mode> <sha> <sha> <status>` NUL `<path>` NUL, so the caller also
# knows the BLOB the pointe holds (range_lire). The root fall-back carries
# `--root`: without it a repository's `log.showRoot false` makes `git show`
# list NOTHING, rc 0, no signal (measured: `nothing to scan` + CLEAN over a
# committed `os.system`); and `--no-show-signature`: `log.showSignature` of the
# scanned repository runs `gpg.program` on a signed pointe (measured). `--`
# after the revision: a file named like the ref makes it ambiguous.
files_changed_by() {  # $1 = ref  — raw records, NUL-separated
  git -C "$ROOT" "${GN[@]}" diff --raw -z --no-renames --no-abbrev "$1~1" "$1" -- 2>/dev/null \
    || git -C "$ROOT" "${GN[@]}" show --root --raw -z --no-renames --no-abbrev --no-show-signature --format= "$1" -- 2>/dev/null \
    || { if [ -n "${SG_SIG:-}" ]; then printf 'commit-census\n' >> "$SG_SIG"; fi; }
}

# files_changed_since <base> — the THREE-DOT form, i.e. the merge base. The naive
# two-dot form would include commits that are FOREIGN to this task as soon as the
# base moves on (`--since main` on a living `main`), manufacturing out-of-scope
# noise and a `DEGRADED` loop. A failed range census (T-01M4XY8PP8VYW0VVCYAAK0VARF)
# leaves `since-census` in $SG_SIG — it ran empty in silence before.
files_changed_since() {  # $1 = base — raw records, NUL-separated
  git -C "$ROOT" "${GN[@]}" diff --raw -z --no-renames --no-abbrev "$1...HEAD" -- 2>/dev/null \
    || { if [ -n "${SG_SIG:-}" ]; then printf 'since-census\n' >> "$SG_SIG"; fi; }
}

# ---- R-BASE: the ONE place that resolves the base ----------------------------
# Closed sources, in order: an explicit `--since`, then `@{upstream}` WHEN IT IS
# CONFIGURED, then INDETECTABLE. The third case is the point: without an upstream
# (throwaway repos, local clones, detached HEAD) the predicate "is this branch
# more than one commit from its fork" has NO TRUTH VALUE, and guessing either way
# is a defect — false means the dangerous first-parent fall-back returns, true
# means a denial of service on every repo without an upstream. So it PROCEEDS on
# HEAD alone and SAYS SO in the scope line. Never a silence, never a DoS.
# A source that ANSWERS serves as the base; it never triggers a refusal.
resolve_base() {  # echoes the base ref on stdout, or returns 1 (INDETECTABLE)
  if [ -n "$SINCE_BASE" ]; then printf '%s' "$SINCE_BASE"; return 0; fi
  if git -C "$ROOT" "${GN[@]}" rev-parse --verify --quiet '@{upstream}' >/dev/null 2>&1; then
    printf '%s' '@{upstream}'; return 0
  fi
  return 1
}

# head_is_merge — detectable WITHOUT any reference, by counting parents. This is
# why the merge case can refuse while the multi-commit case cannot.
head_is_merge() {
  [ "$(git -C "$ROOT" "${GN[@]}" rev-list --parents -n 1 HEAD 2>/dev/null | wc -w)" -gt 2 ]
}

# ---- WHAT GIT COMMITS IS READ, NOT ONLY THE WORKING TREE (T-01M4XY8NC97JBSQP6C28AFD7QP)
# Measured at c2a42ba2: a sink `git add`ed, then the file rewritten benign (D1a)
# or removed (D1b), read `clean on the diff.` — the commit then carried the
# sink; a sink COMMITTED under a benign working tree (D1c) read the same, by
# default and under `--at HEAD`; the hook Stop was mute (H1); a submodule's
# index was never read. The perimeter now carries GIT OBJECTS beside the files:
#   index:<rel>   an index entry that differs from HEAD (or from the empty tree
#                 when there is no commit yet) — the root at the gate (default
#                 and no-commit modes, never `--at`, which asks what a COMMIT
#                 changed) and each REACHABLE submodule; the root alone at the
#                 hook Stop. An unreachable submodule's index is NOT read (said),
#                 nor that of a partial clone under a git that cannot refuse a
#                 lazy fetch (said: index_candidats).
#   commit:<rel>  a path of the target's commits whose working-tree copy differs
#                 from the POINTE (HEAD, or the `--at` ref) or is not a readable
#                 regular file (deleted, skip-worktree absent). Only the pointe
#                 is read, never an intermediate commit.
# The LABELS exist before the attestation (they are part of the perimeter);
# the blobs are written only when semgrep runs, RAW by `git cat-file` (no
# filter), into a fresh `semgrep-objs.*` directory under $OUT (inside the
# repository, ignored, skipped by OUT_REL — see lire_objets), and the report
# paths are relabelled before any reader sees them. An object not read is a
# COUNTED loss; a staged copy identical to the tree is scanned twice (price).
OBJ_K=(); OBJ_G=(); OBJ_S=(); OBJ_R=(); OBJ_L=(); OBJ_PATHS=(); OBJ_FILTRE=0
RANGE_P=(); RANGE_SHA=()

# obj_ajouter <i|c> <repo> <sha> <rel> — one object, its label beside it. In the
# hook (OBJ_FILTRE=1) the name is filtered by COVERED_EXTS like the hook's tree
# census: an uncovered OR extension-less name is neither read nor scanned, MUTE,
# as at the gate — decision S-01M5162VM18MKHE0E8GGT1ZNCK, which re-decides the
# closing line C3 of the plan. Measured: semgrep 1.175 reads NO explicit target
# without an extension (absent from paths.scanned), so the gate concludes CLEAN
# over it; counting it at the Stop said a loss the gate never says, made every
# Stop DEGRADED and cut its clean-verdict cache. The extension-less guard is
# load-bearing for a base name that IS a covered extension (a file named `py`):
# without it that name would be read and handed to semgrep, which never reads it.
obj_ajouter() {  # $1 = i|c  $2 = repo dir  $3 = sha  $4 = rel (prefixed, ROOT-relative)
  local _b _e _ce _hit
  if [ "$OBJ_FILTRE" = 1 ]; then
    _b="${4##*/}"; _e="${_b##*.}"
    [ "$_e" != "$_b" ] || return 0
    _hit=0
    while IFS= read -r _ce; do [ "$_e" = "$_ce" ] && { _hit=1; break; }; done <<< "$COVERED_EXTS"
    [ "$_hit" = 1 ] || return 0
  fi
  OBJ_K+=("$1"); OBJ_G+=("$2"); OBJ_S+=("$3"); OBJ_R+=("$4")
  if [ "$1" = i ]; then
    OBJ_L+=("index:$4")
  else
    OBJ_L+=("commit:$4")
  fi
}

# retenu <rel> — TRUE iff classer_chemin would keep <rel> as a file to scan
# (a readable regular file), WITHOUT its loss counters.
retenu() {  # $1 = path relative to ROOT
  [ -f "$ROOT/$1" ] && [ -r "$ROOT/$1" ]
}

# _di_lire <repo> <tree-ish> <prefix> — one `diff-index --cached`, its rc read
# through an EMPTY record (a path is never empty) appended by the producer: the
# rc of a `< <( … )` is otherwise lost. A missing sentinel (the producer killed)
# leaves _di_rc=x, read as a failure. Stage 0 only, a deletion and a conflict
# (status D/U) carry no content; modes 100644/100755/120000 (a link's TARGET
# TEXT, never followed); a 040000 entry (a sparse index not expanded) is counted.
_di_lire() {  # $1 = repo dir  $2 = tree-ish  $3 = prefix  -> _di_rc _di_s[] _di_r[] _di_vide
  local rec p rest mode sha stg
  _di_rc=x; _di_s=(); _di_r=(); _di_vide=0
  while IFS= read -r -d '' rec; do
    if [ -z "$rec" ]; then
      IFS= read -r -d '' _di_rc
      break
    fi
    IFS= read -r -d '' p || break
    rest="${rec#* }"; mode="${rest%% *}"
    rest="${rest#* }"; rest="${rest#* }"
    sha="${rest%% *}"; stg="${rest#* }"
    case "$stg" in
      D*|U*)
        continue ;;
    esac
    case "$mode" in
      100644|100755|120000)
        _di_s+=("$sha"); _di_r+=("$3$p") ;;
      040000)
        _di_vide=$((_di_vide + 1)) ;;
    esac
  done < <(git -C "$1" "${GN[@]}" diff-index --cached -z --no-renames "$2" -- 2>/dev/null; printf '\0%s\0' "$?")
}

# index_candidats C <repo> <prefix> (port of gitleaks-scan.sh, branch C alone):
# the entries of the repo's index that differ from HEAD — or from the EMPTY
# tree, computed per repo, when there is no commit yet. Called in THIS shell.
# A partial clone under a git that cannot refuse a lazy fetch (paresseux) is
# NOT read: `diff-index --cached HEAD` reads HEAD's trees — absent from a
# treeless clone before any checkout, or after a `fetch` + `reset --soft`, a
# sparse one included — and FETCHED them, running the remote's uploadpack
# (security-code-review of 13a3cebf, measured in devsg9: the hook Stop ran it on
# such a root). Its staged objects are then not read either: the loss is said,
# before any git of this function.
index_candidats() {  # $1 = C  $2 = repo dir  $3 = prefix ("" at the root, "<sub_rel>/" in a submodule)
  local base i
  [ "$1" = C ] || return 0
  if paresseux "$2"; then
    perte_perimetre "?" "staged git object(s) not read (partial clone, git < 2.45: the index is not diffed against HEAD, a missing tree would be fetched, running the remote's uploadpack)"
    return 0
  fi
  _di_lire "$2" HEAD "$3"
  if [ "$_di_rc" != 0 ] && ! git -C "$2" "${GN[@]}" rev-parse -q --verify HEAD >/dev/null 2>&1; then
    # Not a repository at all: nothing to read, and the census already said so.
    git -C "$2" "${GN[@]}" rev-parse --git-dir >/dev/null 2>&1 || return 0
    base="$(git -C "$2" "${GN[@]}" hash-object -t tree /dev/null 2>/dev/null)" || base=""
    if [ -z "$base" ]; then
      perte_perimetre 1 "git index of a repository not read (no empty tree)"
      return 0
    fi
    _di_lire "$2" "$base" "$3"
  fi
  if [ "$_di_rc" != 0 ]; then
    perte_perimetre 1 "git index of a repository not read (diff-index failed)"
    return 0
  fi
  if [ "$_di_vide" -gt 0 ]; then
    perte_perimetre "$_di_vide" "sparse-index directory entr(y|ies) not expanded"
  fi
  i=0
  while [ "$i" -lt "${#_di_s[@]}" ]; do
    obj_ajouter i "$2" "${_di_s[$i]}" "${_di_r[$i]}"
    i=$((i + 1))
  done
}

# objets_pointe <pointe> — the commit objects of RANGE_P/RANGE_SHA (the target's
# committed paths and their blob at the pointe): (ii) every path that is not a
# readable regular file in the tree (deleted, skip-worktree absent, unreadable),
# then (i) every path whose working-tree copy differs from the pointe, by ONE
# `diff --raw` against the pointe over those paths (xargs: no ARG_MAX bound),
# its source side giving the pointe's blob. A failed diff (xargs rc != 0), a
# filter driver not neutralized, or a partial clone that cannot refuse a lazy
# fetch: SAFE BY DEFAULT, every path of RANGE_P becomes an object. A tree equal
# to the pointe gives no object. (iii) (closing review B1) an entry git NEVER
# compares — assume-unchanged (lowercase tag of `ls-files -v`, set on every
# path `git add` stages under core.ignoreStat=true) or skip-worktree (`S`): the
# diff takes its INDEX copy for the tree, so a committed sink rewritten benign
# there, unstaged, read equal to the pointe (measured at be913df4: rc 0, CLEAN,
# by default and under `--at HEAD`). Such a path is an object, the tree
# readable or not; ONE `ls-files -v` over RANGE_P (xargs), its rc read through
# the sentinel — a failure is SAFE BY DEFAULT too. The flagged set is a
# newline-framed string, matched by a QUOTED pattern (literal): a path holding
# a newline can only add an object, never drop one. Called in THIS shell.
objets_pointe() {  # $1 = pointe (HEAD or the --at ref)
  local i p rec rest mode sha _rc _rcv _aa _ok=1 _nl=$'\n' _fls
  local -a _ps=() _pp=()
  _fls="$_nl"
  [ "${#RANGE_P[@]}" -gt 0 ] || return 0
  neutres_racine
  if [ "$_PARESSEUX" = 1 ] || [ "$_neutres_ok" != 1 ]; then
    _ok=0
  else
    _rc=x
    while IFS= read -r -d '' rec; do
      if [ -z "$rec" ]; then
        IFS= read -r -d '' _rc
        break
      fi
      IFS= read -r -d '' p || break
      rest="${rec#:}"; mode="${rest%% *}"
      rest="${rest#* }"; rest="${rest#* }"
      sha="${rest%% *}"
      case "$mode" in
        100644|100755|120000)
          _ps+=("$sha"); _pp+=("$p") ;;
      esac
    done < <(printf '%s\0' "${RANGE_P[@]}" | xargs -0 git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} --literal-pathspecs diff --raw -z --no-renames --no-abbrev --no-ext-diff --no-textconv --ignore-submodules=dirty "$1" -- 2>/dev/null; printf '\0%s\0' "$?")
    [ "$_rc" = 0 ] || _ok=0
    # A sparse-index entry naming an absent tree: the `ls-files -v` below would
    # OMIT its entries, rc 0 (arbres_absents, MAJEUR) — SAFE BY DEFAULT instead.
    if [ "$_ok" = 1 ]; then
      _aa=0
      arbres_absents "$ROOT" || _aa=$?
      [ "$_aa" = 1 ] || _ok=0
    fi
    # (iii) the entries the diff above never compared.
    if [ "$_ok" = 1 ]; then
      _rcv=x
      while IFS= read -r -d '' rec; do
        if [ -z "$rec" ]; then
          IFS= read -r -d '' _rcv
          break
        fi
        case "$rec" in
          [hsmrckS]" "*)
            _fls="$_fls${rec#??}$_nl" ;;
        esac
      done < <(printf '%s\0' "${RANGE_P[@]}" | xargs -0 git -C "$ROOT" "${GN[@]}" --literal-pathspecs ls-files -v -z -- 2>/dev/null; printf '\0%s\0' "$?")
      [ "$_rcv" = 0 ] || _ok=0
    fi
  fi
  if [ "$_ok" = 1 ]; then
    i=0
    while [ "$i" -lt "${#RANGE_P[@]}" ]; do
      retenu "${RANGE_P[$i]}" || obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}"
      i=$((i + 1))
    done
    # (iii) a readable path git never compares: an object (a non-readable one
    # came in by (ii) just above).
    i=0
    while [ "$i" -lt "${#RANGE_P[@]}" ]; do
      case "$_fls" in
        *"$_nl${RANGE_P[$i]}$_nl"*)
          retenu "${RANGE_P[$i]}" && obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}" ;;
      esac
      i=$((i + 1))
    done
    i=0
    while [ "$i" -lt "${#_pp[@]}" ]; do
      # A path the tree does not hold as a readable file came in by (ii) above;
      # one git never compares, by (iii).
      case "$_fls" in
        *"$_nl${_pp[$i]}$_nl"*)
          : ;;
        *)
          retenu "${_pp[$i]}" && obj_ajouter c "$ROOT" "${_ps[$i]}" "${_pp[$i]}" ;;
      esac
      i=$((i + 1))
    done
  else
    i=0
    while [ "$i" -lt "${#RANGE_P[@]}" ]; do
      obj_ajouter c "$ROOT" "${RANGE_SHA[$i]}" "${RANGE_P[$i]}"
      i=$((i + 1))
    done
  fi
}

# range_lire <rec> <path> — one `--raw -z` record of the target's commits: the
# path goes to PROPOSED (as before), and to RANGE_P/RANGE_SHA when the pointe
# holds a blob there (mode 100644/100755/120000, status != D).
range_lire() {  # $1 = raw meta record  $2 = path
  local rest mode sha stg
  PROPOSED+=("$2")
  rest="${1#:}"; rest="${rest#* }"; mode="${rest%% *}"
  rest="${rest#* }"; rest="${rest#* }"
  sha="${rest%% *}"; stg="${rest#* }"
  case "$stg" in
    D*)
      return 0 ;;
  esac
  case "$mode" in
    100644|100755|120000)
      RANGE_P+=("$2"); RANGE_SHA+=("$sha") ;;
  esac
}

# ---- the reader of git objects (port of SYM-19224 lire_index, LIRE_INDEX_PY,
# SYM-19217 garde_enfant). When python answers: ONE `git cat-file --batch` per
# (repository, kind), exactly <size> bytes per object, each file created
# O_EXCL|O_NOFOLLOW under the destination, a path that is absolute or carries an
# empty, "." or ".." component (or a backslash) refused and counted as NOT
# read. Its own deadline kills git. One line per candidate READ on stdout: "w
# <k>" written, "d <k>" the SAME object (same sha) already written at the SAME
# path in this run; nothing for a candidate NOT read. A destination that EXISTS
# for any other reason is NOT read: on APFS (case-insensitive) index `K.py`
# benign + `k.py` holding a sink collide, and trusting mere existence would
# scan the benign one under both names.
LIRE_INDEX_PY='
import os, subprocess, sys, threading, time
lim = float(sys.argv[1])
dest, cand, cmd = sys.argv[2], sys.argv[3], sys.argv[4:]
fin = time.monotonic() + lim
FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
with open(cand, "rb") as fh:
    parts = fh.read().split(b"\0")
rc = 0
written = {}
try:
    git = subprocess.Popen(cmd + ["cat-file", "--batch"], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
except OSError:
    sys.exit(1)
minuteur = threading.Timer(max(lim, 0.0), git.kill)
minuteur.daemon = True
minuteur.start()
def parents(comps):
    d = dest
    for c in comps[:-1]:
        d = os.path.join(d, os.fsdecode(c))
        try:
            os.mkdir(d, 0o700)
        except FileExistsError:
            pass
k = -1
for sha, rel in zip(parts[0::2], parts[1::2]):
    k += 1
    if time.monotonic() >= fin:
        rc = 3
        break
    if not os.path.isdir(dest):
        rc = 3
        break
    comps = rel.split(b"/")
    if b"\\" in rel or (os.name == "nt" and b":" in rel) or any(c in (b"", b".", b"..") for c in comps):
        rc = 1
        continue
    try:
        git.stdin.write(sha + b"\n")
        git.stdin.flush()
        hdr = git.stdout.readline().split()
    except OSError:
        rc = 3
        break
    if not hdr:
        rc = 3
        break
    if len(hdr) != 3 or hdr[1] != b"blob":
        rc = 1
        continue
    left = int(hdr[2])
    full = os.path.join(dest, *[os.fsdecode(c) for c in comps])
    out = None
    seen = False
    try:
        parents(comps)
        out = os.fdopen(os.open(full, FLAGS, 0o600), "wb")
    except FileExistsError:
        seen = written.get(rel) == sha
    except OSError:
        out = None
    ecrit = out is not None
    while left > 0:
        bloc = git.stdout.read(min(left, 1048576))
        if not bloc:
            break
        left -= len(bloc)
        if ecrit:
            try:
                out.write(bloc)
            except OSError:
                ecrit = False
    git.stdout.read(1)
    if out is not None:
        try:
            out.close()
        except OSError:
            ecrit = False
    if left > 0:
        rc = 3
        break
    if ecrit:
        written[rel] = sha
        sys.stdout.write("w %d\n" % k)
    elif seen:
        sys.stdout.write("d %d\n" % k)
    else:
        rc = 1
try:
    git.stdin.close()
except OSError:
    pass
try:
    git.wait(timeout=max(fin - time.monotonic(), 1.0))
except Exception:
    git.kill()
minuteur.cancel()
sys.stdout.flush()
sys.exit(rc)
'

# garde_enfant <cmd…>: runs ONE writer of the objects in the BACKGROUND, its pid
# in _LECTEUR, and waits for it — so that the EXIT trap can kill and reap it
# BEFORE removing $OBJ (a SIGTERM to this shell alone left gitleaks' reader
# orphaned, writing a blob after the cleanup — measured there).
_LECTEUR=""
garde_enfant() {
  local rc
  "$@" &
  _LECTEUR=$!
  wait "$_LECTEUR"; rc=$?
  _LECTEUR=""
  return "$rc"
}

# lire_objets <deadline s> — writes the objects under $OBJ/i/<rel> (index) and
# $OBJ/c/<rel> (commit) and sets OBJ_PATHS to the files WRITTEN, never to the
# ones asked (a semgrep target that does not exist answers `Invalid scanning
# root` and loses every finding of the tree). Written < asked: a counted loss.
# $OBJ is made under $OUT (`.agents/state/local/sca-reports`), INSIDE the
# repository, never under TMPDIR — except when $OUT is reached through a
# symbolic link (out_prive: $OUT is then the private directory under TMPDIR,
# at the price below): semgrep launched from a repository pays a
# fixed price per target that lies OUTSIDE it — measured with semgrep 1.175 on
# a clone of the kit, the same 50 objects took 13.2 s under TMPDIR and 1.96 s
# in an ignored directory of the clone. $OUT is ignored where the kit is
# installed (`.agents/.gitignore`: `state/local/`), the two censuses skip
# OUT_REL, and semgrep scans an EXPLICIT target even when `.gitignore` or a
# `.semgrepignore` covers it (measured, 1.175). $OUT has no trailing slash (it
# is built from `pwd`), so the report paths keep the `$OBJ/i/` prefix that
# reecrire_rapport strips. Without python, one `cat-file blob` per object under
# timeout(1), with the same "same sha at the same path" rule.
lire_objets() {  # $1 = deadline in seconds for the whole read
  local tot i j k l _fin _rest _w=0 _d=0 _paress=0 manque dest p sha _vu _es _ep _dit=0
  local -a gk=() gd=() _sel=() etat=() pre=()
  OBJ_PATHS=()
  tot="${#OBJ_S[@]}"
  [ "$tot" -gt 0 ] || return 0
  OBJ="$(mktemp -d "$OUT/semgrep-objs.XXXXXX" 2>/dev/null)" || OBJ=""
  if [ -z "$OBJ" ] || ! mkdir "$OBJ/i" "$OBJ/c" 2>/dev/null; then
    perte_perimetre "$tot" "git object(s) not read (index or commit content not scanned)"
    return 0
  fi
  i=0
  while [ "$i" -lt "$tot" ]; do
    etat+=("-")
    j=0
    while [ "$j" -lt "${#gk[@]}" ]; do
      [ "${gk[$j]}" = "${OBJ_K[$i]}" ] && [ "${gd[$j]}" = "${OBJ_G[$i]}" ] && break
      j=$((j + 1))
    done
    if [ "$j" -eq "${#gk[@]}" ]; then
      gk+=("${OBJ_K[$i]}"); gd+=("${OBJ_G[$i]}")
    fi
    i=$((i + 1))
  done
  _fin=$((SECONDS + $1))
  j=0
  while [ "$j" -lt "${#gk[@]}" ]; do
    _sel=()
    : > "$OBJ/cand"
    i=0
    while [ "$i" -lt "$tot" ]; do
      if [ "${OBJ_K[$i]}" = "${gk[$j]}" ] && [ "${OBJ_G[$i]}" = "${gd[$j]}" ]; then
        printf '%s\0%s\0' "${OBJ_S[$i]}" "${OBJ_R[$i]}" >> "$OBJ/cand"
        _sel+=("$i")
      fi
      i=$((i + 1))
    done
    dest="$OBJ/${gk[$j]}"
    # A partial clone under a git that cannot refuse a lazy fetch (paresseux):
    # no cat-file at all — its objects are a counted loss, never a fetch.
    if paresseux "${gd[$j]}"; then
      _paress=$((_paress + ${#_sel[@]}))
      j=$((j + 1))
      continue
    fi
    _rest=$((_fin - SECONDS))
    [ "$_rest" -gt 0 ] || break
    if [ -n "$PY" ]; then
      : > "$OBJ/lu"
      garde_enfant "$PY" -I -c "$LIRE_INDEX_PY" "$_rest" "$dest" "$OBJ/cand" git -C "${gd[$j]}" "${GN[@]}" > "$OBJ/lu" 2>/dev/null
      while IFS= read -r l; do
        k="${l#? }"
        case "$k" in
          ''|*[!0-9]*)
            continue ;;
        esac
        [ "$k" -lt "${#_sel[@]}" ] || continue
        case "$l" in
          w*)
            etat[${_sel[$k]}]=w ;;
          d*)
            etat[${_sel[$k]}]=d ;;
        esac
      done < "$OBJ/lu"
      j=$((j + 1))
      continue
    fi
    pre=()
    if have timeout; then
      pre=(timeout 1)
    elif [ "$_dit" = 0 ]; then
      echo "note: git object read unbounded (no timeout(1), no python) — a blocked git call is not bounded" >&2
      _dit=1
    fi
    : > "$OBJ/ecrits"
    k=0
    while [ "$k" -lt "${#_sel[@]}" ]; do
      i="${_sel[$k]}"; p="${OBJ_R[$i]}"; sha="${OBJ_S[$i]}"
      k=$((k + 1))
      _rest=$((_fin - SECONDS))
      [ "$_rest" -gt 0 ] || break
      case "/$p/" in
        *"/../"*|*"/./"*|*"//"*|*"\\"*)
          continue ;;
      esac
      if [ -e "$dest/$p" ] || [ -L "$dest/$p" ]; then
        # SAME rule as the python reader: read ONLY if this run already wrote
        # the same sha at this very path; anything else — a case or Unicode
        # collision on an insensitive file system — is a loss.
        _vu=0
        while IFS= read -r -d '' _es && IFS= read -r -d '' _ep; do
          if [ "$_ep" = "$p" ] && [ "$_es" = "$sha" ]; then
            _vu=1
            break
          fi
        done < "$OBJ/ecrits"
        [ "$_vu" = 1 ] && etat[$i]=d
        continue
      fi
      case "$p" in
        */*)
          garde_enfant mkdir -p "$dest/${p%/*}" 2>/dev/null || continue ;;
      esac
      if [ "${#pre[@]}" -gt 0 ]; then
        pre=(timeout "$_rest")
      fi
      if garde_enfant ${pre[@]+"${pre[@]}"} git -C "${gd[$j]}" "${GN[@]}" cat-file blob "$sha" > "$dest/$p" 2>/dev/null; then
        etat[$i]=w
        printf '%s\0%s\0' "$sha" "$p" >> "$OBJ/ecrits"
      else
        rm -f "$dest/$p"
      fi
    done
    j=$((j + 1))
  done
  i=0
  while [ "$i" -lt "$tot" ]; do
    case "${etat[$i]}" in
      w)
        _w=$((_w + 1)); OBJ_PATHS+=("$OBJ/${OBJ_K[$i]}/${OBJ_R[$i]}") ;;
      d)
        _d=$((_d + 1)) ;;
    esac
    i=$((i + 1))
  done
  manque=$((tot - _w - _d - _paress))
  if [ "$manque" -gt 0 ]; then
    perte_perimetre "$manque" "git object(s) not read (index or commit content not scanned)"
  fi
  if [ "$_paress" -gt 0 ]; then
    perte_perimetre "$_paress" "git object(s) not read (partial clone, git < 2.45: a missing blob would be fetched, running the remote's uploadpack)"
  fi
}

# reecrire_rapport <report> — the machine paths of the objects become their
# LABELS, in the five fields that carry a path (results[].path, paths.scanned,
# paths.skipped[].path, errors[].path, errors[].type[1][].path), BEFORE any
# reader (scan_verdict.py, the PARSE, PHASE B) sees the report; os.replace. A
# machine path LEFT in one of those five fields (the object directory still in
# it) is a counted loss — never printed. Other fields (a message) are neither
# rewritten nor checked (closing line C5 of the plan). Without python: no
# rewrite (the PARSE is `nopython`, no reader receives a machine path).
# A rule `paths:` filter judges an object on its MACHINE path (closing review
# M3: a rule excluding `.agents/` left `commit:k.py` and `index:k.py` unscanned,
# CLEAN, a note in paths.scanned only): every object WRITTEN ($OBJ/ecrits,
# OBJ_PATHS NUL-separated, argv[4] — a LIST, never a walk of $OBJ: the census
# of tree walks, test_repo_walk_census.py, refuses an unclassified one) whose
# working-tree twin is in the perimeter ($OBJ/arbre, FILES NUL-separated,
# argv[3]) AND was scanned, while the object was not, is COUNTED (`manque`) —
# a loss said by the caller. An object without a twin in the tree (D1b) is
# still judged on its machine path alone (bound said in the README); an
# unreadable list prints `manque ?`, a loss too.
RECRIRE_PY='
import json, os, sys, tempfile
rapport, obj = sys.argv[1], sys.argv[2]
pre = ((obj + "/i/", "index:"), (obj + "/c/", "commit:"))
base = os.path.basename(obj)
reste = [0]
def lab(v):
    if not isinstance(v, str):
        return v
    for a, b in pre:
        if v.startswith(a):
            v = b + v[len(a):]
            break
    if base in v:
        reste[0] += 1
    return v
try:
    with open(rapport, encoding="utf-8") as fh:
        d = json.load(fh)
except Exception:
    print("illisible")
    sys.exit(0)
if not isinstance(d, dict):
    print("illisible")
    sys.exit(0)
for r in d.get("results") or []:
    if isinstance(r, dict) and "path" in r:
        r["path"] = lab(r["path"])
p = d.get("paths")
if isinstance(p, dict):
    if isinstance(p.get("scanned"), list):
        p["scanned"] = [lab(x) for x in p["scanned"]]
    for s in p.get("skipped") or []:
        if isinstance(s, dict) and "path" in s:
            s["path"] = lab(s["path"])
for e in d.get("errors") or []:
    if not isinstance(e, dict):
        continue
    if "path" in e:
        e["path"] = lab(e["path"])
    t = e.get("type")
    if isinstance(t, list) and len(t) > 1 and isinstance(t[1], list):
        for it in t[1]:
            if isinstance(it, dict) and "path" in it:
                it["path"] = lab(it["path"])
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(rapport) or ".", prefix=".semgrep-rw.")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(d, fh)
os.replace(tmp, rapport)
try:
    with open(sys.argv[3], "rb") as fh:
        arbre = set(x for x in fh.read().decode("utf-8", "surrogateescape").split("\0") if x)
except Exception:
    print("reste %d manque ?" % reste[0])
    sys.exit(0)
sc = set(x for x in (p.get("scanned") or []) if isinstance(x, str)) if isinstance(p, dict) else set()
try:
    with open(sys.argv[4], "rb") as fh:
        ecrits = [x for x in fh.read().decode("utf-8", "surrogateescape").split("\0") if x]
except Exception:
    print("reste %d manque ?" % reste[0])
    sys.exit(0)
manque = 0
for x in ecrits:
    for a, lab_k in pre:
        if x.startswith(a):
            rel = x[len(a):]
            if rel in arbre and rel in sc and (lab_k + rel) not in sc:
                manque += 1
            break
print("reste %d manque %d" % (reste[0], manque))
'
reecrire_rapport() {  # $1 = report file
  local _r
  [ "${#OBJ_PATHS[@]}" -gt 0 ] && [ -n "$OBJ" ] && [ -n "$PY" ] || return 0
  printf '%s\0' ${FILES[@]+"${FILES[@]}"} > "$OBJ/arbre" 2>/dev/null
  printf '%s\0' "${OBJ_PATHS[@]}" > "$OBJ/ecrits" 2>/dev/null
  _r="$("$PY" -I -c "$RECRIRE_PY" "$1" "$OBJ" "$OBJ/arbre" "$OBJ/ecrits" 2>/dev/null)" || _r="echec"
  case "$_r" in
    "reste 0 manque 0"|illisible)
      : ;;
    "reste 0 manque "*)
      perte_perimetre "${_r##* }" "git object(s) not scanned while their working-tree twin was (a rule paths: filter judged the machine path)" ;;
    *)
      perte_perimetre 1 "report paths not relabelled (machine paths left)" ;;
  esac
}

# ---- HOOK MODE (T-00000459, Lot A) ------------------------------------------
# A self-contained handler that NEVER falls through to the gate code below, so
# the gate path stays byte-identical. The registration that will drive it lands
# in Lot B (T-00000476); until then this only runs from the flag and its own
# test suite. Two python passes: PHASE A decides + emits every NON-scan outcome
# (absent, inert, unknown tool, unknown path-key, non-JSON, mute) and writes a
# directive; PHASE B, after semgrep has run, emits findings/clean/degraded.
# Everything the payload needs is READ from real graphies parsed elsewhere in
# this repo (SYM-005..SYM-011 recopiées inline, no import). Two of those copies
# are DURCIES rather than verbatim, because the payload is UNTRUSTED STDIN:
# (a) SYM-009 (normalize_path) CONFINES every candidate to root — SYM-009's own
#     code does NOT (it keeps the outside path on the relative_to ValueError), so
#     citing it as the traversal defense without the confinement clause was a
#     doc asserting a guarantee the code did not hold (L-00000111). A `..` or an
#     absolute path outside the repo is now dropped, and a shell belt in PHASE B
#     backs it up (CWE-22, defense in depth).
# (b) SYM-011's `*** …File:` apply_patch regex is BOUNDED to apply_patch (its own
#     grammar), no longer scanned on every tool's `command`.
# EMPREINTE DU STOP (T-00000836) — règles, contenus, chemins. `--no-filters` :
# sans lui, `core.autocrlf` (défaut de Git for Windows) ou un filtre `clean`
# rendrait le même hash pour deux contenus différents (CRLF/LF mesuré). Lit
# FILES, CFG, ROOT ; $1 = chemin résolu des règles. LES OBJETS AUSSI
# (T-01M4Z5T5SKZA63MCWM1VRTZ6D8) : une ligne `obj <sha> <étiquette>` par objet
# de l'index — sans elle, un CLEAN mis en cache sur des octets d'arbre
# identiques servait un puits `git add`é ensuite.
sc_empreinte() {
  local h i
  h="$(git -C "$ROOT" "${GN[@]}" hash-object --no-filters -- "$1" ${FILES[@]+"${FILES[@]}"} 2>/dev/null)" || return 1
  {
    printf 'cfg %s\n%s\n' "$CFG" "$h"
    printf '%s\n' ${FILES[@]+"${FILES[@]}"}
    i=0
    while [ "$i" -lt "${#OBJ_S[@]}" ]; do
      printf 'obj %s %s\n' "${OBJ_S[$i]}" "${OBJ_L[$i]}"
      i=$((i + 1))
    done
  } | git -C "$ROOT" "${GN[@]}" hash-object --stdin 2>/dev/null
}

# hk_nettoyer — the EXIT trap of the HOOK (T-01M4Z5T5SKZA63MCWM1VRTZ6D8): the
# Stop now writes work files (_TMP_FN, _TMP_SW, SG_SIG, SG_LSERR) under TMPDIR
# and git objects ($OBJ) under $OUT, and a signal before their in-line removal
# must not leave them there.
# Installed by run_hook_mode BEFORE its first mktemp; only the shell that
# installed it may run it ($BASHPID, as cleanup() of the gate); a writer of the
# objects still running is killed and reaped first (garde_enfant).
HK_OWNER=""
hk_nettoyer() {
  [ "${BASHPID:-$$}" = "$HK_OWNER" ] || return 0
  [ -n "${_LECTEUR:-}" ] && { kill "$_LECTEUR" 2>/dev/null; wait "$_LECTEUR" 2>/dev/null; }
  [ -n "${OBJ:-}" ] && rm -rf -- "$OBJ"
  [ -n "${_TMP_FN:-}" ] && rm -f -- "$_TMP_FN"
  [ -n "${_TMP_SW:-}" ] && rm -f -- "$_TMP_SW"
  [ -n "${SG_SIG:-}" ] && rm -f -- "$SG_SIG"
  [ -n "${SG_LSERR:-}" ] && rm -f -- "$SG_LSERR"
  [ -n "${OUT_PRIVE:-}" ] && rm -rf -- "$OUT_PRIVE"
  return 0
}

run_hook_mode() {
  local INPUT HOST MARKDIR PFILE DIRECTIVE CANDS REPORT RESULT HAVE action HK_H16
  local rverdict rcount rec rtrans e ce cand hit rc SC_EMPREINTE SC_CFG _b
  INPUT="$(cat)"
  HOST="${AGENTS_HOOK_HOST:-claude}"          # ABSENT -> claude (gitleaks-scan.sh:61)
  MARKDIR="$ROOT/.agents/state/local/semgrep-hook"

  # The EXIT trap is installed FIRST: the private directory below, the work
  # files and the git objects are all removed by it, whatever the exit.
  _TMP_FN=""; _TMP_SW=""; OBJ=""; SG_LSERR=""
  HK_OWNER="${BASHPID:-$$}"
  trap hk_nettoyer EXIT

  # $OUT, a parent of it under ROOT, or a fixed name written in place is a
  # symbolic link (OUT_LIEN, tested at the top before the only mkdir): the hook
  # goes on in a PRIVATE directory (out_prive) — its markers, its clean-verdict
  # cache and its audit line are lost with it, a loss said before the scan.
  # Only when that directory cannot be made is it refused HERE, before any
  # write. The event is resolved as in the no-python branch below (the flag,
  # then hook_event_name grepped from the raw payload, then post); the literals
  # are FIXED and APOSTROPHE-FREE, as there.
  if [ -n "$OUT_LIEN" ]; then
    out_prive
  fi
  if [ -n "$OUT_LIEN" ] && [ -n "$OUT" ]; then
    MARKDIR="$OUT/semgrep-hook"
  elif [ -n "$OUT_LIEN" ]; then
    echo "COVERAGE DEGRADED: SAST hook — the report directory (.agents/state/local/sca-reports, a parent of it or a fixed name in it) is a symbolic link and no private directory could be made; refused before any write, nothing scanned" >&2
    NL_EVT="$HOOK_EVENT"
    if [ -z "$NL_EVT" ]; then
      if printf '%s' "$INPUT" | grep -Eiq '"hook_event_name"[[:space:]]*:[[:space:]]*"(agent)?stop"'; then
        NL_EVT="stop"
      else
        NL_EVT="post"
      fi
    fi
    if [ "$NL_EVT" = "stop" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned."}\n'
    elif [ "$HOST" = "copilot" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned."}, "additionalContext": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned."}\n'
    else
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook — the report directory is a symbolic link and no private directory could be made; refused before any write, nothing scanned."}}\n'
    fi
    exit 0
  fi

  # No interpreter to read the JSON payload -> announce, never block (like the
  # semgrep-absent branch of the gate, safe-bash.sh:88): stderr + systemMessage.
  if [ -z "$PY" ]; then
    echo "COVERAGE DEGRADED: SAST hook — no python on PATH to read the payload; hook INACTIF" >&2
    # Resolve the event WITHOUT a JSON parser: the flag if the registration set
    # one, else hook_event_name grepped from the raw payload (stop|agentstop =>
    # stop), else post — the SAME precedence PHASE A applies, so the journal
    # names the resolved event, never just the flag. The DEGRADED form then
    # follows the resolved event: the two-key union in post, systemMessage alone
    # in stop. The literal is FIXED and APOSTROPHE-FREE (C3) — it lives in a
    # single-quoted printf, where a French apostrophe would close the string
    # under any bash; the SAME English message is repeated in BOTH keys.
    NP_EVT="$HOOK_EVENT"
    if [ -z "$NP_EVT" ]; then
      if printf '%s' "$INPUT" | grep -Eiq '"hook_event_name"[[:space:]]*:[[:space:]]*"(agent)?stop"'; then
        NP_EVT="stop"
      else
        NP_EVT="post"
      fi
    fi
    # Under copilot only (T-01M4RWC0DBM6XC1PDQGEG4P79C), post ALSO carries the
    # context at the TOP level, the field the Copilot CLI reads — still a FIXED
    # literal, no interpolation; every other host keeps the two-key union.
    if [ "$NP_EVT" = "stop" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload."}\n'
    elif [ "$HOST" = "copilot" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload."}, "additionalContext": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload."}\n'
    else
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook inactive — no python to read the payload."}}\n'
    fi
    AUDIT_MODE="hook" AUDIT_EVENT="$NP_EVT" audit "DEGRADED" 0 "[]"
    AUDIT_MODE="hook" AUDIT_EVENT="$NP_EVT" emit_scan degraded 0 "[]"
    exit 0
  fi

  HAVE=0; have semgrep && HAVE=1
  mkdir -p "$MARKDIR" 2>/dev/null || true
  PFILE="$(mktemp "${TMPDIR:-$OUT}/.semgrep-hk-pl.XXXXXX")"
  DIRECTIVE="$(mktemp "${TMPDIR:-$OUT}/.semgrep-hk-dir.XXXXXX")"
  CANDS="$(mktemp "${TMPDIR:-$OUT}/.semgrep-hk-cnd.XXXXXX")"
  printf '%s' "$INPUT" > "$PFILE"

  # ---- PHASE A: decide + emit every non-scan outcome ------------------------
  HK_PAYLOAD_FILE="$PFILE" HK_EVENT="$HOOK_EVENT" HK_EVENT_SEEN="$HOOK_EVENT_SEEN" \
  HK_HOST="$HOST" HK_ROOT="$ROOT" HK_MARKDIR="$MARKDIR" HK_HAVE="$HAVE" \
  HK_DIRECTIVE="$DIRECTIVE" HK_CANDS="$CANDS" \
  "$PY" - <<'HKAEOF'
import os, sys, json, re, hashlib

root          = os.environ["HK_ROOT"]
markdir       = os.environ["HK_MARKDIR"]
host          = os.environ["HK_HOST"]
have          = os.environ["HK_HAVE"] == "1"
event_flag    = os.environ.get("HK_EVENT", "")
event_seen    = os.environ.get("HK_EVENT_SEEN", "0") == "1"
directive_f   = os.environ["HK_DIRECTIVE"]
cands_f       = os.environ["HK_CANDS"]
payload_raw   = open(os.environ["HK_PAYLOAD_FILE"], encoding="utf-8").read()

def directive(action, sid16=""):
    # line 1 = action, line 2 = h16 (SCANSTOP reads it for its once-per-session
    # marker), line 3 = the RESOLVED event (flag -> hook_event_name -> post) so
    # the shell audits what PHASE A resolved, never the raw --event flag.
    with open(directive_f, "w", encoding="utf-8") as fh:
        fh.write("%s\n%s\n%s\n" % (action, sid16, event))

def degraded_form(event, msg):
    # PER EVENT: post = ONE object with BOTH keys (systemMessage in service on
    # claude, additionalContext in service on codex — the union loses a host only
    # if it ignores BOTH); stop = systemMessage alone (unchanged). ONE host case,
    # additive only (T-01M4RWC0DBM6XC1PDQGEG4P79C): under copilot, post ALSO
    # carries additionalContext at the TOP level, the field the Copilot CLI reads;
    # the two-key union stays byte-identical for every other host.
    if event == "stop":
        return json.dumps({"systemMessage": msg})
    body = {"systemMessage": msg,
            "hookSpecificOutput":
            {"hookEventName": "PostToolUse", "additionalContext": msg}}
    if host == "copilot":
        body["additionalContext"] = msg
    return json.dumps(body)

def marker_new(name):
    # True iff freshly created (O_CREAT|O_EXCL, stop-arbitrate.sh:62). No sid ->
    # cannot bound -> speak every call (the bound is DECLARED, never silent).
    if not name:
        return True
    try:
        os.makedirs(markdir, exist_ok=True)
        fd = os.open(os.path.join(markdir, name), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        return True

# --- payload parse (non-JSON in post = case (e) degraded) ---
try:
    payload = json.loads(payload_raw) if payload_raw.strip() else {}
    if not isinstance(payload, dict):
        payload = {}
    parsed = True
except Exception:
    payload, parsed = {}, False

# --- event: FLAG first, hook_event_name fall-back, post default ---
if event_seen and event_flag in ("post", "stop"):
    event = event_flag
else:
    hen = str(payload.get("hook_event_name") or "").strip().lower()
    event = "stop" if hen in ("stop", "agentstop") else "post"

# --- session id (never raw in a filename) + h16 ---
sid = ""
for k in ("session_id", "sessionId", "conversationId"):
    if payload.get(k):
        sid = str(payload.get(k)); break
h16 = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16] if sid else ""

def safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "")

def emit_degraded(msg, marker=None):
    # C26/L-00000347: stderr AND stdout, deduped by marker. On a repeat (marker
    # present) BOTH channels stay silent — the arms assert stdout non-empty on
    # the 1st call, empty on the 2nd. The form is PER EVENT (degraded_form): the
    # two-key union in post, systemMessage alone in stop — the inert branch below
    # now takes the SAME form as every other path, with no special-cased override.
    new = marker_new(marker) if marker is not None else True
    if new:
        sys.stderr.write(msg + "\n")
        sys.stdout.write(degraded_form(event, msg) + "\n")
    directive("DEGRADED")

if not parsed:
    emit_degraded("COVERAGE DEGRADED: SAST hook — payload not readable JSON")
    sys.exit(0)

# --- semgrep absent: stderr EVERY call + systemMessage ONCE per session ---
if not have:
    msg = ("COVERAGE DEGRADED: semgrep not installed — SAST hook INACTIF sur cet "
           "hôte (install : README-SECURITY-SCAN-SETUP.md § SAST)")
    sys.stderr.write(msg + "\n")
    if (not h16) or marker_new("absent-" + h16):
        sys.stdout.write(degraded_form(event, msg) + "\n")
    directive("DEGRADED")
    sys.exit(0)

# --- SYM-008 tool_args / SYM-007 tool_name / SYM-009 normalize / SYM-011 paths (inline) ---
def tool_args(pl):
    args = (pl.get("toolArgs") or pl.get("tool_args") or pl.get("toolInput")
            or pl.get("tool_input") or pl.get("input") or pl.get("arguments") or {})
    if isinstance(args, str):
        try:
            j = json.loads(args)
            return j if isinstance(j, dict) else {"command": args, "raw": args}
        except Exception:
            return {"command": args, "raw": args}
    return args if isinstance(args, dict) else {}

def tool_name(pl):
    return (pl.get("toolName") or pl.get("tool_name") or pl.get("tool")
            or pl.get("name") or "")

def normalize_path(value):
    # SYM-009 recopiée mais DURCIE contre CWE-22. The payload is UNTRUSTED STDIN:
    # a `..` segment or an absolute path OUTSIDE the repo would otherwise make
    # semgrep open and read a file the CALLER chose, levels above root. So every
    # candidate is resolved against `root` and CONFINED — anything that is neither
    # `root` nor a descendant is REJECTED (returns ""), handled exactly like "no
    # path extracted": it lands in the unknown-path-key branch or the mute
    # fall-back. NB — SYM-009's OWN code (.codex/hooks/_common.py:114-130) does
    # NOT confine: on the relative_to ValueError it KEEPS the outside path. We do
    # not copy that behaviour, we reject. The shell belt after normalization
    # catches a regression here (defense in depth, the "deux ceintures").
    if not value:
        return ""
    text = str(value).replace("\\", "/")
    try:
        resolved  = os.path.realpath(os.path.join(root, text))
        root_real = os.path.realpath(root)
    except Exception:
        return ""
    if resolved != root_real and not resolved.startswith(root_real + os.sep):
        return ""                                           # outside root -> CWE-22, drop it
    text = os.path.relpath(resolved, root_real).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text

PATH_KEYS = ("file_path", "path", "target_file", "target", "filename", "filePath", "files")
# The `*** …File:` grammar is apply_patch's ALONE (SYM-048). Scanning it on the
# `command` of EVERY tool widened the smuggling surface past what this header
# describes; it is now BOUNDED to the tools that actually carry a patch. (The
# residual surface is capped anyway by normalize_path's confinement, but the
# bound keeps the code honest to its own description.)
PATCH_TOOLS = ("apply_patch",)
def paths_from(pl, name=""):
    args = tool_args(pl)
    vals, has_key = [], False
    for key in PATH_KEYS:                                  # SYM-011 keys (+ it.2 additions)
        if key in args:
            has_key = True
            v = args[key]
            vals.extend(v if isinstance(v, list) else [v])
    if name in PATCH_TOOLS:                                # BOUNDED: apply_patch only
        for patch in (args.get("command"), args.get("patch"), args.get("input"),
                      args.get("raw"), pl.get("_raw")):     # apply_patch regex (SYM-011)
            if isinstance(patch, str):
                for m in re.finditer(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.M):
                    has_key = True
                    vals.append(m.group(1).strip())
    if not vals:                                            # same keys FLAT, last resort
        for key in PATH_KEYS:
            if key in pl:
                has_key = True
                v = pl[key]
                vals.extend(v if isinstance(v, list) else [v])
    norm = [p for p in (normalize_path(v) for v in vals) if p]
    # TROISIÈME SIGNAL — « une valeur EXPLOITABLE était là, le confinement l'a
    # écartée ». Sans lui, l'appelant ne peut pas distinguer « aucune clé de
    # chemin connue » de « clé connue, chemin refusé parce qu'il sort de la
    # racine », et il annonçait donc les DEUX comme une borne de la liste des
    # clés. Ces deux cas n'ont pourtant rien à voir : le premier est un trou de
    # couverture RÉEL, le second est la garde CWE-22 qui fait exactement son
    # travail.
    #
    # UNE VALEUR VIDE N'EST PAS UN CONFINEMENT, et la nuance n'est pas théorique :
    # une clé présente portant `None` ou `""` produit un `vals` non vide dont
    # `normalize_path` ne tire rien, sans qu'aucun chemin ait jamais été refusé.
    # La compter comme un confinement ferait annoncer une garde qui n'a rien
    # gardé — la même faute de cause, déplacée d'un cran. On exige donc une
    # valeur qui soit une chaîne NON VIDE.
    exploitables = [v for v in vals if isinstance(v, str) and v.strip()]
    confine = bool(exploitables) and not norm
    # `has_key` ÉTAIT CALCULÉ ET JAMAIS CONSOMMÉ — un signal mort, et c'est
    # pourquoi la branche de refus ne pouvait pas choisir son message. Il est
    # désormais rendu ET lu.
    return norm, has_key, confine

name = tool_name(payload)
paths, has_key, confine = paths_from(payload, name)
step = ("stepIdx" in payload)                              # Antigravity's own key (GEMINI.md:21)

# COPILOT (alignment L-B): its write tool is `create` (MEASURED, canaries P1/P1v,
# 2026-10-12, Copilot CLI 1.0.95: toolName "create", toolArgs.path). `edit` is its
# documented edit tool and was NEVER SEEN by a canary — listed, NOT MEASURED.
# `bash` and `task` are the shell and sub-agent tools it names (S3): no path to scan.
SCAN   = ("Edit", "Write", "MultiEdit", "apply_patch", "create_file", "edit_file",
          "create", "edit")
IGNORE = ("Read", "Grep", "Glob", "Bash", "Task", "view", "read_file", "run_command",
          "bash", "task")

# COPILOT FIRES A STOP AT THE END OF EVERY SUB-AGENT, ON BOTH ITS LEGS — MEASURED
# (P4, 2026-10-13, Copilot CLI 1.0.95, macOS): the native `agentStop` (camelCase,
# marker `copilot`) AND the `Stop` of `.claude/settings.json` (snake_case, NO
# marker, so host == "claude" here). The sub-agent payload carries ITS OWN session
# id but the ROOT session transcript (`…/session-state/<root id>/events.jsonl`).
# The stop-<h16> marker is keyed on that id, so the sub-agent got ITS OWN refusal,
# once, whenever the dirty tree held a class-1 finding — read-only critics
# included, which cannot fix anything. It is now MUTE (no scan); the root, whose
# id EQUALS the transcript folder, is still judged on the SAME tree.
# BOUNDED DISCRIMINANT (the sub-agent test of `affirmation-guard.sh`, both
# graphies, PLUS the Copilot layout test of its registry-Claude leg): host
# `copilot` or marker absent; id and transcript non-empty strings OF THE SAME
# graphy; a Copilot transcript layout (consecutive pair `.copilot`,
# `session-state`, or the tail `session-state`, <UUID>, `events.jsonl` —
# `COPILOT_HOME` / `--config-dir` relocate the state); parent folder UUID-shaped
# and DIFFERENT from the id. Every other case keeps the previous behaviour.
# NOT MEASURED: Windows (`\` separator DEDUCED), another Copilot version, a
# relocated state (tail form DEDUCED), a resumed Copilot session
# (`--resume`/`--continue`). gitleaks (class 0) is NOT exempted.
_FORME_SESSION = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")

def sous_agent_copilot(pl):
    if host not in ("claude", "copilot"):
        return False
    for cle_sid, cle_tr in (("session_id", "transcript_path"), ("sessionId", "transcriptPath")):
        ident, transcript = pl.get(cle_sid), pl.get(cle_tr)
        if isinstance(ident, str) and ident and isinstance(transcript, str) and transcript:
            break
    else:
        return False
    morceaux = [m for m in transcript.replace("\\", "/").split("/") if m]
    disposition = (any(a == ".copilot" and b == "session-state"
                       for a, b in zip(morceaux, morceaux[1:]))
                   or (len(morceaux) >= 3 and morceaux[-3] == "session-state"
                       and morceaux[-1] == "events.jsonl"))
    if not disposition or len(morceaux) < 2 or not _FORME_SESSION.match(morceaux[-2]):
        return False
    return morceaux[-2] != ident

# (i) STOP: dirty tree, loop-guarded (stop_hook_active + stop-<h16>). transcript
#     -only Stop payloads land HERE via the flag, never in the inert branch.
if event == "stop":
    if payload.get("stop_hook_active"):
        directive("MUTE"); sys.exit(0)
    if sous_agent_copilot(payload):          # Copilot sub-agent: the root judges
        directive("MUTE"); sys.exit(0)
    if h16 and os.path.exists(os.path.join(markdir, "stop-" + h16)):
        directive("MUTE"); sys.exit(0)
    directive("SCANSTOP", h16); sys.exit(0)

# (ii) POST: filter by tool NAME first.
if name in IGNORE:
    directive("MUTE"); sys.exit(0)
if name in SCAN:
    if paths:
        with open(cands_f, "w", encoding="utf-8") as fh:
            fh.write("\n".join(paths) + "\n")
        directive("SCANPOST"); sys.exit(0)
    # (d) SCAN tool, aucun chemin SCANNABLE — MAIS DEUX CAUSES, ET UNE SEULE EST
    #     UN TROU DE COUVERTURE. La rédaction précédente les confondait et
    #     accusait toujours la liste des clés : mesuré le 2026-09-10 puis revu le
    #     2026-09-12, TOUTE écriture hors dépôt — chaque fichier de scratchpad —
    #     imprimait « clé de chemin inconnue » alors que la clé AVAIT été
    #     trouvée et que `normalize_path` avait simplement CONFINÉ le chemin.
    #
    #     Un canal de dégradation qui crie à la mauvaise cause finit ignoré, et
    #     ce jour-là il ne dira plus rien de la vraie. C'est L-00000136 : un
    #     mécanisme dont le canal de retour est jeté n'existe pas.
    if confine:
        # LA GARDE A FAIT SON TRAVAIL, CE N'EST PAS UNE DÉGRADATION. Le périmètre
        # de ce scanner est le DÉPÔT ; une écriture au-dessus de la racine en est
        # dehors par construction. On le DIT quand même — une fois par session et
        # par outil, comme les autres bornes — parce qu'un refus de traversée
        # silencieux serait invisible le jour où il compte.
        emit_degraded("SAST hook — chemin CONFINÉ hors racine pour l'outil '%s' : "
                      "non scanné, et c'est la garde CWE-22 qui le refuse, pas une "
                      "borne de couverture. Le verdict du dépôt est INCHANGÉ." % name,
                      marker=("confine-%s-%s" % (h16, safe(name))) if h16 else None)
        sys.exit(0)
    #     Ici seulement la liste des clés peut être en cause. On DIT laquelle des
    #     deux situations on a — clé absente, ou clé présente mais sans valeur
    #     exploitable — plutôt que d'accuser la liste dans les deux cas.
    cause = ("la liste des clés est une BORNE" if not has_key
             else "la clé est connue mais ne porte aucune valeur exploitable")
    emit_degraded("COVERAGE DEGRADED: SAST hook — clé de chemin inconnue pour "
                  "l'outil '%s' (%s)" % (name, cause),
                  marker=("unknownkey-%s-%s" % (h16, safe(name))) if h16 else None)
    sys.exit(0)
# name in NEITHER list:
if paths:
    # (C21) unknown tool carrying a path — named, once per session per name.
    emit_degraded("COVERAGE DEGRADED: SAST hook — outil inconnu '%s' portant un "
                  "chemin, non scanné (la liste des outils est une BORNE)" % name,
                  marker=("unknown-%s-%s" % (h16, safe(name))) if h16 else None)
    sys.exit(0)
if step:
    # (iv) inert: no path key AND stepIdx — once per session, systemMessage, exit 0.
    emit_degraded("COVERAGE DEGRADED: SAST hook inerte sur cet hôte (payload sans "
                  "chemin)", marker=("inert-" + h16) if h16 else None)
    sys.exit(0)
# (v) nothing to do.
directive("MUTE"); sys.exit(0)
HKAEOF

  action="$(sed -n '1p' "$DIRECTIVE" 2>/dev/null)"
  HK_H16="$(sed -n '2p' "$DIRECTIVE" 2>/dev/null)"
  HK_RESOLVED_EVT="$(sed -n '3p' "$DIRECTIVE" 2>/dev/null)"   # event RÉSOLU en phase A

  if [ "$action" = "MUTE" ]; then
    rm -f "$PFILE" "$DIRECTIVE" "$CANDS"; exit 0
  fi
  if [ "$action" = "DEGRADED" ]; then
    AUDIT_MODE="hook" AUDIT_EVENT="${HK_RESOLVED_EVT:-post}" audit "DEGRADED" 0 "[]"
    AUDIT_MODE="hook" AUDIT_EVENT="${HK_RESOLVED_EVT:-post}" emit_scan degraded 0 "[]"
    rm -f "$PFILE" "$DIRECTIVE" "$CANDS"; exit 0
  fi

  # ---- build FILES = candidates ∩ classer_chemin ∩ COVERED_EXTS -------------
  # T-01M4X9PP7FED0570PMPSYGA0V8: the extension is read FIRST, from the path
  # string, so a LISTED path counts as a loss (unreachable, unreadable) only when
  # its extension is covered or absent — an uncovered one stays mute as before.
  # A no-extension path is never scanned, but its loss is counted. The extension
  # is read on the BASENAME (closing review T2): on the whole path, `.cfg/run`
  # read as the extension `cfg/run`, uncovered, and its loss went mute.
  covered_extensions          # sets COVERED_EXTS (may be empty -> nothing scannable)
  FILES=()
  # A scan in the private directory (OUT_LIEN, above): said once the scan is
  # decided — a MUTE call stays mute; the clean-verdict cache is not read.
  if [ -n "$OUT_LIEN" ]; then
    # The event goes out only through AGENTS_EVENTS_DIR outside the repository
    # (emit_scan, evenements_ailleurs): said as it is.
    _ev="scan event not emitted"
    if evenements_ailleurs; then
      _ev="scan event emitted to AGENTS_EVENTS_DIR (outside the repository)"
    fi
    perte_perimetre "?" "audit line, markers and clean-verdict cache not kept (report directory is a symbolic link; private directory used); $_ev"
  fi
  OUT_REL="${OUT_DEPOT#"$ROOT/"}"
  HK_EVT="stop"
  SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
  if [ "$action" = "SCANPOST" ]; then
    HK_EVT="post"
    while IFS= read -r cand; do
      [ -n "$cand" ] || continue
      # 2nd ceinture (CWE-22): even if normalize_path regressed, a candidate from
      # the UNTRUSTED payload must stay root-relative — reject a `..` segment or
      # an absolute path so a lone regression cannot reopen the traversal hole.
      case "/$cand/" in
        */../*) continue ;;
      esac
      case "$cand" in
        /*) continue ;;
      esac
      _b="${cand##*/}"; e="${_b##*.}"
      hit=2                                   # 2 = no extension: loss counted, never scanned
      if [ "$e" != "$_b" ]; then
        hit=0
        while IFS= read -r ce; do [ "$e" = "$ce" ] && { hit=1; break; }; done <<< "$COVERED_EXTS"
      fi
      [ "$hit" -eq 0 ] && continue
      classer_chemin "$cand" || continue
      [ "$hit" -eq 1 ] && FILES+=("$cand")
    done < "$CANDS"
  else   # SCANSTOP — the DIRTY TREE only (changed + untracked vs HEAD, or vs the
         # empty tree when there is no commit yet); census and ls-files stderr
         # relevés exactly as in the gate. The SAME cut channels as the gate
         # (T-01M4Z24V0J813T40XRW3S4VW67: the Stop RAN the repository's
         # fsmonitor and clean filter, measured): filters decided here, in
         # this shell, before the producer; K2 added; sorted in bytes. On a
         # partial clone under a git that cannot refuse a lazy fetch, NO git
         # below reads a tree or an object (paresseux): the two before the
         # producer read a ref and hash an empty buffer — measured, neither
         # fetched — and every later one is skipped, its loss said.
    if git -C "$ROOT" "${GN[@]}" rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
      SG_BASE="HEAD"
    else
      SG_BASE="$(git -C "$ROOT" "${GN[@]}" hash-object -t tree /dev/null 2>/dev/null)"
    fi
    _ign_ill=0
    neutres_racine
    SG_LSERR="$(mktemp "${TMPDIR:-/tmp}/semgrep-lserr.XXXXXX" 2>/dev/null)" || SG_LSERR=""
    while IFS= read -r -d '' cand; do
      [ -n "$cand" ] || continue
      case "$cand" in
        "$OUT_REL"/*) continue ;;
      esac
      _b="${cand##*/}"; e="${_b##*.}"
      hit=2                                   # 2 = no extension: loss counted, never scanned
      if [ "$e" != "$_b" ]; then
        hit=0
        while IFS= read -r ce; do [ "$e" = "$ce" ] && { hit=1; break; }; done <<< "$COVERED_EXTS"
      fi
      [ "$hit" -eq 0 ] && continue
      classer_chemin "$cand" || continue
      [ "$hit" -eq 1 ] && FILES+=("$cand")
    done < <( {
        if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
          git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty "$SG_BASE" -- 2>/dev/null \
            || { if [ -n "$SG_SIG" ]; then printf 'census\n' >> "$SG_SIG"; fi; }
        fi
        # Not on a partial clone under an old git (B2): it would fetch a
        # skip-worktree `.gitignore` — the loss is said by relever_neutres.
        # K2 below skips itself there too (a sparse index would expand).
        if [ "$_PARESSEUX" != 1 ]; then
          if [ -n "$SG_LSERR" ]; then
            git -C "$ROOT" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>"$SG_LSERR"
          else
            git -C "$ROOT" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>/dev/null
          fi
        fi
        k2_lister || { if [ -n "$SG_SIG" ]; then printf 'k2-census\n' >> "$SG_SIG"; fi; }
      } | LC_ALL=C sort -zu )
    relever_lserr "$SG_LSERR"
    if [ -n "$SG_LSERR" ]; then rm -f "$SG_LSERR"; fi
    SG_LSERR=""
    relever_neutres
    # Closing line C1 of the plan: the skip-worktree `.gitignore` probe at the
    # Stop TOO, in this shell, its loss said BEFORE relever_signaux — measured:
    # under the no-lazy-fetch export ALONE the C18 fixture went from rc 2 (sink
    # found) to a MUTE rc 0.
    ignores_illisibles "$ROOT"
    relever_ignores   # (hook Stop) C1 — before relever_signaux, never the mute exit
    # K2 and the probe listed the index: complete only if no sparse-index entry
    # names an absent tree (MAJEUR) — said here, never the mute exit.
    dire_arbres "$ROOT"
    # The INDEX of the root (the Stop never reads a submodule: bound written in
    # README-SECURITY-SCAN-SETUP.md), its names filtered by COVERED_EXTS — an
    # extension-less name mute, as at the gate (S-01M5162VM18MKHE0E8GGT1ZNCK).
    # Not read on a partial clone under an old git (index_candidats: its
    # `diff-index` fetched HEAD's absent trees), the loss said.
    OBJ_FILTRE=1
    index_candidats C "$ROOT" ""
  fi
  relever_partition
  relever_signaux             # removes $SG_SIG in line, BEFORE the cache and any exit
  # Nothing covered to scan — no file AND no git object — AND nothing lost ->
  # mute exit 0. A loss is never muted: it goes to phase B as DEGRADED.
  if [ "${#FILES[@]}" -eq 0 ] && [ "${#OBJ_S[@]}" -eq 0 ] && [ "$PERTE_N" -eq 0 ]; then
    rm -f "$PFILE" "$DIRECTIVE" "$CANDS"; exit 0
  fi

  # ---- CACHE DU VERDICT PROPRE — STOP SEULEMENT (T-00000836) ----------------
  # Le Stop rescannait l'arbre sale À CHAQUE TOUR (~5 s mesurées le 2026-09-29),
  # même quand aucun octet n'avait bougé depuis le tour précédent. L'empreinte
  # couvre ce qui décide le verdict : le chemin et le hash des RÈGLES, puis le
  # chemin et le hash de CHAQUE fichier scanné. Identique à celle d'un verdict
  # CLEAN antérieur → même verdict, on ne relance pas. Seul un CLEAN s'inscrit ;
  # un finding ou une dégradation l'efface, donc on ne saute jamais un refus.
  # Règles hors fichier local (config registre `p/…`) : pas de cache, leur
  # contenu peut changer sans que rien ici ne le voie. L'empreinte est reprise
  # APRÈS le scan et le CLEAN ne s'inscrit que si elle n'a pas bougé : un
  # fichier réécrit PENDANT le scan (autre session, formateur) aurait sinon
  # associé le verdict d'un contenu à l'empreinte d'un autre — faux vert
  # reproduit en revue. BORNES NON TENUES, dites : un aller-retour A→B→A pendant
  # le scan passe encore (le fermer exigerait de scanner un instantané copié) ;
  # une montée de version de semgrep n'invalide pas l'empreinte.
  # A run that LOST paths never reads the cache (T-01M4X9PP7FED0570PMPSYGA0V8):
  # the fingerprint covers what was READ, never what was lost; SC_EMPREINTE stays
  # empty, so the write below cannot fire either, and the erase does.
  SC_EMPREINTE=""
  if [ "$HK_EVT" = "stop" ] && [ "$PERTE_N" -eq 0 ]; then
    case "$CFG" in
      /*|?:*) SC_CFG="$CFG" ;;
      *) SC_CFG="$ROOT/$CFG" ;;
    esac
    if [ -f "$SC_CFG" ]; then
      SC_EMPREINTE="$(sc_empreinte "$SC_CFG")" || SC_EMPREINTE=""
      if [ -n "$SC_EMPREINTE" ] && [ "$(cat "$MARKDIR/stop-propre" 2>/dev/null)" = "$SC_EMPREINTE" ]; then
        # Le saut se JOURNALISE (C25 : « pas de trace » ne doit jamais se lire
        # « la porte n'a pas tourné ») — un printf, le gain est conservé.
        AUDIT_MODE="hook-cache" AUDIT_EVENT="stop" audit "CLEAN" 0 "[]"
        # Canal A aussi (`skipped`, vocabulaire clos d'events.py) : la vue
        # Sécurité compare runs du journal et événements, ils restent alignés.
        AUDIT_MODE="hook-cache" AUDIT_EVENT="stop" emit_scan skipped 0 "[]"
        rm -f "$PFILE" "$DIRECTIVE" "$CANDS"; exit 0
      fi
    fi
  fi

  # ---- the git objects of the index, written AFTER the cache test -----------
  # (closing line C2 of the plan: the fingerprint needs only their sha, so a
  # cached CLEAN never pays the read.) The read is bounded by 8 s FIXED, never
  # SEMGREP_TIMEOUT: with the 45 s of semgrep below the Stop stays under the
  # host's 60 s, the census before it excepted (bound written in the README).
  # An overrun is a counted loss.
  lire_objets 8

  # ---- run semgrep (hook default timeout 45s < the 60s host budget) ---------
  REPORT="$(mktemp "${TMPDIR:-$OUT}/.semgrep-hk-rep.XXXXXX")"
  RESULT="$(mktemp "${TMPDIR:-$OUT}/.semgrep-hk-res.XXXXXX")"
  SEMGREP_ARGS=(--config "$CFG" --json --quiet --disable-version-check --metrics=off)
  if [ "${#FILES[@]}" -eq 0 ] && [ "${#OBJ_PATHS[@]}" -eq 0 ]; then
    # Reached only on a loss with nothing left to read: semgrep is NOT launched
    # (an empty `"${FILES[@]}"` aborts under bash 3.2 + set -u, and `semgrep --`
    # with no target reads the whole current directory), phase B reads an
    # empty, well-formed report and renders the DEGRADED form.
    printf '{"results":[],"errors":[]}\n' > "$REPORT"
    rc=0
  elif have timeout; then
    # semgrep itself runs `git ls-remote --get-url` in ROOT (closing review m2):
    # fsmonitor and hooks are cut for its git by GIT_CONFIG_COUNT, as for ours
    # (a caller's own GIT_CONFIG_COUNT is replaced for semgrep's process only).
    ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null timeout "${SEMGREP_TIMEOUT:-45}" semgrep "${SEMGREP_ARGS[@]}" -- ${FILES[@]+"${FILES[@]}"} ${OBJ_PATHS[@]+"${OBJ_PATHS[@]}"} ) > "$REPORT" 2>/dev/null
    rc=$?
  else
    ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null semgrep "${SEMGREP_ARGS[@]}" -- ${FILES[@]+"${FILES[@]}"} ${OBJ_PATHS[@]+"${OBJ_PATHS[@]}"} ) > "$REPORT" 2>/dev/null
    rc=$?
  fi
  # The machine paths of the objects become `index:<rel>` before PHASE B reads
  # the report: a finding of the index then takes the shape of a finding of the
  # tree (claude Stop: exit 2) — a NEW source of exit 2, the one this task wants.
  reecrire_rapport "$REPORT"

  # ---- PHASE B: emit findings / clean / degraded ----------------------------
  HK_REPORT="$REPORT" HK_RC="$rc" HK_EVENT="$HK_EVT" HK_HOST="$HOST" \
  HK_H16="$HK_H16" HK_MARKDIR="$MARKDIR" HK_RESULT="$RESULT" \
  HK_PERTE="$PERTE_N" HK_PERTE_MSG="$PERTE_MSG" \
  "$PY" - <<'HKBEOF'
import os, sys, json, hashlib

event   = os.environ["HK_EVENT"]
host    = os.environ["HK_HOST"]
h16     = os.environ.get("HK_H16", "")
markdir = os.environ["HK_MARKDIR"]
report  = os.environ["HK_REPORT"]
rc      = int(os.environ.get("HK_RC", "0"))
result_f= os.environ["HK_RESULT"]
ENVELOPE = ("codex", "copilot", "gemini")
# T-01M4X9PP7FED0570PMPSYGA0V8 — the perimeter losses counted by the shell
# (perte_perimetre already wrote each one on stderr). Unparseable => a loss.
try:
    perte_n = int(os.environ.get("HK_PERTE", "0") or "0")
except ValueError:
    perte_n = 1
perte_msg = os.environ.get("HK_PERTE_MSG", "")

def event_form(msg):
    # C1: KEPT — the FINDING emission below still calls this (additionalContext
    # alone in post; the finding is addressed to the model that fixes, its pilot
    # surface is the Stop systemMessage + the claude exit 2). Do NOT fold it into
    # degraded_form: swapping it there would NameError at the finding site and
    # turn every finding into a silent exit 0.
    # COPILOT (alignment L-B): the NESTED hookSpecificOutput is IGNORED by Copilot
    # (P1/P3, measured). STOP = `{"decision":"block","reason":…}`, the channel
    # MEASURED at P3 (honoured, `stop_hook_active` present, once per session by
    # the stop-<h16> marker). POST = `additionalContext` at the ROOT, the shape
    # typed by Copilot SDK 1.0.95 (PostToolUseHookOutput), measured reaching the
    # model with a real finding (2026-10-23, Copilot CLI 1.0.96).
    if event == "stop":
        if host == "copilot":
            return json.dumps({"decision": "block", "reason": msg})
        return json.dumps({"systemMessage": msg})
    obj = {"hookSpecificOutput":
           {"hookEventName": "PostToolUse", "additionalContext": msg}}
    if host == "copilot":
        obj["additionalContext"] = msg
    return json.dumps(obj)

def degraded_form(msg):
    # DEGRADED form only, PER EVENT: post = ONE object with BOTH keys, stop =
    # systemMessage alone. Sibling of event_form on purpose (C1). Same additive
    # copilot case as event_form (T-01M4RWC0DBM6XC1PDQGEG4P79C).
    if event == "stop":
        return json.dumps({"systemMessage": msg})
    body = {"systemMessage": msg,
            "hookSpecificOutput":
            {"hookEventName": "PostToolUse", "additionalContext": msg}}
    if host == "copilot":
        body["additionalContext"] = msg
    return json.dumps(body)

def result(word):
    open(result_f, "w", encoding="utf-8").write(word + "\n")

def degrade(msg):
    sys.stderr.write(msg + "\n")
    sys.stdout.write(degraded_form(msg) + "\n")   # C26: never stderr alone on exit 0
    result("DEGRADED 0 0")

if rc == 124:
    degrade("COVERAGE DEGRADED: SAST hook — semgrep timed out (%ss)"
            % os.environ.get("SEMGREP_TIMEOUT", "45")); sys.exit(0)
try:
    data = json.load(open(report, encoding="utf-8"))
except Exception:
    degrade("COVERAGE DEGRADED: SAST hook — semgrep report not readable JSON"); sys.exit(0)
if rc not in (0, 1):
    degrade("COVERAGE DEGRADED: SAST hook — semgrep error (%d)" % rc); sys.exit(0)

# THE SHAPE OF WHAT IS READ BELOW (T-01M52EC9PE7758B4ZG95YXMSJN). Measured: `{}`
# read CLEAN at the Stop AND filled the stop-propre cache (the next Stops skipped
# the scan); `[1]` or `{"results":[1]}` died here, stdout EMPTY on every host.
# The same test as the gate's `forme`, copied from scan_verdict.py
# `_forme_semgrep` (read, never imported), kept in parity with both by the
# suite's arm (prsp). Bound, said: `skipped_rules` and `paths.skipped` are not
# read here, so not checked. AFTER the rc test, so "semgrep error (N)" keeps its
# precedence. degrade() writes stderr, the form per host/event and DEGRADED, so
# the Stop cache below is ERASED, never filled.
def forme_hk(doc):
    if not isinstance(doc, dict):
        return False
    lst = doc.get("results")
    if not (isinstance(lst, list) and all(isinstance(x, dict) for x in lst)):
        return False
    errs = doc.get("errors")
    if errs is not None and not (isinstance(errs, list) and all(isinstance(x, dict) for x in errs)):
        return False
    pths = doc.get("paths")
    if pths is None:
        return True
    if not isinstance(pths, dict):
        return False
    scn = pths.get("scanned")
    return scn is None or (isinstance(scn, list) and all(isinstance(x, str) for x in scn))

if not forme_hk(data):
    degrade("COVERAGE DEGRADED: SAST hook — semgrep report malformed (no 'results' list of objects, or errors/paths mistyped)"); sys.exit(0)

results = data.get("results", []) or []
n = len(results)
if n == 0 and perte_n > 0:
    # NO FINDING ON AN INCOMPLETE PERIMETER IS NOT A CLEAN. DEGRADED at every
    # call (result + the stderr lines already written); the systemMessage once
    # per session AND per message at the Stop, by a `perte-<h16>-<sha1>` marker
    # (O_EXCL, same guard as stop-<h16>). In post h16 is empty (phase A writes
    # it only at the Stop), so no marker: the notice goes out at every call.
    msg = ("COVERAGE DEGRADED: SAST hook — perimeter INCOMPLETE (%s) — not "
           "scanned; no finding here is NOT a clean" % perte_msg)
    dire = True
    if event == "stop" and h16:
        nom = "perte-%s-%s" % (h16, hashlib.sha1(msg.encode("utf-8")).hexdigest()[:12])
        try:
            os.makedirs(markdir, exist_ok=True)
            fd = os.open(os.path.join(markdir, nom), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            dire = False
        except Exception:
            pass                                  # marker unwritable: say it again
    if dire:
        sys.stdout.write(degraded_form(msg) + "\n")
    result("DEGRADED 0 0"); sys.exit(0)
if n == 0:
    # 4e champ (T-00000836) : les erreurs TRANSITOIRES (Timeout & co.) d'un CLEAN.
    # Un « 0 résultat » sous timeout n'est pas un propre à figer : le cache du
    # Stop ne l'inscrit que si ce compte vaut 0. PartialParsing est déterministe
    # (mêmes octets, même parse), il ne compte pas.
    transitoires = sum(
        1 for e in (data.get("errors") or [])
        if not (isinstance(e, dict) and isinstance(e.get("type"), list)
                and e["type"][:1] == ["PartialParsing"])
    )
    result("CLEAN 0 0 %d" % transitoires); sys.exit(0)

# stderr: the 10 first locations `rule-id file:line`, deterministic order, then
# "(+N non listés)" — the same top-10 bound the gate applies to LOCJSON (C11).
locs = []
for r in results:
    rule = str(r.get("check_id", "?"))
    path = str(r.get("path", "?"))
    line = r.get("start", {}).get("line", "?")
    locs.append("%s %s:%s" % (rule, path, line))
for l in locs[:10]:
    sys.stderr.write(l + "\n")
if n > 10:
    sys.stderr.write("(+%d non listés)\n" % (n - 10))
sys.stderr.write("SAST (class-1 input, semgrep): %d finding(s) — route to "
                 "security-code-review triage\n" % n)

msg = "SAST (class-1): %d finding(s) — %s%s" % (
    n, locs[0], (" (+%d more)" % (n - 1) if n > 1 else ""))
if event == "stop" and h16:               # one block per session (stop-<h16>)
    try:
        os.makedirs(markdir, exist_ok=True)
        fd = os.open(os.path.join(markdir, "stop-" + h16), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except Exception:
        pass
# CHANNEL by host/event (arbitrage 2, C20): claude POST is stderr-only — on an
# exit-2 PostToolUse the host re-feeds stderr and JETTE stdout, so an envelope
# there would reach no one. Every OTHER cell renders the event form on stdout:
# claude STOP as a systemMessage (h6b), envelope hosts (exit 0), and an UNKNOWN
# marker (exit 2, two channels — but NEVER a permissionDecision, a PreToolUse
# shape). Findings on stderr always, for every host.
if not (host == "claude" and event == "post"):
    sys.stdout.write(event_form(msg) + "\n")
result("FINDINGS %d %d" % (n, 0 if host in ENVELOPE else 2))
sys.exit(0)
HKBEOF

  rverdict="$(sed -n '1p' "$RESULT" 2>/dev/null | cut -d' ' -f1)"
  rcount="$(sed -n '1p' "$RESULT" 2>/dev/null | cut -d' ' -f2)"
  rec="$(sed -n '1p' "$RESULT" 2>/dev/null | cut -d' ' -f3)"
  rtrans="$(sed -n '1p' "$RESULT" 2>/dev/null | cut -d' ' -f4)"
  # ---- THE BELT: PHASE B DIED BEFORE ANY VERDICT (T-01M52EC9PE7758B4ZG95YXMSJN)
  # $RESULT is created EMPTY by its mktemp above, and PHASE B writes its first
  # word on every path it reaches (CLEAN, FINDINGS, DEGRADED): an EMPTY first
  # word means the interpreter died first (a traceback, a killed process —
  # measured with `[1]`: stdout EMPTY on every host, the audit DEGRADED alone).
  # C26, as degrade(): a degraded exit 0 is never stderr alone — the message on
  # stderr AND the DEGRADED form per host/event on stdout, printed by the SHELL
  # (the dead interpreter cannot), the printf COPIED IN LINE from the refusal
  # of a linked report directory at the top of run_hook_mode, never factored.
  # Fires ONLY on an empty word, so a living PHASE B keeps its ONE stdout line.
  # Bound, said: a result() that fails AFTER a stdout line was written gives
  # TWO stdout lines (that line, then this one) — at THREE sites of PHASE B:
  # degrade() (its DEGRADED form), the perimeter-loss notice (n == 0 and
  # perte_n > 0, degraded_form) and the finding (event_form, every cell but
  # claude post).
  if [ -z "$rverdict" ]; then
    echo "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing" >&2
    if [ "$HK_EVT" = "stop" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing."}\n'
    elif [ "$HOST" = "copilot" ]; then
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing."}, "additionalContext": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing."}\n'
    else
      printf '{"systemMessage": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COVERAGE DEGRADED: SAST hook — the report phase died before any verdict; nothing reported, a 0 here proves nothing."}}\n'
    fi
  fi
  case "$rverdict" in
    FINDINGS)
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" audit "FINDINGS" "${rcount:-0}" "[]"
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" emit_scan scanned "${rcount:-0}" "[]" ;;
    CLEAN)
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" audit "CLEAN" 0 "[]"
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" emit_scan scanned 0 "[]" ;;
    *)
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" audit "DEGRADED" 0 "[]"
      AUDIT_MODE="hook" AUDIT_EVENT="$HK_EVT" emit_scan degraded 0 "[]" ;;
  esac
  # Le cache du Stop (plus haut) n'inscrit QUE un CLEAN, et tout autre verdict
  # l'efface : un refus ou une panne ne se saute jamais au tour suivant.
  # Borne dite (T-01M52EC9PE7758B4ZG95YXMSJN) : un stop-propre écrit AVANT ce
  # correctif sur un rapport malformé (`{}` lu CLEAN) reste servi tant que son
  # empreinte tient — elle porte la config et les octets du périmètre, PAS ceux
  # de ce script ; le premier Stop qui rescanne (un fichier ou la config change)
  # l'efface ou le réécrit sur un vrai CLEAN.
  if [ "$HK_EVT" = "stop" ]; then
    if [ "$rverdict" = "CLEAN" ] && [ -n "$SC_EMPREINTE" ] && [ "${rtrans:-0}" = "0" ] \
       && [ "$(sc_empreinte "$SC_CFG")" = "$SC_EMPREINTE" ]; then
      # `rm -f` FIRST (closing review M2): a link put there after the test of
      # the top is removed, never followed — the printf then makes a new file.
      mkdir -p "$MARKDIR" 2>/dev/null && { rm -f "$MARKDIR/stop-propre" 2>/dev/null; printf '%s\n' "$SC_EMPREINTE" > "$MARKDIR/stop-propre" 2>/dev/null; }
    else
      rm -f "$MARKDIR/stop-propre" 2>/dev/null
    fi
  fi
  rm -f "$PFILE" "$DIRECTIVE" "$CANDS" "$REPORT" "$RESULT"
  if [ -n "$OBJ" ]; then rm -rf "$OBJ"; OBJ=""; fi
  exit "${rec:-0}"
}

if [ "$HOOK" -eq 1 ]; then
  run_hook_mode
  exit 0            # unreachable: run_hook_mode always exits
fi

# ---- the COMMON VERDICT (cadre.scan-verdict/1, T-01M4W80Q5C3F6G99G0JXJB3RH4) -
# Outside the hook, this run's verdict is written to $SV_VERDICT by
# scan_verdict.py, at ONE point: right after semgrep returns (below). The
# previous run's verdict is removed HERE, before any exit, so every exit before
# the scan (semgrep absent, unresolvable --at, empty perimeter, refusal to
# conclude, --attest) leaves NO verdict rather than a stale one. The hook mode
# above returns first: it neither writes nor removes it. The usage refusals of
# the option parser exit 2 before this line and leave the old file: their rc 2
# says so. $SV is resolved from THIS script's directory, absolute, because the
# call runs after `cd "$ROOT"` and the script may be launched from anywhere.
SV="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/scan_verdict.py"
# $OUT, a parent of it under ROOT, or a fixed name written in place is a
# symbolic link (OUT_LIEN, tested at the top before the only mkdir): the gate
# goes on in a PRIVATE directory (out_prive), ABOVE the removal of the previous
# verdict — that `rm` would delete a file where the link points. The scan is
# NOT blind (closing review M1: a single committed link turned the gate off,
# rc 0 over a committed sink): the loss is said — the audit line and the common
# verdict are written in the private directory, removed by the EXIT trap — and
# the perimeter is read; the scan event is not emitted (emit_scan: under a link
# at `.agents/state` it would land where the link points, said in the loss line)
# — unless AGENTS_EVENTS_DIR sends it outside the repository, said too.
# Only when that directory cannot be made does the gate
# refuse, before any write: rc 0, no audit line, no event, nothing read.
# (exec-critic of 7c78f87f, security advisory) Under a link at a FIXED name only
# — `audit-log.jsonl`, `semgrep-hook`, `stop-propre`: OUT_LIEN is the FIRST link
# of the top-level list, so the four directories of $OUT_DEPOT are real — the
# repository's own previous `semgrep-verdict.json` is removed too, unless it is
# itself a link: the `rm` below only reaches the private directory, and a stale
# verdict would outlive a run whose own was never kept (the rule above: no
# verdict rather than a stale one; the refusal branch included). Behind a
# linked DIRECTORY it is never touched: that `rm` would delete a file where the
# link points.
if [ -n "$OUT_LIEN" ]; then
  case "$OUT_LIEN" in
    .agents/state/local/sca-reports/audit-log.jsonl|.agents/state/local/semgrep-hook|.agents/state/local/semgrep-hook/stop-propre)
      if [ ! -L "$OUT_DEPOT/semgrep-verdict.json" ]; then
        rm -f "$OUT_DEPOT/semgrep-verdict.json"
      fi ;;
  esac
  out_prive
  if [ -z "$OUT" ]; then
    perte_perimetre "?" "path(s) of the perimeter (the report directory .agents/state/local/sca-reports, a parent of it or a fixed name in it is a symbolic link and no private directory could be made: refused before the census, nothing read, nothing written)"
    exit 0
  fi
  # The event goes out only through AGENTS_EVENTS_DIR outside the repository
  # (emit_scan, evenements_ailleurs): said as it is.
  _ev="scan event not emitted"
  if evenements_ailleurs; then
    _ev="scan event emitted to AGENTS_EVENTS_DIR (outside the repository)"
  fi
  perte_perimetre "?" "audit line and common verdict not kept (report directory is a symbolic link; private directory used); $_ev"
fi
SV_VERDICT="$OUT/semgrep-verdict.json"
rm -f "$SV_VERDICT"

# ---- ONE cleanup(), ONE EXIT trap, installed BEFORE the census --------------
# (T-01M4XY8NC97JBSQP6C28AFD7QP, closing line C5 of its plan.) The census now
# creates work files (_TMP_FN, the filter drivers; _TMP_SW, the skip-worktree
# probe; SG_SIG, the producers' signals; SG_LSERR, the stderr of ls-files) under
# TMPDIR and the scan writes git objects ($OBJ) under $OUT: a signal before
# their in-line removal must not leave them there, so the trap sits HERE, before
# the first of them — the form of gitleaks-scan.sh (trap before the census). The
# early exits below (`--at` unresolvable, base unresolvable, merge refusal) now
# fire it too and remove whatever already exists (a SG_SIG made before the
# refusal included), as hk_nettoyer does for the hook.
REPORT=""; LOCFILE=""; UNPARSED=""; VERDICT_CANDS=""
_TMP_FN=""; _TMP_SW=""; OBJ=""
cleanup() {
  # Only the shell that INSTALLED this trap may run it: a background child that
  # inherits the EXIT trap and is killed before it finishes exec'ing fires the
  # trap too, and would delete this run's report while it is still scanning.
  # $$ cannot tell parent from child; $BASHPID can. Same guard as verify.sh's
  # lock_release (LOCK_HOLDER); degrades to inert on a bash 3.x without BASHPID.
  [ "${BASHPID:-$$}" = "$CLEANUP_OWNER" ] || return 0
  [ -n "$REPORT" ]  && rm -f "$REPORT"
  [ -n "$LOCFILE" ] && rm -f "$LOCFILE"
  # T-00000370 — folded in HERE, not a second `trap … EXIT`: a second trap
  # REPLACES the first, it does not chain. Same `-n` guard as its siblings,
  # because an early exit (semgrep absent, empty perimeter) fires this trap
  # BEFORE $UNPARSED is assigned, and `set -u` would abort the cleanup.
  [ -n "$UNPARSED" ] && rm -f "$UNPARSED"
  # The candidate list of the common verdict (below, after the scan) is removed
  # right after its call; this line covers an interruption DURING that call.
  # `:-` because arm (e) of the suite evals this body under `set -u` with only
  # REPORT, LOCFILE and UNPARSED set — and so are the six lines below.
  [ -n "${VERDICT_CANDS:-}" ] && rm -f "$VERDICT_CANDS"
  # A writer of the git objects still running (a signal to this shell alone) is
  # killed and reaped BEFORE $OBJ is removed (garde_enfant).
  [ -n "${_LECTEUR:-}" ] && { kill "$_LECTEUR" 2>/dev/null; wait "$_LECTEUR" 2>/dev/null; }
  [ -n "${OBJ:-}" ] && rm -rf "$OBJ"
  [ -n "${_TMP_FN:-}" ] && rm -f "$_TMP_FN"
  [ -n "${_TMP_SW:-}" ] && rm -f "$_TMP_SW"
  # The signal file and the ls-files stderr, as hk_nettoyer: relever_signaux and
  # relever_lserr remove them in line; these two lines cover a signal or an exit
  # BEFORE that.
  [ -n "${SG_SIG:-}" ] && rm -f "$SG_SIG"
  [ -n "${SG_LSERR:-}" ] && rm -f "$SG_LSERR"
  # The private directory of a run whose $OUT is reached through a link
  # (out_prive) — never the link path itself.
  [ -n "${OUT_PRIVE:-}" ] && rm -rf "$OUT_PRIVE"
  return 0
}
CLEANUP_OWNER="${BASHPID:-$$}"
trap cleanup EXIT

# ---- A PARTIAL CLONE UNDER A GIT THAT CANNOT REFUSE A LAZY FETCH -------------
# (closing review B2.) Measured with a git that ignores the no-lazy-fetch
# variable (no `--no-lazy-fetch`, as git < 2.45): `ls-files --others` FETCHES a
# skip-worktree `.gitignore` without its blob, the commit and range diffs and
# the merge base fetch what a treeless clone lacks — each fetch RUNS the
# remote's uploadpack. The gate does not enumerate such a root at all: a refusal
# to conclude, said, rc 0, before ANY git that reads its objects (paresseux
# reads the config, and probes `--no-lazy-fetch` once).
if paresseux "$ROOT"; then
  perte_perimetre "?" "perimeter not enumerated (partial clone, git < 2.45: a missing object would be fetched, running the remote's uploadpack)"
  couverture_at_least "refus de conclure"
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

# ---- build the list of files to scan ----------------------------------------
# Default: the working-tree diff (changed + untracked vs HEAD).
# --at <ref>: the files that commit changed.
PROPOSED=()          # every path the target enumerated, BEFORE the `[ -f ]` filter
SCAN_MODE="worktree"      # internal branch name
SCOPE_NOTE=""             # what the human-facing scope line must SAY        # what the scope line must say about how the base resolved
POINTE=""                 # the commit whose blobs the commit objects carry (HEAD or the --at ref)
if [ -n "$AT_REF" ]; then
  SCAN_MODE="at:$AT_REF"
  if ! git -C "$ROOT" "${GN[@]}" rev-parse --verify --quiet "$AT_REF^{commit}" >/dev/null 2>&1; then
    # A ref that does not resolve must NEVER fall through to an empty perimeter:
    # that would render a "nothing to scan" indistinguishable from a real clean.
    echo "COVERAGE DEGRADED: --at '$AT_REF' does not resolve to a commit — nothing was scanned" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  POINTE="$AT_REF"
  # The signal file is created AFTER this branch's early exit, so no exit can
  # leave it behind; relever_signaux (after the submodule block) removes it.
  SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
  while IFS= read -r -d '' rec && IFS= read -r -d '' f; do
    [ -n "$f" ] || continue
    range_lire "$rec" "$f"
    # A file the commit DELETED is absent from the tree and cannot be scanned:
    # classer_chemin drops it silently, exactly as the worktree branch does
    # (announced via the scope line, S<N). One that EXISTS behind an
    # unsearchable directory, or that cannot be read, is COUNTED instead.
    classer_chemin "$f" || continue
    FILES+=("$f")
  done < <( files_changed_by "$AT_REF" )
  relever_partition
  # The pointe's own blobs where the working tree does not hold them (step 3).
  objets_pointe "$POINTE"
  _on=""; [ "${#OBJ_L[@]}" -gt 0 ] && _on=" + ${#OBJ_L[@]} git object(s) (index/commit)"
  echo "semgrep-scan: perimeter = commit $AT_REF ($(git -C "$ROOT" "${GN[@]}" rev-parse --short "$AT_REF" 2>/dev/null)), ${#FILES[@]} scannable file(s)$_on — SLICE AUDIT, not the gate's default target" >&2
elif git -C "$ROOT" "${GN[@]}" rev-parse HEAD >/dev/null 2>&1; then
  # ---- DEFAULT MODE = THE TARGET (T-00000370) --------------------------------
  #   target = (commits since the base, when knowable) ∪ (HEAD, otherwise)
  #            ∪ (dirty tree)
  # There is no longer a remedy HOP: the default already covers what a follow-up
  # `--at HEAD` used to be needed for.
  BASE=""
  if BASE="$( resolve_base )"; then
    if ! git -C "$ROOT" "${GN[@]}" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null 2>&1; then
      # Class D — an unresolvable base is an unresolvable PERIMETER, never a
      # silent fall-back to a narrower one.
      echo "COVERAGE DEGRADED: base '$BASE' does not resolve to a commit — perimeter unresolvable, nothing was scanned" >&2
      audit "DEGRADED" 0 "[]"
      emit_scan degraded 0 "[]"
      exit 0
    fi
    # A BASE WITHOUT A MERGE BASE (T-01M4XY8PP8VYW0VVCYAAK0VARF, decision
    # S-01M4XWS5WEV0DDV98HP04H8K9M). Measured at c2a42ba2: `--since o` with `o`
    # an unrelated (orphan) history made `diff o...HEAD` fail rc 128 in silence
    # — `nothing to scan` + CLEAN on a clean tree, `clean on the diff` + a
    # rendered verdict on a dirty one, over a COMMITTED sink; `@{upstream}`=o
    # the same. The merge base is asked BEFORE the signal file exists: rc 1 on
    # a MERGE head is the refusal below (as with no base at all); rc 1
    # otherwise falls back to HEAD alone, SAID; rc >= 2 is a failed census.
    _mb=0
    git -C "$ROOT" "${GN[@]}" merge-base "$BASE" HEAD >/dev/null 2>&1 || _mb=$?
    if [ "$_mb" -eq 1 ] && head_is_merge; then
      couverture_at_least "refus de conclure"
      echo "COVERAGE DEGRADED: HEAD is a MERGE and the base '$BASE' shares no merge base with HEAD — refusing to conclude on a perimeter that would omit this task's own commits; pass --since <base>" >&2
      audit "DEGRADED" 0 "[]"
      emit_scan degraded 0 "[]"
      exit 0
    fi
    SCOPE_NOTE="cible=$BASE...HEAD + arbre sale"
    # Created AFTER this sub-branch's early exits (unresolvable base, merge
    # refusal) and BEFORE its commit census, so the census can signal; no exit
    # lies between it and relever_signaux (closing review T3).
    SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
    if [ "$_mb" -eq 0 ]; then
      while IFS= read -r -d '' rec && IFS= read -r -d '' f; do
        [ -n "$f" ] || continue
        range_lire "$rec" "$f"
      done < <( files_changed_since "$BASE" )
    elif [ "$_mb" -eq 1 ]; then
      perte_perimetre "?" "commit(s) since the base not enumerated (no merge base with HEAD; fell back to HEAD alone)"
      SCOPE_NOTE="cible=HEAD-seul (base sans base de fusion) + arbre sale"
      while IFS= read -r -d '' rec && IFS= read -r -d '' f; do
        [ -n "$f" ] || continue
        range_lire "$rec" "$f"
      done < <( files_changed_by HEAD )
    else
      if [ -n "$SG_SIG" ]; then printf 'since-census\n' >> "$SG_SIG"; fi
    fi
  else
    # INDETECTABLE (R-BASE line 3). A MERGE head with an unknown base is the one
    # case that refuses: `git diff HEAD~1 HEAD` on a merge lists only what the
    # other side brought, so THIS TASK'S OWN WORK would be absent from the
    # target — a false CLEAN on the exact files under review. Parent counting
    # needs no reference, which is why this disjunct is decidable here.
    if head_is_merge; then
      couverture_at_least "refus de conclure"
      echo "COVERAGE DEGRADED: HEAD is a MERGE and no base is knowable (no --since, no @{upstream}) — refusing to conclude on a perimeter that would omit this task's own commits; pass --since <base>" >&2
      audit "DEGRADED" 0 "[]"
      emit_scan degraded 0 "[]"
      exit 0
    fi
    SCOPE_NOTE="cible=HEAD-seul (fork indétectable — passez --since) + arbre sale"
    # Created AFTER the merge refusal and BEFORE the commit census (T3).
    SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
    while IFS= read -r -d '' rec && IFS= read -r -d '' f; do
      [ -n "$f" ] || continue
      range_lire "$rec" "$f"
    done < <( files_changed_by HEAD )
  fi
  SG_BASE="HEAD"
  POINTE="HEAD"
else
  # ---- NO COMMIT YET (T-01M4X9PP7FED0570PMPSYGA0V8, plan NOHEAD) -------------
  # This branch did not exist: a repo without a commit fell through to an empty
  # perimeter, `nothing to scan` and an audit CLEAN — over an INDEXED sink. The
  # dirty tree is now taken against the EMPTY tree (hashed, never written: no
  # `-w`), i.e. everything indexed or modified, plus the untracked files.
  # OUTSIDE any git repository this branch is taken too: its census then fails
  # (refus de conclure), and the scope line must say so rather than "no commit"
  # (closing review T4).
  if git -C "$ROOT" "${GN[@]}" rev-parse --git-dir >/dev/null 2>&1; then
    SCOPE_NOTE="arbre sale (aucun commit)"
  else
    SCOPE_NOTE="hors dépôt git"
  fi
  SG_SIG="$(mktemp "${TMPDIR:-/tmp}/semgrep-sig.XXXXXX" 2>/dev/null)" || SG_SIG=""
  SG_BASE="$(git -C "$ROOT" "${GN[@]}" hash-object -t tree /dev/null 2>/dev/null)"
fi
if [ "$SCAN_MODE" = "worktree" ]; then
  # ...∪ the dirty tree, in both cases. A failed `git diff` (rc 128 on an
  # unreadable submodule gitdir, plan R4) used to empty the WHOLE dirty tree
  # without a word; it now leaves `census` in $SG_SIG (this producer runs in
  # the subshell of `< <( … )`). The stderr of `ls-files --others` is captured
  # and counted by relever_lserr, never thrown away.
  #
  # THE DIFF RUNS NO CODE OF THE REPOSITORY (T-01M4Z24V0J813T40XRW3S4VW67): "${GN[@]}"
  # (fsmonitor, hooks), every filter driver emptied by filtres_neutres — decided
  # HERE, in this shell, before the producer; when that fails, or on a partial
  # clone under a git that cannot refuse a lazy fetch, the diff is NOT run and
  # the loss is said (relever_neutres) —, no external diff, no textconv, no
  # stat-only refresh (the price: a stat-dirty file listed and scanned, never a
  # file lost), and a submodule's working tree is not opened
  # (`--ignore-submodules=dirty`, never `=all`, which hid a gitlink turned into
  # a regular file — measured). `--` after the base. The sparse-index advice is
  # switched off on `ls-files --others` only: its lines would be counted as
  # unreadable directories. K2 — assume-unchanged entries (lowercase tag of
  # `ls-files -v`): `git diff` never compares their working-tree copy, so a sink
  # written there was never listed; they join the census (`k2-census` in
  # $SG_SIG when the listing fails).
  neutres_racine
  SG_LSERR="$(mktemp "${TMPDIR:-/tmp}/semgrep-lserr.XXXXXX" 2>/dev/null)" || SG_LSERR=""
  while IFS= read -r -d '' f; do
    [ -n "$f" ] || continue
    PROPOSED+=("$f")
  done < <( {
      if [ "$_PARESSEUX" != 1 ] && [ "$_neutres_ok" = 1 ]; then
        git -C "$ROOT" "${GN[@]}" -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty "$SG_BASE" -- 2>/dev/null \
          || { if [ -n "$SG_SIG" ]; then printf 'census\n' >> "$SG_SIG"; fi; }
      fi
      if [ -n "$SG_LSERR" ]; then
        git -C "$ROOT" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>"$SG_LSERR"
      else
        git -C "$ROOT" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>/dev/null
      fi
      k2_lister || { if [ -n "$SG_SIG" ]; then printf 'k2-census\n' >> "$SG_SIG"; fi; }
    } )
  relever_lserr "$SG_LSERR"
  if [ -n "$SG_LSERR" ]; then rm -f "$SG_LSERR"; fi
  relever_neutres
  # The skip-worktree `.gitignore` probe of the root (its count is said once,
  # after the submodule loop).
  ignores_illisibles "$ROOT"
  # The root's index listings (K2, the probe, the enumeration's gitlinks) are
  # complete only if no sparse-index entry names an absent tree (MAJEUR).
  dire_arbres "$ROOT"
  # dedup, NUL-safe, then apply the existence filter once.
  #
  # AND THE SCANNER NEVER SCANS ITS OWN OUTPUT. `$OUT` holds this run's report and
  # the audit log it appends to, so in a repo that does not gitignore it those
  # artifacts land in the NEXT run's perimeter — and in this one's, once a
  # previous run has written them. The perimeter then depends on how many times
  # the gate has already run, which is how the differential check caught it:
  # two consecutive runs of the same tree reported 8 and 7 scannable files. A
  # perimeter that is not stable across identical runs cannot support a verdict,
  # and worse, it makes the figure drift upward every time the gate is used.
  OUT_REL="${OUT_DEPOT#"$ROOT/"}"
  # Sorted in BYTES (T-01M4Z5T4YQND3S63PW8D4ERN25): a UTF-8 collation folds two
  # distinct names (`a.py` and `a<U+200B>.py`) into one under `sort -u` —
  # measured: under LC_ALL=fr_FR.UTF-8 the sink twin was never scanned.
  if [ "${#PROPOSED[@]}" -gt 0 ]; then
    while IFS= read -r -d '' f; do
      [ -n "$f" ] || continue
      case "$f" in
        "$OUT_REL"/*) continue ;;
      esac
      classer_chemin "$f" || continue
      FILES+=("$f")
    done < <( printf '%s\0' "${PROPOSED[@]}" | LC_ALL=C sort -zu )
  fi
  relever_partition
  # The pointe's blobs where the tree does not hold them (default mode: HEAD),
  # then the root INDEX (default and no-commit modes).
  if [ -n "$POINTE" ]; then objets_pointe "$POINTE"; fi
  index_candidats C "$ROOT" ""
  _on=""; [ "${#OBJ_L[@]}" -gt 0 ] && _on=" + ${#OBJ_L[@]} git object(s) (index/commit)"
  echo "semgrep-scan: perimeter = $SCOPE_NOTE, ${#FILES[@]} scannable file(s)$_on" >&2
fi
# T-00000293: extend the perimeter with the content of INITIALIZED submodules —
# same enumeration as gitleaks-scan.sh (DUPLICATED on purpose, no shared
# helper), each entry through classer_chemin rather than a bare `[ -f ]`
# (T-01M4X9PP7FED0570PMPSYGA0V8). tracked ∪ untracked = the whole
# non-ignored work tree of each submodule, as SUPERPROJECT-relative `S/f` paths;
# the two sets are disjoint, so no dedup. Zero submodule => FILES unchanged
# (octet-for-octet). NUL-safe throughout.
#
# WORKTREE MODE ONLY (T-00000364). `--at <ref>` asks "what did THAT COMMIT
# change?", and a submodule's whole checked-out tree is not part of the answer —
# appending it would silently widen an explicitly narrowed perimeter and make the
# scope figures meaningless. A submodule change recorded in that commit appears
# as a gitlink path, which `[ -f ]` drops, and the S<N scope line says so. The
# narrowing is stated here rather than left to be inferred from the `if`.
if [ "$SCAN_MODE" = "worktree" ]; then
# Same partition as the top level (classer_chemin), same stderr capture of
# `ls-files --others` — one file for every submodule, counted once after them.
SG_LSERR="$(mktemp "${TMPDIR:-/tmp}/semgrep-lserr.XXXXXX" 2>/dev/null)" || SG_LSERR=""
SG_SUBS=0
while IFS= read -r -d '' sub_rel; do
  SG_SUBS=$((SG_SUBS + 1))
  # A submodule that is itself a partial clone under a git that cannot refuse a
  # lazy fetch (B2): none of its files is enumerated — its `ls-files --others`
  # would fetch — the loss is said, the submodule skipped. The producer did not
  # list its index either (enumerate_submodules tests it BEFORE its recursion):
  # its nested submodules are part of the loss.
  if paresseux "$ROOT/$sub_rel"; then
    perte_perimetre "?" "submodule file(s) not enumerated (partial clone, git < 2.45: a missing object would be fetched; its index not listed, nested submodules included)"
    continue
  fi
  # Its index listings (tracked files, probe, nested gitlinks) are complete only
  # if no sparse-index entry names an absent tree (MAJEUR) — said, then listed.
  dire_arbres "$ROOT/$sub_rel"
  while IFS= read -r -d '' subf; do
    [ -n "$subf" ] || continue
    rel="$sub_rel/$subf"
    classer_chemin "$rel" || continue
    FILES+=("$rel")
  # A failed listing of the submodule's TRACKED files used to drop them without
  # a word (rc never read); it now leaves `submod-ls` in $SG_SIG, this producer
  # being the subshell of `< <( … )`.
  done < <( git -C "$ROOT/$sub_rel" "${GN[@]}" ls-files -z 2>/dev/null \
              || { if [ -n "$SG_SIG" ]; then printf 'submod-ls\n' >> "$SG_SIG"; fi; }
            if [ -n "$SG_LSERR" ]; then
              git -C "$ROOT/$sub_rel" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>>"$SG_LSERR"
            else
              git -C "$ROOT/$sub_rel" "${GN[@]}" -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z 2>/dev/null
            fi )
  # In THIS shell (the loop body is not the producer): the submodule's own
  # skip-worktree `.gitignore` probe, then its INDEX (T-01M4Z5T6N1DN43K5SEC2DNB63M
  # — measured at c2a42ba2: a sink `git add`ed in a submodule under a benign
  # tree read `clean on the diff.`).
  ignores_illisibles "$ROOT/$sub_rel"
  index_candidats C "$ROOT/$sub_rel" "$sub_rel/"
done < <(enumerate_submodules "$ROOT" "" 0)
relever_partition
if [ "$SG_SUBS" -gt 0 ]; then relever_lserr "$SG_LSERR"; fi
if [ -n "$SG_LSERR" ]; then rm -f "$SG_LSERR"; fi
# ONE loss line for every skip-worktree `.gitignore` counted, root and submodules.
relever_ignores
fi
# Every signal the producer subshells left (census, submodules) becomes a loss
# HERE, and the signal file is removed in line — before any exit below.
relever_signaux
# The PERIMETER is the files AND the labels of the git objects
# (T-01M4XY8NC97JBSQP6C28AFD7QP): the attestation's equality, the covered
# count, the empty-perimeter test, N and the verdict's candidates read CIBLES;
# with no object it IS FILES, byte for byte.
CIBLES=(${FILES[@]+"${FILES[@]}"} ${OBJ_L[@]+"${OBJ_L[@]}"})

# ---- EMPTY PERIMETER: a CLEAN here used to be the script's one false green ----
# (T-00000364.) This branch wrote `audit CLEAN` + `emit_scan skipped` + exit 0
# whenever the working tree was clean. But AGENTS.md's nominal pipeline runs the
# security gate AFTER the dev stage, and the dev stage COMMITS — so on the
# nominal path this branch is reached BY CONSTRUCTION, and it posted a CLEAN
# verdict to the audit log for a perimeter of zero files. That is the exact
# class of defect the invariant further down (T-00000262) forbids: "NO path
# writes CLEAN when the report itself is defective". A scope of zero is the most
# defective report there is.
#
# So the branch now ASKS A QUESTION before it answers: does HEAD's commit carry
# any file in a language this ruleset covers? If yes, the emptiness is BLINDNESS
# and is announced as DEGRADED with the runnable remedy named. If no, the repo
# genuinely has nothing for this scanner and the original CLEAN stands — a
# distinction the old code could not make because it never looked.
# ---- ATTESTATION MODE: the manual half is VERIFIED, not merely asserted ------
# For class A (scanner absent) and for "not measurable", a CLEAN rests on a human
# review. Nothing mechanical will ever stop a LYING attestation — that is the
# irreducible residue of any manual review, and §7 says so rather than pretending
# otherwise. What IS mechanisable is the SHAPE: an attestation is a list, one
# entry per file of the perimeter, and it is compared.
#
# THE OPERATOR IS EQUALITY, NEVER INCLUSION, and the difference is the whole
# point: `∅ ⊆ anything` is TRUE, so an inclusion test passes an EMPTY attestation
# — the "vacant justification" this gate forbids one storey down, readmitted by
# the very operator meant to prevent it. Three ways to fail, and each has an arm:
#   * an entry OUTSIDE the perimeter        -> attests something it cannot attest
#   * EMPTY while the perimeter is not      -> attests nothing at all
#   * PARTIAL (all in scope, count < N)     -> the case only equality catches
if [ "$ATTEST_SEEN" -eq 1 ]; then
  if [ ! -r "$ATTEST_FILE" ]; then
    echo "COVERAGE DEGRADED: attestation '$ATTEST_FILE' unreadable — nothing was verified" >&2
    audit "DEGRADED" 0 "[]"
    exit 0
  fi
  att_n=0; att_bad=""; att_seen=""
  while IFS= read -r line || [ -n "$line" ]; do
    entry="${line%%	*}"                      # everything before the first TAB
    [ -n "$entry" ] || continue
    case "$entry" in
      \#*) continue ;;
    esac # comments are not entries
    att_n=$((att_n + 1))
    found=0
    for f in ${CIBLES[@]+"${CIBLES[@]}"}; do
      [ "$f" = "$entry" ] && { found=1; break; }
    done
    [ "$found" -eq 1 ] && att_seen="$att_seen$entry
" || att_bad="$att_bad $entry"
  done < "$ATTEST_FILE"
  # Distinct entries counted in BYTES (T-01M4Z5T4YQND3S63PW8D4ERN25): a UTF-8
  # collation folds two distinct names into one and turns an equal attestation
  # into a false PARTIELLE.
  att_uniq="$(printf '%s' "$att_seen" | LC_ALL=C sort -u | grep -c . || true)"
  if [ -n "$att_bad" ]; then
    echo "COVERAGE DEGRADED: attestation ≢ retenues — elle porte $(echo $att_bad | wc -w) entrée(s) HORS PÉRIMÈTRE :$att_bad" >&2
    couverture_at_least "DEGRADED"
    audit "DEGRADED" 0 "[]"
    exit 0
  fi
  if [ "$att_n" -eq 0 ] && [ "${#CIBLES[@]}" -gt 0 ]; then
    echo "COVERAGE DEGRADED: attestation VIDE sur un périmètre de ${#CIBLES[@]} fichier(s) — malformée. Une attestation vide passe l'INCLUSION (∅ ⊆ tout) et n'atteste rien" >&2
    couverture_at_least "DEGRADED"
    audit "DEGRADED" 0 "[]"
    exit 0
  fi
  if [ "$att_uniq" -ne "${#CIBLES[@]}" ]; then
    echo "COVERAGE DEGRADED: attestation ≢ retenues — $att_uniq entrée(s) distincte(s) pour ${#CIBLES[@]} fichier(s) au périmètre. PARTIELLE : c'est le cas que seule l'ÉGALITÉ attrape, l'inclusion l'accepte" >&2
    couverture_at_least "DEGRADED"
    audit "DEGRADED" 0 "[]"
    exit 0
  fi
  couverture_at_least "portable par attestation"
  # The benign conclusion only when COUVERTURE says what it announces
  # (T-01M4X9PP7FED0570PMPSYGA0V8, C1): an attestation equal to a perimeter that
  # LOST paths attests the retained files, never the lost ones.
  if [ "$COUVERTURE" = "portable par attestation" ]; then
    echo "semgrep-scan: attestation ≡ retenues ($att_uniq/${#CIBLES[@]}) — couverture portable par attestation" >&2
  else
    echo "SAST (class-1 input, semgrep): aucun finding, mais couverture = $COUVERTURE — le vide N'EST PAS une preuve ici" >&2
    emit_scan degraded 0 "[]"
  fi
  audit "CLEAN" 0 "[]"
  exit 0
fi

# ---- SCANNER AVAILABILITY IS CHECKED *AFTER* THE ATTESTATION (T-00000370) --
# This block used to sit near the top, which put the ONE path that exists FOR
# a missing scanner behind a check for that scanner. Class A — semgrep absent —
# is precisely when a human review has to carry the verdict, so `--attest` was
# unreachable in the only situation it was written for. Found by the linux
# replay, where semgrep is not installed: the host leg passed because semgrep
# was present there, which is exactly the blind spot a second platform exists
# to cover.
# ---- semgrep availability: absent => COVERAGE DEGRADED, exit 0 (never a false CLEAN)
if ! have semgrep; then
  couverture_at_least "portable par attestation"   # class A: a human review can carry this one
  echo "COVERAGE DEGRADED: semgrep not installed — couverture portable par ATTESTATION énumérative (une entrée par fichier du périmètre)" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

# ---- COVERAGE IS ESTABLISHED ONCE, AND BEFORE THE SCAN (T-00000370) ---------
# A COVERAGE LIMIT IS NOT CONDITIONAL ON THE SCAN SUCCEEDING. This call used to
# live only inside the branches BELOW, i.e. after semgrep had run — so a ruleset
# declaring a language the mapping table does not know went UNANNOUNCED whenever
# semgrep itself then failed on that same ruleset. The run degraded on the scan
# error and never said the thing the operator most needed to hear: that the
# blindness check could not see part of the ruleset. Establishing coverage first
# also means class B (ruleset unusable) is known BEFORE a scan is launched with
# it. Called once; the figures are reused by every branch below.
count_covered < <( printf '%s\0' ${CIBLES[@]+"${CIBLES[@]}"} )   # NUL on stdin; redirect, never a pipe
PERIMETER_COVERED="${COVERED_COUNT:-0}"

if [ "${#CIBLES[@]}" -eq 0 ]; then
  # REFUSE TO CONCLUDE before drawing any conclusion. If the covered-language set
  # could not be established (ruleset absent/unreadable/language-less), then an
  # empty perimeter is UNINTERPRETABLE: it may be genuinely clean, or it may be
  # hiding committed code we have no way to recognise. Announcing DEGRADED is the
  # only honest answer; the helper has already said WHY on stderr.
  if [ "$COVERED_UNMEASURABLE" -eq 1 ]; then
    couverture_at_least "refus de conclure"   # the covered set is UNKNOWN, not merely partial
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  # THE OLD `BLIND_N` PROBE IS GONE, and its disappearance is the fix. It asked
  # "is the tree clean while HEAD hides covered code?" — a question that only
  # existed because the default perimeter was the working-tree diff. HEAD's files
  # are now IN the perimeter (R-BASE), so an empty perimeter here means the
  # TARGET is genuinely empty, and there is no narrower mode left to point at.
  # An EMPTY perimeter is "nothing to scan" only when nothing was lost on the
  # way (T-01M4X9PP7FED0570PMPSYGA0V8, C1): the loss lines above said what.
  if [ "$COUVERTURE" = "CLEAN" ]; then
    echo "semgrep-scan: nothing to scan (target empty: no commit since the base, clean working tree)."
    audit "CLEAN" 0 "[]"
    emit_scan skipped 0 "[]"
  else
    echo "SAST (class-1 input, semgrep): aucun finding, mais couverture = $COUVERTURE — le vide N'EST PAS une preuve ici" >&2
    audit "CLEAN" 0 "[]"
    emit_scan degraded 0 "[]"
  fi
  exit 0
fi

# ---- run semgrep on just those files, report to a mktemp file ---------------
# mktemp (not a $$ name) gives an unpredictable path + 0600 perms: no
# symlink/TOCTOU hijack of the report while it briefly sits on disk
# (CWE-59/377 — same lesson as gitleaks-scan.sh's shard). cleanup() and its
# EXIT trap are installed ABOVE, before the census.
AUDIT_UNPARSED_N=0
# The git objects are WRITTEN only now that semgrep will run (their labels have
# been part of the perimeter since the census), bounded by the scan's own
# deadline (SEMGREP_TIMEOUT, default 180 s).
_obj_tmo="${SEMGREP_TIMEOUT:-180}"
case "$_obj_tmo" in
  ''|*[!0-9]*)
    _obj_tmo=180 ;;
esac
lire_objets "$_obj_tmo"
REPORT="$(mktemp "${TMPDIR:-$OUT}/.semgrep-scan.XXXXXX")"

# `--` marks the end of options: FILES comes from git diff/ls-files and may
# contain a name starting with `-`/`--` (e.g. an untracked file literally
# named `--config=https://attacker.example/rules.yml`). Without `--`, click
# (semgrep's CLI parser) would read such a name as an OPTION — repeating
# --config lets the LAST one win, silently swapping the ruleset for an
# attacker-controlled/remote one (CWE-88: argument injection). `--` forces
# everything after it to be treated as a positional path, never an option.
# --disable-version-check skips a network ping to the semgrep registry and
# --metrics=off skips the anonymous-metrics upload; together they turn a cold
# first invocation from ~100s (measured 103s on this repo) into ~7s, with no
# change to findings. Both are pure network suppressors — offline-safe.
SEMGREP_ARGS=(--config "$CFG" --json --quiet --disable-version-check --metrics=off)

# Wrap the scan in `timeout` WHEN it resolves on this host, so a hung or very
# slow scan SAYS so (rc=124 below) instead of blocking the review gate forever.
# `timeout` is never a prerequisite: absent, the scan runs bare and the rc=124
# branch is unreachable (a "timed out" message there would be a lie — C5).
TIMED=0
if [ "${#FILES[@]}" -eq 0 ] && [ "${#OBJ_PATHS[@]}" -eq 0 ]; then
  # Reached only when every target was a git object and NONE could be written
  # (a counted loss already): semgrep is NOT launched — `semgrep … --` with no
  # target reads the CURRENT DIRECTORY (measured: fx/d1 => scanned ['k.py']),
  # i.e. the whole of $ROOT. An empty, well-formed report, the DEGRADED form,
  # as in the hook.
  printf '{"results":[],"errors":[]}\n' > "$REPORT"
  rc=$?
elif have timeout; then
  TIMED=1
  # semgrep runs `git ls-remote --get-url` in ROOT (m2): fsmonitor and hooks cut
  # for its git too, by GIT_CONFIG_COUNT (as at the hook Stop).
  ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null timeout "${SEMGREP_TIMEOUT:-180}" semgrep "${SEMGREP_ARGS[@]}" -- ${FILES[@]+"${FILES[@]}"} ${OBJ_PATHS[@]+"${OBJ_PATHS[@]}"} ) > "$REPORT" 2>/dev/null
  rc=$?
else
  ( cd "$ROOT" && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=core.hooksPath GIT_CONFIG_VALUE_1=/dev/null semgrep "${SEMGREP_ARGS[@]}" -- ${FILES[@]+"${FILES[@]}"} ${OBJ_PATHS[@]+"${OBJ_PATHS[@]}"} ) > "$REPORT" 2>/dev/null
  rc=$?
fi
# The machine paths of the objects become their labels BEFORE any reader.
reecrire_rapport "$REPORT"

# ---- the common verdict is produced HERE, once, before any branch reads $rc -
# From semgrep's raw report, its real rc and the perimeter ($FILES, one path a
# line). semgrep runs WITHOUT --error, hence `--findings-exit-code none`. The
# status of the call lives in sv_rc and NEVER in rc: the branches below (124,
# rc != 0) and this script's own rc, audit() and emit_scan are UNCHANGED by
# this producer. Its output goes to /dev/null: the console reads ONE fixed line
# when the verdict is not rendered — no path, no timestamp, nothing that could
# read as a scan verdict. The verdict may be stricter than this script's rc
# (it reads the raw report only); the rc remains the gate.
sv_rc="absent"
[ -z "$PY" ] && sv_rc="python-absent"
if [ -n "$PY" ] && [ -f "$SV" ]; then
  VERDICT_CANDS="$(mktemp "${TMPDIR:-$OUT}/.semgrep-cands.XXXXXX" 2>/dev/null)" || VERDICT_CANDS=""
  [ -n "$VERDICT_CANDS" ] && printf '%s\n' ${CIBLES[@]+"${CIBLES[@]}"} > "$VERDICT_CANDS"
  # --candidates only when its list exists: an empty value is a directory to argparse (critic-opus T4).
  SVA=(semgrep --report "$REPORT" --findings-exit-code none --exit-code "$rc" --config "$CFG" --out "$SV_VERDICT")
  [ -n "$VERDICT_CANDS" ] && SVA+=(--candidates "$VERDICT_CANDS")
  ( cd "$ROOT" && "$PY" "$SV" "${SVA[@]}" ) >/dev/null 2>&1
  sv_rc=$?
  [ -n "$VERDICT_CANDS" ] && rm -f "$VERDICT_CANDS"
  VERDICT_CANDS=""
fi
if [ "$sv_rc" = "python-absent" ]; then
  echo "semgrep-scan: verdict commun non rendu (python absent)" >&2
elif [ "$sv_rc" = "absent" ]; then
  echo "semgrep-scan: verdict commun non rendu (scan_verdict absent)" >&2
elif [ "$sv_rc" -ne 0 ]; then
  echo "semgrep-scan: verdict commun non rendu (scan_verdict rc=$sv_rc)" >&2
fi
# A perimeter that LOST paths renders NO common verdict (T-01M4X9PP7FED0570PMPSYGA0V8,
# C10): scan_verdict.py counts the candidates it is given, it cannot say a loss,
# so the unread path would read `status=clean`. "No verdict rather than a stale
# one" (the rule of this producer) extends to "rather than a false one".
if [ "$PERTE_N" -gt 0 ]; then
  rm -f "$SV_VERDICT"
  echo "semgrep-scan: verdict commun non rendu (périmètre incomplet)" >&2
fi

# rc=124 is `timeout`'s "killed at the deadline" code — a dedicated branch that
# SAYS the scan expired: DEGRADED, never "clean", never a block. Only reachable
# when the envelope was actually placed (TIMED=1); in the bare branch nothing
# of ours produces 124, so it falls through to the generic error path instead.
if [ "$TIMED" -eq 1 ] && [ "$rc" -eq 124 ]; then
  echo "COVERAGE DEGRADED: semgrep timed out after ${SEMGREP_TIMEOUT:-180}s (${#FILES[@]} file(s))" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi
if [ "$rc" -ne 0 ]; then
  echo "COVERAGE DEGRADED: semgrep error ($rc) scanning the diff" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

# ---- parse findings + SCOPE, with a CLOSED enumeration of failure paths -----
# Invariant (T-00000262): NO path writes CLEAN when the report itself is
# defective. The audit log and scan.sast are the PERSISTED channel machines
# read, so a CLEAN posted on a scope nobody measured is the class of defect
# this closes. Never dump matched code snippets — only rule_id and file:line
# reach the console / audit log, same discipline as gitleaks --redact. LOCFILE
# is already registered in cleanup() above (declared before this mktemp so the
# EXIT trap always covers it, even on an interruption/timeout mid-scan).
LOCFILE="$(mktemp "${TMPDIR:-$OUT}/.semgrep-loc.XXXXXX")" || LOCFILE=""
# Files semgrep listed as scanned but only PARTIALLY parsed. mktemp (O_EXCL,
# random name), never a name derived from the pid under $OUT: the PARSE opens
# it "w", which FOLLOWS a link, and a committed link at the guessable
# `$OUT/.semgrep-unparsed.<pid>` made the gate truncate the file behind it,
# outside the repository (closing review 2, F1: fixture fxU, rc 0 `clean on
# the diff.`, the file behind the link left at 0 bytes).
UNPARSED="$(mktemp "${TMPDIR:-$OUT}/.semgrep-unparsed.XXXXXX")" || UNPARSED=""
total=0
SCOPE=""            # unknown until parsed: "absent" | "nopython" | integer S
N="${#CIBLES[@]}"   # files AND git-object labels (T-01M4XY8NC97JBSQP6C28AFD7QP)

# (row 1) report absent or empty — pure shell (`! -s`), no parser needed.
# semgrep --json ALWAYS writes a JSON object (even `{"results":[]}`), so an
# empty report means the run failed to produce one: DEGRADED, never CLEAN.
if [ ! -s "$REPORT" ]; then
  echo "COVERAGE DEGRADED: semgrep report empty — scope unmeasured (a 0 here proves nothing)" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

# ---- THE PARSE CANNOT FAIL OPEN (security-code-review S-01M52B4FB4) ---------
# This script runs WITHOUT `set -e` (`set -uo pipefail`): a failing step does not
# stop it, it hands an EMPTY value to the next test. Measured on d0c2c238 with a
# fake semgrep: a report that is a JSON list, a result that is not an object, a
# path carrying a lone surrogate (UnicodeEncodeError writing $LOCFILE, a REAL
# finding lost), or a failed mktemp below each made the parser die with an
# empty stdout; `total` then defaulted to 0, `[ "" -eq 0 ]` and `[ "" -lt "$N" ]`
# both answered FALSE (rc 2), and the scope case fell through to "full scope":
# `clean on the diff.`, rc 0. Every guard below names ITS reason, so a reader
# (and the suite) can tell which one held: work file not creatable / parser
# exited N / parser output malformed / not a JSON object / count unreadable.
# (1) The two work files: an empty name is opened as "" by the parser.
if [ -z "$LOCFILE" ] || [ -z "$UNPARSED" ]; then
  echo "COVERAGE DEGRADED: semgrep report parse — work file not creatable (mktemp failed under ${TMPDIR:-$OUT}) — findings and scope unmeasured, a 0 here proves nothing" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

if [ -n "$PY" ]; then
  PARSE=$("$PY" - "$REPORT" "$LOCFILE" "$UNPARSED" <<'PYEOF'
import json, sys
report, locfile, unparsedfile = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(report, encoding="utf-8"))
except Exception:
    # (row 2) the except NO LONGER swallows into an empty result set: it emits
    # a sentinel so the shell DEGRADES instead of writing a false CLEAN.
    print("INVALID"); sys.exit(0)

# THE SHAPE OF WHAT IS READ BELOW (T-01M52EC9PE7758B4ZG95YXMSJN). Valid JSON is
# not a semgrep report: `{}` read 0 results, `clean on the diff.`, rc 0, while
# the common verdict of the SAME run said degraded/report_unreadable. The test
# is COPIED from scan_verdict.py `_forme_semgrep` (read, never imported: this
# parser runs where that module may not), on the fields THIS parser reads only.
# Bound, said: `skipped_rules` and `paths.skipped` are not read here, so not
# checked — the common verdict still degrades on them. Kept in parity with the
# hook copy (`forme_hk`) and with `_forme_semgrep` by the suite's arm (prsp).
def forme(d):
    if not isinstance(d, dict):
        return False
    res = d.get("results")
    if not (isinstance(res, list) and all(isinstance(r, dict) for r in res)):
        return False
    err = d.get("errors")
    if err is not None and not (isinstance(err, list) and all(isinstance(e, dict) for e in err)):
        return False
    pth = d.get("paths")
    if pth is None:
        return True
    if not isinstance(pth, dict):
        return False
    sc = pth.get("scanned")
    return sc is None or (isinstance(sc, list) and all(isinstance(q, str) for q in sc))

if not forme(data):
    print("MALFORMED"); sys.exit(0)
results = data.get("results", [])
paths = data.get("paths", {})

# A PARTIALLY PARSED FILE IS NOT A COVERED FILE (T-00000370, 13th axis).
# Measured on this repo's own 50 shell scripts: 10 fail to parse, ALL TEN are
# PartialParsing, and all ten appear in `paths.scanned` anyway — among them
# gitleaks-scan.sh (the class-0 secrets scanner), verify.sh, and this very
# script. Counting them as scanned would let the gate announce FULL coverage of
# a file whose unknown remainder was never analysed: the founding defect of this
# ticket — a verdict rendered on an undimensioned perimeter — rebuilt one storey
# up, BY the fix. So they are SUBTRACTED from the scope figure and NAMED.
# The path may sit on the error itself or inside a ['PartialParsing', [ … ]]
# payload; both shapes are read, and neither is assumed.
errored = set()
for e in (data.get("errors") or []):
    if not isinstance(e, dict):
        continue
    q = e.get("path")
    if q:
        errored.add(str(q).replace("\\", "/"))
    kind = e.get("type")
    if isinstance(kind, list) and len(kind) > 1 and isinstance(kind[1], list):
        for item in kind[1]:
            if isinstance(item, dict) and item.get("path"):
                errored.add(str(item["path"]).replace("\\", "/"))

unparsed = []
if isinstance(paths, dict) and "scanned" in paths:
    scanned = [str(q).replace("\\", "/") for q in (paths.get("scanned") or [])]
    unparsed = sorted(set(scanned) & errored)
    scope = str(len(scanned) - len(unparsed))
else:
    scope = "absent"                                    # key absent on a readable report
with open(unparsedfile, "w", encoding="utf-8") as fh:
    for q in unparsed:
        fh.write(q + "\n")
with open(locfile, "a", encoding="utf-8") as fh:
    for r in results:                                   # location + rule only — never the matched code
        path = r.get("path", "?")
        line = r.get("start", {}).get("line", "?")
        rule = r.get("check_id", "?")
        fh.write(f"{path}:{line} [{rule}]\n")
print(f"{len(results)} {scope}")
PYEOF
)
  py_rc=$?
  # (2) The parser's OWN status, read first: a parser that died is never read,
  # whatever it printed before dying.
  if [ "$py_rc" -ne 0 ]; then
    echo "COVERAGE DEGRADED: semgrep report parse — parser exited $py_rc — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  if [ "$PARSE" = "INVALID" ]; then
    echo "COVERAGE DEGRADED: semgrep report is not valid JSON — scope unmeasured" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  # Valid JSON of the WRONG SHAPE (`{}`, `[]`, results not a list of objects,
  # errors/paths/scanned mistyped): read as a clean run before this guard.
  if [ "$PARSE" = "MALFORMED" ]; then
    echo "COVERAGE DEGRADED: semgrep report parse — report malformed (no 'results' list of objects, or errors/paths mistyped) — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  # (3) The SHAPE of what it printed: exactly `<findings> <scope>`, findings an
  # integer, scope an integer or `absent` — anything else (an empty line, a
  # stray line on stdout before the figures) is never read as a count.
  _pn="${PARSE%% *}"; _pscope="${PARSE##* }"; _parse_ok=1
  [ "$PARSE" = "$_pn $_pscope" ] || _parse_ok=0
  case "$_pn" in
    ''|*[!0-9]*)
      _parse_ok=0 ;;
  esac
  case "$_pscope" in
    absent)
      : ;;
    ''|*[!0-9]*)
      _parse_ok=0 ;;
  esac
  if [ "$_parse_ok" -ne 1 ]; then
    echo "COVERAGE DEGRADED: semgrep report parse — parser output malformed (expected '<findings> <scope>') — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  total="$_pn"
  SCOPE="$_pscope"
else
  # No Python: approximate — count "check_id" occurrences and record the rule
  # ids seen (good enough for a redacted audit trail without a JSON parser).
  # Scope CANNOT be verified here (paths.scanned needs a JSON parser), so
  # SCOPE stays "nopython" and the verdict is kept, announced (row 6).
  # (4) semgrep --json writes ONE JSON object: a report that does not open on
  # `{` (a list, a stray line) holds no `"check_id"` to count, and its grep
  # count of 0 read `clean on the diff.` (measured with `[]`). Builtins only —
  # a narrowed PATH cannot turn this guard into a 127. An object WITHOUT a
  # `results` list is caught by (6) below; the bound of this branch is said there.
  _first=""
  IFS= read -r -n 1 _first < "$REPORT"
  case "$_first" in
    "{")
      : ;;
    *)
      echo "COVERAGE DEGRADED: semgrep report parse — not a JSON object (no Python to parse it) — findings and scope unmeasured, a 0 here proves nothing" >&2
      audit "DEGRADED" 0 "[]"
      emit_scan degraded 0 "[]"
      exit 0 ;;
  esac
  while IFS= read -r cid; do
    printf '%s\n' "$cid" >> "$LOCFILE"
  done < <(grep -oE '"check_id"[[:space:]]*:[[:space:]]*"[^"]*"' "$REPORT" 2>/dev/null \
             | sed -E 's/.*"([^"]*)"$/\1/')
  total="$(grep -c '"check_id"' "$REPORT" 2>/dev/null || true)"
  # (6) An object that opens no `results` list (`{}`, `{"results":{}}`) holds no
  # `"check_id"` either: its count of 0 read `clean on the diff.` (measured with
  # `{}`, T-01M52EC9PE7758B4ZG95YXMSJN). A grep that cannot run (127) or fails
  # proves nothing and degrades the same way. An object that does not CLOSE —
  # its last non-blank byte is not `}` — is a TRUNCATED report: `{"results":[`
  # with rc 0 read `clean on the diff.` too (measured on fc6c0aa3, security
  # review of this task); its tail is read by `tail -c` (a 127 leaves it empty,
  # so it degrades as well). Bound, said: without a parser this branch only
  # sees that the list OPENS and that the object ENDS on `}` — a report cut
  # right after an inner `}`, the ELEMENTS of the list, `errors` and `paths`
  # are NOT checked; the Python branch above checks them.
  _res_ok=1
  grep -Eq '"results"[[:space:]]*:[[:space:]]*\[' "$REPORT" 2>/dev/null || _res_ok=0
  if [ "$_res_ok" -ne 1 ]; then
    echo "COVERAGE DEGRADED: semgrep report parse — no 'results' list (no Python to parse it) — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  _fin="$(tail -c 256 "$REPORT" 2>/dev/null)" || _fin=""
  _fin_ws="${_fin##*[![:space:]]}"
  _fin="${_fin%"$_fin_ws"}"
  _fin_ok=0
  case "$_fin" in
    *"}")
      _fin_ok=1 ;;
  esac
  if [ "$_fin_ok" -ne 1 ]; then
    echo "COVERAGE DEGRADED: semgrep report parse — report truncated (no Python to parse it: its last non-blank byte is not a closing brace) — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  SCOPE="nopython"
fi
# (5) The count itself, whatever branch produced it: an empty or non-integer
# count is NEVER defaulted to 0 (that default was the fail-open). Unreached on
# this script as it stands (the Python branch is shape-checked above, grep -c
# prints a number on any readable report): defense in depth, removed by the
# suite's mutant MPALL only, with (2), (3) and the scope branch below.
case "$total" in
  ''|*[!0-9]*)
    echo "COVERAGE DEGRADED: semgrep report parse — findings count unreadable — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0 ;;
esac

# ---- SCOPE verdict: a CLOSED enumeration, EVERY branch NAMED (C2/C3) ---------
# Only S=0-on-N>0 degrades; the rest let the normal verdict below stand (emit
# scanned, exit 0/1 per findings) and merely annotate the scope — never a
# silent else, never a DEGRADED on a clean run whose report simply omits the key.
case "$SCOPE" in
  nopython)
    echo "note: scope unverifiable (no Python) — verdict from grep count kept as-is" >&2 ;;
  absent)
    # `paths.scanned` absent on a READABLE report — the EXPECTED case of real
    # installs. Verdict UNCHANGED; treating it as a zero would DEGRADE every
    # clean run and make the journal false the other way (L-00000187).
    echo "note: scope unverifiable (semgrep report carries no paths.scanned key)" >&2 ;;
  ''|*[!0-9]*)
    # Neither an integer nor a named word: never handed to `-eq`/`-lt`, whose
    # rc 2 on a non-integer read as "full scope". Unreached as it stands (the
    # shape check above holds first) — defense in depth, removed by MPALL only.
    echo "COVERAGE DEGRADED: semgrep report parse — scope figure unreadable — findings and scope unmeasured, a 0 here proves nothing" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0 ;;
  *)
    if [ "$SCOPE" -eq 0 ] && [ "$N" -gt 0 ]; then
      # ---- CLASS E: S=0 is only BLINDNESS when something COVERED was in the
      # perimeter (T-00000370). Otherwise the repo genuinely holds nothing this
      # ruleset can read, and a DEGRADED there is a false alarm that teaches the
      # reader to skip the real ones. So the branch ASKS before it answers.
      #
      # THE REMEDY HOP IS GONE. Until T-00000370 this message said "re-run with
      # --at HEAD", because the default perimeter was the working-tree diff and
      # could not see committed code. The default is now the TARGET — commits
      # since the base plus the dirty tree — so there is nothing left to hop to,
      # and repeating the advice would send a reader to a NARROWER perimeter
      # than the one that just ran.
      # figures already established above — recomputing here would print the
      # ruleset announcements a second time.
      COVERED_COUNT="$PERIMETER_COVERED"
      if [ "$COVERED_UNMEASURABLE" -eq 1 ]; then
        couverture_at_least "refus de conclure"
        # The covered-language set could not be established: refusing to
        # conclude outranks every other verdict (L-00000186). The helper has
        # already said why on stderr.
        audit "DEGRADED" 0 "[]"
        emit_scan degraded 0 "[]"
        exit 0
      fi
      # Files semgrep LISTED as scanned but only PARTIALLY parsed are named
      # here, never counted. Measured on this repo: 10 of its 50 shell scripts,
      # gitleaks-scan.sh and verify.sh among them.
      UNPARSED_N=0
      UNPARSED_LIST=""
      if [ -s "$UNPARSED" ]; then
        UNPARSED_N="$(wc -l < "$UNPARSED" | tr -d ' ')"
        AUDIT_UNPARSED_N="$UNPARSED_N"      # so the machine record carries it too
        UNPARSED_LIST="$(paste -sd',' "$UNPARSED" 2>/dev/null || tr '\n' ',' < "$UNPARSED")"
      fi
      if [ "${COVERED_COUNT:-0}" -eq 0 ]; then
        # No file of a covered language was in the perimeter at all. But a file
        # MAY still be of a language this script KNOWS (its extension is in the
        # mapping table above) that the ruleset carries NO rule for — that
        # residual absence is NAMED here, per language, instead of collapsing
        # into a bare "rien à lire" (T-00000317, symmetric to sca-scan.sh's
        # per-ecosystem "skipped"). The objective sentence is BOUNDED to THIS
        # COVERED_COUNT=0 branch (C3, tranche = borne): where at least one
        # covered file WAS scanned, the partial-scope line below (S<N) already
        # carries the shortfall, so the naming is not duplicated there.
        #
        # ext -> canonical language name — kept ALIGNED with covered_extensions()
        # above (same universe of extensions, read the other way). A perimeter
        # extension that is NOT in COVERED_EXTS and IS in this table is a
        # present-without-rule language; an extension in neither (a .txt) stays
        # UNNAMED, so the negative control (p) survives unchanged.
        UNRULED_LANGS=""
        for _f in ${CIBLES[@]+"${CIBLES[@]}"}; do
          _e="${_f##*.}"
          [ "$_e" != "$_f" ] || continue           # no dot => no extension
          _is_covered=0
          while IFS= read -r _ce; do
            [ "$_e" = "$_ce" ] && { _is_covered=1; break; }
          done <<< "$COVERED_EXTS"
          [ "$_is_covered" -eq 0 ] || continue      # covered ext => it HAS a rule
          case "$_e" in
            py|pyi)          UNRULED_LANGS="$UNRULED_LANGS python" ;;
            js|jsx|mjs|cjs)  UNRULED_LANGS="$UNRULED_LANGS javascript" ;;
            ts|tsx|mts|cts)  UNRULED_LANGS="$UNRULED_LANGS typescript" ;;
            java)            UNRULED_LANGS="$UNRULED_LANGS java" ;;
            yml|yaml)        UNRULED_LANGS="$UNRULED_LANGS yaml" ;;
            go)              UNRULED_LANGS="$UNRULED_LANGS go" ;;
            rb)              UNRULED_LANGS="$UNRULED_LANGS ruby" ;;
            php)             UNRULED_LANGS="$UNRULED_LANGS php" ;;
            c|cc|cpp|h|hpp)  UNRULED_LANGS="$UNRULED_LANGS c/c++" ;;
            cs)              UNRULED_LANGS="$UNRULED_LANGS csharp" ;;
            rs)              UNRULED_LANGS="$UNRULED_LANGS rust" ;;
            sh|bash)         UNRULED_LANGS="$UNRULED_LANGS shell" ;;
            *)               : ;;                    # extension hors table => non nommé
          esac
        done
        UNRULED_LANGS="$(printf '%s\n' $UNRULED_LANGS | grep -v '^$' | sort -u \
                          | tr '\n' ',' | sed 's/,$//; s/,/, /g')"
        NAME_MSG="semgrep-scan: 0 cible inspectée sur $N (périmètre : ${SCOPE_NOTE:-$SCAN_MODE}) — aucun fichier du périmètre n'est d'un langage que ce ruleset déclare; rien à lire, ce n'est pas un aveuglement"
        if [ -n "$UNRULED_LANGS" ]; then
          NAME_MSG="$NAME_MSG — langage(s) présent(s) sans règle : $UNRULED_LANGS"
        fi
        # "Not a blindness" only when nothing was lost upstream
        # (T-01M4X9PP7FED0570PMPSYGA0V8, C1): a lost path may be the covered one.
        if [ "$COUVERTURE" = "CLEAN" ]; then
          echo "$NAME_MSG" >&2
          audit "CLEAN" 0 "[]"
          emit_scan skipped 0 "[]"
        else
          echo "SAST (class-1 input, semgrep): aucun finding, mais couverture = $COUVERTURE — le vide N'EST PAS une preuve ici" >&2
          audit "CLEAN" 0 "[]"
          emit_scan degraded 0 "[]"
        fi
        exit 0
      fi
      if [ "$UNPARSED_N" -gt 0 ]; then
        if [ "$UNPARSED_N" -eq 1 ]; then P_VERB="n'a été PARSÉ QUE PARTIELLEMENT, et il est donc retiré du compte"; else P_VERB="n'ont été PARSÉS QUE PARTIELLEMENT, et ils sont donc retirés du compte"; fi
        echo "COVERAGE DEGRADED: 0 cible inspectée sur $N (périmètre : ${SCOPE_NOTE:-$SCAN_MODE}) — $COVERED_COUNT fichier(s) d'un langage couvert au périmètre, dont $UNPARSED_N $P_VERB. NON LU, nommément : $UNPARSED_LIST" >&2
      else
        echo "COVERAGE DEGRADED: 0 cible inspectée sur $N (périmètre : ${SCOPE_NOTE:-$SCAN_MODE}) — $COVERED_COUNT fichier(s) du périmètre sont d'un langage couvert et n'ont pourtant pas été inspectés — aveuglement réel" >&2
      fi
      audit "DEGRADED" 0 "[]"
      emit_scan degraded 0 "[]"
      exit 0
    elif [ "$SCOPE" -lt "$N" ]; then
      echo "note: partial scope — $SCOPE/$N cible(s) inspectée(s)" >&2      # (row 4) 0<S<N
    else
      : # DEFAULT branch NAMED (C3 it.2): key present and S=N (or S>N) => full scope, verdict proceeds
    fi ;;
esac

# ---- build a JSON array of the (capped) locations for the audit line --------
LOCJSON="[]"
if [ -s "$LOCFILE" ]; then
  if [ -n "$PY" ]; then
    LOCJSON=$("$PY" - "$LOCFILE" <<'PYEOF'
import json, sys
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
print(json.dumps(lines[:50]))
PYEOF
)
    loc_rc=$?
    # A failed read of the locations must not write `"locations":}` (an invalid
    # audit line): the verdict (FINDINGS, rc 1) is unchanged, the line stays JSON.
    case "$loc_rc:$LOCJSON" in
      "0:["*"]")
        : ;;
      *)
        echo "note: finding locations unreadable (parser exited $loc_rc) — the audit line carries [] ; the verdict is unchanged" >&2
        LOCJSON="[]" ;;
    esac
  else
    arr=""; count=0
    while IFS= read -r loc; do
      [ -n "$loc" ] || continue
      count=$((count + 1)); [ "$count" -gt 50 ] && break
      loc="${loc//\\/\\\\}"; loc="${loc//\"/\\\"}"
      arr="$arr,\"$loc\""
    done < "$LOCFILE"
    LOCJSON="[${arr#,}]"
  fi
fi

# ---- BOTH AXES ARE RENDERED, AND BOTH ARE ROUTED (C27) ----------------------
# The findings line is emitted FIRST and ALWAYS: findings are never masked by a
# coverage doubt. The coverage line follows when it is not CLEAN, so a run that
# finds a sink AND could not enumerate a submodule says so twice — one sentence
# per axis — instead of collapsing into whichever the code checked first.
if [ "$total" -gt 0 ]; then
  echo "SAST (class-1 input, semgrep): $total finding(s) on the diff — route to security-code-review triage" >&2
  [ "$COUVERTURE" = "CLEAN" ] \
    || echo "SAST couverture: $COUVERTURE — à traiter EN PLUS des $total finding(s), jamais à leur place" >&2
  audit "FINDINGS" "$total" "$LOCJSON"
  emit_scan scanned "$total" "$LOCJSON"
  exit 1
fi

if [ "$COUVERTURE" = "CLEAN" ]; then
  echo "SAST (class-1 input, semgrep): clean on the diff."
else
  echo "SAST (class-1 input, semgrep): aucun finding, mais couverture = $COUVERTURE — le vide N'EST PAS une preuve ici" >&2
fi
audit "CLEAN" 0 "[]"
# Channel A says `scanned` (events.py: scanned and clean) only on a CLEAN
# coverage; a lost path routes it to `degraded`, like the three other exits
# (T-01M4X9PP7FED0570PMPSYGA0V8, closing review T1).
if [ "$COUVERTURE" = "CLEAN" ]; then
  emit_scan scanned 0 "[]"
else
  emit_scan degraded 0 "[]"
fi
exit 0
