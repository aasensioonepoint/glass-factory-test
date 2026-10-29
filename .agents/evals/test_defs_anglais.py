#!/usr/bin/env python3
"""The PROSE of every agent definition is English; what it prints to the pilot stays French.

Rule: `.agents/ref/WORKING_LANGUAGE.md` — pilot decision S-01M54GFZ9VTKTJ07AVZHKRA982, extended to
every def by S-01M5VCGTEBC76MKR63HJ2K67CE (pilot order of 2026-10-25, T-01M5S9338BJP1B5RM3TG14AMYT).
The agents answer the pilot in French; their instructions are English, and what they PRINT to the
pilot — fenced blocks, lines opening on `▸`, «…» quotations — stays French, byte for byte, held by
`.agents/evals/test_working_language.py`. The two benches split the text along the same regions:
that one freezes the printed regions, this one counts French in what is left.

WHAT IT JUDGES.
* The defs are DISCOVERED by glob — never a list of names — on the five host directories
  (`.claude/agents/*.md`, `.codex/agents/*.toml`, `.github/agents/*.agent.md`,
  `.gemini/agents/*.md`, `.kimi-code/agents/*.md`), on the single sources `agents/*.md`
  (`README.md` excepted) and on the Cursor renders `.cursor/rules/*.mdc`: a def added later, in its
  source or on a host, is judged at birth.
* For each file, its PROSE: the whole text (frontmatter and body) minus fenced blocks, «…»
  quotations, lines opening on `▸` and inline backtick spans, minus the CLOSED allow-list
  `KEPT_FRENCH` of exact phrases kept by rule; on what remains, the closed counter of 34 French
  tool-words must find 0.
* No def says `closing pair`, `pair of critics` or `critic pair`: the closing review is ONE critic
  (S-00004500), and a "pair" there is the defect, never a translation of "binôme".
* Every def carries `You answer in French.`; the three runner defs carry the claude body on the
  four other hosts; the counter holds exactly 34 words; no def body is empty.
* The `communicator` keeps, in every file, the French headings it prints to the pilot (rule (e));
  a RATCHET caps the inline-backtick spans of the prose that carry 2 French tool-words or more (the
  counter does not see backticks, the ratchet does); the doctrine line of `AGENTS.md` and of
  `.github/copilot-instructions.md` stays written, pointing at the sheet and at both benches.

WHAT IT DOES NOT JUDGE (bound). It counts French TOOL-WORDS in the prose. A French word inside
backticks, a French sentence made only of words outside the 34, and anything inside a printed
region are not seen here (the printed regions are frozen by the other bench, for the defs that
existed at its base). It judges neither the meaning nor the quality of the English, nor that an
agent really answers in French. It binds the KIT's defs only: in an adopting project (no
`.agents/IS_THE_KIT`) the whole module is skipped, with the reason printed — an adopter's own defs
stay in the language it chooses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: the kit marker does not travel; its absence skips this whole module, announced.
IS_THE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(
    not IS_THE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant) — the English rule "
                           "binds the kit's defs, never an adopter's own")

#: The five host directories and the glob of each: the population is DERIVED, never listed.
HOSTS = {
    "claude": (".claude/agents", "*.md"),
    "codex": (".codex/agents", "*.toml"),
    "copilot": (".github/agents", "*.agent.md"),
    "gemini": (".gemini/agents", "*.md"),
    "kimi": (".kimi-code/agents", "*.md"),
}
#: The single sources the hosts are rendered from, and the Cursor renders (a derived target).
RENDERED_FROM = {
    "source": ("agents", "*.md"),
    "cursor": (".cursor/rules", "*.mdc"),
}
PLACES = {**HOSTS, **RENDERED_FROM}
#: Files of `agents/` that are not sources (`render_hosts.NON_SOURCES`).
NOT_A_DEF = frozenset({"README.md"})

#: The closed counter: 34 French tool-words, case-insensitive, whole words.
WORDS = re.compile(
    r"\b(jamais|toujours|dans|avec|les|des|une|est|sur|pour|qui|que|tu|ne|sans|du|au|aux"
    r"|ce|cette|ou|et|le|la|un|de|en|il|elle|sa|ses|se|si|par)\b",
    re.IGNORECASE,
)
INLINE_CODE = re.compile(r"`[^`\n]*`")
#: The printed regions — the same patterns as `.agents/evals/test_working_language.py`.
FENCE = re.compile(r"(?ms)^(```|~~~)[^\n]*\n.*?^\1[^\n]*$")
GUIL = re.compile(r"«[^»]*»")
BANNER = "▸"

# KEPT_FRENCH — CLOSED LIST. It NEVER grows by convenience: a French phrase that trips the counter
# is translated in the def, or put in backticks when one of rules (a)–(e) binds it — the counter
# does not see backticks, the ratchet `BACKTICKED_FRENCH_CAP` below does; an entry is added only when
# one of the keep-French rules binds the phrase, with the binding file:line in its comment, and
# `test_every_kept_phrase_is_still_used` turns a dead entry red. The rules: (a) emitted or matched
# by code; (b) a plan-grammar line or a printed format a tool parses; (c) the name of a section of
# another surface the def cross-references; (d) a text another surface says to copy verbatim;
# (e) the communicator's French headings and the kit terms.
KEPT_FRENCH = (
    # (c) the def's own heading gloss that .agents/skills/kickoff/SKILL.md:954 cites (« Règle de preuve »),
    #     in exec-critic and security-code-review, symmetric with `(mode réfutation)` cited at :953
    "(règle de preuve)",
    # (c) section names of .agents/ref/PLAN_GRAMMAIRE.md:35, :39, :73, :82, cited as anchors
    "Cibles de plan (T-00000654)",
    "Dépendances de plan (T-00000765)",
    "SQL de plan (T-01M54BDV4WKPR1RMT96J7C0KJK)",
    "Préflight de forme",
    # (c) section name of .agents/skills/planning/SKILL.md:274 (`## Le cadrage — AVANT tout planner`)
    "§ Le cadrage",
    # (b) the FORECAST header the run-log hooks parse — .claude/hooks/log-agent-usage.sh:156,
    #     .codex/hooks/log_agent_usage.py:135 ("est." is the English abbreviation of "estimate",
    #     read by the counter as the French "est"); the narrow column, the one left in prose
    "FORECAST                est.",
)

#: Never in a def: the closing review is one critic, a "pair" is the defect (S-00004500).
PAIR = re.compile(r"closing\s+pair|pair\s+of\s+critics|critic\s+pair", re.IGNORECASE)

ANSWER = "You answer in French."
#: CLOSED — the defs exempt from the `ANSWER` line, and from it ONLY (T-01M5S9338BJP1B5RM3TG14AMYT,
#: orchestrator ruling): `language-detector` prints one JSON object and never addresses the pilot, and its
#: def is sha-pinned by `.agents/evals/fixtures/detector_spring_angular.observed.json` (48 real host
#: replays, re-recording them is out of reach). It stays judged by the French tool-word count. Same
#: tuple as `test_working_language.py`; its length is pinned to 1.
NO_ANSWER = ("language-detector",)
NO_ANSWER_SIZE = 1
#: The three runner defs whose four mirrors carry the claude body.
RUNNERS = ("terraform-deployer", "reverse-engineer", "load-tester")
TOML_OPENING = 'developer_instructions = """'

#: Rule (e): the headings the `communicator` prints to the pilot stay French, in every file of it.
#: Measured byte-identical on the five hosts, the Codex copy included (accented), in the source and
#: in the Cursor render — one tuple per place, so a place that drifts is named on its own.
_HEADINGS = ("📣 ON VOUS DEMANDE UNE DÉCISION", "Contexte :", "La question :", "Vos options :",
             "Recommandation :", "Sans réponse :", "CE QUI BLOQUE")
COMMUNICATOR_HEADINGS = {place: _HEADINGS for place in PLACES}

#: RATCHET — inline-backtick spans of the PROSE carrying 2 French tool-words or more, summed over
#: every file the bench discovers (five hosts, sources, Cursor renders). MEASURED at 125 after the
#: merge with develop and the extension of `.agents/ref/WORKING_LANGUAGE.md` (S-01M5VCGTEBC76MKR63HJ2K67CE):
#: 18 distinct spans — code-emitted `COVERAGE DEGRADED` banners, cited section names, the
#: communicator's headings, the plan-grammar `LOT:` line… A span opening on `▸` is banner text, a
#: printed region: never counted. The counter above does not see backticks; this cap does. It never
#: rises by convenience: a new French span is translated, and a span that one of rules (a)–(e) binds
#: raises the cap only with a comment here naming its binding file:line. A span translated lowers it.
#: RE-MEASURED at 125 after the final correction pass of T-01M5S9338BJP1B5RM3TG14AMYT, which restored
#: develop's French spans (`preuve: non fournie`, `C<n> — non fermé : <why>`, the two `plan_lots.py
#: absent` banners, `<nom>`/`<cible>`/`<outil>` placeholders…) and fenced the Codex templates: unchanged,
#: because every restored span carries at most ONE tool-word, and the cap counts two or more.
BACKTICKED_FRENCH_CAP = 125

#: The doctrine line that states the rule, one per surface: its anchor, then what the line carries.
DOCTRINE_LINES = {
    "AGENTS.md": "La langue des défs d'agents DU KIT suit",
    ".github/copilot-instructions.md": "The language of the KIT's agent definitions follows",
}
DOCTRINE_TOKENS = ("`.agents/ref/WORKING_LANGUAGE.md`", "`.agents/evals/test_working_language.py`",
                   "`.agents/evals/test_defs_anglais.py`", "`You answer in French.`", "`.agents/IS_THE_KIT`",
                   "`agents/<", "`▸`", "«…»")


def discover(root: Path) -> dict[str, Path]:
    """Every def under the five host directories, `agents/` and `.cursor/rules/` of `root`, keyed `<place>/<name>`."""
    found = {}
    for place, (directory, pattern) in PLACES.items():
        for path in sorted((root / directory).glob(pattern)):
            if place == "source" and path.name in NOT_A_DEF:
                continue
            name = path.name[: -len(pattern) + 1]
            found[f"{place}/{name}"] = path
    return found


def printed_out(text: str) -> str:
    """`text` without what the agent prints to the pilot: fenced blocks, «…», lines opening on `▸`."""
    rest = GUIL.sub(" ", FENCE.sub(" ", text))
    return "\n".join(" " if line.startswith(BANNER) else line for line in rest.split("\n"))


def prose(text: str) -> str:
    """The prose the counter reads: the printed regions and the inline backtick spans removed."""
    return INLINE_CODE.sub(" ", printed_out(text))


def french_words(text: str, kept: tuple[str, ...] = KEPT_FRENCH) -> list[str]:
    """The French tool-words of the prose of `text`, outside the kept phrases."""
    rest = prose(text)
    for phrase in kept:
        rest = rest.replace(phrase, " ")
    return [m.group(0) for m in WORDS.finditer(rest)]


def faults(text: str, kept: tuple[str, ...] = KEPT_FRENCH) -> list[str]:
    """The faults of ONE def text; an empty list is the conformant answer."""
    found = [f"French tool-word: {w!r}" for w in french_words(text, kept)]
    found += [f"forbidden wording: {m.group(0)!r}" for m in PAIR.finditer(text)]
    return found


def body(place: str, text: str) -> str:
    """The def body: `developer_instructions` on Codex, what follows the frontmatter elsewhere."""
    if place == "codex":
        start = text.index(TOML_OPENING) + len(TOML_OPENING)
        return text[start:text.rindex('"""')]
    assert text.startswith("---\n"), "frontmatter absent"
    return text[text.index("\n---\n", 4) + len("\n---\n"):]


def without_continuation(text: str) -> str:
    """The one measured host difference: the `.codex` body joins a `\\`-continued command on ONE
    line, TOML forbidding the backslash continuation inside a basic string."""
    return re.sub(r" \\\n\s+", " ", text)


def missing_headings(place: str, text: str) -> list[str]:
    """The communicator headings of `place` that `text` no longer carries byte-identically."""
    return [h for h in COMMUNICATOR_HEADINGS[place] if h not in text]


def backticked_french(texts) -> int:
    """How many inline-backtick spans of the prose of `texts` carry 2 French tool-words or more."""
    return sum(1 for text in texts for span in INLINE_CODE.findall(printed_out(text))
               if not span.startswith("`" + BANNER) and len(WORDS.findall(span)) >= 2)


def doctrine_faults(text: str, anchor: str) -> list[str]:
    """The faults of the doctrine line: ONE line carries the anchor, and that line carries each token."""
    lines = [line for line in text.splitlines() if anchor in line]
    if len(lines) != 1:
        return [f"anchor {anchor!r} on {len(lines)} line(s), expected 1"]
    return [f"{token} absent from the doctrine line" for token in DOCTRINE_TOKENS if token not in lines[0]]


DEFS = discover(ROOT)


def _read(key: str) -> str:
    return DEFS[key].read_text(encoding="utf-8")


def _names(place: str) -> set[str]:
    return {k.split("/", 1)[1] for k in DEFS if k.startswith(place + "/")}


def test_population_is_discovered_on_every_place() -> None:
    names = {place: _names(place) for place in PLACES}
    assert names["claude"], "no def discovered under .claude/agents: the bench would judge nothing"
    for place in (*HOSTS, "source"):
        assert names[place] == names["claude"], f"{place}: defs differ from claude: {names[place] ^ names['claude']}"
    assert names["cursor"] and names["cursor"] <= names["claude"], "cursor: a rule with no def, or no rule at all"
    assert set(RUNNERS) | {"communicator"} <= names["claude"]
    assert "README" not in names["source"]


@pytest.mark.parametrize("key", sorted(DEFS))
def test_the_def_is_in_english(key: str) -> None:
    found = faults(_read(key))
    assert found == [], f"{key}: {len(found)} fault(s): {found[:12]}"


def test_every_kept_phrase_is_still_used() -> None:
    texts = [prose(_read(k)) for k in DEFS]
    dead = [p for p in KEPT_FRENCH if not any(p in t for t in texts)]
    assert dead == [], f"kept phrase no def carries in its prose any more (remove it from KEPT_FRENCH): {dead}"


def test_every_kept_phrase_trips_the_counter() -> None:
    """An entry the counter would not see anyway is not an exception, it is noise."""
    assert [p for p in KEPT_FRENCH if not WORDS.search(p)] == []
    assert len(KEPT_FRENCH) == len(set(KEPT_FRENCH))


@pytest.mark.parametrize("key", sorted(DEFS))
def test_the_reply_language_line_is_written(key: str) -> None:
    if key.split("/", 1)[1] in NO_ANSWER:
        return  # exempt from this check only — see NO_ANSWER
    assert ANSWER in " ".join(_read(key).split()), f"{key}: `{ANSWER}` absent (WORKING_LANGUAGE.md § The rule)"


@pytest.mark.parametrize("name", RUNNERS)
def test_the_four_mirrors_carry_the_claude_body(name: str) -> None:
    reference = body("claude", _read(f"claude/{name}"))
    for host in ("copilot", "gemini", "kimi"):
        assert body(host, _read(f"{host}/{name}")) == reference, f"{host}/{name}: body differs from claude"
    assert without_continuation(body("codex", _read(f"codex/{name}"))) == without_continuation(reference), (
        f"codex/{name}: body differs from claude beyond the `\\` continuation")


@pytest.mark.parametrize("key", sorted(DEFS))
def test_the_body_read_is_not_empty(key: str) -> None:
    place, name = key.split("/", 1)
    floor = 5_000 if name in RUNNERS else 100
    assert len(body(place, _read(key))) > floor


def test_the_counter_holds_the_34_words() -> None:
    words = WORDS.pattern[len(r"\b("):-len(r")\b")].split("|")
    assert len(words) == len(set(words)) == 34


@pytest.mark.parametrize("place", sorted(PLACES))
def test_the_communicator_keeps_its_french_headings(place: str) -> None:
    assert missing_headings(place, _read(f"{place}/communicator")) == [], (
        f"{place}/communicator: a heading printed to the pilot changed — rule (e) keeps it French, byte-identical")


def test_backticked_french_does_not_grow() -> None:
    found = backticked_french(_read(k) for k in DEFS)
    assert found <= BACKTICKED_FRENCH_CAP, (
        f"{found} backticked spans with French tool-words > cap {BACKTICKED_FRENCH_CAP}: translate the new span; "
        "only a span one of rules (a)–(e) binds raises the cap, with a comment naming its binding file:line")
    assert found == BACKTICKED_FRENCH_CAP, (
        f"{found} < cap {BACKTICKED_FRENCH_CAP}: a span was translated — lower BACKTICKED_FRENCH_CAP to {found}")


@pytest.mark.parametrize("surface", sorted(DOCTRINE_LINES))
def test_the_doctrine_line_is_written(surface: str) -> None:
    text = (ROOT / surface).read_text(encoding="utf-8")
    assert doctrine_faults(text, DOCTRINE_LINES[surface]) == [], surface


# --- Mutants: the guard can turn red (in memory or under tmp_path, never on the real files) -----------
def test_mutant_a_french_sentence_in_a_def_turns_red() -> None:
    text = _read("claude/orchestrator")
    assert faults(text) == [], "base red: the mutant would measure nothing"
    lines = text.splitlines()
    lines.insert(20, "Le runner ne lit jamais un état dans la session.")
    assert len(faults("\n".join(lines))) >= 3
    assert faults("The runner never reads a state in the session.") == []


def test_mutant_the_printed_regions_are_the_only_french_left() -> None:
    """French inside a fenced block, a «…» or a `▸` line is printed text: not counted; the SAME
    sentence one line outside the region is prose: counted. The boundary is the sheet's, no wider."""
    sentence = "une ligne réutilisable, ou aucune"
    assert faults(f"```\nVERDICT: <GO>\n{sentence}\n```\n") == []
    assert faults(f"```\nVERDICT: <GO>\n```\n{sentence}\n")
    assert faults(f"Quote it: « {sentence} ».\n") == []
    assert faults(f"Quote it: \"{sentence}\".\n")
    assert faults(f"▸ agent ✓ {sentence}\n") == []
    assert faults(f"  ▸ agent ✓ {sentence}\n"), "a `▸` that does not open the line is prose"


@pytest.mark.parametrize("phrase", KEPT_FRENCH)
def test_mutant_each_kept_phrase_is_load_bearing(phrase: str) -> None:
    """Remove ONE entry from the allow-list: a def that carries the phrase turns red."""
    users = [k for k in DEFS if phrase in prose(_read(k))]
    assert users, f"{phrase!r}: no def carries it"
    narrower = tuple(p for p in KEPT_FRENCH if p != phrase)
    assert faults(_read(users[0])) == [] and faults(_read(users[0]), narrower), f"{phrase!r} is not load-bearing"


def test_mutant_a_new_french_def_is_discovered_and_turns_red(tmp_path: Path) -> None:
    for directory, _ in PLACES.values():
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / ".claude/agents/nouveau.md").write_text(
        "---\nname: nouveau\ndescription: Relit le plan.\n---\nTu relis le plan et tu ne modifies jamais "
        "un fichier.\n", encoding="utf-8")
    (tmp_path / ".codex/agents/nouveau.toml").write_text(
        'name = "nouveau"\ndeveloper_instructions = """\nTu relis le plan sans jamais écrire.\n"""\n',
        encoding="utf-8")
    (tmp_path / "agents/nouveau.md").write_text(
        "---\nname: nouveau\ndescription: Relit le plan.\n---\nTu relis le plan sans jamais écrire.\n",
        encoding="utf-8")
    (tmp_path / "agents/README.md").write_text("Le mode d'emploi de la source, en français.\n", encoding="utf-8")
    (tmp_path / ".cursor/rules/nouveau.mdc").write_text(
        "---\ndescription: Relit le plan.\nalwaysApply: false\n---\nTu relis le plan sans jamais écrire.\n",
        encoding="utf-8")
    found = discover(tmp_path)
    assert set(found) == {"claude/nouveau", "codex/nouveau", "source/nouveau", "cursor/nouveau"}, (
        "the source README.md is the source's manual, never a def")
    for key, path in found.items():
        assert faults(path.read_text(encoding="utf-8")), f"{key}: a def written in French stays green"


@pytest.mark.parametrize("place", sorted(PLACES))
def test_mutant_a_translated_heading_turns_red(place: str) -> None:
    text = _read(f"{place}/communicator")
    assert missing_headings(place, text) == [], "base red: the mutant would measure nothing"
    mutant = text.replace("Sans réponse :", "Without an answer:")
    assert mutant != text and missing_headings(place, mutant) == ["Sans réponse :"]


def test_mutant_a_new_backticked_french_span_breaks_the_ratchet() -> None:
    texts = [_read(k) for k in DEFS]
    assert backticked_french(texts) == BACKTICKED_FRENCH_CAP, "base red: the mutant would measure nothing"
    texts[0] += "\nKeep `une phrase dans le code` as is.\n"
    assert backticked_french(texts) == BACKTICKED_FRENCH_CAP + 1
    assert backticked_french(["`one French word: le`"]) == 0, "a single tool-word is not a span the cap counts"
    assert backticked_french(["`▸ agent ⚙ <action en une ligne>…`"]) == 0, "banner text is printed, not prose"


def answer_exemption_faults(exempt: tuple, names: set) -> list:
    """A size other than the pinned one, a duplicate, a name no def carries."""
    out = [f"size {len(exempt)} != {NO_ANSWER_SIZE}"] if len(exempt) != NO_ANSWER_SIZE else []
    out += ["duplicate"] if len(set(exempt)) != len(exempt) else []
    return out + [f"{n}: no such def" for n in exempt if n not in names]


def test_the_answer_exemption_stays_closed() -> None:
    names = _names("claude")
    assert answer_exemption_faults(NO_ANSWER, names) == [], answer_exemption_faults(NO_ANSWER, names)
    # mutants: a second def slipped into the tuple, a name no def carries, the tuple emptied
    assert answer_exemption_faults(NO_ANSWER + ("planner",), names), "a second exempt def stays green"
    assert answer_exemption_faults(("no-such-def",), names), "an exemption naming no def stays green"
    assert answer_exemption_faults((), names), "an emptied exemption stays green"
    # the exempt def stays under the French counter, on every place it lives
    exempt = [k for k in DEFS if k.split("/", 1)[1] in NO_ANSWER]
    assert len(exempt) == 7, exempt
    assert faults(_read(exempt[0]) + "\nLes données sont dans le dépôt pour la tâche.\n"), "exempt def not counted"


def test_mutant_a_def_without_the_reply_line_turns_red() -> None:
    text = _read("claude/analyzer")
    assert ANSWER in " ".join(text.split()), "base red: the mutant would measure nothing"
    assert ANSWER not in " ".join(text.replace(ANSWER, "").split())


@pytest.mark.parametrize("surface", sorted(DOCTRINE_LINES))
def test_mutant_the_doctrine_line_removed_or_gutted_turns_red(surface: str) -> None:
    text = (ROOT / surface).read_text(encoding="utf-8")
    anchor = DOCTRINE_LINES[surface]
    assert doctrine_faults(text, anchor) == [], "base red: the mutant would measure nothing"
    removed = "\n".join(line for line in text.splitlines() if anchor not in line)
    assert doctrine_faults(removed, anchor) == [f"anchor {anchor!r} on 0 line(s), expected 1"]
    for token in DOCTRINE_TOKENS:
        assert doctrine_faults(text.replace(token, ""), anchor) == [f"{token} absent from the doctrine line"]


@pytest.mark.parametrize("wording", ["the closing pair runs", "a pair of critics", "the critic pair"])
def test_mutant_closing_pair_turns_red(wording: str) -> None:
    text = _read("claude/critic-opus")
    assert faults(text) == []
    assert any("forbidden wording" in f for f in faults(text + "\n" + wording + "\n"))
