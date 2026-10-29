"""Tests for dashboard_registry.py — the machine-wide daemon registry
(T-00000083, M1).

EVERY test redirects the registry through `AGENTKIT_REGISTRY` onto a tmp file.
That redirect is not hygiene, it is a hard requirement: without it this suite
would read and REWRITE the developer's real `~/.agentkit/registry.json` and
garbage-collect their own running daemons.

The centre of gravity here is the TRI-STATE GC. `dead` and `indeterminate`
must not be conflated, because conflating them means a healthy peer on a busy
machine is deleted from the registry and never comes back.
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


registry = _load("_test_dashboard_registry", "dashboard_registry.py")

_DEAD_PID = 2 ** 22 + 54321  # the same "certainly not running" pid the daemon tests use


def _free_port() -> int:
    """A port nothing listens on: bind it, read it, close it. What a caller
    gets is a port that REFUSES connections — the `dead` half of the tri-state."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors: Windows can hold a handle past the test
        # (L-00000035); never let an assertion depend on cleanup succeeding.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self._prev = os.environ.get("AGENTKIT_REGISTRY")
        os.environ["AGENTKIT_REGISTRY"] = str(self.tmp / "registry.json")
        self._servers: list[http.server.HTTPServer] = []

    def tearDown(self):
        for srv in self._servers:
            srv.shutdown()
            srv.server_close()
        if self._prev is None:
            os.environ.pop("AGENTKIT_REGISTRY", None)
        else:
            os.environ["AGENTKIT_REGISTRY"] = self._prev
        self._tmp.cleanup()

    def entry(self, project_id="p-1", **over):
        base = {
            "project_id": project_id,
            "project_root": str(self.tmp / project_id),
            "name": "Projet " + project_id,
            "pid": os.getpid(),
            "port": _free_port(),
            "started": "2026-08-01T10:00:00",
        }
        base.update(over)
        return base

    def _serve(self, handler_cls) -> int:
        """A stub peer, THREADED and with a deep accept queue on purpose.

        A single-threaded stub under concurrent probing eventually REFUSES a
        connection (backlog full) — and a refusal is, by the approved design, a
        definitive `dead` verdict. That would make the concurrency test below
        fail for a reason that has nothing to do with the write race it is
        actually about. Real peers are `ThreadingMixIn` servers, so this stub
        matches them rather than inventing a failure mode."""
        class _Server(http.server.ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 64

        httpd = _Server(("127.0.0.1", 0), handler_cls)
        self._servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd.server_address[1]

    def _summary_server(self, body: bytes, status: int = 200) -> int:
        """A server that answers `/api/peer/summary` with exactly `body`."""
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's contract
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        return self._serve(_Handler)


# ---------------------------------------------------------------------------
# The file: roundtrip, tolerance, the pid guard.
# ---------------------------------------------------------------------------

class RoundtripTests(RegistryTestCase):
    def test_register_then_read_roundtrip(self):
        entry = self.entry()
        self.assertTrue(registry.register(entry, timeout=0.05))
        data = registry.read_registry()
        self.assertEqual(data["version"], registry.REGISTRY_VERSION)
        self.assertEqual(data["projects"]["p-1"], entry)

    def test_an_entry_carries_a_closed_key_set_and_no_token(self):
        """A machine-wide file readable by every project on the box: a caller
        must not be able to smuggle a token (or anything else) into it."""
        registry.register(self.entry(token="s3cret", extra="nope"), timeout=0.05)
        stored = registry.read_registry()["projects"]["p-1"]
        self.assertEqual(set(stored), {"project_id", "project_root", "name",
                                       "pid", "port", "started"})

    def test_absent_registry_reads_empty_never_raises(self):
        data, state = registry.read_registry_state()
        self.assertEqual(data, {"version": registry.REGISTRY_VERSION, "projects": {}})
        self.assertEqual(state, "empty")

    def test_corrupt_registry_reads_empty_and_says_unreadable(self):
        registry.registry_path().parent.mkdir(parents=True, exist_ok=True)
        registry.registry_path().write_text("{not json at all", encoding="utf-8")
        data, state = registry.read_registry_state()
        self.assertEqual(data["projects"], {})
        self.assertEqual(state, "unreadable")
        # …and a corrupt file is not a dead end: the next register rebuilds it.
        self.assertTrue(registry.register(self.entry(), timeout=0.05))
        self.assertIn("p-1", registry.read_registry()["projects"])

    def test_a_valid_json_of_the_wrong_shape_is_unreadable_not_empty(self):
        registry.registry_path().parent.mkdir(parents=True, exist_ok=True)
        registry.registry_path().write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        self.assertEqual(registry.read_registry_state()[1], "unreadable")

    def test_register_refuses_an_entry_without_a_project_id(self):
        with self.assertRaises(ValueError):
            registry.register({"pid": os.getpid(), "port": 1}, timeout=0.05)


class UnregisterTests(RegistryTestCase):
    def test_unregister_removes_our_own_entry(self):
        registry.register(self.entry(), timeout=0.05)
        self.assertTrue(registry.unregister("p-1", os.getpid()))
        self.assertEqual(registry.read_registry()["projects"], {})

    def test_unregister_with_a_different_pid_is_a_no_op(self):
        """A successor daemon for the SAME project may have registered while we
        were shutting down; clobbering its entry would make a LIVE daemon
        invisible to every other project."""
        successor = self.entry(pid=os.getpid())
        registry.register(successor, timeout=0.05)
        self.assertFalse(registry.unregister("p-1", os.getpid() + 1))
        self.assertEqual(registry.read_registry()["projects"]["p-1"], successor)

    def test_unregister_of_an_absent_project_is_a_no_op(self):
        self.assertFalse(registry.unregister("nobody", os.getpid()))


# ---------------------------------------------------------------------------
# THE TRI-STATE. `indeterminate` survives; only `dead` is collected.
# ---------------------------------------------------------------------------

class TriStateTests(RegistryTestCase):
    def test_a_live_pid_and_a_matching_summary_is_alive(self):
        port = self._summary_server(json.dumps({
            "kind": registry.PEER_SUMMARY_KIND, "project_id": "p-1"}).encode("utf-8"))
        entry = self.entry(port=port)
        verdict, summary = registry.inspect_entry(entry, timeout=2.0)
        self.assertEqual(verdict, registry.ALIVE)
        self.assertEqual(summary["project_id"], "p-1")

    def test_registry_gc_keeps_entry_on_probe_timeout(self):
        """THE amendment this task turns on. A socket that accepts and then
        says nothing is a BUSY peer, not a dead one — the entry survives the
        GC and is merely reported `alive: false`.

        The stall is a listening socket NOBODY EVER ACCEPTS FROM: the kernel
        completes the handshake into the backlog, the request goes out, and the
        response never comes. That is precisely the transient failure a loaded
        machine produces — and the one a two-state GC would read as death.
        The backlog is deliberately generous, because a FULL backlog is a
        different (and definitive) failure on Windows: a RST, i.e. `refused`."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(50)
        port = listener.getsockname()[1]
        try:
            entry = self.entry(port=port)
            self.assertEqual(registry.is_entry_alive(entry, timeout=0.3),
                             registry.INDETERMINATE)
            # The GC must KEEP it: a neighbour registers (which GCs) and the
            # busy entry is still there afterwards.
            registry.register(entry, timeout=0.3)
            registry.register(self.entry("p-2"), timeout=0.3)
            self.assertIn("p-1", registry.read_registry()["projects"],
                          "an indeterminate entry must SURVIVE the GC")
        finally:
            listener.close()

    def test_a_refused_connection_is_dead_and_is_collected(self):
        """Connection refused = nothing listens there any more. urllib wraps it
        in URLError, so this also pins the UNWRAP of `.reason` — without it,
        every timeout would classify as death too.

        THE TIMEOUT HERE IS GENEROUS ON PURPOSE, and it is a measured platform
        fact rather than slack: on Windows a connect to a closed loopback port
        takes ~2 s to come back as WinError 10061 (it is retried before it is
        refused), while Linux refuses at once. The property under test is the
        CLASSIFICATION, not the latency; the production default (0.5 s) reads
        the same port as `indeterminate` on Windows, which is the safe
        direction and is documented in the module."""
        entry = self.entry(port=_free_port())
        self.assertEqual(registry.is_entry_alive(entry, timeout=5.0), registry.DEAD)
        registry.register(entry, timeout=5.0)
        registry.register(self.entry("p-2"), timeout=5.0)
        self.assertNotIn("p-1", registry.read_registry()["projects"])

    def test_a_dead_pid_is_dead_without_probing(self):
        entry = self.entry(pid=_DEAD_PID)
        self.assertEqual(registry.is_entry_alive(entry, timeout=1.0), registry.DEAD)
        registry.register(entry, timeout=0.5)
        registry.register(self.entry("p-2"), timeout=0.5)
        self.assertNotIn("p-1", registry.read_registry()["projects"])

    def test_a_mismatched_project_id_is_dead(self):
        """The recycled-port case: something answers our contract, but it is
        somebody else's project."""
        port = self._summary_server(json.dumps({
            "kind": registry.PEER_SUMMARY_KIND, "project_id": "somebody-else"}).encode("utf-8"))
        self.assertEqual(registry.is_entry_alive(self.entry(port=port), timeout=2.0),
                         registry.DEAD)

    def test_a_non_json_answer_is_dead(self):
        port = self._summary_server(b"<html>not us</html>")
        self.assertEqual(registry.is_entry_alive(self.entry(port=port), timeout=2.0),
                         registry.DEAD)

    def test_a_wrong_kind_is_dead(self):
        port = self._summary_server(json.dumps({
            "kind": "something.else", "project_id": "p-1"}).encode("utf-8"))
        self.assertEqual(registry.is_entry_alive(self.entry(port=port), timeout=2.0),
                         registry.DEAD)

    def test_a_redirect_is_dead_and_is_never_followed(self):
        """SSRF, closed (security review, T-00000083). `urlopen` follows 3xx by
        default, so a process squatting a peer's port could point this daemon at
        a URL of its choosing. Two assertions, because "verdict is dead" alone
        would also hold if the redirect HAD been followed to a non-peer: the
        decoy counts its hits, and that count must stay at zero."""
        hits: list[str] = []

        class _Decoy(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's contract
                hits.append(self.path)
                body = json.dumps({"kind": registry.PEER_SUMMARY_KIND,
                                   "project_id": "p-1"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        decoy_port = self._serve(_Decoy)

        class _Redirector(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{decoy_port}/anything")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        port = self._serve(_Redirector)
        self.assertEqual(registry.is_entry_alive(self.entry(port=port), timeout=2.0),
                         registry.DEAD)
        self.assertEqual(hits, [], "a redirect must NEVER be followed")

    def test_a_404_is_dead(self):
        """An older daemon that predates `/api/peer/summary` answers 404. That
        is a definitive "not a peer", not a transport hiccup."""
        port = self._summary_server(b'{"error":"not_found"}', status=404)
        self.assertEqual(registry.is_entry_alive(self.entry(port=port), timeout=2.0),
                         registry.DEAD)


# ---------------------------------------------------------------------------
# Concurrency — the whole reason `register()` verifies.
# ---------------------------------------------------------------------------

class LockPoisonTests(RegistryTestCase):
    """T-00000089 — the two ways the lock became unavailable in practice, each
    of which turned every later writer into an unlocked stampede that lost
    entries (measured: 6 writers -> 2 surviving entries, all returning True)."""

    def _lock_path(self) -> Path:
        return Path(str(registry.registry_path()) + ".lock")

    def test_a_dead_owners_lock_is_broken_immediately_not_after_30s(self):
        """A lock file whose recorded pid is provably dead is a corpse: it must
        be broken on sight, not waited out for `_LOCK_STALE_SECONDS` while the
        whole machine writes unlocked."""
        lock = self._lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(_DEAD_PID), encoding="ascii")  # fresh mtime, dead pid
        import time as _time
        t0 = _time.monotonic()
        landed = registry.register(self.entry(port=_free_port()), timeout=0.05)
        elapsed = _time.monotonic() - t0
        self.assertTrue(landed, "register must land after breaking a corpse lock")
        self.assertLess(elapsed, registry._LOCK_WAIT_SECONDS,
                        "a corpse lock must be broken before patience runs out, "
                        f"took {elapsed:.2f}s")
        self.assertIn("p-1", registry.read_registry()["projects"])

    def test_a_live_owners_fresh_lock_is_respected(self):
        """The corpse rule must not break a LIVE owner's lock: with our own
        (live) pid inside, the waiter waits, then proceeds degraded — the file
        is never deleted under its owner."""
        lock = self._lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()), encoding="ascii")
        old_wait = registry._LOCK_WAIT_SECONDS
        registry._LOCK_WAIT_SECONDS = 0.2
        try:
            landed = registry.register(self.entry(port=_free_port()), timeout=0.05)
        finally:
            registry._LOCK_WAIT_SECONDS = old_wait
        self.assertTrue(landed)
        self.assertTrue(lock.exists(),
                        "a live owner's lock must never be deleted by a waiter")

    def test_the_lock_release_retries_a_transient_unlink_failure(self):
        """A swallowed PermissionError on release leaks the lock and poisons
        every writer for 30 s (the AV/indexer case, family L-00000035). The
        release must retry with the same bounded recipe as replace_with_retry."""
        import unittest.mock as mock
        real_unlink = os.unlink
        lock_name = self._lock_path().name
        fails = {"left": 3}

        def flaky_unlink(path, *a, **kw):
            if Path(path).name == lock_name and fails["left"] > 0:
                fails["left"] -= 1
                raise PermissionError(13, "held by a scanner", str(path))
            return real_unlink(path, *a, **kw)

        with mock.patch.object(registry.os, "unlink", side_effect=flaky_unlink):
            landed = registry.register(self.entry(port=_free_port()), timeout=0.05)
        self.assertTrue(landed)
        self.assertFalse(self._lock_path().exists(),
                         "the lock must not leak past a transient unlink failure")
        self.assertEqual(fails["left"], 0, "the retry path was never exercised")

    def test_the_lock_retries_a_non_fileexists_oserror_until_acquired(self):
        """On Windows a lock file in the delete-pending state (the releaser
        unlinked it while a waiter still holds a handle via `_lock_is_stale`)
        makes O_CREAT|O_EXCL fail with PermissionError, NOT FileExistsError
        (T-00000204). Breaking out of the acquire loop on that error proceeds
        UNLOCKED at once, and two such writers lose an entry — the very
        stampede this lock exists to prevent. A non-FileExistsError must be
        retried until the deadline, so a transient one ends with the lock
        ACQUIRED rather than skipped.

        The proof that the lock was ACQUIRED and not skipped unlocked is the
        os.open call count: the buggy code calls os.open exactly once on the
        lock (raise -> break -> proceed unlocked), while the fix retries past
        each transient failure and the last call is the one that succeeds. This
        is deterministic and load-free: os.open is mocked to raise N times then
        delegate, so no scheduling variance can make it pass or fail."""
        import unittest.mock as mock
        real_open = os.open
        fails = {"left": 3}
        opened = {"count": 0}

        def flaky_open(path, *a, **kw):
            if str(path).endswith(".lock"):
                opened["count"] += 1
                if fails["left"] > 0:
                    fails["left"] -= 1
                    raise PermissionError(5, "delete-pending", str(path))
            return real_open(path, *a, **kw)

        with mock.patch.object(registry.os, "open", side_effect=flaky_open):
            landed = registry.register(self.entry(port=_free_port()), timeout=0.05)
        self.assertTrue(landed)
        self.assertEqual(fails["left"], 0, "the retry path was never exercised")
        self.assertEqual(opened["count"], 4,
                         "the lock must be ACQUIRED after the transient errors, "
                         "not skipped unlocked (os.open called once then broken)")
        self.assertIn("p-1", registry.read_registry()["projects"])

    def test_a_dead_owners_lock_raising_permissionerror_is_reclaimed(self):
        """A dead owner's lock that surfaces as PermissionError instead of
        FileExistsError — the Windows delete-pending sibling of the corpse
        case (T-00000204/T-00000260) — must be reclaimed ON SIGHT by the
        OSError branch, exactly as the FileExistsError branch already does for
        `test_a_dead_owners_lock_is_broken_immediately_not_after_30s`. Before
        this fix the OSError branch had no reclaim: it merely retried to the
        deadline, so a corpse lock raising PermissionError made the waiter sleep
        out `_LOCK_WAIT_SECONDS` before proceeding degraded.

        Deterministic and load-free — no scheduling counter: os.open raises for
        the lock ONLY while the lock file still EXISTS on disk, so the very
        reclaim under test (its os.unlink) is what ends the mock. First open
        sees the corpse file and raises PermissionError; `_lock_is_stale` reads
        the dead pid and unlinks it; the next open finds no file and creates
        ours for real."""
        import unittest.mock as mock
        import time as _time
        real_open = os.open
        lock = self._lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(_DEAD_PID), encoding="ascii")  # fresh mtime, dead pid

        def flaky_open(path, *a, **kw):
            # Raise while the corpse lock is still on disk; delegate (so the
            # acquire succeeds) once the reclaim's unlink has removed it.
            if str(path).endswith(".lock") and Path(path).exists():
                raise PermissionError(13, "delete-pending corpse", str(path))
            return real_open(path, *a, **kw)

        t0 = _time.monotonic()
        with mock.patch.object(registry.os, "open", side_effect=flaky_open):
            landed = registry.register(self.entry(port=_free_port()), timeout=0.05)
        elapsed = _time.monotonic() - t0
        self.assertTrue(landed, "register must land after reclaiming a corpse lock")
        self.assertLess(elapsed, registry._LOCK_WAIT_SECONDS,
                        "a PermissionError corpse lock must be reclaimed before "
                        f"patience runs out, took {elapsed:.2f}s")
        self.assertIn("p-1", registry.read_registry()["projects"])


class ConcurrentWriterTests(RegistryTestCase):
    def test_concurrent_registers_lose_no_entry(self):
        """Read-modify-write from N writers with no shared lock: `os.replace`
        keeps each write atomic, but a naive implementation silently drops
        entries to last-writer-wins. The bounded verify-and-retry is what makes
        this pass — and the assertion is on the FILE at the end, not merely on
        each writer's return value.

        Every writer gets a REAL summary server answering its own project_id,
        so each entry reads `alive` and the GC has nothing to collect: what is
        under test is the write race, not the liveness rules."""
        ports = {
            f"p-{n}": self._summary_server(json.dumps({
                "kind": registry.PEER_SUMMARY_KIND, "project_id": f"p-{n}"}).encode("utf-8"))
            for n in range(6)
        }
        results: dict[str, bool] = {}
        errors: list[BaseException] = []
        lock = threading.Lock()

        def writer(project_id: str) -> None:
            try:
                landed = registry.register(
                    self.entry(project_id, port=ports[project_id]), timeout=2.0)
            except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
                with lock:
                    errors.append(exc)
                return
            with lock:
                results[project_id] = landed

        threads = [threading.Thread(target=writer, args=(pid,)) for pid in ports]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertEqual(errors, [], f"a concurrent writer raised: {errors}")
        self.assertTrue(all(results.values()),
                        f"a writer never saw its own entry land: {results}")
        self.assertEqual(set(registry.read_registry()["projects"]), set(ports),
                         "a concurrent register lost an entry")

    def test_a_second_register_of_the_same_project_replaces_its_entry(self):
        registry.register(self.entry(port=1234), timeout=0.05)
        registry.register(self.entry(port=5678), timeout=0.05)
        projects = registry.read_registry()["projects"]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects["p-1"]["port"], 5678)


class RegistryPathTests(RegistryTestCase):
    def test_env_override_wins_and_the_default_is_under_home(self):
        self.assertEqual(registry.registry_path(), self.tmp / "registry.json")
        os.environ.pop("AGENTKIT_REGISTRY")
        try:
            self.assertEqual(registry.registry_path(),
                             Path.home() / ".agentkit" / "registry.json")
        finally:
            os.environ["AGENTKIT_REGISTRY"] = str(self.tmp / "registry.json")


class SchemaAheadTests(RegistryTestCase):
    """LE REGISTRE EST PARTAGÉ PAR TOUS LES PROJETS DU POSTE, et il rétrogradait
    en silence. `REGISTRY_VERSION` était ÉCRIT quatre fois et comparé zéro fois :
    un projet sur un kit plus récent écrivait `version: 2` plus ses champs ; un
    projet sur un kit plus ancien relisait, filtrait ce qu'il ne connaissait pas,
    et réécrivait `version: 1`. Perte silencieuse, aucun message, sur le fichier
    que deux projets partagent. Trouvé par le binôme de clôture le 2026-09-12,
    séparément par les deux critiques.

    LE TÉMOIN DÉCISIF est `test_un_kit_plus_ancien_n_ECRIT_PAS` : il compare les
    OCTETS du fichier avant et après. Sur le code d'avant le correctif il ROUGIT,
    puisque c'est exactement la réécriture qu'il constate."""

    def _ecrire_registre(self, version, extra=None):
        """Pose un registre écrit par un kit FICTIF plus récent."""
        contenu = {
            "version": version,
            "projects": {
                "p-futur": {
                    "project_id": "p-futur", "pid": _DEAD_PID, "port": 4242,
                    "name": "Projet du futur",
                    # Le champ que `_ENTRY_FIELDS` ne connaît pas : c'est LUI que
                    # la réécriture perdait.
                    "champ_inconnu_du_kit_ancien": "a preserver",
                },
            },
        }
        if extra:
            contenu.update(extra)
        chemin = registry.registry_path()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin

    def test_une_version_superieure_se_dit_schema_ahead_et_jamais_ok(self):
        self._ecrire_registre(registry.REGISTRY_VERSION + 1)
        _registre, etat = registry.read_registry_state()
        self.assertEqual(etat, "schema_ahead")

    def test_un_kit_plus_ancien_n_ECRIT_PAS(self):
        """LE TÉMOIN. Les octets du fichier doivent être INCHANGÉS."""
        chemin = self._ecrire_registre(registry.REGISTRY_VERSION + 1)
        avant = chemin.read_bytes()
        self.assertFalse(registry.register(self.entry(project_id="p-ancien"),
                                           timeout=0.3),
                         "register() doit REFUSER, pas publier")
        self.assertEqual(chemin.read_bytes(), avant,
                         "le registre d'un kit plus recent a ete reecrit : "
                         "version retrogradee et champs inconnus perdus")

    def test_unregister_refuse_aussi(self):
        chemin = self._ecrire_registre(registry.REGISTRY_VERSION + 1)
        avant = chemin.read_bytes()
        self.assertFalse(registry.unregister("p-futur", _DEAD_PID))
        self.assertEqual(chemin.read_bytes(), avant)

    def test_une_v2_DONT_LA_FORME_A_CHANGE_n_est_pas_ecrasee(self):
        """LE CAS QUE LA VERSION DÉSIGNE, et que la première rédaction du garde
        RATAIT. `REGISTRY_VERSION` se bumpe quand un lecteur de la génération
        précédente lirait faux — une vraie v2 n'a donc PAS forcément `projects`.
        Tant que la FORME était testée avant la VERSION, ce fichier lisait
        `unreadable`, et `unreadable` est contractuellement réécrit par le
        prochain `register()`. Mesuré sur la première rédaction : `register()`
        rendait True et la v2 était écrasée en entier."""
        chemin = registry.registry_path()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps({
            "version": registry.REGISTRY_VERSION + 1,
            "daemons": {"p-futur": {"pid": _DEAD_PID, "port": 4242,
                                    "nouveau": "a preserver"}},
        }), encoding="utf-8")
        avant = chemin.read_bytes()
        self.assertEqual(registry.read_registry_state()[1], "schema_ahead")
        self.assertFalse(registry.register(self.entry(project_id="p-ancien"),
                                           timeout=0.3))
        self.assertEqual(chemin.read_bytes(), avant,
                         "une v2 de forme differente a ete ecrasee en entier")

    def test_le_verrou_est_RELACHE_par_le_refus(self):
        """Le refus sort d'un `with _registry_lock():`. Un verrou laissé derrière
        empoisonnerait TOUS les projets du poste : chaque écrivain suivant
        épuiserait sa patience puis écrirait SANS exclusion, et la bousculade
        perd des entrées (T-00000089)."""
        self._ecrire_registre(registry.REGISTRY_VERSION + 1)
        verrou = Path(str(registry.registry_path()) + ".lock")
        self.assertFalse(registry.register(self.entry(project_id="p-ancien"),
                                           timeout=0.3))
        self.assertFalse(verrou.exists(), "verrou laisse derriere par le refus")
        self.assertFalse(
            list(registry.registry_path().parent.glob("._registry_*")),
            "temporaire laisse derriere par le refus")
        debut = time.monotonic()
        self.assertFalse(registry.unregister("p-futur", _DEAD_PID))
        self.assertLess(time.monotonic() - debut, 1.0,
                        "l appel suivant a attendu la patience du verrou : "
                        "le verrou n avait pas ete relache")

    def test_une_version_ANTERIEURE_n_est_pas_lue_comme_la_notre(self):
        """LE SENS INVERSE, qui rétrogradait aussi. `version: 0` ou négative
        n'est pas notre format ; la lire `ok` puis la restamper à 1 est la même
        perte, dans l'autre sens. Mesuré avant correctif : `ok` pour 0 ET -1."""
        for v in (0, -1):
            with self.subTest(version=v):
                self._ecrire_registre(v)
                self.assertEqual(registry.read_registry_state()[1], "unreadable")

    def test_une_cle_de_PREMIER_NIVEAU_survit_a_version_EGALE(self):
        """LA MOITIÉ COURANTE DU DÉFAUT, que le garde de version ne voit pas par
        construction. Une clé additive ne bumpe PAS (règle écrite en tête du
        module), donc elle traverse un kit d'une autre génération. La
        reconstruction à deux clés la détruisait — mesuré : `hub` ne survivait
        pas à un aller-retour."""
        chemin = registry.registry_path()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps({
            "version": registry.REGISTRY_VERSION,
            "hub": "une cle additive posee par un autre kit",
            "projects": {},
        }), encoding="utf-8")
        self.assertIn("hub", registry.read_registry(),
                      "la cle additive est perdue des la LECTURE")
        self.assertTrue(registry.register(self.entry(project_id="p-ancien"),
                                          timeout=0.3))
        relu = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(relu["hub"], "une cle additive posee par un autre kit",
                         "la cle additive est perdue a l ECRITURE")

    def test_NON_VACUITE_une_version_courante_s_ecrit_TOUJOURS(self):
        """LE CONTRÔLE NÉGATIF, sans quoi les tests ci-dessus passeraient même
        si `register()` avait cessé d'écrire tout court. Il vérifie aussi la
        VERSION écrite et la survie d'un pair tiers — sans quoi il passerait
        avec un écrivain qui publie en jetant les autres."""
        self._ecrire_registre(registry.REGISTRY_VERSION)
        chemin = registry.registry_path()
        avant = chemin.read_bytes()
        self.assertTrue(registry.register(self.entry(project_id="p-ancien"),
                                          timeout=0.3),
                        "a version EGALE, register() doit publier normalement")
        self.assertNotEqual(chemin.read_bytes(), avant)
        relu = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(relu["version"], registry.REGISTRY_VERSION)
        self.assertIn("p-ancien", relu["projects"])

    def test_une_version_non_entiere_est_unreadable(self):
        """La forme n'est pas la nôtre : on ne l'interprète pas."""
        self._ecrire_registre("2")
        self.assertEqual(registry.read_registry_state()[1], "unreadable")
        self._ecrire_registre(True)
        self.assertEqual(registry.read_registry_state()[1], "unreadable")


if __name__ == "__main__":
    unittest.main()
