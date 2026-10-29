"""`night_approve.py` sous la grammaire `P-<ULID>` (T-00001040, étape 4 du plan de T-00000726).

UN MODULE FRÈRE (E23, cliquet) : `test_night_approve.py` est au plafond du cliquet de
taille ; il ne reçoit que les élargissements E4 EN PLACE. Ce frère porte les témoins
NEUFS, avec le même patron d'import que son aîné (import direct : pytest insère le
dossier de ce fichier dans `sys.path`). Racines jetables : aucun magasin suivi touché.

Ce qu'il tient : (1) chaque constante RECOPIÉE en deux colonnes — ANCRÉE (`TASK_ID_EXACT`,
`DELIVERED_ID`) et RECHERCHE (`TASK_PATTERN`, `VERDICT_ID`) — sur les fixtures FIXES de la
réserve B-C8 ; (2) `_same_task` : deux ULID par CHAÎNE, deux anciens par NOMBRE, MIXTE
faux ; (3) les CINQ sites qui ordonnaient ou comparaient par `specs.numeric_id` (S-00004585,
réserve C2 de S-00004589) n'y passent plus — un témoin par site : les quatre qui ORDONNENT par
`specs.sort_key`, `_same_task`, qui COMPARE, par `specs.identity_key` (bb50be4e).

MUTANTS (chacun rougit au moins le témoin qui le nomme) :
  M3     ULID posé en SECOND dans une constante de recherche ⇒ `T-<U8>` / `S-<U8>` coupé
  M16    un des cinq sites revenu à `specs.numeric_id` (:469, :679, :702, :799, :820)
  M23    branche ULID retirée de `_same_task` ⇒ marqueur sous `T-<ULID>` ignoré
  M23m   « ULID seulement si les DEUX le sont, sinon numérique » ⇒ MIXTE vrai
  M8'    `\\A…\\Z` revenu à `^…$` ⇒ `"T-00000001\\n"` accepté
  R2-R4  numérique retiré / `(?i)` / branche numérique élargie ⇒ colonne rouge
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import night_approve
import specs

U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"  # corps qui finit par une LETTRE (numeric_id lève)
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"   # finit par 2 : numeric_id le lit 2, comme S-00000002
U8 = "01234567ABCDEFGHJKMNPQRSTV"        # HUIT chiffres puis des lettres
PLAN_REL = "docs/tasks/LOT-X-plan.md"


def _entree(sid: str, kind: str, title: str, text: str = "", task: str = "T-00000001") -> dict:
    return {"id": sid, "task": task, "kind": kind, "title": title, "text": text}


class ConstantesTests(unittest.TestCase):
    def test_task_pattern_recherche(self):
        """TASK_PATTERN (roster). MUTANTS M3, branche ULID retirée, borne retirée."""
        ligne = f"Tâches : T-{U_LETTER} · T-00000001, T-{U8}"
        self.assertEqual(night_approve.TASK_PATTERN.findall(ligne),
                         [f"T-{U_LETTER}", "T-00000001", f"T-{U8}"])
        for voisin in (f"T-0{U_LETTER}", f"T-{U_LETTER}A", "T-000002099", "T-012"):
            with self.subTest(voisin=voisin):
                lus = night_approve.TASK_PATTERN.findall(f"Tâches : {voisin}")
                self.assertNotIn(voisin, lus)
                self.assertFalse(any(len(x) == 28 for x in lus), lus)

    def test_task_id_exact_ancree(self):
        """TASK_ID_EXACT (`--lot`). MUTANTS M8', R3, R4 (`\\d{8}` → `\\d+`)."""
        for tid in (f"T-{U_LETTER}", f"T-{U8}", "T-00000001"):
            with self.subTest(tid=tid):
                self.assertIsNotNone(night_approve.TASK_ID_EXACT.match(tid))
        for tid in ("T-00000001\n", f"T-{U_LETTER}\n", f"T-0{U_LETTER}", f"T-{U_LETTER.lower()}",
                    "T-012", "T-000000001", f"S-{U_LETTER}"):
            with self.subTest(refuse=tid):
                self.assertIsNone(night_approve.TASK_ID_EXACT.match(tid), repr(tid))

    def test_delivered_id_ancree_court_compris(self):
        """DELIVERED_ID (`--delivered`) : l'ancien COURT reste admis. MUTANTS M8', R1-R4."""
        for tid in (f"T-{U_LETTER}", f"T-{U8}", "T-00000848", "T-848"):
            with self.subTest(tid=tid):
                self.assertIsNotNone(night_approve.DELIVERED_ID.match(tid))
        for tid in ("T-848\n", f"T-{U_LETTER}\n", f"T-0{U_LETTER}", f"T-{U_LETTER.lower()}", "T-", "T-8a"):
            with self.subTest(refuse=tid):
                self.assertIsNone(night_approve.DELIVERED_ID.match(tid), repr(tid))

    def test_verdict_id_recherche_lit_l_id_ecrit(self):
        """VERDICT_ID lit l'id que `specs.add_entry` rend après `--apply` (`written_id`).
        MUTANTS M3 (`S-<U8>` coupé à `S-01234567`), branche ULID retirée (`S-01`)."""
        for sid in (f"S-{U_LETTER}", f"S-{U8}", "S-00004589", "S-1"):
            with self.subTest(sid=sid):
                m = night_approve.VERDICT_ID.search(f"SPECS: {sid} added (decision)")
                self.assertEqual(m.group(0), sid)
        for voisin in (f"S-0{U_LETTER}", f"S-{U_LETTER}A"):
            with self.subTest(voisin=voisin):
                m = night_approve.VERDICT_ID.search(f"SPECS: {voisin} added")
                self.assertNotEqual(m.group(0) if m else None, voisin)
                self.assertNotEqual(len(m.group(0)) if m else 0, 28)


class MemeTacheTests(unittest.TestCase):
    def test_deux_ulid_par_chaine(self):
        """MUTANT M23 (branche ULID retirée) ⇒ un ULID n'est plus lui-même."""
        self.assertTrue(night_approve._same_task(f"T-{U_LETTER}", f"T-{U_LETTER}"))
        self.assertTrue(night_approve._same_task(f"T-{U_DIGIT}", f"T-{U_DIGIT}"))
        self.assertFalse(night_approve._same_task(f"T-{U_LETTER}", f"T-{U_DIGIT}"))

    def test_mixte_jamais_la_meme_tache(self):
        """MUTANTS M23m et M16 (:679 sur `numeric_id`) : `T-<U_DIGIT>` vaudrait T-00000002."""
        self.assertFalse(night_approve._same_task(f"T-{U_DIGIT}", "T-00000002"))
        self.assertFalse(night_approve._same_task("T-00000002", f"T-{U_DIGIT}"))
        self.assertFalse(night_approve._same_task(f"T-{U_DIGIT}", "T-2"))

    def test_anciens_par_nombre_et_formes_malformees(self):
        self.assertTrue(night_approve._same_task("T-848", "T-00000848"))
        for a, b in ((f"T-0{U_LETTER}", f"T-0{U_LETTER}"), (f"S-{U_LETTER}", f"S-{U_LETTER}"),
                     (None, "T-00000001"), (f"T-{U_LETTER}\n", f"T-{U_LETTER}")):
            with self.subTest(a=a, b=b):
                self.assertFalse(night_approve._same_task(a, b))


class SitesSortKeyTests(unittest.TestCase):
    """Un témoin par site M16. Un `S-<ULID>` est POSTÉRIEUR à tout ancien ; sous
    `numeric_id`, `S-<U_DIGIT>` vaudrait 2 (ordre faux) et `S-<U_LETTER>` lèverait."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_469_le_dernier_verdict_plan_critic_est_le_ulid(self):
        for neuf in (f"S-{U_DIGIT}", f"S-{U_LETTER}"):
            with self.subTest(neuf=neuf):
                entrees = [
                    _entree("S-00004589", "verdict", "plan-critic GO", f"plan={PLAN_REL}"),
                    _entree(neuf, "verdict", "plan-critic NO_GO", f"plan={PLAN_REL}"),
                ]
                v = night_approve.latest_verdict_for_plan(self.root, entrees, PLAN_REL)
                self.assertEqual(v["id"], neuf)

    def test_702_un_effacement_ulid_posterieur_leve_le_marqueur(self):
        for neuf in (f"S-{U_DIGIT}", f"S-{U_LETTER}"):
            with self.subTest(neuf=neuf):
                livre = _entree("S-00000500", "decision", night_approve.NIGHT_DELIVERED_TITLE)
                efface = _entree(neuf, "decision", night_approve.NIGHT_DELIVERED_CLEARED_TITLE)
                self.assertIsNone(night_approve.active_night_delivered([livre, efface], "T-00000001"))
                # et l'inverse : une livraison ULID APRÈS un effacement ancien re-arme
                efface_ancien = _entree("S-00000500", "decision", night_approve.NIGHT_DELIVERED_CLEARED_TITLE)
                livre_neuf = _entree(neuf, "decision", night_approve.NIGHT_DELIVERED_TITLE)
                actif = night_approve.active_night_delivered([efface_ancien, livre_neuf], "T-00000001")
                self.assertEqual(actif["id"], neuf)

    def test_702_un_marqueur_sous_t_ulid_est_lu(self):
        """MUTANT M23 : le marqueur journalé sous `T-<ULID>` serait ignoré."""
        livre = _entree("S-00000500", "decision", night_approve.NIGHT_DELIVERED_TITLE, task=f"T-{U_LETTER}")
        actif = night_approve.active_night_delivered([livre], f"T-{U_LETTER}")
        self.assertEqual(actif["id"], "S-00000500")
        self.assertIsNone(night_approve.active_night_delivered([livre], "T-00000001"))

    def test_799_la_derniere_paire_est_le_ulid(self):
        for neuf in (f"S-{U_DIGIT}", f"S-{U_LETTER}"):
            with self.subTest(neuf=neuf):
                entrees = [
                    _entree("S-00000500", "verdict", "T-00000001 itération 2/8 : paire GO / GO"),
                    _entree(neuf, "verdict", "T-00000001 itération 3/8 : paire NO_GO / GO"),
                ]
                self.assertEqual(night_approve.latest_pair_verdict_for_task(entrees, "T-00000001")["id"], neuf)

    def test_820_une_paire_ulid_posterieure_au_verdict_refuse(self):
        verdict = _entree("S-00004589", "verdict", "plan-critic GO", f"plan={PLAN_REL}")
        for neuf in (f"S-{U_DIGIT}", f"S-{U_LETTER}"):
            with self.subTest(neuf=neuf):
                paire = _entree(neuf, "verdict", "T-00000001 itération 3/8 : paire NO_GO / GO")
                self.assertIsNotNone(night_approve.condition_pair_form(paire, verdict, PLAN_REL))
                # l'inverse : un verdict ULID postérieur à une paire ancienne passe
                paire_ancienne = _entree("S-00000500", "verdict", "T-00000001 itération 2/8 : paire GO / GO")
                verdict_neuf = _entree(neuf, "verdict", "plan-critic GO", f"plan={PLAN_REL}")
                self.assertIsNone(night_approve.condition_pair_form(paire_ancienne, verdict_neuf, PLAN_REL))


class FonctionnelTests(unittest.TestCase):
    def test_roster_enrole_un_t_ulid(self):
        plan = f"# PLAN — LOT X\n\nTâches : T-{U_LETTER} · T-00000002\n\nCorps qui cite T-{U_DIGIT}.\n"
        self.assertIsNone(night_approve.condition_roster(plan, f"T-{U_LETTER}"))
        self.assertIsNotNone(night_approve.condition_roster(plan, f"T-{U_DIGIT}"))

    def test_lot_accepte_un_t_ulid(self):
        lots = night_approve.parse_lots([["docs/tasks/LOT-X-plan.md", f"T-{U_LETTER}", "T-00000002"]])
        self.assertEqual(lots[0].tasks, [f"T-{U_LETTER}", "T-00000002"])
        with self.assertRaises(night_approve.NightApproveError):
            night_approve.parse_lots([["docs/tasks/LOT-X-plan.md", f"T-0{U_LETTER}"]])

    def test_delivered_sous_t_ulid_de_bout_en_bout(self):
        """`--delivered T-<ULID>` : DELIVERED_ID, `_same_task` et le site :702 ensemble."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = specs.store_path(tmp)
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(json.dumps({"next_id": 501, "entries": [
                {"id": "S-00000500", "task": f"T-{U_LETTER}", "kind": "decision",
                 "title": night_approve.NIGHT_DELIVERED_TITLE, "text": "", "date": "2026-10-08"},
            ]}), encoding="utf-8")
            rc, lignes = night_approve.delivered_report(tmp, [f"T-{U_LETTER}", "T-00000002"])
            self.assertEqual(rc, night_approve.DELIVERED_IN_FORCE, lignes)
            self.assertTrue(any(f"T-{U_LETTER}" in ligne and "S-00000500" in ligne for ligne in lignes), lignes)


if __name__ == "__main__":
    unittest.main()
