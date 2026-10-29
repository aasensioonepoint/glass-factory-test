"""Four-host parity for the shared protected-paths extension (T-00000031).

THE DECISION THIS ENFORCES. `.agents/bin/` must stay writable IN THE KIT — the
kit maintains itself, every tool in that directory was written by an agent
working in this repo, and protecting it here would mean no agent could ever
update its own guardrails. In a CONSUMER project the same directory is
vendored code nobody should edit locally. So the protection is not hardcoded:
it is a project-level list, `.agents/protected-paths.local`, shipped with
content only on the template branch (`own:` in `.template-exclude`).

WHY A PARITY TEST AND NOT A UNIT TEST. A path guard honoured by one host and
ignored by the other three is worse than no guard: it reads as protection
while leaving three doors open — the exact failure the MCP path guards were
made four-host to avoid. Claude reads the file in sh, Codex and Gemini in
Python, Copilot by executing the Codex script (L-006). Four implementations,
one behaviour, asserted together.

Each case drives the REAL guard as its host invokes it (a subprocess fed the
host's own payload shape on stdin) and compares VERDICTS, not mechanisms: the
hosts genuinely disagree on how a denial is signalled — Claude Code exits 2,
the three others emit a `permissionDecision` object on stdout and exit 0 — so
each protocol is normalised to `deny`/`allow` before comparison. The first
version of this eval asserted a shared exit code and "found" three broken
guards that were working correctly; a parity test must know what parity means.

Fixtures are disposable trees; the repo's own guards are read, never modified,
and no test writes `.agents/protected-paths.local` into this repository — where
its presence would immediately block this session's own work.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")

# The protected prefix a consumer project is expected to carry, and a path
# under it. Also the point of the whole task.
CONSUMER_RULE = ".agents/bin/"
TARGET_UNDER_RULE = ".agents/bin/tasks.py"
TARGET_OUTSIDE = "src/app/main.py"


def _fixture_tree(tmp: Path, *, with_extension: bool, rule: str = CONSUMER_RULE) -> Path:
    """A throw-away project carrying copies of the four hosts' guards."""
    root = tmp / "project"
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / ".codex" / "hooks").mkdir(parents=True)
    (root / ".gemini" / "hooks").mkdir(parents=True)
    (root / ".agents").mkdir(parents=True)

    shutil.copy(ROOT / ".claude" / "hooks" / "protect-paths.sh",
                root / ".claude" / "hooks" / "protect-paths.sh")
    # emit-event.sh is invoked by the sh guard on a denial; a missing bridge
    # must not change the verdict, but copy it so the test exercises the real
    # path rather than an accidental degraded one.
    shutil.copy(ROOT / ".claude" / "hooks" / "emit-event.sh",
                root / ".claude" / "hooks" / "emit-event.sh")
    for host in (".codex", ".gemini"):
        for name in ("protect_paths.py", "_common.py"):
            shutil.copy(ROOT / host / "hooks" / name, root / host / "hooks" / name)

    if with_extension:
        (root / ".agents" / "protected-paths.local").write_text(
            "# consumer projects protect vendored kit code\n"
            f"{rule}\n"
            "\n",
            encoding="utf-8", newline="\n",
        )
    return root


DENY, ALLOW = "deny", "allow"


def _run_claude(root: Path, target: str) -> str:
    """Claude Code's protocol: exit 2 blocks, exit 0 allows."""
    payload = json.dumps({"tool_input": {"file_path": target}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root),
           "AGENTS_EVENTS_DIR": str(root / ".events")}
    proc = subprocess.run([BASH, str(root / ".claude" / "hooks" / "protect-paths.sh")],
                          input=payload, capture_output=True, text=True, env=env)
    if proc.returncode == 2:
        return DENY
    assert proc.returncode == 0, f"claude guard crashed: rc={proc.returncode} err={proc.stderr!r}"
    return ALLOW


def _run_python_host(root: Path, host: str, target: str, host_label: str | None = None) -> str:
    """Codex/Copilot/Gemini protocol: a JSON object on stdout carrying
    `permissionDecision`, exit code 0 either way — NOT exit 2. The hosts
    genuinely differ here, so this eval normalises each one's own protocol to a
    verdict and compares VERDICTS. Asserting a shared exit code instead would
    have been a test measuring its own assumption (it did, on first run).

    Codex and Gemini each run their own `<host>/hooks/protect_paths.py`;
    Copilot executes the Codex one (L-006), hence host vs host_label."""
    payload = json.dumps({"tool_input": {"file_path": target}})
    env = {**os.environ, "AGENTS_EVENTS_DIR": str(root / ".events")}
    if host_label:
        env["AGENTS_HOOK_HOST"] = host_label
    proc = subprocess.run([sys.executable, str(root / host / "hooks" / "protect_paths.py")],
                          input=payload, capture_output=True, text=True, env=env,
                          cwd=str(root))
    assert proc.returncode == 0, (
        f"{host_label or host} guard exited {proc.returncode} — these hosts signal a denial "
        f"in stdout, never with a non-zero code. stderr={proc.stderr!r}"
    )
    out = proc.stdout.strip()
    if not out:
        return ALLOW
    try:
        body = json.loads(out)
        nested = body["hookSpecificOutput"]
        decision = nested["permissionDecision"]
    except (ValueError, KeyError, TypeError) as exc:  # malformed = not a decision we can trust
        raise AssertionError(f"{host_label or host} emitted unreadable output {out!r} ({exc})")
    if host_label == "copilot":
        # T-01M4RWC0DBM6XC1PDQGEG4P79C : la CLI Copilot honore le
        # `permissionDecision` de PREMIER NIVEAU ; c'est lui le verdict de cette
        # jambe, et il doit egaler l'imbrique (raison comprise), qui reste en place.
        top = (body.get("permissionDecision"), body.get("permissionDecisionReason"))
        if top != (decision, nested.get("permissionDecisionReason")):
            raise AssertionError(
                f"copilot: top-level {top!r} != nested "
                f"{(decision, nested.get('permissionDecisionReason'))!r} in {out!r}"
            )
        decision = top[0]
    elif set(body) != {"hookSpecificOutput"}:
        raise AssertionError(
            f"{host_label or host}: only copilot carries a second form, got keys {sorted(body)!r}"
        )
    return DENY if decision == "deny" else ALLOW


HOSTS = (
    ("claude", lambda root, target: _run_claude(root, target)),
    ("codex", lambda root, target: _run_python_host(root, ".codex", target, "codex")),
    ("copilot", lambda root, target: _run_python_host(root, ".codex", target, "copilot")),
    ("gemini", lambda root, target: _run_python_host(root, ".gemini", target, "gemini")),
)


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude guard")
class SharedExtensionParityTests(unittest.TestCase):
    def setUp(self):
        # Windows flake: git/AV handles can outlive the test (ledger L-00000035).
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_four_hosts_block_a_path_listed_in_the_shared_file(self):
        root = _fixture_tree(self.tmp, with_extension=True)
        for name, run in HOSTS:
            with self.subTest(host=name):
                self.assertEqual(
                    run(root, TARGET_UNDER_RULE), DENY,
                    f"{name} ignored .agents/protected-paths.local — a guard honoured by "
                    "some hosts and not others reads as protection while leaving doors open",
                )

    def test_all_four_hosts_allow_the_same_path_without_the_file(self):
        """The control that makes the case above meaningful: the block must come
        from the extension file, not from something already hardcoded."""
        root = _fixture_tree(self.tmp, with_extension=False)
        for name, run in HOSTS:
            with self.subTest(host=name):
                self.assertEqual(
                    run(root, TARGET_UNDER_RULE), ALLOW,
                    f"{name} blocks {TARGET_UNDER_RULE} with no extension file — then this "
                    "suite proves nothing about the extension mechanism",
                )

    def test_an_unrelated_path_stays_allowed_on_all_four_hosts(self):
        root = _fixture_tree(self.tmp, with_extension=True)
        for name, run in HOSTS:
            with self.subTest(host=name):
                self.assertEqual(run(root, TARGET_OUTSIDE), ALLOW,
                                 f"{name} over-blocked an unrelated path")

    def test_comments_and_blank_lines_are_not_treated_as_patterns(self):
        """A comment must not become a pattern. On the sh side an unstripped
        `#` would word-split into several bogus patterns — one of which
        ('consumer', 'code'…) would then match half the tree."""
        root = _fixture_tree(self.tmp, with_extension=True)
        for name, run in HOSTS:
            with self.subTest(host=name):
                self.assertEqual(run(root, "docs/consumer/code.md"), ALLOW,
                                 f"{name} matched a word from a comment line")

    def test_a_malformed_or_unreadable_file_never_fails_open_nor_crashes(self):
        """A guard must not crash on a broken optional file — and must not stop
        enforcing its BUILT-IN rules because the extension file is unusable."""
        root = _fixture_tree(self.tmp, with_extension=False)
        target = root / ".agents" / "protected-paths.local"
        target.write_bytes(b"\xff\xfe\x00 not utf-8 \x00")
        for name, run in HOSTS:
            with self.subTest(host=name):
                # built-in rule still enforced
                self.assertEqual(run(root, "src/legacy/old.py"), DENY,
                                 f"{name} stopped enforcing built-ins over a broken extension file")
                # and no crash-shaped exit code
                self.assertIn(run(root, TARGET_OUTSIDE), (ALLOW, DENY),
                              f"{name} crashed on a malformed extension file")


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude guard")
class EnvTemplateParityTests(unittest.TestCase):
    """Four-host parity for the `.env` TEMPLATE exception.

    THE DECISION THIS ENFORCES. `.env*` was blocked without distinction, but a
    `.env.example` / `.env.sample` / `.env.template` / `.env.dist` is a TEMPLATE:
    it carries the NAMES of the variables and never their values, and it is
    precisely the file an agent must update when it adds a configuration
    variable. So the four recognized suffixes are editable and everything else
    under `.env*` stays blocked.

    WHY IT IS ASSERTED HERE, WITH THE EXTENSION MECHANISM. Same reason and same
    shape: an exception honoured by one host and ignored by the other three is a
    guard that reads as protection while behaving differently per host — and this
    one is worse than the extension case, because the DIVERGENCE IS SILENT IN
    BOTH DIRECTIONS (one host refusing a legitimate template edit, another
    allowing a real `.env`). The exception was rapatriated from a consumer
    project that shipped it on its three guards with no test at all; these are
    the arms it never had.

    Recognition is BY SUFFIX, never by intent, hence the negative arms: they are
    the half that makes this class non-vacuous. A template is recognized
    WHATEVER ITS CASE, on the four hosts (pilot decision
    S-01M5X79JTGRSSTB872R4YBPVMF, which replaces S-01M5SZJE11): Claude folds
    both the candidate and the compared `.env` rule, the Python twins judge the
    folded forms — so `.env.EXAMPLE` is a template everywhere, and `.ENV`,
    `.env.LOCAL` or `.env.EXAMPLE.` stay refused everywhere.
    """

    TEMPLATES = (".env.example", ".env.sample", ".env.template", ".env.dist",
                 "apps/web/.env.example", ".env.EXAMPLE", "app/.env.Example",
                 ".env.TEMPLATE", ".env.Sample")
    REAL_ENV = (".env", ".env.local", ".env.production", ".env.example.bak",
                ".env.LOCAL", ".ENV.Production", ".env.Example.bak", ".ENV",
                ".env.EXAMPLE.")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        # No extension file: this exception belongs to the guards' BUILT-IN rules,
        # so it must hold on a project that carries no local list at all.
        self.root = _fixture_tree(self.tmp, with_extension=False)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_four_hosts_allow_a_recognized_env_template(self):
        for target in self.TEMPLATES:
            for name, run in HOSTS:
                with self.subTest(host=name, path=target):
                    self.assertEqual(
                        run(self.root, target), ALLOW,
                        f"{name} blocks {target} — a template carries variable names and no "
                        "values, and is the one .env file an agent is meant to author",
                    )

    def test_all_four_hosts_still_block_a_real_env_file(self):
        """The arm that makes the one above safe rather than merely convenient."""
        for target in self.REAL_ENV:
            for name, run in HOSTS:
                with self.subTest(host=name, path=target):
                    self.assertEqual(
                        run(self.root, target), DENY,
                        f"{name} allows {target} — the exception is scoped to four recognized "
                        "SUFFIXES; anything else under .env* may carry live credentials",
                    )

    def test_the_extension_file_does_not_re_block_templates(self):
        """A consumer listing `.env` in its own local list must not resurrect the
        block: the exception is scoped to the `.env` RULE, whichever list carries
        it. Without this arm a project could silently lose the exception by
        writing down the rule it already had — in any case (`.ENV` too)."""
        cases = ((".env", ".env.example", ".env.local"),
                 (".ENV", ".ENV.EXAMPLE", ".ENV.LOCAL"))
        for rule, template, real in cases:
            # Its own tmp root: setUp already built a tree under self.tmp, and
            # _fixture_tree always names it "project".
            other = self.tmp / f"with-local-list-{'lc' if rule.islower() else 'uc'}"
            other.mkdir()
            root = _fixture_tree(other, with_extension=True, rule=rule)
            for name, run in HOSTS:
                with self.subTest(host=name, rule=rule):
                    self.assertEqual(run(root, template), ALLOW,
                                     f"{name} re-blocked {template} via the extension rule {rule}")
                    self.assertEqual(run(root, real), DENY,
                                     f"{name} stopped blocking {real} under the extension rule {rule}")


class KitSelfMaintenanceTests(unittest.TestCase):
    """The other half of the decision: `main` must NOT carry the file, or the
    kit could no longer maintain its own tooling."""

    def test_main_does_not_carry_the_protected_paths_file(self):
        """Asserted against the COMMITTED tree (`HEAD`), never the working tree.

        The distinction is the whole point of the design: the file MUST exist on
        the template branch — a consumer project starts with `.agents/bin/`
        protected — and must NOT be tracked by the kit's own line of work (the
        "main" of the name), where that directory is how the kit maintains
        itself. An earlier version checked the working tree, which would have
        failed on the template, greeting every consumer who runs this suite with
        a red test that is actually correct behaviour. The file stays on disk
        here, untracked (`.agents/.gitignore`): the guards read it from disk.

        WHY `HEAD` AND NOT THE `main` REF (T-00000803). A ref is not frozen by
        `verify.sh --at`: the push that a green gate authorises moved `main` and
        turned this test red with no byte of the tree changed (L-00000369). And
        `main:.agents/ui-src`, the former discriminator, was absent from CI (no
        local `main`) and from this repo's `main` (a separate history): the
        test skipped everywhere. `HEAD` is the sha under test, in CI and under
        `--at` alike.

        The discriminator is the kit marker `.agents/IS_THE_KIT` (`strip:`):
        a template clone and a template-derived DISTRIBUTION both lack it, and
        both legitimately carry the file (measured on op-agentic-builder-kit,
        2026-08-02 — a `main`-only guard greeted that distribution red).
        `rc == 0` is required: without git, an empty listing would pass vacuously."""
        # adopting-tree: the kit marker never travels; its absence IS a template clone or distribution
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("no .agents/IS_THE_KIT — a template clone or a distribution, "
                          "where the file belongs")
        on_head = subprocess.run(
            ["git", "-C", str(ROOT), "ls-tree", "--name-only", "HEAD", "--",
             ".agents/protected-paths.local"],
            capture_output=True, text=True)
        self.assertEqual(0, on_head.returncode, on_head.stderr)
        self.assertEqual(
            "", on_head.stdout.strip(),
            "HEAD tracks protected-paths.local: .agents/bin/ would be write-protected in the "
            "kit's own repo, where that directory is how the kit maintains itself. The content "
            "ships from the template branch (`own:` in .template-exclude), never from here.",
        )

    def test_the_template_rule_is_declared(self):
        text = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        self.assertIn("own: .agents/protected-paths.local", text,
                      "the sync rule that keeps this file template-only is missing")


if __name__ == "__main__":
    unittest.main()
