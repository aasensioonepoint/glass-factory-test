#!/usr/bin/env python3
"""T-00001008 (BK-415, E-26) : le format « un fichier par enregistrement » et la projection machine des
corrélations — fonctions PURES de `tasks_stockage.py` (`RECORD_FORMAT`, `record_file`, `record_bytes`,
`explode_store`, `assemble_store`, `correlation_projection`, `read_records`), avec leur banc aller-retour.

Témoins W1-W9 du plan `docs/tasks/T-00001008-plan.md` rév. 1 ; W10, réserve C4 du plan-critic (le board RÉEL,
dépôt-kit seul) ; W11, delta de clôture de T-1058 (S-01M4M2E77V0ZPRSDHSNR65SS8K) : aucun chemin d'écriture ne
transite par un dict nu — l'objet `_BoardCharge` passé à l'éclatement garde sa vue O2, une corrélation acquittée
(qui ne vit plus que dans TASKS.json) et une clé de suppression (permanente, README.md:113) restent dans les
fichiers. Chaque témoin est ROUGE sur la BASE (les fonctions n'existent pas) ; le mutant que chacun tue est nommé
dans sa docstring et se joue sur une COPIE jetable des parties (L-00000487), jamais sur le fichier que
`tasks.py` charge. T-00001009 ajoute les réserves K2 de T-1008 — W1b, W4b à W4e, VERTS à leur base et ROUGES
sous leur mutant N — et W9c (`record_bytes_pour`, la collection passée) ; W10 lit le board dans sa forme.

Décisions pilote tenues : S-01M4JN56JEQ0XS97K38CDWBTW6 (le lien opération ↔ tâche est un champ
`sync_operations` DANS l'enregistrement de la tâche, la table est sa projection inversée) ;
S-01M4JN56NB05914VWW942W214X (« compatible » s'entend à la LIGNE : deux champs voisins d'un même enregistrement
conflictent encore — borne écrite, W8 (c) ; la fusion par champ est une autre tâche).

Montage : `tasks.py` chargé par chemin (`spec_from_file_location`), une racine jetable par témoin sous
`tempfile`, `CADRE_STATE_DIR` / `AGENTS_EVENTS_DIR` / `TMPDIR` posés. Fusion git (W8) : dépôt jetable, identité
en config LOCALE, hooks coupés, configs système et globale écartées. Fixtures SYNTHÉTIQUES, sauf W10, qui lit
les magasins du dépôt-kit en LECTURE seule. Aucun parcours d'arbre : `iterdir()` sur des dossiers connus.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("tasks_enregistrement_banc", HERE / "tasks.py")
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

TACHES = ("tasks", "epics")
ENTREES = ("entries",)
BOARD_REL = Path(".agents") / "state" / "board"
TASKS_REL = BOARD_REL / "TASKS.json"
OUTBOX_REL = BOARD_REL / "sync_outbox"
MARQUEUR_KIT = Path(".agents") / "IS_THE_KIT"
# Les deux magasins d'ENTRÉES du kit, lus par leur MODULE (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : `load` lit la forme présente
# — monolithe, dossier `memory/entries/` ou journal `SPECS.jsonl`.
MAGASINS_ENTREES = ("ledger.py", "specs.py")
ULID_A = "T-01AAAAAAAAAAAAAAAAAAAAAAAA"
ULID_B = "T-01BBBBBBBBBBBBBBBBBBBBBBBB"
JOUR = "2026-10-11"


def canon(objet: Any) -> bytes:
    """La sérialisation de `save()` (le `publie` de TASKS.json) et des intents O2 : la RÉFÉRENCE du banc."""
    return (json.dumps(objet, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def tache(tid: str, titre: str, state: str = "pending", stage: str = "") -> dict[str, Any]:
    return {"id": tid, "owner": "", "stage": stage, "state": state, "task": titre, "updated": JOUR}


def vivante(tid: str) -> dict[str, Any]:
    return {"board_task_id": tid, "tombstoned": False}


def magasin() -> dict[str, Any]:
    """Board synthétique de W1 : alias court et long (`T-012`, `T-00000013`), `T-999` avant `T-1000` (ordre
    NUMÉRIQUE), un ULID, deux epics, des corrélations vivantes, une tâche sans corrélation (`T-999`) et une tâche
    SUPPRIMÉE dont les deux clés sont tombées (`T-00000177` : la tombe)."""
    return {
        "epics": [{"id": "E-01", "titre": "un"}, {"id": "E-02", "titre": "deux"}],
        "sync_correlations": {
            "op-012": vivante("T-012"),
            "op-013": vivante("T-00000013"),
            "op-1000": vivante("T-1000"),
            "op-177-creation": {"board_task_id": "T-00000177", "tombstoned": True},
            "op-177-suppression": {"board_task_id": "T-00000177", "tombstoned": True},
            "op-ulid": vivante(ULID_A),
        },
        "tasks": [
            tache("T-012", "douze"),
            tache("T-00000013", "treize — été"),
            tache("T-999", "sans corrélation"),
            tache("T-1000", "mille", state="running"),
            tache(ULID_A, "un ULID"),
        ],
    }


def poser(dossier: Path, fichiers: dict[str, bytes], collections: tuple[str, ...]) -> None:
    """L'écrivain DU BANC (T-1008 n'en pose aucun) : chaque fichier de l'éclatement, et le retrait de ceux qu'il
    ne produit plus, dans chaque dossier de collection."""
    for collection in collections:
        sous = dossier / collection
        if sous.is_dir():
            for chemin in sous.glob("*.json"):
                if f"{collection}/{chemin.name}" not in fichiers:
                    chemin.unlink()
    for nom, octets in fichiers.items():
        (dossier / nom).parent.mkdir(parents=True, exist_ok=True)
        (dossier / nom).write_bytes(octets)


def cliche(dossier: Path, collections: tuple[str, ...]) -> dict[str, Any]:
    """Les noms du dossier et les octets de chaque fichier de ses dossiers de collection (deux niveaux CONNUS)."""
    vue: dict[str, Any] = {"": sorted(p.name for p in dossier.iterdir())}
    for collection in collections:
        sous = dossier / collection
        if sous.is_dir():
            vue.update({f"{collection}/{p.name}": p.read_bytes() for p in sous.iterdir() if p.is_file()})
    return vue


def git(depot: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    p = subprocess.run(["git", "-C", str(depot), "-c", f"core.hooksPath={os.devnull}", *args],
                       capture_output=True, text=True, env=env, timeout=120)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : rc={p.returncode} {p.stderr[-400:]}")
    return p


class _Racine(unittest.TestCase):
    """Une racine jetable et un environnement d'état isolé."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        (self.root / BOARD_REL).mkdir(parents=True)
        (self.base / "tmp").mkdir()
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(self.base / "state"),
            "AGENTS_EVENTS_DIR": str(self.base / "events"),
            "TMPDIR": str(self.base / "tmp"),
        })
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)

    def refus(self, appel: Any, *attendus: str) -> str:
        """`appel()` lève `BoardError`, et son message nomme chacun des `attendus`."""
        with self.assertRaises(tasks.BoardError) as ctx:
            appel()
        message = str(ctx.exception)
        for attendu in attendus:
            self.assertIn(attendu, message)
        return message


class FormatEnregistrementTests(_Racine):
    def test_w1_aller_retour_synthetique_aux_octets_de_save(self) -> None:
        """W1 : `assemble_store(explode_store(d)) == d` ; un fichier par enregistrement, nommé par son id STOCKÉ
        (`T-012.json` reste `T-012.json`) ; chaque fichier aux octets canoniques (ceux de `save` et des intents O2,
        `_octets_enveloppe` de T-1058) ; le magasin assemblé, publié par `save()`, aux octets EXACTS de l'original.
        Tue M-tri-chaîne (`T-1000` avant `T-999`) et M-octets (indent, sort_keys ou LF de `record_bytes`)."""
        d = magasin()
        fichiers = tasks.explode_store(d, TACHES)
        self.assertEqual(sorted(fichiers), sorted([
            "tasks/T-012.json", "tasks/T-00000013.json", "tasks/T-999.json", "tasks/T-1000.json",
            f"tasks/{ULID_A}.json", "tasks/T-00000177.json", "epics/E-01.json", "epics/E-02.json",
        ]))
        for nom, octets in fichiers.items():
            self.assertEqual(octets, canon(json.loads(octets)), f"{nom} : octets non canoniques")
            self.assertEqual(octets, tasks._octets_enveloppe(json.loads(octets)), f"{nom} : pas le sérialiseur O2")
        self.assertEqual(json.loads(fichiers["tasks/T-00000177.json"]), {
            "format": 1, "id": "T-00000177", "record": None,
            "sync_operations": ["op-177-creation", "op-177-suppression"],
        })
        self.assertEqual(json.loads(fichiers["tasks/T-999.json"])["sync_operations"], [])
        self.assertEqual(json.loads(fichiers["tasks/T-012.json"])["sync_operations"], ["op-012"])
        self.assertEqual(set(json.loads(fichiers["epics/E-01.json"])), {"format", "id", "record"})
        assemble = tasks.assemble_store(dict(reversed(list(fichiers.items()))), TACHES)
        self.assertEqual([t["id"] for t in assemble["tasks"]], ["T-012", "T-00000013", "T-999", "T-1000", ULID_A])
        self.assertEqual(assemble, d)
        tasks.save(str(self.root), magasin())
        autre = self.base / "repo2"
        (autre / BOARD_REL).mkdir(parents=True)
        tasks.save(str(autre), assemble)
        self.assertEqual((autre / TASKS_REL).read_bytes(), (self.root / TASKS_REL).read_bytes())

    def test_w1b_operations_triees_quel_que_soit_l_ordre_des_cles(self) -> None:
        """W1b (T-00001009, K2 : réserve de T-1008) : `sync_operations` sort TRIÉE de l'éclatement, quel que soit
        l'ordre d'insertion des clés de `sync_correlations` — pour une tâche VIVANTE (`op-012-b` inséré AVANT
        `op-012`) comme pour une TOMBE (`op-177-suppression` inséré AVANT `op-177-creation`) ; les octets sont ceux
        d'un magasin aux clés insérées dans l'ordre. VERT à la BASE (le code trie déjà). Tue N6 (tri retiré au site
        vivant) et N6b (tri retiré aux deux sites)."""
        d = magasin()
        desordre = {"op-177-suppression": {"board_task_id": "T-00000177", "tombstoned": True},
                    "op-012-b": vivante("T-012")}
        desordre.update(d["sync_correlations"])
        d["sync_correlations"] = desordre
        fichiers = tasks.explode_store(d, TACHES)
        self.assertEqual(json.loads(fichiers["tasks/T-012.json"])["sync_operations"], ["op-012", "op-012-b"])
        self.assertEqual(json.loads(fichiers["tasks/T-00000177.json"])["sync_operations"],
                         ["op-177-creation", "op-177-suppression"])
        ordre = magasin()
        ordre["sync_correlations"] = dict(sorted(desordre.items()))
        self.assertEqual(fichiers, tasks.explode_store(ordre, TACHES))

    def test_w2_projection_reconstruite_depuis_les_seuls_octets(self) -> None:
        """W2 : la projection se RECONSTRUIT depuis les seuls octets des fichiers (critère BK-415 « aucune donnée
        seulement dans la projection ») : `correlation_projection` et `assemble_store` rendent `sync_correlations`
        exactement, tombées comprises, après un éclatement intercalé d'un autre magasin ; une opération écrite À LA
        MAIN dans un fichier suit dans la projection ; la forme passe `_validate_sync_extensions` (SYM-11113) ; une
        opération portée par DEUX enregistrements est refusée, les deux nommés. Tue M-sans-tombe (tombe non écrite :
        2 corrélations perdues ici, 8 sur le board réel) et M-proj-entrée (projection recopiée de l'entrée)."""
        attendu = copy.deepcopy(magasin()["sync_correlations"])
        octets = dict(tasks.explode_store(magasin(), TACHES))
        autre = magasin()
        autre["sync_correlations"] = {}
        autre["tasks"] = [tache("T-012", "autre")]
        tasks.explode_store(autre, TACHES)
        enveloppes = [json.loads(b) for nom, b in octets.items() if nom.startswith("tasks/")]
        projection = tasks.correlation_projection(enveloppes)
        self.assertEqual(projection, attendu)
        self.assertEqual(tasks.assemble_store(octets, TACHES)["sync_correlations"], attendu)
        tasks._validate_sync_extensions(Path("projection"), {"sync_outbox": [], "sync_correlations": projection})
        env = json.loads(octets["tasks/T-999.json"])
        env["sync_operations"] = ["op-main"]
        octets["tasks/T-999.json"] = canon(env)
        self.assertEqual(tasks.assemble_store(octets, TACHES)["sync_correlations"]["op-main"], vivante("T-999"))
        env = json.loads(octets["tasks/T-1000.json"])
        env["sync_operations"] = ["op-012", "op-1000"]
        octets["tasks/T-1000.json"] = canon(env)
        self.refus(lambda: tasks.assemble_store(octets, TACHES), "op-012", "T-012", "T-1000")

    def test_w3_refus_f5_pendante_cle_inconnue_et_outbox_jamais_eclatee(self) -> None:
        """W3 : refus NOMMÉS, jamais une perte — (a) une tâche VIVANTE qui porte une corrélation tombée (F5) ;
        (b) une corrélation non tombée dont la tâche est absente (pendante), seule ou à côté d'une tombée ; (c) une
        clé de tête inconnue (`next_id`, `zzz`), et `sync_correlations` sur un magasin d'entrées ; (d) une
        corrélation hors forme, ou dont le `board_task_id` ne peut pas nommer un fichier, et un magasin, une
        collection, un enregistrement sans id ou une enveloppe de projection hors forme ; (e) `sync_outbox` non
        vide n'est JAMAIS éclaté : mêmes fichiers et mêmes octets que sans elle, entrée intacte, clé absente de
        l'assemblage (ses intents vivent dans leurs fichiers O2, T-1058). Tue M-F5-muet, M-pendante-ignorée,
        M-clé-perdue et M-outbox-éclaté."""
        d = magasin()
        d["sync_correlations"]["op-012"]["tombstoned"] = True
        self.refus(lambda: tasks.explode_store(d, TACHES), "T-012", "op-012")
        d = magasin()
        d["sync_correlations"]["op-pendante"] = vivante("T-00000250")
        self.refus(lambda: tasks.explode_store(d, TACHES), "T-00000250", "op-pendante")
        d = magasin()
        d["sync_correlations"]["op-177-creation"]["tombstoned"] = False
        self.refus(lambda: tasks.explode_store(d, TACHES), "T-00000177", "op-177-creation")
        for cle in ("next_id", "zzz"):
            d = magasin()
            d[cle] = 7
            self.refus(lambda: tasks.explode_store(d, TACHES), cle)
        self.refus(lambda: tasks.explode_store({"entries": [], "sync_correlations": {}}, ENTREES),
                   "sync_correlations")
        for correlation in ({"board_task_id": "T-012"}, {"board_task_id": "T-012", "tombstoned": "non"},
                            {"board_task_id": "", "tombstoned": True}, {"board_task_id": "../T-1", "tombstoned": True},
                            {"board_task_id": "T-1/x", "tombstoned": True}):
            d = magasin()
            d["sync_correlations"]["op-x"] = correlation
            self.refus(lambda: tasks.explode_store(d, TACHES), "op-x")
        self.refus(lambda: tasks.explode_store([], TACHES), "not an object")
        self.refus(lambda: tasks.explode_store({"tasks": [], "sync_correlations": []}, TACHES), "sync_correlations")
        self.refus(lambda: tasks.explode_store({"tasks": {}, "sync_correlations": {}}, TACHES), "tasks")
        for record in ({"titre": "sans id"}, {"id": "../T-1"}, "T-1"):
            self.refus(lambda: tasks.explode_store({"tasks": [record], "sync_correlations": {}}, TACHES), "tasks")
        self.refus(lambda: tasks.correlation_projection([{"format": 1, "id": "T-1", "record": None}]), "T-1")
        sans = tasks.explode_store(magasin(), TACHES)
        d = magasin()
        d["sync_outbox"] = [{"operation_id": "op-012", "event_kind": "BOARD_TASK_OBSERVED"}]
        avant = copy.deepcopy(d)
        avec = tasks.explode_store(d, TACHES)
        self.assertEqual(avec, sans)
        self.assertEqual(d, avant)
        self.assertNotIn("sync_outbox", tasks.assemble_store(avec, TACHES))

    def test_w4_identite_nom_id_et_ids_hostiles(self) -> None:
        """W4 : l'IDENTITÉ d'un enregistrement est `identity_key`, jamais la chaîne — `T-012.json` et
        `T-00000012.json` ensemble sont refusés, les deux nommés (à l'assemblage comme à l'éclatement) ; un nom qui
        n'est pas l'`id` de son enveloppe, un `record.id` qui n'est pas l'`id`, un chemin hors forme ou une
        collection inconnue : refusés. `record_file` n'accepte qu'un id `P-<ULID>` ou `[TSLE]-<1 à 15 chiffres>`
        (l'alias stocké, jamais réécrit) ; traversée, séparateur, casse, vide, fin de ligne et 16 chiffres
        (`numeric_id` borne à 15) lèvent. Tue M-identité-chaîne, M-nom-libre et le mutant `\\d+` (16 chiffres)."""
        dossier = self.base / "home"
        for rid in ("T-012", "T-00000012", ULID_A, "E-01", "S-00004500", "L-00000435", "T-" + "9" * 15):
            self.assertEqual(tasks.record_file(dossier, rid), dossier / f"{rid}.json")
        for rid in ("../T-1", "T-1/x", "T-1\\x", "t-1", "", "T-1\n", "T-" + "1" * 16, "X-1", "T-1.json", " T-1",
                    "T-01aaaaaaaaaaaaaaaaaaaaaaaa", "T-", None):
            self.refus(lambda: tasks.record_file(dossier, rid))
        un = canon({"format": 1, "id": "T-012", "record": tache("T-012", "a"), "sync_operations": []})
        deux = canon({"format": 1, "id": "T-00000012", "record": tache("T-00000012", "b"), "sync_operations": []})
        self.refus(lambda: tasks.assemble_store({"tasks/T-012.json": un, "tasks/T-00000012.json": deux}, TACHES),
                   "tasks/T-012.json", "tasks/T-00000012.json")
        d = {"tasks": [tache("T-012", "a"), tache("T-00000012", "b")], "sync_correlations": {}}
        self.refus(lambda: tasks.explode_store(d, TACHES), "T-012", "T-00000012")
        six = canon({"format": 1, "id": "T-6", "record": tache("T-6", "x"), "sync_operations": []})
        self.refus(lambda: tasks.assemble_store({"tasks/T-5.json": six}, TACHES), "tasks/T-5.json")
        faux = canon({"format": 1, "id": "T-5", "record": tache("T-6", "x"), "sync_operations": []})
        self.refus(lambda: tasks.assemble_store({"tasks/T-5.json": faux}, TACHES), "tasks/T-5.json")
        cinq = canon({"format": 1, "id": "T-5", "record": tache("T-5", "x"), "sync_operations": []})
        for nom in ("tasks/../T-5.json", "tasks/sous/T-5.json", "autre/T-5.json", "T-5.json", "tasks/T-5.JSON",
                    "tasks/T-5"):
            self.refus(lambda: tasks.assemble_store({nom: cinq}, TACHES), nom)

    def test_w4b_une_tombe_dont_l_id_n_est_pas_son_nom_est_refusee(self) -> None:
        """W4b (T-00001009, K2) : une TOMBE (`record: null`, donc aucun `record.id` à comparer) dont l'`id` n'est
        pas celui de son nom — `tasks/T-5.json` qui porte `T-6` — est refusée, le fichier nommé, à l'assemblage
        comme à la lecture d'un dossier. VERT à la BASE. Tue N2 (contrôle `enveloppe.id == nom` retiré)."""
        faux = canon({"format": 1, "id": "T-6", "record": None, "sync_operations": ["op-6"]})
        self.refus(lambda: tasks.assemble_store({"tasks/T-5.json": faux}, TACHES), "tasks/T-5.json", "T-6")
        home = self.base / "home"
        (home / "tasks").mkdir(parents=True)
        (home / "tasks" / "T-5.json").write_bytes(faux)
        self.refus(lambda: tasks.read_records(home, TACHES), "tasks/T-5.json")

    def test_w4c_identite_controlee_dans_chaque_collection(self) -> None:
        """W4c (T-00001009, K2) : deux epics d'UNE identité (`E-01` et `E-00000001`) sont refusées à l'éclatement,
        les deux nommées — la règle `identity_key` vaut pour CHAQUE collection, pas seulement `tasks`. VERT à la
        BASE. Tue N32 (contrôle d'identité réservé à la collection corrélée)."""
        d = magasin()
        d["epics"] = [{"id": "E-01", "titre": "un"}, {"id": "E-00000001", "titre": "un bis"}]
        self.refus(lambda: tasks.explode_store(d, TACHES), "E-01", "E-00000001")

    def test_w4d_tombstoned_strictement_booleen(self) -> None:
        """W4d (T-00001009, K2) : `tombstoned` vaut `true` ou `false`, rien d'autre — `0` et `null` sur une tâche
        VIVANTE (falsy : ils passaient pour vivants), `1` sur une tâche ABSENTE (truthy : il passait pour une tombe)
        sont refusés, l'opération nommée. VERT à la BASE. Tue N35 (contrôle `isinstance(…, bool)` retiré)."""
        for tid, valeur in (("T-012", 0), ("T-012", None), ("T-00000404", 1)):
            d = magasin()
            d["sync_correlations"]["op-faux"] = {"board_task_id": tid, "tombstoned": valeur}
            with self.subTest(tid=tid, tombstoned=valeur):
                self.refus(lambda: tasks.explode_store(d, TACHES), "op-faux")

    def test_w4e_un_nom_qui_n_est_pas_un_id_est_refuse_meme_coherent(self) -> None:
        """W4e (T-00001009, K2) : à l'assemblage, le NOM est jugé comme id (`_refus_id_enregistrement`) même quand
        l'enveloppe le répète à l'identique — `tasks/t-5.json` portant `t-5`, `tasks/T-<16 chiffres>.json`, une
        epic `epics/E-1x.json` : refusés, le fichier nommé. VERT à la BASE. Tue N38 (contrôle du nom retiré
        d'`assemble_store`)."""
        for collection, rid in (("tasks", "t-5"), ("tasks", "T-" + "1" * 16), ("epics", "E-1x")):
            env: dict[str, Any] = {"format": 1, "id": rid, "record": None}
            if collection == "tasks":
                env["sync_operations"] = []
            nom = f"{collection}/{rid}.json"
            with self.subTest(nom=nom):
                self.refus(lambda: tasks.assemble_store({nom: canon(env)}, TACHES), nom)

    def test_w5_version_cles_illisible_tombe_vide_et_octets_toleres(self) -> None:
        """W5 : `format` > 1 refusé (plus récent que ce code), `format` ABSENT refusé (un lecteur qui défaut à 1
        avalerait un fichier étranger, réserve C4), `format` non entier (`true`, `"1"`, 0, 1.0, null) refusé ; clé
        d'enveloppe inconnue, `sync_operations` absent d'une tâche ou hors forme : refusés ; JSON invalide, octets
        non UTF-8 ou racine non objet : refusés EN NOMMANT le fichier ; une tombe à `sync_operations: []` ACCEPTÉE
        (format prêt pour une suppression sans corrélation — angle mort 4, T-1009 —, réserve C4) ; des octets
        valides mais NON canoniques acceptés (« valide à l'écriture, tolère à la lecture ») puis ré-émis canoniques.
        Tue M-version, le défaut à 1, M-illisible-sauté et M-strict-octets."""
        nom = "tasks/T-5.json"
        ok = {"format": 1, "id": "T-5", "record": tache("T-5", "cinq — été"), "sync_operations": ["op-5"]}

        def avec(**champs: Any) -> dict[str, bytes]:
            env = dict(ok)
            env.update(champs)
            return {nom: canon(env)}

        self.refus(lambda: tasks.assemble_store(avec(format=2), TACHES), nom, "2")
        sans_format = {k: v for k, v in ok.items() if k != "format"}
        self.refus(lambda: tasks.assemble_store({nom: canon(sans_format)}, TACHES), nom, "no `format`")
        for valeur in (True, "1", 0, 1.0, None):
            self.refus(lambda: tasks.assemble_store(avec(format=valeur), TACHES), nom)
        self.refus(lambda: tasks.assemble_store(avec(extra=1), TACHES), nom)
        sans_ops = {k: v for k, v in ok.items() if k != "sync_operations"}
        self.refus(lambda: tasks.assemble_store({nom: canon(sans_ops)}, TACHES), nom)
        for ops in ("op-5", [""], ["op-5", "op-5"], [5], None):
            self.refus(lambda: tasks.assemble_store(avec(sync_operations=ops), TACHES), nom)
        for brut in (b"{", b"\xff\xfe", b"[]", b"null"):
            self.refus(lambda: tasks.assemble_store({nom: brut}, TACHES), nom)
        tombe_vide = canon({"format": 1, "id": "T-6", "record": None, "sync_operations": []})
        self.assertEqual(tasks.assemble_store({"tasks/T-6.json": tombe_vide}, TACHES),
                         {"tasks": [], "sync_correlations": {}})
        brut = json.dumps(ok, indent=4).replace("\n", "\r\n").encode("utf-8")
        try:
            assemble = tasks.assemble_store({nom: brut}, TACHES)
        except tasks.BoardError as exc:
            self.fail(f"octets valides mais non canoniques refusés : {exc}")
        self.assertEqual(assemble["tasks"], [ok["record"]])
        self.assertEqual(tasks.explode_store(assemble, TACHES), {nom: canon(ok)})

    def test_w6_entrees_generiques_au_rang_sort_key(self) -> None:
        """W6 : le même format pour LEDGER et SPECS (`entries`, sans `sync_operations`) ; l'assemblage range chaque
        entrée à son rang `sort_key` (aucun ordinal stocké, angle mort 2) — `L-9`, `L-10`, `L-00000011` puis
        l'ULID, que l'ordre des CHAÎNES inverse —, quel que soit l'ordre des fichiers ; une entrée hors ordre à
        l'entrée revient à son rang, multiensemble égal (l'écart SPECS de M3, à T-1011). Tue M-ordre-entrée."""
        entrees = [{"id": "L-9", "lecon": "neuf"}, {"id": "L-10", "lecon": "dix"},
                   {"id": "L-00000011", "lecon": "onze"}, {"id": "L-01AAAAAAAAAAAAAAAAAAAAAAAA", "lecon": "ulid"}]
        d = {"entries": copy.deepcopy(entrees)}
        fichiers = tasks.explode_store(d, ENTREES)
        self.assertEqual(sorted(fichiers), sorted(f"entries/{e['id']}.json" for e in entrees))
        for octets in fichiers.values():
            self.assertEqual(set(json.loads(octets)), {"format", "id", "record"})
        self.assertEqual(tasks.assemble_store(dict(reversed(list(fichiers.items()))), ENTREES), d)
        melange = {"entries": [entrees[3], entrees[1], entrees[0], entrees[2]]}
        rendu = tasks.assemble_store(tasks.explode_store(melange, ENTREES), ENTREES)
        self.assertEqual(rendu, d)
        self.assertNotEqual(rendu, melange)
        avec_ops = canon({"format": 1, "id": "L-9", "record": entrees[0], "sync_operations": []})
        self.refus(lambda: tasks.assemble_store({"entries/L-9.json": avec_ops}, ENTREES), "entries/L-9.json")
        self.assertEqual(tasks.assemble_store({}, ENTREES), {"entries": []})
        spec = {"entries": [{"id": "S-00004500", "kind": "decision"},
                            {"id": "S-01M4JN56JEQ0XS97K38CDWBTW6", "kind": "decision"}]}
        self.assertEqual(tasks.assemble_store(tasks.explode_store(spec, ENTREES), ENTREES), spec)

    def test_w7_lire_un_dossier_d_enregistrements(self) -> None:
        """W7 : `read_records` lit `<dossier>/<collection>/<id>.json` puis assemble — un nom pointé (le temporaire
        d'une écriture atomique) est IGNORÉ ; tout autre nom hors forme (`T-12.JSON`, `x.txt`, un sous-dossier) est
        REFUSÉ et nommé, jamais sauté ; un lien symbolique et un fichier au-delà du plafond sont refusés ; dossier
        absent ⇒ magasin vide ; ce qui n'est pas un dossier de collection n'est pas lu ; rien n'est écrit (`save`
        jamais appelé, dossier inchangé). Tue M-saut-muet."""
        d = magasin()
        home = self.base / "home"
        poser(home, tasks.explode_store(d, TACHES), TACHES)
        (home / "tasks" / ".T-012.json.tmp").write_bytes(b"{")
        (home / "LISEZMOI").write_text("pas un enregistrement", encoding="utf-8")
        avant = cliche(home, TACHES)
        with mock.patch.object(tasks, "save", side_effect=AssertionError("read_records a écrit")):
            try:
                lu = tasks.read_records(home, TACHES)
            except tasks.BoardError as exc:
                self.fail(f"un nom pointé (temporaire d'écriture) n'a pas été ignoré : {exc}")
        self.assertEqual(lu, d)
        self.assertEqual(cliche(home, TACHES), avant)
        for nom, contenu in (("T-12.JSON", b"{}"), ("x.txt", b"x")):
            chemin = home / "tasks" / nom
            chemin.write_bytes(contenu)
            self.refus(lambda: tasks.read_records(home, TACHES), nom)
            chemin.unlink()
        (home / "tasks" / "sous").mkdir()
        self.refus(lambda: tasks.read_records(home, TACHES), "sous")
        (home / "tasks" / "sous").rmdir()
        with mock.patch.object(tasks, "_PLAFOND_ENREGISTREMENT_OCTETS", 16):
            self.refus(lambda: tasks.read_records(home, TACHES), "tasks/")
        if os.name != "nt":
            cible = home / "tasks" / "T-999.json"
            (self.base / "ailleurs.json").write_bytes(cible.read_bytes())
            cible.unlink()
            cible.symlink_to(self.base / "ailleurs.json")
            self.refus(lambda: tasks.read_records(home, TACHES), "T-999.json")
        self.assertEqual(tasks.read_records(self.base / "absent", TACHES), {"tasks": [], "sync_correlations": {}})
        self.assertEqual(tasks.read_records(self.base / "absent", ENTREES), {"entries": []})

    def test_w8_fusion_git_enregistrements_differents_et_bornes(self) -> None:
        """W8 : fusion git RÉELLE (dépôt jetable) — (a) deux branches qui modifient deux tâches DIFFÉRENTES et
        créent chacune une tâche (deux ULID, chacune avec sa corrélation) fusionnent rc 0, et l'assemblage est
        l'UNION ; (b) une tombe contre une modification de la même tâche ⇒ CONFLIT sur ce seul fichier, jamais une
        perte muette ; (c) BORNE ÉCRITE, S-01M4JN56NB05914VWW942W214X : deux champs VOISINS d'un même
        enregistrement (`state` / `stage`) conflictent encore — « compatible » s'entend à la ligne, la fusion par
        champ est une autre tâche. Tue M-un-fichier (le magasin entier dans un seul fichier : les deux créations
        s'insèrent au même endroit, conflit sur (a))."""
        depot = self.base / "fusion"
        depot.mkdir()
        git(depot, "-c", "init.defaultBranch=main", "init", "-q")
        for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"),
                            ("commit.gpgsign", "false")):
            git(depot, "config", cle, valeur)
        base = {"tasks": [tache("T-1", "un"), tache("T-2", "deux"), tache("T-3", "trois")],
                "sync_correlations": {f"op-{n}": vivante(f"T-{n}") for n in (1, 2, 3)}}
        poser(depot, tasks.explode_store(base, TACHES), TACHES)
        git(depot, "add", "-A")
        git(depot, "commit", "-q", "-m", "base")

        def fusion(a: str, cote_a: dict[str, Any], b: str, cote_b: dict[str, Any]) -> tuple[int, list[str]]:
            for nom, data in ((a, cote_a), (b, cote_b)):
                git(depot, "checkout", "-q", "-B", nom, "main")
                poser(depot, tasks.explode_store(data, TACHES), TACHES)
                git(depot, "add", "-A")
                git(depot, "commit", "-q", "--allow-empty", "-m", nom)
            git(depot, "checkout", "-q", a)
            rc = git(depot, "merge", "-q", "--no-edit", b, check=False).returncode
            return rc, git(depot, "diff", "--name-only", "--diff-filter=U").stdout.split()

        cote_a, cote_b = copy.deepcopy(base), copy.deepcopy(base)
        cote_a["tasks"][0]["state"] = "done"
        cote_a["tasks"].append(tache(ULID_A, "créée en A"))
        cote_a["sync_correlations"]["op-a"] = vivante(ULID_A)
        cote_b["tasks"][1]["state"] = "blocked"
        cote_b["tasks"].append(tache(ULID_B, "créée en B"))
        cote_b["sync_correlations"]["op-b"] = vivante(ULID_B)
        self.assertEqual(fusion("a1", cote_a, "b1", cote_b), (0, []), "(a) deux enregistrements différents")
        union = copy.deepcopy(cote_a)
        union["tasks"][1]["state"] = "blocked"
        union["tasks"].append(tache(ULID_B, "créée en B"))
        union["sync_correlations"]["op-b"] = vivante(ULID_B)
        self.assertEqual(tasks.read_records(depot, TACHES), union)

        supprime, modifie = copy.deepcopy(base), copy.deepcopy(base)
        del supprime["tasks"][2]
        supprime["sync_correlations"]["op-3"]["tombstoned"] = True
        modifie["tasks"][2]["state"] = "done"
        rc, conflits = fusion("a2", supprime, "b2", modifie)
        self.assertNotEqual(rc, 0, "(b) une tombe contre une modification a fusionné en silence")
        self.assertEqual(conflits, ["tasks/T-3.json"])
        git(depot, "merge", "--abort")

        etat, etape = copy.deepcopy(base), copy.deepcopy(base)
        etat["tasks"][0]["state"] = "blocked"
        etape["tasks"][0]["stage"] = "étape b"
        rc, conflits = fusion("a3", etat, "b3", etape)
        self.assertNotEqual(rc, 0, "(c) la borne écrite S-01M4JN56NB05914VWW942W214X a bougé : relire la décision")
        self.assertEqual(conflits, ["tasks/T-1.json"])
        git(depot, "merge", "--abort")

    def test_w9_record_bytes_stable_utf8_aux_octets_de_save(self) -> None:
        """W9 : `record_bytes` est un point fixe (`record_bytes(json.loads(record_bytes(x))) == record_bytes(x)`)
        sur trois formes d'id, aux octets de `save` et des intents O2 — UTF-8 BRUT (`été`, jamais `\\u00e9`), LF,
        clés triées, indent 2 — et refuse d'écrire une enveloppe hors forme (« valide à l'écriture »). Tue
        M-ensure-ascii."""
        for rid in ("T-012", "T-00000013", ULID_A):
            env = {"format": 1, "id": rid, "record": tache(rid, "titre — été"), "sync_operations": ["op-a", "op-b"]}
            octets = tasks.record_bytes(env)
            self.assertEqual(octets, canon(env))
            self.assertIn("été".encode("utf-8"), octets)
            self.assertNotIn(b"\r\n", octets)
            self.assertEqual(tasks.record_bytes(json.loads(octets)), octets)
        self.refus(lambda: tasks.record_bytes({"format": 1, "id": "T-1", "record": tache("T-2", "x"),
                                               "sync_operations": []}), "T-1")
        self.refus(lambda: tasks.record_bytes({"format": 2, "id": "T-1", "record": None, "sync_operations": []}))
        self.assertEqual(tasks.RECORD_FORMAT, 1)

    def test_w9b_chiffres_non_ascii_nan_et_surrogat_refuses(self) -> None:
        """W9b (passe de clôture E-26) : un id ne se lit qu'en chiffres ASCII — `numeric_id` et `record_file`
        refusent `T-١٢` (arabe-indien), `L-１２` (pleine chasse), `E-٣` et `T-١12` (queue ASCII derrière un chiffre
        non ASCII), qu'un `\\d` Unicode lisait 12 ou nommait `T-١٢.json` ; `record_bytes` refuse en `BoardError` un
        NaN / Infinity (des octets qu'aucun lecteur JSON strict ne relit) et un surrogat isolé (`UnicodeEncodeError`
        brut avant). ROUGE PAR ASSERTION avant le correctif : toute autre issue devient un échec nommé."""
        dossier = self.base / "home"

        def leve(appel: Any, quoi: str) -> None:
            try:
                rendu = appel()
            except tasks.BoardError:
                return
            except Exception as exc:  # converti en échec d'assertion, jamais avalé
                self.fail(f"{quoi} : {type(exc).__name__} au lieu de BoardError : {exc}")
            self.fail(f"{quoi} : accepté, rendu {rendu!r}")

        for rid in ("T-١٢", "L-１２", "E-٣", "T-١12"):
            with self.subTest(id=rid):
                leve(lambda: tasks.numeric_id(rid), f"numeric_id({rid!r})")
                leve(lambda: tasks.record_file(dossier, rid), f"record_file({rid!r})")
        self.assertEqual(12, tasks.numeric_id("T-012"), "contrôle : un id ASCII reste lu")
        for nom, champ in (("NaN", {"poids": float("nan")}), ("Infinity", {"poids": float("inf")}),
                           ("surrogat", {"task": "\ud800"})):
            env = {"format": 1, "id": "T-5", "record": dict(tache("T-5", "x"), **champ), "sync_operations": []}
            with self.subTest(octets=nom):
                leve(lambda: tasks.record_bytes(env), f"record_bytes({nom})")
        self.assertEqual(canon({"format": 1, "id": "T-5", "record": tache("T-5", "x"), "sync_operations": []}),
                         tasks.record_bytes({"format": 1, "id": "T-5", "record": tache("T-5", "x"),
                                             "sync_operations": []}), "contrôle : une enveloppe saine passe")

    def test_w9c_la_collection_est_passee_jamais_deduite(self) -> None:
        """W9c (T-00001009, M9) : `record_bytes_pour(enveloppe, collection)` juge l'enveloppe contre la collection
        PASSÉE — `sync_operations` hors `tasks` refusé, une enveloppe de `tasks` SANS `sync_operations` (la tombe que
        relirait `read_records` en la refusant) refusée — puis rend les octets canoniques ; `record_bytes(enveloppe)`
        garde son raccourci documenté (il DÉDUIT : sans `sync_operations`, une enveloppe à trois clés passe, et la
        parité W11 avec ledger.py tient). ROUGE à la BASE (`record_bytes_pour` absent). Tue M-déduction."""
        avec_ops = {"format": 1, "id": "T-5", "record": None, "sync_operations": ["op-5"]}
        sans_ops = {"format": 1, "id": "T-5", "record": None}
        self.refus(lambda: tasks.record_bytes_pour(avec_ops, "entries"), "T-5", "sync_operations")
        self.refus(lambda: tasks.record_bytes_pour(avec_ops, "epics"), "T-5")
        self.refus(lambda: tasks.record_bytes_pour(sans_ops, "tasks"), "T-5", "sync_operations")
        self.assertEqual(tasks.record_bytes_pour(avec_ops, "tasks"), canon(avec_ops))
        self.assertEqual(tasks.record_bytes_pour(sans_ops, "entries"), canon(sans_ops))
        self.assertEqual(tasks.record_bytes(sans_ops), canon(sans_ops), "raccourci : la déduction reste admise")
        self.refus(lambda: tasks.record_bytes_pour({"format": 1, "id": "T-5", "record": {"id": "T-5", "x": float("nan")},
                                                    "sync_operations": []}, "tasks"), "T-5")

    def test_w10_board_reel_du_kit_aller_retour(self) -> None:
        """W10 (réserve C4, dépôt-kit seul) : W1 et W2 rejoués sur les magasins RÉELS, en lecture seule — TASKS :
        assemblage == texte (`sync_outbox` mise à part), octets == TASKS.json quand le texte ne la porte plus,
        projection == `sync_correlations` (0 écart), une tombe par tâche absente dont les clés sont tombées (au
        moins une : les clés de suppression sont permanentes, README.md:113), un fichier par enregistrement ;
        LEDGER et SPECS : même multiensemble, rangé par `sort_key` (l'écart d'ordre SPECS de M3 est à T-1011). Tue
        M-sans-tombe sur le board réel. INDÉPENDANT DE LA FORME (T-00001009) : sans monolithe, le board se lit en
        dossier (`lire_board_brut`) et l'éclatement doit redonner les octets de chaque fichier — une tombe sans clé
        (`sync_operations: []`) n'est écrite que par `save()`, jamais par l'éclatement."""
        if not (REPO / MARQUEUR_KIT).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un board d'adoptant n'est pas tenu ici")
        self.aller_retour_board(REPO)
        for chemin in MAGASINS_ENTREES:  # par le MODULE, dans la forme présente (T-01M4KKMY43ZKCW1YD2Y8JX9MKH)
            spec = importlib.util.spec_from_file_location(f"w10_{chemin[:-3]}_banc", HERE / chemin)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            entrees = {"entries": module.load(REPO)["entries"]}
            self.assertGreater(len(entrees["entries"]), 0, f"{chemin} : magasin réel du kit vide ou absent")
            rendu = tasks.assemble_store(tasks.explode_store(entrees, ENTREES), ENTREES)
            self.assertEqual(sorted(map(canon, rendu["entries"])), sorted(map(canon, entrees["entries"])), chemin)
            ids = [e["id"] for e in rendu["entries"]]
            self.assertEqual(ids, sorted(ids, key=tasks.sort_key), chemin)

    def test_w10b_le_meme_aller_retour_sur_un_board_migre(self) -> None:
        """W10b (exec-critic de T-00001009, BLOQUANT : la branche dossier de W10 n'était jouée par aucun banc) : le volet
        TASKS de W10 sur une racine JETABLE migrée par `migrate_store`, sur le modèle de
        `test_W7b_repli_sur_un_head_migre` — sans TASKS.json, `aller_retour_board` lit par `lire_board_brut`, exige les
        octets de chaque fichier == l'éclatement, et tolère hors de l'éclatement la seule tombe SANS clé (`[]`, écrite
        par `save()` : ici une suppression sous `suppress_sync`). ROUGE à la BASE ; MUTANTS « branche dossier qui
        lève » et « sans repli » (le W10 d'avant, TASKS.json seul) ⇒ rouges."""
        r = str(self.root)
        tasks.save(r, magasin())
        self.assertIn("migrated", tasks.migrate_store(r))
        with tasks.suppress_sync("op-w10b"):
            tasks.delete_task(r, "T-999")
        self.assertFalse((self.root / TASKS_REL).exists())
        self.assertEqual(json.loads((self.root / BOARD_REL / "tasks" / "T-999.json").read_bytes())["sync_operations"],
                         [], "la tombe sans clé doit exister pour que la tolérance soit jouée")
        self.aller_retour_board(self.root)

    def aller_retour_board(self, racine: Path) -> None:
        """Le volet TASKS de W10 sur le board de `racine`, dans la forme qu'il a (monolithe, sinon dossier)."""
        board = racine / BOARD_REL
        if (racine / TASKS_REL).is_file():
            brut = (racine / TASKS_REL).read_bytes()
            data = json.loads(brut.decode("utf-8"))
            texte = {k: v for k, v in data.items() if k != "sync_outbox"}
            fichiers = tasks.explode_store(data, TACHES)
            assemble = tasks.assemble_store(fichiers, TACHES)
            self.assertEqual(assemble, texte)
            if "sync_outbox" not in data:
                self.assertEqual(canon(assemble), brut)
        else:
            data = tasks.lire_board_brut(racine)
            fichiers = tasks.explode_store(data, TACHES)
            assemble = tasks.assemble_store(fichiers, TACHES)
            disque = {f"{c}/{p.name}": p.read_bytes() for c in TACHES if (board / c).is_dir()
                      for p in (board / c).iterdir() if not p.name.startswith(".")}
            self.assertEqual({nom: disque.get(nom) for nom in fichiers}, fichiers)
            for nom in sorted(set(disque) - set(fichiers)):
                self.assertEqual(json.loads(disque[nom])["record"], None, f"{nom} : vivant hors de l'éclatement")
                self.assertEqual(json.loads(disque[nom]).get("sync_operations"), [], nom)
        self.assertEqual(assemble["sync_correlations"], data["sync_correlations"])
        vivantes = {t["id"] for t in data["tasks"]}
        absentes = {c["board_task_id"] for c in data["sync_correlations"].values()} - vivantes
        tombes = {nom for nom, octets in fichiers.items() if json.loads(octets)["record"] is None}
        self.assertEqual(tombes, {f"tasks/{tid}.json" for tid in absentes})
        self.assertGreater(len(tombes), 0)
        self.assertEqual(len(fichiers), len(data["tasks"]) + len(data.get("epics", [])) + len(absentes))


class AucunCheminDEcritureParUnDictNuTests(_Racine):
    def _nouvelle(self, titre: str) -> str:
        return tasks.new_task(str(self.root), titre, "banc").split()[1]

    def _definitifs(self) -> list[str]:
        dossier = self.root / OUTBOX_REL
        return sorted(p.name for p in dossier.glob("*.json")) if dossier.is_dir() else []

    def test_w11_eclater_garde_la_vue_o2_les_acquittees_et_les_tombes(self) -> None:
        """W11 (delta S-01M4M2E77V0ZPRSDHSNR65SS8K, clôture de T-1058) : la forme des fichiers O2 et le retrait
        « vue lue − liste écrite » reposent sur `_BoardCharge.vue_o2`, qu'un dict nu PERD. (a) Éclater et
        assembler le `_BoardCharge` d'un vrai `load()` n'écrit RIEN (`save` jamais appelé, TASKS.json et dossier
        O2 inchangés) et le laisse INTACT — même type, même `vue_o2`, même `ressuscites`, même `sync_outbox` — ;
        un `save` du MÊME objet garde donc chaque fichier d'intent ; l'assemblage est un dict NEUF, sans vue O2,
        jamais un `_BoardCharge`. (b) Une corrélation ACQUITTÉE ne vit plus que dans TASKS.json : après le drain,
        chaque création porte encore son opération dans son fichier, projection == `sync_correlations`. (c) Une
        suppression acquittée laisse une clé tombée PERMANENTE (README.md:113) : sa tombe porte l'opération. Tue
        M-dict-nu (l'éclatement qui retire `sync_outbox` de l'objet reçu : le save suivant supprime les fichiers
        d'intent encore en attente)."""
        t1, t2 = self._nouvelle("un"), self._nouvelle("deux")
        self.assertEqual(len(self._definitifs()), 2)
        data = tasks.load(str(self.root))
        vue, outbox, ressuscites = data.vue_o2, copy.deepcopy(data["sync_outbox"]), data.ressuscites
        texte, intents = (self.root / TASKS_REL).read_bytes(), self._definitifs()
        with mock.patch.object(tasks, "save", side_effect=AssertionError("l'éclatement a écrit")):
            fichiers = tasks.explode_store(data, TACHES)
            assemble = tasks.assemble_store(fichiers, TACHES)
        self.assertIs(type(data), tasks._BoardCharge)
        self.assertIs(data.vue_o2, vue)
        self.assertEqual(data.ressuscites, ressuscites)
        self.assertEqual(data.get("sync_outbox"), outbox)
        self.assertEqual(((self.root / TASKS_REL).read_bytes(), self._definitifs()), (texte, intents))
        self.assertNotIsInstance(assemble, tasks._BoardCharge)
        self.assertIsNone(getattr(assemble, "vue_o2", None))
        self.assertNotIn("sync_outbox", assemble)
        tasks.save(str(self.root), data)
        self.assertEqual(self._definitifs(), intents)

        tasks.drain_sync_outbox(str(self.root), lambda _intent: True)
        self.assertEqual(self._definitifs(), [])
        data = tasks.load(str(self.root))
        fichiers = tasks.explode_store(data, TACHES)
        for tid in (t1, t2):
            self.assertEqual(len(json.loads(fichiers[f"tasks/{tid}.json"])["sync_operations"]), 1, tid)
        self.assertEqual(tasks.assemble_store(fichiers, TACHES)["sync_correlations"], data["sync_correlations"])

        tasks.delete_task(str(self.root), t1)
        tasks.drain_sync_outbox(str(self.root), lambda _intent: True)
        data = tasks.load(str(self.root))
        fichiers = tasks.explode_store(data, TACHES)
        tombe = json.loads(fichiers[f"tasks/{t1}.json"])
        self.assertIsNone(tombe["record"])
        self.assertTrue(tombe["sync_operations"])
        projection = tasks.assemble_store(fichiers, TACHES)["sync_correlations"]
        self.assertEqual(projection, data["sync_correlations"])
        self.assertTrue(all(projection[op]["tombstoned"] for op in tombe["sync_operations"]))


if __name__ == "__main__":
    unittest.main()
