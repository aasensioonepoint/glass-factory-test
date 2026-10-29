"""La source unique `agents/` + `commands/` est DITE sur chaque surface de doctrine qui voyage
(T-01M5C1P8VY9DR179A05MKPC6J6, décision pilote S-01M5C01EAKQACKA27PNH804CR3).

Le CODE tient le rendu (`.agents/bin/render_hosts.py --check`, `.agents/bin/test_render_hosts.py`) ;
ce banc tient sa PROSE, zéro LLM, sur l'arbre réel :
  (U1) `AGENTS.md` § Cross-agent surfaces, `CLAUDE.md`, `README-CLAUDE.md`, `README-OTHER-HOSTS.md`
       et `.github/copilot-instructions.md` disent que les défs sont RENDUES depuis `agents/`, les
       commandes depuis `commands/`, et qu'un rendu n'est JAMAIS édité à la main ;
  (U2) dans `AGENTS.md` § Cross-agent surfaces, chacune des cinq lignes d'hôte (Claude Code, Codex,
       GitHub Copilot, Gemini CLI, Kimi Code) dit son dossier d'agents rendu depuis `agents/` ;
  (U3) la même section porte une ligne `**Cursor**` qui la dit CIBLE DÉRIVÉE, `cadre.config.HOTES`
       inchangé, et NON MESURÉ ;
  (U4) la boucle de réparation bornée : `CLAUDE.md`, `.github/copilot-instructions.md`,
       `AGENTS.md` et `README-CLAUDE.md` portent « 3 tentatives » au moins une fois, et toute forme
       « <N> tentatives » y dit 3 — « 4 tentatives » rougit ;
  (U5) des témoins synthétiques, en mémoire : chaque jeton retiré d'une surface, « NON MESURÉ »
       retiré, ou le nombre changé, fait rougir le contrôleur en nommant CE défaut.

Jetons comparés en casse pliée, blancs pliés. CE QU'IL NE VOIT PAS : qu'un rendu soit réellement
à jour (c'est `render_hosts.py --check`) ; qu'un agent n'édite pas un rendu à la main (aucune garde
ne le refuse : prose) ; qu'une paraphrase garde les jetons en renversant le sens (« never edited by
hand » sous une négation passe) ; que Cursor lise quoi que ce soit ; les autres surfaces qui citent
`.claude/agents/` (`git grep` les trouve, ce banc ne les énumère pas).

VOYAGE : les cinq surfaces partent chez l'adoptant (`.template-exclude` n'en strippe aucune) ; ce
banc y juge donc aussi, sans saut.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

AGENTS = "AGENTS.md"
CLAUDE = "CLAUDE.md"
README_CLAUDE = "README-CLAUDE.md"
README_HOTES = "README-OTHER-HOSTS.md"
COPILOT = ".github/copilot-instructions.md"
SURFACES = (AGENTS, CLAUDE, README_CLAUDE, README_HOTES, COPILOT)

#: (U1) les jetons de chaque surface — la langue de la surface, jamais traduite ici.
JETONS = {
    AGENTS: ("rendu depuis `agents/`", "depuis `agents/` et `commands/`", "jamais édités à la main"),
    CLAUDE: ("rendered from `agents/`", "rendered from `commands/`", "never edited by hand"),
    README_CLAUDE: ("rendered from `agents/`", "rendered from `commands/`", "never edited by hand"),
    README_HOTES: ("rendered from `agents/`", "rendered from `commands/`", "never edited by hand"),
    COPILOT: ("rendered from `agents/`", "rendered from `commands/", "never edited by hand"),
}
#: (U2) les cinq lignes d'hôte de la section, par leur ouverture exacte.
LIGNES_HOTE = ("- **Claude Code**", "- **Codex**", "- **GitHub Copilot**", "- **Gemini CLI**", "- **Kimi Code**")
JETON_HOTE = "depuis `agents/`"
#: (U3) la ligne Cursor.
LIGNE_CURSOR = "- **Cursor**"
JETONS_CURSOR = ("CIBLE DÉRIVÉE", "`cadre.config.HOTES` inchangé", "NON MESURÉ")
#: (U4) le nombre de tentatives et les surfaces qui le portent.
TENTATIVES = 3
SURFACES_BOUCLE = (CLAUDE, COPILOT, AGENTS, README_CLAUDE)
FORME_TENTATIVES = re.compile(r"\b(\d+)\s+tentatives\b", re.IGNORECASE)
TITRE_SECTION = "## Cross-agent surfaces"


def plier(texte: str) -> str:
    """Casse et blancs pliés : une coupure de ligne ou une majuscule ne cachent pas un jeton."""
    return " ".join(texte.split()).casefold()


def section_surfaces(texte: str) -> str:
    """`AGENTS.md` § Cross-agent surfaces, jusqu'au titre `## ` suivant ; vide si absente."""
    debut = texte.find(TITRE_SECTION)
    if debut < 0:
        return ""
    suite = texte.find("\n## ", debut + len(TITRE_SECTION))
    return texte[debut:] if suite < 0 else texte[debut:suite]


def ligne_ouvrant(section: str, ouverture: str) -> str | None:
    for ligne in section.splitlines():
        if ligne.startswith(ouverture):
            return ligne
    return None


def defauts(textes: dict[str, str]) -> list[str]:
    """Tous les défauts des cinq surfaces, chacun nommé `<surface> : <défaut>`."""
    sortie: list[str] = []
    for surface in SURFACES:
        if surface not in textes:
            sortie.append(f"{surface} : surface absente")
    if sortie:
        return sortie
    section = section_surfaces(textes[AGENTS])
    if not section:
        return [f"{AGENTS} : § Cross-agent surfaces introuvable — le contrôle serait aveugle"]
    portees = {s: (section if s == AGENTS else textes[s]) for s in SURFACES}
    for surface, jetons in JETONS.items():
        plie = plier(portees[surface])
        for jeton in jetons:
            if plier(jeton) not in plie:
                sortie.append(f"{surface} : jeton absent « {jeton} »")
    for ouverture in LIGNES_HOTE:
        ligne = ligne_ouvrant(section, ouverture)
        if ligne is None:
            sortie.append(f"{AGENTS} : ligne d'hôte absente « {ouverture} »")
        elif plier(JETON_HOTE) not in plier(ligne):
            sortie.append(f"{AGENTS} : la ligne « {ouverture} » ne dit pas son dossier « {JETON_HOTE} »")
    cursor = ligne_ouvrant(section, LIGNE_CURSOR)
    if cursor is None:
        sortie.append(f"{AGENTS} : ligne Cursor absente")
    else:
        for jeton in JETONS_CURSOR:
            if plier(jeton) not in plier(cursor):
                sortie.append(f"{AGENTS} : la ligne Cursor ne dit pas « {jeton} »")
    for surface in SURFACES_BOUCLE:
        nombres = [int(n) for n in FORME_TENTATIVES.findall(textes[surface])]
        if TENTATIVES not in nombres:
            sortie.append(f"{surface} : « {TENTATIVES} tentatives » absent")
        for n in sorted(set(nombres) - {TENTATIVES}):
            sortie.append(f"{surface} : « {n} tentatives » écrit, la règle dit {TENTATIVES}")
    return sortie


def lire_arbre(racine: Path = ROOT) -> dict[str, str]:
    return {s: (racine / s).read_text(encoding="utf-8") for s in SURFACES if (racine / s).is_file()}


class SourceUniqueDoctrine(unittest.TestCase):

    def test_U1_U4_arbre_reel(self):
        fautes = defauts(lire_arbre())
        self.assertEqual(fautes, [], "\n".join(fautes))

    # --- (U5) témoins synthétiques, en mémoire, sur les textes réels ---------------------------

    def _mute(self, surface: str, avant: str, apres: str) -> list[str]:
        textes = lire_arbre()
        self.assertIn(avant, textes[surface], f"témoin aveugle : « {avant} » absent de {surface}")
        textes[surface] = textes[surface].replace(avant, apres)
        return defauts(textes)

    def test_U5_phrase_retiree_d_une_surface(self):
        fautes = self._mute(README_HOTES, "never edited by hand", "edited")
        self.assertIn(f"{README_HOTES} : jeton absent « never edited by hand »", fautes)

    def test_U5_commande_rendue_retiree(self):
        fautes = self._mute(CLAUDE, "rendered from `commands/`", "kept in `.claude/commands/`")
        self.assertIn(f"{CLAUDE} : jeton absent « rendered from `commands/` »", fautes)

    def test_U5_ligne_d_hote_sans_son_rendu(self):
        fautes = self._mute(AGENTS, "`.codex/agents/` (rendu depuis `agents/`)", "`.codex/agents/`")
        self.assertIn(f"{AGENTS} : la ligne « - **Codex** » ne dit pas son dossier « {JETON_HOTE} »", fautes)

    def test_U5_non_mesure_retire_de_cursor(self):
        fautes = self._mute(AGENTS, "que Cursor lise ces fichiers est NON MESURÉ", "Cursor lit ces fichiers")
        self.assertIn(f"{AGENTS} : la ligne Cursor ne dit pas « NON MESURÉ »", fautes)

    def test_U5_quatre_tentatives(self):
        fautes = self._mute(COPILOT, "3 tentatives", "4 tentatives")
        self.assertIn(f"{COPILOT} : « 4 tentatives » écrit, la règle dit 3", fautes)
        self.assertIn(f"{COPILOT} : « 3 tentatives » absent", fautes)

    def test_U5_section_absente_rend_le_controle_bruyant(self):
        fautes = self._mute(AGENTS, TITRE_SECTION, "## Surfaces")
        self.assertEqual(fautes, [f"{AGENTS} : § Cross-agent surfaces introuvable — le contrôle serait aveugle"])

    def test_U5_jeton_hors_section_ne_compte_pas(self):
        """Le jeton d'AGENTS.md est lu dans la SECTION : le recopier ailleurs ne la répare pas."""
        textes = lire_arbre()
        section = section_surfaces(textes[AGENTS])
        textes[AGENTS] = textes[AGENTS].replace(section, section.replace("jamais édités à la main", "édités"))
        textes[AGENTS] += "\njamais édités à la main\n"
        self.assertIn(f"{AGENTS} : jeton absent « jamais édités à la main »", defauts(textes))


if __name__ == "__main__":
    unittest.main()
