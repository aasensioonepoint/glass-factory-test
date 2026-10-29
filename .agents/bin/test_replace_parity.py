#!/usr/bin/env python3
"""Parity net for the SEVEN `_replace_with_retry` copies in .agents/bin/ (T-00000066).

`build_index.py`, `events.py`, `event_store.py`, `project_init.py`, `tasks.py`,
`ledger.py` and `specs.py` each carry their OWN copy of the retried atomic
replace (T-00000053 / L-00000054): `os.replace`, retried ONLY on the Windows
sharing violation (`PermissionError`), `_REPLACE_ATTEMPTS` (30) times spaced
`_REPLACE_DELAY_SECONDS` (0.01 s) apart, re-raising the LAST exception so the
traceback names the real cause.

WHY A NET AND NOT AN EXTRACTION. Folding the seven into one shared module was
weighed and REJECTED on survey, not out of caution (see docs/tasks/LOT-6-plan.md
section T-00000066): `events.py` carries a written contract of zero local
dependencies (event_store.py:152-154) and the hooks swallow any exception raised
while loading it, so a missing sibling in a vendored copy would kill ALL
telemetry in silence; two module-scope nets already pin the surface per file
(test_state_atomic.py, test_build_index_atomic.py); and the seven copies are NOT
byte-identical (tasks.py embeds the board commit-guard, build_index.py is
untyped and lacks the `assert`, project_init.py types its parameters `str`). The
named risk is a FUTURE correction diverging one copy from the others; this net is
what makes that divergence go RED — and, like test_state_atomic.py's docstring
promises, NAMES the file that broke (every assertion carries the module name).

WHY IT RUNS EVERYWHERE, INCLUDING macOS AND ubuntu CI. Nothing is skipped by
platform: the sharing violation is INJECTED by monkeypatching `os.replace`,
never provoked by opening a real handle. The retry is therefore exercised
identically on the three platforms the kit meets — Windows dev boxes, ubuntu CI,
macOS — instead of only on the one where a real handle can be held.

WHAT THIS TESTS AND HOW. The four properties are checked on the FUNCTION
DIRECTLY — `module._replace_with_retry(src, target)` with `os.replace` swapped —
never by driving `emit()`, `save()` or the SQLite store, so a divergence is
localised to the helper rather than diluted through a whole publish path. The
trio tasks/ledger/specs is bare-imported (the same instances test_state_atomic.py
holds, so no second module is created); the other four are loaded by
`spec_from_file_location` REGISTERED in `sys.modules` BEFORE `exec_module` — the
Python 3.14 lesson from test_migrate_layout.py:28-56 (a class body resolves
`sys.modules[cls.__module__]` during construction and explodes on an absent
module).

OUT OF SCOPE, NAMED so its absence does not read as an oversight: wrap.py:211
carries an EIGHTH `_replace_with_retry` of DIFFERENT semantics (returns a bool,
`attempts`/`sleep_s` parameters) — outside the T-00000053 recipe and tested on
its own in test_wrap.py.

Structural precedent: .agents/evals/test_ledger_parity.py (cross-surface parity)
and test_state_atomic.py:11-15 ("name the file that broke").
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def load_by_path(name: str, path: Path) -> ModuleType:
    """Load `path` as module `name`, REGISTERED in `sys.modules` BEFORE its body
    runs (the Python 3.14 lesson — test_migrate_layout.py:28-56). On a failed
    exec the name is removed again, so a half-built module is never left for the
    next importer to find. Deliberately the same shape as that helper, not a
    variant of it."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


# The trio bare-imported — the SAME instances test_state_atomic.py drives, so
# this net never forks a second copy of them (see module docstring).
import ledger  # noqa: E402
import specs  # noqa: E402
import tasks  # noqa: E402

# The other four by explicit-path load (register-before-exec). event_store.py
# pulls events.py + otel_receiver.py at import under its own sibling names, as
# test_event_store.py already exercises under pytest — reused as-is.
build_index = load_by_path("build_index", HERE / "build_index.py")
events = load_by_path("events", HERE / "events.py")
event_store = load_by_path("event_store", HERE / "event_store.py")
project_init = load_by_path("project_init", HERE / "project_init.py")

# (module, human name) — the seven copies under T-00000053's recipe. tasks.py's
# copy also runs the board commit-guard, but its ContextVar defaults to None, so
# with no guard installed it takes the exact same path as the other six here.
MODULES = (
    (build_index, "build_index.py"),
    (events, "events.py"),
    (event_store, "event_store.py"),
    (project_init, "project_init.py"),
    (tasks, "tasks.py"),
    (ledger, "ledger.py"),
    (specs, "specs.py"),
)


class ReplaceWithRetryParityTests(unittest.TestCase):
    def test_every_copy_keeps_the_kit_wide_bound(self):
        """Property 1: the two constants every copy shares. A copy that drifts
        off 30 x 0.01 s is named."""
        for module, name in MODULES:
            with self.subTest(module=name):
                self.assertTrue(
                    hasattr(module, "_replace_with_retry"),
                    f"{name} has no _replace_with_retry")
                self.assertEqual(
                    module._REPLACE_ATTEMPTS, 30,
                    f"{name} must keep the kit-wide retry bound of 30")
                self.assertEqual(
                    module._REPLACE_DELAY_SECONDS, 0.01,
                    f"{name} must keep the kit-wide 10 ms delay")

    def test_a_transient_sharing_violation_is_absorbed(self):
        """Property 2: a reader that lets go after a few milliseconds must not
        fail the write. INJECTED via os.replace, so this is portable."""
        for module, name in MODULES:
            with self.subTest(module=name):
                calls = {"n": 0}

                def flaky(src, dst, _c=calls):
                    _c["n"] += 1
                    if _c["n"] <= 3:
                        raise PermissionError(13, "used by another process")
                    return None

                real_replace = os.replace
                os.replace = flaky
                try:
                    module._replace_with_retry("src", "dst")
                finally:
                    os.replace = real_replace
                self.assertEqual(
                    calls["n"], 4,
                    f"{name} did not retry the transient sharing violation")

    def test_a_non_sharing_oserror_raises_on_the_first_attempt(self):
        """Property 3: only PermissionError is retried. Any OTHER OSError must
        surface on the FIRST call — retrying a genuinely broken path would turn
        a clear failure into 300 ms of silence and then the same failure."""
        for module, name in MODULES:
            with self.subTest(module=name):
                calls = {"n": 0}

                def broken(src, dst, _c=calls):
                    _c["n"] += 1
                    raise OSError(22, "invalid argument")

                real_replace = os.replace
                os.replace = broken
                try:
                    with self.assertRaises(OSError) as caught:
                        module._replace_with_retry("src", "dst")
                finally:
                    os.replace = real_replace
                self.assertNotIsInstance(
                    caught.exception, PermissionError,
                    f"{name} test injected the wrong error class")
                self.assertEqual(
                    calls["n"], 1,
                    f"{name} retried a non-sharing OSError")

    def test_exhaustion_reraises_the_last_exception_after_exactly_the_bound(self):
        """Property 4: a reader that never lets go fails LOUDLY, with the LAST
        exception (not a manufactured one), after EXACTLY _REPLACE_ATTEMPTS
        calls. The injected message carries the attempt number, so 'the last
        one' is proven rather than assumed."""
        for module, name in MODULES:
            with self.subTest(module=name):
                calls = {"n": 0}

                def never(src, dst, _c=calls):
                    _c["n"] += 1
                    raise PermissionError(13, f"held #{_c['n']}")

                real_replace = os.replace
                saved_delay, module._REPLACE_DELAY_SECONDS = (
                    module._REPLACE_DELAY_SECONDS, 0.0)
                os.replace = never
                try:
                    with self.assertRaises(PermissionError) as caught:
                        module._replace_with_retry("src", "dst")
                finally:
                    os.replace = real_replace
                    module._REPLACE_DELAY_SECONDS = saved_delay
                self.assertEqual(
                    calls["n"], module._REPLACE_ATTEMPTS,
                    f"{name} gave up early or looped past its bound")
                self.assertIn(
                    f"held #{module._REPLACE_ATTEMPTS}", str(caught.exception),
                    f"{name} did not re-raise the LAST exception")


if __name__ == "__main__":
    unittest.main()
