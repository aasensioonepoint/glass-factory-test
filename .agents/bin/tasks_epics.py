# tasks_epics.py — PARTIE de `tasks.py` (T-00001043) : l'EPIC OPTIONNELLE —
# le registre racine `epics`, le champ `epic` d'une tâche, les verbes `epic-new`
# et `epic`, les lectures `epic-list` et `list --epic`, et la garde de plan au `done`.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.
#
# D1. Le registre est la clé racine `epics` de TASKS.json, une liste d'objets
# `{id, titre, vague?, priorite?, exclusive?, risque?}`, ÉCRITE seulement par un
# premier `epic-new` et lue par `epics_of` : un store sans epic garde sa forme
# exacte (aucun `setdefault` dans `load`, qui ne contrôle que la FORME).
# D2. Le champ `epic` d'une tâche est une chaîne `E-NN` ; ABSENT veut dire sans
# epic, comme `chantier`. `""` est refusé PARTOUT en écriture (on détache par
# `epic T-NNN --retirer`) ; en LECTURE, `list --epic ""` = les tâches sans epic.
# L'EPIC SE REND, ELLE NE SE STOCKE PAS DANS LE TITRE : `cell` pose `[E-NN]` en
# tête du titre dans les vues à largeur fixe ; `list --json` rend le titre brut
# et la clé `epic`. `retitle` et `new --epic` refusent donc un titre qui ouvre
# sur la propre epic de la tâche (R10) : stocké, le préfixe s'imprimerait deux fois.
# NON LIVRÉS, et dits : `epic-delete`, et le regroupement `--group` par epic.
# DETTE NOMMÉE : `epics` ajoute une collection à TASKS.json, que « état partagé
# fusionnable » (E-25, E-26) devra migrer avec le store.

from __future__ import annotations

EPIC_ID = re.compile(r"^E-\d{2,}$")
EPIC_PRIORITES = ("P0", "P1", "P2")
# Le préfixe tel que `cell` le rend, relu en tête d'un titre proposé (R10).
_EPIC_EN_TETE = re.compile(r"^\[(E-\d{2,})\]")
# GRAMMAIRE DE PLAN de la garde du `done` : `EPIC: T-<id> -> E-NN`, hors bloc de
# code, puce `- ` tolérée, mot-clé en MAJUSCULES seulement (comme `ARÊTE:`, W9 :
# `epic : …` reste de la prose). Une ligne qui ouvre sur le mot-clé sans suivre la
# forme est FAUTIVE ; une ligne PROCHE (indentée, autre puce, gras, citation) est
# nommée elle aussi, pour qu'une epic voulue ne soit jamais ignorée en silence.
_EPIC_MOT_CLE = re.compile(r"^(?:- )?EPICS? ?:")
# L'id de tâche : `T-<ULID>` EN PREMIER (T-00000726), puis l'ancien `T-<chiffres>`
# (T-00001040 ; témoins : `ReleveEpicUlidTests` de test_tasks_epics.py).
_EPIC_LIGNE = re.compile(
    r"^(?:- )?EPIC:[ \t]*(T-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{1,12}))[ \t]*->[ \t]*(E-\d{2,})[ \t]*$")
_EPIC_PROCHE = re.compile(r"EPICS?[ \t]*:")
_EPIC_PUCE = re.compile(r"(?:[-*+]|\d{1,3}[.)])[ \t]")
_EPIC_NUMERO = re.compile(r"^E-(\d+)$")


def epics_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Le registre, ou `[]` quand la clé est absente (store d'avant T-00001043)."""
    registre = data.get("epics") or []
    return [e for e in registre if isinstance(e, dict)]


def find_epic(data: dict[str, Any], eid: str) -> dict[str, Any] | None:
    """L'entrée du registre d'id EXACT `eid`, ou `None`."""
    return next((e for e in epics_of(data) if e.get("id") == eid), None)


def _cle_epic(entree: dict[str, Any]) -> tuple[int, int, str]:
    """Tri du registre PAR NUMÉRO (`E-9` avant `E-10`) ; un id hors forme, posé à
    la main et accepté par `load`, se range après, par texte."""
    eid = str(entree.get("id", ""))
    m = _EPIC_NUMERO.match(eid)
    return (0, int(m.group(1)), eid) if m else (1, 0, eid)


def epic_shape_refusal(data: dict[str, Any]) -> str | None:
    """PRÉSENCE ET FORME SEULEMENT, appelée UNE fois par `load` après la boucle
    des tâches. LE RÉFÉRENT N'EST PAS EXIGÉ : une tâche peut porter une epic
    absente du registre (même règle que `blocked_on`) — un store accepté hier
    reste lisible, et `epic-list` la montre « hors registre ». `epics` absent est
    accepté ; présent, c'est une liste d'objets à `id` chaîne non vide et unique
    (`titre` chaîne s'il est là). L'`epic` d'une tâche est une chaîne non vide."""
    if "epics" in data:
        registre = data["epics"]
        if not isinstance(registre, list):
            return f"epics must be a list of objects, not {type(registre).__name__}"
        vus: set[str] = set()
        for i, entree in enumerate(registre):
            if not isinstance(entree, dict):
                return f"epics[{i}] is not an object"
            eid = entree.get("id")
            if not isinstance(eid, str) or not eid:
                return f"epics[{i}] has no id ({eid!r}); expected a non-empty string"
            if eid in vus:
                return f"epics: duplicate id {eid}"
            vus.add(eid)
            if "titre" in entree and not isinstance(entree["titre"], str):
                return f"epics[{i}] ({eid}) has a non-string titre ({entree['titre']!r})"
    for task in data.get("tasks", []):
        if "epic" in task and (not isinstance(task["epic"], str) or not task["epic"]):
            return (
                f"task {task.get('id')} has an invalid epic ({task['epic']!r}); "
                f"expected a non-empty E-NN string (absent = no epic)"
            )
    return None


def epic_title_refusal(title: str, epic: str | None) -> str | None:
    """R10 : un titre qui OUVRE sur `[<epic de la tâche>]` est refusé, jamais
    normalisé en silence. `cell` rend ce préfixe depuis le champ ; stocké, il
    s'imprimerait deux fois. Une AUTRE epic en tête reste du texte libre."""
    if not epic:
        return None
    m = _EPIC_EN_TETE.match(title or "")
    if m and m.group(1) == epic:
        return (
            f"the title starts with [{epic}], the task's own epic; that prefix is RENDERED "
            f"from the `epic` field by every fixed-width view, so stored it would print "
            f"twice. Write the title without it"
        )
    return None


def _epic_ecrivable(data: dict[str, Any], eid: str, geste: str) -> None:
    """UNE règle pour l'écriture d'une epic sur une tâche : ni vide, ni hors forme,
    ni absente du registre. Lève `BoardError` en nommant le remède."""
    if eid == "":
        raise BoardError(
            f'{geste}: an empty epic is refused — detach a task with '
            f'`tasks.py epic T-NNN --retirer`'
        )
    if not EPIC_ID.match(eid):
        raise BoardError(f"{geste}: {eid!r} is not an epic id (expected E-NN, two digits or more)")
    if find_epic(data, eid) is None:
        raise BoardError(
            f'{geste}: unknown epic {eid} — declare it first: tasks.py epic-new {eid} "<titre>"'
        )


def _une_ligne(valeur: str) -> bool:
    return bool(valeur.strip()) and len(valeur.splitlines()) == 1


def new_epic(
    root: str,
    eid: str,
    titre: str,
    *,
    vague: int | None = None,
    priorite: str | None = None,
    exclusive: bool = False,
    risque: str | None = None,
    maj: bool = False,
) -> str:
    """Déclare (ou, sous `maj`, REMPLACE) une entrée du registre, trié par numéro.

    PAS D'INTENTION DE SYNC, et c'est voulu : le registre n'est pas une tâche, et
    le pont V3 ne projette que des tâches, par un snapshot gelé
    (`SYNC_SNAPSHOT_FIELDS`). Le verbe reste `mutating` dans `main` : le replay V3
    qui l'entoure rejoue les intentions en attente, comme pour tout écrivain.
    Un doublon est refusé sauf `maj` ; une entrée identique sous `maj` n'écrit rien."""
    if not isinstance(eid, str) or not EPIC_ID.match(eid):
        raise BoardError(f"epic-new: {eid!r} is not an epic id (expected E-NN, two digits or more)")
    if not isinstance(titre, str) or not _une_ligne(titre):
        raise BoardError(f"epic-new {eid}: the title must be one non-empty line")
    if priorite is not None and priorite not in EPIC_PRIORITES:
        raise BoardError(f"epic-new {eid}: priorite {priorite!r}; expected one of {', '.join(EPIC_PRIORITES)}")
    if vague is not None and (not isinstance(vague, int) or isinstance(vague, bool) or vague < 0):
        raise BoardError(f"epic-new {eid}: vague {vague!r}; expected a non-negative integer")
    if risque is not None and not _une_ligne(risque):
        raise BoardError(f"epic-new {eid}: the risque must be one non-empty line")
    entree: dict[str, Any] = {"id": eid, "titre": titre}
    if vague is not None:
        entree["vague"] = vague
    if priorite is not None:
        entree["priorite"] = priorite
    if exclusive:
        entree["exclusive"] = True
    if risque is not None:
        entree["risque"] = risque
    with board_lock(root):
        data = load(root)
        existante = find_epic(data, eid)
        if existante is not None and not maj:
            raise BoardError(
                f"epic-new: {eid} already exists ({existante.get('titre', '')!r}) — "
                f"`--maj` replaces the entry"
            )
        if existante == entree:
            return f"TASKS: epic {eid} unchanged"
        registre = [e for e in (data.get("epics") or []) if not (isinstance(e, dict) and e.get("id") == eid)]
        registre.append(entree)
        registre.sort(key=_cle_epic)
        data["epics"] = registre
        save(root, data)
    return f"TASKS: epic {eid} {'replaced' if existante is not None else 'created'} — {titre}"


def _titre_deja_prefixe(tid: str, titre: Any, eid: str) -> str | None:
    """L'avertissement de `set_epic` quand le titre STOCKÉ ouvre sur `[eid]`, ou `None`."""
    if not isinstance(titre, str):
        return None
    m = _EPIC_EN_TETE.match(titre)
    if not m or m.group(1) != eid:
        return None
    import shlex  # local : un import de tête doublonnerait la façade (découpe, témoin e)

    reste = titre[m.end():]
    return (
        f"TASKS: warning — {tid}'s stored title already opens on [{eid}], which `cell` now "
        f"renders from the `epic` field, so every fixed-width view prints it twice. Drop it: "
        f"tasks.py retitle {tid} {shlex.quote(reste)}"
    )


def set_epic(root: str, tid: str, eid: str | None = None, *, retirer: bool = False) -> str:
    """Range UNE tâche sous une epic du registre, ou l'en détache (`retirer`).

    Sibling de `regroup_task`, et sans condition d'état pour la même raison,
    `running` COMPRIS. Un id vide ou inconnu, ou les deux gestes ensemble, sont
    refusés. `retirer` RETIRE la clé : « sans epic » n'a qu'une forme stockée.
    L'INTENTION DE SYNC DIT LE GESTE, PAS LA VALEUR, comme `regroup` : le snapshot
    gelé ne porte pas `epic`, la valeur se lit sur la tâche.

    UN TITRE QUI OUVRE DÉJÀ SUR `[eid]` EST DIT, JAMAIS REFUSÉ : c'est l'état
    d'un titre d'avant migration, que l'importeur retitre juste APRÈS ce verbe.
    Refuser casserait cet ordre ; se taire laisserait les vues imprimer
    `[E-01][E-01]…`. D'où un avertissement sur STDERR, après l'écriture, qui donne
    le `retitle` prêt à lancer — y compris quand le geste est sans effet."""
    if retirer and eid is not None:
        raise BoardError("epic: give an epic id OR --retirer, not both")
    if not retirer and eid is None:
        raise BoardError("epic: give an epic id (E-NN), or --retirer to detach the task")
    double: str | None = None
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        if not retirer:
            _epic_ecrivable(data, eid, f"epic {tid}")
            double = _titre_deja_prefixe(tid, task.get("task"), eid)
        actuelle = task.get("epic")
        if (retirer and actuelle is None) or (not retirer and actuelle == eid):
            # Un geste sans effet ne tamponne pas `updated`, comme `unblock` d'un pending.
            if double is not None:
                print(double, file=sys.stderr)
            return f"TASKS: {tid} epic unchanged ({actuelle or 'none'})"
        before = copy.deepcopy(task)
        if retirer:
            task.pop("epic", None)
        else:
            task["epic"] = eid
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    if double is not None:
        print(double, file=sys.stderr)
    if retirer:
        return f"TASKS: {tid} detached from {actuelle} (epic cleared)"
    return f"TASKS: {tid} → epic {eid}"


def epic_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Une ligne par epic : le registre trié, puis les ids PORTÉS par des tâches
    et absents du registre (`hors_registre`), pour qu'aucune epic ne disparaisse
    de la liste parce que son entrée manque. Compte par état, sans plafond."""
    comptes: dict[str, dict[str, int]] = {}
    for t in data.get("tasks", []):
        eid = t.get("epic")
        if eid:
            comptes.setdefault(eid, dict.fromkeys(STATES, 0))[t["state"]] += 1
    lignes: list[dict[str, Any]] = []
    connus = set()
    for e in sorted(epics_of(data), key=_cle_epic):
        connus.add(e["id"])
        ligne = {k: e[k] for k in ("id", "titre", "vague", "priorite", "risque") if k in e}
        ligne["exclusive"] = bool(e.get("exclusive"))
        ligne["hors_registre"] = False
        ligne["compte"] = comptes.get(e["id"], dict.fromkeys(STATES, 0))
        lignes.append(ligne)
    for eid in sorted(set(comptes) - connus, key=lambda i: _cle_epic({"id": i})):
        lignes.append({"id": eid, "titre": "", "exclusive": False, "hors_registre": True,
                       "compte": comptes[eid]})
    for ligne in lignes:
        ligne["total"] = sum(ligne["compte"].values())
    return lignes


def render_epic_list(data: dict[str, Any], as_json: bool = False) -> str:
    """`epic-list` : UNE ligne par epic, sans en-tête (le compte de lignes EST le
    compte d'epics), ou la même liste en JSON. Registre vide : une phrase, jamais
    un silence."""
    lignes = epic_rows(data)
    if as_json:
        return json.dumps(lignes, indent=2, ensure_ascii=False)
    if not lignes:
        return "(no epic: the registry is empty and no task carries one)"
    rendu = []
    for ligne in lignes:
        attributs = [f"vague={ligne['vague']}"] if "vague" in ligne else []
        attributs += [ligne["priorite"]] if "priorite" in ligne else []
        attributs += ["exclusive"] if ligne["exclusive"] else []
        titre = "(hors registre)" if ligne["hors_registre"] else (ligne.get("titre") or EMPTY)
        compte = " ".join(f"{s}={ligne['compte'][s]}" for s in STATES)
        rendu.append(f"{ligne['id']} | {titre} | {' '.join(attributs) or EMPTY} | {compte}")
    return "\n".join(rendu)


def render_epic_tasks(
    data: dict[str, Any], epic: str, state: str | None = None, as_json: bool = False
) -> tuple[str, str | None]:
    """`list --epic` : `(sortie, absence)`. `""` = les tâches SANS epic. Un id est
    CONNU s'il est au registre OU porté par une tâche (une epic hors registre se
    lit, elle ne disparaît pas) ; sinon c'est un refus, jamais un vide qui se
    lirait « aucune tâche ». Combinable avec `state` et `as_json` seulement : la
    matrice est fermée dans `main`. Ni `render_list` ni `filter_tasks` ne sont
    touchés, donc `list --json` sans filtre garde sa forme exacte. En JSON,
    l'absence va sur STDERR (`absence`), STDOUT reste du JSON."""
    if state is not None and state not in STATES:
        raise BoardError(f"unknown state {state!r}; expected one of {', '.join(STATES)}")
    if epic != "":
        connus = {e["id"] for e in epics_of(data)} | {t["epic"] for t in data["tasks"] if t.get("epic")}
        if epic not in connus:
            raise BoardError(
                f"unknown epic {epic!r}: neither in the registry nor carried by a task "
                f"(tasks.py epic-list shows them)"
            )
    matched = [t for t in data["tasks"] if (t.get("epic") or "") == epic]
    if state is not None:
        matched = [t for t in matched if t["state"] == state]
    matched = sorted_tasks(matched, cap_done=False)
    label = f"epic={epic or '(sans epic)'}" + (f", state={state}" if state is not None else "")
    if as_json:
        return json.dumps(matched, indent=2, ensure_ascii=False), (None if matched else f"no task matching {label}")
    if not matched:
        return f"## TASK BOARD — filter: {label}\n(no task matching {label})", None
    plural = "" if len(matched) == 1 else "s"
    head = f"## TASK BOARD — filter: {label} ({len(matched)} task{plural})"
    return head + "\n" + "\n".join(render_table(matched)), None


def _epic_proche(ligne: str) -> bool:
    s = ligne.lstrip(" \t>")
    puce = _EPIC_PUCE.match(s)
    if puce:
        s = s[puce.end():].lstrip(" \t")
    return bool(_EPIC_PROCHE.match(s.lstrip("*_").lstrip(" \t")))


def releve_epic(texte: str, tid: str) -> tuple[list[str], list[str]]:
    """FONCTION PURE : `(epics de tid, lignes fautives)` lus HORS bloc de code.

    Les blocs de code sont écartés par `plan_cible.lignes_hors_code` quand le
    module frère est là ; sans lui, toutes les lignes sont lues (la garde, elle,
    est inerte sans module). L'id de tâche se compare par `identity_key` : un
    ancien par valeur NUMÉRIQUE (`T-1043` vaut `T-00001043`, `load` interdit deux
    ids de même valeur), un `T-<ULID>` par son corps EXACT, jamais un ULID contre
    un ancien de même chiffre final (T-00001040). Une
    ligne conforme d'une AUTRE tâche est ignorée ; une ligne FAUTIVE est nommée
    quelle que soit sa tâche ; deux epics distinctes pour `tid` sont une faute."""
    _pc = plan_cible_module()
    lignes = _pc.lignes_hors_code(texte) if _pc is not None else texte.split("\n")
    epics: list[str] = []
    sources: dict[str, str] = {}
    fautives: list[str] = []
    for ligne in lignes:
        if not _EPIC_MOT_CLE.match(ligne):
            if _epic_proche(ligne):
                fautives.append(
                    f"ligne proche du mot-clé {ligne.strip()!r} — ni lue ni ignorée : écris "
                    f"`EPIC: T-<id> -> E-NN` en tête de ligne (seule la puce `- ` est tolérée)")
            continue
        m = _EPIC_LIGNE.match(ligne)
        if not m:
            fautives.append(f"ligne malformée {ligne.strip()!r} — forme attendue `EPIC: T-<id> -> E-NN`")
            continue
        if identity_key(m.group(1)) != identity_key(tid):
            continue
        if m.group(2) not in epics:
            epics.append(m.group(2))
            sources[m.group(2)] = ligne.strip()
    if len(epics) > 1:
        fautives.append(
            f"deux epics pour {tid} ({', '.join(repr(sources[e]) for e in epics)}) — "
            f"une tâche a une seule epic")
    return epics, fautives


def refus_epic_au_done(root: str, tid: str, data: dict[str, Any]) -> str | None:
    """LA GARDE DE PLAN DE L'EPIC, appelée par `set_state` au `done` JUSTE APRÈS
    les arêtes, hors `sans_cible`, sur le `data` pris SOUS le verrou. `None` =
    inerte ou conforme ; sinon le refus.

    Régime : `_arme_pour_tache`, LE lecteur unique du marqueur (jamais une relecture
    inline) ; plan : `resoudre_plan(slot=True)`, R1 puis R2, le même que la cible
    et les arêtes. INERTE si le module manque, si le chantier n'est pas armé, si
    aucun plan n'est résolu, ou sur `CibleError`/`OSError`/`ValueError` : la jambe
    `cible_inexploitable` a déjà refusé un marqueur armé sans module, et
    `evaluer_done`, en amont sur la même résolution, un plan irrésoluble. AUCUNE
    ligne `EPIC:` pour la tâche = inerte : l'epic reste OPTIONNELLE. LIMITES : elle
    mord au `done` seulement, dans un chantier armé seulement, jamais au verdict
    de plan ni côté planificateur (ticket F2) ; le pont V3 la franchit sous
    `sans_cible`, et la marque `[SANS CIBLE : …]` le dit au board."""
    _pc = plan_cible_module()
    if _pc is None:
        return None
    try:
        if _pc._arme_pour_tache(root, tid, data, avertir=False) is None:
            return None
        resolu = _pc.resoudre_plan(root, tid, data, slot=True)
        if resolu is None:
            return None
        chemin, note = resolu
        texte = Path(chemin).read_text(encoding="utf-8")
    except (_pc.CibleError, OSError, ValueError):
        return None
    epics, fautives = releve_epic(texte, tid)
    emprunt = f" {note}" if note else ""
    sortie = 'Sortie tracée : `--sans-cible "<pourquoi>"`, visible au board.'
    if fautives:
        liste = "\n".join(f"  - {f}" for f in fautives)
        return (
            f"TASKS: refus de clore {tid} — le plan approuvé {Path(chemin).name}{emprunt} porte "
            f"des lignes `EPIC:` fautives :\n{liste}\n"
            f"Forme fermée : `EPIC: T-<id> -> E-NN` (une epic par tâche, hors bloc de code). "
            f"Corrige le plan, recalcule son sha256 et rejoue l'approbation.\n{sortie}"
        )
    if not epics:
        return None
    voulue = epics[0]
    actuelle = find(data, tid).get("epic")
    if actuelle == voulue:
        return None
    commandes = [f'tasks.py epic-new {voulue} "<titre>"'] if find_epic(data, voulue) is None else []
    commandes.append(f"tasks.py epic {tid} {voulue}")
    constat = f"le board la range sous {actuelle}" if actuelle else "le board ne lui en donne aucune"
    return (
        f"TASKS: refus de clore {tid} — le plan approuvé {Path(chemin).name}{emprunt} range la "
        f"tâche sous l'epic {voulue} (`EPIC: {tid} -> {voulue}`), et {constat}.\n"
        f"Pose-la, puis rejoue le `done` :\n" + "\n".join(f"  {c}" for c in commandes) + f"\n{sortie}"
    )
