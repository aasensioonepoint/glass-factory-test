"""Témoin D3 (T-01M5T4NRDNZ0ESYGFR3154RRJM, lot P) : /planning rend au pilote
la ligne de commit du plan AVANT `night_approve.py --apply`.

`night_approve.py` refuse (condition 8) un plan absent de HEAD ou modifié
depuis HEAD ; `/planning` ne commite jamais (commands/planning.md, « jamais de
commit »). La phrase S2 (annexe du plan, § 8) doit donc vivre, à l'octet, au
point 8 « n'écrit PAS le contrat » de la source et de ses trois rendus : un
rendu non rejoué après l'édition de la source rougit ici.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: S2, la commande d'hôte remplacée par {cmd} (`/planning` ou `$planning`).
S2 = (
    "**Avant `--apply`, le pilote commite le plan** — `git add -- <plan>` puis "
    '`git commit -m "docs(tasks): plan T-NNNNNNNN" -- <plan>` : '
    "`night_approve.py` refuse (condition 8) un plan absent de HEAD ou modifié "
    "depuis HEAD, et `{cmd}` ne commite rien."
)

#: (chemin, commande d'hôte) : la source et ses trois rendus.
SURFACES = (
    ("commands/planning.md", "/planning"),
    (".claude/commands/planning.md", "/planning"),
    (".cursor/commands/planning.md", "/planning"),
    (".agents/skills/source-command-planning/SKILL.md", "$planning"),
)

DEBUT = "n'écrit PAS le contrat `night-eligible: approved`.**"
FIN = "\n9. "


def _section(texte: str) -> str:
    """Le point 8 : de son titre au point 9, bornes exigées."""
    assert DEBUT in texte, "point 8 « n'écrit PAS le contrat » introuvable"
    debut = texte.index(DEBUT)
    assert FIN in texte[debut:], "point 9 introuvable après le point 8"
    return texte[debut : texte.index(FIN, debut)]


@pytest.mark.parametrize(("rel", "cmd"), SURFACES, ids=[s[0] for s in SURFACES])
def test_s2_au_point_8(rel: str, cmd: str) -> None:
    section = _section((ROOT / rel).read_text(encoding="utf-8"))
    phrase = S2.format(cmd=cmd)
    assert phrase in section, f"{rel} : S2 absente du point 8"
    apply_ = section.index("night_approve.py --apply")
    commit = section.index(phrase)
    non_approuve = section.index("non approuvé n'ouvre AUCUNE nuit")
    assert apply_ < commit < non_approuve, f"{rel} : S2 hors de sa place"
