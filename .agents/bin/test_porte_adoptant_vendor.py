"""Témoins et mutants VENDOR de la porte de l'ADOPTANT — T-01M5PHAWDMW783NHQ2YJH2BYAN.

POURQUOI : semgrep ignore `vendor/` sous `-- .` (son `.semgrepignore` par
défaut, mesuré sur semgrep 1.175.0) ; la porte passe donc les fichiers SUIVIS
sous `.agents/vendor/` en cibles explicites (`tests/` compris), et une
énumération git en échec est COVERAGE DEGRADED, rouge sauf
CADRE_GARDES_DEGRADEES — semgrep tourne ENCORE sur `-- .` seul (réserve K1).

POURQUOI UN FRÈRE : le banc principal tient sous la borne de 1600 lignes ; on
n'en importe que `_Banc` (0 test) et le module (`banc.…`) — toute sous-classe
de TestCase importée par son nom serait recollectée.

CHAQUE TÉMOIN JOUE SON MUTANT : la source d'abord, puis la copie mutée
(`banc.MutantsDurablesTests.muter`), chargée en mémoire quand le témoin
appelle `jouer_semgrep` directement.

SAUT ANNONCÉ (réserve K4) : W3-W5 jouent le semgrep RÉEL, en local seulement ;
semgrep absent du PATH (job CI `tests`) ou CI posée, ils sautent EN LE DISANT.
W1, W2, W6, W7 et W8 sont bouchonnés et tournent partout.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import test_porte_adoptant as banc
from test_porte_adoptant import _Banc

A = ".agents/vendor/agentic_v3/a.py"
B = ".agents/vendor/agentic_v3/tests/b.py"
C = ".agents/vendor/agentic_v3/c.py"
LIEN = ".agents/vendor/agentic_v3/lien.py"
REGLES = ".agents/security/semgrep.yml"
NON_ENUMERES = "COVERAGE DEGRADED — semgrep : fichiers suivis sous .agents/vendor/ non énumérés (racine)"
ENCORE = "semgrep tourne encore sur `-- .` seul"
TROUVAILLE = "semgrep : TROUVAILLE sur racine (rc 1)"
SANS_REEL = banc.SEMGREP_REEL is None or bool(os.environ.get("CI"))
SAUT = ("SAUT ANNONCÉ : semgrep réel absent du PATH ou CI posée (local seul, réserve K4) — "
        "W3-W5 non rejoués ; W1, W2, W6-W8 (bouchonnés) tournent")
# Ancres des mutants (une occurrence chacune dans porte_adoptant.py, vérifié par `muter`).
CIBLES = '"--", "."] + cibles,'
M_VENDOR_CIBLE = (CIBLES, '"--", "."] + [],')
M_SANS_POINT = (CIBLES, '"--"] + cibles,')
M_SEGMENTS = ("if rel and not (dossier / rel).is_symlink()",
              'if rel and "tests" not in rel.split("/") and not (dossier / rel).is_symlink()')
M_IS_FILE = ("and (dossier / rel).is_file())", "and True)")
M_LIEN = ("not (dossier / rel).is_symlink()", "True")
M_GIT_MUET = ('if not porte.deroger("CADRE_GARDES_DEGRADEES", alerte):', "if False:")
M_RETOUR = ("        cibles = []\n", "        return\n")
M_RACINE = ("cibles_vendor(dossier)\n", "cibles_vendor(porte.racine)\n")
SOUS = ".agents/vendor/agentic_v3/s.py"


def queue(argv: list[str]) -> list[str]:
    """Les cibles de semgrep : ce qui suit le dernier `--`."""
    return argv[len(argv) - argv[::-1].index("--"):]


class _BancVendor(_Banc):
    """Outillage commun (0 test)."""

    muter = banc.MutantsDurablesTests.muter

    def charger_mutant(self, chemin: Path):
        spec = importlib.util.spec_from_file_location("porte_adoptant_vendor_mutant", str(chemin))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def mutant(self, ancres: tuple[str, str]) -> Path:
        return self.muter(*ancres)

    def arbre(self, fichiers: dict, regle: str | None = None) -> Path:
        """Un adoptant NEUF (module npm à la racine) ; journal vidé."""
        arbre = self.tmp / "adoptant"
        if arbre.exists():
            shutil.rmtree(arbre)
        self.journal.unlink(missing_ok=True)
        self.bouchon("npm")
        base = dict(banc.MODULE_NPM) | fichiers
        if regle is not None:
            base[REGLES] = regle
        return self.adoptant(base)

    def commit(self, arbre: Path, fichiers: dict) -> None:
        self.ecrire(arbre, fichiers)
        self.git(arbre, "add", "-A")
        self.git(arbre, "commit", "-q", "-m", "suite")

    def cibles_porte(self, arbre: Path, porte: Path = banc.PORTE) -> tuple[list[str], str]:
        """La porte ENTIÈRE, semgrep bouchonné : les cibles de son appel."""
        self.journal.unlink(missing_ok=True)
        rc, sortie, _res = self.lancer(arbre, porte=porte)
        self.assertEqual(rc, 0, sortie)
        return queue(self.appels("semgrep")[0]["argv"]), sortie


# =============================================================================
class ArgvVendorTests(_BancVendor):
    """W1, W2, W7 : l'argv bouchonné de la porte entière."""

    def test_W1_vendor_en_cibles_tests_compris(self):
        """MUTANTS M-VENDOR-CIBLE, M-SEGMENTS, M-SANS-POINT (rejoués ici)."""
        arbre = self.arbre({A: "x = 1\n", B: "y = 2\n", "top.py": "z = 3\n"})
        cibles, sortie = self.cibles_porte(arbre)
        self.assertEqual(cibles, [".", A, B], sortie)
        self.assertIn("semgrep : 2 fichier(s) suivi(s) sous .agents/vendor/ en cible explicite "
                      "(racine)", sortie)
        for ancres, attendu in ((M_VENDOR_CIBLE, ["."]), (M_SEGMENTS, [".", A]), (M_SANS_POINT, [A, B])):
            with self.subTest(mutant=ancres[1]):
                cibles, sortie = self.cibles_porte(arbre, self.mutant(ancres))
                self.assertEqual(cibles, attendu, sortie)

    def test_W2_fichier_suivi_supprime_hors_cible(self):
        """MUTANT M-IS-FILE (rejoué) : semgrep rendrait rc 2 sur la cible absente (M5)."""
        arbre = self.arbre({A: "x = 1\n", B: "y = 2\n"})
        (arbre / B).unlink()
        cibles, sortie = self.cibles_porte(arbre)
        self.assertEqual(cibles, [".", A], sortie)
        cibles, sortie = self.cibles_porte(arbre, self.mutant(M_IS_FILE))
        self.assertEqual(cibles, [".", A, B], sortie)

    def test_W7_lien_symbolique_suivi_hors_cible(self):
        """MUTANT M-LIEN (rejoué). Semgrep sur une cible lien : non mesuré, exclu."""
        arbre = self.arbre({A: "x = 1\n"})
        try:
            os.symlink("a.py", arbre / LIEN)
        except OSError as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique impossible ici ({exc})")
        self.git(arbre, "add", "--", LIEN)
        self.git(arbre, "commit", "-q", "-m", "lien")
        cibles, sortie = self.cibles_porte(arbre)
        self.assertEqual(cibles, [".", A], sortie)
        cibles, sortie = self.cibles_porte(arbre, self.mutant(M_LIEN))
        self.assertEqual(cibles, [".", A, LIEN], sortie)

    def test_W8_sous_module_peuple_ses_propres_cibles(self):
        """MUTANT M-RACINE (rejoué) : un sous-module peuplé passe SES fichiers
        vendor, jamais ceux de la racine (racine et dossier diffèrent)."""
        arbre = self.arbre({A: "x = 1\n"})
        self.sous_module(arbre, "m1", {SOUS: "y = 2\n"})
        for porte, attendu in ((banc.PORTE, [".", SOUS]), (self.mutant(M_RACINE), [".", A])):
            with self.subTest(porte=porte.name):
                self.journal.unlink(missing_ok=True)
                _rc, sortie, _res = self.lancer(arbre, porte=porte)
                appels = [queue(a["argv"]) for a in self.appels("semgrep")]
                self.assertEqual(appels, [[".", A], attendu], sortie)


# =============================================================================
class GitMuetTests(_BancVendor):
    """W6 : énumération git en échec — rouge nommé sauf dérogation, et semgrep
    tourne ENCORE sur `-- .` seul (réserve K1)."""

    def jouer(self, module, raisons: dict, retour) -> tuple:
        arbre = self.arbre({A: "x = 1\n"})
        porte = module.Porte(arbre, raisons)
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, self.env(), clear=True), \
                mock.patch.object(module, "git", return_value=retour), \
                contextlib.redirect_stdout(sortie):
            module.jouer_semgrep(porte, ["semgrep", "--error"], arbre, "racine")
        return porte, [a["argv"] for a in self.appels("semgrep")], sortie.getvalue()

    def test_W6_non_enumeres_rouge_puis_deroge(self):
        """MUTANTS M-GIT-MUET (le refus tu) et M-RETOUR (semgrep sauté) ; rejoués."""
        echec = subprocess.CompletedProcess([], 128, "", "fatal")
        for retour in (None, echec):
            with self.subTest(retour=retour):
                porte, appels, sortie = self.jouer(banc.porte_adoptant, {}, retour)
                self.assertEqual(len(porte.refus), 1, sortie)
                self.assertTrue(porte.refus[0].startswith(NON_ENUMERES), porte.refus)
                self.assertIn(ENCORE, porte.refus[0])
                self.assertEqual([a[-2:] for a in appels], [["--", "."]], sortie)
                porte, appels, sortie = self.jouer(
                    banc.porte_adoptant, {"CADRE_GARDES_DEGRADEES": "banc git muet"}, retour)
                self.assertEqual(porte.refus, [], sortie)
                self.assertEqual(porte.appliquees, {"derogation_gardes": "banc git muet"})
                self.assertIn(NON_ENUMERES + " — dérogé par CADRE_GARDES_DEGRADEES", sortie)
                self.assertEqual([a[-2:] for a in appels], [["--", "."]], sortie)
        muet = self.charger_mutant(self.mutant(M_GIT_MUET))
        porte, appels, sortie = self.jouer(muet, {}, None)
        self.assertEqual(porte.refus, [], "M-GIT-MUET devait taire le refus : " + sortie)
        retour = self.charger_mutant(self.mutant(M_RETOUR))
        porte, appels, sortie = self.jouer(retour, {"CADRE_GARDES_DEGRADEES": "banc"}, None)
        self.assertEqual(appels, [], "M-RETOUR devait sauter semgrep : " + sortie)


# =============================================================================
@unittest.skipIf(SANS_REEL, SAUT)
class SemgrepReelTests(_BancVendor):
    """W3-W5 : semgrep RÉEL, `jouer_semgrep` appelé directement, règle
    `banc.REGLE_EVAL` (jamais le semgrep.yml du kit)."""

    def refus(self, module, arbre: Path, base: str | None = None, rapports: list | None = None) -> list[str]:
        """`rapports`, s'il est donné, reçoit les `results` du rapport JSON de semgrep."""
        porte = module.Porte(arbre, {})
        lire = module.lecture_entiere

        def espion(porte_, rapport: Path, ou: str) -> None:
            if rapports is not None:
                rapports.extend(json.loads(rapport.read_text(encoding="utf-8"))["results"])
            lire(porte_, rapport, ou)
        argv = ["semgrep", "--config", str(arbre / REGLES), "--error", "--metrics=off",
                "--disable-version-check", "--quiet"]
        if base is not None:
            argv += ["--baseline-commit", base]
        with mock.patch.dict(os.environ, {"SEMGREP_ENABLE_VERSION_CHECK": "0",
                                          "SEMGREP_SEND_METRICS": "off"}), \
                mock.patch.object(module, "lecture_entiere", espion):
            module.jouer_semgrep(porte, argv, arbre, "racine")
        return [r.split(" — ", 1)[0] for r in porte.refus]

    def test_W3_vendor_sans_semgrepignore(self):
        """MUTANT M-VENDOR-CIBLE (rejoué) : `-- .` seul ne voit pas vendor (M1)."""
        arbre = self.arbre({A: 'eval("2")\n', B: 'eval("3")\n'}, banc.REGLE_EVAL)
        self.assertIn(TROUVAILLE, self.refus(banc.porte_adoptant, arbre))
        mutant = self.charger_mutant(self.mutant(M_VENDOR_CIBLE))
        self.assertEqual(self.refus(mutant, arbre), [])

    def test_W4_vendor_neuf_sous_base(self):
        """MUTANT M-VENDOR-CIBLE (rejoué) : sous `--baseline-commit`, le vendor
        NEUF bloque (M6)."""
        arbre = self.arbre({A: 'eval("2")\n'}, banc.REGLE_EVAL)
        base = self.git(arbre, "rev-parse", "HEAD").strip()
        self.commit(arbre, {C: 'eval("5")\n'})
        self.assertIn(TROUVAILLE, self.refus(banc.porte_adoptant, arbre, base))
        mutant = self.charger_mutant(self.mutant(M_VENDOR_CIBLE))
        self.assertEqual(self.refus(mutant, arbre, base), [])

    def test_W5_semgrepignore_ui_assets_point_garde(self):
        """MUTANT M-SANS-POINT (rejoué) : le `.` reste en cible, sous le
        `.semgrepignore` de T-01M5HXFPTCC (non-contradiction, M3-M4) ; A, vu par
        `-- .` ET en cible explicite, ne compte qu'une fois au rapport JSON (M4)."""
        arbre = self.arbre({".semgrepignore": ".agents/ui/assets/\n", "src/x.py": 'eval("4")\n',
                            A: 'eval("1")\n'}, banc.REGLE_EVAL)
        rapports: list = []
        self.assertIn(TROUVAILLE, self.refus(banc.porte_adoptant, arbre, rapports=rapports))
        vus = [(r["path"], r["start"]["line"]) for r in rapports]
        self.assertEqual(sorted(vus), [(A, 1), ("src/x.py", 1)], rapports)
        mutant = self.charger_mutant(self.mutant(M_SANS_POINT))
        rapports = []
        self.refus(mutant, arbre, rapports=rapports)
        self.assertEqual([r["path"] for r in rapports], [A])


class EtageAVendorTests(unittest.TestCase):
    """Ce fichier voyage : aucune référence ancrée sur la racine réelle au
    marqueur ni à l'état local."""

    def test_aucune_reference_ancree(self):
        self.assertEqual(banc.references_ancrees(Path(__file__).read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
