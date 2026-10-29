#!/usr/bin/env python3
"""Banc de `kit_code_guard._TICKET` — LA GRAMMAIRE D'ID D'UN OCTROI PILOTE
(T-00001040, étape 4 du plan de T-00000726).

CE QUE CE BANC PROTÈGE. Une ligne de `KIT_CODE_AUTORISE` nomme le ticket qui
justifie l'octroi. Le jour où `tasks.py new` émet des `T-<ULID>` (C2 de
T-00000726), une grammaire restée `T-\\d{8}` rendrait MALFORMÉE toute ligne
écrite pour une tâche neuve : l'octroi ne mordrait pas, et le refus le compterait
comme une faute du pilote. La constante est RECOPIÉE (jamais importée de
`tasks.py`) : ce banc la tient sur une table de fixtures fixe (réserve B-C8 du
plan), en colonne ANCRÉE.

MUTANTS (joués sur la constante réelle, chacun rougit au moins le témoin nommé) :
  M3    branche ULID retirée de `_TICKET` ⇒ `test_ancree_accepte_ulid_et_ancien`
  M8'   `\\A…\\Z` revenu à `^…$` ⇒ `test_ancree_refuse_les_formes_voisines`
        (`"T-00000001\\n"` accepté)
  R2    branche numérique retirée ⇒ `test_ancree_accepte_ulid_et_ancien`
  R3    `(?i)` posé sur la constante ⇒ `test_ancree_refuse_les_formes_voisines`
        (corps minuscule accepté)
  R4    branche numérique élargie (`\\d{8}` → `\\d+` ou `[0-9A-Z]+`) ⇒
        `test_ancree_refuse_les_formes_voisines` (`T-012` ou `T-0<ULID>` accepté)
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / ".agents" / "bin" / "kit_code_guard.py"


def _charger():
    spec = importlib.util.spec_from_file_location("kit_code_guard_banc_ulid", GUARD)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


kcg = _charger()

# Fixtures FIXES (réserve B-C8) : un corps qui finit par une LETTRE, un qui finit
# par un CHIFFRE ; tous deux en majuscules Crockford, 26 symboles.
CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


class FixturesTests(unittest.TestCase):
    def test_les_fixtures_sont_des_ulid(self):
        """Filet à vide : une fixture mal formée rendrait les deux colonnes
        vertes pour une mauvaise raison."""
        for u in (U_LETTER, U_DIGIT):
            self.assertEqual(len(u), 26, u)
            self.assertTrue(set(u) <= CROCKFORD, u)
        self.assertTrue(U_LETTER[-1].isalpha())
        self.assertTrue(U_DIGIT[-1].isdigit())


class TicketGrammaireTests(unittest.TestCase):
    def test_ancree_accepte_ulid_et_ancien(self):
        """MUTANTS M3, R2 : la ligne d'un octroi pour une tâche `T-<ULID>` ET
        pour une tâche ancienne à 8 chiffres est lue."""
        for tid in (f"T-{U_LETTER}", f"T-{U_DIGIT}", "T-00000001", "T-00001040"):
            with self.subTest(tid=tid):
                self.assertIsNotNone(kcg._TICKET.match(tid), tid)

    def test_ancree_refuse_les_formes_voisines(self):
        """MUTANTS M8', R3, R4 : saut de ligne final, corps à 25/27 symboles,
        `T-0<ULID>`, minuscules, lettres exclues (I, L, O, U), préfixe étranger,
        ancien court (`T-012` : la constante exige 8 chiffres)."""
        refusees = (
            "T-00000001\n",
            f"T-{U_LETTER}\n",
            f"T-{U_LETTER[:-1]}",
            f"T-{U_LETTER}A",
            f"T-0{U_LETTER}",
            f"T-{U_LETTER.lower()}",
            f"t-{U_LETTER}",
            "T-" + U_LETTER[:-1] + "U",
            "T-" + U_LETTER[:-1] + "I",
            f"S-{U_LETTER}",
            "T-012",
            "T-000000001",
            "",
        )
        for tid in refusees:
            with self.subTest(tid=tid):
                self.assertIsNone(kcg._TICKET.match(tid), repr(tid))


class OctroiUlidTests(unittest.TestCase):
    """La constante vue par son SEUL lecteur, `read_grants` : une ligne
    d'octroi pour une tâche `T-<ULID>` est VALIDE, une ligne `T-0<ULID>` est
    IGNORÉE et comptée « malformée » — jamais acceptée en silence."""

    NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    def _grants(self, lignes: list[str]):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            fichier = Path(tmp) / kcg.GRANT_REL
            fichier.parent.mkdir(parents=True)
            fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
            return kcg.read_grants(tmp, now=self.NOW)

    def test_un_octroi_sous_t_ulid_est_valide(self):
        """MUTANT M3 (branche ULID retirée) ⇒ la ligne ULID tombe en « malformée »."""
        valides, ignorees = self._grants([
            f".agents/bin/kit_code_guard.py T-{U_LETTER} 2999-01-01T00:00Z",
            f".agents/bin/specs.py T-{U_DIGIT} 2999-01-01T00:00Z",
            ".agents/bin/ledger.py T-00000001 2999-01-01T00:00Z",
        ])
        self.assertEqual(ignorees, {})
        self.assertEqual(len(valides), 3, valides)

    def test_un_octroi_sous_t_0_ulid_est_ignore_et_compte(self):
        valides, ignorees = self._grants([
            f".agents/bin/kit_code_guard.py T-0{U_LETTER} 2999-01-01T00:00Z",
        ])
        self.assertEqual(valides, [])
        self.assertEqual(ignorees, {"malformée": 1})


if __name__ == "__main__":
    unittest.main()
