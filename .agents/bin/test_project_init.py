"""Tests for project_init.py — the immutable project-identity generator
(T-00000048, V1-a).

Every test runs project_init.py as a REAL subprocess against a fresh temp git
repo, because the two properties that matter most are cross-process: the
O_CREAT|O_EXCL exactly-one-winner race, and the git user.name gate reading the
repo's own config. In-process calls could not exercise either honestly.

Fixture discipline: `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`
(L-00000035 — Windows may still hold a handle at teardown), and each temp repo
does `git init` + `git config user.name test` so the identity gate passes by
default. The one gate test overrides that with an isolated, empty git config.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "project_init.py"


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    # Decode explicitly (never the parent locale). git output is never
    # asserted on content here, and git may emit non-UTF-8 -> errors="replace"
    # so a decode crash can't masquerade as a test failure.
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)


def _run_init(repo: Path, *args: str, env: dict | None = None,
              stdin=None, fermer_stdin: bool = False) -> subprocess.CompletedProcess:
    """project_init.py with cwd=repo so its git rev-parse / git config resolve
    against THIS repo.

    stderr/stdout are pinned to UTF-8 on BOTH sides so the gate is green
    whatever encoding vars the parent shell exports (the Windows false-red:
    with PYTHONIOENCODING=utf-8 exported the child emits UTF-8, decoded as
    cp1252 locale -> « déjà initialisée » mojibake, l.230 assertion fails):
      * child side  -> PYTHONIOENCODING="utf-8" forces the child to EMIT
        UTF-8 regardless of the parent's value; set on a COPY of the env,
        never a mutation of the caller's dict.
      * parent side -> encoding="utf-8" (errors default = STRICT: both sides
        are pinned, so an unexpected byte MUST surface, not be replaced).
    Decoding alone would just move the false-red (crash WITHOUT the var).
    ROLLBACK (both sides, restore locale-decoded text=True):
        git checkout -- .agents/bin/test_project_init.py
    EMITTER DEBT (out of write-set, C3): project_init.py writes stderr via
    _die (:106) / _handle_collision « déjà initialisée » (:130) straight to
    sys.stderr without reconfiguring its own stdio encoding — a real pilot
    run on a cp1252 Windows console (no PYTHONIOENCODING) can still mojibake.
    The child-side pin here only holds under THIS harness; the emitter fix
    belongs to a task on project_init.py, not this file.
    `fermer_stdin` runs the child with fd 0 CLOSED (`0<&-`, through bash,
    POSIX only); `stdin` is passed through to subprocess.run (T-00001103).
    """
    run_env = dict(os.environ) if env is None else dict(env)
    run_env["PYTHONIOENCODING"] = "utf-8"
    argv = [sys.executable, str(SCRIPT), *args]
    if fermer_stdin:
        argv = ["bash", "-c", 'exec "$@" 0<&-', "_", *argv]
    return subprocess.run(
        argv, stdin=stdin,
        cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", env=run_env,
    )


def _isolated_git_env(base: dict | None = None) -> dict:
    """A git environment with NO global/system config, so `git config
    user.name` reflects only what a test sets in the repo — the machine's real
    user.name never leaks in."""
    env = dict(os.environ) if base is None else dict(base)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


class ProjectInitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.repo = Path(self._tmp.name)
        # Isolate from the machine's real global git identity in EVERY test.
        self.env = _isolated_git_env()
        _git(self.repo, "init")
        _git(self.repo, "config", "user.name", "test", env=self.env)

    def tearDown(self):
        self._tmp.cleanup()

    def _identity(self) -> dict:
        return json.loads((self.repo / ".agents" / "state" / "project.json").read_text(encoding="utf-8"))

    # -- init --------------------------------------------------------------

    def test_init_writes_expected_keys_and_defaults(self):
        result = _run_init(self.repo, "--name", "My Cool Project", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        ident = self._identity()
        self.assertEqual(set(ident), {"project_id", "name", "slug", "created"})
        # No `user` / personal-identity field ever (spec §A.1).
        self.assertNotIn("user", ident)
        self.assertEqual(ident["name"], "My Cool Project")
        self.assertTrue(ident["project_id"])
        self.assertTrue(ident["created"].endswith("Z"))

    def test_slug_is_derived_and_fs_safe(self):
        _run_init(self.repo, "--name", "  Héllo, World!!  ", env=self.env)
        slug = self._identity()["slug"]
        # lowercase, non-alphanumeric squeezed to single '-', trimmed.
        self.assertEqual(slug, "h-llo-world")
        self.assertRegex(slug, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    # -- default name without input (T-00001103, lot A) --------------------

    def _assert_default_name(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self._identity()["name"], self.repo.name)
        self.assertIn("--rename", result.stderr)
        self.assertIn(f"« {self.repo.name} »", result.stderr)

    def test_empty_stdin_without_name_defaults_to_the_repo_basename(self):
        self._assert_default_name(
            _run_init(self.repo, env=self.env, stdin=subprocess.DEVNULL))

    @unittest.skipIf(os.name == "nt", "fd 0 closed through bash: POSIX only")
    def test_closed_stdin_without_name_defaults_to_the_repo_basename(self):
        self._assert_default_name(_run_init(self.repo, env=self.env, fermer_stdin=True))

    def test_an_empty_line_read_on_stdin_is_still_refused(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], input="\n", cwd=str(self.repo),
            capture_output=True, text=True, encoding="utf-8",
            env={**self.env, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ne peut pas être vide", result.stderr)
        self.assertFalse((self.repo / ".agents" / "state" / "project.json").exists())

    # -- state stores provisioned at init (decision D7) --------------------

    def _tasks(self):
        """The board's OWNER module, imported the same way the crash arm at the
        bottom of this file imports project_init: a `sys.path` insertion and a
        plain `import`. No `exec_module` anywhere here, so the modload net's
        `sys.modules[spec.name]` idiom (which governs LOADERS) does not apply."""
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import tasks

        return tasks

    def _board(self) -> Path:
        return self.repo / ".agents" / "state" / "board" / "TASKS.json"

    def _view(self) -> Path:
        return self.repo / ".agents" / "state" / "local" / "TASKS.md"

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_init_provisions_a_board_its_owner_can_read(self):
        """THE DEFECT THIS CLOSES: an adopting project had a RED gate on its
        first day — `check-stale-justification.sh` exits 1 on a missing board
        and `verify.sh` runs it, so a project that had never opened a task
        failed a gate for having nothing to fail.

        PRESENCE IS NOT THE PROPERTY. A file that the board's OWNER cannot read
        would MOVE the failure rather than close it (the next verb to touch the
        board would raise instead), so the store is re-read through
        `tasks.load` — which validates and raises on a malformed board — and
        its shape asserted. The view is asserted too: it is what the pilot and
        the SessionStart hooks actually display."""
        result = _run_init(self.repo, "--name", "Adoptant", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._board().exists(), result.stdout)
        self.assertTrue(self._view().exists(), "la vue TASKS.md doit etre regeneree")
        data = self._tasks().load(self.repo)  # raises on a malformed store
        self.assertEqual(data["tasks"], [])
        self.assertIn("board cree", result.stdout)
        # The output is the only discoverability this has until the doc task
        # lands: what remains to do, and which stores are NORMALLY absent.
        self.assertIn("RESTE A FAIRE", result.stdout)
        self.assertIn("magasins paresseux", result.stdout)

    def test_a_board_already_there_is_never_overwritten(self):
        """The property that makes this safe to ship at all: provisioning is an
        EXISTENCE GUARD, never a merge and never a repair. A project that has
        been tracking tasks for months must come out of an init byte-for-byte
        identical.

        ASSERTED ON THE SHA256, not on existence: a board that had just been
        overwritten with the empty structure still EXISTS, so an existence
        assertion would stay green through exactly the data loss this arm is
        here to make impossible. Both entry points are exercised, because both
        can reach the provisioning code."""
        tasks = self._tasks()
        tasks.new_task(self.repo, "une tache qui existait avant l init", "", "")
        before = self._sha256(self._board())

        init = _run_init(self.repo, "--name", "Adoptant", env=self.env)
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertEqual(self._sha256(self._board()), before,
                         "l init a reecrit un board qui existait deja")

        again = _run_init(self.repo, "--ensure-stores", env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self._sha256(self._board()), before,
                         "--ensure-stores a reecrit un board qui existait deja")
        self.assertIn("deja present", again.stdout)

    def test_ensure_stores_is_idempotent_and_leaves_the_identity_alone(self):
        """The REPAIR gesture — for a project inited before this flag existed,
        where the identity is on disk and the board is not. Run twice back to
        back: the second pass must say so and change nothing, because a
        provisioning step that is not idempotent is one a pilot cannot re-run
        after a failure, which is precisely when it gets re-run.

        It must also NOT create an identity: the whole point of a separate flag
        is that it touches the stores and nothing else."""
        first = _run_init(self.repo, "--ensure-stores", env=self.env)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("board cree", first.stdout)
        after_first = self._board().read_bytes()
        self.assertFalse((self.repo / ".agents" / "state" / "project.json").exists(),
                         "--ensure-stores ne doit jamais fabriquer une identite")

        second = _run_init(self.repo, "--ensure-stores", env=self.env)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("deja present", second.stdout)
        self.assertNotIn("board cree", second.stdout)
        self.assertEqual(self._board().read_bytes(), after_first)

    def _obstruct_the_board(self, repo: Path) -> None:
        """Make provisioning FAIL, without touching project_init.py.

        A regular FILE where `tasks.save()` must `mkdir` a DIRECTORY: `mkdir(...,
        exist_ok=True)` suppresses FileExistsError only when the target is a
        directory, so this raises OSError from inside the owner module — a
        failure of the STORE, reached through the real code path.

        WHY THIS OBSTRUCTION AND NOT A PERMISSION BIT: `chmod 0o500` is not a
        verdict on Windows and is a no-op under root, so the arm would go green
        by ACCIDENT on two hosts — the exact vacuity this arm exists to refuse.
        A stray file is deterministic and portable, and it is the same class of
        failure as a read-only mount: the store cannot be created, cause
        unknown to us. `.agents/state/` itself stays a real directory, so the
        IDENTITY write still succeeds — which is the whole point."""
        (repo / ".agents" / "state").mkdir(parents=True, exist_ok=True)
        (repo / ".agents" / "state" / "board").write_text("", encoding="utf-8")

    def test_a_board_that_cannot_be_written_degrades_without_losing_the_identity(self):
        """THE DEGRADED PATH, WHICH NOTHING ELSE EXERCISES.

        This tool is the FIRST thing an adopting project runs, so its failure
        mode is not a detail: the identity is generated ONCE and is
        irrecoverable if lost (an uuid4 not minted at init can never be minted
        again). A secondary store failing must therefore cost the board and
        NOTHING else.

        Four properties, and each one can fail on its own:
          1. `do_init` still returns 0 — the identity IS on disk, and an exit 2
             would tell the pilot to re-run an init that would then collide.
          2. `project.json` really is there — asserting the code alone would
             pass on an init that returned 0 having written nothing.
          3. the failure is NAMED, with its CAUSE, on STDERR — a degradation
             that prints nothing reads as "there was nothing to do", and the
             cause is what makes the remedy actionable.
          4. `--ensure-stores` ALONE returns 2 — there the store was the ONLY
             thing asked for, so its failure is the whole result.
        """
        self._obstruct_the_board(self.repo)

        init = _run_init(self.repo, "--name", "Adoptant", env=self.env)
        # 1 + 2 — the identity survives the store's failure.
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertTrue((self.repo / ".agents" / "state" / "project.json").exists(),
                        "l identite doit etre ecrite meme si le board echoue")
        self.assertTrue(self._identity()["project_id"])
        self.assertFalse(self._board().exists())

        # 3 — named, with its cause, and on the RIGHT channel. The cause is
        # asserted NON-EMPTY rather than verbatim: pinning an OSError's exact
        # wording would make this arm a test of the platform's error strings.
        self.assertIn("ATTENTION — board non provisionne", init.stderr)
        cause = re.search(r"ATTENTION — board non provisionne \(([^)]*)\)", init.stderr)
        self.assertIsNotNone(cause, init.stderr)
        self.assertTrue(cause.group(1).strip(), "la cause ne doit pas etre vide")
        # The remedy is the half that makes the warning actionable.
        self.assertIn("--ensure-stores", init.stderr)
        # Channel pinned both ways: stdout carries the SUCCESS narrative only,
        # so a hook parsing it never reads a failure as a provisioning.
        self.assertNotIn("ATTENTION", init.stdout)
        self.assertNotIn("board cree", init.stdout)

        # 4 — the flag alone: the store was the entire request.
        flag = _run_init(self.repo, "--ensure-stores", env=self.env)
        self.assertEqual(flag.returncode, 2, flag.stderr or flag.stdout)
        self.assertIn("ATTENTION — board non provisionne", flag.stderr)
        self.assertEqual(flag.stdout.strip(), "")

    # -- --print-otel-env (V1-c, T-00000050) -------------------------------

    def test_print_otel_env_prints_the_real_project_id_and_writes_nothing(self):
        """The pilot's copy-paste step. It must print the REAL id — a doc could
        only ever show a placeholder, and a placeholder pasted verbatim is an
        attribution that lands in nobody's bucket."""
        _run_init(self.repo, "--name", "Attributed", env=self.env)
        ident = self._identity()
        before = (self.repo / ".agents" / "state" / "project.json").read_bytes()

        result = _run_init(self.repo, "--print-otel-env", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id={ident['project_id']}",
                      result.stdout)
        self.assertIn("Attributed", result.stdout)
        # READ-ONLY, asserted byte-for-byte: this command must never be a way to
        # mutate an identity that is FROZEN by design.
        self.assertEqual((self.repo / ".agents" / "state" / "project.json").read_bytes(),
                         before)

    def test_print_otel_env_refuses_without_an_identity(self):
        """No id to print, and inventing one would create a SECOND identity for
        the repo — the one thing `project_id` exists to make impossible."""
        result = _run_init(self.repo, "--print-otel-env", env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("project_init.py", result.stderr)
        self.assertNotIn("OTEL_RESOURCE_ATTRIBUTES", result.stdout)
        self.assertFalse((self.repo / ".agents" / "state" / "project.json").exists(),
                         "a refusal must not create the file it was missing")

    def test_print_otel_env_json_is_pure_and_carries_the_real_id(self):
        """T-00000061 — the PRIMARY target reads JSON, not shell.

        The pilot bumped into exactly this: `--print-otel-env` printed a
        `KEY=value` line, usable for direnv or a profile, while Claude Code
        expects an `env` object inside `.claude/settings.local.json`. A shell
        line pasted into a JSON file is not a near miss, it is a file that no
        longer parses.

        `--format=json` must therefore be PURE: `json.loads` on the whole stdout,
        with no comment line to strip first. Asserting on a substring would let a
        commented-out heading survive and the arm would measure nothing.
        """
        _run_init(self.repo, "--name", "Attributed", env=self.env)
        ident = self._identity()
        result = _run_init(self.repo, "--print-otel-env", "--format=json", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["env"]["OTEL_RESOURCE_ATTRIBUTES"],
            f"agentkit.project_id={ident['project_id']}",
        )
        # NOT a shell line anywhere: the two forms must not bleed into each other.
        self.assertNotIn("OTEL_RESOURCE_ATTRIBUTES=agentkit", result.stdout)

    def test_print_otel_env_json_is_the_identity_key_alone_even_with_settings(self):
        """T-01M4WNKCBXS893CHPSKD1Z1PN9 — the json form carries ONE key.

        Claude Code 2.1.299 refuses the five activation keys in project AND
        local scope (`… is ignored — project-scoped settings can't set this
        key`, measured), and merges the `env` of the scopes key by key
        (measured): relaying `settings.json`'s `env` into `settings.local.json`
        would paste keys the host drops. The fixture carries the six keys the
        kit used to ship plus a third-party key: NONE may come out — the whole
        object is compared, so a relay reintroduced goes red here."""
        _run_init(self.repo, "--name", "Attributed", env=self.env)
        ident = self._identity()
        settings = self.repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"env": {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp", "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "OTEL_METRIC_EXPORT_INTERVAL": "5000", "A_THIRD_PARTY_KEY": "dropped"}}),
            encoding="utf-8")
        result = _run_init(self.repo, "--print-otel-env", "--format=json", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"env": {
            "OTEL_RESOURCE_ATTRIBUTES": f"agentkit.project_id={ident['project_id']}"}})

    def test_print_otel_env_json_without_settings_is_the_same_single_key(self):
        """No `settings.json` — a fresh consumer clone — yields the SAME one-key
        object: the activation keys live in user scope, never in this output."""
        _run_init(self.repo, "--name", "Attributed", env=self.env)
        ident = self._identity()
        result = _run_init(self.repo, "--print-otel-env", "--format=json", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"env": {
            "OTEL_RESOURCE_ATTRIBUTES": f"agentkit.project_id={ident['project_id']}"}})

    def test_print_otel_env_default_both_keeps_the_shell_block_first(self):
        """NON-REGRESSION, and it is why `both` is the default rather than
        `json`: every existing consumer of this output — the two arms above this
        one included — reads the shell line. It stays FIRST and unchanged; the
        JSON is appended, never substituted."""
        _run_init(self.repo, "--name", "Attributed", env=self.env)
        ident = self._identity()
        result = _run_init(self.repo, "--print-otel-env", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        shell_line = f"OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id={ident['project_id']}"
        self.assertIn(shell_line, result.stdout)
        self.assertLess(result.stdout.index(shell_line), result.stdout.index('"env"'))

    def test_print_otel_env_json_emits_nothing_at_all_when_it_refuses(self):
        """THE PINNED VOID, EXTENDED RATHER THAN WEAKENED. The refusal arm above
        asserts a stdout with no `OTEL_RESOURCE_ATTRIBUTES`; adding a second form
        is exactly the kind of change that quietly re-fills a void a test was
        holding open. A JSON `env` carrying a placeholder id is the silent
        mis-attribution this command exists to prevent, so `--format=json` emits
        NOTHING on the refusal path either."""
        result = _run_init(self.repo, "--print-otel-env", "--format=json", env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")

    # -- git identity gate -------------------------------------------------

    def test_refuses_when_git_user_name_empty(self):
        # A fresh repo with an isolated, EMPTY git config: user.name is unset.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            repo = Path(raw)
            env = _isolated_git_env()
            _git(repo, "init")
            result = _run_init(repo, "--name", "X", env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("user.name", result.stderr)
            self.assertFalse((repo / ".agents" / "state" / "project.json").exists())
            # NOR ANY STORE. Provisioning sits at the END of a SUCCESSFUL init,
            # after the atomic create — a refusal path must leave the repo
            # exactly as it found it. A refusal that dropped a board behind it
            # would make the NEXT run's diagnosis wrong: the operator would see
            # a half-initialised project and no longer know which half failed.
            self.assertFalse((repo / ".agents" / "state" / "board" / "TASKS.json").exists(),
                             "un refus ne doit provisionner aucun magasin")

    # -- collision (distinct diagnostics, C2) ------------------------------

    def test_refuses_to_overwrite_valid_identity(self):
        _run_init(self.repo, "--name", "First", env=self.env)
        result = _run_init(self.repo, "--name", "Second", env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("déjà initialisée", result.stderr)
        self.assertIn("project_id=", result.stderr)
        # Original identity untouched.
        self.assertEqual(self._identity()["name"], "First")

    def test_stderr_survives_hostile_parent_ioencoding(self):
        """C1 — the pin proven on BOTH sides, from a HOSTILE parent shell that
        exports PYTHONIOENCODING=cp1252. It reuses the accented collision
        message (« déjà initialisée », l.230) as the payload:
          * revert the CHILD-side pin -> the child inherits cp1252 and emits
            cp1252 bytes; the strict UTF-8 decode of 'é'/'à' raises
            UnicodeDecodeError and this test ERRORS -> the revert is caught.
          * revert the PARENT-side pin on a cp1252-locale host (Windows) ->
            the message arrives mojibake and the assertIn below fails.
        Honesty on scope: on a UTF-8-locale host (macOS/Linux CI) the
        parent-side revert is masked (locale already decodes UTF-8); it is the
        child-side pin that this arm guards robustly everywhere, and the
        parent-side pin that protects the cp1252 host the child-side cannot."""
        hostile = dict(self.env)
        hostile["PYTHONIOENCODING"] = "cp1252"
        _run_init(self.repo, "--name", "First", env=hostile)
        result = _run_init(self.repo, "--name", "Second", env=hostile)
        # The caller's dict must not have been mutated by _run_init's copy.
        self.assertEqual(hostile["PYTHONIOENCODING"], "cp1252")
        self.assertEqual(result.returncode, 2)
        self.assertIn("déjà initialisée", result.stderr)

    def test_corrupt_file_gets_distinct_message(self):
        path = self.repo / ".agents" / "state" / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json", encoding="utf-8")
        result = _run_init(self.repo, "--name", "X", env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("corrompu", result.stderr)
        self.assertNotIn("déjà initialisée", result.stderr)

    # -- rename keeps frozen fields ----------------------------------------

    def test_rename_changes_name_only_frozen_fields_stable(self):
        _run_init(self.repo, "--name", "Original Name", env=self.env)
        before = self._identity()
        result = _run_init(self.repo, "--rename", "Renamed Thing", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self._identity()
        self.assertEqual(after["name"], "Renamed Thing")
        # slug FROZEN across a rename (C4), plus id/created; key set stable.
        self.assertEqual(after["slug"], before["slug"])
        self.assertEqual(after["project_id"], before["project_id"])
        self.assertEqual(after["created"], before["created"])
        self.assertEqual(set(after), set(before))
        self.assertEqual(set(after), {"project_id", "name", "slug", "created"})

    def test_rename_preserves_legacy_retired_key(self):
        # A project.json written before T-00000594 keeps its retired key,
        # inert: no migration strips it, --rename copies it, nothing reads it.
        p = self.repo / ".agents" / "state" / "project.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"project_id": "legacy", "name": "Old", "slug": "old",
                                 "created": "2026-07-29T00:00:00Z", "kit_version": "unknown"}),
                     encoding="utf-8")
        result = _run_init(self.repo, "--rename", "New", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self._identity()
        self.assertEqual((after["name"], after["slug"], after["kit_version"]), ("New", "old", "unknown"))

    def test_stamp_kit_version_flag_is_refused(self):
        # Tombstone (T-00000734): refused with the cause and the remedy, with
        # or without a value, and nothing is written.
        for args in (("--stamp-kit-version", "v9"), ("--name", "Foo", "--stamp-kit-version"),
                     ("--stamp-kit-version", "v9", "--bogus")):
            with self.subTest(args=args):
                result = _run_init(self.repo, *args, env=self.env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("RETIRÉ (T-00000594)", result.stderr)
                self.assertIn(".agents/kit.lock (clé version_kit", result.stderr)
                self.assertNotIn("unrecognized arguments", result.stderr)
                self.assertFalse((self.repo / ".agents" / "state" / "project.json").exists())

    def test_stamp_tombstone_precedes_every_side_effect_branch(self):
        p = self.repo / ".agents" / "state" / "project.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        before = json.dumps({"project_id": "x", "name": "Old", "slug": "old",
                             "created": "2026-07-29T00:00:00Z"})
        p.write_text(before, encoding="utf-8")
        for args in (("--rename", "New", "--stamp-kit-version", "v9"),
                     ("--ensure-stores", "--stamp-kit-version"),
                     ("--print-otel-env", "--stamp-kit-version")):
            with self.subTest(args=args):
                result = _run_init(self.repo, *args, env=self.env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("RETIRÉ (T-00000594)", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(p.read_text(encoding="utf-8"), before)
                self.assertFalse(self._board().exists())

    def test_help_does_not_advertise_the_removed_flag(self):
        result = _run_init(self.repo, "--help", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("stamp-kit-version", result.stdout)

    # -- exactly-one-winner across concurrent processes --------------------

    def test_exactly_one_winner_across_concurrent_inits(self):
        """N inits launched back-to-back on a virgin repo: O_EXCL must let
        exactly one succeed, the rest refuse with exit 2. Same pattern as
        LockRaceTests.test_exactly_one_winner_across_concurrent_processes
        (.agents/evals/test_gate_b_launch_probe.py)."""
        n = 10
        procs = [
            subprocess.Popen(
                # Only return codes are asserted here (pipes unread) -> decode
                # explicitly with errors="replace" for uniformity, no crash risk.
                [sys.executable, str(SCRIPT), "--name", f"racer-{i}"],
                cwd=str(self.repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=self.env,
            )
            for i in range(n)
        ]
        codes = [p.wait(timeout=30) for p in procs]
        self.assertEqual(codes.count(0), 1, f"expected exactly one winner, got {codes}")
        self.assertEqual(codes.count(2), n - 1)
        # Exactly one identity on disk, and it is well-formed.
        ident = self._identity()
        self.assertTrue(ident["project_id"])

    # -- mid-write crash leaves NO file, re-init succeeds ------------------

    def test_midwrite_crash_leaves_no_file_then_reinit_succeeds(self):
        """A BaseException during the write must unlink the partial file, so a
        later init on the same repo is a clean create, not a false collision."""
        sys.path.insert(0, str(HERE))
        import project_init as pi  # in-process to inject a failing write

        path = pi.project_json_path(self.repo)

        # Force a BaseException AFTER O_EXCL has created the (empty) file, by
        # making fsync blow up — exercises the unlink-partial-then-reraise guard.
        real_fsync = os.fsync

        def boom_fsync(fd):
            raise KeyboardInterrupt("simulated crash at fsync")

        os.fsync = boom_fsync
        try:
            data = {
                "project_id": "x", "name": "n", "slug": "n",
                "created": "2026-01-01T00:00:00Z",
            }
            with self.assertRaises(KeyboardInterrupt):
                pi._atomic_create(path, data)
        finally:
            os.fsync = real_fsync
        # Partial unlinked -> re-init is a clean create.
        self.assertFalse(path.exists())
        result = _run_init(self.repo, "--name", "After Crash", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._identity()["name"], "After Crash")


if __name__ == "__main__":
    unittest.main()
