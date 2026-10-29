#!/usr/bin/env python3
"""Dashboard daemon lifecycle — singleton lock, detached launch, liveness,
auto-stop (T-00000025 shard 2). stdlib only.

This module is the PRODUCTION launch path that `dashboard.py` (shard 1)
deliberately does not contain. Every mechanism here is the one GATE B
(`.agents/evals/test_gate_b_launch_probe.py`, verdict S-00000041) proved
empirically on this platform — nothing below is a guess:

  1. SINGLETON — `state/local/dashboard.lock`, acquired with
     `os.open(O_CREAT | O_EXCL)`: exactly one winner across concurrent
     processes (GATE B item 3, 3/3 runs at 10 processes).
  2. DETACHED LAUNCH — `subprocess.Popen` with stdin/stdout/stderr =
     `DEVNULL` plus `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on
     Windows (GATE B item 1: the bare-inherit baseline HANGS the
     SessionStart hook; this combo returns promptly and the child
     survives). POSIX fallback: `start_new_session=True` (combo G, also
     green). The hook's stdout stays ONE JSON object (item 2) because the
     child never touches the inherited pipe.
  3. LIVENESS — a pid probe ALONE is insufficient (GATE B item 4: a
     recycled pid is alive without being ours). Liveness therefore
     requires pid-alive AND a tokenised HTTP ping answered 200 on the
     locked port. The ping reuses the frozen `/api/snapshot` contract with
     the lock's own Bearer token — no new route, so the shard-1 route
     freeze holds.
  4. ATOMIC LOCK REWRITE — mkstemp -> write -> fsync -> close fd ->
     `os.replace` wrapped in a BOUNDED RETRY on PermissionError
     (L-00000054: a bare replace fails 69-81% of the time under a
     concurrent reader on Windows; 30 x 10ms always converged, never tore).

RECLAIM RACE: two processes can both observe the same stale lock and both
rewrite it — `os.replace` makes the writes atomic but the LAST writer wins.
So after binding its servers, the daemon re-reads the lock and verifies the
token is its own; a loser shuts its servers down and exits quietly instead
of running unlisted (`run_daemon` step "ownership re-check").

FAIL-OPEN (non-negotiable): launched from the SessionStart hook, no failure
here may ever block or corrupt the session. `ensure_running` swallows
everything; `run_daemon` reports degradation on stderr (visible on a manual
run, discarded under the hook's DEVNULL) and exits — it never raises out.

OTLP: the daemon owns BOTH sockets of design doc §B.3 in one process — the
UI/API server (ephemeral port, tokenised) and the OTLP receiver on 4318
(`otel_receiver.OTLPHandler`, its own handler class, nothing shared). A 4318
bind conflict is the documented degraded path (L-00000050): recorded in the
lock as `otel: degraded`, never fatal to the UI side.

RESIDUAL RISK (security review, advisory): the lock's liveness is
self-certifying — a co-resident process running as the same user could write
its own pid/port/token into the lock and answer the ping itself, steering
`/dash` to an impostor. Accepted under the declared threat model: same-user
code already has arbitrary control over this repo; no realistic in-kit
mitigation exists (documented alongside L-00000050/L-00000054).

MACHINE REGISTRY (T-00000083): once the lock is confirmed ours, this daemon
also publishes {project_id, root, name, pid, port, started} — NEVER its token —
into `~/.agentkit/registry.json` (`dashboard_registry.py`), and withdraws on the
way out. That file is the only way another project's dashboard learns this one
exists; there is no discovery and no disk scan. Both halves are strictly
best-effort: no identity, or a registry that cannot be written, degrades to a
stderr line and an invisible daemon — never to a failed launch. `pid_alive` and
`replace_with_retry` now LIVE in that module and are delegated back here under
their original names.

AUTO-STOP: a watchdog thread stops the daemon (and removes its own lock)
after `--idle-hours` (default 4h) without activity, where activity is an
authorised UI request OR movement in the OTLP receiver's ingest
diagnostics. A killed daemon (SIGTERM, crash) leaves its lock behind on
purpose — the next launch sees it stale via liveness and reclaims.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Same explicit-path import contract as dashboard.py — never depend on
    sys.path[0] (a hook feeding Python from stdin has no useful one)."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_dashboard = _load_sibling("_daemon_dashboard", "dashboard.py")
# The SAME module instance whose OTLPHandler serves 4318 must be the one the
# watchdog reads diagnostics from — load once, share both uses.
_otel_receiver = _dashboard._otel_receiver
# T-00000049 — the SQLite projection. Reused from `dashboard.py`'s own load for
# the same reason as the receiver above: the ingest thread's resume offsets and
# the `notify_dirty` doorbell must live in ONE module instance, or the doorbell
# rings in a store nobody is ticking.
_event_store = _dashboard._event_store_mod
# T-00000083 — the machine-wide daemon registry (`~/.agentkit/registry.json`).
# Loaded as its own sibling rather than reused from `_dashboard`: that module
# holds no state for it (the registry is a file, not a cache), and the daemon
# must keep working if the dashboard's own load order ever changes.
_registry = _load_sibling("_daemon_registry", "dashboard_registry.py")

# Bound on the ingest thread's shutdown join. Exceeding it is NOT a reason to
# release the daemon lock (see `run_daemon`): "the daemon is the sole writer of
# the database" outranks "the lock file is tidy".
_INGEST_JOIN_SECONDS = 10.0
# T-01M51Q7GJ1B6315SFKNDAAE2P0 (lot C) — the same bound, and the same rule, for the etat.db writer thread: a
# join that times out keeps the daemon lock, so no second writer of etat.db can start.
_ETAT_JOIN_SECONDS = _INGEST_JOIN_SECONDS

_LOCK_RELPATH = Path(".agents") / "state" / "local" / "dashboard.lock"
_IDLE_HOURS_DEFAULT = 4.0
# 2s, not 1s: the ping answers /api/snapshot (~7ms warm after the 4b
# memoisation) but a cold read under AV/suite contention was measured
# spilling past 1s — a false "stale" verdict there makes a healthy daemon
# get reclaimed. Worst case this bounds a session-start liveness check, so
# generosity is cheap; correctness of the verdict is not.
_PING_TIMEOUT_SECONDS = 2.0
# L-00000054 — measured on this host: 5-8 retries max were ever needed;
# 30 x 10ms is the proven bound that always converged and never tore.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01
# How long ensure_running polls for the spawned child to publish its lock.
_SPAWN_WAIT_SECONDS = 5.0
# T-00000613 - how long `--stop` waits for the signalled pid to VANISH before it
# gives up and KEEPS the lock. Read at call time (tests shorten it; its production
# value is pinned between 2 and 30 s by test_dashboard_daemon_arret). 5 s is a
# choice, not a measurement: a real daemon vanished 1-13 ms after SIGTERM, idle
# and at 0.79 GB under four snapshot clients (empty store, no OTLP receiver); one
# that pages out at several GB is unmeasured.
_STOP_WAIT_SECONDS = 5.0
_STOP_POLL_SECONDS = 0.1


def normalize_root(value: str | Path | None) -> Path | None:
    """Accept a Git-Bash/MSYS POSIX root (`/c/Users/...`) as well as a native
    one, translating the former to `c:/Users/...` when that is what exists.

    Not cosmetic (found in use): every hook in this kit exports
    `CLAUDE_PROJECT_DIR` through `cygpath -u`, so the documented invocation
    `--dash --root "$CLAUDE_PROJECT_DIR"` handed this CLI a path native Python
    cannot resolve. The lock then resolved under a nonexistent tree, so a live
    daemon looked absent, the spawn had the same broken root, and `--dash`
    exited 2 with "no daemon could be started" while one was running happily.
    Same translation as `log-agent-usage.sh`'s `resolve_path` (L-003)."""
    if value is None:
        return None
    text = str(value)
    path = Path(text)
    if path.exists():
        return path
    match = re.match(r"^/([A-Za-z])/(.*)$", text)
    if match:
        alt = Path(f"{match.group(1)}:/{match.group(2)}")
        if alt.exists():
            return alt
    return path


def _project_root() -> Path:
    return _dashboard._project_root()


def lock_path(root: Path) -> Path:
    return root / _LOCK_RELPATH


# ---------------------------------------------------------------------------
# GATE B item 4 / L-00000054 — atomic publish with bounded retry.
# ---------------------------------------------------------------------------

def replace_with_retry(
    src: str | Path,
    target: str | Path,
    attempts: int = _REPLACE_ATTEMPTS,
    delay: float = _REPLACE_DELAY_SECONDS,
) -> None:
    """`os.replace` with a bounded retry on PermissionError. Re-raises the
    last PermissionError once the bound is exhausted — a lock that cannot be
    published is a loud failure, never a silent partial.

    THE BODY MOVED to `dashboard_registry.py` (T-00000083), which needs the
    same recipe for a file this module does not own. This name stays public
    and unchanged: it is the daemon's publish primitive and its callers (here
    and in the tests) address it as `dashboard_daemon.replace_with_retry`.
    Delegation, not a copy — one measured recipe, one implementation."""
    _registry.replace_with_retry(src, target, attempts=attempts, delay=delay)


def write_lock(root: Path, payload: dict[str, Any]) -> None:
    """mkstemp -> write -> fsync -> close fd -> replace_with_retry. The fd
    MUST be closed before the replace (GATE B: replace with the source fd
    still open fails deterministically with WinError 32)."""
    target = lock_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._lock_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False))
            fh.flush()
            os.fsync(fh.fileno())
        replace_with_retry(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_lock(root: Path) -> dict[str, Any] | None:
    """The lock's parsed content, or None (absent, unreadable, malformed,
    or not the {pid, port, token} shape). Malformed never raises: a corrupt
    lock is indistinguishable from a stale one and handled the same way."""
    try:
        raw = lock_path(root).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not all(k in data for k in ("pid", "port", "token")):
        return None
    if not isinstance(data["pid"], int) or not isinstance(data["port"], int):
        return None
    if not isinstance(data["token"], str) or not data["token"]:
        return None
    return data


def remove_lock_if_ours(root: Path, token: str) -> bool:
    """Remove the lock only if it still carries OUR token — never clobber a
    successor's lock from a stale shutdown path."""
    current = read_lock(root)
    if current is None or current["token"] != token:
        return False
    try:
        os.unlink(lock_path(root))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# GATE B item 4 — liveness: pid probe PLUS tokenised ping. Neither alone.
# ---------------------------------------------------------------------------

def pid_alive(pid: int) -> bool:
    """MOVED to `dashboard_registry.py` (T-00000083) — the registry's GC needs
    the same Windows-correct probe. Public name kept: `daemon.pid_alive` is
    what `daemon_status` and the tests call."""
    return _registry.pid_alive(pid)


def _probe(port: int, path: str, token: str, timeout: float) -> bool | None:
    """True/False for an answered request, None when the route is absent (404)
    so the caller can fall back."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # older daemon: this route did not exist yet
        return False     # 401 and friends: answering, but not ours
    except (urllib.error.URLError, ConnectionError, OSError):
        return False


def ping(port: int, token: str, timeout: float = _PING_TIMEOUT_SECONDS) -> bool:
    """True only if OUR daemon answers, using `/api/ping` — a route that reads
    nothing and builds nothing (T-00000043).

    This used to probe `/api/snapshot` to avoid adding a route. That was
    reasonable while the snapshot was a handful of small JSON reads, and became
    a defect once D4 grew it to ~166 KB across six readers: a liveness check
    that pays the cost of the heaviest read reports a HEALTHY daemon as stale
    whenever the machine is busy, and the reclaim path then takes its lock.

    Falls back to `/api/snapshot` on a 404 so a daemon started before this
    change is still recognised as alive — an upgrade in flight must never look
    like a dead daemon."""
    result = _probe(port, "/api/ping", token, timeout)
    if result is None:
        return bool(_probe(port, "/api/snapshot", token, timeout))
    return result


def code_state(lock: dict[str, Any] | None) -> str:
    """'current' · 'stale' · 'unknown' — does the live daemon serve the code
    that is on disk right now? (T-00000040: a stale daemon is indistinguishable
    from a healthy one by pid and ping alone; the symptom lands in the browser,
    not in any probe.) 'unknown' when the lock predates this field, so an
    upgrade in flight never reports a false 'stale'."""
    if not lock or not isinstance(lock.get("code"), str):
        return "unknown"
    return "current" if lock["code"] == _dashboard.served_code_fingerprint() else "stale"


def _rss_octets(pid: Any) -> int | None:
    """La mémoire résidente du démon, en OCTETS — ou None si on n'a pas su lire.

    OCTETS BRUTS, ET C'EST UNE LEÇON PAYÉE LE 2026-09-14. J'avais d'abord rendu
    des « Mo » : mes tickets les écrivaient en Mo DÉCIMAUX (÷ 1e6) et cet
    instrument en Mio (÷ 1024²). Le même `events.db` valait donc 628,9 ici et
    599,8 là — deux chiffres pour un fichier, sur des nombres destinés à porter
    une décision de plafond. Un entier d'octets ne peut pas être mal lu ; la
    conversion appartient à qui affiche, jamais à qui mesure.

    `ps` plutôt qu'une bibliothèque : ce fichier tourne sur un noyau stdlib
    seule, et `psutil` n'est pas une dépendance qu'on ajoute pour un chiffre de
    diagnostic. None, jamais 0 : une mesure absente ne se lit pas « le processus
    ne consomme rien ».

    COUVERTURE INÉGALE, ET IL FAUT LE DIRE PLUTÔT QUE DE LE LAISSER DÉCOUVRIR
    (relevé du binôme). `ps` n'existe pas sur Windows : ce champ y vaut donc
    **TOUJOURS None**, et la croissance mémoire du démon y est invisible. La
    dégradation est correcte — None plutôt qu'un zéro menteur — mais elle n'est
    pas une couverture. `events_db_octets`, lui, se lit partout : les deux
    moitiés de l'empreinte n'ont pas la même portée, et un lecteur qui compte
    des postes instrumentés ne doit pas les confondre.
    """
    try:
        brut = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=5).stdout.decode().strip()
        return int(brut) * 1024 if brut else None  # `ps` rend des Ko
    except Exception:
        return None


# T-00000613 - what `ps` shows for a daemon RUN, as `main()` accepts it: a Python
# interpreter as the FIRST word (`python3`, `python3.12`, `python.exe`, or the
# `Python` a macOS framework build shows), its own options, then the script
# `dashboard_daemon.py` as the program, then an isolated `--daemon`, then maybe
# `--root <root>` or `--root=<root>` (a root may hold spaces: it ends at the next
# `--flag`). The literal spelling only: an abbreviated flag (`--dae`) is not
# recognised.
_DEMON_INTERP = re.compile(r"(?:^|[/\\])python[0-9.]*[tw]?(?:\.exe)?$", re.IGNORECASE)
_DEMON_FILE = re.compile(r"(?:^|[/\\])dashboard_daemon\.py$")
_DEMON_NEW_ARG = re.compile(r"[-/\\]|[A-Za-z]:[\\/]")
_DEMON_FLAG = re.compile(r"(?:^|\s)--daemon(?=\s|$)")
_DEMON_ROOT = re.compile(r"(?:^|\s)--root[\s=](?P<root>.+?)(?=\s--[A-Za-z]|$)")


def _demon_argv(args: str) -> str | None:
    """What follows the script on a `ps` line that RUNS `dashboard_daemon.py`
    under a Python interpreter, or None (T-00000613). A wrapper (`timeout`,
    `sh -c`, `uv run`, `caffeinate`) is not that line - its Python child is,
    once; nor is a tool that only cites the command (`grep`, `pgrep -f`, an
    editor), nor `python -m ...` / `python -c ...`. The script path may hold
    spaces: a later word joins it only when the first word is a path, the word
    does not open a new argument (`-`, `/`, a backslash, a drive letter) and the
    previous word is not a `.py` program. Over-count residual, named: a Python
    program launched by path whose next words are a RELATIVE path ending in
    `dashboard_daemon.py` then `--daemon` is counted, whether it runs that
    script (`coverage run` does) or only cites it. Under-count: an interpreter
    whose own path holds a space or that is not named `python*` (PyPy), and
    `python -m dashboard_daemon`."""
    premier, _, reste = args.partition(" ")
    if not _DEMON_INTERP.search(premier):
        return None
    reste = reste.lstrip()
    while reste.startswith("-"):
        mot, _, reste = reste.partition(" ")
        if mot == "-" or mot.startswith("--"):
            return None
        for i, lettre in enumerate(mot[1:], 1):
            if lettre in "cm":
                return None  # `-c` / `-m`: the program is not a script file
            if lettre in "XW":
                if i == len(mot) - 1:
                    reste = reste.lstrip().partition(" ")[2]  # its value is the next word
                break
        reste = reste.lstrip()
    mots = reste.split(" ")
    for n, mot in enumerate(mots):
        if n and (not re.search(r"[/\\]", mots[0]) or _DEMON_NEW_ARG.match(mot)
                  or mots[n - 1].endswith(".py")):
            return None
        if _DEMON_FILE.search(mot):
            return " ".join(mots[n + 1:])
    return None


def _demons_du_poste() -> list[dict[str, Any]] | None:
    """The dashboard daemons `ps` shows on THIS machine, whatever their project
    (T-00000613): pid, rss_octets (raw bytes, like `_rss_octets`), root. A LOWER
    BOUND of the daemon runs, never a census (the one over-count residual is
    named in `_demon_argv`): it counts a process whose program is
    `dashboard_daemon.py` under a Python interpreter, with the token `--daemon`,
    for every account `ps -A` shows - a shared host thus shows other accounts'
    roots, which `ps` already shows anyone. A daemon started another way
    (renamed script, abbreviated flag, an interpreter `_demon_argv` does not
    know) is invisible: `--status` checks that blindness on the one daemon it can
    ping (`demons_du_poste_etalon`). Neither the lock (one root) nor the machine
    registry (only daemons with an identity) can count. None when `ps` cannot be
    read (Windows, absent, failing, silent): an absent measure is never an empty
    list."""
    try:
        done = subprocess.run(["ps", "-A", "-ww", "-o", "pid=,rss=,args="],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        return None
    brut = done.stdout.decode("utf-8", "replace")
    if done.returncode != 0 or not brut.strip():
        return None
    demons: list[dict[str, Any]] = []
    for ligne in brut.splitlines():
        champs = ligne.split(None, 2)
        if len(champs) < 3 or not champs[0].isdigit():
            continue
        reste = _demon_argv(champs[2])
        if reste is None or _DEMON_FLAG.search(reste) is None:
            continue
        racine = _DEMON_ROOT.search(reste)
        demons.append({"pid": int(champs[0]),
                       "rss_octets": int(champs[1]) * 1024 if champs[1].isdigit() else None,
                       "root": racine.group("root") if racine else None})
    return demons


def _empreinte_locale(root: Path, lock: dict[str, Any] | None) -> dict[str, Any]:
    """CE QUE CE POSTE PAIE EN CE MOMENT — T-00000612 et T-00000613.

    POURQUOI ICI, ET PAS AILLEURS. Les deux tickets demandent la MÊME chose en
    premier : instrumenter avant de chercher la fuite. `--status` est le seul
    endroit que le pilote consulte déjà quand il se demande ce que le dashboard
    fabrique — y ajouter deux nombres coûte zéro et rend VISIBLE une croissance
    qui, jusqu'ici, ne se découvrait qu'en tapant `ls -la` ou `ps`.

    CE QUE ÇA A COÛTÉ DE NE PAS L'AVOIR : le 2026-09-14, ce démon tenait 3,5 Go
    après 1 h 40 et a fait TUER une porte par l'OS — pas un rouge, un incident
    de machine, c'est-à-dire le seul mode d'échec qu'aucun verdict ne nomme.
    Et `events.db` pesait 628 936 704 octets sans que rien ne le signale, parce qu'il vit
    sous `.agents/state/local/`, qui est git-ignoré : il n'apparaît dans aucun
    diff et aucune revue ne le voit grossir.

    CE N'EST PAS UNE GARDE, ET IL NE FAUT PAS LE LIRE COMME TELLE : rien ne
    refuse, rien ne se plafonne. On rend un fait lisible ; décider quoi en faire
    reste porté par les deux tickets. Poser un seuil ici, sans la courbe que
    personne n'a encore mesurée, serait exactement le nombre inventé que ces
    tickets interdisent.
    """
    out: dict[str, Any] = {}
    if lock and lock.get("pid"):
        out["rss_octets"] = _rss_octets(lock["pid"])
    db = root / ".agents" / "state" / "local" / "events.db"
    try:
        out["events_db_octets"] = db.stat().st_size if db.is_file() else None
    except OSError:
        out["events_db_octets"] = None
    return out


def stop_and_release(root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """SIGTERM the locked pid, then release the lock ONLY once that pid is
    verified gone (T-00000613). A pid that survives `_STOP_WAIT_SECONDS` KEEPS
    the lock: releasing it would let the next session start a second daemon while
    this one still runs, unreachable by any later `--stop`. No SIGTERM handler is
    installed by the daemon or by any module it loads through `_load_sibling`
    (pinned by a source witness in test_dashboard_daemon_arret; a real daemon was
    measured dying by the signal, exit -15), so the daemon never runs its own
    cleanup on `--stop` - the `finally` of `run_daemon` is not reached: the lock
    is removed here, on its behalf, once the pid is gone. Nothing here removes
    the killed daemon's machine-registry entry either: the next daemon that
    registers garbage-collects it once probed dead (unchanged). On Windows
    SIGTERM is also a hard TerminateProcess."""
    import signal

    pid = lock["pid"]
    attente = _STOP_WAIT_SECONDS
    kill_error = None
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as exc:
        kill_error = f"{type(exc).__name__}: {exc}"
    deadline = time.monotonic() + attente
    while pid_alive(pid):
        if time.monotonic() >= deadline:
            out: dict[str, Any] = {"status": "still-running", "pid": pid, "lock": "kept",
                                   "waited_seconds": attente}
            if kill_error:
                out["kill_error"] = kill_error
            return out
        time.sleep(_STOP_POLL_SECONDS)
    remove_lock_if_ours(root, lock["token"])
    return {"status": "stopped", "pid": pid}


def daemon_status(root: Path) -> tuple[str, dict[str, Any] | None]:
    """('alive', lock) — pid alive AND tokenised ping answered;
    ('stale', lock) — a lock exists but fails either probe;
    ('absent', None) — no (readable) lock at all."""
    lock = read_lock(root)
    if lock is None:
        # An unreadable/malformed lock FILE may still exist — report it
        # stale so acquisition reclaims it rather than O_EXCL failing forever.
        return ("stale", None) if lock_path(root).exists() else ("absent", None)
    if pid_alive(lock["pid"]) and ping(lock["port"], lock["token"]):
        return ("alive", lock)
    return ("stale", lock)


# ---------------------------------------------------------------------------
# GATE B item 3 — acquisition: O_CREAT|O_EXCL, stale reclaim via atomic
# rewrite, reclaim race closed later by run_daemon's ownership re-check.
# ---------------------------------------------------------------------------

def acquire_lock(root: Path, provisional: dict[str, Any]) -> bool:
    """True if WE now hold the lock (freshly created, or reclaimed from a
    stale holder); False if a live daemon already holds it."""
    target = lock_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        status, _lock = daemon_status(root)
        if status == "alive":
            return False
        # Stale (or unreadable) — reclaim atomically. If a rival reclaims
        # concurrently, os.replace keeps every read whole and the LAST
        # writer wins; run_daemon re-checks ownership after binding.
        write_lock(root, provisional)
        return True
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(provisional, ensure_ascii=False))
    return True


# ---------------------------------------------------------------------------
# The daemon itself.
# ---------------------------------------------------------------------------

def _start_otel_thread() -> tuple[Any | None, str]:
    """Bind the OTLP receiver (4318, fixed by every host) in-process and serve
    it from a daemon thread. Returns (server-or-None, status). A bind conflict
    is the documented degraded path — visible, never fatal (L-00000050).

    V1-c / spec §A.4 — COEXIST, NEVER FIGHT. On a bind failure the daemon now
    ASKS who holds the port instead of reporting a bare `degraded`, and the
    three answers are three different lock states an operator can act on:

      * `served_elsewhere` — a PEER of this kit (another provisioned project's
        daemon) holds 4318. It redacts and persists exactly as we do, so canal B
        is served, just not by us. We do NOT try to take the port: `_ExclusiveHTTPServer`
        is untouched (L-00000050 — SO_EXCLUSIVEADDRUSE means neither side can
        steal it anyway) and killing a peer would take down another project's
        trail. NOT AN ERROR.
      * `degraded_foreign` — something else owns 4318. Canal B IS degraded for
        this machine and the operator has to know, because our hosts will keep
        POSTing telemetry into a process we know nothing about.
      * `unreachable` -> ONE immediate re-bind. Nobody answered, so the bind
        failure was a race or the holder just died; recording a permanent
        verdict on that would be wrong (iteration 1, C6). If the retry also
        fails, `degraded` — and `run_daemon`'s 30 s poll keeps retrying.
    """
    def _bind() -> tuple[Any | None, OSError | None]:
        try:
            return _otel_receiver._ExclusiveHTTPServer(
                (_otel_receiver._HOST, _otel_receiver._PORT), _otel_receiver.OTLPHandler
            ), None
        except OSError as exc:
            return None, exc

    httpd, error = _bind()
    if httpd is None:
        # The address is passed EXPLICITLY: a probe that reported on a different
        # socket than the one that just failed to bind would be worse than no
        # probe at all (found by this function's own test).
        probe = _otel_receiver.probe_port_holder(
            _otel_receiver._HOST, _otel_receiver._PORT)
        holder = probe.get("holder")
        if holder == "unreachable":
            httpd, error = _bind()          # the race / just-died case
        if httpd is None:
            if holder == "kit_peer":
                print(
                    f"OTEL RECEIVER SERVED ELSEWHERE: {_otel_receiver._HOST}:"
                    f"{_otel_receiver._PORT} is held by another agentkit daemon "
                    f"({probe.get('server')}) — not contesting it; canal B for this "
                    f"project is collected by that peer and attributed by "
                    f"agentkit.project_id",
                    file=sys.stderr, flush=True,
                )
                return None, "served_elsewhere"
            if holder == "foreign":
                print(
                    f"OTEL RECEIVER DEGRADED (FOREIGN HOLDER): {_otel_receiver._HOST}:"
                    f"{_otel_receiver._PORT} is held by a process that is not this kit "
                    f"({probe.get('server') or 'no Server header'}) — every host will "
                    f"keep POSTing telemetry to it and this project collects NOTHING",
                    file=sys.stderr, flush=True,
                )
                return None, "degraded_foreign"
            print(
                f"OTEL RECEIVER DEGRADED: bind {_otel_receiver._HOST}:"
                f"{_otel_receiver._PORT} failed ({error}) and nothing answered the "
                f"probe ({probe.get('reason')}) — dashboard UI continues without a "
                f"collector; the 30 s poll will retry the bind",
                file=sys.stderr, flush=True,
            )
            return None, "degraded"
    threading.Thread(target=httpd.serve_forever, daemon=True, name="otel-receiver").start()
    return httpd, "listening"


def _otel_activity_fingerprint() -> tuple[int, ...]:
    try:
        diag = _otel_receiver.get_diagnostics()
    except Exception:
        return ()
    return tuple(diag[k] for k in sorted(diag))


def _start_ingest_loop() -> Any | None:
    """Start the 5 s spool->SQLite ingest tick INSIDE this process (spec §A.2:
    "dans la boucle existante du démon (pas de nouveau processus)"). A second
    process would be a second writer, which is the one thing the design forbids.

    Degraded, never fatal: a store that cannot be opened leaves the spool files
    untouched on disk, so the file-based readers keep working and nothing is
    lost — exactly the fail-open posture the rest of the observability trail
    has."""
    try:
        _otel_receiver.set_dirty_notifier(_event_store.notify_dirty)
    except Exception as exc:  # noqa: BLE001 - a doorbell is never load-bearing
        print(f"INGEST DOORBELL DEGRADED: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
    try:
        loop = _event_store.IngestLoop()
        loop.start()
        return loop
    except Exception as exc:  # noqa: BLE001
        print(
            f"EVENT STORE DEGRADED: ingest thread not started "
            f"({type(exc).__name__}: {exc}) — the spool files are kept and the "
            f"file readers still serve them",
            file=sys.stderr, flush=True,
        )
        return None


def _start_etat_loop(root: Path, verrou: Any | None) -> Any | None:
    """Start the etat.db writer (`etat_projection.Boucle`, T-01M51Q7GJ1B6315SFKNDAAE2P0 lot C) INSIDE this
    process: its ONLY writer, beside the only server that reads it. `verrou` is the snapshot memo's build lock,
    held by every tick while it loads the team stores — never two loads of one store at once in this process.

    Loaded HERE, not at import: a missing or broken `etat_projection.py` must cost the paginated routes their
    base (they read the stores directly), never the daemon its start. Degraded, never fatal."""
    try:
        module = _load_sibling("_daemon_etat_projection", "etat_projection.py")
        boucle = module.Boucle(root, verrou=verrou)
        boucle.start()
        return boucle
    except Exception as exc:  # noqa: BLE001
        print(
            f"ETAT DB DEGRADED: projection thread not started ({type(exc).__name__}: {exc}) — the "
            f"paginated routes read the stores directly",
            file=sys.stderr, flush=True,
        )
        return None


def run_daemon(
    root: Path | None = None,
    idle_seconds: float = _IDLE_HOURS_DEFAULT * 3600.0,
    poll_seconds: float = 30.0,
    with_otel: bool = True,
    with_ingest: bool = True,
    with_etat: bool = True,
) -> int:
    """Blocking daemon entry point. Exit codes: 0 = clean (including
    "another live daemon already holds the lock" and "lost the reclaim
    race" — both are the singleton working); 2 = degraded (could not bind
    the UI socket).

    `with_etat` (default True, T-01M51Q7GJ1B6315SFKNDAAE2P0) starts the etat.db
    writer thread, and only alongside the ingest loop (`with_ingest=True`):
    the switch measure M5 flips, with no CLI flag and no environment
    variable."""
    root = normalize_root(root) or _project_root()

    provisional = {"pid": os.getpid(), "port": 0, "token": f"starting-{os.getpid()}-{time.time_ns()}"}
    try:
        if not acquire_lock(root, provisional):
            print("dashboard daemon already running — exiting", file=sys.stderr, flush=True)
            return 0
    except OSError as exc:
        print(f"DASHBOARD DAEMON DEGRADED: cannot acquire lock ({exc})", file=sys.stderr, flush=True)
        return 2

    created = _dashboard.create_ui_server(project_root=root)
    if created is None:
        print("DASHBOARD DAEMON DEGRADED: UI bind failed — no daemon started", file=sys.stderr, flush=True)
        remove_lock_if_ours(root, provisional["token"])
        return 2
    httpd, token = created
    port = httpd.server_address[1]

    # A MUTABLE holder, because the watchdog re-tries the bind (see below) and
    # the shutdown path has to close whatever is bound BY THEN, not what was
    # bound at start-up.
    otel: dict[str, Any] = {"httpd": None, "status": "disabled"}
    if with_otel:
        otel["httpd"], otel["status"] = _start_otel_thread()
    otel_httpd, otel_status = otel["httpd"], otel["status"]

    payload = {
        "pid": os.getpid(),
        "port": port,
        "token": token,
        "otel": otel_status,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # T-00000040: what this process would serve, so a later --status can
        # tell "alive" from "alive but serving code older than the disk".
        "code": _dashboard.served_code_fingerprint(),
    }
    try:
        write_lock(root, payload)
    except OSError as exc:
        print(f"DASHBOARD DAEMON DEGRADED: cannot publish lock ({exc})", file=sys.stderr, flush=True)
        httpd.server_close()
        if otel_httpd is not None:
            otel_httpd.shutdown()
            otel_httpd.server_close()
        return 2

    # Ownership re-check — closes the stale-reclaim race (module docstring).
    current = read_lock(root)
    if current is None or current["token"] != token:
        print("dashboard daemon lost the lock race after binding — exiting", file=sys.stderr, flush=True)
        httpd.server_close()
        if otel_httpd is not None:
            otel_httpd.shutdown()
            otel_httpd.server_close()
        return 0

    # T-00000083 — publish into the machine-wide registry, AFTER the ownership
    # re-check: a daemon that lost the reclaim race above has already returned,
    # so no loser ever advertises itself to the other projects.
    #
    # NEVER FATAL, in either direction. No usable identity (`project.json`
    # absent, or carrying no project_id) means no key to register under, so
    # this daemon simply stays invisible to `/api/peers` and says so on stderr
    # — the UI, the lock and the ingest loop are untouched.
    #
    # ANCHOR CAVEAT: the identity is resolved through
    # `event_store.project_json_path()`, which is anchored on `__file__` (or
    # `AGENTS_PROJECT_JSON`), NOT on `--root`. Under `--root X` those two can
    # name different files — the pre-existing divergence tracked as
    # T-00000056. Accepted here rather than papered over: inventing a third
    # resolution rule for this one call site would make the registry disagree
    # with `/api/projects` about who this daemon is.
    registered_project_id: str | None = None
    identity = _dashboard._resolve_identity_once(_event_store.project_json_path())
    if identity["status"] != "ok":
        print(
            f"REGISTRY DEGRADED (no project identity: {identity['status']}/"
            f"{identity['cause']}) — this daemon will not appear in other "
            f"projects' /api/peers",
            file=sys.stderr, flush=True,
        )
    else:
        registered_project_id = identity["project_id"]
        try:
            published = _registry.register({
                "project_id": registered_project_id,
                "project_root": str(root),
                # T-00000582: the registry name is ROOT-derived (this daemon's
                # own --root), like /api/peer/summary, NOT identity["name"].
                # Reached via the `_load_sibling` handle (`_dashboard`), never a
                # direct import of dashboard.py.
                "name": _dashboard._nom_depuis_racine(root),
                "pid": os.getpid(),
                "port": port,
                "started": payload["started"],
            })
            if not published:
                # LE CANAL DE RETOUR ÉTAIT JETÉ, et `register()` a DEUX façons
                # de rendre False : refuser (registre écrit par un kit plus
                # récent) ou échouer après ses essais. Les deux étaient muettes
                # — le démon disparaissait des `/api/peers` de tous les autres
                # projets sans un octet sur stderr, et de façon PERMANENTE dans
                # le premier cas. Un mécanisme dont le canal de retour est
                # jeté n'existe pas (L-00000136).
                cause = (
                    "un kit PLUS RECENT a ecrit le registre et celui-ci refuse "
                    "de le retrograder"
                    if _registry.read_registry_state()[1] == "schema_ahead"
                    else "l ecriture n a pas tenu apres ses essais"
                )
                print(
                    f"REGISTRY DEGRADED (not published: {cause}) — this daemon "
                    f"will not appear in other projects' /api/peers. Remedy: "
                    f"upgrade this kit, or remove {_registry.registry_path()} "
                    f"if no newer daemon is running",
                    file=sys.stderr, flush=True,
                )
        except Exception as exc:  # noqa: BLE001 - a registry write is never fatal
            print(
                f"REGISTRY DEGRADED (cannot publish: {type(exc).__name__}: {exc}) "
                f"— this daemon will not appear in other projects' /api/peers",
                file=sys.stderr, flush=True,
            )

    # Started only after the lock is confirmed OURS: the ingest thread is the
    # database's sole writer, so it must not exist in a process that just lost
    # the singleton race.
    ingest = _start_ingest_loop() if with_ingest else None
    # Same placement, same reason: the etat.db writer exists only in the process that won the singleton.
    memo = getattr(httpd, "snapshot_memo", None)
    etat = _start_etat_loop(root, getattr(memo, "verrou", None)) if with_ingest and with_etat else None

    # T-00000084: `listening` on 4318 means MORE than "we collect our own
    # traffic" — it means this process is the machine's router, and an operator
    # reading one start-up line should be told which of the two roles this
    # daemon just took. `served_elsewhere` is the other side of the same fact:
    # our own events are collected by the peer that holds the port.
    otel_role = {
        "listening": " — router for this machine",
        "served_elsewhere": " — a peer routes our events to us",
    }.get(otel_status, "")
    print(
        f"DASHBOARD DAEMON LISTENING 127.0.0.1:{port} (otel: {otel_status}"
        f"{otel_role}, ingest: {'on' if ingest is not None else 'off'}, "
        f"etat: {'on' if etat is not None else 'off'})",
        flush=True,
    )

    def retry_otel_bind() -> None:
        """V1-c: while canal B is NOT `listening`, re-try the bind on every poll
        (iteration 1, C5). A peer that dies — the other project's session ends,
        its daemon auto-stops — must not leave this project collecting nothing
        until the next SessionStart. On success the LOCK IS REWRITTEN, because
        `--status` and the dashboard read `otel` from the lock and a stale
        `served_elsewhere` there would describe a state that no longer exists.

        WHO ARBITRATES THE HANDOVER, named once (T-00000084): nobody elects a
        successor. EVERY daemon that is not `listening` retries here on its own
        30 s watchdog tick, and the arbiter is the BIND ITSELF —
        `_ExclusiveHTTPServer` (SO_EXCLUSIVEADDRUSE on Windows, plain
        exclusivity on POSIX) admits exactly one listener on 4318, the same
        way `O_CREAT|O_EXCL` admits exactly one holder of the project lock. So
        N racing daemons produce one `listening` and N-1 `served_elsewhere`,
        with no coordination and no leader. That mechanism is EXISTING and is
        not re-implemented here; what this task adds is the line below.

        RECLAIMING 4318 MAKES US THE MACHINE'S ROUTER, so the router cache is
        dropped: every entry in it was proven while another process held the
        port and the registry has necessarily moved since (the previous holder
        withdrew its own entry on the way out).

        Never raises: this runs inside the watchdog thread, whose death would
        silently disable the idle auto-stop too."""
        if not with_otel or otel["status"] == "listening":
            return
        try:
            new_httpd, new_status = _start_otel_thread()
        except Exception:  # noqa: BLE001 - a re-bind attempt may never end the thread
            return
        if new_status != "listening" or new_httpd is None:
            otel["status"] = new_status
            return
        otel["httpd"], otel["status"] = new_httpd, new_status
        try:
            _otel_receiver._reset_router_cache()
        except Exception:  # noqa: BLE001 - a cache reset never ends this thread
            pass
        print(
            f"OTEL RECEIVER RECLAIMED 127.0.0.1:{_otel_receiver._PORT} — this "
            f"daemon now holds canal B for the machine and routes foreign "
            f"events to their own project (routing cache cleared)",
            file=sys.stderr, flush=True,
        )
        try:
            write_lock(root, {**payload, "otel": new_status})
        except OSError as exc:
            print(f"DASHBOARD DAEMON DEGRADED: canal B re-bound but the lock could "
                  f"not be rewritten ({exc}) — `--status` will under-report it",
                  file=sys.stderr, flush=True)

    def watchdog() -> None:
        last_otel = _otel_activity_fingerprint()
        last_activity = time.monotonic()
        while True:
            time.sleep(poll_seconds)
            retry_otel_bind()
            ui_last = getattr(httpd, "last_activity", None)
            if ui_last is not None and ui_last > last_activity:
                last_activity = ui_last
            now_otel = _otel_activity_fingerprint()
            if now_otel != last_otel:
                last_otel = now_otel
                last_activity = time.monotonic()
            if time.monotonic() - last_activity >= idle_seconds:
                print(
                    f"dashboard daemon idle for {idle_seconds:.0f}s — auto-stop",
                    file=sys.stderr,
                    flush=True,
                )
                httpd.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True, name="idle-watchdog").start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        # `otel["httpd"]`, not the start-up local: the watchdog may have
        # re-bound canal B since (a peer died), and closing the wrong handle
        # would leave a live listener behind after this process exits.
        current_otel = otel["httpd"]
        if current_otel is not None:
            current_otel.shutdown()
            current_otel.server_close()
        # T-00000083 — withdraw from the machine registry UNCONDITIONALLY, and
        # BEFORE the ingest join below. Deliberately decoupled from both the
        # join verdict and `remove_lock_if_ours`: those two are about this
        # project's database and lock, while an entry left behind here makes a
        # DEAD daemon advertise itself to every other project on the machine.
        # The guard against removing a successor's entry is inside
        # `unregister` (it matches on our pid), not here.
        if registered_project_id is not None:
            try:
                withdrawn = _registry.unregister(registered_project_id, os.getpid())
                if not withdrawn and _registry.read_registry_state()[1] == "schema_ahead":
                    # Même canal jeté qu'à la publication. Ici False est AUSSI le
                    # cas normal (entrée déjà retirée, ou successeur légitime),
                    # donc on ne parle que du refus, qui est le cas anormal.
                    print(
                        "REGISTRY DEGRADED (not withdrawn: un kit PLUS RECENT a "
                        "ecrit le registre) — a stale entry may linger until the "
                        "next daemon garbage-collects it",
                        file=sys.stderr, flush=True,
                    )
            except Exception as exc:  # noqa: BLE001 - shutdown never raises out
                print(
                    f"REGISTRY DEGRADED (cannot withdraw: {type(exc).__name__}: "
                    f"{exc}) — a stale entry may linger until the next daemon "
                    f"garbage-collects it",
                    file=sys.stderr, flush=True,
                )
        # SOLE-WRITER BEFORE TIDINESS (plan-critic iteration 2, C10). Releasing
        # the daemon lock while the ingest thread is still inside a transaction
        # would let the next daemon start and become a SECOND writer of the same
        # database. A join that times out therefore LEAVES the lock in place and
        # says so; the next launch reclaims a lock whose holder fails the
        # liveness check (pid alive AND tokenised ping), never by its age.
        #
        # BOTH STOP SIGNALS GO OUT BEFORE THE FIRST JOIN (exec-critic, lot C of
        # T-01M51Q7GJ1B6315SFKNDAAE2P0): the two writer threads wind down at the
        # same time, and their joins share ONE bound — a degraded stop costs
        # `_INGEST_JOIN_SECONDS`, never the sum of two bounds.
        for signal_stop in (lambda: etat.signaler_arret(), lambda: ingest.stop_event.set()):
            try:
                signal_stop()
            except Exception:  # noqa: BLE001 - a missing thread or handle signals nothing
                pass
        join_deadline = time.monotonic() + _INGEST_JOIN_SECONDS
        ingest_stopped = True
        if ingest is not None:
            try:
                ingest_stopped = ingest.stop(timeout=_INGEST_JOIN_SECONDS)
            except Exception:  # noqa: BLE001
                ingest_stopped = False
        etat_stopped = True
        if etat is not None:
            try:
                etat_stopped = etat.stop(
                    timeout=min(_ETAT_JOIN_SECONDS, max(0.0, join_deadline - time.monotonic())))
            except Exception:  # noqa: BLE001
                etat_stopped = False
        if ingest_stopped and etat_stopped:
            remove_lock_if_ours(root, token)
        if not ingest_stopped:
            print(
                f"EVENT STORE DEGRADED: the ingest thread did not stop within "
                f"{_INGEST_JOIN_SECONDS:.0f}s — the daemon lock is LEFT IN PLACE "
                f"so no second writer can start (it will be reclaimed by liveness)",
                file=sys.stderr, flush=True,
            )
        if not etat_stopped:
            print(
                f"ETAT DB DEGRADED: the etat.db writer did not stop within "
                f"{_ETAT_JOIN_SECONDS:.0f}s — the daemon lock is LEFT IN PLACE "
                f"so no second writer can start (it will be reclaimed by liveness)",
                file=sys.stderr, flush=True,
            )
    return 0


# ---------------------------------------------------------------------------
# GATE B items 1+2 — detached spawn from the SessionStart hook. Fail-open:
# this function may never raise and never write to stdout.
# ---------------------------------------------------------------------------

def spawn_detached(root: Path) -> bool:
    """Launch `run_daemon` in a fully detached child. The proven combo:
    DEVNULL on all three stdio handles + DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP (Windows); start_new_session on POSIX (combo G,
    also green). True = the Popen call itself succeeded (NOT a liveness
    claim — the child dedupes/binds on its own, fail-open)."""
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    if flags:
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [sys.executable, str(HERE / "dashboard_daemon.py"), "--daemon", "--root", str(root)],
            **kwargs,
        )
        return True
    except Exception:
        return False


def ensure_running(root: Path | None = None, wait_seconds: float = _SPAWN_WAIT_SECONDS) -> dict[str, Any] | None:
    """Idempotent 'make sure a daemon exists': returns the live lock, or
    None if none could be confirmed within the bound. Never raises."""
    try:
        root = normalize_root(root) or _project_root()
        status, lock = daemon_status(root)
        if status == "alive":
            return lock
        if not spawn_detached(root):
            return None
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            time.sleep(0.2)
            status, lock = daemon_status(root)
            if status == "alive":
                return lock
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Dashboard daemon lifecycle (T-00000025 shard 2): "
        "singleton lock, detached launch, liveness, idle auto-stop."
    )
    parser.add_argument("--root", default=None, help="project root (default: derived)")
    parser.add_argument("--idle-hours", type=float, default=_IDLE_HOURS_DEFAULT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daemon", action="store_true", help="run the daemon (blocking)")
    mode.add_argument("--ensure", action="store_true", help="start a daemon if none is alive")
    mode.add_argument("--status", action="store_true", help="print the lock state as JSON")
    mode.add_argument("--stop", action="store_true", help="stop a live daemon")
    mode.add_argument("--dash", action="store_true", help="ensure a daemon and print the tokenised URL")
    args = parser.parse_args(argv)

    root = normalize_root(args.root) or _project_root()

    if args.daemon:
        return run_daemon(root, idle_seconds=args.idle_hours * 3600.0)

    if args.ensure:
        lock = ensure_running(root)
        print(json.dumps({"status": "alive" if lock else "unavailable"}))
        return 0 if lock else 2

    if args.status:
        status, lock = daemon_status(root)
        safe = dict(lock or {})
        safe.pop("token", None)  # the token belongs to /dash output only
        report: dict[str, Any] = {"status": status, "lock": safe or None}
        if status == "alive":
            report["code"] = code_state(lock)
            if report["code"] == "stale":
                report["action"] = (
                    "restart required: this daemon serves code older than the files on "
                    "disk (a running process holds its route table in memory, so new "
                    "front-end modules 404 and the page renders blank). Run --stop then --dash."
                )
        # HORS DU BLOC `alive`, ET C EST LE POINT. La premiere redaction
        # enfermait cette ligne dans `if status == "alive"`, alors que
        # `_empreinte_locale` separe volontairement les deux moities :
        # `events_db_octets` se lit SANS verrou. Consequence mesuree par le
        # binome — le poids du store restait invisible EXACTEMENT quand le
        # pilote regarde, c est-a-dire apres un `--stop` ou le matin avant
        # d ouvrir le dashboard. Et mon propre banc exercait alors un chemin que
        # la CLI ne produisait jamais : le defaut que le temoin de cablage avait
        # ete ecrit pour interdire, reste ouvert sur l autre moitie.
        report["empreinte"] = _empreinte_locale(root, lock)
        demons = _demons_du_poste()
        report["demons_du_poste"] = demons
        # Calibrated on the ONE daemon this probe can vouch for (it answered the
        # tokenised ping), shown with its pid: `vu: false` = the relevé is blind
        # to at least one launch form; `vu: true` says only that THIS daemon is
        # seen, never that the relevé is complete. null = nothing to calibrate on
        # (no live daemon for this root, or `ps` unreadable). A daemon that dies
        # between the ping and `ps` reads `vu: false`: recount by hand first.
        report["demons_du_poste_etalon"] = (
            {"pid": lock["pid"], "vu": lock["pid"] in {d["pid"] for d in demons}}
            if status == "alive" and lock is not None and demons is not None else None)
        print(json.dumps(report))
        return 0

    if args.stop:
        status, lock = daemon_status(root)
        if status != "alive" or lock is None:
            print(json.dumps({"status": "not-running"}))
            return 0
        result = stop_and_release(root, lock)
        print(json.dumps(result))
        if result["status"] != "stopped":
            print(f"dashboard daemon pid {result['pid']} survived SIGTERM for "
                  f"{result['waited_seconds']:.0f}s - its lock is KEPT while it answers its ping (silent: --stop "
                  f"answers not-running and --ensure/--dash may take its lock, T-00001120); read its command line "
                  f"(ps -p {result['pid']} -o command=, or the Task Manager on Windows) before ending it", file=sys.stderr)
            return 2
        return 0

    # --dash
    lock = ensure_running(root)
    if lock is None:
        print("dashboard unavailable: no daemon could be started (see --daemon on a terminal for details)", file=sys.stderr)
        return 2
    if code_state(lock) == "stale":
        # T-00000040: --dash is idempotent by design (it reuses a live daemon),
        # which is exactly how a stale process survives an upgrade unnoticed.
        # Restart it here rather than handing back a URL that renders blank.
        print("dashboard daemon was serving stale code — restarting it", file=sys.stderr)
        if stop_and_release(root, lock)["status"] != "stopped":
            print(f"dashboard daemon pid {lock['pid']} serves stale code and survived "
                  f"SIGTERM - its lock is KEPT, no second daemon started", file=sys.stderr)
            return 2
        lock = ensure_running(root)
        if lock is None:
            print("dashboard unavailable after restart attempt (see --daemon on a terminal)", file=sys.stderr)
            return 2
    url = f"http://127.0.0.1:{lock['port']}/?token={lock['token']}"
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
