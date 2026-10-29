"""The contract of the `.agents/ref/CONVENTIONS_*.md` family (T-00000163, T-00000162).

WHY THIS FILE EXISTS. `CONVENTIONS_typescript.md` invites an adopting project to
keep its own facts in a §2 of its own copy. An invitation to write something a
later refresh might erase is a TRAP, and the kind that stays invisible until the
day someone's §2 is gone. T-00000163's relevé concluded that no mechanism of THIS
repo can erase it — `sync_template.py` refuses outright outside the kit, docs-sync
never touches `.agents/ref/`, and a consumer refresh is a merge (L-015) — so the
task reduces to writing the guarantee down and pinning it here.

THE ASSERTION IS CONDITIONAL, AND THAT IS A DELIBERATE DEVIATION FROM THE PLAN,
which asked for the guarantee in EVERY `CONVENTIONS_*.md`. Two files
(`python.md`, `infra.md`) carry no §2 invitation at all, so they carry no trap,
and they sit outside this lot's declared write-set. Demanding the paragraph there
would be boilerplate bought with a write-set overrun. The conditional form is
STRONGER where it matters: it catches the file that does not exist yet — the next
convention sheet that adds the invitation and forgets the guarantee — which a
fixed per-file list never would.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / ".agents" / "ref"

# The invitation that CREATES the obligation, and the guarantee that discharges
# it. Both are matched on a stable substring rather than on a whole paragraph: a
# net that pins prose word for word turns every edit into a false failure.
INVITATION = "§2 of that project's own copy"
GUARANTEE = "SURVIVES a template refresh"


def convention_files() -> list[Path]:
    return sorted(REF.glob("CONVENTIONS_*.md"))


def test_the_family_is_not_empty():
    """NON-VACUITY. Every arm below iterates over a glob; if the glob ever
    returned nothing — a moved directory, a renamed family — they would all pass
    while measuring strictly nothing."""
    assert convention_files(), f"no CONVENTIONS_*.md under {REF}"


@pytest.mark.parametrize("path", convention_files(), ids=lambda p: p.name)
def test_a_sheet_that_invites_a_project_section_carries_the_guarantee(path: Path):
    """The trap, closed. A sheet may legitimately have no §2 invitation; what it
    may NOT do is invite one and stay silent on whether it survives."""
    text = path.read_text(encoding="utf-8")
    if INVITATION not in text:
        pytest.skip(f"{path.name} invites no project section — no obligation")
    assert GUARANTEE in text, (
        f"{path.name} invites a project §2 but never says it survives a refresh — "
        "that invitation is a trap until the guarantee is written"
    )


def test_the_typescript_sheet_is_the_one_that_carries_the_invitation():
    """THE ARM THAT KEEPS THE ONE ABOVE FROM BEING VACUOUS. Every arm of this
    file skips when no sheet invites anything, so a refactor that dropped the
    invitation everywhere would turn the whole suite green while deleting the
    very doctrine it exists to protect."""
    text = (REF / "CONVENTIONS_typescript.md").read_text(encoding="utf-8")
    assert INVITATION in text
    assert GUARANTEE in text


def test_the_nextjs_sheet_exists_and_carries_its_three_named_rules():
    """T-00000162 — the sheet that was MISSING, and the hole aimed straight at
    the two agents just shipped: `frontend-fidelity` and `design-review` point at
    the generic `CONVENTIONS_<stack>.md`, and `language-detector` emits
    `CONVENTIONS_typescript.md` even on a Next project. Without this file they
    fall back on their habits for exactly the framework they are meant to serve.

    The three anchors are asserted because they are the three rules whose absence
    was the defect — a file that exists and says nothing useful would satisfy a
    mere `.exists()`.
    """
    path = REF / "CONVENTIONS_nextjs.md"
    assert path.exists(), "CONVENTIONS_nextjs.md is missing"
    text = path.read_text(encoding="utf-8")
    for anchor in ("webpack", "params", "react-server"):
        assert anchor in text, f"CONVENTIONS_nextjs.md never mentions `{anchor}`"
    # It carries the §1/§2 doctrine too — it was born with it rather than being
    # retrofitted, which is why T-00000163 landed first.
    assert INVITATION in text and GUARANTEE in text


def test_the_shell_sheet_exists_and_carries_its_eight_forbidden_forms():
    """T-00000525 — la feuille qui MANQUAIT, et le trou visait le langage de tout
    l'outillage du kit : hooks, gardes, bancs, `verify.sh`. Six feuilles
    existaient (dotnet, go, infra, nextjs, python, typescript), aucune pour le
    shell — donc `language-detector` émettait `null` et chaque agent retombait
    sur ses habitudes, précisément pour le langage où une forme innocente coûte
    la LECTURE du fichier entier par la porte SAST.

    Les ancres sont assertées parce que leur absence EST le défaut : une feuille
    qui existe et ne dit rien d'utile satisferait un simple `.exists()`. Mesuré
    le 2026-09-09 : 17 fichiers shell sur 121 étaient hors lecture, et les
    corriger a révélé 8 findings `ERROR` préexistants.
    """
    path = REF / "CONVENTIONS_shell.md"
    assert path.exists(), "CONVENTIONS_shell.md is missing"
    text = path.read_text(encoding="utf-8")
    # Les huit formes, chacune par un fragment STABLE — jamais une phrase entière,
    # qu'une reformulation rendrait rouge à tort.
    for anchor in (
        "${prefix:-<root>}",      # 1. métacaractère dans une expansion
        "(_now - _epoch)",        # 2. arithmétique parenthésée
        "10#$RAW",                # 3. base forcée
        "if ! {",                 # 4. `!` devant un groupe d'accolades
        "<<PY",                   # 5. heredoc en condition de `if`
        "case \"$X\" in a) : ;;", # 6. clause collée au `case … in`
        "set\\ *)",               # 7. espace échappé en motif
        "?:[\\\\/]*)",            # 8. classe de caractères à antislash
    ):
        assert anchor in text, f"CONVENTIONS_shell.md ne montre pas la forme `{anchor}`"
    # Le POURQUOI, sans lequel la feuille se lit comme une préférence de style.
    assert "retiré du compte des cibles inspectées" in text or \
           "retirée du compte des cibles inspectées" in text, \
        "la feuille n'explique pas ce que la forme COÛTE (le fichier sort du périmètre inspecté)"
    # Et le filet qui la rend opposable.
    assert "test_no_compact_case.py" in text, \
        "la feuille ne nomme pas le filet qui refuse ces formes"


def test_the_java_sheet_carries_architecture_lint_and_registry_routes():
    """The Java sheet and registry must route to the same, usable Boot 4 guidance."""
    sheet = REF / "CONVENTIONS_java.md"
    assert sheet.is_file(), "Java agents receive no convention sheet"
    text = sheet.read_text(encoding="utf-8")
    for architecture, rule, packages in (
        ("Hexagonal", "onionArchitecture()", ("domain/port/", "adapter/in/", "adapter/out/")),
        ("N-tier", "layeredArchitecture()", ("controller/", "service/", "persistence/")),
    ):
        section = text.split(architecture, 1)[-1].split("N-tier" if architecture == "Hexagonal" else "## Build", 1)[0]
        assert section != text, f"{architecture} architecture is absent"
        assert rule in section, f"{architecture} has no matching ArchUnit rule"
        assert all(package in section for package in packages), f"{architecture} layout is incomplete"
        assert "src/test/java/" in section, f"{architecture} has no architecture test location"
        if architecture == "Hexagonal":
            assert "layeredArchitecture()" not in section, \
                "the hexagonal section prescribes the n-tier ArchUnit rule"
    assert re.search(r"lint[^\n]*only if the corresponding plugin is declared", text), \
        "lint is prescribed without checking the declared plugin"
    for plugin in ("Checkstyle", "Spotless", "PMD"):
        assert re.search(rf"Run {plugin} only if its plugin is declared", text), \
            f"{plugin} is not conditional on a declared plugin"
    assert "./mvnw -B verify" in text and "./gradlew test" in text
    assert "@SpyBean" in text and "@MockitoSpyBean" in text

    registry = (REF / "DOCS_REGISTRY.md").read_text(encoding="utf-8")
    java = registry.split("## java / kotlin\n", 1)[-1].split("\n## c# / .net", 1)[0]
    assert java != registry, "the Java registry section is absent"
    assert re.search(r"^conventions: \.agents/ref/CONVENTIONS_java\.md\b", java, re.M), \
        "the registry does not route Java agents to the sheet"
    for url in ("https://docs.oracle.com/en/java/javase/25/",
                "https://docs.spring.io/spring-boot/4.1/reference/",
                "https://docs.spring.io/spring-framework/reference/",
                "https://www.archunit.org/userguide/html/000_Index.html"):
        assert url in java, f"missing official Java source: {url}"
    assert "not Boot 4's minimum" in java, "Java 25 must not be stated as Boot 4's minimum"


def test_java_skill_and_sheet_share_version_architecture_and_build_rules():
    """A change to either guidance surface must preserve their common contract."""
    skill = (ROOT / ".agents/skills/java-hexagonal-spring/SKILL.md").read_text(
        encoding="utf-8"
    )
    sheet = (REF / "CONVENTIONS_java.md").read_text(encoding="utf-8")
    for name, text in (("skill", skill), ("sheet", sheet)):
        for token in ("Java 25", "Spring Boot 4", "Spring Framework 7", "Java 17"):
            assert token in text, f"{name} loses version rule {token}"
        for command in ("./mvnw -B verify", "./gradlew test"):
            assert command in text, f"{name} loses wrapper command {command}"
        for architecture, required, forbidden in (
            ("hexagonal", "onionArchitecture()", "layeredArchitecture()"),
            ("n-tier", "layeredArchitecture()", "onionArchitecture()"),
        ):
            if name == "skill":
                heading = "### Architecture " + architecture
                section = text.partition(heading)[2].split("\n### ", 1)[0]
            else:
                heading = "Hexagonal" if architecture == "hexagonal" else "N-tier"
                section = text.partition(heading)[2].split(
                    "\nN-tier" if architecture == "hexagonal" else "\n## Build", 1
                )[0]
            assert section.strip(), f"{name} loses {architecture} section"
            assert required in section and forbidden not in section, \
                f"{name} uses the wrong ArchUnit rule for {architecture}"
        for plugin in ("Checkstyle", "Spotless", "PMD"):
            assert plugin in text, f"{name} loses conditional lint tool {plugin}"
    assert "La cible du kit est **Java 25**" in skill
    assert "son minimum est Java 17" in skill
    assert "Java 25 is the target of this kit's guidance" in sheet
    assert re.search(r"Spring Boot 4\s+requires Java 17 at minimum", sheet)
    assert "Aucun wrapper" in skill and "ne devine pas un outil global" in skill
    assert "If neither wrapper is present" in sheet
    assert "do not guess" in sheet and "globally installed" in sheet
    assert not re.search(
        r"declared test task if neither wrapper|if neither wrapper[^\n]*declared test task",
        sheet, re.I,
    ), "the sheet suggests a test task without a wrapper"
    assert "si son plugin est déclaré" in skill
    assert "only if the corresponding plugin is declared" in sheet


ANGULAR_PIN = "b1eb9a0a5e156a3640b07cfdd86a136abc65f31f"
ANGULAR_SHA256 = "ec8d1925e160cf524f643880711ea70a706ff9974f66f6718d7651f1be388cc5"


def _sheet_section(text: str, heading: str) -> str:
    """The body of one `## ` section, empty when the heading is gone."""
    _, found, rest = text.partition(f"\n## {heading}\n")
    return rest.split("\n## ", 1)[0] if found else ""


def angular_sheet_faults(sheet: str, registry: str) -> list[str]:
    """T-01M5DFN0Y4HP3W30WVJZER6JY6 lot B. Every verification command of the
    Angular sheet is CONDITIONED on what the project declares: a sheet that
    fixes npm, imposes Vitest on a Karma suite or runs `ng lint` without a
    target hands the agent a command that passes nowhere or installs something.
    The registry routes to the sheet and carries the audited upstream pin
    beside `kit_skill`, never under `## installed` (nothing is installed)."""
    faults: list[str] = []
    if "CONVENTIONS_typescript.md" not in sheet.split("\n## ", 1)[0]:
        faults.append("the sheet no longer layers on CONVENTIONS_typescript.md")
    manager = _sheet_section(sheet, "Package manager")
    for token in ("`packageManager`", "`package.json`", "cli.packageManager", "unknown"):
        if token not in manager:
            faults.append(f"package manager is not read from the project: {token} missing")
    if re.search(r"(?im)^- (?:always )?use npm\b", manager):
        faults.append("package manager fixed to npm")
    order = [manager.find(token) for token in ("lockfile", "`packageManager`", "`cli.packageManager`")]
    if -1 in order or order != sorted(order):
        faults.append("package manager sources out of order: lockfile < packageManager < cli.packageManager")
    if "`bun.lockb` > `pnpm-lock.yaml` >\n  `yarn.lock` > `package-lock.json`" not in manager:
        faults.append("the detector's lockfile precedence is missing")
    if "The detector reads neither `bun.lock` nor `cli.packageManager`" not in manager:
        faults.append("bun.lock or cli.packageManager attributed to the detector")
    if "`npm run ng -- test --watch=false`" not in manager:
        faults.append("npm flags not passed after `--`")
    tests = _sheet_section(sheet, "Tests")
    for token in ("options.runner", "@angular/build:karma",
                  "@angular-devkit/build-angular:karma", "ng test --watch=false",
                  "--no-watch --no-progress --browsers=ChromeHeadless"):
        if token not in tests:
            faults.append(f"test runner not read from angular.json: {token} missing")
    if not re.search(r"from v21 the default runner is Vitest;\s+in v20 `runner` is required", tests):
        faults.append("default runner per major not stated (v21 Vitest, v20 required)")
    if re.search(r"(?i)always (?:use|run) vitest", tests):
        faults.append("Vitest imposed whatever the declared runner")
    lint = _sheet_section(sheet, "Lint")
    if not re.search(r"`ng lint` only if `angular\.json` declares a `lint` target", lint):
        faults.append("ng lint is not conditioned on a declared lint target")
    angular = _sheet_section(registry, "angular")
    installed = _sheet_section(registry, "installed")
    if not re.search(r"^conventions: \.agents/ref/CONVENTIONS_angular\.md\b", angular, re.M):
        faults.append("registry ## angular does not route to the sheet")
    if not re.search(r"^kit_skill: \.agents/skills/angular-modern/SKILL\.md$", angular, re.M):
        faults.append("registry ## angular lost its kit_skill")
    upstream = next((line for line in angular.splitlines()
                     if line.startswith("upstream_skill: angular/skills#angular-developer")), "")
    if f"pin={ANGULAR_PIN}" not in upstream:
        faults.append("registry ## angular lost the audited pin")
    if f"sha256={ANGULAR_SHA256}" not in upstream:
        faults.append("registry ## angular lost the audited fingerprint")
    if "angular" in installed.lower():
        faults.append("the upstream Angular skill is listed under ## installed")
    return faults


def test_angular_sheet_routes_and_registry():
    sheet = (REF / "CONVENTIONS_angular.md").read_text(encoding="utf-8")
    registry = (REF / "DOCS_REGISTRY.md").read_text(encoding="utf-8")
    assert _sheet_section(registry, "installed"), "## installed vanished: B7 is vacuous"
    assert angular_sheet_faults(sheet, registry) == []


@pytest.mark.parametrize("name, mutate, fault", [
    ("B1", lambda s, r: (s.replace("`.agents/ref/CONVENTIONS_typescript.md`", "the base sheet"), r),
     "the sheet no longer layers on CONVENTIONS_typescript.md"),
    ("B2", lambda s, r: (re.sub(r"(?s)(## Package manager\n).*?(\n## )", r"\1\n- Use npm.\n\2", s), r),
     "package manager fixed to npm"),
    ("B3", lambda s, r: (s.replace("- `@angular/build:karma`", "- Always use Vitest; `@angular/build:karma`"), r),
     "Vitest imposed whatever the declared runner"),
    ("B4", lambda s, r: (s.replace("only if `angular.json` declares a `lint` target for the\n  project", "always"), r),
     "ng lint is not conditioned on a declared lint target"),
    ("B5", lambda s, r: (s, re.sub(r"(?m)^conventions: \.agents/ref/CONVENTIONS_angular\.md.*\n", "", r)),
     "registry ## angular does not route to the sheet"),
    ("B6", lambda s, r: (s, r.replace(f"pin={ANGULAR_PIN}", "pin=main").replace(f"sha256={ANGULAR_SHA256}", "")),
     "registry ## angular lost the audited pin"),
    ("B7", lambda s, r: (s, r.replace("(none yet — run /skills-sync | $skills-sync)",
                                      f"- angular/skills#angular-developer   hash={ANGULAR_SHA256[:12]}")),
     "the upstream Angular skill is listed under ## installed"),
    ("B8", lambda s, r: (s.replace("`npm run ng -- test --watch=false`", "`npm run ng test --watch=false`"), r),
     "npm flags not passed after `--`"),
    ("B9", lambda s, r: (re.sub(r"(?s)(## Package manager\n\n)(.*?\n)(- Then read the `packageManager`[^\n]*\n)",
                                r"\1\3\2", s), r),
     "package manager sources out of order: lockfile < packageManager < cli.packageManager"),
    ("B10", lambda s, r: (s.replace("The detector reads neither `bun.lock` nor `cli.packageManager`",
                                    "The detector reads `bun.lock` and `cli.packageManager`"), r),
     "bun.lock or cli.packageManager attributed to the detector"),
    ("B11", lambda s, r: (s.replace("`bun.lockb` > `pnpm-lock.yaml`", "`pnpm-lock.yaml` > `bun.lockb`"), r),
     "the detector's lockfile precedence is missing"),
    ("B12", lambda s, r: (s.replace("in v20 `runner` is required", "in v20 Karma is the default"), r),
     "default runner per major not stated (v21 Vitest, v20 required)"),
    ("B13", lambda s, r: (s.replace(" --browsers=ChromeHeadless", ""), r),
     "test runner not read from angular.json: --no-watch --no-progress --browsers=ChromeHeadless missing"),
])
def test_angular_sheet_mutants_are_red(name, mutate, fault):
    """B1–B7: each mutant flips exactly the fault it targets, on the real files."""
    sheet = (REF / "CONVENTIONS_angular.md").read_text(encoding="utf-8")
    registry = (REF / "DOCS_REGISTRY.md").read_text(encoding="utf-8")
    mutant_sheet, mutant_registry = mutate(sheet, registry)
    assert (mutant_sheet, mutant_registry) != (sheet, registry), f"{name} mutated nothing"
    assert fault in angular_sheet_faults(mutant_sheet, mutant_registry), name


def test_the_agents_router_carries_the_shell_rule():
    """DÉCOUVERTE. Une feuille que personne n'ouvre est une feuille qui n'existe
    pas. `AGENTS.md` est la surface que les six hôtes lisent à CHAQUE session et
    qui VOYAGE chez les adoptants — c'est là que la règle doit être nommée, avec
    le pointeur vers la feuille."""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "CONVENTIONS_shell.md" in text, "AGENTS.md ne route vers aucune feuille shell"
    assert "test_no_compact_case.py" in text, "AGENTS.md ne nomme pas le filet qui refuse"


def test_the_typescript_sheet_routes_to_the_nextjs_one():
    """DISCOVERY WIRING, and the reason it is one line and not four agent-sheet
    edits: an agent that opens the TypeScript conventions on a Next project must
    be TOLD there is a framework layer. Without this line the new file exists and
    nobody reaches it — a documentation defect that looks exactly like a fixed
    one."""
    text = (REF / "CONVENTIONS_typescript.md").read_text(encoding="utf-8")
    assert "CONVENTIONS_nextjs.md" in text


def test_template_exclude_carries_no_rule_over_the_ref_directory():
    """`.agents/ref/` must stay TAKE(overwrite) kit-side: that is how the §1
    canonical rules travel main -> template.

    A `strip:` here would read like protection and do the opposite — it would
    freeze every adopting project on the convention text of the day it forked.
    The absence is therefore a CHOICE, commented in the file, and pinned here so
    that adding a rule requires facing this test.
    """
    text = (ROOT / ".template-exclude").read_text(encoding="utf-8")
    rules = [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^\s*(strip|keep|own)\s*:", line)
    ]
    offending = [r for r in rules if ".agents/ref" in r]
    assert not offending, (
        "a sync rule now covers .agents/ref/: " + "; ".join(offending) +
        " — see the comment in .template-exclude before changing this"
    )
    # NON-VACUITY of the scan itself: the file really does carry rules, so an
    # empty `rules` list would mean the parser broke, not that the repo is clean.
    assert rules, ".template-exclude parsed to zero rules — the scan is broken"


# ---------------------------------------------------------------------------
# THE `conventions_file` FIELD OF `language-detector` (T-00000436)
# ---------------------------------------------------------------------------
# THE DEFECT WAS NEVER THE DEAD PATH, IT WAS THE SILENCE. A detector that names a
# convention sheet for a stack that has none hands the dev agent a path it cannot
# read; the dev agent falls back on its own habits and says nothing at all. The
# field itself stays, because four sheets DO exist and are canonical — and one of
# them, the Next.js one, is reachable by no other route than the wiring pinned by
# `test_the_typescript_sheet_routes_to_the_nextjs_one` above. What changes is that
# the pointer is emitted only when the sheet exists, that its absence is spelled
# out rather than faked, and that the consumer DECLARES the fallback it takes.
#
# EACH ARM'S UNIVERSE IS WRITTEN OUT BY HAND, AND THAT IS THE POINT. Deriving it
# from "every agent def that mentions conventions_file" would sweep the three
# `dev-mono` defs — which carry the CONSUMPTION anchor and none of the emission
# ones — into the emission arm, and the suite would fail on three files that are
# perfectly correct. A hand-written list is the narrower claim, so each list gets
# a non-vacuity arm below: a path that vanished would otherwise make its arm pass
# by measuring nothing.

# The three anchors, written here EXACTLY as they must appear in the defs: the
# word null bare, with no backticks and no bold. The prose that specifies this
# rule elsewhere naturally writes the word as inline code, and a def that copied
# that markup would satisfy a human reader while failing every machine that looks
# for the field's contract. Pinning the bare form is what keeps the two in step.
EMISSION_CONDITION = "only when the sheet EXISTS on disk"
EMISSION_FALLBACK = "emit null and name the stack skill"
CONSUMPTION_FALLBACK = "null means no sheet exists"

# The template that pointed at a file which, for most stacks, does not exist.
DEAD_TEMPLATE = "CONVENTIONS_<stack>.md"

# Five emitters: Copilot now names conventions_file and carries the same
# existence and fallback rule as the other four hosts.
DETECTOR_EMITTERS = [
    ".claude/agents/language-detector.md",
    ".gemini/agents/language-detector.md",
    ".kimi-code/agents/language-detector.md",
    ".codex/agents/language-detector.toml",
    ".github/agents/language-detector.agent.md",
]
DETECTOR_DEFS = DETECTOR_EMITTERS

# THE CONSUMERS ARE `dev-mono` ALONE, on its three hosts. `dev-multi` names the
# field on no host at all — it receives the language JSON through the same
# contract but never reaches for this key.
CONVENTIONS_CONSUMERS = [
    ".claude/agents/dev-mono.md",
    ".gemini/agents/dev-mono.md",
    ".kimi-code/agents/dev-mono.md",
]

CODEX_DETECTOR = ".codex/agents/language-detector.toml"


@pytest.mark.parametrize("rel", DETECTOR_EMITTERS)
def test_A1_an_emitter_conditions_the_pointer_on_the_sheet_existing(rel: str):
    """A1 — EMISSION. Every def that emits `conventions_file` must say both halves
    of the rule: when to emit a path, and what to emit instead when there is no
    path to emit. Half the rule is worse than none, because a def that says only
    "check first" leaves the agent to invent the other branch."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    for anchor in (EMISSION_CONDITION, EMISSION_FALLBACK):
        assert anchor in text, (
            f"{rel} never says `{anchor}` — the emission rule is missing or was "
            "paraphrased. The anchor is a literal on purpose: a host that "
            "rewords it drifts from the other three in silence"
        )


@pytest.mark.parametrize("rel", DETECTOR_EMITTERS)
def test_A1n_each_named_emitter_exists_and_really_emits_the_field(rel: str):
    """NON-VACUITY OF A1. Two empty sets agree: if one of these defs were renamed
    or stopped emitting the field, A1 above would keep passing over a file whose
    subject had disappeared."""
    path = ROOT / rel
    assert path.exists(), f"{rel} is named by A1 but does not exist"
    assert "conventions_file" in path.read_text(encoding="utf-8"), (
        f"{rel} no longer emits `conventions_file` — A1 is now guarding a rule "
        "about a field this def does not have. Re-establish the list"
    )


@pytest.mark.parametrize("rel", DETECTOR_DEFS)
def test_A2_no_detector_def_still_carries_the_dead_template(rel: str):
    """A2 — THE DEAD TEMPLATE. The literal placeholder is a path no repository
    ever has on disk, so shipping it as the field's value guarantees the failed
    read it was meant to describe."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert DEAD_TEMPLATE not in text, (
        f"{rel} still carries the literal `{DEAD_TEMPLATE}` — that is a path that "
        "exists in no tree. Emit a sheet that exists, or null"
    )


@pytest.mark.parametrize("rel", DETECTOR_DEFS)
def test_A2n_each_detector_def_exists_and_is_not_empty(rel: str):
    """NON-VACUITY OF A2. An absence is the easiest assertion in the world to
    satisfy by accident — a missing or emptied file proves nothing at all."""
    path = ROOT / rel
    assert path.exists(), f"{rel} is named by A2 but does not exist"
    assert path.read_text(encoding="utf-8").strip(), f"{rel} is empty"


@pytest.mark.parametrize("rel", CONVENTIONS_CONSUMERS)
def test_A3_the_consumer_says_out_loud_what_an_absent_sheet_means(rel: str):
    """A3 — CONSUMPTION, and the arm that closes the actual defect. Making the
    emitter honest stops the failed read; it does NOT stop the silent fallback.
    The consumer has to name what it does when no sheet exists, and declare it."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert CONSUMPTION_FALLBACK in text, (
        f"{rel} never says `{CONSUMPTION_FALLBACK}` — it takes the field when "
        "present and stays silent otherwise, which is the silence this contract "
        "exists to remove"
    )


@pytest.mark.parametrize("rel", CONVENTIONS_CONSUMERS)
def test_A3n_each_named_consumer_exists_and_really_reads_the_field(rel: str):
    """NON-VACUITY OF A3, same reasoning as A1n on the other side of the wire."""
    path = ROOT / rel
    assert path.exists(), f"{rel} is named by A3 but does not exist"
    assert "conventions_file" in path.read_text(encoding="utf-8"), (
        f"{rel} no longer reads `conventions_file` — A3 guards a fallback for a "
        "field this def never receives"
    )


def test_A4_the_codex_detector_parses_as_toml_and_carries_the_rule():
    """A4 — THE FRAGILE STRING, AND A HOLE CLOSED AT THE MOMENT WE WALK THROUGH IT.
    The Codex def keeps its whole prompt inside one TOML multi-line basic string,
    where a stray backslash is an escape and a line ending in a double quote runs
    into the terminator. No suite in this repo parses that file — the one that
    reads it takes the raw bytes — so a broken escape would land green and the
    host would fail at load time instead. Editing that string is exactly when the
    parse becomes worth asserting."""
    instructions = _codex_prompt()["developer_instructions"]
    for anchor in (EMISSION_CONDITION, EMISSION_FALLBACK):
        assert anchor in instructions, (
            f"{CODEX_DETECTOR} parses, but its prompt never says `{anchor}`"
        )


def test_A4n_the_codex_prompt_key_is_present_and_not_empty():
    """NON-VACUITY OF A4, and the reason A4 subscripts instead of using
    `.get(..., "")`. With a default, a renamed or vanished key would yield an
    empty string, A4 would fail on its anchors, and the message would send the
    reader hunting for missing prose when the real breakage is structural. The
    subscript raises where the fault is; this arm names the same fault first."""
    doc = _codex_prompt()
    assert "developer_instructions" in doc, (
        f"{CODEX_DETECTOR} no longer has a `developer_instructions` key — the "
        "prompt moved, and A4 would be asserting anchors against nothing"
    )
    assert doc["developer_instructions"].strip(), (
        f"{CODEX_DETECTOR} carries an empty `developer_instructions`"
    )


def _codex_prompt() -> dict:
    return tomllib.loads((ROOT / CODEX_DETECTOR).read_text(encoding="utf-8"))
