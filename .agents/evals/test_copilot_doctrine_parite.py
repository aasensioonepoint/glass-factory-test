"""Parité de la doctrine Copilot (`.github/copilot-instructions.md`) avec le cœur partagé.

TÉMOIN du lot B de T-01M5MCXMQVHZ231CW0K2JR76MD (décision pilote S-01M5MCXYV352ZNNW7ZC75T8DJH) :
la doctrine Copilot porte ce que `AGENTS.md` tient pour tous les hôtes — `iac_guard` parmi les gardes
qui refusent, `CADRE_GATE_JOBS` (forme nue de la porte), le clone jetable `mktemp -d /tmp/cadre-`,
le workflow `$jira`, la ligne d'état chrono de Copilot (`statusLine`, geste du pilote), la profondeur 2
des skills mesurée sur Copilot — et ne dit plus trois choses que la mesure du 2026-10-23 (Copilot CLI
1.0.96) a réfutées : la profondeur « NOT measured », l'`additionalContext` « never replayed », et une
session Copilot « sans marqueur » (Copilot CLI exporte `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` ;
que le refus les lise, c'est `tracabilite_jira.AGENT_CALLER_MARKERS` qui le tient, jamais la doctrine).
Base 42abc9e23 : 9 fautes. Chaque mutant de `_mutants` doit rougir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ".github/copilot-instructions.md"

# (étiquette, motif EXIGÉ) — présence littérale dans le texte aplati.
REQUIS = (
    ("iac_guard", "`iac_guard`"),
    ("CADRE_GATE_JOBS", "CADRE_GATE_JOBS=1"),
    ("clone jetable", "mktemp -d /tmp/cadre-"),
    ("workflow jira", "`$jira`"),
    ("workflow setup", "`$setup`"),
    ("ligne d'état chrono", "`statusLine.command`"),
    ("profondeur 2 mesurée", "level 2, measured"),
)
# (étiquette, motif INTERDIT) — phrases réfutées par la mesure du 2026-10-23.
INTERDITS = (
    ("profondeur non mesurée", "depth are NOT measured"),
    ("additionalContext jamais relu", "typed by the SDK, never replayed"),
)
# Ligne du marqueur Copilot : les deux variables exportées ET le renvoi au tuple qui fait foi.
MARQUEURS = ("`COPILOT_AGENT_SESSION_ID`", "`COPILOT_CLI`", "`tracabilite_jira.AGENT_CALLER_MARKERS`")
# Copilot dans une phrase « sans marqueur » : la doctrine ne le dit plus (le shell de l'agent en porte un).
COPILOT_SANS_MARQUEUR = re.compile(
    r"Copilot\b[^.;:()]{0,40}\b(?:session there is no marker|without (?:a |any )?marker|sans marqueur)")


def _plat(texte: str) -> str:
    return " ".join(texte.split())


def fautes(texte: str) -> list:
    plat = _plat(texte)
    f = [f"absent : {nom}" for nom, motif in REQUIS if motif not in plat]
    f += [f"présent : {nom}" for nom, motif in INTERDITS if motif in plat]
    marqueur = [m for m in MARQUEURS if m not in plat]
    sans = COPILOT_SANS_MARQUEUR.search(plat)
    if marqueur or sans:
        f.append("ligne :7 marqueur Copilot : "
                 + ", ".join([f"absent {m}" for m in marqueur] + ([f"réfuté « {sans.group(0)} »"] if sans else [])))
    return f


def _mutants(texte: str) -> dict:
    plat = _plat(texte)
    m = {f"retiré : {nom}": plat.replace(motif, "") for nom, motif in REQUIS}
    m.update({f"remis : {nom}": plat + " " + motif + "." for nom, motif in INTERDITS})
    m.update({f"marqueur retiré : {x}": plat.replace(x, "") for x in MARQUEURS})
    m["Copilot remis sans marqueur"] = plat + " In a Codex, Gemini, Copilot or Kimi session there is no marker."
    return m


def test_doctrine_copilot_a_parite():
    assert fautes((ROOT / DOC).read_text(encoding="utf-8")) == []


def test_chaque_mutant_de_la_doctrine_rougit():
    texte = (ROOT / DOC).read_text(encoding="utf-8")
    mutants = _mutants(texte)
    assert len(mutants) == len(REQUIS) + len(INTERDITS) + len(MARQUEURS) + 1
    verts = [nom for nom, mut in mutants.items() if mut == _plat(texte) or fautes(mut) == []]
    assert verts == [], verts


# Les deux autres surfaces qui disaient l'`additionalContext` Copilot « jamais rejoué » : la mesure
# du 2026-10-23 y est citée, l'ancienne phrase n'y revient pas.
SURFACES_MESURE = {
    ".agents/skills/guardrails/SKILL.md": "typé par le SDK, jamais rejoué",
    ".agents/security/semgrep-scan.sh": "STATIC, NEVER REPLAYED",
}
MESURE_1096 = "(2026-10-23, Copilot CLI 1.0.96)"


def fautes_mesure(chemin: str, texte: str) -> list:
    f = [] if MESURE_1096 in texte else [f"{chemin} : mesure 1.0.96 absente"]
    if SURFACES_MESURE[chemin] in texte:
        f.append(f"{chemin} : « {SURFACES_MESURE[chemin]} » réfuté")
    return f


@pytest.mark.parametrize("chemin", sorted(SURFACES_MESURE))
def test_additional_context_mesure_citee(chemin):
    texte = (ROOT / chemin).read_text(encoding="utf-8")
    assert fautes_mesure(chemin, texte) == []
    assert fautes_mesure(chemin, texte.replace(MESURE_1096, ""))
    assert fautes_mesure(chemin, texte + "\n" + SURFACES_MESURE[chemin])


@pytest.mark.parametrize("phrase", (
    "in a Codex, Gemini, Copilot or Kimi session there is no marker",
    "Copilot without a marker",
    "Codex, Gemini, Copilot et Kimi sans marqueur",
))
def test_neg_copilot_sans_marqueur_rougit(phrase):
    assert COPILOT_SANS_MARQUEUR.search(phrase)


def test_neg_le_faux_positif_nomme_n_est_pas_un_copilot_sans_marqueur():
    assert not COPILOT_SANS_MARQUEUR.search(
        "a shell started from Copilot CLI inherits `COPILOT_CLI`; in a Codex, Gemini or Kimi session there is no marker")
