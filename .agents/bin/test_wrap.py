"""Tests for wrap.py — the console mirror launcher (T-00000087, M5b).

PLATFORM DISCIPLINE (L-00000068). CI replays ubuntu only, this kit is developed
on Windows, and a test that measures a platform fact is MARKED rather than
loosened: the POSIX pty tests are `skipUnless(os.name != "nt")`, the ConPTY ones
`skipUnless(winpty importable)`. What runs EVERYWHERE is the part that has no
platform in it — the ring, the atomic meta, the bounded replace — plus the
DEGRADED branch, which is precisely the branch a Windows box without pywinpty
(this one) actually takes in production.

An assertion weak enough to pass on both platforms would measure neither.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("wrap", HERE / "wrap.py")
wrap = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = wrap
_spec.loader.exec_module(wrap)

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="branche POSIX (pty stdlib)")
WINPTY_ONLY = pytest.mark.skipif(
    not wrap.winpty_available(),
    reason="branche ConPTY : pywinpty non importable sur cette machine",
)

# A deterministic 64-byte record, so a reader can assert on CONTIGUITY rather
# than on a length it would have to race the writer for.
_RECORD = 64


def _record(i: int) -> bytes:
    return f"{i:06d}".encode() + b"x" * (_RECORD - 7) + b"\n"


@pytest.fixture
def spool_dir(tmp_path, monkeypatch):
    directory = tmp_path / "term"
    monkeypatch.setenv("AGENTS_TERM_DIR", str(directory))
    return directory


@pytest.fixture
def small_ring(monkeypatch):
    """A 64 KiB / 16 KiB ring. The recipe under test is about ORDER, not about
    megabytes; shrinking it is what lets the concurrent-reader test force a
    dozen rotations in a second instead of writing 50 MB."""
    monkeypatch.setattr(wrap, "_SPOOL_CAP_BYTES", 64 * 1024)
    monkeypatch.setattr(wrap, "_SPOOL_KEEP_BYTES", 16 * 1024)
    monkeypatch.setattr(wrap, "_ROTATE_BACKOFF_S", 0.0)


# ---------------------------------------------------------------------------
# Paths, sid, meta — no platform in any of this
# ---------------------------------------------------------------------------

def test_le_repertoire_du_spool_suit_la_convention_events(monkeypatch, tmp_path):
    """Resolved from the FILE, not from cwd (a launcher runs from anywhere),
    with the same `AGENTS_*` override every other state reader in this kit
    honours — that override is what lets dashboard.py's suite point at a tmp
    tree instead of this developer's real sessions."""
    monkeypatch.delenv("AGENTS_TERM_DIR", raising=False)
    assert wrap.term_dir() == HERE.parent / "state" / "local" / "term"
    monkeypatch.setenv("AGENTS_TERM_DIR", str(tmp_path / "ailleurs"))
    assert wrap.term_dir() == tmp_path / "ailleurs"


def test_le_meta_ne_porte_que_le_nom_de_la_commande_jamais_argv(spool_dir):
    """THE privacy property of this feature. A mirror list that showed the full
    command line would publish `--api-key …` to every reader of `/api/term`;
    the meta therefore carries the BASENAME and nothing else, and no key of it
    holds an argument or an environment variable."""
    spool = wrap.Spool(spool_dir, "sid-1", "/usr/local/bin/claude", 4242, 80, 24, "posix")
    try:
        meta = spool.meta()
        assert meta["cmd"] == "claude"
        assert set(meta) == {"sid", "cmd", "pid", "cols", "rows", "started",
                             "ended", "gen", "resize"}
        blob = json.dumps(meta)
        assert "--api-key" not in blob and "/usr/local/bin" not in blob
    finally:
        spool.close()


def test_une_collision_de_sid_est_refusee_net(spool_dir):
    """Exclusive ("x") creation. Two sessions interleaving bytes into one spool
    would produce a mirror that is wrong in a way no reader could detect, so a
    collision fails loudly at launch instead."""
    first = wrap.Spool(spool_dir, "sid-x", "claude", 1, 80, 24, "posix")
    try:
        with pytest.raises(FileExistsError):
            wrap.Spool(spool_dir, "sid-x", "codex", 2, 80, 24, "posix")
    finally:
        first.close()


def test_close_horodate_ended_ce_qui_distingue_une_fin_d_un_crash(spool_dir):
    spool = wrap.Spool(spool_dir, "sid-2", "codex", 7, 80, 24, "posix")
    assert wrap.read_meta(spool.meta_path)["ended"] is None
    spool.close()
    assert wrap.read_meta(spool.meta_path)["ended"] is not None


def test_read_meta_ne_leve_jamais(tmp_path):
    assert wrap.read_meta(tmp_path / "absent.json") is None
    broken = tmp_path / "casse.json"
    broken.write_text("{ pas du json", encoding="utf-8")
    assert wrap.read_meta(broken) is None
    listy = tmp_path / "liste.json"
    listy.write_text("[1,2]", encoding="utf-8")
    assert wrap.read_meta(listy) is None


def test_pid_alive_a_trois_reponses_dont_je_ne_sais_pas():
    """`None` is not a fudge: a session whose meta has no `ended` and whose pid
    cannot be resolved is UNKNOWN, and `/api/term` renders it as such rather
    than guessing `live` (a ghost) or `ended` (a lie)."""
    assert wrap.pid_alive(os.getpid()) is True
    assert wrap.pid_alive(0) is None
    assert wrap.pid_alive("pas un pid") is None


@pytest.mark.skipif(os.name != "nt", reason="sémantique os.kill mesurée sur Windows")
def test_la_sonde_de_liveness_ne_tue_pas_ce_qu_elle_sonde_sur_windows():
    """MEASURED Windows fact, not a style preference: CPython implements
    `os.kill` on Windows as OpenProcess + TerminateProcess, so `os.kill(pid, 0)`
    KILLS the target with exit code 0. `pid_alive` must go through
    OpenProcess/GetExitCodeProcess — this test proves the probed child survives
    being probed."""
    child = subprocess.Popen([sys.executable, "-c",
                              "import time; time.sleep(5)"])
    try:
        assert wrap.pid_alive(child.pid) is True
        time.sleep(0.2)
        assert child.poll() is None, "la sonde a tué le processus qu'elle sondait"
    finally:
        child.kill()
        child.wait(timeout=10)


# ---------------------------------------------------------------------------
# The bounded replace — the piece the rotation's safety rests on
# ---------------------------------------------------------------------------

def test_le_replace_est_retente_sous_une_prise_transitoire(tmp_path, monkeypatch):
    """A reader holding a handle for a few milliseconds is the NORMAL case on
    Windows, so the swap retries instead of giving up on the first refusal.
    Simulated rather than raced: `os.replace` is made to refuse twice, and the
    assertion is on the attempt count, which a race could not pin down."""
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_bytes(b"neuf")
    dst.write_bytes(b"vieux")
    real = os.replace
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("handle transitoire")
        return real(a, b)

    monkeypatch.setattr(wrap.os, "replace", flaky)
    assert wrap._replace_with_retry(src, dst, attempts=5, sleep_s=0.001) is True
    assert calls["n"] == 3
    assert dst.read_bytes() == b"neuf"


def test_le_replace_abandonne_apres_un_nombre_borne_d_essais(tmp_path, monkeypatch):
    """BOUNDED, and it returns False rather than raising: every caller has a
    correct do-nothing fallback, while an exception escaping into the output
    loop would kill the mirror AND the terminal it feeds."""
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_bytes(b"neuf")
    dst.write_bytes(b"vieux")
    calls = {"n": 0}

    def always_busy(a, b):
        calls["n"] += 1
        raise PermissionError("verrouillé")

    monkeypatch.setattr(wrap.os, "replace", always_busy)
    assert wrap._replace_with_retry(src, dst, attempts=4, sleep_s=0.001) is False
    assert calls["n"] == 4
    assert dst.read_bytes() == b"vieux"


# ---------------------------------------------------------------------------
# The ring
# ---------------------------------------------------------------------------

def test_la_rotation_borne_le_spool_et_publie_une_generation(spool_dir, small_ring):
    spool = wrap.Spool(spool_dir, "sid-ring", "claude", 1, 80, 24, "posix")
    try:
        for i in range(2000):  # 128 KiB, i.e. two caps
            spool.write(_record(i))
        assert spool.gen >= 1
        assert spool.raw_path.stat().st_size <= wrap._SPOOL_CAP_BYTES
        on_disk = wrap.read_meta(spool.meta_path)
        assert on_disk["gen"] == spool.gen
        assert not spool.part_path.exists(), "le fichier de rotation doit être consommé"
    finally:
        spool.close()


def test_la_generation_est_publiee_AVANT_le_contenu(spool_dir, small_ring):
    """THE ordering property. A reader that saw new content under an old
    generation would splice two different files together at its own offset and
    render a terminal that never existed. So the meta bump lands on disk BEFORE
    the swap is even attempted — asserted by reading the meta from INSIDE the
    swap."""
    spool = wrap.Spool(spool_dir, "sid-order", "claude", 1, 80, 24, "posix")
    observed = []
    real_replace = wrap._replace_with_retry

    def observing(src, dst, **kwargs):
        if str(dst).endswith(".raw"):
            observed.append(wrap.read_meta(spool.meta_path)["gen"])
        return real_replace(src, dst, **kwargs)

    try:
        wrap._replace_with_retry = observing
        for i in range(2000):
            spool.write(_record(i))
    finally:
        wrap._replace_with_retry = real_replace
        spool.close()
    assert observed, "aucune rotation n'a eu lieu"
    # At the moment of each swap, the meta on disk already carried the
    # generation that swap produces.
    assert observed == list(range(1, len(observed) + 1))


def test_une_rotation_abandonnee_ne_tronque_jamais_sur_place(spool_dir, small_ring, monkeypatch):
    """The fallback that must NOT exist is truncate-in-place: it hands a reader
    a file shorter than its own offset with different bytes in it. When the
    swap cannot happen the old file stays WHOLE and the append continues into
    it — the rotation is simply retried later."""
    monkeypatch.setattr(wrap, "_replace_with_retry",
                        lambda src, dst, **kw: False if str(dst).endswith(".raw") else True)
    spool = wrap.Spool(spool_dir, "sid-abandon", "claude", 1, 80, 24, "posix")
    try:
        written = b""
        for i in range(2000):
            chunk = _record(i)
            spool.write(chunk)
            written += chunk
        # Nothing was swapped, so the file is still the FULL stream — bigger
        # than the cap, and byte-identical to what was written.
        assert spool.raw_path.stat().st_size == len(written)
        assert spool.raw_path.read_bytes() == written
        assert not spool.part_path.exists()
    finally:
        spool.close()


def test_rotation_sous_lecteur_concurrent(spool_dir, small_ring):
    """GATE-B shaped: a reader doing open-read-CLOSE every 10 ms while the
    writer forces a dozen rotations.

    THE PROPERTY, and why it is the one that matters: at every instant the file
    is a CONTIGUOUS SLICE of the stream written so far. Never a torn record,
    never two generations spliced. That is exactly what "the tail is written
    whole, then swapped atomically, and nothing is ever truncated in place"
    buys, and it is unfalsifiable without a reader running against a real
    rotation.

    The reader holds NO handle between ticks — the same discipline
    `dashboard.py`'s `/api/term/stream` reader follows, and the reason the
    bounded replace above is enough on Windows."""
    spool = wrap.Spool(spool_dir, "sid-race", "claude", 1, 80, 24, "posix")
    stop = threading.Event()
    samples: list[tuple[int, bytes]] = []
    errors: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                meta = wrap.read_meta(spool.meta_path)
                # open-read-close, never a handle kept across ticks
                with open(spool.raw_path, "rb") as fh:
                    blob = fh.read()
                if meta is not None:
                    samples.append((int(meta.get("gen", -1)), blob))
            except OSError as exc:
                errors.append(f"{type(exc).__name__}")
            time.sleep(0.01)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    written = bytearray()
    # Write UNTIL the reader has actually sampled across >=2 generations, not for
    # a fixed count of records: the old `range(6000)` let a starved reader finish
    # under-sampled, so the non-vacuity preconditions below measured the
    # scheduler rather than the rotation (T-00000176). The generous deadline is
    # the only bound, and the exit condition MIRRORS those preconditions, so on a
    # healthy machine they are met by construction and on a broken reader/rotation
    # the loop runs to the deadline and the unchanged assertions fail honestly.
    deadline = time.monotonic() + 30.0
    i = 0
    try:
        while time.monotonic() < deadline:
            chunk = _record(i)  # ~64 B each over a 64 KiB ring: forces rotations
            spool.write(chunk)
            written += chunk
            i += 1
            if i % 200 == 0:
                time.sleep(0.002)  # let the reader actually interleave
            snapshot = list(samples)  # atomic copy; reader appends concurrently
            if (
                spool.gen >= 2
                and len(snapshot) >= 5
                and len({gen for gen, _ in snapshot}) >= 2
            ):
                break
    finally:
        stop.set()
        thread.join(timeout=5)
        spool.close()

    assert spool.gen >= 2, f"pas assez de rotations pour mesurer ({spool.gen})"
    assert len(samples) >= 5, f"le lecteur n'a pas assez échantillonné ({len(samples)})"
    assert not errors, f"le lecteur a rencontré des erreurs d'ouverture : {errors[:3]}"
    full = bytes(written)
    for gen, blob in samples:
        if not blob:
            continue
        assert blob in full, (
            f"octets déchirés observés à gen={gen} : le fichier n'est pas une "
            f"tranche contiguë du flux écrit ({len(blob)} octets)")
        # A slice, and always the TAIL of what had been written at that instant:
        # the ring keeps the end, never a middle.
        assert full.endswith(blob) or full.index(blob) + len(blob) <= len(full)
    assert len({gen for gen, _ in samples}) >= 2, (
        "le lecteur n'a jamais vu la génération changer — la course n'a pas eu lieu")


def test_le_spool_ne_leve_jamais_meme_quand_le_disque_refuse(spool_dir):
    """A mirror that raised into the output loop would take the TERMINAL down
    with it. The spool is the thing allowed to degrade, never the console."""
    spool = wrap.Spool(spool_dir, "sid-ferme", "claude", 1, 80, 24, "posix")
    spool._fh.close()  # simulate a handle the OS took away
    spool.write(b"des octets")  # must not raise
    spool.close()  # must not raise either


# ---------------------------------------------------------------------------
# Degraded branch — RUNS EVERYWHERE, because it is what this Windows box does
# ---------------------------------------------------------------------------

def test_sans_backend_la_commande_s_execute_quand_meme(spool_dir, monkeypatch, capsys):
    """The property that makes `wrap.py` safe to put in front of ANY command:
    no mirror is a degradation of the DASHBOARD, never a failure of the
    launcher. The CLI runs, its output is the user's, its exit code is ours."""
    monkeypatch.setattr(wrap, "open_session", lambda: None)
    code = wrap.run([sys.executable, "-c", "print('bonjour'); raise SystemExit(3)"],
                    spool_dir=spool_dir)
    assert code == 3, "le code retour de l'enfant doit être propagé"
    err = capsys.readouterr().err
    assert "WRAP DEGRADED" in err
    assert f"pywinpty=={wrap._PYWINPTY_PIN}" in err, "le pin doit être dit, pas sous-entendu"
    assert "miroir désactivé" in err
    assert not spool_dir.exists() or not list(spool_dir.glob("*.raw")), (
        "la branche dégradée ne doit créer aucun spool")


def test_sans_backend_une_commande_absente_rend_127(spool_dir, monkeypatch):
    monkeypatch.setattr(wrap, "open_session", lambda: None)
    assert wrap.run(["commande-qui-nexiste-pas-du-tout"], spool_dir=spool_dir) == 127


def test_argv_vide_est_un_usage_pas_un_crash(spool_dir):
    assert wrap.run([], spool_dir=spool_dir) == 2


def test_main_ne_capture_aucune_option_du_cli_enveloppe(monkeypatch):
    """`wrap.py claude --help` must show CLAUDE's help. A launcher that
    intercepted `--help` would be undebuggable for exactly the flag people
    reach for first."""
    seen = {}

    def spy(argv, **kwargs):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(wrap, "run", spy)
    wrap.main(["claude", "--help", "--verbose"])
    assert seen["argv"] == ["claude", "--help", "--verbose"]
    wrap.main(["--", "codex", "-h"])
    assert seen["argv"] == ["codex", "-h"]


# ---------------------------------------------------------------------------
# POSIX branch — real pty, real child (skipped on Windows, replayed by CI)
# ---------------------------------------------------------------------------

@POSIX_ONLY
def test_posix_la_sortie_est_dupliquee_verbatim(spool_dir, tmp_path):
    """The whole feature in one assertion: the bytes reach the REAL stdout and
    the spool, and they are the same bytes. Run as a SUBPROCESS rather than
    in-process — `pty.fork()` inside pytest would fork the test runner, and the
    launcher's own CLI entry point is what ships."""
    env = dict(os.environ, AGENTS_TERM_DIR=str(spool_dir))
    proc = subprocess.run(
        [sys.executable, str(HERE / "wrap.py"), sys.executable, "-c",
         "print('MIROIR-FIDELE')"],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 0
    assert b"MIROIR-FIDELE" in proc.stdout, "le vrai terminal doit recevoir les octets"
    raws = list(spool_dir.glob("*.raw"))
    assert len(raws) == 1, f"un spool et un seul, vu : {raws}"
    assert b"MIROIR-FIDELE" in raws[0].read_bytes(), "le spool doit recevoir les mêmes"
    meta = wrap.read_meta(spool_dir / f"{raws[0].name[:-4]}.meta.json")
    assert meta["ended"] is not None
    assert meta["resize"] in ("posix", "frozen")
    assert meta["cmd"] == os.path.basename(sys.executable)


@POSIX_ONLY
def test_posix_le_code_retour_de_l_enfant_est_propage(spool_dir):
    env = dict(os.environ, AGENTS_TERM_DIR=str(spool_dir))
    proc = subprocess.run(
        [sys.executable, str(HERE / "wrap.py"), sys.executable, "-c",
         "raise SystemExit(7)"],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 7


@POSIX_ONLY
def test_posix_le_resize_atteint_le_pty(spool_dir):
    """TIOCSWINSZ actually applied, read back through TIOCGWINSZ on the slave.
    No fork: the ioctl is the platform fact under test, not the spawn."""
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    try:
        session = wrap._PosixPty()
        session.master = master
        session.resize(cols=123, rows=45)
        packed = fcntl.ioctl(slave, termios.TIOCGWINSZ, b"\0" * 8)
        rows, cols, _, _ = struct.unpack("HHHH", packed)
        assert (cols, rows) == (123, 45)
    finally:
        os.close(master)
        os.close(slave)


@POSIX_ONLY
def test_posix_une_rotation_survit_a_une_vraie_session(spool_dir, monkeypatch):
    """Cap and generation exercised through the REAL loop rather than through
    `Spool` alone: a child that prints more than the cap must leave a bounded
    spool whose meta names a generation above zero."""
    env = dict(os.environ, AGENTS_TERM_DIR=str(spool_dir),
               WRAP_TEST_CAP="1", PYTHONUNBUFFERED="1")
    proc = subprocess.run(
        [sys.executable, "-c",
         "import importlib.util, pathlib, sys;"
         "s=importlib.util.spec_from_file_location('wrap', r'" + str(HERE / "wrap.py") + "');"
         "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m;"
         " s.loader.exec_module(m);"
         "m._SPOOL_CAP_BYTES=64*1024; m._SPOOL_KEEP_BYTES=16*1024;"
         "sys.exit(m.run([sys.executable,'-c',\"print('A'*80)\\nfor _ in range(3000): print('B'*80)\"]))"],
        capture_output=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    raws = list(spool_dir.glob("*.raw"))
    assert len(raws) == 1
    assert raws[0].stat().st_size <= 64 * 1024
    meta = wrap.read_meta(spool_dir / f"{raws[0].name[:-4]}.meta.json")
    assert meta["gen"] >= 1


# ---------------------------------------------------------------------------
# Windows/ConPTY branch — skipped when pywinpty is absent (this box)
# ---------------------------------------------------------------------------

@WINPTY_ONLY
def test_windows_la_sortie_est_dupliquee_par_conpty(spool_dir):
    env = dict(os.environ, AGENTS_TERM_DIR=str(spool_dir))
    proc = subprocess.run(
        [sys.executable, str(HERE / "wrap.py"), sys.executable, "-c",
         "print('MIROIR-CONPTY')"],
        capture_output=True, env=env, timeout=120,
    )
    assert proc.returncode == 0
    raws = list(spool_dir.glob("*.raw"))
    assert len(raws) == 1
    assert b"MIROIR-CONPTY" in raws[0].read_bytes()
    meta = wrap.read_meta(spool_dir / f"{raws[0].name[:-4]}.meta.json")
    # `poll` or `frozen`, never `posix`: Windows has no SIGWINCH, and a meta
    # claiming otherwise would make the UI promise dimensions that follow.
    assert meta["resize"] in ("poll", "frozen")


@WINPTY_ONLY
def test_windows_le_backend_choisi_est_conpty():
    session = wrap.open_session()
    assert isinstance(session, wrap._WinPty)
    assert session.resize_mode in ("poll", "frozen")


class _RecordingProc:
    """A stand-in for the pywinpty process that records what was WRITTEN.

    `_WinPty.__init__` imports nothing (pywinpty is loaded lazily inside
    `spawn`), so this arm runs on every platform — including the CI ubuntu that
    has no ConPTY at all. That is the point: the defect it measures is a
    DECODING defect, not a platform one, and pinning it behind a `winpty
    importable` guard would have left it unmeasured on the only machine that
    replays the suite.
    """

    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, text: str) -> None:
        self.writes.append(text)


def _byte_by_byte(session, payload: bytes) -> None:
    """Feed the sink exactly the way `pump_stdin` does on Windows: one byte per
    call (`wrap.py` reads 1 byte because there is no `select()` on a Windows
    console)."""
    for i in range(len(payload)):
        session.write_stdin(payload[i:i + 1])


def test_windows_une_frappe_multi_octets_survit_au_decoupage_par_octet():
    """T-00000092 — `é` typed once must reach the child as `é`, not as two
    replacement characters.

    THE DEFECT, MEASURED: `write_stdin` used to call `data.decode("utf-8",
    "replace")` PER CALL, and the pump hands it one byte at a time. `é` is
    0xC3 0xA9, so it arrived as two independent decodes of one byte each and
    each produced U+FFFD. The user pressed a correct key and the child received
    mojibake. An incremental decoder holds 0xC3 until 0xA9 arrives.
    """
    session = wrap._WinPty()
    session.proc = _RecordingProc()
    _byte_by_byte(session, "é".encode("utf-8"))
    assert "".join(session.proc.writes) == "é"
    # THE ASSERTION THAT NAMES THE DEFECT rather than its symptom: not one
    # replacement character anywhere. Without it, a decoder that emitted
    # "\ufffd\ufffd" would still fail the equality above but the failure would
    # not say WHY.
    assert "\ufffd" not in "".join(session.proc.writes)
    # And the partial byte must produce NO write at all — holding it is the
    # mechanism; a write of "" would mean the sequence was decoded too early.
    partial = wrap._WinPty()
    partial.proc = _RecordingProc()
    partial.write_stdin(b"\xc3")
    assert partial.proc.writes == []


def test_windows_un_emoji_de_quatre_octets_ne_produit_quune_ecriture():
    """The 4-byte case, and it is not redundant with the 2-byte one: a decoder
    that buffered only ONE pending byte would pass `é` and still shatter an
    emoji. Four calls in, exactly one character out."""
    session = wrap._WinPty()
    session.proc = _RecordingProc()
    payload = "🙂".encode("utf-8")
    assert len(payload) == 4
    _byte_by_byte(session, payload)
    assert "".join(session.proc.writes) == "🙂"
    assert len([w for w in session.proc.writes if w]) == 1


def test_windows_un_octet_reellement_invalide_reste_un_seul_remplacement():
    """THE CONTROL THAT KEEPS THE FIX HONEST, and without it the arm above could
    be satisfied by a decoder that swallows everything it cannot parse.
    `errors="replace"` is CONSERVED: a byte that is genuinely invalid — 0xFF is
    valid nowhere in UTF-8 — still becomes exactly one U+FFFD, and the character
    that follows it still arrives intact."""
    session = wrap._WinPty()
    session.proc = _RecordingProc()
    _byte_by_byte(session, b"\xff" + "a".encode("utf-8"))
    assert "".join(session.proc.writes) == "\ufffda"


def test_windows_le_decodeur_est_par_session_jamais_partage():
    """Two sessions must not share a pending sequence. A decoder held on the
    CLASS instead of the instance would let one session's half-typed character
    complete itself with another session's byte — a cross-session corruption
    that no single-session arm above would ever catch."""
    a = wrap._WinPty()
    b = wrap._WinPty()
    a.proc = _RecordingProc()
    b.proc = _RecordingProc()
    a.write_stdin(b"\xc3")
    b.write_stdin(b"\xa9")
    # `b` saw a lone continuation byte: one replacement, and `a` still holds its
    # own partial sequence rather than having been completed by `b`'s byte.
    assert "".join(b.proc.writes) == "\ufffd"
    assert a.proc.writes == []
