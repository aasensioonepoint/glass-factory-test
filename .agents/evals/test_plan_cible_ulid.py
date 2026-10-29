#!/usr/bin/env python3
"""LA CIBLE DE PLAN SOUS LA GRAMMAIRE `P-<ULID>` (T-00001040, étape 4 du plan de T-00000726).

Run: python -m pytest .agents/evals/test_plan_cible_ulid.py -q

Ce que `plan_cible` RECOPIE de la grammaire d'id — `_DECISION` (la 3e valeur d'une
étape), `_TASK_PATTERN` (l'enrôlement d'un plan), la clé d'ÉLECTION de la meilleure
trace d'approbation (`_clef_sid`, à deux étages) — doit lire un `S-<ULID>` / `T-<ULID>`
ENTIER avant que C2 n'en émette. Chez l'adoptant la garde naît ARMÉE en `chantier=*`
(T-1093, R26) : une grammaire restée étroite y IGNORERAIT l'enrôlement de toute tâche
neuve. `cle_de_tache` / `forme_longue` (T-1160, déjà ULID-premier) ne sont PAS édités :
leurs témoins ULID vivent ici, colonne ancrée par `fullmatch`.

UN MODULE FRÈRE, PAS UN AMENDEMENT (E23, cliquet) : `test_plan_cible_guard.py` reste
intact — DÉCLARÉ, non édité — et ce module en hérite l'outillage (`_BaseDone`, un board
jetable par test), comme `test_plan_cible_star.py`.

Fixtures FIXES (réserve B-C8) : UL finit par une LETTRE, UD par un CHIFFRE (`2`), U8
ouvre par HUIT chiffres puis des lettres. Chaque témoin nomme le mutant qu'il tue.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_plan_cible_guard as G  # noqa: E402 — a besoin du chemin inséré ci-dessus

pc = G.pc

UL = "01M3250V003HCPQKTZ8ENYF4VM"
UD = "01M3253WN0W4D0K2S3759WV6M2"
U8 = "01234567ABCDEFGHJKMNPQRSTV"
UE = "01M3250V003HCPQKTZ8ENYF4V9"  # ANTÉRIEUR à UD, queue numérique PLUS GRANDE (9 > 2)
_ULID_SEUL = re.compile(r"[TS]-[0-9A-HJKMNP-TV-Z]{26}")


class GrammaireTests(unittest.TestCase):
    def test_decision_extrait_la_s_id_entiere(self):
        """`_DECISION`, colonne RECHERCHE. MUTANTS : branche ULID retirée ⇒ `S-<UL>` lu
        `S-01` ; ULID en second (M3) ⇒ `S-<U8>` lu `S-01234567` ; numérique retiré (R2)."""
        for sid in (f"S-{UL}", f"S-{UD}", f"S-{U8}", "S-00001558", "S-1"):
            with self.subTest(sid=sid):
                m = pc._DECISION.search(f"   décision pilote: {sid} (raison)")
                self.assertIsNotNone(m, sid)
                self.assertEqual(m.group(1), sid)
        for voisin in (f"S-0{UL}", f"S-{UL}A"):
            with self.subTest(voisin=voisin):
                m = pc._DECISION.search(f"décision pilote: {voisin}")
                self.assertFalse(m and _ULID_SEUL.fullmatch(m.group(1)), voisin)
                self.assertNotEqual(m.group(1) if m else None, voisin)

    def test_task_pattern_extrait_chaque_id_entier(self):
        """`_TASK_PATTERN`, colonne RECHERCHE. MUTANTS : branche ULID retirée ; borne
        `(?![0-9A-Za-z])` retirée (M30b) ⇒ un ULID lu dans `T-<UL>A`."""
        ligne = f"Tâches : T-{UL} · T-012 · T-00000726, T-{U8}"
        self.assertEqual(pc._TASK_PATTERN.findall(ligne), [f"T-{UL}", "T-012", "T-00000726", f"T-{U8}"])
        for voisin in (f"T-0{UL}", f"T-{UL}A"):
            with self.subTest(voisin=voisin):
                lus = pc._TASK_PATTERN.findall(f"Tâches : {voisin}")
                self.assertFalse(any(_ULID_SEUL.fullmatch(x) for x in lus), lus)

    def test_enrolling_line_sur_un_t_ulid(self):
        """MUTANT : branche ULID retirée de `_TASK_PATTERN` ⇒ un roster `T-<ULID>` n'enrôle pas."""
        plan = f"# Plan\nTâches : T-{UL} · T-00000002\n## Steps\n"
        self.assertTrue(pc.enrolling_line(plan, f"T-{UL}"))
        self.assertTrue(pc.enrolling_line(plan, "T-00000002"))
        self.assertFalse(pc.enrolling_line(plan, f"T-{UD}"))
        self.assertFalse(pc.enrolling_line(f"# Plan\nTâches : T-0{UL}\n", f"T-0{UL}"))

    def test_cle_de_tache_ulid_premier_ancree(self):
        """`cle_de_tache` / `forme_longue` (T-1160, NON édités) : témoins de la colonne
        ANCRÉE. Un `T-` + 24 zéros + `12` est un ULID, jamais `T-12`."""
        tout_chiffres = "T-" + "0" * 24 + "12"
        for ref, cle in ((f"T-{UL}", f"T-{UL}"), (f"T-{U8}", f"T-{U8}"), (tout_chiffres, tout_chiffres),
                         ("T-012", "T-12"), ("t-12", "T-12"), ("T-00000012", "T-12")):
            with self.subTest(ref=ref):
                self.assertEqual(pc.cle_de_tache(ref), cle)
        for ref in (f"T-0{UL}", f"T-{UL}A", f"T-{UL.lower()}", f"S-{UL}", "T-١٢"):
            with self.subTest(refuse=ref):
                self.assertIsNone(pc.cle_de_tache(ref))
        self.assertEqual(pc.forme_longue(f"T-{UL}"), f"T-{UL}")
        self.assertEqual(pc.forme_longue("T-12"), "T-00000012")


class ElectionTests(unittest.TestCase):
    """`_meilleure_trace` (SYM-09000) élit la plus RÉCENTE trace d'approbation valide par
    `_clef_sid` : tout `S-<ULID>` après tout ancien, les ULID entre eux par le temps."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.d = Path(self._tmp.name)
        (self.d / "plans").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _trace(self, sid: str, rel: str) -> dict:
        p = self.d / rel
        p.write_text(f"# {rel}\n", encoding="utf-8")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        return {"id": sid, "task": "T-00000001", "kind": "decision", "title": "plan approuvé",
                "text": f"plan={rel} sha256={sha}"}

    def test_clef_sid_deux_etages(self):
        self.assertEqual(pc._clef_sid(f"S-{UL}"), (1, UL))
        self.assertEqual(pc._clef_sid("S-00002000"), (0, 2000))
        self.assertEqual(pc._clef_sid("S-1"), (0, 1))
        self.assertLess(pc._clef_sid("S-99999999"), pc._clef_sid(f"S-{UD}"))
        self.assertLess(pc._clef_sid(f"S-{UL}"), pc._clef_sid(f"S-{UD}"))
        self.assertLess(pc._clef_sid("pas une S-id"), pc._clef_sid("S-1"))

    def test_un_s_ulid_posterieur_gagne_contre_un_ancien(self):
        """MUTANT M10 : SYM-09000 sur `_num_sid` brut ⇒ `S-<UD>` vaut 2 < 2000, le plan
        ANCIEN est élu à tort."""
        ancien = self._trace("S-00002000", "plans/ancien.md")
        neuf = self._trace(f"S-{UD}", "plans/neuf.md")
        for ordre in ([ancien, neuf], [neuf, ancien]):
            with self.subTest(premier=ordre[0]["id"]):
                chemin, sid = pc._meilleure_trace(self.d, ordre)
                self.assertEqual((chemin.name, sid), ("neuf.md", f"S-{UD}"))

    def test_deux_s_ulid_le_plus_recent_gagne(self):
        """MUTANT : étage ULID comparé par chiffres de queue ⇒ l'ANTÉRIEUR `S-<UE>`
        (queue 9) bat le POSTÉRIEUR `S-<UD>` (queue 2), rouge."""
        tot = self._trace(f"S-{UE}", "plans/tot.md")
        tard = self._trace(f"S-{UD}", "plans/tard.md")
        self.assertLess(UE, UD)  # filet à vide : UE est bien antérieur
        for ordre in ([tard, tot], [tot, tard]):
            with self.subTest(premier=ordre[0]["id"]):
                chemin, sid = pc._meilleure_trace(self.d, ordre)
                self.assertEqual((chemin.name, sid), ("tard.md", f"S-{UD}"))


class PertinenceTests(unittest.TestCase):
    def test_une_decision_s_ulid_tracee_sur_la_tache_est_pertinente(self):
        """MUTANT : branche ULID retirée de `_DECISION` ⇒ la citation est lue `S-01`,
        la décision tracée `S-<UL>` est ÉCARTÉE."""
        plan = f"# Plan\nTâches : T-00000001\n## Steps\n1. une\n   décision pilote: S-{UL}\n"
        entrees = [{"id": f"S-{UL}", "task": "T-00000001", "kind": "decision", "title": "d", "text": ""}]
        taches = [{"id": "T-00000001", "state": "pending", "task": "x"}]
        self.assertEqual(pc.decisions_pertinentes(entrees, taches, plan, tid="T-00000001"), {f"S-{UL}"})
        self.assertEqual(pc.etapes_fautives(plan, set(), {f"S-{UL}"}), [])


class EnrolementCliTests(G._BaseDone):
    """De bout en bout, `tasks.py done` sous la garde ARMÉE. L'enrôlement ne mord
    qu'en R2 (une trace PROPRE est élue en R1 sans lui) : une tâche `T-<ULID>` sans
    trace propre se ferme en EMPRUNTANT le plan du slot `running` du même chantier
    SI ce plan la nomme par `Tâches : T-<ULID>` — le régime du slot T-012 (R-SLOT)
    qui fermera chaque tâche neuve après C2 —, sous un chantier NOMMÉ et sous
    `chantier=*` (R26, graine de l'adoptant)."""

    def _tache_ulid(self, chantier: str | None) -> str:
        """Une tâche `T-<ULID>` au board, avant que C2 n'en émette : créée par `new`,
        puis son id réécrit à ses DEUX places (la tâche et sa corrélation de pont) —
        fixture d'ENTRÉE, jamais une allocation."""
        legacy = self.new(chantier=chantier)
        board = self.d / ".agents" / "state" / "board" / "TASKS.json"
        data = json.loads(board.read_text(encoding="utf-8"))
        touches = 0
        for t in data["tasks"]:
            if t["id"] == legacy:
                t["id"], touches = f"T-{UL}", touches + 1
        for c in (data.get("sync_correlations") or {}).values():
            if c.get("board_task_id") == legacy:
                c["board_task_id"] = f"T-{UL}"
        self.assertEqual(touches, 1, data)
        board.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        return f"T-{UL}"

    def _emprunt(self, chantier: str | None, roster: str):
        """`sub` = T-<UL> sans trace propre ; `slot` `running` du même chantier, dont
        la trace `plan approuvé` vise un plan au roster `roster`. Rend `(sub, slot, r)`."""
        sub = self._tache_ulid(chantier)
        slot = self.new(chantier=chantier)
        sha = self.ecrire_plan("plans/slot_ulid.md", self.PLAN_SLOT_ENROLE.format(sub=roster))
        self.ecrire_specs([self.decision("S-00001558", slot),
                           self.trace("S-00002000", slot, "plans/slot_ulid.md", sha)])
        self.armer(chantier=chantier or "*")
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        return sub, slot, self.done(sub)

    def test_t_ulid_enrole_par_le_slot_sous_chantier_nomme(self):
        """MUTANT : branche ULID retirée de `_TASK_PATTERN` ⇒ le roster est lu `T-01`,
        R2 écarte le plan du slot, refus « aucun plan approuvé »."""
        sub, slot, r = self._emprunt(self.CHANTIER, f"T-{UL}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"[cible relevée sur {slot} : slot_ulid.md (S-00002000)]", self.board_stage(sub))

    def test_t_ulid_enrole_par_le_slot_sous_chantier_etoile(self):
        """R26 : la graine de l'adoptant (`chantier=*`). Même mutant."""
        sub, slot, r = self._emprunt(None, f"T-{UL}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"[cible relevée sur {slot} : slot_ulid.md (S-00002000)]", self.board_stage(sub))

    def test_contre_temoin_le_slot_nomme_un_autre_ulid(self):
        """Contrôle NÉGATIF : le roster du slot nomme un AUTRE ULID ⇒ refus nommé (la
        garde ne s'est pas relâchée en s'élargissant ; borne d'égalité EXACTE)."""
        sub, _slot, r = self._emprunt(self.CHANTIER, f"T-{UD}")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"n'enrôle pas {sub}", r.stderr)

    def test_etape_citant_une_decision_s_ulid(self):
        """MUTANT : branche ULID retirée de `_DECISION` ⇒ étape sans cible valide, refus."""
        tid = self.new()
        plan = (f"# Plan\nTâches : {tid}\n## Steps\n1. étape une\n   décision pilote: S-{UL}\n"
                f"2. étape deux\n   décision pilote: S-{UL}\n")
        sha = self.ecrire_plan("plans/ulid.md", plan)
        self.ecrire_specs([self.decision(f"S-{UL}", tid),
                           self.trace("S-00002000", tid, "plans/ulid.md", sha)])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
