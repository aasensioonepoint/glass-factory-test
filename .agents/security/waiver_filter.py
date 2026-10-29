#!/usr/bin/env python3
"""Normalize SCA scanner reports, apply the waiver register, compute the effective gate.

Reads JSON reports in --reports-dir (npm-audit.json, dependency-check-report.json,
socket.json, trivy-config.json, trivy-image.json, pip-audit.json), normalizes findings to a pivot format,
filters them against the waiver register, writes <reports-dir>/effective-verdict.json
and prints one SUMMARY line. stdlib only.

Exit codes: 0 = no ACTIVE finding at/above --gate-level after waiver filtering
            1 = effective gate hit
            2 = usage error (argparse: unknown --gate-level, missing argument)
            3 = a REPORT present in --reports-dir is unreadable, empty, truncated,
                decodes to a shape its parser raises on (`null`, a number where
                a list is expected, an unhashable name), or decodes to a READABLE
                form that SHAPE_CHECKS does not recognise (UnrecognisedShape:
                pip-audit `{}`, trivy `{"Results": {}}`, an npm error envelope
                other than the two named below, or a MIXED form whose parser
                would leave a list unread: npm `vulnerabilities` beside
                `advisories`, socket `alerts` and `issues` both non-empty, npm
                `error` beside its findings object with another code, a socket
                object with neither list and a key outside SOCKET_ENVELOPE_KEYS):
                NO pivot (a stale one is removed), NO SUMMARY line, one line per
                such report appended to <reports-dir>/.degraded, the reason on
                stderr. Fail-closed: a truncated report can hide a HIGH, so no
                verdict is computed from what remains (decision S-01M4XXZ7FMDJ3ZQFDVF2FC9WJZ,
                which named an unreadable or truncated report; its extension to a
                readable unrecognised form is ASSUMED by plan T-01M4Z33N54TX0Q7VHBZATFNR4X).
                The waiver REGISTER unreadable or absent is NOT this case: it stays
                a note, the strictest reading (nothing is waived).
DEGRADED, never an rc of its own — exactly two forms, each one .degraded line,
one pivot note and zero findings, the rc left to the other reports:
  npm-audit.json  an object with neither `vulnerabilities` nor `advisories` whose
                  `error` object has `code` EXACTLY "ENOLOCK" or
                  "ERR_PNPM_AUDIT_NO_LOCKFILE" (no lockfile: nothing was audited);
  socket.json     an object carrying neither `alerts` nor `issues` whose keys ALL
                  belong to the closed list SOCKET_ENVELOPE_KEYS (`ok`, `message`):
                  the supply-chain layer was not read. Any other key is rc 3
                  (pilot decision, 2026-10-16): the real shape of
                  `socket scan create --json` is NOT measured, so an unknown form is
                  NO-GO until it is.
Pivot finding: {ecosystem, package, version, advisory, severity, class, fix_version, direct}
Maven packages are named group:artifact. Waiver semantics: see sca-waivers.json header.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
PURL_ECO = {"npm": "npm", "maven": "maven", "gradle": "gradle", "swift": "swift", "cocoapods": "swift"}
ADVISORY_RE = re.compile(r"(GHSA-[\w-]+|CVE-\d{4}-\d+)")


def norm_sev(s):
    s = (s or "").lower()
    if s == "moderate":
        return "medium"
    return s if s in SEV_ORDER else "low"


def load_json(path, notes, strict=False):
    """Read one JSON file.

    strict=False (the waiver REGISTER): a read or parse failure becomes a note and
    None — nothing is waived, which is the strictest outcome for the gate.
    strict=True (a scanner REPORT): the OSError/ValueError is RE-RAISED for main()
    to fail closed (rc 3). A report used to take the register's path: measured, a
    pip-audit.json truncated in the middle of a HIGH gave `SUMMARY active=0` and
    rc 0, i.e. a GO built on a report nobody could read.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if strict:
            raise
        notes.append(f"{Path(path).name}: unreadable/malformed, skipped ({exc})")
        return None


def fail_closed_unreadable(reports, unreadable):
    """The rc 3 path: no pivot, no SUMMARY, the reports NAMED in .degraded and stderr.

    The stale pivot is removed so that no reader (sca-scan.sh, sca-watch.sh, the
    dashboard) takes a previous run's verdict for this one. The .degraded line
    carries the report's name — the literal of main()'s `parsers` table — and the
    exception CLASS only: the message can carry a filesystem path. It is APPENDED,
    never written over, because sca-scan.sh has already recorded its own reasons
    in that file for this run and adds its fail-closed line after this one.
    """
    (reports / "effective-verdict.json").unlink(missing_ok=True)
    with open(reports / ".degraded", "a", encoding="utf-8") as fh:
        for fname, exc in unreadable:
            fh.write(f"waiver_filter: report {fname} unreadable/malformed "
                     f"({type(exc).__name__}) — no effective verdict\n")
    for fname, exc in unreadable:
        print(f"waiver_filter: UNREADABLE report {fname} ({exc}) — no effective verdict "
              f"(fail-closed)", file=sys.stderr)
    return 3


def finding(ecosystem, package, version, advisory, severity, klass, fix_version=None, direct=None):
    return {"ecosystem": ecosystem, "package": package, "version": version or "unknown",
            "advisory": advisory or "unspecified", "severity": severity, "class": klass,
            "fix_version": fix_version, "direct": direct}


def lock_versions(root):
    """installed-version map from package-lock.json (v2/v3 'packages' or v1 'dependencies')."""
    out = {}
    lock = None
    p = Path(root) / "package-lock.json"
    if p.is_file():
        try:
            lock = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return out
    if not lock:
        return out
    for key, meta in (lock.get("packages") or {}).items():
        if key.startswith("node_modules/") and "/node_modules/" not in key[len("node_modules/"):]:
            out.setdefault(key[len("node_modules/"):], meta.get("version"))
    for name, meta in (lock.get("dependencies") or {}).items():
        out.setdefault(name, meta.get("version"))
    return out


def parse_npm_audit(data, root):
    findings = []
    if "advisories" in data:  # npm<7 / pnpm format
        for adv in data["advisories"].values():
            cves = adv.get("cves") or []
            advisory = cves[0] if cves else (adv.get("github_advisory_id") or f"NPM-{adv.get('id')}")
            for hit in adv.get("findings") or [{}]:
                findings.append(finding("npm", adv.get("module_name"), hit.get("version"),
                                        advisory, norm_sev(adv.get("severity")), "known_cve",
                                        adv.get("patched_versions")))
    elif "vulnerabilities" in data:  # npm>=7 format
        versions = lock_versions(root)
        for name, vul in data["vulnerabilities"].items():
            advisory = None
            for via in vul.get("via") or []:
                if isinstance(via, dict):
                    m = ADVISORY_RE.search(via.get("url") or "")
                    advisory = m.group(1) if m else via.get("title")
                    break
            findings.append(finding("npm", name, versions.get(name), advisory,
                                    norm_sev(vul.get("severity")), "known_cve",
                                    str(vul.get("fixAvailable")), bool(vul.get("isDirect"))))
    return findings


def parse_dc(data):
    findings = []
    for dep in data.get("dependencies") or []:
        vulns = dep.get("vulnerabilities") or []
        if not vulns:
            continue
        eco, pkg, ver = "unknown", dep.get("fileName", "unknown"), "unknown"
        for p in dep.get("packages") or []:
            m = re.match(r"pkg:([^/]+)/(.+)@([^@]+)$", p.get("id") or "")
            if m:
                eco = PURL_ECO.get(m.group(1), m.group(1))
                pkg, ver = m.group(2), m.group(3)
                if eco == "maven":
                    pkg = pkg.replace("/", ":", 1)
                break
        for v in vulns:
            findings.append(finding(eco, pkg, ver, v.get("name"),
                                    norm_sev(v.get("severity")), "known_cve"))
    return findings


def parse_socket(data):
    findings = []
    rows = data if isinstance(data, list) else (data.get("alerts") or data.get("issues") or [])
    for a in rows:
        if not isinstance(a, dict):
            continue
        pkg = a.get("package") or a.get("pkg") or a.get("name")
        if not pkg:
            continue
        findings.append(finding("npm", pkg, str(a.get("version", "unknown")),
                                a.get("type") or a.get("key") or "supply-chain",
                                norm_sev(a.get("severity", "high")), "supply_chain"))
    return findings


def parse_trivy(data):
    """trivy config --format json (IaC misconfiguration: Dockerfile/Terraform/K8s/Helm).

    Pivot mapping (no dependency version exists for an infra misconfig):
    package=check id (AVDID, falling back to ID), version=Target (the scanned
    file/path), advisory=AVDID, class=iac_misconfig. A row is a finding unless
    its Status is explicitly "PASS" or an exception (skipped, ignored, ...):
    Status == "FAIL" is a finding, and so is a missing/absent Status field
    (fail-safe: never silently drop a misconfiguration just because a given
    trivy version omitted the field) — PASS and any other explicit status are
    not.
    """
    findings = []
    for result in data.get("Results") or []:
        target = result.get("Target") or "unknown"
        for m in result.get("Misconfigurations") or []:
            if m.get("Status") not in (None, "FAIL"):
                continue
            check_id = m.get("AVDID") or m.get("ID") or "unknown"
            findings.append(finding("iac", check_id, target, m.get("AVDID") or m.get("ID"),
                                    norm_sev(m.get("Severity")), "iac_misconfig"))
    return findings


def parse_trivy_image(data):
    """trivy image --format json (OS packages + language packages baked in an image).

    Pivot mapping: ecosystem="image", package=PkgName, version=<the EXACT base
    image reference of the scanned image, tag AND digest>, advisory=
    VulnerabilityID, class="image_cve".

    An image CVE is NOT an application dependency, which is why it gets its own
    class rather than reusing known_cve: nothing in this repo declares the
    vulnerable package, so the fix is a BASE IMAGE bump (a new FROM digest) or an
    upstream release we do not own — never a manifest version-bump. Auto-fixing
    is not merely undesirable, it is impossible: there is no version here to
    raise. Hence `image_cve` sits in `always_escalate` in sca-policy.json and
    never in `auto_apply.finding_classes`.

    WHY THE VERSION SLOT CARRIES THE BASE REF, and neither the package's own
    installed version nor ArtifactName. A waiver is keyed on
    (ecosystem, package, version) and must be VOIDED by the event that can
    plausibly fix the finding. For a CVE in an OS package baked into a base
    image, that event is a base-image bump — not a bump of the package itself
    (we do not control it) and certainly not a rebuild: ArtifactName is the local
    build tag ("myapp/web:ci"), identical across every rebuild and across every
    base, so a waiver keyed on it would survive a base bump and blind the
    register forever. Keying on the base ref makes "we changed base" mean "every
    accepted finding is re-examined", which is the whole point of the register.
    For the same reason `advisories: "*"` is a convention violation on this
    class: an image carries dozens of packages, and a future CVE on an
    already-waived package MUST re-alert.

    PRODUCER CONTRACT. The base ref is NOT discoverable from the report itself:
    it comes from a `_BaseRef` key that the image-scan step injects before
    handing the report over, extracted from the FROM of the FINAL stage of the
    scanned Dockerfile. The kit's own sca-scan.sh does NOT produce
    trivy-image.json (it runs `trivy config`, not `trivy image`); a project that
    adds an image scan writes the report and injects the key, and this parser
    then applies the register to it. A MISSING `_BaseRef` yields version
    "unknown", which matches no waiver, so every finding stays ACTIVE and the
    gate goes red — loud, never a silent green.

    NO Status filtering here, and that is the opposite of parse_trivy() above on
    purpose. In a trivy CONFIG report, Status is a check verdict (PASS means "no
    misconfiguration"). In a trivy VULNERABILITY report, Status is the vendor's
    fix state ("affected", "fixed", "will_not_fix", "fix_deferred",
    "end_of_life", "unknown") — every row is a vulnerability PRESENT in the
    scanned image whatever its label, and "fixed" means "upstream published a fix
    the image has not picked up", i.e. the most actionable finding of all. Rows
    with no Status field at all are findings too (same fail-safe reflex).
    """
    base_ref = data.get("_BaseRef") or "unknown"
    findings = []
    for result in data.get("Results") or []:
        for v in result.get("Vulnerabilities") or []:
            pkg = v.get("PkgName")
            if not pkg:
                continue
            findings.append(finding("image", pkg, base_ref, v.get("VulnerabilityID"),
                                    norm_sev(v.get("Severity")), "image_cve",
                                    v.get("FixedVersion")))
    return findings


def parse_pip_audit(data):
    """pip-audit --no-deps -r <requirements*.txt> -f json (PyPI dependency CVEs, T-00000292).

    pip-audit's JSON is {"dependencies": [{"name", "version", "vulns": [
    {"id", "fix_versions", "aliases", "description", ...}]}], "fixes": [...]}
    (older builds emit the dependencies LIST at top level — both are accepted).
    Pivot: ecosystem="pypi", package=name, version=the pinned version audited,
    advisory=vuln id, class=known_cve, fix_version=first fix_versions entry.

    SEVERITY IS FAIL-SAFE. pip-audit's baseline schema carries no CVSS severity
    (PYSEC/OSV rows frequently have none), so a per-vuln "severity" string is read
    when present and an ABSENT/non-string severity defaults to "high": a KNOWN
    vulnerability with unknown severity GATES rather than slips through — the same
    reflex parse_trivy()/parse_trivy_image() apply to a missing Status. A real
    finding genuinely below the gate can be waived; a silent GO on a real CVE
    cannot be undone.
    """
    findings = []
    deps = data if isinstance(data, list) else (data.get("dependencies") or [])
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        pkg = dep.get("name")
        if not pkg:
            continue
        ver = str(dep.get("version") or "unknown")
        for v in dep.get("vulns") or []:
            if not isinstance(v, dict):
                continue
            fixes = v.get("fix_versions") or []
            fix_version = fixes[0] if isinstance(fixes, list) and fixes else None
            sev = v.get("severity")
            sev = sev if isinstance(sev, str) else None
            findings.append(finding("pypi", pkg, ver, v.get("id"),
                                    norm_sev(sev or "high"), "known_cve", fix_version))
    return findings


class UnrecognisedShape(ValueError):
    """A report that DECODES to a form no entry of SHAPE_CHECKS recognises.

    A ValueError, so main() sends it down the rc 3 path of a truncated report.
    Before this rule, a readable form that no parser recognised gave zero findings,
    and zero findings read as GO. Measured with an empty register: pip-audit `{}`,
    trivy `{"SchemaVersion": 2, "Results": {}}`, and npm's "registry unreachable"
    envelope without a `code` each gave rc 0. The MIXED forms are refused too. At
    3c2e132c, socket `alerts` (low) beside `issues` (HIGH), npm `advisories: {}`
    beside `vulnerabilities` (HIGH), and npm ENOTFOUND beside `vulnerabilities: {}`
    each gave rc 0. The message is static text, so no byte of the report reaches
    stderr through it.
    """


# The closed list of npm/pnpm codes meaning "no lockfile, nothing was audited".
# Measured: npm without a lock answers ENOLOCK, and pnpm 10 answers
# ERR_PNPM_AUDIT_NO_LOCKFILE. Every other envelope stays rc 3: ENOTFOUND, E401,
# ETIMEDOUT, a non-object `error`, and a `code` that is absent.
NPM_NO_LOCKFILE_CODES = ("ENOLOCK", "ERR_PNPM_AUDIT_NO_LOCKFILE")
SOCKET_NO_ALERTS_LINE = ("waiver_filter: report socket.json carries no alert list — "
                         "supply-chain layer NOT read, coverage DEGRADED")
# The CLOSED list of keys a socket object without `alerts`/`issues` may carry and
# still read DEGRADED (pilot decision, 2026-10-16, option a of the closing review).
# Measured before it: `{"results": [critical]}` and `{"ok": true, "data": {"alerts":
# [critical]}}` both gave rc 0, active 0 — the alert was lost. The real output of
# `socket scan create --json` is NOT measured; the kit's stubs emit `{"ok": true}`.
SOCKET_ENVELOPE_KEYS = frozenset({"ok", "message"})


def _typed(data: dict, key: str, kind: type) -> bool:
    """A key that is PRESENT must carry its type; an absent key passes."""
    return key not in data or isinstance(data[key], kind)


def _shape_npm(data) -> Optional[str]:
    if not isinstance(data, dict):
        raise UnrecognisedShape("npm audit report is not a JSON object")
    err = data.get("error")
    code = err.get("code") if isinstance(err, dict) else None
    if "vulnerabilities" not in data and "advisories" not in data:
        if code in NPM_NO_LOCKFILE_CODES:
            return (f"waiver_filter: report npm-audit.json is a tool error ({code}) — "
                    "npm audit NOT performed, coverage DEGRADED")
        raise UnrecognisedShape("no `vulnerabilities` or `advisories` object, "
                                "and not a no-lockfile tool error")
    if not (_typed(data, "vulnerabilities", dict) and _typed(data, "advisories", dict)):
        raise UnrecognisedShape("`vulnerabilities` or `advisories` present but not an object")
    # MIXED FORM: parse_npm_audit reads ONE format, picked by the PRESENCE of
    # `advisories`. Measured at 3c2e132c: `{"advisories": {}, "vulnerabilities":
    # {HIGH}}` gave rc 0. Both keys present is rc 3, empty or not.
    if "vulnerabilities" in data and "advisories" in data:
        raise UnrecognisedShape("both `vulnerabilities` and `advisories`: "
                                "the parser reads one of them only")
    # An `error` BESIDE the findings object says the audit failed, so an empty
    # object proves nothing. Measured at 3c2e132c: ENOTFOUND beside
    # `"vulnerabilities": {}` gave rc 0 with no DEGRADED line. A no-lockfile code
    # stays parsed: the plan pins ENOLOCK beside a HIGH at rc 1.
    if "error" in data and code not in NPM_NO_LOCKFILE_CODES:
        raise UnrecognisedShape("an `error` beside the findings object, "
                                "and not a no-lockfile tool error")
    return None


def _shape_dc(data) -> Optional[str]:
    if isinstance(data, dict) and isinstance(data.get("dependencies"), list):
        return None
    raise UnrecognisedShape("dependency-check report has no `dependencies` list")


def _shape_socket(data) -> Optional[str]:
    if isinstance(data, list):
        return None
    if not isinstance(data, dict):
        raise UnrecognisedShape("socket report is neither a list nor a JSON object")
    if "alerts" not in data and "issues" not in data:
        # `{}` passes: the empty set is a subset of the closed list.
        if set(data) <= SOCKET_ENVELOPE_KEYS:
            return SOCKET_NO_ALERTS_LINE
        raise UnrecognisedShape("socket report has no `alerts` or `issues` list "
                                "and a key outside the envelope list")
    if not (_typed(data, "alerts", list) and _typed(data, "issues", list)):
        raise UnrecognisedShape("`alerts` or `issues` present but not a list")
    # MIXED FORM: parse_socket reads `alerts or issues`, so a NON-EMPTY `alerts`
    # hides `issues`. Measured at 3c2e132c: a HIGH in `issues` beside a low alert
    # gave rc 0. An empty list beside the other one is read through the `or`.
    if data.get("alerts") and data.get("issues"):
        raise UnrecognisedShape("`alerts` and `issues` both non-empty: "
                                "the parser reads one of them only")
    return None


def _shape_trivy(data) -> Optional[str]:
    """trivy config and trivy image share this check.

    `Results` must be a list when it is present. When it is absent, the report must
    carry an integer `SchemaVersion` (not a bool): that is trivy's envelope when it
    found nothing to scan.
    """
    if not isinstance(data, dict):
        raise UnrecognisedShape("trivy report is not a JSON object")
    if "Results" in data:
        if isinstance(data["Results"], list):
            return None
        raise UnrecognisedShape("`Results` present but not a list")
    version = data.get("SchemaVersion")
    if isinstance(version, int) and not isinstance(version, bool):
        return None
    raise UnrecognisedShape("neither a `Results` list nor an integer `SchemaVersion`")


def _shape_pip(data) -> Optional[str]:
    if isinstance(data, list):
        return None
    if isinstance(data, dict) and isinstance(data.get("dependencies"), list):
        return None
    raise UnrecognisedShape("pip-audit report is neither a list nor an object "
                            "with a `dependencies` list")


# THE CLOSED TABLE, keyed by the same literals as main()'s `parsers`. Each check
# runs BEFORE its parser and answers in one of three ways:
#   - None: the report is recognised, so it is parsed;
#   - a DEGRADED line: one of the two named forms, with zero findings;
#   - UnrecognisedShape: rc 3.
# The check judges the ENVELOPE only; see the BOUND in main().
SHAPE_CHECKS = {"npm-audit.json": _shape_npm,
                "dependency-check-report.json": _shape_dc,
                "socket.json": _shape_socket,
                "trivy-config.json": _shape_trivy,
                "trivy-image.json": _shape_trivy,
                "pip-audit.json": _shape_pip}


def is_waived_by(f, w):
    if w.get("ecosystem") != f["ecosystem"] or w.get("package") != f["package"]:
        return False
    if w.get("version") not in ("*", f["version"]):
        return False
    adv = w.get("advisories", "*")
    if adv != "*" and f["advisory"] not in adv:
        return False
    if f["class"] == "supply_chain" and w.get("class") != "supply_chain":
        return False  # supply-chain waivers must be explicit (AGENTS.md § security gate)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports-dir", required=True)
    ap.add_argument("--waivers", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--gate-level", choices=("high", "critical"), default="high")
    args = ap.parse_args(argv)

    reports = Path(args.reports_dir)
    notes = []
    parsers = {"npm-audit.json": lambda d: parse_npm_audit(d, args.root),
               "dependency-check-report.json": parse_dc,
               "socket.json": parse_socket,
               "trivy-config.json": parse_trivy,
               "trivy-image.json": parse_trivy_image,
               "pip-audit.json": parse_pip_audit}
    unreadable, degraded = [], []
    seen, deduped = set(), []
    for fname, parser in parsers.items():
        path = reports / fname
        if not path.is_file():
            continue
        # READ, RECOGNISE, PARSE AND KEY in one guarded step. The guard is a BOUND,
        # not a list of classes. A report that decodes but has a shape its parser
        # does not expect raises AFTER json.loads. Measured: `null` in
        # pip-audit.json is an AttributeError, `{"dependencies": 5}` a TypeError,
        # and a package name that is a list makes an unhashable key in the dedup
        # below. Caught only as (OSError, ValueError), each became a traceback,
        # rc 1, no report named, and sca-watch read it as a CONFIGURATION fault.
        # Any Exception here is this report's: rc 3, named.
        # RECOGNISED BEFORE PARSED: a READABLE form that raises nothing used to give
        # zero findings, i.e. a GO. SHAPE_CHECKS now answers first, and its
        # UnrecognisedShape reaches the same rc 3 as a truncation.
        # BOUND: the table judges the ENVELOPE only. It also refuses the MIXED forms
        # whose parser would leave a list unread. That means npm with BOTH
        # `vulnerabilities` and `advisories`, which is rc 3 even when both are empty
        # because the parser picks one by presence. It means socket with `alerts` AND
        # `issues` both non-empty; an empty one is read through the `or`. And it means
        # npm with an `error` beside its findings object, an `error` of ANY value,
        # unless its code is a no-lockfile one. That no-lockfile `error` beside an
        # object is parsed: a HIGH gives rc 1, an empty object rc 0 with no DEGRADED
        # line. Inside a recognised envelope, socket and pip-audit still skip a row
        # that is not an object, and a severity that is absent still reads "low"
        # (norm_sev) in npm, dc and trivy.
        try:
            data = load_json(path, notes, strict=True)
            line = SHAPE_CHECKS[fname](data)
            if line is not None:
                degraded.append(line)
                continue
            for f in parser(data):
                key = (f["ecosystem"], f["package"], f["version"], f["advisory"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(f)
        except Exception as exc:  # noqa: BLE001 — a bound on purpose, see above
            unreadable.append((fname, exc))
    # The DEGRADED lines are written BEFORE the rc 3 decision, so a run that ends
    # unreadable still says which audit was not performed. They are APPENDED,
    # because sca-scan.sh has already recorded its own reasons for this run.
    if degraded:
        with open(reports / ".degraded", "a", encoding="utf-8") as fh:
            for line in degraded:
                fh.write(line + "\n")
        notes.extend(degraded)
    # ONE unreadable report ends the run, even when another report holds a
    # readable HIGH: a verdict computed from the rest would be partial, and the
    # caller could not tell it from a complete one. Decided before the register
    # is read, so the register's own state cannot change this outcome.
    if unreadable:
        return fail_closed_unreadable(reports, unreadable)

    wdata = load_json(args.waivers, notes) or {}
    waivers = [w for w in wdata.get("waivers", []) if isinstance(w, dict)]

    active, accepted, pending = [], [], []
    matched = []
    for f in deduped:
        w = next((w for w in waivers if is_waived_by(f, w)), None)
        if w is None:
            active.append(f)
        else:
            matched.append(w)
            (pending if w.get("status") == "pending_review" else accepted).append(
                dict(f, waiver_status=w.get("status", "accepted")))

    today = date.today().isoformat()
    overdue = len({id(w) for w in matched
                   if w.get("review_by") and w["review_by"] < today})
    threshold = SEV_ORDER[args.gate_level]
    gate_hit = any(SEV_ORDER[f["severity"]] >= threshold for f in active)

    verdict = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_level": args.gate_level,
        "active": active,
        "waived_accepted": accepted,
        "waived_pending": pending,
        "counters": {
            "active_at_gate": sum(1 for f in active if SEV_ORDER[f["severity"]] >= threshold),
            "accepted": len(accepted),
            "pending_review": len(pending),
            "overdue_review": overdue,
        },
        "notes": notes,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "effective-verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8")
    print(f"SUMMARY active={verdict['counters']['active_at_gate']} "
          f"accepted={len(accepted)} pending={len(pending)} overdue={overdue}")
    return 1 if gate_hit else 0


if __name__ == "__main__":
    sys.exit(main())
