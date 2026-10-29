"""Poignée de ``_verrou_export`` fermée sur chaque sortie épinglée (T-00001080).

``_verrou_export`` ferme sa poignée sur CHACUNE de ses HUIT sorties épinglées
(patron de ``board_lock_ferme_sa_poignee_sur_toute_sortie``, T-00001063) :
``stat`` (``Path.stat`` du fichier de verrou lève ``EACCES``), ``ecriture``
(``ENOSPC``), ``delai`` (le verrou n'est jamais libre, la borne expire :
``RunExportError``), ``corps`` (le corps lève ``RuntimeError``), ``fermeture``
(``close()`` lève ``EIO`` une fois la poignée réelle fermée), ``liberation``
(``EIO`` sur ``LOCK_UN``), ``interruption`` (le corps lève
``KeyboardInterrupt``, une ``BaseException`` SYNCHRONE : elle distingue le
``finally`` d'un ``except Exception``) et ``interruption_liberation``
(``Interruption``, une ``BaseException``, sur ``LOCK_UN`` : elle distingue le
``finally`` interne d'un ``except OSError``). Le refus ``EIO`` est ARMÉ sur
``stat``, ``ecriture``, ``delai`` et ``liberation`` — jamais sur ``corps``,
``fermeture`` ni ``interruption``, où il masquerait l'erreur sous test, ni sur
``interruption_liberation``, dont la panne tient cette couture : une
libération tentée alors que le verrou n'a jamais été acquis remplace
l'exception attendue (le garde ``if acquis``). ``liberation`` ré-acquiert AVANT
le nettoyage : une poignée fuitée tient encore son ``flock``. POSIX seulement :
ce témoin saute sous ``nt`` (``msvcrt`` non mesuré, T-00000744). NON épinglé :
les interruptions ASYNCHRONES (un signal tombé dans le ``finally`` : non
injecté). Mesuré avec la poignée RETENUE par le banc ; hors banc, une écriture
comme une libération refusée se ferme au comptage de références dès que
l'exception est lâchée, pas au ramasse-miettes (aucun cycle ``last = exc`` ici ;
M1 : 0 ouverte, 0 délai). Chaque banc pose SES ``CADRE_STATE_DIR`` et
``CADRE_PROJECT_ROOT`` jetables AVANT toute résolution (L-00000527) et vide le
cache de racine avant ET après.

R3-bis, la COURSE de version (T-00001082) : ``backfill_historique`` lit
``user_version`` à l'ouverture, puis écrit plus tard. Une connexion TIERCE — un
kit PLUS RÉCENT — pose ``SCHEMA_VERSION + 1`` juste AVANT une instruction nommée
de la connexion du backfill (``POINTS_DE_COURSE``, injection déterministe par la
factory de ``sqlite3.connect``, patron de ``test_re_13``, aucun délai). Avant le
verrou (``selection``, ``verrou``) : la relecture sous ``BEGIN IMMEDIATE`` la voit,
refus ``CAUSE_VERSION``, code 4, rien n'est frappé. Sous le verrou (``update``) :
la pose est refusée, le backfill écrit en v``SCHEMA_VERSION``. Sans ``flock``,
ces témoins ne sautent pas sous ``nt`` (non mesurés sous Windows).
"""
import errno
import functools
import os
import pathlib
import shutil
import sqlite3
import subprocess
import traceback
from unittest import mock

import pytest

from agentic_v3.db import run_export
from agentic_v3.db.refus_store import CAUSE_VERSION, REFUSE, StoreV3Refuse
from agentic_v3.db.schema import SCHEMA_VERSION, SchemaVersionError, create_tables


class Interruption(BaseException):
    """Une non-``Exception`` levée à la couture de LIBÉRATION (T-00001080, A-C1)."""


@pytest.fixture
def bac(tmp_path, monkeypatch):
    racine = tmp_path / "depot"
    racine.mkdir()
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(racine))
    run_export._paths().vider_cache_racine()
    yield racine
    run_export._paths().vider_cache_racine()


@pytest.mark.skipif(os.name == "nt", reason="msvcrt non mesuré, T-00000744")
@pytest.mark.parametrize("sortie", ["stat", "ecriture", "delai", "corps", "fermeture", "liberation", "interruption", "interruption_liberation"])
def test_verrou_export_ferme_sa_poignee_sur_chaque_sortie_epinglee(sortie, bac, monkeypatch):
    import fcntl  # POSIX seulement : le module entier saute sous nt (pytestmark)

    verrou = run_export._fichier_verrou_export()
    ouvertes = []
    real_open, real_stat, real_flock = pathlib.Path.open, pathlib.Path.stat, fcntl.flock

    class Mandataire:  # une SEULE panne injectée, tout le reste atteint la poignée réelle
        def __init__(self, h):
            self._h = h

        def write(self, *a):
            if sortie == "ecriture":
                raise OSError(errno.ENOSPC, "No space left on device")
            return self._h.write(*a)

        def close(self):
            self._h.close()  # la poignée RÉELLE est fermée d'abord : la panne est l'erreur, jamais une fuite
            if sortie == "fermeture":
                raise OSError(errno.EIO, "close failed")

        def __getattr__(self, n):
            return getattr(self._h, n)

    def ouvre(self, *a, **k):
        h = real_open(self, *a, **k)
        if self == verrou:
            ouvertes.append(h)
            return Mandataire(h) if sortie in ("ecriture", "fermeture") else h
        return h

    def stat(self, *a, **k):
        if self == verrou and ouvertes:
            raise OSError(errno.EACCES, "stat refused")
        return real_stat(self, *a, **k)

    def flock(fd, op):
        if op & fcntl.LOCK_UN:
            if sortie == "interruption_liberation":
                raise Interruption("unlock interrupted")
            raise OSError(errno.EIO, "unlock refused")
        if sortie == "delai" and op & fcntl.LOCK_NB:
            raise BlockingIOError(errno.EAGAIN, "held elsewhere")
        return real_flock(fd, op)

    exc, code = {
        "stat": (OSError, errno.EACCES),
        "ecriture": (OSError, errno.ENOSPC),
        "delai": (run_export.RunExportError, None),
        "corps": (RuntimeError, None),
        "fermeture": (OSError, errno.EIO),
        "liberation": (OSError, errno.EIO),
        "interruption": (KeyboardInterrupt, None),
        "interruption_liberation": (Interruption, None),
    }[sortie]
    try:
        # monkeypatch.context() et JAMAIS monkeypatch.undo() : undo défairait aussi
        # CADRE_STATE_DIR / CADRE_PROJECT_ROOT posés par `bac`, et la ré-acquisition
        # ci-dessous viserait un AUTRE verrou que celui sous test (partition de session de conftest.py).
        with monkeypatch.context() as mp:
            mp.setattr(pathlib.Path, "open", ouvre)
            if sortie == "stat":
                mp.setattr(pathlib.Path, "stat", stat)
            if sortie not in ("corps", "fermeture", "interruption"):  # armé là où le verrou n'est jamais acquis, et comme sortie elle-même
                mp.setattr(fcntl, "flock", flock)
            if sortie == "delai":
                mp.setattr(run_export, "_VERROU_TIMEOUT_S", 0.05)
            with pytest.raises(exc) as ei:
                with run_export._verrou_export():
                    if sortie == "corps":
                        raise RuntimeError("boom")
                    if sortie == "interruption":
                        raise KeyboardInterrupt
        fermees = [h.closed for h in ouvertes]
        if sortie == "liberation":
            with monkeypatch.context() as mp2:
                mp2.setattr(run_export, "_VERROU_TIMEOUT_S", 0.5)
                with run_export._verrou_export():  # AVANT le nettoyage : une poignée fuitée tient encore son flock
                    pass
    finally:
        for h in ouvertes:
            h.close()
    assert code is None or ei.value.errno == code
    assert ouvertes and all(fermees), f"handle(s) left open on exit {sortie!r}: {fermees}"
    assert os.path.abspath(str(verrou)) not in getattr(run_export._verrous_tenus, "chemins", set()), (
        f"stale re-entrancy mark after exit {sortie!r}"
    )


# -- R3-bis (T-00001082) : la course de version entre l'ouverture et l'écriture ---------

#: Courriel du banc : l'auteur de la bibliothèque, et `_email_git` de la CLI.
EMAIL = "banc-r3bis@exemple.invalid"

#: La tierce pose `SCHEMA_VERSION + 1` juste AVANT la première instruction de la
#: connexion du backfill qui CONTIENT ce texte. `selection` : la première lecture (c),
#: après la lecture de version de l'ouverture — le défaut lui-même. `verrou` : le
#: `BEGIN IMMEDIATE` du seuil de (d) — seul point qui tue une relecture faite AVANT le
#: verrou. `update` : le premier UPDATE, verrou tenu — la pose y est REFUSÉE.
POINTS_DE_COURSE = {
    "selection": "FROM events_ledger WHERE ulid IS NULL ORDER BY",
    "verrou": "BEGIN IMMEDIATE",
    "update": "UPDATE events_ledger",
}


def _semer(store: pathlib.Path) -> pathlib.Path:
    """Store du kit (`create_tables` : WAL, v`SCHEMA_VERSION`), UNE ligne `ulid IS NULL`."""
    create_tables(store)
    conn = sqlite3.connect(str(store))
    try:
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
            ("T-R", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "ope0", "TASK_CREATED", 0),
        )
        conn.commit()
    finally:
        conn.close()
    return store


def _etat(store: pathlib.Path) -> tuple:
    """`(user_version, lignes ulid IS NULL)`, par un lecteur NU."""
    conn = sqlite3.connect(str(store), timeout=0.05)
    try:
        return (conn.execute("PRAGMA user_version").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL").fetchone()[0])
    finally:
        conn.close()


def _annexes(store: pathlib.Path) -> set:
    return {s for s in ("-wal", "-shm", "-journal") if store.with_name(store.name + s).exists()}


def _monter(dossier: pathlib.Path, mode: str) -> tuple:
    """`(base, copie 1a ou None, argv de _cli)`. En `appliquer`, la copie est frappée
    AVANT toute course, sans injection (amorce)."""
    dossier.mkdir()
    base = _semer(dossier / "base.db")
    if mode == "frapper":
        return base, None, ["backfill", "--base", str(base)]
    copie = dossier / "copie.db"
    shutil.copyfile(base, copie)
    run_export.backfill_historique(base=copie, auteur=run_export.empreinte_auteur(EMAIL))
    return base, copie, ["backfill", "--base", str(base), "--appliquer-depuis", str(copie)]


def _course(point: str, base: pathlib.Path) -> tuple:
    """`(factory, poses)` : factory de `sqlite3.connect` dont la connexion, avant la
    PREMIÈRE instruction qui contient `POINTS_DE_COURSE[point]`, fait poser
    `SCHEMA_VERSION + 1` sur `base` par une TIERCE (la vraie `connect`, attente 0).
    `poses` reçoit `True` (posée) ou le message du refus de la tierce."""
    vraie = sqlite3.connect
    poses: list = []

    class _Connexion(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if not poses and POINTS_DE_COURSE[point] in sql:
                tierce = vraie(str(base), timeout=0, isolation_level=None)
                try:
                    tierce.execute("PRAGMA user_version = " + str(int(SCHEMA_VERSION + 1)))
                    poses.append(True)
                except sqlite3.OperationalError as exc:
                    poses.append(str(exc))
                finally:
                    tierce.close()
            return super().execute(sql, *args, **kwargs)

    return functools.partial(vraie, factory=_Connexion), poses


@pytest.mark.parametrize("mode", ("frapper", "appliquer"))
@pytest.mark.parametrize("point", ("selection", "verrou"))
def test_r3_bis_une_version_posee_avant_le_verrou_est_refusee_rien_n_est_frappe(
        point, mode, bac, tmp_path, monkeypatch, capsys):
    """R3-bis (T-00001082) : un kit PLUS RÉCENT qui pose `SCHEMA_VERSION + 1` APRÈS la
    lecture de version de l'ouverture et AVANT le verrou d'écriture est VU — la version
    est RELUE sous `BEGIN IMMEDIATE` avant le premier UPDATE. Bibliothèque :
    `StoreV3Refuse` (REFUSÉ, `CAUSE_VERSION`, la BASE), levé par la relecture, jamais par
    l'ouverture. CLI : code 4, UNE ligne stderr, stdout vide. Les deux : aucune ligne
    frappée, la version posée intacte, aucune annexe. Rouge à la base 0eee8d30 :
    `selection` frappe le store passé au schéma futur ; `verrou` n'y trouve aucun
    `BEGIN IMMEDIATE` (précondition)."""
    for appel in ("bibliotheque", "cli"):
        base, copie, argv = _monter(tmp_path / appel, mode)
        factory, poses = _course(point, base)
        rendu = code = out = err = None
        with monkeypatch.context() as mp:
            mp.setattr(run_export.sqlite3, "connect", factory)
            if appel == "bibliotheque":
                try:
                    run_export.backfill_historique(
                        base=base, appliquer_depuis=copie, auteur=run_export.empreinte_auteur(EMAIL))
                except StoreV3Refuse as exc:
                    rendu = exc
            else:
                capsys.readouterr()
                with mock.patch.object(run_export, "_email_git", return_value=EMAIL):
                    code = run_export._cli(argv)
                out, err = capsys.readouterr()
        assert poses == [True], f"précondition ({appel}) : aucune pose au point {point!r} : {poses}"
        assert _etat(base) == (SCHEMA_VERSION + 1, 1), (
            f"({appel}) une ligne frappée sur un store passé au schéma futur : {_etat(base)}")
        assert _annexes(base) == set(), f"({appel}) annexe laissée : {_annexes(base)}"
        if appel == "bibliotheque":
            assert isinstance(rendu, StoreV3Refuse), "aucun refus"
            assert (rendu.verdict, rendu.cause, rendu.chemin) == (REFUSE, CAUSE_VERSION, base)
            assert isinstance(rendu.origine, SchemaVersionError) and rendu.origine is rendu.__cause__
            pile = [trame.name for trame in traceback.extract_tb(rendu.origine.__traceback__)]
            assert "relire_version_sous_verrou" in pile, f"refus hors de la relecture sous verrou : {pile}"
        else:
            assert (code, out) == (4, ""), f"code {code!r}, stdout {out!r}, stderr {err!r}"
            lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
            assert len(lignes) == 1 and "Traceback" not in err, err
            assert lignes[0].startswith(
                f"run_export.py backfill: store V3 {REFUSE} ({CAUSE_VERSION}) — {base} — SchemaVersionError: "
            ), lignes[0]


@pytest.mark.parametrize("mode", ("frapper", "appliquer"))
def test_r3_bis_sous_le_verrou_aucune_version_ne_se_pose_le_backfill_ecrit(mode, bac, tmp_path, monkeypatch):
    """R3-bis (T-00001082), l'autre face : du `BEGIN IMMEDIATE` au commit, le verrou
    d'écriture est TENU — la pose de la tierce, tentée au premier UPDATE, est refusée
    (`database is locked`) et le backfill frappe en v`SCHEMA_VERSION`. Rouge à la base
    0eee8d30 (la pose passe, l'UPDATE frappe un store futur) comme sous une relecture
    faite sans verrou d'écriture."""
    base, copie, _argv = _monter(tmp_path / "update", mode)
    factory, poses = _course("update", base)
    with monkeypatch.context() as mp:
        mp.setattr(run_export.sqlite3, "connect", factory)
        rendu = run_export.backfill_historique(
            base=base, appliquer_depuis=copie, auteur=run_export.empreinte_auteur(EMAIL))
    assert len(poses) == 1 and poses[0] is not True and "locked" in poses[0], (
        f"la pose a passé sous le verrou d'écriture : {poses}")
    assert (rendu["frappees"], rendu["nul_apres"]) == (1, 0), rendu
    assert _etat(base) == (SCHEMA_VERSION, 0)
