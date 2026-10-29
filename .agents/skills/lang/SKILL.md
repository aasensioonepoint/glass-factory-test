---
name: lang
description: Configure observability pointers for agent sessions. Use when the user asks for Langfuse, OpenTelemetry, tracing, or session observability.
---

# Observability Workflow

Configure tracing without committing secrets.

## Process

1. Ask for the observability target only if missing:
   - provider name;
   - project name;
   - public key or non-secret identifier;
   - base URL.
2. Never print or commit secret keys.
3. Prefer user-level or environment-level configuration for credentials.
4. Record non-secret status in `.agents/ref/DOCS_REGISTRY.md`:

   ```text
   observability:
     configured: yes
     provider: <provider>
     project: <project>
     url: <base-url>
   ```

5. For Codex, prefer documented OpenTelemetry or host-native tracing settings.
6. For Copilot, prefer GitHub/Copilot usage metrics and agent session logs unless the user has a supported external integration.

## Rules

- Secrets never go into repository files.
- If a connection test fails, stop and report the reason.
- If the host lacks a supported tracing mechanism, document the limitation and use session logs.
