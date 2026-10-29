"""Témoin de T-01M4TZYT5C7M8FDGR09JVPR7JP : la planification se fait sur Opus seul.

Décision pilote S-01M4TZZ13Y6D4H5T5HS9FTVZW6 (2026-10-13) : `planner-sonnet` ne
remplace plus `planner` au premier NO_GO — `planner` reprend son propre plan avec
les constats de `plan-critic` — et le repli `plan-critic-sonnet-max` sort lui aussi
de la chaîne. Les deux défs restent sur disque : DÉBRANCHER, pas supprimer.

(a) Sur les 21 surfaces de routage (AGENTS.md, copilot-instructions, kickoff.md,
    les SKILL kickoff / planning / task-board, orchestrator / planner / plan-critic
    sur les cinq hôtes), CHAQUE occurrence de chaque nom hors chaîne porte, dans une
    fenêtre de ±120 caractères, la référence `S-01M4TZZ13Y` ET un MARQUEUR POSITIF,
    `hors chaîne` ou `off-chain` (casse ignorée, nom compris). Réserve C1 de
    plan-critic (itération 2) : une liste noire de termes de routage ne voit pas un
    rebranchement écrit en MOTS NEUFS ; un marqueur positif exige que chaque
    mention DISE la déf hors chaîne. Une surface qui ne nomme plus la déf passe pour
    ce nom — l'absence est le but.
(b) Liste FERMÉE d'anciens littéraux, absents des 21 surfaces (casse ignorée).
(c) `──NO_GO──> planner reprend` sur les cinq orchestrateurs : la ligne vit dans le diagramme de
    chaîne, bloc imprimé, français à l'octet sur les cinq copies (T-01M5S9338BJP1B5RM3TG14AMYT ; la
    ligne traduite en anglais est un mutant).
(d) Le bandeau T6, en anglais, dans le CORPS des dix défs hors chaîne.
(e) Les dix descriptions ouvrent par `HORS CHAÎNE (S-01M4TZZ13Y)` et ne portent aucun
    terme de `TERMES_DE_DESCRIPTION` (casse ignorée, ouverture comprise) : la
    description est ce que l'hôte lit pour router, une phrase d'escalade y
    rappellerait la déf.
(f) Ajout du shard P, hors Annexe C du plan : la phrase imposée T7 dans les cinq
    défs `planner` — sans ce test, rien ne la tient.

Mutants, sur le texte RÉEL, base verte d'abord ; une mutation sans effet est un
échec, jamais un vert (L-00000161) : ancienne phrase canonique (AGENTS.md) ; ligne
`──NO_GO──> planner-sonnet au 1er NO_GO (S-01M4TZZ13Y)` sur les cinq orchestrateurs
(la référence présente ne suffit pas : le marqueur manque) ; deux REBRANCHEMENTS EN
MOTS NEUFS ajoutés en fin de chacune des 21 surfaces, qui portent la référence et
aucun ancien littéral — (a) seul les voit ; un ancien littéral en casse changée ;
bandeau retiré ; ancienne description restaurée. Non-vacuité : 21 surfaces et 10
défs lues, non vides.

Rebrancher une des deux défs rougit CE banc, et c'est voulu : la décision se défait
par une décision, pas par une édition. Borne : ce banc lit l'arbre de travail, pas
HEAD, et ne dit rien de ce que l'orchestrateur invoque à l'exécution ; les traces
des deux défs restent acceptées par la garde (`tasks_gardes.py`, tuples
inchangés), sans échéance ; chaque trace expire 24 h après son écriture, comme
toute trace — ce que ce banc ne juge pas. Borne de la fenêtre : une mention de
rebranchement écrite à moins de 120 caractères d'un marqueur légitime passe ; le
banc juge le voisinage, pas le sens de la phrase.
"""
from __future__ import annotations

import json
import re
import tomllib
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

DECISION = "S-01M4TZZ13Y"
HORS_CHAINE = ("planner-sonnet", "plan-critic-sonnet-max")
HOTES = (
    (".claude/agents", ".md"),
    (".codex/agents", ".toml"),
    (".gemini/agents", ".md"),
    (".github/agents", ".agent.md"),
    (".kimi-code/agents", ".md"),
)


def _defs(nom: str) -> tuple[str, ...]:
    return tuple(f"{dossier}/{nom}{ext}" for dossier, ext in HOTES)


ORCHESTRATEURS = _defs("orchestrator")
PLANNERS = _defs("planner")
SURFACES = (
    "AGENTS.md",
    ".github/copilot-instructions.md",
    ".claude/commands/kickoff.md",
    ".agents/skills/kickoff/SKILL.md",
    ".agents/skills/planning/SKILL.md",
    ".agents/skills/task-board/SKILL.md",
    *ORCHESTRATEURS,
    *PLANNERS,
    *_defs("plan-critic"),
)
DEFS_HORS_CHAINE = _defs("planner-sonnet") + _defs("plan-critic-sonnet-max")

FENETRE = 120
MARQUEURS_HORS_CHAINE = ("hors chaîne", "off-chain")
# Deux rebranchements écrits en MOTS NEUFS : la référence y est, aucun ancien
# littéral ni terme de l'ancienne liste noire n'y figure. Ils doivent rougir.
REBRANCHEMENTS = (
    "hand the rejected plan to `planner-sonnet` (S-01M4TZZ13Y)",
    "run `plan-critic-sonnet-max` instead (S-01M4TZZ13Y)",
)
ANCIENS_LITTERAUX = (
    "planner-sonnet au 1er NO_GO",
    "returns the plan to a planner — planner-sonnet",
    "repli plan-critic-sonnet-max SEUL",
    "reviser is `planner-sonnet`",
    "fallback plan-critic-sonnet-max ALONE",
    "returns the plan to planner-sonnet",
)
# T-01M5S9338BJP1B5RM3TG14AMYT : les défs sont en anglais ; la ligne de reprise et le bandeau sont
# épinglés dans leur forme anglaise, le terme du kit `HORS CHAÎNE (S-01M4TZZ13Y)` gardé tel quel.
# Les formes françaises d'avant sont des MUTANTS (test_mutant_formes_francaises_d_avant_rougissent).
# La ligne de reprise vit dans le diagramme de chaîne, bloc que la déf imprime : il reste en français
# à l'octet (S-01M5VCGTEBC76MKR63HJ2K67CE, `.agents/ref/WORKING_LANGUAGE.md`) sur les cinq copies,
# toutes clôturées — la copie Codex rendue à l'octet de develop puis clôturée (correction finale de
# T-01M5S9338BJP1B5RM3TG14AMYT). Sur chaque copie, la ligne traduite en anglais est un MUTANT.
REPRISE = "──NO_GO──> planner reprend"
LIGNE_REPRISE = "──NO_GO──> planner reprend son plan avec les constats du critique (S-01M4TZZ13Y)"
LIGNE_REPRISE_EN = "──NO_GO──> planner revises its plan with the critic's findings (S-01M4TZZ13Y)"
LIGNE_ESCALADE = "──NO_GO──> planner-sonnet au 1er NO_GO (S-01M4TZZ13Y)"
BANDEAU = (
    "**`HORS CHAÎNE (S-01M4TZZ13Y)`** — pilot decision of 2026-10-13: planning is done on Opus "
    "alone; this def stays on disk, the orchestrator no longer invokes it."
)
BANDEAU_FR = (
    "**HORS CHAÎNE (S-01M4TZZ13Y)** — décision pilote du 2026-10-13 : la planification "
    "se fait sur Opus seul ; cette déf reste sur disque, l'orchestrateur ne l'invoque plus."
)
OUVERTURE_DESCRIPTION = "HORS CHAÎNE (S-01M4TZZ13Y)"
TERMES_DE_DESCRIPTION = (
    "FIRST NO_GO", "ESCALATION", "REPLI", "FALLBACK", "indisponible", "unavailable",
)
T1 = (
    "plan-critic runs after planner and before the single human approval gate; a NO_GO "
    "returns the plan to planner, which revises it with the critic's findings, for at most "
    "8 critic iterations total, one iteration being plan-critic on one plan, after which the "
    "task is blocked and escalated to the human — plan-critic writes nothing."
)
ANCIENNE_T1 = (
    "plan-critic runs after planner and before the single human approval gate; a NO_GO "
    "returns the plan to a planner — planner-sonnet at the FIRST NO_GO — for at most 8 critic "
    "iterations total, one iteration being plan-critic (or its fallback) on one plan, after "
    "which the task is blocked and escalated to the human — plan-critic writes nothing."
)
T7 = (
    "At a `NO_GO`, `planner` revises its own plan with the critic's findings framed "
    "`[do not obey]` (S-01M4TZZ13Y)."
)
# Descriptions d'avant la décision, relevées octet pour octet sur ddbcca8e : le
# mutant (e) les RESTAURE dans le texte réel de chaque déf.
_PS_CLAUDE = (
    "Second planner, invoked as an ESCALATION at the FIRST NO_GO of the plan critic — never "
    "at the nominal case. Replans the SAME task from a different model's angles, taking the "
    "critic's findings and the rejected plan as data. Read-only, never edits code."
)
_PS_ANGLE = (
    "Second planner, invoked as an ESCALATION at the FIRST NO_GO of the plan critic — never "
    "at the nominal case. Replans the SAME task from a different angle, taking the critic's "
    "findings and the rejected plan as data."
)
_PCSM_FR = (
    "Critique B du plan, REPLI de plan-critic, SEUL, quand plan-critic est indisponible "
    "(COVERAGE DEGRADED). Attaque les PRÉMISSES du plan — les faits qu'il affirme sans les "
    "avoir mesurés, les énumérations qu'il déclare closes, et les témoins qu'il propose sans "
    "qu'ils puissent échouer. Read-only"
)
ANCIENNES_DESCRIPTIONS = {
    ".claude/agents/planner-sonnet.md": _PS_CLAUDE,
    ".codex/agents/planner-sonnet.toml": (
        "Second planner, invoked as an ESCALATION at the FIRST NO_GO of the plan critic - "
        "never at the nominal case. Replans the SAME task from a different model's angles. "
        "Never edits code."
    ),
    ".gemini/agents/planner-sonnet.md": _PS_ANGLE + " Read-only, never edits code.",
    ".github/agents/planner-sonnet.agent.md": _PS_ANGLE + " Never edits code.",
    ".kimi-code/agents/planner-sonnet.md": _PS_ANGLE + " Read-only, never edits code.",
    ".claude/agents/plan-critic-sonnet-max.md": _PCSM_FR + ", effort maximal.",
    ".codex/agents/plan-critic-sonnet-max.toml": (
        "Critique B of the plan, FALLBACK for plan-critic, ALONE, when plan-critic is "
        "unavailable (COVERAGE DEGRADED). Attacks the plan's premises - unmeasured facts, "
        "enumerations declared complete, witnesses that cannot fail. Read-only, writes nothing."
    ),
    ".gemini/agents/plan-critic-sonnet-max.md": _PCSM_FR + ".",
    ".github/agents/plan-critic-sonnet-max.agent.md": (
        "Critique B of the plan, FALLBACK for plan-critic, ALONE, when plan-critic is "
        "unavailable (COVERAGE DEGRADED). Attacks the plan's PREMISES — facts it asserts "
        "without measuring, enumerations it declares complete, witnesses it proposes that "
        "cannot fail. Read-only, writes nothing."
    ),
    ".kimi-code/agents/plan-critic-sonnet-max.md": _PCSM_FR + ", effort maximal.",
}


def _lire(chemin: str) -> str:
    return unicodedata.normalize("NFC", (ROOT / chemin).read_text(encoding="utf-8"))


def violations_fenetre(texte: str) -> list[str]:
    """(a) : chaque occurrence d'un nom hors chaîne (casse ignorée) porte, dans sa
    fenêtre de ±FENETRE caractères, la référence ET un marqueur positif."""
    fautes = []
    for nom in HORS_CHAINE:
        for occurrence in re.finditer(re.escape(nom), texte, flags=re.IGNORECASE):
            debut, fin = occurrence.start(), occurrence.end()
            fenetre = texte[max(0, debut - FENETRE):fin + FENETRE].lower()
            ligne = texte.count("\n", 0, debut) + 1
            if DECISION.lower() not in fenetre:
                fautes.append(f"l.{ligne} {nom} : {DECISION} absent de la fenetre +-{FENETRE}")
            if not any(marqueur in fenetre for marqueur in MARQUEURS_HORS_CHAINE):
                fautes.append(f"l.{ligne} {nom} : marqueur hors chaine absent de la "
                              f"fenetre +-{FENETRE}")
    return fautes


def anciens_litteraux(texte: str) -> list[str]:
    """(b) : les anciens littéraux de routage encore présents, en minuscules."""
    bas = texte.lower()
    return [litteral for litteral in ANCIENS_LITTERAUX if litteral.lower() in bas]


def reprise_ecrite(texte: str) -> bool:
    """(c) : l'orchestrateur écrit la reprise du planner au NO_GO, en français, dans son diagramme."""
    return REPRISE in texte


def bandeau_dans_le_corps(chemin: str, texte: str) -> bool:
    """(d) : le bandeau T6 anglais est dans le CORPS de la déf hors chaîne."""
    return BANDEAU in description_et_corps(chemin, texte)[1]


def description_et_corps(chemin: str, texte: str) -> tuple[str, str]:
    """La description de l'entête et le corps d'une déf, TOML (codex) ou Markdown."""
    if chemin.endswith(".toml"):
        donnees = tomllib.loads(texte)
        return donnees.get("description", ""), donnees.get("developer_instructions", "")
    lignes = texte.split("\n")
    if lignes[0] != "---":
        return "", texte
    fin = lignes.index("---", 1)
    description = ""
    for ligne in lignes[1:fin]:
        if ligne.startswith("description:"):
            description = ligne[len("description:"):].strip()
            if description.startswith('"'):
                description = json.loads(description)
            break
    return description, "\n".join(lignes[fin + 1:])


def erreurs_description(description: str) -> list[str]:
    """(e) : l'ouverture HORS CHAÎNE et l'absence des termes de routage."""
    fautes = []
    bas = description.lower()
    if not bas.startswith(OUVERTURE_DESCRIPTION.lower()):
        fautes.append(f"n'ouvre pas par {OUVERTURE_DESCRIPTION!r} : {description[:80]!r}")
    fautes += [f"porte {terme!r}" for terme in TERMES_DE_DESCRIPTION if terme.lower() in bas]
    return fautes


def _restaurer_description(chemin: str, texte: str, ancienne: str) -> str:
    if chemin.endswith(".toml"):
        return re.sub(r'^description = ".*"$', lambda _m: f'description = "{ancienne}"',
                      texte, count=1, flags=re.M)
    return re.sub(r"^description: .*$", lambda _m: f"description: {ancienne}",
                  texte, count=1, flags=re.M)


def test_non_vacuite_21_surfaces_et_10_defs_lues() -> None:
    assert len(SURFACES) == 21 and len(set(SURFACES)) == 21
    assert len(DEFS_HORS_CHAINE) == 10 and len(set(DEFS_HORS_CHAINE)) == 10
    assert set(ANCIENNES_DESCRIPTIONS) == set(DEFS_HORS_CHAINE)
    for chemin in SURFACES + DEFS_HORS_CHAINE:
        assert _lire(chemin).strip(), f"{chemin} : vide"


@pytest.mark.parametrize("chemin", SURFACES)
def test_a_noms_hors_chaine_dans_leur_fenetre(chemin: str) -> None:
    assert violations_fenetre(_lire(chemin)) == [], chemin


@pytest.mark.parametrize("chemin", SURFACES)
def test_b_anciens_litteraux_absents(chemin: str) -> None:
    assert anciens_litteraux(_lire(chemin)) == [], chemin


@pytest.mark.parametrize("chemin", ORCHESTRATEURS)
def test_c_planner_reprend_son_plan(chemin: str) -> None:
    assert reprise_ecrite(_lire(chemin)), chemin


@pytest.mark.parametrize("chemin", DEFS_HORS_CHAINE)
def test_d_bandeau_dans_le_corps(chemin: str) -> None:
    assert bandeau_dans_le_corps(chemin, _lire(chemin)), chemin


@pytest.mark.parametrize("chemin", DEFS_HORS_CHAINE)
def test_e_description_hors_chaine(chemin: str) -> None:
    description, _ = description_et_corps(chemin, _lire(chemin))
    assert erreurs_description(description) == [], chemin


@pytest.mark.parametrize("chemin", PLANNERS)
def test_f_planner_porte_t7(chemin: str) -> None:
    assert T7 in _lire(chemin), chemin


def test_mutant_ancienne_phrase_canonique_rougit() -> None:
    texte = _lire("AGENTS.md")
    assert violations_fenetre(texte) == [] and anciens_litteraux(texte) == [], "base rouge"
    mutant = texte.replace(T1, ANCIENNE_T1, 1)
    assert mutant != texte, "T1 absente d'AGENTS.md : la mutation ne change rien"
    assert violations_fenetre(mutant)
    assert anciens_litteraux(mutant)


@pytest.mark.parametrize("chemin", ORCHESTRATEURS)
def test_mutant_ligne_d_escalade_rougit_malgre_la_reference(chemin: str) -> None:
    texte = _lire(chemin)
    assert violations_fenetre(texte) == [] and anciens_litteraux(texte) == [], "base rouge"
    mutant = texte.replace(LIGNE_REPRISE, LIGNE_ESCALADE, 1)
    assert mutant != texte, f"{chemin} : ligne de reprise absente, la mutation ne change rien"
    fautes = violations_fenetre(mutant)
    assert any("marqueur" in faute for faute in fautes), fautes
    assert anciens_litteraux(mutant)


@pytest.mark.parametrize("phrase", REBRANCHEMENTS)
@pytest.mark.parametrize("chemin", SURFACES)
def test_mutant_rebranchement_en_mots_neufs_rougit(chemin: str, phrase: str) -> None:
    """Réserve C1 : la phrase porte la référence et aucun ancien littéral — seul le
    marqueur positif de (a) la voit. Ajoutée en FIN de surface, loin d'un marqueur
    légitime (mesuré : aucune des 21 surfaces ne finit par un marqueur)."""
    texte = _lire(chemin)
    assert violations_fenetre(texte) == [] and anciens_litteraux(texte) == [], "base rouge"
    mutant = f"{texte}\n\n{phrase}\n"
    assert mutant != texte
    fautes = violations_fenetre(mutant)
    assert any("marqueur" in faute for faute in fautes), fautes
    assert all(DECISION not in faute for faute in fautes), fautes
    assert anciens_litteraux(mutant) == [], "un ancien littéral : (a) n'est pas seul juge"


def test_mutant_ancien_litteral_en_casse_changee_rougit() -> None:
    """(b) ignore la casse : un ancien littéral réécrit en capitales rougit."""
    texte = _lire("AGENTS.md")
    assert anciens_litteraux(texte) == [], "base rouge"
    for litteral in ANCIENS_LITTERAUX:
        mutant = f"{texte}\n\n{litteral.upper()}\n"
        assert mutant != texte
        assert anciens_litteraux(mutant) == [litteral], litteral


@pytest.mark.parametrize("chemin", DEFS_HORS_CHAINE)
def test_mutant_formes_francaises_d_avant_rougissent(chemin: str) -> None:
    """Les épingles gardent leur force : le bandeau français d'avant, remis à la place de l'anglais
    (prose), ne satisfait pas (d) ; la ligne de reprise traduite en anglais (bloc imprimé) ne satisfait
    pas (c)."""
    texte = _lire(chemin)
    assert bandeau_dans_le_corps(chemin, texte), "base rouge : (d) ne tient pas sur la déf"
    mutant = texte.replace(BANDEAU, BANDEAU_FR, 1)
    assert mutant != texte, "base rouge : bandeau anglais absent"
    assert not bandeau_dans_le_corps(chemin, mutant), "(d) tient encore sur le bandeau français d'avant"
    for orchestrateur in ORCHESTRATEURS:
        orch = _lire(orchestrateur)
        assert reprise_ecrite(orch), f"{orchestrateur} : base rouge, (c) ne tient pas"
        mutant_orch = orch.replace(LIGNE_REPRISE, LIGNE_REPRISE_EN, 1)
        assert mutant_orch != orch, f"{orchestrateur} : ligne de reprise absente, la mutation ne change rien"
        assert not reprise_ecrite(mutant_orch), (
            f"{orchestrateur} : (c) tient encore sur la reprise traduite en anglais")


@pytest.mark.parametrize("chemin", DEFS_HORS_CHAINE)
def test_mutant_bandeau_retire_rougit(chemin: str) -> None:
    texte = _lire(chemin)
    assert bandeau_dans_le_corps(chemin, texte), "base rouge"
    mutant = texte.replace(BANDEAU, "", 1)
    assert mutant != texte
    assert not bandeau_dans_le_corps(chemin, mutant)


@pytest.mark.parametrize("chemin", DEFS_HORS_CHAINE)
def test_mutant_ancienne_description_restauree_rougit(chemin: str) -> None:
    texte = _lire(chemin)
    assert erreurs_description(description_et_corps(chemin, texte)[0]) == [], "base rouge"
    mutant = _restaurer_description(chemin, texte, ANCIENNES_DESCRIPTIONS[chemin])
    assert mutant != texte
    assert description_et_corps(chemin, mutant)[0] == ANCIENNES_DESCRIPTIONS[chemin]
    assert erreurs_description(description_et_corps(chemin, mutant)[0])
