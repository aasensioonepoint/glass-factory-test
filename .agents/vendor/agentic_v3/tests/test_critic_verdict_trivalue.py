"""
Tests for the tri-value critic verdict (Phase 1c, T-00000327).

Covers TriValueVerdictMixin as inherited by BOTH CriticVerdictEvent (the immutable
event schema) and CriticOutputPayload (the LLM output that the producer dumps into
payload_json). Each test name carries the bound it exercises (L-00000190), and the
projection traversal runs on a tmp_db FIXTURE so the live store at
`DEFAULT_DB_PATH()` (partition MACHINE hors dépôt depuis T-00000650) is never
written (C5).

Since T-00000655 the models are stdlib dataclasses: reconciliation and the lax
`passed` coercion (table F6) live in `__post_init__`, refusals surface as the exact
stdlib exception (ValueError for a bad value or an incoherent pair, TypeError for a
missing field or a non-dict handed to model_validate), and the F6 table is pinned
below by @pytest.mark.parametrize so it survives independently of any library.
"""

import json
import tempfile
from pathlib import Path

import pytest

from agentic_v3.models.events import CriticVerdictEvent, EventType
from agentic_v3.models.outputs import CriticOutputPayload
from agentic_v3.models.slices import SpecChunkSlice
from agentic_v3.db.event_store import EventStore


# Both models inherit the same mixin; every property is asserted on each.
VERDICT_MODELS = (CriticVerdictEvent, CriticOutputPayload)


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """T-00000650 : l'`EventStore` du banc écrit son export sous une racine de
    TEST et sa base sous `CADRE_STATE_DIR`, auteur FIXÉ (jambe conteneur en root
    sans `git config user.email`). La greffe passe par la PORTE UNIQUE (L-00000500)
    pour rester franchissable — sinon elle éteint tout témoin d'aval du vrai git."""
    from conftest import greffe_email_git_franchissable
    from agentic_v3.db import run_export

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)


@pytest.mark.email_git_reel
def test_la_greffe_email_git_est_franchissable_ici():
    """TÉMOIN (L-00000500) — sous le marqueur `email_git_reel`, la fixture
    `_isolation_export_run` SAUTE sa greffe et le VRAI `_email_git` reste en place.
    On lit l'IDENTITÉ de l'objet (un def -> `__name__ == "_email_git"`, la greffe
    étant un `<lambda>`), preuve indépendante de git et du système de fichiers.
    MUTATION (greffe non franchissable) : l'objet devient le `<lambda>` et rougit."""
    from agentic_v3.db import run_export

    assert run_export._email_git.__name__ == "_email_git", (
        "greffe NON franchie : la porte unique n'a pas sauté sous email_git_reel"
    )


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_trois_valeurs_acceptees_et_passed_derive_go_reserves_true_nogo_false(model):
    # GO and GO_AVEC_RESERVES both advance (passed True); NO_GO does not (passed False).
    for verdict, expected_passed in (
        ("GO", True),
        ("GO_AVEC_RESERVES", True),
        ("NO_GO", False),
    ):
        instance = model(task_id="T-00000327", verdict=verdict)
        assert instance.verdict == verdict
        assert instance.passed is expected_passed


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_retro_compat_payload_historique_sans_verdict_charge_et_derive(model):
    # COMPLETE historical form (C3): a legacy payload with no `verdict`, carrying
    # rejection_reason + findings, loads and derives the verdict from `passed`.
    rejected = model.model_validate(
        {
            "task_id": "T-00000327",
            "passed": False,
            "rejection_reason": "found a regression",
            "findings": ["missing test", "unsafe cast"],
        }
    )
    assert rejected.verdict == "NO_GO"
    assert rejected.passed is False
    assert rejected.rejection_reason == "found a regression"
    assert rejected.findings == ["missing test", "unsafe cast"]

    accepted = model.model_validate({"task_id": "T-00000327", "passed": True})
    assert accepted.verdict == "GO"
    assert accepted.passed is True


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_verdict_hors_literal_refuse_valueerror(model):
    # An out-of-literal verdict is refused with ValueError (membership check against
    # _VALID_VERDICTS in __post_init__), never silently coerced.
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="MAYBE")
    # Case variant: lowercase "go" is a distinct string and must also be refused (C3).
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="go")


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_verdict_hors_literal_avec_passed_coherent_refuse_valueerror(model):
    # P5: an out-of-literal verdict paired with an otherwise-coherent passed must
    # STILL be refused — the membership check runs in the "both present" branch too,
    # not only when passed is absent.
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="MAYBE", passed=True)


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_paire_incoherente_refusee_dans_les_deux_sens(model):
    # Symmetric incoherence (C2): passed != (verdict != "NO_GO") is refused both ways
    # with ValueError.
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="NO_GO", passed=True)
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="GO", passed=False)
    with pytest.raises(ValueError):
        model(task_id="T-00000327", verdict="GO_AVEC_RESERVES", passed=False)
    # Witness: a coherent explicit pair is accepted (guards against a pattern that
    # rejects everything).
    ok = model(task_id="T-00000327", verdict="GO_AVEC_RESERVES", passed=True)
    assert ok.passed is True


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_validator_entrees_hors_nominal_ni_verdict_ni_passed_et_non_dict(model):
    # Neither verdict nor passed present: __post_init__ raises TypeError — same
    # family as a missing required field (F13), never a KeyError.
    with pytest.raises(TypeError):
        model.model_validate({"task_id": "T-00000327", "rejection_reason": "x"})
    # Non-dict input: model_validate refuses any non-dict with TypeError before ever
    # indexing into it.
    with pytest.raises(TypeError):
        model.model_validate(["not", "a", "dict"])
    with pytest.raises(TypeError):
        model.model_validate(42)


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_passed_chaine_false_historique_coerce_par_table_f6(model):
    # A historical string "false" must be coerced through the F6 table, NOT raw
    # bool() (which reads any non-empty string as truthy-True). With raw bool(),
    # {passed:"false"} would derive verdict="GO" and then store passed=False = a
    # GO/False pair loaded in silence — exactly the incoherence the reconciliation
    # exists to refuse.

    # Derivation face: verdict absent, passed="false" -> NO_GO / False (not GO).
    derived = model.model_validate({"task_id": "T-00000331", "passed": "false"})
    assert derived.verdict == "NO_GO"
    assert derived.passed is False

    # C2 witness (second face): the coherent explicit pair {NO_GO, "false"} is
    # accepted and coerces to NO_GO / False — the incoherence check reads the string
    # through the same F6 table, so a true pair is not rejected.
    coherent = model.model_validate(
        {"task_id": "T-00000331", "verdict": "NO_GO", "passed": "false"}
    )
    assert coherent.verdict == "NO_GO"
    assert coherent.passed is False

    # Incoherence face: {verdict:"GO", passed:"false"} is refused (with raw bool()
    # "false" was True, so it slipped past the coherence predicate as GO/True).
    with pytest.raises(ValueError):
        model.model_validate({"task_id": "T-00000331", "verdict": "GO", "passed": "false"})

    # Non-coercible face: "banana" invents NO verdict; __post_init__ refuses the
    # value itself with ValueError.
    with pytest.raises(ValueError):
        model.model_validate({"task_id": "T-00000331", "passed": "banana"})
    # Same when a verdict is also present: coercion fails -> not misreported as
    # incoherent, the value is refused with ValueError.
    with pytest.raises(ValueError):
        model.model_validate({"task_id": "T-00000331", "verdict": "GO", "passed": "banana"})


# --- Table F6 épinglée depuis l'oracle différentiel (T-00000655) --------------
# L'ENSEMBLE COMPLET des 34 valeurs ACCEPTÉES par l'oracle (17 -> True, 17 -> False),
# chacune avec son bool attendu — toutes les casses des 6 formes littérales, int/float
# {0, 1} et les deux bytes. Les valeurs REFUSÉES (dont les formes à espace de tête/fin
# que l'oracle refuse, et des chaînes non vides que raw bool() lirait truthy) lèvent
# ValueError. La table survit à la fermeture de la fenêtre de la bibliothèque de
# validation d'origine, en épinglant l'ensemble mesuré au COMPLET (condensé S-00001709).
_F6_ACCEPTED = [
    # False : toutes casses des 6 formes + int/float 0 + bytes (17)
    ("0", False), ("f", False), ("F", False),
    ("false", False), ("FALSE", False), ("False", False),
    ("n", False), ("N", False),
    ("no", False), ("NO", False), ("No", False),
    ("off", False), ("OFF", False), ("Off", False),
    (0, False), (0.0, False), (b"0", False),
    # True : toutes casses des 6 formes + int/float 1 + bytes (17)
    ("1", True), ("t", True), ("T", True),
    ("true", True), ("TRUE", True), ("True", True),
    ("y", True), ("Y", True),
    ("yes", True), ("YES", True), ("Yes", True),
    ("on", True), ("ON", True), ("On", True),
    (1, True), (1.0, True), (b"true", True),
]
_F6_REFUSED = [
    " true", "true ", "\ttrue", "true\n", "FALSE ", "",
    "banana", "maybe", -1, 2, 0.5, None, [], {},
]


@pytest.mark.parametrize("model", VERDICT_MODELS)
@pytest.mark.parametrize("value,expected", _F6_ACCEPTED)
def test_table_f6_valeurs_acceptees_coercent_vers_le_bool_attendu(model, value, expected):
    inst = model.model_validate({"task_id": "T", "passed": value})
    assert inst.passed is expected
    assert inst.verdict == ("GO" if expected else "NO_GO")


@pytest.mark.parametrize("model", VERDICT_MODELS)
@pytest.mark.parametrize("value", _F6_REFUSED)
def test_table_f6_valeurs_refusees_levent_valueerror(model, value):
    with pytest.raises(ValueError):
        model.model_validate({"task_id": "T", "passed": value})


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_model_dump_json_serialisable_aucune_sentinelle_ne_fuit(model):
    # EventStore.append_event fait json.dumps(payload) : la sentinelle _Absent n'est
    # PAS sérialisable, donc un nominal doit toujours résoudre verdict ET passed en
    # __post_init__ — ce témoin (une ligne) ferme la classe entière.
    json.dumps(model(task_id="T", verdict="GO").model_dump())


def test_seules_les_deux_classes_tri_valeur_portent_model_dump():
    # Rétrécissement DÉCLARÉ (T-00000655) : seules les deux classes tri-valeur gardent
    # model_dump/model_validate sous leurs noms d'origine ; les 17 autres dataclasses
    # exportées (plus l'enum EventType) n'ont ni model_dump ni model_validate. Ce témoin
    # fige l'ensemble CLOS — il rougit si l'API dérive dans un sens (une classe la PERD)
    # comme dans l'autre (une classe la REGAGNE), sans quoi le rétrécissement documenté
    # au __init__ ne serait pas gardé.
    import agentic_v3.models as M

    assert sorted(
        n for n in M.__all__
        if n != "EventType" and hasattr(getattr(M, n), "model_dump")
    ) == ["CriticOutputPayload", "CriticVerdictEvent"]


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_f11_cle_inconnue_toleree_par_model_validate_mais_refusee_par_constructeur(model):
    # F11: model_validate filters unknown keys, so a historical payload carrying an
    # extra field still loads.
    inst = model.model_validate(
        {"task_id": "T", "verdict": "GO", "clef_historique_inconnue": "x"}
    )
    assert inst.verdict == "GO"
    assert inst.passed is True
    # F11-bis (declared narrowing): the constructor no longer swallows extras — a
    # dataclass raises TypeError on an unexpected keyword.
    with pytest.raises(TypeError):
        model(task_id="T", verdict="GO", clef_historique_inconnue="x")


@pytest.mark.parametrize("model", VERDICT_MODELS)
def test_f15_instance_a_model_validate_refusee_typeerror(model):
    # F15 (declared narrowing, A-C7): the previous validation library re-validated a
    # model instance handed to model_validate; the stdlib port refuses any non-dict
    # with TypeError.
    instance = model(task_id="T", verdict="GO")
    with pytest.raises(TypeError):
        model.model_validate(instance)


def test_f12_version_chaine_refusee_sans_coercion():
    # F12 AMENDÉ par T-00000680 (décision pilote S-00002937 Q2) — ce témoin épinglait
    # une PERMISSIVITÉ : la bibliothèque de validation d'origine coerçait version="2"
    # -> int 2, le port dataclass de T-00000655 stockait la chaîne telle quelle. F12
    # reste « aucune coercition » (jamais "2" -> 2), mais la valeur est désormais
    # REFUSÉE par la frontière de type. Producteur non affecté : parse_specs passe
    # des littéraux int (version=1, old_version+1).
    with pytest.raises(TypeError, match="version"):
        SpecChunkSlice(
            req_id="R", version="2", file_path="f", section_title="t", content_markdown="c"
        )


def test_traversee_payload_model_dump_vers_projection_in_test(tmp_db):
    # CriticOutputPayload -> model_dump() -> append_event -> projection status.
    # OBLIGATORY tmp_db fixture (C5): never CriticAgent's default db_path, which
    # points at the LIVE store `DEFAULT_DB_PATH()` (T-00000650: partition MACHINE
    # hors dépôt). The "store never rewritten" promise depends on this test
    # staying off the live store — held by the tmp_db fixture, not the comment.
    store = EventStore(tmp_db)
    payload = CriticOutputPayload(task_id="T-00000327", verdict="GO_AVEC_RESERVES")
    assert payload.passed is True

    dumped = payload.model_dump()
    assert dumped["verdict"] == "GO_AVEC_RESERVES"
    assert dumped["passed"] is True

    event_id = store.append_event(
        task_id="T-00000327",
        agent_role="CriticAgent",
        event_type=EventType.CRITIC_VERDICT,
        payload=dumped,
    )
    assert event_id > 0

    projection = store.get_task_projection("T-00000327")
    # GO_AVEC_RESERVES advances exactly like GO: passed=True -> IN_TEST.
    assert projection["status"] == "IN_TEST"

    events = store.get_task_events("T-00000327")
    persisted = json.loads(events[-1]["payload_json"])
    assert persisted["passed"] is True
    assert persisted["verdict"] == "GO_AVEC_RESERVES"
