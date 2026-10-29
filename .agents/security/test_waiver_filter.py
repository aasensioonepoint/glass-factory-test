#!/usr/bin/env python3
"""Tests for waiver_filter.py — run: python3 -m unittest .agents/security/test_waiver_filter.py (from repo root: cd .agents/security && python -m unittest test_waiver_filter -v)"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waiver_filter as wf


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


NPM_V1 = {  # pnpm / npm<7 "advisories" format
    "advisories": {
        "1065": {
            "module_name": "lodash",
            "severity": "high",
            "cves": ["CVE-2021-23337"],
            "patched_versions": ">=4.17.21",
            "findings": [{"version": "4.17.20", "paths": ["lodash"]}],
        }
    }
}

NPM_V2 = {  # npm>=7 "vulnerabilities" format (no installed version inside)
    "vulnerabilities": {
        "lodash": {
            "name": "lodash",
            "severity": "high",
            "isDirect": True,
            "via": [{"url": "https://github.com/advisories/GHSA-35jh-r3h4-6jhm", "title": "Command Injection"}],
            "fixAvailable": True,
        }
    }
}

LOCK_V2 = {"packages": {"": {}, "node_modules/lodash": {"version": "4.17.20"}}}

DC_REPORT = {
    "dependencies": [
        {
            "fileName": "spring-core-5.3.0.jar",
            "packages": [{"id": "pkg:maven/org.springframework/spring-core@5.3.0"}],
            "vulnerabilities": [{"name": "CVE-2022-22965", "severity": "CRITICAL"}],
        },
        {"fileName": "clean.jar", "packages": [{"id": "pkg:maven/org.x/clean@1.0"}]},
    ]
}

SOCKET_REPORT = {"alerts": [{"package": "evil-pkg", "version": "1.0.0", "type": "installScript", "severity": "high"}]}

TRIVY_REPORT = {  # trivy config --format json (IaC misconfiguration)
    "Results": [
        {
            "Target": "Dockerfile",
            "Class": "config",
            "Type": "dockerfile",
            "Misconfigurations": [
                {
                    "Type": "Dockerfile Security Check",
                    "ID": "DS002",
                    "AVDID": "AVD-DS-0002",
                    "Title": "Last USER should not be root",
                    "Severity": "HIGH",
                    "Status": "FAIL",
                },
                {  # PASS rows are not findings
                    "ID": "DS026",
                    "AVDID": "AVD-DS-0026",
                    "Title": "No HEALTHCHECK defined",
                    "Severity": "LOW",
                    "Status": "PASS",
                },
            ],
        }
    ]
}


BASE_REF = ("node:22.23.2-bookworm-slim@sha256:"
            "f32b81066cde10a75dbac96646099533316d94bac4150c55da1636e1f0ffdc46")

TRIVY_IMAGE_REPORT = {  # trivy image --format json (vulnerabilities, not misconfig)
    "SchemaVersion": 2,
    "ArtifactName": "myapp/web:ci",         # the LOCAL build tag — deliberately NOT the pivot
    "ArtifactType": "container_image",
    "_BaseRef": BASE_REF,                   # injected by the project's image-scan step
    "Results": [
        {
            "Target": "myapp/web:ci (debian 12.13)",
            "Class": "os-pkgs",
            "Type": "debian",
            "Vulnerabilities": [
                {"VulnerabilityID": "CVE-2026-13221", "PkgName": "perl-base",
                 "InstalledVersion": "5.36.0-7+deb12u2", "Severity": "CRITICAL",
                 "Status": "affected"},
                {"VulnerabilityID": "CVE-2023-45853", "PkgName": "zlib1g",
                 "InstalledVersion": "1:1.2.13.dfsg-1", "Severity": "CRITICAL",
                 "Status": "will_not_fix"},
                {"VulnerabilityID": "CVE-2026-41992", "PkgName": "gzip",
                 "InstalledVersion": "1.12-1", "Severity": "HIGH",
                 "Status": "fix_deferred"},
                # No Status field at all — same fail-safe reflex as parse_trivy.
                {"VulnerabilityID": "CVE-2025-69720", "PkgName": "libtinfo6",
                 "InstalledVersion": "6.4-4", "Severity": "HIGH"},
                # No PkgName => not attributable to a package, skipped.
                {"VulnerabilityID": "CVE-2026-00000", "Severity": "HIGH"},
            ],
        },
        {
            "Target": "usr/local/lib/node_modules/npm/package.json",
            "Class": "lang-pkgs",
            "Type": "node-pkg",
            "Vulnerabilities": [
                # Status "fixed" = upstream HAS a fix the image did not pick up:
                # the most actionable finding of all, never a reason to drop.
                {"VulnerabilityID": "CVE-2026-59873", "PkgName": "tar",
                 "InstalledVersion": "7.4.3", "FixedVersion": "7.5.19",
                 "Severity": "CRITICAL", "Status": "fixed"},
            ],
        },
    ],
}


PIP_AUDIT_REPORT = {  # pip-audit --no-deps -r requirements.txt -f json (T-00000292)
    "dependencies": [
        {
            "name": "flask",
            "version": "2.0.0",
            "vulns": [
                {"id": "PYSEC-2023-62", "fix_versions": ["2.2.5", "2.3.2"],
                 "aliases": ["CVE-2023-30861", "GHSA-m2qf-hxjv-5gpq"],
                 "severity": "HIGH", "description": "Possible session disclosure"},
            ],
        },
        {"name": "clean-pkg", "version": "1.0.0", "vulns": []},  # no vuln -> ignored
    ],
    "fixes": [],
}


def waiver(**kw):
    base = {
        "package": "lodash", "version": "4.17.20", "ecosystem": "npm",
        "advisories": "*", "class": "known_cve", "severity_at_accept": "high",
        "status": "accepted", "accepted_by": "test", "date": "2026-07-18",
        "reason": "test", "origin": "test",
    }
    base.update(kw)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reports = self.root / ".sca-reports"
        self.reports.mkdir()
        self.wfile = self.root / "sca-waivers.json"
        write(self.wfile, {"waivers": []})

    def tearDown(self):
        self.tmp.cleanup()

    def run_filter(self, gate="high"):
        code = wf.main([
            "--reports-dir", str(self.reports), "--waivers", str(self.wfile),
            "--root", str(self.root), "--gate-level", gate,
        ])
        verdict = json.loads((self.reports / "effective-verdict.json").read_text(encoding="utf-8"))
        return code, verdict

    def run_raw(self, gate="high"):
        """main() with stdout/stderr captured and the pivot NOT read.

        For the rc 3 cases, where the pivot must NOT exist: run_filter() reads it
        unconditionally and would raise before any assertion could be made.
        """
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = wf.main([
                "--reports-dir", str(self.reports), "--waivers", str(self.wfile),
                "--root", str(self.root), "--gate-level", gate,
            ])
        return code, out.getvalue(), err.getvalue()

    def seed_stale_pivot(self):
        """A GO pivot left by an EARLIER run, marked so its survival is visible."""
        write(self.reports / "effective-verdict.json",
              {"gate_level": "high", "active": [], "counters": {"active_at_gate": 0},
               "notes": ["SEEDED-STALE"]})

    def degraded_lines(self):
        p = self.reports / ".degraded"
        return p.read_text(encoding="utf-8").splitlines() if p.is_file() else None


# The measured truncation (plan preamble D1): pip-audit cut in the middle of a HIGH.
PIP_AUDIT_TRUNCATED = ('{"dependencies":[{"name":"flask","version":"2.0.0","vulns":'
                       '[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"severity":"HIGH"')


def unreadable_line(fname, klass):
    return f"waiver_filter: report {fname} unreadable/malformed ({klass}) — no effective verdict"


class TestParsing(Base):
    def test_npm_v1_format_normalized(self):
        write(self.reports / "npm-audit.json", NPM_V1)
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        f = v["active"][0]
        self.assertEqual((f["ecosystem"], f["package"], f["version"], f["advisory"], f["class"]),
                         ("npm", "lodash", "4.17.20", "CVE-2021-23337", "known_cve"))

    def test_npm_v2_resolves_version_from_lockfile(self):
        write(self.reports / "npm-audit.json", NPM_V2)
        write(self.root / "package-lock.json", LOCK_V2)
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual(v["active"][0]["version"], "4.17.20")
        self.assertEqual(v["active"][0]["advisory"], "GHSA-35jh-r3h4-6jhm")

    def test_owasp_dc_purl_maven_colon_naming(self):
        write(self.reports / "dependency-check-report.json", DC_REPORT)
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        f = v["active"][0]
        self.assertEqual((f["ecosystem"], f["package"], f["version"]),
                         ("maven", "org.springframework:spring-core", "5.3.0"))
        self.assertEqual(len(v["active"]), 1)  # dep without vulnerabilities ignored

    def test_socket_alerts_are_supply_chain(self):
        write(self.reports / "socket.json", SOCKET_REPORT)
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual(v["active"][0]["class"], "supply_chain")

    def test_malformed_report_fails_closed_rc3(self):
        """A malformed REPORT is a verdict NOT obtained — rc 3, never a skip.

        PIÈGE 2, amended on purpose: this test used to be
        `test_malformed_report_skipped_with_note` and pinned `code == 0`, i.e. it
        PINNED the fail-open — an unreadable report was dropped with a note and the
        run went GO on whatever remained (measured: a truncated pip-audit.json
        holding a HIGH gave `SUMMARY active=0`, rc 0). Decision
        S-01M4XXZ7FMDJ3ZQFDVF2FC9WJZ: a report present but unreadable is NO-GO, and
        the report is NAMED.
        """
        self.seed_stale_pivot()
        # A reason sca-scan.sh recorded earlier in the same run: it must survive.
        (self.reports / ".degraded").write_text("trivy: not installed\n", encoding="utf-8")
        (self.reports / "npm-audit.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.run_raw()
        self.assertEqual(code, 3)
        self.assertFalse((self.reports / "effective-verdict.json").exists(),
                         "the stale pivot survived a run that computed no verdict")
        self.assertNotIn("SUMMARY", out)
        self.assertEqual(out, "")
        # EQUALITY on the whole file: appended (the earlier reason kept), the report
        # named by its table literal, the exception CLASS and not its message.
        self.assertEqual(self.degraded_lines(), [
            "trivy: not installed",
            unreadable_line("npm-audit.json", "JSONDecodeError"),
        ])
        self.assertIn("waiver_filter: UNREADABLE report npm-audit.json (", err)
        self.assertTrue(err.rstrip("\n").endswith("— no effective verdict (fail-closed)"), err)

    def test_truncated_pip_audit_with_high_fails_closed(self):
        """The measured case: the cut hides a HIGH, so the answer is rc 3, not GO."""
        (self.reports / "pip-audit.json").write_text(PIP_AUDIT_TRUNCATED, encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse((self.reports / "effective-verdict.json").exists())
        self.assertEqual(self.degraded_lines(),
                         [unreadable_line("pip-audit.json", "JSONDecodeError")])

    def test_zero_byte_report_fails_closed(self):
        (self.reports / "socket.json").write_bytes(b"")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertEqual(self.degraded_lines(),
                         [unreadable_line("socket.json", "JSONDecodeError")])

    def test_readable_high_plus_unreadable_report_is_rc3_not_rc1(self):
        """A readable HIGH does not rescue a partial run: rc 3, not 1.

        rc 1 would read as a COMPLETE verdict with one finding; the truncated
        report beside it may hold more. Every unreadable report is named, in the
        order of the parsers table.
        """
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        (self.reports / "npm-audit.json").write_text("{not json", encoding="utf-8")
        (self.reports / "trivy-config.json").write_text('{"Results": [', encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse((self.reports / "effective-verdict.json").exists())
        self.assertEqual(self.degraded_lines(), [
            unreadable_line("npm-audit.json", "JSONDecodeError"),
            unreadable_line("trivy-config.json", "JSONDecodeError"),
        ])

    def test_unreadable_register_stays_a_note_discriminating_pair(self):
        """THE DISCRIMINATING PAIR: the REGISTER unreadable is NOT a report unreadable.

        With the register unreadable nothing is waived — already the strictest
        reading — so the run keeps its verdict: rc 1 on the HIGH, a fresh pivot,
        a note, and NO .degraded line. A filter that routed the register through
        the report path would answer rc 3 here.
        """
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        self.wfile.write_text("{not json", encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 1)
        self.assertIn("SUMMARY active=1 ", out)
        v = json.loads((self.reports / "effective-verdict.json").read_text(encoding="utf-8"))
        self.assertTrue(any(n.startswith("sca-waivers.json: unreadable/malformed") for n in v["notes"]),
                        v["notes"])
        self.assertIsNone(self.degraded_lines(), "a register fault wrote a .degraded line")

    def test_trivy_config_parses_fail_rows_only(self):
        write(self.reports / "trivy-config.json", TRIVY_REPORT)
        code, v = self.run_filter()
        self.assertEqual(code, 1)  # AVD-DS-0002 is HIGH >= default gate
        self.assertEqual(len(v["active"]), 1)  # the PASS row is not a finding
        f = v["active"][0]
        self.assertEqual((f["ecosystem"], f["package"], f["version"], f["advisory"],
                           f["severity"], f["class"]),
                          ("iac", "AVD-DS-0002", "Dockerfile", "AVD-DS-0002", "high", "iac_misconfig"))

    def test_pip_audit_normalized_and_gates(self):
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        code, v = self.run_filter()
        self.assertEqual(code, 1)  # HIGH >= default gate
        self.assertEqual(len(v["active"]), 1)  # the dep with no vuln is ignored
        f = v["active"][0]
        self.assertEqual((f["ecosystem"], f["package"], f["version"], f["advisory"],
                           f["severity"], f["class"], f["fix_version"]),
                          ("pypi", "flask", "2.0.0", "PYSEC-2023-62", "high",
                           "known_cve", "2.2.5"))

    def test_pip_audit_waived_is_go(self):
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        write(self.wfile, {"waivers": [waiver(
            ecosystem="pypi", package="flask", version="2.0.0",
            advisories=["PYSEC-2023-62"])]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["active"], [])
        self.assertEqual(v["counters"]["accepted"], 1)


REPORT_NAMES = ("npm-audit.json", "dependency-check-report.json", "socket.json",
                "trivy-config.json", "trivy-image.json", "pip-audit.json")


class TestUnexpectedShape(Base):
    """A report that DECODES but has a shape its parser raises on is rc 3, named.

    exec-critic MAJEUR on lot A of T-01M4X7W4M2: the guard covered only
    read/decode (OSError, ValueError), so `null` in pip-audit.json died in the
    parser (AttributeError, traceback, rc 1, no SUMMARY, no report named), and
    sca-watch then advised "fix the configuration". MEASURED on the three probe
    shapes `null`, `[]`, `{"dependencies": 5}` against each of the six parsers
    before that fix: the eleven shape combinations of RAISING below raised. So
    did an unhashable name, which passes the parser and breaks the dedup key.
    PIÈGE 2, amended on purpose (T-01M4Z33N54TX0Q7VHBZATFNR4X). This docstring
    used to pin the seven other combinations as a residue: readable forms with
    no recognised key, zero findings, hence a GO. SHAPE_CHECKS now runs BEFORE
    the parser. It rejects the eleven shape cases as UnrecognisedShape before
    any parser can raise, and the class column says so. The unhashable name sits
    in a RECOGNISED envelope, so it still reaches the dedup and stays TypeError.
    TestRecognitionTable now pins the former residue, as rc 3 or as one of the
    two named DEGRADED forms. `[]` stays a LEGITIMATE empty report for pip-audit
    (older top-level list) and socket (list of alerts), pinned GO below.
    """
    RAISING = [
        ("npm-audit.json", "null", "UnrecognisedShape"),
        ("dependency-check-report.json", "null", "UnrecognisedShape"),
        ("dependency-check-report.json", "[]", "UnrecognisedShape"),
        ("dependency-check-report.json", '{"dependencies": 5}', "UnrecognisedShape"),
        ("socket.json", "null", "UnrecognisedShape"),
        ("trivy-config.json", "null", "UnrecognisedShape"),
        ("trivy-config.json", "[]", "UnrecognisedShape"),
        ("trivy-image.json", "null", "UnrecognisedShape"),
        ("trivy-image.json", "[]", "UnrecognisedShape"),
        ("pip-audit.json", "null", "UnrecognisedShape"),
        ("pip-audit.json", '{"dependencies": 5}', "UnrecognisedShape"),
        # passes SHAPE_CHECKS and parse_pip_audit, then a list as package breaks
        # the dedup key
        ("pip-audit.json",
         '{"dependencies":[{"name":["x"],"version":"1","vulns":[{"id":"A"}]}]}', "TypeError"),
    ]

    def clear_reports(self):
        for p in self.reports.iterdir():
            p.unlink()

    def test_the_table_reaches_every_parser(self):
        self.assertEqual({r[0] for r in self.RAISING}, set(REPORT_NAMES))

    def test_every_raising_shape_is_rc3_named_never_a_traceback(self):
        for fname, payload, klass in self.RAISING:
            with self.subTest(report=fname, payload=payload):
                self.clear_reports()
                self.seed_stale_pivot()
                (self.reports / fname).write_text(payload, encoding="utf-8")
                code, out, err = self.run_raw()
                self.assertEqual(code, 3)
                self.assertNotIn("SUMMARY", out)
                self.assertFalse((self.reports / "effective-verdict.json").exists(),
                                 "the stale pivot survived")
                self.assertEqual(self.degraded_lines(), [unreadable_line(fname, klass)])
                self.assertIn(f"waiver_filter: UNREADABLE report {fname} (", err)

    def test_empty_list_stays_a_legitimate_empty_report(self):
        """The paired GO: rc 3 must not swallow a form the scanner really emits."""
        for fname in ("pip-audit.json", "socket.json"):
            with self.subTest(report=fname):
                self.clear_reports()
                (self.reports / fname).write_text("[]", encoding="utf-8")
                code, v = self.run_filter()
                self.assertEqual(code, 0)
                self.assertEqual(v["active"], [])
                self.assertIsNone(self.degraded_lines())


# npm without a lockfile (measured: npm answers ENOLOCK, pnpm 10 answers
# ERR_PNPM_AUDIT_NO_LOCKFILE): the two tool errors that mean "nothing audited".
NPM_ENOLOCK = {"error": {
    "code": "ENOLOCK", "summary": "This command requires an existing lockfile.",
    "detail": "Try creating one first with: npm i --package-lock-only\n"
              "Original error: loadVirtual requires existing shrinkwrap file"}}
PNPM_NO_LOCKFILE = {"error": {
    "code": "ERR_PNPM_AUDIT_NO_LOCKFILE",
    "message": "No pnpm-lock.yaml found: Cannot audit a project without a lockfile"}}
# npm WITH a lock and the registry unreachable (critique 2, C2): an error
# envelope with NO `code`. It must stay rc 3, never a DEGRADED GO.
NPM_ECONNREFUSED = ('{"message":"request to https://registry.npmjs.org/-/npm/v1/security/'
                    'advisories/bulk failed, reason: connect ECONNREFUSED 127.0.0.1:443",'
                    '"error":{"summary":"","detail":""}}')


# Written out in full here, never read from the module: an equality against the
# module's own constant could not see a change in it.
def tool_error_line(code):
    return (f"waiver_filter: report npm-audit.json is a tool error ({code}) — "
            "npm audit NOT performed, coverage DEGRADED")


SOCKET_NO_ALERTS = ("waiver_filter: report socket.json carries no alert list — "
                    "supply-chain layer NOT read, coverage DEGRADED")


class TestRecognitionTable(Base):
    """The closed table of step 1 (T-01M4Z33N54TX0Q7VHBZATFNR4X): recognised BEFORE parsed.

    Measured before the rule, with an empty register: pip-audit `{}`, trivy
    `{"Results": {}}`, npm `{}` and npm's registry-unreachable envelope each gave
    rc 0, a GO built on a report nobody recognised. Each check judges the
    envelope: a key that is PRESENT carries its type. The answer is one of three:
    recognised (parsed), one of the two named DEGRADED forms, or UnrecognisedShape
    (rc 3, exactly like a truncation).
    """
    UNRECOGNISED = [
        ("npm-audit.json", "[]"),
        ("npm-audit.json", "{}"),
        ("npm-audit.json", '"advisories"'),
        ("npm-audit.json", '{"dependencies": 5}'),
        ("npm-audit.json", '{"ok": true}'),
        ("npm-audit.json", '{"vulnerabilities": []}'),
        ("npm-audit.json", '{"advisories": []}'),
        ("npm-audit.json", '{"vulnerabilities": {}, "advisories": 5}'),
        ("npm-audit.json", '{"error": "x"}'),
        ("npm-audit.json", '{"error": {"code": "ENOTFOUND"}}'),
        ("npm-audit.json", '{"error": {"code": "E401"}}'),
        ("npm-audit.json", '{"error": {"code": "ETIMEDOUT"}}'),
        ("npm-audit.json", NPM_ECONNREFUSED),
        ("npm-audit.json", '{"error": {"code": "ENOLOCK"}, "vulnerabilities": []}'),
        ("dependency-check-report.json", "{}"),
        ("dependency-check-report.json", '{"ok": true}'),
        ("dependency-check-report.json", '{"dependencies": {}}'),
        ("dependency-check-report.json", '"str"'),
        ("socket.json", "5"),
        ("socket.json", '"str"'),
        ("socket.json", '{"alerts": 5}'),
        ("socket.json", '{"issues": "x"}'),
        ("socket.json", '{"alerts": [], "issues": 5}'),
        # Neither list, a key outside SOCKET_ENVELOPE_KEYS (pilot decision, 2026-10-16):
        # both gave rc 0, active 0 before the closed list — the critical was lost.
        ("socket.json", '{"results": [{"package": "evil-pkg", "version": "1.0.0", '
                        '"severity": "critical", "type": "malware"}]}'),
        ("socket.json", '{"ok": true, "data": {"alerts": [{"package": "evil-pkg", '
                        '"version": "1.0.0", "severity": "critical", "type": "malware"}]}}'),
        ("socket.json", '{"stale": true}'),
        ("trivy-config.json", "{}"),
        ("trivy-config.json", '{"dependencies": 5}'),
        ("trivy-config.json", '{"SchemaVersion": 2, "Results": {}}'),
        ("trivy-config.json", '{"Results": null}'),
        ("trivy-config.json", '{"SchemaVersion": true}'),
        ("trivy-config.json", '{"SchemaVersion": "2"}'),
        ("trivy-image.json", "{}"),
        ("trivy-image.json", '{"dependencies": 5}'),
        ("trivy-image.json", '{"SchemaVersion": 2, "Results": {}}'),
        ("trivy-image.json", '{"SchemaVersion": true}'),
        ("pip-audit.json", "{}"),
        ("pip-audit.json", '{"ok": true}'),
        ("pip-audit.json", '{"dependencies": {}}'),
        ("pip-audit.json", '"str"'),
    ]
    # The paired GO: a form the scanner really emits with nothing to report.
    RECOGNISED_EMPTY = [
        ("npm-audit.json", '{"vulnerabilities": {}}'),
        ("npm-audit.json", '{"advisories": {}}'),
        ("dependency-check-report.json", '{"dependencies": []}'),
        ("socket.json", "[]"),
        ("socket.json", '{"alerts": []}'),
        ("socket.json", '{"issues": []}'),
        ("trivy-config.json", '{"SchemaVersion": 2}'),
        ("trivy-config.json", '{"Results": []}'),
        ("trivy-image.json", '{"SchemaVersion": 2}'),
        ("trivy-image.json", '{"Results": []}'),
        ("pip-audit.json", "[]"),
        ("pip-audit.json", '{"dependencies": []}'),
    ]

    def clear_reports(self):
        for p in self.reports.iterdir():
            p.unlink()

    def test_the_unrecognised_table_reaches_every_parser(self):
        self.assertEqual({r[0] for r in self.UNRECOGNISED}, set(REPORT_NAMES))
        self.assertEqual({r[0] for r in self.RECOGNISED_EMPTY}, set(REPORT_NAMES))
        self.assertEqual(set(wf.SHAPE_CHECKS), set(REPORT_NAMES))

    def test_every_unrecognised_form_is_rc3_named(self):
        for fname, payload in self.UNRECOGNISED:
            with self.subTest(report=fname, payload=payload):
                self.clear_reports()
                self.seed_stale_pivot()
                (self.reports / fname).write_text(payload, encoding="utf-8")
                code, out, err = self.run_raw()
                self.assertEqual(code, 3)
                self.assertNotIn("SUMMARY", out)
                self.assertFalse((self.reports / "effective-verdict.json").exists(),
                                 "the stale pivot survived")
                self.assertEqual(self.degraded_lines(),
                                 [unreadable_line(fname, "UnrecognisedShape")])
                self.assertIn(f"waiver_filter: UNREADABLE report {fname} (", err)

    def test_the_unrecognised_message_carries_no_report_byte(self):
        """stderr prints the exception: its text is static, never the report's."""
        (self.reports / "npm-audit.json").write_text(NPM_ECONNREFUSED, encoding="utf-8")
        code, _, err = self.run_raw()
        self.assertEqual(code, 3)
        self.assertIn("waiver_filter: UNREADABLE report npm-audit.json (", err)
        self.assertNotIn("ECONNREFUSED", err)
        self.assertNotIn("registry.npmjs.org", err)

    def test_every_recognised_empty_form_is_go_without_degraded(self):
        for fname, payload in self.RECOGNISED_EMPTY:
            with self.subTest(report=fname, payload=payload):
                self.clear_reports()
                (self.reports / fname).write_text(payload, encoding="utf-8")
                code, v = self.run_filter()
                self.assertEqual(code, 0)
                self.assertEqual(v["active"], [])
                self.assertIsNone(self.degraded_lines())
                self.assertEqual(v["notes"], [])

    def test_no_lockfile_tool_errors_are_degraded_not_rc3(self):
        """ENOLOCK and ERR_PNPM_AUDIT_NO_LOCKFILE: DEGRADED, rc 0, the line EXACT.

        The line is APPENDED: a reason sca-scan.sh wrote earlier in the run stays.
        """
        for payload, code_name in ((NPM_ENOLOCK, "ENOLOCK"),
                                   (PNPM_NO_LOCKFILE, "ERR_PNPM_AUDIT_NO_LOCKFILE")):
            with self.subTest(code=code_name):
                self.clear_reports()
                (self.reports / ".degraded").write_text("trivy: not installed\n",
                                                        encoding="utf-8")
                write(self.reports / "npm-audit.json", payload)
                code, v = self.run_filter()
                self.assertEqual(code, 0)
                self.assertEqual(v["active"], [])
                self.assertEqual(self.degraded_lines(),
                                 ["trivy: not installed", tool_error_line(code_name)])
                self.assertIn(tool_error_line(code_name), v["notes"])

    def test_another_npm_code_is_rc3_the_pair_of_enolock(self):
        """The same envelope, one word apart: ENOTFOUND is not a missing lockfile."""
        write(self.reports / "npm-audit.json",
              {"error": dict(NPM_ENOLOCK["error"], code="ENOTFOUND")})
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertEqual(self.degraded_lines(),
                         [unreadable_line("npm-audit.json", "UnrecognisedShape")])

    def test_socket_without_alert_list_is_degraded(self):
        for payload in ('{"ok": true}', "{}", '{"ok": false, "message": "no scan"}'):
            with self.subTest(payload=payload):
                self.clear_reports()
                (self.reports / "socket.json").write_text(payload, encoding="utf-8")
                code, v = self.run_filter()
                self.assertEqual(code, 0)
                self.assertEqual(v["active"], [])
                self.assertEqual(self.degraded_lines(), [SOCKET_NO_ALERTS])
                self.assertIn(SOCKET_NO_ALERTS, v["notes"])

    def test_socket_envelope_is_a_closed_list(self):
        """Pilot decision, 2026-10-16 (closing review, T3 option a): the closed list.

        Written out in full, never read from the module. `{"ok": true}` stays
        DEGRADED; a critical under `results`, or under `data.alerts`, is rc 3 —
        both gave rc 0, active 0 before the list, the alert lost.
        """
        self.assertEqual(wf.SOCKET_ENVELOPE_KEYS, frozenset({"ok", "message"}))
        (self.reports / "socket.json").write_text('{"ok": true}', encoding="utf-8")
        code, v = self.run_filter()
        self.assertEqual((code, self.degraded_lines()), (0, [SOCKET_NO_ALERTS]))
        crit = {"package": "evil-pkg", "version": "1.0.0", "severity": "critical",
                "type": "malware"}
        for payload in ({"results": [crit]}, {"ok": True, "data": {"alerts": [crit]}}):
            with self.subTest(payload=payload):
                self.assert_unrecognised("socket.json", payload)

    def test_socket_alerts_not_a_list_is_rc3_the_pair(self):
        (self.reports / "socket.json").write_text('{"alerts": 5}', encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertEqual(self.degraded_lines(),
                         [unreadable_line("socket.json", "UnrecognisedShape")])

    def test_tool_error_beside_vulnerabilities_is_parsed_rc1(self):
        """An `error` key does not hide a `vulnerabilities` object that holds a HIGH."""
        write(self.reports / "npm-audit.json",
              {"error": {"code": "ENOLOCK"}, "vulnerabilities": NPM_V2["vulnerabilities"]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual([f["package"] for f in v["active"]], ["lodash"])
        self.assertIsNone(self.degraded_lines())

    # MIXED FORMS (exec-critic of lot A). The parser reads ONE list or ONE format,
    # so the other one went unread: each payload below gave rc 0 at 3c2e132c.
    SOCKET_LOW = {"package": "meh", "version": "1.0.0", "severity": "low", "type": "unmaintained"}
    SOCKET_HIGH = {"package": "evil-pkg", "version": "1.0.0", "severity": "high",
                   "type": "malware"}
    NPM_V1_LOW = {"1": {"module_name": "meh", "severity": "low", "cves": ["CVE-2000-1"],
                        "findings": [{"version": "1.0.0"}]}}

    def assert_unrecognised(self, fname, payload):
        self.clear_reports()
        self.seed_stale_pivot()
        write(self.reports / fname, payload)
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse((self.reports / "effective-verdict.json").exists(),
                         "the stale pivot survived")
        self.assertEqual(self.degraded_lines(), [unreadable_line(fname, "UnrecognisedShape")])

    def test_socket_alerts_beside_issues_both_non_empty_is_rc3(self):
        """`alerts or issues` reads `alerts` only: the HIGH in `issues` was lost."""
        self.assert_unrecognised("socket.json",
                                 {"alerts": [self.SOCKET_LOW], "issues": [self.SOCKET_HIGH]})

    def test_socket_empty_alerts_beside_issues_is_read_the_pair(self):
        """The pair: an EMPTY `alerts` lets the `or` read `issues`, so the HIGH gates."""
        write(self.reports / "socket.json", {"alerts": [], "issues": [self.SOCKET_HIGH]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual([f["package"] for f in v["active"]], ["evil-pkg"])
        self.assertIsNone(self.degraded_lines())

    def test_npm_vulnerabilities_beside_advisories_is_rc3(self):
        """The parser picks `advisories` by PRESENCE: the HIGH in `vulnerabilities` was lost.

        Both keys present is rc 3 even when both are empty (no producer of the kit
        emits the two together; measured on the stubs and the benches).
        """
        for advisories, vulnerabilities in (({}, NPM_V2["vulnerabilities"]),
                                            (self.NPM_V1_LOW, NPM_V2["vulnerabilities"]),
                                            ({}, {})):
            with self.subTest(advisories=advisories, vulnerabilities=vulnerabilities):
                self.assert_unrecognised("npm-audit.json", {"advisories": advisories,
                                                            "vulnerabilities": vulnerabilities})

    def test_npm_error_beside_the_findings_object_is_rc3(self):
        """npm said the audit failed: an empty object beside that error proves nothing.

        An `error` of ANY value beside the object is rc 3, unless its code is a
        no-lockfile one (the pair below, and the ENOLOCK beside a HIGH above).
        """
        for payload in ({"vulnerabilities": {}, "error": {"code": "ENOTFOUND",
                                                          "summary": "registry down"}},
                        {"advisories": {}, "error": {"code": "E401"}},
                        {"vulnerabilities": {}, "error": {"summary": "", "detail": ""}},
                        {"vulnerabilities": {}, "error": "x"},
                        {"vulnerabilities": {}, "error": None}):
            with self.subTest(payload=payload):
                self.assert_unrecognised("npm-audit.json", payload)

    def test_no_lockfile_error_beside_an_empty_object_is_parsed_the_pair(self):
        """The pair: a no-lockfile code beside an empty object is parsed — GO, no DEGRADED."""
        for payload in ({"vulnerabilities": {}, "error": {"code": "ENOLOCK"}},
                        {"advisories": {}, "error": {"code": "ERR_PNPM_AUDIT_NO_LOCKFILE"}}):
            with self.subTest(payload=payload):
                self.clear_reports()
                write(self.reports / "npm-audit.json", payload)
                code, v = self.run_filter()
                self.assertEqual(code, 0)
                self.assertEqual(v["active"], [])
                self.assertIsNone(self.degraded_lines())

    def test_degraded_report_leaves_the_rc_to_the_others(self):
        """socket DEGRADED beside a readable HIGH: rc 1, and the socket line written."""
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        (self.reports / "socket.json").write_text('{"ok": true}', encoding="utf-8")
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual([f["package"] for f in v["active"]], ["flask"])
        self.assertEqual(self.degraded_lines(), [SOCKET_NO_ALERTS])

    def test_readable_high_plus_unrecognised_report_is_rc3(self):
        write(self.reports / "pip-audit.json", PIP_AUDIT_REPORT)
        (self.reports / "trivy-config.json").write_text("{}", encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse((self.reports / "effective-verdict.json").exists())
        self.assertEqual(self.degraded_lines(),
                         [unreadable_line("trivy-config.json", "UnrecognisedShape")])

    def test_degraded_beside_unreadable_is_rc3_and_names_both(self):
        """rc 3 wins, and the DEGRADED line is still written, BEFORE the rc 3 lines."""
        write(self.reports / "npm-audit.json", NPM_ENOLOCK)
        (self.reports / "pip-audit.json").write_text(PIP_AUDIT_TRUNCATED, encoding="utf-8")
        code, out, _ = self.run_raw()
        self.assertEqual(code, 3)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse((self.reports / "effective-verdict.json").exists())
        self.assertEqual(self.degraded_lines(), [
            tool_error_line("ENOLOCK"),
            unreadable_line("pip-audit.json", "JSONDecodeError"),
        ])


class TestWaiverMatching(Base):
    def setUp(self):
        super().setUp()
        write(self.reports / "npm-audit.json", NPM_V1)

    def test_exact_match_suppresses_and_counts_accepted(self):
        write(self.wfile, {"waivers": [waiver()]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["counters"]["accepted"], 1)
        self.assertEqual(v["active"], [])

    def test_wrong_version_does_not_suppress(self):
        write(self.wfile, {"waivers": [waiver(version="4.17.19")]})
        code, _ = self.run_filter()
        self.assertEqual(code, 1)

    def test_wrong_ecosystem_does_not_suppress(self):
        write(self.wfile, {"waivers": [waiver(ecosystem="maven")]})
        code, _ = self.run_filter()
        self.assertEqual(code, 1)

    def test_advisories_narrowing_realerts_on_other_cve(self):
        write(self.wfile, {"waivers": [waiver(advisories=["CVE-2020-0001"])]})
        code, _ = self.run_filter()
        self.assertEqual(code, 1)

    def test_supply_chain_needs_explicit_class(self):
        write(self.reports / "socket.json", SOCKET_REPORT)
        write(self.wfile, {"waivers": [
            waiver(package="evil-pkg", version="1.0.0"),  # class=known_cve -> must NOT waive
            waiver(),  # clears the lodash CVE finding
        ]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        write(self.wfile, {"waivers": [
            waiver(package="evil-pkg", version="1.0.0", **{"class": "supply_chain"}),
            waiver(),
        ]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)

    def test_pending_review_suppresses_but_counts_separately(self):
        write(self.wfile, {"waivers": [waiver(status="pending_review",
                                              accepted_by="auto (kickoff -s false)")]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["counters"]["pending_review"], 1)
        self.assertEqual(v["counters"]["accepted"], 0)

    def test_overdue_review_counted(self):
        write(self.wfile, {"waivers": [waiver(review_by="2020-01-01")]})
        _, v = self.run_filter()
        self.assertEqual(v["counters"]["overdue_review"], 1)

    def test_gate_level_critical_ignores_high(self):
        code, _ = self.run_filter(gate="critical")
        self.assertEqual(code, 0)


class TestIaCWaiver(Base):
    """IaC (trivy config) findings: ecosystem=iac, package=check id, version=path."""

    def setUp(self):
        super().setUp()
        write(self.reports / "trivy-config.json", TRIVY_REPORT)

    def iac_waiver(self, **kw):
        base = {
            "package": "AVD-DS-0002", "version": "Dockerfile", "ecosystem": "iac",
            "advisories": "*", "class": "iac_misconfig", "severity_at_accept": "high",
            "status": "accepted", "accepted_by": "test", "date": "2026-07-25",
            "reason": "test", "origin": "test",
        }
        base.update(kw)
        return base

    def test_accepted_iac_waiver_suppresses_and_counts(self):
        write(self.wfile, {"waivers": [self.iac_waiver()]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["counters"]["accepted"], 1)
        self.assertEqual(v["active"], [])

    def test_pending_review_iac_waiver_suppresses_but_counts_separately(self):
        write(self.wfile, {"waivers": [self.iac_waiver(status="pending_review",
                                                        accepted_by="auto (kickoff -s false)")]})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["counters"]["pending_review"], 1)
        self.assertEqual(v["counters"]["accepted"], 0)

    def test_wrong_check_id_does_not_suppress(self):
        write(self.wfile, {"waivers": [self.iac_waiver(package="AVD-DS-9999")]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertEqual(len(v["active"]), 1)

    def test_wrong_path_does_not_suppress(self):
        write(self.wfile, {"waivers": [self.iac_waiver(version="infra/Dockerfile")]})
        code, _ = self.run_filter()
        self.assertEqual(code, 1)


class TestTrivyImage(Base):
    """Image CVE (trivy image) findings: ecosystem=image, package=PkgName, version=BASE REF.

    The version slot is the base image reference, so that a base bump — the only
    event that can plausibly fix an OS CVE baked into the base — voids every
    waiver. See parse_trivy_image's docstring for the full rationale.

    These arms cover the MECHANISM only. No project's actual register or CVE list
    belongs here: a waiver register is that project's own audit trail, keyed on
    its own base image.
    """

    def setUp(self):
        super().setUp()
        write(self.reports / "trivy-image.json", TRIVY_IMAGE_REPORT)

    def img_waiver(self, **kw):
        base = {
            "package": "perl-base", "version": BASE_REF, "ecosystem": "image",
            "advisories": ["CVE-2026-13221"], "class": "image_cve",
            "severity_at_accept": "critical", "status": "accepted",
            "accepted_by": "test", "date": "2026-08-05", "review_by": "2026-11-01",
            "reason": "test", "origin": "test",
        }
        base.update(kw)
        return base

    def test_pivot_mapping_is_exact(self):
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        f = next(f for f in v["active"] if f["package"] == "perl-base")
        self.assertEqual((f["ecosystem"], f["package"], f["version"], f["advisory"],
                          f["severity"], f["class"]),
                         ("image", "perl-base", BASE_REF, "CVE-2026-13221",
                          "critical", "image_cve"))

    def test_version_is_base_ref_never_artifact_name(self):
        """myapp/web:ci must appear NOWHERE in the pivot: it survives a base bump."""
        _, v = self.run_filter()
        self.assertTrue(all(f["version"] == BASE_REF for f in v["active"]))
        self.assertNotIn("myapp/web:ci", [f["version"] for f in v["active"]])

    def test_every_vendor_status_is_a_finding_and_pkgname_is_required(self):
        """Status is a vendor fix-state, not a pass/fail verdict — nothing is dropped.

        affected / will_not_fix / fix_deferred / absent / fixed => 5 rows in, and
        exactly the one row with no PkgName out.
        """
        _, v = self.run_filter()
        self.assertEqual(
            sorted(f["advisory"] for f in v["active"]),
            ["CVE-2023-45853", "CVE-2025-69720", "CVE-2026-13221",
             "CVE-2026-41992", "CVE-2026-59873"])
        self.assertNotIn("CVE-2026-00000", [f["advisory"] for f in v["active"]])

    def test_fixed_version_is_carried_for_triage(self):
        _, v = self.run_filter()
        tar = next(f for f in v["active"] if f["package"] == "tar")
        self.assertEqual(tar["fix_version"], "7.5.19")

    def test_missing_base_ref_yields_unknown_and_stays_red(self):
        """No _BaseRef => version 'unknown' => matches no waiver => gate red.

        The failure mode this forbids is the dangerous one: a report reaching the
        filter without a base ref must never fall back to something a waiver
        could match.
        """
        report = {k: val for k, val in TRIVY_IMAGE_REPORT.items() if k != "_BaseRef"}
        write(self.reports / "trivy-image.json", report)
        write(self.wfile, {"waivers": [self.img_waiver()]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)
        self.assertTrue(all(f["version"] == "unknown" for f in v["active"]))
        self.assertEqual(v["counters"]["accepted"], 0)

    def test_exact_base_ref_waiver_suppresses(self):
        """The EFFECTIVE verdict: the register is applied, and what remains is
        what the gate sees."""
        write(self.wfile, {"waivers": [self.img_waiver()]})
        code, v = self.run_filter()
        self.assertEqual(code, 1)  # the other four findings are still active
        self.assertEqual(v["counters"]["accepted"], 1)
        self.assertNotIn("perl-base", [f["package"] for f in v["active"]])

    def test_base_bump_voids_the_waiver(self):
        bumped = self.img_waiver(version="node:24.1.0-bookworm-slim@sha256:0000")
        write(self.wfile, {"waivers": [bumped]})
        _, v = self.run_filter()
        self.assertEqual(v["counters"]["accepted"], 0)
        self.assertIn("perl-base", [f["package"] for f in v["active"]])

    def test_advisories_narrowing_realerts_on_a_future_cve(self):
        """A waived package with a NEW CVE must re-alert — why '*' is banned here."""
        write(self.wfile, {"waivers": [self.img_waiver(advisories=["CVE-2027-00001"])]})
        _, v = self.run_filter()
        self.assertIn("CVE-2026-13221", [f["advisory"] for f in v["active"]])

    def test_pending_review_counted_separately(self):
        write(self.wfile, {"waivers": [self.img_waiver(status="pending_review")]})
        _, v = self.run_filter()
        self.assertEqual(v["counters"]["pending_review"], 1)
        self.assertEqual(v["counters"]["accepted"], 0)

    def test_waiving_everything_greens_the_gate(self):
        """The other half of the effective verdict: nothing left => exit 0. Without
        this arm, an always-red filter would pass every test above."""
        waivers = [self.img_waiver(package=p, advisories=[a]) for p, a in (
            ("perl-base", "CVE-2026-13221"), ("zlib1g", "CVE-2023-45853"),
            ("gzip", "CVE-2026-41992"), ("libtinfo6", "CVE-2025-69720"),
            ("tar", "CVE-2026-59873"))]
        write(self.wfile, {"waivers": waivers})
        code, v = self.run_filter()
        self.assertEqual(code, 0)
        self.assertEqual(v["active"], [])
        self.assertEqual(v["counters"]["accepted"], 5)


class TestImageCvePolicyRouting(unittest.TestCase):
    """An image CVE is NOT treated like an application dependency.

    The mechanism above says what a finding IS; this says what is DONE with it.
    A dependency CVE with a fix ≤ minor is class-2 (auto-fixed by
    security-remediation); an image CVE cannot be: nothing in the repo declares
    the vulnerable package, so there is no version to raise — the fix is a base
    image bump or an upstream release. Hence always_escalate, never
    auto_apply.finding_classes. Asserted against the shipped policy so the
    routing cannot be loosened silently.
    """

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parent / "sca-policy.json"
        cls.policy = json.loads(path.read_text(encoding="utf-8"))

    def test_image_cve_is_always_escalated(self):
        self.assertIn("image_cve", self.policy["always_escalate"])

    def test_image_cve_is_never_auto_applied(self):
        self.assertNotIn("image_cve", self.policy["auto_apply"]["finding_classes"])
        # The control: the class that IS auto-fixable is still there, so this
        # assertion is about image_cve and not about an empty policy.
        self.assertIn("known_cve", self.policy["auto_apply"]["finding_classes"])


if __name__ == "__main__":
    unittest.main()
