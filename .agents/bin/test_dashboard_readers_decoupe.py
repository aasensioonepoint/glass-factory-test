"""Banc de la DÉCOUPE de `dashboard_readers.py` (T-00001051) : une façade et cinq parties.

`dashboard_readers.py` est une FAÇADE : ses parties `dashboard_readers_*.py` (liste fermée `PARTIES`) sont des
modules IMPORTÉS par chemin (S-00002684, S-00003316). La façade charge chacune UNE fois, dans l'ordre de
dépendance, lui INJECTE les poignées qu'elle déclare (`nom: Any`), puis RÉ-EXPOSE chacun de ses noms de tête sous
son propre nom ; aucune partie ne charge rien. Ce banc tient ce qui rend ce geste sûr. Tous ses relevés prennent
un DOSSIER : ils se jouent sur le dépôt ET sur des copies mutantes jetables, jamais sur le dépôt, et chaque
témoin joue dans son propre cas au moins un mutant qui le rougit.

TÉMOINS PERMANENTS, joués à chaque porte :
  (a) TAILLE : la façade et chaque partie font au plus 1600 lignes (S-00002684, relevée de 800 par S-00004034).
      La « marge » compte à part : le module qui définit `_mcp_usage` tient sous une borne PASSÉE EN ARGUMENT
      (782 à l'atterrissage, mesuré au rapport de T-00001051, jamais épinglé à vie : la borne permanente reste
      BORNE).
  (b) PARTIES : `PARTIES` == les `dashboard_readers_*.py` du disque ; chacune a sa poignée `_readers_<nom>` sur
      la façade ; `_load_part` refuse un nom hors de la liste.
  (c) IDENTITÉ : tout nom DÉFINI par une partie est le MÊME objet sur la façade ; pour CHAQUE partie et CHAQUE
      poignée qu'elle déclare, la poignée reçue EST celle de la façade (une base, un M, un `_mcp_render`).
  (d) UNICITÉ : aucun nom défini dans deux fichiers (liaisons, déclarations de poignée et dunders exclus).
  (e) LOCALITÉ : le stream canal A, les deux caches, `reset_cache_for_tests` et `build_views` vivent dans la
      façade SEULE, et leurs `__globals__` SONT ceux de la façade : un patch posé sur la façade atteint leurs
      appelants. LIMITE DITE : il n'atteint PAS un nom interne à une partie (ex. `_read_waivers`) — un test qui
      veut patcher celui-là vise la poignée (`readers._readers_security`).
  (f) ZÉRO SPAWN, ZÉRO ÉCRITURE, PARMI LES IDIOMES RELEVÉS — CE N'EST PAS UNE GARANTIE GÉNÉRALE. Le relevé de
      spawns de `test_dashboard` (la fonction ELLE-MÊME, importée) rend [] sur chaque partie et 2 sur la façade ;
      le relevé d'écritures (`ecritures`) rend [] partout. Ce que ces deux relevés ne voient pas (`shutil`,
      `sqlite3`…), c'est la LISTE BLANCHE d'imports de (l) qui le ferme pour les parties ; les mutants nommés
      de ce cas disent, un par un, quel relevé les attrape.
  (g) EMPREINTE : `served_code_fingerprint` bouge quand une partie bouge.
  (h) VOYAGE : `must_travel` ⊇ les cinq parties, et chacune est SUIVIE par git.
  (j) NOMS LIBRES : tout nom global LU par un fichier y est lié, builtin, poignée déclarée ou (façade seule) lié
      par une partie ; une déclaration sans valeur qui n'est pas une poignée rougit.
  (k) LOCALISATEURS DE T-00001006 : `^def _mcp_usage\\(` et `^CANAL_A_EMITTERS([^[:alnum:]_]|$)` rendent le
      MÊME fichier, un seul. CONDITION DE RETRAIT : il tient les localisateurs d'un AUTRE plan, et se retire
      quand T-00001006 a atterri.
  (l) STDLIB SEULE, SANS CHARGEUR : la façade n'importe que la stdlib ; chaque partie n'importe que de
      `IMPORTS_DES_PARTIES` et ne lit ni `__file__`, ni `importlib`, ni `__import__`, ni `exec_module`.
  (m) ISOLATION : deux chargements de la façade ne partagent ni cache, ni partie.

SAUTS NOMMÉS, jamais silencieux : (h) et (k) sautent hors du kit (`.agents/IS_THE_KIT` absent : adoptant, copie
non commitée) ; (h) sans git lisible, (k) sans git. Un saut se lit au rapport `-rs`, et UN SAUT N'EST PAS UNE
RÉUSSITE.

TÉMOIN DE PASSE (i), classe `Passe`, joué seulement si `READERS_AB_AVANT` nomme le dossier du
`dashboard_readers.py` d'AVANT (avec `mcp_render.py` et `build_index.py`) : `ast.dump` identique nom par nom,
docstring d'avant PRÉFIXE de celle d'après, aucune ligne d'avant perdue, tout attribut d'avant présent sur la
façade, (j) propre sur l'avant. Il prouve CE passage et ne garde pas la porte. C'est l'UNIQUE témoin d'une
dérive de CORPS — son mutant `[:200]` → `[:201]` le montre : (i) seul le voit — et il SAUTE à la porte.
"""
from __future__ import annotations

import ast
import builtins
import collections
import importlib
import importlib.util
import os
import shutil
import subprocess
import symtable
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FACADE_NAME = "dashboard_readers.py"
BORNE = 1600
POIGNEES_AUTORISEES = ("_readers_", "_mcp_render")   # les seules déclarations sans valeur admises : les poignées injectées
IMPORTS_DES_PARTIES = frozenset({"__future__", "datetime", "json", "pathlib", "re", "tomllib", "typing"})


# ----------------------------------------------------------------- relevés (tous prennent un DOSSIER)
def fichiers(bin_dir: Path) -> list[Path]:
    return [bin_dir / FACADE_NAME] + sorted(bin_dir.glob("dashboard_readers_*.py"))


def poignee(nom: str) -> str:
    """`dashboard_readers_base.py` → `_readers_base` : le nom de la poignée de cette partie sur la façade."""
    return "_readers_" + nom[len("dashboard_readers_"):-len(".py")]


def lignes(path: Path) -> int:
    return path.read_text(encoding="utf-8").count("\n")          # = `wc -l`


def tailles(bin_dir: Path, borne: int = BORNE) -> list[str]:
    return [f"{p.name}: {lignes(p)} > {borne}" for p in fichiers(bin_dir) if lignes(p) > borne]


def tailles_marge(bin_dir: Path, borne: int) -> list[str]:
    """Le module qui définit `_mcp_usage` (un seul, sinon la liste le dit) face à `borne`."""
    return [f"{p.name}: {lignes(p)} > {borne}" for p in fichiers(bin_dir)
            if "_mcp_usage" in definitions(p) and lignes(p) > borne]


def _cibles(node):
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            yield from _cibles(e)


def _est_liaison(node: ast.Assign) -> bool:
    """`X = _readers_<part>.X` ou la forme tuple `(X,) = (_readers_<part>.X,)` : une LIAISON, pas une définition."""
    names = [n for t in node.targets for n in _cibles(t)]
    vals = node.value.elts if isinstance(node.value, (ast.Tuple, ast.List)) else [node.value]
    if len(names) != len(vals):
        return False
    return all(isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
               and v.value.id.startswith("_readers_") and v.attr == nm for nm, v in zip(names, vals))


def definitions(path: Path) -> dict[str, list[int]]:
    """Noms de tête DÉFINIS (def, class, affectation, annotation AVEC valeur) — hors liaisons, hors déclarations
    de poignée, hors dunders."""
    out: dict[str, list[int]] = collections.defaultdict(list)
    for n in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [n.name]
        elif isinstance(n, ast.Assign):
            names = [] if _est_liaison(n) else [x for t in n.targets for x in _cibles(t)]
        elif isinstance(n, ast.AnnAssign) and n.value is not None and isinstance(n.target, ast.Name):
            names = [n.target.id]
        else:
            continue
        for nm in names:
            if not (nm.startswith("__") and nm.endswith("__")):
                out[nm].append(n.lineno)
    return out


def doublons(bin_dir: Path) -> list[str]:
    seen: dict[str, list[str]] = collections.defaultdict(list)
    for p in fichiers(bin_dir):
        for nm, ls in definitions(p).items():
            seen[nm] += [p.name] * len(ls)
    return sorted(f"{nm}: {fs}" for nm, fs in seen.items() if len(fs) > 1)


def declarees_sans_valeur(path: Path) -> list[str]:
    return [n.target.id for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.AnnAssign) and n.value is None and isinstance(n.target, ast.Name)]


def declarations_hors_poignee(path: Path) -> list[str]:
    return [nm for nm in declarees_sans_valeur(path) if not nm.startswith(POIGNEES_AUTORISEES)]


def _tete_liee(path: Path) -> set[str]:
    """Tout nom lié en tête : def, class, affectation (liaisons comprises), import, déclaration de poignée."""
    out: set[str] = set()
    for n in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {x for t in n.targets for x in _cibles(t)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split(".")[0] for a in n.names}
    return out


def noms_libres(path: Path, fournis: frozenset[str] = frozenset()) -> list[str]:
    """Noms GLOBAUX LUS (en tête, dans une fonction, un lambda, une compréhension) ni liés dans le fichier, ni
    builtins, ni `fournis`. C'est CE relevé qui dérive les liaisons des parties au lieu de les recopier."""
    src = path.read_text(encoding="utf-8")
    lus: set[str] = set()

    def walk(tbl, en_tete: bool) -> None:
        for s in tbl.get_symbols():
            if en_tete:
                if s.is_referenced() and not (s.is_assigned() or s.is_imported() or s.is_namespace()
                                              or s.is_annotated()):
                    lus.add(s.get_name())
            elif s.is_referenced() and s.is_global():
                lus.add(s.get_name())
        for c in tbl.get_children():
            walk(c, False)

    walk(symtable.symtable(src, str(path), "exec"), True)
    implicites = {n for n in lus if n.startswith("__") and n.endswith("__")} | {"annotations"}
    return sorted(lus - _tete_liee(path) - set(dir(builtins)) - set(fournis) - implicites)


def fournis_par_les_parties(bin_dir: Path) -> frozenset[str]:
    return frozenset().union(*[_tete_liee(p) for p in fichiers(bin_dir)[1:]])


def localiser(racine: Path, motif: str) -> list[str]:
    """`git grep --no-index -l -E`, sous `LC_ALL=C` : la forme EXACTE des localisateurs de T-00001006."""
    p = subprocess.run(["git", "grep", "--no-index", "-l", "-E", motif, "--", ".agents/bin/*.py"],
                       cwd=racine, capture_output=True, text=True, timeout=60, env={**os.environ, "LC_ALL": "C"})
    return sorted(p.stdout.split())


def charger(bin_dir: Path, nom: str):
    spec = importlib.util.spec_from_file_location(nom, bin_dir / FACADE_NAME)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(nom, None)
    return mod


def copie(dst: Path) -> Path:
    b = dst / ".agents" / "bin"
    b.mkdir(parents=True)
    for p in HERE.glob("dashboard_readers*.py"):
        shutil.copy2(p, b / p.name)
    for nom in ("mcp_render.py", "build_index.py"):
        shutil.copy2(HERE / nom, b / nom)
    return b


def poignees_fautives(facade, bin_dir: Path) -> list[str]:
    """(c) Pour CHAQUE partie et CHAQUE poignée qu'elle déclare : présente sur le module chargé, et le MÊME objet
    que la poignée de la façade. Rend `<partie>:<poignée> (absente)` ou `(autre objet)`."""
    out = []
    for nom in facade.PARTIES:
        part = getattr(facade, poignee(nom))
        for h in declarees_sans_valeur(bin_dir / nom):
            if not hasattr(part, h):
                out.append(f"{nom}:{h} (absente)")
            elif getattr(part, h) is not getattr(facade, h, None):
                out.append(f"{nom}:{h} (autre objet)")
    return out


def spawns_du_filet():
    """La fonction `_spawns_de_dashboard_readers` ELLE-MÊME, importée de `test_dashboard` (même précédent que le
    banc de T-00001006) : ni copie, ni `exec`. Elle ne lit un fichier que sans `source` : on la nourrit toujours."""
    return importlib.import_module("test_dashboard")._spawns_de_dashboard_readers


_MODES_ECRITURE = set("wax+")
_METHODES_ECRITURE = {"write_text", "write_bytes", "mkdir", "unlink", "touch", "rmdir", "makedirs", "rmtree",
                      "symlink_to", "truncate", "rename", "chmod", "hardlink_to"}


def _mode_ecrit(mode) -> bool:
    """Un mode qui n'est pas une chaîne LITTÉRALE sans w/a/x/+ compte comme une écriture : on ne devine pas."""
    return mode is not None and not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
                                     and not (_MODES_ECRITURE & set(mode.value)))


def ecritures(source: str) -> list[tuple[str, int]]:
    """Les écritures de fichier PARMI LES IDIOMES RELEVÉS ICI — ce n'est pas une garantie générale. `replace` ne
    compte qu'à UN argument (`Path.replace(cible)`) ou sur `os` : `str.replace(a, b)` n'écrit rien."""
    out = []
    for n in ast.walk(ast.parse(source)):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == "open":
            mode = n.args[1] if len(n.args) > 1 else next((k.value for k in n.keywords if k.arg == "mode"), None)
            if _mode_ecrit(mode):
                out.append(("open", n.lineno))
        elif isinstance(f, ast.Attribute) and f.attr in _METHODES_ECRITURE:
            out.append((f.attr, n.lineno))
        elif isinstance(f, ast.Attribute) and f.attr == "replace" and (
                len(n.args) + len(n.keywords) == 1 or (isinstance(f.value, ast.Name) and f.value.id == "os")):
            out.append(("replace", n.lineno))
        elif isinstance(f, ast.Attribute) and f.attr == "open":
            mode = n.args[0] if n.args else next((k.value for k in n.keywords if k.arg == "mode"), None)
            if _mode_ecrit(mode):
                out.append((".open", n.lineno))
    return out


def _modules_importes(path: Path) -> list[str]:
    """Le module de TÊTE de chaque import (`import a.b` → `a`) ; un import relatif rend `.`, `..`… tel quel."""
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out += [a.name.split(".")[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            out.append((n.module or "").split(".")[0] if n.level == 0 else "." * n.level + (n.module or ""))
    return out


def imports_hors_stdlib(path: Path) -> list[str]:
    return [m for m in _modules_importes(path) if m not in sys.stdlib_module_names]


def imports_hors_liste_blanche(path: Path) -> list[str]:
    return [m for m in _modules_importes(path) if m not in IMPORTS_DES_PARTIES]


def chargeurs(path: Path) -> list[str]:
    """Ce qu'une PARTIE ne doit pas faire : lire `__file__`, appeler `__import__`, importer `importlib`, appeler
    `exec_module` / `spec_from_file_location`."""
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Name) and n.id in ("__file__", "__import__"):
            out.append(f"{n.id}:{n.lineno}")
        elif isinstance(n, ast.Import) and any(a.name.split(".")[0] == "importlib" for a in n.names):
            out.append(f"import importlib:{n.lineno}")
        elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "importlib":
            out.append(f"from importlib:{n.lineno}")
        elif isinstance(n, ast.Attribute) and n.attr in ("exec_module", "spec_from_file_location"):
            out.append(f"{n.attr}:{n.lineno}")
    return out


def must_travel(test_hygiene: Path) -> list[str]:
    tree = ast.parse(test_hygiene.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "test_the_dashboard_artefacts_do_travel")
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "must_travel" for t in n.targets):
            return list(ast.literal_eval(n.value))
    raise AssertionError("must_travel introuvable")


def non_suivis(racine: Path, chemins: list[str]) -> list[str] | None:
    """Chemins ABSENTS de `git ls-files` (l'index compte : un `git add` suffit) ; `None` si `racine` n'est pas un
    dépôt git lisible. Sans cela `must_travel` SAUTE en silence un fichier non suivi (`if rel not in self.tracked`)."""
    try:
        p = subprocess.run(["git", "ls-files", "--", *chemins], cwd=racine, capture_output=True, text=True,
                           timeout=30, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return sorted(set(chemins) - set(p.stdout.split()))


def est_le_kit() -> bool:
    return (ROOT / ".agents" / "IS_THE_KIT").is_file()


def charger_dashboard(nom: str):
    spec = importlib.util.spec_from_file_location(nom, HERE / "dashboard.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(nom, None)
    return mod


def empreinte_sourde(d, tmp: Path, parties_disque: list[str]) -> list[str]:
    """Parties dont un changement de mtime NE FAIT PAS bouger `served_code_fingerprint` (HERE patché sur `tmp`)."""
    for nom in parties_disque:
        shutil.copy2(HERE / nom, tmp / nom)
    vieux, d.HERE = d.HERE, tmp
    try:
        sourdes = []
        for nom in parties_disque:
            avant = d.served_code_fingerprint()
            st = (tmp / nom).stat()
            os.utime(tmp / nom, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
            apres = d.served_code_fingerprint()
            os.utime(tmp / nom, ns=(st.st_atime_ns, st.st_mtime_ns))
            if avant == apres:
                sourdes.append(nom)
        return sourdes
    finally:
        d.HERE = vieux


def _garder_les_parties_enregistrees(case: unittest.TestCase) -> None:
    """Un mutant de chargeur laisse ses `_readers_part_*` dans `sys.modules` : on les rend tels quels à la fin."""
    garde = {k: v for k, v in sys.modules.items() if k.startswith("_readers_part_")}

    def rendre():
        for k in [k for k in sys.modules if k.startswith("_readers_part_")]:
            del sys.modules[k]
        sys.modules.update(garde)

    case.addCleanup(rendre)


class Permanents(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t1051-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.parties = sorted(p.name for p in HERE.glob("dashboard_readers_*.py"))

    # (a)
    def test_a_taille(self):
        self.assertEqual([], tailles(HERE))
        b = copie(self.tmp)
        mut = b / "dashboard_readers_memory.py"
        # Le mutant se cale sur BORNE, jamais sur un pas fixe : un ajout fixe resterait sous une borne relevée.
        mut.write_text(mut.read_text(encoding="utf-8") + "# x\n" * (BORNE - lignes(mut)), encoding="utf-8")
        self.assertEqual(BORNE, lignes(mut))
        self.assertEqual([], tailles(b), "un fichier à la borne exacte reste vert")
        mut.write_text(mut.read_text(encoding="utf-8") + "# x\n", encoding="utf-8")
        self.assertEqual(BORNE + 1, lignes(mut))
        self.assertEqual(["dashboard_readers_memory.py"], [x.split(":")[0] for x in tailles(b)], "témoin (a) sourd")
        self.assertEqual([], tailles(b, 10_000))

    # (a), la marge de T-00001006, comptée à part
    def test_a_marge(self):
        self.assertEqual([], tailles_marge(HERE, BORNE))
        b = copie(self.tmp)
        m = b / "dashboard_readers_coverage_mcp.py"
        # Cible relative à la taille courante, jamais un pas fixe ni un plancher : un module qui grossit
        # légitimement ne rend pas le témoin rouge à tort. La borne EXACTE est éprouvée (mutant `>=` tué).
        cible = lignes(m) + 1
        m.write_text(m.read_text(encoding="utf-8") + "# x\n" * (cible - lignes(m)), encoding="utf-8")
        self.assertEqual(cible, lignes(m))
        self.assertEqual([], tailles_marge(b, cible), "un module à la borne exacte reste vert")
        self.assertTrue(tailles_marge(b, cible - 1), f"mutant à {cible} lignes sourd sous {cible - 1}")
        self.assertEqual([], tailles_marge(b, max(BORNE, cible)))

    # (b)
    def test_b_parties(self):
        f = charger(HERE, "_t1051_facade_b")
        self.assertEqual(sorted(f.PARTIES), self.parties)
        for nom in f.PARTIES:
            self.assertEqual(Path(getattr(f, poignee(nom)).__file__).name, nom)
        with self.assertRaises(ValueError):
            f._load_part("dashboard_readers_orpheline.py")
        b = copie(self.tmp)
        (b / "dashboard_readers_orpheline.py").write_text("x = 1\n", encoding="utf-8")
        disque = sorted(p.name for p in b.glob("dashboard_readers_*.py"))
        self.assertEqual(["dashboard_readers_orpheline.py"],
                         sorted(set(disque) - set(charger(b, "_t1051_facade_b2").PARTIES)))

    # (c)
    def test_c_identite(self):
        f = charger(HERE, "_t1051_facade_c")
        for nom in f.PARTIES:
            h = getattr(f, poignee(nom))
            for d in definitions(HERE / nom):
                self.assertIs(getattr(f, d), getattr(h, d), (nom, d))
        self.assertEqual([], poignees_fautives(f, HERE))
        m = f._readers_coverage_mcp
        self.assertIs(f._mcp_usage, m._mcp_usage)
        self.assertIs(f.CANAL_A_EMITTERS, m.CANAL_A_EMITTERS)
        self.assertIs(f._readers_governance.CANAL_A_EMITTERS, m.CANAL_A_EMITTERS)
        # mutant : `_mcp_render=` retiré de l'injection → poignée déclarée ABSENTE
        b = copie(self.tmp / "sans_rendu")
        t = (b / FACADE_NAME).read_text(encoding="utf-8")
        self.assertEqual(1, t.count("_readers_base=_readers_base, _mcp_render=_mcp_render"))
        (b / FACADE_NAME).write_text(t.replace("_readers_base=_readers_base, _mcp_render=_mcp_render",
                                               "_readers_base=_readers_base"), encoding="utf-8")
        self.assertEqual(["dashboard_readers_coverage_mcp.py:_mcp_render (absente)"],
                         poignees_fautives(charger(b, "_t1051_mut_rendu"), b))
        # mutants : une AUTRE base injectée, partie par partie — (c) nomme CELLE-LÀ, et elle seule
        for p in ("governance", "security", "memory"):
            b = copie(self.tmp / ("base_" + p))
            t = (b / FACADE_NAME).read_text(encoding="utf-8")
            i = t.index(f"_readers_{p} = _load_part(")
            j = t.index("_readers_base=_readers_base", i)
            t = t[:j] + '_readers_base=_load_part("dashboard_readers_base.py")' + t[j + len("_readers_base=_readers_base"):]
            (b / FACADE_NAME).write_text(t, encoding="utf-8")
            self.assertEqual([f"dashboard_readers_{p}.py:_readers_base (autre objet)"],
                             poignees_fautives(charger(b, "_t1051_mut_base_" + p), b), p)

    # (d)
    def test_d_doublons(self):
        self.assertEqual([], doublons(HERE))
        b = copie(self.tmp)
        g = b / "dashboard_readers_governance.py"
        g.write_text(g.read_text(encoding="utf-8") + "\n\ndef _clip(value, cap):\n    return value\n", encoding="utf-8")
        self.assertEqual(["_clip"], [x.split(":")[0] for x in doublons(b)])

    # (e)
    def test_e_localite(self):
        f = charger(HERE, "_t1051_facade_e")
        locaux = ("build_views", "read_canal_a_stream", "_read_canal_a_stream_uncached", "reset_cache_for_tests",
                  "_stream_cache", "_views_cache")
        for nom in locaux:
            for p in fichiers(HERE):
                self.assertEqual(p.name == FACADE_NAME, nom in definitions(p), (nom, p.name))
        self.assertIs(f.build_views.__globals__, vars(f))
        self.assertIs(f.read_canal_a_stream.__globals__, vars(f))
        b = copie(self.tmp)
        m = b / "dashboard_readers_memory.py"
        m.write_text(m.read_text(encoding="utf-8") + "\n\ndef build_views(*a, **k):\n    return {}\n", encoding="utf-8")
        self.assertEqual(["build_views"], [x.split(":")[0] for x in doublons(b)])

    # (f)
    def test_f_zero_spawn_zero_ecriture_parmi_les_idiomes_releves(self):
        relever = spawns_du_filet()
        for nom in self.parties:
            src = (HERE / nom).read_text(encoding="utf-8")
            self.assertEqual([], relever(source=src), nom)
            self.assertEqual([], ecritures(src), nom)
        facade = (HERE / FACADE_NAME).read_text(encoding="utf-8")
        self.assertEqual(2, len(relever(source=facade)))
        self.assertEqual([], ecritures(facade))
        # les relevés eux-mêmes peuvent rougir, et ne rougissent pas sur une lecture
        self.assertTrue(relever(source="import subprocess\nsubprocess.run(['git'])\n"))
        self.assertTrue(ecritures("from pathlib import Path\nPath('x').write_text('')\n"))
        self.assertTrue(ecritures("open('x', 'w')\n"))
        self.assertEqual([], ecritures("open('x', 'rb')\nopen('x')\n'a'.replace('a', 'b')\n"))
        # MUTANTS NOMMÉS, greffés en FIN d'une copie de partie : chacun rougit AU MOINS là où il est attendu, et la
        # sortie dit QUI l'attrape. `shutil` et `sqlite3` échappent aux deux relevés d'idiomes : la liste blanche
        # de (l) les ferme — c'est pour cela qu'elle existe.
        mutants = {
            "import os + os.replace": ("import os\nos.replace('a', 'b')\n", {"ecritures", "liste_blanche"}),
            "import subprocess as sp + sp.run": ("import subprocess as sp\nsp.run(['git'])\n",
                                                 {"spawns", "liste_blanche"}),
            "import shutil + copyfile": ("import shutil\nshutil.copyfile('a', 'b')\n", {"liste_blanche"}),
            "import sqlite3 + connect": ("import sqlite3\nsqlite3.connect('x.db')\n", {"liste_blanche"}),
        }
        b = copie(self.tmp)
        cible = b / "dashboard_readers_memory.py"
        t = cible.read_text(encoding="utf-8")
        for nom, (greffe, attendus) in mutants.items():
            cible.write_text(t + "\n" + greffe, encoding="utf-8")
            src = cible.read_text(encoding="utf-8")
            vus = {k for k, v in (("spawns", relever(source=src)), ("ecritures", ecritures(src)),
                                  ("liste_blanche", imports_hors_liste_blanche(cible))) if v}
            print(f"(f) mutant « {nom} » : attrapé par {sorted(vus)}")
            self.assertLessEqual(attendus, vus, nom)

    # (g)
    def test_g_empreinte(self):
        d = charger_dashboard("_t1051_dashboard")
        self.assertEqual(sorted(d._readers_mod.PARTIES), self.parties)
        self.assertEqual([], empreinte_sourde(d, self.tmp, self.parties))
        vieux = d._readers_mod.PARTIES
        d._readers_mod.PARTIES = tuple(x for x in vieux if x != "dashboard_readers_memory.py")
        try:
            self.assertEqual(["dashboard_readers_memory.py"], empreinte_sourde(d, self.tmp, self.parties))
        finally:
            d._readers_mod.PARTIES = vieux

    # (h)
    def test_h_voyage(self):
        if not est_le_kit():
            self.skipTest("SKIP (h) : `.agents/IS_THE_KIT` absent (adoptant, copie non commitée) — "
                          "le voyage des parties n'est PAS mesuré")
        liste = must_travel(HERE.parent / "evals" / "test_template_hygiene.py")
        voulu = {".agents/bin/" + n for n in self.parties}
        self.assertEqual(set(), voulu - set(liste))
        ampute = [x for x in liste if x != ".agents/bin/dashboard_readers_memory.py"]
        self.assertEqual({".agents/bin/dashboard_readers_memory.py"}, voulu - set(ampute))
        suivis = non_suivis(ROOT, sorted(voulu))
        if suivis is None:
            self.skipTest("SKIP (h) : git illisible ici — l'état « suivi » des parties n'est PAS mesuré")
        self.assertEqual([], suivis, "partie non suivie : `git add <chemin>` — `must_travel` la sauterait en silence")
        self.assertEqual([".agents/bin/dashboard_readers_inexistante.py"],
                         non_suivis(ROOT, [".agents/bin/dashboard_readers_inexistante.py"]))

    # (j)
    def test_j_noms_libres(self):
        self.assertEqual([], noms_libres(HERE / FACADE_NAME, fournis_par_les_parties(HERE)), "façade")
        for n in self.parties:
            self.assertEqual([], noms_libres(HERE / n), n)
            self.assertEqual([], declarations_hors_poignee(HERE / n), n)
        # mutant T_mut1 : deux liaisons retirées → exactement ces deux noms
        b = copie(self.tmp / "t_mut1")
        for n, retire in (("dashboard_readers_memory.py", "_CLIP_MARKER = _readers_base._CLIP_MARKER\n"),
                          ("dashboard_readers_security.py", "_SAMPLE_LIMIT = _readers_base._SAMPLE_LIMIT\n")):
            t = (b / n).read_text(encoding="utf-8")
            self.assertEqual(1, t.count(retire), n)
            (b / n).write_text(t.replace(retire, ""), encoding="utf-8")
            self.assertEqual([retire.split(" =")[0]], noms_libres(b / n), n)
        # mutant de la FAÇADE : un nom que `build_views` lit n'est plus défini nulle part
        b = copie(self.tmp / "renomme")
        mem = b / "dashboard_readers_memory.py"
        t = mem.read_text(encoding="utf-8")
        self.assertEqual(1, t.count("def build_memory("))
        mem.write_text(t.replace("def build_memory(", "def build_memoire("), encoding="utf-8")
        self.assertEqual(["build_memory"], noms_libres(b / FACADE_NAME, fournis_par_les_parties(b)))
        # une déclaration sans valeur qui n'est PAS une poignée injectée masquerait un nom libre
        mem.write_text("_CLIP_MARKER: str\n" + t, encoding="utf-8")
        self.assertEqual(["_CLIP_MARKER"], declarations_hors_poignee(mem))

    # (k) — se retire quand T-00001006 a atterri
    def test_k_localisateurs_de_t1006(self):
        if not est_le_kit():
            self.skipTest("SKIP (k) : `.agents/IS_THE_KIT` absent (adoptant, copie non commitée) — "
                          "les localisateurs de T-00001006 ne sont PAS mesurés")
        try:
            en_depot = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True,
                                      timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            en_depot = False
        if not en_depot:
            self.skipTest("SKIP (k) : git absent ou arbre non git — les localisateurs de T-00001006 ne sont PAS mesurés")
        mcp = localiser(ROOT, r"^def _mcp_usage\(")
        emi = localiser(ROOT, r"^CANAL_A_EMITTERS([^[:alnum:]_]|$)")
        self.assertEqual([".agents/bin/dashboard_readers_coverage_mcp.py"], mcp)
        self.assertEqual(mcp, emi)
        # mutant : un second fichier qui OUVRE une ligne `CANAL_A_EMITTERS` → deux fichiers
        b = copie(self.tmp)
        g = b / "dashboard_readers_governance.py"
        t = g.read_text(encoding="utf-8")
        self.assertEqual(1, t.count("(CANAL_A_EMITTERS,) = ("))
        g.write_text(t.replace("(CANAL_A_EMITTERS,) = (", "CANAL_A_EMITTERS = ("), encoding="utf-8")
        self.assertEqual(2, len(localiser(self.tmp, r"^CANAL_A_EMITTERS([^[:alnum:]_]|$)")))

    # (l)
    def test_l_stdlib_seule_sans_chargeur(self):
        self.assertEqual([], imports_hors_stdlib(HERE / FACADE_NAME))
        for nom in self.parties:
            self.assertEqual([], imports_hors_liste_blanche(HERE / nom), nom)
            self.assertEqual([], chargeurs(HERE / nom), nom)
        b = copie(self.tmp)
        m = b / "dashboard_readers_memory.py"
        t = m.read_text(encoding="utf-8")
        m.write_text("import requests\n" + t, encoding="utf-8")
        self.assertEqual(["requests"], imports_hors_stdlib(m))
        self.assertEqual(["requests"], imports_hors_liste_blanche(m))
        m.write_text(t + "\nimport os\n", encoding="utf-8")
        self.assertEqual([], imports_hors_stdlib(m))
        self.assertEqual(["os"], imports_hors_liste_blanche(m))
        m.write_text("from pathlib import Path\nHERE = Path(__file__).resolve().parent\n", encoding="utf-8")
        self.assertEqual(["__file__:2"], chargeurs(m))
        m.write_text("import importlib.util\n", encoding="utf-8")
        self.assertEqual(["import importlib:1"], chargeurs(m))
        m.write_text("mod = __import__('os')\n", encoding="utf-8")
        self.assertEqual(["__import__:1"], chargeurs(m))

    # (m)
    def test_m_isolation(self):
        _garder_les_parties_enregistrees(self)
        a, b = charger(HERE, "_t1051_iso_a"), charger(HERE, "_t1051_iso_b")
        self.assertIsNot(a._views_cache, b._views_cache)
        self.assertIsNot(a._stream_cache, b._stream_cache)
        for nom in a.PARTIES:
            self.assertIsNot(getattr(a, poignee(nom)), getattr(b, poignee(nom)), nom)
        a._views_cache["fingerprint"] = "x"
        b.reset_cache_for_tests()
        self.assertEqual("x", a._views_cache["fingerprint"])
        # mutant : `_load_part` court-circuité par `sys.modules` (« mis en cache ») → les deux chargements
        # PARTAGENT leurs parties ((m) rouge), et (c) rougit aussi : la partie M d'un AUTRE chargement porte un
        # AUTRE `_mcp_render` que celui de la façade qui la reçoit.
        bm = copie(self.tmp)
        t = (bm / FACADE_NAME).read_text(encoding="utf-8")
        ancre = '    spec = importlib.util.spec_from_file_location("_readers_part_" + filename['
        self.assertEqual(1, t.count(ancre))
        cache = ('    if "_readers_part_" + filename[len("dashboard_readers_"):-3] in sys.modules:\n'
                 '        return sys.modules["_readers_part_" + filename[len("dashboard_readers_"):-3]]\n')
        (bm / FACADE_NAME).write_text(t.replace(ancre, cache + ancre), encoding="utf-8")
        ma, mb = charger(bm, "_t1051_iso_ma"), charger(bm, "_t1051_iso_mb")
        partagees = sorted(nom for nom in ma.PARTIES if getattr(ma, poignee(nom)) is getattr(mb, poignee(nom)))
        self.assertEqual(sorted(ma.PARTIES), partagees, "(m) sourd au chargeur mis en cache")
        self.assertIn("dashboard_readers_coverage_mcp.py:_mcp_render (autre objet)", poignees_fautives(mb, bm),
                      "(c) sourd au chargeur mis en cache")


def passe(avant_dir: Path, bin_dir: Path) -> dict:
    """(i) parties 1 et 3 : `ast.dump` nom par nom (liaisons exclues côté après) et multiset des lignes."""
    def tete(path: Path) -> dict[str, str]:
        out = {}
        for n in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[n.name] = ast.dump(n)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    for nm in _cibles(t):
                        out[nm] = ast.dump(n)
            elif isinstance(n, ast.AnnAssign) and n.value is not None and isinstance(n.target, ast.Name):
                out[n.target.id] = ast.dump(n)
        return out

    avant = avant_dir / FACADE_NAME
    apres: dict[str, str] = {}
    for p in fichiers(bin_dir):
        defs = definitions(p)
        apres.update({nm: d for nm, d in tete(p).items() if nm in defs})
    ref = tete(avant)
    nouv = collections.Counter(l for p in fichiers(bin_dir) for l in p.read_text(encoding="utf-8").splitlines())
    vieux = collections.Counter(avant.read_text(encoding="utf-8").splitlines())
    return {"noms": len(ref), "changes": sorted(nm for nm in ref if nm in apres and ref[nm] != apres[nm]),
            "absents": sorted(nm for nm in ref if nm not in apres), "lignes": sum(vieux.values()),
            "perdues": sorted((vieux - nouv).elements())}


class Passe(unittest.TestCase):
    """(i) TÉMOIN DE PASSE — joué seulement si READERS_AB_AVANT nomme le dossier du `dashboard_readers.py` d'AVANT
    (avec `mcp_render.py` et `build_index.py`). Il prouve CE passage et ne garde pas la porte. UN (i) SAUTÉ N'EST
    PAS UNE RÉUSSITE."""

    def setUp(self):
        avant = os.environ.get("READERS_AB_AVANT")
        if not avant:
            self.skipTest("SKIP (i) : READERS_AB_AVANT non posé — le passage n'est PAS mesuré")
        self.avant = Path(avant)
        self.tmp = Path(tempfile.mkdtemp(prefix="t1051-i-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_i_passe(self):
        avant = self.avant / FACADE_NAME
        r = passe(self.avant, HERE)
        print(f"(i) noms de tête d'avant : {r['noms']} ; changés : {r['changes']} ; absents après : {r['absents']}")
        print(f"(i) lignes d'avant : {r['lignes']} ; perdues : {len(r['perdues'])}")
        self.assertEqual(([], [], []), (r["changes"], r["absents"], r["perdues"]))
        d_avant = ast.get_docstring(ast.parse(avant.read_text(encoding="utf-8")), clean=False)
        d_apres = ast.get_docstring(ast.parse((HERE / FACADE_NAME).read_text(encoding="utf-8")), clean=False)
        self.assertTrue(d_apres.startswith(d_avant), "la docstring d'avant n'est plus un PRÉFIXE")
        m_avant = charger(self.avant, "_t1051_avant")
        f = charger(HERE, "_t1051_apres")
        manquants = sorted(n for n in vars(m_avant) if not (n.startswith("__") and n.endswith("__"))
                           and not hasattr(f, n))
        print(f"(i) attributs d'avant : {len(vars(m_avant))} ; absents de la façade : {manquants}")
        self.assertEqual([], manquants)
        self.assertEqual([], noms_libres(avant))
        # MUTANT (i) : une dérive de CORPS (`[:200]` → `[:201]` dans `_read_waivers`), sur une COPIE. (i) la nomme ;
        # la sortie montre ce que les permanents en disent — c'est l'objet de « (i) est l'unique témoin ».
        b = copie(self.tmp)
        s = b / "dashboard_readers_security.py"
        t = s.read_text(encoding="utf-8")
        j = t.index("{str(exc)[:200]}", t.index("def _read_waivers("))
        s.write_text(t[:j] + "{str(exc)[:201]}" + t[j + len("{str(exc)[:200]}"):], encoding="utf-8")
        rm = passe(self.avant, b)
        permanents = {"(a)": tailles(b), "(d)": doublons(b),
                      "(j)": [x for p in fichiers(b)[1:] for x in noms_libres(p) + declarations_hors_poignee(p)]
                      + noms_libres(b / FACADE_NAME, fournis_par_les_parties(b))}
        print(f"(i) mutant [:200]→[:201] : (i) voit {rm['changes']} ({len(rm['perdues'])} ligne perdue) ; "
              f"permanents statiques sur la copie : {permanents}")
        self.assertEqual(["_read_waivers"], rm["changes"])
        self.assertEqual(1, len(rm["perdues"]))


if __name__ == "__main__":
    unittest.main()
