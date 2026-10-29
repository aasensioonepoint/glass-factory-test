"""Rows of test_guard_decision_parity.py for T-00001102, T-00001090 and T-01M55CF5S8BNWEDW14FPE6AYV1 —
git behind a proven envelope chain, branch deletion, and the safe-bash closure witnesses.

NOT collected (no test_ prefix; pytest.ini python_files = test_*.py). A LEAF: the parity imports
`gitenv_rows` and hands it its own `row` and verdict/motive constants; this module never imports
the parity back. Extracted so that the parity, listed in the 1600-line ratchet, never grows: the
rows still run inside its MATRIX, under its label, divergence-note and envelope-count checks.

ASSUMED HOLES, the detail the parity docstring points to:
  - behind an envelope OUTSIDE the tables (`timeout`, `nice`, `ionice`…; `xargs` at the
    head is read, below) only rm/mv fall back to substring semantics, so `timeout 5 <absent>/rg` and
    `timeout 5 git reset --hard` are NOT refused on any host (S1) — widening it
    would refuse `sudo apt install ripgrep`; behind an envelope of the TABLES
    (`env`, `sudo`, `doas`, `command`, `nohup`, `time`) git IS read since
    T-00001102 — in command position when every option is in the table and every
    value is a plain word, anywhere in the window when the window cannot be
    proven (an unknown option, a value or a command that is an expansion);
  - `sudo git rm <tracked>` PASSES since T-00001102, like the bare `git rm`, but
    ONLY behind a PROVEN envelope chain (every option in the table, no value with
    an expansion); an unknown option, an expansion or an envelope outside the
    tables keeps the old refusal (`xargs git mv a`, `timeout 60 git mv a b`,
    `sudo docker rm c`) — the false positive stays the accepted price there;
  - `env -v rm -rf src/x` and `env -v git reset --hard` pass on every host: the
    walk reads `-v` after an envelope as the `command -v` presence probe (S5);
  - an option GLUED to a QUOTED value (`sudo -u"$U" git rm -rf src/x`) proves the
    chain on Claude (the awk reads `-u` then an atomic quoted value) and not on
    the python hosts (a quoted unit is opaque there): the python hosts are the
    stricter, on the refusal side, pinned as DIVERGENCE 7 (glued form); the
    wipe itself (`sudo -u"$U" git reset --hard`) is refused on all three;
  - `xargs` at the HEAD of the command (alone, or behind table envelopes) IS read since
    T-01M5D6XS2S / T-01M5D6XV3J (`git branch --list 'wt/*' | xargs git branch -D`, named by
    the pilot S-00003933 point 3; `xargs -n 1 git restore .`), not behind an envelope outside
    the tables (`timeout 5 xargs git branch -D` passes on all three, S1); `git branch -D` is
    not read when the option comes AFTER a substitution (`git branch $(cat f) -D`: the words
    stop at the substitution);
  - NAMED in the refusals, bounded and not closed (binôme of batch 2, T-00001090):
    `checkout -B`/`switch -C wt/…` (resets a `wt/` branch, its commits left to the
    reflog), `env -S '…'` and `env -v` (S5), an envelope outside the tables
    (`timeout 5`, `nice -n 5`), and a command carried in a quoted string
    (`bash -c "…"`) — on the branch refusal and, for the last three, on the wipe;
  - an unquoted brace LIST or SEQUENCE is expanded as bash expands it and the expanded words are
    read in a second pass on every host since T-01M5D6XS2S / T-01M5D6XV3J (past the bound —
    256 words per word, 1024 per command — refused on its own rule): `git {reset,--hard}`, `git
    reset {--hard,}`, `git restore {.,}`, `git branch {-D,} wt/T-1`, `-{D,}`, `git {branch,-D}
    wt/T-1` and `git branch {x,} -D wt/T-1` are refused on all three (the `brace/*` rows);
  - the words AS WRITTEN are read too, and there a `{`/`}` outside quotes and outside a `${…}`
    (read as an expansion) ENDS the git words on every host, behind a backslash, in a comment or
    in a redirect target too: `git branch -D` counts such a cut as `wt/` (fail-closed, `@{-1}`,
    `{x}`; the cut of a brace LIST only as DIVERGENCE 11 below says), but the wipe does NOT — `git restore --source=HEAD@{1} .` (no list: the
    pathspec after the cut) passes on all three, NAMED in the wipe refusal;
  - the two sides of that cut on `git branch -D`, both NAMED in the branch refusal by their
    MECHANISM rather than by a list of forms (L-00000187; pass quater of batch 2, T-00001090):
    when the forced delete is NOT read before the cut, what follows is never read on any host
    (`git branch wt/T-1 {x} -D` passes: a gap carried by T-00001196); when it IS read before
    the cut, a NON-wt name is refused too (`feat }`, `# cleanup {x}`) — an accepted fail-closed
    false positive; a brace after the end of the command (e.g. `;`, `&`, `|`, a newline, a
    closing `)`) is not read, nor is a quoted one (`"feat{x}"`);
  - DIVERGENCE 11, NARROWED (rétrécie, T-01M5F4GJZD): `git branch -D {feat-a,feat-b}` is read
    EXPANDED on the three hosts and passes (two non-wt names, `branch/brace-list-nonwt`; `x{,}`,
    `feat{1..3}`, `-d -f {a,b}` too) — the python hosts refused the list AS WRITTEN until then;
    a brace that is no list nor sequence left in the expanded words still cuts and counts
    (`{feat-a,feat-b} }`, `{a,b} @{-1}`) and a `wt/` name in the list (`{feat,wt/x}`, `wt/{a,b}`)
    is refused, on all three. What REMAINS is refused UNIFORMLY on the three hosts since the
    double merge (T-01M5GFV9CE21H6BR56NMN8T0AP x T-01M5F4GJZD): a command segment (up to a `;`, a
    newline, or a `&`/`|` that is not part of a redirection: `2>&1`, `&>`, `>|` do not end it)
    that the guard's expansion leaves unchanged or does not reproduce EXACTLY as bash 5 does (a
    letter sequence crossing the characters between `Z` and `a`, which bash emits and re-reads:
    `{V..a..6}wt/x` is `Vwt/x wt/x`; a numeric sequence with a `+` sign; measured on 72 648
    sequences — `branch/brace-sequence-crosses-nonletter`, its motive differs by host),
    or whose RAW text, inside quotes too, holds a character outside the closed
    set `_REREAD_SAFE` (letters, digits, blanks, quotes, `{ } , . _ - / @ : = + % # < > &`), where
    the python hosts still count the cut of the list as `wt/` — that character (a backslash, a
    backslash-newline even inside quotes, a glob, `$`, `(`, `)`, a backtick, `~`, `!`, a non-ASCII
    letter) may stop or split the expanded words where bash goes on, and a CR is excluded too,
    fail-closed, as not read as bash reads it — rightly on `{a,b} \\<LF>wt/x`, `{a,b} \\; wt/x`,
    `{a,b} w?/x`, `{a,b} <(echo) wt/x`, `{a,b} >(cat) wt/x`, `{a,b} <(echo) @{-1}`, `{a,b}
    "w\\<LF>t/x"` (T-00001198, T-01M5G0VHWS9ATWXEXJJGZ9Q8QB, T-01M5G5MTC22R0E3BBBG10KTAT0), a
    fail-closed false positive on non-wt names (`(git branch -D {a,b})`, `git branch -D
    {fix-1,fix-2} > /tmp/x\\ y`, `git branch -D {a,b} x[1]`, `{a,b} ~x`, `{a,b} "w<CR>t/x"`:
    refused on the three hosts, measured) — the `branch/brace-list-*` DENY rows. The other side,
    CLAUDE STRICTER: a TAB inside quotes is in `_REREAD_SAFE`, so the python hosts pass
    `git branch -D {a,b} "w<TAB>t/x"` (no `wt/`) while safe-bash.sh refuses a quoted span that is
    not plain quotes on one line — `branch/brace-list-quoted-tab`;
  - on the Claude host only, a word after `branch` glued to a quoted span (`feat-"old"`,
    `--sort="x"`) counts as `wt/` in a forced delete (the awk's `bglue`); the python hosts
    read it through its quotes — DIVERGENCE 10 of the parity, NAMED in the branch refusal;
  - the DELETE OPTION is not read as bash reads it — a gap carried by T-00001202, NAMED in the
    branch refusal (pass sexies of batch 2, text only, measured at c9512cfc): on Claude only a
    quoted, glued or backslashed option (`git branch '-D' wt/T-1`, also with a literal `@@` in the
    command, `-"D"`, `-d '-f'`, `\\-D`; the python hosts read those, DIVERGENCE 7), and on all three
    an option glued after an expansion that may be empty (`$b-D`,
    `${b}-D`; `"$b"-D` on the python hosts only, DIVERGENCE 10) and a `--` git takes as the value
    of `--sort`/`--format` (`git branch --sort -- -D wt/T-1`) pass unread; a backslash-newline is
    not joined (`git branch -D \\<LF>wt/T-1` passes on all three, T-00001198), and a `${…}` ends
    at its first `}` (`git branch ${x:-{y}} -D wt/T-1` passes on all three, the T-00001196 side
    of the cut); an option in `$'…'` (`$'-D'`) is refused on all three since T-01M5D6XS2S /
    T-01M5D6XV3J;
  - a word bash never expands still counts as `wt/` when it is not an option and holds a `$` or a
    backtick (`'$b'`, `\\$b`, a trailing comment `# $HOME`), and a `-D` in a trailing comment is
    read (`git branch wt/x # -D`): accepted fail-closed false positives, NAMED; on Claude only, a
    literal `@@` anywhere in the command (the awk's own mark for a quoted span) makes every quoted
    word after `branch` count as `wt/`, and the `@@` itself among those words — DIVERGENCE 10;
  - `git branch -D -r wt/x` (a remote-tracking ref only) is REFUSED: an accepted
    fail-closed false positive — `-r` can be the VALUE of another option (`git
    branch -D --sort -r x` deleted the LOCAL branch, measured on git 2.55), so
    honouring it would need a measured value-option table where one miss opens.
"""

# T-00001090 : the `git branch -D wt/*` refusal has its OWN phrase on all three hosts.
MOTIVE_BRANCH = "git branch -D"
# T-00001102 : the option tables of the envelopes whose arity is PROVEN, written HERE from the manuals
# (sudo 1.9.17 --help, GNU env --help, OpenBSD doas(1), bash `command`), independent of the hooks' own copy:
# `(options without a value, options with a SEPARATE value)`.
ENVELOPE_TABLES = {
    'env': ('- -i -0 --ignore-environment --null --debug --list-signal-handling --block-signal --default-signal --ignore-signal --', '-u -C -P -a --unset --chdir --argv0'),
    'sudo': ('-A -B -b -E -H -k -N -n -P -S -i -s --askpass --bell --background --preserve-env --set-home --reset-timestamp --login --non-interactive --preserve-groups --stdin --shell --no-update --', '-C -D -g -p -R -T -U -u -r -t --close-from --chdir --group --prompt --chroot --command-timeout --other-user --user --role --type'),
    'doas': ('-L -n -s --', '-C -u'),
    'command': ('-p --', ''),
    'nohup': ('--', ''),
    'time': ('-p --', ''),
}


def gitenv_rows(row, ALLOW, DENY, PY_STRICTER, MOTIVE_GITWIPE, MOTIVE_GITOUTPUT, MOTIVE_CHECKPOINT):
    rows = []
    # T-01M55CF5S8BNWEDW14FPE6AYV1: executed locale quotes, substitutions, escapes, and coproc.
    for label, command, motive in (
        ("git-reset-hard", '$"git" reset --hard', MOTIVE_GITWIPE),
        ("rm", '$"rm" -rf src/x', MOTIVE_CHECKPOINT),
        ("rm-glued", 'r$"m" -rf src/x', MOTIVE_CHECKPOINT),
        ("git-branch", '$"git" branch -D wt/x', "unmerged work"),
        ("git-clean", '$"git" clean -fd', MOTIVE_GITWIPE),
        ("git-stash", '$"git" stash', MOTIVE_GITWIPE),
        ("sudo-rm", 'sudo $"rm" -rf src/x', MOTIVE_CHECKPOINT),
        ("env-git", 'env $"git" reset --hard', MOTIVE_GITWIPE),
        ("nohup-rm", 'nohup $"rm" -rf src/x', MOTIVE_CHECKPOINT),
    ):
        rows.append(row(f"locale/{label}", "safe_bash", command, DENY,
                        "bash executes the locale quoted command word", motive=motive))
    rows += [
        row("locale/echo", "safe_bash", 'echo $"hello"', ALLOW, "a harmless locale quoted argument"),
        row("locale/log-format", "safe_bash", 'git log --format=$"%h"', ALLOW,
            "a locale quoted format is not a destructive option"),
        row("locale/sudo-git-rm", "safe_bash", 'sudo $"git" rm -q docs/x.md', PY_STRICTER,
            "DIVERGENCE 7: Claude proves the locale quoted git command behind sudo; "
            "Python still treats the quoted wrapper command as ambiguous"),
        row("coproc/git", "safe_bash", "coproc git reset --hard", DENY,
            "coproc starts git in a command position", motive=MOTIVE_GITWIPE),
    ]
    for label, command, motive in (
        ("rm-internal", r'r\m -rf src/x', MOTIVE_CHECKPOINT),
        ("git-internal", r'g\it reset --hard', MOTIVE_GITWIPE),
        ("git-clean-internal", r'gi\t clean -fd', MOTIVE_GITWIPE),
    ):
        rows.append(row(f"escape/{label}", "safe_bash", command, DENY,
                        "an internal backslash cannot hide a destructive command", motive=motive))
    for label, command in (
        ("reset-hard-substitution", "git reset $(echo --hard)"),
        ("reset-hard-backticks", "git reset `echo --hard`"),
    ):
        rows.append(row(f"git-wipe/{label}", "safe_bash", command, DENY,
                        "an unquoted substitution can expand to --hard", motive=MOTIVE_GITWIPE))
    for label, command in (
        ("reset-path-substitution", "git reset HEAD -- $(cat list)"),
        ("clean-dry-run", "git clean -n"),
    ):
        rows.append(row(f"git-wipe/{label}", "safe_bash", command, ALLOW,
                        "a pathspec after -- or a dry run is allowed", motive=MOTIVE_GITWIPE))
    # -- T-00001102 / T-00001090 rev. 2 : git behind a PROVEN envelope chain; `git branch -D wt/*` ---------
    for label, command in (
        ("env-u", "env -u GIT_DIR git mv a.txt b.txt"),
        ("env-bare", "env git mv a.txt b.txt"),
        ("env-i", "env -i git mv a.txt b.txt"),
        ("env-assign", "env FOO=1 git mv a.txt b.txt"),
        ("command", "command git mv a.txt b.txt"),
        ("nohup", "nohup git mv a.txt b.txt"),
        ("time", "time git mv a.txt b.txt"),
        ("sudo-rm", "sudo git rm -q docs/x.md"),
        ("sudo-env", "sudo env -u GIT_DIR git mv a.txt b.txt"),
        ("env-sudo", "env -u GIT_DIR sudo git mv a.txt b.txt"),
        ("sudo-long-option", "sudo --user deploy git mv a.txt b.txt"),
        ("env-quoted-value", 'env -u "$X" git mv a.txt b.txt'),
        ("doas", "doas -u x git mv a.txt b.txt"),
        ("sudo-two-values", "sudo -u deploy -g staff git rm -q docs/x.md"),
        ("sudo-end-of-options", "sudo -- git mv a.txt b.txt"),
        ("env-quoted-assignment", 'env FOO="a b" git mv a.txt b.txt'),
        ("sudo-absolute-paths", "/usr/bin/sudo -u x /usr/bin/git mv a.txt b.txt"),
        ("sudo-global-option", "sudo git -C x mv a.txt b.txt"),
        ("env-global-option-value", "env -u X git -c core.x=1 rm -q docs/y"),
        ("sudo-no-pager", "sudo git --no-pager mv a.txt b.txt"),
        ("incident-T-1102", "cd /tmp/crm && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE git mv scripts/a.sh .agents/evals/a.sh && git status --short"),
    ):
        rows.append(row(
            f"gitenv/lifted-{label}", "safe_bash", command, ALLOW,
            "T-00001102: git behind a PROVEN envelope chain is git, not an rm/mv window; "
            "the bare `git mv` passes and so does this",
        ))
    for label, command, motive in (
        ("env-u-reset", "env -u GIT_DIR git reset --hard", MOTIVE_GITWIPE),
        ("env-u-restore", "env -u GIT_DIR git restore .", MOTIVE_GITWIPE),
        ("env-C-restore", "env -C /tmp git restore .", MOTIVE_GITWIPE),
        ("sudo-u-reset", "sudo -u x git reset --hard", MOTIVE_GITWIPE),
        ("doas-u-restore", "doas -u x git restore .", MOTIVE_GITWIPE),
        ("env-u-output", "env -u GIT_DIR git show --output=f HEAD", MOTIVE_GITOUTPUT),
        ("sudo-u-expansion", "sudo -u $U git reset --hard", MOTIVE_GITWIPE),
        ("env-u-expansion", "env -u $X git reset --hard", MOTIVE_GITWIPE),
        ("sudo-long-option", "sudo --user x git reset --hard", MOTIVE_GITWIPE),
        ("sudo-long-expansion", "sudo --user $U git reset --hard", MOTIVE_GITWIPE),
        ("sudo-g", "sudo -g grp git reset --hard", MOTIVE_GITWIPE),
        ("sudo-env", "sudo env -u GIT_DIR git reset --hard", MOTIVE_GITWIPE),
        ("env-sudo", "env -u GIT_DIR sudo git reset --hard", MOTIVE_GITWIPE),
        ("sudo-substitution", "sudo -u $(id -un) git reset --hard", MOTIVE_GITWIPE),
        ("sudo-command-expansion", "sudo $X git reset --hard", MOTIVE_GITWIPE),
        ("sudo-abbreviated-long", "sudo --us x git reset --hard", MOTIVE_GITWIPE),
        ("sudo-cluster", "sudo -nu root git reset --hard", MOTIVE_GITWIPE),
        ("sudo-unknown-option-value", "sudo --foo bar git reset --hard", MOTIVE_GITWIPE),
        ("sudo-h-host", "sudo -h host git reset --hard", MOTIVE_GITWIPE),
        ("env-S-unquoted", "env -S git reset --hard", MOTIVE_GITWIPE),
        ("sudo-two-expansions", "sudo -u $U -g $G git reset --hard", MOTIVE_GITWIPE),
        ("sudo-quoted-option-word", 'sudo "-u" x git reset --hard', MOTIVE_GITWIPE),
        ("env-absolute-paths", "/usr/bin/env -u X /usr/bin/git reset --hard", MOTIVE_GITWIPE),
        ("sudo-escaped", "\\sudo -u x git reset --hard", MOTIVE_GITWIPE),
        ("doas-expansion", "doas -u $U git restore .", MOTIVE_GITWIPE),
        ("env-u-clean", "env -u GIT_DIR git clean -fd", MOTIVE_GITWIPE),
        ("env-u-stash", "env -u GIT_DIR git stash", MOTIVE_GITWIPE),
    ):
        rows.append(row(
            f"gitenv/closed-{label}", "safe_bash", command, DENY,
            "T-00001102: the false negative CLOSED — git behind an envelope option with its "
            "value was never read as git (rc 0 on all three hosts before)", motive=motive,
        ))
    rows.append(row(
        "gitenv/closed-sudo-glued-quoted-value-wipe", "safe_bash", 'sudo -u"$U" git reset --hard', DENY,
        "T-00001102: the glued-quoted spelling of reserve 2 (S-00003937) on the WIPE — Claude passed it "
        "before (the python hosts already refused it); refused on all three now", motive=MOTIVE_GITWIPE,
    ))
    for label, command in (
        ("env-u-git-value", "env -u git rm -rf src/x"),
        ("env-C-git-value", "env -C git rm -rf src/x"),
        ("sudo-u-git-value", "sudo -u git rm -rf src/x"),
        ("env-unknown-option", "env -X git rm -rf src/x"),
        ("env-expansion-value", "env -u $X git rm -rf src/x"),
        ("env-then-rm", "env git mv a.txt b.txt; rm -rf src/x"),
        ("xargs-git-mv", "xargs git mv a.txt"),
        ("sudo-docker-rm", "sudo docker rm container"),
        ("timeout-git-mv", "timeout 60 git mv a.txt b.txt"),
        ("nice-git-mv", "nice -n 5 git mv a.txt b.txt"),
        ("env-expansion-type", "env -u $X type rm -rf src/x"),
        ("env-expansion-which", "env -u $X which rm"),
        ("sudo-long-git-value", "sudo --user git rm -rf src/x"),
        ("sudo-u-root-v", "sudo -u root -v rm -rf src/x"),
        ("env-u-rm-value", "env -u rm git status"),
        ("sudo-env-git-value", "sudo env -u git rm -rf src/x"),
        ("sudo-git-then-rm", "sudo git rm -rf src/x; rm -rf src/y"),
        ("sudo-git-status-rm", "sudo git status && rm -rf src/x"),
        ("sudo-expansion-rm", "sudo -u $U rm -rf src/x"),
        ("env-assign-expansion", "env FOO=$X git rm -rf src/x"),
        ("sudo-git-submodule-foreach", "sudo git submodule foreach rm -rf src/x"),
        ("env-git-bisect-run", "env -u X git bisect run rm -rf src/x"),
        ("sudo-git-rebase-x", "sudo git rebase -x rm -rf src/x"),
        ("sudo-git-commit-rm-word", "sudo git commit -m rm"),
        ("sudo-git-mv-rm-operand", "sudo git mv a.txt rm"),
        ("sudo-quoted-option-word", 'sudo "-u" x git mv a.txt b.txt'),
        ("sudo-E-then-rm", "sudo -E git rm -rf src/x && rm -rf src/z"),
        ("sudo-long-glued-quoted-value", 'sudo --user="$U" git rm -rf src/x'),
    ):
        rows.append(row(
            f"gitenv/kept-{label}", "safe_bash", command, DENY,
            "T-00001102: DOMINANCE on the old walk — refused before, refused after: a value that "
            "is a word, an option outside the tables, an expansion or an envelope outside the "
            "tables never closes the window; `sudo docker rm`, `timeout 60 git mv`, `nice -n 5 git "
            "mv` and `xargs git mv` stay the accepted false positives",
        ))
    rows.append(row(
        "gitenv/divergence-glued-quoted-value", "safe_bash", 'sudo -u"$U" git rm -rf src/x', PY_STRICTER,
        "DIVERGENCE 7, glued form (reserve 2 of S-00003937): the awk reads `-u` then an atomic quoted "
        "value, so the chain is PROVEN and `git rm` passes; the python hosts read the quoted unit as "
        "opaque, so the window stays ambiguous and rm is refused — stricter, on the refusal side",
    ))
    for label, command in (
        ("timeout-reset", "timeout 5 git reset --hard"),
        ("sudo-timeout-reset", "sudo timeout 5 git reset --hard"),
        ("timeout-sudo-reset", "timeout 5 sudo -u x git reset --hard"),
        ("timeout-branch", "timeout 5 git branch -D wt/T-1"),
    ):
        rows.append(row(
            f"gitenv/known-gap-{label}", "safe_bash", command, ALLOW,
            "KNOWN GAP, shared (S1): an envelope OUTSIDE the tables keeps the old window — only "
            "rm/mv fall back to substring semantics there, git is not read", motive=MOTIVE_GITWIPE,
        ))
    for label, command, motive in (
        ("xargs-restore", "xargs -n 1 git restore .", MOTIVE_GITWIPE),
        ("xargs-branch", "git branch --list 'wt/*' | xargs git branch -D", MOTIVE_BRANCH),
    ):
        rows.append(row(
            f"gitenv/{label}", "safe_bash", command, DENY,
            "T-01M5D6XS2S / T-01M5D6XV3J: `xargs` at the HEAD of the command is read on all three, and a "
            "branch name it feeds counts as `wt/` (S-00003933 point 3, reserve 6 of S-00003937: a KNOWN GAP "
            "until then); behind an envelope outside the tables (`timeout 5 xargs git branch -D`) it stays "
            "unread, NAMED in the refusal",
            motive=motive,
        ))
    for head in ("xargs", "nice", "exec", "watch", "parallel", "setsid", "stdbuf", "ionice", "eval"):
        rows.append(row(
            f"gitenv/kept-chain-{head}", "safe_bash", f"{head} sudo git mv a b", DENY,
            "T-00001102: ONE envelope outside the tables breaks the proof for the whole chain — the "
            "window keeps its old reading (rm/mv refused anywhere), however proven the rest looks",
        ))
    rows.append(row(
        "gitenv/known-relaxation-xargs-braces", "safe_bash", "xargs -I{} sudo git mv {} b", ALLOW,
        "KNOWN RELAXATION, shared: `{}` is a separator for all three readers, so the chain is cut "
        "before `sudo` and `sudo git mv` reads as a proven segment (a git mv: harmless, out of scope "
        "like the bare form)",
    ))
    rows.append(row(
        "gitenv/known-gap-env-v-probe", "safe_bash", "env -v rm -rf src/x", ALLOW,
        "KNOWN GAP, shared (S5): the walk reads `-v` after an envelope as the `command -v` "
        "presence probe, and `env -v` is GNU env's verbose flag that RUNS the command",
    ))
    for envelope, (plain, valued) in ENVELOPE_TABLES.items():
        for option in valued.split():
            rows.append(row(
                f"gitenv/option-valued/{envelope}{option}", "safe_bash", f"{envelope} {option} git rm -rf src/x", DENY,
                "T-00001102: an option declared WITH a value consumes the next word — `git` here is "
                "that value, so rm is still the command and still refused; a table that declared "
                "it valueless would close the window on the value",
            ))
        rows.append(row(
            f"gitenv/options-plain/{envelope}", "safe_bash", f"{envelope} {plain} git mv a.txt b.txt", ALLOW,
            "T-00001102: EVERY option declared WITHOUT a value, chained, leaves git as the command "
            "(one option dropped from a table makes the chain ambiguous: the row turns red)",
        ))
    for label, command in (
        ("D", "git branch -D wt/T-00001090"),
        ("d-f", "git branch -d -f wt/T-1"),
        ("df", "git branch -df wt/T-1"),
        ("fd", "git branch -fd wt/T-1"),
        ("delete-force", "git branch --delete --force wt/T-1"),
        ("abbreviated", "git branch --del --forc wt/T-1"),
        ("f-delete", "git branch -f --delete wt/T-1"),
        ("option-after-operand", "git branch wt/T-1 -D"),
        ("double-dash", "git branch -D -- wt/T-1"),
        ("uppercase", "git branch -D WT/T-1"),
        ("single-quoted", "git branch -D 'wt/T-1'"),
        ("cluster", "git branch -Dq wt/T-1"),
        ("many-operands", "git branch -D main wt/T-1"),
        ("at-brace", "git branch -D @{-1}"),
        ("at-upstream", "git branch -D @{upstream}"),
        ("at-brace-escaped", "git branch -D @\\{-1}"),
        ("at-brace-quoted", 'git branch -D "@{-1}"'),
        ("brace-expansion", "git branch -D {wt/T-1,x}"),
        ("brace-infix", "git branch -D w{t,x}/T-1"),
        ("quoted-expansion", 'git branch -D "$b"'),
        ("expansion", "git branch -D $b"),
        ("git-C", "git -C /x branch -D wt/T-1"),
        ("env-u", "env -u GIT_DIR git branch -D wt/T-1"),
        ("backslash", "git branch -D wt\\/T-1"),
        ("quoted-prefix", 'git branch -D "wt"/T-1'),
        ("quote-in-the-middle", 'git branch -D w"t"/T-1'),
        ("quote-at-the-end", "git branch -D wt/'T-1'"),
        ("double-quoted", 'git branch -D "wt/T-1"'),
        ("sudo-expansion-envelope", "sudo -u $U git branch -D wt/T-1"),
        ("two-operands", "git branch -D wt/T-1 wt/T-2 && git status"),
        ("no-force-then-force", "git branch --delete --no-force --force wt/T-1"),
        ("d-abbreviated", "git branch --d --force wt/T-1"),
        ("substitution", "git branch -D $(cat f)"),
        ("backtick", "git branch -D `cat f`"),
        ("substitution-list", "git branch -D $(git branch --list 'wt/*')"),
        ("param-expansion-then-option", "git branch ${x} -D feat"),
    ):
        rows.append(row(
            f"branch/{label}", "safe_bash", command, DENY,
            "T-00001090: a forced delete of a `wt/` branch destroys the commits only that branch "
            "carries (the unmerged work of a worktree dev); every spelling git itself accepts, and "
            "a name read from a substitution counts as `wt/` (reserve 1 of S-00003937), and so does "
            "`@{…}`, which git resolves (`@{-1}`: the previous branch, measured) and forbids in a ref name, "
            "and a brace list read expanded (`{wt/x,y}`, `w{t,x}/T-1`: the `wt/` name is among the expanded words; "
            "T-01M5F4GJZD — no longer the cut of the list as written)",
            motive=MOTIVE_BRANCH,
        ))
    rows.append(row(
        "branch/false-positive-remotes", "safe_bash", "git branch -D -r wt/T-1", DENY,
        "ACCEPTED FALSE POSITIVE, fail-closed, NAMED in the refusal: `-r` deletes a remote-tracking "
        "ref only, but `-r` can be the value of another option (`git branch -D --sort -r x` deleted "
        "the LOCAL branch, measured on git 2.55), so the guard does not honour it", motive=MOTIVE_BRANCH,
    ))
    # The motive is the phrase of the clause that names each false positive, never MOTIVE_BRANCH alone:
    # these commands were already refused before the clause existed, so only its phrase can turn red.
    # Pass quater (L-00000187): the clause describes the MECHANISM, one fragment per claim it makes.
    for label, command, motive in (
        ("brace-word", "git branch -D feat }", "stops reading a `git` command at its first `{` or `}` outside quotes"),
        ("brace-comment", "git branch -D feat-old # cleanup {x}", "one in a comment or a redirect target counts"),
        ("brace-escaped", "git branch -D feat\\{x\\}", "a backslash does not protect it"),
        ("brace-redirect-target", "git branch -D feat >{x}", "one in a comment or a redirect target counts"),
        ("brace-d-f-before-cut", "git branch -d -f feat {x}",
         "If a forced delete (`-D`, or `-d`/`--delete` with `-f`/`--force`) was read before that point"),
    ):
        rows.append(row(
            f"branch/false-positive-{label}", "safe_bash", command, DENY,
            "ACCEPTED FALSE POSITIVE, fail-closed, NAMED in the refusal: the walk cuts the words at the "
            "first `{`/`}` outside quotes (a backslash, a comment or a redirect target does not shield "
            "it) and counts the cut as `wt/` once the forced delete was read (a brace that is no list nor "
            "sequence: bash keeps it in the word, and the name past it is not read; a brace LIST is read "
            "expanded instead, T-01M5F4GJZD), so a non-wt name, a stray `}` word or a comment holding a brace is refused",
            motive=motive,
        ))
    # DIVERGENCE 11, narrowed by T-01M5F4GJZD: a brace list is read EXPANDED on the three hosts, its cut as written
    # no longer counts as `wt/` on the python hosts when the RAW segment, quotes included, holds only characters of the
    # closed set `_REREAD_SAFE` (letters, digits, blanks, quotes, `{ } , . _ - / @ : = + % # < > &`).
    for label, command in (
        ("brace-list-nonwt", "git branch -D {feat-a,feat-b}"),
        ("brace-list-empty-alternative", "git branch -D x{,}"),
        ("brace-sequence-nonwt", "git branch -D feat{1..3}"),
        ("brace-list-redirect-nonwt", "git branch -D {a,b} 2>/dev/null"),
        ("brace-list-comment-nonwt", "git branch -D {a,b} # done"),
    ):
        rows.append(row(
            f"branch/{label}", "safe_bash", command, ALLOW,
            "T-01M5F4GJZD (DIVERGENCE 11 narrowed): bash deletes non-wt names only; the three hosts read the "
            "expanded words and pass — the python hosts refused the list as written until then (PY_STRICTER)",
        ))
    for label, command, motive in (
        ("brace-list-then-cut", "git branch -D {feat-a,feat-b} }", "a fail-closed false positive for a non-wt name"),
        ("brace-list-wt-suffix", "git branch -D wt/{a,b}", MOTIVE_BRANCH),
        ("brace-list-then-at", "git branch -D {a,b} @{-1}", MOTIVE_BRANCH),
        ("brace-list-other-cmd", "echo {a,b}; git branch -D feat }", MOTIVE_BRANCH),
        ("brace-list-split-quoted-backslash-newline", 'git branch -D {a,b} w"\\\n"t/x', MOTIVE_BRANCH),
    ):
        rows.append(row(
            f"branch/{label}", "safe_bash", command, DENY,
            "T-01M5F4GJZD: the list is read expanded, and the expanded words still hold what stops the walk "
            "(a `}` or `@{…}`, a brace that is no list nor sequence) or a `wt/` name: refused on the three hosts — "
            "a mutant that drops the cut in the second pass, or keeps `reread` past the first, passes these",
            motive=motive,
        ))
    for label, command, why in (
        ("brace-list-backslash-newline", "git branch -D {a,b} \\\nwt/x", "rightly: bash deletes `wt/x` (T-00001198)"),
        ("brace-list-escaped-sep", "git branch -D {a,b} \\; wt/x",
         "rightly: bash deletes `wt/x` (T-01M5G0VHWS9ATWXEXJJGZ9Q8QB)"),
        ("brace-list-glob", "git branch -D {a,b} w?/x", "rightly: the glob may name `wt/x` (T-01M5G0VHWS9ATWXEXJJGZ9Q8QB)"),
        ("brace-list-procsub", "git branch -D {a,b} <(echo) wt/x",
         "rightly: the walk stops at `<(` where bash goes on and deletes `wt/x` (T-01M5G5MTC22R0E3BBBG10KTAT0)"),
        ("brace-list-procsub-out", "git branch -D {a,b} >(cat) wt/x",
         "rightly: the walk stops at `>(` where bash goes on and deletes `wt/x` (T-01M5G5MTC22R0E3BBBG10KTAT0)"),
        ("brace-list-procsub-at", "git branch -D {a,b} <(echo) @{-1}",
         "rightly: bash deletes the previous branch (T-01M5G5MTC22R0E3BBBG10KTAT0)"),
        ("brace-list-quoted-backslash-newline", 'git branch -D {a,b} "w\\\nt/x"',
         "rightly: bash removes the backslash-newline inside the quotes and deletes `wt/x`, shlex does not (T-00001198)"),
        ("brace-list-subshell", "(git branch -D {a,b})",
         "a fail-closed false positive, NAMED: `(` is outside the set, bash deletes `a` and `b` only"),
    ):
        rows.append(row(
            f"branch/{label}", "safe_bash", command, DENY,
            "DIVERGENCE 11, what remains (T-01M5F4GJZD): a character outside the closed set `_REREAD_SAFE` in the RAW "
            "segment, inside quotes too, may stop or split the expanded words where bash goes on (a CR is excluded "
            "too, fail-closed: not read as bash reads it), so the python hosts keep counting the cut of the list as "
            f"`wt/` and refuse — {why}; Claude refuses too since T-01M5GFV9CE21H6BR56NMN8T0AP. Other fail-closed false positives on non-wt names, NAMED: "
            "`git branch -D {fix-1,fix-2} > /tmp/x\\ y`, `git branch -D {a,b} x[1]`, `{a,b} ~x`, `{a,b} \"w<CR>t/x\"`",
            motive="a character outside a closed set",
        ))
    rows.append(row(
        "branch/brace-sequence-crosses-nonletter", "safe_bash", "git branch -D {V..a..6}wt/x", DENY,
        "DIVERGENCE 11, what remains (T-01M5F4GJZD, NO_GO S-01M5GFV8SH): bash 5 expands the letter sequence through "
        "`[ \\ ] ^ _` and the backtick and re-reads what it emits (`\\wt/x` is `wt/x`): it deletes `wt/x`. The guard's "
        "expansion writes `_` there, so it is not EXACT, and the python hosts keep counting the cut of the list as "
        "`wt/` and refuse, rightly; Claude refuses too, its sequence not expanded as bash does (T-01M5GFV9CE21H6BR56NMN8T0AP). "
        "bash 3.2 does not expand a sequence with a step: the name stays as written, no `wt/`",
        motive={"claude": "a sequence the guard does not expand as bash does", "codex": "reproduces bash's exactly", "gemini": "reproduces bash's exactly"},
    ))
    rows.append(row(
        "branch/brace-list-quoted-tab", "safe_bash", 'git branch -D {a,b} "w\tt/x"',
        {"claude": True, "codex": False, "gemini": False},
        "DIVERGENCE 11, the other side, CLAUDE STRICTER (T-01M5GFV9CE21H6BR56NMN8T0AP x T-01M5F4GJZD): a TAB inside quotes is in `_REREAD_SAFE`, "
        "so the python hosts read the expanded words and pass (bash names `a`, `b` and `w<TAB>t/x`, no `wt/`), "
        "while safe-bash.sh refuses a quoted span that is not plain quotes on one line: a fail-closed false "
        "positive, named in its refusal",
        motive="a character outside a closed set",
    ))
    rows.append(row(
        "branch/named-gap-brace-phrase", "safe_bash", "git branch -D wt/T-1", DENY,
        "T-00001196, the other side of the cut: the refusal says that a brace read BEFORE the forced "
        "delete leaves the command unread — this pins that sentence, which only "
        "`named-gap/brace-after-operand-branch` still measures (the brace LISTS are read since T-01M5D6XS2S "
        "/ T-01M5D6XV3J: `brace/*`); the motive is absent from every message before the pass quater",
        motive="passes unread",
    ))
    rows.append(row(
        "branch/divergence-glued-quoted-nonwt", "safe_bash", 'git branch -D feat-"old"',
        {"claude": True, "codex": False, "gemini": False},
        "DIVERGENCE 10: the awk cannot read a word glued to a quoted span whole (`bglue`) and counts it "
        "as `wt/` — fail-closed, NAMED in the refusal as Claude-only; the python hosts read `feat-old` "
        "through its quotes and let the non-wt name pass",
        motive="glued to a quoted span",
    ))
    # Pass sexies of batch 2 (TEXT ONLY: no decision moves, the corrections are T-00001202's): one row per new
    # sentence of the branch refusal, its motive ABSENT from every message at c9512cfc, so the row can turn red.
    for label, motive in (
        ("unescaped-newline", "an unescaped newline"),
        ("backslash-newline", "a backslash-newline is NOT joined"),
        ("backslash-newline-carrier", "gap carried by T-00001198"),
        ("comment-option", "a `-D` read in a trailing comment"),
        ("dollar-or-backtick", "holds a `$` or a backtick, even one bash does not expand"),
        ("param-first-brace", "ends at its first `}`: `${x:-{y}}` cuts there"),
        ("option-reading", "The delete option is not read as bash reads it"),
        ("option-reading-carrier", "gap carried by T-00001202"),
        ("literal-at-at", "once the command holds a literal `@@` anywhere"),
        ("literal-at-at-option", "even with a literal `@@` in the command"),
        ("glued-after-quoted-expansion", "on the Codex and Gemini hosts only"),
    ):
        rows.append(row(
            f"branch/phrase-{label}", "safe_bash", "git branch -D wt/T-1", DENY,
            "T-00001090, pass sexies: the refusal names this bound in this sentence, measured on the three hosts "
            "at c9512cfc; the motive is absent from every message before it, so the row turns red if it is dropped",
            motive=motive,
        ))
    # The refused forms those sentences name, as measured at c9512cfc (decisions unchanged).
    for label, command, motive in (
        ("comment-option", "git branch wt/x # -D", "a `-D` read in a trailing comment"),
        ("dollar-single-quoted", "git branch -D '$b'", "holds a `$` or a backtick"),
        ("dollar-escaped", "git branch -D \\$b", "holds a `$` or a backtick"),
        ("dollar-in-comment", "git branch -D feat # $HOME", "holds a `$` or a backtick"),
        ("backtick-single-quoted", "git branch -D 'a`b'", "holds a `$` or a backtick"),
    ):
        rows.append(row(
            f"branch/false-positive-{label}", "safe_bash", command, DENY,
            "ACCEPTED FALSE POSITIVE, fail-closed, NAMED in the refusal (pass sexies): the walk hands a comment's "
            "words over like the others, and a non-option word holding a `$` or a backtick counts as `wt/` "
            "whether bash expands it or not", motive=motive,
        ))
    for label, command in (
        ("literal-at-at-word", "git branch -D feat # @@"),
        ("literal-at-at-quoted", "echo @@; git branch -D 'feat'"),
    ):
        rows.append(row(
            f"branch/divergence-{label}", "safe_bash", command, {"claude": True, "codex": False, "gemini": False},
            "DIVERGENCE 10: a literal `@@` is the awk's own mark for a quoted span; once the raw command holds one, "
            "the awk drops the quoted spans (`qv`) and counts every quoted word after `branch`, and a `@@` among "
            "those words, as `wt/` — fail-closed, NAMED in the refusal as Claude-only; the python hosts pass the name",
            motive="once the command holds a literal `@@` anywhere",
        ))
    rows.append(row(
        "branch/divergence-glued-after-quoted-expansion", "safe_bash", 'git branch "$b"-D wt/T-1',
        {"claude": True, "codex": False, "gemini": False},
        "DIVERGENCE 10: the awk reads the `-D` glued after the quoted span as an option (and counts the glued span "
        "as `wt/`); the python hosts read the word `$b-D` through its quotes, not as an option, and let it pass — "
        "bash runs `git branch -D wt/T-1` when `$b` is empty: a gap there, carried by T-00001202, NAMED",
        motive="on the Codex and Gemini hosts only",
    ))
    for label, command in (
        ("d-merged", "git branch -d wt/T-1"),
        ("D-agent-branch", "git branch -D worktree-agent-abc"),
        ("D-other", "git branch -D other"),
        ("list", "git branch --list 'wt/*'"),
        ("delete-for", "git branch --delete --for wt/x"),
        ("d-then-list", "git branch -d wt/T-1 && git branch -a"),
        ("bare", "git branch"),
        ("verbose", "git branch -vv"),
        ("rename", "git branch -m wt/old wt/new"),
        ("create", "git branch wt/T-9"),
        ("quoted-mention", 'git commit -m "git branch -D wt/x"'),
        ("D-nested-prefix", "git branch -D foo/wt/x"),
        ("d-remote", "git branch -d -r origin/wt/x"),
        ("d-substitution", "git branch -d $(cat f)"),
        ("d-at-brace", "git branch -d @{-1}"),
        ("d-stash-at", "git branch -d stash@{0}"),
        ("stash-drop-at", "git stash drop stash@{0}"),
        ("show-at", "git show HEAD@{1}"),
        ("restore-source-at", "git restore --source=HEAD@{1} src/x"),
        ("brace-quoted", 'git branch -D "feat{x}"'),
        ("brace-next-command", "git branch -D feat && echo {x}"),
        ("brace-after-subshell", "(git branch -D feat)>{x}"),
        ("brace-after-param-expansion", "git branch ${x}{y} -D feat"),
        ("brace-half-before-cut", "git branch -d feat {--force,}"),
    ):
        rows.append(row(
            f"branch/allow-{label}", "safe_bash", command, ALLOW,
            "T-00001090: only a forced delete of a `wt/` branch is refused — `-d` (git refuses an "
            "unmerged branch itself), other branches, listing, renaming and creating pass",
            motive=MOTIVE_BRANCH,
        ))
    rows.append(row(
        "branch/known-gap-substitution-then-option", "safe_bash", "git branch $(cat f) -D", ALLOW,
        "KNOWN GAP, shared, NAMED in the refusal message (reserve 1 of S-00003937): the words git "
        "is judged on stop at a substitution, so a `-D` written AFTER it is never read",
        motive=MOTIVE_BRANCH,
    ))
    for label, command, motive in (
        ("checkout-B", "git checkout -B wt/T-1 main", MOTIVE_BRANCH),
        ("switch-C", "git switch -C wt/T-1 main", MOTIVE_BRANCH),
        ("env-S-quoted-branch", "env -S 'git branch -D wt/T-1'", MOTIVE_BRANCH),
        ("env-v-branch", "env -v git branch -D wt/T-1", MOTIVE_BRANCH),
        ("nice-branch", "nice -n 5 git branch -D wt/T-1", MOTIVE_BRANCH),
        ("bash-c-branch", 'bash -c "git branch -D wt/T-1"', MOTIVE_BRANCH),
        ("brace-after-operand-branch", "git branch wt/T-1 {x} -D", MOTIVE_BRANCH),
        ("env-S-quoted-wipe", "env -S 'git reset --hard'", MOTIVE_GITWIPE),
        ("env-v-wipe", "env -v git reset --hard", MOTIVE_GITWIPE),
        ("bash-c-wipe", 'bash -c "git reset --hard"', MOTIVE_GITWIPE),
        ("brace-cut-restore-source", "git restore --source=HEAD@{1} .", MOTIVE_GITWIPE),
    ):
        rows.append(row(
            f"named-gap/{label}", "safe_bash", command, ALLOW,
            "KNOWN GAP, shared, NAMED in the refusal message (binôme of batch 2, T-00001090) — bounded, "
            "not closed: this row turns red the day the form is read, and the message must then drop it",
            motive=motive,
        ))
    for label, command, motive in (
        ("option-branch", "git branch {-D,} wt/T-1", MOTIVE_BRANCH),
        ("subcommand-branch", "git {branch,-D} wt/T-1", MOTIVE_BRANCH),
        ("glued-option-branch", "git branch -{D,} wt/T-1", MOTIVE_BRANCH),
        ("before-option-branch", "git branch {x,} -D wt/T-1", MOTIVE_BRANCH),
        ("subcommand-wipe", "git {reset,--hard}", MOTIVE_GITWIPE),
        ("option-wipe", "git reset {--hard,}", MOTIVE_GITWIPE),
        ("pathspec-wipe", "git restore {.,}", MOTIVE_GITWIPE),
    ):
        rows.append(row(
            f"brace/{label}", "safe_bash", command, DENY,
            "T-01M5D6XS2S / T-01M5D6XV3J: the brace list is expanded as bash expands it and the expanded "
            "words are read in a second pass on all three hosts — a KNOWN GAP of batch 2 (T-00001090, "
            "T-00001196) until then, so the refusal no longer names it", motive=motive,
        ))
    rows.append(row(
        "branch/dollar-quote-option", "safe_bash", "git branch $'-D' wt/T-1", DENY,
        "T-01M5D6XS2S / T-01M5D6XV3J: an option in ANSI-C quotes is read on all three hosts — a KNOWN GAP "
        "of the pass sexies (T-00001202) until then", motive=MOTIVE_BRANCH,
    ))
    # Pass sexies: the forms of the gaps the refusal now names, expected AS MEASURED at c9512cfc (bash deletes the
    # `wt/` branch in each); each row turns red the day its carrier reads the form.
    for label, command in (
        ("backslash-newline-operand", "git branch -D \\\nwt/T-1"),
        ("backslash-newline-brace", "git branch -D feat \\\n{wt/x,y}"),
        ("param-first-brace-option", "git branch ${x:-{y}} -D wt/T-1"),
        ("expansion-glued-option", "git branch $b-D wt/T-1"),
        ("braced-expansion-glued-option", "git branch ${b}-D wt/T-1"),
        ("sort-takes-double-dash", "git branch --sort -- -D wt/T-1"),
        ("format-takes-double-dash", "git branch --format -- -D wt/T-1"),
    ):
        rows.append(row(
            f"named-gap/{label}", "safe_bash", command, ALLOW,
            "KNOWN GAP, shared, NAMED in the refusal (pass sexies of batch 2; T-00001198 for a backslash-newline, "
            "T-00001196 for a `${…}` cut at its first `}`, T-00001202 for the option) — bounded, not closed: this "
            "row turns red the day the form is read, and the message must then drop it", motive=MOTIVE_BRANCH,
        ))
    for label, command in (
        ("quoted-option", "git branch '-D' wt/T-1"),
        ("quoted-option-literal-at-at", "git branch '-D' wt/T-1 # @@"),
        ("glued-quoted-option", 'git branch -"D" wt/T-1'),
        ("quoted-force", "git branch -d '-f' wt/T-1"),
        ("backslashed-option", "git branch \\-D wt/T-1"),
    ):
        rows.append(row(
            f"named-gap/{label}", "safe_bash", command, PY_STRICTER,
            "DIVERGENCE 7 on `git branch`: the python hosts read the option through its quotes or its backslash and "
            "refuse; Claude's scrub turns it into `@@` (or keeps the backslash) and lets bash delete the `wt/` "
            "branch — a gap on the Claude host only, carried by T-00001202, NAMED in the refusal", motive=MOTIVE_BRANCH,
        ))
    # The envelopes T-01M5D6XS2S / T-01M5D6XV3J added (chrt, taskset, builtin; timeout), one row per OTHER table of
    # safe-bash.sh than the awk's, which `envelope/*` pins: the brace pass (`ENVS`) and the rm/mv operand pass (`ENVELOPES`).
    for envelope in ("chrt", "taskset", "builtin", "timeout"):
        rows.append(row(
            f"envtable/brace-command-word-{envelope}", "safe_bash", f"{envelope} {{r{{m..m}},-rf,{{1..300}}}} src", DENY,
            "T-01M5D6XS2S / T-01M5D6XV3J: the brace pass skips the envelope before the command word, so a brace in "
            "that word past the bound is refused on its own rule; an envelope dropped from that table makes it the "
            "command word and the form passes", motive="the brace stands in or before its command word",
        ))
        rows.append(row(
            f"envtable/tmp-operand-{envelope}", "safe_bash", f"{envelope} rm -rf /tmp/x", PY_STRICTER,
            "DIVERGENCE 4 behind an envelope: Claude's operand pass skips the envelope and judges `/tmp/x` against its "
            "anchored list (allowed); the python hosts' prefix list refuses it; an envelope dropped from Claude's table "
            "leaves the operand unjudged and the rm refused",
        ))
    return rows
