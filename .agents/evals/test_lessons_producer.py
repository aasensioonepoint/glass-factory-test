"""The LESSONS loop has a PRODUCER, and it is pinned end to end (T-00000362).

WHAT WAS UNPINNED. Every link DOWNSTREAM of the journal was tested — `retro.py`
has its own suite, the two skills shipped by P3 are covered, and
`test_gates_chain_contract.py` pins `LECON_CANDIDATE` inside the chain diagram on
all five hosts. Nothing pinned the link UPSTREAM: that a verdict carrying
`LECON_CANDIDATE` ever reaches `retro.py add`. So `retro.py`, the journal and both
skills could stay PERFECTLY GREEN and PERFECTLY INERT — a loop whose producer is
disconnected passes every test it has.

AND THE PRODUCER IS NOT WHO YOU WOULD GUESS, which is exactly why it needs pinning
rather than assuming. Measured across the five hosts:

  * `plan-critic` and `plan-critic-sonnet-max` declared `tools: Read, Grep, Glob`
    on claude, gemini and kimi, `["read", "search"]` on copilot and
    `sandbox_mode = "read-only"` on codex — without a shell anywhere — UNTIL
    T-00000707. Since then the four plan defs carry a VERIFYING shell on every
    host (`Bash`, `"shell"`, codex still `read-only`), so they COULD run
    `retro.py add`: what keeps them from it is no longer a missing capability
    but their contract.
  * `exec-critic` has a shell on claude, gemini, copilot and kimi — but codex is
    `sandbox_mode = "read-only"`, so the write is not open there either.

A contract telling a critic to journal would therefore prescribe a write the
critic is forbidden — and where the capability IS there, the failure mode is worse
than a silent no-op: a judge writing the journal it is judged by. So the critics
CARRY the line in their verdict and the ORCHESTRATOR journals it, exactly as it
already drives `tasks.py` and `ledger.py`. This suite pins that split, on both
ends — and since T-00000707 the textual disclaimer is the ONLY thing holding the
judge/writer separation on the plan defs: more load-bearing than before, not less.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CRITICS = {
    "claude/plan-critic": ROOT / ".claude" / "agents" / "plan-critic.md",
    "claude/exec-critic": ROOT / ".claude" / "agents" / "exec-critic.md",
    "codex/plan-critic": ROOT / ".codex" / "agents" / "plan-critic.toml",
    "codex/exec-critic": ROOT / ".codex" / "agents" / "exec-critic.toml",
    "gemini/plan-critic": ROOT / ".gemini" / "agents" / "plan-critic.md",
    "gemini/exec-critic": ROOT / ".gemini" / "agents" / "exec-critic.md",
    "copilot/plan-critic": ROOT / ".github" / "agents" / "plan-critic.agent.md",
    "copilot/exec-critic": ROOT / ".github" / "agents" / "exec-critic.agent.md",
    "kimi/plan-critic": ROOT / ".kimi-code" / "agents" / "plan-critic.md",
    "kimi/exec-critic": ROOT / ".kimi-code" / "agents" / "exec-critic.md",
    # T-00000707 : les cinq defs de Critique B entrent dans le filet. Elles
    # portaient deja le champ et le desaveu sans etre surveillees — et deux
    # d entre elles (codex, copilot) disaient « tracked » sans « journal EXISTS »,
    # ce que ce filet n a jamais vu parce qu il ne les lisait pas.
    "claude/plan-critic-sonnet-max": ROOT / ".claude" / "agents" / "plan-critic-sonnet-max.md",
    "codex/plan-critic-sonnet-max": ROOT / ".codex" / "agents" / "plan-critic-sonnet-max.toml",
    "gemini/plan-critic-sonnet-max": ROOT / ".gemini" / "agents" / "plan-critic-sonnet-max.md",
    "copilot/plan-critic-sonnet-max": ROOT / ".github" / "agents" / "plan-critic-sonnet-max.agent.md",
    "kimi/plan-critic-sonnet-max": ROOT / ".kimi-code" / "agents" / "plan-critic-sonnet-max.md",
}

ORCHESTRATORS = {
    "claude": ROOT / ".claude" / "agents" / "orchestrator.md",
    "codex": ROOT / ".codex" / "agents" / "orchestrator.toml",
    "gemini": ROOT / ".gemini" / "agents" / "orchestrator.md",
    "copilot": ROOT / ".github" / "agents" / "orchestrator.agent.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "orchestrator.md",
}

FIELD = "LECON_CANDIDATE"
JOURNAL_CMD = "retro.py add"
JOURNAL_PATH = "retro/LESSONS.md"

# The sentence that kept the channel SHUT until T-00000361. Matched MULTILINE
# (L-00000237): a line-by-line search misses an occurrence folded across two lines
# by reformatting, and this is precisely a net that must not go green on a broken
# pattern.
CLOSED_CHANNEL = re.compile(r"journal\s+does\s+not\s+exist\s+yet", re.S | re.I)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class LessonsProducerTests:
    def test_non_vacuity_all_twenty_surfaces_exist(self) -> None:
        """Twenty files, named. Every assertion below iterates one of the two
        maps, and an emptied map passes vacuously (L-00000232)."""
        assert len(CRITICS) == 15, "the critic map no longer holds 15 surfaces"
        assert len(ORCHESTRATORS) == 5, "the orchestrator map no longer holds 5 surfaces"
        for label, path in {**CRITICS, **ORCHESTRATORS}.items():
            assert path.is_file(), f"{label}: {path} is missing"

    def test_every_critic_emits_the_lesson_field(self) -> None:
        """THE UPSTREAM LINK. Without the field in the verdict template there is
        nothing for the orchestrator to journal, and the whole loop below is
        plumbing with no water in it."""
        missing = [label for label, path in CRITICS.items() if FIELD not in read(path)]
        assert not missing, (
            f"critic def(s) no longer emit {FIELD}: {missing}. The LESSONS loop's "
            "producer is disconnected, and every downstream test would stay green."
        )

    def test_the_channel_is_open_on_every_critic(self) -> None:
        """The regression pin on T-00000361. The sentence "the journal does not
        exist yet" told the critic to keep the line in its verdict and go no
        further; while it stood, the loop was inert BY CONTRACT.
        """
        still_closed = [
            label for label, path in CRITICS.items() if CLOSED_CHANNEL.search(read(path))
        ]
        assert not still_closed, (
            f"critic def(s) still declare the journal absent: {still_closed} — the "
            f"journal is tracked at {JOURNAL_PATH}, so that sentence closes a channel "
            "that is open"
        )
        # POSITIVE WITNESS: the absence above must not be the result of a pattern
        # that matches nothing. Every critic must state the journal EXISTS.
        silent = [label for label, path in CRITICS.items() if "journal EXISTS" not in read(path)]
        assert not silent, (
            f"critic def(s) say nothing about the journal existing: {silent} — the "
            "zero above would then be measuring a broken pattern, not an open channel"
        )

    def test_no_critic_claims_to_run_the_journal_command_itself(self) -> None:
        """THE ROLE-HONESTY PIN, and it is the load-bearing one.

        Until T-00000707 this pinned a CAPABILITY: `plan-critic` lacked a shell
        on every host, so a contract telling it to run `retro.py add` prescribed
        a silent no-op. Since T-00000707 the four plan defs HAVE a verifying
        shell everywhere (`Bash` / `"shell"`; codex still `read-only`), so they
        COULD run it — which is exactly why the textual disclaimer is now the
        ONLY thing holding the judge/writer separation: a critic that journals
        writes the record it is judged by. So each critic def that mentions the
        command must, in the same breath, say it does NOT run it — more
        load-bearing than before, not less. (`exec-critic` on codex is still
        `read-only`.)
        """
        for label, path in CRITICS.items():
            text = read(path)
            if JOURNAL_CMD not in text:
                continue
            # TWO alternatives, not three. A third — "the orchestrator journals
            # it" — used to sit here, and it lives on the SAME LECON line of all
            # fifteen critics: erasing "You never run that command" from a def
            # left this arm green 15/15 (measured on T-00000707's first shard,
            # mutant M3). The disclaimer is what this arm pins, so only the
            # disclaimer may satisfy it.
            disclaims = re.search(
                r"(?:You do NOT run that command|You never run that command)", text, re.S
            )
            assert disclaims, (
                f"{label}: mentions `{JOURNAL_CMD}` without the disclaimer 'You never/do "
                "NOT run that command' — the judge/writer split rests on that line alone "
                "since T-00000707"
            )

    def test_every_orchestrator_names_the_journal_command(self) -> None:
        """THE DOWNSTREAM LINK, on the agent that actually has the capability."""
        for host, path in ORCHESTRATORS.items():
            text = read(path)
            assert FIELD in text, f"{host}: orchestrator does not mention {FIELD}"
            assert JOURNAL_CMD in text, (
                f"{host}: orchestrator does not name `{JOURNAL_CMD}` — the field would "
                "be carried in a verdict and then dropped, which is the disconnected "
                "producer this suite exists to prevent"
            )

    def test_negative_control_both_link_rules_refuse_a_severed_chain(self) -> None:
        """RE-ENABLE THE DEFECT (L-00000057), replayed on the SAME predicates."""
        # Upstream severed: the field removed from a critic.
        text = read(CRITICS["claude/exec-critic"])
        assert FIELD in text, "base not green"
        severed = text.replace(FIELD, "SOMETHING_ELSE")
        assert FIELD not in severed, "the mutation changed nothing"

        # Downstream severed: the command removed from an orchestrator.
        otext = read(ORCHESTRATORS["claude"])
        assert JOURNAL_CMD in otext, "base not green"
        odead = otext.replace(JOURNAL_CMD, "nothing.py add")
        assert JOURNAL_CMD not in odead, "the mutation changed nothing"

        # And the closed-channel matcher must be able to FIRE, or the arm above
        # is an absence check on a pattern that never matches anything.
        assert CLOSED_CHANNEL.search("the journal does   not\nexist yet, alas"), (
            "the CLOSED_CHANNEL pattern does not match its own multiline target — the "
            "open-channel arm would go green on a broken regex"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
