#!/usr/bin/env python3
"""Témoin T-01M5BXTGX5YN8XEXTG1PP7A5ZX, phase C : LES PÉRIMÈTRES DU KIT VOIENT
`.agents/vendor/<paquet>` COMME L'ANCIEN EMPLACEMENT (`src/cadre`, `agentic_v3`).

Run: python -m pytest .agents/bin/test_vendor_scope.py -q

Union STATIQUE, jamais le résolveur `vendor_paths` : chaque site est lu par son
canal réel (fonction du module, ligne du hook jouée par git, pytest lui-même),
avec un chemin sous `.agents/vendor/cadre/…` et sous `.agents/vendor/agentic_v3/…`.

  V1 tasks_direct   chemins de garde : les deux emplacements de board_bridge et du gabarit pytest.
  V2 plan_lots      roster orphelin : un roster sous `.agents/vendor/cadre` seul est exigé ; les
                    deux rosters sur disque, seul l'ancien dans le lot : refus qui nomme le vendor.
  V3 build_index    kit : indexé comme l'ancien (le `vendor` de SKIP_DIRS ne l'élague pas) ;
                    adoptant : exclu comme l'ancien (`.agents` de KIT_CODE_DIRS). Règle « racine
                    seule » (`KIT_VENDOR`) : `src/app/vendor/v.py` reste exclu dans les trois vues.
  V4 stop-reindex   repli git chez l'adoptant : une modification sous vendor ne rend pas STALE ;
                    hook RÉEL (repli git, arbre sans builder) : dans le kit, une modification sous
                    `.agents/vendor` rend STALE, comme le builder qui l'indexe ; chez l'adoptant, non.
  V5 kit_code_guard hors de l'ensemble kit-code, comme l'ancien.
  V6 docs_only      `agentic_v3` sous vendor reste un arbre du runner ; `cadre` sous vendor
                    y ENTRE (`.agents/` est un `testpaths`), l'ancien `src/cadre` non : plus
                    large, jamais plus étroit — dit, pas égalisé.
  V7 porte_adoptant pytest ne descend ni dans `agentic_v3` ni dans `.agents/vendor/*` ; un module
                    découvert sous `.agents/vendor` est écarté. `src/cadre` (ancien) n'est PAS
                    élagué par `norecursedirs` : la copie vendor l'est, plus étroite — dit.
  V8 voyage         plan, étape 7 (`test_voyage_template`, fonctions pytest de tête : `unittest.main`
                    ne les joue pas) : sur trois arbres jetables (ancien, neuf, les deux), le VRAI
                    `.template-exclude` et `sync_template.py --apply` classent `vendor_paths.py` et les
                    cinq `test_vendor_*.py` en TAKE (new), les copient octet pour octet sur la branche
                    template, sans `.agents/IS_THE_KIT` (l'arbre de l'adoptant) ; le résolveur VOYAGÉ y
                    désigne le paquet de la disposition. Mutant permanent : une exclusion
                    `vendor_paths.py` ajoutée au `.template-exclude` jetable → rouge.

BORNES, DITES : le repli de stop-reindex DANS LE KIT exclut encore `.agents/bin` (et le reste de
`.agents` hors `.agents/vendor`) alors que le builder l'indexe — écart antérieur, non jugé ici.
V8 joue `sync_template.py` sur une branche template jetable, jamais la vraie, et ne joue pas la
porte de l'adoptant.
"""
from __future__ import annotations

import importlib.util
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_index as bi  # noqa: E402 — needs the path inserted above
import docs_only_scope as dos  # noqa: E402
import kit_code_guard as kcg  # noqa: E402
import porte_adoptant as pa  # noqa: E402

HOOK = HERE.parents[1] / ".claude" / "hooks" / "stop-reindex.sh"
VENDOR = ".agents/vendor"
# (ancien, neuf) : un fichier de code ordinaire de chaque paquet.
PAIRES = (("src/cadre/x.py", f"{VENDOR}/cadre/x.py"),
          ("agentic_v3/y.py", f"{VENDOR}/agentic_v3/y.py"))
# Des `vendor/` du PROJET, à la racine et en profondeur : élagués partout (règle « racine seule »).
VENDOR_PROJET = ("vendor/w.py", "src/app/vendor/v.py")


def _charger(nom: str, fichier: str):
    """Un module de `HERE` chargé par chemin sous un nom unique (aucun conflit de banc)."""
    spec = importlib.util.spec_from_file_location(nom, HERE / fichier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def _env_git() -> dict:
    return {k: v for k, v in os.environ.items()
            if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")}


def _git(racine: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(racine), "-c", "core.hooksPath=/dev/null",
                           "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], capture_output=True, text=True, env=_env_git(), check=False)


class _Arbre(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp(prefix="vendor-scope-")).resolve()
        self.addCleanup(shutil.rmtree, self.racine, True)

    def ecrire(self, *rels: str, texte: str = "def f(x):\n    return x\n") -> None:
        for rel in rels:
            chemin = self.racine / rel
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(texte, encoding="utf-8")


class V1TasksDirect(unittest.TestCase):
    def test_V1_garde_des_deux_emplacements(self):
        tasks = _charger("tasks_vendor_scope", "tasks.py")
        for ancien, neuf in (("agentic_v3/reconciliation/board_bridge.py",
                              f"{VENDOR}/agentic_v3/reconciliation/board_bridge.py"),
                             ("src/cadre/data/gabarits/pytest.ini.tmpl",
                              f"{VENDOR}/cadre/data/gabarits/pytest.ini.tmpl")):
            with self.subTest(neuf=neuf):
                self.assertTrue(tasks.est_chemin_de_garde(ancien), ancien)
                self.assertTrue(tasks.est_chemin_de_garde(neuf), f"{neuf} : hors liste de garde")
        for ancien, neuf in PAIRES:
            with self.subTest(neuf=neuf):
                self.assertEqual(tasks.est_chemin_de_garde(neuf), tasks.est_chemin_de_garde(ancien))


class V2PlanLots(_Arbre):
    def test_V2_roster_orphelin_aux_deux_emplacements(self):
        pl = _charger("plan_lots_vendor_scope", "plan_lots.py")
        for base in ("src/cadre", f"{VENDOR}/cadre"):
            with self.subTest(base=base):
                racine = self.racine / base.replace("/", "_")
                roster = f"{base}/data/roster/planner.json"
                (racine / roster).parent.mkdir(parents=True)
                (racine / roster).write_text("{}", encoding="utf-8")
                seul = pl.Lot("A", "dev-multi", "x", [".claude/agents/planner.md"], "")
                refus = pl._refus_rosters([seul], racine)
                self.assertEqual(len(refus), 1, refus)
                self.assertIn(roster, refus[0])
                complet = pl.Lot("A", "dev-multi", "x", [".claude/agents/planner.md", roster], "")
                self.assertEqual(pl._refus_rosters([complet], racine), [])

    def test_V2b_les_deux_rosters_seul_l_ancien_dans_le_lot(self):
        pl = _charger("plan_lots_vendor_scope_b", "plan_lots.py")
        ancien, neuf = "src/cadre/data/roster/planner.json", f"{VENDOR}/cadre/data/roster/planner.json"
        self.ecrire(ancien, neuf, texte="{}")
        lot = pl.Lot("A", "dev-multi", "x", [".claude/agents/planner.md", ancien], "")
        refus = pl._refus_rosters([lot], self.racine)
        self.assertEqual(len(refus), 1, refus)
        self.assertIn(f"`{neuf}`", refus[0], "le roster vendor, sur disque, n'est pas exigé")
        complet = pl.Lot("A", "dev-multi", "x", [".claude/agents/planner.md", ancien, neuf], "")
        self.assertEqual(pl._refus_rosters([complet], self.racine), [])


class V3BuildIndex(_Arbre):
    def _vues(self) -> dict:
        hs = bi.host_skip_dirs(self.racine)
        # `_keep` jugé sur les chemins ÉCRITS, pas sur la sortie d'un parcours : chaque site seul.
        ecrits = {p.relative_to(self.racine).as_posix() for p in self.racine.rglob("*") if p.is_file()}
        vues = {"_walk_sources": set(bi._walk_sources(self.racine, hs)),
                "_keep": {r for r in ecrits if bi._keep(r, self.racine, hs)}}
        self.assertEqual(_git(self.racine, "init", "-q").returncode, 0)
        self.assertEqual(_git(self.racine, "add", "-A").returncode, 0)
        vues["git ls-files"] = set(bi.all_source_files(self.racine, hs))
        return vues

    def test_V3a_kit_indexe_vendor_comme_l_ancien(self):
        self.ecrire(*(p for paire in PAIRES for p in paire), "src/app/z.py", *VENDOR_PROJET)
        self.ecrire(bi.KIT_MARKER.as_posix(), ".agents/protected-paths.local", texte="#\n")
        for vue, vus in self._vues().items():
            for ancien, neuf in PAIRES:
                with self.subTest(vue=vue, neuf=neuf):
                    self.assertIn(ancien, vus)
                    self.assertIn(neuf, vus, f"{vue} : {neuf} élagué dans le kit")
            for rel in VENDOR_PROJET:  # `KIT_VENDOR` est une RACINE, jamais un nom de segment
                with self.subTest(vue=vue, rel=rel):
                    self.assertIn("src/app/z.py", vus)
                    self.assertNotIn(rel, vus, f"{vue} : {rel} indexé — la règle vendor n'est plus « racine seule »")

    def test_V3b_adoptant_exclut_vendor_comme_l_ancien(self):
        self.ecrire(*(p for paire in PAIRES for p in paire), "src/app/z.py", *VENDOR_PROJET)
        self.ecrire(".agents/protected-paths.local", texte="#\n")
        for vue, vus in self._vues().items():
            with self.subTest(vue=vue):
                self.assertIn("src/app/z.py", vus)
                for rel in VENDOR_PROJET:
                    self.assertNotIn(rel, vus, f"{rel} : un `vendor/` du projet doit rester élagué")
                for ancien, neuf in PAIRES:
                    self.assertNotIn(ancien, vus)
                    self.assertNotIn(neuf, vus)


def _pathspec_du_hook() -> tuple[list[str], list[str]]:
    """(pathspec fixe de la ligne `git diff`, HOST_EXCL de l'adoptant), lus dans le hook."""
    texte = HOOK.read_text(encoding="utf-8")
    diff = [l for l in texte.splitlines() if 'diff --quiet "$built_sha" --' in l]
    excl = re.findall(r'^\s*HOST_EXCL="(:[^"]+)"', texte, re.M)
    if len(diff) != 1 or len(excl) != 1:
        raise AssertionError(f"hook ambigu : {len(diff)} lignes diff, {len(excl)} HOST_EXCL")
    fixe = shlex.split(diff[0].split(" -- ", 1)[1].split("$HOST_EXCL", 1)[0])
    return fixe, excl[0].split()


class V4StopReindex(_Arbre):
    def test_V4_adoptant_vendor_hors_domaine_comme_l_ancien(self):
        fixe, host_excl = _pathspec_du_hook()
        self.ecrire(*(p for paire in PAIRES for p in paire), "src/app/z.py")
        self.assertEqual(_git(self.racine, "init", "-q").returncode, 0)
        _git(self.racine, "add", "-A")
        self.assertEqual(_git(self.racine, "commit", "-q", "-m", "base").returncode, 0)
        base = _git(self.racine, "rev-parse", "HEAD").stdout.strip()
        temoin = None
        for rel in ("src/app/z.py", *(p for paire in PAIRES for p in paire)):
            with self.subTest(rel=rel):
                self.ecrire(rel, texte="def g(y):\n    return y\n")
                rc = _git(self.racine, "diff", "--quiet", base, "--", *fixe, *host_excl).returncode
                _git(self.racine, "checkout", "-q", "--", rel)
                if rel == "src/app/z.py":
                    temoin = rc
                    self.assertEqual(rc, 1, "contre-témoin : le code du projet doit rendre STALE")
                else:
                    self.assertEqual(rc, 0, f"{rel} : STALE chez l'adoptant, rappel inextinguible")
        self.assertEqual(temoin, 1)


class V4bStopReindexReel(_Arbre):
    """Le hook RÉEL, sur son repli git : l'arbre n'a pas de `.agents/bin/build_index.py`, donc ni sonde ni cache."""

    def _arbre(self, marqueur: str) -> None:
        self.ecrire(*(p for paire in PAIRES for p in paire), "src/app/z.py", "docs/d.md")
        self.ecrire(marqueur, texte="#\n")
        self.assertEqual(_git(self.racine, "init", "-q").returncode, 0)
        _git(self.racine, "add", "-A")
        self.assertEqual(_git(self.racine, "commit", "-q", "-m", "base").returncode, 0)
        sha = _git(self.racine, "rev-parse", "HEAD").stdout.strip()
        self.ecrire(".agents/state/index/SYMBOLS.md", texte=f"# SYMBOLS — built @ {sha}\n")
        self.assertFalse((self.racine / ".agents" / "bin" / "build_index.py").exists())

    def _stale(self) -> bool:
        etat = self.racine.parent / f"{self.racine.name}-etat"
        self.addCleanup(shutil.rmtree, etat, True)
        env = dict(_env_git(), CLAUDE_PROJECT_DIR=str(self.racine), CADRE_STATE_DIR=str(etat), HOME=str(etat))
        p = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, timeout=60, check=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return "Index is stale" in p.stdout

    def _matrice(self, attendus: dict[str, bool]) -> None:
        self.assertFalse(self._stale(), "contre-témoin : rien de modifié, rien de STALE")
        for rel, attendu in attendus.items():
            with self.subTest(rel=rel):
                self.ecrire(rel, texte="def g(y):\n    return y\n")
                stale = self._stale()
                _git(self.racine, "checkout", "-q", "--", rel)
                self.assertEqual(stale, attendu, f"{rel} : STALE={stale}, attendu {attendu}")

    def test_V4b_kit_vendor_rend_stale(self):
        self._arbre(bi.KIT_MARKER.as_posix())
        self._matrice({f"{VENDOR}/cadre/x.py": True, f"{VENDOR}/agentic_v3/y.py": True,
                       "src/cadre/x.py": True, "src/app/z.py": True, "docs/d.md": False})

    def test_V4c_adoptant_vendor_hors_domaine(self):
        self._arbre(".agents/protected-paths.local")
        self._matrice({f"{VENDOR}/cadre/x.py": False, f"{VENDOR}/agentic_v3/y.py": False,
                       "src/cadre/x.py": False, "src/app/z.py": True, "docs/d.md": False})


class V5KitCodeGuard(_Arbre):
    def test_V5_hors_ensemble_comme_l_ancien(self):
        for ancien, neuf in PAIRES:
            with self.subTest(neuf=neuf):
                self.assertFalse(kcg.in_kit_code(ancien))
                self.assertFalse(kcg.in_kit_code(neuf), f"{neuf} : dans l'ensemble kit-code")
                self.assertEqual(kcg.kit_code_reason([neuf], str(self.racine)), ("", "", ""))


class V6DocsOnly(_Arbre):
    def _lien(self, rel: str) -> None:
        (self.racine / "cible").mkdir(exist_ok=True)
        (self.racine / rel).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(self.racine / "cible", self.racine / rel)

    def test_V6_arbres_du_runner(self):
        for rel in ("agentic_v3/lien", f"{VENDOR}/agentic_v3/lien", f"{VENDOR}/cadre/lien"):
            with self.subTest(rel=rel):
                self._lien(rel)
                with self.assertRaises(dos.Abort, msg=f"{rel} : hors des arbres du runner"):
                    dos._listed_paths(str(self.racine), [rel])
        self._lien("src/cadre/lien")
        self.assertEqual(dos._listed_paths(str(self.racine), ["src/cadre/lien"]), [])


class V7PorteAdoptant(_Arbre):
    def test_V7a_pytest_ne_descend_pas_dans_vendor(self):
        ini = self.racine / "porte.ini"
        ini.write_text("[pytest]\nnorecursedirs = " + " ".join(pa.NORECURSE_DEFAUTS + pa.NORECURSE_KIT)
                       + "\n", encoding="utf-8")
        test = "def test_t():\n    assert True\n"
        self.ecrire("tests/test_projet.py", "agentic_v3/tests/test_v3.py",
                    f"{VENDOR}/agentic_v3/tests/test_v3n.py", f"{VENDOR}/cadre/tests/test_cn.py", texte=test)
        p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-c", str(ini),
                            "--rootdir", str(self.racine), "-p", "no:cacheprovider", str(self.racine)],
                           capture_output=True, text=True, cwd=self.racine, check=False)
        self.assertIn("test_projet.py", p.stdout, p.stdout + p.stderr)
        for nom in ("test_v3.py", "test_v3n.py", "test_cn.py"):
            self.assertNotIn(nom, p.stdout, f"{nom} collecté par la porte de l'adoptant")

    def test_V7b_module_sous_vendor_ecarte(self):
        for paquet in ("cadre", "agentic_v3"):
            self.ecrire(f"{VENDOR}/{paquet}/pyproject.toml", texte="[project]\nname = 'x'\n")

        class Decouverte:
            FAMILIES = {"python": ("pyproject.toml",)}

            @staticmethod
            def discover(_racine):
                return {Path(f"{VENDOR}/{p}"): {"families": {"python"}} for p in ("cadre", "agentic_v3")}

        porte = pa.Porte(self.racine, {})
        gardes, ecartes = pa.modules_gardes(porte, Decouverte)
        self.assertEqual(gardes, {})
        self.assertEqual(sorted(n for n, _ in ecartes), [f"{VENDOR}/agentic_v3", f"{VENDOR}/cadre"])


# ---------------------------------------------------------------------------
# V8 — LE VOYAGE vers la branche template (plan, étape 7). Les mécanismes de
# `test_sync_template.py` (dépôt main + template orpheline, gabarits `keep:`/`own:`,
# drapeaux d'`--apply`), chargés sous un nom propre : aucune de ses classes n'entre ici.
# ---------------------------------------------------------------------------
REPO = HERE.parents[1]
VOYAGEURS = (".agents/bin/vendor_paths.py",
             *(f".agents/bin/test_vendor_{n}.py" for n in ("bridge", "paths", "scope", "setup", "state")))
DISPOSITIONS = {"ancien": ("src/cadre", "agentic_v3"),
                "neuf": (f"{VENDOR}/cadre", f"{VENDOR}/agentic_v3"),
                "les deux": ("src/cadre", "agentic_v3", f"{VENDOR}/cadre", f"{VENDOR}/agentic_v3")}
PROVENANCE = {"ancien": "ancien", "neuf": "vendor", "les deux": "vendor"}
_SYNC: list = []


def _sync():
    if not _SYNC:
        _SYNC.append(_charger("test_sync_template_vendor_scope", "test_sync_template.py"))
    return _SYNC[0]


def _exclude_reel() -> str:
    chemin = REPO / ".template-exclude"
    if not chemin.is_file():
        import pytest
        pytest.skip(f"{chemin} absent : voyage vers la template non jugé")
    return chemin.read_text(encoding="utf-8")


def _fautes_du_voyage(base: Path, disposition: str, exclude: str) -> list[str]:
    """`sync_template.py --apply` d'un kit jetable (`disposition`, les VRAIS octets des voyageurs,
    `.agents/IS_THE_KIT`) vers une template orpheline ; rend ce que l'arbre de l'adoptant a de faux."""
    tst = _sync()
    st = tst.st
    octets = {v: (REPO / v).read_text(encoding="utf-8") for v in VOYAGEURS}
    paquets = {f"{lieu}/__init__.py": f"ORIGINE = {lieu!r}\n" for lieu in DISPOSITIONS[disposition]}
    main = {"README.md": "kit\n", bi.KIT_MARKER.as_posix(): "kit\n", **octets, **paquets,
            **tst._frozen_fixtures(st.parse_exclude(exclude))}
    tst.make_repo(base, main_files=main, template_files={"README.md": "ancienne template\n"},
                  exclude_text=exclude)
    tst._git(base, "checkout", "-q", st.TEMPLATE_REF)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = st.main(["--root", str(base), *tst._APPLY_OK])
    if code != st.EXIT_OK:
        return [f"apply rc {code} : {err.getvalue()}{out.getvalue()}"]
    take_new = out.getvalue().split("TAKE (new)", 1)[1].split("TAKE (overwrite)", 1)[0].split()
    suivis = set(tst._git(base, "ls-files").stdout.splitlines())
    fautes = [f"{v} : absent de TAKE (new)" for v in VOYAGEURS if v not in take_new]
    fautes += [f"{v} : absent de la branche template, ou octets différents" for v in VOYAGEURS
               if v not in suivis or not (base / v).is_file()
               or (base / v).read_bytes() != octets[v].encode("utf-8")]
    if bi.KIT_MARKER.as_posix() in suivis or (base / bi.KIT_MARKER).exists():
        fautes.append(f"{bi.KIT_MARKER.as_posix()} : a voyagé, l'arbre de l'adoptant se croirait le kit")
    resolveur = base / VOYAGEURS[0]
    if resolveur.is_file():  # l'adoptant : le résolveur VOYAGÉ, chargé depuis la template, désigne la disposition
        spec = importlib.util.spec_from_file_location(f"vp_voyage_{base.name}", resolveur)
        vp = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = vp  # enregistré AVANT `exec_module` (T-00000134)
        try:
            spec.loader.exec_module(vp)
        finally:  # nom propre à `base` : jamais laissé au processus pytest
            sys.modules.pop(spec.name, None)
        fautes += [f"{p} : provenance {vp.provenance(base, p)!r}, attendu {PROVENANCE[disposition]!r}"
                    for p in vp.PAQUETS if vp.provenance(base, p) != PROVENANCE[disposition]]
    return fautes


def test_voyage_template():
    exclude = _exclude_reel()
    with tempfile.TemporaryDirectory(prefix="vendor-voyage-", ignore_cleanup_errors=True) as tmp:
        for i, disposition in enumerate(DISPOSITIONS):
            base = Path(tmp).resolve() / f"kit{i}"
            base.mkdir()
            assert _fautes_du_voyage(base, disposition, exclude) == [], disposition


def test_voyage_template_rougit_sur_une_exclusion():
    """Mutant permanent : `vendor_paths.py` exclu d'un `.template-exclude` jetable → le voyage le DIT."""
    exclude = _exclude_reel() + f"\nstrip: {VOYAGEURS[0]}\n"
    with tempfile.TemporaryDirectory(prefix="vendor-voyage-mutant-", ignore_cleanup_errors=True) as tmp:
        base = Path(tmp).resolve() / "kit"
        base.mkdir()
        fautes = _fautes_du_voyage(base, "neuf", exclude)
    assert f"{VOYAGEURS[0]} : absent de TAKE (new)" in fautes, fautes
    assert f"{VOYAGEURS[0]} : absent de la branche template, ou octets différents" in fautes, fautes


if __name__ == "__main__":
    unittest.main()
