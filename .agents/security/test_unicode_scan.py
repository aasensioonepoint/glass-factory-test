#!/usr/bin/env python3
"""Banc de unicode_scan.py (T-01M5BZBZ849P61Y6471JZMMPRD).

Lancer : python3 -m pytest -q -p no:cacheprovider .agents/security/test_unicode_scan.py

Toute fixture invisible est bâtie par `chr(0x...)` : aucun caractère invisible littéral ni
échappement `\\u` dans ce fichier (L-00000535) — le banc CLI final le prouve en scannant ce
fichier lui-même.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import unicode_scan as us  # noqa: E402

SCRIPT = ICI / "unicode_scan.py"


def tags(texte: str) -> str:
    return "".join(chr(0xE0000 + ord(c)) for c in texte)


DRAPEAU = chr(0x1F3F4)
ANNULE = chr(0xE007F)

PROPRES = {
    "francais": "Élève à l'école, ça déçoit — « œuvre »",
    "cjk": "漢字とかな、한국어",
    "avertissement_vs16": chr(0x26A0) + chr(0xFE0F),
    "avertissement_vs15": chr(0x26A0) + chr(0xFE0E),
    "arc_en_ciel": chr(0x1F3F3) + chr(0xFE0F) + chr(0x200D) + chr(0x1F308),
    "couple": chr(0x1F468) + chr(0x200D) + chr(0x1F469),
    "bom_initial": chr(0xFEFF) + "# titre\n",
    "keycap": "1" + chr(0xFE0F) + chr(0x20E3) + " #" + chr(0xFE0F) + chr(0x20E3),
    "fleche_sm": chr(0x2194) + chr(0xFE0F),
    "double_exclamation_po": chr(0x203C) + chr(0xFE0F),
    "teint_puis_zwj": chr(0x1F469) + chr(0x1F3FD) + chr(0x200D) + chr(0x1F4BB),
    "subdivision": DRAPEAU + tags("gbeng") + ANNULE,
    "subdivision_ecosse": DRAPEAU + tags("gbsct") + ANNULE,
    "subdivision_galles": "x " + DRAPEAU + tags("gbwls") + ANNULE + " y",
    "tab_cr_lf": "a\tb\r\nc\n",
    "crlf_partout": "a" + chr(0x0D) + "\nb" + chr(0x0D) + "\n",
    # Bornes ÉCRITES : Zs et U+2800 occupent une largeur, ils sont admis.
    "espaces_zs_et_braille_vide": "a" + chr(0x3000) + "b" + chr(0x2800) + "c" + chr(0x2009),
}


def contrebande(charge: str) -> tuple[str, list]:
    """Drapeau + tags de `charge` + E007F : tout tag hors du jeu RGI est un constat."""
    texte = DRAPEAU + tags(charge) + ANNULE
    return texte, ([(1, k, 0xE0000 + ord(c)) for k, c in enumerate(charge, 2)]
                   + [(1, len(charge) + 2, 0xE007F)])


# Forme jadis admise (2 à 7 tags [0-9a-z] après 1F3F4, clos par E007F) : contrebande ASCII.
CONTREBANDES = ("ignore", "ignorea", "sysprom", "rmrf000", "exfil42", "usca", "gbeng0", "gbxyz", "gbenx",
                "gbwlz")

SIGNALES = {
    "rlo": ("ab" + chr(0x202E) + "c", [(1, 3, 0x202E)]),
    "lrm": (chr(0x200E), [(1, 1, 0x200E)]),
    "isolat_bidi": ("x" + chr(0x2066), [(1, 2, 0x2066)]),
    "zwsp": (chr(0x200B), [(1, 1, 0x200B)]),
    "zwj_isole": ("a" + chr(0x200D) + "b", [(1, 2, 0x200D)]),
    "zwj_sans_so_a_droite": (chr(0x1F468) + chr(0x200D) + "b", [(1, 2, 0x200D)]),
    "zwj_apres_vs_non_admis": ("a" + chr(0xFE0F) + chr(0x200D) + chr(0x1F308),
                               [(1, 2, 0xFE0F), (1, 3, 0x200D)]),
    "bom_median": ("a" + chr(0xFEFF), [(1, 2, 0xFEFF)]),
    "bom_ligne_2": ("a\n" + chr(0xFEFF), [(2, 1, 0xFEFF)]),
    "tag_seul": ("x" + chr(0xE0041), [(1, 2, 0xE0041)]),
    "vs16_isole": ("a" + chr(0xFE0F), [(1, 2, 0xFE0F)]),
    "vs16_double": (chr(0x26A0) + chr(0xFE0F) + chr(0xFE0F), [(1, 3, 0xFE0F)]),
    "vs_supplementaire": (chr(0x26A0) + chr(0xE0100), [(1, 2, 0xE0100)]),
    "vs16_apres_po_ascii": ("!" + chr(0xFE0F), [(1, 2, 0xFE0F)]),
    "keycap_sans_20e3": ("1" + chr(0xFE0F), [(1, 2, 0xFE0F)]),
    "subdivision_majuscules": (DRAPEAU + chr(0xE0047) + chr(0xE0042) + ANNULE,
                               [(1, 2, 0xE0047), (1, 3, 0xE0042), (1, 4, 0xE007F)]),
    "subdivision_sans_annule": (DRAPEAU + tags("gb"), [(1, 2, 0xE0067), (1, 3, 0xE0062)]),
    "subdivision_trop_longue": (DRAPEAU + tags("abcdefgh") + ANNULE,
                                [(1, k, 0xE0000 + ord(c)) for k, c in enumerate("abcdefgh", 2)]
                                + [(1, 10, 0xE007F)]),
    "subdivision_sans_drapeau": ("x" + tags("gb") + ANNULE,
                                 [(1, 2, 0xE0067), (1, 3, 0xE0062), (1, 4, 0xE007F)]),
    "remplissage_hangul_lo": (chr(0x3164) + chr(0x115F) + chr(0x1160),
                              [(1, 1, 0x3164), (1, 2, 0x115F), (1, 3, 0x1160)]),
    "prive_co": (chr(0xE000), [(1, 1, 0xE000)]),
    "del_cc": ("a" + chr(0x7F), [(1, 2, 0x7F)]),
    # CR admis SEULEMENT juste avant LF : isolé, doublé ou final sans LF, il masque l'affichage.
    "cr_isole": ("a" + chr(0x0D) + "b", [(1, 2, 0x0D)]),
    "cr_double_avant_lf": ("a" + chr(0x0D) + chr(0x0D) + "\nb", [(1, 2, 0x0D)]),
    "cr_final_sans_lf": ("a\nb" + chr(0x0D), [(2, 2, 0x0D)]),
    # Teint sans So à sa gauche : la branche teint de _zwj_admis refuse.
    "zwj_apres_teint_sans_so": ("a" + chr(0x1F3FD) + chr(0x200D) + chr(0x1F4BB), [(1, 3, 0x200D)]),
    "remplissage_demi_chasse": ("a" + chr(0xFFA0), [(1, 2, 0xFFA0)]),
    "cgj": ("e" + chr(0x034F), [(1, 2, 0x034F)]),
    "khmer_inherentes": (chr(0x17B4) + chr(0x17B5), [(1, 1, 0x17B4), (1, 2, 0x17B5)]),
    "reserve_2065": (chr(0x2065), [(1, 1, 0x2065)]),
    "specials_reserves": (chr(0xFFF0) + chr(0xFFF8), [(1, 1, 0xFFF0), (1, 2, 0xFFF8)]),
    "plan_14_reserve": (chr(0xE0080) + chr(0xE0FFF), [(1, 1, 0xE0080), (1, 2, 0xE0FFF)]),
    "vs_mongols": ("".join(chr(c) for c in range(0x180B, 0x1810)),
                   [(1, k, c) for k, c in enumerate(range(0x180B, 0x1810), 1)]),
    "drapeau_galles_sans_annule": (DRAPEAU + tags("gbwls"),
                                   [(1, k, 0xE0000 + ord(c)) for k, c in enumerate("gbwls", 2)]),
    # Lignes comptées sur LF SEUL : splitlines() couperait aussi sur 0085, 001E et 2028.
    "nel_rs_ls_ps": ("a" + chr(0x85) + "b\nc" + chr(0x1E) + "d\n" + chr(0x2028) + chr(0x2029)
                     + "e" + chr(0x200B),
                     [(1, 2, 0x85), (2, 2, 0x1E), (3, 1, 0x2028), (3, 2, 0x2029),
                      (3, 4, 0x200B)]),
}


class Constats(unittest.TestCase):
    def test_textes_propres_rendent_zero(self):
        for nom, texte in PROPRES.items():
            with self.subTest(nom=nom):
                self.assertEqual([], us.constats(texte))

    def test_textes_signales_a_la_ligne_et_colonne_justes(self):
        for nom, (texte, attendu) in SIGNALES.items():
            with self.subTest(nom=nom):
                self.assertEqual(attendu, us.constats(texte))

    def test_contrebande_de_tags_hors_rgi_est_signalee(self):
        for charge in CONTREBANDES:
            with self.subTest(charge=charge):
                texte, attendu = contrebande(charge)
                self.assertEqual(attendu, us.constats(texte))
                self.assertTrue(us.refus(texte).startswith(
                    f"invisible-unicode character refused: U+{0xE0000 + ord(charge[0]):04X} TAG"))

    def test_nom_lisible_ou_categorie(self):
        self.assertEqual("RIGHT-TO-LEFT OVERRIDE", us.nom(0x202E))
        self.assertEqual("<Cc>", us.nom(0x85))


ENTETE_SPECS = {"format": 1, "store": "specs"}


def specs_entree(sid: str, kind: str = "decision") -> dict:
    return {"date": "2026-10-21", "files": [], "id": sid, "kind": kind, "task": "T-01M5CN9FM2",
            "text": "", "title": f"{kind} {sid}"}


def poser_journal(racine: Path, *lignes, nom: str = "SPECS.jsonl") -> Path:
    """Un journal de specs jetable sous `racine` : objets sérialisés, chaînes écrites telles quelles."""
    dossier = racine / ".agents" / "state" / "specs"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_bytes("".join((x if isinstance(x, str) else json.dumps(x)) + "\n"
                               for x in lignes).encode("utf-8"))
    return chemin


class Allowlist(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp(prefix="unicode-scan-"))
        self.addCleanup(shutil.rmtree, self.racine, True)
        (self.racine / ".agents" / "security").mkdir(parents=True)
        # La décision que cite `entree()` est TRACÉE : sans elle, l'entrée serait ignorée.
        self.journal = poser_journal(self.racine, ENTETE_SPECS, specs_entree("S-01M5CD8VK6"))

    def poser(self, contenu) -> None:
        brut = contenu if isinstance(contenu, str) else json.dumps(contenu)
        (self.racine / ".agents" / "security" / "unicode-allowlist.json").write_bytes(
            brut.encode("utf-8"))

    def entree(self, **kw) -> dict:
        e = {"cible": "o/r#s@abc123", "codepoint": "U+200B", "decision": "S-01M5CD8VK6"}
        e.update(kw)
        return e

    def test_entree_appliquee_a_sa_cible_seule(self):
        self.poser({"entrees": [self.entree()]})
        texte = "a" + chr(0x200B)
        self.assertIsNone(us.refus(texte, "o/r#s@abc123", self.racine))
        # un sha neuf annule l'entrée
        self.assertEqual("invisible-unicode character refused: U+200B ZERO WIDTH SPACE at line 1 col 2",
                         us.refus(texte, "o/r#s@def456", self.racine))

    def test_autre_codepoint_reste_refuse_avec_le_compte(self):
        self.poser({"entrees": [self.entree()]})
        texte = chr(0x200B) + chr(0x202E) + chr(0x2066)
        self.assertEqual(
            "invisible-unicode character refused: U+202E RIGHT-TO-LEFT OVERRIDE at line 1 col 2"
            " (+1 more)", us.refus(texte, "o/r#s@abc123", self.racine))

    def test_allowlist_absente_vaut_vide(self):
        self.assertTrue(us.refus(chr(0x200B), "o/r#s@abc123", self.racine).startswith(
            "invisible-unicode character refused: U+200B"))
        self.assertEqual([], us.charger_allowlist(self.racine))

    def test_allowlist_lue_seulement_sur_constat(self):
        self.poser("{pas du json")
        self.assertIsNone(us.refus("texte propre " + chr(0x26A0) + chr(0xFE0F), "x", self.racine))

    def test_allowlist_invalide_refuse(self):
        cas = {
            "json_invalide": "{pas du json",
            "racine_liste": [],
            "cle_inconnue_en_tete": {"entrees": [], "autre": 1},
            "sans_decision": {"entrees": [{"cible": "o/r#s@abc123", "codepoint": "U+200B"}]},
            "decision_sans_s_id": {"entrees": [self.entree(decision="accord oral")]},
            "cle_inconnue": {"entrees": [dict(self.entree(), expire="2030")]},
            "codepoint_minuscule": {"entrees": [self.entree(codepoint="U+200b")]},
            "cible_vide": {"entrees": [self.entree(cible="")]},
        }
        for nom, contenu in cas.items():
            with self.subTest(nom=nom):
                self.poser(contenu)
                with self.assertRaises(us.AllowlistInvalide):
                    us.charger_allowlist(self.racine)
                self.assertTrue(us.refus(chr(0x200B), "o/r#s@abc123", self.racine).startswith(
                    "invisible-unicode allowlist refused: .agents/security/unicode-allowlist.json"))

    def test_note_optionnelle_admise(self):
        self.poser({"entrees": [dict(self.entree(), note="RTL légitime")]})
        self.assertIsNone(us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_sans_racine_aucune_allowlist(self):
        self.poser({"entrees": [self.entree()]})
        self.assertIsNotNone(us.refus(chr(0x200B), "o/r#s@abc123", None))

    # T-01M5CN9FM2MPY8Z00AS7FTXXWH : la décision citée doit EXISTER au journal, en `kind: decision`.
    REFUS_200B = "invisible-unicode character refused: U+200B ZERO WIDTH SPACE at line 1 col 1"

    def test_s_id_inconnu_ignore_et_dit(self):
        self.poser({"entrees": [self.entree(decision="S-01M5ZZZZZZ")]})
        self.assertEqual(self.REFUS_200B + "; allowlist entry 0 ignored: decision S-01M5ZZZZZZ not found in SPECS",
                         us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_s_id_connu_honore_et_seule_l_entree_inconnue_est_dite(self):
        self.poser({"entrees": [self.entree(), self.entree(codepoint="U+202E", decision="S-01M5ZZZZZZ")]})
        self.assertIsNone(us.refus(chr(0x200B), "o/r#s@abc123", self.racine))
        self.assertEqual(
            "invisible-unicode character refused: U+202E RIGHT-TO-LEFT OVERRIDE at line 1 col 2"
            "; allowlist entry 1 ignored: decision S-01M5ZZZZZZ not found in SPECS",
            us.refus(chr(0x200B) + chr(0x202E), "o/r#s@abc123", self.racine))

    def test_kind_autre_que_decision_non_honore(self):
        for kind in ("verdict", "plan", "delta"):
            with self.subTest(kind=kind):
                poser_journal(self.racine, ENTETE_SPECS, specs_entree("S-01M5CD8VK6", kind))
                self.poser({"entrees": [self.entree()]})
                self.assertEqual(self.REFUS_200B + "; allowlist entry 0 ignored: decision S-01M5CD8VK6"
                                 " not found in SPECS", us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_journal_absent_toutes_entrees_ignorees_et_dit(self):
        self.journal.unlink()
        self.poser({"entrees": [self.entree()]})
        self.assertEqual(self.REFUS_200B + "; allowlist entry 0 ignored: decision S-01M5CD8VK6 unverifiable,"
                         " SPECS journal absent", us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_journal_illisible_toutes_entrees_ignorees_et_dit(self):
        decision = specs_entree("S-01M5CD8VK6")
        cas = {
            "ligne_non_json": ((ENTETE_SPECS, decision, "{pas du json"), "line 3: JSONDecodeError"),
            "sans_entete": ((decision,), "line 1: no journal header"),
            "entete_etranger": (({"format": 1, "store": "board"}, decision), "line 1: no journal header"),
            "ligne_non_objet": ((ENTETE_SPECS, decision, "[1, 2]"), "line 3: not a JSON object"),
            "vide": ((), "no journal header"),
        }
        self.poser({"entrees": [self.entree()]})
        for nom, (lignes, cause) in cas.items():
            with self.subTest(nom=nom):
                poser_journal(self.racine, *lignes)
                self.assertEqual(self.REFUS_200B + "; allowlist entry 0 ignored: decision S-01M5CD8VK6"
                                 f" unverifiable, SPECS unreadable ({cause})",
                                 us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_journal_non_utf8_et_ligne_trop_longue_illisibles(self):
        self.poser({"entrees": [self.entree()]})
        self.journal.write_bytes(json.dumps(ENTETE_SPECS).encode() + b"\n\xff\xfe\n")
        self.assertIn("SPECS unreadable (line 2: UnicodeDecodeError)", us.refus(chr(0x200B), "o/r#s@abc123",
                                                                                 self.racine))
        poser_journal(self.racine, ENTETE_SPECS, dict(specs_entree("S-01M5CD8VK6"), text="x" * 4096))
        borne = us.MAX_LIGNE_SPECS
        self.addCleanup(setattr, us, "MAX_LIGNE_SPECS", borne)
        us.MAX_LIGNE_SPECS = 1024
        self.assertIn("SPECS unreadable (line 2: over 1024 bytes)", us.refus(chr(0x200B), "o/r#s@abc123",
                                                                             self.racine))

    def test_deux_stores_illisible(self):
        poser_journal(self.racine, nom="SPECS.json")
        self.poser({"entrees": [self.entree()]})
        self.assertIn("unverifiable, SPECS unreadable (both SPECS.json and SPECS.jsonl)",
                      us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_lignes_vides_sautees_comme_specs_py(self):
        poser_journal(self.racine, "", ENTETE_SPECS, "", specs_entree("S-01M5CD8VK6"))
        self.poser({"entrees": [self.entree()]})
        self.assertIsNone(us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_monolithe_specs_json_lu_quand_le_journal_manque(self):
        self.journal.unlink()
        dossier = self.racine / ".agents" / "state" / "specs"
        (dossier / "SPECS.json").write_text(json.dumps({"entries": [
            specs_entree("S-01M5CD8VK6"), specs_entree("S-01M5VVVVVV", "verdict")]}), encoding="utf-8")
        self.poser({"entrees": [self.entree(), self.entree(codepoint="U+202E", decision="S-01M5VVVVVV")]})
        self.assertIsNone(us.refus(chr(0x200B), "o/r#s@abc123", self.racine))
        self.assertIn("allowlist entry 1 ignored: decision S-01M5VVVVVV not found in SPECS",
                      us.refus(chr(0x202E), "o/r#s@abc123", self.racine))
        (dossier / "SPECS.json").write_text('{"entrees": []}', encoding="utf-8")
        self.assertIn("SPECS unreadable (SPECS.json: no 'entries' list)",
                      us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_avis_tus_pour_une_autre_cible_ou_un_autre_codepoint(self):
        self.poser({"entrees": [self.entree(cible="autre/cible", decision="S-01M5ZZZZZZ"),
                                self.entree(codepoint="U+2066", decision="S-01M5ZZZZZZ")]})
        self.assertEqual(self.REFUS_200B, us.refus(chr(0x200B), "o/r#s@abc123", self.racine))

    def test_journal_jamais_lu_sans_entree(self):
        self.journal.write_text("{pas du json\n", encoding="utf-8")
        self.poser({"entrees": []})
        self.assertEqual(self.REFUS_200B, us.refus(chr(0x200B), "o/r#s@abc123", self.racine))
        self.assertEqual(([], []), us.scanner([], self.racine))


class Cli(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp(prefix="unicode-cli-"))
        self.addCleanup(shutil.rmtree, self.racine, True)

    def lancer(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(cwd or self.racine),
                              capture_output=True, text=True, encoding="utf-8", timeout=60,
                              check=False)

    def ecrire(self, rel: str, texte: str) -> None:
        chemin = self.racine / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(texte.encode("utf-8"))

    def test_module_et_banc_sont_propres(self):
        r = self.lancer("--", "unicode_scan.py", "test_unicode_scan.py", cwd=ICI)
        self.assertEqual((0, ""), (r.returncode, r.stdout), r.stderr)

    def test_constat_rc1_au_format(self):
        self.ecrire("f.md", "ok\nab" + chr(0x202E) + "\n")
        self.ecrire("-tiret.md", chr(0x200B))
        r = self.lancer("--", "f.md", "-tiret.md")
        self.assertEqual(1, r.returncode, r.stderr)
        self.assertEqual(["f.md:2:3:U+202E:RIGHT-TO-LEFT OVERRIDE",
                          "-tiret.md:1:1:U+200B:ZERO WIDTH SPACE"], r.stdout.splitlines())

    def test_chemin_relatif_lu_sous_la_racine_jamais_sous_le_cwd(self):
        # le cwd (ICI) porte un unicode_scan.py propre du même nom : il ne doit pas masquer
        self.ecrire("unicode_scan.py", chr(0x202E))
        r = self.lancer("--racine", str(self.racine), "--", "unicode_scan.py", cwd=ICI)
        self.assertEqual((1, "unicode_scan.py:1:1:U+202E:RIGHT-TO-LEFT OVERRIDE"),
                         (r.returncode, r.stdout.strip()), r.stderr)

    def test_allowlist_par_chemin_rc0(self):
        self.ecrire("docs/rtl.md", "x" + chr(0x200F))
        self.ecrire(".agents/security/unicode-allowlist.json", json.dumps({"entrees": [
            {"cible": "docs/rtl.md", "codepoint": "U+200F", "decision": "S-00004500"}]}))
        poser_journal(self.racine, ENTETE_SPECS, specs_entree("S-00004500"))
        r = self.lancer("--", "docs/rtl.md")
        self.assertEqual((0, "", ""), (r.returncode, r.stdout, r.stderr))

    def test_s_id_invente_rc1_et_dit_sur_stderr(self):
        # T-01M5CN9FM2MPY8Z00AS7FTXXWH : une entrée au S-id absent du journal est ignorée ET dite.
        self.ecrire("docs/rtl.md", "x" + chr(0x200F))
        self.ecrire("docs/autre.md", "y" + chr(0x200F))
        self.ecrire(".agents/security/unicode-allowlist.json", json.dumps({"entrees": [
            {"cible": "docs/rtl.md", "codepoint": "U+200F", "decision": "S-01M5ZZZZZZ"}]}))
        poser_journal(self.racine, ENTETE_SPECS, specs_entree("S-00004500"),
                      specs_entree("S-01M5ZZZZZZ", "verdict"))
        r = self.lancer("--", "docs/rtl.md", "docs/autre.md")
        self.assertEqual((1, ["docs/rtl.md:1:2:U+200F:RIGHT-TO-LEFT MARK",
                              "docs/autre.md:1:2:U+200F:RIGHT-TO-LEFT MARK"]),
                         (r.returncode, r.stdout.splitlines()), r.stderr)
        self.assertEqual("unicode_scan.py: allowlist entry 0 ignored: decision S-01M5ZZZZZZ not found in SPECS\n",
                         r.stderr)

    def test_journal_absent_rc1_et_dit_sur_stderr(self):
        self.ecrire("docs/rtl.md", "x" + chr(0x200F))
        self.ecrire(".agents/security/unicode-allowlist.json", json.dumps({"entrees": [
            {"cible": "docs/rtl.md", "codepoint": "U+200F", "decision": "S-00004500"}]}))
        r = self.lancer("--", "docs/rtl.md")
        self.assertEqual(1, r.returncode, r.stderr)
        self.assertIn("allowlist entry 0 ignored: decision S-00004500 unverifiable, SPECS journal absent", r.stderr)

    def test_allowlist_invalide_sur_constat_rc2(self):
        self.ecrire("f.md", chr(0x200B))
        self.ecrire(".agents/security/unicode-allowlist.json", '{"entrees": [{"cible": "f.md"}]}')
        r = self.lancer("--", "f.md")
        self.assertEqual((2, ""), (r.returncode, r.stdout), r.stderr)
        self.assertIn("unicode-allowlist.json entry 0", r.stderr)

    def test_allowlist_invalide_sans_constat_rc2(self):
        # La CLI valide l'allowlist à CHAQUE appel ; refus() seul la lit sur constat (borne écrite).
        self.ecrire("propre.md", "texte propre\n")
        self.ecrire(".agents/security/unicode-allowlist.json", "{pas du json")
        r = self.lancer("--", "propre.md")
        self.assertEqual((2, ""), (r.returncode, r.stdout), r.stderr)
        self.assertIn("unicode-allowlist.json unreadable (JSONDecodeError)", r.stderr)

    def test_contrebande_de_tags_rc1(self):
        self.ecrire("skill.md", "titre\n" + contrebande("ignore")[0] + "\n")
        r = self.lancer("--", "skill.md")
        self.assertEqual(1, r.returncode, r.stderr)
        self.assertEqual("skill.md:2:2:U+E0069:TAG LATIN SMALL LETTER I", r.stdout.splitlines()[0])
        self.assertEqual(7, len(r.stdout.splitlines()))

    def test_usage_et_fichiers_illisibles_rc2(self):
        self.assertEqual(2, self.lancer().returncode)
        self.assertEqual(2, self.lancer("--", "absent.md").returncode)
        (self.racine / "binaire.md").write_bytes(bytes([0xFF, 0xFE, 0x00]))
        r = self.lancer("--", "binaire.md")
        self.assertEqual(2, r.returncode)
        self.assertIn("binaire.md: unreadable (UnicodeDecodeError)", r.stderr)


if __name__ == "__main__":
    unittest.main()
