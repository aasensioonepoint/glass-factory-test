"""Contract tests for progressive planning and safe draft resumption."""
from pathlib import Path


AGENTS = Path(__file__).resolve().parents[1]
ROOT = AGENTS.parent

PLANNING_SKILL = (AGENTS / "skills" / "planning" / "SKILL.md").read_text(encoding="utf-8")
PLANNING_COMMAND = (ROOT / ".claude" / "commands" / "planning.md").read_text(
    encoding="utf-8"
)
KICKOFF_SKILL = (AGENTS / "skills" / "kickoff" / "SKILL.md").read_text(encoding="utf-8")
KICKOFF_COMMAND = (ROOT / ".claude" / "commands" / "kickoff.md").read_text(
    encoding="utf-8"
)
POOL = (ROOT / "core-scripts" / "plan_pool.py").read_text(encoding="utf-8")
POOL_TEST = (ROOT / "core-scripts" / "plan_pool.test.sh").read_text(encoding="utf-8")
NIGHT = (ROOT / ".claude" / "commands" / "night.md").read_text(encoding="utf-8")

#: Le littéral de la postériorité dans plan_pool.py — clé `sort_key` (0, n) / (1, ulid).
POSTERIORITE = 'sort_key(e["id"]) > sort_key(plan["id"])'

PLANNING_SURFACES = (PLANNING_SKILL, PLANNING_COMMAND)
RESUME_SURFACES = PLANNING_SURFACES + (KICKOFF_SKILL, KICKOFF_COMMAND)


def test_draft_is_written_before_critic():
    for surface in PLANNING_SURFACES:
        step = surface[surface.index("Étape 2") :]
        planner = step.index("planner")
        written = step.index("écriture", planner)
        critic = step.index("plan-critic", written)
        assert planner < written < critic
        assert "STATUS: IN_PROGRESS" in surface


def test_no_go_amends_same_file():
    for surface in PLANNING_SURFACES:
        normalized = " ".join(surface.split())
        assert "CRITIC_REJECTED" in surface
        assert "même fichier" in surface
        assert "REVISION" in surface
        assert "IN_PROGRESS → CRITIC_REJECTED → IN_PROGRESS → READY" in normalized


def test_resume_uses_latest_revision():
    for surface in RESUME_SURFACES:
        normalized = " ".join(surface.split()).lower()
        assert "latest" in normalized or "dernière entrée numérique" in normalized
        assert "revision" in normalized
        assert "sha256" in normalized
    assert "kind=plan" in KICKOFF_COMMAND
    assert "kind=verdict" in KICKOFF_COMMAND


def test_corrupt_draft_forces_full_replan():
    for surface in RESUME_SURFACES:
        normalized = " ".join(surface.split()).lower()
        assert "corrupt" in normalized
        assert "full replanning" in normalized or "replanification complète" in normalized


def test_lost_write_set_forces_full_replan():
    for surface in RESUME_SURFACES:
        normalized = " ".join(surface.split()).lower()
        assert "write-set" in normalized
        assert "lost" in normalized or "perdu" in normalized or "absent" in normalized
        assert "full replanning" in normalized or "replanification complète" in normalized


def test_checkpoint_order_is_plan_then_verdict():
    for surface in PLANNING_SURFACES:
        plan_checkpoint = surface.index('specs.py add "Plan @ <sha>')
        verdict_checkpoint = surface.index('specs.py add "plan-critic <VERDICT>"')
        assert plan_checkpoint < verdict_checkpoint
    # T-00000726 (C1e) : la postériorité se juge sur la clé à DEUX ÉTAGES —
    # `S-<ULID>` après tout `S-` ancien —, plus sur la seule queue numérique.
    assert POSTERIORITE in POOL


def test_old_verdict_does_not_authorize_new_revision():
    assert POSTERIORITE in POOL
    assert "un ancien verdict n'autorise pas revision 2" in POOL_TEST
    for surface in RESUME_SURFACES:
        normalized = " ".join(surface.split()).lower()
        assert "ancien verdict" in normalized or "old verdict" in normalized


def test_hash_mismatch_is_not_ready():
    assert "recorded_hash != actual_hash" in POOL
    assert 'Verdict(tid, "STALE"' in POOL
    assert "HASH DIVERGENT" in POOL_TEST
    assert "sha256 du verdict different des octets -> STALE" in POOL_TEST
    assert "night-eligible: approved" in NIGHT
    assert "NO_GO` (ou `FAIL` historique)" in NIGHT


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
