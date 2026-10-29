# tasks_verbes.py — PARTIE de `tasks.py` (T-00000788) : les VERBES simples —
# new, block/unblock, reopen, retitle, reassign, regroup, delete, purge.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


def new_task(
    root: str,
    title: str,
    owner: str,
    chantier: str = "",
    epic: str | None = None,
    mesure: str | None = None,
    pas_un_defaut: str | None = None,
    motif: str | None = None,
    champs: dict[str, Any] | None = None,
    responsable: str = "",
) -> str:
    """Create a pending task. ``responsable`` (T-01M54GEHJBGA5996W0T48JXNQ4) is the
    HUMAN in charge, written only when non-empty, exactly like ``chantier`` below.
    ``chantier`` keeps a default so every existing
    caller stays valid, and the key is written ONLY when it carries a value:
    "no chantier" then has ONE stored shape — absent — shared by legacy entries,
    by a plain ``new``, and by ``regroup <tid> ""``. Every reader goes through
    ``task.get("chantier")``, so the three are indistinguishable by construction
    instead of by three branches nobody would keep in step.

    ``epic`` (T-00001043): ``None`` = no epic; ``""`` is REFUSED, like every
    epic write. It is validated INSIDE the lock and BEFORE the id is minted
    (``record_id_module().mint``), so a refusal creates no task and allocates no id.

    ``mesure`` / ``pas_un_defaut`` / ``motif`` (T-00001128): the two exits of
    the measure guard and the closed motif of the first, see
    :func:`mesure_refusal` (``tasks_mesure.py``). Stored under the key of the
    same name, written ONLY when present — like ``chantier`` — and ignored by
    the V3 snapshot (``SYNC_SNAPSHOT_FIELDS`` is frozen); ``list --task`` shows
    them, since ``format_detail`` prints every key.

    ``champs`` (the batch verb, ``tasks_fournee.py``): extra keys written in the
    SAME save as the task, so a lot is never born without its link to the parent.
    CLOSED to ``fournee`` — no CLI path reaches it, and any other key is refused
    before the id is minted."""
    hors = sorted(set(champs or {}) - {"fournee"})
    if hors:
        raise BoardError(f"new: champs {', '.join(hors)} refusé(s) — seul `fournee` est écrit à la création")
    with board_lock(root):
        data = load(root)
        refus_mesure = mesure_refusal(root, mesure, pas_un_defaut, motif=motif, titre=title)
        if refus_mesure is not None:
            raise BoardError(refus_mesure)
        if epic is not None:
            _epic_ecrivable(data, epic, "new --epic")
            refus_titre = epic_title_refusal(title, epic)
            if refus_titre is not None:
                raise BoardError(f"new --epic {epic}: {refus_titre}")
        tid = record_id_module().mint("T")  # T-00000726: a P-<ULID>, never a counter
        task = {
            "id": tid,
            "state": "pending",
            "task": title,
            "owner": owner,
            "stage": "",
            "updated": date.today().isoformat(),
        }
        if chantier:
            task["chantier"] = chantier
        if responsable:
            task["responsable"] = responsable
        if epic:
            task["epic"] = epic
        if mesure is not None:
            task["mesure"] = mesure
        if pas_un_defaut is not None:
            task["pas_un_defaut"] = pas_un_defaut
        if motif is not None:
            task["motif"] = motif
        for cle, valeur in (champs or {}).items():
            task[cle] = copy.deepcopy(valeur)
        data["tasks"].append(task)
        enqueue_sync_intent(data, tid, None, task)
        save(root, data)
    return f"TASKS: {tid} → pending"


class JiraCollision(BoardError):
    """One Jira identity collides with a different board task ID."""


def new_jira_task(root: str, task: dict[str, Any], operation_id: str) -> str:
    """Import one validated Jira issue under the board lock, including its identity."""
    with board_lock(root):
        data = load(root)
        _ensure_sync_extensions(data)
        correlation = data["sync_correlations"].get(operation_id)
        if correlation is not None and correlation.get("tombstoned"):
            return f"JIRA: {task['jira_key']} deja-supprime"
        if any(c.get("board_task_id") == task["id"] and c.get("tombstoned")
               for c in data["sync_correlations"].values()):
            return f"JIRA: {task['jira_key']} deja-supprime"
        existing = next((t for t in data["tasks"] if t.get("jira_site") == task["jira_site"]
                         and t.get("jira_issue_id") == task["jira_issue_id"]), None)
        if existing is not None:
            return f"JIRA: {task['jira_key']} deja-importe {existing['id']}"
        if any(t["id"] == task["id"] for t in data["tasks"]):
            raise JiraCollision(f"JIRA: {task['jira_key']} collision d'identifiant {task['id']}")
        data["tasks"].append(task)
        enqueue_sync_intent(data, task["id"], None, task, operation_id=operation_id)
        save(root, data)
    return f"JIRA: {task['jira_key']} importe {task['id']}"


def create_linked_task(
    root: str,
    title: str,
    owner: str,
    operation_id: str,
    board_task_id: str | None = None,
) -> str:
    """Create once for an authorized V3 operation, atomically linking its id.

    ``board_task_id`` (T-00001060, K1) : l'id que la MACHINE a déjà réservé — jamais
    de frappe ici. Tâche présente ⇒ CRÉDITÉE (corrélation posée, aucune création) ;
    absente ⇒ créée sous cet id. Refus : corrélation de l'opération vers un AUTRE id,
    ou id porté par une corrélation tombée (« refusing resurrection »)."""
    if not operation_id or board_task_id == "":
        raise BoardError("linked task creation requires an operation id (and a non-empty board id when given)")
    with board_lock(root):
        data = load(root)
        _ensure_sync_extensions(data)
        existing = data["sync_correlations"].get(operation_id)
        if existing is not None:
            if existing["tombstoned"]:
                raise BoardError(f"operation {operation_id} is tombstoned; refusing resurrection")
            if board_task_id is not None and existing["board_task_id"] != board_task_id:
                raise BoardError(f"operation {operation_id} already correlates to another board identity")
            board_task_id = existing["board_task_id"]
            find(data, board_task_id)
            return board_task_id
        if board_task_id is not None:
            if any(v["board_task_id"] == board_task_id and v["tombstoned"] for v in data["sync_correlations"].values()):
                raise BoardError(f"{board_task_id} is tombstoned; refusing resurrection")
            if any(t["id"] == board_task_id for t in data["tasks"]):
                data["sync_correlations"][operation_id] = {"board_task_id": board_task_id, "tombstoned": False}
                save(root, data)
                return board_task_id
        else:
            board_task_id = record_id_module().mint("T")
        task = {
            "id": board_task_id,
            "state": "pending",
            "task": title,
            "owner": owner,
            "stage": "",
            "updated": date.today().isoformat(),
        }
        data["tasks"].append(task)
        data["sync_correlations"][operation_id] = {
            "board_task_id": board_task_id,
            "tombstoned": False,
        }
        save(root, data)
        return board_task_id


def link_operation_to_task(root: str, board_task_id: str, operation_id: str) -> str:
    """Alias a retry operation to one existing task without creating a task."""
    if not operation_id:
        raise BoardError("task correlation requires an operation id")
    with board_lock(root):
        data = load(root)
        _ensure_sync_extensions(data)
        find(data, board_task_id)
        existing = data["sync_correlations"].get(operation_id)
        expected = {"board_task_id": board_task_id, "tombstoned": False}
        if existing is not None:
            if existing != expected:
                raise BoardError(
                    f"operation {operation_id} already correlates to another board identity"
                )
            return board_task_id
        data["sync_correlations"][operation_id] = expected
        save(root, data)
        return board_task_id


def block_task(root: str, tid: str, note: str = "", blocked_on: str = "") -> str:
    """Mark blocked, recording the reason in ``stage``.

    WITH a note this is exactly ``set_state(..., "blocked", stage=note)`` and
    reports exactly what it always reported: the documented path, driven by
    every host's kickoff skill, does not move.

    WITHOUT a note it no longer WIPES the field (T-00000103). Measured before
    the fix: ``block T-00000001`` on a task staged ``security-code-review``
    left ``stage: ""``. A verb whose only job is to ANNOTATE was destroying the
    pipeline step in flight and producing a blocked row whose stage column is
    ``—`` — information-free, indistinguishable from a pending row, and a state
    the documented contract cannot express (contrat du champ : voir l'en-tête de
    ce module et ``.agents/skills/task-board/SKILL.md`` — la rédaction
    précédente citait ``AGENTS.md``, qui ne porte PAS cette phrase : zéro
    occurrence mesurée le 2026-09-13, citation fantôme préexistante). That was the
    substantive half of the ``block``/``stage`` incoherence: ``stage <tid>
    <stage>`` cannot omit its value, while ``block`` made the SAME field
    optional *and* destructive.

    So an absent note PRESERVES the stage — ``stage=None`` is ``set_state``'s
    "leave it alone" — and SAYS that no reason was recorded instead of
    reporting a bare success. Both messages keep the ``TASKS: <tid> → blocked``
    prefix any existing consumer matches on, so nothing downstream moves.

    ``blocked_on`` IS THE MACHINE HALF (T-00000182). ``--note`` says why to a
    human; ``--on`` says on WHAT to the board, and that is what lets ``done``
    release this task by itself. The two compose: a task waiting on a human
    decision AND on another task takes ``--note`` for the prose, ``--on`` for the
    link. Three refusals, all loud: an unknown id (exact match, like every write
    verb — a mistyped ``--on 5`` must never link T-00000005 by numeric luck), a
    task blocked on ITSELF (a link nothing could ever release), and a blocker
    already ``done`` (the release would have to fire in the past; the answer is
    to not block, or to block on something else).

    ``stage`` still never loses information: a note wins, an occupied stage is
    preserved, and only an EMPTY stage receives ``on T-MMM`` — so a blocked row
    with no note is not an information-free ``—`` when a link explains it.
    Neither is the link: a ``block`` with no ``--on`` on a task that already
    carries one PRESERVES it (same non-destruction rule), a second ``--on``
    replaces it, and dropping one goes through ``unblock`` or any exit from
    ``blocked``.
    """
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        blocker_id = ""
        if blocked_on:
            blocker = find(data, blocked_on)
            blocker_id = blocker["id"]
            if blocker_id == task["id"]:
                raise BoardError(
                    f"{tid} cannot be blocked on itself; nothing would ever release it"
                )
            if blocker["state"] == "done":
                raise BoardError(
                    f"{blocker_id} is already done — blocking {tid} on it would never be "
                    f"released; do not block it, or block on the task that is actually pending"
                )
        before = copy.deepcopy(task)
        kept = task.get("stage") or ""
        # UN BLOCAGE DIT TOUJOURS POURQUOI — mais la prose n'est pas la seule
        # façon de le dire, et l'exiger en plus d'un lien machine ferait taper
        # « bloqué » comme remplissage, ce qui est pire qu'un lien.
        #
        # Trois sources d'explication, dans l'ordre où le code les emploie déjà :
        # la note, l'étape en vol qu'on PRÉSERVE, et le lien `--on` qui dit sur
        # QUOI la tâche attend. Le refus ne vise donc que le cas réellement
        # MUET — aucune des trois — qui produisait une ligne bloquée dont la
        # colonne motif est `—` : indiscernable d'une ligne en attente, et un
        # état que le contrat documenté ne sait pas exprimer. La rédaction
        # précédente l'écrivait quand même et se contentait de le SIGNALER dans
        # sa sortie ; un signalement qu'on peut ignorer n'a jamais rien empêché.
        if not (note or "").strip() and not blocker_id and not kept.strip():
            raise BoardError(
                f"bloquer {tid} exige une explication : `--note \"<pourquoi>\"` pour "
                f"un motif humain, `--on T-NNN` pour une attente sur une autre "
                "tâche, ou les deux. Sans l'une des deux, la ligne bloquée ne "
                "porte AUCUNE information et ne se distingue plus d'une ligne en "
                "attente."
            )
        # LE CYCLE D'AMONT (S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : `block` ne teste pas l'état de départ.
        # Depuis `running`, la trace sous laquelle la tâche tournait est inscrite si elle manque ;
        # depuis `done`, le cycle clos tombe — gardé, `done` → `block` → `start` reprendrait
        # en REPRISE_DITE le plan d'un cycle CLOS.
        if task["state"] == "running":
            inscrire_lancee_sous(root, task)
        elif task["state"] == "done":
            effacer_cycle_clos(task)
        task["state"] = "blocked"
        # LE MARQUEUR QUI DIT CE QUE LE CHAMP PORTE (T-00000578). `stage` est
        # AMBIGU sur une tâche bloquée : il peut porter une ÉTAPE EN VOL qu'on a
        # préservée, ou un MOTIF DE BLOCAGE qu'il faut effacer en sortant —
        # sinon « on T-B » reste affiché comme étape d'une tâche qui n'est plus
        # bloquée. Sans distinction machine, les trois sorties de `blocked`
        # (`unblock`, `start`, libération au `done` du bloqueur) vidaient le
        # champ dans TOUS les cas, donc perdaient l'étape préservée. Mesuré le
        # 2026-09-13 sur les trois chemins : `security-code-review` -> vide.
        #
        # LE MARQUEUR EST TRANSITOIRE, et c'est ce qui rend acceptable un champ
        # de plus sur un board SANS version de schéma : il naît ici et meurt à
        # la sortie de `blocked`. Aucune tâche non bloquée ne le porte, donc
        # aucun lecteur n'a à le connaître.
        task.pop("stage_kept", None)
        # L'ACTEUR SUIT LE STAGE (T-01M5DBFK3XKKM2VHQM5RE4TP6K) : `block` ne résout aucune identité
        # (le pont V3 l'appelle sans identité locale) ; un stage qu'il RÉÉCRIT perd donc son
        # `stage_actor`, un stage qu'il PRÉSERVE le garde.
        if note:
            task["stage"] = note
            task.pop("stage_actor", None)
        elif blocker_id and not kept:
            task["stage"] = f"on {blocker_id}"
            task.pop("stage_actor", None)
        elif kept:
            task["stage_kept"] = True
        if blocker_id:
            task["blocked_on"] = blocker_id
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    message = f"TASKS: {tid} → blocked"
    if blocker_id:
        message = f"{message} (on {blocker_id} — released when {blocker_id} is done)"
    if note or blocker_id:
        return message
    if kept:
        return f"{message} (no reason recorded — stage kept: {kept})"
    return f'{message} (no reason recorded — use --note "<why>")'


def _unblock_task_unlocked(root: str, tid: str) -> str:
    """``blocked`` → ``pending``, clearing the blocking reason from ``stage``.

    Strict on the departing state on purpose. Accepting any state would make
    this a general "send back to the queue" verb, and the dangerous case is
    ``running``: silently demoting a running task is exactly the kind of
    invisible board move nobody could read back. A task
    that is already ``pending`` is reported rather than rewritten, so nothing
    stamps ``updated`` on a no-op.
    """
    data = load(root)
    task = find(data, tid)
    before = copy.deepcopy(task)
    if task["state"] != "blocked":
        raise BoardError(
            f"{tid} is {task['state']}, not blocked — unblock only returns a blocked task "
            f"to pending (use `start` to make it the running task)"
        )
    # The machine link goes with the blocking reason: `unblock` is the manual
    # form of what `done` does automatically, and leaving `blocked_on` behind
    # would arm a release on a task that is no longer blocked.
    task.pop("blocked_on", None)
    # UNE ÉTAPE PRÉSERVÉE SURVIT À `unblock` (T-00000578). Ce verbe efface le
    # MOTIF de blocage — c'est son travail — mais `stage` porte l'ÉTAPE EN VOL
    # quand `block --on` l'a préservée faute de note. Les deux contenus vivent
    # dans le MÊME champ, et seul `stage_kept` les distingue.
    garde = bool(task.pop("stage_kept", None))
    task.update(state="pending", updated=date.today().isoformat())
    if not garde:
        task["stage"] = ""
        task.pop("stage_actor", None)  # le motif effacé emporte son acteur ; une étape gardée garde le sien
    enqueue_sync_intent(data, tid, before, task)
    save(root, data)
    return f"TASKS: {tid} → pending"


def unblock_task(root: str, tid: str) -> str:
    with board_lock(root):
        return _unblock_task_unlocked(root, tid)


def reopen_task(root: str, tid: str, raison: str, rebloquer: bool = True) -> str:
    """``done`` → ``pending``. L'INVERSE DE ``done``, ET IL MANQUAIT.

    POURQUOI IL EXISTE. Le board avait cinq portes d'entrée dans ``done`` et
    aucune sortie : une clôture prononcée à tort était DÉFINITIVE, quoi qu'on
    découvre ensuite. Mesuré le 2026-09-12 sur T-00000560 et T-00000561 — deux
    tâches ``done`` dont le livrable n'existait dans AUCUN commit, dont le delta
    précédait le plan, et qu'aucune revue n'avait relues. Le seul recours était
    d'écrire une entrée au journal disant que la clôture était fausse, en
    laissant le board continuer d'affirmer le contraire. Un état qu'on ne peut
    pas corriger cesse d'être un état : c'est une affirmation gravée, et le board
    est censé DIRE ce qui est, pas ce qu'on a cru un jour.

    LA RAISON EST OBLIGATOIRE, et ce n'est pas une politesse. Rouvrir est une
    affirmation sur une clôture que quelqu'un a prononcée ; sans motif écrit,
    c'est un mouvement de board invisible — exactement ce que la sévérité de
    ``unblock`` sur son état de départ existe pour empêcher. La raison va dans
    ``stage``, à la même place que celle de ``block``, donc elle se lit dans tout
    relevé sans qu'aucun consommateur change.

    STRICT SUR L'ÉTAT DE DÉPART, comme ``unblock``. Accepter n'importe quel état
    ferait de ce verbe un « renvoyer dans la file » générique, et le cas
    dangereux est ``running`` : rétrograder la tâche active en silence est
    précisément ce que l'invariant du board interdit. Chaque autre état a déjà
    son verbe, et le refus le NOMME plutôt que de le laisser deviner.

    ROUVRIR REPOSE CE QUE LA CLÔTURE AVAIT LIBÉRÉ, et c'est la symétrie qui
    manquait. ``done`` libère les tâches ``blocked`` sur celle-ci en EFFAÇANT
    leur ``blocked_on`` ; le lien ne survivait donc nulle part et la réouverture
    ne pouvait que le constater. ``done`` écrit désormais la liste de ce qu'il a
    libéré dans ``released_on_done``, sur la tâche qui ferme, et ``reopen`` la
    consomme. Le rétablissement est le DÉFAUT, par la même raison que la
    libération l'est : un geste qui exigerait une seconde commande est un geste
    que personne ne fait. ``--sans-rebloquer`` l'écarte quand la dépendance n'a
    plus lieu d'être.

    CHAQUE RÉTABLISSEMENT EST GARDÉ, ET CHAQUE SAUT EST NOMMÉ. Une tâche n'est
    re-bloquée que si elle est ENCORE ``pending`` et ne porte AUCUN
    ``blocked_on``. Entre-temps elle a pu être démarrée, close, ou bloquée pour
    une autre raison : lui remettre l'ancien lien écraserait un état plus récent
    et plus vrai. Ce qui n'est pas rétabli est dit, avec son motif — un
    rétablissement partiel silencieux serait pire que pas de rétablissement.

    Les liens ``depends_on``, eux, SURVIVENT à la clôture — les tâches qui en
    portent un vers celle-ci sont listées en avertissement, sans qu'aucun état
    change ; leur ``start`` est refusé tant qu'elle n'est pas re-close
    (S-01M4Z5VMP5E9YN8T6EMDTBAF0T). ``lancee_sous``, ``lancee_le`` et ``done_at`` tombent ici
    (``effacer_cycle_clos``).
    """
    raison = (raison or "").strip()
    if not raison:
        raise BoardError(
            f"rouvrir {tid} exige --raison : une clôture qu'on annule sans dire "
            "pourquoi est un mouvement de board invisible"
        )
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        if task["state"] != "done":
            raise BoardError(
                f"{tid} est {task['state']}, pas done — `reopen` ne ramène QU'UNE "
                "tâche close vers pending (`unblock` pour une bloquée, `start` "
                "pour en faire la tâche active)"
            )
        today = date.today().isoformat()
        a_rebloquer = list(task.get("released_on_done") or [])
        task.update(state="pending", stage=raison, updated=today)
        task.pop("stage_actor", None)  # la raison de `reopen` n'est signée par aucun acteur résolu
        # CONSOMMÉE : la liste décrit la clôture qu'on est en train d'annuler, donc
        # elle n'a plus d'objet une fois annulée. La laisser ferait rétablir deux
        # fois au prochain cycle.
        task.pop("released_on_done", None)
        # LE DRAPEAU DE CHAÎNE DE PLAN TOMBE AUSSI (T-00000624). Sans cette ligne,
        # une tâche fermée puis rouverte sautait `PLAN_GATE` DÉFINITIVEMENT : le
        # drapeau se pose une fois, il survit au board, et plus aucun `start`
        # n'exigeait de chaîne. C'était écrit comme « mitigation » dans la section
        # Risks de mon plan de correction et n'existait NULLE PART dans le code —
        # relevé par la critique de plan, qui a lu cette fonction en ENTIER pour
        # le prouver. Une mitigation citée dans un plan n'existe pas tant qu'elle
        # n'est pas une ligne de code : c'est exactement le motif `L-00000111`,
        # une doc qui affirme une garantie que le code ne tient pas.
        #
        # ROUVRIR, C'EST REFAIRE DU TRAVAIL : le plan d'il y a six mois ne couvre
        # pas ce qu'on va réécrire aujourd'hui. Le sens sûr est d'exiger la chaîne
        # à nouveau ; la sortie tracée reste là si la tâche ne la mérite pas.
        task.pop("plan_chain_consumed", None)
        # LA DÉROGATION DE CHAÎNE TOMBE AVEC LUI (T-00001177) : `set_state` la
        # reporte au `done` tant que le champ vit, donc la laisser ici ferait
        # dire à la PROCHAINE clôture qu'elle a dérogé, même si ce nouveau cycle
        # a payé sa chaîne. Un nouveau `start --sans-chaine` la repose.
        task.pop("sans_chaine", None)
        # LE RELEVÉ DE RETOUR TOMBE AUSSI (T-00001182) : le relevé dit la clôture
        # qu'on annule ; resté, il admettrait le `done` du cycle suivant sur la
        # fusion du cycle clos (forme de T-624).
        task.pop("retour", None)
        # LA LIVRAISON TOMBE AVEC LUI (T-01M4WTYSCE) : la clôture annulée emporte sa
        # revue (T-586) ; restée, la tâche re-emprunterait au prochain `done` la trace
        # d'un membre, sur un travail que le nouveau cycle va réécrire.
        task.pop("livraison", None)
        # LE CYCLE D'AMONT TOMBE AVEC LA CLÔTURE (S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : `done_at` dit une
        # clôture annulée, `lancee_sous` la trace d'un cycle clos — gardé, le `start` suivant
        # reprendrait en REPRISE_DITE un plan que la réouverture rend périmé.
        effacer_cycle_clos(task)
        # LA MARQUE DIRECTE DIT LE CYCLE EN COURS (T-00001178, binôme ter) :
        # `chaine_franchie` décrit le `start` du cycle qu'on annule. Gardée, un
        # `done` sans nouveau `start` reprendrait la marque du cycle clos.
        # L'estampille, elle, reste : elle est rejouée au `start` suivant.
        if isinstance(task.get("direct"), dict):
            task["direct"].pop("chaine_franchie", None)
        # LA PREUVE DE REVUE MEURT AVEC LA CLÔTURE QU'ON ANNULE, et pour la même
        # raison — mais son mode de défaillance est bien pire, donc il se dit.
        # La trace est indexée par tâche et n'était jamais invalidée : rouvrir
        # puis refermer une tâche la reclouait avec la revue d'HIER, sur un SHA
        # que plus personne n'avait relu. Mesuré par le binôme : `done` →
        # `reopen` → `done` rendait 0 sans une seule revue neuve. C'est la
        # fraîcheur que `T-00000586` exigeait et qui avait disparu à
        # l'implémentation. `reopen` est le seul retour en arrière du board,
        # donc c'est ici que la preuve se périme d'office ; le seul autre
        # purgeur est le verbe explicite `binome-purge` (T-00000842), joué au
        # matin de `/night` avant le binôme d'une tâche livrée la nuit.
        purge_binome_trace(root, tid)
        enqueue_sync_intent(data, tid, before, task)

        par_id = {t["id"]: t for t in data["tasks"]}
        rebloquees: list[str] = []
        sautees: list[str] = []
        if rebloquer:
            for autre_id in a_rebloquer:
                autre = par_id.get(autre_id)
                if autre is None:
                    sautees.append(f"{autre_id} (n'existe plus au board)")
                    continue
                if autre.get("blocked_on"):
                    sautees.append(f"{autre_id} (deja bloquee sur {autre['blocked_on']})")
                    continue
                if autre["state"] != "pending":
                    sautees.append(f"{autre_id} ({autre['state']} depuis — etat plus recent)")
                    continue
                autre_before = copy.deepcopy(autre)
                autre.update(state="blocked", blocked_on=tid,
                             stage=f"re-bloquee : {tid} rouverte", updated=today)
                autre.pop("stage_actor", None)
                enqueue_sync_intent(data, autre_id, autre_before, autre)
                rebloquees.append(autre_id)

        save(root, data)
        # `depends_on` SURVIT à la clôture : ces tâches-là sont encore ordonnées
        # derrière celle qu'on rouvre, et leur pilote a le droit de le savoir.
        derriere = sorted(
            t["id"] for t in data["tasks"]
            if t["id"] != tid and tid in (t.get("depends_on") or [])
        )
    lignes = [f"TASKS: {tid} → pending (rouverte : {raison})"]
    for autre_id in rebloquees:
        lignes.append(f"TASKS: {autre_id} → blocked (lien retabli sur {tid})")
    if sautees:
        lignes.append(
            f"TASKS: {len(sautees)} lien(s) NON retabli(s) : " + " · ".join(sautees)
        )
    if a_rebloquer and not rebloquer:
        lignes.append(
            f"TASKS: --sans-rebloquer — {len(a_rebloquer)} lien(s) laisse(s) libre(s) : "
            + ", ".join(a_rebloquer)
        )
    if not a_rebloquer:
        lignes.append(f"TASKS: la cloture de {tid} n'avait libere aucune tache")
    if derriere:
        lignes.append(
            f"TASKS: {len(derriere)} tache(s) ordonnee(s) derriere {tid} (depends_on : "
            f"leur start est refuse tant que {tid} n'est pas re-close) : " + ", ".join(derriere)
        )
    return "\n".join(lignes)


def retitle_task(root: str, tid: str, title: str) -> str:
    """Update a task's title only. State-free — a task in any state (pending,
    running, blocked, done) can be retitled. A title that OPENS on the task's
    own ``[E-NN]`` is refused (R10, T-00001043): ``cell`` renders that prefix
    from the ``epic`` field, so stored it would print twice. A rollback to the
    old titles therefore detaches the epic (``epic --retirer``) FIRST."""
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        refus_titre = epic_title_refusal(title, task.get("epic"))
        if refus_titre is not None:
            raise BoardError(f"retitle {tid}: {refus_titre}")
        before = copy.deepcopy(task)
        task["task"] = title
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    return f"TASKS: {tid} retitled"


def reassign_task(root: str, tid: str, owner: str) -> str:
    """Update a task's OWNER only — the agent responsible for it.

    Sibling of ``retitle_task``, and state-free for the same reason, ``running``
    INCLUDED: the main case is a task whose nature changes in flight — a screen
    believed technical turns out to be design work, so its owner moves from
    ``dev-mono`` to ``frontend-fidelity`` while the task is the active one.
    Nothing here writes ``state``, so the running invariant is untouched
    by construction rather than by a check.

    NO VALIDATION of ``owner`` against a list of known agents, deliberately.
    ``new --owner`` takes free text and defaults to ``""``; validating here and
    not there would make the SAME value acceptable at creation and refused at
    reassignment — an asymmetry that would surface as a task nobody can hand
    over. If such a list ever exists it belongs to BOTH verbs in one change.
    Do not "fix" the absence here on its own.

    An EMPTY owner is legitimate, not an accident: it returns the task to
    unassigned, exactly the value ``new`` writes with no ``--owner`` (the view
    renders it ``—``). argparse passes an empty positional straight through
    (measured), so ``reassign T-014 ""`` is a real call, and the message SAYS
    the field was cleared instead of trailing off after "reassigned to".
    """
    with board_lock(root):
        data = load(root)
        # Exact-match `find`, like every other write verb: a mistyped `reassign 5`
        # must fail loudly, never hand over T-00000005 by numeric luck.
        task = find(data, tid)
        before = copy.deepcopy(task)
        task["owner"] = owner
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    if owner:
        return f"TASKS: {tid} reassigned to {owner}"
    return f"TASKS: {tid} reassigned to nobody (owner cleared)"


def regroup_task(root: str, tid: str, chantier: str) -> str:
    """Update a task's CHANTIER only — the thematic group it belongs to.

    Sibling of ``reassign_task``, and state-free for the same reason, ``running``
    INCLUDED: a task is regrouped precisely while the work is in flight, once it
    becomes clear it belongs with three others. Nothing here writes ``state``,
    so the running invariant is out of this verb's reach by construction
    rather than by a check.

    NO VALIDATION of ``chantier`` against a list of known groups, deliberately,
    and for the argument spelled out in ``reassign_task``: ``new --chantier``
    takes free text, so refusing a value here that creation accepts would make a
    task impossible to file. If such a list ever exists it belongs to BOTH verbs
    in one change.

    An EMPTY chantier UN-GROUPS, and the key is REMOVED rather than set to
    ``""`` — "no chantier" keeps the single stored shape ``new_task`` documents.
    The message SAYS the field was cleared instead of trailing off after "under".

    THE SYNC INTENT RECORDS THE GESTURE, NOT THE VALUE, and that is a deliberate
    limit rather than an oversight: ``SYNC_SNAPSHOT_FIELDS`` is frozen by
    ``load``'s own validation (``set(snapshot) != set(SYNC_SNAPSHOT_FIELDS)``
    raises, and ``revision_sha256`` is recomputed from it), so widening it would
    make every intent already sitting in a store's outbox unreadable. A regroup
    therefore emits the same canonical intent every other verb does — same
    ``event_kind``, same correlation, ``updated`` moved — and the new value is
    read from the task, never from the snapshot.
    """
    with board_lock(root):
        data = load(root)
        # Exact-match `find`, like every other write verb: a mistyped `regroup 5`
        # must fail loudly, never regroup T-00000005 by numeric luck.
        task = find(data, tid)
        before = copy.deepcopy(task)
        if chantier:
            task["chantier"] = chantier
        else:
            task.pop("chantier", None)
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    if chantier:
        return f"TASKS: {tid} regrouped under {chantier}"
    return f"TASKS: {tid} regrouped under nothing (chantier cleared)"


def responsable_task(root: str, tid: str, responsable: str) -> str:
    """Update a task's RESPONSABLE only — the HUMAN in charge (T-01M54GEHJBGA5996W0T48JXNQ4).

    Patron ``regroup_task``, état libre, ``running`` compris ; texte libre, aucune liste
    de noms ; ``""`` RETIRE la clé (une seule forme stockée pour « personne »). ``owner``
    reste l'AGENT et n'est jamais touché ici. Pas une colonne : ``FIELDS``, ``WIDTHS`` et
    ``SYNC_SNAPSHOT_FIELDS`` sont inchangés — l'intention V3 dit le geste, pas la valeur."""
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        if responsable:
            task["responsable"] = responsable
        else:
            task.pop("responsable", None)
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    if responsable:
        return f"TASKS: {tid} responsable {responsable}"
    return f"TASKS: {tid} responsable cleared (no human in charge)"


def _limite_resume(task: dict[str, Any]) -> str:
    """Les limites d'une tâche, en nombres et instants re-formatés seulement (jamais le titre)."""
    lus, illisibles = limite_champs(task)
    parts = [f"échéance {limite_iso(lus['echeance'])}" if lus["echeance"] else "sans échéance",
             f"limite {limite_k(lus['limite_jetons'])}" if lus["limite_jetons"] else "sans limite de jetons",
             f"jetons déclarés {limite_k(lus['jetons'])}" if lus["jetons"] is not None else "jetons illisibles"]
    parts += [f"champ {c} illisible" for c in illisibles if c != "jetons"]
    return ", ".join(parts)


def limite_task(root: str, tid: str, delai: str | None = None, echeance: str | None = None,
                jetons: str | None = None, retirer: bool = False, maintenant: datetime | None = None) -> str:
    """Pose, relève ou retire les LIMITES d'une tâche (T-01M54GEMCH3JWA95G61N2J70KS, C-verbes).

    `--delai` (maintenant + N) et `--echeance` sont exclusifs et posent `echeance` ;
    `--jetons` pose `limite_jetons` ; `--retirer`, exclusif des trois, retire les deux et
    GARDE le cumul `jetons`. Tout état, `done` compris. Tout refus est une `BoardError`
    (rc 2) levée AVANT le verrou : le board n'est pas écrit."""
    if retirer and (delai is not None or echeance is not None or jetons is not None):
        raise BoardError("limite : --retirer ne se combine avec aucune autre option, board NON écrit")
    if delai is not None and echeance is not None:
        raise BoardError("limite : --delai et --echeance sont exclusifs (le délai CALCULE l'échéance), "
                         "board NON écrit")
    if not retirer and delai is None and echeance is None and jetons is None:
        raise BoardError("limite : rien à poser — --delai, --echeance, --jetons ou --retirer, board NON écrit")
    quand = None
    if delai is not None:
        quand = limite_lire_delai(delai, maintenant or datetime.now(timezone.utc))
    elif echeance is not None:
        quand = limite_lire_echeance(echeance)
    plafond = limite_lire_jetons(jetons, "--jetons") if jetons is not None else None
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        if retirer:
            task.pop("echeance", None)
            task.pop("limite_jetons", None)
        if quand is not None:
            task["echeance"] = limite_iso(quand)
        if plafond is not None:
            task["limite_jetons"] = plafond
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    geste = "limites retirées" if retirer else "limite posée"
    return f"TASKS: {limite_id(task)} {geste} — {_limite_resume(task)}"


def conso_task(root: str, tid: str, quantite: str) -> str:
    """AJOUTE `quantite` au cumul DÉCLARÉ `jetons` (T-01M54GEMCH3JWA95G61N2J70KS, C-arrêt).

    La source est le `subagent_tokens` (`totalTokens`) que l'hôte rend pour un sous-agent
    terminé — la taille de son DERNIER appel, jamais sa consommation (mesuré 1× à 194× sous
    les jetons traités, médiane 39×) —, recopié par l'orchestrateur ; rien ici ne le mesure.
    Sous `LIMITE_ARRET`, une tâche `pending` ou
    `running` dont le cumul dépasse alors sa limite est écrite PUIS passée `blocked` par
    `block_task`, dont la note GARDE l'étape d'avant (`block --note` écrase `stage`)."""
    ajout = limite_lire_jetons(quantite, "conso")
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        lus, _ = limite_champs(task)
        if lus["jetons"] is None:
            raise BoardError(f"{limite_id(task)} : champ jetons illisible — corriger le board à la main avant "
                             "toute conso ; jamais une valeur écrasée en silence, board NON écrit")
        before = copy.deepcopy(task)
        task["jetons"] = lus["jetons"] + ajout
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    plafond = lus["limite_jetons"]
    message = f"TASKS: {limite_id(task)} jetons déclarés {limite_k(task['jetons'])} (+{limite_k(ajout)})"
    if plafond is not None:
        message += f" / limite {limite_k(plafond)}"
    if (plafond is not None and task["jetons"] > plafond and task["state"] in ("pending", "running")
            and limite_arret_arme(root)):
        avant = "".join(c for c in str(task.get("stage") or "") if c.isprintable()).strip()[:200]
        note = (f"limite de jetons dépassée : {limite_k(task['jetons'])} / {limite_k(plafond)} — "
                + (f"étape avant blocage : {avant}" if avant else "aucune étape en cours avant blocage"))
        try:
            message += "\n" + block_task(root, task["id"], note)
        except (BoardError, OSError) as exc:
            raise BoardError(f"{limite_id(task)} {LIMITE_REFUS} {LIMITE_ARME_POURQUOI} — conso ÉCRITE "
                             f"({limite_k(task['jetons'])} / {limite_k(plafond)}) — ne pas la rejouer ; "
                             f"blocage NON posé ({exc}) ; {LIMITE_REMEDE}") from exc
        message += (f"\nTASKS: {limite_id(task)} {LIMITE_REFUS} {LIMITE_ARME_POURQUOI} — conso écrite, "
                    f"tâche passée blocked ; {LIMITE_REMEDE}")
    return message


def _clear_dangling_blocked_on(
    data: dict[str, Any], gone: set[str], today: str, verb: str = "deleted"
) -> list[str]:
    """Clean the links that pointed at a task LEAVING the board, and SAY it.

    A removed blocker is not an ACCOMPLISHED blocker, so this never releases:
    the dependents stay ``blocked``, because turning them ``pending`` would
    claim work was finished when a row was merely erased. Only the dangling
    reference goes — and it goes with a warning per referring task, since a
    dependency dropped in silence is a dependency nobody thinks to re-declare.
    (After a ``done`` the link is already gone, released at closure, so a purge
    of the done backlog normally finds nothing here — it is handled anyway,
    because a store can carry a link minted before any of this existed.)
    """
    warnings: list[str] = []
    for task in data["tasks"]:
        blocker = task.get("blocked_on")
        if blocker not in gone:
            continue
        before = copy.deepcopy(task)
        task.pop("blocked_on", None)
        task["updated"] = today
        enqueue_sync_intent(data, task["id"], before, task)
        if task["state"] == "blocked":
            warnings.append(
                f"warning: {task['id']} was blocked on {verb} {blocker} — still blocked"
            )
        else:
            warnings.append(
                f"warning: {task['id']} referenced {verb} {blocker} — link cleared"
            )
    # THE SAME CLEANING ON THE PERSISTENT AXIS, with a DIFFERENT sentence,
    # because the consequence differs: dropping a `depends_on` edge frees
    # nothing, since the dependent was never held in the first place. Saying
    # "still blocked" here would be false; saying nothing would leave an order
    # silently shorter than the one the pilot declared. The ONE accepted bypass of the
    # ORDRE PILOTE protection (T-00000765): an EXTRA warning names the motif (module absent: skipped).
    _pd = plan_depends_module()
    for task in data["tasks"]:
        declared = depends_on_of(task)
        remaining = [d for d in declared if d not in gone]
        if len(remaining) == len(declared):
            continue
        dropped = [d for d in declared if d in gone]
        before = copy.deepcopy(task)
        for d in dropped:
            motif_perdu = (task.get("depends_motif") or {}).get(d) or ""
            if _pd is not None and _pd.est_ordre_pilote(motif_perdu):
                warnings.append(
                    f"warning: {task['id']} loses an ORDRE PILOTE edge on {verb} {d} — "
                    f"motif : {motif_perdu}"
                )
        if remaining:
            task["depends_on"] = remaining
            # A GUARDED assignment, mirror of the `depends_on` guard just above:
            # a NUDE comprehension would CREATE the key it was only meant to
            # REDUCE — on a legacy edge with no motif it writes `depends_motif:
            # {}`, which `save` never cleans, load accepts vacuously, and
            # `format_detail` renders as a stray empty line. A motif must never
            # survive the edge it describes, and never be minted from nothing.
            filtre = {k: v for k, v in task.get("depends_motif", {}).items() if k in remaining}
            if filtre:
                task["depends_motif"] = filtre
            else:
                task.pop("depends_motif", None)
        else:
            task.pop("depends_on", None)
            task.pop("depends_motif", None)
        task["updated"] = today
        enqueue_sync_intent(data, task["id"], before, task)
        warnings.append(
            f"warning: {task['id']} depended on {verb} {', '.join(dropped)} — link cleared; "
            f"{task['id']} is NOT released, it was never held"
        )
    return warnings


def delete_task(root: str, tid: str, force: bool = False) -> str:
    """Remove ONE task from the board. Deleting never frees its id: a new id is
    a freshly minted ``T-<ULID>`` (T-00000726), never derived from the ids still
    on the board, so a deleted id is a hole, never a reuse. A ``running`` task is one the surfaces
    highlight — deleting it requires an explicit ``--force``. The refusal is
    PLURAL since T-00000188 (a declared parallel group has several), but it is
    the same refusal: a task in flight never leaves the board by accident.
    On a board in records (T-00001009) the task's file becomes a TOMBSTONE
    (``record: null``, its correlation keys inside, ``[]`` without any), never
    removed: the archive-and-compaction task owns any removal."""
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        if task["state"] == "running" and not force:
            raise BoardError(f"{tid} is a running task; pass --force to delete it anyway")
        before = copy.deepcopy(task)
        data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
        enqueue_sync_intent(data, tid, before, None)
        warnings = _clear_dangling_blocked_on(data, {tid}, date.today().isoformat())
        save(root, data)
    return "\n".join([f"TASKS: {tid} deleted", *warnings])


def _purge_tasks_unlocked(
    root: str, state: str = "done", before: str | None = None, dry_run: bool = False, plafond: int = 50
) -> str:
    """Bulk-remove tasks in a given state (default: the ``done`` backlog).
    ``running`` is never purgeable — use ``delete --force`` for the active
    task. With ``--before`` only tasks updated STRICTLY before that ISO date
    go; a task with no ``updated`` stamp is kept (its age cannot be proven).
    ``--dry-run`` reports what would go without writing anything.

    ONE TOMBSTONE PER PURGED TASK, AND A CAP PER CALL (T-00001009, pilot decision
    S-01M4NFRZS1XK1BEQVGH43Z3EDN, interim until the archive-and-compaction task):
    each purged task sends one deletion to V3 and, on a board in records, leaves
    its tombstone file; more than ``plafond`` tasks (50 by default, every state)
    is REFUSED after the count and before any mutation — nothing written, no
    intent — naming the ``--plafond`` that lifts it. ``--dry-run`` is never
    refused: it says when the real run would be. The cap bounds the INVOLUNTARY
    mass, not the intent (``--plafond 9999`` passes)."""
    if isinstance(plafond, bool) or not isinstance(plafond, int) or plafond < 1:
        raise BoardError(f"--plafond expects a whole number of tasks, 1 or more, got {plafond!r}")
    if state == "running":
        raise BoardError("refusing to purge running tasks; use delete --force for the active task")
    if before is not None:
        try:
            date.fromisoformat(before)
        except ValueError as exc:
            raise BoardError(f"--before expects YYYY-MM-DD, got {before!r}") from exc
    data = load(root)
    victims = [
        t
        for t in data["tasks"]
        if t["state"] == state and (before is None or ((t.get("updated") or "") and t["updated"] < before))
    ]
    scope = f"state={state}" + (f", before {before}" if before else "")
    if not victims:
        return f"TASKS: nothing to purge ({scope})"
    ids = ", ".join(t["id"] for t in victims)
    if dry_run:
        refus = f" (a real run would be refused: above the per-call cap of {plafond})" if len(victims) > plafond else ""
        return f"TASKS: purge would remove {len(victims)} task(s) ({scope}): {ids}{refus}"
    if len(victims) > plafond:
        raise BoardError(
            f"refusing to purge {len(victims)} task(s) ({scope}): above the per-call cap of {plafond} — each sends "
            f"one deletion to V3; rerun with --plafond {len(victims)}"
        )
    gone = {t["id"] for t in victims}
    data["tasks"] = [t for t in data["tasks"] if t["id"] not in gone]
    for victim in victims:
        enqueue_sync_intent(data, victim["id"], victim, None)
    warnings = _clear_dangling_blocked_on(data, gone, date.today().isoformat(), verb="purged")
    save(root, data)
    return "\n".join([f"TASKS: purged {len(victims)} task(s) ({scope}): {ids}", *warnings])


def purge_tasks(
    root: str, state: str = "done", before: str | None = None, dry_run: bool = False, plafond: int = 50
) -> str:
    """`_purge_tasks_unlocked` under `board_lock` — the cap (50 by default) included."""
    with board_lock(root):
        return _purge_tasks_unlocked(root, state=state, before=before, dry_run=dry_run, plafond=plafond)


def avis_portee_hors_focus(avant: dict[str, Any] | None, tid: str) -> str | None:
    """F1 de la clôture : ``avant`` est la portée ACTIVE lue AVANT d'écrire le focus ``tid``. Si le
    nouveau focus la met HORS FOCUS alors qu'un membre n'est pas consommé, la ligne à DIRE (le
    remède sans nouveau critique), sinon ``None``. Lu par ``start``, ``fournee`` et ``focus``."""
    if avant is None or avant["focus"] == tid:
        return None
    reste = [m for m in avant["members"] if m not in avant["consumed"]]
    if not reste:
        return None
    return (f"TASKS: AVIS — la review-scope du focus {avant['focus']} passe HORS FOCUS : {len(reste)} membre(s) "
            f"non consommé(s) ({', '.join(reste)}) ne sont plus crédités ; `tasks.py focus {avant['focus']}` "
            f"la rétablit sans nouveau critique")


def fixer_focus(root: str, tid: str) -> str:
    """``tasks.py focus <T>`` (T-01M5F7286N1EYGXAXA5244X86B, S-01M5E50AJX9V9AP8A8VBBHS6B4) : le
    focus du clone — UNE session active par clone — nomme une tâche ``running`` du board, jamais
    une autre ; écrit ``focus.json`` (``poser_focus``) sous le dépôt PRINCIPAL. Ne touche pas au
    board : verbe NON mutant (aucun rejeu V3), qui écrit quand même son JSON local."""
    with board_lock(root):
        task = find(load(root), tid)
        if task["state"] != "running":
            raise BoardError(
                f"focus {task['id']} refusé : la tâche est `{task['state']}`, jamais `running` — le focus "
                f"nomme une tâche EN VOL (`tasks.py start {task['id']}` la démarre et pose le focus)")
        avis = avis_portee_hors_focus(portee_active(root), task["id"])
        poser_focus(root, task["id"])
    return "\n".join([f"TASKS: focus → {task['id']}", *([avis] if avis else [])])


def declarer_portee(root: str, tids: list[str]) -> str:
    """``tasks.py review-scope <T> [<T>…]`` (S-01M5E50ABADJA72966YQF4J285) : la portée de la
    PROCHAINE revue de clôture, une liste EXPLICITE — parent, lots et enfant NOMMÉS, jamais
    inférés. Chaque membre existe et n'est pas clos ; le focus du clone est ``running`` et dans
    la liste. Un refus liste TOUTES ses causes et n'écrit rien ; un id inconnu refuse d'abord
    (``find``). Écrit ``review-scope.json`` = {focus, members, consumed: [], declared_at} :
    une nouvelle déclaration REMPLACE l'ancienne, et un ``done`` réussi consomme son membre."""
    with board_lock(root):
        data = load(root)
        membres = list(dict.fromkeys(find(data, ref)["id"] for ref in tids))
        causes = [f"{m} est `done` : un membre clos n'est plus à revoir"
                  for m in membres if find(data, m)["state"] == "done"]
        focus = lire_focus(root)
        if focus is None:
            causes.append(f"aucun focus au clone ({FOCUS_NOM} absent) : `tasks.py focus <T running>` d'abord")
        else:
            fid = focus["task_id"]
            etat = next((t["state"] for t in data["tasks"] if t["id"] == fid), None)
            if etat != "running":
                causes.append(f"le focus {fid} n'est pas `running` ({etat or 'absent du board'}) : "
                              f"`tasks.py focus <T running>` d'abord")
            elif fid not in membres:
                causes.append(f"le focus {fid} est absent de la liste : la portée CONTIENT le focus")
        if causes:
            raise BoardError("review-scope refusée — " + " ; ".join(causes) + " — rien n'est écrit")
        portee = {"focus": focus["task_id"], "members": membres, "consumed": [],
                  "declared_at": horodatage_done()}
        with verrou_portee(root):  # le verrou de `consommer_portee` : jamais une réécriture croisée
            ecrire_json_local(chemin_portee(root), portee)
    return (f"TASKS: review-scope → {', '.join(membres)} (focus {portee['focus']}, "
            f"déclarée {portee['declared_at']})")
