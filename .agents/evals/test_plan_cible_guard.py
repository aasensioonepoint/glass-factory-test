#!/usr/bin/env python3
"""LE VERROU DE CIBLE — grammaire d'étapes, chemin sûr, isolation, jambe `start`.

Verrou B de T-00000654. ZÉRO APPEL LLM : on appelle `plan_cible` directement sur
des textes de plan, on pose des fixtures de fichiers dans un `tmp_path` RÉEL, et
on regarde `tasks.py start` refuser ou non — le même contrat que
`test_plan_chain_guard.py` tient pour la chaîne.

*** CHAQUE TÉMOIN PORTE SON MUTANT. *** Un témoin qui ne peut pas échouer est
décoratif — ce dépôt l'a mesuré. Le docstring de chaque test nomme la MUTATION
du code réel qui doit le faire rougir.

Ce banc N'EST PAS strippé : son sujet — `plan_cible.py` et la CLI `tasks.py` —
VOYAGE. Seul l'instantané de la spec (`test_spec_clause_registry.py`) est strippé.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
TASKS = BIN / "tasks.py"
SPECS = BIN / "specs.py"
TEMPLATE_EXCLUDE = ROOT / ".template-exclude"

# `.agents/bin` sur le path : la parité de grammaire importe `night_approve` (le
# SEUL banc autorisé à le faire, D4), et le chargement de `plan_cible` reste
# robuste même si une passe le couplait par erreur à un module du kit.
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


pc = _charger("plan_cible", BIN / "plan_cible.py")
# Le résolveur du kit, chargé PAR CHEMIN (patron v3prep) : `exiger` dit où vit le paquet `cadre`
# de la racine (`.agents/vendor/cadre` ou `src/cadre`), sans rien insérer sur `sys.path`.
_VENDOR = _charger("_plan_cible_guard_vendor_paths", BIN / "vendor_paths.py")


def _poser_generateur(kit: Path, source: Path = ROOT) -> Path:
    """`ids.py` du paquet `cadre` de `source`, où qu'il vive (`exiger`), posé là où le
    `record_id.py` copié dans `kit` le cherchera : `dossier_paquet(kit, "cadre")` quand le kit
    porte `vendor_paths.py` ET un paquet à `__init__.py`, sinon le repli `<kit>/src/cadre`
    (`record_id._dossier_cadre`). Rend le chemin posé."""
    origine = _VENDOR.exiger(source, "cadre") / "ledger" / "ids.py"
    dossier = None
    if (kit / ".agents" / "bin" / "vendor_paths.py").is_file():
        dossier = _VENDOR.dossier_paquet(kit, "cadre")
    cible = (dossier if dossier is not None else kit / "src" / "cadre") / "ledger" / "ids.py"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(origine.read_bytes())
    return cible


def _regles_strip() -> list[str]:
    regles = []
    for ligne in TEMPLATE_EXCLUDE.read_text(encoding="utf-8").splitlines():
        d = ligne.strip()
        if d.startswith("strip:"):
            regles.append(d[len("strip:"):].strip())
    return regles


def _est_strippe(rel: str) -> bool:
    for r in _regles_strip():
        if rel == r or (r.endswith("/") and rel.startswith(r)):
            return True
    return False


# ===========================================================================
# GRAMMAIRE D'ÉTAPES — appels directs sur des textes de plan.
# ===========================================================================
class GrammaireTests(unittest.TestCase):
    def test_plan_format_lot_annote_passe(self):
        """MUTANT : valeurs sous `### Étape X` non lues. Un plan de lot dont
        chaque étape porte une décision pilote passe sans faute."""
        plan = (
            "# Plan\n"
            "### Étape A — un truc\n"
            "décision pilote: S-00001558\n"
            "\n"
            "### Étape B — autre truc\n"
            "angle mort: une question au pilote ?\n"
        )
        self.assertEqual(
            pc.etapes_fautives(plan, set(), {"S-00001558"}), [])

    def test_plan_format_lot_non_annote_refuse_en_nommant_Etape_A(self):
        """MUTANT : priorité `### Étape X` retirée. Un plan de lot sans annotation
        est refusé, et la faute NOMME `Étape A` (jamais un numéro)."""
        plan = (
            "# Plan\n"
            "### Étape A — sans cible\n"
            "juste de la prose\n"
            "\n"
            "### Étape B — sans cible non plus\n"
            "encore de la prose\n"
        )
        fautives = pc.etapes_fautives(plan, set(), set())
        self.assertIn("Étape A", fautives)
        self.assertIn("Étape B", fautives)

    def test_etape_sans_cible_refuse(self):
        """MUTANT : `any` au lieu de `all`. UNE étape sans cible suffit à faire
        échouer le plan, même si les autres sont annotées."""
        plan = (
            "### Étape A — ok\n"
            "décision pilote: S-1\n"
            "### Étape B — pas ok\n"
            "rien ici\n"
        )
        self.assertEqual(
            pc.etapes_fautives(plan, set(), {"S-1"}), ["Étape B"])

    def test_etape_a_deux_valeurs_passe(self):
        """MUTANT : une valeur EXACTE exigée. Une étape peut porter deux valeurs
        valides — au moins une suffit, plus n'est pas une faute."""
        plan = (
            "### Étape A — deux valeurs\n"
            "angle mort: une question ?\n"
            "décision pilote: S-1\n"
        )
        self.assertEqual(pc.etapes_fautives(plan, set(), {"S-1"}), [])

    def test_nom_absent_de_la_spec_refuse(self):
        """MUTANT : appartenance au registre non vérifiée. Une `cible: « … »`
        dont le nom n'est PAS dans le registre ne vaut pas une cible."""
        plan = "### Étape A — cible inconnue\ncible: « ce nom n'existe pas »\n"
        self.assertEqual(
            pc.etapes_fautives(plan, {"un vrai nom"}, set()), ["Étape A"])

    def test_nom_hors_section_3_accepte(self):
        """MUTANT : registre borné au §3. Une cible qui nomme un invariant HORS
        du §3 (ici une couture déclarée en §4) est acceptée — le registre couvre
        TOUTE la spec, pas la seule section 3. Spec SYNTHÉTIQUE : ce banc VOYAGE,
        il ne nomme donc jamais la vraie spec, qui ne voyage pas."""
        spec = (
            "## 3. Invariants\n"
            "1. **« invariant du trois »** — un invariant du §3.\n"
            "## 4. Coutures\n"
            "**« couture hors du trois »** — hors §3.\n"
        )
        registre = set(pc.registre_des_noms(spec))
        plan = "### Étape A — couture citée\ncible: « couture hors du trois »\n"
        self.assertEqual(pc.etapes_fautives(plan, registre, set()), [])

    def test_decision_pilote_T_id_refuse(self):
        """MUTANT : motif de décision élargi. Un `décision pilote: T-…` (id de
        tâche) est refusé — seul `S-<id>` est admis."""
        plan = "### Étape A — décision par tâche\ndécision pilote: T-00000654\n"
        self.assertEqual(
            pc.etapes_fautives(plan, set(), {"T-00000654"}), ["Étape A"])

    def test_decision_pilote_S_id_inexistant_refuse(self):
        """MUTANT : contrôle d'existence retiré. Un `S-<id>` qui n'est pas une
        entrée SPECS existante ne vaut pas une cible."""
        plan = "### Étape A — S-id inventé\ndécision pilote: S-99999999\n"
        self.assertEqual(
            pc.etapes_fautives(plan, set(), {"S-00001558"}), ["Étape A"])

    def test_decision_pilote_kind_non_decision_refuse(self):
        """MUTANT : contrôle du `kind` retiré. Une entrée SPECS d'un autre `kind`
        (verdict…) ne compte pas comme une décision pilote."""
        entrees = [{"id": "S-00001558", "kind": "verdict", "task": "T-1",
                    "title": "plan-critic it.1 : GO", "text": ""}]
        decisions = pc.decisions_existantes(entrees)
        self.assertNotIn("S-00001558", decisions)
        plan = "### Étape A — cite un verdict\ndécision pilote: S-00001558\n"
        self.assertEqual(pc.etapes_fautives(plan, set(), decisions), ["Étape A"])

    def test_plan_sans_etape_refuse(self):
        """MUTANT : `all([])` admis. Un plan SANS aucune étape est fautif en bloc,
        jamais vacuously valide."""
        plan = "# Un plan de pure prose\nAucune section Steps, aucun titre d'étape.\n"
        self.assertTrue(pc.etapes_fautives(plan, set(), set()))

    def test_etapes_en_bloc_de_code_ignorees(self):
        """MUTANT : clôtures ``` non détectées. Un `### Étape` DANS un bloc de
        code n'est pas une étape — les vraies étapes sont les items numérotés."""
        plan = (
            "## Steps\n"
            "1. vraie étape\n"
            "   décision pilote: S-1\n"
            "2. seconde étape\n"
            "   angle mort: une question ?\n"
            "\n"
            "```\n"
            "### Étape FANTOME\n"
            "```\n"
        )
        self.assertEqual(pc.etapes_fautives(plan, set(), {"S-1"}), [])

    def test_cible_sur_deux_lignes_cote_plan(self):
        """MUTANT : `\\n` réintroduit dans la classe du motif (`[^»\\n]{1,300}?`).
        D9 replie les retours à la ligne « des deux côtés » : un nom d'invariant
        écrit sur DEUX lignes dans le plan doit valoir cible. `normalise_nom`
        replie déjà le `\\n` côté plan, le motif doit donc l'AUTORISER dans la
        capture — sinon le repli est promis d'un seul côté."""
        registre = {pc.normalise_nom("un invariant sur deux lignes")}
        plan = (
            "### Étape A — cible sur deux lignes\n"
            "cible: « un invariant\n"
            "sur deux lignes »\n"
        )
        self.assertEqual(pc.etapes_fautives(plan, registre, set()), [])

    def test_message_aucune_etape_nomme_la_grammaire(self):
        """MUTANT : message « aucune étape » réduit à « plan incomplet ». Le
        refus d'un plan SANS étape NOMME la grammaire attendue (`### Étape X` ou
        `## Steps`) pour que l'auteur sache quoi corriger."""
        fautives = pc.etapes_fautives("# Pure prose, aucune étape.\n", set(), set())
        self.assertEqual(len(fautives), 1)
        self.assertIn("### Étape", fautives[0])
        self.assertIn("## Steps", fautives[0])


# ===========================================================================
# CHEMIN SÛR — fixtures de fichiers en tmp_path RÉEL.
# ===========================================================================
class CheminSurTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self._tmp_hors = tempfile.TemporaryDirectory()
        self.hors = Path(self._tmp_hors.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._tmp_hors.cleanup()

    def test_chemin_sur_parite_plan_pool(self):
        """MUTANT : contrôle `..`/`relative_to` retiré. Les formes SÛRES rendent
        un chemin, les NON SÛRES rendent None — parité ligne à ligne avec
        `plan_pool.py:438-440`."""
        (self.d / "plans").mkdir()
        (self.d / "plans" / "ailleurs.md").write_text("x", encoding="utf-8")
        (self.d / "docs" / "tasks").mkdir(parents=True)
        (self.d / "docs" / "tasks" / "X.MD").write_text("x", encoding="utf-8")
        (self.d / "docs" / "tasks" / "x.md").write_text("x", encoding="utf-8")
        for sur in ("plans/ailleurs.md", "docs/tasks/X.MD",
                    "docs/tasks/x.md,", "docs/tasks/x.md"):
            self.assertIsNotNone(
                pc.chemin_de_plan_sur(self.d, sur), f"forme SÛRE refusée : {sur!r}")
        # NON SÛRES
        self.assertIsNone(pc.chemin_de_plan_sur(self.d, "/etc/passwd"))
        self.assertIsNone(pc.chemin_de_plan_sur(self.d, "../../outside.md"))
        self.assertIsNone(pc.chemin_de_plan_sur(self.d, "docs/tasks/absent.md"))
        # lien symbolique hors racine : `resolve(strict=True)` suit le lien, puis
        # `relative_to` échoue — c'est LE cas que la mutation fait basculer.
        cible = self.hors / "outside.md"
        cible.write_text("x", encoding="utf-8")
        (self.d / "docs" / "tasks" / "lien.md").symlink_to(cible)
        self.assertIsNone(
            pc.chemin_de_plan_sur(self.d, "docs/tasks/lien.md"),
            "un lien vers un fichier HORS racine a été accepté")

    def test_racine_resolue_sur_tmp_path(self):
        """MUTANT : `resolved_root = root.resolve()` remplacé par `root`. Sans la
        résolution de la RACINE, une fixture `tmp_path` de macOS (`/var` vs
        `/private/var`) fait échouer `relative_to` sur un chemin pourtant sûr."""
        (self.d / "plans").mkdir()
        (self.d / "plans" / "p.md").write_text("x", encoding="utf-8")
        self.assertIsNotNone(pc.chemin_de_plan_sur(self.d, "plans/p.md"))

    def test_plan_pool_voyage(self):
        """MUTANT : règle `strip:` ajoutée pour plan_pool. `core-scripts/plan_pool.py`
        VOYAGE (défense en profondeur, témoin de parité) ; seul son BANC
        `cadre.test.sh` est strippé."""
        self.assertFalse(
            _est_strippe("core-scripts/plan_pool.py"),
            "plan_pool.py est devenu `strip:` — il doit VOYAGER")
        # non-vacuité : le parseur de règles détecte bien un strip réel.
        self.assertTrue(_est_strippe("core-scripts/cadre.test.sh"))


# ===========================================================================
# ISOLATION — grammaire recopiée, pas importée ; stdlib seule ; pas de verrou.
# ===========================================================================
class IsolationTests(unittest.TestCase):
    def test_parite_grammaire_night_approve(self):
        """MUTANT : une alternative retirée de la grammaire de verdict. La
        grammaire est RECOPIÉE de `night_approve` (D4) ; ce banc — et lui seul —
        importe `night_approve` pour prouver la parité."""
        if str(BIN) not in sys.path:
            sys.path.insert(0, str(BIN))
        na = _charger("night_approve", BIN / "night_approve.py")
        self.assertEqual(na.PLAN_CRITIC_TITLE.pattern, pc.PLAN_CRITIC_TITLE.pattern)
        self.assertEqual(na.ANCHORED_VERDICT.pattern, pc.ANCHORED_VERDICT.pattern)
        self.assertEqual(na.VERDICT_PROBES, pc.VERDICT_PROBES)
        self.assertEqual(na.ELIGIBLE_STATUSES, pc.ELIGIBLE_STATUSES)
        self.assertEqual(na.NO_GO_PATTERN, pc.NO_GO_PATTERN)

    def test_parite_exclut_l_appariement_de_titre(self):
        """MUTANT : appariement de titre réintégré au périmètre de parité (repli
        d'accents retiré). `normalise_titre` REPLIE les accents et la casse —
        divergence PERMISSIVE assumée avec night_approve, EXCLUE de la parité de
        grammaire."""
        self.assertEqual(
            pc.normalise_titre("plan approuvé"), pc.normalise_titre("plan approuve"),
            "normalise_titre doit replier les accents (divergence permissive)")
        self.assertEqual(
            pc.normalise_titre("PLAN APPROUVÉ"), pc.normalise_titre("plan approuve"),
            "normalise_titre doit replier la casse")

    def test_plan_cible_stdlib_seule(self):
        """MUTANT : `import night_approve` (ou tasks/specs) ajouté à plan_cible.
        SOUS-PROCESSUS réel : après import de plan_cible, aucun module du kit ne
        doit apparaître dans `sys.modules`."""
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(BIN)!r})\n"
            "import plan_cible\n"
            "interdits = [m for m in ('tasks', 'specs', 'night_approve') "
            "if m in sys.modules]\n"
            "assert not interdits, interdits\n"
            "print('STDLIB-ONLY-OK')\n"
        )
        with tempfile.TemporaryDirectory() as cwd:
            r = subprocess.run(
                [sys.executable, "-c", script],
                cwd=cwd, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0,
                         f"plan_cible a tiré un module du kit :\n{r.stdout}\n{r.stderr}")
        self.assertIn("STDLIB-ONLY-OK", r.stdout)


# ===========================================================================
# JAMBE `start` — via SOUS-PROCESSUS `tasks.py`, board + SPECS + marqueur réels.
# ===========================================================================
class _BaseStart(unittest.TestCase):
    CHANTIER = "refonte-packaging"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "specs", "local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        (self.d / "plans").mkdir()
        # une spec minimale : le registre importe peu, les étapes citent des
        # décisions ; mais `_registre_pour` lit tout de même le fichier.
        (self.d / "spec.md").write_text("**« un invariant »**\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def tasks(self, *args: str, timeout: int = 120):
        return subprocess.run(
            [sys.executable, str(TASKS), "--root", str(self.d), *args],
            capture_output=True, text=True, timeout=timeout)

    def new(self, chantier: str | None = CHANTIER):
        args = ["new", "une tache de banc"]
        if chantier:
            args += ["--chantier", chantier]
        r = self.tasks(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()[1]  # "TASKS: T-… → pending"

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

    def decision(self, sid: str, tid: str, titre: str = "une décision") -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": titre,
                "text": "", "date": "2026-09-17"}

    def trace_approuve(self, sid: str, tid: str, plan_rel: str, sha: str) -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": "plan approuvé",
                "text": f"plan={plan_rel} sha256={sha}", "date": "2026-09-17"}

    PLAN_COMPLET = (
        "# Plan complet\n"
        "Tâches : {tid}\n"
        "## Steps\n"
        "1. étape une\n"
        "   décision pilote: S-00001558\n"
        "2. étape deux\n"
        "   décision pilote: S-00001558\n"
    )
    PLAN_INCOMPLET = (
        "# Plan incomplet\n"
        "Tâches : {tid}\n"
        "## Steps\n"
        "1. étape une\n"
        "   décision pilote: S-00001558\n"
        "2. étape deux SANS cible\n"
        "   juste de la prose\n"
    )

    def board_stage(self, tid: str) -> str:
        data = json.loads(
            (self.d / ".agents" / "state" / "board" / "TASKS.json").read_text(
                encoding="utf-8"))
        for t in data["tasks"]:
            if t["id"] == tid:
                return t.get("stage") or ""
        raise AssertionError(f"{tid} absent du board")


class StartTests(_BaseStart):
    def test_start_sans_trace_propre_passe(self):
        """MUTANT : polarité inversée. Marqueur armé, tâche du chantier, mais
        AUCUNE trace d'approbation : le `start` PASSE (R1 seule ; la cible mordra
        au `done`)."""
        tid = self.new()
        self.armer()
        r = self.tasks("start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ running", r.stdout)

    def test_cli_start_arme_sous_processus(self):
        """MUTANT : plan_cible importe `tasks` et reprend le verrou. SOUS-PROCESSUS
        réel : `tasks.py start` sous marqueur armé, avec une trace vers un plan
        COMPLET, se termine SANS interblocage (isolation D6 : plan_cible relit
        SPECS.json sans jamais reprendre `board_lock`). Un ré-emprunt du verrou
        interbloquerait jusqu'au timeout."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md",
                               self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace_approuve("S-00002000", tid,
                                               "plans/complet.md", sha)])
        self.armer()
        r = self.tasks("start", tid, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ running", r.stdout)

    def test_start_trace_propre_plan_incomplet_refuse(self):
        """MUTANT : contrôle des étapes sauté. Une trace `plan approuvé` valide
        vers un plan INCOMPLET fait refuser le `start`."""
        tid = self.new()
        sha = self.ecrire_plan("plans/incomplet.md",
                               self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace_approuve("S-00002000", tid,
                                               "plans/incomplet.md", sha)])
        self.armer()
        r = self.tasks("start", tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("étape deux SANS cible", r.stderr)

    def test_refus_cible_ne_consomme_pas_la_chaine(self):
        """MUTANT : greffe de la cible APRÈS la consommation de la chaîne. Un
        refus de cible ne doit RIEN consommer — la même paire de verdicts doit
        rester réutilisable."""
        tid = self.new()
        sha = self.ecrire_plan("plans/incomplet.md",
                               self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace_approuve("S-00002000", tid,
                                               "plans/incomplet.md", sha)])
        self.armer()
        # arme AUSSI la chaîne et pose une chaîne complète.
        (self.d / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").touch()
        for nom in ("plan-critic", "plan-critic-sonnet-max", "planner"):
            role = "reviewer" if "critic" in nom else "planner"
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": "2026-09-17T10:00:00Z", "sha": "abc", "role": role}),
                encoding="utf-8")
        r = self.tasks("start", tid)
        self.assertNotEqual(r.returncode, 0, "le plan incomplet aurait dû refuser")
        traces = sorted(p.name for p in
                        (self.d / ".agents" / "state" / "local" / "plan").glob("*.json"))
        self.assertEqual(
            traces, ["plan-critic-sonnet-max.json", "plan-critic.json", "planner.json"],
            "la chaîne a été CONSOMMÉE par un refus de cible")

    def test_sans_cible_visible_au_board(self):
        """MUTANT : marque non ajoutée. `start --sans-cible` passe ET écrit
        `[SANS CIBLE : …]` au board — l'exception se VOIT."""
        tid = self.new()
        self.armer()
        r = self.tasks("start", tid, "--sans-cible", "plan figé, banc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[SANS CIBLE : plan figé, banc]", self.board_stage(tid))

    def test_tache_hors_chantier_inerte(self):
        """MUTANT : contrôle du chantier retiré. Une tâche d'un AUTRE chantier
        n'est pas contrainte, même avec une trace vers un plan incomplet."""
        tid = self.new(chantier="autre-chantier")
        sha = self.ecrire_plan("plans/incomplet.md",
                               self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace_approuve("S-00002000", tid,
                                               "plans/incomplet.md", sha)])
        self.armer(chantier=self.CHANTIER)
        r = self.tasks("start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ running", r.stdout)

    def test_marqueur_absent_inerte(self):
        """MUTANT : test d'existence retiré. Sans marqueur, la garde est INERTE —
        régime d'un dépôt qui ne l'a pas posé, ou d'un adoptant qui l'a retiré
        (la sync template le lui SÈME, avec `chantier=*`)."""
        tid = self.new()
        sha = self.ecrire_plan("plans/incomplet.md",
                               self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace_approuve("S-00002000", tid,
                                               "plans/incomplet.md", sha)])
        # PAS de marqueur.
        r = self.tasks("start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ running", r.stdout)

    def test_marqueur_malforme_refuse(self):
        """MUTANT : marqueur malformé traité comme absent. Un marqueur présent
        mais sans `spec=`/`chantier=` fait refuser (fail-closed) — ne pas savoir
        quelle contrainte est armée est la pire des lectures."""
        tid = self.new()
        self.armer(contenu="ceci n'est pas un marqueur valide\n")
        r = self.tasks("start", tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("malformé", r.stderr)

    def test_cible_check_spec_sans_marqueur(self):
        """MUTANT : `--spec` ignoré. `cible-check <plan> --spec <spec>` fonctionne
        SANS marqueur armé — la spec vient de `--spec`."""
        self.ecrire_plan("plans/annote.md",
                         "## Steps\n1. une étape\n   angle mort: une question ?\n")
        # AUCUN marqueur armé.
        r = self.tasks("cible-check", "plans/annote.md", "--spec", "spec.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("toutes les étapes", r.stdout)

    def test_start_sans_cible_sans_marqueur_aucune_marque(self):
        """MUTANT : marque `[SANS CIBLE]` au start écrite sans condition de
        marqueur (décision orchestrateur). Un dépôt DÉSARMÉ (marqueur absent) qui
        démarre avec --sans-cible ne doit voir AUCUNE marque au board — sinon la
        dérogation s'affiche là où aucune contrainte n'est armée."""
        tid = self.new()
        # PAS de marqueur.
        r = self.tasks("start", tid, "--sans-cible", "raison quelconque")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("[SANS CIBLE", self.board_stage(tid))


# ===========================================================================
# JAMBE `done` — résolution D8 (R1 tâche, R2 slot enrôlant, R3 refus nommé).
# ===========================================================================
class _BaseDone(_BaseStart):
    PLAN_SLOT_ENROLE = (
        "# Plan slot\n"
        "Tâches : {sub}\n"
        "## Steps\n"
        "1. étape une\n"
        "   décision pilote: S-00001558\n"
        "2. étape deux\n"
        "   décision pilote: S-00001558\n"
    )
    PLAN_SLOT_AUTRE = (
        "# Plan slot\n"
        "Tâches : T-00099999\n"
        "## Steps\n"
        "1. étape une\n"
        "   décision pilote: S-00001558\n"
        "2. étape deux\n"
        "   décision pilote: S-00001558\n"
    )
    PLAN_SLOT_CORPS = (
        "# Plan slot\n"
        "Tâches : T-00099999\n"
        "## Steps\n"
        "1. étape une qui parle de {sub} dans son corps\n"
        "   décision pilote: S-00001558\n"
        "2. étape deux\n"
        "   décision pilote: S-00001558\n"
    )

    def trace(self, sid, tid, plan_rel, sha, title="plan approuvé", kind="decision"):
        return {"id": sid, "task": tid, "kind": kind, "title": title,
                "text": f"plan={plan_rel} sha256={sha}", "date": "2026-09-17"}

    def done(self, tid, *extra, raison="clos par le banc", timeout=120):
        return self.tasks("done", tid, "--raison", raison, *extra, timeout=timeout)


class DoneTests(_BaseDone):
    def test_done_resolu_par_approbation_propre(self):
        """MUTANT : lecture des traces d'approbation de la tâche retirée (R1
        vide). Une trace `plan approuvé` propre vers un plan COMPLET ferme la
        tâche par le chemin nominal."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace("S-00002000", tid, "plans/complet.md", sha)])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_titre_de_trace_sans_accents_accepte(self):
        """MUTANT : repli d'accents retiré (D9 bis). Un titre `plan approuve`
        SANS accent désigne la MÊME trace que `plan approuvé`."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([
            self.decision("S-00001558", tid),
            self.trace("S-00002000", tid, "plans/complet.md", sha, title="plan approuve"),
        ])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_titre_contenant_le_jeton_sans_lui_etre_egal_refuse(self):
        """MUTANT : égalité de titre remplacée par une sous-chaîne. `plan
        approuvé (brouillon)` CONTIENT le jeton mais ne LUI EST PAS égal — ce
        n'est pas une trace d'approbation, donc R3 refuse."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([
            self.decision("S-00001558", tid),
            self.trace("S-00002000", tid, "plans/complet.md", sha,
                       title="plan approuvé (brouillon)"),
        ])
        self.armer()
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucun plan approuvé", r.stderr)

    def test_done_resolu_par_approbation_pilote_du_slot(self):
        """MUTANT : recherche R2 retirée. La tâche n'a pas de trace propre, mais
        le slot `running` du même chantier en porte une vers un plan qui NOMME
        la tâche — R2 la résout."""
        sub = self.new()
        slot = self.new()
        sha = self.ecrire_plan("plans/slot_enrole.md",
                               self.PLAN_SLOT_ENROLE.format(sub=sub))
        self.ecrire_specs([self.decision("S-00001558", sub),
                           self.trace("S-00002000", slot, "plans/slot_enrole.md", sha)])
        self.armer()
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_emprunt_plan_ecrit_au_board(self):
        """MUTANT : note d'emprunt non ajoutée au board. Quand la cible est
        relevée sur le slot d'un autre (R2), l'emprunt s'ÉCRIT au board avec la
        S-id qui l'a autorisé — sinon il n'a pas eu lieu pour le lecteur."""
        sub = self.new()
        slot = self.new()
        sha = self.ecrire_plan("plans/slot_enrole.md",
                               self.PLAN_SLOT_ENROLE.format(sub=sub))
        self.ecrire_specs([self.decision("S-00001558", sub),
                           self.trace("S-00002000", slot, "plans/slot_enrole.md", sha)])
        self.armer()
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        self.assertEqual(self.done(sub).returncode, 0)
        self.assertIn(
            f"[cible relevée sur {slot} : slot_enrole.md (S-00002000)]",
            self.board_stage(sub))

    def test_done_resolu_par_contrat_nuit(self):
        """MUTANT : titre `night-eligible: approved` retiré du jeu des traces.
        Une éligibilité de nuit vaut aussi trace d'approbation pour R1."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([
            self.decision("S-00001558", tid),
            self.trace("S-00002000", tid, "plans/complet.md", sha,
                       title="night-eligible: approved"),
        ])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_resolu_par_verdict_planning(self):
        """MUTANT : voie accessoire des verdicts retirée. Un verdict plan-critic
        FAVORABLE portant `plan=` ET `sha256=` vaut trace d'approbation (D8-b)."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([
            self.decision("S-00001558", tid),
            self.trace("S-00002000", tid, "plans/complet.md", sha,
                       title="plan-critic it.1 : GO", kind="verdict"),
        ])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_sha256_diverge_refuse(self):
        """MUTANT : comparaison d'empreinte retirée. Une trace dont le `sha256=`
        ne correspond plus au fichier est INVALIDE — R3 refuse en CITANT les deux
        empreintes (celle citée et celle recalculée)."""
        tid = self.new()
        vrai = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        faux = "0" * 64
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace("S-00002000", tid, "plans/complet.md", faux)])
        self.armer()
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empreinte divergente", r.stderr)
        self.assertIn(faux, r.stderr)
        self.assertIn(vrai, r.stderr)

    def test_done_emprunt_non_enrolant_refuse(self):
        """MUTANT : condition d'enrôlement retirée. Un slot dont le plan ne NOMME
        pas la tâche ne peut pas prêter sa cible — R2 le saute, R3 refuse."""
        sub = self.new()
        slot = self.new()
        sha = self.ecrire_plan("plans/slot_autre.md", self.PLAN_SLOT_AUTRE)
        self.ecrire_specs([self.decision("S-00001558", sub),
                           self.trace("S-00002000", slot, "plans/slot_autre.md", sha)])
        self.armer()
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucun plan approuvé", r.stderr)

    def test_done_enrolement_hors_ligne_Taches_refuse(self):
        """MUTANT : enrôlement cherché par sous-chaîne sur tout le fichier. Un id
        présent dans le CORPS mais ni en ligne 1 ni sur la ligne `Tâches :`
        n'enrôle pas — R3 refuse en CITANT la ligne 1 lue."""
        sub = self.new()
        slot = self.new()
        sha = self.ecrire_plan("plans/slot_corps.md",
                               self.PLAN_SLOT_CORPS.format(sub=sub))
        self.ecrire_specs([self.decision("S-00001558", sub),
                           self.trace("S-00002000", slot, "plans/slot_corps.md", sha)])
        self.armer()
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("n'enrôle pas", r.stderr)
        self.assertIn("Ligne 1 lue", r.stderr)
        self.assertIn("# Plan slot", r.stderr)

    def test_done_choisit_derniere_approbation_valide(self):
        """MUTANT : `max`→`min` sur la S-id. Entre deux traces valides, la
        résolution retient la PLUS RÉCENTE — ici la S-00003000 vers un plan
        COMPLET, jamais la S-00002000 vers un plan incomplet."""
        tid = self.new()
        sha_inc = self.ecrire_plan("plans/incomplet.md",
                                   self.PLAN_INCOMPLET.format(tid=tid))
        sha_com = self.ecrire_plan("plans/complet.md",
                                   self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([
            self.decision("S-00001558", tid),
            self.trace("S-00002000", tid, "plans/incomplet.md", sha_inc),
            self.trace("S-00003000", tid, "plans/complet.md", sha_com),
        ])
        self.armer()
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_sans_slot_refuse(self):
        """MUTANT : polarité R3 inversée (le refus devient un laissez-passer).
        Sans AUCUNE trace d'approbation, le `done` est refusé fail-closed en
        NOMMANT l'absence de trace."""
        tid = self.new()
        self.ecrire_specs([self.decision("S-00001558", tid)])
        self.armer()
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucune trace d'approbation", r.stderr)

    def test_done_propre_plan_sans_cible_refuse(self):
        """MUTANT : contrôle des étapes sauté au `done`. Une trace propre vers un
        plan INCOMPLET fait refuser la clôture en nommant l'étape fautive."""
        tid = self.new()
        sha = self.ecrire_plan("plans/incomplet.md",
                               self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace("S-00002000", tid, "plans/incomplet.md", sha)])
        self.armer()
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("étape deux SANS cible", r.stderr)

    def test_done_sans_cible_passe(self):
        """MUTANT : `--sans-cible` non relayé au `done`. La dérogation ferme la
        tâche MALGRÉ l'absence de plan approuvé, et sa raison reste VISIBLE."""
        tid = self.new()
        self.armer()
        r = self.done(tid, "--sans-cible", "plan figé @ banc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[SANS CIBLE : plan figé @ banc]", self.board_stage(tid))

    def test_done_hors_chantier_inerte(self):
        """MUTANT : comparaison de chantier retirée. Une tâche d'un AUTRE chantier
        se ferme sans contrainte, même sans plan approuvé."""
        tid = self.new(chantier="autre-chantier")
        self.armer(chantier=self.CHANTIER)
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_marqueur_absent_inerte(self):
        """MUTANT : test d'existence du marqueur retiré. Sans marqueur, la garde
        est INERTE — une clôture sans plan approuvé passe."""
        tid = self.new()
        # PAS de marqueur.
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_cli_done_arme_sous_processus(self):
        """MUTANT : plan_cible importe `tasks` et REPREND `board_lock`.
        SOUS-PROCESSUS réel : `tasks.py done` sous marqueur armé, avec une trace
        vers un plan COMPLET, se termine SANS interblocage (isolation D6) — un
        ré-emprunt du verrou interbloquerait jusqu'au timeout borné."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace("S-00002000", tid, "plans/complet.md", sha)])
        self.armer()
        r = self.done(tid, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)

    def test_done_plan_enrolant_ancien_non_masque_par_un_recent(self):
        """MUTANT : enrôlement remis en POST-contrôle de l'élu (À CORRIGER 1).
        Sur un même slot, un plan de lot RÉCENT (S-id plus haute) qui n'enrôle
        PAS la tâche ne doit pas masquer un plan plus ANCIEN qui l'enrôle :
        l'enrôlement FILTRE le vivier, il ne post-contrôle pas le seul élu."""
        sub = self.new()
        slot = self.new()
        sha_enrole = self.ecrire_plan("plans/slot_enrole.md",
                                      self.PLAN_SLOT_ENROLE.format(sub=sub))
        sha_autre = self.ecrire_plan("plans/slot_autre.md", self.PLAN_SLOT_AUTRE)
        self.ecrire_specs([
            self.decision("S-00001558", sub),
            self.trace("S-00002000", slot, "plans/slot_enrole.md", sha_enrole),
            self.trace("S-00003000", slot, "plans/slot_autre.md", sha_autre),
        ])
        self.armer()
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ done", r.stdout)
        # l'emprunt NOMME le plan ANCIEN qui enrôle, jamais le récent
        self.assertIn("slot_enrole.md (S-00002000)", self.board_stage(sub))

    def test_done_marqueur_malforme_refuse(self):
        """MUTANT : marqueur malformé traité comme absent au `done`. Un marqueur
        présent mais sans `spec=`/`chantier=` fait refuser la clôture
        (fail-closed, cause NOMMÉE), jamais un laissez-passer."""
        tid = self.new()
        self.armer(contenu="ni spec ni chantier ici\n")
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("malformé", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_done_spec_marqueur_absente_refuse_nomme(self):
        """MUTANT : repli `Path(root)/spec_rel` sans garde (À CORRIGER 2). Une
        spec de marqueur absente du disque fait un refus NOMMÉ, jamais un
        traceback. Une trace d'approbation VALIDE est posée pour atteindre
        `_registre_pour` (R1 résout d'abord)."""
        tid = self.new()
        sha = self.ecrire_plan("plans/complet.md", self.PLAN_COMPLET.format(tid=tid))
        self.ecrire_specs([self.decision("S-00001558", tid),
                           self.trace("S-00002000", tid, "plans/complet.md", sha)])
        self.armer(spec_rel="specs/absente.md")  # jamais écrite
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("spec du marqueur PLAN_CIBLE_REQUIRED inexploitable", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_done_specs_corrompu_fail_closed(self):
        """MUTANT : `entrees_specs` rend `[]` en silence sur un JSON corrompu
        (fable C6). Un SPECS.json présent mais illisible fait un refus
        fail-closed NOMMÉ, jamais un diagnostic FAUX « aucune trace »."""
        tid = self.new()
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            "{ ceci n'est pas du JSON", encoding="utf-8")
        self.armer()
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("corrompu", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_entree_specs_non_dict_refuse(self):
        """MUTANT : filtre `isinstance(e, dict)` retiré d'`entrees_specs` (fable
        C6). Une entrée SPECS qui n'est pas un objet lèverait un AttributeError
        muet plus loin ; on la refuse NOMMÉ, fail-closed."""
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 1, "entries": ["pas un objet"]}),
            encoding="utf-8")
        with self.assertRaises(pc.CibleError) as ctx:
            pc.entrees_specs(str(self.d))
        self.assertIn("n'est pas un objet", str(ctx.exception))

    def test_sans_cible_sans_marqueur_aucune_marque(self):
        """MUTANT : marque `[SANS CIBLE]` au done écrite sans condition de
        marqueur (décision orchestrateur). Un adoptant DÉSARMÉ (marqueur absent)
        qui ferme avec --sans-cible ne doit voir AUCUNE marque au board — sinon
        chaque clôture passant par le pont V3 la porterait."""
        tid = self.new()
        # PAS de marqueur.
        r = self.done(tid, "--sans-cible", "raison quelconque")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("[SANS CIBLE", self.board_stage(tid))


# ===========================================================================
# JAMBE VERDICT (D5) — appels DIRECTS sur `refus_au_verdict`, et wiring `specs.py`.
# ===========================================================================
class VerdictDirectTests(_BaseStart):
    """Le filtre D5 lui-même, sans passer par `specs.py` : la garde ne mord que
    sur un verdict plan-critic FAVORABLE portant `plan=`, et laisse tout le reste
    passer SANS lecture."""

    def _prep(self, incomplet=True):
        tid = self.new()
        self.armer()
        self.ecrire_specs([self.decision("S-00001558", tid)])
        rel = "plans/incomplet.md" if incomplet else "plans/complet.md"
        gabarit = self.PLAN_INCOMPLET if incomplet else self.PLAN_COMPLET
        self.ecrire_plan(rel, gabarit.format(tid=tid))
        return tid, rel

    def test_verdict_no_go_enregistre(self):
        """MUTANT : filtre de statut D5 retiré. Un verdict NON éligible (NO_GO)
        n'est jamais contrôlé, même s'il cite un plan incomplet."""
        tid, rel = self._prep()
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : NO_GO", f"plan={rel}"))

    def test_verdict_security_code_review_passe(self):
        """MUTANT : filtre de titre D5 retiré. Un verdict qui n'est pas titré
        plan-critic (security-code-review) passe sans contrôle."""
        tid, rel = self._prep()
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict", "security-code-review : HIGH", f"plan={rel}"))

    def test_verdict_design_review_passe(self):
        """MUTANT : filtre de titre D5 retiré. Un verdict design-review passe
        sans contrôle, même en citant un plan incomplet."""
        tid, rel = self._prep()
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict", "design-review : [Blocker]", f"plan={rel}"))

    def test_verdict_sans_plan_passe(self):
        """MUTANT : filtre `plan=` D5 retiré. Un verdict plan-critic favorable
        SANS `plan=` ne cite aucun plan à contrôler — il passe."""
        tid, _rel = self._prep()
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : GO", "aucun plan cité ici"))

    def test_verdict_plan_critic_sonnet_max_passe(self):
        """MUTANT : grammaire de titre élargie (le `(?![\\w-])` recopié de
        night_approve retiré). Un titre `plan-critic-sonnet-max` n'est PAS
        `plan-critic` au sens de la grammaire ANCRÉE — la jambe ne se déclenche
        pas. C'est `is_plan_critic_verdict` qui porte la discrimination : le
        verdict de PAIRE (Critique B) ne mord pas, la trace `plan approuvé` étant
        la morsure porteuse."""
        self.assertFalse(
            pc.is_plan_critic_verdict({"title": "plan-critic-sonnet-max it.1 : GO"}),
            "un titre à suffixe ne doit pas être vu comme plan-critic")
        # non-vacuité : un vrai `plan-critic` EST reconnu.
        self.assertTrue(pc.is_plan_critic_verdict({"title": "plan-critic it.1 : GO"}))
        tid, rel = self._prep()
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict",
            "plan-critic-sonnet-max it.1 : GO", f"plan={rel}"))

    def test_verdict_marqueur_absent_inerte(self):
        """MUTANT : test d'existence du marqueur retiré. Sans marqueur, la jambe
        verdict est INERTE, même pour un verdict plan-critic favorable vers un
        plan incomplet."""
        tid = self.new()
        self.ecrire_specs([self.decision("S-00001558", tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        # PAS de marqueur.
        self.assertIsNone(pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : GO",
            "plan=plans/incomplet.md"))

    def test_plan_cite_par_verdict_chemin_non_sur_refuse(self):
        """MUTANT : le bras « chemin non sûr » rend None au lieu de refuser. Un
        verdict plan-critic favorable qui cite un `plan=` hors racine est REFUSÉ."""
        tid, _rel = self._prep()
        refus = pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : GO", "plan=/etc/passwd")
        self.assertIsNotNone(refus)
        self.assertIn("non sûr", refus)

    def test_verdict_plan_sans_cible_refuse_appel_direct(self):
        """MUTANT : jambe verdict retirée. Un verdict plan-critic favorable vers
        un plan INCOMPLET est refusé en nommant l'étape fautive."""
        tid, rel = self._prep()
        refus = pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : GO", f"plan={rel}")
        self.assertIsNotNone(refus)
        self.assertIn("étape deux SANS cible", refus)

    def test_verdict_plan_repertoire_refuse_sans_traceback(self):
        """MUTANT : `is_file()` retiré de `chemin_de_plan_sur` (fable C5). Un
        `plan=` qui résout sur un RÉPERTOIRE de suffixe `.md` ne doit pas
        atteindre `read_text`/`read_bytes` (IsADirectoryError en traceback) : la
        résolution le rejette et le refus est NOMMÉ « non sûr »."""
        tid, _rel = self._prep()
        (self.d / "plans" / "un_repertoire.md").mkdir()
        refus = pc.refus_au_verdict(
            str(self.d), tid, "verdict", "plan-critic it.1 : GO",
            "plan=plans/un_repertoire.md")
        self.assertIsNotNone(refus)
        self.assertIn("non sûr", refus)


class VerdictWiringTests(_BaseStart):
    """La greffe dans `specs.py add` : refus AVANT écriture, sortie `--sans-cible`,
    et import PARESSEUX de `plan_cible`."""

    def specs_cli(self, *args, timeout=60):
        return subprocess.run(
            [sys.executable, str(SPECS), "--root", str(self.d), *args],
            capture_output=True, text=True, timeout=timeout)

    def specs_entries(self):
        p = self.d / ".agents" / "state" / "specs" / "SPECS.json"
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))["entries"]

    def _prep_incomplet(self):
        tid = self.new()
        self.armer()
        self.ecrire_specs([self.decision("S-00001558", tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        return tid

    def test_verdict_plan_sans_cible_refuse(self):
        """MUTANT : jambe verdict retirée de `specs.py`. `specs.py add` d'un
        verdict plan-critic favorable vers un plan incomplet est refusé (rc 2)."""
        tid = self._prep_incomplet()
        r = self.specs_cli("add", "plan-critic it.1 : GO", "--task", tid,
                           "--kind", "verdict", "--text", "plan=plans/incomplet.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("étape deux SANS cible", r.stderr)

    def test_verdict_refuse_n_ecrit_rien(self):
        """MUTANT : greffe déplacée APRÈS `save`. Un verdict refusé n'ajoute
        AUCUNE entrée au journal — le refus précède le verrou et l'écriture."""
        tid = self._prep_incomplet()
        avant = len(self.specs_entries())
        r = self.specs_cli("add", "plan-critic it.1 : GO", "--task", tid,
                           "--kind", "verdict", "--text", "plan=plans/incomplet.md")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(self.specs_entries()), avant,
                         "une entrée a été écrite malgré le refus")

    def test_verdict_sans_cible_trace_dans_le_texte(self):
        """MUTANT : `--sans-cible` non joint au texte sur `specs.py add`. La
        dérogation enregistre le verdict ET marque la raison dans le texte."""
        tid = self._prep_incomplet()
        r = self.specs_cli("add", "plan-critic it.1 : GO", "--task", tid,
                           "--kind", "verdict", "--text", "plan=plans/incomplet.md",
                           "--sans-cible", "plan figé au banc")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        textes = [e["text"] for e in self.specs_entries() if e["task"] == tid
                  and e["kind"] == "verdict"]
        self.assertTrue(any("[SANS CIBLE : plan figé au banc]" in t for t in textes),
                        textes)

    def test_import_paresseux(self):
        """MUTANT : `import plan_cible` remonté en tête de `specs.py`. SOUS-PROCESSUS :
        prouve SEULEMENT qu'importer `specs` ne tire pas `plan_cible`, chargé ensuite
        sur tout verdict `plan-critic…` hors --sans-cible, armé ou non, NO_GO compris."""
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(BIN)!r})\n"
            "import specs\n"
            "assert 'plan_cible' not in sys.modules, 'plan_cible importé au chargement'\n"
            "print('LAZY-OK')\n"
        )
        with tempfile.TemporaryDirectory() as cwd:
            r = subprocess.run([sys.executable, "-c", script],
                               cwd=cwd, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"{r.stdout}\n{r.stderr}")
        self.assertIn("LAZY-OK", r.stdout)

    def test_verdict_hors_chantier_inerte(self):
        """MUTANT : contrôle du `chantier=` retiré de la jambe verdict (BLOQUANT
        1). La phrase canonique promet « tâche hors chantier : rien ne change ».
        Un verdict plan-critic FAVORABLE vers un plan INCOMPLET est ENREGISTRÉ
        (rc 0) quand la tâche est d'un AUTRE chantier ET quand elle est ABSENTE
        du board."""
        autre = self.new(chantier="autre-chantier")
        self.armer(chantier=self.CHANTIER)
        self.ecrire_specs([self.decision("S-00001558", autre)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=autre))
        r = self.specs_cli("add", "plan-critic it.1 : GO", "--task", autre,
                           "--kind", "verdict", "--text", "plan=plans/incomplet.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # tâche ABSENTE du board : la garde est inerte de la même façon.
        r2 = self.specs_cli("add", "plan-critic it.1 : GO", "--task", "T-99999999",
                            "--kind", "verdict", "--text", "plan=plans/incomplet.md")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_verdict_marqueur_malforme_refuse_rc2(self):
        """MUTANT : `except SpecsError` seul dans `specs.py add` — `CibleError`
        non enveloppée (BLOQUANT 2 bis). Un marqueur MALFORMÉ fait un refus NOMMÉ
        rc 2 sur `specs.py add`, jamais un traceback rc 1."""
        tid = self.new()
        self.armer(contenu="ceci n'est pas un marqueur valide\n")
        self.ecrire_specs([self.decision("S-00001558", tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        r = self.specs_cli("add", "plan-critic it.1 : GO", "--task", tid,
                           "--kind", "verdict", "--text", "plan=plans/incomplet.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("malformé", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class IsolationSpecsTests(_BaseStart):
    def test_specs_lecture_hors_verrou_coherente(self):
        """MUTANT : lecture de `SPECS.json` déplacée SOUS `store_lock`. La jambe
        verdict relit le journal AVANT de prendre le verrou (licite : `save` est
        atomique). Un porteur concurrent tient le verrou : le code correct refuse
        tout de suite (cible), le mutant ATTEND le verrou et EXPIRE."""
        specs = _charger("specs_iso", BIN / "specs.py")
        tid = self.new()
        self.armer()
        self.ecrire_specs([self.decision("S-00001558", tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))

        held = threading.Event()
        release = threading.Event()

        def porteur():
            with specs.store_lock(str(self.d)):
                held.set()
                release.wait(timeout=10)

        t = threading.Thread(target=porteur)
        t.start()
        try:
            self.assertTrue(held.wait(timeout=5), "le porteur n'a pas pris le verrou")
            specs._STORE_LOCK_TIMEOUT_SECONDS = 0.4
            with self.assertRaises(specs.SpecsError) as ctx:
                specs.add_entry(str(self.d), tid, "verdict",
                                "plan-critic it.1 : GO", "plan=plans/incomplet.md")
            message = str(ctx.exception)
            self.assertIn("n'annote pas toutes ses étapes", message)
            self.assertNotIn("store lock", message)
            self.assertNotIn("timed out", message)
        finally:
            release.set()
            t.join()


class PerformanceGrammaireTests(unittest.TestCase):
    """Le motif de `cible:` reste LINÉAIRE sur une entrée adverse.

    Revue sécurité du 2026-09-18, finding HIGH : `cible\\s*:\\s*«\\s*(.+?)\\s*»`
    était QUADRATIQUE — mesuré 3,5 s sur 60 Ko de `cible : «` jamais fermés, plus
    de 20 s sur 500 Ko, et ce PENDANT que `set_state` tient `board_lock`. Un plan
    mal formé gelait donc la clôture des tâches, c'est-à-dire le geste même que
    cette garde protège. Mutation qui rougit ce témoin : rendre la classe de
    caractères générique (`(.+?)` au lieu de `([^»\\n]{1,300}?)`).
    """

    def test_le_motif_cible_ne_degenere_pas_sur_une_entree_adverse(self):
        module = pc
        # 58 Ko : taille où le motif dégénéré met 3,5 s (mesuré) et le motif
        # borné 0,054 s. Volontairement PAS 500 Ko : là, le dégénéré ne rend
        # plus la main du tout, et un témoin qui PEND bloque la porte au lieu
        # de rougir (mesuré le 2026-09-18 : tué à 60 s).
        adverse = "cible : « " * 6000
        self.assertGreater(len(adverse), 50_000, "population non vide")
        debut = time.monotonic()
        trouves = list(module._CIBLE.finditer(adverse))
        ecoule = time.monotonic() - debut
        self.assertEqual(trouves, [], "aucune cible ne se ferme dans cette entrée")
        self.assertLess(
            ecoule, 1.0,
            "motif dégénéré : " + str(round(ecoule, 2)) + " s sur 58 Ko — "
            "le quadratique est revenu (mesuré 0,054 s après la borne, 3,5 s avant)",
        )

    def test_la_borne_ne_casse_pas_la_capture_nominale(self):
        module = pc
        self.assertEqual(
            module._CIBLE.findall("   cible: « socle inviolable »\n"),
            ["socle inviolable"],
        )


class ModuleAbsentTests(unittest.TestCase):
    """`tasks.py` et ses parties `tasks_*.py`, SANS le module frère `plan_cible.py`, restent utilisables.

    Mesuré le 2026-09-18 : `.claude/hooks/run-recap.test.sh` copie `tasks*.py`
    sans `plan_cible.py` dans un dépôt jetable puis appelle `start` — la porte
    rougissait sur un TRACEBACK (`ModuleNotFoundError: plan_cible`), pas sur une
    propriété. Un harnais, une copie partielle ou un adoptant qui copie
    `tasks*.py` sans `plan_cible.py` ne doit pas casser : module absent = garde
    INERTE, même polarité que marqueur absent. MUTANT qui rougit ce témoin :
    retirer le `except ModuleNotFoundError` de `plan_cible_module()`.

    FRÈRES D'ALLOCATION (plan T-00000726, E13). Une copie de `tasks*.py` sans
    frère LIT comme aujourd'hui — `plan_cible.py` absent = garde INERTE,
    `record_id.py` absent = lecture INCHANGÉE (M33, `RecordIdAbsentLectureTests`) ;
    l'ALLOCATION exige, depuis C2, `record_id.py` ET `src/cadre/ledger/ids.py`
    (ou le paquet `cadre`) : un harnais qui alloue les provisionne. Ces trois
    témoins créent par `new` (et `specs.py add`) : le `setUp` pose donc les deux
    frères, et les ids sont CAPTURÉS, jamais prédits.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cible-sans-module-"))
        (self.tmp / ".agents" / "bin").mkdir(parents=True)
        (self.tmp / ".agents" / "state" / "local").mkdir(parents=True)
        for p in BIN.glob("tasks*.py"): (self.tmp / ".agents" / "bin" / p.name).write_bytes(p.read_bytes())
        self.assertFalse((self.tmp / ".agents" / "bin" / "plan_cible.py").exists())
        (self.tmp / ".agents" / "bin" / "record_id.py").write_bytes((BIN / "record_id.py").read_bytes())
        _poser_generateur(self.tmp)

    def _nouvelle(self, *argv):
        """`new`, puis l'id RENDU (« TASKS: <id> → pending ») — jamais un id prédit."""
        r = self._tasks("new", *argv)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        self.assertIsNotNone(trouve, r.stdout)
        return trouve.group(1)

    def _tasks(self, *argv):
        return subprocess.run(
            [sys.executable, str(self.tmp / ".agents" / "bin" / "tasks.py"), *argv],
            capture_output=True, text=True, env={**os.environ,
                                                 "CLAUDE_PROJECT_DIR": str(self.tmp)},
        )

    def test_start_et_done_passent_sans_le_module_frere(self):
        tid = self._nouvelle("sonde", "--owner", "dev-mono")
        r = self._tasks("start", tid, "--stage", "dev-mono")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        d = self._tasks("done", tid, "--raison", "sonde",
                        "--sans-binome", "sonde")
        self.assertEqual(d.returncode, 0, d.stdout + d.stderr)
        self.assertNotIn("Traceback", d.stderr)

    def test_cible_check_dit_pourquoi_il_ne_peut_rien_verifier(self):
        r = self._tasks("cible-check", "docs/tasks/x.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("plan_cible.py", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_marqueur_arme_sans_module_refuse_au_lieu_de_desarmer(self):
        """L'ÉCHAPPATOIRE À DEUX GESTES, refermée (revue de clôture, C3).

        `git rm .agents/bin/plan_cible.py` n'est refusé par AUCUN hook de ce
        dépôt — `safe-bash.decide_git()` ne connaît que `clean`/`restore`/
        `checkout`, et `BLOCKED_PATTERNS` ne cite pas `.agents/bin/`. Sans ce
        témoin, ce seul geste rendait `start` et `done` muets sur un chantier
        ARMÉ, et sans même écrire la marque `[SANS CIBLE : …]` qui aurait laissé
        une trace au board : la contrainte disparaissait sans un octet.

        MUTANT qui rougit ce témoin : faire rendre `False` à
        `cible_inexploitable()`, ou retirer l'un des deux appels dans
        `set_state`. La polarité INVERSE (module absent ET marqueur absent =
        inerte) reste tenue par les deux témoins ci-dessus, qui ne posent aucun
        marqueur — les deux cas se distinguent donc, au lieu de se confondre.
        """
        (self.tmp / ".agents" / "state" / "gates").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            "spec=docs/spec.md\nchantier=peu-importe\n", encoding="utf-8")
        tid = self._nouvelle("sonde", "--owner", "dev-mono")

        r = self._tasks("start", tid, "--stage", "dev-mono")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("INEXPLOITABLE", r.stderr)
        self.assertIn("plan_cible.py", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

        # La sortie tracée reste praticable — et elle MARQUE le board, alors que
        # l'ancien silence n'y laissait rien.
        s = self._tasks("start", tid, "--stage", "dev-mono",
                        "--sans-cible", "module retiré, sonde")
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        d = self._tasks("done", tid, "--raison", "sonde",
                        "--sans-binome", "sonde")
        self.assertEqual(d.returncode, 2, d.stdout + d.stderr)
        self.assertIn("INEXPLOITABLE", d.stderr)

    def test_specs_arme_sans_module_refuse_un_verdict_plan_critic(self):
        """LE JUMEAU OUBLIÉ (revue de clôture, T4). `dd36712` n'avait corrigé que
        `tasks.py` : `specs.py` copié seul traçait un `ModuleNotFoundError` sur
        un verdict `plan-critic` portant un `plan=`. Le banc restait vert parce
        que le seul harnais qui copie `specs.py` seul n'écrit pas de verdict —
        absence de COUVERTURE, pas absence de défaut.

        MUTANT : retirer le `except ModuleNotFoundError` de `_plan_cible_module`
        (traceback), ou lui faire ignorer le marqueur (refus perdu).
        """
        specs_src = TASKS.parent / "specs.py"
        (self.tmp / ".agents" / "bin" / "specs.py").write_bytes(specs_src.read_bytes())
        (self.tmp / ".agents" / "state" / "specs").mkdir(parents=True, exist_ok=True)

        def _specs(*argv):
            return subprocess.run(
                [sys.executable, str(self.tmp / ".agents" / "bin" / "specs.py"), *argv],
                capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.tmp)})

        # Marqueur ABSENT : garde inerte, aucun traceback, l'entrée s'écrit.
        r = _specs("add", "--task", "T-00000001", "--kind", "verdict",
                   "plan-critic GO", "--text", "plan=docs/tasks/x.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

        # Marqueur PRÉSENT, module absent : refus nommé.
        (self.tmp / ".agents" / "state" / "gates").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            "spec=docs/spec.md\nchantier=peu-importe\n", encoding="utf-8")
        r2 = _specs("add", "--task", "T-00000001", "--kind", "verdict",
                    "plan-critic GO", "--text", "plan=docs/tasks/x.md")
        self.assertEqual(r2.returncode, 2, r2.stdout + r2.stderr)
        self.assertIn("INEXPLOITABLE", r2.stderr)
        self.assertNotIn("Traceback", r2.stderr)


class RecordIdAbsentLectureTests(unittest.TestCase):
    """M33 (plan T-00000726, étape 2 ; forme A, décision S-00003552) — une copie
    de `tasks*.py` SANS `record_id.py` NI `src/` LIT un board MIXTE comme un
    board ancien : `list` (et `--session`, `--json`), `start`, `block --on`,
    `unblock` et `done` rendent 0 et voient les trois ids.

    CLASSE DISTINCTE de `ModuleAbsentTests`, dont le `setUp` PROVISIONNE les
    frères d'allocation : ici on n'en copie AUCUN, et le board est écrit à la
    main (aucune allocation). Rouge sur le code d'avant T-00001038
    (`numeric_id` lève sur `T-<U_LETTER>`), rouge sous la forme « accesseur »
    (une LECTURE qui charge le frère et lève s'il manque : mutant M33-acc),
    rouge à la porte de C2 si un chemin de lecture appelle l'accesseur (M35).
    `done` n'exige ici que `--raison` : la copie ne porte aucun marqueur
    (relevé au banc, pas deviné)."""

    U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"  # finit par une LETTRE
    U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"   # finit par « 2 »

    def setUp(self):
        dossier = tempfile.TemporaryDirectory(prefix="m33-sans-record-id-", ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        self.tmp = Path(dossier.name)
        bin_ = self.tmp / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for p in BIN.glob("tasks*.py"):
            (bin_ / p.name).write_bytes(p.read_bytes())
        self.assertFalse((bin_ / "record_id.py").exists())
        self.assertFalse((self.tmp / "src").exists())
        self.ids = ("T-00000001", f"T-{self.U_LETTER}", f"T-{self.U_DIGIT}")
        board = self.tmp / ".agents" / "state" / "board"
        board.mkdir(parents=True)
        lignes = [{"id": tid, "state": "pending", "task": f"tache {tid[-4:]}", "owner": "dev-multi",
                   "stage": "", "updated": "2026-10-02"} for tid in self.ids]
        (board / "TASKS.json").write_text(json.dumps({"tasks": lignes}), encoding="utf-8")
        self.tasks_affichage = _charger("tasks_m33_affichage", TASKS)

    def _tasks(self, *argv):
        return subprocess.run(
            [sys.executable, str(self.tmp / ".agents" / "bin" / "tasks.py"), *argv],
            capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.tmp)},
        )

    def _montre(self, tid):
        """L'id tel qu'une VUE le montre : coupé à `WIDTHS["id"]` tant que C2 ne l'élargit pas."""
        return self.tasks_affichage.fit(tid, self.tasks_affichage.WIDTHS["id"]).strip()

    def _etats(self):
        r = self._tasks("list", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return {t["id"]: t for t in json.loads(r.stdout)}

    def test_m33_une_copie_sans_record_id_lit_un_board_mixte_et_le_fait_vivre(self):
        self.assertEqual(set(self.ids), set(self._etats()))
        for vue in (("list",), ("list", "--session")):
            r = self._tasks(*vue)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for tid in self.ids:
                self.assertIn(self._montre(tid), r.stdout, f"{' '.join(vue)} ne montre pas {tid}")

        legacy, lettre, _chiffre = self.ids
        for argv in (("start", legacy, "--stage", "dev-multi"),
                     ("block", legacy, "--on", lettre),
                     ("unblock", legacy),
                     ("done", lettre, "--raison", "M33")):
            r = self._tasks(*argv)
            self.assertEqual(r.returncode, 0, f"{' '.join(argv)} : {r.stdout}{r.stderr}")
            self.assertNotIn("Traceback", r.stderr)
            if argv[0] == "block":
                self.assertEqual(lettre, self._etats()[legacy].get("blocked_on"))

        etats = self._etats()
        self.assertEqual("done", etats[lettre]["state"])
        self.assertEqual("pending", etats[legacy]["state"])  # `unblock` rend la tâche à pending
        self.assertFalse((self.tmp / ".agents" / "bin" / "record_id.py").exists())


class MarqueurLectureTests(_BaseStart):
    """La LECTURE du marqueur : BOM, doublons, chantier fantôme."""

    def test_bom_utf8_ne_ment_pas_sur_la_cause(self):
        """T5 — un marqueur posé sous Windows porte une BOM ; elle se collait au
        `s` de `spec=`, la ligne ne matchait plus, et le refus annonçait « il
        doit porter une ligne `spec=` » ALORS QU'ELLE Y ÉTAIT. MUTANT : repasser
        `lire_marqueur` en `encoding="utf-8"`."""
        self.armer(contenu="﻿spec=spec.md\nchantier=" + self.CHANTIER + "\n")
        self.assertEqual(
            pc.lire_marqueur(self.d), ("spec.md", self.CHANTIER))

    def test_deux_lignes_spec_refusent_au_lieu_du_dernier_gagne(self):
        """C4 — l'ancienne boucle écrasait : le pilote relisait la PREMIÈRE
        ligne, la garde s'armait sur la SECONDE. MUTANT : revenir à
        `spec = ms.group(1)` dans la boucle."""
        self.armer(contenu="spec=a.md\nspec=b.md\nchantier=" + self.CHANTIER + "\n")
        with self.assertRaises(pc.CibleError) as ctx:
            pc.lire_marqueur(self.d)
        self.assertIn("ambigu", str(ctx.exception))
        self.assertIn("«a.md»", str(ctx.exception))
        self.assertIn("«b.md»", str(ctx.exception))

    def test_deux_lignes_chantier_refusent(self):
        self.armer(contenu="spec=spec.md\nchantier=un\nchantier=deux\n")
        with self.assertRaises(pc.CibleError):
            pc.lire_marqueur(self.d)

    def test_chantier_qui_ne_nomme_aucune_tache_AVERTIT(self):
        """T1 — LE DÉSARMEMENT SILENCIEUX, rendu BRUYANT. Mesuré avant
        correction : `chantier=refonte-packaging # armé le 18/09` (commentaire)
        et `chantier=refonte-Packaging` (majuscule) laissaient `done` passer
        rc 0 EN SILENCE — la comparaison échouait pour TOUTES les tâches, donc
        la garde se taisait partout, et le pilote la croyait armée.

        Le `done` PASSE toujours (rc 0) : refuser board-entier contredirait la
        clause canonique « tâche hors chantier : rien ne change », que trois
        autres témoins de ce fichier tiennent. Ce qui change, c'est que stderr
        le DIT. MUTANT : retirer l'appel à `avertissement_chantier` dans
        `evaluer_done`, ou lui faire rendre `None` inconditionnellement.
        """
        for faux in (f"{self.CHANTIER} # armé le 18/09", "refonte-Packaging"):
            with self.subTest(faux=faux):
                tid = self.new()
                self.armer(contenu=f"spec=spec.md\nchantier={faux}\n")
                r = self.tasks("done", tid, "--raison", "sonde",
                               "--sans-binome", "sonde")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("AVERTISSEMENT", r.stderr)
                self.assertIn("ne mordra donc sur RIEN", r.stderr)
                self.assertIn(self.CHANTIER, r.stderr)  # les chantiers connus
                self.assertNotIn("Traceback", r.stderr)

    def test_chantier_exact_n_avertit_pas(self):
        """La polarité INVERSE : sans elle, un avertissement inconditionnel
        satisferait le témoin ci-dessus."""
        tid = self.new()
        self.armer()
        r = self.tasks("done", tid, "--raison", "sonde", "--sans-binome", "sonde")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("AVERTISSEMENT", r.stderr)
        self.assertIn("aucun plan approuvé", r.stderr)

    def test_le_refus_r3_donne_le_chemin_NOMINAL_pas_seulement_la_sortie(self):
        """TROU 1 — sur les 53 tâches ouvertes du chantier, la seule commande
        exécutable que le refus proposait était `--sans-cible`. Une garde dont
        le seul geste praticable est sa propre dérogation est désarmée dans la
        semaine. MUTANT : retirer la ligne « Chemin nominal » de
        `_message_refus_r3`, ou n'y nommer que `décision pilote:` (la forme de
        42551627, muette sur `cible: «` et `angle mort:`)."""
        tid = self.new()
        self.armer()
        r = self.tasks("done", tid, "--raison", "sonde", "--sans-binome", "sonde")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Chemin nominal", r.stderr)
        self.assertIn("cible: «", r.stderr)
        self.assertIn("angle mort:", r.stderr)
        # Sans les arêtes, le `specs.py add` proposé ci-dessous refuse.
        self.assertIn("une ligne `ARÊTES: aucune` ou une `ARÊTE:` par dépendance",
                      r.stderr)
        self.assertIn("specs.py add --task " + tid, r.stderr)
        self.assertIn("plan approuvé", r.stderr)
        self.assertIn("--sans-cible", r.stderr)


class VendorSeulGenerateurTests(unittest.TestCase):
    """Témoin B (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot B). Une racine SOURCE « vendor seul » (paquet
    `cadre` sous `.agents/vendor/cadre`, aucun `src/`) provisionne le générateur d'un kit jetable,
    et `mint` y alloue : (1) kit sans `vendor_paths.py`, `ids.py` au repli `<kit>/src/cadre` ;
    (2) kit avec `vendor_paths.py` ET paquet vendor complet, `ids.py` dans ce paquet, que
    `record_id._IDS_PATH` désigne. MUTANT qui rougit : source `source / "src" / "cadre"` dans
    `_poser_generateur` (FileNotFoundError : la racine vendor seul n'a pas de `src/`)."""

    _SONDE = ("import importlib.util as u, sys\n"
              "s = u.spec_from_file_location('record_id', sys.argv[1])\n"
              "m = u.module_from_spec(s); sys.modules['record_id'] = m; s.loader.exec_module(m)\n"
              "print(m._IDS_PATH); print(m.mint('T'))\n")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vendor-seul-b-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paquet = _VENDOR.exiger(ROOT, "cadre")
        self.source = self.tmp / "source"
        shutil.copytree(self.paquet, self.source / ".agents" / "vendor" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.assertFalse((self.source / "src").exists())

    def _kit(self, nom: str, *freres: str) -> Path:
        kit = self.tmp / nom
        (kit / ".agents" / "bin").mkdir(parents=True)
        for frere in ("record_id.py", *freres):
            shutil.copy2(BIN / frere, kit / ".agents" / "bin" / frere)
        return kit

    def _mint(self, kit: Path) -> tuple[Path, str]:
        r = subprocess.run([sys.executable, "-I", "-B", "-c", self._SONDE,
                            str(kit / ".agents" / "bin" / "record_id.py")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        chemin, ident = r.stdout.split()
        self.assertRegex(ident, r"\AT-[0-9A-HJKMNP-TV-Z]{26}\Z")
        return Path(chemin), ident

    def test_vendor_seul_b(self):
        sans = self._kit("kit-sans-resolveur")
        pose = _poser_generateur(sans, self.source)
        self.assertEqual(pose, sans / "src" / "cadre" / "ledger" / "ids.py")
        chemin, _ = self._mint(sans)
        self.assertEqual(chemin.resolve(), pose.resolve())

        complet = self._kit("kit-vendor-complet", "vendor_paths.py")
        shutil.copytree(self.source / ".agents" / "vendor" / "cadre", complet / ".agents" / "vendor" / "cadre")
        pose = _poser_generateur(complet, self.source)
        self.assertEqual(pose.resolve(), (complet / ".agents" / "vendor" / "cadre" / "ledger" / "ids.py").resolve())
        self.assertFalse((complet / "src").exists())
        chemin, _ = self._mint(complet)
        self.assertEqual(chemin.resolve(), pose.resolve())


if __name__ == "__main__":
    unittest.main()
