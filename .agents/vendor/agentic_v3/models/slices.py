"""
Stdlib dataclass Context Slices for Scope-Slicing across agent roles.
Prevents Context Pollution by transmitting only strictly necessary data to each agent.

Every slice CHECKS its field types at construction (T-00000680) through
``events._exiger`` — a ``TypeError`` naming ``<Class>.<field>``, never a coercion.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from agentic_v3.models.events import _LISTE_STR, _exiger


@dataclass(kw_only=True)
class SpecChunkSlice:
    """Mutable slice of a versioned Markdown specification requirement.

    ``.version`` and ``.spec_diff_from_previous`` are reassigned by
    ``ingestion/parse_specs.py`` on hot spec mutation, so this dataclass is never
    frozen — and those reassignments are NOT type-checked (the border bites at
    construction only).
    """

    req_id: str
    file_path: str
    section_title: str
    content_markdown: str
    version: int = 1
    spec_diff_from_previous: Optional[str] = None

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "req_id", self.req_id, str)
        _exiger(n, "file_path", self.file_path, str)
        _exiger(n, "section_title", self.section_title, str)
        _exiger(n, "content_markdown", self.content_markdown, str)
        _exiger(n, "version", self.version, int)
        _exiger(n, "spec_diff_from_previous", self.spec_diff_from_previous, (str, None))


@dataclass(kw_only=True)
class DevContextSlice:
    """Scoped context delivered to the Dev Agent for code generation/modification.

    ``__post_init__`` checks the types FIRST, THEN caps ``applied_lessons`` at 3 (the
    former field validator became an explicit truncation; a ``str`` is refused, no
    longer truncated as a sequence).
    """

    task_id: str
    spec_chunk: SpecChunkSlice
    target_files: List[str] = field(default_factory=list)
    ctags_symbols: List[str] = field(default_factory=list)
    last_rejection_reason: Optional[str] = None
    is_spec_updated: bool = False
    applied_lessons: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "spec_chunk", self.spec_chunk, SpecChunkSlice)
        _exiger(n, "target_files", self.target_files, _LISTE_STR)
        _exiger(n, "ctags_symbols", self.ctags_symbols, _LISTE_STR)
        _exiger(n, "last_rejection_reason", self.last_rejection_reason, (str, None))
        _exiger(n, "is_spec_updated", self.is_spec_updated, bool)
        _exiger(n, "applied_lessons", self.applied_lessons, _LISTE_STR)
        if len(self.applied_lessons) > 3:
            self.applied_lessons = self.applied_lessons[:3]


@dataclass(kw_only=True)
class CriticContextSlice:
    """Scoped context delivered to the Critic Agent for code review & static analysis."""

    task_id: str
    spec_chunk: SpecChunkSlice
    generated_code_diff: str
    target_files: List[str] = field(default_factory=list)
    static_analysis_reports: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "spec_chunk", self.spec_chunk, SpecChunkSlice)
        _exiger(n, "generated_code_diff", self.generated_code_diff, str)
        _exiger(n, "target_files", self.target_files, _LISTE_STR)
        _exiger(n, "static_analysis_reports", self.static_analysis_reports, _LISTE_STR)


@dataclass(kw_only=True)
class TestContextSlice:
    """Scoped context delivered to the Test Agent for test execution."""

    task_id: str
    target_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    sandbox_environment: str = "isolated-pytest"

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "target_files", self.target_files, _LISTE_STR)
        _exiger(n, "test_files", self.test_files, _LISTE_STR)
        _exiger(n, "sandbox_environment", self.sandbox_environment, str)


@dataclass(kw_only=True)
class ScanContextSlice:
    """Scoped context delivered to the Security Scan Agent for SAST/DAST verification."""

    task_id: str
    target_files: List[str] = field(default_factory=list)
    security_policies: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "target_files", self.target_files, _LISTE_STR)
        _exiger(n, "security_policies", self.security_policies, _LISTE_STR)


@dataclass(kw_only=True)
class FrontDesignContextSlice:
    """Scoped context delivered to the Front/Design Agent for visual reconciliation."""

    task_id: str
    target_url: str
    figma_component_id: Optional[str] = None
    expected_design_tokens: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "target_url", self.target_url, str)
        _exiger(n, "figma_component_id", self.figma_component_id, (str, None))
        _exiger(n, "expected_design_tokens", self.expected_design_tokens, dict)
