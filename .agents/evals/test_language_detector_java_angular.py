"""Java/Angular detector contract and replay ledger for the five host definitions.

The three upstream files in tree.json are the dated start.spring.io bytes,
pinned in DATED_SOURCES. observed.json is filled only from actual host runs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import tomllib
import unittest
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TREE = FIXTURES / "detector_spring_angular.tree.json"
OBSERVED = FIXTURES / "detector_spring_angular.observed.json"
DEFS = {
    "claude": ".claude/agents/language-detector.md",
    "gemini": ".gemini/agents/language-detector.md",
    "kimi": ".kimi-code/agents/language-detector.md",
    "codex": ".codex/agents/language-detector.toml",
    "copilot": ".github/agents/language-detector.agent.md",
}
HOSTS = ("claude", "codex")
# model / effort pinned by each replayed definition (.claude frontmatter,
# .codex model + model_reasoning_effort).
# Codex medium: pilot decision S-01M5KNFS6N (same model), after three passes
# at low left Codex cases under the 2/3 majority.
PINS = {"claude": ("haiku", "low"), "codex": ("gpt-6-luna", "medium")}
DRAWS = 3
MAJORITY = 2
VARIANTS = (
    "base", "gradle", "starter-test-runner-karma", "sans-runner",
    "karma-sans-lock", "angular20-sans-runner", "angularjs", "angular19",
)
SOURCE_PATHS = {
    "pom-web": ("base", "backend/pom.xml"),
    "pom-bare": ("starter-test-runner-karma", "backend/pom.xml"),
    # starter.zip baseDir=demo makes demo/ the project root: its build.gradle.kts
    # sits beside gradlew, so the fixture maps demo/ onto the backend module root.
    "gradle-kts": ("gradle", "backend/build.gradle.kts"),
}
# C18: upstream sha256 measured on 2026-10-21 by the planner (two identical
# pulls each) and re-pulled unchanged on 2026-10-22 for the fixture bytes.
# Any change carries a date and a reason in the same commit.
DATED_SOURCES = {
    "pom-web": "a7e7cacb296072ef1412029fd57019a8fbdbf7c7c721810d3401a5ebe2c9d7a3",
    "pom-bare": "be07080c22229e92514bb0d3dad09d9028adf3289e86335842369e2dafde84c3",
    "gradle-kts": "3384bac8d3a2ad1357ebe466e19a9970746d0accab45813ca0ccd1e87f79a199",
}
EXPECTED = {
    "base": (("maven", "junit"), ("npm", "vitest")),
    "gradle": (("gradle", "junit"), ("npm", "vitest")),
    "starter-test-runner-karma": (("maven", "junit"), ("npm", "karma")),
    "sans-runner": (("maven", "unknown"), ("npm", "vitest")),
    "karma-sans-lock": (("maven", "junit"), ("unknown", "karma")),
    "angular20-sans-runner": (("maven", "junit"), ("npm", "unknown")),
    "angularjs": (("maven", "junit"), ("unknown", "unknown")),
    "angular19": (("maven", "junit"), ("unknown", "karma")),
}
JAVA_RULE = (
    "Java test runner is junit only when the manifest declares spring-boot-starter-test, "
    "a spring-boot-starter-*-test artifact, org.junit.jupiter, or org.junit.platform; "
    "otherwise unknown."
)
JAVA_EXAMPLE = (
    "Example: spring-boot-starter-webmvc-test, spring-boot-starter-data-jpa-test and "
    "spring-boot-starter-security-test each match spring-boot-starter-*-test, so each "
    "one means junit."
)
MODULES_RULE = (
    "modules[] is mandatory whenever two or more manifest roots exist, for example "
    "frontend/package.json and backend/pom.xml: emit one entry per root, even for a "
    "module whose framework stays unknown, and never omit the array."
)
ROOTS_RULE = (
    "Before stopping, Glob every manifest name across the whole scope, subdirectories "
    "included (for example **/package.json, **/pom.xml and **/build.gradle.kts): each "
    "directory holding a manifest is a manifest root, and the stop applies per root, "
    "never to the whole scope."
)
EXCLUDED_ROOTS_RULE = (
    "Never count a manifest under node_modules/, .git/, target/, build/, dist/, out/, "
    "vendor/, .venv/, venv/, .gradle/, .claude/worktrees/ or any git-ignored "
    "directory as a manifest root."
)
ROOT_MODULE_RULE = 'A manifest at the repository root is the module `path: "."`.'
# Measured cause (angular19/claude, 2 draws of 3 on 97de609c1): signals_used held
# frontend/ only, the backend pom.xml was never globbed, modules[] absent.
ALL_ROOTS_RULE = (
    "Run that Glob FIRST, before you read any manifest. A repository with a manifest "
    "in two or more directories ALWAYS emits modules[], one entry per root, and its "
    "signals_used names a manifest of every root — never a single-root answer built "
    "from the first manifest you read."
)
# Measured on ea41e44cc: codex emitted `modules: []` (angularjs, draw 2) and
# dropped modules[] on angular20/angular19; the root AngularJS confidence slipped.
MODULES_NEVER_EMPTY_RULE = (
    "When manifests live under two or more roots, modules is NEVER empty and NEVER "
    "absent: one entry per root."
)
ANGULARJS_OUTPUT_RULE = (
    'AngularJS exact output: the ROOT object carries "confidence": "low" and '
    '"route_to": "ask", whatever the other modules say, and the AngularJS module '
    'carries "framework": "unknown", "confidence": "low" and "conventions_file": null '
    "unless a JavaScript sheet exists. Example, frontend AngularJS beside backend "
    'Spring Boot: {"confidence": "low", "route_to": "ask", "modules": [{"path": '
    '"backend", "framework": "spring-boot@4"}, {"path": "frontend", "framework": '
    '"unknown", "confidence": "low", "conventions_file": null}]}'
)
# The two defs that carry the multi-module JSON example (.gemini, .codex and
# .github have none): its backend entry must name the Java sheet (F3).
JAVA_EXAMPLE_DEFS = ("claude", "kimi")
JAVA_EXAMPLE_RE = re.compile(r'\{"path": "backend", "primary_language": "java",(.*?)\}', re.S)
SHEET_EXAMPLE = (
    "Example: an Angular module written in TypeScript, with no Angular sheet on disk, "
    "takes .agents/ref/CONVENTIONS_typescript.md when that file exists."
)
# S-01M5KHFD58 — measured on 8281891 (48 draws): 4 draws named the TypeScript
# sheet for an Angular frontend although CONVENTIONS_angular.md existed, and the
# multi-module example of two defs taught exactly that; 2 Codex draws dropped
# modules[]. Both sentences sit right after SHEET_EXAMPLE, at the output point.
FRAMEWORK_SHEET_EXAMPLE = (
    '{"path": "frontend", "primary_language": "typescript", "framework": "angular@22", '
    '"conventions_file": ".agents/ref/CONVENTIONS_angular.md", '
    '"registry_sections": ["typescript", "angular"]}'
)
FRAMEWORK_SHEET_RULE = (
    "When .agents/ref/CONVENTIONS_<framework>.md exists for the framework of a module, "
    "for example angular or nextjs, that sheet IS the conventions_file of that module, "
    "never the base language sheet. Exact output for an Angular frontend when "
    ".agents/ref/CONVENTIONS_angular.md exists: " + FRAMEWORK_SHEET_EXAMPLE
)
OUTPUT_MODULES_CHECK = (
    "Last check before you output: with manifests under two or more roots, the JSON "
    "carries a modules[] array with one entry per root; an answer without it is "
    "incomplete, so add the array before you answer."
)
# Measured on 2b7f94b77: the 4 failing Codex draws emitted `"modules": []`, the
# literal value of the Codex schema template. An empty modules value in a host
# template must carry this note, which bounds it to an all-root repository.
EMPTY_MODULES = '"modules": []'
EMPTY_MODULES_NOTE = '"modules": [] only when every manifest lives at the repository root'


def _bare_empty_modules(body: str) -> int:
    """Occurrences of an empty modules value NOT carried by the bounding note."""
    return body.count(EMPTY_MODULES) - body.count(EMPTY_MODULES_NOTE)


# A JSON example value that hands a framework module the base language sheet.
BASE_SHEET_EXAMPLE = '"conventions_file": ".agents/ref/CONVENTIONS_typescript.md"'
ANGULAR_RULE = (
    "Angular test runner: @angular/build:unit-test uses options.runner when set; when "
    "absent, use vitest for @angular/core major 21 or newer and unknown for 20. "
    "@angular/build:karma and @angular-devkit/build-angular:karma use karma; otherwise "
    "unknown. Read the builder in angular.json and the core version in package.json."
)
RULES = (
    JAVA_RULE,
    JAVA_EXAMPLE,
    MODULES_RULE,
    ROOTS_RULE,
    SHEET_EXAMPLE,
    ANGULAR_RULE,
    "mvnw",
    "gradlew",
    "repository-relative paths",
    "packageManager",
    "modules[]",
    "test_runner",
    "conventions_file",
    "registry_sections",
    "typescript",
)
SHEETS = (
    ".agents/ref/CONVENTIONS_java.md",
    ".agents/ref/CONVENTIONS_angular.md",
    ".agents/ref/CONVENTIONS_typescript.md",
)
JAVASCRIPT_SHEET = ".agents/ref/CONVENTIONS_javascript.md"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
# An absolute path starts with a slash glued to its first segment: a slash
# followed by a blank (the registry title `java / kotlin`) is prose, not a path.
MACHINE_PATH_RE = re.compile(
    r"(?:^|[\s=\"'])(?:/(?!\s)|~[/\\]|[A-Za-z]:[/\\])"
    r"|(?:^|[\s=\"'])(?:-C|--cd)(?:=)?(?:/|~[/\\]|[A-Za-z]:[/\\])"
    r"|file:///|(?:^|[/\\])\.\.(?:[/\\]|$)"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _prompt(relative: str) -> str:
    body = (ROOT / relative).read_text(encoding="utf-8")
    if relative.endswith(".toml"):
        return tomllib.loads(body)["developer_instructions"]
    return body


def _missing_rules(body: str) -> list[str]:
    return [rule for rule in RULES if rule not in body]


def _machine_hits(value: Any) -> list[str]:
    """Check keys and values, including paths hidden after command options."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            hits.extend(_machine_hits(key))
            hits.extend(_machine_hits(item))
    elif isinstance(value, list):
        for item in value:
            hits.extend(_machine_hits(item))
    elif isinstance(value, str):
        if "-Users-" in value or "/tmp/" in value or MACHINE_PATH_RE.search(value):
            hits.append(value)
    return hits


def _fixture_faults(tree: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    variants = tree.get("variants", {})
    if tuple(variants) != VARIANTS or set(tree.get("expect", {})) != set(VARIANTS):
        faults.append("eight named variants and expectations required")
    for name, files in variants.items():
        if not isinstance(files, dict) or "frontend/package.json" not in files:
            faults.append(f"{name}: frontend manifest absent")
            continue
        if not any(path in files for path in ("backend/pom.xml", "backend/build.gradle.kts")):
            faults.append(f"{name}: backend manifest absent")
        for path in files:
            if path.startswith("/") or ".." in Path(path).parts:
                faults.append(f"{name}: non-relative file path {path}")
        if name not in EXPECTED:
            continue
        expected = tree["expect"].get(name, {})
        if (tuple(expected.get("backend", ())), tuple(expected.get("frontend", ()))) != EXPECTED[name]:
            faults.append(f"{name}: expected result drifted")
        package = json.loads(files["frontend/package.json"])
        dependencies = package.get("dependencies", {})
        angular = files.get("frontend/angular.json")
        builder = None
        runner = None
        if angular is not None:
            test = json.loads(angular)["projects"]["app"]["architect"]["test"]
            builder = test["builder"]
            runner = test.get("options", {}).get("runner")
        if name == "base" and (runner is not None or builder != "@angular/build:unit-test"):
            faults.append("base: must represent ng new unit-test without runner")
        if name == "starter-test-runner-karma" and runner != "karma":
            faults.append("starter-test-runner-karma: explicit karma runner absent")
        if name == "sans-runner" and "-test" in files["backend/pom.xml"]:
            faults.append("sans-runner: test dependency remains")
        if name == "karma-sans-lock" and (
            builder != "@angular/build:karma" or "frontend/package-lock.json" in files
            or "packageManager" in package
        ):
            faults.append("karma-sans-lock: fixture still has a lock or wrong builder")
        if name == "angular20-sans-runner" and (
            not dependencies.get("@angular/core", "").startswith("^20") or runner is not None
        ):
            faults.append("angular20-sans-runner: version or runner drifted")
        if name == "angularjs" and (
            "@angular/core" in dependencies or "angular" not in dependencies
        ):
            faults.append("angularjs: AngularJS marker drifted")
        if name == "angular19" and (
            not dependencies.get("@angular/core", "").startswith("^19")
            or builder != "@angular-devkit/build-angular:karma"
        ):
            faults.append("angular19: version or karma builder drifted")
        if name == "gradle" and (
            "backend/build.gradle.kts" not in files or "backend/gradlew" not in files
        ):
            faults.append("gradle: starter Gradle tree absent")
    return faults


def _source_faults(tree: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    sources = {source["id"]: source for source in tree["sources"]}
    if set(sources) != set(SOURCE_PATHS):
        faults.append("three pinned source identities required")
        return faults
    for source_id, (variant, path) in SOURCE_PATHS.items():
        content = tree["variants"][variant][path].encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        if digest != sources[source_id]["sha256"]:
            faults.append(f"{source_id}: sha differs from pinned content")
        if digest != DATED_SOURCES[source_id]:
            faults.append(f"{source_id}: dated source bytes absent")
    return faults


def _provenance_faults(record: dict[str, Any], kit: bool) -> list[str]:
    """Absolute on EVERY draw, never voted: a draw from the wrong host, model,
    effort or definition, without its command, or degraded, is not a replay of
    the delivered detector, whatever the other draws of its case say."""
    faults: list[str] = []
    name = record.get("variant")
    host = record.get("host")
    if name not in VARIANTS or host not in HOSTS:
        return ["unknown variant or host"]
    if record.get("degraded"):
        faults.append(f"{host} replay cannot be degraded")
    if (record.get("model"), record.get("effort")) != PINS[host]:
        faults.append(f"{host} replay must use {PINS[host][0]}/{PINS[host][1]}")
    if not isinstance(record.get("command"), str) or not record["command"].strip():
        faults.append("command missing")
    elif f"fixture-{name}-{host}" not in record["command"]:
        faults.append("command does not name its relative fixture")
    if not COMMIT_RE.fullmatch(str(record.get("base_sha", ""))):
        faults.append("base_sha missing")
    if not SHA256_RE.fullmatch(str(record.get("def_sha256", ""))):
        faults.append("def_sha256 missing")
    elif kit:
        digest = hashlib.sha256((ROOT / DEFS[host]).read_bytes()).hexdigest()
        if record["def_sha256"] != digest:
            faults.append("definition sha is stale")
    present = sorted(sheet for sheet in SHEETS if (ROOT / sheet).is_file())
    if sorted(record.get("sheets_present", [])) != present:
        faults.append("sheets_present is stale")
    if _machine_hits(record):
        faults.append("machine path in observed record")
    return faults


def _record_faults(record: dict[str, Any], tree: dict[str, Any], kit: bool) -> list[str]:
    provenance = _provenance_faults(record, kit)
    if provenance:
        return provenance
    return _detection_faults(record, tree)


def _detection_faults(record: dict[str, Any], tree: dict[str, Any]) -> list[str]:
    """The detection RESULT only: the one part a majority of draws may carry."""
    faults: list[str] = []
    name = record["variant"]
    expected = tree["expect"][name]
    actual = record.get("json")
    if not isinstance(actual, dict):
        return ["JSON output missing"]
    modules = actual.get("modules")
    if not isinstance(modules, list):
        return ["modules[] missing"]
    by_path = {item.get("path"): item for item in modules if isinstance(item, dict)}
    for path in ("backend", "frontend"):
        module = by_path.get(path)
        if module is None:
            faults.append(f"{path}: module missing")
            continue
        for key, value in zip(("package_manager", "test_runner"), expected[path]):
            if module.get(key) != value:
                faults.append(f"{path}: {key} expected {value}, got {module.get(key)}")
        if not isinstance(module.get("registry_sections"), list):
            faults.append(f"{path}: registry_sections missing")
        # Framework sheet, then language sheet, else null (AGENTS.md § Language
        # routing). AngularJS is plain JavaScript with no Angular framework, so
        # neither the Angular nor the TypeScript sheet applies to it.
        if path == "backend":
            candidates: tuple[str, ...] = SHEETS[0:1]
        elif name == "angularjs":
            candidates = (JAVASCRIPT_SHEET,)
        else:
            candidates = (SHEETS[1], SHEETS[2])
        expected_sheet = next((sheet for sheet in candidates if (ROOT / sheet).is_file()), None)
        if module.get("conventions_file") != expected_sheet:
            faults.append(f"{path}: conventions_file expected {expected_sheet}")
    front = by_path.get("frontend", {})
    # modules[] entries carry no confidence field: the root one rules unless
    # the module states its own.
    front_confidence = front.get("confidence", actual.get("confidence"))
    if name == "angularjs" and (
        front.get("framework") != "unknown" or front_confidence != "low"
        or actual.get("route_to") != "ask"
    ):
        faults.append("AngularJS must stay unknown and low")
    if name == "angular19" and front_confidence == "high":
        faults.append("Angular 19 confidence cannot be high")
    return faults


def _majority_faults(
    records: list[dict[str, Any]],
    judge: Callable[[dict[str, Any]], list[str]],
    provenance: Callable[[dict[str, Any]], list[str]] = lambda record: [],
) -> tuple[list[str], dict[tuple[str, str], int]]:
    """Orchestrator decision S-01M5JSK35V: each case and host is judged on
    DRAWS real draws and passes with at least MAJORITY conforming ones.
    Only the detection result is voted: `provenance` faults are absolute and
    fail the case on any single draw."""
    faults: list[str] = []
    expected = {(v, h, d) for v in VARIANTS for h in HOSTS for d in range(1, DRAWS + 1)}
    seen = [(r.get("variant"), r.get("host"), r.get("draw")) for r in records]
    if len(seen) != len(expected) or set(seen) != expected:
        faults.append(f"{len(expected)} actual host replays required, one per case, host and draw")
    rates: dict[tuple[str, str], int] = {(v, h): 0 for v in VARIANTS for h in HOSTS}
    for record in records:
        for fault in provenance(record):
            faults.append(
                f"{record.get('variant')}/{record.get('host')} draw {record.get('draw')}: {fault}"
            )
    for record in records:
        key = (record.get("variant"), record.get("host"))
        if key in rates and not judge(record):
            rates[key] += 1
    for (variant, host), good in rates.items():
        if good < MAJORITY:
            faults.append(f"{variant}/{host}: {good}/{DRAWS} draws conform, {MAJORITY} required")
    return faults, rates


def _observed_faults(
    records: list[dict[str, Any]], tree: dict[str, Any], kit: bool
) -> tuple[list[str], dict[tuple[str, str], int]]:
    """Provenance on every draw, then the vote on the detection result of the
    draws whose provenance holds."""
    return _majority_faults(
        records,
        lambda record: _record_faults(record, tree, kit),
        lambda record: _provenance_faults(record, kit),
    )


class LanguageDetectorJavaAngularTests(unittest.TestCase):
    def test_D_ignored_manifest_roots_are_excluded_on_five_hosts(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(ROOTS_RULE + "\n" + EXCLUDED_ROOTS_RULE, _prompt(relative))

    def test_D_repository_root_module_is_named_on_five_hosts(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(EXCLUDED_ROOTS_RULE + "\n" + ROOT_MODULE_RULE, _prompt(relative))

    def test_D_every_root_is_globbed_first_on_five_hosts(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(ROOT_MODULE_RULE + "\n" + ALL_ROOTS_RULE, _prompt(relative))

    def test_D_modules_never_empty_on_five_hosts(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(ALL_ROOTS_RULE + "\n" + MODULES_NEVER_EMPTY_RULE, _prompt(relative))

    def test_D_angularjs_exact_output_on_five_hosts_and_its_example_passes_the_judge(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(ANGULARJS_OUTPUT_RULE, _prompt(relative))
        example = json.loads(ANGULARJS_OUTPUT_RULE[ANGULARJS_OUTPUT_RULE.index("{"):])
        front = next(m for m in example["modules"] if m["path"] == "frontend")
        self.assertEqual(
            (example["confidence"], example["route_to"], front["framework"], front["confidence"]),
            ("low", "ask", "unknown", "low"),
        )
        self.assertFalse((ROOT / JAVASCRIPT_SHEET).is_file() and front["conventions_file"] is None)

    def test_D_framework_sheet_and_output_check_on_five_hosts(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertIn(
                    SHEET_EXAMPLE + " " + FRAMEWORK_SHEET_RULE + " " + OUTPUT_MODULES_CHECK,
                    _prompt(relative),
                )

    def test_D_framework_sheet_example_parses_and_names_an_existing_sheet(self) -> None:
        example = json.loads(FRAMEWORK_SHEET_EXAMPLE)
        self.assertEqual(example["conventions_file"], SHEETS[1])
        self.assertTrue((ROOT / SHEETS[1]).is_file())
        self.assertTrue(example["framework"].startswith("angular@"))

    def test_D_no_json_example_hands_a_framework_module_the_base_sheet(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertNotIn(BASE_SHEET_EXAMPLE, _prompt(relative))

    def test_D_mutants_framework_sheet_and_output_check_are_red(self) -> None:
        anchored = SHEET_EXAMPLE + " " + FRAMEWORK_SHEET_RULE + " " + OUTPUT_MODULES_CHECK
        cases = (
            ("codex", "never the base language sheet", ""),
            ("gemini", FRAMEWORK_SHEET_EXAMPLE, FRAMEWORK_SHEET_EXAMPLE.replace(SHEETS[1], SHEETS[2])),
            ("copilot", OUTPUT_MODULES_CHECK, ""),
        )
        for host, old, new in cases:
            with self.subTest(host=host, removed=old[:40]):
                body = _prompt(DEFS[host])
                self.assertIn(anchored, body)
                self.assertNotIn(anchored, body.replace(old, new, 1))
        kimi = _prompt(DEFS["kimi"])
        mutant = kimi.replace(
            '"conventions_file": "' + SHEETS[1] + '",\n', BASE_SHEET_EXAMPLE + ",\n", 1
        )
        self.assertNotEqual(kimi, mutant, "the kimi Angular example moved")
        self.assertIn(BASE_SHEET_EXAMPLE, mutant, "the kimi base-sheet mutant is not caught")

    def test_D_no_host_template_carries_a_bare_empty_modules(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertEqual(_bare_empty_modules(_prompt(relative)), 0)
        # NON-VACUITY: the host whose template was measured carries the note.
        self.assertIn(EMPTY_MODULES_NOTE, _prompt(DEFS["codex"]))

    def test_D_mutant_codex_template_back_to_empty_modules_is_red(self) -> None:
        raw = (ROOT / DEFS["codex"]).read_text(encoding="utf-8")
        start = raw.index('  "modules": [\n')
        end = raw.index("\n  ]\n}", start) + len("\n  ]")
        mutant = raw[:start] + '  "modules": []' + raw[end:]
        body = tomllib.loads(mutant)["developer_instructions"]
        self.assertEqual(_bare_empty_modules(body), 1)
        noteless = tomllib.loads(raw.replace(EMPTY_MODULES_NOTE, "modules may be empty", 1))
        self.assertEqual(_bare_empty_modules(noteless["developer_instructions"]), 0,
                         "removing the note alone leaves no bare value: the template entry holds")
        self.assertNotIn(EMPTY_MODULES_NOTE, noteless["developer_instructions"])

    def test_D_java_example_names_the_java_sheet(self) -> None:
        self.assertTrue((ROOT / SHEETS[0]).is_file())
        for host in JAVA_EXAMPLE_DEFS:
            with self.subTest(host=host):
                found = JAVA_EXAMPLE_RE.findall(_prompt(DEFS[host]))
                self.assertEqual(len(found), 1, "one Java backend example expected")
                self.assertIn(f'"conventions_file": "{SHEETS[0]}"', found[0])

    def test_mutant_gate_reddens_once_per_new_witness(self) -> None:
        """Run with DETECTOR_MUTANT=D|U|F|O|V|P and -k test_mutant_gate.

        Each mode starts from the same positive predicate as its witness and
        deliberately asserts that the altered input remains valid. A red run
        demonstrates that the corresponding predicate can reject the fault.
        """
        mode = os.environ.get("DETECTOR_MUTANT", "")
        if not mode:
            return
        if mode == "D":
            body = _prompt(DEFS["gemini"]).replace("spring-boot-starter-*-test", "", 1)
            self.assertEqual(_missing_rules(body), [])
        elif mode == "U":
            tree = _load_json(TREE)
            tree["variants"]["base"]["backend/pom.xml"] += "x"
            self.assertEqual(_source_faults(tree), [])
        elif mode == "F":
            tree = _load_json(TREE)
            del tree["variants"]["base"]["backend/pom.xml"]
            self.assertEqual(_fixture_faults(tree), [])
        elif mode == "O":
            tree = _load_json(TREE)
            record = {
                "variant": "base", "host": "claude", "model": "haiku", "effort": "low",
                "command": "claude -p --agent language-detector fixture-base-claude",
                "base_sha": "a" * 40,
                "def_sha256": hashlib.sha256((ROOT / DEFS["claude"]).read_bytes()).hexdigest(),
                "sheets_present": sorted(s for s in SHEETS if (ROOT / s).is_file()),
                "json": {"modules": [
                    {"path": "backend", "package_manager": "gradle", "test_runner": "junit",
                     "registry_sections": ["java", "spring-boot"],
                     "conventions_file": next((s for s in SHEETS[0:1] if (ROOT / s).is_file()), None)},
                    {"path": "frontend", "package_manager": "npm", "test_runner": "vitest",
                     "registry_sections": ["typescript", "angular"],
                     "conventions_file": next((s for s in SHEETS[1:] if (ROOT / s).is_file()), None)},
                ]},
            }
            self.assertEqual(_record_faults(record, tree, True), [])
        elif mode == "V":
            path = ROOT / ".agents/bin/sync_template.py"
            spec = importlib.util.spec_from_file_location("sync_template_detector_mutant", path)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            text = (ROOT / ".template-exclude").read_text(encoding="utf-8")
            rules = module.parse_exclude(
                text + "\nstrip: .agents/evals/fixtures/detector_spring_angular.tree.json\n"
            )
            self.assertIsNone(module.match_rule(TREE.relative_to(ROOT).as_posix(), rules))
        elif mode == "P":
            self.assertEqual(_machine_hits({"command": "codex exec -C/var/folders/fixture"}), [])
        else:
            self.fail(f"unknown DETECTOR_MUTANT {mode}")

    def test_D_five_operational_prompts_carry_each_rule(self) -> None:
        for host, relative in DEFS.items():
            with self.subTest(host=host):
                self.assertEqual(_missing_rules(_prompt(relative)), [], host)

    def test_D_mutant_rule_removed_from_gemini_is_red(self) -> None:
        body = _prompt(DEFS["gemini"])
        self.assertEqual(_missing_rules(body), [])
        mutant = body.replace("spring-boot-starter-*-test", "", 1)
        self.assertIn(JAVA_RULE, _missing_rules(mutant))

    def test_D_mutant_codex_comment_only_is_red(self) -> None:
        body = (ROOT / DEFS["codex"]).read_text(encoding="utf-8")
        mutant = body.replace("spring-boot-starter-*-test", "", 1)
        mutant += "\n# spring-boot-starter-*-test\n"
        parsed = tomllib.loads(mutant)["developer_instructions"]
        self.assertIn(JAVA_RULE, _missing_rules(parsed))

    def test_U_three_source_contents_are_pinned(self) -> None:
        self.assertEqual(_source_faults(_load_json(TREE)), [])

    def test_U_mutant_one_pom_byte_is_red(self) -> None:
        tree = _load_json(TREE)
        tree["variants"]["base"]["backend/pom.xml"] += "x"
        self.assertIn("pom-web: sha differs from pinned content", _source_faults(tree))

    def test_F_eight_manifest_trees_are_complete(self) -> None:
        self.assertEqual(_fixture_faults(_load_json(TREE)), [])

    def test_F_mutant_missing_pom_is_red(self) -> None:
        tree = _load_json(TREE)
        del tree["variants"]["base"]["backend/pom.xml"]
        self.assertIn("base: backend manifest absent", _fixture_faults(tree))

    def test_F_mutant_explicit_karma_in_base_is_red(self) -> None:
        tree = _load_json(TREE)
        angular = json.loads(tree["variants"]["base"]["frontend/angular.json"])
        angular["projects"]["app"]["architect"]["test"]["options"]["runner"] = "karma"
        tree["variants"]["base"]["frontend/angular.json"] = json.dumps(angular)
        self.assertIn("base: must represent ng new unit-test without runner", _fixture_faults(tree))

    def test_O_fortyeight_real_replays_conform_by_majority(self) -> None:
        tree = _load_json(TREE)
        records = _load_json(OBSERVED)["records"]
        self.assertEqual(len(records), len(VARIANTS) * len(HOSTS) * DRAWS,
                         "48 actual host replays required")
        kit = (ROOT / ".agents/IS_THE_KIT").exists()  # adopting-tree: le marqueur du kit ne voyage pas, son absence EST l'adoptant
        faults, rates = _observed_faults(records, tree, kit)
        for (variant, host), good in rates.items():
            print(f"stability {variant}/{host}: {good}/{DRAWS}")
        self.assertEqual(faults, [])

    def test_O_mutant_provenance_on_one_draw_of_a_full_case_is_red(self) -> None:
        """Provenance is absolute: one bad draw in a 3/3 case is not outvoted."""
        tree = _load_json(TREE)
        kit = (ROOT / ".agents/IS_THE_KIT").exists()  # adopting-tree: idem
        original = _load_json(OBSERVED)["records"]
        self.assertEqual(_observed_faults(original, tree, kit)[0], [])

        def degrade(record: dict[str, Any]) -> None:
            for key in list(record):
                if key not in ("variant", "host", "draw"):
                    del record[key]
            record["degraded"] = True

        def other_model(record: dict[str, Any]) -> None:
            record["model"], record["effort"] = "sonnet", "high"

        def stale_def(record: dict[str, Any]) -> None:
            record["def_sha256"] = "b" * 64

        def no_command(record: dict[str, Any]) -> None:
            record["command"] = ""

        mutants = (
            (("base", "claude"), degrade, "claude replay cannot be degraded"),
            (("gradle", "claude"), other_model, "claude replay must use haiku/low"),
            (("gradle", "codex"), other_model, "codex replay must use gpt-6-luna/" + PINS["codex"][1]),
            (("base", "codex"), degrade, "codex replay cannot be degraded"),
            (("gradle", "claude"), no_command, "command missing"),
        )
        if kit:
            mutants += ((("gradle", "claude"), stale_def, "definition sha is stale"),)
        for case, mutate, fault in mutants:
            with self.subTest(case=case, fault=fault):
                records = json.loads(json.dumps(original))
                target = next(r for r in records if (r["variant"], r["host"], r["draw"]) == (*case, 1))
                mutate(target)
                faults, rates = _observed_faults(records, tree, kit)
                self.assertGreaterEqual(rates[case], MAJORITY, "the vote alone would pass")
                self.assertIn(f"{case[0]}/{case[1]} draw 1: {fault}", faults)

    def test_O_mutant_case_at_one_draw_in_three_is_red(self) -> None:
        records = [
            {"variant": v, "host": h, "draw": d}
            for v in VARIANTS for h in HOSTS for d in range(1, DRAWS + 1)
        ]

        def judge(record: dict[str, Any]) -> list[str]:
            bad = (record["variant"], record["host"]) == ("base", "claude") and record["draw"] > 1
            return ["planted fault"] if bad else []

        faults, rates = _majority_faults(records, judge)
        self.assertEqual(rates[("base", "claude")], 1)
        self.assertEqual(faults, [f"base/claude: 1/{DRAWS} draws conform, {MAJORITY} required"])
        ok_faults, _ = _majority_faults(records, lambda record: [] if record["draw"] > 1 else ["x"])
        self.assertEqual(ok_faults, [], "2/3 everywhere must stay green")
        missing, _ = _majority_faults(records[:-1], lambda record: [])
        self.assertIn("48 actual host replays required, one per case, host and draw", missing)

    def test_O_mutant_wrong_backend_manager_is_red(self) -> None:
        tree = _load_json(TREE)
        record = {
            "variant": "base", "host": "codex", "model": "gpt-6-luna",
            "effort": PINS["codex"][1], "command": "codex exec fixture-base-codex",
            "base_sha": "a" * 40,
            "def_sha256": hashlib.sha256((ROOT / DEFS["codex"]).read_bytes()).hexdigest(),
            "sheets_present": sorted(s for s in SHEETS if (ROOT / s).is_file()),
            "json": {"modules": [
                {"path": "backend", "package_manager": "gradle", "test_runner": "junit",
                 "registry_sections": ["java", "spring-boot"],
                 "conventions_file": next((s for s in SHEETS[0:1] if (ROOT / s).is_file()), None)},
                {"path": "frontend", "package_manager": "npm", "test_runner": "vitest",
                 "registry_sections": ["typescript", "angular"],
                 "conventions_file": next((s for s in SHEETS[1:] if (ROOT / s).is_file()), None)},
            ]},
        }
        faults = _record_faults(record, tree, True)
        self.assertIn("backend: package_manager expected maven, got gradle", faults)
        record["def_sha256"] = "b" * 64
        self.assertIn("definition sha is stale", _record_faults(record, tree, True))

    def test_P_all_observed_strings_have_relative_paths(self) -> None:
        self.assertEqual(_machine_hits(_load_json(OBSERVED)), [])

    def test_P_mutants_absolute_and_option_glued_paths_are_red(self) -> None:
        account = "-Us" + "ers-demo-"
        for value in (
            "/private/tmp/claude-502/" + account + "projects/fixture/backend/pom.xml",
            "codex exec -C /var/folders/fixture-base-codex",
            "codex exec -C/var/folders/fixture-base-codex",
            "codex exec --cd=C:\\work\\fixture",
            "file:///fixture-base-codex",
            "~/fixture-base-codex",
        ):
            with self.subTest(value=value):
                self.assertTrue(_machine_hits({"command": value}))
        self.assertTrue(_machine_hits({"json": {"signals_used": ["/private/tmp/fixture/backend/pom.xml"]}}))
        self.assertEqual(_machine_hits({"version": "~5.9.2"}), [])

    def test_P_registry_title_with_spaced_slash_is_not_a_machine_path(self) -> None:
        """Measured on a526683 (angular20/codex draw 2): registry_sections held
        `java / kotlin`, the DOCS_REGISTRY title, and the old pattern took the
        ` /` for an absolute path — a provenance fault on a correct draw."""
        self.assertEqual(_machine_hits({"json": {"registry_sections": ["java / kotlin"]}}), [])
        self.assertTrue(_machine_hits({"json": {"registry_sections": ["java /kotlin"]}}))
        self.assertTrue(_machine_hits({"command": "codex exec -C /var/folders/x"}))

    def test_P_mutant_old_slash_pattern_flags_the_registry_title(self) -> None:
        old = re.compile(MACHINE_PATH_RE.pattern.replace("(?:/(?!\\s)|", "(?:/|", 1))
        self.assertNotEqual(old.pattern, MACHINE_PATH_RE.pattern, "the mutant changed nothing")
        self.assertIsNotNone(old.search("java / kotlin"))
        self.assertIsNone(MACHINE_PATH_RE.search("java / kotlin"))

    def test_V_fixture_paths_travel_on_take_channel(self) -> None:
        path = ROOT / ".agents/bin/sync_template.py"
        spec = importlib.util.spec_from_file_location("sync_template_detector_probe", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        rules = module.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for item in (TREE, OBSERVED, Path(__file__), ROOT / DEFS["codex"]):
            relative = item.relative_to(ROOT).as_posix()
            self.assertIsNone(module.match_rule(relative, rules), relative)
        mutant = module.parse_exclude(
            (ROOT / ".template-exclude").read_text(encoding="utf-8")
            + "\nstrip: .agents/evals/fixtures/detector_spring_angular.tree.json\n"
        )
        self.assertIsNotNone(module.match_rule(TREE.relative_to(ROOT).as_posix(), mutant))


if __name__ == "__main__":
    unittest.main()
