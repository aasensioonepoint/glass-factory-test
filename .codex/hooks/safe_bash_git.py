# The git-hooks-bypass verdict (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) lives in safe_bash_hooks.py, its MIT notice with it.
"""The git ARGUMENT judge of safe_bash.py, in a sibling module (T-00001090, T-00001102).

A LEAF: stdlib only, it never imports safe_bash or _common, so safe_bash.py loads it the way
it loads _common (the script directory is on sys.path under pyrun.sh, pyrun.ps1 and a bare
`python3 safe_bash.py`). The Codex and Gemini copies are held identical by
test_guard_decision_parity (test_the_two_python_bridges_carry_the_same_guard), and the
benches that copy the bridges into a fixture copy this file too (COMMON_FILES, COPIED).
Extracted so that safe_bash.py, listed in the 1600-line ratchet, never grows.
"""
import re

# The git-hooks-bypass rule, in its own LEAF sibling (stdlib only, imports nothing of this kit). HOOKS_REASON and
# hooks_refusal are re-exported: safe_bash.py imports hooks_refusal from here, the benches read HOOKS_REASON here.
from safe_bash_hooks import (  # noqa: F401
    _CLUSTER, _HOOK_VERBS, _VERIFY_VERBS, HOOKS_REASON, _cluster, _config_bypass, _hook_setting, hooks_refusal,
)

# An UNQUOTED expansion inside a word handed to `git` is marked with this
# character (git_words): quoted text is `@` in the scrubbed copy, so a `$` left
# there is outside quotes — one bash expands, unless a backslash escapes it
# (`\$b` is marked too: fail-closed).
_EXPANSION_MARK = "\x1d"
# T-01M5D6XV3J: an UNREADABLE `$'…'` (ansi_decode gives None, or the decoder failed) reads as
# `$` + _EXPANSION_MARK + this mark (read_ansi): an expansion everywhere, and under `branch` a
# possible forced delete of a `wt/` name — unreadable in an option's place is a refusal.
_ANSI_UNREAD = "\x1e"


# --- The unscoped git wipe, the --output write, the grep pager (T-00000762) --
# PORT, rule for rule, of `decide_git` in .claude/hooks/safe-bash.sh — read its
# comment block before touching this. Same subcommands, same global options
# whose value is SKIPPED (`-C`, `-c`, `--git-dir`, `--work-tree`, `--namespace`,
# `--config-env`), same stash modes, same pathspec rule, same `--output` and
# pager tests, same order. The words are the walk's own WORD units up to the
# next separator, subshell or substitution (git_words), a redirect skipped with
# its target — the SAME bound as the awk's. An UNQUOTED expansion stays in its
# word, marked: as the value of `-C`/`-c`/… it is skipped like any value, as a
# pathspec it is read as BROAD (it may split, glob, or be empty — `git stash
# push -- $f` is refused on both hosts, `-- "$f"` passes on both), and where
# git reads its SUBCOMMAND it hides it — `git $sub .`, `git $(…) …` — which is
# refused fail-closed (rule git-subcommand-hidden, T-00000762 decision 3). The
# difference that remains is how a word is READ: here through its quotes
# (executed_word), which is DIVERGENCE 7 — since the second pass it covers a
# quoted OPTION or SUBCOMMAND only (`git reset "--hard"`, `git log
# "--output=x"`, `git grep "-O" x`, `git "stash"`: refused here, `@@` on
# Claude), a quoted PATHSPEC being read through its quotes on Claude too. A
# tokenisation shlex refuses is NOT fail-closed on this guard: the walk's
# units suffice, and `git commit -m "l'index` must not fall.
_GIT_GLOBAL_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})
_STASH_NEVER = frozenset("list show pop apply drop clear branch create store".split())
_GREP_VALUE = frozenset({"-e", "-f", "-A", "-B", "-C", "-m"})
_PAGER_OPTION = "open-files-in-pager"
_PAGER_VALUE_LETTERS = "efABCm"

# The git-branch-force-delete refusal, MOVED here verbatim from safe_bash.py (ratchet, T-01M5C1AF6GB3ZRX5QF9SF6R80Y).
BRANCH_FORCE_REASON = (
    "BLOCKED by shell guard: `git branch -D` (or `-d --force`) on a `wt/` branch deletes the commits only that branch carries: the "
    "unmerged work of a worktree dev. Run `git branch -d wt/<T>` after the merge instead — git refuses to delete an unmerged branch, "
    "and a refused `-d` is reported, never forced. Bounds: `wt/` only, letters folded (`WT/x` names the same branch on an APFS or "
    "NTFS disk); a name held in an expansion or a substitution (`$b`, `\"$b\"`, `$(…)`) and a name holding `@{…}`, quoted or not (`@{-1}`), count as `wt/`, and so does any word after `branch` that is not an option and holds a `$` or a backtick, even one bash does not expand — quoted (`'$b'`), escaped (`\\$b`) or in a trailing comment (`# $HOME`), a fail-closed false positive — while a `$` inside an option word is not read as a name (`--sort=$x`); `-D -r wt/…` is refused too (fail-closed false positive); so is a `-D` read in a trailing comment (`git branch wt/x # -D`). "
    "Braces: an unquoted brace list or sequence (`{wt/x,y}`, `{-D,}`, `-{D..D}`, `{branch,-D}`) is expanded as bash expands it and "
    "the expanded words are read in a second pass (T-01M5D6XV3J; past its bound — 256 words per word, 1024 per command — it is "
    "refused on its own rule), the words as written being read too, so what follows holds for them: "
    "the guard stops reading a `git` command at its first `{` or `}` outside quotes and outside a `${…}`, a brace that is no list nor sequence (`{x}`, `@{…}`) (read as an expansion; a `${…}` ends at its first `}`: `${x:-{y}}` cuts there, so `git branch ${x:-{y}} -D wt/…` passes unread) — a backslash does not protect it, and one in a comment or a redirect target counts (the words end with the command, e.g. at `;`, `&`, `|`, an unescaped newline or a closing `)`: a brace after that is not read; a backslash-newline is NOT joined, so `git branch -D \\<LF>wt/…` and `git branch -D feat \\<LF>{wt/x,y}` pass unread on the three hosts — gap carried by T-00001198). If a forced delete (`-D`, or `-d`/`--delete` with `-f`/`--force`) was read before that point, the command is refused as if the name were `wt/` (a fail-closed false positive for a non-wt name: `feat }`, `# {x}`); if not, it passes unread (named gap, T-00001196: `git branch wt/… {x} -D`; `git branch {-D,} wt/…` is read in the second pass). "
    "On every host (Claude too since T-01M5GFV9CE), a brace list or sequence cuts the words as written too, and that cut counts as `wt/` once the forced delete was read, unless the guard's expansion changes the same command segment (up to a `;`, a newline, or a `&`/`|` that is not part of a redirection: `2>&1`, `&>`, `>|` do not end it) and reproduces bash's exactly — a letter sequence crossing the characters between `Z` and `a` (`{V..a..6}wt/x`) or a numeric one with a `+` sign is not reproduced exactly — and every character of that segment, inside quotes too, is a letter, a digit, a blank, a quote or one of `{ } , . _ - / @ : = + % # < > &` — a character outside a closed set (a backslash, a backslash-newline even inside quotes, a glob, `$`, `(`, `)`, a backtick, `~`, `!`, a non-ASCII letter) may stop or split the expanded words where bash goes on, and a carriage return is excluded too, fail-closed, as a character not read as bash reads it: refused rightly on `git branch -D {a,b} <(echo) wt/x` and `{a,b} \"w\\<LF>t/x\"`, a fail-closed false positive on `(git branch -D {a,b})`, `{a,b} ~x`, `{a,b} \"w<CR>t/x\"`. "
    "On the Claude host only, a word after `branch` glued to a quoted span (`feat-\"old\"`, `--sort=\"x\"`) counts as `wt/` too, and so does, once the command holds a literal `@@` anywhere, every quoted word after `branch` and a `@@` among those words (`git branch -D 'feat' # @@`, `git branch -D feat # @@`) (fail-closed false positive). The delete option is not read as bash reads it — gap carried by T-00001202: on the Claude host only, a quoted or glued option (`git branch '-D' wt/…`, even with a literal `@@` in the command, `-\"D\"`, `-d '-f'`) or one behind a backslash (`\\-D`), and on the three hosts an option glued after an expansion that may be empty (`$b-D`, `${b}-D`; `\"$b\"-D` on the Codex and Gemini hosts only), and a `--` taken by git as the value of `--sort`/`--format` (`git branch --sort -- -D wt/…`) pass unread; an option in ANSI-C quotes is decoded and read on the Codex and Gemini hosts (`$'-D'`, `$'\\055D'`, T-01M5D6XV3J), and an unreadable one (`$'\\c'`, a UTF-16 half) counts as a forced delete of a `wt/` name. Not covered, named: `branch -M|-C <x> wt/…`, `branch -f wt/…`, "
    "`update-ref -d`, `push . :wt/x`, an option written after a substitution (`git branch $(…) -D`), `checkout -B`/`switch -C wt/…`, "
    "`env -S '…'`/`env -v`, an envelope outside the table (`timeout 5 git …`, `nice -n 5 git …`), a command carried in a quoted string (`bash -c \"…\"`) and `xargs` behind an envelope outside the table (`timeout 5 xargs git branch -D`) — bounded, not closed. "
    "`xargs` at the head of the command (alone, or behind table envelopes) IS read: a branch name it feeds from the pipe counts as `wt/` (T-01M5D6XV3J). "
    "Named, not closed: the `)` of a `case` pattern inside a quoted `\"$(…)\"` ends the substitution early for this guard, the "
    "rest is read as quoted data; a `)` inside `${x:-)}` no longer does."
)


def _long_option(word, option, shortest):
    """`(matched, value)` — `word` is `--<name>[=<value>]` and `<name>` is a
    prefix of `option` at least `shortest` letters long. git accepts ANY
    unambiguous abbreviation of a long option (measured, git 2.55: `reset --h`
    wipes like `--hard`, `restore --w .` like `--worktree`, `stash push --m
    wip` takes `wip` as its message; `--pathspec-f` is ambiguous and refused,
    so `--pathspec-fr` is the shortest). `value` is None without `=`."""
    if not word.startswith("--"):
        return False, None
    name, eq, value = word[2:].partition("=")
    if len(name) < shortest or not option.startswith(name):
        return False, None
    return True, (value if eq else None)


def _broad_pathspec(word):
    """A pathspec that reaches the WHOLE tree: once its magic is read, a path
    made only of `.`, `/` and `*` — `.`, `./`, `./.`, `*`, and nothing at all
    after `:/` or `:(top)` — or an EXCLUDE magic (`:!x`, `:^x`,
    `:(exclude)x`, which means everything else), or an UNQUOTED expansion
    (marked by git_words), which may split, glob or be empty."""
    if _EXPANSION_MARK in word:
        return True
    path = word.replace("\\", "")
    if path.startswith(":("):
        close = path.find(")")
        if close < 0:
            return False
        if "exclude" in [magic.strip() for magic in path[2:close].split(",")]:
            return True
        path = path[close + 1:]
    elif path.startswith(":"):
        end = 1
        while end < len(path) and path[end] in "/!^":
            end += 1
        if "!" in path[1:end] or "^" in path[1:end]:
            return True
        if end < len(path) and path[end] == ":":
            end += 1
        path = path[end:]
    return all(char in "./*" for char in path)


def _git_output_word(word):
    """`--output` or `--output=…`, EXACTLY: `--output-indicator-*` is another
    option, and `-o` is never read (its meaning changes per subcommand)."""
    return word == "--output" or word.startswith("--output=")


def _git_pager_word(word):
    """A `git grep` option that opens a pager: a long word whose name (two
    letters at least) begins `open-files-in-pager` (`--op`, not `--or`), or a
    short cluster where `O` comes before any value letter `e f A B C m`. Case
    SENSITIVE (`-o` is --only-matching)."""
    if word.startswith("--"):
        name = word[2:].split("=", 1)[0]
        return len(name) >= 2 and _PAGER_OPTION.startswith(name)
    if not word.startswith("-"):
        return False
    for char in word[1:]:
        if char == "O":
            return True
        if char in _PAGER_VALUE_LETTERS:
            return False
    return False


def _clean_odd(word, glob):
    """A `git clean` word that may become an option once bash reads it: opening on an unquoted expansion or an
    UNQUOTED glob character (`glob`: the walk saw one outside quotes), or a `-…` word holding an unquoted
    expansion, a backslash or such a glob (`$x`, `-?n`, `-e\\`). A quoted `'*.log'` is a pattern, not odd."""
    if (glob and word[:1] in ("*", "?", "[")) or (word.startswith("$") and _EXPANSION_MARK in word):
        return True
    return word.startswith("-") and (glob or any(c in word for c in (_EXPANSION_MARK, "\\")))


def _alias_value(value, anywhere=False):
    """A git config value that DEFINES an alias (`alias.<x>=…`; anywhere in GIT_CONFIG_PARAMETERS), or that
    cannot be read (an unquoted expansion): the subcommand git runs is then hidden (T-01M5D6XV3J, T-01M53HV4)."""
    if _EXPANSION_MARK in value:
        return True
    value = value.lower()
    return "alias." in value if anywhere else value.startswith("alias.")


def alias_assignment(word):
    """True for an assignment before git (`GIT_CONFIG_KEY_<n>=alias.…`, `GIT_CONFIG_PARAMETERS=…alias.…`, behind
    `env` too) that defines an alias for the git of this command; `word` is read, an unquoted expansion marked."""
    name, _eq, value = word.partition("=")
    if name != "GIT_CONFIG_PARAMETERS" and not re.match(r"GIT_CONFIG_KEY_[0-9]+$", name):
        return False
    return _alias_value(value, name == "GIT_CONFIG_PARAMETERS")


def judge_git(words, stop="", galias=False, piped=False, globs=frozenset(), reread=False):
    """`(wipe, output, pager, hidden, branch_force, alias, hooks)` for the words after a `git`
    in position of command: `wipe` is the subcommand to name in the refusal
    (`restore`, `checkout`, `clean`, `reset --hard`, `stash`) or None; `hidden`
    is True when an UNQUOTED expansion stands where git reads its subcommand
    (or the stash mode), or a substitution ends the words before one was read.
    `branch_force` (T-00001090) is True for `git branch` carrying a DELETE
    (`-d`, `-D`, a cluster with d or D, `--delete` and its abbreviations) AND a
    FORCE (`-D`, a cluster with f or D, `--forc[e]`) among the words git_words
    hands over (an option after the operand counts, and so does one in a
    comment: `git branch wt/x # -D`; after `--` operands only), with one
    operand that opens `wt/` once folded and unbackslashed, or holds `@{`
    (forbidden in a ref name, resolved by git: `@{-1}` is the previous branch),
    or holds a `$` or a backtick, expanded by bash or not (`$b`, `'$b'`,
    `\\$b`, a comment word `$HOME`: fail-closed), or the expansion mark — or
    with the words cut by a substitution (`git branch -D $(…)`) or by a
    `{`/`}` (`stop == "brace"`). An option is a word that starts with `-` once
    read through its quotes: `$'-D'` (read `$-D`), `$b-D`, `"$b"-D` and a `--`
    git takes as the value of `--sort`/`--format` are NOT read as one (a gap
    named in the refusal, T-00001202). git_words stops at the first `{`/`}`
    outside quotes and outside a `${…}` (an expansion word, which ends at its
    first `}`: `${x:-{y}}` cuts at the second), behind a backslash or in a
    redirect target too, so the cut counts as `wt/` when the forced delete was
    read before it (`feat }`, `# {x}`: fail-closed) and
    what follows is never read when it was not (`git branch wt/… {x} -D`,
    `git branch ${x:-{y}} -D wt/…`, a gap named in the refusal, T-00001196).
    A brace LIST or SEQUENCE is no longer such a cut: stage 1.5 expands it and
    the expanded words reach this judge in a second pass (`{-D,}`, T-01M5D6XV3J).
    `reread` (T-01M5F4GJZD) is True on the FIRST pass of a command stage 1.5
    expanded, in a RAW segment made of only characters of the closed set
    `_REREAD_SAFE` (safe_bash.py), inside quotes too, that this expansion
    changes, exactly as bash 5 does (no `inexact` sequence, nothing unread):
    there the `brace` cut does not count as `wt/` (`{feat-a,feat-b}` passes,
    as on Claude), the
    second pass reading the expanded words, where a brace that is no list nor
    sequence still cuts and counts (`{feat-a,feat-b} }`, `{a,b} @{-1}`). Any
    other character (a backslash, a glob, `$`, `(`, `)`, a backtick, `~`, `!`,
    a CR, a non-ASCII letter) may stop or split the second pass where bash goes
    on, or is not read as bash reads it, so the cut counts there: `{a,b}
    <(echo) wt/x`, `{a,b} "w\\<LF>t/x"`, `{a,b} \\; wt/x`, `{a,b} w?/x` are
    refused, and so are the non-wt `{a,b} x[1]`, `(git branch -D {a,b})`,
    `{fix-1,fix-2} > /tmp/x\\ y` (fail-closed).
    `-r` is NOT honoured (`--sort -r` makes it a value): `-D -r wt/x` is
    refused, a named false positive.

    `stop` is git_words' own: "subst", "brace" or "". The wipe, output and
    pager verdicts never read "brace": a word cut at a brace that is no list nor
    sequence is not read past it there (`git reset HEAD@{1}`); a list or a
    sequence (`git reset {--hard,}`) is read in the second pass, expanded.

    Stash modes, as in the awk: 1 `push`, 2 implicit (an option or nothing
    first), 3 never refused (`list show pop apply drop clear branch create
    store`), 4 `save` (always refused, it takes no pathspec), 5 an unknown word
    (git refuses it itself: nothing runs). A pathspec is any non-option word
    after `push` or after `--`, or `--pathspec-from-file[=]`; the value of
    `-m`/`--message` (and its abbreviations) is SKIPPED; a BROAD pathspec
    (_broad_pathspec) refuses, and so does `--pathspec-from-file=-` (and `-`
    as its next word) on restore, checkout and stash — the list comes from a
    pipe. `reset` is refused on `--hard` and every abbreviation (`--h`);
    `--soft`, `--mixed`, `--keep`, `--merge` and `reset <commit> -- <path>`
    never are. `restore --worktree` counts under every abbreviation (`--w`).
    `clean` is refused unless it is a DRY RUN (`-n`, `--dry-run` and its
    abbreviations, a short cluster carrying `n` before an `e`), T-00000762
    decision 5: `git clean -n` deletes nothing and is the remedy the refusal
    names — credited option by option since T-01M5D6XV3J (see the clean branch).

    T-01M5D6XV3J. `alias` is True when an ALIAS is defined for this git — `-c alias.<x>=…`, `--config-env=
    alias.<x>=…` (glued forms too), or `galias`, an assignment before git held by the walk (alias_assignment) —
    or when such a value is an unquoted expansion: the subcommand is hidden, no wipe or branch verdict is
    guessed. `piped` is `xargs` at the head of the command: the operands come from a pipe, so a restore or
    checkout pathspec and a stash pathspec are BROAD, and a branch name counts as `wt/`. `globs` holds the
    indices of the words carrying a glob character OUTSIDE quotes (git_words), read by the clean credit.

    `hooks` (T-01M5C1AF6GB3ZRX5QF9SF6R80Y, read by hooks_refusal): 2 when the
    words skip the hooks — `--no-verify` from `--no-v` on _VERIFY_VERBS, `-n` in
    a commit/am cluster (_cluster, which also skips the value of a final value
    letter), an UNQUOTED expansion before `--` on _VERIFY_VERBS — or a substitution
    that ENDS the words there (`stop == "subst"`: an option after it is unread) —, a `-c` or
    `--config-env` value (_hook_setting: alias. always, hookspath/include on
    _HOOK_VERBS), a `git config` _config_bypass refuses; 1 when the subcommand
    is in _HOOK_VERBS without any of these; 0 otherwise.
    """
    alias_set = hooks_set = bypass = False
    config_words = []
    scmd, gotsub = "", False
    b_delete = b_force = b_wt = False
    staged = worktree = wipe = hard = spec = broad = dashdash = dry = hidden = nocred = False
    output = pager = False
    halias = galias
    smode = 0
    index, count = 0, len(words)
    while index < count:
        word = words[index]
        index += 1
        if not gotsub:
            if word in _GIT_GLOBAL_VALUE:
                if word in ("-c", "--config-env") and index < count:
                    alias, hooks = _hook_setting(words[index])
                    alias_set, hooks_set = alias_set or alias, hooks_set or hooks
                    if _alias_value(words[index]):
                        halias = True
                index += 1
                continue
            if word.startswith("--config-env="):
                alias, hooks = _hook_setting(word[len("--config-env="):])
                alias_set, hooks_set = alias_set or alias, hooks_set or hooks
            if word.startswith("-"):
                output = output or _git_output_word(word)
                if (word.startswith("-c") and len(word) > 2 and _alias_value(word[2:])) or (
                        word.startswith("--config-env=") and _alias_value(word[13:])):
                    halias = True
                continue
            if _EXPANSION_MARK in word:
                hidden = True
                break
            scmd, gotsub = word.lower(), True
            continue
        # T-01M5D6XV3J (T-01M55TRZ): `git stash #c` — a `#` opening a word opens a comment, which ends the
        # words and the pathspecs: bash runs a BARE stash. Read under stash only (under branch a comment
        # stays read, the named false positives of guard 6); a QUOTED `'#x'` is read so too (false positive).
        if scmd == "stash" and word.startswith("#"):
            break
        if scmd == "stash" and smode == 0:
            if not word.startswith("-"):
                if _EXPANSION_MARK in word:
                    hidden = True
                    break
                if word == "push":
                    smode = 1
                elif word == "save":
                    smode = 4
                elif word in _STASH_NEVER:
                    smode = 3
                else:
                    smode = 5
                continue
            smode = 2
        if word == "--" and not dashdash:
            dashdash = True
            continue
        if not dashdash:
            from_file, value = _long_option(word, "pathspec-from-file", 11)
            if from_file and scmd in ("restore", "checkout", "stash"):
                if value is None:
                    value = words[index] if index < count else ""
                    index += 1
                spec = True
                if value == "-":
                    wipe = broad = True
                continue
            if scmd == "grep" and word in _GREP_VALUE:
                index += 1
                continue
            separated = (True, None)
            if scmd == "stash" and (word == "-m" or _long_option(word, "message", 1) == separated):
                index += 1
                continue
            if _git_output_word(word):
                output = True
            if scmd == "grep" and _git_pager_word(word):
                pager = True
        if scmd == "config":
            config_words.append(word)
            continue
        if scmd in _VERIFY_VERBS:
            if dashdash:
                continue
            if _EXPANSION_MARK in word or _long_option(word, "no-verify", 4)[0]:
                bypass = True
            elif scmd in _CLUSTER and word[:1] == "-" and word[1:2] not in ("", "-"):
                no_verify, takes_next = _cluster(word, scmd)
                bypass = bypass or no_verify
                index += takes_next
            continue
        if scmd == "branch":
            if _ANSI_UNREAD in word:            # an unreadable `$'…'` may be `-D`: fail-closed
                b_delete = b_force = b_wt = True
                continue
            if not dashdash and word.startswith("-"):
                if word.startswith("--"):
                    b_delete = b_delete or _long_option(word, "delete", 1)[0]
                    b_force = b_force or _long_option(word, "force", 4)[0]
                else:
                    for char in word[1:]:
                        b_delete = b_delete or char in "dD"
                        b_force = b_force or char in "fD"
                continue
            # `@{` is forbidden in a ref name and git resolves it (`@{-1}`: the previous branch).
            name = word.lower().replace("\\", "")
            if name.startswith("wt/") or "@{" in name or "$" in word or "`" in word or _EXPANSION_MARK in word:
                b_wt = True
            continue
        if scmd in ("restore", "checkout"):
            if word in ("--staged", "-S"):
                staged = True
            elif word == "-W" or (not dashdash and _long_option(word, "worktree", 1)[0]):
                worktree = True
            elif word == "--all":
                wipe = True
            elif word.startswith("-"):
                pass
            elif _broad_pathspec(word):
                wipe = True
            continue
        if scmd == "reset":
            # T-01M5D6XV3J (T-01M53HV4, T-01M55TRZ): an option word holding an UNQUOTED expansion (`$x`,
            # `--hard$x`) may be --hard once expanded; a word opening on neither `$` nor `-` (`HEAD~$n`) is a commit.
            if not dashdash and (_long_option(word, "hard", 1)[0]
                                 or (_EXPANSION_MARK in word and word[:1] in "$-")):
                hard = True
            continue
        if scmd == "stash":
            if dashdash or (smode == 1 and not word.startswith("-")):
                spec = True
                if _broad_pathspec(word):
                    broad = True
            continue
        # T-01M5D6XV3J (T-01M56ZE6): the dry-run credit is read OPTION BY OPTION — the last of -n / --dry-run /
        # --no-dry-run wins; -e / --exclude takes its value, at the end of a cluster too (`-fde -n`: -n is the
        # pattern); a word that may expand into an option (_clean_odd) withdraws ALL credit, -e's value included.
        if scmd == "clean" and not dashdash:
            if word == "-e" or _long_option(word, "exclude", 1) == (True, None):
                if index < count:
                    nocred = nocred or _clean_odd(words[index], index in globs)
                    index += 1
                continue
            nocred = nocred or _clean_odd(word, index - 1 in globs)
            if word == "-n" or _long_option(word, "dry-run", 1)[0]:
                dry = True
            elif _long_option(word, "no-dry-run", 4)[0]:
                dry = False
            elif word.startswith("-") and not word.startswith("--"):
                for pos in range(1, len(word)):
                    if word[pos] == "e":
                        if pos == len(word) - 1 and index < count:
                            nocred = nocred or _clean_odd(words[index], index in globs)
                            index += 1
                        break
                    if word[pos] == "n":
                        dry = True
    hidden = hidden or (not gotsub and stop == "subst")
    hard = hard or (scmd == "reset" and stop == "subst" and not dashdash)
    b_wt = b_wt or (scmd == "branch" and (stop == "subst" or (stop == "brace" and not reread)))
    # A `$(…)` or a backtick ended the words of a verb of V before `--`: an option after it is never read
    # (`git push -u origin $(git branch --show-current) --no-verify`), so the cut counts as a bypass.
    bypass = bypass or (scmd in _VERIFY_VERBS and stop == "subst" and not dashdash)
    hooks = 1 if scmd in _HOOK_VERBS else 0
    if alias_set or (hooks and (hooks_set or bypass)) or (scmd == "config" and _config_bypass(config_words, _EXPANSION_MARK)):
        hooks = 2
    if halias and not hidden:
        return None, output, pager, False, False, True, hooks
    if piped:
        wipe = wipe or scmd in ("restore", "checkout")
        broad = broad or scmd == "stash"
        b_wt = b_wt or scmd == "branch"
    verdict = None
    if hidden:
        pass  # what would run is unknown: no wipe verdict is guessed
    elif scmd == "clean":
        verdict = None if (dry and not nocred) else "clean"
    elif scmd == "reset":
        verdict = "reset --hard" if hard else None
    elif scmd == "stash":
        verdict = "stash" if smode == 4 or (smode <= 2 and (not spec or broad)) else None
    elif scmd in ("restore", "checkout") and wipe:
        verdict = None if (scmd == "restore" and staged and not worktree) else scmd
    return verdict, output, pager, hidden, (scmd == "branch" and b_delete and b_force and b_wt), False, hooks


# --- Stages 0.5 and 1 of safe_bash.py (T-01M5D6XV3J, step 1) ------------------
# Moved here BYTE FOR BYTE from safe_bash.py, which re-imports quoted_spans and
# strip_heredoc_bodies by name on its single `from safe_bash_git import` line
# (iac_guard.py and core-scripts/measure_shell_write_fp.py still read them
# through safe_bash). safe_bash.py sits at its length ceiling: the lot grows here.
def quoted_spans(text):
    r"""`[(start, end)]` of every quoted segment, BACKSLASH-AWARE.

    A quote preceded by an ODD number of backslashes is an ESCAPED quote: bash
    hands it to the command as a literal character and it opens NOTHING.
    Reading it as an opening quote is a class-1 bypass, and it was a LIVE one
    here — reproduced by this task's security review, which is why this scanner
    replaced a `'[^']*'|"[^"]*"` regex. In `echo \" ; rm -rf src/x \"` the two
    escaped quotes made the whole interval between them — the separator AND the
    destructive command — look like one quoted string, so stage 2 cut nothing and
    stage 3 saw a single opaque token: bash really ran the rm, and this guard
    said nothing. It was also a REGRESSION, which is the part worth remembering:
    the naive `re.split(r"[;&|\n]+")` that this stage replaced REFUSED that same
    payload, precisely because it never tried to understand quoting at all. A
    stage that understands quoting half-way is worse than one that does not.

    The scan follows bash's rules rather than approximating them:
      - outside quotes a backslash escapes the NEXT character, so `\"`, `\'` and
        `\\` are literal — and an EVEN run of backslashes therefore leaves a
        following quote free to open a real segment (`echo \\" ; rm x \\"` is a
        genuine quoted string in bash, and must keep being read as data);
      - a single-quoted segment ends at the next `'`, with NO escapes inside:
        `'a\'` really is the two characters `a\` in bash;
      - a double-quoted segment ends at the next UNESCAPED `"`.

    An unpaired quote closes nothing and leaves the remainder analysable, which
    is what keeps `echo l'index && rm -rf src/x` refused.

    THE COMMENT BOUNDARY (T-00000225), and the LIVE bypass it closes. An unpaired
    quote living in a `#` COMMENT used to pair with a real quote further on and
    neutralise the whole interval — including a line of REAL CODE, on another
    physical line, that bash genuinely runs. Measured against this very hook
    before the fix: `# don't run this` ⏎ `rm -rf src/x && echo 'ok'` came back
    ALLOW, while the same two lines without the comment came back DENY (the
    negative control, which is what makes the measurement mean something). The
    residue was therefore NOT confined to data: it reached code.

    THE CLAUSE IS REUSED, NOT REWRITTEN (D1) — it is the one stage 0.5 already
    carries (`_heredoc_scan`, `if ch == "#" and head`), same separator constant
    via `_STAGE1_SEP`, same `head` tracking, same exceptions: never after `$` nor
    `{`, so `$#` and `${#v}` stay expansions. The cut is applied DURING the quote
    scan, so a quote sitting after such a `#` can never take part in a pairing
    that crosses the end of that line — which is exactly bash's semantics, where
    a comment stops at its physical line whatever it contains.

    WHAT THE CUT DOES NOT DO, DELIBERATELY (D2): it ERASES nothing. The comment's
    text is not blanked, only excluded from quote pairing, so it flows on to the
    later stages UNCHANGED and is ANALYSED there. Blanking would match bash more
    closely, but a faulty recognition would then erase CODE — and the `#` lines of
    a NAKED-delimiter heredoc body, whose `$(…)` bash expands, would vanish:
    fail-open. In error this clause can only produce a FALSE POSITIVE (a comment
    containing `; rm -rf x` may be refused though bash runs nothing). Safe side,
    assumed, and that is the named price.

    ONE ASSUMED DIVERGENCE from stage 0.5, in the safe direction: that automaton
    reopens a word start after a `<<` (it needs to), this scanner does not — `<`
    is not in the separator class. So it cuts LESS often, which can only produce
    one more ANALYSED. Widening the class would touch stage 0.5 with no arm
    measuring it: named rather than fixed crookedly.

    T-01M5D6XV3J (T-01M55CF5, T-01M55BRE) — a RECURSIVE reading, port rule for
    rule of `scrub_spans` in .claude/hooks/safe-bash.sh @05c8182b, the CONTRACTS
    and not a re-derivation:
      - `$'…'` is an ANSI-C quote: a backslash escapes inside it, so `$'\''` is
        ONE span holding an apostrophe — read as `'…'` it opened a false span
        that swallowed `; git reset --hard ;` on the three hosts. The span starts
        at the `$`; the word is decoded by ansi_decode() when it is read;
      - inside "…", an UNESCAPED `$(…)` or backtick is CODE: the quoted span is
        cut around it and the inside is read as a command (`echo "$(git reset
        --hard)"` runs the reset); `\$(` and an escaped backtick stay text;
      - in that code, a heredoc body with a QUOTED delimiter is DATA up to the
        first line that STARTS with the delimiter once leading blanks are
        stripped (`EOF)` included) — an accepted FALSE POSITIVE where bash
        closes later (`EOFX`); a body line that starts with `)` (bash 3.2 closes
        the substitution there) or a body never closed takes the STOP PATH;
      - a NAKED (or top-level) heredoc body keeps its quotes LITERAL: only its
        `$(…)` and backticks are code, so an apostrophe living there opens
        nothing (T-00000224, CLOSED here);
      - `${…}`, `$((…))` and `((…))` are read as ONE BLOCK (_opaque): no span
        and no heredoc inside, their text stays ANALYSED; an ANSI-C quote, a
        substitution or a backtick inside the block takes the STOP PATH.
    THE STOP PATH, the one answer to every doubt: a nested construction that
    does not close, more than 64 levels, or any of the forms above, STOPS the
    reading — nothing after the quote that opened it is neutralised, so all of
    it is ANALYSED (bash runs nothing after an unclosed construction), and no
    speculative re-reading is ever made (it would be exponential). NAMED, not
    closed: the `)` of a `case` pattern inside a quoted `"$(…)"` closes the
    substitution early for this scanner, and the rest reads as quoted data.

    NOTE: audit_gate.py (and audit-gate.sh) still carry the PREVIOUS scanner,
    without ANSI-C nor substitutions in "…" — T-01M5D8B1JJ.
    """
    spans = []
    n = len(text)
    meta = " \t;&|()<>\n"
    stop = [False]

    def single(i):
        k = i + 2 if text[i] == "$" else i + 1
        while k < n:
            if text[i] == "$" and text[k] == _HD_BS:
                k += 2
                continue
            if text[k] == _HD_SQ:
                return k + 1
            k += 1
        return -1

    def opaque(i, close):
        j = _opaque(text, i, close)
        if j == -1:
            stop[0] = True
        return j

    def double(i, lvl):
        start = i
        k = i + 1
        while k < n:
            c = text[k]
            if c == _HD_BS:
                k += 2
                continue
            if c == _HD_DQ:
                spans.append((start, k + 1))
                return k + 1
            if c == "$" and text.startswith("((", k + 1):
                j = opaque(k + 3, "))")
                if j == -1:
                    return -1
                if j > 0:
                    if k > start:
                        spans.append((start, k))
                    start = j
                    k = j
                    continue
            if c == _HD_BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                if k > start:
                    spans.append((start, k))
                k = code(k + 1 if c == _HD_BT else k + 2, c if c == _HD_BT else ")", lvl + 1)
                if k < 0:
                    return -1
                start = k
                continue
            k += 1
        return -1

    def delimiter(i):
        dash = i < n and text[i] == "-"
        if dash:
            i += 1
        while i < n and text[i] in " \t":
            i += 1
        word = []
        quoted = False
        braced = False
        while i < n and text[i] not in meta:
            c = text[i]
            if c == _HD_SQ or c == _HD_DQ:
                j = text.find(c, i + 1)
                if j < 0:
                    stop[0] = True
                    return i, None
                spans.append((i, j + 1))
                word.append(text[i + 1:j])
                quoted = True
                i = j + 1
                continue
            if c == _HD_BS and i + 1 < n:
                word.append(text[i + 1])
                quoted = True
                i += 2
                continue
            if c in "{}":
                braced = True
            word.append(c)
            i += 1
        # T-01M5D6XV3J (exec-critic): bash DOES apply quote removal to a delimiter (`$'EOF'` -> EOF, `"E\$F"` ->
        # E$F, measured under bash 3.2 and 5.3); this reader does not replicate it, so any delimiter outside
        # [A-Za-z0-9_] — the rule of stage 0.5 (_heredoc_delimiter) —, an empty word or an unclosed quote is
        # UNREADABLE and takes the STOP PATH (all that follows is analysed), never a body.
        if not word or (quoted and braced) or any(ch not in _HD_CHARS for ch in "".join(word)):
            stop[0] = True
            return i, None
        return i, ("".join(word), quoted, dash)

    def bare(i, word, dash, close, lvl):
        while i < n:
            e = text.find("\n", i)
            line = text[i:] if e < 0 else text[i:e]
            first = line.lstrip("\t") if dash else line
            if first == word or (close == ")" and first.startswith(word + ")")):
                return i
            k = i
            while k < n and text[k] != "\n":
                c = text[k]
                if c == _HD_BS:
                    k += 2
                    continue
                if c == _HD_BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                    k = code(k + 1 if c == _HD_BT else k + 2, c if c == _HD_BT else ")", lvl + 1)
                    if k < 0:
                        return n
                    continue
                k += 1
            i = k + 1
        return n

    def bodies(i, docs, close, lvl):
        for at, (word, quoted, dash) in enumerate(docs):
            last = at == len(docs) - 1
            if i >= n:
                return n
            if quoted and close:
                k = i
                found = -1
                while True:
                    e = text.find("\n", k)
                    if e < 0:
                        e = n
                    if text[k:e].lstrip(" \t").startswith(word):
                        found = k
                        break
                    if text[k:e].lstrip(" \t").startswith(")"):
                        stop[0] = True          # bash 3.2 closes `$(` there: STOP PATH
                        return n
                    if e >= n:
                        break
                    k = e + 1
                if found >= 0:
                    if found - 1 > i:
                        spans.append((i, found - 1))
                    i = found
                    if not last:
                        e = text.find("\n", i)
                        i = n if e < 0 else e + 1
                    continue
            i = bare(i, word, dash, close, lvl)
            if not last and i < n:
                e = text.find("\n", i)
                i = n if e < 0 else e + 1
        return i

    def code(i, close, lvl):
        if lvl > 64:
            stop[0] = True
            return -1
        head = True
        depth = 0
        docs = []
        while i < n:
            c = text[i]
            if c == "\n" and docs:
                i = bodies(i + 1, docs, close, lvl)
                docs = []
                head = True
                continue
            if c == _HD_BS:
                i += 2
                head = False
                continue
            if c == "#" and head:
                j = text.find("\n", i)          # EXCLUDED from pairing, never erased
                if j < 0:
                    break
                i = j
                continue
            if close and c == close and (close == _HD_BT or depth == 0):
                return i + 1
            if (c == "$" and i + 1 < n and text[i + 1] == "{") or (c == "$" and text.startswith("((", i + 1)) \
                    or (c == "(" and text.startswith("(", i + 1)):
                if text[i + 1] == "{":
                    j = opaque(i + 2, "}")
                else:
                    j = opaque(i + (3 if c == "$" else 2), "))")
                if j == -1:
                    if close:
                        return -1
                    break
                if j > 0:
                    i = j
                    head = False
                    continue
            if c == _HD_SQ or (c == "$" and i + 1 < n and text[i + 1] == _HD_SQ):
                j = single(i)
                if j < 0:
                    i += 1                      # unpaired: closes nothing
                    head = False
                    continue
                spans.append((i, j))
                i = j
                head = False
                continue
            if c == _HD_DQ:
                mark = len(spans)
                j = double(i, lvl)
                if j < 0:
                    del spans[mark:]
                    if stop[0]:
                        if close:
                            return -1
                        break
                    i += 1
                    head = False
                    continue
                i = j
                head = False
                continue
            if c == "<" and i + 1 < n and text[i + 1] == "<":
                if i + 2 < n and text[i + 2] == "<":
                    i += 3
                    head = True
                    continue
                i, doc = delimiter(i + 2)
                if doc:
                    docs.append(doc)
                elif stop[0]:
                    if close:
                        return -1
                    break
                head = False
                continue
            if c == "(":
                depth += 1
            elif c == ")" and depth > 0:
                depth -= 1
            i += 1
            head = c in _STAGE1_SEP
        if close:
            stop[0] = True
            return -1
        return n

    code(0, "", 0)
    return spans


def _opaque(text, i, close):
    """End (exclusive) of a `${…}` (close "}", `i` after `${`) or of a `$((…))`/`((…))` (close "))", `i` after the
    `((`) read as ONE block, quotes skipped; -2 when `((` turns out not to be an arithmetic; -1 when it never closes
    OR holds an ANSI-C quote, a `$(` or a backtick (double quotes included): the caller takes the STOP PATH (port
    of `opaque` in safe-bash.sh @05c8182b, N1). Shared by stage 1 (quoted_spans) and stage 0.5 (_heredoc_scan)."""
    n = len(text)
    depth = 0
    k = i
    while k < n:
        c = text[k]
        if c == _HD_BS:
            k += 2
            continue
        if c == _HD_BT or (c == "$" and k + 1 < n and text[k + 1] in "(" + _HD_SQ):
            return -1
        if c == _HD_SQ or c == _HD_DQ:
            k += 1
            while k < n and text[k] != c:
                if c == _HD_DQ and text[k] == _HD_BS:
                    k += 1
                elif c == _HD_DQ and (text[k] == _HD_BT or (text[k] == "$" and k + 1 < n and text[k + 1] == "(")):
                    return -1
                k += 1
            k += 1
            continue
        if close == "}":
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0:
                    return k + 1
                depth -= 1
        elif c == "(":
            depth += 1
        elif c == ")":
            if depth > 0:
                depth -= 1
            elif k + 1 < n and text[k + 1] == ")":
                return k + 2
            else:
                return -2
        k += 1
    return -1


_ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
                "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def ansi_decode(body):
    """The text bash makes of the BODY of a `$'…'` quote, or None when it cannot be read — the WHOLE contract of
    `ansi_decode` in safe-bash.sh:1350-1397 @05c8182b: `\\a \\b \\e \\E \\f \\n \\r \\t \\v \\\\ \\' \\" \\?`; `\\NNN`
    1 to 3 octal digits, value mod 256; `\\xHH` (2), `\\uHHHH` (4), `\\UHHHHHHHH` (8) hex digits, none = the letter
    kept literally; a value of 0x110000 or more, or a UTF-16 half (0xD800-0xDFFF), is UNREADABLE (None); `\\c` is
    UNREADABLE; any other `\\y` stays literal; the result is cut at its first NUL (bash ends the word there)."""
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        x = body[i + 1]
        if x in _ANSI_SIMPLE:
            out.append(_ANSI_SIMPLE[x])
            i += 2
            continue
        if x in "01234567":
            j = i + 1
            v = 0
            while j < n and j < i + 4 and body[j] in "01234567":
                v = v * 8 + int(body[j])
                j += 1
            out.append(chr(v % 256))
            i = j
            continue
        if x in "xuU":
            lim = 2 if x == "x" else (4 if x == "u" else 8)
            j = i + 2
            v = 0
            while j < n and j < i + 2 + lim and body[j] in "0123456789abcdefABCDEF":
                v = v * 16 + int(body[j], 16)
                j += 1
            if j == i + 2:
                out.append("\\" + x)
                i += 2
                continue
            if v >= 0x110000 or 0xD800 <= v <= 0xDFFF:
                return None
            out.append(chr(v))
            i = j
            continue
        if x == "c":
            return None
        out.append("\\" + x)
        i += 2
    s = "".join(out)
    return s.split("\x00", 1)[0]


def read_ansi(token):
    """Decode unquoted `$'…'` and remove the `$` of unquoted `$"…"` before shlex reads the executed word.
    An ANSI-C span becomes the single-quoted text bash makes of it (`$'-D'` -> `-D`,
    `$'\\x2d\\x2dhard'` -> `--hard`, `$'-exec'` -> `-exec`). An
    UNREADABLE body — ansi_decode() gives None, or raises: no exception leaves here — reads as `$` +
    _EXPANSION_MARK + _ANSI_UNREAD, an unquoted expansion. Inside '…' or "…" a `$'` is text; an unpaired one is
    left as written (shlex then refuses the word, which the callers already treat as unreadable)."""
    if "$'" not in token and '$"' not in token:
        return token
    out = []
    i, n = 0, len(token)
    while i < n:
        c = token[i]
        if c == "\\":
            out.append(token[i:i + 2])
            i += 2
            continue
        if c == "$" and token.startswith('"', i + 1):
            i += 1
            continue
        if c in "'\"":
            k = i + 1
            while k < n and token[k] != c:
                k += 2 if (c == '"' and token[k] == "\\") else 1
            out.append(token[i:k + 1])
            i = k + 1
            continue
        if c == "$" and token.startswith("'", i + 1):
            k = i + 2
            while k < n and token[k] != "'":
                k += 2 if token[k] == "\\" else 1
            if k >= n:
                out.append(token[i:])
                break
            try:
                body = ansi_decode(token[i + 2:k])
            except Exception:  # noqa: BLE001 — the decoder never fails open
                body = None
            if body is None:
                body = "$" + _EXPANSION_MARK + _ANSI_UNREAD
            out.append("'" + body.replace("'", "'\"'\"'") + "'")
            i = k + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


# --- Stage 1.5: brace EXPANSION, as bash does it (T-01M5D6XV3J; T-01M53RGW, T-01M53HV4) ------------------------
# `{git,reset,--hard}`, `{git,branch,-D} wt/x`, `sudo {git,} reset --hard`, `git diff --{output=AGENTS.md,}`,
# `{rm,-rf} src`, `git reset --{h..h}ard` passed: the walk cut a word at its first brace and read no further.
# bash expands BEFORE it runs, so the guard does too — PORT of stage 1.5 of safe-bash.sh @05c8182b, on the
# EXECUTABLE text only (after stages 0.5 and 1: a quoted brace is `@` there). Expanded: a LIST `{a,b}` (a comma
# outside any nested brace) and a SEQUENCE `{x..y[..n]}` of integers or of one letter; never a `${…}` nor an
# escaped brace. Any other brace (`{x}`, `@{-1}`, `${x:-{y}}`) stays, and the walk cuts there as before. BOUND:
# 256 words per word (more than 256 braces, or a number of more than 9 digits, rejected BEFORE any computation),
# 1024 per command. Past it — or for a brace word holding a quoted piece, or left open before a substitution, a
# process substitution, an arithmetic or a backtick that bash keeps IN the word — the word is UNREAD, and the
# command is refused (rule brace-expansion-unread) when its segment names git, rm, find or xargs, or when that
# word stands in or before the command word (envelopes of ENVELOPES, their options and values — `-S` and a
# timeout's duration included — and reserved words are not the command word). Any exception = UNREAD, never a
# traceback. The expanded text is walked in a SECOND pass by safe_bash.main, the first pass on the text as
# written still standing: its refusals all stand, save one (T-01M5F4GJZD) — the cut of a brace list or sequence
# on `git branch -D`, in a segment whose RAW text holds only the closed set `_REREAD_SAFE` (safe_bash.py), that
# this expansion changes, and EXACTLY as bash 5 does (`inexact` below): there the second reading judges instead.
# INEXACT, measured against bash 5.3 (72 648 sequences): a letter sequence crossing `[ \ ] ^ _` and the backtick
# (emitted `_` here, `{V..a..6}wt/x` is `Vwt/x wt/x` in bash) and a numeric one with a `+` sign (its width).
# chrt, taskset and builtin (T-01M5D6XV3J, N3b): `chrt -i 0 rm -rf src` passed on the three hosts since bfa51a8f.
ENVELOPES = frozenset(
    "sudo doas env command exec eval time nohup nice ionice stdbuf timeout "
    "xargs watch parallel setsid chrt taskset builtin".split()
)
_BR_WORD = 256
_BR_TOTAL = 1024
_BR_HEADS = frozenset(("git", "rm", "find", "xargs"))
_BR_RESERVED = frozenset("! { if then elif else do while until coproc".split())
_BR_ENVVAL = frozenset("-u -g -n -c -C -D -p -r -t -U -T -P -a -h -S -s -k --user --group --chdir --unset --argv0 "
                       "--adjustment --prompt --split-string --signal --kill-after --class --classdata".split())
_BR_NUMERIC = re.compile(r"^(0[xX][0-9a-fA-F]+|[0-9][0-9.]*[smhd]?)$")
_BR_CUT = re.compile("([ \t;&|()<>\n`]+)")
_BR_SEGCUT = frozenset(";&|()\n`")
_BR_ASSIGN = re.compile(r"^[A-Za-z_][0-9A-Za-z_]*=")
_BR_SEQ_INT = re.compile(r"^([+-]?[0-9]+)[.][.]([+-]?[0-9]+)(?:[.][.]([+-]?[0-9]+))?$")
_BR_SEQ_CHR = re.compile(r"^([A-Za-z])[.][.]([A-Za-z])(?:[.][.]([+-]?[0-9]+))?$")


class _BraceOver(Exception):
    """A brace word past the bound: UNREAD."""


def _brace_table(w):
    """ONE stack pass over the word (linear, F7): the closing brace and the top-level commas of each `{`."""
    match, commas, stack = {}, {}, []
    k, n = 0, len(w)
    while k < n:
        c = w[k]
        if c == "\\":
            k += 2
            continue
        if c == "$" and k + 1 < n and w[k + 1] == "{":
            j = w.find("}", k + 2)
            if j < 0:
                break
            k = j + 1
            continue
        if c == "{":
            stack.append(k)
            commas[k] = []
        elif c == "}":
            if stack:
                match[stack.pop()] = k
        elif c == "," and stack:
            commas[stack[-1]].append(k)
        k += 1
    return match, commas


def _brace_sequence(inner, flags=None):
    """The words of a sequence `{x..y[..n]}`, or None; `flags["inexact"]` set when they may differ from bash's."""
    flags = {} if flags is None else flags
    m = _BR_SEQ_INT.match(inner) or _BR_SEQ_CHR.match(inner)
    if m and any(g and len(g.lstrip("+-")) > 9 for g in m.groups()):
        raise _BraceOver()
    m = _BR_SEQ_INT.match(inner)
    if m:
        if "+" in inner:
            flags["inexact"] = True             # bash pads `+0N` otherwise (differential, bash 5.3)
        a, b = int(m.group(1)), int(m.group(2))
        step = (abs(int(m.group(3))) if m.group(3) else 1) or 1
        if abs(b - a) // step + 1 > _BR_WORD:
            raise _BraceOver()
        width = 0
        for g in (m.group(1), m.group(2)):
            digits = g.lstrip("+-")
            if len(digits) > 1 and digits[0] == "0":
                width = max(len(m.group(1)), len(m.group(2)))
        sign = 1 if b >= a else -1
        return [str(v).zfill(width) for v in range(a, b + sign, sign * step)]
    m = _BR_SEQ_CHR.match(inner)
    if m:
        a, b = ord(m.group(1)), ord(m.group(2))
        step = (abs(int(m.group(3))) if m.group(3) else 1) or 1
        sign = 1 if b >= a else -1
        chars = [chr(v) for v in range(a, b + sign, sign * step)]
        if not all(c.isalpha() for c in chars):
            flags["inexact"] = True             # bash emits the real `[ \ ] ^ _` or backtick, and re-reads it
        return [c if c.isalpha() else "_" for c in chars]
    return None


def _brace_expand(w, lo, hi, match, commas, flags=None):
    i = lo
    while i < hi:
        c = w[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and i + 1 < hi and w[i + 1] == "{":
            j = w.find("}", i + 2, hi)
            if j < 0:
                return [w[lo:hi]]
            i = j + 1
            continue
        if c == "{":
            j = match.get(i, -1)
            if i < j < hi:
                if commas[i]:
                    items = []
                    cuts = [i] + commas[i] + [j]
                    for a, b in zip(cuts, cuts[1:]):
                        items.extend(_brace_expand(w, a + 1, b, match, commas, flags))
                        if len(items) > _BR_WORD:
                            raise _BraceOver()
                else:
                    items = _brace_sequence(w[i + 1:j], flags)
                if items is not None:
                    tail = _brace_expand(w, j + 1, hi, match, commas, flags)
                    if len(items) * len(tail) > _BR_WORD:
                        raise _BraceOver()
                    return [w[lo:i] + x + y for x in items for y in tail]
        i += 1
    return [w[lo:hi]]


def _brace_base(w):
    b = (w[1:] if w.startswith("\\") else w).lower().split("/")[-1]
    return b[:-4] if b.endswith(".exe") else b


def _brace_line(raw, scr, state):
    """One line: `(raw, scrubbed)` with every readable brace word expanded in BOTH (the same text: a word without a
    quoted piece is the same in both), state["unread"] set when an unread word must refuse the command."""
    parts = _BR_CUT.split(scr)
    starts, pos = [], 0
    for part in parts:
        starts.append(pos)
        pos += len(part)
    segs = [[]]
    for k, part in enumerate(parts):
        if k % 2 == 1:
            if set(part) & _BR_SEGCUT:
                segs.append([])
        elif part:
            segs[-1].append(k)
    new = {}
    for seg in segs:
        cmd, inenv, skipval = -1, False, False
        for at, k in enumerate(seg):
            w = parts[k]
            if skipval:
                skipval = False
                continue
            if _BR_ASSIGN.match(w) or w in _BR_RESERVED:
                continue
            if _brace_base(w) in ENVELOPES:
                inenv = True
                continue
            if inenv and w.startswith("-"):
                skipval = w in _BR_ENVVAL
                continue
            if inenv and _BR_NUMERIC.match(w):
                continue
            cmd = at
            break
        names = any(_brace_base(parts[k]) in _BR_HEADS for k in seg)
        closer_after = [False] * (len(seg) + 1)       # a later word of the segment holds `}` (linear, F7)
        for at in range(len(seg) - 1, -1, -1):
            closer_after[at] = closer_after[at + 1] or "}" in parts[seg[at]]
        failed = at_head = False
        for at, k in enumerate(seg):
            w = parts[k]
            if "{" not in w:
                continue
            ok = True
            if w.count("{") > w.count("}"):
                nxt = parts[k + 1] if k + 1 < len(parts) else ""
                if "(" in nxt or "`" in nxt or closer_after[at + 1]:
                    ok = False
            items = [w]
            if ok:
                try:
                    if w.count("{") > _BR_WORD:
                        raise _BraceOver()
                    match, commas = _brace_table(w)
                    items = _brace_expand(w, 0, len(w), match, commas, state)
                    if state["used"] + len(items) > _BR_TOTAL:
                        raise _BraceOver()
                    if items != [w] and raw[starts[k]:starts[k] + len(w)] != w:
                        raise _BraceOver()             # a quoted piece in an expanded word: unread
                except Exception:  # noqa: BLE001 — UNREAD, never a traceback
                    items = [w]
                    ok = False
            if not ok:
                failed = True
                if cmd < 0 or at <= cmd:
                    at_head = True
                continue
            if items != [w]:
                state["used"] += len(items)
                names = names or any(_brace_base(x) in _BR_HEADS for x in items)
                new[k] = " ".join(items)
        if failed and (names or at_head):
            state["unread"] = True
    out_raw, out_scr = [], []
    for k, part in enumerate(parts):
        out_raw.append(new.get(k, raw[starts[k]:starts[k] + len(part)]))
        out_scr.append(new.get(k, part))
    return "".join(out_raw), "".join(out_scr)


def expand_braces(raw, scrubbed):
    """`(raw, scrubbed, unread, inexact)` — stage 1.5 on the heredoc-free text and its isometric scrub, both expanded
    alike (the pair stays isometric). A line that raises is kept as written and the command is UNREAD. `inexact`:
    a sequence was expanded otherwise than bash 5 does (`_brace_sequence`), so the text may not be bash's."""
    state = {"used": 0, "unread": False, "inexact": False}
    if "{" not in scrubbed:
        return raw, scrubbed, False, False
    out_raw, out_scr = [], []
    start = 0
    for line_scr in scrubbed.split("\n"):       # cut on the SCRUBBED newlines: a quoted one is `@` there
        line_raw = raw[start:start + len(line_scr)]
        start += len(line_scr) + 1
        try:
            line_raw, line_scr = _brace_line(line_raw, line_scr, state)
        except Exception:  # noqa: BLE001 — UNREAD, never a traceback
            state["unread"] = True
        out_raw.append(line_raw)
        out_scr.append(line_scr)
    return "\n".join(out_raw), "\n".join(out_scr), state["unread"], state["inexact"]

# --- Stage 0.5: a heredoc BODY is redirected DATA, never code ---------------
# PORT of .claude/hooks/safe-bash.sh stage 0.5 (T-00000210's PIECE PARSER, not
# the `OPEN_RE` regex it replaced), rule for rule. It runs BEFORE stage 1
# because a heredoc body is not QUOTED — it is REDIRECTED — so quoted_spans()
# can do nothing about it. The founding incident is the third of its kind: a
# `git commit -F -` whose message DESCRIBED a guarded command was refused.
#
# THE THREE LOAD-BEARING PROPERTIES, each of which a "simplification" would
# break in a direction the guard cannot afford:
#
#  1. POLARITY. A body is blanked ONLY IF AT LEAST ONE PIECE OF THE DELIMITER
#     IS QUOTED. Bash builds the delimiter word by CONCATENATING pieces and then
#     removing the quotes, so `<<'A'B` -> `AB`, `<<\EOF` -> `EOF`, `<<E"O"F` ->
#     `EOF`, and each of those bodies is 100% literal. A fully NAKED delimiter
#     (`<<EOF`) is the opposite case: bash EXPANDS `$(…)` inside that body, so
#     the body really can execute a command and it stays ANALYSED. Blanking it
#     would be a fail-open.
#  2. FAIL-CLOSED ON EVERY NON-RECOGNITION. An unknown piece, a character
#     outside `[A-Za-z0-9_]`, an unclosed quote, a missing word boundary, no
#     quoted piece at all: the parser returns "" and the body is KEPT, hence
#     analysed. That is the parser's ONLY error exit, by design.
#  3. THE TRAILING WORD BOUNDARY IS PART OF RECOGNITION. After the last piece
#     there must be end-of-line or a separator; without it the parser would keep
#     a PREFIX of the delimiter, never find its closing line, and blank to the
#     end of the payload — a measured fail-open.
#
# The scan of the introduction line is anchored on the FIRST `<<` candidate with
# NO retry (a retry reopens the herestring hole `<<<`), refuses to open a body
# when the line does not end in a NEUTRAL state (unpaired quote, trailing `\`,
# open `(`/`[`/`{`/backtick — bash opens the body after the LOGICAL line), and
# stops at an unquoted `#` in word-initial position.
#
# NOT COVERED, enumerated rather than universally claimed: a delimiter carrying a
# space, a `$` or a dot stays outside `[A-Za-z0-9_]`, so its body is ANALYSED
# (bounded FALSE POSITIVE, never a fail-open). CLOSED by T-01M5D6XV3J, ahead of
# the Claude homologue: a `<<'W'` inside `${…}`, `$((…))` or `((…))` (`${v#<<'X'}`,
# `$((1<<'E'))`) opens no body — the block is read whole (_opaque), and one that
# does not close on its line, or holds `$'`, `$(` or a backtick, opens none. The
# automaton also reads `$'…'` as an ANSI-C quote (a backslash escapes in it). The COMMENT-BOUNDARY
# clause of stage 1 used to be listed here as NOT ported and live — T-00000225
# closed it, and stage 1 now REUSES the `#`/`head` clause below rather than
# owning a second copy of it; the line is corrected instead of left standing,
# because a comment that describes a hole already shut is the next reader's bug.
_HD_SQ = "'"
_HD_DQ = '"'
_HD_BS = "\\"
_HD_BT = "`"
_HD_SEP = " \t;&|()" + _HD_BT
_HD_TAIL = _HD_SEP + "<>"
# The SAME class, extended by the ONE character stage 0.5 cannot see: it scans a
# PHYSICAL line at a time, so a newline never reaches it, while stage 1 scans the
# WHOLE payload and must treat a line start as a word start. DERIVED, never a
# second literal — two spellings of one frontier diverge at the first change
# (D1), and the Claude homologue writes exactly this pair (safe-bash.sh l.309 vs
# l.540). Read by quoted_spans() above: a module global is resolved at CALL time,
# so the constant may be defined after the function that uses it, and it is kept
# HERE, beside the clause it is shared with, rather than beside its second reader.
_STAGE1_SEP = _HD_SEP + "\n"
_HD_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"


def _heredoc_delimiter(line, at):
    """The delimiter word of the `<<` at offset `at`, or "" (fail-closed).

    Pieces are ENUMERATED AND CLOSED — `'X'`, `"X"`, `\\c`, or a NAKED run — each
    bounded to `[A-Za-z0-9_]`; the delimiter is their concatenation with the
    quotes removed. "" whenever at least one piece is not quoted, or anything at
    all is unrecognised: the caller then keeps the body and it stays analysed.
    """
    n = len(line)
    i = at + 2
    if i < n and line[i] == "-":
        i += 1
    while i < n and line[i] in " \t":
        i += 1
    parts = []
    quoted = False
    while i < n:
        ch = line[i]
        if ch == _HD_SQ or ch == _HD_DQ:
            end = line.find(ch, i + 1)
            if end < 0:
                return ""
            inner = line[i + 1:end]
            for c in inner:
                if c not in _HD_CHARS:
                    return ""
            parts.append(inner)
            quoted = True
            i = end + 1
            continue
        if ch == _HD_BS:
            if i + 1 >= n or line[i + 1] not in _HD_CHARS:
                return ""
            parts.append(line[i + 1])
            quoted = True
            i += 2
            continue
        if ch in _HD_CHARS:
            parts.append(ch)
            i += 1
            continue
        break
    if not quoted:
        return ""                       # POLARITY: a naked delimiter EXPANDS
    if i < n and line[i] not in _HD_TAIL:
        return ""                       # a prefix would over-blank to the end
    return "".join(parts)


def _heredoc_scan(line):
    """`(loose, cont, cands)` for one PHYSICAL line.

    `loose` is the offset of the first unpaired quote, `cont` says the line does
    not end in a neutral state, and `cands` holds the offsets of every `<<`
    written outside quotes and before any comment. A `\\<` never forms `<<`, and
    a `#` in word-initial position ends the line for recognition purposes.
    """
    n = len(line)
    i = 0
    loose = -1
    par = 0
    brk = 0
    brc = 0
    tick = 0
    cont = False
    cands = []
    head = True
    while i < n:
        ch = line[i]
        if ch == _HD_BS:
            if i + 1 >= n:
                cont = True
            i += 2
            head = False
            continue
        ansi = ch == "$" and i + 1 < n and line[i + 1] == _HD_SQ
        if ch == _HD_SQ or ch == _HD_DQ or ansi:
            end = i + 2 if ansi else i + 1
            if ansi:
                ch = _HD_SQ
            while end < n:
                if (ch == _HD_DQ or ansi) and line[end] == _HD_BS:
                    end += 2
                    continue
                if line[end] == ch:
                    break
                end += 1
            if end >= n:
                if loose < 0:
                    loose = i
                i += 1
            else:
                i = end + 1
            head = False
            continue
        if ch == "#" and head:
            break
        # T-01M5D6XV3J: `${…}`, `$((…))` and `((…))` are ONE block (_opaque) — a `<<` inside one is no
        # redirection; never closed on this line, or holding `$'`, `$(` or a backtick: no body opens.
        if (ch == "$" and line.startswith("{", i + 1)) or line.startswith("((", i + (1 if ch == "$" else 0)):
            j = _opaque(line, i + 2, "}") if line.startswith("{", i + 1) else \
                _opaque(line, i + (3 if ch == "$" else 2), "))")
            if j == -1:
                cont = True
                break
            if j > 0:
                i = j
                head = False
                continue
        if ch == "<" and i + 1 < n and line[i + 1] == "<":
            cands.append(i)
            i += 2
            head = True
            continue
        if ch == "(":
            par += 1
        elif ch == ")":
            if par > 0:
                par -= 1
        elif ch == "[":
            brk += 1
        elif ch == "]":
            if brk > 0:
                brk -= 1
        elif ch == "{":
            brc += 1
        elif ch == "}":
            if brc > 0:
                brc -= 1
        elif ch == _HD_BT:
            tick = 1 - tick
        i += 1
        head = ch in _HD_SEP
    if tick or par > 0 or brk > 0 or brc > 0:
        cont = True
    return loose, cont, cands


def _heredoc_opener(line, base, spans):
    """The delimiter this line opens a body with, or "".

    ANCHORED on the FIRST candidate with no retry — retrying at the next offset
    is exactly what let a herestring `<<<` be read as a heredoc — and refusing
    outright when the line carries an unpaired quote or does not end neutral,
    because bash opens the body after the LOGICAL line, not this physical one.

    AND REFUSING when the candidate sits INSIDE a quoted segment opened on an
    EARLIER line (T-00000235, the ROOT critical). `loose` only ever saw a quote
    left open on THIS physical line; the state that matters — "are we already
    inside a string?" — exists only at whole-TEXT level, and stage 1 computes it
    AFTER this stage by construction. Without the veto, `echo "a` / `cat <<X`
    made this stage believe in an opener, blank to the end for want of a
    delimiter, and erase the REAL closing quote together with the guarded command
    that followed it, outside any quoting. Stage 1 never saw that command: it had
    disappeared before its turn. FAIL-OPEN, in CODE territory.

    The veto CALLS `quoted_spans()` rather than restating its rule — on this host
    that function is shared by both stages, so there is no second copy to keep in
    step (the bash homologues must copy it, and pin the copy with an arm). Note
    what the shared rule buys: an UNPAIRED quote opens nothing, so a stray
    apostrophe cannot veto every later heredoc — which is exactly the regression a
    hand-rolled cumulative automaton would have introduced.
    """
    loose, cont, cands = _heredoc_scan(line)
    if not cands:
        return ""
    if loose >= 0 or cont:
        return ""
    at = cands[0]
    for lo, hi in spans:
        if lo <= base + at < hi:
            return ""
    return _heredoc_delimiter(line, at)


def strip_heredoc_bodies(command):
    """The command with every QUOTED-delimiter heredoc body replaced by empty
    lines; naked-delimiter bodies are left untouched (property 1 above).

    The line COUNT is preserved, so stage 2's cut on `\\n` sees the same number of
    segments and the introduction line stays code. `\\r` is stripped from EVERY
    line at storage, not from body lines alone: otherwise `EOF\\r` != `EOF`, the
    body never closes and everything after it is blanked. The closing line is
    reprinted VERBATIM; a body opened and never closed blanks to the end, which
    is safe because an unterminated heredoc is a bash parse error — nothing runs.
    (The Claude homologue drops one trailing newline here; that is undoing its
    own `printf '%s\\n'`, and there is no such addition on this side.)
    """
    src = []
    for raw in command.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        src.append(raw)
    # Offsets computed on the RECONSTRUCTED text, never on the original: `\r` is
    # stripped from every line above, so spans taken from the raw command would
    # drift by one character per CRLF line and the veto would aim beside its
    # target — on a Windows checkout, that is every line.
    spans = quoted_spans("\n".join(src))
    bases = []
    pos = 0
    for line in src:
        bases.append(pos)
        pos += len(line) + 1
    out = []
    total = len(src)
    i = 0
    while i < total:
        out.append(src[i])
        delim = _heredoc_opener(src[i], bases[i], spans)
        if delim:
            i += 1
            while i < total and src[i].strip(" \t") != delim:
                out.append("")
                i += 1
            if i < total:
                out.append(src[i])
        i += 1
    return "\n".join(out)
