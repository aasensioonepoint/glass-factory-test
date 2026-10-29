---
description: Configure Langfuse tracing for this project (local or self-hosted/Kubernetes). Usage — /lang [project-name] [pk-lf-…] [sk-lf-…] [https://langfuse.example.com] — or run bare for interactive setup.
---

Configure Langfuse observability for Claude Code in this project. Arguments given: $ARGUMENTS
(positional: $0=project name, $1=public key, $2=secret key, $3=base URL)

## Step 1 — Check current state (idempotent)
```bash
# Plugin installed?
claude plugin list 2>/dev/null | grep -i langfuse
# Manual config present?
cat .claude/settings.local.json 2>/dev/null | grep -i langfuse
```
If already configured: show current BASE_URL + project name (NEVER echo the secret key — mask as `sk-lf-***`), ask whether to update or exit.

## Step 2 — Collect the four values
Use the arguments if provided. For any missing value, ask me directly:
1. **Project name** — used as trace metadata/tag to identify this repo in Langfuse
2. **Public key** — starts with `pk-lf-`
3. **Secret key** — starts with `sk-lf-` (if I pasted it as a command argument, warn me once that CLI args can persist in shell history; suggest interactive entry next time)
4. **Base URL** — my self-hosted instance, e.g. `http://localhost:3000` (local) or `https://langfuse.<my-domain>` (Kubernetes ingress). No trailing slash. For k8s in-cluster use, the service DNS also works: `http://langfuse-web.<namespace>.svc.cluster.local:3000`

Validate formats before proceeding (pk-lf-/sk-lf- prefixes, URL parses). 

## Step 3 — Test the connection BEFORE writing anything
```bash
curl -s -o /dev/null -w "%{http_code}" -u "<PK>:<SK>" "<BASE_URL>/api/public/projects"
```
- `200` → proceed.
- `401/403` → keys wrong or wrong host for these keys. Stop, tell me.
- Connection refused / timeout → instance unreachable. If URL is localhost, suggest checking `docker compose ps`; if k8s, suggest `kubectl get pods -n <ns>` and ingress/port-forward (`kubectl port-forward svc/langfuse-web 3000:3000`). Stop.

## Step 4 — Install (preferred: official plugin)
```bash
claude plugin marketplace add langfuse/Claude-Observability-Plugin
claude plugin install langfuse-observability@langfuse-observability
```
The plugin prompts for LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL and stores the secret in the OS keychain. Requires Python 3.9+ and `pip install "langfuse>=4.0,<5"`.

**Fallback (plugin unavailable — e.g. air-gapped k8s):** PRINT the env config below for the pilot to paste into `.claude/settings.local.json` (NOT settings.json — local file stays out of git). Do NOT write that file yourself: it carries Claude Code's local permissions, and agent writes to it are refused by protect-paths and `permissions.deny` since T-00000750 — the destination is unchanged, the hand that writes it is the pilot's:
```json
{
  "env": {
    "LANGFUSE_PUBLIC_KEY": "<PK>",
    "LANGFUSE_SECRET_KEY": "<SK>",
    "LANGFUSE_BASE_URL": "<BASE_URL>",
    "OTEL_RESOURCE_ATTRIBUTES": "service.name=<PROJECT_NAME>"
  }
}
```
Then follow https://langfuse.com/integrations/developer-tools/claude-code to create and register the Stop-hook script (it converts session transcripts into Langfuse traces grouped by session_id).

## Step 5 — Protect secrets
```bash
grep -q "settings.local.json" .gitignore 2>/dev/null || echo ".claude/settings.local.json" >> .gitignore
```
Confirm to me that the secret key is not in any git-tracked file:
```bash
git grep -l "sk-lf-" -- ':!.claude/settings.local.json' || echo "clean"
```

## Step 6 — Wrap up
- Record in `.agents/ref/DOCS_REGISTRY.md` § observability: `configured: yes — project=<name>, url=<base_url>` (keys NEVER go in the registry).
- Remind me to restart the Claude Code session so hooks/plugin load.
- Tell me where to look: Langfuse UI → Traces (per-turn), Sessions tab (full runs grouped by session_id) — useful to spot repeated file reads and near-duplicate tool calls, i.e. exactly the token waste this kit is designed to avoid.

## Hard rules
- NEVER print the secret key back to me in full, in any output.
- NEVER write keys into CLAUDE.md, DOCS_REGISTRY.md, or any file that could be committed.
- Do not proceed past Step 3 on a failed connection test.

Shared process reference: `.agents/skills/lang/SKILL.md` (Codex/Copilot counterpart). The plugin CLI (`claude plugin …`) and `.claude/settings.local.json` mechanics of Steps 1, 4 and 5 are Claude Code only; this command's cross-host mirror `.agents/skills/source-command-lang/SKILL.md` carries the same process to the other hosts, where those two mechanics do not exist: `.agents/skills/lang/SKILL.md` names the alternative for Codex and Copilot, and for any other host the limitation to state.
