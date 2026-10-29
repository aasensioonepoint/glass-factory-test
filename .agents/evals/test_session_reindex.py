"""T-013: reader-side deterministic index freshness at the SessionStart entry
point (the pipeline-entry rebuild is covered by `.codex/test_pipeline_contract.py`).

No new hook registration and no SubagentStop: this asserts the three hosts'
SessionStart hooks each carry a guarded, best-effort call to
`build_index.py --if-stale` BEFORE the index is read/injected, and that the
guard (SYMBOLS.md must already exist) is present so an unindexed repo never
gets its first full scan here — that stays an explicit `/index` decision.

The two halves are deliberately asymmetric:

  * the PYTHON hosts (codex, gemini) name the builder in code and stay pinned
    textually, builder path included;
  * the BASH host is proven STRUCTURALLY by `prove_guarded_if_stale_refresh()`
    below, because a consumer project legitimately names the builder by a
    VARIABLE resolved to a project wrapper that carries the index PERIMETER
    (calling the bare kit builder there would regenerate a wider index). Such a
    hook is right, and pinning the literal `"$BIN/build_index.py"` reddened it.
    So: the builder may be a kit literal or a variable — provided that variable
    still DEFAULTS to the kit builder before any wrapper override, the
    `[ -f "…index/SYMBOLS.md" ]` test stays literal, the two `-f` tests pair in
    either order, the guarded token is the one actually invoked, and the call
    stays inside the guarded block. Strengthening conditions are allowed;
    weakening is not.

That structural logic is a pure function of the hook TEXT, applied both to the
repo's real hook and to the fixtures at the foot of this file, so its
non-vacuity is re-established at every run rather than by a one-off mutation
check (L-00000129).

Style aligned with `.agents/evals/test_ledger_parity.py` (module-level helpers,
ROOT-relative paths, text-level assertions rather than executing the python
hooks, since the guard/timeout/try-except shape is what matters here, not the
runtime output).
"""
from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SESSION_START_SH = ROOT / ".claude" / "hooks" / "session-start.sh"
CODEX_SESSION_CONTEXT = ROOT / ".codex" / "hooks" / "session_context.py"
GEMINI_SESSION_CONTEXT = ROOT / ".gemini" / "hooks" / "session_context.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_function(source: str, name: str) -> str:
    """The body of a top-level `def name():` up to the next top-level `def`."""
    match = re.search(rf"^def {re.escape(name)}\(.*?\):\n", source, re.M)
    assert match, f"{name} not found"
    start = match.end()
    next_def = re.search(r"^def \w+\(", source[start:], re.M)
    end = start + next_def.start() if next_def else len(source)
    return source[start:end]


# --------------------------------------------------------------------------
# The bash guard, as a pure function of the hook's TEXT.
#
# One implementation, two callers: the repo's real session-start.sh (below) and
# the hand-written fixtures at the bottom of this file. The fixtures are what
# make the real-file assertion non-vacuous at EVERY run rather than at the one
# run where someone mutated the hook by hand (L-00000129).
# --------------------------------------------------------------------------


class GuardViolation(AssertionError):
    """The hook's guarded `build_index.py --if-stale` refresh cannot be proven."""


@dataclass(frozen=True)
class CodeLine:
    """One logical shell line: comments and heredoc bodies gone, continuations folded."""

    lineno: int
    text: str


@dataclass(frozen=True)
class GuardVerdict:
    """What the proof located, so callers can assert on the resolved builder."""

    guard_lineno: int
    call_lineno: int
    fi_lineno: int
    guarded_token: str
    kit_default: str


# `<< 'PYEOF'` / `<<EOF`, but never a `<<<` herestring.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|([A-Za-z_]\w*))\s*$")
_GUARD_IF = re.compile(r"^\s*if\s+(?P<cond>.*?);\s*then\b")
_F_TEST = re.compile(r"\[\s+-f\s+(?P<operand>[^\]]+?)\s+\]")
_SYMBOLS_OPERAND = re.compile(r"index/SYMBOLS\.md$")
_BARE_VAR = re.compile(r"^\$(\w+)$")
_BUILDER_PATH = re.compile(r"^\$\w+/build_index\.py$")


def normalize_shell_token(token: str) -> str:
    """`"${IDX_BUILDER}"` and `'$IDX_BUILDER'` both normalise to `$IDX_BUILDER`."""
    stripped = token.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        stripped = stripped[1:-1]
    return re.sub(r"\$\{(\w+)\}", r"$\1", stripped)


def normalize_shell_line(line: str) -> str:
    """Same normalisation, applied to a whole command line (quotes dropped)."""
    return re.sub(r"\$\{(\w+)\}", r"$\1", line.replace('"', "").replace("'", ""))


def fold_continuations(lines: list[CodeLine]) -> list[CodeLine]:
    """Join `\\`-continued physical lines, keeping the FIRST one's line number."""
    folded: list[CodeLine] = []
    pending = None
    for line in lines:
        text = (pending.text + " " + line.text.strip()) if pending else line.text
        lineno = pending.lineno if pending else line.lineno
        if text.rstrip().endswith("\\"):
            pending = CodeLine(lineno, text.rstrip()[:-1].rstrip())
            continue
        folded.append(CodeLine(lineno, text))
        pending = None
    if pending is not None:
        folded.append(pending)
    return folded


def shell_code_lines(hook_text: str) -> list[CodeLine]:
    """Executable logical lines only: comment lines and heredoc BODIES removed.

    The heredoc removal is not cosmetic. session-start.sh embeds a python
    heredoc whose body carries several `if …:` and no `fi`; counting `if`/`fi`
    over the raw text would desynchronise and make any confinement claim true
    by accident. An unterminated heredoc is reported loudly instead.
    """
    raw_lines = hook_text.splitlines()
    kept: list[CodeLine] = []
    i = 0
    while i < len(raw_lines):
        raw = raw_lines[i]
        if raw.lstrip().startswith("#"):
            i += 1
            continue
        kept.append(CodeLine(i + 1, raw))
        opener = _HEREDOC.search(raw)
        if opener is None:
            i += 1
            continue
        delimiter = next(group for group in opener.groups() if group)
        end = i + 1
        while end < len(raw_lines) and raw_lines[end].strip() != delimiter:
            end += 1
        if end >= len(raw_lines):
            raise GuardViolation(
                f"unterminated heredoc <<{delimiter} opened at line {i + 1}: the hook "
                "cannot be delimited, so no claim may be made about its guard"
            )
        i = end + 1
    return fold_continuations(kept)


def prove_guarded_if_stale_refresh(hook_text: str) -> GuardVerdict:
    """Prove the bash hook's `--if-stale` refresh is properly guarded, or raise.

    What is required, and nothing more:
      * exactly ONE `--if-stale` call in executable code (a prose mention in a
        comment is not a call, and an ambiguous count is a loud failure, never
        a silent pass);
      * that call sits INSIDE an `if … ; then … fi` block;
      * the block's condition carries the literal `[ -f "…index/SYMBOLS.md" ]`
        test — non-negotiable: it is what keeps an unindexed repo from getting
        its first full scan here;
      * and a `-f` test on the very builder the call runs, named either by the
        kit literal (`$BIN/build_index.py`) or by a shell VARIABLE that
        defaults to it.
    Order of the two `-f` tests is irrelevant (`&&` commutes here) and extra
    strengthening conditions (`command -v timeout …`) are welcome; weakening is
    what this refuses.
    """
    code = shell_code_lines(hook_text)

    calls = [line for line in code if "--if-stale" in line.text]
    if len(calls) != 1:
        raise GuardViolation(
            "expected exactly ONE --if-stale call among the hook's executable lines "
            f"(comments and heredoc bodies excluded), found {len(calls)} at lines "
            f"{[line.lineno for line in calls]} — the confinement proof has no unique anchor"
        )
    call = calls[0]

    guards = []
    for index, line in enumerate(code):
        matched = _GUARD_IF.match(line.text)
        if matched is None:
            continue
        operands = [normalize_shell_token(o) for o in _F_TEST.findall(matched.group("cond"))]
        if any(_SYMBOLS_OPERAND.search(o) for o in operands):
            guards.append((index, line, operands))
    if len(guards) != 1:
        raise GuardViolation(
            'the --if-stale call must be gated by exactly one `if` testing [ -f "…index/'
            f'SYMBOLS.md" ]; found {len(guards)} such guard(s). Without it an unindexed '
            "repo gets its first full scan at SessionStart, which stays an explicit "
            "/index decision"
        )
    guard_index, guard, operands = guards[0]

    depth = 1
    closing = None
    for line in code[guard_index + 1:]:
        text = line.text.strip()
        if re.match(r"^if\b", text):
            depth += 1
        elif re.match(r"^fi\b", text):
            depth -= 1
            if depth == 0:
                closing = line
                break
    if closing is None:
        raise GuardViolation(
            f"the guard opened at line {guard.lineno} is never closed by `fi` — "
            "the guarded region cannot be delimited"
        )
    if not guard.lineno < call.lineno < closing.lineno:
        raise GuardViolation(
            f"the --if-stale call (line {call.lineno}) must sit INSIDE the guarded block "
            f"(lines {guard.lineno}..{closing.lineno}); outside it, the guard proves nothing"
        )

    call_line = normalize_shell_line(call.text)
    guarded = [
        operand
        for operand in operands
        if not _SYMBOLS_OPERAND.search(operand)
        and re.search(re.escape(operand) + r"(?!\w)", call_line)
    ]
    if len(guarded) != 1:
        raise GuardViolation(
            "the file gated by [ -f … ] must be the very builder the call runs: guarded "
            f"{operands}, invoked `{call.text.strip()}` — matched {len(guarded)} token(s). "
            "Testing one path and running another measures nothing"
        )
    token = guarded[0]

    if _BUILDER_PATH.match(token):
        return GuardVerdict(guard.lineno, call.lineno, closing.lineno, token, token)

    variable = _BARE_VAR.match(token)
    if variable is None:
        raise GuardViolation(
            f"the guarded builder {token!r} is neither the kit literal "
            '"$BIN/build_index.py" nor a shell variable naming it'
        )
    name = variable.group(1)
    assignment = re.compile(r"(?:^|[\s;&|])" + re.escape(name) + r"=(?P<rhs>\S+)")
    assigned = [
        normalize_shell_token(found.group("rhs"))
        for line in code[:guard_index]
        for found in [assignment.search(line.text)]
        if found is not None
    ]
    if not assigned or not _BUILDER_PATH.match(assigned[0]):
        found = f"first assignment is {assigned[0]!r}" if assigned else "no assignment at all"
        raise GuardViolation(
            f"the guarded builder is named by ${name}, so ${name} must still DEFAULT to the "
            f'kit builder: an assignment `{name}="$BIN/build_index.py"` is required BEFORE '
            f"any project-wrapper override — {found}. Otherwise {name}=<anything> satisfies "
            "the guard and the assertion measures nothing"
        )
    return GuardVerdict(guard.lineno, call.lineno, closing.lineno, token, assigned[0])


class SessionReindexFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.session_start_sh = read(SESSION_START_SH)
        self.codex_hook = read(CODEX_SESSION_CONTEXT)
        self.gemini_hook = read(GEMINI_SESSION_CONTEXT)

    # (a) session-start.sh carries the --if-stale call, textually BEFORE the
    # CODEBASE_INDEX.md read.
    def test_session_start_sh_refreshes_before_reading_the_index(self):
        idx_call = self.session_start_sh.index("--if-stale")
        idx_read = self.session_start_sh.index("CODEBASE_INDEX.md")
        self.assertLess(
            idx_call, idx_read,
            "the --if-stale refresh must run before the CODEBASE_INDEX.md read",
        )
        self.assertIn("build_index.py", self.session_start_sh)
        # …and not merely in a comment: the builder the guarded call actually
        # runs resolves to build_index.py (kit literal, or a variable whose
        # kit default is it).
        verdict = prove_guarded_if_stale_refresh(self.session_start_sh)
        self.assertTrue(
            verdict.kit_default.endswith("/build_index.py"),
            f"the refreshed builder must be the kit's build_index.py, got {verdict.kit_default!r}",
        )

    # (b) both python session hooks: the call is inside a try/except, with
    # timeout=5, guarded by SYMBOLS.md existence.
    def test_python_session_hooks_guard_timeout_and_try_except(self):
        for name, source in (("codex", self.codex_hook), ("gemini", self.gemini_hook)):
            fn = extract_function(source, "refresh_index_if_stale")
            self.assertIn("SYMBOLS.md", fn, f"{name}: missing SYMBOLS.md existence guard")
            self.assertIn("try:", fn, f"{name}: refresh must be wrapped in try/except")
            self.assertIn("except Exception", fn, f"{name}: must swallow every failure")
            self.assertIn("timeout=5", fn, f"{name}: subprocess call must bound at 5s")
            self.assertIn("--if-stale", fn, f"{name}: must invoke build_index.py --if-stale")
            self.assertIn("build_index.py", fn, f"{name}: must call build_index.py")

    # (b, continued) the refresh must run before the index is read in main().
    def test_python_session_hooks_refresh_before_reading_the_index(self):
        for name, source in (("codex", self.codex_hook), ("gemini", self.gemini_hook)):
            main_fn = extract_function(source, "main")
            idx_call = main_fn.index("refresh_index_if_stale()")
            idx_read = main_fn.index("CODEBASE_INDEX.md")
            self.assertLess(
                idx_call, idx_read,
                f"{name}: refresh_index_if_stale() must run before the index read in main()",
            )

    # (c) codex and gemini call lines are semantically identical (parity).
    def test_codex_and_gemini_refresh_functions_are_identical(self):
        codex_fn = extract_function(self.codex_hook, "refresh_index_if_stale")
        gemini_fn = extract_function(self.gemini_hook, "refresh_index_if_stale")
        self.assertEqual(
            codex_fn, gemini_fn,
            "codex vs gemini refresh_index_if_stale() diverge — parity broken",
        )

    # (d) no session hook triggers the builder when SYMBOLS.md is absent —
    # assert the guard's presence textually (fixture projects in
    # test_ledger_parity.py have no SYMBOLS.md, so this guard is what makes
    # the refresh a no-op there).
    def test_no_session_hook_refreshes_without_the_symbols_guard(self):
        # session-start.sh: the refresh sits inside a single `if` whose condition
        # tests AT LEAST SYMBOLS.md existence (literal, non-negotiable) and the
        # builder it then runs. The builder may be named by the kit literal OR by
        # a variable that still defaults to it — a consumer project routes through
        # a wrapper carrying its index PERIMETER, and that hook is right, not
        # broken. Test order is irrelevant; strengthening conditions (e.g.
        # `command -v timeout`, added after the security review) are allowed;
        # weakening is not. The same function runs against the fixtures in
        # GuardShapeFixtureTests, so this call cannot pass vacuously.
        verdict = prove_guarded_if_stale_refresh(self.session_start_sh)
        self.assertTrue(
            verdict.kit_default.endswith("/build_index.py"),
            f"the guarded builder must default to the kit's: {verdict.kit_default!r}",
        )
        for name, source in (("codex", self.codex_hook), ("gemini", self.gemini_hook)):
            fn = extract_function(source, "refresh_index_if_stale")
            self.assertIn(
                'INDEX / "SYMBOLS.md").exists()', fn,
                f"{name}: the refresh must return early when SYMBOLS.md is absent",
            )


# --------------------------------------------------------------------------
# Fixtures: hook shapes written HERE, so the guard logic above is exercised
# against known-good AND known-bad text at every run. Without them the
# real-file assertion could quietly become unfalsifiable.
# --------------------------------------------------------------------------

FIXTURE_HEAD = r'''#!/usr/bin/env bash
# SessionStart fixture head, shared by every shape below.
BIN="$CLAUDE_PROJECT_DIR/.agents/bin"
STATE="$CLAUDE_PROJECT_DIR/.agents/state"
PY="python3"
CTX=""
'''

# The tail carries a python heredoc whose body holds unbalanced `if …:` lines:
# any home-made if/fi counting over the RAW text desynchronises here, which is
# exactly how a confinement assertion turns vacuously true.
FIXTURE_TAIL = r'''[ -f "$STATE/index/CODEBASE_INDEX.md" ] && CTX="$CTX$(cat "$STATE/index/CODEBASE_INDEX.md")"
[ -z "$CTX" ] && exit 0
"$PY" - "$CTX" << 'PYEOF'
import json, sys
if len(sys.argv) > 1:
    if sys.argv[1]:
        print(json.dumps({"ctx": sys.argv[1]}))
PYEOF
exit 0
'''

# (a) the kit's own shape: literal builder, condition over two lines.
FIXTURE_KIT_LITERAL = FIXTURE_HEAD + r'''if [ -f "$BIN/build_index.py" ] && [ -f "$STATE/index/SYMBOLS.md" ] \
   && command -v timeout >/dev/null 2>&1; then
  timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (b) a consumer project: kit default FIRST, conditional wrapper override, then
# the guard on the variable. The wrapper carries the index perimeter.
FIXTURE_CONSUMER_VARIABLE = FIXTURE_HEAD + r'''IDX_BUILDER="$BIN/build_index.py"
[ -f "$CLAUDE_PROJECT_DIR/scripts/build_code_index.py" ] && IDX_BUILDER="$CLAUDE_PROJECT_DIR/scripts/build_code_index.py"
if [ -f "$IDX_BUILDER" ] && [ -f "$STATE/index/SYMBOLS.md" ] \
   && command -v timeout >/dev/null 2>&1; then
  timeout 5 "$PY" "$IDX_BUILDER" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (c) same, braced in the guard and bare at the call: same variable.
FIXTURE_BRACED_VARIABLE = FIXTURE_HEAD + r'''IDX_BUILDER="${BIN}/build_index.py"
if [ -f "${IDX_BUILDER}" ] && [ -f "$STATE/index/SYMBOLS.md" ]; then
  timeout 5 "$PY" "$IDX_BUILDER" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (d) the two -f tests swapped: semantically identical.
FIXTURE_SWAPPED_TESTS = FIXTURE_HEAD + r'''if [ -f "$STATE/index/SYMBOLS.md" ] && [ -f "$BIN/build_index.py" ] \
   && command -v timeout >/dev/null 2>&1; then
  timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (e) prose mentioning --if-stale: a comment is not a second call site.
FIXTURE_PROSE_COMMENT = FIXTURE_HEAD + r'''# Best-effort: the --if-stale refresh below is skipped when timeout(1) is absent,
# and --if-stale never rebuilds an unindexed repo from scratch.
if [ -f "$BIN/build_index.py" ] && [ -f "$STATE/index/SYMBOLS.md" ]; then
  timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (f) the SYMBOLS.md test dropped: an unindexed repo would get a full scan.
FIXTURE_NO_SYMBOLS_TEST = FIXTURE_HEAD + r'''if [ -f "$BIN/build_index.py" ] && command -v timeout >/dev/null 2>&1; then
  timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (g) no guard at all.
FIXTURE_NO_GUARD = FIXTURE_HEAD + r'''timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
''' + FIXTURE_TAIL

# (h) guard present but the call escaped past the `fi`.
FIXTURE_CALL_AFTER_FI = FIXTURE_HEAD + r'''if [ -f "$BIN/build_index.py" ] && [ -f "$STATE/index/SYMBOLS.md" ]; then
  :
fi
timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
''' + FIXTURE_TAIL

# (i) builder named by a variable that never defaults to the kit builder.
FIXTURE_VARIABLE_WITHOUT_KIT_DEFAULT = FIXTURE_HEAD + r'''IDX_BUILDER="/bin/true"
if [ -f "$IDX_BUILDER" ] && [ -f "$STATE/index/SYMBOLS.md" ]; then
  timeout 5 "$PY" "$IDX_BUILDER" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL

# (j) one file tested, another builder run.
FIXTURE_GUARD_CALL_MISMATCH = FIXTURE_HEAD + r'''IDX_BUILDER="$BIN/build_index.py"
if [ -f "$IDX_BUILDER" ] && [ -f "$STATE/index/SYMBOLS.md" ]; then
  timeout 5 "$PY" "$BIN/some_other_builder.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
''' + FIXTURE_TAIL


class GuardShapeFixtureTests(unittest.TestCase):
    """Permanent non-vacuity for prove_guarded_if_stale_refresh().

    One half asserts correct hooks are ACCEPTED (a generalisation that rejects
    a right hook is the very defect this task fixes), the other that weakened
    ones are REJECTED (a generalisation that accepts a wrong hook measures
    nothing). Same function as the real-file test above — no duplicated logic.
    """

    def assert_accepted(self, label: str, hook_text: str) -> GuardVerdict:
        try:
            return prove_guarded_if_stale_refresh(hook_text)
        except GuardViolation as violation:
            self.fail(f"fixture ({label}) is a CORRECT hook but was rejected: {violation}")

    def assert_rejected(self, label: str, hook_text: str) -> str:
        with self.assertRaises(GuardViolation) as caught:
            verdict = prove_guarded_if_stale_refresh(hook_text)
            self.fail(f"fixture ({label}) must be rejected, was accepted as {verdict}")
        return str(caught.exception)

    def test_a_kit_literal_two_line_condition_is_accepted(self):
        verdict = self.assert_accepted("a/kit-literal", FIXTURE_KIT_LITERAL)
        self.assertEqual("$BIN/build_index.py", verdict.guarded_token)
        self.assertEqual("$BIN/build_index.py", verdict.kit_default)

    def test_b_consumer_wrapper_variable_is_accepted(self):
        verdict = self.assert_accepted("b/consumer-variable", FIXTURE_CONSUMER_VARIABLE)
        self.assertEqual("$IDX_BUILDER", verdict.guarded_token)
        self.assertEqual("$BIN/build_index.py", verdict.kit_default)

    def test_c_braced_variable_in_the_guard_is_accepted(self):
        verdict = self.assert_accepted("c/braced-variable", FIXTURE_BRACED_VARIABLE)
        self.assertEqual("$IDX_BUILDER", verdict.guarded_token)

    def test_d_swapped_f_tests_are_accepted(self):
        verdict = self.assert_accepted("d/swapped-tests", FIXTURE_SWAPPED_TESTS)
        self.assertEqual("$BIN/build_index.py", verdict.guarded_token)

    def test_e_prose_comment_mentioning_if_stale_is_accepted(self):
        self.assert_accepted("e/prose-comment", FIXTURE_PROSE_COMMENT)

    def test_f_dropping_the_symbols_test_is_rejected(self):
        self.assertIn("SYMBOLS.md", self.assert_rejected("f/no-symbols-test", FIXTURE_NO_SYMBOLS_TEST))

    def test_g_no_guard_at_all_is_rejected(self):
        self.assertIn("SYMBOLS.md", self.assert_rejected("g/no-guard", FIXTURE_NO_GUARD))

    def test_h_call_after_the_fi_is_rejected(self):
        self.assertIn("INSIDE", self.assert_rejected("h/call-after-fi", FIXTURE_CALL_AFTER_FI))

    def test_i_variable_without_kit_default_is_rejected(self):
        message = self.assert_rejected("i/no-kit-default", FIXTURE_VARIABLE_WITHOUT_KIT_DEFAULT)
        self.assertIn("must still DEFAULT to the kit builder", message)

    def test_j_guarding_one_file_and_running_another_is_rejected(self):
        message = self.assert_rejected("j/guard-call-mismatch", FIXTURE_GUARD_CALL_MISMATCH)
        self.assertIn("the very builder the call runs", message)


if __name__ == "__main__":
    unittest.main()
