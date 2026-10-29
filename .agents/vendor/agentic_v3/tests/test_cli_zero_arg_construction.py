"""Témoin 21 (T-00000650) : les classes du CLI V3 se construisent à ZÉRO argument
— exactement comme `agentic_v3/cli.py` — et leur `db_path` par défaut résout
PARESSEUSEMENT vers `DEFAULT_DB_PATH()` sous la partition MACHINE, sans écrire un
octet sous le dépôt.

AUCUNE variable `ROOT` liée à `__file__` : le fichier voyage avec `agentic_v3/` et
n'a rien à nommer sur la racine réelle, donc `test_adopting_gate` ne le balaye pas.

BORNE ÉCRITE : `LessonsStore` et `BoardBridge` ne sont PAS couverts ici — aucun
site de production ne les construit à zéro argument (précondition 3). Ce témoin
n'exerce PAS `dashboard-summary` (son banc : `test_cli_dashboard_summary.py`,
T-00001066) : « aucun écrivain n'échappe au mécanisme » et « rien d'autre ne casse »
sont deux preuves différentes ; ce banc porte la seconde.
"""

from pathlib import Path

import pytest

from agentic_v3.db import run_export
from agentic_v3.db.event_store import EventStore
from agentic_v3.db.schema import DEFAULT_DB_PATH, create_tables, get_db_connection
from agentic_v3.checkpoints.session_checkpoint import SessionCheckpointManager
from agentic_v3.ingestion.parse_specs import SpecParser


@pytest.fixture
def partition(tmp_path, monkeypatch, request):
    from conftest import greffe_email_git_franchissable

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    # PORTE UNIQUE (L-00000500) : greffe franchissable, jamais un setattr nu.
    greffe_email_git_franchissable(monkeypatch, request, run_export)
    return proj


@pytest.mark.email_git_reel
def test_la_greffe_email_git_est_franchissable_ici(partition: Path):
    """TÉMOIN (L-00000500) — sous le marqueur `email_git_reel`, la fixture
    `partition` SAUTE sa greffe et le VRAI `_email_git` reste en place (def ->
    `__name__ == "_email_git"`, la greffe étant un `<lambda>`). MUTATION (greffe
    non franchissable) : l'objet devient le `<lambda>` et rougit."""
    assert run_export._email_git.__name__ == "_email_git", (
        "greffe NON franchie : la porte unique n'a pas sauté sous email_git_reel"
    )


def test_les_trois_classes_du_cli_se_construisent_a_zero_argument_sous_la_partition_fixture(
    partition: Path,
) -> None:
    attendu = DEFAULT_DB_PATH()
    for construire in (EventStore, SpecParser, SessionCheckpointManager):
        obj = construire()  # ZÉRO argument, exactement comme cli.py
        assert isinstance(obj.db_path, Path), f"{construire.__name__}.db_path n'est pas un Path"
        # MUTATION : un `= DEFAULT_DB_PATH` nu en défaut d'un des __init__ ferait
        # `Path(<objet fonction>)` -> TypeError ici, à la construction.
        assert obj.db_path == attendu, f"{construire.__name__}.db_path != DEFAULT_DB_PATH()"
        assert str(run_export.state_project()) in str(obj.db_path), (
            f"{construire.__name__}.db_path hors de state_project()"
        )
    # Rien sous <fixture>/.agents/state/ : la base vit sous la partition MACHINE.
    etat = partition / ".agents" / "state"
    fuite = [p for p in etat.rglob("*")] if etat.exists() else []
    assert not fuite, f"un fichier est apparu sous .agents/state/ : {fuite}"


def test_get_db_connection_et_create_tables_a_zero_argument_ouvrent_la_meme_base(
    partition: Path,
) -> None:
    create_tables()  # ZÉRO argument -> DEFAULT_DB_PATH()
    conn = get_db_connection()  # ZÉRO argument -> la MÊME base
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(events_ledger)")]
        assert len(cols) == 11, f"la base à zéro argument n'a pas la forme courante : {cols}"
    finally:
        conn.close()
    assert DEFAULT_DB_PATH().is_file(), "la base par défaut n'existe pas sous la partition"
