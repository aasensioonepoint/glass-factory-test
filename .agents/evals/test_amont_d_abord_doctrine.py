"""L'amont d'abord est écrit sur chaque surface qui voyage (T-01M4Z5VJ1DYQZM67AYHTACKFTA).

Décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T : `depends_on` ordonne ET garde. Le CODE la tient
(`tasks.py deps-ready`, refus au `start` et à la `fournee`, `.agents/bin/test_tasks_amont.py`) ;
ce banc tient sa PROSE : chaque surface nommée par le plan (étape 8) porte le verbe et ses jetons
de 1re ligne. Jetons et surfaces vivent dans `doctrine_registre.py`, règle `REGLE` ci-dessous,
et nulle part ici : `test_doctrine_registre.py` (4d) refuse un jeton recopié en constante. Les
MEMBRES des surfaces sont épinglés ici ; la LISTE des jetons est épinglée à la constante du code
`DEPS_READY_JETONS` (`.agents/bin/tasks_graphe.py`, lue par AST, jamais importée) : hors le
verbe, une liste de groupe qui diverge de la constante — jeton en plus, en moins, ordre de
précédence changé — rougit. Seul un jeton de la constante plus court que `LONGUEUR_MIN` (4f)
n'est pas exigé, et il doit alors être NOMMÉ dans la `limite` de la règle.

ÉTAT ATTENDU. Mesuré à develop @ 1afdc046 : 0 occurrence des jetons sur les 16 surfaces, et ni la
constante ni le verbe dans le code. Ce banc est donc ROUGE sur la branche du lot D seule — il
juge la constante du lot A et les surfaces des lots B, C et E — et VERT sur l'arbre intégré :
le plan fusionne A, puis B, C et E, puis D en dernier, si bien que develop ne voit jamais son
rouge.

LE SENS (exec-critic des lots B-E, angle mort M12 : « AMONT_OUVERT → continue » restait vert).
Sur chaque surface, le jeton `sens.arret` du registre est suivi au moins une fois, dans sa
PROPOSITION (jusqu'au jeton suivant, à un `;` ou à une fin de phrase), d'un geste d'arrêt ; aucun
jeton de rc 1 (la constante du code moins `DEPS_READY_PASSANTS`) n'est suivi de « continue ». Les
blocs JUMEAUX — kickoff 3-amont (skill et commande, texte identique), night gate et night tour
(skill et commande) — branchent pareil : même suite (jeton, classe de geste).

CE QU'IL NE VOIT PAS : le sens n'est lu que par LEXIQUE — ni le comportement des lanceurs, ni
l'ordre de précédence écrit, ni une négation (« jamais un STOP » passe pour un geste), ni une
dépendance non déclarée ; la `limite` de la règle le dit. ZÉRO appel LLM, aucune énumération de
l'arbre.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402

REGLE = "amont-d-abord"
#: La constante du code à laquelle la liste des jetons est épinglée, et le CLI qui déclare le verbe.
CODE = ".agents/bin/tasks_graphe.py"
CONSTANTE = "DEPS_READY_JETONS"
CLI = ".agents/bin/tasks_cli.py"

#: Les 16 surfaces de l'étape 8 du plan, par groupe — ÉPINGLÉES (un compte laisserait
#: substituer une surface à taille égale) ; le roster généré n'en est pas.
ATTENDU = {
    "routeur": (
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".agents/skills/task-board/SKILL.md",
    ),
    "lanceurs": (
        ".agents/skills/kickoff/SKILL.md",
        ".claude/commands/kickoff.md",
        ".agents/skills/planning/SKILL.md",
        ".claude/commands/planning.md",
        ".agents/skills/planning-all/SKILL.md",
        ".claude/commands/planning-all.md",
        ".agents/skills/night/SKILL.md",
        ".claude/commands/night.md",
    ),
    "orchestrateur": (
        ".claude/agents/orchestrator.md",
        ".codex/agents/orchestrator.toml",
        ".gemini/agents/orchestrator.md",
        ".kimi-code/agents/orchestrator.md",
        ".github/agents/orchestrator.agent.md",
    ),
}
GROUPES = tuple(R.regle(REGLE)["groupes"])

#: LE SENS — instruments de mesure, jamais des jetons (4d) : le jeton jugé vient du registre
#: (`sens`), les jetons de rc 1 de la constante du code moins celle des passants.
PASSANTS = "DEPS_READY_PASSANTS"
FENETRE_MAX = 300
FIN_DE_PROPOSITION = re.compile(r";|\.\s")
ARRET = re.compile(r"\b(?:stop|sort|sortent|refus\w*|report\w*)\b", re.I)
CONTINUE = re.compile(r"\bcontinue\b", re.I)
#: Classes de geste de la signature d'un bloc jumeau (une proposition peut en porter plusieurs).
GESTES = (
    ("arret", re.compile(r"\b(?:stop|sort|sortent|refus\w*|report\w*|saute\w*)\b", re.I)),
    ("start", re.compile(r"\bstart\b", re.I)),
    ("entre", re.compile(r"\bentre(?:nt)?\b", re.I)),
    ("revision", re.compile(r"\brévis\w*", re.I)),
    ("continue", CONTINUE),
)
#: Les blocs JUMEAUX : (nom, skill, commande, début, fin, texte identique exigé).
JUMEAUX = (
    ("kickoff 3-amont", ".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md",
     "3-amont. **L'amont d'abord", "« SIXIÈME GARDE ».", True),
    ("night gate", ".agents/skills/night/SKILL.md", ".claude/commands/night.md",
     "**L'amont se RELÈVE par `deps-ready`", "La nuit ne passe JAMAIS", False),
    ("night tour", ".agents/skills/night/SKILL.md", ".claude/commands/night.md",
     "**Puis, au même tour et AVANT le `start`, rejoue `deps-ready`**",
     "refuse de toute façon un amont ouvert", False),
)


def _fautes(textes: dict[str, str], groupe: str) -> list[str]:
    """`<surface> : <jetons manquants>` pour chaque texte du groupe qui ne porte pas la règle."""
    attendus = R.jetons(REGLE, groupe)
    return [f"{rel} : {m}" for rel, t in textes.items() if (m := R.manquants(t, attendus))]


def _textes(groupe: str) -> dict[str, str]:
    return {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in R.chemins(REGLE, groupe)}


def _constante_du_code(source: str) -> tuple[str, ...] | None:
    """La valeur de `CONSTANTE` affectée au niveau module de `source`, sinon None."""
    for n in ast.parse(source).body:
        if isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id == CONSTANTE for c in n.targets):
            return tuple(ast.literal_eval(n.value))
    return None


def _ecarts(jetons: tuple[str, ...], constante: tuple[str, ...]) -> list[str]:
    """Les écarts d'une liste de groupe à la constante : ses jetons PRIS dans la constante sont
    exactement ceux de la constante assez longs pour 4f, dans son ordre ; hors constante, il ne
    reste qu'un jeton, le verbe."""
    exiges = tuple(j for j in constante if len(j) >= R.LONGUEUR_MIN)
    pris = tuple(j for j in jetons if j in constante)
    hors = [j for j in jetons if j not in constante]
    fautes = []
    if pris != exiges:
        fautes.append(f"jetons {pris} != constante {exiges}")
    if len(hors) != 1:
        fautes.append(f"hors constante {hors} : seul le verbe y a sa place")
    return fautes


def _passants_du_code(source: str) -> frozenset[str] | None:
    """La valeur de `PASSANTS` (`frozenset({...})` ou littéral) au niveau module, sinon None."""
    for n in ast.parse(source).body:
        if isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id == PASSANTS for c in n.targets):
            v = n.value
            return frozenset(ast.literal_eval(v.args[0] if isinstance(v, ast.Call) and v.args else v))
    return None


def _suites(texte: str, jetons: tuple[str, ...]) -> list[tuple[str, str]]:
    """`(jeton, proposition)` pour chaque occurrence d'un jeton, dans l'ordre du texte aplati : la
    proposition court jusqu'au jeton suivant, à un `;` ou à une fin de phrase, ≤ FENETRE_MAX."""
    plat = " ".join(texte.split())
    motif = re.compile(r"\b(?:" + "|".join(map(re.escape, jetons)) + r")\b")
    out = []
    for m in motif.finditer(plat):
        reste = plat[m.end(): m.end() + FENETRE_MAX]
        coupes = [x.start() for x in (motif.search(reste), FIN_DE_PROPOSITION.search(reste)) if x]
        out.append((m.group(0), reste[: min(coupes, default=len(reste))]))
    return out


def _fautes_de_sens(textes: dict[str, str], arret: str, rc1: tuple[str, ...],
                    jetons: tuple[str, ...]) -> list[str]:
    """`<surface> : <faute>` — `arret` jamais suivi d'un geste d'arrêt, ou un jeton de rc 1 suivi
    de « continue »."""
    fautes = []
    for rel, t in textes.items():
        suites = _suites(t, jetons)
        if not any(ARRET.search(p) for j, p in suites if j == arret):
            fautes.append(f"{rel} : {arret} n'est jamais suivi d'un STOP, d'un refus ou d'une sortie")
        fautes += [f"{rel} : {j} suivi de « continue » ({p.strip()[:80]!r})"
                   for j, p in suites if j in rc1 and CONTINUE.search(p)]
    return fautes


def _bloc(texte: str, debut: str, fin: str) -> str:
    """Le bloc aplati de `debut` à `fin` inclus ; vide si l'un des deux manque."""
    plat = " ".join(texte.split())
    i = plat.find(debut)
    j = plat.find(fin, i) if i >= 0 else -1
    return plat[i: j + len(fin)] if i >= 0 and j >= 0 else ""


def _signature(bloc: str, jetons: tuple[str, ...]) -> list[tuple[str, tuple[str, ...]]]:
    """La suite `(jeton, classes de geste de sa proposition)` d'un bloc : ce que la branche FAIT."""
    return [(j, tuple(n for n, rx in GESTES if rx.search(p))) for j, p in _suites(bloc, jetons)]


def _fautes_jumeaux(a: str, b: str, jetons: tuple[str, ...], identique: bool) -> list[str]:
    """Les écarts de deux blocs jumeaux : bloc vide ou privé d'un jeton, signature ou texte divergents."""
    fautes = [f"bloc {c} vide ou privé de {[j for j in jetons if j not in {s[0] for s in _signature(x, jetons)}]}"
              for c, x in (("skill", a), ("commande", b))
              if not x or {s[0] for s in _signature(x, jetons)} != set(jetons)]
    if _signature(a, jetons) != _signature(b, jetons):
        fautes.append(f"signatures divergentes : {_signature(a, jetons)} != {_signature(b, jetons)}")
    if identique and a != b:
        fautes.append("texte divergent entre les jumeaux")
    return fautes


class AmontDAbordDoctrineTests(unittest.TestCase):
    maxDiff = None  # le rouge nomme CHAQUE surface et ses jetons manquants, jamais tronqué

    def test_chaque_surface_porte_la_regle(self) -> None:
        """← un lot B, C, D ou E qui n'écrit pas le verbe ou un jeton sur sa surface."""
        fautes = [f for g in GROUPES for f in _fautes(_textes(g), g)]
        self.assertEqual(fautes, [], "surfaces sans la règle de l'amont d'abord")

    def test_la_liste_des_jetons_est_epinglee_a_la_constante_du_code(self) -> None:
        """← un jeton ajouté, retiré ou réordonné dans `DEPS_READY_JETONS` sans le registre (ou
        l'inverse) ; ← un jeton court non exigé que la `limite` ne nomme pas ; ← verbe renommé."""
        constante = _constante_du_code((ROOT / CODE).read_text(encoding="utf-8"))
        self.assertIsNotNone(constante, f"{CONSTANTE} absente de {CODE} (lot A non fusionné ?)")
        for g in GROUPES:
            self.assertEqual(_ecarts(R.jetons(REGLE, g), constante), [], f"groupe {g}")
        limite = R.regle(REGLE)["limite"]
        for j in constante:
            if len(j) < R.LONGUEUR_MIN:
                self.assertIn(j, limite, f"{j!r} n'est pas exigé et la limite ne le nomme pas")
        cli = (ROOT / CLI).read_text(encoding="utf-8")
        verbes = {j for g in GROUPES for j in R.jetons(REGLE, g) if j not in constante}
        self.assertEqual(len(verbes), 1, verbes)
        self.assertIn(f'add_parser("{verbes.pop()}"', cli, f"le verbe n'est pas un sous-verbe de {CLI}")

    def test_controle_negatif_membres_et_plancher(self) -> None:
        """L-00000232 : un balayage qui perd une surface ou un jeton passe à vide."""
        self.assertEqual(
            {g: R.chemins(REGLE, g) for g in GROUPES}, ATTENDU,
            "les surfaces de la règle ont changé au registre",
        )
        toutes = [s for g in GROUPES for s in R.chemins(REGLE, g)]
        self.assertEqual(len(toutes), 16)
        self.assertEqual(len(set(toutes)), 16, "une surface dans deux groupes")
        for g in GROUPES:
            self.assertGreaterEqual(len(R.jetons(REGLE, g)), 6, f"{g} a perdu un jeton")
        self.assertIn(".agents/evals/test_amont_d_abord_doctrine.py", R.regle(REGLE)["bancs"])

    def test_temoin_le_filet_rougit_sur_une_surface_privee_de_la_regle(self) -> None:
        """Témoin synthétique, indépendant de l'arbre : une surface qui porte tous les jetons
        passe ; privée d'UN jeton, elle rougit en nommant CE jeton ; vidée, elle rougit sur tous."""
        for g in GROUPES:
            attendus = R.jetons(REGLE, g)
            plein = " ".join(attendus)
            self.assertEqual(_fautes({"porte.md": plein}, g), [])
            for j in attendus:
                self.assertEqual(
                    _fautes({"porte.md": plein, "privee.md": plein.replace(j, "")}, g),
                    [f"privee.md : {[j]}"],
                )
            self.assertEqual(_fautes({"vide.md": ""}, g), [f"vide.md : {list(attendus)}"])

    def test_temoin_l_epinglage_rougit_sur_chaque_divergence(self) -> None:
        """Témoin synthétique, indépendant du lot A : une constante bâtie sur le registre (verbe
        en tête par convention, plus un jeton COURT exempté) passe ; chaque divergence rougit."""
        toks = R.jetons(REGLE, GROUPES[0])
        c = ("COURT",) + toks[1:]
        self.assertEqual(_ecarts(toks, c), [])
        self.assertEqual(_constante_du_code(f"{CONSTANTE} = {c!r}\n"), c)
        self.assertIsNone(_constante_du_code(f"AUTRE = {c!r}\n"))
        divergences = {
            "jeton ajouté au code": c + ("JETON_NEUF",),
            "jeton retiré du code": tuple(x for x in c if x != toks[2]),
            "précédence inversée": c[:1] + tuple(reversed(c[1:])),
        }
        for cas, mutee in divergences.items():
            self.assertNotEqual(_ecarts(toks, mutee), [], cas)
        self.assertNotEqual(_ecarts(toks[:1] + toks[2:], c), [], "jeton retiré du registre")

    def _jetons_du_code(self) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        """`(constante, jetons de rc 1, jeton d'arrêt du registre)`, cohérents entre eux."""
        source = (ROOT / CODE).read_text(encoding="utf-8")
        constante, passants = _constante_du_code(source), _passants_du_code(source)
        self.assertIsNotNone(constante, f"{CONSTANTE} absente de {CODE}")
        self.assertTrue(passants and passants < set(constante), f"{PASSANTS} absente ou hors de {CONSTANTE}")
        rc1 = tuple(j for j in constante if j not in passants)
        arret = R.regle(REGLE)["sens"]["arret"]
        self.assertIn(arret, rc1, "le jeton d'arrêt du registre n'est pas un jeton de rc 1 du code")
        return constante, rc1, arret

    def test_le_sens_amont_ouvert_arrete_et_aucun_rc1_ne_continue(self) -> None:
        """← M12 : « AMONT_OUVERT → continue » (ou son STOP effacé) sur une surface ; ← un jeton de
        rc 1 suivi de « continue »."""
        constante, rc1, arret = self._jetons_du_code()
        textes = {rel: t for g in GROUPES for rel, t in _textes(g).items()}
        self.assertEqual(len(textes), 16)
        self.assertEqual(_fautes_de_sens(textes, arret, rc1, constante), [], "surfaces au sens faux")

    def test_les_blocs_jumeaux_kickoff_et_night_branchent_pareil(self) -> None:
        """← une branche changée d'un seul côté (skill ou commande) ; ← un bloc introuvable."""
        constante, _rc1, _arret = self._jetons_du_code()
        for nom, skill, commande, debut, fin, identique in JUMEAUX:
            a = _bloc((ROOT / skill).read_text(encoding="utf-8"), debut, fin)
            b = _bloc((ROOT / commande).read_text(encoding="utf-8"), debut, fin)
            self.assertEqual(_fautes_jumeaux(a, b, constante, identique), [], nom)

    def test_temoin_le_sens_rougit_sur_continue_et_sur_un_stop_efface(self) -> None:
        """Témoin synthétique : branches justes vertes ; « → continue » à la place du STOP rougit
        deux fois (geste absent, continue) ; un autre jeton de rc 1 suivi de continue rougit."""
        constante, rc1, arret = self._jetons_du_code()
        autre = next(j for j in rc1 if j != arret)
        juste = f"`{arret}` (rc 1) → STOP, rien n'est planifié. `{autre}` (rc 1) → STOP."
        self.assertEqual(_fautes_de_sens({"s.md": juste}, arret, rc1, constante), [])
        m12 = juste.replace("STOP, rien n'est planifié", "continue", 1)
        self.assertEqual(len(_fautes_de_sens({"s.md": m12}, arret, rc1, constante)), 2)
        self.assertEqual(len(_fautes_de_sens({"s.md": juste.replace("→ STOP.", "→ continue.")},
                                             arret, rc1, constante)), 1)

    def test_temoin_la_parite_rougit_sur_une_branche_divergente(self) -> None:
        """Témoin synthétique : deux jumeaux égaux passent ; une branche changée, un jeton perdu ou
        un texte divergent (exigé identique) rougissent."""
        constante, _rc1, arret = self._jetons_du_code()
        bloc = " ".join(f"`{j}` → STOP ;" for j in constante)
        self.assertEqual(_fautes_jumeaux(bloc, bloc, constante, True), [])
        self.assertNotEqual(_fautes_jumeaux(bloc, bloc.replace(f"`{arret}` → STOP", f"`{arret}` → continue"),
                                            constante, False), [])
        self.assertNotEqual(_fautes_jumeaux(bloc, bloc.replace(f"`{arret}` → STOP ;", ""), constante, False), [])
        self.assertNotEqual(_fautes_jumeaux(bloc, bloc + " mot ajouté", constante, True), [])
        self.assertNotEqual(_fautes_jumeaux("", "", constante, True), [])


if __name__ == "__main__":
    unittest.main()
