#!/usr/bin/env bash
# .agents/security/sca-watch.sh — kit-adapted from security-agents-pack-v2.
# Scheduled entry point for continuous vulnerability watch. New advisories are
# published daily against UNCHANGED dependency trees, so this runs the full scan
# even when no code moved.
#
# Schedule it (choose one):
#   cron          : 0 6 * * 1-5  cd /path/to/repo && .agents/security/sca-watch.sh
#   CI scheduled  : Jenkins cron / GitLab schedules / GitHub Actions `on: schedule`
#   Windows       : Task Scheduler -> "C:\Program Files\Git\bin\bash.exe" -lc "cd /c/path/to/repo && .agents/security/sca-watch.sh"
#
# Modes (scan-only is the default — orchestrate is an explicit governance opt-in):
#   SCA_WATCH_MODE=scan-only   -> scan + audit log, never invokes Claude
#   SCA_WATCH_MODE=orchestrate -> on a NO-GO, headless run: claude -p "watch mode: ..."
#                                 (requires a `claude` binary and an allowed inference path);
#                                 the prompt says WHICH NO-GO: findings, or a verdict NOT
#                                 obtained — fail-closed config, or an unreadable scanner
#                                 report (waiver_filter rc 3), both named when both are
#                                 present — never the one for the other; or a run that
#                                 obtained no verdict at all (a module run interrupted, the
#                                 reports lock held beyond its wait), named on its own
# The watch NEVER writes to the waiver register: only /kickoff runs create entries.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 1
OUT="$ROOT/.agents/state/local/sca-reports"; mkdir -p "$OUT"
MODE="${SCA_WATCH_MODE:-scan-only}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 0) A reports directory this watch cannot write: nothing can be recorded there —
# not the scan's verdict, not this watch's log (`tee`), audit row or digest.
# MEASURED before this test, scan-only, the scan saying `reports directory not
# writable`: with no earlier last-watch-scan.log, `tee` could not create it, the
# line went unread and the watch said "Findings"; with one, it said the run motif
# and its remedy "relancer le scan", which cannot work. Said at once, its own
# remedy, in both modes, nothing scanned, exit 1. INERT under uid 0 (`-w` always
# true there), as the scanner's own test (closing review T5).
MOTIF_NOWRITE='verdict SCA non obtenu (dossier de rapports non inscriptible — le rendre inscriptible, puis relancer)'
if [ ! -w "$OUT" ]; then
  echo "sca-watch: NO-GO — $MOTIF_NOWRITE: $OUT is not writable, so neither the scan nor this watch can record anything there — nothing scanned, auto-fix nothing."
  exit 1
fi

# 1) Full scan, no CHANGED_ONLY throttle (the advisory DBs moved, not the tree).
# `bash "<path>"`, never the file as an executable — EVERY .sh in this repo is
# mode 100644 in the git index (Windows-authored), so on a REAL POSIX checkout
# (GitHub Actions) invoking the FILE dies with Permission denied. This is the
# class T-00000307 already measured and already fixed inside sca-scan.sh itself
# (see its own note: Windows ignores the bit and Docker Desktop mounts
# everything 755, which is why neither a dev box nor the frozen-clone container
# ever saw it) — and this line was the ONE site in the repo that still got it
# wrong. Measured on an untouched tree with a HIGH-CVE fixture: the call died
# rc=126 and the watch printed "GO — no action needed", exit 0, on a repository
# it had never scanned.
# THIS run's output is kept in last-watch-scan.log (tee: it still streams). rc 1
# has THREE meanings and only the output tells them apart: real findings, or the
# fail-closed gate of sca-scan.sh — waiver_filter gave no fresh effective verdict
# — for one of two motifs: the CONFIGURATION (an invalid SCA_GATE_LEVEL, measured:
# argparse rc 2), or a scanner REPORT present but unreadable or truncated
# (waiver_filter rc 3, T-01M4X7W4M2XCFBK1MSY04X2907). The old step 6 read every
# rc 1 as findings and handed `claude -p` "high/critical findings are present" on
# a run that had established none. `.degraded` is NOT read instead: under
# --all-modules a module's marker is rebuilt only when that module runs, so a
# stale one can survive; the log of this run cannot be stale. A FOURTH meaning —
# a run that obtained no verdict at all (a module run interrupted, the reports
# lock busy) — has its own anchor below (FC_RUN_RE). BOUND, named and not closed
# here: this log and the pivot read for the digest live OUTSIDE the reports lock,
# so two concurrent watches can each describe the other's run; each one's rc
# stays its own (PIPESTATUS of its own scan).
SCAN_LOG="$OUT/last-watch-scan.log"
SCA_GATE_LEVEL="${SCA_GATE_LEVEL:-high}" bash "$SCRIPT_DIR/sca-scan.sh" | tee "$SCAN_LOG"
rc=${PIPESTATUS[0]}
# The fail-closed line as sca-scan.sh's `log` prints it (two-space indent, one
# per module that failed closed), anchored so a path or package name carrying
# the same words elsewhere on a line cannot flip the reading.
# The rc it carries tells the two motifs apart: `rc=3,` is the unreadable
# REPORT — the configuration is fine, the remedy is to re-run the scanner, and
# the report is named on the run's COVERAGE DEGRADED line; any other rc is the
# CONFIGURATION motif. The trailing comma keeps rc=30..39 out of the report
# motif. COUNTED, not merely detected, so that a log holding both motifs names
# both: FC_CONFIG means a fail-closed line whose rc is NOT 3 is present — or no
# rc=3 line was recognised at all, which keeps the reading this watch gave
# every fail-closed line before rc 3 existed.
FC_ANY='^  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=.*no fresh effective verdict (fail-closed)$'
FC_RC3='^  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=3, .*no fresh effective verdict (fail-closed)$'
MOTIF_CONFIG='verdict SCA non obtenu (fail-closed config)'
MOTIF_REPORT='verdict SCA non obtenu (rapport de scanner illisible — voir COVERAGE DEGRADED)'
# THE THIRD MOTIF: a run that obtained NO verdict at all (T-01M4Z395686TR4M7326AQ8ZPHW,
# T-01M4Z39613YVM24WCTWB56N2TH) — a module run of --all-modules that exited outside
# {0,1,2}, with 2 without its no-ecosystem line, or with 1 on its no-verdict line;
# the reports lock held by another run beyond its wait. (The scanner's "reports
# directory not writable" line matches FC_RUN_RE too, but step 0 above stops the
# watch before the scan on that directory, with its own motif.) Its lines do
# NOT name waiver_filter, so FC_ANY cannot see them: before this anchor such a run
# read as FINDINGS. Its own anchor (BRE, the `all-modules ` word optional), its own
# remedy — re-run the scan — and never the configuration's.
FC_RUN_RE='^  SCA GATE \(all-modules \)\{0,1\}(effective, waivers applied): NO-GO — .*, no verdict obtained (fail-closed)$'
MOTIF_RUN='verdict SCA non obtenu (run de module interrompu ou verrou occupé — relancer le scan)'
FAILCLOSED=0
FC_REPORT=0
FC_CONFIG=0
FC_RUN=0
if [ "$rc" = "1" ]; then
  n_fc="$(LC_ALL=C grep -c "$FC_ANY" "$SCAN_LOG" 2>/dev/null)"
  n_fc3="$(LC_ALL=C grep -c "$FC_RC3" "$SCAN_LOG" 2>/dev/null)"
  n_run="$(LC_ALL=C grep -c "$FC_RUN_RE" "$SCAN_LOG" 2>/dev/null)"
  n_fc="${n_fc:-0}"
  n_fc3="${n_fc3:-0}"
  n_run="${n_run:-0}"
  if [ "$n_fc" -gt 0 ]; then
    FAILCLOSED=1
    if [ "$n_fc3" -gt 0 ]; then FC_REPORT=1; fi
    if [ "$n_fc" -gt "$n_fc3" ] || [ "$FC_REPORT" -eq 0 ]; then FC_CONFIG=1; fi
  fi
  if [ "$n_run" -gt 0 ]; then
    FAILCLOSED=1
    FC_RUN=1
  fi
fi
# Appended to the config/report texts when a run ALSO obtained no verdict; empty
# otherwise, so those texts stay byte-identical when FC_RUN is 0.
RUN_CON=""
RUN_ADD=""
if [ "$FC_RUN" -eq 1 ]; then
  RUN_CON=" + $MOTIF_RUN"
  RUN_ADD=" Also $MOTIF_RUN: at least one run obtained NO verdict at all (a module run interrupted, or the reports lock held beyond its wait) — re-run the scan, auto-fix nothing."
fi

# 2) Watch-level audit line (sca-scan.sh already logged its own).
# The verdict is a BOUND, not an enumeration (L-00000187). It used to default to
# GO and name only rc 1 and rc 2, so EVERY other code — 126 from the refusal
# above, 127 from a missing interpreter, 124 from a timeout — read as GO. That is
# the half that made the failure SILENT: the bad invocation broke the scan, this
# line made it green. An unknown rc is a measurement NOT OBTAINED, never a pass.
case "$rc" in
  0) verdict="GO" ;;
  1) verdict="NO-GO" ;;
  2) verdict="NO-ECOSYSTEM" ;;
  *) verdict="DEGRADED" ;;
esac
# `$MODE` is the ONE field here that comes from outside (SCA_WATCH_MODE in the
# environment), and it was interpolated raw into JSON. `$TS` comes from date(1)
# and `$verdict` from the case above, so neither needs any of this. FOUR vectors,
# and they are NOT equally serious — the label matters more than the count:
#   - a `"` TRUNCATES the object, so the row stops parsing;
#   - a newline (any C0 control) forges a WHOLE EXTRA LINE in an append-only
#     audit log — a fabricated verdict in the exact file a reader consults to
#     know whether the watch ran;
#   - a byte that is not valid UTF-8 makes the row UNREADABLE to the production
#     reader: `dashboard_readers.read_new_records` decodes line by line and
#     counts a `UnicodeDecodeError` as `malformed`, so a REAL run silently
#     disappears from the Security view. This is the only one of the four with an
#     observable victim in this repo today;
#   - the NON-C0 separators — U+2028, U+2029 and U+0085 (NEL, bytes \xc2\x85) —
#     are JSON-valid and forge nothing for a reader that splits on `b"\n"`, which
#     is what every reader in this repo does. Closed PROSPECTIVELY, for a
#     consumer that splits with Python's `str.splitlines()`. And what they cost
#     THAT reader is NOT a forged row, it is the REAL one: MEASURED on the
#     unhardened form with the suite's fully delimited (g) payload, a
#     `splitlines()` reader gets 6 unparsable fragments and forged=0 — and 3
#     unparsable / forged=0 when only the NEL substitution below is stripped.
#     Either way forged=0. The escape step below has already
#     backslash-escaped the payload's quotes, so nothing it carries can parse as
#     a record — forging cleanly would take a raw `printf`, which is exactly what
#     the suite's paired witness uses. So this is the SAME damage as the invalid
#     byte above — a line LOST, unreadable — not a readable fabricated verdict.
# HOW FAR THIS CLOSES THE SEPARATOR CLASS: 10 of the 10 code points that
# `str.splitlines()` splits on, and that is a COUNT, not an absolute. Seven are
# C0 (\n \r \v \f \x1c \x1d \x1e) and fall to the `tr` below; the three others
# (U+2028, U+2029, U+0085) are substituted. Add a code point to that CPython list
# and this becomes 10 of 11 with nothing here to say so — re-derive the count,
# never trust the word "closed".
# THE ORDER OF THE FOUR STEPS BELOW IS THE CORRECTION, NOT A DETAIL.
# Re-encode to valid UTF-8 first (invalid bytes DROPPED, and dropped without a
# marker: the record then reads `scan-only`, never `scan-only?`), then strip the
# C0 controls AND DEL (`\177`), then escape backslash BEFORE quote — the other
# order would double-escape the backslashes it just introduced — and only THEN
# substitute the three non-C0 separators, for that same reason one level down:
# substituted earlier, the backslash of the `\uXXXX` each of them introduces
# would itself be escaped.
# `iconv -c` (drop invalid sequences) is POSIX; `//IGNORE` is a GNU extension and
# is deliberately not used. `LC_ALL=C` on `tr` freezes a by-the-byte behaviour on
# every host, because BSD `tr` under a UTF-8 locale is not required to agree with
# GNU `tr` about an invalid byte.
if command -v iconv >/dev/null 2>&1; then
  utf8_clean() { iconv -c -f UTF-8 -t UTF-8 2>/dev/null; }
else
  # NEVER silent: passthrough IS the old behaviour, so the one thing that must
  # not happen is a run that looks hardened and is not.
  echo "sca-watch: iconv absent — \$MODE non ré-encodé, un octet UTF-8 invalide passera dans l'audit log." >&2
  utf8_clean() { cat; }
fi
MODE_J="$(printf '%s' "$MODE" | utf8_clean | LC_ALL=C tr -d '\000-\037\177')"
MODE_J="${MODE_J//\\/\\\\}"
MODE_J="${MODE_J//\"/\\\"}"
MODE_J="${MODE_J//$'\xe2\x80\xa8'/\\u2028}"
MODE_J="${MODE_J//$'\xe2\x80\xa9'/\\u2029}"
# U+0085 (NEL) is the third one, and it was MISSED on the first pass: it is the
# only `splitlines()` separator that is neither C0 nor in the U+2028/9 pair, so
# `tr -d '\000-\037\177'` never sees it (its bytes are \xc2\x85, both >= 0x80)
# and it is valid UTF-8, so `iconv -c` keeps it. Measured before this line
# existed: one NEL made a real row read as 2 fragments of which 0 parse.
MODE_J="${MODE_J//$'\xc2\x85'/\\u0085}"
printf '{"ts":"%s","mode":"watch","entry":"sca-watch.sh","verdict":"%s","watch_mode":"%s"}\n' \
  "$TS" "$verdict" "$MODE_J" >> "$OUT/audit-log.jsonl"

# 3) DEGRADED stops here, BEFORE the digest below. The scan did not run to a
# verdict we recognise, so there is nothing to decide FROM. Two things must not
# happen on this path, and the order of the blocks is what prevents them:
#   - it must not borrow the cheap path's "no action needed" — that sentence is
#     what a reader takes as "we looked and it was fine";
#   - it must not let the human digest be REFRESHED from a stale
#     effective-verdict.json under TODAY's timestamp. That is the same lie as
#     the false GO this task closes, just on the surface a human actually reads:
#     yesterday's counters wearing today's date. So the digest is overwritten
#     with a banner that says what happened, and the digest step is skipped.
# Exit 3, distinct from GO (0), NO-GO (1) and NO-ECOSYSTEM (2), so a scheduler
# can tell "clean" from "never measured" without parsing prose.
if [ "$verdict" = "DEGRADED" ]; then
  printf '# SCA watch digest — %s\n\n**DEGRADED — no scan was performed. There are no counters for this run.**\n\n- `sca-scan.sh` exited %s, outside the recognised set {0,1,2}.\n- This file previously held the counters of an EARLIER run. They were overwritten\n  on purpose: left in place under the timestamp above, they would have read as\n  today'"'"'s measurement. Absence of figures here is the honest answer.\n- Investigate before trusting any earlier verdict in `audit-log.jsonl`.\n' \
    "$TS" "$rc" > "$OUT/last-watch-digest.md"
  echo "sca-watch: COVERAGE DEGRADED — sca-scan.sh exited $rc, which is outside {0,1,2}; NOTHING was scanned to a verdict." >&2
  echo "sca-watch: DEGRADED — no verdict obtained (this is NOT a clean run)."
  exit 3
fi

# 4) Human digest (register counters + overdue reviews). Refreshed on every
# RECOGNISED verdict — GO, NO-GO, NO-ECOSYSTEM. It is deliberately NOT reached on
# DEGRADED: see the block above, which overwrites this same file with a banner
# instead. "Always refreshed" is what this comment used to say, and it was the
# sentence that hid the problem.
# A fail-closed NO-GO puts its reason at the TOP of the digest: the counters
# below then read `?`, and a `?` alone does not say that no verdict was obtained.
# One paragraph per motif present; the report motif never borrows the
# configuration's remedy.
NOTE_CONFIG="**NO-GO — verdict SCA non obtenu (fail-closed config).** At least one module has no fresh effective verdict: waiver_filter refused the configuration (e.g. SCA_GATE_LEVEL) or returned none. This NO-GO is NOT a count of findings — see \`last-watch-scan.log\`."
NOTE_REPORT="**NO-GO — verdict SCA non obtenu (rapport de scanner illisible — voir COVERAGE DEGRADED).** At least one scanner report is present but unreadable or truncated, so waiver_filter computed no effective verdict (rc 3): a truncated report can hide a finding. This NO-GO is NOT a count of findings — the COVERAGE DEGRADED line of \`last-watch-scan.log\` names the report; re-run the scanner."
NOTE_RUN="**NO-GO — $MOTIF_RUN.** At least one run obtained NO verdict at all: a module run of --all-modules exited outside {0,1,2}, with 2 without its no-ecosystem line, or with 1 on its no-verdict line; or the reports lock was held by another run beyond its wait. This NO-GO is NOT a count of findings, and the counters below are NOT read (the pivot on disk is not this run's) — see \`last-watch-scan.log\`; re-run the scan, auto-fix nothing."
DIGEST_NOTE=""
if [ "$FC_CONFIG" -eq 1 ] && [ "$FC_REPORT" -eq 1 ]; then
  DIGEST_NOTE="$(printf '%s\n\n%s' "$NOTE_CONFIG" "$NOTE_REPORT")"
elif [ "$FC_REPORT" -eq 1 ]; then
  DIGEST_NOTE="$NOTE_REPORT"
elif [ "$FC_CONFIG" -eq 1 ]; then
  DIGEST_NOTE="$NOTE_CONFIG"
fi
if [ "$FC_RUN" -eq 1 ]; then
  if [ -n "$DIGEST_NOTE" ]; then
    DIGEST_NOTE="$(printf '%s\n\n%s' "$DIGEST_NOTE" "$NOTE_RUN")"
  else
    DIGEST_NOTE="$NOTE_RUN"
  fi
fi
# Under FC_RUN the pivot is NOT read: the run obtained no verdict, so whatever sits
# in effective-verdict.json is an earlier run's — or, on a busy lock, the HOLDER's.
"$PY" - "$OUT/effective-verdict.json" "$OUT/last-watch-digest.md" "$TS" "$DIGEST_NOTE" "$FC_RUN" <<'PY'
import json, sys
from pathlib import Path
noread = len(sys.argv) > 5 and sys.argv[5] == "1"
v = {} if noread else (json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if Path(sys.argv[1]).is_file() else {})
c = v.get("counters", {})
dflt = "?" if noread else 0
note = sys.argv[4] if len(sys.argv) > 4 else ""
lines = [f"# SCA watch digest — {sys.argv[3]}", ""] + ([note, ""] if note else []) + [
         f"- Active findings at gate: **{c.get('active_at_gate', '?')}**",
         f"- Waived: {c.get('accepted', dflt)} accepted / {c.get('pending_review', dflt)} PENDING REVIEW",
         f"- Overdue reviews (`review_by` passed): {c.get('overdue_review', dflt)}", ""]
for f in v.get("active", [])[:8]:
    lines.append(f"- `{f['package']}@{f['version']}` ({f['ecosystem']}) — {f['severity']} — {f['advisory']}")
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

# 5) Nothing to decide -> stop here (the common, cheap path). Reached only for a
# recognised verdict, so `!= 1` now means exactly GO or NO-ECOSYSTEM.
[ "$rc" != "1" ] && { echo "sca-watch: $verdict — no action needed."; exit 0; }

# 6) A NO-GO. Either hand over to the orchestrator, or leave an actionable trace —
# and say WHICH NO-GO: "findings" only when the run did not fail closed, and,
# when it did, which motif — an unreadable report is never told to "fix the
# configuration", and a run carrying both motifs names both.
if [ "$MODE" = "orchestrate" ] && command -v claude >/dev/null 2>&1; then
  if [ "$FC_CONFIG" -eq 1 ] && [ "$FC_REPORT" -eq 1 ]; then
    echo "sca-watch: NO-GO — $MOTIF_CONFIG + $MOTIF_REPORT$RUN_CON — launching headless orchestrator run (policy-bound)."
    claude -p "watch mode: invoke the security-orchestrator agent. TWO motifs, each a \
verdict NOT obtained: (1) $MOTIF_CONFIG — waiver_filter refused the configuration \
(e.g. SCA_GATE_LEVEL) or returned none for at least one module; (2) $MOTIF_REPORT — \
at least one scanner report is present but unreadable or truncated (waiver_filter rc 3), \
named on the COVERAGE DEGRADED line of .agents/state/local/sca-reports/last-watch-scan.log. \
This NO-GO is not a count of findings: claim and auto-fix nothing this run did not \
establish, report and escalate the configuration fault, re-run the scanner, never touch \
the waiver register, update the audit log and the notify digest.$RUN_ADD" \
      >> "$OUT/last-watch-run.log" 2>&1
  elif [ "$FC_REPORT" -eq 1 ]; then
    echo "sca-watch: NO-GO — $MOTIF_REPORT$RUN_CON — launching headless orchestrator run (policy-bound)."
    claude -p "watch mode: invoke the security-orchestrator agent. $MOTIF_REPORT: at least \
one scanner report under .agents/state/local/sca-reports/ is present but unreadable or \
truncated, so waiver_filter computed NO effective verdict (rc 3) — a truncated report can \
hide a finding; the COVERAGE DEGRADED line of \
.agents/state/local/sca-reports/last-watch-scan.log names the report. This NO-GO is not a \
count of findings: re-run the scanner, auto-fix nothing, never touch the waiver register, \
update the audit log and the notify digest.$RUN_ADD" \
      >> "$OUT/last-watch-run.log" 2>&1
  elif [ "$FC_CONFIG" -eq 1 ]; then
    echo "sca-watch: NO-GO — verdict SCA non obtenu (fail-closed config)$RUN_CON — launching headless orchestrator run (policy-bound)."
    claude -p "watch mode: invoke the security-orchestrator agent. verdict SCA non obtenu \
(fail-closed config): at least one module has NO fresh effective verdict — waiver_filter \
refused the configuration (e.g. SCA_GATE_LEVEL) or returned none; see \
.agents/state/local/sca-reports/last-watch-scan.log. This NO-GO is not a count of \
findings: claim and auto-fix nothing this run did not establish, report and escalate \
the configuration fault, never touch the waiver register, update the audit log and \
the notify digest.$RUN_ADD" \
      >> "$OUT/last-watch-run.log" 2>&1
  elif [ "$FC_RUN" -eq 1 ]; then
    echo "sca-watch: NO-GO — $MOTIF_RUN — launching headless orchestrator run (policy-bound)."
    claude -p "watch mode: invoke the security-orchestrator agent. $MOTIF_RUN: at least one \
run obtained NO verdict at all — \
a module run of --all-modules exited outside {0,1,2}, with 2 without its no-ecosystem line, or with 1 on its no-verdict line; \
or the reports lock was held by another run beyond its wait; see \
.agents/state/local/sca-reports/last-watch-scan.log. This NO-GO is not a count of \
findings: re-run the scan, auto-fix nothing, never touch the waiver register, update the \
audit log and the notify digest." \
      >> "$OUT/last-watch-run.log" 2>&1
  else
    echo "sca-watch: NO-GO — launching headless orchestrator run (policy-bound)."
    claude -p "watch mode: invoke the security-orchestrator agent. New or existing \
high/critical findings are present in .agents/state/local/sca-reports/. Apply .agents/security/sca-policy.json \
strictly: auto-fix only policy-eligible items on the policy branch, escalate the \
rest, never touch the waiver register, update the audit log and the notify digest." \
      >> "$OUT/last-watch-run.log" 2>&1
  fi
  echo "sca-watch: orchestrator run finished — see $OUT/last-watch-run.log and audit-log.jsonl"
elif [ "$FAILCLOSED" -eq 1 ]; then
  if [ "$FC_CONFIG" -eq 1 ]; then
    echo "sca-watch: NO-GO — scan-only mode. verdict SCA non obtenu (fail-closed config): \
at least one module has no fresh effective verdict — see $SCAN_LOG ; fix the \
configuration (e.g. SCA_GATE_LEVEL), then re-run."
  fi
  if [ "$FC_REPORT" -eq 1 ]; then
    echo "sca-watch: NO-GO — scan-only mode. $MOTIF_REPORT: at least one scanner report \
is present but unreadable or truncated (waiver_filter rc 3) — the COVERAGE DEGRADED line \
of $SCAN_LOG names it ; re-run the scanner, then re-run the watch."
  fi
  if [ "$FC_RUN" -eq 1 ]; then
    echo "sca-watch: NO-GO — scan-only mode. $MOTIF_RUN: at least one run obtained no \
verdict at all (a module run interrupted, or the reports lock held beyond its wait) — see \
$SCAN_LOG ; re-run the scan, auto-fix nothing."
  fi
  exit 1
else
  echo "sca-watch: NO-GO — scan-only mode. Findings in $OUT ; run /kickoff or the \
security-orchestrator agent interactively to remediate under policy."
  exit 1
fi
