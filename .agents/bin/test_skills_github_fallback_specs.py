"""Unicode allowlist of the skills fallback, honoured only under a traced decision
(T-01M5BZBZ849P61Y6471JZMMPRD, T-01M5CN9FM2MPY8Z00AS7FTXXWH).

Split out of `test_skills_github_fallback.py`, which crossed the 1600-line bound of
`test_python_file_length.py`: these are the tests whose allowlist entry (`ALLOW`) cites
an S-id that `build_root` writes into the throwaway `.agents/state/specs/SPECS.jsonl`.
Same discipline as the original file, whose helpers and autouse fixtures are imported
(never copied): ZERO real network (`_block_network`), pilot-terminal regime
(`_pilot_terminal`), every tree under `tmp_path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_skills_github_fallback import (  # noqa: E402,F401 — autouse fixtures must be in this module's namespace
    ZW_SKILL,
    _block_network,
    _pilot_terminal,
    _search_fake,
    _zw,
    build_root,
    recent_iso,
    resp,
    run,
    sgf,
)

# The S-id below is the `kind: decision` entry `build_root` writes into the throwaway SPECS journal.
ALLOW = '{"entrees": [{"cible": "%s", "codepoint": "U+200B", "decision": "S-01M5CD8VK6"}]}'


@pytest.mark.parametrize("allowlist", [None, ALLOW % "o/r#good-skill@def456"])
def test_install_refuses_invisible_unicode_writes_nothing(tmp_path, capsys, monkeypatch, allowlist):
    rc, _out, err, vendored = _zw(tmp_path, capsys, monkeypatch, allowlist)  # sha neuf : entrée nulle
    assert rc == sgf.RC_DEGRADED and vendored == []
    assert "INSTALL REFUSED invisible-unicode character refused: U+200B ZERO WIDTH SPACE" in err


def test_install_allowlisted_sha_installs(tmp_path, capsys, monkeypatch):
    rc, out, err, vendored = _zw(tmp_path, capsys, monkeypatch, ALLOW % "o/r#good-skill@abc123")
    assert rc == 0, err
    assert "INSTALLED o/r#good-skill@abc123" in out and vendored == ["good-skill"]


def test_install_unknown_decision_refuses_and_says_so(tmp_path, capsys, monkeypatch):
    # T-01M5CN9FM2MPY8Z00AS7FTXXWH : un S-id absent du journal n'admet rien, et le refus le DIT.
    allowlist = (ALLOW % "o/r#good-skill@abc123").replace("S-01M5CD8VK6", "S-01M5ZZZZZZ")
    rc, _out, err, vendored = _zw(tmp_path, capsys, monkeypatch, allowlist)
    assert rc == sgf.RC_DEGRADED and vendored == []
    assert ("INSTALL REFUSED invisible-unicode character refused: U+200B ZERO WIDTH SPACE at line"
            in err), err
    assert "; allowlist entry 0 ignored: decision S-01M5ZZZZZZ not found in SPECS" in err, err


@pytest.mark.parametrize("allowlist", [
    "{broken", (ALLOW % "o/r#good-skill@abc123").replace(', "decision": "S-01M5CD8VK6"', "")])
def test_install_unreadable_or_undecided_allowlist_refuses(tmp_path, capsys, monkeypatch, allowlist):
    rc, _out, err, vendored = _zw(tmp_path, capsys, monkeypatch, allowlist)
    assert rc == sgf.RC_DEGRADED and vendored == []
    assert "INSTALL REFUSED invisible-unicode allowlist refused: .agents/security/" in err


def test_search_refuses_invisible_candidate_unless_allowlisted(tmp_path, capsys, monkeypatch):
    root = build_root(tmp_path)
    monkeypatch.setattr(sgf, "_resolve_auth", lambda: None)
    item = {"owner": {"login": "zw"}, "name": "repo", "stargazers_count": 120,
            "pushed_at": recent_iso(), "default_branch": "main", "license": {"spdx_id": "MIT"}}
    monkeypatch.setattr(sgf, "http_get", _search_fake([
        ("search/repositories", resp(200, {"items": [item]})),
        ("/repos/zw/repo/commits/", resp(200, {"sha": "cafe1234", "commit": {"tree": {"sha": "t"}}})),
        ("git/trees", resp(200, {"tree": [{"type": "blob", "path": "good/SKILL.md", "size": 400}]})),
        ("raw.githubusercontent.com/zw", resp(200, raw=ZW_SKILL))]))
    _rc, out, _ = run(["search", "--stacks", "python"], root, capsys)
    assert "verdict=REFUSED invisible-unicode character refused: U+200B" in out
    (root / ".agents" / "security" / "unicode-allowlist.json").write_bytes(
        (ALLOW % "zw/repo#good@cafe1234").encode("utf-8"))
    _rc, out, _ = run(["search", "--stacks", "python"], root, capsys)
    assert "TOP python: zw/repo#good@cafe1234" in out
