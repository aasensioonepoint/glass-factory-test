#!/usr/bin/env python3
"""Security waiver register writer — the ONE writer of `sca-waivers.json`.

Same split as `tasks.py` / `ledger.py` / `specs.py`: a tracked JSON store with
exactly one program allowed to write it, and every other consumer reading it.
`waiver_filter.py` READS this register to compute the effective gate; it never
writes. `sca-watch.sh` is scan-only and never writes it either. This module is
the write end, and it exists because T-00000028 opened a POST path from the
dashboard UI: a server that hand-assembled a JSON entry of its own would be a
SECOND writer of a tracked security artefact, and the two would drift the first
day the schema gained a field (C2 of the approved plan — the server never
writes a first-hand JSON store).

An entry (the shape `waiver_filter.is_waived_by` matches on)::

    {"ecosystem": "npm", "package": "lodash", "version": "4.17.20",
     "advisories": "*", "status": "accepted", "class": "known_cve",
     "reason": "...", "task": "T-00000028", "date": "2026-08-11"}

KEY is `(ecosystem, package, version)` — stated in the register's own header
comment and honoured here: `add` on an existing key REPLACES that entry rather
than appending a second one, because two waivers on one key make "which one
applies" depend on list order, and `waiver_filter` takes the FIRST match.

`status` is a CLOSED vocabulary: `accepted` (pilot decision) | `pending_review`
(auto-flagged, `$kickoff -s false`). Both suppress alerts; they stay separate in
every counter, which is exactly why neither may be invented here.

SUPPLY CHAIN IS NEVER WAIVED BY ACCIDENT (AGENTS.md security gate, spec D7).
`waiver_filter.is_waived_by` refuses to apply a waiver to a supply-chain
finding unless the waiver itself carries `"class": "supply_chain"`. So a caller
that KNOWS it is waiving a supply-chain finding (`--finding-class
supply_chain`) and does not say so on the waiver (`--class supply_chain`) is
writing an entry that will silently never match. That is not a warning here, it
is a REFUSAL: a waiver that cannot ever apply is worse than no waiver, since it
reads in the audit trail as a decision that was taken.

A MALFORMED STORE FAILS LOUDLY. Same posture as the three state stores: a
register that is not an object, or whose `waivers` is not a list, raises rather
than being silently replaced by a fresh one — this file is the audit trail, and
the failure mode to avoid is a scanner going green because the register was
quietly reset.

    python waivers.py add --ecosystem npm --package lodash --version 4.17.20 \
        --status accepted --reason "no fix upstream" --task T-00000028
    python waivers.py status
    python waivers.py status --json

Exit code is 0 unless the arguments are invalid or the store is malformed (2),
mirroring `tasks.py`/`specs.py` — a caller (the dashboard route) can therefore
tell a REFUSAL (rc=2, the operator's fault) from a crash (anything else).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

STORE_REL = Path(".agents") / "security" / "sca-waivers.json"

# Closed vocabularies. The keyword is the data; anything else is rejected.
STATUSES = ("accepted", "pending_review")
# The finding classes this kit's scanners emit (see `waiver_filter.py`'s pivot
# format and `sca-policy.json`). `unknown` is deliberately absent: a waiver
# whose class nobody could name is a waiver nobody can audit.
CLASSES = ("known_cve", "supply_chain", "iac_misconfig", "image_cve")

# Bounds on free text reaching a tracked, committed file. A reason is a
# sentence, not a payload; the register is read by humans in a diff.
MAX_REASON_CHARS = 400
MAX_FIELD_CHARS = 200
MAX_ADVISORIES = 40


class WaiverError(Exception):
    """Operator-facing refusal — rc 2, never a traceback."""


def store_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / STORE_REL


def load(root: str | os.PathLike[str]) -> dict[str, Any]:
    """Read the register. A MISSING file is not an error (a project may not
    have waived anything yet); a malformed one is."""
    path = store_path(root)
    if not path.is_file():
        return {"waivers": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise WaiverError(f"malformed waiver register {path}: {exc}") from exc
    except OSError as exc:
        raise WaiverError(f"unreadable waiver register {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WaiverError(f"malformed waiver register {path}: top level is not an object")
    waivers = data.get("waivers", [])
    if not isinstance(waivers, list):
        raise WaiverError(f"malformed waiver register {path}: 'waivers' is not a list")
    if any(not isinstance(entry, dict) for entry in waivers):
        raise WaiverError(f"malformed waiver register {path}: a waiver entry is not an object")
    data["waivers"] = waivers
    return data


def save(root: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """Atomic replace, same recipe as the state stores: a half-written security
    register is a register that reads as empty, i.e. a silent un-waiving."""
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".waivers-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _clean(label: str, value: str, *, limit: int = MAX_FIELD_CHARS) -> str:
    """One physical line, bounded. Newlines are collapsed rather than rejected
    so a pasted advisory blurb does not become a refusal, but a field can never
    forge a second entry's worth of text in the committed diff."""
    text = " ".join(str(value or "").split())
    if not text:
        raise WaiverError(f"{label} is required and must not be blank")
    if len(text) > limit:
        raise WaiverError(f"{label} is longer than {limit} characters")
    return text


def parse_advisories(raw: str) -> Any:
    """`*` (the whole version) or a comma-separated advisory list. Returned in
    the shape `waiver_filter.is_waived_by` compares against: the literal string
    `"*"`, or a list of ids."""
    text = " ".join(str(raw or "").split())
    if text in ("", "*"):
        return "*"
    items = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    if not items:
        return "*"
    if len(items) > MAX_ADVISORIES:
        raise WaiverError(f"at most {MAX_ADVISORIES} advisories per waiver, got {len(items)}")
    for item in items:
        if len(item) > MAX_FIELD_CHARS:
            raise WaiverError(f"advisory id longer than {MAX_FIELD_CHARS} characters")
    return items


def add_waiver(
    root: str | os.PathLike[str],
    ecosystem: str,
    package: str,
    version: str,
    status: str = "accepted",
    klass: str = "known_cve",
    advisories: str = "*",
    reason: str = "",
    task: str = "",
    finding_class: str = "",
) -> str:
    if status not in STATUSES:
        raise WaiverError(f"unknown status {status!r}; expected one of {', '.join(STATUSES)}")
    if klass not in CLASSES:
        raise WaiverError(f"unknown class {klass!r}; expected one of {', '.join(CLASSES)}")
    if finding_class and finding_class not in CLASSES:
        raise WaiverError(
            f"unknown finding class {finding_class!r}; expected one of {', '.join(CLASSES)}"
        )
    # Spec D7, enforced at the WRITE end rather than discovered at the read end:
    # `waiver_filter.is_waived_by` will never apply a non-supply-chain waiver to
    # a supply-chain finding, so writing that pair produces an entry that reads
    # in the audit trail as a decision taken and behaves as no decision at all.
    if finding_class == "supply_chain" and klass != "supply_chain":
        raise WaiverError(
            "a supply-chain finding is waivable only by an explicit "
            "`--class supply_chain` waiver (spec D7): the entry you asked for "
            "would never match the finding it claims to waive"
        )

    ecosystem = _clean("ecosystem", ecosystem)
    package = _clean("package", package)
    version = _clean("version", version)
    advisory_value = parse_advisories(advisories)
    reason_text = " ".join(str(reason or "").split())
    if len(reason_text) > MAX_REASON_CHARS:
        raise WaiverError(f"reason is longer than {MAX_REASON_CHARS} characters")
    task_text = " ".join(str(task or "").split())
    if len(task_text) > MAX_FIELD_CHARS:
        raise WaiverError(f"task is longer than {MAX_FIELD_CHARS} characters")

    entry = {
        "ecosystem": ecosystem,
        "package": package,
        "version": version,
        "advisories": advisory_value,
        "status": status,
        "class": klass,
        "reason": reason_text,
        "task": task_text,
        "date": date.today().isoformat(),
    }

    data = load(root)
    key = (ecosystem, package, version)
    replaced = False
    waivers = []
    for existing in data["waivers"]:
        if (existing.get("ecosystem"), existing.get("package"),
                existing.get("version")) == key:
            replaced = True
            continue
        waivers.append(existing)
    waivers.append(entry)
    data["waivers"] = waivers
    save(root, data)
    verb = "replaced" if replaced else "added"
    return f"WAIVER: {verb} {ecosystem}/{package}@{version} ({status}, {klass})"


def render_status(root: str | os.PathLike[str]) -> str:
    waivers = load(root)["waivers"]
    if not waivers:
        return "WAIVERS: 0 entries"
    counts: dict[str, int] = {}
    for entry in waivers:
        state = str(entry.get("status") or "accepted")
        counts[state] = counts.get(state, 0) + 1
    head = "WAIVERS: {} entries ({})".format(
        len(waivers),
        ", ".join(f"{name}={counts[name]}" for name in sorted(counts)),
    )
    lines = [head]
    for entry in waivers:
        advisories = entry.get("advisories", "*")
        shown = advisories if isinstance(advisories, str) else ",".join(advisories)
        lines.append(
            "- {}/{}@{} [{}] class={} advisories={} task={} date={}".format(
                entry.get("ecosystem", "?"), entry.get("package", "?"),
                entry.get("version", "?"), entry.get("status", "?"),
                entry.get("class", "?"), shown,
                entry.get("task") or "-", entry.get("date") or "-",
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Security waiver register writer — the one writer of "
                    ".agents/security/sca-waivers.json."
    )
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    sub = ap.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="add or replace one waiver (key: ecosystem+package+version)")
    p_add.add_argument("--ecosystem", required=True)
    p_add.add_argument("--package", required=True)
    p_add.add_argument("--version", required=True, help="the affected version, or '*' for every version")
    p_add.add_argument("--status", default="accepted", choices=list(STATUSES))
    p_add.add_argument("--class", dest="klass", default="known_cve", choices=list(CLASSES),
                       help="the waiver's own class; supply_chain must be stated explicitly")
    p_add.add_argument("--advisories", default="*",
                       help="'*' waives the whole version, or a comma-separated advisory list")
    p_add.add_argument("--reason", default="")
    p_add.add_argument("--task", default="", help="the task this decision was taken under")
    p_add.add_argument("--finding-class", dest="finding_class", default="",
                       help="the class of the finding being waived, when known; "
                            "supply_chain here without --class supply_chain is refused (spec D7)")

    p_status = sub.add_parser("status", help="print the register, one line per waiver")
    p_status.add_argument("--json", action="store_true", help="raw entries as JSON")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            print(add_waiver(
                args.root, args.ecosystem, args.package, args.version,
                status=args.status, klass=args.klass, advisories=args.advisories,
                reason=args.reason, task=args.task, finding_class=args.finding_class,
            ))
        elif args.cmd == "status":
            if args.json:
                print(json.dumps(load(args.root)["waivers"], indent=2, ensure_ascii=False))
            else:
                print(render_status(args.root))
        else:
            ap.print_help()
    except WaiverError as exc:
        print(f"waivers.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
