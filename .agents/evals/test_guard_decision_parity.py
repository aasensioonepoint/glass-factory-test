"""Cross-host DECISION parity for the two Bash guards (T-00000151).

test_events_parity.py already pins the SHAPE of what a denial writes. This suite
pins the DECISION itself: one command in, allow-or-deny out, replayed on the
three hosts that wire these guards —

  claude -> .claude/hooks/safe-bash.sh + audit-gate.sh   (bash; deny = exit 2)
  codex  -> .codex/hooks/safe_bash.py + audit_gate.py    (python; deny = a
  gemini -> .gemini/hooks/*.py                            permissionDecision
                                                          body on stdout, rc 0)

(copilot executes the .codex files verbatim — L-006 — so it is covered by the
codex column and is not replayed a third time.)

WHY A MATRIX AND NOT MORE UNIT TESTS. Each host's colocated suite tests its own
guard against its own expectations, which is exactly how the two families drifted:
the python hosts gated `pnpm dlx` without its options, knew nothing of `yarn dlx`
or `bunx`, and read a `rm` sitting inside a QUOTED task title as an execution.
None of that is visible from inside one host. A row here is a claim about all
three at once, so a divergence has to be either FIXED or NAMED — it cannot be
merely local any more.

DIVERGENCES ARE DATA, NOT FAILURES — but only when they are WRITTEN DOWN. Every
row whose expectation is not uniform carries the reason in its note, and each was
MEASURED on both hosts rather than predicted (four of them were predicted wrong
while this file was being written, which is the whole argument for measuring):

  1. A QUOTED VERB (`"rm" -rf x`, `r"m" -rf x`, `sudo "rm" -rf x`) — CLOSED by
     T-01M5D6XS2S, and this entry stays because the closing is what the rows now
     assert. The python hosts read the verb from the SHLEX tokens of the raw
     segment; the Claude hook replaced a quoted run by a fixed ` @@ ` token, which
     destroyed the verb, until it read the command word with its quotes removed:
     the three `quoted/verb-*` rows, PY_STRICTER until then, are UNIFORM DENY.
  2. The POWERSHELL VERBS (`del`, `erase`, `Remove-Item`, `Move-Item`) are known
     to the python hosts only. PYTHON IS STRICTER.
  3. UNSCOPED GIT WIPE — CLOSED by T-00000762, and this entry stays because the
     closing is what the rows now assert. `git restore .` and `git clean -fdx`
     used to be guarded on Claude only (the python hosts did not even refuse
     `git checkout .`), and the two `git-wipe/` rows that pinned that ABSENCE as
     `CLAUDE_STRICTER` are UNIFORM DENY now: `judge_git` ports `decide_git` rule
     for rule to both python bridges, together with the two new subcommands
     (`reset --hard`, `stash` without a pathspec) and the two new guards on the
     same tokens (`--output`, `git grep -O`). THE PINNING WORKED — it is why
     the port had to flip those rows explicitly instead of drifting past them.
  4. The TEMP ALLOWLISTS ARE DIFFERENT LISTS, and they disagree in BOTH
     directions: Claude judges each OPERAND against an ANCHORED list (strictly
     under `/tmp/` or its RESOLVED form — `/private/tmp/` on macOS, computed —
     or a relative path whose first component is `.tmp`, `node_modules`,
     `dist`, `build`, `.cache`, and that git does not track; T-00000762 replaced
     the raw-substring match) while the python hosts match a repo-relative
     PREFIX (`tmp/`, `temp/`, `.tmp/`, `dist/`, `build/`, `coverage/`,
     `node_modules/`, `.next/`). The `allowlist/` rows enumerate the lists one
     target each rather than summarising, because a list-versus-list difference
     is invisible to any single example, and a few per-operand rows land on the
     same difference (a `/tmp` operand). NEITHER HOST IS STRICTER — it depends on
     the target. This is pre-existing and is documented here, not repaired: the
     lists are policy, and unifying them is a decision, not a bug fix. The
     `/private/tmp` rows have a PLATFORM-COMPUTED expectation: the resolved
     anchor is `/private/tmp/` on macOS (Claude allows, `PY_STRICTER`) and
     coincides with `/tmp/` on Linux (Claude refuses, `DENY`); the Linux branch
     is exercised by the ubuntu leg of CI, not by a local macOS gate.
  5. An ESCAPED QUOTE (`echo \\" ; rm -rf src/x \\"`) — CLOSED, and this entry stays because
     the closing is what the rows now assert. `\\"` is a LITERAL quote in bash, so a stage 1
     that reads it as an opening delimiter masks the whole interval between two of them —
     separator and destructive command included — and allows a payload the shell really
     executes. It was an OPEN class-1 BYPASS on the Claude host, reproduced by T-00000151's
     security review on BOTH guards (an `rm -rf` and an unaudited skill install), and it
     lived here for exactly one revision: the python hosts closed it with a backslash-aware
     scanner (quoted_spans, in either module) while .claude/hooks/safe-bash.sh and
     audit-gate.sh kept a one-pass sed that could not express escaping and were outside that
     task's authorised files. Those four rows were pinned to the MEASURED — divergent —
     verdicts so that they would FAIL, loudly, the day the Claude side was repaired.
     T-00000181 repaired it: both bash guards now run the same scanner as an inline python
     program, so the four rows are UNIFORM DENY and the divergence is gone. THAT PORT WAS
     PER-LINE, AND SAYING SO HERE HAS SINCE BECOME FALSE IN THE REPOSITORY: T-00000208 moved
     the scan to the WHOLE TEXT on every host, because in bash a quoted segment PAIRS ACROSS
     A NEWLINE. A per-line scanner read the second line's two orphan apostrophes as a pair
     of its own and neutralised everything between them — a `rm` the shell really executes
     included. The `inversion/quote-pairs-across-the-newline` row below is that measured
     payload, and it is the row a return to per-line scanning fails on. What survives is the
     CONTROL below it (`even-backslash-is-a-real-quote`, ALLOW on all three): an EVEN run of
     backslashes leaves the quote free to open a genuine segment, and without that row the
     fix could have been "ignore backslashes entirely", which would refuse well-formed data.
     THE PINNING WORKED — it is why this section reads `closed` instead of describing a hole
     nobody noticed.
  (6. The CREDENTIAL LISTS of the write-redirect guard — CLOSED by T-00000721,
     and this entry stays because the closing is what the rows now assert.
     `id_rsa` was refused on Claude only, `.key` and `.envrc` on the Python hosts
     only; the lists are aligned token for token since, and the three
     `redirect/credential-*` rows that pinned the divergence are UNIFORM DENY.
     THE PINNING WORKED — they went red on the flip, and were flipped by hand.)
  7. A QUOTED GIT WORD — from the SAME root as 1: the python hosts read a git
     word through its quotes, Claude's scrub turns it into `@@`. Its first
     statement ("the port introduces ONE divergence", a quoted PATHSPEC) was an
     UNDER-COUNT, measured by the closing pair of T-00000762: four more rows, a
     quoted OPTION or SUBCOMMAND (`git reset "--hard"`, `git log "--output=x"`,
     `git grep "-O" x`, `git "stash"`), refused on the python hosts and
     allowed on Claude, divergent BY DECISION (S-00002513, decision 4: reading
     them would cost Claude a python spawn per git command) — décision 4
     resserrée pour reset seul par T-01M5D6XS2S: `git reset "--hard"` is UNIFORM
     DENY. The PATHSPEC half is CLOSED (decision 1): the Claude awk reads the
     CONTENT of a quoted span from the raw payload (`git checkout -- "."`).
     PYTHON IS STRICTER on the three that remain (`--output`, `-O`, `git "stash"`), and on a quoted, glued or backslashed `git branch` delete option (`'-D'`, `-"D"`, `\\-D`: a gap on Claude, carried by T-00001202).
  8. A WORD THAT IS NOT AN OPERAND read as one — the python hosts read a
     redirect glued to an rm operand (`rm -rf dist/x 2>/dev/null`), a trailing
     comment (`rm -rf build/x # src/a.py`) and the `)` of a subshell (`( rm -rf
     .tmp/x )`) as TARGETS, outside their list, and refuse; Claude's
     per-operand pass (T-00000762) drops a redirect with its target and stops
     its slice at an unquoted ` #` and at an unnested `)`. PYTHON IS STRICTER.
     Pre-existing on the python side and NOT corrected by T-00000762 (its plan
     and its closing decisions keep it out of scope); carried by T-00000764.
  9. AN rm OPERAND ENDING IN `/` — CLOSED by T-00000762 (S-00002513, decision
     6), and this entry stays because the closing is what the rows now assert.
     The python hosts' `_ROOT_RM` regex read ANY operand ending in `/` as the
     root (`rm -rf ./node_modules/` refused as CATASTROPHIC) and
     `is_allowed_target` refused the listed directory itself (`rm -rf dist`);
     the regex now wants a BARE `/` and the directory is inside its own list,
     so those rows are UNIFORM ALLOW.
  10. A WORD GLUED TO A QUOTED SPAN in a forced `git branch` delete (`git branch -D feat-"old"`, `--sort="x"`; in
      `"$b"-D` the awk also reads the glued `-D`), and every quoted word once the command holds a literal `@@` (the awk's
      own mark, `qv` off): the awk cannot read that word whole (`bglue`) and counts it as `wt/`; the python hosts read it
      through its quotes and let a non-wt name pass, and `"$b"-D wt/…` too (a gap there, T-00001202). CLAUDE IS STRICTER, fail-closed, NAMED in the refusal (T-00001090).

ASSUMED HOLES, pinned so that closing one FAILS here and gets noticed:
  - a verb nested inside a quoted payload (`bash -c "rm -rf x"`) is invisible to
    every host (`sh`/`bash` are deliberately not envelopes);
  - behind an envelope OUTSIDE the tables only rm/mv fall back to substring semantics
    (`timeout 5 <absent>/rg` passes, S1); behind a TABLE envelope git IS read and
    `sudo git rm <tracked>` passes behind a PROVEN chain only, since T-00001102 —
    detail, and `env -v` (S5), in guard_parity_gitenv_rows.py.

FAILURE SEMANTICS, deliberately harsh. An unreachable host is a FAILURE, never a
skip: a python leg that exits non-zero, a Claude leg that exits anything but 0/2,
and — the one that matters most — a Claude leg printing `COVERAGE DEGRADED` all
raise, because a guard that did not run returns "allow" and would read as a
passing row. The only skip in this file is the Claude column when there is no
bash on PATH (a Windows dev box), and it is a REPORTED skip covered by
`verify.sh --linux`. The matrix's own size is asserted too, so an empty or
truncated table cannot pass vacuously.
"""
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from guard_parity_gitenv_rows import gitenv_rows

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VP = importlib.util.spec_from_file_location("_gdp_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
_VP = sys.modules[_SPEC_VP.name] = importlib.util.module_from_spec(_SPEC_VP)
_SPEC_VP.loader.exec_module(_VP)  # `cadre` résolu vendor d'abord (S-01M5BXT85VP4JBBMXVXR9STP5F)

# On Windows a bare "bash" resolved by CreateProcess can hit the WSL relay shim
# in System32 (searched before PATH) instead of Git Bash. Pin it the way
# test_events_parity.py does, so the Claude leg is honoured on the ubuntu runner
# and on a Windows dev box alike.
BASH = shutil.which("bash")

PY_HOSTS = {"codex": ".codex", "gemini": ".gemini"}
HOSTS = ("claude", "codex", "gemini")

CLAUDE_SCRIPT = {"safe_bash": "safe-bash.sh", "audit_gate": "audit-gate.sh"}
HOOK_MODULES = (
    "protect_paths", "safe_bash", "audit_gate", "post_edit_check",
    "stale_index", "pre_compact_backup", "session_context", "log_agent_usage",
)
COMMON_FILES = ("_common.py", "safe_bash_git.py", "safe_bash_hooks.py") + tuple(f"{m}.py" for m in HOOK_MODULES)

# A path that cannot exist, used as the `rg` token. Preferred over emptying PATH:
# the Claude hook needs python+sed+awk ON PATH to read its payload at all, so a
# stripped PATH makes it degrade and prove nothing, while an unresolvable
# ABSOLUTE token exercises the same branch on all three hosts with no dependence
# on what happens to be installed.
ABSENT_RG = "/nonexistent-guard-probe-zz/rg"

# Deny motives, asserted on deny rows so that a row cannot pass by denying for
# the WRONG reason (an rg row satisfied by the rm/mv guard would be a false
# green). Substrings common to both hosts' wordings.
MOTIVE_ROOT = "refusing catastrophic rm"
MOTIVE_RG = "does not resolve on this machine"
MOTIVE_CHECKPOINT = "checkpoint"
MOTIVE_AUDIT = "audit gate"
# The git-wipe guard has its OWN motive, and asserting it is what proves its rows
# are refused by that guard rather than by the rm/mv one reaching further: its
# message is about destroying uncommitted work, not about rewind. Claude-only
# until T-00000762 (DIVERGENCE 3, now closed); the same word on all three hosts.
MOTIVE_GITWIPE = "unscoped"
# The two guards T-00000762 adds on the same git tokens, each with its own
# motive: a `--output` row satisfied by the git-wipe guard would be a false green.
MOTIVE_GITOUTPUT = "--output"
MOTIVE_GITPAGER = "open-files-in-pager"
# The rm/mv refusal of a verb with NO operand or FED BY A PIPE (T-00000762). It
# is also a "checkpoint" refusal, but `find … {} \;` is refused by shlex on the
# python hosts as well, so a row satisfied by the quoting would stay green under
# a mutant that drops the `fed` flag: this phrase is what the pipe rows assert.
MOTIVE_PIPE = "come from a pipe"
# The fail-closed arm of the three git guards (T-00000762, decision 3): an
# unquoted expansion where git reads its subcommand. Its own rule
# (git-subcommand-hidden) and its own phrase, identical on the three hosts.
MOTIVE_GITHIDDEN = "where git reads its subcommand"
# The write-redirect guard's OWN motive (T-00000244): a row satisfied by the
# rm/mv or git-restore guard would be a false green, so the deny rows below assert
# this phrase, which only the redirect guard's message carries.
MOTIVE_REDIRECT = "redirects a write"
# The python hosts' refusal of a command with no faithful byte form (a NUL or a
# lone surrogate, T-00000785, rule unrepresentable-command). Claude has no such
# refusal — its payload read drops the NUL and judges what is left — so rows
# carrying it pin this phrase on the python hosts only, through a per-host
# motive dict.
MOTIVE_UNREPRESENTABLE = "no faithful byte form"

DENY = {"claude": True, "codex": True, "gemini": True}
ALLOW = {"claude": False, "codex": False, "gemini": False}
PY_STRICTER = {"claude": False, "codex": True, "gemini": True}
CLAUDE_STRICTER = {"claude": True, "codex": False, "gemini": False}

# Envelopes and keywords, one deny row each: these pin safe-bash.sh's awk table (`split(…)`)
# and safe_bash_git.py `ENVELOPES`; for chrt, taskset, builtin, timeout its brace and operand
# tables are pinned by `envtable/*` (guard_parity_gitenv_rows.py). An earlier port listed
# five, which would have turned `nohup rm -rf src/x` into a silent allow on three hosts.
ENVELOPES = (
    "sudo", "doas", "env", "command", "exec", "eval", "time", "nohup", "nice", "ionice",
    "stdbuf", "timeout", "xargs", "watch", "parallel", "setsid", "chrt", "taskset", "builtin",
)
KEYWORDS = ("if", "then", "elif", "else", "do", "while", "until", "!", "coproc")


def row(label, guard, command, expected, note, motive=MOTIVE_CHECKPOINT, env=None):
    return {
        "label": label, "guard": guard, "command": command, "expected": expected,
        "note": note, "motive": motive, "env": env or {},
    }


def build_matrix():
    rows = []

    # -- the receiver: every envelope, every keyword -------------------------
    for envelope in ENVELOPES:
        rows.append(row(
            f"envelope/{envelope}", "safe_bash", f"{envelope} rm -rf src/x", DENY,
            "an envelope takes a command, so the position of command stays open behind it",
        ))
    rows.append(row(
        "envelope/timeout+own-arg", "safe_bash", "timeout 5 rm -rf src/x", DENY,
        "envelope with its OWN argument: nobody can tell where it stops, so rm/mv "
        "fall back to substring semantics inside that window",
    ))
    for keyword in KEYWORDS:
        rows.append(row(
            f"keyword/{keyword}", "safe_bash", f"{keyword} rm -rf src/x", DENY,
            "a keyword does not close the position of command",
        ))

    # -- the three motives, and the shape of the verb ------------------------
    rows += [
        row("root/exact", "safe_bash", "rm -rf /", DENY,
            "root EXACTLY is the catastrophic form", motive=MOTIVE_ROOT),
        row("verb/plain", "safe_bash", "rm -rf src/x", DENY, "the baseline refusal"),
        row("verb/path", "safe_bash", "/bin/rm -rf src/x", DENY, "the verb's path is stripped"),
        row("verb/exe", "safe_bash", "rm.exe -rf src/x", DENY, "the verb's extension is stripped"),
        row("verb/escaped", "safe_bash", "\\rm -rf src/x", DENY,
            "`\\rm` bypasses an alias, not this guard"),
        row("verb/assignment-prefix", "safe_bash", "FOO=bar rm -rf src/x", DENY,
            "an assignment does not close the position of command"),
        row("verb/find-exec", "safe_bash", "find src -type f -exec rm -rf src/x ;", DENY,
            "-exec reopens a position of command"),
        row("verb/not-a-subcommand", "safe_bash", "docker rm container", ALLOW,
            "`docker rm` is not an rm: substring matching used to refuse it"),
        row("verb/git-rm", "safe_bash", "git rm -q docs/tasks/T-002.md", ALLOW,
            "git rm stages a recoverable change — rewindable via git, out of scope"),
        row("verb/git-rm-then-real-rm", "safe_bash",
            "git rm -q docs/tasks/T-002.md ; rm -rf src/x", DENY,
            "the second segment is a real rm and must not be masked by the first"),
        row("verb/sudo-git-rm", "safe_bash", "sudo git rm -q docs/tasks/T-002.md", ALLOW,
            "T-00001102, the ONLY refusal lifted: git behind a PROVEN envelope chain is git, "
            "so `git rm` passes like the bare form; other windows keep it (gitenv/kept-*)"),
        row("verb/install-named-ripgrep", "safe_bash", "sudo apt install ripgrep", ALLOW,
            "the envelope-window fallback is restricted to rm/mv precisely so this "
            "stays allowed"),
    ]

    # -- stage 1 + 2: a quoted mention is DATA -------------------------------
    rows += [
        row("quoted/title-multiword", "safe_bash",
            'python .agents/bin/tasks.py new "corriger le garde: rm -rf src/x refuse"', ALLOW,
            "a board title QUOTING a destructive command is data; refusing it lost a "
            "board write in session"),
        row("quoted/title-single-word", "safe_bash",
            'python .agents/bin/tasks.py new "rm"', ALLOW,
            "the single-word case: a quoted run must not be readable as a verb even "
            "when it is exactly one"),
        row("quoted/title-root-rm", "safe_bash",
            'python .agents/bin/tasks.py new "rm -rf /"', ALLOW,
            "the catastrophic form, quoted, is still only a mention"),
        row("quoted/separator-inside-quotes", "safe_bash",
            'python .agents/bin/tasks.py new "titre; rm -rf src/x"', ALLOW,
            "a `;` INSIDE quotes must not fabricate a segment boundary — the reason "
            "the scrub has to be isometric"),
        row("quoted/title-then-real-rm", "safe_bash",
            'python .agents/bin/tasks.py new "clean title" ; rm -rf src/x', DENY,
            "the converse: a real separator AFTER a quoted title still cuts, so the "
            "rm is seen"),
        row("quoted/ledger-single-quotes", "safe_bash",
            "python .agents/bin/ledger.py add --category lesson 'rm -rf src/x est refuse'",
            ALLOW, "single quotes neutralise the same way"),
        row("quoted/unpaired-apostrophe", "safe_bash", "echo l'index && rm -rf src/x", DENY,
            "an unpaired quote closes nothing and must not swallow the real command"),
        row("quoted/verb-fully-quoted", "safe_bash", '"rm" -rf src/x', DENY,
            "DIVERGENCE 1, CLOSED by T-01M5D6XS2S: the shell runs this; every host reads "
            "the verb through the quotes (Claude's fixed-token scrub destroyed it)"),
        row("quoted/verb-partially-quoted", "safe_bash", 'r"m" -rf src/x', DENY,
            "DIVERGENCE 1, CLOSED, harder form: the quotes sit INSIDE the word"),
        row("quoted/verb-quoted-under-envelope", "safe_bash", 'sudo "rm" -rf src/x',
            DENY, "DIVERGENCE 1, CLOSED, under an envelope"),
        row("quoted/nested-payload", "safe_bash", 'bash -c "rm -rf src/x"', ALLOW,
            "ASSUMED HOLE, shared: closing it needs a nested-command parser, not a "
            "wider pattern"),
        # The gap that let a class-1 bypass through this very matrix: 95 green rows
        # and not one of them put a BACKSLASH in front of a quote.
        row("quoted/escaped-quote-masks-separator", "safe_bash",
            'echo \\" ; rm -rf src/x \\"', DENY,
            "DIVERGENCE 5, CLOSED by T-00000181: `\\\"` is a LITERAL quote, so bash "
            "really runs the rm and every host must refuse it. It was a class-1 bypass "
            "on the Claude host alone — its one-pass sed read the two escaped quotes as "
            "one quoted string spanning separator AND verb, so stage 2 cut nothing. "
            "safe-bash.sh now runs the same backslash-aware scanner as the python "
            "hosts and the divergence is gone. NOT per-line, and the correction "
            "matters: T-00000208 moved that scan to the WHOLE TEXT on every host, "
            "because a quote pairs ACROSS a newline in bash — see the "
            "`inversion/` row below"),
        row("quoted/escaped-single-quote-masks-separator", "safe_bash",
            "echo \\' ; rm -rf src/x \\'", DENY,
            "DIVERGENCE 5, single-quote form: same bypass, closed the same way by "
            "T-00000181 — outside quotes a backslash escapes the next character "
            "whichever quote follows it"),
        row("quoted/even-backslash-is-a-real-quote", "safe_bash",
            'echo \\\\" ; rm -rf src/x \\\\"', ALLOW,
            "THE CONTROL for the two rows above: an EVEN run of backslashes leaves the "
            "quote free to open a genuine segment, so bash executes nothing here and "
            "every host is RIGHT to allow. Without this row the fix could have been "
            "'ignore backslashes entirely', which would refuse well-formed data"),
        row("verb/escaped-quotes-around-target", "safe_bash", 'rm -rf \\"src/x\\"', DENY,
            "escaped quotes around the TARGET change nothing: the verb is still in a "
            "position of command on every host"),
    ]

    # -- the WHOLE-TEXT scanner, and the heredoc stage -----------------------
    # Four rows added by T-00000211. Each was MEASURED on the three hosts before
    # being written here — the first two pin T-00000208's move off per-line
    # scanning, the last two pin the heredoc stage that this task ported from
    # .claude/hooks/safe-bash.sh to the two python hosts.
    rows += [
        row("inversion/quote-pairs-across-the-newline", "safe_bash",
            "echo 'a\nb' && rm -rf src/x && echo 'x'", DENY,
            "THE INVERSION PROBE, and the killing mutant of a return to per-line "
            "scanning. Bash opens a single-quoted segment on line 1 and closes it on "
            "line 2 — quoting crosses the newline — so what follows is NAKED CODE that "
            "the shell executes, and the trailing `'x'` is a second quoted segment. A "
            "per-line scanner saw only two orphan apostrophes on line 2, paired them "
            "with each other, and blanked the `rm` between them: ALLOW, a broken "
            "checkpoint without a word. UNIFORM DENY since T-00000208"),
        row("inversion/control-continued-string-is-one-argument", "safe_bash",
            'echo "unterminated \\"\nrm -rf src/x "', ALLOW,
            "THE CONTROL for the row above, and its expectation is DERIVED FROM BASH "
            "rather than from suite comfort: the `\\\"` is an ESCAPED quote INSIDE the "
            "double-quoted segment opened on line 1, so it closes nothing and the "
            "string runs on to the final `\"` of line 2. The whole thing is ONE "
            "argument to `echo`; bash deletes nothing, no checkpoint is at risk, and "
            "every host is right to allow. Without this row, 'scan the whole text' "
            "could degrade into refusing any payload that spans a newline"),
        row("heredoc/quoted-delimiter-body-is-data", "safe_bash",
            "git commit -F - <<'MSG'\nrm -rf src/x est desormais refuse\nMSG", ALLOW,
            "THE FOUNDING INCIDENT of the heredoc stage, third of its kind: a commit "
            "message DESCRIBING a guarded command was refused. A heredoc body is not "
            "QUOTED, it is REDIRECTED, so no quote-scanning stage can reach it — it "
            "takes a stage of its own, running BEFORE them. It was UNIFORM DENY until "
            "T-00000211 ported that stage to the two python hosts, where it was simply "
            "absent; it is UNIFORM ALLOW now"),
        row("heredoc/backslash-delimiter-is-quoted", "safe_bash",
            "cat <<\\EOF > notes.md\nrm -rf src/x est desormais refuse\nEOF", ALLOW,
            "THE PIECE PARSER, which is what the row above alone would not pin. Bash "
            "builds the delimiter word by CONCATENATING pieces and then removing the "
            "quotes, so `<<\\\\EOF` is a QUOTED delimiter exactly like `<<'EOF'` and its "
            "body is 100% literal. The regex this parser replaced (T-00000210) admitted "
            "one fully quoted piece only, missed this form, and left its body ANALYSED — "
            "a false positive on pure DATA. The POLARITY that must never flip with it is "
            "the NAKED delimiter `<<EOF`, whose body bash EXPANDS: that one stays "
            "analysed on every host, and it is pinned in each colocated suite"),
    ]

    # -- command position reopened by a metacharacter ------------------------
    rows += [
        row("cmdpos/substitution", "safe_bash", "$(rm src/x)", DENY,
            "a command substitution reopens a position of command"),
        row("cmdpos/backtick", "safe_bash", "`rm src/x`", DENY, "same, backtick form"),
    ]

    # -- dissolved targets: fail-closed --------------------------------------
    rows += [
        row("dissolved/home", "safe_bash", "rm -rf $HOME", DENY,
            "no literal prefix at all: refused rather than judged on nothing"),
        row("dissolved/braced", "safe_bash", "rm -rf ${DIR}", DENY, "same, braced form"),
        row("dissolved/substitution-in-target", "safe_bash", "rm -rf $(pwd)/src", DENY,
            "the expansion is the whole prefix"),
        row("dissolved/literal-prefix-survives", "safe_bash", "rm -rf tmp/$USER",
            CLAUDE_STRICTER,
            "DIVERGENCE 4 (C16): python judges the LITERAL prefix `tmp/` and allows; "
            "Claude's substring list wants `/tmp/` with a leading slash and refuses"),
        row("tokenise/line-continuation", "safe_bash", "rm -rf src \\", DENY,
            "shlex REFUSES a trailing backslash; the whitespace retry is a guess, so "
            "a verb recognised there is refused"),
    ]

    # -- the temp allowlists, list against list ------------------------------
    for target, expected in (
        ("tmp/x", CLAUDE_STRICTER),
        ("/tmp/x", PY_STRICTER),
        ("temp/x", CLAUDE_STRICTER),
        (".tmp/x", ALLOW),
        ("dist/x", ALLOW),
        ("build/x", ALLOW),
        ("coverage/x", CLAUDE_STRICTER),
        ("node_modules/x", ALLOW),
        (".next/x", CLAUDE_STRICTER),
        (".cache/x", PY_STRICTER),
        ("/tmp/../etc/x", DENY),
    ):
        rows.append(row(
            f"allowlist/{target}", "safe_bash", f"rm -rf {target}", expected,
            "DIVERGENCE 4: measured against BOTH allowlists, one row per target "
            "(the last one is the traversal disqualifier, refused on both)",
        ))

    # -- the PowerShell verbs and the git-restore guard ----------------------
    rows += [
        row("ps-verb/del", "safe_bash", "del src/x", PY_STRICTER,
            "DIVERGENCE 2: python-only verb"),
        row("ps-verb/erase", "safe_bash", "erase src/x", PY_STRICTER,
            "DIVERGENCE 2: python-only verb"),
        row("ps-verb/remove-item", "safe_bash", "Remove-Item -LiteralPath src/x -Force",
            PY_STRICTER, "DIVERGENCE 2: python-only verb"),
        row("git-wipe/restore-dot", "safe_bash", "git restore .", DENY,
            "DIVERGENCE 3, CLOSED by T-00000762: this row pinned the guard's ABSENCE on "
            "the python hosts (CLAUDE_STRICTER) until judge_git ported decide_git",
            motive=MOTIVE_GITWIPE),
        row("git-wipe/clean", "safe_bash", "git clean -fdx", DENY,
            "DIVERGENCE 3, CLOSED by T-00000762: same flip, same port",
            motive=MOTIVE_GITWIPE),
    ]

    # -- T-00000762: the git wipe extended, `--output`, `git grep -O` --------
    # Every probe of the plan's step 4 that needs no fixture of its own is a row
    # here, UNIFORM except DIVERGENCE 4 (the lists), 7 (a quoted option or
    # subcommand, by decision) and 8 (a word that is not an operand) — the plan
    # predicted 4 and 7 only; 8 and 9 were MEASURED, pre-existing on the python
    # side, and 9 is closed since. Measured on the three hosts after the port; before it
    # the DENY rows were ALLOW on all three (reset/stash/--output/-O) or on the
    # python hosts (`git checkout .`).
    for label, command in (
        ("reset-hard", "git reset --hard"),
        ("reset-hard-head", "git reset --hard HEAD"),
        ("reset-hard-head-1", "git reset --hard HEAD~1"),
        ("reset-hard-origin", "git reset --hard origin/main"),
        ("reset-hard-other-repo-C", "git -C /tmp/jetable reset --hard"),
        ("reset-hard-after-cd", "cd /tmp/jetable && git reset --hard"),
        ("reset-hard-sudo", "sudo git reset --hard"),
        ("stash-bare", "git stash"),
        ("stash-push", "git stash push"),
        ("stash-u", "git stash -u"),
        ("stash-save", "git stash save wip"),
        ("stash-push-message-only", 'git stash push -m "wip"'),
        ("stash-k", "git stash -k"),
        ("stash-push-broad-dot", "git stash push -- ."),
        ("stash-push-bare-expansion", "git stash push -- $f"),
        ("work-tree-value-skipped", "git --work-tree /x checkout ."),
        ("git-dir-value-skipped", "git --git-dir /x/.git restore ."),
    ):
        rows.append(row(
            f"git-wipe/{label}", "safe_bash", command, DENY,
            "an unscoped wipe of the uncommitted work of every agent (T-00000762): "
            "GLOBAL scope, like the checkout rule — the text does not say where a cd or "
            "-C lands; a bare `$f` is an UNQUOTED expansion, read as a broad pathspec on "
            "every host (it may split, glob or be empty)",
            motive=MOTIVE_GITWIPE,
        ))
    for label, command in (
        ("reset-soft", "git reset --soft HEAD~1"),
        ("reset-path", "git reset HEAD -- src/x"),
        ("reset-mixed", "git reset"),
        ("reset-keep", "git reset --keep"),
        ("reset-merge", "git reset --merge"),
        ("stash-push-path", "git stash push -- src/x"),
        ("stash-push-message-and-path", 'git stash push -m "wip" -- src/x'),
        ("stash-implicit-path", "git stash -- src/x"),
        ("stash-push-quoted-expansion", 'git stash push -- "$f"'),
        ("stash-list", "git stash list"),
        ("stash-show", "git stash show -p"),
        ("stash-pop", "git stash pop"),
        ("stash-apply", "git stash apply"),
        ("stash-drop", "git stash drop"),
        ("stash-clear", "git stash clear"),
    ):
        rows.append(row(
            f"git-wipe/{label}", "safe_bash", command, ALLOW,
            "scoped, tree-preserving, or a stash subcommand that is never refused "
            "(T-00000762): the guard is bounded to the ABSENCE of a pathspec",
            motive=MOTIVE_GITWIPE,
        ))
    rows += [
        row("git-wipe/known-gap-behind-nice", "safe_bash", "nice -n 10 git reset --hard", ALLOW,
            "KNOWN GAP, shared (S1): behind an envelope OUTSIDE the tables only rm/mv fall "
            "back to substring semantics, so git is not read there", motive=MOTIVE_GITWIPE),
        row("git-wipe/checkout-quoted-dot", "safe_bash", 'git checkout -- "."', DENY,
            "DIVERGENCE 7, pathspec half CLOSED by T-00000762 (decision 1): this row was "
            "PY_STRICTER until the Claude awk read the CONTENT of a quoted span from the "
            "raw payload", motive=MOTIVE_GITWIPE),
        row("git-wipe/stash-quoted-dot", "safe_bash", 'git stash push -- "."', DENY,
            "DIVERGENCE 7, pathspec half CLOSED: same flip, on the stash branch",
            motive=MOTIVE_GITWIPE),
        row("git-quoted/reset-hard-option", "safe_bash", 'git reset "--hard"', DENY,
            "DIVERGENCE 7 for reset: S-00002513 décision 4 resserrée pour reset seul par "
            "T-01M5D6XS2S — the quoted option is read through its quotes on every host", motive=MOTIVE_GITWIPE),
        row("git-quoted/log-output-option", "safe_bash", 'git log "--output=x"', PY_STRICTER,
            "DIVERGENCE 7, by decision: the quoted --output", motive=MOTIVE_GITOUTPUT),
        row("git-quoted/grep-O-option", "safe_bash", 'git grep "-O" x', PY_STRICTER,
            "DIVERGENCE 7, by decision: the quoted -O", motive=MOTIVE_GITPAGER),
        row("git-quoted/stash-subcommand", "safe_bash", 'git "stash"', PY_STRICTER,
            "DIVERGENCE 7, by decision: a quoted SUBCOMMAND", motive=MOTIVE_GITWIPE),
    ]
    rows += gitenv_rows(row, ALLOW, DENY, PY_STRICTER, MOTIVE_GITWIPE, MOTIVE_GITOUTPUT, MOTIVE_CHECKPOINT)
    for label, command in (
        ("show-tracked", "git show --output=README.md HEAD"),
        ("log-equals", "git log --output=/tmp/x -1"),
        ("log-separated", "git log --output /tmp/x"),
        ("diff", "git diff --output=f"),
        ("stash-show", "git stash show --output=f"),
        ("archive", "git archive --output=x.tar HEAD"),
    ):
        rows.append(row(
            f"git-output/{label}", "safe_bash", command, DENY,
            "`--output` writes a file around Edit/Write, whatever the subcommand "
            "(T-00000762, decision 3)", motive=MOTIVE_GITOUTPUT,
        ))
    rows += [
        row("git-output/indicator-is-another-option", "safe_bash",
            "git log --output-indicator-new=x -1", ALLOW,
            "EXACT match: `--output-indicator-*` writes nothing", motive=MOTIVE_GITOUTPUT),
        row("git-output/after-dashdash-is-a-path", "safe_bash", "git log -- --output", ALLOW,
            "after `--` it is a pathspec, not an option", motive=MOTIVE_GITOUTPUT),
        row("git-output/known-gap-archive-o", "safe_bash", "git archive -o x.tar HEAD", ALLOW,
            "KNOWN GAP, shared: `-o` is never read (its meaning changes per subcommand); "
            "`git archive -o`, `git bundle create`, `git config --file` are carried by "
            "T-00000764", motive=MOTIVE_GITOUTPUT),
    ]
    for label, command in (
        ("O-value", "git grep -O'sh -c id' foo"),
        ("O-bare", "git grep -O foo"),
        ("O-glued", "git grep -Ovim foo"),
        ("nO-cluster", "git grep -nO foo"),
        ("iO-cluster", "git grep -iO foo"),
        ("long", "git grep --open-files-in-pager=less foo"),
        ("abbrev-open", "git grep --open=x foo"),
        ("abbrev-op", "git grep --op=x foo"),
    ):
        rows.append(row(
            f"git-pager/{label}", "safe_bash", command, DENY,
            "`git grep` opening a pager runs an arbitrary command (T-00000762, decision 4)",
            motive=MOTIVE_GITPAGER,
        ))
    rows += [
        row("git-pager/e-value-is-a-pattern", "safe_bash", "git grep -e Ofoo", ALLOW,
            "the value of an isolated -e is a pattern: nothing runs", motive=MOTIVE_GITPAGER),
        row("git-pager/o-is-only-matching", "safe_bash", "git grep -o foo", ALLOW,
            "case sensitive: -o is --only-matching", motive=MOTIVE_GITPAGER),
        row("git-pager/or-is-not-open", "safe_bash", "git grep --or -e a -e b", ALLOW,
            "`--or` does not begin open-files-in-pager", motive=MOTIVE_GITPAGER),
    ]

    # -- T-00000762: rm/mv judged OPERAND BY OPERAND -------------------------
    # Claude used to compare its list by SUBSTRING of the whole command, so one
    # allowlisted operand carried every other one (`rm src/x /tmp/x`). The
    # probes with a fixture of their own (the tracked-file veto, a symlink out of
    # the list, a project with no git, a symlink under /tmp, the no-HIT cost)
    # stay in safe-bash-t-y.test.sh.
    tmp_is_private = str(Path("/tmp").resolve()) == "/private/tmp"
    tmp_note = (
        "DIVERGENCE 4, PLATFORM-COMPUTED: Claude accepts the RESOLVED /tmp anchor "
        f"({'/private/tmp/ here, so PY_STRICTER' if tmp_is_private else 'equal to /tmp/ here, so DENY'}); "
        "the python list is repo-relative and refuses every absolute /tmp path"
    )
    rows += [
        row("operand/tracked-beside-tmp", "safe_bash", "rm src/x /tmp/x", DENY,
            "one allowlisted operand no longer carries the tracked one"),
        row("operand/mv-tracked-to-tmp", "safe_bash", "mv src/x /tmp/x", DENY,
            "mv: the source is judged too"),
        row("operand/build-not-first-component", "safe_bash", "rm docs/build/x.md", DENY,
            "build/ must be the FIRST component, not a substring"),
        row("operand/cache-is-a-component", "safe_bash", "rm .cache-notes.md", DENY,
            ".cache must be a whole component, not a prefix of a name"),
        row("operand/substitution-glued-to-tmp", "safe_bash",
            "rm -rf /tmp/a$(echo x) README.md", DENY,
            "a substitution glued to a /tmp operand carries neither itself nor the next one"),
        row("operand/mv-t-value-is-judged", "safe_bash", "mv -t /tmp/x README.md", DENY,
            "every operand is judged; the -t value is read as a path (named false positive)"),
        row("operand/partial-dissolution", "safe_bash", "rm -rf dist/x $HOME", DENY,
            "ONE operand dissolves: refused on every host (formula F2 on python)"),
        row("operand/partial-dissolution-quoted", "safe_bash", 'rm -rf dist/x "$HOME"', DENY,
            "same, quoted expansion"),
        row("operand/tmp-itself", "safe_bash", "rm -rf /tmp", DENY,
            "the anchor itself is not STRICTLY under it"),
        row("operand/tmp-subdir-of-a-source-dir", "safe_bash", "rm -rf src/tmp/x", DENY,
            "tmp is not the first component"),
        row("operand/nested-node-modules", "safe_bash", "rm -rf packages/ui/node_modules", DENY,
            "a NESTED node_modules is outside the anchored list, as on the python hosts "
            "(accepted false positive in a monorepo)"),
        row("operand/mv-source-outside-the-list", "safe_bash", "mv out.bin build/out.bin", DENY,
            "the SOURCE out.bin is judged: Claude used to pass it on the `build/` substring"),
        row("operand/expanded-directory", "safe_bash", 'S=/private/tmp/x; rm -rf "$S/y"', DENY,
            "no literal prefix: judged by its literal prefix only (accepted false positive)"),
        row("operand/dot-slash-node-modules", "safe_bash", "rm -rf ./node_modules/", ALLOW,
            "DIVERGENCE 9, CLOSED by T-00000762 (decision 6): this row was PY_STRICTER "
            "for the wrong motive — the python _ROOT_RM read ANY operand ending in `/` "
            "as the root; it wants a BARE `/` now"),
        row("operand/listed-dir-itself", "safe_bash", "rm -rf dist", ALLOW,
            "DIVERGENCE 9, CLOSED: the listed directory itself is inside the list on "
            "every host (the python allowlist compared `dist` against `dist/`)"),
        row("operand/listed-dir-trailing-slash", "safe_bash", "rm -rf dist/", ALLOW,
            "DIVERGENCE 9, CLOSED: `dist/` is no longer read as `rm -rf /`"),
        row("operand/escaped-quote-is-not-an-operand", "safe_bash",
            'echo \\" ; rm -rf .tmp/x \\"', ALLOW,
            "the lone `\"` left by an escaped quote is dropped BEFORE the count (A-C2): the "
            "rm is SEEN, and its only operand is allowlisted"),
        row("operand/quoted-tmp-with-space", "safe_bash", 'rm -rf "/tmp/a b"', PY_STRICTER,
            "DIVERGENCE 4: an absolute /tmp operand, allowed on Claude only"),
        row("operand/tmp-behind-timeout", "safe_bash", "timeout 5 rm -rf /tmp/scratch",
            PY_STRICTER, "DIVERGENCE 4: an absolute /tmp operand, allowed on Claude only"),
        row("operand/git-rm-then-tmp", "safe_bash", "git rm -q x && rm -rf /tmp/scratch",
            PY_STRICTER, "DIVERGENCE 4: an absolute /tmp operand, allowed on Claude only"),
        row("operand/redirect-is-not-an-operand", "safe_bash", "rm -rf dist/x 2>/dev/null",
            PY_STRICTER,
            "DIVERGENCE 8: the python hosts read `2>/dev/null` as a target (pre-existing, "
            "T-00000764); Claude's pass drops a redirect with its target"),
        row("allowlist//private/tmp/x", "safe_bash", "rm -rf /private/tmp/x",
            PY_STRICTER if tmp_is_private else DENY, tmp_note),
        row("operand/agents-scratchpad", "safe_bash",
            "rm -rf /private/tmp/claude-502/-Users-x-proj/0000-sess/scratchpad/x",
            PY_STRICTER if tmp_is_private else DENY, tmp_note),
    ]
    for label, command in (
        ("bare-rm", "rm"),
        ("echo-into-xargs", "echo src/x | xargs rm -f"),
        ("git-ls-files-into-xargs", "git ls-files | xargs rm -f"),
        ("ls-into-xargs-listed-operand", "ls | xargs rm -f build/x"),
        ("printf-into-xargs-listed-operand", "printf 'src/x' | xargs rm -f build/x"),
        ("find-exec-listed-operand", "find . -name '*.o' -exec rm -f build/x {} \\;"),
        ("find-exec-under-tmp", "find /tmp/x -name '*.o' -exec rm {} \\;"),
        ("parallel-listed-operand", "parallel rm -f build/x"),
    ):
        rows.append(row(
            f"operand/{label}", "safe_bash", command, DENY,
            "no operand, or operands fed by a pipe (xargs, parallel, find -exec): refused "
            "BY CONSTRUCTION whatever the static operand (T-00000762)",
            motive=MOTIVE_PIPE,
        ))

    # -- T-00000762, closing-pair pass: every finding a row on the three hosts --
    # Measured before the fix on the bridges of eb058e8a: each DENY row below was
    # ALLOW on at least one host (most on all three), each ALLOW row is its
    # control. The shapes with a fixture of their own (the case-insensitive
    # veto) stay in the colocated suites.
    for label, command, motive in (
        ("redirect-amp-gt-is-not-a-separator", "rm build/x &>/dev/null src/a.py", MOTIVE_CHECKPOINT),
        ("redirect-amp-gt-gt", "rm build/x &>>/dev/null src/a.py", MOTIVE_CHECKPOINT),
        ("redirect-lt-amp", "rm build/x <&- src/a.py", MOTIVE_CHECKPOINT),
        ("leading-input-redirect", "< list.txt rm -rf src/x", MOTIVE_CHECKPOINT),
        ("leading-output-redirect", "> out.txt rm -rf src/x", MOTIVE_CHECKPOINT),
        ("leading-fd-redirect", "2>/dev/null rm -rf src/x", MOTIVE_CHECKPOINT),
        ("expansion-after-envelope", "sudo $X rm -rf src/x", MOTIVE_CHECKPOINT),
        ("expansion-assignment-value", "FOO=$x rm -rf src/x", MOTIVE_CHECKPOINT),
        ("quoted-assignment-value", 'FOO="bar" rm -rf src/x', MOTIVE_CHECKPOINT),
        ("expansion-is-the-command", "$X rm -rf build/x", MOTIVE_PIPE),
        ("mv-glued-t", "mv -tsrc build/x", MOTIVE_CHECKPOINT),
        ("mv-target-directory", "mv --target-directory=src build/x", MOTIVE_CHECKPOINT),
        ("mv-target-abbreviated", "mv --targ=src build/x", MOTIVE_CHECKPOINT),
        ("brace-is-an-argument", "rm -rf .tmp/x } src/a.py", MOTIVE_CHECKPOINT),
        ("fed-behind-nice", "ls | nice -n 10 xargs rm -f build/x", MOTIVE_PIPE),
        ("fed-behind-timeout", "ls | timeout 5 xargs rm -f build/x", MOTIVE_PIPE),
        ("fed-behind-sudo-u", "ls | sudo -u root xargs rm -f build/x", MOTIVE_PIPE),
        ("fed-parallel-behind-nice", "nice -n 10 parallel rm -f build/x", MOTIVE_PIPE),
        ("fed-through-process-substitution", "xargs -a <(git ls-files) rm -f build/x", MOTIVE_PIPE),
        ("fed-parallel-process-substitution", "parallel -a <(git ls-files) rm -f build/x", MOTIVE_PIPE),
        ("fed-arg-file-expansion", "xargs -a $F rm -f build/x", MOTIVE_PIPE),
        ("fed-leading-redirect", "< list.txt xargs rm -f build/x", MOTIVE_PIPE),
        ("fed-frame-across-a-semicolon", "xargs -a <(a; b) rm -f build/x", MOTIVE_PIPE),
        ("fed-find-ok", "find . -name x -ok rm -f build/x {} ;", MOTIVE_PIPE),
        ("fed-find-okdir", "find . -name x -okdir rm -f build/x {} ;", MOTIVE_PIPE),
        # Refused on every host, for a host's own reason: Claude by its LITERAL
        # prefix `/tmp/` (decision 2, pinned with its motive by the (y54) arm),
        # the python hosts by their list, which holds no absolute /tmp path.
        ("dissolved-tmp-anchor", "rm -rf /tmp/$X", MOTIVE_CHECKPOINT),
    ):
        rows.append(row(
            f"pass2/{label}", "safe_bash", command, DENY,
            "T-00000762 closing-pair pass: a redirect's target, an expansion and a "
            "quoted assignment value never take the command slot, `&>`/`<&` never cut, "
            "the feeder survives envelopes, frames and redirects, a glued mv "
            "destination is an operand, `}` is an argument", motive=motive,
        ))
    for label, command, motive in (
        ("git-reset-h", "git reset --h", MOTIVE_GITWIPE),
        ("git-reset-har-head", "git reset --har HEAD", MOTIVE_GITWIPE),
        ("git-restore-staged-wo", "git restore --staged --wo .", MOTIVE_GITWIPE),
        ("git-stash-m-abbrev", "git stash push --m wip", MOTIVE_GITWIPE),
        ("git-stash-pathspec-stdin", "git stash push --pathspec-from-file=-", MOTIVE_GITWIPE),
        ("git-stash-pathspec-stdin-separate", "git stash push --pathspec-from-file -", MOTIVE_GITWIPE),
        ("git-restore-pathspec-stdin", "git restore --pathspec-from-file=-", MOTIVE_GITWIPE),
        ("git-checkout-quoted-star", "git checkout -- '*'", MOTIVE_GITWIPE),
        ("git-checkout-star", "git checkout -- *", MOTIVE_GITWIPE),
        ("git-restore-quoted-top", "git restore ':(top)'", MOTIVE_GITWIPE),
        ("git-restore-dot-slash-dot", "git restore ./.", MOTIVE_GITWIPE),
        ("git-stash-exclude-only", "git stash push -- ':!src/x'", MOTIVE_GITWIPE),
        ("git-glued-quoted-git-dir", 'git --git-dir="$d" restore .', MOTIVE_GITWIPE),
        ("git-expansion-value-then-wipe", "git -C $d reset --hard", MOTIVE_GITWIPE),
        ("git-expansion-pathspec", "git checkout $BRANCH", MOTIVE_GITWIPE),
        ("git-clean-e-value-n", "git clean -f -e -n", MOTIVE_GITWIPE),
        ("git-subcommand-expansion", "git $SUB .", MOTIVE_GITHIDDEN),
        ("git-subcommand-substitution", "git $(echo reset) --hard", MOTIVE_GITHIDDEN),
        ("git-stash-mode-expansion", "git stash $MODE", MOTIVE_GITHIDDEN),
    ):
        rows.append(row(
            f"pass2/{label}", "safe_bash", command, DENY,
            "T-00000762 closing-pair pass: git abbreviations (measured, git 2.55), a "
            "pathspec list from stdin, broad and quoted pathspecs (decision 1), an "
            "unquoted expansion where git reads its subcommand (decision 3)",
            motive=motive,
        ))
    for label, command in (
        ("mv-glued-destination-in-list", "mv -tbuild/y build/x"),
        ("case-pattern-reopens-the-command", "case $x in a) rm -rf .tmp/x;; esac"),
        ("redirect-target-after-echo", "echo x > out.txt rm -rf src/x"),
        ("substitution-argument-of-echo", "echo $(date) rm -rf src/x"),
        ("git-stash-pathspec-file", "git stash push --pathspec-from-file=list.txt"),
        ("git-restore-quoted-precise", 'git restore "src/a b.txt"'),
        ("git-checkout-quoted-expansion", 'git checkout "$BRANCH"'),
        ("git-expansion-value", "git -C $d status"),
        ("git-clean-dry-run", "git clean -n"),
        ("git-clean-dry-run-long", "git clean --dry-run"),
        ("git-clean-dry-run-cluster", "git clean -ndx"),
    ):
        rows.append(row(
            f"pass2/{label}", "safe_bash", command, ALLOW,
            "T-00000762 closing-pair pass, CONTROL: a scoped or dry form, a value, a "
            "word that never takes the command slot",
        ))
    rows += [
        row("pass2/comment-is-not-an-operand", "safe_bash", "rm -rf build/x # src/a.py",
            PY_STRICTER,
            "DIVERGENCE 8: Claude stops its per-operand slice at the ` #`; the python "
            "hosts read `#` and `src/a.py` as targets (pre-existing, T-00000764)"),
        row("pass2/subshell-paren-is-not-an-operand", "safe_bash", "( rm -rf .tmp/x )",
            PY_STRICTER,
            "DIVERGENCE 8: Claude stops its slice at the unnested `)`; the python hosts "
            "read `)` as a target (pre-existing, T-00000764)"),
    ]

    # -- guard 4: a WRITE REDIRECT to a tracked or protected file ------------
    # T-00000244. UNIFORM across the three hosts: the predicate is the same on
    # both families — refuse iff the literal target is git-tracked OR protected —
    # the only per-family difference being the SOURCE of the protected patterns
    # (Claude extracts them textually from protect-paths.sh, the python hosts
    # import protect_paths). The fixture's tracked file is `src/x`; KICKOFF_REQUIRED
    # and .mcp.json are untracked there, so they exercise the PROTECTED clause
    # specifically — the half that catches the two sensitive files git misses.
    rows += [
        row("redirect/doctrine-idiom", "safe_bash", "make check > build.out 2>&1", ALLOW,
            "THE CONTRACT UNDER ITS OWN NAME: `cmd > out 2>&1` is the idiom the kit "
            "ORDERS agents to use; its target is untracked, so it must PASS on every host"),
        row("redirect/doctrine-idiom-deny-twin", "safe_bash", "echo x > src/x", DENY,
            "the twin of the row above: the SAME redirect form, but the target is the "
            "fixture's TRACKED file, so it is refused — proving the idiom passes on its "
            "target and not on its shape", motive=MOTIVE_REDIRECT),
        row("redirect/append-tracked", "safe_bash", "cat >> src/x", DENY,
            "append (`>>`) to a tracked file bypasses Edit/Write just as truncation does",
            motive=MOTIVE_REDIRECT),
        row("redirect/protected-kickoff", "safe_bash",
            "printf y > .agents/state/gates/KICKOFF_REQUIRED", DENY,
            "the PROTECTED clause, first sensitive file: a `>` truncation would DISARM "
            "the mandate guard, and it is untracked so only clause 2 catches it",
            motive=MOTIVE_REDIRECT),
        row("redirect/protected-mcp", "safe_bash", "echo x > .mcp.json", DENY,
            "the PROTECTED clause, second sensitive file: creating `.mcp.json` escapes "
            "the Edit deny on all four hosts", motive=MOTIVE_REDIRECT),
        row("redirect/dup-descriptor", "safe_bash", "echo err >&2", ALLOW,
            "descriptor duplication writes no file, so it PASSES the polarity table"),
        row("redirect/absolute-outside-repo", "safe_bash", "echo x > /tmp/scratch-t244", ALLOW,
            "a target outside the repository is neither tracked nor protected"),
        row("redirect/quoted-target-invisible", "safe_bash", 'echo x > "spaced name.txt"', ALLOW,
            "a quoted target is neutralised before this stage, so it is invisible and "
            "PASSES — the same isometric/@@-scrub the rm/mv guard relies on"),
        row("redirect/expansion-target-invisible", "safe_bash", "echo x > $OUT", ALLOW,
            "a $-expanded target has no literal prefix to judge, so it PASSES"),
        row("redirect/gt-inside-quotes-is-data", "safe_bash", 'echo "a > src/x is data"', ALLOW,
            "a `>` living inside a quoted string is not a redirection operator"),
        row("redirect/body-of-quoted-heredoc-is-data", "safe_bash",
            "git commit -F - <<'MSG'\necho x > src/x\nMSG", ALLOW,
            "a `>` in a quoted-delimiter heredoc body is redirected DATA, blanked by the "
            "heredoc stage before the redirect guard sees it"),
        # -- T-00000698: the SAME predicate said per path, and the breach the two
        # Python twins had on the default-branch markers. No row pins the `how`
        # column or the rule id (a glob on Claude, an id on the Python hosts):
        # those per-host wordings live in each host's own bench; here only the
        # VERDICT and the redirect MOTIVE are asserted, uniformly.
        row("redirect/relative-target-after-internal-cd", "safe_bash",
            "cd /tmp/t698 && echo x > src/x", DENY,
            "a relative target is resolved against the PROJECT ROOT, never against a cd "
            "internal to the command — src/x is the fixture's tracked file THERE",
            motive=MOTIVE_REDIRECT),
        row("redirect/absolute-outside-repo-same-name", "safe_bash",
            "echo x > /tmp/t698/src/x", ALLOW,
            "the SAME name, absolute and outside the repository: neither tracked nor "
            "protected, so the root resolution binds relative targets only"),
        row("redirect/protected-binome-outside-repo", "safe_bash",
            "printf y > /tmp/t698/.agents/state/gates/BINOME_REQUIRED", DENY,
            "a guard-arming marker is refused by its own rule WHEREVER it lives, outside "
            "the repository included — so a throwaway clone cannot arm it",
            motive=MOTIVE_REDIRECT),
        row("redirect/absolute-inside-repo", "safe_bash",
            "echo x > {project}/src/x", DENY,
            "an ABSOLUTE target under the root is the tracked file itself; the "
            "{project} token is substituted with the fixture path by verdict(), the "
            "fixture not existing yet when this matrix is built at import",
            motive=MOTIVE_REDIRECT),
        row("redirect/protected-push-defaut-sortie", "safe_bash",
            "printf y > .agents/state/gates/PUSH_DEFAUT_AUTORISE", DENY,
            "the pilot-only exit of the default-branch guard (T-00000595): untracked in "
            "the fixture (.agents/ is ignored), so only the protected clause refuses it; "
            "the Python twins' protect_paths carries SEVEN suffixes vs FIVE before "
            "T-00000698, and this row was an ALLOW on codex/gemini until then",
            motive=MOTIVE_REDIRECT),
        row("redirect/protected-push-defaut-arming", "safe_bash",
            "printf y > /tmp/t698/.agents/state/gates/PUSH_DEFAUT_PROTEGE", DENY,
            "the default-branch arming marker OUTSIDE the fixture: git cannot see it, "
            "only the protected clause can — the breach T-00000706 measured on the four "
            "Python hosts",
            motive=MOTIVE_REDIRECT),
        # -- T-00000698, correction (B#1 of the closing pair): the NAME rule. Both
        # bypass rows were MEASURED allow on the three hosts before it; the rule is
        # `arming-marker-name`, its list DERIVED from each family's canonical path
        # guard (the `case` block of protect-paths.sh, the `*_SUFFIX` constants of
        # protect_paths.py), never a third copy. Named mutation: the name rule
        # removed from one family → its three deny rows red on that host only.
        row("redirect/arming-marker-after-cd", "safe_bash",
            "cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE", DENY,
            "a cd internal to the command hides the DIRECTORY from the root-relative "
            "resolution (the target read as <root>/PUSH_DEFAUT_AUTORISE matched no "
            "suffix); the marker NAME is what a cd cannot hide",
            motive=MOTIVE_REDIRECT),
        row("redirect/arming-marker-quoted", "safe_bash",
            'printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"', DENY,
            "a quoted target is invisible to the path clauses by construction; a marker "
            "name is the ONE quoted target the guard reads", motive=MOTIVE_REDIRECT),
        row("redirect/arming-marker-expanded-dir", "safe_bash",
            "printf y > $D/KICKOFF_REQUIRED", DENY,
            "the directory is expanded, the last segment is literal: judged by name",
            motive=MOTIVE_REDIRECT),
        row("redirect/ordinary-name-after-cd", "safe_bash",
            "cd docs && echo x > notes.txt", ALLOW,
            "NEGATIVE CONTROL of the name rule: an ordinary, untracked name after a cd "
            "passes unchanged — the general cd/quote case is T-00000720, not this lot"),
        # -- T-00000698, third correction: the FOUR MEDIUM bypasses of the name rule
        # the security review measured on 09a5284 (S-00001921). Each row was
        # MEASURED allow before its fix on the host(s) named in its note, and each
        # carries a NAMED mutation — revert the hunk, the row is red:
        #   M1  safe-bash.sh marker_hits head class (`" \t;&|("` + NL back to STOP)
        #       → the `${#x}` row red on claude only;
        #   M2  opaque_expansion_end / opaque_end removed from the target word loop
        #       → the `${D}/` row red on the three hosts;
        #   M3  `>&word` skipped again whatever the word (fd_dup / _FD_DUP_WORD)
        #       → the `>&` row red on the three hosts;
        #   M4  `_COARSE_CUT` back to `[;&|\n]+` → the `>|` row red on codex/gemini.
        row("redirect/arming-marker-after-brace-hash", "safe_bash",
            'echo ${#x} > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"', DENY,
            "M1: a `#` after `{` is NOT a comment head (bash writes the file, measured); "
            "Claude's name rule read the rest of the line as a comment and passed",
            motive=MOTIVE_REDIRECT),
        row("redirect/arming-marker-braced-expanded-dir", "safe_bash",
            "printf y > ${D}/PUSH_DEFAUT_AUTORISE", DENY,
            "M2: `${D}/NAME` — the `{` cut the target word at `$` on the three hosts, "
            "leaving nothing to compare; the expansion is now walked opaquely and the "
            "literal last segment judged (`$(pwd)/NAME` and a backtick span alike)",
            motive=MOTIVE_REDIRECT),
        row("redirect/arming-marker-amp-redirect", "safe_bash",
            "printf y >& PUSH_DEFAUT_AUTORISE", DENY,
            "M3: `>&word` with a non-numeric word is a WRITE to that file (bash created "
            "it, measured), not a fd duplication — skipped as `>&N` on the three hosts",
            motive=MOTIVE_REDIRECT),
        row("redirect/arming-marker-noclobber-after-cd", "safe_bash",
            "cd g && printf y >| PUSH_DEFAUT_AUTORISE", DENY,
            "M4: `>|` was cut as a PIPE by the Python coarse cut, so the target fell "
            "into the next segment and was lost; Claude refused it already",
            motive=MOTIVE_REDIRECT),
        row("redirect/expansion-glued-to-name-passes", "safe_bash",
            "echo x > ${X}PUSH_DEFAUT_AUTORISE", ALLOW,
            "NEGATIVE CONTROL of M2: an expansion GLUED to the name leaves no literal "
            "last segment, so it still passes — the rule judges a segment, not a suffix"),
        row("redirect/noclobber-ordinary-target-passes", "safe_bash",
            "ls | wc -l || echo x >| out.txt", ALLOW,
            "NEGATIVE CONTROL of M4: `|`, `||` still cut and an untracked `>|` target "
            "still passes on every host"),
        row("redirect/dup-descriptor-close-and-var", "safe_bash",
            "echo x >&- 2>&1; echo y >& $fd", ALLOW,
            "NEGATIVE CONTROL of M3: `>&-` closes, `2>&1` duplicates, `>& $fd` has no "
            "literal segment — none is a write this guard can name"),
        # -- T-00000698, correction (A-T3): the credential lists DIFFERED per host
        # and the deny clause said so; these three rows pinned it. T-00000721
        # aligned the lists and they are UNIFORM DENY — the row NAMES are kept so
        # the history reads in `git log -S`. Named mutations: `id_rsa` removed from
        # protect_paths.SECRET_NAMES → the id_rsa row red on codex/gemini; `*.key`
        # removed from the credential arm of protect-paths.sh → the key row red on
        # claude; the `.env` substring removed from safe-bash's `protected()` →
        # the envrc row red on claude.
        row("redirect/credential-id_rsa-claude-only", "safe_bash",
            "echo x > /tmp/t698/id_rsa", DENY,
            "DIVERGENCE 6, CLOSED by T-00000721: `id_rsa` joined protect_paths."
            "SECRET_NAMES; it was a Claude-only credential glob", motive=MOTIVE_REDIRECT),
        row("redirect/credential-key-python-only", "safe_bash",
            "echo x > /tmp/t698/server.key", DENY,
            "DIVERGENCE 6, CLOSED by T-00000721: Claude's credential arm now carries "
            "the SECRET_EXTENSIONS of the twins, `.key` included", motive=MOTIVE_REDIRECT),
        row("redirect/credential-envrc-python-only", "safe_bash",
            "echo x > /tmp/t698/.envrc", DENY,
            "DIVERGENCE 6, CLOSED by T-00000721: safe-bash's `protected()` judges `.env` "
            "as a SUBSTRING, templates exempted, like SECRET_NAMES on the Python hosts",
            motive=MOTIVE_REDIRECT),
        row("redirect/credential-colon-stream", "safe_bash",
            "echo x > /tmp/t698/server.key:stream", DENY,
            "T-00000722: an NTFS stream hides the extension from the case-folded "
            "candidate (`server.key:stream` ends with no credential extension); the "
            "NT-folded candidate reads `server.key` — refused on every host",
            motive=MOTIVE_REDIRECT),
        row("redirect/mcp-config-toml-wherever", "safe_bash",
            "echo x > /tmp/t698/.codex/config.toml", DENY,
            "one of the two host settings files the deny clause now names among the "
            "`wherever it lives` protected names (mcp-config on every host)",
            motive=MOTIVE_REDIRECT),
        row("redirect/mcp-config-settings-wherever", "safe_bash",
            "echo x > /tmp/t698/.gemini/settings.json", DENY,
            "the other host settings file, same rule, same reach",
            motive=MOTIVE_REDIRECT),
    ]

    # -- guard 2: an absent rg lies BY THE VOID ------------------------------
    rows += [
        row("rg/absent-plain", "safe_bash", f"{ABSENT_RG} motif", DENY,
            "an unresolvable rg is refused: its failure is indiscernible from an "
            "empty result", motive=MOTIVE_RG),
        row("rg/absent-exe", "safe_bash", f"{ABSENT_RG}.exe motif", DENY,
            "the .exe spelling resolves to the same base", motive=MOTIVE_RG),
        row("rg/probe-command-v", "safe_bash", f"command -v {ABSENT_RG}", ALLOW,
            "A GUARD MUST NOT BLOCK ITS OWN DIAGNOSTIC: a probe prints a path or "
            "fails, it never runs the tool"),
        row("rg/probe-which", "safe_bash", f"which {ABSENT_RG}", ALLOW, "same, which"),
        row("rg/probe-type", "safe_bash", f"type {ABSENT_RG}", ALLOW, "same, type"),
        row("rg/probe-hash", "safe_bash", f"hash {ABSENT_RG}", ALLOW, "same, hash"),
        row("rg/probe-then-real-call", "safe_bash",
            f"command -v {ABSENT_RG} && {ABSENT_RG} motif", DENY,
            "the probe flag dies at the separator, so it opens no bypass window",
            motive=MOTIVE_RG),
        row("rg/envelope-window", "safe_bash", f"timeout 5 {ABSENT_RG} motif", ALLOW,
            "ASSUMED HOLE, shared: the envelope-window fallback covers rm/mv only, "
            "so widening it would refuse `sudo apt install ripgrep`"),
        row("rg/present-is-never-blocked", "safe_bash", "rg motif", ALLOW,
            "the guard fires on ABSENCE only; PATH is forged with a shim so this row "
            "does not depend on what the machine has installed", env={"RG_SHIM": "1"}),
    ]

    # -- audit gate: the runners, the anchor, the ref ------------------------
    rows += [
        row("install/bunx", "audit_gate", "bunx skills add other/pkg", DENY,
            "runner the python hosts did not gate at all", motive=MOTIVE_AUDIT),
        row("install/bunx+opts", "audit_gate", "bunx --bun skills add other/pkg", DENY,
            "options between runner and verb are the cheapest bypass", motive=MOTIVE_AUDIT),
        row("install/yarn-dlx", "audit_gate", "yarn dlx skills add other/pkg", DENY,
            "runner the python hosts did not gate at all", motive=MOTIVE_AUDIT),
        row("install/yarn-dlx+opts", "audit_gate", "yarn dlx --quiet skills add other/pkg",
            DENY, "options admitted between runner and verb", motive=MOTIVE_AUDIT),
        row("install/pnpm-dlx+opts", "audit_gate", "pnpm dlx -y skills add other/pkg", DENY,
            "pnpm dlx was gated WITHOUT its options: `-y` walked past the gate",
            motive=MOTIVE_AUDIT),
        row("install/global-cli", "audit_gate", "skills add other/pkg", DENY,
            "the globally installed CLI has no runner, so the anchor is the position "
            "of command", motive=MOTIVE_AUDIT),
        row("install/global-cli-cmd", "audit_gate", "skills.cmd add other/pkg", DENY,
            "same, Windows spelling", motive=MOTIVE_AUDIT),
        row("install/global-after-separator", "audit_gate", "echo hi && skills add other/pkg",
            DENY, "a separator opens a position of command", motive=MOTIVE_AUDIT),
        row("install/global-mention", "audit_gate", "we should discuss skills add later",
            ALLOW, "NON-VACUITY of the anchor: a mention mid-sentence is not an "
            "install", motive=MOTIVE_AUDIT),
        row("install/audited-passes", "audit_gate", "skills add owner/pkg", ALLOW,
            "an audit=pass entry is what the gate is for", motive=MOTIVE_AUDIT),
        row("install/ref-cut-at-metachar", "audit_gate", "npx skills add owner/pkg&&echo done",
            ALLOW, "the ref STOPS at the first metacharacter: without the cut the ref "
            "reads `owner/pkg&&echo` and the gate refuses an ALREADY AUDITED skill",
            motive=MOTIVE_AUDIT),
        row("install/ref-cut-still-gates", "audit_gate",
            "npx skills add other/pkg&&echo done", DENY,
            "the cut must not become a bypass: the unaudited ref is still refused",
            motive=MOTIVE_AUDIT),
        row("install/quoted-title", "audit_gate",
            'python .agents/bin/tasks.py new "corriger le garde: npx skills add bloque le board"',
            ALLOW, "the measured incident: this refusal lost a board write", motive=MOTIVE_AUDIT),
        row("install/quoted-single-word", "audit_gate",
            'python .agents/bin/tasks.py new "skills"', ALLOW,
            "single-word quoted mention", motive=MOTIVE_AUDIT),
        row("install/nested-payload", "audit_gate", 'bash -c "npx skills add other/pkg"',
            ALLOW, "ASSUMED HOLE, shared with the Claude homologue and pinned in both "
            "colocated suites", motive=MOTIVE_AUDIT),
        # T-00000461: the local skills fallback's own `install` is gated in command
        # position too. Parity pins only the NESTED (quoted) form here — ALLOW on
        # all three, an ASSUMED HOLE shared with install/nested-payload. The
        # positive DENY is per-host (test_guard_hooks / test_gemini_hooks +
        # audit-gate.test.sh), because the gate SPAWNS skills_github_fallback.py,
        # which this fixture does not carry. Reach: 3 implementations measured
        # (claude audit-gate.sh, codex + gemini audit_gate.py) / 6 hosts (Copilot
        # AND Kimi run .codex/audit_gate.py; Gemini AND Antigravity run
        # .gemini/audit_gate.py) / 5 registries — Kimi runtime SUPPOSÉ (T-00000395).
        row("fallback-install/nested-payload", "audit_gate",
            'bash -c "python .agents/bin/skills_github_fallback.py install o/r"', ALLOW,
            "TROU ASSUMÉ, partagé avec install/nested-payload — span CITÉ blanchi par "
            "l'étage 1 ; T-00000416 le couvre", motive=MOTIVE_AUDIT),
        row("install/naked-unaudited", "audit_gate", "npx skills add other/pkg", DENY,
            "the baseline refusal", motive=MOTIVE_AUDIT),
        row("install/escaped-quote-masks-separator", "audit_gate",
            'echo \\" && npx skills add other/pkg \\"', DENY,
            "DIVERGENCE 5 on the gate, CLOSED by T-00000181: the same escaped-quote "
            "masking installed an UNAUDITED skill past the AUDIT_LOG. "
            ".claude/hooks/audit-gate.sh now carries the same backslash-aware scanner "
            "as the python hosts, so the install is seen and refused on all three",
            motive=MOTIVE_AUDIT),
        row("install/escaped-single-quote-masks-separator", "audit_gate",
            "echo \\' && npx skills add other/pkg \\'", DENY,
            "DIVERGENCE 5, single-quote form: closed the same way by T-00000181",
            motive=MOTIVE_AUDIT),
        row("install/even-backslash-is-a-real-quote", "audit_gate",
            'echo \\\\" && npx skills add other/pkg \\\\"', ALLOW,
            "THE CONTROL: an even run of backslashes opens a genuine quoted segment, so "
            "this really is a mention and not an install", motive=MOTIVE_AUDIT),
    ]

    # -- T-00000240: a runner OR the global CLI QUALIFIED BY A PATH -----------
    # The measured hole: `npx skills add x` was refused but `/usr/local/bin/npx`,
    # `./node_modules/.bin/npx` and — worst — `/usr/local/bin/skills add x` (the
    # global CLI behind a path) all walked past the Claude gate, while the python
    # hosts already refused the RUNNER forms via `\b`. Two edits close it on
    # Claude and align UPWARD: `.`, `/`, `-` become left boundaries of the six
    # runner patterns (P1-P3, P7), and a path PREFIX group is admitted before the
    # global `skills` CLI anchor (P5, P6, P12). The prefix cannot cross a space or
    # a shell separator, so on THAT stage the two holes stayed open — T-00000256
    # then CLOSED them by widening the position of command past a bare `skills`: a
    # QUOTED path (P8) scrubbed to ` @@ ` reads as `@@ add`/`@@ skills add`, and an
    # ASSIGNMENT prefix (P9) is admitted between the anchor and the CLI. P11 is
    # still ALLOW, unlike P8/P9 now, but for a
    # DIFFERENT reason — its ref is audited — and is discriminated by P5 (same
    # form, unaudited ref, DENY). Behaviour proven on gawk AND mawk before the
    # write (measures/T-00000240/sonde.awk): the class {/,\} compiles under both.
    rows += [
        row("install/path-npx-abs", "audit_gate", "/usr/local/bin/npx skills add other/pkg",
            DENY, "an absolute path before a runner is no longer a left boundary that "
            "hides it — the python hosts already refused this via `\\b`", motive=MOTIVE_AUDIT),
        row("install/path-npx-rel", "audit_gate", "./node_modules/.bin/npx skills add other/pkg",
            DENY, "the most natural form in a JS project, and the one the task title "
            "names: `.bin/npx` is the runner, path or not", motive=MOTIVE_AUDIT),
        row("install/path-pnpm-dlx", "audit_gate", "/usr/bin/pnpm dlx skills add other/pkg",
            DENY, "the path-qualified runner generalises past npx to pnpm/yarn dlx too",
            motive=MOTIVE_AUDIT),
        row("install/path-npx-backslash", "audit_gate", "C:\\tools\\npx.cmd skills add other/pkg",
            DENY, "pins that the BACKSLASH was ALREADY a boundary before this task "
            "(DENY on both families before AND after): the edit does not regress it",
            motive=MOTIVE_AUDIT),
        row("install/path-cli-abs", "audit_gate", "/usr/local/bin/skills add other/pkg",
            DENY, "THE HOLE THE TASK CLOSES: the global CLI behind an absolute path. "
            "ALLOW on all three before the fix, DENY on all three after", motive=MOTIVE_AUDIT),
        row("install/path-cli-backslash", "audit_gate", "C:\\tools\\skills.cmd add other/pkg",
            DENY, "the same hole, Windows backslash spelling of the global CLI path",
            motive=MOTIVE_AUDIT),
        row("install/suffix-homonym", "audit_gate", "my-npx skills add other/pkg",
            DENY, "`-` becomes a left boundary, so `my-npx` is read as the runner `npx`; "
            "the python hosts refused it already — this removes a divergence",
            motive=MOTIVE_AUDIT),
        row("install/quoted-path-closed", "audit_gate", '"/opt/tools/skills" add other/pkg',
            DENY, "HOLE CLOSED by T-00000256: a QUOTED path scrubs to ` @@ `, and `@@ "
            "add` in command position is read as the absorbed global CLI installing",
            motive=MOTIVE_AUDIT),
        row("install/assign-prefix-closed", "audit_gate", "FOO=1 skills add other/pkg",
            DENY, "HOLE CLOSED by T-00000256: an assignment prefix is admitted between "
            "the anchor and the CLI — it does not close the position of command",
            motive=MOTIVE_AUDIT),
        row("install/assign-quoted-value", "audit_gate", 'FOO="x y" skills add other/pkg',
            DENY, "the assignment's quoted value scrubs to `FOO= @@ skills add`: the `@@` "
            "is admitted alongside the assignment word before the CLI",
            motive=MOTIVE_AUDIT),
        row("install/widening-not-cmd-pos", "audit_gate", 'echo "hi" skills add other/pkg',
            ALLOW, "the widening stays ANCHORED: `echo @@ skills add` has the scrubbed "
            "quote MID-LINE, not in command position, so it is a mention not an install",
            motive=MOTIVE_AUDIT),
        row("install/assign-mid-sentence", "audit_gate", "we discuss FOO=1 skills add later",
            ALLOW, "an assignment mid-sentence opens no position of command: `FOO=1 "
            "skills add` here follows a bareword, not the start or a separator",
            motive=MOTIVE_AUDIT),
        row("install/path-cli-audited", "audit_gate", "/usr/local/bin/skills add owner/pkg",
            ALLOW, "the path-qualified global CLI whose ref IS audited: recognised as an "
            "install now, then passed by the AUDIT_LOG. Non-discriminant alone — it is "
            "P5's twin, same form, and P5's unaudited ref is what makes P5 DENY",
            motive=MOTIVE_AUDIT),
        row("install/path-vtab", "audit_gate", "a\vb/skills add other/pkg",
            DENY, "pins the prefix class is `[^ \\t...\\n]` and NOT `[^\\s...]`: a vertical "
            "tab is admitted inside the path prefix, so `a<VT>b/skills add` is an install. "
            "`[^\\s]` would exclude the VT and read this as ALLOW", motive=MOTIVE_AUDIT),
    ]

    # -- the comment frontier, and the heredoc stage on THE OTHER guard -------
    # Eight rows added by T-00000225, and both defects they pin were LIVE on the
    # python hosts when these rows were written — measured with their negative
    # control, host by host, before the fix. The Claude host already decided the
    # way this block expects, so every row here is a row where the three hosts
    # DISAGREED and now agree; that is what makes them parity rows rather than
    # colocated arms, and it is why they are here as well as in the two suites.
    rows += [
        row("comment/unpaired-quote-cannot-whiten-code", "safe_bash",
            "# don't run this\nrm -rf src/x && echo 'ok'", DENY,
            "THE FIRST LIVE BYPASS. The apostrophe of `don't` sits in a COMMENT, which "
            "bash ends at its physical line — but the quote scanner paired it with the "
            "`'` of `'ok'` on the NEXT line and neutralised everything between them, the "
            "`rm` included. The residue was therefore NOT confined to data: it reached "
            "CODE, in the most exposed zone there is, and bash really ran that rm. "
            "ALLOW on both python hosts until T-00000225 ported the frontier the Claude "
            "host already carried; UNIFORM DENY now"),
        row("comment/control-the-same-payload-without-its-comment", "safe_bash",
            "rm -rf src/x && echo 'ok'", DENY,
            "THE NEGATIVE CONTROL of the row above, and the reason its measurement means "
            "anything: strip the comment line and every host ALREADY refused, before the "
            "fix as after it. Without this row the charge could be satisfied by a guard "
            "that refuses everything"),
        row("comment/control-an-allowlisted-target-still-passes", "safe_bash",
            "# don't run this\nrm -rf .tmp/x && echo 'ok'", ALLOW,
            "THE SECOND CONTROL, in the other direction: the frontier must not degrade "
            "into 'refuse any payload carrying a #'. The guard still decides on the "
            "TARGET, so an allowlisted one passes on all three hosts"),
        row("comment/unpaired-quote-cannot-whiten-an-install", "audit_gate",
            "# don't install this\nnpx skills add other/pkg && echo 'ok'", DENY,
            "THE SAME BYPASS ON THE GATE, where it cost an UNAUDITED INSTALL rather than "
            "a checkpoint. Same shape, same apostrophe, different price — which is why "
            "the frontier had to be ported to BOTH guards and not only to the one where "
            "it was first measured", motive=MOTIVE_AUDIT),
        row("comment/control-the-same-install-without-its-comment", "audit_gate",
            "npx skills add other/pkg && echo 'ok'", DENY,
            "the twin negative control: already refused everywhere before the fix, so "
            "the row above measures the COMMENT and not the install",
            motive=MOTIVE_AUDIT),
        row("heredoc/gate-quoted-delimiter-body-is-data", "audit_gate",
            "git commit -F - <<'MSG'\nnpx skills add other/pkg dans la doc\nMSG", ALLOW,
            "THE FOUNDING INCIDENT, transposed to the gate: a commit message DESCRIBING "
            "an install was refused as one. D4 of LOT 3 had ruled the stage out of this "
            "guard 'since no host has one'; that premise died when audit-gate.sh got "
            "one, and T-00000225 restores the symmetry in the other direction. UNIFORM "
            "DENY (a false positive on pure data) until then, UNIFORM ALLOW now",
            motive=MOTIVE_AUDIT),
        row("heredoc/gate-apostrophe-in-a-body-cannot-whiten-an-install", "audit_gate",
            "git commit -F - <<'MSG'\nit's fine\nMSG\n"
            "npx skills add other/pkg && echo 'ok'", DENY,
            "THE SECOND LIVE BYPASS, and the one that shows why the stage is not a "
            "comfort feature: an `it's` in a commit message — a body whose delimiter is "
            "QUOTED, hence 100% literal for bash — paired with the `'` of `'ok'` two "
            "lines down and whitened a GENUINE unaudited install. ALLOW on both python "
            "hosts until the stage was ported here", motive=MOTIVE_AUDIT),
        row("heredoc/gate-naked-delimiter-stays-analysed", "audit_gate",
            "cat <<MSG > f\nnpx skills add other/pkg\nMSG", DENY,
            "THE POLARITY, and the row that must never flip: with a NAKED delimiter bash "
            "EXPANDS the body, so the body is CODE. A stage that blanked it too would "
            "read better and be a fail-open — this is the parity-level twin of the "
            "mutant killed in each colocated suite", motive=MOTIVE_AUDIT),
    ]

    # -- T-00000235: THE ROOT, of which the two rows above are only copies ----
    # Stage 0.5 decided opener / not-opener on ONE PHYSICAL LINE. Its `loose`
    # guard only ever saw a quote left open on THAT line: it had no memory of the
    # line already sitting INSIDE a double quote opened HIGHER UP — a state only
    # the whole-TEXT scan of stage 1 knows, and that stage runs AFTER, by
    # construction. So it believed in an opener, blanked to the delimiter (absent)
    # hence to the END, and erased the REAL closing quote together with the
    # guarded command that followed it, outside any quoting. Stage 1 never saw
    # that command: it had vanished before its turn. FAIL-OPEN, in CODE.
    #   PROPAGATION, and it is what makes these rows parity rows: before the night
    #   of 2026-08-18 safe-bash.sh was ALREADY holed while audit-gate.sh was
    #   PROTECTED (it had no stage 0.5 at all). T-00000208 ported the stage
    #   verbatim — and the hole with it; T-00000211 ported both into the two
    #   safe_bash.py; T-00000225 would have finished the job on the two
    #   audit_gate.py. Six guards, four hosts, code already published on `main`
    #   AND on template/starter-kit. Measured 2026-08-19 on all six, with the
    #   non-vacuity control below: bare payload DENY, same payload behind two
    #   lines ALLOW with no output at all.
    rows += [
        row("root/a-string-opened-earlier-cannot-fabricate-a-heredoc", "safe_bash",
            "echo \"line1\ncat <<'X'\n\" && rm -rf src/x", DENY,
            "THE ROOT CHARGE. Three lines, using NONE of the bypasses already closed: "
            "no escaping (T-00000181), no continuation (T-00000187), no piece parser "
            "(T-00000210), no comment frontier (T-00000225). The `<<'X'` sits INSIDE the "
            "string opened on line 1, so it is not an opener at all — bash never opens a "
            "body there. UNIFORM ALLOW on all six guards until the veto; UNIFORM DENY now"),
        row("root/control-the-same-payload-without-its-heredoc-line", "safe_bash",
            "echo \"line1\n\" && rm -rf src/x", DENY,
            "THE DISCRIMINATING CONTROL, and the one that names the vector: strip the "
            "`cat <<'X'` line and the quotes alone refuse everywhere, before the fix as "
            "after it. Without this row the charge above could be blamed on the quote "
            "pairing rather than on the heredoc opener, and the fix would have been "
            "written in stage 1 where it does not belong"),
        row("root/control-the-bare-payload-is-refused", "safe_bash",
            "rm -rf src/x", DENY,
            "NON-VACUITY. A guard that refused nothing would make the two rows above "
            "green for the wrong reason"),
        row("root/anti-regression-a-legitimate-quoted-body-is-still-data", "safe_bash",
            "git commit -F - <<'EOF'\nrm -rf src/x\nEOF", ALLOW,
            "THE ROW THAT FORBIDS THE LAZY FIX. A veto that over-fires — 'recognise no "
            "heredoc at all' — makes the charge green and kills the stage, silently, "
            "resurrecting the FOUNDING incident: a commit message DESCRIBING a guarded "
            "command, refused as one. The stage must still blank this body"),
        row("root/an-unpaired-quote-does-not-veto-a-later-heredoc", "safe_bash",
            "echo \"orphan\ncat <<'EOF'\nrm -rf src/x\nEOF", ALLOW,
            "THE ROW THAT DECIDES THE FORM OF THE FIX, and it is why the veto reuses "
            "stage 1's pairing rule instead of a hand-rolled cumulative automaton. An "
            "UNPAIRED quote opens nothing (bash: this whole payload is a parse error, so "
            "nothing runs); a naive automaton would hold it open to the end of the text "
            "and veto every later heredoc, turning the stage off by another route"),
        row("root/crlf-the-same-payload-with-windows-line-endings", "safe_bash",
            "echo \"line1\r\ncat <<'X'\r\n\" && rm -rf src/x", DENY,
            "THE OFFSET TRAP, and it aims at the machine this kit is developed on. "
            "Stage 0.5 strips the `\\r` from EVERY line at storage; spans taken from the "
            "ORIGINAL text while candidates are located in the RECONSTRUCTED one drift by "
            "one character per CRLF line, so the veto aims beside its target and the "
            "fail-open returns — on a Windows checkout, on every line"),
        row("root/gate-a-string-opened-earlier-cannot-fabricate-a-heredoc", "audit_gate",
            "echo \"line1\ncat <<'X'\n\" && npx skills add other/pkg", DENY,
            "THE SAME ROOT ON THE GATE, where it costs an UNAUDITED INSTALL rather than "
            "a checkpoint. This guard was PROTECTED before the night of 2026-08-18 and "
            "was holed by a faithful copy of the stage — which is the whole argument for "
            "fixing the canonical source first and porting afterwards",
            motive=MOTIVE_AUDIT),
        row("root/gate-control-the-same-payload-without-its-heredoc-line", "audit_gate",
            "echo \"line1\n\" && npx skills add other/pkg", DENY,
            "the twin discriminating control: refused everywhere before the fix as after, "
            "so the row above measures the heredoc opener and not the quotes",
            motive=MOTIVE_AUDIT),
    ]

    # -- a NUL byte in the command (T-00000785, R1) --------------------------
    rows += [
        row("nul/operand-after-a-traversal", "safe_bash", "rm -rf tmp/../.agents\x00", DENY,
            "the python hosts CRASHED here before T-00000785 (ValueError out of "
            "normalize_path, rc 1, no JSON, before any refusal); they now refuse the "
            "whole command under rule unrepresentable-command, and the row pins THAT "
            "phrase on them. The Claude column is MEASURED (macOS, bash 5.3.15) and "
            "refuses a DIFFERENT thing: the payload read `CMD=$(… python …)` drops the "
            "NUL (seen as `octet nul ignoré en entrée` under a French locale — "
            "`ignored null byte in input` in C) and the rm guard refuses `rm -rf "
            "tmp/../.agents` for its `..` — same verdict, its own checkpoint motive. "
            "Linux bash is ASSUMED to drop it the same way, not measured. No lone-"
            "surrogate row: the Claude hook DEGRADES on one (COVERAGE DEGRADED, "
            "payload read as unreadable JSON, measured), which this runner fails by "
            "design",
            motive={"claude": MOTIVE_CHECKPOINT, "codex": MOTIVE_UNREPRESENTABLE,
                    "gemini": MOTIVE_UNREPRESENTABLE}),
    ]
    return rows


MATRIX = build_matrix()


def build_fixture(root: Path) -> Path:
    """A disposable git project carrying every host's bridge at the paths the
    hooks expect, plus the two pieces of state the guards read: a tracked source
    file (so `git ls-files` has something to answer about) and an AUDIT_LOG."""
    (root / ".agents" / "bin").mkdir(parents=True)
    (root / ".agents" / "state" / "gates").mkdir(parents=True)
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "docs" / "tasks").mkdir(parents=True)

    shutil.copy2(ROOT / ".agents" / "bin" / "events.py", root / ".agents" / "bin" / "events.py")
    # T-00000641 : events.py charge redaction.py PAR CHEMIN (voie NORMALE) ; posé à l'ancien ET au neuf lieu.
    for lieu in ("src/cadre/ledger", ".agents/vendor/cadre/ledger"):
        (root / lieu).mkdir(parents=True, exist_ok=True)
        shutil.copy2(_VP.exiger(ROOT, "cadre") / "ledger" / "redaction.py", root / lieu / "redaction.py")
    shutil.copy2(
        ROOT / ".claude" / "hooks" / "emit-event.sh", root / ".claude" / "hooks" / "emit-event.sh"
    )
    for host_dir in (".codex", ".gemini"):
        target = root / host_dir / "hooks"
        target.mkdir(parents=True)
        for name in COMMON_FILES:
            shutil.copy2(ROOT / host_dir / "hooks" / name, target / name)

    (root / "src" / "x").write_text("tracked\n", encoding="utf-8")
    (root / "docs" / "tasks" / "T-002.md").write_text("# t\n", encoding="utf-8")
    (root / ".agents" / "state" / "gates" / "AUDIT_LOG").write_text(
        "# <owner>/<repo>[#<skill>] audit=pass|fail\nowner/pkg audit=pass\n", encoding="utf-8"
    )
    # The copied bridges stay untracked (same reasoning as test_events_parity:
    # autocrlf warnings on a tracked events.py leak into other hooks' stdout).
    (root / ".gitignore").write_text(
        ".agents/\n.claude/\n.codex/\n.gemini/\nsrc/cadre/\n", encoding="utf-8"
    )
    git = ["git", "-C", str(root)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["config", "user.email", "t@t"], check=True)
    subprocess.run(git + ["config", "user.name", "t"], check=True)
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(git + ["commit", "-qm", "fixture"], check=True, capture_output=True)
    return root


def build_rg_shim(directory: Path) -> str:
    """A PATH prefix in which `rg` RESOLVES, so the "a working rg is never
    blocked" row measures the guard instead of measuring the dev box.

    Both spellings are created: POSIX `command -v rg` needs the executable bit on
    a bare name, while shutil.which and Git Bash look for `rg.exe` on Windows.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("rg", "rg.exe"):
        shim = directory / name
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(directory)


class GuardDecisionParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One fixture for the whole matrix: no row writes to it, and a git init
        # per row would dominate the runtime. ignore_cleanup_errors per
        # L-00000035 (Windows teardown handles are infrastructure noise).
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.tmp = Path(cls._tmp.name)
        cls.fixture = build_fixture(cls.tmp / "project")
        cls.events = cls.tmp / "events"
        cls.events.mkdir()
        cls.rg_shim = build_rg_shim(cls.tmp / "rgbin")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def env_for(self, extra: dict, project_dir=None) -> dict:
        env = dict(os.environ)
        env.pop("AGENTS_HOOK_HOST", None)
        env.pop("CLAUDE_PROJECT_DIR", None)
        # Every write is redirected: a matrix run must never inject real-looking
        # hook.deny lines into the audit trail the dashboard reads.
        env["AGENTS_EVENTS_DIR"] = str(self.events)
        if project_dir is not None:
            env["CLAUDE_PROJECT_DIR"] = str(project_dir)
        if extra.get("RG_SHIM"):
            env["PATH"] = self.rg_shim + os.pathsep + env.get("PATH", "")
        return env

    def verdict(self, host: str, entry: dict):
        """`(denied, message)` for one row on one host. Raises on anything that
        would make a row pass without the guard having decided."""
        command, guard = entry["command"], entry["guard"]
        # MATRIX is built at import and the fixture only exists from setUpClass:
        # a row that needs an ABSOLUTE path INSIDE the fixture writes `{project}`
        # and it is substituted here, on the command only (T-00000698).
        command = command.replace("{project}", str(self.fixture))
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        if host == "claude":
            env = self.env_for(entry["env"], project_dir=self.fixture)
            result = subprocess.run(
                [BASH, str(ROOT / ".claude" / "hooks" / CLAUDE_SCRIPT[guard])],
                input=payload.encode("utf-8"), capture_output=True,
                cwd=str(self.fixture), env=env, timeout=120,
            )
            stderr = result.stderr.decode("utf-8", "replace")
            if "COVERAGE DEGRADED" in stderr:
                raise AssertionError(
                    f"claude/{entry['label']}: the guard DEGRADED instead of deciding "
                    f"({stderr.strip()[:200]}) — an unreachable host reads as 'allow', "
                    "so this is a failure and never a pass"
                )
            if result.returncode not in (0, 2):
                raise AssertionError(
                    f"claude/{entry['label']}: exit {result.returncode}, expected 0 or 2 "
                    f"({stderr.strip()[:200]})"
                )
            return result.returncode == 2, stderr
        env = self.env_for(entry["env"])
        if host == "codex":
            env["AGENTS_HOOK_HOST"] = "codex"
        script = self.fixture / PY_HOSTS[host] / "hooks" / f"{guard}.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script)],
            input=payload.encode("utf-8"), capture_output=True,
            cwd=str(self.fixture), env=env, timeout=120,
        )
        stdout = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode != 0:
            raise AssertionError(
                f"{host}/{entry['label']}: exit {result.returncode} "
                f"({result.stderr.decode('utf-8', 'replace').strip()[:200]})"
            )
        if not stdout:
            return False, ""
        body = json.loads(stdout)
        decision = body["hookSpecificOutput"]["permissionDecision"]
        reason = body["hookSpecificOutput"].get("permissionDecisionReason", "")
        if decision != "deny":
            raise AssertionError(f"{host}/{entry['label']}: unexpected decision {decision!r}")
        return True, reason

    def check(self, host: str, entry: dict):
        denied, message = self.verdict(host, entry)
        self.assertEqual(
            denied, entry["expected"][host],
            f"{host}/{entry['label']}: expected "
            f"{'deny' if entry['expected'][host] else 'allow'} for {entry['command']!r} — "
            f"{entry['note']}",
        )
        # A row may pin a DIFFERENT motive per host (a {host: substring} dict)
        # when the hosts refuse the same command for different reasons
        # (T-00000785): one substring asserted on all three would have to be
        # the weakest word they share, and would stay green under a mutant that
        # swaps one host's guard for another.
        motive = entry["motive"]
        if isinstance(motive, dict):
            motive = motive[host]
        if denied and motive:
            self.assertIn(
                motive, message,
                f"{host}/{entry['label']}: denied for the WRONG motive — expected the "
                f"guard whose message carries {motive!r}, got {message[:200]!r}",
            )

    # -- the matrix, python hosts (always runnable) -------------------------

    def test_decision_matrix_on_the_python_hosts(self):
        for entry in MATRIX:
            for host in ("codex", "gemini"):
                with self.subTest(row=entry["label"], host=host):
                    self.check(host, entry)

    # -- the matrix, Claude host -------------------------------------------

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_decision_matrix_on_the_claude_host(self):
        for entry in MATRIX:
            with self.subTest(row=entry["label"], host="claude"):
                self.check("claude", entry)

    # -- non-vacuity -------------------------------------------------------

    def test_matrix_is_populated_and_covers_the_named_receiver(self):
        """A truncated table must not pass. Sizes are asserted, not trusted, and
        the two enumerations the receiver depends on are counted explicitly."""
        self.assertGreaterEqual(len(MATRIX), 80, "the matrix lost rows")
        labels = {entry["label"] for entry in MATRIX}
        self.assertEqual(len(labels), len(MATRIX), "duplicate row labels")
        self.assertEqual(
            len([l for l in labels if l.startswith("envelope/")]), len(ENVELOPES) + 1,
            "one row per envelope, plus the own-argument window",
        )
        self.assertEqual(
            len([l for l in labels if l.startswith("keyword/")]), len(KEYWORDS),
            "one row per keyword",
        )
        # A guard that refused EVERYTHING would satisfy every deny row, so the
        # allow rows are counted too: they are the half of the matrix that a
        # false positive breaks.
        uniform_allow = [e for e in MATRIX if not any(e["expected"].values())]
        self.assertGreaterEqual(len(uniform_allow), 15, "the matrix lost its allow rows")
        for entry in MATRIX:
            self.assertEqual(set(entry["expected"]), set(HOSTS), entry["label"])
            if isinstance(entry["motive"], dict):
                self.assertEqual(set(entry["motive"]), set(HOSTS), entry["label"])

    def test_divergent_rows_carry_their_reason(self):
        """A non-uniform expectation is only legitimate when it is NAMED: this is
        what stops a red row from being repaired by quietly editing a verdict."""
        for entry in MATRIX:
            verdicts = set(entry["expected"].values())
            if len(verdicts) > 1:
                with self.subTest(row=entry["label"]):
                    self.assertRegex(
                        entry["note"], r"DIVERGENCE \d",
                        "a row that expects different verdicts per host must name the "
                        "divergence in its note",
                    )

    def test_the_two_python_bridges_carry_the_same_guard(self):
        """ONE SOURCE, ONE COPY (T-01M4V7R5H0HE0Z5TPJ4Q64VMPF). Every `*.py` of
        `.codex/hooks/` that is not a `test_*` IS its `.gemini/hooks/` namesake,
        BYTE FOR BYTE, and the two sets of names are equal in BOTH directions: a
        module absent from the copy, different, or orphaned there is red. The
        listing is NOT recursive. The repair is never a hand edit of the copy:
        `python3 .agents/bin/hooks_jumeaux.py --ecrire`. FLOOR: the modules that
        .agents/hooks.json runs from `.gemini/hooks/`, plus `_common.py` and
        `safe_bash_git.py` — an empty or shrunken listing would make the
        equality vacuous.

        This replaces a per-statement AST comparator of `_common.py` and its
        closed exemption list EXPECTED_LITERAL (T-00000785), which held two
        traps open, named here: (1) comparing PIECES — functions, then
        statements — left what fell between them unseen (a constant added to one
        copy, S-00002872; a decorator, S-00002882; a comment BETWEEN statements,
        never seen at all); (2) an EXEMPTION is a channel — code smuggled under
        an exempted name passed until its text was pinned (pass 4, T1). Byte
        equality has no pieces and no exemption, so both close by construction;
        event_host() reads the directory instead of diverging (_common.py)."""

        def modules(directory):
            return {p.name: p.read_bytes() for p in sorted(directory.glob("*.py"))
                    if p.is_file() and not p.name.startswith("test_")}

        def gaps(source, copy):
            return ([f"absent from the copy: {n}" for n in sorted(set(source) - set(copy))]
                    + [f"different: {n}" for n in sorted(set(source) & set(copy))
                       if source[n] != copy[n]]
                    + [f"orphan in the copy: {n}" for n in sorted(set(copy) - set(source))])

        codex = modules(ROOT / ".codex" / "hooks")
        gemini = modules(ROOT / ".gemini" / "hooks")
        cited = set(re.findall(r"\.gemini/hooks/([A-Za-z0-9_]+\.py)",
                               (ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(cited), 5, f"the floor read too few cited hooks: {sorted(cited)}")
        floor = cited | {"_common.py", "safe_bash_git.py", "safe_bash_hooks.py"}
        for side, listing in (("codex", codex), ("gemini", gemini)):
            with self.subTest(floor=side):
                self.assertLessEqual(floor, set(listing), f"{side} listing below its floor")
        found = gaps(codex, gemini)
        self.assertEqual(found, [], "the gemini copy drifted from its codex source; regenerate it with "
                         "`python3 .agents/bin/hooks_jumeaux.py --ecrire`:\n" + "\n".join(found))
        # Negative controls: each mutant of the plan, applied to the copy, is NAMED.
        flipped = bytes([gemini["_common.py"][0] ^ 1]) + gemini["_common.py"][1:]
        for label, copy, source, expected in (
            ("byte", {**gemini, "_common.py": flipped}, codex, "different: _common.py"),
            ("DRIFT", {**gemini, "_common.py": gemini["_common.py"] + b"DRIFT = 1\n"}, codex,
             "different: _common.py"),
            ("missing", {k: v for k, v in gemini.items() if k != "safe_bash.py"}, codex,
             "absent from the copy: safe_bash.py"),
            ("codex only", gemini, {**codex, "nouveau.py": b"x = 1\n"}, "absent from the copy: nouveau.py"),
            ("orphan", {**gemini, "orphelin.py": b"x = 1\n"}, codex, "orphan in the copy: orphelin.py"),
        ):
            with self.subTest(control=label):
                self.assertEqual(gaps(source, copy), [expected])
        for label, listing in (("empty listing", {}),
                               ("safe_bash_git.py absent", {k: v for k, v in gemini.items()
                                                            if k != "safe_bash_git.py"})):
            with self.subTest(control=label):
                self.assertFalse(floor <= set(listing), "the floor must refuse this listing")

    # -- negative controls -------------------------------------------------

    def test_negative_control_the_runner_can_report_both_verdicts(self):
        """Proof the comparator can FAIL. If the runner returned False for
        everything, every ALLOW row above would be passing vacuously."""
        for host in ("codex", "gemini"):
            with self.subTest(host=host):
                denied, _ = self.verdict(
                    host, row("nc-deny", "safe_bash", "rm -rf src/x", DENY, "control")
                )
                self.assertTrue(denied)
                allowed, _ = self.verdict(
                    host, row("nc-allow", "safe_bash", "echo ok", ALLOW, "control")
                )
                self.assertFalse(allowed)

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_negative_control_the_claude_runner_can_report_both_verdicts(self):
        denied, message = self.verdict(
            "claude", row("nc-deny", "safe_bash", "rm -rf src/x", DENY, "control")
        )
        self.assertTrue(denied)
        self.assertIn(MOTIVE_CHECKPOINT, message)
        allowed, _ = self.verdict(
            "claude", row("nc-allow", "safe_bash", "echo ok", ALLOW, "control")
        )
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
