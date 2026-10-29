"""Tests for waivers.py — the ONE writer of the security waiver register
(T-00000028).

Style: explicit-path module load, matching `test_dashboard.py` /
`test_events.py`. Every test writes into a `tmp_path` root, never the real
`.agents/security/sca-waivers.json` — this register is a committed audit trail,
and a test suite that could append to it would be the second writer this module
exists to prevent.

The last section is the one that matters most: it runs entries written HERE
through `waiver_filter.is_waived_by`, the READER that decides the effective
security gate. A register whose writer and reader agree only by inspection is a
register that will disagree the first day either side gains a field.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import sys

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


waivers = _load("waivers", HERE / "waivers.py")
waiver_filter = _load("waiver_filter", HERE.parent / "security" / "waiver_filter.py")


def _register(root: Path) -> dict:
    return json.loads((root / ".agents" / "security" / "sca-waivers.json").read_text(encoding="utf-8"))


def _entries(root: Path) -> list[dict]:
    return _register(root)["waivers"]


def _add(root: Path, **kwargs) -> str:
    payload = {"ecosystem": "npm", "package": "lodash", "version": "4.17.20"}
    payload.update(kwargs)
    return waivers.add_waiver(root, **payload)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def test_an_absent_register_is_created_rather_than_being_an_error(tmp_path):
    """A project that has waived nothing yet has no register, and that is a
    normal state — not a malformed one."""
    message = _add(tmp_path, reason="pas de correctif amont", task="T-00000028")
    assert "added" in message
    entry = _entries(tmp_path)[0]
    assert entry["ecosystem"] == "npm"
    assert entry["package"] == "lodash"
    assert entry["version"] == "4.17.20"
    assert entry["status"] == "accepted"
    assert entry["class"] == "known_cve"
    assert entry["advisories"] == "*"
    assert entry["task"] == "T-00000028"
    assert entry["date"]


def test_the_key_is_ecosystem_package_version_so_a_second_add_replaces(tmp_path):
    """Stated in the register's own header and honoured here. Two waivers on one
    key would make "which one applies" depend on list order, and
    `waiver_filter` takes the FIRST match — i.e. a pilot's second decision would
    silently lose to his first."""
    _add(tmp_path, status="accepted", reason="premiere decision")
    message = _add(tmp_path, status="pending_review", reason="revue demandee")
    assert "replaced" in message
    entries = _entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["status"] == "pending_review"
    assert entries[0]["reason"] == "revue demandee"


def test_a_different_version_is_a_different_waiver(tmp_path):
    """A version bump voids a waiver — that is the register's whole safety
    property, so two versions must never collapse into one entry."""
    _add(tmp_path, version="4.17.20")
    _add(tmp_path, version="4.17.21")
    assert len(_entries(tmp_path)) == 2


def test_the_register_comment_header_survives_a_write(tmp_path):
    """The `_comment` key documents the whole waiver vocabulary. A writer that
    dropped it would leave the next reader of this file with no semantics at
    all."""
    path = tmp_path / ".agents" / "security" / "sca-waivers.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"_comment": "les regles du registre", "waivers": []}),
                    encoding="utf-8")
    _add(tmp_path)
    assert _register(tmp_path)["_comment"] == "les regles du registre"


def test_an_existing_entry_is_preserved_when_another_is_added(tmp_path):
    _add(tmp_path, package="lodash")
    _add(tmp_path, package="minimist")
    assert sorted(e["package"] for e in _entries(tmp_path)) == ["lodash", "minimist"]


# ---------------------------------------------------------------------------
# Closed vocabularies and bounds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["approved", "waived", "ok", "", "ACCEPTED"])
def test_an_unknown_status_is_refused(tmp_path, status):
    """`accepted` and `pending_review` stay separate in every counter and
    digest; a third value invented at a call site would be counted as neither."""
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, status=status)


@pytest.mark.parametrize("klass", ["cve", "unknown", "", "supply-chain"])
def test_an_unknown_class_is_refused(tmp_path, klass):
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, klass=klass)


@pytest.mark.parametrize("field", ["ecosystem", "package", "version"])
def test_a_blank_key_field_is_refused(tmp_path, field):
    """A blank key component writes an entry that matches nothing — a decision
    recorded in the audit trail that can never apply."""
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, **{field: "   "})


def test_a_refusal_leaves_no_register_behind(tmp_path):
    """Validation happens BEFORE the store is touched. A refusal that had
    created an empty register would look like "this project waived nothing"
    rather than "nothing was written"."""
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, status="nope")
    assert not (tmp_path / ".agents" / "security" / "sca-waivers.json").exists()


def test_free_text_is_collapsed_to_one_line_and_bounded(tmp_path):
    """This file is read by humans in a git diff. A multi-line reason would let
    one entry span what looks like several."""
    _add(tmp_path, reason="ligne un\nligne deux\r\tligne trois")
    assert _entries(tmp_path)[0]["reason"] == "ligne un ligne deux ligne trois"
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, reason="z" * (waivers.MAX_REASON_CHARS + 1))


def test_advisories_default_to_the_whole_version(tmp_path):
    for value in ("", "*", "   "):
        _add(tmp_path, advisories=value)
        assert _entries(tmp_path)[0]["advisories"] == "*"


def test_advisories_can_narrow_to_a_list(tmp_path):
    _add(tmp_path, advisories="CVE-2021-23337, GHSA-35jh-r3h4-6jhm")
    assert _entries(tmp_path)[0]["advisories"] == ["CVE-2021-23337", "GHSA-35jh-r3h4-6jhm"]


def test_an_unbounded_advisory_list_is_refused(tmp_path):
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, advisories=",".join(f"CVE-2020-{n}" for n in range(waivers.MAX_ADVISORIES + 1)))


# ---------------------------------------------------------------------------
# Supply chain (spec D7) — the refusal that has to live in exactly one place
# ---------------------------------------------------------------------------

def test_a_supply_chain_finding_is_refused_without_an_explicit_class(tmp_path):
    """`waiver_filter.is_waived_by` will never apply a non-supply-chain waiver
    to a supply-chain finding. Writing that pair produces an entry that reads in
    the audit trail as a decision taken and behaves as no decision at all —
    which is worse than no entry, so it is a refusal and not a warning."""
    with pytest.raises(waivers.WaiverError) as excinfo:
        _add(tmp_path, package="evil-postinstall", finding_class="supply_chain")
    assert "supply" in str(excinfo.value)
    assert not (tmp_path / ".agents" / "security" / "sca-waivers.json").exists()


def test_a_supply_chain_waiver_that_says_so_is_accepted(tmp_path):
    _add(tmp_path, package="evil-postinstall", klass="supply_chain",
         finding_class="supply_chain", reason="audite a la main")
    assert _entries(tmp_path)[0]["class"] == "supply_chain"


def test_an_unknown_finding_class_is_refused(tmp_path):
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, finding_class="mystery")


def test_a_non_supply_chain_finding_class_does_not_force_the_class(tmp_path):
    """The refusal is targeted, not a blanket requirement to restate the class:
    declaring `known_cve` on both sides must stay the ordinary, quiet path."""
    _add(tmp_path, finding_class="known_cve")
    assert _entries(tmp_path)[0]["class"] == "known_cve"


# ---------------------------------------------------------------------------
# A malformed store fails LOUDLY — same posture as the three state stores
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "{not json at all",
    '["a", "list"]',
    '"a string"',
    '{"waivers": {"not": "a list"}}',
    '{"waivers": ["not an object"]}',
])
def test_a_malformed_register_raises_instead_of_being_replaced(tmp_path, body):
    """The failure mode this guards against is a scanner going green because the
    register was quietly reset. Loud, and — asserted below — non-destructive."""
    path = tmp_path / ".agents" / "security" / "sca-waivers.json"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path)
    assert path.read_text(encoding="utf-8") == body


def test_a_malformed_register_is_named_in_the_message(tmp_path):
    path = tmp_path / ".agents" / "security" / "sca-waivers.json"
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(waivers.WaiverError) as excinfo:
        waivers.load(tmp_path)
    assert "sca-waivers.json" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The CLI surface — exit 2 is an operator refusal, and the dashboard route
# depends on that distinction to answer 400 rather than 502.
# ---------------------------------------------------------------------------

def test_the_cli_adds_and_reports_zero_on_success(tmp_path, capsys):
    rc = waivers.main(["--root", str(tmp_path), "add", "--ecosystem", "npm",
                       "--package", "lodash", "--version", "4.17.20"])
    assert rc == 0
    assert "WAIVER:" in capsys.readouterr().out
    assert len(_entries(tmp_path)) == 1


def test_the_cli_exits_2_on_a_refusal(tmp_path, capsys):
    """rc 2, exactly like `tasks.py` and `specs.py` — the dashboard's write
    route reads that code to answer 400 (the caller's fault) instead of 502 (a
    server failure)."""
    (tmp_path / ".agents" / "security").mkdir(parents=True)
    (tmp_path / ".agents" / "security" / "sca-waivers.json").write_text("{bad", encoding="utf-8")
    rc = waivers.main(["--root", str(tmp_path), "add", "--ecosystem", "npm",
                       "--package", "lodash", "--version", "1.0.0"])
    assert rc == 2
    assert "waivers.py:" in capsys.readouterr().err


def test_the_cli_status_lists_every_entry(tmp_path, capsys):
    _add(tmp_path, package="lodash")
    _add(tmp_path, package="minimist", status="pending_review")
    assert waivers.main(["--root", str(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "2 entries" in out
    assert "accepted=1" in out
    assert "pending_review=1" in out
    assert "lodash" in out and "minimist" in out


def test_the_cli_status_on_an_empty_project_says_zero(tmp_path, capsys):
    assert waivers.main(["--root", str(tmp_path), "status"]) == 0
    assert "0 entries" in capsys.readouterr().out


def test_the_cli_status_json_is_the_machine_shape(tmp_path, capsys):
    _add(tmp_path)
    waivers.main(["--root", str(tmp_path), "status", "--json"])
    entries = json.loads(capsys.readouterr().out)
    assert entries[0]["package"] == "lodash"


# ---------------------------------------------------------------------------
# WRITER vs READER — the cross-check that keeps the two ends of this file in
# agreement. `waiver_filter.is_waived_by` is what actually decides the gate.
# ---------------------------------------------------------------------------

def _finding(**kwargs) -> dict:
    base = {"ecosystem": "npm", "package": "lodash", "version": "4.17.20",
            "advisory": "CVE-2021-23337", "severity": "high", "class": "known_cve"}
    base.update(kwargs)
    return base


def test_an_entry_written_here_actually_waives_the_matching_finding(tmp_path):
    """The end-to-end property, and the reason this section exists: an entry
    this module writes must be one the GATE recognises. Asserted against the
    real reader, never against a re-implementation of its rules."""
    _add(tmp_path)
    entry = _entries(tmp_path)[0]
    assert waiver_filter.is_waived_by(_finding(), entry) is True


def test_a_narrowed_entry_waives_only_the_advisories_it_names(tmp_path):
    _add(tmp_path, advisories="CVE-2021-23337")
    entry = _entries(tmp_path)[0]
    assert waiver_filter.is_waived_by(_finding(), entry) is True
    assert waiver_filter.is_waived_by(_finding(advisory="CVE-2099-0001"), entry) is False


def test_an_entry_does_not_survive_a_version_bump(tmp_path):
    _add(tmp_path, version="4.17.20")
    entry = _entries(tmp_path)[0]
    assert waiver_filter.is_waived_by(_finding(version="4.17.21"), entry) is False


def test_a_star_version_waives_every_version(tmp_path):
    _add(tmp_path, version="*")
    entry = _entries(tmp_path)[0]
    assert waiver_filter.is_waived_by(_finding(version="9.9.9"), entry) is True


def test_the_supply_chain_refusal_matches_what_the_reader_would_have_done(tmp_path):
    """The refusal in `add_waiver` is not a second, independent rule — it is the
    reader's rule, enforced early. This test proves the two agree: the entry the
    writer refuses is exactly the entry the reader would have ignored."""
    _add(tmp_path, package="evil-postinstall", klass="known_cve")
    would_have_been_written = _entries(tmp_path)[0]
    supply_chain_finding = _finding(package="evil-postinstall",
                                    **{"class": "supply_chain"})
    assert waiver_filter.is_waived_by(supply_chain_finding, would_have_been_written) is False
    with pytest.raises(waivers.WaiverError):
        _add(tmp_path, package="evil-postinstall", finding_class="supply_chain")


def test_an_explicit_supply_chain_entry_is_honoured_by_the_reader(tmp_path):
    _add(tmp_path, package="evil-postinstall", klass="supply_chain",
         finding_class="supply_chain")
    entry = _entries(tmp_path)[0]
    finding = _finding(package="evil-postinstall", **{"class": "supply_chain"})
    assert waiver_filter.is_waived_by(finding, entry) is True
