#!/usr/bin/env python3
"""Banc du lot C de T-01M51Q7GJ1B6315SFKNDAAE2P0 — `etat_projection.py` et son écrivain dans le démon.

Les témoins de l'annexe A3 C, chacun écrit pour ROUGIR sous le mutant qu'il nomme, plus les réserves du verdict
plan-critic 2/8 qui touchent ce lot : C1 (`lire` rend None dès qu'une source est `degraded`, parité base/direct),
C2 (chargement sous le verrou de construction du snapshot), C3 (aucun nom de magasin écrit en dur), C7 (couture
`cadre.paths`), C8 (`lire` ne lève jamais, classes non attrapées comprises), C9 (≤ 1600 lignes).

ISOLATION (C4, L-00000076, L-00000537) : chaque cas redirige `AGENTS_ETAT_DB`, `CADRE_STATE_DIR` et, pour le
démon, `AGENTS_EVENTS_DIR`, `AGENTS_OTEL_DIR`, `AGENTS_EVENTS_DB`, `AGENTKIT_REGISTRY`, `AGENTS_PROJECT_JSON`
vers un répertoire jetable ; `_start_ingest_loop` est TOUJOURS un espion quand `run_daemon` tourne avec
`with_ingest=True` — jamais l'events.db du développeur.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAGIE_SQLITE = b"SQLite format 3\x00"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ep = _load("_test_etat_projection", HERE / "etat_projection.py")
daemon = _load("_test_etat_daemon", HERE / "dashboard_daemon.py")
# T-01M5BXTPQE3JZV3KZA6WD9P5XC lot Q : le paquet `cadre` d'une racine vient du résolveur chargé PAR CHEMIN
# (`.agents/vendor/cadre`, sinon `src/cadre`), jamais d'un `src/cadre` écrit en dur ni d'un `sys.path` modifié.
vendor_paths = _load("_test_etat_vendor_paths", HERE / "vendor_paths.py")


def _paths_attendu(racine: Path) -> Path:
    """Le `cadre/paths.py` que la couture doit charger sous `racine` : celui du paquet que la règle désigne."""
    return vendor_paths.exiger(racine, "cadre") / "paths.py"

# A2.1 recopiée en LITTÉRAUX : (nom, type, notnull, pk) par colonne, dans l'ordre du DDL.
A2_1: dict[str, list[tuple[str, str, int, int]]] = {
    "meta": [("cle", "TEXT", 0, 1), ("valeur", "TEXT", 1, 0)],
    "specs": [("id", "TEXT", 0, 1), ("rang", "INTEGER", 1, 0), ("task", "TEXT", 1, 0), ("kind", "TEXT", 1, 0),
              ("date", "TEXT", 1, 0), ("tier", "INTEGER", 1, 0), ("num", "INTEGER", 0, 0),
              ("valeur", "TEXT", 1, 0), ("pli", "TEXT", 1, 0), ("sha", "TEXT", 1, 0), ("corps", "TEXT", 1, 0)],
    "journal_ledger": [("id", "TEXT", 0, 1), ("rang", "INTEGER", 1, 0), ("category", "TEXT", 1, 0),
                       ("status", "TEXT", 1, 0), ("created", "TEXT", 1, 0), ("tier", "INTEGER", 1, 0),
                       ("num", "INTEGER", 0, 0), ("valeur", "TEXT", 1, 0), ("pli", "TEXT", 1, 0),
                       ("sha", "TEXT", 1, 0), ("corps", "TEXT", 1, 0)],
    "sources": [("nom", "TEXT", 0, 1), ("empreinte", "TEXT", 1, 0), ("statut", "TEXT", 1, 0),
                ("raison", "TEXT", 0, 0)],
}
# Le motif R-B1, recopié de test_cadre_ledger_precedence.surfaces_grep (témoin d'égalité ci-dessous).
MOTIF_RB1 = ('lessons_learned|LESSONS\\.md|CREATE TABLE.*(lesson|lecon)|'
             'TABLE = "lecons"|lecon_appliquee')
ULID = "01M5391RMK0000000000000000"


def _spec(n: int, **champs: Any) -> dict[str, Any]:
    entree = {"id": f"S-{n:08d}", "task": "T-1", "kind": "plan", "title": f"titre {n}", "date": "2026-10-16",
              "text": "", "files": []}
    entree.update(champs)
    return entree


def _lecon(n: int, **champs: Any) -> dict[str, Any]:
    entree = {"id": f"L-{n:08d}", "category": "lesson", "status": "active", "title": f"lecon {n}",
              "text": f"texte {n}", "created": "2026-10-16"}
    entree.update(champs)
    return entree


class EtatCase(unittest.TestCase):
    """Une racine de projet jetable et une base HORS de cette racine (`AGENTS_ETAT_DB`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name).resolve()
        self.racine = self.tmp / "projet"
        (self.racine / ".agents").mkdir(parents=True)
        self.etat = self.tmp / "machine" / "etat.db"
        self._horloge = 1_700_000_000_000_000_000
        env = mock.patch.dict(os.environ, {"AGENTS_ETAT_DB": str(self.etat),
                                           "CADRE_STATE_DIR": str(self.tmp / "state")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)
        self.addCleanup(self._tmp.cleanup)

    # -- écrivains de fixtures : la forme RÉELLE (journal SPECS, dossier LEDGER) ou le monolithe -----------
    def _dater(self, chemin: Path) -> None:
        """Chaque écriture reçoit un mtime STRICTEMENT croissant : l'empreinte bouge toujours."""
        self._horloge += 1_000_000_000
        os.utime(chemin, ns=(self._horloge, self._horloge))

    def ecrire_specs(self, entrees: list[dict[str, Any]], *, monolithe: bool = False) -> Path:
        if monolithe:
            chemin = ep._specs.store_path(self.racine)
            corps = json.dumps({"entries": entrees}, ensure_ascii=False)
        else:
            chemin = ep._specs.journal_store_path(self.racine)
            corps = "".join(ep._specs.journal_line(o) for o in [ep._specs.JOURNAL_HEADER, *entrees])
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(corps.encode("utf-8"))
        self._dater(chemin)
        return chemin

    def ecrire_ledger(self, entrees: list[dict[str, Any]], *, monolithe: bool = False) -> None:
        if monolithe:
            chemin = ep._ledger.store_path(self.racine)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(json.dumps({"entries": entrees}, ensure_ascii=False).encode("utf-8"))
            self._dater(chemin)
            return
        dossier = ep._ledger.entries_dir(self.racine)
        dossier.mkdir(parents=True, exist_ok=True)
        for vieux in dossier.glob("*.json"):
            if vieux.name[:-5] not in {e["id"] for e in entrees}:
                vieux.unlink()
        for entree in entrees:
            chemin = dossier / f"{entree['id']}.json"
            enveloppe = {"format": ep._ledger.RECORD_FORMAT, "id": entree["id"], "record": entree}
            chemin.write_bytes(json.dumps(enveloppe, ensure_ascii=False).encode("utf-8"))
            self._dater(chemin)

    def peupler(self, n_specs: int = 3, n_lecons: int = 2) -> None:
        self.ecrire_specs([_spec(i) for i in range(1, n_specs + 1)])
        self.ecrire_ledger([_lecon(i) for i in range(1, n_lecons + 1)])

    def brute(self) -> sqlite3.Connection:
        """Une connexion de CONTRÔLE à la base, hors de l'API sous test."""
        con = sqlite3.connect(str(self.etat))
        self.addCleanup(con.close)
        return con

    def corps_par_rang(self, con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        requete = {"specs": "SELECT corps FROM specs ORDER BY rang",
                   "journal_ledger": "SELECT corps FROM journal_ledger ORDER BY rang"}[table]
        return [json.loads(c) for (c,) in con.execute(requete)]


# ---------------------------------------------------------------------------
# A2.1 / A2.2 : le contrat lui-même.
# ---------------------------------------------------------------------------

class ContratTests(EtatCase):
    def test_ddl_egal_A2_1(self) -> None:
        """Mutant « colonne retirée » (ou type, NOT NULL, clé) → rouge."""
        self.peupler()
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        con = self.brute()
        tables = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertEqual(tables, set(A2_1))
        for table, colonnes in A2_1.items():
            with self.subTest(table=table):
                info = [tuple(r) for r in con.execute(
                    'SELECT name, type, "notnull", pk FROM pragma_table_info(?) ORDER BY cid', (table,))]
                self.assertEqual(info, colonnes)
        self.assertEqual(con.execute("SELECT cle, valeur FROM meta").fetchall(), [("schema", "1")])

    def test_ddl_hors_motif_R_B1(self) -> None:
        """Aucune ligne du module (DDL compris) ne porte le motif R-B1 ; le motif voit bien un mutant."""
        motif = re.compile(MOTIF_RB1, re.IGNORECASE)
        source = (HERE / "etat_projection.py").read_text(encoding="utf-8")
        self.assertEqual([ligne for ligne in source.splitlines() if motif.search(ligne)], [])
        self.assertEqual([d for d in ep.DDL if motif.search(d)], [])
        self.assertTrue(motif.search("CREATE TABLE lecons(id TEXT)"), "le motif est aveugle")
        precedence = (ROOT / ".agents" / "evals" / "test_cadre_ledger_precedence.py").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE.*(lesson|lecon)|", precedence, "le motif recopié a divergé de R-B1")

    def test_api_A2_2_signatures(self) -> None:
        def params(f: Any) -> list[tuple[str, Any]]:
            return [(p.name, p.kind) for p in inspect.signature(f).parameters.values()]
        positionnel = inspect.Parameter.POSITIONAL_OR_KEYWORD
        for f in (ep.chemin_base, ep.empreinte_sources, ep.lire):
            with self.subTest(f=f.__name__):
                self.assertEqual(params(f), [("racine", positionnel)])
        self.assertEqual(params(ep.rafraichir), [("racine", positionnel), ("verrou", inspect.Parameter.KEYWORD_ONLY)])
        self.assertEqual(params(ep.plier), [("s", positionnel)])
        self.assertEqual(set(ep.empreinte_sources(self.racine)), {"SPECS", "LEDGER"})

    def test_plier_vecteur_A2(self) -> None:
        self.assertEqual(ep.plier("Élève ÇA S-12"), "eleve ca s-12")
        self.assertEqual(ep.plier("Ångström"), "angstrom")

    def test_tier_num_valeur_vecteurs(self) -> None:
        """Port de recordTier ; mutant « num en TEXT » → `typeof(num)` rougit."""
        self.assertEqual(ep.rangement(f"S-{ULID}"), (2, None, ULID))
        self.assertEqual(ep.rangement("S-00000123"), (1, 123, ""))
        self.assertEqual(ep.rangement("T-12"), (1, 12, ""))
        self.assertEqual(ep.rangement("T-12 "), (1, 12, ""))
        self.assertEqual(ep.rangement("abc"), (0, None, "abc"))
        self.assertEqual(ep.rangement("S-١٢"), (0, None, "S-١٢"), "\\d du JS est ASCII")
        self.assertEqual(ep.rangement("S-" + ULID.lower()), (0, None, "S-" + ULID.lower()))
        self.ecrire_specs([_spec(123), {**_spec(1), "id": f"S-{ULID}"}])
        self.ecrire_ledger([])
        ep.rafraichir(self.racine)
        lignes = {r[0]: r[1:] for r in self.brute().execute(
            "SELECT id, tier, num, valeur, typeof(tier), typeof(num) FROM specs")}
        self.assertEqual(lignes["S-00000123"], (1, 123, "", "integer", "integer"))
        self.assertEqual(lignes[f"S-{ULID}"], (2, None, ULID, "integer", "null"))

    def test_corps_brut_sha_et_champs(self) -> None:
        """`corps` = `serialiser` de l'entrée chargée (`files` compris), `sha` = sha256 de ces octets ; champ
        absent → ''."""
        self.ecrire_specs([_spec(1, files=["a.py"], text="t")])
        self.ecrire_ledger([{k: v for k, v in _lecon(1).items()}])
        ep.rafraichir(self.racine)
        con = self.brute()
        charge = ep._specs.load(self.racine)["entries"][0]
        corps, sha, task, kind, date = con.execute("SELECT corps, sha, task, kind, date FROM specs").fetchone()
        self.assertEqual(corps.encode("utf-8"), ep._transport.serialiser(charge))
        self.assertEqual(sha, hashlib.sha256(corps.encode("utf-8")).hexdigest())
        self.assertEqual(json.loads(corps)["files"], ["a.py"])
        self.assertEqual((task, kind, date), ("T-1", "plan", "2026-10-16"))
        self.assertEqual(ep._ligne("LEDGER", "L-1", 0, {"id": "L-1"}, "{}", "x")[2:5], ("", "", ""))

    def test_pli_par_source(self) -> None:
        """SPECS : id, task, kind, title — jamais `text` ; LEDGER : text, text_preview, tags, related."""
        self.ecrire_specs([_spec(1, title="Décision Élevée", text="seulementdanstexte")])
        self.assertEqual(ep.foin("LEDGER", {"id": "L-1", "tags": ["a", None, ""], "related": {"x": 1}}),
                         "L-1    a [object Object]", "join JS : null → '', {} est VRAI")
        self.assertEqual(ep.foin("LEDGER", {"id": "L-1", "related": 0}), "L-1     ", "0 est FAUX en JS")
        self.ecrire_ledger([_lecon(1, text="Corps", text_preview="Aperçu", tags=["Étiquette", ""],
                                   related="T-9"),
                            _lecon(2, related=["T-7", "T-8"])])
        ep.rafraichir(self.racine)
        con = self.brute()
        (pli_s,) = con.execute("SELECT pli FROM specs").fetchone()
        self.assertEqual(pli_s, "s-00000001 t-1 plan decision elevee")
        self.assertNotIn("seulementdanstexte", pli_s)
        plis = dict(con.execute("SELECT id, pli FROM journal_ledger"))
        self.assertEqual(plis["L-00000001"], "l-00000001 lecon 1 corps apercu etiquette t-9")
        self.assertTrue(plis["L-00000002"].endswith(" t-7 t-8"))

    def test_recette_de_dashboard_readers_base(self) -> None:
        """La recette d'empreinte EST celle du snapshot (`_VIEW_SOURCE_FILES`, `_LEDGER_ENTRIES_REL`)."""
        fichiers = [rel for nom in ep.SOURCES for rel in ep._RECETTE[nom][0]]
        for rel in fichiers:
            self.assertIn(rel, ep._base._VIEW_SOURCE_FILES)
        self.assertEqual(ep._RECETTE["LEDGER"][1], (ep._base._LEDGER_ENTRIES_REL,))
        self.assertEqual(ep._RECETTE["SPECS"][1], ())


# ---------------------------------------------------------------------------
# L'écrivain : diff, ordre, verrou, empreinte prise en premier, crash.
# ---------------------------------------------------------------------------

class EcritureTests(EtatCase):
    def test_diff_ajout_modif_suppression(self) -> None:
        """Mutant « pas de DELETE » → l'entrée retirée reste → rouge."""
        self.ecrire_specs([_spec(1), _spec(2), _spec(3)])
        self.ecrire_ledger([_lecon(1), _lecon(2)])
        ep.rafraichir(self.racine)
        self.ecrire_specs([_spec(1), _spec(3, title="modifié"), _spec(4)])
        self.ecrire_ledger([_lecon(2)])
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        con = self.brute()
        self.assertEqual([e["id"] for e in self.corps_par_rang(con, "specs")], ["S-00000001", "S-00000003", "S-00000004"])
        self.assertEqual(self.corps_par_rang(con, "specs")[1]["title"], "modifié")
        self.assertEqual([e["id"] for e in self.corps_par_rang(con, "journal_ledger")], ["L-00000002"])

    def test_seules_les_lignes_qui_changent_sont_construites(self) -> None:
        """Les lignes passent en flux : seule celle qui change est construite (aucune liste du store entier)."""
        self.peupler(n_specs=3)
        ep.rafraichir(self.racine)
        self.ecrire_specs([_spec(1), _spec(2), _spec(3), _spec(4)])
        with mock.patch.object(ep, "_ligne", wraps=ep._ligne) as ligne:
            ep.rafraichir(self.racine)
        self.assertEqual([(c.args[0], c.args[1]) for c in ligne.call_args_list], [("SPECS", "S-00000004")])

    def test_rang_suit_le_store(self) -> None:
        """`rang` = position dans le store CHARGÉ (le monolithe garde l'ordre du fichier) ; mutant « rang = ordre
        des id » → rouge."""
        self.ecrire_specs([_spec(3), _spec(1), _spec(2)], monolithe=True)
        self.ecrire_ledger([], monolithe=True)
        ep.rafraichir(self.racine)
        rangs = dict(self.brute().execute("SELECT id, rang FROM specs"))
        self.assertEqual(rangs, {"S-00000003": 0, "S-00000001": 1, "S-00000002": 2})
        self.ecrire_specs([_spec(2), _spec(3), _spec(1)], monolithe=True)
        ep.rafraichir(self.racine)
        rangs = dict(self.brute().execute("SELECT id, rang FROM specs"))
        self.assertEqual(rangs, {"S-00000002": 0, "S-00000003": 1, "S-00000001": 2})

    def test_tick_sans_changement_aucun_load(self) -> None:
        """Mutant « load à chaque tick » → rouge ; seule la source modifiée est rechargée."""
        self.peupler()
        ep.rafraichir(self.racine)
        with mock.patch.object(ep._specs, "load", wraps=ep._specs.load) as specs_load, \
                mock.patch.object(ep._ledger, "load", wraps=ep._ledger.load) as ledger_load:
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
            self.assertEqual((specs_load.call_count, ledger_load.call_count), (0, 0))
            self.ecrire_specs([_spec(1), _spec(9)])
            ep.rafraichir(self.racine)
            self.assertEqual((specs_load.call_count, ledger_load.call_count), (1, 0))

    def test_C2_chargement_sous_le_verrou_du_snapshot(self) -> None:
        """Chaque chargement d'un journal a lieu verrou TENU, et le verrou est rendu ; mutant « load hors
        verrou » → rouge."""
        self.peupler()
        verrou = threading.Lock()
        vus: list[bool] = []
        vrai_specs, vrai_ledger = ep._specs.load, ep._ledger.load

        def espion(vrai: Any) -> Any:
            def charger(racine: Any) -> Any:
                vus.append(verrou.locked())
                return vrai(racine)
            return charger
        with mock.patch.object(ep._specs, "load", espion(vrai_specs)), \
                mock.patch.object(ep._ledger, "load", espion(vrai_ledger)):
            self.assertEqual(ep.rafraichir(self.racine, verrou=verrou), {"SPECS": "ok", "LEDGER": "ok"})
        self.assertEqual(vus, [True, True])
        self.assertFalse(verrou.locked(), "le verrou du snapshot doit être rendu")

    def test_C2_verrou_occupe_reporte_le_tick_sans_rien_ecrire(self) -> None:
        self.peupler()
        verrou = mock.Mock()
        verrou.acquire.return_value = False
        with mock.patch.object(ep._specs, "load") as specs_load:
            statuts = ep.rafraichir(self.racine, verrou=verrou)
        specs_load.assert_not_called()
        verrou.release.assert_not_called()
        self.assertEqual(statuts, {"SPECS": "degraded", "LEDGER": "degraded"})
        self.assertEqual(self.brute().execute("SELECT count(*) FROM sources").fetchone(), (0,))

    def test_empreinte_prise_en_premier(self) -> None:
        """Un journal modifié PENDANT le chargement : l'empreinte stockée est l'ancienne, `lire` rend None, le
        tick suivant reprend ; mutant « empreinte prise après le load » → `lire` sert du périmé → rouge."""
        self.peupler()
        vrai = ep._specs.load

        def charger_puis_ecrire(racine: Any) -> Any:
            donnees = vrai(racine)
            self.ecrire_specs([_spec(1), _spec(2), _spec(3), _spec(4)])
            return donnees
        with mock.patch.object(ep._specs, "load", charger_puis_ecrire):
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        self.assertIsNone(ep.lire(self.racine), "une base plus vieille que le disque est servie pour à jour")
        ep.rafraichir(self.racine)
        con = ep.lire(self.racine)
        self.assertIsNotNone(con)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT count(*) FROM specs").fetchone(), (4,))

    def test_crash_mi_transaction_puis_reprise(self) -> None:
        """Un VRAI crash (`os._exit`) entre les poses et la ligne `sources` : la transaction n'a pas eu lieu,
        `lire` rend None, puis le tick suivant reprend."""
        self.peupler(n_specs=2)
        ep.rafraichir(self.racine)
        self.ecrire_specs([_spec(1), _spec(2), _spec(3)])
        script = (
            "import importlib.util, os, sys\n"
            "from pathlib import Path\n"
            "spec = importlib.util.spec_from_file_location('_crash_ep', sys.argv[1])\n"
            "ep = importlib.util.module_from_spec(spec); sys.modules[spec.name] = ep; spec.loader.exec_module(ep)\n"
            "ouvrir = ep._ouvrir_ecrivain\n"
            "class Mandataire:\n"
            "    def __init__(self, con): self._con = con\n"
            "    def execute(self, sql, *args):\n"
            "        if sql.startswith('INSERT OR REPLACE INTO sources'): os._exit(3)\n"
            "        return self._con.execute(sql, *args)\n"
            "    def __getattr__(self, nom): return getattr(self._con, nom)\n"
            "ep._ouvrir_ecrivain = lambda *a: Mandataire(ouvrir(*a))\n"
            "ep.rafraichir(Path(sys.argv[2]))\n"
            "os._exit(0)\n"
        )
        fin = subprocess.run([sys.executable, "-c", script, str(HERE / "etat_projection.py"), str(self.racine)],
                             env=dict(os.environ), capture_output=True, timeout=60, check=False)
        self.assertEqual(fin.returncode, 3, fin.stderr.decode("utf-8", "replace"))
        self.assertIsNone(ep.lire(self.racine))
        self.assertEqual(self.brute().execute("SELECT count(*) FROM specs").fetchone(), (2,))
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        con = ep.lire(self.racine)
        self.assertIsNotNone(con)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT count(*) FROM specs").fetchone(), (3,))

    def test_base_supprimee_reconstruite(self) -> None:
        self.peupler()
        ep.rafraichir(self.racine)
        for suffixe in ("", "-wal", "-shm"):
            self.etat.with_name("etat.db" + suffixe).unlink(missing_ok=True)
        self.assertFalse(self.etat.exists())
        self.assertIsNone(ep.lire(self.racine))
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        con = ep.lire(self.racine)
        self.assertIsNotNone(con)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT count(*) FROM specs").fetchone(), (3,))

    def _fichiers_etrangers(self) -> dict[str, bytes]:
        """Les quatre fichiers qu'aucun chemin forcé n'accepte, en octets : non SQLite, vide, SQLite d'autrui,
        etat.db d'un autre schéma (posée en mode `delete` : aucune connexion n'y laisse de -wal)."""
        def sqlite(*instructions: str) -> bytes:
            chemin = self.tmp / f"fabrique-{len(instructions)}-{instructions[0][:12].replace(' ', '_')}.db"
            con = sqlite3.connect(str(chemin))
            for instruction in instructions:
                con.execute(instruction)
            con.commit()
            con.close()
            return chemin.read_bytes()
        return {
            "non sqlite": b"donnees precieuses d'autrui\n" * 50,
            "vide": b"",
            "sqlite d'autrui": sqlite("CREATE TABLE comptes(id INTEGER PRIMARY KEY, solde INTEGER)",
                                      "INSERT INTO comptes VALUES (1, 100)"),
            "autre schéma": sqlite(*ep.DDL, "INSERT INTO meta(cle, valeur) VALUES ('schema', '2')"),
        }

    def test_securite_chemin_force_fichier_etranger_refuse_intact(self) -> None:
        """Avis S-01M53CAX4W (MEDIUM) : au chemin forcé, un fichier existant sans `meta.schema='1'` est REFUSÉ —
        mêmes octets, aucun -wal/-shm né, aucun DROP ; mutant « refaire ce qui n'est pas à jour » → rouge."""
        self.peupler()
        self.etat.parent.mkdir(parents=True, exist_ok=True)
        for nom, octets in self._fichiers_etrangers().items():
            with self.subTest(fichier=nom):
                self.etat.write_bytes(octets)
                self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "degraded"})
                self.assertEqual(self.etat.read_bytes(), octets, "un fichier étranger a été modifié")
                self.assertFalse(self.etat.with_name("etat.db-wal").exists())
                self.assertIsNone(ep.lire(self.racine))
                self.etat.unlink()

    def test_securite_chemin_par_defaut_jamais_supprime_ni_drop_chez_autrui(self) -> None:
        """Au chemin par défaut : un fichier non SQLite, une base d'autrui ou corrompue restent INTACTS ; une base
        NÔTRE d'un autre schéma est refaite ; un fichier vide (crash de la 1re création) est initialisé."""
        os.environ.pop("AGENTS_ETAT_DB")
        os.environ["CADRE_PROJECT_ROOT"] = str(self.racine)
        self.peupler()
        base = ep.chemin_base(self.racine)
        base.parent.mkdir(parents=True, exist_ok=True)
        etrangers = self._fichiers_etrangers()
        attendu = {"non sqlite": "refus", "sqlite d'autrui": "refus", "autre schéma": "refaite", "vide": "refaite"}
        for nom, octets in etrangers.items():
            with self.subTest(fichier=nom):
                base.write_bytes(octets)
                statuts = ep.rafraichir(self.racine)
                if attendu[nom] == "refus":
                    self.assertEqual(statuts, {"SPECS": "degraded", "LEDGER": "degraded"})
                    self.assertEqual(base.read_bytes(), octets, "un fichier d'autrui a été modifié")
                else:
                    self.assertEqual(statuts, {"SPECS": "ok", "LEDGER": "ok"})
                    self.assertIsNotNone(ep.lire(self.racine))
                for suffixe in ("", "-wal", "-shm"):
                    base.with_name("etat.db" + suffixe).unlink(missing_ok=True)

    def test_securite_droits_0700_et_0600(self) -> None:
        """Avis S-01M53CAX4W (LOW) : le dossier créé en 0o700, la base et ses -wal/-shm en 0o600, une base
        existante trop ouverte resserrée ; mutant « droits par défaut » → rouge."""
        if os.name == "nt":
            self.skipTest("droits POSIX")
        self.peupler()
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        self.assertEqual(stat.S_IMODE(self.etat.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.etat.stat().st_mode), 0o600)
        lecteur = ep.lire(self.racine)  # tient la base ouverte : ses -wal/-shm survivent à l'écrivain
        self.addCleanup(lecteur.close)
        os.chmod(self.etat, 0o644)
        self.ecrire_specs([_spec(1), _spec(7)])
        ep.rafraichir(self.racine)
        for suffixe in ("", "-wal", "-shm"):
            with self.subTest(fichier="etat.db" + suffixe):
                chemin = self.etat.with_name("etat.db" + suffixe)
                self.assertTrue(chemin.exists())
                self.assertEqual(stat.S_IMODE(chemin.stat().st_mode), 0o600)

    def test_securite_plafonds_taille_et_entrees(self) -> None:
        """Avis S-01M53CAX4W (LOW) : au-delà du plafond de taille, `degraded` SANS chargement ; au-delà du
        plafond d'entrées, `degraded` ; mutant « sans plafond » → rouge."""
        self.peupler()
        with mock.patch.object(ep, "_TAILLE_MAX", 10), \
                mock.patch.object(ep._specs, "load", wraps=ep._specs.load) as specs_load:
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "degraded"})
        specs_load.assert_not_called()
        raison = self.brute().execute("SELECT raison FROM sources WHERE nom = 'SPECS'").fetchone()[0]
        self.assertIn("plafond de taille", raison)
        self.assertIsNone(ep.lire(self.racine))
        self.ecrire_specs([_spec(1), _spec(2)])
        with mock.patch.object(ep, "_ENTREES_MAX", 1):
            self.assertEqual(ep.rafraichir(self.racine)["SPECS"], "degraded")
        self.assertIsNone(ep.lire(self.racine))
        self.ecrire_specs([_spec(1)])
        self.assertEqual(ep.rafraichir(self.racine)["SPECS"], "ok")

    def _borne(self, fifos: list[Path], delai: float = 5.0) -> tuple[bool, Any]:
        """`rafraichir` dans un fil borné ; s'il bloque, chaque FIFO est débloquée (une ouverture en écriture
        rend EOF au lecteur bloqué) : le cas ROUGIT, il ne fige jamais le banc."""
        resultat: dict[str, Any] = {}
        fil = threading.Thread(target=lambda: resultat.setdefault("r", ep.rafraichir(self.racine)), daemon=True)
        fil.start()
        fil.join(delai)
        fini = not fil.is_alive()
        if not fini:
            for fifo in fifos:
                try:
                    os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
                except OSError:
                    pass
            fil.join(delai)
        return fini, resultat.get("r")

    def test_fifo_au_chemin_de_la_base_ne_bloque_jamais(self) -> None:
        """Une FIFO au chemin de la base est 'etrangere' : refusée sans bloquer, laissée telle quelle ;
        mutant « open() bloquant » → le fil ne rend pas → rouge (exec-critic, fifo.out : rc 124)."""
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO POSIX")
        self.peupler()
        self.etat.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(self.etat)
        fini, statuts = self._borne([self.etat])
        self.assertTrue(fini, "rafraichir a bloqué sur la FIFO au chemin de la base")
        self.assertEqual(statuts, {"SPECS": "degraded", "LEDGER": "degraded"})
        self.assertTrue(stat.S_ISFIFO(self.etat.lstat().st_mode), "la FIFO a été remplacée")
        self.assertIsNone(ep.lire(self.racine))

    def test_nature_tout_ce_qui_n_est_pas_un_fichier_regulier_est_etrangere(self) -> None:
        """`_nature` : une FIFO (sans bloquer), un lien vers une VRAIE base, un dossier → 'etrangere' ; une base →
        'sqlite' ; mutants « sans S_ISREG » et « sans O_NOFOLLOW » → rouges."""
        if not hasattr(os, "mkfifo") or not hasattr(os, "symlink"):
            self.skipTest("FIFO et liens POSIX")
        self.peupler()
        ep.rafraichir(self.racine)
        fifo, lien, dossier = self.tmp / "fifo", self.tmp / "lien.db", self.tmp / "dossier"
        os.mkfifo(fifo)
        lien.symlink_to(self.etat)
        dossier.mkdir()
        self.assertEqual(ep._nature(self.etat), "sqlite")
        for chemin in (fifo, lien, dossier):
            with self.subTest(chemin=chemin.name):
                resultat: dict[str, str] = {}
                fil = threading.Thread(target=lambda c=chemin: resultat.setdefault("n", ep._nature(c)), daemon=True)
                fil.start()
                fil.join(5.0)
                if fil.is_alive():
                    os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
                    fil.join(5.0)
                    self.fail(f"_nature a bloqué sur {chemin.name}")
                self.assertEqual(resultat["n"], "etrangere")

    def test_securite_liens_et_fichiers_non_reguliers_refuses_dans_les_magasins(self) -> None:
        """Avis S-01M53CAX4W (LOW) : un journal qui est un lien (il compterait 0 octet au plafond), un dossier
        d'entrées qui est un lien, une entrée qui est un lien, une FIFO comme journal : la source est `degraded`
        SANS chargement, sans bloquer ; mutant « liens suivis » → rouge."""
        if not hasattr(os, "symlink") or not hasattr(os, "mkfifo"):
            self.skipTest("liens et FIFO POSIX")
        self.peupler()
        ep.rafraichir(self.racine)
        journal = ep._specs.journal_store_path(self.racine)
        ailleurs = self.tmp / "ailleurs"
        ailleurs.mkdir()
        dossier = ep._ledger.entries_dir(self.racine)

        def lien_journal() -> list[Path]:
            cible = ailleurs / "journal"
            cible.write_bytes(journal.read_bytes())
            journal.unlink()
            journal.symlink_to(cible)
            return []

        def fifo_journal() -> list[Path]:
            journal.unlink()
            os.mkfifo(journal)
            return [journal]

        def lien_dossier() -> list[Path]:
            cible = ailleurs / "entrees"
            dossier.rename(cible)
            dossier.symlink_to(cible, target_is_directory=True)
            return []

        def lien_entree() -> list[Path]:
            cible = ailleurs / "L-00000009.json"
            cible.write_bytes((dossier / "L-00000001.json").read_bytes())
            (dossier / "L-00000009.json").symlink_to(cible)
            return []
        for nom, geste, source in (("journal lié", lien_journal, "SPECS"), ("journal FIFO", fifo_journal, "SPECS"),
                                   ("dossier lié", lien_dossier, "LEDGER"), ("entrée liée", lien_entree, "LEDGER")):
            with self.subTest(cas=nom):
                fifos = geste()
                proprietaire = ep._specs if source == "SPECS" else ep._ledger
                with mock.patch.object(proprietaire, "load", wraps=proprietaire.load) as charge:
                    fini, statuts = self._borne(fifos)
                self.assertTrue(fini, "le tick a bloqué")
                self.assertEqual(statuts[source], "degraded")
                charge.assert_not_called()
                raison = self.brute().execute("SELECT raison FROM sources WHERE nom = ?", (source,)).fetchone()[0]
                self.assertIn("refusé, non chargé", raison)
                self.assertIsNone(ep.lire(self.racine))
            # remise en état : journal et dossier réels, sans entrée liée
            if journal.is_symlink() or journal.exists():
                journal.unlink()
            self.ecrire_specs([_spec(1), _spec(2), _spec(3)])
            if dossier.is_symlink():
                dossier.unlink()
                (ailleurs / "entrees").rename(dossier)
            (dossier / "L-00000009.json").unlink(missing_ok=True)
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"}, nom)

    def test_base_verrouillee_jamais_supprimee(self) -> None:
        """Une base VERROUILLÉE par un tiers pendant l'écriture : le tick rend `degraded` et laisse le fichier et
        ses lignes ; mutant « OperationalError traitée comme corruption » → rouge."""
        self.peupler()
        ep.rafraichir(self.racine)
        tiers = sqlite3.connect(str(self.etat), isolation_level=None)
        self.addCleanup(tiers.close)
        tiers.execute("BEGIN IMMEDIATE")
        inode = self.etat.stat().st_ino
        self.ecrire_specs([_spec(1), _spec(5)])
        with mock.patch.object(ep, "_ATTENTE_SECONDES", 0.2):
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "degraded"})
        self.assertEqual(self.etat.stat().st_ino, inode, "la base verrouillée a été supprimée puis refaite")
        tiers.execute("ROLLBACK")
        self.assertEqual(tiers.execute("SELECT count(*) FROM specs").fetchone(), (3,))
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})

    def test_identifiant_en_double_degraded(self) -> None:
        self.peupler()
        with mock.patch.object(ep._specs, "load", return_value={"entries": [_spec(1), _spec(1)]}):
            self.assertEqual(ep.rafraichir(self.racine)["SPECS"], "degraded")
        self.assertIsNone(ep.lire(self.racine))


# ---------------------------------------------------------------------------
# Le lecteur : None quand il faut, jamais d'exception, et la parité base/direct (C1).
# ---------------------------------------------------------------------------

class LectureTests(EtatCase):
    def test_lire_signature_et_None(self) -> None:
        """Base absente / schéma 2 / empreinte périmée → None ; à jour → une connexion EN LECTURE SEULE."""
        self.peupler()
        self.assertIsNone(ep.lire(self.racine), "base absente")
        self.assertFalse(self.etat.exists(), "lire ne crée jamais la base")
        ep.rafraichir(self.racine)
        con = ep.lire(self.racine)
        self.assertIsInstance(con, sqlite3.Connection)
        self.assertTrue(con.in_transaction, "les contrôles et la lecture partagent un instantané")
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM specs")
        con.close()
        self.ecrire_ledger([_lecon(1)])
        self.assertIsNone(ep.lire(self.racine), "empreinte périmée")
        ep.rafraichir(self.racine)
        brute = self.brute()
        brute.execute("UPDATE meta SET valeur = '2'")
        brute.commit()
        self.assertIsNone(ep.lire(self.racine), "schéma 2")

    def test_ro_voit_le_wal(self) -> None:
        """Mutant « immutable=1 » : le lecteur ignore le WAL et rend l'ancien corps → rouge."""
        self.peupler()
        ep.rafraichir(self.racine)
        ecrivain = sqlite3.connect(str(self.etat), isolation_level=None)
        self.addCleanup(ecrivain.close)
        ecrivain.execute("PRAGMA wal_autocheckpoint = 0")
        ecrivain.execute("UPDATE specs SET corps = 'marque-du-wal' WHERE id = 'S-00000001'")
        self.assertGreater(self.etat.with_name("etat.db-wal").stat().st_size, 0, "rien dans le WAL")
        con = ep.lire(self.racine)
        self.assertIsNotNone(con)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT corps FROM specs WHERE id = 'S-00000001'").fetchone(),
                         ("marque-du-wal",))

    def test_C1_source_illisible_degraded_tables_intactes_et_lire_None(self) -> None:
        """Mutant « tables intactes servies » (lire qui ignore `statut`) → rouge."""
        self.peupler()
        ep.rafraichir(self.racine)
        chemin = ep._specs.journal_store_path(self.racine)
        chemin.write_bytes(chemin.read_bytes() + b"{pas du json\n")
        self._dater(chemin)
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "ok"})
        con = self.brute()
        statut, raison = con.execute("SELECT statut, raison FROM sources WHERE nom = 'SPECS'").fetchone()
        self.assertEqual(statut, "degraded")
        self.assertTrue(raison)
        self.assertNotIn(str(self.racine), raison, "la raison ne porte pas la racine absolue")
        self.assertEqual(con.execute("SELECT count(*) FROM specs").fetchone(), (3,), "tables intactes")
        self.assertIsNone(ep.lire(self.racine))

    def test_C1_parite_base_direct_sur_chaque_etat(self) -> None:
        """Pour chaque état des sources, `lire` rend une connexion SI ET SEULEMENT SI la lecture directe lit les
        deux journaux, et alors la base rend EXACTEMENT leurs entrées, dans leur ordre."""
        self.peupler()
        specs_chemin = ep._specs.journal_store_path(self.racine)
        sain = specs_chemin.read_bytes()

        def casser_specs() -> None:
            specs_chemin.write_bytes(sain + b"{casse\n")
            self._dater(specs_chemin)

        def reparer_specs() -> None:
            specs_chemin.write_bytes(sain)
            self._dater(specs_chemin)

        # Les intrus du LEDGER sont HORS du champ d'une empreinte `*.json` : un `.json.orig` et un sous-dossier,
        # que le propriétaire refuse — le témoin rougit si l'empreinte ne voit pas tous les noms.
        entrees_dir = ep._ledger.entries_dir(self.racine)
        orig = entrees_dir / "L-00000001.json.orig"

        def casser_ledger_orig() -> None:
            orig.write_bytes((entrees_dir / "L-00000001.json").read_bytes())

        def reparer_ledger_orig() -> None:
            orig.unlink()

        def casser_ledger_dossier() -> None:
            (entrees_dir / "sousdossier").mkdir()

        def reparer_ledger_dossier() -> None:
            (entrees_dir / "sousdossier").rmdir()
        servies = 0
        for nom, geste in (("sain", lambda: None), ("specs illisible", casser_specs), ("réparé", reparer_specs),
                           ("ledger .json.orig", casser_ledger_orig), ("ledger réparé", reparer_ledger_orig),
                           ("ledger sous-dossier", casser_ledger_dossier),
                           ("ledger réparé 2", reparer_ledger_dossier)):
            with self.subTest(etat=nom):
                geste()
                ep.rafraichir(self.racine)
                direct: dict[str, Any] = {}
                for source, proprietaire in (("specs", ep._specs), ("journal_ledger", ep._ledger)):
                    try:
                        direct[source] = proprietaire.load(self.racine)["entries"]
                    except Exception:  # noqa: BLE001 - la lecture directe échoue : c'est l'état sous test
                        direct[source] = None
                con = ep.lire(self.racine)
                if None in direct.values():
                    self.assertIsNone(con, "la base sert des lignes là où la lecture directe n'en sert aucune")
                    continue
                self.assertIsNotNone(con)
                servies += 1
                for table, entrees in direct.items():
                    self.assertEqual(self.corps_par_rang(con, table), entrees)
                con.close()
        self.assertEqual(servies, 4, "témoin vide : la base n'a jamais été servie")

    def test_C1_tout_nom_du_dossier_est_dans_l_empreinte(self) -> None:
        """Un `.json.orig`, un `~`, un sous-dossier dans le dossier du LEDGER : le propriétaire les refuse, la
        base doit dire `degraded` et `lire` None ; mutant « empreinte sur `*.json` seuls » → rouge (exec-critic,
        c1a.out : la base servait 580 entrées là où la lecture directe levait)."""
        self.peupler()
        ep.rafraichir(self.racine)
        entrees_dir = ep._ledger.entries_dir(self.racine)
        premiere = entrees_dir / "L-00000001.json"
        for intrus in ("L-00000001.json.orig", "L-00000001.json~", "sousdossier"):
            with self.subTest(intrus=intrus):
                chemin = entrees_dir / intrus
                if intrus == "sousdossier":
                    chemin.mkdir()
                else:
                    chemin.write_bytes(premiere.read_bytes())
                with self.assertRaises(Exception):
                    ep._ledger.load(self.racine)
                self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "degraded"})
                self.assertIsNone(ep.lire(self.racine))
                chemin.rmdir() if chemin.is_dir() else chemin.unlink()
                self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
                self.assertIsNotNone(ep.lire(self.racine))

    def test_C1_droits_retires_bougent_l_empreinte(self) -> None:
        """`chmod 000` sur une entrée : mtime et taille ne bougent pas, la lecture directe lève ; l'empreinte voit
        le mode et le ctime ; mutant « signature (mtime, taille) seule » → rouge."""
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("droits POSIX d'un utilisateur non root")
        self.peupler()
        ep.rafraichir(self.racine)
        entree = ep._ledger.entries_dir(self.racine) / "L-00000002.json"
        os.chmod(entree, 0)
        self.addCleanup(os.chmod, entree, 0o644)
        with self.assertRaises(Exception):
            ep._ledger.load(self.racine)
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "degraded"})
        self.assertIsNone(ep.lire(self.racine))

    def test_C8_lire_ne_leve_jamais(self) -> None:
        """Toute classe, à la connexion comme à la lecture de `meta` ou de `sources`, rend None et ferme
        (L-00000495 : une classe NON nommée par le code est injectée aussi)."""
        self.peupler()
        ep.rafraichir(self.racine)
        classes = (OSError, PermissionError, sqlite3.DatabaseError, sqlite3.OperationalError, RuntimeError,
                   ValueError, KeyError)
        for classe in classes:
            with self.subTest(etape="connexion", classe=classe.__name__), self.assertLogs(level="WARNING"), \
                    mock.patch.object(ep, "_connecter_lecture", side_effect=classe("injecté")):
                self.assertIsNone(ep.lire(self.racine))
        for etape in ("BEGIN", "meta", "sources"):
            for classe in classes:
                vraie = ep._connecter_lecture(self.etat)
                self.addCleanup(vraie.close)
                fausse = mock.Mock()

                def executer(sql: str, *args: Any, _e: str = etape, _c: type = classe, _v: Any = vraie) -> Any:
                    if (_e == "BEGIN" and sql == "BEGIN") or (_e in sql):
                        raise _c("injecté")
                    return _v.execute(sql, *args)
                fausse.execute.side_effect = executer
                with self.subTest(etape=etape, classe=classe.__name__), self.assertLogs(level="WARNING"), \
                        mock.patch.object(ep, "_connecter_lecture", return_value=fausse):
                    self.assertIsNone(ep.lire(self.racine))
                    fausse.close.assert_called_once_with()
        with self.assertLogs(level="WARNING"), \
                mock.patch.object(ep, "empreinte_sources", side_effect=MemoryError("injecté")):
            self.assertIsNone(ep.lire(self.racine))
        self.assertIsNotNone(ep.lire(self.racine), "témoin vide : la base saine n'est jamais servie")


# ---------------------------------------------------------------------------
# Où vit la base : hors dépôt, par la couture cadre.paths (C7).
# ---------------------------------------------------------------------------

class EmplacementTests(EtatCase):
    def _sans_force(self) -> None:
        os.environ.pop("AGENTS_ETAT_DB")
        os.environ["CADRE_PROJECT_ROOT"] = str(self.racine)

    def _fichiers_sqlite(self, racine: Path) -> list[Path]:
        trouves = []
        for dossier, _sous, noms in os.walk(racine):
            for nom in noms:
                chemin = Path(dossier) / nom
                with open(chemin, "rb") as fh:
                    if fh.read(16) == MAGIE_SQLITE:
                        trouves.append(chemin)
        return trouves

    def test_chemin_sous_state_project_aucun_sqlite_dans_le_depot(self) -> None:
        """Mutant « chemin = racine du dépôt » → un fichier SQLite sous la racine → rouge."""
        self._sans_force()
        self.peupler()
        cp = ep._cadre_paths()
        attendu = Path(cp.state_project(depuis=self.racine)) / "etat.db"
        self.assertEqual(ep.chemin_base(self.racine), attendu)
        self.assertTrue(str(attendu).startswith(str(self.tmp / "state")), attendu)
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})
        self.assertEqual(attendu.read_bytes()[:16], MAGIE_SQLITE)
        self.assertIsNotNone(ep.lire(self.racine))
        self.assertEqual(self._fichiers_sqlite(self.racine), [])

    def test_cadre_introuvable_degraded_aucune_base(self) -> None:
        self._sans_force()
        self.peupler()
        with mock.patch.object(ep.importlib, "import_module", side_effect=ModuleNotFoundError("cadre")), \
                mock.patch.object(ep, "_CHEMIN_CADRE_PATHS", self.tmp / "absent" / "paths.py"), \
                mock.patch.object(ep, "_NOM_CADRE_PATHS_PAR_CHEMIN", "_cadre_paths_banc_absent"):
            self.assertIsNone(ep.chemin_base(self.racine))
            self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "degraded"})
            self.assertIsNone(ep.lire(self.racine))
            self.assertNotIn("_cadre_paths_banc_absent", sys.modules, "une copie ratée reste dans sys.modules")
        self.assertFalse((self.tmp / "state").exists(), "une base est née sans emplacement résolu")
        self.assertEqual(self._fichiers_sqlite(self.tmp), [])

    def test_couture_repli_par_chemin(self) -> None:
        """Paquet absent : le `cadre/paths.py` du clone (vendor ou `src`), chargé par chemin, résout l'emplacement."""
        self._sans_force()
        with mock.patch.object(ep.importlib, "import_module", side_effect=ModuleNotFoundError("cadre")):
            module = ep._cadre_paths()
            self.assertEqual(Path(module.__file__), _paths_attendu(ROOT))
            self.assertIsNotNone(ep.chemin_base(self.racine))

    def test_vendor_seul_q(self) -> None:
        """Témoin Q : sous une racine « les deux » (`.agents/vendor/cadre` ET `src/cadre`) comme « vendor seul »,
        le banc attend le paquet NEUF, et la couture charge ce fichier-là ; « ancien seul » : `src/cadre`.
        Mord : `_paths_attendu` rendu à `racine / "src" / "cadre"` (chemin en dur rétabli) → rouge."""
        dispositions = {"les deux": ("vendor", "src"), "vendor seul": ("vendor",), "ancien seul": ("src",)}
        for disposition, lieux in dispositions.items():
            with self.subTest(disposition=disposition):
                racine = self.tmp / disposition.replace(" ", "-")
                for lieu in lieux:
                    paquet = racine / (".agents/vendor/cadre" if lieu == "vendor" else "src/cadre")
                    paquet.mkdir(parents=True)
                    (paquet / "__init__.py").write_text("", encoding="utf-8")
                    (paquet / "paths.py").write_text(f"LIEU = {lieu!r}\n", encoding="utf-8")
                attendu = _paths_attendu(racine)
                self.assertEqual(ep._dossier_cadre(racine) / "paths.py", attendu, "banc et produit divergent")
                nom = f"_cadre_paths_banc_q_{lieux[0]}_{len(lieux)}"
                self.addCleanup(sys.modules.pop, nom, None)
                with mock.patch.object(ep.importlib, "import_module", side_effect=ModuleNotFoundError("cadre")), \
                        mock.patch.object(ep, "_CHEMIN_CADRE_PATHS", attendu), \
                        mock.patch.object(ep, "_NOM_CADRE_PATHS_PAR_CHEMIN", nom):
                    self.assertEqual(ep._cadre_paths().LIEU, lieux[0], disposition)

    def test_racine_resolue_differente_None(self) -> None:
        self._sans_force()
        autre = self.tmp / "autre"
        (autre / ".agents").mkdir(parents=True)
        os.environ["CADRE_PROJECT_ROOT"] = str(autre)
        self.assertIsNone(ep.chemin_base(self.racine))
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "degraded", "LEDGER": "degraded"})


# ---------------------------------------------------------------------------
# C3 (cliquet des lecteurs d'état) et C9 (taille).
# ---------------------------------------------------------------------------

class CliquetTests(unittest.TestCase):
    def test_C3_aucun_nom_de_magasin_ecrit_en_dur(self) -> None:
        """Le détecteur du cliquet ne voit rien dans les deux fichiers de production du lot ; il voit le
        mutant « un nom de magasin en dur »."""
        cliquet = _load("_test_etat_cliquet", ROOT / ".agents" / "evals" / "test_lecture_etat_cliquet.py")
        for nom in ("etat_projection.py", "dashboard_daemon.py"):
            with self.subTest(fichier=nom):
                self.assertEqual(cliquet.occurrences((HERE / nom).read_text(encoding="utf-8"), ".py"), 0)
        source = (HERE / "etat_projection.py").read_text(encoding="utf-8")
        mutant = source + '\n_X = (".agents", "state", "specs", "SPECS.jsonl")\n'
        self.assertGreater(cliquet.occurrences(mutant, ".py"), 0)

    def test_securite_aucune_suppression_de_fichier_dans_le_module(self) -> None:
        """Avis S-01M53CAX4W : l'écrivain ne supprime JAMAIS un fichier — aucun appel `unlink`, `remove`,
        `rmtree`, `rmdir` dans le module ; mutant « refaire une base corrompue en la supprimant » → rouge."""
        arbre = ast.parse((HERE / "etat_projection.py").read_text(encoding="utf-8"))
        appels = sorted({n.func.attr for n in ast.walk(arbre) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute)
                         and n.func.attr in ("unlink", "remove", "rmtree", "rmdir", "removedirs")})
        self.assertEqual(appels, [])
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "unlink"
                            for n in ast.walk(ast.parse("Path(x).unlink()"))), "le détecteur est aveugle")

    def test_C9_fichiers_sous_1600_lignes(self) -> None:
        for nom in ("etat_projection.py", "test_etat_projection.py", "dashboard_daemon.py"):
            with self.subTest(fichier=nom):
                self.assertLessEqual((HERE / nom).read_bytes().count(b"\n"), 1600)


# ---------------------------------------------------------------------------
# Le fil écrivain, et son câblage dans run_daemon (C47, C4, C2).
# ---------------------------------------------------------------------------

class BoucleTests(EtatCase):
    def test_premier_tick_tout_de_suite_puis_arret_borne(self) -> None:
        self.peupler()
        boucle = ep.Boucle(self.racine, verrou=threading.Lock(), periode=0.05)
        self.assertTrue(boucle.start())
        limite = time.monotonic() + 10.0
        while boucle.ticks < 2 and time.monotonic() < limite:
            time.sleep(0.02)
        self.assertTrue(boucle.stop(timeout=5.0))
        self.assertGreaterEqual(boucle.ticks, 2)
        self.assertIsNotNone(ep.lire(self.racine))

    def test_un_tick_qui_leve_ne_tue_pas_le_fil(self) -> None:
        with mock.patch.object(ep, "_rafraichir", side_effect=RuntimeError("injecté")), \
                self.assertLogs(level="WARNING"):
            boucle = ep.Boucle(self.racine, periode=0.02)
            boucle.start()
            limite = time.monotonic() + 10.0
            while boucle.ticks < 3 and time.monotonic() < limite:
                time.sleep(0.02)
            self.assertTrue(boucle.stop(timeout=5.0))
        self.assertGreaterEqual(boucle.ticks, 3)


class DemonTests(EtatCase):
    def setUp(self) -> None:
        super().setUp()
        identite = self.tmp / "project.json"
        identite.write_text(json.dumps({"project_id": f"banc-etat-{os.getpid()}", "name": "Banc"}),
                            encoding="utf-8")
        env = mock.patch.dict(os.environ, {
            "AGENTKIT_REGISTRY": str(self.tmp / "registry.json"), "AGENTS_PROJECT_JSON": str(identite),
            "AGENTS_EVENTS_DIR": str(self.tmp / "events"), "AGENTS_OTEL_DIR": str(self.tmp / "otel"),
            "AGENTS_EVENTS_DB": str(self.tmp / "events.db")})
        env.start()
        self.addCleanup(env.stop)

    def lancer(self, etat: Any = None, ingest_loop: Any = None,
               **kwargs: Any) -> tuple[mock.Mock, mock.Mock, list[Any]]:
        """`run_daemon` jusqu'à son arrêt sur inactivité, `_start_ingest_loop` ET `_start_etat_loop` espionnés."""
        ingest = mock.Mock(return_value=ingest_loop)
        espion_etat = mock.Mock(return_value=etat)
        serveurs: list[Any] = []
        vrai = daemon._dashboard.create_ui_server

        def creer(**kw: Any) -> Any:
            cree = vrai(**kw)
            serveurs.append(cree[0])
            return cree
        resultat: dict[str, Any] = {}
        with mock.patch.object(daemon, "_start_ingest_loop", ingest), \
                mock.patch.object(daemon, "_start_etat_loop", espion_etat), \
                mock.patch.object(daemon._dashboard, "create_ui_server", side_effect=creer):
            fil = threading.Thread(target=lambda: resultat.setdefault("code", daemon.run_daemon(
                self.racine, idle_seconds=0.3, poll_seconds=0.05, with_otel=False, **kwargs)), daemon=True)
            fil.start()
            fil.join(timeout=60.0)
        self.assertFalse(fil.is_alive(), "le démon ne s'est pas arrêté")
        self.assertEqual(resultat.get("code"), 0)
        return ingest, espion_etat, serveurs

    def test_C47_defaut_with_etat_vrai(self) -> None:
        """`run_daemon(with_ingest=True)` SANS kwarg → le fil d'état démarre une fois ; mutant « défaut False »
        → rouge."""
        ingest, etat, _ = self.lancer(with_ingest=True)
        self.assertEqual(ingest.call_count, 1)
        self.assertEqual(etat.call_count, 1)
        self.assertIs(inspect.signature(daemon.run_daemon).parameters["with_etat"].default, True)

    def test_with_etat_false_aucun_fil(self) -> None:
        """Mutant « with_etat ignoré » → rouge."""
        ingest, etat, _ = self.lancer(with_ingest=True, with_etat=False)
        self.assertEqual(ingest.call_count, 1)
        etat.assert_not_called()

    def test_sans_ingest_aucun_fil_d_etat(self) -> None:
        ingest, etat, _ = self.lancer(with_ingest=False)
        ingest.assert_not_called()
        etat.assert_not_called()

    def test_C2_le_demon_passe_le_verrou_du_snapshot(self) -> None:
        _, etat, serveurs = self.lancer(with_ingest=True)
        racine, verrou = etat.call_args.args
        self.assertEqual(Path(racine), daemon.normalize_root(self.racine))
        self.assertIs(verrou, serveurs[0].snapshot_memo.verrou)

    def test_arret_joint_le_fil_d_etat_et_garde_le_verrou_s_il_tient(self) -> None:
        """Un fil d'état qui ne s'arrête pas dans sa borne laisse le verrou du démon EN PLACE (écrivain unique
        avant propreté) ; arrêté, le verrou est retiré."""
        tenace = mock.Mock()
        tenace.stop.return_value = False
        erreurs = io.StringIO()
        with contextlib.redirect_stderr(erreurs):
            self.lancer(etat=tenace, with_ingest=True)
        tenace.stop.assert_called_once()
        self.assertTrue(0.0 < tenace.stop.call_args.kwargs["timeout"] <= daemon._ETAT_JOIN_SECONDS)
        self.assertTrue(daemon.lock_path(self.racine).exists())
        self.assertIn("reclaimed by liveness", erreurs.getvalue())
        self.assertNotIn("by age", erreurs.getvalue())
        daemon.lock_path(self.racine).unlink()
        docile = mock.Mock()
        docile.stop.return_value = True
        self.lancer(etat=docile, with_ingest=True)
        docile.stop.assert_called_once()
        self.assertFalse(daemon.lock_path(self.racine).exists())

    def test_arret_les_deux_signaux_avant_la_premiere_jointure_et_une_borne_partagee(self) -> None:
        """Les deux fils reçoivent leur signal d'arrêt AVANT la première jointure, et leurs jointures partagent
        UNE borne : un arrêt dégradé coûte une borne, jamais deux ; mutants « signal posé par stop() seul » et
        « borne pleine pour chaque fil » → rouges."""
        gestionnaire = mock.Mock()

        def ingest_lente(timeout: float | None = None) -> bool:
            time.sleep(0.3)
            return True
        gestionnaire.ingest.stop.side_effect = ingest_lente
        gestionnaire.etat.stop.return_value = True
        with mock.patch.object(daemon, "_INGEST_JOIN_SECONDS", 0.5), \
                mock.patch.object(daemon, "_ETAT_JOIN_SECONDS", 0.5):
            self.lancer(etat=gestionnaire.etat, ingest_loop=gestionnaire.ingest, with_ingest=True)
        appels = [c[0] for c in gestionnaire.mock_calls]
        premiere_jointure = min(appels.index("ingest.stop"), appels.index("etat.stop"))
        self.assertLess(appels.index("etat.signaler_arret"), premiere_jointure, appels)
        self.assertLess(appels.index("ingest.stop_event.set"), premiere_jointure, appels)
        self.assertLessEqual(gestionnaire.etat.stop.call_args.kwargs["timeout"], 0.5 - 0.25,
                             "la jointure du fil d'état n'a pas partagé la borne de l'ingestion")

    def test_start_etat_loop_reel_ecrit_la_base_puis_s_arrete(self) -> None:
        self.peupler()
        boucle = daemon._start_etat_loop(self.racine, threading.Lock())
        self.assertIsNotNone(boucle)
        limite = time.monotonic() + 10.0
        while ep.lire(self.racine) is None and time.monotonic() < limite:
            time.sleep(0.05)
        self.assertTrue(boucle.stop(timeout=daemon._ETAT_JOIN_SECONDS))
        self.assertIsNotNone(ep.lire(self.racine), "le premier tick n'a pas écrit la base")

    def test_start_etat_loop_degrade_sans_module(self) -> None:
        with mock.patch.object(daemon, "_load_sibling", side_effect=ImportError("absent")):
            self.assertIsNone(daemon._start_etat_loop(self.racine, None))


if __name__ == "__main__":
    unittest.main()
