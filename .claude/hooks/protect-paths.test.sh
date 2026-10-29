#!/usr/bin/env bash
# Tests for protect-paths.sh. Run: bash .claude/hooks/protect-paths.test.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $1"; exit 1; }

# $1 = file path, $2 = expected exit code (0 allow, 2 deny), $3 = label
check() {
  set +e
  OUT=$(printf '{"tool_input":{"file_path":"%s"}}' "$1" | bash "$HERE/protect-paths.sh" 2>&1)
  RC=$?
  set -e
  [ "$RC" -eq "$2" ] || fail "$3 (expected exit $2, got $RC; output: $OUT)"
}

# --- existing behaviour (regression guard — must not change, L-013) ---
check "src/legacy/x.ts" 2 "src/legacy/ still denied"
check ".env.local" 2 ".env.local still denied"
check "foo.credentials.json" 2 "*credentials* still denied"
check "README.md" 0 "README.md still allowed"

# --- turned on purpose (T-00000721): the four lines above stay intact ---
# FORMER TRAP: `*secret*` used to be matched on
# the raw, case-sensitive $FILE only, so "SecretsRotation" passed here while the
# three Python twins refused it. Every rule is now judged on the case-folded
# candidates too, like the twins — the same file is refused on every host.
check "docs/SecretsRotation.md" 2 "aligned with the Python twins since T-00000721 (tokens judged case-folded)"

# --- new: MCP configuration is human-audited, never agent-writable ---
check ".mcp.json" 2 ".mcp.json denied"
check ".vscode/mcp.json" 2 ".vscode/mcp.json denied"
check ".MCP.json" 2 ".MCP.json denied (every rule is judged on the case-folded candidate, T-00000722)"
check ".codex/config.toml" 2 ".codex/config.toml denied"
check ".gemini/settings.json" 2 ".gemini/settings.json denied"
check ".github/copilot/settings.json" 2 ".github/copilot/settings.json denied (disableAllHooks, H-29)"
check ".codex/agents/foo.toml" 0 ".codex/agents/foo.toml allowed (neighbour, not MCP config)"

# --- new: .env TEMPLATES are not secrets, real .env files still are ---
# A template carries variable NAMES and no values, and is the file an agent must
# update when it adds a configuration variable. Recognition is BY SUFFIX, never
# by intent — so the negative arms below are the load-bearing half of this block:
# without them the exception could widen to any `.env*` and this suite would
# still be green.
check ".env.example" 0 ".env.example editable (template, names only)"
check ".env.sample" 0 ".env.sample editable (template)"
check ".env.template" 0 ".env.template editable (template)"
check ".env.dist" 0 ".env.dist editable (template)"
check "apps/web/.env.example" 0 "nested .env.example editable (suffix match, not a root-only rule)"
check ".env" 2 "a bare .env still denied"
check ".env.production" 2 ".env.production still denied (not a recognized template suffix)"
# The trap: a recognized suffix is a SUFFIX. `.env.example.bak` ends in .bak,
# so it is a real env file under a backup name and must stay denied.
check ".env.example.bak" 2 ".env.example.bak still denied (suffix, not substring)"
check "dotenv.example" 0 "dotenv.example allowed (never matched .env in the first place)"
# A template is recognized WHATEVER ITS CASE, on every host (decision
# S-01M5X79JTGRSSTB872R4YBPVMF, which replaces S-01M5SZJE11); a real env file
# stays denied whatever its case, and the suffix rule still holds.
check ".env.EXAMPLE" 0 "W1 .env.EXAMPLE editable (template, case-insensitive)"
check "app/.env.Example" 0 "W2 nested .env.Example editable (template, case-insensitive)"
check ".env.TEMPLATE" 0 "W3 .env.TEMPLATE editable (template, case-insensitive)"
check ".env.Sample" 0 "W4 .env.Sample editable (template, case-insensitive)"
check ".env.Dist" 0 "W5 .env.Dist editable (template, case-insensitive)"
check ".env.LOCAL" 2 "W6 .env.LOCAL still denied (not a template, whatever its case)"
check ".env.EXAMPLE." 2 "W7 .env.EXAMPLE. still denied (NTFS trailing dot is not a template)"
check ".env.Example.bak" 2 "W8 .env.Example.bak still denied (suffix, not substring, whatever its case)"

# --- T-00000844: the class-0 exception register is pilot-only ---
# A corrupt `.gitleaks.toml` used to switch the secrets gate off at BOTH hooks;
# a widened one exempts a secret. The neighbour stays editable.
check ".gitleaks.toml" 2 ".gitleaks.toml denied (class-0 exception register, pilot only)"
check "sub/.GITLEAKS.toml" 2 "a case-folded .gitleaks.toml under a subdirectory denied"
check "docs/gitleaks-notes.md" 0 "docs/gitleaks-notes.md allowed (neighbour, not the register)"

# --- T-00000847: the specs journal is written by specs.py only ---
# It carries the night-eligible contracts and the night-delivered markers /night
# re-reads unattended; an Edit could erase one. Its neighbours stay editable.
check ".agents/state/specs/SPECS.json" 2 "SPECS.json denied (append-only journal, specs.py only)"
check ".AGENTS/STATE/SPECS/specs.json" 2 "a case-folded SPECS.json denied"
check ".agents/state/specs/SPECS.json." 2 "SPECS.json with a trailing NTFS dot denied"
check ".agents/state/local/SPECS.md" 0 "the generated view SPECS.md allowed (not the journal)"
check "docs/SPECS.json" 0 "a SPECS.json elsewhere allowed (the rule is the journal's path)"

# --- T-00001128: the measure guard's arming file is pilot-only ---
# Entered ONE gesture after the marker was armed (f3d47430), by the closing
# pair's correction pass: the hole the plan-chain lesson names. The neighbour
# stays editable, so a rule that refused everything would still be red here.
check ".agents/state/gates/MESURE_REQUIRED" 2 "MESURE_REQUIRED denied (arms the measure guard of new, pilot only)"
check ".agents/state/gates/mesure_required" 2 "a case-folded MESURE_REQUIRED denied"
check ".agents\\state\\gates\\MESURE_REQUIRED" 2 "MESURE_REQUIRED with NTFS backslashes denied"
check ".agents/state/gates/MESURE_REQUIRED.md" 0 "a neighbour of the marker allowed (suffix, not substring)"

echo "PASS: protect-paths (41/41)"
