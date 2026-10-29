# Quick Setup — machine prerequisites & first run

Everything a Windows PC or a Mac needs before the kit works, in order. One-time,
roughly 15 minutes plus downloads. Host-specific usage lives in
[README-CLAUDE.md](README-CLAUDE.md) and [README-OTHER-HOSTS.md](README-OTHER-HOSTS.md);
security-scanner depth in [README-SECURITY-SCAN-SETUP.md](README-SECURITY-SCAN-SETUP.md).

## 1. Core tools (required by every host)

> **One command on macOS / Ubuntu.** `bash core-scripts/setup.sh`, typed in an
> ordinary terminal (never from your assistant: under an agent it refuses), does
> this section and §5 in one go — the prerequisites, gitleaks, semgrep and the
> audit tool of each module family it detects — shows each command before
> running it, then replays `doctor.sh`. On Linux, gitleaks, trivy and
> dependency-check stay manual. **Windows:** `core-scripts/setup.ps1` installs
> the prerequisites; the scanners stay manual.

| Tool | Why the kit needs it | Windows | macOS |
|---|---|---|---|
| **Git ≥ 2.40 with Git Bash** | every hook and script runs through `bash`; checkpoints, worktrees | [git-scm.com](https://git-scm.com) installer — keep **Git Bash** selected | `xcode-select --install` or `brew install git` |
| **Python 3.11+** (a real install) | hooks, waiver filter, module discovery, HTML audit report (stdlib only — no pip installs) | [python.org](https://python.org) or `winget install Python.Python.3.14` — see the aliases note below | `brew install python` |
| **Node.js LTS + npm** | `npm audit` (SCA), `npx skills add` (audited skill installs) | `winget install OpenJS.NodeJS.LTS` | `brew install node` |

**Windows only — Microsoft Store aliases.** A default Windows install ships fake
`python.exe`/`python3.exe` stubs that open the Store instead of running Python.
The kit defends itself (every script resolves `python3 → python → py`, plus the
shared shim `.agents/pyrun.sh`), but clean the machine anyway:
*Settings → Apps → Advanced app settings → App execution aliases* → turn **off**
the `python.exe` / `python3.exe` "App Installer" entries. Verify in a new
terminal: `python --version` prints a real version. Optional, if you want bare
`python3` to actually work: `mklink C:\Python3xx\python3.exe C:\Python3xx\python.exe`
(admin terminal).

### macOS and Linux — the pinned tools, from the inventory

Two scripts, in this order, both run by you in a terminal (never by an agent):

1. `bash core-scripts/setup.sh` installs the required tools (class B of
   `core-scripts/tool-inventory.tsv`) through the system package manager
   (brew, apt-get). Those packages are **not pinned**: you get the version your
   package manager serves.
2. `bash core-scripts/install-tools.sh` installs **only** the inventory tools
   that carry a `ci_pin`, at the exact version the kit's CI pins, read from
   `.github/workflows/ci.yml` and the requirements files it names with `-r`:
   hash-pinned pip installs (`--require-hashes`, one virtual environment per
   requirements file) and release archives checked against their sha256 before
   anything is written.

On Debian/Ubuntu, run `apt install python3-venv` first: the virtual
environments need it.

`install-tools.sh` defaults to `--plan`: it prints what it would install and
writes nothing, with no network access. Only `--appliquer` installs, and only
under its prefix (default `~/.local/share/cadre-outils`, change it with
`--prefix <dir>`, which must sit under your home directory: a prefix outside it,
or one with `.`, `..` or `:`, is refused (exit 2), unless you also pass
`--hors-home` for the first case); no shell profile is edited. One run at a
time: a second `--appliquer` on the same prefix refuses (exit 1) while
`<prefix>/.verrou` exists. It then prints the `export PATH=…` line to add
yourself (shell-quoted). That line puts the prefix's `bin/` (command-line
tools such as `semgrep` are linked there) and the `pytest` virtual environment
ahead of your own PATH — so that environment's `python3` and `pip` come before
yours. It runs `core-scripts/doctor.sh` before and after, under that PATH: a
tool it installed that the doctor does not report present, or a tool present
before and hidden after, makes it exit 1. Re-running it is safe: a tool whose
receipt matches, at the version its environment really holds, is reported as
already installed and is not downloaded again.
Run under an agent marker with `--appliquer`, it refuses (exit 7); on Windows it
refuses (exit 2) — use `setup.ps1` there.

What it does **not** install: any inventory line without a `ci_pin` — for
example `k6` (AGPL licence) and `terraform` (BUSL licence) — and any pin for
another platform. A hash-pinned pip closure is installed only on the
architecture and the Python minor version of the CI job that resolved it;
elsewhere it is reported as not installable here, with the reason. Today
`gitleaks` and `semgrep` are pinned for Linux x86_64 only (`semgrep` for
CPython 3.12), so on an Apple Silicon Mac whose first `python3` is 3.14, only
`pytest` is installed. Nothing is redistributed by the
kit: each publisher serves its own artefact when you run the script.

### Optional — `k6` for the `load-tester` agent

Only needed to run load tests (`.agents/bin/loadtest.py`, skill
`.agents/skills/load-test/SKILL.md`). k6 is an external binary, not shipped with
the kit. Without it the runner does not guess: it prints
`COVERAGE DEGRADED — k6 absent, verdict absent` and exits 3 — never a false GO.

| OS | Install |
|---|---|
| **macOS** | `brew install k6` (measured on k6 v2.3.0, darwin/arm64) |
| **Linux** | apt / dnf repositories per [k6 install guide](https://grafana.com/docs/k6/latest/set-up/install-k6/) — source: à vérifier, not run here |
| **Windows** | `winget install k6 --source winget` — source: à vérifier, not run here |

Verify: `k6 version`. Azure Load Testing is not a k6 runner (JMeter/Locust only).

### Optional — `terraform` for the `terraform-deployer` agent

Only needed for IaC tasks and Terraform deployments (`.agents/bin/tfdeploy.py`,
skill `.agents/skills/terraform-deploy/SKILL.md`). The runner calls `terraform`
only, never `tofu`: OpenTofu is not a substitute (Q8, `tfdeploy.py` docstring). What the
runner needs, as `tfdeploy.py` holds it (`OUTILS_REQUIS`, `OUTILS_PROBE`):

| Tool | Role | Absent |
|---|---|---|
| `terraform` | `fmt`, `init`, `validate`, `plan`, `apply` | DEGRADED, never GO |
| `trivy`, `checkov` | scan of the plan JSON (trivy HIGH or CRITICAL → NO_GO `scanner` ; checkov findings relayed, never blocking — `severity` is null without an API key) | DEGRADED, never GO — trivy `0.69.4` too (`TRIVY_ECARTEES`) |
| `tflint` | lint, run at `plan` only if present | skipped |
| `az` / `gcloud` / `aws` | the CLI of your target's provider: the identity check, replayed by `identity`, `plan`, `apply`, `verify` and `drift` | DEGRADED on those commands |

Install `terraform`: macOS `brew tap hashicorp/tap && brew install hashicorp/tap/terraform`;
Linux and Windows per the [install page](https://developer.hashicorp.com/terraform/install)
(apt repository, or a zip binary on Windows) — read on that page 2026-10-19, not run here.
For the other tools, their own install guides — source: à vérifier, not run here.

Verify: `bash .agents/pyrun.sh .agents/bin/tfdeploy.py probe`. Measured on
macOS darwin/arm64 without terraform, trivy and checkov: it exits **3** and
prints, on stderr, one line per missing required tool —
`COVERAGE DEGRADED — terraform absent, verdict absent` (then the same for
`trivy` and `checkov`) — and a JSON line on stdout with `"verdict": "DEGRADED"`
and `"couverture_degradee": ["terraform", "trivy", "checkov"]`. With all three
present it exits 0 (`"verdict": "OK"`).

### Optional — `rea` (via `npx`) for the `reverse-engineer` agent

Only needed to run the `reverse-engineer` agent (runner `.agents/bin/rea_run.py`,
skill `.agents/skills/reverse-engineering/SKILL.md`). rea is an external CLI, not
shipped with the kit: the runner launches the pinned `rea-agents@6.7.0` (upstream
tag `rea-agents-6.7.0`, commit `27dc42d1`) through `npx -y`, fetched into the npx
cache on first use (the npm registry must then be reachable; `~/.npmrc` is
honoured), never installed globally — so nothing beyond Node.js LTS + npm (§ 1
above) is required, but rea itself needs Node `^22.19.0 || ^24.11.0 || >=26.0.0`
(`PLAGE_NODE` in the runner). Run `probe` first: outside that range, or with
`node` / `npx` off `PATH`, `probe` prints `COVERAGE DEGRADED — <cause>` and exits 3,
and the agent's flow stops there — never a false verdict.

- **Optional dependencies are omitted**: the runner sets `npm_config_omit=optional`,
  so `npx` does not fetch `frida` and its native binding (only `--with-optional`,
  under a traced pilot decision, lifts it). An npx cache that already holds them
  keeps them — the runner's docstring names that limit.
- **External engines are yours to bring**: Hopper, Ghidra, IDA, jadx and Kuna are
  never installed by the kit; their five variables (`HOPPER_LAUNCHER_PATH`,
  `GHIDRA_INSTALL_DIR`, `REA_IDA_MCP_CONFIG`, `REA_JADX_MCP_JAR`, `REA_KUNA_COMMAND`)
  reach rea only under `--moteurs`, which a `run` takes with a traced pilot decision.
- **Always through the runner**: never `rea setup`, never `claude mcp add` from the
  kit — the runner refuses `setup`, `update`, `uninstall` and `mcp` outright.

Verify: `node --version` falls in the range above. The agent runs the runner's
`probe` itself (it takes no target), once the pilot has named and authorised one.

### Optional — `universal-ctags` for wider index coverage

`/index` runs `.agents/bin/build_index.py`. Out of the box it extracts symbols
with a **stdlib Python fallback** (Python and TypeScript/JavaScript) — nothing to
install. Installing **Universal Ctags** upgrades extraction to 100+ languages
(Java, Go, Rust, C#, Ruby, PHP, …); the builder auto-detects it on `PATH`, and the
`SYMBOLS.md` header then reads `backend ctags` instead of `backend fallback`.

Two requirements: it must be **Universal** Ctags (not the legacy *Exuberant* Ctags),
and the builder must be able to find it — via `PATH`, or via `$CTAGS` / `$CTAGS_PATH`
if you keep it outside `PATH` (see *Pointing at a specific binary* below).

| OS | Install |
|---|---|
| **Windows** | `scoop install universal-ctags` **or** `choco install universal-ctags` (both put it on PATH). Manual: download the x64 zip from the official Windows builds — [universal-ctags/ctags-win32 → Releases](https://github.com/universal-ctags/ctags-win32/releases) — extract `ctags.exe` into a permanent folder (e.g. `C:\tools\ctags\`), then add that folder to your **user PATH** (*Settings → Environment Variables → Path → New*, or `setx PATH "%PATH%;C:\tools\ctags"`). |
| **macOS** | `brew install universal-ctags` |
| **Linux / Unix** | Debian/Ubuntu `sudo apt install universal-ctags` · Fedora/RHEL `sudo dnf install ctags` · Arch `sudo pacman -S ctags` · openSUSE `sudo zypper install ctags` |

**Verify** in a *new* terminal — the first line must say **Universal Ctags**:

```bash
ctags --version        # -> "Universal Ctags 6.x …"
                       # "Exuberant Ctags" = wrong package; the builder ignores it and keeps the fallback
```

No kit configuration is needed: with `ctags` on `PATH`, the next `/index` uses it
automatically; otherwise the Python fallback runs. Air-gapped machines: fetch the
package/zip on a connected host and copy it in — the builder never reaches the network.

**Pointing at a specific binary.** The builder checks `$CTAGS`, then `$CTAGS_PATH`,
then `PATH`. Set one when the binary lives outside `PATH`, or when hooks/CI run with
a different `PATH` than your shell — without it the builder degrades silently to the
Python fallback and the only symptom is `backend fallback` in the `SYMBOLS.md` header.

```bash
export CTAGS=/opt/ctags/bin/ctags      # macOS / Linux
setx CTAGS "C:\tools\ctags\ctags.exe"  # Windows (new terminal after)
```

A value that doesn't resolve to Universal Ctags is ignored, and `PATH` is tried next.

**Tuning what gets indexed.** By default only structural kinds are kept (functions,
classes, methods, interfaces, structs, enums, …) — indexing every field, local and
`package` tag would multiply the index 3-4x on a large repo and stop it fitting in a
context window. Override with `--kinds` or `$ABK_INDEX_KINDS` (comma-separated ctags
kind names) if your stack needs something else:

```bash
ABK_INDEX_KINDS=function,class,method,interface,struct,enum,field python .agents/bin/build_index.py --full
```

**What is skipped.** Dependency and build trees (`node_modules/`, `vendor/`, `Pods/`,
`.next/`, `target/`, …) even when committed, machine-written files (`*.min.js`,
`*_pb2.py`, `*.d.ts`, `*-generated.*`, …), and anything over 1.5 MB. None of these
contain a symbol worth navigating to, and minified bundles alone would dominate the scan.

**Scale.** Reference point on a 3600-file / 151k-line / 65k-symbol tree: full build
~3 s, incremental ~1.4 s (ctags is batched, not one process per file). Routine `/index`
runs are incremental — only files changed since the `built @ <sha>` anchor are rescanned.

Past 500 symbols the index shards by module, and a module past 2000 rows splits again
(`SYMBOLS_core_1.md`, `_2`, …) so no shard is too big to read in one pass. `SYMBOLS.md`
becomes an index-of-indexes listing each shard with its symbol count and id range.
SYM ids are padded to a fixed width per build, so `grep 'SYM-00102'` finds exactly that
symbol's callers — at a fixed 3 digits it would also have matched `SYM-1020`…`SYM-1029`.

## 2. Host CLIs — install the ones you use

| Host | Install | First-run note |
|---|---|---|
| **Claude Code** | `npm install -g @anthropic-ai/claude-code`, then `claude` and log in | discovers `.claude/` automatically; `/agents` should list 35 agents |
| **OpenAI Codex** | `npm install -g @openai/codex`, then `codex` and log in | **trust the kit hooks once**: run `/hooks` in an interactive session and approve them — they report `Failed` until trusted, and must be re-trusted after any `.codex/hooks.json` change (hash-pinned by design) |
| **Gemini / Antigravity** | Antigravity IDE, or `npm install -g @google/gemini-cli` | reads `GEMINI.md` → `AGENTS.md`; workflows via `$name` |
| **GitHub Copilot** | VS Code Copilot extension and/or `gh` CLI | cloud agent reads `.github/` from the **default branch** — commit the kit before expecting hooks/agents there |

## 3. Copy the kit into your repository — the current adoption channel

**Who copies what, and from where:**

- **Adopting project — today:** copy a checkout of the `template/starter-kit`
  branch, as described in the rest of this section: it is the current adoption channel.
- **Adopting project — once published:** the `cadre-kit` wheel (pinned source:
  § Install the core) once per machine, then `cadre init --host <host>` once per
  project. **Not available yet:** no version is published, and `cadre init` is a
  RESERVED command until Phase 3 (`cadre --help` lists it as reserved). Until
  then, use the template channel.
- **Team that develops the kit itself** (vendoring, pilot tests): the same copy,
  from a checkout of the kit.

From the root of the checkout you copy (template branch or kit), copy into the
target repo root:

```
.agents/  .claude/  .codex/  .cursor/  .gemini/  .github/  .githooks/  .kimi-code/
agentic_v3/ (if present)  core-scripts/  docs/  agents/  commands/
AGENTS.md  CLAUDE.md  GEMINI.md  README*.md  QUICK-SETUP.md  CHANGELOG.md  verifier-agent.md
SECURITY.md  THIRD_PARTY_NOTICES.md
.gitignore  .gitattributes  .geminiignore  .gitleaks.toml  .template-exclude
conftest.py  pytest.ini  contract.lock.json
```

That is every top-level entry of the `template/starter-kit` branch except `TEMPLATE.md`, which exists only on that branch; a kit checkout carries more at its root, and that surplus stays out. `core-scripts/` holds `verify.sh` and `.githooks/` the push hook, both used below; the core, the `cadre` package, lives under `.agents/vendor/cadre/` and comes with `.agents/`. When upgrading a repository that still carries the old `src/cadre/`, remove it (`git rm -r src/cadre`); the kit team's editable tool is reinstalled from the kit checkout (by the editable reinstall of the kit team's own clone, below); an installed wheel is unaffected.

The V3 package may live at `agentic_v3/` or `.agents/vendor/agentic_v3/`.
The latter is already included when you copy `.agents/`. Copy the root directory
only if it exists in the source checkout. Both locations keep the Python package
name `agentic_v3`; the kit resolver chooses the vendor copy when both exist.
For a direct `python -m agentic_v3` invocation at the root without `-P`, Python loads the
root copy when both exist. Use `PYTHONPATH=.agents/vendor python3 -P -m agentic_v3`
to load the vendor copy. The kit now ships the engine under `.agents/vendor/agentic_v3/`
only: when upgrading a repository that still carries `agentic_v3/` at the root, delete
that root copy after the recopy (`git rm -r agentic_v3`), so only one engine remains,
then delete the leftover `agentic_v3/` directory: its ignored `__pycache__/` caches
survive `git rm`, and while that directory exists `python -m agentic_v3` at the root
fails with "'agentic_v3' is a package and cannot be directly executed". Before
deleting it, check that it holds nothing but `__pycache__/` (`find agentic_v3 -path
'*/__pycache__' -prune -o -type f -print` prints nothing); anything else is yours.

If your repository already has its OWN version of any of these files or folders (README.md, AGENTS.md, CLAUDE.md, GEMINI.md, CHANGELOG.md, .gitignore, .gitattributes, conftest.py, pytest.ini, workflows under .github/, a docs/ or src/ tree), merge it — never overwrite yours. A later recopy of the kit, to upgrade it, replaces the kit's own files: save what you enriched first (`docs/PROMPT-projet.md`, below).

**Do NOT copy `.agents/IS_THE_KIT`** — delete it if a recursive copy of
`.agents/` brought it along. It is the kit's IDENTITY marker: its presence tells
the index builder "this tree is the kit itself", so in *your* repo it makes
`.claude/`, `.codex/`, `.gemini/` and `agentic_v3/` be indexed as your own source
code, burying your symbols under vendored kit plumbing. **It ALSO
switches your push gate to the KIT's suite:** with the file present,
`core-scripts/verify.sh`, `.githooks/pre-push` and the `porte` job of `ci.yml`
run the kit's own tests instead of your project's build and tests
(`.agents/bin/porte_adoptant.py`), and the CI `adoptant` job is skipped — which
the forge reports as Success. On a pull request, the `porte` job refuses a PR
that takes an adopting base out of adoptant mode; nothing refuses a tree that
never was in it. The
`strip:` rule in `.template-exclude` covers the template channel only; a raw
`cp -r` is exactly the case it cannot reach. Nothing reads the file's content, so
deleting it is safe and complete:

```
rm -f .agents/IS_THE_KIT
```

**Remove the LAST line of `.agents/.gitignore`** (`protected-paths.local`) if you
want git to track your own `.agents/protected-paths.local`. The kit ignores that
file on `main` so a stray `git add -A` cannot commit its per-machine patterns; a
recursive copy brings the rule along, and while it stays, your file is invisible
to git. The template channel does not carry this line (`keep: .agents/.gitignore`
in `.template-exclude`), so only the raw copy needs the edit. A
recursive copy also brings the kit checkout's own untracked
`.agents/protected-paths.local` if that machine has one: KEEP the file, empty or
rewritten with your project's prefixes, BEFORE the first `git add` — never delete
it; if it is missing, `touch .agents/protected-paths.local`. Its mere presence keeps
the kit's code out of your index (`build_index.py`, presence-only).

**`.agents/state/` — what you keep depends on WHERE you copy from.** That
directory is *this* team's state: board, ledger, specs, and **gate markers whose
mere presence arms a refusal**. Five of them are ARMED by default for an
adopter, on purpose: `BINOME_REQUIRED` (closing a task needs one
traced closing review), `PLAN_CHAIN_REQUIRED` (starting a task needs a traced
plan chain), `PLAN_CIBLE_REQUIRED` (every step of a plan carries a target —
`spec=docs/PROMPT-projet.md`, `chantier=*`, i.e. every task of the board, with
or without a chantier), `CHRONO_REQUIRED` (a `plan-critic …` loop verdict
carries the turn's `chrono:` field) and `CONFIG_QUALITE_PROTEGE` (an agent's
Edit/Write of an EXISTING lint/format config is refused; creating one stays
allowed). Each has a traced way out that stays
VISIBLE: `--sans-binome`, `--sans-chaine`, `--sans-cible` on the board,
`--sans-chrono` in the specs journal, and for the config guard a pilot grant
line in `.agents/state/gates/CONFIG_QUALITE_AUTORISE`, each granted write
journaled as `hook.warn`. The traces are written
by the host; which host writes which trace is in `README-OTHER-HOSTS.md`
(per-host coverage table, dated: MEASURED / WIRED / NOT WIRED / ASSUMED per
item). On a host that does not trace, the refusal is the CHOSEN regime, not an
accident — use the exit and say why (`hôte sans trace : <host>`).

- Copying from a **template checkout** (`template/starter-kit`): keep
  `.agents/state/gates/` — once the first seeded sync has run, the five
  markers arrive with the copy, and nothing else of this team's state is on
  that branch. If `.agents/state/gates/` is absent from your template copy
  (template not yet re-synced), it starts UNARMED and has nothing to restore
  from: start from a kit checkout.
- Copying from a **kit checkout**: its own state travels with a raw copy and must
  go, then the seeds are restored:

```
rm -rf .agents/state
mkdir -p .agents/state/gates
cp .agents/adopter-seed/gates/* .agents/state/gates/
rm -rf .agents/adopter-seed
```

Check, from either source: `ls .agents/state/gates` lists exactly
`BINOME_REQUIRED`, `CHRONO_REQUIRED`, `CONFIG_QUALITE_PROTEGE`, `PLAN_CHAIN_REQUIRED`
and `PLAN_CIBLE_REQUIRED`.
`rm -rf .agents/state` ALONE, from either source, leaves no marker at all
(measured): the project would start UNARMED. Enrich `docs/PROMPT-projet.md`
(seven generic targets) before your first plan; a recopy overwrites it, so save
an enriched one first. Disarming a guard = removing its marker, a gesture of the
project's pilot. Current channels: a copy of the template branch or of a kit
checkout; `cadre init` (reserved) seeds nothing.

Then commit. Two rules the kit enforces from that moment: no edits without an
approved plan, and `rm`/`mv` on tracked files is hook-blocked (use your editor
or git).

### Install the core — pinned source

For the adopting project, not the kit team, and **once published**: today no
version is published and `cadre init` stays reserved (see the once-published
bullet of this section). The core is the distribution `cadre-kit`; its command
and its import package are both `cadre`. **Another package already holds the
name `cadre` on the public index**, so the core is never installed from the
public index, nor from an index uv picks for itself: every command below pins
its channel. Each one starts with the same
prefix, `env -u` on the seven uv variables that can re-route a `cadre-kit`
install, and passes `--no-config`, which ignores every `uv.toml`. Keep both on every line:
uv remembers neither. On uv, the adopting project installs the core with
uv's tool install as below, never with uv's pip interface, which the kit's own
install net (a lint of the kit repository, not shipped to adopting projects)
refuses.

**Migrating a machine that already carries the former distribution.** If this
machine already has the core installed under its former distribution name,
`cadre` (the kit team's editable install, for instance), remove that tool
FIRST, with uv's tool uninstall aimed at the tool named `cadre`, and only then
run one of the pinned installs below. Never force the pinned install over it:
uv refuses it (« Executable already exists: cadre »), and following its
`--force` hint leaves both tools listed, so a later removal of the old tool
deletes the `cadre` executable and cadre-kit's command disappears with it. On
the kit team's own clone, where nothing is published yet, reinstall from the
clone root with:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    -u UV_INDEX_URL -u UV_BUILD_CONSTRAINT \
    uv tool install --no-config --editable .
```

The clone is never looked up on an index and the distribution itself carries
no runtime dependency, but its build backend (`hatchling`) is, so this line
also unsets `UV_INDEX_URL` (honoured when no `--default-index` is passed) and
`UV_BUILD_CONSTRAINT` (which can pin the backend to a URL); offline, it needs a
warm uv cache. The prefix neutralises uv's routing variables, not a hostile
shell: UV_WORKING_DIR (which moves .) and PYTHONPATH (which reaches the build
backend) stay honoured under this line.

(a) **From the `glass-dist` distribution** (a folder or a page of wheels), the
documented path:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool install --no-config --no-index --find-links <glass-dist> cadre-kit
```

(b) **Offline fallback**, from a wheel file you were handed:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool install --no-config <path-or-URL>/cadre_kit-<v>-py3-none-any.whl
```

(c) **Alternative, a private registry:**

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool install --no-config --default-index <registry> cadre-kit
```

**Upgrade the core.** This is the command; the core's version-mismatch refusal
will point to this section — the kit's install net admits a
pinned form only in a `bash` fenced block of a `.md`:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool upgrade --no-config cadre-kit
```

After an install by (b), that command answers « Nothing to upgrade »: uv
remembers a wheel path, not a source. What upgrades then is a reinstall from
`glass-dist`:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool install --no-config --reinstall --no-index --find-links <glass-dist> cadre-kit
```

Offline, replay form (b) with the new wheel file: it replaces the installed
version (measured, uv 0.12.7).

This one repairs an installation in place:

```bash
env -u UV_INDEX -u UV_EXTRA_INDEX_URL -u UV_DEFAULT_INDEX -u UV_FIND_LINKS \
    -u UV_OVERRIDE -u UV_CONSTRAINT -u UV_CONFIG_FILE \
    uv tool upgrade --no-config --reinstall cadre-kit
```

If uv itself suggests reinstalling by the bare distribution name, do not follow
that hint: use the pinned form above. A programmatic launcher removes the seven
variables from the child's environment and passes `--no-config` in its argument
list.

**Bounds, measured with uv 0.12.7 on 2026-09-27 (darwin):**

- neither the `env -u` prefix nor `--no-config` is remembered in uv's install
  receipt, so type both on every install, upgrade and reinstall;
- `--no-config` ignores the whole `uv.toml`, so a proxy or index setting kept
  only there is dropped too: possibly a loud failure behind a proxy, not
  measured;
- form (c) is safe only on a registry with no public upstream. A registry that
  redirects to PyPI, relays it (a virtual repository with a PyPI upstream) or
  mirrors it (a public mirror) is not detected, and the reservation of the name
  is then the only rampart;
- uv reads further environment variables (its `[env:]` list); those outside
  these seven are not measured;
- PowerShell is not measured; GNU `env -u` is documented, and measured on the
  BSD `env` only.

## 4. First run (any host — `/name` on Claude, `$name` elsewhere)

0. **`python3 .agents/bin/setup_projet.py`** — the FIRST command after tooling,
   run from the repository root (Windows — Git Bash:
   `bash .agents/pyrun.sh .agents/bin/setup_projet.py`). It chains the
   existing producers, offline, and prints ONE line per leg —
   `setup: <leg> : créé | déjà là | sans objet | dégradé — <reason or remedy>`:
   there is no need to prefix this command with
   `PYTHONPATH=.agents/vendor`: the setup's V3 leg puts `.agents/vendor` first
   on its own import path whenever it carries the package.
   - **identity + board** — `project_init.py --name <directory name>` (pass
     `--name "My Project"` to choose), or `--ensure-stores` when the identity is
     already there. `git config user.name` must be set: an empty one degrades
     this leg and STOPS the setup (exit 1), nothing else is written;
   - **machine stores** (V3 event store, `events.db`, `index.db`), then the
     **files index** (`build_index.py --if-stale`) and its SQLite copy
     (`migrate_index_to_db.py --resync`, then `--verify`);
   - **V3 specs** — `PYTHONPATH=.agents/vendor python3 -P -m agentic_v3 sync-spec`
     whenever `.agents/vendor/agentic_v3/` exists (it wins over a copy at the root),
     else `python -m agentic_v3 sync-spec` with the package at the root, on the tracked
     `docs/specs/*.md` and `specs/*.md` (not recursive), plus the files an
     *old* V3 base names (`.agents/state/v3_event_store.db`, from before the
     store moved out of the repository). Only files `git ls-files` lists are
     synced; the line counts what it left out (untracked files, the `.md`
     files in SUB-directories of `specs/` and `docs/specs/`, `docs/*.md`).
     The old base is READ ONLY (`mode=ro&immutable=1`): never copied, rewritten
     or deleted. Its line reports what the replay recovers and what it cannot
     (sections without a source file, older versions); a non-empty `-wal` next
     to it makes that leg `dégradé` (the read may be incomplete);
   - **specs graph** (`specs_graph.py generate`), then READ-ONLY probes: the
     dashboard snapshot sections (with the remedy of each degraded one —
     `/audit`, `project_init.py --print-otel-env`), dashboard daemons of other
     roots, the gate markers present and `core.hooksPath`; the field-merge
     driver is verified, then offered (below). A daemon that is not alive, and an unset
     `core.hooksPath` next to a `.githooks/`, are `dégradé` — the same `KO` the
     verified bilan gives them — without moving the exit code. The dashboard
     reads no V3 table yet: synced specs do not show there. The last line,
     `setup: résumé rc=<n> — …`, counts the setup's legs; the verified bilan's
     verdict is its own `bilan: … — exit <n>` line.

   **Git hooks opt-in during setup.** The machine setup (`setup.sh` or
   `setup.ps1`) and this project setup first check the repository,
   `.githooks/`, effective `core.hooksPath`, and active entries other than
   `*.sample` in Git's hooks directory. With no conflict, an input TTY, no
   `--dry-run` and no agent marker set (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`,
   `AGENTS_HOOK_HOST`, `COPILOT_AGENT_SESSION_ID`, `COPILOT_CLI`; under one of
   them the machine setup refuses outright outside `--dry-run`, exit 7; Codex, Gemini and Kimi set
   none in the agent's shell), they ask exactly:
   `Activer les hooks de ce dépôt (tous ses worktrees liés partagent ce réglage) dans .githooks ? core.hooksPath remplace les hooks de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; commit-msg refuse certains sujets ; Git exécute les hooks de l’arbre courant. [o/N]`
   Only exact lowercase `o` or `oui`, without spaces, sets the local
   `core.hooksPath=.githooks`; Enter, EOF, `Non`, `Oui`, `OUI`, and ` o ` mean No.
   A foreign hooksPath, missing `.githooks/`, failed Git read, or active hooks
   means no question and no change to config or hooks. With active hooks,
   integrate the existing hooks into `.githooks/` and chain matching names;
   alternatively integrate the kit hooks into the active hooks directory
   without changing `core.hooksPath`. If a `pre-push` already exists there,
   chain the two `pre-push` hooks; never copy the kit's over the existing one.
   `core.hooksPath` replaces `.git/hooks/` rather than adding to it.

   **Merge driver opt-in during setup.** The machine setup (`setup.sh` or
   `setup.ps1`) and this project setup check the per-clone driver. Only a run
   that reaches its summary line offers it; an early stop (exit 2: unsupported
   platform, missing brew/apt-get/winget, unreadable inventory or doctor)
   offers nothing and says nothing. If verification
   fails, they ask `Installer le pilote de fusion dans ce clone ? [o/N]` on an
   input TTY. Only lowercase `o` or `oui` installs it (case-sensitive); `N`, Enter,
   EOF, and a refusal leave it unarmed and say so (machine setup:
   `pilote de fusion refusé ; rien armé.`; project setup: a `sans objet` leg;
   exit code unchanged).
   No driver is armed without a TTY,
   during `--dry-run` (PowerShell: `-DryRun`), or under an agent marker (the
   five listed above). Python ≥ 3.11
   is required; if it is absent, the driver is not offered. Only in the kit,
   with `.agents/IS_THE_KIT`, `HEAD` on `develop`, and `origin/develop` present,
   installation adds `--depuis origin/develop`; an adopting project does not.
   After a refusal, repair each clone with
   `python3 .agents/bin/fusion_enregistrement.py --installer` and then
   `python3 .agents/bin/fusion_enregistrement.py --verifier` (Windows: use
   `.agents/pyrun.sh` to select Python). The interpreter and driver copy are
   frozen; `post-merge` and `post-commit` hooks still come from the merged tree,
   so review that tree. With `core.hooksPath → .githooks`, the hooks alert after
   covered merges, including a two-parent merge committed after resolving a
   conflict by hand. Without that hooksPath, there is no alert; a worktree
   whose hooksPath points outside its own `.githooks` is also silent. Rebase
   without `-r`, cherry-pick, revert, and any merge that ends in neither
   `git merge`/`git pull` nor a two-parent commit (`stash apply/pop`, `am -3`,
   `checkout -m`) are not reported. With `rebase -r`, a merge
   recreated without conflict is not reported on screen (git does not show the
   hook's alert); one recreated after a conflict and `git rebase --continue`
   is reported. Amending a merge reports it again (an extra alert). In an
   adopting project, `porte_adoptant.py` checks mode `100755` only for
   `pre-push`: if `post-merge` or `post-commit` arrives as `100644`, Git ignores
   it with an `ignoredHook` advice (unless `advice.ignoredHook=false`). Git for
   Windows with `C:\`
   paths has not been measured. The adopting channel is `sync_template.py` into
   `template/starter-kit`, followed by the project's copy or update.

   - **verified bilan** — `setup_bilan.py` (read-only leg, played before the
     probes so the snapshot reads this run's result): seven legs — version,
     tools, scanners, interpreter, hooks, gates, dashboard — each `OK`, `KO`
     or `SANS OBJET` (the scanners themselves, and the audit tool of each
     module family, are installed by `bash core-scripts/setup.sh` — on
     Linux, gitleaks, trivy and dependency-check stay manual; on Windows,
     `setup.ps1` installs none of them),
     every `KO` with its written remedy (`bilan: <leg> : KO — … ; remède : <cmd>`).
     It writes the git-ignored contract `.agents/state/local/setup-bilan.json`
     (atomically; `--sans-ecrire` writes nothing), which the dashboard serves
     under the `setup` key of `/api/snapshot`. Replay it alone, any time, after
     applying a remedy: `python3 .agents/bin/setup_bilan.py` — exit 0 no `KO`,
     1 any `KO`, 2 usage. Bounds: `hooks` means « declared and present » (no
     `disableAllHooks: true` in `.claude/settings.json` or
     `.claude/settings.local.json`, the `.githooks/` that `core.hooksPath` names
     exists), never « fired by the host », and covers Claude Code only; `gates`
     is `SANS OBJET` in the kit itself.

   Re-running is safe: nothing is duplicated, and nothing is overwritten except
   the git-ignored verified-bilan contract `.agents/state/local/setup-bilan.json`,
   rewritten on every run (`genere_le` moves). On a tree where
   nothing changed since the previous run, the creating legs then say
   `déjà là` — bounded: a source change since the last commit makes the index
   leg rebuild (`créé`); the old-base line stays `dégradé` as long as sections
   remain unrecovered; and a real run lets Python write its git-ignored
   `__pycache__/`. `--dry-run` probes each leg read-only (`git config
   user.name`, `--stale-check`, `--verify`, `generate --stdout`) and says what
   a real run would do (`à créer`), writing nothing, bytecode included; a spec
   changed after its last sync is still said `déjà là` there. `--commit` (opt-in) also
   commits the state stores (`tasks.py commit-stores --exiger`). Exit code: 2 =
   refused before any leg (not a git top level, the kit itself, a diverging
   `$CADRE_PROJECT_ROOT`, neither `.agents/vendor/cadre/` nor `src/cadre/`), 1 = a creating leg degraded, 0
   otherwise.

   The identity is `.agents/state/project.json` (a uuid4 `project_id`, a
   derived `slug`, the creation timestamp). The name the dashboard DISPLAYS is
   the basename of the repo's directory, not this one; `--name` only fills
   `project.json:name`, written and NOT displayed. **A project
   identity is generated ON PLACE and never copied**: the file is git-ignored,
   so it does not travel between repos. A `project.json` that arrived via a
   clone or a copy is an *inherited* identity (someone else's `project_id`) —
   delete it and re-run the setup. Until it exists, every SessionStart shows a
   « projet sans nom » nudge. `python3 .agents/bin/project_init.py` alone still
   creates the identity and the board, without the other legs.
1. **`/index`** — (re)builds the shared memory (`CODEBASE_INDEX.md`,
   `SYMBOLS.md`) via the deterministic `build_index.py`, which the setup has
   already run once. Language detection runs first automatically when the
   index has no Stack section. Works out of the box for Python/TS/JS; install
   `universal-ctags` (§1) first for wider coverage.
2. **`/skills-sync`** — detects the stack, installs best-practice skills from
   audited GitHub-pinned sources (manual audit + `AUDIT_LOG`; skills.sh is an
   OIDC-gated probe that degrades loudly, not the install path), fills the docs
   registry. The GitHub fallback ships `install_mode` `confirm` in
   `.agents/security/skills-fallback-policy.json`, so
   `install` refuses rc 5 without `--confirmed-by <pilote>` — the resolver
   stops after `show` and hands you the exact install command to run
   yourself. Restart the session afterwards so new skills load.
3. Optional baseline: **`/audit`** (add `-global` for a whole-repo code
   review) — read-only, multi-module security audit; HTML report at
   `.agents/state/local/sca-reports/audit-latest.html`.
4. Real work: **`/kickoff <task>`** — the governed pipeline (forecast →
   approvals → dev → security gate → docs → index).
5. Optional, **Claude Code only**: **`/night`** — autonomous overnight mode.
   Approve the plans it may run with `/kickoff --defer-night <task>` (they stay
   `pending`, their plan snapshot is committed, and they carry its sha256), then rehearse with
   `/night --dry-run`, which writes nothing. On Codex / Copilot / Gemini /
   Antigravity the workflow is refused, not emulated.

## 5. Security scanners (gitleaks and semgrep are REQUIRED by the adopter gate — installed by setup.sh on macOS)

- **`NVD_API_KEY`** (free, required for Java/Swift CVE data):
  https://nvd.nist.gov/developers/request-an-api-key — export it and the kit
  forwards it to the scanners. Full per-ecosystem setup, Gradle plugin snippet
  and degraded-verdict semantics: [README-SECURITY-SCAN-SETUP.md](README-SECURITY-SCAN-SETUP.md).
- **socket CLI** (`npm i -g socket`) for the npm supply-chain layer —
  otherwise that layer reports DEGRADED (scans still run).
- npm projects need nothing else; Maven/Gradle prefer their committed
  `./mvnw` / `./gradlew` wrappers (the kit uses them automatically).

## 6. Sanity checks (30 seconds)

```bash
bash .agents/pyrun.sh -c "print('python: ok')"     # resolver finds a real python
bash .agents/security/sca-scan.sh                  # exit 2 = no manifests here (normal
                                                   # for the bare kit); scans your modules otherwise
```

On Claude Code: `/agents` lists 35 agents. On Codex: `/hooks` shows the kit
hooks as trusted. If a hook ever blocks you, that is the kit working — read the
reason, don't work around it.

## 7. Dashboard telemetry (optional) — canal B, per host

The dashboard has two independent inputs. **Canal A** (kit semantics: gate
verdicts, denials, board moves, index rebuilds) needs **zero configuration** —
the hooks emit it on all four hosts out of the box. (Kimi Code is wired the same
way — `.kimi-code/hooks.json` → `.codex/hooks/*` under `AGENTS_HOOK_HOST=kimi` —
but its runtime emission is SUPPOSED, not measured: no kimi CLI run proves it here,
so the emitter count stays four.) **Canal B** (tokens, cost,
model, durations) is the host's own OpenTelemetry stream, and each host activates
it differently. Everything below is opt-in, paste-ready, and **localhost only**.

Three rules that are not negotiable, and one limit you must know before trusting
a number:

- **`127.0.0.1` exclusively, never a remote collector.** These streams carry
  `user.email` and `organization.id`.
- **Prompt/content capture stays OFF.** It is off by default on Claude Code,
  Codex and Copilot — and **ON by default on Gemini CLI**, the only one of the
  four, so `logPrompts: false` there is mandatory, not decorative.
- The receiver serves exactly `POST /v1/logs` and `POST /v1/metrics` on
  `127.0.0.1:4318`; start it with `/dash` (or let SessionStart launch it).
- **Port 4318 is machine-global while the kit is per-project.** No host attaches
  a project identifier to its OTLP payload on its own. The receiver routes each
  event by the resource attribute `agentkit.project_id`; without it the spend is
  counted as `unattributed` by whichever daemon holds the port, and that
  project's Cost totals include it. Set it per clone: on Claude Code in the
  git-ignored `.claude/settings.local.json` (the identity key only), on Copilot
  in the host environment; Gemini is attributed by its in-repo outfile; Codex
  stays unattributable. Get the line with
  `python3 .agents/bin/project_init.py --print-otel-env --format shell`;
  step-by-step in `docs/usage.html`, tab « 1 · Installer », step 4 « Branche ton assistant ».

**Claude Code** — USER scope only: Claude Code ignores these keys when they come
from a project's `.claude/settings.json` or `.claude/settings.local.json` (read
in the 2.1.299 binary: "project-scoped settings can't set this key"), so the
project file carries no telemetry keys. Put the six
variables in the `env` of your `~/.claude/settings.json` (they are part of
`docs/settings-utilisateur-recommande.json`), or export them before launching
the CLI (telemetry is read at startup; exporting it in an existing session does
nothing):

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_METRIC_EXPORT_INTERVAL=5000   # else ~60 s before anything shows up
# Project attribution (agentkit.project_id): .claude/settings.local.json, see above.
# Do NOT set OTEL_LOG_USER_PROMPTS / OTEL_LOG_TOOL_DETAILS / OTEL_LOG_RAW_API_BODIES.
```

**Codex** — `~/.codex/config.toml`, **user level only**. Agents cannot write this
file (the MCP path guard denies it), so this is a human paste by construction:

```toml
[otel]
environment = "dev"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }
```

`exporter` is an **inline table**, not an `[otel.exporter."otlp-http"]` section —
the shape previously flagged as unconfirmed, now checked against the
official reference. `protocol` must be spelled out: the vendor example uses
`binary`, which the kit's stdlib receiver does not parse.

**Gemini / Antigravity** — the CLI's `telemetry` key in `.gemini/settings.json`.
Also a human paste: same path guard, and the file is shared with Antigravity IDE
settings, so **add** the key, never overwrite the file.

```json
{
  "telemetry": {
    "enabled": true,
    "target": "local",
    "logPrompts": false,
    "otlpProtocol": "http",
    "otlpEndpoint": "http://127.0.0.1:4318"
  }
}
```

`logPrompts` defaults to **`true`** here — omitting it exports your prompts. The
default endpoint is gRPC on `:4317`, and the JSON-over-HTTP encoding is **not
documented**, so if nothing arrives use the file fallback (`"target": "local"`
with `"outfile": "<path>.jsonl"`) instead of assuming the HTTP path works.
Environment equivalents: `GEMINI_TELEMETRY_ENABLED`, `GEMINI_TELEMETRY_TARGET`,
`GEMINI_TELEMETRY_OTLP_ENDPOINT`, `GEMINI_TELEMETRY_OTLP_PROTOCOL`,
`GEMINI_TELEMETRY_LOG_PROMPTS`, `GEMINI_TELEMETRY_OUTFILE`.

**GitHub Copilot** — environment:

```bash
export COPILOT_OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export "$(python3 .agents/bin/project_init.py --print-otel-env --format shell | grep '^OTEL_RESOURCE_ATTRIBUTES=')"
# Do NOT set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT.
```

What is **not** claimed here: runtime delivery has only been confirmed for Claude
Code. Codex's docs now describe an OTel *metrics* pipeline, which contradicts the
kit's earlier NO-GO note on Codex metrics — re-verify before reading a Codex cost
figure as fact. Gemini stays a file-export fallback until someone proves the HTTP
encoding. Sources: [Claude Code](https://code.claude.com/docs/en/monitoring-usage)
· [Codex](https://learn.chatgpt.com/docs/config-file/config-advanced) ·
[Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/telemetry.md)
· [Copilot](https://docs.github.com/en/copilot/how-tos/copilot-sdk/observability/opentelemetry).
