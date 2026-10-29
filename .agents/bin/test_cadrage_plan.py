#!/usr/bin/env python3
"""Témoins du CADRAGE — `cadrage_plan.py` et la séquence de découpe qu'il annonce (T-01M5AVF0Q5ZB53NG1CW3R5NCYP).

Run: python -m pytest .agents/bin/test_cadrage_plan.py -q

Décisions pilote : S-01M5AQMWW0077BDFZMJAAXJP7S (règle globale, qui voyage), S-01M5AN9N5Q4NNR5RDVQQ5QRFTV (bloc
EN PREMIER), S-01M5ATNMNBYQGYF65SNNZ5JHBN (`start` de l'enfant suivant, `--sans-binome` du parent). Arbres et
boards TEMPORAIRES, jamais l'état du dépôt :
  * SEUILS — `verdict(mesurer(…))`, bornes écrites en LITTÉRAUX ici (11 ; 6 sur 3 surfaces ; 8 mêlant code et
    prose) : un seuil déplacé d'un cran rougit ;
  * INVENTAIRE — surfaces et hôtes de la table fermée (`.agent/` est Antigravity, `.agents/` ne l'est pas) ;
  * COUVERTURE — les refus rc 2 de la CLI : toutes les causes sur stderr, stdout vide ;
  * ORDRE — `fournee` pour un enfant disjoint des `running`, sinon `start` APRÈS LA FUSION de chaque enfant
    précédent qu'il recouvre ; aucun `start` ne rétrograde (T-01M5F7286N1EYGXAXA5244X86B) ;
  * COÛT — la fourchette médiane–p90 PAR TÂCHE de `specs.py chrono` (tous tours cumulés) multipliée par le
    nombre de plans (arbitrage S-01M5BFKA2D), repli « mesure du kit, 18/10 » ;
  * BLOC PREMIER — la sortie ouvre sur `CADRAGE <T>`, ferme sur `FIN CADRAGE`, lignes dans l'ordre du gabarit ;
    un enfant encore au-dessus du seuil le DIT (il n'est jamais re-cadré) ; la ligne `Ordre :` nomme les
    `running` du board, d'un autre chantier comprises, qu'aucun `start` d'enfant ne repasse `pending` ; la ligne
    `Clôture prévue :` déclare `review-scope <parent> <lots> <enfants>` AVANT la revue (C40) ;
  * SOUS-PROCESSUS — un `tasks.py` hors délai ou introuvable rend un refus rc 2, un `specs.py` le repli étiqueté ;
  * AMONT — un enfant qui hérite de l'amont ouvert du parent (`tasks.py depends`) ne démarre pas ;
  * VOYAGE — les cinq chemins de la règle sont pris (TAKE) par `sync_template` (sauté, et dit, sans lui) ;
  * SÉQUENCE — la découpe A, B (deux `LOT:`), C1, C2 jouée de bout en bout par le VRAI `tasks.py` sur un board
    jetable (`--root`, `HOME`, `CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR` temporaires, `BINOME_REQUIRED` posé), dans
    le régime du kit puis dans celui de l'adoptant (`PLAN_CHAIN_REQUIRED`, `PLAN_CIBLE_REQUIRED` `chantier=*`,
    `CHRONO_REQUIRED`, plans à cibles, lots `direct` relevés par `retour` dans un dépôt git ; le parent n'a
    JAMAIS de plan, et chez l'adoptant se clôt avec `--sans-cible`) ; tous les enfants restent `running`, une
    `running` étrangère aussi ; la portée est déclarée, PUIS la revue tracée sur chaque membre comme le fait le
    traceur du lot C, PUIS la porte ; six mutants de séquence rendus rc 2 : A du même chantier mais hors portée,
    portée re-déclarée après la revue, `fournee C1` avec B `running`, revue datée avant la portée, une seconde
    porte qui périme une trace empruntée, le parent de l'adoptant clos sans `--sans-cible` ;
  * DOCTRINE — les trois skills portent la commande, ses options existent dans l'outil, et leurs chiffres et
    leur motif sont ceux du code.
Chaque témoin nomme le mutant qu'il tue (`kills …`). Voyage chez l'adoptant avec son sujet.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = HERE / "cadrage_plan.py"
SKILLS = {
    "planning": ROOT / ".agents" / "skills" / "planning" / "SKILL.md",
    "kickoff": ROOT / ".agents" / "skills" / "kickoff" / "SKILL.md",
    "planning-all": ROOT / ".agents" / "skills" / "planning-all" / "SKILL.md",
}
REGLE = (".agents/bin/cadrage_plan.py", ".agents/bin/test_cadrage_plan.py", ".agents/skills/planning/SKILL.md",
         ".agents/skills/kickoff/SKILL.md", ".agents/skills/planning-all/SKILL.md")
CHANTIER = "cadrage-planification-global"
MOTIF = "parent de coordination sans code"
MOTIF_CIBLE = "parent de découpe sans plan (cadrage)"
COMMANDE = "bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task"
KIT = {"BINOME_REQUIRED": ""}
ADOPTANT = {"BINOME_REQUIRED": "", "PLAN_CHAIN_REQUIRED": "plafond-critique=2\n", "CHRONO_REQUIRED": "",
            "PLAN_CIBLE_REQUIRED": "spec=docs/PROMPT-projet.md\nchantier=*\n"}

# La découpe réelle du parent T-01M5AN76HCMVQ1DDCZTB3J2K1J (17 chemins, 20 affectations, cinq hôtes).
PARTIES_REELLES = (
    ("A", REGLE),
    ("B", (".claude/commands/kickoff.md", ".claude/commands/planning.md", ".claude/commands/planning-all.md",
           "AGENTS.md", ".github/copilot-instructions.md", ".agents/evals/test_cadrage_surfaces.py")),
    ("C1", (".claude/agents/orchestrator.md", ".codex/agents/orchestrator.toml",
            "src/cadre/data/roster/orchestrator.json", ".agents/evals/test_cadrage_surfaces.py")),
    ("C2", (".gemini/agents/orchestrator.md", ".github/agents/orchestrator.agent.md",
            ".kimi-code/agents/orchestrator.md", "src/cadre/data/roster/orchestrator.json",
            ".agents/evals/test_cadrage_surfaces.py")),
)
INVENTAIRE_REEL = list(dict.fromkeys(c for _n, cs in PARTIES_REELLES for c in cs))
GABARIT = ("CADRAGE ", "Titre : ", "Taille mesurée : ", "Verdict : ", "Découpe : ", "Ordre : ", "Clôture prévue : ",
           "Estimation : ", "Suite : ", "FIN CADRAGE")


def _module():
    spec = importlib.util.spec_from_file_location("cadrage_plan_sous_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


CP = _module()


def il_y_a(heures: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=heures)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Board:
    """UN board jetable, la CLI du VRAI `.agents/bin` braquée dessus ; `gates` = marqueurs posés."""

    def __init__(self, case: unittest.TestCase, gates: dict[str, str]):
        self.case, self.gates = case, gates
        self.racine = Path(tempfile.mkdtemp(prefix="cadrage-")).resolve()
        case.addCleanup(shutil.rmtree, self.racine, True)
        self.d = self.racine / "depot"
        for sous in ("depot", "home", "xdg", "etat", "events"):
            (self.racine / sous).mkdir()
        for sous in ("board", "gates", "local/binome", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True)
        for nom, contenu in gates.items():
            (self.d / ".agents" / "state" / "gates" / nom).write_text(contenu, encoding="utf-8")
        (self.d / "docs" / "tasks").mkdir(parents=True)
        (self.d / "docs" / "PROMPT-projet.md").write_text("# spec\n- **« cadrage »** : la règle.\n", encoding="utf-8")
        (self.racine / "home" / ".gitconfig").write_text(
            "[user]\n\tname = banc\n\temail = banc@exemple.invalid\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        self.env.update(HOME=str(self.racine / "home"), XDG_CONFIG_HOME=str(self.racine / "xdg"),
                        CADRE_STATE_DIR=str(self.racine / "etat"), AGENTS_EVENTS_DIR=str(self.racine / "events"))
        self.git = False

    def t(self, *args: str, script: str = "tasks.py") -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(HERE / script), "--root", str(self.d), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=300, env=self.env,
                              check=False)

    def ok(self, *args: str, script: str = "tasks.py") -> subprocess.CompletedProcess[str]:
        r = self.t(*args, script=script)
        if r.returncode != 0:
            raise RuntimeError(f"banc : {script} {args} en échec : {r.stdout}{r.stderr}")
        return r

    def nouvelle(self, titre: str, chantier: str | None = CHANTIER) -> str:
        r = self.ok("new", titre, *(["--chantier", chantier] if chantier else []))
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        if trouve is None:
            raise RuntimeError(f"banc : message de `new` inattendu : {r.stdout}")
        return trouve.group(1)

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def etats(self, *tids: str) -> list[str]:
        return [self.tache(t)["state"] for t in tids]

    def plan(self, tid: str, lots: str, writeset: list[str]) -> None:
        """Un plan À CIBLES, son write-set déclaré, et sa trace `plan approuvé` sur son sha réel."""
        rel = f"docs/tasks/{tid}-plan.md"
        texte = (f"# PLAN {tid}\nTâches : {tid}\n### Étape 1 — écrire\ncible: « cadrage »\n## Lots\n{lots}\n"
                 "ARÊTES: aucune\nPREFLIGHT: à jouer par l’exécuteur\n")
        (self.d / rel).write_text(texte, encoding="utf-8", newline="\n")
        sha = hashlib.sha256((self.d / rel).read_bytes()).hexdigest()
        if writeset:
            self.ok("writeset", tid, *writeset)
        self.ok("add", "--task", tid, "--kind", "decision", "--text", f"plan={rel} revision=1 sha256={sha} ; GO",
                "plan approuvé", script="specs.py")

    def chaine(self) -> None:
        """La chaîne de plan que l'hôte trace (`planner` + `plan-critic`), sous `PLAN_CHAIN_REQUIRED` seul."""
        if "PLAN_CHAIN_REQUIRED" not in self.gates:
            return
        dossier = self.d / ".agents" / "state" / "local" / "plan"
        dossier.mkdir(parents=True, exist_ok=True)
        for nom, role in (("planner", "planner"), ("plan-critic", "reviewer")):
            (dossier / f"{nom}.json").write_text(json.dumps({"sha": "abc1234", "at": il_y_a(0), "role": role}),
                                                 encoding="utf-8")

    def declarer(self, membres: list[str], at: str) -> None:
        """`tasks.py review-scope` réel, puis son `declared_at` ramené à `at` : la chronologie du board jetable
        (déclaration, revue, porte) se pose dans le passé, comme les traces et les portes."""
        self.ok("review-scope", *membres)
        chemin = self.d / ".agents" / "state" / "local" / "review-scope.json"
        portee = json.loads(chemin.read_text(encoding="utf-8"))
        portee["declared_at"] = at
        chemin.write_text(json.dumps(portee), encoding="utf-8")

    def tracer(self, at: str, estampille: bool = True, seul: str | None = None) -> None:
        """Ce que le traceur de l'hôte écrit à l'arrêt du critique de clôture (lot C, T-01M5F728FGJ43QJX1RJKTWWKRB) :
        UNE trace par membre non consommé et non clos de la portée active, estampillée de son `declared_at`.
        `estampille=False` : la trace d'avant ce code (ou posée à la main), sans `portee` ; `seul` : sur ce
        membre seulement, les autres n'ayant que l'emprunt."""
        sha = self.g("rev-parse", "--short", "HEAD").strip() if self.git else "abc1234"
        portee = json.loads((self.d / ".agents" / "state" / "local" / "review-scope.json").read_text(encoding="utf-8"))
        for tid in portee["members"]:
            if tid in portee["consumed"] or self.tache(tid)["state"] == "done" or seul not in (None, tid):
                continue
            trace = {"sha": sha, "at": at, **({"portee": portee["declared_at"]} if estampille else {})}
            chemin = self.d / ".agents" / "state" / "local" / "binome" / f"{tid}.critic-opus.json"
            chemin.write_text(json.dumps(trace), encoding="utf-8")

    def portes(self, *ats: str) -> None:
        """`VERIFY_STAMP.log` : un vert `frozen` par `at`, chacun sur un sha distinct."""
        chemin = self.d / ".agents" / "state" / "local" / "VERIFY_STAMP.log"
        chemin.write_text("".join(f"at={a}\tsha=c0ffee{i}\tmode=frozen\n" for i, a in enumerate(ats)),
                          encoding="utf-8")

    def g(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=self.d, env=self.env, capture_output=True, text=True, timeout=120,
                           check=False)
        if r.returncode != 0:
            raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
        return r.stdout

    def depot_git(self) -> None:
        """Le board devient un dépôt git (état et plans hors suivi) : le canal réel du `retour` d'un lot."""
        self.g("init", "-q", "-b", "main")
        (self.d / ".git" / "info" / "exclude").write_text(".agents/\ndocs/\n", encoding="utf-8")
        (self.d / "LISEZMOI").write_text("base\n", encoding="utf-8")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "base")
        self.git = True

    def livrer_lot(self, lot: str, chemin: str) -> None:
        """Le retour d'un lot `direct` chez l'adoptant : branche, relevé, fusion `--no-ff`, verdict de sécurité."""
        base = self.g("rev-parse", "HEAD").strip()
        branche = f"lot-{lot[-8:].lower()}"
        self.g("checkout", "-q", "-b", branche)
        (self.d / chemin).write_text(f"livré par {lot}\n", encoding="utf-8")
        self.g("add", chemin)
        self.g("commit", "-q", "-m", f"lot {lot}")
        self.g("checkout", "-q", "main")
        self.ok("retour", "--base", base, "--branche", branche, lot)
        self.g("merge", "-q", "--no-ff", "-m", f"fusion {branche}", branche)
        self.ok("add", "--task", lot, "--kind", "verdict", "--text", "CLEAN, 0 HIGH", "security-code-review CLEAN",
                script="specs.py")


class _Cli(unittest.TestCase):
    """La CLI réelle, sur un board jetable qui porte UNE tâche titrée."""

    def board(self) -> tuple[Board, str]:
        b = Board(self, {})
        return b, b.nouvelle("feat: une tâche à cadrer", chantier=None)

    def cadrer(self, b: Board, tid: str, fichiers: list[str], parties: list[str] = (),
               *extra: str) -> subprocess.CompletedProcess[str]:
        args = ["--task", tid, *[x for f in fichiers for x in ("--file", f)], *[x for p in parties
                                                                                for x in ("--part", p)], *extra]
        return b.t(*args, script="cadrage_plan.py")


def _parties_cli() -> list[str]:
    return [f"{nom}={','.join(cs)}" for nom, cs in PARTIES_REELLES]


# --- SEUILS -------------------------------------------------------------------------------------------------
class SeuilsTests(unittest.TestCase):
    """Les seuils en LITTÉRAUX : 11 ; 6 sur 3 surfaces ; 8 mêlant code et prose."""

    def leve(self, chemins: list[str]) -> str:
        return CP.verdict(CP.mesurer(chemins))[0]

    def test_eleven_paths_on_one_surface_cut_and_ten_plan(self):
        # kills « SEUIL_CHEMINS 11 → 12 », « 11 → 10 » and « >= → > »
        chemins = [f".agents/bin/f{i}.json" for i in range(11)]
        self.assertEqual(self.leve(chemins), "découper")
        self.assertEqual(self.leve(chemins[:10]), "planifier")

    def test_six_paths_on_three_surfaces_cut_five_or_two_surfaces_plan(self):
        # kills « 6 → 7 », « 6 → 5 », « 3 surfaces → 4 », « 3 → 2 » and « >= → > » on both terms
        trois = [".agents/bin/a.json", ".agents/evals/b.json", "src/c.json", "src/d.json", "src/e.json", "src/f.json"]
        self.assertEqual(self.leve(trois), "découper")
        self.assertEqual(self.leve(trois[:5]), "planifier")
        deux = [".agents/bin/a.json", ".agents/evals/b.json"] + [f".agents/evals/x{i}.json" for i in range(4)]
        self.assertEqual(self.leve(deux), "planifier")

    def test_eight_mixed_paths_cut_seven_or_unmixed_plan(self):
        # kills « SEUIL_MIXTE 8 → 9 », « 8 → 7 », « mixte ignoré » and « mixte = code OU prose »
        mixtes = [f".agents/bin/m{i}.py" for i in range(4)] + [f".agents/bin/m{i}.md" for i in range(4)]
        self.assertEqual(self.leve(mixtes), "découper")
        self.assertEqual(self.leve(mixtes[1:]), "planifier")
        self.assertEqual(self.leve([f".agents/bin/c{i}.py" for i in range(8)]), "planifier")
        self.assertEqual(self.leve([f".agents/bin/p{i}.md" for i in range(8)]), "planifier")

    def test_the_rule_that_fired_is_named(self):
        # kills « règle muette » : le pilote lit POURQUOI
        self.assertEqual(CP.verdict(CP.mesurer(INVENTAIRE_REEL)), ("découper", "17 chemins ≥ 11"))


# --- INVENTAIRE ---------------------------------------------------------------------------------------------
class InventaireTests(unittest.TestCase):

    def test_the_real_cut_counts_seventeen_paths_ten_surfaces_and_five_hosts(self):
        # kills « table d'hôtes amputée » and « .github/ hors hôtes »
        m = CP.mesurer(INVENTAIRE_REEL)
        self.assertEqual(m["n"], 17)
        self.assertEqual(sorted(m["hotes"]), ["Claude Code", "Codex", "Copilot", "Gemini CLI", "Kimi Code"])
        self.assertEqual(len(m["surfaces"]), 10, m["surfaces"])
        self.assertTrue(m["mixte"])

    def test_antigravity_is_dot_agent_never_dot_agents(self):
        # kills « préfixe `.agent` sans barre » : `.agents/` serait compté hôte Antigravity
        self.assertEqual(CP.surface_de(".agent/skills/x/SKILL.md"), ("Antigravity", True))
        self.assertEqual(CP.surface_de(".agents/skills/x/SKILL.md"), ("skills", False))
        self.assertEqual(CP.surface_de("AGENTS.md"), ("routeur", False))
        self.assertEqual(CP.surface_de("Makefile"), ("racine", False))
        self.assertEqual(CP.surface_de("lib/x.py"), ("autre:lib", False))


# --- ORDRE --------------------------------------------------------------------------------------------------
class OrdreTests(unittest.TestCase):

    def test_the_real_cut_launches_a_and_b_by_fournee_then_starts_after_the_merge(self):
        # kills « tout par fournee », « tout par start » and « recouvrement lu contre le seul précédent »
        phrases = CP.ordre([(n, list(cs)) for n, cs in PARTIES_REELLES])
        self.assertEqual(phrases[0], "A part par `tasks.py fournee`")
        self.assertIn("B, disjoint des enfants `running`, part aussi par `tasks.py fournee`", phrases[1])
        self.assertIn("`tasks.py start C1` APRÈS LA FUSION de B (", phrases[2])
        self.assertIn("`tasks.py fournee C1` si son plan porte des `LOT:`", phrases[2])
        self.assertIn("`tasks.py start C2` APRÈS LA FUSION de B, C1 (", phrases[3])

    def test_a_start_keeps_the_running_set(self):
        # kills « start rétrograde encore » (T-01M5F7286N1EYGXAXA5244X86B) : après `start B`, A reste `running` —
        # C, qui ne recouvre que A, attend la fusion de A, jamais une `fournee` qui recouvrirait A
        phrases = CP.ordre([("A", ["a", "x"]), ("B", ["a", "b"]), ("C", ["x"]), ("D", ["b"])])
        self.assertIn("`tasks.py start B` APRÈS LA FUSION de A (aucune `running` ne repasse `pending`)", phrases[1])
        self.assertIn("C recouvre A (`x`) : `tasks.py start C` APRÈS LA FUSION de A (", phrases[2])
        self.assertIn("D recouvre B (`b`)", phrases[3])
        self.assertNotIn("repassent `pending`", " ".join(phrases))

    def test_start_waits_for_every_overlapped_child_never_a_disjoint_running_one(self):
        # kills « start n'attend que l'enfant k-1 » (exec-critic, item 3) et « start attend une `running` qu'il ne
        # recouvre pas » : sans rétrogradation, seul le recouvrement fait attendre
        phrases = CP.ordre([("A", ["a", "x"]), ("B", ["a", "b"]), ("C", ["x"]), ("D", ["b"])])
        self.assertIn("`tasks.py start D` APRÈS LA FUSION de B (", phrases[3])
        phrases = CP.ordre([("A", ["a"]), ("B", ["b"]), ("C", ["a"])])
        self.assertIn("C recouvre A (`a`) : `tasks.py start C` APRÈS LA FUSION de A (", phrases[2])
        # un enfant disjoint de TOUS les précédents (tous encore `running`) part par fournee ; D nomme A et B
        phrases = CP.ordre([("A", ["a"]), ("B", ["a", "b"]), ("C", ["c"]), ("D", ["a"])])
        self.assertIn("C, disjoint des enfants `running`, part aussi par `tasks.py fournee`", phrases[2])
        self.assertIn("D recouvre A (`a`), B (`a`) : `tasks.py start D` APRÈS LA FUSION de A, B (", phrases[3])


# --- COUVERTURE, BLOC PREMIER, COÛT : la CLI ----------------------------------------------------------------
class CliTests(_Cli):

    def test_the_block_comes_first_in_template_order(self):
        # kills « bloc après un autre message », « ligne du gabarit perdue » and « seuil présenté comme calibré »
        b, tid = self.board()
        p = self.cadrer(b, tid, INVENTAIRE_REEL, _parties_cli(), "--chantier", CHANTIER)
        self.assertEqual((p.returncode, p.stderr), (0, ""), p.stderr)
        lignes = p.stdout.splitlines()
        self.assertEqual(lignes[0], f"CADRAGE {tid}")
        self.assertEqual(lignes[-1], "FIN CADRAGE")
        self.assertEqual(len(lignes), len(GABARIT), p.stdout)
        for ligne, tete in zip(lignes, GABARIT):
            self.assertTrue(ligne.startswith(tete), (tete, ligne))
        self.assertEqual(lignes[1], "Titre : feat: une tâche à cadrer")
        self.assertIn("17 chemins distincts, 20 affectations entre 4 enfants", lignes[2])
        self.assertIn("5 hôte(s)", lignes[2])
        self.assertTrue(lignes[3].startswith("Verdict : découper"), lignes[3])
        self.assertIn("seuil heuristique, non calibré", lignes[3])
        self.assertIn(f"--chantier {CHANTIER}", lignes[5])
        self.assertIn(f'PUIS le parent par `done --sans-binome "{MOTIF}"`', lignes[6])
        self.assertIn("aucune autre porte entre la porte et ces `done`", lignes[6])
        self.assertIn("puis A, B, C1 (toujours `running` ; l'emprunt passe par la portée, plus par le chantier), "
                      "PUIS C2", lignes[6])
        # T4 — chez l'adoptant, le parent sans plan se clôt aussi par la sortie tracée de la cible
        self.assertIn(f'chez l\'adoptant, avec `--sans-cible "{MOTIF_CIBLE}"`', lignes[6])
        # T2 — B reste au-dessus du seuil : le bloc le DIT au pilote, sans re-cadrage
        self.assertIn("B (6 chemins, encore au-dessus du seuil : 6 chemins ≥ 6 sur 4 surfaces ≥ 3 — au pilote, "
                      "jamais re-cadré)", lignes[4])
        self.assertIn("A (5 chemins), ", lignes[4])
        # T5 — un board sans `running` le dit, jamais par défaut
        self.assertIn("`running` au board à ce cadrage : aucune — un `start` d'enfant ne repasse AUCUNE `running` "
                      "en `pending`, d'un autre chantier comprise", lignes[5])
        # T1 — la Suite fait lire deps-ready du parent AVANT de créer, et hériter ses amonts
        self.assertIn(f"`$kickoff` lit `tasks.py deps-ready {tid}` — seul `AMONT_CLOS` crée les enfants —", lignes[8])
        self.assertIn("chacun héritant des amonts déclarés du parent (`tasks.py depends`)", lignes[8])
        self.assertIn("sans nouveau cadrage", lignes[8])

    def test_a_small_task_plans_and_its_chantier_defaults_to_the_task(self):
        # kills « verdict figé à découper » and « Suite découper sans découpe »
        b, tid = self.board()
        p = self.cadrer(b, tid, list(REGLE))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Verdict : planifier", p.stdout)
        self.assertIn("Découpe : aucune — un seul plan.", p.stdout)
        self.assertIn("Suite : le planner part sur cette tâche.", p.stdout)
        p = self.cadrer(b, tid, ["a.py", "b.md"], ["X=a.py", "Y=b.md"])
        self.assertIn("Verdict : planifier", p.stdout)
        self.assertIn("Découpe : proposée, non exigée par le seuil : X (1 chemin), Y (1 chemin).", p.stdout)
        self.assertIn(f"Tous les enfants portent `--chantier cadrage-{tid}`", p.stdout)

    def test_planifier_with_parts_never_says_the_task_skips_the_planner(self):
        # kills « Suite découper sous le seuil » (T7) : `Verdict : planifier` + `--part` → le planner part
        b, tid = self.board()
        p = self.cadrer(b, tid, ["a/x.py", "a/y.md"], ["X=a/x.py", "Y=a/y.md"])
        self.assertEqual(p.returncode, 0, p.stderr)
        suite = next(l for l in p.stdout.splitlines() if l.startswith("Suite : "))
        self.assertEqual(suite, "Suite : le planner part sur cette tâche ; la découpe proposée, non exigée par le "
                                "seuil, ne se fait que sur décision du pilote.")
        self.assertNotIn("jamais au planner", p.stdout)

    def test_without_measured_turns_the_kit_measure_is_labelled(self):
        # kills « repli non étiqueté » : la mesure du kit ne se fait jamais passer pour locale
        b, tid = self.board()
        p = self.cadrer(b, tid, list(REGLE))
        self.assertIn("aucune tâche mesurée dans ce dépôt — mesure du kit, 18/10 : 22–79 min et 250–470 k jetons "
                      "par plan", p.stdout)
        self.assertIn("pas une borne", p.stdout)
        # un journal illisible ne se lit jamais « zéro tour » : il est DIT illisible, et le repli reste étiqueté
        (b.d / ".agents" / "state" / "specs" / "SPECS.json").write_text("{pas du json", encoding="utf-8")
        p = self.cadrer(b, tid, list(REGLE))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("aucune mesure locale lisible (`specs.py chrono`) — mesure du kit, 18/10", p.stdout)

    def test_the_per_task_median_and_p90_are_multiplied_by_the_number_of_plans(self):
        # kills « p90 par TOUR » (T6), « un tour par plan », « médiane interpolée » and « estimation d'un seul plan » :
        # une tâche à 1 tour de 10 min, une autre à 3 tours de 10 min → par tâche [10, 30] min ; 2 plans →
        # médiane basse 10 × 2 = 20 min, p90 au rang le plus proche 30 × 2 = 60 min
        b, tid = self.board()
        autre = b.nouvelle("une tâche déjà planifiée en trois tours", chantier=None)
        tours = ((tid, 1), (autre, 3))
        for tache, n in tours:
            for k in range(1, n + 1):
                b.ok("add", "--task", tache, "--kind", "verdict", "--text",
                     f"plan=docs/tasks/{tache}-plan.md ; chrono: planner=6m00s/60.0k plan-critic=4m00s/40.0k",
                     f"plan-critic NO_GO (iteration {k}/8)", script="specs.py")
        p = self.cadrer(b, tid, ["a.py", "b.md"], ["X=a.py", "Y=b.md"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Estimation : ~20m00s à ~1h00m00s et ~200.0 k à ~600.0 k jetons pour 2 plan(s), médiane–p90 "
                      "PAR TÂCHE de `specs.py chrono` (2 tâche(s) mesurée(s), tous ses tours planner + critique "
                      "cumulés : 10m00s à 30m00s par tâche)", p.stdout)

    def test_a_foreign_running_task_is_named_in_the_order_line(self):
        # kills « start du 4e cas muet sur les running étrangères » (T5) : la tâche d'un autre chantier est NOMMÉE
        b, tid = self.board()
        x = b.nouvelle("tâche étrangère en dev", chantier="autre-chantier")
        b.ok("start", x)
        p = self.cadrer(b, tid, ["a.py", "b.md"], ["X=a.py", "Y=b.md"])
        self.assertEqual(p.returncode, 0, p.stderr)
        ordre = next(l for l in p.stdout.splitlines() if l.startswith("Ordre : "))
        self.assertIn(f"`running` au board à ce cadrage : {x} (autre-chantier) — un `start` d'enfant ne repasse "
                      "AUCUNE `running` en `pending`, d'un autre chantier comprise", ordre)
        self.assertIn("attendre la fusion d'une `running` étrangère qui recouvre l'enfant", ordre)

    def test_closure_declares_explicit_scope(self):
        # kills « clôture par emprunt du chantier » (C40, S-01M5E50ABADJA72966YQF4J285) : le bloc ET le point 4 de
        # planning/SKILL.md déclarent `review-scope <parent> <lots> <enfants>` AVANT la revue globale ; rétablir
        # « emprunt du slot … même chantier » sur l'une des surfaces rougit
        ancien = re.compile(r"emprunt du slot[^.;]*même chantier")
        b, tid = self.board()
        p = self.cadrer(b, tid, INVENTAIRE_REEL, _parties_cli(), "--chantier", CHANTIER)
        self.assertEqual(p.returncode, 0, p.stderr)
        cloture = p.stdout.splitlines()[6]
        self.assertIn(f"AVANT la revue de clôture globale, `tasks.py review-scope {tid} <lots de fournée> A B C1 C2` "
                      "(liste EXPLICITE parent, lots et enfants", cloture)
        self.assertLess(cloture.index("review-scope"), cloture.index("puis la revue"), cloture)
        texte = " ".join(SKILLS["planning"].read_text(encoding="utf-8").split())
        point4 = texte.split("4. Clôture : ", 1)[1].split(" 5. Chez l'adoptant", 1)[0]
        self.assertIn("déclarer la portée AVANT la revue de clôture globale : `tasks.py review-scope <parent> <lots> "
                      "<enfants>` — liste EXPLICITE", point4)
        self.assertIn("L'emprunt passe par la portée, plus par le chantier", point4)
        self.assertLess(point4.index("review-scope"), point4.index("puis la revue"), point4)
        self.assertIn("chaque membre déclaré figure dans le brief du critique avec son diff", point4)
        for clause in ("le traceur écrit sur CHAQUE membre nommé, non consommé, une trace estampillée de la "
                       "déclaration", "une nouvelle déclaration invalide les traces d'avant",
                       "une trace EMPRUNTÉE à un autre membre `running` (membre sans trace propre) périme à la porte "
                       "verte suivante"):
            self.assertIn(clause, point4)
        self.assertNotIn("n'a plus de critique à emprunter", point4)
        for nom, surface in (("bloc", cloture), ("pt 4", point4), ("docstring", " ".join(CP.__doc__.split()))):
            with self.subTest(surface=nom):
                self.assertIsNone(ancien.search(surface), surface)
        self.assertIn("`tasks.py review-scope <parent> <lots> <enfants>`", " ".join(CP.__doc__.split()))

    def test_an_unreadable_running_list_is_said_unreadable(self):
        # kills « board illisible lu comme aucune running » (T5, fail-closed)
        with mock.patch.object(CP, "_executer", return_value=subprocess.CompletedProcess([], 1, "", "boom")):
            self.assertIsNone(CP.lire_running(Path(".")))
        with mock.patch.object(CP, "_executer", return_value=subprocess.CompletedProcess([], 0, "[]", "")):
            self.assertEqual(CP.lire_running(Path(".")), [])

    def test_every_refusal_is_listed_and_nothing_is_printed(self):
        # kills « première cause seule » and « bloc imprimé malgré un refus »
        b, tid = self.board()
        p = self.cadrer(b, tid, ["a.py", "/abs", "x/*.py", "d/", "../up", "b.py"],
                        ["A=a.py,zz.py", "A=b.py", "9=b.py"])
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        for cause in ("chemin absolu : /abs", "motif glob", "répertoire, pas un chemin exact", "chemin qui remonte",
                      "partie en double : A", "partie mal formée", "`zz.py` n'est pas dans l'inventaire",
                      "`b.py` n'est couvert par aucune partie", "8 cause(s)"):
            self.assertIn(cause, p.stderr)

    def test_parts_must_cover_the_inventory_and_count_two_at_least(self):
        # kills « couverture non vérifiée » and « découpe à un enfant admise »
        b, tid = self.board()
        p = self.cadrer(b, tid, ["a.py", "b.py"], ["A=a.py"])
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("`b.py` n'est couvert par aucune partie", p.stderr)
        p = self.cadrer(b, tid, ["a.py"], ["A=a.py"])
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("une seule partie", p.stderr)
        p = self.cadrer(b, tid, ["a.py"], ["A=a.py", "B="])
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("partie B", p.stderr)

    def test_absent_data_is_refused(self):
        # kills « tâche inconnue cadrée sans titre », « inventaire deviné » and « racine absente lue vide »
        b, _tid = self.board()
        for args, cause in ((["--task", "T-99999999", "--file", "a.py"], "unknown task id: T-99999999"),
                            (["--task", "T-1"], "aucun `--file`"),
                            (["--task", "t-x", "--file", "a.py"], "id de tâche non conforme")):
            with self.subTest(cause=cause):
                p = b.t(*args, script="cadrage_plan.py")
                self.assertEqual((p.returncode, p.stdout), (2, ""))
                self.assertIn(cause, p.stderr)
        p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(b.racine / "absente"), "--task", "T-1",
                            "--file", "a.py"], capture_output=True, text=True, encoding="utf-8", env=b.env,
                           timeout=60, check=False)
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("racine absente", p.stderr)

    def test_a_hung_or_missing_subprocess_is_a_refusal_never_a_traceback(self):
        # kills « TimeoutExpired non rattrapé » (T8) : par l'entrée réelle `main`, rc 2 et la cause sur stderr ;
        # l'estimation, elle, rend le repli étiqueté
        b, tid = self.board()
        for exc in (subprocess.TimeoutExpired(["tasks.py"], 120), FileNotFoundError("python introuvable")):
            with self.subTest(exc=type(exc).__name__):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(CP.subprocess, "run", side_effect=exc), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = CP.main(["--root", str(b.d), "--task", tid, "--file", "a.py"])
                self.assertEqual((rc, out.getvalue()), (2, ""))
                self.assertIn(f"tâche illisible au board : tasks.py : {type(exc).__name__}", err.getvalue())
                with mock.patch.object(CP.subprocess, "run", side_effect=exc):
                    self.assertEqual(CP._executer(CP.SPECS, b.d, "chrono", "--json").returncode,
                                     CP.RC_SOUS_PROCESSUS)
                    self.assertIn("aucune mesure locale lisible", CP.estimation(b.d, 1))

    def test_the_tool_writes_nothing(self):
        # kills « l'outil écrit le board ou SPECS » : lecture seule, octet pour octet
        b, tid = self.board()
        etat = b.d / ".agents" / "state"
        avant = {p: p.read_bytes() for p in etat.rglob("*") if p.is_file() and "local" not in p.parts}
        self.assertEqual(self.cadrer(b, tid, INVENTAIRE_REEL, _parties_cli()).returncode, 0)
        apres = {p: p.read_bytes() for p in etat.rglob("*") if p.is_file() and "local" not in p.parts}
        self.assertEqual(avant, apres)


# --- VOYAGE -------------------------------------------------------------------------------------------------
class VoyageTests(unittest.TestCase):

    @unittest.skipUnless((ROOT / ".template-exclude").is_file() and (HERE / "sync_template.py").is_file(),
                         "canal de synchro absent (dépôt adoptant) : le voyage se juge dans le kit")
    def test_the_rule_travels_to_the_adopter(self):
        # kills « une règle de .template-exclude retient l'outil ou une skill » (S-01M5AQMWW0 : elle voyage)
        sys.path.insert(0, str(HERE))
        try:
            from sync_template import match_rule, parse_exclude
        finally:
            sys.path.remove(str(HERE))
        regles = parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for chemin in REGLE:
            with self.subTest(chemin=chemin):
                regle = match_rule(chemin, regles)
                self.assertTrue(regle is None or regle.polarity not in ("strip", "keep", "own"), regle)
                self.assertTrue((ROOT / chemin).is_file())


# --- SÉQUENCE -----------------------------------------------------------------------------------------------
class _Sequence(unittest.TestCase):
    """La découpe réelle en miniature : A (dégénérée), B (deux `LOT:`), C1 et C2 qui partagent roster et témoin."""

    def admis(self, r: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(r.returncode, 0, f"refusé : {r.stdout}{r.stderr}")

    def refuse(self, r: subprocess.CompletedProcess[str], *contient: str) -> None:
        self.assertEqual(r.returncode, 2, f"attendu rc 2 : {r.stdout}{r.stderr}")
        for x in contient:
            self.assertIn(x, r.stderr)

    def lancer(self, gates: dict[str, str], *, chantier_a: str | None = CHANTIER,
               livrer: bool = True) -> tuple[Board, dict[str, str], list[str]]:
        """Création, plans, `fournee A`, `fournee B` (lots livrés chez l'adoptant). Rend A, B et les lots `running`."""
        b = Board(self, gates)
        adoptant = "PLAN_CIBLE_REQUIRED" in gates
        if adoptant:
            b.depot_git()
        ids = {"P": b.nouvelle("parent de cadrage"), "A": b.nouvelle("A", chantier=chantier_a),
               "B": b.nouvelle("B"), "C1": b.nouvelle("C1"), "C2": b.nouvelle("C2")}
        # Le parent ne va JAMAIS au planner : aucun plan, aucune trace `plan approuvé` (T4 de la revue globale).
        b.plan(ids["A"], "LOTS: aucun | petit", ["a.py", "skill.md"])
        b.plan(ids["B"], "LOT: X | dev-mono | commande | cmd.md\nLOT: Y | dev-mono | témoin | test_s.py\n"
                         "INTÉGRATION: aucune", ["cmd.md", "test_s.py"])
        b.plan(ids["C1"], "LOTS: aucun | petit", ["orch1.md", "roster.json", "test_s.py"])
        b.plan(ids["C2"], "LOTS: aucun | petit", ["orch2.md", "roster.json", "test_s.py"])
        b.chaine()
        b.ok("fournee", ids["A"])
        b.chaine()
        b.ok("fournee", ids["B"])
        lots = b.tache(ids["B"])["fournee"]["lots"]
        self.assertEqual(len(lots), 2, lots)
        self.assertEqual(b.etats(ids["A"], ids["B"], *lots), ["running"] * 4)
        if adoptant and livrer:
            for lot in lots:
                b.livrer_lot(lot, b.tache(lot)["writeset"][0])
        return b, ids, lots

    def suivants(self, b: Board, ids: dict[str, str], lots: list[str]) -> None:
        """`start C1` APRÈS LA FUSION de B, puis `start C2` : aucun `start` ne rétrograde, tous restent `running`."""
        b.chaine()
        b.ok("start", ids["C1"])
        self.assertEqual(b.etats(ids["A"], ids["B"], *lots, ids["C1"]), ["running"] * 5)
        b.chaine()
        b.ok("start", ids["C2"])
        self.assertEqual(b.etats(ids["C1"], ids["C2"]), ["running", "running"])

    @staticmethod
    def membres(b: Board, ids: dict[str, str]) -> list[str]:
        """La portée de la découpe : parent, lots de fournée, enfants — nommés, jamais inférés."""
        return [ids["P"], *b.tache(ids["B"])["fournee"]["lots"], *(ids[k] for k in ("A", "B", "C1", "C2"))]

    def revue_et_porte(self, b: Board, ids: dict[str, str], *portes: str, hors: tuple[str, ...] = (),
                       revue: str | None = None, seul: str | None = None) -> None:
        """Chaque acte daté APRÈS celui qui l'ouvre : la portée EXPLICITE déclarée (il y a 1 h ; focus C2), puis
        la revue globale (il y a 30 min) que le traceur écrit sur chaque membre, puis la porte unique (il y a
        15 min ; la précédente datait d'avant la déclaration). `hors` : membres omis ; `revue` : trace datée
        ailleurs, non estampillée ; `seul` : trace sur ce membre seul (mutants)."""
        b.declarer([m for m in self.membres(b, ids) if m not in hors], il_y_a(1))
        b.tracer(revue or il_y_a(0.5), estampille=revue is None, seul=seul)
        b.portes(*(portes or (il_y_a(2), il_y_a(0.25))))

    @staticmethod
    def cloture_parent(gates: dict[str, str]) -> list[str]:
        """La clôture du parent SANS plan : `--sans-binome`, plus `--sans-cible` là où la cible est armée."""
        return ["--raison", "enfants clos", "--sans-binome", MOTIF,
                *(["--sans-cible", MOTIF_CIBLE] if "PLAN_CIBLE_REQUIRED" in gates else [])]

    def sequence_verte(self, gates: dict[str, str]) -> None:
        b, ids, lots = self.lancer(gates)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids)
        for tid in [*lots, ids["A"], ids["B"], ids["C1"], ids["C2"]]:
            self.admis(b.t("done", tid, "--raison", "livré sous la porte unique"))
        self.admis(b.t("done", ids["P"], *self.cloture_parent(gates)))
        self.assertEqual(b.etats(*lots, *(ids[k] for k in ("A", "B", "C1", "C2", "P"))), ["done"] * 7)
        for tid in [*lots, ids["A"], ids["B"], ids["C1"], ids["C2"]]:
            self.assertNotIn("SANS BINÔME", b.tache(tid)["stage"])
            self.assertNotIn("relevé sur", b.tache(tid)["stage"])  # sa PROPRE trace, jamais un emprunt
        self.assertIn(f"[SANS BINÔME : {MOTIF}]", b.tache(ids["P"])["stage"])


class SequenceTests(_Sequence):

    def test_kit_sequence_is_green_end_to_end(self):
        # kills « la règle livrée ne passe pas les gardes » (C21, C27) : BINOME_REQUIRED posé, B à deux lots
        self.sequence_verte(KIT)

    def test_adopter_sequence_is_green_end_to_end(self):
        # kills « règle pensée pour le kit seul » (C30) : chaîne, cibles `chantier=*`, lots `direct` relevés
        self.sequence_verte(ADOPTANT)

    def test_mutant_a_outside_the_scope_refuses_done_a(self):
        # mutant 1 — kills « membre omis de la portée » et « emprunt par le chantier » : A, du MÊME chantier que C2,
        # mais non nommé, ne reçoit aucune trace et n'emprunte rien ; nommé (séquence verte), il est admis
        b, ids, lots = self.lancer(KIT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids, hors=(ids["A"],))
        self.assertEqual(b.tache(ids["A"]).get("chantier"), b.tache(ids["C2"]).get("chantier"))
        self.refuse(b.t("done", ids["A"], "--raison", "x"), "REVUE CRITIQUE", "0 critique(s) tracé(s)")
        self.admis(b.t("done", ids["B"], "--raison", "nommé, donc tracé"))
        self.assertNotIn("relevé sur", b.tache(ids["B"])["stage"])

    def test_independent_running_survives_child_start(self):
        # kills « le `start` d'un enfant rétrograde une `running` étrangère » (C3, T-01M5F7286N1EYGXAXA5244X86B) :
        # X, d'un autre chantier et disjoint, reste `running` à travers `start C1` et `start C2`, et le bloc le DIT
        b, ids, lots = self.lancer(KIT)
        x = b.nouvelle("tâche étrangère en dev", chantier="autre-chantier")
        b.ok("writeset", x, "etranger.py")
        b.ok("start", x)
        bloc = b.t("--task", ids["P"], "--file", "a.py", "--file", "b.md", "--part", "X=a.py", "--part", "Y=b.md",
                   script="cadrage_plan.py")
        self.assertEqual(bloc.returncode, 0, bloc.stderr)
        ordre = next(l for l in bloc.stdout.splitlines() if l.startswith("Ordre : "))
        self.assertIn(f"{x} (autre-chantier)", ordre)
        self.assertIn("— un `start` d'enfant ne repasse AUCUNE `running` en `pending`", ordre)
        self.suivants(b, ids, lots)
        self.assertEqual(b.etats(x, ids["A"], ids["B"], *lots, ids["C1"], ids["C2"]), ["running"] * 7)

    def test_mutant_scope_redeclared_after_the_review_refuses_done_b(self):
        # mutant 2 — kills « une nouvelle déclaration garde les traces d'avant » : chaque membre porte la trace
        # estampillée de SA déclaration ; re-déclarer après la revue (focus C2 inchangé) les invalide toutes
        b, ids, lots = self.lancer(KIT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids)
        b.ok("review-scope", *self.membres(b, ids))
        self.refuse(b.t("done", ids["B"], "--raison", "x"), "REVUE CRITIQUE")

    def test_mutant_fournee_c1_while_b_runs_is_refused(self):
        # mutant 3 — kills « fournee pour tout enfant » : C1 recouvre un lot de B encore `running`
        b, ids, _lots = self.lancer(KIT)
        b.chaine()
        self.refuse(b.t("fournee", ids["C1"]), "recouvre le write-set", "Rien n'a été écrit.")

    def test_mutant_review_before_the_scope_refuses_done_lot(self):
        # mutant 4 — kills « portée déclarée après la revue » : une trace datée AVANT `declared_at` ne crédite
        # aucun membre, lot compris — la portée se déclare JUSTE AVANT le critique
        b, ids, lots = self.lancer(KIT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids, revue=il_y_a(1.5))
        self.refuse(b.t("done", lots[0], "--raison", "x"), "REVUE CRITIQUE")

    def test_mutant_a_second_gate_expires_a_borrowed_trace(self):
        # mutant 5 — kills « une autre porte entre la porte et les done » (C32) : A, sans trace propre, emprunte
        # celle de C2 (même portée, `running`) ; une seconde porte verte après la revue la périme
        b, ids, lots = self.lancer(KIT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids, il_y_a(0.4), il_y_a(0.25), seul=ids["C2"])
        self.refuse(b.t("done", ids["A"], "--raison", "x"), "PÉRIMÉE")
        # témoin du cas : sous la seule porte d'après la revue, le même emprunt est admis
        b.portes(il_y_a(2), il_y_a(0.25))
        self.admis(b.t("done", ids["A"], "--raison", "emprunt de C2 sous la porte unique"))
        self.assertIn(f"binôme relevé sur {ids['C2']}", b.tache(ids["A"])["stage"])

    def test_last_child_closed_first_refuses_the_borrow(self):
        # sonde P4 — kills « l'emprunt survit à la clôture du porteur » : C2, dernier enfant et SEUL tracé, se clôt
        # d'abord sous la porte unique ; A ne peut plus emprunter sa trace, le prêteur doit être `running`
        b, ids, lots = self.lancer(KIT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids, seul=ids["C2"])
        self.admis(b.t("done", ids["C2"], "--raison", "porteur de la trace, clos d'abord"))
        self.refuse(b.t("done", ids["A"], "--raison", "x"), "REVUE CRITIQUE")
        self.assertEqual(b.etats(ids["A"]), ["running"])

    def test_mutant_adopter_parent_closed_without_sans_cible_is_refused(self):
        # mutant 6 — kills « parent sans plan clos comme un enfant chez l'adoptant » (T4) : la cible `chantier=*`
        # contrôle tout `done` ; le parent, qui n'a pas de plan, n'a que la sortie tracée `--sans-cible`
        b, ids, lots = self.lancer(ADOPTANT)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids)
        for tid in [*lots, ids["A"], ids["B"], ids["C1"], ids["C2"]]:
            self.admis(b.t("done", tid, "--raison", "livré sous la porte unique"))
        self.refuse(b.t("done", ids["P"], "--raison", "enfants clos", "--sans-binome", MOTIF),
                    "aucun plan approuvé ne porte de cible")
        self.admis(b.t("done", ids["P"], *self.cloture_parent(ADOPTANT)))
        self.assertIn(MOTIF_CIBLE, b.tache(ids["P"])["stage"])

    def test_a_child_inherits_the_parents_open_upstream(self):
        # kills « la découpe contourne L'AMONT D'ABORD » (T1) : sans l'arête héritée, l'enfant démarre sous
        # l'amont ouvert du parent (le trou mesuré) ; avec elle, deps-ready dit AMONT_OUVERT et `start` refuse
        b = Board(self, KIT)
        u, p = b.nouvelle("amont ouvert", chantier=None), b.nouvelle("parent", chantier=None)
        b.ok("depends", p, u, "--motif", "TECHNIQUE: le parent lit ce que U pose")
        self.assertEqual(b.t("deps-ready", p).stdout.splitlines()[0], "deps-ready: AMONT_OUVERT")
        sans, avec = b.nouvelle("enfant sans héritage"), b.nouvelle("enfant qui hérite")
        self.assertEqual(b.t("deps-ready", sans).stdout.splitlines()[0], "deps-ready: AMONT_CLOS")
        b.ok("depends", avec, u, "--motif", f"TECHNIQUE: amont hérité du parent {p} (découpe de cadrage)")
        self.assertEqual(b.t("deps-ready", avec).stdout.splitlines()[0], "deps-ready: AMONT_OUVERT")
        r = b.t("start", avec)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(b.etats(avec), ["pending"])

    def test_adopter_direct_lot_without_its_return_is_refused(self):
        # kills « retour du lot facultatif chez l'adoptant » (skill planning, point 5)
        b, ids, lots = self.lancer(ADOPTANT, livrer=False)
        self.suivants(b, ids, lots)
        self.revue_et_porte(b, ids)
        self.refuse(b.t("done", lots[0], "--raison", "x"), "aucun relevé de retour")


# --- DOCTRINE -----------------------------------------------------------------------------------------------
PHRASES = {
    "planning": ("APRÈS LA FUSION de chaque enfant précédent qui le recouvre — 4e cas de `start`",
                 "Aucune arête `depends_on` entre eux",
                 "Les `done` suivent la porte unique sans autre porte entre les deux", "seuil heuristique, non calibré",
                 "mesure du kit, 18/10", "relayé tel quel", "`tasks.py retour`",
                 # revue de clôture globale : T2 (portée), T1 (amont), T3 (R1), T5 (running), T6, T13, T4
                 "Le cadrage se joue UNE fois, avant le PREMIER `planner`",
                 "jamais sur la voie directe (`tasks.py direct` rc 0), ni sur une reprise, une révision ou un enfant "
                 "d'une découpe (arbitrage S-01M5BFKA2D)",
                 "AVANT de créer un enfant, lire `python .agents/bin/tasks.py deps-ready <parent>` : seul "
                 "`AMONT_CLOS` crée les enfants", "`python .agents/bin/tasks.py depends <enfant> <amonts du parent…>",
                 "jamais une arête entre enfants", "Planifier les enfants un à un, dans l'ordre du cadrage, sans les "
                 "re-cadrer", "l'exception écrite à R1 FERMER AVANT D'OUVRIR",
                 "Ce `start` ne repasse AUCUNE `running` en `pending` (T-01M5F7286N1EYGXAXA5244X86B)",
                 "une `running` étrangère qui recouvre l'enfant, non fusionnée → attendre sa fusion, jamais `start`",
                 "`tasks.py review-scope <parent> <lots> <enfants>`",
                 "la médiane et le p90 PAR TÂCHE de `specs.py chrono`",
                 "Avant chaque `new`, `tasks.py list --chantier <nom> --json` : un enfant déjà présent (même partie) "
                 "n'est jamais recréé", "Avant le `done` du parent, `tasks.py list --chantier <nom> --json` montre "
                 "chaque enfant `done`", "le parent, qui n'a pas de plan, se clôt par"),
    "kickoff": ("AFTER THE MERGE of every earlier child it overlaps — the 4th `start` case",
                "NO `depends_on` edge between children",
                "no other gate in between", "relayed verbatim", "`tasks.py retour`",
                # la liste FERMÉE des cas de `start` (exec-critic, item 5) porte le 4e cas, dans sa phrase
                "the morning path, `/night`, and the next child of a cadrage cut, after the MERGE of the earlier "
                "children it waits for (§ CADRAGE FIRST), then `fournee` if its plan carries `LOT:` lines "
                "(S-01M5ATNMNBYQGYF65SNNZ5JHBN)",
                # 2bis dit « plan », jamais « planner » : `.codex/test_pipeline_contract.py` lit le PREMIER
                # « planner » de la skill après `language-detector`
                "ONCE per task, before its FIRST plan only — never on the direct route, a resumption, a revision "
                "or a child of a cadrage cut", "ONCE per task, before its FIRST planner only — never on the direct "
                "route (`tasks.py direct` rc 0), a resumption",
                "before creating any child, read `tasks.py deps-ready <parent>`: only `AMONT_CLOS` creates children",
                "each child inherits the parent's DECLARED upstream (`tasks.py depends <child>", "never cadré again",
                "the next child of a cadrage cut is the written exception (S-01M5ATNMNBYQGYF65SNNZ5JHBN, § CADRAGE "
                "FIRST)", "that `start` demotes no `running` task (several run at once; it moves the clone's focus to "
                "the child", "a `running` task whose write-set overlaps the child's, not yet merged → wait for its "
                "merge, never `start`", "`tasks.py review-scope <parent> <lots…> <children…>` JUST BEFORE the critic "
                "(explicit list, never inferred; each declared member appears in the critic's brief with its diff)",
                "of the other children (still `running`: no `start` demotes them)",
                "before each `new`, `tasks.py list --chantier <name> --json`", "before the parent's `done`, "
                "`tasks.py list --chantier <name> --json` shows every child `done`",
                "the parent, which has no plan, closes with"),
    "planning-all": ("relaie le verdict vers `$kickoff`", "par FUSION sous une porte unique",
                     "chaque arête `DÉPEND` du tableau coûte une porte",
                     "cadrée UNE fois, avant son PREMIER `planner`, en lecture seule — ni sur une reprise, une "
                     "révision ou un enfant d'une découpe"),
}
#: L'exception écrite à R1 FERMER AVANT D'OUVRIR (T3), sur les surfaces skill qui portent R1.
TASK_BOARD = ROOT / ".agents" / "skills" / "task-board" / "SKILL.md"
R1_EXCEPTION = ("exception écrite : l'enfant suivant d'une découpe de cadrage (S-01M5ATNMNBYQGYF65SNNZ5JHBN), dont "
                "les `done` se ferment ensemble sous la porte unique de la découpe")
#: Chaque chemin de la commande prescrite est entre guillemets doubles (T13) : jamais `--file <`, ni `--part <`.
NU = re.compile(r"--(?:file|part|chantier) <")
GUILLEMETS = re.compile(r'--file "<[^"]+>"')


class DoctrineTests(unittest.TestCase):

    def texte(self, nom: str) -> str:
        return " ".join(SKILLS[nom].read_text(encoding="utf-8").split())

    def test_each_skill_carries_the_command_and_its_rule(self):
        # kills « commande ou phrase de règle retirée d'une skill »
        for nom, phrases in PHRASES.items():
            texte = self.texte(nom)
            with self.subTest(skill=nom):
                self.assertIn(COMMANDE, texte)
                for phrase in phrases:
                    self.assertIn(phrase, texte)

    def test_the_options_the_skills_prescribe_exist_in_the_tool(self):
        # kills « option renommée dans l'outil ou dans une skill seule »
        aide = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True,
                              encoding="utf-8", timeout=60, check=True).stdout
        for nom in SKILLS:
            ligne = next(l for l in SKILLS[nom].read_text(encoding="utf-8").splitlines() if COMMANDE in l)
            options = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", ligne))
            with self.subTest(skill=nom):
                self.assertTrue({"--task", "--file", "--part"} <= options, options)
                for option in options:
                    self.assertIn(option, aide)

    def test_the_skills_say_the_numbers_and_the_motive_of_the_code(self):
        # kills « seuil changé dans le code seul » and « motif du parent divergent »
        seuils = (f"≥ {CP.SEUIL_CHEMINS} chemins ; ≥ {CP.SEUIL_SURFACES_CHEMINS} sur ≥ {CP.SEUIL_SURFACES} surfaces ; "
                  f"≥ {CP.SEUIL_MIXTE} mêlant code et prose")
        self.assertIn(seuils, self.texte("planning"))
        self.assertEqual(CP.MOTIF_PARENT, MOTIF)
        self.assertEqual(CP.MOTIF_CIBLE_PARENT, MOTIF_CIBLE)
        for nom in ("planning", "kickoff"):
            with self.subTest(skill=nom):
                self.assertIn(f'`done --sans-binome "{MOTIF}"`', self.texte(nom))
                self.assertIn(f'`done --sans-binome "{MOTIF}" --sans-cible "{MOTIF_CIBLE}"`', self.texte(nom))

    def test_the_r1_exception_is_written_on_the_task_board_skill(self):
        # kills « R1 contredit la séquence sans exception écrite » (T3) — AGENTS.md et le miroir Copilot sont
        # jugés par `.agents/evals/test_cadrage_surfaces.py`
        self.assertIn(R1_EXCEPTION, " ".join(TASK_BOARD.read_text(encoding="utf-8").split()))

    def test_every_path_of_the_prescribed_command_is_double_quoted(self):
        # kills « chemin nu dans la commande composée » (T13) : un chemin à espace ou à apostrophe la casse
        for nom in SKILLS:
            ligne = next(l for l in SKILLS[nom].read_text(encoding="utf-8").splitlines() if COMMANDE in l)
            with self.subTest(skill=nom):
                self.assertIsNone(NU.search(ligne), ligne)
                self.assertIsNotNone(GUILLEMETS.search(ligne), ligne)
        # l'Usage de l'outil lui-même (docstring) prescrit la même forme
        usage = CP.__doc__.split("Usage :", 1)[1].split("`", 2)[1]
        self.assertIsNone(NU.search(usage), usage)
        self.assertIsNotNone(GUILLEMETS.search(usage), usage)


if __name__ == "__main__":
    unittest.main()
