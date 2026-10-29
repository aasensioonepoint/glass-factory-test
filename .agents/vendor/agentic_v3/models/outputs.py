"""
Stdlib dataclass Structured Output schemas for LLM Node responses.
Guarantees deterministic parsing without fragile regex.

Every payload CHECKS its field types at construction (T-00000680) through
``events._exiger`` — a ``TypeError`` naming ``<Class>.<field>``, never a coercion.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union

from agentic_v3.models.events import (
    TriValueVerdictMixin, _ABSENT, _Absent, _LISTE_STR, _exiger,
)


@dataclass(kw_only=True)
class DevOutputPayload:
    """Structured response output from Dev Agent LLM invocation."""

    task_id: str
    explanation: str
    code_diff: str
    modified_files: List[str]
    status: str = "DEV_COMPLETED"

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "explanation", self.explanation, str)
        _exiger(n, "code_diff", self.code_diff, str)
        _exiger(n, "modified_files", self.modified_files, _LISTE_STR)
        _exiger(n, "status", self.status, str)


@dataclass(kw_only=True)
class CriticOutputPayload(TriValueVerdictMixin):
    """Structured critic output carrying the tri-value ``verdict`` (see
    :class:`~agentic_v3.models.events.TriValueVerdictMixin`) alongside the stored
    ``passed`` boolean.

    Its former producer ``agents/critic_agent.py`` was removed by T-012; the schema
    survives as the tri-value contract for ``payload_json``, dumped unchanged via
    ``model_dump()``. ``passed`` carries the ``_ABSENT`` sentinel (imported from
    ``events``, never redefined) so it may be absent at construction and resolved
    in ``__post_init__``.
    """

    task_id: str
    passed: Union[bool, _Absent] = _ABSENT
    rejection_reason: Optional[str] = None
    findings: List[str] = field(default_factory=list)

    def _verifier_types(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "rejection_reason", self.rejection_reason, (str, None))
        _exiger(n, "findings", self.findings, _LISTE_STR)
        _exiger(n, "cause_racine", self.cause_racine, (str, None))
        _exiger(n, "lecon_candidate", self.lecon_candidate, (str, None))


@dataclass(kw_only=True)
class TestOutputPayload:
    """Structured response output from Test Agent invocation."""

    task_id: str
    passed: bool
    test_summary: str
    coverage_percentage: float = 100.0

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "passed", self.passed, bool)
        _exiger(n, "test_summary", self.test_summary, str)
        _exiger(n, "coverage_percentage", self.coverage_percentage, float)


@dataclass(kw_only=True)
class ScanOutputPayload:
    """Structured response output from Security Scan Agent invocation."""

    task_id: str
    passed: bool
    security_summary: str
    vulnerabilities_count: int = 0

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "passed", self.passed, bool)
        _exiger(n, "security_summary", self.security_summary, str)
        _exiger(n, "vulnerabilities_count", self.vulnerabilities_count, int)


@dataclass(kw_only=True)
class VisualDiffReportPayload:
    """Structured response output from Front/Design Agent Playwright visual reconciliation."""

    task_id: str
    match_percentage: float
    has_divergence: bool
    divergence_details: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "match_percentage", self.match_percentage, float)
        _exiger(n, "has_divergence", self.has_divergence, bool)
        _exiger(n, "divergence_details", self.divergence_details, _LISTE_STR)
