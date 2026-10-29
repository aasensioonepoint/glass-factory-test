# MCP Registry — allowlist + audit procedure

## Threat, one line

MCP tool descriptions are third-party free text entering the model's
instruction channel every session, mutable server-side without a commit. The
kit ships zero MCP servers; this registry and the audit procedure below must
exist before the first one does, and agents must not be able to write MCP
configuration (see the path guards in `.claude/hooks/protect-paths.sh`,
`.codex/hooks/protect_paths.py`, `.gemini/hooks/protect_paths.py`, plus the
`permissions.deny` layer in `.claude/settings.json`).

## Audit procedure

Before adding ANY row to `.agents/state/gates/MCP_ALLOWLIST.md`:

1. **Pin the EXACT version** of the server you are about to trust — never a
   range, never `latest`, never a floating tag.
2. **Capture tool descriptions as evidence** at audit time: run/introspect the
   server at that exact pinned version and save the full set of tool
   descriptions it advertises to a file (e.g.
   `.agents/state/local/mcp-evidence/<name>-<version>.txt`). This is the
   record of what the model was actually shown, so a later dispute has
   something to diff against.
3. **Record the evidence path** in the allowlist row (see format below) —
   a row without an evidence path is not a valid audit.
4. **Re-audit on ANY version bump.** A new version is a new audit: re-run
   steps 1-3 and append a new row (or update the existing one) before the
   bumped version is used. Never carry a pin forward on trust.

## Allowlist row format

One line per audited server/version, appended to
`.agents/state/gates/MCP_ALLOWLIST.md`:

```
mcp <name>@<version> audit=pass by=<who> date=<date> evidence=<path>
```

Rules:
- **`<name>` is the PACKAGE IDENTITY, never the config key.** It is the
  package name extracted from the server's launch `args` — e.g. an
  `.mcp.json` server declared under the human-chosen key `"figma"` but
  launching `npx -y figma-developer-mcp@1.2.3` audits and matches on
  `figma-developer-mcp`, never on `figma`. A row keyed on the config key does
  not authorize the real package — `mcp_render.py` (see § Propagating to
  other hosts below) refuses exactly that mismatch.
- **npm-only propagation.** Package-identity extraction, and therefore
  `mcp_render.py`'s allowlist gate, only applies to servers launched via
  `npx -y <package>@<version>`. A server started any other way (`bash`,
  `docker`, `uvx`, `node`, a url/sse/http endpoint) has no npm package
  identity to check — it is still auditable by hand under this same
  procedure, but it is never mechanically matched against a row and never
  rendered for other hosts; it is listed as `manual — propagate by hand
  after audit`.
- **Exact pins only, never ranges** — `@1.4.2`, never `@^1.4`, `@latest`, or a
  bare tag.
- **No row without evidence** — `evidence=<path>` must point at a file that
  actually exists and actually contains the captured tool descriptions for
  that exact pinned version.
- Only the auditing human appends rows. Agents and the gate never write this
  file (there is currently no mechanical write-gate — see Residuals below).
- **The allowlist has zero rows today.** No project currently ships an
  audited server, so this redefinition of `<name>` as package identity
  changes the meaning of zero pre-existing rows — there is nothing to
  re-interpret or migrate.

## Worked example — adding the Figma MCP server

What this does NOT require, first: no agent switching, no per-host procedure.
Everything is done BY THE HUMAN in an editor — agents are blocked on these
files by design. The audit and the allowlist row are done ONCE and are
host-agnostic; only the config declaration is per host, and only for the
hosts you actually want the server on (Claude Code only → one file,
`.mcp.json`, done). Per-host config locations: `.mcp.json` (Claude Code),
`.vscode/mcp.json` (VS Code/Copilot), `~/.codex/config.toml`
(`[mcp_servers.*]`, user-scope) for Codex, `.gemini/settings.json`
(`mcpServers`) for Gemini.

Versions below are EXAMPLES — audit the version you actually install.

1. **Pick the exact version.** For an npm-distributed server:
   `npm view figma-developer-mcp version` → say it prints `1.2.3`. That string
   is your pin. (Figma's official Dev Mode server is a local endpoint served by
   the desktop app, not an npm package — for that one the pin is the desktop
   app version, and the evidence step below is what carries the audit.)
2. **Introspect at that pin and capture the evidence** — run the server in
   isolation and record the FULL tool descriptions it announces:

   ```bash
   mkdir -p .agents/state/local/mcp-evidence
   npx -y @modelcontextprotocol/inspector --cli \
       npx -y figma-developer-mcp@1.2.3 --stdio \
       --method tools/list \
       > .agents/state/local/mcp-evidence/figma-1.2.3-tools.json
   ```

   READ what you captured. The tool descriptions are the text that will enter
   the model's instruction channel every session — that reading IS the audit.
3. **Append the row** (the auditing human, never an agent):

   ```
   mcp figma-developer-mcp@1.2.3 audit=pass by=your-user date=2026-07-27 evidence=.agents/state/local/mcp-evidence/figma-1.2.3-tools.json
   ```

   The row is keyed on `figma-developer-mcp` — the PACKAGE, extracted from
   the launch `args` below — never on `figma`, the config key you are about
   to choose for `.mcp.json`. A row keyed on the config key would not
   authorize this package.
4. **Edit the MCP config OUTSIDE the agent** (agents are path-blocked on it).
   `.mcp.json` at the repo root, for Claude Code project scope:

   ```json
   {
     "mcpServers": {
       "figma": {
         "command": "npx",
         "args": ["-y", "figma-developer-mcp@1.2.3", "--stdio"],
         "env": { "FIGMA_API_KEY": "${FIGMA_API_KEY}" }
       }
     }
   }
   ```

   Two rules inside that file: the version in `args` is the SAME exact pin as
   the allowlist row — never `@latest`; and the API key is an environment
   expansion, NEVER a literal — `.mcp.json` is tracked, and a real key in it
   is a class-0 finding (gitleaks blocks, resolution is rotation).
5. **On the next Figma bump** (`1.2.3` → `1.3.0`): re-run step 2 at the new
   pin, DIFF the two evidence files — mutated descriptions are exactly what
   you are looking for — then append a NEW row and update the config. The old
   row stays: the allowlist is append-only history.
6. **Want the server on another host too?** Render the paste-ready blocks
   instead of hand-copying `.mcp.json` into each dialect:

   ```bash
   python .agents/bin/mcp_render.py --host all
   ```

   Read-only: it parses `.mcp.json`, re-verifies the package identity from
   `args` against this allowlist, and PRINTS the `.vscode/mcp.json` /
   `.gemini/settings.json` / `~/.codex/config.toml` equivalents — nothing is
   written to any file, you paste. See § Propagating to other hosts below.

## Propagating to other hosts — `mcp_render.py`

`.agents/bin/mcp_render.py` is a READ-ONLY generator: it never writes a
file, never takes `--apply`. It parses `.mcp.json`, refuses on any literal
secret-shaped value or unaudited/mismatched package (whole-run refusal, no
partial output), and otherwise prints the equivalent blocks for VS Code,
Gemini, and Codex for the human to paste. A server not launched via
`npx -y <package>@<version>` (bash, docker, uvx, a url/sse/http endpoint) is
listed under `manual — propagate by hand after audit` and never rendered.
Re-run it after any `.mcp.json` change; a server deleted from `.mcp.json`
must be removed from each pasted target BY HAND — this tool prints, it never
deletes.

## Residuals — what this does NOT cover

- (a) **A server mutating its descriptions WITHOUT a version change** is
  caught only at the NEXT re-audit, never in real time — the registry has no
  way to detect a server that silently changes behaviour while keeping the
  same version string. Re-audit periodically, not only on bumps you notice.
- (b) **Install commands are not gated at INSTALL time; coherence is VERIFIED,
  not enforced.** `mcp add` (or equivalent) is not mechanically intercepted when
  it runs — string-matching CLI text for that kept producing authorize-unaudited
  bugs (two review passes). What IS mechanical now (T-00000461): `mcp_render.py
  --check` VALIDATES that this registry's allowlist and `.mcp.json` agree — every
  row well-formed, `audit=pass`, carrying `evidence=`; no PHANTOM row; every npx
  server backed by an audited row at its pinned version — and `verify.sh` runs it,
  so an incoherent allowlist reddens the gate against a parsed config, never CLI
  text. It does NOT refuse a non-allowlisted server at RUNTIME: that is a
  Claude-only hook, OUT OF SCOPE here and tracked in **T-00000506**. Until then,
  install-time is process discipline; coherence is checked.
- (c) **`ref/` reaches provisioned projects only via the kit upgrader or a
  manual copy** (merge-only-if-absent, per `.agents/README.md` § Upgrading the
  kit in a project). A project that never re-runs the upgrader keeps whatever
  copy of this file it started with.
