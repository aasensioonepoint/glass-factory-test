"""W24-W26 — LA DOCTRINE DE LA VOIE DIRECTE, TENUE PAR LE CODE (T-00001178, étape 7).

CE QUE CE BANC TIENT — trois propriétés de PROSE que la voie directe a fait
naître, et que rien d'autre ne tient :

- W24, PARITÉ DU SEUIL. Le seuil vit dans UNE constante, `MAX_FICHIERS_DIRECT`
  (`.agents/bin/tasks_direct.py`), LUE ICI PAR `ast`, jamais recopiée : la voie
  directe vaut pour N fichiers OU MOINS, et le plan est requis à partir de N + 1
  (S-00004135). Chaque phrase de la liste fermée `SURFACES_SEUIL` qui répète ce
  nombre doit dire l'un ou l'autre. Une phrase qui dirait encore « plus de 3
  fichiers », ou « moins de 5 » (la forme que S-00004135 a remplacée), affirmerait
  une garantie que le code ne tient plus (L-00000111).
- W25, LES GRAINES. Chaque graine (`PLAN_CHAIN_REQUIRED`, `PLAN_CIBLE_REQUIRED`)
  nomme `tasks.py direct`. Ce test RESTE ROUGE tant que le geste pilote de l'étape
  8 n'a pas eu lieu (chemins protégés : aucun agent ne les écrit). C'est voulu :
  le geste ne s'oublie donc pas.
- W26, LES CINQ ORCHESTRATEURS. Dans chaque hôte, le paragraphe « ROUTES axis »
  (« Axe des ROUTES » avant la traduction des défs, T-01M5S9338BJP1B5RM3TG14AMYT ;
  l'ancre exclut le renvoi « the ROUTES axis ») et la règle (1) « No execution
  without a … » nomment `tasks.py direct`.
  La règle (1) disait « never otherwise », et la voie directe l'enfreint à la
  lettre ; un axe des routes qui ne la compterait pas serait une énumération sous
  titre universel (L-00000187).

ÉCART AU PLAN, DIT. Le plan (rév. 4, étape 7) demande « un motif de capture par
surface ». Ce banc applique à chaque surface UNE FAMILLE FERMÉE de motifs
(`FAMILLE`, anglais et français, chiffres et nombres en toutes lettres). La
raison : les shards A et B écrivent leurs phrases en parallèle de ce shard, sur un
contrat figé qui fixe le NOMBRE et non la TOURNURE. Un motif par surface épinglé
à l'aveugle rougirait sur une tournure juste. La propriété « chaque surface est
vue » est gardée autrement : toute surface de `SURFACES_SEUIL` doit porter au
moins une capture, sinon c'est un échec, jamais un saut.

BORNE DITE. `SURFACES_SEUIL` liste les porteurs CONNUS : le `git grep` du
2026-10-05 sur l'énumération de l'étape 6, plus `tasks_cli.py` et
`tasks_mesure.py`. Ce banc ne voit pas :
- un porteur neuf ;
- une phrase hors de la famille (« over 3 files », un nombre coupé entre deux
  littéraux Python).
Restent HORS liste, chacun pour sa raison :
- `docs/usage.html` et `.agents/skills/task-board/SKILL.md` : gelés, tâche de suite ;
- `docs/HISTORIQUE-0.1.0.md` (le journal figé ; `CHANGELOG.md` ne porte plus de
  seuil), `PLAN-ETAT*.md`, `docs/design/`, `docs/tasks/`, `docs/interne/` :
  archives datées, où l'ancien seuil est un fait d'histoire ;
- `tasks_direct.py` : il PORTE la constante ;
- `.agents/skills/planning/SKILL.md` : appartient à T-00001129.
`SURFACES_VEILLE` liste les surfaces que le shard B réécrit sans que le plan leur
promette un nombre. Elles sont contrôlées SI elles en portent un, sans plancher.

CE BANC SE TAIT CHEZ L'ADOPTANT. Il lit des surfaces du kit. Chaque classe qui
les lit saute par un `skipTest` NOMMÉ en `setUp` quand `.agents/IS_THE_KIT` est
absent : c'est la forme (c) du localisateur de `test_adopting_gate.py`. Aucune
ligne `strip:` n'est posée : `.template-exclude` est gelé par T-00000781 et
T-00001088, la ligne viendra avec la tâche de suite. Un saut n'est pas un vert qui
prouve. Les contrôles synthétiques de la famille de motifs ne lisent aucune
surface et tournent partout.

ROUGE PAR CONSTRUCTION DANS LE WORKTREE DU SHARD C SEUL. W24 lit `tasks_direct.py`
et les phrases des shards A et B. L'ordre de fusion est A, B, C : ce banc est
fusionné en dernier.
"""

from __future__ import annotations

import ast
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# LA SOURCE DU SEUIL : un fichier, un nom. La valeur n'est écrite nulle part ici.
SOURCE_SEUIL = ".agents/bin/tasks_direct.py"
NOM_SEUIL = "MAX_FICHIERS_DIRECT"

# LES PORTEURS CONNUS DU SEUIL — chacun DOIT porter au moins une capture.
SURFACES_SEUIL: tuple[str, ...] = (
    # shard C (ce shard) : descriptions, règle DIRECT, renvoi de l'optimizer
    ".claude/agents/orchestrator.md",
    ".gemini/agents/orchestrator.md",
    ".kimi-code/agents/orchestrator.md",
    ".codex/agents/orchestrator.toml",
    ".github/agents/orchestrator.agent.md",
    ".claude/agents/optimizer.md",
    ".gemini/agents/optimizer.md",
    ".kimi-code/agents/optimizer.md",
    # shard A : aide du motif `gros`, son sens, la table et la docstring de la garde
    ".agents/bin/tasks_cli.py",
    ".agents/bin/tasks_mesure.py",
    ".agents/bin/kickoff_guard.py",
    # shard B : la règle du pipeline et ses répétitions
    "AGENTS.md",
    ".github/copilot-instructions.md",
    "README.md",
    ".agents/skills/kickoff/SKILL.md",
)

# Réécrites par le shard B sans nombre promis : contrôlées SI elles en portent un.
SURFACES_VEILLE: tuple[str, ...] = (
    "CLAUDE.md",
    "README-CLAUDE.md",
    "README-OTHER-HOSTS.md",
    "docs/PROMPT-projet.md",
    ".claude/commands/kickoff.md",
)

PLANCHER_SURFACES = 8

_NOMBRES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}
_N = (
    r"(?<![\w.])(\d+|"
    + "|".join(sorted(_NOMBRES, key=len, reverse=True))
    + r")(?!\w)"
)

# LA FAMILLE FERMÉE. Chaque motif capture UN nombre et dit ce qu'il implique :
# `plan_des = nombre + decalage` est le premier compte de fichiers qui exige un
# plan. « 6 files or more » -> 6 ; « more than 5 files » -> 6 ; « 5 files or
# fewer » -> 6 ; « moins de 5 fichiers » -> 5, donc refusé.
FAMILLE: tuple[tuple[str, re.Pattern[str], int], ...] = tuple(
    (nom, re.compile(motif, re.IGNORECASE), decalage)
    for nom, motif, decalage in (
        ("N files or more", rf"{_N}\s+files?\s+or\s+more\b", 0),
        ("more than N files", rf"\bmore\s+than\s+~?{_N}\s+files?\b", 1),
        ("> N files", rf"(?:>|&gt;)\s*~?{_N}\s+files?\b", 1),
        ("N files or fewer", rf"{_N}\s+files?\s+or\s+(?:fewer|less)\b", 1),
        ("fewer than N files", rf"\b(?:fewer|less)\s+than\s+{_N}\s+files?\b", 0),
        ("at most N files", rf"\b(?:at\s+most|up\s+to)\s+{_N}\s+(?:exact\s+)?(?:files?|paths?)\b", 1),
        ("N fichiers ou plus", rf"{_N}\s+fichiers?\s+ou\s+plus\b", 0),
        ("plus de N fichiers", rf"\bplus\s+de\s+~?{_N}\s+fichiers?\b", 1),
        ("N fichiers ou moins", rf"{_N}\s+fichiers?\s+ou\s+moins\b", 1),
        ("moins de N fichiers", rf"\bmoins\s+de\s+{_N}\s+fichiers?\b", 0),
        ("a partir de N fichiers", rf"(?:\ba|à)\s+partir\s+de\s+{_N}\s+fichiers?\b", 0),
        ("> N chemins", rf"(?:>|&gt;)\s*{_N}\s+chemins?\b", 1),
        ("plus de N chemins", rf"\bplus\s+de\s+{_N}\s+chemins?\b", 1),
        ("N chemins ou moins", rf"{_N}\s+chemins?(?:\s+exacts?)?\s+ou\s+(?:-|moins)", 1),
    )
)


@dataclass(frozen=True)
class Capture:
    motif: str
    nombre: int
    plan_des: int
    debut: int
    fin: int
    ligne: int


def _valeur(jeton: str) -> int:
    return int(jeton) if jeton.isdigit() else _NOMBRES[jeton.casefold()]


def captures(texte: str) -> list[Capture]:
    """Toutes les répétitions du seuil dans `texte`, une par nombre (la même
    position prise par deux motifs ne compte qu'une fois), dans l'ordre du texte."""
    vues: dict[int, Capture] = {}
    for nom, motif, decalage in FAMILLE:
        for m in motif.finditer(texte):
            debut, fin = m.span(1)
            if debut in vues:
                continue
            n = _valeur(m.group(1))
            vues[debut] = Capture(nom, n, n + decalage, debut, fin, texte.count("\n", 0, debut) + 1)
    return [vues[k] for k in sorted(vues)]


def violations(texte: str, max_direct: int) -> list[Capture]:
    """LA RÈGLE, en fonction, pour que les mutants rejouent CETTE règle
    (L-00000057) : toute capture doit impliquer « plan requis à partir de
    max_direct + 1 »."""
    return [c for c in captures(texte) if c.plan_des != max_direct + 1]


def lire_seuil(source: str) -> int:
    """La constante, lue dans le code par `ast` : UNE affectation de tête, un
    entier littéral ≥ 1. Deux affectations, ou une expression, sont refusées au
    lieu d'être devinées."""
    valeurs = []
    for noeud in ast.parse(source).body:
        if isinstance(noeud, ast.Assign) and any(
            isinstance(cible, ast.Name) and cible.id == NOM_SEUIL for cible in noeud.targets
        ):
            valeurs.append(noeud.value)
        elif (
            isinstance(noeud, ast.AnnAssign)
            and isinstance(noeud.target, ast.Name)
            and noeud.target.id == NOM_SEUIL
        ):
            valeurs.append(noeud.value)
    if len(valeurs) != 1:
        raise ValueError(f"{NOM_SEUIL} : {len(valeurs)} affectation(s) de tête, une seule attendue")
    valeur = valeurs[0]
    if not (isinstance(valeur, ast.Constant) and type(valeur.value) is int and valeur.value >= 1):
        raise ValueError(f"{NOM_SEUIL} n'est pas un entier littéral ≥ 1")
    return valeur.value


def muter_premiere_capture(texte: str, valeur: str = "4") -> str:
    c = captures(texte)[0]
    return texte[: c.debut] + valeur + texte[c.fin :]


def _decrire(rel: str, liste: list[Capture]) -> str:
    return "; ".join(f"{rel}:{c.ligne} « {c.motif} » n={c.nombre} -> plan dès {c.plan_des}" for c in liste)


# ---------------------------------------------------------------------------
# W26 — les cinq orchestrateurs
# ---------------------------------------------------------------------------
ORCHESTRATEURS = {
    "claude": ".claude/agents/orchestrator.md",
    "codex": ".codex/agents/orchestrator.toml",
    "gemini": ".gemini/agents/orchestrator.md",
    "copilot": ".github/agents/orchestrator.agent.md",
    "kimi": ".kimi-code/agents/orchestrator.md",
}
VERBE = "tasks.py direct"
#: Le titre du paragraphe (`**ROUTES axis —`, `ROUTES axis:`, `*ROUTES axis*`), jamais son renvoi
#: « the ROUTES axis bounds… » : unique par hôte, comme l'était « Axe des ROUTES ».
ANCRE_ROUTES_TEXTE = "ROUTES axis"
ANCRE_ROUTES = re.compile(r"(?<!the )ROUTES axis")
ANCRE_ROUTES_FIN = "ENTRY POINTS axis"
ANCRE_REGLE_1 = "No execution without a"  # le fragment de test_gates_chain_contract.py
ANCRE_REGLE_1_FIN = "Max 8 round trips"  # la règle (2), sur les cinq hôtes


def tranche(texte: str, debut: str | re.Pattern[str], fin: str) -> str | None:
    """Le texte entre deux ancres. None si une ancre manque OU si l'ancre de début
    est ambiguë : l'appelant le traite en ÉCHEC, jamais en tranche vide qui
    satisferait tout (L-00000186)."""
    if isinstance(debut, re.Pattern):
        vues = [m.start() for m in debut.finditer(texte)]
        if len(vues) != 1:
            return None
        i = vues[0]
    else:
        if texte.count(debut) != 1:
            return None
        i = texte.find(debut)
    j = texte.find(fin, i)
    return None if j < 0 else texte[i:j]


def violations_orchestrateur(hote: str, texte: str) -> list[str]:
    fautes = []
    routes = tranche(texte, ANCRE_ROUTES, ANCRE_ROUTES_FIN)
    if routes is None:
        fautes.append(f"{hote} : paragraphe « {ANCRE_ROUTES_TEXTE} » introuvable ou ambigu")
    elif VERBE not in routes:
        fautes.append(f"{hote} : l'axe des routes ne nomme pas `{VERBE}`")
    regle = tranche(texte, ANCRE_REGLE_1, ANCRE_REGLE_1_FIN)
    if regle is None:
        fautes.append(f"{hote} : règle (1) « {ANCRE_REGLE_1} » introuvable ou ambiguë")
    elif VERBE not in regle:
        fautes.append(f"{hote} : la règle (1) ne borne pas son « never otherwise » par `{VERBE}`")
    return fautes


# ---------------------------------------------------------------------------
# W25 — les graines
# ---------------------------------------------------------------------------
GRAINES = ("PLAN_CHAIN_REQUIRED", "PLAN_CIBLE_REQUIRED")


def violations_graine(nom: str, texte: str) -> list[str]:
    return [] if VERBE in texte else [f"graine {nom} : ne nomme pas `{VERBE}`"]


# ---------------------------------------------------------------------------
# La famille de motifs, sur des échantillons : aucune surface lue, tourne partout
# ---------------------------------------------------------------------------
class CapturesSeuilTests(unittest.TestCase):
    """La règle de W24 mord, sur des phrases écrites ICI (L-00000261)."""

    CONFORMES_A_5 = (
        "If the fix requires 6 files or more, hand back to `planner`.",
        "Pipeline mandatory for any task touching 6 files or more.",
        "DIRECT task — 5 files or fewer, admitted by the CODE.",
        "a task touching more than 5 files",
        "Mandatory for any task (>5 files, refactor)",
        "une tâche de cinq fichiers ou moins passe sans plan",
        "le plan est requis à partir de 6 fichiers",
        "6 fichiers ou plus",
        "writeset > 5 chemins exacts → ARMEE ; writeset de 5 chemins exacts ou - → NON armee",
        "a declared write-set of at most 5 exact paths",
    )
    FAUTIVES_A_5 = (
        "If the fix requires > 3 files, hand back to `planner`.",
        "any task touching more than 3 files or any refactor",
        "Any task touching more than ~3 files",
        "une tâche de moins de 5 fichiers",  # la forme que S-00004135 a remplacée
        "une tâche de trois fichiers ou moins passe sans plan",
        "the fix touches 5 files or more, or needs a plan",
        "plus de 3 fichiers",
        "writeset > 3 chemins exacts",
        "16 files or more",  # « 16 » n'est jamais lu « 6 »
    )

    def test_les_phrases_conformes_passent(self) -> None:
        for phrase in self.CONFORMES_A_5:
            with self.subTest(phrase=phrase):
                self.assertTrue(captures(phrase), f"aucune capture : la famille ne voit pas {phrase!r}")
                self.assertEqual(violations(phrase, 5), [], phrase)

    def test_les_phrases_fautives_rougissent(self) -> None:
        for phrase in self.FAUTIVES_A_5:
            with self.subTest(phrase=phrase):
                self.assertTrue(violations(phrase, 5), f"LA RÈGLE NE MORD PAS sur {phrase!r}")

    def test_une_phrase_sans_seuil_ne_capture_rien(self) -> None:
        for phrase in (
            "8 fichiers quand docs/tasks/** en vaut 216",
            "refactors over 3 files stay out of the main context",
            "90 des 181 `done` récents",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(captures(phrase), [], phrase)

    def test_la_regle_suit_la_constante(self) -> None:
        """Mutant « constante mutée » : la même phrase juste à 5 est fautive à 4."""
        self.assertEqual(violations("6 files or more", 5), [])
        self.assertTrue(violations("6 files or more", 4))

    def test_lire_seuil_refuse_ce_qu_il_ne_peut_pas_lire(self) -> None:
        self.assertEqual(lire_seuil(f"# x\n{NOM_SEUIL} = 5\n"), 5)
        self.assertEqual(lire_seuil(f"{NOM_SEUIL}: int = 7\n"), 7)
        for source in ("X = 5\n", f"{NOM_SEUIL} = 5\n{NOM_SEUIL} = 6\n", f"{NOM_SEUIL} = 2 + 3\n",
                       f"{NOM_SEUIL} = True\n", f"{NOM_SEUIL} = 0\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                lire_seuil(source)

    def test_les_controles_negatifs_de_w26_et_w25_mordent(self) -> None:
        conforme = (
            "**ROUTES axis — x tasks.py direct y; the ROUTES axis bounds w. **ENTRY POINTS axis\n"
            "No execution without a GO — tasks.py direct z\nMax 8 round trips"
        )
        self.assertEqual(violations_orchestrateur("t", conforme), [])
        sans_axe = conforme.replace("ROUTES axis — x tasks.py direct", "ROUTES axis — x", 1)
        self.assertTrue(violations_orchestrateur("t", sans_axe))
        sans_regle = conforme.replace("GO — tasks.py direct z", "GO — z", 1)
        self.assertTrue(violations_orchestrateur("t", sans_regle))
        self.assertTrue(violations_orchestrateur("t", conforme.replace("**ROUTES axis", "**Axis", 1)))
        double = conforme + "\n" + ANCRE_ROUTES_TEXTE
        self.assertTrue(violations_orchestrateur("t", double), "une ancre ambiguë doit échouer")
        # Force de la re-épingle (T-01M5S9338BJP1B5RM3TG14AMYT) : le seul renvoi « the ROUTES axis »
        # n'est pas un titre ; les ancres françaises d'avant ne satisfont plus.
        self.assertTrue(violations_orchestrateur("t", conforme.replace("**ROUTES axis", "**Paragraph", 1)))
        francais = (conforme.replace("**ROUTES axis", "Axe des ROUTES", 1)
                    .replace("the ROUTES axis", "l'axe", 1)
                    .replace("**ENTRY POINTS axis", "Axe des POINTS D'ENTRÉE", 1)
                    .replace("Max 8 round trips", "Max 8 allers-retours", 1))
        self.assertTrue(violations_orchestrateur("t", francais), "la forme française d'avant passe encore")
        regle_fr = conforme.replace("Max 8 round trips", "Max 8 allers-retours", 1)
        self.assertTrue(violations_orchestrateur("t", regle_fr), "la fin de règle française passe encore")
        self.assertEqual(violations_graine("g", "# `tasks.py direct <id>` démarre"), [])
        self.assertTrue(violations_graine("g", "# Désarmer = retirer ce fichier"))


# ---------------------------------------------------------------------------
# W24 — les surfaces du kit
# ---------------------------------------------------------------------------
class SeuilDirectSurfacesTests(unittest.TestCase):
    """W24 : chaque phrase qui répète le seuil dit celui du code."""

    def setUp(self) -> None:
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("SKIP W24 : `.agents/IS_THE_KIT` absent (adoptant) — les surfaces lues sont celles du kit")

    def _seuil(self) -> int:
        source = ROOT / SOURCE_SEUIL
        self.assertTrue(
            source.is_file(),
            f"{SOURCE_SEUIL} absent : le shard A de T-00001178 n'est pas fusionné — ce banc est "
            "rouge par construction dans le worktree du shard C seul (ordre de fusion A, B, C)",
        )
        return lire_seuil(source.read_text(encoding="utf-8"))

    def _texte(self, rel: str) -> str:
        chemin = ROOT / rel
        self.assertTrue(chemin.is_file(), f"{rel} : surface absente — la liste fermée nomme un fichier disparu")
        return chemin.read_text(encoding="utf-8")

    def test_w24_la_liste_est_fermee_et_au_dessus_du_plancher(self) -> None:
        self.assertGreaterEqual(len(SURFACES_SEUIL), PLANCHER_SURFACES)
        self.assertEqual(len(set(SURFACES_SEUIL)), len(SURFACES_SEUIL), "surface listée deux fois")
        self.assertFalse(set(SURFACES_SEUIL) & set(SURFACES_VEILLE), "une surface est dans les deux listes")

    def test_w24_chaque_surface_dit_le_seuil_du_code(self) -> None:
        seuil = self._seuil()
        fautes, porteuses = [], 0
        for rel in SURFACES_SEUIL:
            texte = self._texte(rel)
            if not captures(texte):
                fautes.append(f"{rel} : AUCUNE répétition du seuil vue (phrase retirée, ou hors de la famille)")
                continue
            porteuses += 1
            mauvaises = violations(texte, seuil)
            if mauvaises:
                fautes.append(_decrire(rel, mauvaises))
        self.assertEqual(fautes, [], f"seuil du code {NOM_SEUIL} = {seuil} (plan dès {seuil + 1}) :\n" + "\n".join(fautes))
        self.assertGreaterEqual(porteuses, PLANCHER_SURFACES, "plancher de non-vacuité")

    def test_w24_les_surfaces_de_veille_ne_disent_pas_un_autre_seuil(self) -> None:
        seuil = self._seuil()
        fautes = []
        for rel in SURFACES_VEILLE:
            chemin = ROOT / rel
            if chemin.is_file():
                mauvaises = violations(chemin.read_text(encoding="utf-8"), seuil)
                if mauvaises:
                    fautes.append(_decrire(rel, mauvaises))
        self.assertEqual(fautes, [], "\n".join(fautes))

    def test_w24_mutant_une_surface_a_4(self) -> None:
        """Mutant « une surface à 4 » : le premier nombre capturé de chaque
        surface conforme est remplacé par 4, et la règle doit rougir."""
        seuil = self._seuil()
        mutees = 0
        for rel in SURFACES_SEUIL:
            texte = self._texte(rel)
            if not captures(texte) or violations(texte, seuil):
                continue  # non conforme : déjà rouge au test ci-dessus
            mutant = muter_premiere_capture(texte, "4")
            self.assertNotEqual(mutant, texte, f"{rel} : le mutant n'a rien changé — il ne mesure rien")
            self.assertTrue(violations(mutant, seuil), f"{rel} : LA RÈGLE NE MORD PAS sur une surface à 4")
            mutees += 1
        self.assertGreaterEqual(mutees, PLANCHER_SURFACES, "trop peu de surfaces conformes pour muter")


# ---------------------------------------------------------------------------
# W25 — les graines (geste pilote)
# ---------------------------------------------------------------------------
class GrainesDirectTests(unittest.TestCase):
    """W25 : les graines d'adoptant nomment la voie directe — ROUGE avant le geste pilote."""

    def setUp(self) -> None:
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("SKIP W25 : `.agents/IS_THE_KIT` absent (adoptant) — les graines sont une surface du kit")

    def test_w25_chaque_graine_nomme_la_voie_directe(self) -> None:
        dossier = ROOT / ".agents" / "adopter-seed" / "gates"
        if not dossier.is_dir():
            self.skipTest("SKIP W25 : `.agents/adopter-seed/gates/` absent — aucune graine à lire")
        fautes = []
        for nom in GRAINES:
            graine = dossier / nom
            self.assertTrue(graine.is_file(), f"graine {nom} absente de {dossier}")
            fautes += violations_graine(nom, graine.read_text(encoding="utf-8"))
        self.assertEqual(
            fautes, [],
            "geste pilote de l'étape 8 de T-00001178 non fait (chemins protégés) : " + " ; ".join(fautes),
        )


# ---------------------------------------------------------------------------
# W26 — les cinq orchestrateurs
# ---------------------------------------------------------------------------
class OrchestrateursDirectTests(unittest.TestCase):
    """W26 : l'axe des routes et la règle (1) nomment la voie directe, sur les cinq hôtes."""

    def setUp(self) -> None:
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("SKIP W26 : `.agents/IS_THE_KIT` absent (adoptant) — les défs lues sont celles du kit")

    def _textes(self) -> dict[str, str]:
        self.assertEqual(len(ORCHESTRATEURS), 5, "ce banc revendique cinq hôtes")
        textes = {}
        for hote, rel in ORCHESTRATEURS.items():
            chemin = ROOT / rel
            self.assertTrue(chemin.is_file(), f"{hote} : {rel} absent")
            textes[hote] = chemin.read_text(encoding="utf-8")
        return textes

    def test_w26_axe_des_routes_et_regle_1_nomment_la_voie_directe(self) -> None:
        fautes = [f for hote, texte in self._textes().items() for f in violations_orchestrateur(hote, texte)]
        self.assertEqual(fautes, [], "\n".join(fautes))

    def test_w26_mutant_route_directe_absente_d_un_hote(self) -> None:
        for hote, texte in self._textes().items():
            routes = tranche(texte, ANCRE_ROUTES, ANCRE_ROUTES_FIN)
            self.assertIsNotNone(routes, f"{hote} : base non verte")
            mutant = texte.replace(routes, routes.replace(VERBE, "tasks.py retire"), 1)
            self.assertNotEqual(mutant, texte, f"{hote} : le mutant n'a rien changé")
            self.assertTrue(violations_orchestrateur(hote, mutant), f"{hote} : LA RÈGLE NE MORD PAS sur l'axe")

    def test_w26_mutant_regle_1_sans_exception(self) -> None:
        for hote, texte in self._textes().items():
            regle = tranche(texte, ANCRE_REGLE_1, ANCRE_REGLE_1_FIN)
            self.assertIsNotNone(regle, f"{hote} : base non verte")
            mutant = texte.replace(regle, regle.replace(VERBE, "tasks.py retire"), 1)
            self.assertNotEqual(mutant, texte, f"{hote} : le mutant n'a rien changé")
            self.assertTrue(violations_orchestrateur(hote, mutant), f"{hote} : LA RÈGLE NE MORD PAS sur la règle (1)")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
