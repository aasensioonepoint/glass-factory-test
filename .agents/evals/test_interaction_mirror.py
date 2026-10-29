"""La ligne INTERACTION d'un plan d'écran, épinglée sur ses surfaces (T-01M5NPC8GCA28T1XBWTG456BN0,
lot C ; décision pilote S-01M5N24P2Y0SH6S0W0YNG3TAN6).

CE QU'IL JUGE. La règle `interaction` du registre (`doctrine_registre.py`) : chaque surface qui
ÉNONCE la règle d'écran (routeur, miroir Copilot, skill) porte le littéral `INTERACTION:` à sept
clés, sa forme `sans objet` et la décision ; chacune des cinq défs `frontend-fidelity` porte la
ligne appliquée à l'étape 0 et l'arbitrage RENDU au parent. Les jetons vivent au registre, nulle
part ici (`test_doctrine_registre.py` 4d). En plus : les sept clés, dans leur ordre, sur chaque
surface (découpe sur « ; » puis au PREMIER `=`, comme le préflight du lot A) ; et l'ABSENCE de
l'ancienne clause « seul contrôle UI qui bloque » sur les surfaces d'énoncé.

CE QU'IL NE PROUVE PAS. Une ligne présente n'est pas une ligne appliquée : le dev est jugé par
design-review et exec-critic. Le tuple de clés est relu dans `plan_preflight.INTERACTION_CLES`
(C7) : un ordre changé au préflight rougit ici.
Les défs plan-critic et planner ne sont pas lues ici (lot B, `test_plan_ecran_juges.py`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

BIN = ROOT / ".agents" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import doctrine_registre as R  # noqa: E402
import plan_preflight  # noqa: E402

REGLE = "interaction"
#: Les sept clés, dans leur ordre, relues du préflight (C7).
CLES = plan_preflight.INTERACTION_CLES
OUVERTURE = "INTERACTION: "
#: L'ancienne clause, qui faisait du mockup le SEUL contrôle UI bloquant.
ANCIENNES = ("seul contrôle UI qui bloque", "it is the one UI check that blocks")

ENONCE = R.chemins(REGLE, "enonce")
DEV = R.chemins(REGLE, "dev")


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def cles_de(texte: str) -> list[tuple[str, ...]]:
    """Les clés de chaque littéral `INTERACTION: <clé>=…` à sept segments du texte : découpe sur
    « ; », puis au PREMIER `=` ; le littéral s'arrête au premier backtick, guillemet ou parenthèse
    fermante."""
    trouves = []
    at = texte.find(OUVERTURE)
    while at >= 0:
        fin = len(texte)
        for borne in ("`", '"', ")", "\n"):
            k = texte.find(borne, at)
            if 0 <= k < fin:
                fin = k
        corps = texte[at + len(OUVERTURE):fin]
        if "=" in corps:
            trouves.append(tuple(seg.split("=", 1)[0].strip() for seg in corps.split(";")))
        at = texte.find(OUVERTURE, at + 1)
    return trouves


def test_membres_des_surfaces() -> None:
    """Contrôle négatif : une surface retirée du registre rougit ici."""
    assert set(ENONCE) == {"AGENTS.md", ".github/copilot-instructions.md",
                           ".agents/skills/frontend-fidelity/SKILL.md"}
    assert len(DEV) == 5 and all(Path(p).stem.startswith("frontend-fidelity") for p in DEV)


@pytest.mark.parametrize("groupe,rel", [("enonce", r) for r in ENONCE] + [("dev", r) for r in DEV])
def test_chaque_surface_porte_ses_jetons(groupe: str, rel: str) -> None:
    attendus = R.jetons(REGLE, groupe)
    texte = lire(rel)
    assert R.manquants(texte, attendus) == [], f"{rel} ({groupe})"
    for j in attendus:
        assert R.manquants(texte.replace(j, ""), attendus) == [j], f"{rel} privé de {j!r} reste vert"


@pytest.mark.parametrize("rel", ENONCE + DEV)
def test_les_sept_cles_dans_leur_ordre(rel: str) -> None:
    trouves = cles_de(lire(rel))
    assert trouves, f"{rel} : aucun littéral INTERACTION à clés"
    assert all(t == CLES for t in trouves), f"{rel} : {trouves}"


@pytest.mark.parametrize("rel", ENONCE + DEV)
def test_mutant_une_cle_otee_ou_permutee_rougit(rel: str) -> None:
    texte = lire(rel)
    at = texte.find(OUVERTURE + "focus=")
    assert at >= 0, f"{rel} : littéral absent"
    tete, queue = texte[:at], texte[at:]
    permute = queue.replace("echap=", "@@=", 1).replace("modal=", "echap=", 1).replace("@@=", "modal=", 1)
    for mute in (tete + queue.replace(" ; wcag=", " ; ", 1), tete + permute):
        assert mute != texte, f"{rel} : mutant vide"
        assert any(t != CLES for t in cles_de(mute)), f"{rel} : mutant de clés resté vert"


@pytest.mark.parametrize("rel", ENONCE)
def test_l_ancienne_clause_du_seul_controle_est_absente(rel: str) -> None:
    texte = lire(rel)
    assert [a for a in ANCIENNES if a in texte] == [], rel


def test_mutant_l_ancienne_clause_revenue_rougit() -> None:
    texte = lire(ENONCE[0]) + "\n" + ANCIENNES[1] + "\n"
    assert [a for a in ANCIENNES if a in texte] != []


def test_decoupe_au_premier_egal() -> None:
    """Une valeur qui porte elle-même un `=` ne déplace pas la clé (étape 1, C9)."""
    ligne = "`" + OUVERTURE + " ; ".join(f"{c}=a=b" for c in CLES) + "`"
    assert cles_de(ligne) == [CLES]
    assert cles_de("`" + OUVERTURE + "sans objet | motif`") == []
