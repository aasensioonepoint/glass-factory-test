#!/usr/bin/env python3
"""Tests for audit_report.py — run: cd .agents/security && python -m unittest test_audit_report -v"""
import contextlib
import html
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_report as ar

FINDING = {"ecosystem": "npm", "package": "lodash", "version": "4.17.20",
           "advisory": "CVE-2021-23337", "severity": "high", "class": "known_cve",
           "fix_version": ">=4.17.21", "direct": True}

EMPTY_COUNTERS = {"active_at_gate": 0, "accepted": 0, "pending_review": 0, "overdue_review": 0}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def verdict(active=(), accepted=(), pending=()):
    return {"gate_level": "high", "active": list(active),
            "waived_accepted": list(accepted), "waived_pending": list(pending),
            "counters": {"active_at_gate": len(active), "accepted": len(accepted),
                         "pending_review": len(pending), "overdue_review": 0},
            "notes": []}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rd = Path(self.tmp.name) / ".sca-reports"
        self.rd.mkdir()
        self.wfile = Path(self.tmp.name) / "sca-waivers.json"
        write(self.wfile, {"waivers": []})

    def tearDown(self):
        self.tmp.cleanup()

    def multi_module(self, fe_active=None):
        fe = [fe_active] if fe_active else [FINDING]
        write(self.rd / "modules" / "frontend" / "effective-verdict.json", verdict(active=fe))
        write(self.rd / "modules" / "backend" / "effective-verdict.json", verdict())
        write(self.rd / "modules" / "summary.json",
              {"generated": "2026-07-19T00:00:00Z", "root": "/repo", "gate_level": "high",
               "modules": [
                   {"slug": "frontend", "path": "frontend", "submodules": 0, "verdict": "NO-GO",
                    "exit_code": 1, "reports_dir": ".agents/state/local/sca-reports/modules/frontend",
                    "counters": dict(EMPTY_COUNTERS, active_at_gate=1)},
                   {"slug": "backend", "path": "backend", "submodules": 2, "verdict": "GO",
                    "exit_code": 0, "reports_dir": ".agents/state/local/sca-reports/modules/backend",
                    "counters": dict(EMPTY_COUNTERS)}],
               "global_verdict": "NO-GO",
               "counters_total": dict(EMPTY_COUNTERS, active_at_gate=1)})

    def run_report(self, *extra):
        code = ar.main(["--reports-dir", str(self.rd), "--project", "fixture",
                        "--waivers", str(self.wfile), *extra])
        latest = self.rd / "audit-latest.html"
        return code, (latest.read_text(encoding="utf-8") if latest.is_file() else "")


class TestRender(Base):
    def test_multi_module_report(self):
        self.multi_module()
        code, doc = self.run_report()
        self.assertEqual(code, 0)
        self.assertIn("NO-GO", doc)
        self.assertIn("frontend", doc)
        self.assertIn("backend", doc)
        self.assertIn("lodash", doc)
        self.assertIn("2 sub-modules collapsed", doc)

    def test_timestamped_and_latest_identical(self):
        self.multi_module()
        self.run_report()
        stamped = [p for p in self.rd.iterdir()
                   if p.name.startswith("audit-") and p.name != "audit-latest.html"]
        self.assertEqual(len(stamped), 1)
        self.assertEqual(stamped[0].read_text(encoding="utf-8"),
                         (self.rd / "audit-latest.html").read_text(encoding="utf-8"))

    def test_mono_module_fallback(self):
        write(self.rd / "effective-verdict.json", verdict(active=[FINDING]))
        code, doc = self.run_report()
        self.assertEqual(code, 0)
        self.assertIn("root", doc)
        self.assertIn("NO-GO", doc)

    def test_root_module_relocated_to_root(self):
        # Since T-00000291 the root module writes to the ROOT of sca-reports and
        # its summary entry's reports_dir points there. audit_report must resolve
        # the verdict from reports_dir, not from modules/root/ — otherwise the
        # HTML shows the root module with a blank verdict and zero findings.
        write(self.rd / "effective-verdict.json", verdict(active=[FINDING]))
        write(self.rd / "modules" / "frontend" / "effective-verdict.json", verdict())
        write(self.rd / "modules" / "summary.json",
              {"generated": "t", "root": "/repo", "gate_level": "high",
               "modules": [
                   {"slug": "root", "path": ".", "submodules": 0, "verdict": "NO-GO",
                    "exit_code": 1, "reports_dir": ".agents/state/local/sca-reports",
                    "counters": dict(EMPTY_COUNTERS, active_at_gate=1)},
                   {"slug": "frontend", "path": "frontend", "submodules": 0, "verdict": "GO",
                    "exit_code": 0,
                    "reports_dir": ".agents/state/local/sca-reports/modules/frontend",
                    "counters": dict(EMPTY_COUNTERS)}],
               "global_verdict": "NO-GO",
               "counters_total": dict(EMPTY_COUNTERS, active_at_gate=1)})
        code, doc = self.run_report()
        self.assertEqual(code, 0)
        # The finding lives in the ROOT module's verdict; its presence proves the
        # verdict was read from reports_dir (the root), not from modules/root/
        # (which does not exist here) — a slug-built path would render it blank.
        self.assertIn("lodash", doc)
        self.assertIn("CVE-2021-23337", doc)

    def test_no_input_exit_2(self):
        code, _ = self.run_report()
        self.assertEqual(code, 2)

    def test_html_escaping(self):
        evil = dict(FINDING, package="<script>alert(1)</script>")
        self.multi_module(fe_active=evil)
        _, doc = self.run_report()
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)

    def test_code_review_section_conditional(self):
        self.multi_module()
        _, doc = self.run_report()
        self.assertNotIn("Global code review", doc)
        write(self.rd / "code-review.json",
              {"stats": {"files_flagged": 4, "files_read": 4, "caps_hit": False},
               "findings": [{"file": "backend/src/Api.java", "line": 42, "severity": "high",
                             "category": "sql-injection", "summary": "string-built query",
                             "fix_hint": "use PreparedStatement", "module": "backend"}]})
        _, doc = self.run_report()
        self.assertIn("Global code review", doc)
        self.assertIn("Api.java", doc)

    def test_waiver_annex_joins_register(self):
        waived = dict(FINDING, waiver_status="accepted")
        write(self.rd / "modules" / "frontend" / "effective-verdict.json",
              verdict(accepted=[waived]))
        write(self.rd / "modules" / "summary.json",
              {"generated": "t", "root": "/repo", "gate_level": "high",
               "modules": [{"slug": "frontend", "path": "frontend", "submodules": 0,
                            "verdict": "GO", "exit_code": 0,
                            "reports_dir": ".agents/state/local/sca-reports/modules/frontend",
                            "counters": dict(EMPTY_COUNTERS, accepted=1)}],
               "global_verdict": "GO", "counters_total": dict(EMPTY_COUNTERS, accepted=1)})
        write(self.wfile, {"waivers": [
            {"package": "lodash", "version": "4.17.20", "ecosystem": "npm",
             "advisories": "*", "class": "known_cve", "status": "accepted",
             "accepted_by": "your-user", "date": "2026-07-19",
             "reason": "risk accepted for pilot", "review_by": "2026-10-01"}]})
        code, doc = self.run_report()
        self.assertEqual(code, 0)
        self.assertIn("Applied waivers", doc)
        self.assertIn("risk accepted for pilot", doc)

    def test_degraded_module_rendered(self):
        self.multi_module()
        s = json.loads((self.rd / "modules" / "summary.json").read_text(encoding="utf-8"))
        s["modules"][1]["degraded"] = True
        s["modules"][1]["degraded_reasons"] = ["gradle: no ./gradlew wrapper and no gradle on PATH"]
        write(self.rd / "modules" / "summary.json", s)
        _, doc = self.run_report()
        self.assertIn("(DEGRADED)", doc)
        self.assertIn("no ./gradlew wrapper", doc)

    # ---- a run that obtained NO verdict (closing review T1, scenario E3) -------
    # lock_busy and run_aborted write nothing in the reports directory but ONE
    # audit row: the summary and the pivots on disk are an EARLIER run's.
    def go_summary_2000(self):
        write(self.rd / "modules" / "sub" / "effective-verdict.json", verdict())
        write(self.rd / "modules" / "summary.json",
              {"generated": "2000-01-01T00:00:00Z", "root": "", "gate_level": "high",
               "modules": [{"slug": "sub", "path": "sub", "submodules": 0, "verdict": "GO",
                            "exit_code": 0, "gating": True,
                            "reports_dir": ".agents/state/local/sca-reports/modules/sub",
                            "counters": dict(EMPTY_COUNTERS)}],
               "global_verdict": "GO", "counters_total": dict(EMPTY_COUNTERS)})

    def audit_rows(self, *rows):
        (self.rd / "audit-log.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    @staticmethod
    def badge(doc):
        m = re.search(r"<span class='badge' style='background:[^']*'>([^<]*)</span>", doc)
        return m.group(1) if m else None

    def test_lock_busy_after_a_go_summary_is_no_go(self):
        """E3: a GO summary dated 2000, then `--all-modules` rc 1 lock-busy -> NO-GO."""
        self.go_summary_2000()
        self.audit_rows({"ts": "2026-10-16T04:06:02Z", "mode": "all-modules",
                         "entry": "sca-scan.sh", "verdict": "NO-GO", "reason": "lock-busy",
                         "gate_level": "high"})
        code, doc = self.run_report()
        self.assertEqual(code, 0)
        self.assertEqual(self.badge(doc), "NO-GO")
        self.assertIn("latest run obtained NO verdict (lock-busy, 2026-10-16T04:06:02Z); "
                      "rows below date from 2000-01-01T00:00:00Z", doc)

    def test_aborted_mono_module_run_is_no_go(self):
        write(self.rd / "effective-verdict.json", verdict())
        self.audit_rows({"ts": "2026-10-16T05:00:00Z", "mode": "scan", "entry": "sca-scan.sh",
                         "module": "root", "verdict": "NO-GO", "reason": "aborted",
                         "gate_level": "high"})
        _, doc = self.run_report()
        self.assertEqual(self.badge(doc), "NO-GO")
        self.assertIn("latest run obtained NO verdict (aborted", doc)

    # Rows of the OTHER writers of the same log: never a sca-scan.sh run.
    WATCH_ROW = {"ts": "2026-10-16T07:00:00Z", "mode": "watch", "entry": "sca-watch.sh",
                 "verdict": "NO-GO", "watch_mode": "scan-only"}
    LEAKS_ROW = {"ts": "2026-10-16T07:01:00Z", "mode": "diff", "entry": "gitleaks-scan.sh",
                 "class": 0, "verdict": "clean", "findings": 0}
    SEMGREP_ROW = {"ts": "2026-10-16T07:02:00Z", "mode": "gate", "entry": "semgrep-scan.sh",
                   "class": 1, "verdict": "clean", "findings": 0}

    def test_a_later_verdict_keeps_the_go_the_pair(self):
        """The pair: a LATER sca-scan.sh verdict outranks an earlier no-verdict row;
        the rows of sca-watch.sh, gitleaks-scan.sh and semgrep-scan.sh never count.
        (Until S-01M51TQ06A, a scan/sub lock-busy after an --all-modules GO kept the
        GO here too: it is NO-GO now, test_a_no_verdict_row_of_either_mode_is_no_go.)"""
        self.go_summary_2000()
        busy = {"ts": "2026-10-16T04:00:00Z", "mode": "all-modules", "verdict": "NO-GO",
                "reason": "lock-busy"}
        later_go = {"ts": "2026-10-16T05:00:00Z", "mode": "all-modules", "verdict": "GO",
                    "modules": 1}
        for rows in ((busy, later_go), (later_go, "{not json"),
                     (later_go, self.WATCH_ROW, self.LEAKS_ROW, self.SEMGREP_ROW)):
            with self.subTest(rows=rows):
                (self.rd / "audit-log.jsonl").write_text(
                    "".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows),
                    encoding="utf-8")
                _, doc = self.run_report()
                self.assertEqual(self.badge(doc), "GO")
                self.assertNotIn("obtained NO verdict", doc)

    def test_a_no_verdict_row_of_either_mode_is_no_go(self):
        """Security advisory S-01M51TQ06A: the LAST sca-scan.sh row of EITHER mode.
        Measured before: A, A2 and B rendered the GO badge (the rendered mode only)."""
        busy = {"mode": "scan", "entry": "sca-scan.sh", "module": "root", "verdict": "NO-GO",
                "reason": "lock-busy", "ts": "2026-10-16T06:00:00Z"}
        am_go = {"ts": "2026-10-16T05:00:00Z", "mode": "all-modules", "entry": "sca-scan.sh",
                 "verdict": "GO", "modules": 1}
        am_busy = dict(am_go, verdict="NO-GO", reason="lock-busy", ts="2026-10-16T06:00:00Z")
        root_go = {"ts": "2026-10-16T07:00:00Z", "mode": "scan", "entry": "sca-scan.sh",
                   "module": "root", "verdict": "GO", "gate_level": "high"}
        cases = (  # name, summary on disk, rows, the exact no-verdict line
            ("A mono lock-busy after an --all-modules GO", True, (am_go, busy), "latest run"),
            ("A2 a module's lock-busy after an --all-modules GO", True,
             (am_go, dict(busy, module="sub")), "latest run"),
            ("B --all-modules lock-busy after a mono GO", False,
             (dict(root_go, ts="2026-10-16T05:00:00Z"), am_busy), "latest run"),
            # Green before the fix too: they kill a bare "last row, any writer" reading.
            ("guard: the other writers' rows after the lock-busy", True,
             (am_busy, self.WATCH_ROW, self.LEAKS_ROW, self.SEMGREP_ROW), "latest run"),
            ("C a later mono GO does not clear the rendered mode's lock-busy", True,
             (am_busy, root_go), "latest all-modules run"))
        for name, with_summary, rows, who in cases:
            with self.subTest(name):
                for p in (self.rd / "modules" / "summary.json", self.rd / "effective-verdict.json"):
                    p.unlink(missing_ok=True)
                if with_summary:
                    self.go_summary_2000()
                else:
                    write(self.rd / "effective-verdict.json", verdict())
                self.audit_rows(*rows)
                _, doc = self.run_report()
                self.assertEqual(self.badge(doc), "NO-GO")
                self.assertIn(f"{who} obtained NO verdict (lock-busy, 2026-10-16T06:00:00Z); ", doc)

    def test_mono_module_later_go_row_keeps_the_go_the_pair(self):
        """The mono pair: sca-scan.sh's nominal row carries `module` too (root here),
        so a later GO of the bare form outranks an earlier lock-busy one."""
        write(self.rd / "effective-verdict.json", verdict())
        self.audit_rows({"ts": "2026-10-16T04:00:00Z", "mode": "scan", "module": "root",
                         "verdict": "NO-GO", "reason": "lock-busy"},
                        {"ts": "2026-10-16T05:00:00Z", "mode": "scan", "module": "root",
                         "verdict": "GO", "gate_level": "high"})
        _, doc = self.run_report()
        self.assertEqual(self.badge(doc), "GO")
        self.assertNotIn("obtained NO verdict", doc)

    def test_a_non_utf8_line_never_hides_a_lock_busy(self):
        """Closing review F1: one byte not UTF-8 in ANOTHER writer's line made the
        whole log unreadable, so the lock-busy row vanished and the badge said GO.
        Measured before: GO, 0 no-verdict line. The bad line skipped, either side."""
        self.go_summary_2000()
        busy = json.dumps({"ts": "2026-10-16T04:06:02Z", "mode": "all-modules",
                           "entry": "sca-scan.sh", "verdict": "NO-GO", "reason": "lock-busy",
                           "gate_level": "high"}).encode("utf-8")
        latin1 = json.dumps(dict(self.SEMGREP_ROW, config="CFG")).encode("utf-8").replace(
            b"CFG", b"/r\xe9gles")
        for name, rows in (("bad line before", (latin1, busy)), ("bad line after", (busy, latin1))):
            with self.subTest(name):
                (self.rd / "audit-log.jsonl").write_bytes(b"".join(r + b"\n" for r in rows))
                _, doc = self.run_report()
                self.assertEqual(self.badge(doc), "NO-GO")
                self.assertIn("latest run obtained NO verdict (lock-busy, 2026-10-16T04:06:02Z)", doc)

    def test_a_pivot_changed_after_a_go_summary_is_no_go(self):
        """Closing review F2: an --all-modules run killed by KILL or INT (TERM and HUP
        now write `aborted`, F2b) after its module rewrote the root pivot writes no
        audit row and no summary. Measured
        before: the earlier GO summary, a root pivot at active_at_gate 1, badge GO,
        one HIGH listed. The counters of a summary row are copied from its pivot
        (sca-scan.sh), so a mismatch says the pivot is a LATER run's."""
        rows = ({"ts": "2026-10-16T08:00:05Z", "mode": "all-modules", "entry": "sca-scan.sh",
                 "verdict": "GO", "modules": 1},
                # run 2's own module row (no reason): it must not read as no-verdict
                {"ts": "2026-10-16T09:00:00Z", "mode": "scan", "entry": "sca-scan.sh",
                 "module": "root", "verdict": "NO-GO", "gate_level": "high"})
        write(self.rd / "modules" / "summary.json",
              {"generated": "2026-10-16T08:00:00Z", "root": "/repo", "gate_level": "high",
               "modules": [{"slug": "root", "path": ".", "submodules": 0, "verdict": "GO",
                            "exit_code": 0, "gating": True,
                            "reports_dir": ".agents/state/local/sca-reports",
                            "counters": dict(EMPTY_COUNTERS)}],
               "global_verdict": "GO", "counters_total": dict(EMPTY_COUNTERS)})
        self.audit_rows(*rows)
        cases = (("killed by KILL or INT (TERM and HUP now write `aborted`, F2b) after the root pivot "
                  "was rewritten", [FINDING], "NO-GO"),
                 # BOUND, said: a rewritten pivot with the SAME counters is not seen
                 ("same counters", [], "GO"))
        for name, active, expected in cases:
            with self.subTest(name):
                write(self.rd / "effective-verdict.json", verdict(active=active))
                _, doc = self.run_report()
                self.assertEqual(self.badge(doc), expected)
                if expected == "NO-GO":
                    self.assertIn("module pivot(s) root changed after the summary", doc)
                else:
                    self.assertNotIn("changed after the summary", doc)

    def test_qualifiers_rendered(self):
        self.multi_module()
        write(self.rd / "audit-qualifiers.json",
              {"qualifiers": ["NVD data 12 days old — maven verdict DEGRADED"],
               "gaps": ["socket CLI not installed"]})
        _, doc = self.run_report()
        self.assertIn("NVD data 12 days old", doc)
        self.assertIn("socket CLI not installed", doc)


class TestGlobalPasses(Base):
    """/audit -global passes: --lots, then the merge under --global (plan r4 step 6,
    T-01M51GN76VNBC3S4VBBRCHD6S4). The SCA benches above — SYM-03821 and
    SYM-20370..20374, SYM-20376, SYM-20377 — run WITHOUT --global, unchanged.
    Paths are judged against the realpath'd cwd, so every test runs from `root`."""

    def setUp(self):
        super().setUp()
        self.root = Path(os.path.realpath(self.tmp.name))
        self.old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.old_cwd)
        super().tearDown()

    def mk(self, rel, size=1):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as fh:
            fh.truncate(size)  # sized without writing: os.stat is all lots() reads
        return rel

    def sca_go(self):
        write(self.rd / "effective-verdict.json", verdict())

    def census_pass(self, census, modules_total=None, stopped="complete", untriaged=(),
                    files_candidate=None):
        listed = sum(len(v) for v in census.values())
        write(self.rd / "code-review.pass-1.json",
              {"census": census, "findings": [],
               "stats": {"files_candidate": listed if files_candidate is None else files_candidate,
                         "modules_total": len(census) if modules_total is None else modules_total,
                         "stopped": stopped, "units_untriaged": list(untriaged)}})

    def lot_pass(self, k, paths, stopped="complete", findings=(), dropped=0):
        write(self.rd / f"code-review.pass-{k}.json",
              {"stats": {"files_read_paths": list(paths), "stopped": stopped,
                         "findings_dropped": dropped},
               "findings": list(findings)})

    def split(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ar.main(["--reports-dir", str(self.rd), "--lots"])
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())["lots"]

    def report(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code, doc = self.run_report(*extra)
        return code, doc, out.getvalue()

    def clear_review_files(self):
        for p in self.rd.glob("code-review*.json"):
            p.unlink()

    def ten_files(self):
        """10 files of 80 000 o in 3 units -> lots of 4, 4 and 2 (5 x 80 000 > 358 400)."""
        census = {"api": [self.mk(f"src/api/f{i}.py", 80_000) for i in range(4)],
                  "db": [self.mk(f"src/db/f{i}.py", 80_000) for i in range(4)],
                  "ui": [self.mk(f"src/ui/f{i}.py", 80_000) for i in range(2)]}
        self.census_pass(census)
        lots = self.split()
        self.assertEqual([len(lot) for lot in lots], [4, 4, 2])
        return census, lots

    # ---- --lots --------------------------------------------------------------
    def test_lots_next_fit_in_census_order(self):
        """70 x 45 000 o then one 400 000 o LAST -> exactly 11 lots (10 x 7 + 1).
        Budget / 10 makes every file a lot of its own: 71 lots, red."""
        paths = [self.mk(f"src/f{i:02}.py", 45_000) for i in range(70)]
        big = self.mk("assets/big.bin", 400_000)
        census = {"core": paths[:40], "edge": paths[40:] + ["./src/f00.py", big]}
        lots = ar.lots(census, str(self.root))["lots"]
        self.assertEqual([len(lot) for lot in lots], [7] * 10 + [1])
        self.assertEqual(lots[-1], [big])
        self.assertEqual([p for lot in lots for p in lot], paths + [big])  # once, in order
        size = {p: (self.root / p).stat().st_size for lot in lots for p in lot}
        for lot, nxt in zip(lots, lots[1:]):  # next-fit: the next file did not fit
            self.assertLessEqual(sum(size[p] for p in lot), ar.LOT_BUDGET)
            self.assertGreater(sum(size[p] for p in lot) + size[nxt[0]], ar.LOT_BUDGET)

    def test_lots_need_no_sca_artefact(self):
        self.census_pass({"api": [self.mk("a.py", 10)]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ar.main(["--reports-dir", str(self.rd), "--lots"])
        self.assertEqual(code, 0)
        written = json.loads((self.rd / "code-review.lots.json").read_text(encoding="utf-8"))
        self.assertEqual(written, json.loads(out.getvalue()))
        self.assertEqual(written["lots"], [["a.py"]])
        self.assertFalse((self.rd / "audit-latest.html").exists())
        (self.rd / "code-review.lots.json").unlink()
        write(self.rd / "code-review.pass-1.json", {"stats": {"stopped": "complete"}})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = ar.main(["--reports-dir", str(self.rd), "--lots"])
        self.assertEqual(code, 2)
        self.assertFalse((self.rd / "code-review.lots.json").exists())

    def test_census_paths_normalised(self):
        """`./x` == `x`; `../y`, `/etc/passwd` -> census_rejected (never sized);
        an absolute path under the root -> relative; absent -> census_missing."""
        self.mk("x.py")
        self.mk("z.py")
        census = {"a": ["./x.py", "x.py", "../y.py", "/etc/passwd", "gone.py",
                        str(Path(self.tmp.name) / "z.py")]}  # unresolved: /var vs /private/var
        res = ar.lots(census, str(self.root))
        self.assertEqual(res["lots"], [["x.py", "z.py"]])
        self.assertEqual(res["census_rejected"], ["../y.py", "/etc/passwd"])
        self.assertEqual(res["census_missing"], ["gone.py"])

    def test_symlink_leaving_the_root_is_rejected(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "secret.py").write_text("s", encoding="utf-8")
        try:
            os.symlink(outside / "secret.py", self.root / "esc.py")
        except (OSError, NotImplementedError):
            self.skipTest("no symlink on this host")
        res = ar.lots({"a": ["esc.py"]}, str(self.root))
        self.assertEqual((res["lots"], res["census_rejected"]), ([], ["esc.py"]))

    # ---- merge under --global -----------------------------------------------
    # The contract of security-code-review-global § Output (lot A, 3e76413c).
    DEF = (Path(__file__).resolve().parents[2]
           / ".claude" / "agents" / "security-code-review-global.md")
    # the github def had no example (closing review F4): its own pair must merge too
    DEF_GITHUB = (Path(__file__).resolve().parents[2]
                  / ".github" / "agents" / "security-code-review-global.agent.md")
    CONTRACT_P1 = {"census": {"backend": ["backend/src/main/java/Api.java"], "frontend": []},
                   "stats": {"modules_total": 2, "files_candidate": 1, "units_untriaged": [],
                             "stopped": "complete"},
                   "findings": []}
    CONTRACT_PK = {"stats": {"files_read_paths": ["backend/src/main/java/Api.java"],
                             "stopped": "complete", "findings_dropped": 0},
                   "findings": []}

    def def_output_blocks(self, path=None):
        """The ```json blocks of the def's `## Output` section — READ, never copied, so
        an edit of the def turns this red. Red on lot B alone, by design: the base def
        still emits the single-shot code-review.json; lot A of the same task brings the
        pass contract and the two lots merge together (exec-critic: fusion conjointe)."""
        path = path or self.DEF
        text = path.read_text(encoding="utf-8")
        self.assertIn("\n## Output", text, f"{path}: no ## Output section")
        section = re.split(r"\n## ", text.split("\n## Output", 1)[1], maxsplit=1)[0]
        blocks = re.findall(r"```json\n(.*?)\n```", section, re.S)
        self.assertEqual(len(blocks), 2, (
            f"{path} § Output: {len(blocks)} json block(s), expected the pass-1 and "
            "pass-k examples of the -global pass contract (lot A of T-01M51GN76VNBC3S4VBBRCHD6S4)"))
        return [json.loads(b) for b in blocks]

    def test_the_defs_output_examples_merge_complete(self):
        """The def's own pass-1 and pass-k examples, run through --lots and --global,
        are one complete run: every census path read, no INCOMPLETE — claude and github."""
        for path in (self.DEF, self.DEF_GITHUB):
            with self.subTest(path.name):
                self.clear_review_files()
                self.sca_go()
                p1, pk = self.def_output_blocks(path)
                paths = {q for ps in p1["census"].values() for q in ps}
                for q in paths:
                    self.mk(q, 10)
                write(self.rd / "code-review.pass-1.json", p1)
                self.assertEqual(len(self.split()), 1)
                write(self.rd / "code-review.pass-2.json", pk)
                _, doc, out = self.report("--global")
                self.assertIn(f"coverage: {len(paths)}/{len(paths)} files (100 %) — déclarés "
                              "par l'agent · passes: 2 · stopped: complete", out)
                self.assertNotIn("INCOMPLETE", doc + out)
                for f in pk["findings"]:
                    self.assertIn(f"<code>{html.escape(str(f['file']))}:{f['line']}</code>", doc)

    def test_keys_outside_the_contract_are_never_guessed(self):
        """census under `stats`, files_read_paths at the top level: absent, so
        INCOMPLETE — never read from wherever they happen to sit."""
        self.sca_go()
        self.mk("backend/src/main/java/Api.java", 10)
        p1, pk = self.CONTRACT_P1, self.CONTRACT_PK
        write(self.rd / "code-review.lots.json", {"lots": [["backend/src/main/java/Api.java"]]})
        write(self.rd / "code-review.pass-1.json",
              {"stats": dict(p1["stats"], census=p1["census"]), "findings": []})
        write(self.rd / "code-review.pass-2.json", pk)
        _, _, out = self.report("--global")
        self.assertIn("coverage: unmeasured (no valid census)", out)
        self.assertIn("INCOMPLETE — pass 1 without census", out)
        write(self.rd / "code-review.pass-1.json", p1)
        write(self.rd / "code-review.pass-2.json",
              {"files_read_paths": pk["stats"]["files_read_paths"],  # the ONLY fault
               "stats": {"stopped": "complete", "findings_dropped": 0}, "findings": []})
        _, _, out = self.report("--global")
        self.assertIn("coverage: 0/1 files (0 %)", out)
        self.assertIn("INCOMPLETE — invalid-pass (pass 2: files_read_paths, stopped, "
                      "findings or findings_dropped malformed)", out)

    def test_absolute_path_under_root_counts_as_read(self):
        self.sca_go()
        self.census_pass({"api": [self.mk("src/a.py", 10)]})
        self.split()
        self.lot_pass(2, [str(Path(self.tmp.name) / "src" / "a.py")])
        _, _, out = self.report("--global")
        self.assertIn("coverage: 1/1 files (100 %)", out)
        self.assertNotIn("INCOMPLETE", out)

    def test_complete_run_ten_of_ten_no_banner(self):
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        code, doc, out = self.report("--global")
        self.assertEqual(code, 0)
        line = ("coverage: 10/10 files (100 %) — déclarés par l'agent · passes: 4 · "
                "stopped: complete")
        self.assertIn(line, out)
        self.assertIn(html.escape(line, quote=True), doc)  # l&#x27;agent in the HTML
        self.assertNotIn("INCOMPLETE", doc + out)
        self.assertIn("modules: 3/3 covered", doc)

    def test_lot_not_run_is_forty_percent_incomplete(self):
        """Pass 3 is lot 2's yet re-declares lot 1: never counted twice (a SUM of the
        passes' reads would say 8/10), never as lot 2."""
        self.sca_go()
        _, lots = self.ten_files()
        self.lot_pass(2, lots[0])
        self.lot_pass(3, lots[0])
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 4/10 files (40 %)", out)
        self.assertIn("INCOMPLETE — 1 lot(s) not run; 6 file(s) unread", out)
        self.assertIn("<strong>INCOMPLETE — 1 lot(s) not run; 6 file(s) unread</strong>", doc)

    def test_interrupted_executor_reads_bounded_to_the_lot(self):
        """K - 1 < number of lots, and pass 2 claims the WHOLE census: only its lot counts."""
        self.sca_go()
        census, _ = self.ten_files()
        self.lot_pass(2, [p for ps in census.values() for p in ps])
        _, _, out = self.report("--global")
        self.assertIn("coverage: 4/10 files (40 %)", out)
        self.assertIn("INCOMPLETE — 2 lot(s) not run; 6 file(s) unread", out)

    def test_twelve_passes_merge_in_numeric_order(self):
        """pass-10..12 sort after pass-9: k is the integer, never a lexical position."""
        self.sca_go()
        self.census_pass({"u": [self.mk(f"big/f{i:02}.bin", 200_000) for i in range(11)]})
        lots = self.split()
        self.assertEqual(len(lots), 11)
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        _, _, out = self.report("--global")
        self.assertIn("coverage: 11/11 files (100 %) — déclarés par l'agent · passes: 12 · "
                      "stopped: complete", out)
        self.assertNotIn("INCOMPLETE", out)
        self.lot_pass(12, lots[10], stopped="budget")  # the LAST pass is k = 12
        _, _, out = self.report("--global")
        self.assertIn("stopped: budget", out)

    def test_missing_pass_number_is_incomplete(self):
        self.sca_go()
        _, lots = self.ten_files()
        self.lot_pass(2, lots[0])
        self.lot_pass(4, lots[2])
        _, _, out = self.report("--global")
        self.assertIn("coverage: 6/10 files (60 %)", out)
        self.assertIn("INCOMPLETE — missing pass(es) 3; 4 file(s) unread", out)

    def test_complete_declared_but_lot_unread(self):
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, [] if k == 3 else lot)
        _, _, out = self.report("--global")
        self.assertIn("coverage: 6/10 files (60 %)", out)
        self.assertIn("stopped: complete\nINCOMPLETE — 4 file(s) unread\n", out)

    def test_a_later_lot_on_budget_is_a_local_incomplete(self):
        """C35: after the probe, a lot that stops on `budget` is a local gap: the
        merge says INCOMPLETE even when that pass declares its whole lot read."""
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot, stopped="budget" if k == 3 else "complete")
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 10/10 files (100 %)", out)
        self.assertIn("INCOMPLETE — pass 3 stopped on budget", out)
        self.assertIn("caps hit: True", doc)

    def test_dropped_findings_are_incomplete(self):
        """exec-critic (lot B): findings_dropped was read nowhere — 40 findings cut by
        a pass's ~60 cap rendered 1/1 (100 %) with no INCOMPLETE."""
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot, dropped=40 if k == 3 else 0)
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 10/10 files (100 %)", out)
        self.assertIn("INCOMPLETE — pass 3 dropped 40 findings\n", out)  # the console says it
        self.assertIn("<strong>INCOMPLETE — pass 3 dropped 40 findings</strong>", doc)
        self.assertIn("caps hit: True", doc)

    def test_a_pass_beyond_the_lots_is_refused(self):
        """exec-critic blind spot: pass 5 when lots.json lists 3 lots — accepted, its
        finding rendered. Now invalid-pass, named, its reads and findings dropped."""
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        self.lot_pass(5, lots[0], findings=[{"file": "src/extra/EXTRA.py", "line": 7,
                                             "severity": "high", "summary": "extra"}])
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 10/10 files (100 %)", out)
        self.assertIn("INCOMPLETE — invalid-pass (pass 5 beyond the 3 lot(s) of "
                      "code-review.lots.json)", out)
        self.assertNotIn("EXTRA.py", doc)

    def test_files_candidate_is_the_count_of_census_paths(self):
        """files_candidate = the paths the census LISTS (duplicates included); any other
        value is an inconsistent census, INCOMPLETE."""
        self.sca_go()
        census, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        self.census_pass(census, files_candidate=9)
        _, _, out = self.report("--global")
        self.assertIn("coverage: 10/10 files (100 %)", out)
        self.assertIn("INCOMPLETE — files_candidate 9 ≠ 10 census paths", out)
        self.clear_review_files()  # one file listed by two units: 2 listed, 1 to read
        self.census_pass({"a": [self.mk("x.py", 10)], "b": ["./x.py"]})
        for k, lot in enumerate(self.split(), 2):
            self.lot_pass(k, lot)
        _, _, out = self.report("--global")
        self.assertIn("coverage: 1/1 files (100 %)", out)
        self.assertNotIn("INCOMPLETE", out)

    def test_malformed_pass_is_invalid_pass_never_an_exception(self):
        self.sca_go()
        census = {"api": [self.mk("src/a.py", 10)]}
        st1 = {"modules_total": 1, "files_candidate": 1, "stopped": "complete",
               "units_untriaged": []}
        good1 = {"census": census, "stats": st1}
        good2 = {"stats": {"files_read_paths": ["src/a.py"], "stopped": "complete",
                           "findings_dropped": 0},
                 "findings": [{"file": "src/a.py", "line": 1, "severity": 3, "summary": "s"}]}
        st2 = good2["stats"]
        cases = (
            ("census not a dict", {1: dict(good1, census=["src/a.py"]), 2: good2}),
            ("modules_total absent", {1: {"census": census, "stats": {
                k: v for k, v in st1.items() if k != "modules_total"}}, 2: good2}),
            ("modules_total not an integer", {1: {"census": census, "stats": dict(
                st1, modules_total="1")}, 2: good2}),
            ("stopped out of vocabulary", {1: {"census": census, "stats": dict(
                st1, stopped="partial")}, 2: good2}),
            ("files_candidate absent", {1: {"census": census, "stats": {
                k: v for k, v in st1.items() if k != "files_candidate"}}, 2: good2}),
            ("files_read_paths not a list", {1: good1, 2: {"stats": dict(
                st2, files_read_paths="src/a.py")}}),
            ("findings_dropped not an integer", {1: good1, 2: {"stats": dict(
                st2, findings_dropped="40")}}),
            ("unreadable json", {1: "{not json", 2: good2}),
            ("leading-zero pass name", {1: good1, 2: good2, "01": good1}))
        for name, files in cases:
            with self.subTest(name):
                self.clear_review_files()
                write(self.rd / "code-review.lots.json", {"lots": [["src/a.py"]]})
                for k, obj in files.items():
                    (self.rd / f"code-review.pass-{k}.json").write_text(
                        obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
                code, doc, out = self.report("--global")
                self.assertEqual(code, 0)
                self.assertEqual(TestRender.badge(doc), "GO")  # the SCA report, rendered
                self.assertIn("INCOMPLETE — invalid-pass (", out)
                self.assertIn("<strong>INCOMPLETE — invalid-pass (", doc)
        self.clear_review_files()  # the valid pair: a non-string severity renders
        write(self.rd / "code-review.lots.json", {"lots": [["src/a.py"]]})
        write(self.rd / "code-review.pass-1.json", good1)
        write(self.rd / "code-review.pass-2.json", good2)
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 1/1 files (100 %)", out)
        self.assertIn("<code>src/a.py:1</code>", doc)

    def test_truncated_census_names_its_untriaged_units(self):
        self.sca_go()
        census = {f"u{i}": [self.mk(f"u{i}/a.py", 10)] for i in range(1, 9)}
        self.census_pass(census, modules_total=10, stopped="budget", untriaged=["u9", "u10"])
        for k, lot in enumerate(self.split(), 2):
            self.lot_pass(k, lot)
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 8/8 files (100 %)", out)
        self.assertIn("INCOMPLETE — census stopped on budget; units untriaged: u9, u10", out)
        self.assertIn("modules: 8/10 covered · unread: u10, u9", doc)
        self.clear_review_files()  # a census short of modules_total, nothing untriaged
        self.census_pass(census, modules_total=12)
        for k, lot in enumerate(self.split(), 2):
            self.lot_pass(k, lot)
        _, _, out = self.report("--global")
        self.assertIn("INCOMPLETE — units 8 of modules_total 12", out)

    def test_census_stopped_on_budget_is_incomplete(self):
        self.sca_go()
        self.census_pass({"api": [self.mk("a.py", 10)]}, stopped="budget")
        for k, lot in enumerate(self.split(), 2):
            self.lot_pass(k, lot)
        _, doc, out = self.report("--global")
        self.assertIn("coverage: 1/1 files (100 %)", out)
        self.assertIn("INCOMPLETE — census stopped on budget", out)
        self.assertIn("caps hit: True", doc)

    def test_empty_census_is_zero_of_zero_na(self):
        self.sca_go()
        self.census_pass({}, modules_total=0)
        self.assertEqual(self.split(), [])
        code, _, out = self.report("--global")
        self.assertEqual(code, 0)
        self.assertIn("coverage: 0/0 files (n/a) — déclarés par l'agent · passes: 1 · "
                      "stopped: complete", out)
        self.assertNotIn("INCOMPLETE", out)

    def test_empty_unit_untriaged_is_not_covered(self):
        self.sca_go()
        census = {"api": [self.mk("a.py", 10)], "docs": []}
        for untriaged, expected in ((["docs"], "modules: 1/2 covered · unread: docs</p>"),
                                    ([], "modules: 2/2 covered</p>")):
            with self.subTest(untriaged=untriaged):
                self.census_pass(census, untriaged=untriaged)
                for k, lot in enumerate(self.split(), 2):
                    self.lot_pass(k, lot)
                _, doc, _ = self.report("--global")
                self.assertIn(expected, doc)

    def test_global_without_pass_is_absent_run_failed(self):
        self.sca_go()
        code, doc, out = self.report("--global")
        self.assertEqual(code, 0)
        self.assertIn("<strong>global review: absent (run failed)</strong>", doc)
        self.assertIn("global review: absent (run failed)", out)
        self.assertEqual(TestRender.badge(doc), "GO")

    def test_passes_without_global_are_not_merged(self):
        self.sca_go()
        _, lots = self.ten_files()
        self.lot_pass(2, lots[0])
        _, doc, out = self.report()
        self.assertIn("2 pass files present, not merged (no --global)", out)
        self.assertNotIn("coverage:", doc + out)
        self.assertNotIn("Global code review", doc)
        self.assertNotIn("run failed", doc + out)

    def test_single_shot_fallback_has_no_coverage_line(self):
        self.sca_go()
        write(self.rd / "code-review.json",
              {"stats": {"files_flagged": 3, "files_read": 2, "caps_hit": False}, "findings": []})
        for extra in ((), ("--global",)):
            with self.subTest(extra=extra):
                _, doc, out = self.report(*extra)
                self.assertIn("files read: 2", doc)
                self.assertNotIn("coverage:", doc + out)
                self.assertNotIn("modules: ", doc)
                self.assertNotIn("INCOMPLETE", doc + out)

    def test_incomplete_review_never_touches_the_summary(self):
        self.sca_go()
        _, lots = self.ten_files()
        self.lot_pass(2, lots[0])
        _, doc, out = self.report("--global")
        self.assertIn("INCOMPLETE", out)
        self.assertEqual(TestRender.badge(doc), "GO")
        self.assertNotIn("obtained NO verdict", doc)
        self.assertEqual(ar.gather(str(self.rd), str(self.wfile), True)["summary"],
                         ar.gather(str(self.rd), str(self.wfile), False)["summary"])

    def test_lock_busy_with_complete_passes_side_by_side(self):
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        (self.rd / "audit-log.jsonl").write_text(json.dumps(
            {"ts": "2026-10-16T06:00:00Z", "mode": "scan", "entry": "sca-scan.sh",
             "module": "root", "verdict": "NO-GO", "reason": "lock-busy"}) + "\n",
            encoding="utf-8")
        _, doc, out = self.report("--global")
        self.assertEqual(TestRender.badge(doc), "NO-GO")
        self.assertIn("latest run obtained NO verdict (lock-busy, 2026-10-16T06:00:00Z)", doc)
        self.assertIn("coverage: 10/10 files (100 %)", out)
        self.assertNotIn("INCOMPLETE", out)

    # ---- closing review (critic-opus, audit global en Opus) ------------------
    def lots_err(self):
        """--lots run with stdout AND stderr captured: (rc, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ar.main(["--reports-dir", str(self.rd), "--lots"])
        return code, out.getvalue(), err.getvalue()

    def clear(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ar.main(["--reports-dir", str(self.rd), "--clear"])
        return code, out.getvalue(), err.getvalue()

    def age(self, name, ns):
        """Set the mtime of a review file to `ns` (explicit: no same-tick flakiness)."""
        os.utime(self.rd / name, ns=(ns, ns))

    def run1_complete(self):
        """Yesterday's run: every lot read, one finding OLD-RUN1-lot<i> per lot."""
        census, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot, findings=[{"file": lot[0], "line": 1, "severity": "high",
                                             "summary": f"OLD-RUN1-lot{k - 1}"}])
        return census, lots

    def test_clear_removes_the_review_files_by_fixed_name_only(self):
        """C1 (F1): /audit step 3 by code. Removes the review files and audit-latest.html,
        bad-named passes included; keeps the SCA artefacts and timestamped reports."""
        self.sca_go()
        self.run1_complete()
        self.lot_pass("01", ["x"])
        write(self.rd / "code-review.json", {"stats": {}, "findings": []})
        (self.rd / "audit-latest.html").write_text("old", encoding="utf-8")
        (self.rd / "audit-20261015-000000.html").write_text("old", encoding="utf-8")
        code, out, err = self.clear()
        self.assertEqual((code, err), (0, ""))
        left = sorted(p.name for p in self.rd.iterdir())
        self.assertEqual(left, ["audit-20261015-000000.html", "effective-verdict.json"])
        for name in ("code-review.json", "code-review.lots.json", "audit-latest.html",
                     "code-review.pass-1.json", "code-review.pass-4.json",
                     "code-review.pass-01.json"):
            self.assertIn(name, out)
        self.assertEqual(self.clear()[:2], (0, "cleared: nothing\n"))
        (self.rd / "code-review.json").mkdir()  # a file that cannot go: rc 1, named
        code, _, err = self.clear()
        self.assertEqual(code, 1)
        self.assertIn("NOT removed: code-review.json", err)

    def test_stale_passes_of_an_earlier_run_are_never_merged(self):
        """F1/T2 (critic sim3): run 1 complete, run 2 rewrites pass 1, --lots, then the
        probe (pass 2) stops on budget. Before: passes 3-4 of run 1 merged as today's,
        « 58 % · stopped: complete », OLD-RUN1-lot2/lot3 rendered."""
        self.sca_go()
        for leg in ("clear", "identical census, no clear", "new census, no clear"):
            with self.subTest(leg):
                self.clear_review_files()
                census, _ = self.run1_complete()
                if leg == "clear":
                    self.assertEqual(self.clear()[0], 0)
                    self.sca_go()
                    self.census_pass(census)
                else:
                    t0 = (self.rd / "code-review.pass-1.json").stat().st_mtime_ns
                    for k in (2, 3, 4):
                        self.age(f"code-review.pass-{k}.json", t0 - 10**9)
                    if leg.startswith("new"):  # the lots change: stale whatever the mtimes
                        census = dict(census, extra=[self.mk("src/extra/e.py", 80_000)])
                        self.census_pass(census)
                        for k in (2, 3, 4):
                            self.age(f"code-review.pass-{k}.json", t0 + 10**12)
                    else:
                        self.census_pass(census)
                        self.age("code-review.pass-1.json", t0)
                code, _, err = self.lots_err()
                self.assertEqual(code, 0)
                if leg != "clear":
                    self.assertIn("purged 3 stale pass file(s) of an earlier run: "
                                  "code-review.pass-2.json, code-review.pass-3.json, "
                                  "code-review.pass-4.json", err)
                self.lot_pass(2, [], stopped="budget")
                _, doc, out = self.report("--global")
                self.assertNotIn("OLD-RUN1", doc)
                self.assertIn("lot(s) not run", out)
                self.assertNotIn("stopped: complete", out)

    def test_a_second_lots_of_the_same_run_keeps_its_passes(self):
        """The guard of the purge: same lots, passes newer than pass 1 -> kept."""
        self.sca_go()
        _, lots = self.ten_files()
        t1 = (self.rd / "code-review.pass-1.json").stat().st_mtime_ns
        for k, lot in enumerate(lots[:2], 2):
            self.lot_pass(k, lot)
            self.age(f"code-review.pass-{k}.json", t1 + 10**9)
        code, _, err = self.lots_err()
        self.assertEqual(code, 0)
        self.assertNotIn("purged", err)
        self.assertTrue((self.rd / "code-review.pass-2.json").is_file())
        self.assertTrue((self.rd / "code-review.pass-3.json").is_file())

    def test_a_malformed_pass_never_hides_its_findings(self):
        """C2 (F2, critic sim2): a complete pass carrying a CRITICAL, with (a)
        findings_dropped absent, (b) stopped 'partial', (c) findings_dropped null, (d)
        files_read_paths at the top level (S6). Before: the CRITICAL vanished, 0/1."""
        self.sca_go()
        self.census_pass({"api": [self.mk("src/a.py", 10)]})
        self.split()
        rce = {"file": "src/a.py", "line": 9, "severity": "critical", "category": "rce",
               "summary": "RCE-MARKER"}
        ok = {"files_read_paths": ["src/a.py"], "stopped": "complete", "findings_dropped": 0}
        variants = (
            ("findings_dropped absent", {"stats": {k: v for k, v in ok.items()
                                                    if k != "findings_dropped"}}),
            ("stopped partial", {"stats": dict(ok, stopped="partial")}),
            ("findings_dropped null", {"stats": dict(ok, findings_dropped=None)}),
            ("files_read_paths top-level", {"files_read_paths": ["src/a.py"], "stats": {
                "stopped": "complete", "findings_dropped": 0}}))
        for name, obj in variants:
            with self.subTest(name):
                write(self.rd / "code-review.pass-2.json", dict(obj, findings=[rce]))
                code, doc, out = self.report("--global")
                self.assertEqual(code, 0)
                self.assertIn("RCE-MARKER", doc)
                self.assertIn("coverage: 0/1 files (0 %)", out)
                self.assertIn("INCOMPLETE — invalid-pass (pass 2: files_read_paths, stopped, "
                              "findings or findings_dropped malformed, 1 finding(s) kept)", out)
        # a pass BEYOND the lots is judged first, whatever its shape: its findings dropped
        write(self.rd / "code-review.pass-2.json", {"stats": ok, "findings": []})
        write(self.rd / "code-review.pass-3.json", {"stats": {}, "findings": [
            dict(rce, file="src/extra/EXTRA.py")]})
        _, doc, out = self.report("--global")
        self.assertIn("invalid-pass (pass 3 beyond the 1 lot(s) of code-review.lots.json)", out)
        self.assertNotIn("EXTRA.py", doc)

    def test_deep_nesting_is_invalid_pass_never_a_traceback(self):
        """C5 (F5): json.loads raises RecursionError on '['*100000 under Python <= 3.12
        (eval-nightly runs 3.12); 3.14 does not raise, so the patched leg holds the
        `except` on every interpreter."""
        self.sca_go()
        self.census_pass({"api": [self.mk("src/a.py", 10)]})
        self.split()
        (self.rd / "code-review.pass-2.json").write_text("[" * 100_000 + "]" * 100_000,
                                                         encoding="utf-8")
        code, _, out = self.report("--global")  # live: rc 0 on every interpreter
        self.assertEqual(code, 0)
        self.assertIn("invalid-pass (pass 2 unreadable or not a JSON object)", out)
        real = json.loads

        def deep(s, *a, **kw):
            if str(s).startswith("[[[["):
                raise RecursionError("maximum recursion depth exceeded")
            return real(s, *a, **kw)
        with mock.patch.object(ar.json, "loads", side_effect=deep):
            self.assertIsNone(ar.load(self.rd / "code-review.pass-2.json"))
            code, _, out = self.report("--global")
            self.assertEqual(code, 0)
            self.assertIn("invalid-pass (pass 2 unreadable or not a JSON object)", out)
            (self.rd / "audit-log.jsonl").write_text(
                json.dumps({"mode": "scan", "entry": "sca-scan.sh", "module": "root",
                            "verdict": "NO-GO", "reason": "lock-busy"}) + "\n"
                + "[" * 50 + "]" * 50 + "\n", encoding="utf-8")
            self.assertEqual(ar._last_row(self.rd)["reason"], "lock-busy")  # line skipped
            (self.rd / "code-review.pass-1.json").write_text("[" * 100_000, encoding="utf-8")
            self.assertEqual(self.lots_err()[0], 2)

    def test_a_huge_pass_number_costs_no_loop(self):
        """C6 (F6, critic S5b): one code-review.pass-5000000.json -> 43.9 MB of stdout,
        and the same in the HTML. Bounded: beyond the lots it is ONE invalid-pass; without
        lots.json the gaps are counted, the first 20 named."""
        self.sca_go()
        _, lots = self.ten_files()
        for k, lot in enumerate(lots, 2):
            self.lot_pass(k, lot)
        write(self.rd / "code-review.pass-5000000.json", {})
        _, doc, out = self.report("--global")
        self.assertLess(len(out), 2_000)
        self.assertLess(len(doc), 100_000)
        self.assertIn("invalid-pass (pass 5000000 beyond the 3 lot(s) of code-review.lots.json)", out)
        self.assertNotIn("missing pass(es)", out)
        (self.rd / "code-review.lots.json").unlink()
        for k in (2, 3, 4):
            (self.rd / f"code-review.pass-{k}.json").unlink()
        _, _, out = self.report("--global")
        self.assertLess(len(out), 2_000)
        shown = ", ".join(str(k) for k in range(2, 22))
        self.assertIn(f"missing pass(es) {shown} (+{5_000_000 - 2 - 20} more)", out)

    def test_lots_capped_in_files(self):
        """C7 (F7a): 200 files of 1 byte fit one 350 KB lot; capped at LOT_MAX_FILES
        (an estimate under gemini's max_turns 100) -> 80, 80, 40."""
        self.assertEqual(ar.LOT_MAX_FILES, 80)
        census = {"u": [self.mk(f"s/f{i:03}.py", 1) for i in range(200)]}
        lots = ar.lots(census, str(self.root))["lots"]
        self.assertEqual([len(lot) for lot in lots], [80, 80, 40])
        self.assertEqual([p for lot in lots for p in lot], census["u"])  # once, in order

    def test_lots_announce_their_count_and_estimate_on_stderr(self):
        """C8 (F8): the run announces its size before pass 2 — on stderr, so stdout
        stays the lots JSON the executor parses. 10 x 80 000 o, 3 lots:
        4 x 12k + 800 000 // 3584 = 271k."""
        self.census_pass({"api": [self.mk(f"src/api/f{i}.py", 80_000) for i in range(4)],
                          "db": [self.mk(f"src/db/f{i}.py", 80_000) for i in range(4)],
                          "ui": [self.mk(f"src/ui/f{i}.py", 80_000) for i in range(2)]})
        code, out, err = self.lots_err()
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["lots"]), 3)  # stdout: the JSON alone
        self.assertIn("lots: 3 · passes: 4 (census included) · 800,000 bytes to read · "
                      "estimate ≈ 271k tokens", err)


if __name__ == "__main__":
    unittest.main()
