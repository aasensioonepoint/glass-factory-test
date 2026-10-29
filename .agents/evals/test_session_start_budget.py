"""Le SessionStart de Claude tient sous le plafond d'additionalContext (T-00000834).

POURQUOI CE BANC EXISTE. Claude Code ne rend au modèle un additionalContext
qu'en dessous d'environ 10 000 caractères ; au-delà il le remplace par un
APERÇU de 2 ko, sans erreur. Relevé le 2026-09-29 sur les transcripts de ce
dépôt : toutes les injections de `session-start.sh` depuis le 2026-09-24
(72 à 85 ko) étaient réduites à l'aperçu — le début de l'index. Board, ledger
et état de chantier n'arrivaient jamais au modèle.

CE QU'IL PROUVE : sur une racine factice qui déborde de partout (board de 40
pending, PLAN-ETAT de 60 ko, index énorme), la sortie reste sous le budget, le
board passe en tête, et chaque coupe est ANNONCÉE avec où lire le reste.
CE QU'IL NE PROUVE PAS : la valeur exacte du plafond de l'hôte — c'est un
relevé, pas une API documentée ; `SS_BUDGET` garde ~600 octets de marge.

La racine factice ne porte que les fichiers de `tasks.py` : ni
`dashboard_daemon.py` (aucun démon lancé), ni `build_index.py` (aucune
réindexation), ni `emit-event.sh` — le hook les saute tous en silence.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-start.sh"
BASH = shutil.which("bash")
PLAFOND_HOTE = 10_000


def _racine(
    tmp: Path,
    pending: int,
    index_octets: int = 800,
    plan_octets: int = 0,
    blocked: int = 1,
    sorties: bool = False,
) -> Path:
    bin_dir = tmp / ".agents" / "bin"
    bin_dir.mkdir(parents=True)
    for source in (ROOT / ".agents" / "bin").glob("tasks*.py"):
        if not source.name.startswith("test_"):
            shutil.copy2(source, bin_dir / source.name)
    today = date.today().isoformat()
    rows = [
        {"id": "T-00000001", "state": "running", "task": "en cours", "owner": "dev-mono", "stage": "", "updated": today},
    ] + [
        {"id": f"T-{n:08d}", "state": "blocked", "task": f"b{n}", "owner": "planner", "stage": "", "updated": today}
        for n in range(2, 2 + blocked)
    ] + [
        {"id": f"T-{n:08d}", "state": "pending", "task": f"p{n}", "owner": "dev-mono", "stage": "", "updated": today}
        for n in range(100, 100 + pending)
    ]
    board = tmp / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True)
    board.write_text(json.dumps({"next_id": 100 + pending, "tasks": rows}), encoding="utf-8")
    index = tmp / ".agents" / "state" / "index" / "CODEBASE_INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text("# Codebase index\n" + "x" * index_octets + "\n", encoding="utf-8")
    if plan_octets:
        # Fin de ligne FINALE exprès : `$(…)` la mange, et c'est ce qui faisait
        # annoncer une troncature sur un fichier injecté en entier.
        (tmp / "PLAN-ETAT.md").write_text("# PLAN-ETAT\n" + "é" * (plan_octets // 2) + "\n", encoding="utf-8")
    if sorties:
        # Une ligne datée que `_SO_MOTIF` de session-start.sh retient : le bloc
        # critique « SORTIES SANS BINÔME » part alors en tête, hors de la coupe.
        local = tmp / ".agents" / "state" / "local"
        local.mkdir(parents=True, exist_ok=True)
        (local / "affirmation-sorties.log").write_text("2026-10-24T08:00:00Z sortie x\n", encoding="utf-8")
    return tmp


def _injecte(racine: Path) -> str:
    out = subprocess.run(
        [BASH, str(HOOK)],
        env={"PATH": __import__("os").environ["PATH"], "CLAUDE_PROJECT_DIR": str(racine)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.stdout.strip(), f"le hook n'a rien émis — stderr : {out.stderr[:400]}"
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]


# Le préfixe que la jambe Python du hook pose devant le contexte : HORS budget (le budget borne
# ce que le shell compose ; le plafond hôte de 10 000 caractères, lui, l'inclut — décision du plan
# T-01M4NBTSPT14QQD75XG0AB36X2, angle mort tranché au défaut recommandé).
PREFIXE = "[AUTO-INJECTED INDEX — do not re-read these files]\n"
# La réserve que le hook prend pour sa ligne `[CONTEXTE TRONQUÉ : …]` au moment de la coupe.
RESERVE_COUPE = 300


def _ss_budget() -> int:
    """`SS_BUDGET` LU dans le hook, jamais recopié ici (L-00000132) : un budget retouché déplace
    le témoin avec lui au lieu de le figer sur 9 400."""
    m = re.search(r"^SS_BUDGET=(\d+)$", HOOK.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, "SS_BUDGET introuvable dans session-start.sh — ce banc ne sait plus ce qu'il borne"
    return int(m.group(1))


def _octets_hors_prefixe(ctx: str) -> int:
    """Les octets que le SHELL a composés : le contexte sans `PREFIXE`. `surrogateescape` rend
    à l'identique les octets d'un caractère UTF-8 que `head -c` aurait coupé en deux."""
    assert ctx.startswith(PREFIXE), f"préfixe d'injection absent : {ctx[:80]!r}"
    return len(ctx[len(PREFIXE):].encode("utf-8", "surrogateescape"))


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude Code hook")
class SessionStartBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_debordement_de_partout_reste_sous_le_plafond_et_le_dit(self) -> None:
        ctx = _injecte(_racine(self.tmp, pending=40, plan_octets=60_000))
        self.assertLess(len(ctx), PLAFOND_HOTE)
        self.assertIn("T-00000001", ctx, "la tâche running doit passer")
        self.assertIn("(+20 less recently updated pending not shown", ctx)
        self.assertIn("ÉTAT DE CHANTIER — PLAN-ETAT.md", ctx)
        self.assertIn("lis PLAN-ETAT.md en entier", ctx)

    def test_le_board_passe_avant_l_etat_de_chantier(self) -> None:
        ctx = _injecte(_racine(self.tmp, pending=5, plan_octets=60_000))
        self.assertLess(ctx.index("## TASK BOARD"), ctx.index("ÉTAT DE CHANTIER"))

    def test_un_etat_qui_tient_passe_entier_sans_annonce(self) -> None:
        ctx = _injecte(_racine(self.tmp, pending=3, plan_octets=400))
        self.assertIn("ÉTAT DE CHANTIER — PLAN-ETAT.md", ctx)
        self.assertNotIn("TRONQUÉ", ctx)
        self.assertNotIn("NON INJECTÉ", ctx)

    def test_moins_qu_un_paragraphe_devient_un_pointeur(self) -> None:
        ctx = _injecte(_racine(self.tmp, pending=40, blocked=40, plan_octets=60_000))
        self.assertLess(len(ctx), PLAFOND_HOTE)
        self.assertIn("lis PLAN-ETAT.md en entier", ctx)

    def test_garde_fou_global_coupe_le_detail_jamais_le_board(self) -> None:
        ctx = _injecte(_racine(self.tmp, pending=3, index_octets=30_000))
        self.assertLess(len(ctx), PLAFOND_HOTE)
        self.assertIn("CONTEXTE TRONQUÉ", ctx)
        self.assertIn("T-00000001", ctx, "la tâche running doit survivre à la coupe")

    def test_les_sorties_sans_binome_survivent_a_un_board_geant(self) -> None:
        """Le bloc critique (`_SS_CRIT`) passe EN TÊTE et hors de toute coupe, même
        quand le board et l'index débordent. Rouge sous le mutant
        `CTX="$_SS_CRIT$CTX$_SS_PE"` → `CTX="$CTX$_SS_PE"`."""
        ctx = _injecte(_racine(self.tmp, pending=25, blocked=45, index_octets=30_000, sorties=True))
        self.assertLess(len(ctx), PLAFOND_HOTE)
        self.assertIn("## SORTIES SANS BINÔME", ctx)
        self.assertLess(ctx.index("## SORTIES SANS BINÔME"), ctx.index("## TASK BOARD"))

    def test_la_coupe_annoncee_tient_sous_ss_budget(self) -> None:
        """T-01M4NBTSPT14QQD75XG0AB36X2. Une coupe ANNONCÉE ne rajoute pas sa ligne PAR-DESSUS le
        budget : la tête coupée ET sa ligne `[CONTEXTE TRONQUÉ : …]` tiennent sous `SS_BUDGET`.
        Rouge à la base (9 558 > 9 400 : la ligne s'ajoutait après une tête pleine) et sous le
        mutant M-reserve-0 (réserve à la coupe ramenée à 0)."""
        budget = _ss_budget()
        fixtures = {
            "garde-fou": dict(pending=3, index_octets=30_000),
            "sorties": dict(pending=25, blocked=45, index_octets=30_000, sorties=True),
            "pointeur": dict(pending=40, blocked=40, plan_octets=60_000),
        }
        for nom, kw in fixtures.items():
            with self.subTest(fixture=nom):
                racine = self.tmp / nom
                racine.mkdir()
                ctx = _injecte(_racine(racine, **kw))
                self.assertIn("CONTEXTE TRONQUÉ", ctx,
                              f"contrôle de la fixture {nom} : elle doit passer par la coupe globale")
                n = _octets_hors_prefixe(ctx)
                self.assertLessEqual(
                    n, budget,
                    f"fixture {nom} : {n} octets composés pour un budget de {budget} — la ligne de "
                    "coupe s'ajoute au-delà du budget qu'elle annonce tenir")

    def test_un_contexte_qui_tient_n_est_pas_coupe(self) -> None:
        """T-01M4NBTSPT14QQD75XG0AB36X2. La réserve se prend AU MOMENT de la coupe, jamais sur tout
        le plafond : un contexte qui tient sous le budget sans coupe n'est pas coupé. Vert à la
        base ; rouge sous le mutant M-plafond-global (`_SS_PLAFOND` amputé de 300 pour tous,
        mesuré : contexte coupé à 9 257 octets)."""
        budget = _ss_budget()
        ctx = _injecte(_racine(self.tmp, pending=40, plan_octets=60_000))
        n = _octets_hors_prefixe(ctx)
        # PRÉCONDITION (réserve C2 de plan-critic, L-00000318) : ce témoin ne discrimine que si la
        # fixture pèse dans ]budget - réserve, budget] — en dessous, une réserve prise sur tout le
        # plafond ne couperait rien non plus et ce vert ne dirait rien.
        self.assertTrue(
            budget - RESERVE_COUPE < n <= budget,
            f"CALIBRATION : la fixture débordement pèse {n} octets, hors de "
            f"]{budget - RESERVE_COUPE}, {budget}] — elle ne discrimine plus une réserve prise sur "
            "tout le plafond ; recalibre pending/plan_octets (la taille dépend des tasks*.py copiés)")
        self.assertNotIn("CONTEXTE TRONQUÉ", ctx,
                         f"un contexte de {n} octets tient sous {budget} et a pourtant été coupé")


# Le STUB d'un outil d'état (`tasks.py`, `ledger.py`) : il note son argv dans une SENTINELLE à côté
# de lui (preuve qu'il a été APPELÉ), puis rend une 1re ligne marquée et, au besoin, un remplissage.
_STUB = (
    "import os, sys\n"
    "with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), {sentinelle!r}), 'a') as fh:\n"
    "    fh.write(' '.join(sys.argv[1:]) + '\\n')\n"
    "print({marque!r} + ' argv=' + ' '.join(sys.argv[3:]))\n"
    "print('y' * {remplissage})\n"
)


def _racine_formes(
    tmp: Path,
    board: str = "",
    ledger: str = "",
    remplissage: int = 0,
) -> Path:
    """Une racine factice dont les magasins sont en FORME DOSSIER (T-00001012) : aucun `TASKS.json`
    ni `LEDGER.json`. ``board`` / ``ledger`` : ``"enregistrement"`` (un ``<id>.json`` réel),
    ``"vide"`` (dossier vide, ou un nom POINTÉ seul — le temporaire d'une écriture atomique), ``""``
    (absent). `tasks.py` et `ledger.py` sont des STUBS toujours présents : le contenu passe par
    l'API, et seule la GARDE de présence est sous test. Un petit index garantit une sortie."""
    bin_dir = tmp / ".agents" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "tasks.py").write_text(
        _STUB.format(sentinelle="tasks.appele", marque="STUB-TASKS", remplissage=remplissage), encoding="utf-8")
    (bin_dir / "ledger.py").write_text(
        _STUB.format(sentinelle="ledger.appele", marque="STUB-LEDGER", remplissage=0), encoding="utf-8")
    index = tmp / ".agents" / "state" / "index" / "CODEBASE_INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text("# Codebase index\nfin-de-l-index\n", encoding="utf-8")
    taches = tmp / ".agents" / "state" / "board" / "tasks"
    entrees = tmp / ".agents" / "state" / "memory" / "entries"
    if board:
        taches.mkdir(parents=True)
    if board == "enregistrement":
        (taches / "T-00000001.json").write_text(
            '{"format": 1, "id": "T-00000001", "record": {"id": "T-00000001"}, "sync_operations": []}\n',
            encoding="utf-8")
    if ledger:
        entrees.mkdir(parents=True)
    if ledger == "enregistrement":
        (entrees / "L-00000001.json").write_text(
            '{"format": 1, "id": "L-00000001", "record": {"id": "L-00000001"}}\n', encoding="utf-8")
    elif ledger == "vide":
        (entrees / ".x.json").write_text("{}\n", encoding="utf-8")
    return tmp


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude Code hook")
class SessionStartFormesTests(unittest.TestCase):
    """LES DEUX FORMES DES MAGASINS (T-00001012, BK-419, E-26). Un board ou un ledger passés en un
    fichier par enregistrement (`board/tasks/<id>.json`, `memory/entries/<id>.json`) doivent ARMER
    les mêmes appels d'API que leur monolithe, sous le même budget. S1, S2 et S4 sont ROUGES à la base
    (gardes `[ -f TASKS.json ]` / `[ -f LEDGER.json ]` seules) ; S3 est un CONTRÔLE vert à la base.
    Mutants tués : M-garde-mono (S1 board, S2 ledger), M-dossier-nu (`[ -d ]`, S3),
    M-board-hors-budget (le board ajouté hors de CTX, S4)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _appele(self, nom: str) -> bool:
        return (self.tmp / ".agents" / "bin" / f"{nom}.appele").exists()

    def test_s1_board_en_dossier_seul_arme_tasks_list_session(self) -> None:
        ctx = _injecte(_racine_formes(self.tmp, board="enregistrement"))
        self.assertIn("STUB-TASKS argv=list --session", ctx)
        self.assertTrue(self._appele("tasks"))

    def test_s2_ledger_en_dossier_seul_arme_ledger_context(self) -> None:
        ctx = _injecte(_racine_formes(self.tmp, ledger="enregistrement"))
        self.assertIn("STUB-LEDGER argv=context", ctx)
        self.assertTrue(self._appele("ledger"))

    def test_s3_controle_dossiers_sans_enregistrement_n_arment_rien(self) -> None:
        ctx = _injecte(_racine_formes(self.tmp, board="vide", ledger="vide"))
        self.assertIn("fin-de-l-index", ctx, "contrôle de la fixture : l'index doit passer")
        self.assertFalse(self._appele("tasks"), "tasks/ vide : aucun appel de tasks.py attendu")
        self.assertFalse(self._appele("ledger"), "entries/ au seul nom pointé : aucun appel de ledger.py attendu")
        self.assertNotIn("## TASK BOARD", ctx)

    def test_s4_board_en_dossier_reste_sous_le_budget(self) -> None:
        ctx = _injecte(_racine_formes(self.tmp, board="enregistrement", remplissage=30_000))
        self.assertLess(len(ctx), PLAFOND_HOTE)
        self.assertIn("CONTEXTE TRONQUÉ", ctx)
        self.assertIn("STUB-TASKS argv=list --session", ctx, "la 1re ligne du board doit survivre à la coupe")


if __name__ == "__main__":
    unittest.main()
