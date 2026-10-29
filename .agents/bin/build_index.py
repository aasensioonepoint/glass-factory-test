#!/usr/bin/env python3
"""Deterministic, incremental codebase-index builder for the agentic kit.

Extracts symbols (universal-ctags when available, stdlib fallback for
.py/.ts/.js), resolves APPROXIMATE ``uses[...]`` edges by name against the
symbol table, and rewrites ``.agents/state/index/SYMBOLS.md`` (sharded past a
threshold), ``CODEBASE_INDEX.md`` and ``INDEX_DELTA.json``. Only re-scans files
changed since the ``built @ <sha>`` anchor unless ``--full``.

Built for repos in the 500k-LOC range: ctags runs batched (``-L``, not one
process per file), only structural kinds are kept, and edge resolution drops
names carried by more than ``MAX_NAME_CARRIERS`` symbols. Reference point —
3600 files / 151k lines / 65k symbols: full build ~3 s, incremental ~1.4 s.

``ctags`` is resolved from ``$CTAGS`` / ``$CTAGS_PATH`` first, then ``PATH``;
without it the stdlib fallback covers .py/.ts/.js only.

No LLM runs here. The ``indexer`` agent only annotates ``:: purpose`` on the
delta and the Role/Owner cells of CODEBASE_INDEX.md. Usage:

    python build_index.py [--root DIR] [--full] [--if-stale] [--threshold N]
                          [--kinds K,…] [--unskip .claude,.codex,.gemini]

COVERAGE, stated once: `.agents` is excluded at any depth (L-020), and in a tree
detected as a VENDORED kit — exactly one carrying `.agents/protected-paths.local`
or `.claude/hooks/protected-paths.local` at its root — `.claude`, `.codex` and
`.gemini` are excluded AT THE ROOT ONLY (`host_skip_dirs`). Under that SAME
marker, and at the root only too, the kit's own code roots go with them —
`agentic_v3`, the V3 engine, which travels with the kit and would otherwise be
counted as the consumer's own code. The kit's own repository carries the NEGATIVE
marker `.agents/IS_THE_KIT` (`KIT_MARKER`), which OVERRIDES either vendoring
marker: there `host_skip_dirs` returns the empty set and all of those directories
stay indexed, because there they are the source code. That marker is `strip:`-ed
in `.template-exclude`, so it never reaches a consumer through the template.
`--unskip` re-includes one of the HOST directories; it accepts nothing else, so a
`KIT_CODE_DIRS` root is not re-includable by any flag.

IDENTITY IS (path, name, kind, ORDINAL) — the same key the SQLite store has
keyed on since its v2 schema (v3 adds `body_sha` and moves no key). A file
legitimately carries several symbols of the same name AND kind, and a key
without the ordinal collapsed such a group and let all but one of them leave the
index WITHOUT a tombstone at the next build (T-00000122). The ordinal
numbers a group by increasing start line; the start line itself is deliberately
NOT in the key, so shifting code down a file moves no SYM-ID. See `identity_keys`.

Publication is ATOMIC: every artefact is staged in a temp file next to its
target and moved in with ``os.replace``, nothing is ever truncated first, and
the SYM-ID bound is reserved BEFORE the first publish — a build killed mid-run
leaves the previous index readable and can never re-issue an id that is already
cited (L-021 / L-022 / L-023).

Exit codes: 0 = published, or a benign degradation (nothing to rebuild, build
already in flight, failure BEFORE the first publish). 1 = a mixed-generation
publish only a re-run converges, or a refusal to re-ID after the identity source
was lost. The stdout marker line, not the code, says which. Exit 2 is never
used by the build itself: from a Stop hook it makes the host loop. (argparse's own
usage errors — a malformed `--threshold`, an out-of-vocabulary `--unskip` — do exit
2, as they always have; no hook passes those flags.)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

SRC_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".java", ".go",
    ".rb", ".rs", ".swift", ".kt", ".kts", ".c", ".cc", ".cpp", ".h",
    ".hpp", ".cs", ".php", ".scala", ".m", ".mm",
    # T-00000102: a front-end project's stylesheets are half of what it visibly
    # IS, and the index described an application it could not see. `.css` ONLY,
    # deliberately — see CSS_EXT for the arbitration and for why .scss/.less are
    # a NAMED gap rather than three more entries on this line.
    ".css",
    # T-00000541: shell IS this kit's application layer (hooks, gates, CI), and
    # 78 tracked `.sh` had no symbol row at all. Unlike Sass/Less (T-00000143,
    # see CSS_EXT), no extractor is owed here — universal-ctags parses Sh
    # natively — so the shell joins `.java`/`.go` on this line. BOUND: with no
    # universal-ctags on PATH, `extract_file` returns [] and the shell yields
    # zero symbols IN SILENCE.
    ".sh",
}
PY_EXT = {".py"}
JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
# SCSS/Sass/Less are NOT here, and that is a decision, not an omission: they add
# a SECOND variable syntax (`$x`, `@x`) that is not a CSS custom property, and
# arbitrary nesting, which makes "top-level rule" — half of what the extractor
# below keys on — mean something different. That is another extractor, not a
# wider extension set, and shipping this one half-right on those files would put
# wrong rows in the index rather than no rows.
CSS_EXT = {".css"}
SKIP_DIRS = {
    ".git", "node_modules", "vendor",
    # `.agents` A QUITTÉ CET ENSEMBLE le 2026-09-09 — voir SKIP_PREFIXES et
    # KIT_CODE_DIRS juste en dessous. Il y était pour écarter les rapports SCA,
    # qui vivent sous `.agents/state/local/` ; mais `SKIP_DIRS` élague PAR NOM À
    # TOUTE PROFONDEUR, donc il emportait aussi `.agents/bin/`,
    # `.agents/security/`, `.agents/evals/` et `.agents/skills/` — 100 fichiers
    # source de l'outillage du kit, sans une entrée symbolique.
    # ".sca-reports" stays for projects not yet migrated to the new layout.
    "venv", ".venv", "__pycache__", ".sca-reports", "coverage",
    # build output and dependency trees that are routinely committed
    ".next", ".nuxt", ".svelte-kit", ".output", ".gradle", ".terraform",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "Pods", "DerivedData", "bower_components", "third_party",
    "site-packages", "migrations", "__snapshots__",
}
# --- vendored-kit discrimination (T-00000062) --------------------------------
# The SAME directory has two statuses depending on the repo it sits in. In THIS
# repository `.codex/hooks/*.py` and `.gemini/hooks/*.py` ARE the source code —
# the kit maintains itself there, and indexing them is correct. In a CONSUMER
# project they are vendored plumbing: nobody navigates to them, a kit upgrade
# overwrites them, and they crowd out the project's own code in the file the
# golden rule makes agents read FIRST (measured on one consumer: 145 of 472
# symbols, ~31 %, with `.codex` ranking 2nd and `.gemini` 4th by size — ahead of
# `app`, `components` and `lib`).
#
# So the discriminator is NOT the directory name, it is the presence of a
# VENDORING MARKER at the root of the tree being indexed. SKIP_DIRS is
# deliberately left untouched: the kit's own index keeps every symbol it has
# today, and consumers are cleaned retroactively with nothing to reinstall.
HOST_DIRS = frozenset({".claude", ".codex", ".gemini"})
# `.github` is NOT in this set on purpose: a consumer's own JS action or CI
# scripts plausibly live there, and it is not vendored kit plumbing.
#
# KIT CODE ROOTS — the same discriminator, a different reason. `agentic_v3` is
# the kit's V3 engine, and it TRAVELS: no `.template-exclude` rule covers it and
# none should, since it is part of the deliverable. So in a consumer project its
# symbols are indexed as that project's own code, in the very file the golden
# rule makes agents read FIRST. In THIS repository it is the source we maintain,
# and the absence of a marker keeps it indexed — which is why the exclusion hangs
# off the marker rather than off the directory name, exactly like HOST_DIRS, and
# applies AT THE ROOT ONLY for the same monorepo reason.
#
# Deliberately NOT reachable through `--unskip`. A host directory can plausibly
# hold wiring a consumer wants back in their index; a kit code root never holds
# the consumer's code, so re-including it could only ever push the kit's engine
# back in. Same reasoning that keeps `.agents` unreachable (L-020).
KIT_CODE_DIRS = frozenset({"agentic_v3", ".agents", "core-scripts", ".githooks", "src/cadre"})
#
# `core-scripts` ET `.githooks` Y ENTRENT LE 2026-09-09, et c'est LE geste qui délivre
# ce que le renommage T-00000403 rendait seulement POSSIBLE : chez un adoptant, la
# plomberie du kit sort de SON index. POURQUOI IL FALLAIT RENOMMER D'ABORD. `scripts/`
# est un nom de répertoire projet COURANT : l'exclure aurait effacé le
# `scripts/deploy.sh` d'un adoptant qui en a un, puisque chez lui le kit se FOND dans
# son propre `scripts/`. `core-scripts` ne collisionne avec rien, donc l'exclusion
# devient sûre. C'est tout l'objet de T-00000403, et sans cette ligne-ci ce renommage
# n'aurait rien livré du tout.
#
# `.githooks` : mesuré, il VOYAGE (aucune règle de `.template-exclude` ne le
# vise) et n'était couvert par aucun discriminant. Sans lui ici, un module
# `.githooks` naîtrait dans le `CODEBASE_INDEX.md` de chaque adoptant — le
# fichier injecté à CHAQUE session — pour UN seul symbole.
#
# CE QUE ÇA NE RETIRE PAS À L'ADOPTANT, et la distinction est le point : les deux
# répertoires continuent d'être LIVRÉS et de fonctionner chez lui. `.githooks`
# reste une offre opt-in (`git config core.hooksPath .githooks`), et
# `core-scripts/verify.sh` reste sa porte de vérification. Seul l'INDEX les
# ignore. Vérifié : `KIT_CODE_DIRS` n'est lu que par ce module, jamais par
# `sync_template.py` — ce qui voyage est décidé par `.template-exclude`, et rien
# n'y vise ces deux répertoires.
#
# `.agents` A REJOINT CET ENSEMBLE le 2026-09-09 (T-00000251 / T-00000539), et
# le déplacement est le cœur de la correction. Il était dans `SKIP_DIRS`, donc
# élagué PAR NOM À TOUTE PROFONDEUR, POUR TOUT LE MONDE — y compris pour le kit
# lui-même. Conséquence, mesurée : `.agents/bin/tasks.py`, `.agents/bin/events.py`
# et leurs 98 voisins n'avaient AUCUNE entrée symbolique, alors que la règle d'or
# ordonne à tout agent de partir de l'index. Un planificateur planifiait donc
# contre un index AVEUGLE sur le code qu'il devait modifier, pendant que le
# critic, qui lit les fichiers directement, découvrait l'écart. C'est L-020, écrite
# à l'époque de T-005 et jamais payée : « un agent qui cherche un test du kit via
# SYMBOLS.md ne le trouvera pas ».
#
# Ici, il se comporte comme `agentic_v3` : exclu À LA RACINE SEULEMENT et UNIQUEMENT
# chez un adoptant (marqueur de vendoring), indexé dans le dépôt du kit. Un
# `packages/x/.agents/` de monorepo reste donc indexé, là où l'ancien élagage par nom le
# supprimait. NON RÉ-INCLUABLE par `--unskip`, et c'est voulu : chez un adoptant,
# `.agents/` ne contient jamais SON code, seulement la plomberie du kit — exactement
# l'argument qui vaut pour `agentic_v3`, et ce que L-020 demandait de préserver.
#
# LA BOUCLE QUE L-020 REDOUTAIT est refermée séparément, par `SKIP_PREFIXES` :
# « attention : cela réindexerait aussi state/, ce qui créerait une boucle
# index-qui-s-indexe ».
#
# `src/cadre` Y ENTRE avec T-00001100 (relevé de migration ec-crm-multi) : le noyau du
# kit VOYAGE sous ce chemin (aucune règle de `.template-exclude`) et comptait chez
# l'adoptant comme SON code. Première racine à DEUX segments : préfixe ancré (`_keep`).

# EXCLUSIONS PAR CHEMIN — troisième règle de profondeur, et la seule qui juge un
# PRÉFIXE plutôt qu'un nom de segment.
#
# POURQUOI ELLE EXISTE PLUTÔT QU'UNE ENTRÉE DE PLUS DANS `SKIP_DIRS` : y mettre
# `state` élaguerait n'importe quel répertoire nommé `state` À TOUTE PROFONDEUR —
# le `src/state/` d'un adoptant disparaîtrait de son propre index. Le nom est
# banal ; le chemin ne l'est pas.
#
# CE QU'ELLE ÉCARTE : les stores générés du kit — index publié, board, journaux,
# rapports SCA. Les indexer créerait la boucle index-qui-s-indexe nommée par
# L-020, et ferait de chaque écriture du board un changement d'index.
SKIP_PREFIXES = frozenset({".agents/state"})
KIT_VENDOR = ".agents/vendor"  # racine seule, SAUF du `vendor` de SKIP_DIRS (T-01M5BXTGX5YN8XEXTG1PP7A5ZX)
# Either marker counts (see host_skip_dirs): the shared one is honoured by all
# four hosts' path guards, the Claude-only one is what README-CLAUDE.md's
# enforcement table has always pointed at, so a consumer who followed the doc
# must be covered too.
VENDOR_MARKERS = (
    Path(".agents") / "protected-paths.local",
    Path(".claude") / "hooks" / "protected-paths.local",
)
#
# THE NEGATIVE MARKER (T-00000513). The two files above were readable as "this
# tree is a consumer" only as long as they meant nothing else. On 2026-09-06
# `.agents/protected-paths.local` acquired a SECOND meaning — it also carried the
# path-guard patterns of the local dev route, since retired (T-00000493) — so the kit's own repository grew a
# reason to hold the file while still being the kit. The measured consequence: the
# marker appeared here, `host_skip_dirs` read it as vendoring evidence, and the
# kit's index fell from 482 symbols to 64, tombstoning 427 rows of its own source.
#
# The defect was that ONE file answered TWO questions. So identity gets a signal
# of its OWN, and it is negative: present in the kit, absent everywhere else. It
# takes PRECEDENCE over either vendoring marker (see `host_skip_dirs`), which is
# what makes a guard file's second meaning harmless — whatever else lands in a
# `.local` file, the kit stays the kit.
#
# It never travels: `strip: .agents/IS_THE_KIT` in `.template-exclude` keeps it
# off the template branch. That bounds the mirror-image risk without removing it
# — a hand-copied marker WOULD make a consumer index its own plumbing — so the
# file says so in its own body and QUICK-SETUP.md § 3 names it as not-to-copy.
# Presence-only, exactly like the markers above: the content is never read.
KIT_MARKER = Path(".agents") / "IS_THE_KIT"
# Names that mean "build output" next to a manifest and mean SOURCE anywhere
# else. Skipping them unconditionally silently deleted whole layers from the
# index: hexagonal/ports-and-adapters code lives in `adapter/in/` and
# `adapter/out/`, Rust binaries in `src/bin/`, Go commands in `cmd/.../out`.
# They are pruned only where a build actually produces them — a sibling
# manifest — or at the repo root.
AMBIGUOUS_BUILD_DIRS = {"build", "target", "out", "bin", "dist", "obj", "Debug",
                        "Release"}
BUILD_SIBLING_MANIFESTS = (
    "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    "pom.xml", "package.json", "Cargo.toml", "Makefile", "CMakeLists.txt",
    "go.mod", "tsconfig.json", "pyproject.toml",
)
# Machine-written files. They are legitimate source by extension but carry no
# symbol a human would ever navigate to, and minified bundles are single lines
# of 200k characters that dominate scan time.
SKIP_FILE_RE = re.compile(
    r"(\.min\.[cm]?js$|\.bundle\.[cm]?js$|[-.]generated\.|_pb2?\.py$|_pb\.go$"
    r"|\.pb\.go$|\.g\.dart$|\.designer\.cs$|\.d\.ts$"
    # Stylesheet build output. The NAME rule is free and also keeps the file out
    # of the source COUNT; it is not sufficient on its own — measured, this
    # repo's own bundle is `ui/assets/app.css`, matching no name rule at all —
    # so `_css_is_machine_written` catches the rest by shape.
    r"|\.min\.css$|\.bundle\.css$)", re.I)
# A source file past this is generated, vendored or a data blob — never
# something the index should carry.
MAX_FILE_BYTES = 1_500_000

# Structural kinds only. ctags emits every declaration it can see, including
# locals, fields and per-file `package` tags — on a 500k-LOC repo that is 3-4x
# more tags than there are symbols worth addressing, and the index stops fitting
# in a context window. Names are ctags kind NAMES (language-agnostic), so this
# stays correct without per-language --kinds-<LANG> flags. Override: --kinds.
CTAGS_KINDS = {
    "function", "func", "method", "singletonMethod", "subroutine",
    "class", "interface", "struct", "enum", "trait", "protocol",
    "namespace", "module", "type", "union", "record", "object",
    "constant", "const",
}
# Files per `ctags -L` invocation. One process per file costs ~15 ms of pure
# spawn overhead (measured, Windows) — 10k files would be ~2.5 min of nothing.
# Batched, the same 2683 files parse in ~1.3 s.
CTAGS_CHUNK = 800
# `+e` (end line) is free: measured identical to `+n` on 2683 files, warm cache
# (~1.3 s both). Keep it — where a parser reports a real end we want it, and
# _derive_ends only has to cover the parsers that don't (TS/JS, Ruby, PHP, C#).
CTAGS_FIELDS = "--fields=+ne"
# .py never goes to ctags: the stdlib ast extractor is exact and, unlike ctags,
# applies the "skip private helpers under 20 lines" rule the index depends on
# to stay small. Not a speed choice — ctags handles Python fine.
#
# .css joins it for the SAME reason, and this exclusion is load-bearing rather
# than a preference (MEASURED, universal-ctags 6.2.0). ctags DOES parse CSS, and
# both halves of what it returns are wrong for this index:
#   * it emits ZERO tags for custom properties — 0 of the 32 in this repo's own
#     `tokens.css`. The design tokens, the single most valuable thing in a
#     stylesheet and the one `frontend-fidelity` is told to resolve Figma
#     variables against, are exactly what it cannot see.
#   * its selector tags carry kind `class`, which IS in CTAGS_KINDS. So `.css`
#     added to SRC_EXT alone would not be a no-op: it would pour 146 selector
#     rows out of one 223-line file (`views.css`) into the index while still
#     indexing no token at all — a symbol every 1.4 lines, ~20x the density of
#     the .py files around it.
# Without this line `extract_file` would return those ctags rows and the
# extractor below would never run on the files that need it most.
CTAGS_SKIP_EXT = PY_EXT | CSS_EXT

# --- layout -----------------------------------------------------------------
# Generated index artefacts and hand-maintained reference data live in separate
# buckets: everything under .agents/state/ is written by this script, .agents/ref/
# is never written here (only read, for the conventions listing).
STATE_INDEX_REL = Path(".agents") / "state" / "index"
REF_REL = Path(".agents") / "ref"
MAIN_NAME = "SYMBOLS.md"
DELTA_NAME = "INDEX_DELTA.json"
# The body-hash side map (T-00000377). A LATERAL file, deliberately, and not a
# field on the SYM-NNN row: `ACTIVE_RE` anchors the end of the row, so any extra
# field would make `_parse_rows` SKIP the line IN SILENCE — every symbol would
# come back as new and every `:: purpose` and past `SYM-NNNN` citation would go
# orphan. It is also invisible to every existing reader (`classify_index_files`
# and `drop_stale_shards` glob `SYMBOLS_*.md` only), and it carries NOTHING but
# `{id: sha}` — no name, no path, no line range, no source text — which is what
# keeps the bash suite's seven "this must appear NOWHERE in the index" greps
# standing.
BODIES_NAME = "INDEX_BODIES.json"
# The normalisation, NAMED, so a future change to it is a change of NAME rather
# than a silent re-interpretation of hashes already on disk.
BODY_ALGO = "sha256-16-rstrip"
# The stamp `header()` writes when there is no git sha. The lateral must carry
# the SAME string, or its generation could never match the files' on a non-git
# tree and the map would read as UNKNOWN forever.
NO_GIT_STAMP = "nogit"


def index_dir(root):
    """Where every generated index artefact is written."""
    return Path(root) / STATE_INDEX_REL


def ref_dir(root):
    """Hand-maintained reference data — read-only from here."""
    return Path(root) / REF_REL


def _read(path):
    """Text of `path`, or None when it does not exist / cannot be read."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# --- atomic publish ---------------------------------------------------------
# Every artefact is staged in a temp file IN THE TARGET DIRECTORY (same
# filesystem, so the move is a rename) and published with os.replace, atomic on
# POSIX and on Windows. Nothing is truncated first: the previous generation stays
# whole until the instant it is superseded. The old code emptied every shard
# before rewriting it, so a build killed in between left empty symbol files, the
# next run read max_id=0 and re-issued every SYM-ID — silently, at exit 0 (L-021).
#
# The prefix must match NEITHER SHARD_GLOB nor the `SYMBOLS*.md` greps used by the
# test suite and the agents, or a staging file would be read as an index shard.
TMP_PREFIX = "._tmp_"

# L-00000054 (measured, GATE B of T-00000025): on Windows a bare os.replace
# fails with PermissionError 69-81% of the time while a concurrent reader
# merely holds the target open — and since the dashboard shipped,
# CODEBASE_INDEX.md HAS a frequent reader (`/api/snapshot` stats it on every
# 5s poll and re-reads it when the memo key moves, T-01M4XR9ESW), so "readers
# are rare" no longer holds for this publisher (T-00000036). Bound proven
# sufficient on this host: 5-8 retries max ever needed; exhaustion re-raises —
# a publish that cannot land is a loud failure, never a silent partial.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01


def _replace_with_retry(src, target):
    last = None
    for _ in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(_REPLACE_DELAY_SECONDS)
    raise last


class _Publisher:
    """Stages and publishes artefacts, and remembers how far publishing got.

    `replaced` is the publish-progress flag the exit-code policy in `cli()`
    reads: 0 means nothing on disk has changed yet (a failure there is benign —
    the previous index is intact), >0 means the artefacts on disk no longer
    belong to a single generation and only a re-run converges them.
    """

    def __init__(self):
        self.replaced = 0
        self.staged = set()

    def write(self, target, text):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=TMP_PREFIX,
                                   suffix=".part")
        self.staged.add(tmp)
        try:
            # `newline="\n"` forces LF on EVERY platform. `.gitattributes` pins
            # `eol=lf` for these artefacts, but the text-mode default translates
            # `\n` to the platform separator on write — CRLF under Windows — so a
            # Windows build dirtied the whole index in the working tree at every
            # run (L-00000277). This `write` is the SINGLE publication channel —
            # MAIN, shards, annotate targets, DELTA and BODIES all pass through it
            # — so one `newline` covers every text artefact. The byte identity
            # with `Path.write_text` this comment once claimed was FALSE on
            # Windows by construction (L-00000111): a doc must not assert a
            # guarantee the code does not hold.
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            # mkstemp creates 0600. A published index only its writer can read
            # breaks every other tool in the pipeline, so carry the target's mode
            # over when it exists and fall back to a plain 0644 when it does not.
            try:
                mode = stat.S_IMODE(os.stat(str(target)).st_mode)
            except OSError:
                mode = 0o644
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass  # exotic filesystem — not worth failing a publish over
            _replace_with_retry(tmp, str(target))
        except BaseException:
            self._discard(tmp)
            raise
        self.staged.discard(tmp)
        self.replaced += 1
        return target

    def _discard(self, tmp):
        self.staged.discard(tmp)
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def cleanup(self):
        """Unlink whatever was staged but never published (call from a finally)."""
        for tmp in sorted(self.staged):
            self._discard(tmp)


# --- SYM-ID watermark -------------------------------------------------------
# INDEX_DELTA.json carries `max_sym_id`: the highest id ever ALLOCATED. It is an
# UPPER BOUND, and three rules keep it safe (L-022):
#   1. reserved in phase 1, BEFORE the first publish. Written last, it can sit
#      below ids already on disk and already cited, and the next build then hands
#      the same id to a different symbol — worse than restarting at 1, because
#      nothing looks wrong.
#   2. monotone: max(previous, computed), never a decrease.
#   3. a missing file, an unparseable one or a missing key means "no known
#      bound", NEVER zero — zero would let one build over empty shards destroy
#      the protection permanently.
WATERMARK_KEY = "max_sym_id"


def read_delta_bound(root):
    """Reserved SYM-ID upper bound from INDEX_DELTA.json, or None if unknown."""
    raw = _read(index_dir(root) / DELTA_NAME)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get(WATERMARK_KEY)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def reserve_watermark(root, computed_max, pub):
    """Phase 1: raise the on-disk bound to cover `computed_max`, before publish.

    The previous payload is preserved and only the bound is touched, so the
    reservation survives a build that dies before write_delta. This writer
    creates the index directory itself: on a bare tree it is the FIRST writer,
    and write_delta never had a mkdir of its own.
    """
    idx = index_dir(root)
    idx.mkdir(parents=True, exist_ok=True)
    payload = {}
    raw = _read(idx / DELTA_NAME)
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
    previous = read_delta_bound(root)
    value = max(previous or 0, int(computed_max), 0)
    payload[WATERMARK_KEY] = value
    pub.write(idx / DELTA_NAME, json.dumps(payload, indent=2) + "\n")
    return value


# --- SYMBOLS.md grammar (must match the indexer agent definition) ----------
ACTIVE_RE = re.compile(
    r"^(SYM-\d+)\s+(\S+):(\d+)-(\d+)\s+(\S+)\s+(\S+)\s+uses\[([^\]]*)\]\s*(?:::\s*(.*))?$"
)
DELETED_RE = re.compile(r"^(SYM-\d+)\s+DELETED\s+(\S+)\s+(\S+)\s*$")
SHARD_GLOB = "SYMBOLS_*.md"
# Rows per shard. Sharding by module alone is not enough: a single large module
# produces a shard nobody can read in one pass, which is the problem sharding
# exists to solve.
MAX_SHARD_ENTRIES = 2000


# --------------------------------------------------------------------------- git
def git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True,
        )
    except (OSError, FileNotFoundError):
        return None
    return r.stdout if r.returncode == 0 else None


def is_git(root):
    return git(root, "rev-parse", "--git-dir") is not None


def head_sha(root):
    out = git(root, "rev-parse", "--short", "HEAD")
    return out.strip() if out else None


# ------------------------------------------------------------------------- scope
def host_skip_dirs(root, unskip=()):
    """The kit directories to exclude AT THE ROOT of `root`, or an empty set.

    EXACT SCOPE, stated so nobody has to infer it: this returns a non-empty set
    for exactly those repositories carrying, at the root of `root`, one of
    `VENDOR_MARKERS` — `.agents/protected-paths.local` OR
    `.claude/hooks/protected-paths.local` — AND NOT carrying `KIT_MARKER`
    (`.agents/IS_THE_KIT`). Either vendoring marker is enough; both may exist.
    Every other repository gets `set()` and is indexed exactly as before.

    PRECEDENCE, kit OVER vendor, and it is checked FIRST: the kit's own repository
    DOES carry `.agents/protected-paths.local` — from 2026-09-06 that file also
    held the guard patterns of the local dev route, since retired — so it is not a tree that "carries
    neither". What keeps it indexed is `.agents/IS_THE_KIT`, which short-circuits
    to `set()` before the vendoring markers are looked at at all. Read the order
    below as the guarantee: no content a guard file may acquire can ever make the
    kit blind to its own source again (T-00000513, which is what that
    misreading actually cost: 482 symbols down to 64).

    PRESENCE-ONLY FOR BOTH MARKERS: a consumer who copies `.agents/IS_THE_KIT` by
    hand indexes their own vendored plumbing, and their push gate runs the KIT's
    suite (T-00001183). Bounded, not prevented: the file names the remedy, the
    template strips it (`.template-exclude`), and QUICK-SETUP.md says not to copy
    it.

    TWO SETS, ONE MARKER: `HOST_DIRS` (vendored host wiring) and `KIT_CODE_DIRS`
    (the kit's own code, e.g. the V3 engine). They are excluded together because
    the question they answer is the same one — "is this tree a consumer of the
    kit, or the kit itself?" — but only `HOST_DIRS` is ever re-includable. That
    last guarantee is enforced by the CLI's CLOSED vocabulary (`--unskip` rejects
    anything outside `HOST_DIRS` before a build starts), not by the subtraction
    below; said here rather than implied, because a reader of this line would
    otherwise have to guess which of the two layers holds it.

    ONLY THE PRESENCE of a marker is read here — either kind — never its content.
    That is deliberate, and slightly loose, coupling: the path guards parse the
    vendoring file for prefixes, so an EMPTY marker protects zero paths while
    still being evidence about the tree it sits in. We would rather exclude the
    plumbing of a consumer who emptied the file than index the plumbing of every
    consumer who never listed a prefix. Reading CONTENT to answer "is this the
    kit?" was considered and refused (T-00000513): no content is invariant across
    consumers, and a consumer who legitimately empties the file would then be
    re-indexed WITH their plumbing — the very case this loose coupling covers.

    Pure: no global is read or written, so two roots handled in one process (the
    dashboard imports this module; the tests call `cli()` in-process) can never
    leak scope into each other.
    """
    root = Path(root)
    # KIT FIRST: the negative marker wins over any vendoring marker (T-00000513).
    if (root / KIT_MARKER).is_file():
        return set()
    if not any((root / marker).is_file() for marker in VENDOR_MARKERS):
        return set()
    return (set(HOST_DIRS) | set(KIT_CODE_DIRS)) - set(unskip)


def scope_fingerprint(host_skip):
    """Digest of the EFFECTIVE directory-exclusion scope, for the header stamp.

    Covers all three ingredients that decide which directories are pruned — the
    root-only host set, `SKIP_DIRS` (pruned at any depth) and the fact that the
    two are applied with DIFFERENT depth rules — so that editing `SKIP_DIRS`
    also invalidates a published index instead of silently leaving it narrower or
    wider than the code that reads it. It is a digest of the RULES, not of the
    resulting file list.

    `KIT_CODE_DIRS` needs NO code change here and gets none: it reaches the digest
    through `host_skip`, already folded in under `rootonly:`. That is what makes
    the correction land on a consumer who is ALREADY indexed — the fingerprint
    moves, `reconcile` forces one full rebuild with `purge=True`, and the kit-code
    rows are tombstoned instead of lingering as symbols no incremental would ever
    revisit.

    IT ALSO COVERS `SRC_EXT`, and that inclusion is what makes T-00000102 actually
    LAND. Widening the extension set widens the file set, but an incremental build
    only ever scans CHANGED files — so without this, a consumer adding `.css`
    would index a stylesheet the day someone edited it and leave every OTHER
    stylesheet invisible indefinitely, which is the same shape of empty promise
    T-00000104 removes from the summary. Folded in here, the existing `dirscope`
    comparison forces exactly ONE full rebuild and the coverage is real. The
    header field keeps the name `dirscope` on purpose — `built @`-adjacent fields
    may not move (see `build_stamp`) and `published_dirscope` reads an absent field
    as the pre-field default — so the NAME is now slightly narrower than what it
    digests. That is the honest trade and it is written down rather than inferred.
    """
    # `SKIP_PREFIXES` entre ici le 2026-09-09, et il DOIT y entrer : c'est une
    # QUATRIÈME règle de profondeur. Sans elle dans l'empreinte, sortir `.agents`
    # de `SKIP_DIRS` déplacerait le périmètre sans invalider un index publié —
    # exactement la panne silencieuse que ce digest existe pour empêcher, et que
    # sa propre docstring décrit pour `SKIP_DIRS`.
    # LE BUILDER LUI-MÊME ENTRE ICI (T-00000606), et c'est une régression
    # ADOPTANT que ça ferme — mesurée des DEUX côtés par le binôme de clôture.
    #
    # LE DÉFAUT. Depuis que `index_is_current` ne compare plus `built @` à HEAD
    # (T-00000575), plus rien ne portait un changement du BUILDER : ni `SRC_EXT`,
    # ni `SKIP_DIRS`, ni `SKIP_PREFIXES` ne bougent quand on touche
    # `SKIP_FILE_RE`, `MAX_FILE_BYTES`, `AMBIGUOUS_BUILD_DIRS`, un extracteur ou
    # la mise en page. Sur le KIT c'était masqué — `.agents/bin/*.py` est
    # lui-même indexé, donc dans le scope. Sur un dépôt ADOPTANT, où `.agents`
    # est dans `host_skip`, un upgrade du kit qui change ce qui est indexé
    # n'atterrissait JAMAIS par `--if-stale`. Avant le retrait du sha il
    # atterrissait, puisque tout upgrade avançait HEAD : c'est donc une
    # régression, pas un trou ancien.
    #
    # LE DIGEST DU FICHIER PLUTÔT QU'UNE CONSTANTE À BUMPER, et c'est la mesure
    # qui a tranché, pas le goût. Une constante `BUILDER_FP = "2026-09-14-a"`
    # coûte zéro mais repose sur la mémoire humaine — la famille de défaut que ce
    # dépôt traque. Le digest est EXACT et sans mémoire ; son seul coût est de
    # forcer une reconstruction COMPLÈTE à chaque commit du builder. Relevé le
    # 2026-09-14 sur ce dépôt : reconstruction complète **3,02 s** contre
    # **0,26 s** en incrémental, et **6 des 200 derniers commits** (3 %) touchent
    # `build_index.py` — 18 sur 1028 dans tout l'historique. L'exactitude coûte
    # donc environ **17 secondes par 200 commits**. C'est payé.
    #
    # BORNE : ça couvre le builder, PAS les modules qu'il importe. Un changement
    # dans un extracteur qui vivrait ailleurs ne serait toujours pas vu. Dit
    # plutôt que découvert — aujourd'hui tout est dans ce fichier.
    try:
        builder = hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest()[:12]
    except OSError:
        # Illisible : on rend une valeur CONSTANTE plutôt que de lever. Une
        # exception ici coûterait l'index entier pour une lecture ratée, et la
        # direction sûre est « rien n'a changé côté builder » — les quatre
        # autres champs continuent de décider.
        builder = "nonlu"
    payload = ("anydepth:" + ",".join(sorted(SKIP_DIRS))
               + "|prefixes:" + ",".join(sorted(SKIP_PREFIXES))
               + "|rootonly:" + ",".join(sorted(host_skip))
               + "|ext:" + ",".join(sorted(SRC_EXT))
               + "|builder:" + builder)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def scope_caveat(host_skip):
    """One sentence naming what this index does NOT cover — DERIVED, not static.

    The dashboard and the UI panel state a coverage limit to their reader; that
    statement has to follow the scope actually applied, otherwise it becomes the
    misleading kind of caveat the moment the scope moves.
    """
    # RÉÉCRIT le 2026-09-09 : l'ancienne phrase affirmait que « THIS kit's own
    # tooling and tests have no symbolic entry at all ». Depuis que `.agents` a
    # quitté `SKIP_DIRS`, c'est FAUX dans le dépôt du kit — et une phrase de
    # couverture qui ment est précisément ce qui empêche de voir le défaut
    # suivant (L-00000111).
    stores = ", ".join(f"'{p}/'" for p in sorted(SKIP_PREFIXES))
    if not host_skip:
        return (f"{stores} is excluded (generated stores: published index, board, "
                "journals, SCA reports — indexing them would make the index index "
                "itself, L-020). The kit's own tooling under '.agents/' IS indexed "
                "here since 2026-09-09; a consumer gets it excluded at the repo "
                "ROOT instead, as vendored plumbing.")
    listed = ", ".join(f"'{d}'" for d in sorted(host_skip))
    return (f"{stores} is excluded at any depth and {listed} at the repo ROOT "
            "(vendored kit plumbing and kit code roots, detected via a vendoring "
            "marker — '.agents' among them since 2026-09-09, which is how L-020 "
            "keeps holding for a consumer), so host wiring and kit code have no "
            "symbolic entry — by construction, not by staleness.")


_BUILD_DIR_CACHE = {}


def _is_build_output(root, parent_rel, name):
    """True when `<parent_rel>/<name>` is build output rather than source.

    An ambiguous name is output at the repo root (top-level `build/`, `dist/`)
    or next to a manifest that produces it (`domain/build.gradle` -> `domain/
    build/`). Everywhere else it is a package a human wrote — `adapter/out/`,
    `src/bin/` — and pruning it costs the index a whole architectural layer.
    """
    if name not in AMBIGUOUS_BUILD_DIRS:
        return False
    if parent_rel == "":
        return True
    if root is None:
        return False
    hit = _BUILD_DIR_CACHE.get(parent_rel)
    if hit is None:
        base = Path(root) / parent_rel
        hit = any((base / m).is_file() for m in BUILD_SIBLING_MANIFESTS)
        _BUILD_DIR_CACHE[parent_rel] = hit
    return hit


def _under_skip_prefix(rel):
    """Vrai si `rel` EST un préfixe exclu, ou vit dessous.

    Compare SEGMENT PAR SEGMENT, jamais par `startswith` sur la chaîne : un
    `startswith('.agents/state')` nu attraperait aussi `.agents/stateful.py`,
    qui n'a rien à voir. La frontière est le `/`, et elle doit être explicite.

    Les deux chemins d'entrée de l'index l'appellent — `_walk_sources` (élagage
    du parcours) et `_keep` (filtre appliqué à `git ls-files`) — parce que
    `git ls-files` ne passe PAS par `os.walk` : la même leçon que le commentaire
    en tête de `_keep` raconte pour `SKIP_DIRS`.
    """
    parts = rel.replace("\\", "/").strip("/").split("/")
    for prefixe in SKIP_PREFIXES:
        pparts = prefixe.split("/")
        if parts[:len(pparts)] == pparts:
            return True
    return False


def _walk_sources(root, host_skip=()):
    files = []
    for dp, dns, fns in os.walk(root):
        parent = os.path.relpath(dp, root).replace("\\", "/")
        parent = "" if parent == "." else parent
        dns[:] = [d for d in dns
                  if (d not in SKIP_DIRS or f"{parent}/{d}" == KIT_VENDOR) and not _is_build_output(root, parent, d)
                  and (f"{parent}/{d}" if parent else d) not in host_skip
                  and not _under_skip_prefix(f"{parent}/{d}" if parent else d)]
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root).replace("\\", "/")
            files.append(rel)
    return files


def _keep(rel, root=None, host_skip=()):
    # SKIP_DIRS used to apply only to the os.walk path — `git ls-files` sailed
    # straight past it, so committed vendor/ and generated/ trees were indexed.
    parts = rel.replace("\\", "/").split("/")
    if Path(rel).suffix not in SRC_EXT:
        return False
    # Préfixes exclus — ici AUSSI, et pas seulement dans `_walk_sources` :
    # `git ls-files` est le chemin nominal et ne passe jamais par `os.walk`.
    if _under_skip_prefix(rel):
        return False
    # `host_skip` is applied AT THE ROOT ONLY, like _is_build_output's ambiguous
    # names: a ROOT-ANCHORED prefix cut at `/` (`src/cadre`, never `src/cadre_x`),
    # never per segment like the SKIP_DIRS loop below — `packages/x/.codex/` in a
    # monorepo is a workspace a human wrote; pruning it would delete a real layer.
    if any("/".join(parts[:i]) in host_skip for i in range(1, len(parts))):
        return False
    for i, part in enumerate(parts[:-1]):
        if (part in SKIP_DIRS and "/".join(parts[:i + 1]) != KIT_VENDOR) or _is_build_output(root, "/".join(parts[:i]), part):
            return False
    if SKIP_FILE_RE.search(parts[-1]):
        return False
    if root is not None:
        try:
            if (root / rel).stat().st_size > MAX_FILE_BYTES:
                return False
        except OSError:
            pass  # missing (deleted in the diff) — the caller tombstones it
    return True


def all_source_files(root, host_skip=()):
    out = git(root, "ls-files")
    files = out.splitlines() if out is not None else _walk_sources(root, host_skip)
    return sorted(f for f in files if _keep(f, root, host_skip))


def _changed_names(root, built_sha):
    """Les noms bruts qui ont bougé depuis `built_sha`, ou None si on n'a PAS PU.

    LA DISTINCTION EST TOUT, ET ELLE N'EXISTAIT PAS (T-00000575, binôme du
    2026-09-13, les deux critiques indépendamment). `git()` rend `None` sur
    rc≠0, et le `if out:` d'origine l'avalait : un `git diff` EN ÉCHEC était donc
    indiscernable d'un `git diff` qui ne rend rien, c'est-à-dire d'un « aucun
    fichier indexé n'a bougé ». Tant que la fraîcheur se décidait aussi sur
    `built @ == HEAD`, ce silence était rattrapé par le sha. Depuis que le sha ne
    décide plus, il ne l'est plus par rien.

    SCÉNARIO MESURÉ PAR LE BINÔME : dépôt cloné `--filter=tree:0`, index
    tamponné, trois commits de code récupérés, remote injoignable. `cat-file -e`
    rend 0 — le sha tamponné est bien là — mais `git diff <built> HEAD` échoue
    sur un objet absent. Ancien code : `INDEX STALE`. Nouveau code, sans cette
    fonction : `INDEX CURRENT — nothing to rebuild`, trois fichiers indexés hors
    de l'index et aucune reconstruction au démarrage de session.

    SEULE LA PREMIÈRE JAMBE EST FATALE, et c'est délibéré : elle porte la mesure
    « ce qui a changé entre l'ancre et HEAD ». Les trois autres lisent l'arbre de
    travail, où un échec dégrade la précision sans invalider l'ancrage.
    """
    committed = git(root, "diff", "--name-only", built_sha, "HEAD")
    if committed is None:
        return None
    names = set(committed.splitlines())
    for args in (
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        out = git(root, *args)
        if out:
            names.update(out.splitlines())
    return names


def _non_suivis(root):
    """Les noms NON SUIVIS de l'arbre de travail, ou un ensemble VIDE.

    SÉPARE LES DEUX QUESTIONS QUE `_changed_names` FOND EN UNE (T-00000608,
    décision pilote du 2026-09-14, option b). Cette fonction-là verse les non
    suivis dans le même ensemble que les fichiers suivis qui ont bougé, alors
    que `all_source_files` bâtit l'index depuis `git ls-files` SEUL : un fichier
    non suivi entre donc dans le SCOPE et, en incrémental, dans l'INDEX
    (T-00000230) — un `--full` seul le laisse dehors — et `_changed_names` le
    renomme à CHAQUE sonde, ce qui rend `STALE` pour toujours et fait
    reconstruire à chaque SessionStart sans jamais converger. Mesuré le
    2026-09-14 sur ce dépôt : un résidu de banc de 319 Ko
    laissé par un agent a tenu neuf heures et toute une nuit de sessions, et une
    reconstruction COMPLÈTE ne l'éteignait pas.

    POURQUOI ON NE LES RETIRE PAS DU SCOPE : deux desseins ÉCRITS s'opposent ici,
    et l'un d'eux n'a pas cédé. `StaleCheckTests::test_current_then_stale_then_
    current_again` (T-00000033) épingle que la sonde DOIT dire STALE sur un non
    suivi — elle existe pour pousser à le commiter. Le pilote a tranché qu'aucun
    des deux ne céderait : la SONDE garde son nudge et le NOMME désormais, le
    RAFRAÎCHISSEMENT cesse de tourner à vide. Les deux questions étaient
    confondues, elles ne le sont plus.

    FAIL-OPEN, et dans le sens qui coûte le moins : `git` muet rend un ensemble
    vide, donc AUCUN fichier n'est réputé non suivi, donc on retombe exactement
    sur le comportement d'avant — une reconstruction de trop. L'autre sens
    aurait sauté un rafraîchissement dû.
    """
    out = git(root, "ls-files", "--others", "--exclude-standard")
    return set(out.splitlines()) if out else set()


def changed_source_files(root, built_sha, host_skip=(), stat_root=True):
    """Les fichiers INDEXÉS qui ont bougé depuis `built_sha`, ou None si on n'a
    pas pu mesurer (voir `_changed_names`).

    `stat_root=False` passe `None` à `_keep`, qui cesse alors de STATER l'arbre.
    Le prédicat de fraîcheur en a besoin : avec la racine, un fichier indexé
    devenu plus gros que `MAX_FILE_BYTES`, ou tombé sous un répertoire de build,
    sort du résultat — donc le résultat est vide pour une raison qui n'est PAS
    « rien n'a changé », et `index_is_current` fige des symboles MORTS. Mesuré
    par le binôme sur un dépôt jetable : un fichier indexé porté à 2 000 025
    octets laissait son symbole disparu dans l'index, avec `INDEX CURRENT`.
    La CONSTRUCTION, elle, garde `stat_root=True` : elle doit bien refuser de
    lire un fichier trop gros. Les deux réponses sont justes, à deux questions
    différentes.

    `root` DOIT être un `Path` : `_keep` fait de l'arithmétique de chemin
    (`root / rel`), donc un `str` lève `TypeError` — mesuré. Le voisin
    `dashboard_readers` portait déjà l'avertissement en commentaire, ce qui veut
    dire que le piège avait déjà mordu une fois ; on le rend mécanique plutôt que
    de le redire une troisième."""
    root = Path(root)
    names = _changed_names(root, built_sha)
    if names is None:
        return None
    return sorted(f for f in names
                  if _keep(f, root if stat_root else None, host_skip))


# --------------------------------------------------------------------- existing
TOC_SHARD_RE = re.compile(r"SYMBOLS_[A-Za-z0-9_]+\.md")
IDENTITY_LOST = (
    "build_index: SYMBOLS.md missing or unparseable but shards exist — identity "
    "source lost, refusing to re-ID; restore SYMBOLS.md, delete the shards, or run "
    "--full to rebuild identity deliberately (existing SYM-ID citations will dangle)"
)


def _header_line(text):
    return (text or "").split("\n", 1)[0]


def _header_field(line, name, pattern=r"\S+"):
    """One `<name> <value>` field of a header line, or None."""
    m = re.search(re.escape(name) + r" (" + pattern + r")", line or "")
    return m.group(1) if m else None


def _generation(text):
    """The `built @ <sha>` stamp of a symbol file — its generation marker."""
    return _header_field(_header_line(text), "built @")


def classify_index_files(root):
    """Sort the symbol files on disk by how far they may be trusted (L-023).

    Returns `(authoritative, watermark_only, status)`.

    * `authoritative` — SYMBOLS.md plus every shard its ToC references. Only
      these define identity (by_key / by_id).
    * `watermark_only` — a shard the ToC does NOT reference whose generation
      stamp MATCHES the ToC's: a true leftover of this same generation (a module
      that fell from two parts back to one, or a crossing of the sharding
      threshold). Merging it resurrects stale line ranges and can even undo a
      tombstone — a tombstone is one line, and the shard glob is read
      last-writer-wins — so it contributes to max_id and nothing else, and the
      next successful publish deletes it.
    * a shard the ToC does not reference whose stamp DIFFERS is not a leftover:
      it is residue of a build that died between publishing shards and publishing
      the ToC. It holds the NEWEST identity on disk, so it stays AUTHORITATIVE
      and the re-run reconciles and republishes from it. Downgrading it to
      watermark-only would throw away freshly published ids.

    `status` is "ok", "no-index" (nothing readable, nothing to lose) or
    "identity-lost" (SYMBOLS.md gone or unparseable while shards exist — the
    caller refuses to re-ID, see `_build`).
    """
    idx = index_dir(root)
    main_text = _read(idx / MAIN_NAME)
    shards = sorted(idx.glob(SHARD_GLOB))
    generation = _generation(main_text)
    if main_text is None or generation is None:
        return [], [], ("identity-lost" if shards else "no-index")
    referenced = set(TOC_SHARD_RE.findall(main_text))
    authoritative, watermark_only = [idx / MAIN_NAME], []
    for shard in shards:
        text = _read(shard)
        if text is None:
            continue
        if shard.name in referenced or _generation(text) != generation:
            authoritative.append(shard)
        else:
            watermark_only.append(shard)
    return authoritative, watermark_only, "ok"


def _parse_rows(text):
    """Yield the symbols encoded in a SYMBOLS file, in file order."""
    for line in (text or "").splitlines():
        md = DELETED_RE.match(line)
        if md:
            yield {"id": int(md.group(1)[4:]), "name": md.group(2),
                   "kind": md.group(3), "deleted": True}
            continue
        ma = ACTIVE_RE.match(line)
        if not ma:
            continue
        uses = [int(x[4:]) for x in ma.group(7).split(",") if x.strip().startswith("SYM-")]
        yield {
            "id": int(ma.group(1)[4:]), "path": ma.group(2),
            "start": int(ma.group(3)), "end": int(ma.group(4)),
            "name": ma.group(5), "kind": ma.group(6),
            "uses": uses, "purpose": (ma.group(8) or "").strip(),
            "deleted": False,
        }


def identity_keys(rows):
    """`(path, name, kind, ordinal)` for each row, IN INPUT ORDER.

    THE ORDINAL EXISTS BECAUSE (path, name, kind) IS NOT A KEY. One file
    legitimately carries several symbols of the same name AND kind — homonymous
    local constants across test blocks are the common shape — and a dict keyed on
    the triple collapses them into one entry. Every symbol of a collapsed group
    but one then left the index at the NEXT build without a tombstone: not live,
    not `DELETED`, evaporated, and invisible even in `SYMBOLS_deleted.md`
    (T-00000122; measured 2 losses out of 3 homonyms on a 3-symbol harness).

    `rows` is a sequence of `(path, name, kind, start, tiebreak)`. A
    (path, name, kind) group is numbered 0, 1, 2 … by increasing START line;
    `tiebreak` orders rows that would otherwise compare equal and must be unique
    within a group (the SYM-ID for published rows, the extraction position for
    freshly extracted ones), so the numbering is a total, deterministic function
    of its input and never depends on dict iteration order.

    THE START LINE IS IN THE ORDER, NEVER IN THE KEY. That is the whole design:
    this key re-pairs SYM-IDs across two rebuilds, so a key holding the line
    number would rename every symbol below an inserted function — killing the
    hand-written `:: purpose` annotations keyed on SYM-ID and every `SYM-NNNN` a
    past session wrote down. An ordinal moves only when the RELATIVE order of the
    homonyms themselves changes.

    THE CONVENTION IS MIRRORED, DELIBERATELY, from
    `migrate_index_to_db.assign_ordinals` (the store's key since its v2 schema),
    which keys the SQLite store the same way. Two divergent conventions between
    the producer and the store
    would be a worse defect than the collapse this fixes, so the pair is pinned by
    a test that runs both. It is a mirror rather than an import because migrate
    imports THIS module — the other direction is a cycle.

    ONE DIFFERENCE FROM THE STORE, and it is intended: migrate REFUSES two live
    rows sharing a name, a kind AND a start line (a contradictory index it will
    not represent). This is a PRODUCER on the Stop-hook path — it must always be
    able to publish — so it orders that pair by `tiebreak` and carries on rather
    than failing a build.
    """
    rows = list(rows)
    groups = {}
    for pos, (path, name, kind, start, tiebreak) in enumerate(rows):
        # `start` is None only on a row a caller built without one; sort it first
        # instead of comparing None to an int.
        groups.setdefault((path, name, kind), []).append(
            (-1 if start is None else start, tiebreak, pos))
    keys = [None] * len(rows)
    for group, members in groups.items():
        for ordinal, (_start, _tiebreak, pos) in enumerate(sorted(members)):
            keys[pos] = (*group, ordinal)
    return keys


def load_existing(root, perdants=None):
    """Return (by_key, by_id, max_id). Keys are (path, name, kind, ordinal).

    Identity comes ONLY from the files `classify_index_files` calls
    authoritative; orphan shards of this generation feed max_id alone (L-023).
    max_id is then raised to the reserved watermark — the single place the bound
    is applied — so a lost symbol file never re-issues cited ids (L-021 / L-022).
    Ordinals are computed AFTER `by_id` deduplicated ids: mid-publish residue
    repeats an id, and numbering it twice would lose the higher ordinal.

    ONE ID ON TWO ROWS OF DIFFERENT IDENTITY, A TOMBSTONE INCLUDED (M5, a merge resolved "ours" beside a shard
    only the other side created): the row of a file the ToC cites wins, then a live row over a tombstone, else the
    later file; the loser leaves by_id, named on stderr — a live loser joins `perdants`, the channel `reconcile`
    reads to rescan its file under a fresh id above max_id (never a silent loss); a losing tombstone is dropped.
    """
    by_id, cited_id, max_id = {}, {}, 0
    authoritative, watermark_only, _status = classify_index_files(root)
    toc = set(TOC_SHARD_RE.findall(_read(index_dir(root) / MAIN_NAME) or ""))
    for f in authoritative:
        cited = f.name == MAIN_NAME or f.name in toc
        for sym in _parse_rows(_read(f)):
            max_id, prev = max(max_id, sym["id"]), by_id.get(sym["id"])
            if prev and not (prev["deleted"] and sym["deleted"]) and any(prev.get(k) != sym.get(k) for k in
                    ("name", "kind") + (() if prev["deleted"] or sym["deleted"] else ("path",))):
                keep = (cited_id[sym["id"]], not prev["deleted"]) > (cited, not sym["deleted"])
                lost = sym if keep else prev
                print(f"build_index: {sid(lost['id'])} collision — {lost.get('path', 'DELETED')} {lost['name']}"
                      f" ({lost['kind']}) loses the id, {('rescanned', 'dropped')[lost['deleted']]}", file=sys.stderr)
                if perdants is not None and not lost["deleted"]:
                    perdants.append(lost)
                if keep:
                    continue
            by_id[sym["id"]], cited_id[sym["id"]] = sym, cited
    for f in watermark_only:
        for sym in _parse_rows(_read(f)):
            max_id = max(max_id, sym["id"])
    live = [sym for sym in by_id.values() if not sym["deleted"]]
    keys = identity_keys([(s["path"], s["name"], s["kind"], s["start"], s["id"]) for s in live])
    bound = read_delta_bound(root)
    return dict(zip(keys, live)), by_id, (max_id if bound is None else max(max_id, bound))


# ---------------------------------------------------------------- extraction
def ctags_binary():
    """Resolve universal-ctags: $CTAGS / $CTAGS_PATH first, then PATH.

    The env override matters because hooks and CI can run with a PATH that
    differs from the developer's shell — without it the builder would silently
    degrade to the stdlib fallback and nobody would notice.
    """
    for env in ("CTAGS", "CTAGS_PATH"):
        cand = os.environ.get(env)
        if not cand:
            continue
        resolved = shutil.which(cand) or (cand if Path(cand).is_file() else None)
        if resolved and _is_universal_ctags(resolved):
            return resolved
    found = shutil.which("ctags")
    return found if found and _is_universal_ctags(found) else None


def _is_universal_ctags(binary):
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True)
    except (OSError, ValueError):
        return False
    return r.returncode == 0 and "Universal Ctags" in (r.stdout + r.stderr)


def _tag_to_sym(j, kinds):
    if j.get("_type") != "tag" or "line" not in j:
        return None
    kind = j.get("kind", "symbol")
    if kind not in kinds:
        return None
    # T-00000541: ctags attributes the dotted/bracketed names it finds inside a
    # shell heredoc (`"$PY" - <<'PYEOF'`) to the HOST .sh file. Bounded to `.sh`
    # ON PURPOSE: this helper filters EVERY ctags language, so an unguarded rule
    # would delete bracketed JavaScript members wholesale.
    #
    # THE EXAMPLE THIS COMMENT USED TO GIVE IS NO LONGER LIVE, and saying so
    # costs less than letting the next reader check. It cited
    # `[Symbol.asyncIterator]` as "a row published today"; since T-00000609 took
    # the minified `app.js` bundle out of the index by SHAPE, that name survives
    # only in `SYMBOLS_deleted_1.md` — measured 2026-09-14, zero occurrence in
    # any live SYMBOLS file. The BOUND is unchanged and still load-bearing; what
    # changed is that its illustration became a ghost, and an illustration that
    # no longer exists is how a correct rule starts looking arbitrary.
    if (j.get("path") or "").endswith(".sh") and any(c in str(j.get("name") or "") for c in ".[]"):
        return None
    try:
        start = int(j["line"])
    except (TypeError, ValueError):
        return None
    has_end = str(j.get("end", "")).isdigit()
    end = int(j["end"]) if has_end else start
    return {"name": j["name"], "kind": kind, "start": start,
            "end": max(end, start), "_noend": not has_end}


def _derive_ends(abspath, syms):
    """Fill end lines for parsers that don't report one (TS/JS, Ruby, PHP, C#).

    ctags only emits `end` where the parser implements it. Left alone those tags
    collapse to a single line, which silently breaks both the `uses[…]` body scan
    and the "read only this range" contract of the index.
    """
    if not any(s.get("_noend") for s in syms):
        for s in syms:
            s.pop("_noend", None)
        return syms
    try:
        lines = Path(abspath).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    starts = sorted({s["start"] for s in syms})
    for s in syms:
        if s.pop("_noend", False) and lines:
            end = _block_end(lines, s["start"])
            if end <= s["start"]:
                # No brace block (one-liner, or an indentation language): stop at
                # the next tag in the file, else at EOF.
                nxt = next((x for x in starts if x > s["start"]), None)
                end = (nxt - 1) if nxt else len(lines)
            s["end"] = max(end, s["start"])
    return syms


def extract_ctags_batch(root, rels, binary, kinds):
    """{rel: [sym]} for one `ctags -L` pass per chunk instead of one per file.

    Paths are fed relative with cwd=root, so the JSON `path` field comes back
    exactly as the key we need. stdout is consumed streaming: a full scan of a
    large repo emits enough JSON that buffering it whole is a real memory cost.
    """
    out = {}
    for i in range(0, len(rels), CTAGS_CHUNK):
        chunk = rels[i:i + CTAGS_CHUNK]
        listfile = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                             encoding="utf-8") as fh:
                fh.write("\n".join(chunk))
                listfile = fh.name
            proc = subprocess.Popen(
                [binary, "--output-format=json", CTAGS_FIELDS,
                 "-L", listfile, "-f", "-"],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, errors="replace",
            )
            for rel in chunk:
                out.setdefault(rel, [])
            for line in proc.stdout:
                try:
                    j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sym = _tag_to_sym(j, kinds)
                if sym is None:
                    continue
                out.setdefault((j.get("path") or "").replace("\\", "/"), []).append(sym)
            proc.stdout.close()
            proc.wait()
        except (OSError, ValueError):
            for rel in chunk:
                out.pop(rel, None)  # chunk failed → let the fallback handle it
        finally:
            if listfile:
                try:
                    os.remove(listfile)
                except OSError:
                    pass
    for rel, syms in out.items():
        _derive_ends(root / rel, syms)
    return out


def extract_py(text):
    syms = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return syms

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = child.lineno
                end = getattr(child, "end_lineno", start) or start
                private = child.name.startswith("_")
                if not private or (end - start) > 20:
                    kind = "class" if isinstance(child, ast.ClassDef) else "function"
                    syms.append({"name": child.name, "kind": kind,
                                 "start": start, "end": end})
                if isinstance(child, ast.ClassDef):
                    visit(child)  # one level: methods

    visit(tree)
    return syms


JS_PATTERNS = [
    (re.compile(r"^\s*export\s+default\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*export\s+default\s+class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*export\s+class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="), "const"),
    (re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)"), "class"),
]


MAX_BLOCK_SCAN = 3000  # a single declaration longer than this is pathological


def _block_end(lines, start, stop=None):
    """1-indexed end line: brace-match from `start`, or `start` for one-liners.

    `stop` is the next declaration's start line, and bounds ONLY the case where
    no brace block ever opened: such a declaration with no `;` used to scan to
    EOF, making extraction O(symbols x lines) — a 5000-line bundle with 200
    exports cost millions of character steps. A braced block still scans past
    `stop`, otherwise a function containing a nested one would be truncated at
    the nested declaration.
    """
    limit = min(len(lines), start - 1 + MAX_BLOCK_SCAN)
    depth, started = 0, False
    for idx in range(start - 1, limit):
        for ch in lines[idx]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth <= 0:
                    return idx + 1
        if not started and (";" in lines[idx]
                            or (stop is not None and idx + 1 >= stop)):
            return start
    return limit if started else start


def extract_js(text):
    lines = text.splitlines()
    hits, seen = [], set()
    for i, line in enumerate(lines, start=1):
        for pat, kind in JS_PATTERNS:
            m = pat.match(line)
            if m:
                name = m.group(1)
                if (name, i) in seen:
                    break
                seen.add((name, i))
                hits.append((i, name, kind))
                break
    # Resolve ends in a second pass: each block stops at the next declaration.
    syms = []
    for n, (i, name, kind) in enumerate(hits):
        stop = hits[n + 1][0] if n + 1 < len(hits) else None
        syms.append({"name": name, "kind": kind,
                     "start": i, "end": _block_end(lines, i, stop)})
    return syms


# --------------------------------------------------------------------- CSS
# WHAT A "SYMBOL" IS IN A STYLESHEET (T-00000102). The test is the one every
# other extractor here already passes: a symbol is something an agent ADDRESSES
# BY NAME and navigates to. Applied to CSS that admits four things and rejects
# the rest, and the ranking is by measured value, not by syntax:
#
#   1. CUSTOM PROPERTY DECLARATIONS (`--brand-500: #...`), kind `cssvar`. The
#      design tokens. They are DECLARED rather than inferred, referenced by name
#      across files, and they are what `frontend-fidelity` is required to resolve
#      a Figma `get_variable_defs` payload against — with no index entry it can
#      only grep for them. `@property --x { … }` registers one too and lands in
#      the same kind. THE HIGHEST-VALUE ROWS, and the ones ctags cannot see.
#   2. `@keyframes <name>`, kind `keyframes` — named, sparse, and referenced by
#      name from an `animation:` shorthand, so a name-matched edge is real.
#   3. `@layer <name> { … }`, kind `layer` — the stylesheet's own architecture,
#      a handful per project.
#   4. SIMPLE top-level selectors, kind `selector`, and "simple" is doing real
#      work: one comma-separated part, WHITESPACE-FREE. That is not a
#      convenience, it is forced — the SYMBOLS.md grammar reads the name field as
#      `\S+` (see ACTIVE_RE), so a row named `.fe code` would not parse on
#      reload, its identity would be unrecoverable, and every build would re-ID
#      it. Splitting on commas keeps `.cat.constraint, .cat.decision` as two real
#      rows and drops descendant/combinator selectors, which is also the right
#      call on value: `.card` is a component another file styles or a JSX file
#      names, `.cell-nd .cell-g` is a local adjustment nobody navigates to.
#
# DELIBERATELY NOT SYMBOLS. `@media` / `@supports` / `@container` / `@scope`
# preludes: a CONDITION is not a name, nothing can reference it, and it would be
# a row whose only content is a duplicate of the source line. Bare declarations
# other than custom properties (`color: red`) — a value, not an identity. Rules
# nested inside another rule (CSS nesting) and the `0%`/`from`/`to` steps inside
# `@keyframes`: local structure, and indexing them is how a stylesheet drowns an
# index. `::selection`, `:root`, `*`, `[data-x="y"]` and `.a>.b` all fail the
# simple-name test above and are dropped with it; `:root` in particular loses
# nothing, since the tokens it holds each get their own row.
CSS_VAR_KIND = "cssvar"
CSS_KEYFRAMES_KIND = "keyframes"
CSS_LAYER_KIND = "layer"
CSS_SELECTOR_KIND = "selector"
# THE VOLUME BOUND, stated: at most this many symbols per stylesheet. CSS is
# roughly 20x denser in addressable names than the code around it (measured: 156
# ctags tags in 223 lines of `views.css` vs ~1 symbol per 27 lines in this file),
# and a design-system or reset sheet reaches four figures on its own — which is
# the failure T-00000104 is about, an index nobody can read in one pass. When the
# cap bites, the KINDS ARE RANKED (`CSS_PRIORITY`): every token, `@keyframes` and
# `@layer` survives, and selectors — the numerous, least-referenced kind — are
# what gets cut. Truncation is a deterministic function of the file, and it is
# LOGGED per file (a silent truncation reads as full coverage).
MAX_CSS_SYMBOLS = 150
# A comma list longer than this is a reset or a normalize sheet, not a component.
MAX_CSS_SELECTORS_PER_RULE = 12
# Minification detected by SHAPE, not by name. Measured on this repo: the six
# hand-written stylesheets have a mean line of 25-35 characters and a longest
# line of 156; the built bundle `.agents/ui/assets/app.css` is ONE line of 36 334
# characters and yields 390 ctags tags. 200 is ~6x above the measured
# hand-written mean and ~180x below the bundle's, so the bound has margin on both
# sides — and a file over it yields NO symbols instead of garbage ones.
CSS_MAX_MEAN_LINE_CHARS = 200
CSS_MIN_BYTES_FOR_SHAPE_TEST = 4000  # too small to be a bundle; skip the test
CSS_PRIORITY = {CSS_VAR_KIND: 0, CSS_KEYFRAMES_KIND: 1, CSS_LAYER_KIND: 1,
                CSS_SELECTOR_KIND: 2}
# Wrappers whose CHILDREN are still top-level rules for our purpose. `@layer` is
# both a wrapper and a name, hence its presence here and a row of its own.
CSS_TRANSPARENT_AT = frozenset({"media", "supports", "container", "scope", "layer"})
CSS_VAR_RE = re.compile(r"^(--[A-Za-z0-9_-]+)\s*:")
CSS_AT_RE = re.compile(r"^@([A-Za-z-]+)\s*([^{;]*)$")
# One selector part, whitespace-free and combinator-free. `.btn`, `#app`,
# `table.board`, `a:hover`, `.cat.constraint` pass; `.a>.b`, `*`, `::before`,
# `[data-x="y"]` do not.
CSS_SELECTOR_NAME_RE = re.compile(r"^[.#]?[A-Za-z_][A-Za-z0-9_.:#-]*$")


def _css_is_machine_written(text: str) -> bool:
    """True when a stylesheet is a minified/built bundle rather than source."""
    lines = text.splitlines()
    if not lines or len(text) < CSS_MIN_BYTES_FOR_SHAPE_TEST:
        return False
    return (len(text) / len(lines)) > CSS_MAX_MEAN_LINE_CHARS


# LA MÊME GARDE POUR LE JS, ET ELLE MANQUAIT (T-00000609). Le JS avait déjà une
# règle par NOM — `SKIP_FILE_RE` saute `.min.js` et `.bundle.js` — mais AUCUNE
# par forme, alors que le CSS a les deux. L'asymétrie exacte était donc
# CSS = nom + forme, JS = nom seul, et le bundle de ce dépôt ne porte aucun de
# ces noms.
#
# CE QUE ÇA COÛTAIT, MESURÉ : `.agents/ui/assets/app.js` fait 717 397 octets sur
# 33 lignes au sens de `wc -l` — 37 au sens de `str.splitlines()`, qui est la
# formule de cette garde — et il produisait **2 051 des 7 807 lignes ACTIVES de
# l'index publié, soit 26 %**, arêtes comprises. (7 928 est le filigrane
# `max_sym_id` et NON un compte de lignes : il ne bouge pas quand des lignes
# deviennent des pierres tombales. Ma première rédaction citait ce nombre-là
# comme dénominateur — relevé du binôme, et c'est la même faute que mêler
# `wc -l` et `splitlines()` : deux conventions, une seule annoncée.) Un agent
# qui cherche un
# symbole par nom pouvait tomber sur une ligne d'index pointant vers 135 207
# caractères sur une seule ligne. Et `migrate_index_to_db --resync` REFUSAIT
# d'écrire à cause de lui, donc la base advisory est restée figée plusieurs jours.
#
# LE SEUIL N'EST PAS CHOISI, IL EST MESURÉ, et c'est ce qui distingue ce
# correctif d'un réglage : sur les 54 fichiers `.js/.jsx/.ts/.tsx/.mjs/.cjs`
# SUIVIS du dépôt, la moyenne de ligne la plus forte HORS bundle est **65**
# (`.agents/ui-src/e2e/fixtures.mjs`). 200 garde donc ~3× de marge au-dessus du
# code écrit à la main, exactement comme la borne CSS voisine — et un fichier
# au-dessus rend ZÉRO symbole plutôt que des symboles faux.
JS_MAX_MEAN_LINE_CHARS = 200
JS_MIN_BYTES_FOR_SHAPE_TEST = 4000  # trop petit pour être un bundle


def _js_is_machine_written(text: str, syms=None) -> bool:
    """True when a `.js`/`.ts` file is a minified/built bundle rather than source.

    LA MOYENNE SEULE NE SUFFIT PAS, et ma première rédaction annonçait une marge
    qu'elle n'avait pas. J'avais écrit « ~3× de marge » : c'était la marge contre
    les fichiers du dépôt TELS QU'ILS SONT, pas contre la CLASSE des fichiers
    légitimes. Mesuré par le binôme, puis refait : `fixtures.mjs` (9 212
    caractères, 140 lignes, moyenne 65,8) bascule au-dessus de 200 dès qu'on y
    ajoute **une seule ligne de 19 000 caractères** — un SVG inline, une police
    en base64, un tableau de données. Tous ses symboles disparaîtraient alors,
    avec pour seule trace un stdout que les hooks jettent. Une sourcemap inline
    produit exactement la même forme, mesuré sur un module de 2 465 octets.

    ON MESURE DONC LÀ OÙ SONT LES SYMBOLES, pas où sont les octets : un bundle a
    ses symboles SUR les lignes longues, un module à gros littéral les a
    ailleurs. Relevé sur ce dépôt — `app.js` : **80 %** de ses tags sont sur des
    lignes de plus de 200 caractères ; `fixtures.mjs` : **22 %**. La moitié
    sépare les deux sans ambiguïté.

    Sans `syms` — l'extracteur de repli, quand ctags n'a rien rendu — on retombe
    sur la moyenne seule : c'est la borne, et elle est dite plutôt que tue."""
    lines = text.splitlines()
    if not lines or len(text) < JS_MIN_BYTES_FOR_SHAPE_TEST:
        return False
    if (len(text) / len(lines)) <= JS_MAX_MEAN_LINE_CHARS:
        return False
    if not syms:
        return True
    longues = sum(1 for s in syms
                  if 0 < s.get("start", 0) <= len(lines)
                  and len(lines[s["start"] - 1]) > JS_MAX_MEAN_LINE_CHARS)
    return longues * 2 > len(syms)


def is_machine_written(relpath, text) -> bool:
    """Vrai quand une garde de FORME fait rendre ZÉRO symbole EXPRÈS.

    CÔTÉ LECTURE UNIQUEMENT, et c'est un correctif du binôme. `extract_file`
    répond `[]` pour TROIS prétentions qui ne se ressemblent pas : aucun
    extracteur pour ce suffixe, fichier illisible, et — depuis T-00000609 —
    ÉCARTÉ DÉLIBÉRÉMENT. `symbols.py` confondait la troisième avec « j'ai
    regardé, il n'y a rien », donc un fichier PRÉSENT dans l'arbre sortait
    `[GONE dans l'arbre]`. Reproduit par le binôme : 800 lignes sur 800 marquées
    disparues, la liste des non-couverts VIDE — l'overlay affirmait avoir
    regardé. Le défaut préexistait pour le CSS ; ce changement l'élargissait au
    JS, soit 2 051 lignes ici."""
    suffix = Path(relpath or "").suffix
    if suffix in JS_EXT:
        return _js_is_machine_written(text)
    if suffix in CSS_EXT:
        return _css_is_machine_written(text)
    return False


def _css_strip_comments(text: str) -> str:
    """Blank out `/* … */`, PRESERVING newline count so line numbers stay true."""
    out, i = [], 0
    while True:
        j = text.find("/*", i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        k = text.find("*/", j + 2)
        chunk = text[j:] if k < 0 else text[j:k + 2]
        out.append("\n" * chunk.count("\n"))
        if k < 0:
            return "".join(out)
        i = k + 2


def _css_selector_names(head: str) -> list:
    """The whitespace-free parts of a selector list, deduplicated, in order."""
    names, seen = [], set()
    for part in head.split(","):
        part = part.strip()
        if not part or part in seen or not CSS_SELECTOR_NAME_RE.match(part):
            continue
        seen.add(part)
        names.append(part)
        if len(names) >= MAX_CSS_SELECTORS_PER_RULE:
            break
    return names


def _css_block_head(head: str, nested: bool) -> tuple:
    """`(kind, [names], opaque)` for the prelude of a `{` block.

    `opaque` is True when whatever this block CONTAINS must not be indexed — a
    plain rule (so CSS nesting below it is local structure), `@keyframes` (whose
    children are `0%` steps), `@font-face` and friends. It is False only for the
    transparent wrappers, whose children are still top-level rules.
    """
    if head.startswith("@"):
        m = CSS_AT_RE.match(head)
        at = m.group(1).lower() if m else ""
        arg = m.group(2).strip() if m else ""
        simple = arg and not re.search(r"\s", arg)
        if at in CSS_TRANSPARENT_AT:
            if at == "layer" and simple:
                return CSS_LAYER_KIND, [arg], False
            return None, [], False  # a condition is not a name
        if at == "keyframes" and simple:
            return CSS_KEYFRAMES_KIND, [arg], True
        if at == "property" and simple and arg.startswith("--"):
            return CSS_VAR_KIND, [arg], True
        return None, [], True
    if nested:
        return None, [], True
    return CSS_SELECTOR_KIND, _css_selector_names(head), True


def extract_css(text: str, relpath: str = "") -> list:
    """Symbols of a CSS stylesheet — see the block comment above for the slice.

    A single character scan tracks brace depth over the comment-stripped text, so
    line numbers stay exact and no symbol's identity depends on indentation. Ends
    come from the matching `}`, which is what keeps the "read only this range"
    contract of the index true for a rule.

    `--kinds` does NOT reach here, the same way it does not reach `extract_py`:
    that flag filters CTAGS kind names, and these kinds are ours.
    """
    if _css_is_machine_written(text):
        log = f"build_index: {relpath}: " if relpath else "build_index: "
        # SUR STDERR, ET C'EST UN CORRECTIF (T-00000609). Cette note partait sur
        # STDOUT, or `extract_file` est aussi appelée par l'overlay de
        # `symbols.py`, dont `--json` écrit sa charge sur ce même flux : une
        # seule exclusion suffisait donc à rendre la sortie NON PARSABLE.
        # Reproduit de bout en bout — `symbols.py query --file <bundle> --json`
        # rendait `build_index: …: minified/built bundle …` PUIS le JSON, et
        # `json.loads` levait. Le défaut existait déjà pour le CSS ; la garde JS
        # l'aurait rendu courant. Les lignes de VERDICT du constructeur
        # (`INDEX BUILT @ …`) restent sur stdout : ce sont elles que les
        # appelants lisent.
        # ASCII only: a cp1252 console renders an em dash as '?'. Measured here.
        print(f"{log}minified/built stylesheet (mean line > "
              f"{CSS_MAX_MEAN_LINE_CHARS} chars) - no symbols extracted",
              file=sys.stderr)
        return []
    src = _css_strip_comments(text)
    syms, stack = [], []
    buf, buf_line, line_no = [], 1, 1

    def declaration(head, end_line):
        """A `--name: value` declaration inside a block is a token; else nothing.

        Only the IMMEDIATE parent may be a rule: an ancestor above it that is
        `opaque` means this declaration sits in a nested rule or in a `@keyframes`
        step, which is local structure rather than the project's token set.
        """
        m = CSS_VAR_RE.match(head)
        if m and stack and not any(f["opaque"] for f in stack[:-1]):
            syms.append({"name": m.group(1), "kind": CSS_VAR_KIND,
                         "start": buf_line, "end": max(end_line, buf_line)})

    # LEADING WHITESPACE IS DROPPED WHILE `buf` IS EMPTY, and that is not tidiness:
    # buffering it makes `buf` non-empty, so `buf_line` never advances and every
    # symbol after the first inherits a stale start line — which would move SYM-IDs
    # around on unrelated edits.
    for ch in src:
        if ch == "\n":
            line_no += 1
            if buf:
                buf.append(" ")  # separator only; a prelude may span lines
            continue
        if ch not in "{};":
            if not buf:
                if ch.isspace():
                    continue
                buf_line = line_no
            buf.append(ch)
            continue
        head, buf = "".join(buf).strip(), []
        if ch == ";":
            declaration(head, line_no)
            continue
        if ch == "}":
            if head:
                declaration(head, line_no)  # last declaration, no trailing ';'
            frame = stack.pop() if stack else None
            for sym in (frame or {}).get("own", ()):
                sym["end"] = max(line_no, sym["start"])
            continue
        kind, names, opaque = _css_block_head(head, any(f["opaque"] for f in stack))
        own = [{"name": name, "kind": kind, "start": buf_line, "end": buf_line}
               for name in names]
        syms.extend(own)
        stack.append({"opaque": opaque, "own": own, "kind": kind})

    if len(syms) > MAX_CSS_SYMBOLS:
        ranked = sorted(syms, key=lambda s: (CSS_PRIORITY.get(s["kind"], 9),
                                             s["start"], s["name"]))
        dropped, syms = len(syms) - MAX_CSS_SYMBOLS, ranked[:MAX_CSS_SYMBOLS]
        log = f"build_index: {relpath}: " if relpath else "build_index: "
        print(f"{log}stylesheet capped at {MAX_CSS_SYMBOLS} symbols, {dropped} "
              f"dropped (tokens and named at-rules are kept first)")
    return sorted(syms, key=lambda s: (s["start"], s["kind"], s["name"]))


def extract_file(abspath, relpath, ctags_syms, text=None):
    """`text` is the file already read by the caller, or None to read it here.

    OPTIONAL ON PURPOSE (T-00000377). `reconcile` needs the source lines anyway,
    to hash each symbol's body, so it reads the file ONCE and hands the text
    down: the stdlib branch stops re-reading it, and the ctags branch — which
    reads nothing today — gets the text it would otherwise have had to open a
    second time. Every other caller keeps the old two-argument behaviour.
    """
    # LA GARDE DE FORME PASSE AVANT `ctags_syms`, ET C'EST LOAD-BEARING
    # (T-00000609). Le CSS est dans `CTAGS_SKIP_EXT`, donc sa garde peut vivre
    # dans son extracteur ; le JS, lui, est COUVERT par ctags, donc `ctags_syms`
    # est non vide et la ligne ci-dessous rendrait avant qu'on ait rien pu dire.
    # Placée après, la garde serait INERTE — et elle aurait l'air d'exister.
    suffix = Path(relpath or "").suffix
    if suffix in JS_EXT:
        if text is None:
            try:
                text = Path(abspath).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ctags_syms or []
        if _js_is_machine_written(text, ctags_syms):
            log = f"build_index: {relpath}: " if relpath else "build_index: "
            # STDERR, même raison que la note CSS jumelle : `symbols.py --json`
            # écrit sa charge sur stdout et appelle cette fonction.
            print(f"{log}minified/built bundle (mean line > "
                  f"{JS_MAX_MEAN_LINE_CHARS} chars) - no symbols extracted",
                  file=sys.stderr)
            return []
    # ctags covered the file: trust it, EXCEPT when it found nothing in a file the
    # stdlib fallback understands (parse error on its side — don't lose symbols).
    if ctags_syms:
        return ctags_syms
    if text is None:
        try:
            text = Path(abspath).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    if suffix in PY_EXT:
        return extract_py(text)
    if suffix in JS_EXT:
        return extract_js(text)
    if suffix in CSS_EXT:
        # Not a "fallback" for CSS: this is the ONLY extractor for it, because
        # ctags is both blind to tokens and far too coarse on selectors (see
        # CTAGS_SKIP_EXT). `.css` is in CTAGS_SKIP_EXT, so `ctags_syms` above is
        # always empty here and this branch always runs.
        return extract_css(text, relpath)
    return []  # unsupported by the fallback → no symbols (ctags would cover it)


def extract_scope(root, rels, ctags_bin, kinds):
    """`{rel: [symbol…]}` for `rels` — the extraction half of `reconcile`, PURE.

    THE SAME EIGHT LINES, LIFTED, NOT SHARED (T-00000378). `reconcile` keeps its
    own copy on purpose: it is the Stop-hook WRITE path, and rerouting it through
    a function whose other caller is a READ path (`symbols.py`'s freshness
    overlay) would put a query's bug on the builder's critical path. So this is a
    deliberate duplication, and what keeps the two honest is a PARITY NET — a
    test that runs both over the same file set and asserts the same rows
    (L-00000221: unification PAR FILET, not by a refactor nobody asked for).

    IT WRITES NOTHING IN THE REPOSITORY, and the formulation is exact (↯ C7): one
    ctags pass stages a listfile in the SYSTEM temp dir (`extract_ctags_batch`)
    and removes it, then runs one process per batch. On a tree whose sources are
    all `.py`/`.css` — `CTAGS_SKIP_EXT` — that branch never runs at all.

    A FILE WITH NO EXTRACTOR STILL GETS AN ENTRY, and the caller must not read it
    as GONE. `extract_file` answers `[]` for a suffix neither ctags nor the stdlib
    branch covers, exactly as it does inside `reconcile`; the difference is that
    `reconcile` holds the whole picture and may tombstone, while a read-side
    caller holds one changed-file window and must stay conservative. That
    judgement belongs to the caller, so this function stays a faithful lift and
    invents no third answer.

    `rels` is not filtered here either: callers pass what `changed_source_files`
    or `all_source_files` already put through `_keep`.
    """
    rels = list(rels)
    out = {}
    # CONFINE EVERY `rel` TO `root` BEFORE ANY DEREFERENCE -- ctags included
    # (T-00000378). A `rel` may be a store `path` column, a COMMITTED BINARY
    # forgeable by whoever lands a row; an absolute path or one climbing out with
    # `../` would have ctags (below) or `read_text` print an ARBITRARY file into
    # an agent's context. An escape is NOT read: it gets an EMPTY entry, so the
    # caller counts it NOT COVERED -- never GONE, never raised -- exactly like a
    # suffix no extractor understands. `resolve()` closes the symlink route too.
    # Mirrors the idiom in symbols.py:tree_lines, the store's other deref site.
    root_resolved = Path(root).resolve()
    safe = []
    for rel in rels:
        target = (Path(root) / rel).resolve()
        if Path(rel).is_absolute() or not target.is_relative_to(root_resolved):
            out[rel] = []
        else:
            safe.append(rel)
    ctags_scope = [f for f in safe if Path(f).suffix not in CTAGS_SKIP_EXT]
    ctags_map = extract_ctags_batch(root, ctags_scope, ctags_bin, kinds) if ctags_bin else {}
    for rel in safe:
        abspath = Path(root) / rel
        if not abspath.exists():
            continue  # deleted in the tree → the caller decides what that means
        try:
            text = abspath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        out[rel] = extract_file(abspath, rel, ctags_map.get(rel), text=text)
    return out


# --------------------------------------------------------------------- edges
MAX_NAME_CARRIERS = 8   # a name owned by more symbols than this is noise, not an edge
MAX_EDGES = 6
# The second alternative exists so `var(--brand-500)` in a rule body resolves to
# the `cssvar` row that DECLARES that token (T-00000102) — without it a stylesheet
# would be in the index but connected to nothing, since `--brand-500` is not a
# token under the first alternative and `brand` alone matches no symbol. It is
# additive by construction: no language in SRC_EXT allows an identifier to start
# with `--`, so this alternative can only ever match a CSS custom property name.
# It does fire on a `--i` pre-decrement in C/JS, which can only produce a false
# edge if a custom property of that exact name also exists — and `uses[]` is
# documented APPROXIMATE for precisely this class of miss.
TOKEN_RE = re.compile(r"[A-Za-z_$][\w$]*|--[A-Za-z_][A-Za-z0-9_-]*")


def resolve_edges(symbols, root):
    """Fill `uses` on symbols flagged `_fresh` (re-extracted this run).

    Two things keep this linear on a large repo. First, names carried by more
    than MAX_NAME_CARRIERS symbols are dropped: `get`/`run`/`handle` match
    hundreds of ids, which is both quadratic and an edge that says nothing.
    Second, `uses` is a set — membership used to be a scan over a list growing
    to that same length, which is what made a 43k-symbol build never finish.
    """
    name_to_ids = {}
    loc = {}  # id -> (path, module), for ranking candidates by locality
    for s in symbols:
        if not s.get("deleted"):
            name_to_ids.setdefault(s["name"], []).append(s["id"])
            loc[s["id"]] = (s["path"], module_of(s["path"]))
    for name in [n for n, ids in name_to_ids.items() if len(ids) > MAX_NAME_CARRIERS]:
        del name_to_ids[name]

    # Grouped by path so only ONE file's text is resident at a time — the old
    # cache held every scanned file for the whole run.
    fresh = sorted((s for s in symbols if s.get("_fresh") and not s.get("deleted")),
                   key=lambda s: s["path"])
    cur_path, lines = None, []
    for s in fresh:
        if s["path"] != cur_path:
            cur_path = s["path"]
            try:
                lines = (root / cur_path).read_text(
                    encoding="utf-8", errors="replace").splitlines()
            except OSError:
                lines = []
        body = "\n".join(lines[s["start"] - 1:s["end"]])
        uses = set()
        for tok in set(TOKEN_RE.findall(body)):
            if tok == s["name"]:
                continue
            uses.update(name_to_ids.get(tok, ()))
        uses.discard(s["id"])
        # Truncating by id kept the OLDEST matches, which is meaningless. When a
        # name resolves to several symbols the local one is nearly always the
        # intended target, so rank same-file, then same-module, then the rest.
        my_path, my_mod = s["path"], module_of(s["path"])

        def rank(i):
            p, m = loc.get(i, ("", ""))
            return (0 if p == my_path else 1 if m == my_mod else 2, i)

        s["uses"] = sorted(sorted(uses, key=rank)[:MAX_EDGES])


# ------------------------------------------------------------------ reconcile
# Characters of pathspec per `git ls-files` call in `_suivis_parmi`. Windows caps a
# whole command line at 32 767 characters (CreateProcess); a sparse checkout can
# hold hundreds of indexed files outside its cone. Past the cap `git()` swallows
# the OSError and answers None — the rule would then go inert in silence.
_PATHSPEC_BUDGET = 8000


def _absent_du_disque(path):
    """True seulement quand le système PROUVE l'absence : ENOENT ou ENOTDIR.

    « Pas prouvé présent » n'est pas « prouvé absent » (binôme de T-00000681).
    `Path.exists()` rend False sur TOUTE OSError depuis Python 3.12 : sous un
    répertoire illisible (EACCES), des fichiers suivis et PRÉSENTS passaient
    pour effacés et leurs lignes étaient tombstonées — mesuré, `chmod 000` sur
    un répertoire du dépôt, 16 lignes. Toute autre OSError (EACCES, ELOOP,
    ENAMETOOLONG…) répond donc False : sur un doute, la ligne est recopiée.
    """
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return False


def _suivis_parmi(root, chemins):
    """Ceux de `chemins` que l'index git SUIT, ou None si git n'a pas répondu.

    `--literal-pathspecs` : un chemin est un nom, jamais un motif — un fichier
    nommé `*.py` ne doit pas attraper ses voisins. `-z` : aucune citation, donc
    la sortie se compare octet pour octet aux chemins des lignes. Une entrée
    `--skip-worktree` (sparse-checkout) est listée : elle est dans l'index même
    absente du disque, et c'est précisément ce qu'on veut savoir. Par lots de
    `_PATHSPEC_BUDGET` caractères.
    """
    suivis, lot, taille = set(), [], 0
    lots = []
    for chemin in sorted(chemins):
        if lot and taille + len(chemin) + 1 > _PATHSPEC_BUDGET:
            lots.append(lot)
            lot, taille = [], 0
        lot.append(chemin)
        taille += len(chemin) + 1
    if lot:
        lots.append(lot)
    for noms in lots:
        out = git(root, "--literal-pathspecs", "ls-files", "-z", "--", *noms)
        if out is None:
            return None
        suivis.update(p for p in out.split("\0") if p)
    return suivis


def reconcile(root, scope, ctags_bin, kinds, purge=False, bodies=None):
    """`purge` (full builds only): also tombstone symbols whose file left the
    source set — deleted outside an incremental window, or newly excluded by the
    effective directory scope (`SKIP_DIRS` at any depth, `host_skip_dirs()` at the
    root). Incremental builds do NOT purge: there, out-of-scope only means
    "unchanged" for a file that still EXISTS on disk. A copied-forward row whose
    file is PROVEN GONE from the disk AND that git does not track is tombstoned
    by an incremental build too (T-00000681): a file git never tracked is named by
    no scope channel once deleted, so without this its rows would outlive it.
    Two bounds. "Gone" means ENOENT/ENOTDIR (`_absent_du_disque`) — an unreadable
    directory is not an absence. And a TRACKED file absent from the disk
    (skip-worktree, sparse-checkout) is kept: the index is committed, so
    tombstoning it on one clone would erase its rows for everyone and change its
    ids when the file comes back. What this does NOT change: `--if-stale` reads
    the same channels, so it still answers CURRENT while such a row lingers —
    the row dies at the next REAL build, never at the probe.

    `bodies` is the PREVIOUS `{id: sha}` map (`read_bodies`), and this is THE ONE
    PLACE a body hash is computed (T-00000377). A symbol in scope is re-extracted,
    so its hash is recomputed from the text just read; a symbol OUT of scope is
    copied forward from the published rows, so its hash is carried over from that
    map — an incremental build must not silently drop the hashes of every file it
    did not touch. A RESURRECTED symbol goes through the fresh path and is
    re-hashed, never inheriting; a tombstone gets no hash at all.

    The hash lives on the symbol dict as `body_sha`, and nothing that FORMATS a
    published artefact reads it: `sym_line` and `write_delta` name their fields
    one by one. So no signature changes and no published format moves.
    """
    bodies = bodies or {}
    perdants = []  # rows that lost their id to a collision (M5): file rescanned
    by_key, by_id, max_id = load_existing(root, perdants)
    scope = list(scope) + sorted({p["path"] for p in perdants} - set(scope))
    scope_set = set(scope)
    ctags_scope = [f for f in scope if Path(f).suffix not in CTAGS_SKIP_EXT]
    ctags_map = extract_ctags_batch(root, ctags_scope, ctags_bin, kinds) if ctags_bin else {}
    result = {}  # id -> symbol
    added, changed = [], []

    # T-00000681 (bornes : docstring) : un `stat` par chemin DISTINCT hors scope ;
    # un fichier PRESENT ou SUIVI reste recopie, `purge` tombstone deja tout le
    # hors-scope, git muet (None) ne prouve aucun non-suivi : rien n'est efface.
    absents = set()
    if not purge:
        candidats = {p for p in {s["path"] for s in by_id.values() if not s.get("deleted")}
                     if p not in scope_set and _absent_du_disque(root / p)}
        suivis = _suivis_parmi(root, candidats) if candidats else set()
        absents = candidats - suivis if suivis is not None else set()

    # Preserve everything outside the scope (including prior tombstones).
    gone = []
    for sym in by_id.values():
        if sym.get("deleted"):
            result[sym["id"]] = sym
        elif sym["path"] not in scope_set:
            if purge or sym["path"] in absents:
                result[sym["id"]] = {"id": sym["id"], "name": sym["name"],
                                     "kind": sym["kind"], "deleted": True}
                gone.append(sym["id"])
            else:
                # Copied forward, body unread: the hash comes from the PREVIOUS
                # map or stays unknown — on a copy, since `by_id` holds the rows
                # `_parse_rows` produced, not ours to annotate in place.
                carried = bodies.get(sym["id"])
                result[sym["id"]] = ({**sym, "body_sha": carried} if carried
                                     else sym)

    next_id = max_id
    seen_keys = set()
    for rel in scope:
        abspath = root / rel
        if not abspath.exists():
            continue  # deleted file → its symbols fall through to tombstoning
        # ONE read per in-scope file, for both jobs: the stdlib extractors and
        # the body hashes below. `None` (an unreadable file) means no line to
        # slice, so every hash of this file degrades to None — never to the hash
        # of an empty body.
        try:
            text = abspath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        lines = text.splitlines() if text is not None else []
        extracted = extract_file(abspath, rel, ctags_map.get(rel), text=text)
        # Ordinals PER FILE, with `load_existing`'s convention, so homonyms
        # re-pair one to one; the (deterministic) extraction position breaks ties.
        keys = identity_keys([(rel, ex["name"], ex["kind"], ex["start"], pos)
                              for pos, ex in enumerate(extracted)])
        for key, ex in zip(keys, extracted):
            seen_keys.add(key)
            prev = by_key.get(key)
            if prev:
                sym = dict(prev)
                if (sym["start"], sym["end"]) != (ex["start"], ex["end"]):
                    changed.append(prev["id"])
                sym.update(start=ex["start"], end=ex["end"], deleted=False, _fresh=True)
            else:
                next_id += 1
                sym = {"id": next_id, "path": rel, "name": ex["name"],
                       "kind": ex["kind"], "start": ex["start"], "end": ex["end"],
                       "uses": [], "purpose": "", "deleted": False, "_fresh": True}
                added.append(next_id)
            # In scope means re-extracted means RE-HASHED, always — including a
            # symbol resurrected from a tombstone, which must never inherit a
            # hash taken before it died.
            sym["body_sha"] = body_hash(lines, ex["start"], ex["end"])
            result[sym["id"]] = sym

    # Tombstone symbols that lived in a scope file but were not re-extracted.
    #
    # THIS LOOP IS WHERE THE INVARIANT IS ENFORCED: no live symbol ever leaves the
    # index without a tombstone. It can only see what `by_key` holds, so before the
    # key carried an ordinal, the homonyms a triple had collapsed were unreachable
    # from here — neither carried forward nor tombstoned (T-00000122). Every live
    # identity now has its own entry, so "gone" is always spelled `DELETED`.
    removed = []
    for key, prev in by_key.items():
        if prev["path"] in scope_set and key not in seen_keys:
            result[prev["id"]] = {"id": prev["id"], "name": prev["name"],
                                  "kind": prev["kind"], "deleted": True}
            removed.append(prev["id"])

    symbols = sorted(result.values(), key=lambda s: s["id"])
    resolve_edges(symbols, root)

    # Symbols outside the scope are never re-resolved, so an incremental build
    # leaves their uses[] pointing at ids tombstoned this run. Drop those: an
    # edge to a DELETED symbol is worse than no edge, it reads as real.
    live = {s["id"] for s in symbols if not s.get("deleted")}
    for s in symbols:
        if not s.get("deleted") and s["uses"]:
            kept = [i for i in s["uses"] if i in live]
            if len(kept) != len(s["uses"]):
                s["uses"] = kept
    return symbols, {"added": added, "removed": removed + gone, "changed": changed}


# ---------------------------------------------------------------- write-out
# Source-layout scaffolding that names no module: the JVM convention
# `src/main/java/<group>/<module>` put EVERY file of a single-module Gradle or
# Maven repo in a module called `main`, which is how a hexagonal backend ended
# up looking like one flat blob. These segments are skipped to reach the first
# directory a developer actually chose.
SRC_ROOTS = {"src", "lib", "app", "packages", "apps"}
LAYOUT_SEGMENTS = {"main", "test", "it", "integrationTest", "java", "kotlin",
                   "scala", "groovy", "resources", "jvmMain", "commonMain"}
# Reverse-domain package roots. `com/acme/domain` -> the module is `domain`,
# not `com`: the two leading segments are the group id, shared by every file.
PACKAGE_ROOTS = {"com", "org", "io", "net", "co", "de", "fr", "eu", "uk", "us",
                 "ch", "be", "nl", "es", "it", "cn", "jp", "dev", "ai", "cloud"}


def module_of(path):
    dirs = path.split("/")[:-1]
    if not dirs:
        return "(root)"
    i = 0
    if dirs[0] in SRC_ROOTS:
        i = 1
        while i < len(dirs) and dirs[i] in LAYOUT_SEGMENTS:
            i += 1
        if i < len(dirs) and dirs[i] in PACKAGE_ROOTS:
            i += 2  # skip <tld>/<org>
    if i >= len(dirs):
        i = len(dirs) - 1
    return dirs[i]


def sym_line(s):
    if s.get("deleted"):
        return f"{sid(s['id'])}  DELETED  {s['name']}  {s['kind']}"
    uses = "uses[" + ",".join(sid(i) for i in s["uses"]) + "]"
    tail = f"  :: {s['purpose']}" if s.get("purpose") else "  ::"
    return f"{sid(s['id'])}  {s['path']}:{s['start']}-{s['end']}  {s['name']}  {s['kind']}  {uses}{tail}"


# All ids in one build are rendered at the same width. At 3 digits, `grep SYM-102`
# also matches SYM-1020..SYM-1029 — and the header tells readers to grep exactly
# like that to find callers. Any repo of this size passes 999 immediately, so the
# width tracks the largest id instead of being fixed.
_ID_WIDTH = 3


def set_id_width(max_id):
    global _ID_WIDTH
    _ID_WIDTH = max(3, len(str(max(max_id, 1))))
    return _ID_WIDTH


def sid(n):
    return f"SYM-{n:0{_ID_WIDTH}d}"


def kinds_fingerprint(kinds):
    """Stable short digest of the kept ctags kinds, for the header stamp."""
    return hashlib.sha256(",".join(sorted(kinds)).encode("utf-8")).hexdigest()[:8]


def body_hash(lines, start, end):
    """`sha256[:16]` of the symbol's body, or None when the range is not real.

    PURE, and its normalisation is `BODY_ALGO`: every line is `rstrip`ped and the
    body is re-joined with `\\n`. That buys immunity from the two differences that
    are NOT the code changing — CRLF vs LF (the `--linux` replay of verify.sh
    would otherwise turn every hash red on the same source) and trailing
    whitespace. It is deliberately NOT immune to leading indentation: moving a
    function into a class DOES change its body.

    OUT OF RANGE RETURNS None, NEVER THE HASH OF THE EMPTY STRING. An empty body
    hashes to a perfectly stable value that would then read as "this symbol is
    FRESH" on every truncated file — a stable, wrong answer, which is worse than
    no answer. `None` travels as UNKNOWN instead.
    """
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if start < 1 or end < start or end > len(lines):
        return None
    body = "\n".join(line.rstrip() for line in lines[start - 1:end])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def build_stamp(threshold, kinds_fp, dirscope_fp=None):
    """The extra header fields `--if-stale` fingerprints the index with.

    APPENDED after the existing ones on purpose: `built @ (\\S+)` — parsed here
    and by .claude/hooks/stop-reindex.sh — must keep matching, so nothing that
    already exists on that line may move. `dirscope` is likewise appended AFTER
    `kinds`, for the same reason.
    """
    tail = f" · dirscope {dirscope_fp}" if dirscope_fp else ""
    return f" · threshold {threshold} · kinds {kinds_fp}{tail}"


def published_dirscope(line):
    """The `dirscope` digest of a published header — ABSENT means the EMPTY set.

    An index published before this field existed carries no `dirscope`, and it
    was built with no root-only host exclusion at all. Reading a missing field as
    `scope_fingerprint(set())` is therefore the CORRECT reading, not a lenient
    one: it makes every repo without a vendoring marker — the kit's own included
    — agree with its published index and skip the forced full rebuild. Only a
    repo whose effective scope really did change pays for one.
    """
    return _header_field(line, "dirscope") or scope_fingerprint(set())


def header(count, sha, backend, stamp=""):
    try:
        today = date.today().isoformat()
    except Exception:
        today = "unknown"
    return [
        f"# Symbols — {count} entries — built @ {sha or NO_GIT_STAMP} · updated {today}"
        f" · backend {backend}{stamp}",
        "# grammar:  SYM-NNN  <path>:<start>-<end>  <name>  <kind>  uses[SYM-…]  :: <purpose ≤10 words>",
        f"# ids are fixed-width ({_ID_WIDTH} digits) — find callers of {sid(20)} with:"
        f"  grep '{sid(20)}' SYMBOLS*.md   (reverse edges are NOT stored)",
        "# uses[] edges are APPROXIMATE (name-matched by build_index.py) — verify before relying on them",
        "",
    ]


def _require_watermark(root, symbols):
    """Precondition: the reserved bound already covers every id we are about to
    publish (L-022, ordering invariant).

    Not an `assert`: this must hold under `python -O` too. Raising here routes
    through the publish-progress flag in `cli()`, so the caller learns whether
    anything had already been replaced.
    """
    computed = max((s["id"] for s in symbols), default=0)
    bound = read_delta_bound(root)
    if bound is None or bound < computed:
        raise RuntimeError(
            f"SYM-ID watermark not reserved before publish (bound {bound} < "
            f"max id {computed}) — reserve_watermark() must run first")


def drop_stale_shards(root, keep):
    """Delete shards this build did not write. Runs LAST, after every artefact of
    the new generation is published: a shard deleted before the ToC that replaces
    it is a shard whose symbols vanish if the build then dies. `keep` is empty on
    the monolithic branch, so a stray shard from a sharded generation always goes
    (L-023 corollary) instead of lingering as an unreferenced duplicate.
    """
    dropped = 0
    for old in sorted(index_dir(root).glob(SHARD_GLOB)):
        if old.name in keep:
            continue
        try:
            old.unlink()
            dropped += 1
        except OSError:
            pass  # locked on win32 — it stays watermark-only until the next run
    return dropped


def write_index(root, symbols, sha, backend, threshold, pub=None, stamp=""):
    """Publish SYMBOLS.md (+ shards). Returns shard_info, including the `keep`
    set of shard names the caller must pass to `drop_stale_shards` afterwards.
    """
    pub = pub or _Publisher()
    idx = index_dir(root)
    idx.mkdir(parents=True, exist_ok=True)
    _require_watermark(root, symbols)
    active = [s for s in symbols if not s.get("deleted")]
    tombs = [s for s in symbols if s.get("deleted")]
    count = len(active)

    if count <= threshold:
        lines = header(count, sha, backend, stamp)
        lines += [sym_line(s) for s in active]
        if tombs:
            lines += [""] + [sym_line(s) for s in tombs]
        pub.write(idx / MAIN_NAME, "\n".join(lines) + "\n")
        return {"sharded": False, "shards": 1, "active": count, "keep": set()}

    groups = {}
    for s in active:
        groups.setdefault(module_of(s["path"]), []).append(s)
    # tombstones follow their module (path unknown for tombstones → a catch-all shard)
    for s in tombs:
        groups.setdefault("_deleted", []).append(s)

    toc = header(count, sha, backend, stamp)
    toc.append(f"# index-of-indexes (>{threshold} entries) — a shard is capped at "
               f"{MAX_SHARD_ENTRIES} rows so any single read stays affordable")
    written, keep = 0, set()
    for mod in sorted(groups):
        rows = groups[mod]
        base = re.sub(r"[^A-Za-z0-9]+", "_", mod).strip("_") or "root"
        # One oversized module used to mean one oversized shard — a `src/core`
        # with 30k symbols is as unreadable as the monolith sharding avoids.
        parts = [rows[i:i + MAX_SHARD_ENTRIES]
                 for i in range(0, len(rows), MAX_SHARD_ENTRIES)] or [[]]
        for n, chunk in enumerate(parts, start=1):
            suffix = f"_{n}" if len(parts) > 1 else ""
            shard = f"SYMBOLS_{base}{suffix}.md"
            act = [r for r in chunk if not r.get("deleted")]
            shard_lines = header(len(act), sha, backend, stamp) + [sym_line(s) for s in chunk]
            keep.add(shard)
            pub.write(idx / shard, "\n".join(shard_lines) + "\n")
            span = ""
            if len(parts) > 1 and act:
                span = f"  [{sid(act[0]['id'])}..{sid(act[-1]['id'])}]"
            toc.append(f"- {mod + suffix:<20} {len(act):>6} symbols   →  {shard}{span}")
            written += 1
    # Shards first, ToC second: a ToC published before the shards it lists points
    # at content that may never arrive.
    pub.write(idx / MAIN_NAME, "\n".join(toc) + "\n")
    return {"sharded": True, "shards": written, "active": count, "keep": keep}


# --------------------------------------------------------- codebase index
MANIFESTS = [
    ("package.json", "Node/JS"), ("tsconfig.json", "TypeScript"),
    ("pyproject.toml", "Python"), ("requirements.txt", "Python"),
    ("pom.xml", "Java/Maven"), ("build.gradle", "Java/Gradle"),
    ("build.gradle.kts", "Kotlin/Gradle"), ("go.mod", "Go"),
    ("Cargo.toml", "Rust"), ("Gemfile", "Ruby"), ("composer.json", "PHP"),
    ("Package.swift", "Swift"), ("Podfile", "iOS/CocoaPods"),
]
ENTRY_NAMES = {
    "main", "index", "server", "app", "cli", "__main__", "manage",
    "Program", "Application", "bootstrap",
}
MAX_MODULE_ROWS = 15
# An EMPTY first cell no longer matches (never written here: the Module cell always carries a path).
ROW_RE =re.compile(r"^\|\s*(?:`\s*)?([^|`\s](?:[^|`]*[^|`\s])?)(?:\s*`)?\s*\|([^|]*)\|([^|]*)\|(.*)\|\s*$")


def _existing_roles(path):
    """Keep indexer-written Role / Owner cells. ROW_RE is LINEAR, cells 2-4 raw (callers strip): lazy cells were ReDoS."""
    roles = {}
    if not path.exists():
        return roles
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW_RE.match(line)
        if m and not set(m.group(2).strip()) <= {"-", " "}:
            roles[m.group(1).strip()] = (m.group(2).strip(), m.group(4).strip())
    return roles


def _entry_points(files):
    hits = []
    for f in files:
        p = Path(f)
        # A stylesheet is never an entry point: `src/index.css` made the heuristic wrong on
        # every front-end project the moment `.css` entered SRC_EXT (T-00000102).
        if p.suffix in CSS_EXT:
            continue
        rel = p.parts[2:] if p.parts[:2] == (".agents", "vendor") else p.parts  # depth counted below the vendor
        if p.stem in ENTRY_NAMES and len(rel) <= 3:
            hits.append(f)
    return sorted(hits, key=lambda f: (len(Path(f).parts), f))[:8]


def write_codebase_index(root, symbols, files, sha, backend, threshold, pub=None):
    """Deterministic skeleton: module table, sizes, cross-module edges, entries.

    Everything here is countable. The indexer agent only fills the Role and Owner
    columns of the modules it does not already know — bounded LLM work, the same
    contract as `needs_purpose`, which is what keeps a 500k-LOC repo affordable.
    """
    pub = pub or _Publisher()
    idx = index_dir(root)
    idx.mkdir(parents=True, exist_ok=True)
    target = idx / "CODEBASE_INDEX.md"
    prior = _existing_roles(target)

    active = [s for s in symbols if not s.get("deleted")]
    by_id = {s["id"]: s for s in active}
    mods, files_per_mod = {}, {}
    for f in files:
        files_per_mod[module_of(f)] = files_per_mod.get(module_of(f), 0) + 1
    for s in active:
        mods.setdefault(module_of(s["path"]), []).append(s)

    deps = {}  # module -> {module: edge count}
    for s in active:
        src = module_of(s["path"])
        for uid in s.get("uses", []):
            tgt = by_id.get(uid)
            if tgt and module_of(tgt["path"]) != src:
                deps.setdefault(src, {})
                dst = module_of(tgt["path"])
                deps[src][dst] = deps[src].get(dst, 0) + 1

    ranked = sorted(set(mods) | set(files_per_mod),
                    key=lambda m: (-len(mods.get(m, [])), m))
    shown, overflow = ranked[:MAX_MODULE_ROWS], ranked[MAX_MODULE_ROWS:]

    stack = sorted({label for name, label in MANIFESTS if (root / name).exists()})
    needs_role = []
    lines = [
        f"# Codebase index — built @ {sha or 'nogit'} · updated {date.today().isoformat()}"
        f" · backend {backend}",
        "# generated by build_index.py — Role/Owner cells are yours to fill and are preserved",
        "",
        "## Stack",
        ("- " + ", ".join(stack)) if stack else "- (no manifest detected)",
        f"- {len(files)} source files · {len(active)} indexed symbols · "
        f"{len(ranked)} modules",
        "",
        f"## Modules (top {len(shown)} by symbol count)",
        "| Path | Role | Depends on | Owner agent |",
        "|------|------|------------|-------------|",
    ]
    for mod in shown:
        role, owner = prior.get(mod, ("—", "—"))
        if role == "—":
            needs_role.append(mod)
        top = sorted(deps.get(mod, {}).items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        dep = ", ".join(m for m, _ in top) or "—"
        lines.append(f"| {mod} | {role} | {dep} | {owner} |")
    if overflow:
        rest = sum(len(mods.get(m, [])) for m in overflow)
        lines.append(f"| ({len(overflow)} more) | {rest} symbols — see shards | — | — |")

    lines += ["", "## Sizes", ""]
    for mod in shown:
        lines.append(f"- {mod}: {files_per_mod.get(mod, 0)} files, "
                     f"{len(mods.get(mod, []))} symbols")

    entries = _entry_points(files)
    lines += ["", "## Entry points (heuristic — confirm before relying on them)", ""]
    lines += [f"- {e}" for e in entries] or ["- (none matched)"]

    # Conventions are reference data, not generated state — they live in .agents/ref/.
    conv = sorted(p.name for p in ref_dir(root).glob("CONVENTIONS_*.md"))
    lines += ["", "## Conventions files", ""] + ([f"- .agents/ref/{c}" for c in conv]
                                                 or ["- (none)"])
    lines += ["", "## Symbols", "",
              f"- `.agents/state/index/SYMBOLS.md`"
              f"{' — index-of-indexes, one shard per module' if len(active) > threshold else ''}",
              "", "## Do-not-touch", "", "- src/legacy/", "- generated/", "- .env*", ""]
    pub.write(target, "\n".join(lines) + "\n")
    return {"modules": len(ranked), "entry_points": len(entries),
            "needs_role": needs_role}


def write_delta(root, symbols, sha, backend, delta, shard_info, cb_info, pub=None):
    pub = pub or _Publisher()
    idx = index_dir(root)
    needs_purpose = [sid(s["id"]) for s in symbols
                     if not s.get("deleted") and not s.get("purpose")]
    added_ids = set(delta["added"])  # hoisted: rebuilding this per symbol was O(n^2)
    # Phase 2 of the watermark: never below what phase 1 reserved, never below
    # what was just published. Monotone by construction (L-022).
    reserved = read_delta_bound(root)
    payload = {
        "built_sha": sha,
        "backend": backend,
        WATERMARK_KEY: max(reserved or 0, max((s["id"] for s in symbols), default=0)),
        "needs_module_role": cb_info["needs_role"],
        "counts": {
            "active": shard_info["active"],
            "deleted": sum(1 for s in symbols if s.get("deleted")),
            "added": len(delta["added"]),
            "changed": len(delta["changed"]),
            "removed": len(delta["removed"]),
        },
        "sharded": shard_info["sharded"],
        "shards": shard_info["shards"],
        "needs_purpose": needs_purpose,
        "added": [{"id": sid(s["id"]), "path": s.get("path"), "name": s.get("name"),
                   "kind": s.get("kind")}
                  for s in symbols if s["id"] in added_ids],
        "changed": [sid(i) for i in delta["changed"]],
        "removed": [sid(i) for i in delta["removed"]],
    }
    # A payload without the bound must be unbuildable: read back, a missing key
    # means "no known bound" and silently disarms the whole protection.
    if WATERMARK_KEY not in payload:  # unreachable by construction — that is the point
        raise RuntimeError(f"delta payload is missing {WATERMARK_KEY}")
    pub.write(idx / DELTA_NAME, json.dumps(payload, indent=2) + "\n")
    return payload


def read_bodies(root, generation):
    """`({id: sha}, note)` from INDEX_BODIES.json. `note is None` = USABLE.

    THE MAP IS BELIEVED WHOLE OR NOT AT ALL, and the discriminator is the
    generation. `generation` is the `built @ <sha>` stamp of SYMBOLS.md; the
    lateral carries its own. Anything else — file absent, unparseable, a
    different `algo`, a different stamp — yields `({}, <why>)`, and every caller
    treats that as "no body hash is known", never as "these few are".

    THIS IS WHAT MAKES THE PUBLISH ORDER IRRELEVANT. A build killed between the
    two publishes leaves one side at G-1: either the lateral is behind the files
    or the files are behind the lateral, and BOTH cases land here as one note and
    a refusal to believe a single entry. No half-trusted map, in either direction.
    """
    path = index_dir(root) / BODIES_NAME
    raw = _read(path)
    if raw is None:
        return {}, (f"{BODIES_NAME} absent — no body hash is known; the next "
                    f"build rebuilds it in full")
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}, f"{BODIES_NAME} is not readable JSON — the whole map is UNKNOWN"
    if not isinstance(payload, dict):
        return {}, f"{BODIES_NAME} is not an object — the whole map is UNKNOWN"
    algo = payload.get("algo")
    if algo != BODY_ALGO:
        return {}, (f"{BODIES_NAME} was written with algo {algo!r}, this kit "
                    f"computes {BODY_ALGO!r} — the whole map is UNKNOWN")
    stamped = payload.get("generation")
    if not generation or stamped != generation:
        return {}, (f"{BODIES_NAME} is stamped {stamped or 'nothing'}, the index "
                    f"files are stamped {generation or 'nothing'} — the whole map "
                    f"is UNKNOWN")
    bodies = payload.get("bodies")
    if not isinstance(bodies, dict):
        return {}, f"{BODIES_NAME} carries no `bodies` object — the whole map is UNKNOWN"
    out = {}
    for key, value in bodies.items():
        try:
            out[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return out, None


def write_bodies(root, symbols, sha, pub=None):
    """Publish INDEX_BODIES.json through the same atomic `_Publisher`.

    ONE ENTRY PER LIVE SYMBOL THAT ACTUALLY HAS A HASH. A tombstone gets none (a
    deleted body has nothing to hash) and neither does a symbol whose range did
    not resolve, so the map never carries a dead id and never carries a hash
    nobody computed. `sort_keys` + `indent` for the same reason `write_delta` has
    them: the bytes must be stable across two runs over the same tree.
    """
    pub = pub or _Publisher()
    bodies = {}
    for s in symbols:
        if s.get("deleted"):
            continue
        digest = s.get("body_sha")
        if digest:
            bodies[str(s["id"])] = digest
    payload = {"generation": sha or NO_GIT_STAMP, "algo": BODY_ALGO, "bodies": bodies}
    pub.write(index_dir(root) / BODIES_NAME,
              json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return payload


# ------------------------------------------------------------- single flight
# Two builds writing the same index at once is no longer corruption — publishes
# are atomic — but it is wasted work and interleaved generations. The lock is
# ADVISORY: anything that goes wrong acquiring it degrades to running unlocked
# with a printed notice, because a broken lock must never be the reason /index
# stops working.
LOCK_REL = Path(".agents") / "state" / "local" / ".build_index.lock"
LOCK_STALE_SECONDS = 300


def _lock_age(path):
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None  # vanished between O_EXCL and stat → treat as stealable


def acquire_lock(root):
    """Return `(state, path)`; state is acquired | stolen | held | degraded."""
    path = Path(root) / LOCK_REL
    try:
        # A fresh clone has no state/local/ at all (it is git-ignored).
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"build_index: lock directory unavailable ({e}) — running unlocked")
        return "degraded", None
    stolen = False
    for _ in (1, 2):  # at most one steal, then give up on locking entirely
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            age = _lock_age(path)
            if age is not None and age < LOCK_STALE_SECONDS:
                return "held", None
            try:
                os.unlink(str(path))
            except OSError:
                return "degraded", None
            stolen = True
            continue
        except OSError as e:
            print(f"build_index: lock unavailable ({e}) — running unlocked")
            return "degraded", None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()} {int(time.time())}\n")
        except OSError as e:
            # A lock we created but cannot stamp (disk full, AV interference) must
            # degrade like every other lock failure — never abort the build.
            try:
                os.unlink(path)
            except OSError:
                pass
            print(f"build_index: lock write failed ({e}) — running unlocked")
            return "degraded", None
        return ("stolen" if stolen else "acquired"), path
    print("build_index: lock contended — running unlocked")
    return "degraded", None


def release_lock(path):
    if path is None:
        return
    try:
        os.unlink(str(path))
    except OSError:
        pass  # win32 may keep it open; the age check recovers on the next run


def index_is_current(root, sha, backend, threshold, kinds_fp, scope, incremental,
                     dirscope_fp=None):
    """True when NO INDEXED FILE changed since the `built @` anchor (`--if-stale`).

    Fingerprint: the backend, --threshold, the --kinds digest and the effective
    directory-scope digest all match the published header, a bound is already
    reserved, and no in-scope source file changed. THE `built @` SHA IS NOT
    COMPARED since T-00000575: HEAD may be arbitrarily far ahead of it.

    CE N'EST DONC PLUS « une reconstruction produirait les mêmes fichiers », et
    la nuance a coûté un NO_GO de binôme : elle ne couvre PAS un changement du
    BUILDER lui-même — `SKIP_FILE_RE`, `MAX_FILE_BYTES`, `AMBIGUOUS_BUILD_DIRS`,
    un extracteur, la mise en page — qui n'entre dans aucune empreinte. Sur le
    kit c'est masqué, `.agents/bin/*.py` étant indexé donc dans `scope` ; sur un
    dépôt ADOPTANT, où `.agents` est dans `host_skip`, un upgrade du kit qui
    change ce qui est indexé n'atterrit JAMAIS par `--if-stale`. Mesuré par le
    binôme, les deux côtés. `--full` est le seul rattrapage, et le choix de
    l'empreinte à ajouter est porté par une tâche à part plutôt qu'improvisé ici.

    The `dirscope` comparison is redundant with `incremental` on the current call
    path (`_build` folds the same disagreement into that predicate, so a mismatch
    already forces a full build) and is kept anyway: this function is the ONE
    place the currency fingerprint is defined, and a fingerprint that omits a
    field it depends on is one refactor away from being wrong.
    """
    if not incremental or not sha or scope:
        return False
    line = _header_line(_read(index_dir(root) / MAIN_NAME))
    if not line:
        return False
    if read_delta_bound(root) is None:
        return False  # no reserved bound → rebuild, if only to reserve one
    if dirscope_fp is not None and published_dirscope(line) != dirscope_fp:
        return False
    # LE SHA NE DÉCIDE PLUS — CE QUI DÉCIDE, C'EST `scope` (T-00000575, décision
    # pilote « option C » du 2026-09-13).
    #
    # LE DÉFAUT. Ce prédicat exigeait `built @ == HEAD`. Or TOUT commit avance
    # HEAD : un commit de docs, de board, de plan rendait l'index « périmé » sans
    # qu'aucun fichier indexé ait bougé. `session-start.sh --if-stale`
    # reconstruisait alors, la reconstruction réécrivait les fichiers d'index,
    # l'arbre devenait sale, un `chore(index)` suivait — qui avançait HEAD à son
    # tour. Mesuré le 2026-09-13 avec `_keep()` : **125 des 200 derniers commits,
    # soit 62 %, ne touchent AUCUN fichier indexé** — 125 mesuré à l'ancre
    # `6ffd81c` ; le compte glisse entre 124 et 127 selon le commit où l'on se
    # place, et un chiffre sans son ancre n'est pas reproductible.
    #
    # POURQUOI LE RETIRER EST SÛR — ET LA PREMIÈRE RÉDACTION DE CE PARAGRAPHE
    # ÉTAIT FAUSSE, les deux critiques l'ont démontée. Elle disait : « le sha est
    # joignable, donc le `git diff` a réellement tourné ». Non — `cat-file -e`
    # atteste l'objet COMMIT, pas les arbres qu'il faut lire pour le diffuser :
    # sur un clone partiel hors ligne, le premier rend 0 et le second ÉCHOUE. Et
    # `git()` rendant `None` sur rc≠0, l'échec se lisait « rien n'a changé ».
    #
    # CE QUI REND LE RETRAIT SÛR EST DONC UNE GARDE ÉCRITE, pas une garde
    # espérée : `_changed_names` distingue « aucun changement » de « pas pu
    # mesurer », rend `None` dans le second cas, et l'appelant retire alors
    # l'incrémental — donc `scope` vaut `all_files`, donc cette fonction rend
    # faux dès sa première ligne. S'ajoute que `scope` est calculé SANS stater
    # l'arbre : un fichier indexé devenu trop gros ne peut plus sortir du
    # périmètre et faire passer un index figé pour un index à jour.
    #
    # CE QUI RESTE VÉRIFIÉ CI-DESSOUS : le backend, le seuil et l'empreinte des
    # kinds. Un index construit par un autre outillage reste périmé, lui — mais
    # pas un index construit par une AUTRE VERSION du même outillage : voir la
    # borne adoptant écrite dans la docstring.
    return (_header_field(line, "backend") == backend
            and _header_field(line, "threshold", r"\d+") == str(threshold)
            and _header_field(line, "kinds") == kinds_fp)


# ------------------------------------------------------- advisory DB staleness
DB_STALE_PREFIX = "DB STALE @ "
# `sys.modules` name the sibling migrate module is cached under. Private (leading
# underscore) so it cannot be mistaken for an importable module, and NAMED so the
# probe's second call reuses the first load instead of re-executing the file.
PROBE_MODULE = "_abk_index_db_probe"


def db_staleness_line(root, files_generation):
    """The ADVISORY second line of `--stale-check`: is the SQLite index store — a
    MACHINE store outside the repository since T-00000668, located by
    `migrate_index_to_db.db_path` (`cadre.paths.index_db()`) — a generation
    behind the index FILES?

    WHY IT LIVES IN THE PROBE (T-00000108). The DB is advisory in v1 — the files
    are still the authority and no automatic resync exists — so it goes stale at
    every rebuild and NOTHING said so: the three SessionStart hooks throw the
    builder's stdout away, and `migrate_index_to_db.py --verify` only speaks when
    a human runs it. The Stop-hook nudge is the one channel that already READS
    this probe's output and shows it to the pilot, so this is where the silence
    ends. Nothing here resyncs, marks, or writes anything.

    THE COMPARISON IS NOT OURS. `migrate_index_to_db.py` owns it
    (`db_generation_behind`, on the same predicate its `--check` / `--verify`
    use); this function only asks. Hence no hand-written `SELECT` here, and no
    second spelling of the `meta` key to drift from the first.

    RESOLVED BY SIBLING PATH, NEVER BY A BARE IMPORT, for two independent
    reasons: this module installs no `sys.path` shim and a consumer project loads
    it through `spec_from_file_location`, where `import migrate_index_to_db`
    would fail — precisely the tree that needs the warning most; and migrate
    imports THIS module, so a module-level import would be a cycle. The module is
    registered in `sys.modules` BEFORE `exec_module`, which is not decoration:
    measured on Python 3.14, an unregistered module makes migrate's `@dataclass`
    raise (`dataclasses` resolves `sys.modules[cls.__module__]`).

    Returns the line to print, or None. EVERY failure returns None — migrate
    absent, sqlite3 unavailable, an unreadable or corrupt DB, no `meta` table —
    so the DB half degrades in SILENCE and can never suppress the index verdict,
    raise, or change the exit code. `index.db` is never created: see
    `migrate_index_to_db.read_db_generation`, which checks existence before
    connecting and then opens `mode=ro`.
    """
    try:
        import importlib.util
        source = Path(__file__).resolve().parent / "migrate_index_to_db.py"
        if not source.is_file():
            return None
        name = PROBE_MODULE
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(name, source)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(name, None)
                raise
        behind = module.db_generation_behind(root, files_generation)
        if not behind:
            return None
        db_generation, files_stamp = behind
        # ASCII, hex-first head: the Stop hook parses the two generations out of
        # this line, and a cp1252 console mangles the em dash below to '?'.
        return (f"{DB_STALE_PREFIX}{db_generation or 'unknown'} vs files @ "
                f"{files_stamp} — the machine {module.DB_NAME} (outside the "
                f"repository) was built from another index generation; run python "
                f".agents/bin/migrate_index_to_db.py --resync — nothing to commit "
                f"(advisory in v1: the FILES remain the authority)")
    except Exception:  # noqa: BLE001 — a probe reports; it never raises
        return None


# --------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic incremental index builder.")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    ap.add_argument("--full", action="store_true", help="ignore the built@ anchor; rebuild all")
    ap.add_argument("--if-stale", action="store_true",
                    help="skip the build when the index already matches HEAD, the "
                         "backend, --threshold, --kinds and the effective directory "
                         "scope, and no in-scope source file changed (prints INDEX "
                         "CURRENT, writes nothing). --full overrides.")
    ap.add_argument("--stale-check", action="store_true",
                    help="read-only probe: print INDEX CURRENT or INDEX STALE and "
                         "write NOTHING, using exactly the --if-stale currency "
                         "computation. This is the Stop-hook nudge's signal "
                         "(T-00000033) — one staleness definition, owned here, so "
                         "the nudge can never disagree with the refresh it "
                         "recommends. Adds a second, independent 'DB STALE @ …' "
                         "line when the advisory index.db lags the index files "
                         "(T-00000108), asked of migrate_index_to_db.py and "
                         "silent when it cannot be answered. Always exits 0.")
    ap.add_argument("--threshold", type=int, default=500, help="max entries before sharding")
    ap.add_argument("--kinds", default=os.environ.get("ABK_INDEX_KINDS"),
                    help="comma-separated ctags kind names to keep (default: structural)")
    ap.add_argument("--unskip", default=os.environ.get("ABK_INDEX_UNSKIP"),
                    help="comma-separated host directories to keep indexing even in a "
                         "tree detected as a vendored kit. CLOSED vocabulary: "
                         + ", ".join(sorted(HOST_DIRS)) + ". Anything else is a usage "
                         "error — '.agents' in particular is NOT reachable this way, so "
                         "L-020 stays unconditionally true, and neither is a kit code "
                         "root (" + ", ".join(sorted(KIT_CODE_DIRS)) + "): it is the "
                         "kit's code, never the consumer's.")
    args = ap.parse_args(argv)
    kinds = ({k.strip() for k in args.kinds.split(",") if k.strip()}
             if args.kinds else CTAGS_KINDS)
    # Closed vocabulary, checked before anything runs. Three chains of caveat
    # elsewhere assert '.agents is excluded by construction'; an open-ended escape
    # hatch here would let a flag silently falsify all three.
    unskip = {u.strip() for u in (args.unskip or "").split(",") if u.strip()}
    if unskip - HOST_DIRS:
        ap.error("--unskip / ABK_INDEX_UNSKIP accepts only "
                 + ", ".join(sorted(HOST_DIRS)) + "; rejected: "
                 + ", ".join(sorted(unskip - HOST_DIRS)))

    # Never let a non-UTF-8 console (e.g. Windows cp1252) crash the summary print;
    # the index FILES are always written as UTF-8 regardless.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    root = Path(args.root).resolve()
    global _PUBLISHER
    pub = _PUBLISHER = _Publisher()
    state, lock_path = acquire_lock(root)
    if state == "held":
        print("INDEX BUILD IN FLIGHT — skipped")
        return 0
    if state == "stolen":
        print(f"build_index: lock older than {LOCK_STALE_SECONDS}s taken over "
              f"(previous build died without releasing it)")
    try:
        # Resolved ONCE per run and passed down as a parameter — like `kinds` —
        # never parked in a module global: `dashboard.py` imports this module and
        # the tests drive `cli()` in-process, so a mutated global would leak one
        # root's scope into the next and make test order significant.
        return _build(root, args, kinds, pub, host_skip_dirs(root, unskip))
    finally:
        pub.cleanup()
        release_lock(lock_path)


def _build(root, args, kinds, pub, host_skip=frozenset()):
    sha = head_sha(root)
    _authoritative, _orphans, status = classify_index_files(root)
    if status == "identity-lost":
        if getattr(args, "stale_check", False):
            # Read-only probe: a lost identity source certainly needs a
            # rebuild decision, but the probe itself never exits non-zero
            # (it runs from a Stop hook — exit 2 there would loop the host).
            # Deliberately index-only: with the identity source gone there is no
            # trustworthy generation to compare the advisory DB against, and a
            # second verdict here would just add noise to a louder problem.
            print(f"INDEX STALE @ {head_sha(root) or 'nogit'} — identity source lost")
            return 0
        if not args.full:
            # Exit 1 as well, but with its OWN marker: the marker line, not the
            # code, is the machine signal that tells this apart from a
            # mixed-generation publish failure.
            print(IDENTITY_LOST)
            return 1
        print("build_index: --full over a lost identity source — rebuilding identity "
              "from scratch; every existing SYM-ID citation will dangle")
    built_sha = None
    header_line = _header_line(_read(index_dir(root) / MAIN_NAME))
    anchor = _header_field(header_line, "built @")
    # Hex-only validation before the sha reaches git as a positional arg (L-009
    # discipline): the header is on-disk data an editor or merge could mangle,
    # and a mangled anchor must degrade to a full scan, not become a git flag.
    if anchor and re.fullmatch(r"[0-9a-fA-F]{4,40}", anchor):
        built_sha = anchor

    # ORDERING IS LOAD-BEARING. The scope digest is computed and compared HERE,
    # BEFORE `incremental` is decided, and the disagreement is folded INTO that
    # predicate — not tested later. A narrowed scope must produce a FULL build,
    # because the purge below only tombstones what is outside `scope`: fold the
    # disagreement in after `scope` was already set to the changed-files list and
    # `reconcile(purge=True)` would tombstone every symbol of every UNCHANGED file
    # instead of just the newly-excluded ones. Hence the invariant asserted a few
    # lines down: purge=True ⇒ scope IS all_files.
    dirscope_fp = scope_fingerprint(host_skip)
    dirscope_agrees = published_dirscope(header_line) == dirscope_fp

    # THE BODY MAP IS PART OF THE SAME PREDICATE, and it belongs HERE rather than
    # in `index_is_current` (T-00000377). Forcing a rebuild from there would leave
    # the build INCREMENTAL with a possibly EMPTY scope: it would re-extract
    # nothing, publish `{"generation": <sha>, "bodies": {}}` — generationally
    # VALID and empty — and every reader would answer UNKNOWN forever, with
    # nothing left to nudge it. Folded in here, an absent or disagreeing lateral
    # makes `incremental` False, hence `purge` True, hence `scope is all_files`
    # (the RuntimeError below pins that chain): exactly ONE full rebuild, which
    # populates the map for every live symbol.
    prev_bodies, bodies_note = read_bodies(root, anchor)
    incremental = (not args.full) and built_sha and is_git(root) \
        and git(root, "cat-file", "-e", built_sha) is not None \
        and dirscope_agrees and bodies_note is None
    all_files = all_source_files(root, host_skip)
    # UN SEUL TOUR DE `git`, DEUX FILTRES — parce que les deux questions ne sont
    # pas la même (T-00000575) : CONSTRUIRE doit écarter un fichier illisible ou
    # trop gros ; DÉCIDER DE LA FRAÎCHEUR ne le doit pas, sinon un fichier sorti
    # du périmètre par sa TAILLE rend le scope vide et l'index « à jour » sur des
    # symboles morts. Et un diff en ÉCHEC (`None`) retire l'incrémental : sans le
    # sha pour rattraper, un git muet valait « rien n'a changé ».
    changed_names = _changed_names(root, built_sha) if incremental else None
    if incremental and changed_names is None:
        incremental = False
    if incremental:
        scope = sorted(f for f in changed_names if _keep(f, root, host_skip))
        # UN NON SUIVI DU PÉRIMÈTRE REND `STALE` POUR TOUJOURS — DÉCISION ÉCRITE,
        # pas un défaut (`StaleCheckTests`, T-00000033) : la sonde pousse à COMMITER.
        # Mesure du 2026-09-14 (résidu de 319 Ko, 17 fichiers salis) puis option (b)
        # du pilote, `T-00000608` : la SONDE garde son nudge et NOMME le fichier,
        # `--if-stale` ne reconstruit plus sur un scope de SEULS non suivis. Le récit
        # suit dans la docstring de `_non_suivis` et aux deux branches plus bas.
        scope_currency = sorted(f for f in changed_names if _keep(f, None, host_skip))
        # Calculé ICI, une fois, pas au site de décision : `--stale-check` et
        # `--if-stale` lisent LA MÊME liste, sinon la sonde nommerait ce que le
        # rafraîchissement ne compte pas — la divergence exacte que ce ticket ferme.
        _nsuivis = _non_suivis(root)
        scope_non_suivi = [f for f in scope_currency if f in _nsuivis]
        scope_suivi = [f for f in scope_currency if f not in _nsuivis]
    else:
        scope = scope_currency = all_files
        scope_non_suivi = scope_suivi = []  # non mesurés hors incrémental

    ctags_bin = ctags_binary()
    backend = "ctags" if ctags_bin else "fallback"
    kinds_fp = kinds_fingerprint(kinds)
    stamp = build_stamp(args.threshold, kinds_fp, dirscope_fp)

    current = (not args.full) and index_is_current(
        root, sha, backend, args.threshold, kinds_fp, scope_currency,
        bool(incremental), dirscope_fp)

    # T-00000608, option (b) du pilote : LE SCOPE N EST QUE DES NON SUIVIS, qu un
    # --full laisse dehors (`all_source_files` lit `git ls-files` SEUL) et qu un
    # incremental met dans le scope ET l index (T-00000230). Traites CURRENT pour
    # CONVERGER, pas parce qu un rebuild ne changerait rien ; CE meme predicat.
    _que_non_suivis = bool(incremental) and bool(scope_non_suivi) and not scope_suivi

    if getattr(args, "stale_check", False):
        if current:
            print(f"INDEX CURRENT @ {sha or 'nogit'} — nothing to rebuild")
        elif _que_non_suivis:
            # LA SONDE GARDE SON NUDGE (T-00000033 ne cede pas) : STALE, le fichier
            # NOMME, l effet REEL d une reconstruction. Trois textes y ont menti,
            # mesures : << a rebuild would change … >> (2026-09-14, un --full
            # laissait le verdict identique) ; le remede add-seul (passe 1 :
            # `diff --cached` renomme le fichier) ; << seuls retrait, ignore … >>
            # (binome ter : enumeration fausse, et le fantome ABSORBE etait tu).
            print(f"INDEX STALE @ {sha or 'nogit'} — {len(scope_non_suivi)} "
                  "fichier(s) NON SUIVI(S) dans le périmètre indexé ; un build "
                  "incrémental les AJOUTE, un --full les RETIRE (T-00000230), et la "
                  "sonde reste STALE ; un commit puis un rebuild la rend CURRENT, un "
                  "retrait ou un ignore aussi (REMEDE).")
        else:
            print(f"INDEX STALE @ {sha or 'nogit'} — a rebuild would change the index files")
            if scope_non_suivi:  # T-00001136 : l'état MIXTE les nomme aussi.
                print(f"  dont {len(scope_non_suivi)} NON SUIVI(S) dans le périmètre "
                      "indexé, qu'un rebuild n'éteint pas (T-00000608) :")
        for f in scope_non_suivi[:10]:  # vide si CURRENT : scope_currency l'est
            print(f"    - {f}")
        if len(scope_non_suivi) > 10:
            print(f"    … et {len(scope_non_suivi) - 10} autre(s)")
        if _que_non_suivis:
            print("  REMEDE : `git add` + `git commit`, puis un rebuild (--if-stale, "
                  "build nu ou --full) ; un add SEUL laisse STALE et fait reconstruire "
                  "--if-stale à chaque appel. Ou retire/ignore le fichier : la SONDE "
                  "redevient CURRENT, mais s'il était déjà ABSORBÉ par un build "
                  "incrémental, ses symboles restent ACTIFS — un --full les retire "
                  "aussitôt ; sans --full, un retiré tombe au prochain build nu (pas "
                  "--if-stale, qui répond CURRENT), un ignoré survit aux builds "
                  "incrémentaux. Un non suivi seul ne fait plus reconstruire "
                  "--if-stale (T-00000608).")
        elif scope_non_suivi:  # T-00001136 : REMEDE de l'état MIXTE, chaque geste joué.
            print("  REMEDE (état mixte) : `git commit` des SUIVIS modifiés puis un "
                  "rebuild (--if-stale, build nu ou --full) rend CURRENT si chaque NON "
                  "SUIVI est réglé avant ce rebuild — `git add` + `git commit`, un "
                  "retrait (ses symboles ABSORBÉS tombent à ce rebuild) ou un ignore "
                  "(ils survivent aux builds incrémentaux, un --full les retire) ; "
                  "sinon la sonde ne nomme plus qu'eux, avec leur REMEDE.")
        # Second, INDEPENDENT verdict (T-00000108): the advisory SQLite store can
        # be a generation behind while the FILES are perfectly current — that is
        # the common case, since every rebuild leaves it behind. Compared against
        # `anchor`, the files' own `built @` stamp, which is exactly the
        # generation migrate's --check/--verify compare the DB to.
        db_line = db_staleness_line(root, anchor)
        if db_line:
            print(db_line)
        return 0

    if args.if_stale and current:
        print(f"INDEX CURRENT @ {sha or 'nogit'} — nothing to rebuild")
        return 0

    if args.if_stale and _que_non_suivis:
        # LA CONVERGENCE (moitie que T-00000575 defend) ne cede pas non plus : sans
        # ce retour, `session-start.sh --if-stale` reconstruisait a CHAQUE demarrage
        # sur un STALE qu aucun rebuild n eteint, salissant 17 a 18 fichiers suivis
        # (2026-09-14 : residu non suivi, neuf heures, une nuit). La sonde dit STALE.
        print(f"INDEX CURRENT @ {sha or 'nogit'} — rien à reconstruire : les "
              f"{len(scope_non_suivi)} fichier(s) du périmètre sont NON SUIVI(S) ; "
              "--if-stale ne reconstruit pas sur ce seul motif, --stale-check "
              "les NOMME (T-00000608).")
        return 0

    purge = not incremental
    # Structural precondition, not an `assert` (must hold under `python -O` too):
    # `purge` tombstones every prior symbol whose file is outside `scope`, so a
    # partial scope with purge on would tombstone the whole unchanged codebase.
    # Pinned by a test as well — this is the one guard against reintroducing that
    # ordering defect by moving the fingerprint comparison below the predicate.
    if purge and scope is not all_files:
        raise RuntimeError(
            "build_index: purge requires the FULL source set as scope "
            f"({len(scope)} files scoped vs {len(all_files)} in the tree) — the "
            "incremental predicate must be decided BEFORE scope is assigned")
    symbols, delta = reconcile(root, scope, ctags_bin, kinds, purge=purge,
                               bodies=prev_bodies)
    set_id_width(max((s["id"] for s in symbols), default=1))
    # Phase 1: reserve the id bound BEFORE the first publish (L-022). Everything
    # from here on is a publish, so a failure means mixed generations on disk.
    reserve_watermark(root, max((s["id"] for s in symbols), default=0), pub)
    shard_info = write_index(root, symbols, sha, backend, args.threshold, pub, stamp)
    cb_info = write_codebase_index(root, symbols, all_files, sha, backend,
                                   args.threshold, pub)
    payload = write_delta(root, symbols, sha, backend, delta, shard_info, cb_info, pub)
    write_bodies(root, symbols, sha, pub)
    # True orphans go last, once every artefact of this generation is published.
    drop_stale_shards(root, shard_info["keep"])

    mode = "incremental" if incremental else "full"
    c = payload["counts"]
    print(f"INDEX BUILT @ {sha or 'nogit'} [{backend}, {mode}, {len(scope)} files scanned]:")
    print(f"- SYMBOLS: {c['active']} active (+{c['added']} / ~{c['changed']} / -{c['removed']})"
          f"{' · sharded ' + str(shard_info['shards']) if shard_info['sharded'] else ''}")
    print(f"- CODEBASE_INDEX: {cb_info['modules']} modules, "
          f"{cb_info['entry_points']} entry point(s)")
    # HONEST PHRASING (T-00000104). These two lines used to read "-> indexer
    # annotates the delta" and "-> indexer fills Role/Owner", which named a
    # TRIGGER THAT DOES NOT EXIST: `indexer` is a CONDITIONAL, annotation-only
    # pipeline stage invoked by the orchestrator or a human — never something a
    # build schedules, and deliberately not the index-freshness mechanism (that is
    # `--if-stale`, 0 LLM). Measured on a consumer project the first line read
    # "needs purpose: 5947 symbol(s) -> indexer annotates the delta": a five-digit
    # count in front of an arrow promising automatic work that would never happen.
    # The count is kept — it is the useful half — and the arrow is replaced by the
    # deliberate gesture, named. ASCII only: a cp1252 console mangles an em dash.
    print(f"- {len(payload['needs_purpose'])} symbol(s) carry no ':: purpose' "
          f"- annotating them is a DELIBERATE step, nothing triggers it: invoke "
          f"the 'indexer' agent (backlog: {DELTA_NAME} -> needs_purpose)")
    if cb_info["needs_role"]:
        print(f"- {len(cb_info['needs_role'])} module(s) carry no Role/Owner "
              f"- same deliberate step, not triggered: the 'indexer' agent fills "
              f"those cells (backlog: {DELTA_NAME} -> needs_module_role)")
    return 0


# ------------------------------------------------------------------ exit policy
FAILED_BEFORE = "build_index: FAILED before publish, previous index intact"
FAILED_MID = ("build_index: FAILED mid-publish, index files are mixed-generation; "
              "re-run to converge")
_PUBLISHER = None


def cli(argv=None):
    """Return the process exit code. Two failure shapes, kept distinguishable.

    Nothing published yet (`_PUBLISHER.replaced == 0`) → 0 + FAILED_BEFORE: the
    previous index is intact and nothing changed, which is exactly the case the
    original blanket `except Exception: sys.exit(0)` was defending — "never
    hard-fail a build the pipeline depends on". That intent is kept, but it now
    routes through the publish-progress flag instead of swallowing every failure.

    Something already published → 1 + FAILED_MID: the artefacts on disk no longer
    belong to one generation, and only a re-run converges them. Silence here was
    the L-021 defect: a half-written index reported success.

    The stdout MARKER is the machine signal, not the code: the identity refusal in
    `_build` also exits 1, with its own marker line. Nothing ever exits 2 — from a
    Stop hook, exit 2 makes the host loop (regression 5e43ba6).
    """
    try:
        return main(argv)
    except SystemExit:
        raise
    except Exception as e:
        print(f"build_index: {type(e).__name__}: {e}", file=sys.stderr)
        published = _PUBLISHER is not None and _PUBLISHER.replaced > 0
        print(FAILED_MID if published else FAILED_BEFORE)
        return 1 if published else 0


if __name__ == "__main__":
    sys.exit(cli())
