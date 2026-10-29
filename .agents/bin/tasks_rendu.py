# tasks_rendu.py — PARTIE de `tasks.py` (T-00000788) : le RENDU —
# table, vue `TASKS.md`, détail, liste groupée, `render_list`, `statusline`.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


def cell(task: dict[str, Any], field: str) -> str:
    if field == "state":
        return f"{STATE_EMOJI[task['state']]} {task['state']}"
    value = task.get(field)
    # THE EPIC IS RENDERED, NEVER STORED IN THE TITLE (T-00001043): `[E-NN]` + the
    # stored title, no separator, so a migrated `[BK-…]` title reads exactly as the
    # old `[E-NN][BK-…]` one in every fixed-width view. A non-string epic never
    # renders (`load` refuses it anyway); `list --json` keeps the raw title.
    if field == "task" and isinstance(task.get("epic"), str) and task["epic"]:
        return f"[{task['epic']}]{value or ''}"
    # A list-valued field (``writeset``) reads as a path list, never as a Python
    # repr: `format_detail` prints EVERY key, including ones added after it.
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or EMPTY
    # A dict-valued field (`depends_motif`) reads as `key → value` pairs, never
    # a Python repr: `format_detail` prints EVERY key outside FIELDS, so a type
    # added to the store later would surface as `{'T-...': '...'}` without this.
    if isinstance(value, dict):
        return ", ".join(f"{k} → {v}" for k, v in sorted(value.items())) or EMPTY
    return str(value or EMPTY)


def fit(text: str, width: int) -> str:
    """Pad or truncate to a FIXED width. Emoji occupy two terminal columns."""
    shown = len(text) + sum(1 for ch in text if ch in "🟢🔴⚪✅")
    if shown > width:
        return text[: max(0, width - 1)] + "…"
    return text + " " * (width - shown)


def render_table(tasks: list[dict[str, Any]]) -> list[str]:
    header = "| " + " | ".join(fit(f, WIDTHS[f]) for f in FIELDS) + " |"
    rule = "|" + "|".join("-" * (WIDTHS[f] + 2) for f in FIELDS) + "|"
    rows = ["| " + " | ".join(fit(cell(t, f), WIDTHS[f]) for f in FIELDS) + " |" for t in tasks]
    return [header, rule] + rows


def sorted_tasks(tasks: list[dict[str, Any]], cap_done: bool = True) -> list[dict[str, Any]]:
    """running → blocked → pending → the most recent done rows, NEWEST FIRST
    inside each group: the running task heads the board, and everything after
    it reads most-recent to oldest so the freshest work is on screen instead of
    buried under whatever was filed first. Sorted on ``sort_key``, never the
    string: a legacy id by its NUMERIC value — a mix of 3-digit and 8-digit
    ids still orders chronologically — and every ``T-<ULID>`` (T-00000726)
    AFTER every legacy id, ULIDs by time. Newest first therefore reads: ULIDs,
    most recent first, then legacy ids from the highest down.

    TWO STABLE PASSES, not one composite key: the id tier holds a string for a
    ULID and an int for a legacy id, which cannot be negated, so the ids are
    sorted newest-first (``reverse=True``) and the state rank is applied after,
    ascending — Python's sort is stable, so each state keeps the id order.

    ``cap_done`` keeps the ``MAX_DONE_SHOWN`` digest bound, and defaults to
    doing so because that IS the board's shape everywhere it is injected. An
    explicit query passes ``False``: the cap answers "what does the board look
    like", not "how many done tasks are there", and quietly dropping rows from
    the second question would be a silent truncation (see ``filter_tasks``)."""
    live = sorted(
        sorted((t for t in tasks if t["state"] != "done"), key=lambda t: sort_key(t["id"]), reverse=True),
        key=lambda t: SORT_ORDER[t["state"]],
    )
    done = sorted((t for t in tasks if t["state"] == "done"), key=lambda t: sort_key(t["id"]), reverse=True)
    return live + (done[:MAX_DONE_SHOWN] if cap_done else done)


def render_view(root: str | os.PathLike[str], data: dict[str, Any] | None = None) -> None:
    data = load(root) if data is None else data
    body = VIEW_HEADER.format(today=date.today().isoformat())
    table = render_table(sorted_tasks(data["tasks"])) if data["tasks"] else ["(no tracked task)"]
    path = view_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "\n" + "\n".join(table) + "\n", encoding="utf-8")


def format_detail(task: dict[str, Any]) -> str:
    """One task, EVERY field, UNTRUNCATED — the shape ``--task`` asks for.

    Deliberately not the table: the view's fixed widths cut a title at 44 chars
    and a stage at 22, which is right for a board digest and wrong for "show me
    this one task" (the whole point of the filter is to stop paying for the
    board to read one row). Keys outside ``FIELDS`` are printed too, so a field
    added to the store later is never silently swallowed by this reader.
    """
    extra = sorted(k for k in task if k not in FIELDS)
    keys = list(FIELDS) + extra
    width = max(len(k) for k in keys)
    lines = [f"## TASK {task['id']}"]
    lines += [f"{key.ljust(width)} : {cell(task, key)}" for key in keys]
    return "\n".join(lines)


def stale_running_warning(tasks: list[dict[str, Any]], today: date) -> str | None:
    """The line(s) saying a task in flight has been sitting there too long.

    ONE LINE PER RUNNING TASK (T-00000188). It used to look at the first running
    task only, which was exactly right while there could be but one; with a
    declared parallel group, stopping at the first would let every other member
    go stale in the silence this warning exists to break. The return shape is
    unchanged — one string, ``None`` when nothing is stale — so the bare ``list``
    and the three SessionStart hooks need no edit: several stale members simply
    arrive as several lines.

    The clock is INJECTED rather than read: a warning computed from
    ``date.today()`` inside the function is untestable except by freezing time
    globally, and the kit's python convention wants every temporal fact of a
    test stamped on the same clock.

    NEVER RAISES. Its only caller is the bare ``list``, which the three hosts'
    SessionStart hooks consume — ``.claude/hooks/session-start.sh`` treats any
    non-zero exit as a broken board — so a garbage ``updated`` is REPORTED, not
    thrown: an unreadable stamp is exactly the case where nobody can vouch for
    the task's freshness, which is what the warning is for.
    """
    tail = "stage/block/done, ou start une autre tâche"
    lines: list[str] = []
    for running in running_tasks(tasks):
        tid = running.get("id", "?")
        raw = running.get("updated") or ""
        try:
            updated = date.fromisoformat(raw)
        except (TypeError, ValueError):
            lines.append(
                f"!! RUNNING STALE — {tid} sans date de mise à jour lisible (updated {raw!r}): {tail}"
            )
            continue
        days = (today - updated).days
        if days >= STALE_RUNNING_DAYS:
            lines.append(
                f"!! RUNNING STALE — {tid} inchangée depuis {days} jours (updated {raw}): {tail}"
            )
    return "\n".join(lines) if lines else None


def group_by_chantier(tasks: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Partition an ALREADY SORTED list into ``(chantier, tasks)`` sections.

    Sorting is not redone here, and that is the point: each section keeps the
    board's own order (running → blocked → pending → done, newest first inside
    each), so a section reads like the board narrowed, not like a second
    ordering the reader has to learn.

    Sections come out alphabetically, ``(sans chantier)`` LAST — the ungrouped
    tasks are the residue of the question "what is grouped", so they belong at
    the bottom whatever their name would sort as. Alphabetical rather than
    by-size because the order must be STABLE across two consecutive reads: a
    section that moves because a task closed is a section the eye has to hunt
    for again.
    """
    sections: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        sections.setdefault(chantier_of(task) or NO_CHANTIER, []).append(task)
    named = sorted((name for name in sections if name != NO_CHANTIER), key=str.casefold)
    ordered = named + ([NO_CHANTIER] if NO_CHANTIER in sections else [])
    return [(name, sections[name]) for name in ordered]


def render_grouped_list(data: dict[str, Any], state: str | None = None) -> str:
    """The board cut into ``### <chantier> (n)`` sections.

    THE SET IS NOT A NEW SET. With no filter it is the bare list's set, done
    digest cap included; with ``--state`` it is exactly what ``filter_tasks``
    already returns, uncapped, because an explicit state filter answers "how
    many" and truncating it would be the silent drop the filters were built to
    avoid. ``--group`` only CUTS a set it never chooses, so the cap behaviour is
    unchanged in both branches rather than re-decided here.

    No stale-running alert: the alert rides the BARE list, whose byte-for-byte
    contract the hooks depend on, and this is a different read.
    """
    if state is None:
        selected = sorted_tasks(data["tasks"])
    else:
        selected = filter_tasks(data, state=state)
    label = filter_label(state=state)
    scope = f" — filter: {label}" if label else ""
    if not selected:
        return f"## TASK BOARD — par chantier{scope}\n(no task matching {label or 'the board'})"
    plural = "" if len(selected) == 1 else "s"
    lines = [f"## TASK BOARD — par chantier{scope} ({len(selected)} task{plural})"]
    for name, section in group_by_chantier(selected):
        lines.append("")
        lines.append(f"### {name} ({len(section)})")
        lines += render_table(section)
    return "\n".join(lines)


def render_list(
    root: str,
    task: str | None = None,
    state: str | None = None,
    chantier: str | None = None,
    group: bool = False,
    blocked_by: str | None = None,
    depends_on: str | None = None,
    responsable: str | None = None,
) -> str:
    """The board as markdown, for SessionStart injection — and, with a filter,
    the narrow read an agent needs when it wants ONE task out of thirty-four.

    THE BARE CALL IS THE CONTRACT, and it is the most load-bearing thing here.
    Since T-00000834 the three SessionStart hooks inject ``render_session_board``
    (``list --session``: pending bounded, cut announced) and FALL BACK to this
    bare call — ``render_list(root)`` positionally in the two python
    ``session_context.py``, a bare ``list`` in ``session-start.sh`` — while the
    board-reporter agents on four hosts parse ``list --json``. The session view
    carries the same alert. That contract is now BOARD UNCHANGED PLUS ONE
    CONDITIONAL ALERT LINE AT THE HEAD: the table, its widths, its order and
    the done cap are byte for byte what they always were, and a stale running
    task inserts ``stale_running_warning`` as line 2, right under the header.
    The alert rides the bare list AND the session view, so it reaches all
    three hosts whichever of the two they inject. The filters stay strictly
    additive, and neither they nor ``--json`` nor ``--statusline`` ever carry
    the alert: a filtered read is a narrow question, and ``--json`` is parsed
    by machines that never asked for prose.

    A FILTER THAT MATCHES NOTHING SAYS SO IN WORDS. An empty table would render
    as an empty BOARD — which a reader cannot tell from "no such task" — and
    the kit's rule is an absence announced, never a silence. A match count is
    printed for the same reason: it proves no row was dropped.

    ``group`` REFUSES rather than ignores. Sectioning one chantier is a
    non-sense the ``--chantier`` filter already answers, a single task has
    no sections at all, and a ``--blocked-by`` fan-out is a flat set with no
    chantier axis to cut — so all three combinations raise here as well as at
    the CLI boundary, for the programmatic callers that never pass through
    argparse. A flag silently dropped is worse than a flag refused: the caller
    reads the output as the answer to the question it asked.
    """
    data = load(root)
    if group:
        if task is not None:
            raise BoardError("--group does not combine with --task: one task has no sections")
        if chantier is not None:
            raise BoardError(
                "--group does not combine with --chantier: sectioning a single group is a "
                "non-sense — use --chantier alone for one group, --group alone for all of them"
            )
        if blocked_by is not None:
            raise BoardError(
                "--group does not combine with --blocked-by: a dependency fan-out has no "
                "chantier axis to cut — use --blocked-by without --group"
            )
        if depends_on is not None:
            raise BoardError(
                "--group does not combine with --depends-on: a dependency fan-out has no "
                "chantier axis to cut — use --depends-on without --group"
            )
        return render_grouped_list(data, state=state)
    if (
        task is None
        and state is None
        and chantier is None
        and blocked_by is None
        and depends_on is None
        and responsable is None
    ):
        tasks = data["tasks"]
        if not tasks:
            return "## TASK BOARD\n(empty — no tracked task)"
        head = ["## TASK BOARD"]
        warning = stale_running_warning(tasks, date.today())
        if warning is not None:
            head.append(warning)
        return "\n".join(head + render_table(sorted_tasks(tasks)))

    matched = filter_tasks(
        data,
        task=task,
        state=state,
        chantier=chantier,
        blocked_by=blocked_by,
        depends_on=depends_on,
        responsable=responsable,
    )
    label = filter_label(
        task=task,
        state=state,
        chantier=chantier,
        blocked_by=blocked_by,
        depends_on=depends_on,
        responsable=responsable,
    )
    if not matched:
        return f"## TASK BOARD — filter: {label}\n(no task matching {label})"
    if task is not None:
        # A single-task query wants the fields, not a row of the digest.
        return "\n\n".join(format_detail(t) for t in matched)
    plural = "" if len(matched) == 1 else "s"
    head = f"## TASK BOARD — filter: {label} ({len(matched)} task{plural})"
    return head + "\n" + "\n".join(render_table(matched))


def render_session_board(root: str, max_pending: int | None = None) -> str:
    """The board as SessionStart injects it: the bare list's shape and order,
    stale-running alert included, with the pending rows BOUNDED to the
    ``max_pending`` most recently updated (default ``SESSION_MAX_PENDING``). Running and blocked are
    never cut — they are what the session must act on.

    WHY A SEPARATE VIEW rather than a cap on the bare list: ``render_list(root)``
    is a byte-for-byte contract the board-reporters and suites read. The three
    SessionStart hooks switch to this view; the bare list is untouched.

    THE CUT IS SAID, with its count and the command that shows the rest, so a
    truncated backlog never reads as a short one.
    """
    cap = SESSION_MAX_PENDING if max_pending is None else max(0, max_pending)
    tasks = load(root)["tasks"]
    if not tasks:
        return "## TASK BOARD\n(empty — no tracked task)"
    rows = sorted_tasks(tasks)
    # KEPT = the most recently TOUCHED pending (``updated``, then id), not the
    # highest ids: a task stopped mid-way today must not sink under a batch of
    # backlog filed after it. Display order stays the bare list's.
    pending = sorted(
        (t for t in rows if t["state"] == "pending"),
        key=lambda t: (str(t.get("updated") or ""), sort_key(t["id"])),
        reverse=True,
    )
    hidden = pending[cap:]
    if hidden:
        drop = {id(t) for t in hidden}
        rows = [t for t in rows if id(t) not in drop]
    head = ["## TASK BOARD"]
    paires = session_paires_tete(root, tasks)
    if paires is not None:
        head.append(paires)
    limites = limite_tete(root, tasks)
    if limites is not None:
        head.append(limites)
    warning = stale_running_warning(tasks, date.today())
    if warning is not None:
        head.append(warning)
    lines = head + render_table(rows)
    if hidden:
        lines.append(
            f"(+{len(hidden)} less recently updated pending not shown — "
            "python .agents/bin/tasks.py list --state pending)"
        )
    return "\n".join(lines)


SESSION_TETE_MAX = 3


def session_paires_tete(root: str, tasks: list[dict[str, Any]]) -> str | None:
    """La ligne de tête ``SESSION-PAIRE:`` de la vue de session (T-01M54GEHJBGA5996W0T48JXNQ4),
    patron ``stale_running_warning`` : ``None`` sans paire VIVANTE, donc la vue reste
    octet pour octet celle d'avant. Au plus ``SESSION_TETE_MAX`` sessions, la coupe DITE ;
    par session, au plus ``SESSION_TETE_TACHES`` tâches encore ``running``, la coupe dite.
    NEVER RAISES — même contrat que ``stale_running_warning`` (le SessionStart lit cette vue)."""
    try:
        paires = sessions_paires(root)
        if not paires:
            return None
        en_vol = {t.get("id") for t in running_tasks(tasks)}
        lignes = [f"SESSION-PAIRE: {len(paires)} session(s) vivante(s) écrivent ce board — pid, tâches tenues, âge"]
        for m in paires[:SESSION_TETE_MAX]:
            tenues = [i for i in m["taches"] if i in en_vol]
            texte = ", ".join(tenues[:SESSION_TETE_TACHES]) or "aucune tâche running"
            if len(tenues) > SESSION_TETE_TACHES:
                texte += f" (+{len(tenues) - SESSION_TETE_TACHES})"
            lignes.append(f"  pid {m['pid']} — {texte} — dernier start/fournée {session_age(m['maj'])}")
        if len(paires) > SESSION_TETE_MAX:
            lignes.append(f"  (+{len(paires) - SESSION_TETE_MAX} session(s) non montrée(s))")
        lignes.append(SESSION_BORNE)
        return "\n".join(lignes)
    except Exception:  # noqa: BLE001 — NEVER RAISES, comme `stale_running_warning`
        return None


# LE RENDU DES LIMITES PAR TÂCHE (T-01M54GEMCH3JWA95G61N2J70KS) : la lecture et le jugement
# vivent dans `tasks_requetes.py` (`depassements`, `limite_jugement`) ; ici, les lignes.
def limite_k(n: int) -> str:
    """Un compte de jetons en milliers, EXACT et en ENTIERS (aucun flottant, donc aucune perte
    au-delà de 2**53) : 240000 → `240k`, 500001 → `500.001k`, 1500 → `1.5k`."""
    if n % 1000 == 0:
        return f"{n // 1000}k"
    return f"{n // 1000}.{n % 1000:03d}".rstrip("0") + "k"


def limite_ligne(d: dict[str, Any]) -> str:
    """C-lignes, bâties sur une entrée de :func:`depassements` (valeurs déjà re-formatées)."""
    if d["type"] == "illisible":
        return f"LIMITE-ILLISIBLE: {d['tache']} champ {d['valeur']}"
    if d["type"] == "jetons":
        return f"LIMITE-DEPASSEE: {d['tache']} jetons : {limite_k(d['valeur'])} / limite {limite_k(d['limite'])}"
    debut, juge = _limite_instant(d["limite"]), _limite_instant(d["valeur"])
    ecart = max(0, int((juge - debut).total_seconds())) if debut and juge else 0
    return (f"LIMITE-DEPASSEE: {d['tache']} délai : échéance {d['limite']} dépassée de "
            f"{ecart // 3600}h{ecart % 3600 // 60:02d}")


def limite_tete(root: str, tasks: list[dict[str, Any]], maintenant: datetime | None = None) -> str | None:
    """La tête ``LIMITE-DEPASSEE:`` de la vue de session (T-01M54GEMCH3JWA95G61N2J70KS, C-tête),
    patron ``session_paires_tete`` : ``None`` sans dépassement ni valeur illisible, donc la vue
    reste octet pour octet celle d'avant. UNE ligne d'en-tête (y compris quand la tête ne porte
    que des illisibles), puis au plus ``SESSION_TETE_MAX`` lignes AU TOTAL, dépassements
    d'abord, la coupe DITE avec la commande qui montre le reste. NEVER RAISES (le SessionStart
    lit cette vue)."""
    try:
        arme = limite_arret_arme(root)
        trouves = depassements({"tasks": tasks}, maintenant, arme)
        if not trouves:
            return None
        n = len({d["tache"] for d in trouves if d["type"] != "illisible"})
        m = sum(1 for d in trouves if d["type"] == "illisible")
        illisibles = f", {m} valeur(s) illisible(s)" if m else ""
        mode = "arrêt armé" if arme else "alerte seule"
        lignes = [f"LIMITE-DEPASSEE: {n} tâche(s) au-delà de leur limite{illisibles} ({mode})"]
        ordre = sorted(trouves, key=lambda d: d["type"] == "illisible")
        lignes += [f"  {limite_ligne(d)}" for d in ordre[:SESSION_TETE_MAX]]
        if len(ordre) > SESSION_TETE_MAX:
            lignes.append(f"  (+{len(ordre) - SESSION_TETE_MAX} ligne(s) non montrée(s) — "
                          "python .agents/bin/tasks.py depassements)")
        return "\n".join(lignes)
    except Exception:  # noqa: BLE001 — NEVER RAISES, comme `session_paires_tete`
        return None


def render_depassements(root: str, as_json: bool = False,
                        maintenant: datetime | None = None) -> tuple[int, str]:
    """`depassements [--json]` : rc 1 dès une entrée (dépassement ou valeur illisible), rc 0
    sinon ; `--json` rend C-json (`[]` sans entrée). Lecture seule, hors `mutating`."""
    arme = limite_arret_arme(root)
    trouves = depassements(load(root), maintenant, arme)
    if as_json:
        return (1 if trouves else 0), json.dumps(trouves, indent=2, ensure_ascii=False)
    mode = "arrêt armé (LIMITE_ARRET)" if arme else "alerte seule"
    if not trouves:
        return 0, f"LIMITE: aucune tâche au-delà de sa limite — {mode}"
    n = sum(1 for d in trouves if d["type"] != "illisible")
    pied = f"LIMITE: {n} dépassement(s), {len(trouves) - n} valeur(s) illisible(s) — {mode}"
    return 1, "\n".join([limite_ligne(d) for d in trouves] + [pied])


def _statusline_chrono(root: str, task: dict[str, Any]) -> str:
    """The ⏱ suffix of ``task`` (``''`` when there is nothing to say). NEVER RAISES."""
    try:
        fournee = task.get("fournee")
        parent = fournee.get("parent") if isinstance(fournee, dict) else None
        if isinstance(parent, str) and parent:
            return task_chrono_module().suffixe_statusline(root, parent, lot=task["id"])
        return task_chrono_module().suffixe_statusline(root, task["id"])
    except Exception:  # noqa: BLE001 — the status line never raises
        return ""


def statusline(root: str) -> str:
    """One compact line: the FOCUS task, a `∥N` suffix when N tasks are running —
    grouped or not, since T-01M5F7286N1EYGXAXA5244X86B — plus pending/done counters.

    The focus is ``focus_task``'s rule — the first running task in store order —
    and the suffix appears ONLY above one running task, so the single-task line
    every host renders today is byte for byte unchanged.

    THE OPEN CHRONO STEP (T-01M5KKFBCXXEVYR8GJPYFEH3C8) : ` · ⏱ <step> <elapsed>/~<median>|?[ +N]`
    right after the focus id, BEFORE the stage detail (C12 : the detail is unbounded, the suffix is
    not — at most ``task_chrono.SUFFIXE_MAX`` chars), then ` · <detail>`, cut to 24 chars (``[:23] + "…"``,
    decision S-01M5KZ4HSR): under the worst suffix produced (35 chars), a detail over 24 chars grows the
    line by 36 at most, a shorter one by the suffix plus its separator (``SUFFIXE_MAX + 2`` at most). A
    lot reads its PARENT's
    journal under its own key. No open step, an absent journal or any error : the line above, byte for
    byte. Read from ``root`` as is, without git — in a linked worktree the journal lives at the common
    root, so the suffix is absent there."""
    try:
        tasks = load(root)["tasks"]
    except BoardError:
        return "board malformed"
    if not tasks:
        return "no active task"
    running = running_tasks(tasks)
    blocked = [t for t in tasks if t["state"] == "blocked"]
    pending = sum(1 for t in tasks if t["state"] == "pending")
    done = sum(1 for t in tasks if t["state"] == "done")
    if running:
        task = running[0]
        detail = task.get("stage") or task.get("owner") or task["task"][:24]
        chrono = _statusline_chrono(root, task)
        if chrono:
            # Décision S-01M5KZ4HSR : sous le suffixe, le détail tient en 24 caractères. Avec le pire suffixe
            # produit (35 caractères), un détail de plus de 24 caractères n'allonge la ligne d'avant que de 36
            # au plus ; un détail plus court, du suffixe et de son séparateur (SUFFIXE_MAX + 2 au plus).
            if len(detail) > 24:
                detail = detail[:23] + "…"
            head = f"▶ {task['id']}{chrono}{' · ' + detail if detail.strip() else ''}".rstrip()
        else:
            head = f"▶ {task['id']} {detail}".rstrip()
        if len(running) > 1:
            head = f"{head} ∥{len(running)}"
    elif blocked:
        head = f"⛔ {blocked[0]['id']} blocked"
    else:
        head = "no active task"
    return f"{head} · ⏸{pending} ✓{done}"
