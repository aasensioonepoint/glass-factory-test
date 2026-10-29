#!/usr/bin/env python3
"""BANC DE DISCIPLINE LOCAL — aucune E/S hors `Workspace` dans le service ledger.

Étape C (point 5) de T-012. Le filet global `check_orchestration_purity` ne
couvre PAS `exists`/`is_file`/`stat` (le `+3` reste au LOT-3 — `is_dir` l'a
rejoint par T-00000633). Ce banc-ci resserre sur `src/cadre/ledger/**` ET LUI
SEUL :

  - jeu `IO_PAR_METHODE ∪ {is_dir, exists, is_file, stat}` sur TOUT `ledger/**`
    (store.py COMPRIS — il ne doit toucher au disque QUE par `connect`) ;
  - `connect` interdit dans `ledger/**` SAUF `store.py`, l'unique ouverture de
    connexion (R-A14) — et SAUF `store.connect(…)` appelé depuis `stores.py`,
    exemption NOMMÉE `PRODUCTEUR_CHARGE`, bornée à ce récepteur et à ce fichier.

Sans lui, le `+3` du LOT-3 rougirait rétroactivement ce livrable (TRAP 1 : un
filet d'architecture est un analyseur de TEXTE à portée de FICHIER ; on garde
l'E/S TEXTUELLEMENT dans `ledger/`, derrière un récepteur annoté, plutôt que de
la déporter pour « la faire passer »). La reconnaissance d'un récepteur
`Workspace` lit l'ANNOTATION, jamais le type réel — même choix que le filet
global (`_noms_de_workspace`).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` OÙ QU'IL VIVE (`.agents/vendor/cadre` d'abord, puis `src/cadre`) :
# `vendor_paths.py` chargé PAR CHEMIN, jamais un `src` en dur (T-01M5BXTPQE, lot H).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ledger_purete_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
LEDGER = _VENDOR.exiger(ROOT, "cadre") / "ledger"

#: `IO_PAR_METHODE` du filet global ∪ le `+3` (exists, is_file, stat) que lui ne
#: couvre pas encore. LITTÉRAL INDÉPENDANT (jamais `GLOBAL | {...}`, qui serait
#: vrai par construction et injouable) : le témoin
#: `test_le_jeu_local_est_le_jeu_global_plus_trois` rougit si les deux divergent.
IO_PAR_METHODE = {
    "read_text", "read_bytes", "write_text", "write_bytes", "unlink", "mkdir",
    "rmdir", "touch", "glob", "rglob", "iterdir", "open", "replace", "rename",
    "chmod", "walk", "resolve", "is_dir", "exists", "is_file", "stat",
}
STORE = "store.py"
#: SEULE autre ouverture tolérée, NOMMÉE et bornée : dans `stores.py`, un
#: `.connect` dont le récepteur est le nom `store` — `cadre.ledger.store`, le SEUL
#: définisseur de `sqlite3.connect` du service, appelé par `stores.py` pour ouvrir
#: les trois stores de l'adoptant. Depuis T-00000646 (S-00001590) aucun module
#: producteur n'est plus chargé depuis la racine cible : l'ancien récepteur
#: `module` n'existe plus et n'est plus toléré. Écrit ici plutôt que masqué par
#: `getattr(store, "connect")` : une ruse textuelle qui aveugle le banc est
#: exactement ce que le Trap 1 interdit (binôme C, 2026-09-17). Le nom de la
#: constante est gardé pour que ses citations restent résolvables.
PRODUCTEUR_CHARGE = ("stores.py", "store")


def _fichiers_ledger() -> list[Path]:
    return sorted(LEDGER.rglob("*.py")) if LEDGER.is_dir() else []


def _noms_de_workspace(arbre: ast.AST) -> set[str]:
    """Les noms DÉCLARÉS `Workspace` par annotation (paramètre, `AnnAssign`) ou
    par liaison directe `x = Workspace(...)`."""
    noms: set[str] = set()

    def _est_ws(annotation) -> bool:
        return annotation is not None and "Workspace" in ast.unparse(annotation)

    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
                and isinstance(n.value.func, ast.Name) and n.value.func.id == "Workspace":
            noms |= {c.id for c in n.targets if isinstance(c, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                and _est_ws(n.annotation):
            noms.add(n.target.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
                if _est_ws(arg.annotation):
                    noms.add(arg.arg)
    return noms


def _fautifs_purete(rel_ledger: str, arbre: ast.AST) -> list[str]:
    """Les infractions de pureté d'UN fichier de `ledger/**`, désigné par son
    chemin RELATIF à `ledger/` (`rel_ledger`) et donné par son AST. Extrait tel
    quel de la boucle du balayage réel pour que le témoin de l'exemption
    `connect` le joue sur des sources SYNTHÉTIQUES."""
    fautifs: list[str] = []
    ateliers = _noms_de_workspace(arbre)
    rel = (LEDGER / rel_ledger).relative_to(ROOT).as_posix()
    # PAR CHEMIN RELATIF à `ledger/`, jamais par `p.name` : un `sub/store.py`
    # niché ne doit pas hériter de l'exemption de l'UNIQUE `ledger/store.py`.
    est_store = rel_ledger == STORE
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            if (f.id == "getattr" and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)
                    and n.args[1].value in IO_PAR_METHODE | {"connect"}):
                # `getattr(x, "connect")(…)` contourne les deux contrôles
                # ci-dessous par le TEXTE : refusé partout, store.py compris.
                fautifs.append(rel + ":" + str(n.lineno)
                               + " → getattr(…, " + repr(n.args[1].value) + ")")
            elif f.id == "open":
                fautifs.append(rel + ":" + str(n.lineno) + " → open()")
            elif f.id == "connect" and not est_store:
                # `from sqlite3 import connect; connect(...)` — un `connect`
                # NU échappait au contrôle `.connect` (attribut) ci-dessous.
                fautifs.append(rel + ":" + str(n.lineno)
                               + " → connect() hors store.py")
        elif isinstance(f, ast.Attribute):
            producteur = (rel_ledger == PRODUCTEUR_CHARGE[0]
                          and isinstance(f.value, ast.Name)
                          and f.value.id == PRODUCTEUR_CHARGE[1])
            if f.attr == "connect" and not est_store and not producteur:
                fautifs.append(rel + ":" + str(n.lineno)
                               + " → .connect() hors store.py")
            elif f.attr in IO_PAR_METHODE:
                recepteur = f.value
                sanctionne = (isinstance(recepteur, ast.Name)
                              and recepteur.id in ateliers)
                if not sanctionne:
                    fautifs.append(rel + ":" + str(n.lineno)
                                   + " → ." + f.attr + "() hors `Workspace`")
    return fautifs


class PureteDuServiceLedgerTests(unittest.TestCase):
    def test_le_paquet_ledger_existe_et_n_est_pas_vide(self):
        """NON-VACUITÉ de la population : sans elle, le balayage ci-dessous
        passerait à blanc et certifierait une propriété qu'il ne mesure pas."""
        self.assertTrue(LEDGER.is_dir(), f"{LEDGER} absent")
        self.assertGreaterEqual(
            len(_fichiers_ledger()), 5,
            "service ledger trop maigre pour prouver quoi que ce soit",
        )

    def test_aucune_E_S_hors_Workspace_dans_le_service_ledger(self):
        fichiers = _fichiers_ledger()
        self.assertTrue(fichiers, "population VIDE — le banc passerait à blanc")
        fautifs: list[str] = []
        for p in fichiers:
            fautifs += _fautifs_purete(p.relative_to(LEDGER).as_posix(),
                                       ast.parse(p.read_text(encoding="utf-8")))
        self.assertEqual(
            fautifs, [],
            "E/S hors `Workspace` (ou `connect` hors store.py) dans le service "
            "ledger. On garde l'E/S TEXTUELLEMENT dans `ledger/`, derrière un "
            "récepteur annoté — on ne la déporte pas pour la faire passer. "
            + str(fautifs),
        )

    def test_l_exemption_connect_ne_vaut_que_pour_store_dans_stores_py(self):
        """T6 (T-00000646) — l'exemption `PRODUCTEUR_CHARGE` est bornée sur ses
        DEUX axes, joués sur des sources SYNTHÉTIQUES : le RÉCEPTEUR (`store`, et
        lui seul — ni `autre` ni l'ancien `module`) et le FICHIER (`stores.py`, et
        lui seul — le même `store.connect` dans `lessons.py` rougit). Sans ce
        témoin, un filet qui ignorerait le récepteur, ou qui garderait l'ancien
        `module`, passerait vert sur l'arbre réel."""
        def fautifs(rel_ledger: str, source: str) -> list[str]:
            return _fautifs_purete(rel_ledger, ast.parse(source))

        self.assertEqual(fautifs("stores.py", "store.connect(chemin)\n"), [],
                         "store.connect depuis stores.py est l'exemption NOMMÉE")
        for recepteur in ("autre", "module"):
            self.assertEqual(
                len(fautifs("stores.py", recepteur + ".connect(chemin)\n")), 1,
                f"{recepteur}.connect depuis stores.py doit rougir : l'exemption "
                f"ne vaut que pour le récepteur `store`")
        self.assertEqual(len(fautifs("lessons.py", "store.connect(chemin)\n")), 1,
                         "store.connect hors stores.py doit rougir : l'exemption "
                         "ne vaut que pour ce fichier")

    def test_le_jeu_local_est_le_jeu_global_plus_trois(self):
        """Le jeu LOCAL est le jeu GLOBAL ∪ {exists, is_file, stat} — un `+3`, PAS
        un `+4` : `is_dir` a REJOINT le jeu global par T-00000633, il n'est plus
        le résidu du LOT-3. La forme `+4` serait VRAIE PAR IDEMPOTENCE d'union dès
        que `is_dir` est au global, donc elle ne prouverait jamais que l'étape 6 a
        bien ajouté `is_dir` ; le `+3` ROUGIT si on l'oublie. On importe le MODULE,
        jamais la classe (sinon pytest re-collecte ses tests ici) ; le littéral
        local RESTE indépendant (une forme dérivée `LOCAL = GLOBAL | {...}` serait
        vraie par construction et injouable)."""
        import test_cadre_package

        global_set = test_cadre_package.OrchestrationPurityTests.IO_PAR_METHODE
        # (a) le `+3` doit RESTER hors du global, sinon `L == G | {+3}` est vrai
        #     par absorption meme si l'un des trois a deja migre : cette assertion
        #     rend l'hypothese EXPLICITE et rougit si elle tombe.
        self.assertTrue(
            {"exists", "is_file", "stat"}.isdisjoint(global_set),
            "un des trois residus (exists/is_file/stat) a REJOINT le jeu global : "
            "mettre a jour le `resume` du manifeste ET ce `+3`",
        )
        self.assertEqual(IO_PAR_METHODE, global_set | {"exists", "is_file", "stat"})


if __name__ == "__main__":
    unittest.main()
