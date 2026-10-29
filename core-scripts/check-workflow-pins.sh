#!/usr/bin/env bash
# ============================================================================
# WORKFLOW SUPPLY-CHAIN GUARD — the enforcement half of the pinning work
#
#   bash core-scripts/check-workflow-pins.sh [--root <dir>]
#
# The pinning itself (digest-pinned actions, hash-pinned Python deps,
# persist-credentials off) is true TODAY and false in three weeks: nothing in
# this repo stops the next hand-edited workflow from arriving with
# `uses: actions/foo@v1`, or the next install line from arriving without a hash.
# A pinning without a guard is hygiene, and hygiene is lost at the first rushed
# commit. This script is that guard.
#
# ----------------------------------------------------------------------------
# THIS FILE IS A CONTROL, NOT A TEST SUITE — AND ITS OWN GUARD IS SEPARATE
# ----------------------------------------------------------------------------
# It deliberately does NOT carry the `.test.sh` suffix. Its own guard — the one
# proving it can still go red — is `core-scripts/check-workflow-pins.test.sh`, which
# DOES carry the suffix and is therefore auto-discovered by
# `core-scripts/run-bash-tests.sh`. Splitting the two lets the guard FAKE trees for
# the scanner (via `--root`) without the scanner knowing its tests exist.
#
# HOW THIS IS WIRED INTO CI, AND WHY NOT AS ITS OWN CI STEP: the repo's rule is
# that `core-scripts/verify.sh` runs EXACTLY what CI runs, and verify.sh runs two
# steps — `python -m pytest` and `bash core-scripts/run-bash-tests.sh`. Adding a
# third step to ci.yml alone would make verify.sh stop matching CI, which is the
# precise failure L-00000068 records (green locally, red in CI). So the wiring
# goes through `run-bash-tests.sh`: the companion test invokes this scanner
# against the REAL tree as its first case, so a floating tag re-introduced
# anywhere turns both CI and verify.sh red, on Windows and on the linux leg.
#
# ----------------------------------------------------------------------------
# THE FOUR RULES, AND WHAT EACH ONE PREVENTS
# ----------------------------------------------------------------------------
#   R1  EVERY `uses:` carries `@<40 hex>` AND a `# vX.Y.Z` tag comment.
#       A git tag is MUTABLE: `actions/checkout@v4` is a pointer its maintainer
#       — or whoever takes that account — can move with no commit in THIS repo
#       changing. The code running in our CI would then no longer be described
#       by our repo.
#       THE COMMENT IS REQUIRED ON THE SAME FOOTING AS THE DIGEST, and that is
#       not comfort: nobody recognises `11d5960a…`. Without the tag in clear,
#       the pin is immutable AND unauditable — you can no longer say which
#       version is running, so you can never decide whether to bump it. A digest
#       nobody can read will never be updated.
#
#   R2  EVERY workflow `pip install` runs under `--require-hashes`, names only
#       `==`-pinned packages, and every requirement line carries a full
#       `--hash=sha256:<64 hex>`.
#       What this prevents: a Python package executes code AT INSTALL time
#       (build hooks), before a single test runs. In `eval-nightly.yml` — the
#       only job in this repo carrying a live secret — that code would run with
#       ANTHROPIC_API_KEY in its environment.
#       The pattern covers the REAL forms of the repo — `python -m pip install`,
#       `python3 -m pip install`, `pip install`, `pip3 install` — not just bare
#       `pip install`: the line that motivated this rule was written
#       `python -m pip install --upgrade pip pytest`, and a rule that missed it
#       would have guarded nothing at all.
#       `-r <file>` IS FOLLOWED (T-00001183). Before, `-r` was skipped as an
#       option and R2c read only the inline lines of the workflow: a file named
#       by `-r` was NEVER opened, so "every requirement line carries a full
#       hash" was false for it — measured. Now each LOGICAL requirement of that
#       file (backslash continuations joined, comments dropped) must be
#       `==`-pinned and carry the full `--hash=sha256:<64 hex>`; a missing file,
#       a URL, an absolute path, an option line inside the file (`--index-url`,
#       a nested `-r`/`-c`…) and an EMPTY file are violations.
#
#   R3  EVERY workflow declares `permissions:` AT THE ROOT with `contents: read`.
#       With no root block, GITHUB_TOKEN takes the ORGANISATION default, which
#       this repo does not control and which may be "read and write". A
#       compromised action would then hold a token able to write to the repo.
#       STATE OF THE REPO AS WRITTEN: both workflows already do this. So this
#       rule fixes nothing — it LOCKS an acquired property. That is exactly what
#       a guard is better at than a comment: nobody would notice its absence in
#       a third workflow added on a Friday.
#
#   R4  EVERY `actions/checkout` sets `persist-credentials: false`.
#       By default checkout leaves GITHUB_TOKEN in `.git/config`, readable by
#       every later step — including code a dependency runs at install time.
#       That is what turns an unpinned install into an exfiltration path, so R2
#       and R4 are halves of one rule, not two unrelated ones.
#       ESCAPE HATCH, ON PURPOSE: a job that genuinely pushes NEEDS the token,
#       and a rule with no way out simply gets deleted the first time it is
#       inconvenient. So `persist-credentials: true` is accepted when, and only
#       when, the same line carries a `# needs-token: <reason>` justification.
#       Silence is refused; a stated reason is accepted and greppable.
#
# ----------------------------------------------------------------------------
# BLIND SPOTS, NAMED HERE RATHER THAN DISCOVERED BY SOMEBODY ELSE
# ----------------------------------------------------------------------------
#   1. A HASH FREEZES BYTES, IT DOES NOT VOUCH FOR THEM. R2 guarantees the
#      artefact is the one reviewed; it says nothing about whether that artefact
#      was ever trustworthy. Same for R1: a valid SHA-40 pointing at a malicious
#      fork passes. Both rules buy IMMUTABILITY and REVIEWABILITY (a bump is a
#      diff), not trust.
#   2. TRANSITIVE DEPS ARE COVERED ONLY BECAUSE THE CLOSURE IS LISTED IN FULL.
#      `--require-hashes` refuses to install anything unlisted, so a new
#      conditional dependency makes CI fail LOUD rather than pull unpinned code.
#      Fail-safe, but it is a maintenance cost, not a free win.
#   3. `sudo apt-get install` IS NOT PINNABLE and is NOT checked here. apt has
#      no digest equivalent, and `pkg=version` breaks as soon as the ubuntu
#      archive rotates that build. That trust is real and unguarded.
#   4. `python-version` IS PINNED TO THE MINOR `3.12` in both workflows; only the
#      PATCH floats, knowingly (pinned wheels are all `py3-none-any`, a patch pin
#      would break at each runner tool-cache rotation for no gain). Not checked here.
#   5. THIS SCANNER READS `.github/workflows/` ONLY. `core-scripts/verify.sh` runs
#      its own unpinned `pip install` inside the Docker leg; that file is out of
#      this guard's scope and remains a known gap.
#   6. LOCAL ACTIONS (`uses: ./…`) are accepted with no digest: they name a path
#      in THIS repo, already frozen by the current commit.
#   7. A `uses:` WRITTEN AS A MULTI-LINE YAML BLOCK SCALAR (`uses: >-` then the
#      ref on the next line) escapes R1's line-at-a-time reading. This residual
#      is FAIL-SAFE, which is why it stays a comment and not code: `>-` looks
#      neither like a local path nor like a SHA-40, so the rule goes RED. False
#      red, never false green. No tool writes a `uses:` that way.
#   8. FULLY-COMMENTED LINES ARE STRIPPED BEFORE ANALYSIS, and that is
#      MANDATORY here: these workflows spell out what they avoid — ci.yml's
#      header writes `actions/checkout@v4` to explain why it no longer uses it,
#      and names the old `--upgrade pip` line. A guard matching substrings would
#      go red on the prose and be disarmed within the week. A `#` at the END of
#      a line is KEPT: that is where R1's tag comment lives.
#   9. A `-r` WHOSE ARGUMENT IS A SHELL EXPANSION (`-r "$REQ"`) IS NOT FOLLOWED:
#      it names a file the step writes at run time from its INLINE block
#      (`cat > "$REQ" <<'EOF'`), and those inline lines are what R2c already
#      reads one by one. What this cannot see is an expansion that points at
#      some OTHER file — no workflow here does it, and a literal path is the
#      form R2 follows. `-c`/`--constraint` files are not followed either: a
#      constraint cannot add a package, only narrow one.
#
# ----------------------------------------------------------------------------
# AN EMPTY PERIMETER IS A FAILURE, NOT A PASS
# ----------------------------------------------------------------------------
# Zero workflows analysed renders "no violations" — the perfect false green.
# The subject counts are therefore PRINTED, and zero subjects is an error.
#
# Exit: 0 no violation · 1 at least one violation (or no subject) · 2 usage error
# ============================================================================
# NOT `set -e`: violations are counted and reporting continues, so the operator
# sees every faulty line in one run instead of the first one only.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      shift
      [ "$#" -gt 0 ] || { echo "check-workflow-pins: --root requires a directory" >&2; exit 2; }
      ROOT="$1"
      ;;
    -h|--help)
      sed -n '2,6p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    # An unknown flag is REFUSED, never ignored: a silently-swallowed `--rot`
    # would return a green that does not measure what the caller believed.
    *)
      echo "check-workflow-pins: unknown option \"$1\"" >&2
      exit 2
      ;;
  esac
  shift
done

[ -d "$ROOT" ] || { echo "check-workflow-pins: directory not found \"$ROOT\"" >&2; exit 2; }

WF_DIR="$ROOT/.github/workflows"

VIOLATIONS=0
N_WORKFLOWS=0
N_USES=0
N_PIP=0
N_PINS=0
N_REQFILES=0
N_CHECKOUT=0
LINES=()

violation() { # violation <file> <line|-> <message>
  printf 'RED %s:%s  %s\n' "$1" "$2" "$3"
  VIOLATIONS=$((VIOLATIONS + 1))
}

# Leading-space count of a line. YAML forbids tabs for indentation, so spaces
# are the only case that needs handling.
indent_of() {
  local pre="${1%%[![:space:]]*}"
  printf '%s' "${#pre}"
}

# ----------------------------------------------------------------------------
# R1 — is a `uses:` pinned AND readable?
# ----------------------------------------------------------------------------
check_uses() { # check_uses <file> <lineno> <text after `uses:`>
  local f="$1" lineno="$2" rest="$3"
  local ref comment

  # First token is the reference; whatever follows is the comment.
  ref="${rest%%[[:space:]]*}"
  comment="${rest#"$ref"}"

  N_USES=$((N_USES + 1))

  # LOCAL action: a path in this repo, already frozen by the current commit.
  case "$ref" in
    ./*|.\\*) return 0 ;;
  esac

  if [[ ! "$ref" =~ @[0-9a-fA-F]{40}$ ]]; then
    violation "$f" "$lineno" \
      "uses: \"$ref\" is NOT pinned to a SHA-40 — a tag is MUTABLE"
    return 0
  fi

  # `# vX.Y.Z` — FULL semver required. A bare `# v4` would be as uninformative
  # as the floating tag just removed.
  if [[ ! "$comment" =~ \#[[:space:]]*v?[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    violation "$f" "$lineno" \
      "uses: pinned but with NO \"# vX.Y.Z\" tag comment — digest is unauditable"
  fi
}

# ----------------------------------------------------------------------------
# R2a/R2b — does a pip install line demand hashes and name only pinned packages?
# ----------------------------------------------------------------------------
check_pip() { # check_pip <file> <lineno> <line text>
  local f="$1" lineno="$2" line="$3"
  local args tok skip_next=0 bare="" req_next=0 reqs="" r
  # Newline-separated rather than an array: under `set -u`, bash < 4.4 treats
  # an EMPTY array expansion as unbound (the macOS runner's /bin/bash 3.2).
  local _nl='
'

  N_PIP=$((N_PIP + 1))

  if [[ ! "$line" =~ (^|[[:space:]])--require-hashes([[:space:]]|$) ]]; then
    violation "$f" "$lineno" \
      "pip install WITHOUT --require-hashes — PyPI code would run unverified at install time"
  fi

  # Everything after `pip install`, then TRUNCATED at the first shell chaining
  # operator: `pip install pytest==9.1.1 && echo ok` must not have `echo` and
  # `ok` judged as unpinned packages.
  # Les trois opérateurs passent par une VARIABLE, jamais en littéral dans le
  # motif : `${args%%&&*}` est du bash valide mais tree-sitter-bash ne le parse
  # pas, et un seul site retire le fichier ENTIER du compte des cibles
  # inspectées par la porte SAST. Le motif reste le même une fois la variable
  # développée — troncature identique, mesurée.
  _amp='&&'
  _semi=';'
  _pipe='|'
  args="${line#*pip install}"
  args="${args%%$_amp*}"
  args="${args%%$_semi*}"
  args="${args%%$_pipe*}"
  args="${args%%#*}"

  for tok in $args; do
    if [ "$req_next" -eq 1 ]; then
      req_next=0
      reqs="${reqs:+$reqs$_nl}$tok"
      continue
    fi
    if [ "$skip_next" -eq 1 ]; then skip_next=0; continue; fi
    case "$tok" in
      # `-r <file>`: the NEXT token is a requirement file, FOLLOWED below (R2d)
      # instead of skipped — before T-00001183 it was never opened.
      -r|--requirement)
        req_next=1 ;;
      --requirement=*)
        reqs="${reqs:+$reqs$_nl}${tok#--requirement=}" ;;
      # `-r<file>`, glued: pip's option parser accepts it, so must this guard.
      # `--require-hashes` cannot match — its second character is `-`.
      -r?*)
        reqs="${reqs:+$reqs$_nl}${tok#-r}" ;;
      # Flags whose NEXT token is a value, not a package. `--only-binary :all:`
      # is the one that matters most here: `:all:` does not start with `-`, so
      # without this it would be reported as an unpinned package — a FALSE RED,
      # which is exactly how a guard gets disarmed.
      -c|--constraint|--only-binary|--no-binary|\
      -i|--index-url|--extra-index-url|-f|--find-links|-t|--target|\
      --prefix|--cache-dir|--timeout|--retries|--proxy|--cert|--client-cert|\
      --python-version|--platform|--abi|--implementation|--progress-bar|--report)
        skip_next=1 ;;
      -*) ;;
      *)
        case "$tok" in
          *==*) ;;
          *) bare="${bare:+$bare, }$tok" ;;
        esac
        ;;
    esac
  done

  if [ -n "$bare" ]; then
    violation "$f" "$lineno" \
      "UNPINNED pip install: $bare — a floating package runs code at install time"
  fi

  # A trailing `-r` with no argument is a pip usage error; name it rather than
  # let it read as "nothing to follow".
  if [ "$req_next" -eq 1 ]; then
    violation "$f" "$lineno" "pip install ends on \"-r\" with no file — nothing R2 could check"
  fi
  if [ -n "$reqs" ]; then
    while IFS= read -r r; do
      [ -n "$r" ] || continue
      check_req_file "$f" "$lineno" "$r"
    done <<< "$reqs"
  fi
}

# ----------------------------------------------------------------------------
# R2c — does every requirement line carry a full sha256?
#
# These are the `<name>==<version>` lines of the inline requirement block. The
# hash must be on the SAME line, which is why the block is written one
# requirement per line: it makes the rule exact instead of approximate.
# ----------------------------------------------------------------------------
check_pin_line() { # check_pin_line <file> <lineno> <line text>
  local f="$1" lineno="$2" line="$3"
  local name="${line#"${line%%[![:space:]]*}"}"
  name="${name%%==*}"

  N_PINS=$((N_PINS + 1))

  if [[ ! "$line" =~ --hash=sha256:[0-9a-f]{64}([[:space:]]|$) ]]; then
    violation "$f" "$lineno" \
      "requirement \"$name\" pinned by version but with NO valid --hash=sha256:<64 hex>"
  fi
}

# ----------------------------------------------------------------------------
# R2d — a `-r <file>` is FOLLOWED (T-00001183).
#
# Every LOGICAL requirement of the file — backslash continuations joined, full
# comment lines and ` #` tails dropped, as pip reads it — must be `==`-pinned,
# and goes through check_pin_line for its hash. The file is resolved RELATIVE TO
# THE ROOT (`--root`), which is where a workflow step runs. Refused: an absent
# file, a URL, an absolute path (it names the runner's disk, not this repo), an
# option line (an index, a nested `-r`/`-c` — each widens what pip may fetch
# beyond what is pinned here), and an EMPTY file (`-r` of nothing pins nothing).
# A shell expansion is not followed: blind spot 9 in the header.
# ----------------------------------------------------------------------------
check_req_requirement() { # check_req_requirement <req file> <lineno> <logical line>
  local rf="$1" lno="$2" t="$3" first
  # Leading and trailing whitespace off.
  t="${t#"${t%%[![:space:]]*}"}"
  t="${t%"${t##*[![:space:]]}"}"
  [ -n "$t" ] || return 1
  first="${t%%[[:space:]]*}"
  case "$t" in
    -*)
      violation "$rf" "$lno" \
        "option line \"$first\" in a hash-pinned requirement file — an index, a nested -r/-c or any option widens what pip may install"
      return 0 ;;
  esac
  # `name[extras]==version`, optionally glued to the `;` of an environment marker.
  local _re_eq='^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?==[^[:space:];]+;?$'
  if [[ ! "$first" =~ $_re_eq ]]; then
    violation "$rf" "$lno" \
      "requirement \"$first\" is NOT ==-pinned — a range lets the resolver pick an artefact nobody reviewed"
  fi
  check_pin_line "$rf" "$lno" "$t"
  return 0
}

check_req_file() { # check_req_file <workflow> <lineno> <-r argument>
  local f="$1" lineno="$2" arg="$3"
  local path l t cur="" start=0 lno=0 n=0
  local _q='"' _sq="'" _bs='\' _dollar='$' _sp_hash=' #' _cr
  _cr="$(printf '\r')"
  path="$arg"
  path="${path#"$_q"}"; path="${path%"$_q"}"
  path="${path#"$_sq"}"; path="${path%"$_sq"}"
  case "$path" in
    *"$_dollar"*)
      return 0 ;;
    *://*)
      violation "$f" "$lineno" \
        "pip -r \"$arg\" is a URL — a requirement file must be a file of this repository, readable by this guard"
      return 0 ;;
    /*)
      violation "$f" "$lineno" \
        "pip -r \"$arg\" is an ABSOLUTE path — it names the runner's disk, not a file of this repository"
      return 0 ;;
  esac
  path="${path#./}"
  if [ ! -f "$ROOT/$path" ]; then
    violation "$f" "$lineno" \
      "pip -r \"$path\": requirement file NOT FOUND under the repository root — R2 cannot check its hashes"
    return 0
  fi
  N_REQFILES=$((N_REQFILES + 1))

  while IFS= read -r l || [ -n "$l" ]; do
    lno=$((lno + 1))
    l="${l%"$_cr"}"
    t="${l#"${l%%[![:space:]]*}"}"
    case "$t" in
      "#"*)
        continue ;;
    esac
    l="${l%%"$_sp_hash"*}"
    [ "$start" -ne 0 ] || start="$lno"
    case "$l" in
      *"$_bs")
        cur="$cur${l%"$_bs"} "
        continue ;;
    esac
    cur="$cur$l"
    if check_req_requirement "$path" "$start" "$cur"; then
      n=$((n + 1))
    fi
    cur=""
    start=0
  done < "$ROOT/$path"
  if [ -n "${cur//[[:space:]]/}" ]; then
    check_req_requirement "$path" "$start" "$cur" && n=$((n + 1))
  fi

  if [ "$n" -eq 0 ]; then
    violation "$path" "-" \
      "requirement file holds NO requirement — \"-r\" of an empty file pins nothing"
  fi
  return 0
}

# ----------------------------------------------------------------------------
# R4 — does an actions/checkout drop the token?
#
# Window = the lines following the `uses:` whose indentation is at least that of
# the `uses:` KEY itself. That definition works for both `- uses:` and the
# `- name: …` / `uses:` spelling, and stops at the next step, which necessarily
# dedents.
# ----------------------------------------------------------------------------
check_persist_credentials() { # <file> <lineno> <key indent> <start index>
  local f="$1" lineno="$2" ki="$3" start="$4"
  local j line ind found_false=0 true_line=""

  N_CHECKOUT=$((N_CHECKOUT + 1))

  for ((j = start + 1; j < ${#LINES[@]}; j++)); do
    line="${LINES[j]}"
    [ -n "${line// /}" ] || continue
    ind="$(indent_of "$line")"
    [ "$ind" -ge "$ki" ] || break
    if [[ "$line" =~ persist-credentials:[[:space:]]*([A-Za-z]+) ]]; then
      if [ "${BASH_REMATCH[1]}" = "false" ]; then
        found_false=1
        break
      fi
      true_line="$line"
    fi
  done

  [ "$found_false" -eq 1 ] && return 0

  # Accepted-and-stated: a job that pushes needs the token and must say so.
  if [ -n "$true_line" ] && \
     [[ "$true_line" =~ \#[[:space:]]*needs-token:[[:space:]]*[^[:space:]] ]]; then
    return 0
  fi

  if [ -n "$true_line" ]; then
    violation "$f" "$lineno" \
      "actions/checkout keeps persist-credentials: true with NO \"# needs-token: <reason>\" — GITHUB_TOKEN stays in .git/config"
  else
    violation "$f" "$lineno" \
      "actions/checkout does NOT set persist-credentials: false — GITHUB_TOKEN stays in .git/config for every later step"
  fi
}

# ----------------------------------------------------------------------------
# R3 — is `permissions: contents: read` declared AT THE ROOT?
#
# "At the root" = column 0, i.e. outside any job. A `permissions:` inside a job
# covers THAT job only: the next one would fall back to the org default.
# ----------------------------------------------------------------------------
check_permissions() { # check_permissions <file> <effective body>
  local f="$1" body="$2"
  local line inside=0 found=0 declared=""

  while IFS= read -r line; do
    if [ "$inside" -eq 1 ]; then
      # End of block: first non-empty line back at column 0.
      if [ -n "${line// /}" ] && [[ ! "$line" =~ ^[[:space:]] ]]; then
        inside=0
      else
        if [[ "$line" =~ ^[[:space:]]+contents:[[:space:]]*([A-Za-z-]+) ]]; then
          declared="${BASH_REMATCH[1]}"
          [ "$declared" = "read" ] && found=1
        fi
        continue
      fi
    fi
    # Block form: `permissions:` alone at column 0.
    if [[ "$line" =~ ^permissions:[[:space:]]*$ ]]; then
      inside=1
      continue
    fi
    # Flow form: `permissions: { contents: read }`, also accepted — the rule is
    # about the EFFECT, not the YAML style.
    if [[ "$line" =~ ^permissions:[[:space:]]*\{ ]]; then
      declared="$(printf '%s' "$line" | sed -n 's/.*contents:[[:space:]]*\([A-Za-z-]*\).*/\1/p')"
      [ "$declared" = "read" ] && found=1
      [ -n "$declared" ] || declared="(contents absent)"
    fi
  done <<< "$body"

  if [ "$found" -ne 1 ]; then
    if [ -n "$declared" ]; then
      violation "$f" "-" \
        "root permissions: declares contents: $declared — expected \"read\""
    else
      violation "$f" "-" \
        "NO root \"permissions:\" block — the token inherits the organisation default"
    fi
  fi
}

# ============================================================================
# MAIN LOOP
# ============================================================================
if [ ! -d "$WF_DIR" ]; then
  echo "check-workflow-pins: no .github/workflows directory under \"$ROOT\"" >&2
  echo "check-workflow-pins: 0 subject analysed — an empty perimeter proves NOTHING." >&2
  exit 1
fi

shopt -s nullglob
for f in "$WF_DIR"/*.yml "$WF_DIR"/*.yaml; do
  rel="${f#"$ROOT"/}"
  N_WORKFLOWS=$((N_WORKFLOWS + 1))

  # EFFECTIVE CONTENT: fully-commented lines are replaced by an EMPTY line (not
  # deleted), so numbering keeps pointing at the real line of the file.
  if ! effective="$(sed -E 's%^[[:space:]]*#.*$%%' "$f" 2>/dev/null)"; then
    echo "check-workflow-pins: FAILED to read \"$rel\" — the control cannot conclude" >&2
    exit 1
  fi

  LINES=(); while IFS= read -r _line; do LINES+=("$_line"); done <<< "$effective"

  for ((i = 0; i < ${#LINES[@]}; i++)); do
    line="${LINES[i]}"
    [ -n "${line// /}" ] || continue
    lineno=$((i + 1))

    if [[ "$line" =~ ^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*(.+)$ ]]; then
      rest="${BASH_REMATCH[2]}"
      prefix="${line%%uses:*}"
      check_uses "$rel" "$lineno" "$rest"
      case "$rest" in
        actions/checkout@*|actions/checkout[[:space:]]*)
          check_persist_credentials "$rel" "$lineno" "${#prefix}" "$i" ;;
      esac
    fi

    # Covers `pip install`, `pip3 install`, `python -m pip install` and
    # `python3 -m pip install`: the REAL forms of this repo, not the textbook one.
    if [[ "$line" =~ (^|[^[:alnum:]_./-])pip3?[[:space:]]+install[[:space:]] ]]; then
      check_pip "$rel" "$lineno" "$line"
    fi

    # A requirement line of the inline block: `<name>==<version> …`.
    if [[ "$line" =~ ^[[:space:]]*[A-Za-z0-9][A-Za-z0-9._-]*==[^[:space:]]+ ]]; then
      check_pin_line "$rel" "$lineno" "$line"
    fi
  done

  check_permissions "$rel" "$effective"
done
shopt -u nullglob

echo "check-workflow-pins: $N_WORKFLOWS workflow(s) — $N_USES uses: site(s), $N_CHECKOUT checkout(s), $N_PIP pip line(s), $N_PINS pinned requirement(s), $N_REQFILES requirement file(s) followed — $VIOLATIONS violation(s)"

# AN EMPTY PERIMETER IS A FAILURE. "0 violations over 0 subjects" is green and
# measures nothing — the false green this guard exists in order not to produce.
if [ "$N_WORKFLOWS" -eq 0 ]; then
  echo "check-workflow-pins: NO workflow found under $WF_DIR — an empty perimeter proves NOTHING." >&2
  exit 1
fi

if [ "$VIOLATIONS" -ne 0 ]; then
  cat >&2 <<'EOF'

Workflow supply-chain pinning requires:
  * uses:        @<40 hex> followed by a "# vX.Y.Z" tag comment
                 (resolve with `git ls-remote <url> <tag>`, dereferencing `^{}`
                 for annotated tags, cross-checked against the release page)
  * pip:         --require-hashes, every package `==`-pinned, and every
                 requirement line carrying --hash=sha256:<64 hex> — inline
                 AND in a `-r <file>` of this repository, which is followed
                 (no URL, no option line, never empty)
                 (regenerate with `pip download --only-binary :all:`)
  * permissions: ROOT block with `contents: read`
  * checkout:    persist-credentials: false, unless the step states
                 `# needs-token: <reason>` because the job really pushes
EOF
  exit 1
fi
exit 0
