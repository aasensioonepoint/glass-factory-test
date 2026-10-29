---
description: Check the Jira setup read-only. Usage — /jira
---

# Jira

## Agent run

From the project root, run in this order, even when `status` reports a missing
setup:

```bash
python3 .agents/bin/jira_setup.py status
python3 .agents/bin/jira_setup.py verify
```

Report the local state, the result of the read-only check and every failure
separately. Never ask for, receive, print or write a token. The former French
verb names (`etat`, `verifier`) are still accepted.

## Command for the pilot's terminal

To set up or redo the Jira setup, switch project or replace the token, give the
pilot this command to type in **their own terminal**:

```text
python3 .agents/bin/jira_setup.py configure
```

To replace a token already present on purpose, point them to the
`--change-token` option (former name `--changer-jeton`, still accepted; the
verb's former name `configurer` too). The agent never runs `configure` (nor `configurer`),
with or without that option, even when the `/jira` request is about the setup.

Shared process reference: `.agents/skills/jira/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
