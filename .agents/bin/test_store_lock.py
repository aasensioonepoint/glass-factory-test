"""Concurrency net for the per-store locks (T-00000189, volet 2; board, T-00000730;
``set_state`` and the ``board_lock`` handle, T-00001063).

THREE stores, two shapes. specs.py and ledger.py each wrap read->mutate->write
in a dedicated ``store_lock``, exactly as tasks.py wraps ``board_lock``. The
suite is PARAMETRISED over those two so a regression that unlocks ONE of them
names the faulty file rather than hiding in the other's green (same argument as
test_state_atomic.py's parametrised trio). The BOARD (tasks.py, ``board_lock``
in tasks_stockage.py) has its OWN forced-interleave case,
``board_lock_un_entrelacement_force_ne_perd_aucune_tache``, outside ``STORES``:
the parametrised cases read ``load()["entries"]`` (the board holds ``tasks``)
and four of them reach ``_STORE_LOCK_DEPTH``, ``_STORE_LOCK_TIMEOUT_SECONDS``,
``_acquire_lock_once`` or ``_release_lock_once``, none of which tasks.py has.

WHY THE INTERLEAVING NET CARRIES NO CLOCK (L-00000035). A concurrency test that
sleeps to "let the other side get ahead" flakes the first time a Windows AV
handle or a cold start stretches that sleep. Here the ordering is driven by
MARKER FILES a causal event writes, never by a duration:
``un_entrelacement_force_ne_perd_aucune_entree`` makes writer A hold the lock
and wait for writer B to CONTEND (B writes ``B_contend`` on its first missed
acquisition, through the one module seam ``_lock_poll_sleep``); the wait bounds
are generous and their EXPIRY IS A FAILURE, never a green. Remove the lock and
the test goes red deterministically (B never contends, A overwrites B, one
entry, and A receives ``B_ecrit`` instead of ``B_contend``) — verified by
neutering ``store_lock`` and re-running this one case.

The board case uses the same markers through tasks.py's own seam
``_lock_poll_sleep`` (T-00000730). The mutation that turns IT red is the
short-circuited seam: ``board_lock`` keeping an inline ``time.sleep`` instead of
calling ``_lock_poll_sleep``. B then contends without ever writing ``B_contend``,
keeps contending (the driver raises its lock bound to 30 s) until A's wait
expires at 30 s. That red is deterministic but slow, and the expiry is a
FAILURE, never a green; ``board_lock_appelle_la_couture`` reds the same mutation
at once, clock-free. A writer B that dies BEFORE writing touches ``B_echec``, so
A stops waiting at once instead of at its 30 s bound.

SET_STATE ET POIGNÉE DE ``board_lock`` (T-00001063) — bornés PAR JAMBE, jamais
« couvert » sans borne (L-00000111, L-00000187).

- ``set_state``, MESURÉ (verbes ``running`` et ``done``, gardes désarmées) :
  chargement sous verrou, écriture sous verrou, verrou CONTINU (une seule
  acquisition externe de ``load`` à ``save``) et BON verrou (la clé de CE board,
  jamais ``POST_TASK_DONE.lock``), par la sonde
  ``set_state_tient_un_seul_verrou_du_chargement_a_l_ecriture`` ; exclusion
  réelle entre deux processus, par
  ``set_state_un_entrelacement_force_ne_perd_aucune_tache``. Rougissent la
  sonde : chargement hors verrou, aucun verrou, mauvais nom de verrou, écriture
  hors verrou, verrou scindé en deux ``with``, profondeur jamais dépilée, second
  ``save`` après le verrou, rechargement-et-écriture après le verrou. Rougit
  l'entrelacement SEUL : un ``board_lock`` qui ne pose aucun ``flock`` (la sonde
  reste verte). Borne de la sonde : elle relève CHAQUE ``load`` et CHAQUE
  ``save`` atteints par les noms ``tasks.load`` / ``tasks.save``, et compte les
  acquisitions passées par ``tasks.board_lock`` ; un accès qui contournerait ces
  noms n'est pas vu, et si ``set_state`` cessait de les atteindre la sonde
  ROUGIT (liste vide), jamais ne verdit. La jambe git armée de
  ``binome_reprise_refusal`` n'est pas exercée (racine tmp, gardes désarmées).
- ``new_task``, par ``board_lock_un_entrelacement_force_ne_perd_aucune_tache`` :
  chargement hors verrou, verrou absent, écriture hors verrou MESURÉS ; mauvais
  nom de verrou MESURÉ par les entrelacements de ``set_state`` (le B lancé par
  ``_DRIVER`` y est un ``new_task``) ; verrou CONTINU NON MESURÉ.
- CÂBLÉES, NON MESURÉES : 19 autres fonctions du board (relevé
  ``scan_unlocked.py``, annexe hors dépôt du plan T-00001063, rejoué à
  92220a06 : 21 fonctions dont chaque
  ``load`` et chaque ``save`` est sous un ``with board_lock``, moins
  ``set_state`` et ``new_task``). Relevé lexical, ne suit ni appelants ni alias,
  et ne voit pas un verrou scindé (la continuité).
- SUPPOSÉ : Windows (branche ``msvcrt``).

Pourquoi l'injection de l'entrelacement est sur ``load`` : c'est le bord que
la propriété poursuit (charger sous le verrou) ; injecté sur ``save``, le même
patron reste VERT quand le chargement sort du verrou (plan T-00001063, N3) —
chaque couture ne tient qu'un bord, d'où la sonde. Pourquoi la lecture PRÉCÈDE
l'attente : un A qui attendrait d'abord relirait l'écriture de B et masquerait
la perte. L'entrelacement ne revendique ni l'écriture ni la continuité : c'est
la sonde qui les tient.

Poignée : ``board_lock_ferme_sa_poignee_sur_toute_sortie`` exige, sur une
écriture refusée à l'ouverture (``ENOSPC``) ET sur une libération refusée
(``EIO`` sur ``LOCK_UN``, POSIX seulement), l'exception PROPAGÉE, la poignée
réelle FERMÉE et la profondeur de ré-entrée de CE verrou revenue à 0.

Poignée de ``store_lock`` (T-00001080), bornée PAR SORTIE (L-00000111, L-00000187) :
``store_lock_ferme_sa_poignee_sur_chaque_sortie_epinglee`` épingle HUIT sorties par
store — ``stat`` refusé, ``ecriture`` refusée, ``delai``, ``corps`` qui lève,
``fermeture`` qui lève, ``liberation`` refusée, ``interruption`` (``KeyboardInterrupt``
SYNCHRONE levé par le corps), ``interruption_liberation`` (``BaseException`` levée à
la couture de libération) — et exige l'exception PROPAGÉE, la poignée réelle
FERMÉE et la profondeur de CE verrou à 0. Le refus de libération y est ARMÉ là où le
verrou n'est jamais acquis (le garde ``if acquired``, épinglé du seul côté
NON-appel) ; ``liberation`` ré-acquiert AVANT le nettoyage (une poignée fuitée tient
son ``flock``) : la jambe SEULE rougit 2 cas ici (``[specs.py-liberation]``,
``[ledger.py-liberation]``), le 3e dans ``test_run_export_verrou.py``. MESURÉ avec la
poignée RETENUE par le banc ; hors banc, ``ecriture`` se ferme au comptage de
références et ``liberation`` au prochain ramasse-miettes. NON épinglé : les
interruptions ASYNCHRONES (un signal tombé dans le ``finally`` : non injecté). Même
matrice pour ``_verrou_export`` : ``agentic_v3/tests/test_run_export_verrou.py``.

Windows non mesuré : jambe non bloquante, T-00000744.
"""
from __future__ import annotations

import contextlib
import errno
import inspect
import os
import pathlib
import subprocess
import sys
import time

import pytest

import ledger
import specs

BIN = os.path.dirname(os.path.abspath(specs.__file__))


def _add_specs(root, tag):
    return specs.add_entry(root, "T-1", "delta", tag)


def _add_ledger(root, tag):
    return ledger.add_entry(root, "lesson", tag)


# (module, its error class, an add callable, the import name B's driver uses)
STORES = [
    pytest.param(specs, specs.SpecsError, _add_specs, "specs", id="specs.py"),
    pytest.param(ledger, ledger.LedgerError, _add_ledger, "ledger", id="ledger.py"),
]


def _count(module, root) -> int:
    return len(module.load(root)["entries"])


def _lock_held(module) -> bool:
    depths = getattr(module._STORE_LOCK_DEPTH, "paths", {})
    return any(v > 0 for v in depths.values())


# --- marker helpers: a causal event, never a duration -----------------------
def _touch(sig: str, name: str) -> None:
    open(os.path.join(sig, name), "w").close()


def _wait_for_any(sig: str, names, timeout: float = 30.0) -> str:
    """Spin until one of ``names`` appears and return it. The timeout is a
    SAFETY NET whose expiry FAILS the test — it never gates a green path."""
    deadline = time.monotonic() + timeout
    while True:
        for name in names:
            if os.path.exists(os.path.join(sig, name)):
                return name
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for any of {names} in {sig}")
        time.sleep(0.005)


# The subprocess writer B. It imports the SAME store module (fresh interpreter,
# so its save is NOT the test's monkeypatched one), waits for A to hold the lock
# (marker A_charge), then contends: its wrapped _lock_poll_sleep writes B_contend
# on the first missed acquisition, and B_ecrit lands after its save returns —
# or B_echec if the write raised, so A never waits out its bound on a dead B.
_DRIVER = r'''
import importlib, os, sys, time
bin_dir, mod_name, root, sig, tag = sys.argv[1:6]
sys.path.insert(0, bin_dir)
m = importlib.import_module(mod_name)

def wait_for(name, timeout=30.0):
    deadline = time.monotonic() + timeout
    p = os.path.join(sig, name)
    while not os.path.exists(p):
        if time.monotonic() > deadline:
            raise SystemExit("B: timed out waiting for " + name)
        time.sleep(0.005)

def touch(name):
    open(os.path.join(sig, name), "w").close()

wait_for("A_charge")
real_sleep = m._lock_poll_sleep
state = {"contended": False}
def wrapped():
    if not state["contended"]:
        state["contended"] = True
        touch("B_contend")
    real_sleep()
m._lock_poll_sleep = wrapped
# B's lock bound is a SAFETY NET like A's marker wait: generous, never the
# binding clock (L-00000288). board_lock/store_lock read it in the BODY.
if mod_name == "tasks":
    m._LOCK_TIMEOUT_SECONDS = 30.0
else:
    m._STORE_LOCK_TIMEOUT_SECONDS = 30.0

try:
    if mod_name == "specs":
        m.add_entry(root, "T-1", "delta", tag)
    elif mod_name == "tasks":
        m.new_task(root, tag, "dev-multi")
    else:
        m.add_entry(root, "lesson", tag)
except BaseException:
    touch("B_echec")  # B died BEFORE writing: A stops waiting at once
    raise
touch("B_ecrit")
'''


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_le_verrou_est_tenu_pendant_save(module, err, add, mod_name, tmp_path, monkeypatch):
    """The mutator holds the lock ACROSS save, not merely around the append."""
    root = str(tmp_path)
    real_save = module.save
    seen = {}

    def spy(root_arg, data):
        seen["held"] = _lock_held(module)
        return real_save(root_arg, data)

    monkeypatch.setattr(module, "save", spy)
    add(root, "x")
    assert seen.get("held") is True, f"{mod_name}: save ran without the store lock held"


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_une_lecture_n_attend_jamais(module, err, add, mod_name, tmp_path, monkeypatch):
    """A read acquires NOTHING. Booby-trap the acquire primitive; a read that
    tried to lock would detonate it."""
    root = str(tmp_path)
    add(root, "seed")

    def boom(handle):
        raise AssertionError(f"{mod_name}: a read acquired the store lock")

    monkeypatch.setattr(module, "_acquire_lock_once", boom)
    data = module.load(root)  # a bare read
    assert len(data["entries"]) == 1
    module.render_list(root)  # the CLI read path, also lock-free


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_le_depassement_refuse_bruyamment_store_intact(
    module, err, add, mod_name, tmp_path, monkeypatch
):
    """A lock nobody can take makes the mutator RAISE loudly and touch nothing.
    Clock-free: the bound is monkeypatched to 0, so the deadline is immediate
    and _lock_poll_sleep is never reached."""
    root = str(tmp_path)
    add(root, "seed")
    before = module.store_path(root).read_bytes()

    monkeypatch.setattr(module, "_STORE_LOCK_TIMEOUT_SECONDS", 0.0)

    def always_busy(handle):
        raise OSError("held elsewhere")

    monkeypatch.setattr(module, "_acquire_lock_once", always_busy)
    with pytest.raises(err):
        add(root, "should-not-land")
    after = module.store_path(root).read_bytes()
    assert before == after, f"{mod_name}: a lock timeout must leave the store intact"


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_la_liberation_survit_a_un_refus_transitoire(
    module, err, add, mod_name, tmp_path, monkeypatch
):
    """The Windows unlock can be refused transiently too; the release retries
    and the write still lands. Clock-free: one injected refusal, then the real
    unlock."""
    root = str(tmp_path)
    real_release = module._release_lock_once
    calls = {"n": 0}

    def flaky(handle):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient unlock refusal")
        return real_release(handle)

    monkeypatch.setattr(module, "_release_lock_once", flaky)
    add(root, "x")
    assert calls["n"] >= 2, f"{mod_name}: release did not retry after a transient refusal"
    assert _count(module, root) == 1


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_N_ecritures_serialisees_donnent_N_entrees(
    module, err, add, mod_name, tmp_path
):
    """NON-VACUITY: the lock does not break the ordinary sequential path. Five
    adds give five entries with five distinct ids."""
    root = str(tmp_path)
    for i in range(5):
        add(root, f"entry-{i}")
    entries = module.load(root)["entries"]
    assert len(entries) == 5
    assert len({e["id"] for e in entries}) == 5


@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_un_entrelacement_force_ne_perd_aucune_entree(
    module, err, add, mod_name, tmp_path, monkeypatch
):
    """The property the whole volet exists for: two writers racing on one store
    lose NO entry. A holds the lock and waits; B (a real subprocess) must
    CONTEND before A commits, so A writes, releases, B re-reads and appends —
    two entries. See the module docstring for why this is deterministic and why
    removing the lock turns it red."""
    root = str(tmp_path)
    sig = str(tmp_path / "signals")
    os.makedirs(sig, exist_ok=True)
    driver = str(tmp_path / "driver_b.py")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write(_DRIVER)

    real_save = module.save
    received = {}

    def a_save(root_arg, data):
        _touch(sig, "A_charge")
        received["marker"] = _wait_for_any(sig, ["B_contend", "B_ecrit", "B_echec"])
        return real_save(root_arg, data)

    proc = subprocess.Popen(
        [sys.executable, driver, BIN, mod_name, root, sig, "B"]
    )
    try:
        monkeypatch.setattr(module, "save", a_save)
        add(root, "A")
    finally:
        monkeypatch.undo()  # restore save before we read the result
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise

    assert proc.returncode == 0, f"{mod_name}: writer B subprocess failed"
    assert received.get("marker") == "B_contend", (
        f"{mod_name}: A did not observe B CONTEND for the lock — the writers were "
        f"not serialised (A saw {received.get('marker')!r})"
    )
    entries = module.load(root)["entries"]
    assert len(entries) == 2, (
        f"{mod_name}: expected 2 entries after the forced interleave, got "
        f"{len(entries)} — an entry was lost"
    )
    assert len({e["id"] for e in entries}) == 2, f"{mod_name}: the two entries share an id"


def test_board_lock_appelle_la_couture():
    """BK-402 (1), clock-free: board_lock reaches its poll nap THROUGH the seam,
    so the short-circuited-seam mutation reds HERE at once, not at a 30 s bound."""
    # Imported HERE: a tasks part that fails to load errors THIS case only.
    import tasks

    assert "_lock_poll_sleep" in inspect.unwrap(tasks.board_lock).__code__.co_names, (
        "tasks_stockage.py: board_lock no longer calls _lock_poll_sleep"
    )


def test_board_lock_un_entrelacement_force_ne_perd_aucune_tache(tmp_path, monkeypatch):
    """The same property for the BOARD (T-00000730): two ``new_task`` racing on
    one TASKS.json lose NO task. A holds ``board_lock`` inside its patched
    ``tasks.save`` and waits; B (a real subprocess, unpatched ``save``) must
    CONTEND — its wrapped ``tasks._lock_poll_sleep`` writes ``B_contend`` — before
    A commits, so A writes, releases, B re-reads and appends: two tasks, two ids.
    Outside ``STORES`` on purpose: see the module docstring. The env points the
    project root at the board root (``racine``) and the state dir and the event
    dir at a tmp env dir, and B inherits it (same isolation as
    test_tasks_decoupe's
    ``test_g_un_patch_sur_le_module_atteint_le_code_d_une_partie``)."""
    # Imported HERE: a tasks part that fails to load errors THIS case only.
    import tasks

    env_dir = tmp_path / "env"
    env_dir.mkdir()
    racine = tmp_path / "racine"
    racine.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(racine))
    for var in ("CADRE_STATE_DIR", "AGENTS_EVENTS_DIR"):
        monkeypatch.setenv(var, str(env_dir))
    root = str(racine)
    sig = str(tmp_path / "signals")
    os.makedirs(sig, exist_ok=True)
    driver = str(tmp_path / "driver_b.py")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write(_DRIVER)

    real_save = tasks.save
    received = {}

    def a_save(root_arg, data):
        _touch(sig, "A_charge")
        received["marker"] = _wait_for_any(sig, ["B_contend", "B_ecrit", "B_echec"])
        return real_save(root_arg, data)

    proc = subprocess.Popen(
        [sys.executable, driver, BIN, "tasks", root, sig, "B"]
    )
    try:
        monkeypatch.setattr(tasks, "save", a_save)
        tasks.new_task(root, "A", "dev-multi")
    finally:
        monkeypatch.undo()  # restore save (and the env) before we read the result
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise

    assert proc.returncode == 0, "tasks.py: writer B subprocess failed"
    assert received.get("marker") == "B_contend", (
        "tasks.py: A did not observe B CONTEND for board_lock — the writers were "
        f"not serialised (A saw {received.get('marker')!r})"
    )
    board = tasks.load(root)["tasks"]
    assert len(board) == 2, (
        f"tasks.py: expected 2 tasks after the forced interleave, got {len(board)} "
        "— a task was lost"
    )
    assert len({t["id"] for t in board}) == 2, "tasks.py: the two tasks share an id"
    assert sorted(t["task"] for t in board) == ["A", "B"], (
        f"tasks.py: expected tasks ['A', 'B'], got {sorted(t['task'] for t in board)}"
    )


# --- set_state (T-00001063): see the module docstring for the bound of each leg
def _board_a_une_tache(tmp_path, monkeypatch):
    """A board rooted at ``racine`` holding ONE task ``A``, isolated exactly like
    ``board_lock_un_entrelacement_force_ne_perd_aucune_tache`` (project root at
    ``racine``, state dir and event dir under tmp). Returns (tasks, root, id of A)."""
    # Imported HERE: a tasks part that fails to load errors THIS case only.
    import tasks

    env_dir = tmp_path / "env"
    env_dir.mkdir()
    racine = tmp_path / "racine"
    racine.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(racine))
    for var in ("CADRE_STATE_DIR", "AGENTS_EVENTS_DIR"):
        monkeypatch.setenv(var, str(env_dir))
    root = str(racine)
    tasks.new_task(root, "A", "dev-multi")
    return tasks, root, tasks.load(root)["tasks"][0]["id"]


def _transitionner(tasks, root, tid, verbe):
    return tasks.set_state(root, tid, verbe, stage="témoin" if verbe == "done" else None)


@pytest.mark.parametrize("verbe", ["running", "done"])
def test_set_state_tient_un_seul_verrou_du_chargement_a_l_ecriture(verbe, tmp_path, monkeypatch):
    """ONE assertion, four legs: EVERY ``load`` and EVERY ``save`` of ``set_state``
    runs with THIS board's lock held (load under lock, save under lock), and all
    of them inside the SAME outermost acquisition (the lock is CONTINUOUS from
    load to save). The counter keys on THIS board's lock path, so a section held
    under another lock file (``POST_TASK_DONE.lock``) counts nothing and reds."""
    tasks, root, tid = _board_a_une_tache(tmp_path, monkeypatch)
    cle = os.path.normcase(str(tasks.lock_path(root).resolve()))  # THE board lock, by its key

    def tenu() -> bool:
        return getattr(tasks._BOARD_LOCK_DEPTH, "paths", {}).get(cle, 0) > 0

    real_lock, real_load, real_save = tasks.board_lock, tasks.load, tasks.save
    acquisitions = [0]
    chargements = []  # (lock held, outermost acquisitions so far) at EACH load
    ecritures = []  # the same at EACH save

    @contextlib.contextmanager
    def compte(r, timeout_seconds=None, name=None):
        if os.path.normcase(str(tasks.lock_path(r, name).resolve())) == cle and not tenu():
            acquisitions[0] += 1  # only the OUTERMOST acquisition of THIS board's lock
        with real_lock(r, timeout_seconds, name):
            yield

    def sonde_load(r):
        chargements.append((tenu(), acquisitions[0]))
        return real_load(r)

    def sonde_save(r, d):
        ecritures.append((tenu(), acquisitions[0]))
        return real_save(r, d)

    monkeypatch.setattr(tasks, "board_lock", compte)
    monkeypatch.setattr(tasks, "load", sonde_load)
    monkeypatch.setattr(tasks, "save", sonde_save)
    _transitionner(tasks, root, tid, verbe)
    assert chargements and all(x == (True, 1) for x in chargements), (
        f"set_state {verbe}: (lock held, acquisitions) at each load = {chargements}"
    )
    assert ecritures and all(x == (True, 1) for x in ecritures), (
        f"set_state {verbe}: (lock held, acquisitions) at each save = {ecritures}"
    )


@pytest.mark.parametrize("verbe", ["running", "done"])
def test_set_state_un_entrelacement_force_ne_perd_aucune_tache(verbe, tmp_path, monkeypatch):
    """Real EXCLUSION between two processes: A's ``set_state`` READS the board
    (patched ``tasks.load``), THEN signals ``A_charge`` and waits; B (a real
    subprocess, ``new_task "B"``, the unchanged ``_DRIVER``) must CONTEND before
    A writes, so B appends after A releases: tasks A and B, A in state ``verbe``.
    The read comes FIRST: waiting first would re-read B's write and mask the
    loss. This case claims neither the write leg nor continuity (the probe does)."""
    tasks, root, tid = _board_a_une_tache(tmp_path, monkeypatch)
    sig = str(tmp_path / "signals")
    os.makedirs(sig, exist_ok=True)
    driver = str(tmp_path / "driver_b.py")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write(_DRIVER)

    real_load = tasks.load
    received = {}
    armed = [True]

    def a_load(root_arg):
        data = real_load(root_arg)  # READ first, wait AFTER
        if armed[0]:
            armed[0] = False  # only the first load waits
            _touch(sig, "A_charge")
            received["marker"] = _wait_for_any(sig, ["B_contend", "B_ecrit", "B_echec"])
        return data

    proc = subprocess.Popen(
        [sys.executable, driver, BIN, "tasks", root, sig, "B"]
    )
    try:
        monkeypatch.setattr(tasks, "load", a_load)
        _transitionner(tasks, root, tid, verbe)
    finally:
        monkeypatch.undo()  # restore load (and the env) before we read the result
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise

    assert proc.returncode == 0, "tasks.py: writer B subprocess failed"
    assert received.get("marker") == "B_contend", (
        f"tasks.py: set_state {verbe} did not see B CONTEND for board_lock — the "
        f"writers were not serialised (A saw {received.get('marker')!r})"
    )
    board = tasks.load(root)["tasks"]
    assert sorted(t["task"] for t in board) == ["A", "B"], (
        f"tasks.py: expected tasks ['A', 'B'] after set_state {verbe}, got "
        f"{sorted(t['task'] for t in board)} — a task was lost"
    )
    assert next(t for t in board if t["task"] == "A")["state"] == verbe


@pytest.mark.parametrize(
    "sortie",
    [
        "ecriture",
        pytest.param(
            "liberation",
            marks=pytest.mark.skipif(os.name == "nt", reason="msvcrt non mesuré, T-00000744"),
        ),
    ],
)
def test_board_lock_ferme_sa_poignee_sur_toute_sortie(sortie, tmp_path, monkeypatch):
    """``board_lock`` closes its handle on EVERY exit (S-00003443, S-00003558):
    ``ecriture`` — the first write to a fresh lock file raises ``ENOSPC``;
    ``liberation`` — ``flock(LOCK_UN)`` raises ``EIO``. Each time the exception
    PROPAGATES (kept by ``pytest.raises``), the REAL handle is closed, and the
    re-entrancy depth of THIS lock is back to 0 (a stale depth would let the
    next ``board_lock`` of this thread re-enter WITHOUT any ``flock``)."""
    # Imported HERE: a tasks part that fails to load errors THIS case only.
    import tasks

    verrou = tasks.lock_path(tmp_path)
    ouvertes = []
    real_open = pathlib.Path.open

    class EchecEcriture:  # proxy: write raises ENOSPC, everything else reaches the real handle
        def __init__(self, h):
            self._h = h

        def write(self, *_):
            raise OSError(errno.ENOSPC, "No space left on device")

        def __getattr__(self, n):
            return getattr(self._h, n)

    def ouvre(self, *a, **k):
        h = real_open(self, *a, **k)
        if self == verrou:  # the lock file ONLY
            ouvertes.append(h)
            return EchecEcriture(h) if sortie == "ecriture" else h
        return h

    monkeypatch.setattr(pathlib.Path, "open", ouvre)
    attendu = errno.ENOSPC
    if sortie == "liberation":
        import fcntl

        real_flock = fcntl.flock
        attendu = errno.EIO

        def flock(fd, op):
            if op & fcntl.LOCK_UN:
                raise OSError(errno.EIO, "unlock refused")
            return real_flock(fd, op)

        monkeypatch.setattr(fcntl, "flock", flock)
    try:
        with pytest.raises(OSError) as ei:
            with tasks.board_lock(tmp_path):
                pass
        monkeypatch.undo()
        fermees = [h.closed for h in ouvertes]
    finally:
        for h in ouvertes:
            h.close()  # the test never leaks, whatever the verdict
    assert ei.value.errno == attendu
    assert ouvertes and all(fermees), f"handle(s) left open on exit {sortie!r}: {fermees}"
    assert tasks._BOARD_LOCK_DEPTH.paths.get(os.path.normcase(str(verrou.resolve())), 0) == 0, (
        f"stale board_lock depth after exit {sortie!r}"
    )


@pytest.mark.skipif(os.name == "nt", reason="flock POSIX : la poignée concurrente est tenue par le banc ; msvcrt non mesuré, T-00000744")
def test_board_lock_echeance_leve_boarderror_ferme_sa_poignee_et_ne_laisse_aucune_profondeur(tmp_path, monkeypatch):
    """Troisième sortie de `board_lock`, la plus fréquente après le succès : le verrou est TENU par un autre descripteur, l'attente
    expire. `BoardError` (« timed out waiting for board lock »), la poignée ouverte par CET appel est FERMÉE, la profondeur de
    ré-entrée de CE verrou est 0. Aucune levée de ce chemin n'était jusqu'ici épinglée. Le garde-fou compte les sommeils : une attente
    sans borne (mutant : échéance remplacée par `if False`) LÈVE `AssertionError` au lieu de bloquer le banc."""
    import fcntl

    import tasks

    verrou = tasks.lock_path(tmp_path)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    ouvertes, real_open = [], pathlib.Path.open

    def ouvre(self, *a, **k):
        h = real_open(self, *a, **k)
        if self == verrou:
            ouvertes.append(h)
        return h

    sommeils = [0]

    def sommeil():
        sommeils[0] += 1
        assert sommeils[0] < 1000, "attente sans borne : l'échéance n'est jamais atteinte"
        time.sleep(0.001)

    tenu = os.open(verrou, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(tenu, fcntl.LOCK_EX | fcntl.LOCK_NB)  # une AUTRE description de fichier : conflit, même dans ce processus
        monkeypatch.setattr(pathlib.Path, "open", ouvre)
        monkeypatch.setattr(tasks, "_lock_poll_sleep", sommeil)
        with pytest.raises(tasks.BoardError, match="timed out waiting for board lock"):
            with tasks.board_lock(tmp_path, timeout_seconds=0.05):
                pytest.fail("verrou acquis alors qu'un autre descripteur le tient")
        monkeypatch.undo()
        fermees = [h.closed for h in ouvertes]
    finally:
        os.close(tenu)
        for h in ouvertes:
            h.close()  # le banc ne fuit jamais, quel que soit le verdict
    assert sommeils[0] > 0, "le verrou n'a jamais été disputé : le banc ne mesure rien"
    assert ouvertes and all(fermees), f"poignée(s) laissée(s) ouverte(s) à l'échéance : {fermees}"
    assert tasks._BOARD_LOCK_DEPTH.paths.get(os.path.normcase(str(verrou.resolve())), 0) == 0, "profondeur périmée après l'échéance"


class Interruption(BaseException):
    """A non-``Exception`` raised at the RELEASE seam (T-00001080, A-C1)."""


@pytest.mark.parametrize("sortie", ["stat", "ecriture", "delai", "corps", "fermeture", "liberation", "interruption", "interruption_liberation"])
@pytest.mark.parametrize("module, err, add, mod_name", STORES)
def test_store_lock_ferme_sa_poignee_sur_chaque_sortie_epinglee(
    module, err, add, mod_name, sortie, tmp_path, monkeypatch
):
    """``store_lock`` closes its handle on each of EIGHT pinned exits (T-00001080;
    the shape of ``board_lock_ferme_sa_poignee_sur_toute_sortie``): ``stat`` —
    ``Path.stat`` of the lock file raises ``EACCES``; ``ecriture`` — the first
    write raises ``ENOSPC``; ``delai`` — the lock is never free and the bound
    expires (``err``); ``corps`` — the body raises ``RuntimeError``;
    ``fermeture`` — ``close()`` raises ``EIO`` once the real handle is closed;
    ``liberation`` — every ``_release_lock_once`` raises ``EIO``;
    ``interruption`` — the body raises ``KeyboardInterrupt``, a SYNCHRONOUS
    ``BaseException`` that tells ``finally`` apart from ``except Exception``;
    ``interruption_liberation`` — ``_release_lock_once`` raises ``Interruption``,
    a ``BaseException`` that tells the inner ``finally`` from ``except OSError``.
    Each time the exception PROPAGATES, the REAL handle is closed and the
    re-entrancy depth of THIS lock is back to 0. The ``EIO`` release refusal is
    ARMED on ``stat``, ``ecriture``, ``delai`` and ``liberation`` — never on
    ``corps``, ``fermeture`` or ``interruption`` (it would mask the error under
    test), nor on ``interruption_liberation`` (its own fault holds that seam) —
    so a release attempted when the lock was never acquired replaces the
    expected exception (the ``if acquired`` guard, pinned on its NON-call side
    only: a release skipped after an acquisition is not seen, ``close()`` drops
    the ``flock`` on POSIX). ``liberation`` also re-acquires BEFORE the cleanup:
    a leaked handle still holds its ``flock``. NOT pinned: Windows (T-00000744)
    and ASYNCHRONOUS interrupts (a signal landing in the ``finally``; not
    injected). Measured with the handle RETAINED by the bench; unretained, a
    refused write closes by refcount and a refused release at the next garbage
    collection."""
    root = str(tmp_path)
    verrou = module.lock_path(root)
    ouvertes = []
    real_open, real_stat = pathlib.Path.open, pathlib.Path.stat

    class Mandataire:  # proxy: ONE fault injected, everything else reaches the real handle
        def __init__(self, h):
            self._h = h

        def write(self, *a):
            if sortie == "ecriture":
                raise OSError(errno.ENOSPC, "No space left on device")
            return self._h.write(*a)

        def close(self):
            self._h.close()  # the REAL handle is closed first: the fault is the error, never a leak
            if sortie == "fermeture":
                raise OSError(errno.EIO, "close failed")

        def __getattr__(self, n):
            return getattr(self._h, n)

    def ouvre(self, *a, **k):
        h = real_open(self, *a, **k)
        if self == verrou:  # the lock file ONLY
            ouvertes.append(h)
            return Mandataire(h) if sortie in ("ecriture", "fermeture") else h
        return h

    def stat(self, *a, **k):
        if self == verrou and ouvertes:  # AFTER the handle is open
            raise OSError(errno.EACCES, "stat refused")
        return real_stat(self, *a, **k)

    def refus(_handle):
        raise OSError(errno.EIO, "unlock refused")

    def occupe(_handle):
        raise OSError(errno.EAGAIN, "held elsewhere")

    def coupe(_handle):
        raise Interruption("release interrupted")

    monkeypatch.setattr(pathlib.Path, "open", ouvre)
    if sortie == "stat":
        monkeypatch.setattr(pathlib.Path, "stat", stat)
    if sortie == "delai":
        monkeypatch.setattr(module, "_acquire_lock_once", occupe)
    if sortie not in ("corps", "fermeture", "interruption", "interruption_liberation"):  # armed where the lock is never acquired, and as the exit itself
        monkeypatch.setattr(module, "_release_lock_once", refus)
        monkeypatch.setattr(module, "_lock_poll_sleep", lambda: None)
    if sortie == "interruption_liberation":
        monkeypatch.setattr(module, "_release_lock_once", coupe)
    exc, code = {
        "stat": (OSError, errno.EACCES),
        "ecriture": (OSError, errno.ENOSPC),
        "delai": (err, None),
        "corps": (RuntimeError, None),
        "fermeture": (OSError, errno.EIO),
        "liberation": (OSError, errno.EIO),
        "interruption": (KeyboardInterrupt, None),
        "interruption_liberation": (Interruption, None),
    }[sortie]
    try:
        with pytest.raises(exc) as ei:
            # [delai]: X2 dies by bound > 0 OR armed refusal, survives 0.0 AND disarmed (plan T-00001080:51): keep both
            with module.store_lock(root, timeout_seconds=0.05 if sortie == "delai" else None):
                if sortie == "corps":
                    raise RuntimeError("boom")
                if sortie == "interruption":
                    raise KeyboardInterrupt
        monkeypatch.undo()
        fermees = [h.closed for h in ouvertes]
        if sortie == "liberation" and os.name != "nt":
            with module.store_lock(root, timeout_seconds=0.5):  # BEFORE the cleanup
                pass
    finally:
        for h in ouvertes:
            h.close()  # the test never leaks, whatever the verdict
    assert code is None or ei.value.errno == code
    assert ouvertes and all(fermees), f"{mod_name}: handle(s) left open on exit {sortie!r}: {fermees}"
    assert module._STORE_LOCK_DEPTH.paths.get(os.path.normcase(str(verrou.resolve())), 0) == 0, (
        f"{mod_name}: stale store_lock depth after exit {sortie!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
