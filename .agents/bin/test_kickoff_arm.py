#!/usr/bin/env python3
"""Banc de `kickoff_arm.py` — LE GESTE TRACE QUI ARME LE MANDAT D'ECRITURE.

CE QUE CE BANC PROTEGE. Le script existe pour une seule raison : le pilote a
demande que l'orchestrateur puisse lancer `/kickoff` sans son geste manuel, et
lever les deux couches de refus aurait rendu `kickoff_guard` decorative. La
propriete qui remplace le refus est donc la TRACE — et une trace qui peut
manquer en silence ne vaut rien. Ces tests portent d'abord la-dessus.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "kickoff_arm.py"


def depot_jetable(base: Path) -> Path:
    """Un vrai depot git : le script resout sa racine par `rev-parse`, comme le
    reste du kit, donc une arborescence nue ne suffirait pas."""
    subprocess.run(["git", "init", "-q", str(base)], check=True)
    (base / ".agents" / "bin").mkdir(parents=True)
    (base / ".agents" / "state" / "gates").mkdir(parents=True)
    return base


def lancer(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )


class KickoffArmTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = depot_jetable(Path(self._tmp.name))
        self.gate = self.root / ".agents" / "state" / "gates" / "KICKOFF_REQUIRED"
        # Un faux `ledger.py` qui REUSSIT, pour les cas nominaux.
        self.journal = self.root / ".agents" / "bin" / "ledger.py"
        self.trace = self.root / "trace.txt"
        self.journal.write_text(
            "import sys, pathlib\n"
            f"pathlib.Path(r'{self.trace}').open('a').write(' '.join(sys.argv[1:]) + chr(10))\n"
            "print('LEDGER: L-TEST added (decision)')\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_absence_du_fichier_est_le_regime_de_reference(self):
        r = lancer(self.root, "--status")
        self.assertEqual(0, r.returncode)
        self.assertIn("DESARME", r.stdout)
        self.assertFalse(self.gate.exists(), "`--status` ne doit RIEN ecrire")

    def test_armement_ecrit_le_fichier_et_trace(self):
        r = lancer(self.root, "--arm", "T-012", "--raison", "banc")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertTrue(self.gate.exists())
        self.assertIn("T-012", self.gate.read_text(encoding="utf-8"))
        self.assertIn("ARME", self.trace.read_text(encoding="utf-8"))

    def test_sans_trace_possible_rien_n_est_arme(self):
        """LA PROPRIETE CENTRALE. Si le registre ne peut pas enregistrer, le
        script REFUSE d'armer — un armement muet est exactement ce que ce script
        existe pour empecher. Le controle porte sur les DEUX moities : code de
        sortie non nul ET fichier absent."""
        self.journal.unlink()
        r = lancer(self.root, "--arm", "T-012")
        self.assertNotEqual(0, r.returncode)
        self.assertFalse(self.gate.exists(), "arme SANS trace : la garde est contournable en silence")

    def test_un_registre_qui_echoue_bloque_aussi(self):
        """Meme propriete, autre cause : le registre EXISTE mais refuse."""
        self.journal.write_text("import sys; sys.exit(7)\n", encoding="utf-8")
        r = lancer(self.root, "--arm", "T-012")
        self.assertNotEqual(0, r.returncode)
        self.assertFalse(self.gate.exists())

    def test_identifiant_mal_forme_refuse_avant_toute_ecriture(self):
        r = lancer(self.root, "--arm", "PAS-UN-ID")
        self.assertEqual(2, r.returncode)
        self.assertFalse(self.gate.exists())
        self.assertFalse(self.trace.exists(), "rien ne doit etre trace pour un refus de forme")

    def test_arm_remplace_la_liste_au_lieu_de_cumuler(self):
        """C'est un MANDAT, pas un cumul : une tache qui n'est plus nommee n'est
        plus armee. Un cumul silencieux elargirait le mandat sans decision."""
        lancer(self.root, "--arm", "T-012", "T-013")
        lancer(self.root, "--arm", "T-014")
        contenu = self.gate.read_text(encoding="utf-8")
        self.assertIn("T-014", contenu)
        self.assertNotIn("T-012", contenu)
        self.assertNotIn("T-013", contenu)

    def test_desarmement_supprime_le_fichier_et_trace(self):
        lancer(self.root, "--arm", "T-012")
        r = lancer(self.root, "--disarm", "--raison", "banc")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertFalse(self.gate.exists())
        self.assertIn("DESARME", self.trace.read_text(encoding="utf-8"))

    def test_desarmement_sans_trace_possible_est_refuse(self):
        """LE SENS QUI COMPTE LE PLUS. Un agent peut desormais se desarmer — c'est
        le prix du geste demande par le pilote. Ce qui doit rester impossible,
        c'est de le faire SANS que ce soit ecrit quelque part."""
        lancer(self.root, "--arm", "T-012")
        self.journal.unlink()
        r = lancer(self.root, "--disarm")
        self.assertNotEqual(0, r.returncode)
        self.assertTrue(self.gate.exists(), "desarme SANS trace : la garde est levee en silence")

    def test_reecriture_identique_n_ecrit_rien(self):
        lancer(self.root, "--arm", "T-012")
        avant = self.trace.read_text(encoding="utf-8")
        r = lancer(self.root, "--arm", "T-012")
        self.assertEqual(0, r.returncode)
        self.assertEqual(avant, self.trace.read_text(encoding="utf-8"),
                         "un armement idempotent ne doit pas polluer le registre")

    def test_armement_sur_un_t_ulid(self):
        """T-00001040 : une tâche `T-<ULID>` (C2 de T-00000726) s'arme comme une
        ancienne. MUTANT M3 (branche ULID retirée de `ID_RE`) ⇒ rc 2, rouge."""
        r = lancer(self.root, "--arm", f"T-{U_LETTER}", "T-012", "--raison", "banc")
        self.assertEqual(0, r.returncode, r.stderr)
        contenu = self.gate.read_text(encoding="utf-8")
        self.assertIn(f"T-{U_LETTER}", contenu)
        self.assertIn("T-012", contenu)


# T-00001040 — `ID_RE` en colonne ANCRÉE (réserve B-C8 du plan de T-00000726) :
# fixtures FIXES, un corps ULID qui finit par une LETTRE et un par un CHIFFRE.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kickoff_arm_banc_ulid", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IdGrammaireTests(unittest.TestCase):
    """MUTANTS : M3 (ULID retiré) et R2 (numérique retiré) ⇒ `accepte` rouge ;
    M8' (`\\A…\\Z` → `^…$`), R3 (`(?i)`), R4 (`[0-9]{3,}` → `[0-9A-Z]{3,}`) ⇒
    `refuse` rouge."""

    def test_ancree_accepte_ulid_ancien_et_ancien_court(self):
        id_re = _module().ID_RE
        for tid in (f"T-{U_LETTER}", f"T-{U_DIGIT}", "T-00000001", "T-012", "T-1040"):
            with self.subTest(tid=tid):
                self.assertIsNotNone(id_re.match(tid), tid)

    def test_ancree_refuse_les_formes_voisines(self):
        id_re = _module().ID_RE
        for tid in ("T-00000001\n", f"T-{U_LETTER}\n", f"T-{U_LETTER[:-1]}", f"T-{U_LETTER}A",
                    f"T-0{U_LETTER}", f"T-{U_LETTER.lower()}", f"t-{U_LETTER}", "T-12",
                    "T-" + U_LETTER[:-1] + "U", f"S-{U_LETTER}", "PAS-UN-ID", ""):
            with self.subTest(tid=tid):
                self.assertIsNone(id_re.match(tid), repr(tid))


BIN = ROOT / ".agents" / "bin"


def jouer_script(nom: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(BIN / nom), *args],
        cwd=cwd or ROOT, capture_output=True, text=True, check=False,
        env={**os.environ, "NO_COLOR": "1"},  # sous -I, PYTHON_COLORS est ignore ; NO_COLOR bat FORCE_COLOR
    )


class AliasAnglais(unittest.TestCase):
    """T-01M5QC86XNEJ5NEX6DGZJ0AJZ5, lot K : chaque CLI de porte et de lancement
    prend le nom ANGLAIS en tete et garde l'ancien nom francais en alias, sur la
    MEME `dest`. MUTANTS (annexe § C) : `--reason` sans `dest="raison"` => la trace
    perd son motif (AttributeError) ; `--list` retire => rc 2 d'argparse, aucune
    ligne `porte :` ; `--list` sur une autre `dest` => mode porte, PORTE_RESULT
    efface ; `--write`/`--root` sans `dest` ancien => AttributeError ou racine
    ignoree ; `--freshness` retire ou sans `dest` => aucune ligne FRAICHEUR."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_kickoff_arm_reason_et_raison_portent_le_motif(self):
        for drapeau in ("--reason", "--raison"):
            with self.subTest(drapeau=drapeau):
                root = depot_jetable(self.base / drapeau.strip("-"))
                trace = root / "trace.txt"
                (root / ".agents" / "bin" / "ledger.py").write_text(
                    "import sys, pathlib\n"
                    f"pathlib.Path(r'{trace}').open('a').write(' '.join(sys.argv[1:]) + chr(10))\n"
                    "print('LEDGER: L-TEST added (decision)')\n",
                    encoding="utf-8",
                )
                r = lancer(root, "--arm", "T-012", drapeau, f"motif-{drapeau.strip('-')}")
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertIn(f"motif-{drapeau.strip('-')}", trace.read_text(encoding="utf-8"))

    def test_porte_adoptant_list_et_liste_ne_jouent_pas_la_porte(self):
        for drapeau in ("--list", "--liste"):
            with self.subTest(drapeau=drapeau):
                arbre = self.base / drapeau.strip("-")
                resultat = arbre / ".agents" / "state" / "local" / "PORTE_RESULT"
                resultat.parent.mkdir(parents=True)
                resultat.write_text("OK\n", encoding="utf-8")
                r = jouer_script("porte_adoptant.py", drapeau, "--root", str(arbre))
                self.assertNotIn("Traceback", r.stderr)
                self.assertNotIn("unrecognized", r.stderr)
                self.assertIn("porte : AUCUNE", r.stdout)
                self.assertTrue(resultat.exists(), f"{drapeau} a joue le mode porte (PORTE_RESULT efface)")

    def test_hooks_jumeaux_write_root_et_ecrire_racine(self):
        for options in (("--write", "--root"), ("--ecrire", "--racine")):
            with self.subTest(options=options):
                depot = self.base / options[0].strip("-")
                (depot / ".codex" / "hooks").mkdir(parents=True)
                (depot / ".gemini" / "hooks").mkdir(parents=True)
                (depot / ".codex" / "hooks" / "a.py").write_bytes(b"print(1)\n")
                r = jouer_script("hooks_jumeaux.py", options[0], options[1], str(depot))
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertIn("ecrit: a.py", r.stdout)
                self.assertEqual(b"print(1)\n", (depot / ".gemini" / "hooks" / "a.py").read_bytes())

    def test_sync_template_docs_freshness_et_fraicheur(self):
        for drapeau in ("--freshness", "--fraicheur"):
            with self.subTest(drapeau=drapeau):
                r = jouer_script("sync_template_docs.py", drapeau, "--ref", "main", "--tag", "pas-un-tag")
                self.assertEqual(2, r.returncode, r.stderr)
                self.assertIn("FRAICHEUR 2:", r.stdout)

    def test_aide_nomme_l_anglais_en_tete_et_l_alias(self):
        for nom, anglais, ancien in (
            ("kickoff_arm.py", "--reason", "--raison"),
            ("porte_adoptant.py", "--list", "--liste"),
            ("hooks_jumeaux.py", "--write", "--ecrire"),
            ("hooks_jumeaux.py", "--root", "--racine"),
            ("sync_template_docs.py", "--freshness", "--fraicheur"),
        ):
            with self.subTest(nom=nom, anglais=anglais):
                aide = jouer_script(nom, "--help").stdout
                self.assertIn(f"  {anglais}", aide)
                self.assertIn(f", {ancien}", aide)
                self.assertLess(aide.index(f"  {anglais}"), aide.index(f", {ancien}"))
                self.assertTrue(aide.isascii(),"aide non ASCII")

    def test_aide_de_night_approve_ascii_et_metavars_anglais(self):
        aide = jouer_script("night_approve.py", "--help")
        self.assertEqual(0, aide.returncode, aide.stderr)
        self.assertTrue(aide.stdout.isascii(), "aide de night_approve non ASCII")
        self.assertIn("--reason, --raison REASON", jouer_script("kickoff_arm.py", "--help").stdout)
        self.assertIn("--root, --racine ROOT", jouer_script("hooks_jumeaux.py", "--help").stdout)


if __name__ == "__main__":
    unittest.main()
