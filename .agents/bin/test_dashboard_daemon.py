"""Tests for dashboard_daemon.py (T-00000025 shard 2).

Covers the four GATE B mechanisms at PRODUCT level (the probe
`.agents/evals/test_gate_b_launch_probe.py` proved the primitives; these
tests prove OUR code uses them correctly): lock roundtrip and malformed
tolerance, bounded-retry atomic rewrite, singleton acquisition against a
live daemon, stale-lock reclaim, liveness = pid AND tokenised ping, idle
auto-stop, and the post-bind ownership re-check.
"""
import importlib.util
import json
import os
import re
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


daemon = _load("_test_dashboard_daemon", "dashboard_daemon.py")
dashboard = daemon._dashboard


registry = daemon._registry


class DaemonTestCase(unittest.TestCase):
    def setUp(self):
        # Windows flake: git/AV handles can outlive the test and make cleanup
        # raise PermissionError (ledger L-00000035) — never a regression here.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self._servers = []
        # T-00000083. `run_daemon` now WRITES the machine-wide registry, and it
        # resolves its identity from `AGENTS_PROJECT_JSON` — both are redirected
        # here for the same reason `with_ingest=False` exists below: without it
        # these tests would register a test port under this DEVELOPER's real
        # project id, in their real `~/.agentkit/registry.json`, and every other
        # project on the machine would then probe a daemon that stopped when the
        # test ended.
        self._env_backup = {k: os.environ.get(k)
                            for k in ("AGENTKIT_REGISTRY", "AGENTS_PROJECT_JSON")}
        os.environ["AGENTKIT_REGISTRY"] = str(self.root / "registry.json")
        self.project_id = "test-project-" + str(os.getpid())
        identity = self.root / "project.json"
        identity.write_text(json.dumps({"project_id": self.project_id, "name": "Sous test"}),
                            encoding="utf-8", newline="\n")
        os.environ["AGENTS_PROJECT_JSON"] = str(identity)

    def tearDown(self):
        for srv in self._servers:
            srv.shutdown()
            srv.server_close()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _live_ui_server(self):
        """A REAL UI server on an ephemeral port, served from a thread —
        what a live daemon looks like from the outside."""
        created = dashboard.create_ui_server(project_root=self.root)
        self.assertIsNotNone(created)
        httpd, token = created
        self._servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, token


class LockRoundtripTests(DaemonTestCase):
    def test_write_then_read_roundtrip(self):
        payload = {"pid": 123, "port": 456, "token": "tok"}
        daemon.write_lock(self.root, payload)
        self.assertEqual(daemon.read_lock(self.root), payload)

    def test_absent_lock_reads_none_and_status_absent(self):
        self.assertIsNone(daemon.read_lock(self.root))
        self.assertEqual(daemon.daemon_status(self.root), ("absent", None))

    def test_malformed_lock_reads_none_but_status_stale(self):
        for bad in ("not json", "[]", json.dumps({"pid": "x", "port": 1, "token": "t"}),
                    json.dumps({"pid": 1}), json.dumps({"pid": 1, "port": 1, "token": ""})):
            daemon.lock_path(self.root).parent.mkdir(parents=True, exist_ok=True)
            daemon.lock_path(self.root).write_text(bad, encoding="utf-8")
            self.assertIsNone(daemon.read_lock(self.root), f"accepted malformed lock: {bad!r}")
            # A malformed FILE must be reclaimable, not a permanent wedge.
            self.assertEqual(daemon.daemon_status(self.root)[0], "stale")

    def test_remove_lock_only_when_token_matches(self):
        daemon.write_lock(self.root, {"pid": 1, "port": 2, "token": "ours"})
        self.assertFalse(daemon.remove_lock_if_ours(self.root, "theirs"))
        self.assertTrue(daemon.lock_path(self.root).exists())
        self.assertTrue(daemon.remove_lock_if_ours(self.root, "ours"))
        self.assertFalse(daemon.lock_path(self.root).exists())


class ReplaceRetryTests(DaemonTestCase):
    def test_bounded_retry_converges_after_transient_permission_errors(self):
        target = self.root / "dashboard.lock"
        target.write_text("old", encoding="utf-8")
        src = self.root / "new.part"
        src.write_text("new", encoding="utf-8")
        real_replace = os.replace
        failures = [0]

        def flaky(a, b):
            if failures[0] < 3:
                failures[0] += 1
                raise PermissionError("simulated sharing violation (L-00000054)")
            real_replace(a, b)

        daemon.os.replace = flaky
        try:
            daemon.replace_with_retry(src, target, attempts=10, delay=0.001)
        finally:
            daemon.os.replace = real_replace
        self.assertEqual(failures[0], 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_retry_bound_exhausted_reraises_loudly(self):
        real_replace = os.replace
        calls = [0]

        def always_fails(a, b):
            calls[0] += 1
            raise PermissionError("permanent")

        daemon.os.replace = always_fails
        try:
            with self.assertRaises(PermissionError):
                daemon.replace_with_retry("a", "b", attempts=5, delay=0.001)
        finally:
            daemon.os.replace = real_replace
        self.assertEqual(calls[0], 5, "retry must be BOUNDED, not infinite")


class LivenessTests(DaemonTestCase):
    def test_ping_accepts_only_our_token(self):
        httpd, token = self._live_ui_server()
        port = httpd.server_address[1]
        self.assertTrue(daemon.ping(port, token))
        self.assertFalse(daemon.ping(port, "wrong-token"), "an imposter token must not read as ours")

    def test_ping_false_when_nothing_listens(self):
        # Grab a genuinely free port, then close it before pinging.
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertFalse(daemon.ping(port, "any"))

    def test_status_alive_requires_pid_AND_ping(self):
        httpd, token = self._live_ui_server()
        port = httpd.server_address[1]
        # Live pid + answering ping -> alive.
        daemon.write_lock(self.root, {"pid": os.getpid(), "port": port, "token": token})
        self.assertEqual(daemon.daemon_status(self.root)[0], "alive")
        # Live pid but WRONG token (recycled pid / imposter port): stale.
        daemon.write_lock(self.root, {"pid": os.getpid(), "port": port, "token": "not-it"})
        self.assertEqual(daemon.daemon_status(self.root)[0], "stale")
        # Dead pid, even with a correct-token listener: stale.
        daemon.write_lock(self.root, {"pid": 2 ** 22 + 12345, "port": port, "token": token})
        self.assertEqual(daemon.daemon_status(self.root)[0], "stale")

    def test_pid_alive_on_self_and_dead_pid(self):
        self.assertTrue(daemon.pid_alive(os.getpid()))
        self.assertFalse(daemon.pid_alive(-1))


class AcquisitionTests(DaemonTestCase):
    def test_fresh_acquire_wins_and_writes_provisional(self):
        prov = {"pid": os.getpid(), "port": 0, "token": "prov"}
        self.assertTrue(daemon.acquire_lock(self.root, prov))
        self.assertEqual(daemon.read_lock(self.root), prov)

    def test_acquire_refused_while_a_daemon_is_alive(self):
        httpd, token = self._live_ui_server()
        daemon.write_lock(self.root, {"pid": os.getpid(), "port": httpd.server_address[1], "token": token})
        self.assertFalse(daemon.acquire_lock(self.root, {"pid": 1, "port": 0, "token": "rival"}))
        # The live holder's lock is untouched.
        self.assertEqual(daemon.read_lock(self.root)["token"], token)

    def test_stale_lock_is_reclaimed(self):
        daemon.write_lock(self.root, {"pid": 2 ** 22 + 54321, "port": 1, "token": "dead"})
        prov = {"pid": os.getpid(), "port": 0, "token": "reclaimer"}
        self.assertTrue(daemon.acquire_lock(self.root, prov))
        self.assertEqual(daemon.read_lock(self.root), prov)


class RunDaemonTests(DaemonTestCase):
    def _run_in_thread(self, **kwargs):
        result = {}

        def target():
            # `with_ingest=False` IS LOAD-BEARING (found in flight while landing
            # V1-c, and it had been quietly true since V1-b). These tests are
            # about the LOCK and the watchdog, and they do NOT redirect
            # `AGENTS_EVENTS_DIR` / `AGENTS_OTEL_DIR`. With an ingest loop, each
            # of them opened the developer's REAL events.db as a SECOND WRITER —
            # racing their live daemon, consuming real spool files, and (from
            # V1-c on) running a data migration on real data from inside a unit
            # test. Worse, the loop outlives the test: it re-reads
            # `AGENTS_OTEL_DIR` on every tick, so once a LATER test monkeypatched
            # that variable to its own tmp dir, this thread ingested that test's
            # fixtures INTO THE REAL DATABASE. Two such rows were found in this
            # repo's own store, correctly quarantined as foreign — the mechanism
            # worked, but the leak was real.
            kwargs.setdefault("with_ingest", False)
            result["code"] = daemon.run_daemon(self.root, with_otel=False, **kwargs)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        return t, result

    def _wait_alive(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, lock = daemon.daemon_status(self.root)
            if status == "alive":
                return lock
            time.sleep(0.05)
        self.fail("daemon never became alive")

    def test_daemon_publishes_lock_then_idle_auto_stop_removes_it(self):
        t, result = self._run_in_thread(idle_seconds=1.0, poll_seconds=0.1)
        lock = self._wait_alive()
        self.assertEqual(lock["pid"], os.getpid())
        self.assertTrue(daemon.ping(lock["port"], lock["token"]))
        # No activity for idle_seconds -> auto-stop, lock removed, exit 0.
        # A generous join: the assertion is "it eventually stops on its own",
        # never "it stops within a tight budget" (that would be a load test).
        t.join(timeout=30.0)
        self.assertFalse(t.is_alive(), "daemon did not auto-stop on idle")
        self.assertEqual(result["code"], 0)
        self.assertFalse(daemon.lock_path(self.root).exists(), "auto-stop must remove its own lock")

    def test_authorised_activity_defers_auto_stop(self):
        # Timing margins, learned the hard way: an earlier version used a 1.2s
        # idle window and 8 real pings spaced 0.25s apart, and flaked under
        # full-suite load — a ping that takes longer than the gap makes the
        # loop itself outlast the window it is supposed to keep deferring.
        # The property under test is "activity defers the stop", not "a ping
        # completes in under 250ms", so the window is now wide enough that
        # only a genuinely broken watchdog fails it: keep pinging for ~2.5s
        # against a 3s window, then assert still alive.
        t, result = self._run_in_thread(idle_seconds=3.0, poll_seconds=0.1)
        lock = self._wait_alive()
        deadline = time.monotonic() + 2.5
        pings = 0
        while time.monotonic() < deadline:
            self.assertTrue(daemon.ping(lock["port"], lock["token"]))
            pings += 1
            time.sleep(0.2)
        self.assertGreater(pings, 3, "sanity: the deferring loop must actually have run")
        self.assertTrue(t.is_alive(), "authorised activity must defer the auto-stop")
        # … then go quiet and it stops.
        t.join(timeout=20.0)
        self.assertFalse(t.is_alive())
        self.assertEqual(result["code"], 0)

    def test_second_daemon_exits_zero_without_touching_the_lock(self):
        t, _result = self._run_in_thread(idle_seconds=30.0, poll_seconds=0.5)
        lock = self._wait_alive()
        code = daemon.run_daemon(self.root, with_otel=False, with_ingest=False,
                                 idle_seconds=30.0)
        self.assertEqual(code, 0)
        self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"], "rival must not clobber a live lock")
        # The first daemon's thread is daemon=True and dies with the test
        # process; its clean shutdown/lock removal is covered by the
        # auto-stop test above.

    def test_daemon_registers_at_start_and_withdraws_at_stop(self):
        """T-00000083 M1, at PRODUCT level: the registry entry appears while the
        daemon serves and is gone once it has stopped. Asserted through
        `run_daemon` itself, not by calling `register()` — the property is that
        the LIFECYCLE publishes and withdraws, and a unit test of the store
        cannot see a `finally` that never runs."""
        t, result = self._run_in_thread(idle_seconds=1.0, poll_seconds=0.1)
        lock = self._wait_alive()
        entry = registry.read_registry()["projects"].get(self.project_id)
        self.assertIsNotNone(entry, "a live daemon must publish itself to its peers")
        self.assertEqual(entry["pid"], os.getpid())
        self.assertEqual(entry["port"], lock["port"])
        self.assertEqual(entry["project_root"], str(self.root))
        # T-00000582: the registry name is ROOT-derived now (dashboard_daemon.py
        # publishes `_dashboard._nom_depuis_racine(root)`), so it is the basename
        # of self.root — no longer the JSON's "Sous test". "Sous test" stays
        # WRITTEN in setUp (:60) to prove the JSON content is IGNORED.
        self.assertEqual(entry["name"], self.root.name)
        # No token, ever, in a machine-wide file (L-00000112).
        self.assertNotIn("token", entry)

        t.join(timeout=30.0)
        self.assertFalse(t.is_alive(), "daemon did not auto-stop on idle")
        self.assertEqual(result["code"], 0)
        self.assertNotIn(self.project_id, registry.read_registry()["projects"],
                         "a stopped daemon must not stay advertised to other projects")

    def test_no_identity_means_no_registration_and_no_fatality(self):
        """A repo that never ran `project_init.py` has no id to register under.
        That must cost the daemon NOTHING: it serves, it locks, it auto-stops —
        it is merely invisible to `/api/peers`, and says so on stderr."""
        os.environ["AGENTS_PROJECT_JSON"] = str(self.root / "absent.json")
        t, result = self._run_in_thread(idle_seconds=1.0, poll_seconds=0.1)
        lock = self._wait_alive()
        self.assertTrue(daemon.ping(lock["port"], lock["token"]),
                        "the UI must serve normally without a registry entry")
        self.assertEqual(registry.read_registry()["projects"], {})
        t.join(timeout=30.0)
        self.assertEqual(result["code"], 0)

    def test_a_registry_that_cannot_be_written_is_degraded_not_fatal(self):
        """The registry is a convenience, the daemon is not. A store that raises
        on every write leaves the daemon serving and exiting 0."""
        real_register = registry.register

        def boom(*args, **kwargs):
            raise OSError("simulated registry failure")

        registry.register = boom
        try:
            t, result = self._run_in_thread(idle_seconds=1.0, poll_seconds=0.1)
            lock = self._wait_alive()
            self.assertTrue(daemon.ping(lock["port"], lock["token"]))
            t.join(timeout=30.0)
        finally:
            registry.register = real_register
        self.assertEqual(result["code"], 0)

    def test_ownership_recheck_backs_off_when_lock_is_stolen(self):
        """If, between our lock write and the re-read, a rival's write wins,
        the daemon must shut down and leave the rival's lock alone."""
        real_write = daemon.write_lock
        stolen = {"pid": 1, "port": 1, "token": "rival-took-it"}

        def write_then_steal(root, payload):
            real_write(root, payload)
            if payload.get("port"):  # only on the FINAL publish, not the provisional
                real_write(root, stolen)

        daemon.write_lock = write_then_steal
        try:
            code = daemon.run_daemon(self.root, with_otel=False, with_ingest=False,
                                 idle_seconds=30.0)
        finally:
            daemon.write_lock = real_write
        self.assertEqual(code, 0)
        self.assertEqual(daemon.read_lock(self.root), stolen, "loser must not remove the winner's lock")

    def test_ui_bind_failure_is_degraded_exit_2_and_lock_released(self):
        real_create = dashboard.create_ui_server
        dashboard.create_ui_server = lambda **kw: None
        try:
            code = daemon.run_daemon(self.root, with_otel=False, with_ingest=False,
                                 idle_seconds=30.0)
        finally:
            dashboard.create_ui_server = real_create
        self.assertEqual(code, 2)
        self.assertFalse(daemon.lock_path(self.root).exists(), "degraded exit must not leave our provisional lock")


class EnsureRunningTests(DaemonTestCase):
    def test_ensure_running_returns_existing_live_lock_without_spawning(self):
        httpd, token = self._live_ui_server()
        lock = {"pid": os.getpid(), "port": httpd.server_address[1], "token": token}
        daemon.write_lock(self.root, lock)
        real_spawn = daemon.spawn_detached
        daemon.spawn_detached = lambda root: self.fail("must not spawn when a daemon is alive")
        try:
            self.assertEqual(daemon.ensure_running(self.root), lock)
        finally:
            daemon.spawn_detached = real_spawn

    def test_ensure_running_never_raises_and_bounds_its_wait(self):
        real_spawn = daemon.spawn_detached
        daemon.spawn_detached = lambda root: True  # spawn "succeeds" but no daemon appears
        try:
            t0 = time.monotonic()
            self.assertIsNone(daemon.ensure_running(self.root, wait_seconds=0.5))
            self.assertLess(time.monotonic() - t0, 5.0)
        finally:
            daemon.spawn_detached = real_spawn


if __name__ == "__main__":
    unittest.main()


class StaleCodeDetectionTests(DaemonTestCase):
    """T-00000040: a running daemon holds its route table in memory, so after
    an upgrade it 404s new front-end modules and the page renders blank — while
    pid+ping still say 'alive'. The lock records a fingerprint of the code the
    process would serve so this is detectable instead of silent."""

    def test_fingerprint_changes_when_a_served_file_changes(self):
        first = dashboard.served_code_fingerprint()
        self.assertEqual(first, dashboard.served_code_fingerprint(), "must be stable")
        # The built bundle: `.agents/ui/` is now Vite output, so the file that
        # used to be hand-written `app.js` is `assets/app.js`. Restored byte for
        # byte in the `finally` below — a test that left a marker in the served
        # bundle would poison every later fingerprint comparison.
        target = dashboard._UI_DIR / "assets" / "app.js"
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n// touched by test\n")
            self.assertNotEqual(dashboard.served_code_fingerprint(), first,
                                "a changed served file must change the fingerprint")
        finally:
            target.write_bytes(original)

    def test_code_state_reports_current_stale_and_unknown(self):
        self.assertEqual(
            daemon.code_state({"pid": 1, "port": 2, "token": "t",
                               "code": dashboard.served_code_fingerprint()}),
            "current")
        self.assertEqual(
            daemon.code_state({"pid": 1, "port": 2, "token": "t", "code": "0" * 16}),
            "stale")
        # A lock written before this field existed must never read as stale:
        # an upgrade in flight would otherwise restart a healthy daemon.
        self.assertEqual(daemon.code_state({"pid": 1, "port": 2, "token": "t"}), "unknown")
        self.assertEqual(daemon.code_state(None), "unknown")

    def test_status_flags_a_stale_daemon_with_an_action(self):
        httpd, token = self._live_ui_server()
        daemon.write_lock(self.root, {"pid": os.getpid(), "port": httpd.server_address[1],
                                      "token": token, "code": "0" * 16})
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = daemon.main(["--status", "--root", str(self.root)])
        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["status"], "alive")
        self.assertEqual(report["code"], "stale")
        self.assertIn("restart", report["action"].lower())
        self.assertNotIn("token", json.dumps(report), "the token never leaves /dash")

    def test_a_daemon_publishes_its_own_fingerprint_as_current(self):
        result = {}

        def target():
            result["code"] = daemon.run_daemon(self.root, with_otel=False,
                                               with_ingest=False,
                                               idle_seconds=1.0, poll_seconds=0.1)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        deadline = time.monotonic() + 10.0
        lock = None
        while time.monotonic() < deadline:
            status, lock = daemon.daemon_status(self.root)
            if status == "alive":
                break
            time.sleep(0.05)
        self.assertIsNotNone(lock)
        self.assertEqual(daemon.code_state(lock), "current")
        t.join(timeout=15.0)


class CivilisedPortTests(DaemonTestCase):
    """V1-c / spec §A.4 — two provisioned projects on one machine must coexist
    on 4318 without fighting.

    Every test here redirects `_otel_receiver._PORT` to an EPHEMERAL port: a
    suite that bound the real 4318 would fight the developer's own live daemon,
    which is precisely the behaviour under test.
    """

    def setUp(self):
        super().setUp()
        self._receiver = daemon._otel_receiver
        self._real_port = self._receiver._PORT
        self._receiver._PORT = self._free_port()

    def tearDown(self):
        self._receiver._PORT = self._real_port
        super().tearDown()

    @staticmethod
    def _free_port() -> int:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()      # released WITHOUT SO_REUSEADDR, so a bind gets it clean
        return port

    def _hold_port(self, handler_cls):
        import http.server
        httpd = http.server.HTTPServer(("127.0.0.1", self._receiver._PORT), handler_cls)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd, thread

    def test_a_kit_peer_holding_the_port_is_served_elsewhere_not_degraded(self):
        """A peer redacts and persists exactly as we do, and attributes by
        `agentkit.project_id`. So canal B is SERVED — just not by us. Reporting
        that as a failure would push an operator to kill another project's
        collector."""
        httpd, thread = self._hold_port(self._receiver.OTLPHandler)
        try:
            server, status = daemon._start_otel_thread()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        self.assertIsNone(server)
        self.assertEqual(status, "served_elsewhere")

    def test_a_foreign_holder_is_reported_as_degraded_foreign(self):
        """Distinguished from a peer because the consequence differs: every host
        keeps POSTing telemetry into a process we know nothing about, and this
        project collects nothing."""
        import http.server

        class _Foreign(http.server.BaseHTTPRequestHandler):
            server_version = "NotTheKit/1"
            sys_version = ""

            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        httpd, thread = self._hold_port(_Foreign)
        try:
            server, status = daemon._start_otel_thread()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        self.assertIsNone(server)
        self.assertEqual(status, "degraded_foreign")

    def test_an_unreachable_holder_triggers_one_immediate_rebind(self):
        """`unreachable` is not a verdict, it is a retry (iteration 1, C6): the
        bind failure was a race or the holder just died, and recording a
        permanent state on that would strand canal B until the next session."""
        real_server_cls = self._receiver._ExclusiveHTTPServer
        attempts = []

        class _FailsOnce(real_server_cls):
            def __init__(self, *args, **kwargs):
                attempts.append(1)
                if len(attempts) == 1:
                    raise OSError("simulated EADDRINUSE race")
                super().__init__(*args, **kwargs)

        self._receiver._ExclusiveHTTPServer = _FailsOnce
        try:
            server, status = daemon._start_otel_thread()
        finally:
            self._receiver._ExclusiveHTTPServer = real_server_cls
        try:
            self.assertEqual(status, "listening")
            self.assertEqual(len(attempts), 2, "the probe said unreachable — retry once")
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()

    def test_exactly_one_of_n_daemons_listens_and_the_rest_are_served_elsewhere(self):
        """T-00000084 — WHO ARBITRATES THE HANDOVER: nobody. There is no leader
        election and no successor list; the BIND is the arbiter, exactly as
        `O_CREAT|O_EXCL` is for the project lock. N daemons that all want 4318
        therefore produce one `listening` and N-1 `served_elsewhere`, which is
        the invariant "one router per machine" rests on.

        The attempts are SEQUENTIAL on purpose: fired concurrently, a loser can
        probe the winner in the microseconds between `HTTPServer.__init__`
        (which already listens) and the start of its accept thread, and get
        `unreachable` — that would measure thread scheduling, not exclusion."""
        first, status = daemon._start_otel_thread()
        self.assertEqual(status, "listening")
        self.assertIsNotNone(first)
        try:
            others = [daemon._start_otel_thread() for _ in range(3)]
            self.assertEqual([s for _, s in others],
                             ["served_elsewhere"] * 3)
            self.assertTrue(all(server is None for server, _ in others),
                            "a loser must not hold a socket it did not win")
        finally:
            first.shutdown()
            first.server_close()

    def test_a_dead_peer_is_reclaimed_at_the_poll_and_the_lock_is_rewritten(self):
        """The transition an operator actually lives through: the neighbouring
        project's session ends, its daemon auto-stops, and this daemon must pick
        the port up at its next 30 s poll — and REWRITE THE LOCK, because
        `--status` and the dashboard read `otel` from there and a stale
        `served_elsewhere` would describe a state that no longer exists."""
        httpd, thread = self._hold_port(self._receiver.OTLPHandler)
        result = {}

        def target():
            # A short idle window on purpose: the daemon must auto-stop by
            # itself at the end of this test rather than be left holding a
            # socket for the rest of the suite.
            #
            # `with_ingest=False` IS LOAD-BEARING, not tidiness. `AGENTS_EVENTS_DIR`
            # is not redirected here (this test is about a SOCKET), so an ingest
            # loop would open the developer's REAL events.db as a second writer —
            # racing their live daemon, deleting real spool files, and running the
            # V1-c backfill on real data from inside a unit test. Found by chasing
            # a flake this very test caused elsewhere in the suite.
            result["code"] = daemon.run_daemon(self.root, idle_seconds=5.0,
                                               poll_seconds=0.2, with_ingest=False)

        runner = threading.Thread(target=target, daemon=True)
        runner.start()
        try:
            deadline = time.monotonic() + 10.0
            lock = None
            while time.monotonic() < deadline:
                status, lock = daemon.daemon_status(self.root)
                if status == "alive":
                    break
                time.sleep(0.05)
            self.assertIsNotNone(lock)
            self.assertEqual(lock["otel"], "served_elsewhere",
                             "the peer holds the port at start-up")

            # T-00000084: a routing decision made (or, as here, planted) while
            # somebody ELSE held 4318 must not survive our taking it over — the
            # registry has necessarily moved, since the dying holder withdraws
            # its own entry on the way out.
            self._receiver._router_cache["stale-peer-id"] = (
                time.monotonic() + 3600.0, self.root)

            # The peer dies.
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                current = daemon.read_lock(self.root)
                if current and current.get("otel") == "listening":
                    break
                time.sleep(0.1)
            else:
                self.fail("the poll never re-bound canal B after the peer died")
            self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"],
                             "a rewritten lock must keep this daemon's own token")
            self.assertEqual(self._receiver._router_cache, {},
                             "reclaiming 4318 makes this daemon the machine's "
                             "router — it must re-prove every destination")
        finally:
            # The daemon stops itself on idle — asserted, not assumed: a thread
            # left holding this port would poison every later test in the suite.
            runner.join(timeout=45.0)
            self.assertFalse(runner.is_alive(), "the daemon must auto-stop on idle")
            self.assertEqual(result.get("code"), 0)
            self.assertFalse(daemon.lock_path(self.root).exists(),
                             "auto-stop removes its own lock")


class MsysRootTests(DaemonTestCase):
    """Found in use: every hook exports CLAUDE_PROJECT_DIR through `cygpath -u`,
    so the documented `--dash --root "$CLAUDE_PROJECT_DIR"` handed this CLI a
    `/c/Users/...` path native Python cannot resolve. The lock then resolved
    under a nonexistent tree: a live daemon read as absent, the spawn inherited
    the same broken root, and --dash exited 2 claiming no daemon could be
    started while one was running."""

    def test_native_root_passes_through(self):
        self.assertEqual(daemon.normalize_root(self.root), self.root)
        self.assertEqual(daemon.normalize_root(str(self.root)), self.root)

    def test_msys_style_root_is_translated_when_that_is_what_exists(self):
        native = str(self.root)  # e.g. C:\Users\...\Temp\xyz
        if not re.match(r"^[A-Za-z]:", native):
            self.skipTest("not a drive-letter platform")
        drive, rest = native[0], native[2:].replace("\\", "/")
        msys = f"/{drive.lower()}/{rest.lstrip('/')}"
        self.assertFalse(Path(msys).exists(), "sanity: the MSYS form must not resolve natively")
        resolved = daemon.normalize_root(msys)
        self.assertTrue(resolved.exists(), f"MSYS root {msys!r} was not translated")
        self.assertEqual(resolved.resolve(), self.root.resolve())

    def test_an_msys_root_finds_a_live_daemons_lock(self):
        """The property that actually broke: same tree, two spellings, one lock."""
        httpd, token = self._live_ui_server()
        daemon.write_lock(self.root, {"pid": os.getpid(), "port": httpd.server_address[1],
                                      "token": token})
        native = str(self.root)
        if not re.match(r"^[A-Za-z]:", native):
            self.skipTest("not a drive-letter platform")
        msys = f"/{native[0].lower()}/{native[2:].replace(chr(92), '/').lstrip('/')}"
        self.assertEqual(daemon.daemon_status(daemon.normalize_root(msys))[0], "alive")

    def test_unresolvable_root_is_returned_as_is_not_silently_remapped(self):
        bogus = "/zz/definitely/not/here"
        self.assertEqual(str(daemon.normalize_root(bogus)), str(Path(bogus)))
        self.assertIsNone(daemon.normalize_root(None))


class LivenessCostTests(DaemonTestCase):
    """T-00000043 root cause: the liveness probe must not pay the cost of the
    heaviest read. Reopened after closing it once on the timing symptoms —
    the intermittent failures were the messenger, this coupling was the defect."""

    def test_ping_route_is_cheap_and_carries_no_repo_data(self):
        import json as _json
        import urllib.request

        httpd, token = self._live_ui_server()
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
            self.assertEqual(resp.status, 200)
        payload = _json.loads(body)
        self.assertTrue(payload["ok"])
        # Cheap is the point: a liveness answer that carried board/ledger data
        # would reintroduce the coupling under a different name.
        self.assertLess(len(body), 200, f"the ping answer grew to {len(body)} bytes")
        for forbidden in ("board", "ledger", "specs", "views", "events"):
            self.assertNotIn(forbidden, payload)

    def test_ping_route_still_requires_the_token(self):
        import urllib.error
        import urllib.request

        httpd, _token = self._live_ui_server()
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

    def test_ping_falls_back_when_the_route_is_absent(self):
        """An older daemon (started before this change) has no /api/ping. It
        must still read as alive, or an upgrade in flight looks like a death."""
        real_probe = daemon._probe
        calls = []

        def fake_probe(port, path, token, timeout):
            calls.append(path)
            return None if path == "/api/ping" else True

        daemon._probe = fake_probe
        try:
            self.assertTrue(daemon.ping(1234, "tok"))
        finally:
            daemon._probe = real_probe
        self.assertEqual(calls, ["/api/ping", "/api/snapshot"])

    def test_ping_does_not_fall_back_on_a_wrong_token(self):
        """A 401 is an answer, not an absent route: no second probe, no
        pretending an imposter is ours."""
        httpd, _token = self._live_ui_server()
        port = httpd.server_address[1]
        self.assertFalse(daemon.ping(port, "not-our-token"))


class EmpreinteLocaleTests(DaemonTestCase):
    """L'EMPREINTE LOCALE RENDUE PAR `--status` — T-00000612 et T-00000613.

    CE QUE CES ARMS DÉFENDENT. Les deux tickets demandent la même chose en
    premier : instrumenter avant de chercher la fuite. Le 2026-09-14 le démon
    tenait 3,5 Go après 1 h 40 et a fait TUER une porte par l'OS — pas un rouge,
    un incident de machine, le seul mode d'échec qu'aucun verdict ne nomme. Et
    `events.db` pesait 628 936 704 octets sans que rien ne le signale, vivant sous
    `.agents/state/local/` qui est git-ignoré : aucun diff, aucune revue.

    Retirer ces deux champs rendrait les deux croissances invisibles à nouveau,
    et rien d'autre ne rougirait.
    """

    def test_l_empreinte_est_rendue_en_OCTETS_BRUTS(self):
        """OCTETS, JAMAIS DES Mo — leçon payée le jour même.

        La première rédaction rendait des « Mo » : les tickets les écrivaient en
        Mo DÉCIMAUX, l'instrument en Mio. Le même fichier valait 628,9 d'un côté
        et 599,8 de l'autre, sur des nombres censés porter une décision de
        plafond. Un entier d'octets ne peut pas être mal lu.
        """
        src = (HERE / "dashboard_daemon.py").read_text(encoding="utf-8")
        self.assertIn("rss_octets", src)
        self.assertIn("events_db_octets", src)
        self.assertNotIn("rss_mo", src, "retour à une unité ambiguë")
        self.assertNotIn("events_db_mo", src, "retour à une unité ambiguë")

    def test_l_empreinte_est_REELLEMENT_CABLEE_dans_status(self):
        """LE CÂBLAGE, PAS SEULEMENT LE HELPER — et cet arm existe parce que mon
        contrôle de non-vacuité a ÉCHOUÉ sans lui.

        Les trois autres arms testent les fonctions et le texte source. Je les
        ai écrits, puis j'ai débranché `_empreinte_locale` de `--status` pour
        vérifier qu'ils mordaient : ILS SONT TOUS RESTÉS VERTS. Un instrument
        jamais appelé aurait donc passé la porte, et les deux croissances
        seraient redevenues invisibles sans qu'une seule surface rougisse.
        C'est exactement la classe de défaut que ce dépôt refuse ailleurs.
        """
        import contextlib
        import io

        httpd, token = self._live_ui_server()
        daemon.write_lock(self.root, {"pid": os.getpid(),
                                      "port": httpd.server_address[1],
                                      "token": token,
                                      "code": dashboard.served_code_fingerprint()})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(daemon.main(["--status", "--root", str(self.root)]), 0)
        report = json.loads(buf.getvalue())
        self.assertIn(
            "empreinte", report,
            "`--status` ne rend plus l'empreinte locale : la mémoire du démon et "
            "le poids du store redeviennent invisibles (T-00000612, T-00000613)",
        )
        self.assertIn("rss_octets", report["empreinte"])
        self.assertIn("events_db_octets", report["empreinte"])
        self.assertNotIn("token", json.dumps(report), "le token ne quitte que /dash")

    def test_le_poids_du_store_est_rendu_par_status_MEME_demon_arrete(self):
        """LE CÂBLAGE DE L'AUTRE MOITIÉ — trou laissé ouvert par mon premier
        témoin de câblage, et trouvé par le binôme.

        `events.db` grossit que le démon tourne ou non, et c'est APRÈS un
        `--stop`, ou le matin avant d'ouvrir le dashboard, que le pilote
        regarde. La première rédaction enfermait l'appel dans `if status ==
        "alive"` : la branche `lock=None` de `_empreinte_locale` n'était donc
        joignable QUE depuis ce banc, jamais depuis la CLI. Un banc qui exerce
        un chemin que le produit ne produit pas est un banc qui se ment.
        """
        import contextlib
        import io

        local = self.root / ".agents" / "state" / "local"
        local.mkdir(parents=True, exist_ok=True)
        (local / "events.db").write_bytes(b"x" * 4242)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(daemon.main(["--status", "--root", str(self.root)]), 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["status"], "absent")
        self.assertEqual(report["empreinte"]["events_db_octets"], 4242)

    def test_le_RSS_est_un_ENTIER_POSITIF_sur_un_pid_vivant(self):
        """NON-VACUITÉ, et sans lui les autres arms sont décoratifs.

        Les trois premiers n'assertent que `None` ou la présence de la clé. Un
        `_rss_octets` dégradé en `None` permanent — `ps` busybox sans `-o rss=`,
        l'import retiré, une exception avalée par le `except Exception` — les
        laisse TOUS verts, et la croissance à 3,5 Go redevient invisible. C'est
        le mode d'échec nommé par `T-00000613`, reproduit par le filet censé le
        voir.
        """
        octets = daemon._rss_octets(os.getpid())
        self.assertIsInstance(octets, int)
        self.assertGreater(octets, 1_000_000,
                           "un interpréteur Python vivant pèse plus d'un Mo")

    def test_une_mesure_absente_rend_None_jamais_zero(self):
        """UN ZÉRO SE LIRAIT « le processus ne consomme rien ». Sur un pid qui
        n'existe pas, `ps` ne rend rien : la seule réponse honnête est None."""
        self.assertIsNone(daemon._rss_octets(999999))
        self.assertIsNone(daemon._rss_octets("pasunpid"))

    def test_le_poids_du_store_est_lu_meme_sans_demon(self):
        """Le store grossit que le démon tourne ou non : son poids ne dépend pas
        d'un verrou. Contrôle des deux sens — fichier présent puis absent."""
        racine = self.root
        local = racine / ".agents" / "state" / "local"
        local.mkdir(parents=True, exist_ok=True)
        (local / "events.db").write_bytes(b"x" * 4242)
        emp = daemon._empreinte_locale(racine, None)
        self.assertEqual(emp["events_db_octets"], 4242)
        self.assertNotIn("rss_octets", emp, "pas de verrou => pas de pid => pas de RSS")

        (local / "events.db").unlink()
        self.assertIsNone(daemon._empreinte_locale(racine, None)["events_db_octets"])
