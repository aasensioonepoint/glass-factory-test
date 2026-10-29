#!/usr/bin/env python3
"""CLIQUET DES LECTEURS D'ÉTAT (T-01M4V7R6EF5KSEC93N462BW5WM) — il empêche d'OUBLIER, il n'empêche pas de TRICHER.

POURQUOI. Les trois magasins d'état suivis (board, specs, ledger) ont chacun un module PROPRIÉTAIRE, et une
interface de lecture commune, `.agents/bin/etat_lecture.py`, qui délègue à ces propriétaires sans nommer un seul
chemin de magasin. Un code qui NOMME un magasin hors d'eux est un lecteur brut, ou le devient au premier
`read_text`. Ce banc tient la LISTE FERMÉE des fichiers qui le font, chacun avec sa catégorie et la suite qui le
résorbera : un fichier de plus ROUGIT, une entrée qui ne nomme plus rien ROUGIT aussi. La LISTE est une ÉGALITÉ
voulue, jamais un plafond.

L'UNIVERS, lu par `git ls-files` SEUL (jamais un parcours du disque) : les `.py` et `.sh` suivis sous `.agents/`,
`.claude/`, `.codex/`, `.gemini/`, `.github/hooks/`, `.kimi-code/`, `.githooks/`, `core-scripts/`, `agentic_v3/`
ou `.agents/vendor/agentic_v3/`, et `src/` ; hors bancs (motif `BANC`), hors `.agents/state/`
et hors autres `/vendor/`. Les deux chemins V3 partagent une entrée de LISTE ; si les deux sont suivis,
le fichier vendor fait foi. `docs/` est HORS univers.

LES RÈGLES DE DÉTECTION.
  * MOTIF : un nom de magasin (`TASKS.json`, `LEDGER.json`, `SPECS.json`, `SPECS.jsonl`) ou un segment de
    chemin (`state/board`, `state/memory`, `state/specs`, `board/tasks`, `board/epics`, `memory/entries`).
  * JOINTURE : les segments séparés, `"state", "board"` ou `"state" / "board"`, et `STATE / "board"`.
  * En `.py` : les constantes chaîne de l'AST hors docstrings qui portent le MOTIF, plus les lignes non commentées
    qui portent une JOINTURE. En `.sh` : les lignes non commentées qui portent l'un ou l'autre.
  * Un `.py` qu'`ast` ne lit pas est ROUGE, git inutilisable aussi : ne pas lire n'est jamais « rien à signaler ».

CE QU'IL TIENT : C1 aucun fichier détecté hors LISTE ; C2 aucune entrée de LISTE qui ne soit plus détectée ;
C3 le détecteur voit ses positifs et ignore ses négatifs ; chaque idiome de `IDIOMES_NON_DETECTES` lui échappe
vraiment.

CE QU'IL NE TIENT PAS — LES BORNES, ÉCRITES (L-00000187) :
  * le détecteur est un FILET À MAILLES : `IDIOMES_NON_DETECTES` énumère des écritures qu'il ne voit pas, et cette
    liste n'est pas close ;
  * la CATÉGORIE et la SUITE d'une entrée sont des DÉCLARATIONS : rien ici ne prouve qu'un « message » ne lit pas ;
  * il ne voit ni `docs/`, ni un banc, ni un fichier non suivi.

REMÈDE d'un refus : `python3 .agents/evals/test_lecture_etat_cliquet.py --relever` imprime la LISTE mesurée, sans
rien écrire ; puis une entrée et son motif dans le même commit, avec ce banc dans le write-set.

KIT SEUL : la LISTE nomme les fichiers de CE dépôt ; chez l'adoptant (`.agents/IS_THE_KIT` absent) le banc saute.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

UNIVERS = (".agents/", ".claude/", ".codex/", ".gemini/", ".github/hooks/", ".kimi-code/", ".githooks/",
           "core-scripts/", "agentic_v3/", "src/")
HORS_UNIVERS = (".agents/state/",)
BANC = re.compile(r"(^|/)test_|\.test\.(sh|mjs)$|/tests/|/fixtures/|smoketest|(^|/)conftest\.py$")
MOTIF = re.compile(r"TASKS\.json|LEDGER\.json|SPECS\.jsonl?|state/(board|memory|specs)|board/(tasks|epics)"
                   r"|memory/entries")
JOINTURE = re.compile(r"""["']state["']\s*[,/]\s*["'](board|memory|specs)["']"""
                      r"""|\bSTATE\s*/\s*["'](board|memory|specs)["']""")
REMEDE = ("remède : `python3 .agents/evals/test_lecture_etat_cliquet.py --relever`, puis une entrée et son motif "
          "dans le même commit, avec ce banc dans le write-set")

PROPRIETAIRE, LECTEUR_BRUT, SITE_CHEMIN, MESSAGE = (
    "propriétaire", "lecteur brut", "site qui nomme un chemin", "message")
CATEGORIES = (PROPRIETAIRE, LECTEUR_BRUT, SITE_CHEMIN, MESSAGE)
SUITES = {
    "aucune": "propriétaire du magasin : rien à résorber",
    "S1": "empreinte du dashboard",
    "S2": "core-scripts (décision pilote : interdit d'import, ou jumeau)",
    "S3": "lecteurs de garde",
    "S4": "hooks des trois hôtes",
    "S5": "sites qui nomment un chemin",
    "S6": "le cliquet voyage-t-il ?",
    "S7": "table LECTEURS",
}

# LA LISTE FERMÉE — relevée par `--relever` sur l'arbre fusionné : 36 fichiers.
LISTE: dict[str, tuple[str, str]] = {
    ".agents/bin/dashboard_readers_base.py": (SITE_CHEMIN, "S1"),
    ".agents/bin/dashboard_readers_memory.py": (MESSAGE, "S1"),
    ".agents/bin/docs_only_scope.py": (SITE_CHEMIN, "S5"),
    ".agents/bin/kickoff_guard.py": (MESSAGE, "S5"),
    ".agents/bin/ledger.py": (PROPRIETAIRE, "aucune"),
    ".agents/bin/loadtest.py": (LECTEUR_BRUT, "S7"),  # résidu : la surcharge `.json` de AGENTS_SPECS_PATH
    ".agents/bin/migrate_layout.py": (PROPRIETAIRE, "aucune"),
    ".agents/bin/plan_cible.py": (LECTEUR_BRUT, "S3"),
    ".agents/bin/plan_depends.py": (LECTEUR_BRUT, "S3"),
    ".agents/bin/post-task-done-index.sh": (SITE_CHEMIN, "S5"),
    ".agents/bin/retro.py": (MESSAGE, "S5"),
    ".agents/bin/specs.py": (PROPRIETAIRE, "aucune"),
    ".agents/bin/specs_graph.py": (MESSAGE, "S5"),
    ".agents/bin/tasks.py": (PROPRIETAIRE, "aucune"),
    ".agents/bin/tasks_cli.py": (PROPRIETAIRE, "aucune"),
    ".agents/bin/tasks_direct.py": (SITE_CHEMIN, "S5"),
    ".agents/bin/tasks_requetes.py": (LECTEUR_BRUT, "S7"),  # revendication : board publié lu en refs Git via cat-file/show
    ".agents/bin/tasks_stockage.py": (PROPRIETAIRE, "aucune"),
    ".agents/evals/classification_rules.py": (SITE_CHEMIN, "S5"),
    ".agents/security/unicode_scan.py": (LECTEUR_BRUT, "S3"),  # journal SPECS lu ligne à ligne, fail-closed (allowlist)
    ".claude/hooks/affirmation-guard.sh": (LECTEUR_BRUT, "S3"),
    ".claude/hooks/protect-paths.sh": (SITE_CHEMIN, "S4"),
    ".claude/hooks/run-recap.sh": (LECTEUR_BRUT, "S4"),
    ".claude/hooks/safe-bash.sh": (MESSAGE, "S4"),
    ".claude/hooks/session-start.sh": (SITE_CHEMIN, "S4"),
    ".codex/hooks/_common.py": (SITE_CHEMIN, "S4"),
    ".codex/hooks/protect_paths.py": (SITE_CHEMIN, "S4"),
    ".codex/hooks/safe_bash.py": (MESSAGE, "S4"),
    ".codex/hooks/session_context.py": (SITE_CHEMIN, "S4"),
    ".gemini/hooks/_common.py": (SITE_CHEMIN, "S4"),
    ".gemini/hooks/protect_paths.py": (SITE_CHEMIN, "S4"),
    ".gemini/hooks/safe_bash.py": (MESSAGE, "S4"),
    ".gemini/hooks/session_context.py": (SITE_CHEMIN, "S4"),
    "agentic_v3/reconciliation/board_bridge.py": (LECTEUR_BRUT, "S7"),  # le repli monolithe du pont
    "core-scripts/check-stale-justification.sh": (LECTEUR_BRUT, "S2"),
    "core-scripts/plan_pool.py": (LECTEUR_BRUT, "S2"),
    "core-scripts/plan_waves.py": (LECTEUR_BRUT, "S2"),
}

# Écritures que le détecteur NE VOIT PAS — la borne écrite (précédent : test_repo_walk_census.py). Chaque extrait est
# asserté NON détecté : le jour où le détecteur s'élargit, cette liste doit suivre.
IDIOMES_NON_DETECTES: dict[str, tuple[tuple[str, str], ...]] = {
    "concaténation": ((".py", 'nom = "TASKS" + ".json"\n'),),
    "segments en variables": ((".py", 's = "state"\nb = "board"\nchemin = Path(".agents") / s / b\n'),),
    "chemin du propriétaire lu en brut": ((".py", "texte = tasks.store_path(root).read_text()\n"),),
    "nom du propriétaire par getattr": ((".py", 'nom = getattr(specs, "STORE_NAME")\n'),),
    "CLI en sous-processus": ((".py", 'subprocess.run(["python3", ".agents/bin/tasks.py", "list"])\n'),),
    "segments constants sans « state » cité à côté": (
        (".py", 'p = PurePosixPath(".agents/state").joinpath("memory", "entries")\n'),
        (".py", 'p = os.path.join(STATE_DIR, "board", "tasks")\n'),
    ),
    "chemin venu de l'environnement": ((".py", 'texte = Path(os.environ["AGENTS_SPECS_PATH"]).read_text()\n'),),
}

# C3 — le détecteur n'est pas aveugle : ses positifs (K1, K3, K4) et ses négatifs (K2, commentaire shell).
POSITIFS: tuple[tuple[str, str], ...] = (
    (".py", 'data = json.loads(Path(".agents/state/board/TASKS.json").read_text())\n'),
    (".py", 'REL = (".agents", "state", "board", "TASKS.json")\n'),
    (".py", 'BOARD = STATE / "board"\n'),
    (".sh", "cat .agents/state/board/TASKS.json\n"),
)
NEGATIFS: tuple[tuple[str, str], ...] = (
    (".py", '"""Lit .agents/state/board/TASKS.json par son propriétaire."""\nx = 1\n'),
    (".py", "x = 1  # TASKS.json\n# STATE / \"board\"\n"),
    (".sh", "# TASKS.json\necho ok\n"),
)


class CliquetError(RuntimeError):
    """L'univers ne se lit pas (git inutilisable, fichier illisible, `.py` qu'`ast` refuse) : ROUGE, jamais vide."""


def fichiers_suivis(racine: Path) -> list[str]:
    """`git ls-files` de `racine`, SEULE source de l'univers ; git inutilisable ⇒ `CliquetError`."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    try:
        p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(racine), "ls-files", "-z"], env=env,
                           capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CliquetError(f"git inutilisable ({type(exc).__name__}: {exc}) — l'univers ne se lit que par "
                           f"`git ls-files`") from exc
    if p.returncode != 0:
        raise CliquetError(f"git ls-files rc {p.returncode} : {p.stderr.decode('utf-8', 'replace').strip()}")
    return [f for f in p.stdout.decode("utf-8").split("\0") if f]


def dans_univers(chemin: str) -> bool:
    return (chemin.startswith(UNIVERS) and chemin.endswith((".py", ".sh")) and not BANC.search(chemin)
            and not chemin.startswith(HORS_UNIVERS)
            and ("/vendor/" not in chemin or chemin.startswith(".agents/vendor/agentic_v3/")))


def chemin_liste(chemin: str) -> str:
    vendor = ".agents/vendor/agentic_v3/"
    return "agentic_v3/" + chemin[len(vendor):] if chemin.startswith(vendor) else chemin


def _docstrings(arbre: ast.AST) -> set[int]:
    vus: set[int] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.body \
                and isinstance(noeud.body[0], ast.Expr) and isinstance(noeud.body[0].value, ast.Constant):
            vus.add(id(noeud.body[0].value))
    return vus


def occurrences(texte: str, suffixe: str) -> int:
    """Le nombre d'occurrences selon les RÈGLES de la docstring. `.py` illisible ⇒ `SyntaxError`, jamais 0."""
    lignes = [ligne for ligne in texte.splitlines() if not ligne.lstrip().startswith("#")]
    if suffixe != ".py":
        return sum(1 for ligne in lignes if MOTIF.search(ligne) or JOINTURE.search(ligne))
    arbre = ast.parse(texte)
    docstrings = _docstrings(arbre)
    n = sum(1 for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and id(noeud) not in docstrings
            and MOTIF.search(noeud.value))
    return n + sum(1 for ligne in lignes if JOINTURE.search(ligne))


def relever(racine: Path) -> dict[str, int]:
    """Chaque fichier de l'univers qui nomme un magasin → son nombre d'occurrences."""
    releve: dict[str, int] = {}
    suivis = set(fichiers_suivis(racine))
    for chemin in sorted(suivis):
        if not dans_univers(chemin):
            continue
        if chemin.startswith("agentic_v3/") and ".agents/vendor/" + chemin in suivis:
            continue
        try:
            texte = (racine / chemin).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CliquetError(f"{chemin} : suivi mais illisible ({type(exc).__name__})") from exc
        try:
            n = occurrences(texte, Path(chemin).suffix)
        except SyntaxError as exc:
            raise CliquetError(f"{chemin} : illisible par `ast` ({exc.msg}, ligne {exc.lineno}) — un fichier "
                               f"qu'on ne lit pas n'est jamais « rien à signaler »") from exc
        if n:
            releve[chemin_liste(chemin)] = n
    return releve


class CliquetLecteursEtatTests(unittest.TestCase):
    releve: dict[str, int]

    @classmethod
    def setUpClass(cls) -> None:
        # adopting-tree: marqueur du kit, absent chez l'adoptant
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            raise unittest.SkipTest("`.agents/IS_THE_KIT` absent (adoptant) : la LISTE nomme les fichiers du kit")
        cls.releve = relever(ROOT)  # git inutilisable ou `.py` illisible : CliquetError, le banc ROUGIT

    def test_c1_aucun_fichier_hors_liste(self) -> None:
        hors = sorted(set(self.releve) - set(LISTE))
        self.assertEqual(hors, [], f"fichier(s) qui nomment un magasin d'état hors LISTE — {REMEDE}")

    def test_c2_aucune_entree_perimee(self) -> None:
        perimees = sorted(set(LISTE) - set(self.releve))
        self.assertEqual(perimees, [], f"entrée(s) de LISTE qui ne nomment plus aucun magasin — {REMEDE}")

    def test_liste_bien_formee(self) -> None:
        for chemin, (categorie, suite) in LISTE.items():
            with self.subTest(chemin=chemin):
                self.assertTrue(dans_univers(chemin), "entrée hors univers")
                self.assertIn(categorie, CATEGORIES)
                self.assertIn(suite, SUITES)
                self.assertEqual(categorie == PROPRIETAIRE, suite == "aucune", "seul un propriétaire n'a pas de suite")


class DetecteurTests(unittest.TestCase):
    def test_vendor_board_reste_dans_la_liste_unique(self) -> None:
        ancien = "agentic_v3/reconciliation/board_bridge.py"
        vendor = ".agents/vendor/" + ancien
        self.assertTrue(dans_univers(vendor))
        self.assertEqual(chemin_liste(vendor), ancien)
        self.assertFalse(dans_univers(".agents/vendor/autre/reader.py"))

    def test_c3_detecteur_non_aveugle(self) -> None:
        for suffixe, texte in POSITIFS:
            with self.subTest(positif=texte):
                self.assertGreater(occurrences(texte, suffixe), 0)
        for suffixe, texte in NEGATIFS:
            with self.subTest(negatif=texte):
                self.assertEqual(occurrences(texte, suffixe), 0)

    def test_idiomes_non_detectes(self) -> None:
        for nom, extraits in IDIOMES_NON_DETECTES.items():
            for suffixe, texte in extraits:
                with self.subTest(idiome=nom, extrait=texte):
                    self.assertEqual(occurrences(texte, suffixe), 0, "l'idiome est détecté : la borne doit suivre")
        self.assertEqual(len(IDIOMES_NON_DETECTES), 7)

    def test_illisible_et_git_inutilisable_rougissent(self) -> None:
        with self.assertRaises(SyntaxError):
            occurrences("def (:\n", ".py")
        with mock.patch.dict(os.environ, {"PATH": ""}):
            with self.assertRaises(CliquetError):
                fichiers_suivis(ROOT)


def _imprimer_releve() -> int:
    """`--relever` : la LISTE mesurée, prête à recopier, et l'écart à la LISTE du banc. N'écrit rien."""
    releve = relever(ROOT)
    print("LISTE: dict[str, tuple[str, str]] = {")
    for chemin in sorted(releve):
        categorie, suite = LISTE.get(chemin, ("À CLASSER", "À NOMMER"))
        print(f'    "{chemin}": ({categorie!r}, {suite!r}),  # {releve[chemin]} occurrence(s)')
    print("}")
    print(f"# {len(releve)} fichier(s) ; hors LISTE : {sorted(set(releve) - set(LISTE)) or '-'} ; "
          f"périmées : {sorted(set(LISTE) - set(releve)) or '-'}")
    return 0


if __name__ == "__main__":
    if "--relever" in sys.argv[1:]:
        sys.exit(_imprimer_releve())
    unittest.main()
