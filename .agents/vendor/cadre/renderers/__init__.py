"""Le rendu des défs d'agents vers les hôtes, PUR (T-01M5C1NXE5JWY6A0C2XWEGDPCC).

Décision pilote S-01M5C01EAKQACKA27PNH804CR3 : `agents/<nom>.md`, à la racine,
est la SOURCE UNIQUE ; les cinq dossiers d'hôte et le roster JSON
(`data/roster/<nom>.json`) en sont DÉRIVÉS. Ce module rend des TEXTES et ne
touche jamais au disque (banc de pureté, `test_cadre_package.py`) : les E/S
vivent dans `.agents/bin/render_hosts.py`. Il fusionne les renderers markdown et
TOML prévus par T-00000974 et T-00000975.

LES DEUX FORMES, à l'octet (algorithme de `test_cadre_roster.recomposer`) :
  Markdown : `---` / entête / `---` / corps, lignes jointes par `\\n` ;
  TOML     : entête / `developer_instructions = \"\"\"` / corps, puis `\"\"\"\\n`.
Un hôte est TOML s'il est dans `roster._IDENTITE_TOML` (codex), markdown sinon.

`serialiser` est la sérialisation canonique d'un objet FORMAT 1 (`cadre.roster`) :
celle dont `test_cadre_roster.py` T5 tient les octets du roster.

`rendus` résout le renvoi `{"comme": "claude"}` et rend, dans l'ordre de
`HOTES`, le texte de chaque hôte que l'objet porte.

Les COMMANDES (`commands/<nom>.md`, T-01M5C1P67FN2YR9T3R0BHV7M3M) ont leur rendu pur à
part, dans `renderers.commands`.

REFUSÉ par `rendre`, en `RenduRefuse` (une `ValueError`), FAIL-CLOSED, avant tout texte :
  TOML     : une ligne de corps qui porte `\"\"\"` (elle refermerait la chaîne
             `developer_instructions` et poserait des clés codex — `sandbox_mode`,
             `approval_policy` — depuis un corps) ou `\\` (un échappement de chaîne basique :
             TOML invalide, ou valeur différente du corps) ; puis le texte rendu est
             RE-PARSÉ par `tomllib` : ses clés sont EXACTEMENT celles de l'entête (parsé seul)
             plus `developer_instructions`, et cette valeur ÉGALE le corps joint ;
  Markdown : une ligne `---` dans l'entête (elle refermerait le frontmatter de l'hôte).
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence

from cadre.config import HOTES, HoteInconnu
from cadre.roster import _IDENTITE_TOML, REFERENCE

__all__ = ["FERMETURE_TOML", "INTERDITS_TOML", "OUVERTURE_TOML", "RenduRefuse", "rendre", "rendus",
           "serialiser"]

CLE_TOML = "developer_instructions"
OUVERTURE_TOML = f'{CLE_TOML} = """'
FERMETURE_TOML = '"""\n'
SEPARATEUR_MD = "---"
#: Ce qu'une ligne de corps codex ne porte jamais : le délimiteur, et l'échappement.
INTERDITS_TOML = ('"""', "\\")


class RenduRefuse(ValueError):
    """Le rendu d'un hôte est refusé ; le message nomme l'hôte, la ligne et la cause."""


def _toml(texte: str, hote: str, quoi: str) -> dict:
    try:
        return tomllib.loads(texte)
    except (tomllib.TOMLDecodeError, RecursionError, ValueError) as exc:
        raise RenduRefuse(f"rendu {hote} : {quoi} n'est pas un TOML valide — {exc}") from exc


def _rendre_toml(hote: str, entete: Sequence[str], corps: Sequence[str]) -> str:
    for rang, ligne in enumerate(corps):
        for interdit in INTERDITS_TOML:
            if interdit in ligne:
                raise RenduRefuse(f"rendu {hote} : corps[{rang}] {ligne!r} porte {interdit!r} — il fermerait "
                                  f"ou corromprait la chaine {CLE_TOML}")
    cles = set(_toml("\n".join(entete), hote, "l'entete"))
    if CLE_TOML in cles:
        raise RenduRefuse(f"rendu {hote} : l'entete porte deja la cle {CLE_TOML!r}")
    texte = "\n".join([*entete, OUVERTURE_TOML]) + "\n" + "\n".join(corps) + FERMETURE_TOML
    relu = _toml(texte, hote, "le texte rendu")
    if set(relu) != cles | {CLE_TOML}:
        raise RenduRefuse(f"rendu {hote} : cles relues {sorted(relu)} != entete {sorted(cles)} + {CLE_TOML!r}")
    if relu[CLE_TOML] != "\n".join(corps):
        raise RenduRefuse(f"rendu {hote} : la valeur relue de {CLE_TOML!r} differe du corps")
    return texte


def rendre(hote: str, entete: Sequence[str], corps: Sequence[str]) -> str:
    """Le texte du fichier d'hôte `hote` pour cet entête et ce corps (en lignes)."""
    if hote not in HOTES:
        raise HoteInconnu(f"hote {hote!r} hors de la liste fermee {list(HOTES)}")
    if hote in _IDENTITE_TOML:
        return _rendre_toml(hote, entete, corps)
    if SEPARATEUR_MD in entete:
        raise RenduRefuse(f"rendu {hote} : l'entete porte une ligne {SEPARATEUR_MD!r} — elle refermerait "
                          "le frontmatter")
    return "\n".join([SEPARATEUR_MD, *entete, SEPARATEUR_MD, *corps])


def _corps(objet: Mapping, hote: str) -> Sequence[str]:
    corps = objet["rendus"][hote]["corps"]
    if isinstance(corps, Mapping):
        return objet["rendus"][corps["comme"]]["corps"]
    return corps


def rendus(objet: Mapping) -> dict[str, str]:
    """Hôte -> texte rendu, pour chaque hôte que l'objet FORMAT 1 porte, dans l'ordre
    de `HOTES`. Le renvoi `comme` est résolu vers `REFERENCE`."""
    if REFERENCE not in objet["rendus"]:
        raise ValueError(f"{objet.get('nom')!r} : le rendu de reference {REFERENCE!r} est absent")
    return {hote: rendre(hote, objet["rendus"][hote]["entete"], _corps(objet, hote))
            for hote in HOTES if hote in objet["rendus"]}


def serialiser(objet: Mapping) -> str:
    """La sérialisation CANONIQUE d'un objet FORMAT 1 (octets de `data/roster/<nom>.json`)."""
    return json.dumps(objet, indent=2, ensure_ascii=False) + "\n"
