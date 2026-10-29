# tasks_stockage.py — PARTIE de `tasks.py` (T-00000788) : le STORE du board —
# chemins, verrou `board_lock`, `commit_stores`, chargement validé, écriture
# atomique. Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


class BoardError(Exception):
    """Unknown task id, or a store that fails validation."""


def numeric_id(tid: str) -> int:
    """The numeric value of a ``T-<n>`` id, for sorting and duplicate
    detection — never the string itself, so a zero-padding change (3-digit
    legacy ids vs 8-digit new ones) never reorders or re-collides tasks. ASCII digits ONLY (`[0-9]`, E-26
    closing pass): a Unicode ``\\d`` read ``T-١٢`` as 12; the look-behind stays Unicode, so ``T-١12`` is refused."""
    match = re.search(r"(?<!\d)([0-9]{1,15})\Z", tid or "")
    if not match:
        raise BoardError(f"malformed id {tid!r}: expected a trailing numeric component")
    return int(match.group(1))


# THE `P-<ULID>` ID FORM (T-00000726, form A, S-00003552) — PURE READING, NO SIBLING
# NEEDED: these names load neither `record_id.py` nor the ULID generator, so a copy
# of the CLI without them reads a mixed board exactly as it reads a legacy one.
# They are COPIED, never imported, into specs.py and ledger.py (T-00001039, P-PAR
# parity). Allocation is `record_id.mint`, reached through `record_id_module()`.
ULID_BODY = "[0-9A-HJKMNP-TV-Z]{26}"
_ULID_ID = re.compile(r"\A[TSL]-(" + ULID_BODY + r")\Z")


def is_ulid_id(tid: str) -> bool:
    """True for a ``P-<ULID>`` id (P in T/S/L, 26 UPPER-CASE Crockford symbols),
    anchored at BOTH ends: ``T-<ULID>`` followed by a newline, a lower-case body
    or a 25/27-symbol body is not one."""
    return _ULID_ID.match(tid or "") is not None


def sort_key(tid: str) -> tuple[int, int | str]:
    """Two-tier ORDER key: ``(0, n)`` for a legacy numeric id, ``(1, ulid)`` for
    a ULID. Every ULID sorts after every legacy id; ULIDs order among themselves
    by time (Crockford is monotonic in ASCII), legacy ids by NUMERIC value as
    before. A malformed id still raises ``BoardError`` through ``numeric_id``."""
    m = _ULID_ID.match(tid or "")
    return (1, m.group(1)) if m else (0, numeric_id(tid))


def identity_key(tid: str) -> tuple[int, int | str]:
    """IDENTITY key: two ids name the same record iff their keys are equal — a
    legacy id by its numeric value (``T-012`` is ``T-00000012``), a ULID by its
    exact body. Same value as ``sort_key`` today; a separate name so that every
    caller says WHICH question it asks (order, or sameness)."""
    return sort_key(tid)


# THE ALLOCATION SIBLING (T-00000726, C2 switch-over). Every NEW task id is
# `record_id.mint("T")` — no stored counter, so two branches never mint the same
# id. ONLY the allocation sites (`new_task`, `create_linked_task`, and the V3
# bridge that mints the id it reserves, T-00001060) call this accessor, never a
# read path: a copy of the CLI without `record_id.py` still
# reads, lists, starts, blocks and closes (M33), and refuses only to ALLOCATE,
# naming the remedy. Loaded BY PATH (never `sys.path`), under ONE `sys.modules`
# name shared with the twins of specs.py and ledger.py, reused only when it is the
# expected file, registered before `exec_module` and withdrawn if that raises.
RECORD_ID_REMEDE = "git checkout -- .agents/bin/record_id.py"
_RECORD_ID_NOM = "_cadre_record_id_bin"


def record_id_module() -> Any:
    """The allocation sibling `record_id.py`, loaded on first use. Absent ⇒
    ``BoardError`` naming the remedy, raised before anything is written."""
    chemin = Path(__file__).resolve().with_name("record_id.py")
    existant = sys.modules.get(_RECORD_ID_NOM)
    fichier = getattr(existant, "__file__", None)
    if existant is not None and fichier and Path(fichier).resolve() == chemin:
        return existant
    if not chemin.is_file():
        raise BoardError(
            f"cannot allocate a new task id: the allocation sibling {chemin} is ABSENT "
            f"(every new record is a P-<ULID> and there is no counter to fall back on) — "
            f"restore it: `{RECORD_ID_REMEDE}`"
        )
    import importlib.util

    spec = importlib.util.spec_from_file_location(_RECORD_ID_NOM, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RECORD_ID_NOM] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if existant is not None:
            sys.modules[_RECORD_ID_NOM] = existant
        else:
            sys.modules.pop(_RECORD_ID_NOM, None)
        raise
    return module


def force_utf8_stdio() -> None:
    """Windows consoles default to cp1252, which cannot encode → or the state
    emoji — the board is UTF-8 by construction, so make stdio match."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def store_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / STORE_REL / STORE_NAME


def view_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / VIEW_REL / VIEW_NAME


def normalize_root(value: str | os.PathLike[str]) -> str:
    """Accept a Git-Bash/MSYS root (``/c/Users/...``) as well as a native one,
    translating the former to ``c:/Users/...`` when THAT is what exists.

    Copied (not imported) from dashboard_daemon.normalize_root — L-00000063:
    every hook exports the root through ``cygpath -u``, and a bare ``Path()``
    does not resolve ``/c/...``. Without this the board lock and the
    POST_TASK_DONE lock would resolve under a nonexistent tree, and two hooks
    would take two locks on two paths, losing mutual exclusion in silence. It is
    a no-op on a native root (the path already exists), so it is inert for every
    in-process caller passing a resolved ``--root``."""
    text = str(value)
    if Path(text).exists():
        return text
    match = re.match(r"^/([A-Za-z])/(.*)$", text)
    if match:
        alt = f"{match.group(1)}:/{match.group(2)}"
        if Path(alt).exists():
            return alt
    return text


def lock_path(root: str | os.PathLike[str], name: str | None = None) -> Path:
    return Path(root) / VIEW_REL / (name or LOCK_NAME)


def _lock_poll_sleep() -> None:
    """The poll nap of ``board_lock``, extracted to a module function so a
    concurrency net can wrap it WITHOUT any seam in production code — the same
    shape as specs.py/ledger.py's (T-00000189, F3; here T-00000730). Called only
    while spinning for a lock another holder owns; production never patches it.
    ``time`` and ``_LOCK_POLL_SECONDS`` are free names of the façade."""
    time.sleep(_LOCK_POLL_SECONDS)


@contextmanager
def board_lock(
    root: str | os.PathLike[str],
    timeout_seconds: float | None = None,
    name: str | None = None,
) -> Iterator[None]:
    """Hold a persistent local lock, re-entering within one thread.

    ``name`` selects WHICH lock file under ``.agents/state/local/``: the board
    (``TASKS.lock``, default) or the post-done commit (``POST_TASK_DONE.lock``,
    T-00000189). ``timeout_seconds=None`` reads the module bound in the BODY —
    the same replaceable shape specs.py/ledger.py's ``store_lock`` exposes.
    Both additions are inert for every existing caller: none passes a second
    positional argument (surveyed before the change).

    A LINKED DIRECTORY IS NEVER FOLLOWED (security review, advisory — the
    control of ``ecrire_json_local``): ``.agents``, ``state``, ``local`` or the
    lock file itself a symbolic link ⇒ ``BoardError`` before ``open("a+b")``."""
    if timeout_seconds is None:
        timeout_seconds = _LOCK_TIMEOUT_SECONDS
    path = lock_path(root, name)
    for lien in (path, path.parent, path.parent.parent, path.parent.parent.parent):
        if lien.is_symlink():
            raise BoardError(f"{path.name} not opened: {lien} is a symbolic link, never followed — REMEDY: replace "
                             f"the link by a real directory (copy its target's content, then move the copy into "
                             f"place), or run from the repository where the target lives")
    key = os.path.normcase(str(path.resolve()))
    depths = getattr(_BOARD_LOCK_DEPTH, "paths", None)
    if depths is None:
        depths = {}
        _BOARD_LOCK_DEPTH.paths = depths
    if depths.get(key, 0):
        depths[key] += 1
        try:
            yield
        finally:
            depths[key] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise BoardError(f"timed out waiting for board lock {path}") from exc
                _lock_poll_sleep()
        depths[key] = 1
        yield
    finally:
        depths.pop(key, None)
        try:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def commit_stores(root: str, lock_timeout: float | None = None) -> str:
    """The LOCK leg of the post-done commit (T-00000189, volet 1).

    Serialises the three-store git commit under a DEDICATED lock
    (``POST_TASK_DONE.lock``, distinct from the board's) so two closures racing
    at once no longer let one commit swallow the other in silence — measured 6/6
    on the pre-change code. It runs the shell SECTION leg
    (``post-task-done-index.sh --commit-section``) INSIDE the lock and relays
    that leg's single token, so the external leg can classify the outcome.
    ALWAYS returns a token and never raises: the hook is advisory and must
    exit 0.

    BASH IS RESOLVED, never the bare string ``"bash"`` (L-00000166; precedent
    dashboard._bash_executable): CreateProcess searches System32 first and finds
    the WSL relay shim, which dies rc=1 and would degrade the commit on every
    Windows box, silently. A resolution UNDER System32 is rejected too. If no
    usable bash resolves, this leg degrades to ``bash-introuvable`` and the
    external leg — itself bash — commits without the lock: refusing would make
    the commit of the three sources of truth PROBABILISTIC where it is only
    concurrent today.
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash or "system32" in bash.replace("\\", "/").lower():
        return "bash-introuvable"
    script = Path(root) / ".agents" / "bin" / "post-task-done-index.sh"
    try:
        with board_lock(root, timeout_seconds=lock_timeout, name=POST_TASK_DONE_LOCK):
            proc = subprocess.run(
                [bash, str(script), "--commit-section", str(root)],
                capture_output=True,
                text=True,
            )
            lines = (proc.stdout or "").strip().splitlines()
            return lines[-1] if lines else "failed"
    except BoardError:
        # The lock was held past the bound: another closure owns it and is
        # presumably committing. NOT a self-commit — that would defeat the lock.
        return "locked-out"
    except Exception:
        return "failed"


def _validate_sync_extensions(path: Path, data: dict[str, Any]) -> None:
    outbox = data.get("sync_outbox")
    correlations = data.get("sync_correlations")
    if not isinstance(outbox, list):
        raise BoardError(f"{path}: sync_outbox must be a list")
    if not isinstance(correlations, dict):
        raise BoardError(f"{path}: sync_correlations must be an object")
    for operation_id, correlation in correlations.items():
        if not isinstance(operation_id, str) or not operation_id:
            raise BoardError(f"{path}: sync_correlations keys must be non-empty operation ids")
        if not isinstance(correlation, dict) or set(correlation) != {"board_task_id", "tombstoned"}:
            raise BoardError(
                f"{path}: sync_correlations[{operation_id!r}] must contain exactly "
                "board_task_id and tombstoned"
            )
        if not isinstance(correlation["board_task_id"], str) or not isinstance(
            correlation["tombstoned"], bool
        ):
            raise BoardError(f"{path}: invalid sync correlation {operation_id!r}")
    for index, intent in enumerate(outbox):
        refus = _refus_intent(intent, correlations)
        if refus is not None:
            raise BoardError(f"{path}: sync_outbox[{index}] {refus}")


def _refus_intent(intent: Any, correlations: dict[str, Any] | None) -> str | None:
    """Why ONE outbox entry fails the checks of `load()`, or ``None`` — the SAME checks, in the same order, for an
    entry of TASKS.json and for the intent of an O2 file (T-00001058, D4 (f) of T-00001053's closing: a file intent
    is validated like an inline one, `expires_at: "x"` included). ``correlations=None`` skips the correlation test:
    a file intent whose key the text lost is an ORPHAN, re-indexed from its envelope, not an invalid entry."""
    required = {
        "operation_id",
        "event_kind",
        "affected_task_ids",
        "before",
        "after",
        "revision_sha256",
        "attempt",
        "lease",
    }
    if not isinstance(intent, dict) or not required.issubset(intent):
        return "is missing required fields"
    operation_id = intent["operation_id"]
    if not isinstance(operation_id, str) or (correlations is not None and operation_id not in correlations):
        return "has no valid correlation"
    if intent["event_kind"] not in SYNC_EVENT_KINDS:
        return "has an unknown event_kind"
    affected = intent["affected_task_ids"]
    if not isinstance(affected, list) or not affected or not all(isinstance(item, str) for item in affected):
        return "has invalid affected_task_ids"
    if not isinstance(intent["attempt"], int) or intent["attempt"] < 0:
        return "has invalid attempt"
    if not re.fullmatch(r"[0-9a-f]{64}", str(intent["revision_sha256"])):
        return "has invalid revision_sha256"
    for snapshot_name in ("before", "after"):
        snapshot = intent[snapshot_name]
        if snapshot is not None and (
            not isinstance(snapshot, dict) or set(snapshot) != set(SYNC_SNAPSHOT_FIELDS)
        ):
            return f"has invalid {snapshot_name} snapshot"
    if intent["revision_sha256"] != revision_sha256(intent["before"], intent["after"]):
        return "revision_sha256 does not match snapshots"
    lease = intent["lease"]
    if lease is not None and (
        not isinstance(lease, dict)
        or set(lease) != {"owner", "token", "expires_at"}
        or not isinstance(lease["owner"], str)
        or not isinstance(lease["token"], str)
        or not isinstance(lease["expires_at"], (int, float))
    ):
        return "has invalid lease"
    return None


def _ensure_sync_extensions(data: dict[str, Any]) -> None:
    data.setdefault("sync_outbox", [])
    data.setdefault("sync_correlations", {})


# THE O2 OUTBOX (T-00001058, S-00003918 (1)) — ONE FILE PER INTENT, VERSIONED. A pending intent lives in
# `.agents/state/board/sync_outbox/<order:20 digits>-<operation_id>.json`, ONE sorted JSON object
# `{"correlation": {board_task_id, tombstoned}, "intent": {…}}` (indent 2, LF, no `merge=union`), committed with
# TASKS.json by the stores hook: two clones that each enqueue MERGE their intents instead of keeping one side's
# list (F3, measured). TASKS.json no longer carries `sync_outbox`: `load()` ASSEMBLES `data["sync_outbox"]` (the
# VIEW), the one key every reader — claim, ack, release, drain, spill, the V3 bridge — keeps reading. Two LOCAL
# folders, git-ignored (`.agents/state/local/`, next to the spill file): the lots of a save in flight, and the
# quarantine. An operation id names its file, so it must match `[0-9A-Za-z][0-9A-Za-z._-]*` (no `/`, no `..`).
_NOM_INTENT = re.compile(r"\A(\d{20})-([0-9A-Za-z][0-9A-Za-z._-]{0,127})\.json\Z")
# READ CAPS (closing security advisory): an intent file arrives by `git pull` from another clone, so at most
# cap + 1 bytes are ever read; above it, a NAMED refusal — out of the view, quarantined like any unreadable file.
# One intent holds at most two snapshots of one task: the largest task of the kit's real board is 29 634 bytes
# (measured 2026-10-11), so 4 MiB is a margin of more than 60. A lot holds EVERY new intent of one save — a spill
# put back at once has no fixed bound — so its cap is far wider; a lot above it (thousands of intents of the
# largest size in ONE save) would be quarantined, its intents kept in that file, not delivered.
_PLAFOND_INTENT_OCTETS = 4 * 1024 * 1024
_PLAFOND_LOT_OCTETS = 512 * 1024 * 1024
# CUMULATIVE CAPS (M3, T-01M4MC28CAKFE8YZ2W4WN7DV2C): one read takes at most the first 10 000 intent files by order key
# and 128 MiB (legitimate, measured: at most threshold + slice = 250 per clone, an envelope at most 2 × 29 634 bytes) —
# beyond, a window (`_intents_retenus`), the rest left in place, one stderr line; the quarantine holds at most 100 `.n`
# copies per name, 1 000 entries and 256 MiB — beyond, « quarantaine IMPOSSIBLE, laissé en place ».
_PLAFOND_INTENTS_NOMBRE = 10_000
_PLAFOND_INTENTS_OCTETS_CUMULES = 128 * 1024 * 1024
_PLAFOND_QUARANTAINE_COPIES = 100
_PLAFOND_QUARANTAINE_ENTREES = 1_000
_PLAFOND_QUARANTAINE_OCTETS = 256 * 1024 * 1024


def _lire_plafonne(fichier: Any, plafond: int) -> bytes:
    """At most ``plafond`` + 1 bytes of an open file: above ``plafond``, ``ValueError`` (the readers' unreadable)."""
    octets = fichier.read(plafond + 1)
    if len(octets) > plafond:
        raise ValueError(f"above the {plafond}-byte cap")
    return octets


def _dossier_outbox(root: str | os.PathLike[str]) -> Path:
    return Path(root) / STORE_REL / "sync_outbox"


def _dossier_lots(root: str | os.PathLike[str]) -> Path:
    return lock_path(root).with_name("sync_outbox_lots")


def _dossier_quarantaine(root: str | os.PathLike[str]) -> Path:
    return lock_path(root).with_name("sync_outbox_quarantaine")


class _BoardCharge(dict):
    """What `load()` returns: a plain mapping for every reader, carrying in ``vue_o2`` the O2 view it was assembled
    from — the operation ids and the file bytes it READ — so that `save()` removes the files of the intents that LEFT
    the list (view read − list written), NEVER "folder − list": a save from data that never saw a file leaves it
    alone. ``copy.deepcopy`` keeps it; ``dict(data)`` or a fresh dict drops it, and such a save removes nothing.
    ``ressuscites`` holds the ids `resurrection_refusal` saw at that load: a save whose set is a STRICT subset of
    it — one `delete` per id, the remedy — passes; a fresh dict has none and is refused on any resurrection.
    ``vue_dossier`` (T-00001009, folder form only): the bytes READ per record file and the tombstones among them, so
    that a save writes the files whose bytes changed and a tombstone for every id that LEFT (never "folder − data")."""

    vue_o2: dict[str, Any] | None = None
    ressuscites: frozenset[str] | None = None
    vue_dossier: dict[str, Any] | None = None


def _octets_enveloppe(enveloppe: dict[str, Any]) -> bytes:
    return (json.dumps(enveloppe, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _refus_enveloppe(enveloppe: Any, op_du_nom: str) -> str | None:
    """Why an O2 file does not hold ONE valid intent, or ``None``: the envelope's two keys, its correlation's shape,
    the `load()` checks of the intent (`_refus_intent`), and the operation id its NAME announces."""
    if not isinstance(enveloppe, dict) or set(enveloppe) != {"correlation", "intent"}:
        return "is not an intent envelope {correlation, intent}"
    correlation = enveloppe["correlation"]
    if (
        not isinstance(correlation, dict)
        or set(correlation) != {"board_task_id", "tombstoned"}
        or not isinstance(correlation["board_task_id"], str)
        or not isinstance(correlation["tombstoned"], bool)
    ):
        return "has an invalid correlation"
    refus = _refus_intent(enveloppe["intent"], None)
    if refus is not None:
        return refus
    if enveloppe["intent"]["operation_id"] != op_du_nom:
        return "does not hold the operation its name announces"
    return None


def _lire_definitifs(root: str | os.PathLike[str], ecart: dict[str, int] | None = None
                     ) -> list[tuple[int, str, bytes | None, Any, str | None]]:
    """Every file of the O2 folder NAMED like an intent, in name order: ``(order key, name, bytes, envelope,
    refusal)`` — envelope ``None`` and the refusal saying why when the file cannot be read or fails the checks.
    Opened like the spill file (`_ouvrir_sans_lien`: no final symlink, a regular file only). `Path.glob("*.json")`,
    never a recursive walk; a `.json` not named like an intent is not ours and is left alone. The folder itself as a
    link is refused first (`_refus_liens`, M2). M3: only the window of `_intents_retenus` is read; the files beyond it
    stay in place, out of the view, one stderr line at every read, and ``ecart["nombre"]`` gets their count."""
    _refus_liens(root)
    dossier = _dossier_outbox(root)
    if not dossier.is_dir():
        return []
    retenus, ecartes = _intents_retenus(dossier)
    if ecartes:
        if ecart is not None:
            ecart["nombre"] = ecartes
        print(f"TASKS: sync_outbox — {ecartes} fichier(s) d'intent au-delà du plafond de lecture "
              f"({_PLAFOND_INTENTS_NOMBRE} fichiers, {_PLAFOND_INTENTS_OCTETS_CUMULES} octets), laissé(s) en place hors "
              "de la vue : un intent mis en file depuis ne part pas tant que le dossier dépasse ce plafond (`git log -- "
              ".agents/state/board/sync_outbox/`)", file=sys.stderr)
    lus: list[tuple[int, str, bytes | None, Any, str | None]] = []
    for chemin in retenus:
        match = _NOM_INTENT.match(chemin.name)
        if match is None:
            continue
        try:
            with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
                octets = _lire_plafonne(fichier, _PLAFOND_INTENT_OCTETS)
            enveloppe = json.loads(octets.decode("utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            lus.append((int(match.group(1)), chemin.name, None, None, f"is unreadable ({exc})"))
            continue
        refus = _refus_enveloppe(enveloppe, match.group(2))
        lus.append((int(match.group(1)), chemin.name, octets, None if refus else enveloppe, refus))
    return lus


def _lire_lots(root: str | os.PathLike[str]) -> list[tuple[Path, dict[str, Any] | None]]:
    """The lots left by a save that did not finish, in name order: ``(path, lot)``, lot ``None`` when unreadable
    or out of shape — ``{"cible": <sha256 of the TASKS.json bytes that save publishes>, "intents": [{"nom",
    "enveloppe"}, …]}``, at least one intent, each name and envelope valid. A FOLDER-FORM lot (T-00001009,
    ``"forme": "dossier"``) is judged by `_lot_dossier_valide`: its own sha256 validates it."""
    dossier = _dossier_lots(root)
    if not dossier.is_dir():
        return []
    lus: list[tuple[Path, dict[str, Any] | None]] = []
    for chemin in sorted(dossier.glob("*.json")):
        try:
            with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
                lot = json.loads(_lire_plafonne(fichier, _PLAFOND_LOT_OCTETS).decode("utf-8"))
        except (OSError, ValueError, RecursionError):
            lus.append((chemin, None))
            continue
        if isinstance(lot, dict) and lot.get("forme") == "dossier":  # T-00001009 : validé par sa propre empreinte
            lus.append((chemin, lot if _lot_dossier_valide(lot) else None))
            continue
        entrees = lot.get("intents") if isinstance(lot, dict) else None
        valide = bool(isinstance(lot, dict) and isinstance(lot.get("cible"), str) and isinstance(entrees, list)
                      and entrees)
        for entree in entrees if valide else ():
            nom = entree.get("nom") if isinstance(entree, dict) else None
            match = _NOM_INTENT.match(nom) if isinstance(nom, str) else None
            if match is None or _refus_enveloppe(entree.get("enveloppe"), match.group(2)) is not None:
                valide = False
                break
        lus.append((chemin, lot if valide else None))
    return lus


def _lot_valide(lot: dict[str, Any], empreinte: str, correlations: dict[str, Any]) -> bool:
    """A lot is VALIDATED when the save that wrote it reached TASKS.json: the sha256 of TASKS.json on disk is its
    target, or EVERY operation id of the lot is in the text's `sync_correlations` — written by the SAME replace
    (réserve C3 : « the task carries the `after` » would validate a lot whose mutation was replayed by hand)."""
    ops = [entree["enveloppe"]["intent"]["operation_id"] for entree in lot["intents"]]
    return lot["cible"] == empreinte or all(op in correlations for op in ops)


def _assembler_vue(root: str | os.PathLike[str], data: _BoardCharge, octets: bytes) -> None:
    """THE VIEW (T-00001058 step 2), read-only and TOLERANT: ``data["sync_outbox"]`` becomes the intents still IN
    LINE (a TASKS.json written before O2 — they come first, and one also present as a file PRIMES at that file's
    rank), then the definitive files and the VALIDATED lots, by order key, one entry per operation id (lowest key).
    An ORPHAN — a file whose key the text lost (a merge resolved that hunk on the other side, S-00003917 (2)) — is
    RE-INDEXED in memory from its envelope, and the next `save()` writes the key back, saying so. An unreadable or
    invalid file, and a lot not validated, stay OUT of the view: nothing new raises at a read (doctrine « valide à
    l'écriture, tolère à la lecture »); the next save quarantines the file and the lot."""
    correlations = data["sync_correlations"]
    en_ligne = data["sync_outbox"]
    cles: dict[str, tuple[int, dict[str, Any], dict[str, Any]]] = {}
    fichiers: dict[str, bytes] = {}
    illisibles: set[str] = set()
    for cle, nom, brut, enveloppe, _refus in _lire_definitifs(root):
        if enveloppe is None:
            illisibles.add(nom)
            continue
        fichiers[nom] = brut
        op = enveloppe["intent"]["operation_id"]
        if op not in cles or cle < cles[op][0]:
            cles[op] = (cle, enveloppe["intent"], enveloppe["correlation"])
    lots = _lire_lots(root)
    if lots:
        empreinte = hashlib.sha256(octets).hexdigest()
        for _chemin, lot in lots:
            if lot is None or not (lot.get("forme") == "dossier" or _lot_valide(lot, empreinte, correlations)):
                continue
            for entree in lot["intents"]:
                cle, intent = int(entree["nom"][:20]), entree["enveloppe"]["intent"]
                if intent["operation_id"] not in cles or cle < cles[intent["operation_id"]][0]:
                    cles[intent["operation_id"]] = (cle, intent, entree["enveloppe"]["correlation"])
    par_op = {intent["operation_id"]: intent for intent in en_ligne}
    vue = [intent for intent in en_ligne if intent["operation_id"] not in cles]
    reindexes: list[str] = []
    for op, (_cle, intent, correlation) in sorted(cles.items(), key=lambda paire: (paire[1][0], paire[0])):
        if op in par_op:
            vue.append(par_op[op])
            continue
        if op not in correlations:
            correlations[op] = dict(correlation)
            reindexes.append(op)
        vue.append(intent)
    data["sync_outbox"] = vue
    data.vue_o2 = {
        "racine": os.path.normcase(str(Path(root).resolve())),
        "ops": {intent["operation_id"] for intent in vue},
        "fichiers": fichiers,
        "illisibles": illisibles,
        "reindexes": reindexes,
    }


def load(root: str | os.PathLike[str]) -> dict[str, Any]:
    """Read and VALIDATE the store. A malformed board raises — it never
    degrades into silently losing a task. The O2 outbox (T-00001058) is assembled
    AFTER the entries still in line are validated, so their refusals keep their
    index: `_assembler_vue` adds only intents its readers already validated.

    IN THE FORM IT FINDS (T-00001009, `store_form`): the folder of records ⇒
    `_load_dossier` (the records, a validated lot overlaid, the correlations
    projected IN MEMORY, then the SAME validation, `_valider_board`); both forms ⇒
    this monolith, read only if the folder holds the same board
    (`_comparer_deux_formes`); a monolith or no board ⇒ this path, unchanged."""
    forme = store_form(root)
    if forme == "dossier":
        return _load_dossier(root)
    path = store_path(root)
    if not path.exists():
        return {"tasks": []}
    octets = path.read_bytes()
    try:
        data = json.loads(octets.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BoardError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise BoardError(f"{path}: expected an object with a 'tasks' list")

    _ensure_sync_extensions(data)
    _validate_sync_extensions(path, data)
    data = _BoardCharge(data)
    _assembler_vue(root, data, octets)
    data.ressuscites = frozenset(_ids_ressuscites(data))  # APRÈS la vue : une clé ré-indexée compte
    _valider_board(path, data)
    if forme == "les deux":
        _comparer_deux_formes(root, data)
    return data


def _valider_board(path: Path, data: dict[str, Any], lieux: dict[str, Path] | None = None) -> None:
    """THE VALIDATION OF `load()`, shared by its two forms (T-00001009): each per-task refusal names ``path`` — or, in
    the folder form, the task's record file (``lieux``: id → file) —, then the epic shape, the running-group rule, and
    the drop of a residual ``next_id``. In the monolith form the messages are those of before, byte for byte."""
    seen_ids: set[str] = set()
    seen_numeric: dict[int, str] = {}
    for i, task in enumerate(data["tasks"]):
        if not isinstance(task, dict):
            raise BoardError(f"{path}: task #{i} is not an object")
        lieu = lieux.get(task.get("id"), path) if lieux else path
        missing = [f for f in ("id", "state", "task") if not task.get(f)]
        if missing:
            raise BoardError(f"{lieu}: task #{i} is missing {', '.join(missing)}")
        if task["state"] not in STATES:
            raise BoardError(
                f"{lieu}: task {task['id']} has state {task['state']!r}; expected one of {', '.join(STATES)}"
            )
        # ABSENT is the normal shape (every task minted before T-00000184), so
        # this validates presence only: a legacy entry must keep loading. Same rule for
        # `responsable`, the HUMAN in charge (T-01M54GEHJBGA5996W0T48JXNQ4): shape only.
        for champ in ("chantier", "responsable"):
            if champ in task and not isinstance(task[champ], str):
                raise BoardError(f"{lieu}: task {task['id']} has a non-string {champ} ({task[champ]!r})")
        # PRESENCE ONLY, and the REFERENT IS NOT REQUIRED TO EXIST: a store whose
        # blocker was deleted or purged long ago must stay readable — a read
        # surface the SessionStart hooks consume cannot start refusing history.
        # `delete`/`purge` clean the dangling link when they see it (and say so);
        # a `done` never matches one, so it simply releases nothing.
        if "blocked_on" in task and (
            not isinstance(task["blocked_on"], str) or not task["blocked_on"]
        ):
            raise BoardError(
                f"{lieu}: task {task['id']} has an invalid blocked_on "
                f"({task['blocked_on']!r}); expected a non-empty task id"
            )
        # PRESENCE AND SHAPE ONLY (T-00000188), like `chantier` above: the
        # ADMISSION of a path is checked at the DECLARATION, where the pilot can
        # still fix the string. A read surface the SessionStart hooks consume
        # must never start refusing a store it accepted yesterday.
        if "writeset" in task and (
            not isinstance(task["writeset"], list)
            or not all(isinstance(p, str) for p in task["writeset"])
        ):
            raise BoardError(
                f"{lieu}: task {task['id']} has an invalid writeset "
                f"({task['writeset']!r}); expected a list of path strings"
            )
        if "parallel_group" in task and not isinstance(task["parallel_group"], str):
            raise BoardError(
                f"{lieu}: task {task['id']} has a non-string parallel_group "
                f"({task['parallel_group']!r})"
            )
        # PRESENCE AND SHAPE ONLY, and THE REFERENTS ARE NOT REQUIRED TO EXIST —
        # same rule as `blocked_on` and `depends_on` above, same reason: a read
        # surface the SessionStart hooks consume must never start refusing a
        # store it accepted yesterday. A dangling id here is HARMLESS by
        # construction: `reopen` looks each one up and SKIPS the ones it cannot
        # restore, naming why, rather than trusting the list.
        if "released_on_done" in task and (
            not isinstance(task["released_on_done"], list)
            or not all(isinstance(d, str) and d for d in task["released_on_done"])
        ):
            raise BoardError(
                f"{lieu}: task {task['id']} has an invalid released_on_done "
                f"({task['released_on_done']!r}); expected a list of non-empty task ids"
            )
        # PRESENCE AND SHAPE ONLY, like `blocked_on` above, and THE REFERENT IS
        # NOT REQUIRED TO EXIST for the same reason: `delete`/`purge` clean the
        # dangling link when they see it (and say so), and a read surface the
        # SessionStart hooks consume cannot start refusing a store it accepted
        # yesterday.
        #
        # NO CYCLE DETECTION HERE, AND THAT IS THE POINT (T-00000530). The guard
        # belongs to `set_depends`, which proves acyclicity BEFORE writing, so no
        # `tasks.py` can ever mint a cycle. Putting it here instead would make a
        # hand-edited cycle unloadable for EVERY verb — `list`, `done`, and the
        # very `depends --clear` that repairs it. That is the defect the parallel
        # group guard already cost this repo once (see the note above `save`), and
        # a guard that forbids its own remedy is worse than the cycle. A cycle
        # that arrives by hand therefore LOADS; `core-scripts/plan_waves.py` refuses it
        # loudly, names the path and names the command that clears it.
        if "depends_on" in task and (
            not isinstance(task["depends_on"], list)
            or not all(isinstance(d, str) and d for d in task["depends_on"])
        ):
            raise BoardError(
                f"{lieu}: task {task['id']} has an invalid depends_on "
                f"({task['depends_on']!r}); expected a list of non-empty task ids"
            )
        # THE SHAPE OF `depends_motif` IS CHECKED, ITS HISTORY IS NOT. When
        # present it must map a SUBSET of `depends_on` to non-empty single-line
        # strings — same content bound as the write, so a hand-edited store
        # cannot introduce what the verb refuses. Never REQUIRED: a legacy edge
        # carries no motif and must still load. An EMPTY dict `{}` is accepted
        # (an empty key set is vacuously a subset), so load is NOT the net
        # against a minted-empty key — the write guard and its bench are.
        if "depends_motif" in task:
            dm = task["depends_motif"]
            declared = set(task.get("depends_on") or [])
            if not isinstance(dm, dict) or not set(dm).issubset(declared) or not all(
                isinstance(v, str) and v.strip() and len(v.splitlines()) <= 1
                for v in dm.values()
            ):
                raise BoardError(
                    f"{lieu}: task {task['id']} has an invalid depends_motif "
                    f"({task['depends_motif']!r}); expected a dict mapping a subset "
                    f"of depends_on to non-empty single-line strings"
                )
        if task["id"] in seen_ids:
            raise BoardError(f"{lieu}: duplicate task id {task['id']}")
        seen_ids.add(task["id"])
        # A ULID id has NO numeric value to collide on (T-00000726): the EXACT-id
        # check above is its whole duplicate guard, which is why this `continue`
        # sits BELOW it — a ULID listed twice is refused, never skipped.
        if is_ulid_id(task["id"]):
            continue
        n = numeric_id(task["id"])
        if n in seen_numeric:
            raise BoardError(
                f"{lieu}: numeric id collision — {seen_numeric[n]} and {task['id']} both resolve to {n}"
            )
        seen_numeric[n] = task["id"]
    # THE EPIC REGISTRY AND FIELD (T-00001043): PRESENCE AND SHAPE ONLY, the referent
    # NOT required, and no `setdefault` — a store with no epic keeps its exact shape.
    refus_epic = epic_shape_refusal(data)
    if refus_epic is not None:
        raise BoardError(f"{path}: {refus_epic}")
    # SEVERAL RUNNING TASKS ARE LEGITIMATE (T-01M5F7286N1EYGXAXA5244X86B, pilot decision
    # S-01M5DBTHMEAEXGD93Q284GJPJE): neither this read nor `save()` refuses a set of
    # running tasks any more — the single-group rule of T-00000188 is retired, with the
    # demotion `start` used to perform. A group stays the disjunction proof of `parallel`.

    # NO COUNTER (T-00000726): an id is minted, never counted. A store written
    # before the switch-over still carries `next_id`: TOLERATED, and dropped from
    # what is returned, so no reader ever sees a counter again.
    data.pop("next_id", None)


# os.replace under a concurrent reader on Windows (L-00000054): same bound as
# every other publisher in the kit. 30 × 10 ms ≈ 300 ms of patience, which is
# what the measurement said absorbs a reader's open handle.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01


def _replace_with_retry(src: str | Path, target: str | Path) -> None:
    """`os.replace`, retried on the Windows sharing violation (T-00000053).

    A bare `os.replace` is NOT enough here: Windows raises `PermissionError`
    when the target is open in a reader, and that was MEASURED at 69-81 %
    failure under a concurrent reader (L-00000054). The reader is not
    hypothetical for this store — the dashboard daemon reads it on every
    snapshot, so any write while the page is open runs that race.

    COSTS NOTHING OFF WINDOWS, and that is by construction rather than by a
    platform test: on macOS and Linux a rename over an open file succeeds, so
    the very first `os.replace` returns and the loop never reaches `sleep`.
    There is deliberately no `if os.name == "nt"` guard — one code path, whose
    slow branch simply cannot be taken there.

    Same shape and same bound as `build_index.py`, `events.py`,
    `event_store.py` and `project_init.py`: only `PermissionError` is retried
    (a genuinely broken path must still fail fast), and the LAST exception is
    re-raised rather than a fresh one, so the traceback names the real cause."""
    last: OSError | None = None
    for _ in range(_REPLACE_ATTEMPTS):
        try:
            commit_guard = _BOARD_COMMIT_GUARD.get()
            if commit_guard is not None:
                try:
                    commit_allowed = commit_guard()
                except Exception as exc:
                    raise BoardError("board commit guard failed") from exc
                if not commit_allowed:
                    raise BoardError("board commit guard refused save")
            os.replace(src, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(_REPLACE_DELAY_SECONDS)
    assert last is not None
    raise last


def save(root: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """Write the store ATOMICALLY (mkstemp in the same dir -> write -> close the
    fd -> chmod -> replace, in that order — closing before replace is a hard
    Windows requirement, an open handle makes the replace fail there), then
    regenerate the view from it. The replace itself is RETRIED on the Windows
    sharing violation: see `_replace_with_retry`.

    `save()` is the single door every writer goes through, so a write refusal
    belongs HERE and runs BEFORE the temp file is created: a refusal leaves the
    store exactly as it was. The running-group refusal of T-00000188 is retired
    (T-01M5F7286N1EYGXAXA5244X86B): several running tasks are a legitimate board.

    NO COUNTER IS WRITTEN (T-00000726): what is serialised is a COPY of ``data``
    minus ``next_id`` — a caller (or an old store) may still carry it — and minus
    ``sync_outbox`` (T-00001058: one file per intent, below); every other key,
    ``epics`` and ``sync_correlations`` included, passes.

    THE O2 OUTBOX IS WRITTEN IN TWO STEPS AROUND ONE POINT OF VALIDATION, the
    replace of TASKS.json (T-00001058 step 3): (1) the NEW intents of this save go
    into ONE local lot, created exclusively and fsync'ed, carrying the sha256 of the
    bytes about to be published — no `os.replace` before (2), so a commit guard that
    refuses leaves the store, the folder and no lot (the lot is withdrawn with the
    temp); (2) the replace; (3) the lot is exploded into its definitive files and
    withdrawn LAST, the MODIFIED intents are rewritten in their file (C1), the files
    of the intents that LEFT the list are removed. A crash leaves at most one lot,
    which the next `save()` / `claim` explodes (validated) or quarantines (not) —
    `_reprendre_lots`, at the head of both, under `board_lock`. A save without any
    intent, intent folder or lot does what it did before: ONE `os.replace`, and no
    lock taken here (`project_init` provisions a board that way; its golden listing
    has no `TASKS.lock`, test_cadre_init.py I11).

    AND IT REFUSES A RESURRECTION (F5, T-00001058 step 4): a task on the board whose
    id a correlation marks ``tombstoned`` came back by a merge or by a git gesture
    that detached an intent file — named by `resurrection_refusal`, before anything
    is written — UNLESS this save removes one of those its `load` saw (`_BoardCharge.ressuscites`):
    `delete_task` removes one id per command, so with two a refusal on the current set alone froze
    the board, remedy included (closing review T1).

    IN THE FORM IT FINDS (T-00001009), after that refusal: the folder of records
    ⇒ `_save_dossier` (no root key, a tombstone for every id that left, one lot as the
    point of validation); both forms ⇒ REFUSED, with the remedy lines; a monolith or
    no board ⇒ the path below, unchanged — a new store is still a monolith."""
    ressuscites, avant = set(_ids_ressuscites(data)), getattr(data, "ressuscites", None)
    if ressuscites and not (avant is not None and ressuscites < avant):
        raise BoardError(f"refusing to write the board: {resurrection_refusal(data)} — nothing was written")
    # THE FORM (T-00001009), decided AFTER the refusal above, which stays HERE for both forms (Piège 1).
    forme = store_form(root)
    if forme == "les deux":
        raise BoardError(_refus_deux_formes_ecriture(root))
    if forme == "dossier":
        _save_dossier(root, data)
        return
    publie = {cle: valeur for cle, valeur in data.items() if cle not in ("next_id", "sync_outbox")}
    octets = (json.dumps(publie, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    from contextlib import nullcontext

    o2 = bool(data.get("sync_outbox")) or _dossier_outbox(root).is_dir() or _dossier_lots(root).is_dir()
    with board_lock(root) if o2 else nullcontext():
        if o2:
            _reprendre_lots(root)
        plan = _planifier_outbox(root, data)
        lot = _ecrire_lot(root, hashlib.sha256(octets).hexdigest(), plan["neufs"]) if plan["neufs"] else None
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tasks-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(octets)
            os.chmod(tmp_name, 0o644)
            _replace_with_retry(tmp_name, path)
        except BaseException:
            for reste in (tmp_name, lot):
                try:
                    if reste is not None:
                        os.unlink(reste)
                except OSError:
                    pass
            if lot is not None:
                _ranger(lot.parent)
            raise
        _apres_publication(root, lot, plan)
    render_view(root, data)


def _ranger(dossier: Path) -> None:
    """Remove a local O2 folder once empty, so `.agents/state/local/` keeps no trace of a finished save."""
    try:
        os.rmdir(dossier)
    except OSError:
        pass


def _fsync_dossier(dossier: Path) -> None:
    """The folder entry too: a file BORN there survives a power cut (precedent `_deverser_excedent`)."""
    if os.name == "nt":
        return
    fd = os.open(dossier, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ecrire_lot(root: str | os.PathLike[str], cible: str, neufs: list[dict[str, Any]]) -> Path:
    """STEP 1: the new intents of ONE save in ONE local lot, CREATED exclusively (`xb`, by `_ouvrir_sans_lien`) —
    never an `os.replace`: nothing is published before the TASKS.json replace, and a commit guard that refuses
    sees none (test_tasks.py, guard witnesses) — then fsync'ed with its folder."""
    dossier = _dossier_lots(root)
    dossier.mkdir(parents=True, exist_ok=True)
    contenu = (json.dumps({"cible": cible, "intents": neufs}, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    base, rang = neufs[0]["nom"][:20], 0
    while True:
        chemin = dossier / (f"{base}.json" if rang == 0 else f"{base}.{rang}.json")
        try:
            fichier = open(chemin, "xb", opener=_ouvrir_sans_lien)
            break
        except FileExistsError:
            rang += 1
    try:
        with fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        _fsync_dossier(dossier)
    except BaseException:  # disque plein, p. ex. : ce save n'a rien publié, son lot ne reste pas
        try:
            os.unlink(chemin)
        except OSError:
            pass
        _ranger(dossier)
        raise
    return chemin


def _poser_definitif(root: str | os.PathLike[str], nom: str, octets: bytes, dossier: Path | None = None) -> None:
    """ONE definitive file, published by `os.replace` from a temp OUTSIDE the tracked folder (`.agents/state/local/`:
    never a `.tmp` under the hook's pathspec, M8), fsync'ed first. Idempotent: same name, same bytes. No commit
    guard — it only runs AFTER the point of validation — but the same retry on the Windows sharing violation.
    ``dossier``: the O2 folder by default; a record folder of the folder form (T-00001009)."""
    dossier = _dossier_outbox(root) if dossier is None else dossier
    dossier.mkdir(parents=True, exist_ok=True)
    local = lock_path(root).parent
    local.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(local), prefix=".sync_outbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(octets)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o644)
        for essai in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp_name, dossier / nom)
                return
            except PermissionError:
                if essai == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_DELAY_SECONDS)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _eclater_lot(root: str | os.PathLike[str], chemin: Path, entrees: list[dict[str, Any]]) -> None:
    """Explode a VALIDATED lot into its definitive files, IDEMPOTENTLY (same names, same bytes), then remove the lot
    LAST: a crash anywhere before leaves a lot that `load` still shows at its rank and the next `save()` / `claim`
    explodes again (S-00003917 (3))."""
    for entree in entrees:
        _poser_definitif(root, entree["nom"], _octets_enveloppe(entree["enveloppe"]))
    _fsync_dossier(_dossier_outbox(root))
    os.unlink(chemin)
    _ranger(chemin.parent)


def _mettre_en_quarantaine(root: str | os.PathLike[str], chemin: Path, raison: str,
                           bilan: dict[str, int] | None = None) -> None:
    """Into the local quarantine, never an `unlink`, under ONE stderr line naming it; a name already taken there
    gets a `.<n>` suffix. A LOT (local, git-ignored) is MOVED. A file of the VERSIONED folder stays IN PLACE —
    refused at every read, and no stores commit removes it from the other clones (pilot decision, closing review
    T4) — and a COPY goes to the quarantine, ONCE per content (the next save finds it again: no `.1` for the same
    bytes, the line is said again). M3 caps, beyond which « IMPOSSIBLE »: `_PLAFOND_QUARANTAINE_COPIES` per name; the
    folder's entries and bytes, checked for a NEW entry only — a copy already there costs nothing and is never
    refused — on ``bilan``, the caller's `_bilan_quarantaine`, evaluated at its first new entry, then counted here."""
    dossier = _dossier_quarantaine(root)
    lot = chemin.parent == _dossier_lots(root)
    try:
        octets = None
        if not lot:
            with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
                try:
                    octets = _lire_plafonne(fichier, _PLAFOND_INTENT_OCTETS)
                except ValueError as exc:
                    raise OSError(f"no copy: {exc}") from exc
        dossier.mkdir(parents=True, exist_ok=True)
        cible, rang, deja = dossier / chemin.name, 0, False
        while os.path.lexists(cible):
            if octets is not None and not cible.is_symlink() and cible.is_file() \
                    and cible.stat().st_size == len(octets) and cible.read_bytes() == octets:
                deja = True
                break
            rang += 1
            if rang >= _PLAFOND_QUARANTAINE_COPIES:
                raise OSError(f"au-delà de {_PLAFOND_QUARANTAINE_COPIES} copies pour ce nom")
            cible = dossier / f"{chemin.stem}.{rang}{chemin.suffix}"
        taille = 0 if deja else len(octets) if octets is not None else chemin.lstat().st_size
        bilan = {} if bilan is None else bilan
        if not deja and not bilan:
            bilan.update(_bilan_quarantaine(dossier))
        if not deja and (bilan["entrees"] >= _PLAFOND_QUARANTAINE_ENTREES
                         or bilan["octets"] + taille > _PLAFOND_QUARANTAINE_OCTETS):
            raise OSError(f"dossier au-delà de son plafond ({bilan['entrees']} entrées, {bilan['octets']} octets)")
        if lot:
            os.replace(chemin, cible)
        elif not deja:
            with open(cible, "xb", opener=_ouvrir_sans_lien) as copie:
                copie.write(octets)
        if not deja:
            bilan["entrees"], bilan["octets"] = bilan["entrees"] + 1, bilan["octets"] + taille
    except OSError as exc:
        print(f"TASKS: sync_outbox — {chemin.name} : {raison} ; quarantaine IMPOSSIBLE, laissé en place : {exc}",
              file=sys.stderr)
        return
    if lot:
        _ranger(chemin.parent)
        geste = (f"mis en quarantaine dans {dossier} (rien n'est effacé, ses intents ne sont pas livrés : à examiner, "
                 "puis à supprimer à la main)")
    else:
        geste = (f"LAISSÉ EN PLACE, refusé à chaque lecture (dossier versionné : les autres clones le gardent) ; "
                 f"copie {'déjà ' if deja else ''}en quarantaine : {cible} (ses intents ne sont pas livrés : à "
                 "examiner, puis à retirer à la main du dossier et à commiter)")
    print(f"TASKS: sync_outbox — {chemin.name} : {raison} ; {geste}", file=sys.stderr)


def _reprendre_lots(root: str | os.PathLike[str]) -> None:
    """THE RECOVERY of the two-step write (S-00003917 (1)), under `board_lock`, at the head of `save()` and of
    `claim_sync_event`: a lot whose save reached TASKS.json (`_lot_valide`) is exploded; any other — a crash before
    the replace, or an unreadable lot — goes to quarantine with one stderr line, never an `unlink`. A VALIDATED
    folder-form lot (T-00001009) is applied again, idempotently (`_appliquer_lot_dossier`), ONLY while the folder form
    is present (N2: on a board whose folders were set aside it would recreate them — quarantined, named);
    `migrate_store` recovers first too. M2 (T-01M4MC28CAKFE8YZ2W4WN7DV2C): before ANY read, a lots or quarantine folder
    — or a record or O2 folder — that is a symbolic link is refused (`_refus_liens`), before every publication."""
    with board_lock(root):
        _refus_liens(root, lots=True)
        lots = _lire_lots(root)
        if not lots:
            return
        bilan: dict[str, int] = {}
        path = store_path(root)
        octets = path.read_bytes() if path.exists() else b""
        try:
            correlations = json.loads(octets.decode("utf-8")).get("sync_correlations")
        except (ValueError, AttributeError, RecursionError):
            correlations = None
        empreinte = hashlib.sha256(octets).hexdigest()
        forme = store_form(root) if any(lot and lot.get("forme") == "dossier" for _chemin, lot in lots) else None
        for chemin, lot in lots:
            if lot is not None and lot.get("forme") == "dossier" and forme not in ("dossier", "les deux"):
                _mettre_en_quarantaine(root, chemin, f"lot de la forme dossier sur un board « {forme} » (dossiers "
                                       "mis de côté ?) : jamais rejoué, il recréerait les dossiers", bilan)
            elif lot is not None and lot.get("forme") == "dossier":
                _appliquer_lot_dossier(root, chemin, lot)
            elif lot is not None and _lot_valide(lot, empreinte, correlations if isinstance(correlations, dict) else {}):
                _eclater_lot(root, chemin, lot["intents"])
            else:
                _mettre_en_quarantaine(
                    root, chemin, "lot d'une écriture qui n'a pas atteint TASKS.json (arrêt avant sa publication), "
                    "ou illisible", bilan)


def _cles_d_ordre(connues: list[int | None], plafond: int) -> list[int]:
    """The ORDER KEY of every intent of the list, the known ones kept: the folder's sorted order IS the list's
    order. New intents at the TAIL take `max(time.time_ns(), last + 1)` upward — `plafond` is the highest key on
    disk —, new ones at the HEAD (the spill put back, `_reinjecter_deverses`) take `min − k … min − 1` in their order
    (S-00003917 (3)). Never `record_id.mint` (§ 2 (d): `start`/`done` enqueue without that sibling). Known keys that
    do not increase, or new intents with no room between two known ones, are REFUSED: no code path produces
    either (enqueue appends, the spill put back prepends, everything else only removes)."""
    presentes = [cle for cle in connues if cle is not None]
    if any(apres <= avant for avant, apres in zip(presentes, presentes[1:])):
        raise BoardError("refusing to write the board: the sync_outbox order no longer follows the order keys of "
                         "its intent files (an intent was moved inside the list) — nothing was written")
    cles = list(connues)
    premiere = next((rang for rang, cle in enumerate(connues) if cle is not None), None)
    if premiere is None:
        depart = max(time.time_ns(), plafond + 1)
        return [depart + rang for rang in range(len(connues))]
    if connues[premiere] < premiere:
        raise BoardError("refusing to write the board: no order key is left before the head of sync_outbox — "
                         "nothing was written")
    for rang in range(premiere):
        cles[rang] = connues[premiere] - premiere + rang
    precedente, rang = connues[premiere], premiere + 1
    while rang < len(cles):
        if cles[rang] is not None:
            precedente, rang = cles[rang], rang + 1
            continue
        fin = rang
        while fin < len(cles) and cles[fin] is None:
            fin += 1
        if fin < len(cles) and cles[fin] - precedente - 1 < fin - rang:
            raise BoardError("refusing to write the board: no order key is left between two pending intents of "
                             "sync_outbox — nothing was written")
        depart = precedente + 1 if fin < len(cles) else max(time.time_ns(), plafond + 1, precedente + 1)
        for decale in range(rang, fin):
            cles[decale] = depart + decale - rang
        rang = fin
    return cles


def _planifier_outbox(root: str | os.PathLike[str], data: dict[str, Any]) -> dict[str, Any]:
    """What `save()` does to the O2 folder, decided BEFORE anything is written (a refusal leaves everything as it
    was): the NEW intents (into the lot), the MODIFIED ones (rewritten in place: a lease, an attempt, a copy of the
    correlation — C1), the files to REMOVE — the intents that LEFT the list, i.e. read at `load` and not written
    now (S-00003917 (1); never "folder − list"), and the extra copies of one operation —, the unreadable files to
    quarantine, and the keys re-indexed at `load` that the text gets back."""
    meta = getattr(data, "vue_o2", None)
    if meta is not None and meta.get("racine") != os.path.normcase(str(Path(root).resolve())):
        meta = None
    vus, charges = (meta["ops"], meta["fichiers"]) if meta else (set(), {})
    correlations = data.get("sync_correlations") or {}
    outbox = data.get("sync_outbox") or []
    ops: list[str] = []
    gardes: set[str] = set()
    for intent in outbox:
        op = intent.get("operation_id") if isinstance(intent, dict) else None
        if not isinstance(op, str) or _NOM_INTENT.match(f"{0:020d}-{op}.json") is None or op in gardes:
            raise BoardError(f"refusing to write the board: sync_outbox entry {op!r} cannot name ONE intent file "
                             "(no operation id, a duplicate one, or one outside [0-9A-Za-z._-]) — nothing was written")
        ops.append(op)
        gardes.add(op)
    disque: dict[str, list[tuple[int, str]]] = {}
    octets_disque: dict[str, bytes] = {}
    quarantaine: list[str] = []
    plafond = -1
    for cle, nom, brut, enveloppe, _refus in _relire(root, charges, meta) if meta else _lire_definitifs(root):
        if enveloppe is None:
            quarantaine.append(nom)
            continue
        disque.setdefault(_NOM_INTENT.match(nom).group(2), []).append((cle, nom))
        octets_disque[nom] = brut
        plafond = max(plafond, cle)
    cles = _cles_d_ordre([min(disque[op])[0] if op in disque else None for op in ops], plafond)
    neufs: list[dict[str, Any]] = []
    modifies: list[tuple[str, bytes]] = []
    retirer: list[str] = []
    for intent, op, cle in zip(outbox, ops, cles):
        nom = f"{cle:020d}-{op}.json"
        correlation = correlations.get(op)
        if not (isinstance(correlation, dict) and set(correlation) == {"board_task_id", "tombstoned"}):
            affectes = intent.get("affected_task_ids")
            premier = affectes[0] if isinstance(affectes, list) and affectes and isinstance(affectes[0], str) else ""
            correlation = {"board_task_id": premier, "tombstoned": intent.get("after") is None}
        enveloppe = {"correlation": correlation, "intent": intent}
        presents = [present for _cle, present in disque.get(op, [])]
        if nom in presents:
            if octets_disque[nom] != _octets_enveloppe(enveloppe):
                modifies.append((nom, _octets_enveloppe(enveloppe)))
        else:
            neufs.append({"nom": nom, "enveloppe": enveloppe})
        retirer += [present for present in presents if present != nom and op in vus]
    for op, presents in disque.items():
        if op not in gardes and op in vus:
            retirer += [present for _cle, present in presents]
    reindexes = [op for op in (meta["reindexes"] if meta else []) if op in correlations]
    return {"neufs": neufs, "modifies": modifies, "retirer": retirer, "quarantaine": quarantaine,
            "reindexes": reindexes}


def _relire(root: str | os.PathLike[str], charges: dict[str, bytes], meta: dict[str, Any]) -> list[tuple[Any, ...]]:
    """The folder at `save()` time, re-reading ONLY the files `load` did not read (a file is re-read once per save at
    most): the names on disk, the bytes `load` kept for the others, and the files it found unreadable — within the SAME
    window as `_lire_definitifs` (M3, `_intents_retenus`): a file beyond it is never « unreadable », never quarantined."""
    dossier = _dossier_outbox(root)
    noms = [chemin.name for chemin in _intents_retenus(dossier)[0]] if dossier.is_dir() else []
    inconnus = {nom for nom in noms if nom not in charges and nom not in meta["illisibles"]}
    relus = {lu[1]: lu for lu in _lire_definitifs(root) if lu[1] in inconnus} if inconnus else {}
    lus: list[tuple[Any, ...]] = []
    for nom in noms:
        match = _NOM_INTENT.match(nom)
        if match is None:
            continue
        if nom in charges:
            lus.append((int(match.group(1)), nom, charges[nom], True, None))
        elif nom in relus:
            lus.append(relus[nom])
        else:
            lus.append((int(match.group(1)), nom, None, None, "is unreadable"))
    return lus


def _apres_publication(root: str | os.PathLike[str], lot: Path | None, plan: dict[str, Any]) -> None:
    """STEP 3, after the single point of validation (the TASKS.json replace): explode the lot, rewrite the modified
    intents (C1), remove the files of the intents that left the list, quarantine the unreadable files, and say the
    keys given back to the text. TASKS.json IS published: a failure here is SAID on stderr, never raised — a lot
    left behind stays validated and visible, and the next save explodes it."""
    dossier = _dossier_outbox(root)
    etapes = (
        ("éclatement du lot", lambda: _eclater_lot(root, lot, plan["neufs"]) if lot is not None else None),
        ("réécriture des intents modifiés", lambda: [_poser_definitif(root, nom, octets)
                                                     for nom, octets in plan["modifies"]]),
        ("retrait des intents sortis", lambda: [(dossier / nom).unlink(missing_ok=True) for nom in plan["retirer"]]),
    )
    for etape, geste in etapes:
        try:
            geste()
        except OSError as exc:
            print(f"TASKS: sync_outbox — board écrit, {etape} à reprendre au prochain save : {exc}", file=sys.stderr)
    bilan: dict[str, int] = {}  # M3 : le dossier de quarantaine évalué une fois pour ce save, à sa première entrée neuve
    for nom in plan["quarantaine"]:
        _mettre_en_quarantaine(root, dossier / nom, "fichier d'intent illisible ou hors forme, exclu de la vue", bilan)
    if plan["reindexes"]:
        # OÙ la clé revient dépend de la FORME (T-00001009) : le texte de TASKS.json, ou le `sync_operations` de
        # l'enregistrement de sa tâche (`plan["forme"]`, posé par `_save_dossier`).
        ou = ("dans le sync_operations de l'enregistrement de leur tâche (board/tasks/<id>.json), enregistrement "
              "fusionné ou restauré sans elles") if plan.get("forme") == "dossier" else \
            "dans TASKS.json (TASKS.json fusionné ou restauré sans elles)"
        print(
            f"TASKS: sync_outbox — {len(plan['reindexes'])} clé(s) de corrélation remise(s) {ou} depuis leur fichier "
            f"d'intent : {', '.join(plan['reindexes'])}",
            file=sys.stderr,
        )


def _ids_ressuscites(data: dict[str, Any]) -> list[str]:
    """The ids ALIVE on the board that a correlation marks ``tombstoned``, sorted. EXACT ids, never a prefix: two
    `T-<ULID>` minted a few ms apart share one."""
    vivants = {tache.get("id") for tache in data.get("tasks") or [] if isinstance(tache, dict)}
    tombes = {
        correlation.get("board_task_id")
        for correlation in (data.get("sync_correlations") or {}).values()
        if isinstance(correlation, dict) and correlation.get("tombstoned") is True
    }
    return sorted(tid for tid in vivants & tombes if isinstance(tid, str))


def resurrection_refusal(data: dict[str, Any]) -> str | None:
    """F5 (T-00001058 step 4, S-00003918): why the board carries a deletion that came back (`_ids_ressuscites`), or
    ``None``. Detection AT BEST: on a monolith, a merge that drops the tombstoned key itself, or a `git restore` of the
    whole file, leaves no trace; in the folder form (T-00001009) ``tombstoned`` is DERIVED from ``record: null``, so F5
    bites a deletion still IN FLIGHT (its intent file) only — once acknowledged, its tombstone file protects by a merge
    CONFLICT, and a `git restore` of the whole folder still leaves no trace. Called by `save()` before anything is
    written, and by the drain, which delivers
    nothing while it holds (a refused drain would make every verb fail, `delete` — the remedy — included). The remedy
    names ONE `delete` per id (one id per command), and `new` AFTER them: a `new` first is refused like any save. M1
    (T-01M4MC28CAKFE8YZ2W4WN7DV2C): each id of a printed command is `shlex.quote`d — POSIX quoting only (L-00000079),
    like `_remedy_line` —; the descriptive list heading the sentence stays raw (prose, not a command)."""
    import shlex

    ids = _ids_ressuscites(data)
    if not ids:
        return None
    return (
        f"{', '.join(ids)} {'is' if len(ids) == 1 else 'are'} on the board AND tombstoned in sync_correlations: a "
        "deletion came back — a git merge kept the task from one side and its deletion from the other, or a git "
        "gesture detached an intent file from its TASKS.json (`git stash` without -u, `git restore` or `git checkout` "
        "of TASKS.json, `git clean`; see `git status -- .agents/state/board/sync_outbox/`). If the intent files were "
        "stashed, `git stash pop` (or restore the TASKS.json that goes with them) FIRST; otherwise delete again, one "
        f"command per id ({'; '.join(f'`tasks.py delete {shlex.quote(tid)}`' for tid in ids)}); to keep a content, "
        "read it first (`tasks.py list --task <id>`), delete it, THEN `tasks.py new`"
    )


def canonical_task_snapshot(task: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return only business fields; technical sync metadata never enters hashes."""
    if task is None:
        return None
    return {field: task.get(field, "") for field in SYNC_SNAPSHOT_FIELDS}


def revision_sha256(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> str:
    body = json.dumps(
        {
            "before": canonical_task_snapshot(before),
            "after": canonical_task_snapshot(after),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


# THE RECORD FORMAT (T-00001008, BK-415, E-26) — ONE FILE PER RECORD, AND THE MACHINE PROJECTION OF THE
# CORRELATIONS. PURE functions: nothing below writes. Since T-00001009, `load()` / `save()` in the folder form and
# `migrate_store` (tasks_dossier.py) call them; the kit's REAL board stays a monolith until the switch-over task
# (T-01M4KKMY43ZKCW1YD2Y8JX9MKH). T-1010 COPIED the format into ledger.py (S-00003552, never imported) and T-1011 chose
# a JSONL journal (S-01M4KKQ0XD9MFD63AVX0KDGHR2), so a fix here must be replayed on ledger.py's copy; and the
# multi-file write REUSES the two-step publication of T-00001058 (S-00003917), never a new one. A record lives in
# `<home>/<collection>/<id>.json`: ONE
# envelope `{"format": 1, "id", "record"}`, plus `"sync_operations"` in the `tasks` collection only. `record` is the
# object as the store holds it, or `null` = a TOMBSTONE: a deleted record — in the folder form, EVERY id that leaves
# the board, its correlation keys inside (`[]` without any, T-00001009); tombstones stay in the live folder until the
# compaction of the archive task (retention clause).
# Pilot decision S-01M4JN56JEQ0XS97K38CDWBTW6: the link operation ↔ task is the
# `sync_operations` field OF the task's record, and `sync_correlations` is its inverted projection, computed, never
# versioned on its own. ALIGNED on T-1058 (S-00003918): the same bytes (`_octets_enveloppe`: indent 2, sorted keys,
# raw UTF-8, LF), the same exclusion of dot names at read; DIVERGENT on purpose: a versioned envelope naming its id,
# where an O2 file is the bare `{correlation, intent}` of one operation. BOUND (pilot decision
# S-01M4JN56NB05914VWW942W214X): git merges two DIFFERENT records without conflict, but two neighbouring fields of
# the SAME record (`stage`/`state`, `updated`) still conflict — "compatible" means line-compatible; a per-field merge
# is another task.
RECORD_FORMAT = 1
_ID_ENREGISTREMENT = re.compile(r"\A[TSLE]-[0-9]{1,15}\Z", re.ASCII)  # ASCII digits: `T-١٢` names no file
_COLLECTION_CORRELEE = "tasks"
# Read cap of ONE record file (it arrives by `git pull` from another clone): the largest record of the kit's three
# stores is 33 129 bytes (T-012, measured 2026-10-11), so 4 MiB is a margin above 120.
_PLAFOND_ENREGISTREMENT_OCTETS = 4 * 1024 * 1024


def _refus_id_enregistrement(rid: Any) -> str | None:
    """Why ``rid`` cannot name a record file, or ``None``: a ``P-<ULID>`` (`is_ulid_id`) or the stored legacy alias
    ``[TSLE]-<1 to 15 digits>`` (the bound of `numeric_id`), anchored at both ends — nothing else."""
    if isinstance(rid, str) and (is_ulid_id(rid) or _ID_ENREGISTREMENT.match(rid)):
        return None
    return f"{rid!r} is not a record id (P-<ULID>, or [TSLE]-<1 to 15 digits> as stored)"


def _refus_enregistrement(enveloppe: Any, collection: str, rid: str) -> str | None:
    """Why ``enveloppe`` is not ONE valid record of ``collection`` named ``rid``, or ``None``. ``format`` is
    REQUIRED (a reader that defaulted it to 1 would swallow a foreign file) and an exact ``int``; the keys are exact
    (``sync_operations`` in ``tasks`` only); ``id`` is the name's id and ``record`` is ``null`` or an object whose
    ``id`` is that id; ``sync_operations`` is a list of distinct non-empty operation ids."""
    if not isinstance(enveloppe, dict):
        return "is not a record envelope (a JSON object)"
    if "format" not in enveloppe:
        return "has no `format` key"
    version = enveloppe["format"]
    if type(version) is not int or version < 1:
        return f"has an invalid format {version!r}"
    if version > RECORD_FORMAT:
        return f"is in format {version}, newer than this code reads ({RECORD_FORMAT}): update the kit first"
    attendues = {"format", "id", "record"} | ({"sync_operations"} if collection == _COLLECTION_CORRELEE else set())
    if set(enveloppe) != attendues:
        return f"has keys {sorted(map(str, enveloppe))}, expected exactly {sorted(attendues)}"
    if enveloppe["id"] != rid:
        return f"holds id {enveloppe['id']!r}, not the {rid!r} its name announces"
    record = enveloppe["record"]
    if record is not None and (not isinstance(record, dict) or record.get("id") != rid):
        return f"holds a record whose id is not {rid!r}"
    if collection == _COLLECTION_CORRELEE:
        ops = enveloppe["sync_operations"]
        if not (isinstance(ops, list) and all(isinstance(op, str) and op for op in ops) and len(set(ops)) == len(ops)):
            return "has invalid sync_operations (expected a list of distinct non-empty operation ids)"
    return None


def record_file(dossier: str | os.PathLike[str], rid: str) -> Path:
    """The file of record ``rid`` in ``dossier``: ``<dossier>/<rid>.json``, under the STORED id (``T-012`` stays
    ``T-012.json``, never padded nor rewritten). Any other id — traversal, separator, lower case, empty, a final
    newline, 16 digits — raises `BoardError`: a name read from another clone never leaves its folder."""
    refus = _refus_id_enregistrement(rid)
    if refus is not None:
        raise BoardError(f"record file: {refus}")
    return Path(dossier) / f"{rid}.json"


def record_bytes(enveloppe: dict[str, Any]) -> bytes:
    """The canonical bytes of ONE record envelope, its collection DEDUCED from it (``sync_operations`` present ⇒
    ``tasks``): a documented SHORTCUT, kept at ONE argument for the parity of ledger.py's copy (W11). Every
    production writer passes the collection to `record_bytes_pour` (T-00001009, M9): deduced, a task envelope that
    lost its ``sync_operations`` would be written, then refused by `read_records`."""
    return record_bytes_pour(enveloppe, _COLLECTION_CORRELEE if isinstance(enveloppe, dict)
                             and "sync_operations" in enveloppe else "")


def record_bytes_pour(enveloppe: dict[str, Any], collection: str) -> bytes:
    """The canonical bytes of ONE record envelope of ``collection`` (PASSED, never deduced): `_octets_enveloppe`, the
    serialiser of the O2 intents and the form of `save()` (T-00001058), CALLED, never redefined. VALID AT WRITE: an
    envelope out of shape for that collection (`_refus_enregistrement`) raises `BoardError` instead of reaching a
    file. STRICT JSON in UTF-8 too: a NaN / Infinity (bytes no strict JSON reader reads back) or a lone surrogate (no
    UTF-8 form) raises `BoardError`, never a raw `ValueError` / `UnicodeEncodeError` (E-26 closing pass)."""
    rid = enveloppe.get("id") if isinstance(enveloppe, dict) else None
    refus = _refus_id_enregistrement(rid)
    if refus is None:
        refus = _refus_enregistrement(enveloppe, collection, rid)
    if refus is not None:
        raise BoardError(f"record {rid!r}: refusing to serialise an envelope that {refus}")
    try:
        json.dumps(enveloppe, allow_nan=False)  # NaN / Infinity: ValueError
        return _octets_enveloppe(enveloppe)  # a lone surrogate: UnicodeEncodeError, a ValueError too
    except ValueError as exc:
        raise BoardError(
            f"record {rid!r}: refusing to serialise an envelope that is not strict UTF-8 JSON ({exc})") from None


def explode_store(data: dict[str, Any], collections: tuple[str, ...]) -> dict[str, bytes]:
    """ONE file per record of ``data``: ``{"<collection>/<id>.json": bytes}``, for ``("tasks", "epics")`` (TASKS)
    or ``("entries",)`` (a one-collection store; ledger.py carries its own copy). Reads ``data`` and NEVER changes
    it — a `_BoardCharge` handed in keeps its ``vue_o2``, its ``ressuscites`` and its ``sync_outbox``, on which the
    O2 removal rule rests (S-01M4M2E77V0ZPRSDHSNR65SS8K) — and writes nothing.

    Every key of ``sync_correlations`` goes INTO the record of its task (``sync_operations``, sorted), the
    acknowledged ones included: they live nowhere but in TASKS.json. A task absent from the board whose keys are ALL
    tombstoned gets a TOMBSTONE file (``record: null``) carrying them — the permanent trace F5 reads. Refused, named,
    never a loss: a live task carrying a tombstoned key (F5, `resurrection_refusal`); a key NOT tombstoned whose task
    is absent (dangling); a correlation out of shape or naming no record id; a top-level key that is neither a
    collection nor — on TASKS — ``sync_correlations`` / ``sync_outbox``; two records of one identity
    (`identity_key`). ``sync_outbox`` is NEVER exploded: its intents live in their O2 files (T-00001058), and
    `load()` fills that key from them."""
    if not isinstance(data, dict):
        raise BoardError("explode: the store is not an object")
    correle = _COLLECTION_CORRELEE in collections
    connues = set(collections) | ({"sync_correlations", "sync_outbox"} if correle else set())
    inconnues = sorted(str(cle) for cle in data if cle not in connues)
    if inconnues:
        raise BoardError(f"explode: unknown top-level key(s) {', '.join(inconnues)} — neither a collection of "
                         f"{list(collections)} nor a key this format carries; nothing is dropped in silence")
    correlations = data.get("sync_correlations", {}) if correle else {}
    if not isinstance(correlations, dict):
        raise BoardError("explode: sync_correlations must be an object")
    par_tache: dict[str, list[tuple[str, bool]]] = {}
    for op, correlation in correlations.items():
        if not (isinstance(op, str) and op and isinstance(correlation, dict)
                and set(correlation) == {"board_task_id", "tombstoned"}
                and isinstance(correlation["tombstoned"], bool)
                and _refus_id_enregistrement(correlation["board_task_id"]) is None):
            raise BoardError(f"explode: correlation {op!r} is out of shape or names no record id: {correlation!r}")
        par_tache.setdefault(correlation["board_task_id"], []).append((op, correlation["tombstoned"]))
    fichiers: dict[str, bytes] = {}
    for collection in collections:
        records = data.get(collection, [])
        if not isinstance(records, list):
            raise BoardError(f"explode: {collection} must be a list")
        enveloppes: list[dict[str, Any]] = []
        for record in records:
            rid = record.get("id") if isinstance(record, dict) else None
            refus = _refus_id_enregistrement(rid)
            if refus is not None:
                raise BoardError(f"explode: a record of {collection}: {refus}")
            enveloppe = {"format": RECORD_FORMAT, "id": rid, "record": record}
            if collection == _COLLECTION_CORRELEE:
                siennes = par_tache.pop(rid, [])
                tombees = sorted(op for op, tombee in siennes if tombee)
                if tombees:
                    raise BoardError(f"explode: {rid} carries the tombstoned key(s) {', '.join(tombees)} — "
                                     f"{resurrection_refusal(data)}")
                enveloppe["sync_operations"] = sorted(op for op, _tombee in siennes)
            enveloppes.append(enveloppe)
        if collection == _COLLECTION_CORRELEE:
            for tid, siennes in sorted(par_tache.items()):
                pendantes = sorted(op for op, tombee in siennes if not tombee)
                if pendantes:
                    raise BoardError(f"explode: {', '.join(pendantes)} correlate(s) {tid}, absent from the board and "
                                     "not tombstoned — a dangling correlation, refused rather than dropped")
                enveloppes.append({"format": RECORD_FORMAT, "id": tid, "record": None,
                                   "sync_operations": sorted(op for op, _tombee in siennes)})
        identites: dict[tuple[int, int | str], str] = {}
        for enveloppe in enveloppes:
            nom = f"{collection}/{enveloppe['id']}.json"
            cle = identity_key(enveloppe["id"])
            if cle in identites:
                raise BoardError(f"explode: {identites[cle]} and {nom} name the same record (identity_key)")
            identites[cle] = nom
            fichiers[nom] = record_bytes_pour(enveloppe, collection)
    return fichiers


def correlation_projection(enveloppes: Any) -> dict[str, dict[str, Any]]:
    """THE MACHINE PROJECTION (S-01M4JN56JEQ0XS97K38CDWBTW6): ``{operation_id: {"board_task_id": <id of the record
    that carries it>, "tombstoned": <that record is a tombstone>}}`` — the exact shape `_validate_sync_extensions`
    accepts — rebuilt from the task envelopes ALONE: no data lives only in the projection. An envelope out of shape,
    or an operation carried by two records (both named), is refused: an operation belongs to ONE task."""
    projection: dict[str, dict[str, Any]] = {}
    for enveloppe in enveloppes:
        rid = enveloppe.get("id") if isinstance(enveloppe, dict) else None
        refus = _refus_id_enregistrement(rid) or _refus_enregistrement(enveloppe, _COLLECTION_CORRELEE, rid)
        if refus is not None:
            raise BoardError(f"projection: task record {rid!r} {refus}")
        for op in enveloppe["sync_operations"]:
            if op in projection:
                raise BoardError(f"projection: operation {op!r} is carried by two records, "
                                 f"{projection[op]['board_task_id']} and {rid}")
            projection[op] = {"board_task_id": rid, "tombstoned": enveloppe["record"] is None}
    return projection


def assemble_store(fichiers: dict[str, bytes], collections: tuple[str, ...]) -> dict[str, Any]:
    """The store rebuilt from its record files ``{"<collection>/<id>.json": bytes}``, the inverse of
    `explode_store`. Each collection is sorted by `sort_key` of the id — no ordinal is stored, so an entry written out
    of order comes back at its rank — never by string. The FIRST collection is always present, another only when it
    holds a record (a store without epics keeps its shape; a hand-written ``"epics": []`` does not come back —
    bound). On ``tasks``, ``sync_correlations`` is `correlation_projection` of the task files, tombstones included;
    ``sync_outbox`` is NOT rendered: the caller joins the O2 view to it.

    VALID AT WRITE, TOLERANT AT READ: bytes that are valid but not canonical (indent, key order, CRLF, escaped UTF-8)
    are ACCEPTED. Refused, naming the file, never skipped: a name that is not ``<collection>/<record id>.json``, bytes
    that are not UTF-8 JSON, an envelope out of shape (`_refus_enregistrement`), two files of one identity
    (``T-012`` and ``T-00000012``). A tombstone with no operation is accepted: in the folder form EVERY id that
    leaves the board gets one, ``[]`` included (T-00001009, `_save_dossier`).

    Returns a FRESH plain dict, never a `_BoardCharge`: it carries no O2 view, so it is never handed to `save()` as
    is — a writer goes through `load()` (S-01M4M2E77V0ZPRSDHSNR65SS8K)."""
    par_collection: dict[str, list[dict[str, Any]]] = {collection: [] for collection in collections}
    identites: dict[tuple[str, tuple[int, int | str]], str] = {}
    for nom in sorted(fichiers):
        collection, _sep, fichier = nom.partition("/")
        rid = fichier[: -len(".json")] if fichier.endswith(".json") else None
        if collection not in par_collection or rid is None or _refus_id_enregistrement(rid) is not None:
            raise BoardError(f"record file {nom!r} is not <collection>/<record id>.json for {list(collections)}")
        try:
            enveloppe = json.loads(fichiers[nom].decode("utf-8"))
        except (ValueError, RecursionError) as exc:
            raise BoardError(f"record file {nom!r} is unreadable ({exc})") from exc
        refus = _refus_enregistrement(enveloppe, collection, rid)
        if refus is not None:
            raise BoardError(f"record file {nom!r} {refus}")
        cle = (collection, identity_key(rid))
        if cle in identites:
            raise BoardError(f"record files {identites[cle]!r} and {nom!r} name the same record (identity_key)")
        identites[cle] = nom
        par_collection[collection].append(enveloppe)
    store: dict[str, Any] = {}
    for rang, collection in enumerate(collections):
        enveloppes = sorted(par_collection[collection], key=lambda enveloppe: sort_key(enveloppe["id"]))
        records = [enveloppe["record"] for enveloppe in enveloppes if enveloppe["record"] is not None]
        if rang == 0 or records:
            store[collection] = records
    if _COLLECTION_CORRELEE in collections:
        store["sync_correlations"] = correlation_projection(par_collection[_COLLECTION_CORRELEE])
    return store


def read_records(dossier: str | os.PathLike[str], collections: tuple[str, ...]) -> dict[str, Any]:
    """The store read from ``<dossier>/<collection>/<id>.json``, then `assemble_store`; reads only, writes nothing.
    In a collection folder, a name starting with ``.`` is IGNORED — the temp file of an atomic write —; any other
    name that is not ``<record id>.json`` (``T-12.JSON``, ``x.txt``, a sub-folder) is REFUSED, named, never skipped.
    Each file is opened like an O2 intent (`_ouvrir_sans_lien`: no final symlink, a regular file only) and read up to
    `_PLAFOND_ENREGISTREMENT_OCTETS`; a collection FOLDER that is a symbolic link is REFUSED (T-00001009, security
    review: `O_NOFOLLOW` guards the last component only, the folder would be traversed). An absent folder or
    collection folder is an empty collection; what is not a collection folder is not read."""
    return assemble_store(_octets_enregistrements(dossier, collections), collections)


def _octets_enregistrements(dossier: str | os.PathLike[str], collections: tuple[str, ...]) -> dict[str, bytes]:
    """The READ of `read_records`, its bytes kept per ``"<collection>/<id>.json"`` (T-00001009: the folder form's
    `load()` keeps them to write only what changed) — the same names refused, the same opening and cap."""
    fichiers: dict[str, bytes] = {}
    for collection in collections:
        sous = Path(dossier) / collection
        if os.path.islink(sous):
            raise BoardError(f"{sous} is a symbolic link — refused, never traversed: put a real folder in its place")
        if not sous.is_dir():
            continue
        for chemin in sorted(sous.iterdir()):
            if chemin.name.startswith("."):
                continue
            nom = f"{collection}/{chemin.name}"
            rid = chemin.name[: -len(".json")] if chemin.name.endswith(".json") else None
            if rid is None or _refus_id_enregistrement(rid) is not None:
                raise BoardError(f"{sous}: {chemin.name!r} is not a record file <record id>.json — refused, never "
                                 "skipped")
            try:
                with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
                    fichiers[nom] = _lire_plafonne(fichier, _PLAFOND_ENREGISTREMENT_OCTETS)
            except (OSError, ValueError) as exc:
                raise BoardError(f"record file {nom!r} is unreadable ({exc})") from exc
    return fichiers
