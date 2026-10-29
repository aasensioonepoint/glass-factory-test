"""La ligne `## Tests` d'un lot porte `BANCS:` (T-01M576S8956DA9FMXY384P7EYF, lot P).

CE QU'IL JUGE. Les deux surfaces de planification (`.claude/commands/planning.md`, et son
pendant Codex/Copilot `.agents/skills/planning/SKILL.md`) portent la regle de l'annexe § 4(c) et
§ 6, UNE fois chacune, identique a l'octet, sous l'etape 2 : la forme
`- <lot> — témoin neuf <chemin> ; BANCS: <items>` ; le mandat recopie les ITEMS qui suivent
`BANCS: `, jamais la ligne entiere (C19 : `^BANCS:` est ancre, la ligne du plan ouvre par `- `) ;
un banc existant qu'un critere lance est parmi les items, le temoin neuf passe par `PROOFS:` (C27) ;
une seule ligne, une ligne dans un bloc ``` ne compte pas. Dans la commande, la regle est un
paragraphe INDENTE du point 6 : un paragraphe nu terminerait la liste numerotee.
Le fait que la regle affirme est rejoue : de la forme qu'elle prescrit, la ligne recopiee en entier
n'est pas une ligne `BANCS:` ; les items recopies le sont.
CHAQUE ATOME A SON MUTANT, joue EN MEMOIRE : l'atome retire, la regle retiree de la skill,
doublee, divergente, sortie de l'etape 2, desindentee dans la commande — chacun rougit.
CHEZ L'ADOPTANT CE BANC JUGE (aucun saut) : les deux surfaces voyagent (`.template-exclude` ne les
cite pas).
LE PRODUCTEUR ET LE JUGE (C2). Le gabarit `## Tests` des cinq planners porte la ligne de lot,
et la grille des cinq plan-critic en controle la forme ; chacun a son mutant.
CE QU'IL NE PROUVE PAS. Qu'un plan reel respecte la forme : aucun code ne la verifie, seul
`plan-critic` la controle en prose (une reserve) ; ni que « THE BENCH LIST » existe dans kickoff
(lot K) ; le hook `bancs-mandat` (lot A) lit le mandat, jamais le plan.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMANDE = ".claude/commands/planning.md"
SKILL = ".agents/skills/planning/SKILL.md"
FORME = "- <lot> — témoin neuf <chemin> ; BANCS: <chemin exact>[::<test>], …"
ATOMES = (
    "**La ligne `## Tests` d'un lot (T-01M576S8956DA9FMXY384P7EYF).**",
    f"Sous `## Tests`, une ligne par lot, de la forme `{FORME}`",
    "bancs EXISTANTS seulement, sans glob, sans répertoire, sans mot",
    "Le mandat du dev et de ses juges porte, en tête de ligne, `BANCS: ` puis les items qui le suivent "
    "sur cette ligne, recopiés tels quels jusqu'à la fin de ligne",
    "(« THE BENCH LIST », `.agents/skills/kickoff/SKILL.md`)",
    "jamais la ligne entière, dont le `- <lot> — ` cacherait la liste au hook (`sans-liste`)",
    "jamais une formule ouverte",
    "Un banc qu'un critère d'acceptation lance est parmi ces items s'il existe déjà",
    "le témoin neuf du lot, et un critère qui le lance, passent par `PROOFS:`, jamais par `BANCS:`",
    "Une seule ligne `BANCS:`, jamais recopiée d'un autre rapport",
    "une ligne dans un bloc ``` ne compte pas.",
)
REGLE = (f"{ATOMES[0]} {ATOMES[1]} : {ATOMES[2]}. {ATOMES[3]} {ATOMES[4]} — {ATOMES[5]}, {ATOMES[6]}. "
         f"{ATOMES[7]} ; {ATOMES[8]}. {ATOMES[9]} ; {ATOMES[10]}")
# (section, debut, fin) : la regle tombe entre debut et fin, sous la section.
BORNES = {
    COMMANDE: ("6. **Étape 2**", "6. **Étape 2**", "\n7. "),
    SKILL: ("## Étape 2 ", "**Découpe PAR DÉFAUT**", "\n## "),
}
LIGNE_BANCS = re.compile(r"(?m)^BANCS: (.+)$")


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def verifier(texte: str, rel: str) -> list[str]:
    """Constats sur une surface ; liste vide = regle tenue."""
    for atome in ATOMES:
        if atome not in texte:
            return [f"atome absent : {atome}"]
    if texte.count(REGLE) != 1:
        return [f"regle x{texte.count(REGLE)}"]
    section, debut, fin = BORNES[rel]
    s = texte.find(section)
    d = texte.find(debut, s) if s >= 0 else -1
    p = texte.find(REGLE)
    f = texte.find(fin, p) if p >= 0 else -1
    if not (0 <= s <= d < p < f):
        return [f"regle hors de l'etape 2 : section {s}, debut {d}, regle {p}, fin {f}"]
    if rel == COMMANDE and not texte[:p].endswith("\n   "):
        return ["regle hors du point 6 (paragraphe non indente)"]
    return []


def items_recopies(ligne_du_plan: str) -> str:
    """Ce que la regle prescrit de recopier : `BANCS: ` puis les items qui le suivent, jusqu'a la fin de ligne."""
    return "BANCS: " + ligne_du_plan.split("BANCS: ", 1)[1]


TEXTES = {rel: lire(rel) for rel in (COMMANDE, SKILL)}


@pytest.mark.parametrize("rel", sorted(TEXTES))
def test_la_regle_est_tenue_sous_l_etape_2(rel):
    assert verifier(TEXTES[rel], rel) == [], rel


def test_la_regle_est_identique_sur_les_deux_surfaces():
    assert [rel for rel, t in TEXTES.items() if REGLE not in t] == []


def test_la_ligne_entiere_est_invisible_les_items_recopies_ne_le_sont_pas():
    """C19 rejoue sur la forme que la regle prescrit : sa raison (`sans-liste`) est un fait, pas une opinion."""
    ligne = "- Q — témoin neuf .agents/evals/test_x.py ; BANCS: .agents/evals/test_a.py, core-scripts/b.test.sh"
    assert ligne.startswith(FORME.split("<lot>")[0]) and " ; BANCS: " in FORME
    assert LIGNE_BANCS.findall(ligne) == []
    assert LIGNE_BANCS.findall(items_recopies(ligne)) == [".agents/evals/test_a.py, core-scripts/b.test.sh"]
    assert "test_x.py" not in items_recopies(ligne), "le temoin neuf ne passe jamais par BANCS:"


@pytest.mark.parametrize("atome", ATOMES)
@pytest.mark.parametrize("rel", sorted(TEXTES))
def test_mutant_atome_retire_rougit(rel, atome):
    assert verifier(TEXTES[rel].replace(atome, "", 1), rel), (rel, atome)


@pytest.mark.parametrize("rel", sorted(TEXTES))
def test_mutants_de_forme_rougissent(rel):
    texte = TEXTES[rel]
    section, debut, fin = BORNES[rel]
    sans = texte.replace(REGLE, "", 1)
    mutants = {
        "regle retiree": sans,
        "regle doublee": texte + "\n" + REGLE + "\n",
        "regle divergente": texte.replace("s'il existe déjà ;", "s'il existe ;", 1),
        "regle avant l'etape 2": REGLE + "\n" + sans,
        "regle apres l'etape 2": sans + "\n" + REGLE + "\n",
    }
    if rel == COMMANDE:
        mutants["paragraphe desindente"] = texte.replace("\n   " + REGLE, "\n" + REGLE, 1)
    for nom, mutant in mutants.items():
        assert verifier(mutant, rel), (rel, nom)


# --- Le producteur et le juge du plan (C2) -------------------------------------------------------
# Le gabarit `## Tests` des cinq planners porte la ligne de lot ; la grille des cinq plan-critic
# en contrôle la forme (une réserve). Valeurs ÉCRITES ICI (L-00000261).
HOTES = ((".claude/agents", ".md"), (".codex/agents", ".toml"), (".gemini/agents", ".md"),
         (".github/agents", ".agent.md"), (".kimi-code/agents", ".md"))
GABARIT = "témoin neuf <chemin> ; BANCS: <chemin exact>[::<test>], … | aucun | <pourquoi>"
ANCIEN_GABARIT = "- Add/modify: <test file>::<case>"
# Les plan-critic sont en anglais depuis T-01M5S9338BJP1B5RM3TG14AMYT : la grille est épinglée dans sa
# forme anglaise, entière ; la française d'avant ne la satisfait plus (témoin dédié ci-dessous). Le
# gabarit des planners reste en français : c'est une ligne de grammaire de plan, recopiée telle quelle.
GRILLE = ("Test form (T-01M576S8956DA9FMXY384P7EYF): every `LOT:` has under `## Tests` its line that "
          "ends with `BANCS:` (EXISTING benches, form of `planning/SKILL.md`); absent, it is a concern, "
          "never a NO_GO.")
GRILLE_FR = ("Forme des tests (T-01M576S8956DA9FMXY384P7EYF) : chaque `LOT:` a sous `## Tests` sa ligne qui "
             "finit par `BANCS:` (bancs EXISTANTS, forme de `planning/SKILL.md`) ; absente, c'est une réserve, "
             "jamais un NO_GO.")
PLANNERS = tuple(f"{d}/planner{e}" for d, e in HOTES)
CRITIQUES = tuple(f"{d}/plan-critic{e}" for d, e in HOTES)


def fautes_producteur_juge(textes: dict[str, str]) -> list[str]:
    f = [f"{rel} : gabarit de lot absent ou doublé" for rel in PLANNERS if textes[rel].count(GABARIT) != 1]
    f += [f"{rel} : ancien gabarit `Add/modify` revenu" for rel in PLANNERS if ANCIEN_GABARIT in textes[rel]]
    f += [f"{rel} : contrôle de forme absent ou doublé" for rel in CRITIQUES if textes[rel].count(GRILLE) != 1]
    return f


def _producteur_juge() -> dict[str, str]:
    return {rel: lire(rel) for rel in PLANNERS + CRITIQUES}


def test_planners_et_plan_critics_portent_la_forme():
    assert fautes_producteur_juge(_producteur_juge()) == []


@pytest.mark.parametrize("rel", PLANNERS + CRITIQUES)
def test_mutant_producteur_juge_rougit(rel):
    textes = _producteur_juge()
    vieux = GABARIT if rel in PLANNERS else GRILLE
    mutant = {**textes, rel: textes[rel].replace(vieux, "", 1)}
    assert mutant != textes, f"mutant sans effet : {rel}"
    assert fautes_producteur_juge(mutant), f"mutant SURVIVANT : {rel}"


@pytest.mark.parametrize("rel", CRITIQUES)
def test_mutant_grille_francaise_d_avant_rougit(rel):
    textes = _producteur_juge()
    mutant = {**textes, rel: textes[rel].replace(GRILLE, GRILLE_FR, 1)}
    assert mutant != textes, f"mutant sans effet : {rel}"
    assert fautes_producteur_juge(mutant), f"la grille française d'avant passe encore : {rel}"
