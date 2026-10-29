"""record_id.py — ALLOCATION d'un identifiant `P-<ULID>` (T-00000726, forme A).

CE MODULE N'ALLOUE QUE. Il porte `mint(prefix)` et son erreur, rien d'autre
(décision S-00003552, forme A) : la LECTURE d'un id — `is_ulid_id`, `sort_key`,
`identity_key` — vit en fonctions PURES dans `tasks_stockage.py` (recopiées dans
`specs.py` et `ledger.py`), jamais ici. Une copie de la CLI SANS ce fichier LIT,
LISTE, DÉMARRE, BLOQUE et FERME donc comme avant ; seule l'allocation (après la
bascule C2) a besoin de lui.

FORME (décision S-00002657) : `<P>-<ULID>`, P ∈ {T, S, L}, ULID = 26 caractères
Crockford MAJUSCULES `[0-9A-HJKMNP-TV-Z]{26}`. Aucun compteur stocké.

GÉNÉRATEUR : `cadre.ledger.ids.nouvel_ulid` (stdlib seule), chargé par `mint`
SEUL — JAMAIS au chargement de ce module (dans `sys.modules`, un `import record_id`
ne pose que le résolveur `_cadre_vendor_paths_bin`, jamais `_cadre_ledger_ids_v3`). Ordre de résolution, même patron que la couture
`agentic_v3/db/run_export.py` (`_cadre` / `_charger_par_chemin`) :
  (0) la copie `_cadre_ledger_ids_v3` déjà chargée, si elle vient du fichier
      attendu (`_IDS_PATH`) ;
  (1) le paquet `cadre` : quand la racine porte un dossier `cadre`, CE paquet,
      chargé par `vendor_paths.charger_paquet` (provenance vérifiée) AVANT
      l'import — jamais `import_module` d'abord (S-01M5CN1KM2) ; sans dossier,
      le paquet importable ; toute `ImportError` (dont `ProvenanceRefusee`)
      passe à (2) ;
  (2) sinon `<dossier de cadre>/ledger/ids.py` PAR CHEMIN, racine = `parents[2]`
      de CE fichier, dossier de `cadre` donné par le RÉSOLVEUR `vendor_paths.py`
      (frère de ce fichier, T-01M5BXTGX5YN8XEXTG1PP7A5ZX phase B) :
      `.agents/vendor/cadre` s'il porte le paquet, sinon `src/cadre` ; résolveur
      ABSENT (copie partielle de `.agents/bin`), INCOMPLET (un nom de son API
      manque) ou paquet introuvable : `src/cadre`,
      le lieu d'avant la phase B, que le refus (3) nomme ;
      sous le nom `_cadre_ledger_ids_v3` — le MÊME nom que la
      couture, donc UNE seule copie (une seule horloge monotone) par processus ;
      la copie déjà présente dans `sys.modules` n'est relue que si son `__file__`
      est le fichier attendu ; enregistrée AVANT `exec_module`, et la copie
      d'avant rendue (ou le nom retiré) si l'exécution lève ;
  (3) sinon `RecordIdError` nommant le remède — FAIL-CLOSED : jamais `uuid`,
      jamais `random`, jamais un codec embarqué (S-00002657).

Stdlib seule ; du kit, ne charge que le résolveur `vendor_paths.py` (stdlib
seule), PAR CHEMIN, au chargement, sous le nom partagé `_cadre_vendor_paths_bin`
— le générateur (et le paquet `cadre` de la branche (1)) n'est jamais chargé
avant `mint`.
"""
from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

#: Le résolveur des deux emplacements, frère de CE fichier, sous un nom PARTAGÉ avec
#: `event_store.py`, `migrate_index_to_db.py` et `tasks_sync.py` : une seule copie
#: par processus, relue seulement si elle vient du fichier ATTENDU.
_NOM_RESOLVEUR = "_cadre_vendor_paths_bin"
#: L'API que les quatre producteurs lisent du résolveur ; un nom manquant (fichier vide, tronqué, d'une autre
#: version) = résolveur ABSENT, jamais un `AttributeError` qui refuserait le verbe.
_API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _resolveur() -> ModuleType | None:
    """Le résolveur COMPLET (toute `_API_RESOLVEUR`), ou `None` : absent,
    incomplet ou illisible (tronqué en pleine instruction : `SyntaxError` à
    l'exécution) comptent pareil — le repli `src/cadre` d'avant la phase B ; illisible le DIT
    en une ligne sur stderr (S-01M5CAG0HC)."""
    try:
        module = _charger_resolveur()
    except Exception as exc:  # illisible = ABSENT ; `_charger_resolveur` a déjà nettoyé `sys.modules`
        print(f"record_id: résolveur {Path(__file__).resolve().with_name('vendor_paths.py')} illisible "
              f"({type(exc).__name__}: {' '.join(str(exc).split())}) — repli sur src/cadre", file=sys.stderr)
        return None
    if module is None or any(not hasattr(module, nom) for nom in _API_RESOLVEUR):
        return None
    return module


def _charger_resolveur() -> ModuleType | None:
    """`vendor_paths.py`, frère de ce fichier, chargé PAR CHEMIN ; `None` s'il
    manque (copie partielle de `.agents/bin`). Enregistré avant `exec_module`,
    la copie d'avant rendue (ou le nom retiré) si l'exécution lève."""
    chemin = Path(__file__).resolve().with_name("vendor_paths.py")
    existant = sys.modules.get(_NOM_RESOLVEUR)
    fichier = getattr(existant, "__file__", None)
    if existant is not None and fichier and Path(fichier).resolve() == chemin:
        return existant
    if not chemin.is_file():
        return None
    spec = importlib.util.spec_from_file_location(_NOM_RESOLVEUR, chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NOM_RESOLVEUR] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if existant is not None:
            sys.modules[_NOM_RESOLVEUR] = existant
        else:
            sys.modules.pop(_NOM_RESOLVEUR, None)
        raise
    return module


def _dossier_cadre(racine: Path) -> Path:
    """Le dossier du paquet `cadre` sous `racine` selon le résolveur ; à défaut
    (résolveur absent, paquet introuvable) l'ancien lieu `src/cadre`."""
    resolveur = _resolveur()
    dossier = None if resolveur is None else resolveur.dossier_paquet(racine, "cadre")
    return dossier if dossier is not None else racine / "src" / "cadre"


#: Générateur par chemin : `<dossier de cadre>/ledger/ids.py` (voir `_dossier_cadre`).
_IDS_PATH = _dossier_cadre(Path(__file__).resolve().parents[2]) / "ledger" / "ids.py"
#: Nom de module PARTAGÉ avec `run_export._charger_par_chemin("ledger.ids")`.
_NOM_MODULE = "_cadre_ledger_ids_v3"
#: Préfixes admis : tâche, entrée de journal, leçon.
PREFIXES = ("T", "S", "L")
#: Grammaire PRIVÉE de SORTIE : ce que `mint` rend après le préfixe.
_CORPS_ULID = re.compile(r"\A[0-9A-HJKMNP-TV-Z]{26}\Z")


class RecordIdError(RuntimeError):
    """Générateur ULID introuvable, préfixe hors {T, S, L}, ou sortie hors
    grammaire : AUCUN identifiant n'est émis."""


def _paquet_ids() -> ModuleType:
    """Branche (1) : `cadre.ledger.ids` du paquet. La racine porte un dossier
    `cadre` : `charger_paquet` charge CE paquet (provenance vérifiée) avant
    l'import ; aucun dossier : le paquet importable, comme avant. Toute
    `ImportError` (dont `ProvenanceRefusee`, un `ledger/__init__` qui lève, un
    résolveur absent) renvoie au repli (2)."""
    racine = Path(__file__).resolve().parents[2]
    if (_IDS_PATH.parent.parent / "__init__.py").is_file():
        resolveur = _resolveur()
        if resolveur is None:
            raise ImportError("résolveur vendor_paths absent : (2) par chemin")
        resolveur.charger_paquet(racine, "cadre")
    return importlib.import_module("cadre.ledger.ids")


def _ids() -> ModuleType:
    """Le module générateur `cadre.ledger.ids`, résolu PARESSEUSEMENT (voir la
    docstring du module : copie déjà chargée, paquet, puis chemin, puis refus
    nommé ; jamais `import_module` avant la provenance, S-01M5CN1KM2)."""
    existant = sys.modules.get(_NOM_MODULE)
    fichier_existant = getattr(existant, "__file__", None)
    if existant is not None and fichier_existant is not None and (
        Path(fichier_existant) == _IDS_PATH
    ):
        return existant
    try:
        return _paquet_ids()  # (1) paquet
    except ImportError:
        pass
    if not _IDS_PATH.is_file():
        raise RecordIdError(
            f"générateur ULID introuvable : ni paquet `cadre`, ni {_IDS_PATH} — "
            "remède : installer le paquet cadre, ou resynchroniser le kit "
            "(.agents/vendor/cadre/ledger/ids.py à côté de .agents/bin/)"
        )
    spec = importlib.util.spec_from_file_location(_NOM_MODULE, _IDS_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise RecordIdError(f"générateur ULID non chargeable : {_IDS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # (2) repli PAR CHEMIN
    except BaseException:
        # Jamais une copie À MOITIÉ exécutée laissée à la relecture ; une copie
        # valide d'avant (autre fichier) est RENDUE, pas effacée.
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    return module


def mint(prefix: str) -> str:
    """Un identifiant NEUF `<prefix>-<ULID>`. Lève `RecordIdError` plutôt que
    d'émettre un id hors grammaire ou d'improviser un générateur."""
    if prefix not in PREFIXES:
        raise RecordIdError(f"préfixe {prefix!r} hors {PREFIXES}")
    corps = _ids().nouvel_ulid()
    if not isinstance(corps, str) or _CORPS_ULID.match(corps) is None:
        raise RecordIdError(f"générateur ULID : sortie {corps!r} hors grammaire")
    return f"{prefix}-{corps}"
