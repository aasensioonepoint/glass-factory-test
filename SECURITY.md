# Security policy

## Reporting a vulnerability

Report a suspected vulnerability privately to the maintainers of this repository, never in a public issue or pull request. Include:

- what is affected (file, guard, hook, host);
- how to reproduce it, as a command and what it printed;
- the impact you expect (a guard bypassed, a secret exposed, code run without consent…).

## What happens next

| Step | Target |
|---|---|
| Acknowledgement | 2 working days |
| Triage, with a severity class (0 secret, 1 code, 2 dependency, 3 pilot decision) | 7 days |
| Fix or mitigation for class 0 and class 1 HIGH/CRITICAL | 14 days |

The classes are the kit's own (`.agents/skills/security-gate/SKILL.md`): a class-0 secret is removed and rotated without exception; a class-1 HIGH or CRITICAL finding in produced code is fixed and is never waived.

## Scope and limits

- The kit's guards (`.claude/hooks/`, `.codex/hooks/`, `.gemini/hooks/`) **prevent forgetting, not cheating**: each one names the forms it does not see. A bypass of a form the guard claims to cover is a vulnerability; a form it names as a bound is not.
- Coverage differs by host (`README-OTHER-HOSTS.md`). A guard that is inert on a host is documented, not a vulnerability.
- Third-party material and its licences: `THIRD_PARTY_NOTICES.md`.
