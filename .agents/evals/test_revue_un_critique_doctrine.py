"""BANC PERMANENT — la revue de clôture tient sur UN critique (S-00004500, T-00001227).

POURQUOI CE BANC. La décision pilote S-00004500 a réécrit les cinq défs
`orchestrator` et les quinze défs `critic-*` (T-00001226) : la clôture tient sur
UN critique, `critic-opus` en nominal, repli `critic-fable` puis
`critic-sonnet-max`, chacun seul porteur des angles A et B. L'exec-critic de
T-00001226 a nommé l'angle mort (S-00004521) : aucun banc ne tenait ces vingt
fichiers, donc un retour de la paire — la paire `∥`, « deux critiques » de
clôture, des critiques « sans se coordonner » — serait passé vert.

CE QU'IL TIENT, ZÉRO LLM, par la forme du texte (blancs normalisés, pour qu'un
retour à la ligne ne cache rien) :
  (1) chaque orchestrator écrit « ONE closing critic for every closure (pilot
      decision S-00004500): critic-opus » et la cascade « critic-fable, then
      critic-sonnet-max » ;
  (2) chaque déf `critic-*` écrit « ONE critic for every closure
      (S-00004500) » (en anglais depuis T-01M5S9338BJP1B5RM3TG14AMYT ; la forme
      française d'avant ne satisfait plus le motif) ;
  (3) aucun des vingt fichiers ne porte un motif de PAIRE ;
  (4) contrôles positifs : chaque motif de PAIRE, injecté dans le texte RÉEL de
      chacun des vingt fichiers, le fait rougir ; la phrase positive retirée
      aussi. Un contrôle qui ne change rien au texte est lui-même un échec.

LES VALEURS ATTENDUES SONT ÉCRITES ICI, jamais extraites d'un hôte
(L-00000261) : un banc qui lirait sa phrase dans un des fichiers surveillés
resterait vert sur une réécriture coordonnée des vingt.

BORNES, ÉCRITES. Il lit ces vingt fichiers et rien d'autre ; une paire formulée
hors des motifs de PAIRE lui échappe. « closing binôme » et « binôme de
clôture » sont le NOM du mécanisme (`BINOME_REQUIRED`) et restent permis ;
« en parallèle » seul aussi — les défs critic disent que deux PORTES en
parallèle produisent des faux rouges. Les motifs sont écrits DÉCOUPÉS, pour que
le balayage A1 de T-00001227 ne voie jamais ce banc lui-même.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# LE PÉRIMÈTRE. Vingt fichiers nommés : ni glob, ni balayage.
HOSTS = {
    "claude": ".claude/agents/{}.md",
    "codex": ".codex/agents/{}.toml",
    "gemini": ".gemini/agents/{}.md",
    "copilot": ".github/agents/{}.agent.md",
    "kimi": ".kimi-code/agents/{}.md",
}
CRITICS = ("critic-opus", "critic-fable", "critic-sonnet-max")
ORCHESTRATORS = {h: ROOT / tpl.format("orchestrator") for h, tpl in HOSTS.items()}
CRITIC_DEFS = {(h, c): ROOT / tpl.format(c) for h, tpl in HOSTS.items() for c in CRITICS}

# (1) et (2) — les phrases positives.
ORCH_ONE_CRITIC = re.compile(
    r"ONE closing critic for every closure \(pilot decision S-00004500\): `?critic-opus`?"
)
ORCH_CASCADE = re.compile(r"`?critic-fable`?, then `?critic-sonnet-max`?")
# T-01M5S9338BJP1B5RM3TG14AMYT : les quinze défs critiques sont en anglais ; la phrase française
# d'avant (« UN critique pour toute clôture (S-00004500) ») ne la satisfait plus — témoin
# `test_controle_positif_la_phrase_francaise_d_avant_rougit`.
CRITIC_ONE = re.compile(r"ONE critic for every closure \(S-00004500\)")
CRITIC_ONE_FR_D_AVANT = "UN critique pour toute clôture (S-00004500)"

# (3) — les motifs de PAIRE, écrits découpés (voir l'en-tête).
PAIRE = {
    "paire ∥": re.compile(r"critic-opus`?\s*" + "∥" + r"\s*`?critic-fable"),
    "deux critiques": re.compile(r"deux\s+critiques"),
    "two critics": re.compile(r"two\s+(?:distinct\s+)?(?:traced\s+)?(?:closing\s+)?critics"),
    "both critics": re.compile(r"both\s+critics"),
    "closing pair": re.compile(r"closing\s+" + r"pair\b"),
    "sans se coordonner": re.compile(r"sans\s+se\s+coordonner"),
    "without coordinating": re.compile(r"without\s+coordinating"),
}
# (4) — un échantillon par motif, injecté dans le texte réel.
ECHANTILLONS = {
    "paire ∥": "critic-opus " + "∥" + " critic-fable",
    "deux critiques": "deux critiques " + "distincts",
    "two critics": "two traced " + "closing critics",
    "both critics": "both " + "critics",
    "closing pair": "the closing " + "pair runs",
    "sans se coordonner": "sans se " + "coordonner",
    "without coordinating": "without " + "coordinating",
}


def _plat(texte: str) -> str:
    return re.sub(r"\s+", " ", texte)


def violations(texte: str, orchestrator: bool) -> list[str]:
    """Les fautes d'un texte, par nom ; vide = conforme."""
    plat = _plat(texte)
    fautes = [nom for nom, rx in PAIRE.items() if rx.search(plat)]
    if orchestrator:
        if not ORCH_ONE_CRITIC.search(plat):
            fautes.append("phrase « ONE closing critic … S-00004500 » absente")
        if not ORCH_CASCADE.search(plat):
            fautes.append("cascade « critic-fable, then critic-sonnet-max » absente")
    elif not CRITIC_ONE.search(plat):
        fautes.append("phrase « ONE critic for every closure (S-00004500) » absente")
    return fautes


def _cas():
    for h, p in ORCHESTRATORS.items():
        yield pytest.param(p, True, id=f"orchestrator-{h}")
    for (h, c), p in CRITIC_DEFS.items():
        yield pytest.param(p, False, id=f"{c}-{h}")


def test_le_perimetre_compte_vingt_fichiers() -> None:
    assert len(ORCHESTRATORS) == 5 and len(CRITIC_DEFS) == 15
    absents = [str(p.relative_to(ROOT)) for p in [*ORCHESTRATORS.values(), *CRITIC_DEFS.values()] if not p.is_file()]
    assert not absents, f"fichiers absents — le banc ne surveille rien : {absents}"


@pytest.mark.parametrize(("chemin", "orchestrator"), list(_cas()))
def test_la_revue_de_cloture_tient_sur_un_critique(chemin: Path, orchestrator: bool) -> None:
    fautes = violations(chemin.read_text(encoding="utf-8"), orchestrator)
    assert not fautes, f"{chemin.relative_to(ROOT)} : {fautes} (S-00004500 : UN critique de clôture)"


@pytest.mark.parametrize(("chemin", "orchestrator"), list(_cas()))
def test_controle_positif_chaque_motif_de_paire_rougit(chemin: Path, orchestrator: bool) -> None:
    texte = chemin.read_text(encoding="utf-8")
    assert set(ECHANTILLONS) == set(PAIRE), "un motif de PAIRE sans échantillon : contrôle vide"
    for nom, echantillon in ECHANTILLONS.items():
        mute = texte + "\n" + echantillon + "\n"
        assert mute != texte
        assert nom in violations(mute, orchestrator), f"{chemin.relative_to(ROOT)} : « {nom} » injecté ne rougit pas"


@pytest.mark.parametrize(("chemin", "orchestrator"), list(_cas()))
def test_controle_positif_la_phrase_retiree_rougit(chemin: Path, orchestrator: bool) -> None:
    plat = _plat(chemin.read_text(encoding="utf-8"))
    rx = ORCH_ONE_CRITIC if orchestrator else CRITIC_ONE
    mute = rx.sub("", plat)
    assert mute != plat, f"{chemin.relative_to(ROOT)} : la phrase positive n'a pas été trouvée (contrôle vide)"
    assert violations(mute, orchestrator), f"{chemin.relative_to(ROOT)} : la phrase retirée ne rougit pas"


@pytest.mark.parametrize("chemin", list(CRITIC_DEFS.values()), ids=[f"{c}-{h}" for h, c in CRITIC_DEFS])
def test_controle_positif_la_phrase_francaise_d_avant_rougit(chemin: Path) -> None:
    """La re-épingle anglaise garde sa force : la phrase française d'avant, remise à la place de
    l'anglaise, ne satisfait pas la règle."""
    plat = _plat(chemin.read_text(encoding="utf-8"))
    mute = CRITIC_ONE.sub(CRITIC_ONE_FR_D_AVANT, plat)
    assert mute != plat, f"{chemin.relative_to(ROOT)} : contrôle vide"
    assert violations(mute, False), f"{chemin.relative_to(ROOT)} : la phrase française d'avant reste verte"
