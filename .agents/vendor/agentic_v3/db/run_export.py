"""Export versionné des événements du run — clause « run par auteur ».

Ce module écrit l'export d'auteur `runs/<auteur>/<copie>/<AAAA-MM>.jsonl` : un
enregistrement JSON autonome par ligne (clés triées, LF, AJOUT SEUL), la
propriété (2) de « état partagé fusionnable » dont l'export de run est
l'**Exception nommée**. Il porte aussi le journal d'attente
(`state_project()/run/attente/<ulid>.json`) qui garde l'ordre d'écriture
texte -> projection et la reprise après arrêt.

IDENTITÉ D'AUTEUR — PSEUDONYMAT, JAMAIS ANONYMAT (décision pilote S-00001659).
`<auteur>` = `sha256(user.email git normalisé)[:16]`. Sur un ensemble de
contributeurs FERMÉ, cette empreinte NE rend PAS l'auteur anonyme : elle le
PSEUDONYMISE. L'historique git de ce dépôt porte un petit nombre d'adresses
distinctes, et la table d'équivalence complète se reconstruit en UNE commande
(hacher chaque adresse, comparer). L'empreinte est donc un IDENTIFIANT STABLE
DE CONTRIBUTEUR, corrélable par quiconque possède le dépôt, sans effort et pour
toujours. L'empreinte RESTE — la saler la rendrait non reconstructible entre
copies, cassant « run par auteur » pour un gain NUL en interne — et ce texte
cesse de promettre un anonymat qu'il ne tient pas. La borne vaut pour un
ensemble fermé ; elle n'est pas une raison de saler demain, c'est une raison de
ne pas ÉCRIRE qu'elle protège.

BACKFILL — VALEUR RÉSERVÉE DE `<copie>` (décision pilote S-00001594).
`identifiant_de_copie()` refuse de tirer, d'écrire ou d'accepter la valeur
littérale `backfill` pour une opération normale : sans ce refus, rien ne
distingue une ligne RECONSTRUITE d'une ligne OBSERVÉE dans un magasin en AJOUT
SEUL, c'est-à-dire irréparable par `git revert`. Le backfill écrit MALGRÉ ce
refus par la seule porte `backfill()` (keyword-only `_reserve=True`).

stdlib seule : `hashlib`, `json`, `secrets`, `datetime`, `sqlite3`, `argparse` —
`pyproject.toml` `dependencies` reste vide (contrat « stdlib seule »). Le backfill
et la CLI (`backfill`/`mesure`, T-00000677) lisent `events_ledger` par `sqlite3`.
"""

from __future__ import annotations

import argparse
import datetime
import errno
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import secrets
import shlex
import sqlite3
import stat
import sys
import threading
import time
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

__all__ = [
    "RunExportError",
    "AuteurIndisponible",
    "PanneInfrastructure",
    "RESERVE_BACKFILL",
    "empreinte_auteur",
    "identifiant_de_copie",
    "state_project",
    "project_root",
    "nouvel_ulid",
    "ulid_bien_forme",
    "chemin_export",
    "journal_attente",
    "preparer_journal_attente",
    "ecrire_journal_attente",
    "effacer_journal_attente",
    "ajouter_a_l_export",
    "lister_journaux_attente",
    "lire_journal_attente",
    "auteur_courant",
    "backfill",
    "BORNE_BACKFILL",
    "backfill_historique",
    "re_exporter_frappees",
    "mesurer_runs",
    "FORMAT_MARQUEUR",
    "EN_TETE_APPARENTEE",
    "lire_marqueur_partition",
    "assurer_marqueur_partition",
    "relever_partitions_apparentees",
    "signaler_partitions_apparentees",
]

#: Crockford base32, monotone en ASCII (identique à `cadre.ledger.ids`).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: La valeur de `<copie>` que seul le backfill de la tâche sœur peut porter.
RESERVE_BACKFILL = "backfill"

#: Code de sortie de `backfill` quand la base désignée est un store V3 REFUSÉ à
#: l'ouverture ou à la première lecture (`StoreV3Refuse`, T-00001054). Décision
#: pilote S-00003324 3b : « Le refus de store sort avec le code 4
#: (RC_STORE_REFUSE) ». Même valeur que `agentic_v3/cli.py::RC_STORE_REFUSE`,
#: LITTÉRALE et jamais importée : un import du paquet en tête casserait la forme
#: chemin (`python3 run_export.py`), dont `sys.path` est amorcé APRÈS les imports.
RC_STORE_REFUSE = 4


class RunExportError(RuntimeError):
    """Un export du run est refusé — auteur invalide, copie réservée, ou entrée
    malformée. AUCUNE écriture n'a lieu quand elle est levée."""


class AuteurIndisponible(RunExportError):
    """L'identité d'auteur (`git user.email`) est ABSENTE ou VIDE — l'export est
    donc REPORTABLE, PAS échoué (S-00001805 (2), S-00001806 T4).

    CONTRAT ENTRE DEUX FICHIERS, ÉCRIT ICI POUR QUE LE SITE AVAL NE L'INVENTE PAS.
    Le report d'export (`event_store.py`, chemin d'intégration) n'attrape QUE
    cette sous-classe : « identité absente » se DIFFÈRE (base écrite, journal
    conservé, export vide, convergence au rejeu). Une PANNE d'infrastructure —
    git absent (code 127), dépôt corrompu / `.git/config` illisible (128),
    timeout — lève au contraire `PanneInfrastructure`, sous-classe SŒUR de
    `RunExportError` (jamais cette sous-classe-ci).

    OÙ CETTE PANNE VA, ET C'EST DÉSORMAIS DEUX CHEMINS (T-00000695/696,
    borne de S-00001806 T4 au chemin où elle a un sens) :
      * CHEMIN D'ÉCRITURE (`_flush_export`, on tente RÉELLEMENT d'exporter) — il
        REMONTE fail-closed : au moment où l'on exporte, une panne PERMANENTE ne se
        différe pas comme un email manquant.
      * CHEMIN DE CONSTRUCTION (`_rejouer_journaux_attente`, à la NAISSANCE du
        store) — il est ATTRAPÉ, annoncé DISTINCTEMENT « PANNE … export BLOQUÉ
        jusqu'à réparation », et rend 0 : construire un store n'est PAS exporter,
        et TOUTE commande de board (y compris celles qui RÉPARENT la panne) le
        construit. La distinction que T4 exige tient toujours — le message porte
        PANNE et BLOQUÉ, jamais « auteur absent » — seule la mort du board part.

    `isinstance(AuteurIndisponible(), RunExportError)` reste VRAI : aucun banc ni
    aucun appelant existant attrapant `RunExportError` ne casse."""


class PanneInfrastructure(RunExportError):
    """`git config user.email` a ÉCHOUÉ — git absent ou cwd invalide (127), dépôt
    ou configuration illisible (128), lancement refusé (126), timeout (124) — ou
    n'a PAS PU ÊTRE LANCÉ, la couture `cadre.executor` étant introuvable OU en
    erreur : une PANNE, non reportable, et l'export est BLOQUÉ jusqu'à réparation
    (S-00001806 T4, S-00001859). Ou — depuis T-00000770 — la couture
    `cadre.ledger.store`, qui ouvre les bases SQLite sans suivre de lien, est
    introuvable ou en erreur : aucune base ne s'ouvre (site (b) ci-dessous).

    POURQUOI UN TYPE, ET PAS SEULEMENT UN MESSAGE (T-00000695/696, constat du
    binôme). Le chemin d'ÉCRITURE propage cette panne jusqu'à
    `tasks.py::drain_sync_outbox`, qui l'annonçait EN TÊTE comme « git user.email
    absent » — la SEULE cause qui ne peut PAS l'atteindre, `_flush_export`
    attrapant `AuteurIndisponible` en amont — et sans jamais dire PANNE ni
    BLOQUÉ, là où le chemin de CONSTRUCTION les disait. Or le drain ne voit qu'un
    `RunExportError` : une copie réservée ou un ULID malformé en sont aussi. Seul
    le TYPE lui permet de nommer la panne pour ce qu'elle est sans la prêter aux
    autres — la distinction était déjà PORTÉE PAR LE TYPE pour « auteur absent ».

    SOUS-CLASSE DE `RunExportError`, SŒUR d'`AuteurIndisponible` : tout appelant
    qui attrape `RunExportError` l'attrape encore, et `_rejouer_journaux_attente`
    continue d'attraper toute erreur de résolution d'auteur qui n'est pas un
    auteur absent. Levée par DEUX sites (T-00000770 en a ajouté un) : (a)
    `_email_git`, sur ses TROIS causes : `git config` en échec, la couture
    `cadre.executor` introuvable, ET cette couture trouvée mais en erreur
    (message distinct, exec-critic) ; (b) `_couture_ledger_store`, quand la
    couture `cadre.ledger.store` — la primitive d'ouverture NON SUIVIE des
    bases SQLite, que `_ouvrir_base_sqlite` et `agentic_v3.db.schema`
    (`create_tables`, `get_db_connection`) appellent — est introuvable ou en
    erreur : aucune base ne s'ouvre sans elle, ce n'est pas un refus
    d'emplacement. `_cli` la relève (rc 1, traceback), comme la première. CETTE
    PHRASE-CI, AVANT T-00000770, DISAIT « `_email_git` SEUL » ; et avant
    T-00000695/696 elle ne nommait que la PREMIÈRE des trois causes de (a)
    (exec-critic) : la seconde sortait de
    `_email_git` sans ce type — un `RunExportError` NU par la branche défensive de
    `_cadre`, et, mesuré, un `FileNotFoundError` par son repli PAR CHEMIN quand le
    fichier manque — donc le drain disait « DIFFÉRÉ … conservé pour rejeu » (ou
    « échec inattendu ») au lieu de PANNE, et la construction du store mourait
    au lieu d'annoncer la panne. `_email_git` enveloppe désormais l'accès à la
    couture."""


def _racine_depot() -> Path:
    chemin = Path(__file__).resolve()
    if chemin.parents[2].name == "vendor" and chemin.parents[3].name == ".agents":
        return chemin.parents[4]
    return chemin.parents[2]

def _vendor_paths() -> Any:
    chemin = _racine_depot() / ".agents" / "bin" / "vendor_paths.py"
    spec = importlib.util.spec_from_file_location("_vendor_paths_v3", chemin)
    if spec is None or spec.loader is None or not chemin.is_file():
        raise RunExportError(f"résolveur introuvable ({chemin})")
    module = sys.modules[spec.name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _dossier_cadre() -> Path:  # résolveur absent (arbre partiel) : `src/cadre`, le repli d'avant v3prep, sans lever
    racine = _racine_depot()
    return (_vendor_paths().dossier_paquet(racine, "cadre") if (racine / ".agents/bin/vendor_paths.py").is_file()
            else None) or racine / "src" / "cadre"
# Couture cadre.* (T-00000641, T-00000770) : (1) le paquet chargé de CE dossier (`_cadre_d_ici`), sinon (2) par chemin sous _SRC_CADRE (stdlib, U0).
_SRC_CADRE = _dossier_cadre()
_MODULES_CADRE: Dict[str, Any] = {}

def _cadre_d_ici() -> bool:  # (1) admise : aucun paquet sous `_SRC_CADRE`, ou le `cadre` chargé en vient (`verifier_charge`)
    try:
        return not (_SRC_CADRE / "__init__.py").is_file() or _vendor_paths().verifier_charge(_racine_depot(), "cadre") is not None
    except Exception:  # résolveur absent, `cadre` non chargé ou chargé d'un autre arbre : (2)
        return False

def _cadre(nom: str) -> Any:
    """`cadre.<nom>`, mémoïsé ; jamais `import_module` d'abord (S-01M5CN1KM2) : (1) si `_cadre_d_ici()`, sinon ou s'il lève (2) par chemin."""
    if _MODULES_CADRE.get(nom) is None:
        try:
            _MODULES_CADRE[nom] = importlib.import_module(f"cadre.{nom}") if _cadre_d_ici() else _charger_par_chemin(nom)
        except Exception:
            _MODULES_CADRE[nom] = _charger_par_chemin(nom)  # (2) repli PAR CHEMIN, déclaré
    return _MODULES_CADRE[nom]


def _charger_par_chemin(nom: str) -> Any:
    """Branche (2) de `_cadre`, extraite telle quelle (binôme F2 de T-00000770,
    pour que `_couture_ledger_store` la rejoue sur un paquet PÉRIMÉ) :
    `src/cadre/<nom>.py` chargé PAR CHEMIN sous `_cadre_<nom>_v3`, sans mémo."""
    chemin = _SRC_CADRE.joinpath(*nom.split(".")).with_suffix(".py")
    nom_module = "_cadre_" + nom.replace(".", "_") + "_v3"
    # T-00000691 (report T-00000689) : COPIE UNIQUE par processus. Le mémo
    # `_MODULES_CADRE` est propre à CETTE copie de `run_export` ; une seconde
    # copie (chargée par chemin ailleurs) exécutait le module une SECONDE fois,
    # d'état indépendant — deux horloges monotones d'ULID dans un processus.
    # `sys.modules` est partagé : on y relit la copie déjà chargée AVANT d'en
    # fabriquer une — MAIS SEULEMENT si elle vient du fichier ATTENDU
    # (addendum exec-critic, passe de revue T-00000691). Relue sans ce contrôle,
    # la copie en cache répondait même quand `_SRC_CADRE` désignait un dossier
    # SANS le fichier : la couture « introuvable » était trouvée, et deux témoins
    # (`test_couture_executor_introuvable_leve_PanneInfrastructure`,
    # `test_reconstruction_survit_a_la_couture_executor_introuvable`) rougissaient
    # dès que leur fichier tournait SEUL — masqués dans la porte combinée, où un
    # autre fichier met `src/` sur `sys.path` et fait gagner la branche (1).
    existant = sys.modules.get(nom_module)
    fichier_existant = getattr(existant, "__file__", None)
    if existant is not None and fichier_existant is not None and (
        Path(fichier_existant) == chemin
    ):
        return existant
    spec = importlib.util.spec_from_file_location(nom_module, chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise RunExportError(f"module cadre.{nom} introuvable ({chemin})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # (2) repli PAR CHEMIN, déclaré
    except BaseException:
        # Jamais une copie À MOITIÉ exécutée laissée à la relecture ; et la
        # copie VALIDE d'avant (autre fichier) est RENDUE à `sys.modules`,
        # pas effacée : un chargement raté d'ailleurs ne casse pas la copie
        # unique des autres appelants.
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    return module


def _paths() -> Any:
    return _cadre("paths")


def _couture_ledger_store() -> Tuple[Any, Any]:
    """`(cadre.ledger.store, cadre.workspace)` par la couture `_cadre` : la
    primitive d'ouverture NON SUIVIE des bases SQLite (`refuser_les_liens`,
    `ouvrir_sans_suivre`) et le `Workspace` qu'elle reçoit (T-00000770). Seul
    point d'accès de `agentic_v3/db/` à cette primitive — `_ouvrir_base_sqlite`
    et `schema.create_tables`/`get_db_connection` passent par ici.

    Couture INDISPONIBLE -> `PanneInfrastructure`, cause chaînée, message en DEUX
    cas, patron de `_email_git` : INTROUVABLE (`ImportError`,
    `FileNotFoundError` du repli par chemin, `RunExportError` défensif de
    `_cadre`) ; en ERREUR (toute autre `Exception`). Un module TROUVÉ sans la
    primitive — un paquet `cadre` installé antérieur à T-00000770 — n'arrête PAS
    la couture : elle retente PAR CHEMIN (`_charger_par_chemin`, binôme F2) et
    mémoïse la copie qui répond ; la panne (en ERREUR) ne tombe que si la copie
    par chemin échoue AUSSI, et nomme alors le module périmé (`__name__` ET
    `__file__`). Jamais une ouverture par `sqlite3.connect` nu, qui rouvrirait
    la fenêtre."""
    try:
        modules = []
        for nom, attributs in (("ledger.store", ("refuser_les_liens", "ouvrir_sans_suivre",
                                                 "EmplacementRefuse")),
                               ("workspace", ("Workspace",))):
            module = _cadre(nom)
            manque = [a for a in attributs if not callable(getattr(module, a, None))]
            if manque:
                perime = (f"{getattr(module, '__name__', module)} "
                          f"({getattr(module, '__file__', '?')}) ne porte pas "
                          f"{', '.join(manque)} (antérieur à T-00000770 ?)")
                try:
                    module = _charger_par_chemin(nom)
                except Exception as exc:
                    raise AttributeError(f"{perime} ; la copie par chemin a échoué aussi : "
                                         f"{type(exc).__name__}: {exc}") from exc
                encore = [a for a in attributs if not callable(getattr(module, a, None))]
                if encore:
                    raise AttributeError(
                        f"{perime} ; la copie par chemin {getattr(module, '__name__', module)} "
                        f"({getattr(module, '__file__', '?')}) ne porte pas "
                        f"{', '.join(encore)} non plus")
                _MODULES_CADRE[nom] = module
            modules.append(module)
        store_mod, workspace_mod = modules
    except (ImportError, FileNotFoundError, RunExportError) as exc:
        raise PanneInfrastructure(
            "couture cadre.ledger.store INTROUVABLE "
            f"({type(exc).__name__}: {exc}) : aucune base SQLite ne s'ouvre sans la "
            "primitive d'ouverture non suivie — PAS un refus d'emplacement (panne "
            "d'infrastructure, non reportable)."
        ) from exc
    except Exception as exc:
        raise PanneInfrastructure(
            f"couture cadre.ledger.store en ERREUR ({type(exc).__name__}: {exc}) : "
            "module trouvé, mais son chargement a levé ou il ne porte pas la "
            "primitive d'ouverture — aucune base SQLite ne s'ouvre sans elle."
        ) from exc
    return store_mod, workspace_mod


def state_project(depuis: Any = None) -> Path:
    """La partition d'état MACHINE du projet (`cadre.paths.state_project`), via la
    couture d'import — le point unique où `agentic_v3/db/` résout cette racine."""
    return _paths().state_project(depuis=depuis)


def project_root(depuis: Any = None) -> Path:
    """La racine du dépôt de travail (`cadre.paths.project_root`), via la couture
    d'import."""
    return _paths().project_root(depuis=depuis)


def nouvel_ulid(horodatage_ms: Optional[int] = None) -> str:
    """Un ULID (`cadre.ledger.ids.nouvel_ulid`, stdlib seule), via la couture
    d'import — pas de doublon embarqué."""
    return _cadre("ledger.ids").nouvel_ulid(horodatage_ms)


#: Longueur EXACTE d'un ULID produit par `nouvel_ulid` (10 temps + 16 aléa).
_LONGUEUR_ULID = 26


def ulid_bien_forme(ulid: Any) -> bool:
    """Vrai si `ulid` est EXACTEMENT 26 caractères de `_ALPHABET` (Crockford
    base32) — la seule forme que `nouvel_ulid()` produit. Sert de filtre EXPLICITE
    au chemin de reconstruction, qui lit des `.jsonl` versionnés et fusionnables
    entre contributeurs : une ligne hostile est ainsi SAUTÉE plutôt que suivie."""
    return (
        isinstance(ulid, str)
        and len(ulid) == _LONGUEUR_ULID
        and all(car in _ALPHABET for car in ulid)
    )


def _valider_ulid(ulid: Any) -> str:
    """Valide la FORME de `ulid` AVANT qu'il compose un composant de chemin, et
    lève `RunExportError` sinon (CONSTAT 1, revue sécurité). Un composant absolu
    (`/etc/…`) ou porteur de `..` écraserait le préfixe et livrerait une écriture
    ou une suppression HORS de la partition.

    DEUX sites du dépôt fabriquent un composant de chemin depuis un identifiant, et
    l'énoncé « un SEUL site » du correctif précédent était FAUX (constat majeur du
    binôme de clôture) : `journal_attente` compose depuis l'`ulid` (validé ici), et
    `chemin_export` depuis `<copie>` ET `<auteur>` (validés par `_valider_copie` ;
    `<auteur>` ne l'était pas avant T-00000697). Ces valeurs viennent d'un `.jsonl`
    versionné, du disque ou d'un mot-clé PUBLIC ; toutes sont contrôlées AVANT."""
    if not ulid_bien_forme(ulid):
        raise RunExportError(
            f"identifiant hors forme ULID (26 car. Crockford base32) : {ulid!r} — "
            "refus de composer un chemin (traversée de chemin, CONSTAT 1)."
        )
    return ulid


def _valider_copie(copie: Any, quoi: str = "identifiant de copie") -> str:
    """Valide la FORME d'un segment du chemin d'export AVANT qu'il le compose :
    `<copie>`, lu SUR DISQUE (`identifiant_de_copie`) ou passé par le mot-clé PUBLIC
    `copie=`, et `<auteur>`, passé par `auteur=` (T-00000697) ; `quoi` le nomme dans
    le refus. Absolue ou porteuse de `..`, la valeur écrirait HORS du dossier
    d'exports et HORS du dépôt (mesuré, constat majeur du binôme) ; porteuse d'un
    séparateur ou vide, elle décalerait la profondeur (`runs/` + `""` + `c` = `runs/c`)."""
    if (
        not isinstance(copie, str)
        or not copie
        or copie in (".", "..")
        or "/" in copie
        or "\\" in copie
        or "\x00" in copie
        or os.path.isabs(copie)
    ):
        raise RunExportError(
            f"{quoi} hors forme (segment de chemin unique attendu) : "
            f"{copie!r} — refus de composer un chemin d'export (traversée de chemin)."
        )
    return copie


# --- Identité d'auteur --------------------------------------------------------
def empreinte_auteur(email: str) -> str:
    """`sha256(email normalisé)[:16]`. Normalisation = `.strip().lower()` et RIEN
    d'autre. Email vide ou nul -> `RunExportError` nommant `user.email` : le
    « refus explicite de `cadre` », sans quoi tous les auteurs sans email
    partageraient un dossier commun."""
    normalise = (email or "").strip().lower()
    if not normalise:
        raise AuteurIndisponible(
            "git n'a rendu aucun user.email (clé ABSENTE ou configuration ILLISIBLE, "
            "rc=1 silencieux) : refus d'écrire un export sans auteur (clause « run par "
            "auteur »). L'export est REPORTABLE, pas échoué."
        )
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()[:16]


def _email_git(depuis: Any = None) -> str:
    """`git config user.email` LU PAR `Executor` (jamais un subprocess posé à la
    main).

    Résultat OK -> l'adresse (`.strip()`, éventuellement VIDE : le cas vide reste
    traité par `empreinte_auteur`, qui lève `AuteurIndisponible`). Résultat NON
    OK -> `PanneInfrastructure` (sous-classe de `RunExportError`) NOMMANT le code
    de retour ET le stderr — git absent OU cwd invalide 127, dépôt corrompu /
    config illisible 128, timeout 124, et lancement refusé (cwd qui est un
    fichier, binaire non exécutable) 126 ; codes rendus par `cadre.executor`,
    mesurés le 2026-09-23 (critic-fable T5 : cette phrase rangeait le cwd
    invalide sous 128) : sans quoi un dépôt cassé était annoncé « git user.email
    absent ou vide », cause MASQUÉE (S-00001805 (2), S-00001806 T4). Cette levée
    n'est PAS une `AuteurIndisponible` : une panne d'infrastructure n'est pas
    reportable.

    COUTURE `cadre.executor` INDISPONIBLE -> `PanneInfrastructure` AUSSI
    (T-00000695/696, exec-critic) : sans exécuteur, `git config` n'est jamais
    lancé, et c'est une panne au même titre qu'un git absent. L'accès est
    enveloppé ci-dessous, cause chaînée (`from exc`), et le message DISTINGUE
    deux cas (exec-critic, second tour) — un `except Exception` unique étiquetait
    « INTROUVABLE » une erreur de programmation d'un module TROUVÉ :
      * INTROUVABLE — `ImportError`, `FileNotFoundError` (repli par chemin sur un
        fichier absent) ou `RunExportError` (branche défensive de `_cadre`) ;
      * en ERREUR — toute autre `Exception` : module trouvé, mais son chargement
        ou son exécuteur a levé (`SyntaxError`, `AttributeError` d'un module sans
        `LocalExecutor`, constructeur qui lève…).
    `_paths()` ne l'est PAS, et c'est délibéré : le constat porte sur
    l'exécuteur, et une racine non résolue (`CadrePathError`) n'est pas une panne
    de git — l'envelopper ici la ferait annoncer « PANNE de résolution
    d'auteur » sous un nom qui n'est pas le sien."""
    try:
        executor = _cadre("executor").LocalExecutor()
    except (ImportError, FileNotFoundError, RunExportError) as exc:
        # paquet ET repli par chemin en échec : la couture est ABSENTE.
        raise PanneInfrastructure(
            "couture cadre.executor INTROUVABLE "
            f"({type(exc).__name__}: {exc}) : git config user.email n'a pas pu être "
            "lancé — PAS un auteur absent (panne d'infrastructure, non reportable)."
        ) from exc
    except Exception as exc:
        # Module TROUVÉ, mais en erreur : ne pas le dire introuvable, ce serait
        # envoyer chercher un fichier présent.
        raise PanneInfrastructure(
            f"couture cadre.executor en ERREUR ({type(exc).__name__}: {exc}) : "
            "module trouvé, mais son chargement ou son exécuteur a levé — git config "
            "user.email n'a pas pu être lancé (panne d'infrastructure, non reportable)."
        ) from exc
    racine = _paths().project_root(depuis=depuis)
    resultat = executor.run(["git", "config", "user.email"], cwd=racine)
    # F1 (BLOQUANT, binôme + bissection critic-fable, mesuré 2026-09-22) :
    # `git config <clé>` rend rc=1 AVEC stdout ET stderr VIDES quand git ne trouve
    # AUCUNE valeur pour la clé. Ce silence NE PROUVE PAS « clé non définie » à lui
    # seul (G2, mesuré 2026-09-22) : une configuration ILLISIBLE hors du dépôt —
    # `GIT_CONFIG_GLOBAL`, `HOME` ou `XDG_CONFIG_HOME` sur un fichier chmod 000 —
    # rend le MÊME rc=1 MUET. **CORRECTION D'UNE PRÉMISSE FAUSSE que ce commentaire
    # portait** (binôme, 3e tour) : un `.git/config` rendu illisible NE rend PAS ce
    # rc=1 muet — mesuré non-root, il rend **128 AVEC stderr** (« impossible
    # d'accéder à '.git/config' ») et part donc dans le chemin fail-closed — la
    # levée `PanneInfrastructure` de la branche `if not resultat.ok` ci-dessous,
    # ce que la docstring d'`AuteurIndisponible` disait déjà. L'exemple cité ici était probablement
    # mesuré sous root, où `chmod 000` ne refuse rien.
    # Les cas rc=1 MUETS sont le cas NOMINAL « aucun auteur », REPORTABLE ; ce filtre les
    # traite pareil À DESSEIN. Une panne d'infrastructure, elle, PARLE : rc 127/128
    # AVEC stderr, ou timeout — et part dans le chemin fail-closed ci-dessous.
    # `Resultat.ok` étant `code == 0`, le rc=1 muet partait sinon dans ce fail-closed,
    # et `empreinte_auteur("")` (SEUL site levant `AuteurIndisponible`) n'était JAMAIS
    # atteint : `tasks.py` mourait dans tout dépôt sans `git user.email` (adoptant, CI,
    # jambe conteneur en root). On rend "" — et NON lever `AuteurIndisponible` d'ici —
    # pour préserver le chemin « vide traité par `empreinte_auteur` » qu'un témoin épingle.
    if resultat.code == 1 and not resultat.expire and not resultat.stderr.strip():
        return ""
    if not resultat.ok:
        raise PanneInfrastructure(
            "git config user.email a ÉCHOUÉ "
            f"(code={resultat.code}, timeout={resultat.expire}) : "
            f"{resultat.stderr.strip()!r} — dépôt cassé ou git indisponible, "
            "PAS un auteur absent (panne d'infrastructure, non reportable)."
        )
    return resultat.stdout.strip()


def auteur_courant(depuis: Any = None) -> str:
    """L'empreinte de l'auteur courant, dérivée de `git config user.email`."""
    return empreinte_auteur(_email_git(depuis))


def _sonder_partition(partition: Path, depuis: Any) -> bool:
    """`partition.is_dir()` (la SONDE d'avant le `mkdir`) ET le refus d'une naissance de
    partition pour une racine jetable sans `CADRE_STATE_DIR` (T-00000753) : lève
    `EmplacementRefuse` AVANT que rien soit créé. Import PARESSEUX : `python3 run_export.py`
    n'a `agentic_v3` sur `sys.path` qu'après ses imports."""
    from agentic_v3.db import naissance_partition

    return naissance_partition.sonder_partition(partition, depuis)


def _fichier_copie(depuis: Any = None) -> Path:
    return _paths().state_project(depuis=depuis) / "run" / "copie"


def _run_copie() -> Any:
    """`run_copie` (lecture et tirage durcis de `run/copie`), import PARESSEUX."""
    from agentic_v3.db import run_copie

    return run_copie


def identifiant_de_copie(depuis: Any = None) -> str:
    """L'identifiant de copie, tiré au PREMIER usage (`secrets.token_hex(8)`, 16
    hex) et conservé sous `state_project()/run/copie`. Aucune information machine
    (ni nom d'hôte, ni utilisateur système, ni dossier personnel, ni IP) : un pur
    tirage aléatoire. REFUSE la valeur réservée `backfill` : une opération
    normale ne peut ni la tirer ni l'ACCEPTER. Lecture et tirage durcis : `run_copie`
    (refus dit, jamais réécrit ; publication `os.link`, le perdant relit le gagnant)."""
    run_copie = _run_copie()
    chemin = _fichier_copie(depuis)
    try:
        valeur = run_copie.lire_copie_disque(chemin)
        if valeur is not None:
            return valeur
        # T-00000692 : partition = `parents[1]` du chemin déjà résolu ; la SONDE
        # précède le `mkdir` pour que `origine` dise vrai (naissance/adoption).
        partition = chemin.parents[1]
        existait = _sonder_partition(partition, depuis)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        assurer_marqueur_partition(
            partition, depuis, origine="adoption" if existait else "naissance"
        )
        return run_copie.publier_copie(chemin)
    except run_copie.CopieRefusee as exc:
        raise RunExportError(str(exc)) from exc


# --- Chemins d'export et de journal d'attente ---------------------------------
def _mois_de_ulid(ulid: str) -> str:
    """`AAAA-MM` (UTC) décodé de l'horodatage EN TÊTE de l'ULID — jamais de
    l'horloge de lecture."""
    if not ulid or len(ulid) < 10:
        raise RunExportError(f"ULID malformé, mois indérivable : {ulid!r}")
    ms = 0
    for car in ulid[:10]:
        try:
            ms = ms * 32 + _ALPHABET.index(car.upper())
        except ValueError as exc:
            raise RunExportError(f"ULID malformé, mois indérivable : {ulid!r}") from exc
    dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m")


def chemin_export(
    ulid: str,
    *,
    depuis: Any = None,
    copie: Optional[str] = None,
    _reserve: bool = False,
    auteur: Optional[str] = None,
) -> Path:
    """`<racine>/runs/<auteur>/<copie>/<AAAA-MM>.jsonl`. `racine` = `project_root`,
    `<auteur>` dérivé de `git user.email` (résolu ici sauf `auteur=` fourni — voir
    plus bas), `<copie>` = `identifiant_de_copie()` sauf surcharge, `<AAAA-MM>`
    décodé de l'ULID. La valeur `backfill` de `copie` n'est acceptée QUE via la
    porte `_reserve=True` (`backfill()`).

    `auteur=` est un raccourci INTERNE : l'appelant qui rejoue N journaux résout
    l'empreinte UNE fois et la passe ici, au lieu d'un `git config user.email` par
    ligne (MAJEUR 4 du binôme — mesuré 4,41 s pour 300 journaux). `<auteur>` et
    `<copie>` composent chacun un segment de chemin : FORME validée (`_valider_copie`)."""
    if copie == RESERVE_BACKFILL and not _reserve:
        raise RunExportError(
            "la valeur « backfill » de <copie> est réservée au backfill "
            "(décision pilote S-00001594)."
        )
    racine = _paths().project_root(depuis=depuis)
    auteur_effectif = auteur if auteur is not None else auteur_courant(depuis)
    _valider_copie(auteur_effectif, "auteur")  # T-00000697, AVANT `identifiant_de_copie`
    copie_effective = _valider_copie(copie if copie is not None else identifiant_de_copie(depuis))
    mois = _mois_de_ulid(ulid)
    return Path(racine) / "runs" / auteur_effectif / copie_effective / f"{mois}.jsonl"


def journal_attente(ulid: str, *, depuis: Any = None) -> Path:
    """`state_project()/run/attente/<ulid>.json` — texte, NON versionné. `ulid` est
    VALIDÉ avant de composer le chemin : un identifiant absolu ou porteur de `..`
    est refusé (`RunExportError`) plutôt que suivi (CONSTAT 1, traversée de chemin)."""
    _valider_ulid(ulid)
    return _paths().state_project(depuis=depuis) / "run" / "attente" / f"{ulid}.json"


def preparer_journal_attente(ulid: str, *, depuis: Any = None) -> Path:
    """Chemin du journal de `ulid` (forme VALIDÉE d'abord), dossier créé, partition
    marquée ; rend le chemin. L'écrivain l'appelle AVANT son INSERT (T-00000805,
    critic-opus C1 : `assurer_marqueur_partition` peut lancer git)."""
    chemin = journal_attente(ulid, depuis=depuis)
    # T-00000692 : `<partition>/run/attente/<ulid>.json` → partition = `parents[2]` ;
    # sonde AVANT le `mkdir` (naissance/adoption dits vrais), marqueur juste après.
    partition = chemin.parents[2]
    existait = _sonder_partition(partition, depuis)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    assurer_marqueur_partition(
        partition, depuis, origine="adoption" if existait else "naissance"
    )
    return chemin


def ecrire_journal_attente(
    ligne: Dict[str, Any], *, depuis: Any = None, prepare: bool = False
) -> Path:
    """Écrit le journal d'attente de `ligne` (déjà rédigée), atomiquement ; rend son
    chemin. L'écrivain l'appelle APRÈS l'INSERT accepté, AVANT le commit, `prepare=True` :
    dossier et marqueur faits avant l'INSERT par `preparer_journal_attente` (T-00000805)."""
    ulid = ligne.get("ulid")
    if not ulid:
        raise RunExportError("ligne d'export sans ULID : journal d'attente refusé.")
    chemin = (journal_attente(ulid, depuis=depuis) if prepare
              else preparer_journal_attente(ulid, depuis=depuis))
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(
        json.dumps(ligne, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, chemin)
    return chemin


def effacer_journal_attente(chemin: Any) -> None:
    """Efface un journal d'attente s'il existe (étape (4), ou branche rollback)."""
    try:
        Path(chemin).unlink()
    except FileNotFoundError:
        pass


def lister_journaux_attente(*, depuis: Any = None) -> List[Path]:
    """Les journaux d'attente restants, `<ulid>.json` uniquement (jamais les
    `.tmp` d'une écriture interrompue)."""
    dossier = _paths().state_project(depuis=depuis) / "run" / "attente"
    if not dossier.is_dir():
        return []
    return sorted(p for p in dossier.glob("*.json") if p.is_file())


def lire_journal_attente(chemin: Any) -> Dict[str, Any]:
    """Relit une ligne d'export depuis son journal d'attente."""
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


# --- Verrou d'écriture de l'export (T2, S-00001806) --------------------------
#: Bornes du verrou, réglées dans le CORPS (jamais à l'import) — même forme
#: remplaçable que `tasks.py::board_lock`.
_VERROU_TIMEOUT_S = 30.0
_VERROU_POLL_S = 0.02

#: H2 (T-00000695/696) : ensemble des chemins de verrou TENUS par le thread courant,
#: pour rendre `_verrou_export` RÉENTRANT dans le processus. `flock`/`msvcrt.locking`
#: ne sont PAS réentrants sur un second descripteur : une imbrication s'auto-bloquerait
#: `_VERROU_TIMEOUT_S` (30 s en prod) puis lèverait. La sérialisation INTER-processus,
#: seule chose que ce verrou promette, reste tenue par le descripteur EXTERNE.
_verrous_tenus = threading.local()


def _fichier_verrou_export(depuis: Any = None) -> Path:
    """Le fichier de verrou de l'export, sous la partition d'état MACHINE
    (`state_project()/run/export.lock`) — JAMAIS sous `runs/` : un `.lock`
    versionné serait capté par `git add -- runs`. Hors dépôt, git-ignoré, comme
    le journal d'attente."""
    return _paths().state_project(depuis=depuis) / "run" / "export.lock"


@contextmanager
def _verrou_export(*, depuis: Any = None) -> Iterator[None]:
    """Sérialise le check-then-act de `ajouter_a_l_export`, sur le patron de
    `tasks_stockage.py::board_lock` (`fcntl.flock` POSIX / `msvcrt.locking`
    Windows, non bloquant + attente bornée à `_VERROU_TIMEOUT_S`) : même
    discipline de POIGNÉE (fermée sur toute sortie, T-00001080) ; DIFFÈRENT,
    notamment : la couture de poll (`time.sleep(_VERROU_POLL_S)` en ligne, pas
    `_lock_poll_sleep`), la ré-entrance (ensemble `tenus`, pas un compteur de
    profondeur), le `discard` de la marque, sous `if acquis`, et la clé de
    ré-entrance (`abspath`, sans `resolve()` ni `normcase`).

    CE QU'IL PROTÈGE — le cas MESURÉ (S-00001806 T2 : 3 exécutions, 2 processus,
    60 journaux → 61/60/1 DOUBLON) : deux processus de CE poste rejouent le MÊME
    journal (mode nuit, hooks, `tasks.py` concurrents) sous une identité git
    absente. Sans verrou, `_ulid_deja_exporte(chemin)` puis l'`append` forment un
    check-then-act : les deux lisent « absent » et ajoutent la MÊME ligne → un
    DOUBLON dans un magasin en AJOUT SEUL, IRRÉPARABLE par `git revert`. Le
    différé de b33d131 ne crée pas la course, il la rend ROUTINIÈRE.

    CE QU'IL NE PROTÈGE PAS, dit plutôt que supposé : `flock` est advisory et
    porte sur l'INODE d'UNE copie de l'arbre. DEUX machines — ou deux clones sur
    le même poste — ont chacun leur `export.lock` sous leur PROPRE partition
    d'état et ne se voient pas ; sur un système de fichiers RÉSEAU (NFS, SMB) la
    sémantique de `flock` n'est pas garantie ; et une écriture qui NE passe pas
    par cette fonction l'ignore. La déduplication O(n²) de `_ulid_deja_exporte`
    n'est PAS touchée ici (le verrou l'enveloppe sans changer son algorithme).

    RÉENTRANT DANS LE PROCESSUS (H2, T-00000695/696) : si CE thread tient déjà ce
    verrou, on rend la main SANS reverrouiller — `flock` non réentrant s'auto-
    bloquerait sinon `_VERROU_TIMEOUT_S`. La sérialisation INTER-processus est
    inchangée : elle est portée par le descripteur EXTERNE, déjà acquis."""
    chemin = _fichier_verrou_export(depuis)
    cle = os.path.abspath(str(chemin))
    tenus = getattr(_verrous_tenus, "chemins", None)
    if tenus is None:
        tenus = set()
        _verrous_tenus.chemins = tenus
    if cle in tenus:
        # Réentrance intra-processus : le descripteur EXTERNE de ce thread tient déjà
        # le flock. On ne reverrouille pas (auto-blocage garanti sinon), on yield.
        yield
        return
    # T-00000692 : `<partition>/run/export.lock` → partition = `parents[1]` ; sonde
    # AVANT le `mkdir`, marqueur juste après (jamais de relevé ici).
    partition = chemin.parents[1]
    existait = _sonder_partition(partition, depuis)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    assurer_marqueur_partition(
        partition, depuis, origine="adoption" if existait else "naissance"
    )
    handle = chemin.open("a+b")
    acquis = False
    try:
        if chemin.stat().st_size == 0:  # msvcrt.locking exige une région à verrouiller
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + _VERROU_TIMEOUT_S
        while not acquis:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquis = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise RunExportError(
                        f"verrou d'export non acquis en {_VERROU_TIMEOUT_S:.0f}s "
                        f"({chemin}) — un autre processus le retient-il ?"
                    ) from exc
                time.sleep(_VERROU_POLL_S)
        tenus.add(cle)
        yield
    finally:
        try:
            if acquis:
                tenus.discard(cle)
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# --- Marqueur interne de racine et partitions apparentées (T-00000692) --------
# Décision pilote S-00002199, options C+D : la CLÉ de partition ne change pas
# (`cadre.paths.state_project`), mais chaque partition porte un `racine.json` qui
# NOMME sa racine, et les partitions SŒURS apparentées au projet courant sont
# relevées à la naissance PUIS À CHAQUE APPARITION D'UNE SŒUR, et SIGNALÉES sur
# stderr à chaque construction du store du run, jusqu'à acquittement ou
# disparition (S-00002240 : le signal se RÉPÈTE ; un second clone VIVANT du même
# dépôt est signalé, acquittable ; l'acquittement est un fichier posé par
# l'orchestrateur sur instruction du pilote, jamais automatique).
# Jamais de migration, de fusion, de déplacement ni de suppression. État
# MACHINE, hors contrat public. Le code vit ICI et non dans `src/cadre/` :
# `paths.py` promet de ne rien écrire, et ce module est déjà le point unique où
# `agentic_v3/db/` résout la partition.
#: Version du format de `racine.json`. Un marqueur d'un autre format — ou dont
#: l'empreinte ne rend pas le nom du dossier — est ÉTRANGER : jamais lu comme
#: preuve, jamais réécrit.
FORMAT_MARQUEUR = 1
_NOM_MARQUEUR = "racine.json"
_NOM_APPARENTEES = "apparentees.json"
_NOM_ACQUITTEMENTS = "acquittements"
#: Le nom d'une partition sous `projets/` : l'empreinte `sha256(racine)[:16]`.
_NOM_PARTITION = re.compile(r"^[0-9a-f]{16}$")
#: Borne des sous-processus git de l'identité de racine, en secondes.
_IDENTITE_GIT_TIMEOUT_S = 30.0
#: L'en-tête du bloc de signal, recopié OCTET pour OCTET du critère E3 du plan
#: (apostrophe ASCII, `É` précomposé U+00C9) : c'est la chaîne que le pilote
#: `grep`. Une ligne par bloc, jamais répétée dans le corps.
EN_TETE_APPARENTEE = "PARTITION D'ÉTAT APPARENTÉE"


def _annoncer(message: str) -> None:
    """Une ligne sur stderr, jamais une levée : un marqueur est une INFORMATION,
    pas une condition de fonctionnement — la construction du store ne meurt
    jamais d'un signal qu'elle n'a pas pu émettre (stderr fermé, encodage)."""
    try:
        print(f"run_export: {message}", file=sys.stderr)
    except (OSError, ValueError):
        pass


def _maintenant_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lire_marqueur_partition(partition: Any) -> Optional[Dict[str, Any]]:
    """Le marqueur `racine.json` de `partition`, ou `None` s'il est ABSENT ou
    ÉTRANGER. Auto-vérification, jamais une levée : objet JSON, `format ==
    FORMAT_MARQUEUR`, `racine` chaîne dont l'empreinte — recalculée par
    `cadre.paths._empreinte_de_racine`, la MÊME fonction qui NOMME la partition,
    atteinte par la couture `_paths()` — ÉGALE le nom du dossier. Un marqueur
    étranger n'est pas une preuve et n'est jamais réécrit.

    Une `racine` NON IMPRIMABLE (`str.isprintable()` faux : retour à la ligne,
    caractère de contrôle) est ÉTRANGÈRE aussi : cette chaîne est la seule
    valeur LIBRE que le bloc de signal imprime, et un marqueur forgé ne doit pas
    pouvoir y injecter une ligne. BORNE, dite : une racine NON DÉCODABLE
    (`surrogateescape`, catégorie Cs) n'est pas imprimable non plus — son
    marqueur s'ÉCRIT (`_json_texte` l'échappe en ASCII) mais n'est jamais LU
    comme preuve : J1/J2 muettes pour elle, J3 seule la voit."""
    partition = Path(partition)
    try:
        obj = json.loads((partition / _NOM_MARQUEUR).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(obj, dict) or obj.get("format") != FORMAT_MARQUEUR:
        return None
    racine = obj.get("racine")
    if not isinstance(racine, str) or not racine or not racine.isprintable():
        return None
    try:
        empreinte = _paths()._empreinte_de_racine(Path(racine))
    except Exception:
        return None
    return obj if empreinte == partition.name else None


def _sans_identifiants(url: str) -> str:
    """`schéma://user:jeton@hôte:port/chemin?requête#fragment` →
    `schéma://hôte:port/chemin` : TOUTE la partie userinfo (jusqu'au DERNIER `@`
    du netloc, donc `u:p@ss@h` aussi), la query-string (`?access_token=…`) et le
    fragment sont retirés, par `urllib.parse.urlsplit` puis reconstruction —
    jamais par une expression sur `[^/@]*@`, qui laissait passer un `@` dans le
    mot de passe. La forme scp (`git@hôte:dépôt`, sans `://`) et un chemin local
    sont rendus INCHANGÉS : `urlsplit` n'y voit pas de netloc, et la forme scp
    ne porte qu'un nom d'utilisateur. Un hôte IPv6 est re-crocheté, un port
    invalide est omis, `hostname` est en minuscules (information seule)."""
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    hote = parts.hostname or ""
    if ":" in hote:
        hote = f"[{hote}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None:
        hote = f"{hote}:{port}"
    return urllib.parse.urlunsplit((parts.scheme, hote, parts.path, "", ""))


def _identite_git(racine: Path) -> Tuple[Optional[List[str]], Optional[str]]:
    """`(commits racines triés | None, remote.origin.url sans identifiants | None)`
    par `cadre.executor.LocalExecutor` — le patron de `_email_git`, jamais un
    `subprocess` nu.

    DÉCIDÉ PAR LE CODE DE RETOUR, JAMAIS PAR LE TEXTE, ET SILENCIEUX : hors dépôt
    git (rc 128), dépôt sans commit (128), git absent ou cwd invalide (127),
    expiration (124) ⇒ `None` sans un octet sur stderr — ce n'est pas une panne,
    c'est une jambe MUETTE (J2 ne tient pas, le marqueur s'écrit quand même).
    Clone SUPERFICIEL ⇒ `None` aussi (une racine greffée n'est pas un commit
    racine), décidé sur `git rev-parse --is-shallow-repository` rendant
    EXACTEMENT `true` ; un git ancien renvoie l'option en écho avec rc 0 et est
    donc lu comme NON superficiel — borne écrite. BORNE DE COÛT : `rev-list
    --max-parents=0 HEAD` parcourt TOUT l'historique — d'où « une fois par vie de
    partition » —, borné à `_IDENTITE_GIT_TIMEOUT_S`, expiration ⇒ `None`."""
    try:
        executor = _cadre("executor").LocalExecutor()
    except Exception:
        return None, None

    def _git(*args: str) -> Any:
        return executor.run(["git", *args], cwd=racine, timeout=_IDENTITE_GIT_TIMEOUT_S)

    commits: Optional[List[str]] = None
    r = _git("rev-list", "--max-parents=0", "HEAD")
    if r.ok:
        commits = sorted({l.strip() for l in r.stdout.splitlines() if l.strip()}) or None
        if commits is not None:
            s = _git("rev-parse", "--is-shallow-repository")
            if s.ok and s.stdout.strip() == "true":
                commits = None
    remote: Optional[str] = None
    u = _git("config", "--get", "remote.origin.url")
    if u.ok:
        remote = _sans_identifiants(u.stdout.strip()) or None
    return commits, remote


def _identite_racine(depuis: Any = None) -> Dict[str, Any]:
    """L'identité de la racine COURANTE telle que le marqueur la porte : `racine`
    (la chaîne `as_posix()` EXACTE que l'empreinte hache — `project_root(depuis)`
    RÉSOLUE, jamais la graphie tapée), `(dev, ino)` par `os.stat`, commits
    racines et remote par `_identite_git`."""
    racine = project_root(depuis).resolve()
    st = os.stat(racine)
    commits, remote = _identite_git(racine)
    return {
        "racine": racine.as_posix(),
        "dev": int(st.st_dev),
        "ino": int(st.st_ino),
        "commits_racines": commits,
        "remote": remote,
    }


def _json_texte(obj: Any) -> str:
    """Le texte JSON d'un marqueur ou d'un cache : `sort_keys`, indenté, ASCII PUR
    (`ensure_ascii` par défaut, JAMAIS `False`) et terminé par un retour à la
    ligne. Une racine NON DÉCODABLE porte des surrogates (`surrogateescape`,
    `'\\udce9'`) : avec `ensure_ascii=False`, `json.dumps` les rendait telles
    quelles et c'est l'ENCODAGE UTF-8 de l'écriture qui levait
    `UnicodeEncodeError` — pas `OSError` — et le marqueur ne s'écrivait jamais.
    Échappées en `\\udce9`, elles s'écrivent et se relisent à l'identique."""
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def _ecrire_tmp_unique(chemin: Path, texte: str) -> Path:
    """Écrit `texte` dans un temporaire au nom UNIQUE PAR APPEL à côté de `chemin`
    (`<nom>.<pid>.<8 hex aléatoires>.tmp`), créé en EXCLUSIF (`O_CREAT|O_EXCL`,
    mode 0o644) — jamais `write_text` sur un nom prévisible, qu'un fichier posé
    d'avance (lien symbolique compris) détournerait. Rend le chemin du
    temporaire ; propage l'`OSError` (dossier absent, lecture seule)."""
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as sortie:
            sortie.write(texte)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return tmp


def _ecrire_une_fois(chemin: Path, texte: str) -> bool:
    """Écrit `chemin` par tmp UNIQUE (`_ecrire_tmp_unique`) + création EXCLUSIVE
    — `os.link`, repli `open(x)` là où le lien dur n'est pas pris en charge —
    JAMAIS `os.replace` : un fichier déjà présent, étranger ou apparu
    entre-temps, reste octet pour octet. Rend Vrai si CETTE écriture a créé le
    fichier. Propage l'`OSError` de l'écriture du tmp (dossier absent, lecture
    seule) : l'appelant annonce."""
    tmp = _ecrire_tmp_unique(chemin, texte)
    try:
        try:
            os.link(tmp, chemin)
            return True
        except FileExistsError:
            return False
        except OSError:
            pass  # lien dur refusé par le FS ou la plateforme : repli exclusif
        try:
            with open(chemin, "x", encoding="utf-8") as sortie:
                sortie.write(texte)
            return True
        except FileExistsError:
            return False
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _ecrire_cache(chemin: Path, texte: str) -> None:
    """Écrit (ou RÉÉCRIT) `chemin` par tmp UNIQUE + `os.replace` : c'est le
    contrat d'un CACHE réécrivable (`apparentees.json`), l'inverse de celui du
    marqueur. Propage l'`OSError` ; le temporaire ne survit pas à un échec.
    BORNE (CONVENTIONS_python) : sous Windows, un `os.replace` concurrent d'un
    lecteur peut échouer — ici sans reprise, parce que le cache se RÉPARE seul :
    un cache absent ou illisible fait rejouer le relevé à la construction
    suivante."""
    tmp = _ecrire_tmp_unique(chemin, texte)
    try:
        os.replace(tmp, chemin)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def assurer_marqueur_partition(
    partition: Any, depuis: Any = None, *, origine: str = "naissance"
) -> Optional[Path]:
    """Pose `racine.json` dans `partition` s'il n'y est pas — UNE fois, jamais
    écrasé. Chemin rapide : UN `stat` si le fichier existe (étranger compris :
    jamais relu, jamais réécrit). Sinon : identité de la racine courante, REFUS
    d'écrire si son empreinte n'est pas le nom du dossier (ce dossier n'est pas
    la partition de cette racine), puis écriture tmp + création exclusive.
    `origine` = `naissance` (le dossier vient d'être créé) ou `adoption` (il
    existait sans marqueur : partition née par `cadre init`, `lessons_store`,
    `session_checkpoint`, `parse_specs`, ou avant ce lot). Rend le chemin du
    marqueur, ou `None` sans lever : toute panne (partition en lecture seule,
    disque plein, racine non résoluble) est ANNONCÉE sur stderr et AVALÉE — un
    marqueur est une information, jamais une condition de fonctionnement."""
    partition = Path(partition)
    chemin = partition / _NOM_MARQUEUR
    try:
        if chemin.exists():
            return chemin
        identite = _identite_racine(depuis)
        empreinte = _paths()._empreinte_de_racine(Path(identite["racine"]))
        if empreinte != partition.name:
            _annoncer(
                f"marqueur NON écrit dans {partition} : l'empreinte de la racine "
                f"courante ({empreinte}, {identite['racine']}) n'est pas le nom du "
                "dossier — ce dossier n'est pas la partition de cette racine."
            )
            return None
        obj = dict(
            identite, format=FORMAT_MARQUEUR, ecrit_le=_maintenant_utc(), origine=origine
        )
        _ecrire_une_fois(chemin, _json_texte(obj))
        return chemin
    except Exception as exc:
        _annoncer(
            f"marqueur de partition non écrit ({chemin}) : {type(exc).__name__}: {exc}"
        )
        return None


def _lire_copie(partition: Path) -> Optional[str]:
    """`run/copie` d'une partition par le lecteur durci (`run_copie` : ni lien, ni
    FIFO, borné, 16 hex, jamais `backfill`), sinon `None` — jamais de levée, pas
    même au chargement de `run_copie` (relevé best-effort à chaque `EventStore`)."""
    try:
        return _run_copie().lire_copie_disque(partition / "run" / "copie")
    except Exception:
        return None


def _copie_versionnee_ici(racine: Path, copie: str) -> bool:
    """Vrai si un dossier `runs/<auteur>/<copie>/` existe sous `racine` — lecture
    du système de fichiers, ZÉRO sous-processus."""
    try:
        auteurs = [
            e for e in (racine / "runs").iterdir()
            if _NOM_PARTITION.match(e.name) and e.is_dir()
        ]
    except OSError:
        return False
    return any((auteur / copie).is_dir() for auteur in auteurs)


def _soeurs(partition: Path) -> List[str]:
    """Les noms des partitions SŒURS de `partition`, triés : entrées de
    `partition.parent` (c'est `state_project(depuis).parent`, donc `projets/` ;
    `state_home()` n'est JAMAIS appelée et `corbeille/`, sœur de `projets/`, est
    hors champ par construction) au nom `^[0-9a-f]{16}$`, dossiers, hors la
    partition courante — par `os.scandir`, dont `is_dir()` lit le type d'entrée
    sans `stat` là où le système de fichiers le rend. Un `projets/` absent ou
    illisible rend `[]` sans rien créer."""
    try:
        with os.scandir(partition.parent) as entrees:
            return sorted(
                e.name for e in entrees
                if e.name != partition.name
                and _NOM_PARTITION.match(e.name)
                and e.is_dir()
            )
    except OSError:
        return []


def relever_partitions_apparentees(
    partition: Any, depuis: Any = None
) -> List[Dict[str, Any]]:
    """Le relevé des partitions SŒURS (`_soeurs`) apparentées à la racine
    courante — joué à la naissance de la partition, puis rejoué par
    `signaler_partitions_apparentees` à chaque APPARITION d'une sœur ou perte du
    cache, jamais à chaque construction. Une sœur est APPARENTÉE si au moins une
    jambe tient ; l'entrée nomme TOUTES les jambes tenues :

      * J1 même répertoire — son marqueur est valide ET ses `(dev, ino)` égalent
        ceux de la racine courante ET sa `racine` diffère : dossier renommé ou
        déplacé sur le même volume, ou autre graphie du même dossier. Non
        déclenchée par une copie (`cp -R`, `git clone` : inode neuf). BORNE, et
        ce n'est PAS « sûr » : un inode RECYCLÉ (ancien dossier supprimé, un
        nouveau reçoit le même numéro — ext4 le fait volontiers) rapproche à
        tort deux dépôts sans lien ; c'est un faux rapprochement ACQUITTABLE, pas
        une action, et jamais une suppression.
      * J2 même historique git — son marqueur et le courant portent chacun un
        ensemble NON VIDE de commits racines, d'intersection non vide. Muette
        (`null`) sans git, sans commit, ou sur un clone superficiel.
      * J3 exports versionnés ici — son `run/copie` (16 hex validés) égale un
        dossier `runs/<auteur>/<copie>/` sous la racine COURANTE. Seule jambe qui
        voit une partition SANS marqueur (née avant ce lot).

    Le courant est son marqueur s'il est valide, sinon l'identité VIVE (git
    rejoué : c'est le cas d'une partition où le marqueur n'a pas pu s'écrire, ou
    dont la racine n'est pas imprimable — borne : tant que `apparentees.json` ne
    peut pas s'écrire non plus, ce relevé est rejoué à chaque construction). Un
    `projets/` absent rend une liste vide sans rien créer. Jamais de levée sur
    une sœur illisible : elle est ignorée. COÛT : deux lectures par sœur
    (marqueur, `run/copie`) — 70–97 ms à chaud sur 1 200 sœurs (mesure du plan)."""
    partition = Path(partition)
    projets = partition.parent
    courant = lire_marqueur_partition(partition) or _identite_racine(depuis)
    racine_courante = Path(courant["racine"])
    commits_courants = {
        c for c in (courant.get("commits_racines") or []) if isinstance(c, str)
    }
    resultat: List[Dict[str, Any]] = []
    for nom in _soeurs(partition):
        entree = projets / nom
        jambes: List[str] = []
        marqueur = lire_marqueur_partition(entree)
        if marqueur is not None:
            if (
                marqueur.get("dev") == courant["dev"]
                and marqueur.get("ino") == courant["ino"]
                and marqueur["racine"] != courant["racine"]
            ):
                jambes.append("J1")
            leurs = marqueur.get("commits_racines")
            if (
                commits_courants
                and isinstance(leurs, list)
                and commits_courants & {c for c in leurs if isinstance(c, str)}
            ):
                jambes.append("J2")
        copie = _lire_copie(entree)
        if copie is not None and _copie_versionnee_ici(racine_courante, copie):
            jambes.append("J3")
        if jambes:
            resultat.append({
                "partition": entree.name,
                "racine": marqueur["racine"] if marqueur is not None else None,
                "copie": copie,
                "jambes": jambes,
            })
    return resultat


_JAMBES_LIBELLES = {
    "J1": "J1 même répertoire (dev, ino) — borne : un inode recyclé rapproche à tort, acquitter",
    "J2": "J2 même historique git (commit racine commun)",
    "J3": "J3 exports présents sous runs/ (run/copie {copie}, commités ou non)",
}
#: Quand J2 est la SEULE jambe tenue : un commit racine commun ne prouve pas le
#: même projet (template partagé, fusion d'historiques).
_NOTE_J2_SEULE = (
    "    (J2 seule : un dépôt issu du même template ou d'une fusion d'historiques "
    "partage ce commit racine — deux PROJETS différents ⇒ acquitter)"
)
#: Le geste de reprise, par jambe. J2/J3 : les événements de run ET le pont board
#: (liens, projections) se rebâtissent depuis runs/, seuls à l'ouverture d'une
#: base VIDE (T-00000691) ; base vivante synchronisée avec sauvegarde, sauf inhibition du kit ou AGENTS_V3_AUTO_SYNC=0. Sinon méthode Python
#: `EventStore.reconstruire_depuis_exports` — aucun verbe de `agentic_v3 cli`,
#: `cadre cli` ni `tasks.py` ne l'enveloppe.
_LIGNES_REPRISE = (
    "  reprise : J1 → déplacement voulu : acquitter ; sinon rendre au dossier son ancien chemin.",
    "    J2/J3 → les événements de run ET le pont board (liens, projections) se rebâtissent depuis runs/ :",
    "    base VIDE reconstruite (T-00000691) ; base vivante synchronisee apres sauvegarde, sauf inhibition ;",
    "    EventStore.reconstruire_depuis_exports, AUCUN verbe CLI — comparer les décomptes",
    "    avant de supprimer l'ancien clone ou l'ancienne partition.",
)


def _bloc_apparentee(
    partition: Path, racine_courante: str, entree: Dict[str, Any]
) -> Optional[str]:
    """Le bloc d'UNE sœur, ou `None` si le signal est TU pour elle : acquittée
    (`acquittements/<id>` présent) ou disparue de `projets/`. Chaque bloc ne
    parle que de SA sœur — jamais d'un récapitulatif, sans quoi un `grep` sur
    l'identifiant d'une sœur ACQUITTÉE la retrouverait encore (critère E4). Une
    `racine` du cache NON IMPRIMABLE est traitée comme inconnue : le cache est
    réécrivable, la garde de `lire_marqueur_partition` est donc redite ici."""
    ident = entree.get("partition")
    if not isinstance(ident, str) or not _NOM_PARTITION.match(ident):
        return None
    if (partition / _NOM_ACQUITTEMENTS / ident).exists():
        return None
    if not (partition.parent / ident).is_dir():
        return None
    racine = entree.get("racine")
    if isinstance(racine, str) and racine and racine.isprintable():
        presence = "encore présent" if Path(racine).is_dir() else "ABSENT du disque"
        ligne_racine = f"racine : {racine} ({presence})"
    else:
        ligne_racine = "sans marqueur : racine inconnue, partition née avant ce lot"
    jambes = [j for j in entree.get("jambes") or [] if j in _JAMBES_LIBELLES]
    copie = entree.get("copie") or "?"
    lignes_jambes = [
        "    - " + _JAMBES_LIBELLES[j].format(copie=copie) for j in jambes
    ]
    if jambes == ["J2"]:
        lignes_jambes.append(_NOTE_J2_SEULE)
    acq = shlex.quote(str(partition / _NOM_ACQUITTEMENTS))
    cible = shlex.quote(str(partition / _NOM_ACQUITTEMENTS / ident))
    return "\n".join([
        f"{EN_TETE_APPARENTEE} — {ident} ({ligne_racine})",
        f"  partition courante : {partition.name} (racine : {racine_courante})",
        "  jambes tenues :",
        *lignes_jambes,
        "  aucune migration ni fusion n'est faite ; rien n'est déplacé ni supprimé.",
        *_LIGNES_REPRISE,
        "  peut être un second clone VIVANT du même dépôt : acquitter.",
        "  acquitter (geste du pilote, tait ce signal) :",
        f"    mkdir -p {acq} && touch {cible}",
    ])


def _lire_cache_apparentees(fichier: Path) -> Optional[Tuple[List[str], List[Any]]]:
    """`(soeurs, apparentees)` du cache `apparentees.json`, ou `None` quand il faut
    REJOUER le relevé : fichier absent (silence), illisible ou hors forme —
    annoncé — c'est-à-dire tout sauf un objet `{"soeurs": [...], "apparentees":
    [...]}` ; la LISTE nue du lot précédent en fait partie et migre ainsi d'elle-
    même, sans geste."""
    try:
        texte = fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        _annoncer(
            f"cache des partitions apparentées illisible ({fichier}), relevé rejoué : "
            f"{type(exc).__name__}: {exc}"
        )
        return None
    try:
        obj = json.loads(texte)
    except (ValueError, RecursionError) as exc:
        _annoncer(
            f"cache des partitions apparentées illisible ({fichier}), relevé rejoué : "
            f"{type(exc).__name__}: {exc}"
        )
        return None
    soeurs = obj.get("soeurs") if isinstance(obj, dict) else None
    entrees = obj.get("apparentees") if isinstance(obj, dict) else None
    if not isinstance(soeurs, list) or not isinstance(entrees, list):
        _annoncer(
            f"cache des partitions apparentées hors forme ({fichier}), relevé rejoué"
        )
        return None
    return [s for s in soeurs if isinstance(s, str)], entrees


def signaler_partitions_apparentees(partition: Any, depuis: Any = None) -> int:
    """À CHAQUE appel : liste les sœurs (`_soeurs`, un `scandir` de `projets/`),
    relit le cache `apparentees.json` (`{"soeurs": [...], "apparentees": [...]}`),
    et REJOUE le relevé (`relever_partitions_apparentees`) si le cache est
    absent, illisible, hors forme (liste nue du lot précédent comprise) ou si une
    sœur est APPARUE depuis le dernier relevé (nom présent sur disque, absent de
    `soeurs`) — le cache est alors RÉÉCRIT (tmp unique + `os.replace`, c'est un
    cache, pas le marqueur). Puis écrit sur stderr un bloc `PARTITION D'ÉTAT
    APPARENTÉE` par entrée dont la partition existe encore sous `projets/` et qui
    n'est pas acquittée (`acquittements/<id>`). Rend le nombre de blocs émis.
    C'est ce qui tient S-00002240 « signal répété jusqu'à acquittement ou
    disparition » : X → Y → X, la partition de Y est une sœur apparue depuis le
    relevé de X, donc revue et signalée — un relevé figé à la naissance la
    manquait (constat F1 du binôme).

    COÛT PAR APPEL, mesuré sur ce poste (APFS, à chaud, moyenne de 50 appels) :
    le `scandir` seul — 0,06 ms sur 2 sœurs, 0,59 ms sur 1 200 (`is_dir()` sans
    `stat`) ; puis une lecture du cache et deux `stat` par entrée (trois quand le
    bloc s'écrit, pour dire si l'ancien chemin existe encore). BORNE : à froid
    ou sur un FS réseau le listage se paie en E/S, non mesuré ici. Le relevé
    lui-même (deux lectures par sœur, 70–97 ms sur 1 200) ne se paie qu'à
    l'apparition d'une sœur ; sur ce chemin-là `relever_partitions_apparentees`
    refait son propre `scandir` — second listage, rare et dit.

    CANAL : stderr de tout constructeur d'`EventStore` sur le chemin par défaut —
    les verbes de `tasks.py` qui drainent le pont V3 (`BoardBridge`, via
    `replay_sync`), `agentic_v3 status`, `agentic_v3 dashboard-summary` et
    `sync-spec` (`SpecParser`) — et non les seuls verbes mutants du board.
    BORNES : une DISPARITION ne rejoue rien (le bloc se tait de lui-même sur
    `is_dir`) ; une sœur DÉJÀ PRÉSENTE au dernier relevé et marquée DEPUIS n'est
    réévaluée qu'au prochain relevé — apparition d'une autre sœur ou perte du
    cache ; supprimer `apparentees.json` force donc un relevé ; un cache NON
    ENREGISTRABLE (partition en lecture seule) est annoncé, le signal part quand
    même depuis le relevé EN MÉMOIRE, et le relevé est rejoué à la prochaine
    construction ; des dépôts de banc aux commits racines figés (dates fixées)
    se rapprochent par J2 — bruit de banc, jamais une action. Jamais fatal :
    toute levée est annoncée et avalée."""
    partition = Path(partition)
    fichier = partition / _NOM_APPARENTEES
    emis = 0
    try:
        soeurs = _soeurs(partition)
        cache = _lire_cache_apparentees(fichier)
        entrees: List[Any]
        if cache is not None and not (set(soeurs) - set(cache[0])):
            entrees = cache[1]
        else:
            entrees = relever_partitions_apparentees(partition, depuis)
            try:
                _ecrire_cache(
                    fichier, _json_texte({"soeurs": soeurs, "apparentees": entrees})
                )
            except OSError as exc:
                _annoncer(
                    f"relevé des partitions apparentées non enregistré ({fichier}), "
                    f"rejoué à la prochaine construction : {type(exc).__name__}: {exc}"
                )
        if not entrees:
            return 0
        courant = lire_marqueur_partition(partition)
        racine_courante = (
            courant["racine"] if courant is not None
            else project_root(depuis).resolve().as_posix()
        )
        for entree in entrees:
            if not isinstance(entree, dict):
                continue
            bloc = _bloc_apparentee(partition, racine_courante, entree)
            if bloc is not None:
                try:
                    print(bloc, file=sys.stderr)
                except (OSError, ValueError):
                    pass
                emis += 1
        return emis
    except Exception as exc:
        _annoncer(
            f"signal des partitions apparentées interrompu ({partition}) : "
            f"{type(exc).__name__}: {exc}"
        )
        return emis


# --- Filet : un banc n'écrit pas sous la racine RÉELLE (T-00000696) -----------
def _racine_reelle() -> Path:
    """Racine réelle du dépôt ; fonction greffable par les bancs de non-fuite."""
    return _racine_depot()


def _exercice_depuis_un_banc() -> bool:
    """Vrai si l'écriture a lieu SOUS UN BANC pytest. Signal : la variable
    d'environnement `PYTEST_CURRENT_TEST`, que pytest POSE pendant chaque test et
    RETIRE au teardown — le seul signal de banc que CE dépôt produit déjà
    (mesuré : `python -m pytest` la pose ; aucun autre marqueur du kit ne l'égale
    en fiabilité).

    CE QU'IL NE DÉTECTE PAS, dit plutôt que découvert : un banc qui ne tourne PAS
    sous pytest (`python -m unittest`, `python -c`, un REPL) ne pose pas cette
    variable et PASSE au travers. Le filet vise la contamination MESURÉE (une
    suite pytest ayant écrit 8 lignes synthétiques sous le `runs/` réel), pas
    toute exécution imaginable."""
    return "PYTEST_CURRENT_TEST" in os.environ


def _refuser_ecriture_de_banc_sous_racine_reelle(chemin: Path) -> None:
    """REFUSE d'écrire `chemin` s'il tombe SOUS le `runs/` RÉEL du dépôt ALORS
    QUE l'on est exercé depuis un banc. C'est le filet au niveau MODULE que la
    fixture `autouse` de `test_board_bridge.py` (protection de TEST, contournable
    par toute exécution qui ne la charge pas) ne pouvait pas donner. Précédent de
    la MÊME classe : dans `core-scripts/run-bash-tests.sh`, le tableau `NESTED`
    et la boucle qui range dans `FOREIGN` toute suite trouvée sous un checkout
    imbriqué (un arbre imbriqué n'est pas le nôtre).

    TROIS PROPRIÉTÉS, chacune tenue par un témoin : il REFUSE une écriture de banc
    sous la racine réelle (remède NOMMÉ : `CADRE_PROJECT_ROOT` vers un tmpdir) ;
    il LAISSE PASSER une écriture de banc redirigée par `CADRE_PROJECT_ROOT` ; et
    il LAISSE PASSER une écriture de PRODUCTION (hors banc) sous la racine réelle
    — ce dernier point est le plus important, un filet qui bloquerait la
    production serait pire que le trou.

    BORNE : un filet posé dans l'arbre ne protège QUE les exécutions qui chargent
    CE module ; une copie PÉRIMÉE de l'arbre utilise son propre module périmé et
    passe au travers (d'où le retrait des copies périmées, fait le 22/09 par le
    pilote)."""
    if not _exercice_depuis_un_banc():
        return
    racine_runs = (_racine_reelle() / "runs").resolve()
    try:
        chemin.resolve().relative_to(racine_runs)
    except ValueError:
        return  # hors du runs/ réel (typiquement un CADRE_PROJECT_ROOT jetable) : OK
    raise RunExportError(
        f"écriture d'export REFUSÉE sous le runs/ RÉEL du dépôt ({racine_runs}) "
        "depuis un banc (PYTEST_CURRENT_TEST présent) : un test ne doit pas "
        "contaminer la surface versionnée. Remède : pose CADRE_PROJECT_ROOT vers "
        "un répertoire temporaire (tmpdir) avant d'exercer l'export."
    )


# --- runs/ SANS LIEN, en lecture COMME en écriture (T-00000691) ----------------
# `runs/` est VERSIONNÉ et FUSIONNABLE : un lien qui y entre par une fusion ne doit
# être suivi NULLE PART. Lecture (S-00002509, HIGH classe 1) : un `.jsonl` lié à
# `~/.ssh/id_rsa` était lu à l'ouverture d'une base vide. ÉCRITURE (S-00002557,
# HAUTE classe 1, critic-opus round 2) : `ajouter_a_l_export` suivait le lien d'un
# `<mois>.jsonl` fusionné vers un fichier de la victime (`.bashrc`) et y APPENDAIT
# une ligne JSON — mesuré. Un lien PHYSIQUE (`st_nlink > 1`) est refusé des deux
# côtés aussi (S-00002550, cohérence T-759) : git n'en livre pas, mais un fichier
# lié physiquement hors de l'arbre serait lu en entier, ou écrit en commun.
# IMPLÉMENTATION UNIQUE, partagée par la reconstruction (`event_store`), l'écrivain
# et `mesurer_runs` — deux parcours divergeraient en silence.
#
# RÉSIDU NOMMÉ, commun aux deux sens : un dossier remplacé par un lien PENDANT
# l'opération, par un processus local qui écrit sous runs/ au même instant, n'est
# vu que dans les fenêtres que ferment le `lstat` rejoué sous le verrou et
# l'identité `lstat` = `fstat` ; fermer tout exigerait un parcours par descripteurs
# (`dir_fd`/`openat`), absent de Windows. Un lien FUSIONNÉ, lui, est statique :
# refusé.

#: Drapeaux ajoutés à TOUTE ouverture d'un fichier sous runs/. `O_NOFOLLOW` — un
#: DERNIER composant lien fait échouer l'ouverture (`ELOOP`) au lieu d'ouvrir sa
#: cible ; `O_NONBLOCK` — un FIFO substitué n'y BLOQUE pas (le `fstat` le refuse
#: ensuite ; sans effet sur un fichier régulier) ; `O_CLOEXEC` ; `O_BINARY` sous
#: Windows (sans lui l'écriture traduirait LF en CRLF). Un drapeau absent de la
#: plateforme vaut 0 : Windows n'a pas d'`O_NOFOLLOW`, le `lstat` préalable y tient.
_DRAPEAUX_SANS_LIEN = (
    getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_BINARY", 0)
)

#: Ouverture en LECTURE d'un export (reconstruction, `mesurer_runs`).
_DRAPEAUX_LECTURE_EXPORT = os.O_RDONLY | _DRAPEAUX_SANS_LIEN


def _est_jonction(chemin: Any) -> bool:
    """Jonction Windows (Python 3.12+) — traitée comme un lien, jamais suivie."""
    jonction = getattr(Path(chemin), "is_junction", None)
    return bool(jonction is not None and jonction())


def _entrees(dossier: Path, erreurs: List[Tuple[Path, OSError]]) -> List["os.DirEntry[str]"]:
    """Les entrées de `dossier` par `os.scandir`, triées par nom — ou `[]` après
    avoir RANGÉ l'`OSError` dans `erreurs` (droits, disparition) : jamais avalée."""
    try:
        with os.scandir(dossier) as flux:
            return sorted(flux, key=lambda entree: entree.name)
    except OSError as exc:
        erreurs.append((dossier, exc))
        return []


def _nature(entree: "os.DirEntry[str]", erreurs: List[Tuple[Path, OSError]]) -> str:
    """`"lien"` (lien symbolique, ou jonction Windows 3.12+), `"dossier"` RÉEL ou
    `"autre"` — sans jamais suivre un lien ; `"erreur"` (rangée) si le type ne se
    lit pas."""
    try:
        jonction = getattr(entree, "is_junction", None)
        if entree.is_symlink() or (jonction is not None and jonction()):
            return "lien"
        return "dossier" if entree.is_dir(follow_symlinks=False) else "autre"
    except OSError as exc:
        erreurs.append((Path(entree.path), exc))
        return "erreur"


def parcourir_runs(
    racine: Path, refuses: List[Path], erreurs: List[Tuple[Path, OSError]]
) -> Iterator[Path]:
    """Énumère les exports candidats `runs/<auteur>/<copie>/*.jsonl` SANS JAMAIS
    SUIVRE DE LIEN — remplace `Path.glob("runs/*/*/*.jsonl")`, qui suivait un
    auteur, une copie ou un fichier LIEN (mesuré 2026-09-26, Python 3.14). MÊME
    ensemble que ce glob, liens exceptés : noms à point initial INCLUS (pathlib les
    prend), niveaux 1 et 2 limités aux dossiers RÉELS, niveau 3 aux noms `*.jsonl`
    (casse selon la plateforme, `normcase`) de tout type — le type (régulier, lien
    physique) est jugé à l'ouverture.

    Rend chaque candidat non-lien ; ajoute à `refuses` tout lien ou jonction
    rencontré à l'un des niveaux — `runs/` lui-même compris — SANS le suivre ni le
    résoudre ; ajoute à `erreurs` tout dossier dont l'énumération lève, au lieu de
    l'AVALER comme le glob. Aux appelants de trancher."""
    runs = racine / "runs"
    try:
        etat = os.lstat(runs)
    except FileNotFoundError:
        return
    except OSError as exc:
        erreurs.append((runs, exc))
        return
    if stat.S_ISLNK(etat.st_mode) or _est_jonction(runs):
        refuses.append(runs)
        return
    if not stat.S_ISDIR(etat.st_mode):
        return
    for auteur in _entrees(runs, erreurs):
        nature = _nature(auteur, erreurs)
        if nature == "lien":
            refuses.append(Path(auteur.path))
        if nature != "dossier":
            continue
        for copie in _entrees(Path(auteur.path), erreurs):
            nature = _nature(copie, erreurs)
            if nature == "lien":
                refuses.append(Path(copie.path))
            if nature != "dossier":
                continue
            for fichier in _entrees(Path(copie.path), erreurs):
                if not os.path.normcase(fichier.name).endswith(".jsonl"):
                    continue
                nature = _nature(fichier, erreurs)
                if nature == "lien":
                    refuses.append(Path(fichier.path))
                elif nature != "erreur":
                    yield Path(fichier.path)


def _identite_differente(avant: os.stat_result, apres: os.stat_result) -> bool:
    """Vrai si le `lstat` et le `fstat` ne désignent pas le MÊME fichier. Un
    `st_ino` nul (certaines graphies Windows) ne prouve rien : non comparé."""
    if not (avant.st_ino and apres.st_ino):
        return False
    return (avant.st_dev, avant.st_ino) != (apres.st_dev, apres.st_ino)


def _lire_descripteur(fd: int, taille: int) -> bytearray:
    """Lit AU PLUS `taille` octets DEPUIS `fd` (jamais rouvert par chemin), dans UN
    tampon préalloué — aucune copie intermédiaire. Un fichier raccourci depuis le
    `fstat` rend moins ; un fichier allongé n'est lu que jusqu'à `taille`."""
    tampon = bytearray(taille)
    lu = 0
    with memoryview(tampon) as vue:
        flux = io.FileIO(fd, "r", closefd=False)
        try:
            while lu < taille:
                with vue[lu:] as reste:
                    n = flux.readinto(reste)
                if not n:
                    break
                lu += n
        finally:
            flux.close()
    del tampon[lu:]
    return tampon


def lire_export_sans_lien(
    chemin: Path, taille_max: int
) -> Tuple[str, Optional[bytearray]]:
    """Lit UN export sans jamais suivre de lien ni dépasser `taille_max`. Rend
    `("ok", octets)`, `("trop_gros", None)` ou `("illisible", None)`.

    `os.lstat` (jamais `stat`) : pas un fichier RÉGULIER — lien, dossier, FIFO qui
    bloquerait, périphérique qui ne finirait pas — ou lien PHYSIQUE (`st_nlink >
    1`, S-00002550) ⇒ illisible, JAMAIS ouvert ; plus gros que la borne ⇒ trop
    gros, JAMAIS ouvert. Puis `os.open` avec `_DRAPEAUX_LECTURE_EXPORT`, `os.fstat`
    SUR LE DESCRIPTEUR — régulier, un seul lien, MÊME fichier que le `lstat`, sous la
    borne — et lecture DEPUIS CE descripteur : aucune course `stat` → `read_bytes`.
    `OSError` ⇒ illisible ; toute autre levée (dont `MemoryError`) remonte."""
    try:
        avant = os.lstat(chemin)
    except OSError:
        return "illisible", None
    if not stat.S_ISREG(avant.st_mode) or avant.st_nlink > 1:
        return "illisible", None
    if avant.st_size > taille_max:
        return "trop_gros", None
    try:
        fd = os.open(chemin, _DRAPEAUX_LECTURE_EXPORT)
    except OSError:  # dont ELOOP : devenu lien entre le `lstat` et l'ouverture
        return "illisible", None
    try:
        etat = os.fstat(fd)
        if (
            not stat.S_ISREG(etat.st_mode)
            or etat.st_nlink > 1
            or _identite_differente(avant, etat)
        ):
            return "illisible", None
        if etat.st_size > taille_max:
            return "trop_gros", None
        return "ok", _lire_descripteur(fd, etat.st_size)
    except OSError:
        return "illisible", None
    finally:
        os.close(fd)


def _refus_lien(chemin: Path, quoi: str) -> RunExportError:
    return RunExportError(
        f"export REFUSÉ : {chemin} est {quoi} sous runs/ — jamais suivi, ni en "
        "lecture ni en écriture (T-00000691). Remède : remplacer le lien par un "
        "VRAI dossier ou un VRAI fichier (un runs/ monté par lien n'est pas pris en "
        "charge), puis rejouer l'export (tasks.py replay-sync)."
    )


def _preparer_dossiers_export(chemin: Path) -> None:
    """Crée `runs/<auteur>/<copie>/` SANS JAMAIS TRAVERSER UN LIEN, et refuse
    (`RunExportError`, rien écrit) tout lien ou jonction à l'un des trois niveaux,
    tout composant qui n'est pas un dossier, et un fichier d'export présent qui est
    un lien, pas un fichier régulier, ou un lien PHYSIQUE.

    `os.mkdir` d'UN composant à la fois (jamais `mkdir(parents=True)`, qui suivait
    un `runs/<auteur>` lié et créait la copie DANS sa cible), puis `os.lstat` : un
    lien déjà là fait échouer `mkdir` (`FileExistsError`, sans le suivre) et le
    `lstat` le nomme. Appelée AVANT le verrou (pour créer) puis REJOUÉE SOUS le
    verrou d'export (S-00002561) : une bascule entre les deux est vue."""
    copie = chemin.parent
    auteur = copie.parent
    runs = auteur.parent
    runs.parent.mkdir(parents=True, exist_ok=True)  # la racine du projet : hors runs/
    for dossier in (runs, auteur, copie):
        try:
            os.mkdir(dossier)
        except FileExistsError:
            pass
        etat = os.lstat(dossier)
        if stat.S_ISLNK(etat.st_mode) or _est_jonction(dossier):
            raise _refus_lien(dossier, "un lien symbolique")
        if not stat.S_ISDIR(etat.st_mode):
            raise RunExportError(f"export REFUSÉ : {dossier} n'est pas un dossier.")
    try:
        etat = os.lstat(chemin)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(etat.st_mode) or _est_jonction(chemin):
        raise _refus_lien(chemin, "un lien symbolique")
    if not stat.S_ISREG(etat.st_mode):
        raise RunExportError(f"export REFUSÉ : {chemin} n'est pas un fichier régulier.")
    if etat.st_nlink > 1:
        raise _refus_lien(chemin, f"un lien physique ({etat.st_nlink} noms)")


def _ouvrir_export_sans_lien(chemin: Path, drapeaux: int) -> int:
    """`os.open(chemin, drapeaux | _DRAPEAUX_SANS_LIEN, 0o644)` puis `fstat` SUR LE
    DESCRIPTEUR : lien (dernier composant) ⇒ `RunExportError` ; pas un fichier
    régulier, ou lien PHYSIQUE ⇒ `RunExportError`, descripteur fermé. Rend le
    descripteur — TOUTE lecture et écriture de l'appelant passe par lui, jamais par
    une réouverture du chemin."""
    try:
        fd = os.open(chemin, drapeaux | _DRAPEAUX_SANS_LIEN, 0o644)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK) or os.path.islink(chemin):
            raise _refus_lien(chemin, "un lien symbolique") from exc
        raise
    try:
        etat = os.fstat(fd)
        if not stat.S_ISREG(etat.st_mode):
            raise RunExportError(f"export REFUSÉ : {chemin} n'est pas un fichier régulier.")
        if etat.st_nlink > 1:
            raise _refus_lien(chemin, f"un lien physique ({etat.st_nlink} noms)")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _ecrire_descripteur(fd: int, donnees: bytes) -> None:
    """Écrit TOUT `donnees` sur `fd` (boucle sur les écritures partielles)."""
    vue = memoryview(donnees)
    while vue:
        n = os.write(fd, vue)
        vue = vue[n:]


def _ulid_dans_descripteur(fd: int, ulid: str) -> bool:
    """Vrai si une ligne du fichier ouvert en `fd` porte `ulid` — lecture en
    STREAMING depuis le début, TOLÉRANTE (octet invalide remplacé, ligne non JSON ou
    non-objet sautée) : même tolérance que `_ulids_deja_dans_le_texte` (A1). Le
    descripteur reste ouvert."""
    os.lseek(fd, 0, os.SEEK_SET)
    with io.BufferedReader(io.FileIO(fd, "r", closefd=False)) as lecteur:
        for brute in lecteur:
            brute = brute.strip()
            if not brute:
                continue
            try:
                obj = json.loads(brute.decode("utf-8", errors="replace"))
            except (ValueError, RecursionError):
                continue
            if isinstance(obj, dict) and obj.get("ulid") == ulid:
                return True
    return False


# --- Écriture de l'export -----------------------------------------------------
def _ulid_deja_exporte(chemin: Path, ulid: str) -> bool:
    """Vrai si `ulid` figure déjà dans le fichier de mois — la déduplication
    côté EXPORT, l'unicité SQL ne couvrant pas un fichier texte. Absent ⇒ faux.
    T-00000691 : lu par `_ouvrir_export_sans_lien` — un lien (symbolique ou
    physique) ⇒ `RunExportError`, jamais suivi."""
    try:
        os.lstat(chemin)
    except FileNotFoundError:
        return False
    # A1 (binôme de clôture) : lecture TOLÉRANTE (errors="replace"), même chemin que
    # `_ulids_deja_dans_le_texte` et le banc de secrets qui lisent le MÊME magasin. Un
    # octet invalide (arrivé par une fusion) dans le fichier de MOIS déjà pourvu de sa
    # borne AVORTAIT `re_exporter_frappees` AVANT tout export en UTF-8 STRICT — la
    # tolérance était posée au seul site que le témoin regardait, pas sur le CHEMIN.
    fd = _ouvrir_export_sans_lien(chemin, os.O_RDONLY)
    try:
        return _ulid_dans_descripteur(fd, ulid)
    finally:
        os.close(fd)


def ajouter_a_l_export(
    ligne: Dict[str, Any],
    *,
    depuis: Any = None,
    copie: Optional[str] = None,
    _reserve: bool = False,
    auteur: Optional[str] = None,
) -> Path:
    """Ajoute `ligne` (déjà rédigée) à l'export du mois — `json.dumps(sort_keys=
    True, ensure_ascii=False)`, LF, AJOUT SEUL. Idempotent par ULID (côté
    export). C'est l'étape (3), APRÈS le `commit()` de l'appelant. `auteur=` est le
    raccourci interne de `chemin_export` (empreinte résolue une seule fois).

    T-00000691 (S-00002557, HAUTE classe 1) — AUCUN LIEN SUIVI EN ÉCRITURE :
    `_preparer_dossiers_export` crée et vérifie `runs/`, `<auteur>`, `<copie>`
    composant par composant (`lstat`), AVANT le verrou puis DE NOUVEAU sous lui ;
    le fichier s'ouvre UNE fois par `_ouvrir_export_sans_lien` (`O_NOFOLLOW`, `fstat` :
    régulier, un seul lien), et la garde LF, la relecture des ULID et l'ajout
    passent TOUS par ce descripteur. Un lien — symbolique ou physique — lève
    `RunExportError` sans rien écrire : les appelants l'annoncent et CONSERVENT le
    journal d'attente (`_flush_export`, `_rejouer_journaux_attente`)."""
    ulid = ligne.get("ulid")
    if not ulid:
        raise RunExportError("ligne d'export sans ULID : ajout refusé.")
    chemin = chemin_export(
        ulid, depuis=depuis, copie=copie, _reserve=_reserve, auteur=auteur
    )
    # C (T-00000696) : un banc n'écrit RIEN sous le runs/ réel — AVANT tout I/O,
    # donc avant même l'acquisition du verrou et le mkdir.
    _refuser_ecriture_de_banc_sous_racine_reelle(chemin)
    _preparer_dossiers_export(chemin)
    # A (T2, S-00001806) : le check-then-act (relecture + append) est SÉRIALISÉ,
    # sans quoi deux processus concurrents écrivent un doublon en AJOUT SEUL.
    with _verrou_export(depuis=depuis):
        _preparer_dossiers_export(chemin)  # REJOUÉ sous le verrou (S-00002561)
        fd = _ouvrir_export_sans_lien(chemin, os.O_RDWR | os.O_APPEND | os.O_CREAT)
        try:
            # F4 (binôme, promesse de la docstring de `re_exporter_frappees` /
            # L-00000111) : un enregistrement DÉCHIRÉ (arrêt entre deux octets, pas
            # de LF terminal) ferait FUSIONNER la ligne suivante — 0 ligne lisible sur
            # 2 et un DOUBLON irréparable au rejeu (mesuré). Réparation en AJOUT SEUL :
            # UN octet. SOUS le verrou (donc pas de course) et AVANT la relecture des
            # ULID, qui lit ce même fichier ligne à ligne.
            taille = os.fstat(fd).st_size
            if taille:
                os.lseek(fd, taille - 1, os.SEEK_SET)
                if os.read(fd, 1) != b"\n":
                    _ecrire_descripteur(fd, b"\n")  # `O_APPEND` : toujours en queue
                    # H1 (T-00000695/696) : poser le LF referme la ligne, mais NE
                    # répare PAS une TRONCATURE AU MILIEU d'un enregistrement. La
                    # ligne qu'on vient de clore peut être un JSON INCOMPLET, donc
                    # ILLISIBLE : ABSENTE du texte qui fait autorité, or
                    # `mesurer_runs` la COMPTE. On l'ANNONCE (jamais une perte
                    # silencieuse, L-00000136). La ligne reste (AJOUT SEUL) ; le rejeu
                    # par ULID ré-ajoute l'événement sur sa PROPRE ligne.
                    lignes_brutes = bytes(_lire_descripteur_depuis_zero(fd)).split(b"\n")
                    derniere = next(
                        (b for b in reversed(lignes_brutes) if b.strip()), b""
                    )
                    try:
                        json.loads(derniere.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        print(
                            f"run_export: enregistrement TRONQUÉ en queue de {chemin} "
                            "(LF rétabli) — ligne ILLISIBLE, ABSENTE du texte qui fait "
                            "autorité mais COMPTÉE par `mesure` (lignes_illisibles). "
                            "Rejeu par ULID requis.",
                            file=sys.stderr,
                        )
            if _ulid_dans_descripteur(fd, ulid):
                return chemin
            texte = json.dumps(ligne, sort_keys=True, ensure_ascii=False) + "\n"
            _ecrire_descripteur(fd, texte.encode("utf-8"))
        finally:
            os.close(fd)
    return chemin


def _lire_descripteur_depuis_zero(fd: int) -> bytearray:
    """Tout le fichier ouvert en `fd`, depuis l'octet 0 (taille lue par `fstat`)."""
    os.lseek(fd, 0, os.SEEK_SET)
    return _lire_descripteur(fd, os.fstat(fd).st_size)


def backfill(ligne: Dict[str, Any], *, depuis: Any = None) -> Path:
    """La SEULE porte par laquelle UNE ligne s'écrit sous `<copie> = "backfill"`.
    Point d'entrée keyword-only `_reserve=True` que le témoin 15 asserte comme
    seule voie d'acceptation de la valeur réservée. Le backfill de MASSE de
    l'historique (T-00000677) passe par `backfill_historique` ci-dessous, qui
    réutilise cette même valeur réservée et pose la borne EN TÊTE."""
    return ajouter_a_l_export(
        ligne, depuis=depuis, copie=RESERVE_BACKFILL, _reserve=True
    )


# --- Backfill de l'historique + CLI (tâche sœur T-00000677) -------------------
#: Borne écrite EN TÊTE de chaque `runs/<auteur>/backfill/<AAAA-MM>.jsonl`
#: (décision pilote S-00001594) : elle NOMME la décision et distingue une ligne
#: RECONSTRUITE d'une ligne OBSERVÉE dans un magasin en AJOUT SEUL (irréparable
#: par `git revert`). `reconstruire_depuis_exports` l'IGNORE (une clé, pas d'ulid).
BORNE_BACKFILL = (
    "backfill des lignes d'events_ledger anterieures a l'ecrivain unique "
    "(T-00000650) : <copie>=backfill, valeur RESERVEE, decision pilote "
    "S-00001594 ; ulid frappe a posteriori, monotone dans l'ordre des event_id."
)


def _ouvrir_base_sqlite(chemin: Path) -> sqlite3.Connection:
    """Ouvre une base V3 EXISTANTE (`--base`, copie 1a) SANS SUIVRE ni créer
    (T-00000770) : `refuser_les_liens` puis `ouvrir_sans_suivre(creer=False)`
    de `cadre.ledger.store`, sur une connexion NUE (`timeout` 30 s explicite,
    celui de `get_db_connection`), `Row` ensuite. Un lien, un second nom, un
    non-régulier ou un nom qui change entre le jugement et l'ouverture lèvent
    `ValueError` (la classe d'une copie chargée par chemin n'est jamais
    attrapée par son nom), traduite en `RunExportError` « refus d'ouverture : »
    — rc 6 au bord de `_cli`. Couture introuvable -> `PanneInfrastructure`
    (`_couture_ledger_store`). Un `--base` LIEN vers une base réelle, SUIVI et
    frappé avant T-00000770, est désormais refusé. Un store de schéma FUTUR
    (`user_version` > `SCHEMA_VERSION`) lève `SchemaVersionError`, connexion
    fermée, avant toute lecture de ligne de ce store (T-00001075) ; la lecture de
    version est le PREMIER énoncé qui lit le fichier : le non SQLite (26) et le
    verrou (5) y lèvent désormais, connexion fermée de même. Puis un store sans
    `ulid` (v0, v1) lève `RunExportError` qui nomme `create_tables()`, connexion
    fermée de même — rc 6 au bord de `_cli` (T-00001097)."""
    store_mod, workspace_mod = _couture_ledger_store()
    chemin = Path(chemin)
    try:
        atelier = workspace_mod.Workspace(chemin.parent)
        store_mod.refuser_les_liens(atelier, chemin.name)
        conn, _ident, _cree = store_mod.ouvrir_sans_suivre(
            atelier, chemin.name, creer=False,
            connecter=lambda uri: sqlite3.connect(uri, uri=True, timeout=30.0))
    except ValueError as exc:
        raise RunExportError(f"refus d'ouverture : {exc}") from exc
    try:
        _refuser_schema_futur(conn, chemin)
        from agentic_v3.db import run_export_ecriture  # paresseux, comme naissance_partition
        run_export_ecriture.refuser_sans_ulid(conn, chemin, RunExportError)  # T-00001097
    except BaseException:
        conn.close()
        raise
    conn.row_factory = sqlite3.Row
    return conn


def _refuser_schema_futur(conn: sqlite3.Connection, chemin: Path) -> None:
    """Refuse un store de schéma FUTUR (`user_version` > `SCHEMA_VERSION`) : lève
    `SchemaVersionError`, la MÊME classe que `create_tables`, que `classer_refus`
    classe en `CAUSE_VERSION`. Lue sur la connexion NUE, avant toute lecture de
    ligne et toute écriture ; comparaison STRICTE — un store ANTÉRIEUR passe, jamais
    monté (T-00001075). Corps dans `run_export_ecriture` (T-00001097)."""
    from agentic_v3.db import run_export_ecriture  # paresseux, comme naissance_partition

    run_export_ecriture.refuser_schema_futur(conn, chemin)


def _ms_de_created_at(created_at: Any, *, event_id: Any = None) -> int:
    """`created_at` (`AAAA-MM-JJ HH:MM:SS`, UTC — `CURRENT_TIMESTAMP` du schéma)
    en millisecondes depuis l'epoch. Sert à dériver l'horodatage EN TÊTE de l'ULID
    frappé : l'ordre ULID suit ainsi l'ordre chronologique, donc l'ordre des
    `event_id` (`created_at` est monotone dans cet ordre — vérifié sur la base).

    Garde (T12b, S-00001809) : `created_at` NULL ou hors forme lève un
    `RunExportError` qui NOMME `event_id` et la valeur fautive — jamais un
    `ValueError`/`TypeError` NU, illisible et sans coordonnée. Le message permet de
    retrouver la ligne à corriger en base."""
    if not isinstance(created_at, str):
        raise RunExportError(
            f"created_at absent ou non textuel (event_id={event_id!r}) : "
            f"{created_at!r} — horodatage indérivable, ligne à corriger en base."
        )
    try:
        dt = datetime.datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError as exc:
        raise RunExportError(
            f"created_at hors forme 'AAAA-MM-JJ HH:MM:SS' (event_id={event_id!r}) : "
            f"{created_at!r} — {exc}"
        ) from exc
    return int(dt.timestamp() * 1000)


def _ligne_export_historique(
    row: sqlite3.Row, ulid: str, predecesseur_ulid: Optional[str]
) -> Dict[str, Any]:
    """La ligne d'export d'une ligne historique — MÊMES clés que l'écrivain vivant
    (`_ecrire_evenement`), pour que `reconstruire_depuis_exports` la lise comme une
    ligne observée (fusion par ULID de l'étape 5 de T-00000650)."""
    return {
        "task_id": row["task_id"],
        "agent_role": row["agent_role"],
        "event_type": row["event_type"],
        "payload_json": row["payload_json"],
        "created_at": row["created_at"],
        "operation_id": row["operation_id"],
        "event_kind": row["event_kind"],
        "attempt": int(row["attempt"] or 0),
        "ulid": ulid,
        "predecesseur_ulid": predecesseur_ulid,
    }


#: Les 9 champs (hors `ulid`) qu'une ligne du TEXTE doit porter à l'IDENTIQUE de sa
#: ligne EN BASE. `re_exporter_frappees` compare ces champs pour un ULID présent des
#: DEUX côtés : un écart signale une ligne DIVERGENTE (A3) — comptée et nommée, jamais
#: réparée (le magasin est en ajout seul).
_CHAMPS_DIVERGENCE = (
    "task_id",
    "agent_role",
    "event_type",
    "payload_json",
    "created_at",
    "operation_id",
    "event_kind",
    "attempt",
    "predecesseur_ulid",
)


def _frapper_triplets(rows: List[sqlite3.Row]) -> List[Tuple[sqlite3.Row, str, Optional[str]]]:
    """Frappe un ULID par ligne (dérivé du `created_at`, ms STRICTEMENT croissant
    dans l'ordre des `event_id` — un compteur `dernier_ms + 1` départage les lignes
    d'une même seconde) et le `predecesseur_ulid` (dernier ULID de la MÊME `task_id`
    dans l'ordre des `event_id`). `nouvel_ulid` tirant 80 bits d'aléa, deux appels
    rendent des ULID DIFFÉRENTS : c'est pourquoi la passe 1b LIT les triplets déjà
    frappés en 1a au lieu de les re-tirer."""
    dernier_ms = -1
    dernier_par_tache: Dict[str, str] = {}
    triplets: List[Tuple[sqlite3.Row, str, Optional[str]]] = []
    for row in rows:
        base_ms = _ms_de_created_at(row["created_at"], event_id=row["event_id"])
        ms = base_ms if base_ms > dernier_ms else dernier_ms + 1
        dernier_ms = ms
        ulid = nouvel_ulid(ms)
        predecesseur = dernier_par_tache.get(row["task_id"])
        dernier_par_tache[row["task_id"]] = ulid
        triplets.append((row, ulid, predecesseur))
    return triplets


def _lire_triplets_source(source: Path) -> Dict[int, Tuple[str, Optional[str]]]:
    """1b : `(event_id -> (ulid, predecesseur_ulid))` des lignes DÉJÀ frappées
    d'une COPIE (passe 1a). N'INVENTE aucun ULID — il les RELIT. Lève
    `StoreV3Refuse` nommant la COPIE (`source`) quand `classer_refus` classe la
    levée de son ouverture ou de sa lecture (T-00001054) ; une copie de schéma
    FUTUR est refusée à l'ouverture (`CAUSE_VERSION`), avant toute lecture de ses
    lignes (T-00001075)."""
    from agentic_v3.db.refus_store import refus_nomme  # paresseux : forme chemin

    with refus_nomme(source):
        conn = _ouvrir_base_sqlite(source)
    try:
        with refus_nomme(source):
            return {
                int(r["event_id"]): (r["ulid"], r["predecesseur_ulid"])
                for r in conn.execute(
                    "SELECT event_id, ulid, predecesseur_ulid FROM events_ledger "
                    "WHERE ulid IS NOT NULL"
                )
            }
    finally:
        conn.close()


def _ecrire_borne_en_tete(chemin: Path, *, depuis: Any = None) -> None:
    """Écrit la ligne borne `{"borne": …}` EN TÊTE du fichier de mois, si elle n'y
    est pas déjà (IDEMPOTENT — un backfill rejoué ne la double pas). La borne est
    la PREMIÈRE ligne : un fichier neuf la reçoit AVANT toute ligne d'événement.

    ÉCART ADMIS À « AJOUT SEUL », NOMMÉ (T10, S-00001809 / S-00001808 MOYEN 6).
    Sur un fichier EXISTANT dont la première ligne non vide N'EST PAS une borne (un
    fichier écrit AVANT que la borne existe), la borne est posée EN TÊTE par
    RÉÉCRITURE ATOMIQUE — fichier temporaire dans le MÊME répertoire, puis
    `os.replace`. C'est le SEUL écart admis à l'AJOUT SEUL, et il est admis parce
    qu'il ne fait qu'AJOUTER une ligne EN TÊTE : AUCUNE ligne préexistante n'est
    retirée ni modifiée (les octets d'origine suivent la borne, inchangés — le banc
    le prouve octet pour octet). L'`open(chemin, "a")` d'origine APPENDAIT la borne
    EN QUEUE sur un tel fichier, ce que le commentaire promettait faux.

    NETTOYAGE DU TEMPORAIRE, BORNE DITE (m4, exec-critic sur da699e8). Ce `.tmp` de
    réécriture est le SEUL des trois sites atomiques du module à atterrir SOUS
    `runs/` (magasin VERSIONNÉ — les deux autres écrivent sous `state_project()`,
    hors dépôt). Un `try/finally` retire le temporaire quand l'`os.replace` n'a PAS
    eu lieu, pour qu'un échec de CE processus ne laisse pas un
    `<mois>.jsonl.borne.tmp` que `git add -- runs` capterait. BORNES : le `finally`
    protège l'échec de CE processus, PAS un arrêt brutal (`SIGKILL`, coupure) qui
    laisserait le résidu ; et il ne BALAYE PAS les résidus d'un run antérieur (ce
    serait une suppression à l'aveugle dans un magasin en AJOUT SEUL).

    T-00000691 (même classe que S-00002557, SECOND écrivain sous runs/) : aucun lien
    suivi ici non plus. `read_bytes` suivait un `<mois>.jsonl` lié et RECOPIAIT le
    contenu de la cible (`~/.ssh/id_rsa`) dans le fichier versionné ; le temporaire
    au nom PRÉVISIBLE (`<mois>.jsonl.borne.tmp`) était écrit À TRAVERS un lien posé
    d'avance. Désormais : `_preparer_dossiers_export` avant et sous le verrou,
    lecture et création par `_ouvrir_export_sans_lien`, temporaire UNIQUE créé en
    EXCLUSIF sans suivre de lien (`<mois>.jsonl.<pid>.<hex>.borne.tmp`)."""
    # C (T-00000696) : la borne est une écriture sous runs/ — même filet de banc.
    _refuser_ecriture_de_banc_sous_racine_reelle(chemin)
    _preparer_dossiers_export(chemin)
    # F5 (binôme) : ce read_bytes -> write_bytes -> os.replace est un SECOND écrivain
    # du MÊME fichier de mois. Hors verrou, il court contre l'append verrouillé de
    # `ajouter_a_l_export` : si A appende pendant que B est entre son read_bytes et son
    # os.replace, le replace réinstalle l'état LU AVANT l'append et la ligne de A est
    # PERDUE (pire qu'un doublon en ajout seul). On sérialise sous le MÊME verrou. Le
    # filet de banc et le `mkdir` RESTENT hors verrou (aucune écriture concurrente).
    # RÉENTRANCE (H2, T-00000695/696) : `_verrou_export` est désormais RÉENTRANT dans
    # le processus (`threading.local` des chemins tenus). Imbriquer `_ecrire_borne_en_
    # tete` sous le verrou de `ajouter_a_l_export` ne s'auto-bloque donc PLUS (avant,
    # `flock` non réentrant gelait `_VERROU_TIMEOUT_S` — 30 s en prod — puis levait, et
    # cette levée était avalée en amont, T-00000313). Les deux appelants
    # (`backfill_historique`, `re_exporter_frappees`) l'appellent AVANT
    # `ajouter_a_l_export` ; la réentrance couvre l'imbrication éventuelle SANS toucher
    # la sérialisation INTER-processus.
    with _verrou_export(depuis=depuis):
        _preparer_dossiers_export(chemin)  # REJOUÉ sous le verrou
        ligne_borne = (
            json.dumps({"borne": BORNE_BACKFILL}, sort_keys=True, ensure_ascii=False) + "\n"
        )
        try:
            os.lstat(chemin)
        except FileNotFoundError:
            fd = _ouvrir_export_sans_lien(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                _ecrire_descripteur(fd, ligne_borne.encode("utf-8"))
            finally:
                os.close(fd)
            return
        # A1 (binôme de clôture) : lecture EN BINAIRE. Le site précédent lisait ce
        # fichier de MOIS en UTF-8 STRICT (`read_text`) : un octet invalide (fusion) y
        # levait une `UnicodeDecodeError` non attrapée, avortant `re_exporter_frappees`
        # AVANT tout export — le défaut M2 que le correctif précédent prétendait fermé,
        # déplacé du site que le témoin regardait vers le CHEMIN. Le binaire TOLÈRE
        # l'octet (décodage `errors="replace"` pour la seule INSPECTION de la 1re ligne)
        # ET préserve les octets préexistants OCTET POUR OCTET sous la borne.
        fd = _ouvrir_export_sans_lien(chemin, os.O_RDONLY)
        try:
            donnees = bytes(_lire_descripteur_depuis_zero(fd))
        finally:
            os.close(fd)
        for premiere in donnees.split(b"\n"):
            premiere = premiere.strip()
            if not premiere:
                continue
            try:
                obj = json.loads(premiere.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                break  # première ligne illisible -> on prépose la borne
            if isinstance(obj, dict) and "borne" in obj:
                return  # borne déjà en tête — idempotent, aucun octet touché
            break  # première ligne non vide n'est pas une borne -> préposer EN TÊTE
        # Réécriture atomique : borne EN TÊTE, octets préexistants INCHANGÉS en dessous.
        # Temporaire UNIQUE, créé en EXCLUSIF sans suivre de lien : un nom prévisible
        # déjà posé (lien compris) fait échouer la création au lieu d'être écrit.
        tmp = chemin.with_name(
            f"{chemin.name}.{os.getpid()}.{secrets.token_hex(4)}.borne.tmp"
        )
        cree = remplace = False
        try:
            fd_tmp = os.open(
                tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _DRAPEAUX_SANS_LIEN, 0o644
            )
            cree = True
            try:
                _ecrire_descripteur(fd_tmp, ligne_borne.encode("utf-8") + donnees)
            finally:
                os.close(fd_tmp)
            os.replace(tmp, chemin)
            remplace = True
        finally:
            # m4 : le `.tmp` sous runs/ (versionné) ne doit pas survivre à un échec de
            # CE processus — `git add -- runs` le capterait. `unlink` Python, jamais `rm`.
            # Seulement le temporaire CRÉÉ ici : jamais un nom que la création
            # exclusive a trouvé déjà pris.
            if cree and not remplace:
                tmp.unlink(missing_ok=True)


def backfill_historique(
    *,
    base: Optional[Any] = None,
    appliquer_depuis: Optional[Any] = None,
    depuis: Any = None,
    auteur: Optional[str] = None,
) -> Dict[str, Any]:
    """FRAPPE un `ulid`/`predecesseur_ulid` par ligne historique (`ulid IS NULL`)
    de `base`, l'ÉCRIT en base (`UPDATE`), puis exporte la ligne sous
    `runs/<auteur>/backfill/<AAAA-MM>.jsonl` (borne EN TÊTE, S-00001594). La ligne
    EN BASE et la ligne du TEXTE portent le MÊME ULID.

    `base` défaut = `DEFAULT_DB_PATH()` (la base VIVANTE — JAMAIS le fichier figé
    `.agents/state/v3_event_store.db`). Deux passes (T-00000677) :
      * `base=<copie>` (1a) : frappe et exporte sur une COPIE ; l'appelant ne
        commite RIEN.
      * `appliquer_depuis=<copie 1a>` (1b) : n'INVENTE aucun ULID — il APPLIQUE à
        `base` (vivante) les triplets `(event_id, ulid, predecesseur_ulid)` frappés
        en 1a, par `UPDATE ... WHERE event_id=? AND ulid IS NULL`. Les exports
        produits sont IDENTIQUES à ceux de 1a (mêmes ULID, mêmes champs) : la
        relecture idempotente par ULID de `ajouter_a_l_export` les laisse
        byte-pour-byte inchangés (garantie `sha256sum` avant/après du plan).

    BORNE ANTI-CRASH, DITE PLUTÔT QUE CACHÉE (T1, S-00001809). L'`UPDATE` des ULID
    est COMMITÉ AVANT la boucle d'export, et ce chemin N'UTILISE PAS le journal
    d'attente. Une interruption ENTRE le commit et la fin de la boucle laisse donc
    des lignes FRAPPÉES en base (`ulid IS NOT NULL`) mais ABSENTES du texte, et un
    rejeu de CE backfill — qui ne regarde que `ulid IS NULL` — rend `frappees: 0`
    et n'exporte RIEN de plus : AUCUN signal. Le chemin de réparation EST
    `re_exporter_frappees` (CLI `backfill --re-exporter`), qui SELECT les lignes
    déjà frappées absentes du texte et les exporte.

    REFUS NOMMÉ (T-00001054, S-00003324) : lève `StoreV3Refuse` à l'ouverture et
    à la première lecture — de `base` comme de la copie `appliquer_depuis`, dont
    il nomme le chemin — puis pendant la phase d'écriture de `base`, du BEGIN
    IMMEDIATE au commit inclus (T-00001074 : le verrou y mord, base inchangée, la
    transaction défaite à la fermeture), quand `refus_store.classer_refus` classe
    la levée (store non SQLite, droits, verrou à la lecture ou à l'écriture,
    racine non résolue…) ; toute autre levée remonte telle quelle. L'ouverture
    LIT la version (T-00001075) : un store de schéma FUTUR (`user_version` >
    `SCHEMA_VERSION`), base comme copie 1a, est refusé (`CAUSE_VERSION`) avant
    toute lecture de ligne de ce store et toute écriture ; celle de `base` est
    RELUE sous le verrou, avant le premier UPDATE (R3-bis, T-00001082). Une
    `PanneInfrastructure` levée dans ces blocs sort ENVELOPPÉE (verdict EN PANNE,
    origine en `__cause__`) quand ce module est chargé comme paquet. HORS des blocs,
    à dessein : `auteur_courant` (R4), le refus de FORME d'auteur (`_valider_copie`,
    T-00000697 : `RunExportError` avant l'ouverture du store), et tout ce qui SUIT
    le commit — le décompte `ulid IS NULL` et la boucle d'export (R9), base déjà
    écrite, jamais un refus — des bornes, pas des promesses.
    """
    from agentic_v3.db import run_export_ecriture  # paresseux, comme naissance_partition
    from agentic_v3.db.refus_store import refus_nomme  # paresseux : forme chemin
    from agentic_v3.db.schema import DEFAULT_DB_PATH  # import paresseux (cycle)

    # (a) la résolution de la base (`--base-vivante` hors projet : `CadrePathError`).
    with refus_nomme(base):
        base_chemin = (
            Path(base) if base is not None else DEFAULT_DB_PATH(project_root(depuis))
        )
    # Garde T12a (S-00001809) : refuser AVANT de connecter — `sqlite3.connect`
    # CRÉERAIT une base vide de 0 octet, silencieusement adoptée comme « base sans
    # historique ». Le message NOMME le chemin pour le retrouver.
    if not base_chemin.exists():
        raise RunExportError(
            f"base introuvable : {base_chemin} — refus de connecter "
            "(sqlite3.connect créerait une base vide de 0 octet, T12a)."
        )
    if appliquer_depuis is not None and not Path(appliquer_depuis).exists():
        raise RunExportError(
            f"copie 1a introuvable : {Path(appliquer_depuis)} — refus de connecter "
            "(sqlite3.connect créerait une base vide de 0 octet, T12a)."
        )
    auteur_effectif = auteur if auteur is not None else auteur_courant(depuis)
    _valider_copie(auteur_effectif, "auteur")  # T-00000697 : AVANT l'UPDATE commité (T1)

    # (b) l'ouverture et la lecture de version — le non SQLite y lève désormais
    # (épinglé, re_11), le verrou aussi (mesuré à la main, `probe_premier.py` de
    # l'annexe de T-00001075, sans témoin automatique) ; (c) la première lecture
    # de lignes ; (d), plus bas, la phase d'écriture (T-00001074).
    with refus_nomme(base_chemin):
        conn = _ouvrir_base_sqlite(base_chemin)
    try:
        with refus_nomme(base_chemin):
            rows = conn.execute(
                "SELECT event_id, task_id, agent_role, event_type, payload_json, "
                "created_at, operation_id, event_kind, attempt "
                "FROM events_ledger WHERE ulid IS NULL ORDER BY event_id"
            ).fetchall()
        nul_avant = len(rows)
        if appliquer_depuis is not None:
            source = _lire_triplets_source(Path(appliquer_depuis))
            triplets: List[Tuple[sqlite3.Row, str, Optional[str]]] = []
            for row in rows:
                eid = int(row["event_id"])
                if eid not in source:
                    raise RunExportError(
                        f"1b : event_id {eid} (ulid IS NULL en base vivante) absent "
                        "de la copie 1a — la copie ne correspond pas à la base "
                        "(aucun ULID à appliquer, refus plutôt que d'inventer)."
                    )
                ulid, predecesseur = source[eid]
                triplets.append((row, ulid, predecesseur))
        else:
            triplets = _frapper_triplets(rows)

        # UPDATE : la ligne en base porte le MÊME ULID que celle du texte ; `AND ulid IS
        # NULL` : jamais re-frappée. (d) la phase d'écriture, du BEGIN IMMEDIATE au
        # commit INCLUS (T-00001074) : version RELUE sous le verrou (R3-bis, T-00001082),
        # qui mord au BEGIN sous un écrivain tenu, au commit sous un lecteur tenu (DELETE).
        # Le BEGIN tient sur UNE ligne, seul : re_12 (test_ouvreurs_refus_store) en lit le TEXTE.
        with refus_nomme(base_chemin):
            conn.execute("BEGIN IMMEDIATE")
            run_export_ecriture.relire_version_sous_verrou(conn, base_chemin)
            for row, ulid, predecesseur in triplets:
                conn.execute(
                    "UPDATE events_ledger SET ulid=?, predecesseur_ulid=? "
                    "WHERE event_id=? AND ulid IS NULL",
                    (ulid, predecesseur, int(row["event_id"])),
                )
            conn.commit()
        nul_apres = int(
            conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL"
            ).fetchone()[0]
        )
    finally:
        conn.close()

    # Export : borne EN TÊTE de CHAQUE mois, puis une ligne par événement (ordre
    # ULID). Grouper par mois pour poser la borne AVANT la première ligne du mois.
    lignes = [
        _ligne_export_historique(row, ulid, pred) for row, ulid, pred in triplets
    ]
    lignes.sort(key=lambda ligne: ligne["ulid"])
    mois_amorces: set = set()
    fichiers: Dict[str, str] = {}
    for ligne in lignes:
        mois = _mois_de_ulid(ligne["ulid"])
        chemin = chemin_export(
            ligne["ulid"],
            depuis=depuis,
            copie=RESERVE_BACKFILL,
            _reserve=True,
            auteur=auteur_effectif,
        )
        if mois not in mois_amorces:
            _ecrire_borne_en_tete(chemin, depuis=depuis)
            mois_amorces.add(mois)
        ajouter_a_l_export(
            ligne,
            depuis=depuis,
            copie=RESERVE_BACKFILL,
            _reserve=True,
            auteur=auteur_effectif,
        )
        fichiers[mois] = str(chemin)
    return {
        "mode": "appliquer" if appliquer_depuis is not None else "frapper",
        "base": str(base_chemin),
        "auteur": auteur_effectif,
        "nul_avant": nul_avant,
        "nul_apres": nul_apres,
        "frappees": len(triplets),
        "mois": sorted(mois_amorces),
        "fichiers": fichiers,
    }


def _lignes_du_texte_sous(racine: Path, motif: str) -> Dict[str, Dict[str, Any]]:
    """`ulid -> ligne lue` pour tous les `.jsonl` que `motif` sélectionne sous
    `racine`. Lecture TOLÉRANTE (`errors="replace"`) : un octet invalide (fusion) ne
    doit pas avorter la lecture. La ligne borne (une clé `borne`, pas d'`ulid`) est
    ignorée ; une ligne illisible est sautée. Rend la LIGNE ENTIÈRE (les 9 champs +
    l'ulid) pour que l'appelant compare le CONTENU, pas seulement la PRÉSENCE.

    T-00000691 : aucun CONTENU lu à travers un lien. Un chemin dont un composant
    sous `racine` (ou `racine` elle-même) est un lien est SAUTÉ et nommé sur
    stderr ; le fichier s'ouvre par `_ouvrir_export_sans_lien` (lien physique,
    non-régulier ⇒ sauté et nommé). BORNE : le `glob` énumère encore le CONTENU
    d'un dossier lié (des noms, jamais des octets)."""
    presents: Dict[str, Dict[str, Any]] = {}
    if not racine.is_dir():
        return presents
    for chemin in sorted(racine.glob(motif)):
        composants = [chemin, *chemin.relative_to(racine).parents]
        if os.path.islink(racine) or any(
            os.path.islink(racine / c) for c in composants[1:] if str(c) != "."
        ) or os.path.islink(chemin):
            print(f"run_export: {chemin} SAUTÉ (lien sous runs/, jamais suivi)", file=sys.stderr)
            continue
        try:
            fd = _ouvrir_export_sans_lien(chemin, os.O_RDONLY)
        except (RunExportError, OSError) as exc:
            print(f"run_export: {chemin} SAUTÉ ({exc})", file=sys.stderr)
            continue
        with io.TextIOWrapper(
            io.BufferedReader(io.FileIO(fd, "r", closefd=True)),
            encoding="utf-8", errors="replace",
        ) as fichier:
            for brute in fichier:
                brute = brute.strip()
                if not brute:
                    continue
                try:
                    obj = json.loads(brute)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("ulid"):
                    presents[obj["ulid"]] = obj
    return presents


def _ulids_deja_dans_le_texte(depuis: Any = None) -> Dict[str, Dict[str, Any]]:
    """`ulid -> ligne lue` des ULID DÉJÀ présents dans le texte d'export, TOUS AUTEURS,
    TOUTES copies et TOUS mois confondus (`runs/*/*/*.jsonl`) — surtout PAS le seul
    auteur COURANT (A2, binôme de clôture). Le magasin VOYAGE par git ENTRE
    contributeurs et `events_ledger` n'a AUCUNE colonne d'auteur (`schema.py`) : une
    ligne exportée sous un AUTRE auteur est DÉJÀ dans le texte partagé, la ré-exporter
    sous l'auteur courant forgerait un DOUBLON dans un magasin en AJOUT SEUL, donc
    irréparable. Borner le scan à un seul auteur — comme le faisait le correctif
    précédent — tenait l'invariant « jamais un doublon en ajout seul » PAR AUTEUR, non
    à l'échelle du magasin (mesuré : 2269 doublons sous un second auteur si
    `user.email` change entre le backfill et la réparation).

    Rend la LIGNE ENTIÈRE (ULID -> ligne) et non un `set`, pour que l'appelant compare
    le CONTENU des 9 champs (A3) : une ligne présente mais DIVERGENTE n'est PAS
    réparée — le magasin est en ajout seul — elle est COMPTÉE et NOMMÉE.

    TOLÉRANCE D'ENCODAGE (m5, exec-critic sur da699e8) : lecture en `errors="replace"`,
    comme le banc de secrets qui lit le MÊME magasin — sans quoi une `UnicodeDecodeError`
    (octet invalide arrivé par une fusion `merge=union`) avorterait la réparation AVANT
    tout export. CONSÉQUENCE DITE : une ligne dont l'ULID serait ABÎMÉ par le
    remplacement ne sera pas reconnue comme déjà exportée, donc RÉ-EXPORTÉE — une ligne
    en trop et VISIBLE, plutôt qu'une réparation impossible."""
    racine = Path(project_root(depuis)) / "runs"
    return _lignes_du_texte_sous(racine, "*/*/*.jsonl")


def re_exporter_frappees(
    *,
    base: Optional[Any] = None,
    depuis: Any = None,
    auteur: Optional[str] = None,
) -> Dict[str, Any]:
    """Passe de RÉ-EXPORT (T1, S-00001809) — le chemin de réparation de la PERTE DE
    DONNÉES de `backfill_historique` (UPDATE des ULID commité AVANT la boucle
    d'export, sans journal d'attente : une interruption laisse des lignes frappées
    HORS du texte, qu'un rejeu nominal ne retrouve jamais).

    Elle calcule d'abord les lignes DÉJÀ présentes dans le texte en balayant TOUS les
    AUTEURS, TOUTES les copies et TOUS les mois (`_ulids_deja_dans_le_texte`, A2),
    SELECT en base les lignes `WHERE ulid IS NOT NULL` dont l'ulid est ABSENT de cet
    ensemble, et les exporte sous `copie=backfill`, borne EN TÊTE, par le MÊME
    `_ligne_export_historique` que le backfill. Mêmes paramètres `base=`/`depuis=`/
    `auteur=` que `backfill_historique`.

    LA JOINTURE PORTE SUR LA PRÉSENCE DE L'ULID (A3, binôme de clôture) ; une ligne
    présente mais DIVERGENTE (même ULID, un des 9 champs différent) n'est PAS réparée
    — le magasin est en AJOUT SEUL — elle est COMPTÉE (`divergentes`) et NOMMÉE
    (`divergentes_ulid`), jamais passée sous silence.

    DÉDUPLICATION À L'ÉCHELLE DU MAGASIN (A2). La réparation ne restaure PLUS une ligne
    dont la seule copie appartient à un AUTRE auteur — et c'est CORRECT, cette copie
    EST là, le texte voyage par git. Ces lignes sont comptées `sous_autre_auteur`. Une
    réparation ne crée JAMAIS un auteur : si des lignes frappées existent en base mais
    qu'AUCUN export n'existe sous l'auteur courant, la fonction REFUSE (`RunExportError`
    nommant un `user.email` probablement changé) plutôt que de forger un dossier
    d'auteur neuf.

    IDEMPOTENTE APRÈS UN LF FINAL MANQUANT, PAS APRÈS UNE TRONCATURE AU MILIEU (A5,
    binôme de clôture ; garde de LF F4 + annonce H1, CE lot T-00000695/696). Un dernier
    enregistrement SANS LF FINAL ferait FUSIONNER l'ajout suivant ; `ajouter_a_l_export`
    RÉPARE ce LF (un octet, en ajout seul, SOUS le verrou) AVANT d'ajouter, l'ajout tombe
    sur sa PROPRE ligne, et une seconde passe rend `re_exportees` = 0. MAIS si le dernier
    enregistrement est TRONQUÉ AU MILIEU (arrêt entre deux octets), poser le LF le referme
    en une ligne ILLISIBLE : ses octets ne sont PAS récupérés, la ligne DEMEURE (magasin
    en AJOUT SEUL) et `mesurer_runs` la compte à part (`lignes_illisibles`). L'idempotence
    du RE-EXPORT tient tout de même — l'ULID illisible n'est pas reconnu comme présent,
    donc ré-émis UNE fois sur une ligne VALIDE, puis retrouvé aux passes suivantes — mais
    la ligne déchirée n'est pas « réparée » : elle est ANNONCÉE (H1) au moment où le LF est
    posé, jamais avalée en silence.

    REFUS NOMMÉ (T-00001054, S-00003324) : lève `StoreV3Refuse` à l'ouverture et
    à la première lecture de `base` quand `refus_store.classer_refus` classe la
    levée — même patron, mêmes bornes que `backfill_historique` ; un store de
    schéma FUTUR y est refusé à l'ouverture (`CAUSE_VERSION`, T-00001075), avant
    toute lecture de ligne de ce store et tout export ; HORS des blocs :
    `auteur_courant`, le refus de FORME d'auteur (`_valider_copie`, T-00000697),
    `_ulids_deja_dans_le_texte`, le refus d'auteur SANS export (`RunExportError`,
    rc 6), les exports. Elle n'écrit RIEN en base : ni écriture, ni bloc (d).
    """
    from agentic_v3.db.refus_store import refus_nomme  # paresseux : forme chemin
    from agentic_v3.db.schema import DEFAULT_DB_PATH  # import paresseux (cycle)

    # (a) la résolution de la base (`--base-vivante` hors projet : `CadrePathError`).
    with refus_nomme(base):
        base_chemin = (
            Path(base) if base is not None else DEFAULT_DB_PATH(project_root(depuis))
        )
    if not base_chemin.exists():
        raise RunExportError(
            f"base introuvable : {base_chemin} — refus de connecter "
            "(sqlite3.connect créerait une base vide de 0 octet, T12a)."
        )
    auteur_effectif = auteur if auteur is not None else auteur_courant(depuis)
    _valider_copie(auteur_effectif, "auteur")  # T-00000697 : AVANT de lire runs/<auteur>/
    racine_runs = Path(project_root(depuis)) / "runs"
    lignes_du_texte = _ulids_deja_dans_le_texte(depuis=depuis)  # TOUS auteurs (A2)
    deja = set(lignes_du_texte)
    lignes_courant = _lignes_du_texte_sous(racine_runs / auteur_effectif, "*/*.jsonl")

    # (b) l'ouverture et la lecture de version (non SQLite et verrou y lèvent
    # désormais, voir `backfill_historique`), (c) la première lecture de lignes.
    with refus_nomme(base_chemin):
        conn = _ouvrir_base_sqlite(base_chemin)
    try:
        with refus_nomme(base_chemin):
            rows = conn.execute(
                "SELECT event_id, task_id, agent_role, event_type, payload_json, "
                "created_at, operation_id, event_kind, attempt, ulid, predecesseur_ulid "
                "FROM events_ledger WHERE ulid IS NOT NULL ORDER BY event_id"
            ).fetchall()
    finally:
        conn.close()
    candidates = len(rows)

    # A2 : une réparation ne crée JAMAIS un auteur. Des lignes frappées en base mais
    # AUCUN export sous l'auteur courant => `user.email` a probablement changé entre le
    # backfill et cette réparation ; ré-exporter forgerait un dossier d'auteur neuf
    # (doublon irréparable en AJOUT SEUL). On REFUSE plutôt que de forger.
    racine_auteur = racine_runs / auteur_effectif
    auteur_a_exporte = racine_auteur.is_dir() and any(racine_auteur.glob("*/*.jsonl"))
    if candidates and not auteur_a_exporte:
        raise RunExportError(
            f"re-export refusé : {candidates} ligne(s) frappée(s) en base mais AUCUN "
            f"export sous l'auteur courant ({auteur_effectif}). Une réparation ne crée "
            "jamais un auteur — `git config user.email` a-t-il changé entre le backfill "
            "et cette réparation ? (le magasin voyage par git, sans colonne d'auteur ; "
            "ré-exporter ici FORGERAIT un doublon sous un nouvel auteur)."
        )

    # A3 : la jointure porte sur la PRÉSENCE de l'ulid ; une ligne PRÉSENTE mais dont
    # un des 9 champs DIVERGE de la base est COMPTÉE et NOMMÉE, jamais réparée (ajout
    # seul) ni passée sous silence.
    divergentes: List[str] = []
    for row in rows:
        ligne_texte = lignes_du_texte.get(row["ulid"])
        if ligne_texte is None:
            continue
        ligne_base = _ligne_export_historique(row, row["ulid"], row["predecesseur_ulid"])
        if any(ligne_texte.get(c) != ligne_base.get(c) for c in _CHAMPS_DIVERGENCE):
            divergentes.append(row["ulid"])

    # A2 : lignes présentes SOUS UN AUTRE AUTEUR (jamais sous le courant) — non
    # réparées, comptées. Leur copie EST là et voyage par git.
    sous_autre_auteur = sum(
        1 for row in rows if row["ulid"] in deja and row["ulid"] not in lignes_courant
    )

    manquantes_rows = [row for row in rows if row["ulid"] not in deja]

    lignes = [
        _ligne_export_historique(row, row["ulid"], row["predecesseur_ulid"])
        for row in manquantes_rows
    ]
    lignes.sort(key=lambda ligne: ligne["ulid"])
    mois_amorces: set = set()
    fichiers: Dict[str, str] = {}
    re_exportees = 0
    for ligne in lignes:
        mois = _mois_de_ulid(ligne["ulid"])
        chemin = chemin_export(
            ligne["ulid"],
            depuis=depuis,
            copie=RESERVE_BACKFILL,
            _reserve=True,
            auteur=auteur_effectif,
        )
        if mois not in mois_amorces:
            _ecrire_borne_en_tete(chemin, depuis=depuis)
            mois_amorces.add(mois)
        deja_dans_ce_fichier = _ulid_deja_exporte(chemin, ligne["ulid"])
        ajouter_a_l_export(
            ligne,
            depuis=depuis,
            copie=RESERVE_BACKFILL,
            _reserve=True,
            auteur=auteur_effectif,
        )
        if not deja_dans_ce_fichier:
            re_exportees += 1
        fichiers[mois] = str(chemin)
    return {
        "mode": "re-exporter",
        "base": str(base_chemin),
        "auteur": auteur_effectif,
        "candidates": candidates,
        "manquantes": len(manquantes_rows),
        "re_exportees": re_exportees,
        "divergentes": len(divergentes),
        "divergentes_ulid": divergentes[:20],
        "sous_autre_auteur": sous_autre_auteur,
        "mois": sorted(mois_amorces),
        "fichiers": fichiers,
    }


def mesurer_runs(depuis: Any = None) -> Dict[str, Any]:
    """Octets par `(auteur, mois)` et total sous `runs/` — la borne du ticket
    (étape 6). Un seul auteur réel aujourd'hui : c'est une borne BASSE, jamais une
    projection.

    T-00000691 (S-00002561) : AUCUN LIEN SUIVI — parcours par `parcourir_runs`,
    ouverture par `_ouvrir_export_sans_lien`. Un lien (symbolique ou physique), un
    non-régulier ou un dossier illisible n'est ni compté ni lu : il est NOMMÉ sous
    `chemins_refuses` (relatif à la racine), jamais tu — une mesure qui sauterait en
    silence se lirait comme complète."""
    racine_projet = Path(project_root(depuis))
    par_auteur_mois: Dict[str, int] = {}
    lignes_par_auteur_mois: Dict[str, int] = {}
    illisibles_par_auteur_mois: Dict[str, int] = {}
    total = 0
    lignes_total = 0
    illisibles_total = 0
    refuses: List[Path] = []
    erreurs: List[Tuple[Path, OSError]] = []
    for chemin in sorted(parcourir_runs(racine_projet, refuses, erreurs)):
        try:
            fd = _ouvrir_export_sans_lien(chemin, os.O_RDONLY)
        except (RunExportError, OSError):
            refuses.append(chemin)
            continue
        auteur = chemin.parent.parent.name
        mois = chemin.stem
        cle = f"{auteur}/{mois}"
        try:
            octets = os.fstat(fd).st_size
            total += octets
            par_auteur_mois[cle] = par_auteur_mois.get(cle, 0) + octets
            # A1 : lecture TOLÉRANTE — la mesure ne doit pas AVORTER sur un octet
            # invalide (le comptage de lignes n'exige pas un décodage strict).
            # H1 (T-00000695/696) : on COMPTE À PART les lignes ILLISIBLES (JSON
            # incomplet d'une troncature au milieu d'un enregistrement) — sans quoi
            # `mesure` compterait une PERTE DE DONNÉES comme une ligne présente.
            with io.BufferedReader(io.FileIO(fd, "r", closefd=False)) as fichier:
                for brute in fichier:
                    if not brute.strip():
                        continue
                    lignes_par_auteur_mois[cle] = lignes_par_auteur_mois.get(cle, 0) + 1
                    lignes_total += 1
                    try:
                        json.loads(brute.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        illisibles_par_auteur_mois[cle] = (
                            illisibles_par_auteur_mois.get(cle, 0) + 1
                        )
                        illisibles_total += 1
        finally:
            os.close(fd)

    def _relatif(chemin: Path) -> str:
        try:
            return chemin.relative_to(racine_projet).as_posix()
        except ValueError:
            return str(chemin)

    return {
        "octets_total": total,
        "octets_par_auteur_mois": par_auteur_mois,
        "lignes_par_auteur_mois": lignes_par_auteur_mois,
        "lignes_total": lignes_total,
        "lignes_illisibles": illisibles_total,
        "lignes_illisibles_par_auteur_mois": illisibles_par_auteur_mois,
        "chemins_refuses": sorted(
            _relatif(p) for p in refuses + [dossier for dossier, _exc in erreurs]
        ),
    }


def _cli(argv: Optional[List[str]] = None) -> int:
    """CLI PUBLIQUE NEUVE de ce module (T-00000677) — `backfill` et `mesure`. C'est
    ce lot qui ajoute une CLI à `run_export.py` (T-00000650 le laissait bibliothèque
    sans surface CLI ; sa ligne « aucune surface CLI publique neuve » ne vaut que
    pour LUI).

    CONTRAT DE REFUS À CODES DE SORTIE DISTINCTS (grave 2 S-00001808, T12 S-00001809 ;
    M1/M2 exec-critic sur da699e8 ; A4 binôme de clôture) — le DÉFAUT de `backfill` NE
    frappe PLUS la base VIVANTE en silence. Les REFUS sont ÉNUMÉRÉS 2–6 ; toute autre
    sortie est VOLONTAIREMENT HORS de cette énumération, et c'est une BORNE, pas une
    liste close (règle d'or AGENTS.md : « WHERE YOU CANNOT ENUMERATE, BOUND ») :
      * 0 succès ; stdout est du JSON PUR.
      * 2 erreur d'usage argparse (défaut d'argparse — inchangé).
      * 3 REFUS : `backfill`/`--re-exporter` sans base désignée — il faut `--base
        <chemin>` OU le drapeau explicite `--base-vivante`. Le message NOMME le remède.
      * 4 REFUS (`RC_STORE_REFUSE`) : base désignée INUTILISABLE —
          - PAS UN FICHIER (contrôle CLI, avant toute ouverture) : le chemin de
            `--base` ou `--appliquer-depuis` est absent, OU un RÉPERTOIRE (A4 :
            `.is_file()` et non `.exists()`, sans quoi un répertoire passait puis
            `sqlite3.connect` levait rc 1 hors énumération) ;
          - OU store REFUSÉ à l'OUVERTURE, à la PREMIÈRE LECTURE (T-00001054,
            S-00003324) ou pendant la PHASE D'ÉCRITURE de la base, du BEGIN
            IMMEDIATE au commit inclus (T-00001074, T-00001082 : la version y est
            relue, le verrou y mord au BEGIN sous un écrivain tenu, au commit sous
            un lecteur tenu en journal DELETE ; la base reste INCHANGÉE, et rien
            après le commit n'est un refus) : la bibliothèque lève `StoreV3Refuse`
            (classé par `refus_store.classer_refus` : non SQLite, corrompu (code
            11, T-00001078), droits, lecture seule (code 8, à l'ouverture comme à
            l'UPDATE), verrou à la lecture ou à l'écriture, racine non résolue
            sous `--base-vivante`…),
            écrit sur UNE ligne STDERR, sans traceback : `run_export.py backfill:
            store V3 REFUSÉ (<cause>) — <base RÉELLEMENT refusée, la copie 1a sous
            --appliquer-depuis> — <Type>: <message>`. Un store de schéma FUTUR
            (`PRAGMA user_version` > `SCHEMA_VERSION`), base ou copie 1a, y est
            REFUSÉ à l'ouverture, avant toute lecture de ligne de ce store et
            toute écriture (`CAUSE_VERSION`), comme chez les quatre ouvreurs
            (T-00001075).
      * 5 REFUS : deux options EXCLUSIVES ensemble — `--base` et `--base-vivante`
        (désignation de base), OU `--re-exporter` et `--appliquer-depuis` (deux MODES :
        réparation vs jambe 1b — sans ce refus, `--re-exporter` AVALAIT
        `--appliquer-depuis` en silence, M1).
      * 6 REFUS DE LA BIBLIOTHÈQUE : une garde côté bibliothèque a levé
        `RunExportError` (auteur indisponible, `created_at` hors forme, base
        introuvable, re-export sans auteur, store sans colonne `ulid` dont le
        message nomme `create_tables()` (T-00001097)…). Fermé AU BORD par `except RunExportError`
        dans `_cli` — message sur STDERR, SANS traceback ; le `except` n'attrape QUE
        `RunExportError` (M2).
    HORS ÉNUMÉRATION, ASSUMÉ — une BORNE, pas une liste close (relevé non clos) :
      * une PANNE d'infrastructure HORS des refus classés du point 4
        (`OperationalError` ou `OSError` que `classer_refus` ne classe pas,
        `PanneInfrastructure`) sort en rc 1 avec traceback, cause chaînée —
        décision pilote S-00003489, aucun code dédié. PORTÉE, mesurée couture
        masquée : en forme PAQUET (`run_export` importé), la panne traverse
        `StoreV3Refuse` (EN PANNE) puis est relancée telle quelle, épinglé en
        processus par la famille (e) ; en forme chemin et `-m`, elle ne le
        traverse JAMAIS — sa classe est celle de `__main__`, que `classer_refus`
        ne reconnaît pas — et sort brute par l'`except PanneInfrastructure` de
        ce module : mesuré à la main (55 et 58 lignes sous `backfill`), non
        épinglé hors processus. `PanneInfrastructure` EST
        une `RunExportError` : elle est donc RELANCÉE avant le handler du code 6,
        qui la déguisait en refus (critic-opus T6, T-00000695/696 — mesuré : rc 6
        sur une panne simulée).
      * R3-bis, la COURSE, BORNÉE : version de la base RELUE sous le verrou (point
        4, T-00001082) ; non relue où rien n'est écrit (copie 1a, `--re-exporter`).
      * un store ANTÉRIEUR à ce binaire : accepté par la lecture de version, jamais
        monté ; sans colonne `ulid`, il sort au point 6 (T-00001097).
      * WAL ORPHELIN : un store refusé dont le `-wal` n'a pas été checkpointé
        (écrivain arrêté sans fermer, copie sans son checkpoint) voit ce `-wal`
        rabattu dans le fichier principal par la fermeture de la connexion de
        lecture — contenu intact, octets et annexes changés, comme la sonde de
        `create_tables`. De même, un `-journal` CHAUD (store en journal DELETE,
        écrivain mort en pleine transaction) est annulé à la première lecture —
        octets changés, `-journal` supprimé, contenu = dernier état committé.
        L'identité d'octets d'un store refusé vaut pour un store fermé
        proprement (mesuré darwin non-root, Linux et Windows non mesurés).
      * une base de 0 octet ou sans `events_ledger` (code 1) : rc 1 avec
        traceback (résidu R2). L'en-tête corrompu (code 11) et le store en
        LECTURE SEULE n'en sont plus (T-00001078) : un FICHIER en `chmod 444`
        (code 8 levé à l'UPDATE, WAL et DELETE) et un DOSSIER en lecture seule
        (1544, de primaire 8, à l'ouverture en WAL) sont REFUSÉS au point 4
        (mesuré darwin non-root).
      * la racine absente avec `--base` : `CadrePathError` brute, levée par
        `auteur_courant` AVANT l'ouverture (résidu R4).
      * APRÈS le commit — le décompte `ulid IS NULL` puis l'export : une levée y
        sort brute, base DÉJÀ écrite, jamais en refus (`CadrePathError` de
        `chemin_export`, résidu R9).
      * un `--base` LIEN : refus de la bibliothèque, rc 6 (point 6, inchangé).
      * un `BrokenPipeError` en 120 ; un SIGINT en 130.
    Ce ne sont PAS des refus classés : ni déguisés en code 4, ni en code 6. Les
    refus écrivent sur STDERR, jamais sur stdout."""
    parser = argparse.ArgumentParser(
        prog="run_export.py",
        description="Export versionné du run — backfill de l'historique et mesure "
        "(clause « run par auteur »).",
    )
    sous = parser.add_subparsers(dest="commande", required=True)
    p_bf = sous.add_parser(
        "backfill",
        help="frappe un ULID par ligne historique (ulid IS NULL), l'écrit en base, "
        "exporte sous runs/<auteur>/backfill/.",
    )
    p_bf.add_argument(
        "--base",
        default=None,
        help="base à frapper — une COPIE pour la jambe de lot 1a. SANS --base ni "
        "--base-vivante, le backfill est REFUSÉ (ne frappe pas la vivante en silence).",
    )
    p_bf.add_argument(
        "--base-vivante",
        dest="base_vivante",
        action="store_true",
        help="opt-in EXPLICITE à frapper la base VIVANTE (DEFAULT_DB_PATH) — requis "
        "puisque le défaut REFUSE (grave 2, S-00001808).",
    )
    p_bf.add_argument(
        "--appliquer-depuis",
        dest="appliquer_depuis",
        default=None,
        help="1b : applique à la base les ULID DÉJÀ frappés sur cette copie 1a "
        "(n'invente aucun ULID).",
    )
    p_bf.add_argument(
        "--re-exporter",
        dest="re_exporter",
        action="store_true",
        help="passe de RÉ-EXPORT (T1) : SELECT les lignes DÉJÀ frappées absentes du "
        "texte et les exporte sous backfill (répare une interruption du backfill).",
    )
    sous.add_parser("mesure", help="octets par mois et par auteur sous runs/.")
    args = parser.parse_args(argv)
    if args.commande == "backfill":
        # Contrat de refus AVANT toute frappe (ordre : exclusivités, base désignée,
        # existence). 5 prime sur 3 qui prime sur 4.
        if args.base is not None and args.base_vivante:
            print(
                "refus : --base et --base-vivante sont exclusifs (l'un OU l'autre "
                "désigne la base, jamais les deux).",
                file=sys.stderr,
            )
            return 5
        if args.re_exporter and args.appliquer_depuis is not None:
            # M1 (exec-critic sur da699e8) : les DEUX drapeaux de MODE sont exclusifs.
            # Avant, `--re-exporter` AVALAIT `--appliquer-depuis` en SILENCE (validé en
            # rc 4 si le chemin manquait, puis IGNORÉ) : l'opérateur croyait rejouer la
            # jambe 1b, jetait sa copie 1a -> doublon irréparable en AJOUT SEUL.
            print(
                "refus : --re-exporter et --appliquer-depuis sont exclusifs — "
                "--appliquer-depuis APPLIQUE les ULID d'une copie 1a (jambe 1b du "
                "backfill), --re-exporter RÉPARE une interruption en ré-exportant les "
                "lignes déjà frappées absentes du texte. Choisis UNE des deux.",
                file=sys.stderr,
            )
            return 5
        if args.base is None and not args.base_vivante:
            print(
                "refus : backfill ne frappe PAS la base vivante par défaut. Désigne "
                "la base par --base <chemin> (une copie) OU par le drapeau explicite "
                "--base-vivante (base VIVANTE).",
                file=sys.stderr,
            )
            return 3
        if args.base is not None and not Path(args.base).is_file():
            # A4 : `.is_file()` et non `.exists()` — un RÉPERTOIRE passait `.exists()`
            # puis `sqlite3.connect` levait une `OperationalError` NON attrapée -> rc 1,
            # traceback, HORS de l'énumération de refus (2–6). `.is_file()` le referme.
            print(
                f"refus : --base {args.base} n'est pas un fichier de base — "
                "sqlite3.connect créerait une base vide de 0 octet (ou échouerait sur "
                "un répertoire). Vérifie le chemin.",
                file=sys.stderr,
            )
            return 4
        if args.appliquer_depuis is not None and not Path(args.appliquer_depuis).is_file():
            print(
                f"refus : --appliquer-depuis {args.appliquer_depuis} n'est pas un "
                "fichier de base — aucune copie 1a à lire. Vérifie le chemin.",
                file=sys.stderr,
            )
            return 4
    # LEÇON (M2, exec-critic sur da699e8) : quand une CLI documente ses codes de
    # sortie comme une LISTE CLOSE, l'énumération se ferme AU BORD dans le MÊME geste
    # qui ajoute une garde côté bibliothèque — sinon la garde sort par un code NON
    # énuméré (mesuré : RunExportError -> traceback brut, rc 1, hors 0/2/3/4/5). Le
    # `except` n'attrape QUE `RunExportError` : une panne d'infrastructure
    # (OperationalError, OSError…) ne doit PAS être déguisée en refus de bibliothèque
    # (leçon déjà payée — binôme de T-650, un `except RunExportError` trop large).
    try:
        if args.commande == "backfill":
            # T-00001054 : import PARESSEUX, jamais en tête — la forme chemin amorce
            # `sys.path` APRÈS les imports du module.
            from agentic_v3.db.refus_store import EN_PANNE, StoreV3Refuse

            # --base-vivante => base=None (backfill_historique résout DEFAULT_DB_PATH).
            base_arg = args.base
            try:
                if args.re_exporter:
                    resultat = re_exporter_frappees(base=base_arg)
                else:
                    resultat = backfill_historique(
                        base=base_arg,
                        appliquer_depuis=args.appliquer_depuis,
                    )
            except StoreV3Refuse as exc:
                if exc.verdict == EN_PANNE:
                    # S-00003489 : la panne reste en rc 1, brute, cause chaînée. La
                    # clause `from` n'est PAS redondante : sans elle, une panne SANS
                    # cause traînerait ce refus dans sa trace (« During handling »).
                    # PORTÉE, mesurée : branche atteinte en forme PAQUET seulement.
                    # En forme chemin et `-m`, la panne est
                    # `__main__.PanneInfrastructure`, que `classer_refus` ne
                    # reconnaît pas : elle sort brute par l'`except
                    # PanneInfrastructure` ci-dessous, sans traverser ce refus.
                    raise exc.origine from exc.origine.__cause__
                print(f"run_export.py backfill: {exc}", file=sys.stderr)
                return RC_STORE_REFUSE
            print(json.dumps(resultat, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.commande == "mesure":
            print(json.dumps(mesurer_runs(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except PanneInfrastructure:
        raise  # une panne n'est pas un refus : rc 1 avec traceback, contrat ci-dessus
    except RunExportError as exc:
        print(f"refus de la bibliothèque : {exc}", file=sys.stderr)
        return 6
    return 2  # pragma: no cover - argparse required=True l'empêche


if __name__ == "__main__":  # pragma: no cover - point d'entrée CLI
    # La forme directe charge le paquet exact sans exposer src/ ni la racine.
    _vendor_paths().charger_paquet(_racine_depot(), "agentic_v3")
    raise SystemExit(_cli())
