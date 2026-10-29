# tasks_sync.py — PARTIE de `tasks.py` (T-00000788) : la SYNCHRONISATION V3 —
# outbox des intents, réservation, acquittement, drain, et `replay_sync`.
# Le déversement hors du board suivi (T-00001006, T-00001052) vit dans `tasks_deversement.py` (T-00001071).
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


@contextmanager
def suppress_sync(operation_id: str) -> Iterator[None]:
    """Suppress only the V3 command currently applying its board effect."""
    if not operation_id:
        raise BoardError("sync suppression requires an active operation id")
    token = _SUPPRESSED_SYNC_OPERATION.set(operation_id)
    try:
        yield
    finally:
        _SUPPRESSED_SYNC_OPERATION.reset(token)


@contextmanager
def guard_board_commit(guard: Callable[[], bool]) -> Iterator[None]:
    """Require ``guard`` to approve immediately before publishing a board save."""
    if not callable(guard):
        raise BoardError("board commit guard must be callable")
    token = _BOARD_COMMIT_GUARD.set(guard)
    try:
        yield
    finally:
        _BOARD_COMMIT_GUARD.reset(token)


def enqueue_sync_intent(
    data: dict[str, Any],
    board_task_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    event_kind: str = "BOARD_TASK_OBSERVED",
    affected_task_ids: list[str] | None = None,
    operation_id: str | None = None,
) -> str:
    """Append one durable intent and its exact operation correlation.

    ``operation_id`` (T-00001060) : une opération EXPLICITE — celle d'une corrélation
    texte seule que la migration nommée du pont porte en machine — au lieu d'un uuid
    neuf ; refusée si elle est déjà dans ``sync_outbox`` (deux intents d'une même
    opération casseraient l'identité d'opération du réducteur). La forme de l'entrée
    ne change pas : ce module reste l'écrivain UNIQUE de l'outbox."""
    _ensure_sync_extensions(data)
    suppressed_operation = _SUPPRESSED_SYNC_OPERATION.get()
    if suppressed_operation is not None:
        return suppressed_operation
    if operation_id is not None:
        if not operation_id or any(i["operation_id"] == operation_id for i in data["sync_outbox"]):
            raise BoardError(f"operation {operation_id!r} is empty or already pending in sync_outbox")
    else:
        operation_id = str(uuid.uuid4())
    tombstoned = after is None
    before_snapshot = canonical_task_snapshot(before)
    after_snapshot = canonical_task_snapshot(after)
    data["sync_correlations"][operation_id] = {
        "board_task_id": board_task_id,
        "tombstoned": tombstoned,
    }
    if tombstoned:
        for correlation in data["sync_correlations"].values():
            if correlation["board_task_id"] == board_task_id:
                correlation["tombstoned"] = True
    data["sync_outbox"].append(
        {
            "operation_id": operation_id,
            "event_kind": event_kind,
            "affected_task_ids": affected_task_ids or [board_task_id],
            "before": before_snapshot,
            "after": after_snapshot,
            "revision_sha256": revision_sha256(before_snapshot, after_snapshot),
            "attempt": 0,
            "lease": None,
        }
    )
    return operation_id


def suppressions_en_vol(data: dict[str, Any], root: str | os.PathLike[str]) -> set[str]:
    """Les ids dont une SUPPRESSION est EN VOL : intents ``after=None`` de
    ``data["sync_outbox"]`` ET du fichier de déversement (``_chemin_deverse``, plus ancien
    que tout le board). Seul lecteur de leurs SUPPRESSIONS pour le pont (T-00001060) ; `_drain_board_backlog` et la
    migration du pont lisent aussi l'outbox (``tasks.load``) et l'existence du déversement : en O2 (T-00001058), tous suivent.

    Aucun filtre sur ``sync_correlations`` (réserve C2) : la clé texte peut manquer, la
    suppression reste en vol. Le fichier est LU sans écrire, ouvert comme le rejeu
    (``_ouvrir_sans_lien``), et son segment final non terminé (ajout interrompu) est
    ignoré comme dans ``_reinjecter_deverses``. Illisible ⇒ ``DeverseIllisible`` :
    FAIL-CLOSED, l'appelant relâche sa commande plutôt que de créer.

    O2 (T-00001058, W13) : le pont passe le JSON BRUT (`_board_data`), qui ne porte plus
    l'outbox ; la lecture couvre donc AUSSI le dossier des intents — chaque définitif,
    orphelin compris (jamais filtré sur les clés) — et TOUS les lots, validés ou non : en
    compter une de trop sur une tâche PRÉSENTE ne change rien, sur un id ABSENT la commande
    est acquittée NR ; en oublier une ressuscite. Asymétrique à `load()` à dessein : un
    définitif ou un lot illisible LÈVE ici (la commande est relâchée), là où `load()`
    l'exclut de la vue pour garder `list` et son remède vivants. Forme DOSSIER (T-00001009) :
    un lot de save porte aussi ses `intents` (la même clé) ; un lot hors forme ou dont
    l'empreinte ne couvre pas le contenu se lit `None` et LÈVE de même.

    T-01M4MC28CAKFE8YZ2W4WN7DV2C : le dossier des intents en lien (M2, `_refus_liens`) et des fichiers
    laissés hors de la fenêtre de lecture (M3, `_intents_retenus`) LÈVENT aussi `DeverseIllisible` :
    une suppression en vol peut y être, la commande est relâchée."""
    ids: set[str] = set()
    intents = list(data.get("sync_outbox") or [])
    chemin = _chemin_deverse(root)
    if os.path.lexists(chemin):
        try:
            with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:  # borné : avis sécu de l'Outbox (F5)
                *lignes, _queue = _lire_plafonne(fichier, _PLAFOND_DEVERSE_OCTETS).split(b"\n")
            intents.extend(json.loads(ligne) for ligne in lignes)
        except (OSError, ValueError, RecursionError) as exc:
            raise DeverseIllisible(f"{chemin} : suppressions en vol illisibles : {exc}") from exc
    ecart: dict[str, int] = {}
    try:
        definitifs = _lire_definitifs(root, ecart=ecart)
    except BoardError as exc:
        raise DeverseIllisible(f"{_dossier_outbox(root)} : suppressions en vol illisibles : {exc}") from exc
    if ecart:
        raise DeverseIllisible(f"{_dossier_outbox(root)} : suppressions en vol illisibles : {ecart['nombre']} "
                               "fichier(s) d'intent au-delà du plafond de lecture")
    for _cle, nom, _octets, enveloppe, refus in definitifs:
        if enveloppe is None:
            raise DeverseIllisible(f"{_dossier_outbox(root) / nom} : suppressions en vol illisibles : {refus}")
        intents.append(enveloppe["intent"])
    for chemin_lot, lot in _lire_lots(root):
        if lot is None:
            raise DeverseIllisible(f"{chemin_lot} : suppressions en vol illisibles : lot hors forme")
        intents.extend(entree["enveloppe"]["intent"] for entree in lot["intents"])
    for intent in intents:
        if not isinstance(intent, dict):
            raise DeverseIllisible(f"{chemin} : intent hors forme : {intent!r}")
        if intent.get("after") is not None:
            continue
        before = intent.get("before")
        if isinstance(before, dict) and isinstance(before.get("id"), str):
            ids.add(before["id"])
        affectes = intent.get("affected_task_ids")
        if isinstance(affectes, list) and affectes and isinstance(affectes[0], str):
            ids.add(affectes[0])  # comme le réducteur (`EventStore.consume_board_intent`)
    return ids


def claim_sync_event(
    root: str | os.PathLike[str],
    owner: str,
    *,
    now: float | None = None,
    lease_seconds: float = _LEASE_SECONDS,
) -> dict[str, Any] | None:
    """Claim one pending/expired intent, saving the lease before returning. Nothing is claimed while the spill file
    exists (T-00001006): a spill born DURING a live drain holds older intents than the board head, so the drain stops
    and the next one replays the file first (`_reinjecter_deverses`). T-00001058 : the lots of an interrupted save are
    recovered FIRST (`_reprendre_lots`), before that early return (S-00003917 (1)) — on a board in records
    (T-00001009) a validated lot is applied again, records and intents, before anything is claimed.
    T-01M4M175MY8RRRVFN7QRV48566 : with the spill file present, the ONLY head that passes is one whose operation is in
    an `actif` slice marker (`_chemin_tranche`) — that slice is older than the whole file; a marker absent, unreadable,
    `prepare` or `rendu` claims nothing, as before."""
    claimed_at = time.time() if now is None else now
    with board_lock(root):
        _reprendre_lots(root)
        tranche: set[str] | None = None
        if os.path.lexists(_chemin_deverse(root)):
            try:
                marqueur = _lire_tranche(root)
            except DeverseIllisible:
                return None
            if marqueur is None or marqueur["etat"] != "actif":
                return None  # T-00001006 : un déversement est né PENDANT ce drain ; il passe d'abord (FIFO)
            tranche = set(marqueur["ops"])
        data = load(root)
        _ensure_sync_extensions(data)
        if not data["sync_outbox"]:
            return None
        intent = data["sync_outbox"][0]
        if tranche is not None and intent["operation_id"] not in tranche:
            return None  # la tranche est livrée : le reste du fichier passe avant le board
        lease = intent["lease"]
        if lease is not None and float(lease["expires_at"]) > claimed_at:
            return None
        if lease is not None:
            intent["attempt"] += 1
        intent["lease"] = {
            "owner": owner,
            "token": str(uuid.uuid4()),
            "expires_at": claimed_at + lease_seconds,
        }
        save(root, data)
        return copy.deepcopy(intent)
    return None


def ack_sync_event(
    root: str | os.PathLike[str],
    operation_id: str,
    lease_token: str,
) -> bool:
    """ACK only the exact claimed lease; stale workers cannot remove a retry."""
    with board_lock(root):
        data = load(root)
        _ensure_sync_extensions(data)
        for index, intent in enumerate(data["sync_outbox"]):
            lease = intent["lease"]
            if intent["operation_id"] != operation_id:
                continue
            if lease is None or lease["token"] != lease_token:
                return False
            del data["sync_outbox"][index]
            correlation = data["sync_correlations"][operation_id]
            same_task_correlations = [
                key
                for key, value in data["sync_correlations"].items()
                if value["board_task_id"] == correlation["board_task_id"] and key != operation_id
            ]
            is_creation = intent["before"] is None and intent["after"] is not None
            # T-00001058 (F5L) : une non-création n'est élaguée que s'il reste une AUTRE clé de sa tâche ; une
            # suppression seule de sa tâche GARDE la sienne, tombstoned=True — la trace que le refus F5 lit.
            if not is_creation and same_task_correlations:
                del data["sync_correlations"][operation_id]
            save(root, data)
            return True
    return False


def release_sync_event(
    root: str | os.PathLike[str],
    operation_id: str,
    lease_token: str,
) -> bool:
    """Release a failed claim and count the next delivery attempt."""
    with board_lock(root):
        data = load(root)
        _ensure_sync_extensions(data)
        for intent in data["sync_outbox"]:
            lease = intent["lease"]
            if intent["operation_id"] != operation_id:
                continue
            if lease is None or lease["token"] != lease_token:
                return False
            intent["attempt"] += 1
            intent["lease"] = None
            save(root, data)
            return True
    return False


_RAISONS_DEGRADATION = (
    "pont-v3-refuse",
    "pont-v3-panne",
    "sync-outbox-deverse",
    "sync-outbox-deverse-impossible",
    "sync-outbox-rejeu-impossible",
)


# T-00001089 : chemin RÉSOLU d'`events.py` -> ((st_mtime_ns, st_size), module chargé).
_EVENTS_PAR_CHEMIN: dict[str, tuple[tuple[int, int], Any]] = {}


def _charger_events(repository_root: str | os.PathLike[str]) -> Any:
    """`events.py` chargé PAR CHEMIN (contrat d'import de ce module), sous un nom
    SYNTHÉTIQUE enregistré dans `sys.modules` AVANT `exec_module` (L-00000142).
    MÉMOÏSÉ par chemin résolu (T-00001089) : son cache `git config user.name` survit
    d'une émission à l'autre ; un fichier RÉÉCRIT (mtime, taille) est rechargé (D31).
    BORNES MESURÉES : réécrit à MÊME taille et même `st_mtime_ns`, il n'est PAS rechargé ;
    à même taille dans la même SECONDE, il l'est mais exécute l'ANCIEN code, servi par
    `__pycache__` (`.pyc` validé sur mtime à la seconde + taille ; APFS : 0 `st_mtime_ns`
    commun sur 2000 réécritures enchaînées). Un hit RÉ-ENREGISTRE le module retiré de
    `sys.modules` par un tiers, sans jamais écraser une entrée en place (`setdefault`).
    Un `events.py` absent lève `FileNotFoundError` dès `stat`, capté par l'appelant."""
    import importlib.util

    chemin = (Path(repository_root) / ".agents" / "bin" / "events.py").resolve()
    st = chemin.stat()
    signature, memo = (st.st_mtime_ns, st.st_size), _EVENTS_PAR_CHEMIN.get(str(chemin))
    if memo is not None and memo[0] == signature:
        sys.modules.setdefault(memo[1].__name__, memo[1])
        return memo[1]
    spec = importlib.util.spec_from_file_location("_events_tasks_sync", chemin)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        _EVENTS_PAR_CHEMIN.pop(str(chemin), None)
        raise
    _EVENTS_PAR_CHEMIN[str(chemin)] = (signature, module)
    return module


def _signaler_degradation_v3(
    root: str | os.PathLike[str],
    repository_root: str | os.PathLike[str],
    pont_commande: dict[str, Any] | None,
    raison: str,
) -> None:
    """Émet `gate.coverage_degraded` (canal A) avec une `reason` du vocabulaire FERMÉ.
    Fail-open comme `emit`. Se TAIT hors commande (`pont_commande` nul) et sur une racine
    étrangère sans `AGENTS_EVENTS_DIR` : `events.py` résout son dossier depuis SON fichier."""
    if pont_commande is None or raison not in _RAISONS_DEGRADATION:
        return
    try:
        if not (
            os.environ.get("AGENTS_EVENTS_DIR")
            or Path(normalize_root(root)).resolve() == Path(repository_root).resolve()
        ):
            return
        events = _charger_events(repository_root)
        if events is None:
            return
        champs: dict[str, Any] = {"reason": raison}
        hote = os.environ.get("AGENTS_HOOK_HOST")
        if hote in ("claude", "codex", "copilot", "gemini"):
            champs["host"] = hote
        events.emit("gate.coverage_degraded", **champs)
    except Exception:
        return


def _est_run_export_error(exc: BaseException) -> bool:
    """Vrai si `exc` est un `RunExportError` (CONSTAT 6). Cette classe HÉRITE de
    `RuntimeError`, exactement comme le fail-closed de rédaction — c'est pourquoi
    une adresse git absente était captée par le même handler et annoncée sous la
    cause rédaction, FAUSSE. Importé par la couture `agentic_v3` ; `False` si
    indisponible, on retombe alors sur la cause rédaction (cause historique)."""
    try:
        from agentic_v3.db.run_export import RunExportError
    except Exception:
        return False
    return isinstance(exc, RunExportError)


def _est_panne_infrastructure(exc: BaseException) -> bool:
    """Vrai si `exc` est une `PanneInfrastructure`. Levée, au relevé du 2026-09-27
    (`git grep -n "raise PanneInfrastructure" agentic_v3/`), par DEUX fonctions de
    `run_export` : `_email_git` (T-00000695/696) — `git config user.email` en ÉCHEC
    (127, 128, 126, 124), couture `cadre.executor` INTROUVABLE ou en ERREUR ; et
    `_couture_ledger_store` (T-00000770) — couture `cadre.ledger.store` introuvable
    ou en erreur, donc dès `create_tables` à la construction du pont (branche PANNE
    de `replay_sync`, T-00000782). Sur le chemin d'ÉCRITURE, seule panne mesurée qui
    remonte jusqu'au drain (`_flush_export` attrape `AuteurIndisponible` et les
    échecs de sa boucle). `False` si `run_export` est indisponible ou antérieur au
    type : on retombe alors sur le message ouvert, jamais sur un avalage."""
    try:
        from agentic_v3.db.run_export import PanneInfrastructure
    except Exception:
        return False
    return isinstance(exc, PanneInfrastructure)


def _remettre_en_file(root: str | os.PathLike[str], rendu: dict[str, Any]) -> int:
    """`_reinjecter_deverses`, en tête du drain comme dans sa boucle (T-01M4M175MY8RRRVFN7QRV48566) : une levée devient
    UNE ligne stderr et `DeverseIllisible`, que `replay_sync` annonce `sync-outbox-rejeu-impossible`."""
    try:
        return _reinjecter_deverses(root, rendu=rendu)
    except (DeverseIllisible, OSError) as exc:  # PAS `BoardError` : verrou expiré ou board illisible gardent leur message (rc 2)
        print(
            "TASKS: sync_outbox — rejeu du déversement IMPOSSIBLE, aucun intent n'est drainé "
            f"(l'ordre FIFO l'exige) : {exc}",
            file=sys.stderr,
        )
        raise DeverseIllisible(str(exc)) from exc


def drain_sync_outbox(
    root: str | os.PathLike[str],
    consumer: Callable[[dict[str, Any]], bool],
    *,
    owner: str | None = None,
    limit: int | None = None,
    echec: dict[str, Any] | None = None,
    signaler: Callable[[str], None] | None = None,
) -> int:
    """Deliver outside the lock, reread, then ACK the same lease token.

    T-00001053 : un drain qui s'arrête sur un ÉCHEC — le consumer lève, ou confirme `False` (le « bail relâché sans
    trace » de BK-766, désormais NOMMÉ sur stderr) — relâche le bail, RESTITUE au fichier de déversement les intents
    qu'il venait d'y reprendre sans les livrer (`_restituer_deverse`), puis ramène l'outbox au seuil
    (`_deverser_excedent`, `signaler` relayé) : la borne de 200 tient sans refus du pont. `echec`, si fourni, reçoit
    `cause` (une ligne) et `attente` quand le code SQLite PRIMAIRE vaut 5. Un ACK perdu n'est pas un échec. Le
    retour, le nombre d'intents acquittés, ne change pas.

    T-00001058 (F5, décision S-01M4KHGGH0BTZF3M0YQ9A9KKAE) : tant que le board porte une tâche tombée VIVANTE
    (`resurrection_refusal`), le drain est SUSPENDU — une ligne stderr, rien de livré ni d'écrit, `echec` posé —
    car chaque `save` y serait refusé et le drain d'avant un verbe rendrait rc 2 à tout verbe, `delete` (le
    remède) compris ; le verbe porte lui-même le refus à son `save`.

    T-01M4M175MY8RRRVFN7QRV48566 : quand la réservation ne rend rien sans échec et que `limit` n'est pas atteint, la
    remise en file est RAPPELÉE — SEULEMENT si le marqueur de tranche existe (`_chemin_tranche`) : la tranche précédente
    livrée, la suivante (ou le reste, s'il tient en une tranche) est remise en file et `rendu` remplacé ; 0 ⇒ fin. SANS
    marqueur, arrêt comme T-00001006 : un déversement né pendant un drain vivant attend le drain suivant. Chaque tour
    livre ou sort. Une levée de la remise en file reçoit le MÊME traitement qu'en tête (`_remettre_en_file`)."""
    rendu: dict[str, Any] = {}
    etat = load(root)
    suspendu = resurrection_refusal(etat)
    if suspendu is not None and (etat.get("sync_outbox") or os.path.lexists(_chemin_deverse(root))):
        print(f"TASKS: sync_outbox — drain SUSPENDU, rien n'est livré ni écrit : {suspendu}", file=sys.stderr)
        if echec is not None:
            echec["cause"] = "drain suspendu : une tâche tombée est vivante au board"
        return 0
    _remettre_en_file(root, rendu)  # le déversement est plus ancien que tout le board : il passe d'abord
    worker = owner or f"tasks.py:{os.getpid()}:{uuid.uuid4()}"
    drained = 0
    cause: str | None = None
    while limit is None or drained < limit:
        intent = claim_sync_event(root, worker)
        if intent is None:
            if os.path.lexists(_chemin_tranche(root)) and _remettre_en_file(root, rendu) > 0:
                continue  # la tranche précédente est livrée : la suivante passe, avant le board
            break
        lease_token = intent["lease"]["token"]
        confirmed = False
        try:
            confirmed = bool(consumer(copy.deepcopy(intent)))
            load(root)  # required post-effect reread before ACK
        except RuntimeError as exc:
            # T-00000641 (B-1, L-00000136) : le store V3 est FAIL-CLOSED sur un
            # module de rédaction absent — il LÈVE plutôt que de miroiter un
            # événement non rédigé. Ne PAS avaler ce signal en silence (sinon le
            # miroir board disparaît sans un octet d'avertissement, dès le premier
            # jour chez un adoptant hors clone du kit) : relâcher le bail, annoncer
            # sur stderr, et arrêter le drain.
            # CONSTAT 6 : `RunExportError` hérite AUSSI de `RuntimeError`, donc un
            # refus d'export tombe dans ce même handler et doit être NOMMÉ pour ce
            # qu'il est, jamais sous la cause rédaction (FAUSSE).
            release_sync_event(root, intent["operation_id"], lease_token)
            if _est_panne_infrastructure(exc):
                # T-00000695/696, constat du binôme : c'est le message du CHEMIN
                # D'ÉCRITURE, et il nommait EN TÊTE « git user.email absent » — la
                # seule cause qui ne peut PAS arriver ici — sans jamais dire PANNE ni
                # BLOQUÉ, là où le chemin de CONSTRUCTION
                # (`event_store.py::_rejouer_journaux_attente`) les dit. Mesuré sur
                # un dépôt au `.git/config` casse : l'exception jointe disait « PAS
                # un auteur absent » pendant que le préfixe disait l'inverse. Même
                # vocabulaire désormais sur les deux chemins : PANNE, BLOQUÉ
                # jusqu'à réparation. L'événement EST en base — la panne remonte de
                # `_flush_export`, APRÈS le commit.
                print(
                    "tasks.py: miroir V3 — PANNE de resolution d'auteur, evenement "
                    "ecrit en base, export versionne BLOQUE jusqu'a reparation, "
                    f"journal d'attente conserve : {_aplatir_exc(exc)}",
                    file=sys.stderr,
                )
            elif _est_run_export_error(exc):
                # T3 (binôme) : un `git user.email` ABSENT est normalement RATTRAPÉ en
                # amont par `event_store.py::_flush_export` (il n'attrape QUE
                # `AuteurIndisponible` : événement commité en base, journal d'attente
                # conservé, export différé), et le drain VIDE alors l'outbox. Ce qui
                # REMONTE jusqu'ici est un `RunExportError` non rattrapé — cause FATALE
                # (copie réservée, ULID malformé, traversée de chemin) ou E/S. L'événement
                # est déjà commité en base, seul l'export versionné est différé, son
                # journal conservé pour rejeu. Ne PAS dire « suspendue » (arrêt qui n'a
                # pas lieu). F2 (binôme) : l'énumération du message reste OUVERTE
                # (« ... ou E/S ») et NOMME `git user.email` plutôt que de l'EXCLURE —
                # épingler une cause EXACTE ici était la faute T1 en image miroir, un
                # message verrouillé dans la porte par un `assertNotIn("user.email")` que
                # F1 rend caduc (le cas nominal « auteur absent » se DIFFÈRE désormais, il
                # n'échoue plus). F9 : locator par NOM de symbole, jamais par plage de
                # lignes (les correctifs de ce lot les déplacent).
                # T-00000695/696 : la PANNE a désormais sa branche (ci-dessus), et
                # « git user.email absent » passe en FIN d'énumération — il reste
                # nommé (F2, défensif), mais n'est plus la première cause lue alors
                # qu'il est rattrapé en amont.
                print(
                    "tasks.py: miroir V3 — evenement ecrit en base, export versionne "
                    "DIFFERE (copie reservee, ULID malforme, traversee de chemin, E/S "
                    "ou git user.email absent), "
                    f"journal d'attente conserve pour rejeu : {_aplatir_exc(exc)}",
                    file=sys.stderr,
                )
            else:
                # Rédaction absente : FAIL-CLOSED réel (T-00000641, B-1) — rien n'est
                # miroité, la synchronisation board->V3 est bien suspendue.
                print(
                    "tasks.py: miroir V3 arrete — redaction indisponible, "
                    f"synchronisation board->V3 suspendue : {_aplatir_exc(exc)}",
                    file=sys.stderr,
                )
            cause = _aplatir_exc(exc)
            break
        except Exception as exc:
            # T3 voisin (binôme, fable) : un échec NON-`RuntimeError` du consumer
            # (OSError disque plein, p.ex.) ne doit pas DISPARAÎTRE. Le retour ne
            # change pas — `confirmed = False`, donc l'intent n'est PAS acquitté et
            # sera rejoué au prochain drain (release ci-dessous) — mais la cause est
            # NOMMÉE sur stderr, jamais avalée en silence (0 mot mesuré avant).
            confirmed = False
            # T-00001056 (décision pilote S-00003429, A) : pont CONSTRUIT, deux échecs
            # du drain sont NOMMÉS par leur code PRIMAIRE (`& 0xFF`) ; depuis T-00001053,
            # la cause remonte par `echec` (`replay-sync` rend 1) et le code 5 y pose
            # `attente` (UNE attente par commande). 5 : verrou
            # d'écrivain en WAL tenu au-delà de l'attente de `_connexion_nue` ; 8 :
            # FICHIER de store en lecture seule. CLASSE d'abord (`DatabaseError`), code
            # ensuite : une autre levée portant un attribut homonyme reste « echec
            # inattendu ». `import sqlite3` LOCAL (filet (e) de `test_tasks_decoupe.py`).
            import sqlite3

            code = (getattr(exc, "sqlite_errorcode", None)
                    if isinstance(exc, sqlite3.DatabaseError) else None)
            nomme = {5: "store verrouille par un autre ecrivain (apres l'attente de 30 s)",
                     8: "store en lecture seule"}.get(code & 0xFF if isinstance(code, int) else None)
            if isinstance(exc, _classe_emplacement_refuse()):  # T-00001007 (h) : le libellé de la construction
                nomme = "REFUSÉ (emplacement du store refusé — lien, second nom, non régulier ou autre)"
            print(
                f"tasks.py: miroir V3 — {nomme or 'echec inattendu du consumer'}, intent NON "
                f"acquitte (rejeu au prochain drain) : {exc!r}",
                file=sys.stderr,
            )
            cause = repr(exc)
            if echec is not None and isinstance(code, int) and code & 0xFF == 5:
                # code primaire 5 (BUSY) : `replay_sync` saute le drain d'après le verbe — UNE attente au plus par commande
                echec["attente"] = True
        if confirmed and ack_sync_event(root, intent["operation_id"], lease_token):
            drained += 1
            continue
        release_sync_event(root, intent["operation_id"], lease_token)
        if not confirmed and cause is None:  # un ACK perdu (bail repris par un autre) n'est PAS un échec
            cause = "confirmation refusee par le consumer"
            print(f"tasks.py: miroir V3 — {cause}, intent NON acquitte (rejeu au prochain drain)", file=sys.stderr)
        break
    if cause is not None:  # T-00001053 : sortie en ÉCHEC, bail relâché — la garde de T-1006 laisse partir l'excédent
        if echec is not None:
            echec["cause"] = cause
        # AVANT le déversement : sinon chaque drain recopie tout le fichier en trace ; le retour est LU (L-00000136)
        if not _restituer_deverse(root, rendu):
            print(
                "TASKS: sync_outbox — restitution NON faite (bail vivant, fichier reparu, trace absente, illisible ou "
                "interrompue, ou écriture en échec) : intents repris gardés au board, trace laissée telle quelle : "
                f"{rendu.get('trace')}",
                file=sys.stderr,
            )
        _deverser_excedent(root, signaler=signaler)
    return drained


def _classe_cadre_path_error() -> type | None:
    """La classe `CadrePathError` EXACTE que `DEFAULT_DB_PATH(root)` peut lever,
    prise DEPUIS la couture d'import de `run_export` (CONSTAT 4). `cadre` n'est PAS
    un paquet installé ici : il est chargé par cette couture sous un nom de module
    SYNTHÉTIQUE (`_cadre_paths_v3`), et c'est CETTE classe-là qui est levée. Un
    `from cadre.paths import CadrePathError` viserait une AUTRE classe (voire
    échouerait, `cadre` non importable sans `src/` sur le `sys.path`). La couture
    rend le MÊME objet-classe quelle que soit la branche (paquet installé OU chemin),
    donc `isinstance` est fiable. `None` si la couture est indisponible — on
    retombe alors sur `raise`, jamais sur un avalage silencieux."""
    try:
        from agentic_v3.db import run_export

        return run_export._cadre("paths").CadrePathError
    except Exception:
        return None


def _classe_emplacement_refuse() -> type | tuple[()]:
    """`EmplacementRefuse` prise PAR LA COUTURE `run_export._couture_ledger_store`, même objet-classe que celui que
    lèvent `create_tables` et `get_db_connection` ; `()` si la couture est indisponible, jamais une levée."""
    try:
        from agentic_v3.db import run_export

        return run_export._couture_ledger_store()[0].EmplacementRefuse
    except Exception:
        return ()


def _aplatir_exc(exc: BaseException) -> str:
    """Le message de `exc` sur UNE ligne affichable (T-00001056, S-00003357) : ses
    blancs réduits à une espace, puis tout caractère non imprimable (`isprintable()`
    faux : saut de ligne, ESC, C1, NUL, séparateurs Unicode) remplacé par `?` ; l'espace
    ASCII est imprimable, elle survit. Même règle que `refus_store._aplatir`
    (T-00001005), COPIÉE ici : cette partie ne dépend pas de ce module."""
    return "".join(c if c.isprintable() else "?" for c in " ".join(str(exc).split()))


def _annonce_refus_construction(exc: BaseException) -> str | None:
    """Le libellé d'un refus de CONSTRUCTION du pont que (2)-(4) de `replay_sync`
    ne rangent pas, ou `None` : la levée REMONTE (T-00001004 et T-00001056, résidus
    R6 de T-00000782). Sélection par CLASSE RÉELLE ou par CODE, jamais par nom ni
    message. (5) `OuvertureImpossible` (SQLite refuse d'ouvrir un emplacement
    INCHANGÉ ; la cause exacte va en fin de ligne) et (6) `HorsRacine` sont prises PAR
    LA COUTURE `run_export._couture_ledger_store`, comme `EmplacementRefuse` : même
    objet-classe que celui que lève `create_tables`. Un paquet `cadre` antérieur sans
    l'attribut rend `()`, jamais une levée ; couture indisponible -> `()` aussi, la
    cause retombe en (4) `PanneInfrastructure`. (7)-(8) `sqlite3.DatabaseError` dont
    le code PRIMAIRE (`sqlite_errorcode & 0xFF` : l'étendu 261, SQLITE_BUSY_RECOVERY,
    garde son primaire 5) vaut 26 (SQLITE_NOTADB, store non SQLite) ou 5 (SQLITE_BUSY,
    verrou tenu au-delà des 30 s d'attente). (9) `PermissionError` : le `mkdir` de la
    partition d'état, ou la création du store dans `run/`, refusé. (10)
    `NotADirectoryError` ou `FileExistsError` : un fichier occupe la partition ou
    `run/`. (9)-(10) sont trois sœurs disjointes sous `OSError`, jamais `OSError`
    entière ; `OuvertureImpossible` est une `OperationalError`, pas une `OSError`.
    (11)-(12) code PRIMAIRE 8 (SQLITE_READONLY ; l'étendu 1544, READONLY_DIRECTORY, garde son primaire ;
    l'étendu 1032, READONLY_DBMOVED, base déplacée, REMONTE) ou 11 (SQLITE_CORRUPT). Codes LITTÉRAUX ;
    `sqlite_errorcode` date de Python 3.11, plancher déclaré du kit (`pyproject.toml`, `requires-python`).
    Sans code — interpréteur antérieur, ou « database is locked » fabriqué à la main —
    la levée REMONTE. Jamais un `except sqlite3.DatabaseError` large (T-00000782 l'a
    refusé). REMONTENT : `IntegrityError` (19), toute `ValueError` nue, toute autre
    `OSError`. `import sqlite3` LOCAL : cette partie s'exécute dans l'espace de
    `tasks`, qui ne l'importe pas, et n'y ajoute aucun nom de tête
    (`test_tasks_decoupe.py`, filet (e))."""
    import sqlite3

    try:
        from agentic_v3.db import run_export

        store_mod, workspace_mod = run_export._couture_ledger_store()
    except Exception:  # couture indisponible : retombe en (4) `PanneInfrastructure`
        store_mod = workspace_mod = None
    if isinstance(exc, getattr(store_mod, "OuvertureImpossible", ())):
        return "REFUSÉ (ouverture impossible, emplacement inchangé — cause SQLite en fin de ligne)"
    if isinstance(exc, getattr(workspace_mod, "HorsRacine", ())):
        return "REFUSÉ (store hors racine)"
    if isinstance(exc, PermissionError):  # (9)
        return "REFUSÉ (état machine non inscriptible)"
    if isinstance(exc, (NotADirectoryError, FileExistsError)):  # (10)
        return "REFUSÉ (chemin d'état occupé par un fichier)"
    if isinstance(exc, sqlite3.DatabaseError):
        code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(code, int):
            primaire = code & 0xFF
            if primaire == 26:  # SQLITE_NOTADB
                return "REFUSÉ (store non SQLite)"
            if primaire == 5:  # SQLITE_BUSY
                return "REFUSÉ (store verrouillé)"
            if primaire == 8 and code != 1032:  # SQLITE_READONLY (1544 compris ; 1032 DBMOVED remonte)
                return "REFUSÉ (store en lecture seule)"
            if primaire == 11:  # SQLITE_CORRUPT
                return "REFUSÉ (store corrompu)"
    return None


#: T-01M5BXTGX5YN8XEXTG1PP7A5ZX (phase B) — OÙ vit `agentic_v3` : le RÉSOLVEUR `vendor_paths.py`, frère de la
#: façade, chargé PAR CHEMIN quand cette partie s'exécute (le `__file__` est alors celui de la façade chargée ; un
#: `__file__` patché ensuite par un banc désigne une RACINE, jamais un autre résolveur). Nom PARTAGÉ avec
#: `record_id.py`, `event_store.py` et `migrate_index_to_db.py`, relu seulement s'il vient du fichier ATTENDU.
#: Résolveur ABSENT (copie partielle de `.agents/bin`) ou INCOMPLET (un nom de `_API_RESOLVEUR_V3` manque : fichier
#: vide, tronqué, d'une autre version) : aucun pont ne se construit, l'outbox est gardée et DITE — le pont est
#: refusé, jamais le verbe (un `AttributeError` le refuserait).
_NOM_RESOLVEUR_V3 = "_cadre_vendor_paths_bin"
_API_RESOLVEUR_V3 = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _charger_resolveur_v3() -> Any:
    """`vendor_paths.py` à côté de la façade, ou `None` s'il manque ; enregistré avant `exec_module`, retiré (ou la
    copie d'avant rendue) si l'exécution lève ; `_resolveur_lisible_v3` traite cette levée comme un résolveur
    ABSENT (le pont refusé, la façade chargée)."""
    import importlib.util

    chemin = Path(__file__).resolve().with_name("vendor_paths.py")
    existant = sys.modules.get(_NOM_RESOLVEUR_V3)
    fichier = getattr(existant, "__file__", None)
    if existant is not None and fichier and Path(fichier).resolve() == chemin:
        return existant
    if not chemin.is_file():
        return None
    spec = importlib.util.spec_from_file_location(_NOM_RESOLVEUR_V3, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NOM_RESOLVEUR_V3] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if existant is not None:
            sys.modules[_NOM_RESOLVEUR_V3] = existant
        else:
            sys.modules.pop(_NOM_RESOLVEUR_V3, None)
        raise
    return module


def _resolveur_complet_v3(module: Any) -> tuple[Any, str | None]:
    """`(module, None)` si le résolveur porte toute `_API_RESOLVEUR_V3`, sinon `(None, cause)` : absent et
    incomplet sont traités pareil, la cause les distingue (dite au déversement sans pont)."""
    if module is None:
        return None, f"résolveur vendor_paths.py absent de {Path(__file__).resolve().parent}"
    manques = [nom for nom in _API_RESOLVEUR_V3 if not hasattr(module, nom)]
    if manques:
        return None, f"résolveur vendor_paths.py incomplet : {', '.join(manques)}"
    return module, None


def _resolveur_lisible_v3() -> tuple[Any, str | None]:
    """Comme `_resolveur_complet_v3`, mais un résolveur qui LÈVE à l'exécution (tronqué en pleine instruction :
    `SyntaxError`) compte aussi comme ABSENT, cause « illisible » : le pont est refusé, jamais le verbe."""
    try:
        return _resolveur_complet_v3(_charger_resolveur_v3())
    except Exception as exc:  # `_charger_resolveur_v3` a déjà rendu `sys.modules` dans son état d'avant
        return None, f"résolveur vendor_paths.py illisible : {type(exc).__name__}"


_RESOLVEUR_V3, _CAUSE_SANS_RESOLVEUR_V3 = _resolveur_lisible_v3()


def _importer_pont_v3(repository_root: Path) -> Any:
    """`BoardBridge` du paquet `agentic_v3` que le RÉSOLVEUR désigne sous `repository_root` (`.agents/vendor` gagne
    sur l'ancien emplacement). Le parent passe sur `sys.path` par `amorcer_cli` — retiré puis replacé derrière la
    bibliothèque standard, jamais devant `.agents/bin` —, jamais par un `insert(0)` à la main. Paquet PAS ENCORE
    chargé : chargé PAR CHEMIN EXACT (`__init__.py` du dossier résolu, sous son nom canonique, enregistré avant
    `exec_module`), une racine sur `sys.path` ou le dossier courant ne choisit donc pas l'arbre. Déjà chargé (le
    conftest racine sous pytest, un autre appelant) : `verifier_charge` le compare au dossier résolu et lève
    `ProvenanceRefusee` s'il vient d'ailleurs, AVANT qu'aucun sous-module ne s'exécute. Masqué (`None` dans
    `sys.modules`) : `ModuleNotFoundError` au nom du paquet, comme l'import qu'il remplace."""
    resolveur = _RESOLVEUR_V3
    dossier = resolveur.exiger(repository_root, "agentic_v3")
    resolveur.amorcer_cli(repository_root, ("agentic_v3",))
    if "agentic_v3" in sys.modules and sys.modules["agentic_v3"] is None:
        raise ModuleNotFoundError("import of agentic_v3 halted; None in sys.modules", name="agentic_v3")
    if "agentic_v3" not in sys.modules:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "agentic_v3", dossier / "__init__.py", submodule_search_locations=[str(dossier)])
        paquet = importlib.util.module_from_spec(spec)
        sys.modules["agentic_v3"] = paquet
        try:
            spec.loader.exec_module(paquet)
        except BaseException:
            sys.modules.pop("agentic_v3", None)
            raise
    resolveur.verifier_charge(repository_root, "agentic_v3")
    from agentic_v3.reconciliation.board_bridge import BoardBridge

    return BoardBridge


def _refuser_provenance_v3(
    root: str | os.PathLike[str],
    repository_root: Path,
    pont_commande: dict[str, Any] | None,
    exc: BaseException,
) -> int:
    """`ProvenanceRefusee` : l'`agentic_v3` chargé n'est pas celui que le résolveur désigne. REFUSER LE PONT, PAS LE
    VERBE (T-012) : la même annonce que les refus de construction, mémorisée (`replay-sync` rend 1), raison
    `pont-v3-refuse` ; les intents restent dans l'outbox, déversés au seuil par le drain suivant de la commande."""
    explicite = pont_commande is not None and pont_commande.get("explicite")
    en_attente = (
        "REFUSÉ (ProvenanceRefusee : agentic_v3 chargé d'un autre arbre que celui du résolveur)",
        "rien n'est rejoué, événements conservés dans l'outbox" if explicite
        else "board écrit sans relecture V3, événements board conservés dans l'outbox",
        _aplatir_exc(exc),
    )
    if pont_commande is None:
        _annoncer_refus_pont({"annonce": en_attente})
        return 0
    if pont_commande.get("differer"):
        pont_commande["annonce"] = en_attente  # dite par `main` APRÈS le verbe (T-00001007)
    else:
        _annoncer_refus_pont({"annonce": en_attente})
    pont_commande.update(refus=True)
    _signaler_degradation_v3(root, repository_root, pont_commande, "pont-v3-refuse")
    return 0


def _annoncer_refus_pont(pont: dict[str, Any], issue: str | None = None) -> None:
    """Imprime puis RETIRE l'annonce d'un refus du pont mise en attente (`pont["annonce"]`) : telle quelle si le verbe
    a abouti (`issue` nul), sinon sa suite remplacée par `issue` (T-00001007, point g de T-00000792). Rien en attente :
    rien. `main` pose `differer` pour un verbe mutant ; tout autre appelant de `replay_sync` reçoit la ligne aussitôt."""
    attente = pont.pop("annonce", None)
    if attente is not None:
        annonce, suite, cause = attente
        print(f"TASKS: pont V3 {annonce}, {issue or suite} — {cause}", file=sys.stderr)


def replay_sync(
    root: str | os.PathLike[str],
    *,
    pont_commande: dict[str, Any] | None = None,
) -> int:
    """Drain through the optional V3 bridge; standalone kit users stay valid.

    `pont_commande` — UN pont par COMMANDE (T-00000695/696) : `main` draine avant
    ET après chaque verbe mutant, et chaque drain reconstruisait `BoardBridge` ->
    `EventStore` -> rejeu des journaux d'attente : une panne sortait DEUX fois par
    commande (mesuré, `.git/config` cassé). Le mémo retient une construction
    RÉUSSIE (`bridge`) ou, depuis T-00000782, un pont REFUSÉ ou en PANNE (`refus`),
    que le second drain ne retente PAS : une annonce par commande. Déplacé, dit :
    les journaux d'un export raté au premier drain sont rejoués à la commande
    suivante, dans les mêmes conditions. Un saut (racine non résolue) n'est pas
    mémorisé sur un verbe mutant — le verbe crée `.agents/`, le second drain résout
    et miroite (décision pilote S-00003321) ; sous `replay-sync` (`explicite`) il
    l'est, et `main` rend 1 (T-00001004). Une levée non classée remonte. `None`
    (défaut, appelants directs) : aucun mémo, ni lu ni écrit — chaque appel
    reconstruit, et annonce.

    Sous refus du pont (T-00001006) : au retour mémo, au-delà de `_SYNC_OUTBOX_SEUIL` intents, les plus anciens
    sont déversés hors du board suivi, dans un fichier local non versionné (`.agents/state/local/`), et rejoués
    EN TÊTE, dans l'ordre, au premier drain dont le pont se construit. Rien n'est supprimé. Chaque refus émet aussi
    `gate.coverage_degraded` (board du dépôt, ou `AGENTS_EVENTS_DIR` posé). Un fichier qui ne se rejoue pas arrête
    tout drain (l'ordre FIFO l'exige) : `replay-sync` rend 1, un verbe mutant n'est pas gelé.

    Drain en ÉCHEC, le pont construit (T-00001053) : la cause remonte par `echec` ; sous `replay-sync` UNE ligne
    « drain V3 en ECHEC » la nomme et `main` rend 1 ; un verbe mutant rend 0. Le drain a déjà ramené l'outbox au
    seuil (`drain_sync_outbox`). Après une attente de verrou d'écrivain (code 5), le mémo saute le drain d'après le
    verbe : UNE attente de 30 s par commande, et l'intent du verbe attend la commande suivante.

    Sans `agentic_v3` (T-00001052) : même déversement, aux deux sorties « kit seul » ; aucun pont ne se
    construit, donc le fichier n'est ni rejoué ni vidé tant qu'`agentic_v3` n'est pas installé."""
    repository_root = Path(__file__).resolve().parents[2]
    if pont_commande is not None and (pont_commande.get("refus") or pont_commande.get("echec_attente")):
        _deverser_excedent(  # T-00001006 : au-delà du seuil, hors du board, rien de perdu
            root,
            signaler=lambda raison: _signaler_degradation_v3(root, repository_root, pont_commande, raison),
        )
        return 0  # refus (T-00000782) ou attente de verrou déjà payée (T-00001053), annoncés par CETTE commande
    if _RESOLVEUR_V3 is None:  # copie partielle de `.agents/bin`, ou résolveur incomplet : rien ne dit où est le paquet
        _deverser_sans_pont(root, repository_root, pont_commande, cause=_CAUSE_SANS_RESOLVEUR_V3)
        return 0
    if _RESOLVEUR_V3.resoudre(repository_root, "agentic_v3") is None:
        _deverser_sans_pont(root, repository_root, pont_commande)  # T-00001052, les DEUX emplacements vides
        return 0
    try:
        BoardBridge = _importer_pont_v3(repository_root)
    except ModuleNotFoundError as exc:
        if exc.name is None or not exc.name.startswith("agentic_v3"):
            raise
        _deverser_sans_pont(root, repository_root, pont_commande,  # T-00001052
                            cause=f"paquet incomplet : {_aplatir_exc(exc)}")
        return 0
    except _RESOLVEUR_V3.ProvenanceRefusee as exc:
        return _refuser_provenance_v3(root, repository_root, pont_commande, exc)
    # T-00000650/677 : la base du run vit HORS dépôt ; `db_path` laissé à défaut est
    # résolu PARESSEUSEMENT par `BoardBridge.__init__` vers `DEFAULT_DB_PATH(root)`
    # (un littéral oublié ne lève pas, il RECRÉE une base VIDE).
    # REFUSER LE PONT PLUTÔT QUE LE VERBE (T-012 ; étendu et déplacé de `main` par
    # T-00000782). Le `try` entoure la SEULE construction du pont : le board s'écrit
    # hors de lui, une panne d'ÉCRITURE du board n'est jamais masquée. Sélection par
    # TYPE RÉEL, jamais par nom (CONSTAT 4). Ensemble attrapé : (1) `CadrePathError`
    # — racine non résolue (`--root` temporaire au tout premier `new`) : saut
    # annoncé, non mémorisé sur un verbe mutant, mémorisé sous `replay-sync` ; (2)
    # `SchemaVersionError` — store écrit par un binaire plus récent ; (3)
    # `EmplacementRefuse` — lien, second nom, non régulier, `:memory:`, nom changé…
    # (`cadre/ledger/store.py`) ; (4) `PanneInfrastructure` — couture
    # `cadre.ledger.store` indisponible ; (5)-(12), T-00001004 et T-00001056, par
    # `_annonce_refus_construction` : `OuvertureImpossible`, `HorsRacine`, store non
    # SQLite (code 26), verrou tenu (code 5, APRÈS les 30 s d'attente : le refus ne
    # raccourcit pas cette attente, le mémo en évite une deuxième) ; depuis
    # T-00001056, `PermissionError` (partition d'état ou `run/` non inscriptible),
    # `NotADirectoryError` et `FileExistsError` (un fichier à leur place), store en
    # lecture seule (code 8, dont 1544 sur `run/` ; 1032 remonte) et store corrompu
    # (code 11, le store n'est pas réécrit). Ce refus ne vaut QU'À LA CONSTRUCTION
    # (verrou `locking_mode=EXCLUSIVE`, dossier `run/` en lecture seule) : un verrou
    # d'ÉCRIVAIN en WAL ou un FICHIER de store en lecture seule la laissent passer et
    # frappent AU DRAIN (voir RÉSIDUS).
    # (2)-(12) : UNE ligne stderr, `refus` mémorisé, rend 0, événements gardés dans
    # l'outbox. (5)-(12) sont classés
    # AVANT (4), pour que la couture masquée de T3 traverse aussi le classeur. TOUT LE
    # RESTE REMONTE, dont la `ValueError` nue de `get_db_connection` (store absent)
    # qu'un `except ValueError` avalerait, et toute autre `OSError` (disque plein,
    # E/S). (3) est prise PAR LA COUTURE, À REBOURS du docstring
    # d'`EmplacementRefuse` (`cadre/ledger/store.py` : « les sites hors paquet attrapent ValueError, JAMAIS cette
    # classe » : deux copies du module peuvent coexister) : la classe levée ici vient
    # de `schema.create_tables`, qui passe par la MÊME couture mémoïsée
    # (`run_export._couture_ledger_store`, `_MODULES_CADRE`) — même objet-classe,
    # `isinstance` VRAI mesuré (lien symbolique et physique ; copie par chemin ET
    # `PYTHONPATH=src`) ; paquet `cadre` pip-installé NON MESURÉ. Couture
    # indisponible -> `()`, jamais un avalage : retombe en (4).
    # RÉSIDUS, mesurés par le vrai canal (T-00001004, T-00001056) : AU DRAIN, pont
    # construit, un verrou d'écrivain en WAL (code 5 : le drain qui écrit attend 30 s ;
    # une seule attente par commande depuis T-00001053, qui ne draine pas une seconde
    # fois après une attente de verrou — 61 à 65 s avaient été mesurés pour deux) et un
    # FICHIER de store en lecture seule (code 8) sont NOMMÉS par `drain_sync_outbox` ;
    # le verbe rend 0, l'intent reste dans l'outbox (au-delà de 200, au déversement),
    # et `replay-sync` rend 1 sur la ligne « drain V3 en ECHEC » qui nomme la cause. Une
    # `IntegrityError` du rejeu des journaux d'attente n'atteint pas le pont : le
    # rejeu l'absorbe. La `ValueError` nue (store disparu entre deux ouvertures, une
    # course) REMONTE et gèle encore le verbe.
    # Et la dégradation part AUSSI par `gate.coverage_degraded` (T-00001006),
    # relayée par le dashboard, non par `/night` ni par les hooks (R12).
    bridge = pont_commande.get("bridge") if pont_commande is not None else None
    if bridge is None:
        try:
            bridge = BoardBridge(project_root=root)
        except Exception as exc:  # borné juste après par TYPE réel, jamais par nom
            cadre_path_error = _classe_cadre_path_error()
            if cadre_path_error is not None and isinstance(exc, cadre_path_error):
                # (1) Annoncé, jamais muet. La racine ne porte aucun `.agents/` (sinon
                # elle se résoudrait), donc AUCUN board ni outbox : rien n'est différé.
                # Sous `replay-sync` (T-00001004, point j) : rien n'est rejoué, et le
                # refus est MÉMORISÉ pour que `main` rende 1 au lieu de « replayed 0 ».
                # Verbe mutant : saut NON mémorisé (S-00003321) — s'il aboutit, le verbe
                # a créé `.agents/` et le drain d'après résout (mesuré : `new` -> outbox
                # 0, T12) ; un verbe refusé (`BoardError`, rc 2) n'a pas de drain d'après.
                explicite = pont_commande is not None and pont_commande.get("explicite")
                suite = ("rien n'est rejoué, aucun board sous cette racine" if explicite
                         else "rien a rejouer avant le verbe ; si le verbe aboutit, le "
                              "drain d'apres reessaie")
                print(
                    "tasks.py: miroir V3 saute — racine du run non resolue "
                    f"(base machine hors depot indisponible), {suite} : {_aplatir_exc(exc)}",
                    file=sys.stderr,
                )
                if explicite and pont_commande is not None:
                    # HORS de la queue commune, graphie DISTINCTE de son littéral : ce
                    # saut n'est pas un refus de pont (T-00001006 s'ancre sur la queue).
                    pont_commande.update(refus=True)
                return 0
            try:
                from agentic_v3.db.schema import SchemaVersionError as refus_version
            except Exception:  # défensif : le pont vient d'importer ce module
                refus_version = ()
            refus_emplacement = _classe_emplacement_refuse()  # couture indisponible : `()`, classée en (4)
            if isinstance(exc, refus_version):
                annonce, suite = ("REFUSÉ (store plus récent que ce binaire)",
                                  "board écrit sans relecture V3")
            elif isinstance(exc, refus_emplacement):
                annonce = ("REFUSÉ (emplacement du store refusé — lien, second nom, non "
                           "régulier ou autre, cause exacte en fin de ligne)")
                suite = "board écrit sans relecture V3, événements board différés dans l'outbox"
            elif (refus_construction := _annonce_refus_construction(exc)) is not None:
                annonce = refus_construction  # (5)-(12), AVANT (4) : voir plus haut
                suite = "board écrit sans relecture V3, événements board différés dans l'outbox"
            elif _est_panne_infrastructure(exc):
                annonce = "en PANNE, miroir BLOQUÉ jusqu'à réparation"
                suite = "board écrit, intents conservés dans l'outbox"
            else:
                raise
            if pont_commande is not None and pont_commande.get("explicite"):  # `replay-sync`
                suite = "rien n'est rejoué, événements conservés dans l'outbox"
            en_attente = (annonce, suite, _aplatir_exc(exc))
            if pont_commande is not None and pont_commande.get("differer"):
                pont_commande["annonce"] = en_attente  # T-00001007 : dite par `main` APRÈS le verbe
            else:
                _annoncer_refus_pont({"annonce": en_attente})
            if pont_commande is not None:
                pont_commande["refus"] = True
                _signaler_degradation_v3(
                    root, repository_root, pont_commande,
                    "pont-v3-panne" if _est_panne_infrastructure(exc) else "pont-v3-refuse",
                )
            return 0
        if pont_commande is not None:
            pont_commande["bridge"] = bridge
    echec: dict[str, Any] = {}
    try:
        rejoues = drain_sync_outbox(
            root, bridge.consume_board_intent, echec=echec,
            signaler=lambda raison: _signaler_degradation_v3(root, repository_root, pont_commande, raison),
        )
    except DeverseIllisible:
        if pont_commande is not None and pont_commande.get("explicite"):
            pont_commande.update(refus=True)  # `replay-sync` rend 1 ; un verbe mutant ne mémorise rien (graphie distincte)
        _signaler_degradation_v3(root, repository_root, pont_commande, "sync-outbox-rejeu-impossible")
        return 0  # annoncé par le drain : le verbe n'est pas gelé, rien n'est rejoué
    if echec and pont_commande is not None:  # T-00001053 : refuser le pont, pas le verbe — un verbe mutant rend 0
        if echec.get("attente"):
            pont_commande["echec_attente"] = True  # UNE attente de 30 s par commande (S-00003429)
        if pont_commande.get("explicite"):
            print(f"TASKS: replay-sync — drain V3 en ECHEC apres {rejoues} intent(s) rejoue(s), le reste est "
                  f"conserve (outbox ou deversement) : {echec['cause']}", file=sys.stderr)
            pont_commande["refus"] = True  # `main` rend 1
    return rejoues
