# Security Scan Setup — prerequisites per ecosystem

What the kit's dependency scans (`/audit`, the SCA hooks, `sca-watch.sh`) need
on your machine or CI to produce **real, up-to-date findings** — and what you
see when something is missing. TL;DR: **npm works out of the box; Java and
Swift need an NVD API key (free) or a pre-seeded NVD database.**

## Secrets scan (gitleaks) — the class-0 gate

Separate from the dependency scans above: `.agents/security/gitleaks-scan.sh`
is the **class-0 secrets gate** (see AGENTS.md § Security gate). It runs on
Edit/Write content (`--content`, catching a secret before it hits disk) and, at
Stop, on the working-tree diff AND the index (what `git commit` takes). A real,
live credential is **non-waivable** and
**blocks** (exit 2); every scan runs `gitleaks --redact`, so a secret value is
never printed and never lands in `.agents/state/local/sca-reports/audit-log.jsonl` (only counts +
`file:line`).

**Who calls it.** Claude Code (`.claude/settings.json`: the `Stop` hook, default
form, and the `PreToolUse` `Edit|Write` hook, `--content`); the
Gemini/Antigravity registrations (`.agents/hooks.json`, both forms); the Codex,
Copilot and Kimi hook registrations (`.codex/hooks.json`,
`.github/hooks/agent-guardrails.json`, `.kimi-code/hooks.json` — both forms);
and `.agents/bin/mcp_render.py`
(`--content`). **Neither `core-scripts/verify.sh` nor the pre-push hook runs
it** — on those paths, secrets are not gated by this script. Every Stop rescans
the working-tree diff; there is no verdict cache on this class-0 gate.

**In an adopting project, `verify.sh` gates secrets through ANOTHER path**
(ADOPTANT iff `.agents/IS_THE_KIT` is absent AND
`.agents/security/module_discovery.py` is present). Its single step,
`.agents/bin/porte_adoptant.py` — also the CI's `adoptant` job — calls the
`gitleaks` BINARY, not this script: `gitleaks dir <dir> --redact --no-banner
--exit-code 7` on the root and on each populated submodule, with that
directory's `.gitleaks.toml`, else the root's, else no `--config`; then
`semgrep --config .agents/security/semgrep.yml --error --baseline-commit <base>`
on the same directories. **For semgrep, only what is NEW blocks.** The root's `<base>` is IMPOSED through
`CADRE_SEMGREP_BASE` when the caller knows it — `verify.sh --at` computes it on
the LIVE tree (never in its frozen clone, whose `origin/HEAD` named the live
tree's checked-out branch: measured, only `HEAD^1` was judged), the CI
`adoptant` job passes the PR's base, or `github.event.before` on a push (every
pushed commit judged) — and taken only if it is 40 hex AND an ancestor of HEAD;
otherwise (a branch creation's `0000…0`, a force-push, a malformed value) the
gate falls back, and says so. Without an imposed base, `<base>` is
`git merge-base HEAD <default branch>` — `origin/HEAD` resolved, then
`origin/main`, `origin/master`, then the local `main`, `master`; HEAD ON or
BEHIND the default branch gives `HEAD^1` (only the last commit is judged). A
submodule's base is its gitlink at its parent's base. **Bound, named, not fixed:** a submodule ADDED by the judged change has
no gitlink at that base, so the gate falls back on the submodule's own
merge-base with its default branch — most often `HEAD^1` — and a finding in its
commits BEFORE the last one passes, although the whole module is new (measured:
the base was commit 1 of 2, the one carrying the pattern). No computable base gives
a FULL scan, and the gate says so. The pre-existing findings are the project's
debt, fixed in a task of their own; an untracked file is not seen under a
baseline (measured on semgrep 1.175.0). gitleaks still reads the whole tree.
**A finding is RED, and no derogation covers it.** **A file whose partial
reading semgrep REPORTS is a refusal, not a clean**: the gate reads semgrep's
JSON report, and any `errors` entry — `PartialParsing` included, which semgrep
reports at rc 0 (measured: a heredoc in an `if` condition hid an `eval`) — is
`COVERAGE DEGRADED — semgrep n'a pas lu en entier N fichier(s) : …`. What
semgrep recovers WITHOUT reporting it passes: measured on semgrep 1.175.0, a
JavaScript file holding only `function (` or `const y = ;` gives `errors: []`,
scanned, rc 0 — the gate only knows what semgrep says. That
refusal, a missing report, an absent or erroring scanner (semgrep rc 2 on an
unreadable base included), an absent `semgrep.yml`, or a failed git enumeration
of the tracked files under `.agents/vendor/` (`COVERAGE DEGRADED — semgrep :
fichiers suivis sous .agents/vendor/ non énumérés`; semgrep still runs on
`-- .` alone), is RED unless
`CADRE_GARDES_DEGRADEES="<why>"` is set; that reason is traced into the stamp
and printed by the pre-push hook.
**The bound, printed at the end of every run:** out of scope by default, AT
LEAST — gitleaks `node_modules/`, `venv/lib/` and its default allowlist, `dir`
mode (the working tree, not the history); semgrep `node_modules/`, `vendor/`,
`tests/`, `build/`, `dist/` (default `.semgrepignore`) EXCEPT `.agents/vendor/`,
whose every tracked file present on disk is scanned whole, `tests/` included
(explicit target; symlinks and untracked files are not targeted; the argv is
bounded by the OS, the target count is printed), and, under
`--baseline-commit`, everything that is not NEW since the base (what already
existed, untracked files); the list is not closed.
The same step builds and tests the project: a tracked `scripts/verify-projet.sh`
at the root is the PROJECT'S OWN SCRIPT — it decides for the WHOLE repository:
the gate runs it (`bash scripts/verify-projet.sh`, cwd the root,
the gate's environment with `GIT_*` removed) and its rc decides, 0 being green;
no default sequence runs for any module, and the guards above still run and
block. A script that calls the gate back is RED, named (reentrance guard
`PORTE_ADOPTANT_EN_COURS`), never a loop. Untracked, it is set aside and named.
Without a script and without any module of a known family (npm, python, java,
swift), the gate does not block: the guards alone judge, and it warns,
`build et tests non vérifiés par le kit : ajoutez scripts/verify-projet.sh` —
a warning carried into the stamp and printed by the pre-push hook at the push.
**A MIXED repository is warned too**: without a tracked
script, a TRACKED manifest of an ecosystem outside the table — a closed list:
`composer.json`, `go.mod`, `Gemfile`, `Cargo.toml`, `mix.exs`, `*.csproj`,
`*.sln`, `build.sbt`, found by `git ls-files` at the root and in each populated
submodule, outside the directories the discovery prunes (`node_modules`,
`.agents`, `build`, `dist`, `target`…) — is NAMED in the same warning, even when
known families run (`manifeste(s) hors table (composer.json) : build et tests de
cette partie non vérifiés par le kit : ajoutez scripts/verify-projet.sh`; ten
names at most, the rest counted); with no known module either, both messages
make ONE value, on one line. Information only: no rc changes. Not seen: an
ecosystem missing from that list, and an untracked manifest.

**"gitleaks returned 1" is never read as clean.** gitleaks exits 1
when it found leaks, so an exit 1 must come with at least one finding the gate
can read. When it does not — no report (the scan subshell died before
gitleaks: an empty `--config` array under macOS's bash 3.2 + `set -u` did
exactly that, and read `clean` on a real secret), or a **truncated/unreadable**
report with no readable finding in it — the gate prints
`COVERAGE DEGRADED: gitleaks returned 1 but no finding could be read …`, audits
`DEGRADED`, emits `scan.secrets` `status=degraded`, and exits 0 (never a false
block, never a false `clean`). A truncated report that still carries a readable
finding (a `"StartLine"` in its text) **BLOCKS** (exit 2), with or without
Python: both paths count the findings still readable; one with no readable
finding is DEGRADED, never clean.

**The gate reads what git will commit, and never calls clean a perimeter it
knows it did not read.**
`git commit` takes the INDEX, not the working tree. Measured before the fix: a
key `git add`ed, then the file rewritten benign — or made unreadable (`chmod
000`) — read `clean.`, rc 0, and the commit carried the key; an unreadable file
of the diff read `nothing to scan`; an initialized submodule whose directory
cannot be searched read `not initialized`, its committed key `clean.`. The
default form now reads TWO perimeters in ONE gitleaks spawn: the dirty working
tree (changed + untracked, as before, plus the entries flagged
`assume-unchanged`, whose tree copy git never compares) and every index entry
that differs from HEAD (`git diff-index --cached`, or against the empty tree
before the first commit) — at the root, in each reachable submodule, plus a
submodule's tracked files it could not read in the tree, plus the whole index
of an initialized but unreachable submodule, read through its git dir. A
location read from the index reads `index:<path>:<line>`; a file identical in
the tree and in the index counts TWICE (`k.txt:1` and `index:k.txt:1`, same
verdict). Index blobs are read RAW, by `git cat-file` — never `checkout-index`,
whose smudge/LFS filters ran even under `--attr-source` (measured with a filter
declared in `$GIT_DIR/info/attributes` or `core.attributesFile`): the index
read runs no filter of the repository, whatever attributes file declares it
(the census's `git diff` no longer runs one either; see the census paragraph below). A
symlink's index blob (mode 120000) is its TARGET TEXT, scanned as such; nothing
is ever followed. They are written into a FRESH directory under the stage
(`mktemp -d`, files created `O_EXCL|O_NOFOLLOW`), and the per-file copy that
follows a failed `tar` starts in a fresh stage and never copies a link —
measured before: a link extracted by the failed `tar`, then `cp` of the same
path, wrote OUTSIDE the stage into an existing file (CWE-59, pre-existing,
closed here). Every git call that reads the repository — the census included —
runs with `-c core.fsmonitor=false -c
core.hooksPath=/dev/null` (measured: a repository's `core.fsmonitor` command is
run by `diff`, `diff-index`, `ls-files -s`, `ls-files -v` and `ls-files
--others` alike); a submodule name
read in `.gitmodules` is refused when it is absolute, carries a `..` component,
or resolves outside the parent's `modules/`.

**What it cannot read is COUNTED and DEGRADES — rc 0, said, never `clean`**
(gitleaks AND semgrep: degrade, never block): a file of the diff that cannot be copied; a listed path under a
directory that cannot be searched; the warning line(s) `git ls-files --others`
prints for a directory it cannot open (its untracked files were never listed);
the working tree of an unreachable submodule (its index IS read); an index
entry that could not be written or read (`cat-file` failed or timed out under
`GITLEAKS_TIMEOUT`); a 040000 entry (a sparse index that was not expanded). Each
loss prints ONE `COVERAGE DEGRADED: <count> <cause> — not scanned; perimeter
INCOMPLETE` line — a COUNT, never a path — and the verdict sink then names it
instead of `clean.` (`fallback scan: DEGRADED (…)` under the fallback, which
a consumer reads as NOT complete). At the Stop it reaches the model as the
`"systemMessage"` (measured on Claude Code; not measured elsewhere). Two cases
stay blind on content that MAY already be committed, and say so with
`content may already be committed`: an unreachable submodule whose git dir is
unreadable, absent (a `.git` DIRECTORY inside the submodule, never absorbed,
sits under the unreadable directory) or behind an unsafe name; and the
submodules NESTED under an unreachable submodule (counted, not descended).
Remedies: repair the permissions, or ignore the DIRECTORY (`vol/`, not
`vol/*` — the latter brings the warning back). The precedent this differs from
is an agent-writable allowlist switching class-0 off, which was refused as a
DEGRADED rc 0: here everything git can commit is read, and what is
degraded is not committable as it stands (`git add` / `commit -a` refuse an
unreadable file). Switching to a block is one line — `exit 2` at the
`CENSUS_OK` sink — a pilot decision.

**Bounds, measured or named, not closed.** A commit made in the SAME Bash call
as the edit escapes the Stop. **LFS:** the index holds the POINTER only; the
real content (`.git/lfs/objects`, pushed separately) is never read, and an LFS
file in the tree is read only when it is dirty. `skip-worktree` entries are not
added (the normal state of every sparse checkout: noise at each Stop; `git add`
refuses them). A conflict is read in the tree (the markers), never its index
stages 1-3 (content already committed on the merged branches). `assume-unchanged`
is read at the root only; the warnings of `ls-files --others` are read at the
root only, not inside submodules. Without python the index is read one `git
cat-file blob` per entry (≈ 19 ms each measured bare, plus the `timeout(1)`
wrapper), each under `timeout(1)` with the time left — without `timeout(1)`
either, the read is SAID unbounded.

**The census reads NUL-separated names, sorts them in bytes, and runs no code
of the repository it MEASURED.** Measured before: a path git QUOTES (non-ASCII
bytes, a quote, a backslash, a control character — `"n\303\251.txt"`) failed
the existence test and was dropped as if absent — a key in an untracked,
modified or assume-unchanged `né.txt` read `nothing to scan`, rc 0; and the
census's own `git diff` ran the repository's `core.fsmonitor`, its `clean` /
`process` filters, a dirty submodule's `git status` (and with it that
submodule's filters), and, in a partial clone, the `remote.<name>.uploadpack`
command of an on-demand blob fetch. Now every census call is `-z` and read
NUL-separated, the list is sorted under the C locale (a UTF-8 collation folded
`a.txt` and `a<U+200B>.txt` into one name), and the `diff` runs through the
same `gitn` wrapper as above, with every `filter.<driver>.clean` / `.process`
emptied and `.required` set false by `--config-env` (never `-c`, which cuts a
driver named `a=b` at its first `=`), no external diff, no textconv, no
stat-only refresh, `--ignore-submodules=dirty`, and `--` after `HEAD` (a file
named `HEAD` at the root made the revision ambiguous: rc 128). The drivers are
read in EVERY config scope — includes and `GIT_CONFIG_GLOBAL` too —
`GIT_CONFIG` unset for that read (it points `git config` at another file, which
`git diff` never reads), and PROVEN by a re-read with the options applied: a
driver whose last value is not empty stops the `diff` (`tracked modified
file(s) not enumerated (a filter driver could not be neutralized)`, DEGRADED).
`GIT_NO_LAZY_FETCH=1` is exported ONCE for every git of the script: a refused
fetch is a failing call, counted (DEGRADED), never an execution. The channels
CLOSED are the ones measured — not "any code at all".

Bounds, written: **versions** — `--config-env` needs git ≥ 2.31 (older: as
soon as ONE filter driver exists in ANY scope — a global `git lfs install`
suffices — the `diff` is not run: DEGRADED at EVERY run, the tree modified or
not; there is NO `-c`
fallback on such a git, by decision: `-c` cuts a driver named `a=b`, and the
security choice stands), `cat-file --batch-check -Z` ≥ 2.42 (older, when a
candidate exists: `git < 2.42 : skip-worktree .gitignore not checked`,
DEGRADED), `GIT_NO_LAZY_FETCH` ≥ 2.45 — under 2.45 the variable has NO effect
(measured, git 2.55 without the export: the index read's `cat-file`, the census
`diff` (a RACY entry under `core.autocrlf` or `text=auto` reads its index blob
even without the stat-only refresh — measured), `ls-files --others` and the
skip-worktree check's own batch `cat-file` then fetch and run `uploadpack`).
So the variable is not trusted alone: every git call of the script that reads a
repository (the header's `rev-parse --show-toplevel` excepted, pin `(brut)`)
also carries `--no-lazy-fetch` wherever this git has it — probed once
per run (one `git version`; its number is never read), and whether a given git
also honors the variable is NOT assumed (a git that accepts the flag but
ignores the variable ran `uploadpack` at the gate and at the Stop — measured
with such a git, arms `(sgl1n)(sgl1nh)`; semgrep's own git
calls do not carry the flag, the variable alone reaches them). In a PARTIAL
clone (a promisor remote) under a git WITHOUT the flag the gate does not
enumerate that root AT ALL: `?
perimeter not enumerated (partial clone, git < 2.45: a missing object would be
fetched, running the remote's uploadpack)`, a refusal to conclude, rc 0
(measured with a git that ignores the variable: the census
`ls-files --others` fetched a skip-worktree `.gitignore`, and the commit diff of
a `--filter=tree:0` clone under `--at HEAD` fetched its trees — each fetch RAN
`uploadpack`). Such a SUBMODULE is skipped BEFORE any git lists it — its index
included: the submodule enumeration tests it before descending into it, since
the `ls-files --stage` of that descent expands a sparse index and fetched an
absent tree, running `uploadpack` (measured with
GIT_TRACE) — and the loss is said (`submodule file(s) not
enumerated (partial clone, git < 2.45 …; its index not listed, nested
submodules included)`). The hook Stop runs NO git that
reads a tree or an object of such a root: NEITHER the census `diff`, NOR
`ls-files --others`, NOR `ls-files -v` (the assume-unchanged pass and the
skip-worktree probe's listing: a SPARSE index expands, reading the tree of each
directory entry), NOR the probe's `--ignored` listing (it reads the same blob),
NOR the index read's `diff-index --cached HEAD` (it reads HEAD's trees), NOR any
`cat-file`: each loss is said (`… not enumerated (partial clone, git < 2.45 …)`,
`… not checked …`, `staged git object(s) not read …`), DEGRADED, rc 0. Measured
with a git that ignores the variable, the hook Stop at 13a3cebf RAN `uploadpack`
through `diff-index` on a treeless clone (`--filter=tree:0`) before any checkout
or after `fetch` + `reset --soft`, and on a sparse-index treeless clone after
`reset --soft`; through `ls-files -v` on a sparse index whose directory entry
names an absent tree. What it still runs there reads no object: `rev-parse
--verify HEAD`, `hash-object -t tree /dev/null`, `config` (measured, no fetch).
This loss is PERMANENT there: every run
refuses or reads DEGRADED, the tree modified or not, at every
run; the remedy is
git ≥ 2.45. Skipping is not over-caution: the census `diff` itself fetches
through the racy entry above. Under git ≥ 2.45, a treeless clone (`--filter=tree:0`) refuses to conclude
whenever the target's commits need a tree it lacks (measured: `--at HEAD`,
`committed path(s) (the commit census failed)`, every such run); fetch the
trees under the operator's authority first (`git diff --raw <base>...HEAD
>/dev/null`). An ordinary repository pays one `git config` read each time the
census, the index read or the object read moves to another repository (a repeat
on the same repository is answered from memory: the Stop reads its root's once),
and the `--no-lazy-fetch` probe runs once, only where a promisor exists. **Cost of the
NUL census:** one bash `read -d ''` loop over the whole index per Stop (the
assume-unchanged pass) — measured on 101 000 skip-worktree entries under macOS
`/bin/bash` 3.2: 4.6 s against 3.3 s on the base (the skip-worktree check now
lists only the `.gitignore` entries, through a glob pathspec; under
`GIT_LITERAL_PATHSPECS=1` git refuses that glob and the check is said failed,
`check failed (git rc 128)`). **Race:** a driver
added between the re-read and the `diff` is not neutralized. **Over-listing:**
without the stat-only refresh, a file whose stat changed but not its content is
listed and scanned — cost, never a loss (an LFS file then reads whole: bounded
by `GITLEAKS_FALLBACK_MAX_FILES` under the fallback, `GITLEAKS_TIMEOUT` under
gitleaks). A submodule's working tree is not opened by the parent's `diff`; its
own census still lists its files, and a gitlink replaced by a regular file is
still listed. The header's `git rev-parse --show-toplevel` stays a plain git
(it reads no object). The sparse-index advice is switched off on the census
`ls-files --others` (an untracked file outside a sparse-index cone printed 8
advice lines, counted as 8 unreadable directories at every Stop). The sibling
census of `semgrep-scan.sh` is not aligned here.

**A skip-worktree `.gitignore` the partial clone cannot read is SAID.** A
`.gitignore` flagged skip-worktree and absent from the disk is read by `ls-files
--others` from its index blob; a partial clone may lack that blob, and under the
export git reads it as EMPTY: it over-lists (what it ignored comes back,
scanned), or UNDER-lists by losing a `!` negation — measured, `d/.gitignore`
`!keep.log` under a root `*.log`: `d/keep.log` and its key were never listed,
rc 0 `nothing to scan`. A lost `!` can only hide a file that the rules APPLIED
now IGNORE — an untracked file that is listed anyway is scanned, never missed.
So, at the root and in every submodule, such a file whose directory EXISTS and
holds an untracked path that is IGNORED now, and whose blob is MISSING, is
counted: `COVERAGE DEGRADED: <n> skip-worktree .gitignore file(s) unreadable
(partial clone) — untracked files they re-include may be missed`, rc 0, never
`clean.`. A file the census can no longer classify is a perimeter loss, said,
not a block;
switching it to a block is a pilot decision. Where nothing can be hidden,
nothing is said — measured: a cone-mode clone, a sparse clone with no untracked
file, and five such directories each holding an untracked file that is NOT
ignored read `clean.` (or `nothing to scan`); a pure over-listing (`d/.gitignore`
`*.key` lost, the key in `d/u.key` listed and BLOCKED) says nothing either. It is
said as soon as such a directory — including one outside a cone that was
recreated by hand — holds an IGNORED untracked file (`d3/x.log` under a root
`*.log`: `COVERAGE DEGRADED: 1 …`). Cost: one `ls-files -v` per repository;
when candidates exist, one listing of the IGNORED untracked paths under their
directories (under the export it fetches nothing; under an older git the census
has already read those `.gitignore` the same way) and ONE batch `cat-file` for
all of them — never a process per file (measured: 400 such files, one process
each, 5.86 s per Stop). A failing git call here is said (`skip-worktree
.gitignore check failed (git rc <n>)`), never a count of 0. Its work files, and
the filter-driver read's, are removed by the exit trap when a signal stops the
run (SIGINT to the gate's process group measured, as a Ctrl-C would send it;
SIGTERM runs the same trap).
Windows (NTFS, locks, no `O_NOFOLLOW`): not measured — the fresh directory
stays the guarantee. On a case- or normalization-INSENSITIVE file system (APFS
by default, NTFS), two index paths that differ only by case (`K.txt`/`k.txt`)
or by Unicode normalization land on ONE file of the index copy: an existing
destination counts as read ONLY when the same object (same sha) was already
written at that very path in the run; otherwise it is a counted loss, DEGRADED
— identical content included, with or without python (the prudent sense; the
file written is never hashed, so no filter takes part) (measured on APFS: before
this rule, a benign `K.txt` hid the key of `k.txt` and the run read `clean.`).
**Signals:** every writer of the index copy runs as ONE background child whose
pid `on_exit` kills and reaps BEFORE any directory is removed, and the reader
never recreates its destination — a SIGTERM to the gate alone leaves neither
stage nor blob in TMPDIR (measured, python and without). Not closed, as before
this task: a SIGKILL runs no trap and leaves the stage — tree copies and index
copy — in TMPDIR; `timeout` signals gitleaks/grep only, and an orphaned scanner
only reads. **Cost, measured on the nominal Stop** (clean kit
clone, index = HEAD): median +31 ms on this workstation over 4 alternating
runs (0.324 s → 0.355 s, load ≈ 3); a separate measurement found +61 ms median. The
plan's ≈ 17 ms was one `diff-index` alone. `semgrep-scan.sh` now carries the
index perimeter too — the root and every REACHABLE submodule at the gate, the
root alone at the hook Stop (see § SAST scan below) — but
NOT the unreachable-submodule branch: the index of a submodule this uid cannot
reach is not read there. Its enumeration names such a submodule unreachable and
counts it as a loss, never `not initialized`.

**Install `gitleaks`:**

```bash
# macOS
brew install gitleaks

# Linux (Debian/Ubuntu CI): download the release binary
GL=8.21.2
curl -sSL "https://github.com/gitleaks/gitleaks/releases/download/v${GL}/gitleaks_${GL}_linux_x64.tar.gz" \
  | tar -xz -C /usr/local/bin gitleaks
```

```powershell
# Windows
winget install gitleaks        # or: choco install gitleaks / scoop install gitleaks
```

**Without gitleaks on PATH:** the gate does not fake a result and does not go
blind either — it prints `COVERAGE DEGRADED: gitleaks not installed —
deterministic fallback ENGAGED (9 prefixed families)` on stderr and scans the
same staged content with a built-in fallback covering 9 PREFIXED credential
families (AWS, GitHub, Slack, Google, GitLab, Stripe, Anthropic, npm, PEM
private-key blocks). That fallback CAN block (exit 2) on a hit. It does NOT cover
generic/entropy secrets, passwords, connection strings, JWTs or binary files —
install gitleaks for full coverage. It DOES honour the `[allowlist] regexes` of
`.gitleaks.toml` as literals (same file, same doctrine: a fixture that is not a
credential, never a real key), **read at each run** — so an exemption the pilot
writes during a session takes effect at the next hook **without relaunching the host**.
**Write it in the shape the fallback reads: one entry per line inside the
multi-line `regexes = [` … `]` of the FIRST `[allowlist]` table; any other TOML
spelling counts 0 for the fallback, and the `fallback allowlist:` line on stderr
tells you how many it honoured.** Note that a BROKEN `.gitleaks.toml` is still
honoured HERE by form (one literal block) while the gitleaks engine sets it
aside — two engines, two verdicts. A benign path still never exits 2. The fallback
declines a staged list above `GITLEAKS_FALLBACK_MAX_FILES` (default 5000) as
DEGRADED — that is an ignore defect, fix `.gitignore`. Emergency off-switch:
`GITLEAKS_FALLBACK=0` in the HOST's environment **at launch** (a hook inherits
the host's environment when the host starts, never from a terminal opened later).

**False positives:** drop a `.gitleaks.toml` at the repo root to allowlist a
known-safe match; `gitleaks-scan.sh` passes it via `--config` automatically when
present. gitleaks honours all four allowlist forms (`rules`, `paths`, `regexes`,
`stopwords`); **the deterministic fallback honours ONLY `regexes`, taken as
LITERALS on the token** — a `paths = [...]` has no effect on it. Prefer a narrow
allowlist entry over disabling the rule. Write it in the shape BOTH engines read
— one entry per line inside a multi-line `regexes = [` … `]` block:

```toml
[allowlist]
description = "known test fixtures / documented example keys"
regexes = [
  '''NOTAREALKEY0123456789abcdef''',
]
```

**`.gitleaks.toml` is the PILOT's file.** It is the exception
register of a gate that cannot be waived, so no agent Edit/Write reaches it: the Edit guards
refuse it on every host that has one — `protect-paths.sh` (Claude Code, rule
`gitleaks-allowlist`), `protect_paths.py` (Codex, Copilot, Kimi via `.codex/`;
Gemini/Antigravity via `.gemini/`), matched case-folded like the gate markers,
plus `Edit(./.gitleaks.toml)` in `permissions.deny`. The match is a suffix, so a
`.gitleaks.toml` in a sub-directory (and a `<x>.gitleaks.toml`) is refused too; the
Claude `safe-bash.sh` redirect guard derives its list from the same arms: the
redirect guard refuses an unquoted redirect to one; like every protected name
outside the arming-marker-name clause it prevents forgetting, not cheating — a
quoted target, tee, cp, sed -i, git checkout pass. An agent that
hits a false positive REPORTS it; the pilot decides and edits the file by hand.

**`.gitleaks.toml` is the ONLY exception channel.** gitleaks has
two more, both writable by the very agent being scanned, and the gate shuts
both (measured on 8.30.1): an inline **`gitleaks:allow`** comment on the
secret's line is IGNORED (`--ignore-gitleaks-allow`), and a **`.gitleaksignore`**
of fingerprints is IGNORED — gitleaks reads it from the working directory and
from the source root, both the gate's staging copy, and an explicit ignore path
does not stop the source-root read, so the staged `.gitleaksignore` is renamed
before each scan — renamed, so its CONTENT is still scanned (reported as
`.gitleaksignore.T844`) and a secret written inside it still blocks. This repo
uses neither. A secret carrying either still BLOCKS, in the Stop form and in
`--content`, and the block adds a note saying these channels are IGNORED by
this gate and that the pilot exempts a false positive's LITERAL in
`.gitleaks.toml`.

**An `[extend] path` MUST be absolute.** gitleaks resolves a
relative `[extend] path` against its working directory, which used to be the
staging copy of the diff, populated by the agent: measured, the pilot's
`path = "extra.toml"` plus an untracked `extra.toml` written by the agent
exempted a secret (rc 0). gitleaks now runs from an empty temp directory beside
the stage, so a relative `[extend] path` never resolves against the scanned stage
— whatever its spelling (`[extend]`, `[ extend ]`, `extend = { path = … }`,
`extend.path = …`, `PATH =` all measured). A plain `x` cannot load there: the
config is set aside (`COVERAGE DEGRADED: … unreadable — default rules, allowlist
IGNORED`) and a real secret BLOCKS; the same holds for a relative `path` inside
an extended file. **But `../x` reaches `$TMPDIR/x`, a path any process of this
user can write** (measured: rc 0, no DEGRADED) — the gate does NOT enforce the
MUST-be-absolute rule, the pilot does.
**Bound:** an ABSOLUTE path is kept as is. Outside the repo it is protected by
nothing in this kit. Inside the repo, name the extension file
`<x>.gitleaks.toml` — the suffix is refused by `protect-paths.sh`
(`*.gitleaks.toml`) and `protect_paths.py` on every host that has an Edit guard;
any other in-repo path is protected by nothing.

**An unreadable `.gitleaks.toml` no longer switches the gate off.**
When a gitleaks scan that carries a config (the project file, or a
`GITLEAKS_CONFIG_TOML` from the host's environment) FAILS the way an unreadable
config fails — an exit code other than 0 and 1, or exit 1 with no readable
finding in the report — the gate loads that config over an empty directory. If
the load fails — broken TOML (gitleaks rc 1), a rule whose regex does not compile
(rc 2) — the config is **set aside**, the gate says so:

```
COVERAGE DEGRADED: <config> unreadable — default rules, allowlist IGNORED (gitleaks rc N …)
```

and the stage is scanned AGAIN on gitleaks' **default rules** — wider than the
pilot's allowlist, NARROWER if the file added custom `[[rules]]`, which are
dropped too (an explicit `[extend] useDefault = true` of its own, so neither the
staged broken file nor the environment can come back in). **A real secret is BLOCKED (exit 2).** The price,
said: **every false positive the file exempted BLOCKS again until the pilot
repairs it.** Before this, the broken file produced `gitleaks returned 1 but no
finding could be read` → DEGRADED, exit 0 — the secret passed, at the Stop AND at
the `--content` PreToolUse hook. **A `GITLEAKS_CONFIG` exported by the host is
never honoured as a source:** the gate re-points that variable at the project's
`.gitleaks.toml`, so with no project file gitleaks is sent to an absent path —
formerly a DEGRADED exit 0, now named (host value and re-pointed path) and
scanned on the default rules. **Cost:** a valid config pays NOTHING — the check
runs only after a failed scan (a first version checked before every scan and
cost ~0.24 s on each Edit/Write and each Stop; it was withdrawn). Measured on
this repo, medians: `--content` 0.45 s before the fix, 0.46 s after (15
interleaved runs); Stop over 20 dirty files 0.50 s both. Only the broken case
pays: one check spawn plus a second scan (Stop 0.50 → 0.86 s).

**Bound — a config that LOADS can still switch gitleaks off.** The check reads
loadability, never coverage. An empty `.gitleaks.toml`, or one without
`[extend] useDefault = true` (a supplied config REPLACES the built-in rules),
loads fine (rc 0), gitleaks then has no rules, and a real secret passes as
`clean` — and so does a loadable, rule-less `GITLEAKS_CONFIG_TOML` when the
project has no file. Nothing in the gate detects it; the ONLY cover is that the
file is pilot-only (the Edit guards and `permissions.deny` above), and the host
environment is the pilot's.

**Bound — two channels, two verdicts on "config set aside, nothing found".**
When the broken config is set aside and the default-rule rescan finds nothing,
stderr and the Stop `systemMessage` say `COVERAGE DEGRADED … allowlist IGNORED`
followed by `clean.`, while the audit line (`audit-log.jsonl`) records `CLEAN`
and the `scan.secrets` event `status=scanned`. Both are true — the scan DID run
to the end, on the default rules (see above for what that drops) — but a reader of the audit or of
canal-A alone does not see that the register was unreadable. The same split
already existed for the `no timeout(1)` notice. The `COVERAGE DEGRADED`
line comes back at every run until the pilot repairs
the file.

**A DEGRADED at the Stop is SHOWN, not just logged.** On exit 0 a
hook's stderr reaches neither the model nor the Claude Code interface. So in the
default (diff) form every `COVERAGE DEGRADED:` line of the run is ALSO emitted as
ONE stdout object, `{"systemMessage": "COVERAGE DEGRADED: …"}` — the Stop form
`semgrep-scan.sh` uses for every host — and the plain `clean.` / `nothing to scan`
line then travels inside that message rather than next to it (stdout must stay a
single JSON value). stderr is unchanged, so a caller that reads it sees the same lines;
exit 2 keeps stderr alone; `--content` keeps an empty stdout. Whether Codex,
Copilot, Gemini and Kimi RENDER a Stop `systemMessage` is not measured.

## SAST scan (semgrep) — class-1 input for `security-code-review`

`.agents/security/semgrep-scan.sh` runs [semgrep](https://semgrep.dev/) on the
files touched by the working-tree diff (changed + untracked vs HEAD) and feeds
its findings into the `security-code-review` agent's triage — in GATE mode it
never gates on its own. Findings this agent confirms as HIGH/CRITICAL are
**class-1: never waivable** (see AGENTS.md § Security gate). It never dumps
matched code, only rule id + `file:line`, appended to
`.agents/state/local/sca-reports/audit-log.jsonl`.

**Registered as a host hook.** The scanner also runs as
a host hook: `--hook --event=post` after every edit (over the edited file(s) only)
and `--hook --event=stop` at end of turn (over the dirty tree only), on the five
registries (`.claude/settings.json`, `.codex/hooks.json`, `.agents/hooks.json`
shared by Gemini/Antigravity, `.kimi-code/hooks.json`, `.github/hooks/agent-guardrails.json`).
Host coverage is **3 measured / 0 inherited / 1 assumed / 2 inert-measured**, never
"six hosts covered". A finding blocks on Claude (stderr + exit 2, the edit is kept
on disk); envelope hosts get the finding in context. Each call costs ~7 s and is
bounded by `SEMGREP_TIMEOUT` (45 s in hook mode). **The Stop hook re-scans the
dirty tree only when a covered file, the path list or the local ruleset changed
since the last CLEAN** (cache `.agents/state/local/semgrep-hook/stop-propre`;
a skipped scan still writes its `audit-log.jsonl` line with
`"mode":"hook-cache"` and a `scan.sast` event with `status=skipped`). A finding
or a degradation clears the cache; a CLEAN carrying a semgrep error other than
`PartialParsing` (a timeout, say) never fills it, nor does a file whose bytes
differ after the scan; a registry `--config` is never cached. **Bounds:** a file
changed and restored to the same bytes during the scan is not detected, and a
semgrep upgrade does NOT invalidate the cache — delete that file after upgrading.
Nor does a kit upgrade: a `stop-propre` written before report validation was fixed
on a malformed report (`{}` read CLEAN, then cached) is still served while its
fingerprint holds — it carries the config and the perimeter's bytes, NOT those of
`semgrep-scan.sh`; the first Stop that rescans (a covered file or the config
changes) erases it, or rewrites it on a real CLEAN. Delete that file after
upgrading the kit. Only the BLOCK is once-per-session, not the scan.

**An unread path is never dropped in silence.**
Every path git lists for the perimeter is now sorted into: scanned, genuinely
deleted (silent, as before), or LOST — and a lost path is COUNTED on stderr as
`COVERAGE DEGRADED: <n> <cause> — not scanned; perimeter INCOMPLETE` (a count
and a cause, never a path). The losses: a path behind a directory this uid
cannot search (unreachable ≠ deleted); a regular file it cannot read (counted
and REMOVED from the scan, so the other files are still read instead of
drowning in semgrep's rc 2); warning lines of `git ls-files --others` (an
untracked directory it could not open); a failed `git diff` census of the
dirty tree (refus de conclure); an unreachable submodule (no longer reported
"not initialized"), a failed submodule enumeration or a failed listing of a
submodule's tracked files (refus de conclure), the submodule depth bound; a
failed commit census (`git diff X~1 X` and `git show X` both in error, default
mode and `--at`: refus de conclure). A repository with no commit yet scans its dirty tree
against the empty tree instead of `nothing to scan`. Outside any git repository
the census fails: the scope line says `hors dépôt git`, the gate says `refus de
conclure`, the hook Stop says COVERAGE DEGRADED (stderr at every Stop, the
systemMessage once per session and message) — both were silent before. On any
loss the gate prints no benign sentence (`clean on the diff`, `nothing to scan`,
`rien à lire`, `couverture portable par attestation`), the audit line carries
`"couverture":"DEGRADED"` (or `refus de conclure`), the `scan.sast` event says
`status=degraded`, and **no common verdict**
`semgrep-verdict.json` is left (`semgrep-scan: verdict commun non rendu
(périmètre incomplet)`): `cadre.scan-verdict/1` cannot carry a loss yet, so a
consumer reads "no verdict", never "clean". In hook mode a loss is never muted
and never served from the Stop cache: the result is DEGRADED, its stderr lines
at every call, the systemMessage once per message and per session at the Stop
(marker `semgrep-hook/perte-<h16>-<hash>`) and at every Post call. Exit code 0,
gate AND hook — degrade, never block. **Bounds:** `[ -r ]` passes under an ACL or an
EDR that then refuses the read (back to the said `semgrep error (2)`); the
INDEX is read only as the git objects of the next paragraph; submodules are out
of the hook's perimeter; the hook counts a lost path only when its extension —
read on the file's basename, so `.cfg/run` has none — is covered or absent. A
base with no merge base with HEAD is no longer a silent loss: next paragraph.

**A report the gate cannot parse is never a clean.** The gate runs without `set -e`: measured on d0c2c238, a parser
that died on semgrep's report — a JSON list, a result that is not an object, a
path carrying a lone surrogate (a REAL finding lost), a failed `mktemp` of its
work files — left an empty count, defaulted to 0, and `[ "" -eq 0 ]` answered
false: `clean on the diff.`, rc 0. Each guard now says ITS reason,
`COVERAGE DEGRADED: semgrep report parse — <reason>`, audits `DEGRADED`, emits
`scan.sast` `status=degraded`, rc 0: `work file not creatable` (mktemp),
`parser exited N` (the status is read before anything the parser printed),
`parser output malformed` (anything but `<findings> <scope>`, a stray stdout
line included), `not a JSON object` (without Python, a report that does not
open on `{`); `findings count unreadable` and `scope figure unreadable` are
defense in depth, unreached as the script stands. **Valid JSON is not a
semgrep report:** measured on 6fc0450c, `{}`,
`{"results":{}}`, `errors`+`paths` without `results`, and `errors`/`paths`/
`scanned` mistyped read `clean on the diff.`, rc 0, audit CLEAN — `{}` without
Python too — while the common verdict of the same run said degraded. The
parser now applies a shape test, `forme`, copied from `scan_verdict.py`
`_forme_semgrep` on the fields it reads: `report malformed (no 'results' list
of objects, or errors/paths mistyped)`. Without Python, two more guards: `no
'results' list (no Python to parse it)` (an object that opens no `results`
list) and `report truncated (no Python to parse it: its last non-blank byte is
not a closing brace)`. The HOOK applies the same test (`forme_hk`) in its report
phase, AFTER the rc test (`semgrep error (N)` keeps precedence): `COVERAGE
DEGRADED: SAST hook — semgrep report malformed (…)`, the DEGRADED form per host
and event, and the Stop cache ERASED, never filled. A report phase that died
before any verdict (measured with `[1]`: a traceback on stderr, stdout EMPTY on
every host) is caught by a shell belt: `COVERAGE DEGRADED: SAST hook — the
report phase died before any verdict; nothing reported, a 0 here proves
nothing` on stderr, and the DEGRADED form per host/event on stdout. A failed read of the finding
LOCATIONS keeps the verdict (FINDINGS, rc 1) and writes `"locations":[]`, so the
audit line stays JSON. Arms `(prs1)`–`(prs17)` (`(prs10)`–`(prs16)`: one witness
per clause of the shape test — results, errors, paths, scanned —, `(prs13)` the
no-Python `results` guard, `(prs17)` its truncation guard), `(hrs1)` (a malformed report at the Stop, `stop-propre`
erased), `(hrs2)` (the belt), `(h15)` (six host/event cells), `(prsp)` (the
three copies of the shape test agree on one corpus); mutants MPRC MPSH MPALL
MPMK MPNP MLJ, MPFS MPFE MPFP MPFC MPRN MPTR, MHFS MHFE MHFP MHFC, MHBELT. **Bounds,
said:** a lone-surrogate path is DEGRADED and its finding is NOT counted (never
a FINDINGS, never a clean); `skipped_rules` and `paths.skipped` are read by
neither `forme` nor `forme_hk`, so not checked there (the common verdict still
degrades on them); without Python the gate only sees that the `results` list
OPENS and that the object ENDS on `}` — a report cut right after an inner `}`,
the ELEMENTS of that list, `errors` and `paths` are NOT checked (the Python
branch checks them); in the hook, a report phase that fails AFTER it wrote a
stdout line gives TWO stdout lines (that line, then the belt's) — at three
sites: `degrade()`, the perimeter-loss notice and a finding's form.

**What the gate reads, and which repository channels it cuts.**
`git commit` takes the INDEX and pushes COMMITS: measured at c2a42ba2, a sink
`git add`ed under a benign working tree (or then removed from it) read `clean on
the diff.`, a sink COMMITTED under a benign tree read the same by default and
under `--at HEAD`, the hook Stop was mute, a submodule's index was never read.
Beside the working-tree files the perimeter now carries GIT OBJECTS, read RAW by
`git cat-file` (no filter), written only when semgrep runs into a fresh
`semgrep-objs.*` directory under `.agents/state/local/sca-reports/` — inside
the repository, ignored, never under TMPDIR (cost below) except when the report
directory is reached through a symbolic link (the private directory, below) —
(0600 files, removed by the EXIT trap),
and scanned under a LABEL that replaces the machine path in every field of the
report that carries a path, before any reader sees it: `index:<rel>` — an index
entry that differs from HEAD (from the empty tree when there is no commit yet),
at the root and in every REACHABLE submodule at the gate, the root alone at the
hook Stop, never under `--at` (which asks what a COMMIT changed); `commit:<rel>`
— a path of the target's commits whose working-tree copy differs from the
POINTE (HEAD, or the `--at` ref), is not a readable regular file (deleted,
skip-worktree absent), or is an entry git NEVER compares — assume-unchanged
(every path `git add` stages under `core.ignoreStat=true`) or skip-worktree:
`git diff` takes its index copy for the tree, so a committed sink rewritten
benign there would read `clean` (measured by default and under
`--at HEAD`). A finding then reads `index:k.py:3`; at the hook Stop it
blocks like a finding of the tree (exit 2 on claude). The labels count in the
perimeter: the scope line adds ` + <m> git object(s) (index/commit)`, and an
attestation must name them (EQUALITY). An object that could not be read is a
COUNTED loss (`git object(s) not read`). **Price:** a staged copy identical to
the tree is scanned twice, and its finding reported twice (`k.py` and
`index:k.py`). Under `core.ignoreStat=true` every path `git add` stages is
assume-unchanged, so EVERY such committed path of the target becomes a
`commit:` object beside its working-tree file (measured: 300 files gave 300 files + 300 objects, the gate from 3.0 s to
4.0 s) — a price, never a loss. **A base with no merge base with HEAD** (`--since o` on an
unrelated history, or such an `@{upstream}`) DEGRADES and falls back to HEAD
alone, said (`? commit(s) since the base not enumerated (no merge base with
HEAD; fell back to HEAD alone)`), no verdict; on a MERGE head it refuses to
conclude; a failed merge-base or range census is a refusal to conclude. **The
census runs no code of the scanned repository through this CLOSED list of cut
channels** — the list, not a promise that nothing runs: `core.fsmonitor` and
`core.hooksPath` (off on every git call that reads a repository); every
`filter.<driver>.clean`/`.process` emptied by `--config-env` (never `-c`, which
cuts a driver named `a=b`), `.required` reset, PROVEN by a re-read with
`GIT_CONFIG` unset — otherwise the tree diff is NOT run and the loss is said;
no external diff, no textconv, no stat-only refresh (`diff.autoRefreshIndex`:
the price is a stat-dirty file scanned, never a file lost); a submodule's
working tree not opened by the root diff (`--ignore-submodules=dirty`, never
`=all`, which hides a gitlink turned into a regular file); the lazy fetch of a
partial clone (`GIT_NO_LAZY_FETCH=1`, exported once); `log.showSignature` (the
commit census passes `--no-show-signature`, so `gpg.program` never runs) and
`log.showRoot` (`show --root`, so a root commit is never listed empty); the
sparse-index advice on `ls-files --others`; and the git that semgrep ITSELF
runs in ROOT (`git remote get-url origin`, `git ls-remote --get-url` —
measured) gets the same `core.fsmonitor`/`core.hooksPath` cut, through
`GIT_CONFIG_COUNT` on semgrep's command line (a caller's own
`GIT_CONFIG_COUNT` is replaced for semgrep's process only). Assume-unchanged entries (lowercase
tag of `ls-files -v`, which `git diff` never compares) join the census; the
perimeter is sorted in BYTES (`LC_ALL=C`), so a UTF-8 collation never folds two
names into one. A skip-worktree `.gitignore` whose blob a partial clone lacks
is counted when it can hide an ignored untracked file — at the gate (root and
submodules) AND at the hook Stop. **An index listing is complete or said
incomplete**: under git 2.55 with the no-lazy-fetch
export, `ls-files`, `ls-files -v` and `ls-files --stage` return rc 0 and OMIT
the entries of a sparse-index directory entry whose tree is absent from the
object store (a crafted index, or a partial clone lacking that tree; measured,
local fixtures). In the default mode — the root and each submodule at the gate,
the root at the Stop — one `ls-files --sparse -s` per repository lists the
directory entries without expanding them, then ONE batch `cat-file` checks
their trees, only when there is one: each absent tree is counted in
`sparse-index directory entr(y|ies) naming a tree absent from the object store
(…)`, DEGRADED, rc 0 (arms `(sga1)(sga1h)`). Under `--at <ref>` no line is
said: the only index listing there is the commit objects' assume-unchanged
pass, which falls back to SAFE BY DEFAULT (every committed path an object) —
a defensive branch no arm isolates, the diff before it failing first on every
such fixture measured. Cost: one more `ls-files` per repository and run (a
`cat-file` only on a sparse index) — measured on the nominal Stop of a 4 055-entry
clone of this kit, `/bin/bash` 3.2, 6 alternating passes, load 6 to 8: median
0.455 s at 7c78f87f, 0.456 s at a35a8813. **Bounds — said, not closed:** only the
POINTE of the ROOT is read, never an intermediate commit of the target; a
submodule's commits are never read as objects; the index of an
UNREACHABLE submodule is not read; a channel outside the list above (an
`alias`, `core.sshCommand`, a credential helper) is NOT declared cut; nor is the
scan event's emitter: the SCANNED repository's own `.claude/hooks/emit-event.sh`
is run under `bash` at every gate and every hook run that emits the event —
repository code, whatever it runs (the kit's own copy loads
`.agents/bin/events.py`) — measured: a committed
`emit-event.sh` runs once per gate and once per Stop; git < 2.31
with a filter driver (no `--config-env`), git < 2.36 (no `ls-files --sparse`:
a sparse-index entry naming an absent tree is NOT checked — a truncated index
listing goes unsaid on such a git), git < 2.42 (no NUL batch-check: the
`.gitignore` probe is `not checked`) and git < 2.45 on a partial clone (no
`--no-lazy-fetch`: the gate refuses to enumerate, the Stop lists neither the
tracked diff nor the untracked files nor reads the index, such a submodule is
skipped) are a
PERMANENT DEGRADED on that host; a SIGKILL runs no trap and leaves
`semgrep-objs.*` (its files 0600) under `.agents/state/local/sca-reports/`
(ignored, skipped by both censuses); a `SEMGREP_CONFIG` value that is
not UTF-8 makes the audit line unreadable — it is counted as malformed (the
line of `config` is otherwise escaped for JSON: backslash, quote, LF, TAB, CR,
control bytes dropped). **At the hook Stop:** the index objects are filtered by
the covered extensions like the tree census — an uncovered OR an extension-less
name is neither read nor scanned, MUTE, exactly as at the gate:
semgrep 1.175 reads NO explicit target without an extension — measured, absent
from `paths.scanned` — so the gate concludes CLEAN over it, and counting it at
the Stop said a loss the gate never says: at be3c94ed a staged `Dockerfile` made
every Stop DEGRADED, its clean-verdict cache off). **Bound, said:** a sink in an
extension-less file (`Makefile`, `Dockerfile`, a shebang script) is read
neither at the gate nor at the Stop. The covered objects are read only after
the clean-verdict cache was consulted (its fingerprint carries their sha),
within 8 s fixed — with the 45 s of semgrep the Stop stays under the host's
60 s, the census before it excepted; an overrun is a counted loss. Each
fail-closed branch of the Stop (filters not neutralized, `ls-files -v` failed,
the skip-worktree `.gitignore` probe, the partial clone under an old git)
degrades with a systemMessage, never the mute exit. **The report directory of
`semgrep-scan.sh` is never reached through a symbolic link** (this script
only — `gitleaks-scan.sh` and `sca-scan.sh` write under the same
`sca-reports/` and do not test it: grep of 2026-10-16, no `[ -L ]` on their
report path): the scanned repository is untrusted, and `.agents/.gitignore`
ignores `state/local/` as a directory only, so a committed link is checked out
like any file. When `.agents`, `.agents/state`, `.agents/state/local`,
`.agents/state/local/sca-reports`, or one of the fixed names written in place —
`sca-reports/audit-log.jsonl`, `.agents/state/local/semgrep-hook` or
`semgrep-hook/stop-propre` — is a symbolic link, the gate AND the hook SCAN in
a private directory made under TMPDIR, removed by their EXIT trap (a refusal
would let ONE committed link turn the gate off over a committed sink, rc 0; a
committed link at `stop-propre` or `audit-log.jsonl` written in place would make
the Stop truncate, or append to, the file behind it — measured): the sink is
found as anywhere else, and the loss is said — `audit line and common verdict
not kept (report directory is a symbolic link; private directory used); scan
event not emitted` at the gate, `audit line, markers and clean-verdict cache not
kept …; scan event not emitted` at the hook — so no common verdict, no audit
line kept, no cached clean, and NO `scan.sast` event: in a kit-shaped
repository (`emit-event.sh` and `events.py` present) the emitter wrote
`<link target>/events/<day>.jsonl` behind a committed `.agents/state` link,
gate and Stop (measured). A link at
`.agents/state/events` itself also suppresses the event, said in a note (no
path of the perimeter is lost). Neither suppression applies when the path of
`AGENTS_EVENTS_DIR` never passes THROUGH the repository (no link of the
repository on that path): the event is emitted there and the loss line ends in
`scan event emitted to AGENTS_EVENTS_DIR (outside the repository)` instead.
That passage is judged by
IDENTITY, never by text (a text prefix would read the
repository's own `.agents/state/events`, spelled `/tmp/…` for a ROOT under
`/private/tmp/…`, as outside, and write the event behind the committed
`.agents/state` link — measured at the gate and at the Stop): a RELATIVE value is made absolute against the PHYSICAL cwd
(where `events.py` resolves it); every textual ancestor is tested `-ef` ROOT;
the deepest existing ancestor is resolved physically and each of ITS ancestors
tested the same way; a dangling link, or a `.`/`..` in the part that does not
exist yet, answers "inside" — the event is then not emitted, said. **Bound:** a
link of the caller's own pointing at a link INSIDE the repository that leads
back outside it is not followed hop by hop. A link on the EMITTER's own path
(`.claude/hooks`, `.agents/bin`) is not tested — the emitter is the
repository's own code, run at each such gate and Stop (bound above). The cache write
also removes `stop-propre` before writing it. Only when that private directory
cannot be made do they refuse before any write — COVERAGE DEGRADED, rc 0,
nothing read, no audit line, no event, no verdict written or removed (measured
with the test off: the audit line, the common verdict and `semgrep-hook/`
landed where the link pointed). The objects then live under TMPDIR, at the
price measured below. **Bounds, said:** a link made after the test (a race) is
not seen — the `rm -f` before the `stop-propre` write narrows that window for
that one name, it does not close it; no other file under `sca-reports/` is
tested, because none is written in place at a guessable name — each is made by
`mktemp`/`mkstemp` (O_EXCL, random name) or replaced by `os.replace`
(`semgrep-verdict.json`), grep of 2026-10-16 (the PARSE's
`.semgrep-unparsed.*` file is named by `mktemp`: opened in place at a guessable
name, a committed link there would make the gate truncate the file behind it,
rc 0 `clean on the diff.`);
a stale `semgrep-verdict.json` behind a parent link is left in place — the kit
has no reader of that file besides `scan_verdict.py`, its writer (grep of
2026-10-16). Under a link at a FIXED name only (`audit-log.jsonl`,
`semgrep-hook`, `stop-propre`: the four directories are then real), the gate
removes the repository's own stale `semgrep-verdict.json` too, unless it is
itself a link — the run's own verdict lives in the private directory, and no
verdict beats a stale one. **The objects are written INSIDE the repository**, under
`.agents/state/local/sca-reports/semgrep-objs.*`, never under TMPDIR except
under a linked report directory (the private directory above): launched
from a repository, semgrep pays ≈ 0.23 s per target that lies OUTSIDE it
(measured with semgrep 1.175: the same 50 object files cost 13.2 s under
TMPDIR and 1.96 s in an ignored directory of the clone; `--no-git-ignore`
changes nothing). That directory is ignored where the kit is installed
(`.agents/.gitignore`: `state/local/`, the template's own copy too), both
censuses skip it, and semgrep scans an EXPLICIT target even when `.gitignore`
or a `.semgrepignore` covers it (measured, 1.175). A rule's own `paths:` filter
still judges an object on that MACHINE path (measured: a rule
excluding `.agents/` leaves `index:k.py` unscanned, CLEAN): an object written and
NOT scanned while its working-tree twin was is a COUNTED loss, `git object(s)
not scanned while their working-tree twin was (a rule paths: filter judged the
machine path)`. **Bound, said:** an object WITHOUT a twin in the tree (a staged
file then removed, D1b) is still judged on its machine path alone — such a
rule can drop it without a word. **Cost, measured on the hook
Stop** (a clone of this kit, 4 047 index entries, semgrep 1.175, median of 4
alternating passes, load 4 to 8; c2a42ba2, before the index was read →
82d10a60, objects under TMPDIR → objects under `sca-reports/`): on a cache
MISS, 10 files staged ≠ HEAD 2.33 → 4.99 → 2.66 s and 50 files 2.47 → 14.75 →
2.99 s under `/bin/bash` 3.2 (bash 5.3: 2.23 → 5.06 → 2.58 s and 2.53 → 14.80 →
3.00 s); 150 files, 2 passes, `/bin/bash` 3.2: 2.67 → 38.33 → 3.52 s — at
82d10a60 that Stop was 7 s from its 45 s timeout. Measured at 82d10a60 and
untouched by the move (no object is written on these two paths): nominal (clean
tree, index = HEAD) 0.28 s → 0.43–0.48 s, i.e. +150 to +200 ms (K2 over the
whole index, the `.gitignore` probe, `diff-index`, the filter-driver reads); 10
files staged with the clean verdict SERVED from the cache 0.38 → 0.57 s (their
blobs are not read). **The bound that remains:** reading and scanning the
objects costs +0.3 to +0.9 s over the tree-only Stop from 10 to 150 staged
files; a Stop that still overruns 45 s DEGRADES on its timeout — a degradation
said, never a false clean. Passing the object DIRECTORY instead is not a
remedy: semgrep's default ignores then skip `tests/` and `vendor/` without a
word (measured).

**Install `semgrep`:**

```bash
# macOS
brew install semgrep

# Linux / pipx (recommended — isolates the install)
pipx install semgrep

# Linux / pip
python3 -m pip install semgrep
```

```powershell
# Windows
pip install semgrep
# (or: pipx install semgrep, then ensure the pipx/pip Scripts dir is on PATH)
```

**Offline vs registry config:** by default the scan uses the small ruleset
committed at `.agents/security/semgrep.yml` — no network required. For full
community-ruleset coverage (many more languages/CWEs), point `SEMGREP_CONFIG`
at the official registry instead (needs network to fetch):

```bash
SEMGREP_CONFIG=p/security-audit bash .agents/security/semgrep-scan.sh
```

**Without semgrep on PATH:** same discipline as gitleaks — the scan does not
fake a result. It prints `COVERAGE DEGRADED: semgrep not installed` on stderr
and exits 0 (never a false CLEAN, never a false block); `security-code-review`
notes the gap and continues its manual review.

In HOOK mode the same DEGRADED is emitted ONCE per session as a `systemMessage`
(session marker under `.agents/state/local/semgrep-hook/`), with exit 0 — the hook
never blocks an edit because a tool is absent.

## IaC misconfiguration scan (trivy) — part of `sca-scan.sh`

[trivy](https://trivy.dev/)'s `config` subcommand is folded into
`.agents/security/sca-scan.sh` as an additional, unconditional block (no
single manifest to gate detection on — trivy finds Dockerfile/Terraform/
docker-compose/Kubernetes/Helm files itself under the scan target). Findings
land in `.agents/state/local/sca-reports/trivy-config.json`, normalized by `waiver_filter.py`
into the same pivot format as dependency findings (`ecosystem: "iac"`), and
gated the same way — see the waiver key below. `sca-policy.json` always
escalates `iac_misconfig` (never auto-fixed: an infra fix is structural, not
a version bump).

**Install `trivy`:**

```bash
# macOS
brew install trivy

# Linux (Debian/Ubuntu)
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
  | sh -s -- -b /usr/local/bin

# Linux / any OS with Go toolchain
go install github.com/aquasecurity/trivy/cmd/trivy@latest
```

```powershell
# Windows
choco install trivy    # or: scoop install trivy
```

**Offline by design:** `trivy config` runs against trivy's built-in
misconfiguration check bundle — no vulnerability database download, no
network required, unlike `trivy image`/`trivy fs` (dependency CVE scanning,
not used by this kit).

**Without trivy on PATH:** the block notes `trivy: not installed` in
`.agents/state/local/sca-reports/modules/<module>/.degraded` (or the root `.degraded` for a
non-module scan) and never fakes a GO — same discipline as every other
scanner in this dispatcher.

**Waiver key for an IaC finding** (`.agents/security/sca-waivers.json`):
`ecosystem: "iac"`, `package: "<check/AVD id>"` (e.g. `"AVD-DS-0002"`),
`version: "<scanned path>"` (e.g. `"Dockerfile"`), `class: "iac_misconfig"`;
`advisories: "*"` waives the whole check on that path, same semantics as a
dependency waiver.

## Python dependency scan (pip-audit) — part of `sca-scan.sh`

[pip-audit](https://pypi.org/project/pip-audit/) (PyPA, free, no account, JSON
output) is folded into `.agents/security/sca-scan.sh` as the Python ecosystem
block. It audits a project's PyPI dependencies against the OSV / PyPI advisory
databases and writes `.agents/state/local/sca-reports/pip-audit.json`,
normalized by `waiver_filter.py` into the same pivot format as every other
dependency finding (`ecosystem: "pypi"`, `class: "known_cve"`).

**Install `pip-audit`:**

```bash
# any OS with Python
pipx install pip-audit    # recommended — isolates the install
# or:
python -m pip install pip-audit
```

**LOCK-ONLY posture — `--no-deps` is ALWAYS passed, and it is the whole point.**
`pip-audit -r <requirements.txt>` **resolves** the dependency set by default:
it downloads and **builds sdists**, i.e. it executes arbitrary `setup.py`. That
is exactly the mutation the dispatcher refuses everywhere else (npm runs
`--package-lock-only`). So `sca-scan.sh` runs `pip-audit --no-deps -r <file> -f
json` and audits **only the versions pinned with `==`** in a `requirements*.txt`.
Anything that would need resolution is REFUSED and NAMED as degraded, never
silently resolved:

- an **unpinned** `requirements*.txt` (any line without `==`) → `GO (DEGRADED)`,
  "requirements non épinglé — résolution refusée, posture lock-only";
- only `pyproject.toml` / `Pipfile` present, with **no lockfile and no**
  `requirements*.txt` → `GO (DEGRADED)`, "manifest(s) not supported in v1".
  These two declare version **RANGES**, and pinning a range needs a
  RESOLUTION — the one thing this posture refuses. Refused, and NAMED;
- `pip-audit` absent from PATH → `GO (DEGRADED)`, "pip-audit not installed",
  **never a block**;
- a run or network failure (OSV/PyPI unreachable, timeout) → `GO (DEGRADED)`.

**LOCKFILES ARE READ — `poetry.lock`, `uv.lock`, `Pipfile.lock`.** A project
carrying one of these and **no** `requirements*.txt` at all used to fall into the
"not supported" branch above and was never audited, while the run still reported
a Python status. It is now scanned: `py_lock_pins.py` TRANSLATES the lock into
pins (the versions are already exact — no network, no build, no resolution) and
hands them to the same single `pip-audit --no-deps` call. Both `default` and
`develop` are read from a `Pipfile.lock`: a dev dependency with a CVE is
installed on every contributor's machine and in most CI images.

Two outcomes have their own wording, because "could not read" and "read, nothing
to audit" are different facts:

- a lock that cannot be read (corrupt, or `tomllib` missing below Python 3.11) →
  `GO (DEGRADED)`, "résolution **ÉCHOUÉE** (pas refusée), rc=`<n>`", with the
  detail in `py-locks.log`. **Every** non-zero exit code lands here — the branch
  is a bound, not a list of codes;
- a valid lock holding no registry dependency → `GO (DEGRADED)`, "locks sans
  dépendance de registre". Nothing failed; there was simply nothing to pin.

**EXCLUSIONS ARE COUNTED AND WRITTEN ON THE NOMINAL PATH, SEPARATED BY MOTIVE.**
A lock entry that is not a registry package cannot be audited, and a scan that
drops it silently publishes `scanned` over an **amputated** perimeter. Every run
therefore logs both counts, even at zero — and only one of them degrades:

| Counter | What it is | Degrades? |
|---|---|---|
| `excluded_root` | the scanned project ITSELF (`uv.lock`'s `editable = "."` / `virtual = "."`) | **No** — it is not a dependency, so its exclusion is structural, not a coverage hole. `poetry.lock` and `Pipfile.lock` have no root entry at all, so this is always 0 for them |
| `excluded_dep` | any other non-registry source: `git`, `url`, `path`, `file`, or an `editable` outside the root | **Yes** — `GO (DEGRADED)`, "dépendance(s) à source non-registre EXCLUE(S) du périmètre — couverture BORNÉE" |

Merging the two would force a choice between a permanently degraded verdict on
every `uv` project and a silence on real holes. Separating them degrades exactly
when it should.

**No key needed**, but `pip-audit` needs network to reach OSV/PyPI; in an
air-gapped environment the block degrades cleanly rather than faking a GO — the
same discipline as every other scanner in this dispatcher. CI never invokes the
real tool: the Python suite (`.agents/security/sca-python.test.sh`) drives a
stub `pip-audit` on the PATH, so it is red-on-a-boxed-HIGH and degraded-without-
the-tool with **zero network**. The lock reader has its own suite,
`.agents/security/test_py_lock_pins.py` (`python -m pytest`).

**Waiver key for a Python finding** (`.agents/security/sca-waivers.json`):
`ecosystem: "pypi"`, `package: "<distribution name>"`, `version: "<pinned
version audited>"`, `class: "known_cve"`, `advisories: ["<PYSEC/GHSA/CVE id>"]`.

## MCP server audit — a human procedure, not a scanner

Unlike gitleaks/semgrep/trivy above, there is no tool to install here: the
kit ships zero MCP servers, and the audit trail below is a human discipline
that must exist before the first one is added, not a scan you run.

**Why:** MCP tool descriptions are third-party free text entering the
model's instruction channel every session, mutable server-side without a
commit — a server can change what it tells the model at any time, with no
diff for you to review.

**The full procedure and allowlist row format** live in
[`.agents/ref/MCP_REGISTRY.md`](.agents/ref/MCP_REGISTRY.md). Walkthrough
before adding any server:

1. **Pin the exact version** you're about to trust — never a range, never
   `latest`.
2. **Capture tool descriptions as evidence**: introspect the server at that
   pinned version and save its full set of tool descriptions to a file (e.g.
   `.agents/state/local/mcp-evidence/<name>-<version>.txt`).
3. **Append one row** to `.agents/state/gates/MCP_ALLOWLIST.md` — the
   auditing human only, never an agent. `<name>` is the PACKAGE identity
   extracted from the launch `args` (`figma-developer-mcp`), never the
   config key (`figma`):
   ```
   mcp <name>@<version> audit=pass by=<who> date=<date> evidence=<path>
   ```
4. **Re-audit on any version bump** — a new version is a new audit, not a
   carried-forward pin.
5. **Propagate to the other hosts** — after `.mcp.json` works, don't hand-copy
   it into each host's dialect:
   ```bash
   python .agents/bin/mcp_render.py --host all
   ```
   Read-only: it re-verifies every server's package identity and exact pin
   against the allowlist (parsed config, fixed-string comparison), then PRINTS
   the paste-ready `.vscode/mcp.json`, `.gemini/settings.json` and
   `~/.codex/config.toml` blocks. It refuses the whole run on any unaudited
   package or literal secret-shaped value (key named, value withheld), and
   lists non-npm servers (docker, uvx, url/sse) as `manual`. You paste;
   nothing is ever written to a file.

**What's mechanically enforced today:** agents cannot Edit/Write project MCP
configuration (`.mcp.json`, `.vscode/mcp.json`, `.codex/config.toml`,
`.gemini/settings.json`) on any of the four hosts — path guards deny it, and
Claude Code adds a second `permissions.deny` layer in `.claude/settings.json`.
And propagation via `mcp_render.py` is gated on parsed config against the
allowlist — the first mechanical check of the audit trail.

**What's NOT enforced (see `MCP_REGISTRY.md` § Residuals for the full list):**
install commands (`claude|codex|gemini mcp add`) are not gated against this
registry — the pin is verified by a human at audit time and by `mcp_render.py`
at propagation time, not at install; a server that mutates its descriptions
without a version bump is only caught at the next re-audit.

## The NVD API key (Java & Swift scans)

OWASP Dependency-Check — the scanner behind Maven, Gradle and Swift audits —
downloads the [NVD](https://nvd.nist.gov/) vulnerability database to your
machine. Since NVD API 2.0, an API key is effectively required: without one,
the first sync is heavily throttled and usually fails.

**Get a key (free, a few minutes):**
👉 **https://nvd.nist.gov/developers/request-an-api-key**

**Set it as an environment variable named `NVD_API_KEY`:**

```bash
# bash / Git Bash / CI
export NVD_API_KEY="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

```powershell
# PowerShell (current session)          # persistent (new sessions)
$env:NVD_API_KEY = "xxxxxxxx-..."       setx NVD_API_KEY "xxxxxxxx-..."
```

`sca-scan.sh` forwards it automatically to Maven (`-DnvdApiKey`) and to the
`dependency-check` CLI (`--nvdApiKey`). **Gradle is the exception** — the
plugin has no reliable CLI pass-through, so the project's `build.gradle` must
read it itself (see the Gradle section below).

**What a run PRINTS about the key — and the one thing to check if you exported
it before the forwarding fix.** The Maven line of a scan states PRESENCE only:
`(NVD_API_KEY set / cached DB)`, or `(NVD_API_KEY NOT set — first NVD sync may
fail/throttle / cached DB)`. A flag, never the value. **Until that fix it was
not.** The line was built from two shell expansions of the same variable, and
the second one renders the VALUE when the variable is non-empty, so the pair
printed `set` immediately followed by the key in clear — on stdout, on **every**
run of the Java gate with the key exported, no failure and no unusual state
required (measured with a sentinel: 1 occurrence). So: **if you have an archived
log of a Java scan run with `NVD_API_KEY` exported — a CI artifact, a terminal
capture, a pasted run — from before that fix, treat the key as disclosed and
rotate it** at the link above. The remedy for a disclosed credential is
rotation; it is not something a waiver can settle. The Swift branch never
printed such a line, so only the Java path is concerned.

**The bound, stated rather than widened.** The value is kept out of the scan's
own CONSOLE (the flag above) and out of the argv journals the test suites write
(`<REDACTED>`, and the redaction now matches the flag case-insensitively plus
any token equal to the key, so an unfamiliar spelling no longer walks through).
It is NOT stripped from whatever the underlying tools choose to write for
themselves: `mvn-dc.log` and `swift-dc.log` are Maven's and the CLI's own
output, and Gradle receives the key through your build file rather than through
`sca-scan.sh`. Treat those three as you would any build log that has seen a
credential.

Good to know:
- The **first sync takes several minutes** (full NVD download). After that the
  database is cached locally and scans run fast, even offline.
- **Offline / air-gapped — pre-seed the NVD database instead of the key.** Two
  environment variables, honoured by the Maven and Swift blocks:

  ```bash
  export NVD_OFFLINE=1                       # never contact the NVD
  export NVD_DATA_DIR=/opt/nvd-data          # a database you seeded yourself
  ```

  `sca-scan.sh` forwards them as `-DautoUpdate=false` / `-DdataDirectory=` to the
  Maven plugin, and as `--noupdate` / `--data` to the `dependency-check` CLI for
  Swift. Those two CLI flags were **confirmed against `dependency-check-cli`
  13.0.0**, and one of them is easy to miss: `--noupdate` appears in
  `dependency-check --help`, but `--data` appears **only** under
  `dependency-check --advancedHelp`. Check the advanced surface, not the bare
  one, before concluding a flag does not exist.

  **THIS MODE PUBLISHES `java: degraded` BY CONSTRUCTION, and that is the point.**
  Three named states:

  | State | Condition | Result |
  |---|---|---|
  | 1 | `NVD_OFFLINE` **true** **+** `NVD_DATA_DIR` | scan runs on your base → `GO (DEGRADED)`, "nvd: base hors-ligne, fraîcheur non vérifiée" |
  | 2 | `NVD_OFFLINE` **true**, no directory | nothing to match against → `GO (DEGRADED)`, "couverture Java NON GARANTIE" |
  | 3 | `NVD_OFFLINE` unset or **false** | normal online scan; no `nvd:` line is written |

  State 1 is not a defect being reported — it is a **bounded coverage** being
  declared. The scan is real; its freshness is not, and nobody downstream can
  tell the difference unless it is written down. State 2 is the dangerous one:
  with no database at all, an empty finding list means "did not look", not
  "found nothing".

  **`NVD_OFFLINE` is read as a TRUTH — these are the accepted values:**

  | You write | Read as | Note |
  |---|---|---|
  | `1`, `true`, `yes` | **offline ON** | case-insensitive (`TRUE`, `Yes` work) |
  | `0`, `false`, `no`, or unset | **offline OFF** | this is how you go back online |
  | anything else | **offline ON**, and **SAID** | you get a `nvd: NVD_OFFLINE='…' non reconnu` line and a log line naming the accepted values |

  The third row is deliberate and it is the only one worth explaining. An
  unrecognised value **fails closed to offline** — so a typo can never quietly
  put an air-gapped scan on the network — but it is never applied in *silence*:
  the run says which value it could not read and what it accepts instead.
  `on` and `off` are **not** in the vocabulary, on purpose: under a variable
  named `*_OFFLINE`, `off` is the one token that collides with the name
  (`NVD_OFFLINE=off` could mean "the value off" or "offline mode, off"), so it
  lands in the third row and gets named rather than guessed at.

  ℹ️ **Before the forwarding fix this was a real trap**: the forwarding tested whether
  the variable was *non-empty* rather than whether it was *true*, so
  `NVD_OFFLINE=0` turned offline mode **ON**. If you carry an older copy of
  `sca-scan.sh`, `unset NVD_OFFLINE` rather than setting it to `0`.

  ⚠️ **`NVD_DATA_DIR` is a PATH, and it does NOT follow the table above.** For a
  path, "non-empty" *is* the correct semantics: set it, or leave it unset. There
  is nothing to invert — `NVD_DATA_DIR=0` is not read as "off", it forwards a
  literal `-DdataDirectory=0`, which fails and lands in "produced no report →
  degraded". Use `unset NVD_DATA_DIR`, never `NVD_DATA_DIR=0`.

  **Gradle is the exception, and it is said rather than silently skipped**: the
  OWASP gradle plugin reads `autoUpdate` and the data directory from the BUILD
  SCRIPT, so neither variable is forwarded. The run logs that non-transmission
  explicitly — configure them in `build.gradle` instead.

## Per-ecosystem requirements

| Ecosystem | Scanner | Needs | Without it |
|---|---|---|---|
| **npm / JS** (Node, Angular, React, RN) | `npm audit` / `pnpm audit` | npm or pnpm on PATH + network to the registry. **No key needed.** | Module flagged `GO (DEGRADED)` — "no npm/pnpm on PATH" |
| npm supply-chain layer (optional) | `socket` CLI | `npm i -g socket` + account | Scan still runs; qualifier "supply-chain layer DEGRADED" |
| **Java — Maven** | OWASP Dependency-Check (invoked by coordinates, **no pom.xml change needed**) | `./mvnw` wrapper (preferred) or `mvn` on PATH + `NVD_API_KEY` or cached NVD DB | No tool → `GO (DEGRADED)`; no NVD data → `GO (DEGRADED)` — "produced no report (NVD DB missing? see mvn-dc.log)" |
| **Java — Gradle** | OWASP Dependency-Check **gradle plugin** (must be declared in the build, see below) | `./gradlew` wrapper (preferred) or `gradle` on PATH + plugin in `build.gradle` + key wired in the build | No tool → `GO (DEGRADED)`; plugin missing → `GO (DEGRADED)` — "produced no report (OWASP plugin missing in the build?)" |
| **Swift / iOS** (SPM, CocoaPods) | `dependency-check` CLI (experimental for SPM) | CLI installed + `NVD_API_KEY` or cached DB | Module flagged `GO (DEGRADED)` — "dependency-check CLI not installed" |
| **Python** (pip / Poetry / Pipenv / uv) | `pip-audit` run `--no-deps` (lock-only, **never resolves or builds**) | `pip-audit` on PATH + network to OSV/PyPI. **No key needed.** Audited: **PINNED** (`==`) `requirements*.txt` **and** the lockfiles `poetry.lock` / `uv.lock` / `Pipfile.lock`, translated into pins by `py_lock_pins.py` (TOML locks need Python ≥ 3.11 for `tomllib`; `Pipfile.lock` is JSON and needs nothing) | No tool → `GO (DEGRADED)` — "pip-audit not installed"; unpinned requirements → `GO (DEGRADED)` — "requirements non épinglé — résolution refusée"; **only `pyproject.toml`/`Pipfile`** (ranges, no lock) → `GO (DEGRADED)` — "manifest(s) not supported in v1"; unreadable lock → `GO (DEGRADED)` — "résolution **ÉCHOUÉE**, rc=`<n>`"; lock with no registry dependency → `GO (DEGRADED)`; a non-registry dependency (git/url/path) excluded → `GO (DEGRADED)` — "couverture BORNÉE". The project's **own root** entry in a `uv.lock` is excluded too, but it is **structural** and does NOT degrade |
| **Go · Rust · .NET/C# · PHP · Ruby** | **none — NOT scanned in v1** (manifest at the root looked at is named as not covered; csproj/sln down to depth 3) | — | Module flagged `GO (DEGRADED)` — "`<eco>: ecosystem not covered in v1 (<manifest> present)`", on the bare form, the hooks AND `/audit` (`--all-modules`, per module and on its no-module path). A repo carrying ONLY these manifests still answers "SCA: no known ecosystem detected." (bare form) / "… in any module." (`/audit`), exit 2 **(exit 0 under the hooks' `SCA_CHANGED_ONLY=1`, unchanged)** — both preceded by the `COVERAGE DEGRADED` line. **Not named**: a manifest in a sub-folder that is not a discovered module (`package.json` at root + `services/api/go.mod`) — the GO says nothing about it; and a hook run whose diff touches only such a manifest, throttled before detection. `govulncheck` (Go) and `dotnet list package --vulnerable` (.NET) are outside v1 |

Socket scans are bounded to 60 seconds so an optional external service cannot
stall the security pipeline. Set `SCA_SOCKET_TIMEOUT_SECONDS` to an integer
from 1 to 900 to change that limit. A timeout, a Socket failure, or a missing
GNU `timeout` command marks only the supply-chain layer as DEGRADED; the other
dependency scans continue, and no report from an earlier run is reused.

Multi-module projects: Maven/Gradle reactors are scanned **once from the
aggregator root** (Maven uses the `aggregate` goal → one consolidated report);
npm workspaces collapse onto their declaring root. A frontend and a backend in
sibling folders are always two separate audit modules.

## Gradle projects: two things to add to the build

The gradle scan runs `dependencyCheckAnalyze`, which only exists if the
project applies the OWASP plugin. In `build.gradle`:

```groovy
plugins {
    id "org.owasp.dependencycheck" version "10.0.4"
}

dependencyCheck {
    nvd { apiKey = System.getenv("NVD_API_KEY") }
    format = "JSON"
}
```

Without this, the module appears in the audit as `GO (DEGRADED)` with the
reason "OWASP plugin missing in the build?" — honest 0% coverage, never a
silent pass. (Maven needs nothing in the pom: the plugin is invoked by
coordinates.)

## How gaps show up (never silently)

The scan never hides a module and never fakes a clean result:

- A dependency manifest of a **scanned** ecosystem (npm, Maven, Gradle, Swift,
  Python) always marks it as **detected**, even when the scanner is unavailable —
  you get `GO (DEGRADED)` with an explicit reason, not `NO-ECOSYSTEM`. For the
  five ecosystems not covered in v1 (Go, Rust, .NET/C#, PHP, Ruby) the manifest is
  NAMED but does NOT count as detected: alone, it still yields
  `SCA: no known ecosystem detected.` / `… in any module.`, exit 2.
- Every degradation reason flows into the console (`COVERAGE DEGRADED: …`),
  `summary.json` (`degraded_reasons`), and the HTML audit report (verdict
  column + "Methodology & limits → Gaps").
- The `COVERAGE DEGRADED:` line is also printed on both
  no-ecosystem paths (bare form, `--all-modules`) — a repo with no manifest prints
  the trivy reason before `SCA: no known ecosystem detected.`, in the Stop hook too
  — **except on the no-module path of `--all-modules`, which writes no
  `summary.json`: there the reason lives on the console and in `.degraded` only,
  never in the HTML Gaps list**.
- Scanner logs land next to the reports: `.agents/state/local/sca-reports/modules/<module>/`
  (`mvn-dc.log`, `gradle-dc.log`, `swift-dc.log`).
- Under `--all-modules`, a module run that exits outside {0,1,2}, or with 2 without the exact line
  `SCA: no known ecosystem detected.`, or with 1 whose run says `no verdict obtained` (its lock
  busy, its run cut short, its reports directory not writable), is `ERROR` in
  `modules/summary.json`: gating even when the module is protected, `counters {}`, reason `module
  run exited rc=<n> — no verdict obtained`, its pivot removed — except under rc 1, where the pivot
  is LEFT: a busy lock belongs to another run, and `/audit`'s HTML then reads that EARLIER pivot
  as if current (bound, « The reports lock »). The run is NO-GO exit 1, line `SCA GATE all-modules
  (effective, waivers applied): NO-GO — module <slug> exited rc=<n>, no verdict obtained
  (fail-closed)`. When the module
  log cannot be created (`mktemp` refused in `modules/`), a raw 1 cannot be read: it is `ERROR`
  too, gating even in a protected module, with that same line (read as a raw 1, it would give
  `TRACKED-NOT-GATING`, GO exit 0 — measured) — the closed direction: that protected module's real
  findings then gate as well.
- A module run that exits 1 on `waiver_filter`'s rc 3 line (`SCA GATE (effective, waivers
  applied): NO-GO — waiver_filter rc=3, …`: a scanner report present but unreadable, truncated or
  of an unrecognised shape) is `ERROR` too, gating even when the module is protected, `counters
  {}` (measured before: a
  protected module with a truncated `pip-audit.json` read `TRACKED-NOT-GATING`, GO exit 0). Its
  line is `SCA GATE all-modules (effective, waivers applied): NO-GO — module <slug>: no fresh
  effective verdict (fail-closed)` — never the `exited rc=<n>, no verdict obtained` one, so
  `sca-watch.sh` gives the « rapport de scanner illisible » motif alone. The exception covers a
  protected module's FINDINGS; an unread report is not a finding. Only rc 3: `waiver_filter`'s
  rc 2 (an invalid `SCA_GATE_LEVEL`, an unreadable register) in a protected module stays
  `TRACKED-NOT-GATING` (open question to the pilot). **Residue, said (denial of
  service):** an rc 3 that is DETERMINISTIC on vendored code — npm's `E401`/`ENOTFOUND` envelope
  behind an internal mirror, which `waiver_filter.py` keeps rc 3 — now keeps red, for as long as
  that envelope comes back, a project whose only npm module is protected, while a readable
  CRITICAL in that same module stays `TRACKED-NOT-GATING`.

### The reports lock

One `sca-scan.sh` at a time owns `.agents/state/local/sca-reports/` (`mkdir .lock`; the owner
writes pid, host and start identity in one `printf`). A second scan waits, then gives up.

- **Liveness** is `kill -0`: only `No such process` reads dead; EPERM or any unknown text reads alive.
- **Start identity**, used ONLY against a recycled pid: on Linux field 22 of `/proc/<pid>/stat`;
  elsewhere `ps -o lstart=` under `LC_ALL=C TZ=UTC0`. An alive owner whose start cannot be
  described is never taken over.
- **Host**: `uname -n`, never `$HOSTNAME`; on Linux followed by the pid namespace
  (`readlink /proc/self/ns/pid`, e.g. `pid:[4026531836]`). A lock written from another hostname,
  or from another pid namespace on Linux, reads foreign: never taken over;
  a DEAD namespace's inode is reused, as bounded below.
- **Unreadable owner**: 40 s grace, reset when the `.lock` changes date (`-nt` or `-ot`, then
  `touch -r`).
- **Wait**: `SCA_LOCK_WAIT_SECONDS`, 600 by default, 30 under `SCA_CHANGED_ONLY=1` — so a hook
  left at its default never takes over a `.lock` without owner (a `SCA_LOCK_WAIT_SECONDS` set in
  its environment applies to hooks too: 40 or more can reach the 40 s grace). Beyond it: NO-GO exit 1, nothing written but the
  audit line `"reason":"lock-busy"`. A run whose lock step is cut short (an arithmetic error)
  is NO-GO exit 1, audit `"reason":"aborted"` — never a scan without the lock. A reports
  directory the run cannot write, with no `.lock` in it, is NO-GO exit 1 AT ONCE, line `SCA GATE
  (effective, waivers applied): NO-GO — reports directory not writable, no verdict obtained
  (fail-closed)`, no audit row — never the wait of a held lock. `/audit`'s
  HTML reads two `sca-scan.sh` audit rows — the last of either mode (`scan`, `all-modules`) and
  the last of the mode it renders (`all-modules` when `modules/summary.json` exists, else
  `scan` of `root`); the rows of `sca-watch.sh`, gitleaks and semgrep never count. `lock-busy`
  or `aborted` on either turns its badge NO-GO and says the rows date from the earlier summary
  (the rendered mode alone left a mono lock-busy after an
  `--all-modules` GO, or the reverse, under the GO badge); the dashboard carries the row's
  `reason`. A run cut by TERM (a Bash tool timeout, GNU `timeout`) or HUP writes ONE audit row
  `"reason":"aborted"` in the mode it holds the lock for (`scan` with its sanitised module, or
  `all-modules`), before it releases the lock, rc 143 / 129;
  only the lock holder writes it — a re-entered module run, a waiter or a thief never does. Bash
  runs the trap between commands only: a TERM sent to the process ALONE waits for its foreground
  command — the scanner of a single-module scan, the module run under `--all-modules` — the lock
  held until it ends, then the `aborted` row is the last; a KILL that follows leaves the lock and
  writes no row. A TERM to the whole process group is immediate. Measured before this trap (macOS; `(f4)`
  of `sca-scan-lock.test.sh`): a TERM to that process alone killed it at once and released the lock WHILE
  its module still ran, and that module then wrote its reports and its row without the lock.
  **Open question to the pilot:** a TERM to the process alone now writes only at the end of its
  foreground command (the scanner, or the module in progress), and holds the lock until then. A run killed by KILL or INT (Ctrl-C) still
  writes no audit row: under a summary that is not NO-GO, a module whose `modules/summary.json`
  counters differ from its pivot's turns the badge NO-GO, line `module pivot(s) <slug> changed
  after the summary`. Not seen: a run killed so before any pivot changed, or
  whose new pivot carries the same counters — the earlier GO stands. Bound: a TERM or HUP that
  lands after the run's own audit row adds the `aborted` row after it — the last row then reads
  NO-GO, the closed direction.
- **Remedy**, the same text as the log: owner `held` (alive and described) → "re-run when it
  ends; do not remove the lock"; owner `undescribed` (alive, start not describable) → "remove the
  lock only if pid <n> is not a sca-scan.sh: `rm -r .agents/state/local/sca-reports/.lock`"; any
  other state → "if no sca-scan.sh is running, remove the orphan lock:
  `rm -r .agents/state/local/sca-reports/.lock .agents/state/local/sca-reports/.lock.steal`".

Bounds, said and not fixed:
- same hostname in another pid namespace (a `--uts=host` container, or the repo mounted in a
  container that carries the host's hostname): CLOSED on Linux, the namespace is in the host line
  — measured in a local container only (`(c8)`, `unshare`; GitHub's runners not measured). Still
  open: where `/proc/self/ns/pid` cannot be read (the bare hostname: the owner reads dead and is
  TAKEN OVER), and between two machines that share a hostname and the repository. A `.lock` left
  on Linux by a version before this one reads foreign: never taken over, the removal remedy
  applies;
- the pid-namespace inode of a DEAD namespace is reused (measured: successive containers all
  `pid:[4026532380]`): a restarted container may read an earlier container's lock as its own
  (taken over through `kill -0` and the start identity, safe) or as foreign (the removal remedy)
  — never a live holder's: an inode in use is not reissued;
- a SIGKILL of the `sca-scan.sh` bash process alone leaves its `waiver_filter.py` alive: it can
  still write the pivot after another run has taken the lock over;
- parallel sessions on the same root wait up to 30 s per hook (`SCA_CHANGED_ONLY=1`) for each
  other's lock;
- a zombie owner reads `held` until it is reaped;
- under `--all-modules`, a module run that exits 1 on its `no verdict obtained` line LEAVES its
  pivot (`ERROR` above): `modules/summary.json` ignores it, but `/audit`'s HTML
  (`audit_report.py`) reads that earlier pivot — its findings listed as active, counted in the
  « Active findings » tile, and no line saying the module obtained no verdict (that line follows
  only a last audit row `lock-busy` or `aborted`, or a summary that is not NO-GO whose counters
  differ from a pivot's — and this summary is NO-GO); the badge says NO-GO. Re-run the scan before
  reading the HTML;
- GNU `timeout` (a TERM to the run, then to its group) no longer cuts `cleanup()` short: it
  opens on `trap '' TERM HUP`, so a second TERM or HUP that lands while it runs is IGNORED.
  Re-measured on this form (macOS, GNU coreutils 9.11, bash 3.2.57 and 5.3.15, 6 runs) — `.lock`
  removed, no `scalockref.*` left, the `aborted` row written; before the TERM trap, `.lock` was
  left in 4 runs of 5 and a `scalockref.*` in 5 of 5 (the next run took the dead pid over within
  a second, no false verdict). A second TERM landing INSIDE cleanup (its `$(date)` slowed, arm
  `(f5)`) cut it before that `trap ''` line: `.lock` and the witness left, no row. A KILL still
  cuts it. Linux: not measured. Under bash 3.2, TERM then KILL during the re-judgement, or a signal between
  `mkdir .lock.steal` and `steal_held=1`, leaves the mutex: the remedy above applies;
- a replacement `.lock` carrying exactly the same date as the first is not seen as new;
  `-nt`/`-ot` compare to the second;
- MSYS, and any sandbox that refuses `ps` (sandbox-exec, some Codex hosts): the owner is
  undescribable, never taken over. Not measured: the text of `kill -0` under MSYS and under a
  localised glibc, WSL, `hidepid`;
- the Linux branch has NO blocking witness of the btime jump it closes: `(c7)` checks the form
  only, and its mutant runs in a local container, not in CI;
- `sca-watch.sh` writes its log and reads the pivot outside the lock.

## Shell correctness scan (shellcheck) — the gap between `bash -n` and semgrep

`bash -n` reads SYNTAX and nothing more: it accepts `cd "$X"` with no guard, an
unquoted variable, a `$?` that refers to something other than what you think.
`semgrep` reads named SECURITY patterns, not shell correctness. Neither sees a
`cd` that fails and leaves the script running in the wrong directory — measured
on this repo, **7 sites, including `core-scripts/verify.sh` itself**.

**Install `shellcheck`:**

```bash
# macOS
brew install shellcheck

# Linux (Debian/Ubuntu)
sudo apt-get install -y shellcheck

# Linux / any OS with a Haskell-free binary release
# https://github.com/koalaman/shellcheck/releases  (static amd64/arm64 tarballs)
```

```powershell
# Windows
choco install shellcheck        # or: scoop install shellcheck
```

**Where it runs** — two places, no new CI step:

| surface | when |
|---|---|
| `PostToolUse(Edit\|Write)` hook | at every edit — silent when clean, so a bad `cd` is caught in seconds, not at the gate |
| `core-scripts/verify.sh` | the pre-push gate, on every tracked shell file — **in the kit's mode only** |

**In an adopting project the pre-push gate does not run it.** There
`verify.sh`'s three kit steps — pytest, the bash suites, this scan — give way to
ONE step, `.agents/bin/porte_adoptant.py`, which plays only `bash -n` (syntax,
nothing more — the gap this section opens on) on the shell scripts the hook
registries cite and on the shell files of `.githooks/`. The `PostToolUse` row
does not depend on the mode.

**The configuration is a MEASURED arbitration, not a tool default.** `shellcheck`
**0.11.0** at severity `style` returns **574 findings on the 78 tracked `*.sh`
files of the WORKING TREE** (re-measured 2026-09-13; the previous « 582 » had
aged). **A scan count carries THREE coordinates — population, version, tree
state — and a bare number is reproducible by none of them.** Measured here: the
scan's own perimeter is **80** files (`git ls-files` plus two extensionless files
brought in by their shebang) and returns the SAME 574, finding for finding — the
two added files carry none; the same 80 files return **613** under 0.10.0; and
the « 573 » first written here was the count at `787b384`, one `SC2016` before
this very fix added one. Wired as-is
it would be red on day one and disarmed within a week — friction without the
benefit. The scan therefore runs at severity `warning` and above, with a **closed
exclusion set, each entry carrying its measured reason**:

| excluded | n | why |
|---|---|---|
| `SC1010` | 17 | **false positive** — `tasks done T-…` passes `done` as a CLI argument, not a loop terminator |
| `SC1087` | 2 | **false positive** — `"$L[[:space:]]"` is a character class in a `grep` pattern, not an array |
| `SC2034` | 53 | "unused variable" — false in a sourced file |
| `SC1112` | 6 | typographic apostrophe inside a French comment |

`SC2015` (**372** under 0.11.0, **379** under 0.10.0 — `A && B \|\| C`) and
`SC2016` (**76**) fall below `warning` and are the repo's own idiom; including
them would drown the signal. Counts re-measured 2026-09-13 on the 78 `*.sh`
files of the working tree.

**Without `shellcheck` on PATH:** `COVERAGE DEGRADED` on stderr, exit 0. Never a
false clean, never a block — same discipline as gitleaks and semgrep.

**Prerequisite — a UTF-8 locale:** `locale -a` must list one of `C.UTF-8`,
`C.utf8`, `en_US.UTF-8` or `en_US.utf8`. The scan sets it for the tool's call
only, spelled verbatim and verified by `locale charmap`, because under locale C
`shellcheck` 0.10.0 (glibc) crashes while writing a non-ASCII file name
(`hPutChar`) and truncates its output. Without one of the four, the inherited
locale stays, and a truncated output is refused — never turned into a verdict.

**A tool failure REFUSES, it does not degrade:** `ECHEC EXECUTION` (tool rc ≥ 2)
and `SORTIE INCOMPLÈTE` (anything on the tool's stderr, or rc 1 with no output
line) exit **1**, or **2** under `--hook`, so the model reads it. This differs on
purpose from semgrep, which degrades to exit 0 on a tool failure. Two triggers
beyond the locale: a file name that is not valid UTF-8 crashes the tool even
under `C.UTF-8` (measured on 0.11.0) — rename the file; a wrapper (npm, snap)
that writes on stderr on success triggers the refusal at every call — call the
binary directly.

**An unread perimeter REFUSES too — tree scan only.** Without file arguments
(and under `--hook` without a payload), the scan reads its population from
`git ls-files -z` through a temporary file, and it refuses — exit **1**, or
**2** under `--hook`, never `propre` nor `rien à mesurer` — when the
perimeter was not read in full:

- `git ls-files` fails (`ECHEC EXECUTION (git ls-files rc=…)`): outside a git
  repository, or a repository owned by another user (git: *dubious
  ownership*, rc 128) — remedy `git config --global --add safe.directory
  <root>`;
- `mktemp` fails (`ECHEC EXECUTION (mktemp a échoué, TMPDIR=…)`): with a GNU
  `mktemp` (Linux, Git Bash, Homebrew coreutils), a `TMPDIR` that is missing,
  not writable or not searchable — measured; one that is writable and
  searchable but unreadable does NOT fail. The message names the `TMPDIR` it
  read and never blames git; targeted mode refuses the same way when its own
  temporary file cannot be created. Bound: macOS's own `/usr/bin/mktemp`,
  called without a template as here, ignores `TMPDIR` (measured: rc 0, file
  under `/var/folders/…/T/`) — there, `TMPDIR` never leads to this refusal;
- a tracked `*.sh` is absent from disk (sparse-checkout outside the cone, an
  `rm` without `git rm`): `PÉRIMÈTRE INCOMPLET — N fichier(s) *.sh SUIVI(S)
  ABSENT(S) du disque — NON lus`, the first 10 named, no verdict. A `propre`
  over the files that remain would read as the whole population. Bound: an
  absent tracked file WITHOUT extension has no shebang to read and is not
  counted.

Targeted mode (`shellcheck-scan.sh <file…>`) and `--hook` with a payload
never read `git ls-files`: they name their files, so of the three refusals
above only the `mktemp` one reaches them (the tool refusals of the previous
paragraph still apply). Temporary files are removed on every exit — verdict
or refusal — and on INT / TERM (exit 130 / 143); a TERM received while
`shellcheck` runs waits for it to finish, because bash defers a trap until
the foreground command completes. Witnesses:
`.agents/security/shellcheck-scan-arbre.test.sh`, cases (u) to (z) and (i) —
TERM is measured by (z); INT by (i), in the foreground and in series only
(under the `&` of a local pool INT arrives ignored and (i) is a named SKIP).
Case (i) proves the cleanup on INT, not the scanner's INT trap line: bash
runs the EXIT trap on INT, so (i) stays green without that line.

**Adding an exclusion** is a `# shellcheck disable=SCxxxx` on the line, **with a
sentence saying why**. An exclusion without a reason is a back door.

## Environment variables — the complete list

Every knob the scanners read, in one place. **Six of them were documented
NOWHERE until 2026-09-09** — you could not tune a lever you had no way to
discover. The worst of those was `SCA_GATE_LEVEL`: it decides what **blocks**.

The list below is not maintained by hand. `.agents/evals/test_security_env_documented.py`
**derives** it from `.agents/security/*.sh` and reddens when a public variable is
added without being named here — which is exactly how the gap opened in the first
place.

### The one that matters most: `SEMGREP_CONFIG`

By default the SAST runs on the **offline ruleset shipped with the kit**:
**31 hand-written rules** — python 5 · javascript 3 · typescript 5 · yaml 3 ·
bash 3 · go 3 · ruby 3 · php 3 · **java 2 · csharp 2 · rust 2**. The three
javascript rules also read typescript; typescript adds two Angular rules
(`bypassSecurityTrust*` on a non-literal value, indexed call included; a
non-literal `innerHTML`/`outerHTML`, `insertAdjacentHTML` or
`Renderer2.setProperty(el, 'innerHTML', …)`), both `ERROR`, so the post-edit
hook blocks a `.ts` edit that introduces one. A literal, a constant and a value
passed through `sanitizer.sanitize(SecurityContext.HTML, …)` are exempt; a
reviewed exception is written `// nosemgrep: <rule id>` on the line. The two counts in
this section are held to the ruleset by `.agents/security/semgrep-scan.test.sh`
arm (aj).

That is a **FLOOR, not an audit**. It is enough not to be blind; it is not enough
to call your code audited. For real coverage on your stack, point at the
community registry — it needs network:

```bash
SEMGREP_CONFIG=p/security-audit bash .agents/security/semgrep-scan.sh
```

The scan does not lie about what it covers: it **derives** the covered-language
set from the ruleset itself and prints `COVERAGE DEGRADED` for anything it cannot
map to file extensions. The gap between 31 rules and an audit is a limit of
**capability**, never a false claim.

### The table

| Variable | Default | What it does — and when to touch it |
|---|---|---|
| `SEMGREP_CONFIG` | `.agents/security/semgrep.yml` | The SAST ruleset. The default is offline and thin; `p/security-audit` gives community coverage. **The highest-yield knob here.** |
| `SEMGREP_TIMEOUT` | **45 s in hook mode · 180 s in a full pass** | Execution wall. *Two different defaults* depending on the mode — a timeout yields `COVERAGE DEGRADED`, never a false `clean`. Raise it on a large repo. In a full pass it also bounds the read of the git objects (index/commit); at the hook Stop that read has its own fixed 8 s. |
| `SCA_GATE_LEVEL` | `high` | **What BLOCKS.** `high` or `critical`. Move to `critical` if HIGH noise stops you shipping — knowing you are narrowing the gate. **Any other value → NO-GO, fail-closed** (exit 1): `waiver_filter.py` rejects it, so there is no fresh effective verdict — the stale `effective-verdict.json` is removed and the reason is named under `COVERAGE DEGRADED`. In a **protected** module (a path this project may not edit), `--all-modules` turns that NO-GO — this rc 2 fail-closed included — into rc 3 **`TRACKED-NOT-GATING`** in `modules/summary.json`: tracked, not blocking (an invalid `SCA_GATE_LEVEL` or an unreadable register stays TRACKED there: open question to the pilot) — never a module run that obtained no verdict at all (lock busy, run cut short, a scanner report unreadable — `waiver_filter` rc 3, below: `ERROR`, gating). Python absent → **DEGRADED, announced, never a block**: exit code unchanged (0), the last line reads `SCA GATE (effective, waivers applied): GO (DEGRADED — no effective verdict)`, the audit row says `"verdict":"DEGRADED"`, the stale `effective-verdict.json` is removed and `COVERAGE DEGRADED` names `waiver_filter: not run (python absent)`. Under `--all-modules` without Python, module discovery is not run: `COVERAGE DEGRADED` names `module discovery: not run (python absent)`, the last line and the audit row say DEGRADED, exit 0, and the stale `effective-verdict.json` and `modules/summary.json` are removed. **A scanner report present but unreadable, truncated, empty or of a shape its parser cannot read → NO-GO, fail-closed**: `waiver_filter.py` exits rc 3 (not the rc 3 `TRACKED-NOT-GATING` of `--all-modules`), `sca-scan.sh` exits 1 and `COVERAGE DEGRADED` names the report (`waiver_filter: report <name> unreadable/malformed (<Class>)`); in a protected module, under `--all-modules`, it is **`ERROR`, gating** — no verdict, not a finding (before: tracked, not blocking): rc 3 is ERROR, rc 2 is TRACKED. **A readable report of an unrecognised shape → NO-GO too**, same rc 3 and line `(UnrecognisedShape)`: npm `[]`/`{}`, a non-list `dependencies`, trivy `"Results": {}`, npm's registry-unreachable envelope without a `code` (offline with a lockfile is NO-GO: rerun online), and the MIXED forms whose parser would leave a list unread — npm `vulnerabilities` beside `advisories` (even empty), socket `alerts` and `issues` both non-empty, npm `error` beside its findings object unless its code is `ENOLOCK`/`ERR_PNPM_AUDIT_NO_LOCKFILE`. Two forms only are DEGRADED, never a block of their own: npm `ENOLOCK` / pnpm `ERR_PNPM_AUDIT_NO_LOCKFILE` alone (nothing audited) and socket with no `alerts`/`issues` list whose keys ALL belong to the closed list `ok`, `message` (supply-chain layer not read), one `COVERAGE DEGRADED` line each, rc left to the other reports. A socket object with neither list and ANY other key (`results`, `data`, …) is rc 3 `(UnrecognisedShape)`, NO-GO: the real output of `socket scan create --json` is NOT measured, so an unknown form stays NO-GO until it is. Bound: the check judges the envelope only; a no-lockfile `error` beside a findings object is parsed (a HIGH gates, an empty object is a GO with no DEGRADED line); an unknown key beside a socket `alerts` or `issues` list is not read; an absent severity reads `low` (`norm_sev`) in npm, dc and trivy. Reports are purged at the start of every run (and of every module), except `trivy-image.json`, written before the gate by the project's image scan: a stale unreadable one keeps the gate red, a stale readable clean one is read as today's — its freshness is its producer's. The audit row writes `gate_level` and the module slug sanitised (any byte outside `A-Za-z0-9._/ -` becomes `?`). |
| `SCA_CHANGED_ONLY` | `0` | At `1`, skip the scan unless a dependency manifest moved vs HEAD. Useful in a fast loop. |
| `SCA_LOCK_WAIT_SECONDS` | `600` (30 under `SCA_CHANGED_ONLY=1`) | How long a scan waits for the reports lock. A decimal 0–3600 without a leading zero; any other value → default + a log line. Beyond it: NO-GO, fail-closed (see « The reports lock »). |
| `SCA_LOCK_OWNER` | — | Internal, do not set: it marks a child run of the lock owner. |
| `SCA_ROOT_ONLY` | `0` | Limit to the root module instead of sweeping every module. |
| `SCA_AUDIT_DEV_DEPS` | opt-in file | Audit `devDependencies` too. Explicit override of the opt-in file. Previously, turning it on under macOS's `/bin/bash` 3.2 killed the npm/pnpm audit before it ran (empty scope array + `set -u`) and the gate read `GO` on no audit at all; fixed, and pinned by `.agents/security/sca-scan.test.sh`. |
| `SCA_SOCKET_TIMEOUT_SECONDS` | `60` | Network wall of the supply-chain layer (1–900). |
| `SCA_WATCH_MODE` | `scan-only` | `scan-only` scans and writes the audit log, never invoking Claude. `orchestrate` starts a headless run on a NO-GO. A fail-closed NO-GO is said as `verdict SCA non obtenu (fail-closed config)`, never as findings — in the orchestrator prompt, the scan-only line and the digest alike. An unreadable scanner report (`waiver_filter` rc 3) is said as `verdict SCA non obtenu (rapport de scanner illisible — voir COVERAGE DEGRADED)`, whose remedy is to rerun the scanner, not to fix the configuration; when both causes are present, both are named. A run cut short or a lock held (`no verdict obtained`) is said as `verdict SCA non obtenu (run de module interrompu ou verrou occupé — relancer le scan)`, with a digest that carries no counters. A reports directory the watch cannot write stops it BEFORE the scan, in both modes: `verdict SCA non obtenu (dossier de rapports non inscriptible — le rendre inscriptible, puis relancer)`, exit 1, nothing scanned, nothing recorded — neither log, audit row nor digest can be written there (before, with no earlier log the watch said « Findings », with one it gave the run motif, whose remedy cannot work); inert under uid 0. |
| `GITLEAKS_TIMEOUT` | `90` | Wall of the **fallback grep** — the one that runs when `gitleaks` is not installed. |
| `GITLEAKS_FALLBACK` | — | Force the fallback path even when `gitleaks` is present (used by the suites). |
| `GITLEAKS_FALLBACK_MAX_FILES` | `5000` | Above this, the fallback **DECLINES and says so** rather than scanning half the tree. |
| `SUBMODULE_SCAN_DEPTH` | `8` | Git submodule recursion depth, for gitleaks and semgrep alike. |
| `NVD_API_KEY` | — | OWASP Dependency-Check key (free). See § *The NVD API key*. |
| `NVD_DATA_DIR` | — | Where the local NVD database lives. |
| `NVD_OFFLINE` | — | Run against a pre-seeded NVD database, no network. |

## Quick checklist before a first real `/audit`

1. `NVD_API_KEY` exported (Java/Swift in the project? then yes) — link above.
   Air-gapped instead? `NVD_OFFLINE=1` + `NVD_DATA_DIR` — and know that this
   publishes `java: degraded` by construction. To go back online: `NVD_OFFLINE`
   accepts `0`/`false`/`no` (or unset it); `NVD_DATA_DIR` is a **path**, so
   **unset** that one — never `NVD_DATA_DIR=0`. Full value table above.
2. Java backend using Gradle? Add the OWASP plugin + key wiring to the build —
   `NVD_OFFLINE`/`NVD_DATA_DIR` are **not** forwarded to Gradle.
3. Optional: `socket` CLI installed for the npm supply-chain layer.
4. Expect the **first** Java scan to be slow (NVD download); later runs are fast.
5. Python project? `pip-audit` on PATH, and **Python ≥ 3.11** if you rely on
   `poetry.lock` / `uv.lock` (`tomllib`). Below that, those two are reported as
   an unreadable lock — degraded and NAMED, never skipped in silence.
   `Pipfile.lock` is JSON and works on any version.
6. Want the watch to be PERIODIC? `.agents/security/sca-watch.sh` is the
   scheduled entry point (cron, or the `sca-watch` job in
   `.github/workflows/eval-nightly.yml`). Invoke it as `bash <path>`, never as
   an executable — every `.sh` here is mode `100644` in the git index, so
   running the file on a POSIX checkout dies with `Permission denied`.
   Its exit codes are `0` GO · `1` NO-GO · `2` no ecosystem · `3` **DEGRADED,
   meaning no verdict was obtained** — treat `3` as "not measured", never as
   clean. In its digest, `Active findings at gate: **?**` means the same thing:
   NOT MEASURED, not zero.
7. Read the report's "Methodology & limits" section: a GO with gaps is not a
   full GO.
