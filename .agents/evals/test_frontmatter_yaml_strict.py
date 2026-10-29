"""Frontmatter YAML STRICT sur les surfaces d'instruction des hotes (alignement, lot L3 ; H-34 et S4).

POURQUOI. Copilot CLI 1.0.95 REFUSE au chargement tout frontmatter dont un scalaire nu contient `: `
(« mapping values are not allowed in this context », P1 et P4, 2026-10-12) : sept SKILL.md et les
deux `communicator` ont disparu SANS ERREUR cote modele (31 agents au lieu de 32). Claude Code, qui lit
un YAML plus laxiste, ne l'a jamais dit : aucun banc du depot ne lisait ces fichiers comme Copilot.

CE QUE CE BANC TIENT : chaque fichier OUVRE sur son frontmatter — `---` en LIGNE 1, puis un `---`
fermant (`ouverture_fautive`) — et aucune ligne de frontmatter `cle: valeur` dont la valeur est un
scalaire NU portant `: ` ou ` #` (la valeur se met entre guillemets doubles, chaine JSON), ni de valeur
entre guillemets MAL FERMEE (un `"` interne non echappe, MX7 de l'exec-critic L3) — sur TOUTES les
surfaces nommees ci-dessous, pas sur une liste choisie. CHAQUE entree de SURFACES doit trouver au moins
un fichier (`test_chaque_surface_juge_au_moins_un_fichier`) : un motif casse ou un dossier renomme ne
vide plus une surface EN SILENCE derriere un total global encore superieur a 100 (plan-critic it. 3, C3).

POURQUOI LA LIGNE 1 EST JUGEE A PART : `scalaires_nus_dangereux` rend `[]` sur un texte sans
frontmatter en ligne 1 — un bandeau `<!-- ... -->` pose AVANT le `---` passait donc pour PROPRE, par
silence. C'est la forme exacte qu'avaient les trois `vendor/*/SKILL.md` : Copilot, qui decouvre
SKILL.md aussi a profondeur 2 (mesure, AGENTS.md § Skills index), les signalait en « YAML malforme »
(T-01M4TK904Z5HY3A2XTCVC6XG5D).

`.kimi-code/agents/*.md` est JUGE depuis l'integration d'E-47 (50a26009, T-01M4RWBX0AE8T5V4TDNP6W9F1N) : son seul fautif
connu (`communicator.md`, borne epinglee sous S-01M4QWD5WD) y a ete corrige, comme le banc le demandait.

`.agents/skills/vendor/*/SKILL.md` est JUGE depuis T-01M4TK904Z5HY3A2XTCVC6XG5D (l'ancienne borne
`VENDOR_BORNE` est retiree) : du code tiers recopie, mais que Copilot lit, donc qu'il refuse.
`test_aucun_skill_md_de_copilot_n_echappe_au_banc` rougit si un SKILL.md a profondeur 1 ou 2 sous les
trois dossiers de skills de Copilot sort des surfaces jugees, et
`test_les_name_des_skill_md_de_copilot_sont_uniques` rougit si deux de ces SKILL.md declarent le meme
`name` (Copilot exige des noms uniques sur ses trois dossiers, AGENTS.md § Cross-agent surfaces) :
d'ou le patch local `name: playwright-best-practices-vendor`, ecrit dans le bandeau du fichier vendor.
Les `.toml` de Codex ne sont pas du YAML. Ce banc ne PROUVE PAS que Copilot charge ce qu'il juge valide
(seul le runtime le dit) ; l'unicite des noms de DOSSIER y est jugee SOUS BORNE nommee
(`COLLISIONS_DOSSIER_BORNEES`, decision pilote en attente) ; et il ne lit pas le YAML avec PyYAML,
absent de la CI (`test_forge_ruleset_model.py`, en-tete) : « strict » veut dire les formes que Copilot
a refusees.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SURFACES = (
    ".agents/skills/*/SKILL.md",
    ".claude/skills/*/SKILL.md",
    ".github/skills/*/SKILL.md",
    ".claude/agents/*.md",
    ".claude/commands/*.md",
    ".claude/rules/*.md",
    ".github/agents/*.agent.md",
    ".github/instructions/*.md",
    ".gemini/agents/*.md",
    ".kimi-code/agents/*.md",  # remis par l'integration E-47 (50a26009) : seul fautif connu corrige
    ".agents/skills/vendor/*/SKILL.md",  # profondeur 2, lue par Copilot (T-01M4TK904Z5HY3A2XTCVC6XG5D)
)
# Les trois dossiers de skills de Copilot (AGENTS.md § Cross-agent surfaces), lus a profondeur 1 ET 2.
DOSSIERS_SKILLS_COPILOT = (".agents/skills", ".claude/skills", ".github/skills")
# BORNE NOMMEE, jamais silencieuse : les trois noms de DOSSIER vendor/<nom>/ repetent ceux des pointeurs de
# profondeur 1 sous .agents/skills/, alors que Copilot veut aussi des noms de dossier uniques. En attente
# de la decision pilote (sortir les vendor de la decouverte). Une QUATRIEME collision rougit, et la
# disparition d'une des trois aussi : la borne se retire avec la decision, jamais en silence.
COLLISIONS_DOSSIER_BORNEES = {"composition-patterns", "playwright-best-practices", "react-best-practices"}
_CLE_VALEUR = re.compile(r"^([A-Za-z_][\w-]*): (.+)$")
_OUVERTURES_SURES = ('"', "'", "[", "{", "|", ">", "&", "*", "!", "%", "@", "`", "#")


def _guillemets_mal_fermes(valeur: str) -> bool:
    """Une valeur OUVERTE par un guillemet doit etre UN scalaire cite complet, sur sa ligne.

    Double : une chaine JSON (sous-ensemble strict du scalaire YAML double, la forme que ce banc exige) —
    un `"` interne non echappe la ferme trop tot et Copilot refuse le fichier (exec-critic L3, MX7).
    Simple : fermee par `'`, une apostrophe interne seulement doublee (`''`)."""
    if valeur.startswith('"'):
        try:
            return not isinstance(json.loads(valeur), str)
        except ValueError:
            return True
    if valeur.startswith("'"):
        return len(valeur) < 2 or not valeur.endswith("'") or "'" in valeur[1:-1].replace("''", "")
    return False


def ouverture_fautive(texte: str) -> str | None:
    """La faute d'OUVERTURE du frontmatter, ou None : `---` doit etre la LIGNE 1 (rien avant, ni
    bandeau, ni ligne vide, ni BOM) et un `---` fermant doit suivre."""
    lignes = texte.replace("\r\n", "\n").split("\n")
    if lignes[0] != "---":
        return f"ligne 1 = {lignes[0][:60]!r}, pas '---'"
    if "---" not in lignes[1:]:
        return "frontmatter ouvert en ligne 1, jamais ferme par '---'"
    return None


def nom_declare(texte: str) -> str | None:
    """Le `name` de premier niveau du frontmatter ouvert en ligne 1 (guillemets retires), ou None."""
    lignes = texte.replace("\r\n", "\n").split("\n")
    if ouverture_fautive(texte):
        return None
    for ligne in lignes[1:lignes.index("---", 1)]:
        m = re.match(r"^name:[ \t]*(.*?)[ \t]*$", ligne)
        if m:
            valeur = m.group(1)
            if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                valeur = valeur[1:-1]
            return valeur or None
    return None


def scalaires_nus_dangereux(texte: str) -> list[tuple[int, str]]:
    """(ligne, cle) de chaque scalaire NU du frontmatter portant `: ` ou ` #`, ET de chaque scalaire
    entre guillemets mal ferme (`_guillemets_mal_fermes`)."""
    lignes = texte.replace("\r\n", "\n").split("\n")
    if not lignes or lignes[0] != "---":
        return []
    try:
        fin = lignes.index("---", 1)
    except ValueError:
        return []
    fautes = []
    for n, ligne in enumerate(lignes[1:fin], start=2):
        m = _CLE_VALEUR.match(ligne)
        if not m:
            continue
        valeur = m.group(2).strip()
        if _guillemets_mal_fermes(valeur):
            fautes.append((n, m.group(1)))
            continue
        if valeur.startswith(_OUVERTURES_SURES):
            continue
        if ": " in valeur or " #" in valeur:
            fautes.append((n, m.group(1)))
    return fautes


def _fichiers() -> list[Path]:
    return sorted({p for motif in SURFACES for p in ROOT.glob(motif) if p.is_file()})


@pytest.mark.parametrize("motif", SURFACES)
def test_chaque_surface_juge_au_moins_un_fichier(motif):
    """Le total global (> 100) ne voit pas une surface VIDÉE : chaque motif doit, seul, trouver un fichier."""
    trouves = [p for p in ROOT.glob(motif) if p.is_file()]
    assert trouves, f"surface vide : {motif!r} ne juge AUCUN fichier (motif casse ou dossier deplace)"


def test_chaque_fichier_ouvre_sur_son_frontmatter_en_ligne_1():
    """PORTEE LARGE, VOULUE ET NOMMEE : la regle « `---` en ligne 1 » est jugee sur TOUTES les SURFACES,
    y compris `.claude/commands/*.md`, `.claude/rules/*.md` et `.github/instructions/*.md`, ou le
    frontmatter est FACULTATIF cote hote (un fichier sans frontmatter y est charge quand meme). Ce n'est
    donc pas une exigence d'hote sur ces trois surfaces mais une convention du depot, mesuree tenue
    partout (T-01M4TK904Z5HY3A2XTCVC6XG5D) : elle garantit que `scalaires_nus_dangereux`, qui se tait sans
    frontmatter en ligne 1, juge reellement chaque fichier. Un futur fichier SANS frontmatter sur l'une
    de ces trois surfaces rougit ici : le retirer de la regle est une decision, pas un correctif."""
    fichiers = _fichiers()
    assert len(fichiers) > 100, "population vide ou tronquee : le banc ne juge rien"
    fautifs = {}
    for p in fichiers:
        faute = ouverture_fautive(p.read_text(encoding="utf-8"))
        if faute:
            fautifs[p.relative_to(ROOT).as_posix()] = faute
    assert fautifs == {}, fautifs


def test_aucun_scalaire_nu_dangereux_sur_les_surfaces_des_hotes():
    fichiers = _fichiers()
    assert len(fichiers) > 100, "population vide ou tronquee : le banc ne juge rien"
    fautifs = {}
    for p in fichiers:
        f = scalaires_nus_dangereux(p.read_text(encoding="utf-8"))
        if f:
            fautifs[p.relative_to(ROOT).as_posix()] = f
    assert fautifs == {}, fautifs


def test_le_detecteur_mord_et_se_tait_ou_il_faut():
    nu = "---\nname: x\ndescription: Use when: the board moves\n---\n"
    assert scalaires_nus_dangereux(nu) == [(3, "description")]
    assert scalaires_nus_dangereux('---\nname: x\ndescription: "Use when: the board moves"\n---\n') == []
    assert scalaires_nus_dangereux("---\nname: x\ndescription: Use it # fast\n---\n") == [(3, "description")]
    assert scalaires_nus_dangereux("---\nname: x\ndescription: Use it\n---\ncorps: a: b\n") == []
    assert scalaires_nus_dangereux("pas de frontmatter\ndescription: a: b\n") == []
    # MX7 : un guillemet interne non echappe ferme la chaine trop tot ; echappe, il passe.
    assert scalaires_nus_dangereux('---\ndescription: "Regime "ATTERRISSAGE" — fin"\n---\n') == [(2, "description")]
    assert scalaires_nus_dangereux('---\ndescription: "Regime \\"ATTERRISSAGE\\" — fin"\n---\n') == []
    assert scalaires_nus_dangereux('---\ndescription: "jamais fermee\n---\n') == [(2, "description")]
    assert scalaires_nus_dangereux("---\ndescription: 'it''s fine'\n---\n") == []
    assert scalaires_nus_dangereux("---\ndescription: 'it's broken'\n---\n") == [(2, "description")]
    assert scalaires_nus_dangereux('---\ntools: ["read", "shell"]\n---\n') == []


def test_l_ouverture_mord_et_se_tait_ou_il_faut():
    # La forme exacte des trois vendor/*/SKILL.md avant T-01M4TK904Z5HY3A2XTCVC6XG5D : bandeau, PUIS `---`.
    bandeau_avant = "<!-- VENDORED THIRD-PARTY REFERENCE\n     pinned : deadbeef\n-->\n---\nname: x\n---\ncorps\n"
    assert ouverture_fautive(bandeau_avant) is not None
    assert scalaires_nus_dangereux(bandeau_avant) == []  # le silence que ce test-ci rattrape
    assert ouverture_fautive("\n---\nname: x\n---\n") is not None
    assert ouverture_fautive(chr(0xFEFF) + "---\nname: x\n---\n") is not None  # BOM avant le `---`
    assert ouverture_fautive("---\nname: x\ndescription: y\n") is not None
    assert ouverture_fautive("pas de frontmatter\n") is not None
    # Bandeau deplace APRES le `---` fermant : la forme corrigee passe.
    assert ouverture_fautive("---\nname: x\n---\n<!-- VENDORED -->\ncorps\n") is None
    assert ouverture_fautive("---\r\nname: x\r\n---\r\n") is None


def _skill_md_de_copilot() -> set[Path]:
    """Tout SKILL.md a profondeur 1 ou 2 sous les trois dossiers de skills que Copilot lit."""
    return {p for d in DOSSIERS_SKILLS_COPILOT for motif in ("*/SKILL.md", "*/*/SKILL.md")
            for p in (ROOT / d).glob(motif) if p.is_file()}


def test_aucun_skill_md_de_copilot_n_echappe_au_banc():
    """Copilot lit SKILL.md a profondeur 1 ET 2 sous ses trois dossiers : aucun n'echappe aux surfaces."""
    juges = set(_fichiers())
    vus = _skill_md_de_copilot()
    profondeur_2 = {p for p in vus if len(p.relative_to(ROOT).parts) == 5}
    assert len(profondeur_2) >= 3, "les trois vendor/*/SKILL.md (profondeur 2) ne sont plus vus"
    hors_banc = sorted(p.relative_to(ROOT).as_posix() for p in vus - juges)
    assert hors_banc == [], f"SKILL.md lus par Copilot mais JAMAIS juges : {hors_banc}"


def test_les_name_des_skill_md_de_copilot_sont_uniques():
    """Deux SKILL.md lus par Copilot (profondeur 1 ou 2, trois dossiers) ne declarent jamais le meme `name`."""
    porteurs: dict[str, list[str]] = {}
    sans_nom = []
    for p in sorted(_skill_md_de_copilot()):
        rel = p.relative_to(ROOT).as_posix()
        nom = nom_declare(p.read_text(encoding="utf-8"))
        if nom is None:
            sans_nom.append(rel)
        else:
            porteurs.setdefault(nom.casefold(), []).append(rel)
    assert sum(len(v) for v in porteurs.values()) > 40, "population vide ou tronquee : le banc ne juge rien"
    assert sans_nom == [], f"SKILL.md sans `name` lisible en frontmatter : {sans_nom}"
    doublons = {nom: rels for nom, rels in porteurs.items() if len(rels) > 1}
    assert doublons == {}, f"`name` declare plusieurs fois sous les dossiers de Copilot : {doublons}"


def test_les_noms_de_dossier_des_skill_md_de_copilot_sont_uniques():
    """Le nom de DOSSIER d'un SKILL.md lu par Copilot est unique, hors COLLISIONS_DOSSIER_BORNEES."""
    vus: dict[str, list[str]] = {}
    for p in sorted(_skill_md_de_copilot()):
        vus.setdefault(p.parent.name.casefold(), []).append(p.relative_to(ROOT).as_posix())
    assert sum(len(r) for r in vus.values()) > 40, "population vide ou tronquee : le banc ne juge rien"
    doublons = {n for n, r in vus.items() if len(r) > 1}
    assert doublons == COLLISIONS_DOSSIER_BORNEES, (
        f"collisions de DOSSIER : {sorted(doublons)} ; bornees : {sorted(COLLISIONS_DOSSIER_BORNEES)} — "
        + "; ".join(f"{n} = {vus[n]}" for n in sorted(doublons ^ COLLISIONS_DOSSIER_BORNEES) if n in vus))


def test_nom_declare_lit_le_frontmatter_et_lui_seul():
    assert nom_declare("---\nname: alpha\ndescription: x\n---\n") == "alpha"
    assert nom_declare('---\nname: "alpha"\n---\n') == "alpha"
    assert nom_declare("---\nname: 'alpha'\n---\n") == "alpha"
    assert nom_declare("---\ndescription: x\n---\nname: corps\n") is None  # le corps ne compte pas
    assert nom_declare("---\nmetadata:\n  name: imbrique\n---\n") is None  # seul le 1er niveau compte
    assert nom_declare("<!-- bandeau -->\n---\nname: alpha\n---\n") is None  # ouverture fautive
    assert nom_declare("---\nname:\n---\n") is None
