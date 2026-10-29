# Planning traps — read before planning against a guard or a test net

<!-- Shared by Claude Code, Codex, Copilot, Gemini/Antigravity and Kimi Code (one copy).
     Read AT NEED — never injected, never read whole "just in case".
     Referenced from the planner and plan-critic definitions of the five hosts.
     Each entry was measured on a consumer project running a vendored copy of
     this kit: a plan that looked correct on paper, failed on the trap, twice. -->

Two traps break plans that were otherwise sound. They share one shape: the plan
reasons about BEHAVIOUR, while the thing that will fail reasons about TEXT. Both
are cheap to check before planning and expensive to discover after.

## Trap 1 — architecture nets are TEXT analysers with FILE scope

A guard that a net proves is proven WHERE THE NET LOOKS, which is very often a
single named file. Factor that guard out — move it into a shared helper, a base
class, a decorator — and the behaviour is unchanged while the proof is gone: the
net searched the original file and no longer finds anything there. The refactor
is correct and the build is red, which is the worst combination to debug under a
plan already approved.

**Before planning any factorisation of a watched guard**, establish the net's
scope: which file(s) it reads, and whether it follows an import. If the net is
file-scoped, the plan either keeps the guard textually present in the watched
file, or amends the net in the SAME plan — and says which of the two it chose.
A plan that moves a guarded behaviour without naming the net that watches it is
incomplete, not merely risky.

## Trap 2 — some nets pin a VACUITY

A net can assert emptiness: a count equal to zero, a collection asserted equal to
`[]` / `{}`, a "no such case exists yet" assertion. It is a real specification —
it says the zone is deliberately empty — and it is invisible to a plan that only
reads the code the zone contains, because there is none.

**Before planning NEW behaviour in a zone**, search the zone for equality-to-empty
assertions. If one exists, the plan that fills the zone breaks it, and **the net
is right until the plan amends it explicitly**: the emptiness was the contract.
Amending it is legitimate and takes one line in the plan; discovering it during
implementation costs a re-plan, and "just update the expected value" applied
without stating why is how a deliberate emptiness gets deleted by accident.

## Trap 3 — argv translation under Git Bash (a green that proves nothing)

**The shape.** A bash suite writes a payload, hands it to a NATIVE interpreter
(`"$PY" -c … "$PAYLOAD"`), and Git Bash rewrites the argument on the way across
the MSYS boundary. The code under test then receives something the suite never
wrote, asserts on it, and goes GREEN. Measured on this repo: `/bin/rm
secrets.txt` arrived as `C:/Program Files/Git/usr/bin/rm secrets.txt`, so the arm
that claimed to measure an absolute-path verb measured a Windows path instead
(L-00000151).

**When it applies.** Only to a bash suite invoking a native interpreter with the
payload in ARGV. It does NOT apply to a payload built inside Python
(`subprocess.run` from `python.exe` crosses no boundary — measured, T-00000157
§1), nor to a payload passed on STDIN (`printf … | "$PY" -c …`), which is the
safe form and the recommended fallback.

**The exposure criterion is NARROW, and measuring it beats neutralising by
precaution.** Only an argument whose value STARTS with `/` is translated. A JSON
carrying `/etc/passwd` in the middle of it passes intact. So most sites that pass
data are not exposed at all, and adding the two variables there would be
decorative — a neutralisation that suggests coverage where there was nothing to
cover.

**NEVER neutralise globally, and never by a bare `export` at the top of a file
that later calls git.** The same translation is REQUIRED for `git` and for native
Python to receive their own path arguments. Measured: exporting the two variables
across the whole bash suite runner turned 15 of 21 suites red, `git` first among them
(`fatal: cannot change to '/tmp/tmp.…'`, exit 128). The fix is INLINE, at the
site that carries the data payload:
`MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$PY" -c … "$PAYLOAD"`.

**How to check it, and why a grep will not do.** The payload and the argv site
are usually in DIFFERENT lines joined by a function, so a one-line grep near an
interpreter name returns zero on a tree that carries the real case. Follow the
function that builds the payload to the site that passes it, and when in doubt
substitute a receiver that prints its own `sys.argv`. The textual sweep is a
LOCATOR, never the authority.

## How this file is used

- **planner** — consult before any plan touching a guard, a check, or a test net;
  when a trap applies, the plan says which one and how it is handled.
- **plan-critic** — when any of these traps applies to the plan under review, verify the
  plan checked it; an unchecked applicable trap is a finding, cited on the row it
  belongs to (`blast-radius` for trap 1, `test-adequacy` for traps 2 and 3), never a new
  checklist row.
