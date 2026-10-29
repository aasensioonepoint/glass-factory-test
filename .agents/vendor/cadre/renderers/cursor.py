"""Le rendu CURSOR, PUR (T-01M5BZCDMCEQXKA2RKTB2EMW8M) — cible DÉRIVÉE, NON MESURÉE.

Cursor n'est PAS un hôte de `cadre.config.HOTES` (liste fermée ; « les héritiers restent hors
de HOTES ») : c'est une cible que `.agents/bin/render_hosts.py` dérive des sources uniques
`agents/` et `commands/`, comme `.claude/commands/` et les miroirs `source-command-*`. Rien
ne prouve que Cursor lise ces fichiers : aucune mesure sur Cursor n'a été faite. Ce module
rend des TEXTES et ne touche jamais au disque (banc de pureté, `test_cadre_package.py`).

LA RÈGLE `.cursor/rules/<nom>.mdc` d'une déf qui porte un rendu `kimi` (hôte non tiéré,
sans `model` ni `effort`), lignes jointes par `\\n` comme `renderers.rendre` :

    ---
    description: <la description de l'entête kimi, sur UNE ligne>
    alwaysApply: false
    ---
    <le corps kimi, renvoi `comme` résolu : les lignes que `rendre("kimi", …)` pose
     après son `---` fermant>

Pas de `globs` : la règle est à la demande de l'agent (« Agent Requested »). La description :
une ligne `description: <valeur>` de l'entête kimi est recopiée TELLE QUELLE ; un bloc plié
(`>` ou `>-`, lignes suivantes indentées) est joint par des espaces et posé en chaîne JSON
(un scalaire YAML entre guillemets doubles). Une déf SANS rendu kimi n'a pas de règle
(`regle` rend `None`) : l'appelant le DIT, jamais en silence.

LA COMMANDE `.cursor/commands/<nom>.md` : les octets de la source (= `.claude/commands/<nom>.md`)
quand son frontmatter ne porte que `description` ; sinon le frontmatter réduit à sa seule ligne
`description:`, corps inchangé. Les commandes Claude Code seul (`commands.CLAUDE_SEUL` : `night`)
n'ont JAMAIS de commande Cursor (`commande` rend `None`).

REFUSÉ, en `RegleRefusee` (une `ValueError`) qui nomme la déf et la cause, FAIL-CLOSED, avant
tout texte : aucune ligne `description:` dans l'entête kimi, ou plus d'une ; une valeur vide
(`""`, `''`, bloc plié sans ligne) ; un bloc littéral (`|`) ou tout autre indicateur de bloc ;
un bloc plié coupé par une ligne vide ; une valeur NUE qui porte `: ` ou ` #` (la forme qu'un
YAML strict refuse, `commands.INTERDITS_NU`). Côté commande : la source refusée par
`commands.lire_commande`, et un frontmatter réduit dont la description ouvre un bloc (`>`, `|`)
— réduite à une ligne, elle perdrait sa suite.

RECONNUS COMME RENDUS (seul un tel fichier, sans source, est un ORPHELIN retirable) :
`est_une_regle` — frontmatter en ligne 1, refermé, d'EXACTEMENT deux lignes, `description:`
puis `alwaysApply: false` ; une commande Cursor l'est par `commands.est_une_commande`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from cadre.renderers import _corps
from cadre.renderers.commands import CLAUDE_SEUL, INTERDITS_NU, lire_commande

__all__ = ["ALWAYS_APPLY", "HOTE_CORPS", "RegleRefusee", "commande", "description", "est_une_regle", "regle",
           "rendre_regle"]

#: L'hôte dont la règle reprend l'entête (description) et le corps.
HOTE_CORPS = "kimi"
SEPARATEUR = "---"
CLE = "description:"
ALWAYS_APPLY = "alwaysApply: false"
#: Les indicateurs de bloc plié admis ; tout autre indicateur de bloc (`|`, `>+`, `>2`…) est refusé.
PLIES = (">", ">-")
OUVRE_BLOC = (">", "|")
INDENTS = (" ", "\t")
VIDES = ('""', "''")


class RegleRefusee(ValueError):
    """Le rendu Cursor est refusé ; le message nomme la déf (ou la commande) et la cause."""


def _refus(nom: str, cause: str) -> RegleRefusee:
    return RegleRefusee(f"rendu cursor {nom} : {cause}")


def _plie(entete: Sequence[str], rang: int, nom: str) -> str:
    """Le bloc plié qui suit `entete[rang]`, joint par des espaces."""
    suite: list[str] = []
    for i in range(rang + 1, len(entete)):
        ligne = entete[i]
        if ligne.startswith(INDENTS):
            suite.append(ligne.strip(" \t"))
            continue
        if ligne == "" and i + 1 < len(entete) and entete[i + 1].startswith(INDENTS):
            raise _refus(nom, f"entete[{i}] : bloc plie coupe par une ligne vide — mets la description sur "
                              "une ligne")
        break
    valeur = " ".join(morceau for morceau in suite if morceau)
    if not valeur:
        raise _refus(nom, f"entete[{rang}] : bloc plie sans ligne — description vide")
    return valeur


def description(entete: Sequence[str], nom: str) -> str:
    """La ligne `description: …` de la règle de `nom`, sur UNE ligne, depuis l'entête kimi."""
    rangs = [i for i, ligne in enumerate(entete) if ligne.startswith(CLE)]
    if len(rangs) != 1:
        raise _refus(nom, f"{len(rangs)} ligne(s) {CLE!r} dans l'entete {HOTE_CORPS}, une seule attendue")
    rang = rangs[0]
    brute = entete[rang][len(CLE):].strip(" \t")
    if brute in PLIES:
        return f"{CLE} {json.dumps(_plie(entete, rang, nom), ensure_ascii=False)}"
    if brute.startswith(OUVRE_BLOC):
        raise _refus(nom, f"entete[{rang}] : indicateur de bloc {brute!r} hors de {list(PLIES)} — mets la "
                          "description sur une ligne")
    if not brute or brute in VIDES:
        raise _refus(nom, f"entete[{rang}] : description vide")
    if not brute.startswith(("'", '"')):
        for interdit in INTERDITS_NU:
            if interdit in brute:
                raise _refus(nom, f"entete[{rang}] : description NUE qui porte {interdit!r} — mets-la entre "
                                  "guillemets doubles (chaine JSON)")
    return f"{CLE} {brute}"


def rendre_regle(nom: str, entete: Sequence[str], corps: Sequence[str]) -> str:
    """Le texte de `.cursor/rules/<nom>.mdc` pour l'entête kimi `entete` et le corps `corps`."""
    return "\n".join([SEPARATEUR, description(entete, nom), ALWAYS_APPLY, SEPARATEUR, *corps])


def regle(objet: Mapping) -> str | None:
    """La règle d'un objet FORMAT 1 (`cadre.roster`), ou `None` s'il ne porte pas de rendu kimi."""
    if HOTE_CORPS not in objet["rendus"]:
        return None
    return rendre_regle(objet["nom"], objet["rendus"][HOTE_CORPS]["entete"], _corps(objet, HOTE_CORPS))


def est_une_regle(texte: str) -> bool:
    """Le texte a-t-il la forme d'une règle rendue ici (frontmatter `description:` puis
    `alwaysApply: false`, rien d'autre) ? Seule une telle règle sans source est un ORPHELIN."""
    lignes = texte.split("\n")
    return (len(lignes) >= 4 and lignes[0] == SEPARATEUR and lignes[1].startswith(CLE)
            and lignes[2] == ALWAYS_APPLY and lignes[3] == SEPARATEUR)


def commande(texte: str, nom: str, source: str | None = None) -> str | None:
    """Le texte de `.cursor/commands/<nom>.md`, ou `None` pour une commande Claude Code seul.
    Lève `commands.CommandeIllisible` sur une source refusée, `RegleRefusee` sur une réduction
    impossible."""
    lire_commande(texte, nom, source)
    if nom in CLAUDE_SEUL:
        return None
    lignes = texte.split("\n")
    fin = lignes.index(SEPARATEUR, 1)
    entete = lignes[1:fin]
    if len(entete) == 1:
        return texte
    (ligne,) = [ligne for ligne in entete if ligne.startswith(CLE)]
    if ligne[len(CLE):].strip(" \t").startswith(OUVRE_BLOC):
        raise _refus(nom, f"la description {ligne!r} ouvre un bloc : reduite a sa seule ligne, elle perdrait "
                          "sa suite")
    return "\n".join([SEPARATEUR, ligne, SEPARATEUR, *lignes[fin + 1:]])
