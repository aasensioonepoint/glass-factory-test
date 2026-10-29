"""Banc de la DÉCOUPE de `tasks.py` (T-00000788, T-00001071) : une façade et onze parties.

`tasks.py` est une FAÇADE : ses parties `tasks_*.py` (liste fermée `PARTIES`)
sont EXÉCUTÉES dans son espace de noms par `_charger_parties()`, jamais
importées (mécanisme A, décision pilote S-00002934 ; règle des lignes par `.py`
S-00002684, relevée de 800 à 1600 par S-00004034). Ce banc tient ce qui rend ce
mécanisme sûr, en deux familles.

TÉMOINS PERMANENTS (a–g), joués à chaque porte :
  (a) `tasks.py` et chaque `tasks_*.py` font au plus 1600 lignes — le cliquet de
      ces fichiers (S-00002844) ;
  (b) les `tasks_*.py` présents sont EXACTEMENT `PARTIES` : une partie orpheline
      ou manquante rougit ici, pas au premier chargement chez un adoptant ;
  (c) toute fonction définie dans un `tasks*.py` a `__globals__ is vars(tasks)`
      (décorateurs déroulés par `__wrapped__`) : c'est CE qui fait qu'un
      `mock.patch.object(tasks, X)`, présent ou futur, atteint le code déplacé,
      par construction et non par une liste à tenir ;
  (d) aucune partie n'ouvre sur une chaîne : exécutée dans l'espace de `tasks`,
      une docstring de partie écraserait `tasks.__doc__` ;
  (e) aucun nom de tête (def, class, affectation, import) n'est défini deux fois
      entre façade et parties — le `from __future__ import annotations` de
      chaque partie RÉPÈTE celui de la façade : répétition déclarée, comptée,
      exclue ;
  (f) deux chargements sous deux noms restent ISOLÉS (`BoardError`,
      `_BOARD_LOCK_DEPTH`, globals distincts), et `__doc__` reste la docstring
      de la façade ;
  (g) un patch posé sur le MODULE atteint une fonction d'une partie, sur une
      racine JETABLE : `board_lock` patché par une levée à message sentinelle,
      `set_writeset` (défini dans `tasks_graphe.py`, chemin valide, donc son
      premier geste après validation EST `board_lock`) lève CE message.
  (h) une partie qui lit à sa définition un nom d'une autre vient APRÈS elle
      dans `PARTIES` (T-00001071 : `DeverseIllisible(BoardError)`).
  MUTANT qui les rougit : le chargeur `exec(compile(...), {})` au lieu de
  `globals()` — (c) et (g) rouges.

TÉMOINS DE PASSE (i, ii), joués seulement si `TASKS_AB_AVANT` nomme le dossier
du `tasks.py` d'AVANT la découpe, avec ses frères `plan_cible.py`,
`plan_depends.py` et `record_id.py` (ancre : `git show <SHA de départ>:.agents/bin/<fichier>` ;
si `TASKS_AB_SHA` est posé, (ii) compare `AVANT/tasks.py` à ce blob, octet pour
octet). Ils prouvent CE passage et ne gardent pas la porte : ils rougiraient au
premier changement légitime du contrat. Leur sortie brute est un livrable.
  (i) CORPUS A/B : l'aide de tête, l'aide de chaque sous-commande qu'elle
      annonce, puis un scénario en régime NU et un en régime ARMÉ
      (`BINOME_REQUIRED`, `PLAN_CHAIN_REQUIRED`, `PLAN_CIBLE_REQUIRED`) ; par
      commande : rc, stdout, stderr, `TASKS.json`, `TASKS.md`. Chaque côté est
      une racine jetable COMPLÈTE, à la MÊME profondeur (le pont V3 est trouvé
      par `parents[2]`) : ses `tasks*.py`, les frères, et ses COPIES
      d'`agentic_v3` et de `src/cadre` — jamais un lien, que `resolve()`
      suivrait jusqu'au dépôt réel (mesuré : `src/cadre` du dépôt était lu des
      deux côtés) ; une sonde d'import MESURE où ils se résolvent. MÊME racine
      absolue, dos à dos dans ce processus, `TZ=UTC`, `COLUMNS=100`. SEULE
      normalisation, déclarée : uuid, horodatages ISO, ids ULID `T-`/`S-`/`L-`
      (alloués à l'horloge ; entiers, ou tronqués par `TASKS.md` avant `…`), ordre des valeurs de
      `sync_correlations` (objet indexé par uuid, écrit `sort_keys=True`) ; la
      FORME brute de `TASKS.json` est comparée à part (fichier == son re-dump
      canonique). Les ids du corpus sont ceux que `new` REND, de chaque côté.
  (ii) IDENTITÉ : multiset des lignes (les retirées sont EXACTEMENT `RETIREES`,
      déclarées ; les ajoutées sont listées) et
      `ast.dump` par nom de tête (identique partout sauf `main`, dont SEUL le
      parseur est extrait dans `_construire_parseur`, prouvé énoncé par
      énoncé, et `cible_inexploitable`, dont SEULE la docstring change) ; les énoncés de tête NON nommés (imports, expressions,
      `if __name__`) comparés en séquence, exclusions déclarées et comptées.
"""
from __future__ import annotations

import ast
import collections
import contextlib
import copy
import difflib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
FACADE = HERE / "tasks.py"
PLAFOND = 1600
AVANT = os.environ.get("TASKS_AB_AVANT", "")
SHA = os.environ.get("TASKS_AB_SHA", "")
if SHA and not re.fullmatch(r"[0-9a-f]{7,64}", SHA):  # jamais une option pour `git show`
    raise SystemExit(f"TASKS_AB_SHA doit être un sha hexadécimal, reçu {SHA!r}")
FRERES = ("plan_cible.py", "plan_depends.py", "record_id.py")  # record_id : `new` alloue son id par lui
# Le résolveur, chargé PAR CHEMIN (patron v3prep, S-01M5BXT85VP4JBBMXVXR9STP5F) : le paquet `cadre` se copie
# depuis là où il vit, `.agents/vendor/cadre` ou l'ancien `src/cadre`, jamais un chemin en dur.
_SPEC_VENDOR = importlib.util.spec_from_file_location("_tasks_decoupe_vendor_paths", HERE / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = VENDOR
_SPEC_VENDOR.loader.exec_module(VENDOR)
SENTINELLE = "banc T-00000788 : le board_lock patché sur le module a été atteint"
NOUVEAUX = ["PARTIES", "_charger_parties", "_construire_parseur"]
# Les SEULES lignes d'origine réécrites (passe 3, critic-opus F3) : deux
# commentaires de `tasks_gardes.py` qui disaient que le harnais copie
# `tasks.py` SEUL — faux depuis la découpe, il copie `tasks*.py`.
RETIREES = collections.Counter({
    "            # 2026-09-18 : `run-recap.test.sh` copie `tasks.py` SEUL dans un dépôt": 1,
    "    où elle sert — un harnais qui copie `tasks.py` SEUL dans un dépôt jetable": 1,
})


def _arbre(chemin: Path) -> ast.Module:
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


def _parties() -> tuple[str, ...]:
    """`PARTIES` lu STATIQUEMENT dans la façade : (a), (b), (d), (e) jugent le
    découpage même quand le chargeur est cassé."""
    for n in _arbre(FACADE).body:
        if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["PARTIES"]:
            return tuple(ast.literal_eval(n.value))
    raise AssertionError("PARTIES absent de tasks.py")


def _charger(nom: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(nom, FACADE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return mod


def _est_future(n: ast.stmt) -> bool:
    return isinstance(n, ast.ImportFrom) and n.module == "__future__"


def _noms(n: ast.stmt) -> list[str]:
    """Les noms qu'un énoncé de tête DÉFINIT ; `[]` pour un énoncé non nommé.

    Un `if`/`try`/`with`/`for`/`while` de tête lie les noms de son corps (imports
    imbriqués compris), sa cible de boucle et ses `as` de `with` — une fois
    chacun, même lié dans deux branches ; `if __name__ …` reste NON nommé. Un
    import de TÊTE reste non nommé : (e) le compte à part, (ii) le compare en
    séquence."""
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [n.name]
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
        return [x.id for c in cibles for x in ast.walk(c) if isinstance(x, ast.Name)]
    if not isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)) or (
            isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)):
        return []
    liens = [n.target] if isinstance(n, ast.For) else [
        i.optional_vars for i in getattr(n, "items", []) if i.optional_vars is not None]
    noms = [x.id for c in liens for x in ast.walk(c) if isinstance(x, ast.Name)]
    for s in [*n.body, *getattr(n, "orelse", []), *getattr(n, "finalbody", []),
              *(s for h in getattr(n, "handlers", []) for s in h.body)]:
        noms += ([(a.asname or a.name).split(".")[0] for a in s.names]
                 if isinstance(s, (ast.Import, ast.ImportFrom)) else _noms(s))
    return list(dict.fromkeys(noms))


def _fichiers() -> list[str]:
    return ["tasks.py", *_parties()]


def trop_longs(fichiers, plafond: int = PLAFOND) -> dict[str, int]:
    """`{nom: lignes}` des fichiers au-delà de `plafond` lignes (fins de ligne
    comptées). Extrait de (a) pour que son SEUIL ait un mutant jouable."""
    return {f.name: n for f in fichiers if (n := f.read_bytes().count(b"\n")) > plafond}


class DecoupePermanente(unittest.TestCase):
    """(a)–(g) : ce qui rend le chargement dans l'espace de noms de `tasks` sûr."""

    def _module(self, nom: str) -> types.ModuleType:
        self.addCleanup(sys.modules.pop, nom, None)
        return _charger(nom)

    def test_vendor_sonde_dans_copie(self):
        """La sonde charge le moteur de la copie, y compris après son déplacement sous vendor."""
        depot = HERE.parents[1]
        v3 = depot / ".agents/vendor/agentic_v3"
        if not (v3 / "__init__.py").is_file():
            v3 = depot / "agentic_v3"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            copie = Path(tmp) / "kit"
            bin_dir = copie / ".agents/bin"
            bin_dir.mkdir(parents=True)
            shutil.copy2(HERE / "vendor_paths.py", bin_dir / "vendor_paths.py")
            for source in (v3, VENDOR.exiger(depot, "cadre")):
                shutil.copytree(source, copie / source.relative_to(depot),
                                ignore=shutil.ignore_patterns("__pycache__", "tests"))
            self.assertTrue(_resolution_v3(copie)[0], "pont ou cadre résolu hors de la copie")

    def test_a_chaque_fichier_tient_sous_le_plafond(self):
        fichiers = [FACADE, *sorted(HERE.glob("tasks_*.py"))]
        self.assertGreater(len(fichiers), 1, "aucune partie trouvée : le témoin serait vide")
        self.assertEqual(trop_longs(fichiers), {}, f"au-delà de {PLAFOND} lignes")

    def test_a_mutant_a_plafond_plus_un_rougit(self):
        """Le seuil de (a) est EXACT : PLAFOND lignes passent, PLAFOND + 1
        rougit. MUTANTS : `> 2 * plafond` (mesuré : laissait tout vert),
        `>= plafond`, et `plafond` ignoré au profit de PLAFOND."""
        with tempfile.TemporaryDirectory() as tmp:
            juste, trop = Path(tmp) / "juste.py", Path(tmp) / "trop.py"
            juste.write_bytes(b"x = 1\n" * PLAFOND)
            trop.write_bytes(b"x = 1\n" * (PLAFOND + 1))
            self.assertEqual(trop_longs([juste]), {})
            self.assertEqual(trop_longs([juste, trop]), {"trop.py": PLAFOND + 1})
            self.assertEqual(trop_longs([juste], plafond=PLAFOND - 1),
                             {"juste.py": PLAFOND})

    def test_b_les_parties_presentes_sont_exactement_PARTIES(self):
        parties = _parties()
        self.assertEqual(len(parties), len(set(parties)), "PARTIES porte un doublon")
        self.assertTrue(parties and all(p.startswith("tasks_") for p in parties), parties)
        self.assertEqual({p.name for p in HERE.glob("tasks_*.py")}, set(parties))

    def test_c_toute_fonction_des_tasks_py_partage_les_globals_de_tasks(self):
        mod = self._module("tasks_decoupe_c")
        g, attendus, vus = vars(mod), set(_fichiers()), collections.Counter()
        for nom, val in list(g.items()):
            for obj in (list(vars(val).values()) if isinstance(val, type) else [val]):
                f = obj.__func__ if isinstance(obj, (staticmethod, classmethod)) else obj
                f = inspect.unwrap(f) if callable(f) else f
                if not isinstance(f, types.FunctionType):
                    continue
                fichier = Path(f.__code__.co_filename).resolve()
                if fichier.parent == HERE and fichier.name in attendus:
                    vus[fichier.name] += 1
                    self.assertTrue(f.__globals__ is g, f"{nom} ({fichier.name}) : globals distincts")
        # NON-VACUITÉ : chaque fichier fournit au moins une fonction relevée, et
        # les trois `@contextmanager` sont bien déroulés vers leur partie.
        self.assertEqual(set(vus), attendus, dict(vus))
        self.assertEqual(Path(inspect.unwrap(mod.board_lock).__code__.co_filename).name,
                         "tasks_stockage.py")

    def test_d_aucune_partie_n_ouvre_sur_une_chaine(self):
        for nom in _parties():
            premier = _arbre(HERE / nom).body[0]
            est_chaine = (isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant)
                          and isinstance(premier.value.value, str))
            self.assertFalse(est_chaine, f"{nom} ouvre sur une chaîne : elle écraserait tasks.__doc__")

    def test_e_aucun_nom_de_tete_defini_deux_fois(self):
        compte, futurs = collections.Counter(), 0
        for nom in _fichiers():
            for n in _arbre(HERE / nom).body:
                if _est_future(n):
                    futurs += 1
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    compte.update((a.asname or a.name).split(".")[0] for a in n.names)
                else:
                    compte.update(_noms(n))
        self.assertGreater(len(compte), 100, "trop peu de noms relevés : le témoin serait vide")
        self.assertEqual(sorted(n for n, c in compte.items() if c > 1), [])
        self.assertEqual(futurs, len(_fichiers()), "un `from __future__` par fichier, déclaré")

    def test_f_deux_chargements_sous_deux_noms_restent_isoles(self):
        a, b = self._module("tasks_decoupe_f1"), self._module("tasks_decoupe_f2")
        self.assertIsNot(a.BoardError, b.BoardError)
        self.assertIsNot(a._BOARD_LOCK_DEPTH, b._BOARD_LOCK_DEPTH)
        self.assertTrue(a.set_state.__globals__ is vars(a), "set_state hors de l'espace du 1er chargement")
        self.assertTrue(b.set_state.__globals__ is vars(b), "set_state hors de l'espace du 2nd chargement")
        self.assertEqual(a.__doc__, ast.get_docstring(_arbre(FACADE), clean=False))

    def test_g_un_patch_sur_le_module_atteint_le_code_d_une_partie(self):
        mod = self._module("tasks_decoupe_g")
        self.assertEqual(Path(mod.set_writeset.__code__.co_filename).name, "tasks_graphe.py")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, mock.patch.dict(
            os.environ, {"CADRE_PROJECT_ROOT": tmp, "CADRE_STATE_DIR": tmp, "AGENTS_EVENTS_DIR": tmp}
        ):
            racine = Path(tmp) / "racine"
            racine.mkdir()
            # L'id RENDU par `new`, jamais un id prédit (T-00000726, règle R-BANCS (i)).
            rendu = re.fullmatch(r"TASKS: (\S+) → pending", mod.new_task(str(racine), "banc", ""))
            self.assertIsNotNone(rendu, "message de `new` inattendu")
            tid = rendu.group(1)
            with mock.patch.object(mod, "board_lock", side_effect=RuntimeError(SENTINELLE)):
                with self.assertRaises(RuntimeError) as cm:
                    mod.set_writeset(str(racine), tid, ["src/a.py"])
            self.assertEqual(str(cm.exception), SENTINELLE)
            # Patch levé, le MÊME appel passe : la sentinelle venait bien du patch.
            mod.set_writeset(str(racine), tid, ["src/a.py"])
            self.assertEqual(mod.writeset_of(mod.load(str(racine))["tasks"][0]), ["src/a.py"])

    def test_h_une_lecture_a_la_definition_suit_sa_source_dans_PARTIES(self):
        """(h) T-00001071 : une partie qui lit À SA DÉFINITION un nom d'une autre partie vient APRÈS elle dans
        `PARTIES`. « À sa définition » = tout ce que l'exécution du module évalue : énoncé de tête entier (corps de
        classe, `if`/`try`/`with` de tête compris), mais d'une fonction ou d'un lambda SEULS ses décorateurs et ses
        défauts (correctif C6 du binôme de la fournée 4 : l'ancien relevé ne voyait ni un corps de classe ni un `if`
        de tête). Non-vacuité : `DeverseIllisible(BoardError)` est relevée. MUTANTS lecture d'aval dans un corps de
        classe, ou dans un `if` de tête, d'une partie d'amont : rouges ici (mesuré sur copie)."""
        parties = _parties()
        source = {k: f for f in parties for n in _arbre(HERE / f).body for k in _noms(n)}

        def lus(n: ast.AST) -> set[str]:
            vus: set[str] = set()

            class V(ast.NodeVisitor):
                def visit_FunctionDef(self, f: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                    for e in [*f.decorator_list, *f.args.defaults, *(d for d in f.args.kw_defaults if d)]:
                        self.visit(e)

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_Lambda(self, f: ast.Lambda) -> None:
                    for e in [*f.args.defaults, *(d for d in f.args.kw_defaults if d)]:
                        self.visit(e)

                def visit_Name(self, x: ast.Name) -> None:
                    if isinstance(x.ctx, ast.Load):
                        vus.add(x.id)

            V().visit(n)
            return vus

        lectures = [(f, nom, source[nom]) for f in parties for n in _arbre(HERE / f).body
                    for nom in sorted(lus(n)) if source.get(nom, f) != f]
        self.assertIn(("tasks_deversement.py", "BoardError", "tasks_stockage.py"), lectures)
        self.assertEqual([x for x in lectures if parties.index(x[2]) > parties.index(x[0])], [])

    def test_fournee_reprise_parent_et_lots_admissibles(self):
        """La preuve PAR TÂCHE atteint les membres ouverts sous les noms de `set_state`
        (`autospec` : un mot-clé inconnu, `reprise=`, lève comme en vrai) ; blocked et clos intacts."""
        mod = self._module("tasks_decoupe_reprise")
        parent = {"id": "T-P", "state": "running", "start_actor": {"auteur": {"nom": "Alice"}}}
        lots = [
            {"id": "T-A", "state": "pending", "stage": "", "fournee": {"parent": "T-P", "lot": "A"}},
            {"id": "T-B", "state": "running", "start_actor": {"auteur": {"nom": "Alice"}},
             "fournee": {"parent": "T-P", "lot": "B"}},
            {"id": "T-C", "state": "blocked", "start_actor": {"auteur": {"nom": "Alice"}},
             "fournee": {"parent": "T-P", "lot": "C"}},
            {"id": "T-D", "state": "done", "start_actor": {"auteur": {"nom": "Alice"}},
             "fournee": {"parent": "T-P", "lot": "D"}},
        ]
        data = {"tasks": [parent, *lots]}
        acteur = {"auteur": {"nom": "Bob"}}
        appels = []
        ids = ("T-P", "T-A", "T-B", "T-C", "T-D")
        preuves = {i: {"ancien": {"auteur": {"nom": "Alice"}}, "nouveau": acteur, "manuel": True,
                       "raison": "motif humain"} for i in ids}
        proprietes = {i: {"ancien": {"auteur": {"nom": "Alice"}}} for i in ids}

        def transferer(_root, tid, state, **kwargs):
            appels.append((tid, kwargs.get("preuve_reprise"), kwargs.get("acteur"),
                           kwargs.get("propriete_attendue")))
            task = mod.find(data, tid)
            task["state"] = state
            task["start_actor"] = copy.deepcopy(kwargs["acteur"])
            return f"TASKS: {tid} → {state}"

        with mock.patch.object(mod, "load", return_value=data), mock.patch.object(
            mod, "set_state", autospec=True, side_effect=transferer
        ):
            mod.fournee_etape_parent("racine", {"parent": parent}, {}, acteur, preuves, proprietes)
            mod.fournee_etape_lots_start("racine", {"parent": parent}, {}, acteur, preuves, proprietes)
            self.assertEqual([a[0] for a in appels], ["T-P", "T-A", "T-B"])
            self.assertTrue(all(preuve is preuves[tid] and qui == acteur and prop is proprietes[tid]
                                for tid, preuve, qui, prop in appels))
            self.assertEqual([(t["state"], t["start_actor"]["auteur"]["nom"]) for t in lots[2:]],
                             [("blocked", "Alice"), ("done", "Alice")])
            appels.clear()
            mod.fournee_etape_parent("racine", {"parent": parent}, {}, acteur)
            mod.fournee_etape_lots_start("racine", {"parent": parent}, {}, acteur)
            self.assertEqual(appels, [], "le nouveau pilote relance sans une seconde raison")

    def test_fournee_transmet_la_reprise_aux_etapes(self):
        """Le verbe transmet preuves et propriétés attendues aux deux étapes, sans les perdre."""
        mod = self._module("tasks_decoupe_dispatch_reprise")
        parent = {"id": "T-P"}
        p = {"parent": parent, "refus": [], "infos": []}
        with mock.patch.object(mod, "load", return_value={"tasks": [parent]}), mock.patch.object(
            mod, "board_lock", return_value=contextlib.nullcontext()
        ), mock.patch.object(mod, "fournee_prevol", return_value=p), mock.patch.object(
            mod, "fournee_entete", return_value="FOURNEE: T-P"
        ), mock.patch.object(mod, "fournee_etape_lots", return_value=[]), mock.patch.object(
            mod, "fournee_etape_writesets", return_value=[]
        ), mock.patch.object(mod, "fournee_etape_direct", return_value=[]), mock.patch.object(
            mod, "fournee_etape_groupe", return_value=[]
        ), mock.patch.object(mod, "fournee_etape_parent", return_value=[]) as etape_parent, mock.patch.object(
            mod, "fournee_etape_lots_start", return_value=[]
        ) as etape_lots:
            preuves, proprietes = {"T-P": {"raison": "motif humain"}}, {"T-P": {"ancien": None}}
            rendu = mod.fournee("racine", "T-P", preuves_reprise=preuves, proprietes_attendues=proprietes,
                                acteur={"auteur": {"nom": "Bob"}})
        self.assertIn("FOURNEE: ok", rendu)
        self.assertEqual(etape_parent.call_args.args[-2:], (preuves, proprietes))
        self.assertEqual(etape_lots.call_args.args[-2:], (preuves, proprietes))

    def test_fournee_ancienne_levee_refusee_avant_lecture(self):
        mod = self._module("tasks_decoupe_sans_revendication")
        with mock.patch.object(mod, "load", side_effect=AssertionError("lecture après refus")):
            with self.assertRaises(mod.BoardError) as cm:
                mod.fournee("racine", "T-P", sans_revendication="ancienne levée")
        self.assertIn("REVENDICATION", str(cm.exception))
        self.assertIn("--reprise", str(cm.exception))


# ---------------------------------------------------------------------------
# TÉMOINS DE PASSE — corpus A/B et identité, contre le `tasks.py` d'AVANT.
# ---------------------------------------------------------------------------
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
# Identifiants ULID (tâche, décision, leçon) : alloués à l'horloge, ils diffèrent d'un côté à l'autre.
_ULID = re.compile(r"\b([TSL])-[0-9A-HJKMNP-TV-Z]{26}\b")
# ... et leur forme TRONQUÉE par une colonne de `TASKS.md` (`on T-01M5CM68ZG5J132S…`, mesuré).
_ULID_TRONQUE = re.compile(r"\b([TSL])-[0-9A-HJKMNP-TV-Z]{4,25}…")
# L'id que `new` rend (`TASKS: T-… → pending`), ULID ou à huit chiffres selon le générateur du côté.
_ID_RENDU = re.compile(r"\bT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\b")


def _norm(texte: str, rendus: tuple[str, ...] | list[str] = ()) -> str:
    """Chaque id que `new` a RENDU de ce côté (`rendus`, dans l'ordre) devient son libellé ORDINAL `T#n`, forme
    tronquée comprise quand son préfixe n'en désigne qu'un : un id mis à la place d'un autre (`on {tid}` au lieu
    de `on {blocker_id}`) reste un ÉCART (S-01M5CP0TM7, mutant G5). Les autres ULID : un même `<ULID>`."""
    for n, tid in enumerate(rendus, 1):
        texte = re.sub(rf"\b{re.escape(tid)}\b", f"T#{n}", texte)

    def tronque(m: re.Match) -> str:
        seuls = [n for n, tid in enumerate(rendus, 1) if tid.startswith(m.group(0)[:-1])]
        return f"T#{seuls[0]}…" if len(seuls) == 1 else f"{m.group(1)}-<ULID>…"

    texte = _ULID_TRONQUE.sub(tronque, _ULID.sub(r"\1-<ULID>", texte))
    return _ISO.sub("<ISO>", _UUID.sub("<UUID>", texte))


def _board(chemin: Path, rendus: list[str]) -> tuple[str, str]:
    """(contenu normalisé, forme brute) de `TASKS.json` ; `("", "absent")` sans fichier."""
    if not chemin.is_file():
        return "", "absent"
    brut = chemin.read_text(encoding="utf-8")
    data = json.loads(brut)
    forme = "canonique" if brut == json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n" \
        else f"NON canonique ({len(_norm(brut, rendus))} car.)"
    if isinstance(data.get("sync_correlations"), dict):
        data["sync_correlations"] = sorted(_norm(json.dumps(v, ensure_ascii=False, sort_keys=True), rendus)
                                           for v in data["sync_correlations"].values())
    return _norm(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), rendus), forme


def _ecrire(racine: Path, rel: str, texte: str) -> None:
    chemin = racine / rel
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")


SPEC = "# Spec du banc\n\n**« contrat déclaré »** — le contrat CLI du board.\n"
PLAN_OK = ("# PLAN — T-00000005 — banc\nTâches : T-00000005\n\n### Étape 1 — un geste\n"
           "cible: « contrat déclaré »\n\n### Étape 2 — un autre\nangle mort: la question au pilote\n")
PLAN_TROU = ("# PLAN — T-00000005 — banc\nTâches : T-00000005\n\n### Étape 1 — un geste\n"
             "cible: « contrat déclaré »\n\n### Étape 2 — sans cible\nrien ici\n")


# Mesure la résolution par `vendor_paths.charger_paquet` (copie du résolveur), plus l'amorçage réel `amorcer_cli`.
_SONDE_V3 = ("import importlib.util as u, sys; from pathlib import Path; "
             "p=Path(sys.argv[1]); s=u.spec_from_file_location('vendor_paths_sonde', p/'.agents/bin/vendor_paths.py'); "
             "v=u.module_from_spec(s); sys.modules[s.name]=v; s.loader.exec_module(v); v.charger_paquet(p, 'agentic_v3'); "
             "from agentic_v3.reconciliation import board_bridge as b; "
             "from agentic_v3.db import run_export as r; "
             "print(b.__file__); print(r._SRC_CADRE); print(u.find_spec('cadre') is not None)")


def _resolution_v3(cote: Path) -> tuple[bool, bool]:
    """(pont ET `src/cadre` résolus DANS la copie de `cote`, un paquet `cadre`
    installé gagnerait) — MESURÉ par le résolveur copié avec la façade,
    dans l'environnement du corpus."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    p = subprocess.run([sys.executable, "-c", _SONDE_V3, str(cote)], capture_output=True, text=True,
                       env=env, cwd=str(cote.parent), timeout=120)
    lignes, racine = p.stdout.splitlines(), cote.resolve()
    if p.returncode != 0 or len(lignes) != 3:
        return False, False
    dedans = [Path(x).resolve().is_relative_to(racine) for x in lignes[:2]]
    return all(dedans) and Path(lignes[1]).is_dir(), lignes[2] == "True"


def _jouer(base: Path, bin_dir: Path, at: str) -> tuple[list[dict], dict[str, int]]:
    """Joue le corpus contre `bin_dir/tasks.py` sur `base/racine` ; rend les
    enregistrements et le compte des aides et des refus par régime."""
    racine, etat = base / "racine", base / "etat"
    for d in (racine, etat):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(TZ="UTC", COLUMNS="100", PYTHONDONTWRITEBYTECODE="1", CADRE_PROJECT_ROOT=str(racine),
               CADRE_STATE_DIR=str(etat), AGENTS_EVENTS_DIR=str(etat))
    sorties: list[dict] = []
    compte = collections.Counter()
    regime = ["aide"]
    rendus: list[str] = []  # les ids que `new` a RENDUS de ce côté, dans l'ordre : `T#n` après `_norm`

    def run(*argv: str) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, str(bin_dir / "tasks.py"), "--root", str(racine), *argv],
                           capture_output=True, text=True, env=env, timeout=180)
        if argv[:1] == ("new",) and (trouve := _ID_RENDU.search(p.stdout)):
            rendus.append(trouve.group(0))
        contenu, forme = _board(racine / ".agents/state/board/TASKS.json", rendus)
        vue = racine / ".agents/state/local/TASKS.md"
        sorties.append({"argv": _norm(" ".join(argv), rendus), "rc": p.returncode, "stdout": _norm(p.stdout, rendus),
                        "stderr": _norm(p.stderr, rendus), "TASKS.json": contenu, "forme": forme,
                        "TASKS.md": _norm(vue.read_text(encoding="utf-8"), rendus) if vue.is_file() else ""})
        compte[regime[0]] += 1
        if p.returncode != 0 and regime[0] != "aide":
            compte[f"refus {regime[0]}"] += 1
        return p

    # Les ids sont ceux que `new` REND (ULID d'horloge, ou huit chiffres selon le générateur du côté),
    # jamais devinés ; `T[9]` reste une tâche INCONNUE. Un `new` refusé laisse un id qu'aucune tâche ne porte.
    T: dict[int, str] = {9: "T-00000009"}

    def nouvelle(n: int, *argv: str) -> None:
        trouve = _ID_RENDU.search(run("new", *argv).stdout)
        T[n] = trouve.group(0) if trouve else f"T-0000000{n}"

    run("--help")
    tete = sorties[0]["stdout"]
    commandes = re.search(r"\{([a-z,-]+)\}", tete).group(1).split(",")
    for c in commandes:
        run(c, "--help")

    regime[0] = "nu"
    run("list")
    run("--statusline")
    nouvelle(1, "alpha", "--owner", "dev-mono", "--chantier", "lot")
    nouvelle(2, "beta")
    nouvelle(3, "gamma", "--chantier", "autre")
    nouvelle(4, "delta")
    run("new")
    run("start", T[1], "--stage", "dev-multi")
    run("stage", T[1], "revue")
    run("start", T[2])
    run("start", T[1])
    run("block", T[2], "--note", "attente amont", "--on", T[1])
    run("list", "--blocked-by", T[1])
    run("block", T[9], "--note", "inconnue")
    run("unblock", T[2])
    run("unblock", T[2])
    run("retitle", T[2], "beta bis")
    run("reassign", T[2], "planner")
    run("regroup", T[2], "lot")
    run("regroup", T[4], "")
    run("writeset", T[1], "src/a.py", "src/b/")
    run("writeset", T[2], "src/c.py")
    run("writeset", T[3], "src/con")
    run("writeset", T[3], "../hors.py")
    run("writeset", T[3], "--clear", "src/x.py")
    run("writeset", T[4], "src/a.py")
    run("parallel", T[1], T[2])
    run("parallel", T[1], T[4])
    run("depends", T[4], T[3], "--motif", "technique : gamma livre")
    run("depends", T[3], T[4], "--motif", "technique : cycle")
    run("depends", T[4], T[4])
    run("depends-show", T[4])
    run("list", "--depends-on", T[3])
    run("list", "--json", "--state", "pending")
    run("list", "--group", "--state", "pending")
    run("list", "--group", "--json")
    run("list", "--chantier", "lot")
    run("list", "--task", T[9])
    run("list", "--json", "--task", T[9])
    run("list", "--state", "inconnu")
    run("block", T[4], "--on", T[1])  # libéré au `done`, re-bloqué au `reopen`
    run("done", T[1])
    run("done", T[1], "--raison", "livré")
    run("reopen", T[1], "--raison", "clôture fausse")
    run("done", T[1], "--raison", "livré bis")
    run("reopen", T[4], "--raison", "pas close")
    run("start", T[9])
    run("stage", T[9], "x")
    run("delete", T[3])
    run("delete", T[3], "--force")
    run("purge", "--dry-run")
    run("purge", "--state", "done", "--before", "2000-01-01")
    run("purge", "--before", "pas-une-date")
    run("purge")
    run("render")
    run("replay-sync")
    run("commit-stores", "--lock-timeout", "1")
    run("commit-run-exports", "--lock-timeout", "1", "--exiger")
    run("cible-check", "docs/absent.md")
    run("verbe-inconnu")
    run("--statusline")
    run("list")

    regime[0] = "armé"
    _ecrire(racine, ".agents/state/gates/BINOME_REQUIRED", "")
    _ecrire(racine, ".agents/state/gates/PLAN_CHAIN_REQUIRED", "")
    _ecrire(racine, ".agents/state/gates/PLAN_CIBLE_REQUIRED", "spec=docs/spec.md\nchantier=lot\n")
    _ecrire(racine, "docs/spec.md", SPEC)
    _ecrire(racine, "docs/tasks/plan-ok.md", PLAN_OK)
    _ecrire(racine, "docs/tasks/plan-trou.md", PLAN_TROU)
    nouvelle(5, "armée dans le chantier", "--chantier", "lot")
    nouvelle(6, "armée hors chantier")
    run("start", T[6])
    run("start", T[6], "--sans-chaine", "banc : chaîne")
    run("done", T[6], "--raison", "fin")
    run("done", T[6], "--raison", "fin", "--sans-binome", "banc : binôme")
    run("start", T[5])
    for nom, role in (("plan-critic", "reviewer"), ("plan-critic-sonnet-max", "reviewer"), ("planner", "planner")):
        _ecrire(racine, f".agents/state/local/plan/{nom}.json", json.dumps({"at": at, "sha": "0000000", "role": role}))
    run("start", T[5])
    run("start", T[5], "--sans-cible", "banc : cible")
    run("start", T[5], "--sans-chaine", "banc", "--sans-cible", "banc", "--sans-dependances", "banc")
    run("done", T[5], "--raison", "fin")
    for nom in ("critic-opus", "critic-fable"):
        _ecrire(racine, f".agents/state/local/binome/{T[5]}.{nom}.json",
                json.dumps({"agent": nom, "task": T[5], "sha": "0000000", "at": at}))
    run("done", T[5], "--raison", "fin")
    run("done", T[5], "--raison", "fin", "--sans-cible", "banc : cible")
    run("done", T[5], "--raison", "fin", "--sans-cible", "banc", "--sans-dependances", "banc")
    run("reopen", T[5], "--raison", "rouvrir", "--sans-rebloquer")
    run("cible-check", "docs/tasks/plan-ok.md")
    run("cible-check", "docs/tasks/plan-trou.md")
    run("cible-check", "docs/tasks/plan-ok.md", "--spec", "docs/absent.md")
    nouvelle(7, "armée aval", "--chantier", "lot")
    run("depends", T[7], T[5], "--motif", "technique : amont livre")
    run("depends", T[7], T[5], "--motif", "ORDRE PILOTE S-00000001 : ordre")
    run("depends-show", T[7])
    run("start", T[7], "--sans-chaine", "banc")
    _ecrire(racine, ".agents/state/gates/PLAN_CIBLE_REQUIRED", "n'importe quoi\n")
    run("start", T[7], "--sans-chaine", "banc")
    run("done", T[7], "--raison", "fin", "--sans-binome", "banc")
    run("depends", T[7], "--clear")
    # PAS `cible-check <plan>` NU ici : sous ce marqueur malformé, sa sortie
    # dépend du `plan_cible.py` de l'AVANT, copié des DEUX côtés. Antérieur à
    # T-00000814, il lève une `CibleError` en trace (rc 1), qui nomme fichier et
    # ligne : pas un contrat comparable. Postérieur, il rend un refus nommé en
    # rc 2 (tenu par `test_plan_cible_pertinence.py`). L'omettre garde le corpus
    # jouable contre tout AVANT.
    run("cible-check", "docs/tasks/plan-ok.md", "--spec", "docs/spec.md")
    run("--statusline")
    run("list", "--group")
    compte["commandes"] = len(commandes)
    compte["v3"] = int(any(etat.rglob("v3_event_store.db")))
    return sorties, dict(compte)


@unittest.skipUnless(AVANT, "TASKS_AB_AVANT non posé : témoins de PASSE (corpus A/B, identité) non joués")
class DecoupePasse(unittest.TestCase):
    """(i), (ii) : ce passage-ci ne change ni le contrat CLI ni le code."""

    def test_i_corpus_ab_zero_ecart(self):
        avant = Path(AVANT).resolve()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base = Path(tmp)
            # T-01M5BXTGX5YN8XEXTG1PP7A5ZX : le résolveur `vendor_paths.py` voyage avec les parties (sans lui, le pont
            # de l'APRÈS est éteint en silence) ; un AVANT antérieur à lui n'en porte pas, d'où le glob de ce côté.
            sources = {"avant": [avant / "tasks.py", *sorted(avant.glob("tasks_*.py")),  # T-1071 : un AVANT découpé
                                 *sorted(avant.glob("vendor_paths.py"))],
                       "apres": [FACADE, *sorted(HERE.glob("tasks_*.py")), HERE / "vendor_paths.py"]}
            depot, ignore = HERE.parents[1], shutil.ignore_patterns("__pycache__", "tests")
            v3 = ".agents/vendor/agentic_v3" if (depot / ".agents/vendor/agentic_v3/__init__.py").is_file() else "agentic_v3"
            cadre = VENDOR.exiger(depot, "cadre").relative_to(depot).as_posix()  # absent : LÈVE, jamais à vide
            copies = [r for r in (v3, cadre) if (depot / r / "__init__.py").is_file()]
            for cote, fichiers in sources.items():
                bin_dir = base / cote / ".agents" / "bin"
                bin_dir.mkdir(parents=True)
                for f in [*fichiers, *(avant / n for n in FRERES)]:
                    shutil.copy2(f, bin_dir / f.name)
                for rel in copies:  # une copie ratée LÈVE : jamais une parité jouée à vide
                    shutil.copytree(depot / rel, base / cote / rel, ignore=ignore)
            resolution = {cote: _resolution_v3(base / cote) for cote in sources}
            at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            joue = {cote: _jouer(base, base / cote / ".agents" / "bin", at) for cote in sources}
        (a, ca), (b, cb) = joue["avant"], joue["apres"]
        engage = len(copies) == 2
        ecarts = [(i, cle) for i, (x, y) in enumerate(zip(a, b)) for cle in x if x[cle] != y[cle]]
        if len(a) != len(b):
            ecarts.append((min(len(a), len(b)), f"longueur {len(a)} != {len(b)}"))
        print(f"\nCORPUS A/B : {len(a)} commandes × 5 sorties (rc, stdout, stderr, TASKS.json, TASKS.md)"
              f" + forme de TASKS.json ; aides {ca.get('aide')} (tête + {ca.get('commandes')} sous-commandes) ;"
              f" régime nu {ca.get('nu')} commandes dont {ca.get('refus nu', 0)} refus ;"
              f" régime armé {ca.get('armé')} dont {ca.get('refus armé', 0)} refus ;"
              f" comptes avant == après : {ca == cb}")
        print(f"PONT V3 : store V3 créé sous l'état jetable avant={ca.get('v3')} après={cb.get('v3')} ;"
              f" COPIÉS par côté, aucun lien : {copies} ; pont et `src/cadre` résolus DANS la copie"
              f" du côté (sonde d'import) : { {c: r[0] for c, r in resolution.items()} } ;"
              f" paquet `cadre` installé qui gagnerait : { {c: r[1] for c, r in resolution.items()} }")
        print(f"CORPUS A/B : écarts = {len(ecarts)}")
        for i, cle in ecarts[:8]:
            if isinstance(cle, str) and cle.startswith("longueur"):
                print(f"  [{i}] {cle}")
                continue
            print(f"  [{i}] `{a[i]['argv']}` — {cle} :")
            for ligne in list(difflib.unified_diff(str(a[i][cle]).splitlines(), str(b[i][cle]).splitlines(),
                                                   "avant", "après", lineterm="", n=1))[:12]:
                print(f"      {ligne}")
        self.assertGreater(ca.get("refus nu", 0), 0)
        self.assertGreater(ca.get("refus armé", 0), 0)
        # NON-VACUITÉ : une parité de traces (tout rc 1 des deux côtés) serait verte.
        self.assertEqual(next(x for x in a if x["argv"].startswith("new alpha"))["rc"], 0)
        # ... et les ids du corpus sont ceux que `new` a rendus : le premier `start` les trouve.
        self.assertEqual(next(x for x in a if x["argv"].startswith("start ")
                              and x["argv"].endswith("--stage dev-multi"))["rc"], 0)
        if engage:
            self.assertEqual((ca.get("v3"), cb.get("v3")), (1, 1), "pont V3 non construit : parité à vide")
            self.assertEqual({c: r[0] for c, r in resolution.items()}, {"avant": True, "apres": True})
        self.assertEqual(ca, cb)
        self.assertEqual(ecarts, [])

    def test_ii_identite_lignes_et_ast(self):
        if any(Path(AVANT).glob("tasks_*.py")):  # (ii) juge le SEUL passage T-788 : un fichier vers dix parties
            self.skipTest("(ii) hors objet : TASKS_AB_AVANT porte déjà des parties (passage postérieur à T-00000788)")
        if SHA:  # l'AVANT est-il bien le blob du SHA de départ ? octet pour octet
            ref = subprocess.run(["git", "-C", str(HERE), "show", f"{SHA}:.agents/bin/tasks.py"],
                                 capture_output=True, check=True, timeout=60).stdout
            ancre = (Path(AVANT) / "tasks.py").read_bytes() == ref
            print(f"\nANCRE : AVANT/tasks.py == `git show {SHA}:.agents/bin/tasks.py` : {ancre} ({len(ref)} octets)")
            self.assertTrue(ancre, f"TASKS_AB_AVANT ne porte pas le tasks.py de {SHA}")
        else:
            print("\nANCRE : TASKS_AB_SHA non posé — AVANT/tasks.py non comparé à un SHA")
        src_avant = (Path(AVANT) / "tasks.py").read_text(encoding="utf-8")
        apres = {nom: (HERE / nom).read_text(encoding="utf-8") for nom in _fichiers()}
        la = collections.Counter(src_avant.splitlines())
        lp = collections.Counter(l for s in apres.values() for l in s.splitlines())
        retirees, ajoutees = la - lp, lp - la
        print(f"\nIDENTITÉ lignes : avant={sum(la.values())} après={sum(lp.values())} "
              f"retirées={sum(retirees.values())} ajoutées={sum(ajoutees.values())}")
        for ligne, c in sorted(retirees.items()):
            print(f"  - ×{c} {ligne!r}")
        for ligne, c in sorted(ajoutees.items()):
            print(f"  + ×{c} {ligne!r}")

        arbre_avant = ast.parse(src_avant)
        arbres = {nom: ast.parse(s) for nom, s in apres.items()}
        n_avant = {k: n for n in arbre_avant.body for k in _noms(n)}
        n_apres = {k: n for a in arbres.values() for n in a.body for k in _noms(n)}
        absents = sorted(set(n_avant) - set(n_apres))
        nouveaux = sorted(set(n_apres) - set(n_avant))
        differents = sorted(k for k in n_avant if k in n_apres and ast.dump(n_avant[k]) != ast.dump(n_apres[k]))
        print(f"IDENTITÉ ast : {len(n_avant)} noms de tête avant, {len(n_apres)} après ; "
              f"absents={absents} différents={differents} nouveaux={nouveaux}")

        # `main` : SEUL le parseur est extrait, énoncé par énoncé.
        m_avant, m_apres, parseur = n_avant["main"], n_apres["main"], n_apres["_construire_parseur"]
        k = next(i for i, s in enumerate(m_avant.body) if ast.unparse(s) == "args = ap.parse_args(argv)")
        dumps = lambda corps: [ast.dump(s) for s in corps]  # noqa: E731
        main_ok = (dumps(parseur.body) == dumps(m_avant.body[:k]) + dumps(ast.parse("return ap").body)
                   and ast.unparse(m_apres.body[0]) == "ap = _construire_parseur(argv)"
                   and dumps(m_apres.body[1:]) == dumps(m_avant.body[k:])
                   and ast.dump(m_apres.args) == ast.dump(m_avant.args)
                   and ast.dump(m_apres.returns) == ast.dump(m_avant.returns))
        print(f"IDENTITÉ main : {k} énoncés de parseur extraits à l'identique + `return ap`, "
              f"{len(m_avant.body) - k} énoncés de répartition inchangés : {main_ok}")

        # Énoncés de tête NON nommés, en séquence ; exclusions déclarées et comptées.
        seq_avant = [ast.dump(n) for n in arbre_avant.body if not _noms(n)]
        seq_apres, exclus = [], []
        for nom, a in arbres.items():
            for n in a.body:
                if _noms(n):
                    continue
                if (nom != "tasks.py" and _est_future(n)) or (
                        nom == "tasks.py" and ast.unparse(n) == "_charger_parties()"):
                    exclus.append(f"{nom}: {ast.unparse(n)}")
                    continue
                seq_apres.append(ast.dump(n))
        print(f"IDENTITÉ non nommés : {len(seq_avant)} avant, {len(seq_apres)} après, "
              f"séquences égales : {seq_avant == seq_apres} ; exclus déclarés = {len(exclus)}")
        self.assertEqual(retirees, RETIREES)
        self.assertEqual(absents, [])
        # `cible_inexploitable` : SA DOCSTRING seule change (ligne de `RETIREES`, binôme F3).
        ci_a, ci_p = n_avant["cible_inexploitable"], n_apres["cible_inexploitable"]
        doc_seule = dumps(ci_a.body[1:]) == dumps(ci_p.body[1:]) and ast.dump(ci_a.args) == ast.dump(ci_p.args)
        print(f"IDENTITÉ cible_inexploitable : identique hors docstring : {doc_seule}")
        self.assertEqual(differents, ["cible_inexploitable", "main"])
        self.assertTrue(doc_seule)
        self.assertEqual(nouveaux, NOUVEAUX)
        self.assertTrue(main_ok)
        self.assertEqual(seq_avant, seq_apres)
        self.assertEqual(len(exclus), len(_parties()) + 1, exclus)


if __name__ == "__main__":
    unittest.main()
