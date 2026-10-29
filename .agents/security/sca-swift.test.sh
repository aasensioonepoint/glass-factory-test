#!/usr/bin/env bash
# Suite for the SWIFT / iOS ecosystem of sca-scan.sh (T-00000512) — the offline
# knob, read as a TRUTH.
#
# Auto-discovered by core-scripts/run-bash-tests.sh. ZERO network, ZERO NVD key and
# ZERO real scanner: a STUB `dependency-check` on the PATH journals its argv and
# writes an empty-but-well-formed report. No header directive is needed — this
# suite never EXECUTES an absent command, because the stub is always present.
#
# WHY THIS SUITE EXISTS, and why it is a FILE of its own rather than a section in
# sca-java.test.sh: one suite per ecosystem is this repo's convention, and Swift
# is not a copy of Java here. It consumes the dependency-check CLI FLAGS
# (`--noupdate`, `-d, --data`) where Maven consumes PLUGIN PROPERTIES
# (`-DautoUpdate`, `-DdataDirectory`) — a different surface, so a shared section
# would have had to branch on the ecosystem anyway.
#
# AND SWIFT WAS THE WORSE OF THE TWO, which is the whole reason the C33 fix could
# not stop at Maven. Under the old `${NVD_OFFLINE:+…}` forwarding, `NVD_OFFLINE=0`
# turned offline mode ON. On Maven that eventually gets loud: a scan with no
# usable database falls into `produced no report` and publishes `degraded`. The
# Swift block has NO no-report branch at all — `SWIFT_STATUS` stays `scanned`.
# So on this ecosystem the inverted knob produced no report check, no `.degraded`
# line and no log. Total silence, and a `swift: scanned` a human would trust.
#
# THE SEVEN FACES
#   (s1) NVD_OFFLINE=1 + NVD_DATA_DIR  -> --noupdate AND --data forwarded, 1 nvd:
#   (s2) NVD_OFFLINE=0                 -> NOTHING forwarded, 0 nvd:  <- THE DEFECT
#   (s3) NVD_OFFLINE=true              -> --noupdate forwarded, EXACTLY 1 nvd:
#   (s4) NVD_OFFLINE=maybe             -> fails CLOSED to offline, and SAYS so: 2 nvd:
#   (s5) neither set                   -> the DEFAULT path: nothing forwarded, 0 nvd:
#   (s6) NVD_OFFLINE=TRUE              -> the CASE FOLD: 1 nvd:, NO 'non reconnu'
#   (s7) NVD_OFFLINE=no                -> the third OFF spelling: nothing, 0 nvd:
#
# (s5) is the paired face (L-00000387) and it is not redundant with (s2): it
# measures the configuration almost every real run uses. Without it, a build that
# forwarded the flags unconditionally would still be caught by (s2), but the most
# common path in production would go unmeasured.
#
# THE STATUS IS NOT OBSERVABLE, SO THESE FACES ASSERT A PROXY — the same one
# sca-java.test.sh names in its own header, said again here rather than
# cross-referenced. `SWIFT_STATUS` reaches exactly one emitter, `emit_sca`, whose
# call is MUZZLED at the byte (`>/dev/null 2>&1 || true`) and which, on a fixture
# root outside this repo, invokes a hook file that does not exist there. So no
# fixture can read `SWIFT_STATUS`. What these faces assert instead is the
# equivalent that IS observable: the site setting `SWIFT_STATUS="degraded"` is
# immediately preceded by a `.degraded` reason line, and those are its only
# writers. It is a proxy, and it is named as one instead of being dressed up as
# a status check.
#
# WHAT REDDENS WHAT (the mutation table, so a reader can check the arms are not
# decorative). Each was REPLAYED on a COPY of .agents/security/:
#   M1  restore `${NVD_OFFLINE:+--noupdate}`              -> (s2) RED
#   M2  `[ "${NVD_OFFLINE:-0}" = "1" ]` strict            -> (s3) RED
#   M3  drop the `*)` unknown branch of nvd_offline_norm   -> (s4) RED
#   M4  forward the RAW variable at the SWIFT site only    -> (s2) RED, java (d4) GREEN
#   M5  drop `tr 'A-Z' 'a-z'` from nvd_offline_norm         -> (s6) RED
# M5 is the SUBTLE one and the reason (s6) asserts three things rather than one:
# with the fold gone, `TRUE` falls to the `*)` branch, which is offline ON as
# well (fail-closed). The `--noupdate` assertion therefore stays GREEN on a fold
# that no longer exists — what reddens is the ABSENCE of `non reconnu` and the
# `nvd:` count of 1 instead of 2. An arm on the flag alone measures nothing.
# A COPY OF THE WHOLE DIRECTORY, never one script dropped in an empty dir: these
# scripts resolve their neighbours through `dirname "$0"`, so an isolated copy
# makes every cell DEGRADED and the replay measures a broken install instead of
# the mutation (measured on sca-watch.sh: 29/23 against 44/8).
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
# the faces here capture that console into SR_OUT and its siblings, so a
# sentinel key measured an occurrence INSIDE the captured output while stdout
# stayed clean.
#
# AND THIS SUITE IS THE WORSE OF THE TWO ON THAT CHANNEL: line 369 ALREADY
# prints a captured console — `ko "(s4) no [swift] prefix on the console:
# $SR_OUT"` (MEASURED: 1 such site here, 0 in sca-java.test.sh). So what keeps
# the key off stdout is not that nobody prints the capture — somebody does — it
# is link 1 (the `unset` below) plus the flag that replaced that expansion in
# sca-scan.sh. NOT the journal redaction: that is link 2 and it never sees this
# channel. DO NOT widen the claim back: the over-wide version is exactly what
# kept F-1 invisible through a whole review (L-00000111 — a doc asserting a
# guarantee the code does not hold prevents anyone from seeing the defect).
#
# ONE LINE, and it closes TEN sites at once — COUNTED on disk, not from memory:
# `grep -cF 'cat "$DCLOG"'` returns 10. Every one of those `ko` messages `cat`s
# the argv journal, and sca-scan.sh forwards the key IN ARGV
# (`${NVD_API_KEY:+--nvdApiKey "$NVD_API_KEY"}`), so a SINGLE red face printed
# the operator's key on stdout — and in CI, into an ARCHIVED log.
#
# THIS SUITE IS WHERE THE EXPOSURE WAS CREATED, which is why the finding is HIGH
# and not a medium: the argv-journal mechanism did not exist on the Swift side
# before T-00000512, so this file brought BOTH the mechanism and its ten sites.
# No "pre-existing" defence is available here.
#
# REPRODUCED, not feared: with a sentinel key on a copy of this directory the
# key appeared in this suite's stdout on the FIRST run, from the (s2) KO line —
# no mutation and no future regression needed, only `NVD_API_KEY` and
# `NVD_DATA_DIR` both exported (the state of a machine that seeded its NVD base
# WITH the key and kept it exported). `NVD_DATA_DIR` is what made the key
# reachable: see the (s2) note for the `env -u` that closes that half.
#
# COST: ZERO, and the measurement written here is now one that REPLAYS. The old
# wording claimed `grep -nF 'nvdApiKey'` over this suite returns rc=1. It does
# not — rc=0, and every match is a comment or the redaction walk below. A
# written measurement that does not reproduce is what makes people stop
# replaying it, so here is the one that does. THE CLAIM THAT BINDS: no
# ASSERTION reads the flag. The check has to exclude COMMENT lines or it counts
# its own documentation — the naive form returns 2, and both hits are the lines
# you are reading. Run from this directory:
#   LC_ALL=C grep -niF 'nvdapikey' sca-swift.test.sh |
#     LC_ALL=C grep -vE '^[0-9]+:[[:space:]]*#' | LC_ALL=C grep -c 'ok "\|ko "'
# returns 0. Case-INSENSITIVE deliberately: since F-4 the walk folds the flag to
# `nvdapikey`, so a check pinned to the `nvdApiKey` spelling would quietly stop
# seeing the code it is supposed to watch. Drop the comment filter and re-read
# the whole line: 2 non-comment hits in this file, both inside the redaction
# walk, neither an assertion. `unset` under `set -u` is safe on an already
# unset name.
#
# WHY THIS IS NOT A COSMETIC: the remedy for a disclosed secret is a credential
# ROTATION, which is the semantics the doctrine attaches to this class.
unset NVD_API_KEY

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
# Same refusal as sca-java.test.sh: an empty $TMP would make every `mkdir -p
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

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for its root.
# A Package.resolved ALONE is what makes the Swift branch fire — no package.json,
# no pom.xml, no requirements.txt, so no other SCANNER runs here.
#
# BUT `.degraded` IS NOT nvd-ONLY ON THIS FIXTURE, and assuming it was would be a
# false guarantee (L-00000111). MEASURED at T-00000512: the trivy block also
# writes `trivy: no IaC file found to scan (or scan produced no report, exit 0)`.
# That is why every count below is pinned on `^nvd:` through nvd_count() and
# never on the line count of the whole file.
make_swift_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf '{"pins":[],"version":2}\n' > "$r/Package.resolved"
  echo "$r"
}

report_dir() { echo "$1/.agents/state/local/sca-reports"; }

# THE ARGV JOURNAL'S CHANNEL IS EXPORTED BEFORE THE HEREDOC (reserve C28). The
# stub runs in a CHILD shell that sca-scan.sh has `cd`-ed into the fixture, so a
# relative path would land somewhere nobody reads and every assertion below would
# be vacuously green on an empty file. One call per line, so a count means
# something.
DCLOG="$TMP/dc-argv.log"
export DCLOG

STUBBIN="$TMP/stubbin"; mkdir -p "$STUBBIN"
cat > "$STUBBIN/dependency-check" <<'STUB'
#!/usr/bin/env bash
# Fake dependency-check CLI: journal argv REDACTED, then write an EMPTY but
# well-formed report so the gate has something real to parse and comes back GO.
# The point of these faces is the argv, not a finding — sca-java.test.sh owns
# the positive control that turns a gate red.
#
# REDACTION AT THE JOURNAL — DEFENCE IN DEPTH, LINK 2 (CWE-532, T-00000512).
# What closes the leak TODAY is the `unset NVD_API_KEY` at the head of this
# suite: link 1, the key never reaches argv. This walk closes link 2, so the
# CLASS cannot come back through a FUTURE face that legitimately exports a test
# key — whatever lands in argv, the journal that TEN KO messages `cat` back
# never holds the value.
#
# TOKEN-BASED, never a regex over the flattened string: a key is redacted WHOLE
# or not at all, and a value that happened to contain a space could not leave
# half of itself behind. It no longer matches a CLOSED LIST of spellings: three
# literals used to be the whole net, and an unrecognised spelling walked
# straight through it (F-4) — see the walk's own note below for the two
# case-insensitive nets and the value-equality backstop that replaced them.
# Still IDENTICAL to the walk in both sca-java.test.sh stubs, deliberately: two
# spellings of one control drift. The `--out` parse below accepts both of ITS
# forms for the same reason — a stub that quietly stops recognising its call
# site measures nothing.
#
# NO ASSERTION IS AFFECTED, and here is the check that reproduces — comment
# lines filtered out, because otherwise it counts this very note:
#   LC_ALL=C grep -niF 'nvdapikey' sca-swift.test.sh |
#     LC_ALL=C grep -vE '^[0-9]+:[[:space:]]*#' | LC_ALL=C grep -c 'ok "\|ko "'
# returns 0 — the non-comment hits are this walk and nothing else, so no face
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
printf '%s\n' "${_jargv# }" >> "$DCLOG"
# `--out DIR` is SPACE-separated here, unlike Maven's `-DoutputDirectory=DIR`.
# Both spellings are accepted so the stub does not silently write nowhere if the
# call site ever switches form.
outdir=""
want_out=0
for a in "$@"; do
  if [ "$want_out" -eq 1 ]; then outdir="$a"; want_out=0; continue; fi
  case "$a" in
    --out)   want_out=1 ;;
    --out=*) outdir="${a#--out=}" ;;
  esac
done
[ -n "$outdir" ] || exit 0
mkdir -p "$outdir"
# NAMED EXPLICITLY, mirroring the Maven stub: the filter reads
# `dependency-check-report.json` under --out, so writing "whatever the CLI would
# have called it" is the one thing that would make these faces vacuous.
cat > "$outdir/dependency-check-report.json" <<'JSON'
{"dependencies":[]}
JSON
exit 0
STUB
chmod +x "$STUBBIN/dependency-check"

# swift_run NAME [ENV-ARG …]: run the scan on a fresh fixture with the stub first
# on PATH, and leave the journal, the .degraded path and the output in globals.
# One helper rather than five copies, so a face reads as its ASSERTIONS.
#
# EVERY ARG AFTER NAME GOES VERBATIM TO `env`, which is why a face can pass
# `-u NVD_DATA_DIR` as well as `VAR=VAL` — `env` takes its options before its
# assignments, so no wrapper flag is needed and (s2) uses exactly the same
# stripping mechanism (s5) writes out inline. A face that must NEUTRALISE the
# runner's environment can therefore do it without a second helper.
swift_run() {
  : > "$DCLOG"
  SR_ROOT="$(make_swift_root "$1")"
  shift
  SR_OUT="$(cd "$SR_ROOT" && PATH="$STUBBIN:$PATH" env "$@" bash "$SCAN" 2>&1)"
  SR_RC=$?
  SR_DEG="$(report_dir "$SR_ROOT")/.degraded"
  SR_REPORT="$(report_dir "$SR_ROOT")/dependency-check-report.json"
}

# nvd_count: how many `nvd:` reason lines this run published. `^nvd:` and not a
# bare `nvd`, so a different ecosystem's wording can never be miscounted.
nvd_count() { LC_ALL=C grep -c '^nvd:' "$SR_DEG" 2>/dev/null || true; }

# witness FACE: NON-VACUITY FIRST, exactly as sca-java.test.sh (d) does. The
# journal must EXIST and the scan must have really been invoked BEFORE any
# presence or absence is asserted — without this opener, a run where the Swift
# branch never fired would satisfy every "flag absent" line for the worst
# possible reason.
witness() {
  [ -s "$DCLOG" ] && LC_ALL=C grep -qF -- '--enableExperimental' "$DCLOG"
}

# ---- (s1) offline WITH a pre-seeded base: both CLI flags forwarded -----------
echo "=== (s1) NVD_OFFLINE=1 + NVD_DATA_DIR => --noupdate AND --data forwarded"
FAKE_DB="$TMP/nvd-data"; mkdir -p "$FAKE_DB"
swift_run offline_with_base NVD_OFFLINE=1 NVD_DATA_DIR="$FAKE_DB"
if witness; then
  ok "(s1) witness: the dependency-check CLI was really invoked (journal non-empty)"
  [ -s "$SR_REPORT" ] \
    && ok "(s1) witness: the report landed where the filter reads it" \
    || ko "(s1) witness: no report at $SR_REPORT — the face would measure nothing"
  LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s1) --noupdate is forwarded to the CLI" \
    || ko "(s1) --noupdate missing from argv: $(cat "$DCLOG")"
  LC_ALL=C grep -qF -- "--data $FAKE_DB" "$DCLOG" \
    && ok "(s1) --data is forwarded with the caller's path" \
    || ko "(s1) --data missing from argv: $(cat "$DCLOG")"
  # A BOUNDED coverage is `degraded`: the scan is real, its freshness is not, and
  # nobody downstream can tell the difference unless it is written down.
  [ -f "$SR_DEG" ] && LC_ALL=C grep -qF 'fraîcheur non vérifiée' "$SR_DEG" \
    && ok "(s1) the unverified freshness is written to .degraded" \
    || ko "(s1) no freshness reason line: $(cat "$SR_DEG" 2>/dev/null)"
  [ "$(nvd_count)" -eq 1 ] \
    && ok "(s1) proxy: EXACTLY one nvd: line — swift coverage is published degraded" \
    || ko "(s1) expected 1 nvd: line, got $(nvd_count): $(cat "$SR_DEG" 2>/dev/null)"
  LC_ALL=C grep -qF 'COVERAGE DEGRADED' <<<"$SR_OUT" \
    && ok "(s1) the run announces COVERAGE DEGRADED" \
    || ko "(s1) no COVERAGE DEGRADED announced"
else
  ko "(s1) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s2) NVD_OFFLINE=0: THE DEFECT C33 NAMED -------------------------------
# The face that was RED before T-00000512, and the one whose silence was total on
# this ecosystem. `0` is non-empty, so `${NVD_OFFLINE:+--noupdate}` forwarded
# `--noupdate` and turned offline mode ON — the exact opposite of what the
# operator wrote — with no report branch to make it loud afterwards.
echo
echo "=== (s2) NVD_OFFLINE=0 => nothing forwarded, nothing claimed (was INVERTED)"
# `-u NVD_DATA_DIR` (T-00000512): this face pins the ABSENCE of `--data`, and
# `NVD_DATA_DIR` is forwarded on its OWN raw `:+` test, independent of the
# offline truth — so an operator with the variable exported (a normal state:
# they seeded an NVD base) made this face RED on a correct build. (s7) already
# refused to pin `--data` for exactly that reason; this face pinned it anyway,
# which is the inconsistency the review measured. MEASURED before the strip:
# `KO: (s2) a --data appeared from nowhere: … --nvdApiKey <the key> --data …` —
# the single line that carried the class-1 HIGH out of this suite.
swift_run offline_zero -u NVD_DATA_DIR NVD_OFFLINE=0
if witness; then
  ok "(s2) witness: the dependency-check CLI was really invoked (journal non-empty)"
  ! LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s2) NVD_OFFLINE=0 does NOT forward --noupdate — 0 means OFF" \
    || ko "(s2) NVD_OFFLINE=0 turned offline mode ON: $(cat "$DCLOG")"
  ! LC_ALL=C grep -qF -- '--data' "$DCLOG" \
    && ok "(s2) no --data invented when the caller gave none" \
    || ko "(s2) a --data appeared from nowhere: $(cat "$DCLOG")"
  [ "$(nvd_count)" -eq 0 ] \
    && ok "(s2) proxy: ZERO nvd: line — 0 claims no bounded coverage" \
    || ko "(s2) an nvd: line appeared on NVD_OFFLINE=0: $(cat "$SR_DEG" 2>/dev/null)"
  # PAIRED with the absences above: the run must not have DIED either, because
  # under `set -uo pipefail` an "unbound variable" exit would ALSO satisfy both
  # lines above, for a reason that has nothing to do with the knob.
  #
  # A BELT, NOT AN ARM, and said so rather than dressed up (L-00000111). The C6
  # hazard is the head of nvd_offline_norm not assigning unconditionally, and
  # MEASURED at T-00000512 that mutation does NOT redden HERE: with
  # `NVD_OFFLINE=0` the `0|false|no` branch assigns anyway. What it reddens is
  # the UNSET path, where the helper returns early — that is (s5) below, which
  # is therefore the face that really holds C6 on this ecosystem.
  ! LC_ALL=C grep -qF 'unbound variable' <<<"$SR_OUT" \
    && ok "(s2) belt: the run did not die on an unbound variable" \
    || ko "(s2) the OFF branch left a variable unset and set -u killed the run"
else
  ko "(s2) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s3) NVD_OFFLINE=true: the value a strict `= "1"` would break ----------
# The counter-face to (s2), and the one that refuses the naive fix. A correction
# written `[ "${NVD_OFFLINE:-0}" = "1" ]` would read `true` as FALSE and put an
# air-gapped run back on the network — here, with ZERO nvd: line to say so.
echo
echo "=== (s3) NVD_OFFLINE=true => --noupdate forwarded, EXACTLY 1 nvd:"
swift_run offline_true NVD_OFFLINE=true
if witness; then
  ok "(s3) witness: the dependency-check CLI was really invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s3) NVD_OFFLINE=true forwards --noupdate" \
    || ko "(s3) 'true' was not read as true — a strict = \"1\" fix is in: $(cat "$DCLOG")"
  [ -f "$SR_DEG" ] && LC_ALL=C grep -qF 'base hors-ligne (swift)' "$SR_DEG" \
    && ok "(s3) the posture is stated on 'true' exactly as on '1'" \
    || ko "(s3) no posture line on 'true': $(cat "$SR_DEG" 2>/dev/null)"
  # EXACTLY 1: a recognised value must not also draw the "non reconnu" line.
  [ "$(nvd_count)" -eq 1 ] \
    && ok "(s3) proxy: EXACTLY one nvd: line — 'true' is recognised, not flagged" \
    || ko "(s3) expected 1 nvd: line, got $(nvd_count): $(cat "$SR_DEG" 2>/dev/null)"
else
  ko "(s3) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s4) NVD_OFFLINE=maybe: fail-closed to ON, and SAID --------------------
# An unrecognised value keeps TODAY'S behaviour (ON — so a typo never puts an
# air-gapped scan on the network) but stops being SILENT about it. This face also
# covers `off`, deliberately kept OUT of the vocabulary: under a variable named
# *_OFFLINE that one token collides with the NAME, so it is NAMED rather than
# resolved in secret.
echo
echo "=== (s4) NVD_OFFLINE=maybe => still offline, and NAMED: 2 nvd:"
swift_run offline_unknown NVD_OFFLINE=maybe
if witness; then
  ok "(s4) witness: the dependency-check CLI was really invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s4) an unrecognised value fails CLOSED — still offline" \
    || ko "(s4) an unrecognised value silently went online: $(cat "$DCLOG")"
  [ -f "$SR_DEG" ] && LC_ALL=C grep -qF 'non reconnu' "$SR_DEG" \
    && ok "(s4) the unrecognised value is NAMED in .degraded" \
    || ko "(s4) fail-closed happened in SILENCE: $(cat "$SR_DEG" 2>/dev/null)"
  # The line must carry the VOCABULARY, or the reader cannot act on it.
  [ -f "$SR_DEG" ] && LC_ALL=C grep -qF '1/true/yes' "$SR_DEG" \
    && ok "(s4) the reason line spells out the accepted values" \
    || ko "(s4) 'non reconnu' without saying what IS recognised"
  # The offending value is quoted back, or the operator cannot find their typo.
  LC_ALL=C grep -qF "NVD_OFFLINE='maybe'" "$SR_DEG" \
    && ok "(s4) the offending value is quoted back to the operator" \
    || ko "(s4) the reason line does not say WHICH value was refused"
  # TWO, and the count is the point: posture + "non reconnu". (s3) pins 1 on a
  # recognised value, so this pair proves the note is CONDITIONAL, not constant.
  [ "$(nvd_count)" -eq 2 ] \
    && ok "(s4) proxy: EXACTLY two nvd: lines — posture plus the unrecognised value" \
    || ko "(s4) expected 2 nvd: lines, got $(nvd_count): $(cat "$SR_DEG" 2>/dev/null)"
  # The note is attributed to THIS ecosystem, not to a neighbour's log prefix.
  LC_ALL=C grep -qF '[swift]' <<<"$SR_OUT" \
    && ok "(s4) the console note is attributed to the swift ecosystem" \
    || ko "(s4) no [swift] prefix on the console: $SR_OUT"
else
  ko "(s4) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s5) neither variable set: the DEFAULT path ----------------------------
# THE PAIRED FACE (L-00000387): without it, a build that forwarded the flags
# unconditionally would look identical to one that reads the environment. `env -u`
# strips both variables so an exported value in the RUNNER'S own shell cannot
# make this face vacuous — measured hazard, not a precaution: this suite is run
# from a session that may legitimately have NVD_DATA_DIR set.
echo
echo "=== (s5) neither variable set => nothing forwarded, no nvd: line"
: > "$DCLOG"
SR_ROOT="$(make_swift_root online_default)"
SR_OUT="$(cd "$SR_ROOT" && PATH="$STUBBIN:$PATH" env -u NVD_OFFLINE -u NVD_DATA_DIR bash "$SCAN" 2>&1)"
SR_RC=$?
SR_DEG="$(report_dir "$SR_ROOT")/.degraded"
SR_REPORT="$(report_dir "$SR_ROOT")/dependency-check-report.json"
if witness; then
  ok "(s5) witness: the dependency-check CLI was really invoked (journal non-empty)"
  ! LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s5) no --noupdate when the caller asked for none" \
    || ko "(s5) --noupdate forwarded unconditionally: $(cat "$DCLOG")"
  ! LC_ALL=C grep -qF -- '--data' "$DCLOG" \
    && ok "(s5) no --data when the caller asked for none" \
    || ko "(s5) --data forwarded unconditionally: $(cat "$DCLOG")"
  [ "$(nvd_count)" -eq 0 ] \
    && ok "(s5) proxy: ZERO nvd: line — an online run claims no bounded coverage" \
    || ko "(s5) an nvd: line appeared without any offline knob: $(cat "$SR_DEG" 2>/dev/null)"
else
  ko "(s5) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s6) NVD_OFFLINE=TRUE: the CASE FOLD the README GUARANTEES -------------
# README-SECURITY-SCAN-SETUP.md promises, in its accepted-values table,
# "case-insensitive (`TRUE`, `Yes` work)". Until this face NOTHING in either
# suite exercised it: every arm passed `1`, `0`, `true` or `maybe`. So the
# `LC_ALL=C tr 'A-Z' 'a-z'` fold of nvd_offline_norm — the bash 3.2 substitute
# for `${raw,,}`, and the most fragile line of the helper — was a DOCUMENTED
# guarantee with zero coverage. L-00000111 read the other way round: the code
# holds it, and nothing proved it.
#
# THREE ASSERTIONS, NOT ONE, AND THE REASON IS MEASURED: a dead fold sends
# `TRUE` to the `*)` unknown branch, which is offline ON as well (fail-closed).
# A face pinning only `--noupdate` would be GREEN on a fold that no longer
# exists. What separates "recognised" from "fell through" is the side effect of
# the unknown branch: a `non reconnu` line, hence 2 `nvd:` lines instead of 1.
#
# BOUND (L-00000187): this arms the FOLD, not every spelling. `TRUE` and `Yes`
# go through the SAME single `tr` call, so one uppercase value covers the
# mechanism; `Yes` is NOT separately armed and is not claimed to be.
echo
echo "=== (s6) NVD_OFFLINE=TRUE => --noupdate forwarded, 1 nvd:, the fold ALIVE"
swift_run offline_true_upper NVD_OFFLINE=TRUE
if witness; then
  ok "(s6) witness: the dependency-check CLI was really invoked (journal non-empty)"
  LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s6) NVD_OFFLINE=TRUE forwards --noupdate" \
    || ko "(s6) 'TRUE' was not read as true — the case fold is gone: $(cat "$DCLOG")"
  # THE LINE THAT MAKES THIS FACE NON-VACUOUS (see M5 in the header table).
  [ -f "$SR_DEG" ] && ! LC_ALL=C grep -qF 'non reconnu' "$SR_DEG" \
    && ok "(s6) 'TRUE' is RECOGNISED — no 'non reconnu' line, the fold is ALIVE" \
    || ko "(s6) 'TRUE' fell through to the unknown branch, or no posture line: $(cat "$SR_DEG" 2>/dev/null)"
  [ "$(nvd_count)" -eq 1 ] \
    && ok "(s6) proxy: EXACTLY one nvd: line — posture only, no unrecognised note" \
    || ko "(s6) expected 1 nvd: line, got $(nvd_count): $(cat "$SR_DEG" 2>/dev/null)"
else
  ko "(s6) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

# ---- (s7) NVD_OFFLINE=no: the third OFF spelling, and none armed it ---------
# `no` is advertised twice — by the README table and by the reason line the
# helper prints (`faux : 0/false/no`) — while the OFF side was measured on `0`
# alone. This face catches a `case` pattern narrowed to `0|false` under a
# message that keeps promising three spellings.
#
# WHAT IT DOES NOT ASSERT, AND WHY: `--data` absence is NOT pinned here.
# `NVD_DATA_DIR` is forwarded on its own raw `:+` test, independent of the
# offline truth, so an exported value in the runner's shell would make that
# assertion fail for a reason unrelated to `no`. (s2) and (s5) own it, each
# with its own `env -u` strip — and until T-00000512 (s2) pinned it WITHOUT
# one, which is how the reasoning written here failed to reach the face next
# door.
echo
echo "=== (s7) NVD_OFFLINE=no => nothing forwarded, no nvd: line"
swift_run offline_no NVD_OFFLINE=no
if witness; then
  ok "(s7) witness: the dependency-check CLI was really invoked (journal non-empty)"
  ! LC_ALL=C grep -qF -- '--noupdate' "$DCLOG" \
    && ok "(s7) NVD_OFFLINE=no does NOT forward --noupdate — 'no' means OFF" \
    || ko "(s7) NVD_OFFLINE=no turned offline mode ON: $(cat "$DCLOG")"
  # ZERO is what separates "recognised as false" from "unrecognised": a `no`
  # falling through to `*)` would be ON *and* draw a `non reconnu` line.
  [ "$(nvd_count)" -eq 0 ] \
    && ok "(s7) proxy: ZERO nvd: line — 'no' claims no bounded coverage" \
    || ko "(s7) an nvd: line appeared on NVD_OFFLINE=no: $(cat "$SR_DEG" 2>/dev/null)"
  # Same belt as (s2), same reason: under `set -uo pipefail` a death on an
  # unbound variable would ALSO satisfy the absence above.
  ! LC_ALL=C grep -qF 'unbound variable' <<<"$SR_OUT" \
    && ok "(s7) belt: the run did not die on an unbound variable" \
    || ko "(s7) the OFF branch left a variable unset and set -u killed the run"
else
  ko "(s7) premise: the Swift branch never invoked the CLI — the face measured nothing"
fi

echo
echo "================================================================"
echo "sca-swift: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Swift SCA: the offline knob is read as a TRUTH, not as a non-empty string."
echo "0/false/no mean OFF, 1/true/yes mean ON, and any other value stays offline"
echo "but is NAMED rather than applied in silence. This is the ecosystem where the"
echo "old inversion was TOTALLY silent — no no-report branch, so swift: scanned."
