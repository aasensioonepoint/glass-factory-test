# tasks_deversement.py — PARTIE de `tasks.py` (T-00000788), extraite de `tasks_sync.py` par T-00001071 : le
# DÉVERSEMENT de la sync_outbox hors du board suivi (T-00001006, S-00003315) et sa sortie « kit seul » (T-00001052).
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`, APRÈS `tasks_stockage.py` : `DeverseIllisible`
# lit `BoardError` à sa définition. Jamais importée seule : ses noms libres viennent de la façade et des autres parties.

from __future__ import annotations


_SYNC_OUTBOX_SEUIL = 200
#: T-01M4M175MY8RRRVFN7QRV48566 : au-delà de ce nombre d'intents à remettre en file, le drain n'en remet qu'une TRANCHE
#: de cette taille à la tête du board, le reste attend au fichier. INDÉPENDANTE du seuil (un banc qui l'abaisse à 3 ne
#: bascule pas dans les tranches) et au plus égale à lui (le board revient au seuil après chaque verbe). Lue À L'APPEL.
_TRANCHE_REINJECTION = 50
#: Le marqueur de tranche est lu par `_lire_plafonne` : au-delà de ces octets, il est illisible.
_PLAFOND_TRANCHE_OCTETS = 1024 * 1024
_ETATS_TRANCHE = ("prepare", "actif", "rendu")
#: Le NOM de trace qu'un marqueur peut porter : la forme que `_reinjecter_deverses` frappe (`<fichier>.rejoue-<ns>`),
#: en ASCII de nom de fichier seul (avis sécurité de l'Outbox, passe de correction F5) — `\n`, NUL, caractère de
#: contrôle, espace ou séparateur rendent le marqueur HORS FORME, jamais un `open` sur un nom forgé.
_NOM_TRACE = re.compile(r"\A[A-Za-z0-9._-]+\.rejoue-[0-9]+\Z", re.ASCII)
#: Plafond de LECTURE du fichier de déversement et de ses traces (même avis) : celui d'un lot de save (512 Mio) ;
#: au-delà, `DeverseIllisible` nommée, jamais une lecture sans fin. Lu À L'APPEL.
_PLAFOND_DEVERSE_OCTETS = 512 * 1024 * 1024


class DeverseIllisible(BoardError):
    """Le fichier de déversement ne se rejoue pas : rien n'est réinjecté, donc rien n'est drainé."""


def _lire_deverse(chemin: Path, fichier: Any) -> bytes:
    """Le contenu d'un fichier de déversement ou d'une trace OUVERT, borné à `_PLAFOND_DEVERSE_OCTETS` ; au-delà,
    `DeverseIllisible` qui nomme le fichier (une `BoardError` : chaque appelant la traite déjà)."""
    try:
        return _lire_plafonne(fichier, _PLAFOND_DEVERSE_OCTETS)
    except ValueError as exc:
        raise DeverseIllisible(f"{chemin} : {exc}") from exc


def _ouvrir_sans_lien(chemin: str, drapeaux: int) -> int:
    """Ouvre le fichier de déversement sans suivre un lien FINAL (`O_NOFOLLOW`) ni attendre un écrivain
    (`O_NONBLOCK`), puis exige un fichier régulier par `S_ISREG` sur le descripteur OUVERT (T-00001081). Sinon,
    FIFO, périphérique ou dossier : `OSError`, que chaque appelant traite déjà (`_deverser_excedent` garde ses
    intents au board, `_reinjecter_deverses` lève `DeverseIllisible` sans renommer). Mesuré : sans `O_NONBLOCK`,
    `open("rb")` sur une FIFO sans écrivain reste pendu ; sur un fichier régulier, `O_NONBLOCK` ne change rien.
    Borne Windows : `O_NOFOLLOW` et `O_NONBLOCK` n'y existent pas (`getattr` rend 0), donc un lien posé à la place
    du fichier y est suivi, et `S_ISREG` ne le refuse que si sa cible n'est pas un fichier régulier. Partout,
    `O_NOFOLLOW` ne tient que le DERNIER composant du chemin : un dossier parent remplacé par un lien est encore
    traversé (mesuré)."""
    import stat

    fd = os.open(chemin, drapeaux | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise OSError(f"pas un fichier régulier ({stat.filemode(mode)}), refusé sans l'attendre : {chemin}")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _chemin_deverse(root: str | os.PathLike[str]) -> Path:
    """`.agents/state/local/sync_outbox_deverse.jsonl` : à côté de `TASKS.lock`, adressé par `lock_path` comme le
    verrou lui-même. Le dossier est git-ignoré (non versionné, S-00003315) et suit le dépôt qu'on renomme ou qu'on
    copie ; il ne suit pas un clone. Créé par `board_lock`, que `_deverser_excedent` tient avant d'y écrire."""
    return lock_path(root).with_name("sync_outbox_deverse.jsonl")


def _chemin_tranche(root: str | os.PathLike[str]) -> Path:
    """`.agents/state/local/sync_outbox_deverse.tranche` (T-01M4M175MY8RRRVFN7QRV48566) : le MARQUEUR LOCAL d'une tranche
    remise en file, à côté du fichier de déversement, git-ignoré comme lui (relu par `git check-ignore`). Un objet
    `{"etat", "ops", "trace"}` : `prepare` (posé avant le `save` de la tranche), `actif` (la tranche est au board, le
    reste au fichier), `rendu` (sa restitution est commencée) ; `ops`, les `operation_id` de la tranche dans l'ordre ;
    `trace`, le NOM de sa trace `.rejoue-<ns>`, dans le même dossier."""
    return lock_path(root).with_name("sync_outbox_deverse.tranche")


def _lire_tranche(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Le marqueur de tranche, ou `None` s'il n'existe pas. Ouvert comme le fichier de déversement
    (`_ouvrir_sans_lien`), lu par `_lire_plafonne` ; illisible ou hors forme ⇒ `DeverseIllisible`, qui le nomme.
    Ouvert SANS test d'existence préalable : son absence est le `FileNotFoundError` de l'ouverture même."""
    chemin = _chemin_tranche(root)
    try:
        with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
            marqueur = json.loads(_lire_plafonne(fichier, _PLAFOND_TRANCHE_OCTETS).decode("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError) as exc:  # UnicodeDecodeError et JSONDecodeError : des ValueError
        raise DeverseIllisible(f"{chemin} : marqueur de tranche illisible : {exc}") from exc
    if not (isinstance(marqueur, dict) and set(marqueur) == {"etat", "ops", "trace"}
            and marqueur["etat"] in _ETATS_TRANCHE and isinstance(marqueur["ops"], list) and marqueur["ops"]
            and all(isinstance(op, str) for op in marqueur["ops"])
            and isinstance(marqueur["trace"], str) and _NOM_TRACE.match(marqueur["trace"])):
        raise DeverseIllisible(f"{chemin} : marqueur de tranche hors forme")
    return marqueur


def _substituer(cible: Path, octets: bytes, temporaire: Path) -> None:
    """`cible` ← `octets`, jamais à moitié écrit : `temporaire` créé `xb` par `_ouvrir_sans_lien`, `fsync`é, substitué
    par `_replace_with_retry`, puis le dossier `fsync`é. Un échec avant la substitution ne laisse pas le temporaire."""
    cree = False
    try:
        with open(temporaire, "xb", opener=_ouvrir_sans_lien) as fichier:
            cree = True
            fichier.write(octets)
            fichier.flush()
            os.fsync(fichier.fileno())
        _replace_with_retry(temporaire, cible)
    except BaseException:
        if cree:
            try:
                os.unlink(temporaire)
            except OSError:
                pass
        raise
    _fsync_dossier(cible.parent)


def _poser_tranche(root: str | os.PathLike[str], etat: str, ops: list[str], trace: str) -> None:
    chemin = _chemin_tranche(root)
    octets = (json.dumps({"etat": etat, "ops": ops, "trace": trace}, ensure_ascii=False, sort_keys=True) + "\n")
    _substituer(chemin, octets.encode("utf-8"), chemin.with_name(f"{chemin.name}.ecrit-{time.time_ns()}"))


def _enlever_tranche(root: str | os.PathLike[str]) -> None:
    chemin = _chemin_tranche(root)
    os.unlink(chemin)
    _fsync_dossier(chemin.parent)


def _lignes_du_fichier(chemin: Path) -> tuple[list[bytes], bytes]:
    """Les lignes complètes de `chemin` et son segment final non terminé ; rien s'il n'existe pas."""
    if not os.path.lexists(chemin):
        return [], b""
    with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
        *lignes, queue = _lire_deverse(chemin, fichier).split(b"\n")
    return lignes, queue


def _ops_des_lignes(lignes: list[bytes]) -> list[str | None]:
    """L'`operation_id` de chaque ligne, `None` pour une ligne qui n'en porte pas un textuel."""
    ops: list[str | None] = []
    for ligne in lignes:
        try:
            op = json.loads(ligne)["operation_id"]
        except (ValueError, KeyError, TypeError, RecursionError):
            op = None
        ops.append(op if isinstance(op, str) else None)
    return ops


def _creer_trace(trace: Path, octets: bytes) -> None:
    with open(trace, "xb", opener=_ouvrir_sans_lien) as fichier:
        fichier.write(octets)
        fichier.flush()
        os.fsync(fichier.fileno())
    _fsync_dossier(trace.parent)


def _reprendre_tranche(root: str | os.PathLike[str], chemin: Path) -> bool:
    """LA REPRISE du marqueur de tranche (T-01M4M175MY8RRRVFN7QRV48566), sous le `board_lock` que l'appelant tient,
    idempotente ; « la tranche au board » = au moins un de ses ops dans `sync_outbox` :
    `prepare` sans elle au board — son `save` n'a pas eu lieu, rien n'a pu être livré : marqueur enlevé, fichier INTACT
    (l'achever perdrait la tranche) ; `prepare` avec elle — achevée : trace des lignes jusqu'à sa dernière si la trace
    manque, fichier ← la suite (une ligne déversée depuis y reste), marqueur `actif` ; `actif` avec elle — en vol ;
    `actif` sans elle — livrée, marqueur enlevé ; `rendu` avec elle — la restitution est achevée (`_rendre_tranche`) ;
    `rendu` sans elle — marqueur enlevé. Rend VRAI quand une tranche est en vol : rien d'autre ne se remet en file."""
    marqueur = _lire_tranche(root)
    if marqueur is None:
        return False
    data = load(root)
    _ensure_sync_extensions(data)
    ops = set(marqueur["ops"])
    if not any(intent["operation_id"] in ops for intent in data["sync_outbox"]):
        _enlever_tranche(root)
        return False
    if marqueur["etat"] == "actif":
        return True
    if marqueur["etat"] == "rendu":
        _rendre_tranche(root, chemin, marqueur, data)
        return False
    lignes, queue = _lignes_du_fichier(chemin)
    rangs = [rang for rang, op in enumerate(_ops_des_lignes(lignes)) if op in ops]
    if rangs:  # arrêt avant (4) : refaire (3) si la trace manque, puis (4)
        coupe = rangs[-1] + 1
        trace = chemin.with_name(marqueur["trace"])
        if not os.path.lexists(trace):
            _creer_trace(trace, b"".join(ligne + b"\n" for ligne in lignes[:coupe]))
        _substituer(chemin, b"".join(ligne + b"\n" for ligne in lignes[coupe:]) + queue,
                    chemin.with_name(f"{chemin.name}.reste-{time.time_ns()}"))
    _poser_tranche(root, "actif", marqueur["ops"], marqueur["trace"])
    return True


def _rendre_tranche(root: str | os.PathLike[str], chemin: Path, marqueur: dict[str, Any], data: dict[str, Any]) -> None:
    """(r1)-(r4) de la restitution d'une tranche, le marqueur déjà `rendu` (r0) et le verrou tenu : (r1) le fichier
    vivant ← la tranche RESTANTE (copies du BOARD, `attempt` compté, dans son ordre) PUIS ses octets actuels — sauf s'il
    commence déjà par elle (une reprise après (r1)) ; (r2) `save` du board sans elle ; (r3) la trace réduite à ses autres
    lignes (`_reduire_trace`) ; (r4) marqueur enlevé. Chaque intent est au fichier ou au board à chaque instant."""
    tranche = set(marqueur["ops"])
    par_op = {intent["operation_id"]: intent for intent in data["sync_outbox"] if intent["operation_id"] in tranche}
    restante = [op for op in marqueur["ops"] if op in par_op]
    lignes, queue = _lignes_du_fichier(chemin)
    if _ops_des_lignes(lignes[:len(restante)]) != restante:
        tete = b"".join(json.dumps(par_op[op], ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                        for op in restante)
        _substituer(chemin, tete + b"".join(ligne + b"\n" for ligne in lignes) + queue,
                    chemin.with_name(f"{chemin.name}.rendu-{time.time_ns()}"))
    data["sync_outbox"] = [intent for intent in data["sync_outbox"] if intent["operation_id"] not in par_op]
    save(root, data)
    _reduire_trace(chemin, chemin.with_name(marqueur["trace"]), set(restante))
    _enlever_tranche(root)


def _reduire_trace(chemin: Path, trace: Path, revenus: set[str]) -> None:
    """(r3) : la trace d'une tranche rendue garde ses lignes qui ne sont PAS revenues au fichier (livrées, ou écartées à
    la remise en file), par un temporaire `<fichier>.reduite-<ns>` (hors du motif `.rejoue-*`) ; vide, elle est enlevée.
    Absente : rien. Interrompue, illisible ou en échec : gardée pleine, une ligne stderr (doublons, aucune perte)."""
    if not os.path.lexists(trace):
        return
    try:
        lignes, queue = _lignes_du_fichier(trace)
        ops = _ops_des_lignes(lignes)
        if queue or None in ops:
            raise ValueError("segment final interrompu, ou ligne sans operation_id")
        gardees = b"".join(ligne + b"\n" for ligne, op in zip(lignes, ops) if op not in revenus)
        if gardees:
            _substituer(trace, gardees, chemin.with_name(f"{chemin.name}.reduite-{time.time_ns()}"))
        else:
            os.unlink(trace)
    except (BoardError, OSError, ValueError) as exc:
        print(f"TASKS: sync_outbox — trace {trace} NON réduite, gardée pleine (doublons, aucune perte) : {exc}",
              file=sys.stderr)


def _deverser_excedent(
    root: str | os.PathLike[str],
    chemin: Path | None = None,
    *,
    signaler: Callable[[str], None] | None = None,
) -> tuple[int, int, int] | None:
    """Ramène `sync_outbox` au seuil en DÉVERSANT ses intents les plus ANCIENS hors du board suivi, dans un
    fichier local non versionné ; rien n'est supprimé (S-00003315). Appelable hors de la voie du refus, avec
    un `chemin` fourni (S-00003330). Sous `board_lock` : ajout seul au fichier puis `fsync`, ENSUITE `save` du
    board sans eux ; un arrêt entre les deux laisse un doublon, que le rejeu écarte. Rien ne part tant que la
    tête est sous bail vivant. `signaler(raison)`, si fourni, reçoit `sync-outbox-deverse` après un déversement
    et `sync-outbox-deverse-impossible` après un échec. Rend (déversés, intents DISTINCTS en attente hors board,
    restants au board), ou `None` si rien n'est déversé.

    T-01M4M175MY8RRRVFN7QRV48566 : les intents de TÊTE dont l'op est dans le marqueur de tranche (tout état) sont
    ENJAMBÉS — la tranche est plus ancienne que le reste du fichier, elle reste en tête du board — et l'excédent part
    de ce qui les suit, la garde de bail portant sur le premier d'entre eux ; marqueur illisible ⇒ la ligne
    « déversement IMPOSSIBLE » ci-dessous. Sans marqueur, rien n'est enjambé : le déversement d'avant."""
    chemin = chemin if chemin is not None else _chemin_deverse(root)
    try:
        if len(load(root).get("sync_outbox") or []) <= _SYNC_OUTBOX_SEUIL:
            return None  # pré-contrôle SANS verrou : `save` est atomique
        with board_lock(root):
            data = load(root)
            _ensure_sync_extensions(data)
            outbox = data["sync_outbox"]
            marqueur = _lire_tranche(root)
            enjambes = set(marqueur["ops"]) if marqueur is not None else set()
            debut = 0
            while debut < len(outbox) and outbox[debut]["operation_id"] in enjambes:
                debut += 1
            nombre = min(len(outbox) - _SYNC_OUTBOX_SEUIL, len(outbox) - debut)
            bail = outbox[debut]["lease"] if debut < len(outbox) else None
            if nombre <= 0 or (bail is not None and float(bail["expires_at"]) > time.time()):
                return None
            lot = b"".join(
                json.dumps(intent, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                for intent in outbox[debut:debut + nombre]
            )
            chemin.parent.mkdir(parents=True, exist_ok=True)
            with open(chemin, "a+b", opener=_ouvrir_sans_lien) as fichier:
                fichier.seek(0)
                deja = _lire_deverse(chemin, fichier)
                garde = deja.rfind(b"\n") + 1
                if garde != len(deja):
                    fichier.truncate(garde)  # ajout interrompu avant le `save` : ses intents sont encore au board
                fichier.write(lot)
                fichier.flush()
                os.fsync(fichier.fileno())
            if os.name != "nt":  # l'entrée du dossier aussi : un fichier NÉ ici survit à une coupure avant le `save`
                dossier = os.open(chemin.parent, os.O_RDONLY)
                try:
                    os.fsync(dossier)
                finally:
                    os.close(dossier)
            distincts: set[Any] = set()
            for ligne in deja[:garde].split(b"\n")[:-1]:  # doublons d'un `fsync` en échec : comptés UNE fois
                try:
                    distincts.add(json.loads(ligne)["operation_id"])
                except (ValueError, KeyError, TypeError, RecursionError):  # trop imbriquée : pas une ValueError
                    distincts.add(ligne)  # illisible : une entrée à part, que le rejeu refusera
            distincts.update(intent["operation_id"] for intent in outbox[debut:debut + nombre])
            en_attente = len(distincts)
            data["sync_outbox"] = outbox[:debut] + outbox[debut + nombre:]
            save(root, data)
    except (BoardError, OSError) as exc:
        print(f"TASKS: sync_outbox — déversement IMPOSSIBLE, intents gardés au board : {exc}", file=sys.stderr)
        if signaler is not None:
            signaler("sync-outbox-deverse-impossible")
        return None
    restants = len(data["sync_outbox"])
    print(
        f"TASKS: sync_outbox AU SEUIL ({_SYNC_OUTBOX_SEUIL}) — {nombre} intent(s) déversé(s) hors du board vers "
        f"{chemin}, {en_attente} en attente d'un pont, {restants} au board ; rien n'est supprimé — rejoués dans "
        "l'ordre PAR CE POSTE à la reconstruction du pont (fichier local .agents/state/local/, non versionné, "
        "absent d'un clone)",
        file=sys.stderr,
    )
    if signaler is not None:
        signaler("sync-outbox-deverse")
    return nombre, en_attente, restants


def _reinjecter_deverses(
    root: str | os.PathLike[str], chemin: Path | None = None, *, rendu: dict[str, Any] | None = None
) -> int:
    """AVANT tout drain : les intents déversés repassent EN TÊTE de `sync_outbox`, dans leur ordre. Chaque
    déversement a pris la tête de l'outbox, donc « fichier puis board » EST l'ordre FIFO d'origine ; un déversement
    né PENDANT un drain vivant n'est pas dépassé, car `claim_sync_event` ne réserve rien tant que le fichier existe
    (T-00001006) : ce drain s'arrête, le suivant rejoue le fichier d'abord. Écartés :
    un `operation_id` déjà au board (arrêt entre l'ajout et le `save`, ou deux déversements du même intent), ou
    sans corrélation (déjà acquitté : arrêt entre ce `save` et le renommage). Validé COMME `load` avant le `save`
    (`save` ne valide pas les extensions : une ligne hors schéma rendrait le board illisible). `save`, PUIS le
    fichier est RENOMMÉ `<nom>.rejoue-<ns>`, une trace que seule `_restituer_deverse` réduit. Rend le nombre
    réinjecté ; lève `DeverseIllisible` si le fichier ne se relit pas ou ne se rejoue pas. `rendu`, si fourni
    (T-00001053), reçoit le fichier, sa trace et les `operation_id` réinjectés : de quoi les RESTITUER si le
    drain qui suit échoue.

    PAR TRANCHES (T-01M4M175MY8RRRVFN7QRV48566). `rendu` est VIDÉ en tête, avant toute reprise : une tranche déjà
    livrée n'est jamais restituée par l'échec d'une remise suivante. Sous le verrou, d'abord la REPRISE du marqueur
    (`_reprendre_tranche`) : une tranche en vol ⇒ 0, `rendu` vide (elle n'est pas la nôtre). Au plus
    `_TRANCHE_REINJECTION` intents retenus ⇒ le chemin ci-dessus, inchangé, `rendu["tranche"]` faux. Au-delà, la
    tranche S = les K premiers retenus, dans CET ordre : (1) marqueur `prepare` ; (2) `save` du board S en tête ;
    (3) trace `.rejoue-<ns>` = les lignes lues jusqu'à la K-ième retenue (`xb`, `fsync`) ; (4) le fichier vivant ← les
    lignes suivantes, par un temporaire `<nom>.reste-<ns>` substitué (RÉÉCRIT, pas renommé) ; (5) marqueur `actif`.
    `rendu["tranche"]` vrai. À chaque instant chaque intent est au fichier OU au board (S aux deux de (2) à (4))."""
    chemin = chemin if chemin is not None else _chemin_deverse(root)
    if rendu is not None:
        rendu.clear()
    if not os.path.lexists(chemin) and not os.path.lexists(_chemin_tranche(root)):
        return 0
    with board_lock(root):
        if _reprendre_tranche(root, chemin):
            return 0  # une tranche est en vol : elle passe d'abord
        if not os.path.lexists(chemin):
            return 0  # rejoué par un autre drain entre le test sans verrou et le verrou
        try:
            with open(chemin, "rb", opener=_ouvrir_sans_lien) as fichier:
                *lignes, queue = _lire_deverse(chemin, fichier).split(b"\n")  # segment final non terminé : ajout interrompu
        except OSError as exc:
            raise DeverseIllisible(f"{chemin} : {exc}") from exc
        intents = []
        for numero, ligne in enumerate(lignes, 1):
            try:
                intents.append(json.loads(ligne))
            except (ValueError, RecursionError) as exc:  # trop imbriquée : `RecursionError`, pas une ValueError
                raise DeverseIllisible(f"{chemin} : ligne {numero} illisible : {exc}") from exc
        if not all(isinstance(intent, dict) and isinstance(intent.get("operation_id"), str) for intent in intents):
            raise DeverseIllisible(f"{chemin} : ligne sans operation_id textuel")
        data = load(root)
        _ensure_sync_extensions(data)
        vus = {intent["operation_id"] for intent in data["sync_outbox"]}
        neufs = []
        rangs = []
        for rang, intent in enumerate(intents):
            if intent["operation_id"] in vus or intent["operation_id"] not in data["sync_correlations"]:
                continue
            vus.add(intent["operation_id"])
            neufs.append(intent)
            rangs.append(rang)
        taille = _TRANCHE_REINJECTION
        tranche = len(neufs) > taille
        remis = neufs[:taille] if tranche else neufs
        if remis:
            data["sync_outbox"] = remis + data["sync_outbox"]
            try:
                _validate_sync_extensions(store_path(root), data)
            except (BoardError, TypeError) as exc:
                raise DeverseIllisible(f"{chemin} : {exc}") from exc
        trace = chemin.with_name(f"{chemin.name}.rejoue-{time.time_ns()}")
        ops = [intent["operation_id"] for intent in remis]
        if tranche:
            coupe = rangs[taille - 1] + 1
            _poser_tranche(root, "prepare", ops, trace.name)
            save(root, data)
            _creer_trace(trace, b"".join(ligne + b"\n" for ligne in lignes[:coupe]))
            _substituer(chemin, b"".join(ligne + b"\n" for ligne in lignes[coupe:]) + queue,
                        chemin.with_name(f"{chemin.name}.reste-{time.time_ns()}"))
            _poser_tranche(root, "actif", ops, trace.name)
        else:
            if remis:
                save(root, data)
            _replace_with_retry(chemin, trace)
        if rendu is not None:  # T-00001053 : de quoi RESTITUER si le drain échoue
            rendu.update(chemin=chemin, trace=trace, ops=ops, tranche=tranche)
    if tranche:
        print(
            f"TASKS: sync_outbox — tranche de {taille} : {len(remis)} intent(s) déversé(s) réinjecté(s) en tête, "
            f"{coupe - taille} écarté(s) (déjà au board, ou sans corrélation), {len(lignes) - coupe} ligne(s) restant "
            f"au fichier {chemin}, réécrit ; rejoués dans l'ordre, la tranche suivante quand celle-ci est livrée",
            file=sys.stderr,
        )
        return len(remis)
    print(
        f"TASKS: sync_outbox — {len(neufs)} intent(s) déversé(s) réinjecté(s) en tête, "
        f"{len(intents) - len(neufs)} écarté(s) (déjà au board, ou sans corrélation), depuis {chemin} ; "
        "rejoués dans l'ordre",
        file=sys.stderr,
    )
    return len(neufs)


def _restituer_deverse(root: str | os.PathLike[str], rendu: dict[str, Any]) -> bool:
    """T-00001053 : un drain qui ÉCHOUE juste après une réinjection ne laisse pas une trace pleine par commande. Sous
    `board_lock`, les intents réinjectés ENCORE en attente retournent au fichier vivant — la copie du BOARD, dont
    `attempt` compte les échecs, une fois par `operation_id`, dans l'ordre de la trace — ouvert `xb` par
    `_ouvrir_sans_lien` puis `fsync` (fichier et dossier) D'ABORD ; ils quittent ENSUITE le board ; la trace est
    ENFIN réduite à ses autres lignes (livrées, ou écartées à la réinjection), par un temporaire
    `sync_outbox_deverse.jsonl.reduite-<ns>` (hors du motif `.rejoue-*`, ouvert comme le fichier vivant) substitué à la
    trace. Réduite à zéro ligne, la trace est retirée : chacune de ses lignes est alors dans le fichier vivant, écrite
    et `fsync`ée sous le même verrou. Chaque ligne est dans le fichier, la trace ou le board avant l'étape suivante ;
    une réduction en échec garde la trace PLEINE, le dit sur stderr et ne laisse pas le temporaire sur disque. Rend
    vrai quand il ne reste rien à restituer : restitution faite, rien de réinjecté, ou chaque intent repris déjà
    livré. Fichier déjà reparu, trace partie, bail vivant sur un intent repris, ligne illisible, segment final
    interrompu ou écriture en échec : rien n'est touché, retour FAUX, que `drain_sync_outbox` dit sur stderr ; le
    déversement d'après tranche comme avant (une trace pleine, jamais une perte).

    `rendu["tranche"]` vrai (T-01M4M175MY8RRRVFN7QRV48566) : `_restituer_tranche` — la tranche restante revient EN TÊTE
    du fichier vivant, qui existe par construction (la garde « fichier reparu » ne vaut qu'ici, hors tranche). Faux ou
    absent : ce protocole, y compris pour le reste final d'un déversement passé par des tranches."""
    ops = set(rendu.get("ops") or ())
    if not ops:
        return True  # rien de réinjecté : rien à restituer
    chemin, trace = rendu["chemin"], rendu["trace"]
    try:
        with board_lock(root):
            if rendu.get("tranche"):
                return _restituer_tranche(root, chemin, ops)
            if os.path.lexists(chemin) or not os.path.lexists(trace):
                return False
            data = load(root)
            _ensure_sync_extensions(data)
            maintenant = time.time()
            attente = [intent for intent in data["sync_outbox"] if intent["operation_id"] in ops]
            if not attente:
                return True  # chaque intent repris est livré : la trace ne porte que des livrés ou des écartés
            if any(i["lease"] is not None and float(i["lease"]["expires_at"]) > maintenant for i in attente):
                return False
            par_op = {intent["operation_id"]: intent for intent in attente}
            ids = set(par_op)
            with open(trace, "rb", opener=_ouvrir_sans_lien) as fichier:
                *lignes, queue = _lire_deverse(trace, fichier).split(b"\n")
            if queue:
                return False  # segment final interrompu : un doute, la trace reste pleine
            gardees, rejouees, ecrits = [], [], set()
            for ligne in lignes:
                try:
                    op = json.loads(ligne)["operation_id"]
                    garder = op in ids
                except (ValueError, KeyError, TypeError, RecursionError):
                    return False
                if not garder:
                    rejouees.append(ligne + b"\n")
                elif op not in ecrits:  # la copie du BOARD, pas les octets de la trace : son `attempt` a compté l'échec
                    ecrits.add(op)
                    gardees.append(json.dumps(par_op[op], ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n")
            with open(chemin, "xb", opener=_ouvrir_sans_lien) as fichier:
                fichier.write(b"".join(gardees))
                fichier.flush()
                os.fsync(fichier.fileno())
            if os.name != "nt":  # l'entrée du dossier aussi, comme `_deverser_excedent`
                dossier = os.open(chemin.parent, os.O_RDONLY)
                try:
                    os.fsync(dossier)
                finally:
                    os.close(dossier)
            data["sync_outbox"] = [intent for intent in data["sync_outbox"] if intent["operation_id"] not in ids]
            save(root, data)
            cree = None  # le temporaire, une fois créé ici et tant qu'il n'est pas substitué
            try:
                if rejouees:
                    reduite = chemin.with_name(f"{chemin.name}.reduite-{time.time_ns()}")
                    with open(reduite, "xb", opener=_ouvrir_sans_lien) as fichier:
                        cree = reduite
                        fichier.write(b"".join(rejouees))
                        fichier.flush()
                        os.fsync(fichier.fileno())
                    _replace_with_retry(reduite, trace)
                    cree = None
                else:
                    os.unlink(trace)
            except (BoardError, OSError) as exc:  # la trace reste PLEINE : des doublons du fichier, jamais une perte
                print(f"TASKS: sync_outbox — trace {trace} NON réduite, gardée pleine (doublons, aucune perte) : {exc}",
                      file=sys.stderr)
            finally:
                if cree is not None:  # pas d'orphelin `.reduite-<ns>` : aucun code ne le relit
                    try:
                        os.unlink(cree)
                    except OSError as exc:
                        print(f"TASKS: sync_outbox — temporaire {cree} laissé sur disque : {exc}", file=sys.stderr)
            return True
    except (BoardError, OSError):
        return False


def _restituer_tranche(root: str | os.PathLike[str], chemin: Path, ops: set[str]) -> bool:
    """La restitution d'une TRANCHE après un drain en échec, sous le verrou. Elle n'est la nôtre que si le marqueur est
    `actif` sur ces mêmes ops et que le fichier vivant existe ; sinon FAUX, rien touché. Gardes de la BASE : chaque op
    déjà livré ⇒ vrai, rien touché ; bail vivant sur l'un d'eux, trace absente, illisible ou interrompue ⇒ FAUX, rien
    touché, marqueur laissé `actif`. Puis (r0) marqueur `rendu` et (r1)-(r4) par `_rendre_tranche` : la tranche
    restante EN TÊTE du fichier, plus ancienne que son reste et que tout déversement survenu depuis."""
    marqueur = _lire_tranche(root)
    if marqueur is None or marqueur["etat"] != "actif" or set(marqueur["ops"]) != ops or not os.path.lexists(chemin):
        return False
    data = load(root)
    _ensure_sync_extensions(data)
    attente = [intent for intent in data["sync_outbox"] if intent["operation_id"] in ops]
    if not attente:
        return True
    maintenant = time.time()
    if any(i["lease"] is not None and float(i["lease"]["expires_at"]) > maintenant for i in attente):
        return False
    trace = chemin.with_name(marqueur["trace"])
    if not os.path.lexists(trace):
        return False
    lignes, queue = _lignes_du_fichier(trace)
    if queue or None in _ops_des_lignes(lignes):
        return False
    _poser_tranche(root, "rendu", marqueur["ops"], marqueur["trace"])
    _rendre_tranche(root, chemin, marqueur, data)
    return True


def _taille_deverse(chemin: Path) -> str:
    """Taille du fichier de déversement, en octets ; illisible, la cause : jamais une levée, le board est déjà sauvé."""
    try:
        return f"{chemin.stat().st_size} octets"
    except OSError as exc:
        return f"taille illisible : {exc}"


def _deverser_sans_pont(
    root: str | os.PathLike[str],
    repository_root: str | os.PathLike[str],
    pont_commande: dict[str, Any] | None,
    cause: str | None = None,
) -> None:
    """Kit sans `agentic_v3` (T-00001052) : aucun pont ne se construit, donc aucun drain. L'outbox est ramenée au
    seuil par le MÊME déversement que sous refus (S-00003315). Le fichier n'est rejoué qu'au premier drain dont le
    pont se construit : tant qu'`agentic_v3` manque, il n'est ni rejoué ni vidé, et sa taille est dite à chaque
    déversement. Un board illisible n'est pas un déversement manqué : le verbe l'annonce lui-même. `cause` posée
    (résolveur absent, incomplet ou illisible, paquet incomplet) : la ligne dit `agentic_v3 non chargé dans
    <racine> (<cause>)`, le paquet pouvant être sur le disque (T-01M5BXTGX5YN8XEXTG1PP7A5ZX) ; sans `cause`,
    aucun des DEUX emplacements du résolveur ne le porte, et la ligne garde sa forme d'avant, `absent de`."""
    try:
        if len(load(root).get("sync_outbox") or []) <= _SYNC_OUTBOX_SEUIL:
            return
    except (BoardError, OSError, ValueError):
        return
    if _deverser_excedent(
        root,
        signaler=lambda raison: _signaler_degradation_v3(root, repository_root, pont_commande, raison),
    ) is None:
        return
    chemin = _chemin_deverse(root)
    etat = f"non chargé dans {repository_root} ({cause})" if cause else f"absent de {repository_root}"
    print(
        f"TASKS: agentic_v3 {etat} "
        f"— aucun pont ne se construit ici : {chemin} n'est ni "
        f"rejoué ni vidé tant qu'agentic_v3 n'est pas installé ({_taille_deverse(chemin)})",
        file=sys.stderr,
    )
