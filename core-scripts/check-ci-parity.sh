#!/usr/bin/env bash
# ============================================================================
# CI <> verify.sh PARITY CONTROL — the detector half of T-00000113
#
#   bash core-scripts/check-ci-parity.sh [--ci <file>] [--verify <file>]
#
# The repo's rule is that `core-scripts/verify.sh` runs EXACTLY what CI
# (.github/workflows/ci.yml) runs, so a push cannot go green locally and red
# upstream (L-00000068). Two ends of that promise are made IMPOSSIBLE by
# construction — verify.sh EXTRACTS the apt list, the image tag and the pip
# closure straight from ci.yml, so they can no longer be a second copy that
# drifts (D3/D4, and the pip closure T-00000155). But one end cannot be closed
# by extraction: the LIST OF COMMANDS the `tests` job runs. A new step added to
# ci.yml, or a flag changed on the test command, is invisible to verify.sh and
# nothing goes red. That structural hole (D5) — plus the two known verbosity
# flags (D1 `pytest -q`, D2 `pip --quiet`) — is what this control DETECTS.
#
# ----------------------------------------------------------------------------
# THIS FILE IS A CONTROL, NOT A TEST SUITE — the split mirrors check-workflow-pins
# ----------------------------------------------------------------------------
# It deliberately does NOT carry the `.test.sh` suffix. Its own guard — proving
# it can still go red — is `core-scripts/check-ci-parity.test.sh`, which DOES carry
# the suffix and is therefore auto-discovered by `core-scripts/run-bash-tests.sh`.
# That runner is a step of BOTH ci.yml and verify.sh, so the parity net runs on
# the Windows dev box AND on the linux leg WITHOUT a third step being added to
# ci.yml — which would itself break the very parity this guards.
#
# ----------------------------------------------------------------------------
# WHAT IS COMPARED, AND WHAT IS ACCEPTED
# ----------------------------------------------------------------------------
#   * TEST COMMANDS (D5/D1/D2). The significant `run:` commands of ci.yml's
#     `tests` job vs. verify.sh's host `step` calls AND its docker heredoc.
#     Environment setup (apt, pip and their scaffolding) is NOT compared as a
#     command here — it is either handled by construction or by the apt/version
#     checks below — so what remains is the actual test-execution surface. The
#     comparison is SYMMETRIC per leg: a command in ci.yml missing from a
#     verify.sh leg, OR the reverse, is a violation. The full command is printed.
#
#   * THE VERBOSITY ALLOWLIST, closed and commented, on the model of
#     check-workflow-pins.sh's `# needs-token:` — one line, one reason each:
#         -q       pytest verbosity (D1) — same scope, quieter output
#         --quiet  pip verbosity (D2)    — same scope, quieter output
#     These two are normalised away before comparison. ANY OTHER flag change is
#     a real divergence and goes red — that is what keeps D1/D2 detected rather
#     than hidden: swap `-q` for `-v` and the control bites.
#
#   * APT PACKAGES (D4). apt(ci.yml) must be a SUBSET of apt(verify docker), and
#     the surplus must belong to the NAMED list RUNNER_PREINSTALLED — what the CI
#     leg already has and python:*-slim lacks, by EITHER route: shipped by
#     ubuntu-latest, or installed there by `--with-deps` under armed_by=ci (the
#     Chromium shared libraries). The list is READ from verify.sh, never
#     enumerated here: an enumeration in a second file is a copy that drifts,
#     and this one had already drifted (it still said "git nodejs npm" after
#     procps joined). verify.sh derives
#     its apt list from ci.yml via `$APT_PKGS`, so this holds BY CONSTRUCTION on
#     the real tree; the check still bites if verify.sh ever REGRESSES to a
#     hardcoded literal list that drops a package ci.yml installs.
#
#   * PYTHON VERSION (D3). ci.yml's `python-version:` vs verify.sh's docker image
#     tag. Derived via `$IMAGE` on the real tree (by construction); a literal
#     `python:<x>-slim` that disagrees with ci.yml goes red.
#
# ----------------------------------------------------------------------------
# AN EMPTY PERIMETER IS A FAILURE, NOT A PASS
# ----------------------------------------------------------------------------
# Zero commands extracted from EITHER side renders "no divergence" — the perfect
# false green, and the exact shape a reformatted ci.yml that breaks the sed
# extraction would produce. The counts are PRINTED, and a zero on any side is a
# violation.
#
# ----------------------------------------------------------------------------
# BOUNDED, said here rather than discovered elsewhere
# ----------------------------------------------------------------------------
#   * SCRIPT STEPS ARE `run: |`, `run: >`, or an inline `run: <cmd>`. A bare
#     `run:` (e.g. the `defaults: run:` MAPPING) is not a script and is skipped —
#     otherwise `shell: bash` would be read as a command.
#   * `echo` lines are treated as scaffolding, so a hypothetical `run: echo …`
#     STEP would not be compared. Real test steps invoke a runner or a script,
#     which is what D5 is about.
#   * Full-comment lines are stripped FIRST (check-workflow-pins.sh discipline),
#     so the header prose that CITES `apt-get install` / `python -m pytest`
#     cannot poison a match. Inline `# …` (the tag on RUNNER_PREINSTALLED) kept.
#   * ci.yml holds THREE jobs since T-00001183 — `porte` (decides the mode),
#     `tests` (the kit's suite) and `adoptant` (the adopting project's gate) —
#     and the TEST COMMANDS are compared PER JOB, never over the whole file:
#       - the `run:` commands of the `tests` job ONLY (`job_text`) against
#         verify.sh's kit steps and docker heredoc. Before T-00001183 every
#         `run:` of the file was read, and the header said "assumed to hold ONE
#         job"; with `porte` and `adoptant` present that read their commands as
#         kit test commands — 20 divergences on the real tree, measured;
#       - verify.sh's ADOPTANT step (the `step` that runs
#         `.agents/bin/porte_adoptant.py`) is set apart from the kit steps and
#         compared, both ways, to the `run:` of the `adoptant` job that runs
#         the same script. Its installers (gitleaks, semgrep) are not compared:
#         they are environment, like apt and pip for `tests`;
#       - the `porte` job runs no test command and is not compared;
#       - a job NOT in `JOBS_CONNUS` is a violation: a fourth job is a
#         comparison nobody wrote yet, and it must be added here on purpose;
#       - an EMPTY perimeter on any side (kit or adoptant) is a violation.
#     apt (D4) and python-version (D3) still read the FIRST match of the whole
#     file, as verify.sh does — which is why `adoptant` sits AFTER `tests`.
#
# Exit: 0 no divergence · 1 at least one divergence (or empty perimeter) · 2 usage
# ============================================================================
# NOT `set -e`: divergences are counted and reporting continues, so the operator
# sees every faulty line in one run instead of the first one only.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

CI_FILE="$ROOT/.github/workflows/ci.yml"
VERIFY_FILE="$ROOT/core-scripts/verify.sh"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ci)
      shift
      [ "$#" -gt 0 ] || { echo "check-ci-parity: --ci requires a file" >&2; exit 2; }
      CI_FILE="$1" ;;
    --verify)
      shift
      [ "$#" -gt 0 ] || { echo "check-ci-parity: --verify requires a file" >&2; exit 2; }
      VERIFY_FILE="$1" ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}"
      exit 0 ;;
    # An unknown flag is REFUSED, never ignored: a silently-swallowed one would
    # return a green that does not measure what the caller believed.
    *)
      echo "check-ci-parity: unknown option \"$1\"" >&2
      exit 2 ;;
  esac
  shift
done

[ -f "$CI_FILE" ]     || { echo "check-ci-parity: ci file not found \"$CI_FILE\"" >&2; exit 2; }
[ -f "$VERIFY_FILE" ] || { echo "check-ci-parity: verify file not found \"$VERIFY_FILE\"" >&2; exit 2; }

VIOLATIONS=0
violation() { # violation <message>
  printf 'RED  %s\n' "$1"
  VIOLATIONS=$((VIOLATIONS + 1))
}

# Full-line comments -> blank (inline `# …` kept). Same discipline as
# check-workflow-pins.sh:386, and mandatory here for the same reason: these
# files spell out in comments exactly what they avoid.
strip_comments() { sed -E 's/^[[:space:]]*#.*$//' "$1"; }

# Leading-space count of a line.
indent_of() { local pre="${1%%[![:space:]]*}"; printf '%s' "${#pre}"; }
# Column where the `run:` key starts (chars before it) — the block-scalar body
# must be indented MORE than this.
keyindent_of() { local pre="${1%%run:*}"; printf '%s' "${#pre}"; }

# Normalise a command for comparison: canonicalise the interpreter token, drop
# `sudo`, remove the CLOSED verbosity ALLOWLIST (-q, --quiet), collapse and trim
# whitespace. Anything OTHER than the two allowlisted flags stays visible.
normalize_cmd() {
  printf '%s' "$1" | sed -E '
    s/"\$PY"/python/g
    s/(^|[[:space:]])python3([[:space:]]|$)/\1python\2/g
    s/(^|[[:space:]])sudo([[:space:]])/\1/g
    s/(^|[[:space:]])--quiet([[:space:]]|$)/\1\2/g
    s/(^|[[:space:]])-q([[:space:]]|$)/\1\2/g
    s/[[:space:]]+/ /g
    s/^ +//
    s/ +$//
  '
}

# Is a normalised command environment-setup or shell scaffolding (so NOT part of
# the test-execution surface compared here)?
is_setup() {
  case "$1" in
    "")                                             return 0 ;;
    set|"set "*)                                     return 0 ;;   # espace CITÉ, pas échappé :
                                                                   # `set\ *` n'est pas parsé par
                                                                   # tree-sitter-bash et sortait ce
                                                                   # fichier du compte SAST
    *apt-get*)                                       return 0 ;;   # apt: checked separately
    *"pip install"*|*"pip3 install"*)               return 0 ;;   # pip: by construction
    *"brew install"*)                                return 0 ;;   # macOS runner env setup (bash 5
                                                                   # for /bin/bash-3.2 runners); a dev
                                                                   # macOS box has brew bash already —
                                                                   # nothing for verify.sh to replay,
                                                                   # its docker leg is Linux
    # Windows-only universal-ctags PIN (ci.yml "Install system deps (Windows,
    # ctags pinned)"). These three are SYSTEM-DEP install, NOT test-execution:
    # nothing for verify.sh to replay (a dev box carries its own ctags), and the
    # ubuntu equivalent is apt, checked separately in D4. Each brace is narrowed
    # to *ctags* so it swallows ONLY the pinned-ctags step, never a bare `curl`,
    # `python -m zipfile` or `--version` a future real test step might run — the
    # negative twin in check-ci-parity.test.sh proves that per brace. The step's
    # `set -euo pipefail`, its `echo <sha256> | sha256sum -c` and its
    # `echo … >> "$GITHUB_PATH"` are ALREADY absorbed by the `set *` / `echo *`
    # braces above, so no brace is added for them.
    *curl*ctags*)                                    return 0 ;;   # fetch the pinned release zip
    *zipfile*ctags*)                                 return 0 ;;   # extract it into $RUNNER_TEMP
    *ctags*--version*)                               return 0 ;;   # post-install sanity of the binary
    REQ=*|*mktemp*)                                  return 0 ;;
    "cat "*|*"<<"*)                                  return 0 ;;
    EOF)                                             return 0 ;;
    *--hash=*|*==*)                                  return 0 ;;   # requirement lines
    *"git config"*)                                  return 0 ;;   # container-only setup
    "echo "*)                                        return 0 ;;
    rc_*)                                            return 0 ;;   # rc bookkeeping
    "[ "*)                                           return 0 ;;   # `[ "$rc" -eq 0 ] && …`
    "\\"|"]"|"}"|"{")                                return 0 ;;
  esac
  return 1
}

# Deduplicated append to a newline-delimited "set" held in a named variable.
set_add() { # set_add <listvar-name> <value>
  local cur="${!1}" v="$2"
  case "
$cur
" in
    *"
$v
"*) return 0 ;;
  esac
  printf -v "$1" '%s' "${cur:+$cur
}$v"
}

set_has() { # set_has <list> <value>
  # La clause descend d'une ligne : `case … in <clause>` sur la MÊME ligne
  # n'est pas parsé par tree-sitter-bash (le `esac` n'y est pour rien), et un
  # seul site retire ce fichier ENTIER du compte des cibles inspectées par la
  # porte SAST. Le sujet et le motif — sauts de ligne encadrants compris —
  # sont INCHANGÉS.
  case "
$1
" in
    *"
$2
"*) return 0 ;;
  esac
  return 1
}

count_set() { # count_set <list>
  [ -n "$1" ] || { printf '0'; return; }
  printf '%s\n' "$1" | grep -c .
}

# ---------------------------------------------------------------- extraction
CI_CMDS=""
HOST_CMDS=""
DOCKER_CMDS=""
CI_ADOPTANT_CMDS=""
HOST_ADOPTANT_CMDS=""

# The jobs this control knows how to compare (header). A fourth job is refused
# until someone writes ITS comparison here.
JOBS_CONNUS="tests porte adoptant"
# The script that marks verify.sh's adoptant step and the `adoptant` job's run.
PORTE_ADOPTANT_SCRIPT=".agents/bin/porte_adoptant.py"

maybe_add() { # maybe_add <listvar> <raw command>
  local n; n="$(normalize_cmd "$2")"
  [ -n "$n" ] || return 0
  is_setup "$n" && return 0
  set_add "$1" "$n"
}

# --- ci.yml: the jobs ---------------------------------------------------------
# A job = a two-space-indented `<id>:` key under the top-level `jobs:`, up to the
# next one or the next top-level key. Comments are blanked FIRST, as everywhere
# in this file. Bounded scanning, not YAML parsing: a shape it does not see
# yields an EMPTY job, which the perimeter checks turn into a violation.
job_names() { # job_names <ci file> — one job id per line
  strip_comments "$1" | awk '
    /^jobs:[[:space:]]*$/ { j = 1; next }
    j && /^[^[:space:]]/ { j = 0 }
    j && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { id = $0; sub(/^  /, "", id); sub(/:[[:space:]]*$/, "", id); print id }
  '
}

job_text() { # job_text <ci file> <job id> — that job's lines; empty when absent
  strip_comments "$1" | awk -v want="$2" '
    /^jobs:[[:space:]]*$/ { j = 1; next }
    j && /^[^[:space:]]/ { j = 0; t = 0 }
    j && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { id = $0; sub(/^  /, "", id); sub(/:[[:space:]]*$/, "", id); t = (id == want); next }
    j && t { print }
  '
}

# --- ci.yml: the `run:` commands of ONE job -----------------------------------
# collect_ci <job id> <listvar> [<substring>] — with a substring, only the
# commands carrying it are kept (the adoptant job: its run of the gate script,
# not its installers).
collect_ci() {
  local job="$1" listvar="$2" must="${3:-}" content line rest rest_t run_ind=0 inrun=0 ind
  content="$(job_text "$CI_FILE" "$job")"
  while IFS= read -r line; do
    if [ "$inrun" -eq 1 ]; then
      if [ -z "${line//[[:space:]]/}" ]; then continue; fi   # blank inside block
      ind="$(indent_of "$line")"
      if [ "$ind" -gt "$run_ind" ]; then
        collect_one "$listvar" "$line" "$must"
        continue
      fi
      inrun=0    # dedented: block ended, re-examine this line below
    fi
    if [[ "$line" =~ ^[[:space:]]*(-[[:space:]]+)?run:(.*)$ ]]; then
      rest="${BASH_REMATCH[2]}"
      rest_t="$(printf '%s' "$rest" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
      case "$rest_t" in
        "|"|">"|"|-"|">-"|"|+"|">+")
          run_ind="$(keyindent_of "$line")"; inrun=1 ;;
        "")
          : ;;   # bare run: (defaults mapping / empty) — not a script
        *)
          collect_one "$listvar" "$rest_t" "$must"; inrun=0 ;;
      esac
    fi
  done <<< "$content"
}

collect_one() { # collect_one <listvar> <raw command> <substring or empty>
  if [ -n "$3" ]; then
    case "$2" in
      *"$3"*) ;;
      *) return 0 ;;
    esac
  fi
  maybe_add "$1" "$2"
}

# --- verify.sh: host `step` calls ------------------------------------------
# The ADOPTANT step (it runs the gate script) is set apart from the kit steps:
# it runs only in an adopting project, where `tests` is skipped, so it is
# compared to the `adoptant` job — never to `tests`.
collect_host() {
  local content line rest
  content="$(strip_comments "$VERIFY_FILE")"
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*step[[:space:]]+\"[^\"]*\"[[:space:]]+(.+)$ ]]; then
      rest="${BASH_REMATCH[1]}"
      case "$rest" in
        *"$PORTE_ADOPTANT_SCRIPT"*)
          maybe_add HOST_ADOPTANT_CMDS "$rest" ;;
        *)
          maybe_add HOST_CMDS "$rest" ;;
      esac
    fi
  done <<< "$content"
}

# --- verify.sh: docker heredoc commands ------------------------------------
collect_docker() {
  local content line trimmed indocker=0
  content="$(strip_comments "$VERIFY_FILE")"
  while IFS= read -r line; do
    if [ "$indocker" -eq 0 ]; then
      case "$line" in
        *"bash -c '"*) indocker=1 ;;
      esac
      continue
    fi
    trimmed="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    case "$trimmed" in
      \'*) indocker=0; continue ;;    # closing quote line: `'; then`
    esac
    maybe_add DOCKER_CMDS "$line"
  done <<< "$content"
}

collect_ci tests CI_CMDS
collect_ci adoptant CI_ADOPTANT_CMDS "$PORTE_ADOPTANT_SCRIPT"
collect_host
collect_docker

# ---------------------------------------------------------------- known jobs
CI_JOBS="$(job_names "$CI_FILE")"
while IFS= read -r _job; do
  [ -n "$_job" ] || continue
  case " $JOBS_CONNUS " in
    *" $_job "*) ;;
    *) violation "ci.yml carries an UNKNOWN job [$_job] — this control compares the jobs it knows ($JOBS_CONNUS); write that job's comparison here before adding it" ;;
  esac
done <<< "$CI_JOBS"

# ---------------------------------------------------------------- compare
diff_missing() { # diff_missing <from-desc> <in-desc> <from-list> <in-list>
  local fromd="$1" ind="$2" fl="$3" il="$4" line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    set_has "$il" "$line" || \
      violation "test command in $fromd is MISSING from $ind: [$line]"
  done <<< "$fl"
}

diff_missing "ci.yml tests job"    "verify.sh host leg"   "$CI_CMDS"     "$HOST_CMDS"
diff_missing "verify.sh host leg"  "ci.yml tests job"     "$HOST_CMDS"   "$CI_CMDS"
diff_missing "ci.yml tests job"    "verify.sh docker leg" "$CI_CMDS"     "$DOCKER_CMDS"
diff_missing "verify.sh docker leg" "ci.yml tests job"    "$DOCKER_CMDS" "$CI_CMDS"
diff_missing "ci.yml adoptant job"     "verify.sh adoptant step" "$CI_ADOPTANT_CMDS"   "$HOST_ADOPTANT_CMDS"
diff_missing "verify.sh adoptant step" "ci.yml adoptant job"     "$HOST_ADOPTANT_CMDS" "$CI_ADOPTANT_CMDS"

# ---------------------------------------------------------------- apt (D4)
apt_ci_raw="$(strip_comments "$CI_FILE" \
  | sed -n -E 's/^[[:space:]]*(sudo[[:space:]]+)?apt-get[[:space:]]+install[[:space:]]+-y[[:space:]]+(.+)$/\2/p' \
  | head -1)"
runner_pre="$(strip_comments "$VERIFY_FILE" \
  | sed -n -E 's/^[[:space:]]*RUNNER_PREINSTALLED="([^"]*)".*$/\1/p' \
  | head -1)"
apt_docker_line="$(strip_comments "$VERIFY_FILE" \
  | sed -n -E 's/^[[:space:]]*apt-get[[:space:]]+install[[:space:]]+(.+)$/\1/p' \
  | head -1)"
# Le `>` passe par une variable : un métacaractère écrit DANS le motif d'une
# expansion n'est pas parsé par tree-sitter-bash. Troncature INCHANGÉE.
_redir='>'
apt_docker_line="${apt_docker_line%%$_redir*}"   # drop the `>/dev/null` redirection

APT_CI=""
APT_DOCKER=""
construction=0
set -f
for tok in $apt_ci_raw; do
  case "$tok" in
    -*) ;;
    '') ;;
    *) set_add APT_CI "$tok" ;;
  esac
done
for tok in $apt_docker_line; do
  case "$tok" in
    *APT_PKGS*) construction=1 ;;   # derived from ci.yml + RUNNER_PREINSTALLED
    -*) ;;
    '') ;;
    *) set_add APT_DOCKER "$tok" ;;
  esac
done
if [ "$construction" -eq 1 ]; then
  for tok in $apt_ci_raw; do
    case "$tok" in
      -*) ;;
      '') ;;
      *) set_add APT_DOCKER "$tok" ;;
    esac
  done
  for tok in $runner_pre;  do set_add APT_DOCKER "$tok"; done
fi
set +f

if [ -z "$APT_CI" ]; then
  violation "apt package list could not be extracted from ci.yml (empty perimeter)"
else
  # apt(ci) subset of apt(docker)
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    set_has "$APT_DOCKER" "$p" || \
      violation "apt package [$p] installed by ci.yml is MISSING from verify.sh's docker leg"
  done <<< "$APT_CI"
  # surplus of apt(docker) must belong to RUNNER_PREINSTALLED
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    set_has "$APT_CI" "$p" && continue
    case " $runner_pre " in
      *" $p "*) ;;
      *) violation "apt package [$p] is in verify.sh's docker leg, absent from ci.yml, and NOT in RUNNER_PREINSTALLED [$runner_pre]" ;;
    esac
  done <<< "$APT_DOCKER"
fi

# ---------------------------------------------------------------- python (D3)
py_ci="$(strip_comments "$CI_FILE" \
  | sed -n -E 's/^[[:space:]]*python-version:[[:space:]]*"?([0-9]+(\.[0-9]+)*)"?.*$/\1/p' \
  | head -1)"
image_tok="$(strip_comments "$VERIFY_FILE" \
  | sed -n -E 's/.*docker run .* ([^[:space:]]+) bash -c.*/\1/p' \
  | head -1)"
if [ -z "$py_ci" ]; then
  violation "python-version could not be extracted from ci.yml (empty perimeter)"
else
  case "$image_tok" in
    *IMAGE*) : ;;   # derived from ci.yml's python-version — by construction
    python:*)
      v="${image_tok#python:}"; v="${v%-slim}"
      [ "$v" = "$py_ci" ] || \
        violation "verify.sh docker image [$image_tok] disagrees with ci.yml python-version [$py_ci]" ;;
    *)
      violation "verify.sh docker image [$image_tok] is neither the derived \$IMAGE nor a python:<ver>-slim literal" ;;
  esac
fi

# ---------------------------------------------------------------- perimeter
n_ci="$(count_set "$CI_CMDS")"
n_host="$(count_set "$HOST_CMDS")"
n_docker="$(count_set "$DOCKER_CMDS")"

if [ "$n_ci" -eq 0 ] || [ "$n_host" -eq 0 ] || [ "$n_docker" -eq 0 ]; then
  violation "empty perimeter: ci=$n_ci host=$n_host docker=$n_docker test command(s) — a side with 0 is a false green"
fi

# The adoptant perimeter, same rule: zero on either side compares nothing.
n_ci_ad="$(count_set "$CI_ADOPTANT_CMDS")"
n_host_ad="$(count_set "$HOST_ADOPTANT_CMDS")"
if [ "$n_ci_ad" -eq 0 ] || [ "$n_host_ad" -eq 0 ]; then
  violation "empty adoptant perimeter: ci.yml adoptant job=$n_ci_ad verify.sh adoptant step=$n_host_ad (both must run $PORTE_ADOPTANT_SCRIPT) — a side with 0 is a false green"
fi

echo "check-ci-parity: ci=$CI_FILE"
echo "check-ci-parity: verify=$VERIFY_FILE"
echo "check-ci-parity: jobs — $(printf '%s' "$CI_JOBS" | tr '\n' ' ') (known: $JOBS_CONNUS)"
echo "check-ci-parity: perimeter — ci.yml test cmd(s):"
printf '%s\n' "$CI_CMDS" | sed -n 's/^\(.\)/    ci     | \1/p'
printf '%s\n' "$HOST_CMDS" | sed -n 's/^\(.\)/    host   | \1/p'
printf '%s\n' "$DOCKER_CMDS" | sed -n 's/^\(.\)/    docker | \1/p'
printf '%s\n' "$CI_ADOPTANT_CMDS" | sed -n 's/^\(.\)/    ci-adoptant   | \1/p'
printf '%s\n' "$HOST_ADOPTANT_CMDS" | sed -n 's/^\(.\)/    host-adoptant | \1/p'
echo "check-ci-parity: $n_ci CI test cmd(s), $n_host host step(s), $n_docker docker cmd(s); adoptant: ci=$n_ci_ad verify=$n_host_ad; apt ci=[$apt_ci_raw] runner-preinstalled=[$runner_pre]; python-version=$py_ci — $VIOLATIONS divergence(s)"

if [ "$VIOLATIONS" -ne 0 ]; then
  cat >&2 <<'EOF'

CI <> verify.sh parity requires one of, per divergence:
  * REFLECT the ci.yml command in verify.sh (host step and/or docker heredoc), or
  * ADD a one-line, commented allowlist entry (verbosity only) in this control,
    on the model of the -q / --quiet lines already present, or
  * for apt: name the surplus package in RUNNER_PREINSTALLED with its reason.
Ultimate rollback: delete check-ci-parity.sh + .test.sh to restore the statu quo.
EOF
  exit 1
fi
exit 0
