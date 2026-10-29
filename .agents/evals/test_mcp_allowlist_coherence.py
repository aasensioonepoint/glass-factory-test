"""T-00000461 S7 — the MCP allowlist is VALIDATED, never filled.

`mcp_render.py --check` reports incoherence between the audited allowlist
(`.agents/state/gates/MCP_ALLOWLIST.md`) and `.mcp.json`. This eval pins that the
REPO is coherent today — piège 2, a DELIBERATE vacuity: zero rows and `.mcp.json`
absent is coherent, and that emptiness is epinglée on purpose — and that the
check BITES on three FABRICATED roots (L-00000337: never assert against the live
tree alone). Runtime refusal of a non-allowlisted server is OUT OF SCOPE and
tracked in T-00000506 (see MCP_REGISTRY.md § Residuals)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import mcp_render  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

_AUDITED = "mcp pkg@1.0.0 audit=pass by=pilote evidence=https://example/audit\n"


def _check(root) -> tuple[int, str]:
    out: list[str] = []
    err: list[str] = []
    rc = mcp_render.check_coherence(str(root), out, err)
    return rc, "\n".join(out + err)


def _fabricate(tmp_path: Path, mcp=None, allow: str = "") -> Path:
    (tmp_path / ".agents" / "state" / "gates").mkdir(parents=True)
    (tmp_path / ".agents" / "state" / "gates" / "MCP_ALLOWLIST.md").write_text(
        allow, encoding="utf-8"
    )
    if mcp is not None:
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    return tmp_path


def test_repo_allowlist_is_coherent_today():
    """The deliberate vacuity: zero rows, .mcp.json absent -> coherent (rc 0)."""
    rc, msg = _check(ROOT)
    assert rc == 0, msg


def test_fabricated_phantom_row_is_incoherent(tmp_path):
    root = _fabricate(tmp_path, allow=_AUDITED)  # a row, but no .mcp.json server
    rc, msg = _check(root)
    assert rc == 1, msg
    assert "PHANTOM" in msg, msg


def test_fabricated_npx_server_without_a_row_is_incoherent(tmp_path):
    root = _fabricate(
        tmp_path,
        mcp={"mcpServers": {"s": {"command": "npx", "args": ["-y", "pkg@1.0.0"]}}},
        allow="# no rows\n",
    )
    rc, msg = _check(root)
    assert rc == 1, msg


def test_fabricated_server_with_matching_audited_row_is_coherent(tmp_path):
    root = _fabricate(
        tmp_path,
        mcp={"mcpServers": {"s": {"command": "npx", "args": ["-y", "pkg@1.0.0"]}}},
        allow=_AUDITED,
    )
    rc, msg = _check(root)
    assert rc == 0, msg


def test_fabricated_row_without_evidence_is_incoherent(tmp_path):
    root = _fabricate(
        tmp_path,
        mcp={"mcpServers": {"s": {"command": "npx", "args": ["-y", "pkg@1.0.0"]}}},
        allow="mcp pkg@1.0.0 audit=pass by=pilote\n",
    )
    rc, msg = _check(root)
    assert rc == 1, msg
    assert "evidence" in msg, msg
