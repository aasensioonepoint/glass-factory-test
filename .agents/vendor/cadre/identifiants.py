"""La couche de résolution des secrets du noyau — ENVIRONNEMENT SEUL (T-00000898).

Objet (§A-8 du prompt de refonte) : UNE seule API par laquelle le noyau obtient
un identifiant (jeton, clé d'API), `resoudre_secret(nom)`. Les consommateurs s'y
branchent dans T-00000900 ; ce module n'en a encore aucun.

PÉRIMÈTRE : la variable d'environnement, et elle seule. Décision pilote
S-00003973 (Q6, option c, 2026-10-03) : « environnement seul + erreur nommée ;
trousseau OS en tâche suivante ; stdlib seule maintenue ». Elle supersède le
« (env, trousseau OS) » du texte de la tâche. Le module s'appelle `identifiants`,
pas `secrets` : la garde de chemins refuse tout chemin qui porte ce mot
(décision pilote decision/T-00000898/01, option a), et un module `secrets` du
noyau masquerait celui de la stdlib.

CE QUI EST GARANTI ICI
- Le nom est validé AVANT toute lecture : `[A-Za-z_][A-Za-z0-9_]{0,127}` en
  ASCII explicite, par `fullmatch` (un `match` ancré laisserait passer `"A\\n"`).
  Un nom refusé lève `NomSecretInvalide` ; le message ne recopie JAMAIS
  l'entrée, il en donne la longueur.
- Une variable absente, ou VIDE, lève `SecretAbsent` (statut « absente » ou
  « vide ») : jamais une valeur vide silencieuse, jamais `None`. Vide veut dire
  `""` ou une chaîne dont `str.isspace()` est vrai — c'est la frontière, et elle
  est écrite : U+200B (espace sans chasse) n'est PAS un blanc pour Python, une
  valeur qui n'en porte que lui est donc « présente ».
- Une valeur présente est rendue EXACTE, jamais `.strip()` : `"tok\\r"` (un
  fichier d'environnement en CRLF) est rendu avec son `\\r`.
- La lecture se fait À L'APPEL, sans cache.
- Tout texte produit qui porte le nom passe par `rediger` (le message de
  `SecretAbsent`, `SecretAbsent.nom`, `Secret.nom`). Le message de
  `NomSecretInvalide` n'a rien à rédiger : phrases fixes et une longueur.
- `Secret` masque sa valeur dans `repr`, `str` et `format`, quel que soit le
  spécificateur ; `reveler()` est la SEULE sortie. Ni copie ni sérialisation :
  `__getstate__` lève `TypeError`, ce qui ferme `copy`, `deepcopy` et `pickle`.
- Construit en direct, `Secret(nom, valeur)` tient les invariants de
  `resoudre_secret` : nom validé par la même règle (`NomSecretInvalide`),
  valeur `str` (sinon `TypeError`), ni vide ni faite de blancs (sinon
  `ValueError`). Un refus ne laisse la valeur dans aucun local du cadre qui
  lève : elle n'y vit que masquée, dans `self`.
- Les exceptions ont leur message pour UNIQUE argument : elles survivent à une
  copie et à `pickle`. Elles sont construites par des fabriques APPELÉES avant
  le `raise` : le cadre qui lève ne tient que `nom`, `statut` et `valeur`
  (`None`), jamais la table d'environnement — c'est ce qui garde
  `--showlocals` et `capture_locals` muets.
- Ni `print` ni `logging` dans ce module.

CE QUI NE L'EST PAS
- `rediger` reconnaît des MOTIFS (jetons GitHub, clés AWS…), pas des secrets :
  un nom qui ne ressemble à aucun motif reste en clair dans les messages.
- `Secret._valeur` reste atteignable : Python n'a pas d'encapsulation.
- `Secret.nom` reste réassignable (`__slots__` n'interdit pas l'écriture) : la
  rédaction vaut à la construction, pas après.
- Sous Windows, `os.environ` ignore la casse des noms (`resoudre_secret("jeton")`
  y lirait `JETON`) : lu dans `os.py` (`encodekey` y met la clé en majuscules),
  NON MESURÉ sur un poste Windows.
- Un CONSOMMATEUR qui journalise `reveler()`, ou qui lie la valeur à un local,
  n'est vu par rien ici ; T-00000900 posera le contrôle.
- Aucune comparaison à temps constant n'est fournie : un consommateur qui
  compare passe par `reveler()` et `hmac.compare_digest`.
- Tout processus enfant d'un consommateur hérite de l'environnement : c'est le
  modèle « environnement seul ».

COUPLAGE SUBI (zone A). Importer ce module exécute `cadre/ledger/__init__.py`,
qui charge tout le paquet ledger. Mesuré à dd9444f2 sous Python 3.11.16,
3.12.14 et 3.14.7 : `import cadre.ledger.redaction` charge 9 sous-modules du
ledger (redaction compris), `cadre.paths`,
`cadre.workspace`, et avec eux les modules `sqlite3` et `subprocess` de la
stdlib. Le filet de pureté juge l'arbre syntaxique de CE fichier, pas les
modules chargés. Conséquence : aucun de ces modules du noyau ne peut importer
`identifiants` sans cycle — le banc `test_cadre_identifiants.py` le tient.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from cadre.ledger.redaction import rediger

__all__ = [
    "resoudre_secret",
    "Secret",
    "ErreurSecret",
    "SecretAbsent",
    "NomSecretInvalide",
]

_NOM = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_REGLE = ("attendu une lettre ASCII ou « _ », puis 0 à 127 lettres ASCII, "
          "chiffres ASCII ou « _ »")
_ABSENTE = "absente"
_VIDE = "vide"
_PRESENTE = "présente"
_VALEUR_NON_CHAINE = "valeur d'un Secret : une chaîne est attendue"
_VALEUR_VIDE = "valeur d'un Secret : vide ou faite de blancs"


class ErreurSecret(Exception):
    """Base des erreurs de la couche ; le message est l'unique argument."""


class SecretAbsent(ErreurSecret, LookupError):
    """La variable est absente ou vide. `nom` est rédigé ; `statut` vaut
    « absente » ou « vide »."""

    nom: str
    statut: str


class NomSecretInvalide(ErreurSecret, ValueError):
    """Le nom demandé n'a pas la forme d'un nom de variable ; le message ne
    recopie jamais l'entrée."""


def _absent(nom: str, statut: str) -> SecretAbsent:
    exc = SecretAbsent(
        rediger(f"secret « {nom} » : variable d'environnement {statut}"))
    exc.nom = rediger(nom)
    exc.statut = statut
    return exc


def _invalide(nom: object) -> NomSecretInvalide:
    if isinstance(nom, str):
        return NomSecretInvalide(
            f"nom de secret invalide ({len(nom)} caractères) : {_REGLE}")
    return NomSecretInvalide(
        f"nom de secret invalide : une chaîne est attendue ; {_REGLE}")


class Secret:
    """Une valeur résolue. `reveler()` est sa seule sortie ; `nom` est rédigé."""

    __slots__ = ("nom", "_valeur")

    def __init__(self, nom: str, valeur: str) -> None:
        # Un refus laisse `self` dans le cadre qui lève : `nom` provisoire posé
        # d'abord (en 3.11, `capture_locals` appelle `repr(self)` sans filet),
        # puis la valeur ne vit plus que masquée, dans `self`.
        self.nom = "<refusé>"
        self._valeur = valeur
        del valeur
        if not isinstance(nom, str) or _NOM.fullmatch(nom) is None:
            raise _invalide(nom)
        if not isinstance(self._valeur, str):
            raise TypeError(_VALEUR_NON_CHAINE)
        if not self._valeur or self._valeur.isspace():
            raise ValueError(_VALEUR_VIDE)
        self.nom = rediger(nom)

    def reveler(self) -> str:
        return self._valeur

    def __repr__(self) -> str:
        return f"Secret(nom={self.nom}, valeur=<masquée>)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __getstate__(self) -> object:
        raise TypeError(
            "un Secret ne se copie ni ne se sérialise ; seul reveler() rend la valeur")


def _lire_env(nom: str, environ: Mapping[str, str]) -> tuple[str, str | None]:
    """Cœur pur : la table est un ARGUMENT. Ne lève jamais, pour que son cadre
    (qui tient la table) ne soit dans aucune trace."""
    brut = environ.get(nom)
    if brut is None:
        return _ABSENTE, None
    if not brut or brut.isspace():
        return _VIDE, None
    return _PRESENTE, brut


def resoudre_secret(nom: str) -> Secret:
    """Résout `nom` dans l'environnement du processus, à l'appel.

    Lève `NomSecretInvalide` (nom hors forme, avant toute lecture) ou
    `SecretAbsent` (variable absente ou vide). Ne rend jamais `""` ni `None`.
    """
    if not isinstance(nom, str) or _NOM.fullmatch(nom) is None:
        raise _invalide(nom)
    statut, valeur = _lire_env(nom, os.environ)
    if valeur is None:
        raise _absent(nom, statut)
    return Secret(nom, valeur)
