"""test_record_id.py — T-00000726 : tranches T-00001038, T-00001039, puis la
bascule C2 (forme A, S-00003552 ; aucun compteur stocké, S-00002657).

CE QUE CE BANC TIENT.
  (a)    FUSION : deux branches nées de la MÊME base allouent chacune un
         enregistrement (tâche, entrée de journal, leçon) — deux ids DIFFÉRENTS,
         deux `P-<ULID>`, et l'union des deux magasins se charge (mutant M1 : la
         frappe rendue au compteur) ;
  (b)    la grammaire de LECTURE, sur les fonctions PURES de `tasks`
         (`is_ulid_id`, `sort_key`, `identity_key`) — elles ne vivent pas dans
         `record_id.py`, et c'est voulu : une copie de la CLI sans ce frère lit ;
  mint   `record_id.mint(P)` rend un id que la lecture pure reconnaît, refuse un
         préfixe hors {T, S, L} et une sortie hors grammaire ;
  (c)-C2 les TROIS magasins réels, sur copie jetable : `save(load(x))` rend x
         MOINS la seule clé `next_id`, À L'OCTET (forme canonique de `save`), et
         la vue est identique (dépôt-kit seul) ; le cycle est idempotent et sans
         `next_id` partout ; `epics` et le champ `epic` survivent (M37 ; M7 est
         tué ailleurs, voir `MagasinsReelsKitTests`). Ils
         REMPLACENT les (c)-C1 de T-00001038 (`test_c1_*`, qui tenaient
         `save(load(x)) == x` et sortent avec la bascule) ;
  (d)    UNE seule copie du générateur par processus, sous les deux branches de
         résolution (paquet, chemin) : `record_id` et la couture
         `run_export._cadre` rendent le MÊME objet ;
  (e)    fail-closed : générateur absent ⇒ `RecordIdError` au texte exact, rien
         d'écrit, rien d'enregistré dans `sys.modules` ;
  (e)-C2 la même chose au SITE d'allocation : `new_task`, `specs.add_entry` et
         `ledger.add_entry` lèvent `RecordIdError` sans toucher au magasin (M5) ;
         et une copie de la CLI SANS `record_id.py` refuse d'allouer en NOMMANT
         le remède (`git checkout -- .agents/bin/record_id.py`), rc 2 ;
  (g)    le REGISTRE des constantes qui RECOPIENT la grammaire d'id, en deux
         colonnes (ancrée / recherche), plus la parité de la clé d'ordre avec
         `plan_pool` et `plan_waves` (M30, M30b, R1-R4) ;
  (h)    LARGEUR : un id de 28 caractères est rendu ENTIER dans `list`, dans la
         vue `.md` et dans le board de session ; le `task` d'une entrée de
         journal et le `related` d'une leçon aussi (M31, M31') ;
  (e'')  chargement PARESSEUX, joué en SOUS-PROCESSUS (jamais dans le processus
         pytest, où un banc antérieur qui alloue poserait la clé) — mutant M27.
  P-PAR  (T-00001039) les copies PURES de `specs.py` et `ledger.py` répondent
         comme celles de `tasks` sur une table fixe — mutant M34 ;
  M33s/M33l (T-00001039) une copie de `specs.py` ou de `ledger.py` SEULE lit un
         magasin mixte, sans frère — mutants M35s/M35l.

LES CHEMINS RÉELS SONT UNE TABLE DE CHAÎNES RELATIVES, jamais un littéral
`ROOT / ...` : `.agents/state/` et `.agents/IS_THE_KIT` sont `strip:` dans
`.template-exclude`, donc absents chez un adoptant ; chaque méthode qui les lit
saute EN LE DISANT (`skipTest` nommé dans le `def`).
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(__file__).resolve().parent


def _charger(nom: str, fichier: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(nom, BIN / fichier)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record_id = _charger("record_id_under_test", "record_id.py")
tasks = _charger("tasks_under_test_record_id", "tasks.py")
specs = _charger("specs_under_test_record_id", "specs.py")
ledger = _charger("ledger_under_test_record_id", "ledger.py")
vendor_paths = _charger("vendor_paths_under_test_record_id", "vendor_paths.py")

#: Deux corps ULID figés : U_LETTER finit par une LETTRE (`numeric_id` lève
#: dessus), U_DIGIT finit par un CHIFFRE (`numeric_id` y lirait 2) ; U_ALLDIG
#: n'a que des chiffres. Les trois sont des ULID, jamais des nombres.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"
U_ALLDIG = "01234567890123456789012345"

# adopting-tree: ni les magasins réels ni le marqueur du kit ne voyagent (strip: .agents/state/, strip: .agents/IS_THE_KIT)
CHEMINS_REELS = {
    "tasks": ".agents/state/board/TASKS.json",
    "specs": ".agents/state/specs/SPECS.json",
    "ledger": ".agents/state/memory/LEDGER.json",
    "kit": ".agents/IS_THE_KIT",
}
MODULES = {"tasks": tasks, "specs": specs, "ledger": ledger}
#: La forme ENREGISTREMENT de chaque magasin (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : les chemins qui la portent.
FORMES_ENREGISTREMENT = {
    "tasks": (".agents/state/board/tasks", ".agents/state/board/epics"),
    "specs": (".agents/state/specs/SPECS.jsonl",),
    "ledger": (".agents/state/memory/entries",),
}


def _forme_reelle(nom: str) -> str | None:
    """La forme PRÉSENTE du magasin réel `nom` : `monolithe` (d'abord), `enregistrements`, ou `None` (ni l'une ni
    l'autre — le seul cas où les (c)-C2 sautent encore : le kit ne saute jamais sur un clone basculé)."""
    if (ROOT / CHEMINS_REELS[nom]).is_file():
        return "monolithe"
    if any((ROOT / rel).exists() for rel in FORMES_ENREGISTREMENT[nom]):
        return "enregistrements"
    return None


def _octets_forme(racine: Path, nom: str) -> dict[str, bytes]:
    """`{chemin relatif: octets}` de la forme enregistrement de `nom` sous `racine` : les fichiers non pointés de chaque
    dossier, ou le fichier lui-même (`SPECS.jsonl`)."""
    octets: dict[str, bytes] = {}
    for rel in FORMES_ENREGISTREMENT[nom]:
        chemin = racine / rel
        if chemin.is_file():
            octets[rel] = chemin.read_bytes()
        elif chemin.is_dir():
            octets.update({f"{rel}/{p.name}": p.read_bytes() for p in sorted(chemin.iterdir())
                           if not p.name.startswith(".") and p.is_file()})
    return octets


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def _sans_compteur(donnees: dict[str, Any]) -> dict[str, Any]:
    """Le magasin MOINS la clé `next_id` et une `sync_outbox` VIDE (T-00001058 : les intents vivent en fichiers)."""
    return {k: v for k, v in donnees.items() if k != "next_id" and not (k == "sync_outbox" and v == [])}  # + T-1058 : outbox VIDE (elle vit en fichiers)


def _canonique(donnees: dict[str, Any]) -> bytes:
    """Les octets que `save()` écrit pour `donnees` (même forme dans les trois modules)."""
    return (json.dumps(donnees, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


#: Les ids que chaque module ALLOUE, et comment : `(module, préfixe, allouer(racine) -> id, clé de liste)`.
ALLOCATEURS = {
    "tasks": (tasks, "T", lambda r: tasks.new_task(str(r), "tâche de banc", "").split()[1], "tasks"),
    "specs": (specs, "S", lambda r: specs.add_entry(r, "T-00000001", "delta", "entrée de banc").split()[1], "entries"),
    "ledger": (ledger, "L", lambda r: ledger.add_entry(r, "lesson", "leçon de banc").split()[1], "entries"),
    # 1(a') (7bis, S6) : le QUATRIÈME site d'allocation, la création liée du pont V3 ; il rend l'id NU.
    "tasks-linked": (tasks, "T", lambda r: tasks.create_linked_task(str(r), "t", "dev-mono", "op-" + r.name), "tasks"),
}
#: Un magasin ANCIEN, avec son compteur : le point de départ des deux branches.
BASES = {
    "tasks": {"next_id": 8, "tasks": [{"id": "T-00000007", "state": "pending", "task": "ancienne", "owner": "",
                                       "stage": "", "updated": "2026-10-01"}]},
    "specs": {"next_id": 8, "entries": [{"id": "S-00000007", "task": "T-00000001", "kind": "plan", "title": "ancienne",
                                         "text": "", "files": [], "date": "2026-10-01"}]},
    "ledger": {"next_id": 8, "entries": [{"id": "L-00000007", "category": "lesson", "title": "ancienne", "text": "",
                                          "created": "2026-10-01", "tags": [], "related": "", "status": "active"}]},
}
BASES["tasks-linked"] = BASES["tasks"]


class _RacineJetable(unittest.TestCase):
    """Une racine jetable, et l'état V3 qui la suit (jamais `~/.local/state`)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)
        env = {"CADRE_STATE_DIR": str(self.racine / "etat"), "AGENTS_EVENTS_DIR": str(self.racine / "evenements"),
               "CADRE_PROJECT_ROOT": str(self.racine)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _semer(self, nom: str, sous: str) -> Path:
        """Pose le magasin ANCIEN `BASES[nom]` sous `<racine>/<sous>` ; rend cette racine."""
        racine = self.racine / sous
        cible = (ALLOCATEURS[nom][0] if nom in ALLOCATEURS else MODULES[nom]).store_path(racine)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps(BASES[nom], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return racine


class FusionDeDeuxBranchesTests(_RacineJetable):
    """1(a) — LA PROPRIÉTÉ (1) DE « ÉTAT PARTAGÉ FUSIONNABLE ». Deux branches nées
    de la MÊME base allouent chacune UN enregistrement : avec un compteur stocké,
    les deux frappent le même `T-00000008` et la fusion perd une tâche (ou ne se
    charge plus : « duplicate id »). Sans compteur, deux `P-<ULID>` distincts, et
    l'union des deux magasins se charge. MUTANT M1 : la frappe rendue au compteur."""

    def _fusion(self, nom: str) -> None:
        module, prefixe, allouer, cle = ALLOCATEURS[nom]
        branches = [self._semer(nom, f"{nom}-{cote}") for cote in ("a", "b")]
        ids = [allouer(racine) for racine in branches]
        self.assertNotEqual(ids[0], ids[1], f"{nom} : deux branches ont frappé le même id")
        for rid in ids:
            self.assertTrue(re.fullmatch(prefixe + "-[0-9A-HJKMNP-TV-Z]{26}", rid), f"{nom} : {rid!r} n'est pas un ULID")
        apres = [module.load(racine) for racine in branches]
        union = dict(apres[0])
        union[cle] = list(apres[0][cle]) + [r for r in apres[1][cle] if r["id"] == ids[1]]
        fusion = self._semer(nom, f"{nom}-fusion")
        module.store_path(fusion).write_bytes(_canonique(union))
        relu = [r["id"] for r in module.load(fusion)[cle]]
        self.assertEqual(sorted([BASES[nom][cle][0]["id"], *ids]), sorted(relu))

    def test_a_deux_branches_de_board_frappent_deux_ids_qui_fusionnent(self) -> None:
        self._fusion("tasks")

    def test_a_deux_branches_de_journal_frappent_deux_ids_qui_fusionnent(self) -> None:
        self._fusion("specs")

    def test_a_deux_branches_de_ledger_frappent_deux_ids_qui_fusionnent(self) -> None:
        self._fusion("ledger")

    def test_a_deux_creations_liees_du_pont_frappent_deux_ids_qui_fusionnent(self) -> None:
        """1(a') — `create_linked_task` (M46 : rendu au compteur, les deux branches frappent le MÊME `T-0000000N`)."""
        self._fusion("tasks-linked")


class GrammaireLecturePureTests(unittest.TestCase):
    """(b) — la LECTURE d'un id `P-<ULID>`, sur les fonctions pures de `tasks`."""

    def test_un_ULID_est_reconnu_sous_les_trois_prefixes(self) -> None:
        for prefixe in ("T", "S", "L"):
            for corps in (U_LETTER, U_DIGIT, U_ALLDIG):
                with self.subTest(prefixe=prefixe, corps=corps):
                    self.assertTrue(tasks.is_ulid_id(f"{prefixe}-{corps}"))

    def test_les_formes_voisines_ne_sont_pas_des_ULID(self) -> None:
        voisines = {
            "25 symboles": f"T-{U_LETTER[:-1]}",
            "27 symboles": f"T-{U_LETTER}0",
            "zéro de tête en trop": f"T-0{U_LETTER}",
            "minuscules": f"T-{U_LETTER.lower()}",
            "I hors Crockford": f"T-{U_LETTER[:-1]}I",
            "L hors Crockford": f"T-{U_LETTER[:-1]}L",
            "O hors Crockford": f"T-{U_LETTER[:-1]}O",
            "U hors Crockford": f"T-{U_LETTER[:-1]}U",
            "fin de ligne": f"T-{U_LETTER}\n",
            "blanc de tête": f" T-{U_LETTER}",
            "préfixe hors T/S/L": f"P-{U_LETTER}",
            "préfixe minuscule": f"t-{U_LETTER}",
            "tiret absent": f"T{U_LETTER}",
            "ancien à 8 chiffres": "T-00000012",
            "ancien court": "T-012",
            "vide": "",
        }
        for raison, tid in voisines.items():
            with self.subTest(raison=raison):
                self.assertFalse(tasks.is_ulid_id(tid), f"{raison} : {tid!r} lu comme un ULID")

    def test_sort_key_a_deux_etages_ancien_par_valeur_ULID_par_corps(self) -> None:
        self.assertEqual((0, 12), tasks.sort_key("T-012"))
        self.assertEqual((0, 12), tasks.sort_key("T-00000012"))
        self.assertEqual((1, U_LETTER), tasks.sort_key(f"T-{U_LETTER}"))
        # Un corps qui FINIT par des chiffres reste un ULID : jamais lu comme un nombre.
        self.assertEqual((1, U_DIGIT), tasks.sort_key(f"T-{U_DIGIT}"))
        self.assertEqual((1, U_ALLDIG), tasks.sort_key(f"T-{U_ALLDIG}"))
        ordre = sorted(
            [f"T-{U_DIGIT}", "T-99999999", f"T-{U_LETTER}", "T-012", "T-00000002"],
            key=tasks.sort_key,
        )
        self.assertEqual(
            ["T-00000002", "T-012", "T-99999999", f"T-{U_LETTER}", f"T-{U_DIGIT}"], ordre,
            "tout ancien avant tout ULID ; anciens par valeur, ULID par corps (temps)",
        )

    def test_identity_key_confond_les_rembourrages_jamais_un_ULID_et_un_nombre(self) -> None:
        self.assertEqual(tasks.identity_key("T-012"), tasks.identity_key("T-00000012"))
        self.assertNotEqual(tasks.identity_key(f"T-{U_DIGIT}"), tasks.identity_key("T-00000002"))
        self.assertNotEqual(tasks.identity_key(f"T-{U_LETTER}"), tasks.identity_key(f"T-{U_DIGIT}"))

    def test_un_id_malforme_leve_toujours(self) -> None:
        for tid in ("T-abc", f"T-{U_LETTER.lower()}", ""):
            with self.subTest(tid=tid), self.assertRaises(tasks.BoardError):
                tasks.sort_key(tid)


#: P-PAR — la table FIXE sur laquelle les trois copies doivent répondre pareil :
#: anciens (courts, à 8 chiffres, `S-1`), ULID sous les trois préfixes, et les
#: formes voisines (25/27 symboles, minuscules, fin de ligne, préfixe hors T/S/L).
TABLE_P_PAR = (
    "T-012", "T-00000726", "S-00001936", "L-00000030", "S-1",
    *(f"{p}-{corps}" for p in ("T", "S", "L") for corps in (U_LETTER, U_DIGIT, U_ALLDIG)),
    f"P-{U_LETTER}", f"P-{U_DIGIT}", f"P-{U_ALLDIG}",
    f"T-{U_LETTER[:-1]}", f"T-{U_LETTER}0", f"T-{U_LETTER.lower()}", f"T-{U_LETTER}\n",
    *(f"S-{U_LETTER[:-1]}{hors}" for hors in "ILOU"),
    f"S-{U_DIGIT}\n", "L-abc", "",
    # 7bis (C2 de S-00004755) : lue `(0, 123)` par les copies pures, ILLISIBLE pour `direct_rang_specs`.
    "S-abc123",
)
FONCTIONS_PURES = ("is_ulid_id", "sort_key", "identity_key")
ERREURS_DE_LECTURE = (tasks.BoardError, specs.SpecsError, ledger.LedgerError)


class PariteDesCopiesPuresTests(unittest.TestCase):
    """P-PAR (T-00001039, R23) — la forme A RECOPIE `ULID_BODY`, `is_ulid_id`,
    `sort_key` et `identity_key` de `tasks_stockage.py` dans `specs.py` et
    `ledger.py`, sans import (S-00003552 : une copie sans frère doit LIRE). Trois
    copies divergent en silence ; ce banc les tient égales sur une table FIXE —
    mutant M34. L'erreur levée sur un id malformé est celle de CHAQUE module : la
    parité porte sur « lève / rend quoi », jamais sur la classe d'erreur."""

    def _issue(self, module: types.ModuleType, fonction: str, tid: str) -> tuple:
        try:
            return ("rend", getattr(module, fonction)(tid))
        except ERREURS_DE_LECTURE:
            return ("lève",)

    def test_meme_grammaire_dans_les_trois_modules(self) -> None:
        self.assertEqual(tasks.ULID_BODY, specs.ULID_BODY)
        self.assertEqual(tasks.ULID_BODY, ledger.ULID_BODY)
        self.assertEqual(tasks._ULID_ID.pattern, specs._ULID_ID.pattern)
        self.assertEqual(tasks._ULID_ID.pattern, ledger._ULID_ID.pattern)

    def test_des_copies_jamais_des_imports(self) -> None:
        for nom, module in (("specs", specs), ("ledger", ledger)):
            for fonction in FONCTIONS_PURES:
                with self.subTest(module=nom, fonction=fonction):
                    copie = getattr(module, fonction)
                    self.assertIsNot(getattr(tasks, fonction), copie)
                    self.assertEqual(module.__name__, copie.__module__, "fonction importée, pas recopiée")

    def test_memes_reponses_sur_la_table_fixe(self) -> None:
        issues_tasks = []
        for fonction in FONCTIONS_PURES:
            for tid in TABLE_P_PAR:
                reference = self._issue(tasks, fonction, tid)
                issues_tasks.append(reference)
                for nom, module in (("specs", specs), ("ledger", ledger)):
                    with self.subTest(fonction=fonction, tid=tid, module=nom):
                        self.assertEqual(reference, self._issue(module, fonction, tid))
        # Témoin de NON-VACUITÉ : la table fait rendre les deux étages ET lever.
        self.assertIn(("rend", (0, 726)), issues_tasks)
        self.assertIn(("rend", (1, U_DIGIT)), issues_tasks)
        self.assertIn(("lève",), issues_tasks)


class MintTests(unittest.TestCase):
    """`mint(P)` — l'allocation. Aucun appelant en C1 : ce banc est son seul usage."""

    def test_mint_rend_un_id_que_la_lecture_pure_reconnait(self) -> None:
        for prefixe in ("T", "S", "L"):
            with self.subTest(prefixe=prefixe):
                tid = record_id.mint(prefixe)
                self.assertEqual(28, len(tid))
                self.assertTrue(tid.startswith(f"{prefixe}-"))
                self.assertTrue(tasks.is_ulid_id(tid), tid)

    def test_mint_est_strictement_croissant_dans_une_copie(self) -> None:
        emis = [record_id.mint("T") for _ in range(64)]
        self.assertEqual(sorted(emis), emis)
        self.assertEqual(len(emis), len(set(emis)))

    def test_un_prefixe_hors_T_S_L_est_refuse(self) -> None:
        for prefixe in ("P", "t", "", "TS"):
            with self.subTest(prefixe=prefixe), self.assertRaises(record_id.RecordIdError):
                record_id.mint(prefixe)

    def test_une_sortie_hors_grammaire_du_generateur_est_refusee(self) -> None:
        for sortie in ("abc", U_LETTER.lower(), U_LETTER + "0", None):
            faux = types.SimpleNamespace(nouvel_ulid=lambda s=sortie: s)
            with self.subTest(sortie=sortie), mock.patch.object(record_id, "_ids", return_value=faux):
                with self.assertRaises(record_id.RecordIdError):
                    record_id.mint("T")


class CopieUniqueTests(unittest.TestCase):
    """(d) — UNE copie du générateur par processus : `record_id._ids()` et la
    couture `run_export._cadre("ledger.ids")` rendent le MÊME module, sous les
    deux branches. Deux copies feraient deux horloges monotones."""

    def _run_export(self) -> Any:
        try:
            vendor_paths.charger_paquet(ROOT, "agentic_v3")
        except vendor_paths.PaquetIntrouvable as exc:
            self.skipTest(f"couture absente : {exc}")
        return importlib.import_module("agentic_v3.db.run_export")

    def test_vendor_seul_charge(self) -> None:
        """La couture charge le paquet choisi par la racine, même après déplacement."""
        attendu = vendor_paths.exiger(ROOT, "agentic_v3").resolve()
        parent = vendor_paths.parent_import(ROOT, "agentic_v3").resolve()
        sans_paquet = [entree for entree in sys.path
                       if Path(entree or os.curdir).resolve() not in {ROOT.resolve(), parent}]
        with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", sans_paquet):
            for nom in list(sys.modules):
                if nom == "agentic_v3" or nom.startswith("agentic_v3."):
                    del sys.modules[nom]
            try:
                run_export = self._run_export()
            except unittest.SkipTest as exc:
                self.fail(f"paquet présent mais import sauté : {exc}")
        self.assertEqual(Path(run_export.__file__).resolve().parents[1], attendu)

    def test_paquet_homonyme_de_provenance_etrangere_refuse(self) -> None:
        """Un paquet déjà chargé d'une autre racine ne doit jamais gagner."""
        intrus = types.ModuleType("agentic_v3")
        intrus.__file__ = "/tmp/paquet-etranger/agentic_v3/__init__.py"
        with mock.patch.dict(sys.modules, {"agentic_v3": intrus}):
            with self.assertRaises(vendor_paths.ProvenanceRefusee):
                try:
                    self._run_export()
                except unittest.SkipTest as exc:
                    self.fail(f"provenance étrangère masquée par un saut : {exc}")

    def test_d_branche_chemin_une_seule_copie_dans_les_deux_ordres(self) -> None:
        run_export = self._run_export()
        neutre = {"cadre": None, "cadre.ledger": None, "cadre.ledger.ids": None}
        for premier_nom in ("run_export", "record_id"):
            with self.subTest(premier=premier_nom), mock.patch.dict(sys.modules, neutre), \
                    mock.patch.dict(run_export._MODULES_CADRE, clear=True):
                sys.modules.pop("_cadre_ledger_ids_v3", None)
                if premier_nom == "run_export":
                    premier = run_export._cadre("ledger.ids")
                    second = record_id._ids()
                else:
                    premier = record_id._ids()
                    second = run_export._cadre("ledger.ids")
                self.assertIs(premier, second)
                self.assertIs(second, sys.modules["_cadre_ledger_ids_v3"])
                self.assertEqual(record_id._IDS_PATH, Path(second.__file__))

    def test_d_branche_paquet_une_seule_copie(self) -> None:
        """Le paquet de l'arbre (`vendor_paths.exiger`, 0 saut) : DEUX ordres × deux
        `sys.path` — (a) aucune entrée d'où `cadre` s'importe (C16 : `cadre` absent),
        (b) le seul parent du paquet de l'arbre. Une seule copie dans chaque cas, et
        elle vient du dossier de l'arbre. Mutant : la copie `_cadre_ledger_ids_v3` (0)
        relue APRÈS le paquet (1) → `run_export` d'abord, deux copies, rouge."""
        run_export = self._run_export()
        dossier = vendor_paths.exiger(ROOT, "cadre").resolve()
        sans_cadre = [e for e in sys.path if not (Path(e or ".") / "cadre" / "__init__.py").is_file()]
        for nom_path, chemins in (("aucun cadre importable", sans_cadre),
                                  ("parent de l'arbre seul", [str(dossier.parent), *sans_cadre])):
            for premier_nom in ("run_export", "record_id"):
                with self.subTest(path=nom_path, premier=premier_nom), mock.patch.dict(sys.modules), \
                        mock.patch.object(sys, "path", chemins), \
                        mock.patch.dict(run_export._MODULES_CADRE, clear=True):
                    for nom in [n for n in sys.modules if n == "cadre" or n.startswith("cadre.")
                                or n == "_cadre_ledger_ids_v3"]:
                        del sys.modules[nom]
                    if premier_nom == "run_export":
                        premier, second = run_export._cadre("ledger.ids"), record_id._ids()
                    else:
                        premier, second = record_id._ids(), run_export._cadre("ledger.ids")
                    self.assertIs(premier, second)
                    self.assertEqual(Path(second.__file__).resolve(), dossier / "ledger" / "ids.py")


class FailClosedTests(unittest.TestCase):
    """(e)-C1 — générateur introuvable ⇒ refus NOMMÉ, jamais un repli."""

    def test_e_generateur_absent_leve_au_texte_exact_sans_rien_ecrire(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as vide:
            absent = Path(vide) / "src" / "cadre" / "ledger" / "ids.py"
            neutre = {"cadre": None, "cadre.ledger": None, "cadre.ledger.ids": None}
            with mock.patch.dict(sys.modules, neutre), mock.patch.object(record_id, "_IDS_PATH", absent):
                avant = dict(sys.modules)
                with self.assertRaises(record_id.RecordIdError) as pris:
                    record_id.mint("T")
                self.assertEqual(avant, dict(sys.modules), "un refus a enregistré un module")
            self.assertEqual([], list(Path(vide).iterdir()), "un refus a écrit sur le disque")
        self.assertEqual(
            f"générateur ULID introuvable : ni paquet `cadre`, ni {absent} — "
            "remède : installer le paquet cadre, ou resynchroniser le kit "
            "(.agents/vendor/cadre/ledger/ids.py à côté de .agents/bin/)",
            str(pris.exception),
        )


class FailClosedAllocationTests(_RacineJetable):
    """(e)-C2 — le refus au SITE d'allocation. (1) Générateur introuvable ⇒
    `new_task` / `specs.add_entry` / `ledger.add_entry` lèvent `RecordIdError`
    (celle du module que charge l'ACCESSEUR, `record_id_module()`), et le magasin
    garde son sha256 : rien d'écrit, aucun fichier temporaire laissé (M5 : un
    repli uuid4 émettrait). (2) `record_id.py` ABSENT d'une copie de la CLI ⇒ la
    copie refuse d'allouer, rc 2, en NOMMANT le remède — jamais un traceback, et
    jamais un id ancien frappé en repli."""

    REMEDE = "git checkout -- .agents/bin/record_id.py"

    def test_e_c2_generateur_absent_aucun_site_n_alloue_ni_n_ecrit(self) -> None:
        absent = self.racine / "vide" / "src" / "cadre" / "ledger" / "ids.py"
        neutre = {"cadre": None, "cadre.ledger": None, "cadre.ledger.ids": None}
        for nom, (module, _prefixe, allouer, _cle) in ALLOCATEURS.items():
            with self.subTest(magasin=nom):
                racine = self._semer(nom, f"e-{nom}")
                magasin = module.store_path(racine)
                avant = _sha(magasin.read_bytes())
                frere = module.record_id_module()
                with mock.patch.dict(sys.modules, neutre), mock.patch.object(frere, "_IDS_PATH", absent):
                    sys.modules.pop("_cadre_ledger_ids_v3", None)
                    with self.assertRaises(frere.RecordIdError) as pris:
                        allouer(racine)
                self.assertIn("générateur ULID introuvable", str(pris.exception))
                self.assertEqual(avant, _sha(magasin.read_bytes()), f"{nom} : un refus a écrit le magasin")
                self.assertEqual([magasin.name], sorted(p.name for p in magasin.parent.iterdir()),
                                 f"{nom} : un refus a laissé un fichier à côté du magasin")

    def test_e_c2_record_id_absent_la_copie_refuse_d_allouer_et_nomme_le_remede(self) -> None:
        cas = {
            "tasks": (sorted(p.name for p in BIN.glob("tasks*.py")), ["tasks.py", "new", "tâche de banc"]),
            "specs": (["specs.py"], ["specs.py", "add", "--task", "T-00000001", "--kind", "delta", "entrée"]),
            "ledger": (["ledger.py"], ["ledger.py", "add", "--category", "lesson", "leçon"]),
        }
        for nom, (fichiers, argv) in cas.items():
            with self.subTest(magasin=nom):
                racine = self._semer(nom, f"copie-{nom}")
                bin_ = racine / ".agents" / "bin"
                bin_.mkdir(parents=True)
                for fichier in fichiers:
                    (bin_ / fichier).write_bytes((BIN / fichier).read_bytes())
                self.assertFalse((bin_ / "record_id.py").exists())
                magasin = MODULES[nom].store_path(racine)
                avant = _sha(magasin.read_bytes())
                fait = subprocess.run(
                    [sys.executable, str(bin_ / argv[0]), "--root", str(racine), *argv[1:]],
                    cwd=str(racine), capture_output=True, text=True, timeout=120,
                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(racine)},
                )
                self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
                self.assertIn(self.REMEDE, fait.stderr)
                self.assertNotIn("Traceback", fait.stderr)
                self.assertEqual(avant, _sha(magasin.read_bytes()), f"{nom} : un refus a écrit le magasin")

    def test_e_c2_cli_generateur_absent_rc2_sans_trace(self) -> None:
        """(e)-C2-CLI (7bis, S5) — une copie de `.agents/bin/*.py` AVEC `record_id.py` mais
        SANS `src/`, jouée sous `python3 -I` (ni paquet `cadre`, ni générateur par chemin) :
        `tasks.py new`, `specs.py add`, `ledger.py add` refusent d'ALLOUER — rc 2, le refus du
        générateur et son remède sur stderr, aucun `Traceback`, aucun magasin écrit ; et
        `tasks.py` n'annonce pas « verbe interrompu » (C6 : le pont dit le refus).
        MUTANT M45 : la clause `RecordIdError` retirée d'UN `main()` ⇒ rc 1 et une trace."""
        copie = self.racine / "copie-cli"
        bin_ = copie / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for fichier in BIN.glob("*.py"):
            (bin_ / fichier.name).write_bytes(fichier.read_bytes())
        self.assertTrue((bin_ / "record_id.py").is_file(), "précondition : le frère d'allocation est là")
        self.assertFalse((copie / "src").exists(), "précondition : aucun générateur par chemin")
        cas = {
            "tasks": ["tasks.py", "new", "tâche de banc"],
            "specs": ["specs.py", "add", "--task", "T-00000001", "--kind", "delta", "entrée"],
            "ledger": ["ledger.py", "add", "--category", "lesson", "leçon"],
        }
        for nom, argv in cas.items():
            with self.subTest(cli=argv[0]):
                racine = self.racine / f"cli-{nom}"
                racine.mkdir()
                fait = subprocess.run(
                    [sys.executable, "-I", str(bin_ / argv[0]), "--root", str(racine), *argv[1:]],
                    cwd=str(racine), capture_output=True, text=True, timeout=120,
                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(racine)},
                )
                self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
                self.assertNotIn("Traceback", fait.stderr)
                self.assertIn("générateur ULID introuvable", fait.stderr)
                self.assertIn("resynchroniser le kit (.agents/vendor/cadre/ledger/ids.py", fait.stderr)
                self.assertNotIn("src/cadre/ledger/ids.py)", fait.stderr)
                self.assertFalse(MODULES[nom].store_path(racine).exists(), f"{nom} : un refus a écrit le magasin")
                if nom == "tasks":
                    self.assertNotIn("verbe interrompu", fait.stderr)


class ChargementParesseuxTests(unittest.TestCase):
    """(e'') — charger `record_id.py` ne charge PAS le générateur (mutant M27).
    Joué en SOUS-PROCESSUS : dans le processus pytest, un banc antérieur qui
    alloue a pu poser la clé, et le témoin mentirait dans les deux sens."""

    def test_e2_charger_record_id_ne_charge_pas_le_generateur(self) -> None:
        sonde = "\n".join((
            "import importlib.util, sys",
            "spec = importlib.util.spec_from_file_location('record_id_e2', sys.argv[1])",
            "module = importlib.util.module_from_spec(spec)",
            "sys.modules[spec.name] = module",
            "spec.loader.exec_module(module)",
            "print('_cadre_ledger_ids_v3' in sys.modules, 'cadre.ledger.ids' in sys.modules,"
            " callable(module.mint))",
        ))
        fait = subprocess.run(
            [sys.executable, "-c", sonde, str(BIN / "record_id.py")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual("False False True", fait.stdout.strip())


#: Charge une COPIE du module par son chemin (argv[1]) et imprime les ids que son
#: `load` lit sous la racine argv[2] — la lecture en processus, hors pytest.
LIRE_LA_COPIE = "\n".join((
    "import importlib.util, json, sys",
    "spec = importlib.util.spec_from_file_location('copie_sans_frere', sys.argv[1])",
    "module = importlib.util.module_from_spec(spec)",
    "sys.modules[spec.name] = module",
    "spec.loader.exec_module(module)",
    "print(json.dumps([e['id'] for e in module.load(sys.argv[2])['entries']]))",
))


class LectureSansFrereSpecsLedgerTests(unittest.TestCase):
    """M33s / M33l (T-00001039, réserve B-C2) — une copie de `specs.py` (resp.
    `ledger.py`) SEULE, sans `record_id.py` ni `src/`, LIT un magasin MIXTE : la
    lecture n'a besoin d'aucun frère (forme A, S-00003552). Mutants M35s / M35l :
    un chemin de LECTURE qui chargerait le frère (l'accesseur de C2) rougit ici."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)
        self.bin = self.racine / ".agents" / "bin"
        self.bin.mkdir(parents=True)

    def _copie_seule(self, fichier: str) -> Path:
        copie = self.bin / fichier
        copie.write_bytes((BIN / fichier).read_bytes())
        self.assertEqual([fichier], sorted(p.name for p in self.bin.iterdir()), "la copie a un frère")
        self.assertFalse((self.racine / "src").exists(), "la copie a un générateur")
        return copie

    def _lancer(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *argv], cwd=str(self.racine),
                              capture_output=True, text=True, timeout=60)

    def _ids_lus(self, copie: Path) -> list:
        fait = self._lancer("-c", LIRE_LA_COPIE, str(copie), str(self.racine))
        self.assertEqual(0, fait.returncode, fait.stderr)
        return json.loads(fait.stdout)

    def test_M33s_une_copie_de_specs_seule_lit_un_journal_mixte(self) -> None:
        copie = self._copie_seule("specs.py")
        entrees = [
            {"id": "S-00000001", "task": "T-00000001", "kind": "plan", "title": "ancienne",
             "text": "", "files": [], "date": "2026-07-26"},
            {"id": f"S-{U_LETTER}", "task": f"T-{U_DIGIT}", "kind": "delta", "title": "neuve",
             "text": "", "files": [], "date": "2026-07-26"},
        ]
        magasin = specs.store_path(self.racine)
        magasin.parent.mkdir(parents=True)
        magasin.write_text(json.dumps({"next_id": 2, "entries": entrees}), encoding="utf-8")
        self.assertEqual(["S-00000001", f"S-{U_LETTER}"], self._ids_lus(copie))
        liste = self._lancer(str(copie), "--root", str(self.racine), "list", "--task", "T-00000001")
        self.assertEqual(0, liste.returncode, liste.stderr)
        self.assertIn("[S-00000001] (T-00000001/plan) ancienne", liste.stdout)
        tout = self._lancer(str(copie), "--root", str(self.racine), "list")
        self.assertEqual(0, tout.returncode, tout.stderr)
        ancienne = tout.stdout.index("[S-00000001] (T-00000001/plan) ancienne")
        neuve = tout.stdout.index(f"[S-{U_LETTER}] (T-{U_DIGIT}/delta) neuve")
        self.assertLess(ancienne, neuve, "un ULID se range après un ancien")

    def test_M33l_une_copie_de_ledger_seule_lit_un_ledger_mixte(self) -> None:
        copie = self._copie_seule("ledger.py")
        base = {"category": "constraint", "text": "", "created": "2026-07-20", "tags": [], "status": "active"}
        entrees = [
            dict(base, id="L-00000030", title="ancienne", related=""),
            dict(base, id=f"L-{U_LETTER}", title="neuve", related=f"T-{U_DIGIT}"),
        ]
        magasin = ledger.store_path(self.racine)
        magasin.parent.mkdir(parents=True)
        magasin.write_text(json.dumps({"next_id": 31, "entries": entrees}), encoding="utf-8")
        self.assertEqual(["L-00000030", f"L-{U_LETTER}"], self._ids_lus(copie))
        liste = self._lancer(str(copie), "--root", str(self.racine), "list")
        self.assertEqual(0, liste.returncode, liste.stderr)
        self.assertLess(liste.stdout.index("ancienne"), liste.stdout.index("neuve"), "un ULID se range après un ancien")
        contexte = self._lancer(str(copie), "--root", str(self.racine), "context")
        self.assertEqual(0, contexte.returncode, contexte.stderr)
        self.assertIn(f"- [L-{U_LETTER}] (constraint/active) neuve", contexte.stdout)
        self.assertIn("- [L-00000030] (constraint/active) ancienne", contexte.stdout)


class MagasinsReelsKitTests(unittest.TestCase):
    """(c)-C2 — les trois magasins RÉELS, sur copie jetable, sous le code de C2.

    Ils REMPLACENT les (c)-C1 de T-00001038 (`test_c1_octets_bruts_*`, lignes de
    l'acceptation du test de fermeture de T-00001042 : `save(load(x)) == x`
    tenait sous C1 et cesse de tenir, PAR CONSTRUCTION, à la bascule). Ce qui
    tient désormais : `save(load(x))` est x MOINS la seule clé `next_id`, dans la
    forme canonique de `save` (dépôt-kit seul : un magasin d'adoptant écrit avant
    les clés sync rend DIFF) ; `next_id` n'est plus écrit, et le cycle est
    idempotent, PARTOUT ; `epics` et le champ `epic` passent (M37 : `save()` par
    liste blanche de clés). M7 (`save()` qui garde `next_id`) n'est PAS tué ici :
    après `load`, qui retire la clé, `save` n'a plus de `next_id` à garder — il l'est
    par `test_state_atomic.py` et les `*SaveTrieLesClesTests`. La vue est comparée À
    ELLE-MÊME — rendue depuis `load(x)` puis depuis `load(save(load(x)))`, même
    processus, racine jetable —, jamais à un `.md` du dépôt (non suivi, daté)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)

    def _cycle(self, nom: str) -> dict[str, Any]:
        """Copie le magasin `nom` DANS SA FORME PRÉSENTE (T-01M4KKMY43ZKCW1YD2Y8JX9MKH : le monolithe, sinon les
        fichiers de sa forme enregistrement) sous une racine jetable, puis load → vue → save → load → vue → save.
        Rend la forme, les octets (le monolithe ; l'ENSEMBLE `{chemin relatif: octets}` sinon) et les vues."""
        module = MODULES[nom]
        forme = _forme_reelle(nom)
        racine = Path(self.tmp.name) / nom
        if forme == "enregistrements":
            source: Any = _octets_forme(ROOT, nom)
            for rel, octets in source.items():
                (racine / rel).parent.mkdir(parents=True, exist_ok=True)
                (racine / rel).write_bytes(octets)

            def lire() -> Any:
                return _octets_forme(racine, nom)
        else:
            cible = racine / CHEMINS_REELS[nom]
            source = (ROOT / CHEMINS_REELS[nom]).read_bytes()
            cible.parent.mkdir(parents=True)
            cible.write_bytes(source)
            lire = cible.read_bytes
        premier = module.load(racine)
        module.render_view(racine, premier)
        vue_1 = module.view_path(racine).read_text(encoding="utf-8")
        module.save(racine, premier)
        octets_1 = lire()
        second = module.load(racine)
        module.render_view(racine, second)
        vue_2 = module.view_path(racine).read_text(encoding="utf-8")
        module.save(racine, second)
        octets_2 = lire()
        return {"forme": forme, "x": source, "b1": octets_1, "b2": octets_2, "v1": vue_1, "v2": vue_2}

    @staticmethod
    def _ecarts(avant: dict[str, bytes], apres: dict[str, bytes]) -> list[str]:
        """Les chemins de la forme enregistrement dont les octets diffèrent (ou qui naissent, ou disparaissent)."""
        return [rel for rel in sorted(set(avant) | set(apres)) if avant.get(rel) != apres.get(rel)]

    def _octets_bruts(self, nom: str) -> None:
        cycle = self._cycle(nom)
        if cycle["forme"] == "enregistrements":
            self.assertTrue(cycle["x"], f"{nom} : forme enregistrement présente mais vide")
            self.assertEqual([], self._ecarts(cycle["x"], cycle["b1"]),
                             f"{nom} (forme enregistrement) : save(load(x)) a changé les octets de ces fichiers")
            self.assertEqual(cycle["v1"], cycle["v2"], f"{nom} : la vue rendue a changé après un cycle")
            return
        avant = json.loads(cycle["x"])
        apres = json.loads(cycle["b1"])
        self.assertEqual(_sans_compteur(avant), apres, f"{CHEMINS_REELS[nom]} : le cycle a changé autre chose que `next_id`")
        self.assertEqual(
            _sha(_canonique(_sans_compteur(avant))), _sha(cycle["b1"]),
            f"{CHEMINS_REELS[nom]} : save(load(x)) n'est pas x moins `next_id`, à l'octet",
        )
        self.assertEqual(cycle["v1"], cycle["v2"], f"{nom} : la vue rendue a changé après un cycle")

    def _exiger_forme(self, nom: str, formes: str) -> None:
        """Magasin `nom` ABSENT (ni monolithe ni enregistrements) : ÉCHEC dans le kit, saut ailleurs. Passe de
        correction F5 (exec-critic de la bascule, constat 5) : le mutant « ne lire que le monolithe » n'était tué que
        par un SAUT sur un kit basculé, et ce banc n'est pas au checks.manifest.json — la porte n'aurait rien vu."""
        if _forme_reelle(nom) is not None:
            return
        message = f"magasin {nom.upper()} absent ({formes})"
        if (ROOT / CHEMINS_REELS["kit"]).is_file():
            self.fail(f"{message} dans le kit : ses magasins y sont suivis, un absent est un lecteur qui ne voit pas "
                      f"leur forme")
        self.skipTest(message)

    def test_c2_octets_bruts_tasks(self) -> None:
        if not (ROOT / CHEMINS_REELS["kit"]).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un board d'adoptant n'est pas tenu à l'octet")
        self._exiger_forme("tasks", "ni TASKS.json ni board/tasks/")
        self._octets_bruts("tasks")

    def test_c2_octets_bruts_specs(self) -> None:
        if not (ROOT / CHEMINS_REELS["kit"]).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un journal d'adoptant n'est pas tenu à l'octet")
        self._exiger_forme("specs", "ni SPECS.json ni SPECS.jsonl")
        self._octets_bruts("specs")

    def test_c2_octets_bruts_ledger(self) -> None:
        if not (ROOT / CHEMINS_REELS["kit"]).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un ledger d'adoptant n'est pas tenu à l'octet")
        self._exiger_forme("ledger", "ni LEDGER.json ni memory/entries/")
        self._octets_bruts("ledger")

    def test_c2_idempotence_sans_compteur(self) -> None:
        absents = [nom for nom in MODULES if _forme_reelle(nom) is None]
        if absents and (ROOT / CHEMINS_REELS["kit"]).is_file():
            self.fail(f"magasin(s) absent(s) dans le kit (ni monolithe ni enregistrements) : {', '.join(absents)}")
        if len(absents) == len(MODULES):
            self.skipTest("aucun magasin réel présent : idempotence sans objet")
        verifies = []
        for nom in MODULES:
            if nom in absents:
                continue
            cycle = self._cycle(nom)
            if cycle["forme"] == "enregistrements":
                self.assertEqual([], self._ecarts(cycle["b1"], cycle["b2"]),
                                 f"{nom} : save(load(save(load(x)))) diffère de save(load(x)) sur ces fichiers")
                verifies.append(nom)
                continue
            self.assertEqual(
                _sha(cycle["b1"]), _sha(cycle["b2"]),
                f"{CHEMINS_REELS[nom]} : save(load(save(load(x)))) diffère de save(load(x))",
            )
            for etape in ("b1", "b2"):
                self.assertNotIn("next_id", json.loads(cycle[etape]), f"{CHEMINS_REELS[nom]} : `next_id` réécrit ({etape})")
            verifies.append(nom)
        if absents:
            self.skipTest(f"magasin(s) absent(s) : {', '.join(absents)} — vérifié(s) : {', '.join(verifies)}")

    def test_c2_epics_survivent(self) -> None:
        self._exiger_forme("tasks", "ni TASKS.json ni board/tasks/")
        cycle = self._cycle("tasks")
        if cycle["forme"] == "enregistrements":
            self._epics_survivent_aux_enregistrements(cycle)
            return
        avant = json.loads(cycle["x"])
        if not avant.get("epics") and not any(t.get("epic") for t in avant["tasks"]):
            self.skipTest("le board ne porte aucune epic : survie sans objet")
        for etape in ("b1", "b2"):
            apres = json.loads(cycle[etape])
            self.assertNotIn("next_id", apres, f"`next_id` réécrit ({etape})")
            self.assertEqual(avant.get("epics"), apres.get("epics"), f"registre `epics` perdu ({etape})")
            self.assertEqual(
                {(t["id"], t.get("epic")) for t in avant["tasks"]},
                {(t["id"], t.get("epic")) for t in apres["tasks"]},
                f"champ `epic` d'une tâche perdu ou déplacé ({etape})",
            )

    def _epics_survivent_aux_enregistrements(self, cycle: dict[str, Any]) -> None:
        """La forme dossier : les `board/epics/*.json` et le champ `epic` des `board/tasks/*.json` ÉGAUX après chaque
        save (T-01M4KKMY43ZKCW1YD2Y8JX9MKH)."""
        epics_rel, taches_rel = FORMES_ENREGISTREMENT["tasks"][1] + "/", FORMES_ENREGISTREMENT["tasks"][0] + "/"

        def releve(octets: dict[str, bytes]) -> tuple[dict[str, bytes], set[tuple[str, Any]]]:
            epics = {rel: o for rel, o in octets.items() if rel.startswith(epics_rel)}
            champs = {(e["id"], (e["record"] or {}).get("epic"))
                      for e in (json.loads(o) for rel, o in octets.items() if rel.startswith(taches_rel))}
            return epics, champs

        avant = releve(cycle["x"])
        if not avant[0] and not any(epic for _id, epic in avant[1]):
            self.skipTest("le board ne porte aucune epic : survie sans objet")
        for etape in ("b1", "b2"):
            apres = releve(cycle[etape])
            self.assertEqual(avant[0], apres[0], f"registre `board/epics/` perdu ou réécrit ({etape})")
            self.assertEqual(avant[1], apres[1], f"champ `epic` d'une tâche perdu ou déplacé ({etape})")


B26 = "[0-9A-HJKMNP-TV-Z]{26}"
#: 1(g) — LE REGISTRE des constantes IMPORTABLES qui RECOPIENT la grammaire d'id
#: (étapes 4 à 6 du plan de T-00000726). `(fichier, constante, colonne, préfixe,
#: ancien accepté, gabarit, groupe)`. Colonnes : `ancree` (`\A…\Z`, ou jugée par
#: `fullmatch` : l'id ENTIER et rien autour) ; `recherche` (extrait l'id ENTIER
#: d'un contexte, et AUCUN ULID d'un voisin `P-0<ULID>` / `P-<ULID>A`) ;
#: `canonique` (l'en-tête d'un ordre pilote, deux copies, W14) ; `entier`
#: (`_SIDS_CITES`, T-00001062 : sur-capture VOULUE, « sur-capturer ne fait que
#: REFUSER davantage » — exception nommée). La colonne « ancien seul » de la
#: rév. 9 (`night_approve._TASK_ID_NUMERIC`) n'a plus de membre : ce nom n'existe
#: plus, `_TASK_ID_FORM` (ancrée) l'a remplacé. Les outils du backlog, non
#: importables, restent tenus par `OutilsBacklogGrammaireTests` (test_depends_add.py).
REGISTRE = (
    (".agents/bin/night_approve.py", "TASK_ID_EXACT", "ancree", "T", "T-00000726", None, None),
    (".agents/bin/night_approve.py", "DELIVERED_ID", "ancree", "T", "T-012", None, None),
    (".agents/bin/night_approve.py", "_TASK_ID_FORM", "ancree", "T", "T-012", None, None),
    (".agents/bin/plan_depends.py", "_SID", "ancree-fullmatch", "S", "S-1", None, None),
    (".agents/bin/kit_code_guard.py", "_TICKET", "ancree", "T", "T-00000726", None, None),
    (".agents/bin/kickoff_arm.py", "ID_RE", "ancree", "T", "T-012", None, None),
    (".agents/bin/dashboard.py", "_TASK_ID_RE", "ancree", "T", "T-012", None, None),
    (".agents/bin/dashboard.py", "_SPECS_ID_RE", "ancree", "S", "S-1", None, None),
    (".agents/bin/night_approve.py", "TASK_PATTERN", "recherche", "T", "T-00000726", "vu {id}, fin", 0),
    (".agents/bin/night_approve.py", "VERDICT_ID", "recherche", "S", "S-1", "vu {id}, fin", 0),
    (".agents/bin/plan_cible.py", "_DECISION", "recherche", "S", "S-1", "décision pilote: {id}", 1),
    (".agents/bin/plan_cible.py", "_TASK_PATTERN", "recherche", "T", "T-012", "vu {id}, fin", 0),
    (".agents/bin/plan_depends.py", "_ARETE", "recherche", "T", "T-012", "ARÊTE: {id} <- T-00000001 | motif", 1),
    (".agents/bin/plan_depends.py", "SUGGESTION_RE", "recherche", "T", "T-012",
     "SUGGESTION: ajouter {id} <- T-00000001", 2),
    (".agents/bin/plan_depends.py", "_SID_DU_MOTIF", "recherche", "S", "S-00003347", "ORDRE PILOTE {id} : x", 1),
    (".agents/bin/tasks.py", "_EPIC_LIGNE", "recherche", "T", "T-012", "EPIC: {id} -> E-01", 1),
    (".agents/bin/specs_graph.py", "TASK_REF_RE", "recherche", "T", "T-012", "vu {id}, fin", 0),
    (".agents/bin/plan_depends.py", "ORDRE_PILOTE_CANONIQUE", "canonique", "S", "S-00003347",
     "ORDRE PILOTE {id} : x", None),
    ("core-scripts/plan_waves.py", "ORDRE_PILOTE_CANONIQUE", "canonique", "S", "S-00003347",
     "ORDRE PILOTE {id} : x", None),
    (".agents/bin/plan_depends.py", "_SIDS_CITES", "entier", "S", "S-00003364", "cf. {id} et S-00003364", None),
    # 7bis (E26, S4) : la voie directe lit le texte NORMALISÉ (casefold) — le groupe rend le CORPS.
    (".agents/bin/tasks.py", "DIRECT_S_ID", "recherche-normalisee", "s", "s-00004741", "decision tranchee {id}", 1),
)


class RegistreGrammaireTests(unittest.TestCase):
    """1(g) — chaque constante du REGISTRE accepte les DEUX formes (l'ULID, et
    l'ancien qu'elle acceptait) et refuse ce qu'aucun écrivain ne frappe : `\\n`
    final, 27 ou 25 symboles, minuscules, préfixe voisin (fixtures B-C8 : ancien
    court `S-1` / `T-012`, minuscule). MUTANTS M30 (une constante reposée à
    l'ancienne grammaire), M30b (la borne `(?![0-9A-Za-z])` retirée d'une
    constante de RECHERCHE), R1-R4. Plus la PARITÉ de la clé d'ordre : `plan_pool`
    et `plan_waves` la RECOPIENT (aucun import de `.agents/bin`) et doivent
    répondre comme `tasks.sort_key` sur la table fixe de P-PAR."""

    _modules: dict[str, types.ModuleType | None] = {}

    @classmethod
    def _module(cls, rel: str) -> types.ModuleType | None:
        if rel not in cls._modules:
            chemin = ROOT / rel
            if not chemin.is_file():
                cls._modules[rel] = None
            elif rel == ".agents/bin/tasks.py":
                cls._modules[rel] = tasks
            else:
                nom = "registre_1g_" + Path(rel).stem
                spec = importlib.util.spec_from_file_location(nom, chemin)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                sys.modules[nom] = module
                if str(chemin.parent) not in sys.path:
                    sys.path.insert(0, str(chemin.parent))
                spec.loader.exec_module(module)
                cls._modules[rel] = module
        return cls._modules[rel]

    def _constante(self, rel: str, nom: str) -> re.Pattern:
        module = self._module(rel)
        if module is None:
            self.skipTest(f"{rel} absent : constante {nom} non jugée")
        return getattr(module, nom)

    @staticmethod
    def _extraits(rx: re.Pattern, texte: str, groupe: int) -> list[str]:
        return [m.group(groupe) for m in rx.finditer(texte)]

    def test_g_chaque_constante_tient_ses_deux_colonnes(self) -> None:
        colonnes = set()
        for rel, nom, colonne, p, ancien, gabarit, groupe in REGISTRE:
            with self.subTest(constante=f"{rel}:{nom}", colonne=colonne):
                rx = self._constante(rel, nom)
                autre = "S" if p == "T" else "T"
                if colonne.startswith("ancree"):
                    juge = rx.fullmatch if colonne == "ancree-fullmatch" else rx.match
                    for bon in (f"{p}-{U_LETTER}", f"{p}-{U_DIGIT}", f"{p}-{U_ALLDIG}", ancien):
                        self.assertTrue(juge(bon), f"{nom} refuse {bon!r}")
                    for mal in (f"{p}-{U_LETTER}\n", f"{ancien}\n", f"{p}-0{U_LETTER}", f"{p}-{U_LETTER}A",
                                f"{p}-{U_LETTER[1:]}", f"{p}-{U_LETTER.lower()}", f"{autre}-{U_LETTER}"):
                        self.assertFalse(juge(mal), f"{nom} accepte {mal!r}")
                elif colonne == "recherche":
                    for bon in (f"{p}-{U_LETTER}", f"{p}-{U_DIGIT}", ancien):
                        self.assertEqual([bon], self._extraits(rx, gabarit.format(id=bon), groupe), nom)
                    for voisin in (f"{p}-0{U_LETTER}", f"{p}-{U_LETTER}A", f"{p}-{U_LETTER.lower()}"):
                        lus = self._extraits(rx, gabarit.format(id=voisin), groupe)
                        self.assertFalse([i for i in lus if re.fullmatch(p + "-" + B26, i or "")],
                                         f"{nom} extrait un ULID de {voisin!r} : {lus}")
                elif colonne == "canonique":
                    for bon in (f"{p}-{U_LETTER}", f"{p}-{U_DIGIT}", ancien):
                        self.assertTrue(rx.match(gabarit.format(id=bon)), f"{nom} refuse {bon!r}")
                    for mal in (f"{p}-0{U_LETTER}", f"{p}-{U_LETTER}A", f"{p}-{U_LETTER.lower()}"):
                        self.assertFalse(rx.match(gabarit.format(id=mal)), f"{nom} accepte {mal!r}")
                elif colonne == "recherche-normalisee":  # minuscules : l'id ENTIER, rien d'un voisin
                    for bon in (f"{p}-{U_LETTER.lower()}", f"{p}-{U_DIGIT.lower()}", ancien):
                        lus = [f"{p}-{corps}" for corps in self._extraits(rx, gabarit.format(id=bon), groupe)]
                        self.assertEqual([bon], lus, nom)
                    for voisin in (f"{p}-0{U_LETTER.lower()}", f"{p}-{U_LETTER.lower()}a", "s-000047451"):
                        self.assertEqual([], self._extraits(rx, gabarit.format(id=voisin), groupe), f"{nom} lit {voisin!r}")
                else:  # entier : la sur-capture est voulue, l'extraction reste ENTIÈRE
                    self.assertEqual([U_LETTER, "00003364"], rx.findall(gabarit.format(id=f"{p}-{U_LETTER}")))
                colonnes.add(colonne)
        self.assertEqual({"ancree", "ancree-fullmatch", "recherche", "recherche-normalisee", "canonique", "entier"},
                         colonnes)

    def test_g_direct_rang_specs_range_comme_specs_et_isole_l_illisible(self) -> None:
        """1(g), 7bis (E26, S1 ; C2 de S-00004755) — la clé d'ORDRE de la voie directe :
        sur toute S-id BIEN FORMÉE (`S-[0-9]{1,15}` ou `S-<ULID>`), la MÊME valeur que
        `specs.sort_key` ; sur le reste de la table P-PAR (dont `S-abc123`, que les copies
        pures lisent `(0, 123)`), `DIRECT_RANG_ILLISIBLE` ; un tri de la table entière ne
        compare jamais un `int` à un `str`. MUTANT M42 (rang `int`, -1 sur un ULID)."""
        rang, illisible = tasks.direct_rang_specs, tasks.DIRECT_RANG_ILLISIBLE
        self.assertEqual((-1, 0), illisible, "parité avec plan_cible._clef_sid")
        bien_formee = re.compile(r"S-(?:" + B26 + r"|[0-9]{1,15})")
        lisibles = [s for s in TABLE_P_PAR if bien_formee.fullmatch(s)]
        self.assertTrue({"S-1", "S-00001936", f"S-{U_LETTER}", f"S-{U_ALLDIG}"} <= set(lisibles), lisibles)
        for sid in lisibles:
            self.assertEqual(specs.sort_key(sid), rang({"id": sid}), sid)
        for sid in [s for s in TABLE_P_PAR if s not in lisibles] + [None]:
            self.assertEqual(illisible, rang({"id": sid}), repr(sid))
        self.assertIn("S-abc123", TABLE_P_PAR)
        self.assertEqual((0, 123), specs.sort_key("S-abc123"), "précondition : la copie pure la lit")
        self.assertEqual(illisible, rang({"id": "S-abc123"}))
        self.assertEqual((0, 0), rang({"id": "S-00000000"}), "la borne d'un SPECS vide (RETOUR_SPECS_VIDE) est lisible")
        ordre = sorted(TABLE_P_PAR, key=lambda s: rang({"id": s}))  # jamais un `int` contre un `str`
        illisibles = len(TABLE_P_PAR) - len(lisibles)
        self.assertEqual({illisible}, {rang({"id": s}) for s in ordre[:illisibles]}, "l'illisible se range sous tout lisible")
        self.assertEqual(f"S-{U_DIGIT}", ordre[-1], "le plus récent des ULID se range en dernier")

    def test_g_les_deux_copies_canoniques_sont_identiques(self) -> None:
        motifs = {rel: self._constante(rel, nom).pattern for rel, nom, colonne, *_ in REGISTRE if colonne == "canonique"}
        self.assertEqual(2, len(motifs), motifs)
        self.assertEqual(1, len(set(motifs.values())), motifs)

    def test_g_plan_pool_et_plan_waves_rangent_comme_tasks(self) -> None:
        cles = (("core-scripts/plan_pool.py", "sort_key", "PoolError"),
                ("core-scripts/plan_waves.py", "numeric_id", "WavesError"))
        for rel, fonction, erreur in cles:
            with self.subTest(module=rel):
                module = self._module(rel)
                if module is None:
                    self.skipTest(f"{rel} absent")
                copie, leve = getattr(module, fonction), getattr(module, erreur)
                for tid in TABLE_P_PAR:
                    try:
                        attendu: tuple = ("rend", tasks.sort_key(tid))
                    except tasks.BoardError:
                        attendu = ("lève",)
                    try:
                        obtenu: tuple = ("rend", copie(tid))
                    except leve:
                        obtenu = ("lève",)
                    self.assertEqual(attendu, obtenu, f"{rel}.{fonction}({tid!r})")


#: Une ligne de chaque magasin, à id ULID, pour 1(h).
LIGNE_TACHE = {"id": f"T-{U_LETTER}", "state": "pending", "task": "neuve", "owner": "dev-multi", "stage": "",
               "updated": "2026-10-09"}
LIGNE_JOURNAL = {"id": f"S-{U_LETTER}", "task": f"T-{U_DIGIT}", "kind": "delta", "title": "neuve", "text": "",
                 "files": [], "date": "2026-10-09"}
LIGNE_LECON = {"id": f"L-{U_LETTER}", "category": "lesson", "title": "neuve", "text": "", "created": "2026-10-09",
               "tags": [], "related": f"T-{U_DIGIT}", "status": "active"}


class LargeurDesVuesTests(_RacineJetable):
    """1(h) — un id `P-<ULID>` fait 28 caractères : `list`, la vue `.md` et le
    board de session le rendent ENTIER, comme le `task` d'une entrée de journal
    et le `related` d'une leçon — jamais coupé en `T-01M3250…` (une référence
    tronquée ne se recopie pas). MUTANTS M31 (`WIDTHS["id"]` laissé à 10), M31'
    (`WIDTHS["task"]` de specs.py, `WIDTHS["related"]` de ledger.py laissés)."""

    def _poser(self, nom: str, cle: str, ligne: dict[str, Any]) -> Path:
        racine = self.racine / f"h-{nom}"
        magasin = MODULES[nom].store_path(racine)
        magasin.parent.mkdir(parents=True)
        magasin.write_text(json.dumps({cle: [ligne]}), encoding="utf-8")
        MODULES[nom].render_view(racine)
        return racine

    def test_h_le_board_rend_l_id_entier_partout(self) -> None:
        racine = self._poser("tasks", "tasks", LIGNE_TACHE)
        rendus = {"list": tasks.render_list(str(racine)), "vue .md": tasks.view_path(racine).read_text(encoding="utf-8"),
                  "board de session": tasks.render_session_board(str(racine))}
        for vue, texte in rendus.items():
            with self.subTest(vue=vue):
                self.assertIn(f"| {LIGNE_TACHE['id']} |", texte)

    def test_h_le_journal_rend_l_id_et_la_tache_entiers(self) -> None:
        racine = self._poser("specs", "entries", LIGNE_JOURNAL)
        vue = specs.view_path(racine).read_text(encoding="utf-8")
        self.assertIn(f"| {LIGNE_JOURNAL['id']} | {LIGNE_JOURNAL['task']} |", vue)
        self.assertIn(f"[{LIGNE_JOURNAL['id']}] ({LIGNE_JOURNAL['task']}/delta)", specs.render_list(racine))

    def test_h_le_ledger_rend_l_id_et_le_related_entiers(self) -> None:
        racine = self._poser("ledger", "entries", LIGNE_LECON)
        rendus = {"list": ledger.render_list(racine), "vue .md": ledger.view_path(racine).read_text(encoding="utf-8")}
        for vue, texte in rendus.items():
            with self.subTest(vue=vue):
                self.assertIn(f"| {LIGNE_LECON['id']} |", texte)
                self.assertIn(f"| {LIGNE_LECON['related']} |", texte)


if __name__ == "__main__":
    unittest.main()
