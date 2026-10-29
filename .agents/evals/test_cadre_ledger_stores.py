#!/usr/bin/env python3
"""BANCS DE LA CRÉATION DES TROIS STORES DE L'ADOPTANT — `cadre.ledger.stores`.

T-00000646 (décisions pilote S-00001590, S-00001591, S-00002138) : les trois
stores naissent par le CODE DE LA WHEEL (`cadre.ledger.stores_schemas`), et plus
par des modules producteurs chargés depuis la racine cible. Les témoins T1-T12 du
plan de la tâche vivent ici, sauf T6 (`test_cadre_ledger_purete.py`) et T7
(`test_cadre_no_inprocess_load.py`).

RÈGLE DES TÉMOINS (ticket T-00000625) : tout témoin prouve (a) une population NON
VIDE, (b) qu'elle vient de la SOURCE qu'il prétend lire, ET (c) qu'elle est
UTILISABLE — jamais l'un sans les deux autres. Aucun nombre attendu n'entre ici
sans avoir été OBTENU PAR EXÉCUTION (comptes lus par `PRAGMA` / `sqlite_master`
sur des fichiers RÉELS, jamais `:memory:`, jamais un chiffre déduit du code).

DEUX MONTAGES. `_racine_nue()` : une racine qui ne porte QUE `.agents/state/` —
ni `agentic_v3/` ni `.agents/bin/` — où la wheel doit tout créer seule.
`_batir_depot()` : un dépôt jetable portant les PRODUCTEURS du kit COPIÉS, qui
sert de RÉFÉRENCE aux parités (T2, T3) et aux usages (T8) — jamais de fournisseur
de code pour la création.

ISOLATION. Tout banc qui appelle `creer_les_stores` force `CADRE_PROJECT_ROOT` et
`CADRE_STATE_DIR` sur des tmp — par les montages `_racine_nue`/`_depot_isole`,
ou par `_etat_frere` quand il bâtit son dépôt à la main (`RacineDivergenteTests`)
— : résolution déterministe, aucune écriture sous le VRAI `state_home()`, sous
pytest COMME sous `unittest` nu (la fixture autouse n'est qu'un second filet).
Tout banc qui ouvre `event_store` fait résoudre son spool DANS le montage —
`AGENTS_EVENTS_DIR`/`AGENTS_OTEL_DIR` forcés (T2, T5), ou retirés sur une COPIE du
producteur qui résout alors depuis son `__file__` (T8) —, retire
`AGENTS_EVENTS_DB`, et le VÉRIFIE par une garde AVANT le premier appel : un banc a
déjà détruit le spool réel d'un poste (L-00000076).
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    # `agentic_v3.db.schema` (T3) est IMPORTÉ, jamais retapé.
    sys.path.append(str(ROOT))

_RESOLVEUR_SPEC = importlib.util.spec_from_file_location(
    "_stores_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
_RESOLVEUR = sys.modules[_RESOLVEUR_SPEC.name] = importlib.util.module_from_spec(_RESOLVEUR_SPEC)
_RESOLVEUR_SPEC.loader.exec_module(_RESOLVEUR)
_RESOLVEUR.charger_paquet(ROOT, "agentic_v3")
_RESOLVEUR.charger_paquet(ROOT, "cadre")  # vendor d'abord, puis `src/cadre`, sans `sys.path` (S-01M5BXT85V)

from cadre.init_surfaces import STORES  # noqa: E402
from cadre.ledger import schema, store, stores, stores_schemas, version  # noqa: E402
from cadre.paths import CadrePathError, index_db, state_home, state_project  # noqa: E402
from cadre.workspace import HorsRacine, Workspace  # noqa: E402
from agentic_v3.db import run_export as v3run  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolation_state_home(tmp_path, monkeypatch):
    """T-00000650, ÉCART NOMMÉ AU PLAN : `_creer_v3` écrit sous `state_project()`.
    Les montages ET `RacineDivergenteTests` (`_etat_frere`) posent leur propre
    `CADRE_STATE_DIR` depuis T-00000646 (F9) ; ce garde-fou reste le SECOND filet
    — sous pytest seulement — d'un banc futur qui l'oublierait : il redirige
    `CADRE_STATE_DIR` hors du vrai `state_home()` pour TOUT banc, et ceux qui
    posent le leur l'écrasent ensuite."""
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state_home"))

#: Producteurs copiés : `event_store` charge `events` et `otel_receiver` ; `migrate_index` charge `build_index`.
#: Le schéma V3 importe `run_export` et `cadre.ledger.store` depuis le paquet du banc, non sa copie.
#: Les producteurs copiés ouvrent `cadre.ledger.store` par le paquet : pas de `src/` dans le dépôt jetable.
_MODULES_BIN = ("event_store.py", "events.py", "otel_receiver.py",
                "migrate_index_to_db.py", "build_index.py")
_MODULE_V3 = (v3run._vendor_paths().dossier_paquet(v3run._racine_depot(), "agentic_v3") / "db/schema.py").relative_to(ROOT)

#: Le paquet copié SEUL par T9 — nommé ici pour qu'une mutation puisse pointer
#: une copie modifiée sans toucher à l'arbre.
_SRC_CADRE = _RESOLVEUR.exiger(ROOT, "cadre")

#: Un day-file de spool ANTÉRIEUR à aujourd'hui, posé dans le dépôt jetable et
#: dans l'arbre ÉTRANGER de SYM-8794 : si la création touchait un spool, ce
#: fichier bougerait.
_TRAP_NAME = "2020-01-01.trap.1.jsonl"
_TRAP_LINE = '{"ts":"2020-01-01T00:00:00Z","kind":"piege"}\n'

#: Entrées `sys.modules` que les producteurs posent PAR NOM : `build_index` par
#: `migrate_index_to_db`, `_store_events`/`_store_otel_receiver` par `event_store`.
_VOISINS_PAR_NOM = ("build_index", "_store_events", "_store_otel_receiver")

#: Le schéma v1 de `index.db`, FIGÉ — recopié de `V1_SCHEMA_SQL`
#: (`.agents/bin/test_migrate_index_to_db.py`) plutôt qu'importé : ce banc ne
#: charge pas les bancs du kit. C'est le passé par définition ; ne jamais
#: l'aligner sur une version plus récente. Sa clé `symbols_live_key` à TROIS
#: colonnes est ce que l'échelon v1 -> v2 doit retirer.
_INDEX_V1_SCHEMA = (
    "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE symbols("
    " id INTEGER PRIMARY KEY, path TEXT, name TEXT, kind TEXT,"
    " start INTEGER, \"end\" INTEGER,"
    " deleted INTEGER NOT NULL DEFAULT 0, generation TEXT)",
    "CREATE UNIQUE INDEX symbols_live_key"
    " ON symbols(path, name, kind) WHERE deleted = 0",
    "CREATE TABLE edges("
    " src_id INTEGER, dst_id INTEGER, PRIMARY KEY(src_id, dst_id))",
    "CREATE TABLE modules("
    " path TEXT PRIMARY KEY, role TEXT, depends_on TEXT, owner TEXT)",
    "CREATE TABLE annotations("
    " scope TEXT NOT NULL CHECK(scope IN ('symbol','module')), key TEXT NOT NULL,"
    " purpose TEXT, role TEXT, owner TEXT, PRIMARY KEY(scope, key))",
    "CREATE TABLE journal("
    " seq INTEGER PRIMARY KEY, at_sha TEXT, kind TEXT, payload TEXT)",
)

#: `events_ledger` d'un store V3 d'AVANT les colonnes d'idempotence
#: (T-00000629/T-00000650) — le « v0 ancien format » que les `ALTER` gardés de
#: `_ddl_v3` montent. Les cinq colonnes de `_V3_COLONNES_LEDGER` y manquent.
_V3_LEDGER_ANCIEN = (
    "CREATE TABLE events_ledger (event_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " task_id TEXT NOT NULL, agent_role TEXT NOT NULL, event_type TEXT NOT NULL,"
    " payload_json TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)


def _batir_depot() -> Path:
    """Un dépôt de l'adoptant jetable, avec les modules producteurs et un spool
    piège dans `.agents/state/events/`. Rend sa racine ABSOLUE."""
    cible = Path(tempfile.mkdtemp(prefix="cadre_stores_")).resolve()
    (cible / ".agents" / "bin").mkdir(parents=True)
    (cible / _MODULE_V3).parent.mkdir(parents=True)
    for nom in _MODULES_BIN:
        shutil.copy(ROOT / ".agents" / "bin" / nom, cible / ".agents" / "bin" / nom)
    shutil.copy(ROOT / _MODULE_V3, cible / _MODULE_V3)
    evdir = cible / ".agents" / "state" / "events"
    evdir.mkdir(parents=True)
    (evdir / _TRAP_NAME).write_text(_TRAP_LINE, encoding="utf-8")
    return cible


def _empreinte(dossier: Path) -> dict[str, str]:
    """Relevé OCTET POUR OCTET d'un arbre : `{chemin relatif -> sha256}`, plus la
    liste implicite des fichiers (les clés). Un `{}` pour un arbre absent."""
    if not dossier.is_dir():
        return {}
    out: dict[str, str] = {}
    for p in sorted(dossier.rglob("*")):
        if p.is_file():
            out[p.relative_to(dossier).as_posix()] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


def _noms(d: Path) -> set[str]:
    """Les NOMS d'un arbre, imbriqués compris (`exports/*/*.jsonl` est une source
    d'ingestion) ; dossier ABSENT = ensemble vide, jamais une levée — les deux
    dossiers de spool réels sont git-ignorés, donc absents d'un clone neuf."""
    return {p.relative_to(d).as_posix() for p in d.rglob("*")} if d.is_dir() else set()


def _sha(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _cookie(chemin: Path) -> int:
    """Le `schema_version` de SQLite LU DANS L'EN-TÊTE (4 octets gros-boutiens à
    l'offset 40), sans ouvrir de connexion — donc sans créer de `-wal`/`-shm`."""
    return int.from_bytes(chemin.read_bytes()[40:44], "big")


def _annexes(chemin: Path) -> list[str]:
    return [s for s in ("-wal", "-shm", "-journal")
            if Path(str(chemin) + s).exists()]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, str(chemin))
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def _charger_isole(nom: str, chemin: Path):
    """`_charger`, ENCADRÉ : `sys.path` et les entrées `sys.modules` des voisins
    chargés par nom sont RESTAURÉS après — le module chargé garde SON voisin, le
    processus ne garde rien d'une copie jetable. Hygiène que l'ancien
    `stores._charger` portait, désormais au banc seul (la wheel ne charge plus)."""
    sauve_path = list(sys.path)
    sauve_mods = {n: sys.modules.get(n) for n in _VOISINS_PAR_NOM}
    try:
        return _charger(nom, chemin)
    finally:
        sys.path[:] = sauve_path
        for n, ancien in sauve_mods.items():
            if ancien is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = ancien


def _objets(conn) -> set[str]:
    """Noms des tables/index RÉELS (hors internes `sqlite_%`), LUS PAR EXÉCUTION."""
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index') "
        "AND name NOT LIKE 'sqlite_%'")}


def _forme(chemin: Path) -> dict:
    """La FORME d'un store, lue par exécution : `sqlite_master` (texte `sql`
    compris, hors `rootpage`), colonnes de chaque table, `user_version`, journal,
    et les lignes `meta` quand la table existe."""
    conn = sqlite3.connect(str(chemin))
    try:
        maitre = sorted(tuple(r) for r in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%'"))
        colonnes = {nom: [tuple(r) for r in conn.execute(
                        "SELECT * FROM pragma_table_info(?)", (nom,))]
                    for typ, nom, _t, _s in maitre if typ == "table"}
        forme = {
            "sqlite_master": maitre,
            "table_info": colonnes,
            "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        }
        if "meta" in colonnes:
            forme["meta"] = sorted(tuple(r) for r in conn.execute(
                "SELECT key, value FROM meta"))
        return forme
    finally:
        conn.close()


def _poser_store_du_futur(nom: str, chemin: Path) -> None:
    """Un store que la wheel doit REFUSER : version déclarée UN CRAN au-delà de
    la sienne (`user_version` pour v3/events, `meta.schema_version` pour index)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(chemin))
    try:
        if nom == "index":
            conn.execute("CREATE TABLE symbols(id INTEGER PRIMARY KEY)")
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                         (str(stores_schemas.INDEX_SCHEMA_VERSION + 1),))
        else:
            futur = {"v3_event_store": stores_schemas.V3_USER_VERSION,
                     "events": stores_schemas.EVENTS_USER_VERSION}[nom] + 1
            conn.execute("CREATE TABLE t(x)")
            # PRAGMA sans paramètre lié : entier du banc, forcé par int().
            pragma = "PRAGMA user_version = " + str(int(futur))
            conn.execute(pragma)
        conn.commit()
    finally:
        conn.close()


def _poser_verrou_de_maintenance(racine: Path, age: float = 0.0) -> Path:
    """Le `.maintenance.lock` d'`events.py`, à SON emplacement par défaut
    (`_events_dir() / _MAINTENANCE_LOCK_NAME` — parité tenue par
    `VerrouDeMaintenanceTests`), posé comme lui le pose : un fichier créé, rien
    d'autre (`O_CREAT|O_EXCL`). `age` > 0 l'antidate (`os.utime`)."""
    verrou = racine / ".agents" / "state" / "events" / ".maintenance.lock"
    verrou.parent.mkdir(parents=True, exist_ok=True)
    verrou.write_bytes(b"")
    if age:
        passe = time.time() - age
        os.utime(verrou, (passe, passe))
    return verrou


def _en_parallele(n: int, cible) -> list[str]:
    """`cible(rang)` dans `n` fils RÉELS ; rend les levées `Type: message`, et
    un fil encore vivant après 60 s compte comme une levée (jamais un banc
    pendu en silence)."""
    erreurs: list[str] = []

    def corps(rang: int) -> None:
        try:
            cible(rang)
        except Exception as exc:  # noqa: BLE001 — le banc COMPTE toute levée
            erreurs.append(f"{type(exc).__name__}: {exc}")

    fils = [threading.Thread(target=corps, args=(r,), daemon=True) for r in range(n)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=60)
    erreurs.extend(f"fil {i} bloqué au-delà de 60 s"
                   for i, f in enumerate(fils) if f.is_alive())
    return erreurs


class _EnvMixin(unittest.TestCase):
    def _forcer_env(self, **kv):
        """Pose (ou retire si valeur `None`) des variables d'environnement, et
        enregistre leur restauration — sans pytest, on gère l'état à la main."""
        for cle, val in kv.items():
            ancienne = os.environ.get(cle)
            self.addCleanup(self._restaurer, cle, ancienne)
            if val is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = val

    @staticmethod
    def _restaurer(cle, ancienne):
        if ancienne is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = ancienne

    def _producteur(self, nom: str, chemin: Path):
        """Un producteur chargé par `_charger_isole`, son entrée `sys.modules`
        retirée au nettoyage."""
        self.addCleanup(sys.modules.pop, nom, None)
        return _charger_isole(nom, chemin)

    def _etat_frere(self, racine: Path) -> Path:
        """`CADRE_STATE_DIR` forcé sur un dossier FRÈRE et unique de `racine`,
        retiré au nettoyage — le patron de `_depot_isole`, pour un banc qui bâtit
        son dépôt à la main (F9). Rend le dossier, ABSENT tant que rien n'y
        écrit : c'est l'état machine que ces bancs relèvent."""
        etat = racine.parent / (racine.name + "_state")
        self.addCleanup(shutil.rmtree, etat, ignore_errors=True)
        self._forcer_env(CADRE_STATE_DIR=str(etat))
        return etat

    def _partition_reelle_de(self, cible: Path) -> Path:
        """Le `state_project(cible)` RÉEL (CONSTAT 5) — la partition MACHINE où le
        store V3 ATTERRIRAIT si la résolution de partition ignorait `CADRE_STATE_DIR`
        (isolation contournée). `CADRE_STATE_DIR`/`XDG_STATE_HOME` retirés le temps
        de la résoudre. Ce relevé DÉTECTE une fuite là où la fixture autouse
        `_isolation_state_home` ne fait que la PRÉVENIR.

        ÉCART NOMMÉ AU BRIEF (CONSTAT 5) : le brief prescrivait un relevé de l'ARBRE
        ENTIER de `state_home()` (modèle `test_run_export.py:299-305`). MESURÉ sur ce
        poste : le `state_home()` réel est écrit EN CONTINU par la session (hooks,
        `tasks.py`), donc un before/after de l'arbre entier FLOTTE — il a rougi deux
        fois sur une écriture concurrente SANS fuite. On SCOPE donc au hash de
        `cible` : une fuite atterrit sous CETTE partition, l'activité concurrente
        sous d'AUTRES — la détection est conservée, la flakerie éliminée."""
        sauve = {c: os.environ.get(c) for c in ("CADRE_STATE_DIR", "XDG_STATE_HOME")}
        for cle in sauve:
            os.environ.pop(cle, None)
        try:
            return state_project(cible)  # ne crée rien sur le disque (paths.py:193)
        finally:
            for cle, val in sauve.items():
                if val is not None:
                    os.environ[cle] = val

    def _liste_partitions_reelles(self) -> set:
        """MINEUR 9 (binôme) : la LISTE des partitions sous la VRAIE `state_home()`.
        Le relevé scopé à la partition de la CIBLE (`_partition_reelle_de`) ne voit
        pas une fuite atterrissant sous la partition d'une racine AUTRE que la cible.
        La liste ne bouge pas pendant une session ; une partition neuve est une
        fuite. Coût de fausse alerte NUL : on relève des NOMS de dossiers, pas leur
        contenu."""
        sauve = {c: os.environ.get(c) for c in ("CADRE_STATE_DIR", "XDG_STATE_HOME")}
        for cle in sauve:
            os.environ.pop(cle, None)
        try:
            projets = state_home() / "projets"
            return {p.name for p in projets.iterdir()} if projets.is_dir() else set()
        finally:
            for cle, val in sauve.items():
                if val is not None:
                    os.environ[cle] = val

    def _depot_isole(self) -> Path:
        cible = _batir_depot()
        self.addCleanup(shutil.rmtree, cible, ignore_errors=True)
        # T-00000650 : `_creer_v3` écrit SOUS `state_project()` (partition MACHINE),
        # donc on FORCE `CADRE_STATE_DIR` sur un dossier FRÈRE et unique du
        # tempdir — sans quoi la création écrirait sous le VRAI `state_home()` à
        # chaque porte, sur chaque poste et en CI. ÉCART NOMMÉ AU PLAN : le plan
        # écrit `cible.parent / "state"` (soit `/tmp/state`, PARTAGÉ) ; on l'unicise
        # par le nom du tempdir pour éviter la collision inter-tests.
        state_dir = cible.parent / (cible.name + "_state")
        self.addCleanup(shutil.rmtree, state_dir, ignore_errors=True)
        # `AGENTS_OTEL_DIR` retiré AUSSI (F9) : la COPIE résout alors son otel
        # depuis son `__file__`, dans la cible — la garde de T8 le vérifie.
        self._forcer_env(AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None,
                         AGENTS_OTEL_DIR=None,
                         CADRE_PROJECT_ROOT=str(cible),
                         CADRE_STATE_DIR=str(state_dir))
        return cible

    def _racine_nue(self) -> Path:
        """Une racine qui ne porte QUE `.agents/state/` — aucun code. R4 du plan :
        `CADRE_PROJECT_ROOT` ET `CADRE_STATE_DIR` (frère unique du tempdir) sont
        forcés par `_forcer_env`, sur le patron de `_depot_isole` — sans quoi un
        shell qui exporte `CADRE_PROJECT_ROOT` ferait rougir tout banc monté ici,
        et un `unittest` nu écrirait le store V3 sous le VRAI `state_home()`. Les
        variables `AGENTS_EVENTS_*`/`AGENTS_OTEL_DIR` sont RETIRÉES : la wheel ne
        les lit pas, et ce montage le prouve."""
        racine = Path(tempfile.mkdtemp(prefix="cadre_nue_")).resolve()
        self.addCleanup(shutil.rmtree, racine, ignore_errors=True)
        (racine / ".agents" / "state").mkdir(parents=True)
        state_dir = racine.parent / (racine.name + "_state")
        self.addCleanup(shutil.rmtree, state_dir, ignore_errors=True)
        self._forcer_env(AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None,
                         AGENTS_OTEL_DIR=None,
                         CADRE_PROJECT_ROOT=str(racine),
                         CADRE_STATE_DIR=str(state_dir))
        return racine


class CreationParLaWheelTests(_EnvMixin):
    """T1 — une racine NUE (aucun `.py` producteur) reçoit les trois stores."""

    def test_une_racine_NUE_cree_les_trois_stores(self):
        racine = self._racine_nue()
        # Non-vacuité du montage : la racine ne porte AUCUN code producteur.
        self.assertEqual(sorted(p.name for p in racine.iterdir()), [".agents"])
        self.assertEqual(sorted(p.name for p in (racine / ".agents").iterdir()),
                         ["state"])

        res = stores.creer_les_stores(racine)

        attendus = {
            "v3_event_store": (stores_schemas.V3_USER_VERSION, "wal"),
            "events": (stores_schemas.EVENTS_USER_VERSION, "wal"),
            "index": (0, "delete"),
        }
        for nom, (user_version, journal) in attendus.items():
            chemin = getattr(res, nom)
            with self.subTest(store=nom):
                self.assertTrue(chemin.is_file(), f"store non créé : {chemin}")
                self.assertGreater(chemin.stat().st_size, 0,
                                   f"store de 0 octet — aucun schéma posé : {chemin}")
                forme = _forme(chemin)
                self.assertTrue(forme["sqlite_master"], f"aucune table dans {chemin}")
                self.assertEqual(forme["user_version"], user_version)
                self.assertEqual(forme["journal_mode"], journal)
        self.assertIn(("schema_version", str(stores_schemas.INDEX_SCHEMA_VERSION)),
                      _forme(res.index)["meta"])
        # Où ils naissent : v3 ET index HORS dépôt (partition machine — T-00000650,
        # T-00000668), events seul dedans.
        partition = state_project(racine).resolve()
        for chemin in (res.v3_event_store, res.index):
            self.assertTrue(chemin.is_relative_to(partition),
                            f"store hors de la partition MACHINE : {chemin}")
            self.assertFalse(chemin.is_relative_to(racine), f"store DANS le dépôt : {chemin}")
        self.assertTrue(res.events.is_relative_to(racine), f"hors racine : {res.events}")


class PariteDesSchemasTests(_EnvMixin):
    """T2 — la wheel produit EXACTEMENT la forme des producteurs du kit : seconde
    définition des schémas ASSUMÉE (S-00001592), tenue ici à chaque porte.

    Les deux côtés sont des stores NEUFS : aucun ALTER ne joue d'aucun côté (le
    `CREATE` de chaque producteur porte déjà la forme finale ; les échelons de
    l'index ne sont exercés que par T12)."""

    def test_la_wheel_produit_la_forme_des_producteurs(self):
        racine = self._racine_nue()
        cote_wheel = stores.creer_les_stores(racine)

        depot = _batir_depot()
        self.addCleanup(shutil.rmtree, depot, ignore_errors=True)
        spool = depot / ".agents" / "state" / "events"
        otel = depot / ".agents" / "state" / "local" / "otel"
        self._forcer_env(AGENTS_EVENTS_DIR=str(spool), AGENTS_OTEL_DIR=str(otel),
                         AGENTS_EVENTS_DB=None)
        v3 = self._producteur("_t2_v3_schema", depot / _MODULE_V3)
        es = self._producteur("_t2_event_store", depot / ".agents/bin/event_store.py")
        mi = self._producteur("_t2_migrate_index",
                              depot / ".agents/bin/migrate_index_to_db.py")
        # GARDE avant tout appel au producteur events (L-00000076).
        self.assertEqual(es._events_dir(), spool)
        self.assertEqual(es._otel_dir(), otel)

        cote_producteurs = depot / "producteurs"
        v3.create_tables(str(cote_producteurs / "v3_event_store.db"))
        handle = es.open_store(cote_producteurs / "events.db", create=True)
        try:
            self.assertEqual(handle.status, "ok", handle.degraded_reason() or "")
        finally:
            handle.close()
        # T-00000668 : `mi.db_path` refuse une racine que l'environnement fait
        # diverger — `_racine_nue` a forcé `$CADRE_PROJECT_ROOT` sur la racine de la
        # WHEEL. Le côté producteurs nomme donc SA racine ; `$CADRE_STATE_DIR`
        # (isolé par `_racine_nue`) reste en place, l'index producteur naît sous
        # la partition machine isolée de `cote_producteurs`.
        self._forcer_env(CADRE_PROJECT_ROOT=str(cote_producteurs))
        with contextlib.redirect_stdout(io.StringIO()):
            mi.run_apply(cote_producteurs, mi.State(root=cote_producteurs))
        paires = {
            "v3_event_store": (cote_wheel.v3_event_store,
                               cote_producteurs / "v3_event_store.db"),
            "events": (cote_wheel.events, cote_producteurs / "events.db"),
            "index": (cote_wheel.index, mi.db_path(cote_producteurs)),
        }
        for nom, (wheel, producteur) in paires.items():
            with self.subTest(store=nom):
                forme_wheel, forme_producteur = _forme(wheel), _forme(producteur)
                self.assertGreaterEqual(len(forme_producteur["sqlite_master"]), 5,
                                        "producteur sans schéma — banc non armé")
                self.assertEqual(forme_wheel, forme_producteur,
                                 f"la wheel diverge du producteur pour {nom}")

        # Versions et échelles : les constantes de la wheel sont CELLES des producteurs.
        self.assertEqual(stores_schemas.V3_USER_VERSION, v3.SCHEMA_VERSION)
        self.assertEqual(stores_schemas.EVENTS_USER_VERSION, es.SCHEMA_VERSION)
        self.assertEqual(stores_schemas.INDEX_SCHEMA_VERSION, mi.SCHEMA_VERSION)
        self.assertEqual(set(stores_schemas.ECHELONS_INDEX), set(mi.SCHEMA_UPGRADES))
        self.assertEqual(set(stores_schemas.ECHELONS_EVENTS), set(es._MIGRATIONS))


class PariteDesCheminsTests(_EnvMixin):
    """T3 — `chemins_des_stores` rend les MÊMES chemins que les résolveurs des
    producteurs, sans rien écrire."""

    def test_chemins_des_stores_egale_les_resolveurs_des_producteurs(self):
        from agentic_v3.db.schema import DEFAULT_DB_PATH  # noqa: PLC0415

        # `_depot_isole` retire AGENTS_EVENTS_DIR ET AGENTS_EVENTS_DB : `events`,
        # chargé depuis la COPIE, résout alors depuis son `__file__` (sans le
        # retrait d'AGENTS_EVENTS_DB, l'override court-circuiterait `__file__`).
        cible = self._depot_isole()
        mi = self._producteur("_t3_migrate_index",
                              cible / ".agents/bin/migrate_index_to_db.py")
        ev = self._producteur("_t3_events", cible / ".agents/bin/events.py")

        chemins = stores.chemins_des_stores(cible)

        self.assertEqual(chemins.index, mi.db_path(cible))
        self.assertEqual(chemins.events, ev.events_db_path())
        self.assertEqual(chemins.v3_event_store, DEFAULT_DB_PATH(cible))
        # Non-vacuité : les résolveurs visent bien la copie, pas le kit.
        self.assertTrue(ev.events_db_path().is_relative_to(cible))
        # PUR : rien n'a été créé.
        for chemin in (chemins.v3_event_store, chemins.events, chemins.index):
            self.assertFalse(chemin.exists(), f"chemins_des_stores a écrit {chemin}")


class IdempotenceTests(_EnvMixin):
    """T4 — un rejeu ne change ni un octet ni le cookie de schéma."""

    def test_un_rejeu_ne_change_ni_octet_ni_cookie(self):
        racine = self._racine_nue()
        res = stores.creer_les_stores(racine)
        trois = (res.v3_event_store, res.events, res.index)
        avant = {p: (_sha(p), _cookie(p)) for p in trois}
        for p in trois:
            self.assertGreater(_cookie(p), 0, f"aucun schéma posé dans {p}")
            self.assertEqual(_annexes(p), [], f"fichier annexe résiduel : {p}")

        res2 = stores.creer_les_stores(racine)

        self.assertEqual(res2, res)
        for p in trois:
            with self.subTest(store=p.name):
                self.assertEqual(_annexes(p), [], f"fichier annexe résiduel : {p}")
                self.assertEqual((_sha(p), _cookie(p)), avant[p],
                                 f"le rejeu a changé {p.name}")


class SpoolTests(_EnvMixin):
    """T5 — un `events.db` né par la wheel ne perd AUCUNE garantie anti-double
    comptage : le tick normal du démon n'ingère qu'UNE fois un triangle
    préexistant (fichier fusionné + résidu par écrivain d'un jour passé).

    ORDRE DU CORPS, IMPOSÉ (la sûreté de ce témoin tient à cette discipline,
    qu'aucune garde mécanique n'impose) : (1) `_forcer_env` ; (2) garde sur les
    trois résolveurs ; (3) `creer_les_stores` ; (4) `open_store` ; (5) relevé
    `avant` du spool RÉEL, JUSTE avant le tick (R1) ; (6) `ingest_once` ; (7)
    asserts positifs ; (8) assert négatif. La garde est le VRAI témoin : elle
    échoue AVANT tout dommage. L'assert négatif est un filet SECONDAIRE : il
    constate après le tick et ne voit que des NOMS."""

    def test_un_triangle_preexistant_n_est_ingere_qu_une_fois_apres_creation_par_la_wheel(self):
        racine = self._racine_nue()
        spool = racine / ".agents" / "state" / "events"
        spool.mkdir(parents=True)
        n = 5
        lignes = "".join('{"ts":"2020-01-01T00:00:0%dZ","kind":"t5","n":%d}\n' % (i, i)
                         for i in range(n))
        fusionne = spool / "2020-01-01.merged.jsonl"
        residu = spool / "2020-01-01.hostA.pid1.jsonl"
        fusionne.write_text(lignes, encoding="utf-8")
        residu.write_text(lignes, encoding="utf-8")

        # (1) ISOLATION — le spool et le store du tick visent la racine jetable.
        self._forcer_env(AGENTS_EVENTS_DIR=str(racine / ".agents/state/events"),
                         AGENTS_OTEL_DIR=str(racine / ".agents/state/local/otel"),
                         AGENTS_EVENTS_DB=None)
        es = self._producteur("_t5_event_store", ROOT / ".agents/bin/event_store.py")
        # (2) GARDE — AVANT `open_store`, qui sans env résoudrait le `events.db` réel.
        self.assertEqual(es._events_dir(), racine / ".agents/state/events")
        self.assertEqual(es._otel_dir(), racine / ".agents/state/local/otel")
        self.assertEqual(es._events_mod.events_db_path(),
                         racine / ".agents/state/local/events.db")

        # (3) CRÉATION par la wheel — le spool n'est ni lu ni touché.
        res = stores.creer_les_stores(racine)
        self.assertTrue(fusionne.exists() and residu.exists(),
                        "la création a touché le spool")
        # (4) OUVERTURE par le producteur, sur le store né par la wheel.
        handle = es.open_store(create=False)
        self.addCleanup(handle.close)
        self.assertEqual(handle.status, "ok", handle.degraded_reason() or "")
        self.assertEqual(handle.path, res.events)

        # (5) RELEVÉ du spool RÉEL, JUSTE avant le tick. Variables dérivées de
        # ROOT, et d'elles seules.
        # adopting-tree: spool git-ignoré, absent chez l'adoptant ; `_noms` y rend {} et l'inclusion tient — relevé de sûreté, jamais une exigence de présence.
        spool_reel_events = ROOT / ".agents" / "state" / "events"
        spool_reel_otel = ROOT / ".agents" / "state" / "local" / "otel"
        avant_ev = _noms(spool_reel_events)
        avant_ot = _noms(spool_reel_otel)

        # (6) LE TICK
        rep = handle.ingest_once(datetime.now(timezone.utc))

        # (7) POSITIFS — une seule ingestion, le résidu reconnu et retiré.
        self.assertIsNone(rep["error"], rep["error"])
        self.assertEqual(rep["rows_inserted"], n,
                         "le triangle a été compté deux fois (ou pas du tout)")
        self.assertEqual(rep["residue_skipped"], 1)
        self.assertFalse(residu.exists(), "le résidu n'a pas été retiré")

        # (8) NÉGATIF — aucun fichier du spool RÉEL n'a disparu. INCLUSION
        # d'ensembles : un hook concurrent peut en CRÉER pendant le test, le tick
        # jamais. BORNE (R1) : un dashboard en cours (`dashboard.lock`) supprime
        # légitimement des fichiers du spool réel — rouge possible sans faute du
        # test ; la garde pré-`open_store` reste le témoin.
        self.assertLessEqual(avant_ev, _noms(spool_reel_events),
                             "un fichier du spool RÉEL a DISPARU pendant le tick")
        self.assertLessEqual(avant_ot, _noms(spool_reel_otel),
                             "un fichier du spool otel RÉEL a DISPARU pendant le tick")


class PaquetSeulTests(_EnvMixin):
    """T9 — TÉMOIN DU TICKET. `src/cadre/` COPIÉ SEUL, sans `agentic_v3/` ni
    `.agents/bin/`, sous `python -I -S` (ni `PYTHON*`, ni cwd, ni site-packages :
    une installation éditable ne peut masquer une dépendance non déclarée), crée
    les trois stores. BORNE : prouve l'autonomie de `src/cadre/`, pas le contenu
    d'une wheel construite (`check_wheel_contents`, prévu)."""

    def test_le_paquet_copie_SEUL_cree_les_trois_stores(self):
        racine = self._racine_nue()
        tmp = Path(tempfile.mkdtemp(prefix="cadre_paquet_seul_")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(_SRC_CADRE, tmp / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__"))
        # `sys.path.insert` vit dans le snippet du BANC, jamais dans `src/cadre/`.
        snippet = (
            "import sys\n"
            f"sys.path.insert(0, {str(tmp)!r})\n"
            "from cadre.ledger import stores\n"
            f"r = stores.creer_les_stores({str(racine)!r})\n"
            "print(stores.__file__)\n"
            "print(sorted(n for n in sys.modules if n.split('.')[0] in "
            "('agentic_v3', 'event_store', 'events', 'migrate_index_to_db', "
            "'build_index')))\n"
            "for p in (r.v3_event_store, r.events, r.index):\n"
            "    print(p)\n"
        )
        proc = subprocess.run([sys.executable, "-I", "-S", "-c", snippet],
                              cwd=str(tmp), env=dict(os.environ),
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        sortie = proc.stdout.splitlines()
        self.assertTrue(Path(sortie[0]).resolve().is_relative_to(tmp),
                        f"le paquet chargé n'est pas la COPIE : {sortie[0]}")
        self.assertEqual(sortie[1], "[]", "un module producteur a été chargé")
        self.assertEqual(len(sortie[2:]), 3)
        for ligne in sortie[2:]:
            self.assertTrue(Path(ligne).is_file(), f"store non créé : {ligne}")
            self.assertGreater(Path(ligne).stat().st_size, 0, ligne)


class RefusTests(_EnvMixin):
    """T10, T11 — un store existant que la wheel ne sait pas porter est REFUSÉ
    par la SONDE, AVANT qu'aucun des trois ne soit écrit."""

    def test_un_store_du_futur_est_refuse_sans_rien_ecrire(self):
        noms = ("v3_event_store", "events", "index")
        for nom in noms:
            with self.subTest(store=nom):
                racine = self._racine_nue()
                chemins = stores.chemins_des_stores(racine)
                futur = getattr(chemins, nom)
                _poser_store_du_futur(nom, futur)
                sha_avant = _sha(futur)

                with self.assertRaises(CadrePathError) as ctx:
                    stores.creer_les_stores(racine)

                self.assertIn("PLUS RÉCENT", str(ctx.exception))
                self.assertEqual(_sha(futur), sha_avant, "le store du futur a été touché")
                self.assertEqual(_annexes(futur), [])
                for autre in noms:
                    if autre != nom:
                        self.assertFalse(getattr(chemins, autre).exists(),
                                         f"{autre} créé malgré le refus de {nom}")

    def test_un_index_sans_version_est_etranger(self):
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        chemins.index.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(chemins.index))
        try:
            conn.execute("CREATE TABLE symbols(id INTEGER PRIMARY KEY, path TEXT)")
            conn.commit()
        finally:
            conn.close()
        sha_avant = _sha(chemins.index)

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        self.assertIn("étranger", str(ctx.exception))
        self.assertEqual(_sha(chemins.index), sha_avant, "l'index étranger a été touché")
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")
        self.assertFalse(chemins.events.exists(), "events créé malgré le refus")

    def test_une_version_du_futur_dans_le_WAL_SEUL_est_refusee_a_la_sonde(self):
        """F2 (critic-opus) / MAJEUR 1 (exec-critic) : la sonde LIT LE WAL. Un
        écrivain TENANT (`wal_autocheckpoint=0`, connexion gardée ouverte) a
        tamponné `events.db` un cran au-delà de la wheel ; la version n'existe
        que dans le WAL. La sonde en `immutable=1` y lisait 0, laissait passer,
        et v3 naissait avant que la re-sonde ne refuse : création partielle."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        chemins.events.parent.mkdir(parents=True)
        tenant = sqlite3.connect(str(chemins.events), isolation_level=None)
        self.addCleanup(tenant.close)
        self.assertEqual(tenant.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        tenant.execute("PRAGMA wal_autocheckpoint=0")
        futur = stores_schemas.EVENTS_USER_VERSION + 1
        # PRAGMA sans paramètre lié : entier du banc, forcé par int().
        tenant.execute("PRAGMA user_version = " + str(int(futur)))
        # ARMEMENT : la version du futur vit dans le WAL SEUL — une lecture qui
        # ignore le WAL y lit encore 0.
        immuable = store.connect(chemins.events, lecture_seule=True)
        try:
            self.assertEqual(immuable.execute("PRAGMA user_version").fetchone()[0], 0,
                             "banc non armé : la version a atteint le fichier principal")
        finally:
            immuable.close()

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        self.assertIn("PLUS RÉCENT", str(ctx.exception))
        self.assertFalse(chemins.v3_event_store.exists(),
                         "v3 créé AVANT le refus d'events : la sonde a ignoré le WAL")
        self.assertFalse(chemins.index.exists(), "index créé malgré le refus")

    def test_un_fichier_non_SQLite_est_refuse_sans_rien_ecrire(self):
        """F3 (critic-opus) / MAJEUR 2 (exec-critic) / T4 (critic-fable) : un
        fichier qui n'est pas une base SQLite, à l'emplacement de CHAQUE store,
        lève `CadrePathError` — jamais une `sqlite3.DatabaseError` brute — et
        n'est pas touché ; les deux autres stores ne naissent pas."""
        noms = ("v3_event_store", "events", "index")
        for nom in noms:
            with self.subTest(store=nom):
                racine = self._racine_nue()
                chemins = stores.chemins_des_stores(racine)
                cible = getattr(chemins, nom)
                cible.parent.mkdir(parents=True, exist_ok=True)
                cible.write_bytes(b"ceci n'est pas une base SQLite\n" * 40)
                sha_avant = _sha(cible)

                with self.assertRaises(CadrePathError) as ctx:
                    stores.creer_les_stores(racine)

                self.assertIn("DatabaseError", str(ctx.exception))
                self.assertEqual(_sha(cible), sha_avant, f"{nom} non-SQLite touché")
                self.assertEqual(_annexes(cible), [])
                for autre in noms:
                    if autre != nom:
                        self.assertFalse(getattr(chemins, autre).exists(),
                                         f"{autre} créé malgré le refus de {nom}")


class MonteeIndexTests(_EnvMixin):
    """T12 — un `index.db` v2 est MONTÉ en v3 par l'échelle de la wheel, sans
    perte : symboles, `watermark` d'équipe et autres lignes `meta` préservés."""

    def test_un_index_v2_est_monte_en_v3_sans_perte(self):
        if sqlite3.sqlite_version_info < (3, 35, 0):
            self.skipTest("ALTER TABLE … DROP COLUMN exige SQLite >= 3.35 pour "
                          "fabriquer l'index v2")
        racine = self._racine_nue()
        res = stores.creer_les_stores(racine)
        # Fabrique un v2 : `body_sha` retiré, version 2 déclarée, contenu d'équipe.
        conn = sqlite3.connect(str(res.index))
        try:
            conn.execute("ALTER TABLE symbols DROP COLUMN body_sha")
            conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
            conn.execute("UPDATE meta SET value = '42' WHERE key = 'watermark'")
            conn.execute("INSERT INTO symbols(id, path, name, kind, start, \"end\","
                         " deleted, generation, ordinal)"
                         " VALUES(7, 'a.py', 'f', 'function', 1, 2, 0, 'g1', 0)")
            conn.commit()
            colonnes_v2 = {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}
        finally:
            conn.close()
        self.assertNotIn("body_sha", colonnes_v2, "fixture v2 non armée")

        stores.creer_les_stores(racine)

        conn = sqlite3.connect(str(res.index))
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            colonnes = {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}
            ligne = conn.execute(
                "SELECT path, name, kind, generation, body_sha FROM symbols"
                " WHERE id = 7").fetchone()
        finally:
            conn.close()
        self.assertEqual(meta["schema_version"], str(stores_schemas.INDEX_SCHEMA_VERSION))
        self.assertIn("body_sha", colonnes)
        self.assertEqual(meta["watermark"], "42", "le watermark d'équipe a été réécrit")
        self.assertEqual(ligne, ("a.py", "f", "function", "g1", None),
                         "le symbole d'équipe a été perdu ou altéré")

    def test_un_index_v1_avec_FTS_monte_a_la_forme_du_producteur(self):
        """F11 (critic-opus) / BLIND SPOT (exec-critic) : l'échelon v1 -> v2
        n'avait aucun témoin — retirer son `DROP INDEX` laissait le banc vert.
        Un v1 RÉEL (schéma figé + `symbols_fts`, contenu d'équipe) est copié deux
        fois : l'une montée par `garantir_index`, l'autre par le producteur
        (`upgrade_schema` puis `ensure_schema`, l'ordre qu'il prescrit). Les
        deux FORMES doivent être égales, meta comprise. Témoin de COUVERTURE :
        vert sur l'état antérieur (l'échelon y était juste), rouge par mutation."""
        sonde = sqlite3.connect(":memory:")
        try:
            sonde.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        except sqlite3.OperationalError:
            self.skipTest("FTS5 absent de cet interpréteur : la fixture v1 le porte")
        finally:
            sonde.close()
        self._racine_nue()  # isolation de l'environnement ; aucun store créé ici
        tmp = Path(tempfile.mkdtemp(prefix="cadre_index_v1_")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        v1 = tmp / "v1.db"
        conn = sqlite3.connect(str(v1))
        try:
            for ddl in _INDEX_V1_SCHEMA:
                conn.execute(ddl)
            conn.execute("CREATE VIRTUAL TABLE symbols_fts USING fts5(name, path, purpose)")
            conn.executemany("INSERT INTO meta(key, value) VALUES(?, ?)",
                             (("schema_version", "1"), ("built_at_sha", "abc"),
                              ("watermark", "7")))
            conn.execute("INSERT INTO symbols(id, path, name, kind, start, \"end\","
                         " deleted, generation) VALUES(1, 'a.py', 'f', 'function',"
                         " 1, 2, 0, 'g1')")
            conn.commit()
        finally:
            conn.close()
        forme_v1 = _forme(v1)
        noms_v1 = {nom for _t, nom, _tb, _s in forme_v1["sqlite_master"]}
        self.assertIn("symbols_live_key", noms_v1, "fixture v1 non armée")
        self.assertIn("symbols_fts", noms_v1, "fixture v1 sans FTS")
        self.assertIn(("schema_version", "1"), forme_v1["meta"])
        cote_wheel, cote_producteur = tmp / "wheel.db", tmp / "producteur.db"
        shutil.copy(v1, cote_wheel)
        shutil.copy(v1, cote_producteur)

        conn = store.connect(cote_wheel)
        try:
            stores_schemas.garantir_index(conn)
        finally:
            conn.close()
        depot = _batir_depot()
        self.addCleanup(shutil.rmtree, depot, ignore_errors=True)
        mi = self._producteur("_t11_migrate_index",
                              depot / ".agents/bin/migrate_index_to_db.py")
        conn = mi.connect(cote_producteur)
        try:
            self.assertIsNotNone(mi.upgrade_schema(conn), "le producteur n'a rien monté")
            mi.ensure_schema(conn)
        finally:
            conn.close()

        forme_wheel, forme_producteur = _forme(cote_wheel), _forme(cote_producteur)
        noms_wheel = {nom for _t, nom, _tb, _s in forme_wheel["sqlite_master"]}
        self.assertNotIn("symbols_live_key", noms_wheel,
                         "la clé v1 à trois colonnes a survécu à la montée")
        self.assertIn(("schema_version", str(stores_schemas.INDEX_SCHEMA_VERSION)),
                      forme_wheel["meta"])
        self.assertEqual(forme_wheel, forme_producteur,
                         "la montée v1 de la wheel diverge de celle du producteur")


class ConfinementSpoolTests(_EnvMixin):
    """B-C1 : la création ne touche RIEN hors de sa racine — ni un arbre étranger
    frère, ni le `git status` du vrai dépôt, ni la partition machine RÉELLE. Le
    spool (étranger comme local) n'est plus lu par la création depuis T-00000646 ;
    son ingestion unique est tenue par `SpoolTests` (T5)."""

    def test_creer_les_stores_ne_touche_RIEN_hors_de_sa_racine(self):
        cible = self._depot_isole()
        # Un dossier ÉTRANGER, FRÈRE de la racine, avec SON propre spool piège : si
        # la création touchait autre chose que sa racine, il rougirait.
        etranger = Path(tempfile.mkdtemp(prefix="cadre_etranger_")).resolve()
        self.addCleanup(shutil.rmtree, etranger, ignore_errors=True)
        etr_evdir = etranger / ".agents" / "state" / "events"
        etr_evdir.mkdir(parents=True)
        (etr_evdir / _TRAP_NAME).write_text(_TRAP_LINE, encoding="utf-8")
        av_etranger = _empreinte(etr_evdir)
        self.assertIn(_TRAP_NAME, av_etranger, "spool étranger absent — banc non armé")
        # ET l'arbre du VRAI dépôt (git status), qui ne doit pas bouger non plus.
        av_git = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True).stdout
        # CONSTAT 5 : relevé AVANT/APRÈS de la partition RÉELLE de la cible — prescrit
        # par l'étape 2 du plan, EN PLUS de la fixture `_isolation_state_home`.
        # `_creer_v3` écrit sous `state_project()` ; si la partition se résolvait sous
        # la VRAIE `state_home()` (fixture contournée), un chemin y apparaîtrait.
        partition_reelle = self._partition_reelle_de(cible)
        av_partition = (set(partition_reelle.rglob("*"))
                        if partition_reelle.exists() else set())
        # MINEUR 9 : la LISTE des partitions machine, AVANT — une neuve sous une
        # racine AUTRE que la cible est une fuite que le relevé scopé ci-dessus ne
        # voit pas.
        av_partitions_liste = self._liste_partitions_reelles()

        res = stores.creer_les_stores(cible)

        # Les trois stores sont bien nés — events SOUS la racine cible, et
        # v3_event_store (T-00000650) comme index (T-00000668) SOUS la PARTITION
        # MACHINE de la racine cible. `is_relative_to` et non une sous-chaîne : la
        # partition isolée vit sous `<cible>_state/`, dont le chemin CONTIENT
        # `str(cible)` — l'ancien `assertIn(str(cible), …)` passait pour un index
        # hors racine (témoin qui ne pouvait pas échouer, mesuré sous T-00000668).
        self.assertTrue(res.events.is_file(), f"store non créé : {res.events}")
        self.assertTrue(res.events.resolve().is_relative_to(cible.resolve()),
                        f"store hors de la racine cible : {res.events}")
        for chemin in (res.v3_event_store, res.index):
            self.assertTrue(chemin.is_file(), f"store non créé : {chemin}")
            self.assertIn(str(state_project(cible)), str(chemin.resolve()),
                          f"store hors de la partition MACHINE : {chemin}")
            self.assertFalse(chemin.resolve().is_relative_to(cible.resolve()),
                             f"store DANS le dépôt cible : {chemin}")

        # Le spool ÉTRANGER n'a pas bougé d'un octet — relevé octet pour octet.
        self.assertEqual(_empreinte(etr_evdir), av_etranger,
                         "un arbre étranger, frère de la racine, a été touché.")
        ap_git = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True).stdout
        self.assertEqual(ap_git, av_git,
                         "le `git status` du VRAI dépôt a changé pendant la "
                         "création dans la cible.")
        # CONSTAT 5 : aucun chemin n'a paru sous la partition RÉELLE de la cible — la
        # création a bien écrit sous la partition ISOLÉE, jamais sous la vraie.
        ap_partition = (set(partition_reelle.rglob("*"))
                        if partition_reelle.exists() else set())
        self.assertEqual(ap_partition, av_partition,
                         "un chemin est apparu sous la partition RÉELLE de la cible "
                         "(state_home() réel) pendant la création — isolation "
                         "contournée.")
        # MINEUR 9 : aucune partition NEUVE sous une racine AUTRE que la cible.
        self.assertEqual(av_partitions_liste, self._liste_partitions_reelles(),
                         "une partition machine neuve est apparue sous une racine "
                         "AUTRE que la cible pendant la création.")


class RacineDivergenteTests(_EnvMixin):
    """CORRECTION 4 : `$CADRE_PROJECT_ROOT` prime sur l'argument. Créer les stores
    ailleurs que là où l'appelant l'a demandé serait une divergence silencieuse."""

    def test_creer_les_stores_refuse_une_racine_divergente_de_l_environnement(self):
        a = _batir_depot()
        self.addCleanup(shutil.rmtree, a, ignore_errors=True)
        b = _batir_depot()
        self.addCleanup(shutil.rmtree, b, ignore_errors=True)
        # env pointe A ; on appelle sur B. `project_root` rend A (env prime) ≠ B.
        # F9 : l'état MACHINE est redirigé lui aussi — sans quoi, sous `unittest`
        # nu, une création fautive écrirait sous le VRAI `state_home()`.
        etat = self._etat_frere(a)
        self._forcer_env(AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None,
                         CADRE_PROJECT_ROOT=str(a))
        with self.assertRaises(CadrePathError):
            stores.creer_les_stores(b)
        # AUCUN store créé : ni events dans A ou B, ni le store V3 NI l'index sous
        # l'état machine REDIRIGÉ (leur seule demeure depuis T-00000650 et
        # T-00000668 — les anciens relevés `.agents/state/v3_event_store.db` et
        # `.agents/state/index/index.db` ne pouvaient plus échouer).
        for racine in (a, b):
            for rel in (".agents/state/local/events.db",):
                self.assertFalse((racine / rel).exists(),
                                 f"un store a été créé malgré le refus : {racine / rel}")
        self.assertEqual(_empreinte(etat), {},
                         "un fichier est apparu sous l'état machine malgré le refus")

    def test_creer_les_stores_n_est_plus_refuse_par_une_simple_difference_de_casse(self):
        # T-00000674 : les DEUX côtés du comparateur (`base` et `demandee`)
        # passent par la MÊME canonicalisation `canonique_disque`. Une graphie de
        # casse différente d'UN répertoire ne diverge donc plus et n'est plus
        # refusée. Le REFUS d'une racine RÉELLEMENT divergente (témoin ci-dessus)
        # est conservé.
        cible = _batir_depot()
        self.addCleanup(shutil.rmtree, cible, ignore_errors=True)
        autre_graphie = cible.parent / cible.name.swapcase()
        if not autre_graphie.is_dir():
            self.skipTest("FS sensible a la casse")
        etat = self._etat_frere(cible)  # F9 : store V3 sous un état machine jetable
        self._forcer_env(AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None,
                         CADRE_PROJECT_ROOT=str(cible))
        # n'attend plus de levée : appel avec `autre_graphie`, résolu vers `cible`.
        resultat = stores.creer_les_stores(autre_graphie)
        self.assertTrue(Path(resultat.v3_event_store).exists())
        self.assertTrue(Path(resultat.v3_event_store).resolve().is_relative_to(
            etat.resolve()), f"store V3 hors de l'état redirigé : {resultat.v3_event_store}")

    def test_creer_les_stores_par_la_branche_GIT_accepte_une_graphie_de_casse_differente(self):
        # BLOQUANT binome de cloture : SANS $CADRE_PROJECT_ROOT (branche 2, git).
        # Sous GIT_WORK_TREE, `git rev-parse --show-toplevel` rend la graphie TAPEE ;
        # sans la canonicalisation de la SORTIE git (paths.py:324), `base` (racine
        # resolue) != `demandee` et le comparateur refuse a tort. Le temoin ci-dessus
        # ne prouve que la branche 1 ($CADRE_PROJECT_ROOT).
        cible = _batir_depot()
        self.addCleanup(shutil.rmtree, cible, ignore_errors=True)
        autre = cible.parent / cible.name.swapcase()
        if not autre.is_dir():
            self.skipTest("FS sensible a la casse")
        subprocess.run(["git", "init", "-q", str(cible)], check=True)
        etat = self._etat_frere(cible)  # F9 : store V3 sous un état machine jetable
        self._forcer_env(AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None,
                         CADRE_PROJECT_ROOT=None,
                         GIT_DIR=str(cible / ".git"),
                         GIT_WORK_TREE=str(autre))
        resultat = stores.creer_les_stores(autre)
        self.assertTrue(Path(resultat.v3_event_store).exists())
        self.assertTrue(Path(resultat.v3_event_store).resolve().is_relative_to(
            etat.resolve()), f"store V3 hors de l'état redirigé : {resultat.v3_event_store}")


class IndexPreserveTests(_EnvMixin):
    """CORRECTION 1 : sur un `index.db` EXISTANT et PEUPLÉ, la recréation met le
    schéma à niveau SANS réécrire l'état. `run_resync(State vide)` aurait, lui,
    soit effacé le contenu, soit refusé d'abaisser le watermark. Le store vit sous
    la partition machine depuis T-00000668 ; la propriété ne dépend pas du lieu."""

    def test_une_recreation_ne_reecrit_pas_un_index_peuple(self):
        cible = self._depot_isole()
        res = stores.creer_les_stores(cible)
        # SIMULE un store d'équipe déjà peuplé : un watermark de DONNÉES à '42'.
        conn = sqlite3.connect(str(res.index))
        try:
            conn.execute("INSERT INTO meta(key, value) VALUES('watermark', '42') "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
            conn.commit()
        finally:
            conn.close()
        # RECRÉATION : aucune exception (chemin « existant » = échelle + schéma),
        # et le watermark d'équipe est INTACT.
        res2 = stores.creer_les_stores(cible)
        self.assertEqual(res2.index, res.index)
        conn = sqlite3.connect(str(res2.index))
        try:
            wm = conn.execute(
                "SELECT value FROM meta WHERE key = 'watermark'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(wm, "la ligne watermark a disparu (write_state l'a effacée)")
        self.assertEqual(wm[0], "42",
                         "le watermark d'équipe a été réécrit par une recréation")


class StoresUtilisablesTests(_EnvMixin):
    """T8 — les PRODUCTEURS du kit ouvrent et utilisent les stores nés par la
    wheel, sans refus."""

    def test_les_trois_stores_crees_sont_UTILISABLES(self):
        cible = self._depot_isole()
        res = stores.creer_les_stores(cible)

        v3 = self._producteur("_stores_util_v3", cible / _MODULE_V3)
        mi = self._producteur("_stores_util_mi",
                              cible / ".agents" / "bin" / "migrate_index_to_db.py")
        es = self._producteur("_stores_util_es",
                              cible / ".agents" / "bin" / "event_store.py")
        # GARDE avant tout appel au producteur events (L-00000076) : la COPIE
        # résout son spool depuis son `__file__`, donc DANS le dépôt jetable.
        self.assertNotIn("AGENTS_EVENTS_DB", os.environ)
        self.assertEqual(es._events_dir(), cible / ".agents" / "state" / "events")
        otel = es._otel_dir()
        self.assertTrue(otel is not None and otel.is_relative_to(cible), otel)

        # --- v3_event_store.db : user_version=2, 11 colonnes réelles, idempotent.
        c3 = v3.get_db_connection(str(res.v3_event_store))
        self.addCleanup(c3.close)
        self.assertEqual(c3.execute("PRAGMA user_version").fetchone()[0], 2,
                         "user_version attendu = 2 pour le store V3")
        objets_v3 = _objets(c3)
        self.assertTrue(objets_v3, "store V3 vide — aucune table")
        cols_ledger = [r[1] for r in c3.execute("PRAGMA table_info(events_ledger)")]
        self.assertEqual(len(cols_ledger), 11,
                         "events_ledger doit porter ses 11 colonnes (mesuré)")
        v3.create_tables(str(res.v3_event_store))  # rejeu idempotent : ne lève pas
        self.assertEqual(c3.execute("PRAGMA user_version").fetchone()[0], 2,
                         "le rejeu de create_tables a bougé la version")

        # --- events.db : rouvre sans refus par la propriété PUBLIQUE `.connection`.
        handle = es.open_store(res.events, create=False)
        self.addCleanup(handle.close)
        self.assertEqual(handle.status, "ok", handle.degraded_reason() or "")
        self.assertIsNotNone(handle.connection, "connexion publique absente")
        self.assertTrue(_objets(handle.connection), "store events sans table")

        # --- index.db : db_schema_version rend la version courante ; comptes
        #     DÉRIVÉS SÉPARÉMENT selon la présence de FTS5, jamais l'un de l'autre.
        ci = mi.connect(res.index)
        self.addCleanup(ci.close)
        self.assertEqual(mi.db_schema_version(ci), mi.SCHEMA_VERSION,
                         "db_schema_version ne rend pas la version courante")
        objets_index = _objets(ci)
        cœur = {"meta", "symbols", "edges", "modules", "annotations", "journal"}
        self.assertTrue(cœur <= objets_index,
                        f"tables de cœur manquantes : {sorted(cœur - objets_index)}")
        fts_present = any(n == "symbols_fts" for n in objets_index)
        objets_hors_fts = {n for n in objets_index if not n.startswith("symbols_fts")}
        self.assertTrue(objets_hors_fts, "aucune table hors-FTS dans index.db")
        if fts_present:
            self.assertGreater(len(objets_index), len(objets_hors_fts),
                               "FTS5 présent mais aucune table d'ombre comptée")

        # --- DEUXIÈME CRÉATION IDEMPOTENTE : ne lève pas, mêmes chemins, versions
        #     inchangées.
        res2 = stores.creer_les_stores(cible)
        self.assertEqual((res2.v3_event_store, res2.events, res2.index),
                         (res.v3_event_store, res.events, res.index))
        c3b = v3.get_db_connection(str(res2.v3_event_store))
        self.addCleanup(c3b.close)
        self.assertEqual(c3b.execute("PRAGMA user_version").fetchone()[0], 2)
        cib = mi.connect(res2.index)
        self.addCleanup(cib.close)
        self.assertEqual(mi.db_schema_version(cib), mi.SCHEMA_VERSION)


class EcrivainsConcurrentsTests(_EnvMixin):
    """F1, F3, F4, F5 (binôme de T-00000646) — la création face à un TIERS : un
    écrivain qui tient le verrou, une maintenance du spool, un écrivain qui a
    validé des lignes. Chaque tiers est une connexion SQLite RÉELLE (ou le
    fichier-verrou RÉEL d'`events.py`), relâchée au nettoyage."""

    def _tenir(self, chemin: Path) -> sqlite3.Connection:
        """Un écrivain TIERS qui tient `BEGIN IMMEDIATE` sur `chemin` jusqu'au
        nettoyage (ROLLBACK puis fermeture — `addCleanup` est LIFO)."""
        conn = sqlite3.connect(str(chemin), isolation_level=None, timeout=0)
        conn.execute("BEGIN IMMEDIATE")
        self.addCleanup(conn.close)
        self.addCleanup(self._relacher, conn)
        return conn

    @staticmethod
    def _relacher(conn: sqlite3.Connection) -> None:
        if conn.in_transaction:
            conn.execute("ROLLBACK")

    def _verrou_de_maintenance(self, racine: Path) -> Path:
        """Un `.maintenance.lock` FRAIS (`_poser_verrou_de_maintenance`)."""
        return _poser_verrou_de_maintenance(racine)

    def test_un_rejeu_a_jour_passe_sous_un_ecrivain_tenant(self):
        """F1 : trois tenants `BEGIN IMMEDIATE`, un par store ; le rejeu sur des
        stores À JOUR ne prend aucun verrou et rend le premier résultat. Avant :
        `garantir_v3` prenait `BEGIN IMMEDIATE` sans condition et levait
        `OperationalError` après 5 s — là où `create_tables` rejoue en 0 s."""
        racine = self._racine_nue()
        premier = stores.creer_les_stores(racine)
        trois = (premier.v3_event_store, premier.events, premier.index)
        for chemin in trois:
            self._tenir(chemin)
        # ARMEMENT : chaque verrou est bien TENU — un second écrivain échoue.
        for chemin in trois:
            rival = sqlite3.connect(str(chemin), isolation_level=None, timeout=0)
            try:
                with self.assertRaises(sqlite3.OperationalError,
                                       msg=f"banc non armé : {chemin.name} non tenu"):
                    rival.execute("BEGIN IMMEDIATE")
            finally:
                rival.close()

        second = stores.creer_les_stores(racine)

        self.assertEqual(second, premier)

    def test_l_attente_d_un_ecrivain_egale_celle_du_producteur_V3(self):
        """F1 : `busy_timeout` posé par chaque `garantir_*` = celui qu'ouvre
        `agentic_v3.db.schema.get_db_connection`, LU PAR EXÉCUTION des deux
        côtés — jamais le défaut de `sqlite3.connect` (5 s)."""
        from agentic_v3.db import schema as v3  # noqa: PLC0415

        d = Path(tempfile.mkdtemp(prefix="cadre_attente_")).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        # T-00000770 : `get_db_connection` ne crée plus le store — le producteur
        # le crée par `create_tables`, comme chaque constructeur de production.
        # La mesure reste celle de la connexion que `get_db_connection` ouvre.
        v3.create_tables(str(d / "producteur.db"))
        producteur = v3.get_db_connection(str(d / "producteur.db"))
        try:
            attendu = producteur.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            producteur.close()
        nu = sqlite3.connect(str(d / "nu.db"))
        try:
            defaut = nu.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            nu.close()
        self.assertGreater(attendu, defaut, "banc non armé : le producteur n'attend "
                                            "pas plus longtemps que le défaut")
        for nom, garantir in (("v3", stores_schemas.garantir_v3),
                              ("events", stores_schemas.garantir_events),
                              ("index", stores_schemas.garantir_index)):
            with self.subTest(store=nom):
                conn = store.connect(d / (nom + ".db"))
                try:
                    garantir(conn)
                    self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0],
                                     attendu)
                finally:
                    conn.close()

    def test_chaque_sonde_attend_un_ecrivain_autant_que_la_creation(self):
        """critic-opus T3 / critic-fable 3 : les sondes de `_sonder` tournaient
        sur la connexion nue de `store.connect`, au défaut de 5 s, là où
        `garantir_*` attend `_ATTENTE_ECRIVAIN_MS`. Chaque sonde est ESPIONNÉE :
        le `busy_timeout` de SA connexion est lu par exécution à CHAQUE appel,
        ceux de `_sonder` comme ceux de `garantir_*`."""
        racine = self._racine_nue()
        stores.creer_les_stores(racine)  # les trois existent : tous sont sondés
        vraies = {nom: getattr(stores_schemas, nom)
                  for nom in ("sonder_v3", "sonder_events", "sonder_index")}
        vues: list[tuple[str, int]] = []

        def espion(nom):
            def sonde(conn):
                vues.append((nom, conn.execute("PRAGMA busy_timeout").fetchone()[0]))
                return vraies[nom](conn)
            return sonde

        with mock.patch.multiple(stores_schemas,
                                 **{nom: espion(nom) for nom in vraies}):
            stores.creer_les_stores(racine)

        # Non-vacuité : chaque store sondé au moins deux fois — par `_sonder`,
        # puis par son `garantir_*`.
        self.assertEqual({nom for nom, _t in vues}, set(vraies), vues)
        self.assertGreaterEqual(len(vues), 6, vues)
        for nom, attente in vues:
            self.assertEqual(attente, stores_schemas._ATTENTE_ECRIVAIN_MS,
                             f"{nom} sondé à busy_timeout={attente} ms : {vues}")

    def test_un_events_verrouille_pendant_sa_montee_leve_CadrePathError_et_le_rejeu_reprend(self):
        """F3 / T4 (critic-fable) : un tiers tient `events.db` (v0, vide) pendant
        que la wheel doit y poser le schéma. `CadrePathError` nommant la cause —
        jamais `OperationalError` brute —, l'état partiel est celui que le
        message annonce (v3 créé, index pas encore), et un rejeu reprend.
        L'attente est RACCOURCIE : ce témoin porte sur la traduction, la durée
        a le sien (ci-dessus)."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        chemins.events.parent.mkdir(parents=True)
        tenant = self._tenir(chemins.events)

        with mock.patch.object(stores_schemas, "_ATTENTE_ECRIVAIN_MS", 200):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        self.assertIn("OperationalError", str(ctx.exception))
        self.assertIn("relancer reprend", str(ctx.exception))
        self.assertTrue(chemins.v3_event_store.exists(), "état partiel non conforme")
        self.assertFalse(chemins.index.exists(), "état partiel non conforme")
        self._relacher(tenant)

        res = stores.creer_les_stores(racine)

        self.assertEqual(_forme(res.events)["user_version"],
                         stores_schemas.EVENTS_USER_VERSION, "le rejeu n'a pas repris")

    def test_une_maintenance_du_spool_fait_refuser_la_creation_d_events_a_la_sonde(self):
        """F4 : `.maintenance.lock` présent et `events.db` ABSENT ⇒ refus AVANT
        toute écriture (course C2 d'`events.py`) ; le verrou du tiers intact."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        verrou = self._verrou_de_maintenance(racine)

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        self.assertIn(".maintenance.lock", str(ctx.exception))
        for chemin in (chemins.v3_event_store, chemins.events, chemins.index):
            self.assertFalse(chemin.exists(), f"{chemin.name} créé malgré le refus")
        self.assertTrue(verrou.exists(), "le verrou d'un tiers a été retiré")

    def test_un_verrou_de_maintenance_apparu_apres_la_sonde_est_revu_avant_la_creation(self):
        """F4, SECONDE vérification : le verrou apparaît entre la sonde et la
        création d'`events.db` (simulé APRÈS `_creer_v3`) ; `_creer_events`
        refuse, le store précédent reste créé — la fenêtre est RÉDUITE, pas
        fermée, et la docstring le dit."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        vrai_creer_v3 = stores._creer_v3

        def creer_v3_puis_verrou(ws, rel):
            rendu = vrai_creer_v3(ws, rel)
            self._verrou_de_maintenance(racine)
            return rendu

        with mock.patch.object(stores, "_creer_v3", creer_v3_puis_verrou):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        self.assertIn(".maintenance.lock", str(ctx.exception))
        self.assertTrue(chemins.v3_event_store.exists())
        self.assertFalse(chemins.events.exists(), "events.db créé sous la maintenance")

    def test_un_events_PRESENT_est_monte_malgre_une_maintenance(self):
        """F4, CONTRE-TÉMOIN : le refus ne vaut que pour la CRÉATION ; un
        `events.db` présent n'est que monté, aucune course C2."""
        racine = self._racine_nue()
        premier = stores.creer_les_stores(racine)
        self._verrou_de_maintenance(racine)

        self.assertEqual(stores.creer_les_stores(racine), premier)

    def test_un_store_vivant_n_est_jamais_remplace_par_la_creation(self):
        """F5 : un écrivain a VALIDÉ N lignes dans le store V3 et garde sa
        connexion. La fenêtre check-then-act (store absent à `exists`, présent
        à l'écriture) est SIMULÉE en faisant répondre « absent » à
        `Workspace.exists` pour CE store. Avant : `write_bytes(b"")` →
        `os.replace` remplaçait l'inode et les N lignes étaient perdues ; après :
        seul le répertoire est créé, SQLite ouvre le fichier existant."""
        racine = self._racine_nue()
        res = stores.creer_les_stores(racine)
        cible = res.v3_event_store
        ecrivain = sqlite3.connect(str(cible), isolation_level=None)
        self.addCleanup(ecrivain.close)
        n = 4
        ecrivain.executemany(
            "INSERT INTO lessons_learned(language, domain_tag, error_pattern,"
            " lesson_text) VALUES('py', 't', 'e', ?)", [(str(i),) for i in range(n)])
        inode = cible.stat().st_ino
        vrai_exists = Workspace.exists

        def exists_menteur(ws, relatif):
            if ws.resolve(relatif) == cible.resolve():
                return False
            return vrai_exists(ws, relatif)

        with mock.patch.object(Workspace, "exists", exists_menteur):
            stores.creer_les_stores(racine)

        self.assertEqual(cible.stat().st_ino, inode, "l'inode du store vivant a changé")
        lecteur = sqlite3.connect(str(cible))
        try:
            lignes = lecteur.execute("SELECT COUNT(*) FROM lessons_learned").fetchone()[0]
        finally:
            lecteur.close()
        self.assertEqual(lignes, n, "des lignes validées ont été perdues")


class CreateursConcurrentsTests(_EnvMixin):
    """critic-opus T1/T2 sur a6b7bdb3 — deux ou trois CRÉATEURS d'un même store,
    chacun sur sa connexion SQLite RÉELLE, dans des fils RÉELS. Ces bancs
    appellent `stores_schemas` sur des fichiers d'un tmp, jamais
    `creer_les_stores` : aucune partition machine n'est résolue."""

    def _tmp(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="cadre_createurs_")).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    @staticmethod
    def _colonnes_et_version(db: Path) -> tuple[list[str], int]:
        conn = sqlite3.connect(str(db))
        try:
            noms = [r[1] for r in conn.execute("PRAGMA table_info(events_ledger)")]
            return noms, conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()

    def test_deux_createurs_d_un_v3_v0_ancien_format_passent_sans_colonne_dupliquee(self):
        """T1 : sur a6b7bdb3 le DDL v3 tournait HORS verrou ; deux créateurs
        inspectaient `events_ledger`, y voyaient manquer les mêmes colonnes, et
        le second `ALTER` levait « duplicate column name » (mesuré). Le
        rendez-vous est posé APRÈS cette inspection, attente bornée à 1 s :
        hors verrou les deux créateurs s'y croisent ; sous verrou le second
        attend le premier, le rendez-vous expire, puis la re-sonde le trouve
        tamponné."""
        db = self._tmp() / "v3_event_store.db"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(_V3_LEDGER_ANCIEN)
            conn.commit()
        finally:
            conn.close()
        manquantes = {col for col, _alter in stores_schemas._V3_COLONNES_LEDGER}
        noms_avant, version_avant = self._colonnes_et_version(db)
        self.assertEqual(version_avant, 0, "banc non armé : store déjà versionné")
        self.assertTrue(manquantes.isdisjoint(noms_avant),
                        "banc non armé : aucune colonne à ajouter")
        rendez_vous = threading.Barrier(2)
        vraies_colonnes = stores_schemas._colonnes

        def colonnes_puis_rendez_vous(c, pragma):
            rendu = vraies_colonnes(c, pragma)
            if "events_ledger" in pragma:
                with contextlib.suppress(threading.BrokenBarrierError):
                    rendez_vous.wait(timeout=1.0)
            return rendu

        def createur(_rang: int) -> None:
            c = store.connect(db)
            try:
                stores_schemas.garantir_v3(c)
            finally:
                c.close()

        with mock.patch.object(stores_schemas, "_colonnes", colonnes_puis_rendez_vous):
            erreurs = _en_parallele(2, createur)

        self.assertEqual(erreurs, [], "un créateur concurrent a levé")
        noms, version = self._colonnes_et_version(db)
        self.assertEqual(len(noms), len(set(noms)), f"colonne dupliquée : {noms}")
        self.assertTrue(manquantes <= set(noms), f"montée incomplète : {noms}")
        self.assertEqual(version, stores_schemas.V3_USER_VERSION)

    def test_un_kit_plus_recent_entre_sonde_et_DDL_fait_refuser_sans_recreer_de_table(self):
        """T1 : un kit PLUS RÉCENT tamponne v3 un cran au-delà et RETIRE
        `lessons_learned` entre la première sonde et le verrou. Sur a6b7bdb3 le
        DDL hors verrou recréait la table AVANT que la re-sonde du tampon ne
        refuse (mesuré) ; la re-sonde passe désormais sous le verrou, AVANT
        tout DDL, et la transaction est annulée."""
        db = self._tmp() / "v3_event_store.db"
        conn = store.connect(db)
        try:
            stores_schemas.garantir_v3(conn)
            conn.execute("PRAGMA user_version = 0")  # forme complète, version 0
        finally:
            conn.close()
        futur = stores_schemas.V3_USER_VERSION + 1
        vraie_sonde = stores_schemas.sonder_v3
        appels: list[int] = []
        rendus: list[int] = []

        def sonde_puis_kit_recent(c):
            appels.append(len(appels) + 1)  # compté AVANT : la re-sonde LÈVE
            rendu = vraie_sonde(c)
            rendus.append(rendu)
            if len(appels) == 1:
                tiers = sqlite3.connect(str(db), isolation_level=None)
                try:
                    tiers.execute("DROP TABLE lessons_learned")
                    # PRAGMA sans paramètre lié : entier du banc, forcé par int().
                    tiers.execute("PRAGMA user_version = " + str(int(futur)))
                finally:
                    tiers.close()
            return rendu

        conn = store.connect(db)
        try:
            with mock.patch.object(stores_schemas, "sonder_v3", sonde_puis_kit_recent):
                with self.assertRaises(stores_schemas.StoreRefuse) as ctx:
                    stores_schemas.garantir_v3(conn)
        finally:
            conn.close()

        self.assertEqual(rendus[0], 0, "banc non armé : la première sonde n'a pas vu v0")
        self.assertGreaterEqual(len(appels), 2, "aucune re-sonde sous le verrou")
        self.assertIn("PLUS RÉCENT", str(ctx.exception))
        lecteur = sqlite3.connect(str(db))
        try:
            tables = {r[0] for r in lecteur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            version = lecteur.execute("PRAGMA user_version").fetchone()[0]
        finally:
            lecteur.close()
        self.assertNotIn("lessons_learned", tables,
                         "une table retirée par le kit plus récent a été RECRÉÉE")
        self.assertIn("events_ledger", tables, "banc non armé : store vidé")
        self.assertEqual(version, futur, "le tampon du kit plus récent a été touché")

    def test_un_createur_intercale_entre_deux_instructions_ne_fait_pas_refuser_la_sonde(self):
        """T2, DÉTERMINISTE : un créateur valide le schéma d'`events.db` au DÉBUT
        de la DEUXIÈME instruction de premier niveau de `sonder_events`. Sur
        a6b7bdb3 la sonde lisait la version (0) puis la vacuité en deux
        instructions : la seconde voyait les tables du créateur, faux refus
        « non versionné » (mesuré). Lue en UNE instruction, elle voit UN
        instantané. Les traces imbriquées (`-- …`, émises par
        `pragma_user_version`) ne sont pas des instructions de premier niveau."""
        db = self._tmp() / "events.db"
        conn = store.connect(db)
        self.addCleanup(conn.close)
        premier_niveau: list[str] = []

        def intercaler(sql: str) -> None:
            if sql.lstrip().startswith("--"):
                return
            premier_niveau.append(sql)
            if len(premier_niveau) == 2:
                tiers = store.connect(db)
                try:
                    stores_schemas.garantir_events(tiers)
                finally:
                    tiers.close()

        conn.set_trace_callback(intercaler)
        try:
            version = stores_schemas.sonder_events(conn)
        finally:
            conn.set_trace_callback(None)

        self.assertTrue(premier_niveau, "banc non armé : aucune instruction tracée")
        self.assertIn(version, (0, stores_schemas.EVENTS_USER_VERSION))

    def test_trois_createurs_qui_sondent_en_boucle_ne_font_aucun_faux_refus(self):
        """T2, CHARGE : trois créateurs d'un `events.db` neuf, chacun sur sa
        connexion ; le rang 0 crée d'emblée, les deux autres SONDENT EN BOUCLE
        jusqu'à voir le store versionné (le geste d'un init qui interroge),
        puis tous montent. Mesuré sur a6b7bdb3 : 90 à 98 faux refus sur 300
        appels ; attendu 0. Borné à 60 rondes ET 20 s ; moins de 10 rondes
        dans la borne est un banc non armé, pas un vert."""
        base = self._tmp()
        faux: list[str] = []
        rondes = 0
        limite = time.monotonic() + 20.0
        while rondes < 60 and time.monotonic() < limite:
            dossier = base / f"r{rondes}"
            dossier.mkdir()
            db = dossier / "events.db"
            depart = threading.Barrier(3)

            def createur(rang: int, db: Path = db, depart=depart) -> None:
                c = store.connect(db)
                try:
                    depart.wait(timeout=10)
                    if rang == 0:
                        stores_schemas.garantir_events(c)
                    for _ in range(5000):
                        if (stores_schemas.sonder_events(c)
                                == stores_schemas.EVENTS_USER_VERSION):
                            break
                    stores_schemas.garantir_events(c)
                finally:
                    c.close()

            faux.extend(_en_parallele(3, createur))
            rondes += 1

        self.assertGreaterEqual(rondes, 10, "banc non armé : trop peu de rondes")
        self.assertEqual(faux, [], f"{len(faux)} faux refus sur {3 * rondes} appels")

    # --- T-00000668 (critic-fable, décision S-00002394) : passage en WAL -------
    # MESURÉ (sqlite 3.53.4) : sur un store encore en journal CLASSIQUE, un tiers
    # qui tient `BEGIN IMMEDIATE` (verrou RESERVED) fait lever `PRAGMA
    # journal_mode=WAL` IMMÉDIATEMENT (« database is locked », 0,0 s) — SQLite
    # n'appelle PAS le gestionnaire d'attente pour cette escalade, quel que soit
    # `busy_timeout`. C'est la course de deux créateurs d'un store neuf : 1 sur 20
    # à 1 sur 80 sous charge (critic-fable), 0 sur 50 à vide (mesuré) — d'où ces
    # témoins DÉTERMINISTES plutôt qu'une boucle de charge.

    def _tenant_reserved(self, db: Path) -> sqlite3.Connection:
        """Un tiers qui tient `BEGIN IMMEDIATE` sur `db` (fichier vide, donc en
        journal classique), relâchable depuis un autre fil, relâché au nettoyage."""
        db.write_bytes(b"")
        tenant = sqlite3.connect(str(db), isolation_level=None, timeout=0,
                                 check_same_thread=False)
        tenant.execute("BEGIN IMMEDIATE")
        self.addCleanup(tenant.close)
        self.addCleanup(lambda: tenant.in_transaction and tenant.execute("ROLLBACK"))
        return tenant

    def _armement_wal_sans_attente(self, db: Path) -> None:
        """ARMEMENT : le tenant fait bien lever le passage en WAL SANS attendre,
        malgré une attente de 5 s — sinon le banc ne prouve rien."""
        sonde = sqlite3.connect(str(db), isolation_level=None, timeout=5.0)
        try:
            debut = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError,
                                   msg="banc non armé : le passage en WAL a réussi"):
                sonde.execute("PRAGMA journal_mode=WAL")
            self.assertLess(time.monotonic() - debut, 1.0,
                            "banc non armé : SQLite a ATTENDU (gestionnaire appelé)")
        finally:
            sonde.close()

    def test_un_tenant_RESERVED_ne_fait_plus_lever_le_passage_en_WAL(self):
        """Le tiers relâche après 300 ms ; `garantir_v3` RETENTE le passage en
        WAL au lieu de lever, puis crée et tamponne. Mutation : retirer la
        retente (appel direct du PRAGMA) → `OperationalError` en 0,0 s."""
        db = self._tmp() / "v3_event_store.db"
        tenant = self._tenant_reserved(db)
        self._armement_wal_sans_attente(db)
        minuterie = threading.Timer(0.3, lambda: tenant.execute("COMMIT"))
        minuterie.start()
        self.addCleanup(minuterie.join)    # LIFO : avant la fermeture du tenant
        conn = store.connect(db)
        self.addCleanup(conn.close)

        debut = time.monotonic()
        stores_schemas.garantir_v3(conn)
        duree = time.monotonic() - debut

        self.assertGreaterEqual(duree, 0.25, "banc non armé : aucune attente observée")
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],
                         stores_schemas.V3_USER_VERSION)

    def test_la_retente_du_passage_en_WAL_est_bornee_par_l_attente_d_un_ecrivain(self):
        """Le tiers ne relâche JAMAIS (avant le nettoyage) ; `_ATTENTE_ECRIVAIN_MS`
        raccourcie à 200 ms. `garantir_v3` lève « locked » APRÈS l'attente, jamais
        avant, et rend la main. Mutations : borne retirée → le fil reste vivant
        au-delà de 10 s ; retente retirée → levée avant 200 ms."""
        db = self._tmp() / "v3_event_store.db"
        self._tenant_reserved(db)
        self._armement_wal_sans_attente(db)
        rendu: dict = {}

        def creer() -> None:
            conn = store.connect(db)
            debut = time.monotonic()
            try:
                stores_schemas.garantir_v3(conn)
                rendu["leve"] = None
            except sqlite3.OperationalError as exc:
                rendu["leve"] = str(exc)
            finally:
                rendu["duree"] = time.monotonic() - debut
                conn.close()

        with mock.patch.object(stores_schemas, "_ATTENTE_ECRIVAIN_MS", 200):
            fil = threading.Thread(target=creer, daemon=True)
            fil.start()
            fil.join(timeout=10)
            self.assertFalse(fil.is_alive(), "retente NON bornée : fil vivant après 10 s")

        self.assertIn("locked", rendu["leve"] or "", rendu)
        self.assertGreaterEqual(rendu["duree"], 0.2, f"levée avant l'attente : {rendu}")

    def test_la_borne_tient_quand_un_lecteur_fait_attendre_la_derniere_tentative(self):
        """critic-opus T5 (T-00000668) : chaque tentative tournait sous le
        `busy_timeout` ENTIER. Tenant RESERVED relâché juste avant l'échéance,
        lecteur SHARED tenu : la tentative qui suit le relâchement passe, elle,
        par le gestionnaire d'attente (le lecteur bloque l'EXCLUSIVE) et
        attendait `_ATTENTE_ECRIVAIN_MS` DE PLUS — mesuré 1 207 à 1 237 ms pour
        une borne de 600 ms. Attendu : levée « locked » APRÈS la borne et au
        plus borne + marge, `busy_timeout` rétabli ensuite. Mutations : retirer
        le `busy_timeout` du reste → ~2× la borne ; retirer le `finally` → le
        `busy_timeout` reste au dernier reste posé."""
        borne_ms, marge_s, liberation_s = 600, 0.3, 0.5
        db = self._tmp() / "v3_event_store.db"
        tenant = self._tenant_reserved(db)
        lecteur = sqlite3.connect(str(db), isolation_level=None, timeout=0,
                                  check_same_thread=False)
        self.addCleanup(lecteur.close)
        self.addCleanup(lambda: lecteur.in_transaction and lecteur.execute("ROLLBACK"))
        lecteur.execute("BEGIN")
        lecteur.execute("SELECT count(*) FROM sqlite_master").fetchone()
        self._armement_wal_sans_attente(db)
        conn = store.connect(db)
        self.addCleanup(conn.close)
        minuterie = threading.Timer(liberation_s, lambda: tenant.execute("ROLLBACK"))

        with mock.patch.object(stores_schemas, "_ATTENTE_ECRIVAIN_MS", borne_ms):
            minuterie.start()
            self.addCleanup(minuterie.join)    # LIFO : avant la fermeture du tenant
            debut = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                stores_schemas.garantir_v3(conn)
            duree = time.monotonic() - debut
            retabli = conn.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertIn("locked", str(ctx.exception))
        self.assertGreaterEqual(duree, borne_ms / 1000.0, "levée AVANT la borne")
        self.assertLessEqual(duree, borne_ms / 1000.0 + marge_s,
                             f"borne dépassée : {duree * 1000:.0f} ms pour {borne_ms} ms")
        self.assertEqual(retabli, borne_ms, "busy_timeout non rétabli après la retente")

    def test_une_erreur_autre_que_locked_n_est_jamais_retentee(self):
        """Seul « locked » est retenté : une autre `OperationalError` au passage
        en WAL est RELEVÉE à la première tentative. Mutation : retenter toute
        `OperationalError` → plusieurs tentatives comptées."""
        db = self._tmp() / "v3_event_store.db"
        vraie = store.connect(db)
        self.addCleanup(vraie.close)
        tentatives: list[str] = []

        class _Mandataire:
            """`vraie`, sauf le PRAGMA de passage en WAL, qui lève."""

            def execute(self, sql: str, *args):
                if sql.replace(" ", "").lower().startswith("pragmajournal_mode=wal"):
                    tentatives.append(sql)
                    raise sqlite3.OperationalError("disk I/O error")
                return vraie.execute(sql, *args)

            def __getattr__(self, nom: str):
                return getattr(vraie, nom)

            def __setattr__(self, nom: str, valeur) -> None:
                setattr(vraie, nom, valeur)

        with mock.patch.object(stores_schemas, "_ATTENTE_ECRIVAIN_MS", 300):
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                stores_schemas.garantir_v3(_Mandataire())

        self.assertIn("disk I/O error", str(ctx.exception))
        self.assertEqual(len(tentatives), 1, f"erreur non-locked retentée : {tentatives}")


class VerrouDeMaintenanceTests(_EnvMixin):
    """critic-fable 1 / critic-opus T5, décision S-00002323 (option A) : le
    `.maintenance.lock` est jugé comme `events.maintenance_lock` le juge —
    PRÉSENCE et ÂGE —, et la wheel ne le supprime JAMAIS. Chemin et seuil sont
    tenus égaux à ceux d'`events.py`, LUS des deux côtés : l'ancien témoin
    posait le verrou au même littéral que le code, donc ne pouvait pas
    échouer sur un chemin faux."""

    def test_chemin_et_seuil_egalent_ceux_d_events_py(self):
        # `_depot_isole` retire AGENTS_EVENTS_DIR : la COPIE d'`events.py`
        # résout son spool depuis son `__file__`, donc DANS le dépôt jetable.
        cible = self._depot_isole()
        ev = self._producteur("_verrou_events", cible / ".agents/bin/events.py")
        self.assertNotIn("AGENTS_EVENTS_DIR", os.environ)
        self.assertTrue(ev._events_dir().is_relative_to(cible),
                        f"banc non armé : events.py résout hors du dépôt jetable "
                        f"({ev._events_dir()})")

        self.assertEqual(cible / stores._REL_VERROU_MAINTENANCE,
                         ev._events_dir() / ev._MAINTENANCE_LOCK_NAME)
        self.assertEqual(stores._MAINTENANCE_PERIMEE_S, ev._MAINTENANCE_STALE_SECONDS)

    def test_un_verrou_de_plus_de_10_min_est_ignore_et_jamais_supprime(self):
        racine = self._racine_nue()
        verrou = _poser_verrou_de_maintenance(racine, age=7200.0)
        empreinte = (verrou.stat().st_ino, verrou.stat().st_mtime)
        # ARMEMENT : l'âge, lu par la méthode même qu'emploie la wheel, dépasse
        # le seuil.
        self.assertGreater(Workspace(racine).age_secondes(stores._REL_VERROU_MAINTENANCE),
                           stores._MAINTENANCE_PERIMEE_S, "banc non armé")

        res = stores.creer_les_stores(racine)

        self.assertEqual(_forme(res.events)["user_version"],
                         stores_schemas.EVENTS_USER_VERSION,
                         "events.db non créé sous un verrou orphelin")
        self.assertTrue(verrou.exists(), "le verrou orphelin a été SUPPRIMÉ")
        self.assertEqual((verrou.stat().st_ino, verrou.stat().st_mtime), empreinte,
                         "le verrou orphelin a été touché")

    def test_un_verrou_de_moins_de_10_min_fait_refuser_et_le_message_le_dit(self):
        for age in (0.0, 540.0):
            with self.subTest(age=age):
                racine = self._racine_nue()
                chemins = stores.chemins_des_stores(racine)
                verrou = _poser_verrou_de_maintenance(racine, age=age)

                with self.assertRaises(CadrePathError) as ctx:
                    stores.creer_les_stores(racine)

                message = str(ctx.exception)
                self.assertIn("Relancez quand elle a fini. Un verrou de plus de 10 min "
                              "est ignoré (orphelin), jamais supprimé", message)
                self.assertFalse(chemins.events.exists(), "events.db créé sous le verrou")
                self.assertTrue(verrou.exists(), "le verrou d'un tiers a été retiré")


class TraductionDesErreursTests(_EnvMixin):
    """critic-opus T6/T7 sur a6b7bdb3 : toute levée de la création sort en
    `CadrePathError` — `OSError` et `HorsRacine` comprises —, et le message dit
    OÙ le refus est tombé, sans double point."""

    def test_un_local_qui_est_un_FICHIER_leve_CadrePathError(self):
        racine = self._racine_nue()
        local = racine / ".agents" / "state" / "local"
        local.write_bytes(b"pas un repertoire\n")

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertEqual(local.read_bytes(), b"pas un repertoire\n", "le fichier a été touché")

    def test_un_local_lien_HORS_racine_leve_CadrePathError_sans_rien_ecrire_dehors(self):
        racine = self._racine_nue()
        dehors = Path(tempfile.mkdtemp(prefix="cadre_dehors_")).resolve()
        self.addCleanup(shutil.rmtree, dehors, ignore_errors=True)
        try:
            (racine / ".agents" / "state" / "local").symlink_to(
                dehors, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur cet hôte")

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        self.assertIsInstance(ctx.exception.__cause__, HorsRacine)
        self.assertEqual(sorted(dehors.iterdir()), [], "un fichier a été écrit HORS racine")

    def test_un_refus_a_la_sonde_le_dit_sans_double_point(self):
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        chemins.index.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(chemins.index))
        try:
            conn.execute("CREATE TABLE symbols(id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertIn("étranger", message, "banc non armé : pas le refus attendu")
        self.assertTrue(message.endswith("Refus à la sonde : aucun store créé ni monté."),
                        message)
        self.assertNotIn("relancer reprend", message)
        self.assertNotIn("..", message)
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")

    def test_une_levee_au_seuil_de_la_creation_ne_pretend_pas_que_rien_n_est_cree(self):
        """Le premier ÉCRIT est le SEUIL de `_creer_v3` — répertoire, puis
        fichier ouvert par SQLite —, pas son retour : une levée dans
        `garantir_v3` laisse déjà un fichier v3 sur disque, et le message ne
        doit pas annoncer « aucun store créé »."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)

        def garantir_qui_leve(_conn):
            raise sqlite3.OperationalError("database is locked")

        with mock.patch.object(stores_schemas, "garantir_v3", garantir_qui_leve):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertTrue(chemins.v3_event_store.exists(), "banc non armé : aucun fichier v3")
        self.assertIn("relancer reprend", message)
        self.assertNotIn("aucun store créé", message)


class LiensEtCourseTests(_EnvMixin):
    """T-00000759 (S-00002298, S-00002320) — la création des stores face à un
    LIEN SYMBOLIQUE à leur emplacement : (a) pré-planté, par exemple commité dans
    un dépôt cloné, et (b) planté par un tiers PENDANT la fenêtre entre la
    création du fichier et son ouverture par SQLite. La course (b) est SIMULÉE
    en interceptant `stores.store.connect`, le seul point par lequel la wheel
    ouvre un store : le piège agit au PREMIER appel, puis laisse passer."""

    def _lien(self, lien: Path, cible) -> None:
        try:
            os.symlink(cible, lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur cet hôte")

    def _dehors(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="cadre_dehors_")).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def _connect_piege(self, cible: Path, plantes: list[Path]):
        """Un `store.connect` qui, au PREMIER appel, délie le fichier qu'il
        reçoit et plante À SA PLACE un lien vers `cible`, puis ouvre par le
        VRAI `connect` avec les mêmes arguments."""
        vrai = store.connect

        def connect(chemin, *args, **kwargs):
            if not plantes:
                p = Path(chemin)
                p.unlink(missing_ok=True)
                self._lien(p, cible)
                plantes.append(p)
            return vrai(chemin, *args, **kwargs)

        return connect

    def test_un_lien_INTERNE_a_l_emplacement_d_events_est_refuse_a_la_sonde(self):
        """W1 (M6) : `events.db` est un lien RELATIF, comme git le stocke, vers
        un fichier INTERNE — présent (un `pkg/__init__.py` vide, suivi) puis
        absent. Avant : le fichier suivi DEVENAIT une base SQLite, et la cible
        absente était CRÉÉE par SQLite. Après : refus À LA SONDE — aucun store
        créé, cible intacte ou toujours absente, lien laissé en place (rien
        n'est supprimé). Le cas « absent » est celui que seule la sonde voit :
        `exists` suit le lien et le dit absent."""
        for cible_presente in (True, False):
            racine = self._racine_nue()
            chemins = stores.chemins_des_stores(racine)
            (racine / "pkg").mkdir()
            cible = racine / "pkg" / ("__init__.py" if cible_presente else "absent.db")
            if cible_presente:
                cible.write_bytes(b"")
            chemins.events.parent.mkdir(parents=True)
            self._lien(chemins.events, os.path.relpath(cible, chemins.events.parent))
            avant = _sha(cible) if cible_presente else None

            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

            message = str(ctx.exception)
            self.assertIn("lien symbolique", message)
            self.assertTrue(message.endswith(
                "Refus à la sonde : aucun store créé ni monté."), message)
            self.assertTrue(chemins.events.is_symlink(), "le lien a été retiré")
            if cible_presente:
                self.assertEqual(_sha(cible), avant, "le fichier suivi a été réécrit")
            else:
                self.assertFalse(cible.exists(), "SQLite a créé la cible du lien")
            self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")

    def test_un_lien_plante_pendant_la_creation_n_ecrit_rien_dehors(self):
        """W2 (M7) : entre la création du fichier et son ouverture, un tiers le
        délie et plante un lien vers `dehors/vole.db`, ABSENT. Avant : SQLite
        suivait le lien, CRÉAIT `vole.db` et y écrivait le schéma, et le refus
        (`HorsRacine`) tombait APRÈS l'écriture. Après : l'ouverture SANS
        création échoue sur le lien pendant — `dehors` reste vide."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        dehors = self._dehors()
        plantes: list[Path] = []

        with mock.patch.object(stores.store, "connect",
                               self._connect_piege(dehors / "vole.db", plantes)):
            with self.assertRaises(CadrePathError):
                stores.creer_les_stores(racine)

        self.assertEqual(plantes, [chemins.v3_event_store],
                         "banc non armé : le piège n'a pas visé le store V3")
        self.assertEqual(sorted(dehors.iterdir()), [], "un fichier a été écrit HORS racine")

    def test_un_echange_vers_une_base_etrangere_est_refuse_avant_toute_ecriture(self):
        """W3 : le fichier neuf est échangé contre un lien vers une base
        ÉTRANGÈRE, en WAL, dont un tiers tient la connexion avec des trames EN
        ATTENTE (point de contrôle automatique coupé). SQLite ouvre la base
        sans rien créer — c'est la comparaison d'identité APRÈS ouverture qui
        refuse, avant tout `garantir_*`. Les TROIS fichiers de l'étrangère
        (base, `-wal`, `-shm`) gardent leurs octets."""
        racine = self._racine_nue()
        etrangere = self._dehors() / "etrangere.db"
        tenant = sqlite3.connect(str(etrangere), isolation_level=None)
        self.addCleanup(tenant.close)
        tenant.execute("PRAGMA journal_mode=WAL")
        tenant.execute("PRAGMA wal_autocheckpoint=0")
        tenant.execute("CREATE TABLE t(x)")
        tenant.execute("INSERT INTO t VALUES (1)")
        trio = (etrangere, Path(str(etrangere) + "-wal"), Path(str(etrangere) + "-shm"))
        self.assertTrue(all(p.is_file() for p in trio), "banc non armé : trio incomplet")
        self.assertGreater(trio[1].stat().st_size, 0, "banc non armé : aucune trame en attente")
        avant = {p.name: _sha(p) for p in trio}
        plantes: list[Path] = []

        with mock.patch.object(stores.store, "connect",
                               self._connect_piege(etrangere, plantes)):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        self.assertEqual(len(plantes), 1, "banc non armé : le piège n'a pas joué")
        self.assertIn("emplacement changé", str(ctx.exception))
        self.assertEqual({p.name: _sha(p) for p in trio}, avant,
                         "la base étrangère a été écrite")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : bits POSIX non mesurés ici")
    def test_un_store_neuf_nait_en_0o600(self):
        """W4 (R1, décision 0o600) : les trois stores NEUFS naissent sans aucun
        bit de groupe ni d'autres — données d'exécution privées d'un
        utilisateur. Aujourd'hui (umask 022) ils naissaient 0o644. `-wal` et
        `-shm` d'un store ouvert héritent du mode (M3). L'umask est FIXÉ à 022
        d'abord (binôme F4) : sous un umask 077 hérité, un store né 0o644
        sortirait 0o600 et le témoin passerait sans rien prouver."""
        ancien = os.umask(0o022)
        self.addCleanup(os.umask, ancien)
        racine = self._racine_nue()
        res = stores.creer_les_stores(racine)
        for chemin in (res.v3_event_store, res.events, res.index):
            mode = os.lstat(chemin).st_mode & 0o777
            self.assertEqual(mode & 0o077, 0, f"{chemin.name} né en {oct(mode)}")
            self.assertEqual(mode & 0o600, 0o600, f"{chemin.name} né en {oct(mode)}")
        conn = sqlite3.connect(str(res.events), isolation_level=None)
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE w4(x)")
        for annexe in ("-wal", "-shm"):
            mode = os.lstat(str(res.events) + annexe).st_mode & 0o777
            self.assertEqual(mode & 0o077, 0, f"events.db{annexe} né en {oct(mode)}")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_un_lien_sur_un_annexe_wal_est_refuse(self):
        """W5 : `events.db` absent, mais `events.db-wal` est un lien vers un
        fichier d'un tiers. Refus À LA SONDE — aucun store créé —, le lien
        laissé en place et la cible intacte. Avant : la création passait et
        SQLite disposait de l'annexe à sa guise."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        cible = self._dehors() / "wal_cible"
        cible.write_bytes(b"octets d'un tiers\n")
        chemins.events.parent.mkdir(parents=True)
        wal = Path(str(chemins.events) + "-wal")
        self._lien(wal, cible)

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertIn("lien symbolique", message)
        self.assertTrue(message.endswith(
            "Refus à la sonde : aucun store créé ni monté."), message)
        self.assertTrue(wal.is_symlink(), "le lien annexe a été retiré")
        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n", "la cible a été touchée")
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")
        self.assertFalse(chemins.events.exists(), "events.db créé malgré le refus")

    # -- passe binôme (S-00002497, S-00002505, décision S-00002506) ---------

    _REPREND = "relancer reprend une fois la cause nommée ci-dessus levée."
    _RESTE = "aucune écriture de schéma ; le fichier vide créé reste en place"
    _REMPLACE = ("le fichier vide créé a été retiré ou remplacé par un tiers — rien "
                 "n'est supprimé, retirez ce qui occupe le nom puis relancez")

    def _etrangere_en_wal(self) -> tuple[Path, Path, Path]:
        """Une base ÉTRANGÈRE hors racine, en WAL, dont un tiers tient la
        connexion avec des trames EN ATTENTE (R4) : rend le trio (base, `-wal`,
        `-shm`), armé."""
        etrangere = self._dehors() / "etrangere.db"
        tenant = sqlite3.connect(str(etrangere), isolation_level=None)
        self.addCleanup(tenant.close)
        tenant.execute("PRAGMA journal_mode=WAL")
        tenant.execute("PRAGMA wal_autocheckpoint=0")
        tenant.execute("CREATE TABLE t(x)")
        tenant.execute("INSERT INTO t VALUES (1)")
        trio = (etrangere, Path(str(etrangere) + "-wal"), Path(str(etrangere) + "-shm"))
        self.assertTrue(all(p.is_file() for p in trio), "banc non armé : trio incomplet")
        self.assertGreater(trio[1].stat().st_size, 0, "banc non armé : aucune trame en attente")
        return trio

    def _espion_connect(self) -> list[Path]:
        """`stores.store.connect` espionné (appel réel conservé) : rend la
        liste des chemins ouverts, remplie au fil de l'eau."""
        vrai = store.connect
        ouverts: list[Path] = []

        def connect(chemin, *args, **kwargs):
            ouverts.append(Path(chemin))
            return vrai(chemin, *args, **kwargs)

        patch = mock.patch.object(stores.store, "connect", connect)
        patch.start()
        self.addCleanup(patch.stop)
        return ouverts

    def test_un_lien_PHYSIQUE_a_l_emplacement_d_events_est_refuse_a_la_sonde(self):
        """Binôme F1 : `events.db` est un second NOM (lien physique, `os.link`)
        d'un fichier suivi VIDE. Il n'est pas un lien symbolique et il est
        régulier, donc la sonde le laissait passer, et SQLite RÉÉCRIVAIT le
        fichier de l'autre nom en base. Après : refus À LA SONDE qui dit le
        nombre de liens, victime toujours vide, aucun store créé."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        (racine / "pkg").mkdir()
        victime = racine / "pkg" / "__init__.py"
        victime.write_bytes(b"")
        chemins.events.parent.mkdir(parents=True)
        try:
            os.link(victime, chemins.events)
        except (OSError, NotImplementedError):
            self.skipTest("liens physiques indisponibles sur ce système de fichiers")

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertIn("porte 2 liens physiques", message)
        self.assertIn("Rien n'est touché — retirez l'autre nom", message)
        self.assertTrue(message.endswith(
            "Refus à la sonde : aucun store créé ni monté."), message)
        self.assertEqual(victime.read_bytes(), b"", "le fichier de l'autre nom a été réécrit")
        self.assertEqual(os.lstat(chemins.events).st_nlink, 2, "un des deux noms a été retiré")
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_database_list_SEUL_voit_un_lien_plante_puis_retire_pendant_l_ouverture(self):
        """exec-critic MAJEUR, moitié LEXICALE (Mc1) : pendant l'ouverture, le
        fichier créé est mis de côté, un lien vers une base ÉTRANGÈRE prend sa
        place le temps que SQLite ouvre, puis le fichier revient sous son nom
        (échange ABA par un lien). La seconde identité est alors ÉGALE à la
        première : seul `PRAGMA database_list`, qui rend la cible résolue,
        voit l'échange. Le nom désigne toujours le fichier vide créé : le
        message dit qu'il reste en place."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        trio = self._etrangere_en_wal()
        avant = [_sha(p) for p in trio]
        vrai = store.connect
        joues: list[Path] = []

        def connect(chemin, *args, **kwargs):
            if joues:
                return vrai(chemin, *args, **kwargs)
            p = Path(chemin)
            de_cote = p.with_name(p.name + ".de_cote")
            os.rename(p, de_cote)
            self._lien(p, trio[0])
            try:
                return vrai(chemin, *args, **kwargs)
            finally:
                p.unlink()
                os.rename(de_cote, p)
                joues.append(p)

        with mock.patch.object(stores.store, "connect", connect):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertEqual(joues, [chemins.v3_event_store], "banc non armé : le piège n'a pas joué")
        self.assertIn("emplacement changé entre création et ouverture", message)
        self.assertIn(f"SQLite a ouvert {trio[0]}", message)
        self.assertIn("le nom désigne le même fichier.", message)
        self.assertIn(self._RESTE, message)
        self.assertTrue(message.endswith(self._REPREND), message)
        self.assertEqual([_sha(p) for p in trio], avant, "la base étrangère a été écrite")
        self.assertEqual(os.lstat(chemins.v3_event_store).st_size, 0,
                         "le fichier créé n'est plus vide")

    def test_la_seconde_identite_SEULE_voit_une_base_etrangere_renommee_sur_le_nom(self):
        """exec-critic MAJEUR, moitié IDENTITÉ (Mc2) : entre la création et
        l'ouverture, un tiers RENOMME (`os.replace`) une base étrangère, en WAL
        et tenue avec des trames en attente, SUR le nom du store. Ce n'est pas
        un lien : `database_list` rend, lexicalement, le chemin attendu — seule
        la seconde identité voit que l'inode a changé. Avant la seconde moitié,
        le schéma était écrit DANS la base étrangère (banc S1). Les trois
        fichiers de l'étrangère — la base, désormais sous le nom du store, et
        ses `-wal`/`-shm` restés sous leur nom — gardent leurs octets."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        trio = self._etrangere_en_wal()
        avant = [_sha(p) for p in trio]
        vrai = store.connect
        joues: list[Path] = []

        def connect(chemin, *args, **kwargs):
            if not joues:
                os.replace(trio[0], chemin)
                joues.append(Path(chemin))
            return vrai(chemin, *args, **kwargs)

        with mock.patch.object(stores.store, "connect", connect):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertEqual(joues, [chemins.v3_event_store], "banc non armé : le piège n'a pas joué")
        self.assertIn("emplacement changé entre création et ouverture", message)
        self.assertIn(f"SQLite a ouvert {chemins.v3_event_store}", message)
        self.assertIn("le nom désigne un autre fichier.", message)
        self.assertIn(self._REMPLACE, message)
        self.assertNotIn("reste en place", message)
        apres = [_sha(chemins.v3_event_store), _sha(trio[1]), _sha(trio[2])]
        self.assertEqual(apres, avant, "la base étrangère a été écrite")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_un_lien_plante_entre_la_sonde_et_la_creation_est_juge_avant_toute_ouverture(self):
        """exec-critic, branche de secours (1/3) : le nom est LIBRE à la sonde,
        puis un tiers y plante un lien vers une base étrangère juste avant la
        création exclusive, qui rend donc `None`. `_ouvrir` relit l'identité
        EXISTANTE et la juge (`_juger_la_feuille`) : refus nommé « lien », et
        `store.connect` n'est JAMAIS appelé sur ce nom."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        trio = self._etrangere_en_wal()
        avant = [_sha(p) for p in trio]
        ouverts = self._espion_connect()
        vrai = Workspace.creer_fichier_exclusif
        joues: list[str] = []

        def creer(ws, relatif, mode=0o600):
            if not joues:
                self._lien(ws.resolve(Path(relatif).parent) / Path(relatif).name, trio[0])
                joues.append(str(relatif))
            return vrai(ws, relatif, mode)

        with mock.patch.object(Workspace, "creer_fichier_exclusif", creer):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertEqual(len(joues), 1, "banc non armé : le piège n'a pas joué")
        self.assertIn("ne se crée ni ne s'ouvre à travers un lien", message)
        self.assertNotIn(chemins.v3_event_store, ouverts,
                         "SQLite a ouvert le nom avant que la feuille soit jugée")
        self.assertTrue(chemins.v3_event_store.is_symlink(), "le lien a été retiré")
        self.assertEqual([_sha(p) for p in trio], avant, "la base étrangère a été écrite")

    def test_une_feuille_NON_REGULIERE_est_refusee_a_la_sonde_sans_ouverture(self):
        """exec-critic, branche de secours (2/3) : `events.db` est un
        RÉPERTOIRE. Refus À LA SONDE nommé « pas un fichier régulier », sans
        qu'SQLite l'ouvre ; le répertoire reste, vide."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        chemins.events.mkdir(parents=True)
        ouverts = self._espion_connect()

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertIn(f"{chemins.events} n'est pas un fichier régulier", message)
        self.assertTrue(message.endswith(
            "Refus à la sonde : aucun store créé ni monté."), message)
        self.assertEqual(ouverts, [], "SQLite a ouvert un store malgré le refus")
        self.assertTrue(chemins.events.is_dir(), "le répertoire a été retiré")
        self.assertEqual(sorted(chemins.events.iterdir()), [], "le répertoire a été écrit")
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")

    def test_un_annexe_qui_est_un_REPERTOIRE_est_refuse_a_la_sonde(self):
        """W5bis (binôme fable) : `events.db` absent, `events.db-wal` est un
        RÉPERTOIRE. Seul un LIEN d'annexe était refusé : la création passait,
        puis SQLite échouait sur le WAL APRÈS avoir créé `events.db`. Après :
        refus À LA SONDE, message dédié aux annexes, rien créé."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        wal = Path(str(chemins.events) + "-wal")
        wal.mkdir(parents=True)

        with self.assertRaises(CadrePathError) as ctx:
            stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertIn(f"{wal} n'est pas un fichier régulier à l'emplacement d'un "
                      f"annexe de store", message)
        self.assertTrue(message.endswith(
            "Refus à la sonde : aucun store créé ni monté."), message)
        self.assertTrue(wal.is_dir(), "l'annexe répertoire a été retiré")
        self.assertFalse(chemins.events.exists(), "events.db créé malgré le refus")
        self.assertFalse(chemins.v3_event_store.exists(), "v3 créé malgré le refus")

    def test_un_annexe_a_liens_PHYSIQUES_est_refuse_a_la_sonde_comme_la_feuille(self):
        """Décision orchestrateur (suite S-00002506) : `events.db-wal` est un
        second NOM (`os.link`) du fichier d'un tiers, à côté d'un `events.db`
        absent (store neuf) puis présent (store existant). Mesuré avant (darwin,
        SQLite 3.53.4) : aucun refus, SQLite RETIRAIT ce nom — octets du tiers
        intacts, mais un nom d'un tiers supprimé. Après : refus À LA SONDE, comme
        pour la feuille, qui dit le nombre de liens ; les deux noms restent, les
        octets du tiers aussi."""
        for existant in (False, True):
            with self.subTest(store="existant" if existant else "neuf"):
                racine = self._racine_nue()
                chemins = stores.chemins_des_stores(racine)
                if existant:
                    stores.creer_les_stores(racine)
                else:
                    chemins.events.parent.mkdir(parents=True)
                tiers = self._dehors() / "fichier_du_tiers"
                tiers.write_bytes(b"octets d'un tiers\n" * 4)
                wal = Path(str(chemins.events) + "-wal")
                try:
                    os.link(tiers, wal)
                except (OSError, NotImplementedError):
                    self.skipTest("liens physiques indisponibles sur ce système de fichiers")
                avant = _sha(tiers)

                with self.assertRaises(CadrePathError) as ctx:
                    stores.creer_les_stores(racine)

                message = str(ctx.exception)
                self.assertIn(f"{wal} porte 2 liens physiques à l'emplacement d'un "
                              f"annexe de store (-wal)", message)
                self.assertIn("Rien n'est touché — retirez l'autre nom", message)
                self.assertTrue(message.endswith(
                    "Refus à la sonde : aucun store créé ni monté."), message)
                self.assertTrue(os.path.lexists(wal), "le second nom du tiers a été retiré")
                self.assertEqual(os.lstat(tiers).st_nlink, 2, "un des deux noms a disparu")
                self.assertEqual(_sha(tiers), avant, "les octets du tiers ont été écrits")
                self.assertEqual(chemins.events.exists(), existant,
                                 "events.db créé (ou retiré) malgré le refus")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_un_lien_shm_plante_avant_le_passage_en_WAL_est_nomme(self):
        """Binôme fable, chemin de CRÉATION : un lien `-shm` planté après la
        sonde, juste avant le passage en WAL, fait lever SQLite
        (`unable to open database file`, CANTOPEN mesuré 3.53.4) SANS nommer le
        lien. Après : la garantie re-sonde les liens sur cette levée, et le
        refus NOMME l'annexe ; le lien reste, sa cible est intacte."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        cible = self._dehors() / "shm_cible"
        cible.write_bytes(b"octets d'un tiers\n")
        shm = Path(str(chemins.v3_event_store) + "-shm")
        vrai = stores_schemas._passer_en_wal
        joues: list[int] = []

        def passer_en_wal(conn):
            if not joues:
                self._lien(shm, cible)
                joues.append(1)
            return vrai(conn)

        with mock.patch.object(stores_schemas, "_passer_en_wal", passer_en_wal):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertEqual(joues, [1], "banc non armé : le piège n'a pas joué")
        self.assertIsInstance(ctx.exception.__cause__, stores_schemas.StoreRefuse)
        self.assertIsInstance(ctx.exception.__cause__.__context__, sqlite3.OperationalError,
                              "banc non armé : pas la levée de SQLite")
        self.assertIn(f"{shm} est un lien symbolique", message)
        self.assertTrue(message.endswith(self._REPREND), message)
        self.assertTrue(shm.is_symlink(), "le lien annexe a été retiré")
        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n", "la cible a été touchée")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_un_lien_d_annexe_plante_entre_le_jugement_et_la_sonde_est_nomme(self):
        """Binôme fable, chemin de SONDE : un store V3 déjà créé (en WAL) ; au
        rejeu, un lien `-wal` est planté APRÈS le jugement des liens et AVANT
        la première lecture de la sonde. SQLite lève (CANTOPEN, mesuré 3.53.4)
        et laisse le lien ; le refus le NOMME, à la sonde."""
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        stores.creer_les_stores(racine)
        cible = self._dehors() / "wal_cible"
        cible.write_bytes(b"octets d'un tiers\n")
        wal = Path(str(chemins.v3_event_store) + "-wal")
        self.assertFalse(os.path.lexists(wal), "banc non armé : un -wal traîne")
        vrai = stores_schemas.sonder_v3
        joues: list[int] = []

        def sonder_v3(conn):
            if not joues:
                self._lien(wal, cible)
                joues.append(1)
            return vrai(conn)

        with mock.patch.object(stores_schemas, "sonder_v3", sonder_v3):
            with self.assertRaises(CadrePathError) as ctx:
                stores.creer_les_stores(racine)

        message = str(ctx.exception)
        self.assertEqual(joues, [1], "banc non armé : le piège n'a pas joué")
        self.assertIsInstance(ctx.exception.__cause__.__context__, sqlite3.OperationalError,
                              "banc non armé : pas la levée de SQLite")
        self.assertIn(f"{wal} est un lien symbolique", message)
        self.assertTrue(message.endswith(
            "Refus à la sonde : aucun store créé ni monté."), message)
        self.assertTrue(wal.is_symlink(), "le lien annexe a été retiré")
        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n", "la cible a été touchée")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : non mesuré ici")
    def test_un_refus_d_ouverture_sans_creation_dit_ce_que_le_nom_designe(self):
        """Binôme fable (refus W2 opaque) et F5 : quand `store.connect(…,
        sans_creation=True)` lève, le refus est un `StoreRefuse` NOMMÉ qui dit
        ce que le nom désigne désormais — rien, un lien symbolique, un autre
        fichier ou le même fichier —, et ne prétend que le fichier vide créé
        « reste en place » que si le nom le désigne encore."""
        dehors = self._dehors()
        cas = {
            "rien": lambda p: p.unlink(),
            "un lien symbolique": lambda p: (p.unlink(), self._lien(p, dehors / "vole.db")),
            "un autre fichier": lambda p: (p.unlink(), p.mkdir()),
            "le même fichier": lambda p: os.chmod(p, 0),
        }
        for designe, geste in cas.items():
            with self.subTest(designe=designe):
                if designe == "le même fichier" and getattr(os, "geteuid", lambda: 1)() == 0:
                    self.skipTest("root ouvre un fichier en mode 000 : cas non jouable")
                racine = self._racine_nue()
                chemins = stores.chemins_des_stores(racine)
                vrai = store.connect
                joues: list[Path] = []

                def connect(chemin, *args, _geste=geste, _joues=joues, **kwargs):
                    if not _joues:
                        _geste(Path(chemin))
                        _joues.append(Path(chemin))
                    return vrai(chemin, *args, **kwargs)

                with mock.patch.object(stores.store, "connect", connect):
                    with self.assertRaises(CadrePathError) as ctx:
                        stores.creer_les_stores(racine)

                message = str(ctx.exception)
                self.assertEqual(joues, [chemins.v3_event_store], "banc non armé")
                self.assertIsInstance(ctx.exception.__cause__, stores_schemas.StoreRefuse,
                                      "la levée de SQLite sort brute")
                self.assertIsInstance(ctx.exception.__cause__.__cause__,
                                      sqlite3.OperationalError)
                self.assertIn(f"le nom désigne {designe} —", message)
                if designe == "le même fichier":
                    self.assertIn(self._RESTE, message)
                else:
                    self.assertIn(self._REMPLACE, message)
                    self.assertNotIn("reste en place", message)
                self.assertTrue(message.endswith(self._REPREND), message)
                self.assertEqual(sorted(dehors.iterdir()), [], "un fichier a été écrit HORS racine")


#: La sonde de U1 (T-00000770), jouée dans un ENFANT `sys.executable -I` : ni
#: `src/` ni le cwd sur `sys.path`, donc `cadre` introuvable par import — armement
#: RENDU par l'enfant (`arme`), asserté par le parent. `store.py` et `workspace.py`
#: y sont chargés PAR CHEMIN, `sys.modules` posé AVANT `exec_module`, comme le font
#: les trois coutures des producteurs. Chaque cas rend son constat en JSON ; le
#: parent les juge un par un (`subTest`).
_SONDE_U1 = r'''
import hashlib, importlib.util, json, os, sqlite3, sys
from pathlib import Path


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


rapport = {"arme": importlib.util.find_spec("cadre") is None}
st = charger("_cadre_ledger_store_u1", sys.argv[1])
wsm = charger("_cadre_workspace_u1", sys.argv[2])
d = Path(sys.argv[3]).resolve()
dehors = Path(sys.argv[4]).resolve()
os.umask(0o022)
ws = wsm.Workspace(d)


def refus(appel):
    try:
        appel()
    except st.EmplacementRefuse as exc:
        return str(exc)
    return None


# (1) un lien PENDANT à l'emplacement : refusé, sa cible jamais créée.
os.symlink(dehors / "pendant_cible.db", d / "pendant.db")
rapport["lien pendant"] = {
    "refus": [refus(lambda: st.ouvrir_sans_suivre(ws, "pendant.db", creer=c))
              for c in (True, False)],
    "cible_creee": (dehors / "pendant_cible.db").exists()}

# (2) un lien à l'emplacement d'un ANNEXE, store présent : `refuser_les_liens`.
for suffixe in ("-wal", "-shm", "-journal"):
    nom = "annexe" + suffixe.replace("-", "_") + ".db"
    (d / nom).write_bytes(b"")
    os.symlink(dehors / ("annexe_cible" + suffixe), d / (nom + suffixe))
    rapport["annexe " + suffixe] = {
        "refus": [refus(lambda: st.refuser_les_liens(ws, nom))],
        "cible_creee": (dehors / ("annexe_cible" + suffixe)).exists()}

# (3) un lien vers une base ÉTRANGÈRE vivante (base + -wal + -shm tenus ouverts).
etr = dehors / "etrangere.db"
tenue = sqlite3.connect(str(etr))
tenue.execute("PRAGMA journal_mode=WAL")
tenue.execute("CREATE TABLE t(x)")
tenue.execute("INSERT INTO t VALUES (1)")
tenue.commit()
trois = [etr, Path(str(etr) + "-wal"), Path(str(etr) + "-shm")]
avant = [sha(p) for p in trois]
os.symlink(etr, d / "lien.db")
rapport["base etrangere"] = {
    "refus": [refus(lambda: st.ouvrir_sans_suivre(ws, "lien.db", creer=c))
              for c in (True, False)],
    "trois_fichiers": len([p for p in trois if p.exists()]),
    "sha_inchange": [sha(p) for p in trois] == avant}
tenue.close()

# (4) un store NEUF naît en 0o600, par les deux ouvertures (défaut et `connecter`).
modes = []
for nom, connecter in (("neuf_defaut.db", None),
                       ("neuf_nu.db", lambda u: sqlite3.connect(u, uri=True, timeout=30.0))):
    conn, ident, cree = st.ouvrir_sans_suivre(ws, nom, creer=True, connecter=connecter)
    conn.close()
    modes.append([cree, oct((d / nom).stat().st_mode & 0o777), str(ident.chemin) == str(d / nom)])
rapport["neuf 0o600"] = {"modes": modes}

# (5) `:memory:` refusé par les DEUX entrées, aucun fichier de ce nom créé.
rapport[":memory:"] = {
    "refus": [refus(lambda: st.ouvrir_sans_suivre(ws, ":memory:", creer=True)),
              refus(lambda: st.refuser_les_liens(ws, ":memory:"))],
    "fichier_cree": (d / ":memory:").exists()}

# (6) un lien PENDANT planté ENTRE la création et l'ouverture (ouverture par
# défaut, `connect` du module intercepté) : SQLite lève au lieu de créer au bout.
vrai = st.connect
plantes = []


def piege(chemin, **kw):
    if not plantes:
        Path(chemin).unlink()
        os.symlink(dehors / "plante_cible.db", chemin)
        plantes.append(str(chemin))
    return vrai(chemin, **kw)


st.connect = piege
rapport["lien plante"] = {
    "refus": [refus(lambda: st.ouvrir_sans_suivre(ws, "plante.db", creer=True))],
    "arme": len(plantes) == 1,
    "cible_creee": (dehors / "plante_cible.db").exists()}
st.connect = vrai

# (7) une base étrangère RENOMMÉE sur le nom pendant l'ouverture (`connecter`) :
# `database_list` rend le nom attendu, seule la seconde identité la voit.
autre = dehors / "renommee.db"
c = sqlite3.connect(str(autre))
c.execute("CREATE TABLE u(y)")
c.commit()
c.close()
sha_autre = sha(autre)
(d / "renomme.db").write_bytes(b"")
renommes = []


def renommer(uri):
    if not renommes:
        os.replace(autre, d / "renomme.db")
        renommes.append(uri)
    return sqlite3.connect(uri, uri=True)


rapport["base renommee"] = {
    "refus": [refus(lambda: st.ouvrir_sans_suivre(ws, "renomme.db", creer=False,
                                                  connecter=renommer))],
    "arme": len(renommes) == 1,
    "sha_inchange": sha(d / "renomme.db") == sha_autre}
print(json.dumps(rapport))
'''


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (R3 de T-00000759)")
class OuvrirSansSuivreTests(unittest.TestCase):
    """T-00000770 — la primitive d'ouverture NON SUIVIE vit dans `store.py`, qui
    reste STDLIB-SEULE : les trois producteurs hors paquet (`event_store.py`,
    `migrate_index_to_db.py`, `agentic_v3`) la chargent PAR CHEMIN quand `cadre`
    n'est pas installé, et un `store.py` qui importerait `cadre.*` casserait ce
    chargement (mesuré, contrôle négatif du plan : `ModuleNotFoundError`)."""

    _STORE_PY = _SRC_CADRE / "ledger" / "store.py"

    def test_store_py_n_importe_aucun_module_cadre_t770(self):
        """U0 — VERT AVANT ET APRÈS : garde de la direction. Aucun `import cadre…`
        ni `from cadre… import`, à quelque profondeur que ce soit (`ast.walk`
        voit un `if TYPE_CHECKING:` comme un corps de fonction), et aucun import
        RELATIF (`level > 0`). Mord : Mn (`from cadre.workspace import Identite`
        ajouté à store.py)."""
        arbre = ast.parse(self._STORE_PY.read_text(encoding="utf-8"))
        imports, fautifs = 0, []
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                imports += 1
                fautifs += [f"{n.lineno}: import {a.name}" for a in n.names
                            if a.name.split(".")[0] == "cadre"]
            elif isinstance(n, ast.ImportFrom):
                imports += 1
                if n.level > 0 or (n.module or "").split(".")[0] == "cadre":
                    fautifs.append(f"{n.lineno}: from {'.' * n.level}{n.module or ''}")
        self.assertGreaterEqual(imports, 2, "banc non armé : aucun import relevé")
        self.assertEqual(fautifs, [], "store.py importe un module `cadre` : son "
                                      "chargement PAR CHEMIN casserait")

    def test_la_primitive_chargee_par_chemin_refuse_sans_suivre_t770(self):
        """U1 — rouge sur BASE (`AttributeError: ouvrir_sans_suivre`). Dans un
        enfant `-I` où `cadre` est INTROUVABLE (armement asserté), `store.py` et
        `workspace.py` chargés par chemin : lien pendant refusé sans créer sa
        cible (création comme vérification) ; lien d'annexe refusé par
        `refuser_les_liens` ; lien vers une base étrangère vivante refusé, ses
        trois fichiers inchangés ; store neuf en 0o600 par les deux ouvertures ;
        `:memory:` refusé par les deux entrées sans fichier créé ; lien pendant
        planté entre création et ouverture refusé sans cible créée (Mb) ; base
        étrangère renommée sur le nom refusée (Mc2)."""
        base = Path(tempfile.mkdtemp(prefix="cadre_u1_")).resolve()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        d, dehors, cwd = base / "atelier", base / "dehors", base / "cwd"
        for p in (d, dehors, cwd):
            p.mkdir()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "CADRE_STATE_DIR": str(base / "state"),
               "CADRE_PROJECT_ROOT": str(base / "racine"),
               "AGENTS_EVENTS_DIR": str(base / "events")}
        fini = subprocess.run(
            [sys.executable, "-I", "-c", _SONDE_U1, str(self._STORE_PY),
             str(_SRC_CADRE / "workspace.py"), str(d), str(dehors)],
            cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        rapport = json.loads(fini.stdout.strip().splitlines()[-1])
        self.assertTrue(rapport.pop("arme"), "banc non armé : `cadre` importable dans l'enfant")
        attendus = {"lien pendant", "annexe -wal", "annexe -shm", "annexe -journal",
                    "base etrangere", "neuf 0o600", ":memory:", "lien plante",
                    "base renommee"}
        self.assertEqual(set(rapport), attendus)
        for cas, constat in rapport.items():
            with self.subTest(cas=cas):
                if cas == "neuf 0o600":
                    self.assertEqual(constat["modes"], [[True, "0o600", True]] * 2)
                    continue
                for message in constat["refus"]:
                    self.assertIsNotNone(message, f"{cas} : aucun refus")
                if cas == ":memory:":
                    self.assertTrue(all(":memory:" in m for m in constat["refus"]))
                    self.assertFalse(constat["fichier_cree"])
                    continue
                if "cible_creee" in constat:
                    self.assertFalse(constat["cible_creee"], f"{cas} : cible créée au bout du lien")
                if cas in ("lien pendant", "base etrangere") or cas.startswith("annexe"):
                    self.assertTrue(all("lien symbolique" in m for m in constat["refus"]),
                                    constat["refus"])
                if cas == "base etrangere":
                    self.assertEqual(constat["trois_fichiers"], 3, "banc non armé")
                    self.assertTrue(constat["sha_inchange"], "la base étrangère a été écrite")
                if cas in ("lien plante", "base renommee"):
                    self.assertTrue(constat["arme"], f"{cas} : piège non joué")
                if cas == "base renommee":
                    self.assertTrue(constat["sha_inchange"], "la base renommée a été écrite")


class UriAbsolueTests(unittest.TestCase):
    """T-00000759, binôme F2 : l'URI de `store.connect(…, sans_creation=True)`
    et de la lecture seule. Sur un chemin UNC Windows (`\\\\serveur\\partage\\…`),
    `as_uri` met le SERVEUR en autorité (`file://serveur/…`), que SQLite
    refuse (« invalid uri authority ») ; `file:////serveur/…` le passe dans le
    CHEMIN. Mesuré ici : la forme de `as_uri` et le refus de SQLite ; l'OUVERTURE
    Windows d'un partage, elle, n'est PAS mesurée (§ BORNE WINDOWS de
    `store.py`). `PurePath.as_uri` est déprécié (retrait annoncé en 3.19) :
    l'avertissement est tu ici, et le banc se saute le jour où il disparaît."""

    @staticmethod
    def _uri(chemin, parametres: str = "?mode=rw") -> str:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return store._uri_absolue(chemin, "sans création", parametres)

    @unittest.skipUnless(hasattr(PureWindowsPath, "as_uri"),
                         "PurePath.as_uri retiré : forme UNC non rejouable hors Windows")
    def test_un_chemin_UNC_passe_le_serveur_dans_le_chemin_pas_dans_l_autorite(self):
        unc = PureWindowsPath(r"\\serveur\partage\etat\v3_event_store.db")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            brut = unc.as_uri()
        self.assertEqual(brut, "file://serveur/partage/etat/v3_event_store.db",
                         "banc non armé : as_uri ne met plus le serveur en autorité")
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            sqlite3.connect(brut + "?mode=rw", uri=True)
        self.assertIn("authority", str(ctx.exception), "banc non armé : pas le refus d'autorité")

        rendu = self._uri(unc)

        self.assertEqual(rendu, "file:////serveur/partage/etat/v3_event_store.db?mode=rw")
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            sqlite3.connect(rendu, uri=True)
        self.assertNotIn("authority", str(ctx.exception),
                         "SQLite refuse encore l'URI rendue pour son autorité")

    @unittest.skipUnless(hasattr(PureWindowsPath, "as_uri"),
                         "PurePath.as_uri retiré : forme Windows non rejouable hors Windows")
    def test_les_formes_deja_justes_ne_bougent_pas(self):
        self.assertEqual(self._uri(PureWindowsPath("C:/etat/x.db")),
                         "file:///C:/etat/x.db?mode=rw")
        self.assertEqual(self._uri(PurePosixPath("/etat/un store.db"), "?mode=ro&immutable=1"),
                         "file:///etat/un%20store.db?mode=ro&immutable=1")
        with self.assertRaises(ValueError):
            self._uri(PurePosixPath("relatif.db"))


class PointUniqueDesCheminsTests(_EnvMixin):
    """F8 : `chemins_des_stores` est le seul site qui résout les chemins ABSOLUS ;
    `init_surfaces.STORES` porte en RELATIF le seul store qui vit encore sous la
    racine (`events.db`). Les deux doivent désigner les MÊMES fichiers — et
    l'index, sorti de `STORES` par T-00000668, doit être HORS de la racine, au
    point unique `cadre.paths.index_db`."""

    def test_STORES_egale_chemins_des_stores(self):
        racine = self._racine_nue()
        chemins = stores.chemins_des_stores(racine)
        sous_la_racine = {c.relative_to(racine).as_posix()
                          for c in (chemins.v3_event_store, chemins.events, chemins.index)
                          if c.is_relative_to(racine)}
        self.assertTrue(STORES, "init_surfaces.STORES vide — banc non armé")
        self.assertEqual({s.chemin for s in STORES}, sous_la_racine)
        self.assertEqual(sous_la_racine, {chemins.events.relative_to(racine).as_posix()})
        self.assertEqual(chemins.index, index_db(racine),
                         "l'index ne vient pas du point unique cadre.paths.index_db")


class GardeFouColonnesTests(unittest.TestCase):
    """`schema.COLONNES` (l'ordre canonique sur lequel `lessons.py` aligne ses
    INSERT) doit ÉGALER les colonnes réelles du DDL — mesurées par exécution sur
    un store réel, jamais un `len()` qui laisserait passer un écart de NOMS."""

    def _colonnes_reelles(self) -> tuple[str, ...]:
        with tempfile.TemporaryDirectory() as d:
            conn = store.connect(Path(d) / "lecons.db")
            try:
                version.garantir_schema(conn)
                return tuple(r["name"] for r in conn.execute(
                    "PRAGMA table_info(" + schema.TABLE + ")"))
            finally:
                conn.close()

    def test_schema_COLONNES_egale_les_colonnes_reelles_du_DDL(self):
        reelles = self._colonnes_reelles()
        self.assertTrue(reelles, "PRAGMA table_info vide — store non peuplé")
        self.assertEqual(
            set(schema.COLONNES), set(reelles),
            "écart de NOMS entre schema.COLONNES et le DDL réel.\n  en trop : "
            + str(sorted(set(schema.COLONNES) - set(reelles)))
            + "\n  manquants : " + str(sorted(set(reelles) - set(schema.COLONNES))))
        self.assertEqual(
            tuple(schema.COLONNES), reelles,
            "COLONNES et le DDL réel divergent en ORDRE — les INSERT positionnels "
            "de lessons.py s'y aligneraient de travers.")


if __name__ == "__main__":
    unittest.main()
