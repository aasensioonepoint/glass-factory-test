"""La chaîne du socle, lue dans le NOYAU (T-00000899, décision S-00003974).

`data/socle.json` porte, dans l'ordre, les noeuds de la chaîne de gates du kit.
Ce module la LIT et la VALIDE ; il ne l'exécute pas (la chaîne reste en prose,
T-012). Il la COMPARE dans `check_socle_integrity` (T-00000901, plus bas), qui
juge une chaîne effective et les défs des agents contre le socle que rend
`charger()`.

Trois choses sont voulues, et chacune a son témoin dans
`.agents/evals/test_cadre_socle_chaine.py`.

* **La chaîne vit dans le paquet, JAMAIS dans le dépôt adoptant.** `charger()`
  n'a AUCUN paramètre : aucune racine projet, aucun chemin, aucune couche de
  configuration ne peut lui être passé. Elle lit `pkg_root()/data/socle.json`
  et rien d'autre. `data/socle.json` n'est pas une couche de config : `config`
  ne le lit pas, et ce module ne lit pas `config`. BORNE : la garantie tient à
  `pkg_root()`, la racine du paquet chargé. La copie de `src/cadre` qu'un
  adoptant reçoit par la template est VENDORÉE dans son arbre ; ce module ne
  dit rien de son intégrité, qui est confiée à `check_socle_integrity`.
* **Un fichier illisible LÈVE.** Absent, binaire, JSON cassé ou trop imbriqué,
  clé répétée dans un même objet, lien qui sort du paquet, forme inconnue :
  `SocleIllisible`, qui nomme le fichier et la cause. Jamais un repli sur une
  chaîne par défaut, qui ferait « réussir » un run sur un socle qu'il n'a pas lu.
* **Les identifiants sont un vocabulaire de contrat.** ASCII minuscules ; un
  doublon, un accent ou une majuscule est refusé à la lecture.

Imports : seuls `paths` et `workspace` sont importés AU NIVEAU DU MODULE, et le
banc le tient. Une fonction qui a besoin d'un autre module du paquet l'importe
DANS SON CORPS — `check_socle_integrity` le fait pour `cadre.managed` : le
paquet minimal que le banc copie sous `python -I -S` reste alors suffisant pour
`charger()`.

`check_socle_integrity` (clause « socle inviolable » de la spec : la
configuration ne fait qu'INSÉRER) est une fonction PURE, sans E/S, jugée par
`.agents/evals/test_check_socle_integrity.py`. Elle rend un `Releve` : les
atteintes (un noeud du socle retiré, en double, réordonné — le noeud DÉPLACÉ,
hors de la plus longue sous-suite ordonnée, jamais son voisin —, désactivé ou
rendu non bloquant, drapeaux typés ; la déf d'un agent du socle absente,
étrangère — son `name` n'est pas celui de l'agent —, à marqueur illisible ou
modifiée depuis la pose de son checksum), chacune NOMMANT son gate ou son agent,
et les défs qu'elle n'a pas pu vérifier. Un gate inséré est accepté où qu'il
soit et quoi qu'il porte. BORNES, écrites pour qu'aucune ne passe pour tenue :

* Elle juge la chaîne EFFECTIVE qu'on lui passe, jamais un fichier. La forme de
  configuration qui la produit (clé `gates`) est celle de T-00000878, et le run
  qui l'appelle, échoue franchement et trace au ledger est T-00000902 : à ce
  jour, aucun run ne l'appelle et une clé de configuration n'est pas lue.
* Elle juge la chaîne DÉCLARÉE, pas le chemin qu'un run joue : la `condition`
  d'un noeud et la voie directe ne sont pas de son ressort.
* `socle.json` ne dit pas quels noeuds sont bloquants : elle ne refuse que
  l'ABAISSEMENT explicite (`Gate.bloquant` ni `None` ni `True`), jamais un
  caractère absent.
* Elle lit les identifiants, pas l'origine : un gate inséré qui prendrait l'id
  d'un noeud du socle retiré est indiscernable ici ; le refus d'un tel nom vit
  au chargement de la configuration (T-00000878).
* Les checksums portent sur les agents des noeuds (`Socle.agents()`), pas sur
  le reste du roster. Une déf NON MARQUÉE ou REPRISE (`cadre.managed: false`)
  n'est pas une atteinte : elle est RENDUE dans `Releve.non_verifiees`, parce
  qu'aucune empreinte attendue n'est tenue hors de la copie qui la porte.
* Sous apply-mode, une déf MARQUÉE est MODIFIÉE (`managed.py`, « CE QUE REPRIS
  NE COMPARE PAS ») : le volet checksum y rendrait une atteinte `checksum` par
  agent du socle ; décision à T-00000752.
* `def-etrangere` lit le `name` DÉCLARÉ (la première ligne `name` dont la valeur
  se lit : nue, entre guillemets doubles ou simples, commentaire de fin de ligne
  et BOM initial admis), pas le contenu : une ligne `name` illisible est passée
  et la suivante lue. Une déf qui porte le bon `name` sur le corps d'un autre agent
  passe ce volet ; seul le checksum d'une déf MARQUÉE la tient.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from cadre.paths import pkg_root
from cadre.workspace import HorsRacine, Workspace

__all__ = ["ATTEINTES", "Atteinte", "CHEMIN", "DefLue", "Gate", "Noeud", "Releve", "Socle",
           "SocleIllisible", "chaine_du_socle", "charger", "check_socle_integrity"]

#: Relatif à `pkg_root()`. Écrit UNE fois ici.
CHEMIN = "data/socle.json"

NATURES = ("agent", "humain", "deterministe")

_CLES_RACINE = frozenset({"$comment", "version_format", "chaine", "voie_directe_depuis"})
_CLES_NOEUD = frozenset({"id", "nature", "agents", "condition"})
_IDENTIFIANT = re.compile(r"^[a-z][a-z0-9-]*$")


class SocleIllisible(ValueError):
    """Le socle n'a pas pu être lu ; le message nomme le fichier et la cause."""


@dataclass(frozen=True)
class Noeud:
    id: str
    nature: str
    agents: tuple[str, ...]
    condition: str | None


@dataclass(frozen=True)
class Socle:
    chaine: tuple[Noeud, ...]
    voie_directe_depuis: str

    def ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.chaine)

    def voie_directe(self) -> tuple[str, ...]:
        """Les identifiants joués par la voie directe : `voie_directe_depuis` INCLUS."""
        ids = self.ids()
        return ids[ids.index(self.voie_directe_depuis):]

    def agents(self) -> tuple[str, ...]:
        """Les agents qui tiennent un noeud, dans l'ordre de la chaîne, chacun une fois."""
        vus: list[str] = []
        for noeud in self.chaine:
            for agent in noeud.agents:
                if agent not in vus:
                    vus.append(agent)
        return tuple(vus)


def _refus(source: str, cause: str) -> SocleIllisible:
    return SocleIllisible(f"{source} : {cause}")


def _identifiant(valeur: object, source: str, ou: str) -> str:
    # `fullmatch`, pas `match` : avec `match`, le `$` admet un saut de ligne final (« a\n »).
    if not isinstance(valeur, str) or not _IDENTIFIANT.fullmatch(valeur):
        raise _refus(source, f"{ou} doit etre un identifiant ASCII minuscule (vu {valeur!r})")
    return valeur


def _noeud(brut: object, rang: int, source: str) -> Noeud:
    ou = f"chaine[{rang}]"
    if not isinstance(brut, dict):
        raise _refus(source, f"{ou} doit etre un objet (vu {type(brut).__name__})")
    inconnues = sorted(set(brut) - _CLES_NOEUD)
    if inconnues:
        raise _refus(source, f"{ou} : cle inconnue {inconnues}")
    ident = _identifiant(brut.get("id"), source, f"{ou}.id")
    nature = brut.get("nature")
    if nature not in NATURES:
        raise _refus(source, f"{ou} ({ident}) : nature {nature!r} hors de {NATURES}")
    agents = brut.get("agents")
    if nature == "agent":
        if not isinstance(agents, list) or not agents:
            raise _refus(source, f"{ou} ({ident}) : un noeud `agent` porte au moins un agent")
        noms = tuple(_identifiant(a, source, f"{ou} ({ident}).agents") for a in agents)
    else:
        if agents is not None:
            raise _refus(source, f"{ou} ({ident}) : un noeud `{nature}` ne porte pas d'agents")
        noms = ()
    condition = brut.get("condition")
    if condition is not None:
        condition = _identifiant(condition, source, f"{ou} ({ident}).condition")
    return Noeud(ident, nature, noms, condition)


def _valider(brut: object, source: str) -> Socle:
    if not isinstance(brut, dict):
        raise _refus(source, f"la racine doit etre un objet (vu {type(brut).__name__})")
    inconnues = sorted(set(brut) - _CLES_RACINE)
    if inconnues:
        raise _refus(source, f"cle racine inconnue {inconnues}")
    # L'ENTIER 1, et lui seul : `True == 1` et `1.0 == 1` sont vrais en Python, d'où `type(...) is int`.
    version = brut.get("version_format")
    if type(version) is not int or version != 1:
        raise _refus(source, f"version_format {version!r} : seul l'entier 1 est connu")
    chaine = brut.get("chaine")
    if not isinstance(chaine, list) or not chaine:
        raise _refus(source, "`chaine` doit etre une liste non vide")
    noeuds = tuple(_noeud(n, i, source) for i, n in enumerate(chaine))
    ids = [n.id for n in noeuds]
    doublons = sorted({i for i in ids if ids.count(i) > 1})
    if doublons:
        raise _refus(source, f"identifiant en double {doublons}")
    depuis = brut.get("voie_directe_depuis")
    if depuis not in ids:
        raise _refus(source, f"voie_directe_depuis {depuis!r} n'est pas un noeud de la chaine")
    return Socle(noeuds, depuis)


def _sans_doublon(source: str):
    """`object_pairs_hook` : une cle repetee dans un meme objet LEVE (`json` garde la derniere en silence)."""
    def crochet(paires: list[tuple[str, object]]) -> dict:
        vues: set[str] = set()
        for cle, _ in paires:
            if cle in vues:
                raise _refus(source, f"cle JSON en double {cle!r}")
            vues.add(cle)
        return dict(paires)
    return crochet


def _lire(atelier: Workspace) -> Socle:
    """Lit `CHEMIN` sous `atelier`. `atelier` EST ANNOTÉ : c'est la forme que
    `check_orchestration_purity` sanctionne pour une E/S."""
    source = str(atelier.racine / CHEMIN)
    try:
        brut = atelier.read_text(CHEMIN)
    except (OSError, UnicodeDecodeError, HorsRacine) as exc:
        raise _refus(source, f"illisible — {exc}") from exc
    try:
        charge = json.loads(brut, object_pairs_hook=_sans_doublon(source))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise _refus(source, f"JSON invalide — {exc}") from exc
    return _valider(charge, source)


def charger() -> Socle:
    """La chaîne du socle. Aucun paramètre, aucun cache : voir le module."""
    return _lire(Workspace(pkg_root()))


# --------------------------------------------------------------------------
# check_socle_integrity (T-00000901) — PUR : aucune E/S, voir les bornes du module.
# --------------------------------------------------------------------------

#: Les natures d'atteinte. Une atteinte rend le socle INCOMPLET ; rien d'autre ne le rend tel.
ATTEINTES = ("retrait", "doublon", "reordonnancement", "desactivation", "non-bloquant",
             "def-absente", "def-etrangere", "marqueur-illisible", "checksum")


@dataclass(frozen=True)
class Gate:
    """Un gate de la chaîne EFFECTIVE d'un run : un noeud du socle ou un gate inséré.

    Drapeaux TYPÉS, jugés par identité : `actif` autre que le booléen `True`
    (`"false"`, `0`, `None`…) DÉSACTIVE le gate. `bloquant` : `None` quand rien
    ne surcharge le caractère du gate, `True` quand on le déclare bloquant ; toute
    autre valeur l'ABAISSE."""

    id: str
    actif: bool = True
    bloquant: bool | None = None


@dataclass(frozen=True)
class DefLue:
    """La déf d'un agent telle qu'elle a été lue : son chemin relatif, qui choisit la
    forme du marqueur (`managed.forme_de`), et son texte."""

    relatif: str
    texte: str


@dataclass(frozen=True)
class Atteinte:
    """Une atteinte au socle : sa nature (dans `ATTEINTES`) et le gate ou l'agent qu'elle NOMME."""

    nature: str
    cible: str
    detail: str

    def __str__(self) -> str:
        return f"{self.nature} : {self.cible} — {self.detail}"


@dataclass(frozen=True)
class Releve:
    """Le verdict : les atteintes, et les défs non vérifiées `(agent, état)` — un état
    `non_marque` ou `repris` de `managed.Etat`, rendu, jamais tu."""

    atteintes: tuple[Atteinte, ...]
    non_verifiees: tuple[tuple[str, str], ...]

    @property
    def intact(self) -> bool:
        return not self.atteintes


def chaine_du_socle(socle: Socle) -> tuple[Gate, ...]:
    """La chaîne effective qu'aucune configuration ne touche : les noeuds du socle, dans leur ordre."""
    return tuple(Gate(n.id) for n in socle.chaine)


def _atteintes_de_chaine(socle: Socle, chaine: tuple[Gate, ...]) -> list[Atteinte]:
    rang = {ident: k for k, ident in enumerate(socle.ids())}
    vus = [g.id for g in chaine if g.id in rang]
    atteintes: list[Atteinte] = []
    for ident in socle.ids():
        fois = vus.count(ident)
        if fois == 0:
            atteintes.append(Atteinte("retrait", ident, "noeud du socle absent de la chaine effective"))
        elif fois > 1:
            atteintes.append(Atteinte("doublon", ident, f"noeud du socle present {fois} fois ; "
                                      "seule l'insertion d'un gate NOUVEAU est admise"))
    # Les noeuds HORS de la plus longue sous-suite ordonnée sont les déplacés : c'est eux
    # qu'on nomme, jamais leur voisin (une paire voisine inversée nommerait le mauvais gate).
    uniques = [i for i in vus if vus.count(i) == 1]
    # La place de chaque unique DANS LA CHAÎNE JUGÉE : l'ancre du message est son prédécesseur
    # RÉEL, gate inséré ou doublon compris, jamais le précédent des seuls uniques.
    places = [p for p, g in enumerate(chaine) if g.id in uniques]
    rangs = [rang[i] for i in uniques]
    longueur, prec = [1] * len(rangs), [-1] * len(rangs)
    for j in range(len(rangs)):
        for i in range(j):
            if rangs[i] < rangs[j] and longueur[i] + 1 > longueur[j]:
                longueur[j], prec[j] = longueur[i] + 1, i
    gardes: set[int] = set()
    k = longueur.index(max(longueur)) if rangs else -1
    while k >= 0:
        gardes.add(k)
        k = prec[k]
    for k, ident in enumerate(uniques):
        if k not in gardes:
            ou = f"place apres {chaine[places[k] - 1].id}" if places[k] else "place en tete"
            atteintes.append(Atteinte("reordonnancement", ident, f"{ou}, hors de l'ordre du socle"))
    for g in chaine:
        if g.id not in rang:
            continue  # un gate insere : tout lui est permis, il ne touche aucun noeud du socle
        # Drapeaux TYPÉS : seul le booléen True tient `actif` ; None ou True tiennent `bloquant`.
        if g.actif is not True:
            atteintes.append(Atteinte("desactivation", g.id, "noeud du socle desactive"))
        if g.bloquant is not None and g.bloquant is not True:
            atteintes.append(Atteinte("non-bloquant", g.id, "noeud du socle rendu non bloquant"))
    return atteintes


#: Le `name` d'une déf : `name: x` (frontmatter Markdown) ou `name = "x"` (TOML) — nu, entre guillemets
#: doubles ou simples appariés, commentaire de fin de ligne admis —, la première ligne dont la valeur
#: se lit ainsi. Le nom est le groupe 2.
_NOM_DE_DEF = re.compile(r'''^name\s*[:=]\s*(["']?)([A-Za-z0-9._-]+)\1\s*(?:#.*)?$''', re.M)
#: U+FEFF, le BOM initial, retiré avant la lecture du `name` — écrit par `chr`, jamais brut
#: (même règle que `managed._BOM`).
_BOM = chr(0xFEFF)


def _atteintes_des_defs(socle: Socle, defs: dict[str, DefLue]) -> tuple[list[Atteinte], list[tuple[str, str]]]:
    from cadre import managed  # dans le corps : voir « Imports » au module

    atteintes: list[Atteinte] = []
    non_verifiees: list[tuple[str, str]] = []
    for agent in socle.agents():
        lue = defs.get(agent)
        if lue is None:
            atteintes.append(Atteinte("def-absente", agent, "aucune def lue pour cet agent du socle"))
            continue
        # La déf d'un AUTRE agent, même intacte, ne tient pas ce noeud : son checksum ne prouve rien ici.
        nom = _NOM_DE_DEF.search(lue.texte.lstrip(_BOM))
        if nom is None or nom.group(2) != agent:
            atteintes.append(Atteinte("def-etrangere", agent,
                                      f"{lue.relatif} : name {nom.group(2) if nom else 'absent'}, attendu {agent}"))
            continue
        try:
            etat = managed.verifier(lue.texte, managed.forme_de(lue.relatif))
        except (managed.MarqueurIllisible, managed.FormeInconnue) as exc:
            atteintes.append(Atteinte("marqueur-illisible", agent, f"{lue.relatif} : {exc}"))
            continue
        if etat is managed.Etat.MODIFIE:
            atteintes.append(Atteinte("checksum", agent,
                                      f"{lue.relatif} : le contenu ne correspond plus au checksum pose"))
        elif etat is not managed.Etat.INTACT:
            non_verifiees.append((agent, etat.value))
    return atteintes, non_verifiees


def check_socle_integrity(socle: Socle, chaine: tuple[Gate, ...], defs: dict[str, DefLue]) -> Releve:
    """Juge `chaine` (la chaîne effective d'un run) et `defs` (agent → déf lue) contre
    `socle`. PURE : l'appelant lit ; un agent du socle absent de `defs` est une
    `def-absente`. Le socle est intact si et seulement si `Releve.atteintes` est vide."""
    de_chaine = _atteintes_de_chaine(socle, tuple(chaine))
    des_defs, non_verifiees = _atteintes_des_defs(socle, defs)
    return Releve(tuple(de_chaine + des_defs), tuple(non_verifiees))
