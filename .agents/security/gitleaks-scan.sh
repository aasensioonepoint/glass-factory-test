#!/usr/bin/env bash
# .agents/security/gitleaks-scan.sh — class-0 SECRETS gate (gitleaks).
#
# Class-0 is ABSOLUTE and NON-WAIVABLE: a real, live secret blocks — full stop.
# This script reads ONE exception register — the project .gitleaks.toml
# (GITLEAKS_CONFIG, l.32), passed to gitleaks at l.74 as --config and honoured by
# the deterministic fallback for its [allowlist] regexes ONLY, taken as LITERALS
# on the token (never paths, never a regex metacharacter) — and read in ONE shape
# only: the MULTI-LINE `regexes = [` … `]` block of the FIRST [allowlist] table,
# one entry per line; any other TOML spelling gitleaks accepts (a one-line array,
# [[allowlists]], a second [allowlist] table) yields 0 literals here, and the
# `fallback allowlist: 0 literal(s) honoured` line SAYS so — plus the upstream
# gitleaks EXAMPLE-suffix rule, transposed to the token, extended to all nine
# families, and RE-TESTED: a token ending in EXAMPLE is exempt ONLY if cutting
# that suffix stops it matching any family (the suffix was load-bearing for the
# shape, as in AWS's AKIA + IOSFODNN7EXAMPLE — written BROKEN here, and in the
# body below, because the contiguous 20-char token would make this class-0
# scanner trip on its OWN source; (c4)/(c4bis) pin that). A token that matches
# is a credential wearing a word and it BLOCKS — the exemption is a shape test,
# never a spelling. Both are written here because a filter on a
# class-0 gate that goes unsaid is a silent exemption, and a bound on that filter
# that goes unsaid is a trap. (Dependency CVEs are classes 1-3 and live in
# sca-scan.sh; secrets are class-0 and sit above them.)
#
# That register is PILOT-ONLY (T-00000844): protect-paths.sh, protect_paths.py
# and permissions.deny refuse an agent Edit of it. And it must LOAD: a config
# gitleaks cannot load is SET ASIDE, said ("… unreadable — default rules,
# allowlist IGNORED"), and the scan runs on the default rules — a real secret
# still BLOCKS, and so does every false positive it exempted, until repaired.
# In diff mode (the Stop hook) every COVERAGE DEGRADED line also reaches stdout
# as ONE {"systemMessage": …} object, because stderr on exit 0 reaches no one.
#
# Call forms:
#   gitleaks-scan.sh --content   read text on STDIN (e.g. a PreToolUse
#                                tool_input payload) and scan it in-memory —
#                                catches a secret BEFORE it ever hits disk.
#   gitleaks-scan.sh             default: scan the working-tree DIFF (changed +
#                                untracked files vs HEAD) AND the index entries
#                                that differ from HEAD — what `git commit` takes
#                                (T-01M4X7Q1RR7WPF1GWYFEFHDDM9) — never the
#                                whole git history.
#
# Callers (git grep, 2026-09-29): Claude Code (.claude/settings.json — Stop, and
# PreToolUse Edit|Write with --content), the Gemini/Antigravity registrations
# (.agents/hooks.json — both forms), the Codex / Copilot / Kimi hook
# registrations (.codex/hooks.json, .github/hooks/agent-guardrails.json,
# .kimi-code/hooks.json — both forms) and .agents/bin/mcp_render.py
# (--content). Neither core-scripts/verify.sh nor
# the pre-push hook calls it.
#
# gitleaks always runs with --redact: a secret VALUE never reaches stdout, the
# console, or the audit log. Only counts and file:line locations are recorded.
# Outputs: a location read from the INDEX copy reads `index:<path>:<line>`; a
# file identical in the tree and in the index counts twice (same verdict).
#
# Exit codes (mirrors sca-scan.sh's "never a false GO, never a false block"):
#   0  clean — OR gitleaks absent AND the deterministic fallback found nothing.
#      A perimeter not read ENTIRELY (an unreadable file or directory, an
#      unreachable submodule) also exits 0, but DEGRADED and said — never clean
#      (pilot decision S-01M4XWS5NDR78YXVG5E42ZQCM2: degrade, never block).
#      A benign path must NEVER exit 2: Claude Code treats hook exit 2 as a
#      BLOCKING error, so a false 2 on the "nothing to scan" path becomes an
#      infinite hook loop.
#   2  a real secret was detected — BLOCK (class-0, non-waivable) — by gitleaks,
#      OR by the deterministic fallback (9 PREFIXED families, --redact
#      equivalent) when gitleaks is absent. GITLEAKS_FALLBACK=0 in the HOST's
#      environment AT LAUNCH restores the old always-passing contract.
set -uo pipefail

# ---- SORTIE PRÉCOCE SOUS COPILOT : LECTURE LOCALE (T-01M4RWC6VHHN479J2A9RRY1BE3)
# Sous AGENTS_HOOK_HOST=copilot SEULEMENT, et sur la seule forme --content : un
# outil de lecture locale, identifié POSITIVEMENT par son nom de premier niveau,
# sort avant tout git, mktemp ou mkdir. Définie ICI, appelée juste après la
# résolution de PY : la fenêtre qui suit le diagnostic « PYTHON 3 NOT FOUND »
# reste celle qu'épingle .agents/evals/test_python_hook_launchers.py. Le nom est
# lu et comparé DANS python, sur la liste OUTILS_LECTURE_COPILOT, copie jumelle
# de celle de .codex/hooks/_common.py (filet :
# .agents/evals/test_copilot_early_exit.py) ; jamais relu comme du shell. Tout
# le reste — forme groupée ou HYBRIDE (`toolCalls` ou `tool_calls` à côté d'un
# nom listé : un second outil), graphies du nom en désaccord, nom vide ou
# inconnu, charge illisible, python absent, stdin terminal — suit le chemin
# entier et EST JUGÉ (classe 0 : .agents/security/gitleaks-scan.test.sh (vii)).
# La charge, lue sous copilot seulement, est réinjectée sur stdin quand le nom
# n'est pas listé : elle arrive entière au scanner.
# PERTE ACCEPTÉE, écrite au plan (décision S-01M4RWM3TC4JWE5FDC8YB819Z4) : pour
# un nom listé, l'argument (le path d'un view, le pattern d'un grep) n'est plus
# scanné ; il reste dans le processus local, et le scan du diff au Stop reste
# entier. Un nom dont l'argument SORT du poste (web_fetch, web_search…) n'est
# jamais listé (C1) : .agents/security/gitleaks-scan.test.sh (vi) le tient.
sortie_precoce_copilot() {  # "$@" = les arguments du script
  local forme=0 charge
  [ "${1:-}" = "--content" ] && forme=1
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
        # redirection échoue ne fait pas sortir le script et laisserait le
        # scanner sur un stdin déjà vidé (fail-open, mesuré bash 3.2 et 5.3) :
        # classe 0, la charge non réinjectée est BLOQUÉE, jamais jugée vide.
        exec <<<"$charge" || { echo "gitleaks-scan: charge copilot non reinjectable sur stdin (here-string sans fichier temporaire) : BLOQUEE, jamais jugee vide (classe 0)" >&2; exit 2; }
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
# No lazy fetch for ANY git below (T-01M4Y09EY4M664896DMGDTMDXF): in a partial
# clone, fetching a missing blob RUNS `remote.<name>.uploadpack` (measured: the
# census diff, the index cat-file, ls-files --others). A refused fetch fails,
# and is counted. git >= 2.45; older: no effect — see paresseux (README).
export GIT_NO_LAZY_FETCH=1
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ROOT="$(cd "$ROOT" && pwd)"            # canonicalize (Git Bash: git prints C:/..., pwd prints /c/...)
OUT="$ROOT/.agents/state/local/sca-reports"
# A GITLEAKS_CONFIG coming from the HOST's environment is EXPORTED, so the line
# below re-points it at $ROOT/.gitleaks.toml for gitleaks too (present or not).
# Noted here so the config check (T-00000844, after a failed scan) can name it.
GL_ENV_CONFIG="${GITLEAKS_CONFIG:-}"
GITLEAKS_CONFIG="$ROOT/.gitleaks.toml" # optional allowlist for false positives (see README-SECURITY-SCAN-SETUP.md)
MODE="diff"; [ "${1:-}" = "--content" ] && MODE="content"

have() { command -v "$1" >/dev/null 2>&1; }
mkdir -p "$OUT"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- COVERAGE DEGRADED must REACH someone (T-00000844) ----------------------
# Every DEGRADED path of this gate exits 0 (a benign path never blocks a hook),
# and on exit 0 Claude Code shows the hook's stderr to NOBODY — neither the model
# nor the pilot. A DEGRADED said on stderr alone was therefore a silence. `deg`
# still writes stderr (callers and the suites read it there) AND records the
# line in $DEGFILE — a FILE, not a variable, because the submodule enumeration
# runs in a process substitution whose variables die with it. At exit 0 in DIFF
# mode (the Stop hook), on_exit() turns those lines into ONE stdout object
# `{"systemMessage": "COVERAGE DEGRADED: …"}` — the Stop form semgrep-scan.sh
# emits for EVERY host (its `event == "stop"` branch precedes any host test), so
# no AGENTS_HOOK_HOST switch here. The plain stdout sink text ("clean." / "nothing
# to scan") is then carried INSIDE that object, never next to it: Claude parses
# ALL of stdout as JSON, and JSON + a text line is unreadable — the notice would
# be lost without a sound. Exit 2 (BLOCKED) keeps stderr alone, which Claude
# re-feeds to the model. --content mode (PreToolUse, mcp_render.py) is unchanged.
DEGFILE="$(mktemp "${TMPDIR:-/tmp}/gitleaks-deg.XXXXXX" 2>/dev/null)" || DEGFILE=""
FINAL_OUT=""
deg() {  # $1 = one COVERAGE DEGRADED line
  printf '%s\n' "$1" >&2
  if [ -n "$DEGFILE" ]; then
    printf '%s\n' "$1" >> "$DEGFILE" 2>/dev/null
  fi
  return 0
}

# ---- A perimeter that could not be READ is never called clean ---------------
# (T-01M4X7Q1RR7WPF1GWYFEFHDDM9). perte_perimetre <count> <cause> says ONE
# COVERAGE DEGRADED line AT THE FINDING — a COUNT, never a path: a caller may
# capture 2>&1, and a path is repo-controlled text — then poses CENSUS_OK=0, so
# the verdict sinks of BOTH engines refuse "clean" and say WHY. The first loss
# REPLACES the default census texts (kept byte for byte when nothing is lost:
# (c15)/(c16)/(c17) grep them); a further loss is APPENDED after "; ". No cause
# ever carries " file(s) scanned, " — the fallback's completion marker; no script parses it since T-01M5PCCHMWXTRCM5QJT8J5KNEH: its reader ("a consumer" below) is whoever reads the Stop systemMessage or the audit log.
perte_perimetre() {  # $1 = count (or "?")  $2 = cause
  deg "COVERAGE DEGRADED: $1 $2 — not scanned; perimeter INCOMPLETE"
  if [ "$CENSUS_OK" = 1 ]; then
    CENSUS_WHY="$1 $2"
    CENSUS_MARK="$1 $2"
    CENSUS_TAIL0="nothing could be read, so nothing was scanned"
    CENSUS_TAIL0M="nothing readable"
  else
    CENSUS_WHY="$CENSUS_WHY; $1 $2"
    CENSUS_MARK="$CENSUS_MARK; $1 $2"
  fi
  CENSUS_OK=0
  return 0
}

# injoignable <root> <rel> : rc 0 when <rel> cannot be reached because a parent
# directory EXISTS but is not searchable (chmod 000, a volume of another owner) —
# as opposed to a path really deleted. Walks up to the first ancestor that
# exists and judges THAT one; a path without a parent is never unreachable.
injoignable() {  # $1 = root  $2 = path relative to root
  local p="${2%/*}"
  [ "$p" = "$2" ] && return 1
  while :; do
    if [ -e "$1/$p" ]; then
      if [ -d "$1/$p" ] && [ ! -x "$1/$p" ]; then
        return 0
      fi
      return 1
    fi
    case "$p" in
      */*)
        p="${p%/*}" ;;
      *)
        return 1 ;;
    esac
  done
}

# Every git call that reads a repository goes through gitn (K1): measured on git
# 2.55, a `core.fsmonitor` command from the repository's config is RUN by
# diff-index --cached, ls-files -s, ls-files -v, ls-files --others and diff
# alike, and a submodule's git dir carries a config of its own. Since
# T-01M4Y09EY4M664896DMGDTMDXF that includes the census calls which predated
# T-01M4X7Q1RR7WPF1GWYFEFHDDM9 (root census, submodule listing, submodule
# enumeration); only the header's `rev-parse --show-toplevel` stays plain.
GITN=(git -c core.fsmonitor=false -c core.hooksPath=/dev/null)
gitn() { ${GITN[@]+"${GITN[@]}"} "$@"; }

# paresseux <location args> (T-01M4Y09EY4M664896DMGDTMDXF, security review): rc 0
# when the repository is a PARTIAL clone (a promisor remote) and this git cannot
# refuse a lazy fetch — it has no `--no-lazy-fetch`, which arrived with the
# no-lazy-fetch variable in git 2.45 (RelNotes 2.45.0): there the export above
# has no effect, and a missing blob would be fetched, RUNNING the remote's
# uploadpack. The census diff and every `cat-file` are then NOT run, and the
# loss is said (DEGRADED). The capability is probed ONCE, and only when a
# promisor exists: an ordinary repository pays one `git config` read.
_NLF=""
paresseux() {  # "$@" = location args (-C <dir> | --git-dir=<dir> …)
  gitn "$@" config --get-regexp '^(remote\..*\.promisor|extensions\.partialclone)$' >/dev/null 2>&1 || return 1
  if [ -z "$_NLF" ]; then
    _NLF=oui
    gitn --no-lazy-fetch version >/dev/null 2>&1 || _NLF=non
  fi
  [ "$_NLF" = non ]
}

# filtres_neutres <repo> (T-01M4Y09EY4M664896DMGDTMDXF): a `filter.<driver>.clean`
# or `.process` of the repository's config is a COMMAND, which `git diff` runs
# on a tracked file whose content it has to read (measured: a racily clean
# entry, even under diff.autoRefreshIndex=false). Prints, NUL-separated, the
# options that empty every such driver for ONE git call — `--config-env=` on
# `filter.<n>.clean` and `.process` (GL_VIDE) and `.required` (GL_FAUX), git >=
# 2.31; never `-c`, which cuts a driver named `a=b` at its first `=` (measured)
# — then the record `ok`. The drivers are read in EVERY scope (system, global,
# local, worktree, includes, command line: a driver declared through an
# include or GIT_CONFIG_GLOBAL runs too), GIT_CONFIG unset (it points `git
# config` at another file, which `git diff` never reads). PROVEN by a re-read
# with the options applied: the LAST value of every clean/process key must be
# empty; otherwise — or on an older git, which refuses --config-env — `ok` is
# never printed and the caller does not run the diff. A SUBSHELL: the unset
# never leaks. Its work file ($2) is created by the CALLER, in _TMP_FN, so that
# cleanup() removes it when a signal stops the run (security review).
export GL_VIDE='' GL_FAUX=false
filtres_neutres() {  # $1 = repo dir  $2 = work file (created by the caller)
  (
    unset GIT_CONFIG
    nl=$'\n'
    lu="$2"
    [ -n "$lu" ] || exit 1
    rc=0
    gitn -C "$1" config -z --get-regexp '^filter\..*\.(clean|process)$' > "$lu" 2>/dev/null || rc=$?
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
      gitn ${opts[@]+"${opts[@]}"} -C "$1" config -z --get-regexp '^filter\..*\.(clean|process)$' > "$lu" 2>/dev/null || { rm -f "$lu"; exit 1; }
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

# ignores_illisibles <repo> (T-01M4Y09FSEM2QQNA7Y9KRH5DJG): a `.gitignore` flagged
# skip-worktree (tag `S`, or `s` when also assume-unchanged, in `ls-files -v`)
# and ABSENT from the disk is read by the census `ls-files --others
# --exclude-standard` from its INDEX blob — which a partial clone may not have:
# under the no-lazy-fetch export git reads it as EMPTY. Measured: it over-lists
# (what it ignored comes back: noise, scanned) or UNDER-lists — a `!keep.log`
# negation in `d/.gitignore` under a root `*.log` was lost, `d/keep.log` and its
# key were never listed, and the run read "nothing to scan", rc 0. Such a file
# is COUNTED in _ign_ill (one loss line after the submodule loop) only when it
# can hide something. A lost `!` can only hide a file the rules APPLIED now
# IGNORE (an untracked file already listed is scanned, never missed — exec-critic
# major 1, orchestrator decision): so its directory must EXIST and hold an
# untracked path that is IGNORED now — one listing per repo, `--ignored
# --exclude-standard --directory` on the candidate directories as literal
# pathspecs (under the export nothing is fetched; under an older git the census
# has already read that `.gitignore` the same way) — and its blob must be
# MISSING: ONE batch `cat-file` per repo for every candidate, never one process
# per file (a sparse clone carries hundreds: measured 5.86 s against 0.25 s).
# No candidate, no extra process. A git call that fails here is SAID, never read
# as a count of 0; a git older than 2.42 (no NUL-terminated batch-check) is said
# "not checked", and so is a partial clone under a git that cannot refuse the
# fetch (paresseux: the batch is not run). Called in THIS shell, never under a
# command substitution: perte_perimetre has to reach CENSUS_OK. Its work file
# lives in _TMP_SW, which cleanup() removes when a signal stops the run.
ignores_illisibles() {  # $1 = repo dir (absolute)
  local lv rec chemin d u i _g _k rc=0 n=0 j=0
  local -a cand=() rep=() unt=() garde=()
  _TMP_SW="$(mktemp "${TMPDIR:-/tmp}/gitleaks-sw.XXXXXX" 2>/dev/null)" || _TMP_SW=""
  lv="$_TMP_SW"
  if [ -z "$lv" ]; then
    perte_perimetre "?" "skip-worktree .gitignore check failed (no temporary file)"
    return 0
  fi
  # Only the `.gitignore` entries are listed (glob pathspec, root included): a
  # bash `read -d ''` loop over the WHOLE index cost 2 s per 100k entries under
  # bash 3.2 (closing review, measured). Under GIT_LITERAL_PATHSPECS git refuses
  # the glob (rc 128): said below as a failed check, never a silent 0 — a
  # default-mode `*/.gitignore` would under-match without a word.
  gitn --glob-pathspecs -C "$1" ls-files -v -z -- '**/.gitignore' > "$lv" 2>/dev/null || rc=$?
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
  if [ "$rc" -eq 0 ] && [ "${#cand[@]}" -gt 0 ]; then
    gitn --literal-pathspecs -C "$1" ls-files --others --ignored --exclude-standard --directory -z -- ${rep[@]+"${rep[@]}"} > "$lv" 2>/dev/null || rc=$?
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
  if [ "$rc" = 0 ] && [ "${#garde[@]}" -gt 0 ] && paresseux -C "$1"; then
    rc=paresseux
  fi
  if [ "$rc" = 0 ] && [ "${#garde[@]}" -gt 0 ]; then
    printf ':0:%s\0' ${garde[@]+"${garde[@]}"} | gitn -C "$1" cat-file --batch-check -Z > "$lv" 2>/dev/null || rc=$?
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
    elif ! gitn -C "$1" cat-file --batch-check -Z < /dev/null > /dev/null 2>&1; then
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
    paresseux)
      perte_perimetre "?" "skip-worktree .gitignore file(s) not checked (partial clone, git < 2.45: a missing blob would be fetched, running the remote's uploadpack)" ;;
    *)
      perte_perimetre "?" "skip-worktree .gitignore check failed (git rc $rc)" ;;
  esac
  return 0
}

# Prints the JSON object on stdout. json.dumps when python answers; otherwise a
# hand-built string: `\` and `"` escaped, control bytes dropped, lines joined by
# the two characters `\n` — valid JSON either way (a path in a message may carry
# a quote or a backslash, and a submodule path is repo-controlled).
emit_system_message() {
  local js="" line msg="" nl='\n'
  if [ -n "$PY" ]; then
    js="$({ cat "$DEGFILE"; if [ -n "$FINAL_OUT" ]; then printf '%s\n' "$FINAL_OUT"; fi; } \
      | "$PY" -c 'import json, sys
m = sys.stdin.buffer.read().decode("utf-8", "replace").strip("\n")
sys.stdout.write(json.dumps({"systemMessage": m}))' 2>/dev/null)" || js=""
  fi
  if [ -z "$js" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line//\\/\\\\}"
      line="${line//\"/\\\"}"
      line="$(printf '%s' "$line" | tr -d '\000-\037')"
      msg="${msg:+$msg$nl}$line"
    done < <(cat "$DEGFILE"; if [ -n "$FINAL_OUT" ]; then printf '%s\n' "$FINAL_OUT"; fi)
    js="{\"systemMessage\": \"$msg\"}"
  fi
  printf '%s\n' "$js"
}

audit() {  # $1 verdict  $2 findings  $3 locations-json  — one line per run, never the value
  printf '{"ts":"%s","mode":"%s","entry":"gitleaks-scan.sh","class":0,"waivable":false,"verdict":"%s","findings":%s,"locations":%s}\n' \
    "$TS" "$MODE" "$1" "$2" "$3" >> "$OUT/audit-log.jsonl"
}

# scan.secrets emission (T-00000018 shard 2) — $1 status (scanned|degraded|
# skipped), $2 findings count, $3 locations-json (already redacted, no value).
# A SEPARATE step from audit() above: audit-log.jsonl is the pre-existing,
# always-on trail; canal-A is additive observability, never a replacement.
emit_scan() {
  # T-00000041: this script is registered on ALL FOUR hosts, but the bridge it
  # calls lives under .claude/ and defaults `host` to "claude" — so scan.*
  # events from the other three either landed labelled `claude` or were lost
  # (the bridge re-resolves its own root from CLAUDE_PROJECT_DIR, unset there,
  # falling back to cwd). Both are fixed by passing what we already know:
  # EVT_HOST from the same AGENTS_HOOK_HOST discriminant the other hosts'
  # registrations already set, and
  # CLAUDE_PROJECT_DIR from $ROOT (resolved above via `git rev-parse`, so it is
  # correct on every host and independent of cwd). The `claude` fallback is not
  # a guess: Claude Code is the ONE host whose registrations cannot carry the
  # variable (its hooks live in .claude/settings.json, which agents never
  # edit), and the parity eval asserts the other three do set it.
  EVT_HOST="${AGENTS_HOOK_HOST:-claude}" CLAUDE_PROJECT_DIR="$ROOT" \
    bash "$ROOT/.claude/hooks/emit-event.sh" scan.secrets "status=$1" \
    "counters:={\"findings\":$2}" "locations:=$3" >/dev/null 2>&1 || true
}

# ---- Deterministic fallback secret scan (used ONLY when gitleaks is absent) ---
# Nine PREFIXED credential families, each with prefix + alphabet + LENGTH — never
# a bare prefix (a prefix alone matches prose). This is a `grep` over the staged
# tree, NOT a parser: it covers what a fixed-shape regex catches and NAMES what
# it cannot. NOT COVERED, on purpose: generic/entropy secrets, passwords,
# connection strings, JWTs, Azure/Twilio/SendGrid, Slack forms with no leading
# numeric segment (legacy xoxa-2-…, xapp-, xoxe-), binary files (grep -I), and —
# from the project .gitleaks.toml — everything the bounded read does not return
# (one honoured shape, everything else counts 0 and the marker says so). Each
# family is one array element so a per-family test can drop exactly one.
FALLBACK_FAMILIES=(
  '(AKIA|ASIA)[A-Z2-7]{16}'                                 # AWS access key id
  'gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}'  # GitHub token / fine-grained PAT
  'xox[baprs]-[0-9]{10,13}-[0-9A-Za-z-]{10,}'               # Slack bot/user token (leading numeric segment)
  'AIza[0-9A-Za-z_-]{35}'                                   # Google API key
  'glpat-[A-Za-z0-9_-]{20}'                                 # GitLab PAT
  'sk_live_[A-Za-z0-9]{24,}'                                # Stripe live secret key
  'sk-ant-[A-Za-z0-9_-]{20,}'                               # Anthropic API key
  'npm_[A-Za-z0-9]{36}'                                     # npm token
  '-----BEGIN[^-]*PRIVATE KEY-----'                         # PEM private-key block
)

# Read the project .gitleaks.toml allowlist, BOUNDED BY FORM (header l.5): ONLY
# the MULTI-LINE `regexes = [` … `]` block of the FIRST [allowlist] table, one
# entry per line, taken as LITERALS. Any other TOML spelling gitleaks accepts
# (a one-line array, [[allowlists]], a second [allowlist] table) yields 0
# literals here, and the marker SAYS so. Sets FB_LITERALS.
_fallback_read_allowlist() {  # $1 = toml path
  FB_LITERALS=()
  local cfg="$1" line trimmed after entry in_allowlist=0 in_regexes=0
  if [ ! -f "$cfg" ]; then
    echo "fallback allowlist: none (.gitleaks.toml absent)" >&2
    return 0
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    trimmed="${line#"${line%%[![:space:]]*}"}"          # left-trim
    case "$trimmed" in
      \#*) continue ;;
    esac # comment line
    if [ "$in_regexes" = 1 ]; then
      case "$trimmed" in
        ']'*) break ;;                                   # end of the block
        '') continue ;;
      esac
      entry="$trimmed"
      entry="${entry%"${entry##*[![:space:]]}"}"        # right-trim
      entry="${entry%,}"                                 # trailing comma
      entry="${entry%"${entry##*[![:space:]]}"}"        # right-trim before comma
      case "$entry" in
        \'\'\'*\'\'\') entry="${entry#\'\'\'}"; entry="${entry%\'\'\'}" ;;
        \'*\')         entry="${entry#\'}"; entry="${entry%\'}" ;;
        \"*\")         entry="${entry#\"}"; entry="${entry%\"}" ;;
      esac
      [ -n "$entry" ] && FB_LITERALS+=("$entry")
      continue
    fi
    if [ "$in_allowlist" = 0 ]; then
      case "$trimmed" in
        '[allowlist]'*) in_allowlist=1 ;;
      esac
      continue
    fi
    case "$trimmed" in
      regexes*=*'['*)
        after="${trimmed#*'['}"
        after="${after#"${after%%[![:space:]]*}"}"      # left-trim after '['
        case "$after" in
          ''|'#'*) in_regexes=1 ;;                      # pure multi-line opener
          *) break ;;                                    # inline array → not honoured
        esac
        ;;
      '['*) break ;;                                     # a new table ends the first [allowlist]
    esac
  done < "$cfg"
  echo "fallback allowlist: ${#FB_LITERALS[@]} literal(s) honoured from .gitleaks.toml" >&2
}

# The scan itself. Sets $total / $SCAN_STATUS; writes file:line (never the value)
# into $LOCFILE. Same polarity as the gitleaks path: kill-switch / timeout / tool
# error are DEGRADED (exit 0), never a false GO and never a false block; a
# retained finding hands back so the shared l.327 path BLOCKS (exit 2).
_fallback_scan() {
  if [ "${GITLEAKS_FALLBACK:-1}" = 0 ]; then
    echo "fallback scan: NOT RUN (GITLEAKS_FALLBACK=0)" >&2
    audit "DEGRADED" 0 "[]"; emit_scan degraded 0 "[]"; exit 0
  fi

  _fallback_read_allowlist "$GITLEAKS_CONFIG"

  local pattern grc line loc tok skip lit _ifs raw stripped
  _ifs="$IFS"; IFS='|'; pattern="${FALLBACK_FAMILIES[*]}"; IFS="$_ifs"

  # LC_ALL=C so a BSD grep does not abort on an invalid byte; -I skips binaries,
  # -o gives only the matched token, -n the line, -r recurses. Never PCRE.
  # Time-bounded exactly like the gitleaks path (l.242-251). The comsub is
  # DÉQUOTÉE on purpose (no `="$(`): it carries no heredoc, so it is not the
  # bash<4.4 parse debt bash-parse-oldest.test.sh pins.
  if have timeout; then
    raw=$(cd "$STAGE" && LC_ALL=C timeout "$GITLEAKS_TIMEOUT" grep -rIoEn -e "$pattern" . 2>/dev/null); grc=$?
  else
    deg "COVERAGE DEGRADED: no timeout(1) on PATH — fallback scan runs unbounded over $staged staged file(s)"
    raw=$(cd "$STAGE" && LC_ALL=C grep -rIoEn -e "$pattern" . 2>/dev/null); grc=$?
  fi

  # grep rc: 0 = match, 1 = none, >1 = error (BSD grep(1); GNU's 2 is covered by
  # -gt 1 without opening its doc). 124/137 = timeout expired / SIGKILL. Errors
  # and timeouts are DEGRADED and THROW AWAY the partial output — a partial
  # result presented as a verdict is a false green.
  if [ "$grc" -eq 124 ] || [ "$grc" -eq 137 ]; then
    deg "COVERAGE DEGRADED: fallback scan exceeded ${GITLEAKS_TIMEOUT}s over $staged staged file(s)"
    echo "fallback scan: ABORTED (timeout ${GITLEAKS_TIMEOUT}s over $staged staged file(s))" >&2
    audit "DEGRADED" 0 "[]"; emit_scan degraded 0 "[]"; exit 0
  fi
  if [ "$grc" -gt 1 ]; then
    deg "COVERAGE DEGRADED: fallback grep error (rc $grc) over $staged staged file(s)"
    echo "fallback scan: ABORTED (grep rc $grc over $staged staged file(s))" >&2
    audit "DEGRADED" 0 "[]"; emit_scan degraded 0 "[]"; exit 0
  fi

  total=0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    tok="${line##*:}"                 # token = after the last colon (no colon in any family)
    loc="${line%:*}"; loc="${loc#./}" # file:line, stripped of grep -r's leading ./
    # A location read from the INDEX copy is labelled `index:<path>:<line>`.
    if [ -n "$IDXNAME" ]; then
      case "$loc" in
        "$IDXNAME"/*)
          loc="index:${loc#"$IDXNAME"/}" ;;
      esac
    fi
    # EXAMPLE-suffix rule — STRIP THEN RE-TEST, never a naked `continue`.
    # The naked form (`case "$tok" in *EXAMPLE) continue`) let a REAL credential
    # through this class-0 gate. The count below is RE-DERIVABLE, so it cannot
    # drift again: the nine array elements spell TEN alternatives (the GitHub
    # element holds two), and the ones at risk are those ENDING in an OPEN
    # quantifier `{N,}` over an alphabet holding [A-Za-z] — FOUR of the ten:
    # sk-ant-…{20,}, github_pat_…{22,}, xox[baprs]-…-…{10,}, sk_live_…{24,}.
    # The criterion is TRAILING-and-open, not "open anywhere": the PEM
    # alternative carries an open `[^-]*` yet CLOSES on the fixed literal
    # `-----`, so its token can never end in the suffix — counting it gives the
    # wrong five. Only those four absorb: an `EXAMPLE` GLUED to a live key enters the
    # match, the captured token ends in EXAMPLE, and the token was dropped — after
    # which the run printed "N file(s) scanned, 0 finding(s)", i.e. a COMPLETE,
    # CLEAN scan (measured: sk-ant-api03-…0123456789 blocks, the same + EXAMPLE
    # passed). That line is also what a consumer reads as "the fallback scanned,
    # all clear" — a non-measure rendered green.
    # So: cut the suffix and ask the SAME nine families again.
    #   still a family  => the suffix was decoration on a real credential => KEEP;
    #   no longer one   => the suffix was LOAD-BEARING for the shape => fixture.
    # That is what keeps AWS's documented AKIA + IOSFODNN7EXAMPLE exempt (the
    # token is AKIA+16 only WITH the suffix; without it AKIA+9 matches nothing —
    # and the literal is written BROKEN so this scanner never trips on its own
    # source, which would otherwise depend on the very exception below) while a key
    # wearing the same word blocks. A fixture that SURVIVES the re-test is a
    # false positive like any other: it goes in .gitleaks.toml [allowlist].
    case "$tok" in
      *EXAMPLE)
        stripped="${tok%EXAMPLE}"
        if [[ ! "$stripped" =~ $pattern ]]; then continue; fi
        ;;
    esac
    skip=0
    for lit in ${FB_LITERALS[@]+"${FB_LITERALS[@]}"}; do
      case "$tok" in
        *"$lit"*) skip=1; break ;;
      esac # allowlist literal CONTAINED in the token
    done
    [ "$skip" = 1 ] && continue
    printf '%s\n' "$loc" >> "$LOCFILE"
    total=$((total + 1))
  done <<< "$raw"

  SCAN_STATUS=degraded
  if [ "$total" -eq 0 ]; then
    # Same discipline as the staged=0 branch: a 0-finding marker means the
    # perimeter was BUILT and swept. A partial census (one of the three census
    # commands failed while another returned names) swept SOMETHING, but not the
    # diff — so it is named DEGRADED rather than passed off as a clean sweep.
    if [ "$CENSUS_OK" = 0 ]; then
      deg "COVERAGE DEGRADED: $CENSUS_WHY — $staged file(s) swept, perimeter INCOMPLETE"
      echo "fallback scan: DEGRADED ($CENSUS_MARK — perimeter incomplete)" >&2
      audit "DEGRADED" 0 "[]"; emit_scan degraded 0 "[]"; exit 0
    fi
    echo "fallback scan: $staged file(s) scanned, 0 finding(s)" >&2
    audit "DEGRADED" 0 "[]"; emit_scan degraded 0 "[]"; exit 0
  fi
  echo "fallback scan: $staged file(s) scanned, $total finding(s)" >&2
  echo "engine=fallback (9 prefixed families) — a fixture literal that is NOT a credential goes in .gitleaks.toml: ONE ENTRY PER LINE inside the MULTI-LINE 'regexes = [' ... ']' of the FIRST [allowlist] table (any other TOML spelling reads as 0 here, and the 'fallback allowlist:' line above says so) ; read at EACH run, no relaunch ; to disable the fallback entirely: GITLEAKS_FALLBACK=0 in the HOST's environment at launch" >&2
}

# ---- gitleaks availability: absent => deterministic fallback ENGAGED (never a false block)
# ENGINE and SCAN_STATUS are posed UNCONDITIONALLY before the `if`: they are read
# on every path (l.330, the staging bound, the invocation site), and a bare read
# under `set -u` would kill the gate on the host where gitleaks IS present.
ENGINE=gitleaks
SCAN_STATUS=scanned
IGN_SEEN=0   # read at the BLOCKED sink on BOTH engines (T-00000844) — posed here, never in a branch
if ! have gitleaks; then
  ENGINE=fallback
  deg "COVERAGE DEGRADED: gitleaks not installed — deterministic fallback ENGAGED (9 prefixed families); generic/entropy/password/JWT secrets NOT covered"
fi

CFG=(); [ -f "$GITLEAKS_CONFIG" ] && CFG=(--config "$GITLEAKS_CONFIG")

# ---- Submodule enumeration (T-00000293) -------------------------------------
# gitleaks/semgrep build their perimeter from `git diff HEAD` + `ls-files
# --others`, each path filtered by `[ -f ]`. A gitlink is a DIRECTORY, so that
# filter drops it, and `ls-files --others` never descends across a submodule
# boundary — so a secret COMMITTED inside a submodule is invisible in EVERY git
# state (measured: docs/design/2026-08-22-mesure-scan-sous-modules.md). This
# enumeration re-includes the content of INITIALIZED submodules, recursively.
#
# Per repo, `git ls-files -z --stage` filtered on mode 160000 lists the gitlinks
# NUL-safely (never `submodule status`+awk, which splits a path with a space).
# Descent happens only when `<sub>/.git` EXISTS (`-e`, not `-d`: inside a
# submodule `.git` is a FILE pointer, not a directory) — i.e. only INITIALIZED
# submodules, whose content is actually on disk. Depth is bounded, and the bound
# SAYS SO when it bites (a silent bound would recreate the blindness one level
# down). Enumeration failure is fail-open AND ANNOUNCED: the superproject scan
# continues, but the shrunk perimeter is never passed off as full coverage.
# DUPLICATED in semgrep-scan.sh on purpose (no shared helper — the per-suite
# grep-scope pins want each script self-contained, same reason emit_scan is
# duplicated) — but the copies have DIVERGED, they are no longer verbatim: the
# semgrep copy reports its failures to $SG_SIG (T-01M4X9PP7FED0570PMPSYGA0V8),
# this one records an UNREACHABLE submodule for index_injoignables
# (T-01M4X7Q1RR7WPF1GWYFEFHDDM9) and lists the gitlinks through gitn and under
# the no-lazy-fetch export (T-01M4Y09EY4M664896DMGDTMDXF); aligning the semgrep
# copy is T-01M4Z24V0J813T40XRW3S4VW67. Prints each initialized submodule's
# path, relative to ROOT, NUL-separated on stdout; every notice goes to stderr.
SUBMODULE_SCAN_DEPTH="${SUBMODULE_SCAN_DEPTH:-8}"
enumerate_submodules() {  # $1 repo-abs  $2 prefix(rel to ROOT, "" at top)  $3 depth
  # `_racine` est LOCAL parce que cette fonction est RÉCURSIVE. Il existe pour
  # sortir les chevrons de la SYNTAXE de l'expansion : `${prefix:-<root>}` est
  # du bash valide que tree-sitter-bash ne parse pas, et un seul site retire ce
  # fichier ENTIER du compte des cibles inspectées par la porte SAST.
  local repo="$1" prefix="$2" depth="$3" lf rc rec mode path sub_rel sub_abs
  local _racine='<root>'
  lf="$(mktemp "${TMPDIR:-/tmp}/submod-ls.XXXXXX")" || return 0
  gitn -C "$repo" ls-files -z --stage > "$lf" 2>/dev/null; rc=$?
  if [ "$rc" -ne 0 ]; then
    deg "COVERAGE DEGRADED: submodule enumeration failed at '${prefix:-$_racine}' (git ls-files rc=$rc) — submodule content not scanned"
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
      # INITIALIZED but UNREACHABLE (its directory, or a parent, cannot be
      # searched): `-e` fails for want of access, not of a .git. Taken for "not
      # initialized", its committed secret passed as clean. Recorded for
      # index_injoignables (a FILE: this function runs under `< <(…)`), which
      # reads its index through its git dir and SAYS the tree unread.
      if injoignable "$ROOT" "$sub_rel/.git"; then
        if [ -n "$SUBUNREACH" ]; then
          printf '%s\0%s\0%s\0' "$repo" "$path" "$sub_rel" >> "$SUBUNREACH"
        fi
        continue
      fi
      echo "gitleaks-scan: submodule '$sub_rel' not initialized — content absent, not scanned" >&2
      continue
    fi
    printf '%s\0' "$sub_rel"                    # this submodule's OWN files get scanned
    if [ "$depth" -ge "$SUBMODULE_SCAN_DEPTH" ]; then
      deg "COVERAGE DEGRADED: submodule depth bound ($SUBMODULE_SCAN_DEPTH) exceeded at $sub_rel — content not scanned"
      continue                                  # scanned this one, but do not descend further
    fi
    enumerate_submodules "$sub_abs" "$sub_rel" "$((depth + 1))"
  done < "$lf"
  rm -f "$lf"
}

# ---- The INDEX is a second perimeter (T-01M4X7Q1RR7WPF1GWYFEFHDDM9, T-01M4X9Y079FMHBQHHQRXV4GK1V)
# `git commit` takes the INDEX, not the working tree: a key `git add`ed, then
# the file rewritten benign or made unreadable (chmod 000), used to pass as
# "clean." while the commit carried it. The candidates — every index entry
# that differs from HEAD (diff-index --cached), plus, for a submodule, its
# tracked files this gate could not read in the tree, plus every entry of an
# UNREACHABLE submodule's index, read through its git dir — are collected
# BEFORE the staging bound (one diff-index per repo, kept in $WORKD), then
# written AFTER the stage of the tree, into a FRESH directory under the stage
# ($IDX: mktemp -d, unpredictable, exclusive; nothing in it is ever a link).
# Blobs are read RAW by `git cat-file`: never `checkout-index`, whose
# smudge/LFS filters ran even under --attr-source (measured: filters declared
# in $GIT_DIR/info/attributes or core.attributesFile still ran). Modes read:
# 100644, 100755, and 120000 (a link's TARGET TEXT, written as a regular file:
# nothing is ever followed). Stage 0 only (K4); a conflict is read in the tree.
#
# The reader, when python answers: ONE `git cat-file --batch`, exactly <size>
# bytes per object, each file created O_EXCL|O_NOFOLLOW under the destination,
# a path that is absolute or carries an empty, "." or ".." component (or a
# backslash) refused and counted as NOT read. Its own deadline kills git. One
# line per candidate on stdout: "w" written, "d" the SAME object (same sha)
# already written at the SAME path in this run (a submodule file both changed
# in the index and unreadable in the tree); nothing for a candidate NOT read —
# the caller counts those as a loss. A destination that EXISTS for any other
# reason is NOT read: measured on APFS (case-insensitive), index `K.txt` benign
# + `k.txt` holding a key made the key's file collide with K.txt's, and a "d"
# that trusted mere existence read `clean.` — the commit carried the key. Same
# for two paths that differ only by Unicode normalization.
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
for sha, rel in zip(parts[0::2], parts[1::2]):
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
        sys.stdout.write("w\n")
    elif seen:
        sys.stdout.write("d\n")
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

# gitdir_sur <name> <git dir> <common dir> (K1): the name comes from a
# REPO-CONTROLLED .gitmodules, and `rev-parse --git-path modules/<name>` does
# not validate it. Refused: empty, absolute, a drive, a ".." component, a
# backslash; then the git dir, made PHYSICAL (pwd -P), must sit under the
# parent's common git dir /modules/. A refused name is DEGRADED, never opened.
gitdir_sur() {  # $1 = name  $2 = git dir (physical)  $3 = common git dir (physical)
  case "$1" in
    ''|/*|[A-Za-z]:*|..|../*|*/..|*/../*|*"\\"*)
      return 1 ;;
  esac
  [ -n "$2" ] && [ -n "$3" ] || return 1
  case "$2" in
    "$3"/modules/?*)
      return 0 ;;
  esac
  return 1
}

# index_ls_s <ls-files -s -z output> <prefix> <candidates file>: appends the
# STAGE-0 entries (K4: a conflict's stages 1-3 are content already committed on
# the merged branches) of mode 100644/100755/120000; counts gitlinks.
index_ls_s() {
  local rec meta p mode rest sha stg
  _ls_n=0; _ls_liens=0
  while IFS= read -r -d '' rec; do
    meta="${rec%%$'\t'*}"; p="${rec#*$'\t'}"
    mode="${meta%% *}"; rest="${meta#* }"
    sha="${rest%% *}"; stg="${rest#* }"
    [ "$stg" = 0 ] || continue
    case "$mode" in
      100644|100755|120000)
        printf '%s\0%s\0' "$sha" "$2$p" >> "$3"; _ls_n=$((_ls_n + 1)) ;;
      160000)
        _ls_liens=$((_ls_liens + 1)) ;;
    esac
  done < "$1"
}

# index_candidats C <repo> <prefix> | G <git dir> <prefix> — one GROUP of
# candidates (sha NUL path NUL, the path already carrying <prefix>), recorded
# in $IDXGROUPS, counted in _idx_n for the staging bound. C: the entries of the
# repo's index that differ from HEAD — or from the EMPTY tree, computed per repo
# (a sha256 submodule in a sha1 superproject has another), when there is no
# commit yet. A deletion and a conflict (status U, new mode 000000) carry no
# content to read; a gitlink has its own pass; a 040000 entry (a sparse index
# that was not expanded) is never dropped in silence. G: every stage-0 entry of
# an unreachable submodule, read through its git dir with --work-tree on a
# directory git never writes to (without it, git chdirs to core.worktree — the
# unreadable directory — and fails, measured).
index_candidats() {  # $1 = C | G  $2 = repo dir (C) or git dir (G)  $3 = destination prefix
  local base rc cand rec p rest mode sha stg n=0 vide=0
  [ -n "$WORKD" ] || return 0
  _grp=$((_grp + 1)); cand="$WORKD/c.$_grp"
  if [ "$1" = G ]; then
    gitn --git-dir="$2" --work-tree="$STAGE" ls-files -s -z > "$WORKD/ls" 2>/dev/null; rc=$?
    if [ "$rc" -ne 0 ]; then
      perte_perimetre 1 "git index of an unreachable submodule not read (ls-files failed) — content may already be committed"
      return 0
    fi
    : > "$cand"
    index_ls_s "$WORKD/ls" "$3" "$cand"
    n="$_ls_n"; _imbriques=$((_imbriques + _ls_liens))
  else
    # stderr is dropped ON PURPOSE: the channel is the rc; git's text is
    # localized and never parsed here. HEAD first (the common case costs ONE
    # process); only a failure asks whether HEAD exists at all.
    gitn -C "$2" diff-index --cached -z --no-renames HEAD -- > "$WORKD/ls" 2>/dev/null; rc=$?
    if [ "$rc" -ne 0 ] && ! gitn -C "$2" rev-parse -q --verify HEAD >/dev/null 2>&1; then
      # Not a repository at all: nothing to read, and the census already said so.
      gitn -C "$2" rev-parse --git-dir >/dev/null 2>&1 || return 0
      base="$(gitn -C "$2" hash-object -t tree /dev/null 2>/dev/null)" || base=""
      if [ -z "$base" ]; then
        perte_perimetre 1 "git index of a repository not read (no empty tree)"
        return 0
      fi
      gitn -C "$2" diff-index --cached -z --no-renames "$base" -- > "$WORKD/ls" 2>/dev/null; rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
      perte_perimetre 1 "git index of a repository not read (diff-index failed)"
      return 0
    fi
    : > "$cand"
    # rec = ":<old mode> <new mode> <old sha> <new sha> <status>", then the path.
    while IFS= read -r -d '' rec && IFS= read -r -d '' p; do
      rest="${rec#* }"; mode="${rest%% *}"
      rest="${rest#* }"; rest="${rest#* }"
      sha="${rest%% *}"; stg="${rest#* }"
      case "$stg" in
        D*|U*)
          continue ;;
      esac
      case "$mode" in
        100644|100755|120000)
          printf '%s\0%s\0' "$sha" "$3$p" >> "$cand"; n=$((n + 1)) ;;
        040000)
          vide=$((vide + 1)) ;;
      esac
    done < "$WORKD/ls"
    if [ "$vide" -gt 0 ]; then
      perte_perimetre "$vide" "sparse-index directory entr(y|ies) not expanded"
    fi
  fi
  printf '%s\0%s\0%s\0%s\0' "$_grp" "$1" "$2" "$3" >> "$IDXGROUPS"
  _idx_n=$((_idx_n + n))
}

# index_injoignables: each submodule enumerate_submodules found INITIALIZED BUT
# UNREACHABLE (its directory exists and cannot be searched) is read through its
# git dir — name from the parent's .gitmodules (`config -z`: a name may carry
# dots or spaces), git dir from `rev-parse --git-path modules/<name>`, both
# checked by gitdir_sur (K1). Its WORKING TREE stays unread (DEGRADED); a git
# dir unreadable or absent (a `.git` DIRECTORY inside the submodule, never
# absorbed, sits under the unreadable directory) is DEGRADED with "content may
# already be committed", and so are the submodules nested under it (counted,
# not descended: their name lives in an index this gate does not resolve).
index_injoignables() {
  local repo path sub_rel rec key val name gd cm rgd rcm lus=0 sans_dir=0 noms=0
  [ -n "$WORKD" ] && [ -n "$SUBUNREACH" ] && [ -s "$SUBUNREACH" ] || return 0
  while IFS= read -r -d '' repo && IFS= read -r -d '' path && IFS= read -r -d '' sub_rel; do
    name=""
    gitn config -z -f "$repo/.gitmodules" --get-regexp '^submodule\..*\.path$' > "$WORKD/gm" 2>/dev/null
    while IFS= read -r -d '' rec; do
      key="${rec%%$'\n'*}"; val="${rec#*$'\n'}"
      if [ "$val" = "$path" ]; then
        name="${key#submodule.}"; name="${name%.path}"
        break
      fi
    done < "$WORKD/gm"
    gd=""; cm=""
    if [ -n "$name" ]; then
      gd="$(gitn -C "$repo" rev-parse --git-path "modules/$name" 2>/dev/null)" || gd=""
      cm="$(gitn -C "$repo" rev-parse --git-common-dir 2>/dev/null)" || cm=""
    fi
    case "$gd" in
      ''|/*|[A-Za-z]:/*)
        : ;;
      *)
        gd="$repo/$gd" ;;
    esac
    case "$cm" in
      ''|/*|[A-Za-z]:/*)
        : ;;
      *)
        cm="$repo/$cm" ;;
    esac
    if [ -z "$gd" ] || [ ! -d "$gd" ] || [ ! -r "$gd" ] || [ ! -x "$gd" ]; then
      sans_dir=$((sans_dir + 1))
      continue
    fi
    rgd="$(cd "$gd" 2>/dev/null && pwd -P)" || rgd=""
    rcm="$(cd "$cm" 2>/dev/null && pwd -P)" || rcm=""
    if ! gitdir_sur "$name" "$rgd" "$rcm"; then
      noms=$((noms + 1))
      continue
    fi
    index_candidats G "$rgd" "$sub_rel/"
    lus=$((lus + 1))
  done < "$SUBUNREACH"
  if [ "$lus" -gt 0 ]; then
    perte_perimetre "$lus" "unreachable submodule(s): working tree not read (index read)"
  fi
  if [ "$sans_dir" -gt 0 ]; then
    perte_perimetre "$sans_dir" "unreachable submodule(s) whose git dir is unreadable or absent — content may already be committed"
  fi
  if [ "$noms" -gt 0 ]; then
    perte_perimetre "$noms" "unreachable submodule(s) whose .gitmodules name is unsafe (absolute, '..' or outside modules/) — git dir not opened, content may already be committed"
  fi
  if [ "$_imbriques" -gt 0 ]; then
    perte_perimetre "$_imbriques" "nested submodule(s) under an unreachable submodule not read — content may already be committed"
  fi
}

# garde_enfant <cmd…>: runs ONE writer of the index copy in the BACKGROUND, its
# pid in _LECTEUR, and waits for it. Measured by the exec-critic on 02ec9e97: a
# SIGTERM to this shell ALONE left the python reader orphaned; it recreated
# $STAGE/.gl-index.*/ after the cleanup and wrote the key's blob there, which
# stayed in TMPDIR. on_exit now kills and reaps _LECTEUR BEFORE removing any
# directory, and the reader never recreates its destination (layered: each
# defense alone masks the other — the combined mutant M17 reddens (trr17)).
garde_enfant() {
  local rc
  "$@" &
  _LECTEUR=$!
  wait "$_LECTEUR"; rc=$?
  _LECTEUR=""
  return "$rc"
}

# lire_index: AFTER the stage of the tree. (1) A tracked file of a REACHABLE
# submodule that could not be read in the tree is re-read from THAT submodule's
# index (a submodule's perimeter is all its tracked content, T-00000293),
# assigned to the DEEPEST submodule holding it. (2) Every group is read RAW
# into $IDX. What was written joins `staged`; what was not is a counted loss.
# Bounded by GITLEAKS_TIMEOUT for the whole read: python kills git at its own
# deadline; without python each `cat-file blob` runs under timeout(1) with the
# time left, and a loop that has neither is SAID unbounded.
lire_index() {
  local grp kind loc pfx f best bestg p x y tot=0 _w=0 _d=0 manque out rc l sha tmo _fin _rest _dit=0 _vu _es _ep _paress=0
  local -a ga pre paths
  [ -n "$WORKD" ] && [ -n "$IDXGROUPS" ] && [ -s "$IDXGROUPS" ] || return 0
  if [ -n "$FAILLIST" ] && [ -s "$FAILLIST" ]; then
    while IFS= read -r -d '' f; do
      best=""; bestg=""
      while IFS= read -r -d '' grp && IFS= read -r -d '' kind && IFS= read -r -d '' loc && IFS= read -r -d '' pfx; do
        if [ "$kind" = C ] && [ -n "$pfx" ] && [ "${#pfx}" -gt "${#best}" ]; then
          case "$f" in
            "$pfx"?*)
              best="$pfx"; bestg="$grp" ;;
          esac
        fi
      done < "$IDXGROUPS"
      if [ -n "$bestg" ]; then
        printf '%s\0' "${f#"$best"}" >> "$WORKD/f.$bestg"
      fi
    done < "$FAILLIST"
    while IFS= read -r -d '' grp && IFS= read -r -d '' kind && IFS= read -r -d '' loc && IFS= read -r -d '' pfx; do
      [ -s "$WORKD/f.$grp" ] || continue
      paths=()
      while IFS= read -r -d '' p; do
        paths+=("$p")
      done < "$WORKD/f.$grp"
      gitn --literal-pathspecs -C "$loc" ls-files -s -z -- ${paths[@]+"${paths[@]}"} > "$WORKD/ls" 2>/dev/null; rc=$?
      if [ "$rc" -ne 0 ]; then
        perte_perimetre "${#paths[@]}" "unreadable submodule file(s) not re-read from its index (ls-files failed)"
        continue
      fi
      index_ls_s "$WORKD/ls" "$pfx" "$WORKD/c.$grp"
    done < "$IDXGROUPS"
  fi
  while IFS= read -r -d '' grp && IFS= read -r -d '' kind && IFS= read -r -d '' loc && IFS= read -r -d '' pfx; do
    while IFS= read -r -d '' x && IFS= read -r -d '' y; do
      tot=$((tot + 1))
    done < "$WORKD/c.$grp"
  done < "$IDXGROUPS"
  [ "$tot" -gt 0 ] || return 0
  IDX="$(mktemp -d "$STAGE/.gl-index.XXXXXX" 2>/dev/null)" || IDX=""
  if [ -z "$IDX" ]; then
    perte_perimetre "$tot" "index entries not read (no index directory)"
    return 0
  fi
  IDXNAME="${IDX##*/}"
  : > "$WORKD/ecrits"
  tmo="${GITLEAKS_TIMEOUT:-90}"
  case "$tmo" in
    ''|*[!0-9]*)
      tmo=90 ;;
  esac
  _fin=$((SECONDS + tmo))
  while IFS= read -r -d '' grp && IFS= read -r -d '' kind && IFS= read -r -d '' loc && IFS= read -r -d '' pfx; do
    [ -s "$WORKD/c.$grp" ] || continue
    if [ "$kind" = G ]; then
      ga=(--git-dir="$loc" --work-tree="$IDX")
    else
      ga=(-C "$loc")
    fi
    # A partial clone under a git that cannot refuse a lazy fetch (paresseux):
    # no cat-file at all — its entries are a counted loss, never a fetch.
    if paresseux ${ga[@]+"${ga[@]}"}; then
      while IFS= read -r -d '' sha && IFS= read -r -d '' p; do
        _paress=$((_paress + 1))
      done < "$WORKD/c.$grp"
      continue
    fi
    _rest=$((_fin - SECONDS))
    [ "$_rest" -gt 0 ] || break
    if [ -n "$PY" ]; then
      : > "$WORKD/lu"
      garde_enfant "$PY" -I -c "$LIRE_INDEX_PY" "$_rest" "$IDX" "$WORKD/c.$grp" ${GITN[@]+"${GITN[@]}"} ${ga[@]+"${ga[@]}"} > "$WORKD/lu" 2>/dev/null
      while IFS= read -r l; do
        case "$l" in
          w*)
            _w=$((_w + 1)) ;;
          d*)
            _d=$((_d + 1)) ;;
        esac
      done < "$WORKD/lu"
      continue
    fi
    pre=()
    if have timeout; then
      pre=(timeout 1)
    elif [ "$_dit" = 0 ]; then
      deg "COVERAGE DEGRADED: index read unbounded (no timeout(1), no python) — a blocked git call is not bounded"
      _dit=1
    fi
    while IFS= read -r -d '' sha && IFS= read -r -d '' p; do
      _rest=$((_fin - SECONDS))
      [ "$_rest" -gt 0 ] || break
      case "/$p/" in
        *"/../"*|*"/./"*|*"//"*|*"\\"*)
          continue ;;
      esac
      if [ -e "$IDX/$p" ] || [ -L "$IDX/$p" ]; then
        # SAME rule as the python reader: read ONLY if this run already wrote
        # the same sha at this very path (its register, "$WORKD/ecrits");
        # anything else — a case or Unicode-normalization collision on an
        # insensitive file system, identical content included — is a loss,
        # counted by `manque`. No hash of the file: no filter can intervene.
        _vu=0
        while IFS= read -r -d '' _es && IFS= read -r -d '' _ep; do
          if [ "$_ep" = "$p" ] && [ "$_es" = "$sha" ]; then
            _vu=1
            break
          fi
        done < "$WORKD/ecrits"
        [ "$_vu" = 1 ] && _d=$((_d + 1))
        continue
      fi
      case "$p" in
        */*)
          garde_enfant mkdir -p "$IDX/${p%/*}" 2>/dev/null || continue ;;
      esac
      if [ "${#pre[@]}" -gt 0 ]; then
        pre=(timeout "$_rest")
      fi
      if garde_enfant ${pre[@]+"${pre[@]}"} ${GITN[@]+"${GITN[@]}"} ${ga[@]+"${ga[@]}"} cat-file blob "$sha" > "$IDX/$p" 2>/dev/null; then
        _w=$((_w + 1))
        printf '%s\0%s\0' "$sha" "$p" >> "$WORKD/ecrits"
      fi
    done < "$WORKD/c.$grp"
  done < "$IDXGROUPS"
  manque=$((tot - _w - _d - _paress))
  _depuis_index=$((_depuis_index + _w))
  staged=$((staged + _w))
  if [ "$manque" -gt 0 ]; then
    perte_perimetre "$manque" "index entries not read (cat-file failed or timed out, or two index paths collided on this file system: case or Unicode normalization)"
  fi
  if [ "$_paress" -gt 0 ]; then
    perte_perimetre "$_paress" "index entries not read (partial clone, git < 2.45: a missing blob would be fetched, running the remote's uploadpack)"
  fi
}

STAGE=""; REPORT=""; LOCFILE=""; LIST=""; _TMP_FN=""; _TMP_SW=""; CEN_RAW=""; CEN_SORTED=""
cleanup() {
  # Only the shell that INSTALLED this trap may run it: a background child that
  # inherits the EXIT trap and is killed before it finishes exec'ing fires the
  # trap too, and would delete this run's staging while it is still scanning.
  # $$ cannot tell parent from child; $BASHPID can. Same guard as verify.sh's
  # lock_release (LOCK_HOLDER); degrades to inert on a bash 3.x without BASHPID.
  [ "${BASHPID:-$$}" = "$CLEANUP_OWNER" ] || return 0
  # 2>/dev/null: on the timeout path the killed scanner can still hold a staged
  # file open ("Device or resource busy"), and a hook must not spew about its
  # own temp dir — TMPDIR reclaims it. The staging is never load-bearing.
  [ -n "$STAGE" ]   && rm -rf "$STAGE" 2>/dev/null
  [ -n "$REPORT" ]  && rm -f "$REPORT" 2>/dev/null
  [ -n "$LOCFILE" ] && rm -f "$LOCFILE" 2>/dev/null
  [ -n "$LIST" ]    && rm -f "$LIST" 2>/dev/null
  # The census work files (T-01M4Y09EY4M664896DMGDTMDXF, security review), read
  # through `:-` so that the (h) arm, which feeds the four variables above,
  # still runs this body under set -u.
  [ -n "${_TMP_FN:-}" ] && rm -f "$_TMP_FN" 2>/dev/null
  [ -n "${_TMP_SW:-}" ] && rm -f "$_TMP_SW" 2>/dev/null
  [ -n "${CEN_RAW:-}" ] && rm -f "$CEN_RAW" 2>/dev/null
  [ -n "${CEN_SORTED:-}" ] && rm -f "$CEN_SORTED" 2>/dev/null
  return 0
}
CLEANUP_OWNER="${BASHPID:-$$}"
# on_exit wraps cleanup() rather than growing it: the (h) arm of the suite
# extracts cleanup() by name and feeds it four of its eight variables (the four
# census work files are read with a default). Same owner guard, for the same reason — a
# killed child must neither print nor delete.
DEFCFG=""
SCAN_CWD=""   # the EMPTY directory gitleaks runs from (T-00000844), removed below
SCAN_SRC="."; SCAN_PFX=""   # posed here: read on paths set -u must survive
on_exit() {
  local exit_rc=$?
  if [ "${BASHPID:-$$}" = "$CLEANUP_OWNER" ]; then
    # FIRST: a writer of the index copy still running (a SIGTERM to this shell
    # alone) is killed and reaped before any directory is removed (garde_enfant).
    [ -n "${_LECTEUR:-}" ] && { kill "$_LECTEUR" 2>/dev/null; wait "$_LECTEUR" 2>/dev/null; }
    if [ "$MODE" = diff ] && [ "$exit_rc" -eq 0 ] && [ -n "$DEGFILE" ] && [ -s "$DEGFILE" ]; then
      emit_system_message
    elif [ -n "$FINAL_OUT" ]; then
      printf '%s\n' "$FINAL_OUT"
    fi
    [ -n "$DEGFILE" ] && rm -f "$DEGFILE" 2>/dev/null
    [ -n "$DEFCFG" ] && rm -f "$DEFCFG" 2>/dev/null
    # The index pass's work directory, when a signal (SIGTERM runs this trap,
    # measured on bash 3.2 and 5) stops the run before its in-line removal.
    [ -n "${WORKD:-}" ] && rm -rf "$WORKD" 2>/dev/null
    if [ -n "$SCAN_CWD" ] && [ "$SCAN_CWD" != "$STAGE" ]; then
      rm -rf "$SCAN_CWD" 2>/dev/null
    fi
  fi
  cleanup
}
trap on_exit EXIT

# ---- Stage everything to scan under ONE root, then scan it in ONE spawn ------
# gitleaks takes a single --source and costs ~0.5 s of process start-up per
# invocation, so the previous one-spawn-per-file loop made the Stop hook grow
# with the working tree: `git diff HEAD` + untracked only ever grows until a
# commit lands, and 20 dirty files measured 9.3 s against 0.53 s for a single
# spawn over the same 20 (T-gitleaks-perf). The staging copy is what makes one
# spawn possible while keeping the scan scoped to the diff — pointing --source
# at $ROOT instead would drag in the whole repo, node_modules included.
#
# Relative paths are MIRRORED inside the stage, so the report's `File` field is
# already the display path in both modes — no translation table needed.
# mktemp -d gives an unpredictable 0700 directory: no symlink/TOCTOU hijack of
# files that briefly hold a potential secret (CWE-59/377).
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-stage.XXXXXX")"
staged=0
# CENSUS_OK — "the file list was actually BUILT", distinct from "the file list is
# empty". They used to be the same observable: the census was a `{ git…; git…; }
# | sort -u` whose rc nobody read, so a failing element (measured: `sort` off
# PATH) left staged=0 and the run took the "clean working tree" branch — two
# files carrying keys reported CLEAN + exit 0. Harmless while it only meant a
# missing scan; NOT harmless once that branch also prints "fallback scan: 0
# file(s) scanned, 0 finding(s)", which a consumer reads as "the fallback ran to
# the end, all clear". "Empty diff" and "nothing could be enumerated" are
# not the same state, so they no longer print the same marker. Default 1: the
# --content mode never runs a census, and its single staged payload IS the truth.
# Since T-01M4X7Q1RR7WPF1GWYFEFHDDM9, 1 means "enumerated AND entirely read": a
# path git lists but this gate could not read (perte_perimetre) poses 0 too.
CENSUS_OK=1
# Posed HERE, outside every branch, like ENGINE/IGN_SEEN: read under set -u on
# paths --content also takes. The four CENSUS_* texts are the sinks' default
# wording, byte for byte; perte_perimetre rewrites them on the first loss.
_non_copies=0; _depuis_index=0; _injoignables=0; _listes=0; _idx_n=0
_grp=0; _imbriques=0; _ls_n=0; _ls_liens=0; _LECTEUR=""; _ign_ill=0
NEUTRES=(); _neutres_ok=0
IDX=""; IDXNAME=""; WORKD=""; FAILLIST=""; SUBUNREACH=""; IDXGROUPS=""
CENSUS_WHY="file census FAILED (git diff / ls-files / sort)"
CENSUS_MARK="file census failed"
CENSUS_TAIL0="nothing was enumerated, so nothing was scanned"
CENSUS_TAIL0M="nothing enumerated"

if [ "$MODE" = "content" ]; then
  # Slurp stdin verbatim. The payload may be raw text or a whole hook event
  # JSON — gitleaks scans the text either way, so a secret in tool_input.content
  # is still caught. Named `stdin` so that is what the audit location reads.
  cat > "$STAGE/stdin"
  staged=1
else
  # The file list is collected first and POPULATED IN ONE BATCH below. A
  # per-file `dirname`+`mkdir -p`+`cp` loop reintroduces the very defect this
  # rewrite removes: on Windows those are three process spawns per file, which
  # measured 4.5 s for 30 files — the staging would have grown with the working
  # tree just as the scan used to. One `tar` pipeline does the same work in
  # ~0.1 s and recreates the directory structure on its own. NUL-separated, so
  # paths with spaces survive.
  LIST="$(mktemp "${TMPDIR:-/tmp}/gitleaks-list.XXXXXX")"
  # The temporaries of T-01M4X7Q1RR7WPF1GWYFEFHDDM9 live in ONE work directory
  # BESIDE the stage, never in it (the stage is what gets scanned, and it is
  # replaced whole when tar fails), removed in line right after the index pass
  # and before the DECLINED exit: cleanup() keeps its four (h)-fed variables, the
  # census files beside them are read with a default.
  WORKD="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-work.XXXXXX" 2>/dev/null)" || WORKD=""
  CEN_ERR=/dev/null
  if [ -n "$WORKD" ]; then
    FAILLIST="$WORKD/failed"; SUBUNREACH="$WORKD/unreachable"; IDXGROUPS="$WORKD/groups"
    CEN_ERR="$WORKD/others.err"
    : > "$FAILLIST"; : > "$SUBUNREACH"; : > "$IDXGROUPS"
  else
    perte_perimetre "?" "index entries and unreadable paths not read (no work directory)"
  fi
  if gitn -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
    # Each step writes to a FILE and its rc is read ON THE SPOT — never `$?`
    # behind a pipe, which is what hid the failure before: in `{ a; b; } | sort`
    # only `sort`'s rc is visible without pipefail gymnastics, and nobody read it
    # at all. Three commands, three rcs, one flag. The temps are removed right
    # after the read loop; a signal before that is covered by cleanup(), which
    # reads them with a default so that the (h) arm still feeds it four
    # variables (T-01M4Y09EY4M664896DMGDTMDXF: their window now spans config
    # reads and git calls, and a SIGINT left two path lists in TMPDIR).
    # NUL-separated end to end (T-01M4Y09EY4M664896DMGDTMDXF): without -z git
    # QUOTES a path carrying a non-ASCII byte, a quote, a backslash or a control
    # character (`"n\303\251.txt"`), which failed the existence test below and
    # was dropped as if absent — measured: a key in `né.txt` read "nothing to
    # scan", rc 0. Sorted in BYTES (C locale): a UTF-8 collation folds two
    # distinct names (`a.txt` and `a<U+200B>.txt`) into one under `sort -u`.
    CEN_RAW="$(mktemp "${TMPDIR:-/tmp}/gitleaks-census.XXXXXX")"
    CEN_SORTED="$(mktemp "${TMPDIR:-/tmp}/gitleaks-census.XXXXXX")"
    # The diff runs no code of the repository (T-01M4Y09EY4M664896DMGDTMDXF):
    # gitn (fsmonitor, hooks), every filter driver emptied by filtres_neutres —
    # when that fails the diff is NOT run and the loss is said —, no external
    # diff, no textconv, no stat-only refresh (that refresh reads the content of
    # every stat-dirty file through its filter, and in a partial clone fetches
    # its blob — and so does a RACY entry under core.autocrlf / text=auto, refresh
    # off (has_crlf_in_index, measured: the export, or the paresseux skip, is
    # what closes that one): the price is a stat-dirty file listed and scanned,
    # never a file lost), and a submodule's working tree is not opened (its `git status`
    # child ran the submodule's own filters and fsmonitor; a gitlink replaced
    # by a regular file is still listed). `--` after HEAD: a file named HEAD at
    # the root made the revision ambiguous, rc 128 (measured).
    # A partial clone under a git that cannot refuse a lazy fetch (paresseux):
    # the diff is NOT run either — a loss said, never an execution.
    _TMP_FN="$(mktemp "${TMPDIR:-/tmp}/gitleaks-filters.XXXXXX" 2>/dev/null)" || _TMP_FN=""
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
    if paresseux -C "$ROOT"; then
      perte_perimetre "?" "tracked modified file(s) not enumerated (partial clone, git < 2.45: a missing blob would be fetched, running the remote's uploadpack)"
    elif [ "$_neutres_ok" = 1 ]; then
      gitn -c diff.autoRefreshIndex=false ${NEUTRES[@]+"${NEUTRES[@]}"} -C "$ROOT" diff --name-only -z --no-renames --no-ext-diff --no-textconv --ignore-submodules=dirty HEAD -- > "$CEN_RAW" 2>/dev/null || CENSUS_OK=0
    else
      perte_perimetre "?" "tracked modified file(s) not enumerated (a filter driver could not be neutralized)"
    fi
    # stderr KEPT (T-01M4X7Q1RR7WPF1GWYFEFHDDM9): git exits 0 on a directory it
    # cannot open and says so in ONE warning line — the untracked files under it
    # were never listed. Its text is localized and never parsed: lines counted.
    # The sparse-index advice is switched off on THIS call only: expanding a
    # sparse index for an untracked file outside the cone printed 8 advice
    # lines, counted as 8 unreadable directories — a false DEGRADED at every
    # Stop (measured on the base).
    gitn -c advice.sparseIndexExpanded=false -C "$ROOT" ls-files --others --exclude-standard -z >> "$CEN_RAW" 2>"$CEN_ERR" || CENSUS_OK=0
    ignores_illisibles "$ROOT"
    # K2 — assume-unchanged entries (lowercase tag of `ls-files -v`): git never
    # compares their working-tree copy, so `diff --name-only` does not list a
    # secret written there. Added to the census like any dirty file (copied and
    # scanned when readable, a counted loss when not); the byte sort below folds
    # a path listed twice. The tag is matched against a closed list of lowercase
    # letters (no range: locale-free). skip-worktree (uppercase S) is the normal
    # state of every sparse checkout and is not added (bound written in the
    # README); `s` (skip-worktree AND assume-unchanged) is.
    gitn -C "$ROOT" ls-files -v -z > "$CEN_SORTED" 2>/dev/null || CENSUS_OK=0
    while IFS= read -r -d '' rec; do
      case "$rec" in
        [hsmrck]" "*)
          printf '%s\0' "${rec#??}" >> "$CEN_RAW" ;;
      esac
    done < "$CEN_SORTED"
    LC_ALL=C sort -u -z "$CEN_RAW" > "$CEN_SORTED" 2>/dev/null || CENSUS_OK=0
    while IFS= read -r -d '' f; do
      [ -n "$f" ] || continue
      if [ ! -f "$ROOT/$f" ]; then
        # Not a regular file: a directory or gitlink that EXISTS (its content
        # has its own pass), a path really deleted, or a path under a directory
        # this gate cannot search — only the last is a loss: counted, never clean.
        if [ ! -e "$ROOT/$f" ] && injoignable "$ROOT" "$f"; then
          _injoignables=$((_injoignables + 1))
          [ -n "$FAILLIST" ] && printf '%s\0' "$f" >> "$FAILLIST"
        fi
        continue
      fi
      printf '%s\0' "$f" >> "$LIST"
      staged=$((staged + 1))
    done < "$CEN_SORTED"
    rm -f "$CEN_RAW" "$CEN_SORTED"; CEN_RAW=""; CEN_SORTED=""
    if [ -s "$CEN_ERR" ]; then
      _n_err="$(wc -l < "$CEN_ERR" | tr -d ' ')"
      [ "${_n_err:-0}" -gt 0 ] 2>/dev/null || _n_err=1
      perte_perimetre "$_n_err" "warning line(s) from git ls-files --others (an unreadable directory hides its untracked files)"
    fi
  else
    # A census that NEVER RAN is not an empty diff — and the `if` above is what
    # decides between them, so the flag has to be posed on BOTH sides or the
    # optimistic default silently covers the skip. Measured on a repo with no
    # commit (`rev-parse HEAD` rc=128) carrying a live sk-ant- key in an
    # untracked file: the whole block is skipped, INCLUDING the `ls-files
    # --others` that would have listed exactly that file, staged stays 0, and the
    # run took the "clean working tree" branch — verdict CLEAN, exit 0, and under
    # the fallback the liberation marker `0 file(s) scanned, 0 finding(s)` that
    # a consumer reads as a completed sweep. Same false green as a census that
    # ran and FAILED, reached by the other door. Also covers a ROOT that is not a
    # git repo at all: nothing could be enumerated there either.
    CENSUS_OK=0
  fi
  # T-00000293: extend the perimeter with the content of INITIALIZED submodules.
  # For each submodule S, add its tracked ∪ untracked files as SUPERPROJECT-
  # relative paths `S/f`, each passing the SAME `[ -f ]` existence filter as the
  # base list (C1 it.2: a tracked-but-deleted file would break the tar batch and
  # force the slow per-file staging). tracked and untracked are disjoint by
  # definition, so no dedup is needed. All paths stay in ONE $LIST => still a
  # SINGLE gitleaks spawn (pin (e)). Zero submodule => zero extra bytes (silence,
  # octet-for-octet unchanged). NUL-safe throughout.
  while IFS= read -r -d '' sub_rel; do
    while IFS= read -r -d '' subf; do
      [ -n "$subf" ] || continue
      rel="$sub_rel/$subf"
      if [ ! -f "$ROOT/$rel" ]; then
        # Same three cases as the root census; an unreachable path of a
        # submodule is re-read from ITS index by lire_index (FAILLIST).
        if [ ! -e "$ROOT/$rel" ] && injoignable "$ROOT" "$rel"; then
          _injoignables=$((_injoignables + 1))
          [ -n "$FAILLIST" ] && printf '%s\0' "$rel" >> "$FAILLIST"
        fi
        continue
      fi
      printf '%s\0' "$rel" >> "$LIST"
      staged=$((staged + 1))
    done < <( gitn -C "$ROOT/$sub_rel" ls-files -z 2>/dev/null; \
              gitn -C "$ROOT/$sub_rel" ls-files --others --exclude-standard -z 2>/dev/null )
    ignores_illisibles "$ROOT/$sub_rel"
    index_candidats C "$ROOT/$sub_rel" "$sub_rel/"
  done < <(enumerate_submodules "$ROOT" "" 0)
  if [ "$_injoignables" -gt 0 ]; then
    perte_perimetre "$_injoignables" "listed path(s) unreachable in the working tree (a parent directory is not searchable)"
  fi
  if [ "$_ign_ill" -gt 0 ]; then
    perte_perimetre "$_ign_ill" "skip-worktree .gitignore file(s) unreadable (partial clone) — untracked files they re-include may be missed"
  fi
  # Here `staged` is the complete count of the TREE census, root and submodules.
  _listes=$staged
  # The INDEX perimeter, counted BEFORE the bound (written after the tree stage).
  index_candidats C "$ROOT" ""
  index_injoignables
  # Staging bound, fallback ONLY (C9): the tar/copy below is what costs the >5 min
  # measured on a tree with a broken .gitignore; the census above is a shell loop
  # over names, assumed under the bound. DECLINED carries no " file(s) scanned, "
  # so a consumer reads it DEGRADED (nothing scanned end-to-end). The gitleaks
  # path is untouched — it keeps its own scan timeout at l.242. The index
  # candidates count toward the bound; `staged` itself stays the tree's count.
  fb_max="${GITLEAKS_FALLBACK_MAX_FILES:-5000}"
  # the bound is on the LARGER of the two sets, never their sum (critic-opus F2).
  _a_lire=$staged; [ "$_idx_n" -gt "$_a_lire" ] && _a_lire=$_idx_n
  if [ "$ENGINE" = fallback ] && [ "$_a_lire" -gt "$fb_max" ]; then
    [ -n "$WORKD" ] && rm -rf "$WORKD" 2>/dev/null; WORKD=""
    deg "COVERAGE DEGRADED: fallback declines $_a_lire staged file(s) ($staged tree file(s) / $_idx_n index entries) > GITLEAKS_FALLBACK_MAX_FILES=$fb_max (ignore defect? check .gitignore for build output)"
    echo "fallback scan: DECLINED ($_a_lire staged file(s) — $staged tree / $_idx_n index — > GITLEAKS_FALLBACK_MAX_FILES=$fb_max)" >&2
    audit "DEGRADED" 0 "[]"
    emit_scan degraded 0 "[]"
    exit 0
  fi
  if [ "$staged" -gt 0 ]; then
    # `if ! { … ; }` est du bash valide que tree-sitter-bash NE PARSE PAS — la
    # cause exacte est le `!` DEVANT un groupe d'accolades (sans le `!`, ou
    # sans les accolades, le parse passe ; le pipeline n'y est pour rien).
    # Un seul site retire ce fichier ENTIER du compte des cibles inspectées par
    # la porte SAST. Le groupe reste un groupe — même shell, aucun sous-shell —
    # seul le `!` sort, remplacé par un relevé de statut. Équivalence vérifiée
    # dans les deux sens, et ce script tourne sous `set -uo pipefail`, sans
    # `-e` : aucune interaction avec errexit.
    _copie_ok=1
    { have tar && tar -cf - -C "$ROOT" --null --files-from="$LIST" 2>/dev/null \
        | tar -xf - -C "$STAGE" 2>/dev/null; } || _copie_ok=0
    if [ "$_copie_ok" -eq 0 ]; then
      # No tar (or a tar that chokes): fall back to the per-file copy. Slower and
      # linear in the file count, but correctness never depends on tar.
      # A tar that CHOKES (one unreadable file: GNU rc 2, bsdtar rc 1) has
      # already extracted the rest — links included. Measured (ESC, CWE-59): an
      # untracked relative link `lnk -> ../escape-target` extracted there, then
      # `cp` of the same path wrote THROUGH it, outside the stage, into an
      # existing file. So the copy starts over in a FRESH stage (same template,
      # same parent: SCAN_CWD's check compares the parents), and a link is never
      # copied — parity with tar, which archives a link as a link: its target
      # is not read. A file that cannot be copied is COUNTED, never skipped.
      STAGE2="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-stage.XXXXXX" 2>/dev/null)" || STAGE2=""
      if [ -z "$STAGE2" ]; then
        perte_perimetre "$staged" "files not staged (no fresh stage directory)"
        staged=0
      else
        rm -rf "$STAGE" 2>/dev/null; STAGE="$STAGE2"
        staged=0
        while IFS= read -r -d '' f; do
          [ -L "$ROOT/$f" ] && continue
          case "$f" in
            */*)
              if ! mkdir -p "$STAGE/${f%/*}" 2>/dev/null; then
                _non_copies=$((_non_copies + 1))
                [ -n "$FAILLIST" ] && printf '%s\0' "$f" >> "$FAILLIST"
                continue
              fi
              ;;
          esac
          if ! cp "$ROOT/$f" "$STAGE/$f" 2>/dev/null; then
            _non_copies=$((_non_copies + 1))
            [ -n "$FAILLIST" ] && printf '%s\0' "$f" >> "$FAILLIST"
            continue
          fi
          staged=$((staged + 1))
        done < "$LIST"
      fi
    fi
  fi
  # The INDEX perimeter, written now that the tree is staged (index_candidats).
  lire_index
  if [ "$_non_copies" -gt 0 ]; then
    perte_perimetre "$_non_copies of $_listes" "enumerated file(s) unreadable in the working tree ($_depuis_index index entr(y|ies) read instead)"
  fi
  [ -n "$WORKD" ] && rm -rf "$WORKD" 2>/dev/null; WORKD=""
fi

if [ "$staged" -eq 0 ] && [ "$CENSUS_OK" = 0 ]; then
  # staged=0 because the census FAILED, not because the tree is clean. No
  # "nothing to scan", no liberation marker: `DEGRADED` carries no
  # " file(s) scanned, ", so a consumer reads it DEGRADED instead of
  # complete. Still exit 0 — a benign path never blocks a hook (l.32).
  deg "COVERAGE DEGRADED: $CENSUS_WHY — $CENSUS_TAIL0"
  echo "fallback scan: DEGRADED ($CENSUS_MARK — $CENSUS_TAIL0M)" >&2
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

if [ "$staged" -eq 0 ]; then
  FINAL_OUT="gitleaks-scan: nothing to scan (clean working tree)."   # printed by on_exit
  # An empty diff under the fallback is a COMPLETE, empty scan — the marker lets
  # a consumer read it as complete instead of DEGRADED. Reached
  # only with CENSUS_OK=1 (branch above), i.e. the list was BUILT and is empty.
  [ "$ENGINE" = fallback ] && echo "fallback scan: 0 file(s) scanned, 0 finding(s)" >&2
  audit "CLEAN" 0 "[]"
  emit_scan skipped 0 "[]"
  exit 0
fi

# ---- One scan over the stage; accumulate count + redacted locations ----------
REPORT="$(mktemp "${TMPDIR:-/tmp}/gitleaks.XXXXXX")"
LOCFILE="$(mktemp "${TMPDIR:-/tmp}/gitleaks-loc.XXXXXX")"
total=0

# Hard wall-clock bound on the scan. The staged list is `git diff HEAD` plus
# untracked-and-not-ignored, so it grows with whatever the working tree fails
# to IGNORE — not with what the session touched. Measured 2026-08-19 on a
# consumer repo whose .gitignore had lost its build/ and out/ rules: 45 027
# files in that list and a Stop hook running past FIVE MINUTES every turn,
# against 344 files and 5.9 s once the rules were restored. The root cause
# belongs in .gitignore, but a gate that can hang is a gate its pilot will
# switch off, so the scan is bounded here as well. A timeout is DEGRADED —
# never a block, never a silent pass — and it PRINTS THE COUNT, which is what
# makes an ignore defect visible instead of merely slow. Without timeout(1) on
# PATH the bound cannot be applied: that is said out loud rather than assumed.
GITLEAKS_TIMEOUT="${GITLEAKS_TIMEOUT:-90}"
if [ "$ENGINE" = fallback ]; then
  # rc is read at l.254/l.263 below; _fallback_scan sets $total/$SCAN_STATUS and
  # either exits (kill-switch/timeout/error/0-findings) or hands back on a
  # retained finding, which the shared l.327 path turns into exit 2.
  rc=0
  _fallback_scan
else
# ---- The exception register must LOAD, or it is set aside (T-00000844) -----
# A corrupt .gitleaks.toml made `gitleaks detect --config` exit 1 WITHOUT a
# report; the rc-1 guard below read that DEGRADED, exit 0 — so ONE agent Edit
# of the allowlist switched class-0 off, at the Stop AND at PreToolUse --content
# (measured, gitleaks 8.30.1). Pilot decision 2026-09-30: an unreadable config
# is SET ASIDE, SAID, and the scan runs on the DEFAULT rules — a real secret is
# BLOCKED; the price, written: every false positive the file exempted blocks
# again until the pilot repairs it.
#
# THE CHECK, AFTER THE SCAN AND ONLY WHEN IT FAILED (pilot, 2026-09-30): a
# first design checked the config BEFORE every scan and cost ~0.24 s on every
# Edit/Write and every Stop (0.45 -> 0.69 s median, --content). An unreadable
# config has ONE signature on the scan itself — an rc other than 0 and 1, or rc 1
# with NO readable finding (no `"StartLine"` in the report, the same criterion
# the counting below uses) — so the check runs only then. Same verdicts; a valid
# config pays nothing. The check: the same gitleaks, the same config resolution,
# over an EMPTY directory (mktemp -d). Measured on 8.30.1: rc 0 for a loadable
# config (the kit's own, a bare `[extend] useDefault`, even an EMPTY file); rc 1
# for broken TOML — via --config, via GITLEAKS_CONFIG, via GITLEAKS_CONFIG_TOML,
# and for a GITLEAKS_CONFIG naming an absent file (which is what a host-exported
# GITLEAKS_CONFIG always is here once l.~89 re-points it, when the project has no
# .gitleaks.toml — the host's own file is never read); rc 2 for a rule whose
# regex does not compile. Any rc != 0 sets the config aside and the stage is
# SCANNED AGAIN on the default rules. With no config at all nothing is checked —
# (e) pins one spawn. A timeout (124/137) is never re-scanned: it is not a config
# signature, and a second run would double the wait.
#
# WHY NOT A BARE `CFG=()` for the default rules: with no --config, gitleaks
# falls back on the env forms, then on a `.gitleaks.toml` at the ROOT OF THE
# SOURCE — and in diff mode the corrupt file IS in the diff, hence STAGED at
# $STAGE/.gitleaks.toml (measured: rc 1 again, the same DEGRADED). An EXPLICIT
# `--config` wins over all three (measured on both env forms), so the default
# rules are passed as a two-line file of our own, outside the stage.
#
# BOUND, said: a config that LOADS but switches rules off (an empty file, a
# config without `[extend] useDefault = true`) passes this check and silences
# the gate — this check reads LOADABILITY, never what the rules cover.
CFG_SRC=""
if [ -f "$GITLEAKS_CONFIG" ]; then
  CFG_SRC="$GITLEAKS_CONFIG"
elif [ -n "$GL_ENV_CONFIG" ]; then
  # The host's value is NEVER what gitleaks reads: l.~89 re-points the exported
  # variable at the absent project file. Both are named, so nobody goes looking
  # for a defect in a file that was not even opened.
  CFG_SRC="GITLEAKS_CONFIG (environment) — host value $GL_ENV_CONFIG, re-pointed by this gate at $GITLEAKS_CONFIG, absent,"
elif [ -n "${GITLEAKS_CONFIG_TOML:-}" ]; then
  CFG_SRC="GITLEAKS_CONFIG_TOML (environment)"
fi
# `${CFG[@]+…}` ET NON `"${CFG[@]}"` (T-00000841) : sous bash 3.2 (le /bin/bash
# de macOS) + `set -u`, un tableau VIDE — pas de .gitleaks.toml — tue le
# sous-shell AVANT gitleaks ; rc 1 sans rapport se lisait « clean ». Mesuré :
# même dépôt, même secret, bash 3.2 rc 0 « clean », bash 5 rc 2 BLOCKED.
HAVE_TIMEOUT=0
if have timeout; then
  HAVE_TIMEOUT=1
else
  deg "COVERAGE DEGRADED: no timeout(1) on PATH — gitleaks runs unbounded over $staged staged file(s)"
fi
# ONE EXCEPTION CHANNEL, THE PILOT'S (T-00000844). gitleaks honours two more,
# both writable by the very agent it scans (measured on 8.30.1):
#   * an inline `gitleaks:allow` comment on the secret's line — exempted (rc 0).
#     `--ignore-gitleaks-allow` turns that off (rc 1 on the same line);
#   * a `.gitleaksignore` of fingerprints, read from the CWD (the -i default,
#     ".") AND from the source root. The CWD is now an empty directory (below),
#     but the source root is still $STAGE, and an explicit `-i <empty dir>` does
#     NOT stop the source-root read (measured: still rc 0).
#     So the staged copy is RENAMED before each scan — NOT deleted: a deletion
#     made a secret written INSIDE that file vanish from the scan (measured by
#     the closing review: rc 0 clean, where the old gate said rc 2). Renamed,
#     its CONTENT is still scanned (reported as `.gitleaksignore.T844`) and its
#     fingerprints are honoured by nobody. The target never overwrites a staged
#     file of the same name (the diff could carry one): a free suffix is taken.
#     In --content mode the stage holds only `stdin`; $ROOT is never the cwd nor
#     the source, so the repo's own `.gitleaksignore` is never read either.
# IGN_SEEN (initialised with ENGINE) remembers that one was set aside, for the
# note at the BLOCKED sink.
gl_scan() {  # sets rc ; the report is rewritten from scratch
  local ign_dst ign_n
  if [ -f "$STAGE/.gitleaksignore" ]; then
    IGN_SEEN=1
    ign_dst="$STAGE/.gitleaksignore.T844"; ign_n=0
    while [ -e "$ign_dst" ]; do
      ign_n=$((ign_n + 1))
      ign_dst="$STAGE/.gitleaksignore.T844.$ign_n"
    done
    mv -f "$STAGE/.gitleaksignore" "$ign_dst" 2>/dev/null
    if [ -f "$STAGE/.gitleaksignore" ]; then
      # The rename failed: an honoured fingerprint file is worse than an
      # unscanned one — it is removed, and that is said.
      rm -f "$STAGE/.gitleaksignore" 2>/dev/null
      deg "COVERAGE DEGRADED: staged .gitleaksignore could not be renamed — removed, its content NOT scanned"
    fi
  fi
  : > "$REPORT"
  if [ "$HAVE_TIMEOUT" = 1 ]; then
    ( cd "$SCAN_CWD" && timeout "$GITLEAKS_TIMEOUT" gitleaks detect --no-git --source "$SCAN_SRC" --redact --no-banner \
        --ignore-gitleaks-allow \
        --report-format json --report-path "$REPORT" ${CFG[@]+"${CFG[@]}"} ) >/dev/null 2>&1
    rc=$?
  else
    ( cd "$SCAN_CWD" && gitleaks detect --no-git --source "$SCAN_SRC" --redact --no-banner \
        --ignore-gitleaks-allow \
        --report-format json --report-path "$REPORT" ${CFG[@]+"${CFG[@]}"} ) >/dev/null 2>&1
    rc=$?
  fi
}
# Sets the default rules in place of the config: an explicit two-line file of
# our own (see above why never a bare `CFG=()`).
cfg_set_aside() {
  CFG=()
  DEFCFG="$(mktemp "${TMPDIR:-/tmp}/gitleaks-default.XXXXXX" 2>/dev/null)" || DEFCFG=""
  if [ -n "$DEFCFG" ] && printf '[extend]\nuseDefault = true\n' > "$DEFCFG" 2>/dev/null; then
    CFG=(--config "$DEFCFG")
  fi
}

# ---- gitleaks runs from an EMPTY directory (T-00000844) ----------------------
# gitleaks resolves a RELATIVE `[extend] path` against its CWD. That CWD was
# $STAGE, which the diff (hence the agent) populates — measured on 8.30.1: the
# pilot's `.gitleaks.toml` saying `path = "extra.toml"` + an UNTRACKED
# `extra.toml` written by the agent with an allowlist => the secret passed,
# rc 0. A syntactic reader of the config missed four of the spellings gitleaks
# accepts (`[ extend ]`, `extend = { path = … }`, `extend.path = …`, `PATH =`),
# so the fix is STRUCTURAL: the CWD is a fresh EMPTY directory, created BESIDE
# the stage (same parent), and the stage is passed as `--source ../<stage>`. A
# relative `[extend] path` then resolves in an empty directory, whatever its
# spelling: it cannot load, the scan fails the "unreadable config" way, and the
# check below sets the config aside (default rules — a real secret BLOCKS).
# The source is RELATIVE on purpose: an absolute `--source` makes every report
# `File` absolute, and under Git Bash a POSIX path handed to a native gitleaks
# comes back as C:\… — a prefix nobody can strip reliably. `../<name>/` is the
# same on every platform (backslashes are folded before stripping).
# If no empty directory can be had beside the stage, gitleaks runs from the
# stage as before — and then the config is set aside up front, said.
SCAN_CWD="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-cwd.XXXXXX" 2>/dev/null)" || SCAN_CWD=""
if [ -n "$SCAN_CWD" ] && [ "${SCAN_CWD%/*}" = "${STAGE%/*}" ]; then
  SCAN_SRC="../${STAGE##*/}"
else
  [ -n "$SCAN_CWD" ] && rm -rf "$SCAN_CWD" 2>/dev/null
  SCAN_CWD="$STAGE"; SCAN_SRC="."
  if [ -n "$CFG_SRC" ]; then
    deg "COVERAGE DEGRADED: no empty working directory beside the stage — gitleaks runs FROM the stage, where a relative [extend] path would resolve against the diff; $CFG_SRC set aside, default rules, allowlist IGNORED"
    cfg_set_aside
    CFG_SRC=""
  fi
fi
SCAN_PFX=""
[ "$SCAN_SRC" = "." ] || SCAN_PFX="$SCAN_SRC/"
export SCAN_PFX   # read by the python counter below
export IDXNAME    # likewise: the index copy's directory name, "" when none

gl_scan
CFG_SUSPECT=0
if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] && [ "$rc" -ne 137 ]; then
  if [ "$rc" -ne 1 ]; then
    CFG_SUSPECT=1
  elif ! grep -q '"StartLine"' "$REPORT" 2>/dev/null; then
    CFG_SUSPECT=1
  fi
fi
if [ -n "$CFG_SRC" ] && [ "$CFG_SUSPECT" = 1 ]; then
  vrc=0
  VALDIR="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-cfgcheck.XXXXXX" 2>/dev/null)" || VALDIR=""
  if [ -z "$VALDIR" ]; then
    deg "COVERAGE DEGRADED: $CFG_SRC could not be checked (mktemp failed) — scanning with it as is"
  else
    if have timeout; then
      ( cd "$VALDIR" && timeout "$GITLEAKS_TIMEOUT" gitleaks detect --no-git --source "." --no-banner \
          ${CFG[@]+"${CFG[@]}"} ) >/dev/null 2>&1
      vrc=$?
    else
      ( cd "$VALDIR" && gitleaks detect --no-git --source "." --no-banner \
          ${CFG[@]+"${CFG[@]}"} ) >/dev/null 2>&1
      vrc=$?
    fi
    rm -rf "$VALDIR" 2>/dev/null
  fi
  if [ "$vrc" -ne 0 ]; then
    deg "COVERAGE DEGRADED: $CFG_SRC unreadable — default rules, allowlist IGNORED (gitleaks rc $vrc loading it over an empty directory). A real secret is still BLOCKED; every false positive this file exempted BLOCKS TOO until the pilot repairs it."
    cfg_set_aside
    gl_scan    # the second pass, on the default rules — its rc is the one judged below
  fi
fi
fi

# 124 = GNU timeout expired; 137 = 128+9, killed if it escalated to SIGKILL.
if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
  deg "COVERAGE DEGRADED: gitleaks exceeded ${GITLEAKS_TIMEOUT}s over $staged staged file(s) — a working tree this large is almost always an ignore defect; check .gitignore for build output"
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi
# gitleaks: 0 = no leaks, 1 = leaks found, anything else = tool error. A tool
# error now costs the whole batch rather than one file — so it is reported
# loudly as DEGRADED and still exits 0: never a false GO, never a false block.
if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
  deg "COVERAGE DEGRADED: gitleaks error ($rc) scanning $staged staged file(s)"
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

if [ -s "$REPORT" ]; then
  if [ -n "$PY" ]; then
    total="$("$PY" - "$REPORT" "$LOCFILE" <<'PYEOF'
import json, re, sys
report, locfile = sys.argv[1], sys.argv[2]
# A report that does not parse (truncated, garbled) is NOT an empty one: count
# the findings still readable in its text — the same `"StartLine"` count the
# no-python path makes below — and keep the larger figure, so a readable
# finding BLOCKS on both paths (T-00000837, F2). 0 readable finding with rc 1
# is caught after this block as DEGRADED, never clean.
try:
    data = json.load(open(report, encoding="utf-8"))
    if not isinstance(data, list):
        data = []
    fb = 0
except Exception:
    data = []
    try:
        text = open(report, encoding="utf-8", errors="replace").read()
    except Exception:
        text = ""
    fb = len(re.findall(r'"StartLine"', text))
# gitleaks runs from an empty dir with `--source ../<stage>` (T-00000844): every
# File carries that prefix, stripped here so locations stay stage-relative.
# Backslashes (a native gitleaks under Git Bash) are folded first; runs of `/`
# are squeezed so an escaped `\\` pair folds to one separator.
import os
pfx = os.environ.get("SCAN_PFX", "")
# A file read from the INDEX copy (T-01M4X7Q1RR7WPF1GWYFEFHDDM9) is labelled
# "index:<path>" — same rule as the two other counters.
idx = os.environ.get("IDXNAME", "")
def rel(p):
    p = re.sub(r"/+", "/", str(p).replace("\\", "/"))
    p = p[len(pfx):] if pfx and p.startswith(pfx) else p
    return "index:" + p[len(idx) + 1:] if idx and p.startswith(idx + "/") else p
with open(locfile, "w", encoding="utf-8") as fh:
    for f in data:                                  # location only — never f["Secret"]
        if isinstance(f, dict):
            fh.write(f"{rel(f.get('File', '?'))}:{f.get('StartLine', '?')}\n")
    if fb > len(data):                              # unparsed report: file:line pairs by regex, value never read
        for m in re.finditer(r'"StartLine"\s*:\s*(\d+)(?:[^{}]*?"File"\s*:\s*"([^"]*)")?', text):
            fh.write(f"{rel(m.group(2) or '?')}:{m.group(1)}\n")
print(max(len(data), fb))
PYEOF
)"
  else
    # No Python: count findings AND still record file:line locations (the value
    # stays out — --redact already stripped it from the report). gitleaks emits
    # "StartLine" before "File" within each finding, so pairing them in emission
    # order is well defined. `"SymlinkFile"` cannot match the `"File"` alternative.
    line_no=""
    while IFS= read -r kv; do
      case "$kv" in
        *'"StartLine"'*) line_no="$(printf '%s' "$kv" | sed -E 's/.*:[[:space:]]*//')" ;;
        *'"File"'*)
          f="$(printf '%s' "$kv" | sed -E 's/^"File"[[:space:]]*:[[:space:]]*"?//; s/"$//')"
          # Same stage-relative location as the python path (T-00000844).
          f="$(printf '%s' "$f" | tr '\\' '/' | tr -s '/')"
          f="${f#"$SCAN_PFX"}"
          if [ -n "$IDXNAME" ]; then
            case "$f" in
              "$IDXNAME"/*)
                f="index:${f#"$IDXNAME"/}" ;;
            esac
          fi
          printf '%s:%s\n' "$f" "${line_no:-?}" >> "$LOCFILE" ;;
      esac
    done < <(grep -oE '"(StartLine|File)"[[:space:]]*:[[:space:]]*("[^"]*"|[0-9]+)' "$REPORT" 2>/dev/null)
    total="$(grep -c '"StartLine"' "$REPORT" 2>/dev/null || true)"; total="${total:-0}"
  fi
fi
# Un compte vide ou non numérique (analyseur python mort, sortie parasite) ne
# doit JAMAIS glisser vers « clean » : `[ "" -gt 0 ]` est FAUX, pas une erreur
# qui arrête. Il vaut 0 ici, et la garde ci-dessous le relit avec le rc.
case "${total:-}" in
  ''|*[!0-9]*) total=0 ;;
esac
# rc 1 = « leaks found » — il DOIT y avoir au moins un finding LISIBLE. rc 1
# sans rapport, c'est un sous-shell mort avant gitleaks (T-00000841 : tableau
# vide sous bash 3.2), pas un arbre propre : on le DIT, jamais « clean ». La
# garde est placée APRÈS le comptage, sur les DEUX chemins (python et grep) :
# un rapport TRONQUÉ ou illisible SANS finding lisible (0 `"StartLine"` dans son
# texte, sur les deux chemins) rend total=0 — même verdict, DEGRADED. Un
# rapport tronqué qui porte ENCORE un finding lisible compte ≥ 1 et BLOQUE.
if [ "$rc" -eq 1 ] && [ "$total" -eq 0 ]; then
  deg "COVERAGE DEGRADED: gitleaks returned 1 but no finding could be read (no or unreadable report: subshell died, config load failure, report write failure) — NOT clean"
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

# ---- Build a redacted JSON array of locations for the audit line ------------
LOCJSON="[]"
if [ -s "$LOCFILE" ]; then
  if [ -n "$PY" ]; then
    LOCJSON="$("$PY" - "$LOCFILE" <<'PYEOF'
import json, sys
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
print(json.dumps(lines[:50]))
PYEOF
)"
  else
    # Fallback: assemble a valid JSON array by hand, escaping \ and " so the
    # audit line stays parseable even without Python.
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

if [ "$total" -gt 0 ]; then
  # T-00000844 : the agent that wrote `gitleaks:allow` or a `.gitleaksignore`
  # expected an exemption — tell it, AT the block, why it did not get one. The
  # flagged lines are read back from the stage (file:line from $LOCFILE); a
  # location that cannot be read is simply not a hit.
  ALLOW_SEEN=0
  if [ -s "$LOCFILE" ] && [ -n "$STAGE" ]; then
    while IFS= read -r loc; do
      [ -n "$loc" ] || continue
      lf="${loc%:*}"; ln="${loc##*:}"
      case "$ln" in
        ''|*[!0-9]*) continue ;;
      esac
      lp="$STAGE/$lf"
      if [ -n "$IDX" ]; then
        case "$lf" in
          index:*)
            lp="$IDX/${lf#index:}" ;;
        esac
      fi
      [ -f "$lp" ] || continue
      if sed -n "${ln}p" "$lp" 2>/dev/null | grep -q 'gitleaks:allow'; then
        ALLOW_SEEN=1
        break
      fi
    done < "$LOCFILE"
  fi
  if [ "$ALLOW_SEEN" = 1 ] || [ "$IGN_SEEN" = 1 ]; then
    echo "note: gitleaks:allow comments and .gitleaksignore fingerprints are IGNORED by this gate (T-00000844) — report the false positive to the pilot, who exempts its LITERAL in .gitleaks.toml" >&2
  fi
  echo "SECRETS GATE (class-0, NON-WAIVABLE): $total secret(s) detected — BLOCKED" >&2
  audit "SECRETS" "$total" "$LOCJSON"
  emit_scan "$SCAN_STATUS" "$total" "$LOCJSON"
  exit 2
fi

# CENSUS_OK is read HERE too — this is the verdict sink of the DEFAULT engine
# (gitleaks present), and it was the last one still reading a failed census as a
# clean sweep. The flag used to be consulted only by the two fallback sinks
# (l.248/251) and by the staged=0 branch, i.e. never on the configuration most
# workstations run. Measured with a REAL trigger, no stub — a partial object
# store, so `git diff --name-only HEAD` fails rc=128 while `ls-files` and `sort`
# return 0: a TRACKED, MODIFIED file carrying a live key is never enumerated,
# gitleaks legitimately finds nothing in the truncated perimeter, and the run
# printed `SECRETS GATE (class-0): clean.` + audit CLEAN + exit 0. Downstream,
# a consumer saw neither a degraded line nor a fallback marker and read the
# run as clean. Placed AFTER the blocking branch on purpose: a partial census that still
# turned up a secret must keep blocking (exit 2) — degrading it would be the
# opposite error. Still exit 0, like every other benign path (l.32).
if [ "$CENSUS_OK" = 0 ]; then
  deg "COVERAGE DEGRADED: $CENSUS_WHY — $staged file(s) swept by $ENGINE, perimeter INCOMPLETE"
  audit "DEGRADED" 0 "[]"
  emit_scan degraded 0 "[]"
  exit 0
fi

FINAL_OUT="SECRETS GATE (class-0): clean."   # printed by on_exit (inside the systemMessage if DEGRADED)
audit "CLEAN" 0 "[]"
emit_scan scanned 0 "[]"
exit 0
