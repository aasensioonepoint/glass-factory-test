"""PreToolUse [Bash] — the NUMBERED guards below, one distinct motive per refusal
rule (the list is read off the `rule=` of the deny events, never closed by a
number, L-00000187), ONE recognition stage (plus the write-redirect guard of
T-00000244, described where it is built, and the fail-closed arm of the git
guards, rule git-subcommand-hidden). The git ARGUMENT judge (guards 3 to 6)
lives in the leaf sibling safe_bash_git.py, loaded like _common.

  1. `rm`/`mv` (plus the PowerShell verbs) on a tracked or source path — refused
     because it BREAKS CHECKPOINT REWIND: the operation is not replayable
     backwards. Remedy: Edit/Write. Since T-00000762 three more shapes are
     refused BY CONSTRUCTION (judge_targets, formula F2): a verb with NO operand
     (`rm`), a verb FED BY A PIPE (`xargs`, `parallel`, `find -exec|-ok`) whatever
     its static operands — the feeder is also seen inside an envelope's window
     (`nice -n 10 xargs rm …`), across a process substitution (`xargs -a <(…)
     rm …`) and behind a leading redirect (`< list xargs rm …`) — and a verb ONE
     of whose operands dissolves into an expansion (`rm -rf dist/x $HOME`, which
     used to pass on `dist/x` alone). A `mv` destination glued to its option
     (`-tDIR`, `--target-directory=DIR`) is judged, and the tracked veto is
     case-insensitive (`:(icase)`).
  2. `rg` ABSENT from PATH — refused because it MANUFACTURES FALSE CLAIMS OF
     ABSENCE: its failure is indiscernible from an empty result (`rg PAT || echo
     NONE` takes the failure branch on the 127 of command-not-found and prints
     NONE). Remedy: the host's built-in search tool, which fails loudly.
  3. An UNSCOPED GIT WIPE (T-00000762, port of the Claude homologue's guard 3) —
     `git restore|checkout .`, `git clean` (a dry run `-n` excepted), `git reset
     --hard` (every abbreviation, `--h` included), `git stash` without a
     pathspec — refused because it DESTROYS the uncommitted work of every
     agent: a never-staged edit leaves no git object and nothing in the reflog,
     and a stash lands in the stack SHARED by every session. A BROAD pathspec
     counts as none: `.`, `*`, `:/`, `:(top)`, an exclude-only one, a list read
     from stdin, an unquoted expansion. Remedy, per subcommand and always
     possible: a precise pathspec, `git reset --keep`, `git clean -n`, or
     commit first. An unquoted expansion where git reads its SUBCOMMAND (`git
     $sub .`) is refused fail-closed, rule git-subcommand-hidden.
  4. `git … --output[=<f>]` (T-00000762) — refused because it WRITES A FILE,
     tracked ones included, around Edit/Write. Remedy: `git log … > /tmp/x`.
  5. `git grep -O` / `--open-files-in-pager` (T-00000762) — refused because it
     RUNS AN ARBITRARY COMMAND on the files it finds.
  6. `git branch -D` (or `-d --force`) on a `wt/…` branch (T-00001090) — refused
     because it DESTROYS the commits only that branch carries, the unmerged work
     of a worktree dev. Remedy: `git branch -d wt/<T>` after the merge.
  Since T-00001102 git behind a chain of TABLE envelopes (`env`, `sudo`, `doas`,
  `command`, `nohup`, `time`) is read as git (scan_window); see main.

Recognition is a FOUR-STAGE port of .claude/hooks/safe-bash.sh, and the reason
it is a port rather than a rewrite is that the old matcher here was the
substring matcher that host already fixed twice: it split the payload on
`[;&|\\n]`, then read EVERY token of every segment, so a `rm` sitting in a
QUOTED task title or commit message was executed as far as the guard was
concerned, and `docker rm x` was an `rm`. Same defect, same fix, same order:

  Stage 0.5 — a heredoc BODY is redirected DATA and is blanked, but ONLY when
    the delimiter carries a quoted piece (`<<'EOF'`, `<<\\EOF`, `<<E"O"F`): with a
    NAKED delimiter bash expands `$(…)` inside the body, so that body stays
    ANALYSED and blanking it would be a fail-open. Port of the piece parser of
    T-00000210; read its section in safe_bash_git.py before touching it.
  Stage 1 — quoted segments are DATA, neutralised at CONSTANT LENGTH (`@` per
    character, never a fixed token). WHICH runs count as quoted is decided by
    quoted_spans(), which knows an ESCAPED quote opens nothing: its regex
    predecessor read `echo \\" ; rm -rf src/x \\"` as one quoted string and
    allowed a payload bash really executes. The isometry is load-bearing and is what
    an earlier revision of this patch got wrong: replacing a quoted run by a
    4-character ` @@ ` makes every offset computed on the scrubbed copy WRONG in
    the raw string from the first quoted title onwards, which is the common case
    (`tasks.py new "titre" ; rm -rf src/x`). With one `@` per character the two
    strings index identically BY CONSTRUCTION, so the segment cuts and the token
    offsets found on the scrubbed copy can be applied to the RAW payload.
  Stage 1.5 (T-01M5D6XV3J) — unquoted brace lists and sequences are EXPANDED
    as bash does (expand_braces, in safe_bash_git.py, with its bounds and its
    brace-expansion-unread refusal); the expanded text is walked in a SECOND
    pass, the first one on the text as written still standing.
  Stage 2 — the coarse cut on `[;&|\\n]` is computed on the SCRUBBED copy and
    applied to the RAW one, so a metacharacter inside quotes cannot fabricate a
    segment boundary, and a real separator still cuts.
  Stage 3 — inside a segment, UNITS are walked (walk_units) to track whether
    we stand in a POSITION OF COMMAND: a redirect's target, an expansion and a
    word glued to a substitution never take the slot, and a nested frame
    (`(`, `$(`, `<(`, a backtick) restores on close the state it interrupted.
    The walk only ever SITUATES: the verb itself is read from the SHLEX tokens
    of the RAW segment at that offset, which is what makes `"rm" -rf x`,
    `r"m" -rf x` and `sudo "rm" -rf x` recognisable here — the shell executes
    those, so a guard that reads them as data is fail-open.

WHAT MUST NOT WEAKEN. The rm/mv guard protects checkpoint rewind: its false
NEGATIVE costs far more than its false positive. The position of command is
therefore transparent to (a) separators in every form, (b) the 19 envelopes that
take a command as argument, (c) the 8 shell keywords, (d) assignments preceding a
verb (`FOO=bar rm x`), (e) the verb's path/escape/extension (`/bin/rm`, `rm.exe`,
`\\rm`), (f) `find -exec|-execdir|-ok|-okdir`, (g) a leading redirect (`< f rm
x`, `2>/dev/null rm x`) and (h) an expansion (`FOO=$x rm x`, `sudo $X rm x`).
Inside an envelope's argument window, where nobody
can tell where ITS options stop (`timeout 5 rm x`, `nice -n 10 rm x`), rm/mv fall
back to the old substring semantics — deliberately restricted to those verbs,
which are dangerous everywhere, and NOT extended to `rg`, which is dangerous only
when executed (`sudo apt install ripgrep` must not be refused).

FAIL-CLOSED, FOUR TIMES, all named rather than implied (judge_targets):
  - tokenisation that shlex REFUSES (an unbalanced quote, a trailing `\\`) is
    retried by whitespace, and a destructive verb recognised in that degraded
    state is REFUSED rather than judged on targets nobody could read;
  - a target with NO analysable literal prefix (`$HOME`, `${DIR}`, `$(pwd)`) is
    DISSOLVED, and since T-00000762 a verb ANY of whose targets dissolved is
    REFUSED — it used to take ALL of them, so `rm -rf dist/x $HOME` passed on
    `dist/x`. `tmp/$USER` is NOT dissolved — it is judged on its literal prefix
    `tmp/`;
  - a verb with NO operand left once empty tokens are dropped (`rm`) is REFUSED
    (T-00000762) — a lone `"` from an escaped quote is not an operand;
  - a verb FED BY A PIPE (`xargs`, `parallel`, `find -exec|-execdir|-ok|-okdir`)
    is REFUSED whatever its static operands (T-00000762): the operands it really
    receives are not in the text. So is a verb that follows an expansion in the
    command slot (`$X rm …`, `$(cmd) rm …`).

DIVERGENCES FROM .claude/hooks/safe-bash.sh, named because a silent one is how
two hosts drift: this file also knows the PowerShell verbs (`del`, `erase`,
`Remove-Item`, `Move-Item`) and recognises a QUOTED verb, so it is STRICTER on
those; its temp allowlist is prefix-relative (`tmp/`) where Claude's is an
ANCHORED list judged operand by operand (`/tmp/` and its resolved form, then
`.tmp`, `node_modules`, `dist`, `build`, `.cache` as a first component), so the
two disagree on `rm -rf tmp/$USER` and on `rm -rf /tmp/x` — in OPPOSITE
directions. It used to carry NO unscoped-git-wipe guard at all (it did not even
refuse `git checkout .`); T-00000762 CLOSED that by porting `decide_git` rule for
rule (judge_git below). DIVERGENCE 7 comes from the same root as the quoted
verb: this host reads a git word THROUGH its quotes. Its first statement, "the
port introduces ONE divergence", was an UNDER-COUNT, and so was the example it
gave: the closing pair of T-00000762 measured four more rows, a quoted OPTION or
SUBCOMMAND — `git reset "--hard"`, `git log "--output=x"`, `git grep "-O" x`,
`git "stash"` — refused here and allowed on Claude, whose scrub turns them into
`@@`. Those four stay divergent BY DECISION (PY_STRICTER, closing them would
cost Claude a python spawn per git command); the quoted PATHSPEC (`git checkout
-- "."`) is no longer among them, Claude now reading its content too. And
DIVERGENCE 8, pre-existing and carried by T-00000764: this host still reads a
word that is not an operand as a TARGET and refuses it — a redirect glued to an
operand (`rm -rf dist/x 2>/dev/null`), a trailing comment (`rm -rf .tmp/x #
note`), the `)` that closes a subshell (`( rm -rf .tmp/x )`) — where Claude's
per-operand pass drops the redirect with its target and stops at the comment
and at the `)`. DIVERGENCE 9 is CLOSED (T-00000762, decision 6): `_ROOT_RM`
read ANY rm operand ending in `/` as the root and `is_allowed_target` refused
the listed directory itself, so `rm -rf ./node_modules/` and `rm -rf dist` were
refused here and allowed on Claude. Every divergence is pinned, host by host,
in .agents/evals/test_guard_decision_parity.py; a payload whose verb is itself
quoted-and-nested (`bash -c "rm x"`) is an ASSUMED hole, pinned there too.
"""
import hashlib
import re
import shlex
import shutil
import sys

from _common import (
    command_from_payload,
    deny,
    emit_event,
    git_tracked,
    normalize_path,
    normalize_path_checked,
    read_payload,
    ROOT,
)
# The git ARGUMENT judge and stages 0.5/1, in the LEAF sibling (stdlib only, never imports this file).
from safe_bash_hooks import _double_open
from safe_bash_git import (BRANCH_FORCE_REASON, ENVELOPES, _ANSI_UNREAD, _EXPANSION_MARK, _GIT_GLOBAL_VALUE,
                           _long_option, alias_assignment, expand_braces, hooks_refusal, judge_git, quoted_spans,
                           read_ansi, strip_heredoc_bodies)

# WRITE-REDIRECTION guard (T-00000244), the SECOND clause read from the CANONICAL
# path guard rather than copied: this family imports protect_paths, its own
# sibling (the Claude homologue extracts the patterns textually from
# protect-paths.sh — chaque famille lit LE SIEN). A `\rm`-shaped hole existed for
# `>`/`>>`/`tee`/`python -c`, and the write-redirect form is the one the measure
# (core-scripts/measure_shell_write_fp.py) retained: FP 0.033% of executed commands,
# zero red on the closed polarity forms (T-00000244's corpus). REMEASURED on
# 2026-09-26 for the predicate of T-00000721 (throwaway clones at 9582d114 and
# bab7ea2f, same corpora): raw positives 0/3762 on this repo's transcripts (all
# post-guard, so blind to its own refusals) and 3 -> 12/10428 on the older
# sibling-checkout corpus; of the 9 new, 2 wrote by redirect the marker of the
# local dev route, since retired (true positives then, T-00000750) and 7 are `.git/config`-style writes after a `cd`
# into a scratch repo (false positives: a relative target is judged against the
# root, never the cd) — FP +0.067%. The measure PORTS this exact predicate,
# so the two never drift. STRICT branch, said out loud: when protect_paths cannot
# be read the protected-path CLAUSE is announced-off (git-tracked writes stay
# guarded) rather than silently dropped — never an empty exemption.
try:
    import protect_paths as _protect_paths
    _protected_reason = _protect_paths.protected_reason
except Exception:  # pragma: no cover - the sibling is always present in a checkout
    _protect_paths = None
    _protected_reason = None


ALLOW_PREFIXES = (
    "tmp/",
    "temp/",
    ".tmp/",
    "dist/",
    "build/",
    "coverage/",
    "node_modules/",
    ".next/",
)

# The verbs whose effect is not replayable backwards. The four PowerShell ones
# are this host's own addition (Codex/Copilot/Gemini run on Windows boxes where
# they are the ordinary spelling) and a divergence from the Claude homologue,
# which knows only rm/mv.
DESTRUCTIVE = frozenset(
    {"rm", "mv", "del", "erase", "remove-item", "move-item"}
)

# Envelopes: they TAKE a command, so the position of command stays OPEN behind
# them — without this list `sudo rm x`, `xargs rm` and `timeout 5 rm x` are false
# negatives. `sh`/`bash` are deliberately ABSENT: their payload is QUOTED, hence
# already neutralised by stage 1 (assumed hole, pinned in the parity eval).
# ENVELOPES lives in safe_bash_git.py since T-01M5D6XV3J (imported above): ONE
# table for this walk and for stage 1.5, which skips them before the command word.

# Keywords: `if [ x ]; then rm f; fi`, `for f in *; do rm $f; done` — without
# `then`/`do` the rm no longer stands in a position of command and walks free.
KEYWORDS = frozenset("if then elif else do while until ! coproc".split())

# PRESENCE PROBES print a path or fail; they never run the name they resolve. A
# `which rm` deletes nothing and a probe on `rg` cannot manufacture the false
# emptiness guard 2 exists to catch, since its output is about presence and not
# about occurrences. Measured on this kit's Claude homologue: `command -v rg` was
# REFUSED — the guard blocked the very command that diagnoses the failure it
# describes. `command` is not in this set because it is an ENVELOPE: only its
# `-v`/`-V` form is a probe (handled in the walk).
PROBES = frozenset("which type hash whence".split())

# T-00001102 : TABLES FERMÉES (options SANS valeur, options À valeur séparée) des six enveloppes dont on
# PROUVE l'arité ; tout le reste est ambigu (scan_window). ENVELOPES ci-dessus reste la liste COMPLÈTE.
ENVELOPE_OPTIONS = {
    "env": (frozenset("- -i -0 --ignore-environment --null --debug --list-signal-handling --block-signal --default-signal --ignore-signal --".split()),
            frozenset("-u -C -P -a --unset --chdir --argv0".split())),
    "sudo": (frozenset("-A -B -b -E -H -k -N -n -P -S -i -s --askpass --bell --background --preserve-env --set-home --reset-timestamp --login --non-interactive --preserve-groups --stdin --shell --no-update --".split()),
             frozenset("-C -D -g -p -R -T -U -u -r -t --close-from --chdir --group --prompt --chroot --command-timeout --other-user --user --role --type".split())),
    "doas": (frozenset("-L -n -s --".split()), frozenset("-C -u".split())),
    "command": (frozenset("-p --".split()), frozenset()),
    "nohup": (frozenset(["--"]), frozenset()),
    "time": (frozenset("-p --".split()), frozenset()),
}

# Stages 0.5 and 1 (quoted_spans, strip_heredoc_bodies) live in safe_bash_git.py
# since T-01M5D6XV3J, imported above by name; read their comment blocks there.

# Stage 2's coarse cut. Only the TRUE separators: the wider class of the walk
# below is for SITUATING a command position, never for cutting, because cutting
# on `$` would dissolve `rm -rf $HOME` into a verb with no target at all — a
# refusal LOST, which is the direction that must never happen here. A `|` or
# `&` that belongs to a REDIRECT OPERATOR is not a separator: `>|` bypasses
# noclobber and `>&` duplicates a fd or names a FILE (T-00000698, third
# correction, M3/M4), and since T-00000762 `<&` and `&>`/`&>>` too — `rm build/x
# &>/dev/null src/a.py` was cut at the `&`, so `src/a.py` fell into a segment of
# its own and the rm passed on the strength of `build/x` alone, on all three
# hosts (measured). `a || b`, `ls | grep x`, `a & b`, `2>&1 && next` cut where
# they did.
_COARSE_CUT = re.compile(r"[;\n]+|(?<![<>])(?!&>)[&|]+")
# T-01M5F4GJZD: on a RAW segment of these only, quotes included, bash only splits words, honours comments (read fail-closed), redirections, assignments and reserved words (a `{ …; }` group is refused unread), expands braces and removes quotes — all reproduced by pass 2 or refused (bounded by the bn*/brace/* benches and a list differential, not proven).
_REREAD_SAFE = re.compile(r"""[A-Za-z0-9 \t{},._/@:=+%#<>&'"-]*""")

# Stage 3, the WALK — rewritten by T-00000762 after the closing pair of its
# first pass. It used to fold every one of `|;&(){}$<>` and backtick into a
# separator that REOPENED the position of command, and that was not the safe
# direction it looked like: whatever word followed took the command slot and
# hid the real verb behind it. `< list.txt rm -rf src/x`, `> out.txt rm -rf
# src/x`, `2>/dev/null rm -rf src/x`, `sudo $X rm -rf src/x` and `FOO=$x rm -rf
# src/x` all passed on the three hosts (measured), because `list.txt`,
# `out.txt`, `2`, `X` and `x` were read as the command. The walk now reads
# UNITS that say what bash reads (walk_units):
#   - a REDIRECT operator (`<`, `>`, `>>`, `2>`, `2>&1`, `&>`, `>|`, `<<<`,
#     `<<`…), its fd number included: its TARGET word never takes the slot;
#   - an EXPANSION (`$x`, `$1`, `$@`, `${x}`) is part of its WORD, never a
#     separator; a word that STARTS with one, in the command slot, is an
#     unknown command, so what follows is judged as an envelope's window, FED;
#   - `(`, `$(`, `<(`, `>(`, a backtick and a `${…}` holding a substitution
#     OPEN a nested frame, and the matching close RESTORES the state it
#     interrupted — so the `fed` of `xargs -a <(git ls-files) rm -f build/x`
#     survives the substitution. Frames persist across the coarse segments of
#     ONE command (a `;` inside `<(a; b)` cuts a segment, not the frame); a `)`
#     that nothing opened (a `case` pattern) starts a command, like `;`;
#   - `|` `;` `&`, and a `{`/`}` that is not a `${…}`, reset everything.
_UNIT_REDIR = re.compile(r"[0-9]*(?:&>>|&>|<<<|<<-|<<|<>|>>|>&|<&|>\||>|<)")
_UNIT_STOP = frozenset(" \t|;&()<>`{}")
_SIMPLE_BRACE = re.compile(r"\$\{[^}$`(]*\}")


def walk_units(scrubbed, frames=None):
    """`[(kind, start, end, sub, glued)]` over one coarse segment's SCRUBBED
    text, offsets valid in the RAW one (the scrub is isometric). `frames` is
    the pairing state of the opens (backticks, `${`), carried by the caller
    from one segment of the command to the next.

    `kind` is `sep`, `redir`, `open`, `close` or `word`. For an `open`, `sub`
    says which (`sub` for `$(`, `bt` for a backtick, `param` for a `${…}` that
    holds a substitution, `proc` for `<(`/`>(`, `par` for a plain `(`), and a
    `close` carries the kind it closed ("" when it closes nothing here); for a
    `word`, `sub` is `exp` when it holds an UNQUOTED expansion. `glued` says
    the unit continues a word (`FOO=$(…)`, `$(…)x`), so it takes no slot."""
    units = []
    frames = [] if frames is None else frames
    i, n = 0, len(scrubbed)
    while i < n:
        ch = scrubbed[i]
        if ch in " \t":
            i += 1
            continue
        glued = (i > 0 and scrubbed[i - 1] not in _UNIT_STOP) or bool(
            units and units[-1][0] == "close" and units[-1][2] == i
            and units[-1][3] in ("sub", "bt", "param")
        )
        nxt = scrubbed[i + 1] if i + 1 < n else ""
        if ch in "<>" and nxt == "(":
            frames.append("proc")
            units.append(("open", i, i + 2, "proc", glued))
            i += 2
            continue
        if ch == "$" and (nxt == "(" or (nxt == "{" and not _SIMPLE_BRACE.match(scrubbed, i))):
            sub = "sub" if nxt == "(" else "param"
            frames.append(sub)
            units.append(("open", i, i + 2, sub, glued))
            i += 2
            continue
        redir = _UNIT_REDIR.match(scrubbed, i)
        if redir:
            units.append(("redir", i, redir.end(), "", False))
            i = redir.end()
            continue
        if ch == "(":
            frames.append("par")
            units.append(("open", i, i + 1, "par", glued))
        elif ch == "`" and not (frames and frames[-1] == "bt"):
            frames.append("bt")
            units.append(("open", i, i + 1, "bt", glued))
        elif ch in ")`" or (ch == "}" and frames and frames[-1] == "param"):
            units.append(("close", i, i + 1, frames.pop() if frames else "", False))
        elif ch in "|;&{}":
            units.append(("sep", i, i + 1, "", False))
        else:
            j = i
            while j < n and scrubbed[j] not in _UNIT_STOP:
                if scrubbed[j] == "$" and j + 1 < n and scrubbed[j + 1] in "({":
                    simple = _SIMPLE_BRACE.match(scrubbed, j)
                    if not simple:
                        break
                    j = simple.end()
                    continue
                j += 1
            if j == i:
                j = i + 1
            units.append(("word", i, j, "exp" if "$" in scrubbed[i:j] else "", glued))
            i = j
            continue
        i += 1
    return units

# `FOO=bar rm x`: an assignment does not close the position of command.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][0-9A-Za-z_]*=")

# Where a target stops being a LITERAL path. Everything from the first expansion
# onward is unknown at hook time: `$HOME`, `${DIR}`, `$(pwd)`, a backtick.
_EXPANSION = re.compile(r"[$`]")

# `rm -rf /` — root EXACTLY, applied to the SCRUBBED segment, so a task title
# QUOTING a catastrophic rm is data, like every other quoted mention. The last
# operand must be a BARE `/` (T-00000762, decision 6): the old tail `/\s*$`
# read ANY operand ending in `/` as the root, so `rm -rf dist/` and `rm -rf
# ./node_modules/` were refused as catastrophic here and allowed on Claude —
# DIVERGENCE 9, closed.
_ROOT_RM = re.compile(r"\brm\s+-[^\n]*[rf][^\n]*\s/\s*$")


def scrub_quoted(command):
    """Neutralise each quoted segment, PRESERVING ITS LENGTH.

    `@` is chosen because it is neither whitespace nor a walk metacharacter: a
    quoted run therefore stays a single token and can never fabricate either a
    segment boundary or a position of command. The isometry is what lets every
    offset found here index the RAW payload — see stage 1 in the module header.
    A payload with no quotes at all comes back byte-identical, which is the
    guarantee that this stage can never make the guard ALLOW a naked `rm`.

    WHAT COUNTS AS QUOTED is decided by quoted_spans(), which knows that an
    escaped quote opens nothing — read its docstring before touching this.
    """
    out, last = [], 0
    for start, end in quoted_spans(command):
        out.append(command[last:start])
        out.append("@" * (end - start))
        last = end
    out.append(command[last:])
    return "".join(out)


def coarse_segments(command, scrubbed=None):
    """`[(raw, scrubbed)]` — cut on the SCRUBBED copy, sliced from BOTH.

    The two members of each pair have the same length and the same indices, so a
    token offset found in one is valid in the other. `scrubbed` is given when the
    pair was built together (stage 1.5 expands both alike).
    """
    scrubbed = scrub_quoted(command) if scrubbed is None else scrubbed
    segments, start = [], 0
    for cut in _COARSE_CUT.finditer(scrubbed):
        segments.append((command[start:cut.start()], scrubbed[start:cut.start()]))
        start = cut.end()
    segments.append((command[start:], scrubbed[start:]))
    return segments


def tokenize(text):
    """`(tokens, honest)` — shlex, or whitespace when shlex REFUSES.

    `honest` is False on the fallback path and that flag is the whole point:
    shlex raises on an unbalanced quote or a trailing `\\` (a line continuation),
    and a whitespace split of such a payload is a GUESS. The caller refuses
    rather than judging targets it cannot read.
    """
    try:
        return shlex.split(text, posix=True), True
    except ValueError:
        return text.split(), False


def executed_word(token):
    """The word the SHELL would execute for one walk token, and whether it could
    be read honestly. `r"m"` -> `rm`; `"rm"` -> `rm`; `@@@@` never reaches here
    (the walk hands over the RAW slice, not the scrubbed one). An unquoted `$'…'` is DECODED first (read_ansi,
    T-01M5D6XV3J): `$'-D'` -> `-D`; an unreadable one reads as an unquoted expansion."""
    words, honest = tokenize(read_ansi(token))
    return (words[0] if words else ""), honest


def base_name(word):
    """`/bin/rm` -> `rm`, `rm.exe` -> `rm`, `\\rm` -> `rm` (an alias bypass is not
    a guard bypass), `C:\\tools\\rm.cmd` -> `rm`."""
    raw = word[1:] if word.startswith("\\") else word
    base = raw.lower().replace("\\", "/").split("/")[-1]
    return re.sub(r"\.(?:cmd|exe)$", "", base)


def git_subcommand_unit(raw_segment, units, index):
    """Unit index of the word git reads as its SUBCOMMAND after the `git` at `units[index]` (global options
    skipped, those with a SEPARATE value with their value, as judge_git), when that word is rm or mv, else -1."""
    skip = False
    for pos in range(index + 1, len(units)):
        kind, start, end, sub, glued = units[pos]
        if kind == "redir":
            skip = True
            continue
        if kind != "word":
            return -1
        if skip:
            skip = False
            continue
        if glued:
            continue
        word = executed_word(raw_segment[start:end])[0]
        if word in _GIT_GLOBAL_VALUE:
            skip = True
            continue
        if word.startswith("-"):
            continue
        return pos if base_name(word) in ("rm", "mv") else -1
    return -1


def scan_window(raw_segment, units, index, env):
    """`(state, unit_index)` — the envelope is at `units[index]`, in position of command. READ what
    follows WITHOUT changing anything, to learn which word will be the real command. `state` is "none"
    (nothing to add: the base walk goes on alone), "amb" (an option outside the tables, a value with an
    expansion, an envelope outside the tables, an opaque unit: the window cannot be PROVEN) or "git"
    (git PROVEN in position of command at `unit_index`: a chain of table envelopes, no ambiguity)."""
    amb = evn = False
    for pos in range(index + 1, len(units)):
        kind, start, end, sub, glued = units[pos]
        if kind in ("sep", "close"):
            return ("amb" if amb else "none"), 0
        if kind != "word":
            return "amb", 0
        if glued:
            continue
        raw = raw_segment[start:end]
        quoted = "'" in raw or '"' in raw
        word = executed_word(raw)[0]
        if evn:
            evn = False
            amb = amb or sub == "exp"
            continue
        if quoted and not _ASSIGNMENT.match(raw):
            return "amb", 0
        if word.startswith("-"):
            plain, valued = ENVELOPE_OPTIONS[env]
            if word in plain:
                continue
            if word in valued:
                evn = True
                continue
            if word.startswith("--"):
                name, eq, _value = word.partition("=")
                if eq and (name in plain or name in valued):
                    amb = amb or sub == "exp"
                    continue
            elif len(word) > 2 and word[:2] in valued:
                amb = amb or sub == "exp"
                continue
            amb = True
            continue
        if env in ("env", "sudo") and _ASSIGNMENT.match(word):
            amb = amb or sub == "exp"
            continue
        if sub == "exp" and word.startswith("$"):
            return "amb", 0
        base = base_name(word)
        if base in ENVELOPE_OPTIONS:
            env = base
            continue
        if base in ENVELOPES:
            return "none", 0
        if base == "git":
            return ("amb", 0) if amb else ("git", pos)
        return ("amb" if amb else "none"), 0
    return ("amb" if amb else "none"), 0


def is_allowed_target(path):
    """`path` must ALREADY be normalized (judge_targets does it once).

    This compares, it no longer normalizes: normalize_path() drops a trailing
    separator, so re-normalizing here turned the literal prefix `tmp/` of
    `rm -rf tmp/$USER` back into `tmp`, which matches no `tmp/` entry — the
    allowlist silently stopped applying to every directory-only prefix. Measured
    while writing the parity matrix: that row denied on this host for a reason
    that had nothing to do with its target. Callers already pass normalized
    input, so no other behaviour moves.

    The listed directory ITSELF is accepted too (T-00000762, decision 6):
    `rm -rf dist` normalizes to `dist`, which starts with no `dist/` entry, so
    the whole build output was refused while every file under it passed.
    """
    lowered = path.lower()
    return any(
        lowered.startswith(prefix) or lowered == prefix.rstrip("/") for prefix in ALLOW_PREFIXES
    )


def literal_prefix(target):
    """The leading run of a target that is a literal path, i.e. everything before
    the first shell expansion. `tmp/$USER` -> `tmp/` (judged, and allowed);
    `$HOME` -> `` (DISSOLVED, and refused when nothing else is judgeable)."""
    expansion = _EXPANSION.search(target)
    return target[: expansion.start()] if expansion else target


def command_fingerprint(command):
    """`(unsalted sha256, character length)` of the denied command — and NEVER
    the command itself, not even truncated.

    This guard operates on a whole shell COMMAND, which is model-controlled and
    can legitimately carry a live credential (`curl -H "Authorization: Bearer
    <token>" ... && rm -rf /`). gitleaks scans Edit/Write content and the
    working-tree diff, never a hook's own JSONL append, so such a string in the
    event stream would land unredacted where the class-0 gate cannot see it —
    the exact incident recorded as L-00000043. A substring blocklist was
    rejected there as the primary defence (enumerate-instead-of-normalize,
    L-00000042); a hash carries no payload by construction.

    UNSALTED on purpose, same accepted tradeoff as .claude/hooks/safe-bash.sh:
    the digest is a stable cross-session correlation key, which is precisely the
    de-duplication property the audit trail wants. It also lets a party who
    already knows a candidate command confirm a match — rated low, and accepted
    rather than hidden. Keeping the algorithm identical to the Claude hook is
    also what makes the two hosts byte-comparable for the same command.

    The length is an INT (T-00000042). It used to be a decimal STRING here
    only because that is what the wire already carried: emit-event.sh's
    `key=value` form stringifies every field, and Claude's safe-bash.sh used
    it, so `"cmd_len": "94"` was the de facto format. A count that reads as a
    string is a small lie a consumer has to undo, and two JSON types under one
    field name (per denying host) is worse — so the fix was made on ALL FOUR
    hosts at once: Claude now emits it through `key:=<json>`, which parses the
    literal, and the parity eval asserts the type, not merely the presence.

    TOTAL since T-00000785: it runs AFTER deny() has printed, so a strict
    encode that raised on a lone surrogate turned a refusal into rc 1.
    `surrogatepass` is byte-identical to strict UTF-8 for every command that
    has a UTF-8 form (no digest already emitted moves) and injective on the
    rest — unlike `backslashreplace`, whose output collides with the TEXT
    `\\ud800`.
    """
    return (
        hashlib.sha256(command.encode("utf-8", "surrogatepass")).hexdigest(),
        len(command),
    )


def faithful_bytes(command):
    """True when `command` has ONE byte form a shell receives as written
    (T-00000785). The class is CLOSED, not enumerated: strict UTF-8 refuses
    exactly the lone surrogates (every other code point has a UTF-8 form, and
    a host must drop or replace one it cannot encode), and NUL is the one
    encodable code point no argv string carries. Holds for a STRING command
    only: command_from_payload() stringifies a list with str(), whose repr
    escapes a NUL into four ASCII characters — a list-form command is not
    judged (T-00000795)."""
    if "\x00" in command:
        return False
    try:
        command.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def judge_targets(raw_segment, offset, honest, fed):
    """`(unsafe, why)` for a destructive verb recognised at `offset`.

    Targets are read from the SHLEX tokens of the RAW segment starting at the
    verb, and each one is judged git-tracked OR outside the temp/build
    allowlist = unsafe — tested in the order `not is_allowed_target(c) or
    git_tracked(c)`: the same verdict, and no git subprocess for a target that
    is already outside the list (T-00000762).

    `why` names a refusal that carries NO path, "" when there is none. Formula
    F2 (T-00000762): refuse iff `fed or not targets or judged < len(targets)`,
    where F0 read `bool(targets) and judged == 0` and let two shapes through:
      - "fed"       the verb is fed by a pipe (`xargs`, `parallel`,
                    `find -exec|-execdir`, flag held by main()): the operands it
                    really receives are not in the text, so no static operand
                    can make it safe — tested FIRST, so that a form shlex also
                    refuses (`find … {} \\;`) is refused for THIS reason;
      - "shlex"     shlex refused the tokenisation (unbalanced quote, trailing
                    backslash): targets nobody could read;
      - "empty"     no operand at all (`rm`, or `git ls-files | xargs rm -f`
                    read without its pipe) — F0 let it through;
      - "dissolved" at least ONE target has no literal prefix (`$HOME`): a
                    PARTIAL dissolution is refused too (`rm -rf dist/x $HOME`,
                    which F0 allowed on the strength of `dist/x` alone).
    Tokens left EMPTY by quote stripping are dropped BEFORE the count: the lone
    `"` of an escaped quote (`echo \\" ; rm -rf .tmp/x \\"`) is not an operand,
    and counting it would refuse that allowlisted rm as "dissolved". A `mv`
    destination GLUED to its option (`-tDIR`, `--target-directory=DIR`,
    `--targ=DIR`) is an operand too (T-00000762, second pass): it used to be
    skipped with the option, so `mv -tsrc build/x` passed. The git-tracked veto
    is CASE-INSENSITIVE (`:(icase)`): on a case-insensitive filesystem (APFS,
    NTFS) `rm build/KEEP.txt` deletes the tracked `build/keep.txt`; on a
    case-sensitive one it names another file, and the veto is then a harmless
    over-refusal. `unsafe` and a `why` can both be set. Only caller: main().
    """
    if fed:
        return [], "fed"
    tokens, readable = tokenize(raw_segment[offset:])
    if not (readable and honest):
        return [], "shlex"
    operands = [t for t in tokens[1:] if not t.startswith("-")]
    if tokens and base_name(tokens[0]) == "mv":
        glued_targets = (_mv_glued_target(t) for t in tokens[1:] if t.startswith("-"))
        operands += [glued for glued in glued_targets if glued]
    targets = [stripped for stripped in (t.strip("\"'") for t in operands) if stripped]
    if not targets:
        return [], "empty"
    unsafe, judged = [], 0
    for target in targets:
        prefix = literal_prefix(target)
        if not prefix.strip():
            continue
        candidate, resolved = normalize_path_checked(prefix)
        if not candidate:
            continue
        # normalize_path() drops a trailing separator, which would turn the
        # literal prefix `tmp/` into `tmp` and make it miss the `tmp/` allowlist
        # entry — the target would flip from allowed to refused for a reason that
        # has nothing to do with the target.
        if prefix.endswith(("/", "\\")) and not candidate.endswith("/"):
            candidate += "/"
        judged += 1
        # T-00000785: a candidate whose RESOLUTION failed is refused BEFORE the
        # allowlist is read, whatever the cause — a NUL, a lone surrogate, an
        # OSError. normalize_path() then hands back the UNRESOLVED text, and
        # `tmp/../\ud800/../.agents` starts with `tmp/`: compared as is, a
        # path no shell receives rode the list (pass 1 tested the NUL alone,
        # S-00002872). main() refuses the NUL and surrogate commands first
        # (R2); this keeps the function's own contract whatever its caller,
        # and covers the OSError arm main() cannot see.
        if (
            not resolved
            or not is_allowed_target(candidate)
            or git_tracked(":(icase)" + candidate)
        ):
            unsafe.append(candidate)
    return unsafe, ("dissolved" if judged < len(targets) else "")


def _mv_glued_target(word):
    """The destination a `mv` OPTION carries glued to it — `-tDIR`, `-ftDIR`,
    `--target-directory=DIR` and its abbreviations down to `--t=DIR` — or "".
    A separate `-t DIR` needs nothing: DIR is an operand word and is judged.
    `-S` takes a suffix, so a short cluster stops there."""
    if word.startswith("--"):
        matched, value = _long_option(word, "target-directory", 1)
        return (value or "") if matched else ""
    for position in range(1, len(word)):
        if word[position] == "S":
            return ""
        if word[position] == "t":
            return word[position + 1:]
    return ""


# --- The git judge (T-00000762) lives in safe_bash_git.py; git_words stays here, beside the walk
# whose units it reads (executed_word). Read the comment block of safe_bash_git.py first.
def git_words(raw_segment, scrubbed_segment, units, index):
    """`(words, stop, globs)` — the words handed to the `git` at `units[index]`, up to the next separator, subshell or
    substitution, each read through its quotes (`$'-D'` DECODED to `-D`, read_ansi), a comment's words included, a redirect
    skipped with its target. A word holding a `$` outside quotes, escaped or not (`$b`, `\\$b`, a simple `${b}`), gets
    `_EXPANSION_MARK` appended (`'$b'` does not). `stop` is "subst" when a `$(`, a backtick, or a `${…}` holding a `$`, a
    backtick or a `(`, or left unclosed, ended the words (the subcommand may hide there) — any other `${…}` stays in its
    word up to its FIRST `}` (`${x:-{y}}` leaves one) —, "brace" when a `{`/`}` did (bash keeps it IN the word or expands it: `@{-1}`, `{a,b}`), "" otherwise.
    `globs` holds the indices of the words carrying `*`, `?` or `[` OUTSIDE quotes (T-01M5D6XV3J, read by the clean credit)."""
    words, skip, globs = [], False, set()
    for kind, start, end, sub, _glued in units[index + 1:]:
        if kind == "redir":
            skip = True
            continue
        if kind != "word":
            return words, ("subst" if kind == "open" and sub in ("sub", "bt", "param") else "brace" if scrubbed_segment[start] in "{}" else ""), globs
        if skip:
            skip = False
            continue
        if any(c in scrubbed_segment[start:end] for c in "*?["):
            globs.add(len(words))
        word = executed_word(raw_segment[start:end])[0]
        words.append(word + _EXPANSION_MARK if sub == "exp" else word)
    return words, "", globs


def hook_words(raw_segment, scrubbed_segment, units, index):
    """git_words for the git-hooks-bypass rule ALONE (T-01M5C1AF6GB3ZRX5QF9SF6R80Y, after develop's T-01M5D6XS2S). A
    `$(…)` or backtick opened INSIDE double quotes (`"wip $(date)"`, `"$(git branch --show-current)"`: read from its
    word's start, a `"` is open there — the 7th column of the Claude span table) is one word whatever it prints. It no longer ends the words — it is joined to its two pieces
    into ONE opaque word, and the words after it are read: `git commit -m "$(…)" --no-verify` stays refused. The
    other git arms keep git_words' cut. Bound, named: one still OPEN at the end of the segment (a heredoc
    inside it: `-m "$(cat <<'EOF'` …) ends the words there, so an option after its close is unread."""
    kept, tail, k = [units[index]], units[index + 1:], 0
    while k < len(tail):
        kind, start, end, sub, glued = tail[k]
        if (kind == "open" and sub in ("sub", "bt") and glued and kept[-1][0] == "word"
                and kept[-1][2] == start and _double_open(raw_segment[kept[-1][1]:start])):
            depth, m = 1, k + 1
            while m < len(tail) and depth:
                depth += 1 if tail[m][0] == "open" else -1 if tail[m][0] == "close" else 0
                m += 1
            if depth:  # closed in a later segment: the walk reads on after its close (hook_pending)
                return git_words(raw_segment, scrubbed_segment, kept, 0) + (index + 1 + k,)
            if (not depth and m < len(tail) and tail[m][0] == "word" and tail[m][4]
                    and scrubbed_segment[tail[m][1]] == "@"):
                first = kept.pop()
                kept.append(("word", first[1], tail[m][2], first[3], first[4]))
                k = m + 1
                continue
        kept.append(tail[k])
        k += 1
    return git_words(raw_segment, scrubbed_segment, kept, 0) + (-1,)


# --- The WRITE-REDIRECT parser and its judge (T-00000244) -------------------
# PORTED, not reinvented: core-scripts/measure_shell_write_fp.py carries the identical
# scan, and it is the file this predicate was MEASURED with — so the guard and
# its measurement cannot drift. It runs on the coarse segments AFTER the heredoc
# stage and the isometric scrub, so a `>` living in a quoted string or a
# quoted-delimiter heredoc body is already neutralised, exactly as for rm/mv.
_REDIR_WORD_STOP = frozenset(" \t;&|(){}<>`\n")

# `>&word` is a fd DUPLICATION only when word is digits or `-` (`2>&1`, `>&-`,
# `3>&4-`); any other word is a FILE bash opens for stdout+stderr (`printf y >&
# MARKER`, measured created — T-00000698, third correction, M3).
_FD_DUP_WORD = re.compile(r"[0-9]*-?")


def opaque_expansion_end(s, pos):
    """End (exclusive) of the `${…}`, `$(…)` or backtick span opening at `pos`
    on the SCRUBBED copy, or -1 when it does not close inside `s`.

    Walked as an OPAQUE part of a redirect target word so its literal LAST
    segment is still judged (`${D}/MARKER`, `$(pwd)/MARKER` — T-00000698,
    third correction, M2): the `{`/`(`/backtick members of _REDIR_WORD_STOP used
    to cut the word at `$`, leaving nothing to compare. Braces and parentheses
    nest; quotes are already `@` here. An expansion the coarse cut split
    (`$(a | b)/x`) does not close inside its segment and is left to the old cut.
    """
    n = len(s)
    if s[pos] == "`":
        end = s.find("`", pos + 1)
        return -1 if end < 0 else end + 1
    if s[pos] != "$" or pos + 1 >= n or s[pos + 1] not in "{(":
        return -1
    open_ch = s[pos + 1]
    close_ch = "}" if open_ch == "{" else ")"
    depth, i = 0, pos + 1
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def redirect_write_targets(analysable):
    """`[(raw_target, category)]` for every WRITE redirection.

    `category` is `literal` (a target to judge), `invisible-quoted` (`> "x"`),
    `invisible-expansion` (`> $VAR`) or `no-target`. The PASS forms — descriptor
    duplication (`>&N`, `N>&M`, `>&-`) and input (`<`) — are not returned at all;
    `>&word` with any OTHER word is a write to that file and IS returned. The
    target is read from the RAW segment at the offsets found on the SCRUBBED one,
    which the isometric scrub makes valid; a `${…}`, `$(…)` or backtick span
    inside the word is walked opaquely (opaque_expansion_end) so `${D}/x` yields
    the whole word, not `$`.
    """
    found = []
    for raw_seg, scrubbed in coarse_segments(analysable):
        s, r = scrubbed, raw_seg
        n = len(s)
        i = 0
        while i < n:
            ch = s[i]
            if ch == "<":
                i += 1
                continue
            if ch != ">":
                i += 1
                continue
            if i > 0 and s[i - 1] == ">":     # second '>' of a '>>' already read
                i += 1
                continue
            op_end = i + 2 if (i + 1 < n and s[i + 1] == ">") else i + 1
            if op_end < n and s[op_end] == "|":       # '>|' bypasses noclobber
                op_end += 1
            t = op_end
            while t < n and s[t] in " \t":
                t += 1
            if t < n and s[t] == "&":          # '>&word': fd dup, or a FILE
                w = t + 1
                while w < n and s[w] in " \t":
                    w += 1
                we = w
                while we < n and s[we] not in _REDIR_WORD_STOP:
                    we += 1
                if _FD_DUP_WORD.fullmatch(s[w:we]):   # '>&N' / 'N>&M' / '>&-'
                    i = op_end
                    continue
                t = w                              # '>& out' writes `out` (M3)
            te = t
            while te < n:
                if s[te] in "$`":
                    end = opaque_expansion_end(s, te)
                    if end > 0:
                        te = end
                        continue
                if s[te] in _REDIR_WORD_STOP:
                    break
                te += 1
            raw_target = r[t:te]
            if not raw_target:
                found.append(("", "no-target"))
            elif raw_target[:1] in ("'", '"'):
                found.append((raw_target, "invisible-quoted"))
            else:
                prefix = literal_prefix(raw_target)
                if not prefix.strip():
                    found.append((raw_target, "invisible-expansion"))
                else:
                    found.append((raw_target, "literal"))
            i = op_end
    return found


# --- The NAME rule of the write-redirect guard (T-00000698, correction) -----
# The closing pair measured on the live hooks that two forms ARMED a marker
# with no refusal: `cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE`
# (a cd hides the DIRECTORY from the root-relative resolution, so the target
# reads as `<root>/PUSH_DEFAUT_AUTORISE`, which no suffix matches) and
# `printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"` (a quoted target is
# invisible to the path clauses by construction). The NAME hides from neither.
# So the LAST SEGMENT of every redirect target — bare, quoted, or under an
# expanded directory — is judged, case-folded, against the arming markers the
# canonical path guard of this family names; the list is DERIVED from its
# `*_SUFFIX` constants at call time, never a third copy. Closed list, by
# design: the general cd/quote case for an ORDINARY target is T-00000720, not
# this rule — `cd docs && echo x > notes.txt` is unchanged.
_ARMING_MARKER_DIR = ".agents/state/gates/"


def arming_marker_names():
    """The last segment of every `*_SUFFIX` constant of protect_paths whose value
    lives under `.agents/state/gates/`, already case-folded there. Empty when the
    sibling is unreadable — the same event that turns the protected clause off."""
    if _protect_paths is None:
        return frozenset()
    names = set()
    for attr in dir(_protect_paths):
        value = getattr(_protect_paths, attr, None)
        if attr.endswith("_SUFFIX") and isinstance(value, str) \
                and value.startswith(_ARMING_MARKER_DIR):
            names.add(value.rsplit("/", 1)[-1].lower())
    return frozenset(names)


def arming_marker_target(raw_target, names):
    """`(as_written, last_segment_folded, how)` when the target's last segment
    names an arming marker, else None. The ONE place a quoted target is read:
    shlex unquotes it (an unbalanced quote falls back to a strip). The last
    segment must itself be literal — `$D/KICKOFF_REQUIRED`, `${D}/…`, `$(pwd)/…`
    are judged on `KICKOFF_REQUIRED`; `$NAME` and `${X}KICKOFF_REQUIRED` have
    no literal segment to compare and pass."""
    if not raw_target or not names:
        return None
    try:
        words = shlex.split(raw_target, posix=True)
        word = words[0] if words else ""
    except ValueError:
        word = raw_target.strip("\"'")
    last = word.replace("\\", "/").rsplit("/", 1)[-1]
    # Minusculisé PUIS replié NT (T-00000722, `_protect_paths._nt_fold`), et le
    # test d'expansion porte sur CHAQUE candidat APRÈS son pli : le pli retire le
    # `$` de `MARKER::$DATA`, qui est le marqueur sous NTFS.
    for folded in (last.lower(), _protect_paths._nt_fold(last)):
        if folded and not _EXPANSION.search(folded) and folded in names:
            how = "quoted" if ("'" in raw_target or '"' in raw_target) else "bare"
            return raw_target, folded, how
    return None


def judge_redirect(raw_target):
    """`('git', None)` / `('protected', rule)` / `('pass', None)` for one literal
    redirect target — refuse iff its literal prefix is git-tracked OR protected.

    Same normalisation as judge_targets (the trailing-separator fix included).
    The protected clause is skipped when protect_paths is unreadable; the caller
    ANNOUNCES that (strict branch), it is never a silent exemption.
    """
    prefix = literal_prefix(raw_target)
    if not prefix.strip():
        return ("pass", None)
    candidate, resolved = normalize_path_checked(prefix)
    if not candidate:
        return ("pass", None)
    if prefix.endswith(("/", "\\")) and not candidate.endswith("/"):
        candidate += "/"
    # T-00000785: a candidate whose resolution failed is refused before either
    # clause, whatever the cause. On the STRICT branch (protect_paths
    # unreadable) nothing else caught it: git refuses the argv (git_tracked ->
    # False) and the protected clause is off — ("pass", None).
    if not resolved:
        return ("protected", "unresolvable-path")
    if git_tracked(candidate):
        return ("git", None)
    if _protected_reason is not None:
        reason, rule = _protected_reason(candidate)
        if reason:
            return ("protected", rule)
    return ("pass", None)


def _deny_git(command, reason, rule):
    """The refusal of one git arm: deny, then hook.deny{guard,rule,cmd_sha256,cmd_len} — never `path` (L-00000043)."""
    deny(reason)
    cmd_sha256, cmd_len = command_fingerprint(command)
    emit_event("hook.deny", guard="safe-bash", rule=rule, cmd_sha256=cmd_sha256, cmd_len=cmd_len)


def main():
    payload = read_payload()
    command = command_from_payload(payload)
    if not command:
        return

    # T-00000785 (R2): a command with no faithful byte form (faithful_bytes) is
    # refused first, whatever the verb. What a shell would run is not the text
    # judged below — an argv string ends at the first NUL, bash's command
    # substitution drops them (measured on the Claude homologue: "octet nul
    # ignoré"), and a lone surrogate has no UTF-8 form, so a host drops or
    # replaces it — and inside the verb or its envelope (`r\x00m`, `rm\x00`,
    # `sud\x00o`) it is no word this guard knows, so every judge passed it.
    # Rule `unrepresentable-command`, named for this BYTE class; the per-path
    # refusal in judge_redirect is `unresolvable-path`, named for the broader
    # RESOLUTION class (OSError too). Both per-operand refusals stay: each
    # function holds its contract without this order.
    if not faithful_bytes(command):
        deny(
            "BLOCKED by shell guard: this command has no faithful byte form for a shell "
            "— it carries a NUL (an argv string ends at the first one, and bash's command "
            "substitution drops them) or a lone surrogate (no UTF-8 form, so a host drops "
            "or replaces it) — hence what a shell would run is not the text this guard "
            "reads: no verb, operand or redirect target can be judged, nor whether the "
            "command bypasses the Edit/Write path and its checkpoint and mandate guards. "
            "Refused rather than guessed, whatever the verb; remove that character."
        )
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event(
            "hook.deny", guard="safe-bash", rule="unrepresentable-command",
            cmd_sha256=cmd_sha256, cmd_len=cmd_len,
        )
        return

    root = False
    unsafe = []
    whys = []
    absent_rg = None
    git_wipe = None
    git_output = False
    git_pager = False
    git_hidden = False
    git_branch = False
    git_alias = False
    git_hooks = 0

    # Stage 0.5 FIRST, before the coarse cut: a heredoc body is not QUOTED, it is
    # REDIRECTED, so no later stage can read it as data. Only bodies whose
    # delimiter carries a quoted piece are blanked — a naked one expands `$(…)`
    # and stays analysed. The FINGERPRINT below is still taken on the ORIGINAL
    # `command`, exactly as the Claude homologue hashes `$CMD`, so the same
    # payload keeps producing the same digest on every host.
    # T-01M5D6XV3J: an exception of stage 0.5 or 1 (quoted_spans, _opaque) is a REFUSAL, never a traceback.
    # Stage 1.5 (expand_braces) expands the brace lists and sequences; the expanded text is walked in a SECOND
    # pass, after a `(None, None)` that resets the frames, the first pass on the text as written still standing.
    # `reread` (T-01M5F4GJZD): True in that first pass only, where judge_git leaves the brace cut to the second.
    try:
        analysable = strip_heredoc_bodies(command)
        scrubbed_all = scrub_quoted(analysable)
        segments = coarse_segments(analysable, scrubbed_all)
        braced_raw, braced_scr, brace_unread, _inexact = expand_braces(analysable, scrubbed_all)
        if braced_scr != scrubbed_all:
            segments += [(None, None)] + coarse_segments(braced_raw, braced_scr)
    except Exception:  # noqa: BLE001 — fail-closed by contract: nothing below can be read
        deny(
            "BLOCKED by shell guard: the quoting of this command could not be read (the quote and heredoc "
            "scanner failed on it), so no verb, operand or redirect target can be judged — refused rather "
            "than guessed. Simplify the quoting, or ask the user to approve this exact command."
        )
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event("hook.deny", guard="safe-bash", rule="quote-scan-unread", cmd_sha256=cmd_sha256, cmd_len=cmd_len)
        return

    # The walk's frames live across the segments of the command (walk_units).
    unit_frames, frames, reread = [], [], braced_scr != scrubbed_all
    hook_open, hook_pending = {}, {}
    for raw_segment, scrubbed_segment in segments:
        if raw_segment is None:
            unit_frames, frames, reread = [], [], False
            hook_open, hook_pending = {}, {}
            continue
        if _ROOT_RM.search(scrubbed_segment.lower()):
            root = True
            continue

        # cmdpos/wrapped/probe are the Claude homologue's three walk flags, and
        # they die at every separator: `command -v rg && rg motif` stays guarded
        # on its second segment, so a probe opens no bypass window. `fed`
        # (T-00000762) is the fourth, and dies the same way: set by the `xargs`
        # or `parallel` envelope — in the command slot OR inside an envelope's
        # argument window (`nice -n 10 xargs rm …`, `sudo -u root xargs rm …`,
        # second pass) — and by `-exec|-execdir|-ok|-okdir`, it marks a verb
        # whose real operands come from a pipe: judge_targets refuses it
        # whatever its static operands (`ls | xargs rm -f build/x`). The four
        # are SAVED by an opening frame and RESTORED by its close (walk_units).
        # `cmdname` (T-01M5D6XV3J) is the command word once read: under `find`, a
        # word that may become -exec once bash reads it reopens the command;
        # `galias` an alias assignment before git, `gfed` an `xargs` at the head.
        cmdpos, wrapped, probe, fed, skip, cmdname, galias, gfed = True, False, False, False, False, "", False, False
        gpos, exempt, seg_gread = -1, -1, None
        units = walk_units(scrubbed_segment, unit_frames)
        for index, (kind, start, end, sub, glued) in enumerate(units):
            if kind == "sep":
                cmdpos, wrapped, probe, fed, skip, cmdname, galias, gfed = True, False, False, False, False, "", False, False
                continue
            if kind == "redir":
                skip = True
                continue
            if kind == "open":
                if index in hook_open:  # a quoted substitution of a verb of V left open at this segment's end
                    hook_pending[len(frames)] = hook_open.pop(index)
                # An open that starts a redirect TARGET (`> $(mktemp)`) is part
                # of that word, like a glued one: it takes no slot on close.
                frames.append((cmdpos, wrapped, probe, fed, sub, glued or skip, cmdname, galias, gfed))
                cmdpos, wrapped, probe, fed, skip = sub != "param", False, False, False, False
                cmdname, galias, gfed = "", False, False
                continue
            if kind == "close":
                skip = False
                if frames:
                    cmdpos, wrapped, probe, fed, sub, glued, cmdname, galias, gfed = frames.pop()
                    pending = hook_pending.pop(len(frames), None)
                    if pending is not None:  # its close: the words after it are the same git's
                        cwords, cstop, _cg, copen = hook_words(raw_segment, scrubbed_segment, units, index)
                        if copen >= 0:  # a second quoted substitution left open: read on after ITS close
                            hook_open[copen] = pending + cwords
                        git_hooks = max(git_hooks, judge_git(pending + cwords, cstop)[6])
                    if cmdpos and not glued and sub in ("sub", "bt", "param"):
                        # The substitution's OUTPUT is the command: unknown, so
                        # what follows is read as an envelope's window, fed.
                        cmdpos, wrapped, fed = False, (2 if wrapped == 2 else True), True
                else:
                    # A `)` nothing opened: a `case` pattern (`a) rm …`), or a
                    # syntax error bash refuses. A command follows, as after `;`.
                    cmdpos, wrapped, probe, fed, cmdname, galias, gfed = True, False, False, False, "", False, False
                continue
            if skip or glued:
                # A redirect target, or the rest of a word a substitution
                # started (`$(…)x`): neither takes the command slot.
                skip = False
                continue
            word, honest = executed_word(raw_segment[start:end])
            base = base_name(word)
            # ONE git site (T-00001102) : git in position of command, git PROVEN behind a chain of table
            # envelopes (gpos), or git anywhere in an AMBIGUOUS envelope window (wrapped == 2).
            git_site = base == "git" and not probe and (cmdpos or wrapped == 2 or index == gpos)
            if index == gpos:
                if wrapped == 1:
                    exempt = git_subcommand_unit(raw_segment, units, index)
                gpos = -1
            if git_site:
                gwords, gstop, globs = git_words(raw_segment, scrubbed_segment, units, index)
                if seg_gread is None:  # T-01M5F4GJZD: judged ONCE per segment
                    seg_gread = reread and _REREAD_SAFE.fullmatch(raw_segment) is not None  # closed set, quotes included
                    if seg_gread:  # and THIS segment changes, by an expansion exact to bash's
                        _r, seg_scr, seg_unread, seg_inexact = expand_braces(raw_segment, scrubbed_segment)
                        seg_gread = seg_scr != scrubbed_segment and not (seg_unread or seg_inexact)
                wipe, output, pager, hidden, branch_force, alias, hooks = judge_git(gwords, gstop, galias, gfed, globs, seg_gread)
                hwords, hstop, hglobs, hopen = hook_words(raw_segment, scrubbed_segment, units, index)
                if hopen >= 0:
                    hook_open[hopen] = hwords
                if (hwords, hstop) != (gwords, gstop):  # a substitution read inside double quotes: hooks read on
                    hooks = judge_git(hwords, hstop, galias, gfed, hglobs, seg_gread)[6]
                git_hooks = max(git_hooks, hooks)
                if wipe and git_wipe is None:
                    git_wipe = wipe
                git_output = git_output or output
                git_pager = git_pager or pager
                git_hidden = git_hidden or hidden
                git_branch = git_branch or branch_force
                git_alias = git_alias or alias
            if cmdpos:
                if not probe:
                    if base in DESTRUCTIVE:
                        found, why = judge_targets(raw_segment, start, honest, fed)
                        unsafe.extend(found)
                        if why:
                            whys.append(why)
                    elif base == "rg" and absent_rg is None and shutil.which(word) is None:
                        # The token is resolved AS WRITTEN (`rg`, `rg.exe`,
                        # `/usr/bin/rg`) rather than by a guessed name: what
                        # matters is whether the thing that would actually run
                        # exists.
                        absent_rg = word
                if base in PROBES:
                    probe, cmdpos = True, False
                    continue
                if base == "xargs" and wrapped != 3:
                    # T-01M5D6XV3J (T-01M53HV4): `xargs` at the head (alone, or behind table envelopes) opens an
                    # AMBIGUOUS window where git is judged, its operands from the pipe (gfed); behind an envelope
                    # outside the tables (wrapped 3) the S1 gap is unchanged.
                    wrapped, fed, gfed = 2, True, True
                    continue
                if base in ENVELOPES:
                    if not wrapped:
                        wrapped = 1
                    if base not in ENVELOPE_OPTIONS:
                        if wrapped == 1:
                            wrapped = 3
                    elif wrapped != 3:
                        state, where = scan_window(raw_segment, units, index, base)
                        if state == "amb":
                            wrapped = 2
                        elif state == "git" and wrapped == 1:
                            gpos = where
                    if base in ("xargs", "parallel"):
                        fed = True
                    continue
                if base in KEYWORDS:
                    continue
                if wrapped and word in ("-v", "-V"):
                    probe = True
                    continue
                if word.startswith("-"):
                    continue
                if _ASSIGNMENT.match(word):
                    galias = galias or alias_assignment(word + _EXPANSION_MARK if sub == "exp" else word)
                    continue
                if (sub == "exp" and scrubbed_segment[start] == "$") or _ANSI_UNREAD in word:
                    # An expansion TAKES the command slot (`$X rm …`, `sudo $X
                    # rm …`, an unreadable `$'…'`): the command is unknown — it may
                    # be an envelope, it may be xargs — so what follows is its window,
                    # fed, and AMBIGUOUS (T-01M5D6XV3J): `$X git branch -D wt/x` is judged.
                    cmdpos, wrapped, fed = False, 2, True
                    continue
                cmdpos, cmdname = False, base
            else:
                # T-01M5D6XV3J (T-01M55TRZ): under `find`, a primary bash may read as -exec — a `-…` word holding an
                # expansion or a backslash (`-ex${x}ec`), or an unreadable `$'…'` — reopens the command, fed.
                raw_word = raw_segment[start:end]
                if word in ("-exec", "-execdir", "-ok", "-okdir") or (cmdname == "find" and (
                        _ANSI_UNREAD in word or (word.startswith("-") and (sub == "exp" or "$" in raw_word
                                                                          or "\\" in raw_word)))):
                    cmdpos = True
                    fed = True
                    continue
                if wrapped and not probe and base in ("xargs", "parallel"):
                    fed = True
                if wrapped and not probe and base in DESTRUCTIVE and index != exempt:
                    found, why = judge_targets(raw_segment, start, honest, fed)
                    unsafe.extend(found)
                    if why:
                        whys.append(why)

    # The write-redirect pass (T-00000244), on the SAME heredoc-stripped text: a
    # `>`/`>>`/`&>` etc. whose literal target is git-tracked OR protected bypasses
    # the Edit/Write checkpoint and mandate guards. Descriptor duplication and
    # quoted/expanded targets PASS by construction, except a target whose last
    # segment is a guarded gate name (rule arming-marker-name, read below).
    redirect_unsafe = []
    redirect_literal_seen = 0
    redirect_quoted_seen = 0
    # HOW each refused target was read, said PER PATH in the deny reason
    # (T-00000698): `outside` is tested FIRST, so a relative prefix that leaves
    # the root (`../…`) is `outside` and never `relative`; `inside` needs an
    # ABSOLUTE prefix under the root; everything else is `relative`. Same
    # three words as the Claude homologue (safe-bash.sh, redirect stage).
    _ABS = re.compile(r"^(/|[A-Za-z]:)")
    # The name rule is gated on the SAME condition as the protected clause: the
    # sibling readable. Under the strict branch both are announced-off together.
    marker_names = arming_marker_names() if _protected_reason is not None else frozenset()
    marker_hits = []
    for raw_target, category in redirect_write_targets(analysable):
        hit = arming_marker_target(raw_target, marker_names)
        if hit is not None:
            marker_hits.append(hit)
        if category == "invisible-quoted":
            redirect_quoted_seen += 1
        if category != "literal":
            continue
        redirect_literal_seen += 1
        verdict, rule = judge_redirect(raw_target)
        if verdict in ("git", "protected"):
            prefix = literal_prefix(raw_target)
            cand = normalize_path(prefix)
            # Same trailing-separator fix as judge_redirect: the path SHOWN is
            # the path JUDGED (`tmp/` stays `tmp/`), correction of T-00000698.
            if prefix.endswith(("/", "\\")) and not cand.endswith("/"):
                cand += "/"
            how = (
                "outside" if _ABS.match(cand)
                else ("relative" if not _ABS.match(prefix.replace("\\", "/")) else "inside")
            )
            redirect_unsafe.append((rule or "git-tracked", cand, how))
    # ONCE PER TARGET: a marker already refused by its PATH above is not listed
    # a second time by its name — the name rule only adds what the path clauses
    # could not see (a cd, a quote, an expanded directory).
    named = {c.replace("\\", "/").rsplit("/", 1)[-1].lower() for _, c, _ in redirect_unsafe}
    if _protect_paths is not None:
        named |= {_protect_paths._nt_fold(n) for n in named}
    for as_written, folded, how in marker_hits:
        if folded in named:
            continue
        named.add(folded)
        redirect_unsafe.append(("arming-marker-name", as_written, how))
    if (redirect_literal_seen or redirect_quoted_seen) and _protected_reason is None:
        # STRICT branch, said out loud: the protected clause could not be read, so
        # it is announced-off rather than silently dropped. git-tracked writes are
        # still guarded above; only the protected-path coverage is missing here.
        print(
            "COVERAGE DEGRADED: safe-bash redirect — protect_paths is unreadable, so "
            "the protected-path clause of the write-redirect guard is NOT applied for "
            "this call, the arming-marker-name clause with it; git-tracked redirect "
            "writes remain guarded.",
            file=sys.stderr,
        )

    # Same order as the Claude homologue's verdict block (root, then the git
    # wipe, the --output write, the grep pager and a hidden subcommand, then rg,
    # then rm/mv — aligned by T-00000762), so the same payload denies under the same rule name on
    # every host. hook.deny{guard,rule,cmd_sha256,cmd_len} — NEVER `path`, which
    # for this guard would mean shipping the command line itself (L-00000043).
    if brace_unread:
        deny(
            "BLOCKED by shell guard: an unquoted brace expansion in this command cannot be read: it grows past the "
            "bound the guard expands (256 words per word, 1024 per command), or it holds a quoted piece "
            "(`{git,'reset'}`) or a substitution, a process substitution, an arithmetic or a backtick before its "
            "closing brace (`{git,reset,--hard,$(true)}`, `{git,reset,--$(echo hard)}`) — and the command names "
            "git, rm, find or xargs, or the brace stands in or before its command word (`{r{m,},{1..300}} -rf src`; "
            "an envelope — " + ", ".join(sorted(ENVELOPES)) + ", `env -S` and a timeout's duration included — its "
            "options, and a reserved word (!, {, if, then, elif, else, do, while, until) are not the command word: "
            "`sudo -u root {r{m,},{1..300}} -rf src` is refused too). What bash would run is unknown, so it is "
            "refused rather than guessed. Write the words out, or quote the braces. Within that bound a brace list "
            "or sequence outside quotes (`{a,b}`, `{1..3}`) is expanded as bash expands it before any guard reads "
            "the words."
        )
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event("hook.deny", guard="safe-bash", rule="brace-expansion-unread", cmd_sha256=cmd_sha256, cmd_len=cmd_len)
        return

    if root:
        deny("BLOCKED by shell guard: refusing catastrophic rm against root.")
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event(
            "hook.deny", guard="safe-bash", rule="rm-rf-root",
            cmd_sha256=cmd_sha256, cmd_len=cmd_len,
        )
        return

    if git_wipe is not None:
        # The truth said PER SUBCOMMAND (T-00000762): the old Claude wording
        # "unlike a reset it is not recoverable" was false — `reset --hard` loses
        # a never-staged edit exactly the same way — and a stash is not erased,
        # it is MOVED into a stack every session shares.
        truth = (
            "It moves that work into the stash stack SHARED by every session of this "
            "repository, where another session's `git stash pop`, `drop` or `clear` "
            "takes it — its owner never sees it again."
            if git_wipe == "stash"
            else "An edit that was never staged leaves NO git object and NOTHING in the "
            "reflog, so it cannot be recovered afterwards."
        )
        # The remedy is said PER SUBCOMMAND and every one is POSSIBLE (T-00000762,
        # decision 5): the old "give a precise path" was impossible for `reset
        # --hard` (it takes none) and for `git clean` (refused whatever its path).
        broad = (
            " `.`, `*`, `:/`, `:(top)`, an exclude-only pathspec, a list read from stdin (`--pathspec-from-file=-`, "
            "or the operands `xargs` feeds from a pipe: `xargs git checkout --`) "
            "and an UNQUOTED expansion (`$f`, which may split, glob or be empty) all count as the whole tree — quote an expansion (`\"$f\"`)."
        )
        remedy = {
            "reset --hard": "`git reset --hard` takes no pathspec: drop one file's edits "
            "with `git restore -- src/foo.ts`, move the branch with `git reset --keep "
            "<commit>` (it refuses to lose local edits), or commit first. Every "
            "abbreviation of --hard (`--h`) is refused too, and so is an option word holding an UNQUOTED "
            "expansion (`git reset $x`, `--hard$x`), which may expand to --hard.",
            "clean": "Run `git clean -n` first — a dry run, allowed, that deletes "
            "nothing and lists what would go — then delete what it lists by name, or "
            "ask the user to approve this exact command. The dry run is credited option by option "
            "(T-01M5D6XV3J): the last of `-n`, `--dry-run`, `--no-dry-run` wins, `-e` takes its value even "
            "at the end of a cluster (`-fde -n` excludes the pattern -n, no dry run), and a word that may "
            "expand into an option — an unquoted expansion, a glob, a backslash (`-e $x -n`, `-?n`, `-e\\ -n`) "
            "— withdraws the credit.",
            "stash": "Stash a PRECISE PATH instead (`git stash push -- src/foo.ts`), "
            "or commit first." + broad,
        }.get(
            git_wipe,
            "Give a PRECISE PATH instead (`git restore src/foo.ts`, `git checkout -- "
            "src/foo.ts`), or commit first." + broad,
        )
        _deny_git(command, (
            f"BLOCKED by shell guard: an unscoped `git {git_wipe}` wipes the UNCOMMITTED "
            "work of every agent running right now out of the working tree — including "
            f"the tracked state registers (TASKS.json, LEDGER.json, SPECS.json). {truth} "
            "Measured on a consumer project 2026-08-06: two board tasks created a minute "
            f"earlier vanished during a fan-out and their ids were reassigned. {remedy} "
            "Not read, bounded and not closed: a command carried in a quoted string (`bash -c \"…\"`, `env -S \"…\"`), `env -v …`, "
            "an envelope outside the table (`timeout 5 git …`) and a brace that is no list nor sequence (`HEAD@{1}`), where the words "
            "are cut; a brace list or sequence (`git reset {--hard,}`, `git {reset,--hard}`) is expanded and read (T-01M5D6XV3J), and "
            "refused on its own rule past its bound. Named, not closed: inside a quoted `\"$(…)\"`, the `)` of a `case` pattern ends "
            "the substitution early for this guard, which reads the rest as quoted data (a `git reset --hard` written after such a "
            "pattern passes unread); a `)` inside `${x:-)}` no longer does (the expansion is read as one block)."
        ), "git-wipe-unscoped")
        return

    if git_output:
        _deny_git(command, (
            "BLOCKED by shell guard: `git … --output` writes a FILE — a tracked one "
            "included (`git show --output=f HEAD` overwrote a tracked file, measured) — "
            "and bypasses the Edit/Write path with its checkpoint and mandate guards. "
            "Redirect instead (`git log … > /tmp/x`): the redirect guard JUDGES that "
            "target, and a path outside the repository passes. (Refused whatever the "
            "subcommand and wherever the target points; `-o` is never read as --output.)"
        ), "git-output-write")
        return

    if git_pager:
        _deny_git(command, (
            "BLOCKED by shell guard: `git grep -O` / `--open-files-in-pager` RUNS A "
            "COMMAND — the option's value, or the environment's pager when it has none — "
            "on the files it finds: an arbitrary execution no guard reads. Run `git grep` "
            "without it and open the files with the built-in read tool. (Every "
            "abbreviation of --open-files-in-pager, and every short cluster carrying O "
            "before a value letter, is refused.)"
        ), "git-grep-pager-exec")
        return

    if git_hidden:
        # FAIL-CLOSED arm of the three git guards (T-00000762, decision 3): an
        # expansion where git reads its subcommand hides what would run. A
        # VALUE that is an expansion (`git -C $d …`) hides nothing and passes.
        _deny_git(command, (
            "BLOCKED by shell guard: an UNQUOTED expansion (`$x`, `$(…)`, a backtick) "
            "stands where git reads its subcommand, so whether this is an unscoped wipe, "
            "a `--output` write or a `grep -O` cannot be read — refused rather than "
            "guessed. Quote an expansion that is a VALUE (`d=$(pwd); git -C \"$d\" status`) "
            "and write the subcommand itself literally."
        ), "git-subcommand-hidden")
        return

    if git_alias:
        # T-01M5D6XV3J (T-01M53HV4): an ALIAS defined for this git hides its subcommand the same way — `git bd`
        # would run `branch -D`. Same rule, its own message.
        _deny_git(command, (
            "BLOCKED by shell guard: a git ALIAS is defined for this command — `git -c alias.<x>=…`, `git "
            "--config-env=alias.<x>=…`, or a `GIT_CONFIG_KEY_<n>=alias.…` / `GIT_CONFIG_PARAMETERS` assignment "
            "before git (behind `env` too; a value that is an unquoted expansion counts) — so the subcommand git "
            "runs is hidden behind the alias: whether this is an unscoped wipe, a forced branch delete, a "
            "`--output` write or a `grep -O` cannot be read — refused rather than guessed. Write the git command "
            "itself, without the alias. Not read, named: an alias exported by an EARLIER command of the same call "
            "(`export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd …; git bd …`) or set in a git config file."
        ), "git-subcommand-hidden")
        return

    if git_branch:
        _deny_git(command, BRANCH_FORCE_REASON, "git-branch-force-delete")
        return

    # T-01M5C1AF6GB3ZRX5QF9SF6R80Y: after the six git arms (the alias arm included), as on the Claude homologue.
    hooks_reason = hooks_refusal(command, git_hooks)
    if hooks_reason:
        _deny_git(command, hooks_reason, "git-hooks-bypass")
        return

    if absent_rg is not None:
        deny(
            f"BLOCKED by shell guard: `{absent_rg}` does not resolve on this machine, and an "
            "absent ripgrep fails INDISCERNIBLY from an empty result — `rg PAT || echo NONE` "
            "takes the failure branch on the 127 of command-not-found and prints NONE, while "
            "`rg PAT 2>/dev/null` swallows the message and prints nothing. A sweep that never "
            "ran then reads as 'zero occurrences'. Use the built-in search tool, which fails "
            "loudly. (Only a MISSING tool is blocked; a working rg never is, and a presence "
            "probe such as `command -v rg` is exempt.)"
        )
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event(
            "hook.deny", guard="safe-bash", rule="rg-absent-silent-failure",
            cmd_sha256=cmd_sha256, cmd_len=cmd_len,
        )
        return

    if unsafe or whys:
        # One clause per motive that fired (T-00000762), so the agent reads WHY:
        # paths named up to three and the rest COUNTED, never dropped in silence.
        clauses = []
        # R4 (T-00000785): an operand refused because its resolution failed is
        # not "tracked or outside" — `tmp/x\x00` is inside the list — so it has
        # its own clause and the list names only the others. The split re-asks
        # the SAME resolution judge_targets used, so it follows the class (a
        # lone surrogate too), not one character. Unreachable through main()
        # today for a NUL or a surrogate (R2 refuses those commands first);
        # kept so this block never mislabels an unresolvable operand.
        unresolvable = [p for p in unsafe if not normalize_path_checked(p)[1]]
        listed = [p for p in unsafe if p not in unresolvable]
        if listed:
            named = ", ".join(listed[:3])
            if len(listed) > 3:
                named += f", +{len(listed) - 3} more"
            clauses.append(
                f"Refused operand by operand, as tracked or outside this host's "
                f"disposable directories: {named}."
            )
        if unresolvable:
            clauses.append(
                "An operand could not be resolved (a NUL, a lone surrogate, or a path "
                "the filesystem refused): the path a shell would receive is not the one "
                "judged, so it is refused unread."
            )
        if "dissolved" in whys:
            clauses.append(
                "An operand that starts with an expansion ($HOME, $(pwd), a backtick) is "
                "judged by its LITERAL prefix only, and it has none: refusing rather than "
                "guessing what it would delete."
            )
        if "empty" in whys or "fed" in whys:
            clauses.append(
                "No destructive-verb operand could be resolved, or its operands come from a "
                "pipe (xargs, parallel, find -exec/-ok — through an envelope, a process "
                "substitution or a redirect too) or from a command an expansion hides ($X "
                "rm …): a bare rm, or one fed by a pipe, is refused whatever its static "
                "operands."
            )
        if "shlex" in whys:
            clauses.append(
                "The quoting of a destructive verb could not be read (shlex refused it): "
                "refusing rather than guessing what it would delete."
            )
        deny(
            "BLOCKED by shell guard: destructive command bypasses agent checkpoints. "
            + " ".join(clauses)
            + " Write the path literally under one of THIS host's project-relative "
            "directories (tmp/, temp/, .tmp/, dist/, build/, coverage/, node_modules/, "
            ".next/); an absolute /tmp path is refused on this host — or ask the user to "
            "approve this exact command. Named, not closed: the `)` of a `case` pattern inside a quoted "
            "`\"$(…)\"` ends the substitution early for this guard, which reads the rest as quoted data."
        )
        # Same omission as the branch above, for the same reason: the `unsafe`
        # paths go to the HOST in the deny reason (where the agent must read them
        # to fix its command) but NOT into the event, because the Claude
        # homologue sends no `path` here either and a path list is one parse away
        # from the command.
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event(
            "hook.deny", guard="safe-bash", rule="rm-mv-bypass-checkpoint",
            cmd_sha256=cmd_sha256, cmd_len=cmd_len,
        )
        return

    if redirect_unsafe:
        paths = ", ".join(f"{p} ({r}, {h})" for r, p, h in redirect_unsafe[:3])
        if len(redirect_unsafe) > 3:
            # Three paths are NAMED and the rest is COUNTED, never dropped in
            # silence: a reason naming three of four reads as "three refused" to
            # the agent that must fix its command (T-00000698, exec-critic). The
            # Claude homologue lists every path; the cap of three is this file's.
            paths += f", +{len(redirect_unsafe) - 3} more"
        # The clause after the existing sentence is the one the Claude homologue
        # prints, identical to the byte but for the root token: bash expands
        # ${CLAUDE_PROJECT_DIR:-.} there; the Python hosts have no such variable,
        # so the git toplevel of THIS hook file (_common.ROOT) stands in for it.
        # T-00000785 (C2): a target refused because its resolution failed is
        # not known to be tracked or protected, so the lead names that third
        # case instead of mislabelling it; the motive "redirects a write" stays.
        lead = (
            "a tracked, protected or UNRESOLVABLE target"
            if any(r == "unresolvable-path" for r, _, _ in redirect_unsafe)
            else "a tracked or protected file"
        )
        deny(
            "BLOCKED by shell guard: this command redirects a write (>, >>, &>, ...) to "
            f"{lead} ({paths}). A shell redirect bypasses the "
            "Edit/Write path and its checkpoint and mandate guards — use Edit/Write, or "
            "redirect to a path outside the repository. (Descriptor duplication like "
            "`2>&1` and quoted or $-expanded targets are never blocked for an ORDINARY "
            "name; a target whose last segment names an arming marker is the one "
            "exception, below.) "
            "HOW EACH TARGET WAS JUDGED: a relative target is resolved against the "
            f"PROJECT ROOT ({ROOT}), never against a cd internal to the command — "
            "'cd /tmp/x && echo > AGENTS.md' is judged as '<root>/AGENTS.md'; write the "
            "absolute path or use the Write tool instead. A protected name (one of the "
            "arming/exit markers and pilot-only files protect-paths.sh names — "
            "NIGHT_HEADLESS.allow and MCP_ALLOWLIST.md among them since T-00000723, "
            "AUDIT_LOG alone is not among them (S-00002524) —, .claude/settings.local.json, "
            "mcp.json, .codex/config.toml, .gemini/settings.json, a .git "
            "segment, .env by name or as a substring, a "
            "credential-looking token) is refused by its own reason wherever it lives, "
            "including outside this repository; no exemption, and a directory segment "
            "counts too ('/tmp/secrets/x' is refused by the credential rule). An "
            "arming/exit marker is ALSO refused by its NAME alone (rule "
            "arming-marker-name): a redirect whose target's last segment is one of "
            "those names is refused whether the target is bare after a cd internal to "
            "the command, quoted, or under an expanded directory — this holds the NAME, "
            "not the directory, so neither a cd nor a throwaway clone arms a marker. "
            "WHAT THIS GUARD DOES NOT HOLD, said rather than implied: it prevents "
            "forgetting, not cheating — tee, cp, python -c and sed -i pass; and for any "
            "OTHER tracked or protected target a cd internal to the command or a quoted "
            "target still hides it (T-00000720). A credential-looking token is judged "
            "against the list of THIS host, and the lists are ALIGNED since "
            "T-00000721: id_rsa, credential(s), secret, private-key/private_key, .env "
            "as a SUBSTRING (so .envrc) and the .pem/.key/.p12/.pfx/.crt extensions, on "
            "every host. Every name is judged case-folded AND NTFS-folded "
            "(T-00000722): a trailing dot or space and a ':' stream are stripped per "
            "segment, so 'MARKER.', 'MARKER ' and 'MARKER::$DATA' are the marker. "
            "Everything else is the simple inside case."
        )
        cmd_sha256, cmd_len = command_fingerprint(command)
        emit_event(
            "hook.deny", guard="safe-bash", rule="redirect-write-guarded",
            cmd_sha256=cmd_sha256, cmd_len=cmd_len,
        )
        return


if __name__ == "__main__":
    # T-01M5D6XV3J (security A2): ANY exception of the guard is a REFUSAL, never a traceback (a hook that dies with
    # rc 1 lets the command run on the hosts). Reachable before any decision only: every deny() above is followed by
    # command_fingerprint() (total) and emit_event() (never raises), then a return.
    try:
        main()
    except Exception:  # noqa: BLE001 — fail-closed by contract
        deny("BLOCKED by shell guard: the guard failed while reading this command (an internal error), so "
             "nothing in it was judged — refused rather than guessed. Retry, or ask the user to approve this "
             "exact command.")
        emit_event("hook.deny", guard="safe-bash", rule="guard-internal-fault")
