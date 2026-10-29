#!/usr/bin/env python3
"""INTERFACE DE LECTURE DES MAGASINS D'ÉTAT — board, specs, ledger (STDLIB SEULE au chargement).

CE QU'ELLE EST. Un point de lecture commun aux trois magasins suivis, quelle que soit leur forme (monolithe,
enregistrements, les deux). Elle DÉLÈGUE chaque lecture au module PROPRIÉTAIRE du magasin (`tasks`, `specs`,
`ledger`) et ne lit jamais un octet de magasin elle-même : elle ne nomme aucun chemin de magasin, elle les tient
du propriétaire. Elle n'écrit RIEN, ne prend AUCUN verrou, ne touche pas `sys.path` et ne charge RIEN à l'import.

RÉSOLUTION DU PROPRIÉTAIRE, À CHAQUE APPEL. Chaque niveau n'est retenu que si la PORTE tient : chaque fonction
nommée existe et est `callable`, la classe d'erreur est une classe sous-classe d'`Exception` — sur `__main__`
comme sur `sys.modules[…]` ; une instance à laquelle manque UN attribut n'est pas retenue.
  1. `__main__`, pour le board seulement : sous `python3 tasks.py`, c'est la façade qui tient le verrou du
     processus, et un second module `tasks` l'ignorerait ;
  2. l'instance PUBLIQUE, `sys.modules["tasks" | "specs" | "ledger"]` ;
  3. la copie PRIVÉE déjà chargée, `sys.modules["_cadre_<module>_etat_lecture"]`, SEULEMENT si son `__file__`
     résolu est le frère attendu (un autre exemplaire de ce module, sous une autre racine, a pu la poser) ;
  4. sinon le frère du dossier de CE fichier, chargé PAR CHEMIN sous ce nom privé, enregistré dans `sys.modules`
     AVANT son exécution (T-00000134) et retiré s'il échoue. Absent ⇒ `FileNotFoundError` ; chargé mais hors
     PORTE ⇒ `ImportError` qui nomme l'attribut manquant.
La copie privée est RÉUTILISÉE tant que le public est absent : deux appels lèvent la MÊME classe, et le tuple
`erreurs_de_lecture(…)` pris AVANT un appel couvre l'exception de cet appel. Le public la SUPPLANTE dès qu'il
apparaît. Rien n'est retenu dans une variable de ce module : ce n'est pas un cache figé.

RÉSIDU NOMMÉ. Un propriétaire public qui APPARAÎT entre `erreurs_de_lecture` et l'appel n'est pas couvert par le
tuple déjà pris. Aucune exception de propriétaire n'est emballée : l'appelant reçoit la sienne.

VOCABULAIRE DE FORME. Les propriétaires en ont trois (`dossier`, `folder`, et le `store_mode` de specs) ; `forme`
rend le même pour les trois magasins : `absent`, `monolithe`, `enregistrements`, `les deux`. Pour specs, la table
vient des deux chemins du propriétaire (`store_path`, `journal_store_path`) testés par `.exists()`, en parité avec
`store_mode` — qui LÈVE sur les deux formes, là où `forme` les NOMME.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple

MAGASINS = ("board", "specs", "ledger")
ABSENT, MONOLITHE, ENREGISTREMENTS, LES_DEUX = "absent", "monolithe", "enregistrements", "les deux"


class EtatError(ValueError):
    """Un refus de l'interface ELLE-MÊME — magasin inconnu, board en deux formes pour `board_brut`, forme hors du
    vocabulaire de son propriétaire. Jamais une exception de propriétaire emballée."""


class _Proprietaire(NamedTuple):
    public: str
    fichier: str
    fonctions: tuple[str, ...]
    erreur: str
    main_admis: bool

    @property
    def prive(self) -> str:
        return f"_cadre_{self.public}_etat_lecture"


# La PORTE de chaque propriétaire. Board : `store_path` et `board_dir` en plus de la lecture, pour que le refus
# des deux formes de `board_brut` NOMME les deux chemins sans qu'aucun ne soit écrit ici.
_PROPRIETAIRES: dict[str, _Proprietaire] = {
    "board": _Proprietaire("tasks", "tasks.py",
                           ("store_form", "load", "lire_board_brut", "store_path", "board_dir"), "BoardError", True),
    "specs": _Proprietaire("specs", "specs.py",
                           ("store_mode", "store_path", "journal_store_path", "load", "read_journal"), "SpecsError",
                           False),
    "ledger": _Proprietaire("ledger", "ledger.py", ("store_form", "load"), "LedgerError", False),
}

# Le vocabulaire de `store_form` de chaque propriétaire, ramené au vocabulaire commun.
_VOCABULAIRE: dict[str, dict[str, str]] = {
    "board": {"absent": ABSENT, "monolithe": MONOLITHE, "dossier": ENREGISTREMENTS, "les deux": LES_DEUX},
    "ledger": {"absent": ABSENT, "monolith": MONOLITHE, "folder": ENREGISTREMENTS, "both": LES_DEUX},
}
# specs : (monolithe présent, journal présent) → forme.
_TABLE_SPECS: dict[tuple[bool, bool], str] = {
    (False, False): ABSENT, (True, False): MONOLITHE, (False, True): ENREGISTREMENTS, (True, True): LES_DEUX,
}


def _definition(magasin: str) -> _Proprietaire:
    try:
        return _PROPRIETAIRES[magasin]
    except KeyError:
        raise EtatError(f"magasin inconnu {magasin!r} — attendu l'un de {', '.join(MAGASINS)}") from None


def _manque(module: Any, definition: _Proprietaire) -> str | None:
    """Le premier attribut de la PORTE que `module` ne tient pas, ou `None` si elle tient."""
    if module is None:
        return "module absent"
    for nom in definition.fonctions:
        if not callable(getattr(module, nom, None)):
            return nom
    erreur = getattr(module, definition.erreur, None)
    if not (isinstance(erreur, type) and issubclass(erreur, Exception)):
        return definition.erreur
    return None


def _frere(fichier: str) -> Path:
    return Path(__file__).resolve().with_name(fichier)


def _est_le_frere(module: Any, attendu: Path) -> bool:
    """Réserve C1 : la copie privée n'est réutilisée que si elle EST le frère attendu, fichier résolu compris."""
    fichier = getattr(module, "__file__", None)
    if not fichier:
        return False
    try:
        return Path(fichier).resolve() == attendu
    except (OSError, RuntimeError):
        return False


def _charger_frere(nom: str, fichier: str) -> Any:
    """Le frère `fichier` du dossier de CE fichier, chargé PAR CHEMIN sous le nom privé `nom`, enregistré dans
    `sys.modules` AVANT son exécution (T-00000134) et retiré s'il échoue. Absent ⇒ `FileNotFoundError`.
    Patron recopié de `plan_cible._charger_frere`, SANS son cache de module."""
    import importlib.util

    chemin = _frere(fichier)
    if not chemin.is_file():
        raise FileNotFoundError(f"{chemin} : module frère ABSENT")
    spec = importlib.util.spec_from_file_location(nom, chemin)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"{chemin} : module frère illisible")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


def _proprietaire(magasin: str) -> Any:
    """Le module propriétaire de `magasin`, résolu MAINTENANT (docstring du module : quatre niveaux, une PORTE)."""
    definition = _definition(magasin)
    noms = ("__main__", definition.public) if definition.main_admis else (definition.public,)
    for nom in noms:
        module = sys.modules.get(nom)
        if _manque(module, definition) is None:
            return module
    attendu = _frere(definition.fichier)
    prive = sys.modules.get(definition.prive)
    if _manque(prive, definition) is None and _est_le_frere(prive, attendu):
        return prive
    module = _charger_frere(definition.prive, definition.fichier)
    manque = _manque(module, definition)
    if manque is not None:
        sys.modules.pop(definition.prive, None)
        raise ImportError(f"{attendu} : `{manque}` absent — le propriétaire du magasin {magasin} est hors PORTE")
    return module


# ---------------------------------------------------------------------------
# L'API — chaque fonction résout son propriétaire à l'appel et lui délègue.
# ---------------------------------------------------------------------------
def erreurs_de_lecture(*magasins: str) -> tuple[type[Exception], ...]:
    """Les classes d'erreur des propriétaires des magasins NOMMÉS, résolus à cet instant — chargés si besoin, et
    seulement eux. Un lecteur la prend AVANT son `try` de lecture : son tuple couvre alors l'exception de l'appel.
    Un nom inconnu est refusé AVANT tout chargement."""
    definitions = [_definition(m) for m in magasins]
    return tuple(getattr(_proprietaire(m), d.erreur) for m, d in zip(magasins, definitions))


def forme(root: str | Path, magasin: str) -> str:
    """`absent`, `monolithe`, `enregistrements` ou `les deux`. Board et ledger : le `store_form` du propriétaire,
    ses refus compris (lien, `entries` qui n'est pas un dossier). Specs : la table des deux chemins du propriétaire
    par `.exists()` — `store_mode` lève sur `les deux`, `forme` le nomme."""
    proprietaire = _proprietaire(magasin)
    if magasin == "specs":
        monolithe = proprietaire.store_path(root).exists()
        journal = proprietaire.journal_store_path(root).exists()
        return _TABLE_SPECS[(monolithe, journal)]
    brute = proprietaire.store_form(root)
    try:
        return _VOCABULAIRE[magasin][brute]
    except (KeyError, TypeError):
        raise EtatError(f"{magasin} : forme {brute!r} hors du vocabulaire de son propriétaire") from None


def present(root: str | Path, magasin: str) -> bool:
    """Le magasin existe sous AU MOINS une forme — `forme(root, magasin) != "absent"`, donc sur `.exists()`, comme
    `specs.store_mode`, `tasks.store_form` et `ledger.store_form`."""
    return forme(root, magasin) != ABSENT


def chemin_trace(root: str | Path) -> Path:
    """Le chemin du journal specs que trace un lecteur : le journal s'il existe, sinon le monolithe — les deux
    chemins du propriétaire, jamais un chemin écrit ici. Un chemin TRACÉ, pas une lecture : les deux formes se
    refusent à la lecture (`entrees_specs`)."""
    specs = _proprietaire("specs")
    journal = specs.journal_store_path(root)
    return journal if journal.exists() else specs.store_path(root)


def taches(root: str | Path) -> list[dict[str, Any]]:
    """Les tâches du board VALIDÉES, quelle que soit la forme : `load(root)["tasks"]` du propriétaire."""
    return _proprietaire("board").load(root)["tasks"]


def board_brut(root: str | Path) -> dict[str, Any]:
    """Le board BRUT (`lire_board_brut` du propriétaire), hors verrou. REFUSE les deux formes par une `EtatError`
    qui nomme les deux chemins — là où le propriétaire lirait le monolithe en silence."""
    tasks = _proprietaire("board")
    if tasks.store_form(root) == "les deux":
        raise EtatError(
            f"board en DEUX FORMES : {tasks.store_path(root)} à côté des enregistrements de {tasks.board_dir(root)} "
            f"— une vieille branche a ramené le monolithe ; lire l'un des deux serait un choix fait en silence. "
            f"Remède : retirer celui qui ne porte rien de neuf.")
    return tasks.lire_board_brut(root)


def entrees_specs(root: str | Path) -> list[dict[str, Any]]:
    """Les entrées du journal specs de `root`, quelle que soit la forme : `load(root)["entries"]` du propriétaire,
    qui refuse les deux formes et un journal corrompu."""
    return _proprietaire("specs").load(root)["entries"]


def entrees_journal_specs(chemin: str | Path) -> list[dict[str, Any]]:
    """Les entrées VALIDÉES du fichier journal `chemin` : `read_journal` du propriétaire. Un fichier, pas une
    racine : il ne voit pas un monolithe posé à côté."""
    return _proprietaire("specs").read_journal(chemin)


def entrees_ledger(root: str | Path) -> list[dict[str, Any]]:
    """Les entrées du ledger, quelle que soit la forme : `load(root)["entries"]` du propriétaire."""
    return _proprietaire("ledger").load(root)["entries"]
