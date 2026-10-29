"""Store V3 de forme ANTÉRIEURE (v0, sans colonne ``ulid``) sous ``run_export backfill`` (T-00001097).

Avant : la première lecture levait ``OperationalError: no such column: ulid``
(code 1, que ``classer_refus`` ne classe pas) — rc 1 avec traceback, hors des
refus 2-6, sans nommer le remède. Désormais ``_ouvrir_base_sqlite`` lève
``RunExportError`` APRÈS le refus de version (``run_export_ecriture``) : rc 6 au
bord de ``_cli``, UNE ligne STDERR ``refus de la bibliothèque : …`` qui nomme
``create_tables()``, aucune ligne frappée, octets du store inchangés, ``runs/``
jamais né. Trois lecteurs, une seule ouverture : la base de ``backfill``, la copie
1a de ``--appliquer-depuis``, la base de ``--re-exporter``. Trois formes du CLI :
paquet (en processus), chemin et ``-m`` (sous-processus) — seules les deux
dernières voient la ``RunExportError`` de ``__main__``, que le module frère ne
peut donc pas importer. Chaque banc pose SES ``CADRE_STATE_DIR`` et
``CADRE_PROJECT_ROOT`` jetables AVANT toute résolution et vide le cache de racine
avant ET après ; l'auteur vient du VRAI ``git config user.email`` d'un dépôt
jetable, variables ``GIT_*`` retirées (patron ``_re_env``), sans greffe.
"""
import functools
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_v3.db import run_export
from agentic_v3.db.schema import create_tables

_EMAIL = "v0@banc.test"
_LIGNE = ("T-V0", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "ope0", "TASK_CREATED", 0)
_INSERER = ("INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)")


def _semer(store: Path, *, v0: bool) -> Path:
    """Une ligne ``ulid IS NULL`` ; ``v0`` : ``events_ledger`` à neuf colonnes
    (ni ``ulid`` ni ``predecesseur_ulid``), ``user_version`` 0 — sinon le store
    du kit (``create_tables``)."""
    if not v0:
        create_tables(store)
    conn = sqlite3.connect(str(store))
    try:
        if v0:
            conn.execute(
                "CREATE TABLE events_ledger (event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_id TEXT, agent_role TEXT, event_type TEXT, payload_json TEXT, "
                "created_at TIMESTAMP, operation_id TEXT, event_kind TEXT, attempt INTEGER)")
        conn.execute(_INSERER, _LIGNE)
        conn.commit()
        colonnes = [r[1] for r in conn.execute("PRAGMA table_info(events_ledger)")]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    assert ("ulid" in colonnes) is not v0 and (version == 0) is v0, (colonnes, version)  # précondition
    return store


def _empreinte(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _depot_jetable(tmp_path: Path, env: dict) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git absent du PATH : backfill n'a pas d'auteur")
    racine = tmp_path / "depot"
    racine.mkdir()
    subprocess.run(["git", "init", "-q", str(racine)], check=True, env=env)
    subprocess.run(["git", "-C", str(racine), "config", "user.email", _EMAIL], check=True, env=env)
    return racine


@pytest.fixture
def projet(tmp_path, monkeypatch):
    for cle in [c for c in os.environ if c.startswith("GIT_")]:
        monkeypatch.delenv(cle)
    racine = _depot_jetable(tmp_path, dict(os.environ))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(racine))
    run_export._paths().vider_cache_racine()
    yield racine
    run_export._paths().vider_cache_racine()


def _assert_refus_v0(message: str, v0: Path) -> None:
    assert "create_tables()" in message, message
    assert str(v0) in message and "sans colonne ulid" in message, message


@pytest.mark.parametrize("mode", ("frapper", "appliquer", "re-exporter"))
def test_v0_la_bibliotheque_leve_run_export_error_nommant_create_tables(mode, projet, tmp_path):
    v0 = _semer(tmp_path / "v0.db", v0=True)
    saine = _semer(tmp_path / "saine.db", v0=False)
    avant = (_empreinte(v0), _empreinte(saine))
    with pytest.raises(run_export.RunExportError) as ei:
        if mode == "frapper":
            run_export.backfill_historique(base=v0)
        elif mode == "appliquer":
            run_export.backfill_historique(base=saine, appliquer_depuis=v0)
        else:
            run_export.re_exporter_frappees(base=v0)
    assert not isinstance(ei.value, run_export.PanneInfrastructure)
    _assert_refus_v0(str(ei.value), v0)
    assert (_empreinte(v0), _empreinte(saine)) == avant, "un store a bougé sous le refus"
    assert not (projet / "runs").exists(), "runs/ né sous le refus"


@pytest.mark.parametrize("version", (0, 1))
def test_v0_v1_connexion_fermee_sur_le_refus(version, projet, tmp_path, monkeypatch):
    """Patron de ``test_re_11`` : UNE connexion ouverte, UNE fermée avant que le refus
    de forme ne sorte ; un store v1 (``user_version`` 1, neuf colonnes) est refusé
    comme le v0, sa version lue dans le message."""
    v0 = _semer(tmp_path / "v0.db", v0=True)
    if version:
        conn = sqlite3.connect(str(v0))
        conn.execute("PRAGMA user_version = 1")
        conn.close()
    ouvertes, fermees = [], []

    class _ConnTracee(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            ouvertes.append(self)

        def close(self):
            fermees.append(self)
            super().close()

    vraie = sqlite3.connect
    with monkeypatch.context() as patch:
        patch.setattr(run_export.sqlite3, "connect", functools.partial(vraie, factory=_ConnTracee))
        with pytest.raises(run_export.RunExportError) as ei:
            run_export.backfill_historique(base=v0)
    assert (len(ouvertes), len(fermees)) == (1, 1), (len(ouvertes), len(fermees))
    assert f"(user_version={version}," in str(ei.value), str(ei.value)


def test_v0_cli_paquet_rc_6_une_ligne_sans_traceback(projet, tmp_path, capsys):
    v0 = _semer(tmp_path / "v0.db", v0=True)
    capsys.readouterr()
    code = run_export._cli(["backfill", "--base", str(v0)])
    out, err = capsys.readouterr()
    assert (code, out) == (6, ""), f"code {code!r}, stderr {err!r}"
    lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
    assert len(lignes) == 1 and lignes[0].startswith("refus de la bibliothèque : "), err
    _assert_refus_v0(lignes[0], v0)


@pytest.mark.parametrize("forme", ("chemin", "-m"))
def test_v0_cli_hors_processus_rc_6_une_ligne_sans_traceback(forme, tmp_path):
    env = {cle: val for cle, val in os.environ.items() if not cle.startswith("GIT_")}
    env["CADRE_PROJECT_ROOT"] = str(_depot_jetable(tmp_path, env))
    env["CADRE_STATE_DIR"] = str(tmp_path / "state-hp")
    v0 = _semer(tmp_path / "v0.db", v0=True)
    avant = _empreinte(v0)
    module = Path(run_export.__file__).resolve()
    if forme == "chemin":
        cmd = [sys.executable, "-B", str(module), "backfill", "--base", str(v0)]
    else:
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(module.parents[2]), env.get("PYTHONPATH")) if p)
        cmd = [sys.executable, "-B", "-m", "agentic_v3.db.run_export", "backfill", "--base", str(v0)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=120)
    assert (r.returncode, r.stdout) == (6, ""), f"rc={r.returncode}\n{r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    tolerees = [ligne for ligne in r.stderr.splitlines() if "RuntimeWarning" in ligne]
    assert len(tolerees) <= (1 if forme == "-m" else 0), r.stderr
    lignes = [ligne for ligne in r.stderr.splitlines() if ligne.strip() and ligne not in tolerees]
    assert len(lignes) == 1 and lignes[0].startswith("refus de la bibliothèque : "), r.stderr
    _assert_refus_v0(lignes[0], v0)
    assert _empreinte(v0) == avant
    assert not (Path(env["CADRE_PROJECT_ROOT"]) / "runs").exists(), "runs/ né sous le refus"
