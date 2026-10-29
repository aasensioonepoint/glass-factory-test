"""LE RÉPARTITEUR DE `cadre hook <evenement> --host <hote>` — un module PUR.

Ce module DÉCIDE, la CLI fait les E/S. `repartir` reçoit les OCTETS bruts du
payload — la CLI les lit sur l'entrée standard — et rend une `Reponse` : ce
qu'il faut écrire sur la sortie standard, sur la sortie d'erreur, et le code de
sortie. La CLI l'écrit telle quelle. Rien ici ne lit, n'écrit ni ne lance quoi
que ce soit : aucune référence aux flux standard du module `sys` (leurs doubles
dunder compris, ni par leur nom en chaîne), ni à `print`, `input`, `open`,
`__import__`, ni aux modules `subprocess`, `os` ou `builtins`, et aucun import
hors d'une liste fermée — épinglé sur l'ARBRE SYNTAXIQUE par
`.agents/evals/test_cadre_hook.py` (H9), jamais sur le texte, pour que cette
phrase ne déclenche pas la règle qu'elle énonce. C'est un filet contre
l'INADVERTANCE, borné : un nom fabriqué à l'exécution lui échappe.

TOUT REFUS SORT PAR LE CANAL DE L'HÔTE (`contrat-hook:refus-par-hote`,
L-00000213), qu'il vienne d'une garde ou du répartiteur lui-même :

* claude — la raison sur la sortie d'erreur, code 2, sortie standard VIDE :
  le seul canal mesuré de bout en bout ;
* codex, gemini, copilot, kimi — l'enveloppe
  `hookSpecificOutput.permissionDecision: deny` sur la sortie standard,
  code 0, comme `deny` des jumeaux `.codex/hooks/_common.py` et
  `.gemini/hooks/_common.py` ; copilot reçoit en plus les clés PLATES
  `permissionDecision` et `permissionDecisionReason`. Un code 2 s'y lirait
  comme un plantage du hook, donc comme un échec OUVERT. Kimi passe par
  l'enveloppe sur décision pilote S-01M54NGJC1RVBKHYQJ99RPM3EJ.

`hookEventName` porte le nom CANONIQUE de l'événement — celui du verrou, jamais
la graphie native : copilot reçoit `PreToolUse`, pas `preToolUse`, comme chez
les jumeaux. Pour un événement INCONNU, il porte l'argument TEL QUE REÇU : il
n'y a pas de nom canonique à donner (décision pilote
S-01M54WTQTHB14SH0W0KZTHNCYB : enveloppe et code 0 sur les hôtes à enveloppe,
code 2 sur claude). Comme `natif` compare à la casse exacte, l'argument d'un
événement connu EST son nom canonique.

LES REFUS DU RÉPARTITEUR forment une énumération close, dans cet ordre :
événement hors de la table (`EvenementInconnu`) ; événement que le registre de
l'hôte ne déclare pas (cellule `None` de `natif`) ; payload qui n'est pas de
l'UTF-8 STRICT ; payload qui n'est pas du JSON lisible — vide compris, trop
imbriqué compris, et BOM UTF-8 compris : les octets sont DÉCODÉS d'abord, puis
le TEXTE est donné à `json.loads`, qui refuse un BOM dans une `str` alors qu'il
l'accepte en tête d'octets (mesuré, 3.14.7) ; payload JSON qui n'est pas un
objet ; table des gardes EN FAUTE — l'entrée de l'événement n'est pas une
séquence de gardes : `cadre hook : table des gardes en faute (<type>)` ; garde
EN FAUTE — une garde qui lève QUOI QUE CE SOIT (toute `BaseException` :
`SystemExit` de tout code, `KeyboardInterrupt`, `GeneratorExit` compris), ou
qui rend autre chose que `None` ou un `Refus` :
`cadre hook : garde en faute (<type>)`. Le NOM du type seul, jamais le message
de l'exception, qui peut citer le payload. Fail-closed : un payload qu'on ne
sait pas lire, ou qu'une garde n'a pas su juger, n'est jamais laissé passer —
un traceback (code 1, rien sur la sortie standard) se lirait comme un plantage
du hook, donc comme un échec OUVERT, sur les cinq hôtes ; un `SystemExit(0)`
sorti d'une garde, comme un laisser-passer silencieux (mesuré avant cette
correction : code 0, rien sur aucun flux).

Hors de `repartir`, deux refus rendus par le même canal, pour la CLI :
`refus_d_entree`, une entrée standard qu'elle n'a pas pu lire (toute
`Exception` : `OSError`, `ValueError` d'un flux clos, `AttributeError` d'un
flux sans `.buffer`),
`cadre hook : entree standard illisible (<type>)` ; `refus_de_table`, une table
de production que `resoudre()` n'a pas su rendre (toute `BaseException`),
`cadre hook : table des gardes en faute (<type>)`. Le nom du type seul.
BORNE : une faute à l'ÉCRITURE de la réponse (`BrokenPipeError` sur la sortie
standard) n'est pas traitée — hors périmètre de T-00000862.

Un hôte hors de `HOTES` n'est PAS un refus rendu : `natif` lève
`HoteInconnu`, un type, et la CLI le refuse avant, par argparse.

LA RAISON EST TOUJOURS SÉRIALISÉE PAR `json.dumps(…, ensure_ascii=True)`, dans
l'enveloppe comme sur la sortie d'erreur : une `Reponse` est de l'ASCII pur.
Un `\\ud800` isolé — légal dans un payload JSON, et produit par
`surrogateescape` sur un argv qui n'est pas de l'UTF-8 — s'écrit donc sur
n'importe quel flux sans `UnicodeEncodeError`, donc sans traceback.

LA TABLE DE PRODUCTION EST VIDE. `resoudre()` est la COUTURE où T-00000863 et
T-00000731 brancheront les gardes. Tant qu'elle est vide, un payload valide sur
un événement déclaré est laissé passer : rien sur aucun flux, code 0. Ce
« laisser passer » est transitoire, faute de garde branchée, et le verrou ne le
promet pas.

Le contrat d'un gestionnaire : il reçoit le payload (un objet JSON décodé) —
SA copie, décodée à neuf pour chaque garde, qu'il peut muter sans aveugler la
suivante — et rend `None` pour laisser passer, ou un `Refus`. Le premier `Refus` l'emporte,
et les gardes suivantes ne sont pas appelées. Toute autre valeur, et toute
`BaseException` levée, est une faute de la garde, rendue en refus « garde en
faute » par le canal de l'hôte — jamais un laisser-passer silencieux, jamais un
traceback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from cadre.config import HoteInconnu
from cadre.hotes_evenements import TABLE, EvenementInconnu, natif

__all__ = [
    "HOTES_A_ENVELOPPE",
    "Gestionnaire",
    "Refus",
    "Reponse",
    "refus_d_entree",
    "refus_de_table",
    "repartir",
    "resoudre",
]

#: Les hôtes dont le refus est l'enveloppe JSON sur la sortie standard, code 0.
#: `claude` n'y est pas : son refus est la sortie d'erreur et le code 2. Un hôte
#: ajouté à `HOTES` sans décider de son canal est refusé par `_refuser` en
#: `HoteInconnu`, et le banc exige que `{"claude"} | HOTES_A_ENVELOPPE` égale
#: `HOTES`.
HOTES_A_ENVELOPPE: frozenset[str] = frozenset({"codex", "gemini", "copilot", "kimi"})

#: Le nom JSON d'un payload qui n'est pas un objet, pour la raison du refus.
_TYPES_JSON: Mapping[type, str] = MappingProxyType({
    list: "array", str: "string", int: "number", float: "number",
    bool: "boolean", type(None): "null",
})


@dataclass(frozen=True)
class Refus:
    """Le verdict d'une garde qui refuse : sa raison, une phrase non vide."""

    raison: str

    def __post_init__(self) -> None:
        if not isinstance(self.raison, str) or not self.raison.strip():
            raise ValueError("un refus porte sa raison, une phrase non vide")


@dataclass(frozen=True)
class Reponse:
    """Ce que la CLI écrit : la sortie standard, la sortie d'erreur, le code."""

    stdout: str
    stderr: str
    code: int


#: Une garde : le payload décodé en entrée ; `None` (laisser) ou `Refus`.
Gestionnaire = Callable[[Mapping[str, object]], "Refus | None"]

_LAISSER = Reponse("", "", 0)


def resoudre() -> Mapping[str, Sequence[Gestionnaire]]:
    """La table de PRODUCTION, événement canonique → gardes : VIDE.

    C'est la couture nommée pour T-00000863 (les gardes) et T-00000731 (la
    lecture de `kit.lock`). La CLI l'appelle à chaque invocation, par le
    module, pour qu'un banc la remplace sans toucher au répartiteur.
    """
    return MappingProxyType({})


def _ascii(texte: object) -> str:
    """`texte` en littéral JSON ASCII : guillemets, échappements, `\\uXXXX`."""
    return json.dumps(texte, ensure_ascii=True)


def _refuser(evenement: str, hote: str, raison: str) -> Reponse:
    """Le refus de `raison`, rendu par le canal de `hote`.

    `evenement` est l'argument tel que reçu : le nom canonique pour un
    événement connu, la saisie brute pour un inconnu.
    """
    if hote == "claude":
        return Reponse(
            "",
            f"cadre hook {_ascii(evenement)} --host claude : REFUS : {_ascii(raison)}\n",
            2,
        )
    if hote in HOTES_A_ENVELOPPE:
        enveloppe: dict[str, object] = {
            "hookSpecificOutput": {
                "hookEventName": evenement,
                "permissionDecision": "deny",
                "permissionDecisionReason": raison,
            }
        }
        if hote == "copilot":
            enveloppe["permissionDecision"] = "deny"
            enveloppe["permissionDecisionReason"] = raison
        return Reponse(
            json.dumps(enveloppe, ensure_ascii=True, separators=(",", ":")) + "\n",
            "",
            0,
        )
    raise HoteInconnu(f"hote sans canal de refus decide : {hote!r}.")


def refus_d_entree(evenement: str, hote: str, faute: BaseException) -> Reponse:
    """Le refus d'une entrée standard que la CLI n'a pas pu LIRE — toute
    `Exception` levée par la lecture, pas seulement `OSError` —, par le canal
    de `hote` : le nom du type de `faute` seul, jamais son message.

    La CLI lit, ce module décide : la raison est formée ICI. Lève
    `HoteInconnu` pour un hôte sans canal décidé, comme `_refuser`.
    """
    return _refuser(
        evenement, hote, f"cadre hook : entree standard illisible ({type(faute).__name__})")


def refus_de_table(evenement: str, hote: str, faute: BaseException) -> Reponse:
    """Le refus d'une table des gardes en faute, par le canal de `hote` : le
    nom du type de `faute` seul, jamais son message.

    La CLI l'appelle quand `resoudre()` lève ; `repartir`, quand l'entrée de
    l'événement n'est pas une séquence de gardes. Lève `HoteInconnu` pour un
    hôte sans canal décidé, comme `_refuser`.
    """
    return _refuser(
        evenement, hote, f"cadre hook : table des gardes en faute ({type(faute).__name__})")


def _raison_de(verdict: object) -> str:
    """La raison d'un `Refus` ; `TypeError` pour toute autre valeur.

    Lue UNE fois, sous la protection de `repartir` : une raison qui n'est pas
    une `str` (un `Refus` dérivé qui contourne `__post_init__`) ferait lever
    la sérialisation hors de cette protection.
    """
    if isinstance(verdict, Refus):
        raison = verdict.raison
        if isinstance(raison, str):
            return raison
    raise TypeError(f"une garde rend None ou un Refus, pas {type(verdict).__name__}")


def repartir(
    evenement: str,
    hote: str,
    brut: bytes,
    gestionnaires: Mapping[str, Sequence[Gestionnaire]],
) -> Reponse:
    """Le verdict de `cadre hook evenement --host hote` sur le payload `brut`.

    Lève `HoteInconnu` pour un hôte hors de `HOTES` (par `natif`) ; rend un
    refus par le canal de l'hôte pour chacun des sept refus du répartiteur
    (docstring du module, table et garde en faute comprises) et pour le
    premier `Refus` d'une garde ; rend « laisser passer » (rien, code 0) sinon.
    """
    try:
        graphie = natif(evenement, hote)
    except EvenementInconnu as exc:
        return _refuser(evenement, hote, f"cadre hook : {exc}")
    if graphie is None:
        return _refuser(
            evenement, hote,
            f"cadre hook : l'evenement {evenement} n'est pas declare par l'hote "
            f"{hote} ({TABLE[evenement][hote].raison})",
        )
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _refuser(
            evenement, hote,
            f"cadre hook : payload illisible, pas de l'UTF-8 strict "
            f"({exc.reason}, octet {exc.start})",
        )
    try:
        payload = json.loads(texte)
    except RecursionError:
        return _refuser(evenement, hote, "cadre hook : payload illisible, JSON trop imbrique")
    except ValueError as exc:
        return _refuser(evenement, hote, f"cadre hook : payload illisible, pas du JSON ({exc})")
    if not isinstance(payload, dict):
        return _refuser(
            evenement, hote,
            f"cadre hook : payload JSON de type {_TYPES_JSON.get(type(payload), '?')}, "
            "un objet est attendu",
        )
    # La table vient de `resoudre()`, une couture branchée par d'autres tâches :
    # une entrée qui n'est pas une séquence (une garde seule au lieu d'un
    # tuple) est une faute de TABLE, refusée, jamais un traceback.
    try:
        gardes = tuple(gestionnaires.get(evenement, ()))
    except BaseException as exc:  # noqa: BLE001 — toute faute de table refuse
        return refus_de_table(evenement, hote, exc)
    for gestionnaire in gardes:
        # FAIL-CLOSED : la garde est du code tiers au répartiteur. Tout ce
        # qu'elle lève — `BaseException` : un `SystemExit(0)` laisserait
        # passer en silence — et tout retour hors contrat (`_raison_de` lève
        # `TypeError`) devient un refus par le canal de l'hôte, le NOM du
        # type seul : `str(exc)` peut citer le payload.
        #
        # CHAQUE garde reçoit SA copie, décodée à neuf du même texte : un objet
        # partagé laisserait une garde qui le mute (`pop("tool_input")`) aveugler
        # la suivante, donc un laisser-passer en code 0 (revue de clôture
        # commune). `json.loads` plutôt que `copy.deepcopy` : aucun import hors
        # de la liste fermée (H9), et ce texte vient d'être décodé sans faute —
        # deepcopy, récursif en Python, lève `RecursionError` dès 600 niveaux
        # quand `json.loads` en accepte 20 000 (mesuré, 3.14.7), et la faute
        # serait imputée à la garde.
        try:
            verdict = gestionnaire(json.loads(texte))
            raison = None if verdict is None else _raison_de(verdict)
        except BaseException as exc:  # noqa: BLE001 — toute faute de garde refuse
            return _refuser(
                evenement, hote, f"cadre hook : garde en faute ({type(exc).__name__})")
        if raison is not None:
            return _refuser(evenement, hote, raison)
    return _LAISSER
