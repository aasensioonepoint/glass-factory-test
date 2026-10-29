"""No promoted marker is lost or duplicated when the router is thinned (P4).

WHAT THIS EXISTS FOR. P4 moves nine blocks of `AGENTS.md` into skills, VERBATIM.
Seven of those nine extractions are pinned by NOTHING: if a 35-line paragraph
vanished from `verification-discipline`'s block, `pytest` would stay green. This
suite is the campaign's ONE mechanical control, and its limits are stated so a
green here is not read as more than it is:

  * it covers the MARKERS, not the prose. Prose conservation is proven per task by
    a byte-containment check against `git show HEAD:AGENTS.md`, and by diff review.
  * it is an EQUALITY on a union, so it catches a marker LOST (a block dropped) and
    a marker DUPLICATED (a block copied instead of moved) — the two failure modes a
    text move actually has.

WHY THE UNION AND NOT A PER-FILE COUNT. Before P4 the 28 markers all lived in
`AGENTS.md`. After it, 22 live in skills. A per-file count would therefore have to
be rewritten by each of the nine tasks — nine chances to write the new number
wrong, and no invariant at all. The UNION over the detector's own corpus is
invariant across the whole campaign: it is 28 before the first extraction and 28
after the ninth.

AND THE POPULATION IS THE DETECTOR'S OWN, NOT A RE-IMPLEMENTATION OF IT. The
corpus is read from `ledger.py`'s `LANDING_SURFACES` rather than re-globbed here
(L-00000154: a guard wired through N links must assert all N — a re-implemented
corpus could agree with a bug in the real one). That also makes this suite prove
something stronger than bookkeeping: a marker that moved from the router into a
skill is still seen BY THE DETECTOR, so the promoted entry stays excluded from
`context()` and does not start being double-injected.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PY = ROOT / ".agents" / "bin" / "ledger.py"

# The count `AGENTS.md` carried alone before the first P4 extraction: 27 real
# promotions + 1 documentary placeholder (`L-NNN:<8-hex-token>`, deliberately not
# a real id so this very documentation cannot become a false positive of the
# detector). Written HERE, never derived from the files under test — a test that
# reads its expected value out of what it watches is not watching anything
# (L-00000261, paid for in T-00000348).
MARKERS_BEFORE_P4 = 28

# PROMOTIONS FAITES APRÈS LA CLÔTURE DE P4 (T-00000425). L'invariant de la campagne
# est la CONSERVATION — 28 en entrée, 28 en sortie — et il n'a jamais voulu dire « le
# kit ne promeut plus jamais ». Écrit en équation nue sur 28, ce contrôle rougissait
# sur CHAQUE promotion légitime : il aurait été neutralisé en une semaine, et un
# contrôle qu'on neutralise ne contrôle plus rien.
#
# La correction garde l'esprit ET la lettre : une promotion neuve est ACCEPTÉE, mais
# seulement si elle est DÉCLARÉE ici, une ligne par marqueur. Les deux modes de
# défaillance survivent intacts — un marqueur PERDU fait tomber le total sous la
# somme attendue, un marqueur INVENTÉ le fait monter au-dessus. Seule change
# l'obligation de déclarer ce qu'on ajoute.
#
# ET UNE DÉCLARATION NE PEUT PAS MASQUER UNE PERTE : `test_declared_post_P4_markers_
# are_actually_present` exige que chaque ligne ci-dessous soit RÉELLEMENT dans le
# corpus. Sans elle, déclarer un marqueur qu'on n'a pas collé compenserait
# exactement un marqueur qu'on aurait laissé tomber, et la somme resterait verte.
PROMOTED_AFTER_P4 = {
    # 2026-09-03 — leçons universelles nées du chantier T-410/T-416, promues pour
    # qu'elles atteignent les projets adoptants : `.agents/state/` est `strip:`, donc
    # le registre ne voyage jamais et une leçon n'en sort que par sa surface.
    ("L-00000305", "7ad80b71"),  # « hors du gate » est une propriété de la règle de découverte
    ("L-00000306", "aee32e87"),  # figer le SHA avant de lancer un vérificateur
    ("L-00000308", "1848c85c"),  # sentinelle sur un étage dont le verdict normal est vide
    ("L-00000309", "b96e7d47"),  # un pré-filtre désarme les arms qui ne le satisfont pas
    ("L-00000311", "cb4d4381"),  # ceux ajoutés au même tour n'ont jamais été confrontés à lui
    ("L-00000312", "9209123a"),  # une sonde interroge l'objet, pas un témoin favorable
    # 2026-09-10 — leçons nées du chantier T-00000554 (portabilité Python des hooks
    # sur six hôtes), promues vers des surfaces qui voyagent : marqueurs déjà posés
    # dans verification-discipline et guardrails, déclarés ici comme l'exige le filet.
    ("L-00000430", "bd8eee08"),  # un bras de test qui saute n'est pas un bras qui passe
    ("L-00000432", "414cca82"),  # garder un appel externe par `command -v`, qui est un builtin
    # 2026-10-16 — trois règles d'efficacité du pilote (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH),
    # promues vers le routeur AGENTS.md par T-01M4ZG76AWZKH3HW0R3KKDEFVF (lot B).
    ("L-01M504VA7KMD6QV3MPAYJKN3Y7", "e3a1f957"),  # fermer avant d'ouvrir ; mineur ; voie courte
}

EXPECTED_UNION = MARKERS_BEFORE_P4 + len(PROMOTED_AFTER_P4)

# The marker's shape, per AGENTS.md § Institutional memory. `L-NNN` (the
# placeholder), `L-<digits>` (real legacy ids) and `L-<ULID>` (ids minted after the
# T-00000726 switch-over: 26 UPPER-CASE Crockford symbols) all match, deliberately:
# the union must account for the placeholder too, or the expected total is off by one.
MARKER_RE = re.compile(
    r"\[promu-du-ledger:(L-(?:NNN|[0-9A-HJKMNP-TV-Z]{26}|\d+)):([0-9a-fA-F]{8}|<8-hex-token>)\]"
)

# T-00000448 — a COUNT of the landing corpus written in prose. The corpus is
# `LANDING_SURFACES`, whose size moves with every skill added or removed; the skill
# that documents the detector stated "37 files, the router plus 36 skills" and went
# false without a single red. A number (digits, or a word from one to ninety-nine),
# up to two words, then a corpus noun. Asterisk/backtick emphasis around the
# number or the noun (`**36** skills`, `36 *skills*`, "36 `SKILL.md`") is SEEN.
# NOT SEEN (L-00000187, bounded rather than enumerated): "a dozen" / "dozens of",
# a count whose corpus noun is more than two words away or absent ("51 entries"),
# a scale word with no digits or number word before it ("a hundred", "hundreds",
# "a thousand"), underscore emphasis (`_36_ skills`,
# `__36__ skills`, `36 _skills_`), `~~` strikethrough, HTML tags, link syntax,
# non-ASCII hyphens (`L‑ids`, U+2011). FALSE POSITIVES it accepts, so a prose edit may
# need rewording rather than the motif loosening: "to one skill", "a one-off file",
# "section 3 files", "step 2 of the skill files".
_EMPHASIS = r"[*`]*"
_NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|(?:thir|four|fif|six|seven|eigh|nine)teen"
    r"|(?:twen|thir|for|fif|six|seven|eigh|nine)ty(?:-[a-z]+)?)"
)
CORPUS_COUNT_RE = re.compile(
    r"(?<![-\w])" + _EMPHASIS + _NUMBER + _EMPHASIS
    + r"(?:[\s-]+\S+){0,2}?[\s-]+" + _EMPHASIS
    + r"(?:skills?|files?|SKILL\.md|surfaces?|L-ids?)\b",
    re.IGNORECASE,
)
INSTITUTIONAL_MEMORY_SKILL = ROOT / ".agents" / "skills" / "institutional-memory" / "SKILL.md"


def _load_ledger():
    """Import `ledger.py` by path, registering the module BEFORE exec.

    The registration is not decoration: `.agents/evals/` is inside
    `test_modload_registration.py`'s SCAN_DIRS, and that net requires a
    `sys.modules[spec.name] = module` within 8 lines above any `.exec_module(`
    in this perimeter. Idiom copied from that suite rather than invented.
    """
    spec = importlib.util.spec_from_file_location("_p4_ledger", LEDGER_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def corpus_paths() -> list[Path]:
    """The DETECTOR's own corpus, taken from ledger.py — never re-globbed."""
    ledger = _load_ledger()
    surfaces = getattr(ledger, "LANDING_SURFACES", None)
    if not surfaces:
        raise AssertionError(
            "ledger.py no longer exposes LANDING_SURFACES — this suite was reading the "
            "detector's real corpus through it, and a re-implemented glob here would be "
            "free to disagree with the detector (L-00000154). Re-point it, do not fork it."
        )
    out: list[Path] = []
    for pattern in surfaces:
        if any(ch in pattern for ch in "*?["):
            out.extend(sorted(ROOT.glob(pattern)))
        else:
            p = ROOT / pattern
            if p.is_file():
                out.append(p)
    return out


def markers_in(path: Path) -> list[tuple[str, str]]:
    # RAW BYTES, decoded permissively: the detector itself matches on bytes with
    # no decoding decision, and this suite must not be stricter than what it
    # claims to mirror.
    text = path.read_bytes().decode("utf-8", errors="replace")
    return MARKER_RE.findall(text)


class DoctrineMarkerUnionTests:
    def test_the_corpus_is_non_empty_and_holds_the_router(self) -> None:
        """NON-VACUITY FIRST (L-00000186, L-00000232): every count below is
        satisfied vacuously by an empty corpus, and an empty corpus is exactly
        what a broken glob produces. Name a member that MUST be there.
        """
        paths = corpus_paths()
        assert paths, "the landing corpus is EMPTY — every assertion below would pass vacuously"
        names = {p.name for p in paths}
        assert "AGENTS.md" in names, (
            f"the router is not in the detector's corpus: {sorted(names)[:8]}… — the "
            "union below would then not be measuring the doctrine at all"
        )
        assert len(paths) >= 2, (
            "the corpus holds only the router, so no skill is being scanned; after P4 the "
            "markers live in skills and this suite would be blind to them"
        )

    def test_marker_union_is_conserved_across_the_thinning(self) -> None:
        """THE CONTROL. 28 before the first extraction, 28 after the ninth."""
        seen: dict[tuple[str, str], list[str]] = {}
        for path in corpus_paths():
            for marker in markers_in(path):
                seen.setdefault(marker, []).append(str(path.relative_to(ROOT)))

        assert len(seen) == EXPECTED_UNION, (
            f"the promoted-marker union is {len(seen)}, expected {EXPECTED_UNION} "
            f"({MARKERS_BEFORE_P4} carried across P4 + {len(PROMOTED_AFTER_P4)} declared in "
            "PROMOTED_AFTER_P4). A promotion made without declaring it there lands here too: "
            "add its (id, token) line rather than raising a number.\n"
            "A LOWER number means a moved block lost markers — i.e. text was dropped, not "
            "moved, and the promoted entries it carried will start being injected again "
            "every session. A HIGHER number means a marker was invented. Either way the "
            "per-task byte-containment check against `git show HEAD:AGENTS.md` is the "
            "next thing to run.\nUnion actually found:\n  "
            + "\n  ".join(f"{mid}:{tok} in {', '.join(files)}" for (mid, tok), files in sorted(seen.items()))
        )

    def test_declared_post_P4_markers_are_actually_present(self) -> None:
        """UNE DÉCLARATION NE COMPENSE PAS UNE PERTE.

        `EXPECTED_UNION` est une SOMME : sans ce contrôle, déclarer dans
        `PROMOTED_AFTER_P4` un marqueur qu'on n'a jamais collé compenserait
        exactement un marqueur laissé tomber ailleurs, et le total resterait vert —
        le trou même que la campagne P4 s'était donné pour mission de fermer.

        Chaque ligne déclarée doit donc être RÉELLEMENT dans le corpus du détecteur.
        Et l'inverse est déjà couvert par l'égalité : un marqueur présent mais non
        déclaré fait monter le total au-dessus de la somme.
        """
        seen = set()
        for path in corpus_paths():
            seen.update(markers_in(path))
        missing = sorted(PROMOTED_AFTER_P4 - seen)
        assert not missing, (
            "marqueur(s) DÉCLARÉ(S) dans PROMOTED_AFTER_P4 mais ABSENT(S) du corpus :\n  "
            + "\n  ".join(f"{mid}:{tok}" for mid, tok in missing)
            + "\nUne promotion se termine par le COLLAGE du bloc dans la surface — "
            "`ledger.py promote` n'écrit rien lui-même, et l'entrée a QUITTÉ l'injection "
            "SessionStart : déclarée sans être collée, la leçon est perdue, pas promue."
        )

    def test_no_marker_is_duplicated_across_two_surfaces(self) -> None:
        """A MOVE, NOT A COPY. The union count above would stay at 28 if a block
        were copied into a skill and ALSO left in the router — the union is a SET.
        So duplication needs its own assertion, or "moved verbatim" is unproven
        in the one direction the count cannot see.

        A duplicated marker is not cosmetic: the entry is announced as carried by
        the doctrine, and the pilot then has two places to retract from, one of
        which nobody remembers.
        """
        seen: dict[tuple[str, str], list[str]] = {}
        for path in corpus_paths():
            for marker in markers_in(path):
                seen.setdefault(marker, []).append(str(path.relative_to(ROOT)))
        dupes = {m: f for m, f in seen.items() if len(f) > 1}
        assert not dupes, (
            "marker(s) present on MORE THAN ONE landing surface — a block was COPIED "
            "instead of MOVED:\n  "
            + "\n  ".join(f"{mid}:{tok} in {', '.join(files)}" for (mid, tok), files in sorted(dupes.items()))
        )

    def test_negative_control_the_union_rule_refuses_a_lost_marker(self) -> None:
        """RE-ENABLE THE DEFECT (L-00000057). Drop one marker from the observed
        union and require the equality to fail — replayed on the SAME comparison,
        not a re-derivation.
        """
        seen = set()
        for path in corpus_paths():
            seen.update(markers_in(path))
        assert len(seen) == EXPECTED_UNION, "base not green — read the test above first"

        mutilated = set(list(seen)[:-1])
        assert len(mutilated) == len(seen) - 1, "the mutation removed nothing"
        assert len(mutilated) != EXPECTED_UNION, (
            "THE EQUALITY DOES NOT BITE: a union short by one still equalled the expected "
            "total, so its green measures nothing."
        )

    def test_the_marker_shape_admits_a_ulid_ledger_id(self) -> None:
        """T-00000726 (C1e): a lesson promoted after the switch-over carries an
        `L-<ULID>` id. A marker shape that does not see it would leave that marker
        OUT of the union, and the count would be short without a single red.
        MUTANT: `MARKER_RE` left at `L-(?:NNN|\\d+)` — the first assertion goes red.
        A lower-case or 25-symbol body is no ULID, and no marker."""
        ulid = "01M3250V003HCPQKTZ8ENYF4VM"
        assert MARKER_RE.findall(f"[promu-du-ledger:L-{ulid}:abcdef12]") == [(f"L-{ulid}", "abcdef12")]
        assert MARKER_RE.findall("[promu-du-ledger:L-00000305:7ad80b71]") == [("L-00000305", "7ad80b71")]
        assert MARKER_RE.findall(f"[promu-du-ledger:L-{ulid.lower()}:abcdef12]") == []
        assert MARKER_RE.findall(f"[promu-du-ledger:L-{ulid[:-1]}:abcdef12]") == []

    def test_the_landing_contract_states_no_corpus_count(self) -> None:
        """T-00000448: the skill that names the detector's corpus BOUNDS it
        (the router plus every depth-1 skill), never counts it. Held on the WHOLE
        file, so a count cannot come back in another paragraph. What
        `CORPUS_COUNT_RE` cannot see is written above its definition.
        MUTANT: put back "the detector's corpus is 37 files, the router plus
        36 skills" — this assertion goes red."""
        assert INSTITUTIONAL_MEMORY_SKILL in corpus_paths(), (
            "the institutional-memory skill is no longer in the detector's corpus — "
            "this witness would then judge a file the detector does not read"
        )
        text = INSTITUTIONAL_MEMORY_SKILL.read_text(encoding="utf-8")
        found = CORPUS_COUNT_RE.findall(text)
        assert found == [], (
            f"institutional-memory/SKILL.md states a count of the landing corpus: {found}. "
            "The corpus is LANDING_SURFACES and its size moves with the tree — bound it "
            "(\"the router plus every depth-1 skill\") instead of numbering it."
        )

    def test_negative_control_the_count_pattern_bites(self) -> None:
        """RE-ENABLE THE DEFECT (L-00000057): every form below is a corpus count
        the witness above must refuse, and the last list is prose it must leave
        alone. A motif replaced by `(?!)` turns the first loop red."""
        counts = [
            "36 skill files", "50 SKILL.md files", "51 SKILL.md", "a 37-file corpus",
            "36 traveling skills", "the router plus thirty-six skills",
            "corpus of 51 surfaces", "seventeen files", "twenty skills", "37 L-ids",
            "measured: 50 skills", "the router plus 36 skills", "a corpus of 37 files",
            "**36** skills", "36 *skills*", "36 `SKILL.md`", "Fifty-one SKILL.md",
        ]
        for form in counts:
            assert CORPUS_COUNT_RE.findall(form), f"the count motif misses {form!r}"
        for prose in [
            "depth-1 skill", "every depth-1 skill", "depth-1 skills", "the 5 most recent",
            "every landing surface", "the safety net files", "a property file",
            "a file per entry", "TWO kinds of such surface",
        ]:
            assert CORPUS_COUNT_RE.findall(prose) == [], f"the count motif bites on {prose!r}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
