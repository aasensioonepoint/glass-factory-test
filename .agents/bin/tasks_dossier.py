# tasks_dossier.py — PARTIE de `tasks.py` (T-00001009, BK-416, E-26) : le board en UN FICHIER PAR TÂCHE —
# `board/tasks/<id>.json` et `board/epics/<id>.json` — sa forme (`store_form`), sa lecture et son écriture (appelées
# par `load` / `save` de tasks_stockage.py), sa migration (`migrate_store`) et la lecture BRUTE du pont V3
# (`lire_board_brut`). Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`, jamais importée seule :
# ses noms libres viennent de la façade et des parties amont, lus À L'APPEL seulement, aucun à sa définition
# (test_tasks_decoupe.py (h)).
#
# THE FOLDER FORM. The home is the decision S-01M4N1G4VXD01A3W54Y9FR9856 and the shape is the contract of T-00001012's
# readers (S-01M4N2DK1EW4QWWNB3W6N5BZGM): a FLAT folder per collection, one `<stored id>.json` per record (`T-012`
# stays `T-012.json`), dot names ignored. NO ROOT KEY: the link operation ↔ task lives in the `sync_operations` of each
# task record (S-01M4JN56JEQ0XS97K38CDWBTW6) and `sync_correlations` is their projection, rebuilt in memory at every
# `load`, never written on its own. EVERY id that leaves the board gets a TOMBSTONE (`record: null`, its keys inside,
# `[]` without any — retention decision S-01M4N5YHS77KST2N2FBXX2GEBT); nothing here ever removes a record file: the
# compaction, after a configurable delay, belongs to the archive-and-compaction task, and `board/archive/`,
# `board/tombes.jsonl` and `board/retention.json` are RESERVED to it — never read by `load`, never counted by
# `store_form`. THE WRITE is two-step around ONE point of validation, the lot itself (angle mort 1 (a)): one local lot
# `{cible, forme: "dossier", enregistrements, intents}`, created exclusively and fsync'ed, validated by the sha256 of
# its own content — then each record published from a temp under `.agents/state/local/` (never under `board/`), the
# new O2 intents too, the lot removed LAST. A crash leaves at most that lot: the next save / claim / migration applies
# it again (idempotent), and every reader overlays it meanwhile; a lot that does not validate is quarantined, never
# applied. BOUNDS, named: a `git restore` of the whole folder resurrects without a trace, as of a monolith; the shell
# readers (hooks) read without lots; the real board is migrated by the switch-over task only — no production caller
# and no CLI verb call `migrate_store` (parity with T-1010); reading a migrated board costs 10 to 70 times the monolith
# (M2, no cache); Windows' folder rename (`migrate_store`) is not measured.

from __future__ import annotations

_COLLECTIONS_BOARD = ("tasks", "epics")


def board_dir(root: str | os.PathLike[str]) -> Path:
    """The board folder `.agents/state/board/`: `TASKS.json`, or the record folders `tasks/` and `epics/`."""
    return Path(root) / STORE_REL


def _refus_liens(root: str | os.PathLike[str], lots: bool = False) -> None:
    """A record folder (`board/tasks/`, `board/epics/`) or the VERSIONED O2 intent folder (`board/sync_outbox/`, M2 of
    T-01M4MC28CAKFE8YZ2W4WN7DV2C: a link there arrives by `git pull`) — and, before a write (``lots``), the local lots
    and quarantine folders — that is a SYMBOLIC LINK is REFUSED (security review of T-00001009): `O_NOFOLLOW` guards the
    LAST component only, so a folder versioned as a link would be traversed, read from and WRITTEN to outside the board.
    Nothing read, nothing written; the remedy is a real folder in its place. Bounds: a PARENT folder that is a link is
    still traversed; a Windows junction is not seen by `os.path.islink` before Python 3.12 (not measured)."""
    dossiers = [board_dir(root) / c for c in _COLLECTIONS_BOARD] + [_dossier_outbox(root)]
    if lots:
        dossiers += [_dossier_lots(root), _dossier_quarantaine(root)]
    for dossier in dossiers:
        if os.path.islink(dossier):
            raise BoardError(f"{dossier} is a symbolic link — refused, nothing read or written: put a real folder in "
                             "its place")


def store_form(root: str | os.PathLike[str]) -> str:
    """``absent`` | ``monolithe`` | ``dossier`` | ``les deux`` — THE one definition of a present form (parity with
    `ledger.store_form`, T-00001010): the monolith iff `TASKS.json` exists; the folder iff ONE conforming
    `<record id>.json` exists under `board/tasks/` or `board/epics/` — a dot name (an atomic write's temp) or any other
    name does not count, and nothing else under `board/` is looked at. A record folder, or the O2 intent folder, that
    is a symbolic link is REFUSED (`_refus_liens`) — at the head of every `load` and `save`, of both forms."""
    _refus_liens(root)
    present = False
    for collection in _COLLECTIONS_BOARD:
        sous = board_dir(root) / collection
        if sous.is_dir() and any(not p.name.startswith(".") and p.name.endswith(".json")
                                 and _refus_id_enregistrement(p.name[: -len(".json")]) is None for p in sous.iterdir()):
            present = True
            break
    formes = {(True, True): "les deux", (True, False): "monolithe", (False, True): "dossier"}
    return formes.get((store_path(root).exists(), present), "absent")


def _signature_dossier(root: str | os.PathLike[str]) -> tuple[Any, ...]:
    """What a concurrent save changes, sampled before and after a lock-free read: the names of the local lots, and
    the mtime of each record folder (an `os.replace` into a folder updates it — a whole save between the two samples,
    its lot already gone, still shows)."""
    lots = _dossier_lots(root)
    dates: list[int | None] = []
    for collection in _COLLECTIONS_BOARD:
        try:
            dates.append(os.stat(board_dir(root) / collection).st_mtime_ns)
        except OSError:
            dates.append(None)
    return (tuple(sorted(p.name for p in lots.iterdir())) if lots.is_dir() else (), tuple(dates))


def _surcouche_lots(fichiers: dict[str, bytes], lots: list[tuple[Path, dict[str, Any] | None]]) -> dict[str, bytes]:
    """The record bytes with every VALIDATED folder-form lot applied over them, in name order — the state its save
    published, whatever part of it reached the folder. A lot not validated is not read (quarantined at the next save)."""
    for _chemin, lot in lots:
        if lot is not None and lot.get("forme") == "dossier":
            for nom, enveloppe in lot["enregistrements"].items():
                fichiers[nom] = record_bytes_pour(enveloppe, nom.partition("/")[0])
    return fichiers


def _lire_dossier_coherent(root: str | os.PathLike[str]) -> dict[str, bytes]:
    """The record files' bytes, never HALF a save: lots and folder dates sampled before and after the folder is read
    (`_signature_dossier`); a change ⇒ ONE re-read; a change again ⇒ the read under `board_lock`, which every
    folder-form writer holds. Validated lots are overlaid (`_surcouche_lots`)."""
    board = board_dir(root)
    for _essai in range(2):
        avant = _signature_dossier(root)
        fichiers, lots = _octets_enregistrements(board, _COLLECTIONS_BOARD), _lire_lots(root)
        if _signature_dossier(root) == avant:
            return _surcouche_lots(fichiers, lots)
    with board_lock(root):
        return _surcouche_lots(_octets_enregistrements(board, _COLLECTIONS_BOARD), _lire_lots(root))


def _tombes_de(fichiers: dict[str, bytes], store: dict[str, Any]) -> set[str]:
    """The names among ``fichiers`` that hold a TOMBSTONE: those whose id is no live record of its collection."""
    vivants = _noms_vivants(store)  # UNE fois : par nom, le relevé était quadratique (3,7 s sur 1 338 fichiers)
    return {nom for nom in fichiers if nom not in vivants}


def _noms_vivants(store: dict[str, Any]) -> set[str]:
    """``"<collection>/<id>.json"`` of every LIVE record of ``store`` — each name through `record_file`."""
    return {record_file(Path(collection), record["id"]).as_posix() for collection in _COLLECTIONS_BOARD
            for record in store.get(collection) or []}


def _load_dossier(root: str | os.PathLike[str]) -> dict[str, Any]:
    """`load()` in the folder form: the records (`_lire_dossier_coherent`) assembled — each collection by `sort_key`,
    ``sync_correlations`` = their projection, IN MEMORY —, the O2 view joined as on a monolith (`_assembler_vue`), F5's
    ``ressuscites``, the bytes read per file (``vue_dossier``), then `_valider_board`, each refusal naming its file."""
    board = board_dir(root)
    fichiers = _lire_dossier_coherent(root)
    data = _BoardCharge(assemble_store(fichiers, _COLLECTIONS_BOARD))
    data["sync_outbox"] = []
    _validate_sync_extensions(board, data)
    _assembler_vue(root, data, b"")
    data.ressuscites = frozenset(_ids_ressuscites(data))
    data.vue_dossier = {"racine": os.path.normcase(str(Path(root).resolve())), "fichiers": fichiers,
                        "tombes": _tombes_de(fichiers, data)}
    lieux = {task["id"]: record_file(board / "tasks", task["id"]) for task in data["tasks"]}
    _valider_board(board, data, lieux)
    return data


def _remedy_line(root: str | os.PathLike[str]) -> str:
    """THIS tasks.py, THIS root, absolute, by `repr`, sealed by `shlex.quote`: POSIX only (L-00000079) — the line
    ledger.py prints for the same refusal (T-00001010)."""
    import shlex

    script = (f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); import tasks; "
              f"print(tasks.migrate_store({str(Path(root).resolve())!r}))")
    return "python3 -c " + shlex.quote(script)


#: N1 (closing review of batch 4): a two-forms refusal names at most this many ids per list, then « … and N more ».
_IDS_NOMMES_MAX = 20


def _borne(noms: list[str]) -> str:
    """At most `_IDS_NOMMES_MAX` names, then « … and N more »: a refusal over a thousand ids stays readable (N1)."""
    reste = len(noms) - _IDS_NOMMES_MAX
    return ", ".join(noms[:_IDS_NOMMES_MAX]) + (f" … and {reste} more" if reste > 0 else "") or "-"


def _sans_controle(texte: str) -> str:
    """Every control (`Cc`), format (`Cf`), line (`Zl`) and paragraph (`Zp`) separator escaped `\\xNN`, `\\uNNNN` or
    `\\UNNNNNNNN` — the rule of `_sans_controle` in agentic_v3/db/event_store_annonces.py, COPIED: tasks.py never loads
    agentic_v3. Security review of batch 4 (MEDIUM): `numeric_id` anchors the trailing digits only, so a hostile clone
    puts \\r, ESC or U+2028 in a TASKS.json id or key; pasted into a terminal without bracketed paste, a raw \\r ran
    the rest of a `# …` line."""
    def echappe(c: str) -> str:
        n = ord(c)
        return f"\\x{n:02x}" if n <= 0xFF else f"\\u{n:04x}" if n <= 0xFFFF else f"\\U{n:08x}"

    return "".join(echappe(c) if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in texte)


def _en_commentaire(texte: str) -> str:
    """``texte`` as ONE shell comment line (T1): pasted, it runs nothing — every id, key or path in it escaped first
    (`_sans_controle`: a newline, a \\r or U+2028 never opens a line of their own)."""
    return f"# {_sans_controle(texte)}"


def _mises_de_cote(root: str | os.PathLike[str], intents: list[str] | None = None) -> str:
    """THE TWO EXITS of the two-forms state, NEITHER DESTRUCTIVE (exec-critic of T-00001009: an executable `rm -r` of
    the record folders, pasted, erased the whole board when the wrong side was a near-empty TASKS.json written by a
    tasks.py older than T-1009 — Piège 2). One side is SET ASIDE by a `mv -n` to a DATED sibling name under `board/`
    (never read by `load` nor counted by `store_form`, visible to `git status`): nothing is deleted, the human chooses
    which side is right. EVERY executable line is GUARDED — `test -e <witness of the other form> && test ! -e <dated
    target> && mv -n` — and every other line is a shell comment (T1, closing review of batch 4): pasted WHOLE, the
    message runs ONE alternative (the first, whose move takes away the second's witness, TASKS.json) and never nests a
    side inside a dated name that already exists. ``intents`` (T2): O2 intent files under sync_outbox/ set aside WITH
    TASKS.json, witnessed by its dated name. Absolute paths, sealed by `shlex.quote`: POSIX only (L-00000079)."""
    import shlex

    board = board_dir(Path(root).resolve())
    date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def de_cote(source: Path, temoin: Path) -> str:
        cible = shlex.quote(str(board / f"{source.name}.mis-de-cote-{date}"))
        return f"test -e {shlex.quote(str(temoin))} && test ! -e {cible} && mv -n {shlex.quote(str(source))} {cible}"

    mono, dossiers = board / STORE_NAME, [board / c for c in _COLLECTIONS_BOARD if (board / c).is_dir()]
    lignes = [_en_commentaire(f"If the record folders are right (for instance {STORE_NAME} was written again by a "
                              f"tasks.py older than T-00001009, which reads a migrated board as empty), set "
                              f"{STORE_NAME} aside:"), de_cote(mono, (dossiers or [board / "tasks"])[0])]
    a_part = board / f"{STORE_NAME}.mis-de-cote-{date}"
    lignes += [de_cote(board / "sync_outbox" / nom, a_part) for nom in intents or []]
    lignes += [_en_commentaire(f"If {STORE_NAME} is right, set the record folders aside:")]
    lignes += [de_cote(dossier, mono) for dossier in dossiers]
    lignes.append(_en_commentaire("Nothing is deleted: the side set aside stays beside the board under a dated name, "
                                  "to compare and remove by hand. Pasted whole, only the first alternative runs."))
    return "\n".join(lignes)


def _refus_deux_formes_ecriture(root: str | os.PathLike[str]) -> str:
    """The write refusal of two EQUAL forms: comments, the `python3 -c` line — guarded by itself: `migrate_store`
    re-checks both forms and refuses if they differ — then the guarded set-asides (`_mises_de_cote`)."""
    return (_en_commentaire(
        f"refusing to write the board: {store_path(root)} and the record folders under {board_dir(root)} both hold it "
        f"(an interrupted migration, or an older tasks.py that wrote {STORE_NAME} again); nothing was written. If they "
        f"hold the SAME board (an interrupted migration), finish it with migrate_store, which re-checks the folders "
        f"against {STORE_NAME} and refuses if they differ:") + f"\n{_remedy_line(root)}\n{_mises_de_cote(root)}")


def _intents_des_seuls_mono(root: str | os.PathLike[str], seuls_mono: list[str]) -> tuple[list[str], str]:
    """T2 (decision S-01M4PNVY23WGEA1HZRX6BZE1MX: nothing re-imported, no automatic tombstone): the O2 intent files
    whose correlation names a task found ONLY in TASKS.json — left in sync_outbox/ once TASKS.json is set aside, each
    comes back as an orphan key that refuses every write — and the sentence that names them, or says none is left."""
    if not seuls_mono:
        return [], ""
    ids = set(seuls_mono)
    noms = [nom for _cle, nom, _brut, enveloppe, _refus in _lire_definitifs(root)
            if enveloppe is not None and enveloppe["correlation"]["board_task_id"] in ids]
    if not noms:
        return [], (f" No O2 intent file of the ids only in {STORE_NAME} is left under sync_outbox/ — already "
                    "delivered: V3 may keep them linked (nothing is re-imported, no tombstone is written).")
    return noms[:_IDS_NOMMES_MAX], (
        f" The O2 intent files of the ids only in {STORE_NAME} ({_borne(noms)}) are set aside WITH it below — left "
        "under sync_outbox/, each would come back as an orphan key refusing every write; any not named here, the "
        "next refusal names.")


def _comparer_deux_formes(root: str | os.PathLike[str], mono: dict[str, Any]) -> None:
    """BOTH forms are readable only if they hold the SAME board — tasks, epics and correlations, by id; otherwise
    `BoardError` naming the ids of each side and the different ones (each list bounded, N1), the O2 intent files of
    the ids only in TASKS.json (T2), with the remedy lines. Nothing merged in silence."""
    dossier = _load_dossier(root)
    seuls_mono: list[str] = []
    seuls_dossier: list[str] = []
    differents: list[str] = []
    for collection in _COLLECTIONS_BOARD:
        a = {r["id"]: r for r in mono.get(collection) or []}
        b = {r["id"]: r for r in dossier.get(collection) or []}
        seuls_mono += sorted(set(a) - set(b), key=sort_key)
        seuls_dossier += sorted(set(b) - set(a), key=sort_key)
        differents += sorted((rid for rid in set(a) & set(b) if a[rid] != b[rid]), key=sort_key)
    cles = sorted(op for op in set(mono["sync_correlations"]) | set(dossier["sync_correlations"])
                  if mono["sync_correlations"].get(op) != dossier["sync_correlations"].get(op))
    if seuls_mono or seuls_dossier or differents or cles:
        intents, phrase = _intents_des_seuls_mono(root, seuls_mono)
        raise BoardError(_en_commentaire(
            f"{store_path(root)} and the record folders under {board_dir(root)} both hold the board and DISAGREE — "
            f"only in {STORE_NAME}: {_borne(seuls_mono)}; only in the folders: {_borne(seuls_dossier)}; different: "
            f"{_borne(differents)}; correlations that differ: {_borne(cles)}. Nothing is merged in silence, nothing is "
            f"removed.{phrase}") + "\n" + _mises_de_cote(root, intents))


def _empreinte_lot(contenu: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(contenu, ensure_ascii=False, sort_keys=True, allow_nan=False)
                          .encode("utf-8")).hexdigest()


def _lot_dossier_valide(lot: Any) -> bool:
    """A folder-form lot VALIDATES ITSELF — the point of validation of its save: exactly the keys `cible`, `forme`,
    `enregistrements`, `intents`; `cible` = the sha256 of the other three (a truncated or altered lot fails); every
    record name `<collection>/<record id>.json` holding a valid envelope of that collection; every intent like an O2
    lot's (`_NOM_INTENT`, `_refus_enveloppe`)."""
    if not isinstance(lot, dict) or set(lot) != {"cible", "forme", "enregistrements", "intents"}:
        return False
    if lot["forme"] != "dossier" or not isinstance(lot["enregistrements"], dict) or not isinstance(lot["intents"], list):
        return False
    try:
        if lot["cible"] != _empreinte_lot({cle: lot[cle] for cle in ("forme", "enregistrements", "intents")}):
            return False
    except (ValueError, TypeError, RecursionError):  # un lot très profond : non validé, jamais un `load` bloqué
        return False
    for nom, enveloppe in lot["enregistrements"].items():
        collection, _sep, fichier = nom.partition("/")
        rid = fichier[: -len(".json")] if fichier.endswith(".json") else None
        if (collection not in _COLLECTIONS_BOARD or rid is None or _refus_id_enregistrement(rid) is not None
                or _refus_enregistrement(enveloppe, collection, rid) is not None):
            return False
    for entree in lot["intents"]:
        nom = entree.get("nom") if isinstance(entree, dict) else None
        match = _NOM_INTENT.match(nom) if isinstance(nom, str) else None
        if match is None or _refus_enveloppe(entree.get("enveloppe"), match.group(2)) is not None:
            return False
    return True


def _ecrire_lot_dossier(root: str | os.PathLike[str], enregistrements: dict[str, Any],
                        neufs: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    """THE POINT OF VALIDATION of a folder-form save: ONE local lot, CREATED exclusively (`xb`, by
    `_ouvrir_sans_lien`), written, fsync'ed with its folder. A failure before the end removes it: nothing published."""
    contenu = {"forme": "dossier", "enregistrements": enregistrements, "intents": neufs}
    lot = dict(contenu, cible=_empreinte_lot(contenu))
    octets = (json.dumps(lot, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    dossier = _dossier_lots(root)
    dossier.mkdir(parents=True, exist_ok=True)
    base, rang = f"{time.time_ns():020d}", 0
    # Le nom d'un LOT local, jamais d'un enregistrement : même forme que `_ecrire_lot` (T-00001058). Le critère du plan
    # « tout f-string `.json` passe par `record_file` » vise les ENREGISTREMENTS (`board/tasks/`, `board/epics/`).
    while True:
        chemin = dossier / (f"{base}.json" if rang == 0 else f"{base}.{rang}.json")
        try:
            fichier = open(chemin, "xb", opener=_ouvrir_sans_lien)
            break
        except FileExistsError:
            rang += 1
    try:
        with fichier:
            fichier.write(octets)
            fichier.flush()
            os.fsync(fichier.fileno())
        _fsync_dossier(dossier)
    except BaseException:
        try:
            os.unlink(chemin)
        except OSError:
            pass
        _ranger(dossier)
        raise
    return chemin, lot


def _appliquer_lot_dossier(root: str | os.PathLike[str], chemin: Path, lot: dict[str, Any]) -> None:
    """Apply a VALIDATED folder-form lot, IDEMPOTENTLY (same names, same bytes): each record into its collection
    folder (`_poser_definitif`, its name through `record_file`), each new intent into the O2 folder, the folders
    fsync'ed, the lot removed LAST — a crash before leaves it for the next save / claim / migration. A record folder
    that is a symbolic link is refused BEFORE the first write (`_refus_liens`)."""
    board = board_dir(root)
    _refus_liens(root)
    for nom, enveloppe in sorted(lot["enregistrements"].items()):
        collection, _sep, fichier = nom.partition("/")
        cible = record_file(board / collection, fichier[: -len(".json")])
        _poser_definitif(root, cible.name, record_bytes_pour(enveloppe, collection), cible.parent)
    for collection in sorted({nom.partition("/")[0] for nom in lot["enregistrements"]}):
        _fsync_dossier(board / collection)
    for entree in lot["intents"]:
        _poser_definitif(root, entree["nom"], _octets_enveloppe(entree["enveloppe"]))
    if lot["intents"]:
        _fsync_dossier(_dossier_outbox(root))
    os.unlink(chemin)
    _ranger(chemin.parent)


def _garde_de_commit() -> None:
    """The commit guard of `_replace_with_retry` (the V3 bridge's `guard_board_commit`), asked BEFORE the lot: in the
    folder form the lot, not a replace of TASKS.json, publishes the save."""
    garde = _BOARD_COMMIT_GUARD.get()
    if garde is None:
        return
    try:
        accepte = garde()
    except Exception as exc:
        raise BoardError("board commit guard failed") from exc
    if not accepte:
        raise BoardError("board commit guard refused save")


def _remede_orphelins(root: str | os.PathLike[str], data: dict[str, Any]) -> str:
    """The remedy a « dangling correlation » refusal lacks when its key came from an ORPHAN intent file (re-indexed by
    `_assembler_vue`) whose task has NO record in the folder — a restore of `board/tasks/` to a state before the task,
    or a merge that dropped it. Measured (T-00001009): every write, the drain and `delete` (« unknown task id ») were
    refused with no way out. The refusal STAYS (M10); this names the two exits: restore the record, or move the
    intent file aside (its event then never reaches V3). Empty when no re-indexed key dangles."""
    meta = getattr(data, "vue_o2", None) or {}
    correlations = data.get("sync_correlations") or {}
    vivants = {tache.get("id") for tache in data.get("tasks") or [] if isinstance(tache, dict)}
    orphelins = {op for op in meta.get("reindexes") or [] if isinstance(correlations.get(op), dict)
                 and not correlations[op].get("tombstoned") and correlations[op].get("board_task_id") not in vivants}
    fichiers = sorted(str(_dossier_outbox(root) / nom) for nom in meta.get("fichiers") or {}
                      if _NOM_INTENT.match(nom) and _NOM_INTENT.match(nom).group(2) in orphelins)
    if not fichiers:
        return ""
    taches = sorted({correlations[op]["board_task_id"] for op in orphelins}, key=sort_key)
    return (f" — its key comes from an intent file whose task has no record in {board_dir(root) / 'tasks'} (a restore "
            f"of that folder, or a merge): restore the record of {', '.join(taches)} (for instance from git), or move "
            f"the intent file aside, out of sync_outbox/ — its event then never reaches V3: {', '.join(fichiers)}")


def _save_dossier(root: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """`save()` in the folder form, AFTER the refusals `save()` keeps at its head (running group, F5). Under
    `board_lock`: the lots of an interrupted save first; `explode_store` of the data — no root key, a dangling
    correlation REFUSED (« id à clé non tombée disparu », M10) —; a TOMBSTONE for every id read at `load` and absent now
    (`record_bytes_pour(…, "tasks")`, ``[]`` when it carries no key); a tombstone is never written back alive and two
    names of one identity never stand side by side (both refused, nothing written); the files whose bytes differ from
    those `load` read (``vue_dossier``) — never "folder − data": a file born after the `load` is left alone; then ONE
    lot, its application, and the O2 steps of `_apres_publication`. Without ``vue_dossier`` (a fresh dict) the diff is
    against the folder and no tombstone is written. A record folder or the lots folder that is a symbolic link is
    refused first (`_refus_liens`): nothing written outside the board."""
    board = board_dir(root)
    meta = getattr(data, "vue_dossier", None)
    if meta is not None and meta.get("racine") != os.path.normcase(str(Path(root).resolve())):
        meta = None
    with board_lock(root):
        _refus_liens(root, lots=True)
        _reprendre_lots(root)
        if meta:
            lus, tombes = meta["fichiers"], meta["tombes"]
        else:
            lus = _octets_enregistrements(board, _COLLECTIONS_BOARD)
            tombes = _tombes_de(lus, assemble_store(dict(lus), _COLLECTIONS_BOARD))
        publie = {cle: valeur for cle, valeur in data.items() if cle not in ("next_id", "sync_outbox")}
        try:
            nouveaux = explode_store(publie, _COLLECTIONS_BOARD)
        except BoardError as exc:
            raise BoardError(f"{exc}{_remede_orphelins(root, data)}") from None
        for nom in sorted(lus) if meta else ():
            if nom not in nouveaux:
                collection, _sep, fichier = nom.partition("/")
                tombe: dict[str, Any] = {"format": RECORD_FORMAT, "id": fichier[: -len(".json")], "record": None}
                if collection == _COLLECTION_CORRELEE:
                    tombe["sync_operations"] = []
                nouveaux[nom] = record_bytes_pour(tombe, collection)
        revenus = sorted(_noms_vivants(publie) & set(tombes))
        if revenus:
            etat = "is a tombstone" if len(revenus) == 1 else "are tombstones"
            raise BoardError(f"refusing to write the board: {', '.join(revenus)} {etat} (`record: null`) — a deleted "
                             "id is never written back alive; nothing was written")
        identites: dict[tuple[str, Any], str] = {}
        for nom in sorted(set(lus) | set(nouveaux)):
            collection, _sep, fichier = nom.partition("/")
            cle = (collection, identity_key(fichier[: -len(".json")]))
            if cle in identites:
                raise BoardError(f"refusing to write the board: {identites[cle]} and {nom} would name the same record "
                                 "(identity_key) — nothing was written")
            identites[cle] = nom
        a_ecrire = {nom: json.loads(octets) for nom, octets in sorted(nouveaux.items()) if lus.get(nom) != octets}
        plan = _planifier_outbox(root, data)
        _garde_de_commit()
        if a_ecrire or plan["neufs"]:
            chemin, lot = _ecrire_lot_dossier(root, a_ecrire, plan["neufs"])
            try:
                _appliquer_lot_dossier(root, chemin, lot)
            except OSError as exc:
                print(f"TASKS: board — lot validé, application à reprendre au prochain save : {exc}", file=sys.stderr)
        _apres_publication(root, None, dict(plan, forme="dossier"))
    render_view(root, data)


def lire_board_brut(root: str | os.PathLike[str]) -> dict[str, Any]:
    """The board AS THE V3 BRIDGE READS IT (`BoardBridge._board_data`, T-00001009 step 6), whatever its form: a
    monolith (alone or beside the folder) ⇒ its JSON as is, the bridge's read before T-1009; the folder ⇒ the records
    with a validated lot overlaid, ``sync_correlations`` = their projection, NO ``sync_outbox`` (the bridge reads the
    deletions in flight through `suppressions_en_vol`); no board ⇒ ``{"tasks": [], "sync_correlations": {}}``."""
    forme = store_form(root)
    if forme == "absent":
        return {"tasks": [], "sync_correlations": {}}
    if forme != "dossier":
        return json.loads(store_path(root).read_text(encoding="utf-8"))
    return assemble_store(_lire_dossier_coherent(root), _COLLECTIONS_BOARD)


def _triplets(correlations: dict[str, Any]) -> list[tuple[str, str, bool]]:
    return sorted((op, c["board_task_id"], c["tombstoned"]) for op, c in correlations.items())


def _migration_prechecks(root: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """Before anything is written: no top-level key the folder would drop (`tasks`, `epics`, `sync_correlations`,
    `sync_outbox` only), every id a record file name (`record_file`: traversal, separator, 16 digits refused)."""
    extra = sorted(str(cle) for cle in data if cle not in ("tasks", "epics", "sync_correlations", "sync_outbox"))
    if extra:
        raise BoardError(f"{store_path(root)}: top-level key(s) {', '.join(map(repr, extra))} would be dropped — "
                         "not migrated")
    for collection in _COLLECTIONS_BOARD:
        for record in data.get(collection) or []:
            record_file(board_dir(root) / collection, record.get("id") if isinstance(record, dict) else None)
    for collection in _COLLECTIONS_BOARD:
        sous = board_dir(root) / collection
        if sous.is_dir() and any(sous.iterdir()):
            raise BoardError(f"{sous} is not empty and holds no <record id>.json — not migrated, nothing was written")


def migrate_store(root: str | os.PathLike[str]) -> str:
    """Monolith ⇒ folder (T-00001009 step 5): the ONLY function that creates the record folders AND removes
    TASKS.json — no production caller and no CLI verb (parity with T-1010). Under `board_lock`, the lots of an
    interrupted save first. No board, or an empty one ⇒ nothing, NO folder; the folder ⇒ « already migrated »; both
    forms ⇒ `load` holds them equal (else its refusal) and the migration ENDS (unlink). A monolith: `load`, F5 ⇒
    refused; an outbox still IN LINE (a TASKS.json from before T-1058) ⇒ one monolith save first, which moves it to
    files; `_migration_prechecks`; the triplets (operation, task, tombstoned) counted; the records staged under
    `.agents/state/local/board-staging/`, fsync'ed, published by ONE rename per folder and READ BACK (`read_records`):
    triplets, tasks and epics equal, else the folders are removed and TASKS.json is untouched. THE POINT OF VALIDATION
    is the unlink of TASKS.json, asked of the commit guard first (`_garde_de_commit`, security review: fail-closed —
    refused, the folders are removed and TASKS.json stays). The O2 intent files stay as they are (the outbox is frozen
    under the lock, S-00003390), and nothing here loads `agentic_v3`. A record, lots or staging folder that is a
    symbolic link is refused before anything is written."""
    import shutil

    with board_lock(root):
        _refus_liens(root, lots=True)
        _reprendre_lots(root)
        forme = store_form(root)
        if forme == "dossier":
            return f"TASKS: already migrated ({board_dir(root) / 'tasks'})"
        if forme == "absent":
            return "TASKS: nothing to migrate (no board) — no folder created"
        data = load(root)
        if forme == "les deux":
            _garde_de_commit()
            os.unlink(store_path(root))
            _fsync_dossier(board_dir(root))
            return f"TASKS: migration finished — {STORE_NAME} removed, the record folders hold the board"
        if not data["tasks"] and not data.get("epics") and not data.get("sync_correlations"):
            return "TASKS: nothing to migrate (empty board) — no folder created"
        refus = resurrection_refusal(data)
        if refus is not None:
            raise BoardError(f"refusing to migrate the board: {refus} — nothing was written")
        if "sync_outbox" in json.loads(store_path(root).read_bytes().decode("utf-8")):
            save(root, data)
            data = load(root)
        _migration_prechecks(root, data)
        avant = _triplets(data["sync_correlations"])
        fichiers = explode_store({cle: v for cle, v in data.items() if cle != "sync_outbox"}, _COLLECTIONS_BOARD)
        board, stage = board_dir(root), lock_path(root).parent / "board-staging"
        if os.path.islink(stage):
            raise BoardError(f"{stage} is a symbolic link — refused, nothing written: remove the link")
        shutil.rmtree(stage, ignore_errors=True)  # le reste d'une migration interrompue
        publies: list[Path] = []
        try:
            for nom, octets in fichiers.items():
                collection, _sep, fichier = nom.partition("/")
                cible = record_file(stage / collection, fichier[: -len(".json")])
                cible.parent.mkdir(parents=True, exist_ok=True)
                with open(cible, "xb", opener=_ouvrir_sans_lien) as sortie:
                    sortie.write(octets)
                    sortie.flush()
                    os.fsync(sortie.fileno())
            for collection in _COLLECTIONS_BOARD:
                if (stage / collection).is_dir():
                    _fsync_dossier(stage / collection)
                    if (board / collection).is_dir():
                        (board / collection).rmdir()
                    _replace_with_retry(stage / collection, board / collection)
                    publies.append(board / collection)
            _fsync_dossier(board)
            relu = read_records(board, _COLLECTIONS_BOARD)
        except BaseException:
            for dossier in publies:
                shutil.rmtree(dossier, ignore_errors=True)
            shutil.rmtree(stage, ignore_errors=True)
            raise
        shutil.rmtree(stage, ignore_errors=True)
        par_id = lambda records: sorted(records or [], key=lambda r: sort_key(r["id"]))  # noqa: E731
        if (_triplets(relu["sync_correlations"]) != avant or relu["tasks"] != par_id(data["tasks"])
                or par_id(relu.get("epics")) != par_id(data.get("epics"))):
            for dossier in publies:
                shutil.rmtree(dossier, ignore_errors=True)
            raise BoardError(f"{board}: the record folders did not read back as {STORE_NAME} (correlations, tasks or "
                             f"epics differ) — rolled back, {STORE_NAME} untouched")
        try:
            _garde_de_commit()
        except BoardError:
            for dossier in publies:
                shutil.rmtree(dossier, ignore_errors=True)
            raise
        os.unlink(store_path(root))
        _fsync_dossier(board)
        tombes = len(_tombes_de(fichiers, relu))
        return (f"TASKS: migrated {len(relu['tasks'])} task(s), {len(relu.get('epics') or [])} epic(s) and {tombes} "
                f"tombstone(s) to {board / 'tasks'} — {len(avant)} correlation(s) before == after")


# THE O2 CUMULATIVE CAPS (M3 of T-01M4MC28CAKFE8YZ2W4WN7DV2C) — their two measures live HERE, not beside their callers in
# tasks_stockage.py, for the line budget of that file (reserve 1 of plan-critic it. 2: at most 1 590 lines at the tip,
# never a raise of the ratchet). The caps themselves are the `_PLAFOND_INTENTS_*` / `_PLAFOND_QUARANTAINE_*` of
# tasks_stockage.py, read AT CALL time like every other name of a part.
def _intents_retenus(dossier: Path) -> tuple[list[Path], int]:
    """The intent files ONE read of the O2 folder takes: those NAMED like an intent, in name order (= order key), while
    their number stays within `_PLAFOND_INTENTS_NOMBRE` and the sum of their sizes (`lstat`) within
    `_PLAFOND_INTENTS_OCTETS_CUMULES` — and how many are LEFT OUT beyond that window, in place. `_lire_definitifs` and
    `_relire` read the SAME window: a file beyond it is never « unreadable », never quarantined, never removed."""
    noms = sorted(chemin for chemin in dossier.glob("*.json") if _NOM_INTENT.match(chemin.name))
    nombre, octets, cumul = _PLAFOND_INTENTS_NOMBRE, _PLAFOND_INTENTS_OCTETS_CUMULES, 0
    for rang, chemin in enumerate(noms):
        try:
            cumul += chemin.lstat().st_size
        except OSError:
            pass  # gone between the listing and the measure: its read says so
        if rang >= nombre or cumul > octets:
            return noms[:rang], len(noms) - rang
    return noms, 0


def _bilan_quarantaine(dossier: Path) -> dict[str, int]:
    """The quarantine folder's entries and the sum of their sizes (`lstat`), in ONE `scandir`: evaluated lazily, at the
    first NEW entry of a caller, at most once per caller (`_mettre_en_quarantaine`, ``bilan``)."""
    entrees = octets = 0
    with os.scandir(dossier) as lus:
        for entree in lus:
            entrees += 1
            octets += entree.stat(follow_symlinks=False).st_size
    return {"entrees": entrees, "octets": octets}
