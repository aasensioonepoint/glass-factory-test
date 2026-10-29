#!/usr/bin/env python3
"""project_init.py — DÉLÉGATEUR de l'identité du projet vers `cadre.init`.

T-00000048 (V1-a) l'a écrit ; T-00000969 (BK-121, Epic E-06) en a RELOGÉ toute
la logique dans `src/cadre/init.py` (`principal_project_init` et ses pièces),
où vit désormais la doctrine du fichier : identité git-ignorée générée sur
place, champs gelés et mutables, board provisionné à l'init et jamais écrasé,
création `O_EXCL` et réécriture atomique. Mêmes drapeaux, messages, canaux et
codes qu'avant — golden I11 de `.agents/evals/test_cadre_init.py`, relevé AVANT
le relogement. Divergence DÉCIDÉE — tags git decision/T-00000969/01 et /02 :
après `--rename`, `project.json` reprend le mode de sa création, 0644 masqué
par l'umask (0600 sous 077), même depuis 0600, là où l'ancien `mkstemp` le
passait en 0600. Les AUTRES écarts, tous sur des liens hors ou
dans la racine, sont bornés dans `cadre.init` (BORNES DU RELOGEMENT) ; le
contrat en processus de `main`, dans sa docstring ci-dessous.

CE QUI RESTE ICI, ET POURQUOI :
  * l'amorçage du parent de `cadre` (décision S-00002845, élargie par
    T-01M5BXTGX5YN8XEXTG1PP7A5ZX phase D) : le résolveur `vendor_paths.py`, frère
    chargé par chemin, désigne `.agents/vendor` sinon `src/` ; `charger_paquet`
    charge le paquet EXACT par chemin, sys.path intact, sous `cadre` (le code
    de l'adoptant dans `src/` n'entre jamais sur `sys.path`, la bibliothèque
    standard n'est donc jamais masquée) —
    un `cadre` installé (`.pth`) ou porté par `PYTHONPATH` ne gagne pas, un
    autre déjà chargé est refusé (`ProvenanceRefusee`) ; un arbre sans paquet
    `cadre` lève `PaquetIntrouvable` ;
  * des RÉ-EXPORTS NOMMÉS, ALIAS 1:1 des noms du paquet, pour les consommateurs
    EN PROCESSUS (`test_project_init.py`, `test_replace_parity.py`) — jamais des
    littéraux : muter `cadre.workspace.REMPLACER_DELAI_S` est entendu, rebinder
    `_REPLACE_DELAY_SECONDS` ici ne l'est pas (suite T-00000970) ;
  * `_BoardDuKit`, le fournisseur du board : `tasks` est un FRÈRE de ce fichier
    que `cadre` n'importe jamais, importé PARESSEUSEMENT (les gestes
    `--print-otel-env` et `--rename` n'en dépendent pas) ;
  * `main`.
Ce fichier reste `dette` sous la grammaire du shim (`shim_grammar.SHIMS_DU_KIT`) :
il garde des fautes (amorçage, classe, définitions). Sa bascule en `shim` est le
geste de T-00000665 ; le sort de `_BoardDuKit` sous la grammaire, une décision
que T-00000970 doit prendre.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _amorcer_cadre() -> None:
    """Le paquet `cadre` EXACT de CETTE racine (`vendor_paths.charger_paquet`)."""
    chemin = Path(__file__).resolve().with_name("vendor_paths.py")
    spec = importlib.util.spec_from_file_location("_project_init_vendor_paths", chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise ImportError(f"résolveur illisible : {chemin}")
    resolveur = importlib.util.module_from_spec(spec)
    existant = sys.modules.get(spec.name)
    sys.modules[spec.name] = resolveur  # enregistré AVANT `exec_module` (T-00000134) ; s'il lève, l'entrée d'avant
    try:
        spec.loader.exec_module(resolveur)
    except BaseException:
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    resolveur.charger_paquet(chemin.parents[2], "cadre")


_amorcer_cadre()

from cadre.init import (  # noqa: E402 — après l'amorçage de cadre
    chemin_identite,
    creer_identite_exclusive,
    principal_project_init,
    slugifier,
)
from cadre.workspace import (  # noqa: E402 — après l'amorçage de cadre
    REMPLACER_DELAI_S,
    REMPLACER_TENTATIVES,
    remplacer_avec_reprise,
)

# Ré-exports nommés (réserves C1 et C5) : ALIAS, jamais des copies.
project_json_path = chemin_identite
slugify = slugifier
_atomic_create = creer_identite_exclusive
_replace_with_retry = remplacer_avec_reprise
_REPLACE_ATTEMPTS = REMPLACER_TENTATIVES
_REPLACE_DELAY_SECONDS = REMPLACER_DELAI_S


class _BoardDuKit:
    """Le PROPRIÉTAIRE du board, injecté dans `cadre.init` : `tasks.store_path`
    / `tasks.view_path` pour les chemins, `tasks.save(racine, tasks.load(racine))`
    pour le board vide canonique et sa vue. Import paresseux, à l'appel : un
    échec d'import tombe dans la branche ATTENTION de `provisionner_stores`."""

    @staticmethod
    def _tasks():
        ici = str(Path(__file__).resolve().parent)
        if ici not in sys.path:
            sys.path.insert(0, ici)
        import tasks  # noqa: PLC0415 — import paresseux voulu, voir la docstring

        return tasks

    def chemins(self, racine: Path) -> tuple[Path, Path]:
        tasks = self._tasks()
        return tasks.store_path(racine), tasks.view_path(racine)

    def creer(self, racine: Path) -> None:
        tasks = self._tasks()
        tasks.save(racine, tasks.load(racine))


def main(argv: list[str] | None = None) -> int:
    """L'entrée, avec le board du kit injecté. CONTRAT MIXTE pour un appelant
    EN PROCESSUS : un refus métier (`RefusIdentite`) est RETOURNÉ, code 2,
    message sur stderr ; une erreur d'argparse (option inconnue, valeur
    manquante, `--format` hors liste) LÈVE `SystemExit(2)`, et `--help`
    `SystemExit(0)`. Sous `__main__` les deux finissent en code de sortie 2 —
    le golden I11 ne voit donc rien ; un appelant en processus attrape
    `SystemExit` s'il veut un code dans tous les cas. DIVERGENCE avec la base
    (mesurée, T-00000969) : son `_die` LEVAIT `SystemExit(2)` sur un refus
    métier aussi ; aucun appelant en processus de `main` dans l'arbre au
    relevé de T-00000969 (`git grep`)."""
    return principal_project_init(argv, board=_BoardDuKit())


if __name__ == "__main__":
    raise SystemExit(main())
