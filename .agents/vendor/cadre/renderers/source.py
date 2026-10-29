"""Le format SOURCE `agents/<nom>.md` (T-01M5C1NXE5JWY6A0C2XWEGDPCC), PUR.

Décision pilote S-01M5C01EAKQACKA27PNH804CR3 : un fichier par déf, à la racine,
qui porte TOUS ses rendus d'hôte. `ecrire_source` le compose depuis un objet
FORMAT 1 (`cadre.roster`), `lire_source` le décompose en ce même objet ;
`serialiser(lire_source(ecrire_source(o), nom))` rend les octets du JSON du roster.

LE FORMAT, lignes jointes par `\\n` (le modèle de lignes de `cadre.roster` : un
texte qui finit par `\\n` garde sa dernière ligne vide) :

    ---
    <entête claude>
    ---
    <corps claude>
    <!-- hote: <h> -->            pour chaque hôte porté hors claude, dans l'ordre de HOTES
    <entête de h>
    <!-- corps -->                puis le corps de h,
    <corps de h>
    <!-- corps: comme claude -->  OU cette ligne seule, quand h reprend le corps de claude

UN SEUL PRÉDICAT DE SENTINELLE (`est_sentinelle`), partagé par l'écriture et la
lecture : toute ligne qui OUVRE par `<!-- hote:` ou `<!-- corps` en est une. À
l'écriture, une telle ligne dans un entête ou un corps est REFUSÉE (elle
couperait le fichier) ; à la lecture, une sentinelle qui n'est pas l'une des
trois formes exactes est refusée. Une ligne `---` dans l'entête de claude est
refusée à l'écriture : elle refermerait le frontmatter.

REFUSÉ à la lecture, par `SourceIllisible` qui nomme la source, la ligne et la
cause : source qui n'ouvre pas sur `---` (rendu claude absent), entête de claude
non refermé ou qui porte une sentinelle, hôte inconnu, `claude` en section,
hôte doublé ou hors de l'ordre de `HOTES`, section sans sentinelle de corps,
toute ligne après un renvoi `comme claude` hors la sentinelle de l'hôte suivant.
TOLÉRÉ : UN saut de ligne final unique quand la source finit sur ce renvoi (un
éditeur l'ajoute) ; il est retiré à la lecture, l'écriture reste canonique (sans
lui) ; deux sauts, ou une ligne vide avant l'hôte suivant, restent refusés.
L'objet lu passe ENSUITE `roster._valider` (FORMAT 1 entier : identité, marqueur
`cadre.`, entête vide…), qui lève `RosterIllisible`, puis `renderers.rendus`
(lecture ET écriture), dont le refus `RenduRefuse` (corps codex qui porte `\"\"\"`
ou `\\`, TOML relu hors de ses clés, `---` dans un entête markdown) devient
`SourceIllisible` : `render_hosts.py --check` le nomme. Les trois exceptions sont
des `ValueError`.
"""

from __future__ import annotations

from collections.abc import Mapping

from cadre.config import HOTES
from cadre.renderers import rendus as _rendus
from cadre.roster import REFERENCE, _valider

__all__ = ["COMME", "CORPS", "PREFIXES_SENTINELLE", "SourceIllisible", "ecrire_source",
           "est_sentinelle", "lire_source"]

PREFIXES_SENTINELLE = ("<!-- hote:", "<!-- corps")
OUVRE_HOTE = "<!-- hote: "
FERME = " -->"
CORPS = "<!-- corps -->"
COMME = f"<!-- corps: comme {REFERENCE} -->"
SEPARATEUR = "---"


class SourceIllisible(ValueError):
    """La source n'a pas pu être lue ou écrite ; le message nomme la source et la cause."""


def _refus(source: str, cause: str) -> SourceIllisible:
    return SourceIllisible(f"{source} : {cause}")


def est_sentinelle(ligne: str) -> bool:
    """LE prédicat, unique : la ligne ouvre par `<!-- hote:` ou `<!-- corps`."""
    return ligne.startswith(PREFIXES_SENTINELLE)


def _sentinelle_hote(hote: str) -> str:
    return f"{OUVRE_HOTE}{hote}{FERME}"


def _hote_de(ligne: str) -> str | None:
    """L'hôte d'une ligne `<!-- hote: <h> -->` exacte, ou None."""
    if len(ligne) > len(OUVRE_HOTE) + len(FERME) and ligne.startswith(OUVRE_HOTE) \
            and ligne.endswith(FERME):
        return ligne[len(OUVRE_HOTE):-len(FERME)]
    return None


def _rendable(objet: Mapping, source: str) -> None:
    """Le refus du rendu (`RenduRefuse`), nommé pour la source."""
    try:
        _rendus(objet)
    except ValueError as exc:
        raise _refus(source, str(exc)) from exc


def ecrire_source(objet: Mapping, source: str = "<objet>") -> str:
    """Le texte de `agents/<nom>.md` pour l'objet FORMAT 1 `objet` (validé d'abord)."""
    nom = objet.get("nom") if isinstance(objet, Mapping) else None
    _valider(objet, source, nom if isinstance(nom, str) else "")
    rendus = objet["rendus"]
    for hote, rendu in rendus.items():
        corps = [] if isinstance(rendu["corps"], Mapping) else rendu["corps"]
        for ou, lignes in (("entete", rendu["entete"]), ("corps", corps)):
            for rang, ligne in enumerate(lignes):
                if est_sentinelle(ligne):
                    raise _refus(source, f"rendus.{hote}.{ou}[{rang}] {ligne!r} ouvre comme une sentinelle "
                                         f"{list(PREFIXES_SENTINELLE)} : elle couperait la source")
    reference = rendus[REFERENCE]
    if SEPARATEUR in reference["entete"]:
        raise _refus(source, f"rendus.{REFERENCE}.entete porte une ligne {SEPARATEUR!r} : "
                             "elle refermerait le frontmatter")
    _rendable(objet, source)
    lignes = [SEPARATEUR, *reference["entete"], SEPARATEUR, *reference["corps"]]
    for hote in HOTES:
        if hote == REFERENCE or hote not in rendus:
            continue
        rendu = rendus[hote]
        lignes += [_sentinelle_hote(hote), *rendu["entete"]]
        lignes += [COMME] if isinstance(rendu["corps"], Mapping) else [CORPS, *rendu["corps"]]
    return "\n".join(lignes)


def _jusqu_a_sentinelle(lignes: list[str], i: int) -> int:
    while i < len(lignes) and not est_sentinelle(lignes[i]):
        i += 1
    return i


def lire_source(texte: str, nom: str, source: str | None = None) -> dict:
    """L'objet FORMAT 1 de la source `texte` de la déf `nom` (validé par `roster._valider`)."""
    source = source if source is not None else f"agents/{nom}.md"
    lignes = texte.split("\n")
    if lignes[0] != SEPARATEUR:
        raise _refus(source, f"ligne 1 : le rendu de reference {REFERENCE!r} est absent "
                             f"(la source ouvre par {SEPARATEUR!r})")
    fin = None
    for i in range(1, len(lignes)):
        if est_sentinelle(lignes[i]):
            raise _refus(source, f"ligne {i + 1} : sentinelle {lignes[i]!r} dans l'entete {REFERENCE}")
        if lignes[i] == SEPARATEUR:
            fin = i
            break
    if fin is None:
        raise _refus(source, f"l'entete {REFERENCE} n'est pas refermee par {SEPARATEUR!r}")
    i = _jusqu_a_sentinelle(lignes, fin + 1)
    rendus: dict[str, dict] = {REFERENCE: {"entete": lignes[1:fin], "corps": lignes[fin + 1:i]}}
    rang_precedent = HOTES.index(REFERENCE)
    while i < len(lignes):
        hote = _hote_de(lignes[i])
        if hote is None:
            raise _refus(source, f"ligne {i + 1} : sentinelle {lignes[i]!r} inattendue, "
                                 f"attendu {_sentinelle_hote('<hote>')!r}")
        if hote not in HOTES:
            raise _refus(source, f"ligne {i + 1} : hote inconnu {hote!r}, liste fermee {list(HOTES)}")
        if hote in rendus:
            raise _refus(source, f"ligne {i + 1} : hote {hote!r} double"
                                 + (f" ({REFERENCE} est la tete de la source)" if hote == REFERENCE else ""))
        if HOTES.index(hote) < rang_precedent:
            raise _refus(source, f"ligne {i + 1} : hote {hote!r} hors de l'ordre de HOTES {list(HOTES)}")
        rang_precedent = HOTES.index(hote)
        debut = i + 1
        i = _jusqu_a_sentinelle(lignes, debut)
        entete = lignes[debut:i]
        if i == len(lignes):
            raise _refus(source, f"section {hote!r} sans {CORPS!r} ni {COMME!r}")
        if lignes[i] == COMME:
            corps: list[str] | dict[str, str] = {"comme": REFERENCE}
            i += 1
            if i == len(lignes) - 1 and lignes[i] == "":
                i += 1  # UN saut de ligne final unique, toléré et retiré
            elif i < len(lignes) and not est_sentinelle(lignes[i]):
                raise _refus(source, f"ligne {i + 1} : {lignes[i]!r} apres {COMME!r} — rien ne suit un "
                                     "renvoi sauf l'hote suivant (un saut de ligne final unique tolere)")
        elif lignes[i] == CORPS:
            debut = i + 1
            i = _jusqu_a_sentinelle(lignes, debut)
            corps = lignes[debut:i]
        else:
            raise _refus(source, f"ligne {i + 1} : sentinelle {lignes[i]!r} mal formee, "
                                 f"attendu {CORPS!r} ou {COMME!r}")
        rendus[hote] = {"entete": entete, "corps": corps}
    objet = {"version_format": 1, "nom": nom, "rendus": rendus}
    _valider(objet, source, nom)
    _rendable(objet, source)
    return objet
