"""Témoins T-00001005 (BK-408) et T-00001054 : les quatre ouvreurs V3 hors `tasks.py`,
puis le 5e (`run_export._cli backfill`, famille (e)), refusent un
store illisible par UN refus nommé (`StoreV3Refuse`, une ligne ; code 4 pour un
REFUS, 5 pour une PANNE d'infrastructure — décision pilote S-00003348), jamais
par un traceback qui gèle leur appelant.

Familles :
  (a) les TROIS constructeurs (`SessionCheckpointManager`, `LessonsStore`,
      `SpecParser`) sur de VRAIS stores : type, verdict, cause, chemin, chaînage,
      précondition par `isinstance` sur la classe RÉELLE prise à la couture,
      octets et annexes inchangés ;
  (b) les QUATRE verbes de `cli.main()` : code 4 (REFUSÉ) ou 5 (EN PANNE),
      stdout vide, UNE ligne stderr portant verdict et cause ; plus un cas
      « store sain » par verbe qui ne refuse pas ;
  (c) la sélection par type réel : ce qui ne convertit PAS (hors ensemble :
      `FileNotFoundError`, `IsADirectoryError`, `OSError` 28, codes 6, 10, 14, 19,
      et l'étendu 1032 — base supprimée sous la connexion, aussi par le VRAI canal),
      les cinq causes du pont (T-00001078 : libellés à la lettre, portée
      `erreurs_os`, câblage par l'AST, doctrine écrite : c_viii, c_ix, c_x), et
      l'affichage aplati (un chemin à saut de ligne tient UNE ligne) ;
  (d) le VERBE `sync-spec` sous le refus nommé (T-00001059) — dix fonctions,
      préfixe `test_d_` (la lettre (e) est réservée à T-00001054) : verrou WAL
      RÉEL au premier write → code 4 en une ligne, puis relance qui écrit (d1) ;
      lecteurs non refusés sous le même porteur, contrôle de MONTAGE (d1-contrôle) ;
      frontière bibliothèque brute (d2) ; panne d'export après le commit → 5
      (d3) ; verrou synthétique d'`append_event`, compensé puis 4 (d3') ; hors
      ensemble, le même objet remonte (d4) ; ligne du code 3 aplatie (d5) ; sous
      `erreurs_os=False` (T-00001078) : un spec illisible remonte brut (d6, d6 bis),
      un store en lecture seule sort en 4 au premier write (d7).
  (e) le 5e ouvreur `run_export._cli backfill` (T-00001054), préfixe `test_re_` :
      refus à l'ouverture ou à la première lecture -> 4 en une ligne nommant la
      base RÉELLEMENT refusée (re_1, re_2 ; vrai canal re_5) ; panne : rc 1
      brute, cause chaînée, décision pilote S-00003489 (re_3, EN PROCESSUS
      seulement) ; lien : rc 6, inchangé (témoigné dans `test_run_export.py`) ;
      bornes R4, R9 et après le commit témoignées (re_4) ;
      R3 REFUSÉ (T-00001075 : re_1, re_5, re_9), store antérieur accepté
      (re_10), connexion fermée sur toute levée de l'ouverture (re_11) ; R1
      REFUSÉ à la phase d'écriture, base inchangée (T-00001074 : re_12), sans
      écriture partielle (re_13), de même le code 8 à l'écriture (T-00001078 :
      re_12) et l'en-tête corrompu (code 11 : re_1, re_5) ; refus et bornes dits
      en docstring (re_7).

COUVERTURE PAR TYPE, portée « darwin non-root » (mesurée le 2026-10-01) :
  par le VRAI canal — non SQLite (26), `SchemaVersionError`, `EmplacementRefuse`
  (lien), `OuvertureImpossible` (`chmod 0`), verrou (5, store en journal DELETE :
  en WAL, un verrou EXCLUSIVE ne bloque pas la lecture de version ; et, famille
  d, en WAL sous `BEGIN IMMEDIATE`, au premier write du verbe ; famille e, à
  la phase d'écriture de `backfill` : en WAL sous un écrivain tenu, au
  BEGIN IMMEDIATE, en journal DELETE sous un lecteur tenu, au commit), hors projet
  (`CadrePathError`), panne (couture masquée), en-tête corrompu (11), dossier
  `chmod 500` sans store (`PermissionError`) et avec store (1544), fichier à la
  place de `run/` (`FileExistsError`) et de la partition (`NotADirectoryError`),
  store `chmod 444` à l'écriture (8) — T-00001078 ; négatifs (hors ensemble) :
  `FileNotFoundError`, `IsADirectoryError`, `OSError` 28, codes 6, 10, 14, 19 ;
  base supprimée sous une connexion ouverte en journal DELETE (1032, DBMOVED : brute,
  jamais « lecture seule » ; sous WAL l'écriture qui suit ne lève pas, mesuré) ;
  sous `run_export`, aucune des trois sœurs n'atteint un bloc dans les montages
  mesurés (rc 4 ou 6 sous 3.14, rc 1 brut avant tout bloc sous 3.11 et 3.12 pour
  un parent `chmod 000` ; relevé non clos) et le code 8 à l'OUVERTURE (1544) est
  mesuré à la main, non épinglé ;
  par INJECTION, dit SYNTHÉTIQUE — `HorsRacine` (injoignable par le vrai canal,
  qui rend `EmplacementRefuse`) et `OuvertureImpossible` (actif sous root, où
  `chmod 0` saute) ; codes 517 et `26 | 0x100` synthétiques (famille c).
  Sautés sous `nt` : lien, `chmod 0`, `chmod 500`, `chmod 444`, `chmod 000` ; sous root :
  `chmod 0`, `chmod 500`, `chmod 444`, `chmod 000`. Non mesurés : Linux, Windows (sémantique du verrou WAL comprise),
  un paquet `cadre` pip-installé.

AUCUNE variable `ROOT` liée à `__file__` : ce fichier voyage avec `agentic_v3/`.
"""

import ast
import contextlib
import functools
import gc
import hashlib
import inspect
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, ContextManager, List, Optional, Set, Tuple
from unittest import mock

import pytest

from agentic_v3 import cli
from agentic_v3.checkpoints import session_checkpoint
from agentic_v3.checkpoints.session_checkpoint import SessionCheckpointManager
from agentic_v3.db import event_store, lessons_store, refus_store, run_export, schema
from agentic_v3.db.event_store import ReconstructionAvorteeError
from agentic_v3.db.lessons_store import LessonsStore
from agentic_v3.db.refus_store import (
    CAUSE_CORROMPU,
    CAUSE_EMPLACEMENT,
    CAUSE_HORS_RACINE,
    CAUSE_LECTURE_SEULE,
    CAUSE_NON_INSCRIPTIBLE,
    CAUSE_NON_SQLITE,
    CAUSE_OCCUPE,
    CAUSE_OUVERTURE,
    CAUSE_PANNE,
    CAUSE_RACINE,
    CAUSE_VERROU,
    CAUSE_VERSION,
    CHEMIN_NON_RESOLU,
    EN_PANNE,
    REFUSE,
    StoreV3Refuse,
    classer_refus,
    refus_nomme,
)
from agentic_v3.db.schema import DEFAULT_DB_PATH, SCHEMA_VERSION, create_tables
from agentic_v3.ingestion.parse_specs import SpecParser

#: Annexes qu'SQLite ouvre à côté d'un store : aucune ne doit naître d'un refus.
ANNEXES = ("-wal", "-shm", "-journal")

CONSTRUCTEURS = {
    "SessionCheckpointManager": SessionCheckpointManager,
    "LessonsStore": LessonsStore,
    "SpecParser": SpecParser,
}

#: Chaque module consommateur LIE `create_tables` à l'import : une injection doit
#: viser CES noms, jamais `schema.create_tables` (qu'aucun ne relit).
SITES_CREATE_TABLES = (session_checkpoint, lessons_store, event_store)

VERBES = ("status", "resume", "sync-spec", "dashboard-summary")


# -- montage ---------------------------------------------------------------------


@pytest.fixture
def partition(tmp_path, monkeypatch, request):
    """Patron de SYM-09255 : racine et partition d'état jetables, greffe
    `_email_git` par la porte unique. Rend le chemin du store par défaut."""
    from conftest import greffe_email_git_franchissable

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)
    store = DEFAULT_DB_PATH()
    store.parent.mkdir(parents=True, exist_ok=True)
    return store


def _couture() -> Tuple[object, object]:
    """`(cadre.ledger.store, cadre.workspace)` PAR LA COUTURE, jamais par
    `import cadre.ledger.store` : c'est la classe que lève `create_tables`."""
    return run_export._couture_ledger_store()


def _classe_cadre_path_error() -> type:
    return run_export._cadre("paths").CadrePathError


def _classes_reelles() -> dict:
    store_mod, workspace_mod = _couture()
    return {
        "CadrePathError": _classe_cadre_path_error(),
        "SchemaVersionError": schema.SchemaVersionError,
        "EmplacementRefuse": store_mod.EmplacementRefuse,
        "OuvertureImpossible": store_mod.OuvertureImpossible,
        "HorsRacine": workspace_mod.HorsRacine,
        "PanneInfrastructure": run_export.PanneInfrastructure,
    }


def _sauter_sans_droits_posix(quoi: str) -> None:
    """Skips NOMMÉS, dans cet ordre : `nt` d'abord, puis root."""
    if os.name == "nt":
        pytest.skip(f"{quoi} : droits POSIX sans objet sous Windows (nt)")
    if os.geteuid() == 0:
        pytest.skip(f"{quoi} : root ignore les droits du fichier (conteneur verify.sh --linux)")


def _code_primaire(exc: BaseException) -> Optional[int]:
    code = getattr(exc, "sqlite_errorcode", None)
    return code & 0xFF if isinstance(code, int) else None


def _empreinte(chemin: Path) -> str:
    """sha256 des octets ; un fichier sans droit de lecture est rendu lisible le
    temps de la lecture, puis son mode est RESTAURÉ."""
    mode = stat.S_IMODE(os.stat(chemin).st_mode)
    if mode & stat.S_IRUSR:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    os.chmod(chemin, mode | stat.S_IRUSR)
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    finally:
        os.chmod(chemin, mode)


def _annexes(*chemins: Path) -> Set[Path]:
    trouvees = set()
    for chemin in chemins:
        for suffixe in ANNEXES:
            annexe = chemin.with_name(chemin.name + suffixe)
            if annexe.exists() or annexe.is_symlink():
                trouvees.add(annexe)
    return trouvees


@dataclass
class Montage:
    """Un store préparé : la PRÉCONDITION sur l'origine (classe RÉELLE), la cause
    attendue, le fichier dont octets et mode ne doivent pas bouger."""

    origine: Callable[[BaseException], bool]
    cause: str
    temoin: Path
    verdict: str = REFUSE
    ctx: Callable[[], ContextManager] = contextlib.nullcontext
    synthetique: bool = False


def _etat(m: Montage, store: Path) -> tuple:
    return (
        _empreinte(m.temoin),
        stat.S_IMODE(os.lstat(m.temoin).st_mode),
        store.is_symlink(),
        store.exists(),
        _annexes(store, m.temoin),
    )


def _store_sain(store: Path) -> None:
    create_tables(store)


def _monter_non_sqlite(store: Path, tmp_path: Path, request) -> Montage:
    store.write_bytes(b"pas une base SQLite\n" * 64)
    return Montage(
        origine=lambda e: isinstance(e, sqlite3.DatabaseError) and _code_primaire(e) == 26,
        cause=CAUSE_NON_SQLITE,
        temoin=store,
    )


def _monter_version_future(store: Path, tmp_path: Path, request) -> Montage:
    _store_sain(store)
    conn = sqlite3.connect(str(store))
    try:
        # Concaténation d'un entier, jamais une f-string dans `execute` (réserve 8).
        conn.execute("PRAGMA user_version = " + str(SCHEMA_VERSION + 1))
        conn.commit()
    finally:
        conn.close()
    return Montage(
        origine=lambda e: isinstance(e, schema.SchemaVersionError),
        cause=CAUSE_VERSION,
        temoin=store,
    )


def _monter_lien(store: Path, tmp_path: Path, request) -> Montage:
    if os.name == "nt":
        pytest.skip("lien symbolique : sans objet sous Windows (nt)")
    cible = tmp_path / "cible.db"
    conn = sqlite3.connect(str(cible))
    try:
        conn.execute("CREATE TABLE t(x)")
        conn.commit()
    finally:
        conn.close()
    os.symlink(cible, store)
    refus = _couture()[0].EmplacementRefuse
    return Montage(origine=lambda e: isinstance(e, refus), cause=CAUSE_EMPLACEMENT, temoin=cible)


def _monter_droits(store: Path, tmp_path: Path, request) -> Montage:
    _sauter_sans_droits_posix("chmod 0")
    _store_sain(store)
    os.chmod(store, 0)
    request.addfinalizer(lambda: os.chmod(store, 0o600))
    refus = _couture()[0].OuvertureImpossible
    return Montage(origine=lambda e: isinstance(e, refus), cause=CAUSE_OUVERTURE, temoin=store)


def _monter_verrou(store: Path, tmp_path: Path, request) -> Montage:
    """Verrou RÉEL (M3) : store passé en journal DELETE (en WAL, la lecture de
    version passe sous un verrou EXCLUSIVE, mesuré), verrou tenu par un porteur,
    attente de la sonde ramenée à 0,05 s."""
    _store_sain(store)
    porteur = sqlite3.connect(str(store), timeout=0.05, isolation_level=None)
    porteur.execute("PRAGMA journal_mode = DELETE")
    porteur.execute("BEGIN EXCLUSIVE")

    def liberer() -> None:
        porteur.execute("ROLLBACK")
        porteur.close()

    request.addfinalizer(liberer)
    sonde_courte = lambda uri: sqlite3.connect(uri, uri=True, timeout=0.05)  # noqa: E731
    return Montage(
        origine=lambda e: isinstance(e, sqlite3.OperationalError) and _code_primaire(e) == 5,
        cause=CAUSE_VERROU,
        temoin=store,
        ctx=lambda: mock.patch.object(schema, "_connexion_nue", sonde_courte),
    )


@contextlib.contextmanager
def _couture_ledger_store_absente(tmp_path: Path):
    """Patron `_couture_ledger_store_absente` de test_run_export.py : paquet
    masqué, repli par chemin vers un dossier ABSENT, mémo sans ces deux entrées ;
    `cadre.paths` reste mémoïsé (mémoïsé AVANT le masque). Tout est restauré."""
    run_export._cadre("paths")
    with contextlib.ExitStack() as pile:
        pile.enter_context(mock.patch.dict(sys.modules, {
            "cadre": None, "cadre.ledger": None, "cadre.ledger.store": None,
            "cadre.workspace": None}))
        pile.enter_context(mock.patch.dict(run_export._MODULES_CADRE))
        run_export._MODULES_CADRE.pop("ledger.store", None)
        run_export._MODULES_CADRE.pop("workspace", None)
        pile.enter_context(mock.patch.object(run_export, "_SRC_CADRE", tmp_path / "cadre-absent-banc"))
        yield


def _monter_panne(store: Path, tmp_path: Path, request) -> Montage:
    _store_sain(store)
    run_export._cadre("paths")  # mémoïsé AVANT le masque (M12)
    return Montage(
        origine=lambda e: isinstance(e, run_export.PanneInfrastructure),
        cause=CAUSE_PANNE,
        temoin=store,
        verdict=EN_PANNE,
        ctx=lambda: _couture_ledger_store_absente(tmp_path),
    )


@contextlib.contextmanager
def _injecter(exc: BaseException):
    """`create_tables` levant `exc` AU SITE D'IMPORT de chaque consommateur."""
    with contextlib.ExitStack() as pile:
        for site in SITES_CREATE_TABLES:
            pile.enter_context(mock.patch.object(site, "create_tables", side_effect=exc))
        yield


def _monter_hors_racine(store: Path, tmp_path: Path, request) -> Montage:
    """SYNTHÉTIQUE : le canal réel rend `EmplacementRefuse` (mesuré par T-00001004)."""
    _store_sain(store)
    classe = _couture()[1].HorsRacine
    return Montage(
        origine=lambda e: isinstance(e, classe),
        cause=CAUSE_HORS_RACINE,
        temoin=store,
        ctx=lambda: _injecter(classe("chemin hors racine (injection T-00001005)")),
        synthetique=True,
    )


def _monter_ouverture_injectee(store: Path, tmp_path: Path, request) -> Montage:
    """SYNTHÉTIQUE, actif SOUS ROOT (réserve 5) : `chmod 0` y saute."""
    _store_sain(store)
    classe = _couture()[0].OuvertureImpossible
    return Montage(
        origine=lambda e: isinstance(e, classe),
        cause=CAUSE_OUVERTURE,
        temoin=store,
        ctx=lambda: _injecter(classe("ouverture impossible (injection T-00001005)")),
        synthetique=True,
    )


def _corrompre_en_tete(store: Path) -> None:
    """Octets 100 à 140 écrasés après un vrai `create_tables` : code 11 (M1)."""
    _store_sain(store)
    octets = bytearray(store.read_bytes())
    octets[100:140] = b"\xff" * 40
    store.write_bytes(bytes(octets))


@contextlib.contextmanager
def _dossier_en_lecture(dossier: Path):
    os.chmod(dossier, 0o500)
    try:
        yield
    finally:
        os.chmod(dossier, 0o700)


def _monter_corrompu(store: Path, tmp_path: Path, request) -> Montage:
    """T-00001078 : en-tête corrompu, code PRIMAIRE 11 (SQLITE_CORRUPT) — REFUSÉ ;
    octets, mode, existence et annexes inchangés, l'instantané étant pris APRÈS la
    libération de l'exception (`test_a`)."""
    _corrompre_en_tete(store)
    return Montage(
        origine=lambda e: isinstance(e, sqlite3.DatabaseError) and _code_primaire(e) == 11,
        cause=CAUSE_CORROMPU,
        temoin=store,
    )


def _monter_dossier_en_lecture_sans_store(store: Path, tmp_path: Path, request) -> Montage:
    """T-00001078 : `run/` en `chmod 500`, store ABSENT -> `PermissionError` à la
    création du store. Témoin : un fichier frère ; le store ne doit pas naître
    (`_etat` porte l'existence du store)."""
    _sauter_sans_droits_posix("dossier chmod 500")
    assert not store.exists(), "précondition : le store existe déjà"
    temoin = store.parent / "temoin-banc"
    temoin.write_bytes(b"temoin\n")
    return Montage(
        origine=lambda e: isinstance(e, PermissionError),
        cause=CAUSE_NON_INSCRIPTIBLE,
        temoin=temoin,
        ctx=lambda: _dossier_en_lecture(store.parent),
    )


def _monter_dossier_en_lecture_avec_store(store: Path, tmp_path: Path, request) -> Montage:
    """T-00001078 : store PRÉSENT, `run/` en `chmod 500` -> READONLY_DIRECTORY
    (1544, primaire 8)."""
    _sauter_sans_droits_posix("dossier chmod 500")
    _store_sain(store)
    return Montage(
        origine=lambda e: isinstance(e, sqlite3.OperationalError) and _code_primaire(e) == 8,
        cause=CAUSE_LECTURE_SEULE,
        temoin=store,
        ctx=lambda: _dossier_en_lecture(store.parent),
    )


def _monter_fichier_a_la_place_de_run(store: Path, tmp_path: Path, request) -> Montage:
    """T-00001078 : un FICHIER occupe `run/` -> `FileExistsError` au `mkdir`."""
    store.parent.rmdir()
    store.parent.write_bytes(b"fichier a la place de run/\n")
    return Montage(origine=lambda e: isinstance(e, FileExistsError), cause=CAUSE_OCCUPE,
                   temoin=store.parent)


def _monter_fichier_a_la_place_de_la_partition(store: Path, tmp_path: Path, request) -> Montage:
    """T-00001078 : un FICHIER occupe la partition du projet -> `NotADirectoryError`."""
    partition_projet = store.parent.parent
    shutil.rmtree(partition_projet)
    partition_projet.write_bytes(b"fichier a la place de la partition\n")
    return Montage(origine=lambda e: isinstance(e, NotADirectoryError), cause=CAUSE_OCCUPE,
                   temoin=partition_projet)


#: T-00001078 — les cinq causes que le pont refuse depuis T-00001056.
MONTAGES_T1078 = {
    "corrompu": _monter_corrompu,
    "dossier_en_lecture_sans_store": _monter_dossier_en_lecture_sans_store,
    "dossier_en_lecture_avec_store": _monter_dossier_en_lecture_avec_store,
    "fichier_a_la_place_de_run": _monter_fichier_a_la_place_de_run,
    "fichier_a_la_place_de_la_partition": _monter_fichier_a_la_place_de_la_partition,
}


MONTAGES_A = {
    "non_sqlite": _monter_non_sqlite,
    "version_future": _monter_version_future,
    "lien": _monter_lien,
    "droits": _monter_droits,
    "verrou": _monter_verrou,
    "panne": _monter_panne,
    "hors_racine_injecte": _monter_hors_racine,
    "ouverture_injectee": _monter_ouverture_injectee,
    **MONTAGES_T1078,
}

MONTAGES_B = {
    "non_sqlite": _monter_non_sqlite,
    "lien": _monter_lien,
    "version_future": _monter_version_future,
    "droits": _monter_droits,
    "panne": _monter_panne,
    **MONTAGES_T1078,
}

#: Code de sortie attendu par verdict, en LITTÉRAUX (S-00003324 : 4 ; S-00003348 : 5).
CODE_PAR_VERDICT = {REFUSE: 4, EN_PANNE: 5}


def _hors_projet(tmp_path: Path, monkeypatch) -> Path:
    """Hors projet (réserve 4) : cwd jetable, quatre variables retirées. La
    PRÉCONDITION est vérifiée AVANT toute construction, et son absence est un
    ÉCHEC, jamais un saut : sans `CADRE_STATE_DIR`, elle seule sépare ce banc du
    store réel de la machine."""
    hors = tmp_path / "hors"
    hors.mkdir()
    for nom in ("CADRE_PROJECT_ROOT", "CADRE_STATE_DIR", "GIT_DIR", "GIT_WORK_TREE"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.chdir(hors)
    try:
        resolu = DEFAULT_DB_PATH()
    except _classe_cadre_path_error():
        return hors
    pytest.fail(
        f"précondition hors projet NON tenue : DEFAULT_DB_PATH() résout {resolu} depuis "
        f"{hors} (un ancêtre porte .git ou .agents/) — rien n'a été construit"
    )


# -- (a) les trois constructeurs -------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(MONTAGES_A))
@pytest.mark.parametrize("ouvreur", sorted(CONSTRUCTEURS))
def test_a_le_constructeur_refuse_par_StoreV3Refuse(ouvreur, scenario, partition, tmp_path, request):
    store = partition
    m = MONTAGES_A[scenario](store, tmp_path, request)
    avant = _etat(m, store)
    with m.ctx():
        with pytest.raises(StoreV3Refuse) as ei:
            CONSTRUCTEURS[ouvreur](db_path=store)
    exc = ei.value
    assert m.origine(exc.origine), (
        f"précondition : le montage {scenario} n'a pas levé la classe attendue, "
        f"mais {type(exc.origine).__module__}.{type(exc.origine).__name__}: {exc.origine}"
    )
    assert exc.origine is exc.__cause__, "origine et __cause__ divergent"
    assert (exc.verdict, exc.cause) == (m.verdict, m.cause)
    assert exc.chemin == store
    # T-00001078 : l'exception TIENT, par sa traceback, la connexion que `get_db_connection`
    # et `create_tables` ne ferment pas sur leur chemin d'erreur ; tant qu'elle vit, `-wal`
    # et `-shm` vivent avec elle (mesuré EN PROCESSUS seulement : 0 annexe après la sortie du
    # processus). On la RELÂCHE avant l'instantané : l'épingle « aucune annexe » reste STRICTE.
    ei = exc = None
    gc.collect()
    assert _etat(m, store) == avant, "octets, mode, lien, existence ou annexes du store ont bougé"


@pytest.mark.parametrize("ouvreur", sorted(CONSTRUCTEURS))
def test_a_hors_projet_le_constructeur_a_zero_chemin_refuse(ouvreur, partition, tmp_path, monkeypatch):
    hors = _hors_projet(tmp_path, monkeypatch)
    with pytest.raises(StoreV3Refuse) as ei:
        CONSTRUCTEURS[ouvreur](db_path=None)
    exc = ei.value
    assert isinstance(exc.origine, _classe_cadre_path_error())
    assert exc.origine is exc.__cause__
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, CAUSE_RACINE, None)
    assert CHEMIN_NON_RESOLU in str(exc)
    assert list(hors.iterdir()) == [], "un fichier est né dans le cwd hors projet"


def test_a_hors_projet_SpecParser_refuse_meme_a_chemin_explicite(partition, tmp_path, monkeypatch):
    """M4 : `EventStore` résout la racine AVANT `create_tables`."""
    _hors_projet(tmp_path, monkeypatch)
    explicite = tmp_path / "explicite" / "v3.db"
    with pytest.raises(StoreV3Refuse) as ei:
        SpecParser(db_path=explicite)
    assert isinstance(ei.value.origine, _classe_cadre_path_error())
    assert (ei.value.cause, ei.value.chemin) == (CAUSE_RACINE, explicite)
    assert not explicite.parent.exists(), "le dossier du store explicite est né"


# -- (b) les quatre verbes du CLI ------------------------------------------------


def _argv(verbe: str, tmp_path: Path) -> List[str]:
    if verbe == "status":
        return ["status", "T-1"]
    if verbe == "sync-spec":
        spec = tmp_path / "spec.md"
        spec.write_text("# Titre\n\nUn corps de spécification.\n", encoding="utf-8")
        return ["sync-spec", str(spec)]
    return [verbe]


def _cli(argv: List[str], capsys) -> Tuple[object, str, str]:
    """`cli.main()` sous `sys.argv` patché : (code de sortie, stdout, stderr) ;
    un retour sans `SystemExit` vaut 0."""
    code: object = 0
    with mock.patch.object(sys, "argv", ["agentic_v3", *argv]):
        try:
            cli.main()
        except SystemExit as fin:
            code = fin.code
    out, err = capsys.readouterr()
    return code, out, err


def _une_ligne_de_refus(err: str, verbe: str) -> str:
    lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
    assert len(lignes) == 1, f"attendu UNE ligne stderr, reçu {len(lignes)} : {err!r}"
    assert "Traceback" not in err
    ligne = lignes[0]
    assert ligne.startswith(f"agentic_v3 {verbe}: store V3 "), ligne
    return ligne


def test_b_les_constantes_de_sortie_valent_4_et_5():
    assert cli.RC_STORE_REFUSE == 4
    assert cli.RC_STORE_PANNE == 5


@pytest.mark.parametrize("scenario", sorted(MONTAGES_B))
@pytest.mark.parametrize("verbe", VERBES)
def test_b_le_verbe_refuse_en_une_ligne_et_code_du_verdict(verbe, scenario, partition, tmp_path, request, capsys):
    store = partition
    m = MONTAGES_B[scenario](store, tmp_path, request)
    argv = _argv(verbe, tmp_path)
    capsys.readouterr()
    with m.ctx():
        code, out, err = _cli(argv, capsys)
    assert code == CODE_PAR_VERDICT[m.verdict], f"{m.verdict} : code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _une_ligne_de_refus(err, verbe)
    assert m.verdict in ligne and m.cause in ligne, ligne
    assert str(store) in ligne, f"le chemin du store manque : {ligne}"


@pytest.mark.parametrize("verbe", VERBES)
def test_b_hors_projet_le_verbe_refuse_sans_chemin(verbe, partition, tmp_path, monkeypatch, capsys):
    argv = _argv(verbe, tmp_path)
    _hors_projet(tmp_path, monkeypatch)
    capsys.readouterr()
    code, out, err = _cli(argv, capsys)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _une_ligne_de_refus(err, verbe)
    assert REFUSE in ligne and CAUSE_RACINE in ligne and CHEMIN_NON_RESOLU in ligne, ligne


@pytest.mark.parametrize("verbe", ("status", "resume", "sync-spec"))
def test_b_store_sain_le_verbe_ne_refuse_pas(verbe, partition, tmp_path, capsys):
    """Réserve 6 : un store SAIN ne sort ni par 4 ni par une ligne `store V3`.
    `dashboard-summary` n'y est pas : son témoin est
    `test_cli_dashboard_summary.py` (T-00001066)."""
    _store_sain(partition)
    argv = _argv(verbe, tmp_path)
    capsys.readouterr()
    code, out, err = _cli(argv, capsys)
    assert code in (0, None), f"code {code!r}, stderr {err!r}"
    assert "store V3" not in err
    assert out.strip(), "le verbe n'a rien écrit sur stdout"


# -- (c) ce qui ne convertit PAS ; sélection par type réel ----------------------


@pytest.mark.parametrize("fabrique", [
    lambda: RuntimeError("erreur sans rapport"),
    lambda: ValueError("ValueError nue (store absent de get_db_connection)"),
    lambda: ReconstructionAvorteeError("reconstruction avortée (rc 3 inchangé)"),
    lambda: FileNotFoundError(2, "No such file or directory"),
    lambda: IsADirectoryError(21, "Is a directory"),
    lambda: OSError(28, "No space left on device"),
], ids=["RuntimeError", "ValueError", "ReconstructionAvorteeError", "FileNotFoundError",
        "IsADirectoryError", "OSError-28"])
def test_c_ii_hors_ensemble_le_meme_objet_remonte_sans_chainage(fabrique, tmp_path):
    obj = fabrique()
    with pytest.raises(type(obj)) as ei:
        with refus_nomme(tmp_path / "v3.db"):
            raise obj
    assert ei.value is obj
    assert obj.__cause__ is None and obj.__context__ is None


def test_c_iii_une_sous_classe_de_la_classe_de_couture_est_classee():
    Fille = type("FilleDEmplacementRefuse", (_couture()[0].EmplacementRefuse,), {})
    assert classer_refus(Fille("lien")) == (REFUSE, CAUSE_EMPLACEMENT)


@pytest.mark.parametrize("nom", sorted(_classes_reelles()))
def test_c_iii_un_homonyme_local_n_est_pas_classe(nom):
    reelle = _classes_reelles()[nom]
    assert classer_refus(reelle("contrôle positif")) is not None, "la classe réelle n'est pas classée"
    homonyme = type(nom, (Exception,), {})
    assert homonyme.__name__ == reelle.__name__ and homonyme is not reelle
    assert classer_refus(homonyme("même nom, autre classe")) is None


def _erreur_sqlite(classe: type, code: Optional[int]) -> BaseException:
    exc = classe("erreur SQLite fabriquée")
    if code is not None:
        exc.sqlite_errorcode = code  # SYNTHÉTIQUE : posé à la main
    return exc


@pytest.mark.parametrize("classe,code,attendu", [
    (sqlite3.DatabaseError, 26, (REFUSE, CAUSE_NON_SQLITE)),
    (sqlite3.OperationalError, 5, (REFUSE, CAUSE_VERROU)),
    (sqlite3.OperationalError, 517, (REFUSE, CAUSE_VERROU)),
    (sqlite3.DatabaseError, 26 | 0x100, (REFUSE, CAUSE_NON_SQLITE)),
    (sqlite3.DatabaseError, 11, (REFUSE, CAUSE_CORROMPU)),
    (sqlite3.DatabaseError, 11 | 0x100, (REFUSE, CAUSE_CORROMPU)),
    (sqlite3.OperationalError, 8, (REFUSE, CAUSE_LECTURE_SEULE)),
    (sqlite3.OperationalError, 1544, (REFUSE, CAUSE_LECTURE_SEULE)),
    (sqlite3.OperationalError, 1032, None),
    (sqlite3.IntegrityError, 19, None),
    (sqlite3.OperationalError, 14, None),
    (sqlite3.OperationalError, 10, None),
    (sqlite3.OperationalError, 6, None),
    (sqlite3.OperationalError, None, None),
], ids=["26", "5", "517", "26|0x100", "11", "11|0x100", "8", "1544", "1032", "19", "14", "10", "6",
        "sans-code"])
def test_c_iv_codes_par_masque_primaire(classe, code, attendu):
    assert classer_refus(_erreur_sqlite(classe, code)) == attendu


@pytest.mark.parametrize("fabrique,libelle", [
    (lambda: PermissionError(13, "Permission denied"), "état machine non inscriptible"),
    (lambda: NotADirectoryError(20, "Not a directory"), "chemin d'état occupé par un fichier"),
    (lambda: FileExistsError(17, "File exists"), "chemin d'état occupé par un fichier"),
    (lambda: _erreur_sqlite(sqlite3.OperationalError, 8), "store en lecture seule"),
    (lambda: _erreur_sqlite(sqlite3.OperationalError, 1544), "store en lecture seule"),
    (lambda: _erreur_sqlite(sqlite3.DatabaseError, 11), "store corrompu"),
], ids=["PermissionError", "NotADirectoryError", "FileExistsError", "8", "1544", "11"])
def test_c_viii_les_cinq_causes_portent_le_libelle_du_pont_a_la_lettre(fabrique, libelle):
    """T-00001078 : les QUATRE libellés sont épinglés LITTÉRALEMENT (jamais par la
    constante qui les porte) : `specs-sync` les lit pour choisir le remède, une
    permutation ou une retouche doit rougir."""
    assert classer_refus(fabrique()) == (REFUSE, libelle)


@pytest.mark.parametrize("fabrique", [
    lambda: PermissionError(13, "Permission denied"),
    lambda: NotADirectoryError(20, "Not a directory"),
    lambda: FileExistsError(17, "File exists"),
], ids=["PermissionError", "NotADirectoryError", "FileExistsError"])
def test_c_viii_les_trois_soeurs_ne_sont_classees_qu_a_la_construction(fabrique):
    """T-00001078 (S-00003602) : sous `erreurs_os=False` — le VERBE `sync-spec`, où
    l'`OSError` peut venir du SPEC —, aucune des trois sœurs n'est classée."""
    assert classer_refus(fabrique()) is not None, "précondition : la sœur n'est pas classée par défaut"
    assert classer_refus(fabrique(), erreurs_os=False) is None


@pytest.mark.parametrize("code,libelle", [(8, "store en lecture seule"), (11, "store corrompu")])
def test_c_viii_les_codes_8_et_11_valent_aussi_au_verbe(code, libelle):
    exc = _erreur_sqlite(sqlite3.OperationalError, code)
    assert classer_refus(exc, erreurs_os=False) == (REFUSE, libelle)


def test_c_viii_refus_nomme_erreurs_os_false_laisse_remonter_le_meme_objet(tmp_path):
    """T-00001078 : `refus_nomme(..., erreurs_os=False)` laisse REMONTER une sœur
    `OSError`, MÊME objet, sans chaînage ; par défaut, il la convertit."""
    obj = PermissionError(13, "Permission denied")
    with pytest.raises(PermissionError) as ei:
        with refus_nomme(tmp_path / "v3.db", erreurs_os=False):
            raise obj
    assert ei.value is obj and obj.__cause__ is None
    with pytest.raises(StoreV3Refuse):
        with refus_nomme(tmp_path / "v3.db"):
            raise PermissionError(13, "Permission denied")


def test_c_viii_base_supprimee_sous_la_connexion_1032_remonte_brute(tmp_path):
    """Binôme de fin de la fournée 3 (critic-opus, trouvaille A, recoupée) :
    `SQLITE_READONLY_DBMOVED` (étendu 1032, primaire 8) dit une base DÉPLACÉE ou
    SUPPRIMÉE sous la connexion, jamais un store en lecture seule. VRAI canal : la
    base est supprimée sous une connexion OUVERTE en journal DELETE, puis une
    écriture sous `refus_nomme(..., erreurs_os=False)` (le bloc du VERBE
    `sync-spec`) : l'`OperationalError` brute REMONTE, sans `StoreV3Refuse`.
    BORNE : sous WAL (le mode que pose `schema.get_db_connection`), l'écriture qui
    suit la suppression de la seule base ne lève PAS (mesuré, SQLite 3.53.4)."""
    if os.name == "nt":
        pytest.skip("SKIP : sous nt, un fichier ouvert ne se supprime pas")
    base = tmp_path / "v3.db"
    conn = sqlite3.connect(base)  # journal DELETE, le défaut : voir la BORNE
    try:
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        base.unlink()
        with pytest.raises(sqlite3.OperationalError) as ei:
            with refus_nomme(base, erreurs_os=False):
                conn.execute("INSERT INTO t VALUES (1)")
                conn.commit()
    finally:
        conn.close()
    exc = ei.value
    assert exc.sqlite_errorcode == 1032, (
        f"PRÉCONDITION : code réel {exc.sqlite_errorcode} ({exc.sqlite_errorname}), pas DBMOVED")
    assert not isinstance(exc, StoreV3Refuse) and exc.__cause__ is None
    assert classer_refus(exc) is None and classer_refus(exc, erreurs_os=False) is None


#: Modules qui appellent `refus_nomme` au relevé T-00001078 (cli ×3, run_export ×9 à la base
#: T-00001074, session_checkpoint, lessons_store, parse_specs — comptes par l'AST, jamais figés
#: ici). PRÉCONDITION du parcours, jamais sa borne : `test_c_ix` relève les modules en
#: PARCOURANT le paquet ; un sixième appelant y entre sans retoucher cette liste.
MODULES_REFUS_NOMME_CONNUS = frozenset({
    "agentic_v3.cli",
    "agentic_v3.db.run_export",
    "agentic_v3.checkpoints.session_checkpoint",
    "agentic_v3.db.lessons_store",
    "agentic_v3.ingestion.parse_specs",
})


def _appels_refus_nomme(source: str):
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Call):
            f = noeud.func
            if (isinstance(f, ast.Name) and f.id == "refus_nomme") or (
                    isinstance(f, ast.Attribute) and f.attr == "refus_nomme"):
                yield noeud


def _modules_du_paquet():
    """(nom pointé, source) de chaque `*.py` du paquet `agentic_v3`, hors `tests/` :
    le relevé se fait par PARCOURS, jamais par une liste écrite à la main."""
    paquet = Path(inspect.getsourcefile(cli)).resolve().parent
    for chemin in sorted(paquet.rglob("*.py")):
        rel = chemin.relative_to(paquet.parent)
        if "tests" in rel.parts:
            continue
        parties = rel.with_suffix("").parts
        if parties[-1] == "__init__":
            parties = parties[:-1]
        yield ".".join(parties), chemin.read_text(encoding="utf-8")


def test_c_ix_seul_le_verbe_sync_spec_pose_erreurs_os_false():
    """T-00001078 : le câblage de `erreurs_os`. Sous `run_export backfill`, aucun
    montage mesuré (M9 et 12 autres) n'amène une sœur dans un bloc `refus_nomme` :
    sous Python 3.14 `--base` sort en rc 4 « n'est pas un fichier de base » et
    `--base-vivante` en rc 6 ; sous 3.11 et 3.12, `--base` sous un dossier
    `chmod 000` sort en rc 1 (`PermissionError` de `Path.is_file()`), toujours avant
    tout bloc ; relevé non clos. Aucun cas mesuré ne distingue donc un bloc de
    `run_export` passé à `erreurs_os=False` du défaut — c'est l'AST qui le garde.
    Modules relevés par PARCOURS du paquet `agentic_v3` (hors `tests/`), les cinq
    connus en précondition : un seul appel du paquet pose `erreurs_os`, dans `cli`,
    à `False`."""
    appelants = {}
    for nom, source in _modules_du_paquet():
        appels = list(_appels_refus_nomme(source))
        if appels:
            appelants[nom] = appels
    manquants = sorted(MODULES_REFUS_NOMME_CONNUS - set(appelants))
    assert not manquants, (
        f"précondition : parcours incomplet, ou module qui n'appelle plus `refus_nomme` : {manquants}")
    avec = []
    for nom in sorted(appelants):
        for appel in appelants[nom]:
            for mot in appel.keywords:
                if mot.arg == "erreurs_os":
                    avec.append((nom, ast.literal_eval(mot.value)))
    assert avec == [("agentic_v3.cli", False)], avec


#: T-00001078 : la doctrine ÉCRITE. Par surface : le texte, ce qu'il DOIT porter, ce qu'il ne doit PLUS
#: porter (texte périmé). Un témoin texte à portée docstring (piège 1) : les mots viennent de `p2_docs.py`.
def _aplati(texte: str) -> str:
    return " ".join((texte or "").split())


DOCTRINE = {
    "refus_store.__doc__": (
        lambda: _aplati(refus_store.__doc__),
        ("depuis T-00001078", "CAUSE_NON_INSCRIPTIBLE", "CAUSE_OCCUPE", "CAUSE_LECTURE_SEULE",
         "CAUSE_CORROMPU", "jamais `OSError` entière", "erreurs_os=False",
         "SAUF les trois sœurs `OSError`"),
        ("HORS de la table du témoin de parité", "que les ouvreurs laissent remonter",
         "tout l'ensemble ci-dessus"),
    ),
    "classer_refus.__doc__": (
        lambda: _aplati(classer_refus.__doc__),
        ("erreurs_os", "CAUSE_LECTURE_SEULE", "CAUSE_CORROMPU", "jamais `OSError` entière",
         "ne classe AUCUNE des trois sœurs", "l'étendu 1032"),
        ("26 ou 5",),
    ),
    "refus_nomme.__doc__": (
        lambda: _aplati(refus_nomme.__doc__),
        ("erreurs_os", "REMONTE, MÊME objet"),
        (),
    ),
    "cli.__doc__": (
        lambda: _aplati(cli.__doc__),
        ("lecture seule, corrompu", "PermissionError", "NotADirectoryError", "FileExistsError",
         "les trois soeurs `OSError` exceptees", "un spec illisible n'est pas un store refuse",
         "`OperationalError` 1032"),
        ("code 11",),
    ),
    "refus_store.py (commentaire des libellés)": (
        lambda: inspect.getsource(refus_store),  # texte BRUT : la phrase tient sur UNE ligne
        ("SAUF les quatre derniers (T-00001078)",
         "test_libelles_des_quatre_causes_neuves_egaux_au_pont"),
        ("sans témoin de parité de libellé",),
    ),
}


@pytest.mark.parametrize("surface", sorted(DOCTRINE))
def test_c_x_la_doctrine_ecrite_dit_les_cinq_causes_et_leur_portee(surface):
    lire, presents, absents = DOCTRINE[surface]
    texte = lire()
    for mot in presents:
        assert mot in texte, f"{surface} : « {mot} » manque"
    for mot in absents:
        assert mot not in texte, f"{surface} : texte périmé « {mot} »"


def test_c_v_couture_masquee_classer_refus_ne_leve_pas(tmp_path):
    with _couture_ledger_store_absente(tmp_path):
        with pytest.raises(run_export.PanneInfrastructure):
            run_export._couture_ledger_store()  # précondition : la couture est bien absente
        assert classer_refus(ValueError("nue")) is None
        assert classer_refus(run_export.PanneInfrastructure("couture absente")) == (EN_PANNE, CAUSE_PANNE)


def test_c_vi_cause_et_origine_portent_l_exception_d_origine(tmp_path):
    chemin = tmp_path / "v3.db"
    orig = _couture()[0].OuvertureImpossible("ligne un\nligne deux")
    with pytest.raises(StoreV3Refuse) as ei:
        with refus_nomme(chemin):
            raise orig
    assert ei.value.__cause__ is orig
    assert ei.value.origine is orig
    assert str(ei.value) == (
        f"store V3 REFUSÉ ({CAUSE_OUVERTURE}) — {chemin} — OuvertureImpossible: ligne un ligne deux"
    )


@pytest.mark.parametrize("nom_dossier,message", [
    ("a\nb", "x"),
    ("a\rb", "x"),
    ("a b", "x\x1b[2Ky"),
], ids=["chemin-LF", "chemin-CR", "message-ESC"])
def test_c_vii_affichage_aplati_le_refus_tient_une_ligne(nom_dossier, message, tmp_path):
    """critic-opus T5 : un chemin ou un message à caractère non imprimable sortait
    sur PLUSIEURS lignes (ou portait une séquence de terminal). Affichage seul :
    chaque non-imprimable devient `?`, un vrai espace survit, `chemin` garde le
    chemin RÉEL. Le dossier n'est jamais créé."""
    chemin = tmp_path / nom_dossier / "v3.db"
    orig = _couture()[0].OuvertureImpossible(message)
    with pytest.raises(StoreV3Refuse) as ei:
        with refus_nomme(chemin):
            raise orig
    texte = str(ei.value)
    assert len(texte.splitlines()) == 1, repr(texte)
    assert all(c.isprintable() for c in texte), repr(texte)
    assert ei.value.chemin == chemin, "l'attribut chemin a été aplati : il doit rester réel"
    affiche = "".join(c if c.isprintable() else "?" for c in str(chemin))
    assert f"— {affiche} —" in texte, repr(texte)
    assert not chemin.parent.exists()


# -- (d) le verbe `sync-spec` sous le refus nommé (T-00001059) -------------------


def _d_sonde_courte(uri: str) -> sqlite3.Connection:
    """`schema._connexion_nue` ramenée de 30 s à 0,05 s, dans le banc SEUL : la
    production garde l'attente (figée par
    `test_l_attente_d_un_ecrivain_egale_celle_du_producteur_V3`)."""
    return sqlite3.connect(uri, uri=True, timeout=0.05)


@dataclass
class PorteurWal:
    """Un autre écrivain tenu (`BEGIN IMMEDIATE`) sur un store en WAL."""

    liberer: Callable[[], None]
    ctx: Callable[[], ContextManager]


def _porteur_wal(store: Path, request) -> PorteurWal:
    """Verrou RÉEL en WAL, distinct de `_monter_verrou` (journal DELETE +
    EXCLUSIVE, autre mécanisme) : la construction passe, le premier write du
    verbe attend. PRÉCONDITION : le store est en `wal`. `liberer()` est
    IDEMPOTENT — appelé par un témoin avant sa relance ET enregistré comme
    finaliseur (un second `ROLLBACK` sur connexion fermée lèverait)."""
    create_tables(store)
    porteur = sqlite3.connect(str(store), timeout=0.05, isolation_level=None)
    mode = porteur.execute("PRAGMA journal_mode").fetchone()[0]
    if mode != "wal":
        porteur.close()
        pytest.fail(f"précondition : store en journal {mode!r}, attendu 'wal'")
    porteur.execute("BEGIN IMMEDIATE")
    libere: List[bool] = []

    def liberer() -> None:
        if libere:
            return
        libere.append(True)
        try:
            porteur.execute("ROLLBACK")
        finally:
            porteur.close()

    request.addfinalizer(liberer)
    return PorteurWal(
        liberer=liberer,
        ctx=lambda: mock.patch.object(schema, "_connexion_nue", _d_sonde_courte),
    )


def _d_lignes_spec(store: Path) -> int:
    """Lignes de `spec_requirements` ; un lecteur n'est pas bloqué en WAL."""
    conn = sqlite3.connect(str(store), timeout=0.05)
    try:
        return conn.execute("SELECT COUNT(*) FROM spec_requirements").fetchone()[0]
    finally:
        conn.close()


#: Corps de la v1 posée à la main, patron de `TestSyncSpecAucuneVersionSansEvenement`
#: (`test_run_export.py`), RECOPIÉ et jamais importé.
_D_SPEC_V1 = "# Titre [REQ-S]\nancien"


def _d_spec_v2(tmp_path: Path) -> Path:
    spec = tmp_path / "spec-d.md"
    spec.write_text("# Titre [REQ-S]\ncontenu v2\n", encoding="utf-8")
    return spec


def _d_poser_v1(store: Path, spec: Path) -> None:
    create_tables(store)
    conn = sqlite3.connect(str(store))
    try:
        conn.execute(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES ('REQ-S', 1, ?, 'Titre [REQ-S]', ?, '[]')",
            (str(spec), _D_SPEC_V1),
        )
        conn.commit()
    finally:
        conn.close()


def _d_versions(store: Path) -> List[int]:
    conn = sqlite3.connect(str(store))
    try:
        return [r[0] for r in conn.execute(
            "SELECT version FROM spec_requirements WHERE req_id='REQ-S' ORDER BY version")]
    finally:
        conn.close()


def _d_mutations(store: Path) -> List[int]:
    conn = sqlite3.connect(str(store))
    try:
        return sorted(json.loads(r[0])["version"] for r in conn.execute(
            "SELECT payload_json FROM events_ledger WHERE event_type='SPEC_MUTATED'"))
    finally:
        conn.close()


def test_d_1_sync_spec_sous_verrou_wal_une_ligne_code_4_puis_relance_ecrit(partition, tmp_path, request, capsys):
    """Le défaut : en WAL, la construction de `SpecParser()` passe et le verrou
    mord au premier INSERT de `_synchroniser` ; `OperationalError` 5 sortait de
    `cli.main` (traceback, code 1). PRÉCONDITION, jamais un sync « de contrôle »
    (il consommerait la section) : le spec rend au moins une section et
    `spec_requirements` est vide. POSTCONDITION : verrou libéré, la relance écrit
    la section — le write refusé était bien dû."""
    store = partition
    argv = _argv("sync-spec", tmp_path)
    _store_sain(store)
    sections = SpecParser(store).parse_markdown_file(argv[1])
    assert sections, "précondition : le spec du banc ne rend aucune section"
    assert _d_lignes_spec(store) == 0, "précondition : spec_requirements n'est pas vide"
    porteur = _porteur_wal(store, request)
    capsys.readouterr()
    with porteur.ctx():
        code, out, err = _cli(argv, capsys)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _une_ligne_de_refus(err, "sync-spec")
    assert REFUSE in ligne and f"({CAUSE_VERROU})" in ligne, ligne
    assert str(store) in ligne, f"le chemin du store manque : {ligne}"
    assert "OperationalError: database is locked" in ligne, ligne
    assert _d_lignes_spec(store) == 0, "une section a été écrite sous le verrou"
    porteur.liberer()
    code, out, err = _cli(argv, capsys)
    assert code in (0, None), f"relance : code {code!r}, stderr {err!r}"
    assert "store V3" not in err
    assert _d_lignes_spec(store) == len(sections), "la relance n'a rien écrit"


@pytest.mark.parametrize("verbe", ("status", "resume"))
def test_d_1_controle_les_lecteurs_ne_sont_pas_refuses_sous_verrou_wal(verbe, partition, tmp_path, request, capsys):
    """CONTRÔLE DE MONTAGE, pas un témoin du correctif : sous le MÊME porteur, un
    lecteur n'est pas bloqué en WAL — le refus de d1 vient du write du verbe,
    jamais d'un store que le montage rendrait illisible."""
    porteur = _porteur_wal(partition, request)
    capsys.readouterr()
    with porteur.ctx():
        code, out, err = _cli(_argv(verbe, tmp_path), capsys)
    assert code in (0, None), f"code {code!r}, stderr {err!r}"
    assert "store V3" not in err


def test_d_2_la_bibliotheque_releve_l_erreur_brute_sous_verrou_wal(partition, tmp_path, request):
    """Frontière BIBLIOTHÈQUE, compatible T31/T47 (`test_run_export.py`) : sous le
    même porteur, `process_and_sync_spec` relève l'`OperationalError` BRUTE de
    code primaire 5 — la conversion vit dans `cli.main`, jamais dans
    `parse_specs.py`."""
    store = partition
    spec = _argv("sync-spec", tmp_path)[1]
    porteur = _porteur_wal(store, request)
    with porteur.ctx():
        parser = SpecParser(store)
        with pytest.raises(sqlite3.OperationalError) as ei:
            parser.process_and_sync_spec(spec)
    assert _code_primaire(ei.value) == 5, f"code {getattr(ei.value, 'sqlite_errorcode', None)!r}"
    assert not isinstance(ei.value, StoreV3Refuse)


def test_d_3_panne_d_export_apres_le_commit_sort_en_5_par_la_cli(partition, tmp_path, capsys):
    """Forme de T32 (`test_run_export.py`) par la CLI : `_flush_export` lève
    `PanneInfrastructure` APRÈS le commit de l'événement. Versions [1, 2] et
    SPEC_MUTATED [2] prouvent que la panne est celle du VERBE (événement
    commité), pas de la construction. Changement visible de T-00001059, pour la
    CLI seule : traceback et code 1 -> une ligne et code 5."""
    store = partition
    spec = _d_spec_v2(tmp_path)
    _d_poser_v1(store, spec)
    capsys.readouterr()
    with mock.patch.object(event_store.EventStore, "_flush_export",
                           side_effect=run_export.PanneInfrastructure("greffe banc")):
        code, out, err = _cli(["sync-spec", str(spec)], capsys)
    assert code == 5, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _une_ligne_de_refus(err, "sync-spec")
    assert EN_PANNE in ligne and f"({CAUSE_PANNE})" in ligne, ligne
    assert _d_versions(store) == [1, 2], "la v2 n'a pas été commitée : panne de construction ?"
    assert _d_mutations(store) == [2], "l'événement de la v2 n'est pas commité"


def test_d_3prime_verrou_synthetique_d_append_event_compense_puis_sort_en_4(partition, tmp_path, capsys):
    """SYNTHÉTIQUE (`sqlite_errorcode` posé à la main) : `append_event` lève un
    verrou AVANT son commit. La compensation PRÉCÈDE le refus — versions [1] —,
    puis la CLI sort en 4. Le vrai R1 (le verrou heurte AUSSI la compensation)
    n'est PAS figé : un témoin figerait le défaut (docstring de `cli`)."""
    store = partition
    spec = _d_spec_v2(tmp_path)
    _d_poser_v1(store, spec)
    capsys.readouterr()
    with mock.patch.object(event_store.EventStore, "append_event",
                           side_effect=_erreur_sqlite(sqlite3.OperationalError, 5)) as appel:
        code, out, err = _cli(["sync-spec", str(spec)], capsys)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _une_ligne_de_refus(err, "sync-spec")
    assert REFUSE in ligne and f"({CAUSE_VERROU})" in ligne, ligne
    assert appel.call_count == 1
    assert _d_versions(store) == [1], "la compensation n'a pas précédé le refus"


def test_d_4_hors_ensemble_le_meme_objet_remonte_du_verbe(partition, tmp_path, capsys):
    """Forme de T46 (`test_run_export.py`) par la CLI : le tirage d'ULID lève une
    `RunExportError` NUE — classe MÈRE de `PanneInfrastructure`, hors ensemble.
    `cli.main` laisse remonter le MÊME objet, sans ligne `store V3` ni version
    écrite."""
    store = partition
    spec = _d_spec_v2(tmp_path)
    _d_poser_v1(store, spec)
    obj = run_export.RunExportError("couture ids absente (banc T-00001059)")
    assert classer_refus(obj) is None, "précondition : l'erreur du banc est classée"
    capsys.readouterr()
    with mock.patch.object(run_export, "nouvel_ulid", side_effect=obj), \
            mock.patch.object(sys, "argv", ["agentic_v3", "sync-spec", str(spec)]):
        with pytest.raises(run_export.RunExportError) as ei:
            cli.main()
    assert ei.value is obj
    assert "store V3" not in capsys.readouterr().err
    assert _d_versions(store) == [1]


def test_d_5_la_ligne_du_code_3_est_aplatie(partition, tmp_path, capsys):
    """S-00003354. Message SYNTHÉTIQUE : le vrai remède de
    `ReconstructionAvorteeError` porte des chemins (`db_path.parent`, le
    `filename` d'un `OSError` de `runs/`), qu'un nom de dossier à saut de ligne
    coupait en deux lignes."""
    _store_sain(partition)
    argv = _argv("sync-spec", tmp_path)
    capsys.readouterr()
    with mock.patch.object(SpecParser, "process_and_sync_spec",
                           side_effect=ReconstructionAvorteeError("a\nb\x1bc   d")):
        code, out, err = _cli(argv, capsys)
    assert code == 3, f"code {code!r}, stderr {err!r}"
    lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
    assert len(lignes) == 1, f"attendu UNE ligne stderr, reçu {len(lignes)} : {err!r}"
    assert lignes[0].startswith("agentic_v3 sync-spec: "), lignes[0]
    assert "a b?c d" in lignes[0], repr(lignes[0])
    assert "\x1b" not in err and "Traceback" not in err


def test_d_6_sync_spec_spec_illisible_PermissionError_remonte_brute(partition, tmp_path, capsys):
    """T-00001078, portée : un SPEC illisible n'est pas un store refusé — la
    `PermissionError` du verbe remonte telle quelle, sans ligne `store V3`, et
    jamais en code 4 (la skill specs-sync arrête TOUT sur un 4)."""
    _sauter_sans_droits_posix("spec chmod 000")
    _store_sain(partition)
    spec = tmp_path / "illisible.md"
    spec.write_text("# Titre\n\nCorps.\n", encoding="utf-8")
    os.chmod(spec, 0)
    try:
        capsys.readouterr()
        with mock.patch.object(sys, "argv", ["agentic_v3", "sync-spec", str(spec)]):
            with pytest.raises(PermissionError) as ei:
                cli.main()
    finally:
        os.chmod(spec, 0o600)
    assert ei.value.filename == str(spec), f"précondition : {ei.value.filename!r}"
    assert "store V3" not in capsys.readouterr().err


def test_d_6_bis_sync_spec_permission_error_synthetique_au_verbe_remonte(partition, tmp_path, capsys):
    """T-00001078, SYNTHÉTIQUE (actif sous root, où d_6 saute) : une
    `PermissionError` levée PENDANT `process_and_sync_spec` remonte brute."""
    _store_sain(partition)
    obj = PermissionError(13, "Permission denied (injection T-00001078)")
    capsys.readouterr()
    with mock.patch.object(SpecParser, "process_and_sync_spec", side_effect=obj):
        with mock.patch.object(sys, "argv", ["agentic_v3", *_argv("sync-spec", tmp_path)]):
            with pytest.raises(PermissionError) as ei:
                cli.main()
    assert ei.value is obj
    assert "store V3" not in capsys.readouterr().err


def test_d_7_sync_spec_store_en_lecture_seule_au_verbe_sort_en_4(partition, tmp_path, capsys):
    """T-00001078 : store en `chmod 444` — la CONSTRUCTION passe (précondition),
    le premier write du VERBE lève le code 8 : une ligne, code 4, octets inchangés.
    Les annexes `-wal`/`-shm` que SQLite laisse à côté d'un store en lecture seule
    ne sont PAS épinglées (reliquat mesuré hors processus, SUGGESTION hors write-set)."""
    _sauter_sans_droits_posix("store chmod 444")
    _store_sain(partition)
    os.chmod(partition, 0o444)
    avant = _empreinte(partition)
    try:
        SpecParser(db_path=partition)  # précondition : la construction ne refuse pas
        code, out, err = _cli(_argv("sync-spec", tmp_path), capsys)
    finally:
        os.chmod(partition, 0o600)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    ligne = _une_ligne_de_refus(err, "sync-spec")
    assert REFUSE in ligne and CAUSE_LECTURE_SEULE in ligne and str(partition) in ligne, ligne
    assert _empreinte(partition) == avant, "les octets du store ont bougé"


# -- (e) le 5e ouvreur : run_export._cli backfill (T-00001054) ------------------


#: Les trois modes de `backfill`. La base REFUSÉE est `--base` (frapper,
#: `--re-exporter`) ou la COPIE 1a (`--appliquer-depuis`) ; la SAINE est le store
#: de `partition`, désigné `--base` en `appliquer` et intouché sinon.
MODES_E = ("frapper", "re-exporter", "appliquer")


def _re_semer(store: Path, lignes: int = 1) -> Path:
    """Store du kit (`create_tables`, donc WAL) et `lignes` lignes `ulid IS NULL`
    d'une même tâche (dès la seconde, un prédécesseur), patron de
    `TestCliFormeDocumentee._base_env` (`test_run_export.py`)."""
    create_tables(store)
    conn = sqlite3.connect(str(store))
    try:
        for rang in range(lignes):
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
                ("T-E", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:0" + str(rang),
                 "ope" + str(rang), "TASK_CREATED", 0),
            )
        conn.commit()
    finally:
        conn.close()
    return store


def _re_nuls(store: Path) -> int:
    """Lignes `ulid IS NULL`, par un lecteur NU (non bloqué en WAL)."""
    conn = sqlite3.connect(str(store), timeout=0.05)
    try:
        return conn.execute("SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL").fetchone()[0]
    finally:
        conn.close()


def _re_triplets(store: Path) -> List[tuple]:
    """`(event_id, ulid, predecesseur_ulid)` de chaque ligne, par `event_id`."""
    conn = sqlite3.connect(str(store), timeout=0.05)
    try:
        return conn.execute(
            "SELECT event_id, ulid, predecesseur_ulid FROM events_ledger ORDER BY event_id"
        ).fetchall()
    finally:
        conn.close()


def _re_argv(mode: str, refusee: Path, saine: Path) -> List[str]:
    """Argv de `_cli` : la base REFUSÉE est `--base`, ou la copie 1a en `appliquer`."""
    if mode == "frapper":
        return ["backfill", "--base", str(refusee)]
    if mode == "re-exporter":
        return ["backfill", "--base", str(refusee), "--re-exporter"]
    return ["backfill", "--base", str(saine), "--appliquer-depuis", str(refusee)]


def _re_biblio(mode: str, refusee: Path, saine: Path) -> dict:
    """L'appel de BIBLIOTHÈQUE que `_cli` fait pour `_re_argv(mode, …)`."""
    if mode == "frapper":
        return run_export.backfill_historique(base=refusee)
    if mode == "re-exporter":
        return run_export.re_exporter_frappees(base=refusee)
    return run_export.backfill_historique(base=saine, appliquer_depuis=refusee)


def _re_cli(argv: List[str], capsys) -> Tuple[int, str, str]:
    """`run_export._cli(argv)` EN PROCESSUS (forme paquet) : (code, stdout,
    stderr). Une levée remonte telle quelle — hors processus, rc 1 et traceback.
    Nom distinct du `_cli` de la famille (b), qui pilote `cli.main`."""
    capsys.readouterr()
    code = run_export._cli(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _re_une_ligne(err: str) -> str:
    """La SEULE ligne stderr : préfixe de `backfill`, aucun traceback."""
    lignes = [ligne for ligne in err.splitlines() if ligne.strip()]
    assert len(lignes) == 1, f"attendu UNE ligne stderr, reçu {len(lignes)} : {err!r}"
    assert "Traceback" not in err
    assert lignes[0].startswith("run_export.py backfill: store V3 "), lignes[0]
    return lignes[0]


def _re_connexion_courte() -> ContextManager:
    """`sqlite3.connect` forcé à 0,05 s le temps du bloc : la connexion NUE de
    `_ouvrir_base_sqlite` attend 30 s en production, attente que ce banc ne fige
    pas."""
    vraie = sqlite3.connect

    def courte(*args, **kwargs):
        kwargs["timeout"] = 0.05
        return vraie(*args, **kwargs)

    return mock.patch.object(sqlite3, "connect", courte)


def _re_monter_verrou(store: Path, tmp_path: Path, request) -> Montage:
    """`_monter_verrou` (journal DELETE, porteur EXCLUSIVE), l'attente de
    `run_export` ramenée à 0,05 s : le verrou mord à la PREMIÈRE LECTURE."""
    return replace(_monter_verrou(store, tmp_path, request), ctx=_re_connexion_courte)


def _re_monter_ouverture_injectee(store: Path, tmp_path: Path, request) -> Montage:
    """SYNTHÉTIQUE, actif sous root (où `chmod 0` saute) : `_ouvrir_base_sqlite`
    lève `OuvertureImpossible` pour la SEULE base refusée et ouvre les autres —
    en `appliquer`, la saine est ouverte AVANT la copie."""
    m = _monter_ouverture_injectee(store, tmp_path, request)
    classe = _couture()[0].OuvertureImpossible
    vraie = run_export._ouvrir_base_sqlite

    def ouvrir(chemin: Path) -> sqlite3.Connection:
        if Path(chemin) == store:
            raise classe("ouverture impossible (injection T-00001054)")
        return vraie(chemin)

    return replace(m, ctx=lambda: mock.patch.object(run_export, "_ouvrir_base_sqlite", ouvrir))


def _re_versionner(store: Path, version: int) -> None:
    """`PRAGMA user_version = <version>` — un entier concaténé, jamais une f-string
    dans `execute` (réserve 8 de `_monter_version_future`)."""
    conn = sqlite3.connect(str(store))
    try:
        conn.execute("PRAGMA user_version = " + str(int(version)))
        conn.commit()
    finally:
        conn.close()


def _re_version(store: Path) -> int:
    """`PRAGMA user_version`, par un lecteur NU (0,05 s)."""
    conn = sqlite3.connect(str(store), timeout=0.05)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _re_monter_version_future(store: Path, tmp_path: Path, request) -> Montage:
    """Store du kit SEMÉ (une ligne `ulid IS NULL`), `user_version` FUTUR."""
    _re_semer(store)
    _re_versionner(store, SCHEMA_VERSION + 1)
    return Montage(
        origine=lambda e: isinstance(e, schema.SchemaVersionError),
        cause=CAUSE_VERSION,
        temoin=store,
    )


def _re_monter_version_future_forme_v1(store: Path, tmp_path: Path, request) -> Montage:
    """Store d'un kit PLUS RÉCENT dont `events_ledger` n'a PAS la colonne `ulid`
    (forme v1, 9 colonnes), une ligne, `user_version` FUTUR. La PREMIÈRE LECTURE de
    lignes y lève `OperationalError` code 1 (« no such column: ulid »), brute, rc 1 :
    le refus de version DOIT la précéder (T-00001075, ordre du site unique)."""
    conn = sqlite3.connect(str(store))
    try:
        conn.execute(
            "CREATE TABLE events_ledger (event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "task_id TEXT, agent_role TEXT, event_type TEXT, payload_json TEXT, "
            "created_at TIMESTAMP, operation_id TEXT, event_kind TEXT, attempt INTEGER)")
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
            ("T-E", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "ope0",
             "TASK_CREATED", 0))
        conn.commit()
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT ulid FROM events_ledger").fetchall()  # précondition
    finally:
        conn.close()
    _re_versionner(store, SCHEMA_VERSION + 1)
    return Montage(
        origine=lambda e: isinstance(e, schema.SchemaVersionError),
        cause=CAUSE_VERSION,
        temoin=store,
    )


MONTAGES_E = {
    "version_future": _re_monter_version_future,
    "version_future_forme_v1": _re_monter_version_future_forme_v1,
    "non_sqlite": _monter_non_sqlite,
    "droits": _monter_droits,
    "verrou": _re_monter_verrou,
    "ouverture_injectee": _re_monter_ouverture_injectee,
    "corrompu": _monter_corrompu,
}


@pytest.mark.parametrize("scenario", sorted(MONTAGES_E))
@pytest.mark.parametrize("mode", MODES_E)
def test_re_1_base_refusee_une_ligne_code_4(mode, scenario, partition, tmp_path, request, capsys):
    """Refus à l'OUVERTURE (droits, injection ; depuis T-00001075, la lecture de
    version y fait lever aussi le non SQLite, le verrou et le schéma FUTUR, forme
    v1 comprise, avant toute lecture de ligne de ce store) : la bibliothèque lève
    `StoreV3Refuse` nommant la base RÉELLEMENT refusée — la copie 1a en
    `appliquer` —, `_cli` sort en 4 sur UNE ligne, stdout vide ; ni la refusée
    ni la saine ne bougent."""
    saine = _re_semer(partition)
    refusee = tmp_path / "refusee.db"
    m = MONTAGES_E[scenario](refusee, tmp_path, request)
    avant = (_etat(m, refusee), _empreinte(saine), _annexes(saine))
    with m.ctx():
        with pytest.raises(StoreV3Refuse) as ei:
            _re_biblio(mode, refusee, saine)
        code, out, err = _re_cli(_re_argv(mode, refusee, saine), capsys)
    exc = ei.value
    assert m.origine(exc.origine), (
        f"précondition : le montage {scenario} n'a pas levé la classe attendue, "
        f"mais {type(exc.origine).__module__}.{type(exc.origine).__name__}: {exc.origine}"
    )
    assert exc.origine is exc.__cause__, "origine et __cause__ divergent"
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, m.cause, refusee)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _re_une_ligne(err)
    assert f"{REFUSE} ({m.cause}) — {refusee} — " in ligne, ligne
    assert (_etat(m, refusee), _empreinte(saine), _annexes(saine)) == avant, (
        "octets, mode ou annexes de la refusée ou de la saine ont bougé")


@pytest.mark.parametrize("mode", ("frapper", "re-exporter"))
def test_re_2_hors_projet_base_vivante_refusee_sans_chemin(mode, partition, tmp_path, monkeypatch, capsys):
    """`--base-vivante` hors projet : la résolution de la base (bloc (a)) lève
    `CadrePathError`, refusée en une ligne sans chemin (`_cli` ne passe pas
    `depuis` : le chemin affiché se résout au cwd, ou ne se résout pas)."""
    hors = _hors_projet(tmp_path, monkeypatch)
    argv = ["backfill", "--base-vivante"] + (["--re-exporter"] if mode == "re-exporter" else [])
    code, out, err = _re_cli(argv, capsys)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _re_une_ligne(err)
    assert f"{REFUSE} ({CAUSE_RACINE}) — {CHEMIN_NON_RESOLU} — " in ligne, ligne
    assert list(hors.iterdir()) == [], "un fichier est né dans le cwd hors projet"


@pytest.mark.parametrize("mode", MODES_E)
def test_re_3_panne_sort_brute_cause_chainee(mode, partition, tmp_path, request, capsys):
    """Décision pilote S-00003489 : la panne d'infrastructure reste en rc 1,
    brute, cause chaînée, sans ligne `store V3`. EN PROCESSUS (forme paquet), la
    panne traverse `StoreV3Refuse` (EN PANNE) puis est relancée telle quelle ;
    hors processus (forme chemin, `-m`) elle ne le traverse pas (docstring de
    `_cli`) : ce témoin ne couvre pas ces formes."""
    saine = _re_semer(partition)
    copie = _re_semer(tmp_path / "copie.db")
    m = _monter_panne(saine, tmp_path, request)
    with m.ctx():
        with pytest.raises(run_export.PanneInfrastructure) as ei:
            _re_cli(_re_argv(mode, copie, saine), capsys)
    assert type(ei.value) is run_export.PanneInfrastructure, type(ei.value)
    assert "couture cadre.ledger.store" in str(ei.value), f"précondition : {ei.value}"
    assert ei.value.__cause__ is not None, "la cause chaînée est perdue"
    assert "store V3" not in capsys.readouterr().err


def test_re_3_sans_cause_la_panne_ressort_brute_sans_le_refus_dans_sa_trace(partition, tmp_path, capsys):
    """Une panne SANS cause ressort brute, `__cause__` nul, et sa trace ne porte
    pas le type du refus : c'est la clause `from exc.origine.__cause__` de `_cli`
    qui l'en garde (sans elle, « During handling… »). Le NOM de ce test ne porte
    pas ce type : il figure dans la trace (mesuré, faux rouge à la base)."""
    saine = _re_semer(partition)
    panne = run_export.PanneInfrastructure("panne SANS cause (banc T-00001054)")
    with mock.patch.object(run_export, "_ouvrir_base_sqlite", side_effect=panne):
        with pytest.raises(run_export.PanneInfrastructure) as ei:
            _re_cli(["backfill", "--base", str(saine)], capsys)
    assert ei.value is panne
    assert ei.value.__cause__ is None
    trace = "".join(traceback.format_exception(type(ei.value), ei.value, ei.value.__traceback__))
    assert "StoreV3Refuse" not in trace, trace


def test_re_4_base_de_zero_octet_remonte_brute(partition, tmp_path, capsys):
    """Résidu R2 : une base de 0 octet est un fichier (le contrôle CLI passe),
    SQLite l'ouvre, la première lecture lève le code 1 — hors ensemble, brut."""
    vide = tmp_path / "vide.db"
    vide.write_bytes(b"")
    with pytest.raises(sqlite3.OperationalError) as ei:
        _re_cli(["backfill", "--base", str(vide)], capsys)
    assert not isinstance(ei.value, StoreV3Refuse)
    assert _code_primaire(ei.value) == 1, f"code {getattr(ei.value, 'sqlite_errorcode', None)!r}"
    assert "store V3" not in capsys.readouterr().err
    assert vide.read_bytes() == b""


def test_re_4_borne_apres_le_commit_aucun_refus_base_deja_ecrite(partition, tmp_path, monkeypatch, capsys):
    """BORNE (d) : le bloc de la phase d'écriture S'ARRÊTE au commit. Un code 5
    SYNTHÉTIQUE levé par le décompte qui le suit (`SELECT COUNT(*)`) sort BRUT,
    jamais en `StoreV3Refuse` : la base EST écrite (nuls 1 -> 0), un refus y
    mentirait sur « base inchangée » (T-00001074)."""
    store = _re_semer(tmp_path / "apres.db")
    vraie = sqlite3.connect

    class _ConnDecompte(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL"):
                exc = sqlite3.OperationalError("database is locked (synthétique, après le commit)")
                exc.sqlite_errorcode = 5
                raise exc
            return super().execute(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(run_export.sqlite3, "connect", functools.partial(vraie, factory=_ConnDecompte))
        with pytest.raises(sqlite3.OperationalError) as ei:
            _re_cli(["backfill", "--base", str(store)], capsys)
    assert _code_primaire(ei.value) == 5, "précondition : le code synthétique n'est pas lu"
    assert not isinstance(ei.value, StoreV3Refuse)
    assert "store V3" not in capsys.readouterr().err
    assert _re_nuls(store) == 0, "précondition : le commit n'a pas précédé le décompte"


@pytest.mark.email_git_reel
def test_re_4_borne_R4_hors_projet_avec_base_auteur_courant_remonte_brut(partition, tmp_path, monkeypatch, capsys):
    """BORNE (R4), vrai `_email_git` (greffe de `partition` éteinte) : hors projet
    avec `--base`, `auteur_courant` lève `CadrePathError` AVANT l'ouverture,
    HORS des blocs — brute, base inchangée."""
    store = _re_semer(tmp_path / "r4.db")
    avant = _empreinte(store)
    _hors_projet(tmp_path, monkeypatch)
    with pytest.raises(_classe_cadre_path_error()) as ei:
        _re_cli(["backfill", "--base", str(store)], capsys)
    assert not isinstance(ei.value, StoreV3Refuse)
    pile = [trame.name for trame in traceback.extract_tb(ei.value.__traceback__)]
    assert "auteur_courant" in pile, pile
    assert "store V3" not in capsys.readouterr().err
    assert (_re_nuls(store), _empreinte(store)) == (1, avant), "la base a bougé"


def test_re_4_borne_R9_export_apres_le_commit_remonte_brut(partition, tmp_path, monkeypatch, capsys):
    """BORNE (R9), sous la greffe : hors projet avec `--base`, l'`UPDATE` est
    COMMITÉ (nuls 1 -> 0) puis `chemin_export` lève `CadrePathError`, HORS des
    blocs — brute, base déjà écrite."""
    store = _re_semer(tmp_path / "r9.db")
    assert _re_nuls(store) == 1, "précondition : aucune ligne à frapper"
    _hors_projet(tmp_path, monkeypatch)
    with pytest.raises(_classe_cadre_path_error()) as ei:
        _re_cli(["backfill", "--base", str(store)], capsys)
    assert not isinstance(ei.value, StoreV3Refuse)
    pile = [trame.name for trame in traceback.extract_tb(ei.value.__traceback__)]
    assert "chemin_export" in pile, pile
    assert "store V3" not in capsys.readouterr().err
    assert _re_nuls(store) == 0, "le commit n'a pas précédé l'export"


def _re_env(tmp_path: Path) -> dict:
    """Patron `TestCliFormeDocumentee._base_env` (`test_run_export.py`) RECOPIÉ,
    jamais importé : projet `git init`, `user.email` LOCAL, variables `GIT_*`
    retirées (un `GIT_DIR` hérité ferait écrire ce `config` dans le dépôt HÔTE).
    PRÉCONDITION assertée : sans l'adresse, `auteur_courant` sortirait en 6."""
    if shutil.which("git") is None:
        pytest.skip("git absent du PATH : le vrai canal de backfill n'a pas d'auteur")
    env = {cle: val for cle, val in os.environ.items() if not cle.startswith("GIT_")}
    projet = tmp_path / "projet-e"
    projet.mkdir()
    subprocess.run(["git", "init", "-q", str(projet)], check=True, env=env)
    subprocess.run(["git", "-C", str(projet), "config", "user.email", "e@banc.test"],
                   check=True, env=env)
    lu = subprocess.run(["git", "-C", str(projet), "config", "user.email"],
                        capture_output=True, text=True, env=env)
    assert lu.stdout.strip() == "e@banc.test", (
        f"précondition : user.email local non lu (rc {lu.returncode}, {lu.stderr!r})")
    env["CADRE_PROJECT_ROOT"] = str(projet)
    env["CADRE_STATE_DIR"] = str(tmp_path / "state-e")
    return env


@pytest.mark.parametrize("scenario", ("non_sqlite", "version_future", "corrompu"))
@pytest.mark.parametrize("forme", ("chemin", "-m"))
def test_re_5_vrai_canal_base_refusee_une_ligne_code_4(forme, scenario, tmp_path):
    """VRAI canal, sous-processus : `python3 run_export.py` et `-m`. Seule autre
    ligne tolérée : la `RuntimeWarning` de runpy en `-m`. Module et racine tirés
    de `run_export.__file__`, jamais du `__file__` de ce test. Le schéma FUTUR
    (T-00001075) y lève la classe du PAQUET (`agentic_v3.db.schema`), jamais une
    classe de `__main__` : la ligne porte la version lue, `runs/` ne naît pas."""
    env = _re_env(tmp_path)
    refusee = tmp_path / "refusee.db"
    if scenario == "non_sqlite":
        refusee.write_bytes(b"pas une base SQLite\n" * 64)
        attendu = f"{REFUSE} ({CAUSE_NON_SQLITE}) — {refusee} — DatabaseError: "
    elif scenario == "corrompu":
        _corrompre_en_tete(refusee)
        attendu = f"{REFUSE} ({CAUSE_CORROMPU}) — {refusee} — DatabaseError: "
    else:
        _re_semer(refusee)
        _re_versionner(refusee, SCHEMA_VERSION + 1)
        attendu = (f"{REFUSE} ({CAUSE_VERSION}) — {refusee} — SchemaVersionError: "
                   f"{refusee} porte user_version={SCHEMA_VERSION + 1} ")
    avant = _empreinte(refusee)
    module = Path(run_export.__file__).resolve()
    if forme == "chemin":
        cmd = [sys.executable, "-B", str(module), "backfill", "--base", str(refusee)]
    else:
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(module.parents[2]), env.get("PYTHONPATH")) if p)
        cmd = [sys.executable, "-B", "-m", "agentic_v3.db.run_export",
               "backfill", "--base", str(refusee)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(tmp_path),
                       timeout=120)
    assert r.returncode == 4, f"rc={r.returncode}\n{r.stderr}"
    assert r.stdout == ""
    tolerees = [ligne for ligne in r.stderr.splitlines() if "RuntimeWarning" in ligne]
    assert len(tolerees) <= (1 if forme == "-m" else 0), r.stderr
    ligne = _re_une_ligne("\n".join(
        ligne for ligne in r.stderr.splitlines() if "RuntimeWarning" not in ligne))
    assert attendu in ligne, ligne
    assert (_empreinte(refusee), _annexes(refusee)) == (avant, set())
    assert not (Path(env["CADRE_PROJECT_ROOT"]) / "runs").exists(), "runs/ écrit"


def test_re_6_la_constante_de_refus_vaut_4_des_deux_cotes():
    assert run_export.RC_STORE_REFUSE == cli.RC_STORE_REFUSE == 4


def test_re_7_les_docstrings_disent_le_refus_et_le_refus_de_version():
    """Réserve A-C1 de T-1054, SENS INVERSÉ (T-00001075) : l'UNIQUE segment (`;`)
    de `_cli` qui porte `user_version` dit le REFUS (`CAUSE_VERSION`) ; la phrase
    R3 périmée a disparu de la docstring ENTIÈRE (réserve B-C3) ; les bornes
    neuves n'y portent PAS le jeton `user_version`, et chacune est épinglée par
    son jeton ET par un mot de SENS dans la puce qui la porte — une puce inversée
    qui garde son jeton rougit, pas seulement une puce retirée."""
    for fonction in (run_export._cli, run_export.backfill_historique,
                     run_export.re_exporter_frappees):
        assert "StoreV3Refuse" in (fonction.__doc__ or ""), fonction.__name__
    assert "SchemaVersionError" in (run_export._ouvrir_base_sqlite.__doc__ or "")
    doc = " ".join((run_export._cli.__doc__ or "").split())
    assert "RC_STORE_REFUSE" in doc
    segments = [segment for segment in doc.split(";") if "user_version" in segment]
    assert len(segments) == 1, segments
    assert "CAUSE_VERSION" in segments[0], segments[0]
    for perime in ("n'est PAS refusé", "sort en 0", "résidu R3"):
        assert perime not in doc, f"phrase R3 périmée dans la docstring de `_cli` : {perime}"
    puces = doc.split(" * ")
    for jeton, sens in (("R3-bis", "non relue"), ("ANTÉRIEUR", "jamais monté"),
                        ("WAL ORPHELIN", "rabattu"), ("WAL ORPHELIN", "-journal")):
        porteuses = [puce for puce in puces if jeton in puce]
        assert len(porteuses) == 1, f"borne {jeton} : {len(porteuses)} puce(s) dans `_cli`"
        assert sens in porteuses[0], f"borne {jeton} sans son sens « {sens} » : {porteuses[0]}"
    # T-00001074 : R1 n'est plus un résidu ; la phase d'écriture est dite au point 4,
    # dans la bibliothèque et dans `refus_store`, dont la BORNE nomme `backfill`.
    assert "résidu R1" not in doc, "puce R1 périmée dans la docstring de `_cli`"
    porteuses = [puce for puce in puces if "PHASE D'ÉCRITURE" in puce]
    assert len(porteuses) == 1 and "commit inclus" in porteuses[0], porteuses
    doc_bf = " ".join((run_export.backfill_historique.__doc__ or "").split())
    assert "phase d'écriture" in doc_bf and "R1 : verrou au premier write" not in doc_bf, doc_bf
    doc_rs = " ".join((refus_store.__doc__ or "").split())
    tete = " ".join((refus_store.__doc__ or "").split("\n\n")[0].split())
    assert "run_export._cli backfill" in tete, f"la tête de `refus_store` ne nomme pas le 5e ouvreur : {tete}"
    assert "phase d'écriture" in doc_rs
    ailleurs = [phrase for phrase in doc_rs.split(". ") if "Ailleurs" in phrase]
    assert len(ailleurs) == 1 and "backfill" in ailleurs[0], ailleurs
    # T-00001078 : le code 11 et le code 8 sont REFUSÉS (point 4) ; plus de résidu R8.
    porteuse_4 = [puce for puce in puces if "RC_STORE_REFUSE" in puce]
    assert len(porteuse_4) == 1, porteuse_4
    assert "corrompu (code 11" in porteuse_4[0] and "lecture seule (code 8" in porteuse_4[0], porteuse_4
    assert "R8" not in doc, "résidu R8 périmé (T-00001078) dans la docstring de `_cli`"


def test_re_8_bases_saines_les_trois_modes_sortent_en_0(partition, tmp_path, capsys):
    """Contrôle : frapper la copie 1a, l'APPLIQUER à la vivante (ULID appliqués =
    ceux de la copie), puis ré-exporter — rc 0 partout, aucune ligne `store V3`."""
    copie = _re_semer(tmp_path / "copie.db", lignes=2)
    vivante = partition
    shutil.copyfile(copie, vivante)
    for argv in (["backfill", "--base", str(copie)],
                 ["backfill", "--base", str(vivante), "--appliquer-depuis", str(copie)],
                 ["backfill", "--base", str(vivante), "--re-exporter"]):
        code, out, err = _re_cli(argv, capsys)
        assert code == 0, f"{argv} : code {code!r}, stderr {err!r}"
        assert "store V3" not in err
        json.loads(out)
    frappe = _re_triplets(copie)
    assert all(ulid for _eid, ulid, _pred in frappe), f"précondition : copie non frappée {frappe}"
    assert _re_triplets(vivante) == frappe, "la vivante ne porte pas les ULID de la copie"


#: R3 RETOURNÉ (T-00001075), UNE cellule par mode ; la refusée porte un `user_version`
#: FUTUR : « frapper » (base nulle) ; « frapper-lointain » (idem, version `2**31 - 1`,
#: borne signée de SQLite — le seuil n'est pas une égalité à `SCHEMA_VERSION + 1`) ;
#: « re-exporter » (une ligne frappée ABSENTE du texte) ; « appliquer » (copie 1a
#: FUTURE) ; « appliquer-base » (la BASE `--base` FUTURE, copie 1a saine) ;
#: « frapper-vivante » et « re-exporter-vivante » (`--base-vivante` : la base est le
#: store de `partition`). COUVERTURE PAR CELLULE (3 formes × 8 cellules = 24, sonde
#: `probe_matrix.py` de l'annexe du plan) : ÉPINGLÉES 8 — paquet × {frapper,
#: re-exporter} × {`--base`, `--base-vivante`} et paquet × appliquer × {copie FUTURE,
#: base FUTURE} × `--base` (re_1, re_9), chemin et `-m` × frapper `--base` (re_5) ;
#: les 16 autres MESURÉES seulement, par la sonde.
MODES_R3 = ("frapper", "frapper-lointain", "re-exporter", "appliquer", "appliquer-base",
            "frapper-vivante", "re-exporter-vivante")


def _re_futur(mode: str) -> int:
    """La version FUTURE que porte la refusée du `mode` (réserve B-C1)."""
    return 2**31 - 1 if mode == "frapper-lointain" else SCHEMA_VERSION + 1


def _re_runs(depuis: Path) -> dict:
    """`chemin relatif -> sha256` de chaque fichier sous `<racine>/runs`."""
    runs = depuis / "runs"
    if not runs.exists():
        return {}
    return {str(f.relative_to(runs)): _empreinte(f) for f in sorted(runs.rglob("*")) if f.is_file()}


def _re_monter_r3(mode: str, dossier: Path, version: int, capsys, vivante: Path):
    """Montage par MODE qui ÉCRIT à `SCHEMA_VERSION` (c'est le contrôle de re_9) ; la
    refusée porte `version`. Rend (argv, refusée, saine) — la saine est la refusée
    quand le mode n'ouvre qu'un store."""
    dossier.mkdir()
    sur_vivante = mode.endswith("-vivante")
    if sur_vivante:
        for suffixe in ("",) + ANNEXES:  # le contrôle a déjà écrit cette base
            Path(str(vivante) + suffixe).unlink(missing_ok=True)
    seule = vivante if sur_vivante else dossier / "r3.db"
    designation = ["--base-vivante"] if sur_vivante else ["--base", str(seule)]
    if mode in ("frapper", "frapper-lointain", "frapper-vivante"):
        refusee = saine = _re_semer(seule)
        argv = ["backfill"] + designation
    elif mode in ("re-exporter", "re-exporter-vivante"):
        refusee = saine = _re_semer(seule, lignes=2)
        assert _re_cli(["backfill"] + designation, capsys)[0] == 0, "amorce"
        conn = sqlite3.connect(str(refusee))
        try:
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                "created_at,operation_id,event_kind,attempt,ulid) VALUES (?,?,?,?,?,?,?,?,?)",
                ("T-E", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:09", "ope9",
                 "TASK_CREATED", 0, run_export.nouvel_ulid()))
            conn.commit()
        finally:
            conn.close()
        argv = ["backfill"] + designation + ["--re-exporter"]
    elif mode == "appliquer":
        saine = _re_semer(dossier / "vivante.db")
        refusee = dossier / "copie.db"
        shutil.copyfile(saine, refusee)
        assert _re_cli(["backfill", "--base", str(refusee)], capsys)[0] == 0, "amorce"
        argv = ["backfill", "--base", str(saine), "--appliquer-depuis", str(refusee)]
    else:  # « appliquer-base » : la BASE est refusée, la copie 1a frappée par l'amorce
        refusee = _re_semer(dossier / "vivante.db")
        saine = dossier / "copie.db"
        shutil.copyfile(refusee, saine)
        assert _re_cli(["backfill", "--base", str(saine)], capsys)[0] == 0, "amorce"
        argv = ["backfill", "--base", str(refusee), "--appliquer-depuis", str(saine)]
    _re_versionner(refusee, version)
    return argv, refusee, saine


@pytest.mark.parametrize("mode", MODES_R3)
def test_re_9_schema_futur_refuse_avant_toute_ecriture(mode, partition, tmp_path, capsys):
    """R3 RETOURNÉ (T-00001075) : un store de schéma FUTUR est refusé avant toute
    écriture (rc 4, une ligne, `CAUSE_VERSION`, la version LUE dans le message), là
    où il était FRAPPÉ en rc 0. CONTRÔLE d'abord : le MÊME montage à `SCHEMA_VERSION`
    ÉCRIT (la précondition qui rend l'égalité d'octets non vide) ; puis le montage
    futur n'écrit rien — ni la refusée, ni la saine, ni `runs/`."""
    projet = run_export.project_root()
    argv, refusee, saine = _re_monter_r3(mode, tmp_path / "controle", SCHEMA_VERSION, capsys, partition)
    avant = (_empreinte(refusee), _empreinte(saine), _re_runs(projet))
    code, out, err = _re_cli(argv, capsys)
    assert code == 0, f"contrôle : code {code!r}, stderr {err!r}"
    assert (_empreinte(refusee), _empreinte(saine), _re_runs(projet)) != avant, (
        "précondition : à SCHEMA_VERSION, ce montage n'écrit rien")

    futur = _re_futur(mode)
    argv, refusee, saine = _re_monter_r3(mode, tmp_path / "futur", futur, capsys, partition)
    avant = (_empreinte(refusee), _annexes(refusee), _empreinte(saine), _annexes(saine),
             _re_runs(projet), _re_nuls(saine))
    code, out, err = _re_cli(argv, capsys)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _re_une_ligne(err)
    assert (f"{REFUSE} ({CAUSE_VERSION}) — {refusee} — SchemaVersionError: {refusee} porte "
            f"user_version={futur} ") in ligne, ligne
    assert (_empreinte(refusee), _annexes(refusee), _empreinte(saine), _annexes(saine),
            _re_runs(projet), _re_nuls(saine)) == avant, "une écriture a précédé le refus"
    assert _re_version(refusee) == futur


def test_re_10_store_anterieur_n_est_pas_refuse(partition, tmp_path, capsys):
    """Comparaison STRICTE (`>`, jamais `!=`) : un store ANTÉRIEUR est accepté, jamais
    monté — comportement de HEAD, épinglé."""
    store = _re_semer(tmp_path / "anterieur.db")
    _re_versionner(store, SCHEMA_VERSION - 1)
    code, out, err = _re_cli(["backfill", "--base", str(store)], capsys)
    assert code == 0, f"code {code!r}, stderr {err!r}"
    assert "store V3" not in err
    assert json.loads(out)["frappees"] == 1
    assert _re_version(store) == SCHEMA_VERSION - 1


@pytest.mark.parametrize("scenario", ("non_sqlite", "version_future"))
def test_re_11_connexion_fermee_sur_toute_levee_a_l_ouverture(scenario, partition, tmp_path,
                                                             request, monkeypatch):
    """Réserve A-C2 = B-C5 (T-00001075) : la lecture de version fait lever DANS
    l'ouvreur, au PRAGMA, ce qui levait avant à la première lecture de lignes (le
    non SQLite, code 26). La connexion y est fermée sur TOUTE levée, pas sur le seul
    refus de version : une connexion ouverte, une fermée, avant que `StoreV3Refuse`
    ne sorte ; et la pile de l'origine passe par `_refuser_schema_futur` — la levée a
    lieu au PRAGMA, jamais au SELECT du bloc (c)."""
    refusee = tmp_path / "refusee.db"
    m = MONTAGES_E[scenario](refusee, tmp_path, request)
    ouvertes: List[sqlite3.Connection] = []
    fermees: List[sqlite3.Connection] = []

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
        with pytest.raises(StoreV3Refuse) as ei:
            run_export.backfill_historique(base=refusee)
        comptes = (len(ouvertes), len(fermees))
    assert comptes == (1, 1), f"connexions (ouvertes, fermées) : {comptes}"
    exc = ei.value
    assert m.origine(exc.origine), (
        f"précondition : le montage {scenario} n'a pas levé la classe attendue, "
        f"mais {type(exc.origine).__module__}.{type(exc.origine).__name__}: {exc.origine}"
    )
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, m.cause, refusee)
    pile = [trame.name for trame in traceback.extract_tb(exc.origine.__traceback__)]
    assert "_refuser_schema_futur" in pile, pile


def _re_lecteur_tenu(store: Path, request) -> Callable[[], None]:
    """Verrou RÉEL au COMMIT : store passé en journal DELETE, un LECTEUR tenu en
    transaction (verrou SHARED) ; le BEGIN IMMEDIATE prend RESERVED, le commit
    attend EXCLUSIVE et mord. Rend `liberer`, IDEMPOTENT, enregistré en finaliseur."""
    conn = sqlite3.connect(str(store))
    try:
        mode = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
    finally:
        conn.close()
    assert mode == "delete", f"précondition : journal {mode!r}"
    lecteur = sqlite3.connect(str(store), timeout=0.05, isolation_level=None)
    lecteur.execute("BEGIN")
    lecteur.execute("SELECT COUNT(*) FROM events_ledger").fetchone()
    libere: List[bool] = []

    def liberer() -> None:
        if libere:
            return
        libere.append(True)
        try:
            lecteur.execute("ROLLBACK")
        finally:
            lecteur.close()

    request.addfinalizer(liberer)
    return liberer


#: Où mord le verrou de la phase d'écriture (d), et la ligne de `backfill_historique`
#: qui lève. Les clés nomment le MONTAGE (porteur), pas le mode de journal : `wal` —
#: écrivain `BEGIN IMMEDIATE` tenu sur un store WAL, au BEGIN IMMEDIATE ; `delete` —
#: LECTEUR tenu sur un store en journal DELETE, au COMMIT. Un ÉCRIVAIN tenu sur un
#: store en journal DELETE mord, lui, au BEGIN IMMEDIATE (mesuré, passe nonies de
#: T-00001082, montage non témoigné ici). Valeur : le TEXTE exact de la ligne qui lève.
VERROUS_ECRITURE = {"wal": 'conn.execute("BEGIN IMMEDIATE")', "delete": "conn.commit()"}


@pytest.mark.parametrize("verrou", sorted(VERROUS_ECRITURE))
@pytest.mark.parametrize("mode", ("frapper", "appliquer"))
def test_re_12_verrou_a_la_phase_d_ecriture_une_ligne_code_4_base_inchangee(
        mode, verrou, partition, tmp_path, request, capsys):
    """R1 RETOURNÉ (T-00001074) : le verrou qui mord à la phase d'écriture — sous
    un écrivain tenu en WAL, au BEGIN IMMEDIATE ; sous un lecteur tenu en journal
    DELETE, au commit — sort en `StoreV3Refuse` (REFUSÉ, `CAUSE_VERROU`, la BASE
    nommée, jamais la copie 1a), `_cli` en 4 sur UNE ligne, stdout vide ; la base
    reste INCHANGÉE (nuls, octets, annexes), la copie 1a aussi. PRÉCONDITION : la
    levée d'origine vient de la phase d'écriture (BEGIN IMMEDIATE ou commit), jamais
    de l'ouverture ni de la première lecture."""
    base = _re_semer(tmp_path / "base.db")
    argv = ["backfill", "--base", str(base)]
    copie = None
    if mode == "appliquer":
        copie = tmp_path / "copie.db"
        shutil.copyfile(base, copie)
        assert _re_cli(["backfill", "--base", str(copie)], capsys)[0] == 0, "amorce"
        argv += ["--appliquer-depuis", str(copie)]
    liberer = (_porteur_wal(base, request).liberer if verrou == "wal"
               else _re_lecteur_tenu(base, request))
    avant = (_empreinte(base), copie and _empreinte(copie))
    with _re_connexion_courte():
        with pytest.raises(StoreV3Refuse) as ei:
            run_export.backfill_historique(base=base, appliquer_depuis=copie)
        code, out, err = _re_cli(argv, capsys)
    exc = ei.value
    assert isinstance(exc.origine, sqlite3.OperationalError) and _code_primaire(exc.origine) == 5, (
        f"précondition : origine {type(exc.origine).__name__}: {exc.origine}")
    pile = [(trame.name, trame.line) for trame in traceback.extract_tb(exc.origine.__traceback__)]
    assert ("backfill_historique", VERROUS_ECRITURE[verrou]) in pile, (
        f"précondition : le verrou n'a pas mordu à la phase d'écriture ({verrou}) : {pile}")
    assert exc.origine is exc.__cause__, "origine et __cause__ divergent"
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, CAUSE_VERROU, base)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _re_une_ligne(err)
    assert f"{REFUSE} ({CAUSE_VERROU}) — {base} — OperationalError: " in ligne, ligne
    liberer()
    # Nuls, octets et copie 1a inchangés sont l'INVARIANT de SQLite sous verrou tenu
    # (mesuré, M1, M5, M6 du plan) : aucun mutant du code ne les fait rougir. Le
    # tueur de cette fin est Mut-13 (`finally: conn.close()` -> `pass`) : il rougit
    # [*-wal] par le `-wal` laissé (annexes), [*-delete] par le verrou que la
    # connexion non fermée tient encore à la relecture des nuls.
    assert _re_nuls(base) == 1, "nuls : une ligne frappée sous le verrou"
    assert _empreinte(base) == avant[0], "octets : la base a bougé sous le verrou"
    assert _annexes(base) == set(), "annexes : une annexe laissée derrière le refus"
    assert (copie and _empreinte(copie)) == avant[1], "la copie 1a a bougé"


def test_re_13_refus_a_la_phase_d_ecriture_aucune_ecriture_partielle(partition, tmp_path, monkeypatch):
    """ATOMICITÉ du bloc (d) (T-00001074, réserve A-C1) : sur un store de DEUX
    lignes, un code 5 SYNTHÉTIQUE levé au SECOND `UPDATE` sort en `StoreV3Refuse`
    (REFUSÉ, `CAUSE_VERROU`, la base) et la base reste INCHANGÉE — aucune des deux
    lignes frappée, octets identiques. Un store d'une ligne ne distingue pas un
    commit unique, dernière instruction du bloc, d'un commit par ligne (refus
    prononcé APRÈS une écriture partielle) : ce témoin, si (Mut-12)."""
    base = _re_semer(tmp_path / "deux.db", lignes=2)
    avant = _empreinte(base)
    vraie = sqlite3.connect
    vus: List[str] = []

    class _ConnSecondUpdate(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("UPDATE events_ledger"):
                vus.append(sql)
                if len(vus) == 2:
                    exc = sqlite3.OperationalError("database is locked (synthétique, second UPDATE)")
                    exc.sqlite_errorcode = 5
                    raise exc
            return super().execute(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(run_export.sqlite3, "connect", functools.partial(vraie, factory=_ConnSecondUpdate))
        with pytest.raises(StoreV3Refuse) as ei:
            run_export.backfill_historique(base=base)
    assert len(vus) == 2, f"précondition : la levée n'est pas au SECOND UPDATE ({len(vus)} vu(s))"
    exc = ei.value
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, CAUSE_VERROU, base)
    assert _re_nuls(base) == 2, "écriture PARTIELLE sous refus : une ligne frappée"
    assert _empreinte(base) == avant, "octets : la base a bougé sous le refus"


@pytest.mark.parametrize("mode", ("frapper", "appliquer"))
def test_re_12_lecture_seule_code_8_a_l_ecriture_une_ligne_code_4_base_inchangee(
        mode, partition, tmp_path, request, capsys):
    """T-00001078 RETOURNE `test_re_4_borne_lecture_seule_code_8_a_l_ecriture_remonte_brut`
    (T-00001074) : un store en LECTURE SEULE (`chmod 444`) s'ouvre et se lit, l'UPDATE lève le
    code 8 DANS le bloc (d) ; `classer_refus` le classant, il sort en `StoreV3Refuse` (REFUSÉ,
    `CAUSE_LECTURE_SEULE`, la BASE nommée, jamais la copie 1a), `_cli` en 4 sur UNE ligne, stdout
    vide ; octets et nuls inchangés, la copie 1a aussi. Les annexes `-wal`/`-shm` que SQLite laisse
    à côté d'un store en lecture seule ne sont PAS épinglées (reliquat mesuré hors processus,
    SUGGESTION hors write-set) : ni leur absence, ni leur présence."""
    _sauter_sans_droits_posix("chmod 444")
    base = _re_semer(tmp_path / "base.db")
    argv = ["backfill", "--base", str(base)]
    copie = None
    if mode == "appliquer":
        copie = tmp_path / "copie.db"
        shutil.copyfile(base, copie)
        assert _re_cli(["backfill", "--base", str(copie)], capsys)[0] == 0, "amorce"
        argv += ["--appliquer-depuis", str(copie)]
    os.chmod(base, 0o444)
    request.addfinalizer(lambda: os.chmod(base, 0o644))
    avant = (_empreinte(base), copie and _empreinte(copie))
    with pytest.raises(StoreV3Refuse) as ei:
        run_export.backfill_historique(base=base, appliquer_depuis=copie)
    code, out, err = _re_cli(argv, capsys)
    exc = ei.value
    assert isinstance(exc.origine, sqlite3.OperationalError) and _code_primaire(exc.origine) == 8, (
        f"précondition : origine {type(exc.origine).__name__}: {exc.origine}")
    pile = [(trame.name, trame.line) for trame in traceback.extract_tb(exc.origine.__traceback__)]
    assert ("backfill_historique", "conn.execute(") in pile, (
        f"précondition : le code 8 n'est pas levé à l'UPDATE : {pile}")
    assert exc.origine is exc.__cause__, "origine et __cause__ divergent"
    assert (exc.verdict, exc.cause, exc.chemin) == (REFUSE, CAUSE_LECTURE_SEULE, base)
    assert code == 4, f"code {code!r}, stderr {err!r}"
    assert out == ""
    ligne = _re_une_ligne(err)
    assert f"{REFUSE} ({CAUSE_LECTURE_SEULE}) — {base} — OperationalError: " in ligne, ligne
    assert (_re_nuls(base), _empreinte(base)) == (1, avant[0]), "la base a bougé"
    assert (copie and _empreinte(copie)) == avant[1], "la copie 1a a bougé"
