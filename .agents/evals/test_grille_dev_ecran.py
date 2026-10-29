"""Le dev d'écran joue la grille du juge avant de rendre (T-01M5NPC8GCA28T1XBWTG456BN0, lot C ;
décision pilote S-01M5N24P2Y0SH6S0W0YNG3TAN6).

CE QU'IL JUGE. (1) La grille de la skill `frontend-fidelity` (§ The design-review grid, played by
the dev) porte les huit phases de `design-review` (`.claude/agents/design-review.md` § Phases),
titres ÉGAUX, dans le même ordre. (2) Chacune des cinq défs `frontend-fidelity` porte la section
« play its eight phases » APRÈS l'ancre de clôture de « Before you hand back » (« Capture each
output whole » ; Codex et Copilot : « Capture outputs whole »), donc hors du périmètre que lit
`test_dev_avant_de_rendre.py`, et AVANT « What you return » ; la section nomme `GRID:`, la skill
par son chemin et la grille par son titre.

CE QU'IL NE PROUVE PAS. Une grille écrite n'est pas une grille jouée : design-review rejuge après
le dev. La source des titres est la déf Claude de design-review ; ses miroirs d'autres hôtes ne
sont pas relus ici. Le contenu de chaque phase de la grille n'est pas comparé à celui du juge,
seul son titre.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUGE = ROOT / ".claude" / "agents" / "design-review.md"
SKILL_REL = ".agents/skills/frontend-fidelity/SKILL.md"
SKILL = ROOT / SKILL_REL
TITRE_GRILLE = "The design-review grid, played by the dev"
DEFS = {
    ".claude": ROOT / ".claude/agents/frontend-fidelity.md",
    ".codex": ROOT / ".codex/agents/frontend-fidelity.toml",
    ".gemini": ROOT / ".gemini/agents/frontend-fidelity.md",
    ".github": ROOT / ".github/agents/frontend-fidelity.agent.md",
    ".kimi-code": ROOT / ".kimi-code/agents/frontend-fidelity.md",
}
CLOSE = re.compile(r"Capture (?:each output|outputs) whole")
SECTION = re.compile(r"(?i)before design-review - play its eight phases yourself")
RETOUR = re.compile(r"(?i)what you return")
EXIGES = ("eight phases of design-review", "evidence under GRID:", SKILL_REL, TITRE_GRILLE, "INTERACTION:")
PHASE = re.compile(r"(?m)^(\d)\. \*\*([^*]+)\*\*")


def _plat(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("`", "").replace("**", "").replace("—", "-"))


def phases(texte: str, ouverture: str) -> list[tuple[str, str]]:
    """Les phases numérotées `N. **Titre.**` de la section qui s'ouvre sur `ouverture`, jusqu'au
    titre `## ` suivant."""
    at = texte.find(ouverture)
    if at < 0:
        return []
    fin = texte.find("\n## ", at + len(ouverture))
    return PHASE.findall(texte[at:fin if fin >= 0 else len(texte)])


def ecarts_grille(juge: str, skill: str) -> list[str]:
    attendues = phases(juge, "## Phases")
    vues = phases(skill, f"## {TITRE_GRILLE}")
    out = []
    if len(attendues) != 8:
        out.append(f"juge : {len(attendues)} phases au lieu de 8")
    if vues != attendues:
        out.append(f"grille {vues} != juge {attendues}")
    return out


def manquants(texte: str) -> list[str]:
    plat = _plat(texte)
    close, sec = CLOSE.search(plat), SECTION.search(plat)
    if not close:
        return ["ancre de clôture"]
    if not sec:
        return ["section"]
    if sec.start() < close.end():
        return ["section avant l'ancre de clôture"]
    retour = RETOUR.search(plat, sec.end())
    if not retour:
        return ["What you return après la section"]
    corps = plat[sec.start():retour.start()]
    return [f"section sans {e!r}" for e in EXIGES if e not in corps]


def _lire(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_la_grille_porte_les_huit_phases_du_juge() -> None:
    assert ecarts_grille(_lire(JUGE), _lire(SKILL)) == []


@pytest.mark.parametrize("hote", sorted(DEFS))
def test_chaque_def_joue_la_grille_apres_l_ancre(hote: str) -> None:
    assert manquants(_lire(DEFS[hote])) == [], hote


def test_mutant_phase_otee_de_la_grille_rougit() -> None:
    skill = _lire(SKILL)
    mute = re.sub(r"(?m)^6\. \*\*Robustness\.\*\*[^\n]*\n", "", skill, count=1)
    assert mute != skill, "mutant vide"
    assert ecarts_grille(_lire(JUGE), mute) != []


def test_mutant_titre_renomme_chez_le_juge_rougit() -> None:
    juge = _lire(JUGE)
    mute = juge.replace("**Primary flow.**", "**Main flow.**", 1)
    assert mute != juge, "mutant vide"
    assert ecarts_grille(mute, _lire(SKILL)) != []


def test_mutant_ordre_permute_rougit() -> None:
    skill = _lire(SKILL)
    mute = skill.replace("1. **Primary flow.**", "1. **@@.**", 1).replace(
        "2. **Responsive.**", "2. **Primary flow.**", 1).replace("1. **@@.**", "1. **Responsive.**", 1)
    assert mute != skill, "mutant vide"
    assert ecarts_grille(_lire(JUGE), mute) != []


@pytest.mark.parametrize("hote", sorted(DEFS))
def test_mutant_section_avant_l_ancre_rougit(hote: str) -> None:
    texte = _lire(DEFS[hote])
    sec = re.search(r"(?i)before design-review [-—] play its eight phases yourself", texte)
    close = CLOSE.search(texte)
    assert sec and close, f"{hote} : mutant vide"
    # La section remonte avant « Before you hand back » : l'ancre de clôture la suit.
    avant = texte.find("Before you hand back")
    mute = texte[:avant] + sec.group(0) + " eight phases of design-review evidence under GRID: " \
        + texte[avant:sec.start()] \
        + texte[sec.end():]
    assert manquants(mute) != [], f"{hote} : section déplacée restée verte"


@pytest.mark.parametrize("hote", sorted(DEFS))
@pytest.mark.parametrize("exige", EXIGES)
def test_mutant_atome_ote_de_la_section_rougit(hote: str, exige: str) -> None:
    texte = _lire(DEFS[hote])
    plat = _plat(texte)
    sec = SECTION.search(plat)
    retour = RETOUR.search(plat, sec.end())
    mute = plat[:sec.start()] + plat[sec.start():retour.start()].replace(exige, "X") + plat[retour.start():]
    assert mute != plat, f"{hote} : mutant vide sur {exige!r}"
    assert f"section sans {exige!r}" in manquants(mute), f"{hote} : {exige!r} ôté, resté vert"


def test_population_vide_rougit() -> None:
    assert manquants("") != [] and ecarts_grille("", "") != []
