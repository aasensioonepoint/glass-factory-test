#!/usr/bin/env python3
"""LE BLOC AUTEUR DE `terraform-deployer` EST DIT AU DOCUMENTER — T-01M52X1W3WPKCWX1DC36NMKJB6 (passe CORR-2,
2026-10-19).

POURQUOI. Sur une tâche IaC le slot dev est `terraform-deployer` (AGENTS.md, « On an IaC task … the dev slot is
`terraform-deployer` »), et sa déf fixe, sur les cinq hôtes, le bloc de sortie AUTEUR
`CHANGESET:/FILES:/IaC:/NOT DONE:`. Le documenter reçoit sous l'en-tête `Dev agent's diff summary (if
post-change):` le bloc de CHAQUE passe dev ; les trois sites que la session EXÉCUTE pour /kickoff nomment donc ce
bloc, juste après la clause de compaction (« … with the pass number ») : `.claude/commands/kickoff.md` étape 7,
`.agents/skills/kickoff/SKILL.md` étape 11, `.github/copilot-instructions.md` étape 10.

POURQUOI UN BANC À PART. Le banc voisin (`test_docs_only_route_contract.py`, qui tient le reste de ces trois
étapes) est au plafond de son cliquet de longueur (`test_python_file_length.py`, 6113 lignes) : il ne grandit
plus. Celui-ci est autonome — il ne l'importe pas — et ne relit que les deux ancres dont il a besoin.

CE QUI EST TENU, par site : (1) l'invocation du documenter, trouvée par son ancre ; (2) la fin de la clause de
compaction, à au plus FENETRE caractères après elle ; (3) la phrase AUTEUR, à au plus ECART caractères après
cette clause. Contrôles négatifs sur une COPIE mutée de chaque site : phrase retirée, phrase éloignée, ancre
retirée, clause retirée → rouge. Et les cinq défs `terraform-deployer` portent bien, en début de ligne, les
quatre champs que la phrase leur prête (une phrase qui nommerait un bloc qu'aucune déf ne fixe serait un mensonge
tenu vert).

CE QUI N'EST PAS TENU (bornes) : le contenu réel d'un rendu de `terraform-deployer` ; les sites de nuit
(`.claude/commands/night.md`, `.agents/skills/night/SKILL.md`), qui ne portent pas la phrase et ne sont pas jugés
ici ; un site ajouté après ce relevé (relevé : `git grep -n "AUTEUR block on every host"`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Mesuré à l'écriture : de la fin de l'ancre à la clause de compaction, 1286 à 1351 caractères.
FENETRE = 1600
#: De la fin de la clause à la phrase AUTEUR : « . », un saut de ligne et l'indentation (5 à 6 mesurés).
ECART = 10

# (site, fichier, ancre de l'invocation du documenter) — les ancres du banc voisin, recopiées.
SITES = (
    ("kickoff.md step 7", ROOT / ".claude" / "commands" / "kickoff.md", r"Then\s+invoke\s+documenter"),
    ("kickoff SKILL step 11", ROOT / ".agents" / "skills" / "kickoff" / "SKILL.md", r"\binvoke\s+documenter"),
    ("copilot-instructions step 10", ROOT / ".github" / "copilot-instructions.md", r"^10\.\s+`documenter`"),
)
DEFS = (
    ".claude/agents/terraform-deployer.md",
    ".codex/agents/terraform-deployer.toml",
    ".gemini/agents/terraform-deployer.md",
    ".github/agents/terraform-deployer.agent.md",
    ".kimi-code/agents/terraform-deployer.md",
)
FIN_COMPACTION = re.compile(
    r"an\s+empty\s+`--kind\s+delta`\s+list\s+means\s+the\s+pass\s+is\s+LOST:\s+say\s+so\s+under\s+the\s+heading,"
    r"\s+with\s+the\s+pass\s+number"
)
FRAG_IAC_AUTEUR = re.compile(
    r"On\s+an\s+IaC\s+task\s+the\s+dev\s+pass\s+is\s+terraform-deployer's,\s+and\s+its\s+def\s+fixes\s+its\s+AUTEUR"
    r"\s+block\s+on\s+every\s+host:\s+`CHANGESET:/FILES:/IaC:/NOT\s+DONE:`\s+—\s+`IaC:`\s+carries\s+the\s+resources"
    r"\s+touched,.{0,160}?;\s+`NOT\s+DONE:`\s+names\s+the\s+apply,\s+never\s+played\s+in\s+the\s+task",
    re.S,
)
BLOC_DEF = re.compile(r"^CHANGESET: .*?^FILES:.*?^IaC: .*?^NOT DONE: ", re.M | re.S)


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def auteur_dit(texte: str, ancre: str) -> bool:
    """Ancre, puis clause de compaction à FENETRE près, puis phrase AUTEUR à ECART près. Un maillon absent → False."""
    m = re.search(ancre, texte, re.M)
    if m is None:
        return False
    c = FIN_COMPACTION.search(texte, m.end())
    if c is None or c.start() - m.end() > FENETRE:
        return False
    a = FRAG_IAC_AUTEUR.search(texte, c.end())
    return a is not None and a.start() - c.end() <= ECART


def test_les_trois_sites_sont_releves() -> None:
    assert [s[0] for s in SITES] == ["kickoff.md step 7", "kickoff SKILL step 11", "copilot-instructions step 10"]
    assert all(chemin.is_file() for _, chemin, _ in SITES), "un site a disparu : le relocaliser par son nom"


@pytest.mark.parametrize(("site", "chemin", "ancre"), SITES, ids=[s[0] for s in SITES])
def test_le_site_dit_le_bloc_auteur_apres_la_compaction(site: str, chemin: Path, ancre: str) -> None:
    assert auteur_dit(_lire(chemin), ancre), (
        f"{site}: pas de phrase AUTEUR de terraform-deployer à {ECART} caractères après la clause de compaction"
    )


@pytest.mark.parametrize(("site", "chemin", "ancre"), SITES, ids=[s[0] for s in SITES])
def test_controles_negatifs_sur_une_copie(site: str, chemin: Path, ancre: str) -> None:
    texte = _lire(chemin)
    assert auteur_dit(texte, ancre), f"{site}: base non verte — les contrôles ne mesureraient rien"
    a = FRAG_IAC_AUTEUR.search(texte)
    m = re.search(ancre, texte, re.M)
    c = FIN_COMPACTION.search(texte)
    assert a is not None and m is not None and c is not None
    reste = texte[: a.start()] + texte[a.end() :]
    mutants = (
        ("phrase retirée", reste),
        ("phrase éloignée", reste + "\n" + a.group(0) + "\n"),
        ("ancre retirée", texte[: m.start()] + texte[m.end() :]),
        ("clause de compaction retirée", texte[: c.start()] + texte[c.end() :]),
    )
    for nom, mutant in mutants:
        assert mutant != texte, f"{site}: mutation « {nom} » sans effet (contrôle vide)"
        assert not auteur_dit(mutant, ancre), f"{site}: « {nom} » doit rougir"


@pytest.mark.parametrize("rel", DEFS)
def test_chaque_def_fixe_les_quatre_champs_du_bloc(rel: str) -> None:
    texte = _lire(ROOT / rel)
    assert BLOC_DEF.search(texte), f"{rel}: le bloc AUTEUR `CHANGESET:/FILES:/IaC:/NOT DONE:` n'est plus fixé"
    sans = re.sub(r"^NOT DONE: ", "NOT-DONE ", texte, flags=re.M)
    assert sans != texte and not BLOC_DEF.search(sans), f"{rel}: un champ retiré doit rougir (contrôle vide)"
