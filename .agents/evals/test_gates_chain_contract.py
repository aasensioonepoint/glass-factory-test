"""The gated chain is pinned TEXTUALLY on all five hosts (T-00000352).

WHAT WAS UNGUARDED, MEASURED. `.codex/agents/orchestrator.toml` had its chain
pinned by `.codex/test_pipeline_contract.py` (`process.index(...)` on the codex
def). The other three hosts — claude, gemini, copilot — were covered only by the
five booleans of `fixtures/orchestrator.golden.json` (`emits_forecast`,
`owns_approval_gate`, …). None of those five would notice the whole `## Chaîne à
gates` section being deleted: a future edit could remove the ASCII chain, the
four rules and the `LECON_CANDIDATE` capture from three hosts out of four and no
test would go red.

Worse, the chain text on two of those hosts SAID SO — "No test pins this text on
this host (suivi T-00000352)" — which is the honest form, and which this suite
makes obsolete. Those sentences are corrected in the same commit, because a
sentence declaring itself unpinned after it has been pinned is L-00000111 in the
other direction.

THE SCOPE IS CLOSED AND WRITTEN DOWN, NOT REPO-WIDE, AND THE REASON IS MEASURED.
The three hand-counts the P2 dev ran once and lost were repo-wide, and repo-wide
is exactly what cannot work here: `P5` means a phase in this file and something
entirely different in `frontend-fidelity.*`, and `class-0` appears throughout the
briefs and the archived plans. A repo-wide count would drift on every unrelated
document. So this suite reads exactly five files, named below, and its non-vacuity
floor asserts it found five.

THE EXPECTED VALUES ARE WRITTEN HERE, NEVER EXTRACTED FROM A HOST. That is
L-00000261, paid for in T-00000348 two commits ago: a test that obtains its
expected text by reading one of the files it watches pins the AGREEMENT between
hosts and stays green through a coordinated edit of all of them. Byte-identity
across hosts is a useful separate check (and `test_plan_critic_contract.py` does
it for the canonical sentence); it is not this suite's job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# THE SCOPE. Five files, named. Not a glob, not a sweep — see the header.
ORCHESTRATOR_DEFS = {
    "claude": ROOT / ".claude" / "agents" / "orchestrator.md",
    "codex": ROOT / ".codex" / "agents" / "orchestrator.toml",
    "gemini": ROOT / ".gemini" / "agents" / "orchestrator.md",
    "copilot": ROOT / ".github" / "agents" / "orchestrator.agent.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "orchestrator.md",
}

# THE BLOCK ANCHORS. The chain is an ASCII diagram, and the order check must be
# scoped TO IT — measured: across the whole file `exec-critic` occurs 5-7 times
# and `[GATE humain unique]` 4-11 times, so a first-occurrence comparison over the
# file compares two unrelated mentions and reports a shuffled chain on a perfectly
# ordered one. That is L-00000057 exactly (right logic, wrong anchor), and it is
# how the first version of this suite failed on a conformant repo.
# T-00000624 : l ancre de DEBUT suivait le diagramme, qui nommait alors la PAIRE.
# S-00003871 (decision pilote du 2026-10-03, critique de plan UNIQUE) : elle suit
# encore le diagramme, qui nomme desormais UN critique. Elle porte « critique
# UNIQUE » et s arrete la, avant la glose du repli : ce qui doit casser ce test,
# c est le RETOUR de la paire (« plan-critic ∥ … »), pas une reformulation de la
# parenthese — mutant rejoue par le controle negatif dedie ci-dessous.
# T-01M5S9338BJP1B5RM3TG14AMYT puis S-01M5VCGTEBC76MKR63HJ2K67CE (`.agents/ref/WORKING_LANGUAGE.md`) :
# la PROSE des cinq defs est en anglais (regle 2 : « round trips »), mais le diagramme est un bloc
# que la def imprime, garde en francais a l octet (« critique UNIQUE », « [GATE humain unique] »,
# noeud que la prose cite tel quel) sur les CINQ copies, toutes cloturees — la copie Codex comprise,
# rendue a l octet de develop puis cloturee (correction finale de T-01M5S9338BJP1B5RM3TG14AMYT) : ce que
# la def imprime au pilote reste francais sur chaque hote, cloture ou non. La tete anglaise est un
# MUTANT (EN_BLOCK_START, EN_GATE), jamais une valeur admise.
BLOCK_START = "planner → plan-critic (PLAN, critique UNIQUE"
EN_BLOCK_START = "planner → plan-critic (PLAN, SINGLE critic"
# La forme d AVANT, gardee comme MUTANT, jamais comme valeur admise.
PAIR_BLOCK_START = "planner → plan-critic ∥ plan-critic-sonnet-max (PLAN, les DEUX en parallèle"
BLOCK_END = "LECON_CANDIDATE"
GATE = "[GATE humain unique]"
EN_GATE = "[single human GATE]"

# The chain's nodes IN ROUTING ORDER, checked by position INSIDE the block.
# `planner` is deliberately absent: it is the block's first token by construction
# (see BLOCK_START), so asserting its position would be circular.
CHAIN_NODES = (
    "plan-critic",
    GATE,
    "exec-critic",
    "security-code-review",
    "documenter",
    "LECON_CANDIDATE",
)

# The chain's rules, keyed on the load-bearing fragment of each rather than a
# whole sentence. MEASURED per-host difference that this bounding exists for:
# codex writes rule 1 as `No execution without a GO.` — no backticks, because the
# text lives inside a TOML string. Pinning the backticks would pin FORMATTING and
# go red on a host that is perfectly conformant.
CHAIN_RULES = (
    "No execution without a",                # rule 1 (backtick-agnostic, see above)
    "round trips",                           # rule 2 (the cap, see CAP_FRAGMENT)
    "class-0",                               # rule 4 lives on the class-0 line
)

# Rule 2's cap. Written here, not read from a host (L-00000261). This is a
# SECOND, independent surface from the eight `test_plan_critic_contract.py`
# pins — the same number stated in another place, which is exactly why it needs
# its own assertion.
CAP_FRAGMENT = "Max 8 round trips"

# The LESSONS capture that P3 added to the chain's tail. Nothing else pinned it.
LESSON_CAPTURE = "LECON_CANDIDATE"

# The class-0 PROXIMITY WINDOW. `class-0` must sit within this many characters of
# `gitleaks`: the rule is that the secrets gate stays active in BOTH regimes, and
# a `class-0` mention drifting away from its scanner is how that rule quietly
# becomes a different claim. A bare presence check would not see that drift,
# which is why this is a window and why it carries a negative control below.
PROXIMITY_CHARS = 80


def _read(host: str) -> str:
    return ORCHESTRATOR_DEFS[host].read_text(encoding="utf-8")


def chain_block(text: str) -> str | None:
    """The ASCII chain diagram, sliced between its two anchors. None when either
    anchor is missing — which the caller must treat as a FAILURE, never as an
    empty block that trivially satisfies every check below (L-00000186)."""
    i = text.find(BLOCK_START)
    if i < 0:
        return None
    j = text.find(BLOCK_END, i)
    if j < 0:
        return None
    return text[i : j + len(BLOCK_END)]


def node_order_violations(block: str) -> list:
    """THE ORDER RULE, as a function, so the negative controls replay THIS rule
    rather than a re-derivation of it (L-00000057).

    Operates on the BLOCK, never the whole file — see BLOCK_START's note.
    Returns the pairs found out of order; an empty list is conformant.
    """
    positions = [(node, block.find(node)) for node in CHAIN_NODES]
    missing = [n for n, i in positions if i < 0]
    if missing:
        return [("MISSING", n) for n in missing]
    return [
        (a, b)
        for (a, ia), (b, ib) in zip(positions, positions[1:])
        if ia > ib
    ]


def cap_holds(text: str) -> bool:
    """RULE 2'S CAP, as a function, so the negative controls replay THIS rule
    (L-00000057): the orchestrator text states `CAP_FRAGMENT`."""
    return CAP_FRAGMENT in text


def proximity_holds(text: str, needle: str, anchor: str, window: int) -> bool:
    """THE PROXIMITY RULE, as a function, for the same reason.

    True when some occurrence of `needle` sits within `window` characters of some
    occurrence of `anchor`.
    """
    n_pos = [m.start() for m in re.finditer(re.escape(needle), text)]
    a_pos = [m.start() for m in re.finditer(re.escape(anchor), text)]
    if not n_pos or not a_pos:
        return False
    return any(abs(n - a) <= window for n in n_pos for a in a_pos)


class GatesChainContractTests:
    """The chain's text is pinned on all five hosts, and the rules bite."""

    def test_non_vacuity_all_five_orchestrator_defs_exist_and_are_read(self) -> None:
        """A rule that swept an empty population reports no violation either
        (L-00000232, L-00000186). Name the count that must be found, and require
        each file to be non-trivially sized so a truncated file cannot pass.
        """
        assert len(ORCHESTRATOR_DEFS) == 5, "this suite claims five hosts"
        for host, path in ORCHESTRATOR_DEFS.items():
            assert path.is_file(), f"{host}: {path} is absent — the pin watches nothing"
            assert len(path.read_text(encoding="utf-8")) > 2000, (
                f"{host}: {path} is implausibly short for an orchestrator def; a "
                "truncated file would satisfy the substring checks below vacuously"
            )

    def test_chain_nodes_appear_in_routing_order_on_all_five_hosts(self) -> None:
        for host in ORCHESTRATOR_DEFS:
            block = chain_block(_read(host))
            assert block is not None, (
                f"{host}: the chain block's anchors ({BLOCK_START!r} .. {BLOCK_END!r}) "
                "are not both present — the diagram has been removed or renamed, "
                "which is precisely the deletion this suite exists to catch"
            )
            violations = node_order_violations(block)
            assert not violations, (
                f"{host}: the gated chain's nodes are missing or out of order inside "
                f"the diagram: {violations}. Expected order: {' -> '.join(CHAIN_NODES)}"
            )

    def test_the_chain_block_is_byte_identical_across_the_five_hosts(self) -> None:
        """A SECOND, DIFFERENT CLAIM from the order check above, and both are
        needed. Order-within-a-host catches a shuffle on one host; byte-identity
        catches a DIVERGENCE between hosts — one host quietly acquiring a
        different chain. Measured at the time of writing: the block is 913
        characters and identical on all five, so the hosts genuinely share this
        artefact and any drift is a decision, not an accident.

        This does NOT pin the block's CONTENT (L-00000261 — an agreement check
        stays green through a coordinated edit of all five). The content checks
        are the assertions above and below, whose expected values live in this
        file.
        """
        blocks = {}
        for host in ORCHESTRATOR_DEFS:
            block = chain_block(_read(host))
            assert block is not None, f"{host}: chain block anchors missing"
            blocks[host] = block
        assert len(blocks) == 5
        distinct = set(blocks.values())
        assert len(distinct) == 1, (
            "the chain diagram DIVERGED between hosts. Sizes: "
            + ", ".join(f"{h}={len(b)}" for h, b in blocks.items())
            + ". If the divergence is deliberate, this assertion is the place to "
            "record why — do not delete it, weaken it to a per-host check."
        )

    def test_the_four_chain_rules_are_present_on_all_five_hosts(self) -> None:
        for host in ORCHESTRATOR_DEFS:
            text = _read(host)
            missing = [r for r in CHAIN_RULES if r not in text]
            assert not missing, f"{host}: chain rule fragment(s) absent: {missing}"

    def test_rule_two_states_the_cap_as_eight_on_all_five_hosts(self) -> None:
        """The cap, on a surface the plan-critic suite does not cover. Its value
        is written in THIS file (L-00000261) so a coordinated edit of the five
        orchestrator defs cannot slip past by keeping them consistent.
        """
        for host in ORCHESTRATOR_DEFS:
            assert cap_holds(_read(host)), (
                f"{host}: rule 2 no longer states {CAP_FRAGMENT!r}. The cap is 8 by "
                "standing pilot arbitration; changing it means changing this constant, "
                "which is the visible decision this assertion exists to force."
            )

    def test_lessons_capture_is_in_the_chain_tail_on_all_five_hosts(self) -> None:
        """P3 added the LESSONS capture to the chain and nothing pinned it — so a
        simplification could drop the loop's only entry point with no test red.
        """
        for host in ORCHESTRATOR_DEFS:
            assert LESSON_CAPTURE in _read(host), (
                f"{host}: the {LESSON_CAPTURE} capture has left the chain; the LESSONS "
                "loop's producer would then have no declared entrance on this host"
            )

    def test_class_zero_stays_within_eighty_chars_of_gitleaks_on_all_five_hosts(self) -> None:
        """The proximity window, with its bound in the test's NAME (L-00000190):
        this test cannot pass on a window of 8000 without its name becoming false.
        """
        for host in ORCHESTRATOR_DEFS:
            assert proximity_holds(_read(host), "class-0", "gitleaks", PROXIMITY_CHARS), (
                f"{host}: 'class-0' no longer sits within {PROXIMITY_CHARS} chars of "
                "'gitleaks' — the secrets-gate rule has drifted from its scanner, which "
                "turns 'class-0 is active in both regimes' into a different claim"
            )

    def test_negative_control_the_order_rule_refuses_a_shuffled_chain(self) -> None:
        """RE-ENABLE THE DEFECT AND REQUIRE A RED (L-00000057). The rule is
        replayed as the SAME function on mutated text.
        """
        block = chain_block(_read("claude"))
        assert block is not None and not node_order_violations(block), "base not green"

        # (a) DELETION — the realistic failure: a simplification drops the gate
        # from the diagram.
        cut = block.replace(GATE, "")
        assert cut != block, "the deletion mutation changed nothing — it measures nothing"
        assert node_order_violations(cut), (
            "THE ORDER RULE DOES NOT BITE ON A DELETION: with the human gate removed "
            "it still reported a conformant chain."
        )

        # (b) SHUFFLE — the subtler failure: every node still present, but the
        # gate moved BELOW the dev/exec-critic stage, i.e. approval after
        # execution. A presence check would pass this; the order rule must not.
        shuffled = block.replace(GATE, "@@GATE@@")
        shuffled = shuffled.replace("exec-critic", GATE, 1)
        shuffled = shuffled.replace("@@GATE@@", "exec-critic")
        assert shuffled != block, "the shuffle mutation changed nothing"
        assert node_order_violations(shuffled), (
            "THE ORDER RULE DOES NOT BITE ON A SHUFFLE: the human gate was moved "
            "below the execution stage and it still reported a conformant chain — "
            "so it is a presence check wearing an order check's name."
        )

    def test_negative_control_the_anchor_refuses_a_return_to_the_pair(self) -> None:
        """S-00003871 — mutant « retour a la paire ». Le diagramme d AVANT la
        decision du critique unique, remis sur chaque hote : l ancre doit le
        refuser (bloc introuvable), sinon ce filet laisserait revenir la paire en
        vert sur les cinq hotes a la fois — l accord inter-hotes ne voit pas une
        edition coordonnee (L-00000261).
        """
        for host in ORCHESTRATOR_DEFS:
            text = _read(host)
            assert chain_block(text) is not None, f"{host}: base not green"
            mutant = text.replace(BLOCK_START, PAIR_BLOCK_START, 1)
            assert mutant != text, f"{host}: the pair mutation changed nothing — it measures nothing"
            assert chain_block(mutant) is None, (
                f"{host}: THE ANCHOR DOES NOT BITE ON A RETURN TO THE PAIR: the "
                "pre-S-00003871 diagram still yields a chain block"
            )

    def test_negative_control_the_pins_refuse_the_other_language(self) -> None:
        """T-01M5S9338BJP1B5RM3TG14AMYT — the re-pins keep their strength: on every host, the
        diagram head translated to English yields no chain block, the English gate node leaves the
        order rule red, and the French cap fragment (prose) no longer satisfies rule 2."""
        for host in ORCHESTRATOR_DEFS:
            text = _read(host)
            block = chain_block(text)
            assert block is not None and not node_order_violations(block), f"{host}: base not green"
            mutant = text.replace(BLOCK_START, EN_BLOCK_START, 1)
            assert mutant != text and chain_block(mutant) is None, (
                f"{host}: the head in English still anchors")
            english_gate = block.replace(GATE, EN_GATE)
            assert english_gate != block and node_order_violations(english_gate), f"{host}: the English gate passes"
            assert cap_holds(text), f"{host}: base not green"
            french_cap = text.replace(CAP_FRAGMENT, "Max 8 allers-retours")
            assert french_cap != text, f"{host}: the cap mutation changed nothing"
            assert not cap_holds(french_cap), f"{host}: rule 2 still holds on the French cap fragment"

    def test_negative_control_the_proximity_rule_refuses_a_widened_gap(self) -> None:
        """The window is the whole point: a presence check would pass on text
        where the two tokens are paragraphs apart. Prove the window bites.
        """
        text = _read("claude")
        assert proximity_holds(text, "class-0", "gitleaks", PROXIMITY_CHARS), "base not green"
        # Same tokens, deliberately far apart, nothing else.
        far = "class-0" + ("x" * (PROXIMITY_CHARS * 4)) + "gitleaks"
        assert not proximity_holds(far, "class-0", "gitleaks", PROXIMITY_CHARS), (
            "THE PROXIMITY RULE DOES NOT BITE: it accepted the two tokens "
            f"{PROXIMITY_CHARS * 4} characters apart, so it is a presence check "
            "wearing a window's name."
        )
        # And it must refuse when the anchor is absent entirely, rather than
        # returning True on a vacuous match.
        assert not proximity_holds("class-0 alone", "class-0", "gitleaks", PROXIMITY_CHARS), (
            "the proximity rule returned True with the anchor absent — a vacuous match"
        )

    def test_the_unpinned_disclaimer_is_gone_now_that_this_suite_exists(self) -> None:
        """THE SENTENCE THAT SAID THIS TEXT WAS UNPINNED MUST NOT SURVIVE THIS
        SUITE. Two hosts carried "No test pins this text on this host"; after this
        file that is false, and a doc asserting the wrong thing about its own
        coverage is what stops anyone from going to look (L-00000111) — here in
        the direction that UNDERSTATES coverage, which wastes the next reader's
        time instead of misleading them, but is still false.

        Measured with a MULTILINE pattern (L-00000237): a line-by-line search
        would miss an occurrence folded across two lines by reformatting.
        """
        for host in ORCHESTRATOR_DEFS:
            text = _read(host)
            stale = re.search(r"No\s+test\s+pins\s+this\s+text", text, re.S)
            assert stale is None, (
                f"{host}: still declares its chain text unpinned, but "
                "test_gates_chain_contract.py pins it. Update the sentence."
            )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
