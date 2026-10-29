#!/usr/bin/env python3
"""Témoin T-00001100 : CHEZ UN ADOPTANT, LE DOMAINE DU REPLI GIT DE
`stop-reindex.sh` ÉGALE CE QUE `build_index.py` EXCLUT SOUS UN MARQUEUR.

Run: python -m pytest .agents/bin/test_stop_reindex_domaine.py -q

Le hook VOYAGE. Sans python ou sans `timeout(1)`, il juge l'index par
`git diff --quiet <sha du build> -- . <exclusions>`, et ses exclusions sont une
COPIE de la portée du builder (`HOST_EXCL`), que son propre commentaire interdit
de laisser diverger. Plus large que l'index, ce domaine répond STALE à jamais :
une modification de `src/cadre/x.py` seule, racine entrée dans `KIT_CODE_DIRS`
sans entrer dans `HOST_EXCL`, déclenchait un rappel qu'aucun rebuild n'éteint.

La référence est `host_skip_dirs()` sur une racine VENDORÉE jetable, pas les
constantes recopiées : c'est la portée effective du builder. `.agents` en est
retiré parce que la ligne `git diff` l'exclut toujours, sans `top` — ce que le
second test exige, sinon la soustraction serait une hypothèse.

Lit UN fichier connu, jamais un parcours : rien ici n'écrit le dépôt.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_index as bi  # noqa: E402 — needs the path inserted above

HOOK = HERE.parents[1] / ".claude" / "hooks" / "stop-reindex.sh"


def _vendor_paths():
    """`vendor_paths` chargé PAR CHEMIN sous un nom privé : la règle de résolution du
    paquet, jamais un chemin `src/cadre` en dur."""
    spec = importlib.util.spec_from_file_location("_stop_reindex_vendor_paths", HERE / "vendor_paths.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ligne(motif: str) -> str:
    """La SEULE ligne du hook qui porte `motif` — deux candidates seraient une
    ambiguïté à trancher, pas un choix à faire en silence."""
    lignes = [l for l in HOOK.read_text(encoding="utf-8").splitlines() if motif in l]
    if len(lignes) != 1:
        raise AssertionError(f"{len(lignes)} lignes portent {motif!r} dans {HOOK}: {lignes}")
    return lignes[0]


class StopReindexDomaineTests(unittest.TestCase):

    def test_D1_HOST_EXCL_egale_la_portee_exclue_du_builder(self):
        # tue le mutant « une racine de KIT_CODE_DIRS absente de HOST_EXCL »
        # (la BASE : `src/cadre`), et son symétrique, une exclusion de trop
        exclus = set(re.findall(r':\(exclude,top\)([^\s"]+)', _ligne('HOST_EXCL=":(exclude,top)')))
        for marqueur in bi.VENDOR_MARKERS:
            with self.subTest(marqueur=str(marqueur)), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / marqueur).parent.mkdir(parents=True)
                (Path(tmp) / marqueur).write_text("", encoding="utf-8")
                attendu = bi.host_skip_dirs(tmp) - {".agents"}
                manquants, en_trop = sorted(attendu - exclus), sorted(exclus - attendu)
                self.assertEqual((manquants, en_trop), ([], []),
                                 f"manquants {manquants}, en trop {en_trop}")

    def test_D2_la_ligne_git_diff_exclut_agents_et_porte_HOST_EXCL(self):
        # tue le mutant qui retire `':(exclude).agents'` (la soustraction de D1
        # deviendrait fausse) et celui qui calcule HOST_EXCL sans le passer
        diff = _ligne('diff --quiet "$built_sha"')
        self.assertIn("':(exclude).agents'", diff)
        self.assertIn("$HOST_EXCL", diff)

    def test_vendor_seul_r(self):
        # T-01M5BXTPQE3JZV3KZA6WD9P5XC lot R : le paquet `cadre` que `dossier_paquet` résout,
        # ancien (`src/cadre`) OU neuf (`.agents/vendor/cadre`), sort du domaine du repli git ;
        # tue le mutant qui retire `src/cadre` de HOST_EXCL et celui qui retire `.agents`
        vp = _vendor_paths()
        exclus = set(re.findall(r"':\(exclude\)([^']+)'", _ligne('diff --quiet "$built_sha"')))
        exclus |= set(re.findall(r':\(exclude,top\)([^\s"]+)', _ligne('HOST_EXCL=":(exclude,top)')))
        for lieu, provenance in (("src/cadre", "ancien"), (".agents/vendor/cadre", "vendor")):
            with self.subTest(lieu=lieu), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / lieu).mkdir(parents=True)
                (Path(tmp) / lieu / "__init__.py").write_text("", encoding="utf-8")
                self.assertEqual(vp.provenance(tmp, "cadre"), provenance)
                rel = vp.dossier_paquet(tmp, "cadre").relative_to(Path(tmp).resolve()).as_posix()
                self.assertTrue(any(rel == e or rel.startswith(e + "/") for e in exclus),
                                f"{rel} hors des exclusions {sorted(exclus)}")


if __name__ == "__main__":
    unittest.main()
