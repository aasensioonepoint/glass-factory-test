#!/usr/bin/env python3
"""Migrate the file index (`SYMBOLS*.md`, `CODEBASE_INDEX.md`, `INDEX_DELTA.json`) into a per-project SQLite
store (schema v3) that is MACHINE STATE, OUTSIDE THE REPOSITORY since T-00000668: `cadre.paths.index_db()`,
i.e. `state_project()/index/index.db`. `db_path()` below is a thin delegation to that single resolution
point — the wheel's `cadre.ledger.stores` resolves the same path through the same function. Nothing here is
to be committed any more; the append-only `annotations_log.jsonl` stays versioned next to the index files,
and `--apply` / `--resync` REPLAY it into the store (`apply_log`), so a store that is dropped and rebuilt
keeps, per key, the journal's last value of every field the files do not carry — a field the FILES carry
wins over any journal line (decision S-00002394), so `annotate`/`retire` on such a field lasts only until
the next `--resync` unless the `:: <field>` cell is edited in the files too.

LOCATION SEAM (T-00000668, S-00001655): `cadre.paths` is resolved (1) as the imported package when it comes
from this kit's own `cadre` folder (or no folder exists), else (2) by path from that `cadre/paths.py`
(`.agents/vendor/cadre`, else `src/cadre` — `vendor_paths.py`). When both fail every mode REFUSES naming
`cadre.paths` — never a fallback on the old in-repo path; outside a kit clone, without the package, the
SQLite index is ABSENT and `SYMBOLS*.md` remain the authority. `.agents/state/index/index.db` left at the old
path is a LEGACY DUPLICATE: named by a NOTE, never read, never touched.

THE PARSING IS NOT REWRITTEN. This script does `import build_index as bi` and reuses the REAL producers'
readers — `bi._parse_rows` (row grammar, `uses[]`, start-end ranges, tombstones), `bi.classify_index_files`
(ToC/stamp trust rule, L-023), `bi.read_delta_bound` (SYM-ID watermark, L-022), `bi.ROW_RE` (module table),
`bi._header_line` / `bi._header_field` (header fields). A duplicated grammar would drift from the writer's,
silently, and the drift would look like data loss nobody can date.

AND THE REFUSALS ARE IMPORTED WITH THE READS. Two guard rails apply on EVERY flag, because a DB that looks
valid and is short a few hundred symbols is the worst possible deliverable:

  * `bi.classify_index_files` returns a `status`; anything other than "ok" —
    notably `identity-lost`, SYMBOLS.md gone while shards remain — exits non-zero
    with the builder's own IDENTITY_LOST message. Never "optional file missing,
    noted".
  * `bi._parse_rows` SKIPS a malformed row in silence. The loud refusal is
    therefore a COUNT RECONCILIATION, not a second grammar — three cases, because
    a sharded ToC carries no parsable row by design:
        monolithic file  <->  its own `— N entries` header
        shard            <->  its own header
        sharded ToC      <->  the SUM of the actives of the shards it references
    plus total <-> `counts.active` of INDEX_DELTA.json. Any gap: exit non-zero,
    naming the file and both counts. A corrupted row becomes a count gap, never a
    silently dropped symbol — and a HEALTHY sharded tree never trips it.

IDENTITY IS (path, name, kind, ORDINAL), unchanged since the v2 schema (v3 adds the `body_sha` column and
moves no key). The index files legitimately carry several symbols of the same name AND kind in one file
(homonymous local constants across test blocks are the common shape), so v1's UNIQUE(path, name, kind) was
not a data-quality guard but a schema that could not REPRESENT the files: a real consumer index of 6351 live
symbols carried 5 colliding identities over 16 symbols (0.25 %), all in one test file, and `--resync`
refused outright — its committed DB could no longer be updated at all.

The ordinal numbers the members of a (path, name, kind) group 0, 1, 2 … in order of increasing START line.
THE START LINE ITSELF IS NOT IN THE KEY, deliberately: this key re-pairs SYM-IDs across two rebuilds
(`by_key`), so keying on the line would make every identifier move whenever code shifts down a file,
invalidating hand-written annotations and every `SYM-NNNN` cited in a past session. An ordinal moves only
when the RELATIVE order of homonyms inside the file changes.

The refusal survives for an ambiguity that is genuinely irreducible — two live rows sharing a name, a kind
AND a start line, which no ordering can separate — and `assign_ordinals` raises it during the READS, so
nothing is written and the message names what to do. A refusal that blocks everything is worse than a
precise one.

Flags: `--check` (writes NOTHING), `--apply` (create, atomically), `--verify` (round-trip files<->DB, plus
staleness), `--resync` (idempotent re-run with GUARDED upserts: compared before written, so zero changed
rows = zero written pages = stable bytes = no commit noise). A store on an OLDER schema is upgraded IN PLACE
by `--resync` (`SCHEMA_UPGRADES`, one rung per version): the v1 -> v2 rung adds the column and drops the old
index, so every SYM-ID, annotation, edge and journal row is preserved: the climb itself needs no replay of
`annotations_log.jsonl` (every `--apply`/`--resync` replays it anyway since T-00000668 — the file wins, else
the log's last value, `apply_log`). A store declaring a NEWER schema, or none at all, is refused by name —
never read as if it were current.

The migration NEVER deletes a source file. Retiring the shards is a later,
deliberate step; `--retire-shards` does not exist in v1, on purpose.

The DB is ADVISORY in v1: `build_index.py` keeps writing the FILES, so the machine store goes stale at every
rebuild. There is still no automatic trigger and no automatic resync — hence `--check` and `--verify`
compare `meta.built_at_sha` to the files' `built @` stamps and say `DB STALE` out loud (`--verify` also
exits non-zero). Never a silence that looks like freshness.

That comparison is ALSO consumed from outside, by `build_index.py --stale-check`, so the Stop-hook nudge can
name the staleness the pilot would otherwise never see (T-00000108). This module OWNS the comparison —
`db_generation_behind()` and its read-only, NON-CREATING `read_db_generation()` are its public surface;
nobody else queries `meta` by hand, so there is one freshness definition, not two.

Usage:
    python .agents/bin/migrate_index_to_db.py [--root DIR] (--check|--apply|--verify|--resync)

Exit codes: 0 = done (or a declared degradation); 1 = a refusal, named on stderr,
with nothing written. argparse's own usage errors keep exiting 2.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # run as a script OR imported from elsewhere
    sys.path.insert(0, str(HERE))

import build_index as bi  # noqa: E402  — path shim above must run first

SCHEMA_VERSION = 3
# The live-identity index, and the v1 name it REPLACES. Two distinct names on
# purpose: `CREATE UNIQUE INDEX IF NOT EXISTS` under the old name would silently
# no-op on a v1 store and leave the 3-column index — and its collisions — in
# place, which is exactly the "old store read as if it were new" failure.
LIVE_KEY_INDEX = "symbols_live_identity"
LEGACY_LIVE_KEY_INDEX = "symbols_live_key"
DB_NAME = "index.db"
LOG_NAME = "annotations_log.jsonl"
CODEBASE_NAME = "CODEBASE_INDEX.md"
STALE_MARKER = "DB STALE — lancer --resync"
# The `meta` key holding the index generation the DB was built from. A NAME, not a
# literal repeated at every reader: `build_index.py --stale-check` consumes this
# module's readers below, and a key spelled twice is a key that drifts once.
META_BUILT_AT_SHA = "built_at_sha"
# Cells the generator writes when a human has NOT written anything yet. They are
# mirrored verbatim into `modules` (that table is a mirror of the file) but never
# promoted into `annotations`, which holds AUTHORED content only.
PLACEHOLDERS = frozenset({"", "-", "—", "–", "?"})
# Journal rows are emitted in this fixed order so `seq` is a function of the
# delta's content alone — a resync on unchanged input must produce the same rows.
JOURNAL_KINDS = ("snapshot", "added", "changed", "removed")


class Refusal(Exception):
    """A named, loud stop. Nothing has been written when this is raised."""


# --------------------------------------------------------------------- reading
def repo_root(explicit: str | None = None) -> Path:
    """The project root: `--root` when given, else the git top level, else cwd."""
    if explicit:
        return Path(explicit).resolve()
    out = bi.git(Path.cwd(), "rev-parse", "--show-toplevel")
    return Path(out.strip()).resolve() if out and out.strip() else Path.cwd().resolve()


# --- T-00000668 : l'emplacement du store vient de `cadre.paths` (couture) ------
# Patron S-00001655 (`events.py::_redaction`) : (1) le paquet importé, seulement s'il vient du dossier de
# `cadre` (`verifier_charge`) ou sans dossier (S-01M5CN1KM2 : jamais `import_module` d'abord), sinon (2) le
# chargeur PAR CHEMIN depuis `paths.py` de ce dossier. Monkeypatchables (`_importer_cadre_paths_paquet`,
# `_CHEMIN_CADRE_PATHS`) ; succès mémoïsé, échec non. Un paquet TROP ANCIEN (sans `index_db`) = échec de (1).
# Le dossier vient du RÉSOLVEUR `vendor_paths.py` (`.agents/vendor/cadre`, sinon `src/cadre`), chargé PAR
# CHEMIN sous le nom partagé (record_id, event_store, tasks_sync) ; absent, incomplet ou illisible : `src/cadre`.
_NOM_RESOLVEUR = "_cadre_vendor_paths_bin"
_API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _executer(nom_module: str, chemin: Path, existant: Any) -> Any:
    """`chemin` exécuté sous `nom_module`, enregistré AVANT `exec_module` ; s'il lève, la copie
    d'avant (`existant`) est rendue ou le nom retiré — jamais une copie à moitié exécutée."""
    spec = importlib.util.spec_from_file_location(nom_module, chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise ImportError(f"{nom_module} introuvable ({chemin})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    return module


def _resolveur() -> Any:
    """`vendor_paths.py`, frère de ce fichier, s'il porte toute `_API_RESOLVEUR`, sinon `None` ;
    la copie de `sys.modules` n'est relue que si elle vient du fichier ATTENDU. Illisible
    (`SyntaxError`…) = ABSENT, et le repli le DIT en une ligne sur stderr (S-01M5CAG0HC)."""
    chemin = HERE / "vendor_paths.py"
    try:
        module = sys.modules.get(_NOM_RESOLVEUR)
        fichier = getattr(module, "__file__", None)
        if module is None or not fichier or Path(fichier).resolve() != chemin:
            if not chemin.is_file():
                return None
            module = _executer(_NOM_RESOLVEUR, chemin, module)
    except Exception as exc:
        print(f"migrate_index_to_db: résolveur {chemin} illisible ({type(exc).__name__}: "
              f"{' '.join(str(exc).split())}) — repli sur src/cadre", file=sys.stderr)
        return None
    return module if all(hasattr(module, nom) for nom in _API_RESOLVEUR) else None


def _dossier_cadre(racine: Path) -> Path:
    resolveur = _resolveur()
    dossier = None if resolveur is None else resolveur.dossier_paquet(racine, "cadre")
    return dossier if dossier is not None else racine / "src" / "cadre"


_CHEMIN_CADRE_PATHS = _dossier_cadre(HERE.parents[1]) / "paths.py"
_NOM_CADRE_PATHS_PAR_CHEMIN = "_cadre_paths_index"
_CADRE_PATHS: Any = None  # None = pas encore résolu


def _cadre_d_ici(dossier: Path) -> bool:
    """(1) admise : `dossier` sans paquet, ou le `cadre` chargé vient de la racine (`verifier_charge`)."""
    if not (dossier / "__init__.py").is_file():
        return True
    try:  # résolveur absent (None), `cadre` non chargé ou chargé d'un autre arbre : (2)
        return _resolveur().verifier_charge(HERE.parents[1], "cadre") is not None
    except Exception:
        return False


def _importer_cadre_paths_paquet() -> Any:
    """Branche (1) : `cadre.paths` par le paquet importé, de CE dossier (point de test)."""
    if not _cadre_d_ici(_CHEMIN_CADRE_PATHS.parent):
        raise ImportError("`cadre` d'un autre arbre ou non chargé : (2) par chemin")
    module = importlib.import_module("cadre.paths")
    if not callable(getattr(module, "index_db", None)):
        raise ImportError("le paquet `cadre` installé ne porte pas `cadre.paths.index_db` "
                          "(antérieur à T-00000668)")
    return module


def _cadre_paths() -> Any:
    """`cadre.paths`, en deux branches ; `Refusal` nommant `cadre.paths` si les deux échouent.
    Toute exception est attrapée par `Exception`, jamais par une classe importée : deux copies
    de `cadre.paths` peuvent coexister (paquet ET chargement par chemin), chacune avec SA classe."""
    global _CADRE_PATHS
    if _CADRE_PATHS is not None:
        return _CADRE_PATHS
    try:
        module = _importer_cadre_paths_paquet()  # (1) paquet installé
    except Exception as paquet_exc:
        try:
            spec = importlib.util.spec_from_file_location(
                _NOM_CADRE_PATHS_PAR_CHEMIN, _CHEMIN_CADRE_PATHS)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)  # (2) repli PAR CHEMIN, déclaré
        except Exception as chemin_exc:
            sys.modules.pop(_NOM_CADRE_PATHS_PAR_CHEMIN, None)
            raise Refusal(
                f"cadre.paths introuvable — l'emplacement du store SQLite de l'index ne peut pas être "
                f"résolu. Paquet installé : {type(paquet_exc).__name__}: {paquet_exc} ; chargement par "
                f"chemin {_CHEMIN_CADRE_PATHS} : {type(chemin_exc).__name__}: {chemin_exc}. Hors clone "
                f"du kit, installez la distribution `cadre-kit` (paquet d'import `cadre`) à source "
                f"épinglée — README du kit, § Install the core (glass-dist) ; les fichiers SYMBOLS*.md "
                f"restent l'autorité.") from chemin_exc
    _CADRE_PATHS = module
    return module


# --- T-00000770 : la couture `cadre.ledger.store` — le même patron, généralisé --
# `connect` ouvre le store par la primitive NON SUIVIE du paquet (`cadre.ledger.store.refuser_les_liens`
# / `ouvrir_sans_suivre`). `_cadre_module` GÉNÉRALISE `_cadre_paths` (gardée : ses points de moquerie sont
# ceux de `test_index_machine.py`). Mêmes règles : (1) si `_cadre_d_ici()`, sinon (2) `<_SRC_CADRE>/<nom>.py`
# par chemin (stdlib-seule), `sys.modules` relu sur le fichier ATTENDU, succès mémoïsé, échec non.
_SRC_CADRE = _CHEMIN_CADRE_PATHS.parent
_MODULES_CADRE: dict[str, Any] = {}


def _charger_par_chemin(nom: str) -> Any:
    """Branche (2) de `_cadre_module` : `<_SRC_CADRE>/<nom>.py` chargé PAR CHEMIN sous
    `_cadre_<nom>_index`, sans mémo ; `sys.modules` relu seulement si la copie vient du
    fichier ATTENDU, une exécution ratée y rend la copie d'avant (`_executer`)."""
    chemin = _SRC_CADRE.joinpath(*nom.split(".")).with_suffix(".py")
    nom_module = "_cadre_" + nom.replace(".", "_") + "_index"
    existant = sys.modules.get(nom_module)
    fichier_existant = getattr(existant, "__file__", None)
    if existant is not None and fichier_existant is not None and Path(fichier_existant) == chemin:
        return existant
    return _executer(nom_module, chemin, existant)  # (2) repli PAR CHEMIN, déclaré


def _cadre_module(nom: str) -> Any:
    """`cadre.<nom>`, mémoïsé sur succès. Jamais `import_module` d'abord (S-01M5CN1KM2) : (1) si
    `_cadre_d_ici()`, sinon ou s'il lève (2) `<_SRC_CADRE>/<nom>.py` (`_charger_par_chemin`)."""
    module = _MODULES_CADRE.get(nom)
    if module is not None:
        return module
    try:
        module = importlib.import_module(f"cadre.{nom}") if _cadre_d_ici(_SRC_CADRE) else _charger_par_chemin(nom)
    except Exception:
        module = _charger_par_chemin(nom)
    _MODULES_CADRE[nom] = module
    return module


#: Ce que la couture EXIGE de chaque module — un module qui n'en porte pas un est
#: un paquet `cadre` antérieur à T-00000770.
_PRIMITIVE_CADRE = (("ledger.store", ("refuser_les_liens", "ouvrir_sans_suivre",
                                      "EmplacementRefuse")),
                    ("workspace", ("Workspace",)))


def _decrire_module(module: Any) -> str:
    return f"{getattr(module, '__name__', module)} ({getattr(module, '__file__', '?')})"


def _couture_ledger_store() -> tuple[Any, Any]:
    """`(cadre.ledger.store, cadre.workspace)`, ou `Refusal` nommant
    `cadre.ledger.store` si la couture manque par les deux branches. Un module
    TROUVÉ sans la primitive — un paquet `cadre` installé antérieur à T-00000770
    — n'arrête PAS la couture : elle retente PAR CHEMIN (`_charger_par_chemin`,
    binôme F2) et mémoïse la copie qui répond ; le `Refusal` ne tombe que si la
    copie par chemin échoue AUSSI, et nomme alors le module périmé (`__name__`
    ET `__file__`). Toute exception est attrapée par `Exception`, jamais par une
    classe importée (deux copies peuvent coexister, comme pour `_cadre_paths`)."""
    try:
        modules = []
        for nom, attributs in _PRIMITIVE_CADRE:
            module = _cadre_module(nom)
            manque = [a for a in attributs if not callable(getattr(module, a, None))]
            if manque:
                perime = (f"{_decrire_module(module)} ne porte pas {', '.join(manque)} "
                          f"(antérieur à T-00000770 ?)")
                try:
                    module = _charger_par_chemin(nom)
                except Exception as exc:
                    raise AttributeError(f"{perime} ; la copie par chemin a échoué aussi : "
                                         f"{type(exc).__name__}: {exc}") from exc
                encore = [a for a in attributs if not callable(getattr(module, a, None))]
                if encore:
                    raise AttributeError(f"{perime} ; la copie par chemin "
                                         f"{_decrire_module(module)} ne porte pas "
                                         f"{', '.join(encore)} non plus")
                _MODULES_CADRE[nom] = module
            modules.append(module)
        store_mod, workspace_mod = modules
    except Exception as exc:
        raise Refusal(
            f"cadre.ledger.store introuvable ou incomplet — le store SQLite de l'index ne s'ouvre pas sans "
            f"sa primitive d'ouverture non suivie ({type(exc).__name__}: {exc}). Hors clone du kit, "
            f"installez la distribution `cadre-kit` (paquet d'import `cadre`) à source épinglée — README du "
            f"kit, § Install the core (glass-dist) ; les fichiers SYMBOLS*.md restent l'autorité.") from exc
    return store_mod, workspace_mod


def db_path(root: Path) -> Path:
    """Where the SQLite store of `root` lives: `cadre.paths.index_db(root)`, MACHINE
    state outside the repository (T-00000668). Creates nothing.

    `Refusal` — never an answer at another place — when `cadre.paths` cannot be
    loaded, when it cannot resolve `root`, or when the root it RESOLVES
    (`$CADRE_PROJECT_ROOT`, then the git top level) is not the root asked for:
    same guard as `cadre.ledger.stores.chemins_des_stores`, because reading or
    writing the store of ANOTHER project would be a silent divergence. A `.agents/`
    living in a SUBDIRECTORY of a git repository is refused for the same reason.
    """
    cp = _cadre_paths()
    try:
        demandee = cp.canonique_disque(Path(root).resolve())
        resolue = cp.project_root(depuis=root)
        cible = cp.index_db(depuis=root)
    except Exception as exc:
        raise Refusal(f"cadre.paths n'a pas résolu l'emplacement de l'index pour "
                      f"{root} : {type(exc).__name__}: {exc}") from exc
    if resolue != demandee:
        raise Refusal(
            f"racine demandée {demandee} ≠ racine résolue {resolue} par cadre.paths "
            f"($CADRE_PROJECT_ROOT ou la racine git prime) : le store d'un AUTRE "
            f"projet ne se lit ni ne s'écrit. Nommez la bonne racine par --root, ou "
            f"retirez la variable d'environnement.")
    return cible


def legacy_db_path(root: Path) -> Path:
    """The pre-T-00000668 in-repo location. NEVER read, never written: named only."""
    return bi.index_dir(root) / DB_NAME


def legacy_note(root: Path, target: Path | None = None) -> str | None:
    """`doublon hérité …` when a store still sits at the old in-repo path, else None.
    The file is left exactly as it is: removing it is the pilot's gesture, and the
    NOTE NAMES that gesture (critic-opus F4) — at an adopter the old path can be
    TRACKED and IGNORED at once (committed before the ignore rule landed), where
    a plain delete would show as a deletion to commit and `git add` would refuse."""
    old = legacy_db_path(root)
    try:
        if not old.is_file():
            return None
        if target is not None and old.resolve() == Path(target).resolve():
            return None
    except OSError:
        return None
    return (f"doublon hérité {old} — plus lu depuis T-00000668 ; s'il est suivi : "
            f"`git rm --cached {old}` puis commit, sinon le supprimer")


def log_path(root: Path) -> Path:
    return bi.index_dir(root) / LOG_NAME


def header_count(text: str | None) -> int | None:
    """The `— N entries` count a symbol file declares for itself, or None.

    Read with the BUILDER's own header-field extractor, against the header the
    builder writes (`# Symbols — N entries — built @ …`).
    """
    raw = bi._header_field(bi._header_line(text), "Symbols —", r"\d+")
    return int(raw) if raw is not None else None


@dataclass
class ModuleRow:
    path: str
    role: str
    depends_on: str
    owner: str


@dataclass
class State:
    """Everything the index FILES say, read once, before any write."""

    root: Path
    generation: str | None = None
    stamps: set[str] = field(default_factory=set)
    symbols: dict[int, dict] = field(default_factory=dict)
    edges: set[tuple[int, int]] = field(default_factory=set)
    modules: list[ModuleRow] = field(default_factory=list)
    modules_present: bool = False
    annotations: dict[tuple[str, str], dict] = field(default_factory=dict)
    homonyms: dict[tuple[str, str, str], int] = field(default_factory=dict)
    journal: list[tuple[int, str, str, str]] = field(default_factory=list)
    watermark: int = 0
    delta_bound: int | None = None
    max_id_seen: int = 0
    notes: list[str] = field(default_factory=list)
    # THE ONE HOME OF "the body map is unusable" (↯ C43, T-00000377).
    # `None` = the lateral INDEX_BODIES.json was read and agrees with the files'
    # generation, so `symbols[id]["body_sha"]` is authoritative — including when
    # it is None, which then means "this symbol has no hash". Anything else is
    # the REASON, and both readers that care — `write_state`'s fusion and
    # `verify`'s field comparison — test THIS field and no other. Two
    # hand-rolled "is the lateral usable" tests would drift apart.
    bodies_note: str | None = None

    @property
    def live(self) -> list[dict]:
        return [s for s in self.symbols.values() if not s["deleted"]]

    @property
    def tombstones(self) -> list[dict]:
        return [s for s in self.symbols.values() if s["deleted"]]

    def by_key(self) -> dict[tuple[str, str, str, int], int]:
        """`{(path, name, kind, ordinal): id}` over the LIVING — the re-pairing key.

        The ordinal is what makes this a bijection when a file carries homonyms;
        see `assign_ordinals` for why the start line is deliberately absent.
        """
        return {(s["path"], s["name"], s["kind"], s["ordinal"]): s["id"]
                for s in self.live}


def read_delta(root: Path) -> tuple[dict | None, list[str]]:
    """INDEX_DELTA.json as a dict, plus the notes its absence/corruption owes."""
    raw = bi._read(bi.index_dir(root) / bi.DELTA_NAME)
    if raw is None:
        return None, [f"{bi.DELTA_NAME} absent — journal and watermark bound empty"]
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, [f"{bi.DELTA_NAME} unparseable — journal and watermark bound empty"]
    if not isinstance(payload, dict):
        return None, [f"{bi.DELTA_NAME} is not an object — journal empty"]
    return payload, []


def read_modules(root: Path) -> tuple[list[ModuleRow], bool, list[str]]:
    """The `## Modules` table of CODEBASE_INDEX.md, parsed with `bi.ROW_RE`."""
    text = bi._read(bi.index_dir(root) / CODEBASE_NAME)
    if text is None:
        return [], False, [f"{CODEBASE_NAME} absent — modules table empty"]
    rows: list[ModuleRow] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## Modules"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if not inside:
            continue
        m = bi.ROW_RE.match(line)
        if not m:
            continue
        path, role, depends, owner = (g.strip() for g in m.groups())
        if path == "Path" or set(path) <= set("-: ") or path.startswith("("):
            continue  # column header, separator rule, or the `(N more)` overflow row
        rows.append(ModuleRow(path, role, depends, owner))
    return rows, True, []


def build_journal(delta: dict | None) -> list[tuple[int, str, str, str]]:
    """`INDEX_DELTA.json` as journal rows — deterministic seq, sorted payloads."""
    if not delta:
        return []
    at_sha = str(delta.get("built_sha") or "")
    bodies = {
        "snapshot": {k: delta.get(k) for k in ("counts", "sharded", "shards", "backend")},
        "added": delta.get("added"),
        "changed": delta.get("changed"),
        "removed": delta.get("removed"),
    }
    rows: list[tuple[int, str, str, str]] = []
    for kind in JOURNAL_KINDS:
        body = bodies.get(kind)
        if body in (None, [], {}):
            continue
        rows.append((len(rows) + 1, at_sha, kind,
                     json.dumps(body, sort_keys=True, ensure_ascii=False)))
    return rows


def key_label(key: tuple[str, str, str, int]) -> str:
    """`path:name` for a lone symbol, `path:name#ordinal` for one of a group."""
    path, name, _kind, ordinal = key
    return f"{path}:{name}" + (f"#{ordinal}" if ordinal else "")


def assign_ordinals(symbols: Iterable[dict]) -> dict[tuple[str, str, str], int]:
    """Number each (path, name, kind) group 0, 1, 2 … by increasing START line.

    Mutates every row in place, adding `ordinal`. Tombstones get 0 and are not
    grouped: the live-identity index is partial (`WHERE deleted = 0`), and a
    retired id is kept forever precisely so several of them may share a name.

    Returns `{group_key: size}` for the groups that actually carry homonyms, so
    the caller can REPORT the disambiguation instead of performing it invisibly.

    THE START LINE IS NOT PART OF THE IDENTITY, only of the ordering. That is the whole design: this key
    re-pairs SYM-IDs between two rebuilds, so a key holding the line number would rename every symbol below
    an inserted function — killing the hand-written annotations keyed on SYM-ID and every reference a past
    session wrote down. An ordinal shifts only when the relative order of the homonyms themselves changes,
    which is rare and visible.

    Refuses on the one ambiguity ordering cannot break: two live rows with the same name, kind AND start
    line. Raised here, among the reads, so nothing has been written when it fires.
    """
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for sym in symbols:
        sym["ordinal"] = 0
        if sym["deleted"]:
            continue
        groups.setdefault((sym["path"], sym["name"], sym["kind"]), []).append(sym)

    clashes: list[str] = []
    sizes: dict[tuple[str, str, str], int] = {}
    for key, rows in sorted(groups.items()):
        if len(rows) == 1:
            continue
        sizes[key] = len(rows)
        # `start` is None only on a malformed live row; sort it first rather than
        # comparing None to an int, and let the duplicate check below judge it.
        rows.sort(key=lambda s: (-1 if s["start"] is None else s["start"], s["id"]))
        starts = [s["start"] for s in rows]
        if len(set(starts)) != len(starts):
            path, name, kind = key
            doubled = sorted({s for s in starts if starts.count(s) > 1},
                             key=lambda v: (v is None, v))
            clashes.append(
                f"{path} {name} {kind}: "
                + ", ".join(f"line {s} claimed by "
                            + " and ".join(bi.sid(r["id"]) for r in rows
                                           if r["start"] == s)
                            for s in doubled))
            continue
        for ordinal, sym in enumerate(rows):
            sym["ordinal"] = ordinal

    if clashes:
        # LE MESSAGE ACCUSAIT L'EXTRACTEUR, ET C'ÉTAIT FAUX (T-00000609).
        # Il affirmait « not a legitimate pair of homonyms » et concluait que,
        # si la ligne survivait à un `--full`, l'extracteur émettait un symbole
        # deux fois. REPRODUIT EN 46 OCTETS : `ctags --output-format=json
        # --fields=+nK` sur `class A{f(){}}class B{f(){}}` émet DEUX tags `f`,
        # kind=method, line=1, scope=A et scope=B. Deux homonymes sur une MÊME
        # ligne sont donc parfaitement légitimes en JavaScript — et le message
        # envoyait le lecteur chercher un défaut d'extracteur qui n'existe pas.
        # C'est la faute que la règle d'or nomme : une affirmation qui promet une
        # garantie que l'outil ne tient pas empêche de voir le vrai défaut.
        #
        # LE REFUS RESTE, et c'est délibéré : cette fonction numérote par
        # ORDINAL, donc deux lignes identiques au même départ ne peuvent pas être
        # départagées ici sans une clé de plus. Ce qui change est ce qu'on en
        # DIT, et ce qu'on demande au lecteur de faire. Départager par COLONNE —
        # ctags la donne — est une décision qui reste à prendre, portée par
        # T-00000609 : ce commentaire ne la préempte pas.
        raise Refusal(
            "two live symbols are identical AND start on the same line, so the "
            "ordinal numbering used here cannot tell them apart:\n  - "
            + "\n  - ".join(clashes)
            + "\n  THIS IS NOT NECESSARILY AN EXTRACTOR BUG. In JavaScript two "
              "homonyms legitimately share a line — measured, ctags emits two "
              "`f` method tags on `class A{f(){}}class B{f(){}}`, scoped A and "
              "B — and a MINIFIED BUNDLE puts hundreds of symbols on one line, "
              "so it hits this every time.\n"
              "  do this: (1) check whether the file is a built/minified bundle "
              "— if so it should not be indexed at all, see T-00000609; (2) "
              "otherwise re-publish with `python .agents/bin/build_index.py "
              "--full` and, if the row survives, report the file and line. "
              "Nothing was written here either way.")
    return sizes


def _reconcile(root: Path, authoritative: Sequence[Path], texts: dict[Path, str],
               parsed: dict[Path, list[dict]], delta: dict | None,
               total_live: int) -> None:
    """The loud half of the reads: counts must add up, or nothing is written.

    Three cases (a sharded ToC carries no parsable row by design), then the
    grand total against `counts.active`.
    """
    idx = bi.index_dir(root)
    main = idx / bi.MAIN_NAME
    referenced = set(bi.TOC_SHARD_RE.findall(texts.get(main, "")))
    gaps: list[str] = []

    missing = sorted(n for n in referenced if not (idx / n).exists())
    if missing:
        gaps.append(f"{bi.MAIN_NAME}: ToC references shards that are not on disk: "
                    + ", ".join(missing))

    for path in authoritative:
        declared = header_count(texts.get(path))
        if declared is None:
            gaps.append(f"{path.name}: no `— N entries` header count to reconcile "
                        f"against (header: {bi._header_line(texts.get(path))!r})")
            continue
        if path == main and referenced:
            # Case 3: the ToC counts the whole generation, its shards carry it.
            summed = sum(
                sum(1 for r in parsed.get(idx / name, []) if not r["deleted"])
                for name in sorted(referenced)
            )
            if declared != summed:
                gaps.append(f"{path.name}: ToC header declares {declared} entries, "
                            f"referenced shards parse {summed} active rows")
            continue
        actives = sum(1 for r in parsed.get(path, []) if not r["deleted"])
        if declared != actives:
            gaps.append(f"{path.name}: header declares {declared} entries, "
                        f"{actives} active rows parsed")

    if delta:
        counts = delta.get("counts")
        declared_total = counts.get("active") if isinstance(counts, dict) else None
        if isinstance(declared_total, int) and declared_total != total_live:
            gaps.append(f"{bi.DELTA_NAME}: counts.active is {declared_total}, "
                        f"{total_live} live symbols ingested")

    if gaps:
        raise Refusal(
            "count reconciliation failed — a row was skipped by the parser or a "
            "file is out of sync; refusing to write a plausible-looking, "
            "incomplete DB:\n  - " + "\n  - ".join(gaps))


def read_state(root: Path) -> State:
    """Read every index file into one State, or refuse loudly. Writes nothing."""
    authoritative, watermark_only, status = bi.classify_index_files(root)
    if status == "identity-lost":
        raise Refusal(bi.IDENTITY_LOST)
    if status != "ok":
        raise Refusal(f"index status {status!r} — nothing authoritative to migrate; "
                      f"run build_index.py first")

    state = State(root=root)
    texts: dict[Path, str] = {}
    parsed: dict[Path, list[dict]] = {}
    for path in authoritative:
        text = bi._read(path)
        if text is None:
            raise Refusal(f"{path.name} vanished between classification and read — "
                          f"re-run once the tree is stable")
        texts[path] = text
        parsed[path] = list(bi._parse_rows(text))
        stamp = bi._generation(text)
        if stamp:
            state.stamps.add(stamp)

    state.generation = bi._generation(texts.get(bi.index_dir(root) / bi.MAIN_NAME))

    # The body hashes come from the LATERAL map, not from the rows: the SYM-NNN
    # grammar is untouched by design (T-00000377, §2A). The builder owns both the
    # reading and the generation check, so there is one definition of "usable"
    # here as there is one definition of "stale" in `db_generation_behind`.
    bodies, state.bodies_note = bi.read_bodies(root, state.generation)
    if state.bodies_note:
        # NAMED, never tacit: --check/--apply/--resync/--verify all print
        # `state.notes`, so a store whose body column cannot be compared says so
        # in the same report that declares it healthy.
        state.notes.append(state.bodies_note)

    # Ingestion, in classification order: later files win on a repeated id, the
    # same last-writer-wins the shard glob gives the builder.
    for path in authoritative:
        stamp = bi._generation(texts[path]) or ""
        for row in parsed[path]:
            state.symbols[row["id"]] = {
                "id": row["id"],
                "path": row.get("path"),
                "name": row["name"],
                "kind": row["kind"],
                "start": row.get("start"),
                "end": row.get("end"),
                "deleted": bool(row["deleted"]),
                "generation": stamp,
                # A tombstone never carries one: a deleted body has no hash.
                "body_sha": (None if row["deleted"]
                             else bodies.get(row["id"])),
            }
            if row["deleted"]:
                continue
            for dst in row.get("uses", []):
                state.edges.add((row["id"], int(dst)))
            purpose = (row.get("purpose") or "").strip()
            if purpose:
                state.annotations[("symbol", str(row["id"]))] = {
                    "purpose": purpose, "role": None, "owner": None}

    # Identity closes here: the ordinal that separates legitimate homonyms is a
    # function of the ingested rows alone, and its refusal fires before any write.
    state.homonyms = assign_ordinals(state.symbols.values())

    # L-023: an unreferenced shard of the SAME generation feeds the bound and
    # NOTHING else — merging its rows could resurrect a tombstone.
    ids_seen = [s["id"] for s in state.symbols.values()]
    for path in watermark_only:
        text = bi._read(path)
        if text is None:
            continue
        ids_seen += [r["id"] for r in bi._parse_rows(text)]
        state.notes.append(f"{path.name}: unreferenced shard of the current "
                           f"generation — watermark-only (L-023), rows NOT ingested")
    state.max_id_seen = max(ids_seen, default=0)

    delta, delta_notes = read_delta(root)
    state.notes += delta_notes
    state.delta_bound = bi.read_delta_bound(root)
    # L-022: the bound is an UPPER bound that may exceed anything on disk. Never
    # recomputed from the files alone, never lowered.
    state.watermark = max(state.delta_bound or 0, state.max_id_seen)
    state.journal = build_journal(delta)

    modules, present, module_notes = read_modules(root)
    state.modules, state.modules_present = modules, present
    state.notes += module_notes
    for mod in modules:
        role = mod.role if mod.role not in PLACEHOLDERS else None
        owner = mod.owner if mod.owner not in PLACEHOLDERS else None
        if role or owner:
            state.annotations[("module", mod.path)] = {
                "purpose": None, "role": role, "owner": owner}

    _reconcile(root, authoritative, texts, parsed, delta, len(state.live))
    return state


# ---------------------------------------------------------------------- schema
SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS meta("
    " key TEXT PRIMARY KEY, value TEXT)",
    # `ordinal` THEN `body_sha` ARE LAST, IN THAT ORDER, on purpose: each was
    # added by an upgrade rung (v1 -> v2 for `ordinal`, v2 -> v3 for `body_sha`)
    # and ALTER TABLE can only APPEND, so declaring them last, in the order the
    # rungs run, makes a freshly created store and an upgraded one structurally
    # identical — same column order, same `.dump`, no spurious diff between two
    # projects on the same version. Anything added later goes after `body_sha`.
    "CREATE TABLE IF NOT EXISTS symbols("
    " id INTEGER PRIMARY KEY, path TEXT, name TEXT, kind TEXT,"
    " start INTEGER, \"end\" INTEGER,"
    " deleted INTEGER NOT NULL DEFAULT 0, generation TEXT,"
    " ordinal INTEGER NOT NULL DEFAULT 0, body_sha TEXT)",
    # Identity is unique among the LIVING only: tombstones are kept forever and
    # several of them may share a name. `ordinal` separates the homonyms a single
    # file may legitimately carry (v2) — without it this index refused whole
    # real-world indexes; see the module docstring.
    f"CREATE UNIQUE INDEX IF NOT EXISTS {LIVE_KEY_INDEX}"
    " ON symbols(path, name, kind, ordinal) WHERE deleted = 0",
    "CREATE TABLE IF NOT EXISTS edges("
    " src_id INTEGER, dst_id INTEGER, PRIMARY KEY(src_id, dst_id))",
    "CREATE TABLE IF NOT EXISTS modules("
    " path TEXT PRIMARY KEY, role TEXT, depends_on TEXT, owner TEXT)",
    # Authored content, in its own table: a deterministic rebuild of the derived
    # tables can never overwrite it.
    "CREATE TABLE IF NOT EXISTS annotations("
    " scope TEXT NOT NULL CHECK(scope IN ('symbol','module')), key TEXT NOT NULL,"
    " purpose TEXT, role TEXT, owner TEXT, PRIMARY KEY(scope, key))",
    "CREATE TABLE IF NOT EXISTS journal("
    " seq INTEGER PRIMARY KEY, at_sha TEXT, kind TEXT, payload TEXT)",
)
FTS_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts"
           " USING fts5(name, path, purpose)")


def fts_probe() -> bool:
    """Is FTS5 compiled into THIS interpreter's sqlite3? Asked before writing."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(FTS_SQL)
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def connect(path: Path) -> sqlite3.Connection:
    """A connection in the default rollback-journal mode, on an EXISTING store,
    opened WITHOUT FOLLOWING (T-00000770).

    WAL is deliberately NOT enabled: it would add `-wal`/`-shm` sidecar files
    next to a store meant to be ONE self-contained file (it was committed until
    T-00000668; the wheel's `garantir_index` keeps the same `delete` mode).

    The store is opened through `cadre.ledger.store` (`_couture_ledger_store`): `refuser_les_liens`, then
    `ouvrir_sans_suivre(creer=False)` on a nude connection. `Refusal` — nothing followed, nothing created —
    when the store is ABSENT (`connect` never creates: `run_check`, `run_resync` and `run_verify` test
    existence first, and `_atomic_create` opens a file born by `mkstemp`), when its location is refused (a
    link, pending or not, a second hard name, a non-regular file, a name that changed between the check and
    the open: same message as the primitive's), or when the seam is missing.
    """
    path = Path(path)
    store_mod, workspace_mod = _couture_ledger_store()
    try:
        atelier = workspace_mod.Workspace(path.parent)
        store_mod.refuser_les_liens(atelier, path.name)
        if atelier.identite(path.name) is None:
            raise Refusal(
                f"{path} n'existe pas — rien n'a été créé : `connect` n'ouvre qu'un "
                f"store existant (T-00000770), un outil ne laisse jamais une base de "
                f"0 octet derrière lui. Créez-le par `--apply`.")
        conn, _ident, _cree = store_mod.ouvrir_sans_suivre(
            atelier, path.name, creer=False,
            connecter=lambda uri: sqlite3.connect(uri, uri=True, isolation_level=None))
    except ValueError as exc:
        raise Refusal(str(exc)) from exc
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> bool:
    """Create the current tables. Returns whether FTS5 is available (detected).

    Creation only — it never MIGRATES. An existing store is brought to the current
    version by `upgrade_schema`, which must run FIRST: every statement here is
    `IF NOT EXISTS`, so on an older store this call would quietly leave the old
    shape standing.
    """
    for stmt in SCHEMA_SQL:
        conn.execute(stmt)
    try:
        conn.execute(FTS_SQL)
    except sqlite3.OperationalError:
        return False
    return True


# ------------------------------------------------------------- schema versioning
def _symbols_columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}


def db_schema_version(conn: sqlite3.Connection) -> int:
    """The schema version an existing store DECLARES. 0 = carries no schema yet.

    An UNVERSIONED store — tables but no `meta.schema_version` — is refused rather
    than assumed to be v1: guessing a version and then running DDL on it is how a
    store gets half-migrated. `event_store.py` takes the same position on its own
    `user_version=0` case.
    """
    if not _table_exists(conn, "symbols"):
        return 0
    raw = _fetch_meta(conn).get("schema_version") if _table_exists(conn, "meta") else None
    if raw is None or not str(raw).isdigit():
        raise Refusal(
            f"this index.db holds a `symbols` table but declares no readable "
            f"meta.schema_version ({raw!r}) — an unversioned store cannot be "
            f"upgraded safely. Move it aside and re-create it with --apply: the DB "
            f"is ADVISORY and fully re-derivable from the index files, and the "
            f"authored annotations replay from {LOG_NAME}.")
    return int(raw)


def _upgrade_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: the live-identity key gains `ordinal` (T-00000121).

    Purely additive, so EVERYTHING is preserved — SYM-IDs, annotations, edges,
    journal, tombstones — and `annotations_log.jsonl` needs no replay. A v1 store
    cannot hold a collision (its own unique index forbade one), so every existing
    row is correct at ordinal 0 and the new index is satisfiable; the resync that
    follows recomputes the ordinals from the files.
    """
    if "ordinal" not in _symbols_columns(conn):
        conn.execute("ALTER TABLE symbols ADD COLUMN ordinal INTEGER NOT NULL DEFAULT 0")
    # The 3-column index MUST go: it is what refuses the homonyms, and it would
    # otherwise survive untouched next to the new one.
    # SAST false positive (repatriated from a consumer repo, T-00000310). An index name is an SQL IDENTIFIER and
    # SQLite binds VALUES only -- `DROP INDEX ?` is a syntax error, so
    # parameterization is impossible. The name is `LEGACY_LIVE_KEY_INDEX`, a
    # module-level string literal that never takes a caller-supplied value.
    # nosemgrep: agents.security.python-sql-injection-string-format
    conn.execute(f"DROP INDEX IF EXISTS {LEGACY_LIVE_KEY_INDEX}")


def _upgrade_v2_to_v3(conn: sqlite3.Connection) -> None:
    """v2 -> v3: the symbols table gains `body_sha` (T-00000377).

    Purely additive, like the rung before it: no key moves, so SYM-IDs,
    annotations, edges, journal and tombstones are all preserved and
    `annotations_log.jsonl` needs no replay. The column lands NULL on every
    existing row — which is the honest state, "this store carries no body hash
    yet" — and the `--resync` that follows fills it from the index files.
    """
    if "body_sha" not in _symbols_columns(conn):
        conn.execute("ALTER TABLE symbols ADD COLUMN body_sha TEXT")


# One rung per version, keyed by the version it upgrades FROM. A rung is DDL/DML
# only; the caller owns the transaction and stamps the new version, so an
# interrupted upgrade leaves the OLD version declared and is simply retried.
# `upgrade_schema` climbs them one at a time, so a v1 store reaches v3 in a
# SINGLE --resync.
SCHEMA_UPGRADES: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _upgrade_v1_to_v2,
    2: _upgrade_v2_to_v3,
}


def upgrade_schema(conn: sqlite3.Connection) -> str | None:
    """Bring an existing store up to `SCHEMA_VERSION`, in place. Returns a note
    naming the upgrade, or None when there was nothing to do.

    Refuses — loudly, writing nothing — on a store from a NEWER kit, and on a
    version with no registered rung. A missing rung is reported rather than
    skipped: a silently un-migrated schema is the worst of the three outcomes,
    because the store then LOOKS current.
    """
    version = db_schema_version(conn)
    if version in (0, SCHEMA_VERSION):
        return None
    if version > SCHEMA_VERSION:
        raise Refusal(
            f"this index.db declares schema v{version} but this kit implements "
            f"v{SCHEMA_VERSION}: a NEWER kit wrote it. Nothing here will read or "
            f"write it — roll the kit forward instead of downgrading the store.")

    rungs: list[tuple[int, Callable[[sqlite3.Connection], None]]] = []
    at = version
    while at < SCHEMA_VERSION:
        rung = SCHEMA_UPGRADES.get(at)
        if rung is None:
            raise Refusal(
                f"no upgrade is registered from schema v{at} to v{SCHEMA_VERSION} — "
                f"this store cannot be upgraded in place. Move it aside and "
                f"re-create it with --apply; the annotations replay from {LOG_NAME}.")
        rungs.append((at, rung))
        at += 1

    conn.execute("BEGIN")
    try:
        for _from, rung in rungs:
            rung(conn)
        conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     ("schema_version", str(SCHEMA_VERSION)))
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return (f"schema upgraded in place v{version} -> v{SCHEMA_VERSION} — SYM-IDs, "
            f"annotations, edges, journal and tombstones preserved, no replay needed")


# --------------------------------------------------------------------- writing
def _fetch_symbols(conn: sqlite3.Connection) -> dict[int, dict]:
    """Every stored symbol, in the exact shape `State.symbols` holds.

    The shape must match key for key: `write_state` compares the two dicts with `==` to decide whether to
    write, so a missing key would make every resync rewrite every row and end the stable-bytes property.

    Reads `ordinal` only when the column is THERE, so this stays callable on a v1 store that has not been
    upgraded yet — `--verify` must be able to report that staleness rather than die of an OperationalError
    on its way to saying so. `body_sha` (v3) sits behind the SAME guard for the SAME reason: an ungarded
    SELECT would turn the v2 -> v3 nudge into an OperationalError raised on the way to printing it.
    """
    has_ordinal = "ordinal" in _symbols_columns(conn)
    ordinal_col = "ordinal" if has_ordinal else "0 AS ordinal"
    has_body = "body_sha" in _symbols_columns(conn)
    body_col = "body_sha" if has_body else "NULL AS body_sha"
    rows = conn.execute(
        'SELECT id, path, name, kind, start, "end" AS end, deleted, generation,'
        f" {ordinal_col}, {body_col} FROM symbols").fetchall()
    return {r["id"]: {"id": r["id"], "path": r["path"], "name": r["name"],
                      "kind": r["kind"], "start": r["start"], "end": r["end"],
                      "deleted": bool(r["deleted"]), "generation": r["generation"],
                      "ordinal": r["ordinal"], "body_sha": r["body_sha"]}
            for r in rows}


def _fetch_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}


def _fetch_annotations(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    rows = conn.execute("SELECT scope, key, purpose, role, owner FROM annotations")
    return {(r["scope"], r["key"]): {"purpose": r["purpose"], "role": r["role"],
                                     "owner": r["owner"]} for r in rows}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?",
                        (name,)).fetchone() is not None


def rebuild_fts(conn: sqlite3.Connection, state: State) -> int:
    """Repopulate `symbols_fts` from scratch. Returns the rows indexed.

    Needed exactly once: when the search index has JUST been created on a DB
    that was migrated by an interpreter without FTS5. The upserts are guarded,
    so an otherwise unchanged resync writes no symbol row and would leave the
    fresh index EMPTY while it exists — and an empty index answers every query
    with "no match", which is indistinguishable from a correct answer. Every
    other path keeps it current row by row, inside `write_state`.
    """
    conn.execute("DELETE FROM symbols_fts")
    indexed = 0
    for sym in state.symbols.values():
        if sym["deleted"]:  # tombstones are data, not something to search for
            continue
        purpose = state.annotations.get(("symbol", str(sym["id"])), {})
        conn.execute("INSERT INTO symbols_fts(rowid, name, path, purpose)"
                     " VALUES(?, ?, ?, ?)",
                     (sym["id"], sym["name"], sym["path"], purpose.get("purpose") or ""))
        indexed += 1
    return indexed


def write_state(conn: sqlite3.Connection, state: State, fts: bool,
                logged: frozenset = frozenset()) -> dict[str, int]:
    """Apply `state` to the DB with GUARDED upserts, inside one transaction.

    Every row is COMPARED before it is written: an unchanged run issues zero
    write statements, so SQLite dirties zero pages and the file's bytes do not
    move — which is what keeps `--resync` free of commit noise (C17).

    `logged` is the set of `(scope, key)` the replayed annotations journal names: their `annotations` row is
    left to `apply_log`, which arbitrates it field by field (the files' value wins, else the journal's
    last). Writing the files' row here first made a MIXED key — `owner` in the files, `role` only in the
    journal — ping-pong on every `--resync`: this function wrote `role` NULL, `apply_log` wrote it back, and
    "unchanged" was never reached (critic-opus T1, T-00000668).

    Returns a per-table count of the rows actually written.
    """
    written = {"meta": 0, "symbols": 0, "edges": 0, "modules": 0,
               "annotations": 0, "journal": 0}

    current_meta = _fetch_meta(conn)
    previous = current_meta.get("watermark")
    if previous is not None and str(previous).isdigit() and int(previous) > state.watermark:
        raise Refusal(
            f"refusing to lower the SYM-ID watermark: DB holds {previous}, the "
            f"files bound to {state.watermark} (L-022 — the bound is monotone; "
            f"restore INDEX_DELTA.json's max_sym_id before resyncing)")

    desired_meta = {
        "schema_version": str(SCHEMA_VERSION),
        META_BUILT_AT_SHA: state.generation or "",
        "watermark": str(state.watermark),
    }
    for key, value in desired_meta.items():
        if current_meta.get(key) == value:
            continue
        conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, value))
        written["meta"] += 1

    # symbols — never deleted, only upserted (tombstones are data, not garbage).
    #
    # THE FUSION, AND WHY IT IS HERE RATHER THAN IN `read_state` (↯ C16/C29).
    # NOT KNOWING A BODY HASH DOES NOT AUTHORISE ERASING ONE. When the lateral
    # map is unusable — absent, or stamped with another generation — `read_state`
    # carries `body_sha = None` for every symbol while the store may hold real
    # values. Left alone, `before == sym` would then be false on EVERY row and a
    # resync would rewrite the whole store, destroying the stable-bytes property
    # this function's docstring exists to hold. `read_state` cannot do this: it
    # takes no connection and never sees the stored value.
    #
    # `.get()`, not `[...]`: a symbol absent from the store is the NORMAL case
    # under --apply and for any new symbol under --resync, and indexing directly
    # would raise KeyError on it.
    current_symbols = _fetch_symbols(conn)
    lateral_unusable = state.bodies_note is not None
    for sym in state.symbols.values():
        before = current_symbols.get(sym["id"])
        if lateral_unusable and before is not None:
            sym = {**sym, "body_sha": before["body_sha"]}
        if before == sym:
            continue
        try:
            conn.execute(
                "INSERT INTO symbols(id, path, name, kind, start, \"end\", deleted,"
                " generation, ordinal, body_sha) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET path = excluded.path,"
                " name = excluded.name, kind = excluded.kind, start = excluded.start,"
                " \"end\" = excluded.\"end\", deleted = excluded.deleted,"
                " generation = excluded.generation, ordinal = excluded.ordinal,"
                " body_sha = excluded.body_sha",
                (sym["id"], sym["path"], sym["name"], sym["kind"], sym["start"],
                 sym["end"], int(sym["deleted"]), sym["generation"], sym["ordinal"],
                 sym["body_sha"]))
        except sqlite3.IntegrityError as exc:
            # A BACKSTOP, not the homonym guard: `assign_ordinals` already numbered
            # every legitimate group and refused the irreducible case during the
            # reads. Reaching here means the ordinals and this index disagree —
            # a bug in this module, or a store still carrying the v1 index.
            raise Refusal(
                f"the live-identity index rejected {bi.sid(sym['id'])} "
                f"({sym['path']} {sym['name']} {sym['kind']} ordinal "
                f"{sym['ordinal']}): {exc}\n  ordinals were assigned before any "
                f"write, so this is not a legitimate pair of homonyms. If this "
                f"store predates schema v{SCHEMA_VERSION}, --resync upgrades it; "
                f"otherwise report it — nothing was committed.") from exc
        written["symbols"] += 1
        if fts:
            conn.execute("DELETE FROM symbols_fts WHERE rowid = ?", (sym["id"],))
            if not sym["deleted"]:
                purpose = state.annotations.get(("symbol", str(sym["id"])), {})
                conn.execute(
                    "INSERT INTO symbols_fts(rowid, name, path, purpose)"
                    " VALUES(?, ?, ?, ?)",
                    (sym["id"], sym["name"], sym["path"], purpose.get("purpose") or ""))

    # edges — derived, so a stale one is removed; both directions diffed first.
    current_edges = {(r["src_id"], r["dst_id"])
                     for r in conn.execute("SELECT src_id, dst_id FROM edges")}
    for src, dst in sorted(state.edges - current_edges):
        conn.execute("INSERT INTO edges(src_id, dst_id) VALUES(?, ?)", (src, dst))
        written["edges"] += 1
    for src, dst in sorted(current_edges - state.edges):
        if src in state.symbols:  # only prune edges of symbols the files still describe
            conn.execute("DELETE FROM edges WHERE src_id = ? AND dst_id = ?", (src, dst))
            written["edges"] += 1

    # modules — a mirror of the generated table; stale rows go when the file is there.
    if state.modules_present:
        current_modules = {r["path"]: (r["role"], r["depends_on"], r["owner"])
                           for r in conn.execute(
                               "SELECT path, role, depends_on, owner FROM modules")}
        desired_modules = {m.path: (m.role, m.depends_on, m.owner) for m in state.modules}
        for path, values in desired_modules.items():
            if current_modules.get(path) == values:
                continue
            conn.execute(
                "INSERT INTO modules(path, role, depends_on, owner) VALUES(?, ?, ?, ?)"
                " ON CONFLICT(path) DO UPDATE SET role = excluded.role,"
                " depends_on = excluded.depends_on, owner = excluded.owner",
                (path, *values))
            written["modules"] += 1
        for path in sorted(set(current_modules) - set(desired_modules)):
            conn.execute("DELETE FROM modules WHERE path = ?", (path,))
            written["modules"] += 1

    # annotations — AUTHORED content: upserted, never deleted. A purpose that
    # disappears from a regenerated file does not erase what someone wrote.
    current_annotations = _fetch_annotations(conn)
    for (scope, key), values in state.annotations.items():
        if (scope, key) in logged:
            continue  # apply_log arbitre (file wins per field, else the log's last)
        before = current_annotations.get((scope, key))
        after = {"purpose": values.get("purpose"), "role": values.get("role"),
                 "owner": values.get("owner")}
        if before == after:
            continue
        conn.execute(
            "INSERT INTO annotations(scope, key, purpose, role, owner)"
            " VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(scope, key) DO UPDATE SET purpose = excluded.purpose,"
            " role = excluded.role, owner = excluded.owner",
            (scope, key, after["purpose"], after["role"], after["owner"]))
        written["annotations"] += 1

    # journal — derived from INDEX_DELTA.json, replaced in place.
    current_journal = {r["seq"]: (r["at_sha"], r["kind"], r["payload"])
                       for r in conn.execute(
                           "SELECT seq, at_sha, kind, payload FROM journal")}
    desired_journal = {seq: (sha, kind, payload)
                       for seq, sha, kind, payload in state.journal}
    for seq, values in desired_journal.items():
        if current_journal.get(seq) == values:
            continue
        conn.execute(
            "INSERT INTO journal(seq, at_sha, kind, payload) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(seq) DO UPDATE SET at_sha = excluded.at_sha,"
            " kind = excluded.kind, payload = excluded.payload", (seq, *values))
        written["journal"] += 1
    if state.journal:
        for seq in sorted(set(current_journal) - set(desired_journal)):
            conn.execute("DELETE FROM journal WHERE seq = ?", (seq,))
            written["journal"] += 1

    return written


# ------------------------------------------------------- annotations log (jsonl)
def read_log(path: Path) -> list[dict]:
    """Every well-formed line of the append-only annotations log, in order."""
    raw = bi._read(path)
    if raw is None:
        return []
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("scope") and entry.get("field"):
            out.append(entry)
    return out


def replay_log(entries: Iterable[dict]) -> dict[tuple[str, str], dict]:
    """Fold the log into the `annotations` table it describes — last write wins."""
    out: dict[tuple[str, str], dict] = {}
    for entry in entries:
        key = (str(entry.get("scope")), str(entry.get("key")))
        row = out.setdefault(key, {"purpose": None, "role": None, "owner": None})
        field_name = str(entry.get("field"))
        if field_name in row:
            row[field_name] = entry.get("value")
    return out


def append_log(path: Path, state: State) -> int:
    """Append the annotations the log does not already end on. Guarded: an
    unchanged resync appends nothing, so the file stays byte-identical too."""
    known = replay_log(read_log(path))
    lines: list[str] = []
    for (scope, key), values in sorted(state.annotations.items()):
        before = known.get((scope, key), {"purpose": None, "role": None, "owner": None})
        for field_name in ("purpose", "role", "owner"):
            value = values.get(field_name)
            if value is None or before.get(field_name) == value:
                continue
            lines.append(json.dumps(
                {"scope": scope, "key": key, "field": field_name, "value": value,
                 "at_sha": state.generation or ""},
                sort_keys=True, ensure_ascii=False))
    if not lines:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(lines)


ANNOTATION_SCOPES = ("symbol", "module")


def apply_log(conn: sqlite3.Connection, replayed: dict[tuple[str, str], dict],
              files: dict[tuple[str, str], dict] | None = None,
              overridden: list | None = None) -> tuple[int, int]:
    """Replay the FOLDED annotations log (`replay_log(read_log(...))`) INTO the store.
    `files` is `State.annotations` — what the index FILES carry. Returns `(written, skipped)`. When
    `overridden` is a list, one entry `(scope, key) <field> <before> -> <merged>` is appended for every key
    where a stored NON-NULL field is replaced by the LOG's value (a retraction included): after a `git pull
    --no-rebase`, `merge=union` puts UPSTREAM's lines last, so the log's last value can overwrite this
    machine's in silence — `run_resync` names it instead (critic-opus T2 / critic-fable F2). A field filled
    from NULL is not a replacement, and a field the FILES carry is the files' value, not the journal's:
    neither is collected.

    WHY (T-00000668): the store is machine state now, dropped and rebuilt at will, and `write_state` reads
    annotations from the FILES only — an annotation posed by `symbols.py annotate` that no file carries
    would be LOST at the first `--apply` on a fresh machine. The log is the versioned record; this is the
    one place the JOURNAL -> STORE direction exists.

    THE RULE, per field of every key the log names: A FIELD THE FILES CARRY WINS; OTHERWISE THE LOG'S LAST
    VALUE — a RETRACTION INCLUDED. The store's own value is NOT a source: the log is shared through git, the
    store is per machine, so "store first" (the rule this replaced, critic-opus F1 / exec-critic, decision
    S-00002394) kept P1 on a machine after another one annotated P2, and never applied a `retire` made
    elsewhere. A key whose logged fields all end NULL is a retraction: its NULL row is WRITTEN, because
    `retire` KEEPS that row and `verify` compares the folded log to the table key by key — without it a
    fresh machine failed `--verify` forever. MUST run AFTER `write_state`, inside the same transaction:
    `write_state` upserts a module's `role`/`owner` INCLUDING NULL (a placeholder cell), so running before
    it would be undone. When a file value differs from the log's last one, `append_log` — run after the
    COMMIT — appends the file's value, so the log converges on it and `verify` agrees.

    GUARDED like `write_state`: the stored row is read first and the UPSERT runs only when the merge differs
    from it, so a second call on the same `replayed` writes nothing. A scope outside `ANNOTATION_SCOPES` is
    SKIPPED and counted — never raised, never written. A symbol purpose written here also refreshes its
    `symbols_fts` row, as `symbols.py::write_annotation` does, so the replayed annotation is searchable
    until the next `--resync` that moves the symbol.
    """
    stored = _fetch_annotations(conn)
    fts = _table_exists(conn, "symbols_fts")
    written = skipped = 0
    for (scope, key), values in sorted(replayed.items()):
        if scope not in ANNOTATION_SCOPES:
            skipped += 1
            continue
        before = stored.get((scope, key))
        base = before or {"purpose": None, "role": None, "owner": None}
        file_row = (files or {}).get((scope, key), {})
        merged = {name: (file_row.get(name) if file_row.get(name) is not None
                         else values.get(name))
                  for name in ("purpose", "role", "owner")}
        if merged == before:
            continue
        if overridden is not None:
            replaced = [f"{name} {_short(base[name])} -> {_short(merged[name])}"
                        for name in ("purpose", "role", "owner")
                        if base[name] is not None and merged[name] != base[name]
                        and file_row.get(name) is None]
            if replaced:
                overridden.append(f"({scope}, {key}) " + ", ".join(replaced))
        conn.execute(
            "INSERT INTO annotations(scope, key, purpose, role, owner)"
            " VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(scope, key) DO UPDATE SET purpose = excluded.purpose,"
            " role = excluded.role, owner = excluded.owner",
            (scope, key, merged["purpose"], merged["role"], merged["owner"]))
        written += 1
        if (fts and scope == "symbol" and str(key).isdigit()
                and merged["purpose"] != base.get("purpose")):
            sym = conn.execute("SELECT id, name, path, deleted FROM symbols WHERE id = ?",
                               (int(key),)).fetchone()
            if sym is not None and not sym["deleted"]:
                conn.execute("DELETE FROM symbols_fts WHERE rowid = ?", (int(key),))
                conn.execute("INSERT INTO symbols_fts(rowid, name, path, purpose)"
                             " VALUES(?, ?, ?, ?)",
                             (int(key), sym["name"], sym["path"], merged["purpose"] or ""))
    return written, skipped


def _short(value: str | None, width: int = 60) -> str:
    """`repr` of an annotation value, bounded — a purpose is ≤10 words by
    contract, but the journal is text anyone can write."""
    text = repr(value)
    return text if len(text) <= width else text[:width - 1] + "…"


OVERRIDDEN_SHOWN = 10


def _overridden_note(overridden: Sequence[str]) -> str | None:
    """The `--resync` NOTE naming what the journal's last value REPLACED in this
    store — the first `OVERRIDDEN_SHOWN`, then the count of the rest (a bound
    applied is a bound said)."""
    if not overridden:
        return None
    shown = "; ".join(overridden[:OVERRIDDEN_SHOWN])
    rest = len(overridden) - OVERRIDDEN_SHOWN
    more = f"; … {rest} more" if rest > 0 else ""
    return (f"replaced by the journal's last value: {shown}{more} — on a same key "
            f"the LAST line of {LOG_NAME} wins, and after `git pull --no-rebase` "
            f"that is upstream's (`.gitattributes`)")


def _skipped_note(skipped: int) -> str | None:
    if not skipped:
        return None
    return (f"{skipped} annotation(s) of the log carry a scope outside "
            f"{'/'.join(ANNOTATION_SCOPES)} — skipped, never written")


# --------------------------------------------------------------------- staleness
def _is_behind(built: str | None, stamps: set[str]) -> bool:
    """THE freshness predicate, in one place: is `built` another generation than the files' `stamps`?

    Two silences are deliberate and both mean "no verdict", never "fresh": a DB carrying no
    `meta.built_at_sha` at all (`built is None`), and files carrying no stamp to compare against (empty
    `stamps`). A verdict invented from missing data is worse than no verdict — it would fire at every Stop.
    """
    if built is None:
        return False
    return bool(stamps) and {built} != stamps


def staleness(state: State, meta: dict[str, str]) -> str | None:
    """`DB STALE …` when the DB's generation is not the files' generation."""
    built = meta.get(META_BUILT_AT_SHA)
    stamps = state.stamps or ({state.generation} if state.generation else set())
    if _is_behind(built, stamps):
        return (f"{STALE_MARKER} (DB {META_BUILT_AT_SHA} {built!r}, files stamped "
                f"{', '.join(sorted(stamps))})")
    return None


def read_db_generation(root: Path) -> str | None:
    """The index generation `index.db` was built from, or None when the store has
    no answer to give. READ-ONLY, and NON-CREATING BY CONSTRUCTION.

    `sqlite3.connect()` on a missing path CREATES the file, and a 0-byte `index.db` appearing in a repo that
    never had one would be a WRITE performed by a read-only probe. Two independent guards, because this is
    called from `build_index.py --stale-check`:
      * `exists()` is tested BEFORE any connection is opened;
      * the connection is a `mode=ro` URI, which cannot create a database.

    Every failure answers None — no sqlite3 URI support, an unreadable or corrupt file, no `meta` table
    (`sqlite3.OperationalError`), a NULL value, or the store's location cannot be resolved (`Refusal` from
    `db_path`: `cadre.paths` unavailable, or a root that resolves elsewhere — T-00000668). Silence, not a
    guess: the caller must be able to stay quiet about the DB.
    """
    conn = None
    try:
        target = db_path(root)
        if not target.exists():
            return None
        conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
        row = conn.execute("SELECT value FROM meta WHERE key = ?",
                           (META_BUILT_AT_SHA,)).fetchone()
    except (sqlite3.Error, OSError, ValueError, Refusal):
        return None
    finally:
        if conn is not None:
            conn.close()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def db_generation_behind(root: Path, files_generation: str | None
                         ) -> tuple[str, str] | None:
    """`(db_generation, files_generation)` when the machine store was built from a
    DIFFERENT index generation than the index FILES, else None.

    The comparison lives HERE, on `_is_behind`, the same predicate `staleness()`
    uses — `build_index.py --stale-check` consumes this and never reads `meta`
    itself, so the probe's verdict and `--check` / `--verify` can never disagree.
    Writes nothing, creates nothing, raises nothing worth catching upstream.
    """
    built = read_db_generation(root)
    stamps = {files_generation} if files_generation else set()
    if _is_behind(built, stamps):
        return str(built), str(files_generation)
    return None


# ------------------------------------------------------------------------ verify
def verify(conn: sqlite3.Connection, state: State, log: Path) -> list[str]:
    """Round-trip the files against the DB. Returns one line per divergence."""
    problems: list[str] = []
    meta = _fetch_meta(conn)

    if meta.get("schema_version") != str(SCHEMA_VERSION):
        problems.append(f"meta.schema_version is {meta.get('schema_version')!r}, "
                        f"expected {SCHEMA_VERSION} — run --resync to upgrade the "
                        f"store in place (SYM-IDs and annotations are preserved)")
    # The declared version is a claim; the INDEX is the fact. Checked separately so
    # a store that says v2 while still carrying the v1 key cannot pass as current.
    if _table_exists(conn, LEGACY_LIVE_KEY_INDEX):
        problems.append(f"the v1 identity index {LEGACY_LIVE_KEY_INDEX} is still "
                        f"present — it refuses the homonyms a file may legitimately "
                        f"carry; run --resync to drop it")
    if not _table_exists(conn, LIVE_KEY_INDEX):
        problems.append(f"the live-identity index {LIVE_KEY_INDEX} is missing — "
                        f"run --resync")
    stale = staleness(state, meta)
    if stale:
        problems.append(stale)
    if meta.get("watermark") != str(state.watermark):
        problems.append(f"meta.watermark is {meta.get('watermark')!r}, files bound "
                        f"to {state.watermark}")

    db_symbols = _fetch_symbols(conn)
    db_by_key = {(s["path"], s["name"], s["kind"], s["ordinal"]): s["id"]
                 for s in db_symbols.values() if not s["deleted"]}
    file_by_key = state.by_key()
    for key, sym_id in sorted(file_by_key.items(), key=lambda kv: kv[1]):
        if key not in db_by_key:
            problems.append(f"SYM-{sym_id} {key_label(key)} absent from the DB")
        elif db_by_key[key] != sym_id:
            problems.append(f"identity moved for {key_label(key)} — files say "
                            f"SYM-{sym_id}, DB says SYM-{db_by_key[key]}")
    for key, sym_id in sorted(db_by_key.items(), key=lambda kv: kv[1]):
        if key not in file_by_key:
            problems.append(f"SYM-{sym_id} {key_label(key)} is in the DB and not "
                            f"in the files")

    # BODY HASHES, FIELD BY FIELD — and this loop is the whole reason `--verify`
    # can fail on a v3 store (↯ C14). Everything above compares identity, counts
    # and annotations; NOTHING compared a symbol FIELD, so without these lines a
    # store whose `body_sha` column was entirely NULL would come back green — a
    # criterion that cannot blush. The pairing is by SYM-ID over the LIVING; a
    # tombstone carries no hash on either side.
    #
    # ONE divergence is tolerated, and it is NAMED rather than swallowed: when
    # `state.bodies_note` is set the files simply do not say what the hashes are,
    # so the column is not comparable and `read_state` has already pushed the
    # reason into `state.notes`, which every mode prints.
    if state.bodies_note is None:
        for sym_id in sorted(s["id"] for s in state.live):
            stored = db_symbols.get(sym_id)
            if stored is None or stored["deleted"]:
                continue  # already reported by the identity round-trip above
            want = state.symbols[sym_id]["body_sha"]
            if stored["body_sha"] != want:
                problems.append(
                    f"body_sha diverges for {bi.sid(sym_id)}: files say "
                    f"{want or 'none'}, DB says {stored['body_sha'] or 'none'} — "
                    f"run --resync")

    db_tombs = sum(1 for s in db_symbols.values() if s["deleted"])
    if db_tombs != len(state.tombstones):
        problems.append(f"tombstones: {len(state.tombstones)} in the files, "
                        f"{db_tombs} in the DB")

    replayed = replay_log(read_log(log))
    stored = _fetch_annotations(conn)
    for key in sorted(set(replayed) | set(stored)):
        if replayed.get(key) != stored.get(key):
            problems.append(f"annotation ({key[0]}, {key[1]}) does not replay: log "
                            f"{replayed.get(key)!r} vs DB {stored.get(key)!r}")
    return problems


# ------------------------------------------------------------------- reporting
def summarize(state: State, fts: bool, counts: dict[str, int] | None = None) -> list[str]:
    symbol_annotations = sum(1 for scope, _ in state.annotations if scope == "symbol")
    module_annotations = len(state.annotations) - symbol_annotations
    lines = [
        f"  symbols      {len(state.symbols):>6}  (live {len(state.live)} · "
        f"tombstones {len(state.tombstones)})",
        f"  edges        {len(state.edges):>6}",
        f"  modules      {len(state.modules):>6}",
        f"  annotations  {len(state.annotations):>6}  (symbol {symbol_annotations} · "
        f"module {module_annotations})",
        f"  journal      {len(state.journal):>6}",
        # Printed only when there ARE homonyms: a disambiguation nobody can see is
        # a silent behaviour, and this is the line that would have made the
        # consumer's 5 groups / 16 symbols legible before the refusal.
        *([f"  homonyms     {len(state.homonyms):>6}  identities carrying "
           f"{sum(state.homonyms.values())} symbols, separated by ordinal"]
          if state.homonyms else []),
        f"  watermark    {state.watermark:>6}  (INDEX_DELTA bound "
        f"{state.delta_bound if state.delta_bound is not None else '—'} · "
        f"max id seen {state.max_id_seen})",
        f"  generation   {state.generation or '—'}",
        f"  fts5         {'available' if fts else 'ABSENT — degraded, no symbols_fts'}",
    ]
    if counts:
        lines.append("  rows written " + " · ".join(
            f"{table} {n}" for table, n in sorted(counts.items())))
    return lines


def next_steps(root: Path, target: Path | None = None) -> list[str]:
    """What to do next. NOTHING about committing the store: since T-00000668 it is
    MACHINE state outside the repository — only the annotations log is versioned."""
    rel_log = (Path(bi.STATE_INDEX_REL) / LOG_NAME).as_posix()
    where = target if target is not None else "cadre.paths.index_db()"
    return [
        "NEXT:",
        f"  store MACHINE hors dépôt ({where}) : rien à committer ; "
        f"committer `{rel_log}` s'il a bougé",
        # "ADVISORY in v1" used to sit here; it names the ARC's v1 and now prints
        # one line under "schema v1 in the store", where it read as the schema.
        "  the DB is ADVISORY — after any build_index.py run: --resync.",
    ]


# ------------------------------------------------------------------------- modes
def _atomic_create(target: Path, build: Any) -> None:
    """Build the DB in a sibling `.part` and move it in, the builder's discipline."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._tmp_" + DB_NAME,
                               suffix=".part")
    os.close(fd)
    try:
        conn = connect(Path(tmp))
        try:
            build(conn)
        finally:
            conn.close()
        bi._replace_with_retry(tmp, str(target))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_check(root: Path, state: State) -> int:
    print(f"migrate_index_to_db: --check (nothing is written) — root {root}")
    print("\n".join(summarize(state, fts_probe())))

    target = db_path(root)
    if target.exists():
        conn = connect(target)
        try:
            stale = staleness(state, _fetch_meta(conn))
            version = db_schema_version(conn)
        finally:
            conn.close()
        print(f"  db           present at {target}")
        print(f"  schema       v{version} in the store, v{SCHEMA_VERSION} in this kit"
              + ("" if version == SCHEMA_VERSION
                 else " — --resync would upgrade it IN PLACE, preserving SYM-IDs, "
                      "annotations, edges and journal"))
        if stale:
            print(f"  {stale}")
    else:
        print(f"  db           absent — --apply would create {target}")
    for note in [*state.notes, legacy_note(root, target)]:
        if note:
            print(f"  NOTE: {note}")
    print("\n".join(next_steps(root, target)))
    return 0


def run_apply(root: Path, state: State) -> int:
    target = db_path(root)
    if target.exists():
        raise Refusal(f"{target} already exists — use --resync to bring it up to "
                      f"date (--apply only ever creates)")
    result: dict[str, Any] = {}
    # Folded BEFORE the store is built, and before `append_log` below adds the
    # files' own values to it: what is replayed is what the log held on entry.
    replayed = replay_log(read_log(log_path(root)))

    def build(conn: sqlite3.Connection) -> None:
        fts = ensure_schema(conn)
        conn.execute("BEGIN")
        try:
            counts = write_state(conn, state, fts, frozenset(replayed))
            # AFTER `write_state`, never before (it upserts module role/owner
            # INCLUDING NULL), and inside the same transaction (T-00000668).
            replayed_rows, result["skipped"] = apply_log(conn, replayed,
                                                         state.annotations)
            counts["annotations"] += replayed_rows
            result["counts"] = counts
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        result["fts"] = fts

    _atomic_create(target, build)
    appended = append_log(log_path(root), state)
    print(f"migrate_index_to_db: --apply — created {target}")
    print("\n".join(summarize(state, result["fts"], result["counts"])))
    print(f"  log          {appended:>6}  lines appended to {LOG_NAME}")
    for note in [*state.notes, _skipped_note(result["skipped"]),
                 legacy_note(root, target)]:
        if note:
            print(f"  NOTE: {note}")
    print("\n".join(next_steps(root, target)))
    return 0


def run_resync(root: Path, state: State) -> int:
    """Bring an existing store in line with the files, then replay the journal.

    BOUND, written rather than discovered (critic-opus T6, T-00000668): the journal is folded ONCE, on
    entry, and `symbols.py annotate` writes the store then appends to the journal outside this transaction.
    An annotation written WHILE a `--resync` runs can therefore be replaced by the OLD value (the fold
    predates its journal line); the next `--resync` restores it, since that line is then the journal's last.
    The write order is deliberately not changed.
    """
    target = db_path(root)
    if not target.exists():
        raise Refusal(f"{target} does not exist — run --apply first")
    replayed = replay_log(read_log(log_path(root)))
    conn = connect(target)
    reindexed = 0
    skipped = 0
    overridden: list[str] = []
    try:
        # BEFORE `ensure_schema`, whose statements are all `IF NOT EXISTS` and
        # would leave an older shape standing. This is the ONE place an existing
        # store changes version, and it commits on its own.
        upgrade_note = upgrade_schema(conn)
        # `had_fts` before `ensure_schema`, which is what CREATES the table when
        # the DB was migrated by an interpreter that had no FTS5.
        had_fts = _table_exists(conn, "symbols_fts")
        fts = ensure_schema(conn)
        conn.execute("BEGIN")
        try:
            counts = write_state(conn, state, fts, frozenset(replayed))
            if fts and not had_fts:
                reindexed = rebuild_fts(conn, state)
            # AFTER `write_state` (and after a fresh `rebuild_fts`, which reads the
            # files' purposes only), BEFORE `COMMIT` — T-00000668.
            replayed_rows, skipped = apply_log(conn, replayed, state.annotations,
                                               overridden)
            counts["annotations"] += replayed_rows
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()
    appended = append_log(log_path(root), state)
    total = sum(counts.values())
    print(f"migrate_index_to_db: --resync — {target}")
    print("\n".join(summarize(state, fts, counts)))
    print(f"  log          {appended:>6}  lines appended to {LOG_NAME}")
    if reindexed:
        print(f"  fts          {reindexed:>6}  rows indexed — symbols_fts was created "
              f"by this run (the DB predates FTS5 on this interpreter)")
    if upgrade_note:
        print(f"  MIGRATION: {upgrade_note}")
    # An upgrade rewrote the schema, so the bytes DID move — claiming "unchanged"
    # there would be a false anchor, whatever the row counts say.
    if total == 0 and appended == 0 and not reindexed and not upgrade_note:
        print("  unchanged — zero rows written, the file's bytes did not move")
    for note in [*state.notes, _skipped_note(skipped), _overridden_note(overridden),
                 legacy_note(root, target)]:
        if note:
            print(f"  NOTE: {note}")
    print("\n".join(next_steps(root, target)))
    return 0


def run_verify(root: Path, state: State) -> int:
    target = db_path(root)
    if not target.exists():
        raise Refusal(f"{target} does not exist — nothing to verify; run --apply")
    conn = connect(target)
    try:
        problems = verify(conn, state, log_path(root))
        fts = _table_exists(conn, "symbols_fts")
    finally:
        conn.close()
    print(f"migrate_index_to_db: --verify — {target}")
    print("\n".join(summarize(state, fts)))
    for note in state.notes:
        print(f"  NOTE: {note}")
    if problems:
        print(f"VERIFY FAILED — {len(problems)} divergence(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("  verify       OK — identity, tombstones, watermark, annotations and "
          "body_sha agree")
    return 0


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_index_to_db.py",
        description="Migrate the file index into its SQLite store — machine state "
                    "outside the repository, cadre.paths.index_db() (T-00000668).")
    parser.add_argument("--root", help="project root (default: the git top level)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="plan only, write nothing")
    mode.add_argument("--apply", action="store_true", help="create the DB atomically")
    mode.add_argument("--verify", action="store_true", help="round-trip files <-> DB")
    mode.add_argument("--resync", action="store_true", help="idempotent re-run")
    args = parser.parse_args(argv)

    # Measured on this kit's own Windows box: the summary carries `—` and `·`
    # (the builder's own header vocabulary), and a cp1252 pipe would raise
    # UnicodeEncodeError on them — a migration that dies while PRINTING its
    # result is absurd. Degrade the characters, never the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, OSError, ValueError):
            pass

    root = repo_root(args.root)
    try:
        state = read_state(root)
        if args.check:
            return run_check(root, state)
        if args.apply:
            return run_apply(root, state)
        if args.resync:
            return run_resync(root, state)
        return run_verify(root, state)
    except Refusal as exc:
        print(f"migrate_index_to_db: REFUSED — {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        # critic-opus T4: the JOURNAL is written by `append_log`, AFTER the store's
        # COMMIT (`--apply` and `--resync` alike), and it is the only OSError that
        # can name it — reads go through `bi._read`, which swallows OSError. So
        # this is not a refusal: the store moved, the journal did not, and the
        # remedy is the journal's mode, not the state partition's.
        if (exc.filename is not None
                and os.path.abspath(exc.filename) == os.path.abspath(log_path(root))):
            print(f"migrate_index_to_db: FAILED AFTER COMMIT — {type(exc).__name__}: "
                  f"{exc}. The store WAS updated; make {log_path(root)} writable, "
                  f"then --resync appends the missing lines.", file=sys.stderr)
            return 1
        # critic-opus F3: an unwritable machine partition (`_atomic_create`'s
        # `mkdir`, the `.part` file) used to escape as a 40-line traceback. The
        # store lives OUTSIDE the repository since T-00000668, so the remedy is
        # an environment variable, and the refusal names it.
        print(f"migrate_index_to_db: REFUSED — {type(exc).__name__}: {exc}. The "
              f"machine store lives under the state partition — $CADRE_STATE_DIR, "
              f"else $XDG_STATE_HOME/cadre, else ~/.local/state/cadre: make it "
              f"writable, or point CADRE_STATE_DIR at a writable directory.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
