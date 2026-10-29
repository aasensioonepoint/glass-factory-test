"""The Angular signal on the five `language-detector` defs (T-00000460).

WHY THIS FILE EXISTS. R2-01 of the upstream remontée asked for PROOF that
Angular is detected. The relevé that opened the task said "Angular is named in
the five defs", and that was true only of the EMISSION constant — the closed
token set — which `test_stack_skills_contract.py::test_f_the_emission_constant_appears_once_on_every_detector_def`
already pins. Naming a token you may emit is not detecting a stack: not one def
carried a SIGNAL (`angular.json`, `@angular/core`) that would make the detection
step fire. So the lot ADDED the signal and this file pins it. An eval that only
grepped the literal "Angular" would have been a duplicate of test_f measuring
nothing (L-00000343).

THE SIGNAL IS CARRIED IN TWO PLACES, AND BOTH ARE PINNED HERE. The three LONG
defs carry it where every other marker lives — the `Framework markers` table the
detection procedure actually reads (arm M). All FIVE carry the emission rule
A1C, because the two COMPACT defs (`.github`, `.codex`) have no marker table at
all and A1C is the only byte-identical surface the five share (arm S). The
exemption of those two is ASSERTED rather than left silent: the day one of them
grows a table, arm M claims the marker in it.

DISCOVERY IS HYBRID ON PURPOSE. A literal list of five paths cannot catch the
NEXT sibling def, so the defs are found by scanning. A scan alone is green on an
empty tree (L-00000186), so the five known paths are a FLOOR the scan must
contain. Arms H and H2 then close the other direction — a host declared in
AGENTS.md, or merely PRESENT in the tree, that has no detector def.

THE ROUTE IS NOT DUPLICATED HERE. `## angular` + `kit_skill`, `COVERED angular`
and `ARM: no` are already pinned by `test_stack_skills_contract` arm (e); this
file cites that instead of re-asserting it. The `"framework": "angular@19"`
example in the multi-module block of two defs is deliberately NOT pinned — it is
an example, and pinning it would redden on every retouch.

THIS NET TRAVELS. `.agents/evals/` is not stripped by `.template-exclude`, so an
adopting project runs it too: arm H will redden there the day a host is declared
in its AGENTS.md without a detector def. That is the intended behaviour.
"""
from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The emission rule inserted on the five defs. Byte-identical across hosts on
# purpose: a host that rewords it drifts from the other four in silence. It
# carries NO `"`, no backslash and no backtick — constraint C20, checked by arm
# F — because it has to survive a TOML basic string on the `.codex` side.
A1C = (
    "Angular signal: angular.json at a manifest root, or @angular/core among the "
    "dependencies of package.json, emits the framework token angular with the "
    "major read from @angular/core. AngularJS or angularjs names a different "
    "framework: report framework unknown with confidence low and route to ask, "
    "never emit angular for it."
)

# The two literals the DETECTION step reads. They belong inside the marker
# table, not merely somewhere in the file — that is what arm M bounds.
MARKERS = ("angular.json", "@angular/core")

FORBIDDEN = ('"', "\\", "`")

# The FLOOR: a scan that does not return these five has broken, whatever else it
# returns. Two empty sets agree, so the floor is what makes arms S/T non-vacuous.
KNOWN_DEFS = (
    ".claude/agents/language-detector.md",
    ".gemini/agents/language-detector.md",
    ".kimi-code/agents/language-detector.md",
    ".github/agents/language-detector.agent.md",
    ".codex/agents/language-detector.toml",
)

# The defs that carry a `Framework markers` table…
TABLE_DEFS = (
    ".claude/agents/language-detector.md",
    ".gemini/agents/language-detector.md",
    ".kimi-code/agents/language-detector.md",
)

# …and the two COMPACT defs that carry none. Exempt BY CONSTRUCTION from arm M's
# positive half, and asserted to stay that way by its negative half (decision D1,
# `specs.py list --task T-00000460`).
COMPACT_DEFS = (
    ".github/agents/language-detector.agent.md",
    ".codex/agents/language-detector.toml",
)

CODEX_DEF = ".codex/agents/language-detector.toml"

# A `.bak` or `.orig` left by an editor beside a def must not be scanned as one.
SUFFIXES = frozenset({".md", ".toml"})

TABLE_HEADING = "Framework markers"
CLOSED_SET_RE = re.compile(r"CLOSED set, lowercase with hyphens: (.+?)\.")

# Recopied from test_automode_doctrine.py::_declared_host_dirs — same extraction,
# same section, so the two nets cannot disagree about what a declared host is.
HOST_DIR_RE = re.compile(r"\.([a-z][a-z0-9-]*)/")


def _read(path: Path) -> str:
    """Always utf-8. A1C carries U+2014-free prose but the def files do not, and
    `pytest.ini` targets Windows dev boxes too: decoded as cp1252 the count would
    be 0 and this eval would redden where its author never plays it."""
    return path.read_text(encoding="utf-8")


def scan_defs(root: Path = ROOT) -> list[Path]:
    """Every `language-detector*` def at the fixed depth `<host>/agents/`.

    Depth is fixed at 2 so the scan never descends into `.worktrees/` or a vendored
    copy; symlinks are ignored for the same reason. `Path.glob` does NOT skip
    dot-directories the way a shell does, so `.claude` and friends are matched.
    """
    found = [
        path
        for path in root.glob("*/agents/language-detector*")
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES
    ]
    return sorted(found)


def _rel(paths) -> set[str]:
    return {path.relative_to(ROOT).as_posix() for path in paths}


def _rel_to(root: Path, paths) -> set[str]:
    return {path.relative_to(root).as_posix() for path in paths}


def marker_table(text: str) -> str | None:
    """The `Framework markers` block ALONE, from its heading to the next numbered
    step or level-2 heading. Returns None when the def carries no table.

    Bounding matters: `@angular/core` also appears in prose elsewhere in the kit,
    and a marker that sits outside the table is a marker the detection step never
    reads."""
    lines = text.splitlines()
    start = None
    for number, line in enumerate(lines):
        if TABLE_HEADING in line:
            start = number
            break
    if start is None:
        return None
    end = len(lines)
    for number in range(start + 1, len(lines)):
        line = lines[number]
        if re.match(r"^\d+\.\s", line) or line.startswith("## "):
            end = number
            break
    return "\n".join(lines[start:end])


def closed_set_tokens(text: str) -> list[str]:
    """The closed token set as the def PUBLISHES it, split on `", "`.

    Never a substring test: a future `angularjs` token would satisfy `in` and this
    arm would go green on a def that had lost `angular`."""
    match = CLOSED_SET_RE.search(text)
    if match is None:
        return []
    return [token.strip() for token in match.group(1).split(", ")]


def declared_host_dirs(root: Path = ROOT) -> set[str]:
    """`.<host>/` prefixes cited in AGENTS.md § Cross-agent surfaces."""
    text = _read(root / "AGENTS.md")
    section: list[str] = []
    capturing = False
    for line in text.splitlines():
        if line.startswith("## "):
            if capturing:
                break
            capturing = "Cross-agent surfaces" in line
            continue
        if capturing:
            section.append(line)
    return {"." + name for name in HOST_DIR_RE.findall("\n".join(section))}


class LanguageDetectorAngularTests(unittest.TestCase):
    # ---------------------------------------------------------------- D
    def test_D_the_scan_returns_the_five_known_defs(self):
        """NON-VACUITY. Every arm below iterates over the scan; if the scan broke
        or a def was renamed, they would all pass over an empty set."""
        scanned = _rel(scan_defs())
        missing = sorted(set(KNOWN_DEFS) - scanned)
        self.assertEqual(
            missing, [],
            "the scan no longer returns known detector def(s): "
            f"{missing}. Either a def was renamed or removed, or the depth-2 glob "
            "broke — every arm of this file iterates over that scan",
        )

    # ---------------------------------------------------------------- H
    def test_H_every_declared_host_with_an_agents_dir_has_a_detector(self):
        """DECLARED hosts. A host named in AGENTS.md § Cross-agent surfaces that
        owns an `agents/` directory must own a detector def in it. `.agent`
        (Antigravity) is exempt BY CONSTRUCTION: it has no `agents/` directory —
        its skills reach it by path, never by discovery."""
        declared = declared_host_dirs()
        self.assertTrue(
            declared, "no `.<host>/` prefix extracted from § Cross-agent surfaces "
            "— the section moved or was retitled, and this arm is now vacuous",
        )
        self.assertIn(
            ".kimi-code", declared,
            "`.kimi-code` is missing from the extraction — the regex or the "
            "section changed shape; the multi-segment host is the canary here",
        )
        scanned = _rel(scan_defs())
        for host in sorted(declared):
            if not (ROOT / host / "agents").is_dir():
                continue
            self.assertTrue(
                any(rel.startswith(f"{host}/agents/") for rel in scanned),
                f"{host}/agents/ exists and {host} is declared in AGENTS.md "
                "§ Cross-agent surfaces, but it carries no language-detector def. "
                "A host without a detector routes every task on habit",
            )

    # ---------------------------------------------------------------- H2
    def test_H2_every_host_dir_present_in_the_tree_has_a_detector(self):
        """PRESENT hosts — the tree, not the declaration. A `.cursor/agents/`
        dropped in without touching AGENTS.md would slip past arm H, and the
        objective ("the next sibling def cannot be born without the signal")
        would be overstated. Dot-dirs only: `agentic_v3/agents/` is not a host."""
        scanned = _rel(scan_defs())
        host_dirs = [
            d for d in sorted(ROOT.glob(".*/agents")) if d.is_dir() and not d.is_symlink()
        ]
        self.assertGreaterEqual(
            len(host_dirs), 4,
            "fewer than four `.<host>/agents/` directories found in the tree — the "
            f"glob broke and this arm is measuring nothing. Found: {host_dirs}",
        )
        for agents_dir in host_dirs:
            host = agents_dir.parent.name  # already carries its leading dot
            self.assertTrue(
                any(rel.startswith(f"{host}/agents/") for rel in scanned),
                f"{host}/agents/ is present in the tree but carries no "
                "language-detector def. Declared or not, a host that routes work "
                "needs one",
            )

    # ---------------------------------------------------------------- S
    def test_S_the_emission_rule_appears_exactly_once_on_every_def(self):
        """A1C, byte for byte, once per def. Once — not "at least once" — so a
        copy-paste that lands the rule twice is caught as the drift it is."""
        for path in scan_defs():
            rel = path.relative_to(ROOT).as_posix()
            self.assertEqual(
                _read(path).count(A1C), 1,
                f"{rel} does not carry the Angular emission rule exactly once. "
                "The constant is byte-identical across hosts on purpose: a host "
                "that paraphrases it drifts from the other four in silence",
            )

    # ---------------------------------------------------------------- M
    def test_M_the_markers_sit_inside_the_table_that_serves_detection(self):
        """The signal where the detection step READS it. A marker in the prose of
        the file is a marker step 3 never consults."""
        for rel in TABLE_DEFS:
            table = marker_table(_read(ROOT / rel))
            self.assertIsNotNone(
                table,
                f"{rel} no longer carries a `{TABLE_HEADING}` block — either it "
                "was renamed, or this def became compact and belongs in "
                "COMPACT_DEFS",
            )
            for marker in MARKERS:
                self.assertIn(
                    marker, table,
                    f"{rel}: `{marker}` is not inside the `{TABLE_HEADING}` "
                    "block. Present elsewhere in the file is not enough — the "
                    "detection step reads the table",
                )

    def test_M_the_compact_defs_are_exempt_by_construction_not_by_omission(self):
        """The other half of M, and the reason the exemption is not a permanent
        hole: `.github` and `.codex` are compact defs with no marker table at all
        (decision D1). The day either grows one, this arm fails and the positive
        half above claims the marker in it."""
        for rel in COMPACT_DEFS:
            self.assertIsNone(
                marker_table(_read(ROOT / rel)),
                f"{rel} has gained a `{TABLE_HEADING}` block. It was exempt from "
                "the marker arm BECAUSE it had none — move it into TABLE_DEFS so "
                "the Angular markers are claimed there too",
            )

    # ---------------------------------------------------------------- T
    def test_T_the_closed_set_of_every_def_still_carries_the_angular_token(self):
        """COHERENCE between what A1C emits and what the def allows. Not redundant
        with test_stack_skills_contract test_f: a revision of the emission constant
        that dropped `angular` everywhere at once would keep test_f green (it
        compares the defs to the constant) and redden here."""
        for path in scan_defs():
            rel = path.relative_to(ROOT).as_posix()
            tokens = closed_set_tokens(_read(path))
            self.assertTrue(
                tokens, f"{rel}: the closed token set could not be parsed — the "
                "emission constant was reworded and A1C now emits a token no def "
                "publishes",
            )
            self.assertIn(
                "angular", tokens,
                f"{rel}: `angular` is no longer in the published closed set, but "
                f"A1C tells the agent to emit it. Tokens read: {tokens}",
            )

    # ---------------------------------------------------------------- P
    def test_P_the_codex_def_carries_the_rule_in_its_PARSED_instructions(self):
        """The raw bytes are not what the agent reads. A stray `"` or `\\` in the
        TOML basic string would truncate the instructions without any parse error
        the eye would catch."""
        data = tomllib.loads(_read(ROOT / CODEX_DEF))
        instructions = data.get("developer_instructions", "")
        self.assertIn(
            A1C, instructions,
            f"{CODEX_DEF}: the Angular rule is absent from the PARSED "
            "`developer_instructions`. Present in the raw bytes is not enough — "
            "check for an escaped quote or backslash that truncated the string",
        )

    # ---------------------------------------------------------------- F
    def test_F_the_constant_carries_no_character_the_toml_would_eat(self):
        """C20, checked on the CONSTANT so it fails BEFORE it lands on the TOML."""
        for character in FORBIDDEN:
            self.assertNotIn(
                character, A1C,
                f"A1C carries {character!r}; it has to survive a TOML basic "
                "string in the .codex def",
            )
        self.assertFalse(
            A1C.endswith('"'),
            "A1C ends on a double quote — it would close the TOML string early",
        )

    # ---------------------------------------------------------------- N
    def test_N_negative_controls_every_arm_reddens_on_its_own_mutation(self):
        """Each predicate is asserted GREEN on the tree first, then RED on the
        mutation that should break it. A net nobody has seen fail is a net whose
        failure mode is unknown."""
        claude = _read(ROOT / ".claude/agents/language-detector.md")

        # S — the rule removed
        self.assertEqual(claude.count(A1C), 1, "base for the S control is not green")
        self.assertEqual(
            claude.replace(A1C, "").count(A1C), 0,
            "S DOES NOT BITE: the rule removed, the count held",
        )

        # T — `angular` struck from the published closed set
        self.assertIn("angular", closed_set_tokens(claude), "base for T is not green")
        mutilated = claude.replace(
            "go, angular, vue, nuxt", "go, vue, nuxt", 1
        )
        self.assertNotIn(
            "angular", closed_set_tokens(mutilated),
            "T DOES NOT BITE: the token struck from the closed set, the arm held",
        )

        # M — the marker pulled out of the table
        table = marker_table(claude)
        self.assertIsNotNone(table, "base for the M control is not green")
        self.assertIn("angular.json", table)
        self.assertNotIn(
            "angular.json", marker_table(claude.replace("angular.json", "", 1)) or "",
            "M DOES NOT BITE: the marker removed, the table still matched",
        )

    def test_N2_the_scan_finds_a_host_a_literal_list_would_have_missed(self):
        """The half of the discovery a fixed list cannot do, and the half H2 adds
        on top of it — proven on a planted tree rather than argued."""
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            newhost = root / ".newhost" / "agents"
            newhost.mkdir(parents=True)
            (newhost / "language-detector.md").write_text("x", encoding="utf-8")
            (root / ".other" / "agents").mkdir(parents=True)
            (root / ".newhost" / "agents" / "language-detector.md.bak").write_text(
                "x", encoding="utf-8"
            )

            scanned = _rel_to(root, scan_defs(root))
            self.assertIn(
                ".newhost/agents/language-detector.md", scanned,
                "the scan missed a host no literal list could have named",
            )
            self.assertNotIn(
                ".newhost/agents/language-detector.md.bak", scanned,
                "a `.bak` beside a def was scanned as a def — arm S would redden "
                "on an editor's leftover",
            )
            self.assertFalse(
                any(rel.startswith(".other/agents/") for rel in scanned),
                "base for the H/H2 control is not green: `.other` was never "
                "supposed to yield a def",
            )
            self.assertTrue(
                (root / ".other" / "agents").is_dir(),
                "H2 walks `.*/agents` directories — `.other` has to be one",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
