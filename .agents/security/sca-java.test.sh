#!/usr/bin/env bash
# Suite for the JAVA ecosystem of sca-scan.sh (T-00000462) — a REAL CVE, offline.
#
# optional: dependency-check
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# allows-missing: dependency-check
#
# Auto-discovered by core-scripts/run-bash-tests.sh. ZERO network and ZERO NVD key:
# the vulnerability is emitted by a STUB `mvn` on the PATH, in the exact envelope
# waiver_filter.parse_dc iterates. The CVE is not invented — log4j-core 2.14.1 /
# CVE-2021-44228 (log4shell) is the one every Java team can check against memory,
# which is precisely why it makes a good positive control: a reader who does not
# trust this harness can still recognise the finding.
#
# WHY THIS SUITE EXISTS. Before it, the Java branch of the dispatcher had NO arm
# at all: nobody had ever watched it turn a verdict red. A scanner that has never
# been seen to fail is indistinguishable from a scanner that cannot fail, and the
# second one is worth less than nothing because it is trusted.
#
# THE FOUR + ONE CASES
#   (a) POSITIVE   — a boxed CRITICAL reaches the gate => exit 1, NO-GO.
#   (b) INCAPACITY — no mvn and no ./mvnw on PATH => degraded, NEVER a block.
#   (c) NO REPORT  — the build ran and produced nothing => degraded, never a
#                    silent "scanned". "Found nothing" and "could not look" are
#                    different facts and must not render as the same verdict.
#   (d) THE OFFLINE KNOB, EIGHT FACES — NVD_OFFLINE / NVD_DATA_DIR forwarding.
#                    Three of PRESENCE (d1-d3, T-00000462) and FIVE of TRUTH
#                    (d4-d8, T-00000512): `NVD_OFFLINE=0` used to turn offline
#                    mode ON, because the forwarding tested NON-EMPTY. (d7) and
#                    (d8) close the two spellings the README GUARANTEES and no
#                    arm exercised: the UPPERCASE fold, and `no` as an OFF.
#   (e) THE REAL TOOL — only when a pre-seeded NVD database is on this machine;
#                       otherwise a SKIP that is ANNOUNCED, never silent.
#
# WHAT REDDENS WHAT (T-00000512) — the mutation table, so a reader can check the
# arms are not decorative. Each was REPLAYED on a COPY of .agents/security/:
#   M1  restore `${NVD_OFFLINE:+…}` at the Maven forwarding  -> (d4) RED
#   M2  `[ "${NVD_OFFLINE:-0}" = "1" ]` strict everywhere    -> (d5) RED
#   M3  drop the `*)` unknown branch of nvd_offline_norm     -> (d6) RED
#   M4  forward the RAW variable at ONE site only            -> that site's
#                                                               `=0` face alone
#   M5  drop `tr 'A-Z' 'a-z'` from nvd_offline_norm           -> (d7) RED
# M5 is the SUBTLE one and the reason (d7) asserts three things rather than one:
# with the fold gone, `TRUE` falls to the `*)` branch, which is offline ON TOO
# (fail-closed). The `-DautoUpdate=false` assertion therefore stays GREEN on a
# dead fold — what reddens is the ABSENCE of `non reconnu` and the `nvd:` count
# of 1 instead of 2. An arm on the flag alone would have measured nothing.
# A COPY OF THE WHOLE DIRECTORY, never one script dropped in an empty dir: the
# scripts resolve their neighbours through `dirname "$0"`, so an isolated copy
# makes every cell DEGRADED and the replay measures a broken install instead of
# the mutation (measured on sca-watch.sh: 29/23 against 44/8).
#
# THE STATUS IS NOT OBSERVABLE, SO (d) ASSERTS A PROXY — said once, here
# (reserves C27 and C46). `JAVA_STATUS` is derived from MAVEN/GRADLE and reaches
# exactly one emitter, `emit_sca`, whose call is MUZZLED at the byte
# (`>/dev/null 2>&1 || true`) and which, on a fixture root outside this repo,
# invokes a hook file that does not exist there. The audit line carries the
# verdict and the gate level, never the per-ecosystem status. So no fixture can
# read `MAVEN_STATUS`. What (d) asserts instead is the equivalent that IS
# observable: every site setting `MAVEN_STATUS="degraded"` is immediately
# preceded by a `.degraded` reason line, and those are its only writers. It is a
# proxy, and it is named as one instead of being dressed up as a status check.
#
# FORM (bash 3.2 floor, T-00000477): heredocs at STATEMENT level only, never
# inside a quoted `"$( … )"`; `grep -F`/`-Fx` wherever a literal is pinned;
# `LC_ALL=C` on every grep and sort (L-00000342 — a helper that reads a MESSAGE
# reads a LANGUAGE unless the locale is pinned).
set -uo pipefail

# ---- THE NVD KEY NEVER ENTERS THE ARGV, NEVER REACHES STDOUT (class-1 HIGH,
# ---- CWE-532) --------------------------------------------------------------
#
# THAT IS THE BOUND, AND IT IS NARROWER THAN THE CLAIM THIS HEADER USED TO MAKE
# ("never enters this suite"). FALSIFIED BY MEASUREMENT, T-00000512 re-gate: the
# key DID enter this suite. sca-scan.sh printed it on a console line of its own
# — `(NVD_API_KEY set<KEY> / cached DB)`, finding F-1, fixed in that file — and
# every face here captures that console into OUT_A / OUT_B / OUT_C / OUT_D1..D8,
# so a sentinel key measured 1 occurrence INSIDE OUT_A while stdout stayed at 0.
#
# WHAT CLOSES OUT_*: link 1 (the `unset` below), plus the flag that replaced
# that expansion in sca-scan.sh. NOT the journal redaction — that is link 2 and
# it never sees this channel. Today no `ok`/`ko` line in THIS file prints a
# captured console var (MEASURED: 0 sites; the Swift suite already has 1, at
# sca-swift.test.sh:369), so the channel is one edit away from being printed,
# never a path that fired. DO NOT widen this back: the over-wide claim is
# exactly what kept F-1 invisible through a whole review (L-00000111 — a doc
# asserting a guarantee the code does not hold prevents anyone from seeing the
# defect).
#
# ONE LINE, and it closes ELEVEN sites at once — COUNTED on disk, not from
# memory: `grep -cF 'cat "$MVNLOG"'` returns 11, five of them added by
# T-00000512 and six pre-existing. Every one of those `ko` messages `cat`s the
# argv journal, and sca-scan.sh forwards the key IN ARGV
# (`${NVD_API_KEY:+-DnvdApiKey="$NVD_API_KEY"}`), so a SINGLE red face printed
# the operator's key on stdout — and in CI, into an ARCHIVED log.
#
# REPRODUCED, not feared: with a sentinel key on a copy of this directory the
# key appeared TWICE in this suite's stdout, from the (d2) and (d3) KO lines. No
# mutation and no future regression were needed — only `NVD_API_KEY` and
# `NVD_DATA_DIR` both exported, which is the state of a machine that seeded its
# NVD base WITH the key and kept it exported. See the `env -u` note in the (d)
# block for why the second variable is what made the first one reachable.
#
# COST: ZERO, and the measurement written here is now one that REPLAYS. The old
# wording claimed `grep -nF 'nvdApiKey'` over this suite returns rc=1. It does
# not — rc=0, and every match is a comment or one of the redaction walks below.
# A written measurement that does not reproduce is what makes people stop
# replaying it, so here is the one that does. THE CLAIM THAT BINDS: no
# ASSERTION reads the flag. The check has to exclude COMMENT lines or it counts
# its own documentation — the naive form returns 2, and both hits are the lines
# you are reading. Run from this directory:
#   LC_ALL=C grep -niF 'nvdapikey' sca-java.test.sh |
#     LC_ALL=C grep -vE '^[0-9]+:[[:space:]]*#' | LC_ALL=C grep -c 'ok "\|ko "'
# returns 0. Case-INSENSITIVE deliberately: since F-4 the walk folds the flag to
# `nvdapikey`, so a check pinned to the `nvdApiKey` spelling would quietly stop
# seeing the code it is supposed to watch. Drop the comment filter and re-read
# the whole line: 4 non-comment hits in this file, all four inside the two
# redaction walks, none of them an assertion. And (e), the only face that
# touches the REAL tool, calls
# `--noupdate` and `--advancedHelp`, never the key. `unset` under `set -u` is
# safe on an already unset name.
#
# WHY THIS IS NOT A COSMETIC: the remedy for a disclosed secret is a credential
# ROTATION, which is the semantics the doctrine attaches to this class. A stub
# that journals argv is a logging mechanism, and a logging mechanism that can
# receive a secret is CWE-532 whether or not it fired today.
unset NVD_API_KEY

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
# Same refusal as sca-python.test.sh: an empty $TMP would make every `mkdir -p
# "$TMP/x"` write at `/x` and every `cd` land in the real tree.
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for ROOT.
# A pom.xml is what makes the Maven branch fire — detection is manifest-based.
make_java_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf '<project><modelVersion>4.0.0</modelVersion></project>\n' > "$r/pom.xml"
  echo "$r"
}

report_dir() { echo "$1/.agents/state/local/sca-reports"; }

# THE ARGV JOURNAL'S CHANNEL IS EXPORTED BEFORE THE HEREDOC (reserve C28). The
# stub runs in a CHILD shell that sca-scan.sh has `cd`-ed into the fixture, so a
# relative path would land somewhere nobody reads and every assertion below would
# be vacuously green on an empty file. One call per line, so a count means
# something.
MVNLOG="$TMP/mvn-argv.log"
export MVNLOG

STUBBIN="$TMP/stubbin"; mkdir -p "$STUBBIN"
cat > "$STUBBIN/mvn" <<'STUB'
#!/usr/bin/env bash
# Fake mvn: journal argv REDACTED, then write a dependency-check report EXACTLY
# in the envelope waiver_filter.parse_dc iterates (dependencies[].packages[].id
# as a purl, dependencies[].vulnerabilities[].name/severity).
#
# REDACTION AT THE JOURNAL — DEFENCE IN DEPTH, LINK 2 (CWE-532, T-00000512).
# What closes the leak TODAY is the `unset NVD_API_KEY` at the head of this
# suite: link 1, the key never reaches argv. This walk closes link 2, so the
# CLASS cannot come back through a FUTURE face that legitimately exports a test
# key — whatever lands in argv, the journal that ELEVEN KO messages `cat` back
# never holds the value.
#
# TOKEN-BASED, never a regex over the flattened string: a key is redacted WHOLE
# or not at all, and a value that happened to contain a space could not leave
# half of itself behind. It no longer matches a CLOSED LIST of spellings: three
# literals used to be the whole net, and an unrecognised spelling walked
# straight through it (F-4) — see the walk's own note below for the two
# case-insensitive nets and the value-equality backstop that replaced them.
#
# NO ASSERTION IS AFFECTED, and here is the check that reproduces — comment
# lines filtered out, because otherwise it counts this very note:
#   LC_ALL=C grep -niF 'nvdapikey' sca-java.test.sh |
#     LC_ALL=C grep -vE '^[0-9]+:[[:space:]]*#' | LC_ALL=C grep -c 'ok "\|ko "'
# returns 0 — the non-comment hits are these walks and nothing else, so no face
# can read the flag. (`grep -nF 'nvdApiKey'` alone returns rc=0, not the rc=1
# once claimed here.) `${_jargv# }` strips the single leading space, so the
# journal line is byte-identical to the old `"$*"` whenever no key is present —
# which is every face of this suite.
_jargv=""
_jskip=0
for _a in "$@"; do
  if [ "$_jskip" -eq 1 ]; then _jargv="$_jargv <REDACTED>"; _jskip=0; continue; fi
  # FAILS CLOSED ON A SPELLING IT DOES NOT KNOW (F-4, T-00000512). The walk this
  # replaced matched THREE literal spellings and passed everything else through
  # verbatim, so `-DnvdApiKey V`, `-DNvdApiKey=V`, `--nvdapikey V` and
  # `-DnvdApiKeyX=V` each journalled the value in clear — MEASURED, not feared.
  # A redaction mechanism that fails OPEN on the unfamiliar is the opposite of
  # the control this lot exists to build. THREE nets now, the first two
  # case-INSENSITIVE:
  #   (1) any `KEY=VALUE` token whose KEY part contains `nvdapikey` loses its
  #       VALUE, however the flag is spelled, and keeps its own spelling;
  #   (2) any DASH-LED token containing `nvdapikey` and carrying no `=` arms the
  #       skip, so the FOLLOWING token is redacted. The dash is REQUIRED here on
  #       purpose: without it a mere PATH holding that substring would swallow
  #       the next argument;
  #   (3) backstop for a spelling neither net imagined — a token EQUAL to the
  #       key's value. Guarded by `-n`, and that guard is the whole point: with
  #       an UNSET key every empty token would compare equal and the entire argv
  #       would come back `<REDACTED>`, which is a broken journal, not a
  #       defence. In THIS suite link 1 unsets the key, so net 3 is inert by
  #       construction — it is here for a future face that exports a test key.
  # Journal bytes are UNCHANGED for key-free argv: a token matching no net falls
  # through to the plain append.
  case "$_a" in
    *=*)
      _lk="$(printf '%s' "${_a%%=*}" | LC_ALL=C tr 'A-Z' 'a-z')"
      case "$_lk" in
        *nvdapikey*) _jargv="$_jargv ${_a%%=*}=<REDACTED>"; continue ;;
      esac
      ;;
    -*)
      _lk="$(printf '%s' "$_a" | LC_ALL=C tr 'A-Z' 'a-z')"
      case "$_lk" in
        *nvdapikey*) _jargv="$_jargv $_a"; _jskip=1; continue ;;
      esac
      ;;
  esac
  if [ -n "${NVD_API_KEY:-}" ] && [ "$_a" = "$NVD_API_KEY" ]; then
    _jargv="$_jargv <REDACTED>"
  else
    _jargv="$_jargv $_a"
  fi
done
printf '%s\n' "${_jargv# }" >> "$MVNLOG"
outdir=""
for a in "$@"; do
  # `case` SUR PLUSIEURS LIGNES, et c'est mesuré, pas cosmétique (T-00000525) :
  # le parseur tree-sitter-bash de semgrep ne sait pas lire un `case … esac`
  # écrit sur UNE seule ligne — bash l'accepte, lui. Un seul site de cette forme
  # rend le FICHIER ENTIER non parsé, donc retiré du compte des cibles
  # inspectées par la porte SAST de classe 1. Reproduction minimale au journal,
  # S-00001400. Ne pas recompacter.
  case "$a" in
    -DoutputDirectory=*) outdir="${a#-DoutputDirectory=}" ;;
  esac
done
[ -n "$outdir" ] || exit 0
mkdir -p "$outdir"
cat > "$outdir/dependency-check-report.json" <<'JSON'
{"dependencies":[{"fileName":"log4j-core-2.14.1.jar","packages":[{"id":"pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"}],"vulnerabilities":[{"name":"CVE-2021-44228","severity":"CRITICAL"}]}]}
JSON
exit 0
STUB
chmod +x "$STUBBIN/mvn"

# A second stub that runs but produces NO report — case (c).
BAREBIN="$TMP/barebin"; mkdir -p "$BAREBIN"
cat > "$BAREBIN/mvn" <<'STUB'
#!/usr/bin/env bash
# SAME REDACTION WALK, SAME REASON as the STUBBIN stub above (see the long note
# there). It is repeated rather than cross-referenced because both stubs are
# heredoc'd into standalone files with no shared helper to hold it — and the
# alternative, redacting in one Maven stub and not the other, is exactly the
# half-applied mechanism this lot is here to correct. Case (c) only asserts the
# journal is NON-EMPTY, so nothing here depends on the bytes.
_jargv=""
_jskip=0
for _a in "$@"; do
  if [ "$_jskip" -eq 1 ]; then _jargv="$_jargv <REDACTED>"; _jskip=0; continue; fi
  # FAILS CLOSED ON A SPELLING IT DOES NOT KNOW (F-4, T-00000512). The walk this
  # replaced matched THREE literal spellings and passed everything else through
  # verbatim, so `-DnvdApiKey V`, `-DNvdApiKey=V`, `--nvdapikey V` and
  # `-DnvdApiKeyX=V` each journalled the value in clear — MEASURED, not feared.
  # A redaction mechanism that fails OPEN on the unfamiliar is the opposite of
  # the control this lot exists to build. THREE nets now, the first two
  # case-INSENSITIVE:
  #   (1) any `KEY=VALUE` token whose KEY part contains `nvdapikey` loses its
  #       VALUE, however the flag is spelled, and keeps its own spelling;
  #   (2) any DASH-LED token containing `nvdapikey` and carrying no `=` arms the
  #       skip, so the FOLLOWING token is redacted. The dash is REQUIRED here on
  #       purpose: without it a mere PATH holding that substring would swallow
  #       the next argument;
  #   (3) backstop for a spelling neither net imagined — a token EQUAL to the
  #       key's value. Guarded by `-n`, and that guard is the whole point: with
  #       an UNSET key every empty token would compare equal and the entire argv
  #       would come back `<REDACTED>`, which is a broken journal, not a
  #       defence. In THIS suite link 1 unsets the key, so net 3 is inert by
  #       construction — it is here for a future face that exports a test key.
  # Journal bytes are UNCHANGED for key-free argv: a token matching no net falls
  # through to the plain append.
  case "$_a" in
    *=*)
      _lk="$(printf '%s' "${_a%%=*}" | LC_ALL=C tr 'A-Z' 'a-z')"
      case "$_lk" in
        *nvdapikey*) _jargv="$_jargv ${_a%%=*}=<REDACTED>"; continue ;;
      esac
      ;;
    -*)
      _lk="$(printf '%s' "$_a" | LC_ALL=C tr 'A-Z' 'a-z')"
      case "$_lk" in
        *nvdapikey*) _jargv="$_jargv $_a"; _jskip=1; continue ;;
      esac
      ;;
  esac
  if [ -n "${NVD_API_KEY:-}" ] && [ "$_a" = "$NVD_API_KEY" ]; then
    _jargv="$_jargv <REDACTED>"
  else
    _jargv="$_jargv $_a"
  fi
done
printf '%s\n' "${_jargv# }" >> "$MVNLOG"
echo "simulated: NVD database missing, analysis aborted" >&2
exit 1
STUB
chmod +x "$BAREBIN/mvn"

# ---- (a) POSITIVE CONTROL: a real CVE turns the gate red ---------------------
echo "=== (a) log4j-core 2.14.1 / CVE-2021-44228 => exit 1, NO-GO"
: > "$MVNLOG"
R_A="$(make_java_root positive)"
OUT_A="$(cd "$R_A" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_a=$?
DC_A="$(report_dir "$R_A")/dependency-check-report.json"
# NON-VACUITY FIRST: prove the stub really ran and its report really landed
# where the filter looks. A green verdict assertion without this would measure
# some other ecosystem's gate, not Java's.
[ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG" \
  && ok "(a) witness: the aggregate goal was really invoked" \
  || ko "(a) witness: mvn was never called with the aggregate goal"
[ -s "$DC_A" ] && LC_ALL=C grep -qF 'log4j-core' "$DC_A" \
  && ok "(a) witness: the dependency-check report landed and names log4j-core" \
  || ko "(a) witness: no dependency-check report where the filter reads it"
[ "$rc_a" -eq 1 ] \
  && ok "(a) a CRITICAL Java CVE turns the effective gate NO-GO (exit 1)" \
  || ko "(a) expected exit 1, got $rc_a"
LC_ALL=C grep -qF 'NO-GO' <<<"$OUT_A" \
  && ok "(a) the effective gate is announced NO-GO" \
  || ko "(a) no NO-GO in the output"
# The finding must be IDENTIFIED, not merely counted: a gate that says "1 active"
# without naming the package cannot be acted on.
LC_ALL=C grep -qF 'CVE-2021-44228' "$DC_A" \
  && ok "(a) the advisory is named in the report handed to the filter" \
  || ko "(a) CVE-2021-44228 absent from the report"

# ---- (b) INCAPACITY: no mvn, no ./mvnw => degraded, never a block ------------
echo
echo "=== (b) no mvn and no ./mvnw on PATH => degraded, NEVER a block"
# Build a curated PATH that omits mvn's OWN directory rather than copying tools
# into an isolated bin: on Git Bash / MSYS `ln` COPIES binaries, which then fail
# to load their libraries (exit 127) and the case would measure nothing. The
# absence is ASSERTED below, so a strip that misses fails LOUD.
if command -v mvn >/dev/null 2>&1; then
  mvn_dir="$(cd "$(dirname "$(command -v mvn)")" 2>/dev/null && pwd)"
  BPATH=""; _oldifs="$IFS"; IFS=':'
  for d in $PATH; do
    [ -n "$d" ] || continue
    # Multi-lignes pour la même raison qu'à la ligne 243 (T-00000525).
    case "$(cd "$d" 2>/dev/null && pwd)" in
      "$mvn_dir") continue ;;
    esac
    BPATH="${BPATH:+$BPATH:}$d"
  done
  IFS="$_oldifs"
else
  BPATH="$PATH"
fi
R_B="$(make_java_root nomvn)"
OUT_B="$(cd "$R_B" && PATH="$BPATH" bash "$SCAN" 2>&1)"; rc_b=$?
if PATH="$BPATH" command -v mvn >/dev/null 2>&1; then
  ko "(b) could not simulate mvn absence — this case would measure nothing"
else
  ok "(b) premise: mvn is really absent from the curated PATH"
  DEG_B="$(report_dir "$R_B")/.degraded"
  [ -f "$DEG_B" ] && LC_ALL=C grep -qF 'maven: no ./mvnw wrapper and no mvn on PATH' "$DEG_B" \
    && ok "(b) .degraded names the missing build tool" \
    || ko "(b) .degraded does not name the maven incapacity: $(cat "$DEG_B" 2>/dev/null)"
  LC_ALL=C grep -qF 'COVERAGE DEGRADED' <<<"$OUT_B" \
    && ok "(b) the run announces COVERAGE DEGRADED" \
    || ko "(b) no COVERAGE DEGRADED announced"
  [ "$rc_b" -ne 1 ] \
    && ok "(b) an incapacity is NEVER a block (exit $rc_b, not 1)" \
    || ko "(b) mvn absence hard-blocked the gate (exit 1)"
fi

# ---- (c) THE BUILD RAN AND PRODUCED NOTHING ---------------------------------
echo
echo "=== (c) mvn runs but yields no report => degraded, never a silent scanned"
: > "$MVNLOG"
R_C="$(make_java_root noreport)"
OUT_C="$(cd "$R_C" && PATH="$BAREBIN:$PATH" bash "$SCAN" 2>&1)"; rc_c=$?
DEG_C="$(report_dir "$R_C")/.degraded"
[ -s "$MVNLOG" ] \
  && ok "(c) witness: the stub build really ran" \
  || ko "(c) witness: mvn was never invoked — this case would measure nothing"
[ ! -f "$(report_dir "$R_C")/dependency-check-report.json" ] \
  && ok "(c) premise: no report was produced" \
  || ko "(c) premise: a report exists — the fixture does not model the case"
[ -f "$DEG_C" ] && LC_ALL=C grep -qF 'dependency-check aggregate produced no report' "$DEG_C" \
  && ok "(c) an empty analysis is NAMED, not read as 'found nothing'" \
  || ko "(c) .degraded does not name the missing report: $(cat "$DEG_C" 2>/dev/null)"
[ "$rc_c" -ne 1 ] \
  && ok "(c) a missing report degrades but NEVER blocks (exit $rc_c, not 1)" \
  || ko "(c) a missing report hard-blocked the gate (exit 1)"

# ---- (d) THE OFFLINE KNOB — EIGHT FACES --------------------------------------
# Every face OPENS with non-vacuity (C25): the journal must EXIST and carry the
# aggregate goal BEFORE any presence or absence is asserted. Without that opener,
# a run that never invoked mvn would satisfy every "flag absent" line for the
# worst possible reason.
#
# (d1)-(d3) test PRESENCE — is the knob forwarded when the caller sets it, and
# left alone when they do not. (d4)-(d8) test TRUTH, which is a different
# question and was the defect: under `${NVD_OFFLINE:+…}` the value `0` is
# non-empty, so it forwarded `-DautoUpdate=false` and turned offline mode ON.
#
# ---- `env -u`: THE RUNNER'S OWN ENVIRONMENT IS NOT A FIXTURE (T-00000512) ----
# FOUR of these faces assert something that DEPENDS on `NVD_DATA_DIR` being
# absent — either the absence of `-DdataDirectory=` in argv, or the posture
# WORDING, which sca-scan.sh chooses between `base hors-ligne (<path>)` and
# `SANS répertoire de base` on exactly that variable. An operator with
# `NVD_DATA_DIR` exported is a NORMAL configuration (they seeded an NVD base),
# so without `env -u` those faces are RED on a correct build, and their KO
# messages `cat` the argv journal.
#
# MEASURED before the fix, sentinel key exported, one run, no mutation:
#   (d2) BOTH assertions RED — and its KO printed the key
#   (d3) RED               — and its KO printed the key
#   (d5) RED               — KO cats .degraded, no key in it
#   (d7) GREEN             — it pins the flag, an absence and a count, none of
#                            which depend on the variable (its own note below
#                            already said so, and the measurement agrees)
#
# THE CHOICE, of the two the review offered: `env -u NVD_DATA_DIR` on the
# invocations, NOT "stop pinning a label that depends on NVD_DATA_DIR". The
# label is the most valuable assertion of (d2) — `SANS répertoire de base` is
# the wording for the single most dangerous false GO of this ecosystem — so it
# is the ENVIRONMENT that gets neutralised, not the assertion. This is also the
# treatment (s5) already applies on the Swift side; the Java pendant simply
# never received it.
#
# BOUND (L-00000187): the strip is applied to (d2), (d3), (d5) and (d7), which
# are the faces whose assertions depend on the variable. (d1) SETS
# `NVD_DATA_DIR` itself, so it needs nothing; (d4), (d6) and (d8) pin no
# path-dependent label; (a), (b) and (c) assert verdicts and report presence,
# which no offline knob moves. `-u NVD_OFFLINE` is added to (d3) as well,
# because "neither variable set" is its PREMISE and it was stripping neither —
# the exact form (s5) uses.
echo
echo "=== (d) NVD_OFFLINE / NVD_DATA_DIR forwarding, eight faces"

# -- face 1: offline WITH a pre-seeded base --------------------------------
: > "$MVNLOG"
R_D1="$(make_java_root offline_with_base)"
FAKE_DB="$TMP/nvd-data"; mkdir -p "$FAKE_DB"
OUT_D1="$(cd "$R_D1" && PATH="$STUBBIN:$PATH" NVD_OFFLINE=1 NVD_DATA_DIR="$FAKE_DB" bash "$SCAN" 2>&1)"; rc_d1=$?
DEG_D1="$(report_dir "$R_D1")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d1) witness: the aggregate goal was invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d1) -DautoUpdate=false is forwarded to the plugin" \
    || ko "(d1) -DautoUpdate=false missing from argv: $(cat "$MVNLOG")"
  LC_ALL=C grep -qF -- "-DdataDirectory=$FAKE_DB" "$MVNLOG" \
    && ok "(d1) -DdataDirectory is forwarded with the caller's path" \
    || ko "(d1) -DdataDirectory missing from argv: $(cat "$MVNLOG")"
  # A BOUNDED coverage is `degraded`, exactly as an excluded Python dependency
  # is. The scan is real; its freshness is not, and nobody downstream can tell
  # the difference unless it is written down.
  [ -f "$DEG_D1" ] && LC_ALL=C grep -qF 'fraîcheur non vérifiée' "$DEG_D1" \
    && ok "(d1) the unverified freshness is written to .degraded" \
    || ko "(d1) no freshness reason line: $(cat "$DEG_D1" 2>/dev/null)"
  # PROXY for MAVEN_STATUS=degraded -> JAVA_STATUS=degraded (see the header).
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D1" 2>/dev/null || true)" -eq 1 ] \
    && ok "(d1) proxy: EXACTLY one nvd: line — java coverage is published degraded" \
    || ko "(d1) expected 1 nvd: line, got $(LC_ALL=C grep -c '^nvd:' "$DEG_D1" 2>/dev/null || true)"
  LC_ALL=C grep -qF 'COVERAGE DEGRADED' <<<"$OUT_D1" \
    && ok "(d1) the run announces COVERAGE DEGRADED" \
    || ko "(d1) no COVERAGE DEGRADED announced"
else
  ko "(d1) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 2: offline WITHOUT any base -- the most dangerous state -----------
: > "$MVNLOG"
R_D2="$(make_java_root offline_no_base)"
# `env -u NVD_DATA_DIR` (see the block note above): this face asserts BOTH the
# absence of `-DdataDirectory=` and the `SANS répertoire de base` wording, and
# both flip if the runner has the variable exported. MEASURED red, twice, before
# the strip — and one of the two KO lines printed the sentinel key.
OUT_D2="$(cd "$R_D2" && PATH="$STUBBIN:$PATH" env -u NVD_DATA_DIR NVD_OFFLINE=1 bash "$SCAN" 2>&1)"; rc_d2=$?
DEG_D2="$(report_dir "$R_D2")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d2) witness: the aggregate goal was invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d2) -DautoUpdate=false is still forwarded" \
    || ko "(d2) -DautoUpdate=false missing from argv: $(cat "$MVNLOG")"
  # ABSENCE, paired with the presence just above in the SAME journal.
  ! LC_ALL=C grep -qF -- '-DdataDirectory=' "$MVNLOG" \
    && ok "(d2) -DdataDirectory is NOT invented when the caller gave none" \
    || ko "(d2) a dataDirectory appeared from nowhere: $(cat "$MVNLOG")"
  # Offline with no database at all: an empty finding list means "did not look",
  # not "found nothing". This is the single most dangerous false GO of the
  # ecosystem, so it gets its own wording.
  [ -f "$DEG_D2" ] && LC_ALL=C grep -qF 'SANS répertoire de base' "$DEG_D2" \
    && ok "(d2) the missing base is NAMED — coverage NON GARANTIE" \
    || ko "(d2) no 'SANS répertoire de base' line: $(cat "$DEG_D2" 2>/dev/null)"
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D2" 2>/dev/null || true)" -eq 1 ] \
    && ok "(d2) proxy: EXACTLY one nvd: line — java coverage is published degraded" \
    || ko "(d2) expected 1 nvd: line, got $(LC_ALL=C grep -c '^nvd:' "$DEG_D2" 2>/dev/null || true)"
else
  ko "(d2) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 3: neither variable set -- nothing is forwarded, nothing is claimed
# `env -u NVD_OFFLINE -u NVD_DATA_DIR`, the EXACT form (s5) uses: "neither
# variable set" is this face's PREMISE, and until T-00000512 it stripped
# neither — it merely hoped the runner's shell was empty. MEASURED red before
# the strip, and its KO line printed the sentinel key.
: > "$MVNLOG"
R_D3="$(make_java_root online_default)"
OUT_D3="$(cd "$R_D3" && PATH="$STUBBIN:$PATH" env -u NVD_OFFLINE -u NVD_DATA_DIR bash "$SCAN" 2>&1)"; rc_d3=$?
DEG_D3="$(report_dir "$R_D3")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d3) witness: the aggregate goal was invoked (journal non-empty)"
  # THE PAIRED FACE (L-00000387): without it, a build that forwarded the flags
  # unconditionally would look identical to one that reads the environment.
  ! LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d3) no -DautoUpdate when the caller asked for none" \
    || ko "(d3) -DautoUpdate=false forwarded unconditionally: $(cat "$MVNLOG")"
  ! LC_ALL=C grep -qF -- '-DdataDirectory=' "$MVNLOG" \
    && ok "(d3) no -DdataDirectory when the caller asked for none" \
    || ko "(d3) -DdataDirectory forwarded unconditionally: $(cat "$MVNLOG")"
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D3" 2>/dev/null || true)" -eq 0 ] \
    && ok "(d3) proxy: ZERO nvd: line — an online run claims no bounded coverage" \
    || ko "(d3) an nvd: line appeared without any offline knob"
else
  ko "(d3) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 4: NVD_OFFLINE=0 -- THE DEFECT C33 NAMED (T-00000512) -------------
# The face that was RED before this lot. `0` is non-empty, so `${NVD_OFFLINE:+…}`
# forwarded `-DautoUpdate=false` and turned offline mode ON — the exact opposite
# of what the operator wrote. Note this is the ONE face where the old code was
# not merely silent but INVERTED, so it is asserted as an ABSENCE paired with the
# journal witness: without the witness, a run that never called mvn would satisfy
# "no -DautoUpdate" for the worst possible reason.
: > "$MVNLOG"
R_D4="$(make_java_root offline_zero)"
OUT_D4="$(cd "$R_D4" && PATH="$STUBBIN:$PATH" NVD_OFFLINE=0 bash "$SCAN" 2>&1)"; rc_d4=$?
DEG_D4="$(report_dir "$R_D4")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d4) witness: the aggregate goal was invoked (journal non-empty)"
  ! LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d4) NVD_OFFLINE=0 does NOT forward -DautoUpdate — 0 means OFF" \
    || ko "(d4) NVD_OFFLINE=0 turned offline mode ON: $(cat "$MVNLOG")"
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D4" 2>/dev/null || true)" -eq 0 ] \
    && ok "(d4) proxy: ZERO nvd: line — 0 claims no bounded coverage" \
    || ko "(d4) an nvd: line appeared on NVD_OFFLINE=0: $(cat "$DEG_D4" 2>/dev/null)"
  # PAIRED with the absence above: the run must not have DIED either, because
  # under `set -uo pipefail` an "unbound variable" exit would ALSO satisfy the
  # two lines above, for a reason that has nothing to do with the knob.
  #
  # A BELT, NOT AN ARM, and said so rather than dressed up (L-00000111). The C6
  # hazard is the head of nvd_offline_norm not assigning unconditionally, and
  # MEASURED at T-00000512 that mutation does NOT redden HERE: with
  # `NVD_OFFLINE=0` the `0|false|no` branch assigns anyway. What it reddens is
  # the UNSET path, where the helper returns early — (a), (c) and (d3) below.
  # The plan expected (d4) to catch it; it does not. Kept because it costs one
  # grep and it keeps a green here from ever meaning "the script died".
  ! LC_ALL=C grep -qF 'unbound variable' <<<"$OUT_D4" \
    && ok "(d4) belt: the run did not die on an unbound variable" \
    || ko "(d4) the OFF branch left a variable unset and set -u killed the run"
else
  ko "(d4) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 5: NVD_OFFLINE=true -- the value a strict `= "1"` would break -----
# The counter-face to (d4), and the one that refuses the naive fix. A correction
# written `[ "${NVD_OFFLINE:-0}" = "1" ]` would read `true` as FALSE and silently
# put an air-gapped run back on the network, with ZERO nvd: line to say so.
: > "$MVNLOG"
R_D5="$(make_java_root offline_true)"
# `env -u NVD_DATA_DIR`: this face pins the `SANS répertoire de base` posture
# wording, which sca-scan.sh only writes when NVD_DATA_DIR is ABSENT. This is
# the KO the review reported — `(d5) no posture line on 'true'` — a RED on a
# correct build, produced by the runner's environment alone.
OUT_D5="$(cd "$R_D5" && PATH="$STUBBIN:$PATH" env -u NVD_DATA_DIR NVD_OFFLINE=true bash "$SCAN" 2>&1)"; rc_d5=$?
DEG_D5="$(report_dir "$R_D5")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d5) witness: the aggregate goal was invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d5) NVD_OFFLINE=true forwards -DautoUpdate=false" \
    || ko "(d5) 'true' was not read as true — a strict = \"1\" fix is in: $(cat "$MVNLOG")"
  [ -f "$DEG_D5" ] && LC_ALL=C grep -qF 'SANS répertoire de base' "$DEG_D5" \
    && ok "(d5) the posture is stated on 'true' exactly as on '1'" \
    || ko "(d5) no posture line on 'true': $(cat "$DEG_D5" 2>/dev/null)"
  # EXACTLY 1: a recognised value must not also draw the "non reconnu" line.
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D5" 2>/dev/null || true)" -eq 1 ] \
    && ok "(d5) proxy: EXACTLY one nvd: line — 'true' is recognised, not flagged" \
    || ko "(d5) expected 1 nvd: line, got $(LC_ALL=C grep -c '^nvd:' "$DEG_D5" 2>/dev/null || true): $(cat "$DEG_D5" 2>/dev/null)"
else
  ko "(d5) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 6: NVD_OFFLINE=maybe -- fail-closed to ON, and SAID ---------------
# An unrecognised value keeps TODAY'S behaviour (ON — so a typo never puts an
# air-gapped scan on the network) but stops being SILENT about it. This face is
# also what covers `off`, deliberately kept OUT of the vocabulary: under a
# variable named *_OFFLINE that token collides with the NAME, so it is NAMED
# rather than resolved in secret.
: > "$MVNLOG"
R_D6="$(make_java_root offline_unknown)"
OUT_D6="$(cd "$R_D6" && PATH="$STUBBIN:$PATH" NVD_OFFLINE=maybe bash "$SCAN" 2>&1)"; rc_d6=$?
DEG_D6="$(report_dir "$R_D6")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d6) witness: the aggregate goal was invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d6) an unrecognised value fails CLOSED — still offline" \
    || ko "(d6) an unrecognised value silently went online: $(cat "$MVNLOG")"
  [ -f "$DEG_D6" ] && LC_ALL=C grep -qF 'non reconnu' "$DEG_D6" \
    && ok "(d6) the unrecognised value is NAMED in .degraded" \
    || ko "(d6) fail-closed happened in SILENCE: $(cat "$DEG_D6" 2>/dev/null)"
  # The line must carry the VOCABULARY, or the reader cannot act on it.
  [ -f "$DEG_D6" ] && LC_ALL=C grep -qF '1/true/yes' "$DEG_D6" \
    && ok "(d6) the reason line spells out the accepted values" \
    || ko "(d6) 'non reconnu' without saying what IS recognised"
  # TWO, and the count is the point: posture + "non reconnu". (d5) pins 1 on a
  # recognised value, so this pair proves the note is CONDITIONAL, not constant.
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D6" 2>/dev/null || true)" -eq 2 ] \
    && ok "(d6) proxy: EXACTLY two nvd: lines — posture plus the unrecognised value" \
    || ko "(d6) expected 2 nvd: lines, got $(LC_ALL=C grep -c '^nvd:' "$DEG_D6" 2>/dev/null || true): $(cat "$DEG_D6" 2>/dev/null)"
  # The raw value reaches a HUMAN-read banner, so it goes through
  # sanitize_display like any untrusted string — asserted here as the value
  # being ECHOED BACK at all, which is what makes the line actionable.
  LC_ALL=C grep -qF "NVD_OFFLINE='maybe'" "$DEG_D6" \
    && ok "(d6) the offending value is quoted back to the operator" \
    || ko "(d6) the reason line does not say WHICH value was refused"
else
  ko "(d6) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 7: NVD_OFFLINE=TRUE -- the CASE FOLD the README GUARANTEES --------
# README-SECURITY-SCAN-SETUP.md promises, in its accepted-values table,
# "case-insensitive (`TRUE`, `Yes` work)". Until this face NOTHING exercised it:
# every arm of both suites passed `1`, `0`, `true` or `maybe`. So the
# `LC_ALL=C tr 'A-Z' 'a-z'` fold of nvd_offline_norm — the bash 3.2 substitute
# for `${raw,,}`, and the most fragile line of the helper — was a DOCUMENTED
# guarantee with zero coverage. L-00000111 read the other way round: the code
# holds it, and nothing proved it.
#
# THREE ASSERTIONS, NOT ONE, AND THE REASON IS MEASURED: a dead fold sends
# `TRUE` to the `*)` unknown branch, which is offline ON as well (fail-closed).
# A face pinning only `-DautoUpdate=false` would be GREEN on a fold that no
# longer exists. What separates "recognised" from "fell through" is the side
# effect of the unknown branch: a `non reconnu` line, hence 2 `nvd:` lines
# instead of 1.
#
# BOUND (L-00000187): this arms the FOLD, not every spelling. `TRUE` and `Yes`
# go through the SAME single `tr` call, so one uppercase value covers the
# mechanism; `Yes` is NOT separately armed and is not claimed to be.
#
# The posture WORDING is deliberately not asserted here, and it STAYS that way
# after T-00000512 even though `env -u NVD_DATA_DIR` would now make it stable:
# one face, one question. (d2) and (d5) own the wording; this face owns the
# FOLD. The strip is applied all the same, because a face whose greenness is
# only accidental is a face nobody can reason about — MEASURED: (d7) was the one
# of the four that stayed GREEN with the variable exported, since the flag, the
# absence of `non reconnu` and the count of 1 genuinely do not depend on it.
: > "$MVNLOG"
R_D7="$(make_java_root offline_true_upper)"
OUT_D7="$(cd "$R_D7" && PATH="$STUBBIN:$PATH" env -u NVD_DATA_DIR NVD_OFFLINE=TRUE bash "$SCAN" 2>&1)"; rc_d7=$?
DEG_D7="$(report_dir "$R_D7")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d7) witness: the aggregate goal was invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d7) NVD_OFFLINE=TRUE forwards -DautoUpdate=false" \
    || ko "(d7) 'TRUE' was not read as true — the case fold is gone: $(cat "$MVNLOG")"
  # THE LINE THAT MAKES THIS FACE NON-VACUOUS (see M5 in the header table).
  [ -f "$DEG_D7" ] && ! LC_ALL=C grep -qF 'non reconnu' "$DEG_D7" \
    && ok "(d7) 'TRUE' is RECOGNISED — no 'non reconnu' line, the fold is ALIVE" \
    || ko "(d7) 'TRUE' fell through to the unknown branch, or no posture was written: $(cat "$DEG_D7" 2>/dev/null)"
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D7" 2>/dev/null || true)" -eq 1 ] \
    && ok "(d7) proxy: EXACTLY one nvd: line — posture only, no unrecognised note" \
    || ko "(d7) expected 1 nvd: line, got $(LC_ALL=C grep -c '^nvd:' "$DEG_D7" 2>/dev/null || true): $(cat "$DEG_D7" 2>/dev/null)"
else
  ko "(d7) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# -- face 8: NVD_OFFLINE=no -- the OFF spelling no arm exercised -------------
# `no` is advertised twice — by the README table and by the reason line the
# helper itself prints (`faux : 0/false/no`) — and the OFF side was measured on
# `0` alone. This is the face that catches a `case` pattern narrowed to
# `0|false` while the message keeps promising three spellings: the divergence
# between what the code accepts and what the text claims, which is the shape
# (d6) refuses for the ON side.
#
# ZERO nvd: is what distinguishes "recognised as false" from "unrecognised": a
# `no` falling through to `*)` would be offline ON *and* draw a `non reconnu`
# line, so the count separates the two outcomes the flag alone cannot.
: > "$MVNLOG"
R_D8="$(make_java_root offline_no)"
OUT_D8="$(cd "$R_D8" && PATH="$STUBBIN:$PATH" NVD_OFFLINE=no bash "$SCAN" 2>&1)"; rc_d8=$?
DEG_D8="$(report_dir "$R_D8")/.degraded"
if [ -s "$MVNLOG" ] && LC_ALL=C grep -qF 'dependency-check-maven:aggregate' "$MVNLOG"; then
  ok "(d8) witness: the aggregate goal was invoked (journal non-empty)"
  ! LC_ALL=C grep -qF -- '-DautoUpdate=false' "$MVNLOG" \
    && ok "(d8) NVD_OFFLINE=no does NOT forward -DautoUpdate — 'no' means OFF" \
    || ko "(d8) NVD_OFFLINE=no turned offline mode ON: $(cat "$MVNLOG")"
  [ "$(LC_ALL=C grep -c '^nvd:' "$DEG_D8" 2>/dev/null || true)" -eq 0 ] \
    && ok "(d8) proxy: ZERO nvd: line — 'no' claims no bounded coverage" \
    || ko "(d8) an nvd: line appeared on NVD_OFFLINE=no: $(cat "$DEG_D8" 2>/dev/null)"
  # Same belt as (d4), same reason: under `set -uo pipefail` a death on an
  # unbound variable would ALSO satisfy the absence above.
  ! LC_ALL=C grep -qF 'unbound variable' <<<"$OUT_D8" \
    && ok "(d8) belt: the run did not die on an unbound variable" \
    || ko "(d8) the OFF branch left a variable unset and set -u killed the run"
else
  ko "(d8) premise: empty journal or no aggregate goal — the face measured nothing"
fi

# ---- (e) THE REAL TOOL, only where a pre-seeded database exists ---------------
echo
echo "=== (e) real dependency-check --noupdate (only with a seeded NVD database)"
# `--noupdate` is documented in `dependency-check --help`; `-d, --data <path>` is
# NOT — it appears only under `--advancedHelp` (MEASURED on dependency-check-cli
# 13.0.0, T-00000462). A `--help`-only check would have concluded the flag did
# not exist. The pair is confirmed on the ADVANCED surface, which is what the
# README tells an adopter to read.
ODC_DB=""
for cand in "${NVD_DATA_DIR:-}" "$HOME/.dependency-check/data" "/usr/local/share/dependency-check/data"; do
  [ -n "$cand" ] || continue
  [ -f "$cand/odc.mv.db" ] && { ODC_DB="$cand"; break; }
done
if ! command -v dependency-check >/dev/null 2>&1; then
  echo "  SKIP (e): dependency-check CLI absent de ce poste — l outil RÉEL n'est PAS mesuré"
elif [ -z "$ODC_DB" ]; then
  echo "  SKIP (e): aucune base NVD pré-chargée (odc.mv.db introuvable) — --noupdate NON mesuré"
else
  DC_HELP="$TMP/dc-advhelp.txt"
  dependency-check --advancedHelp > "$DC_HELP" 2>&1 || true
  LC_ALL=C grep -qE -- '--noupdate' "$DC_HELP" \
    && ok "(e) the real CLI advertises --noupdate" \
    || ko "(e) --noupdate absent from --advancedHelp on this version"
  LC_ALL=C grep -qE -- '--data' "$DC_HELP" \
    && ok "(e) the real CLI advertises --data (advanced surface, not --help)" \
    || ko "(e) --data absent from --advancedHelp on this version"
fi

echo
echo "================================================================"
echo "sca-java: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Java SCA: a real CVE (log4j-core 2.14.1 / CVE-2021-44228) turns the gate red"
echo "with no network and no NVD key; an absent build tool and an empty analysis"
echo "both DEGRADE without ever blocking; and an offline NVD base is published as"
echo "bounded coverage rather than passed off as a clean scan. Since T-00000512"
echo "the knob is read as a TRUTH: 0/false/no mean OFF, 1/true/yes mean ON, and"
echo "anything else stays offline but is NAMED instead of applied in silence."
