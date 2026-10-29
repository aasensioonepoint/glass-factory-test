"""Refus NOMMÉ du store V3 par ses ouvreurs hors `tasks.py` (T-00001005, BK-408),
dont le 5e, `run_export._cli backfill` (T-00001054, T-00001075, T-00001074).

Avant ce module, un store illisible faisait lever la construction de
`SessionCheckpointManager`, `LessonsStore`, `SpecParser` et `EventStore` (sous
`cli.main`) : un traceback de 15 à 28 lignes et le code 1, qui gelaient leur
appelant ; `run_export.py backfill` sortait de même (18 à 32 lignes, rc 1).
Ici, UN type (`StoreV3Refuse`), UN classeur (`classer_refus`) et UN
gestionnaire de contexte (`refus_nomme`) qui transforme une levée CLASSÉE en ce
type, chaînée `from` l'origine ; toute autre levée remonte TELLE QUELLE.

ENSEMBLE, PAR TYPE RÉEL (`isinstance`, jamais le nom ni le message), celui que
`replay_sync` (`.agents/bin/tasks_sync.py`) appliquait à la construction du pont
V3 à T-00001005 :
`CadrePathError`, `SchemaVersionError`, `EmplacementRefuse`,
`OuvertureImpossible`, `HorsRacine`, `sqlite3.DatabaseError` de code primaire 26
(store non SQLite) ou 5 (verrou), et `PanneInfrastructure`, étiquetée « EN PANNE »
et non « REFUSÉ » : ce n'est pas un refus d'emplacement. Depuis T-00001056, le pont
refuse EN PLUS `PermissionError`, `NotADirectoryError`, `FileExistsError` et les
codes primaires 8 et 11 ; depuis T-00001078, `classer_refus` les classe AUSSI :
`PermissionError` (`CAUSE_NON_INSCRIPTIBLE`), `NotADirectoryError` et
`FileExistsError` (`CAUSE_OCCUPE`), le code 8, 1544 compris et 1032 excepté
(`CAUSE_LECTURE_SEULE`), et le code 11 (`CAUSE_CORROMPU`). Les trois sœurs `OSError`
sont classées une à une, jamais `OSError` entière ; `IsADirectoryError`,
`FileNotFoundError`, les codes 10, 14 et 19 et l'étendu 1032
(`SQLITE_READONLY_DBMOVED` : base déplacée ou supprimée sous la connexion, ce n'est
pas un store en lecture seule) restent HORS de l'ensemble. PORTÉE : les trois sœurs ne valent
que sous `erreurs_os` vrai (le défaut : la CONSTRUCTION) ; `cli.main` pose
`erreurs_os=False` autour du VERBE `sync-spec`, où une `PermissionError` peut
venir du SPEC et non du store (S-00003602). La table du témoin de parité porte
les cinq causes et leurs négatifs. `CadrePathError` est un
REFUS ici alors que `replay_sync` la traite en SAUT : pour un ouvreur, le store
EST le verbe, il n'y a rien à différer. La parité est tenue par le témoin
`.agents/evals/test_ouvreurs_parite_refus_v3.py`, dans les DEUX sens sur la table
de ce témoin : « refuse au moins ce que `replay_sync` avale » toujours, et l'égalité
des deux ensembles quand `tasks` expose `_annonce_refus_construction` (T-00001004).

Les classes de couture viennent de `run_export._couture_ledger_store()` et de
`run_export._cadre("paths")`, la MÊME couture mémoïsée que celle par laquelle
`schema.create_tables` les lève : même objet-classe. Couture indisponible : `()`
pour ses classes, jamais une levée. `run_export` et `schema` sont importés DANS
les fonctions (`schema` importe `run_export` paresseusement : aucun cycle).

BORNE : le refus vaut à la CONSTRUCTION des quatre ouvreurs ET, posé par
`cli.main` autour du VERBE `sync-spec` (T-00001059, décision pilote
S-00003420 : l'ensemble ci-dessus, SAUF les trois sœurs `OSError`, S-00003602), pendant `process_and_sync_spec`. Il
vaut AUSSI sous `run_export._cli backfill`, le 5e ouvreur, posé par `run_export`
lui-même (code 4 au bord de `_cli`) : à la résolution de la base, à l'ouverture
— lecture de version comprise, un store de schéma FUTUR y est refusé en
`CAUSE_VERSION` (T-00001075) —, à la première lecture (`backfill_historique`,
`_lire_triplets_source`, `re_exporter_frappees`, T-00001054) et pendant la
phase d'écriture de `backfill_historique`, du BEGIN IMMEDIATE au commit inclus
(T-00001074). Ailleurs, une erreur des méthodes qui rouvrent le store après la
construction reste hors de ce module (`status`, `resume`, `dashboard-summary` :
traceback, résidu nommé), comme, sous `backfill`, ce qui suit le commit
(décompte, exports : base déjà écrite). La bibliothèque elle-même ne convertit
rien : `SpecParser` relève l'erreur BRUTE, après sa compensation ; seul
`cli.main` la classe.
VERROU : en WAL (posé à chaque ouverture par `schema.get_db_connection`), un
écrivain tenu ne bloque pas la construction ; le verrou mord au premier write de
`sync-spec`, après l'attente de `schema._connexion_nue` (30 s, figée par
`test_l_attente_d_un_ecrivain_egale_celle_du_producteur_V3`), et sort désormais
en `CAUSE_VERROU`, code 4. Sous `backfill`, il mord à la phase d'écriture (en
WAL au BEGIN IMMEDIATE ; en journal DELETE au commit sous un lecteur tenu, au
BEGIN IMMEDIATE sous un écrivain tenu) et sort de même en `CAUSE_VERROU`, code 4,
base inchangée (T-00001074). À la construction, `CAUSE_VERROU` n'est atteint que
hors WAL ou par le tampon de version.

AFFICHAGE : la ligne de `StoreV3Refuse` est APLATIE — le message d'origine a ses
blancs réduits à une espace, puis tout caractère non imprimable (`isprintable()`
faux) de la ligne, chemin compris, devient `?` : un dossier nommé `a\\nb` ne fait
jamais sortir le refus sur deux lignes. Les attributs (`chemin`, `origine`)
gardent la valeur RÉELLE. `aplatir_message` rend ces deux temps publics pour la
ligne du code 3 de `cli.main` (S-00003354).
"""

import contextlib
import pathlib
import sqlite3
from typing import Any, Iterator, Optional, Tuple, Union

#: Verdicts portés par `StoreV3Refuse.verdict`.
REFUSE = "REFUSÉ"
EN_PANNE = "EN PANNE"

#: Affiché quand le chemin du store n'a pas pu être résolu (racine introuvable).
CHEMIN_NON_RESOLU = "chemin du store non résolu"

#: Codes PRIMAIRES SQLite reconnus (`sqlite_errorcode & 0xFF`), littéraux.
_SQLITE_BUSY = 5
_SQLITE_NOTADB = 26
_SQLITE_READONLY = 8
_SQLITE_CORRUPT = 11
#: Code ÉTENDU exclu du primaire 8 : base déplacée/supprimée sous la connexion, pas « lecture seule ».
_SQLITE_READONLY_DBMOVED = 1032

# Libellés de cause PROPRES à un ouvreur, jamais recopiés de `replay_sync` (les
# siens disent « board écrit » ou « miroir BLOQUÉ », faux pour une CLI) —
# SAUF les quatre derniers (T-00001078) : mot pour mot ceux de
# `_annonce_refus_construction` (`.agents/bin/tasks_sync.py`, branches (9)-(12)),
# repris à la main, jamais importés ; leur parité de libellé est témoignée par
# `test_libelles_des_quatre_causes_neuves_egaux_au_pont` (eval de parité).
CAUSE_RACINE = "racine de projet non résolue"
CAUSE_VERSION = "store plus récent que ce binaire"
CAUSE_EMPLACEMENT = "emplacement du store refusé (lien, second nom ou non régulier)"
CAUSE_OUVERTURE = "store non ouvrable (droits ou chemin)"
CAUSE_HORS_RACINE = "chemin hors racine"
CAUSE_NON_SQLITE = "store non SQLite"
CAUSE_VERROU = "store verrouillé (attente dépassée)"
CAUSE_PANNE = "panne d'infrastructure"
CAUSE_NON_INSCRIPTIBLE = "état machine non inscriptible"
CAUSE_OCCUPE = "chemin d'état occupé par un fichier"
CAUSE_LECTURE_SEULE = "store en lecture seule"
CAUSE_CORROMPU = "store corrompu"


def _aplatir(texte: str) -> str:
    """`texte` où chaque caractère non imprimable (`str.isprintable()` faux :
    sauts de ligne, retour chariot, tabulation, ESC, NUL, séparateurs Unicode)
    devient `?`. L'espace ASCII est imprimable : elle survit."""
    return "".join(c if c.isprintable() else "?" for c in texte)


def aplatir_message(texte: str) -> str:
    """`texte` sur UNE ligne affichable, en DEUX temps — ceux du message de
    `StoreV3Refuse` : ses blancs (sauts de ligne compris) réduits à une espace,
    puis chaque caractère non imprimable restant devenu `?` (`_aplatir`).
    Publique pour la ligne du code 3 de `cli.main` (T-00001059, S-00003354), qui
    n'importe ainsi aucune fonction privée d'un autre module."""
    return _aplatir(" ".join(texte.split()))


class StoreV3Refuse(Exception):
    """Le store V3 est refusé (ou en panne) à la construction d'un ouvreur.

    Porte `verdict` (`REFUSÉ` ou `EN PANNE`), `cause` (libellé propre),
    `chemin` (`Path`, ou `None` si non résolu) et `origine` (l'exception levée,
    aussi en `__cause__`). Son `str()` tient sur UNE ligne, tout entier passé par
    `_aplatir` : `store V3 <verdict> (<cause>) — <chemin> — <Type>: <message>`, le
    message ayant d'abord ses blancs réduits à une espace."""

    def __init__(
        self,
        verdict: str,
        cause: str,
        chemin: Optional[pathlib.Path],
        origine: BaseException,
    ) -> None:
        self.verdict = verdict
        self.cause = cause
        self.chemin = chemin
        self.origine = origine
        message = " ".join(str(origine).split())
        affiche = str(chemin) if chemin is not None else CHEMIN_NON_RESOLU
        super().__init__(_aplatir(
            f"store V3 {verdict} ({cause}) — {affiche} — {type(origine).__name__}: {message}"
        ))


def _classe(module: Any, nom: str) -> Any:
    """L'attribut `nom` de `module` s'il est une classe d'exception, sinon `()` :
    `isinstance(x, ())` rend False, jamais une levée (module `None`, paquet
    antérieur sans l'attribut, attribut qui n'est pas une classe)."""
    candidat = getattr(module, nom, None)
    if isinstance(candidat, type) and issubclass(candidat, BaseException):
        return candidat
    return ()


def classer_refus(
    exc: BaseException, *, erreurs_os: bool = True
) -> Optional[Tuple[str, str]]:
    """`(verdict, cause)` si `exc` est un refus de store de l'ensemble, sinon
    `None`. Ne lève JAMAIS. Ordre : `CadrePathError`, `SchemaVersionError`,
    `EmplacementRefuse`, `OuvertureImpossible` et `HorsRacine` (classes de
    couture, AVANT la branche par code : `OuvertureImpossible` est une
    `OperationalError` SANS code), puis, SI `erreurs_os` (le défaut),
    `PermissionError` (`CAUSE_NON_INSCRIPTIBLE`) et les deux sœurs
    `NotADirectoryError` et `FileExistsError` (`CAUSE_OCCUPE`) — jamais
    `OSError` entière —, puis `sqlite3.DatabaseError` de code primaire
    26, 5, 8 (`CAUSE_LECTURE_SEULE`, l'étendu 1544 compris ; l'étendu 1032,
    `SQLITE_READONLY_DBMOVED`, EXCLU : base déplacée ou supprimée sous la connexion)
    ou 11 (`CAUSE_CORROMPU`) : `sqlite_errorcode & 0xFF`, l'étendu 517 garde son
    primaire 5 ; enfin `PanneInfrastructure`. Sans `sqlite_errorcode` (erreur
    fabriquée à la main), `None`. `erreurs_os=False` (le VERBE `sync-spec`, où
    l'`OSError` peut venir du spec) ne classe AUCUNE des trois sœurs ; les codes 8
    et 11 restent classés."""
    try:
        from agentic_v3.db import run_export
    except Exception:  # paquet incomplet : aucune classe de couture
        run_export = None
    try:
        cadre_paths = run_export._cadre("paths") if run_export is not None else None
    except Exception:  # couture `cadre.paths` indisponible
        cadre_paths = None
    try:
        store_mod, workspace_mod = (
            run_export._couture_ledger_store() if run_export is not None else (None, None)
        )
    except Exception:  # couture indisponible : `PanneInfrastructure`, classée plus bas
        store_mod = workspace_mod = None
    try:
        from agentic_v3.db import schema
    except Exception:  # défensif : paquet incomplet
        schema = None

    if isinstance(exc, _classe(cadre_paths, "CadrePathError")):
        return REFUSE, CAUSE_RACINE
    if isinstance(exc, _classe(schema, "SchemaVersionError")):
        return REFUSE, CAUSE_VERSION
    if isinstance(exc, _classe(store_mod, "EmplacementRefuse")):
        return REFUSE, CAUSE_EMPLACEMENT
    if isinstance(exc, _classe(store_mod, "OuvertureImpossible")):
        return REFUSE, CAUSE_OUVERTURE
    if isinstance(exc, _classe(workspace_mod, "HorsRacine")):
        return REFUSE, CAUSE_HORS_RACINE
    if erreurs_os and isinstance(exc, PermissionError):
        return REFUSE, CAUSE_NON_INSCRIPTIBLE
    if erreurs_os and isinstance(exc, (NotADirectoryError, FileExistsError)):
        return REFUSE, CAUSE_OCCUPE
    if isinstance(exc, sqlite3.DatabaseError):
        code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(code, int):
            primaire = code & 0xFF
            if primaire == _SQLITE_NOTADB:
                return REFUSE, CAUSE_NON_SQLITE
            if primaire == _SQLITE_BUSY:
                return REFUSE, CAUSE_VERROU
            if primaire == _SQLITE_READONLY and code != _SQLITE_READONLY_DBMOVED:
                return REFUSE, CAUSE_LECTURE_SEULE
            if primaire == _SQLITE_CORRUPT:
                return REFUSE, CAUSE_CORROMPU
    if isinstance(exc, _classe(run_export, "PanneInfrastructure")):
        return EN_PANNE, CAUSE_PANNE
    return None


def _chemin_affiche(chemin: Union[str, pathlib.Path, None]) -> Optional[pathlib.Path]:
    """Le chemin à AFFICHER : celui reçu, sinon `DEFAULT_DB_PATH()` tenté pour
    l'affichage seul. Ne lève jamais : un échec de résolution (`CadrePathError`,
    ou toute autre levée) rend `None`, pour que le refus d'origine ne soit
    jamais remplacé par une levée sans rapport."""
    if chemin is not None:
        return pathlib.Path(chemin)
    try:
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        return DEFAULT_DB_PATH()
    except Exception:
        return None


@contextlib.contextmanager
def refus_nomme(
    chemin: Union[str, pathlib.Path, None] = None, *, erreurs_os: bool = True
) -> Iterator[None]:
    """Sous ce bloc, une `Exception` CLASSÉE par `classer_refus` devient
    `StoreV3Refuse(...) from exc` ; toute autre REMONTE, MÊME objet, sans
    chaînage ajouté. `chemin` ne sert qu'à l'affichage (`None` : défaut résolu
    au moment du refus, s'il se résout). `erreurs_os` est transmis tel quel à
    `classer_refus` : sous `False`, une sœur `OSError` (`PermissionError`,
    `NotADirectoryError`, `FileExistsError`) REMONTE, MÊME objet, au lieu d'être
    classée (T-00001078 : le verbe `sync-spec`)."""
    try:
        yield
    except Exception as exc:
        classe = classer_refus(exc, erreurs_os=erreurs_os)
        if classe is None:
            raise
        verdict, cause = classe
        raise StoreV3Refuse(verdict, cause, _chemin_affiche(chemin), exc) from exc
