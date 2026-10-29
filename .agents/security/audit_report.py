#!/usr/bin/env python3
"""Render the /audit HTML report from the SCA report artefacts. stdlib only.

Inputs (under --reports-dir):
  modules/summary.json + modules/<slug>/effective-verdict.json  multi-module scan
    (exception: the repo root itself reports at the root of --reports-dir, never
    modules/root/ — T-00000291; summary.json entries carry the true path in reports_dir)
  effective-verdict.json                                        mono-module fallback
  code-review.json                                              optional (single-shot review)
  code-review.pass-<k>.json                                     /audit -global passes, read
    ONLY under --global: k = 1 the census, k >= 2 the pass of lot k-1 of
    code-review.lots.json (`census` and `findings` top-level, every other key under
    `stats`: the contract of security-code-review-global § Output). Merged into the code-review section with a coverage
    line R/C files — rates DECLARED by the agent, its consistency, not the repo's
    coverage — and an INCOMPLETE banner. Never touches the summary: the global
    verdict, the no-verdict line and the pivot check stay the SCA's alone.
  code-review.lots.json                                         written by --lots
  audit-qualifiers.json                                         optional
  --waivers register (default .agents/security/sca-waivers.json) for the annex
  audit-log.jsonl                                               its LAST sca-scan.sh
    row of either mode, and its last row of the rendered mode (all-modules when
    summary.json exists, else scan/root): when either says a run obtained NO verdict
    (`reason` lock-busy or aborted), the badge turns NO-GO and the page says the
    rows date from the earlier summary. A run cut by TERM or HUP writes its
    `aborted` row (sca-scan.sh's cleanup, F2b), read just above; one killed by
    KILL or INT writes no row: under a summary not NO-GO, a module whose summary
    counters differ from its pivot's turns the badge NO-GO too (that pivot is a
    later run's). BOUND: a run so killed before any pivot changed, or whose new
    pivot carries the same counters, is not seen — the earlier GO stands.

Output: audit-<YYYYMMDD-HHMMSS>.html + a refreshed audit-latest.html copy.
  --lots reads code-review.pass-1.json alone (no SCA input needed), writes
  code-review.lots.json and prints it (stdout: that JSON alone; stderr: the lot
  count, the token estimate, any stale pass purged). Paths are judged against the
  CURRENT directory (realpath): run from the repo root.
  --clear (/audit step 3) deletes, under --reports-dir only and by fixed name,
  code-review.json, code-review.lots.json, audit-latest.html and every
  code-review.pass-*.json, then stops: safe-bash refuses `rm` there, so the purge
  is code. Timestamped audit-*.html reports are kept.
Exit: 0 rendered (or lots written, or cleared) ; 2 no scan input found (or --lots:
pass 1 without a readable census) ; 1 --clear could not remove a file (named on
stderr). Every dynamic string is HTML-escaped.
"""
import argparse
import html
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEV_COLOR = {"critical": "#7f1d1d", "high": "#b91c1c", "medium": "#b45309", "low": "#52525b"}
BADGE_COLOR = {"GO": "#15803d", "NO-GO": "#b91c1c", "NO-ECOSYSTEM": "#52525b"}

CSS = """
*{box-sizing:border-box}body{font:14px/1.5 -apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#18181b;margin:0;background:#fafafa}
header,section{max-width:1000px;margin:0 auto;padding:14px 24px}
header{padding-top:28px}h1{display:inline-block;font-size:22px;margin:0 12px 4px 0}
h2{font-size:16px;border-bottom:1px solid #e4e4e7;padding-bottom:6px;margin-top:8px}
.badge{display:inline-block;color:#fff;font-weight:700;padding:4px 14px;border-radius:14px;vertical-align:middle}
.meta{color:#71717a;font-size:12px;margin:4px 0}
.tiles{display:flex;flex-wrap:wrap;gap:12px}
.tile{background:#fff;border:1px solid #e4e4e7;border-radius:8px;padding:12px 16px;min-width:130px}
.tile .num{font-size:20px;font-weight:700}.tile .lbl{color:#71717a;font-size:12px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px}
th,td{border:1px solid #e4e4e7;padding:6px 10px;text-align:left;vertical-align:top}
th{background:#f4f4f5}tr:nth-child(even) td{background:#fafafa}
code{font:12px ui-monospace,Consolas,monospace;background:#f4f4f5;padding:1px 4px;border-radius:4px}
.chip{color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap}
.note{color:#71717a;font-size:12px}
@media print{body{background:#fff}.tile,table,tr{break-inside:avoid}}
"""


def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)


def load(path):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):  # deep nesting raises under Python <= 3.12
        return None


def _verdict_path(rd, module):
    """Resolve a module's effective-verdict.json from its reports_dir, not its slug.

    Since T-00000291 the root module writes to the ROOT of sca-reports, not
    modules/root/, so a slug-built path (modules/<slug>/) would read an empty
    verdict for it and the HTML report would under-declare — the root row would
    show blank counters. The summary entry already records where each module
    wrote via `reports_dir` (relative to the repo root); we re-anchor it under
    `rd` (the --reports-dir the report is rendered from) by taking the tail
    after the `sca-reports` segment. Missing reports_dir falls back to the legacy
    slug-based path so older summaries still render.
    """
    rdir = module.get("reports_dir") or ""
    parts = Path(rdir).parts
    if "sca-reports" in parts:
        tail = parts[parts.index("sca-reports") + 1:]
        return rd.joinpath(*tail, "effective-verdict.json")
    return rd / "modules" / module["slug"] / "effective-verdict.json"


_SCAN_MODES = ("scan", "all-modules")
_NO_VERDICT = ("lock-busy", "aborted")


def _last_row(rd, mode=None, module=None):
    """The LAST sca-scan.sh audit-log.jsonl row of `mode` (and `module`) — of
    either mode when `mode` is None — or None.

    A lock-busy or aborted run writes nothing in the reports directory but this
    row (sca-scan.sh lock_busy, run_aborted): the summary and the pivots on disk
    are an EARLIER run's. Measured before (closing review E3): a GO summary dated
    2000, a lock held by a live process, `--all-modules` rc 1 lock-busy — and the
    HTML still showed the GO badge. Only sca-scan.sh's own rows count (`entry`
    absent or sca-scan.sh, mode scan or all-modules): sca-watch.sh, gitleaks-scan.sh
    and semgrep-scan.sh append to the same log, and the watch row FOLLOWS its
    scan's lock-busy row with no `reason`. Unreadable lines are skipped, each on
    its own: the log is decoded line by line, so one byte that is not UTF-8 in
    another writer's line never hides a lock-busy row (closing review F1: decoded
    whole, that one byte returned None and the badge said GO).
    """
    try:
        raw = (rd / "audit-log.jsonl").read_bytes()
    except OSError:
        return None
    for line in reversed(raw.splitlines()):
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            continue
        if (isinstance(rec, dict) and rec.get("entry", "sca-scan.sh") == "sca-scan.sh"
                and rec.get("mode") in _SCAN_MODES
                and (mode is None or rec.get("mode") == mode)
                and (module is None or rec.get("module") == module)):
            return rec
    return None


def _counters(obj):
    """The `counters` dict of a summary row or a pivot; {} when absent or malformed."""
    c = obj.get("counters") if isinstance(obj, dict) else None
    return c if isinstance(c, dict) else {}


# ---- /audit -global passes (T-01M51GN76VNBC3S4VBBRCHD6S4) -----------------------
LOT_BUDGET = 358_400  # bytes per lot (350 KB); a larger file is a lot of its own
# files per lot: an ESTIMATE under gemini's max_turns 100 (one turn per Read, margin for
# the `wc -c`); the turns of a real gemini pass are unmeasured.
LOT_MAX_FILES = 80
_STOPPED = ("complete", "budget")
_GAPS_SHOWN = 20  # missing pass numbers named; the rest is counted, never listed
# TOKEN_BUDGETS.md row of security-code-review-global: 12k per pass, +1k per 3.5 KB read
_PASS_TOKENS_K, _BYTES_PER_K = 12, 3584
_PASS_NAME = re.compile(r"code-review\.pass-([1-9][0-9]*)\.json")


def _norm(path, root):
    """`path` relative to `root` (an already realpath'd directory), or None.

    A relative path, or an absolute one UNDER root, comes back relative and
    resolved (`./x` == `x`, a symlink to its target). Only a path that LEAVES root
    (`..`, an absolute path elsewhere, a symlink that escapes), the root itself, an
    empty or non-string value -> None: census_rejected, never sized, counted unread.
    """
    if not isinstance(path, str) or not path:
        return None
    try:
        rp = os.path.realpath(os.path.join(root, path))
        if os.path.commonpath([rp, root]) != root:
            return None
        rel = os.path.relpath(rp, root)
    except (ValueError, OSError):  # embedded NUL; another drive (Windows)
        return None
    return None if rel == os.curdir else rel


def _census_ok(census):
    """A census is {unit: [path, ...]}: a dict of lists of strings, nothing else."""
    return isinstance(census, dict) and all(
        isinstance(v, list) and all(isinstance(x, str) for x in v) for v in census.values())


def _stat(obj, key):
    """`stats[key]` of a pass, or None. The contract of the -global defs (lot A,
    security-code-review-global § Output): `census` and `findings` at the top
    level, every other key under `stats` — pass 1 modules_total, files_candidate,
    units_untriaged, stopped; pass k files_read_paths, stopped, findings_dropped.
    A key elsewhere is absent: the pass is judged malformed, never guessed."""
    st = obj.get("stats")
    return st.get(key) if isinstance(st, dict) else None


def lots(census, root):
    """Next-fit the census into lots of at most LOT_BUDGET bytes AND at most
    LOT_MAX_FILES files, in census order (unit by unit, each unit's paths in its
    severity x exposure order — the priority holds inside a unit, never across units).

    Each path once; a file larger than LOT_BUDGET is a lot of its own. A path that
    leaves root -> census_rejected (never sized); absent, or not a regular file ->
    census_missing. Both stay in the census, so the merge counts them unread."""
    out, cur, size, seen = [], [], 0, set()
    missing, rejected = [], []
    for paths in census.values():
        for raw in paths:
            rel = _norm(raw, root)
            if rel is None:
                if raw not in rejected:
                    rejected.append(raw)
                continue
            if rel in seen:
                continue
            seen.add(rel)
            try:
                st = os.stat(os.path.join(root, rel))
            except (OSError, ValueError):
                missing.append(rel)
                continue
            if not stat.S_ISREG(st.st_mode):
                missing.append(rel)
                continue
            if st.st_size > LOT_BUDGET:
                if cur:
                    out.append(cur)
                    cur, size = [], 0
                out.append([rel])
                continue
            if size + st.st_size > LOT_BUDGET or len(cur) >= LOT_MAX_FILES:
                out.append(cur)
                cur, size = [], 0
            cur.append(rel)
            size += st.st_size
    if cur:
        out.append(cur)
    return {"lots": out, "census_missing": missing, "census_rejected": rejected}


def _pass_files(rd):
    """({k: path} of code-review.pass-<k>.json, [names of pass files whose k is not
    a plain positive integer — pass-01, pass-0, pass-x: never merged, never ignored])."""
    found, bad = {}, []
    for f in sorted(Path(rd).glob("code-review.pass-*.json")):
        m = _PASS_NAME.fullmatch(f.name)
        if m:
            found[int(m.group(1))] = f
        else:
            bad.append(f.name)
    return found, bad


def _lot_list(rd):
    """The `lots` of code-review.lots.json — a list of lists of strings — or None."""
    lj = load(Path(rd) / "code-review.lots.json")
    lst = lj.get("lots") if isinstance(lj, dict) else None
    if isinstance(lst, list) and all(
            isinstance(lot, list) and all(isinstance(x, str) for x in lot) for lot in lst):
        return lst
    return None


def _missing(files, top):
    """(the first _GAPS_SHOWN pass numbers in 1..top absent from `files`, how many are
    absent in all). At most _GAPS_SHOWN + len(files) steps, whatever `top`."""
    n = top - sum(1 for k in files if k <= top)
    first, k = [], 1
    while len(first) < min(_GAPS_SHOWN, n):
        if k not in files:
            first.append(k)
        k += 1
    return first, n


def _merge_passes(rd, root=None):
    """The -global passes merged into one code_review dict, or None when there is none.

    Pure: it writes nothing and returns only the code-review section — the SCA's
    `summary` (global_verdict, no_verdict, the pivot check) is never in its reach,
    so an INCOMPLETE review leaves the badge to the SCA. Census and modules_total
    come from pass 1 alone, never summed; the files_read_paths of pass k count only
    inside ITS lot (lots.json[k-2]), then the union is cut to the census. A unit is
    covered when every one of its paths was read and it is not untriaged.
    INCOMPLETE: a missing k, fewer lot passes than lots (or no lots.json), pass 1
    without a census, stopped short, with units untriaged or a files_candidate
    other than the paths its census lists, units short of modules_total, R < C,
    ANY lot pass that stopped on `budget` (a local gap, never a stop of the audit)
    or dropped findings (findings_dropped > 0). Any unexpected shape, and a pass
    numbered beyond the lots of lots.json -> invalid-pass, INCOMPLETE, never an
    exception. A pass beyond the lots gives no read and no finding (judged first,
    whatever its shape); a malformed pass gives no read, yet its findings are KEPT —
    a malformed count never hides a finding, CRITICAL included. The missing pass
    numbers are sought only up to len(lots) + 1 and only the first _GAPS_SHOWN are
    named, so a pass-5000000 costs no loop over five million numbers.
    BOUND: census and reads are what the agent DECLARES; R/C rates their
    consistency, not the repository's coverage. Without a readable lots.json no
    pass reads anything, yet their findings are still rendered (the reason says
    why the rate is void).
    """
    root = root or os.path.realpath(os.getcwd())
    files, bad = _pass_files(rd)
    if not files and not bad:
        return None
    invalid = [f"unexpected pass file name(s) {', '.join(bad)}"] if bad else []
    reasons, budget_hit = [], False
    K = max(files) if files else 0
    lot_list = _lot_list(rd)
    top = K if lot_list is None else min(K, len(lot_list) + 1)  # passes beyond: invalid-pass
    first, n_gaps = _missing(files, top)
    if n_gaps:
        reasons.append(f"missing pass(es) {', '.join(map(str, first))}"
                       + (f" (+{n_gaps - len(first)} more)" if n_gaps > len(first) else ""))
    passes = {}
    for k in sorted(files):
        obj = load(files[k])
        if isinstance(obj, dict):
            passes[k] = obj
        else:
            invalid.append(f"pass {k} unreadable or not a JSON object")

    census, mt, untri = None, None, []
    p1 = passes.get(1)
    if p1 is not None:
        raw_census, raw_mt = p1.get("census"), _stat(p1, "modules_total")
        raw_untri, stopped1 = _stat(p1, "units_untriaged"), _stat(p1, "stopped")
        raw_fc = _stat(p1, "files_candidate")
        if raw_census is None:
            reasons.append("pass 1 without census")
        elif not _census_ok(raw_census):
            invalid.append("pass 1 census is not {unit: [paths]}")
        elif not isinstance(raw_mt, int) or isinstance(raw_mt, bool) or raw_mt < 0:
            invalid.append("pass 1 modules_total absent or not an integer")
        elif not isinstance(raw_untri, list):
            invalid.append("pass 1 units_untriaged absent or not a list")
        elif stopped1 not in _STOPPED:
            invalid.append(f"pass 1 stopped {stopped1!r} not complete|budget")
        elif not isinstance(raw_fc, int) or isinstance(raw_fc, bool) or raw_fc < 0:
            invalid.append("pass 1 files_candidate absent or not an integer")
        else:
            census, mt, untri = raw_census, raw_mt, [str(u) for u in raw_untri]
            if stopped1 != "complete":
                budget_hit = True
                reasons.append("census stopped on budget")
            if untri:
                reasons.append(f"units untriaged: {', '.join(untri)}")
            listed = sum(len(ps) for ps in census.values())  # "paths listed in total"
            if raw_fc != listed:
                reasons.append(f"files_candidate {raw_fc} ≠ {listed} census paths")

    if lot_list is None:
        reasons.append("code-review.lots.json absent or malformed")
    elif top - 1 < len(lot_list):
        reasons.append(f"{len(lot_list) - max(top - 1, 0)} lot(s) not run")

    unit_paths = {u: [_norm(x, root) or ("rejected", x) for x in ps]
                  for u, ps in (census or {}).items()}
    cset = {q for ps in unit_paths.values() for q in ps}
    read, findings, last = set(), [], None
    for k in sorted(passes):
        obj = passes[k]
        if k == 1:
            last = _stat(obj, "stopped")
            continue
        if lot_list is not None and k - 2 >= len(lot_list):  # judged before its shape
            invalid.append(f"pass {k} beyond the {len(lot_list)} lot(s) of code-review.lots.json")
            last = None
            continue
        frp, stopped, fs = _stat(obj, "files_read_paths"), _stat(obj, "stopped"), obj.get("findings", [])
        dropped = _stat(obj, "findings_dropped")
        if (not isinstance(frp, list) or stopped not in _STOPPED or not isinstance(fs, list)
                or not isinstance(dropped, int) or isinstance(dropped, bool) or dropped < 0):
            kept = [f for f in fs if isinstance(f, dict)] if isinstance(fs, list) else []
            findings.extend(kept)  # a malformed count never hides a finding: 0 read, findings kept
            invalid.append(f"pass {k}: files_read_paths, stopped, findings or "
                           f"findings_dropped malformed"
                           + (f", {len(kept)} finding(s) kept" if kept else ""))
            last = None
            continue
        lot ={_norm(x, root) for x in lot_list[k - 2]} if lot_list is not None else set()
        read |= {n for n in (_norm(x, root) for x in frp) if n in lot and n in cset}
        findings.extend(f for f in fs if isinstance(f, dict))
        last = stopped
        if stopped == "budget":
            budget_hit = True
            reasons.append(f"pass {k} stopped on budget")
        if dropped:  # the ~60 findings cap of a pass: a truncation, never silent
            budget_hit = True
            reasons.append(f"pass {k} dropped {dropped} findings")
    if K not in passes:
        last = None

    coverage = {"K": K, "stopped": last if last in _STOPPED else "unknown",
                "reasons": reasons, "invalid": invalid, "measured": census is not None}
    stats = {}
    if census is not None:
        covered = [u for u, ps in unit_paths.items() if str(u) not in untri and set(ps) <= read]
        unread = sorted(set(untri) | {str(u) for u in unit_paths if u not in covered})
        R, C = len(read), len(cset)
        if len(covered) + len(unread) < mt:
            reasons.append(f"units {len(covered) + len(unread)} of modules_total {mt}")
        if R < C:
            reasons.append(f"{C - R} file(s) unread")
        coverage.update(R=R, C=C)
        stats = {"files_flagged": C, "files_read": R, "caps_hit": budget_hit,
                 "modules_total": mt, "modules_covered": len(covered), "modules_unread": unread}
    return {"stats": stats, "findings": findings, "coverage": coverage}


def coverage_lines(cv):
    """(coverage line, INCOMPLETE banner or None) of a merged review's `coverage`.
    The coverage line never carries `modules: ` (audit_report.test.sh pins its
    absence on the single-shot fallback)."""
    if cv.get("measured"):
        pct = f"{100 * cv['R'] // cv['C']} %" if cv["C"] else "n/a"
        rate = f"{cv['R']}/{cv['C']} files ({pct})"
    else:
        rate = "unmeasured (no valid census)"
    line = (f"coverage: {rate} — déclarés par l'agent · passes: {cv['K']} · "
            f"stopped: {cv['stopped']}")
    why = [f"invalid-pass ({x})" for x in cv["invalid"]] + list(cv["reasons"])
    return line, (f"INCOMPLETE — {'; '.join(why)}" if why else None)


def _code_review(rd, global_):
    """The code-review section: the merged passes under --global, else the
    single-shot code-review.json; --global with neither -> {"absent": True}."""
    if global_:
        merged = _merge_passes(rd)
        if merged is not None:
            return merged
        single = load(rd / "code-review.json")
        return single if single is not None else {"absent": True}
    return load(rd / "code-review.json")


def gather(reports_dir, waivers_path, global_=False):
    rd = Path(reports_dir)
    summary = load(rd / "modules" / "summary.json")
    if summary is None:
        v = load(rd / "effective-verdict.json")
        if v is None:
            return None
        counters = v.get("counters", {})
        mono_verdict = "NO-GO" if counters.get("active_at_gate", 0) else "GO"
        summary = {"generated": v.get("generated", ""), "root": "",
                   "gate_level": v.get("gate_level", "high"),
                   "modules": [{"slug": "root", "path": ".", "submodules": 0,
                                "verdict": mono_verdict,
                                "exit_code": 1 if mono_verdict == "NO-GO" else 0,
                                "reports_dir": str(rd), "counters": counters}],
                   "global_verdict": mono_verdict, "counters_total": counters}
        verdicts = {"root": v}
    else:
        verdicts = {m["slug"]: load(_verdict_path(rd, m)) or {}
                    for m in summary.get("modules", [])}
    # A no-verdict row decides from two places (security advisory S-01M51TQ06A):
    # the LAST sca-scan.sh row of EITHER mode — read in the rendered mode only, a
    # mono lock-busy after an --all-modules GO (or the reverse) left that GO
    # standing — and the last row of the RENDERED mode — read alone, a later mono
    # GO would clear an --all-modules lock-busy while the summary.json rendered
    # dates from before it (no mono run removes summary.json).
    latest = _last_row(rd)
    rendered = (_last_row(rd, "all-modules") if (rd / "modules" / "summary.json").is_file()
                else _last_row(rd, "scan", "root"))
    last, who = None, "latest run"
    if latest and latest.get("reason") in _NO_VERDICT:
        last = latest
    elif rendered and rendered.get("reason") in _NO_VERDICT:
        last, who = rendered, f"latest {rendered.get('mode')} run"
    if last:
        summary = dict(summary, global_verdict="NO-GO",
                       no_verdict=f"{who} obtained NO verdict ({last['reason']}, {last.get('ts')}); "
                                  f"rows below date from {summary.get('generated')}")
    elif summary.get("global_verdict") != "NO-GO":
        # A run killed by KILL or INT (Ctrl-C) writes no audit row and no summary
        # (closing review F2); TERM and HUP now write `aborted`, read above (F2b,
        # T-01M51YJ5GXM101STF0NM586RXN). The counters of a summary
        # row are COPIED from its pivot (sca-scan.sh), so a pivot whose counters
        # differ is a LATER run's. Not `generated`: it is the run's START, so the
        # same run's pivots are newer. The mono fallback is built from its pivot:
        # inert there. BOUND: a run cut short before any pivot changed, or whose
        # new pivot carries the same counters, is not seen; the earlier GO stands.
        stale = sorted(str(m.get("slug", "?")) for m in summary.get("modules", [])
                       if isinstance(m, dict)
                       and _counters(m) != _counters(verdicts.get(m.get("slug"))))
        if stale:
            summary = dict(summary, global_verdict="NO-GO", no_verdict=(
                f"module pivot(s) {', '.join(stale)} changed after the summary (a run "
                f"cut short, or a later one): the module rows below date from "
                f"{summary.get('generated')}, the findings from the newer pivot"))
    register = (load(waivers_path) or {}).get("waivers", [])
    # Read AFTER the SCA checks above and never handed `summary` (plan r4 step 6).
    return {"summary": summary, "verdicts": verdicts,
            "code_review": _code_review(rd, global_),
            "qualifiers": load(rd / "audit-qualifiers.json") or {},
            "register": [w for w in register if isinstance(w, dict)]}


def sev_chip(sev):
    s = str(sev or "low").lower()
    return (f'<span class="chip" style="background:'
            f'{SEV_COLOR.get(s, "#52525b")}">{esc(s.upper())}</span>')


def render(model, project):
    s = model["summary"]
    gv = s.get("global_verdict", "GO")
    tot = s.get("counters_total", {})
    active, waived = [], []
    for m in s.get("modules", []):
        v = model["verdicts"].get(m["slug"], {})
        active.extend((m["slug"], f) for f in v.get("active", []))
        for key in ("waived_accepted", "waived_pending"):
            waived.extend((m["slug"], f) for f in v.get(key, []))
    active.sort(key=lambda t: SEV_RANK.get((t[1].get("severity") or "low").lower(), 9))
    sev_counts = {}
    for _, f in active:
        sv = (f.get("severity") or "low").lower()
        sev_counts[sv] = sev_counts.get(sv, 0) + 1

    parts = [
        f"<header><h1>Security Audit — {esc(project)}</h1>"
        f"<span class='badge' style='background:{BADGE_COLOR.get(gv, '#52525b')}'>{esc(gv)}</span>"
        f"<p class='meta'>generated {esc(s.get('generated'))} · gate level: "
        f"{esc(s.get('gate_level'))} · root: {esc(s.get('root'))}</p></header>"
    ]
    if s.get("no_verdict"):
        parts.append(f"<p class='meta'><strong>{esc(s['no_verdict'])}</strong></p>")

    tiles = [("Modules scanned", len(s.get("modules", []))),
             ("Active findings", sum(sev_counts.values())),
             ("Critical / High", f"{sev_counts.get('critical', 0)} / {sev_counts.get('high', 0)}"),
             ("Waived (accepted)", tot.get("accepted", 0)),
             ("Waived (pending review)", tot.get("pending_review", 0)),
             ("Overdue reviews", tot.get("overdue_review", 0))]
    parts.append("<section class='tiles'>" + "".join(
        f"<div class='tile'><div class='num'>{esc(v)}</div><div class='lbl'>{esc(k)}</div></div>"
        for k, v in tiles) + "</section>")

    rows = []
    for m in s.get("modules", []):
        c = m.get("counters", {})
        note = f" ({m['submodules']} sub-modules collapsed)" if m.get("submodules") else ""
        verdict_txt = str(m.get("verdict") or "") + (" (DEGRADED)" if m.get("degraded") else "")
        rows.append(f"<tr><td><code>{esc(m['slug'])}</code></td><td>{esc(m['path'])}{esc(note)}</td>"
                    f"<td>{esc(verdict_txt)}</td><td>{esc(c.get('active_at_gate', 0))}</td>"
                    f"<td>{esc(c.get('accepted', 0))} / {esc(c.get('pending_review', 0))}</td></tr>")
    parts.append("<section><h2>Modules</h2><table><tr><th>Module</th><th>Path</th>"
                 "<th>Verdict</th><th>Active at gate</th><th>Waived acc./pend.</th></tr>"
                 + "".join(rows) + "</table></section>")

    if active:
        rows = []
        for slug, f in active:
            rows.append(f"<tr><td>{sev_chip(f.get('severity'))}</td>"
                        f"<td><code>{esc(f.get('package'))}@{esc(f.get('version'))}</code></td>"
                        f"<td>{esc(f.get('ecosystem'))}</td><td><code>{esc(slug)}</code></td>"
                        f"<td>{esc(f.get('advisory'))}</td><td>{esc(f.get('class'))}</td>"
                        f"<td>{esc(f.get('fix_version') or '—')}</td></tr>")
        parts.append("<section><h2>Active findings</h2><table><tr><th>Severity</th><th>Package</th>"
                     "<th>Ecosystem</th><th>Module</th><th>Advisory</th><th>Class</th><th>Fix</th></tr>"
                     + "".join(rows) + "</table><p class='note'>Remediation runs through /kickoff "
                     "(class-2 auto-fix under policy, class-3 pilot decision) — never through /audit."
                     "</p></section>")
    else:
        parts.append("<section><h2>Active findings</h2>"
                     "<p>None at gate level after waiver filtering.</p></section>")

    if waived:
        reg = {(w.get("ecosystem"), w.get("package"), w.get("version")): w
               for w in model["register"]}
        rows = []
        for slug, f in waived:
            w = reg.get((f.get("ecosystem"), f.get("package"), f.get("version")), {})
            rows.append(f"<tr><td><code>{esc(f.get('package'))}@{esc(f.get('version'))}</code></td>"
                        f"<td><code>{esc(slug)}</code></td><td>{esc(f.get('waiver_status'))}</td>"
                        f"<td>{esc(w.get('reason', '—'))}</td><td>{esc(w.get('accepted_by', '—'))}</td>"
                        f"<td>{esc(w.get('date', '—'))}</td><td>{esc(w.get('review_by', '—'))}</td></tr>")
        parts.append("<section><h2>Applied waivers</h2><table><tr><th>Package</th><th>Module</th>"
                     "<th>Status</th><th>Reason</th><th>Accepted by</th><th>Date</th>"
                     "<th>Review by</th></tr>" + "".join(rows) + "</table></section>")

    cr = model.get("code_review")
    if isinstance(cr, dict) and cr.get("absent"):
        parts.append("<section><h2>Global code review (-global)</h2>"
                     "<p class='meta'><strong>global review: absent (run failed)</strong></p>"
                     "</section>")
        cr = None
    if cr:
        st = cr.get("stats", {})
        cov_meta = ""
        if isinstance(cr.get("coverage"), dict):
            line, banner = coverage_lines(cr["coverage"])
            cov_meta = f"<p class='meta'>{esc(line)}</p>" + (
                f"<p class='meta'><strong>{esc(banner)}</strong></p>" if banner else "")
        rows = []
        for f in sorted(cr.get("findings", []),
                        key=lambda x: SEV_RANK.get(str(x.get("severity") or "low").lower(), 9)):
            rows.append(f"<tr><td>{sev_chip(f.get('severity'))}</td>"
                        f"<td><code>{esc(f.get('file'))}:{esc(f.get('line'))}</code></td>"
                        f"<td><code>{esc(f.get('module'))}</code></td><td>{esc(f.get('category'))}</td>"
                        f"<td>{esc(f.get('summary'))}</td><td>{esc(f.get('fix_hint'))}</td></tr>")
        cov = ""
        if "modules_total" in st:
            cov = (f" · modules: {esc(st.get('modules_covered', '?'))}/"
                   f"{esc(st.get('modules_total', '?'))} covered")
            unread = st.get("modules_unread") or []
            if unread:
                cov += f" · unread: {esc(', '.join(str(m) for m in unread))}"
        parts.append("<section><h2>Global code review (-global)</h2>"
                     f"<p class='meta'>files flagged: {esc(st.get('files_flagged', '?'))} · "
                     f"files read: {esc(st.get('files_read', '?'))} · caps hit: "
                     f"{esc(st.get('caps_hit', False))}{cov}</p>" + cov_meta +
                     "<table><tr><th>Severity</th><th>Location</th><th>Module</th><th>Category</th>"
                     "<th>Finding</th><th>Suggested fix</th></tr>" + "".join(rows) + "</table>"
                     "<p class='note'>Audit code findings are informative (no gate); the mandatory "
                     "class-1 gate applies to produced diffs in the /kickoff pipeline.</p></section>")

    q = model.get("qualifiers", {})
    degraded_gaps = [f"{m['slug']}: {r}" for m in s.get("modules", [])
                     for r in (m.get("degraded_reasons") or [])]
    quals = "".join(f"<li>{esc(x)}</li>" for x in (q.get("qualifiers") or []))
    gaps = "".join(f"<li>{esc(x)}</li>" for x in ((q.get("gaps") or []) + degraded_gaps))
    parts.append("<section><h2>Methodology &amp; limits</h2>"
                 "<p>Per-ecosystem scanners (npm/pnpm audit, OWASP Dependency-Check, pip-audit "
                 "for Python, Socket when "
                 "installed) run per module; findings are normalized and filtered through the "
                 "committed waiver register (<code>.agents/security/sca-waivers.json</code>) by "
                 "<code>waiver_filter.py</code>; verdicts are the EFFECTIVE gate. Multi-module "
                 "builds are scanned once from their aggregator root.</p>"
                 + (f"<h3>Qualifiers</h3><ul>{quals}</ul>" if quals else "")
                 + (f"<h3>Gaps</h3><ul>{gaps}</ul>" if gaps else "")
                 + "<p class='note'>Generated by /audit (read-only). Remediation: /kickoff.</p>"
                 "</section>")

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Security Audit — {esc(project)}</title><style>{CSS}</style></head><body>"
            + "".join(parts) + "</body></html>")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--project", default="project")
    ap.add_argument("--waivers", default=".agents/security/sca-waivers.json")
    ap.add_argument("--global", dest="global_", action="store_true",
                    help="merge the code-review.pass-<k>.json files of /audit -global")
    ap.add_argument("--lots", action="store_true",
                    help="split pass 1's census into code-review.lots.json, print it, stop")
    ap.add_argument("--clear", action="store_true",
                    help="delete a previous run's review files (/audit step 3), then stop")
    args = ap.parse_args(argv)
    rd = Path(args.reports_dir)
    if args.clear:
        return clear_review(rd)
    if args.lots:  # before gather: the lots need no SCA artefact
        return write_lots(rd)
    model = gather(args.reports_dir, args.waivers, args.global_)
    if model is None:
        print("audit_report: no scan input (modules/summary.json or effective-verdict.json) "
              f"under {args.reports_dir} — run sca-scan.sh first.", file=sys.stderr)
        return 2
    doc = render(model, args.project)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else rd / f"audit-{stamp}.html"
    out.write_text(doc, encoding="utf-8")
    (rd / "audit-latest.html").write_text(doc, encoding="utf-8")
    print(f"audit report: {out}")
    cr = model.get("code_review")
    if not args.global_:
        files, bad = _pass_files(rd)
        if files or bad:
            print(f"{len(files) + len(bad)} pass files present, not merged (no --global)")
    elif isinstance(cr, dict) and cr.get("absent"):
        print("global review: absent (run failed)")
    elif isinstance(cr, dict) and isinstance(cr.get("coverage"), dict):
        for text in coverage_lines(cr["coverage"]):
            if text:
                print(text)
    return 0


_CLEARED = ("code-review.json", "code-review.lots.json", "audit-latest.html")


def clear_review(rd: "Path | str") -> int:
    """--clear, /audit step 3: delete a previous run's review files — by FIXED name
    under `rd` only (never a pattern taken from the caller, never recursive) — so no
    leftover is merged, or shown, as this run's. safe-bash refuses `rm` under
    sca-reports/, hence code. rc 0 cleared (or nothing to clear), 1 a file stayed."""
    rd = Path(rd)
    targets = [rd / n for n in _CLEARED] + sorted(rd.glob("code-review.pass-*.json"))
    gone, stuck = [], []
    for f in targets:
        try:
            f.unlink()  # a symlink loses its link, never its target; a directory refuses
            gone.append(f.name)
        except FileNotFoundError:
            pass
        except OSError as exc:
            stuck.append(f"{f.name} ({exc.__class__.__name__})")
    print(f"cleared: {', '.join(gone) or 'nothing'}")
    if stuck:
        print(f"audit_report --clear: NOT removed: {', '.join(stuck)} — a leftover would be "
              "merged as this run's", file=sys.stderr)
        return 1
    return 0


def _purge_stale_passes(rd, new_lots):
    """The lot passes (code-review.pass-*.json but pass 1) a NEW split makes stale, deleted.

    Stale = the lots change (they no longer match the passes' lot numbers), or the pass
    is OLDER than pass 1: a run writes pass 1, then --lots, then passes 2..K, so a lot
    pass older than pass 1 is an earlier run's — the case where /audit step 3 did not
    run. A second --lots of the same run on the same lots keeps passes 2..j already
    written. BOUND: mtimes; a clock set back between two runs is not seen."""
    try:
        t1 = (rd / "code-review.pass-1.json").stat().st_mtime_ns
    except OSError:
        t1 = None
    changed = _lot_list(rd) != new_lots  # read BEFORE the new lots.json is written
    gone = []
    for f in sorted(rd.glob("code-review.pass-*.json")):
        if f.name == "code-review.pass-1.json":
            continue
        try:
            if changed or (t1 is not None and f.stat().st_mtime_ns < t1):
                f.unlink()
                gone.append(f.name)
        except OSError:
            continue  # unreadable or locked: the merge still names it
    return gone


def write_lots(rd):
    """--lots: pass 1's census -> code-review.lots.json, printed; rc 2 without one.
    stdout carries the lots JSON alone; stderr the lot count, the token estimate (the
    TOKEN_BUDGETS.md row: an estimate, never a bound) and the stale passes purged."""
    p1 = load(rd / "code-review.pass-1.json")
    census = p1.get("census") if isinstance(p1, dict) else None
    if not _census_ok(census):
        print(f"audit_report --lots: {rd / 'code-review.pass-1.json'} has no readable census "
              "({unit: [paths]}) — invalid-pass: stop the -global passes, INCOMPLETE.",
              file=sys.stderr)
        return 2
    root = os.path.realpath(os.getcwd())
    res = lots(census, root)
    text = json.dumps(res, indent=1)
    gone = _purge_stale_passes(rd, res["lots"])
    (rd / "code-review.lots.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    n, size = len(res["lots"]), 0
    for lot in res["lots"]:
        for p in lot:
            try:
                size += os.stat(os.path.join(root, p)).st_size
            except OSError:
                pass
    est = (n + 1) * _PASS_TOKENS_K + size // _BYTES_PER_K
    print(f"lots: {n} · passes: {n + 1} (census included) · {size:,} bytes to read · "
          f"estimate ≈ {est:,}k tokens ({_PASS_TOKENS_K}k per pass + 1k per 3.5 KB read, "
          "TOKEN_BUDGETS.md: an estimate, never a bound)", file=sys.stderr)
    if gone:
        print(f"purged {len(gone)} stale pass file(s) of an earlier run: {', '.join(gone)}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
