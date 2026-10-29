"""Contract for the four STACK skills of the kit (T-00000385).

WHAT THIS SUITE JUDGES, AND WHY IT IS NOT A PRESENCE CHECK. A skill that exists
but is invisible to discovery, or whose rules do not say WHICH version of a
framework they hold for, is worse than an absent skill: it reads as coverage.
So this file judges the SUBSTANCE of the four bodies, not only their presence.

FIVE ARMS, EACH WITH A NAMED NEGATIVE CONTROL (L-00000057 — an arm that cannot
go RED measures nothing):

  (a) FORM      — the four skills sit at DEPTH 1, their frontmatter opens on
                  LINE 1, their `name:` equals their directory, and their body
                  clears a non-vacuity floor. The four names are WRITTEN IN HARD
                  CODE, never derived from a glob: two empty sets agree
                  perfectly (L-00000186).
  (b) LABEL     — every rule line of the Java body carries one label of the
                  CLOSED set, and four of the five appear at least once.
                  `[FW6+7]` is EXEMPT from the floor: it is the "holds on both
                  version lines" label, and requiring it would force an author
                  to invent one.
  (c) SOURCING  — every line carrying a version number carries `https://` or the
                  `à vérifier` marker. ITS CORPUS IS NAMED, and that naming is
                  the point (see the block above ARM_C_CORPUS below).
  (d) CARDINAL  — the label set has EXACTLY five members: a label added without
                  revising this file reddens.
  (e) COVERAGE  — the 9-token probe on the REAL root: the fallback must report
                  `ARM: no`, i.e. the kit no longer sends anyone to GitHub for a
                  stack it now carries itself.
  (f) MIRRORS   — the two emission constants appear ONCE on each of the 5 host
                  defs and carry none of the FORBIDDEN characters. See the block
                  above FORBIDDEN below for why the form binds all five hosts and
                  not `.codex` alone (reserve C20).

WHY THE REAL-TREE CONTRACT LIVES HERE AND NOT IN `.agents/bin/` (C17). The whole
discipline of `.agents/bin/test_skills_github_fallback.py` is `build_root(tmp_path)`
— a synthetic root. Mixing a hermetic bench and a real-tree contract in one file
makes the reason for a red unreadable. That file keeps the UNIT cases; the two
arms that read the REPOSITORY (the four bodies, and the coverage probe) live here.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".agents" / "skills"
POINTER_DIR = ROOT / ".claude" / "skills"
FALLBACK = ROOT / ".agents" / "bin" / "skills_github_fallback.py"

# ARM (a) — WRITTEN HERE, never globbed. A glob would define the expected set as
# whatever it found, and would stay green on an empty tree (L-00000186).
STACK_SKILLS = (
    "angular-modern",
    "go-idiomatic",
    "java-hexagonal-spring",
    "vue-modern",
)

# Non-vacuity floor for a body. A skill whose body is three lines is a skill that
# advertises coverage it does not carry.
BODY_FLOOR_CHARS = 2000
BODY_FLOOR_LINES = 20

# ARM (b) + (d) — the CLOSED label set. Java is the only stack of the four whose
# framework ships two live major lines at once, so it is the only body labelled.
JAVA_SKILL = "java-hexagonal-spring"
RULES_HEADING = "## Règles étiquetées"
VERSION_LABELS = ("[FW6]", "[FW7]", "[FW6+7]", "[BOOT]", "[HORS-BOOT]")
LABEL_CARDINAL = 5
# `[FW6+7]` is deliberately ABSENT from the floor — see the module docstring.
REQUIRED_LABELS = ("[FW6]", "[FW7]", "[BOOT]", "[HORS-BOOT]")
RULE_LINE = re.compile(r"^- \[([A-Z0-9+-]+)\] ")
LABELLED_RULES_FLOOR = 12

# ARM (c) — THE CORPUS THIS ARM SWEEPS, NAMED IN EXTENSION (T-00000385 reserve C21).
#
# An arm whose corpus is unstated is an arm nobody can audit: the two other
# file-reading arms name theirs — (a) names the four skills, (b) bounds itself to
# the Java body — and this one used to name nothing while carrying a pattern
# (`\b\d+\.\d+\b`) that bites on ordinary prose. Unbounded, it would have swept
# every Markdown file in the repository and reddened on a version number written
# in a changelog, a plan or a ledger entry, none of which this contract governs.
#
# So the corpus is EXACTLY the four SKILL.md of STACK_SKILLS, BODY ONLY. The
# FRONTMATTER IS EXCLUDED, and that exclusion is load-bearing rather than
# cosmetic: a `description:` legitimately names versions (it is what a host reads
# to decide whether to trigger the skill), it is not a rule, and it has no room
# for a URL. Sweeping it would force a source onto a line that cannot carry one.
ARM_C_CORPUS = tuple(SKILLS_DIR / name / "SKILL.md" for name in STACK_SKILLS)

# A version claim: either a stack name followed by a number, or any `d.d` pair.
# NEVER an enumeration of today's versions (`\b(3|6|7|17|21)\.`): a predicate that
# lists the versions of the day expires at the first release, and bites on the
# punctuation of ordinary prose.
VERSION_CLAIM = re.compile(
    r"(?i)\b(java|spring boot|spring framework|spring|angular|vue|nuxt|go)"
    r"\s+v?\d{1,2}(?:\.\d+)*\+?"
)
LOOSE_NUMBER = re.compile(r"\b\d+\.\d+\b")
# A bare major written `vNN` or `vNN.N` (« depuis v21 », « v20.2 »): the Angular
# body names its versions this way, with no stack name in front.
V_MAJOR = re.compile(r"\bv\d{2}(?:\.\d+)?\b")
# Assumed bound, written rather than left implicit: a claim carrying NO number
# does not require a source.
SOURCE_MARKERS = ("https://", "à vérifier")

# ARM (e) — the nine tokens. `react` is in the list although this lot does not
# touch it: the probe measures the fallback's verdict on the WHOLE detected
# surface, and a react regression would arm a GitHub search just as loudly.
PROBE_STACKS = "java,spring,spring-boot,spring-framework,go,angular,vue,nuxt,react"
PROBE_TOKEN_COUNT = 9

# ARM (f) — THE TWO EMISSION CONSTANTS, AND WHY THEIR FORM BINDS ALL FIVE HOSTS
# (T-00000385 reserve C20).
#
# The plan asks for VERBATIM mirrors on the five host defs, and separately bounds
# the FORM (no backtick, no double quote, no backslash) to `.codex`, whose
# `developer_instructions` is a TOML BASIC string where `\` is an escape and a
# stray `"` can close the literal. Read literally the two clauses contradict:
# either the added line differs on the fifth host, or the constraint is carried
# in the wrong place.
#
# IT IS CARRIED BY THE CONSTANT, and the repository already settled this. In
# `test_skills_resolver_fallback_contract.py` the same `FORBIDDEN` triple is
# asserted on S1C/S2C/S3C — the CONSTANTS the five hosts carry — never on the
# `.codex` file. A form bound to one host would have to be re-checked by hand on
# every mirror; bound to the constant it holds on all five by construction, and
# byte-identity does the rest. So: one form, five hosts, asserted once.
DETECTOR_DEFS = (
    ROOT / ".claude" / "agents" / "language-detector.md",
    ROOT / ".gemini" / "agents" / "language-detector.md",
    ROOT / ".codex" / "agents" / "language-detector.toml",
    ROOT / ".github" / "agents" / "language-detector.agent.md",
    ROOT / ".kimi-code" / "agents" / "language-detector.md",
)

RESOLVER_DEFS = (
    ROOT / ".claude" / "agents" / "skills-resolver.md",
    ROOT / ".gemini" / "agents" / "skills-resolver.md",
    ROOT / ".codex" / "agents" / "skills-resolver.toml",
    ROOT / ".github" / "agents" / "skills-resolver.agent.md",
    ROOT / ".kimi-code" / "agents" / "skills-resolver.md",
)

CODEX_DEFS = (DETECTOR_DEFS[2], RESOLVER_DEFS[2])

# 2026-10-18, T-01M52X1W3WPKCWX1DC36NMKJB6: `terraform` joins the closed set on
# the five detector defs (lot E, step 5 of the plan).
E1C = (
    "Stack tokens emitted in registry_sections, framework, primary_language and "
    "modules[] entries come from this CLOSED set, lowercase with hyphens: java, "
    "spring-boot, spring-framework, typescript, go, angular, vue, nuxt, terraform. Never the prose Spring "
    "Boot with a space — the form check admits the space, the casefolded token "
    "spring boot matches no registry title and no bullet, and the section resolves "
    "to NO SECTION in silence. Never golang — the mini alias maps it to go for "
    "SECTION lookup only, never for COVERAGE, so it would resolve the section and "
    "still report UNCOVERED, arming a GitHub search for a stack the kit already "
    "carries."
)

R1C = (
    "Before any external search, open the DOCS_REGISTRY section for the detected "
    "stack and read its kit_skill: key — when it names a kit skill, open that file "
    "BY PATH and stop there: a stack the kit already carries is never searched on "
    "GitHub."
)

FORBIDDEN = ('"', "\\", "`")

# The prose form the emission constant exists to forbid. `_normalize_pairs`
# casefolds it to `spring boot`, which matches no registry title and no bullet.
FORBIDDEN_PROSE = "→ Spring Boot"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Raises if the frontmatter does not open line 1.

    The two faults that hide a skill IN SILENCE are depth and this opening line
    (AGENTS.md § Skills index) — neither produces an error, so both are asserted.
    """
    if not text.startswith("---\n"):
        raise ValueError("frontmatter does not open on line 1")
    rest = text[len("---\n") :]
    end = rest.find("\n---\n")
    if end < 0:
        raise ValueError("frontmatter is never closed")
    return rest[:end], rest[end + len("\n---\n") :]


def _body(name: str) -> str:
    return _split_frontmatter(_read(SKILLS_DIR / name / "SKILL.md"))[1]


def _unsourced_lines(body: str) -> list[tuple[int, str]]:
    """Lines of a BODY that claim a version without a source or an `à vérifier`."""
    offenders = []
    for number, line in enumerate(body.split("\n"), 1):
        if not (VERSION_CLAIM.search(line) or LOOSE_NUMBER.search(line) or V_MAJOR.search(line)):
            continue
        if any(marker in line for marker in SOURCE_MARKERS):
            continue
        offenders.append((number, line))
    return offenders


def _java_rule_lines() -> list[str]:
    body = _body(JAVA_SKILL)
    head, sep, tail = body.partition(RULES_HEADING)
    assert sep, f"{JAVA_SKILL} has no `{RULES_HEADING}` section"
    section = tail.split("\n## ", 1)[0]
    return [line for line in section.split("\n") if line.startswith("- ")]


class StackSkillsContractTests(unittest.TestCase):
    # ----------------------------------------------------------------- arm (a)
    def test_a_the_four_skills_exist_at_depth_one(self):
        for name in STACK_SKILLS:
            path = SKILLS_DIR / name / "SKILL.md"
            self.assertTrue(
                path.is_file(),
                f"{name} is missing at DEPTH 1 — at depth 2 (e.g. under vendor/) it "
                "would be invisible to discovery, with no error and no warning",
            )

    def test_a_frontmatter_opens_on_line_one_and_name_equals_the_directory(self):
        for name in STACK_SKILLS:
            text = _read(SKILLS_DIR / name / "SKILL.md")
            frontmatter, _ = _split_frontmatter(text)
            match = re.search(r"^name:\s*(\S+)\s*$", frontmatter, re.M)
            self.assertIsNotNone(match, f"{name}: no `name:` in the frontmatter")
            self.assertEqual(
                match.group(1), name,
                f"{name}: `name:` diverges from its directory. Coverage would then be "
                "FALSE IN SILENCE — the fallback's _coverage matches on `name:` alone",
            )

    def test_a_every_body_clears_the_non_vacuity_floor(self):
        for name in STACK_SKILLS:
            body = _body(name)
            self.assertGreaterEqual(
                len(body), BODY_FLOOR_CHARS,
                f"{name}: body of {len(body)} chars, floor {BODY_FLOOR_CHARS}",
            )
            non_empty = [line for line in body.split("\n") if line.strip()]
            self.assertGreaterEqual(
                len(non_empty), BODY_FLOOR_LINES,
                f"{name}: {len(non_empty)} non-empty body lines, floor {BODY_FLOOR_LINES}",
            )

    def test_a_each_skill_has_its_claude_pointer(self):
        """`.agents/skills/` is NOT discovered by Claude Code: without the pointer
        the four skills are reachable BY PATH only, never by trigger. Two distinct
        mechanisms — the pointer is for the HOST, the depth-1 skill for the PROBE."""
        for name in STACK_SKILLS:
            pointer = POINTER_DIR / f"{name}-pointer" / "SKILL.md"
            self.assertTrue(pointer.is_file(), f"missing Claude pointer for {name}")
            frontmatter, _ = _split_frontmatter(_read(pointer))
            self.assertIn(
                f"name: {name}-pointer", frontmatter,
                f"{name}-pointer: `name:` must equal its directory "
                "(core-scripts/host_sync.test.sh §4-bis)",
            )

    def test_e1_negative_control_form_a_depth_two_skill_is_not_admitted(self):
        """(a) must bite on the depth fault it exists for."""
        deep = SKILLS_DIR / "vendor" / STACK_SKILLS[0] / "SKILL.md"
        self.assertFalse(
            deep.is_file(),
            "base not green — a depth-2 twin exists and this control is meaningless",
        )
        admitted = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
        self.assertNotIn(
            "vendor", admitted, "`vendor` is a container, never a depth-1 skill"
        )
        self.assertTrue(
            set(STACK_SKILLS) <= admitted, "base not green — read the depth-1 test first"
        )

    def test_e2_negative_control_form_a_diverging_name_is_detected(self):
        """(a) must bite on the `name:` fault, which is the one that falsifies
        coverage IN SILENCE. Replayed on the same predicate, mutated in memory."""
        name = STACK_SKILLS[0]
        frontmatter, _ = _split_frontmatter(_read(SKILLS_DIR / name / "SKILL.md"))
        self.assertIn(f"name: {name}", frontmatter, "base not green")
        mutilated = frontmatter.replace(f"name: {name}", "name: not-the-directory", 1)
        found = re.search(r"^name:\s*(\S+)\s*$", mutilated, re.M)
        self.assertIsNotNone(found, "the mutation removed the field instead of changing it")
        self.assertNotEqual(
            found.group(1), name,
            "THE NAME RULE DOES NOT BITE: a `name:` renamed in place still compared equal",
        )

    # ----------------------------------------------------------------- arm (b)
    def test_b_every_java_rule_line_carries_a_label_of_the_closed_set(self):
        rules = _java_rule_lines()
        self.assertGreaterEqual(
            len(rules), LABELLED_RULES_FLOOR,
            f"only {len(rules)} rule lines in {JAVA_SKILL} — floor {LABELLED_RULES_FLOOR}. "
            "An empty section satisfies a per-line rule perfectly (L-00000186)",
        )
        for line in rules:
            match = RULE_LINE.match(line)
            self.assertIsNotNone(match, f"rule line without a label: {line[:80]}")
            label = f"[{match.group(1)}]"
            self.assertIn(
                label, VERSION_LABELS,
                f"label {label} is outside the closed set {VERSION_LABELS}: {line[:80]}",
            )

    def test_b_the_four_floor_labels_each_appear_at_least_once(self):
        rules = _java_rule_lines()
        used = {f"[{RULE_LINE.match(line).group(1)}]" for line in rules if RULE_LINE.match(line)}
        for label in REQUIRED_LABELS:
            self.assertIn(
                label, used,
                f"{label} never used. A version-scoped constraint that carries no scope "
                "is re-read as universal — which is exactly what these labels prevent",
            )

    def test_e3_negative_control_label_an_unlabelled_rule_is_detected(self):
        """(b) must bite. Replayed on the same predicate with the label stripped
        from one real rule line — the mutation is in memory, the tree is untouched."""
        rules = _java_rule_lines()
        self.assertTrue(rules, "base not green — read the label test first")
        mutilated = RULE_LINE.sub("- ", rules[0], count=1)
        self.assertNotEqual(mutilated, rules[0], "the mutation removed nothing")
        self.assertIsNone(
            RULE_LINE.match(mutilated),
            "THE LABEL RULE DOES NOT BITE: a rule line stripped of its label still matched",
        )

    # ----------------------------------------------------------------- arm (c)
    def test_c_every_version_claim_in_the_named_corpus_carries_a_source(self):
        """The corpus is ARM_C_CORPUS — the four SKILL.md, BODY ONLY."""
        self.assertEqual(
            len(ARM_C_CORPUS), len(STACK_SKILLS),
            "the swept corpus no longer matches the declared skill set",
        )
        for path in ARM_C_CORPUS:
            _, body = _split_frontmatter(_read(path))
            offenders = _unsourced_lines(body)
            self.assertFalse(
                offenders,
                f"{path.parent.name}: version claim(s) with neither a source nor "
                f"`à vérifier`: {offenders}",
            )

    def test_c_the_frontmatter_is_excluded_and_that_exclusion_is_measured(self):
        """The exclusion is asserted, not assumed (L-00000111): at least one
        `description:` DOES claim a version, so a sweep of the whole file would
        redden on a line that legitimately cannot carry a URL. The day no
        description claims a version any more, this fails and the reasoning above
        gets revisited instead of quietly becoming false."""
        claiming = []
        for path in ARM_C_CORPUS:
            frontmatter, _ = _split_frontmatter(_read(path))
            if _unsourced_lines(frontmatter):
                claiming.append(path.parent.name)
        self.assertTrue(
            claiming,
            "no frontmatter claims a version any more — the exclusion documented on "
            "ARM_C_CORPUS now describes a hazard that does not exist; rewrite it",
        )

    def test_c_vue_modern_carries_no_url_because_its_registry_roots_are_missing(self):
        """R1 item 6, pinned rather than trusted: the `## vue / nuxt` registry
        section carries `source: à ré-établir — T-00000239` instead of doc roots,
        so this skill has NO official source available in the kit to cite. It
        therefore cites none, and marks every version claim `à vérifier`."""
        registry = _read(ROOT / ".agents" / "ref" / "DOCS_REGISTRY.md")
        section = registry.partition("## vue / nuxt")[2].split("\n## ", 1)[0]
        self.assertIn(
            "à ré-établir", section,
            "the vue/nuxt registry roots were restored — re-source vue-modern and "
            "delete this test in the same edit",
        )
        _, body = _split_frontmatter(_read(SKILLS_DIR / "vue-modern" / "SKILL.md"))
        self.assertNotIn(
            "https://", body,
            "vue-modern cites a URL while its registry section has no doc root: an "
            "invented source is worse than a declared absence",
        )

    def test_e4_negative_control_sourcing_an_unsourced_version_line_is_detected(self):
        """(c) must bite, on the exact line the plan names in extension."""
        offender = "- [FW7] Spring Framework 7 introduit le RestClient"
        self.assertFalse(
            _unsourced_lines("le domaine ne dépend d'aucun type Spring"),
            "the predicate bites on a sentence carrying NO number — assumed bound broken",
        )
        self.assertTrue(
            _unsourced_lines(offender),
            "THE SOURCING RULE DOES NOT BITE: a version claim with neither `https://` "
            "nor `à vérifier` was accepted",
        )
        self.assertFalse(
            _unsourced_lines(offender + " — à vérifier"),
            "the marker does not clear the offender, so the rule is unsatisfiable",
        )

    # ----------------------------------------------------------------- arm (d)
    def test_d_the_label_set_has_exactly_five_members(self):
        self.assertEqual(
            len(VERSION_LABELS), LABEL_CARDINAL,
            "the label set changed size. A label added without revising this file "
            "would be admitted by the closed-set test and floored by nothing",
        )
        self.assertEqual(
            len(set(VERSION_LABELS)), LABEL_CARDINAL, "a label is duplicated"
        )
        self.assertTrue(
            set(REQUIRED_LABELS) < set(VERSION_LABELS),
            "the floor must be a STRICT subset — `[FW6+7]` is exempt by design",
        )

    def test_e5_negative_control_cardinal_a_sixth_label_is_detected(self):
        """(d) must bite: a sixth label added in memory breaks the cardinal."""
        widened = VERSION_LABELS + ("[FW8]",)
        self.assertNotEqual(
            len(widened), LABEL_CARDINAL,
            "THE CARDINAL DOES NOT BITE: a sixth label left the count unchanged",
        )

    # ----------------------------------------------------------------- arm (e)
    def test_e_the_nine_token_probe_reports_arm_no_on_the_real_root(self):
        """THE PROBE IS HARDENED, and each hardening comes from a measured trap:

        - `COVERED` is a SUBSTRING of `UNCOVERED`, so the count is taken on the
          START OF LINE, never with a bare `in`;
        - `_arm_line` and `cmd_check` emit `ARM: no`, `ARM: no (confidence <x>)`
          and `ARM: yes <stacks>` — so the verdict is compared BY WHOLE-LINE
          EQUALITY, which a `startswith` would not distinguish;
        - `_print_analysis` emits one line PER STACK, never per skill, so adding
          a skill elsewhere lengthens a joined list without creating a line: this
          test does not redden at the next skill added.
        """
        proc = subprocess.run(
            [sys.executable, str(FALLBACK), "check", "--stacks", PROBE_STACKS],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, f"check failed: {proc.stderr}")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        uncovered = [line for line in lines if line.startswith("UNCOVERED ")]
        covered = [line for line in lines if line.startswith("COVERED ")]
        self.assertEqual(
            uncovered, [],
            f"the kit still sends a covered stack to GitHub: {uncovered}",
        )
        self.assertEqual(
            len(covered), PROBE_TOKEN_COUNT,
            f"{len(covered)} COVERED lines, expected {PROBE_TOKEN_COUNT}:\n{proc.stdout}",
        )
        self.assertEqual(
            lines[-1], "ARM: no",
            f"the verdict line is not exactly `ARM: no`:\n{proc.stdout}",
        )

    def test_e6_negative_control_coverage_an_uncovered_token_arms_the_search(self):
        """(e) must bite. `cobol` has no section and no skill, so the SAME command
        on the SAME root must report UNCOVERED and arm — proving the green above
        measures the tree rather than the parsing."""
        proc = subprocess.run(
            [sys.executable, str(FALLBACK), "check", "--stacks", "cobol"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, f"check failed: {proc.stderr}")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertTrue(
            any(line.startswith("UNCOVERED ") for line in lines),
            f"THE PROBE DOES NOT BITE: an uncovered stack reported no UNCOVERED line:\n{proc.stdout}",
        )
        self.assertNotEqual(
            lines[-1], "ARM: no",
            "THE PROBE DOES NOT BITE: an uncovered stack still produced `ARM: no`",
        )

    def test_e_the_probe_measures_shard_f_and_not_only_the_four_skills(self):
        """NON-VACUITY OF THE PROBE, PROVEN RATHER THAN HOPED. Six of the nine
        tokens match a skill BY NAME alone (`_word_match` treats `-` as a
        boundary, so `java` bites on `java-hexagonal-spring`): those six would go
        green on the four skills with the coverage families left EMPTY. Only
        `spring-boot`, `spring-framework` and `nuxt` measure the families — so
        they are asserted here by name. Without this, a shipped-empty shard F
        would record every other assertion as green.
        """
        sys.path.insert(0, str(FALLBACK.parent))
        try:
            import skills_github_fallback as fb
        finally:
            sys.path.pop(0)
        for token, skill in (
            ("spring-boot", "java-hexagonal-spring"),
            ("spring-framework", "java-hexagonal-spring"),
            ("nuxt", "vue-modern"),
        ):
            self.assertFalse(
                fb._word_match(token, skill),
                f"`{token}` now matches `{skill}` by NAME — it no longer measures the "
                "coverage families, and this non-vacuity proof needs rewriting",
            )
            self.assertIn(
                token, fb.COVERAGE_EXPANSION,
                f"`{token}` has no coverage family: the probe would report UNCOVERED "
                "and arm a GitHub search for a stack the kit carries",
            )


    # ----------------------------------------------------------------- arm (f)
    def test_f_the_emission_constant_appears_once_on_every_detector_def(self):
        for path in DETECTOR_DEFS:
            self.assertEqual(
                _read(path).count(E1C), 1,
                f"E1C must appear exactly once in {path} — a host left behind is how "
                "T-00000138 failed",
            )

    def test_f_the_resolver_constant_appears_once_on_every_resolver_def(self):
        for path in RESOLVER_DEFS:
            self.assertEqual(
                _read(path).count(R1C), 1, f"R1C must appear exactly once in {path}"
            )

    def test_f_both_constants_carry_no_forbidden_character_on_any_host(self):
        """C20 RESOLVED HERE: the form binds the CONSTANT, so it binds the five
        hosts at once — see the block above FORBIDDEN."""
        for name, phrase in (("E1C", E1C), ("R1C", R1C)):
            for char in FORBIDDEN:
                self.assertNotIn(
                    char, phrase, f"{name} carries a forbidden character {char!r}"
                )
            self.assertFalse(
                phrase.endswith('"'), f"{name} ends on a double quote"
            )

    def test_f_the_codex_tomls_parse_and_their_bodies_carry_the_constant(self):
        """The `.codex` defs are TOML BASIC strings and NO other suite parses the
        detector one — a stray backslash would break it with no net at all."""
        try:
            import tomllib
        except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
            self.skipTest("tomllib unavailable")
        for path, phrase in zip(CODEX_DEFS, (E1C, R1C)):
            data = tomllib.loads(_read(path))
            self.assertIn(
                phrase, data["developer_instructions"],
                f"{path}: the constant is absent from the PARSED body — it may be "
                "present in the raw bytes and still not reach the agent",
            )

    def test_f_no_detector_def_still_emits_the_forbidden_prose(self):
        for path in DETECTOR_DEFS:
            self.assertNotIn(
                FORBIDDEN_PROSE, _read(path),
                f"{path} still maps a manifest marker to the prose form. It casefolds "
                "to `spring boot`, resolves to NO SECTION in silence, and no error says so",
            )

    def test_e7_negative_control_mirrors_a_host_left_behind_is_detected(self):
        """(f) must bite. Replayed on the same count, with the constant stripped
        from one def's text in memory — the tree is untouched."""
        text = _read(DETECTOR_DEFS[0])
        self.assertEqual(text.count(E1C), 1, "base not green — read the E1C test first")
        mutilated = text.replace(E1C, "", 1)
        self.assertEqual(
            mutilated.count(E1C), 0,
            "THE MIRROR RULE DOES NOT BITE: the constant removed, the count held",
        )
        self.assertIn(
            "`", _read(DETECTOR_DEFS[0]),
            "the host file carries no backtick at all, so the FORBIDDEN sweep on the "
            "CONSTANT is what does the work here — which is exactly the C20 point",
        )

    def test_angular_20_22_content_and_sources(self):
        """Lot Angular A: substantive rules and provenance, isolated from lot B."""
        skill = _read(SKILLS_DIR / "angular-modern" / "SKILL.md")
        pointer = _read(POINTER_DIR / "angular-modern-pointer" / "SKILL.md")
        for name, held in _angular_content_checks(skill, pointer).items():
            with self.subTest(criterion=name):
                self.assertTrue(held, f"Angular content missing or stale: {name}")

    def test_angular_meaning_mutants_are_red(self):
        """The witnesses check the MEANING: a mutant that keeps the words but
        inverts the rule turns its named check red."""
        skill = _read(SKILLS_DIR / "angular-modern" / "SKILL.md")
        pointer = _read(POINTER_DIR / "angular-modern-pointer" / "SKILL.md")
        mutants = (
            ("A6: OnPush default v22 and Eager",
             "`ChangeDetectionStrategy.OnPush` est le défaut",
             "`ChangeDetectionStrategy.OnPush` n'est pas le défaut"),
            ("security: XSRF and bypassSecurityTrust",
             "n'appelle jamais `bypassSecurityTrust*`", "appelle `bypassSecurityTrust*`"),
            ("security: XSRF and bypassSecurityTrust", "#httpclient-xsrf-csrf-security", "#xsrf"),
            ("npm flags after --", "`npm run ng -- test --watch=false`",
             "`npm run ng test --watch=false`"),
            ("out of 20-22: no rule by proximity", "n'applique aucune ligne par proximité",
             "applique la ligne la plus proche"),
        )
        for name, old, new in mutants:
            with self.subTest(mutant=new):
                self.assertIn(old, skill, f"mutant `{new}` mutates nothing")
                checks = _angular_content_checks(skill.replace(old, new), pointer)
                self.assertFalse(checks[name], f"mutant `{new}` survives {name}")
        pointer_mutants = (
            ("pointer targets the Angular skill", pointer,
             ".agents/skills/angular-modern/SKILL.md", ".agents/skills/vue-modern/SKILL.md"),
            ("skill routes to the Angular sheet", skill,
             "La feuille `.agents/ref/CONVENTIONS_angular.md`", "La feuille `.agents/ref/CONVENTIONS_typescript.md`"),
        )
        for name, text, old, new in pointer_mutants:
            with self.subTest(mutant=new):
                self.assertIn(old, text, f"mutant `{new}` mutates nothing")
                mutated = text.replace(old, new)
                checks = (_angular_content_checks(skill, mutated) if text is pointer
                          else _angular_content_checks(mutated, pointer))
                self.assertFalse(checks[name], f"mutant `{new}` survives {name}")
        status = _angular_content_checks(
            skill.replace("| Angular 20 | LTS jusqu'au 2026-11-28", "| Angular 20 | Fin de support le 2026-11-28"),
            pointer,
        )
        self.assertTrue(status["support status per row"], "end of support for v20 must not redden")

    def test_c_bare_v_majors_are_version_claims(self):
        """`v21` / `v20.2` with no stack name in front are claims too (Angular body)."""
        body = _body("angular-modern")
        sourced = "en v20, Karma) ; les projets existants peuvent encore utiliser Karma. Ne remplace pas le runner par supposition. https://angular.dev/guide/testing"
        self.assertIn(sourced, body, "the line-41 mutant mutates nothing")
        self.assertTrue(
            _unsourced_lines(body.replace(sourced, sourced.rsplit(" https://", 1)[0])),
            "the `depuis v21` line lost its URL and nobody noticed",
        )
        self.assertTrue(
            _unsourced_lines(body + "\n- Depuis v22, les composants sont OnPush.\n"),
            "an unsourced `Depuis v22` rule was accepted",
        )

    # ----------------------------------------------------------------- arm (g)
    def test_g_java25_boot4_content_sources_and_description(self):
        """T-01M5DFMXZAGQM6R4NSGE5CA074 lot A: the Java body targets Java 25 /
        Boot 4 / Framework 7 and says so in BOTH frontmatters (skill + pointer);
        each architecture style names ITS ArchUnit entry point and not the
        other's; every `@MockBean` / `@SpyBean` line says, in that order, that it
        is retired or replaced by its `@Mockito…` successor; provenance and the
        wrapper commands are written. Reads this lot's write-set only — never the
        sheet or the registry of lot B (plan C1)."""
        skill_fm, body = _split_frontmatter(_read(SKILLS_DIR / JAVA_SKILL / "SKILL.md"))
        pointer_fm, _ = _split_frontmatter(
            _read(POINTER_DIR / f"{JAVA_SKILL}-pointer" / "SKILL.md")
        )
        for where, fm in (("skill", skill_fm), ("pointer", pointer_fm)):
            for token in JAVA_TARGET_TOKENS:
                self.assertIn(token, fm, f"{where} description lacks `{token}`")
            for stale in JAVA_STALE_TOKENS:
                self.assertNotIn(stale, fm, f"{where} description still says `{stale}`")
        self.assertIsNone(
            JAVA25_REQUIRED.search(body),
            "the body claims Boot 4 REQUIRES Java 25 — its minimum is Java 17",
        )
        self.assertIn(BOOT4_MINIMUM, body, "the body no longer states Boot 4's Java minimum")

        rules = body.partition(RULES_HEADING)[2].split("\n## ", 1)[0]
        for heading, own, other in ARCH_STYLES:
            section = rules.partition(heading)[2].split("\n### ", 1)[0]
            self.assertTrue(section.strip(), f"no `{heading}` sub-section")
            archunit_rules = [
                line for line in section.splitlines()
                if line.startswith("- [") and "Architectures." in line
            ]
            self.assertTrue(archunit_rules, f"`{heading}` has no ArchUnit architecture rule")
            self.assertTrue(
                any(own in line for line in archunit_rules),
                f"`{heading}` ArchUnit rule does not name `{own}`",
            )
            self.assertNotIn(other, section, f"`{heading}` names the other style's `{other}`")

        for old, new in RETIRED_TEST_ANNOTATIONS:
            pattern = re.compile(
                re.escape(old) + r"(?![A-Za-z]).*\b(retiré|remplacé)\b.*" + re.escape(new)
            )
            lines = [line for line in body.split("\n") if re.search(re.escape(old) + r"(?![A-Za-z])", line)]
            self.assertTrue(lines, f"no line tells the reader that `{old}` is gone")
            for line in lines:
                self.assertRegex(
                    line, pattern,
                    f"`{old}` mentioned without `retiré`/`remplacé` then `{new}`, in "
                    f"that order: {line[:100]}",
                )

        for needle in JAVA_REQUIRED_SNIPPETS:
            self.assertIn(needle, body, f"the Java body lacks `{needle}`")
        provenance = body.partition(PROVENANCE_HEADING)[2].split("\n## ", 1)[0]
        self.assertTrue(provenance.strip(), f"no `{PROVENANCE_HEADING}` section")
        self.assertEqual(provenance.count("MIT"), len(MIT_SOURCES), "each source carries `MIT`")
        for url in MIT_SOURCES:
            self.assertIn(url, provenance, f"provenance lacks {url}")
        self.assertRegex(provenance, r"\b20\d\d-\d\d-\d\d\b", "provenance carries no date")
        for phrase in ("synthèse originale", "aucune copie substantielle"):
            self.assertIn(phrase, provenance, f"provenance lacks `{phrase}`")

    def test_h_java_web_and_security_boundaries(self):
        """The DTO and each security rule must state the actual boundary."""
        _, body = _split_frontmatter(_read(SKILLS_DIR / JAVA_SKILL / "SKILL.md"))
        web = body.partition("### Couche web")[2].split("\n### ", 1)[0]
        dto_lines = [line for line in web.splitlines() if "`@Valid`" in line]
        self.assertTrue(
            any(all(token in line for token in ("DTO d'entrée borne", "valide", "ne filtre pas"))
                for line in dto_lines),
            "the DTO bounds accepted fields; @Valid validates but does not filter them",
        )
        security = body.partition("### Sécurité")[2].split("\n### ", 1)[0]
        rules = [line for line in security.splitlines() if line.startswith("- [FW6+7]")]
        for tokens in (
            ("CSRF", "stateless", "jeton en en-tête", "jamais", "session cookie"),
            ("application*.yml", "Aucun secret en dur", "variable d'environnement", "coffre"),
            ("SQL ou JPQL", "paramètres liés", "jamais", "concaténée"),
            ("ObjectInputStream", "polymorphic typing", "entrée externe"),
        ):
            self.assertTrue(
                any(all(token in line for token in tokens) for line in rules),
                f"missing Java security rule with {tokens}",
            )


def _angular_content_checks(skill: str, pointer: str) -> dict[str, bool]:
    """Named checks allow each A1-A12 mutant to break one obligation in memory."""
    skill_fm, body = _split_frontmatter(skill)
    pointer_fm, pointer_body = _split_frontmatter(pointer)
    table = body.partition("## Versions prises en charge")[2].split("\n## ", 1)[0]
    components = body.partition("## Composants et état")[2].split("\n## ", 1)[0]
    templates = body.partition("## Gabarits, routes et HTTP")[2].split("\n## ", 1)[0]
    tests = body.partition("## RxJS et tests")[2].split("\n## ", 1)[0]
    provenance = body.partition("## Sources et provenance")[2].split("\n## ", 1)[0]
    rows = {
        version: [line for line in table.splitlines() if line.startswith(f"| Angular {version} |")]
        for version in (20, 21, 22)
    }
    descriptions = [
        re.search(r"^description: (.+)$", fm, re.M)
        for fm in (skill_fm, pointer_fm)
    ]
    return {
        "A1: v20 row and source": len(rows[20]) == 1 and "https://" in rows[20][0],
        "A2: v21 row and source": len(rows[21]) == 1 and "https://" in rows[21][0],
        "A3: v22 row and source": len(rows[22]) == 1 and "https://" in rows[22][0],
        "A4: v20 LTS end": len(rows[20]) == 1 and "2026-11-28" in rows[20][0],
        "A5: explicit zoneless v20": len(rows[20]) == 1 and "provideZonelessChangeDetection()" in rows[20][0],
        "A6: OnPush default v22 and Eager": len(rows[22]) == 1 and all(
            token in rows[22][0] for token in (
                "`ChangeDetectionStrategy.OnPush` est le défaut", "`ChangeDetectionStrategy.Eager`",
            )
        ) and "n'est pas le défaut" not in rows[22][0],
        "A7: input/output/model": any(
            all(token in line for token in ("input()", "output()", "model()"))
            for line in components.splitlines() if line.startswith("- ")
        ),
        "A8: template and HTTP rules": all(
            token in templates for token in ("@if", "@for", "@defer", "withInterceptors")
        ),
        "A9: bounded test and conditional lint": all(
            token in tests for token in ("ng build", "ng test --watch=false", "ng lint", "cible `lint`", "Vitest", "Karma", "angular.json")
        ),
        "A10: no obsolete sheet claim": "Aucune feuille" not in body + pointer_body,
        "A11: pinned MIT notice": all(
            token in provenance for token in (
                "b1eb9a0a5e156a3640b07cfdd86a136abc65f31f", "MIT", "Copyright 2026 Google LLC"
            )
        ),
        "A12: aligned descriptions and title": all(descriptions) and (
            descriptions[0].group(1) == descriptions[1].group(1)
            and "Angular 20-22" in descriptions[0].group(1)
            and "Angular 20-22" in body.splitlines()[1]
        ),
        "versions read from package.json": "`@angular/core`" in body and "`package.json`" in body,
        "v21 zoneless default": len(rows[21]) == 1 and "zoneless est le défaut" in rows[21][0],
        "functional HTTP interceptors": "provideHttpClient(withInterceptors(" in templates,
        "support status per row": len(rows[20]) == len(rows[21]) == len(rows[22]) == 1 and (
            rows[20][0].split("|")[2].strip().startswith(("LTS", "Fin de support"))
            and rows[21][0].split("|")[2].strip().startswith("LTS")
            and rows[22][0].split("|")[2].strip().startswith("Active")
        ),
        "explicit OnPush before v22": all(
            len(rows[v]) == 1 and "OnPush n'est pas le défaut" in rows[v][0]
            and "changeDetection: ChangeDetectionStrategy.OnPush" in rows[v][0]
            for v in (20, 21)
        ),
        "Vitest from v21, Karma in v20": "depuis v21" in tests and "en v20, Karma" in tests,
        "no redirecting zoneless URL": "guide/experimental/zoneless" not in body,
        "provenance URL at the repo root": (
            "b1eb9a0a5e156a3640b07cfdd86a136abc65f31f/angular-developer/SKILL.md" in provenance
            and "/skills/angular-developer/" not in provenance
        ),
        "security: XSRF and bypassSecurityTrust": all(
            token in templates for token in (
                "configure-la avec `withXsrfConfiguration()`",
                "n'appelle jamais `bypassSecurityTrust*` sur une valeur issue de l'utilisateur",
                "https://angular.dev/best-practices/security#httpclient-xsrf-csrf-security",
            )
        ),
        "npm flags after --": "`npm run ng -- test --watch=false`" in tests,
        "pointer targets the Angular skill": (
            "**La substance vit dans `.agents/skills/angular-modern/SKILL.md`" in pointer_body
        ),
        "skill routes to the Angular sheet": (
            "La feuille `.agents/ref/CONVENTIONS_angular.md`, si elle est présente, "
            "complète cette skill." in body
        ),
        "out of 20-22: no rule by proximity": (
            "Hors 20-22 : n'applique aucune ligne par proximité ; dis-le au rapport et relis "
            "https://angular.dev/reference/releases" in body
        ),
    }


# ARM (g) — the Java 25 / Boot 4 content contract (T-01M5DFMXZAGQM6R4NSGE5CA074).
JAVA_TARGET_TOKENS = ("Java 25", "Spring Boot 4", "Spring Framework 7")
JAVA_STALE_TOKENS = ("Java 17+", "Boot 3.5+")
# A positive claim only: `n'exige pas` / `requires not` is the sentence we WANT.
JAVA25_REQUIRED = re.compile(
    r"(?i)boot 4[^.\n]*\b(exige|requires|requiert|nécessite)\b"
    r"(?!\s+(?:pas|not))[^.\n]*java 25"
)
BOOT4_MINIMUM = "son minimum est Java 17"
ARCH_STYLES = (
    ("### Architecture hexagonale", "onionArchitecture()", "layeredArchitecture()"),
    ("### Architecture n-tier", "layeredArchitecture()", "onionArchitecture()"),
)
RETIRED_TEST_ANNOTATIONS = (("@MockBean", "@MockitoBean"), ("@SpyBean", "@MockitoSpyBean"))
JAVA_REQUIRED_SNIPPETS = (
    "SecurityFilterChain", "@ServiceConnection", "./mvnw -B verify", "./gradlew test",
    "si son plugin est déclaré", ".agents/ref/CONVENTIONS_java.md",
    "si `.agents/skills/java-migration/SKILL.md` existe",
)
PROVENANCE_HEADING = "## Sources et provenance"
MIT_SOURCES = (
    "https://github.com/rrezartprebreza/spring-boot-skills",
    "https://github.com/sivaprasadreddy/sivalabs-agent-skills",
)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
