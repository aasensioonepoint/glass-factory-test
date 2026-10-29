"""ZERO-LLM proof for the five hook registries (T-00000461, R1-16).

WHAT THIS PROVES: no hook registered on any of the five registries invokes an
LLM — not in the registered script, nor in the scripts it references (depth 2) —
with ZERO ASSUMED EXCEPTIONS. Two existed, both on Claude and both toward the
launcher of the local dev route; they left with that route
(T-01M5PCCHMWXTRCM5QJT8J5KNEH), and `test_zero_assumed_exceptions` reddens the
day one is added back without a decision.

HOW. The host table is NOT recopied — it is IMPORTED from
`test_semgrep_hook_registration.py` (constant `HOSTS`: 6 hosts, 5 registries,
`shape ∈ {nested, flat}`). A third copy would be a time bomb (L-00000111). This
suite derives only the SET of DISTINCT registries and asserts identity with it.

EXTRACTION IS KEYED ON HOOK FIELDS, NEVER A FULL-FILE REGEX — a decision, not a
detail. `.claude/settings.json` also carries `permissions.allow` lines like
`Bash(.agents/security/sca-watch.sh:*)`, and `sca-watch.sh` DOES run `claude -p`
— a full-file regex would drag in a script NO hook executes and redden for a
false reason. The negative witness `test_sca_watch_is_not_extracted` pins that.

"0 LLM" = none of a CLOSED list of forms, on a line of CODE (a line whose first
non-blank char is `#` is dropped; a trailing comment on a code line is NOT — a
conservative bound, false red possible, never false green: a script that carries
`api.anthropic.com` IN A COMMENT only is not an LLM call, and an exception
resting on a comment would rest on a `sed`). The CLOSED list: CLI (`claude -p|--print`, `codex exec`,
`gemini -p`, `copilot -p`, `ollama run`), the `--print` flag AS A WHOLE WORD
whatever executable carries it (see the NAMED HOLE below), SDK imports
(`anthropic`, `openai`, `google.generativeai|genai`, `litellm`, `langchain`),
API hosts (`api.anthropic.com`, `api.openai.com`,
`generativelanguage.googleapis.com`, `openrouter.ai`). The word "LLM" alone is
NOT a marker (L-00000187).

NAMED HOLE, not plugged: an executable expanded from a variable
(`"$LANCEUR" …`, `$X chat`) is recognised only by its FLAGS — a launcher invoked
without `--print` nor a listed CLI form would pass. Measured instance: the
launcher of the since-retired local dev route, whose executable came from a
variable with a local default.

SECOND NAMED HOLE (C5 it9), DECIDED HERE: the extraction alternation INCLUDES
`scripts` — a registered hook reaches `core-scripts/ci-last-run.sh`
(`session-start.sh` → CI cache) and `scripts/index-refresh.sh`
(`post-task-done-index.sh`, currently ABSENT). Rather than leave `scripts/`
SILENTLY excluded (the silence L-00000187 punishes), it is scanned like the five
prefixes and any absent reference is COUNTED in the printed bound.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# The host table is IMPORTED, never recopied (a third copy would drift).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_semgrep_hook_registration import HOSTS  # noqa: E402
from surface_kit import jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# registry -> shape, derived from the ONE host table (5 distinct registries).
REGISTRIES = {row[1]: row[2] for row in HOSTS}

# Script paths, keyed on the five host prefixes PLUS `scripts` (C5, decided here).
#
# `core-scripts` ET `scripts` — LES DEUX, depuis le renommage du 2026-09-09
# (T-00000403). `core-scripts/` est le répertoire du KIT ; `scripts/` reste
# nécessaire parce qu'un hook référence le `scripts/index-refresh.sh` de
# l'ADOPTANT (`post-task-done-index.sh`), et c'est précisément cette référence
# absente que la borne imprimée doit continuer de COMPTER. Retirer `scripts`
# ici ferait sortir cette jambe du périmètre 0-LLM EN SILENCE, test vert.
# `core-scripts` est placé AVANT `scripts` : l'alternance est ordonnée, et
# l'inverse ferait matcher `scripts` sur la fin de `core-scripts`.
SCRIPT_RE = re.compile(
    r"(?:\.claude|\.codex|\.gemini|\.agents|\.github|core-scripts|scripts)/"
    r"[\w./-]+\.(?:sh|py|ps1)\b"
)

# The CLOSED list of LLM forms. The word "LLM" alone is NOT here (L-00000187).
_LLM_CLI = [
    r"\bclaude\s+-p\b", r"\bclaude\s+--print\b", r"\bcodex\s+exec\b",
    r"\bgemini\s+-p\b", r"\bcopilot\s+-p\b", r"\bollama\s+run\b",
]
_LLM_FLAG = r"(?:^|\s)--print(?:\s|$)"          # whole word, any executable
_LLM_IMPORT = [
    r"\bimport\s+anthropic\b", r"\bfrom\s+anthropic\b",
    r"\bimport\s+openai\b", r"\bfrom\s+openai\b",
    r"\bgoogle\.generativeai\b", r"\bimport\s+genai\b",
    r"\bimport\s+litellm\b", r"\bimport\s+langchain\b", r"\bfrom\s+langchain\b",
]
_LLM_HOSTS = ["api.anthropic.com", "api.openai.com",
              "generativelanguage.googleapis.com", "openrouter.ai"]
_LLM_PATTERNS = [re.compile(p) for p in (_LLM_CLI + [_LLM_FLAG] + _LLM_IMPORT)]

# ASSUMED EXCEPTIONS (host, hook script, reached script, reason): NONE. The two
# that existed (both on Claude, both toward the launcher of the local dev route)
# left with that route (T-01M5PCCHMWXTRCM5QJT8J5KNEH). The mechanism stays: an
# exception added here must be a real chain carrying a form, and
# `test_zero_assumed_exceptions` makes adding one a visible decision.
ASSUMED_EXCEPTIONS: frozenset = frozenset()

GUARDRAILS = ROOT / ".agents" / "skills" / "guardrails" / "SKILL.md"


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _forms_in_text(text: str) -> list:
    """LLM forms on CODE lines only. Returns [(lineno, label, line)]."""
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if _is_comment(line):
            continue
        for pat in _LLM_PATTERNS:
            if pat.search(line):
                hits.append((i, pat.pattern, line.strip()[:100]))
        for host in _LLM_HOSTS:
            if host in line:
                hits.append((i, host, line.strip()[:100]))
    return hits


def _forms_in_file(path: Path) -> list:
    if not path.exists():
        return []
    return _forms_in_text(path.read_text(encoding="utf-8", errors="replace"))


def _hook_named_legs(obj: dict, shape: str) -> list[tuple[str, str]]:
    """Every command/window leg of every hook, keyed on hook fields ONLY —
    never permissions.allow, never a bare full-file scan. Present-but-empty
    fields stay visible so the non-vacuity rule can reject them. Outside the kit,
    a leg the ADOPTER added is not judged (T-01M54MWW5GH, S-01M550PYWS) — filtered
    once, below, on the leg's own text."""
    legs: list[tuple[str, str]] = []
    hooks = obj.get("hooks", {})
    if shape == "nested":
        for _event, blocks in hooks.items():
            for block in blocks:
                for hook in block.get("hooks", []):
                    for key in ("command", "commandWindows"):
                        if key in hook:
                            legs.append((key, str(hook[key])))
    else:  # flat (Copilot)
        for _event, entries in hooks.items():
            for hook in entries:
                for key in ("bash", "powershell"):
                    if key in hook:
                        legs.append((key, str(hook[key])))
    return [(key, leg) for key, leg in legs if jambe_jugee(leg)]


def _hook_legs(obj: dict, shape: str) -> list[str]:
    return [leg for _key, leg in _hook_named_legs(obj, shape)]


def _leg_violations(registry: str, key: str, leg: str) -> list[str]:
    """One replayable scanner rule for real legs and mutation controls."""
    violations: list[str] = []
    scripts = [match.group(0) for match in SCRIPT_RE.finditer(leg)]
    if not scripts:
        violations.append(f"{registry}/{key}: no identifiable script path")
    for script in scripts:
        if not (ROOT / script).is_file():
            violations.append(f"{registry}/{key}: cited script {script} does not exist")

    if key == "commandWindows":
        helper = ".agents/pyrun.ps1"
        if scripts.count(helper) != 1:
            violations.append(f"{registry}/{key}: shared pyrun.ps1 helper not identifiable")
        targets = [script for script in scripts if script != helper]
        if len(targets) != 1:
            violations.append(
                f"{registry}/{key}: expected one literal target beside helper, got {targets}"
            )
    if re.search(r"encodedcommand|invoke-expression", leg, re.IGNORECASE):
        violations.append(f"{registry}/{key}: encoded or evaluated bootstrap is opaque")
    for lineno, label, text in _forms_in_text(leg):
        violations.append(f"{registry}/{key}:{lineno} [{label}] {text}")
    return violations


def _depth1() -> dict:
    """registry -> set of depth-1 script paths cited in its hook legs."""
    out = {}
    for registry, shape in REGISTRIES.items():
        obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
        scripts = set()
        for leg in _hook_legs(obj, shape):
            scripts |= set(m.group(0) for m in SCRIPT_RE.finditer(leg))
        out[registry] = scripts
    return out


def _reached():
    """(reached, edges, missing): depth-1 ∪ depth-2 scripts, the script->{hooks}
    edges (which depth-1 scripts reference a script), and the set of referenced
    paths that do NOT exist on disk. Depth 2 only — not deeper."""
    d1 = _depth1()
    reached = set().union(*d1.values()) if d1 else set()
    edges = {}
    missing = {s for s in reached if not (ROOT / s).exists()}
    for s in sorted(reached):
        p = ROOT / s
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if _is_comment(line):
                continue
            for m in SCRIPT_RE.finditer(line):
                r = m.group(0)
                if r == s:
                    continue
                edges.setdefault(r, set()).add(s)
                if r not in reached:
                    reached.add(r)
                    if not (ROOT / r).exists():
                        missing.add(r)
    return reached, edges, missing


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestZeroLlmHooks:

    def test_zero_llm_table_is_the_semgrep_table(self):
        """The registries this suite walks ARE the distinct registries of the
        imported semgrep host table — not a private copy that could drift."""
        walked = set(REGISTRIES)
        semgrep = {row[1] for row in HOSTS}
        assert walked == semgrep, (
            f"registry sets diverged — walked={sorted(walked)} semgrep={sorted(semgrep)}"
        )
        assert len(walked) == 5, f"expected 5 distinct registries, got {len(walked)}"

    def test_every_leg_yields_an_existing_script_non_vacuity(self):
        """Each registry renders ≥1 leg and EVERY leg exposes existing scripts.
        No script-bearing prefilter may hide empty or unrecognised legs. Python-
        mediated Windows legs expose both helper and literal target."""
        import json
        seen_semgrep = False
        for registry, shape in sorted(REGISTRIES.items()):
            obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
            named_legs = _hook_named_legs(obj, shape)
            print(f"[0-LLM] {registry}: {len(named_legs)} leg(s) inspected")
            assert named_legs, f"{registry}: registry renders no hook leg"
            for key, leg in named_legs:
                offenders = _leg_violations(registry, key, leg)
                assert not offenders, "; ".join(offenders)
                seen_semgrep |= any(
                    match.group(0).endswith("semgrep-scan.sh")
                    for match in SCRIPT_RE.finditer(leg)
                )
        assert seen_semgrep, "positive witness lost: semgrep-scan.sh no longer in the perimeter"

    def test_reject_ps1_mutation(self):
        registry = ".codex/hooks.json"
        obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
        leg = next(
            value for key, value in _hook_named_legs(obj, REGISTRIES[registry])
            if key == "commandWindows"
        )
        assert not _leg_violations(registry, "commandWindows", leg)
        mutated = leg.replace("pyrun.ps1", "pyrun.psx", 1)
        assert mutated != leg, "the ps1 mutation changed nothing"
        assert any("pyrun.ps1 helper" in item for item in _leg_violations(
            registry, "commandWindows", mutated
        ))

    def test_reject_hidden_path_mutation(self):
        registry = ".codex/hooks.json"
        obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
        leg = next(
            value for key, value in _hook_named_legs(obj, REGISTRIES[registry])
            if key == "commandWindows"
        )
        paths = [match.group(0) for match in SCRIPT_RE.finditer(leg)]
        target = next(path for path in paths if path != ".agents/pyrun.ps1")
        mutated = leg.replace(target, "hidden-target", 1)
        assert mutated != leg, "the hidden-path mutation changed nothing"
        assert any("literal target" in item for item in _leg_violations(
            registry, "commandWindows", mutated
        ))

    def test_reject_encoded_command_mutation(self):
        registry = ".codex/hooks.json"
        obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
        leg = next(
            value for key, value in _hook_named_legs(obj, REGISTRIES[registry])
            if key == "commandWindows"
        )
        mutated = leg.replace("-Command", "-EncodedCommand", 1)
        assert mutated != leg, "the encoded-command mutation changed nothing"
        assert any("opaque" in item for item in _leg_violations(
            registry, "commandWindows", mutated
        ))

    def test_reject_bootstrap_llm_injection(self):
        registry = ".codex/hooks.json"
        obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
        leg = next(
            value for key, value in _hook_named_legs(obj, REGISTRIES[registry])
            if key == "commandWindows"
        )
        mutated = leg + " codex exec injected"
        assert any("codex" in item for item in _leg_violations(
            registry, "commandWindows", mutated
        ))

    def test_sca_watch_is_not_extracted(self):
        """Negative witness: sca-watch.sh runs `claude -p` and sits in
        permissions.allow — a FULL-FILE regex would drag it in. The structural
        extraction (hook fields only) must NOT reach it."""
        reached, _edges, _missing = _reached()
        assert not any(s.endswith("sca-watch.sh") for s in reached), (
            "sca-watch.sh entered the extracted set — extraction became full-file "
            "instead of hook-keyed (it runs `claude -p` and would falsely redden)"
        )

    def test_no_unexcepted_script_carries_an_llm_form(self):
        """(i) Any reached script carrying an LLM form on a code line MUST be a
        reached_script of an assumed exception — else RED, naming path+form+line.
        Prints the bound: N scripts scanned, K absent references."""
        reached, _edges, missing = _reached()
        excepted = {exc[2] for exc in ASSUMED_EXCEPTIONS}
        scanned = sorted(s for s in reached if (ROOT / s).exists())
        print(f"[0-LLM] scanned {len(scanned)} script(s), {len(missing)} absent reference(s): "
              f"{sorted(missing)}")
        offenders = []
        for s in scanned:
            forms = _forms_in_file(ROOT / s)
            if forms and s not in excepted:
                for lineno, label, line in forms:
                    offenders.append(f"{s}:{lineno} [{label}] {line}")
        assert not offenders, "un-excepted LLM form(s) reached by a hook:\n" + "\n".join(offenders)

    def test_each_assumed_exception_is_reached_and_carries_a_form(self):
        """(ii) Each exception must be a REAL chain (hook reached from a registry,
        hook references the reached script) AND the reached script must carry an
        LLM form on a code line — a stale exception (a hole that closed) reddens."""
        d1 = _depth1()
        depth1_all = set().union(*d1.values()) if d1 else set()
        reached, edges, _missing = _reached()
        for host, hook, reached_script, _reason in ASSUMED_EXCEPTIONS:
            assert hook in depth1_all, f"exception hook {hook} is no longer registered on any registry"
            assert hook in edges.get(reached_script, set()), (
                f"exception chain {hook} -> {reached_script} no longer exists (stale exception)"
            )
            forms = _forms_in_file(ROOT / reached_script)
            assert forms, (
                f"exception target {reached_script} carries NO LLM form on a code line — "
                f"the hole closed, remove the exception (never let a comment carry it)"
            )

    def test_zero_assumed_exceptions(self):
        """(iii) ZERO exceptions since the local dev route left (T-01M5PCCHMW…):
        adding one back is a decision, so it reddens here first; and the
        session-start hook, which was one of the two chains, now reaches no
        script that carries an LLM form on a code line."""
        assert len(ASSUMED_EXCEPTIONS) == 0, (
            f"assumed exceptions are back: {sorted(ASSUMED_EXCEPTIONS)} — "
            "an exception to the 0-LLM scope is a pilot decision, update the "
            "guardrails scope phrase and this test together"
        )
        _reached_set, edges, _missing = _reached()
        ss = ".claude/hooks/session-start.sh"
        offenders = sorted(
            target for target, hooks in edges.items()
            if ss in hooks and (ROOT / target).is_file() and _forms_in_file(ROOT / target)
        )
        assert not offenders, f"{ss} reaches script(s) carrying an LLM form: {offenders}"

    def test_scope_phrase_is_pinned_in_guardrails_skill(self):
        """The 0-LLM scope travels on guardrails/SKILL.md (a skill that TRAVELS;
        AGENTS.md stays router). The phrase says ZERO exceptions and keeps the
        two LLM gates assumed by design — amputating either reddens."""
        text = GUARDRAILS.read_text(encoding="utf-8")
        for needle in ("AUCUNE exception", "compte EXACTEMENT zéro exception",
                       "`plan-critic` et `security-code-review` sont des gates LLM assumées"):
            assert needle in text, f"guardrails/SKILL.md scope phrase lost {needle!r}"

    def test_armament_taxonomy_is_pinned_in_guardrails_skill(self):
        """The station-armament taxonomy travels on guardrails/SKILL.md, in ITS
        section (T-00000593): five species, the two rules and the open-list
        bound. BOUNDED to that section — `GITLEAKS_FALLBACK=0` already appears
        earlier in the file, so a whole-text search could not redden when the
        section loses it. The MORT command is pinned WITH its first widened
        glob (`'*.js'`): a revert to the `.py`/`.sh`-only form reddens."""
        text = GUARDRAILS.read_text(encoding="utf-8")
        head = "## UNE GARDE N'EST TENUE QUE LÀ OÙ ELLE EST ARMÉE"
        assert head in text, f"guardrails/SKILL.md lost its section {head!r}"
        section = text[text.index(head):]
        end = section.find("\n## ", 1)
        if end != -1:
            section = section[:end]
        for needle in ("marqueurs d'armement de poste", "registres de hooks de poste",
                       "clés git locales", "sorties relues", "marqueurs morts",
                       "NOMMER N'EST PAS LIRE", "relever l'armement sur le poste",
                       "liste non close : toute espèce hors de ces cinq se signale, "
                       "jamais couverte",
                       "GITLEAKS_FALLBACK=0",
                       "ne prouve pas qu'une garde le lit",
                       "il ne vaut que pour ce poste et pour ce jour",
                       "git grep -l -F <nom> -- '*.py' '*.sh' '*.js'"):
            assert needle in section, (
                f"armament section of guardrails/SKILL.md lost {needle!r}"
            )

    # ---- MUTATION fixtures (form detection on synthetic code lines) ----------
    def test_fixture_forms_positive_and_negative(self):
        assert _forms_in_text("echo x | claude -p"), "claude -p must be a form"
        assert _forms_in_text("import anthropic"), "import anthropic must be a form"
        assert _forms_in_text('"$X" --agent a --print'), "--print (any exe) must be a form"
        assert _forms_in_text("codex exec run"), "codex exec must be a form"
        assert _forms_in_text("curl https://api.openai.com/v1"), "api host must be a form"
        assert not _forms_in_text("# claude -p"), "a commented form must NOT count"
        assert not _forms_in_text("# 0 LLM"), "the word LLM alone must NOT count"
        assert not _forms_in_text("echo running the model"), "prose must NOT count"
