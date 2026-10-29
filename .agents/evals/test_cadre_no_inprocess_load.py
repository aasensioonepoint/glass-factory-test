#!/usr/bin/env python3
"""T-00000653 — CHECK `check_no_inprocess_load` : aucun module de `src/cadre/`
ne CHARGE ni n'EXÉCUTE en processus un `.py` trouvé sous la racine adoptante.

CLAUSE. « init exécute la wheel » (docs/PROMPT-refonte-packaging-cadre.md:457-465,
décision pilote du 2026-09-17). L'interdiction porte sur DIX APPELS —
`spec_from_file_location`, `exec` (builtin, `builtins.exec` compris, aussi
derrière un `import builtins as <alias>`), `exec_module`, `load_module`,
`load_source`, `load_compiled`, `runpy.run_path`, `runpy.run_module`,
`importlib.import_module` et `pkgutil.resolve_name` (T-00000666 : ces deux-là
importent un module NOMMÉ par une chaîne, la forme d'un chargeur de greffons)
— plus tout import de `runpy` ET tout `from … import` qui IMPORTE, aliasé ou
non, l'un de ces noms. Détection par ARBRE SYNTAXIQUE, jamais par recherche textuelle : une
docstring qui NOMME l'un de ces appels ne doit pas rougir (c'est la faute que
`no_hardcoded_paths` a déjà payée).

SECONDE FAMILLE, T-00000666 : toute MUTATION de `sys.path` qui AJOUTE une racine
d'import. `sys.path.insert(0, racine)` suivi d'un `import` nu charge en
processus un module de la racine adoptante en DEUX lignes, sans aucun des dix
appels ci-dessus — le contournement nommé par le binôme de clôture de
T-00000653. Sont relevés : `sys.path.insert/append/extend` (aussi derrière un
`import sys as <alias>`), l'affectation (cibles en tuple, étoilée et annotée
comprises, et les cibles de `for`, `with … as` et de compréhension ; une
annotation SANS valeur n'affecte rien et n'est pas relevée),
l'affectation par tranche et l'affectation augmentée de `sys.path`, `from sys
import path` et `from sys import *`, et `addsitedir` (appel ou `from …
import`), qui ajoute la racine ET exécute les lignes `import` de ses `.pth`.
Le filet relève la MUTATION, jamais le couple mutation + import : l'AST ne
sait pas lier un `import` à la racine qu'une ligne précédente a ajoutée, et
tout module importe. Coût d'exemption nul : `src/cadre/` ne porte aucun site
de cette famille, ni aucun `import_module`, `resolve_name` ou `builtins`
(relevé du 2026-10-10).

DEUX BORNES, écrites ici et pas seulement au plan :
  1. L'AST NE SAIT PAS si un chemin est sous `project_root`. Ce filet interdit
     l'APPEL, jamais le chemin — et l'exécution en SOUS-PROCESSUS (subprocess,
     Executor) reste PERMISE. Le témoin E l'épingle.
  2. ÉNUMÉRATION BORNÉE, NON CLOSE. Ne sont PAS couverts :
     - première famille : `eval`, `compile`, `__import__`, `import
       importlib.util` (un `ast.Import` de MODULE, non un alias de nom nu),
       l'aliasing par RÉ-AFFECTATION (`f = exec`, `b = builtins`), le
       `getattr` dynamique (`getattr(importlib, "import_module")`), l'accès
       par indice (`__builtins__["exec"]`), `zipimport` (`zipimporter(…)`
       n'est pas relevé ; seuls ses appels homonymes d'un nom interdit le
       sont), ET `module_from_spec` (qui n'exécute rien — le témoin E le
       range parmi les permis) ;
     - seconde famille : la RÉ-AFFECTATION (`p = sys.path` puis `p.insert`,
       `s = sys`), `getattr`/`setattr(sys, "path", …)`, `sys.__dict__["path"]`
       et `vars(sys)`, l'accès par un autre module (`os.sys.path`,
       `sys.modules["sys"].path`), les méthodes spéciales appelées par leur
       nom (`sys.path.__iadd__`, `sys.path.__setitem__`), la RÉFÉRENCE sans
       appel (`f = sys.path.insert`, `map(sys.path.append, …)`),
       `site.addpackage` (qui lit un `.pth` comme `addsitedir`),
       `sys.meta_path` et `sys.path_hooks` (un chercheur d'import installé),
       les mutations qui RETIRENT (`del`, `remove`, `pop`, `clear` : aucune
       racine ajoutée), ET le `sys.path[0]` que pose l'interpréteur lui-même :
       sous `python -m`, c'est le répertoire COURANT (mesuré le 2026-10-10,
       Python 3.14 ; `-I` et `-P` le retirent) — lancé depuis la racine
       adoptante, un `import` nu s'y résout sans aucune mutation, et tout
       `import` s'y résout AVANT la bibliothèque standard, ceux de
       `src/cadre/` compris (mesuré : `argparse.py` à la racine exécuté sous
       `python -m cadre.cli`, rc 7 ; `-P` le neutralise) ; exposition
       actuelle : seuls des bancs lancent ce mode ;
     - hors du périmètre de la clause, qui vise un `.py` : `ctypes.CDLL` (code
       natif), `pickle` (dont `__reduce__` exécute pourtant du code) et
       `marshal` (un code objet ne s'exécute que par `exec`, lui relevé) ;
     - en sens inverse, SUR-DÉTECTION ASSUMÉE : hors `exec`, les noms
       interdits de la première famille et `addsitedir` sont relevés sur TOUT récepteur et tout `from <module>
       import <nom>`, aliasé ou non (`self.resolve_name`, `ws.run_path`
       rougissent) ; ne pas nommer ainsi une méthode de `src/cadre/`, ou
       l'exempter au compte.

PÉRIMÈTRE : `src/cadre/` ET LUI SEUL, comme `no_hardcoded_paths` — à son emplacement
résolu par `vendor_paths` (`.agents/vendor/cadre/` d'abord). Ce banc ne lit
NI le manifeste NI la spec — c'est ce qui le laisse VOYAGER avec `src/cadre/`
sans règle `strip:` dans `.template-exclude`. TRAP 1 assumé : un chargement
DÉPLACÉ hors du paquet lui échappe par conception ; élargir au dépôt entier
rougirait sur nos propres filets légitimes (`test_spec_clause_registry.py`
charge `plan_cible.py` par `spec_from_file_location` + `exec_module`). Côté
`stores.py`, l'hypothèse résiduelle (un chargement DÉPLACÉ au lieu d'être retiré)
est tenue par `PaquetSeulTests` de `test_cadre_ledger_stores.py` (T-00000646) :
`src/cadre/` copié SEUL, sans `agentic_v3/` ni `.agents/bin/`, crée les trois
stores.

AUCUNE EXEMPTION depuis T-00000646 (S-00001590) : `EXEMPTIONS` est vide, donc
tout appel interdit réintroduit dans `src/cadre/` rougit le témoin B.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le résolveur chargé PAR CHEMIN (patron v3prep), jamais par `sys.path` : le paquet
# vit à `.agents/vendor/cadre` ou à `src/cadre` (T-01M5BXTPQE3JZV3KZA6WD9P5XC).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_no_inprocess_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)


def _paquet(racine: Path) -> Path:
    """Le dossier de `cadre` sous `racine` (vendor d'abord), ou l'ancien lieu s'il manque."""
    return _VENDOR.dossier_paquet(racine, "cadre") or racine / "src" / "cadre"


PKG = _paquet(ROOT)


def sources() -> list[Path]:
    """Les `.py` du paquet `cadre` (`src/cadre/` ou `.agents/vendor/cadre/`), triés — ou `[]` s'il est absent.

    Recopié de SYM-7581 (`sources` de `test_cadre_package.py`) plutôt qu'importé :
    aucune collecte pytest de ce banc ne doit dépendre d'un second fichier.
    """
    return sorted(PKG.rglob("*.py")) if PKG.is_dir() else []


#: Les noms d'appel détectés indifféremment sur un `ast.Name` ou un
#: `ast.Attribute` (`importlib.util.spec_from_file_location`, `spec.loader.
#: exec_module`, les trois `Loader.load_*`, `runpy.run_path`, `runpy.run_module`,
#: et depuis T-00000666 `importlib.import_module` et `pkgutil.resolve_name`).
_NOMS_ATTR_OU_NAME = frozenset({
    "spec_from_file_location", "exec_module", "run_path", "run_module",
    "load_module", "load_source", "load_compiled",
    "import_module", "resolve_name",
})

#: Les méthodes de `sys.path` qui AJOUTENT une racine d'import (T-00000666).
_AJOUTS_SYS_PATH = frozenset({"insert", "append", "extend"})

#: Les noms qu'un `from sys import …` rend mutables sans le préfixe `sys.`.
_NOMS_SYS_PATH_IMPORTES = frozenset({"path", "*"})


def _alias_du_module(arbre: ast.AST, module: str) -> set[str]:
    """Les noms liés au MODULE `module` (`sys`, `builtins`) : son nom, plus
    chaque `import <module> as <a>`.

    Un nom lié par ré-affectation (`s = sys`, `b = builtins`) n'est pas suivi :
    borne déclarée en tête de module."""
    noms = {module}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms |= {a.asname for a in noeud.names if a.name == module and a.asname}
    return noms


def _cibles_affectees(noeud: ast.AST) -> list[ast.expr]:
    """Les cibles d'un `Assign`/`AugAssign`/`AnnAssign`, d'un `for`/`async for`,
    d'un `with … as` et d'une compréhension, tuples, listes et cibles étoilées
    dépliés (`a, sys.path = …`, `*sys.path, = …`) ; `[]` pour tout autre nœud,
    et pour une annotation SANS valeur (`sys.path: list`), qui n'affecte rien.
    `withitem` et `comprehension` n'ont pas de `lineno` : l'appelant prend
    celui de la cible."""
    if isinstance(noeud, ast.Assign):
        pile = list(noeud.targets)
    elif isinstance(noeud, (ast.AugAssign, ast.For, ast.AsyncFor,
                            ast.comprehension)) or (
            isinstance(noeud, ast.AnnAssign) and noeud.value is not None):
        pile = [noeud.target]
    elif isinstance(noeud, ast.withitem) and noeud.optional_vars is not None:
        pile = [noeud.optional_vars]
    else:
        return []
    cibles: list[ast.expr] = []
    while pile:
        cible = pile.pop()
        if isinstance(cible, (ast.Tuple, ast.List)):
            pile.extend(cible.elts)
        elif isinstance(cible, ast.Starred):
            pile.append(cible.value)
        else:
            cibles.append(cible)
    return cibles


def _fautifs_sys_path(arbre: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Les MUTATIONS de `sys.path` qui ajoutent une racine d'import (T-00000666).

    Rend des `(rel, ligne, étiquette)` comme `_fautifs`, qui les y ajoute. Le
    récepteur compte : `sys.path.insert` (ou `<alias de sys>.path.insert`) est
    fautif, `self.path.insert` ou `os.path.join` ne le sont pas. Une lecture de
    `sys.path` (`list(sys.path)`, `sys.path[0]`) n'est pas une mutation."""
    modules_sys = _alias_du_module(arbre, "sys")

    def est_sys_path(expr: ast.AST) -> bool:
        return (isinstance(expr, ast.Attribute) and expr.attr == "path"
                and isinstance(expr.value, ast.Name)
                and expr.value.id in modules_sys)

    trouves: list[tuple[str, int, str]] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            cible = noeud.func
            if isinstance(cible, ast.Attribute) and cible.attr in _AJOUTS_SYS_PATH \
                    and est_sys_path(cible.value):
                trouves.append((rel, noeud.lineno, f"sys.path.{cible.attr}"))
            elif (isinstance(cible, ast.Name) and cible.id == "addsitedir") or (
                    isinstance(cible, ast.Attribute) and cible.attr == "addsitedir"):
                trouves.append((rel, noeud.lineno, "addsitedir"))
        elif isinstance(noeud, ast.ImportFrom):
            for alias in noeud.names:
                if noeud.module == "sys" and alias.name in _NOMS_SYS_PATH_IMPORTES:
                    trouves.append((rel, noeud.lineno, f"from sys import {alias.name}"))
                elif alias.name == "addsitedir":
                    trouves.append((rel, noeud.lineno, "addsitedir"))
        for cible in _cibles_affectees(noeud):
            ligne = getattr(noeud, "lineno", cible.lineno)
            if isinstance(noeud, ast.AugAssign) and (
                    est_sys_path(cible) or (isinstance(cible, ast.Subscript)
                                            and est_sys_path(cible.value))):
                trouves.append((rel, ligne, "sys.path +="))
            elif est_sys_path(cible):
                trouves.append((rel, ligne, "sys.path ="))
            elif isinstance(cible, ast.Subscript) and est_sys_path(cible.value):
                trouves.append((rel, ligne, "sys.path[…] ="))
    return trouves


def _fautifs(arbre: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Les appels de CHARGEMENT/EXÉCUTION en processus dans un AST donné.

    Rend une liste de `(rel, ligne, nom d'appel)`. `exec` n'est fautif que comme
    BUILTIN — `ast.Name` d'id `exec`, ou attribut `exec` du module `builtins`
    (son nom, un `import builtins as <a>`, ou `__builtins__`), étiqueté
    `builtins.exec` ; un attribut homonyme d'un autre récepteur
    (`curseur.exec(...)`) n'est pas visé. Les autres appels le sont sur `Name`
    OU `Attribute`. Tout
    `import runpy` / `from runpy import …` est relevé, et tout `from … import`
    qui IMPORTE un nom interdit, aliasé ou non (`from importlib.util import
    spec_from_file_location as _s`), l'est aussi. La seconde famille, les
    mutations de `sys.path` (`_fautifs_sys_path`, T-00000666), est ajoutée ICI
    et non à côté : c'est ce qui la fait voir aux témoins B et C par
    `_constats`, sans second balayage.

    `rel` n'est qu'une ÉTIQUETTE recopiée telle quelle dans chaque tuple :
    `_constats` la jette et réinjecte la sienne. La signature est gardée parce
    que les témoins D/E la passent en argument.
    """
    modules_builtins = _alias_du_module(arbre, "builtins") | {"__builtins__"}
    trouves: list[tuple[str, int, str]] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            cible = noeud.func
            if isinstance(cible, ast.Name):
                if cible.id == "exec" or cible.id in _NOMS_ATTR_OU_NAME:
                    trouves.append((rel, noeud.lineno, cible.id))
            elif isinstance(cible, ast.Attribute):
                if cible.attr in _NOMS_ATTR_OU_NAME:
                    trouves.append((rel, noeud.lineno, cible.attr))
                elif cible.attr == "exec" and isinstance(cible.value, ast.Name) \
                        and cible.value.id in modules_builtins:
                    trouves.append((rel, noeud.lineno, "builtins.exec"))
        elif isinstance(noeud, ast.Import):
            for alias in noeud.names:
                if alias.name == "runpy" or alias.name.startswith("runpy."):
                    trouves.append((rel, noeud.lineno, "runpy"))
        elif isinstance(noeud, ast.ImportFrom):
            module = noeud.module or ""
            if module == "runpy" or module.startswith("runpy."):
                trouves.append((rel, noeud.lineno, "runpy"))
            for alias in noeud.names:
                if alias.name in _NOMS_ATTR_OU_NAME or alias.name == "exec":
                    trouves.append((rel, noeud.lineno, alias.name))
    trouves.extend(_fautifs_sys_path(arbre, rel))
    return trouves


#: Les nœuds dont la ligne est rattachée à sa fonction englobante : les appels,
#: et depuis T-00000666 les affectations (`sys.path[0:0] = …` n'a aucun appel),
#: les imports (`from sys import path` dans une fonction) et les en-têtes de
#: `for`/`with`, synchrones ou non, qui portent une cible affectée. Tous ont un
#: `lineno` ; `withitem` et `comprehension` n'en ont pas et n'y entrent pas.
_NOEUDS_RATTACHES = (ast.Call, ast.Assign, ast.AugAssign, ast.AnnAssign,
                     ast.Import, ast.ImportFrom, ast.For, ast.AsyncFor,
                     ast.With, ast.AsyncWith)


def _constats(racine: Path | None = None) -> dict[tuple[str, str, str], int]:
    """`_fautifs` appliqué à tout `.py` du paquet `cadre` de `<racine>`, agrégé au COMPTE
    par `(chemin POSIX relatif à la racine, fonction englobante, nom d'appel)`.
    Fixture des témoins B et C ; `racine` défaut = `ROOT`, résolue ICI et non à
    l'import, et le témoin H l'injecte (ARBRE-FANTÔME jamais suivi). Un
    `SyntaxError`/`UnicodeDecodeError` est reconverti en `AssertionError` qui
    NOMME le fichier — sans quoi l'échec ne citait aucun chemin (constat C4)."""
    base = ROOT if racine is None else racine.resolve()  # le résolveur rend un chemin résolu
    paquet = PKG if racine is None else _paquet(base)
    agg: dict[tuple[str, str, str], int] = {}
    for chemin in sorted(paquet.rglob("*.py")):
        rel = chemin.relative_to(base).as_posix()
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise AssertionError(f"{rel} illisible pour l'AST : {exc}") from exc
        # BORNE : cette attribution retient la fonction la plus EXTERNE
        # rencontrée par `ast.walk` (ordre BFS, donc les fonctions de plus haut
        # niveau d'abord). Elle n'est PAS garantie sur des fonctions imbriquées
        # profondes. Depuis T-00000646 aucune clé n'est exemptée : la fonction
        # englobante ne sert plus qu'à NOMMER un fautif dans le message du
        # témoin B, jamais à l'exempter.
        portee: dict[int, str] = {}
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in ast.walk(n):
                    if isinstance(d, _NOEUDS_RATTACHES) \
                            and not portee.get(getattr(d, "lineno", -1)):
                        portee[d.lineno] = n.name
        for _rel, ligne, nom in _fautifs(arbre, rel):
            cle = (rel, portee.get(ligne, "<module>"), nom)
            agg[cle] = agg.get(cle, 0) + 1
    return agg


def _violations(constats: dict[tuple[str, str, str], int]
                ) -> dict[tuple[str, str, str], int]:
    """Les clés dont le compte DÉPASSE l'exemption déclarée : le verdict du
    témoin B, extrait pour que le témoin H rejoue EXACTEMENT le même."""
    return {k: n for k, n in constats.items() if n > EXEMPTIONS.get(k, 0)}


#: AUCUNE EXEMPTION depuis T-00000646 (S-00001590). Les deux sites autrefois
#: exemptés (`_charger` de `stores.py`, relevé du 2026-09-19) ont disparu AVEC le
#: chargement depuis la racine cible, qui a été RETIRÉ et non déplacé. Le témoin C
#: (SYM-9040) est donc vide par construction ; le témoin B (SYM-9039) mord sur
#: tout appel interdit de `src/cadre/`, sans clé d'exemption possible. Une
#: exemption future se déclare ici, clé `(chemin, fonction englobante, appel)` et
#: COMPTE exact, et le témoin C la fait expirer en rougissant.
EXEMPTIONS: dict[tuple[str, str, str], int] = {}


# --- TÉMOINS -----------------------------------------------------------------

# Source SYNTHÉTIQUE du témoin D : les formes interdites de la première famille.
# Le commentaire `# unregistered on purpose:` est IMMÉDIATEMENT au-dessus de la
# ligne `exec_module` — sans lui, le filet repo-wide
# `test_modload_registration.py` (textuel, `\.exec_module\s*\(`) compterait
# CETTE ligne physique comme un `offender`. Il ne cite AUCUN `T-\d{8}`, donc
# hors de portée de `check-stale-justification.sh` par construction. La ligne
# `load_module` reste hors de ce filet, qui ne scanne QUE `\.exec_module\s*\(`.
# Les cinq lignes suivantes (T-00000666) : `builtins.exec`, le même derrière
# un `import builtins as` puis par `__builtins__`, `import_module`,
# `resolve_name`. La dernière, `import_module(nom)` appelé NU derrière
# `from importlib import *` (qui, lui, n'ajoute rien au compte), est la seule
# à exercer le bras `ast.Name` de `_NOMS_ATTR_OU_NAME` : sans elle, retirer ce
# bras laissait D vert (mutant mesuré survivant, clôture de T-00000666).
_SOURCE_TEMOIN_D = '''\
import runpy
import builtins
import builtins as _b
import importlib.util
import importlib.machinery
import pkgutil
from importlib import *


def charge(spec, module, chemin, nom):
    exec("pass")
    importlib.util.spec_from_file_location("x", "/tmp/x.py")
    # unregistered on purpose: fixture synthetique de controle (temoin D), aucun enregistrement en production
    spec.loader.exec_module(module)
    importlib.machinery.SourceFileLoader(nom, chemin).load_module()
    runpy.run_path(chemin)
    runpy.run_module(nom)
    builtins.exec("pass")
    _b.exec("pass")
    __builtins__.exec("pass")
    importlib.import_module(nom)
    pkgutil.resolve_name(nom)
    import_module(nom)
'''

#: Les étiquettes attendues du témoin D, AU COMPTE (multi-ensemble trié).
_ATTENDUS_TEMOIN_D = sorted([
    "runpy", "exec", "spec_from_file_location", "exec_module", "load_module",
    "run_path", "run_module", "builtins.exec", "builtins.exec",
    "builtins.exec", "import_module", "resolve_name", "import_module",
])

# Source SYNTHÉTIQUE du témoin E : des appels PERMIS proches des interdits —
# dont un `exec` qui n'est NI le builtin NI celui du module `builtins`.
_SOURCE_TEMOIN_E = '''\
import subprocess
import importlib.util
import sys


def permis(ws, rel, spec, nom, module, curseur):
    subprocess.run(["python", "-m", "cadre"])
    Executor(ws).run(rel)
    ws.resolve(rel)
    creee = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    curseur.exec("select 1")
    return creee
'''

# Source SYNTHÉTIQUE du témoin F : le contournement en deux lignes de
# T-00000666 (`sys.path.insert` puis `import` nu) et chaque forme de la seconde
# famille, une par ligne. Les appels `_ajoute(racine)` et `path.insert(…)`
# n'ajoutent RIEN au compte : l'alias est relevé à son `from … import`, comme
# pour la première famille. Les trois affectations `a, sys.path`, `*sys.path,`
# et `sys.path: list` (cibles en tuple, étoilée, annotée) rendent chacune UN
# `sys.path =` de plus : le compte au multi-ensemble les distingue. Clôture de
# T-00000666 : les cibles de `for`, de `with … as` et de compréhension rendent
# chacune UN `sys.path =` de plus, et `addsitedir(racine)` appelé NU derrière
# `from site import *` (qui n'ajoute rien) rend UN `addsitedir` — seul site du
# bras `ast.Name` de `addsitedir`, dont le retrait laissait F vert (mutant
# mesuré survivant).
_SOURCE_TEMOIN_F = '''\
import site
import sys
import sys as _s
from sys import path
from sys import *
from site import addsitedir as _ajoute
from site import *


def contourne(racine, ouvrir):
    sys.path.insert(0, str(racine))
    import plugin_adoptant
    sys.path.append(racine)
    sys.path.extend([racine])
    _s.path.insert(0, racine)
    sys.path = [racine, *sys.path]
    sys.path[0:0] = [racine]
    sys.path += [racine]
    site.addsitedir(racine)
    _ajoute(racine)
    a, sys.path = 1, [racine]
    *sys.path, = [racine]
    sys.path: list = [racine]
    path.insert(0, racine)
    for sys.path in [[racine]]: pass
    with ouvrir(racine) as sys.path: pass
    vus = [0 for sys.path in [[racine]]]
    addsitedir(racine)
    return plugin_adoptant, a, vus
'''

#: Les étiquettes attendues du témoin F, AU COMPTE (multi-ensemble trié).
_ATTENDUS_TEMOIN_F = sorted([
    "from sys import path", "from sys import *", "addsitedir",
    "sys.path.insert", "sys.path.append", "sys.path.extend", "sys.path.insert",
    "sys.path =", "sys.path[…] =", "sys.path +=", "addsitedir",
    "sys.path =", "sys.path =", "sys.path =",
    "sys.path =", "sys.path =", "sys.path =", "addsitedir",
])

# Source SYNTHÉTIQUE du témoin G : des usages PERMIS proches de la seconde
# famille — LIRE `sys.path`, l'ANNOTER sans valeur (aucune affectation), et
# muter un `.path` qui n'est pas celui de `sys`.
_SOURCE_TEMOIN_G = '''\
import os
import sys


def permis(self, chemins, path):
    racines = list(sys.path)
    premier = sys.path[0]
    for entree in sys.path:
        chemins.append(entree)
    sys.path: list
    os.path.join("a", "b")
    self.path.insert(0, "x")
    path.append("y")
    chemins.path = ["z"]
    chemins.path[0:0] = ["z"]
    sys.argv.append("--x")
    return racines, premier
'''

# Source SYNTHÉTIQUE du témoin H : posée comme `src/cadre/init.py` d'un
# ARBRE-FANTÔME, elle porte le contournement dans TROIS fonctions — un appel,
# une affectation par tranche, puis une affectation annotée et une augmentée,
# pour épingler le rattachement à la fonction de CHAQUE type de
# `_NOEUDS_RATTACHES`. Les lignes d'affectation ne portent AUCUN appel
# (`[racine]`, pas `[str(racine)]`) : sinon l'appel suffirait à les rattacher et
# `_NOEUDS_RATTACHES` ne serait pas exercé (mutant mesuré survivant sur
# `[str(racine)]`). Clôture de T-00000666 : trois fonctions de plus épinglent
# les imports (`from sys import path`, `import runpy`) et les en-têtes de
# `for`/`with`, synchrones puis asynchrones — eux aussi SANS appel sur la
# ligne (`with racine as …`, pas `with ouvrir(racine) as …`).
_SOURCE_TEMOIN_H = '''\
import sys


def _charger_plugin_adoptant(racine):
    sys.path.insert(0, str(racine))
    import plugin_adoptant
    return plugin_adoptant


def _etendre_par_tranche(racine):
    sys.path[0:0] = [racine]


def _etendre_par_annotation(racine):
    sys.path: list = [racine]
    sys.path += [racine]


def _etendre_par_import():
    from sys import path
    import runpy
    return path, runpy


def _etendre_par_boucle(racine):
    for sys.path in [[racine]]: pass
    with racine as sys.path: pass


async def _etendre_en_asynchrone(racine):
    async for sys.path in racine: pass
    async with racine as sys.path: pass
'''


class NoInProcessLoadTests(unittest.TestCase):
    def test_vendor_seul_wheel(self):
        """La référence des producteurs de la wheel suit le V3 résolu du kit."""
        import test_cadre_ledger_stores as banc_stores
        from agentic_v3.db import run_export

        paquet = run_export._vendor_paths().dossier_paquet(ROOT, "agentic_v3")
        self.assertIsNotNone(paquet, "paquet V3 absent : témoin non armé")
        self.assertEqual(Path(run_export.__file__).resolve().parents[1], paquet)
        attendu = (paquet / "db" / "schema.py").relative_to(ROOT)
        self.assertEqual(banc_stores._MODULE_V3, attendu)
        depot = banc_stores._batir_depot()
        self.addCleanup(shutil.rmtree, depot, ignore_errors=True)
        self.assertEqual((depot / attendu).read_bytes(), (ROOT / attendu).read_bytes())

    def test_A_paquet_present_et_non_vacue(self):
        """A — NON-VACUITÉ. `PKG.is_dir()` ET un seuil de modules : sans les
        deux, tous les balayages ci-dessous passeraient sur zéro fichier."""
        self.assertTrue(PKG.is_dir(), f"{PKG} absent — livrable de la Phase 1")
        self.assertGreaterEqual(
            len(sources()), 10,
            f"{PKG} ne porte que {len(sources())} module(s) — seuil de "
            "non-vacuité à 10, qui laisse retirer des modules sans devenir vide",
        )

    def test_B_aucun_chargement_hors_exemption(self):
        """B — aucun chargement/exécution en processus hors exemption. La
        comparaison porte sur le COMPTE ; `EXEMPTIONS` étant vide depuis
        T-00000646, le moindre appel interdit dans `src/cadre/` rougit."""
        violations = _violations(_constats())
        self.assertEqual(
            violations, {},
            "chargement/exécution en processus NON exempté dans src/cadre/ "
            f"(clé → compte) : {violations}",
        )

    def test_C_aucune_exemption_perimee(self):
        """C — aucune exemption PÉRIMÉE. Égalité STRICTE au compte : une
        exemption dont les sites ont disparu rend 0 face au compte déclaré, et
        cette assertion rougit — l'exemption EXPIRE en rougissant. VIDE PAR
        CONSTRUCTION depuis T-00000646 (plus aucune exemption) : il reste armé
        pour la prochaine qui serait déclarée."""
        constats = _constats()
        perimees = {k: (attendu, constats.get(k, 0))
                    for k, attendu in EXEMPTIONS.items()
                    if constats.get(k, 0) != attendu}
        self.assertEqual(
            perimees, {},
            "exemption périmée : ses sites ont disparu, retire ces lignes de "
            f"EXEMPTIONS (clé → (attendu, observé)) : {perimees}",
        )

    def test_D_controle_negatif_du_detecteur(self):
        """D — contrôle négatif. Les formes interdites de la première famille,
        sur une source synthétique, DOIVENT toutes être vues, AU COMPTE (le
        multi-ensemble `_ATTENDUS_TEMOIN_D`) : sans quoi le détecteur pourrait
        être inerte et B/C verts par cécité. `builtins.exec` y figure trois
        fois — par son nom, derrière un `import builtins as`, et par
        `__builtins__` — pour que perdre l'un des trois récepteurs rougisse."""
        noms = sorted(nom for _, _, nom in _fautifs(ast.parse(_SOURCE_TEMOIN_D),
                                                    "synthetique_D"))
        self.assertEqual(
            noms, _ATTENDUS_TEMOIN_D,
            "les formes interdites relevées ne sont pas celles attendues",
        )

    def test_E_le_permis_reste_permis(self):
        """E — le permis reste permis. subprocess, Executor.run, Workspace.
        resolve, `module_from_spec` et un `exec` d'un autre récepteur
        (`curseur.exec`) NE sont PAS des chargements en processus ; `_fautifs`
        doit rendre `[]`. Épingle aussi la borne `module_from_spec` (qui
        n'exécute rien), déclarée NON COUVERTE par la tête de module."""
        self.assertEqual(
            _fautifs(ast.parse(_SOURCE_TEMOIN_E), "synthetique_E"), [],
            "un appel PERMIS a été signalé comme fautif — la liste close a "
            "débordé (probablement sur module_from_spec, un `.run` ou un "
            "`.exec` hors `builtins`)",
        )

    def test_F_sys_path_puis_import_nu_est_vu(self):
        """F — contrôle négatif de la seconde famille (T-00000666). D'abord le
        contournement EXACT du titre, seul : `sys.path.insert` puis un `import`
        nu doivent rendre UN constat, à la ligne de l'insertion. Puis la
        variante sans préfixe `sys.` : `from sys import *`, `path.insert` et un
        `import` nu rendent UN constat, à la ligne de l'import étoilé. Puis
        chaque forme du multi-ensemble attendu, au COMPTE : une forme perdue, ou
        relevée deux fois, rougit."""
        deux_lignes = "import sys\nsys.path.insert(0, racine)\nimport plugin_adoptant\n"
        self.assertEqual(
            _fautifs(ast.parse(deux_lignes), "synthetique_F"),
            [("synthetique_F", 2, "sys.path.insert")],
            "le contournement en deux lignes (`sys.path.insert` + import nu) "
            "n'est pas vu — la clause se contourne de nouveau",
        )
        etoile = "from sys import *\npath.insert(0, racine)\nimport plugin_adoptant\n"
        self.assertEqual(
            _fautifs(ast.parse(etoile), "synthetique_F"),
            [("synthetique_F", 1, "from sys import *")],
            "le contournement par `from sys import *` puis `path.insert` + "
            "import nu n'est pas vu",
        )
        noms = sorted(nom for _, _, nom in _fautifs(ast.parse(_SOURCE_TEMOIN_F),
                                                    "synthetique_F"))
        self.assertEqual(
            noms, _ATTENDUS_TEMOIN_F,
            "les mutations de `sys.path` relevées ne sont pas celles attendues",
        )

    def test_G_lire_sys_path_reste_permis(self):
        """G — le permis de la seconde famille reste permis. LIRE `sys.path`
        (`list`, indice, itération) n'ajoute aucune racine, et un `.path` qui
        n'est pas celui du module `sys` (`self.path`, `os.path`, un paramètre
        nommé `path`, `chemins.path`) n'est pas `sys.path` : `_fautifs` doit
        rendre `[]`, sans quoi le filet rougirait sur du code sain."""
        self.assertEqual(
            _fautifs(ast.parse(_SOURCE_TEMOIN_G), "synthetique_G"), [],
            "un usage PERMIS a été signalé comme une mutation de `sys.path` — "
            "le contrôle du récepteur a débordé",
        )

    def test_H_le_contournement_dans_src_cadre_rougit_le_temoin_B(self):
        """H — critère d'acceptation de T-00000666 : un module de `src/cadre/`
        qui porte `sys.path.insert` + import nu REND LE BANC ROUGE. Joué sur un
        ARBRE-FANTÔME (jamais l'arbre suivi, qu'un banc interrompu laisserait
        sale) par la MÊME fixture `_constats` et le MÊME verdict `_violations`
        que le témoin B : chaque site est rattaché à SA fonction, les
        affectations par tranche, annotée et augmentée comprises, comme les
        imports et les en-têtes de `for`/`with` (synchrones ou non) — un
        `from sys import path` dans une fonction n'est pas `<module>`."""
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            paquet = racine / "src" / "cadre"
            paquet.mkdir(parents=True)
            (paquet / "__init__.py").write_text("", encoding="utf-8")
            (paquet / "init.py").write_text(_SOURCE_TEMOIN_H, encoding="utf-8")
            violations = _violations(_constats(racine))
        self.assertEqual(
            violations,
            {("src/cadre/init.py", "_charger_plugin_adoptant", "sys.path.insert"): 1,
             ("src/cadre/init.py", "_etendre_par_tranche", "sys.path[…] ="): 1,
             ("src/cadre/init.py", "_etendre_par_annotation", "sys.path ="): 1,
             ("src/cadre/init.py", "_etendre_par_annotation", "sys.path +="): 1,
             ("src/cadre/init.py", "_etendre_par_import", "from sys import path"): 1,
             ("src/cadre/init.py", "_etendre_par_import", "runpy"): 1,
             ("src/cadre/init.py", "_etendre_par_boucle", "sys.path ="): 2,
             ("src/cadre/init.py", "_etendre_en_asynchrone", "sys.path ="): 2},
            "le contournement posé dans src/cadre/ ne rougit pas le témoin B, "
            "ou n'est pas rattaché à sa fonction",
        )

    def test_vendor_seul_h(self):
        """Le paquet au SEUL emplacement vendor (arbre-fantôme) est balayé : le
        contournement du témoin H y rougit B sous son chemin vendor. MUTANT :
        `_paquet` rendu à `racine / "src" / "cadre"` → zéro fichier lu → rouge."""
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            paquet = racine / ".agents" / "vendor" / "cadre"
            paquet.mkdir(parents=True)
            (paquet / "__init__.py").write_text("", encoding="utf-8")
            (paquet / "init.py").write_text(_SOURCE_TEMOIN_H, encoding="utf-8")
            violations = _violations(_constats(racine))
        self.assertEqual(
            violations.get((".agents/vendor/cadre/init.py", "_charger_plugin_adoptant",
                            "sys.path.insert")), 1,
            f"le paquet vendor seul n'est pas balayé : {violations}",
        )
        self.assertEqual(sum(violations.values()), 10, violations)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
