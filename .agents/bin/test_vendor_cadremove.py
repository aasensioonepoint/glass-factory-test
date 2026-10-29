"""test_vendor_cadremove.py — témoin de T-01M5BXTRP8GKS7DMDQCTKK88DZ (vendor 5/5).

Le paquet `cadre` vit sous `.agents/vendor/cadre` (plus sous `src/cadre`). Ce banc
tient ce que le déplacement change, chacun avec le mutant qui le fait rougir :

  W1  `test_racine_du_kit_deux_dispositions` : `racine_du_kit` remonte de trois
      crans sous `.agents/vendor/cadre`, de deux sous `src/cadre`, et rend la
      racine de CE kit. Mutant `return pkg_root().parent.parent` → `.agents`, rouge.
  W2  `test_cadre_etranger_ne_gagne_pas` : un `cadre` d'un AUTRE arbre, déjà
      importé, ne gagne ni `record_id._ids`, ni `event_store._cadre_module`, ni
      `migrate_index_to_db._cadre_paths` / `_cadre_module`, ni `events._redaction`,
      ni `run_export._cadre`, ni le `_redaction` du store V3 (S-01M5CN1KM2). Le faux
      `paths.py` porte `index_db` : seule la provenance le refuse. Mutant :
      `verifier_charge` retiré (`_cadre_d_ici` rend toujours vrai), ou `import_module`
      d'abord → le faux gagne.
  W2b `test_cadre_du_kit_deja_charge_une_seule_copie` : le `cadre` du kit DÉJÀ chargé,
      `run_export._cadre("ledger.ids")` rend le module de `sys.modules` (branche 1),
      jamais une seconde copie par chemin. Mutant : `_cadre_d_ici` sans
      `verifier_charge` (faux dès qu'un paquet existe) → copie par chemin, rouge.
  W3  `test_stale_index_voit_le_vendor` : `newest_source_mtime` des deux hooks
      (.codex, .gemini) voit un fichier posé sous `.agents/vendor` seul, et ignore un
      `__pycache__` plus récent. Mutants : `.agents/vendor` retiré de `WATCH_DIRS`
      → 0.0 ; `__pycache__` retiré des exclus → le `.pyc` gagne, rouge.
  W4  `test_point_d_entree_sous_le_vendor` : `build_index._entry_points` retient
      `.agents/vendor/cadre/cli.py` (profondeur comptée sous le vendor). Mutant :
      `len(p.parts) <= 3` → absent, rouge.
  W9  `test_frag_ne_nomme_aucun_arbre_absent` : chaque racine `<dir>/**` de la
      clause RESTORE BEFORE RE-ROUTE (FRAG du banc et trois défs d'orchestrateur)
      existe dans l'arbre. Mutant : FRAG d'avant → `['agentic_v3', 'src/cadre']`.
  W11 `test_mint_repli_si_le_paquet_ne_s_importe_pas` : kit jetable dont
      `cadre/ledger/__init__.py` lève `ModuleNotFoundError` ; `mint` rend quand même
      un `T-…` par le repli PAR CHEMIN (2). Mutant `except ProvenanceRefusee` au
      lieu d'`except ImportError` → `ModuleNotFoundError`, rouge.
  F1  `test_setup_sans_resolveur_refuse_rc2_sans_trace` : `setup_projet.py` sur un
      arbre sans `vendor_paths.py` → rc 2 `setup: REFUS`, aucune trace. Mutant :
      `_charger` hors du `try` de `main` → rc 1 et un Traceback.
  C19 `test_chaque_paquet_de_la_roue_est_dans_le_sdist` : `packages` de la roue ⊆
      `include` du sdist, et chacun porte `__init__.py`. Mutant : `include` sur
      `src/cadre` → rouge (les bancs de roue restent verts sous ce mutant).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


VP = _charger("vendor_paths_banc_cadremove", HERE / "vendor_paths.py")
CADRE = VP.exiger(ROOT, "cadre").resolve()


def _env(base: Path) -> dict[str, str]:
    """Sans `PYTHON*` ni `PYTEST*` ; état et spool jetables sous `base`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST"))}
    env.update(PYTHONDONTWRITEBYTECODE="1", CADRE_STATE_DIR=str(base / "state"),
               AGENTS_EVENTS_DIR=str(base / "events"), CADRE_PROJECT_ROOT=str(base / "racine"))
    env.pop("CLAUDE_PROJECT_DIR", None)
    return env


class RacineDuKitTests(unittest.TestCase):
    """W1."""

    def test_racine_du_kit_deux_dispositions(self) -> None:
        VP.charger_paquet(ROOT, "cadre")
        import cadre.commandes_adoptant as ca  # noqa: PLC0415 — chargé par `charger_paquet` ci-dessus

        kit = Path("/kit")
        self.assertEqual(ca.racine_du_kit(kit / ".agents" / "vendor" / "cadre"), kit)
        self.assertEqual(ca.racine_du_kit(kit / "src" / "cadre"), kit)
        self.assertEqual(ca.racine_du_kit(kit / "vendor" / "cadre"), kit, "`vendor` hors `.agents` : deux crans")
        self.assertEqual(ca.racine_du_kit().resolve(), ROOT, "la racine de CE kit, depuis son paquet")


# Un `cadre` d'un AUTRE arbre (argv[1]) est importé AVANT les six coutures ; chacune
# doit rendre la copie du kit (argv[2]), jamais le faux.
_SONDE_W2 = r'''
import importlib.util, json, sys
from pathlib import Path
faux, bin_ = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, faux)
import cadre, cadre.ledger.store, cadre.ledger.ids, cadre.ledger.redaction, cadre.paths, cadre.workspace
sys.path.remove(faux)
sys.path.insert(0, str(bin_.parent / "vendor"))
from agentic_v3.db import run_export
from agentic_v3.db import event_store as v3_store
def charger(nom, fichier):
    s = importlib.util.spec_from_file_location(nom, bin_ / fichier)
    m = sys.modules[s.name] = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m
rid = charger("_w2_record_id", "record_id.py")
es = charger("_w2_event_store", "event_store.py")
mig = charger("_w2_migrate", "migrate_index_to_db.py")
ev = charger("_w2_events", "events.py")
print(json.dumps({"faux": cadre.__file__,
                  "record_id": rid._ids().__file__,
                  "event_store": es._cadre_module("ledger.store").__file__,
                  "migrate_paths": mig._cadre_paths().__file__,
                  "migrate_module": mig._cadre_module("workspace").__file__,
                  "events_redaction": ev._redaction().__file__,
                  "run_export": run_export._cadre("ledger.ids").__file__,
                  "v3_store_redaction": v3_store._redaction().__file__}))
'''


class CadreEtrangerTests(unittest.TestCase):
    """W2."""

    def test_cadre_etranger_ne_gagne_pas(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadremove_w2_") as tmp:
            base = Path(tmp).resolve()
            faux = base / "faux" / "cadre"
            (faux / "ledger").mkdir(parents=True)
            for rel in ("__init__.py", "ledger/__init__.py", "ledger/store.py", "ledger/ids.py",
                        "ledger/redaction.py", "workspace.py"):
                (faux / rel).write_text("ORIGINE = 'faux'\n", encoding="utf-8")
            # `index_db` : le faux a la FORME attendue, seule la provenance le refuse (survivant W2).
            (faux / "paths.py").write_text("ORIGINE = 'faux'\ndef index_db(*a, **k):\n    return None\n",
                                           encoding="utf-8")
            p = subprocess.run([sys.executable, "-I", "-c", _SONDE_W2, str(faux.parent), str(HERE)],
                               capture_output=True, text=True, timeout=120, env=_env(base), cwd=str(base))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            rapport = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertTrue(Path(rapport.pop("faux")).resolve().is_relative_to(faux.resolve()),
                            "banc non armé : le faux `cadre` n'est pas chargé")
            for couture, fichier in rapport.items():
                with self.subTest(couture=couture):
                    self.assertTrue(Path(fichier).resolve().is_relative_to(CADRE),
                                    f"{couture} : {fichier} n'est pas sous {CADRE}")


# Le `cadre` du KIT (argv[1] = son dossier parent) est importé AVANT `run_export` : la
# branche (1) doit rendre CE module, jamais une seconde copie chargée par chemin.
_SONDE_W2B = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import cadre.ledger.ids as ids
sys.path.insert(0, sys.argv[2])
from agentic_v3.db import run_export
rendu = run_export._cadre("ledger.ids")
print(json.dumps({"meme": rendu is ids, "nom": rendu.__name__, "fichier": rendu.__file__}))
'''


class CadreDuKitChargeTests(unittest.TestCase):
    """W2b."""

    def test_cadre_du_kit_deja_charge_une_seule_copie(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadremove_w2b_") as tmp:
            base = Path(tmp).resolve()
            p = subprocess.run([sys.executable, "-I", "-c", _SONDE_W2B, str(CADRE.parent), str(ROOT / ".agents" / "vendor")],
                               capture_output=True, text=True, timeout=120, env=_env(base), cwd=str(base))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            rapport = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertTrue(Path(rapport["fichier"]).resolve().is_relative_to(CADRE), rapport)
            self.assertEqual(rapport["nom"], "cadre.ledger.ids", rapport)
            self.assertTrue(rapport["meme"], f"seconde copie de ledger.ids : {rapport}")


_SONDE_W3 = r'''
import importlib.util, sys
from pathlib import Path
hooks, racine = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(hooks))
s = importlib.util.spec_from_file_location("_w3_stale_index", hooks / "stale_index.py")
m = sys.modules[s.name] = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
m.ROOT = racine
print(m.newest_source_mtime())
'''


class StaleIndexTests(unittest.TestCase):
    """W3."""

    def test_stale_index_voit_le_vendor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadremove_w3_") as tmp:
            base = Path(tmp).resolve()
            racine = base / "racine"
            fichier = racine / ".agents" / "vendor" / "cadre" / "x.py"
            fichier.parent.mkdir(parents=True)
            fichier.write_text("X = 1\n", encoding="utf-8")
            os.utime(fichier, (1_700_000_000, 1_700_000_000))
            pyc = fichier.parent / "__pycache__" / "x.cpython-311.pyc"  # plus récent : ignoré
            pyc.parent.mkdir()
            pyc.write_bytes(b"\0")
            os.utime(pyc, (1_800_000_000, 1_800_000_000))
            for hote in (".codex", ".gemini"):
                with self.subTest(hote=hote):
                    p = subprocess.run([sys.executable, "-I", "-c", _SONDE_W3, str(ROOT / hote / "hooks"), str(racine)],
                                       capture_output=True, text=True, timeout=60, env=_env(base), cwd=str(ROOT))
                    self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                    self.assertEqual(float(p.stdout.strip().splitlines()[-1]), 1_700_000_000.0,
                                     f"{hote} : un fichier sous .agents/vendor n'est pas vu, ou un __pycache__ l'est")


class PointDEntreeTests(unittest.TestCase):
    """W4."""

    def test_point_d_entree_sous_le_vendor(self) -> None:
        bi = _charger("build_index_banc_cadremove", HERE / "build_index.py")
        fichiers = [".agents/vendor/cadre/cli.py", ".agents/vendor/cadre/ledger/x/main.py", "src/a/b/main.py"]
        self.assertEqual(bi._entry_points(fichiers), [".agents/vendor/cadre/cli.py"])


#: Les sites de la clause RESTORE BEFORE RE-ROUTE : le FRAG du banc et ses trois copies d'hôte.
_SITES_FRAG = (".agents/evals/test_docs_only_route_contract.py", ".claude/agents/orchestrator.md",
               ".gemini/agents/orchestrator.md", ".kimi-code/agents/orchestrator.md")
_RACINE_GLOB = re.compile(r"(?<![\w./-])([\w.][\w./-]*)/\*\*")
_SPAN = re.compile(r"on THIS repository that is (.*?) — an adopter's instance", re.S)


def racines_absentes(texte: str, racine: Path) -> list[str]:
    """Les racines `<dir>/**` du span « on THIS repository that is … » absentes de `racine`."""
    trouve = _SPAN.search(texte.replace('"\n    "', ""))
    if trouve is None:
        raise AssertionError("span RESTORE BEFORE RE-ROUTE introuvable : le témoin serait creux")
    return sorted({r for r in _RACINE_GLOB.findall(trouve.group(1)) if not (racine / r).exists()})


class FragTests(unittest.TestCase):
    """W9."""

    def test_frag_ne_nomme_aucun_arbre_absent(self) -> None:
        for rel in _SITES_FRAG:
            with self.subTest(site=rel):
                self.assertEqual(racines_absentes((ROOT / rel).read_text(encoding="utf-8"), ROOT), [])

    def test_le_temoin_mord_sur_le_frag_d_avant(self) -> None:
        avant = ("on THIS repository that is .agents/**, .codex/**, agentic_v3/**,\"\n    \" core-scripts/**, "
                 "src/cadre/** — an adopter's instance")
        self.assertEqual(racines_absentes(avant, ROOT), ["agentic_v3", "src/cadre"])


class MintReplieTests(unittest.TestCase):
    """W11."""

    def test_mint_repli_si_le_paquet_ne_s_importe_pas(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadremove_w11_") as tmp:
            base = Path(tmp).resolve()
            kit = base / "kit"
            (kit / ".agents" / "bin").mkdir(parents=True)
            for nom in ("record_id.py", "vendor_paths.py"):
                shutil.copy2(HERE / nom, kit / ".agents" / "bin" / nom)
            paquet = kit / ".agents" / "vendor" / "cadre"
            (paquet / "ledger").mkdir(parents=True)
            for rel in ("__init__.py", "ledger/ids.py"):  # le paquet minimal : `cadre/__init__` et le générateur
                shutil.copy2(CADRE / rel, paquet / rel)
            (paquet / "ledger" / "__init__.py").write_text("import _module_absent_zz\n", encoding="utf-8")
            code = ("import importlib.util, sys\n"
                    "s = importlib.util.spec_from_file_location('_w11_record_id', sys.argv[1])\n"
                    "m = sys.modules[s.name] = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
                    "print(m.mint('T')); print(m._ids().__file__)\n")
            p = subprocess.run([sys.executable, "-I", "-c", code, str(kit / ".agents" / "bin" / "record_id.py")],
                               capture_output=True, text=True, timeout=60, env=_env(base), cwd=str(base))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            ident, fichier = p.stdout.strip().splitlines()[-2:]
            self.assertRegex(ident, r"\AT-[0-9A-HJKMNP-TV-Z]{26}\Z")
            self.assertEqual(Path(fichier).resolve(), (paquet / "ledger" / "ids.py").resolve())


class SetupSansResolveurTests(unittest.TestCase):
    """F1 : `setup_projet.py` sur un arbre qui porte `cadre` mais pas `vendor_paths.py` refuse
    AVANT toute jambe, rc 2 nommé, jamais une trace. Mutant : `_charger` sorti du `try` → rc 1."""

    def test_setup_sans_resolveur_refuse_rc2_sans_trace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadremove_f1_") as tmp:
            base = Path(tmp).resolve()
            racine = base / "projet"
            (racine / ".agents" / "bin").mkdir(parents=True)
            shutil.copy2(HERE / "setup_projet.py", racine / ".agents" / "bin" / "setup_projet.py")
            (racine / ".agents" / "vendor" / "cadre").mkdir(parents=True)
            shutil.copy2(CADRE / "__init__.py", racine / ".agents" / "vendor" / "cadre" / "__init__.py")
            subprocess.run(["git", "-C", str(racine), "init", "-q"], check=True, capture_output=True, timeout=60)
            env = _env(base)
            env.pop("CADRE_PROJECT_ROOT")
            p = subprocess.run([sys.executable, str(racine / ".agents" / "bin" / "setup_projet.py"), "--root",
                                str(racine), "--dry-run"], capture_output=True, text=True, timeout=120, env=env,
                               cwd=str(base))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("setup: REFUS", p.stderr)
            self.assertIn("vendor_paths.py absent", p.stderr)
            self.assertNotIn("Traceback", p.stderr)


class SdistTests(unittest.TestCase):
    """C19."""

    def test_chaque_paquet_de_la_roue_est_dans_le_sdist(self) -> None:
        projet = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        cibles = projet["tool"]["hatch"]["build"]["targets"]
        paquets = cibles["wheel"]["packages"]
        self.assertTrue(paquets, "aucun paquet de roue : le témoin serait creux")
        self.assertEqual(set(paquets) - set(cibles["sdist"]["include"]), set(),
                         "un paquet de la roue manque au sdist : une roue bâtie depuis lui serait vide")
        for paquet in paquets:
            with self.subTest(paquet=paquet):
                self.assertTrue((ROOT / paquet / "__init__.py").is_file(), paquet)
        self.assertIn(".agents/vendor/cadre", paquets)


if __name__ == "__main__":
    unittest.main()
