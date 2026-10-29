"""Working language — pilot decision S-01M54GFZ9VTKTJ07AVZHKRA982 (plan T-01M54GEWXXDA6A2Z663G5SYGG0).

A converted role (5 host defs + skill judged; roster held by `render_hosts.py --check`) is written
in English; what is addressed to the pilot stays in French, and literals stay verbatim. The rule: `.agents/ref/WORKING_LANGUAGE.md`.

Witnesses: the sheet is tracked and carries the rule tokens; each converted surface points at
the sheet ONCE and carries its rule sentence; French share <= 0.05 (lexical, fenced blocks, code
spans and «…» excluded). Kit only (`.agents/IS_THE_KIT`): FROZEN fingerprints taken at 67bfe0d6
on the bodies (frontmatter excluded) — fenced blocks, «…» (whitespace collapsed) and `▸` banner
lines (sha256/16 each); PER SECTION, the multiset of code spans (one may fold over two lines),
S-/T-/L- ids and bare numbers (decimal comma read as a dot) minus ONE pointer span, and the bullet
count. The FROZEN table is
itself replayed against `git show 67bfe0d6:<p>`.
NOT SEEN (the sheet says so): a number written as a word, a rule carrying no atom, a polarity
inversion (never -> always), a verdict code translated in prose, a wrong English sentence that
keeps its atoms, the frontmatter (French share only).

EXTENSION TO EVERY DEF (S-01M5VCGTEBC76MKR63HJ2K67CE, T-01M5S9338BJP1B5RM3TG14AMYT), kit only: the
defs are FOUND by glob on the five host directories and the sources `agents/*.md` (`README.md`
excepted) — a def added later is judged at birth. Each host body carries the pointer ONCE and
`You answer in French.`; a source is judged body by body (a `comme claude` reference excepted);
French share <= 0.05 on every file. What the agent PRINTS to the pilot — the fenced blocks in order,
the «…» as a multiset, the lines and the code spans opening on `▸` — is compared byte for byte with
`git show 8c74e8d55:<path>` (develop's French version) for every def that existed there, each region
tagged with its host section (a region moved to another host section is a change); and, per host
section, every code span of the base's prose is still there byte for byte (spans may be added,
never altered or removed). A block the base did not carry is admitted only when its body is a run
of whole lines of the unfenced text of the SAME host section of the base (a printed template the
base left bare, now fenced) AND its sha256/16 is pinned, in order, in the FROZEN `ADMITTED_FENCES`
(measured at e3ec8bccf): it is compared unfenced; shrinking, growing, moving or editing it turns
red. A DELIBERATE change goes through `EXT_BASE_PAR_DEF` (def -> the literal hex sha of the commit
that made it, not HEAD's, descending from 8c74e8d55 and in HEAD's history).
NOT SEEN by the extension: the ids, numbers and bullets of the prose (load-tester's full table
only), a span ADDED, a printed format left unfenced in base and def alike, and the printed regions
of a def born after 8c74e8d55. In an adopting project the extension is skipped, announced: the
adopter's own defs stay free.
"""
from __future__ import annotations

import functools
import hashlib
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHEET = ".agents/ref/WORKING_LANGUAGE.md"
POINTER = "`" + SHEET + "`"
BASE = "67bfe0d6"
# adopting-tree: the kit identity marker does not travel (strip: .agents/IS_THE_KIT);
# absent, the frozen fingerprints are skipped, said.
IN_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
RULE_TOKENS = ("S-01M54GFZ9VTKTJ07AVZHKRA982", "written in English", "addressed to the pilot stays in French",
               "stay verbatim", "fenced or quoted between")
CEILING = 0.05
FR = frozenset("le la les des du de un une et est sont dans pour avec sans qui que ne pas jamais chaque tout toute "
               "leur sur au aux ce cette ou où être elle il se son sa ses en".split())
EN = frozenset("the an of to is are in for with without who that not never each all their at this or be it its and".split())
FENCE = re.compile(r"(?ms)^(```|~~~)[^\n]*\n.*?^\1[^\n]*$")
GUIL = re.compile(r"«[^»]*»")
# A code span may be folded over TWO lines (`COVERAGE DEGRADED — <outil> absent,` + newline + `verdict absent`).
SPAN = re.compile(r"`[^`\n]+(?:\n[^`\n]+)?`")
IDS = re.compile(r"\b[STL]-[0-9A-Z]{5,26}\b")
NUM = re.compile(r"\d+(?:[.,]\d+)?")
BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
WS = re.compile(r"\s+")
DEF_RULE = "You answer in French."
SKILL = ".agents/skills/load-test/SKILL.md"
DEFS = (".claude/agents/load-tester.md", ".codex/agents/load-tester.toml", ".github/agents/load-tester.agent.md",
        ".gemini/agents/load-tester.md", ".kimi-code/agents/load-tester.md")
RULE_SENTENCE = {**{p: DEF_RULE for p in DEFS}, SKILL: "**narrates** the verdict in French"}
CONVERTED = DEFS + (SKILL,)
# The sheet's erratum on the skill's « é » span: an ASCII-escaped JSON line shows these six ASCII
# characters (backslash, u, 0, 0, e, 9), never a literal é. chr(92) is the backslash.
ERRATUM = "JSON line shows `" + chr(92) + "u00e9`"


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def body(text: str, rel: str) -> str:
    if rel.endswith(".toml"):
        return text.split('developer_instructions = """\n', 1)[1]
    return text.split("\n---\n", 1)[1] if text.startswith("---\n") else text


def sections(b: str) -> list:
    """The body outside fenced blocks, cut before each heading line."""
    out = [[]]
    for ln in FENCE.sub("", b).split("\n"):
        if ln.startswith("#"):
            out.append([])
        out[-1].append(ln)
    return ["\n".join(s) for s in out]


def atoms(text: str) -> Counter:
    rest = FENCE.sub("", text)
    c = Counter(SPAN.findall(rest)) + Counter(IDS.findall(rest))
    c += Counter("#" + n.replace(",", ".") for n in NUM.findall(GUIL.sub("", SPAN.sub("", rest))))
    return c - Counter({POINTER: 1})


def fingerprint(text: str, rel: str) -> dict:
    b = body(text, rel)
    rest, secs = FENCE.sub("", b), sections(b)
    return {"blocs": tuple(sorted(_h(m.group(0)) for m in FENCE.finditer(b))),
            "guillemets": tuple(sorted(_h(WS.sub(" ", g)) for g in GUIL.findall(rest))),
            "bannieres": tuple(sorted(_h(ln.rstrip()) for ln in rest.split("\n") if ln.startswith("▸"))),
            "atomes": tuple((sum(c.values()), _h("\n".join(sorted(c.elements())))) for c in map(atoms, secs)),
            "structure": tuple(sum(1 for ln in s.split("\n") if BULLET.match(ln)) for s in secs)}


def french_share(text: str) -> float:
    w = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", GUIL.sub("", SPAN.sub("", FENCE.sub("", text))).lower())
    f, e = sum(x in FR for x in w), sum(x in EN for x in w)
    return f / (f + e) if f + e else 1.0


def drift(text: str, rel: str) -> list:
    got, want = fingerprint(text, rel), FROZEN[rel]
    return [k for k in want if got[k] != want[k]]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


_DEF_FROZEN = {
    "guillemets": ("570f9a90c0759976", "e38fd255492545de", "feb924a4b422c0bd"),
    "bannieres": ("9fbee86fd35c4e5f", "cd5cbbaa4828d534"),
    "atomes": ((3, "ed439fcb4510b16d"), (9, "2128c7fa91957d51"), (72, "1fbeb507f2d33e41"), (63, "8da8a40c12f47af2"),
               (47, "9e403c1c6e7b3e62"), (12, "251b3a1214f0394f"), (20, "704781bcfbe4c75d"), (17, "47b4c438bc5cfa57"),
               (15, "8acadc2eb2a065d5"), (4, "458b9e9431dc58dc"), (0, "e3b0c44298fc1c14")),
    "structure": (0, 4, 7, 4, 12, 7, 0, 0, 3, 0, 0),
}
FROZEN: dict = {
    **{p: {"blocs": ("796c2af9f860d0c4", "9f820f32760c62d7"), **_DEF_FROZEN} for p in DEFS if not p.endswith(".toml")},
    ".codex/agents/load-tester.toml": {"blocs": ("46bb46d9e003c506", "796c2af9f860d0c4"), **_DEF_FROZEN},
    SKILL: {
        "blocs": ("3912903feed12466", "9f820f32760c62d7", "aad6818168c05e72", "fb5655c507265115"),
        "guillemets": ("412cbbed6ff104cb", "4a86e77e1134d432", "e38fd255492545de", "f4e1283a3c9523aa", "feb924a4b422c0bd"),
        "bannieres": (),
        "atomes": ((0, "e3b0c44298fc1c14"), (1, "745443363406ec55"), (6, "d0aa32d3206ac2ba"), (6, "e3e78fca2745275b"),
                   (0, "e3b0c44298fc1c14"), (105, "31ce5e862b264e6b"), (44, "9f522444eec1cc14"),
                   (45, "421efbc14e139b11"), (28, "430d9dd38d5faf40"), (10, "dc4c3bac0bc6e1f3"),
                   (43, "d817644edd64e7ad"), (51, "d6baf75cd19988da"), (37, "5f6666e3fd9b5505"),
                   (47, "20b0fefa718e778d"), (7, "4c3fc0cb3741309c"), (4, "458b9e9431dc58dc"),
                   (18, "4a308fde1bf9cd60"), (13, "2e8193840f4ad745"), (20, "a0c1217a9179d6d2"),
                   (13, "fb584676d1ef7748"), (14, "77eb06b9434fac19"), (5, "93eedf43b16192ab")),
        "structure": (0, 0, 3, 0, 0, 15, 4, 7, 5, 3, 5, 8, 7, 12, 6, 0, 0, 0, 0, 3, 0, 0),
    },
}


# --- The extension to every def (S-01M5VCGTEBC76MKR63HJ2K67CE) -------------------------------------
#: The French version the extension took the printed text from (develop, merged by T-01M5S9338BJP1B5RM3TG14AMYT).
EXT_BASE = "8c74e8d55"
#: THE DELIBERATE CHANGE PATH (T-01M5S9338BJP1B5RM3TG14AMYT, `.agents/ref/WORKING_LANGUAGE.md`
#: § What the bench sees): def name -> the commit that deliberately changed a printed region or a code
#: span of that def, written by a LATER commit than that one. The def is then compared with that commit
#: instead of EXT_BASE; `test_per_def_bases_are_deliberate` refuses a value that is not a literal hex sha
#: (7-40) naming a commit, HEAD's own commit, a commit that does not descend from EXT_BASE or is not in
#: HEAD's history, and a name no def carries. Never a way to hide a translation.
EXT_BASE_PAR_DEF: dict[str, str] = {
    # 827b4c944: the two off-chain defs carry, like planner and plan-critic, the pointers to
    # `.agents/ref/PLAN_GRAMMAIRE.md` § 1-3 instead of the full plan-grammar clauses (CHANGELOG,
    # T-01M5S9338BJP1B5RM3TG14AMYT) — the clauses' spans left with them; every other span is develop's.
    "planner-sonnet": "827b4c944",
    "plan-critic-sonnet-max": "827b4c944",
}
#: FROZEN at e3ec8bccf (T-01M5S9338BJP1B5RM3TG14AMYT): def file -> host section -> the sha256/16 of the
#: body of each fenced block the base did not carry and that is admitted, in order. Only these
#: blocks are put back unfenced (`admit`), and only when their body is still a run of whole lines of
#: the SAME host section of the base; `test_admitted_fences_are_the_frozen_ones` holds the table equal
#: to what is admitted. Fencing another bare template, or shrinking, growing, moving or editing one of
#: these, changes a hash here: the visible decision, never a silent admission.
_CODEX_PLANNER, _CODEX_COMMUNICATOR = ("25256169effe713a",), ("e1f8ea0355617650", "171067701bd945d8")
_COPILOT_TEMPLATE = ("646258ab63282c33",)
ADMITTED_FENCES: dict = {
    ".codex/agents/board-reporter.toml": {"claude": ("057f67a6d488c211",)},
    ".codex/agents/communicator.toml": {"claude": _CODEX_COMMUNICATOR},
    ".codex/agents/exec-critic.toml": {"claude": ("2400384f34b0bec5",)},
    ".codex/agents/orchestrator.toml": {"claude": ("9415541a6b4b0dce",)},
    ".codex/agents/plan-critic.toml": {"claude": ("07c2dbc545b8a289",)},
    ".codex/agents/planner.toml": {"claude": _CODEX_PLANNER},
    ".github/agents/board-reporter.agent.md": {"claude": _COPILOT_TEMPLATE},
    ".github/agents/communicator.agent.md": {"claude": _COPILOT_TEMPLATE},
    "agents/board-reporter.md": {"<!-- hote: codex -->": ("057f67a6d488c211",),
                                 "<!-- hote: copilot -->": _COPILOT_TEMPLATE},
    "agents/communicator.md": {"<!-- hote: codex -->": _CODEX_COMMUNICATOR,
                               "<!-- hote: copilot -->": _COPILOT_TEMPLATE},
    "agents/exec-critic.md": {"<!-- hote: codex -->": ("2400384f34b0bec5",)},
    "agents/orchestrator.md": {"<!-- hote: codex -->": ("9415541a6b4b0dce",)},
    "agents/plan-critic.md": {"<!-- hote: codex -->": ("07c2dbc545b8a289",)},
    "agents/planner.md": {"<!-- hote: codex -->": _CODEX_PLANNER},
}
HOST_GLOBS = ((".claude/agents", "*.md"), (".codex/agents", "*.toml"), (".github/agents", "*.agent.md"),
              (".gemini/agents", "*.md"), (".kimi-code/agents", "*.md"))
SOURCES = "agents"
NOT_A_SOURCE = frozenset({"README.md"})
SECTION = re.compile(r"(?m)^<!-- hote: [^\n]* -->\n")
#: The same sentinel, captured: a source cut into [claude body, sentinel, body, sentinel, body…].
SECTION_CUT = re.compile(r"(?m)(^<!-- hote: [^\n]* -->\n)")
BODY_MARK = "<!-- corps -->\n"
AS_CLAUDE = "<!-- corps: comme claude -->"
BANNER_SPAN = re.compile(r"`▸[^`\n]*`")
#: CLOSED — the defs exempt from the pointer-once and the `You answer in French.` checks, and from
#: those two ONLY (T-01M5S9338BJP1B5RM3TG14AMYT, orchestrator ruling): `language-detector` prints one
#: JSON object and never addresses the pilot, and its def is sha-pinned by
#: `.agents/evals/fixtures/detector_spring_angular.observed.json` (48 real host replays, re-recording
#: them is out of reach). It stays judged by the English share and the printed regions. Its length is
#: pinned to 1: a second def never enters without a ruling of its own.
NO_POINTER = ("language-detector",)
NO_POINTER_SIZE = 1


def def_name(rel: str) -> str:
    return rel.split("/")[-1].split(".")[0]


def exemption_faults(exempt: tuple, defs: tuple) -> list:
    """What is wrong with an exemption tuple: a size other than the pinned one, a duplicate, a name no
    def carries."""
    names = {def_name(p) for p in defs}
    out = [f"size {len(exempt)} != {NO_POINTER_SIZE}"] if len(exempt) != NO_POINTER_SIZE else []
    out += ["duplicate"] if len(set(exempt)) != len(exempt) else []
    return out + [f"{n}: no such def" for n in exempt if n not in names]


def discover_defs(root: Path) -> tuple:
    """Every def file of `root`: the five host directories, then the sources (README excepted)."""
    found = [p for d, g in HOST_GLOBS for p in sorted((root / d).glob(g))]
    found += [p for p in sorted((root / SOURCES).glob("*.md")) if p.name not in NOT_A_SOURCE]
    return tuple(p.relative_to(root).as_posix() for p in found)


def bodies(text: str, rel: str) -> list:
    """The bodies a file carries: one for a host def; for a source, its claude body and every host
    body it writes out (a `comme claude` reference is not a body)."""
    if not rel.startswith(SOURCES + "/"):
        return [body(text, rel)]
    parts = SECTION.split(text)
    out = [body(parts[0], rel)]
    for part in parts[1:]:
        if AS_CLAUDE in part:
            continue
        assert BODY_MARK in part, f"{rel}: a host section with no body sentinel"
        out.append(part.split(BODY_MARK, 1)[1])
    return out


def cut(text: str) -> list:
    """`text` cut at its host sentinels: [(key, part)], key `claude` for what precedes the first
    sentinel, then each sentinel line (newline stripped). A host file is one `claude` part."""
    parts = SECTION_CUT.split(text)
    return list(zip(["claude"] + [s.rstrip("\n") for s in parts[1::2]], parts[::2]))


def printed(text: str) -> dict:
    """What the agent prints to the pilot, byte for byte, PER HOST SECTION: fenced blocks in order,
    «…» as a multiset, lines and code spans opening on `▸`, each tagged with its section key. A source
    is cut at its host sentinels first, so that no region runs from one host body into the next (a
    lone `«` in one body would reach the `»` of the following one), and a region moved from one host
    section to another is a change."""
    out = {"blocs": [], "guillemets": [], "bannieres": [], "spans_banniere": []}
    for k, part in cut(text):
        rest = FENCE.sub("", part)
        out["blocs"] += [(k, m.group(0)) for m in FENCE.finditer(part)]
        out["guillemets"] += [(k, g) for g in GUIL.findall(rest)]
        out["bannieres"] += [(k, ln) for ln in rest.split("\n") if ln.startswith("▸")]
        out["spans_banniere"] += [(k, s) for s in BANNER_SPAN.findall(rest)]
    out["guillemets"].sort()
    return out


def _inner(block: str) -> str:
    return block.split("\n", 1)[1].rsplit("\n", 1)[0] if block.count("\n") >= 2 else ""


def admit(text: str, base: str, pins: dict) -> tuple:
    """(`text` with its admitted blocks put back unfenced, {section: (sha256/16 of each admitted body,
    in order)}). A fenced block that the SAME host section of `base` does not carry is admitted only
    when (1) its body is, byte for byte, a run of whole lines of that section's unfenced text in
    `base`, and (2) its sha256/16 is the next one `pins` (a FROZEN entry of `ADMITTED_FENCES`) holds
    for that section. Fencing a printed template the base left bare changes nothing; translating,
    editing, shrinking, growing or moving it, or taking a run of another host section, leaves a new
    block, and the comparison goes red."""
    base_parts = dict(cut(base))
    out, used = [], {}
    parts = SECTION_CUT.split(text)
    for i, (k, part) in enumerate(cut(text)):
        bpart = base_parts.get(k)
        want = Counter(m.group(0) for m in FENCE.finditer(bpart or ""))
        bare = "\n" + FENCE.sub("", bpart) + "\n" if bpart is not None else None
        todo = list(pins.get(k, ()))

        def unfence(m: re.Match, want=want, bare=bare, todo=todo, k=k) -> str:
            block = m.group(0)
            if want[block] > 0:
                want[block] -= 1
                return block
            inner = _inner(block)
            if inner and bare is not None and "\n" + inner + "\n" in bare and todo and todo[0] == _h(inner):
                used.setdefault(k, []).append(todo.pop(0))
                return inner
            return block

        out += ([parts[2 * i - 1]] if i else []) + [FENCE.sub(unfence, part)]
    return "".join(out), {k: tuple(v) for k, v in used.items()}


def admitted(text: str, base: str, rel: str) -> str:
    """`text` with the blocks `ADMITTED_FENCES[rel]` pins put back unfenced — see `admit`."""
    return admit(text, base, ADMITTED_FENCES.get(rel, {}))[0]


def spans_by_section(text: str) -> dict:
    """Per host section (`claude` for what precedes the first sentinel, then each sentinel line), the
    multiset of the code spans of the prose — fenced blocks out, whitespace inside a span collapsed."""
    return {k: Counter(WS.sub(" ", s) for s in SPAN.findall(FENCE.sub("", b))) for k, b in cut(text)}


def lost_spans(text: str, base: str, rel: str) -> dict:
    """The code spans of `base` that `text` no longer carries, per host section (a span ADDED is free)."""
    got, want = spans_by_section(admitted(text, base, rel)), spans_by_section(base)
    lost = {k: dict(c - got.get(k, Counter())) for k, c in want.items()}
    return {k: v for k, v in lost.items() if v}


@functools.lru_cache(maxsize=None)
def show(rev: str, rel: str) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"{rev}:{rel} unreadable: {r.stderr.strip()}"
    return r.stdout


def base_of(rel: str) -> str:
    """The commit `rel` is compared with: its deliberate change when `EXT_BASE_PAR_DEF` names it."""
    return EXT_BASE_PAR_DEF.get(def_name(rel), EXT_BASE)


def _is_ancestor(old: str, new: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", old, new],
                          capture_output=True, timeout=60).returncode == 0


def _commit(rev: str) -> str:
    """The full sha `rev` names as a commit, or "" when it names none."""
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", rev + "^{commit}"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ""


HEX_SHA = re.compile(r"[0-9a-f]{7,40}")


def base_faults(mapping: dict, defs: tuple) -> list:
    """What is wrong with a per-def base mapping: a name no def carries; a value that is not a literal
    hex sha (`HEAD`, a branch or a tag name moves under the mapping) or names no commit; the commit of
    HEAD itself (the def would be compared with itself); a commit that does not descend from EXT_BASE;
    a commit outside HEAD's history."""
    names, head = {def_name(p) for p in defs}, _commit("HEAD")
    out = [f"{n}: no such def" for n in mapping if n not in names]
    for n, c in mapping.items():
        sha = _commit(c) if HEX_SHA.fullmatch(c) else ""
        if not HEX_SHA.fullmatch(c):
            out.append(f"{n}: {c!r} is not a hex sha of 7 to 40 characters")
        elif not sha:
            out.append(f"{n}: {c} names no commit")
        elif sha == head:
            out.append(f"{n}: {c} is HEAD itself")
        else:
            out += [f"{n}: {c} does not descend from {EXT_BASE}"] if not _is_ancestor(EXT_BASE, sha) else []
            out += [f"{n}: {c} is not in HEAD's history"] if not _is_ancestor(sha, head) else []
    return out


def _base_paths() -> frozenset:
    r = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", EXT_BASE], capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    return frozenset(r.stdout.split()) if r.returncode == 0 else frozenset()


KIT_DEFS = discover_defs(ROOT) if IN_KIT else ()
BASE_PATHS = _base_paths() if IN_KIT else frozenset()
#: Every kit def but load-tester's host files, which the full FROZEN table above holds.
FROZEN_EXT = tuple(p for p in KIT_DEFS if p in BASE_PATHS and p not in DEFS)
EXT_SKIP = pytest.mark.skipif(not IN_KIT, reason="adopting project: the extension binds the kit's defs only — "
                                                 "your own defs stay free; load-tester and its skill stay judged")


@EXT_SKIP
def test_every_def_is_discovered():
    names = {d: {p.split("/")[-1].split(".")[0] for p in KIT_DEFS if p.startswith(d + "/")}
             for d in [d for d, _ in HOST_GLOBS] + [SOURCES]}
    assert names[".claude/agents"], "no def found: the extension would judge nothing"
    assert all(n == names[".claude/agents"] for n in names.values()), names
    assert set(DEFS) <= set(KIT_DEFS)
    assert BASE_PATHS, f"{EXT_BASE} unreadable (shallow clone?): the printed regions would be judged against nothing"


@EXT_SKIP
@pytest.mark.parametrize("rel", KIT_DEFS)
def test_every_def_body_points_at_sheet_once_and_answers_in_french(rel):
    if def_name(rel) in NO_POINTER:
        return  # exempt from these two checks only — see NO_POINTER
    text = read(rel)
    for i, b in enumerate(bodies(text, rel)):
        assert b.count(POINTER) == 1, f"{rel} body {i}: pointer {POINTER} x{b.count(POINTER)}, expected 1"
        assert DEF_RULE in b, f"{rel} body {i}: {DEF_RULE!r} missing"


@EXT_SKIP
@pytest.mark.parametrize("rel", KIT_DEFS)
def test_every_def_is_english(rel):
    s = french_share(read(rel))
    assert s <= CEILING, f"{rel}: French share {s:.3f} > {CEILING}"


@EXT_SKIP
@pytest.mark.parametrize("rel", FROZEN_EXT)
def test_every_def_prints_the_french_of_its_base(rel):
    base = show(base_of(rel), rel)
    got, want = printed(admitted(read(rel), base, rel)), printed(base)
    assert got == want, f"{rel}: printed regions {[k for k in want if got[k] != want[k]]} differ from {base_of(rel)}"


@EXT_SKIP
@pytest.mark.parametrize("rel", FROZEN_EXT)
def test_every_def_keeps_the_code_spans_of_its_base(rel):
    lost = lost_spans(read(rel), show(base_of(rel), rel), rel)
    assert lost == {}, f"{rel}: code spans of {base_of(rel)} altered or removed, per host section: {lost}"


@EXT_SKIP
def test_admitted_fences_are_the_frozen_ones():
    used = {rel: admit(read(rel), show(base_of(rel), rel), ADMITTED_FENCES.get(rel, {}))[1] for rel in FROZEN_EXT}
    assert {r: u for r, u in used.items() if u} == ADMITTED_FENCES, "ADMITTED_FENCES is not what is admitted"
    # mutants on the Codex communicator: its tasks.py block (the second admitted one)
    rel = ".codex/agents/communicator.toml"
    cbase, cur, pins = show(base_of(rel), rel), read(rel), ADMITTED_FENCES[rel]
    blocks = [m for m in FENCE.finditer(cur) if _h(_inner(m.group(0))) == pins["claude"][1]]
    assert len(blocks) == 1, "base red: the tasks.py block of the Codex communicator is not found"
    blk = blocks[0].group(0)
    opening, closing, lines = blk.split("\n", 1)[0], blk.rsplit("\n", 1)[1], _inner(blk).split("\n")
    assert lines[1].startswith("  # Pour une question ETROITE"), "base red: the block's first comment line moved"
    bare = "\n" + FENCE.sub("", cbase) + "\n"
    after = bare.split("\n" + lines[-1] + "\n", 1)[1].split("\n", 1)[0]  # the base line after the block
    fenced = {  # mutant name -> (text before the new fence, new fence body, text after it)
        "fence moved below its first comment line, that line translated":
            (lines[0] + "\n  # For a NARROW question, ask the TOOL, not yourself:", lines[2:], ""),
        "fence shrunk by its first line": (lines[0], lines[1:], ""),
        "fence shrunk by its last line": ("", lines[:-1], lines[-1]),
        "fence grown over the base's next line": ("", lines + [after], "")}
    for name, (pre, inner, post) in fenced.items():
        new = (pre + "\n" if pre else "") + "\n".join([opening] + inner + [closing]) + ("\n" + post if post else "")
        mut = cur.replace(blk, new, 1)
        assert mut != cur, f"mutant {name} changed nothing"
        assert "\n" + "\n".join(inner) + "\n" in bare, f"mutant {name}: its body must stay a run of the base"
        assert printed(admitted(mut, cbase, rel)) != printed(cbase), f"mutant {name} survives"
    # a body that starts mid-line is no run of whole lines, even pinned
    cutoff = "\n".join([lines[0][2:]] + lines[1:])
    assert cutoff in bare and not admit(cur.replace(blk, "\n".join([opening, cutoff, closing]), 1), cbase,
                                        {"claude": (pins["claude"][0], _h(cutoff))})[1].get("claude", ())[1:], (
        "a body cut mid-line stays admitted")
    # a pinned body taken from ANOTHER host section of the base is refused: the copilot template of the
    # communicator source, moved into its codex section
    src = "agents/communicator.md"
    s_cur, s_base = read(src), show(base_of(src), src)
    tmpl = next(m.group(0) for k, p in cut(s_cur) if k == "<!-- hote: copilot -->" for m in FENCE.finditer(p)
                if _h(_inner(m.group(0))) == _COPILOT_TEMPLATE[0])
    codex_key = "<!-- hote: codex -->"
    cross = s_cur.replace(codex_key + "\n", codex_key + "\n" + tmpl + "\n", 1)
    crossed = {**ADMITTED_FENCES[src], codex_key: _COPILOT_TEMPLATE + ADMITTED_FENCES[src][codex_key]}
    assert "\n" + _inner(tmpl) + "\n" in "\n" + FENCE.sub("", s_base) + "\n", "base red: a whole-file run must hold"
    assert admit(cross, s_base, crossed)[1] != crossed, "a block admitted from another host section stays green"
    # a «…» moved from the claude body into the codex body: same multiset over the file, other section
    k0, claude_part = cut(s_cur)[0]
    quote = GUIL.search(FENCE.sub("", claude_part)).group(0)
    moved = s_cur.replace(quote, "", 1).replace(codex_key + "\n", codex_key + "\n" + quote + "\n", 1)
    blind = sorted(g for _, g in printed(moved)["guillemets"]) == sorted(g for _, g in printed(s_cur)["guillemets"])
    assert k0 == "claude" and blind and printed(moved) != printed(s_cur), (
        "a region moved across host sections stays green")


@EXT_SKIP
def test_per_def_bases_are_deliberate():
    assert base_faults(EXT_BASE_PAR_DEF, KIT_DEFS) == [], base_faults(EXT_BASE_PAR_DEF, KIT_DEFS)
    head = _commit("HEAD")
    branch = subprocess.run(["git", "-C", str(ROOT), "symbolic-ref", "-q", "--short", "HEAD"], capture_output=True,
                            text=True, timeout=60).stdout.strip() or "develop"
    # mutants: a commit older than EXT_BASE (symbolic and hex), a name no def carries, a symbolic ref
    # (HEAD, a branch), HEAD's own sha (full and short)
    for name, mapping, why in (
            ("older, symbolic", {"planner": EXT_BASE + "~1"}, "is not a hex sha"),
            ("older, hex", {"planner": _commit(EXT_BASE + "~1")[:12]}, f"does not descend from {EXT_BASE}"),
            ("no such def", {"no-such-def": EXT_BASE}, "no such def"),
            ("HEAD", {"planner": "HEAD"}, "is not a hex sha"),
            ("branch", {"planner": branch}, "is not a hex sha"),
            ("HEAD's sha", {"planner": head}, "is HEAD itself"),
            ("HEAD's short sha", {"planner": head[:9]}, "is HEAD itself"),
            ("no commit", {"planner": "0000000"}, "names no commit")):
        faults = base_faults(mapping, KIT_DEFS)
        assert [f for f in faults if why in f], f"mutant {name} {mapping}: {faults} lacks {why!r}"
    assert base_faults({"planner": EXT_BASE}, KIT_DEFS) == [], "EXT_BASE itself must stay an admitted base"


@EXT_SKIP
def test_extension_mutants(tmp_path):
    rel = ".claude/agents/exec-critic.md"
    base = read(rel)
    assert rel in FROZEN_EXT and printed(base) == printed(show(EXT_BASE, rel)) and not lost_spans(
        base, show(EXT_BASE, rel), rel), "base red: the mutants would measure nothing"
    # a code span translated, or removed, turns red; a span added stays green
    for name, mut in {"span traduit": base.replace("`preuve: non fournie`", "`proof: not provided`", 1),
                      "span retire": base.replace("`preuve: non fournie`", "preuve non fournie", 1)}.items():
        assert mut != base and lost_spans(mut, show(EXT_BASE, rel), rel), f"mutant {name} survives"
    assert lost_spans(base + "\n`span neuf`\n", show(EXT_BASE, rel), rel) == {}, "an added span must stay free"
    # the Codex template develop left bare, now fenced: admitted verbatim, refused once translated
    codex = ".codex/agents/exec-critic.toml"
    cbase, cur = show(EXT_BASE, codex), read(codex)
    assert printed(cur) != printed(cbase) and printed(admitted(cur, cbase, codex)) == printed(cbase), (
        "base red: the fenced Codex template must be a new block, admitted as develop's bare text")
    translated = cur.replace("CAUSE_RACINE (si NO_GO)", "CAUSE_RACINE (if NO_GO)", 1)
    assert translated != cur and printed(admitted(translated, cbase, codex)) != printed(cbase), (
        "mutant gabarit Codex traduit survives")
    for name, mut in {"bloc traduit": base.replace("preuve: <commande/sortie", "proof: <command/output", 1),
                      "guillemets": base.replace("« mode réfutation »", '"refutation mode"', 1),
                      "pointeur double": base + "\n" + POINTER_LINE + "\n",
                      "pointeur absent": base.replace(POINTER, "`.agents/ref/OTHER.md`", 1),
                      "consigne absente": base.replace(DEF_RULE, "", 1)}.items():
        assert mut != base, f"mutant {name} changed nothing"
        bad = printed(mut) != printed(base) or [b for b in bodies(mut, rel)
                                                  if b.count(POINTER) != 1 or DEF_RULE not in b]
        assert bad, f"mutant {name} survives"
    span = read(".claude/agents/reverse-engineer.md")
    assert printed(span.replace("<action en une ligne>", "<one-line action>", 1)) != printed(span), "banner span"
    # a def added later, in a host directory and in its source, is found and judged at birth
    for d, _ in HOST_GLOBS:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / SOURCES).mkdir()
    (tmp_path / ".claude/agents/nouveau.md").write_text("---\nname: nouveau\n---\nYou review the plan.\n",
                                                      encoding="utf-8")
    (tmp_path / SOURCES / "nouveau.md").write_text(
        "---\nname: nouveau\n---\nYou review the plan. " + DEF_RULE + "\n\n" + POINTER_LINE + "\n<!-- hote: codex -->\n"
        'name = "nouveau"\n' + BODY_MARK + "You review the plan.\n", encoding="utf-8")
    (tmp_path / SOURCES / "README.md").write_text("Mode d'emploi.\n", encoding="utf-8")
    found = discover_defs(tmp_path)
    assert found == (".claude/agents/nouveau.md", "agents/nouveau.md")
    host_body = bodies((tmp_path / found[0]).read_text(encoding="utf-8"), found[0])
    assert [b for b in host_body if b.count(POINTER) != 1], "a new host def without the pointer stays green"
    src_bodies = bodies((tmp_path / found[1]).read_text(encoding="utf-8"), found[1])
    assert len(src_bodies) == 2 and src_bodies[0].count(POINTER) == 1 and src_bodies[1].count(POINTER) == 0, (
        "the codex body of the source, written without the pointer, must be seen on its own")


@EXT_SKIP
def test_the_pointer_exemption_stays_closed():
    assert exemption_faults(NO_POINTER, KIT_DEFS) == [], exemption_faults(NO_POINTER, KIT_DEFS)
    # mutants: a second def slipped into the tuple, a name no def carries, the tuple emptied
    assert exemption_faults(NO_POINTER + ("planner",), KIT_DEFS), "a second exempt def stays green"
    assert exemption_faults(("no-such-def",), KIT_DEFS), "an exemption naming no def stays green"
    assert exemption_faults((), KIT_DEFS), "an emptied exemption stays green"
    # the exempt def stays judged by the printed-region check, every file of it (five hosts + source)
    exempt = [p for p in KIT_DEFS if def_name(p) in NO_POINTER]
    assert len(exempt) == 6 and set(exempt) <= set(FROZEN_EXT), exempt


POINTER_LINE = ("Working language: " + POINTER + " — these instructions are\n"
                "English; what you write for the pilot stays French, literals verbatim.")


def test_sheet_tracked_and_carries_rule():
    assert subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", SHEET],
                          capture_output=True, timeout=60).returncode == 0, f"{SHEET} is not tracked"
    assert [t for t in RULE_TOKENS if t not in read(SHEET)] == []


def test_sheet_erratum_carries_the_escaped_value():
    assert ERRATUM in read(SHEET), f"{SHEET}: the erratum must show the escaped form {ERRATUM!r}"


@pytest.mark.parametrize("rel", CONVERTED)
def test_converted_points_at_sheet_once(rel):
    assert read(rel).count(POINTER) == 1


@pytest.mark.parametrize("rel", CONVERTED)
def test_converted_carries_rule_sentence(rel):
    assert RULE_SENTENCE[rel] in body(read(rel), rel), f"{rel}: rule sentence {RULE_SENTENCE[rel]!r} missing"


@pytest.mark.parametrize("rel", CONVERTED)
def test_converted_is_english(rel):
    s = french_share(read(rel))
    assert s <= CEILING, f"{rel}: French share {s:.3f} > {CEILING}"


@pytest.mark.skipif(not IN_KIT, reason="adopting project: load-tester surfaces are yours, frozen fingerprints not judged")
@pytest.mark.parametrize("rel", CONVERTED)
def test_pilot_facing_literals_and_rule_atoms_frozen(rel):
    assert drift(read(rel), rel) == [], f"{rel}: drift in {drift(read(rel), rel)} vs {BASE}"


@pytest.mark.skipif(not IN_KIT, reason="adopting project: the base commit of the kit is not in your history")
@pytest.mark.parametrize("rel", CONVERTED)
def test_frozen_table_is_the_base(rel):
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE}:{rel}"], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"{BASE}:{rel} unreadable (shallow clone?): {r.stderr.strip()}"
    assert drift(r.stdout, rel) == [], f"FROZEN[{rel}] is not the fingerprint of {BASE}"


def test_codex_prose_is_the_claude_prose():
    """The codex def is a second copy of the claude prose (agents/load-tester.md); hold them equal."""
    c = FENCE.sub("", body(read(DEFS[0]), DEFS[0])).strip()
    x = FENCE.sub("", body(read(DEFS[1]), DEFS[1])).rsplit('"""', 1)[0].strip()
    assert c == x, f"{DEFS[1]}: prose differs from {DEFS[0]} (fenced blocks excluded)"


def test_mutants():
    rel = DEFS[0]
    fr = "Tu es le testeur de charge. Tu ne rends jamais ton verdict, tu recopies celui du runner pour le pilote."
    en = "You are the load tester. You never issue your own verdict; you copy the runner's verdict."
    assert french_share(fr) > CEILING and french_share(en) <= CEILING
    assert french_share(en + "\n```text\n" + fr + "\n```\n« " + fr + " »") <= CEILING
    if not IN_KIT:
        pytest.skip("adopting project: frozen-fingerprint mutants not judged")
    base = read(rel)
    assert drift(base, rel) == []
    span = "`juger`"
    moved = base.replace(span, "`x`", 1).rstrip("\n") + " " + span + "\n"
    moved = moved.replace("`x`", "", 1)
    assert atoms(body(moved, rel)) == atoms(body(base, rel)), "the section mutant must keep the whole multiset"
    for name, mut in {"sortie": base.replace("(aucun verdict)", "(no verdict)", 1),
                      "guillemets": base.replace("\n## ", "\n« neuf »\n## ", 1),
                      "nombre": base.replace("15 min", "45 min", 1),
                      "puce": re.sub(r"(?m)^- [^\n]*\n", "", base, count=1),
                      "banniere": base.replace("verdict du runner recopié", "runner verdict copied", 1),
                      "span replie": base.replace("<outil> absent,\n  verdict absent`", "<tool> missing,\n  verdict missing`", 1),
                      "section": moved}.items():
        assert mut != base and drift(mut, rel) != [], f"mutant {name} survives"
    reflowed = base.replace("« garantie »", "«  garantie\n  »", 1)
    assert reflowed != base and drift(reflowed, rel) == [], "whitespace inside «…» must not count"
    assert RULE_SENTENCE[rel] not in body(base.replace(DEF_RULE, "", 1), rel)
