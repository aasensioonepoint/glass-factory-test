"""
Stdlib dataclass models for Agentic V3 (Context Slices, Events, and Structured Outputs).

API SURFACE (rétrécissement DÉCLARÉ, T-00000655): only the two tri-value classes
``CriticVerdictEvent`` and ``CriticOutputPayload`` keep the ``model_dump()`` /
``model_validate()`` methods under their original names (they inherit
``TriValueVerdictMixin``). The 17 other exported dataclasses (plus the ``EventType``
enum) are BARE — dump via ``dataclasses.asdict(instance)`` and build via the
constructor; they carry no ``model_dump``/``model_validate`` (calling those raises
``AttributeError``). This perimeter is ASSUMED (F10 scoped the API to the tri-value
models), not a gap, and is pinned by
``test_seules_les_deux_classes_tri_valeur_portent_model_dump``.

TYPE BORDER (T-00000680): bare does NOT mean unchecked. All 19 dataclasses CHECK
their field types at construction — constructor and ``model_validate`` alike — and
refuse a wrong type with a ``TypeError`` naming ``<Class>.<field>``, never a
coercion (a ``bool`` is not an ``int``, a bare string is not an ``EventType``). The
two tri-value classes too, except ``verdict``/``passed``, governed by the F6
reconciliation (``ValueError``). BOUND: the border bites at CONSTRUCTION, not at
assignment — ``ingestion/parse_specs.py`` reassigns ``chunk.version`` after
construction, unchecked (a guarded ``__setattr__`` would be another contract).
Pinned by ``agentic_v3/tests/test_models_typage.py``.
"""

from agentic_v3.models.slices import (
    SpecChunkSlice,
    DevContextSlice,
    CriticContextSlice,
    TestContextSlice,
    ScanContextSlice,
    FrontDesignContextSlice,
)
from agentic_v3.models.events import (
    EventType,
    BaseEvent,
    SpecMutatedEvent,
    TaskCreatedEvent,
    CodeGeneratedEvent,
    CriticVerdictEvent,
    TestRunEvent,
    ScanCompletedEvent,
    SpecMutationCancelEvent,
)
from agentic_v3.models.outputs import (
    DevOutputPayload,
    CriticOutputPayload,
    TestOutputPayload,
    ScanOutputPayload,
    VisualDiffReportPayload,
)

__all__ = [
    "SpecChunkSlice",
    "DevContextSlice",
    "CriticContextSlice",
    "TestContextSlice",
    "ScanContextSlice",
    "FrontDesignContextSlice",
    "EventType",
    "BaseEvent",
    "SpecMutatedEvent",
    "TaskCreatedEvent",
    "CodeGeneratedEvent",
    "CriticVerdictEvent",
    "TestRunEvent",
    "ScanCompletedEvent",
    "SpecMutationCancelEvent",
    "DevOutputPayload",
    "CriticOutputPayload",
    "TestOutputPayload",
    "ScanOutputPayload",
    "VisualDiffReportPayload",
]
