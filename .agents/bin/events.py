#!/usr/bin/env python3
"""Canal-A event emission — the observability dashboard's own write path.

Design doc: docs/design/2026-07-26-observability-dashboard.md §B.1 (contract),
§C (envelope schema), §D (retention). Task: docs/tasks/T-00000018.md (shard 1).

WHAT THIS MODULE IS: one public function, `emit(kind, **fields)`, that appends
a single JSON line to a per-writer day-file under `.agents/state/events/`,
plus `compact()` / `--compact` to fold old day-files into monthly digests.
Nothing here reads or aggregates the day-files themselves for the dashboard —
"le lecteur agrège, jamais l'émetteur" (design doc §C); `compact()` is the one
deliberate exception, and it only ever produces COUNTS, never replays raw
event bodies. Canal A is observational and disposable: deleting
`state/events/` must never break anything else in the kit.

WRITE PATH — GATE A finding and the pivot to per-writer files:

    Shard 1's first cut used one shared day-file (`YYYY-MM-DD.jsonl`) with a
    single O_APPEND write() per line, on the premise that O_APPEND below
    PIPE_BUF is atomic across concurrent writers — true on POSIX, NOT proven
    on Windows. The GATE A probe (test_events.py) spawned concurrent OS
    processes writing to that shared file and found real data loss on this
    platform (e.g. 428/480, 450/480, 376/480, 406/480 lines survived across 4
    runs — never corrupted JSON, always fewer lines than written, i.e. a lost
    update, not a torn write). Isolated to rule out a harness bug: a single
    process alone lost 0/2000. Reproduced independently by the coordinator
    (432/480, same shape) and recorded as constraint **L-00000041**.

    Root cause (documented, not re-derived every time someone reads this):
    Windows' CRT-level `os.open(..., os.O_APPEND)` does a seek-to-EOF-then-
    write per call rather than routing through the one atomic "append at
    current EOF" kernel op POSIX guarantees; two processes can race that seek
    and one write clobbers/loses the other's slot.

    Rejected fixes, and why (pilot decision, both explicit no's):
      A. Native Win32 `FILE_APPEND_DATA`-only handle (atomic on local NTFS) —
         rejected because that atomicity is documented for LOCAL NTFS only; a
         provisioned project on a network share would regress silently.
      B. A lock around the write — rejected because correctness would depend
         on every writer, across all 4 hosts, consistently taking the same
         lock; one non-conforming caller silently restores the race (the
         L-025 shape).

    CHOSEN: **option C — one file per writer.** Day-file name is `YYYY-MM-DD.<host>.<pid>.jsonl`,
    where `<pid>` is `os.getpid()` — THE PROCESS's own id, used ONLY to keep filenames apart. This
    is a distinct concept from the envelope's `pid` FIELD below, which is `prompt_id`, the canal-B
    join key — an earlier review round caught exactly this conflation risk, hence the repeated
    comment at both sites (here and in `_build_record`). Sole ownership per process removes
    cross-process contention structurally: no lock, no atomicity assumption to verify per platform,
    nothing to get wrong four hosts at a time.

    NO RANDOMNESS in the filename, on purpose. `os.getpid()` reuse is safe by construction here:
    the OS will not hand out the same pid to two processes that are both alive at once, so two
    processes that ever share a `(day, host, pid)` triple cannot be concurrent with each other —
    therefore cannot contend for the same file. Adding a random suffix would only make the per-day
    file count unbounded for no correctness gain; this reasoning IS the design, not an
    optimization, so it stays a comment, not a TODO.

    In-process concurrency is a SEPARATE, smaller problem: two threads in one process share a pid,
    so they share a filename, so they CAN race the same seek+write the cross-process case did. A
    single module-level `threading.Lock()` around the write closes that gap — in-process only, so
    it does not reintroduce option B's cross-host conformance problem (there is exactly one process
    here to conform, and it is this module).

    `.gitattributes:17` (`/.agents/state/events/*.jsonl merge=union`) still matches every
    per-writer filename (it globs on the `.jsonl` suffix, not on a fixed stem) — verified, no
    change needed. Union-merge is now belt-and-braces rather than load-bearing: with sole ownership
    per writer, two branches should never touch the same physical file in the first place, but
    keeping the merge driver costs nothing and guards the (believed-impossible) case of a same-day,
    same-host, same-pid collision across two different machines.

READERS MUST GLOB, NEVER ASSUME ONE FILE PER DAY. A day is now N files (one per writer that ran
that day); anything that reads `state/events/` — `compact()` below, the eventual dashboard
collector, and every test in `test_events.py` — globs `*.jsonl` and aggregates. This was always the
reader-aggregates contract (design doc §C); option C is the first thing that makes it load-bearing
rather than aspirational.

IMPORT CONTRACT — non-negotiable, read before wiring a new call site:

    Call sites MUST load this module by explicit path, e.g.:

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "events", <absolute-path-to-this-file>)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        mod.emit("hook.deny", guard="protect-paths", rule="...", path="...")

    `from events import emit` is BANNED for shard-2/3 call sites. Two existing
    hooks run Python fed from stdin (run-recap.sh:9, log-agent-usage.sh:10);
    there `sys.path[0]` is the invoking shell's cwd, not this file's
    directory, so a bare name-import silently resolves to nothing (or the
    wrong module, if some unrelated `events.py` happens to be importable).
    `run-recap.sh:39-41` already loads `tasks.py` this way — follow that
    precedent, not a package-style import.

FAIL-OPEN CONTRACT — absolute, for `emit()` only: it never raises. An unwritable path, a full
disk, a missing `state/events/` directory, a value `json.dumps` refuses to serialize — all of it
is swallowed, counted in THIS process's `get_diagnostics()["lost_events"]` (T-00001133) — which no
runtime code reads today (tests only: no hook reads or reports it) — and `emit()` returns `None`.
A hook must never break because of telemetry (precedent `5e43ba6`, "stop hook loop — benign 'no
ecosystem' must not exit 2"). `compact()` is a separate, explicit, operator-invoked maintenance
action, not on any hook's hot path, and may be more talkative about per-file failures (its doc).

C12 — no self-report of a permanently absent module: there is deliberately no "module could not be
loaded, write it on the next successful emit" mechanism here. A permanently absent/broken module
has, by definition, no next successful emit to piggyback such a report on — the mechanism cannot
fire in the one mode it would exist for. Permanent absence is unreportable in-band by construction;
the reader infers it instead (design doc §G.4:459). What IS reportable in-band, and is handled
below, is a *partial* drop inside an otherwise-working process (C13).
"""
from __future__ import annotations

import contextlib
import errno
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# --- T-00000641 : RÉDACTION DES SECRETS À L'ÉCRITURE (couture d'import) -------
# `redaction.py` (invariant « aucun secret au ledger ») est résolu PARESSEUSEMENT,
# à la première écriture — jamais au niveau module : un échec à l'import tuerait ce
# fichier ENTIER, donc `tasks.py` qui importe `events`, et rendrait le fail-open
# IMPOSSIBLE.
#
# DÉCISION PILOTE S-00001655 — résolution à DEUX BRANCHES :
#   (1) le PAQUET INSTALLÉ `cadre.ledger.redaction` (jamais un doublon embarqué :
#       une seconde copie serait une seconde vérité à maintenir), seulement si le
#       `cadre` chargé vient du dossier du kit, ou s'il n'y en a pas (`_cadre_d_ici`) ;
#   (2) À DÉFAUT SEULEMENT, le chargeur PAR CHEMIN ci-dessous — REPLI DÉCLARÉ, qui
#       devient du code mort à retirer le jour où (1) est garanti.
# Mesuré au 2026-09-20 : le paquet n'était PAS importable, donc (2) prenait le relais.
# Depuis vendor 5/5, (1) ne joue que si le `cadre` du kit est DÉJÀ chargé, ou si le kit ne
# porte aucun paquet (roue installée) ; sinon (2), par chemin — jamais un import d'abord.
# `_CHEMIN_REDACTION` est un GLOBAL, et (1) est isolée dans `_importer_redaction_paquet`
# — les deux sont monkeypatchables, pour exercer chaque branche (T10/T14/T17, banc
# de sélection de branche).
#
# POSTURE DU SPOOL — FAIL-OPEN (distincte du store du run `event_store.py`, qui
# est fail-CLOSED) : l'échec des DEUX branches rend `None`, `emit` écrit QUAND MÊME
# la ligne mais NEUTRALISE `data`, l'enveloppe et `user` (voir `emit`), et
# `_DIAGNOSTICS["redaction_unavailable"]` est incrémenté. Fail-open pour le
# processus, fail-closed pour le secret. Sentinelle d'échec DISTINCTE de « pas
# encore tenté » (A-R2) : sans elle un échec serait retenté à CHAQUE écriture.
# BORNE ADOPTANT : hors clone du kit ET sans paquet installé, aucune branche
# n'aboutit → rédaction ABSENTE (spool neutralisé).
def _chemin_redaction(racine: Path) -> Path:
    """Le `redaction.py` du paquet `cadre` de `racine` (T-01M5BXTRP8GKS7DMDQCTKK88DZ) : le
    premier de `.agents/vendor/cadre`, `src/cadre` qui porte `__init__.py` ; aucun des deux :
    le lieu vendor, qu'un échec nomme. Stdlib seule — `events.py` ne charge pas le résolveur."""
    vendor = racine / ".agents" / "vendor" / "cadre"
    for paquet in (vendor, racine / "src" / "cadre"):
        if (paquet / "__init__.py").is_file():
            return paquet / "ledger" / "redaction.py"
    return vendor / "ledger" / "redaction.py"


_CHEMIN_REDACTION = _chemin_redaction(Path(__file__).resolve().parents[2])
_ECHEC = object()  # sentinelle : un échec MÉMOÏSÉ, jamais reconfondu avec None
_REDACTION: Any = None  # None = pas encore tenté


def _cadre_d_ici(dossier: Path) -> bool:
    """(1) admise : `dossier` sans paquet, ou le `cadre` CHARGÉ en vient — le contrôle de
    `verifier_charge` (vendor_paths.py), en stdlib seule. Non chargé ou d'un autre arbre : (2)."""
    if not (dossier / "__init__.py").is_file():
        return True
    fichier = getattr(sys.modules.get("cadre"), "__file__", None)
    try:
        return bool(fichier) and Path(fichier).resolve().parent == dossier.resolve()
    except (OSError, RuntimeError):
        return False


def _importer_redaction_paquet() -> Any:
    """Branche (1), S-00001655 : résoudre `redaction` par le PAQUET INSTALLÉ, seulement si sa
    provenance tient (`_cadre_d_ici`) — jamais `import_module` d'abord (S-01M5CN1KM2) : un
    `cadre` posé par PYTHONPATH ne remplace pas la rédaction des secrets. Point de test."""
    if not _cadre_d_ici(_CHEMIN_REDACTION.parents[1]):
        raise ImportError("`cadre` d'un autre arbre ou non chargé : (2) par chemin")
    return importlib.import_module("cadre.ledger.redaction")


def _redaction() -> Any:
    """Le module `redaction`, mémoïsé, en DEUX branches (S-00001655) : (1) le
    paquet installé, puis (2) — à défaut SEULEMENT — le chargeur par chemin (repli
    déclaré). Rend `None` si les DEUX échouent (jamais une exception : `emit` ne
    doit pas lever). Un seul chargement RÉUSSI par processus, un seul échec
    MÉMOÏSÉ par processus (A-R2)."""
    global _REDACTION
    if _REDACTION is None:
        try:
            _REDACTION = _importer_redaction_paquet()  # (1) paquet installé
        except Exception:
            try:
                spec = importlib.util.spec_from_file_location(
                    "_cadre_redaction_events", _CHEMIN_REDACTION
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                _REDACTION = module  # (2) repli PAR CHEMIN, déclaré
            except Exception:
                _REDACTION = _ECHEC
    return None if _REDACTION is _ECHEC else _REDACTION

# 4 KiB (PIPE_BUF-class ceiling on the platforms this has been checked on). One line must stay
# under this. Under option C this is no longer an atomicity requirement (each writer owns its file)
# but the cap is kept: an unbounded line is still a single caller misbehaving, worth truncating
# rather than growing the tracked day-file without limit.
_DATA_CAP_BYTES = 4096

# Closed `kind` vocabulary (design doc §C: session.* task.* agent.* gate.* hook.* scan.* index.*
# ledger.add). Adding a kind means adding it here AND giving it an ALLOWLIST entry before any call
# site uses it. A kind with no ALLOWLIST entry still validates (KNOWN_KINDS membership) but every
# `data` field sent under it is dropped-and-counted (see C13 below) — a safe default, not a bug;
# shard 2/3 extends ALLOWLIST as each new call site is wired, it does not need to touch this set
# again unless the family itself grows.
KNOWN_KINDS: frozenset[str] = frozenset({
    "session.start", "session.stop", "session.compact", "session.notify",
    "task.new", "task.state", "task.stage",
    "agent.start", "agent.stop",
    "gate.forecast", "gate.plan_verdict", "gate.approval", "gate.security",
    "gate.coverage_degraded",
    "hook.deny", "hook.warn", "hook.check_fail",
    "scan.secrets", "scan.sast", "scan.sca", "scan.iac", "scan.waiver",
    "scan.mcp_call",
    "index.build", "index.stale",
    "ledger.add",
})

# Envelope keys: supplied by the caller as ordinary keyword args to emit(),
# but land in the envelope, never in `data` — they are the canal-B join keys
# (sid/pid/aid) plus routing context, not payload. `user` is NOT in this set:
# it is derived (see _resolve_user), never passed by the caller.
_ENVELOPE_KEYS: frozenset[str] = frozenset(
    {"host", "sid", "pid", "aid", "task", "agent", "effort"}
)

# T-00000641 (bloquant B) : en mode dégradé, les valeurs d'appelant sont
# NEUTRALISÉES par ce littéral (zéro octet d'appelant), APRÈS `_build_record` —
# jamais via `fields`, que `_build_record` jetterait puis reconstruirait BRUT.
# `_CLES_DEGRADEES` est DÉRIVÉ de la constante, jamais recopié à la main.
_MARQUEUR_DEGRADE = "[REDACTION INDISPONIBLE]"
_CLES_DEGRADEES: frozenset[str] = _ENVELOPE_KEYS | {"user"}

# Per-kind field allowlist (design doc §C + task constraints). NOTHING
# outside this list is ever written to `data` for that kind — an
# out-of-allowlist field is dropped and bumps a diagnostics counter (C13); it
# never raises and never blocks the rest of the event.
#
# scan.mcp_call: server package identity, tool suffix, audit state,
#   duration_ms — NEVER `tool_input` / `tool_response` (an MCP argument can be
#   a live credential; this day-file is tracked). `audit_state` is a 3-state
#   field, audited | unaudited | unresolved (C15) — `unresolved` is a NORMAL
#   outcome (e.g. no `.mcp.json` in this repo), never itself a degradation;
#   raising `gate.coverage_degraded` is reserved for a resolution *failure* on
#   a server actually present in project config (shard 2/3 concern, not
#   enforced by this flat allowlist).
# session.compact: trigger + token counters — NEVER `compact_summary` (model
#   prose does not belong in a committed file).
# scan.secrets|sast|iac: counters + file:line locations, plus `status` —
#   scanned | degraded | skipped, for these single-tool kinds.
# scan.sca (C14): same field names, but here `status` is a PER-ECOSYSTEM MAP,
#   never one collapsed tri-state — sca-scan.sh's own `.degraded` marker is
#   per-ecosystem (npm/java/swift/python/supply-chain/iac + go/rust/dotnet/php/ruby
#   (degraded = not covered in v1, never scanned); sca-scan.sh:290+), so a
#   single `status=scanned` would assert "scanned, clean" for an ecosystem
#   that never ran (the exact L-010 false-GO shape). The map-vs-scalar shape
#   is a caller contract this flat allowlist cannot itself enforce — the
#   plumbing that fills it is shard 2/3; shard 1 only defines and tests the
#   schema (see test_events.py's C14 case).
# hook.deny/warn/check_fail: which guard, which rule matched, the path —
#   never file content.
# hook.deny.{cmd_sha256,cmd_len} (T-00000018, class-1 finding, security-code-
#   review): safe-bash.sh's guard operates on a whole shell COMMAND, not a
#   file path — `tool_input.command` is model-controlled and can legitimately
#   contain a live credential (e.g. `curl -H "Authorization: Bearer <token>"
#   ... && rm -rf dist`). Putting that string in `path` (i) is a lie about
#   its shape and (ii) means gitleaks never inspects it (gitleaks scans
#   Edit/Write content and the working-tree diff, never a hook's own JSONL
#   append), so a leaked secret would land, unredacted, in a file this design
#   intends to become tracked. A blocklist of `Bearer`/`Authorization:`/
#   token-shaped substrings was REJECTED as the primary defence — that is the
#   same enumerate-instead-of-normalize mistake already found in this file's
#   OWN rm/mv matching logic (L-00000042); here the failure mode is a leaked
#   live credential, not a slipped-through block. `cmd_sha256`/`cmd_len` let
#   the audit trail correlate/de-duplicate denials of the SAME command
#   without ever carrying the payload — non-reversible by construction.
#   `path` stays exactly as-is for protect-paths.sh/audit-gate.sh/post-edit-
#   check.sh (bounded file paths / a skill ref, never a full command line).
ALLOWLIST: dict[str, frozenset[str]] = {
    "scan.mcp_call": frozenset({"server", "tool", "audit_state", "duration_ms"}),
    "session.compact": frozenset({"trigger", "tokens"}),
    "scan.secrets": frozenset({"status", "counters", "locations"}),
    "scan.sast": frozenset({"status", "counters", "locations"}),
    "scan.iac": frozenset({"status", "counters", "locations"}),
    "scan.sca": frozenset({"status", "counters", "locations"}),
    "scan.waiver": frozenset({"status", "counters"}),
    "hook.deny": frozenset({"guard", "rule", "path", "cmd_sha256", "cmd_len"}),
    "hook.warn": frozenset({"guard", "rule", "path"}),
    "hook.check_fail": frozenset({"guard", "rule", "path"}),
    "agent.stop": frozenset({"tokens", "est", "duration_ms", "model"}),
    "agent.start": frozenset(),
    "gate.forecast": frozenset({"estimates", "total_est"}),
    "gate.plan_verdict": frozenset({"verdict"}),
    "gate.approval": frozenset({"decision", "source", "plan_hash"}),
    "gate.security": frozenset({"verdict"}),
    "gate.coverage_degraded": frozenset({"reason"}),
    "session.start": frozenset(),
    # NO FREE PROSE, and the argument is the same one that kept `message`
    # out of `session.compact`: the day-file is TRACKED, so anything landing
    # in `data` is committed. The marker only needs to EXIST — the envelope
    # already carries host/sid/ts, which is what the dashboard badge reads.
    # The question the agent asked is in the transcript, where it belongs.
    "session.notify": frozenset(),
    "session.stop": frozenset({"reason"}),
    "task.new": frozenset(),
    "task.state": frozenset({"state"}),
    "task.stage": frozenset({"stage"}),
    "index.build": frozenset({"duration_ms"}),
    "index.stale": frozenset({"reason"}),
    "ledger.add": frozenset({"category"}),
}

# Per-(kind, field) HARD length cap — defense in depth, independent of the call-site fix
# (T-00000018 addendum; independent security review, HIGH, confirmed 3x). Fixing safe-bash.sh so it
# no longer sends the raw command through `path` stops TODAY's leak; it does not stop a FUTURE
# emitter (a new guard, a new host's hook, a future call site) from passing an over-long value
# through the SAME field and reproducing it. The existing 4 KiB whole-`data` cap (_DATA_CAP_BYTES)
# did NOT catch the original leak — that record was 1171 bytes, comfortably under it — because a
# whole-payload budget is not a substitute for a bound on a field whose LEGITIMATE values are
# always small. `path`'s legitimate value is a repo-relative file path or a skill ref
# (protect-paths.sh/audit-gate.sh/post-edit-check.sh) — a few hundred bytes is generous for that.
# Anything longer is truncated with a VISIBLE marker and counted (C13-style: observable via
# get_diagnostics(), never silently dropped, never silently shortened).
_FIELD_LEN_CAPS: dict[str, dict[str, int]] = {
    "hook.deny": {"path": 300},
}
_TRUNCATE_MARKER = "...<truncated>"

# C13 — process-local, in-memory diagnostics. Bumped, never raised: a forgotten/renamed field lands
# as a silent `data: {}` otherwise (the reviewer's exact concern — a `scan.mcp_call` with no
# identity and no verdict landing with the suite green). The counters make the drop observable
# IN-PROCESS via get_diagnostics() (no runtime reader today: tests only), without a second line per
# emit() (which would break the one-line-per-event contract this module exists to provide) nor by
# inventing a `kind` outside the closed vocabulary ("un kind inconnu est rejeté... pas inventé").
# `truncated_fields` does the same for the per-field cap above: not a drop, never silent.
_DIAGNOSTICS: dict[str, int] = {
    "unknown_kind": 0, "dropped_fields": 0, "truncated_fields": 0,
    # T-00000641 : le module de rédaction n'a pas pu être chargé (unavailable) ou
    # a levé pendant la rédaction (failed) — dans les deux cas la ligne est écrite
    # mais `data`, l'enveloppe et `user` sont neutralisés (fail-open, secret sûr).
    "redaction_unavailable": 0, "redaction_failed": 0,
    # merge_day_files(): source files skipped as crash residue (every line already present in the
    # merged file). Security review (lot 2, advisory): a legitimate file coinciding byte-for-byte
    # would be skipped too — unpreventable by construction, so it must at least be observable.
    "merge_residue_files": 0,
    # T-00001133 : une ligne d'un `kind` connu qu'une exception a empêché d'écrire — refusée par
    # `json.dumps` (objet, CLÉ non JSON), I/O en échec… : l'`except` extérieur d'`emit` la compte.
    "lost_events": 0,
}


def get_diagnostics() -> dict[str, int]:
    """Snapshot of the in-memory drop counters (C13). Process-local, reset by each new interpreter,
    like all state of a per-invocation hook; a running total is the caller's to emit."""
    return dict(_DIAGNOSTICS)


_USER_UNSET = object()
_cached_user: object = _USER_UNSET

# `user` lives in the ENVELOPE, so neither ALLOWLIST filtering nor
# _FIELD_LEN_CAPS (both scoped to `data`) ever touch it — and the 4 KiB
# whole-line recovery path only rewrites `data`, so a pathological
# `git config user.name` (config is attacker-writable text, not code) would
# bloat EVERY record of the process and could keep the line over the cap
# even after that rewrite (T-00000032). Legitimate author names are short;
# same visible-marker + counter discipline as the data-field caps.
_USER_LEN_CAP = 100


def _resolve_user() -> str | None:
    """`git config user.name` — decision: multi-user attribution (a pull
    brings someone else's events into the same tracked day-file set), and the
    name is already public via commit authorship. Cached for the life of the
    process so a hook emitting many events in one run does not spawn `git`
    once per event; a missing/failing git is cached as None too. Capped at
    _USER_LEN_CAP (see that constant's comment), truncation observable via
    get_diagnostics()["truncated_fields"]."""
    global _cached_user
    if _cached_user is _USER_UNSET:
        try:
            out = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True, text=True, timeout=2,
            )
            name = out.stdout.strip()
            # T-00000641 (A-R1) : rédiger AVANT la troncature (C5), et JAMAIS
            # `_redaction().rediger(name)` — `_redaction()` rend None si le module
            # manque, l'appel lèverait, et le `except` propre à cette fonction
            # figerait `_cached_user = None` pour la vie du processus (user perdu
            # en silence). En mode dégradé `user` reste brut ICI, neutralisé
            # ensuite par la boucle `_CLES_DEGRADEES` d'`emit`.
            red = _redaction()
            name = red.rediger(name) if red is not None else name
            if len(name) > _USER_LEN_CAP:
                name = name[:_USER_LEN_CAP] + _TRUNCATE_MARKER
                _DIAGNOSTICS["truncated_fields"] += 1
            _cached_user = name or None
        except Exception:
            _cached_user = None
    return _cached_user  # type: ignore[return-value]


def _events_dir() -> Path:
    """`.agents/state/events/`, resolved from THIS FILE's location — hooks
    invoke python from arbitrary working directories, so cwd is not a safe
    anchor. `AGENTS_EVENTS_DIR` is an escape hatch for tests (GATE A's probe
    and its per-writer successor both need several independently-spawned
    processes to target one shared, redirected directory)."""
    override = os.environ.get("AGENTS_EVENTS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "state" / "events"


def _digest_dir() -> Path:
    return _events_dir() / "digest"


# ---------------------------------------------------------------------------
# V1-b (T-00000049) — the SQLite projection's path and the ONE maintenance
# lock, both owned HERE rather than in `event_store.py`, on purpose:
#
#   * the path, because `event_store.py` and this module's operator CLI must
#     agree on it BY CONSTRUCTION. Two literals that "obviously" resolve to
#     the same file are exactly how the merge/compact gate below would
#     silently stop gating (the L-00000057 false-anchor shape).
#   * the lock, because the gate ("is there an events.db?") and the legacy
#     one-time migration that CREATES that events.db must take the SAME lock.
#     Checking DB-absence outside the lock is check-then-act: an operator
#     `--merge-days` racing the daemon's first boot would re-home a spool file
#     the daemon had ingested but not yet deleted (the L-00000035 window),
#     giving it a NEW (src_file, line_index) identity that INSERT OR IGNORE
#     cannot match — two rows for one audit line (plan-critic iteration 7, C2).
#
# Import direction is one-way: `event_store.py` imports this module, never the
# reverse. `emit()`'s fail-open hot path is untouched by any of it.
# ---------------------------------------------------------------------------

_MAINTENANCE_LOCK_NAME = ".maintenance.lock"
# A holder that died is detected by age and reclaimed once (10 min: the same
# bound the inline version of this logic used before it was extracted).
_MAINTENANCE_STALE_SECONDS = 600.0


class MaintenanceLockBusy(Exception):
    """A live rival maintenance run holds `.maintenance.lock`. Raised, never
    printed here — the caller decides what a busy lock means for it."""


def events_db_path() -> Path:
    """`.agents/state/local/events.db` — git-ignored, the DAEMON is its only
    writer. Derived from `_events_dir()` so `AGENTS_EVENTS_DIR` redirects the
    spool and the store together (a test that redirects one and not the other
    would assert against this developer's real database). `AGENTS_EVENTS_DB`
    overrides the whole thing for the store's own tests."""
    override = os.environ.get("AGENTS_EVENTS_DB")
    if override:
        return Path(override)
    return _events_dir().parent / "local" / "events.db"


@contextlib.contextmanager
def maintenance_lock() -> Iterator[Path]:
    """One `O_CREAT|O_EXCL` lock around a whole maintenance pass (same
    primitive as `dashboard.lock`, GATE B item 3). Raises
    `MaintenanceLockBusy` when a LIVE holder has it; a holder older than
    `_MAINTENANCE_STALE_SECONDS` is reclaimed once, then the acquisition is
    retried exactly once more."""
    lock = _events_dir() / _MAINTENANCE_LOCK_NAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    for attempt in (1, 2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                age = 0.0
            if attempt == 1 and age > _MAINTENANCE_STALE_SECONDS:
                try:
                    os.unlink(lock)  # stale: holder died >10min ago
                except OSError:
                    pass
                continue
            raise MaintenanceLockBusy(str(lock))
    if not acquired:  # pragma: no cover - the loop either breaks or raises
        raise MaintenanceLockBusy(str(lock))
    try:
        yield lock
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


_HOST_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize_host(host: Any) -> str:
    """Filename component only — never written back into the envelope. Falls back to "unknown"
    for a missing host rather than leaving a literal `None` in a tracked filename."""
    text = str(host) if host else ""
    safe = _HOST_SANITIZE_RE.sub("_", text)
    return safe or "unknown"


def _day_file(now: datetime, host: Any) -> Path:
    """`YYYY-MM-DD.<host>.<pid>.jsonl` — sole ownership per process (option C; GATE A rationale:
    module docstring). `pid` here is `os.getpid()`, THE PROCESS's own id, used only to keep
    filenames apart — NOT the envelope's `pid` field (`prompt_id`, the canal-B join key). No
    randomness: two processes sharing a pid on the same day cannot be concurrent (the OS will not
    reuse a live pid), so they cannot contend. BOUND: in ONE pid namespace only; same-pid writers
    in containers sharing the events dir CAN contend (`_write_line`'s guard limits the damage)."""
    safe_host = _sanitize_host(host)
    this_process_pid = os.getpid()
    return _events_dir() / f"{now.strftime('%Y-%m-%d')}.{safe_host}.{this_process_pid}.jsonl"


def _build_record(kind: str, now: datetime, fields: dict[str, Any]) -> dict[str, Any]:
    """Split `fields` into the envelope and the per-kind `data` payload, applying the ALLOWLIST
    and bumping C13 diagnostics for anything dropped OR truncated (per-field length cap,
    _FIELD_LEN_CAPS — defense in depth, independent of any call site: see that dict's comment)."""
    allowed = ALLOWLIST.get(kind, frozenset())
    caps = _FIELD_LEN_CAPS.get(kind, {})
    data: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _ENVELOPE_KEYS:
            continue
        if key not in allowed:
            _DIAGNOSTICS["dropped_fields"] += 1
            continue
        cap = caps.get(key)
        if cap is not None:
            # Coerce to text BEFORE the length check, so a non-string under a capped name (an int,
            # a dict) cannot skip the cap (independent review, T-00000018 addendum) — by
            # `json.dumps`, never `str()`, whose repr cut a token past the redaction, nested or
            # not (T-00001132). Non-JSON at any depth stays raw: `emit` refuses the line.
            try:
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                text = ""  # left raw: refused by `emit`'s `json.dumps` (overwritten if degraded)
            if len(text) > cap:
                value = text[:cap] + _TRUNCATE_MARKER
                _DIAGNOSTICS["truncated_fields"] += 1
        data[key] = value

    return {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "host": fields.get("host"),
        "sid": fields.get("sid"),
        # `pid` = prompt_id, the canal-B join key — NEVER os.getpid() (that one names the
        # FILE only, `_day_file`); mixing them silently breaks the join. Same short name,
        # two concepts: a review round caught the conflation, hence a comment at both sites.
        "pid": fields.get("pid"),
        "aid": fields.get("aid"),
        "task": fields.get("task"),
        "agent": fields.get("agent"),
        "effort": fields.get("effort"),
        "user": _resolve_user(),
        "data": data,
    }


# In-process guard ONLY: threads of one process share a pid, so a file (_day_file), so race its
# seek+write; one process, one lock — no cross-process lock (option B, rejected: module docstring).
_write_lock = threading.Lock()

# S-00001597 (décision pilote) : magasin STRICTEMENT append-only — aucune purge, aucune réécriture
# — et « la borne doit etre ecrite EN TETE du .jsonl, pas seulement dans la documentation ». Elle
# chevauche le PREMIER enregistrement de chaque day-file, en clé d'enveloppe `borne` ; elle ne
# porte AUCUNE valeur d'appelant, donc échappe au cap `_DATA_CAP_BYTES` (mesuré avant son ajout).
_BORNE_APPEND_ONLY = "append-only: aucune purge ni reecriture de ce magasin (S-00001597)"


def _write_line(record: dict[str, Any], now: datetime, host: Any) -> None:
    """One O_APPEND line, written to COMPLETION (loop below), to THIS PROCESS's own day-file.
    S-00001597's append-only bound is decided DANS la section critique — `created` (day-file absent
    or EMPTY, A-T1) under `_write_lock` adds a `borne` envelope key to the RECORD (unserialized) —
    then serialized and written HERE. ONE lock for primeur + write closes the check-then-act race
    of two threads (shared pid => shared file, T15). os.write directly (not a buffered text-mode
    `open()`): buffering cannot split a line. os.O_BINARY (Windows-only; absent on POSIX, hence
    getattr/0): the CRT cannot rewrite "\\n" as "\\r\\n" — a bug our own CRLF test caught in shard
    1, not inspection. ANY exception mid-line (OSError, KeyboardInterrupt) cuts the file back to
    its size at open, else the next line welds on (both unreadable, one uncounted) — only if bytes
    REMAIN and size == that + THIS call's COUNTED bytes (count late OR complete on an interrupt: no
    cut): never a written line (S-00001597) nor another writer's (`_day_file`). `read_new_records`
    (dashboard_readers_base) et `_read_spool_lines` (event_store) lisent au dernier "\\n" ;
    `_read_jsonl_records` (`compact`, jours passés seuls) JETTE la ligne soudée ENTIÈRE."""
    target = _day_file(now, host)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    with _write_lock:
        # A-T1 (S-00001597) : la borne porte sur le CONTENU — un day-file VIDE (os.open réussi,
        # os.write échoué au tour précédent) la reçoit ENCORE : TAILLE testée, jamais l'existence.
        try:
            created = target.stat().st_size == 0
        except FileNotFoundError:
            created = True
        if created:
            record = {**record, "borne": _BORNE_APPEND_ONLY}
        payload = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
        fd = os.open(str(target), flags, 0o644)
        try:
            debut, reste = os.fstat(fd).st_size, memoryview(payload)  # fichier du pid, verrou
            try:
                while reste:  # T-00001133 : une écriture courte reprend au RESTE, jamais au début
                    n = os.write(fd, reste)
                    if n == 0:  # jamais de boucle sans fin : levée, donc comptée par `emit`
                        raise OSError(errno.EIO, "os.write: 0 octet écrit, ligne incomplète")
                    reste = reste[n:]
            except BaseException:  # binôme ter : ôter NOS octets SEULS (docstring), puis relever
                with contextlib.suppress(OSError):
                    if reste and os.fstat(fd).st_size == debut + len(payload) - len(reste):
                        os.ftruncate(fd, debut)
                raise
        finally:
            os.close(fd)


_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
_MARQUEUR_SURROGATE = "[SURROGATE NEUTRALISE]"


def _sans_surrogates(v: Any, cle: bool = False) -> Any:
    """Notes (3) et (4) d'`emit`. Copie de `v`, types gardés (une clé tuple reste hashable) ;
    deux clés marquées d'un même dict fusionnent : une valeur perdue, aucun jeton. Une CLÉ garde
    son type : `str`, `rediger_arbre` la rédige (T-00001131) ; `bytes`, jamais décodée, refusée
    par `json.dumps`, ligne comptée (`lost_events`, T-00001133)."""
    if isinstance(v, str):
        return _MARQUEUR_SURROGATE if _SURROGATE_RE.search(v) else v
    if isinstance(v, dict):
        return {_sans_surrogates(k, True): _sans_surrogates(x) for k, x in v.items()}
    if isinstance(v, tuple):
        return tuple(_sans_surrogates(x, cle) for x in v)
    if cle or v is None or isinstance(v, (int, float)):
        return v
    if isinstance(v, (list, set, frozenset)):
        return [_sans_surrogates(x) for x in v]
    is_bytes = isinstance(v, (bytes, bytearray))
    return _sans_surrogates(v.decode("utf-8", "surrogateescape")) if is_bytes else v


def emit(kind: str, **fields: Any) -> None:
    """Append one canal-A event to this process's own day-file (option C, module docstring):
    `.agents/state/events/YYYY-MM-DD.<host>.<pid>.jsonl`. Fail-open, absolutely (idem): returns
    `None` always — not a success signal; there is none, by design. A line an exception kept
    unwritten (`json.dumps` refusal, I/O) bumps `lost_events` — in-process, unread at runtime.

    `kind` must be in the closed KNOWN_KINDS vocabulary; an unknown kind is dropped (nothing
    written) and bumps `get_diagnostics()["unknown_kind"]`. Every other keyword is an envelope
    field (host/sid/pid/aid/task/agent/effort — `user` is derived, never passed) or a `data`
    candidate filtered through ALLOWLIST[kind]; anything else is dropped (`dropped_fields`). A
    line over `_DATA_CAP_BYTES` is rewritten with `data = {"truncated": True}`, never dropped.

    Contract notes, T-00000641: (1) the cap is measured BEFORE the optional `borne` envelope key
    (added under the lock in `_write_line`), so the FIRST line of a day-file may exceed it by that
    phrase's length, and the record is serialized TWICE per call; neither has a security
    consequence — `borne` carries no caller value. (2) Degraded mode (`redaction_unavailable`/
    `redaction_failed`): `data`, every `_ENVELOPE_KEYS` field AND `user` carry `_MARQUEUR_DEGRADE`;
    the line exists, its correlation is lost, no caller byte survives — in the content NOR in the
    day-file NAME. T-00000996: (3) a `str` leaf or dict key holding a lone surrogate becomes
    `_MARQUEUR_SURROGATE` WHOLE, BEFORE the redaction — the belt `errors="replace"` alone stitched
    a cut token back with `?`, past `MOTIFS` (35/36 characters in clear). `user` holds none (strict
    decode). T-00001132: (4) a `bytes` leaf is decoded `surrogateescape` and a `set` listed BEFORE
    (3), so neutralised THEN redacted; any other non-JSON object is REFUSED by `json.dumps`, never
    made text — a repr re-escapes a lone surrogate into ASCII, past (3): measured, a dataclass
    wrote a cut token 36/36 in clear. A KEY keeps its type (`str` redacted, `bytes` refused).
    """
    try:
        if kind not in KNOWN_KINDS:
            _DIAGNOSTICS["unknown_kind"] += 1
            return None

        now = datetime.now(timezone.utc)
        # T-00000641 (étape 5) : rédiger `fields` EN ENTIER (enveloppe + charge) AVANT les caps
        # `_FIELD_LEN_CAPS` (C5), sinon un préfixe de secret tronqué survivrait. Ce `try` ne voit
        # qu'une RÉCURSION (cycle → `redaction_failed`). Note (4) : le reste non JSON (objet, CLÉ
        # `bytes` ou tuple) meurt dans `json.dumps` ; l'`except` extérieur compte (`lost_events`).
        degrade: str | None = None
        red = _redaction()  # ne lève jamais : try/except interne → None
        if red is None:
            degrade = "redaction_unavailable"
        else:
            try:
                fields = red.rediger_arbre(_sans_surrogates(fields))
            except Exception:
                degrade = "redaction_failed"  # fields RESTENT bruts → neutralisés

        record = _build_record(kind, now, fields)

        if degrade is not None:
            # Bloquant B : neutraliser APRÈS `_build_record`, jamais via `fields` (`"data"` n'est
            # ni clé d'enveloppe ni nom d'ALLOWLIST, donc jeté puis `data` reconstruit BRUT). La
            # boucle couvre `data` + `_ENVELOPE_KEYS` + `user` : aucun octet d'appelant ne subsiste
            # (reste `ts`, `kind`, marqueurs). On écrase des VALEURS, jamais des CLÉS (SYM-1860).
            record["data"] = {degrade: True}
            for cle in _CLES_DEGRADEES:
                if cle in record:
                    record[cle] = _MARQUEUR_DEGRADE
            _DIAGNOSTICS[degrade] += 1

        line = json.dumps(record, ensure_ascii=False)
        if len(line.encode("utf-8", errors="replace")) > _DATA_CAP_BYTES:
            record["data"] = {"truncated": True}

        # `host` lu APRÈS la neutralisation (rédigé, ou marqueur), jamais l'octet brut : la
        # capture `fields.get("host")` avant `_build_record` faisait fuir le secret dans le
        # NOM du day-file suivi (`_sanitize_host` ne garde que la syntaxe FS — T17).
        host = record["host"]
        _write_line(record, now, host)
        return None
    except Exception:
        _DIAGNOSTICS["lost_events"] += 1  # T-00001133 : compté, mais aucun lecteur d'exécution
        return None


# ---------------------------------------------------------------------------
# --compact — fold day-files older than retention into monthly digests (design doc §D, decision
# L-00000032: "30 jours puis digest"). Resolved PLAN_DRIFT: docs/tasks/T-00000018.md's shard-1
# section lists this bullet; it is authoritative, and option C (one file per writer) converges with
# it — per-writer files make folding MORE necessary, not less, since a day now produces N files
# instead of one.
# ---------------------------------------------------------------------------

_DAY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.")


def _date_from_day_file(path: Path) -> date | None:
    match = _DAY_FILE_RE.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    """Best-effort line read for compaction: a malformed line is skipped, not
    fatal to the whole file — compact() is a maintenance pass over data other
    processes already wrote, some of it possibly from a partial/interrupted
    write this module's fail-open design tolerates upstream."""
    records: list[dict[str, Any]] = []
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return records
    for raw in text.split("\n"):
        if not raw:
            continue
        try:
            records.append(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            continue
    return records


def _empty_digest(month: str) -> dict[str, Any]:
    return {
        "month": month,
        "generated_at": None,
        "total_events": 0,
        "by_kind": {},
        "by_agent": {},
        "by_task": {},
        "days_folded": [],
    }


def _merge_into_digest(digest: dict[str, Any], records: list[dict[str, Any]], day: str) -> None:
    if day not in digest["days_folded"]:
        digest["days_folded"].append(day)
    for rec in records:
        digest["total_events"] += 1
        kind = rec.get("kind")
        agent = rec.get("agent")
        task = rec.get("task")
        if kind:
            digest["by_kind"][kind] = digest["by_kind"].get(kind, 0) + 1
        if agent:
            digest["by_agent"][agent] = digest["by_agent"].get(agent, 0) + 1
        if task:
            digest["by_task"][task] = digest["by_task"].get(task, 0) + 1


# L-00000054: os.replace fails with PermissionError under a concurrent
# reader on Windows (69-81% measured) — and both digests and merged
# day-files ARE frequently read since the dashboard shipped
# (`/api/events` re-reads digest aggregates on every poll). Same proven
# bound as build_index._Publisher / dashboard_daemon.write_lock.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01


def _replace_with_retry(src: str | Path, target: str | Path) -> None:
    last: PermissionError | None = None
    for _ in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(_REPLACE_DELAY_SECONDS)
    assert last is not None
    raise last


def _publish_digest(target: Path, digest: dict[str, Any]) -> None:
    """Atomic publish — the same recipe as build_index.py's _Publisher.write:
    mkstemp IN THE TARGET DIRECTORY (same filesystem, so os.replace is a
    rename) -> write -> fsync -> chmod -> os.replace, fd CLOSED before
    replace (a hard Windows requirement — an open handle makes os.replace
    fail there). Unlike build_index.py, `newline` is forced to "\\n" here
    (L-003) rather than left at the platform default: a digest is part of
    the same observability trail as the day-files it folds, even though it
    is a plain `.json` object rather than a `merge=union` `.jsonl` stream."""
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(digest, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o644)
        except OSError:
            pass  # exotic filesystem — not worth failing a publish over
        _replace_with_retry(tmp, str(target))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def compact(retention_days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    """Fold day-files older than `retention_days` into per-month digests at
    `state/events/digest/YYYY-MM.json`. Aggregates COUNTS by kind/agent/task
    only — never raw event bodies; a digest is a summary, not a second
    archive.

    Idempotent and safe to re-run: a day already present in a digest's
    `days_folded` is not double-counted on a later run, and a source
    day-file is only unlinked AFTER its month's digest has been durably
    published via `_publish_digest` (os.replace) — a crash mid-run leaves
    either the untouched day-file (re-processed next run) or the
    folded-and-removed pair, never a folded-but-still-present duplicate.

    NOT on the emit() fail-open hot path — this is an explicit,
    operator-invoked maintenance action (`--compact`), so a malformed source
    file is skipped and reported (`skipped`) rather than the whole run being
    swallowed silently.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).date()

    by_month: dict[str, list[tuple[str, Path]]] = {}
    skipped: list[str] = []
    for path in sorted(_events_dir().glob("*.jsonl")):
        day = _date_from_day_file(path)
        if day is None:
            skipped.append(path.name)
            continue
        if day >= cutoff:
            continue  # still within retention — left alone
        month = day.strftime("%Y-%m")
        by_month.setdefault(month, []).append((day.isoformat(), path))

    folded_files = 0
    months_updated: list[str] = []
    for month, entries in by_month.items():
        digest_path = _digest_dir() / f"{month}.json"
        try:
            existing = json.loads(digest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = _empty_digest(month)

        to_remove: list[Path] = []
        # Group per day BEFORE the days_folded check: option C means a day is
        # normally N files (one per writer), and the previous per-file loop
        # marked the day folded on the FIRST file, then unlinked every
        # sibling uncounted — silent record loss in the digest, found while
        # reassessing granularity (T-00000038).
        by_day: dict[str, list[Path]] = {}
        for day_str, path in entries:
            by_day.setdefault(day_str, []).append(path)
        for day_str, paths in by_day.items():
            if day_str not in existing["days_folded"]:
                records: list[dict[str, Any]] = []
                for path in paths:
                    records.extend(_read_jsonl_records(path))
                _merge_into_digest(existing, records, day_str)
            to_remove.extend(paths)

        existing["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        _publish_digest(digest_path, existing)
        for path in to_remove:
            try:
                path.unlink()
            except OSError:
                pass
        folded_files += len(to_remove)
        months_updated.append(month)

    return {
        "folded_files": folded_files,
        "months_updated": sorted(months_updated),
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# merge_day_files — consolidate PAST days' per-writer files into one file per
# day (T-00000038). Option C (one file per writer, L-00000041) is correct for
# WRITES — cross-process O_APPEND is not atomic on Windows — but hooks are
# per-invocation processes, so a real day produced 320 files for 323 records.
# The write-side invariant is not renegotiated here; the fix is reader-side
# economics: a filename dated D is only ever appended by a process whose
# `now` is still day D (see _day_file — the date comes from the write's own
# clock), so once D has passed, every `D.*.jsonl` is immutable by
# construction and can be folded into a single `D.merged.jsonl` (2 name
# segments — a writer file always has 3, so no host named "merged" can
# collide). Runs inside the same operator maintenance surface as compact()
# (`--compact` does merge-then-digest; `--merge-days` runs merge alone).
#
# Known, bounded reader effect: a live dashboard cursor that still references
# the pre-merge filenames sees them pruned (surfaced via `pruned_files`,
# non-negotiable #3) and the merged file as a new file read from offset 0 —
# that day's records are re-served once to that client. Visible, bounded to
# consolidated days, and only affects cursors that span a maintenance run.
#
# T-00000049 — DEPRECATION SURFACE, enumerated once so nobody has to re-derive
# it. Once `events_db_path()` exists this function is reachable from exactly
# ONE caller: `event_store._migrate_legacy_spool()`, one time in the life of a
# project, under `maintenance_lock()`, on a still-absent database. Everything
# else that referenced it now short-circuits:
#   * `main()` (`--merge-days` / `--compact`)  -> no-op, gated above.
#   * `dashboard.build_events_response`        -> reads the store, and reports
#     `pruned_files: []` with `cursor_unit: "db_rowid"` in that mode.
#   * `test_events.py`'s merge/compact cases   -> still valid: they run with no
#     events.db in the redirected tree, i.e. they cover the legacy path that
#     the migration is the last user of.
#   * `.agents/README.md`'s maintenance line   -> updated with the no-op rule.
# ---------------------------------------------------------------------------

_MERGED_SUFFIX = ".merged.jsonl"


def _read_jsonl_lines(path: Path) -> list[str]:
    """Raw non-empty lines, undecoded semantics: unlike the digest reader,
    the merger must never DROP a malformed line (a merge is a relocation,
    not a summary) — it carries such lines through verbatim."""
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [ln for ln in text.split("\n") if ln]


def _line_ts(line: str) -> str:
    """Sort key: the record's `ts` (ISO-8601 Z, lexicographically ordered).
    A malformed line sorts last ("~" > "9" in ASCII) but is preserved."""
    try:
        value = json.loads(line).get("ts")
        return value if isinstance(value, str) else "~"
    except (json.JSONDecodeError, ValueError):
        return "~"


def merge_day_files(now: datetime | None = None) -> dict[str, Any]:
    """Fold every PAST day's per-writer files into `YYYY-MM-DD.merged.jsonl`.

    Today's files are never touched — their writers may still be live.
    Records are stably sorted by `ts` (equal stamps keep arrival order).
    Idempotent and crash-safe: the merged file is published atomically
    (mkstemp -> fsync -> close -> replace-with-retry, L-00000054) BEFORE the
    sources are unlinked; a crash in between leaves sources whose every line
    is already present in the merged file, and a re-run detects exactly that
    (whole-file line containment) and just removes them instead of folding
    duplicates. The theoretical false positive — a source file ALL of whose
    lines coincidentally exist verbatim in the merged file — is
    indistinguishable from crash residue by construction, and dropping it
    loses nothing a reader could have distinguished either.

    T-00000641 (A-T5): the merged `YYYY-MM-DD.merged.jsonl` carries NO `borne` at
    its head. The append-only bound (S-00001597) rides the FIRST line of each
    per-writer day-file; merging folds those lines by `ts` like any other record,
    so the merged file guarantees the bound on NONE of its lines in particular —
    a reader must not expect it on the merged file's first record.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()

    groups: dict[str, list[Path]] = {}
    for path in sorted(_events_dir().glob("*.jsonl")):
        if path.name.endswith(_MERGED_SUFFIX):
            continue
        day = _date_from_day_file(path)
        if day is None or day >= today:
            continue
        groups.setdefault(day.isoformat(), []).append(path)

    days_merged: list[str] = []
    files_folded = 0
    for day_str, paths in sorted(groups.items()):
        target = _events_dir() / f"{day_str}{_MERGED_SUFFIX}"
        existing_lines = _read_jsonl_lines(target) if target.exists() else []
        existing_set = set(existing_lines)

        fresh: list[str] = []
        for path in paths:
            lines = _read_jsonl_lines(path)
            if lines and existing_set and all(ln in existing_set for ln in lines):
                _DIAGNOSTICS["merge_residue_files"] += 1
                continue  # crash residue: already folded, just remove below
            fresh.extend(lines)

        if fresh:
            merged = existing_lines + fresh
            merged.sort(key=_line_ts)  # sort() is stable: ties keep order
            text = "\n".join(merged) + "\n"
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._tmp_", suffix=".part")
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
                    fh.flush()
                    os.fsync(fh.fileno())
                try:
                    os.chmod(tmp, 0o644)
                except OSError:
                    pass
                _replace_with_retry(tmp, str(target))
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

        for path in paths:
            try:
                path.unlink()
            except OSError:
                pass
        files_folded += len(paths)
        days_merged.append(day_str)

    return {"days_merged": days_merged, "files_folded": files_folded}


def force_utf8_stdio() -> None:
    """Windows consoles default to cp1252. `--compact` is the only code path
    in this module that prints — emit() never does — so this is invoked from
    main() only."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Canal-A event emission — maintenance CLI (emit() itself has no CLI)."
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="Merge past days' writer files (see --merge-days), then fold "
        "day-files older than --retention-days into monthly digests. "
        "NO-OP once .agents/state/local/events.db exists (see --merge-days).",
    )
    parser.add_argument(
        "--merge-days", action="store_true",
        help="Only consolidate past days' per-writer files into one "
        "YYYY-MM-DD.merged.jsonl per day (T-00000038); today is never touched. "
        "NO-OP once .agents/state/local/events.db exists: the daemon then owns "
        "retention and re-homing a spool file would duplicate audit records.",
    )
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args(argv)

    if not (args.compact or args.merge_days):
        parser.print_help()
        return 1

    force_utf8_stdio()
    # Security review (lot 2, advisory): two concurrent maintenance runs could
    # each glob the same sources, publish rival merged files and unlink —
    # duplicating audit records. Hence the lock; it is now also what makes the
    # events.db gate below atomic (see `maintenance_lock`'s own comment).
    try:
        with maintenance_lock():
            # T-00000049 — RE-HOMING IS RETIRED ONCE THE STORE EXISTS.
            # `merge_day_files()` survives because the store's one-time legacy
            # migration calls it (under this same lock, before the first
            # ingest, on a still-absent database). What must NOT survive is the
            # OPERATOR surface: a spool file the daemon has ingested but not
            # yet deleted (Windows handle window, L-00000035) would be folded
            # into `D.merged.jsonl` and re-read under a NEW (src_file,
            # line_index) identity, which INSERT OR IGNORE cannot match — one
            # audit line, two rows, permanently over-counted (plan-critic
            # iteration 6, C1). Evaluated INSIDE the lock so it cannot be
            # check-then-act against the migration that creates the file
            # (iteration 7, C2).
            db = events_db_path()
            if db.exists():
                print(json.dumps({
                    "skipped": "events.db present — the daemon owns retention",
                    "db": str(db),
                    "note": (
                        "merge/compact are no-ops once the SQLite store exists: "
                        "re-homing a spool file would give an already-ingested "
                        "line a new identity and double-count it. Retention (30d) "
                        "and digests are folded by the daemon's ingest tick."
                    ),
                }, ensure_ascii=False))
                return 0
            report: dict[str, Any] = {}
            # One maintenance surface: --compact implies the merge pass first,
            # so the digest fold downstream sees one file per day instead of N.
            report["merge"] = merge_day_files()
            if args.compact:
                report["compact"] = compact(retention_days=args.retention_days)
    except MaintenanceLockBusy:
        print(json.dumps({"skipped": "maintenance already running"}))
        return 0
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
