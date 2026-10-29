"""The three state stores publish with the SAME retried replace (T-00000053).

`tasks.py`, `ledger.py` and `specs.py` each write their `.json` source of truth
through mkstemp -> write -> close -> chmod -> replace. The replace was BARE
`os.replace`, which on Windows raises `PermissionError` when a reader holds the
target open — measured at 69-81 % failure under a concurrent reader
(L-00000054). The reader is not hypothetical for these three: the dashboard
daemon reads all of them on every snapshot, and the ledger is read again at
every SessionStart on four hosts.

WHY ONE PARAMETRISED MODULE AND NOT THREE TESTS. The three implementations are
character-for-character the same recipe, and the realistic regression is that
someone edits ONE of them back to a bare `os.replace`. A test per file would let
that pass in the two others' green; parametrising over the trio makes the suite
name the file that broke.

WHY THIS RUNS EVERYWHERE, INCLUDING macOS. Nothing here is skipped by platform:
the sharing violation is INJECTED by monkeypatching `os.replace`, never
provoked by opening a real handle. So the retry is exercised identically on
macOS, Linux and Windows — which matters, because the kit is developed on
Windows, its CI is ubuntu, and it must run on mac. A test that could only prove
this on Windows would prove it on the one platform where CI never looks.
"""
import json
import os
import unittest
from pathlib import Path

import ledger
import specs
import tasks

# (module, human name, a callable that writes the store once)
STORES = (
    (tasks, "tasks.py", lambda root: tasks.save(root, {"tasks": [], "next_id": 1})),
    (ledger, "ledger.py", lambda root: ledger.save(root, {"entries": [], "next_id": 1})),
    (specs, "specs.py", lambda root: specs.save(root, {"entries": [], "next_id": 1})),
)


class RetriedReplaceTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        # Windows can hold a handle open in git/AV at teardown; never let an
        # assertion depend on cleanup having succeeded (L-00000035).
        self._tmpdir.cleanup()

    def test_every_store_publishes_through_the_retrying_helper(self):
        """The property, stated once: no store may call `os.replace` directly."""
        for module, name, _write in STORES:
            with self.subTest(store=name):
                self.assertTrue(
                    hasattr(module, "_replace_with_retry"),
                    f"{name} has no _replace_with_retry: it is publishing bare")
                self.assertEqual(module._REPLACE_ATTEMPTS, 30,
                                 f"{name} must keep the kit-wide bound")
                self.assertEqual(module._REPLACE_DELAY_SECONDS, 0.01)

    def test_a_transient_sharing_violation_is_absorbed(self):
        """The case the fix exists for: a reader holds the target for a few
        milliseconds, the write must still land. INJECTED, not provoked — see
        the module docstring on why that makes this test portable."""
        for module, name, write in STORES:
            with self.subTest(store=name):
                real_replace = os.replace
                calls = {"n": 0}

                def flaky(src, dst, _real=real_replace, _c=calls):
                    _c["n"] += 1
                    if _c["n"] <= 3:
                        raise PermissionError(13, "used by another process")
                    return _real(src, dst)

                os.replace = flaky
                try:
                    write(self.root)
                finally:
                    os.replace = real_replace

                self.assertEqual(calls["n"], 4, f"{name} did not retry")
                payload = json.loads(module.store_path(self.root).read_text(encoding="utf-8"))
                collection = "tasks" if module is tasks else "entries"
                self.assertIn(collection, payload, f"{name} did not publish after retrying")
                # T-00000726: the counter handed to `save` is never published.
                self.assertNotIn("next_id", payload, f"{name} published a counter")

    def test_a_real_error_is_not_retried_into_a_hang(self):
        """Non-vacuity of the `except PermissionError` clause: any OTHER OSError
        must surface on the FIRST attempt. Retrying a genuinely broken path
        would turn a clear failure into a 300 ms silence and then the same
        failure — worse, not safer."""
        for module, name, write in STORES:
            with self.subTest(store=name):
                real_replace = os.replace
                calls = {"n": 0}

                def broken(src, dst, _c=calls):
                    _c["n"] += 1
                    raise OSError(22, "invalid argument")

                os.replace = broken
                try:
                    with self.assertRaises(OSError):
                        write(self.root)
                finally:
                    os.replace = real_replace
                self.assertEqual(calls["n"], 1, f"{name} retried a non-sharing error")

    def test_exhaustion_reraises_the_last_real_exception(self):
        """A reader that never lets go must fail LOUDLY, and with the original
        error rather than a manufactured one, so the traceback names the cause."""
        for module, name, write in STORES:
            with self.subTest(store=name):
                real_replace = os.replace
                calls = {"n": 0}

                def never(src, dst, _c=calls):
                    _c["n"] += 1
                    raise PermissionError(13, "held forever")

                module._REPLACE_DELAY_SECONDS, saved = 0.0, module._REPLACE_DELAY_SECONDS
                os.replace = never
                try:
                    with self.assertRaises(PermissionError) as caught:
                        write(self.root)
                finally:
                    os.replace = real_replace
                    module._REPLACE_DELAY_SECONDS = saved

                self.assertEqual(calls["n"], module._REPLACE_ATTEMPTS,
                                 f"{name} gave up early or looped past its bound")
                self.assertIn("held forever", str(caught.exception))

    def test_the_temp_file_never_survives_a_failed_publish(self):
        """The staged file is discarded on every failure path, or a directory
        accumulates `.tmp` debris that a later reader could mistake for a store."""
        for module, name, write in STORES:
            with self.subTest(store=name):
                real_replace = os.replace
                module._REPLACE_DELAY_SECONDS, saved = 0.0, module._REPLACE_DELAY_SECONDS
                os.replace = lambda src, dst: (_ for _ in ()).throw(
                    PermissionError(13, "held forever"))
                try:
                    with self.assertRaises(PermissionError):
                        write(self.root)
                finally:
                    os.replace = real_replace
                    module._REPLACE_DELAY_SECONDS = saved

                leftovers = list(module.store_path(self.root).parent.glob("*.tmp"))
                self.assertEqual(leftovers, [], f"{name} left a staged temp behind")


if __name__ == "__main__":
    unittest.main()
