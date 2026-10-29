#!/usr/bin/env python3
"""mcp_render.py — READ-ONLY generator: paste-ready MCP blocks for other hosts.

The human maintains ONE canonical MCP config, ``.mcp.json`` (Claude Code,
project scope). This tool parses it, verifies every server against the
audited allowlist (``.agents/state/gates/MCP_ALLOWLIST.md``), and PRINTS the
ready-to-paste equivalent blocks for VS Code, Gemini, and Codex. The human
pastes. **Nothing is written to any file** — no ``--apply``, no TTY logic,
because none is needed when nothing writes.

This is the deferred "gate on parsed config" from ledger L-00000033, in its
safest form: a read-only render, never an install-time hook.

Usage::

    python .agents/bin/mcp_render.py [--host vscode|gemini|codex|all]

Validation pipeline — order is load-bearing (class-0 sits first):

1. Parse ``.mcp.json`` (absent -> friendly note, exit 0; malformed JSON ->
   loud refuse, exit 1).
2. Literal-secret scan BEFORE any rendering: every ``env`` value AND every
   ``args`` token that is not a ``${VAR}`` expansion and looks value-like
   (matches a common credential shape, or follows a ``--api-key``/``--token``
   -style flag) -> REFUSE, naming only the server + KEY/FLAG NAME — the value
   itself never reaches stdout/stderr. As belt-and-braces, the RAW source
   text is also piped through ``gitleaks-scan.sh --content`` when available:
   exit 2 -> refuse; scanner/bash absent -> print ``COVERAGE DEGRADED`` (on
   stderr) and continue — never a false block.
3. Shape gate: a server is propagatable ONLY if ``command == "npx"`` AND
   ``args`` match ``["-y", "<package>@<version>", ...flags]`` (the ``-y``
   optional). Anything else (bash, docker, uvx, node, a url/sse/http server,
   or npx without a pinned package in the right position) goes to the
   ``manual`` list and is NEVER rendered.
4. Pin extraction: exactly ONE ``@``-bearing token is allowed among ``args``
   (more than one -> refuse as ambiguous, naming them). Scoped packages split
   on the LAST ``@`` (``@scope/name@1.2.3`` -> package ``@scope/name``,
   version ``1.2.3``).
5. Allowlist gate: the row's ``<name>`` is the PACKAGE IDENTITY extracted
   above — never the human-chosen config key. Fixed-string comparison; any
   unaudited or version-mismatched server refuses the WHOLE run, listing
   every failure (no partial output).
6. Only then, render.

Exit codes: 0 clean (including the "nothing to do" notes), 1 any refusal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

CONFIG_NAME = ".mcp.json"
ALLOWLIST_REL = Path(".agents") / "state" / "gates" / "MCP_ALLOWLIST.md"
REGISTRY_HINT = ".agents/ref/MCP_REGISTRY.md"

# ``${VAR}`` — the only shape that is never a literal. Anything else in an
# env value or an args token is a candidate for the literal-secret scan.
VAR_EXPANSION_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

# Conservative, deliberately over-inclusive "this looks like a live
# credential" shapes. False positives refuse (safe); false negatives are
# backstopped by the gitleaks belt-and-braces pass below.
_CREDENTIAL_SHAPE_PATTERNS = [
    re.compile(r"^sk-[A-Za-z0-9]{10,}$"),                       # OpenAI-style
    re.compile(r"^gh[pousr]_[A-Za-z0-9]{20,}$"),                # GitHub tokens
    re.compile(r"^github_pat_[A-Za-z0-9_]{20,}$"),
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                          # AWS access key id
    re.compile(r"^xox[baprs]-[A-Za-z0-9-]{10,}$"),              # Slack
    re.compile(r"^AIza[0-9A-Za-z_\-]{20,}$"),                   # Google API key
    re.compile(r"^glpat-[A-Za-z0-9_\-]{16,}$"),                 # GitLab PAT
    re.compile(r"^eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"^[A-Za-z0-9_\-]{32,}$"),                       # generic opaque token
]

# A preceding flag whose NAME alone means "the next token is a secret",
# regardless of shape — e.g. ``--api-key``, ``--token``, ``--auth-token``.
_FLAG_LIKE_RE = re.compile(
    r"^--?[\w-]*(api[-_]?key|token|secret|password|passwd|pwd)[\w-]*$", re.IGNORECASE
)


class McpRenderError(Exception):
    """A malformed store. Loud, never a silent partial parse."""


def force_utf8_stdio() -> None:
    """Windows consoles default to cp1252; this tool's output (and any pasted
    JSON/TOML) is UTF-8 by construction. Mirrors ledger.py/tasks.py."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", newline="\n")


def config_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / CONFIG_NAME


def allowlist_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / ALLOWLIST_REL


# --------------------------------------------------------------------------
# step 1 — parse
# --------------------------------------------------------------------------
def load_config(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """``None`` means "no .mcp.json" (a friendly, exit-0 case for the
    caller). A malformed file raises loudly instead of degrading."""
    path = config_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise McpRenderError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise McpRenderError(f"{path}: expected a JSON object at the top level")
    return data


# --------------------------------------------------------------------------
# step 2 — literal-secret scan
# --------------------------------------------------------------------------
def is_var_expansion(value: str) -> bool:
    return bool(VAR_EXPANSION_RE.match(value))


def looks_credential_shape(value: str) -> bool:
    return any(p.search(value) for p in _CREDENTIAL_SHAPE_PATTERNS)


def scan_literal_secrets(servers: dict[str, Any]) -> list[str]:
    """Every finding names the server + the offending KEY or FLAG NAME only —
    never the value. Returns an empty list when clean."""
    findings: list[str] = []
    for key, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        env = spec.get("env") or {}
        if isinstance(env, dict):
            for env_key, val in env.items():
                if not isinstance(val, str) or is_var_expansion(val):
                    continue
                # Security-review HIGH: shape-only detection missed literal
                # secrets that fit none of the vendor patterns. A credential-
                # NAMED key holding ANY literal is refused — the human writes
                # ${VAR}, never a value, whatever the value looks like.
                key_is_credential = bool(_FLAG_LIKE_RE.match("--" + env_key))
                if looks_credential_shape(val) or key_is_credential:
                    findings.append(
                        f"server '{key}': env key '{env_key}' holds a literal "
                        "value (must be a ${VAR} expansion; value withheld)"
                    )
        raw_args = spec.get("args") or []
        if isinstance(raw_args, list):
            for i, tok in enumerate(raw_args):
                if not isinstance(tok, str) or is_var_expansion(tok):
                    continue
                # Security-review HIGH: a joined "--api-key=<secret>" token was
                # caught by neither the adjacency check (two-token form only)
                # nor the anchored shape regexes (the prefix breaks them).
                # Split on the first '=' and judge both halves.
                if tok.startswith("-") and "=" in tok:
                    flag_part, _, value_part = tok.partition("=")
                    if _FLAG_LIKE_RE.match(flag_part) and not is_var_expansion(value_part):
                        findings.append(
                            f"server '{key}': literal value joined to "
                            f"'{flag_part}=' (value withheld)"
                        )
                        continue
                prev = raw_args[i - 1] if i > 0 and isinstance(raw_args[i - 1], str) else None
                flagged = bool(prev) and bool(_FLAG_LIKE_RE.match(prev))
                if looks_credential_shape(tok) or flagged:
                    label = prev if flagged else f"arg[{i}]"
                    findings.append(
                        f"server '{key}': literal secret-shaped value following "
                        f"'{label}' (value withheld)"
                    )
    return findings


def run_gitleaks_belt_and_brace(raw_text: str) -> str:
    """Pipe the RAW source config through gitleaks-scan.sh --content as
    belt-and-braces on top of the regex scan above. Returns one of
    'CLEAN' | 'BLOCK' | 'DEGRADED'. Never raises, never forwards the
    subprocess's own stdout/stderr verbatim (it is already redacted upstream,
    but this tool synthesizes its own messages regardless, defense in
    depth)."""
    script = Path(__file__).resolve().parent.parent / "security" / "gitleaks-scan.sh"
    bash = shutil.which("bash")
    if not bash or not script.exists():
        return "DEGRADED"
    try:
        result = subprocess.run(
            [bash, str(script), "--content"],
            input=raw_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "DEGRADED"
    if result.returncode == 2:
        return "BLOCK"
    if "COVERAGE DEGRADED" in (result.stderr or ""):
        return "DEGRADED"
    return "CLEAN"


# --------------------------------------------------------------------------
# steps 3-4 — shape gate + pin extraction
# --------------------------------------------------------------------------
def split_pin(token: str) -> tuple[str, str]:
    """Split on the LAST ``@`` — the only split that survives scoped
    packages: ``@scope/name@1.2.3`` -> (``@scope/name``, ``1.2.3``)."""
    name, _, version = token.rpartition("@")
    return name, version


def npx_shape(command: str, args: list[Any]) -> str | None:
    """Returns the package pin token when ``command``/``args`` match
    ``["-y", "<package>@<version>", ...flags]`` (the ``-y`` optional).
    ``None`` means "not propagatable" -> the caller routes it to manual."""
    if command != "npx" or not isinstance(args, list):
        return None
    rest = list(args)
    if rest and rest[0] == "-y":
        rest = rest[1:]
    if not rest or not isinstance(rest[0], str):
        return None
    pkg_tok = rest[0]
    if "@" not in pkg_tok or is_var_expansion(pkg_tok):
        return None
    return pkg_tok


def at_bearing_tokens(args: list[Any]) -> list[str]:
    return [
        tok for tok in args
        if isinstance(tok, str) and "@" in tok and not is_var_expansion(tok)
    ]


# --------------------------------------------------------------------------
# step 5 — allowlist gate
# --------------------------------------------------------------------------
_ROW_RE = re.compile(r"^mcp\s+(?P<pkgver>\S+)\s+audit=(?P<audit>\S+)\b")
# T-00000039: the allowlist file DOCUMENTS its own line format inside an HTML
# comment ("mcp <name>@<version> audit=pass by=… evidence=…"), and that line
# starts with "mcp " and carries audit=pass — so the scanner read the example
# as a real audited row. A file whose own header says "zero rows today"
# parsed as {"<name>": {"<version>"}}. Not exploitable (an npm identity
# cannot contain <>, so no real package was ever authorised by it) but the
# row count was wrong and the docstring's tolerance claim was false. Comment
# blocks are removed BEFORE scanning; the placeholder guard below is the
# second layer, in case a future header documents the format outside a
# comment.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def parse_allowlist(text: str) -> dict[str, set[str]]:
    """``{package_identity: {audited versions}}``. Tolerant of comments,
    blank lines, and the file's own HTML-comment header — only lines
    starting with ``mcp `` and carrying ``audit=pass``, OUTSIDE any HTML
    comment block, count as a row. A placeholder identity (one containing
    ``<`` or ``>``) is never a row: no real package identity can carry
    those characters, so such a line is documentation, not an authorisation."""
    text = _HTML_COMMENT_RE.sub("", text)
    rows: dict[str, set[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("mcp "):
            continue
        if "<" in line or ">" in line:
            continue
        m = _ROW_RE.match(line)
        if not m or m.group("audit") != "pass":
            continue
        pkgver = m.group("pkgver")
        if "@" not in pkgver:
            continue
        name, version = split_pin(pkgver)
        rows.setdefault(name, set()).add(version)
    return rows


# --------------------------------------------------------------------------
# step 6 — rendering (verified dialects)
# --------------------------------------------------------------------------
HOST_HEADERS = {
    "vscode": '# paste into .vscode/mcp.json (merge under the top-level "servers" key)',
    "gemini": '# merge into .gemini/settings.json (see the line below for the key)',
    "codex": "# paste into ~/.codex/config.toml (user scope) — one [mcp_servers.<key>] block per server",
}


def _rewrite_env_vscode(value: str) -> str:
    if is_var_expansion(value):
        inner = value[2:-1]
        return "${env:" + inner + "}"
    return value


def render_vscode(propagatable: dict[str, dict[str, Any]]) -> str:
    servers_obj: dict[str, Any] = {}
    for key, info in propagatable.items():
        servers_obj[key] = {
            "type": "stdio",
            "command": info["command"],
            "args": info["args"],
            "env": {k: _rewrite_env_vscode(v) for k, v in info["env"].items()},
        }
    body = json.dumps({"servers": servers_obj}, indent=2, ensure_ascii=False)
    return HOST_HEADERS["vscode"] + "\n" + body


def render_gemini(propagatable: dict[str, dict[str, Any]]) -> str:
    servers_obj: dict[str, Any] = {}
    for key, info in propagatable.items():
        servers_obj[key] = {
            "command": info["command"],
            "args": info["args"],
            "env": dict(info["env"]),
        }
    body = json.dumps({"mcpServers": servers_obj}, indent=2, ensure_ascii=False)
    return (
        HOST_HEADERS["gemini"]
        + "\n"
        + body
        + '\nMerge these entries into the top-level "mcpServers" key of .gemini/settings.json.'
    )


def _toml_str(value: str) -> str:
    """A TOML basic string. json.dumps' escaping (backslash, quote, control
    chars) is a valid subset of TOML's basic-string escaping for the plain
    ASCII values MCP config carries."""
    return json.dumps(value)


def render_codex(propagatable: dict[str, dict[str, Any]]) -> str:
    lines = [HOST_HEADERS["codex"]]
    for key, info in propagatable.items():
        lines.append(f"[mcp_servers.{key}]")
        lines.append(f"command = {_toml_str(info['command'])}")
        args_arr = "[" + ", ".join(_toml_str(a) for a in info["args"]) + "]"
        lines.append(f"args = {args_arr}")
        if info["env"]:
            env_inline = "{ " + ", ".join(f"{k} = {_toml_str(v)}" for k, v in info["env"].items()) + " }"
            lines.append(f"env = {env_inline}")
        lines.append("")
    return "\n".join(lines).rstrip("\n")


RENDERERS = {"vscode": render_vscode, "gemini": render_gemini, "codex": render_codex}

FINAL_REMINDER = (
    "\nReminder: the pasted files are project/user state, not generated by this tool "
    "— re-run it after any .mcp.json change, and a server DELETED from .mcp.json must "
    "be removed from each pasted target BY HAND (this tool only prints, it never "
    "deletes)."
)


def render_manual(manual: list[tuple[str, str, list[Any]]]) -> str:
    lines = ["manual — propagate by hand after audit:"]
    for key, command, raw_args in manual:
        lines.append(f" - {key}: command={command!r} args={raw_args!r}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
def classify_servers(
    servers: dict[str, Any], allowlist_rows: dict[str, set[str]]
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, list[Any]]], list[str]]:
    """Returns (propagatable, manual, failures). ``failures`` non-empty means
    the WHOLE run refuses — the caller must not render anything."""
    propagatable: dict[str, dict[str, Any]] = {}
    manual: list[tuple[str, str, list[Any]]] = []
    failures: list[str] = []

    for key, spec in servers.items():
        if not isinstance(spec, dict):
            failures.append(f"server '{key}': expected an object")
            continue
        command = spec.get("command", "")
        raw_args = spec.get("args") or []
        env = spec.get("env") or {}
        pkg_tok = npx_shape(command, raw_args)
        if pkg_tok is None:
            manual.append((key, command, raw_args))
            continue

        at_tokens = at_bearing_tokens(raw_args)
        if len(at_tokens) != 1:
            failures.append(
                f"server '{key}': ambiguous package pin — {len(at_tokens)} "
                f"'@'-bearing token(s) found: {', '.join(at_tokens) or '(none)'}"
            )
            continue

        name, version = split_pin(at_tokens[0])
        versions = allowlist_rows.get(name)
        if versions is None:
            failures.append(
                f"server '{key}': package '{name}@{version}' is not audited — "
                f"no allowlist row for '{name}' (see {REGISTRY_HINT})"
            )
            continue
        if version not in versions:
            failures.append(
                f"server '{key}': package '{name}' pinned at '{version}' but the "
                f"allowlist audits {sorted(versions)} — re-audit the bump (see {REGISTRY_HINT})"
            )
            continue

        propagatable[key] = {"command": command, "args": raw_args, "env": env}

    return propagatable, manual, failures


def run(root: str | os.PathLike[str], host: str, out: list[str], err: list[str]) -> int:
    """Core logic, output-sink-injected so both the CLI (stdout/stderr) and
    tests (plain lists) can drive it identically."""
    try:
        cfg = load_config(root)
    except McpRenderError as exc:
        err.append(f"mcp_render.py: {exc}")
        return 1

    if cfg is None:
        out.append(
            f"No {CONFIG_NAME} found at {config_path(root)} — nothing to propagate. "
            f"Add a server via the audit procedure in {REGISTRY_HINT} first."
        )
        return 0

    servers = cfg.get("mcpServers") or {}
    if not isinstance(servers, dict) or not servers:
        out.append(f"{CONFIG_NAME} has no servers configured — nothing to propagate.")
        return 0

    # step 2 — own literal-secret scan, before anything else.
    secret_findings = scan_literal_secrets(servers)
    if secret_findings:
        err.append("REFUSE — literal secret-shaped value(s) detected (values withheld):")
        err.extend(f" - {f}" for f in secret_findings)
        return 1

    # step 2 (cont.) — belt-and-braces gitleaks pass on the raw source text.
    raw_text = config_path(root).read_text(encoding="utf-8")
    verdict = run_gitleaks_belt_and_brace(raw_text)
    if verdict == "BLOCK":
        err.append(
            "REFUSE — gitleaks flagged the raw MCP config as containing secret(s) "
            "(values withheld; class-0, non-waivable)."
        )
        return 1
    if verdict == "DEGRADED":
        err.append(
            "COVERAGE DEGRADED: gitleaks/bash not available for the belt-and-braces "
            "pass — proceeding on the literal-secret scan only."
        )

    # step 5 prerequisite — the allowlist file itself must exist.
    alist_path = allowlist_path(root)
    if not alist_path.exists():
        err.append(
            f"REFUSE — {alist_path} not found. Create it first: see {REGISTRY_HINT} "
            "§ Allowlist row format."
        )
        return 1
    allowlist_rows = parse_allowlist(alist_path.read_text(encoding="utf-8"))

    # steps 3-5 — classify every server.
    propagatable, manual, failures = classify_servers(servers, allowlist_rows)
    if failures:
        err.append("REFUSE — one or more MCP servers failed the allowlist gate:")
        err.extend(f" - {f}" for f in failures)
        return 1

    # step 6 — render. No partial output happens above this line.
    hosts = ("vscode", "gemini", "codex") if host == "all" else (host,)
    blocks: list[str] = []
    if propagatable:
        for h in hosts:
            blocks.append(RENDERERS[h](propagatable))
    if manual:
        blocks.append(render_manual(manual))
    if blocks:
        out.append("\n\n".join(blocks) + "\n" + FINAL_REMINDER)
    else:
        out.append(f"{CONFIG_NAME} has no servers configured — nothing to propagate.")
    return 0


def check_coherence(
    root: str | os.PathLike[str], out: list[str], err: list[str]
) -> int:
    """--check (T-00000461): VALIDATE the MCP allowlist against ``.mcp.json`` —
    it NEVER fills the allowlist, it only reports incoherence (rc 1). Incoherent
    when: an allowlist line is malformed, is not ``audit=pass``, lacks
    ``evidence=`` or a pinned ``@version``; a row is PHANTOM (no npx server
    declares its package); or an npx server has no matching audited row (the last
    is delegated to ``classify_servers``, which also pins version drift). Without
    ``.mcp.json``: coherent IFF zero rows. This is the piège-2 vacuity pin: today
    the allowlist has zero rows and ``.mcp.json`` is absent — coherent, and that
    emptiness is deliberately epinglée."""
    problems: list[str] = []
    alist_path = allowlist_path(root)
    alist_text = alist_path.read_text(encoding="utf-8") if alist_path.exists() else ""
    row_names: set[str] = set()
    for raw in _HTML_COMMENT_RE.sub("", alist_text).splitlines():
        line = raw.strip()
        if not line.startswith("mcp "):
            continue
        if "<" in line or ">" in line:  # a documented placeholder is not a row
            continue
        m = _ROW_RE.match(line)
        if not m or m.group("audit") != "pass":
            problems.append(f"malformed allowlist row (want 'mcp <pkg>@<ver> audit=pass …'): {line!r}")
            continue
        if "evidence=" not in line:
            problems.append(f"allowlist row without evidence=: {line!r}")
            continue
        pkgver = m.group("pkgver")
        if "@" not in pkgver:
            problems.append(f"allowlist row without a pinned @version: {line!r}")
            continue
        row_names.add(split_pin(pkgver)[0])

    try:
        cfg = load_config(root)
    except McpRenderError as exc:
        problems.append(f"{CONFIG_NAME} is not readable: {exc}")
        cfg = None
        alist_text = ""  # a broken config cannot validate rows either

    if cfg is None:
        if row_names:
            problems.append(
                f"{CONFIG_NAME} absent but the allowlist authorises "
                f"{sorted(row_names)} — every row is PHANTOM"
            )
    else:
        servers = cfg.get("mcpServers") or {}
        servers = servers if isinstance(servers, dict) else {}
        npx_names: set[str] = set()
        for spec in servers.values():
            if not isinstance(spec, dict):
                continue
            tok = npx_shape(spec.get("command", ""), spec.get("args") or [])
            if tok is not None:
                npx_names.add(split_pin(tok)[0])
        # version-level coherence + "npx server has no row" (delegated).
        _prop, _manual, failures = classify_servers(servers, parse_allowlist(alist_text))
        problems.extend(failures)
        for name in sorted(row_names - npx_names):
            problems.append(
                f"PHANTOM allowlist row for {name!r} — no npx server in {CONFIG_NAME} declares it"
            )

    if problems:
        err.append("MCP ALLOWLIST INCOHERENT with .mcp.json:")
        err.extend(f" - {p}" for p in problems)
        return 1
    out.append("MCP allowlist coherent with .mcp.json (checked, not filled).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only generator: paste-ready MCP blocks for VS Code/Gemini/Codex."
    )
    ap.add_argument("--host", choices=("vscode", "gemini", "codex", "all"), default="all")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    ap.add_argument(
        "--check", action="store_true",
        help="VALIDATE the allowlist against .mcp.json (rc 1 if incoherent); never fills it",
    )
    args = ap.parse_args(argv)
    force_utf8_stdio()

    out: list[str] = []
    err: list[str] = []
    if args.check:
        code = check_coherence(args.root, out, err)
    else:
        code = run(args.root, args.host, out, err)
    for line in out:
        print(line)
    for line in err:
        print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
