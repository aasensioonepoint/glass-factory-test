# `.agents/` — layout map

One rule: **what the kit ships is separated from what a run produces.**

Before, everything lived flat in `.agents/index/`: the scripts, the hand-maintained
reference data, the generated index, the task board, and the throw-away views — all
mixed. You could not upgrade the kit in a project without stepping on that project's
own state, and you could not tell at a glance whether a file was yours to edit.

```
.agents/
├── kit.lock    CONTRACT — kit and contract versions (JSON, format 1, three keys); written by `cadre init` (reserved), to be read by `cadre hook`'s lockstep (T-00000731, not shipped yet). Travels with the kit's values until `cadre init` rewrites it — and a kit update pulled after `cadre init` brings the kit's values back (not yet handled).
├── bin/        TOOLING — kit-shipped code. Tests are colocated.
├── ref/        REFERENCE — fixed data, kit-shipped, project-editable.
├── state/      GENERATED — everything the kit writes for THIS project.
│   ├── local/  THROW-AWAY — regenerable views, run log, SCA reports. Git-ignored.
│   └── events/ CANAL-A EVENT STREAM — also git-ignored (pilot decision, see below).
├── security/   SCA engine, policy, waiver register.
├── skills/     Host-agnostic skill definitions.
├── ui/         Dashboard front end — ESM + CSS, zero build, served by `bin/dashboard.py`, never run standalone.
└── evals/      Cross-host parity tests.
```

## Who writes what

| Path | Written by | Tracked | Edit by hand? |
|---|---|---|---|
| `bin/build_index.py` · `tasks.py` · `ledger.py` · `specs.py` · `migrate_layout.py` · `sync_template.py` · `mcp_render.py` · `events.py` · `dashboard.py` · `dashboard_daemon.py` · `dashboard_readers.py` · `project_init.py` · `wrap.py` | humans | ✔ | yes — it's the tooling |
| `ref/DOCS_REGISTRY.md` · `TOKEN_BUDGETS.md` | humans (+ `skills-resolver` for the `installed:` ledger) | ✔ | yes |
| `ref/CONVENTIONS_<stack>.md` | humans + `custom-docs-curator` | ✔ | yes |
| `ref/MCP_REGISTRY.md` | humans | ✔ | yes |
| `state/index/CODEBASE_INDEX.md` | `build_index.py` + `indexer` (Role/Owner cells only) | ✔ | only the Role/Owner cells |
| `state/index/SYMBOLS.md` · `SYMBOLS_*.md` · `INDEX_DELTA.json` | `build_index.py` | ✔ | **no** |
| `state/index/CUSTOM_DOCS.md` | `custom-docs-curator` | ✔ | no |
| `state/board/` (`TASKS.json` OR `tasks/*.json`) | `tasks.py` only | ✔ | **never** — use the CLI |
| `state/memory/LEDGER.json` | `ledger.py` only | ✔ | **never** — use the CLI |
| `state/specs/SPECS.json` | `specs.py` only | ✔ | **never** — use the CLI |
| `state/events/YYYY-MM-DD.<host>.<pid>.jsonl` | `events.py`'s `emit()`, called from hooks/CLIs (canal A) | ✗ | **no** — one file per writer process, never hand-edit or merge by hand |
| `state/events/digest/YYYY-MM.json` | `events.py --compact` (folds day-files older than 30 days; counts only) — **legacy: no-op once `state/local/events.db` exists, the daemon folds into the `digests` table instead** | ✗ | no |
| `state/local/events.db` | the **dashboard daemon ONLY** (`event_store.py`'s 5 s ingest tick) | ✖ | **never** — single-writer SQLite; git-ignored and regenerable from the spool |
| `state/project.json` | `project_init.py` only | ✗ | **never** — GIT-IGNORÉ, une identité se génère ON PLACE dans chaque repo et ne se copie jamais (un exemplaire hérité d'un clone/fork se supprime puis se ré-init) |
| `state/gates/AUDIT_LOG` | `skills-resolver` (append) | ✔ | no |
| `state/gates/MCP_ALLOWLIST.md` | the auditing human only (append) | ✔ | yes — human audit rows only, never agents or a gate (agent writes refused by protect-paths) |
| `state/gates/KIT_CODE_PROTEGE` | the pilot only, by hand — its presence arms the kit-code guard (`bin/kit_code_guard.py`); shipped ABSENT | ✖ | pilot only — agent writes refused by protect-paths |
| `state/gates/KIT_CODE_AUTORISE` | the pilot only — one grant per line, `<path\|prefix/> T-<NNNNNNNN or ULID> <YYYY-MM-DDTHH:MMZ>` (UTC), valid only inside the kit-code set | ✖ | pilot only — agent writes refused by protect-paths |
| `state/gates/CONFIG_QUALITE_PROTEGE` | the pilot only, by hand — its presence arms the refusal to Edit/Write an EXISTING lint/format config of the project (`bin/config_qualite_guard.py`); seeded ARMED at adopters (`adopter-seed/gates/`); in the kit, TRACKED, set by the pilot after the merge | ✔ | pilot only — agent writes refused by protect-paths |
| `state/gates/CONFIG_QUALITE_AUTORISE` | the pilot only — one grant per line, `<path\|prefix/> T-<NNNNNNNN or ULID> <YYYY-MM-DDTHH:MMZ>` (UTC); a file grant must name a listed config | ✖ | pilot only — agent writes refused by protect-paths |
| `state/local/SPECS.md` | `specs.py` (render) | ✖ | no — regenerable |
| `state/local/**` | scripts + hooks | ✖ | no — regenerable |

`state/` is tracked apart from **`state/local/` and `state/events/`** because the board,
the ledger, the specs and the index are shared memory: they must travel with the repo.

`state/events/` was designed to travel too — it is the canal-A audit trail — and the
pilot reversed that on 2026-07-28 for two measured reasons. Emitters run inside hooks,
a hook is a short-lived process, and the event stream uses one file per writer, so a
single day produced **320 files for 323 records**: a file per emission, which no diff
can usefully review. And before the redaction fix, one `hook.deny` record carried 1171
bytes of raw shell — git history does not forget, and `gitleaks` never scans a hook's
own append. The stream is regenerable by construction, so nothing is lost; the cost is
that the dashboard reader is now its only consumer and no reviewer sees it in a PR.

`state/local/`
holds only what can be rebuilt from them — the two `.md` views, the run log, the SCA
reports — so it is ignored wholesale by one rule.

### `state/events/` — canal A (event stream)

`events.py`'s `emit(kind, **fields)` appends one JSON line per call to this process's
own day-file, `YYYY-MM-DD.<host>.<pid>.jsonl` — one file per writer, not one shared
file per day (a shared-file design lost 10-22% of concurrently-appended lines on
Windows). **Anything that reads this bucket must glob
`*.jsonl`, never assume a single file per day.** `emit()` itself is fully
fail-open: a missing module, a full disk, or an unserializable value is swallowed —
telemetry must never break a hook.

**This bucket is a SPOOL, not the store.** The dashboard
daemon ingests it into `state/local/events.db` (git-ignored) on a 5 s tick and
deletes each file once it is fully consumed and quiet; the daemon is that
database's SOLE WRITER, the UI only reads it. Writers are unchanged — the hooks
still append their mini-JSONL, which is why there is no lock contention to get
wrong. Retention (30 days) and the monthly digests are now folded
by the tick into the `digests` TABLE. Details, the dedup identity
`UNIQUE(project, src_file, line_index, line_hash)`, and the rollback path
(`event_store.py --export-spool`) are in that module's own docstring.

**`events.py --merge-days` / `--compact` are therefore LEGACY and no-op once
`events.db` exists** (checked under `.maintenance.lock`, so it cannot race the
one-time migration that creates it). They are not merely redundant: re-homing a
spool file the daemon had already ingested but not yet deleted (a Windows handle
still open) would give an already-stored line a NEW
`(src_file, line_index)` identity, which `INSERT OR IGNORE` cannot match — one
audit line, two rows, permanently over-counted. What they used to do:
consolidate each PAST day's writer files into a single `YYYY-MM-DD.merged.jsonl`
(immutable once the day has passed; today's files never touched),
then fold day-files older than 30 days into `state/events/digest/YYYY-MM.json`.
`merge_day_files()` survives for exactly one caller — the store's one-time
legacy migration, which runs it once on a still-absent database.

Wiring status: 8 pre-existing hooks plus the security scanners already call `emit()`
for real, and the Claude Code registrations (`SubagentStart`, `SubagentStop`, `PostCompact`,
`SessionEnd`, `PostToolUse[Agent]`, `PreToolUse`/`PostToolUse[mcp__.*]`) are in
`.claude/settings.json`. `agent.stop` (aid, duration,
tokens) comes from `SubagentStop`; `PostToolUse[Agent]` stays declared and emits NOTHING.
`.agents/evals/events-wiring.test.sh` is the proof suite. This bucket is excluded from the codebase index
(`build_index.py`'s `SKIP_DIRS` skips `.agents` at any depth; the whole coverage rule
is stated once in that file's module docstring, and derived for readers by
`build_index.scope_caveat()` — in a VENDORED kit `.claude`/`.codex`/`.gemini` are
excluded at the root as well, and so is the kit's own code root
`agentic_v3` at the repository root or under `.agents/vendor/agentic_v3/`,
which travels with the kit and would otherwise count as the consumer's own
code), so its own staleness domain is wider than
the index's — expected, not a bug to fix here.

### `bin/dashboard.py` + `bin/dashboard_daemon.py` — observability dashboard

`dashboard.py` is the loopback UI/API server (token-only auth), plus static service for `ui/`
from a closed file table (no path reflected from the request): `GET /api/snapshot`
(board+ledger+specs+index+security+canal B+the six D4 views aggregated), `GET /api/events`
(canal A, paginated), `GET /api/stream` (SSE change notices only, never data), `GET /api/ping`
(liveness that reads nothing), `GET /api/projects` (versioned project list, V1-d), and
`GET /api/peers` (this machine's other daemons, from the registry, filtered summaries).
Canal-B (OTLP) aggregation is memoized, not recomputed per poll. A separate,
NON-tokenised route, `GET /api/peer/summary`, answers a peer's probe with a reduced,
closed-key snapshot (name, running task, health — never a token, never `last_activity`);
detailed views of a peer stay on ITS OWN tokenised URL, its own tab. Route-by-route contract,
the closed `identity.status` × `cause` table and the non-guarantee register:
the route docstrings in `dashboard.py`.

`dashboard_daemon.py` owns the lifecycle: a singleton lock at `state/local/dashboard.lock`
(pid + port + token), detached launch from the `SessionStart` hook (fail-open — a launch
failure never blocks the session), tokenised pid+ping liveness, auto-stop after 4h of
inactivity, and an embedded OTLP receiver on 4318 (also fail-open). CLI: `--daemon` /
`--ensure` / `--status` / `--stop` / `--dash`.
The 4318 holder now routes other projects' events to their spool by identity-proven
`project_id` (never drops them), with unroutable ones parked in `orphans/` and counted.
The routing contract is in `otel_receiver.py`.

`bin/dashboard_registry.py` is the machine-wide registry the federation reads and writes:
`~/.agentkit/registry.json` (override `AGENTKIT_REGISTRY`), one entry per running daemon
(`project_id → project_root, name, pid, port, started`), **never a token**. Atomic write with
a best-effort file lock (`registry.json.lock`, broken after 30s). Tri-state GC: an entry is
alive when its pid is alive AND its peer probe agrees; `dead` (pid gone, connection refused,
mismatched `kind`/`project_id`, a 3xx) is garbage-collected; `indeterminate` (timeout, reset)
survives and is shown as `alive: false` rather than dropped. `pid_alive` and
`replace_with_retry` moved here from `dashboard_daemon.py` (same public names, the daemon now
delegates); `dashboard_daemon.py` registers after its ownership re-check (no project identity
→ `REGISTRY DEGRADED` on stderr, never fatal) and unregisters unconditionally in its `finally`.
The registry carries no token by construction (only the
access handoff below reads a peer's lock, process-side), bounded by a
`127.0.0.1`-only probe and a reduced payload — the accepted residual is same-user access.

`bin/dashboard_handoff.py` hands a peer's dashboard over already authenticated, without the
registry ever carrying a token. On a click on a live peer card
the hub daemon verifies the peer (registry entry, live pid, ALIVE probe, lock owned by the
current user, lock pid and port equal to the entry's), reads the peer's token from ITS lock,
and asks the peer (`POST /api/handoff/mint`, `Host: 127.0.0.1:<port>` required) for a 256-bit,
60-second, single-use ticket held in memory; the tab opens on `#handoff=<ticket>` and trades it
once (`GET /api/handoff/redeem`) for the peer's session token. The hub's tab never sees the
peer's token. Loaded by `dashboard.py` at import; contract and threat model:
the docstring of `dashboard_handoff.py`.

### `bin/wrap.py` — console mirror launcher

`python .agents/bin/wrap.py <cli> [args…]` runs the CLI through a pseudo-terminal
(stdlib `pty` on POSIX; ConPTY via `pywinpty==3.0.5`, lazily imported, on Windows — absent
→ direct execution, no mirror, never a refusal to launch) and duplicates its output to
`.agents/state/local/term/<sid>.raw` (4 MiB ring, 1 MiB tail kept, rotation gen-before-swap
with bounded `os.replace` retry) plus `<sid>.meta.json` (basename-only `cmd`, never argv or
env). Read by `dashboard.py`'s `/api/term` and `/api/term/stream`. Strictly one-way: the
only writer into the child is the local keyboard's own stdin, forwarded and never spooled —
an already-open terminal stays invisible by construction, and a session with no mirror shows
as « événements seulement » in the Sessions view. Declared residuals: secrets printed by the
wrapped CLI are not redactable; macOS runs the untested-in-CI POSIX branch; `pywinpty` sits
outside continuous SCA scanning (pin lives in the docstring, re-bump = manual audit). Full
contract: the docstring of `wrap.py`.

## Upgrading the kit in a project

Replace `bin/` and `ref/`. **Never touch `state/`** — it is the project's memory, not
the kit's. Reference data in `ref/` is kit-shipped but project-editable, so diff it
rather than overwriting blind.

## Migrating from the old flat layout

```bash
python .agents/bin/migrate_layout.py --check    # plan, changes nothing
python .agents/bin/migrate_layout.py --apply
```

Tracked files move with `git mv` so history survives. The script never overwrites an
existing destination: a collision is reported as a conflict for a human to merge. It
is idempotent — running it twice is safe.

## Syncing the template branch

The kit's working branch carries the kit plus this project's own dev state (task
board, ledger, design docs); `template/starter-kit` is the kit team's test branch:
the team copies the current version into a project or a
folder, nobody pulls it. Every file that should ship, and every deletion on the
source branch (the step humans forget), has to be mirrored onto the template branch
by hand — or by `sync_template.py`, which syncs FROM a local branch named by
`--source` (default `main`):

```bash
python .agents/bin/sync_template.py --check --source <branch>   # read-only plan, the default mode
python .agents/bin/sync_template.py --apply --source <branch>   # perform it (must be run from template/starter-kit, clean tree)
```

Name the source every time. Both modes refuse an unusable source before any fetch
or plan (`--apply` first checks `10`, `11`, `12`): `20` it is not a local branch, `21` it is the template itself, `22` the
**lineage guard** — the template's last sync commit (subject
`chore(template): sync from <branch> @ <sha>`) names a sha that is not an ancestor
of the source. On this repository the template was last synced from
`feature/packaging-improvement`, so a bare `--check` or `--apply` (source `main`)
is REFUSED with `22` until `main` is of that lineage. `--allow-foreign-source` lifts
`22` and says what it skipped. The guard reads a claim written in a commit subject,
not the content, and a template with no such subject (a fresh or orphan one) is
**not guarded** — it prints `LINEAGE UNGUARDED` and lets the run through.

**The SEED channel** — the template carries five gate markers that the
kit's own `.agents/state/` (`strip:`) never sends: each `.agents/adopter-seed/gates/<NAME>`
of the source is written to `.agents/state/gates/<NAME>` on the template, from the
source's blob — never from this team's markers — and staged in the index from that
blob; the apply verifies it in the index as well as on disk. So an adopter starts with
`BINOME_REQUIRED`, `PLAN_CHAIN_REQUIRED`, `PLAN_CIBLE_REQUIRED` (`chantier=*`),
`CHRONO_REQUIRED` and `CONFIG_QUALITE_PROTEGE` ARMED. Both ends of the channel must be `strip:` and the destination stays under
`.agents/state/gates/` (else `17`). A source that carries NO seed, on a template that
carries markers there, is REFUSED in both modes with `23` (the sync would delete them
all and disarm every later adopter); `--allow-unseeding` lifts `23`, prints `UNSEEDING`
and what it deletes. A source that still seeds at least one marker is not refused: the
others are planned as `DELETE`. Residue, said rather than found: a run of a script
OLDER than this channel has no `23` and deletes the five markers at rc 0 — read the
`DELETE` section before `--apply`. The separate DOCS channel substitutes up to three
public documents from `.agents/adopter-docs/` when those private sources exist; its
source paths are `strip:`. When no private document source exists, DOCS is empty. First seeded sync:
the template's own copy of the script is older, so run the SOURCE's script — put
`.agents/bin/sync_template.py`, `.agents/bin/sync_template_proc.py` and
`.agents/bin/sync_template_docs.py` from that branch into ONE folder outside the
repository (the first imports both siblings),
then run it with `--root <template checkout>`.

Rules live in the repo-root `.template-exclude` (`strip:` / `keep:` / `own:`, one per
line) and are always read from the source branch via `git show`, never from disk.
`--check` prints six classes — `TAKE (new)`, `TAKE (overwrite)` (with the full diff
per path), `DELETE`, `FROZEN/OWN`, `SEED`, `DOCS`, each naming the real source — plus a reminder
about `TEMPLATE.md`'s store paragraph: if it needs an edit, make it in a SEPARATE
commit after the sync commit, so the sync commit's tree is exactly the planned one.
**The review is human**: this tool claims no leak-detection capability (ledger
`L-025`) — a denylist derived from tracked paths can never see an artefact that has
already leaked and become byte-identical on both branches, since that produces no
diff at all. Read every diff yourself before committing the sync.

`--apply` never commits, pushes, or switches branches; it prints the suggested commit
command — its subject `chore(template): sync from <branch> @ <sha>` (the full 40-hex
sha; older 7-hex anchors are still read) is the anchor the next run's lineage guard
reads — and leaves it for the operator to run.

**`--apply` runs as a transaction.** Before any write it refuses with `24`, nothing
applied, a path the plan writes whose place holds the other kind, judged against the
template's tree AND the disk: (1) a parent the plan needs as a directory is a FILE
(tracked, or anything but a real directory on disk); (2) a path written as a file is a
DIRECTORY (tracked paths under it, or one on disk); (3) a path new to the template is
already held on disk by something untracked — an ignored file, or a case variant of a
tracked path. Rule (3) is new: an older script overwrote such an ignored occupant in
silence, and no rollback could bring it back. The remedy is on the template (remove
the blocking path in its own commit) or on disk (move the occupant away), then re-run.
Past the refusals the apply runs in this order: the index first (`update-index`, the
disk untouched), then `checkout-index` writes the taken files and the seeds, then each
deleted path is unlinked and its emptied parents pruned, then every planned path is
verified against the index and the disk. A failed step, a failed verification, any
other error, or an interrupt (Ctrl-C, SIGTERM, SIGHUP — one already ignored, as under
`nohup`, stays ignored) rolls back from a journal kept in memory — the paths the run
created removed, the index and every touched path HEAD's again — and prints `ROLLED
BACK` (what failed, then `ROLLING BACK`, is printed before the rollback starts; the list
of a failed verification's mismatches, after it): exit
`18` for a git or disk error or a failed verification; an interrupt or an
unexpected error is raised again once the rollback is done. A git still running when
the interrupt or a timeout lands gets SIGTERM, which lets it remove its index lock;
SIGKILL comes only after a bounded grace — POSIX only: on Windows `Popen.terminate()` is
`TerminateProcess`, an outright stop, so the lock stays and the manual recovery below
applies. Only a rollback that itself
fails prints `ROLLBACK INCOMPLETE` and the manual recovery. **Bounds**: SIGKILL, a power
cut or a process killed outright replays nothing and prints nothing, because the journal
lives in memory; the index is then at (or part-way to) the plan and the disk mixed.
Recover by hand at a terminal — the kit's shell guard refuses these steps from an agent,
by design: if the index lock exists — `.git/index.lock`, or in a linked worktree the
path `git rev-parse --git-path index.lock` prints — and no git is running, remove it;
then `git reset`, then `git checkout -- .`, then remove by name the `TAKE (new)` and new `SEED`
paths that `--check` prints again; never `git clean`. The signal handlers are given back
before the rollback starts, so any SIGTERM or SIGHUP while it runs (one not ignored), or
a second Ctrl-C (the FIRST one on a failed step or a failed verification), stops it: same
recovery — and so does one in the short window just before it, while the headline and the
wait line are printed. **A dead terminal** (an SSH session that
dropped) still gets the rollback but no report at all, and the exit code is the same
either way: at reconnection, a clean `git status` on the template branch and no file at
the path `git rev-parse --git-path index.lock` prints mean ROLLED BACK; anything else,
follow the manual recovery above. An empty directory the run created may remain either
way (git never lists an empty directory): remove it with `rmdir` — left there, it changes
nothing for the next `--apply`. On a remote machine, run
`--apply` under `tmux` or `screen`, or under `nohup`. The rollback rebuilds the index
from HEAD, so the skip-worktree (sparse checkout), assume-unchanged and intent-to-add
bits do not come back.

## Adding a new generated artefact

Put it under the bucket that matches its **lifecycle**, not its topic:

- rebuildable from source or from another store → `state/local/`
- project memory that must survive a clone → `state/<domain>/`
- hand-maintained input → `ref/`

Then declare its path in exactly one place per host (the `_common.py` bucket constants
for Codex/Gemini, the `BIN`/`STATE` variables in the Claude hooks) — never as a literal
string spread across agent prompts.

⚠️ Do not name a directory `generated/`: `protect-paths` blocks that pattern on all four
hosts and every write into it would be denied (same trap as `secret`/`credential` in a
filename — see ledger `L-007`).
