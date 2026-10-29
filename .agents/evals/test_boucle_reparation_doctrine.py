"""La boucle de réparation bornée est écrite sur chaque surface qui la prescrit (T-01M5BZC0QVFN68QYEE3SG87FCJ).

Ordre pilote S-01M5D9T3AZS3S10YD284G0RJ78 : quand la porte de la clôture rougit, la réparation
tient en 3 tentatives au plus, s'arrête si les erreurs augmentent, et escalade au pilote par
`communicator`. AUCUN CODE ne tient cette boucle — elle est de la PROSE, interprétée par le LLM de
l'hôte comme toute la chaîne ; ce banc tient le TEXTE, rien d'autre.

CE QU'IL JUGE, ZÉRO LLM, sur l'arbre réel :
  (B1) les SIX invariants (`INVARIANTS`) sur chacune des trois surfaces SOURCES
       (`.agents/skills/kickoff/SKILL.md`, `commands/kickoff.md`,
       `.agents/skills/verification-discipline/SKILL.md`) ET sur les deux RENDUS de
       `commands/kickoff.md` (`.claude/commands/kickoff.md`,
       `.agents/skills/source-command-kickoff/SKILL.md`) — lus tels qu'ils sont sur le disque,
       jamais régénérés ici (`render_hosts.py --check` est le banc de la dérive) ;
  (B2) le nombre de tentatives : toute forme « <N> tentatives » d'une surface dit 3, et chaque
       surface en porte au moins une — « 4 tentatives » rougit ;
  (B3) la SECTION de la skill : son titre une seule fois, juste après l'étape 12 (avant
       « ONE REVIEW WAVE PER DELIVERY »), ses six points et ses gestes (`GESTES_SECTION`) ;
  (B4) les RENVOIS : l'ordre de clôture de l'étape 11 renvoie à la section, et les quatre autres
       surfaces la nomment par son titre ;
  (B5) des témoins synthétiques, indépendants de l'arbre : chaque invariant retiré, ou le
       nombre changé, fait rougir le contrôleur en nommant CE défaut.

CE QU'IL NE VOIT PAS : qu'un exécuteur JOUE la boucle — aucun code ne compte les tentatives, ne
refuse la 4e ni ne lit la trace `kind=delta` ; une paraphrase qui garde les jetons mais en
renverse le sens (« jamais d'arrêt si les erreurs augmentent ») reste verte ; `/night` n'est
jugé ici que par la mention de sa sortie de portée, jamais dans `.agents/skills/night/SKILL.md`.
Pas d'entrée au registre de doctrine des bancs (T-01M4V7R89VZ5SP3NXZ32SNNDZ2) : ce banc porte
ses jetons lui-même, comme `test_direct_mode_doctrine.py`, et n'importe pas le registre.

VOYAGE : les cinq surfaces partent chez l'adoptant (`.template-exclude` n'en strippe aucune) ; ce
banc y juge donc aussi, sans saut.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKILL = ".agents/skills/kickoff/SKILL.md"
COMMANDE = "commands/kickoff.md"
VERIFICATION = ".agents/skills/verification-discipline/SKILL.md"
RENDUS = (".claude/commands/kickoff.md", ".agents/skills/source-command-kickoff/SKILL.md")
SOURCES = (SKILL, COMMANDE, VERIFICATION)
SURFACES = SOURCES + RENDUS

#: Les six invariants de la règle, comparés sur le texte aux blancs pliés et en casse pliée.
INVARIANTS = (
    "3 tentatives",
    "arrêt si les erreurs augmentent",
    "k_n > k_(n-1)",
    "escalade `communicator`",
    "`--kind delta` avant de rejouer",
    "une porte tuée n'est pas une porte rouge",
    "`/night` hors portée",
)
TITRE = "La boucle de réparation bornée (porte rouge)"
TITRE_SECTION = f"**{TITRE}**"
APRES = "applied."  # la fin de l'étape 12 de la skill
AVANT = "**ONE REVIEW WAVE PER DELIVERY"
ORDRE = "the order is `work → review → FIX → gate → done`"
RENVOI_FENETRE = 400
POINTS = ("(1) **Déclencheur.**", "(2) **Une tentative n**", "(3) **Bornes d'arrêt**",
          "(4) **Escalade**", "(5) **Portée.**", "(6) **Bornes, dites.**")
GESTES_SECTION = (
    "python .agents/bin/specs.py add --task T-NNN --kind delta \"porte rouge — tentative <n>/3 :",
    "python .agents/bin/tasks.py block T-NNN --note \"porte rouge x<n>",
    "prolongation boucle de réparation : tentative <n+1>",
    "python .agents/bin/tasks.py unblock T-NNN",
    "git revert --no-edit <sha>",
    "git revert -m 1",
    "CADRE_GATE_FAIL_FAST=0",
    "security-code-review",
    "Vos options",
    "Recommandation",
    "Sans réponse : la tâche reste bloquée, rien n'est poussé",
    "le push attend un SHA vert",
    "PRÉEXISTANT",
    "Jamais une 4e tentative sans la prolongation du pilote",
)
NOMBRE = re.compile(r"\b(\d+)\s+tentatives\b", re.IGNORECASE)


def plier(texte: str) -> str:
    """Blancs pliés : une phrase coupée sur deux lignes compte."""
    return " ".join(texte.split())


def manquants(texte: str, attendus: tuple[str, ...] = INVARIANTS) -> list[str]:
    """Les jetons de `attendus` absents de `texte` (blancs et casse pliés), dans leur ordre."""
    plat = plier(texte).casefold()
    return [j for j in attendus if plier(j).casefold() not in plat]


def nombres(texte: str) -> list[int]:
    """Chaque `<N>` d'une forme « <N> tentatives » du texte."""
    return [int(n) for n in NOMBRE.findall(plier(texte))]


def fautes(textes: dict[str, str]) -> list[str]:
    """`<surface> : <faute>` pour chaque invariant manquant et chaque nombre de tentatives ≠ 3."""
    out = []
    for rel, t in textes.items():
        if m := manquants(t):
            out.append(f"{rel} : {m}")
        n = nombres(t)
        if not n or any(x != 3 for x in n):
            out.append(f"{rel} : tentatives {n} au lieu de [3, …]")
    return out


def section(texte: str) -> str:
    """La section de la skill, aplatie : de son titre à « ONE REVIEW WAVE » ; vide si absente."""
    plat = plier(texte)
    i = plat.find(TITRE_SECTION)
    j = plat.find(plier(AVANT), i) if i >= 0 else -1
    return plat[i:j] if i >= 0 and j >= 0 else ""


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class BoucleReparationSurfacesTests(unittest.TestCase):
    maxDiff = None  # le rouge nomme CHAQUE surface et ses jetons manquants

    def test_b1_b2_chaque_surface_porte_les_six_invariants_et_3_tentatives(self) -> None:
        """← un invariant retiré d'une surface (source ou rendu) ; ← « 4 tentatives »."""
        self.assertEqual(fautes({rel: lire(rel) for rel in SURFACES}), [])

    def test_b3_la_section_de_la_skill(self) -> None:
        """← titre absent ou doublé, section déplacée, un point ou un geste perdu."""
        texte = lire(SKILL)
        plat = plier(texte)
        self.assertEqual(plat.count(TITRE_SECTION), 1, "titre de la section absent ou doublé")
        i = plat.find(TITRE_SECTION)
        self.assertTrue(plat[:i].rstrip().endswith(APRES), "la section ne suit plus l'étape 12")
        corps = section(texte)
        self.assertTrue(corps, "section sans fin (« ONE REVIEW WAVE PER DELIVERY » absent après elle)")
        self.assertEqual(manquants(corps), [], "invariants absents de la section")
        self.assertEqual(manquants(corps, POINTS), [], "points de la section")
        self.assertEqual(manquants(corps, GESTES_SECTION), [], "gestes de la section")

    def test_b4_les_renvois(self) -> None:
        """← l'ordre de clôture ne renvoie plus à la section ; ← une surface ne la nomme plus."""
        plat = plier(lire(SKILL))
        i = plat.find(ORDRE)
        self.assertGreaterEqual(i, 0, "ordre de clôture introuvable dans la skill")
        self.assertTrue(f"§ {TITRE}" in plat[i: i + RENVOI_FENETRE], "l'ordre de clôture ne renvoie pas à la section")
        for rel in (COMMANDE, VERIFICATION) + RENDUS:
            plat = plier(lire(rel))
            self.assertTrue(f"{SKILL}` § {TITRE}" in plat, f"{rel} ne nomme pas la section")

    def test_b4_les_rendus_portent_la_phrase_de_la_source(self) -> None:
        """← un rendu qui a dérivé de `commands/kickoff.md` sur la phrase de la boucle."""
        source = plier(lire(COMMANDE))
        debut = source.find("If the gate goes red: the boucle de réparation bornée")
        self.assertGreaterEqual(debut, 0, "phrase de la boucle absente de la source")
        fin = source.find(f"§ {TITRE}.", debut)
        self.assertGreater(fin, debut)
        phrase = source[debut: fin + len(f"§ {TITRE}.")]
        for rel in RENDUS:
            self.assertTrue(phrase in plier(lire(rel)), f"{rel} ne porte pas la phrase de la source")


class BoucleReparationTemoinsTests(unittest.TestCase):
    """B5 — le contrôleur rougit sur chaque défaut, sans lire l'arbre."""

    PLEIN = " ".join(INVARIANTS) + " Jamais une 4e tentative."

    def test_un_texte_plein_passe(self) -> None:
        self.assertEqual(fautes({"s.md": self.PLEIN}), [])
        self.assertEqual(fautes({"s.md": self.PLEIN.upper().replace("K_N > K_(N-1)", "k_n > k_(n-1)")}), [])

    def test_chaque_invariant_retire_rougit_en_le_nommant(self) -> None:
        for j in INVARIANTS:
            prive = self.PLEIN.replace(j, "")
            out = fautes({"s.md": prive})
            self.assertTrue(out and out[0] == f"s.md : {[j]}", (j, out))

    def test_un_autre_nombre_de_tentatives_rougit(self) -> None:
        for n in ("4", "2", "30"):
            out = fautes({"s.md": self.PLEIN.replace("3 tentatives", f"{n} tentatives")})
            self.assertIn(f"s.md : tentatives [{int(n)}] au lieu de [3, …]", out, n)
        out = fautes({"s.md": self.PLEIN + " puis 4 tentatives"})
        self.assertEqual(out, ["s.md : tentatives [3, 4] au lieu de [3, …]"])

    def test_une_phrase_coupee_sur_deux_lignes_compte(self) -> None:
        coupe = self.PLEIN.replace("arrêt si les erreurs augmentent", "arrêt si les\n   erreurs augmentent")
        self.assertEqual(fautes({"s.md": coupe}), [])

    def test_section_absente_ou_sans_fin_est_vide(self) -> None:
        self.assertEqual(section("rien"), "")
        self.assertEqual(section(f"{TITRE_SECTION} sans fin"), "")
        self.assertTrue(section(f"{TITRE_SECTION} corps {AVANT}**").startswith(TITRE_SECTION))


if __name__ == "__main__":
    unittest.main()
