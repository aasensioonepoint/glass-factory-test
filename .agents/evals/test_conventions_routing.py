"""Routing of a detected stack token to its `.agents/ref/CONVENTIONS_*.md` sheet
(T-01M5BZC4DV3XT5AVZ6F388P78K, lot D, chantier reprise-ecc).

WHAT THIS BENCH HOLDS. The registry key `conventions:` (DOCS_REGISTRY.md) names,
per section, the sheet(s) of that stack. NO code reads the key yet — this bench is
its only reader; wiring the language-detector to the resolved section is the
follow-up after T-01M5BZBWTT. Five arms, each with an in-memory negative control:

  R1  every token of ROUTES resolves to a registry section through the real
      resolver (`skills_github_fallback._resolve_section`) ;
  R2  that section carries a `conventions:` line naming the routed sheet ;
  R3  the sheet exists, carries the ECC attribution line EXACTLY, and the
      GUARANTEE of the CONVENTIONS family ;
  R4  every `conventions:` value of the registry is an existing file ;
  R5  no skill (`.agents/skills/*/SKILL.md`, `.claude/skills/*-pointer/SKILL.md`)
      says « Aucune feuille `CONVENTIONS_x.md` » of a sheet that exists.

ROUTES IS WRITTEN BY HAND, ON PURPOSE: a table derived from the registry would
agree with the registry by construction and could never redden.

BOUNDS, said so they are not read as universal. The token `csharp` resolves NO
section (measured None): it is NOT in ROUTES, and `test_csharp_resolves_no_section`
pins the bound the registry header states. R3 covers only the sheets adapted from
ECC (the nine of ROUTES), not go/python/typescript/nextjs/shell/infra. R5 matches
the French « Aucune feuille » sentence only, the one form these skills use.

The resolver is imported through `sys.path` like test_skills_github_fallback.py,
never through `exec_module` (test_modload_registration.py would require the
`sys.modules` registration).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
REF = ROOT / ".agents" / "ref"
REGISTRY = REF / "DOCS_REGISTRY.md"

sys.path.insert(0, str(BIN))

import skills_github_fallback as sgf

ROUTES = {
    "java": "CONVENTIONS_java.md",
    "kotlin": "CONVENTIONS_kotlin.md",
    "c#": "CONVENTIONS_dotnet.md",
    "dotnet": "CONVENTIONS_dotnet.md",
    "php": "CONVENTIONS_php.md",
    "ruby": "CONVENTIONS_ruby.md",
    "rust": "CONVENTIONS_rust.md",
    "swift": "CONVENTIONS_swift.md",
    "c++": "CONVENTIONS_cpp.md",
    "cpp": "CONVENTIONS_cpp.md",
    "dart": "CONVENTIONS_dart.md",
    "flutter": "CONVENTIONS_dart.md",
}

ATTRIBUTION = (
    "Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — "
    "notice : THIRD_PARTY_NOTICES.md"
)
GUARANTEE = "SURVIVES a template refresh"

CONVENTIONS_LINE = re.compile(r"^conventions:\s*(.+)$", re.MULTILINE)
SHEET_PATH = re.compile(r"\.agents/ref/(CONVENTIONS_[A-Za-z0-9_+-]+\.md)")
FALSE_ABSENCE = re.compile(r"Aucune feuille\s+`?(CONVENTIONS_[A-Za-z0-9_+-]+\.md)`?")


# --------------------------------------------------------------------------- #
# Pure predicates: fed the real tree below, and a mutated copy in the controls.
# --------------------------------------------------------------------------- #
def _resolve(token: str, lines: list[str]):
    return sgf._resolve_section(
        token, sgf._registry_titles(lines), sgf._registry_framework_bullets(lines))


def _section_body(lines: list[str], title: str) -> str:
    """Text from `## <title>` to the next column-0 `## ` heading."""
    out, inside = [], False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == title
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def _named_sheets(text: str) -> list[str]:
    """Sheet file names carried by the `conventions:` lines of `text`."""
    return [m for value in CONVENTIONS_LINE.findall(text) for m in SHEET_PATH.findall(value)]


def _route_problem(token: str, sheet: str, lines: list[str]) -> str | None:
    """R1 + R2: None when the token resolves to a section naming the sheet."""
    title = _resolve(token, lines)
    if title is None:
        return f"R1: token {token!r} resolves to no registry section"
    if sheet not in _named_sheets(_section_body(lines, title)):
        return f"R2: section `## {title}` has no `conventions:` naming {sheet}"
    return None


def _sheet_problems(text: str) -> list[str]:
    """R3 on the sheet's text (existence is checked by the caller)."""
    problems = []
    if ATTRIBUTION not in text.splitlines():
        problems.append("R3: exact ECC attribution line missing")
    if GUARANTEE not in text:
        problems.append("R3: GUARANTEE missing")
    return problems


def _missing_values(registry_text: str, ref_dir: Path) -> list[str]:
    """R4: every `conventions:` value of the registry exists under ref_dir."""
    return [s for s in _named_sheets(registry_text) if not (ref_dir / s).is_file()]


def _false_absences(skill_text: str, existing: set[str]) -> list[str]:
    """R5: « Aucune feuille `X` » where X exists."""
    return [s for s in FALSE_ABSENCE.findall(skill_text) if s in existing]


def _registry_lines() -> list[str]:
    return REGISTRY.read_text(encoding="utf-8").splitlines()


def _skill_files() -> tuple[list[Path], list[Path]]:
    return (sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")),
            sorted((ROOT / ".claude" / "skills").glob("*-pointer/SKILL.md")))


def _existing_sheets() -> set[str]:
    return {p.name for p in REF.glob("CONVENTIONS_*.md")}


# --------------------------------------------------------------------------- #
# Arms on the real tree
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token", sorted(ROUTES))
def test_r1_r2_token_resolves_to_a_section_naming_its_sheet(token):
    problem = _route_problem(token, ROUTES[token], _registry_lines())
    assert problem is None, problem


@pytest.mark.parametrize("sheet", sorted(set(ROUTES.values())))
def test_r3_sheet_exists_with_attribution_and_guarantee(sheet):
    path = REF / sheet
    assert path.is_file(), f"R3: {sheet} absent"
    assert _sheet_problems(path.read_text(encoding="utf-8")) == []


def test_r4_every_conventions_value_exists():
    text = REGISTRY.read_text(encoding="utf-8")
    named = _named_sheets(text)
    assert set(ROUTES.values()) <= set(named), (
        "NON-VACUITY: the registry must name every routed sheet in a `conventions:` line")
    assert _missing_values(text, REF) == []


def test_r5_no_skill_denies_an_existing_sheet():
    shared, pointers = _skill_files()
    assert shared, "NON-VACUITY: no .agents/skills/*/SKILL.md scanned"
    assert pointers, "NON-VACUITY: no .claude/skills/*-pointer/SKILL.md scanned"
    skills = shared + pointers
    existing = _existing_sheets()
    offenders = {str(p.relative_to(ROOT)): _false_absences(p.read_text(encoding="utf-8"), existing)
                 for p in skills}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_csharp_resolves_no_section():
    """The bound the registry header states. If `csharp` ever resolves, add it to
    ROUTES and rewrite that header sentence in the same edit."""
    assert _resolve("csharp", _registry_lines()) is None


# --------------------------------------------------------------------------- #
# Negative controls, in memory — each arm must bite on its own mutant.
# --------------------------------------------------------------------------- #
def test_m1_control_renamed_title_breaks_r1():
    lines = ["## php7" if ln == "## php" else ln for ln in _registry_lines()]
    assert _route_problem("php", "CONVENTIONS_php.md", lines).startswith("R1:")


def test_m2_control_dropped_conventions_line_breaks_r2():
    lines = [ln for ln in _registry_lines()
             if ln != "conventions: .agents/ref/CONVENTIONS_rust.md"]
    assert _route_problem("rust", "CONVENTIONS_rust.md", lines).startswith("R2:")


def test_m3_control_altered_attribution_or_missing_guarantee_breaks_r3():
    text = (REF / "CONVENTIONS_swift.md").read_text(encoding="utf-8")
    assert _sheet_problems(text.replace("6f1881ae", "6f1881af")) == [
        "R3: exact ECC attribution line missing"]
    assert _sheet_problems(text.replace(GUARANTEE, "is kept")) == ["R3: GUARANTEE missing"]


def test_m4_control_dangling_value_breaks_r4():
    text = REGISTRY.read_text(encoding="utf-8") + "\nconventions: .agents/ref/CONVENTIONS_nope.md\n"
    assert _missing_values(text, REF) == ["CONVENTIONS_nope.md"]


def test_m5_control_false_absence_breaks_r5():
    text = "Aucune feuille `CONVENTIONS_java.md` n'existe pour cette stack."
    assert _false_absences(text, _existing_sheets()) == ["CONVENTIONS_java.md"]
    assert _false_absences("Aucune feuille `CONVENTIONS_vue.md` n'existe.", _existing_sheets()) == []
