# The git-hooks-bypass verdict below (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) was written after reading
# scripts/hooks/block-no-verify.js of ECC (everything-claude-code); no line of it is copied, its notice is
# kept here in full:
#
# MIT License
#
# Copyright (c) 2026 Affaan Mustafa
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""The git-hooks-bypass rule of safe_bash.py (T-01M5C1AF6GB3ZRX5QF9SF6R80Y), split out of safe_bash_git.py.

A LEAF: stdlib only, it imports nothing of this kit; safe_bash_git.py imports it (and re-exports HOOKS_REASON
and hooks_refusal), the way safe_bash.py loads safe_bash_git. Moved here so that safe_bash_git.py stays under
the 1600-line bound (test_python_file_length). The Codex and Gemini copies are held identical, like their
siblings, and the benches that copy the bridges into a fixture copy this file too.
"""
import re

# --- The git hooks bypass (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) — PORT of the same lines of decide_git ----
# V, the verbs that run a hook; the six with a --no-verify (git 2.54: cherry-pick and revert have none);
# per verb, the short letters taking a SEPARATE value and those taking an OPTIONAL glued one (`-h`).
_HOOK_VERBS = frozenset("commit push merge rebase am pull cherry-pick revert".split())
_VERIFY_VERBS = frozenset("commit push merge rebase am pull".split())
_CLUSTER = {"commit": ("FmcCtU", "uS"), "am": ("Cp", "S")}
# `git config`: a word naming what disarms the hooks, the read options, the closed list of options a
# pure read may carry (valued ones GLUED only) — annexe § 3 of the plan.
_CFG_MENTION = ("hookspath", "core.worktree", "alias.", "include")
_CFG_READ_LONG = ("get-all", "get-regexp", "get-urlmatch", "get-color", "get-colorbool")
_CFG_SAFE = frozenset(
    "--local --global --system --worktree --show-origin --show-scope --show-names --name-only -z --null "
    "--includes --no-includes --fixed-value --bool --int --bool-or-int --bool-or-str --path --expiry-date "
    "--all --regexp -l".split()
)
_CFG_GLUED = ("--file=", "--blob=", "--type=", "--default=", "--value=", "--url=")
# The environment that skips or redirects the hooks, ANCHORED on a non-name character (`FOO_SKIP=`,
# `NOHUSKY=`, `GIT_CONFIG_NOSYSTEM=` do not match); counted only beside a verb of V.
_HOOK_ENV = re.compile(
    r"(?:^|[^A-Za-z0-9_])(?:GIT_CONFIG_(?:PARAMETERS|COUNT|KEY_[0-9]+|VALUE_[0-9]+|GLOBAL|SYSTEM)"
    r"|HUSKY|HUSKY_SKIP_HOOKS|LEFTHOOK|SKIP)="
)
# The refusal, said ONCE for the three hosts: safe-bash.sh echoes the same text after `BLOCKED: `
# (test_garde_contournement_hooks compares them).
HOOKS_REASON = (
    "this git command skips the repository's git hooks (rule git-hooks-bypass) — the pre-commit, commit-msg and "
    "pre-push gates, so what they would refuse ships unseen. Read here: `--no-verify` and every abbreviation from "
    "`--no-v` on commit, push, merge, rebase, am and pull; `-n` in a short cluster of `commit` or `am` (`-an`; "
    "`-uno` and the text of a value letter do not count); an UNQUOTED expansion among the options of those six "
    "verbs (`$F`, `$(…)`, a backtick: an option after one is unread); `-c`/`--config-env` (`=` or separated) whose "
    "value holds `hookspath` (`core.hooksPath=.githooks` exactly excepted: the key in any case, the value as written, "
    "`.GITHOOKS` refused) or `include` on a verb that runs hooks (those six, cherry-pick, revert), and `alias.` on any "
    "verb; an assignment `GIT_CONFIG_PARAMETERS=`, `GIT_CONFIG_COUNT=`, `GIT_CONFIG_KEY_<n>=`, "
    "`GIT_CONFIG_VALUE_<n>=`, `GIT_CONFIG_GLOBAL=`, `GIT_CONFIG_SYSTEM=`, `HUSKY=`, `HUSKY_SKIP_HOOKS=`, "
    "`LEFTHOOK=` or `SKIP=` anywhere in a command that runs such a verb; a `git config` with a word holding "
    "`hookspath`, `core.worktree`, `alias.`, `include` or an unquoted expansion, unless it is a pure read; and "
    "`git config -e`/`--edit`/`edit`, `remove-section`, `rename-section` (`--rem…`, `--ren…`) always. Remedy: run "
    "the command without the bypass and fix what the hook reports, or ask the user to approve this exact command. "
    "A pure read passes: `get`/`list` as the first word, or `--get`, `--get-all`…, `--list`, `-l` among the "
    "options BEFORE the first other word (after it an option is a value: `git config core.hooksPath --get` writes "
    "`--get`), every option from the closed read list, a value glued (`-f.git/config`, `--file=x`, "
    "`--type=bool`); so does `git config [set] core.hooksPath .githooks` (`--local` or `--worktree` at most). "
    "Named false positives: `--no-verify --verify`; two substitutions in one quoted string (`git commit -m \"$(a)$(b)\"`: the second one cuts the words); a value spelled like an option outside a commit/am cluster "
    "(`git commit --message \"--no-verify\"`, `git merge -m \"--no-verify\"`); a `git config` whose VALUE holds one "
    "of those words (`git config user.name alias.x`) or an unquoted expansion; the implicit read `git config "
    "core.hooksPath` (write `--get`); a read with a separated value (`-f x --get …`: write `-fx` or `--file=x`) or "
    "an option outside the closed list; `git -c core.hooksPath=/dev/null commit` in a throwaway repository; such "
    "an environment name quoted, or in a heredoc body (Codex and Gemini hosts), beside such a verb; `git push "
    "origin $b`, `git merge $b`, `git push origin $(git branch --show-current)` (quote it); on the Claude host, once the command holds a literal `@@`, a quoted word after a "
    "`git` (its subcommand, a `-c` value, an option of such a verb, a word of `git config`). Bounds, named and NOT "
    "refused — this guard prevents forgetting, not cheating: "
    "`--git-dir=<d>`/`--git-dir <d>`, `--work-tree=<d>`/`--work-tree <d>`, `GIT_DIR=` and `GIT_WORK_TREE=` with "
    "such a verb (a relative hooksPath then resolves elsewhere); a configuration redirected by `HOME=` or "
    "`XDG_CONFIG_HOME=` (a forged ~/.gitconfig acts when no local core.hooksPath is set); a quoted expansion in "
    "option position (`\"$F\"`), a quoted expansion as a `git config` key (`git config \"$K\" v`) and an expansion "
    "as a `-c` value; on the Claude host, a quoted span glued to a "
    "word (`--no-\"verify\"`, `core.hooks\"Path\"`, `co\"mmit\"`, T-00001202); `--attr-source` (T-00001193); a "
    "brace (`{--no-verify,}`) and an option after a brace, `@{u}` included (`git rebase @{u} --no-verify`); `<(…)` "
    "before an option (`git commit -F <(printf x) --no-verify`); `$'--no-verify'`; a backslash-newline (T-00001198); `printf … >> .git/config` (the "
    "redirect guard's to refuse); an alias already configured (`git ci`); plumbing that writes refs or pushes "
    "without porcelain (`commit-tree`, `update-ref`, `send-pack`); an earlier "
    "`export HUSKY=0`; a command carried in a quoted string (`bash -c \"…\"`); an envelope outside the table "
    "(`timeout 5 git …`); `chmod -x .githooks/*`; the admitted `.githooks` disarming `.husky`; a failed awk stage "
    "(Claude: degraded, announced) and a crashed Python hook (T-00001194) — bounded, not closed: these are the "
    "holes we know."
)


def _hook_setting(value):
    """`(alias, hooks)` for one `-c`/`--config-env` value, folded: `alias.` anywhere; `hookspath` anywhere
    (but the key `core.hookspath` in any case set to `.githooks` EXACTLY: git keeps the value's case, and
    `.GITHOOKS` is another directory on a case-sensitive disk) or `include` anywhere."""
    folded = value.lower()
    key, _, setting = value.partition("=")
    exempt = key.lower() == "core.hookspath" and setting == ".githooks"
    return "alias." in folded, ("hookspath" in folded and not exempt) or "include" in folded


def _cluster(word, verb):
    """`(no_verify, takes_next)` for a short cluster of `commit`/`am`: `n` read before any letter taking a
    value (`-an` yes; `-uno`, `-mn` no: the rest is that letter's value); `takes_next` when the cluster ENDS
    on a letter taking a SEPARATE value, whose value is then the next word (`-m "--no-verify"`)."""
    separate, optional = _CLUSTER[verb]
    for position, char in enumerate(word[1:], 2):
        if char in optional:
            return False, False
        if char in separate:
            return False, position == len(word)
        if char == "n":
            return True, False
    return False, False


def _config_read_option(word):
    """A read option of `git config`: `-l`, a cluster of `z`/`l` holding `l`, `--get`, `--li[s[t]]`, or a
    prefix of at least `--get-a` of get-all/get-regexp/get-urlmatch/get-color/get-colorbool (`--ge` and
    `--get-` are ambiguous: git refuses them, so they are no read)."""
    if word == "-l":
        return True
    if word.startswith("-") and not word.startswith("--") and len(word) > 2:
        return set(word[1:]) <= set("zl") and "l" in word
    if not word.startswith("--"):
        return False
    name = word[2:].split("=")[0]
    if name in ("get", "li", "lis", "list"):
        return True
    return len(name) >= 5 and name.startswith("get-") and any(option.startswith(name) for option in _CFG_READ_LONG)


def _config_safe_option(word):
    """An option a pure read may carry: the closed list, a read option, a valued one with its value GLUED."""
    return (
        word in _CFG_SAFE or _config_read_option(word) or word.startswith(_CFG_GLUED)
        or (len(word) > 2 and (word.startswith("-f") or (word.startswith("-t") and not word.startswith("-t-"))))
    )


def _config_edits(words):
    """`git config` that opens an editor or drops/renames a whole section, whatever it names: `edit`,
    `remove-section`, `rename-section` as the first word, `-e`, `--ed[it]`, `--rem…`, `--ren…` anywhere."""
    if words[:1] in (["edit"], ["remove-section"], ["rename-section"]):
        return True
    for word in words:
        if word == "-e":
            return True
        if word.startswith("--"):
            name = word[2:].split("=")[0]
            if len(name) >= 2 and "edit".startswith(name):
                return True
            if len(name) >= 3 and ("remove-section".startswith(name) or "rename-section".startswith(name)):
                return True
    return False


def _config_bypass(words, mark):
    """True when `git config <words>` may disarm the hooks (annexe § 3 of the plan): an edit or a section
    drop; else a word that MENTIONS hookspath, core.worktree, alias., include, or holds an unquoted
    expansion, unless the call is a PURE READ — `get`/`list` first, or a read option among the option words
    BEFORE the first other word (after it every word is positional: `config core.hooksPath --get` writes
    `--get`), every option of that span in the closed list — or exactly `[set] core.hookspath .githooks`
    under `--local`/`--worktree` at most. `mark` is safe_bash_git's _EXPANSION_MARK."""
    if _config_edits(words):
        return True
    folded = [word.lower() for word in words]
    if not any(mark in word or any(m in word for m in _CFG_MENTION) for word in folded):
        return False
    # The key folded, the value EXACT (`git config core.hooksPath .GITHOOKS` writes another directory).
    values = [word for word in words if not word.startswith("-")]
    if words[:1] == ["set"]:
        values = values[1:]
    if [v.lower() for v in values[:1]] == ["core.hookspath"] and values[1:] == [".githooks"] and all(w in ("--local", "--worktree") for w in words if w.startswith("-")):
        return False
    if words[:1] in (["get"], ["list"]):
        read, scope = True, words[1:]
    else:
        scope = []
        for word in words:
            if not word.startswith("-"):
                break
            scope.append(word)
        read = any(_config_read_option(word) for word in scope)
    return not (read and all(_config_safe_option(word) for word in scope if word.startswith("-")))


def hooks_refusal(command, hooks):
    """The git-hooks-bypass refusal for `command`, or "": `hooks` is the highest judge_git verdict of its git
    sites — 2 a bypass read in the words, 1 a verb of V read (then the environment prefix counts, read on
    the WHOLE command, heredoc bodies included: a divergence with the Claude host, which does not read
    them), 0 neither."""
    if hooks >= 2 or (hooks == 1 and _HOOK_ENV.search(command)):
        return "BLOCKED by shell guard: " + HOOKS_REASON
    return ""


def _double_open(piece):
    """True when a `"` is still open at the end of `piece`, read from a word's start (backslash, `'…'` honoured)."""
    single = double = False
    i = 0
    while i < len(piece):
        if piece[i] == "\\" and not single:
            i += 2
            continue
        if piece[i] == "'" and not double:
            single = not single
        elif piece[i] == '"' and not single:
            double = not double
        i += 1
    return double
