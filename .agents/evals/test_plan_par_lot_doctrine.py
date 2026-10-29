"""Le plan par lot est écrit, jumeau, dans les skills kickoff et planning (T-01M54GE4K9EZRRQFD9TAVNWYKM, lot D).

Les jetons, les surfaces et le titre vivent dans `doctrine_registre.py`, règle `REGLE`
ci-dessous, et nulle part ici : `test_doctrine_registre.py` (4d) refuse un jeton recopié en
constante. Ce banc lit le TEXTE seul ; il n'exécute ni `plan_plafond.py` ni `plan_lots.py`
(tenus par leurs propres bancs).

Ce qu'il tient :
  (a) chaque jeton est présent DANS le paragraphe de chaque surface (pas seulement quelque part
      dans le fichier), et le retirer du paragraphe fait manquer CE jeton et lui seul ;
  (b) chaque surface porte le paragraphe UNE fois, ouvert par le titre en gras ;
  (c) GÉMELLITÉ : les deux paragraphes sont égaux ligne pour ligne, ouverture retirée
      (« 8c. » au kickoff SKILL, rien au planning SKILL) ;
  (d) PLACE : au kickoff SKILL, l'étape qui précède 8c est 8b et la ligne qui le suit ouvre 9 ;
      au planning SKILL, le titre `### <titre>` précède immédiatement le paragraphe, dans
      l'Étape 2, et seules des lignes vides le séparent de la section suivante ;
  (e) chaque instrument rougit sur un mutant en mémoire, et les membres sont épinglés.
Bornes : la `limite` de la règle, au registre.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402

REGLE = "plan-par-lot"
GROUPE = "paragraphe"
CE_BANC = ".agents/evals/test_plan_par_lot_doctrine.py"
KICKOFF = ".agents/skills/kickoff/SKILL.md"
PLANNING = ".agents/skills/planning/SKILL.md"
#: Instruments de place, jamais des jetons : au kickoff SKILL, l'ouverture du paragraphe, l'étape
#: qui le précède et celle qui le suit ; au planning SKILL, le niveau du titre, la section qui
#: l'enclôt et le niveau de la section suivante.
PREFIXE_KICKOFF = "8c. "
ETAPE_AVANT = "8b. "
ETAPE_APRES = "9. "
NIVEAU_TITRE = "### "
NIVEAU_SECTION = "## "
SECTION_ETAPE_2 = "## Étape 2"
#: Une ouverture d'étape numérotée en colonne 0 (`9. `, `8b. `) : elle clôt un paragraphe.
ETAPE = re.compile(r"^\d+[a-z]?\. ")

TITRE: str = R.regle(REGLE)["titre"]
JETONS = R.jetons(REGLE, GROUPE)


def _texte(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def ouverture(titre: str) -> str:
    """L'ouverture en gras du paragraphe, commune aux deux jumeaux."""
    return f"**{titre}** — "


def _fin(lignes: list[str], debut: int) -> int:
    """L'indice qui suit la dernière ligne du paragraphe ouvert en `debut` : une ligne vide, un
    titre ou une ouverture d'étape le clôt."""
    i = debut + 1
    while (
        i < len(lignes)
        and lignes[i].strip()
        and not lignes[i].startswith("#")
        and not ETAPE.match(lignes[i])
    ):
        i += 1
    return i


def bornes(lignes: list[str], prefixe: str, titre: str) -> tuple[int, int] | None:
    """(début, fin) du paragraphe ouvert par `prefixe` puis l'ouverture en gras ; None s'il
    manque ou s'il est doublé."""
    tete = prefixe + ouverture(titre)
    debuts = [i for i, ligne in enumerate(lignes) if ligne.startswith(tete)]
    if len(debuts) != 1:
        return None
    return debuts[0], _fin(lignes, debuts[0])


def corps(texte: str, prefixe: str, titre: str) -> list[str] | None:
    """Les lignes du paragraphe, `prefixe` retiré de la première ; None s'il manque ou s'il est
    doublé."""
    lignes = texte.splitlines()
    b = bornes(lignes, prefixe, titre)
    if b is None:
        return None
    debut, fin = b
    return [lignes[debut][len(prefixe):], *lignes[debut + 1:fin]]


def fautes_kickoff(texte: str, titre: str) -> list[str]:
    """Les fautes de PLACE du paragraphe au kickoff SKILL : entre 8b et 9, ouvert par « 8c. »."""
    lignes = texte.splitlines()
    b = bornes(lignes, PREFIXE_KICKOFF, titre)
    if b is None:
        return [f"paragraphe {PREFIXE_KICKOFF!r} absent ou doublé"]
    debut, fin = b
    fautes: list[str] = []
    avant = [ligne for ligne in lignes[:debut] if ETAPE.match(ligne)]
    if not avant or not avant[-1].startswith(ETAPE_AVANT):
        fautes.append(f"l'étape qui le précède n'est pas {ETAPE_AVANT!r}")
    if fin >= len(lignes) or not lignes[fin].startswith(ETAPE_APRES):
        fautes.append(f"la ligne qui le suit n'ouvre pas {ETAPE_APRES!r}")
    return fautes


def fautes_planning(texte: str, titre: str) -> list[str]:
    """Les fautes de PLACE du paragraphe au planning SKILL : sous son titre, à la fin de l'Étape 2."""
    lignes = texte.splitlines()
    titre_md = NIVEAU_TITRE + titre
    places = [i for i, ligne in enumerate(lignes) if ligne == titre_md]
    if len(places) != 1:
        return [f"titre {titre_md!r} absent ou doublé"]
    h = places[0]
    b = bornes(lignes, "", titre)
    if b is None:
        return ["paragraphe absent ou doublé"]
    debut, fin = b
    fautes: list[str] = []
    if debut != h + 1:
        fautes.append("le titre ne précède pas immédiatement le paragraphe")
    sections = [ligne for ligne in lignes[:h] if ligne.startswith(NIVEAU_SECTION)]
    if not sections or not sections[-1].startswith(SECTION_ETAPE_2):
        fautes.append("le paragraphe n'est pas dans l'Étape 2")
    suite = [ligne for ligne in lignes[fin:] if ligne.strip()]
    if not suite or not suite[0].startswith(NIVEAU_SECTION):
        fautes.append("le paragraphe ne clôt pas l'Étape 2")
    return fautes


def fautes(textes: dict[str, str], titre: str, jetons: tuple[str, ...]) -> list[str]:
    """Toutes les fautes des deux surfaces : présence dans le paragraphe, gémellité, place."""
    trouvees: list[str] = []
    k = corps(textes[KICKOFF], PREFIXE_KICKOFF, titre)
    p = corps(textes[PLANNING], "", titre)
    for rel, c in ((KICKOFF, k), (PLANNING, p)):
        if c is None:
            trouvees.append(f"{rel} : paragraphe absent ou doublé")
        elif manque := R.manquants("\n".join(c), jetons):
            trouvees.append(f"{rel} : jetons manquants au paragraphe {manque}")
    if k is not None and p is not None and k != p:
        trouvees.append("jumeaux divergents")
    trouvees += [f"{KICKOFF} : {f}" for f in fautes_kickoff(textes[KICKOFF], titre)]
    trouvees += [f"{PLANNING} : {f}" for f in fautes_planning(textes[PLANNING], titre)]
    return trouvees


def _textes() -> dict[str, str]:
    return {KICKOFF: _texte(KICKOFF), PLANNING: _texte(PLANNING)}


# --- (a) à (d) sur l'arbre vivant ---------------------------------------------------------


def test_membres_epingles() -> None:
    """Un compte laisserait substituer une surface à taille égale : les membres sont épinglés."""
    assert R.chemins(REGLE, GROUPE) == (KICKOFF, PLANNING)
    assert R.regle(REGLE)["bancs"] == (CE_BANC,)
    assert TITRE in JETONS, "le titre est un jeton : sa présence est exigée"
    assert len(JETONS) >= 2, "plancher de non-vacuité, jamais un compte"


def test_les_deux_skills_portent_le_paragraphe_jumeau_a_sa_place() -> None:
    assert fautes(_textes(), TITRE, JETONS) == []


@pytest.mark.parametrize("rel,prefixe", [(KICKOFF, PREFIXE_KICKOFF), (PLANNING, "")])
def test_chaque_jeton_est_dans_le_paragraphe_et_seul_a_manquer(rel: str, prefixe: str) -> None:
    c = corps(_texte(rel), prefixe, TITRE)
    assert c is not None and len(c) >= 2, f"{rel} : paragraphe absent, doublé ou vide"
    texte = "\n".join(c)
    for j in JETONS:
        mute = texte.replace(j, "")
        assert mute != texte, f"{j!r} absent du paragraphe de {rel}"
        assert R.manquants(mute, JETONS) == [j], f"{rel} privé de {j!r}"


# --- (e) chaque instrument rougit sur un mutant en mémoire ---------------------------------


def _lignes_et_bornes(texte: str, prefixe: str) -> tuple[list[str], int, int]:
    lignes = texte.splitlines()
    b = bornes(lignes, prefixe, TITRE)
    assert b is not None, "mutant posé sur un paragraphe introuvable"
    return lignes, b[0], b[1]


def _m_divergence(texte: str) -> str:
    return texte.replace("ailleurs : en série", "ailleurs : en parallèle", 1)


def _m_derniere_ligne_perdue(texte: str) -> str:
    lignes, _, fin = _lignes_et_bornes(texte, PREFIXE_KICKOFF)
    del lignes[fin - 1]
    return "\n".join(lignes)


def _m_8c_apres_9(texte: str) -> str:
    lignes, debut, fin = _lignes_et_bornes(texte, PREFIXE_KICKOFF)
    bloc, reste = lignes[debut:fin], lignes[:debut] + lignes[fin:]
    i = next(n for n, ligne in enumerate(reste) if ligne.startswith(ETAPE_APRES))
    return "\n".join(reste[:i + 1] + bloc + reste[i + 1:])


def _m_8c_renumerote(texte: str) -> str:
    return texte.replace("\n" + PREFIXE_KICKOFF + "**", "\n8d. **", 1)


def _m_8c_double(texte: str) -> str:
    lignes, debut, fin = _lignes_et_bornes(texte, PREFIXE_KICKOFF)
    return "\n".join(lignes[:fin] + lignes[debut:fin] + lignes[fin:])


def _m_jeton_retire(texte: str) -> str:
    lignes, debut, fin = _lignes_et_bornes(texte, PREFIXE_KICKOFF)
    j = JETONS[len(JETONS) // 2]
    lignes[debut:fin] = [ligne.replace(j, "") for ligne in lignes[debut:fin]]
    return "\n".join(lignes)


def _m_titre_retire(texte: str) -> str:
    return "\n".join(ligne for ligne in texte.splitlines() if ligne != NIVEAU_TITRE + TITRE)


def _m_ligne_vide_sous_le_titre(texte: str) -> str:
    return texte.replace(NIVEAU_TITRE + TITRE + "\n", NIVEAU_TITRE + TITRE + "\n\n", 1)


def _m_hors_etape_2(texte: str) -> str:
    lignes, debut, fin = _lignes_et_bornes(texte, "")
    bloc, reste = lignes[debut - 1:fin], lignes[:debut - 1] + lignes[fin:]
    i = next(n for n, ligne in enumerate(reste) if ligne.startswith(SECTION_ETAPE_2))
    return "\n".join(reste[:i] + bloc + [""] + reste[i:])


def _m_texte_avant_la_section_suivante(texte: str) -> str:
    lignes, _, fin = _lignes_et_bornes(texte, "")
    return "\n".join(lignes[:fin] + ["", "Une phrase glissée après le paragraphe."] + lignes[fin:])


MUTANTS: list[tuple[str, str, Callable[[str], str], str]] = [
    ("jumeau divergent d'un mot", PLANNING, _m_divergence, "jumeaux divergents"),
    ("dernière ligne perdue au kickoff", KICKOFF, _m_derniere_ligne_perdue, "jumeaux divergents"),
    ("jeton retiré du 8c", KICKOFF, _m_jeton_retire, "jetons manquants"),
    ("8c déplacé après 9", KICKOFF, _m_8c_apres_9, "qui le précède"),
    ("8c renuméroté 8d", KICKOFF, _m_8c_renumerote, "absent ou doublé"),
    ("8c doublé", KICKOFF, _m_8c_double, "absent ou doublé"),
    ("titre de section retiré", PLANNING, _m_titre_retire, "absent ou doublé"),
    ("ligne vide entre titre et paragraphe", PLANNING, _m_ligne_vide_sous_le_titre, "immédiatement"),
    ("paragraphe sorti de l'Étape 2", PLANNING, _m_hors_etape_2, "pas dans l'Étape 2"),
    ("texte glissé avant la section suivante", PLANNING, _m_texte_avant_la_section_suivante, "ne clôt pas"),
]


@pytest.mark.parametrize("cas,rel,muter,attendu", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_chaque_instrument_rougit_sur_son_mutant(
    cas: str, rel: str, muter: Callable[[str], str], attendu: str
) -> None:
    textes = _textes()
    mute = muter(textes[rel])
    assert mute != textes[rel], f"{cas} : le mutant n'a rien changé"
    trouvees = fautes({**textes, rel: mute}, TITRE, JETONS)
    assert any(attendu in f for f in trouvees), f"{cas} : {attendu!r} attendu, vu {trouvees}"
