"""T-00000680 — frontière de type stdlib des 19 dataclasses de `agentic_v3.models`.

Le port pydantic -> dataclasses (T-00000655) avait PERDU la validation de type ;
ce banc en épingle le retour, stdlib seule (`isinstance`), JAMAIS par coercition.
Sans E/S, sans store.

Les classes sont atteintes par `getattr(agentic_v3.models, nom)` sur `__all__`, et
jamais importées dans l'espace de ce module : `pytest.ini` porte
`python_classes = *Tests Test*`, donc `TestRunEvent`, `TestContextSlice` et
`TestOutputPayload` y seraient prises pour des classes de test.

  T1 FERMETURE — `_NOMINAUX` couvre EXACTEMENT les dataclasses de `__all__` (19), le
     balayage compte 87 cas et 13 champs `Optional` : une classe ou un champ ajouté
     sans entrée rougit.
  T2 BALAYAGE — chaque `(classe, champ)` reçoit `object()` et lève `TypeError`
     NOMMANT `<Classe>.<champ>` (au BASE, `attempt` et `applied_lessons` levaient
     déjà un `TypeError` ANONYME venu de `<`/`len()` : c'est le nom qui les fait
     rougir). `verdict`/`passed` des deux classes tri-valeur sont exclus : table F6
     et leur `ValueError`, épinglées par `test_critic_verdict_trivalue.py`.
  T3 BORNES — `bool` refusé où `int` est attendu, `int` admis où `float` l'est,
     élément non-`str` de liste refusé, dict refusé pour une dataclass imbriquée,
     `None` admis sur chaque `Optional`, `attempt >= 0` conservé en `ValueError`.
  T4 NOMINAL — les 19 se construisent avec CHAQUE champ valué, valeurs intactes.
  X2 — le refus nomme le TYPE reçu, jamais la valeur (un payload peut porter un secret).
"""

import dataclasses
import re
import typing

import pytest

import agentic_v3.models as M
from agentic_v3.models.events import TriValueVerdictMixin

_TRI_VALEUR_EXCLUS = ("verdict", "passed")


def _chunk():
    return M.SpecChunkSlice(**_NOMINAUX["SpecChunkSlice"]())


#: Kwargs VALIDES par NOM de classe, chaque champ valué (sauf `passed` des deux
#: tri-valeur, DÉRIVÉ du verdict). Des fabriques : un dict neuf par appel.
_NOMINAUX: typing.Dict[str, typing.Callable[[], dict]] = {
    "SpecChunkSlice": lambda: dict(
        req_id="REQ-1", file_path="spec.md", section_title="t", content_markdown="c",
        version=2, spec_diff_from_previous="d"),
    "DevContextSlice": lambda: dict(
        task_id="T", spec_chunk=_chunk(), target_files=["a.py"], ctags_symbols=["f"],
        last_rejection_reason="r", is_spec_updated=True, applied_lessons=["L1"]),
    "CriticContextSlice": lambda: dict(
        task_id="T", spec_chunk=_chunk(), generated_code_diff="d",
        target_files=["a.py"], static_analysis_reports=["rep"]),
    "TestContextSlice": lambda: dict(
        task_id="T", target_files=["a.py"], test_files=["test_a.py"],
        sandbox_environment="isolated-pytest"),
    "ScanContextSlice": lambda: dict(
        task_id="T", target_files=["a.py"], security_policies=["p"]),
    "FrontDesignContextSlice": lambda: dict(
        task_id="T", target_url="http://x", figma_component_id="1:2",
        expected_design_tokens={"color": "#fff"}),
    "BaseEvent": lambda: dict(
        event_id=1, task_id="T", agent_role="r", event_type=M.EventType.TASK_CREATED,
        payload_json={"k": 1}, operation_id="op", event_kind="k", attempt=1,
        created_at="2026-09-27T00:00:00Z"),
    "SpecMutatedEvent": lambda: dict(
        req_id="R", version=1, diff="d", file_path="f", hash_checksum="h"),
    "TaskCreatedEvent": lambda: dict(task_id="T", req_id="R", spec_version=1, assignee="a"),
    "CodeGeneratedEvent": lambda: dict(task_id="T", code_diff="d", modified_files=["a.py"]),
    "CriticVerdictEvent": lambda: dict(
        task_id="T", verdict="GO_AVEC_RESERVES", cause_racine="c", lecon_candidate="l",
        rejection_reason="r", findings=["f"]),
    "TestRunEvent": lambda: dict(
        task_id="T", passed=True, test_output="o", coverage_percentage=87.5),
    "ScanCompletedEvent": lambda: dict(
        task_id="T", vulnerabilities_found=0, security_report="s"),
    "SpecMutationCancelEvent": lambda: dict(task_id="T", req_id="R", reason="r"),
    "DevOutputPayload": lambda: dict(
        task_id="T", explanation="e", code_diff="d", modified_files=["a.py"],
        status="DEV_COMPLETED"),
    "CriticOutputPayload": lambda: dict(
        task_id="T", verdict="GO_AVEC_RESERVES", cause_racine="c", lecon_candidate="l",
        rejection_reason="r", findings=["f"]),
    "TestOutputPayload": lambda: dict(
        task_id="T", passed=False, test_summary="s", coverage_percentage=50.0),
    "ScanOutputPayload": lambda: dict(
        task_id="T", passed=True, security_summary="s", vulnerabilities_count=2),
    "VisualDiffReportPayload": lambda: dict(
        task_id="T", match_percentage=99.5, has_divergence=True, divergence_details=["px"]),
}


def _dataclasses_exportees() -> typing.List[str]:
    return [n for n in M.__all__ if dataclasses.is_dataclass(getattr(M, n))]


def _tri_valeur(nom: str) -> bool:
    return issubclass(getattr(M, nom), TriValueVerdictMixin)


def _cas_balayage() -> list:
    return [
        pytest.param(nom, f.name, id=f"{nom}.{f.name}")
        for nom in _dataclasses_exportees()
        for f in dataclasses.fields(getattr(M, nom))
        if not (_tri_valeur(nom) and f.name in _TRI_VALEUR_EXCLUS)
    ]


def _cas_optionnels() -> list:
    cas = []
    for nom in _dataclasses_exportees():
        indices = typing.get_type_hints(getattr(M, nom))
        for f in dataclasses.fields(getattr(M, nom)):
            if type(None) in typing.get_args(indices[f.name]):
                cas.append(pytest.param(nom, f.name, id=f"{nom}.{f.name}"))
    return cas


_CAS = _cas_balayage()
_OPTIONNELS = _cas_optionnels()


def _construire(nom: str, **surcharge):
    return getattr(M, nom)(**{**_NOMINAUX[nom](), **surcharge})


def test_t1_fermeture_nominaux_egaux_aux_dataclasses_exportees():
    exportees = set(_dataclasses_exportees())
    assert len(exportees) == 19
    assert set(_NOMINAUX) == exportees
    assert len(_CAS) == 87, "balayage : 91 champs moins verdict/passed des 2 tri-valeur"
    assert len(_OPTIONNELS) == 13


@pytest.mark.parametrize("nom,champ", _CAS)
def test_t2_balayage_object_refuse_en_typeerror_nommant_le_champ(nom, champ):
    with pytest.raises(TypeError, match=re.escape(f"{nom}.{champ}:")):
        _construire(nom, **{champ: object()})


class _Porteur:
    """Valeur de type FAUX dont le repr/str porterait un secret (X2)."""
    def __repr__(self) -> str:
        return "fuite-X2"
    __str__ = __repr__


@pytest.mark.parametrize("nom,champ,valeur", [
    *(pytest.param(*cas.values, _Porteur(), id=f"x2-{cas.id}") for cas in _CAS),
    pytest.param("DevContextSlice", "target_files", ["a", _Porteur()], id="x2-liste"),
    pytest.param("BaseEvent", "payload_json", {1: _Porteur()}, id="x2-dict"),
])
def test_x2_le_refus_nomme_le_type_recu_jamais_la_valeur(nom, champ, valeur):
    """X2 (exec-critic) — « le type reçu, jamais la valeur » (`_exiger`) : sur les 87
    cas du balayage et les deux conteneurs, le repr de la valeur n'atteint pas le
    message. Mutant `recu = repr(valeur)` : rouge."""
    with pytest.raises(TypeError, match=re.escape(f"{nom}.{champ}:")) as exc:
        _construire(nom, **{champ: valeur})
    assert "fuite-X2" not in str(exc.value)


@pytest.mark.parametrize("nom,champ,valeur", [
    pytest.param("BaseEvent", "attempt", True, id="attempt=True"),
    pytest.param("SpecChunkSlice", "version", True, id="version=True"),
    pytest.param("ScanOutputPayload", "vulnerabilities_count", True,
                 id="vulnerabilities_count=True"),
    pytest.param("DevContextSlice", "target_files", ["a", 1], id="target_files=[a,1]"),
    pytest.param("DevContextSlice", "spec_chunk", {"req_id": "R"}, id="spec_chunk=dict"),
    pytest.param("CriticContextSlice", "spec_chunk", {"req_id": "R"}, id="critic.spec_chunk=dict"),
    pytest.param("BaseEvent", "attempt", "1", id="attempt='1'"),
    pytest.param("BaseEvent", "event_type", "TASK_CREATED", id="event_type=chaine_nue"),
    pytest.param("BaseEvent", "payload_json", {1: "a"}, id="payload_json=cle_int"),
    pytest.param("DevContextSlice", "applied_lessons", "abcdef", id="applied_lessons=str"),
])
def test_t3_bornes_refusees_en_typeerror_sans_coercition(nom, champ, valeur):
    with pytest.raises(TypeError, match=re.escape(f"{nom}.{champ}:")):
        _construire(nom, **{champ: valeur})


@pytest.mark.parametrize("nom,champ", [
    ("TestRunEvent", "coverage_percentage"),
    ("TestOutputPayload", "coverage_percentage"),
    ("VisualDiffReportPayload", "match_percentage"),
])
def test_t3_int_admis_pour_float_sans_coercition(nom, champ):
    inst = _construire(nom, **{champ: 100})
    assert getattr(inst, champ) == 100 and type(getattr(inst, champ)) is int


@pytest.mark.parametrize("nom,champ", _OPTIONNELS)
def test_t3_none_admis_sur_chaque_optional(nom, champ):
    assert getattr(_construire(nom, **{champ: None}), champ) is None


def test_t3_attempt_negatif_garde_sa_borne_valueerror():
    with pytest.raises(ValueError, match="attempt"):
        _construire("BaseEvent", attempt=-1)


def test_t3_troncature_applied_lessons_apres_les_types():
    inst = _construire("DevContextSlice", applied_lessons=["a", "b", "c", "d"])
    assert inst.applied_lessons == ["a", "b", "c"]


@pytest.mark.parametrize("nom", sorted(_NOMINAUX))
def test_t4_nominal_se_construit_chaque_champ_value_et_intact(nom):
    kwargs = _NOMINAUX[nom]()
    attendus = {f.name for f in dataclasses.fields(getattr(M, nom))}
    if _tri_valeur(nom):
        attendus -= {"passed"}
    assert set(kwargs) == attendus
    inst = getattr(M, nom)(**kwargs)
    for champ, valeur in kwargs.items():
        assert getattr(inst, champ) == valeur
