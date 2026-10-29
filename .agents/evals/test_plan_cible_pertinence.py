#!/usr/bin/env python3
"""LE VERROU DE CIBLE, BANC FRÈRE — contrat rc de `cible-check`, pertinence de
la 3e valeur, résolution R2 sur un plan de lot.

Frère de `test_plan_cible_guard.py`, qui approche la borne des 1600 lignes : les
témoins NEUFS vivent ici, même chargement de `plan_cible` (`sys.modules` AVANT
`exec_module`), mêmes fixtures dans un répertoire temporaire RÉEL, ZÉRO appel LLM.

*** CHAQUE TÉMOIN PORTE SON MUTANT. *** Le docstring de chaque test nomme la
MUTATION du code réel qui doit le faire rougir.

Ce banc N'EST PAS strippé : son sujet — `plan_cible.py` et la CLI `tasks.py` —
VOYAGE.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
TASKS = BIN / "tasks.py"


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pc = _charger("plan_cible", BIN / "plan_cible.py")


class _Base(unittest.TestCase):
    CHANTIER = "refonte-packaging"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "specs"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        (self.d / "plans").mkdir()
        (self.d / "spec.md").write_text("**« un invariant »**\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def tasks(self, *args: str, timeout: int = 120):
        return subprocess.run(
            [sys.executable, str(TASKS), "--root", str(self.d), *args],
            capture_output=True, text=True, timeout=timeout)

    def armer(self, chantier: str = CHANTIER, spec_rel: str = "spec.md",
              contenu: str | None = None):
        m = self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED"
        if contenu is None:
            contenu = f"spec={spec_rel}\nchantier={chantier}\n"
        m.write_text(contenu, encoding="utf-8")

    def ecrire_plan(self, rel: str, contenu: str) -> str:
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenu, encoding="utf-8")
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def ecrire_specs(self, entrees: list[dict]):
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 99999, "entries": entrees}, ensure_ascii=False),
            encoding="utf-8")


# ===========================================================================
# T-00000814 — `cible-check` : rc 1 veut dire « étapes sans cible », RIEN d'autre.
# ===========================================================================
class CibleCheckContratRcTests(_Base):
    PLAN_ANNOTE = "## Steps\n1. une étape\n   angle mort: une question ?\n"

    def _sans_trace_rc2(self, r, attendu: str):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("cible-check:", r.stderr)
        self.assertIn(attendu, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "un refus rc 2 va sur STDERR")

    def test_marqueur_malforme_sans_spec_refus_rc2_nomme(self):
        """Mesuré à la base : `cible-check <plan>` sans `--spec`, sous un marqueur
        malformé OU ambigu, sortait en TRACE `plan_cible.CibleError` avec rc 1 —
        la valeur que le contrat 0/1/2 réserve à « étapes sans cible ». MUTANT :
        retirer le `try/except CibleError` autour de `lire_marqueur` dans
        `cible_check`."""
        self.ecrire_plan("plans/p.md", self.PLAN_ANNOTE)
        cas = (("ceci n'est pas un marqueur valide\n", "malformé"),
               ("spec=spec.md\nspec=b.md\nchantier=x\n", "ambigu"))
        for contenu, attendu in cas:
            with self.subTest(attendu=attendu):
                self.armer(contenu=contenu)
                self._sans_trace_rc2(self.tasks("cible-check", "plans/p.md"),
                                     attendu)

    def test_plan_ou_spec_non_utf8_refus_rc2_nomme(self):
        """Défaut voisin mesuré sur le même chemin : un plan ou une spec non UTF-8
        levait `UnicodeDecodeError` (une `ValueError`, que `except OSError` ne
        rattrape pas) → TRACE, rc 1. MUTANT : ramener l'un des deux `except` de
        `cible_check` à `OSError` seul."""
        self.ecrire_plan("plans/p.md", self.PLAN_ANNOTE)
        (self.d / "plans" / "latin1.md").write_bytes(
            "## Steps\n1. une étape\n".encode("latin-1"))
        (self.d / "latin1.md").write_bytes(b"**\xab un invariant \xbb**\n")
        cas = (("plans/latin1.md", "spec.md", "plan illisible"),
               ("plans/p.md", "latin1.md", "spec illisible"))
        for plan, spec, attendu in cas:
            with self.subTest(plan=plan, spec=spec):
                self._sans_trace_rc2(
                    self.tasks("cible-check", plan, "--spec", spec), attendu)

    def test_specs_non_utf8_refus_rc2_nomme(self):
        """critic-opus F4 : un SPECS.json non UTF-8 levait `UnicodeDecodeError`
        dans `entrees_specs`, que son `except OSError` laissait filer → TRACE,
        rc 1, lue « étapes sans cible ». Appel direct PUIS câblage CLI. MUTANT :
        ramener l'`except` de lecture d'`entrees_specs` à `OSError` seul."""
        self.ecrire_plan("plans/p.md", self.PLAN_ANNOTE)
        self.armer()
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_bytes(b"\xff")
        rc, msg = pc.cible_check(self.d, "plans/p.md", None)
        self.assertEqual(rc, 2, msg)
        self.assertIn("SPECS.json présent mais illisible", msg)
        self._sans_trace_rc2(self.tasks("cible-check", "plans/p.md"), "SPECS.json")

    def test_marqueur_bien_forme_rc0_polarite(self):
        """POLARITÉ : sans elle, un rc 2 inconditionnel satisferait les deux
        témoins ci-dessus. Marqueur bien formé, plan annoté → rc 0 sur STDOUT."""
        self.ecrire_plan("plans/p.md", self.PLAN_ANNOTE)
        self.armer()
        r = self.tasks("cible-check", "plans/p.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("toutes les étapes", r.stdout)


# ===========================================================================
# T-00000910 — R2 sur un plan de lot ANNOTÉ du slot du chantier, à la forme de
# T-012 : id court `T-012` au board, tâche membre à 8 chiffres, titres
# `### Étape`, trace `plan approuvé` portée par le slot. Relevé rejoué à la base
# d217df15 : le CODE accepte déjà ce plan (constat) ; ce qui rend R2
# inutilisable sur le board réel est l'ABSENCE de toute trace d'approbation
# sur T-012 (0 sur 184 entrées), une donnée que seul l'orchestrateur écrit.
# Ces témoins tiennent la non-régression du chemin qu'il empruntera.
# ===========================================================================
class R2PlanDeLotTests(_Base):
    SLOT = "T-012"
    MEMBRE = "T-00000814"
    PLAN = "docs/tasks/LOT-T012-plan.md"
    LOT = (
        "# Plan de lot du slot T-012\n"
        "Tâches : T-00000814, T-00000909\n"
        "### Étape A — première\n"
        "cible: « un invariant »\n"
        "### Étape B — seconde\n"
        "{b}\n"
    )

    def _poser(self, b: str = "angle mort: faut-il découper ?",
               etat_slot: str = "running") -> dict:
        sha = self.ecrire_plan(self.PLAN, self.LOT.format(b=b))
        self.ecrire_specs([{
            "id": "S-00002000", "task": self.SLOT, "kind": "decision",
            "title": "plan approuvé", "text": f"plan={self.PLAN} sha256={sha}",
            "date": "2026-10-04"}])
        self.armer()
        return {"tasks": [
            {"id": self.SLOT, "state": etat_slot, "chantier": self.CHANTIER},
            {"id": self.MEMBRE, "state": "pending", "chantier": self.CHANTIER},
        ]}

    def test_R2_accepte_le_plan_de_lot_annote_du_slot(self):
        """MUTANT : R2 désactivé (`resoudre_plan` rend `None` après R1, ou
        `evaluer_done` passe `slot=False`). Le `done` du membre PASSE et la note
        d'emprunt NOMME le slot, le plan et la trace."""
        refus, note = pc.evaluer_done(self.d, self.MEMBRE, self._poser())
        self.assertIsNone(refus, refus)
        self.assertEqual(
            note, f"[cible relevée sur {self.SLOT} : LOT-T012-plan.md (S-00002000)]")

    def test_R2_controle_les_etapes_du_plan_de_lot(self):
        """POLARITÉ — l'emprunt n'est pas un laissez-passer. MUTANT : sauter le
        contrôle des étapes quand la note d'emprunt est posée (`if fautives and
        not note`). Une étape sans cible du plan de lot fait refuser le membre."""
        refus, note = pc.evaluer_done(
            self.d, self.MEMBRE, self._poser(b="juste de la prose"))
        self.assertIsNotNone(refus)
        self.assertIn("Étape B", refus)
        self.assertIn(f"[cible relevée sur {self.SLOT}", refus)
        self.assertEqual(note, "")

    def test_R2_exige_un_slot_running(self):
        """POLARITÉ — MUTANT : filtre `state == running` retiré du vivier R2. Un
        slot `pending` ne prête pas son plan : refus R3 à la cause nommée."""
        refus, _note = pc.evaluer_done(
            self.d, self.MEMBRE, self._poser(etat_slot="pending"))
        self.assertIsNotNone(refus)
        self.assertIn("aucun plan approuvé", refus)
        self.assertIn("ni pour un slot `running`", refus)


# ===========================================================================
# T-00001160 — R1/R2 lisent une trace écrite sous une AUTRE graphie du MÊME id
# (`T-012` ≡ `T-00000012`), et RIEN d'autre (décision pilote S-00004060).
# Mesuré à la base : la trace `plan approuvé` posée sous `T-00000012` pour le
# slot `T-012` était ignorée, et le refus annonçait FAUX « aucune trace
# d'approbation » ; 9 des 184 entrées réelles de T-012 sont sous `T-00000012`.
# ===========================================================================
class GraphieDesIdsTests(_Base):
    SLOT = "T-012"
    MEMBRE = "T-00000814"
    PLAN = "docs/tasks/LOT-T012-plan.md"
    ROSTER = "T-00000814, T-00000909"
    # 26 symboles Crockford : un ULID, que le motif legacy lirait `T-12`.
    ULID = "T-" + "0" * 24 + "12"

    def _poser(self, trace_sous: str, *, roster: str = ROSTER, sha: str = "",
               b: str = "angle mort: faut-il découper ?",
               sur_disque: bool = False) -> dict:
        lot = R2PlanDeLotTests.LOT.format(b=b).replace(self.ROSTER, roster)
        vrai = self.ecrire_plan(self.PLAN, lot)
        self.ecrire_specs([{
            "id": "S-00002000", "task": trace_sous, "kind": "decision",
            "title": "plan approuvé", "text": f"plan={self.PLAN} sha256={sha or vrai}",
            "date": "2026-10-04"}])
        self.armer()
        data = {"tasks": [
            {"id": self.SLOT, "state": "running", "chantier": self.CHANTIER},
            {"id": self.MEMBRE, "state": "pending", "chantier": self.CHANTIER},
        ]}
        if sur_disque:
            (self.d / ".agents" / "state" / "board" / "TASKS.json").write_text(
                json.dumps(data), encoding="utf-8")
        return data

    def test_cle_de_tache_equivaut_les_graphies_du_meme_id_seulement(self):
        """MUTANTS : `cle_de_tache` rendue identité (aucune équivalence) ; motif
        legacy essayé AVANT le motif ULID (l'ULID à 24 zéros vaudrait `T-12`) ;
        une chaîne non conforme rendue telle quelle au lieu de `None`."""
        cle = pc.cle_de_tache
        self.assertEqual(cle("T-012"), cle("T-00000012"))
        self.assertEqual(cle("T-12"), cle("t-00000012"))
        self.assertNotEqual(cle("T-00000013"), cle("T-012"))
        self.assertEqual(cle(self.ULID), self.ULID)
        for brut in ("T-0x12", "12", "S-00000012", "T-12a", "T-", "", None):
            with self.subTest(brut=brut):
                self.assertIsNone(cle(brut))

    def test_cle_de_tache_refuse_les_chiffres_non_ascii(self):
        """Avis sécurité S-00004067 n° 1 : `\\d` acceptait les chiffres Unicode,
        et `int()` les convertit — `T-١٢` (arabe-indien) et `T-１２` (pleine
        chasse) valaient `T-12` (mesuré). MUTANT : `[0-9]` de `_ID_LEGACY`
        ramené à `\\d`. POLARITÉ : la graphie ASCII reste lue."""
        for brut in ("T-١٢", "T-１２", "T-1٢", "T-0١٢"):
            with self.subTest(brut=ascii(brut)):
                self.assertIsNone(pc.cle_de_tache(brut))
                self.assertFalse(pc.meme_tache(brut, "T-12"))
        self.assertEqual(pc.cle_de_tache("T-012"), "T-12")

    def test_R2_lit_la_trace_du_slot_sous_la_graphie_longue(self):
        """Relevé de la tâche : trace sous `T-00000012`, slot `T-012`. MUTANT :
        `a_lui` ramené à `e.get("task") == autre["id"]`."""
        refus, note = pc.evaluer_done(self.d, self.MEMBRE, self._poser("T-00000012"))
        self.assertIsNone(refus, refus)
        self.assertEqual(
            note, f"[cible relevée sur {self.SLOT} : LOT-T012-plan.md (S-00002000)]")

    def test_R1_lit_la_trace_de_la_tache_sous_une_autre_graphie(self):
        """R1 au `done` puis au `start`, dans les DEUX sens (board court / trace
        longue, board long / trace courte). MUTANT : `a_moi` ramené à
        `e.get("task") == tid`."""
        for tache, trace_sous in (("T-00000814", "T-814"), ("T-00000814", "T-0814"),
                                  ("T-012", "T-00000012")):
            with self.subTest(tache=tache, trace=trace_sous):
                data = self._poser(trace_sous)
                refus, note = pc.evaluer_done(self.d, tache, data)
                self.assertIsNone(refus, refus)
                self.assertEqual(note, "", "R1 n'emprunte rien")
                data = self._poser(trace_sous, b="juste de la prose")
                refus = pc.refus_au_start(self.d, tache, data)
                self.assertIsNotNone(refus, "R1 au start : la trace résout le plan")
                self.assertIn("Étape B", refus)

    def test_R3_nomme_la_cause_d_une_trace_sous_une_autre_graphie(self):
        """Le diagnostic ne dit plus FAUX « aucune trace ». MUTANTS : l'un des
        deux filtres de `_cause_r3` ramené à l'égalité exacte."""
        refus = pc.refus_au_done(self.d, self.MEMBRE,
                                 self._poser("T-00000012", roster="T-00000909"))
        self.assertIn(f"n'enrôle pas {self.MEMBRE}", refus)
        self.assertNotIn("aucune trace d'approbation", refus)
        refus = pc.refus_au_done(self.d, self.MEMBRE,
                                 self._poser("T-814", sha="0" * 64))
        self.assertIn("empreinte divergente", refus)

    def test_verdict_mord_sous_une_autre_graphie_de_la_tache(self):
        """Trouvé au balayage : la jambe verdict reçoit l'id tel que `specs.py
        add --task` l'a reçu (`T-\\d+`), et `chantier_de_tache` le comparait au
        board à l'égalité exacte — `--task T-814` laissait passer, INERTE, un
        verdict GO sur un plan incomplet de T-00000814. MUTANT : la comparaison
        de `chantier_de_tache` ramenée à `t.get("id") == tid`."""
        self._poser("T-00000814", b="juste de la prose", sur_disque=True)
        args = ("verdict", "plan-critic it.1 : GO", f"plan={self.PLAN}")
        refus = pc.refus_au_verdict(self.d, "T-814", *args)
        self.assertIsNotNone(refus, "verdict sous T-814 : la jambe doit mordre")
        self.assertIn("Étape B", refus)
        self.assertIsNone(pc.refus_au_verdict(self.d, "T-815", *args),
                          "POLARITÉ : une tâche ABSENTE du board reste inerte")

    def test_contre_temoins_un_autre_id_un_ulid_une_graphie_non_conforme(self):
        """POLARITÉ — la normalisation n'élargit rien d'autre. MUTANTS : motif
        legacy essayé avant le motif ULID, ou comparaison par la valeur
        numérique de FIN de chaîne (l'ULID vaudrait alors `T-12`). Chaque trace
        reste celle d'une AUTRE tâche : refus R3."""
        for trace_sous in ("T-00000013", self.ULID, "T-0x12"):
            with self.subTest(trace=trace_sous):
                refus, _note = pc.evaluer_done(self.d, self.MEMBRE,
                                               self._poser(trace_sous))
                self.assertIsNotNone(refus)
                self.assertIn("aucune trace d'approbation", refus)


# ===========================================================================
# T-00000909 — PERTINENCE de `décision pilote: S-…` (décision pilote S-00004057,
# option B) : la décision porte sur la tâche contrôlée, sur une tâche de son
# chantier NOMMÉ, ou sur une tâche que le plan ENRÔLE. Sonde à la base : une
# S- tracée sur une tâche d'un AUTRE chantier, non enrôlée, validait l'étape
# (rc 0). Chaque branche est ISOLÉE : son mutant ne peut pas être masqué par une
# autre. Les trois jambes (done, start, verdict) sont jouées à chaque cas.
# ===========================================================================
class PertinenceDecisionTests(_Base):
    TACHE = "T-00000909"
    VOISINE = "T-00000910"      # même chantier, jamais enrôlée
    ENROLEE = "T-00000500"      # sans chantier
    ETRANGERE = "T-00000600"    # autre chantier
    PURGEE = "T-00000700"       # au journal, ABSENTE du board (close puis purgée)
    PLAN = "docs/tasks/T-00000909-plan.md"
    DECISIONS = {"S-00000101": TACHE, "S-00000102": VOISINE,
                 "S-00000103": ENROLEE, "S-00000104": ETRANGERE,
                 "S-00000106": PURGEE}
    ECARTEES = "Décisions citées qui existent mais"

    def _poser(self, sid: str, *, roster: str, star: bool = False,
               sous: dict | None = None) -> dict:
        # Ligne 1 SANS id : seul le roster enrôle.
        plan = (f"# Plan de banc\nTâches : {roster}\n"
                f"### Étape A — une\ndécision pilote: {sid}\n"
                f"### Étape B — deux\nangle mort: faut-il découper ?\n")
        sha = self.ecrire_plan(self.PLAN, plan)
        entrees = [{"id": s, "task": (sous or {}).get(s, t), "kind": "decision",
                    "title": "une décision", "text": "", "date": "2026-10-04"}
                   for s, t in self.DECISIONS.items()]
        entrees.append({"id": "S-00002000", "task": self.TACHE, "kind": "decision",
                        "title": "plan approuvé",
                        "text": f"plan={self.PLAN} sha256={sha}", "date": "2026-10-04"})
        self.ecrire_specs(entrees)
        tache = {"id": self.TACHE, "state": "running"}
        if star:
            self.armer(chantier="*")
        else:
            tache["chantier"] = self.CHANTIER
            self.armer()
        data = {"tasks": [
            tache,
            {"id": self.VOISINE, "state": "pending", "chantier": self.CHANTIER},
            {"id": self.ENROLEE, "state": "pending"},
            {"id": self.ETRANGERE, "state": "pending", "chantier": "autre"},
        ]}
        (self.d / ".agents" / "state" / "board" / "TASKS.json").write_text(
            json.dumps(data), encoding="utf-8")
        return data

    def _jambes(self, data: dict) -> dict:
        return {
            "done": pc.refus_au_done(self.d, self.TACHE, data),
            "start": pc.refus_au_start(self.d, self.TACHE, data),
            "verdict": pc.refus_au_verdict(
                self.d, self.TACHE, "verdict", "plan-critic it.1 : GO",
                f"plan={self.PLAN}"),
        }

    def _acceptee(self, data: dict):
        for jambe, refus in self._jambes(data).items():
            with self.subTest(jambe=jambe):
                self.assertIsNone(refus, refus)

    def _refusee(self, data: dict, ecartee: str | None):
        for jambe, refus in self._jambes(data).items():
            with self.subTest(jambe=jambe):
                self.assertIsNotNone(refus, f"{jambe} : la décision doit être refusée")
                self.assertIn("Étape A", refus)
                if ecartee:
                    self.assertIn(f"{self.ECARTEES}", refus)
                    self.assertIn(ecartee, refus)
                else:
                    self.assertNotIn(self.ECARTEES, refus)

    def test_a_decision_de_la_tache_acceptee_sous_toute_graphie(self):
        """Sous `*`, tâche SANS chantier et HORS roster : seule la branche « la
        tâche elle-même » relie. MUTANTS : branche retirée ; comparaison
        ramenée à l'égalité exacte (sous-cas `T-909`)."""
        for sous in (None, {"S-00000101": "T-909"}):
            with self.subTest(sous=sous):
                self._acceptee(self._poser("S-00000101", roster=self.ENROLEE,
                                           star=True, sous=sous))

    def test_b_decision_d_une_tache_du_chantier_acceptee(self):
        """Voisine du chantier NOMMÉ, hors roster. MUTANT : branche chantier
        retirée."""
        self._acceptee(self._poser("S-00000102", roster=self.ENROLEE))

    def test_c_decision_d_une_tache_enrolee_sans_chantier_acceptee(self):
        """Tâche sans chantier, enrôlée par le roster. MUTANT : branche
        enrôlement retirée."""
        self._acceptee(self._poser("S-00000103", roster=f"{self.TACHE}, {self.ENROLEE}"))

    def test_d_decision_d_un_autre_chantier_non_enrolee_refusee(self):
        """LE DÉFAUT MESURÉ : accepté à la base. Le refus NOMME la décision
        écartée. POLARITÉ : la même décision, sa tâche ENRÔLÉE, est acceptée —
        c'est le non-enrôlement qui refuse, pas le chantier. MUTANTS : rendre
        `decisions_existantes` ; comparer les chantiers sans exiger qu'il soit
        celui de la tâche."""
        self._refusee(self._poser("S-00000104", roster=f"{self.TACHE}, {self.ENROLEE}"),
                      "S-00000104")
        self._acceptee(self._poser("S-00000104", roster=f"{self.TACHE}, {self.ETRANGERE}"))

    def test_e_decision_inexistante_refusee(self):
        """Une S- absente du journal reste refusée, et n'est pas nommée parmi les
        décisions « qui existent ». MUTANT : `_etape_valide` accepte toute S-."""
        self._refusee(self._poser("S-00000105", roster=f"{self.TACHE}, {self.ENROLEE}"),
                      None)

    def test_f_roster_en_forme_courte_n_enrole_pas(self):
        """Décision pilote S-00004059 (« 3 : B ») : un roster en forme COURTE
        n'enrôle pas. MUTANT : enrôlement comparé par `cle_de_tache` au lieu de
        réutiliser `enrolling_line` telle quelle."""
        self._refusee(self._poser("S-00000103", roster=f"{self.TACHE}, T-500"),
                      "S-00000103")

    def test_g_tache_purgee_enrolee_en_forme_longue_acceptee(self):
        """critic-opus F5 : une tâche ABSENTE du board (close puis purgée) n'était
        pas enrôlable — sa décision refusée même nommée au roster. Acceptée
        enrôlée en forme longue, sous les DEUX graphies de sa trace. POLARITÉS :
        non enrôlée, refusée et nommée ; roster en forme COURTE, refusée
        (S-00004059), MÊME quand la trace porte cette forme courte. MUTANTS :
        garde `tache is not None` remise devant l'enrôlement (sous-cas acceptés
        rouges) ; enrôlement par la graphie BRUTE de la trace `e.get("task")`
        (trace `T-700` : roster `T-700` accepté, roster long refusé)."""
        for sous in (None, {"S-00000106": "T-700"}):
            with self.subTest(trace=(sous or {}).get("S-00000106", self.PURGEE)):
                self._acceptee(self._poser(
                    "S-00000106", roster=f"{self.TACHE}, {self.PURGEE}", sous=sous))
                self._refusee(self._poser(
                    "S-00000106", roster=f"{self.TACHE}, T-700", sous=sous), "S-00000106")
        self._refusee(self._poser("S-00000106", roster=f"{self.TACHE}, {self.ENROLEE}"),
                      "S-00000106")

    def test_cible_check_nomme_les_decisions_ecartees(self):
        """critic-fable n° 2 : sous un chantier NOMMÉ, le rc 1 de `cible-check`
        taisait la décision écartée que start, done et le verdict nomment.
        MUTANT : retirer la ligne `ligne_ecartees` du rc 1 de `cible_check`.
        POLARITÉ : une S- inexistante n'est pas nommée « qui existe »."""
        self._poser("S-00000104", roster=f"{self.TACHE}, {self.ENROLEE}")
        rc, msg = pc.cible_check(self.d, self.PLAN, None)
        self.assertEqual(rc, 1, msg)
        self.assertIn(f"{self.ECARTEES} ne portent ni sur une tâche du chantier "
                      f"`{self.CHANTIER}`", msg)
        self.assertIn("enrôle : S-00000104.", msg)
        self._poser("S-00000105", roster=f"{self.TACHE}, {self.ENROLEE}")
        rc, msg = pc.cible_check(self.d, self.PLAN, None)
        self.assertEqual(rc, 1, msg)
        self.assertNotIn(self.ECARTEES, msg)

    def test_cible_check_sous_chantier_nomme_puis_sous_joker(self):
        """`cible-check` sans `--spec` lit le chantier du marqueur : sous un nom,
        la pertinence est celle des jambes (tâches du chantier ∪ enrôlées) ;
        sous `*`, la tâche est inconnue — existence seule, et la sortie le DIT.
        Appel DIRECT (le câblage CLI est tenu par `CibleCheckContratRcTests`).
        MUTANT : `cible_check` rendu à `decisions_existantes` sous un nom."""
        self._poser("S-00000104", roster=f"{self.TACHE}, {self.ENROLEE}")
        rc, msg = pc.cible_check(self.d, self.PLAN, None)
        self.assertEqual(rc, 1, msg)
        self.assertIn("Étape A", msg)
        self._poser("S-00000103", roster=f"{self.TACHE}, {self.ENROLEE}")
        rc, msg = pc.cible_check(self.d, self.PLAN, None)
        self.assertEqual(rc, 0, msg)
        self._poser("S-00000104", roster=self.ENROLEE, star=True)
        rc, msg = pc.cible_check(self.d, self.PLAN, None)
        self.assertEqual(rc, 0, msg)
        self.assertIn("NON contrôlée", msg)


# ===========================================================================
# T-00000909, EXTENSION A (décision pilote S-00004069, constat F3 de critic-opus
# S-00004068) : la décision du PROPRIÉTAIRE de la trace `plan approuvé` qui a élu
# le plan — `tid` en R1, le slot en R2 — est pertinente, comparée par
# `cle_de_tache`. Mesuré à la base 79fda2b8 : sous `chantier=*`, la graine de
# l'adoptant, aucune tâche n'a de chantier ; plan de lot du slot « Tâches :
# <sub> », décision tracée sur le SLOT — `start` du slot rc 0, `done` de la
# sous-tâche rc 2. R2 tenait "" pour un chantier commun, la pertinence exigeait
# un nom. L'enrôlement n'est pas touché : la forme courte n'enrôle toujours pas
# (S-00004059).
# ===========================================================================
class ProprietaireDeLaTraceTests(_Base):
    SID = "S-00003000"
    PLAN = "plans/lot.md"
    LOT = ("# Plan de lot\nTâches : {sub}\n"
           "### Étape A — une\ndécision pilote: {sid}\n"
           "### Étape B — deux\nangle mort: faut-il découper ?\n")
    # Bancs directs : `SLOT` élit le plan. `AUTRE_SLOT`, `running` lui aussi et
    # visité EN PREMIER par R2, porte une trace `plan approuvé` sur un plan qui
    # n'enrôle pas `SUB` : il n'élit rien.
    SUB = "T-00000814"
    SLOT = "T-012"
    AUTRE_SLOT = "T-00000013"
    TIERCE = "T-00000600"
    ECARTEES = PertinenceDecisionTests.ECARTEES

    def setUp(self):
        super().setUp()
        for sub in ("local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)

    def _trace(self, sid: str, tid: str, plan: str, sha: str) -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": "plan approuvé",
                "text": f"plan={plan} sha256={sha}", "date": "2026-10-04"}

    def _decision(self, tid: str) -> dict:
        return {"id": self.SID, "task": tid, "kind": "decision",
                "title": "une décision", "text": "", "date": "2026-10-04"}

    def _nouvelle(self) -> str:
        r = self.tasks("new", "une tache de banc")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()[1]  # "TASKS: T-… → pending"

    def _stage(self, tid: str) -> str:
        board = json.loads((self.d / ".agents" / "state" / "board" / "TASKS.json")
                           .read_text(encoding="utf-8"))
        return next(t.get("stage") or "" for t in board["tasks"] if t["id"] == tid)

    def _poser(self, decision_sur: str, *, star: bool = True) -> dict:
        sha = self.ecrire_plan(self.PLAN, self.LOT.format(sub=self.SUB, sid=self.SID))
        autre = self.ecrire_plan("plans/autre.md",
                                 self.LOT.format(sub="T-00099999", sid=self.SID))
        self.ecrire_specs([
            self._decision(decision_sur),
            self._trace("S-00003001", self.SLOT, self.PLAN, sha),
            self._trace("S-00003002", self.AUTRE_SLOT, "plans/autre.md", autre)])
        self.armer(chantier="*" if star else self.CHANTIER)
        nom = {} if star else {"chantier": self.CHANTIER}
        return {"tasks": [
            {"id": self.AUTRE_SLOT, "state": "running", **nom},
            {"id": self.SLOT, "state": "running", **nom},
            {"id": self.SUB, "state": "pending", **nom},
            {"id": self.TIERCE, "state": "pending",
             **({} if star else {"chantier": "autre"})},
        ]}

    def _done(self, data: dict) -> tuple:
        return pc.evaluer_done(self.d, self.SUB, data)

    def test_a_bout_en_bout_sous_joker_la_decision_du_slot_vaut_pour_l_enrolee(self):
        """LE DÉFAUT MESURÉ, par la CLI : `done` de la sous-tâche rc 2 à la base.
        Le `start` du slot passe (R1, la décision est la sienne) ; le `done` de
        la sous-tâche passe, et sa note NOMME le slot élu. MUTANTS : branche
        propriétaire retirée de `decisions_pertinentes` ; `evaluer_done` ne
        transmet pas le propriétaire."""
        sub, slot = self._nouvelle(), self._nouvelle()
        sha = self.ecrire_plan(self.PLAN, self.LOT.format(sub=sub, sid=self.SID))
        self.ecrire_specs([self._decision(slot),
                           self._trace("S-00003001", slot, self.PLAN, sha)])
        self.armer(chantier="*")
        r = self.tasks("start", slot)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.tasks("done", sub, "--raison", "clos par le banc")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"[cible relevée sur {slot} : lot.md (S-00003001)]",
                      self._stage(sub))

    def test_b_decision_du_slot_elu_acceptee_sous_toute_graphie(self):
        """Même défaut, appel direct, slot `T-012` au board : la décision tracée
        sous `T-012` PUIS sous `T-00000012` est acceptée, et la note nomme le
        slot élu, pas `AUTRE_SLOT` visité avant lui. MUTANTS : branche
        propriétaire retirée (deux sous-cas rouges) ; propriétaire comparé à
        l'égalité exacte, `e.get("task") == proprietaire` (sous-cas
        `T-00000012` rouge) ou `cle == proprietaire` (deux sous-cas rouges)."""
        for sous in (self.SLOT, "T-00000012"):
            with self.subTest(decision_sous=sous):
                refus, note = self._done(self._poser(sous))
                self.assertIsNone(refus, refus)
                self.assertEqual(
                    note, f"[cible relevée sur {self.SLOT} : lot.md (S-00003001)]")

    def test_c_contre_temoin_decision_d_une_tache_tierce_refusee(self):
        """Ni la tâche, ni son chantier (aucun sous `*`), ni enrôlée, ni
        propriétaire : refusée, et NOMMÉE parmi les écartées. MUTANT : toute
        tâche du board tenue pour propriétaire."""
        refus, note = self._done(self._poser(self.TIERCE))
        self.assertIsNotNone(refus, "la décision d'une tâche tierce doit être refusée")
        self.assertIn("Étape A", refus)
        self.assertIn(self.ECARTEES, refus)
        self.assertIn(self.SID, refus)
        self.assertEqual(note, "")

    def test_d_contre_temoin_un_slot_qui_n_a_pas_elu_le_plan(self):
        """`AUTRE_SLOT` est `running`, au même chantier vide, visité AVANT le slot
        élu, et porte une trace `plan approuvé` — sur un plan qui n'enrôle pas
        `SUB` : il n'a pas élu CE plan, sa décision reste écartée. MUTANTS :
        propriétaire pris au premier slot `running` visité, ou à tout slot
        porteur d'une trace d'approbation."""
        refus, _note = self._done(self._poser(self.AUTRE_SLOT))
        self.assertIsNotNone(refus, "un slot qui n'a pas élu le plan ne prête rien")
        self.assertIn("Étape A", refus)
        self.assertIn(self.ECARTEES, refus)
        self.assertIn(f"[cible relevée sur {self.SLOT}", refus)

    def test_e_contre_temoin_sous_chantier_nomme_rien_ne_change(self):
        """Sous un chantier NOMMÉ, R2 n'emprunte qu'au MÊME chantier : la décision
        du slot élu était déjà pertinente par la branche chantier, celle de
        l'autre slot du chantier aussi ; celle d'une tâche d'un AUTRE chantier
        reste refusée. MUTANT : branche chantier remplacée par la seule branche
        propriétaire (sous-cas `AUTRE_SLOT` rouge)."""
        for sur in (self.SLOT, self.AUTRE_SLOT):
            with self.subTest(decision=sur):
                refus, _note = self._done(self._poser(sur, star=False))
                self.assertIsNone(refus, refus)
        refus, _note = self._done(self._poser(self.TIERCE, star=False))
        self.assertIsNotNone(refus, "autre chantier, non enrôlée : refusée")
        self.assertIn(self.ECARTEES, refus)


# ===========================================================================
# Passe de correction F5 (delta S-01M4QK902B8THSQG3KVBJ2PPK0) — `_cause_r3` ne
# diagnostique plus une trace SUPPLANTÉE. Mesuré au done de T-01M4MC28… : la
# cause affichée était l'empreinte périmée de la rév. 1 de LOT-F7-plan.md
# (S-00004077), quand la rév. 2 (S-00004085, empreinte juste) n'enrôlait pas
# la tâche — les 9 tâches docs recevaient la même cause FAUSSE.
# ===========================================================================
class CauseR3TraceSupplanteeTests(_Base):
    SLOT = "T-012"
    MEMBRE = "T-00000814"
    PLAN = "docs/tasks/LOT-F7-plan.md"
    LOT = "# Plan de lot\nTâches : T-00000909\n### Étape A — seule\ncible: « un invariant »\n"

    def _poser(self) -> dict:
        sha = self.ecrire_plan(self.PLAN, self.LOT)
        self.ecrire_specs([
            {"id": "S-00004077", "task": self.SLOT, "kind": "decision", "title": "plan approuvé",
             "text": f"plan={self.PLAN} sha256={'0' * 64}", "date": "2026-10-04"},
            {"id": "S-00004085", "task": self.SLOT, "kind": "decision", "title": "plan approuvé",
             "text": f"plan={self.PLAN} sha256={sha}", "date": "2026-10-05"},
        ])
        self.armer()
        return {"tasks": [{"id": self.SLOT, "state": "running", "chantier": self.CHANTIER},
                          {"id": self.MEMBRE, "state": "pending", "chantier": self.CHANTIER}]}

    def test_la_cause_est_l_enrolement_pas_l_empreinte_supplantee(self):
        """Deux traces du slot sur le MÊME plan : l'ancienne au sha périmé, la récente au sha juste, plan non
        enrôlant. MUTANT : `_plus_recentes_par_plan` ramené à l'identité (ordre du journal, toutes les traces) ⇒ la
        cause redevient « empreinte divergente »."""
        refus = pc.refus_au_done(self.d, self.MEMBRE, self._poser())
        self.assertIsNotNone(refus)
        self.assertIn(f"n'enrôle pas {self.MEMBRE}", refus)
        self.assertNotIn("empreinte divergente", refus)

    def test_polarite_la_seule_trace_perimee_reste_diagnostiquee(self):
        """POLARITÉ : sans trace plus récente sur ce plan, l'empreinte divergente reste la cause nommée."""
        data = self._poser()
        specs = self.d / ".agents" / "state" / "specs" / "SPECS.json"
        brut = json.loads(specs.read_text(encoding="utf-8"))
        brut["entries"] = brut["entries"][:1]
        specs.write_text(json.dumps(brut), encoding="utf-8")
        self.assertIn("empreinte divergente", pc.refus_au_done(self.d, self.MEMBRE, data))


class CibleCheckBoardFailClosedTests(_Base):
    """Passe de correction F5, avis sécurité medium de la bascule : sous un chantier NOMMÉ, `cible-check` lit le board
    hors verrou ; en deux formes ou illisible il refuse NOMMÉ en rc 2, jamais une trace ni un rc 0 sur un board lu
    vide. MUTANT : retirer le `try/except CibleError` autour de `taches_du_board` dans `cible_check` (TRACE, rc 1)."""

    def test_board_illisible_ou_en_deux_formes_rc2_nomme(self):
        self.ecrire_plan("plans/p.md", CibleCheckContratRcTests.PLAN_ANNOTE)
        self.armer()
        board = self.d / ".agents" / "state" / "board"
        (board / "TASKS.json").write_text("{ pas du json", encoding="utf-8")
        rc, msg = pc.cible_check(self.d, "plans/p.md", None)
        self.assertEqual((rc, "illisible" in msg), (2, True), msg)
        (board / "TASKS.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
        self.assertEqual(pc.cible_check(self.d, "plans/p.md", None)[0], 0, "POLARITÉ : board lisible ⇒ rc 0")


if __name__ == "__main__":
    unittest.main()
