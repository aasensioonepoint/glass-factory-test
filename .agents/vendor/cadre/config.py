"""LA PRÉCÉDENCE DE CONFIGURATION, ET SA TRAÇABILITÉ. Phase 1 de T-012.

Quatre couches, de la plus faible à la plus forte :

    embarqué  <  utilisateur  <  hôte  <  projet

`embarqué` est le défaut livré dans la wheel. `utilisateur` vit sous
``CONFIG_HOME``. `hôte` est le réglage propre à Claude Code, Codex, Gemini,
Copilot ou Kimi. `projet` est ce que l'adoptant écrit dans son dépôt, et il
gagne toujours — c'est chez lui.

LA FUSION EST PROFONDE, ET CE CHOIX A UN COÛT QU'IL FAUT DIRE. Deux couches qui
déclarent chacune une partie d'une même table se combinent au lieu que la plus
forte efface l'autre : un projet qui règle un seul seuil n'a pas à recopier
toute la table embarquée pour la garder. Le coût est qu'on ne peut PAS retirer
une clé par surcharge — seulement la remplacer. C'est le compromis habituel, et
il est écrit ici plutôt que découvert par un adoptant qui essaie.

**LES LISTES SONT REMPLACÉES, JAMAIS CONCATÉNÉES.** Une allowlist fusionnée
serait la faute la plus chère de ce module : une couche faible y réinjecterait
des entrées qu'une couche forte croit avoir retirées. Une liste est donc une
VALEUR, comme un entier.

POURQUOI `explain` EXISTE. Une précédence à quatre couches sans moyen de savoir
d'où sort une valeur est une source de confusion nette : on lit un réglage, on
le change, rien ne bouge, et on cherche pendant vingt minutes. `explain` rend la
valeur EFFECTIVE, la couche qui l'a posée, et **les couches qu'elle a
recouvertes** — cette dernière moitié est ce qui répond à « pourquoi mon
changement ne prend pas ».

**ET « EFFECTIVE » VEUT DIRE EFFECTIVE, Y COMPRIS QUAND C'EST UNE TABLE.** La
première rédaction rendait la valeur BRUTE de la couche la plus forte : sur
`utilisateur {"seuil": 3, "mode": "strict"}` et `projet {"seuil": 5}`, la valeur
lue par le kit est `{"seuil": 5, "mode": "strict"}` et `explain` annonçait
`{"seuil": 5}` en disant recouvrir l'autre. Faux deux fois — `mode` survit, et
rien ne l'a recouvert. C'était le défaut le plus cher possible ici, parce qu'il
frappe exactement le cas où la fusion profonde rend la question intéressante, et
parce qu'un outil de diagnostic qui répond faux coûte plus cher que pas d'outil.
Quand plusieurs couches contribuent à une même table, la poseuse est donc
nommée `fusion(...)` et TOUTES les contributrices sont listées.

LES E/S PASSENT PAR `Workspace`, ET CE N'EST PAS UNE FORMALITÉ. Chaque couche est
lue dans un `Workspace` enraciné sur SA racine, donc un nom d'hôte ne peut pas
sortir de `CONFIG_HOME` par construction — la validation de `HOTES` ci-dessous
est la seconde barrière, pas la seule. C'est aussi ce qui rend vrai l'invariant
`check_orchestration_purity` : ce module DÉCIDE d'une précédence, il ne touche
pas le disque lui-même.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cadre.paths import CadrePathError, agents_dir, config_home, pkg_root
from cadre.workspace import HorsRacine, Workspace

__all__ = [
    "COUCHES",
    "HOTES",
    "HERITIERS",
    "HoteInconnu",
    "hote_cli",
    "Origine",
    "Config",
    "charger",
    "fusionner",
    "expliquer",
    "fichiers",
]

#: De la plus FAIBLE à la plus FORTE. L'ordre est la précédence, et il est
#: écrit une fois : toute boucle de ce module l'emprunte plutôt que de le
#: réécrire, sinon deux ordres divergeraient en silence.
COUCHES = ("embarque", "utilisateur", "hote", "projet")

#: LES HÔTES SONT UNE LISTE FERMÉE, ET ELLE EST APPLIQUÉE. L'aide de la CLI
#: énumérait déjà ces cinq noms sans que rien ne les impose, et le nom était
#: interpolé nu dans un chemin : `--hote ../../x` et `--hote /abs/x` faisaient
#: donc lire un JSON quelconque du disque COMME UNE COUCHE DE CONFIGURATION
#: (mesuré le 2026-09-12). C'est L-00000187 — une énumération sous un titre
#: universel est un mensonge différé — sur une surface neuve.
HOTES = ("claude", "codex", "gemini", "copilot", "kimi")

#: LES HÉRITIERS RESTENT HORS DE `HOTES` : ils ne servent qu'à ORIENTER le refus.
#: Antigravity partage la doctrine et les hooks de Gemini (décision pilote
#: S-00001606) et s'active par l'hôte `gemini`. SOURCE PYTHON UNIQUE, réexportée
#: par `hotes_evenements` (S-00004509) : ce module ne l'importe pas, le sens
#: config → hotes_evenements reste sans cycle. `test_cadre_config` exige
#: l'IDENTITÉ des deux noms, jamais une égalité de copies. Hors de Python,
#: `herite_de` de `data/capacites_hotes.json` en est une seconde déclaration,
#: liée par égalité (`test_registres_et_heritiers_egalent_capacites_hotes`) :
#: une divergence y rougit.
HERITIERS: Mapping[str, str] = MappingProxyType({"antigravity": "gemini"})
_HERITIERS = HERITIERS

_FICHIER = "cadre.json"


class HoteInconnu(ValueError):
    """Le nom d'hôte n'appartient pas à la liste fermée `HOTES`.

    Le message porte son REMÈDE quand l'hôte demandé est un héritier
    (`HERITIERS`) : l'hôte dont il hérite. PORTÉE, pour qu'on ne la lise pas
    plus large : DANS CE MODULE, le refus orienté n'est levé que par
    `_emplacements` (`charger`, `expliquer`, `fichiers`). La même classe est
    levée ailleurs avec un autre message : `cadre.init.initialiser` et
    `cadre.roster.corps_de` (n'orientent pas) et `hotes_evenements.natif` (oriente à la casse exacte
    seulement). La CLI ne la lève pas — ses options d'hôte refusent avant, par
    argparse —, mais elle porte le MÊME remède par `hote_cli`.
    """


def _heritier(hote: object) -> tuple[str, str] | None:
    """`(clé canonique, porteur)` quand `hote` nomme un héritier, sinon `None`.

    L'héritier se cherche sur le nom sans casse ni espaces de bord —
    `Antigravity` est le nom du produit tel qu'on le tape —, et par ÉGALITÉ
    seulement : une sous-chaîne enverrait `antigravity-x` vers gemini. Ce qui
    n'est pas une chaîne n'hérite de rien. UNE recherche, partagée par
    `_refus_hote` et `hote_cli` : CE module et la CLI orientent les mêmes noms
    — ni `initialiser` ni `natif`.
    """
    if not isinstance(hote, str):
        return None
    cle = hote.strip().casefold()
    porteur = _HERITIERS.get(cle)
    return None if porteur is None else (cle, porteur)


def _remede(cle: str, porteur: str) -> str:
    """La phrase qui oriente, nommant l'héritier par sa clé CANONIQUE."""
    return (f"{cle} herite de {porteur} (meme doctrine, memes hooks) : "
            f"utiliser l'hote {porteur!r}.")


def _refus_hote(hote: object) -> HoteInconnu:
    """Le refus d'un hôte hors de `HOTES`, orienté quand c'est un héritier.

    La saisie brute reste citée par `repr`, comme dans tout refus. Tout autre
    refus, chaîne ou non, garde son message d'avant.
    """
    admis = ", ".join(HOTES)
    trouve = _heritier(hote)
    if trouve is not None:
        return HoteInconnu(
            f"hote inconnu : {hote!r}. {_remede(*trouve)} Valeurs admises : {admis}."
        )
    return HoteInconnu(
        f"hote inconnu : {hote!r}. Valeurs admises : {admis}. "
        "Un nom d'hote est un identifiant, jamais un chemin."
    )


def hote_cli(valeur: str) -> str:
    """Le `type=` des options d'hôte de la CLI : oriente un héritier, rien d'autre.

    argparse applique `type` AVANT `choices` (documenté : « checked after any
    type conversions » ; mesuré sous 3.11, 3.12 et 3.14), donc c'est ici que
    le remède atteint la CLI. Un héritier lève `ArgumentTypeError` — refus en 2
    par argparse, qui GARDE sa formule « invalid choice » et y ajoute le
    remède : orienter n'est jamais accepter. TOUT AUTRE nom est rendu
    INCHANGÉ, et `choices=HOTES` en décide seul — son refus, avec la liste
    « choose from », reste celui d'argparse.
    """
    trouve = _heritier(valeur)
    if trouve is None:
        return valeur
    raise argparse.ArgumentTypeError(
        f"invalid choice: {valeur!r}. {_remede(*trouve)} "
        f"Valeurs admises : {', '.join(HOTES)}."
    )


@dataclass(frozen=True)
class Origine:
    """D'où sort une valeur effective, et ce qu'elle a recouvert."""

    cle: str
    valeur: Any
    couche: str
    recouvre: tuple[tuple[str, Any], ...] = field(default=())

    def rendu(self) -> str:
        lignes = [f"{self.cle} = {json.dumps(self.valeur, ensure_ascii=False)}",
                  f"  posee par : {self.couche}"]
        if self.recouvre:
            lignes.append("  recouvre  :")
            lignes += [f"    {c:12s} {json.dumps(v, ensure_ascii=False)}"
                       for c, v in self.recouvre]
        else:
            lignes.append("  recouvre  : rien — aucune couche plus faible ne la pose")
        return "\n".join(lignes)


def _emplacements(hote: str | None = None) -> dict[str, tuple[Workspace, str] | None]:
    """Par couche : (workspace enraciné sur SA racine, chemin relatif dedans).

    `paths` RÉSOUT, ce module DÉCIDE, `Workspace` LIT — et le confinement tombe
    de cette découpe plutôt que d'un contrôle ajouté : un nom d'hôte est un
    segment relatif dans `CONFIG_HOME`, donc `..` et l'absolu sont refusés par
    la racine elle-même. La couche projet peut manquer entièrement — hors d'un
    dépôt, une wheel installée reste utilisable — et son absence est un `None`,
    jamais une erreur remontée à l'appelant.
    """
    if hote is not None and hote not in HOTES:
        raise _refus_hote(hote)
    conf = Workspace(config_home())
    out: dict[str, tuple[Workspace, str] | None] = {
        "embarque": (Workspace(pkg_root()), f"data/{_FICHIER}"),
        "utilisateur": (conf, _FICHIER),
        "hote": (conf, f"hotes/{hote}.json") if hote else None,
    }
    try:
        out["projet"] = (Workspace(agents_dir()), _FICHIER)
    except CadrePathError:
        out["projet"] = None
    return out


def fichiers(hote: str | None = None) -> dict[str, Path | None]:
    """Le chemin de chaque couche, ou `None` quand la couche n'a pas de lieu.

    `None` DIT QUELQUE CHOSE, et c'est pourquoi ce n'est plus un chemin bidon.
    La première rédaction pointait la couche hôte sur un `hotes/aucun.json`
    quand aucun hôte n'était nommé : un fichier qu'un utilisateur pouvait créer,
    et qui se serait alors appliqué à toutes les invocations sans qu'aucune
    option ne le demande. La couche projet, elle, pointait `os.devnull`, qui
    n'est même pas un fichier régulier sous Windows.
    """
    out: dict[str, Path | None] = {}
    for nom, emplacement in _emplacements(hote).items():
        if emplacement is None:
            out[nom] = None
            continue
        atelier, relatif = emplacement
        out[nom] = atelier.racine / relatif
    return out


def _lire_couche(atelier: Workspace, relatif: str) -> dict[str, Any]:
    """Une couche absente rend {} ; un fichier ILLISIBLE lève.

    La distinction est délibérée. L'absence est le régime normal — la plupart
    des couches n'existent pas. Un JSON malformé, lui, est une erreur que
    l'adoptant doit voir : l'avaler ferait appliquer silencieusement le défaut
    à la place de son réglage, ce qui est le pire des deux.

    `atelier` EST ANNOTÉ, et l'annotation n'est pas décorative :
    `check_orchestration_purity` sanctionne l'E/S faite à travers un `Workspace`
    et refuse celle faite sur un `Path` nu. Il lit le type DÉCLARÉ plutôt que de
    l'inférer — un banc qui devine se trompe en silence — donc un paramètre non
    annoté rendrait cette lecture indistinguable d'un accès disque direct.
    """
    try:
        if not atelier.exists(relatif):
            return {}
        brut = atelier.read_text(relatif)
    except HorsRacine as exc:
        raise ValueError(f"{relatif} : couche hors de sa racine — {exc}") from exc
    try:
        charge = json.loads(brut)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{atelier.racine / relatif} : JSON invalide — {exc}") from exc
    if not isinstance(charge, dict):
        raise ValueError(
            f"{atelier.racine / relatif} : la racine doit etre un objet, "
            f"vu {type(charge).__name__}"
        )
    return charge


def fusionner(faible: dict[str, Any], fort: dict[str, Any]) -> dict[str, Any]:
    """Fusion PROFONDE des tables, REMPLACEMENT de tout le reste — listes
    comprises. Voir la docstring du module : une allowlist concaténée
    réinjecterait ce qu'une couche forte croit avoir retiré."""
    out = dict(faible)
    for cle, valeur in fort.items():
        if isinstance(valeur, dict) and isinstance(out.get(cle), dict):
            out[cle] = fusionner(out[cle], valeur)
        else:
            out[cle] = valeur
    return out


@dataclass
class Config:
    """La configuration effective, et la mémoire de chaque couche."""

    effective: dict[str, Any]
    par_couche: dict[str, dict[str, Any]]

    def get(self, cle: str, defaut: Any = None) -> Any:
        """Lit une clé pointée — `a.b.c` — dans la table effective."""
        courant: Any = self.effective
        for segment in cle.split("."):
            if not isinstance(courant, dict) or segment not in courant:
                return defaut
            courant = courant[segment]
        return courant


def charger(hote: str | None = None) -> Config:
    par_couche = {
        nom: ({} if emp is None else _lire_couche(emp[0], emp[1]))
        for nom, emp in _emplacements(hote).items()
    }
    effective: dict[str, Any] = {}
    for nom in COUCHES:
        effective = fusionner(effective, par_couche.get(nom, {}))
    return Config(effective=effective, par_couche=par_couche)


def expliquer(cle: str, hote: str | None = None) -> Origine:
    """D'où sort la valeur EFFECTIVE de `cle`, et ce qu'elle recouvre.

    La liste des recouvertes se lit DE LA PLUS FORTE À LA PLUS FAIBLE, parce que
    la question posée est « qu'est-ce qui a battu mon réglage », pas « quel est
    l'ordre du monde ».

    DEUX RÉGIMES, PARCE QUE LA FUSION EST PROFONDE. Sur une valeur scalaire — ou
    une liste, qui est une valeur ici — la couche la plus forte gagne ENTIÈREMENT
    et c'est elle la poseuse. Sur une table à laquelle plusieurs couches
    contribuent, aucune ne l'a « posée » : la valeur lue par le kit est leur
    fusion, donc la poseuse est `fusion(...)` et toutes les contributrices sont
    listées. Annoncer la table brute de la couche la plus forte, comme le faisait
    la première rédaction, rendait une valeur que le kit n'utilise nulle part.
    """
    cfg = charger(hote)
    vues: list[tuple[str, Any]] = []
    for nom in COUCHES:
        courant: Any = cfg.par_couche.get(nom, {})
        trouve = True
        for segment in cle.split("."):
            if not isinstance(courant, dict) or segment not in courant:
                trouve = False
                break
            courant = courant[segment]
        if trouve:
            vues.append((nom, courant))
    if not vues:
        return Origine(cle=cle, valeur=None, couche="aucune")

    # LA VALEUR VIENT DE LA TABLE EFFECTIVE, JAMAIS D'UNE COUCHE PRISE SEULE.
    effective = cfg.get(cle)
    fusionnees = [(nom, v) for nom, v in vues if isinstance(v, dict)]
    if len(fusionnees) > 1 and isinstance(effective, dict):
        contributrices = ",".join(nom for nom, _ in reversed(fusionnees))
        return Origine(cle=cle, valeur=effective, couche=f"fusion({contributrices})",
                       recouvre=tuple(reversed(vues)))
    poseuse, _ = vues[-1]
    return Origine(cle=cle, valeur=effective, couche=poseuse,
                   recouvre=tuple(reversed(vues[:-1])))
