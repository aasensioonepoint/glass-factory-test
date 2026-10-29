"""A SCREEN PLAN NAMES ITS MOCKUP OR DECLARES ITS ABSENCE — read on the REAL plans
(T-00000621, BK-541).

`test_mockup_mirror.py` proves the rule is WRITTEN on three doctrine surfaces; it
opens no plan, and a rule well mirrored is not a rule applied. This net opens every
plan whose task DECLARES a front file in its board write-set, and holds two things:
  1. the plan carries one of the three CLOSED values of AGENTS.md § Golden rules —
     `mockup: <path or node>`, `no mockup: <reason>`,
     `mockup not reproduced: <path> + <task>`;
  2. every `mockup not reproduced:` names a task that EXISTS on the board — after
     its `+` when it writes one, anywhere in its payload otherwise, never inside its
     path — otherwise the debt is a wish (`.agents/skills/frontend-fidelity/SKILL.md`).

TWO DERIVATIONS, each born from a measured miss (BK-541, 2026-09-14):
  * the LINE is read TOLERATING MARKDOWN. An anchored `^mockup:` counted 28 plans
    where the corpus declares on more than a hundred: historical lines sit in
    backticks (LOT-5-plan.md:67), in bold (T-00000379-plan.md:116), or inline
    after a separator (`· no mockup: …`, `(no mockup: …)`). The doctrine fixes no
    line shape.
  * the SCREEN signal is the write-set DECLARED on the board, read by
    `tasks_requetes.writeset_of` itself (CALLED, not paraphrased, through the
    `tasks.py` facade that runs it) — never an extension quoted in prose:
    LOT-5-plan.md:45 cites `.scss` to EXCLUDE it, and T-00000379-plan.md:125 is
    a shell `EXTS` list.

"SCREEN PLAN", MEASURED AND BOUNDED. A plan is judged when its file name is EXACTLY
`<id>-plan.md` for a task `<id>` of the board — the name is LOOKED UP, never
parsed, so a legacy `T-<n>` and a `T-<ULID>` (the form of every new task, hence of
every adopter's plans) are judged alike — AND that task's declared write-set holds
a path whose suffix is in `FRONT_SUFFIXES`. Measured 2026-10-10 on the kit's board
at 2c5bf329: 324 plans, 314 named after a board task, 233 of those with a declared
write-set, 23 screen plans (couloir-b 36939aac: 19); two lacked the line
(T-00000476, T-00000509) and received it in the commit that brought this net.
NOT judged, said rather than implied:
  * a plan named after no board task (`LOT-*-plan.md`, 10 in the kit);
  * a plan whose task declares no write-set (81 of the 314): its write-set lives in
    prose, which this net refuses to parse;
  * a screen outside `FRONT_SUFFIXES` — `.js`/`.ts`/`.mjs` (tooling as often as
    UI), server templates (`.hbs`, `.njk`, `.jinja`, `.erb`, `.twig`, `.php`,
    `.cshtml`/`.razor`), native UI (`.dart`, `.swift`, `.kt`, `.xaml`) — or a
    write-set declaring only a directory;
  * TRUTH: `no mockup: je ne crois pas` passes. Of the debt, only the EXISTENCE of
    the named task is checked, never that it takes the mockup up;
  * EXCLUSIVITY: two different closed values in one plan both pass;
  * SHAPE: a value closed alone in a code span, then prose (`` - `mockup:`
    obligatoire ``), reads as a declaration — the historical form
    `` `no mockup:` aucun fichier de front… `` forbids telling them apart. Only an
    ENUMERATION (`/`, or another closed value in code after a value closed alone)
    is set aside; measured 2026-10-10 on 1211 `.md` (kit and adopters), that rule
    changes no declaration of a judged plan.

IT TRAVELS (pilot decision [decision/T-00000621/01]: no `strip:`). `docs/tasks/` is
`keep:` and `.agents/state/` is `strip:`, so an adopter starts with no plan and no
board: the real-plan arm is an EMPTY parameter set (skipped), and judges the
adopter's OWN screen plans as soon as it writes them. The two arms that read the
kit's own corpus skip outside it, keyed on `.agents/IS_THE_KIT` (`strip:`).
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: `keep:` — an adopter's plans are its own; absent, the real arm is empty
PLANS = ROOT / "docs" / "tasks"
# adopting-tree: `strip:` — project_init.py provisions it; absent, the real arm is empty. The board's FOLDER: it holds
# `TASKS.json` OR the record folders `tasks/`, `epics/` — read by the board's own reader (T-01M4KKMY43ZKCW1YD2Y8JX9MKH)
BOARD = ROOT / ".agents" / "state" / "board"
# adopting-tree: `strip:` — the kit's identity marker; the corpus arms skip without it
KIT = ROOT / ".agents" / "IS_THE_KIT"
TASKS_PY = ROOT / ".agents" / "bin" / "tasks.py"
STOCKAGE = ROOT / ".agents" / "bin" / "tasks_stockage.py"


def _load_tasks_facade():
    """The board's own module: `writeset_of` (absent key, null and `[]` are the same
    write-set) and `lire_board_brut` (the board in its form, T-01M4KKMY43ZKCW1YD2Y8JX9MKH).

    `tasks_requetes.py` is NEVER imported alone — it runs in the namespace of
    `tasks.py` (`_charger_parties`), which supplies its free names — so the
    facade is loaded, as `test_direct_mode.py` loads it, and REGISTERED before
    `exec_module` (T-00000134, `test_modload_registration.py`)."""
    spec = importlib.util.spec_from_file_location("_t621_tasks", TASKS_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_TASKS_FACADE = _load_tasks_facade()
writeset_of = _TASKS_FACADE.writeset_of

# COPIED, never imported, like specs.py and ledger.py do (tasks_stockage.py shares
# the namespace of tasks.py and does not load alone); `test_ulid_body_is_the_boards`
# holds the copy to its source.
ULID_BODY = "[0-9A-HJKMNP-TV-Z]{26}"
# A task id inside a PATH names no task: neither a name part (`T-2-maquette.html`),
# nor a stem before its extension (`T-2.png`), nor a directory (`T-2/x.png`).
_TASK_REF = re.compile(r"(?<![\w-])T-(?:" + ULID_BODY + r"|\d+)(?![\w/-]|\.\w)")

FRONT_SUFFIXES = frozenset(
    {".html", ".htm", ".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
)
CLOSED_VALUES = ("mockup:", "no mockup:", "mockup not reproduced:")
_PLAN_SUFFIX = "-plan.md"

# Where a declaration may OPEN: at line start behind Markdown markup (spaces,
# quote, list bullet or number, emphasis, code tick, table pipe), or inline right
# after a separator (`·`, `(`, `.`, `;`, a dash, a pipe) and its markup. Anything
# else — "aucune ligne `mockup:` n'est due" — is prose ABOUT the line.
_OPEN = r"(?:^[ \t>*_`~|#+-]*(?:\d+[.)][ \t]*)?|[·(.;—–|][ \t]*[*_`]*)"
_DECLARATION = re.compile(
    _OPEN + r"(?<![\w-])(?P<value>mockup not reproduced|no mockup|mockup)[ \t]*:(?P<payload>[^\n]*)",
    re.MULTILINE | re.IGNORECASE,
)
_CLOSING_MARKUP = "`*_\"'»”“‘ \t"
# A `/` that no path character follows opens an ENUMERATION (`/ no mockup:`,
# `/`no mockup:``), never a path (`/srv/design/x.html`).
_ENUMERATION = re.compile(r"/(?![\w.~])")
# After a value CLOSED ALONE, a payload naming ANOTHER closed value in a code span
# lists the doctrine (`` `mockup:` ou `no mockup:` ``) instead of choosing in it;
# a reason in the value's own span may cite one (`no mockup: … ligne `mockup:` …`).
_ANOTHER_VALUE = re.compile(r"`[ \t]*(?:mockup not reproduced|no mockup|mockup)[ \t]*:", re.IGNORECASE)
# A reason may open on a GLOSS — `(texte seul)`, `« aucun écran »`, `— texte seul`,
# or a dash — that a reason FOLLOWS: `—`, `(`, `| — |`, `-`, `-->`, `- -` are none.
_GLOSS = re.compile(r"[«(—–][ \t]*[^\s|]|-[ \t]+[^\s-]")
# A Markdown link or image — `[maquette](x.html)`, `![capture](x.png)`.
_MD_LINK = re.compile(r"!?\[[^\]\n]+\]\(")


def declarations(text: str) -> list[tuple[str, str]]:
    """Every `(closed value, payload)` a plan DECLARES. A payload must carry
    content: empty, a `<placeholder>`, a `,` or an enumeration (`/ no mockup:`,
    `` `mockup:` ou `no mockup:` ``) is a citation of the doctrine, not a choice.

    A payload opens, behind its quotes (`"`, `'`, `“`, `‘`), on a letter, a
    digit, `.`, `/`, `~`, a Markdown link or image (`[maquette](x.html)`,
    `![capture](x.png)`), or a gloss that a reason follows (`(`, `«`, `—`, `–`,
    `-`). The GLOSS counts only when it shares the value's span
    — `no mockup: (texte seul)`, `` `no mockup: (texte seul)` `` — because
    after a value CLOSED ALONE (`` - `no mockup:` (raison obligatoire) ``,
    `` - `mockup:` — la valeur qui nomme la maquette ``) the same opener
    comments the doctrine; by the same rule, another value cited in code lists
    the doctrine only after a value closed alone, and a reason in the value's
    own span may cite one (`no mockup: … aucune ligne `mockup:` …`). BOUND,
    said: `**no mockup:** (outil CLI)` is therefore read as no declaration;
    `**no mockup:** outil CLI` is one."""
    found = []
    for match in _DECLARATION.finditer(text):
        raw = match.group("payload").strip()
        payload = raw.lstrip(_CLOSING_MARKUP)
        listing = payload != raw and _ANOTHER_VALUE.search(payload)
        if not payload or _ENUMERATION.match(payload) or listing:
            continue
        head = payload[0]
        if head.isalnum() or head in "./~" or _MD_LINK.match(payload) or (_GLOSS.match(payload) and payload == raw):
            found.append((match.group("value").lower() + ":", payload))
    return found


def debt_faults(payload: str, board_ids: frozenset[str]) -> list[str]:
    """`mockup not reproduced: <path> + <task>` — the task named exists. With a `+`,
    only what follows it names the task; without one, the whole payload does — a
    real adopter writes `… repris par **T-00000037** (présente au board)` with no
    `+` (ec-crm-multi T-00000040-plan.md:7)."""
    _, plus, tail = payload.partition("+")
    named = _TASK_REF.findall(tail if plus else payload)
    if not named:
        return [f"`mockup not reproduced:` names no task: {payload[:90]!r}"]
    return [f"`mockup not reproduced:` names {t}, which is not on the board" for t in named if t not in board_ids]


def plan_faults(text: str, board_ids: frozenset[str]) -> list[str]:
    found = declarations(text)
    if not found:
        return [f"carries none of {CLOSED_VALUES}"]
    faults: list[str] = []
    for value, payload in found:
        if value == "mockup not reproduced:":
            faults += debt_faults(payload, board_ids)
    return faults


def is_front_path(path: str) -> bool:
    """A write-set path is a screen file by its suffix — `.scss` alone (an
    extension, not a file) has no suffix and is never one."""
    return PurePosixPath(path).suffix.lower() in FRONT_SUFFIXES


def screen_plans(plans_dir: Path, tasks: list) -> list[tuple[Path, list[str]]]:
    """Plans named after a board task whose DECLARED write-set holds a front file."""
    by_id = {str(t.get("id")): t for t in tasks if isinstance(t, dict)}
    found = []
    for plan in sorted(plans_dir.glob("*" + _PLAN_SUFFIX)):
        task = by_id.get(plan.name[: -len(_PLAN_SUFFIX)])
        front = [p for p in writeset_of(task) if is_front_path(p)] if task else []
        if front:
            found.append((plan, front))
    return found


def _board_tasks() -> list:
    """The board's tasks in its FORM (`TASKS.json` OR `tasks/`); no board under `BOARD` ⇒ the empty real arm."""
    if _TASKS_FACADE.store_form(str(ROOT)) == "absent":
        return []
    tasks = _TASKS_FACADE.lire_board_brut(str(ROOT)).get("tasks", [])
    return tasks if isinstance(tasks, list) else []


TASKS = _board_tasks()
BOARD_IDS = frozenset(str(t.get("id")) for t in TASKS if isinstance(t, dict))
REAL = screen_plans(PLANS, TASKS) if PLANS.is_dir() else []


# ---- the detector, on fixtures that CAN fail ---------------------------------

DECLARED = [
    ("no mockup: aucun écran", "no mockup:"),
    ("mockup: docs/design/x.html", "mockup:"),
    ("mockup not reproduced: docs/design/x.html + T-00000001", "mockup not reproduced:"),
    # LOT-5-plan.md:67 — the whole line in backticks.
    ("`no mockup: aucune surface visible touchée — extraction d'index.`", "no mockup:"),
    # T-00000379-plan.md:116 — bold around the value, the path in backticks.
    ("**mockup: `op-agentic-builder-kit/maquette-x/index.html`** — reproduction", "mockup:"),
    ("- no mockup: filet pytest, pas d'écran.", "no mockup:"),
    ("> **no mockup:** outil CLI", "no mockup:"),
    ("Tâches : T-1 · owner dev-multi · `no mockup: aucun écran conçu` — deux pages", "no mockup:"),
    ("Écran : aucun (no mockup: banc shell).", "no mockup:"),
    ("Chantier : x · no mockup : hooks shell, aucune surface d'écran.", "no mockup:"),
    ("`no mockup:` aucun fichier de front ni bundle au writeset.", "no mockup:"),
    # A reason opening on a gloss, inside the value's own span.
    ("no mockup: (aucun écran : texte seul)", "no mockup:"),
    ("no mockup: « aucun écran »", "no mockup:"),
    ("no mockup: — texte seul", "no mockup:"),
    ("no mockup: – texte seul", "no mockup:"),
    ("`no mockup: (texte seul)`", "no mockup:"),
    # An absolute path is no enumeration.
    ("mockup: /srv/design/x.html", "mockup:"),
    # Natural Markdown: a link, an image, curly quotes, a dash, a reason citing a value.
    ("mockup: [maquette](docs/design/x.html)", "mockup:"),
    ("mockup: ![capture](docs/design/x.png)", "mockup:"),
    ("- **mockup:** [maquette](docs/design/x.html)", "mockup:"),
    ("no mockup: “aucun écran”", "no mockup:"),
    ("no mockup: ‘aucun écran’", "no mockup:"),
    ("no mockup: - texte seul", "no mockup:"),
    ("no mockup: aucun écran, donc aucune ligne `mockup:` à nommer", "no mockup:"),
]
CITED_ONLY = [
    "les trois valeurs `mockup:` / `no mockup:` / `mockup not reproduced:`",
    "aucune surface d'écran n'est touchée, donc aucune ligne `mockup:` n'est due.",
    "`no mockup: <raison>`",
    "mockup:",
    "Pas d'écran, pas de mockup.",
    "le mockup: voir plus bas",
    # The doctrine LISTED at line start: an enumeration, with or without spaces,
    # with or without code spans, or joined by a word.
    "- `mockup:` / `no mockup:` / `mockup not reproduced:` — les trois valeurs fermées",
    "mockup: / no mockup: / mockup not reproduced:",
    "`mockup:`/`no mockup:`",
    "- `mockup:` ou `no mockup:` selon le cas",
    # A gloss after a value closed alone comments the doctrine.
    "- `no mockup:` (raison obligatoire)",
    "- `mockup:` — la valeur qui nomme la maquette",
    "- `no mockup:` - raison obligatoire",
    # A dash or a gloss with no reason behind it is no reason.
    "mockup: -",
    "no mockup: -->",
    "no mockup: - -",
    "no mockup: —",
    "no mockup: (",
    "| no mockup: — |",
]
# Values OUTSIDE the three closed forms: a near miss is no declaration.
OUT_OF_THREE = [
    "maquette: docs/design/x.html",
    "mockups: docs/design/x.html",
    "no-mockup: aucun écran",
    "mockup absent: aucun écran",
    "pas de mockup: aucun écran",
    "mockup reproduced: docs/design/x.html",
]


@pytest.mark.parametrize(("line", "value"), DECLARED, ids=range(len(DECLARED)))
def test_a_declared_line_is_recognised_through_its_markup(line: str, value: str):
    assert [v for v, _ in declarations(f"# Plan\n\n{line}\n")] == [value]


@pytest.mark.parametrize("line", CITED_ONLY + OUT_OF_THREE, ids=range(len(CITED_ONLY + OUT_OF_THREE)))
def test_prose_or_a_value_outside_the_three_is_not_a_declaration(line: str):
    text = f"# Plan\n\n{line}\n"
    assert declarations(text) == []
    assert plan_faults(text, frozenset()) == [f"carries none of {CLOSED_VALUES}"]


def test_every_closed_value_has_a_recognised_form():
    assert {value for _, value in DECLARED} == set(CLOSED_VALUES)


def test_the_gloss_bound_is_the_one_the_failure_message_states():
    assert declarations("**no mockup:** (outil CLI)\n") == []
    assert declarations("**no mockup: (outil CLI)**\n") == [("no mockup:", "(outil CLI)**")]


# ---- the debt names a task that exists ---------------------------------------

ULID = "T-01K9ZQ3B7XWMN4RT8VEHJCD2PA"
ON_BOARD = frozenset({"T-00000002", ULID})


DEBT_HOLDS = [
    "mockup not reproduced: docs/design/x.html + T-00000002",
    "mockup not reproduced: docs/design/x.html (rattachement : T-00000002) + `T-00000002`.",
    f"- **mockup not reproduced:** docs/design/x.html + {ULID}",
    # No `+`: the task is read in the whole payload — the form of a real adopter
    # plan (ec-crm-multi T-00000040-plan.md:7, `repris … par **T-00000037**`).
    "mockup not reproduced: docs/design/x.html (T-00000002)",
    "mockup not reproduced: `docs/x.html` l.389-391 / 789 — repris par **T-00000002** (présente au board)",
]
DEBT_FAULTS = [
    ("mockup not reproduced: docs/design/x.html + T-00000009", "T-00000009, which is not on the board"),
    ("mockup not reproduced: docs/design/x.html + T-01K9ZQ3B7XWMN4RT8VEHJCD2PB", "T-01K9ZQ3B7XWMN4RT8VEHJCD2PB"),
    ("mockup not reproduced: docs/design/x.html + une tâche à créer", "names no task"),
    ("mockup not reproduced: docs/design/x.html — à reprendre plus tard", "names no task"),
    ("mockup not reproduced: docs/design/x.html (T-00000009)", "T-00000009, which is not on the board"),
    # With a `+`, only what follows it names the debt's task.
    ("mockup not reproduced: docs/design/x.html (T-00000002) + à créer", "names no task"),
    # A task id inside the PATH names no task: a name suffix, an extension, a directory.
    ("mockup not reproduced: docs/design/T-00000002-maquette.html", "names no task"),
    ("mockup not reproduced: docs/captures/T-00000002.png", "names no task"),
    ("mockup not reproduced: docs/T-00000002/x.png", "names no task"),
]


@pytest.mark.parametrize("line", DEBT_HOLDS, ids=range(len(DEBT_HOLDS)))
def test_a_debt_naming_a_board_task_holds(line: str):
    assert plan_faults(f"# Plan\n\n{line}\n", ON_BOARD) == []


@pytest.mark.parametrize(("line", "fault"), DEBT_FAULTS, ids=range(len(DEBT_FAULTS)))
def test_a_debt_naming_no_board_task_is_a_fault(line: str, fault: str):
    faults = plan_faults(f"# Plan\n\n{line}\n", ON_BOARD)
    assert len(faults) == 1 and fault in faults[0], faults


def test_writeset_of_is_the_boards_reader():
    """CALLED, not paraphrased: the function runs from `tasks_requetes.py`, in the
    namespace of the `tasks.py` facade — the only way that part ever runs."""
    assert Path(writeset_of.__code__.co_filename).name == "tasks_requetes.py"
    assert "_charger_parties" in writeset_of.__globals__, "loaded outside the tasks.py facade"
    assert writeset_of({}) == writeset_of({"writeset": None}) == writeset_of({"writeset": []}) == []


def test_ulid_body_is_the_boards():
    source = STOCKAGE.read_text(encoding="utf-8")
    assert f'ULID_BODY = "{ULID_BODY}"' in source, "the copy drifted from tasks_stockage.py"
    assert _TASK_REF.fullmatch(ULID) and _TASK_REF.fullmatch("T-014") and not _TASK_REF.fullmatch("T-01k9")


# ---- the screen signal: declared write-set, never prose -----------------------

PROSE_FULL_OF_EXTENSIONS = (
    "- l'exclusion `.scss`/`.less` est une décision documentée\n"
    "EXTS  = { .ts .tsx .js .jsx .css .scss .sql .sh }\n"
    "on touchera peut-être `views/Board.jsx` plus tard\n"
)


def _plans(tmp_path: Path, names: list[str], text: str) -> Path:
    for name in names:
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_extensions_quoted_in_prose_never_make_a_screen_plan(tmp_path: Path):
    plans = _plans(tmp_path, ["T-00000001-plan.md", "LOT-9-plan.md"], PROSE_FULL_OF_EXTENSIONS)
    tasks = [{"id": "T-00000001", "writeset": [".agents/bin/x.py", "README.md"]}]
    assert screen_plans(plans, tasks) == []


def test_a_front_file_in_the_declared_writeset_makes_a_screen_plan(tmp_path: Path):
    names = ["T-00000001-plan.md", f"{ULID}-plan.md", "LOT-9-plan.md", "T-00000003-plan.md", "T-00000004-plan.md"]
    plans = _plans(tmp_path, names, "# Plan sans un mot de front\n")
    tasks = [
        {"id": "T-00000001", "writeset": ["README.md", "docs/usage.html"]},
        {"id": ULID, "writeset": ["web/src/App.tsx"]},
        {"id": "LOT-9", "writeset": None},
        {"id": "T-00000003", "writeset": None},
    ]
    found = [(p.name, f) for p, f in screen_plans(plans, tasks)]
    assert found == [("T-00000001-plan.md", ["docs/usage.html"]), (f"{ULID}-plan.md", ["web/src/App.tsx"])]


@pytest.mark.parametrize("path", ["a/b.html", "x.CSS", "s/v.scss", "c/V.jsx", "c/V.tsx", "c/V.vue", "c/S.svelte"])
def test_front_suffixes(path: str):
    assert is_front_path(path)


@pytest.mark.parametrize("path", [".scss", "a/b.py", "a/b.md", "a/b.sh", "docs/design/x.md", "web/app.ts", "web/src/"])
def test_not_front(path: str):
    assert not is_front_path(path)


# The bounds the docstring says, held to the code: a suffix it names as NOT judged
# that entered FRONT_SUFFIXES — or one judged that it still named — would make it lie.
NOT_JUDGED_SUFFIXES = (".js", ".ts", ".mjs", ".hbs", ".njk", ".jinja", ".erb", ".twig", ".php",
                       ".cshtml", ".razor", ".dart", ".swift", ".kt", ".xaml")


@pytest.mark.parametrize("suffix", NOT_JUDGED_SUFFIXES)
def test_a_screen_outside_front_suffixes_is_said_not_judged(suffix: str):
    assert not is_front_path(f"views/x{suffix}")
    assert re.search(re.escape(suffix) + r"(?!\w)", __doc__), f"{suffix} is not judged, and the docstring hides it"


def test_a_directory_only_writeset_is_said_not_judged(tmp_path: Path):
    plans = _plans(tmp_path, ["T-00000001-plan.md"], "# Plan\n")
    assert screen_plans(plans, [{"id": "T-00000001", "writeset": ["web/src/", "web/public"]}]) == []
    assert "only a directory" in __doc__


def test_exclusivity_is_not_judged_and_said_so():
    assert plan_faults("# Plan\n\nmockup: docs/design/x.html\n\nno mockup: aucun écran\n", frozenset()) == []
    assert "EXCLUSIVITY" in __doc__


# ---- the real plans ----------------------------------------------------------

@pytest.mark.parametrize(("plan", "front"), REAL, ids=[p.name for p, _ in REAL])
def test_a_screen_plan_names_its_mockup_or_declares_its_absence(plan: Path, front: list[str]):
    faults = plan_faults(plan.read_text(encoding="utf-8"), BOARD_IDS)
    assert not faults, (
        f"{plan.relative_to(ROOT)} declares front files {front} on the board and {faults} — "
        "add `no mockup: <reason>`, `mockup: <path>` or `mockup not reproduced: <path> + <task>` "
        "(a reason opening on `(`, `«` or a dash counts only inside the value's own markup: "
        "`**no mockup:** (x)` is not read, `**no mockup: (x)**` is)"
    )


@pytest.mark.skipif(not KIT.is_file(), reason="kit only: an adopter's corpus is its own")
def test_non_vacuity_the_kit_corpus_holds_screen_plans():
    """Measured 2026-10-10: 23 board-declared screen plans at 2c5bf329 (couloir-b
    36939aac: 19). A floor well below both, so the arm above cannot go green by
    judging nothing."""
    assert len(REAL) >= 15, f"only {len(REAL)} screen plans judged"


@pytest.mark.skipif(not KIT.is_file(), reason="kit only: the historical plans live in the kit")
@pytest.mark.parametrize("name", ["LOT-5-plan.md", "T-00000379-plan.md"])
def test_the_two_historical_lines_are_read_as_declarations(name: str):
    assert declarations((PLANS / name).read_text(encoding="utf-8"))
