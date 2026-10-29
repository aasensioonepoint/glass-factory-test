#!/usr/bin/env python3
"""Machine-wide registry of running dashboard daemons (T-00000083, M1).

ONE file per USER, outside any project tree: `~/.agentkit/registry.json`
(overridable by `AGENTKIT_REGISTRY`, which the tests use). It is the ONLY
mechanism by which one project's dashboard learns that another project's
dashboard exists — there is NO disk scan and NO discovery (rejected by design,
spec §B.3): a daemon PUBLISHES itself here at start-up and REMOVES itself at
stop.

WHY A SEPARATE MODULE, with zero sibling imports. `dashboard.py` (HTTP routes)
and `dashboard_daemon.py` (lifecycle) both need it, and the daemon already
loads the dashboard — a registry living in either of them would either import a
cycle or duplicate the primitives. It holds no in-memory state, so the two
module instances the `_load_sibling` idiom produces cannot disagree.

TWO PRIMITIVES MOVED HERE, not copied (`dashboard_daemon.py` now delegates,
keeping its public names): `pid_alive` and `replace_with_retry`. Both are
measured recipes, not style choices:

  * `pid_alive` — on Windows, `os.kill(pid, 0)` is not the probe; OpenProcess +
    GetExitCodeProcess is (GATE B item 4).
  * `replace_with_retry` — a bare `os.replace` under a concurrent reader on
    Windows fails 69-81 % of the time (L-00000054); 30 x 10 ms always converged
    and never tore.

LAST-WRITER-WINS IS REAL HERE, and it takes BOTH halves to close it. Unlike the
per-project lock, this file has writers in DIFFERENT PROCESS TREES (two
projects, two daemons). `os.replace` makes each write atomic, so the file is
never torn — but a read-modify-write pair from two daemons drops one of the two
entries. So:

  1. the read-modify-write runs inside a cross-process lock
     (`registry.json.lock`, `os.open(O_CREAT | O_EXCL)` — GATE B item 3), which
     PREVENTS clobbering; and
  2. the writer re-reads afterwards and retries a bounded number of times,
     which DETECTS having been clobbered anyway — by a writer that gave up
     waiting for the lock (bounded patience: a registry write may never block
     a daemon from starting) or by one that broke a stale lock.

Verification alone would not do: two daemons that both write and then both
re-read a file containing themselves are both satisfied while one has been
erased. Exclusion alone would not either, since the lock is deliberately
best-effort.

THE GC IS TRI-STATE, and that is the whole point (plan-critic, blocking
amendment). A registry that garbage-collects on "the probe did not answer"
deletes a HEALTHY peer whose machine was merely busy — and the peer never comes
back, because nothing re-registers a live daemon. So:

  * `alive`         — pid alive AND the peer answered its own summary.
  * `dead`          — pid gone, OR a DEFINITIVE probe failure: connection
                      refused (nothing listens on that port any more), a body
                      that is not our `kind`, a 404 (route absent), or a
                      `project_id` that does not match the entry (the port was
                      recycled by someone else).
  * `indeterminate` — a socket timeout, a reset, anything transient. The entry
                      SURVIVES the GC and is merely reported `alive: false`.

Only `dead` entries are removed. RESIDUAL, accepted and named: an entry that is
perpetually `indeterminate` — a long-lived recycled pid whose port silently
DROPS packets rather than refusing them — stays listed as `alive: false`
forever. There is no heartbeat / re-assertion mechanism to age it out; adding
one would mean a background writer per daemon, which this design does not want.

THE PROBE IS DELIBERATELY UNAUTHENTICATED. A tokenised inter-project ping would
require each daemon's Bearer token to be readable from this shared file, i.e. a
machine-wide file granting full read access to every project's ~166 KB snapshot
— forbidden (L-00000112). The token stays in the per-project lock, and the
cross-project probe answers ONLY `/api/peer/summary`, a route whose payload is
sized to be public-by-design. What is preserved from the liveness recipe is its
STRUCTURE: pid AND ping, never one without the other.
"""
from __future__ import annotations

import contextlib
import ctypes
import json
import os
import random
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# QUAND BUMPER, ÉCRIT PLUTÔT QUE SOUS-ENTENDU (2026-09-12). La règle décide le
# comportement de TOUT ce module, et elle était un demi-commentaire.
#
#   On bumpe SI ET SEULEMENT SI un lecteur de la génération précédente lirait
#   FAUX — sémantique d'un champ changée, clé retirée, structure réarrangée.
#   Une clé ADDITIVE ne bumpe PAS, et elle DOIT survivre à un aller-retour par
#   un kit plus ancien (c'est ce que `{**data, …}` et `{**current, …}` tiennent).
#
# Corollaire, et c'est lui qui justifie le refus de LIRE une version supérieure :
# si le numéro a bougé, c'est par définition que nos yeux lisent faux. Servir ces
# entrées « quand même » serait interpréter une sémantique inconnue.
# (Pas de bump du peer API : c'est `PEER_API_VERSION`, un autre contrat.)
REGISTRY_VERSION = 1

_REGISTRY_ENV = "AGENTKIT_REGISTRY"
_REGISTRY_DIRNAME = ".agentkit"
_REGISTRY_FILENAME = "registry.json"

# L-00000054 — the measured bound, same as every other publisher in this kit.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01

# Bounded re-read after a write (module docstring: two daemons in two process
# trees). 8 attempts with a growing, JITTERED delay: identical writers retrying
# in lockstep clobber each other in lockstep too — measured by the poisoned-lock
# probe of T-00000089, where 6 synchronized unlocked writers converged on 2
# surviving entries. The jitter is what de-synchronizes them.
_VERIFY_ATTEMPTS = 8
_VERIFY_DELAY_SECONDS = 0.02
_VERIFY_JITTER_SECONDS = 0.03

# Cross-process mutual exclusion around the read-modify-write, via
# `os.open(O_CREAT | O_EXCL)` — the same primitive GATE B item 3 proved gives
# exactly one winner across concurrent processes on this platform. Bounded on
# BOTH sides: a waiter gives up after `_LOCK_WAIT_SECONDS` and proceeds
# ANYWAY (a registry write may never block a daemon from starting — the verify
# retry above is what then catches a clobber), and a lock file older than
# `_LOCK_STALE_SECONDS` is broken (a killed daemon must not wedge the registry
# for every project on the machine forever).
_LOCK_WAIT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.01
_LOCK_STALE_SECONDS = 30.0

# Cross-project probe. Short on purpose: `/api/peers` walks the registry
# SEQUENTIALLY, so this bounds the whole route at n x 0.5 s worst case, and a
# timeout here costs an `alive: false`, never a deletion.
#
# MEASURED, and it matters: on this Windows host a connection to a closed
# loopback port takes ~2.0 s to come back as WinError 10061 (it is retried
# before it is refused), while on Linux it refuses immediately. So under the
# default timeout a refused port reads `indeterminate` on Windows, not `dead`.
# That is the SAFE direction — the entry is kept, never a live peer deleted —
# and the GC's primary signal is the pid anyway: a daemon that stops removes
# its own entry, and one that is killed loses its pid. Only the recycled-pid
# case leans on the refusal, and it degrades to "listed, alive: false".
PROBE_TIMEOUT_SECONDS = 0.5

PEER_SUMMARY_PATH = "/api/peer/summary"
PEER_SUMMARY_KIND = "agentkit.peer_summary"

# The tri-state vocabulary, spelled once.
ALIVE = "alive"
DEAD = "dead"
INDETERMINATE = "indeterminate"

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259

# Bound on the probe body we will even parse: a peer summary is ~400 bytes, and
# an impostor on a recycled port must not be able to make this read unbounded.
_PROBE_READ_LIMIT_BYTES = 64 * 1024

_ENTRY_FIELDS = ("project_id", "project_root", "name", "pid", "port", "started")


# ---------------------------------------------------------------------------
# Moved from dashboard_daemon.py — single source, delegated back by name.
# ---------------------------------------------------------------------------

def replace_with_retry(
    src: str | Path,
    target: str | Path,
    attempts: int = _REPLACE_ATTEMPTS,
    delay: float = _REPLACE_DELAY_SECONDS,
) -> None:
    """`os.replace` with a bounded retry on PermissionError. Re-raises the
    last PermissionError once the bound is exhausted — a file that cannot be
    published is a loud failure, never a silent partial."""
    last: PermissionError | None = None
    for _ in range(attempts):
        try:
            os.replace(src, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(delay)
    assert last is not None
    raise last


def pid_alive(pid: int) -> bool:
    """True iff a process with this pid exists RIGHT NOW. Says nothing about
    WHOSE process it is — a recycled pid is alive without being ours, which is
    exactly why every caller pairs this with a ping (GATE B item 4)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# The file.
# ---------------------------------------------------------------------------

def registry_path() -> Path:
    """`~/.agentkit/registry.json`, or `AGENTKIT_REGISTRY` when set.

    Resolved IN THE BODY, never as a default argument: the tests set the env
    var after this module is imported (conventions, "a default argument is
    evaluated at IMPORT")."""
    override = os.environ.get(_REGISTRY_ENV)
    if override:
        return Path(override)
    return Path.home() / _REGISTRY_DIRNAME / _REGISTRY_FILENAME


def empty_registry() -> dict[str, Any]:
    return {"version": REGISTRY_VERSION, "projects": {}}


def read_registry_state() -> tuple[dict[str, Any], str]:
    """`(registry, state)` — state is `ok` | `empty` | `unreadable` | `schema_ahead`.

    NEVER raises: a registry that cannot be read must degrade the peers list,
    never take a route down. `unreadable` covers both "the bytes are not JSON"
    and "the JSON is not our shape" — from a consumer's point of view those are
    the same fact (this file says nothing usable), and both are distinct from
    `empty` (this file says, credibly, that no daemon is registered).

    `schema_ahead` (2026-09-12) est le QUATRIÈME état, et il dit autre chose :
    ce fichier a été écrit par un kit PLUS RÉCENT. Il est distinct
    d'`unreadable` parce qu'il n'autorise pas la même suite — un `unreadable`
    est CONTRACTUELLEMENT réécrit par le prochain `register()` (« a corrupt file
    is not a dead end »), un `schema_ahead` ne l'est **jamais**, sous peine de
    rétrograder la version et de perdre des champs. Les deux écrivains
    (`register`, `unregister`) refusent donc d'écrire dans cet état et rendent
    False — que `run_daemon` IMPRIME en `REGISTRY DEGRADED` avec son remède.

    RÉSIDU NOMMÉ, parce qu'une capacité perdue se nomme plutôt qu'elle ne se
    tait : `schema_ahead` rend un registre VIDE, donc il coûte aussi les
    LECTURES, qui ne portent pourtant aucun risque d'écriture. `/api/peers`
    n'affiche plus aucun pair, et `_peer_spool_for` (`otel_receiver.py`) rend
    None — mis en cache un TTL — donc toute enveloppe OTLP étrangère part en
    `orphans/` au lieu du spool de son projet. Rien n'est perdu ; le routage
    cross-projet s'arrête le temps de l'écart. CE PRIX EST DÉLIBÉRÉ : un bump de
    version signifie par définition qu'un lecteur de notre génération lirait
    FAUX, donc servir ces entrées serait interpréter une sémantique qu'on ne
    connaît pas. Le jour où l'on voudra lire sans écrire, il faudra un drapeau
    `no_write` SÉPARÉ — un état qui mélange « je sais lire » et « j'ai le droit
    d'écrire » ne peut pas rendre les deux réponses."""
    path = registry_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_registry(), "empty"
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError (non-UTF-8 bytes).
        return empty_registry(), "unreadable"
    try:
        data = json.loads(raw)
    except ValueError:
        return empty_registry(), "unreadable"
    if not isinstance(data, dict):
        return empty_registry(), "unreadable"
    # LA VERSION SE LIT AVANT LA FORME, et l'ordre est le correctif lui-même.
    # `REGISTRY_VERSION` est bumpée « only for a breaking change of the FILE
    # format » : une VRAIE v2 n'a donc plus `projects`. Tester la forme d'abord
    # la classait `unreadable` — et `unreadable` est CONTRACTUELLEMENT réécrit
    # par le prochain `register()` (« a corrupt file is not a dead end »). La
    # première rédaction de ce garde ne protégeait donc que la v2 ayant GARDÉ la
    # forme v1, c'est-à-dire le seul cas où le bump n'était pas nécessaire.
    # Mesuré sur cette première rédaction : `register()` rendait True et la v2
    # était écrasée en entier.
    vu = data.get("version", REGISTRY_VERSION)
    if not isinstance(vu, int) or isinstance(vu, bool):
        # La version n'est pas un entier : la forme n'est pas la nôtre, et c'est
        # exactement ce que `unreadable` dit — « ce fichier ne dit rien
        # d'utilisable ». Ne PAS tenter de l'interpréter.
        return empty_registry(), "unreadable"
    if vu > REGISTRY_VERSION:
        # UN KIT PLUS RÉCENT A ÉCRIT CE FICHIER. Ni lu, ni réécrit — voir le
        # RÉSIDU NOMMÉ dans la docstring : ce refus coûte aussi les LECTURES,
        # et c'est un prix, pas un détail.
        return empty_registry(), "schema_ahead"
    if vu < 1:
        # Le SENS INVERSE, qui rétrogradait lui aussi en silence : une v0 ou
        # négative n'est pas notre format et nous ne savons pas la migrer, or
        # `register()` restampait `REGISTRY_VERSION` sans rien migrer. Même
        # politique qu'`event_store.py` (« an unversioned store cannot be
        # migrated safely »). `unreadable` la laisse reconstructible, ce qui est
        # ICI le bon choix : ce registre est un cache republié par chaque démon
        # au démarrage, jamais une source.
        return empty_registry(), "unreadable"
    if not isinstance(data.get("projects"), dict):
        return empty_registry(), "unreadable"
    projects = {
        key: value for key, value in data["projects"].items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    # `{**data, …}` ET NON `{"version", "projects"}` : la reconstruction à deux
    # clés PERDAIT toute clé de PREMIER NIVEAU, et elle la perdait À VERSION
    # ÉGALE — donc dans le cas COURANT, pas dans le cas rare que le garde
    # ci-dessus traite. Mesuré : une clé `hub` ne survivait pas à un aller-retour.
    # C'est la moitié du défaut que la première rédaction avait manquée, et la
    # règle de bump rend la conservation SÛRE : une clé additive ne bumpe pas,
    # donc elle doit survivre.
    return {**data, "version": vu, "projects": projects}, ("ok" if projects else "empty")


def read_registry() -> dict[str, Any]:
    """The registry, or the empty shape. Never raises (see
    `read_registry_state`, which also reports WHY it is empty)."""
    return read_registry_state()[0]


def _write_registry(data: dict[str, Any]) -> None:
    """mkstemp -> write -> fsync -> close fd -> replace_with_retry, same recipe
    as the daemon lock. The fd MUST be closed before the replace (GATE B: a
    replace with the source fd still open fails deterministically with
    WinError 32)."""
    target = registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._registry_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        replace_with_retry(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Liveness — pid AND ping, tri-state (see module docstring).
# ---------------------------------------------------------------------------

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Returning None from `redirect_request` makes urllib raise the 3xx as an
    `HTTPError` instead of chasing `Location`. See `probe_peer`: a peer that
    answers a redirect is not a peer."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


# Built once, at import: no proxies (a 127.0.0.1 probe must never leave the
# host, whatever `http_proxy` says) and no redirect following.
_PROBE_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoRedirectHandler)


def _is_loopback_url(url: str) -> bool:
    """True iff `url` still points at the loopback address we aimed at. Cheap
    second line of defence behind `_NoRedirectHandler`, and the one that is a
    fact about the response rather than a claim about the handler chain."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "http" and parsed.hostname == "127.0.0.1"


def _is_definitive_refusal(exc: BaseException | None) -> bool:
    """True for "nothing is listening on that port", the ONE network failure
    this module treats as proof of death.

    URLLIB WRAPS IT, which is the trap this helper exists for: a refused
    connection surfaces as `urllib.error.URLError` whose `.reason` is the real
    `ConnectionRefusedError` (WinError 10061 on Windows). Testing the URLError
    itself would classify EVERY transport failure — timeouts included — as the
    same thing, and the GC would then delete healthy peers."""
    if exc is None:
        return False
    if isinstance(exc, ConnectionRefusedError):
        return True
    # Windows can also surface it as a bare OSError carrying the winerror.
    return getattr(exc, "winerror", None) == 10061


def probe_peer(port: int, project_id: str | None = None,
               timeout: float = PROBE_TIMEOUT_SECONDS) -> tuple[str, dict[str, Any] | None]:
    """GET `http://127.0.0.1:<port>/api/peer/summary`, UNAUTHENTICATED (see the
    module docstring's arbitration). Returns `(verdict, summary)` with verdict
    in `alive` | `dead` | `indeterminate`; `summary` is the parsed payload, and
    only ever non-None on `alive`.

    A 200 is NOT enough: the body must declare our `kind` AND, when the caller
    supplies one, the SAME `project_id` as the registry entry. Anything else on
    that port is someone else's server that happens to answer — the recycled-port
    case, which is `dead`, not `alive`.

    REDIRECTS ARE NOT FOLLOWED, and that is a security property, not a nicety
    (security review, T-00000083): `urlopen` follows 3xx by default, so a
    process squatting a peer's port could answer `302 Location: <anything>` and
    make this daemon fetch a URL of its choosing — an SSRF primitive handed to
    a co-resident process for free. `_PROBE_OPENER` neutralises the redirect
    handler, so a 3xx surfaces as an `HTTPError` and reads `dead` (it is not
    our `kind`, which is what a redirect literally is: not a peer summary).
    The same opener disables proxies: a loopback probe must never be routed
    through whatever `http_proxy` happens to be exported. The final URL is
    re-checked anyway, because "the handler is neutralised" is a claim and the
    host of what we actually read is a fact."""
    url = f"http://127.0.0.1:{int(port)}{PEER_SUMMARY_PATH}"
    try:
        with _PROBE_OPENER.open(url, timeout=timeout) as resp:
            if resp.status != 200:
                return DEAD, None
            if not _is_loopback_url(resp.geturl()):
                return DEAD, None
            raw = resp.read(_PROBE_READ_LIMIT_BYTES)
    except urllib.error.HTTPError:
        # An answered request with a non-200 code: 404 (the route does not
        # exist — an older daemon), 401, 500. All are "this is not a peer
        # summary", i.e. definitive, never a transient transport failure.
        return DEAD, None
    except urllib.error.URLError as exc:
        # THE UNWRAP. `.reason` is the real errno-bearing exception; the
        # URLError wrapper itself tells timeouts and refusals apart not at all.
        return (DEAD if _is_definitive_refusal(exc.reason) else INDETERMINATE), None
    except OSError as exc:
        # A transport failure urllib did not wrap. `socket.timeout` IS
        # `TimeoutError` (⊂ OSError) since 3.10, so it lands here as
        # indeterminate — never as death. NOTE the branch order: HTTPError ⊂
        # URLError ⊂ OSError, so both must precede this clause or be subsumed.
        return (DEAD if _is_definitive_refusal(exc) else INDETERMINATE), None
    except ValueError:
        # A malformed URL (a port that is not a port). Nothing to probe.
        return DEAD, None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return DEAD, None  # answering, but not with our contract
    if not isinstance(payload, dict) or payload.get("kind") != PEER_SUMMARY_KIND:
        return DEAD, None
    if project_id is not None and payload.get("project_id") != project_id:
        return DEAD, None
    return ALIVE, payload


def inspect_entry(entry: dict[str, Any],
                  timeout: float = PROBE_TIMEOUT_SECONDS) -> tuple[str, dict[str, Any] | None]:
    """`(verdict, summary)` for one registry entry: pid AND ping, in that
    order (a dead pid needs no probe and must not pay for one)."""
    pid = entry.get("pid")
    port = entry.get("port")
    if not isinstance(pid, int) or not pid_alive(pid):
        return DEAD, None
    if not isinstance(port, int) or port <= 0:
        return DEAD, None
    project_id = entry.get("project_id")
    return probe_peer(port, project_id if isinstance(project_id, str) else None, timeout)


def is_entry_alive(entry: dict[str, Any], timeout: float = PROBE_TIMEOUT_SECONDS) -> str:
    """The tri-state verdict alone — `alive` | `dead` | `indeterminate`. Only
    `dead` may be garbage-collected; see the module docstring."""
    return inspect_entry(entry, timeout)[0]


# ---------------------------------------------------------------------------
# Publish / withdraw.
# ---------------------------------------------------------------------------

def _normalised_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """A closed key set, so a caller cannot smuggle a token (or anything else)
    into a machine-wide, world-readable-by-this-user file."""
    return {field: entry.get(field) for field in _ENTRY_FIELDS}


@contextlib.contextmanager
def _registry_lock():
    """Mutual exclusion around the read-modify-write, across PROCESSES.

    Necessary because the verify-and-retry alone cannot fix the classic lost
    update: two daemons both read an empty registry, both write their own
    entry, and both then re-read a file that contains THEMSELVES — each is
    satisfied while one of the two has been erased. Verification detects being
    clobbered, not clobbering; only exclusion prevents the latter.

    NEVER RAISES and never blocks indefinitely: after `_LOCK_WAIT_SECONDS` the
    caller proceeds WITHOUT the lock (degraded, and the verify retry is the
    net), and a lock file older than `_LOCK_STALE_SECONDS` is broken outright
    (its owner was killed; a dead daemon must not wedge every project's
    registration on this machine)."""
    path = Path(str(registry_path()) + ".lock")
    fd: int | None = None
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if _lock_is_stale(path) or time.monotonic() >= deadline:
                if _lock_is_stale(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                    continue
                break  # patience exhausted — proceed unlocked, deliberately
            time.sleep(_LOCK_POLL_SECONDS)
        except OSError:
            # NOT "cannot create a lock at all": on Windows a lock file in the
            # delete-pending state (the releaser unlinked it while a waiter
            # still holds a handle via `_lock_is_stale`->read_text, l.496) makes
            # O_CREAT|O_EXCL fail with PermissionError, not FileExistsError.
            # Breaking here proceeds unlocked AT ONCE, and two such writers lose
            # an entry — exactly the stampede this lock prevents (T-00000204).
            # RECLAIM FIRST, exactly as the FileExistsError branch does: a lock
            # whose recorded owner is provably dead but which surfaces as
            # PermissionError (not FileExistsError) is a corpse too, and must be
            # broken on sight instead of waited out unlocked. The anticipated
            # reclaim therefore now covers BOTH branches (T-00000260).
            if _lock_is_stale(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            # Otherwise retry until the SAME deadline as the FileExistsError
            # branch; proceed unlocked only once patience is exhausted.
            if time.monotonic() >= deadline:
                break  # patience exhausted — proceed unlocked, deliberately
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        if fd is not None:
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            except OSError:
                pass
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            # The release MUST NOT leak: a lock file left behind by a live
            # process poisons every later writer — they wait out their patience
            # (5 s), then ALL proceed unlocked, and the stampede loses entries
            # (T-00000089: 6 writers -> 2 surviving entries, writers returning
            # True). A transient PermissionError here (AV, indexer) gets the
            # same bounded retry as every other unlink in this kit.
            for _attempt in range(_REPLACE_ATTEMPTS):
                try:
                    os.unlink(path)
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    time.sleep(_REPLACE_DELAY_SECONDS)


def _lock_is_stale(path: Path) -> bool:
    """Stale = safe to break: the recorded owner pid is provably DEAD, or the
    file has outlived `_LOCK_STALE_SECONDS`.

    The pid check is what neutralizes a poisoned lock IMMEDIATELY instead of
    after 30 s of machine-wide unlocked stampedes: the creator writes its own
    (live) pid right after the O_EXCL open, so a parsed pid that `pid_alive`
    says is strictly False can only be a corpse. An unreadable/empty content
    (the create-to-write race, or another user's file) proves nothing and
    falls back to the age rule alone."""
    try:
        raw = path.read_text(encoding="ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        raw = ""
    if raw.isdigit():
        try:
            if pid_alive(int(raw)) is False:
                return True
        except (OverflowError, ValueError):
            pass
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age > _LOCK_STALE_SECONDS


def _dead_project_ids(projects: dict[str, Any], skip: str | None,
                      timeout: float) -> dict[str, dict[str, Any]]:
    """The entries whose verdict is `dead`, mapped id -> the entry AS PROBED.

    Computed OUTSIDE the lock on purpose: probing is the slow part (up to
    `timeout` per peer) and holding the cross-process lock for it would make
    two daemons starting together wait on each other's network timeouts. The
    entry is carried along so the caller can check, under the lock, that the
    thing it is about to delete is still the SAME instance it condemned."""
    doomed: dict[str, dict[str, Any]] = {}
    for project_id, entry in projects.items():
        if project_id == skip or not isinstance(entry, dict):
            continue
        if is_entry_alive(entry, timeout) == DEAD:
            doomed[project_id] = entry
    return doomed


def register(entry: dict[str, Any], timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """Publish this daemon into the registry, garbage-collecting the entries
    that are provably `dead` (never the `indeterminate` ones — module
    docstring). Returns True once the entry has been READ BACK from the file.

    Raises only what the filesystem raises (the caller — `run_daemon` — treats
    any failure as `REGISTRY DEGRADED`, never as fatal) and `ValueError` on an
    entry with no project_id, which is a programming error, not a runtime one.

    MEASURED RESIDUAL (T-00000089): if the file lock is unavailable to EVERY
    writer at once (probe: patience forced to zero), a stampede of 6 writers
    still loses entries in ~2 trials of 5, and a lost writer can return True —
    its two verify reads both predated the clobber. Exclusion is the only full
    fix and the lock provides it whenever it can exist at all; the poisoned
    paths that made it unavailable in practice (leaked lock file, dead-owner
    lock) are the ones closed here."""
    project_id = entry.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("register() needs a non-empty project_id")
    payload = _normalised_entry(entry)
    for attempt in range(_VERIFY_ATTEMPTS):
        doomed = _dead_project_ids(read_registry()["projects"], project_id, timeout)
        with _registry_lock():
            current, _state = read_registry_state()
            if _state == "schema_ahead":
                # REFUS D'ÉCRIRE, et refus DÉFINITIF : réessayer ne changera pas
                # la version du fichier. Publier ici restamperait `version` à la
                # nôtre et effacerait les champs d'un kit plus récent.
                return False
            projects = {
                key: value for key, value in current["projects"].items()
                if key != project_id and not _same_instance(value, doomed.get(key))
            }
            projects[project_id] = payload
            # `{**current, …}` : conserver les clés de PREMIER NIVEAU qu'un kit
            # d'une autre génération aurait posées. Les écraser était la perte
            # SILENCIEUSE du cas courant — celui à version ÉGALE, que le garde
            # `schema_ahead` ne voit pas par construction.
            _write_registry({**current, "version": REGISTRY_VERSION,
                             "projects": projects})
        # TWO reads, a jittered beat apart, must BOTH contain the entry. A
        # single point-in-time read returns True to a writer that is about to
        # be erased by a peer still holding a pre-write snapshot (measured in
        # the T-00000089 stampede probe: every writer True, 3 entries of 6 on
        # disk). The settle-read narrows that window from "the rest of the
        # stampede" to "one clobber landing between two spaced reads".
        settled = True
        for _read in range(2):
            verify, _state = read_registry_state()
            if verify["projects"].get(project_id) != payload:
                settled = False
                break
            time.sleep(random.uniform(0.005, 0.02))
        if settled:
            return True
        if attempt < _VERIFY_ATTEMPTS - 1:
            # Growing + jittered: synchronized losers must NOT retry in step.
            time.sleep(_VERIFY_DELAY_SECONDS * (attempt + 1)
                       + random.uniform(0.0, _VERIFY_JITTER_SECONDS))
    return False


def _same_instance(entry: Any, condemned: Any) -> bool:
    """True iff `entry` is the very daemon instance that was probed and found
    dead — same pid AND same port. A project that re-registered while we were
    probing has a fresh entry that must survive our GC."""
    if not isinstance(entry, dict) or not isinstance(condemned, dict):
        return False
    return (entry.get("pid") == condemned.get("pid")
            and entry.get("port") == condemned.get("port"))


def unregister(project_id: str, pid: int) -> bool:
    """Remove OUR entry — and only ours. The `pid` guard is the same reasoning
    as `remove_lock_if_ours`: a successor daemon for the SAME project may have
    registered between our shutdown starting and this call, and clobbering its
    entry would make a LIVE daemon invisible to every other project.

    No GC here, deliberately: this runs on the shutdown path, where spending
    seconds probing the neighbours would delay the process exit for a tidying
    job the next `register()` does anyway.

    Returns True iff an entry was actually removed."""
    if not isinstance(project_id, str) or not project_id:
        return False
    with _registry_lock():
        current, _state = read_registry_state()
        if _state == "schema_ahead":
            # Ce chemin était DÉJÀ sûr par construction — `schema_ahead` rend un
            # registre vide, donc le garde `pid` juste en dessous tombe et rien
            # n'est écrit. Le refus est rendu EXPLICITE parce que la sûreté
            # tenait à la FORME de la valeur rendue, pas à une intention : un
            # futur `read_registry_state` qui rendrait les projets lus malgré
            # l'écart de version rouvrirait la perte sans que rien ne l'annonce.
            return False
        entry = current["projects"].get(project_id)
        if not isinstance(entry, dict) or entry.get("pid") != pid:
            return False
        projects = {key: value for key, value in current["projects"].items()
                    if key != project_id}
        _write_registry({**current, "version": REGISTRY_VERSION,
                         "projects": projects})
    return project_id not in read_registry()["projects"]
