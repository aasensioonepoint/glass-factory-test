"""
Stdlib dataclass Event Sourcing schemas for the SQLite events_ledger.

Each event is a :func:`~dataclasses.dataclass` (``kw_only``) — no third-party
dependency. Every class CHECKS its field types at construction (T-00000680): its
``__post_init__`` calls ``_exiger`` once per NAMED field and refuses a wrong type
with a ``TypeError`` naming ``<Class>.<field>`` — never a coercion. The tri-value
critic verdict keeps its reconciliation and its lax ``passed`` coercion through
hand-written stdlib code (see ``TriValueVerdictMixin``), so the historical
validation behaviour is preserved without a validation library.
"""

from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Dict, Literal, Optional, Union


_VALID_VERDICTS = ("GO", "GO_AVEC_RESERVES", "NO_GO")

# F6 — lax ``passed`` coercion table, copied from the differential oracle (never
# guessed) FOR THE str/bytes/int/float/bool inputs: a historical string is matched
# case-insensitively against these lowercase forms WITH NO ``.strip()`` (the oracle
# refuses " true"/"true "/"\ttrue"), ints/floats are accepted only for the values 0
# and 1, and bytes are decoded first. NOT verbatim over EVERY type: ``Decimal(1)`` /
# ``Decimal(0)`` (which the former validation library accepted) are refused here —
# unreachable from a JSON payload, so the narrowing is inert in practice.
_PASSED_TRUE = frozenset({"1", "t", "true", "y", "yes", "on"})
_PASSED_FALSE = frozenset({"0", "f", "false", "n", "no", "off"})


class _Absent:
    """Absent-value sentinel *type*.

    Declared ABOVE ``TriValueVerdictMixin`` so that the annotation
    ``Union[Literal[...], _Absent]`` and the field default ``_ABSENT`` (both
    evaluated at the class body) resolve at import — a name defined lower would
    raise ``NameError``. It is a TYPE, never the instance: its single instance is
    ``_ABSENT`` just below, used only as the default marking a field as unset.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "_ABSENT"


_ABSENT = _Absent()


def _coerce_passed(value: Any) -> Optional[bool]:
    """Coerce a raw ``passed`` value through the F6 table (never raw ``bool()``).

    Returns the coerced bool, or ``None`` when the value is not coercible (e.g.
    ``"banana"``). ``None`` is the caller's signal to refuse the value rather than
    invent a verdict — a raw ``bool()`` would read the string ``"false"`` as
    truthy-True and silently derive/pass a ``GO``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):  # the bool subclass is already handled above
        if value == 0:
            return False
        if value == 1:
            return True
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        low = value.lower()  # NO .strip(): the oracle refuses leading/trailing whitespace
        if low in _PASSED_TRUE:
            return True
        if low in _PASSED_FALSE:
            return False
        return None
    return None


#: Marqueurs d'``attendu`` des deux formes génériques des modèles (T-00000680).
_LISTE_STR = "list[str]"
_DICT_CLES_STR = "dict[str, Any]"


def _exiger(classe: str, champ: str, valeur: Any, attendu: Any) -> None:
    """Frontière de type stdlib (T-00000680) : REFUSE, ne coerce JAMAIS.

    ``attendu`` est un type, ``_LISTE_STR``, ``_DICT_CLES_STR``, ou un tuple
    ``(X, None)`` pour ``Optional[X]``. Règles, écrites UNE fois :
      - ``Optional[X]`` : ``None`` admis, sinon la règle de ``X`` ;
      - ``str``, ``bool`` : ``isinstance`` ;
      - ``int`` : ``int`` et PAS ``bool`` ; ``float`` : ``int`` ou ``float``, PAS ``bool`` ;
      - ``_LISTE_STR`` (``List[str]``) : ``list`` dont CHAQUE élément est ``str`` ;
      - ``dict`` : ``dict`` ; ``_DICT_CLES_STR`` (``Dict[str, Any]``) : clés ``str`` ;
      - dataclass imbriquée ou ``EventType`` : ``isinstance`` de la classe — une
        chaîne nue n'est PAS un ``EventType`` (rétrécissement DÉCLARÉ).
    Refus : ``TypeError("<Classe>.<champ>: attendu …, reçu …")`` — le type reçu,
    jamais la valeur (un payload peut porter un secret).
    """
    optionnel = isinstance(attendu, tuple)
    if optionnel:
        if valeur is None:
            return
        attendu = attendu[0]
    if attendu is int or attendu is float:
        ok = not isinstance(valeur, bool) and isinstance(
            valeur, (int, float) if attendu is float else int)
    elif attendu == _LISTE_STR:
        ok = isinstance(valeur, list) and all(isinstance(e, str) for e in valeur)
    elif attendu == _DICT_CLES_STR:
        ok = isinstance(valeur, dict) and all(isinstance(k, str) for k in valeur)
    else:
        ok = isinstance(valeur, attendu)
    if not ok:
        nom = attendu if isinstance(attendu, str) else attendu.__name__
        recu = type(valeur).__name__
        if attendu in (_LISTE_STR, _DICT_CLES_STR) and isinstance(valeur, (list, dict)):
            recu += " à élément/clé non-str"
        raise TypeError(
            f"{classe}.{champ}: attendu {f'Optional[{nom}]' if optionnel else nom}, reçu {recu}"
        )


@dataclass(kw_only=True)
class TriValueVerdictMixin:
    """Tri-value critic verdict, first-class beside the legacy ``passed`` boolean.

    ``verdict`` is the source of truth (``GO`` / ``GO_AVEC_RESERVES`` / ``NO_GO``);
    ``passed`` stays a STORED field on each concrete subclass — never computed —
    because the SQLite projector (``db/event_store.py``) reads ``payload["passed"]``
    straight from the persisted dict. ``GO_AVEC_RESERVES`` ADVANCES exactly like
    ``GO`` (``passed=True`` -> projection ``IN_TEST``): définitif côté moteur V3.

    Reconciliation runs in ``__post_init__`` (a dataclass has no "before
    assignment" hook), reading ``passed`` off the subclass by ``getattr``. Both
    ``verdict`` and ``passed`` default to the ``_ABSENT`` sentinel so the four
    historical branches stay reachable — without the sentinel a missing
    keyword-only field would raise ``TypeError`` at construction, BEFORE
    reconciliation could run:
      - verdict present, passed present -> validate the Literal by membership,
        coerce ``passed`` through the F6 table, then refuse an incoherent pair
        (``passed != (verdict != "NO_GO")``) with ``ValueError``;
      - verdict present, passed absent  -> derive ``passed = verdict != "NO_GO"``;
      - passed present, verdict absent  -> coerce ``passed`` (``ValueError`` if not
        coercible), derive ``verdict`` (True -> ``GO``, False -> ``NO_GO``);
      - neither present -> ``TypeError`` (same family as a missing required field).

    BEFORE reconciliation, ``__post_init__`` calls ``_verifier_types()``, which EACH
    concrete subclass defines (T-00000680): ``_exiger`` on its five NON-reconciled
    fields (``task_id``, ``rejection_reason``, ``findings``, ``cause_racine``,
    ``lecon_candidate``). ``verdict``/``passed`` stay governed by F6 above.

    ``model_validate`` / ``model_dump`` are kept under those exact names (consumed
    API): ``model_validate`` refuses a non-dict with ``TypeError`` and filters
    unknown keys before delegating to the constructor; ``model_dump`` is ``asdict``.
    """

    verdict: Union[Literal["GO", "GO_AVEC_RESERVES", "NO_GO"], _Absent] = _ABSENT
    cause_racine: Optional[str] = None
    lecon_candidate: Optional[str] = None

    def _verifier_types(self) -> None:
        """Défini par CHAQUE sous-classe concrète ; l'absence est un refus BRUYANT."""
        raise NotImplementedError(f"{type(self).__name__} doit définir _verifier_types")

    def __post_init__(self) -> None:
        self._verifier_types()  # types des champs NON réconciliés, d'abord
        verdict = self.verdict
        passed = getattr(self, "passed", _ABSENT)
        has_verdict = verdict is not _ABSENT
        has_passed = passed is not _ABSENT

        if has_verdict and has_passed:
            if verdict not in _VALID_VERDICTS:
                raise ValueError(
                    f"verdict hors littéral: {verdict!r} (attendu l'un de {_VALID_VERDICTS})"
                )
            coerced = _coerce_passed(passed)
            if coerced is None:
                raise ValueError(f"passed non coercible: {passed!r}")
            if coerced != (verdict != "NO_GO"):
                raise ValueError(
                    f"incohérent: passed={passed!r} contredit verdict={verdict!r} "
                    "(passed doit valoir verdict != 'NO_GO')"
                )
            self.passed = coerced
            return

        if has_verdict:  # passed absent -> derive it from the verdict
            if verdict not in _VALID_VERDICTS:
                raise ValueError(
                    f"verdict hors littéral: {verdict!r} (attendu l'un de {_VALID_VERDICTS})"
                )
            self.passed = verdict != "NO_GO"
            return

        if has_passed:  # verdict absent (historique) -> derive it from passed
            coerced = _coerce_passed(passed)
            if coerced is None:
                raise ValueError(f"passed non coercible: {passed!r}")
            self.verdict = "GO" if coerced else "NO_GO"
            self.passed = coerced
            return

        # Neither field present: same family as a missing required field (F13).
        raise TypeError("verdict et passed manquants")

    @classmethod
    def model_validate(cls, data: Any) -> "TriValueVerdictMixin":
        """Consumed API kept under its name. A non-dict is refused with ``TypeError``
        (rétrécissement F15 assumé: an instance is no longer re-validated); a dict is
        filtered to the known fields (F11) then handed to the constructor, which
        reconciles verdict and passed in ``__post_init__``."""
        if not isinstance(data, dict):
            raise TypeError(
                f"model_validate attend un dict, reçu {type(data).__name__}"
            )
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def model_dump(self) -> Dict[str, Any]:
        """Consumed API kept under its name: recursive ``asdict`` over nested dataclasses."""
        return asdict(self)


class EventType(str, Enum):
    SPEC_MUTATED = "SPEC_MUTATED"
    TASK_CREATED = "TASK_CREATED"
    CODE_GENERATED = "CODE_GENERATED"
    CRITIC_VERDICT = "CRITIC_VERDICT"
    TEST_RUN = "TEST_RUN"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SPEC_MUTATION_CANCEL = "SPEC_MUTATION_CANCEL"
    VISUAL_RECONCILIATION = "VISUAL_RECONCILIATION"
    BOARD_TASK_OBSERVED = "BOARD_TASK_OBSERVED"
    BOARD_COMMAND_REQUESTED = "BOARD_COMMAND_REQUESTED"
    BOARD_COMMAND_ACKED = "BOARD_COMMAND_ACKED"
    BOARD_COMMAND_FAILED = "BOARD_COMMAND_FAILED"
    BOARD_RUNNING_REPLACED = "BOARD_RUNNING_REPLACED"


@dataclass(kw_only=True)
class BaseEvent:
    """Base event structure matching the SQLite events_ledger table.

    ``__post_init__`` checks every field type FIRST (``_exiger`` — a bare string is
    not an ``EventType``), THEN keeps the ``attempt >= 0`` guard as ``ValueError``.
    """

    event_id: Optional[int] = None
    task_id: str
    agent_role: str
    event_type: EventType
    payload_json: Dict[str, Any] = field(default_factory=dict)
    operation_id: Optional[str] = None
    event_kind: Optional[str] = None
    attempt: int = 0
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "event_id", self.event_id, (int, None))
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "agent_role", self.agent_role, str)
        _exiger(n, "event_type", self.event_type, EventType)
        _exiger(n, "payload_json", self.payload_json, _DICT_CLES_STR)
        _exiger(n, "operation_id", self.operation_id, (str, None))
        _exiger(n, "event_kind", self.event_kind, (str, None))
        _exiger(n, "attempt", self.attempt, int)
        _exiger(n, "created_at", self.created_at, (str, None))
        if self.attempt < 0:
            raise ValueError(f"attempt doit être >= 0, reçu {self.attempt!r}")


@dataclass(kw_only=True)
class SpecMutatedEvent:
    req_id: str
    version: int
    diff: str
    file_path: str
    hash_checksum: str

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "req_id", self.req_id, str)
        _exiger(n, "version", self.version, int)
        _exiger(n, "diff", self.diff, str)
        _exiger(n, "file_path", self.file_path, str)
        _exiger(n, "hash_checksum", self.hash_checksum, str)


@dataclass(kw_only=True)
class TaskCreatedEvent:
    task_id: str
    req_id: str
    spec_version: int
    assignee: str

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "req_id", self.req_id, str)
        _exiger(n, "spec_version", self.spec_version, int)
        _exiger(n, "assignee", self.assignee, str)


@dataclass(kw_only=True)
class CodeGeneratedEvent:
    task_id: str
    code_diff: str
    modified_files: list[str]

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "code_diff", self.code_diff, str)
        _exiger(n, "modified_files", self.modified_files, _LISTE_STR)


@dataclass(kw_only=True)
class CriticVerdictEvent(TriValueVerdictMixin):
    task_id: str
    passed: Union[bool, _Absent] = _ABSENT
    rejection_reason: Optional[str] = None
    findings: list[str] = field(default_factory=list)

    def _verifier_types(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "rejection_reason", self.rejection_reason, (str, None))
        _exiger(n, "findings", self.findings, _LISTE_STR)
        _exiger(n, "cause_racine", self.cause_racine, (str, None))
        _exiger(n, "lecon_candidate", self.lecon_candidate, (str, None))


@dataclass(kw_only=True)
class TestRunEvent:
    task_id: str
    passed: bool
    test_output: str
    coverage_percentage: float

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "passed", self.passed, bool)
        _exiger(n, "test_output", self.test_output, str)
        _exiger(n, "coverage_percentage", self.coverage_percentage, float)


@dataclass(kw_only=True)
class ScanCompletedEvent:
    task_id: str
    vulnerabilities_found: int
    security_report: str

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "vulnerabilities_found", self.vulnerabilities_found, int)
        _exiger(n, "security_report", self.security_report, str)


@dataclass(kw_only=True)
class SpecMutationCancelEvent:
    task_id: str
    req_id: str
    reason: str

    def __post_init__(self) -> None:
        n = type(self).__name__
        _exiger(n, "task_id", self.task_id, str)
        _exiger(n, "req_id", self.req_id, str)
        _exiger(n, "reason", self.reason, str)
