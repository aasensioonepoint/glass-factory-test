"""Le rendu des COMMANDES `commands/<nom>.md`, PUR (T-01M5C1P67FN2YR9T3R0BHV7M3M).

Décision pilote S-01M5C01EAKQACKA27PNH804CR3 : `commands/<nom>.md`, à la racine, est la
SOURCE UNIQUE d'une commande. Ce module rend des TEXTES et ne touche jamais au disque
(banc de pureté, `test_cadre_package.py`) : les chemins des cibles, la lecture des sources
et la liste des noms de commandes vivent dans `.agents/bin/render_hosts.py`.

DEUX RENDUS par source :
  claude : la source, à l'OCTET (`.claude/commands/<nom>.md`) ;
  miroir : la skill cross-hôte `source-command-<nom>` (`.agents/skills/source-command-<nom>/
           SKILL.md`), pour toute commande hors `CLAUDE_SEUL` — `night` est Claude Code seul
           par doctrine (AGENTS.md § Unattended overnight mode) et n'a JAMAIS de miroir.
           Sa forme, à l'octet :

    ---
    name: "source-command-<nom>"
    description: <la description de la commande, en chaîne JSON>
    ---

    # source-command-<nom>

    Use this skill when the user asks to run the migrated source command `<nom>`.

    ## Command Template

    <le corps de la commande, DÉRIVÉ par la règle de régénération des miroirs>

  La règle (décision pilote S-01M5MCXYV352ZNNW7ZC75T8DJH, tenue par
  `.agents/evals/test_source_command_miroirs.py`) : le corps qui suit le `---` fermant, sans
  les lignes `Effort:` (propres à Claude Code) ni la ligne vide qui suit chacune, débarrassé
  des sauts de ligne de tête et de queue, avec trois traductions d'hôte — « Claude Code
  session » lu « Codex session », `` `.claude/skills/` `` lu sous sa forme hôte-neutre, et
  `/<commande>` lu `$<commande>` pour toute commande hors `CLAUDE_SEUL`, jamais un segment
  de chemin. Le miroir finit toujours par un saut de ligne. Rien n'est ajouté au corps : la
  ligne `Shared process reference:` qui pointe la skill partagée vit dans la SOURCE.

REFUSÉ par `lire_commande`, en `CommandeIllisible` (une `ValueError`) qui nomme la source,
la ligne et la cause, FAIL-CLOSED, avant tout texte : un nom hors `[a-z0-9]` et tirets
(il deviendrait un chemin et un `name:` de skill) ; une source qui n'ouvre pas sur `---` en
ligne 1, ou dont le frontmatter n'est pas refermé ; aucune ligne `description:`, ou plus
d'une ; une description vide ; une description entre guillemets doubles qui n'est pas une
chaîne JSON (un `"` interne non échappé), entre guillemets simples mal fermée, ou NUE qui
porte `: ` ou ` #` (la forme que Copilot refuse, `test_frontmatter_yaml_strict.py`).
"""

from __future__ import annotations

import json
import re
from typing import Iterable, NamedTuple

__all__ = ["CLAUDE_SEUL", "PREFIXE_MIROIR", "Commande", "CommandeIllisible",
           "corps_du_miroir", "est_une_commande", "lire_commande", "rendre_miroir", "rendus_commande"]

#: Les commandes Claude Code seul : jamais de miroir cross-hôte, et leur `/` jamais traduit.
CLAUDE_SEUL = frozenset({"night"})
PREFIXE_MIROIR = "source-command-"
SEPARATEUR = "---"
CLE = "description:"
OUVRE_EFFORT = "Effort:"
SKILLS_CLAUDE = "`.claude/skills/`"
SKILLS_HOTE_NEUTRE = "`.agents/skills/<name>/` or `.github/skills/<name>/`"
NOM = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
#: Ce qu'un scalaire YAML NU ne porte jamais ici (Copilot le refuse au chargement).
INTERDITS_NU = (": ", " #")


class CommandeIllisible(ValueError):
    """La source d'une commande n'a pas pu être lue ; le message nomme la source et la cause."""


class Commande(NamedTuple):
    nom: str
    description: str
    corps: str  # tout ce qui suit la ligne `---` fermante du frontmatter


def _refus(source: str, cause: str) -> CommandeIllisible:
    return CommandeIllisible(f"{source} : {cause}")


def _fin_du_frontmatter(lignes: list[str]) -> int | None:
    """L'index de la ligne `---` fermante, ou None (frontmatter absent ou non refermé)."""
    if not lignes or lignes[0] != SEPARATEUR:
        return None
    for i in range(1, len(lignes)):
        if lignes[i] == SEPARATEUR:
            return i
    return None


def est_une_commande(texte: str) -> bool:
    """Le texte porte-t-il un en-tête de commande reconnu : frontmatter en ligne 1, refermé,
    avec une ligne `description:` ? (Seul un tel ORPHELIN se retire.)"""
    lignes = texte.split("\n")
    fin = _fin_du_frontmatter(lignes)
    return fin is not None and any(ligne.startswith(CLE) for ligne in lignes[1:fin])


def _valeur(brute: str, source: str, rang: int) -> str:
    """La valeur d'un scalaire YAML d'une ligne : chaîne JSON, guillemets simples, ou nu."""
    if brute.startswith('"'):
        try:
            valeur = json.loads(brute)
        except ValueError as exc:
            raise _refus(source, f"ligne {rang} : description entre guillemets doubles qui n'est pas une "
                                 f"chaine JSON ({exc})") from exc
        if not isinstance(valeur, str):
            raise _refus(source, f"ligne {rang} : description qui n'est pas une chaine")
        return valeur
    if brute.startswith("'"):
        interieur = brute[1:-1]
        # `re.sub` et non `str.replace` : le filet de purete de `test_cadre_package` lit tout
        # `.replace(` comme une E/S disque (`os.replace`) hors `Workspace` ; le sens est le meme.
        if len(brute) < 2 or not brute.endswith("'") or "'" in re.sub("''", "", interieur):
            raise _refus(source, f"ligne {rang} : description entre guillemets simples mal fermee")
        return re.sub("''", "'", interieur)
    for interdit in INTERDITS_NU:
        if interdit in brute:
            raise _refus(source, f"ligne {rang} : description NUE qui porte {interdit!r} — mets-la entre "
                                 "guillemets doubles (chaine JSON)")
    return brute


def lire_commande(texte: str, nom: str, source: str | None = None) -> Commande:
    """La commande `nom` lue dans `texte` (validée ; voir le docstring du module)."""
    source = source if source is not None else f"commands/{nom}.md"
    if not NOM.match(nom):
        raise _refus(source, f"nom {nom!r} hors de [a-z0-9] et tirets : il deviendrait un chemin et un "
                             "`name:` de skill")
    lignes = texte.split("\n")
    fin = _fin_du_frontmatter(lignes)
    if fin is None:
        raise _refus(source, f"ligne 1 : frontmatter absent ou non refermé (la source ouvre par "
                             f"{SEPARATEUR!r} et le referme)")
    descriptions = [(i + 1, ligne) for i, ligne in enumerate(lignes[1:fin], start=1) if ligne.startswith(CLE)]
    if len(descriptions) != 1:
        raise _refus(source, f"{len(descriptions)} ligne(s) {CLE!r} dans le frontmatter, une seule attendue")
    rang, ligne = descriptions[0]
    description = _valeur(ligne[len(CLE):].strip(" \t"), source, rang)
    if not description.strip():
        raise _refus(source, f"ligne {rang} : description vide")
    return Commande(nom, description, "\n".join(lignes[fin + 1:]))


def corps_du_miroir(corps: str, commandes: Iterable[str]) -> str:
    """Le corps d'un miroir dérivé du corps d'une commande (la règle du docstring du module).
    `commandes` : les noms de toutes les commandes ; celles de `CLAUDE_SEUL` n'y sont jamais traduites."""
    garde: list[str] = []
    saute_vide = False
    for ligne in corps.split("\n"):
        if ligne.startswith(OUVRE_EFFORT):
            saute_vide = True
            continue
        if not (saute_vide and ligne == ""):
            garde.append(ligne)
        saute_vide = False
    texte = "\n".join(garde).strip("\n") + "\n"
    # `re.sub` et non `str.replace` : même raison que dans `_valeur` (filet de pureté).
    texte = re.sub("Claude Code session", "Codex session", texte)
    texte = re.sub(re.escape(SKILLS_CLAUDE), lambda _m: SKILLS_HOTE_NEUTRE, texte)
    traduites = sorted((c for c in set(commandes) if c not in CLAUDE_SEUL), key=len, reverse=True)
    if traduites:
        alternance = "|".join(re.escape(c) for c in traduites)
        texte = re.sub(rf"(?<![\w./-])/({alternance})(?![\w/-])", r"$\1", texte)
    return texte


def rendre_miroir(commande: Commande, commandes: Iterable[str]) -> str:
    """Le texte de `.agents/skills/source-command-<nom>/SKILL.md`. `commandes` : les noms de
    toutes les commandes du kit, pour la traduction `/<commande>` -> `$<commande>`."""
    if commande.nom in CLAUDE_SEUL:
        raise ValueError(f"{commande.nom!r} est Claude Code seul : jamais de miroir")
    nom = f"{PREFIXE_MIROIR}{commande.nom}"
    tete = (f"{SEPARATEUR}\nname: {json.dumps(nom)}\n"
            f"description: {json.dumps(commande.description, ensure_ascii=False)}\n{SEPARATEUR}\n\n"
            f"# {nom}\n\n"
            f"Use this skill when the user asks to run the migrated source command `{commande.nom}`.\n\n"
            "## Command Template\n\n")
    return tete + corps_du_miroir(commande.corps, commandes)


def rendus_commande(texte: str, nom: str, commandes: Iterable[str],
                    source: str | None = None) -> dict[str, str]:
    """`{"claude": texte}` (la source à l'octet), plus `"miroir"` hors `CLAUDE_SEUL`.
    Lève `CommandeIllisible` sur une source refusée."""
    commande = lire_commande(texte, nom, source)
    sortie = {"claude": texte}
    if nom not in CLAUDE_SEUL:
        sortie["miroir"] = rendre_miroir(commande, commandes)
    return sortie
