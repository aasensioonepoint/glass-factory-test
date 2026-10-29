"""vendor_paths.py — OÙ vit le code des paquets `cadre` et `agentic_v3` d'une racine.

T-01M5BXTGX5YN8XEXTG1PP7A5ZX, phase R (décision S-01M5BQB9XKZN9F3Y3TZXE6T3KJ :
résolution compatible AVANT tout déplacement). Ce module ne déplace rien ; les
phases B à E l'ont branché : relevé à la clôture (`git grep -l vendor_paths`, bancs exclus), il est chargé PAR
CHEMIN par les deux conftest, `charge_poste`, `dashboard`, `etat_projection`, `event_store`, `migrate_index_to_db`,
`project_init`, `record_id`, `run_export` (moteur V3, v3prep), `setup_projet` et `tasks_sync` ; `setup_projet`
en RECOPIE aussi la règle (`_parent_cadre`, pour son refus avant toute jambe).

RÈGLE DE RÉSOLUTION, pour une racine R et un paquet P de `PAQUETS` :
  1. neuf    `R/.agents/vendor/P`              s'il porte `__init__.py` ;
  2. ancien  `R/src/cadre` ou `R/agentic_v3`   s'il porte `__init__.py` ;
  3. absent  : `None` (ou `PaquetIntrouvable`, au texte qui nomme les deux lieux).
LES DEUX présents : le NEUF gagne (`.agents/vendor`) — un arbre déplacé qui
garde son ancien emplacement exécute le code déplacé, jamais l'ancien.
Un répertoire SANS `__init__.py` n'est pas un paquet : il ne gagne pas (un
reste vide de déplacement ne masque pas l'emplacement qui porte le code).

RACINES ISOLÉES : la racine est un ARGUMENT, jamais lue dans le cwd, `__file__`
ou une variable d'environnement, et rien n'est mis en cache — deux racines
résolues dans le même processus rendent chacune ses propres chemins.

TROIS CANAUX D'IMPORT (annexe C9 / réserve C14 ; phase D, passes de correction) :
  - `charger_paquet` — CE QUE FONT `project_init.py`, `dashboard.py` et `setup_projet.py` pour
    `cadre` : le paquet EXACT de la racine chargé par chemin, enregistré dans
    `sys.modules` AVANT son exécution (un `import cadre.x` de son `__init__` se
    résout par le `__path__` du paquet, jamais par `sys.path`), PUIS
    `verifier_charge`. `sys.path` n'est PAS touché : `cadre` n'importe que la
    bibliothèque standard et lui-même, son parent n'y sert à rien, et le placer
    devant `site-packages` exposerait le `src/` de l'adoptant (ancienne
    disposition) à tout module absent de la bibliothèque standard de la
    plateforme — un `src/msvcrt.py` gagnait l'`import msvcrt` de la CLI sous
    POSIX. Ni un `cadre` porté par `PYTHONPATH` ou un `.pth` ne gagne, ni le
    `src/` de l'adoptant n'entre sur `sys.path`. Déjà dans `sys.modules` :
    seulement vérifié, `ProvenanceRefusee` s'il vient d'ailleurs.
    `setup_projet._charger` y passe depuis T-01M5BXTRP8GKS7DMDQCTKK88DZ
    (S-01M5CJ820Y) : ce module chargé PAR CHEMIN, `.agents/bin` seul en tête de
    `sys.path` — ni `src` ni `.agents/vendor` n'y entrent plus.
  - `inserer_en_tete` / `amorcer_cli` — le RANG seul (pont V3 de `tasks_sync`) :
    le parent est RETIRÉ de `sys.path` partout où il
    figure, PUIS inséré en tête de la ZONE DES PAQUETS TIERS — juste devant la
    première entrée `site-packages`/`dist-packages` qui suit la bibliothèque
    standard (sans elle, `-S` : juste derrière la dernière entrée de la
    bibliothèque standard, `lib-dynload` comprise ; sans aucune des deux : en
    tête). Un `if … not in sys.path: insert(0, …)` laisse un parent déjà en
    queue derrière un `cadre` installé (`.pth`) : refusé ici. JAMAIS devant la
    bibliothèque standard : en disposition ancienne le parent d'`agentic_v3` est
    la RACINE, et un `calendar.py` posé à la racine de l'adoptant masquerait le
    module standard. JAMAIS devant le `.agents/bin` du kit (`BIN`, le dossier de
    ce module) quand BIN figure sur `sys.path` — comparaison par chemin réel :
    un `tasks.py` à la racine masquerait `.agents/bin/tasks.py`. `amorcer_cli`
    exige ses `paquets` (aucun défaut).
    Ce que l'ordre SEUL ne tient PAS : toute entrée que Python place devant la
    bibliothèque standard (`PYTHONPATH`, le dossier courant sous `-c`, `-m` ou
    le REPL) et qui porte un `cadre` gagne un `import cadre` nu ; un parent déjà
    sur `PYTHONPATH` y est rétrogradé derrière la stdlib. D'où `charger_paquet`
    pour les CLI, et `verifier_charge` pour refuser un module chargé d'ailleurs.
  - `ajouter_en_queue` / `amorcer_conftest` — les conftest partagés laissent
    gagner le paquet de l'adoptant : `append`, seulement si absent.

LE MODULE CHARGÉ, pas seulement le disque (annexe C10/C15) : `verifier_charge`
compare le dossier de `sys.modules[paquet]` (résolu, `/tmp` ≡ `/private/tmp`)
au dossier que la règle désigne, et lève `ProvenanceRefusee` quand ils
diffèrent — un ancien arbre déjà importé ne passe jamais pour le neuf.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

PAQUETS: tuple[str, ...] = ("cadre", "agentic_v3")

# Emplacement NEUF, relatif à la racine : `<racine>/.agents/vendor/<paquet>`.
VENDOR = Path(".agents") / "vendor"

# Emplacements ANCIENS, relatifs à la racine (avant le déplacement vendor).
ANCIENS: dict[str, Path] = {
    "cadre": Path("src") / "cadre",
    "agentic_v3": Path("agentic_v3"),
}

NEUF = "vendor"
ANCIEN = "ancien"

# Le `.agents/bin` du kit qui exécute : `amorcer_cli` n'insère jamais devant lui.
BIN = Path(__file__).resolve().parent


class PaquetIntrouvable(LookupError):
    """Ni l'emplacement neuf ni l'ancien ne portent le paquet sous cette racine."""


class ProvenanceRefusee(ImportError):
    """Le paquet chargé n'est pas celui que la règle désigne sous cette racine."""


def _verifier(paquet: str) -> None:
    if paquet not in ANCIENS:
        raise ValueError(f"paquet inconnu : {paquet!r} (attendu : {', '.join(PAQUETS)})")


def _est_paquet(dossier: Path) -> bool:
    return (dossier / "__init__.py").is_file()


def resoudre(racine: Path | str, paquet: str) -> tuple[Path, str] | None:
    """`(dossier du paquet, provenance)` sous `racine`, ou `None` s'il est absent.

    Provenance : `NEUF` (« vendor ») ou `ANCIEN` (« ancien ») ; le neuf gagne."""
    _verifier(paquet)
    base = Path(racine).resolve()
    neuf = base / VENDOR / paquet
    if _est_paquet(neuf):
        return neuf, NEUF
    ancien = base / ANCIENS[paquet]
    if _est_paquet(ancien):
        return ancien, ANCIEN
    return None


def dossier_paquet(racine: Path | str, paquet: str) -> Path | None:
    """Le dossier du paquet (celui qui porte `__init__.py`), ou `None`."""
    trouve = resoudre(racine, paquet)
    return None if trouve is None else trouve[0]


def provenance(racine: Path | str, paquet: str) -> str | None:
    """`"vendor"`, `"ancien"`, ou `None` quand le paquet est absent."""
    trouve = resoudre(racine, paquet)
    return None if trouve is None else trouve[1]


def parent_import(racine: Path | str, paquet: str) -> Path | None:
    """Le répertoire à placer sur `sys.path` pour que `import <paquet>` lise CE
    dossier : `.agents/vendor`, `src` (cadre ancien) ou la racine (agentic_v3 ancien)."""
    dossier = dossier_paquet(racine, paquet)
    return None if dossier is None else dossier.parent


def exiger(racine: Path | str, paquet: str) -> Path:
    """Comme `dossier_paquet`, mais l'absence est un REFUS NOMMÉ."""
    dossier = dossier_paquet(racine, paquet)
    if dossier is None:
        base = Path(racine).resolve()
        raise PaquetIntrouvable(
            f"{paquet} introuvable sous {base} : ni {VENDOR / paquet} ni "
            f"{ANCIENS[paquet]} ne portent __init__.py — arbre incomplet, "
            "resynchroniser le kit"
        )
    return dossier


def verifier_charge(racine: Path | str, paquet: str) -> tuple[Path, str]:
    """Le paquet CHARGÉ (`sys.modules[paquet]`) est-il celui que la règle désigne
    sous `racine` ? Rend `(dossier, provenance)` ; sinon `ProvenanceRefusee`
    (non chargé, sans `__file__`, ou chargé d'un autre dossier). Les deux côtés
    sont résolus : un alias (`/tmp` → `/private/tmp`, lien symbolique) passe."""
    attendu = exiger(racine, paquet).resolve()
    origine = provenance(racine, paquet)
    module = sys.modules.get(paquet)
    if module is None:
        raise ProvenanceRefusee(
            f"{paquet} n'est pas chargé : rien à vérifier — le charger d'abord (charger_paquet)"
        )
    fichier = getattr(module, "__file__", None)
    if not fichier:
        raise ProvenanceRefusee(
            f"{paquet} chargé sans __file__ (paquet d'espace de noms ?), attendu {attendu}"
        )
    charge = Path(fichier).resolve().parent
    if charge != attendu:
        raise ProvenanceRefusee(
            f"{paquet} chargé depuis {charge}, attendu {attendu} ({origine}) — "
            "un autre arbre est déjà importé ; relancer dans un processus neuf"
        )
    return attendu, str(origine)


def _reel(chemin: str) -> str:
    return os.path.normcase(os.path.realpath(chemin))


def _meme_entree(entree: str, cible: str) -> bool:
    # L'entrée vide (« répertoire courant ») n'est jamais retirée : elle suit le cwd.
    # Chemin RÉEL des deux côtés : un lien symbolique ou `/tmp` ≡ `/private/tmp`
    # désigne la même entrée.
    if not entree:
        return False
    return _reel(entree) == _reel(cible)


# Noms de dossier qui ouvrent la zone des paquets tiers (et des `.pth`).
SITES = frozenset({"site-packages", "dist-packages"})


def _stdlib() -> frozenset[str]:
    """Les entrées de la bibliothèque standard : le dossier d'`os.py` et son
    `lib-dynload` (chemins réels). L'archive `pythonXY.zip` les précède toujours."""
    coeur = os.path.dirname(os.path.realpath(os.__file__))
    return frozenset({_reel(coeur), _reel(os.path.join(coeur, "lib-dynload"))})


def _rang_apres_bin(liste: list[str]) -> int:
    """Le rang qui suit la PREMIÈRE entrée `BIN` de `liste` (chemin réel des
    deux côtés), ou 0 sans elle."""
    for i, entree in enumerate(liste):
        if _meme_entree(entree, str(BIN)):
            return i + 1
    return 0


def _rang_insertion(liste: list[str]) -> int:
    """Devant la première entrée `SITES` qui suit la bibliothèque standard ;
    sans elle, derrière la dernière entrée de la bibliothèque standard ; sans
    aucune des deux, 0 — et jamais devant `BIN` quand BIN figure sur la liste."""
    stdlib = _stdlib()
    fin_stdlib = 0
    for i, entree in enumerate(liste):
        if entree and _reel(entree) in stdlib:
            fin_stdlib = i + 1
    rang = fin_stdlib
    for i in range(fin_stdlib, len(liste)):
        if os.path.normcase(os.path.basename(os.path.normpath(liste[i]))) in SITES:
            rang = i
            break
    return max(rang, _rang_apres_bin(liste))


def _placer(cibles: list[str], liste: list[str]) -> None:
    # RETIRER d'abord (le rang se calcule sur la liste purgée), puis insérer le
    # bloc d'un seul tenant : l'ordre de `cibles` est l'ordre final.
    liste[:] = [e for e in liste if not any(_meme_entree(e, c) for c in cibles)]
    rang = _rang_insertion(liste)
    liste[rang:rang] = cibles


def inserer_en_tete(chemin: Path | str, chemins: list[str] | None = None) -> None:
    """RETIRE `chemin` de `sys.path` partout où il figure, PUIS l'insère en tête
    de la zone des paquets tiers (réserve C14 : déjà présent en queue, il remonte
    quand même, devant tout `.pth`) : derrière la bibliothèque standard, et
    jamais devant `BIN` quand BIN figure sur sys.path."""
    liste = sys.path if chemins is None else chemins
    _placer([os.path.abspath(str(chemin))], liste)


def ajouter_en_queue(chemin: Path | str, chemins: list[str] | None = None) -> None:
    """`append` de `chemin`, seulement s'il n'y figure pas déjà (conftest :
    le paquet de l'adoptant, plus haut sur `sys.path`, garde la priorité)."""
    cible = os.path.abspath(str(chemin))
    liste = sys.path if chemins is None else chemins
    if not any(_meme_entree(e, cible) for e in liste):
        liste.append(cible)


def _parents(racine: Path | str, paquets: tuple[str, ...], strict: bool) -> list[Path]:
    vus: list[Path] = []
    for paquet in paquets:
        if strict:
            parent = exiger(racine, paquet).parent
        else:
            parent = parent_import(racine, paquet)
            if parent is None:
                continue
        if parent not in vus:
            vus.append(parent)
    return vus


def amorcer_cli(
    racine: Path | str,
    paquets: tuple[str, ...],
    chemins: list[str] | None = None,
) -> list[Path]:
    """Pour une CLI du kit : chaque parent RETIRÉ de `sys.path` puis inséré,
    d'un seul bloc, au rang d'`inserer_en_tete` — derrière la bibliothèque
    standard, devant `site-packages` et ses `.pth`, jamais devant `BIN` quand BIN
    figure sur sys.path —, dans l'ordre de `paquets` (le premier paquet finit
    premier). `paquets` est obligatoire : chaque CLI nomme ce qu'elle importe.
    Un paquet absent lève `PaquetIntrouvable` AVANT toute modification."""
    parents = _parents(racine, paquets, strict=True)
    liste = sys.path if chemins is None else chemins
    _placer([os.path.abspath(str(p)) for p in parents], liste)
    return parents


def charger_paquet(racine: Path | str, paquet: str) -> ModuleType:
    """Pour une CLI du kit : le paquet EXACT que la règle désigne sous `racine`,
    chargé par chemin et enregistré sous `paquet` dans `sys.modules` AVANT
    `exec_module` (retiré, sous-modules compris, si l'exécution lève), puis
    `verifier_charge`. `sys.path` n'est jamais modifié (ses sous-modules se
    résolvent par `__path__`). Déjà dans `sys.modules` : rien n'est rechargé,
    seule la provenance est vérifiée (`ProvenanceRefusee`). Paquet absent :
    `PaquetIntrouvable`, rien modifié."""
    dossier = exiger(racine, paquet)
    if paquet not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            paquet, dossier / "__init__.py", submodule_search_locations=[str(dossier)])
        if spec is None or spec.loader is None:  # pragma: no cover - défensif
            raise ProvenanceRefusee(f"{paquet} illisible sous {dossier}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[paquet] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            for nom in [n for n in sys.modules if n == paquet or n.startswith(paquet + ".")]:
                del sys.modules[nom]
            raise
    verifier_charge(racine, paquet)
    return sys.modules[paquet]


def amorcer_conftest(
    racine: Path | str,
    paquets: tuple[str, ...] = PAQUETS,
    chemins: list[str] | None = None,
) -> list[Path]:
    """Pour un conftest : chaque parent trouvé AJOUTÉ EN QUEUE s'il manque ;
    un paquet absent est sauté (rendu : les seuls parents considérés)."""
    parents = _parents(racine, paquets, strict=False)
    for parent in parents:
        ajouter_en_queue(parent, chemins)
    return parents
