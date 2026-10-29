# tasks_graphe.py — PARTIE de `tasks.py` (T-00000788) : le GRAPHE déclaré —
# writeset, dépendances (`depends`, `depends-show`), groupes parallèles.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


def set_writeset(root: str, tid: str, paths: list[str], clear: bool = False) -> str:
    """Declare (or rewrite) the set of files a task is allowed to write.

    REWRITABLE like ``owner`` and ``chantier``, state-free for the same reason,
    and ``--clear`` drops the key entirely — "no writeset" keeps ONE stored
    shape, absent, shared with every task minted before T-00000188.

    A WRITESET INCLUDES ITS GENERATED OUTPUTS. A task that rebuilds a bundle
    writes that bundle: declaring only the sources would prove a disjunction the
    build then breaks. The kit's own case is `.agents/ui/`, regenerated wholesale
    from `.agents/ui-src/`.

    NOTHING IS WRITTEN IF ONE PATH IS REFUSED: the first inadmissible path
    raises with its diagnostic (path, failed clause, canonical example) and the
    task keeps whatever it had. A partial writeset would be a proof computed on
    half a declaration.

    WRITING A WRITESET RETRACTS THE PROOF THAT USED IT, so this DROPS the task's
    ``parallel_group`` and says so (T-00000188 review, MEDIUM b). The measured
    defect was ``--clear``: it emptied the declaration and left the group alive,
    re-introducing after the fact exactly the vacuity ``declare_parallel_group``
    refuses at the declaration — one running member with no writeset at all, the
    board still green, nobody told. A rewrite has the same effect for the same
    reason (the disjunction was computed on the OLD paths), so both branches drop
    it rather than one special case remembering to.

    Dropping it while members run is no longer refused (T-01M5F7286N1EYGXAXA5244X86B:
    several running tasks are a legitimate board); the drop is SAID in the output.
    Re-declare with ``parallel`` afterwards. This stays a coherence guard, never
    an observer (T-00000189).
    """
    if clear and paths:
        raise BoardError("writeset --clear takes no path; it drops the whole declaration")
    if not clear and not paths:
        raise BoardError(
            f"writeset {tid} expects at least one path, or --clear to drop the declaration"
        )
    admitted: list[str] = []
    for raw in paths:
        candidate = admitted_writeset_path(raw)
        if candidate not in admitted:
            admitted.append(candidate)
    with board_lock(root):
        data = load(root)
        # Exact-match `find`, like every other write verb: a mistyped
        # `writeset 5` must never re-declare T-00000005 by numeric luck.
        task = find(data, tid)
        before = copy.deepcopy(task)
        if clear:
            task.pop("writeset", None)
        else:
            task["writeset"] = admitted
        dropped = task.pop("parallel_group", "")
        task["updated"] = date.today().isoformat()
        # Dropping the group of a task running BESIDE other members is no longer
        # refused (T-01M5F7286N1EYGXAXA5244X86B): several running tasks are a
        # legitimate board, the dropped group is SAID below.
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    tail = (
        f" — declared group {dropped} dropped: its proof was computed on the previous "
        f"writeset, re-declare with `tasks.py parallel …`"
        if dropped
        else ""
    )
    if clear:
        return f"TASKS: {tid} writeset cleared{tail}"
    plural = "" if len(admitted) == 1 else "s"
    return f"TASKS: {tid} writeset = {len(admitted)} path{plural}: {', '.join(admitted)}{tail}"


def set_depends(
    root: str,
    tid: str,
    deps: list[str],
    clear: bool = False,
    motif: str | list[str] = "",
    *,
    add: bool = False,
    retirer: str | None = None,
    retirer_ordre_pilote: list[str] | None = None,
) -> str:
    """Declare which tasks ``tid`` is BEHIND — a total rewrite BY DEFAULT, like
    ``writeset``, GUARDED since T-00000765 (an ``ORDRE PILOTE S-<id>`` edge is
    never erased nor re-motived by a rewrite or ``--clear``); ``--add`` unions,
    ``--retirer`` drops ONE technical edge, ``--retirer-ordre-pilote`` drops an
    ORDRE PILOTE under a DISTINCT decision. The verb logic lives in
    ``plan_depends.appliquer_verbe`` (S-00002684), ``find``/``dependency_cycle``
    passed as ARGUMENTS. STRUCTURAL CONTROL FIRST (A-C1 it. 5): module absent ⇒
    a NEW verb is refused whatever the marker, ANY mutation is refused under
    ``PLAN_CIBLE_REQUIRED``; inert ONLY with marker absent AND old verb (the
    pre-T-765 block below, unchanged). STATE-FREE; acyclicity proven HERE (a
    guard in ``load`` would refuse the ``--retirer`` that repairs a cycle);
    NOTHING IS WRITTEN ON THE FIRST REFUSAL."""
    pd = plan_depends_module()
    retrait = retirer is not None or retirer_ordre_pilote is not None
    verbe_neuf = add or retrait
    if pd is None and verbe_neuf:
        raise BoardError(_REFUS_DEPENDS_VERBE_SANS_MODULE.format(geste=f"depends {tid} (--add/--retirer/--retirer-ordre-pilote)"))
    if pd is None and cible_marqueur_present(root):
        raise BoardError(_REFUS_DEPENDS_INEXPLOITABLE.format(geste=f"depends {tid}"))
    # NORMALISE TO A LIST OF STRIPPED MOTIFS FIRST, before any test reads them.
    # `--motif` is `action="append"`, so the CLI hands a list ([] when absent);
    # direct python callers still pass a scalar str. `(x or "").strip()` per
    # element (modelled on `reopen_task`) is None-safe and drops surrounding
    # whitespace so "   " reads as empty. A pure local binding — no I/O — so it
    # moves nothing relative to the lock. `or [""]` keeps an absent flag as one
    # empty motif, which the content check then refuses with "requires --motif".
    motifs = [(m or "").strip() for m in ([motif] if isinstance(motif, str) else motif)] or [""]
    if sum(1 for x in (add, clear, retirer is not None, retirer_ordre_pilote is not None) if x) > 1:
        raise BoardError(f"depends {tid}: --add, --clear, --retirer and --retirer-ordre-pilote are mutually exclusive")
    if retrait and (deps or any(motifs)):
        raise BoardError(f"depends {tid} --retirer/--retirer-ordre-pilote takes neither a positional id nor --motif: name the ONE edge to drop")
    if clear and deps:
        raise BoardError(
            f"depends --clear takes no id (received {len(deps)}); "
            f"`tasks.py depends {tid} --clear` removes the declaration entirely"
        )
    # --clear removes the whole declaration, so there is no edge left to
    # motivate: a --motif alongside it would be silently discarded (B-C7).
    if clear and any(motifs):
        raise BoardError(
            f"depends {tid} --clear takes no --motif: there is no edge left to motivate"
        )
    if not clear and not retrait and not deps:
        raise BoardError(
            f"depends {tid} expects at least one task id, or --clear to remove "
            f"the declaration"
        )
    # THE MOTIF IS REQUIRED AND SINGLE-LINE — ARGUMENT checks, so they live
    # ABOVE the lock and ABOVE `find`: everything past `board_lock` takes the
    # lock and loads the store for a mistyped argument, and everything past
    # `find(data, tid)` would invert the order of refusals. They come AFTER the
    # empty-deps check so a bare `depends <id>` still reports "expects at least
    # one task id". The COUNT is checked first — ONE motif for the whole
    # declaration (uniform), or exactly one per id in order — then each motif's
    # CONTENT: a motif is rendered on ONE row and read back by grep, so any line
    # boundary is refused (newline, carriage return, U+2028, VT, FF, NEL —
    # `splitlines` is the bound, never a closed two-character list), and the
    # faulty POSITION is named when several motifs were given.
    if not clear and not retrait and len(motifs) not in (1, len(deps)):
        raise BoardError(
            f"depends {tid}: give ONE --motif for the whole declaration, or exactly "
            f"{len(deps)} (one per id, in order) — received {len(motifs)}"
        )
    if not clear and not retrait:
        for i, m in enumerate(motifs):
            if m and len(m.splitlines()) <= 1:
                continue
            where = f" (motif #{i + 1})" if len(motifs) > 1 else ""
            detail = (
                "a line boundary is refused (newline, carriage return, U+2028, "
                "VT, FF, NEL): a motif is rendered on one row and read back by grep"
                if m
                else "a dependency is an ORDER, and an order with no stated reason "
                "is one nobody can weigh later"
            )
            raise BoardError(f"depends {tid} requires --motif{where}: {detail}")
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        wanted: list[str] = []
        motif_by_dep: dict[str, str] = {}
        sortie = None
        if pd is not None:
            # TOUTE la logique du verbe vit dans le frère ; `find` (:1134) et
            # `dependency_cycle` lui arrivent en ARGUMENTS (M13, jamais un import).
            mode = ("clear" if clear else "add" if add else "retirer" if retirer is not None
                    else "retirer_ordre_pilote" if retirer_ordre_pilote is not None else "reecriture")
            try:
                wanted, motif_by_dep, sortie = pd.appliquer_verbe(
                    task, deps, motifs, mode=mode, resoudre=lambda raw: find(data, raw)["id"],
                    cycle_de=lambda w: dependency_cycle(_depends_adjacency(data["tasks"]), task["id"], w),
                    decisions=lambda: pd.decisions_du_journal(root), taches=data["tasks"],
                    retrait=(retirer, None) if retirer is not None else
                    (tuple((list(retirer_ordre_pilote) + [None, None])[:2]) if retirer_ordre_pilote is not None else None))
            except ValueError as exc:
                raise BoardError(str(exc)) from exc
            for avert in sortie.avertissements:
                print(avert, file=sys.stderr)
        elif not clear:  # REPLI d'avant T-765, inchangé : marqueur absent, verbe ancien
            for i, raw in enumerate(deps):
                # EXACT resolution, like every writing verb: a mistyped `depends
                # T-5` must never link T-00000005 by numeric luck.
                dep = find(data, raw)["id"]
                if dep == task["id"]:
                    raise BoardError(
                        f"{tid} cannot depend on itself: nothing would ever satisfy it"
                    )
                if dep not in wanted:
                    wanted.append(dep)
                    # PAIR by the input POSITION `i`, captured as the id is kept:
                    # ONE motif applies uniformly, N map one-to-one in the order
                    # ids were given, and a duplicate id keeps the motif of its
                    # FIRST occurrence (the later ones are dropped with it). Done
                    # here rather than with `deps.index(dep)` so no second scan is
                    # needed and duplicates cannot mispair.
                    motif_by_dep[dep] = motifs[0] if len(motifs) == 1 else motifs[i]
            cycle = dependency_cycle(_depends_adjacency(data["tasks"]), task["id"], wanted)
            if cycle is not None:
                raise BoardError(
                    f"declaring this would close a cycle: {' → '.join(cycle)}. "
                    f"Nothing was written — the edge that closes it is "
                    f"{cycle[-2]} → {cycle[-1]}; drop it, or clear the declaration "
                    f"with `tasks.py depends {cycle[-2]} --clear`"
                )
        deduped = len(deps) - len(wanted) if not clear else 0
        if clear or not wanted:
            task.pop("depends_on", None)
            task.pop("depends_motif", None)
        else:
            task["depends_on"] = wanted
            # PER EDGE since T-00000645: `--motif` is repeatable, so ONE value
            # applies to every edge (uniform) or N values map one-to-one to the
            # ids in order. Ignored by the V3 snapshot (SYNC_SNAPSHOT_FIELDS).
            # GUARDED since T-00000765: an inherited edge has no motif, and the
            # key is never minted from nothing (mirror of `_clear_dangling_blocked_on`).
            filtre = {dep: motif_by_dep[dep] for dep in wanted if motif_by_dep.get(dep)}
            if filtre:
                task["depends_motif"] = filtre
            else:
                task.pop("depends_motif", None)
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    if sortie is not None:
        return sortie.texte
    if clear:
        return f"TASKS: {tid} depends_on cleared"
    # A SILENT DEDUPLICATION READS AS A FAITHFUL RECORD. Say it when the count moved.
    tail = f" ({deduped} duplicate id{'' if deduped == 1 else 's'} dropped)" if deduped else ""
    plural = "y" if len(wanted) == 1 else "ies"
    return (
        f"TASKS: {tid} depends_on = {len(wanted)} dependenc{plural}: "
        f"{', '.join(wanted)}{tail}"
    )


def render_depends_show(root: str, tid: str) -> str:
    """Read each OUTGOING edge of ``tid``: the dependency, its state, its class
    and the motif. NEVER a refusal on a dangling edge — a store edited by hand
    can point at a task that left the board, and reporting that is the whole
    point; raising there would be the very rc-2 refusal this reader must not be.

    THE CLASS HAS THREE EXHAUSTIVE VALUES, and ``PENDOUILLANTE`` is TESTED, never
    concluded from ``not SATISFAITE``: on a three-valued domain the couple
    ``not satisfied ⇒ dangling`` would report every healthy WAITING edge as
    dangling — a false report that invites ``depends --clear``, which DESTROYS a
    real declaration. The referent's ABSENCE is tested by a lookup that RAISES.

    The motif is rendered independently of the class: a SATISFAITE edge can be
    motiveless and an EN ATTENTE edge can carry one — the two axes never imply
    each other. This reader CLASSIFIES; it writes nothing to the store."""
    data = load(root)
    # SHORT FORM tolerated on the SUBJECT, like every other reader (`list`,
    # `specs.py list`): `resolve_id` maps `T-2`/`2` to the stored id and RAISES
    # on unknown or ambiguous. The "never raise" rule of this reader is about the
    # REFERENT of each edge (a dangling dependency is reported, not refused), not
    # about the task being asked for (A-C6/B-C5).
    task = find(data, resolve_id(data, tid))
    declared = depends_on_of(task)
    motifs = task.get("depends_motif", {}) or {}
    lines = [f"## DEPENDS {task['id']}"]
    if not declared:
        lines.append("(aucune dépendance déclarée)")
        return "\n".join(lines)
    _pd = plan_depends_module(lecture=True)  # classe du motif (T-00000765) ; absent OU cassé = ligne inchangée
    for dep in declared:
        try:
            other = find(data, dep)
        except BoardError:
            other = None
        if other is None:
            etat, classe = "?", "PENDOUILLANTE"
        elif other["state"] == "done":
            etat, classe = other["state"], "SATISFAITE"
        else:
            etat, classe = other["state"], "EN ATTENTE"
        motif = (motifs.get(dep) or "").strip()
        motif_txt = f"motif : {motif}" if motif else "SANS MOTIF (héritée)"
        genre = f" · {_pd.classe_motif(motif)}" if _pd is not None else ""
        lines.append(f"{dep} → {etat} : {classe} ({motif_txt}){genre}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# L'AMONT D'ABORD (T-01M4Z5VJ1DYQZM67AYHTACKFTA, décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T).
# `depends_on` ORDONNE ET GARDE : tout `start` hors `running` (depuis pending, blocked
# OU done) et la fournée refusent un amont ouvert, sauf `--sans-dependances`, VISIBLE.
# `done` reste un DIRE. BORNE : seul le `depends_on` DÉCLARÉ est lu — une dépendance
# non déclarée n'est pas vue, et l'avis d'écriture partagée de `deps-ready` n'est
# jamais une preuve.
# ---------------------------------------------------------------------------
#: Les jetons de 1re ligne de `deps-ready`, liste FERMÉE et dans l'ordre de PRÉCÉDENCE :
#: le premier qui s'applique est rendu — CYCLE > AMONT_OUVERT > INEXPLOITABLE >
#: PLAN_A_REPLANIFIER | REPRISE_DITE > AMONT_CLOS. Les deux du milieu ont la MÊME
#: condition (un amont clos à ou après la trace élue) ; `lancee_sous` et `lancee_le` les départagent.
#: Recopiée dans `.agents/ref/TASKS_CLI_CONTRACT.json` (`definitions`) et `.md` § 4,
#: épinglée par `test_tasks_cli_contract.py`.
DEPS_READY_JETONS = ("CYCLE", "AMONT_OUVERT", "INEXPLOITABLE", "PLAN_A_REPLANIFIER", "REPRISE_DITE", "AMONT_CLOS")
#: Les jetons qui laissent passer `start` (rc 0 de `deps-ready`) ; les autres rendent 1.
DEPS_READY_PASSANTS = frozenset({"AMONT_CLOS", "REPRISE_DITE"})
#: La marque d'un `start` sous `--sans-dependances`, posée QUEL QUE SOIT le marqueur :
#: la jambe d'amont n'est pas armée par `PLAN_CIBLE_REQUIRED`, sa dérogation non plus.
MARQUE_SANS_DEPENDANCES = "[SANS DÉPENDANCES : arête + amont — {}]"
#: Une dérogation sans raison n'est pas VISIBLE : `--sans-dependances "   "` est refusé, rien n'est écrit
#: (avis de sécurité du lot A) — à `start`, à `done` (`set_state`) et à la fournée, avant tout lot.
REFUS_SANS_DEPENDANCES_VIDE = (
    "TASKS: refus de {geste} — `--sans-dependances` exige une raison NON VIDE (reçu {raison!r}) : une "
    "dérogation sans raison ne dit rien au board. Rien n'est écrit.")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_EPOQUE = datetime(1970, 1, 1, tzinfo=timezone.utc)
_DONE_AT = "%Y-%m-%dT%H:%M:%S.%fZ"


def horodatage_done() -> str:
    """`done_at` : l'instant UTC de l'ENTRÉE dans `done`, à la MILLISECONDE (`…T…:…:….mmmZ`)."""
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def _ms_utc(instant: datetime) -> int:
    """Millisecondes depuis l'époque, en ARITHMÉTIQUE ENTIÈRE (jamais `timestamp() * 1000`)."""
    d = instant - _EPOQUE
    return d.days * 86_400_000 + d.seconds * 1000 + d.microseconds // 1000


def _instant_done_at(valeur: Any) -> datetime | None:
    """`done_at` relu ; illisible ⇒ `None`, et la tâche est jugée comme sans `done_at` (cas c)."""
    try:
        return datetime.strptime(str(valeur), _DONE_AT).replace(tzinfo=timezone.utc) if valeur else None
    except ValueError:
        return None


def _ms_de_sid(sid: str) -> int | None:
    """L'instant d'une S-id `S-<ULID>` (10 premiers symboles Crockford) ; `None` pour une S- numérique."""
    m = re.fullmatch(r"S-([0-9A-HJKMNP-TV-Z]{26})", sid or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1)[:10]:
        n = n * 32 + _CROCKFORD.index(ch)
    return n


def sid_elue_ou_rien(root: str, tid: str) -> str | None:
    """La S-id de la trace `plan approuvé` ÉLUE de `tid` (SYM-18172), ou `None` — SANS REFUS :
    `plan_cible` absent (copie partielle, `run-recap.test.sh`) ou SPECS illisible n'inscrivent
    rien. C'est la valeur de `lancee_sous` ; le jugement, lui, est fail-closed (`releve_amont`)."""
    try:
        pc = plan_cible_module()
    except (ImportError, SyntaxError, OSError):  # frère CASSÉ : une inscription facultative ne plante jamais
        return None
    if pc is None:
        return None
    try:
        elue = pc.trace_plan_approuve(root, tid)
    except (pc.CibleError, OSError, ValueError):
        return None
    return elue[1] if elue else None


def inscrire_lancee_sous(root: str, task: dict[str, Any]) -> None:
    """À une sortie de `running`, `lancee_sous` S'IL MANQUE (tâche lancée avant ce code)."""
    if not task.get("lancee_sous"):
        sid = sid_elue_ou_rien(root, task["id"])
        if sid:
            task["lancee_sous"] = sid


def effacer_cycle_clos(task: dict[str, Any]) -> None:
    """`lancee_sous`, `lancee_le` et `done_at` décrivent le cycle CLOS : effacés à TOUTE sortie de
    `done` (`start`, `block`, `reopen`) — gardés, un plan périmé serait repris en REPRISE_DITE."""
    task.pop("lancee_sous", None)
    task.pop("lancee_le", None)
    task.pop("done_at", None)


def _cycle_amont(par_id: dict[str, dict[str, Any]], tid: str) -> list[str] | None:
    """Le premier cycle ATTEIGNABLE depuis `tid` en suivant `depends_on` (à travers les `done`),
    `[x, …, x]` dans le sens des arêtes (`chemin[i]` dépend de `chemin[i+1]`), ou `None`.
    Itératif : un board édité à la main peut porter un cycle que `load` accepte."""
    couleur = {tid: 1}
    chemin = [tid]
    pile = [iter(depends_on_of(par_id[tid]))]
    while pile:
        suivant = next(pile[-1], None)
        if suivant is None:
            couleur[chemin.pop()] = 2
            pile.pop()
            continue
        if suivant not in par_id:
            continue  # PENDOUILLANTE : satisfaite, jamais un cycle
        etat = couleur.get(suivant, 0)
        if etat == 1:
            return chemin[chemin.index(suivant):] + [suivant]
        if etat == 0:
            couleur[suivant] = 1
            chemin.append(suivant)
            pile.append(iter(depends_on_of(par_id[suivant])))
    return None


def _jour_de_trace(pc: Any, index: dict[str, list[dict[str, Any]]], tid: str, sid: str,
                   ms: int | None) -> str | None:
    """Le jour LOCAL de la trace : celui de l'instant ULID, sinon le champ `date` de l'entrée."""
    if ms is not None:
        return datetime.fromtimestamp(ms / 1000).date().isoformat()
    entree = next((e for e in reversed(pc.entrees_de(index, tid)) if e.get("id") == sid), {})
    jour = str(entree.get("date") or "")
    return jour if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", jour) else None


def _replanification(root: str, tid: str, task: dict[str, Any], clos: list[dict[str, Any]],
                     r: dict[str, Any]) -> None:
    """Juge la trace élue contre les ancêtres CLOS (fermeture complète) ; remplit `r`. Lit
    `plan_cible` SEULEMENT ici, donc seulement si un ancêtre est `done` : absent, ou SPECS
    illisible, c'est INEXPLOITABLE (fail-closed, dérogeable par `--sans-dependances`)."""
    try:
        pc = plan_cible_module()
    except (ImportError, SyntaxError, OSError) as exc:  # frère CASSÉ : `deps-ready` est une LECTURE
        r.update(jeton="INEXPLOITABLE", causes=[
            f"`.agents/bin/plan_cible.py` ne se charge pas ({type(exc).__name__}) : la replanification n'est pas "
            "jugée — `git checkout -- .agents/bin/plan_cible.py`"])
        return
    if pc is None:
        r.update(jeton="INEXPLOITABLE", causes=[
            f"`.agents/bin/plan_cible.py` est absent : {len(clos)} amont(s) clos, la replanification n'est pas "
            "jugée — `git checkout -- .agents/bin/plan_cible.py`"])
        return
    try:
        index = pc.index_par_tache(pc.entrees_specs(root))
        elue = pc.trace_plan_approuve(root, tid, index)
    except (pc.CibleError, OSError, ValueError) as exc:
        # Le TYPE seul, jamais le message : celui de `CibleError` porte le chemin ABSOLU du journal (avis de sécurité).
        r.update(jeton="INEXPLOITABLE", causes=[
            f"journal SPECS illisible ({type(exc).__name__}) : la replanification n'est pas jugée — répare "
            "le journal (`python .agents/bin/specs.py list` le relit)"])
        return
    r["trace_lue"] = True
    if elue is None:
        titre = pc.normalise_titre("plan approuvé")
        brutes = [e for e in pc.entrees_de(index, tid)
                  if e.get("kind") == "decision" and pc.normalise_titre(e.get("title") or "") == titre]
        if brutes:  # N1 : trace présente mais NON ÉLUE (plan absent ou modifié) — dit, jamais tu
            r["avis"].append(f"trace {brutes[-1].get('id')} non élue (plan absent ou modifié depuis "
                             f"l'approbation) : replanification NON JUGÉE sur {len(clos)} amont(s) clos")
        return
    sid = r["sid"] = elue[1]
    ms = _ms_de_sid(sid)
    jour_trace = _jour_de_trace(pc, index, tid, sid, ms)
    if jour_trace is None:
        r.update(jeton="INEXPLOITABLE", causes=[f"trace {sid} sans date lisible : la replanification n'est pas jugée"])
        return
    replan: list[str] = []
    causes_t: list[dict[str, Any]] = []  # les amonts qui ont produit une ligne `replan`
    for t in clos:
        avant = len(replan)
        fin = _instant_done_at(t.get("done_at"))
        if fin is not None and ms is not None:  # (a) S-<ULID> : à la milliseconde, l'égalité est PÉRIMÉE
            if _ms_utc(fin) >= ms:
                replan.append(f"{t['id']} clos le {t['done_at']}, à ou après la trace {sid}")
        elif fin is not None:  # (b) S- numérique : à la journée LOCALE de `done_at`
            jour = fin.astimezone().date().isoformat()
            if jour > jour_trace:
                replan.append(f"{t['id']} clos le {jour}, après le jour de la trace {sid} ({jour_trace})")
            elif jour == jour_trace:
                r["avis"].append(f"{t['id']} clos le jour de la trace {sid} ({jour_trace}) : ordre NON PROUVÉ "
                                 "(S- numérique, à la journée)")
        else:  # (c) sans `done_at` (clos avant ce code) : le jour de `updated`, NON PROUVÉ
            jour = str(t.get("updated") or "")
            if jour > jour_trace:
                replan.append(f"{t['id']} clos sans done_at, touché le {jour}, après le jour de la trace {sid} "
                              f"({jour_trace})")
            elif jour == jour_trace:
                r["avis"].append(f"{t['id']} clos sans done_at, touché le jour de la trace {sid} : ordre NON PROUVÉ")
        if len(replan) > avant:
            causes_t.append(t)
    if replan:
        r["causes"] = replan
        # LA REPRISE NE COUVRE QUE CE QUI PRÉCÈDE LE LANCEMENT (décision du 2026-10-15, revue de clôture C6) :
        # lancée sous CETTE trace ET chaque amont cause clos au plus tard à `lancee_le` (l'égalité à la ms est
        # une reprise). Un amont clos APRÈS le lancement (rouvert puis re-clos pendant que la tâche attendait)
        # ⇒ PLAN_A_REPLANIFIER. Une cause SANS `done_at` est tenue pour close AVANT le lancement : `done_at`
        # est posé à TOUTE entrée dans `done` depuis ce code (seul écrivain : `set_state`), plus ancien que
        # tout `lancee_le` — elle a donc été close avant lui (cas c, P7 de l'exec-critic). Un `done_at`
        # ILLISIBLE se lit comme absent (`_instant_done_at`) et tombe donc du côté de la REPRISE ; un
        # `lancee_le` PRÉSENT mais illisible ne prouve rien : PLAN_A_REPLANIFIER (fail-closed). BORNES :
        # sans `lancee_le` (tâche lancée avant ce champ, ou `lancee_sous` inscrit à la sortie de `running`),
        # la reprise reste celle d'avant ; un arbre SANS ce code n'écrit ni n'efface `done_at` : l'amont qu'il re-clôt
        # n'en a pas (tenu pour antérieur) ou garde celui de sa clôture PRÉCÉDENTE (plus même une cause : AMONT_CLOS).
        brut_le = task.get("lancee_le")
        lance = _instant_done_at(brut_le)
        reprise = task.get("lancee_sous") == sid and (not brut_le or (lance is not None and all(
            (f := _instant_done_at(c.get("done_at"))) is None or f <= lance for c in causes_t)))
        if task.get("lancee_sous") == sid and not reprise:  # le refus dit SA raison (revue de clôture 2, F6)
            r["avis"].append(f"lancée sous {sid} le {brut_le} : `lancee_le` illisible, la reprise n'est pas prouvée"
                             if lance is None else
                             f"lancée sous {sid} le {brut_le} : un amont en cause a été clos APRÈS ce lancement")
        r["jeton"] = "REPRISE_DITE" if reprise else "PLAN_A_REPLANIFIER"


def releve_amont(root: str, tid: str, data: dict[str, Any]) -> dict[str, Any]:
    """LE JUGEMENT D'AMONT de `tid` sur `data` — lu par `deps-ready`, `set_state` (tout `start`
    hors `running`) et la fournée (à blanc). N'écrit rien, ne prend aucun verrou. Rend
    `{jeton, ouverts, pendouillantes, chemin, causes, avis, sid, trace_lue}` :
      * fermeture TRANSITIVE des amonts NON `done` : un `done` arrête la liste ouverte ; un id
        absent du board est PENDOUILLANT, satisfait et nommé ; ordre de Kahn, amont d'abord,
        départage par `sort_key` ; chaque ouvert dit son état, son motif et qui le tire ;
      * CYCLE : le premier cycle atteignable (à travers les `done` aussi), chemin complet ;
      * sans ouvert, les ancêtres `done` de la fermeture COMPLÈTE sont jugés contre la trace
        `plan approuvé` ÉLUE (`_replanification`) — aucune trace : rien à dire.
    `jeton` suit la précédence de `DEPS_READY_JETONS`."""
    par_id = {t["id"]: t for t in data["tasks"]}
    task = par_id[tid]
    r: dict[str, Any] = {"jeton": "AMONT_CLOS", "ouverts": [], "pendouillantes": [], "chemin": None,
                         "causes": [], "avis": [], "sid": None, "trace_lue": False, "clos": 0}
    chemin = _cycle_amont(par_id, tid)
    if chemin is not None:
        r.update(jeton="CYCLE", chemin=chemin)
        return r
    tire: dict[str, tuple[str, str]] = {}
    file_, vus, clos_vus = [tid], {tid}, set()
    i = 0
    while i < len(file_):
        aval = par_id[file_[i]]
        i += 1
        motifs = aval.get("depends_motif") or {}
        for amont in depends_on_of(aval):
            t = par_id.get(amont)
            if t is None:
                if all(p[0] != amont for p in r["pendouillantes"]):
                    r["pendouillantes"].append((amont, aval["id"]))
            elif t["state"] == "done":
                clos_vus.add(amont)
            elif amont not in vus:
                vus.add(amont)
                file_.append(amont)
                tire[amont] = (aval["id"], str(motifs.get(amont) or "").strip())
    if tire:
        # KAHN, amont d'abord : un ouvert sort quand ses propres amonts ouverts sont sortis.
        attente = {u: {d for d in depends_on_of(par_id[u]) if d in tire} for u in tire}
        prets = sorted((u for u, deps in attente.items() if not deps), key=sort_key)
        while prets:
            u = prets.pop(0)
            aval, motif = tire[u]
            r["ouverts"].append({"id": u, "etat": par_id[u]["state"], "aval": aval, "motif": motif})
            for v, deps in attente.items():
                if u in deps:
                    deps.discard(u)
                    if not deps:
                        prets.append(v)
            prets.sort(key=sort_key)
        r["jeton"] = "AMONT_OUVERT"
        return r
    # Les ancêtres CLOS sur la fermeture COMPLÈTE (un grand-parent clos compte, à travers un parent clos).
    pile = list(clos_vus)
    while pile:
        for d in depends_on_of(par_id[pile.pop()]):
            if d in par_id and d not in clos_vus and par_id[d]["state"] == "done":
                clos_vus.add(d)
                pile.append(d)
    clos = sorted((par_id[c] for c in clos_vus), key=lambda t: sort_key(t["id"]))
    r["clos"] = len(clos)
    if clos:
        _replanification(root, tid, task, clos, r)
    return r


def lignes_releve(r: dict[str, Any], data: dict[str, Any] | None = None) -> list[str]:
    """Le détail d'un relevé, une ligne par fait, SANS la 1re ligne `deps-ready: <JETON>`."""
    out: list[str] = []
    jeton = r["jeton"]
    if jeton == "CYCLE":
        _pd = plan_depends_module(lecture=True)
        coupe = (_pd.remede_coupe(data, r["chemin"]) if _pd is not None and data is not None
                 else f"`tasks.py depends {r['chemin'][0]} --retirer {r['chemin'][1]}`")
        out.append(f"chemin : {' → '.join(r['chemin'])} — coupe-le : {coupe}")
    for rang, o in enumerate(r["ouverts"], 1):
        etat = "blocked (attend une décision)" if o["etat"] == "blocked" else o["etat"]
        motif = f"motif : {o['motif']}" if o["motif"] else "SANS MOTIF (héritée)"
        out.append(f"{rang}. {o['id']} — {etat} — tirée par {o['aval']} <- {o['id']} ({motif})")
    if jeton == "REPRISE_DITE":
        out.append(f"lancée sous {r['sid']} : reprise DITE, jamais une révision")
    out += [f"amont clos après la trace : {c}" if jeton in ("PLAN_A_REPLANIFIER", "REPRISE_DITE") else c
            for c in r["causes"]]
    out += [f"PENDOUILLANTE {p} (absente du board, satisfaite) — tirée par {aval}" for p, aval in r["pendouillantes"]]
    out += [f"avis : {a}" for a in r["avis"]]
    if jeton == "AMONT_CLOS" and not out:
        out.append(f"aucun amont ouvert ({r['clos']} amont(s) clos)" if r["clos"] else "aucune dépendance déclarée")
    return out


def refus_amont(geste: str, tid: str, r: dict[str, Any], data: dict[str, Any]) -> str:
    """Le refus de la jambe d'amont : le jeton, le détail, le remède, la sortie tracée."""
    remede = {
        "AMONT_OUVERT": f"Traite d'abord ces amonts, dans cet ordre (`tasks.py deps-ready {tid}`) ; une arête "
                        "TECHNIQUE fausse se retire (`tasks.py depends <aval> --retirer <amont>`), jamais un ORDRE PILOTE.",
        "CYCLE": "Un cycle ne se satisfait jamais : coupe-le, puis relance.",
        "INEXPLOITABLE": "Répare la lecture, puis relance.",
        "PLAN_A_REPLANIFIER": f"Le plan approuvé (trace {r['sid']}) précède la clôture d'un amont : révision par "
                              "planner puis plan-critic sur le code RÉEL, nouvelle trace `plan approuvé`, puis relance.",
    }.get(r["jeton"], "")
    detail = "\n".join(f"  {ligne}" for ligne in lignes_releve(r, data))
    return (f"TASKS: refus de {geste} {tid} — deps-ready: {r['jeton']}\n{detail}\n{remede}\n"
            "Sortie tracée : `--sans-dependances \"<pourquoi>\"` (pilote seul), visible au board.")


def jambe_amont_start(root: str, tid: str, data: dict[str, Any], sans_dependances: str = ""
                      ) -> tuple[list[str], str | None]:
    """LA JAMBE D'AMONT au `start` (source pending, blocked ou done — `set_state` efface le cycle
    clos AVANT d'appeler) : lève `BoardError` sur tout jeton non passant, sauf `--sans-dependances`
    qui DIT ce qu'il saute. Rend `(lignes, sid)` : les lignes à dire après `TASKS: <T> → running`
    (REPRISE_DITE, dérogation, avis) et la S-id élue, valeur de `lancee_sous`."""
    r = releve_amont(root, tid, data)
    lignes: list[str] = []
    if r["jeton"] not in DEPS_READY_PASSANTS:
        if not sans_dependances:
            raise BoardError(refus_amont("démarrer", tid, r, data))
        lignes.append(f"TASKS: {tid} démarre SANS la jambe d'amont (--sans-dependances) : deps-ready: {r['jeton']} — "
                      + " · ".join(lignes_releve(r, data)))
    elif r["jeton"] == "REPRISE_DITE":
        lignes.append(f"TASKS: {tid} REPRISE_DITE — lancée sous {r['sid']} : reprise DITE, jamais une révision — "
                      + " · ".join(r["causes"]))
    if r["jeton"] in DEPS_READY_PASSANTS:
        lignes += [f"TASKS: {tid} avis d'amont — {a}" for a in r["avis"]]
    return lignes, (r["sid"] if r["trace_lue"] else sid_elue_ou_rien(root, tid))


def render_deps_ready(root: str, tid: str) -> tuple[int, str]:
    """`tasks.py deps-ready <T>` — LECTURE SEULE. 1re ligne `deps-ready: <JETON>` (précédence de
    `DEPS_READY_JETONS`), puis le détail ; rc 0 sur AMONT_CLOS et REPRISE_DITE, 1 sinon ; un id
    inconnu lève `BoardError` (rc 2). Ajoute l'avis NON PROUVÉ des tâches `running` dont le
    write-set DÉCLARÉ partage un chemin EXACT avec celui de `T` : un indice, jamais une preuve."""
    data = load(root)
    task = find(data, resolve_id(data, tid))
    r = releve_amont(root, task["id"], data)
    lignes = [f"deps-ready: {r['jeton']}"] + lignes_releve(r, data)
    mien = set(writeset_of(task))
    for autre in data["tasks"]:
        commun = sorted(mien & set(writeset_of(autre))) if autre["state"] == "running" else []
        if commun and autre["id"] != task["id"]:
            lignes.append(f"NON PROUVÉ : {autre['id']} tourne et déclare {', '.join(commun)}, aussi au write-set de "
                          f"{task['id']} — une dépendance non déclarée n'est pas vue")
    return (0 if r["jeton"] in DEPS_READY_PASSANTS else 1), "\n".join(lignes)


def declare_parallel_group(root: str, tids: list[str]) -> str:
    """Prove the declared writesets disjoint, then allocate a parallel group.

    A GUARD OF COHERENCE, NOT OF SECURITY. The disjunction is proven on the
    writesets tasks DECLARE, never on the writes agents PERFORM — nothing in
    this module observes a single write. A writeset includes the outputs a task
    GENERATES (a built bundle, a rendered view). A group is exactly as safe as its
    declarations are faithful.

    THE PROOF IS TEXTUAL, so symbolic links, Windows junctions, 8.3 short
    aliases, HARD LINKS and real targets are outside its reach. Impossible proof
    VALUES AS AN OVERLAP: the refusal leaves the tasks to be serialised, which
    is the safe side.

    VACUITY IS NEVER A PROOF, hence the five refusals, all loud: fewer than two
    tasks (a group of one proves nothing anybody needed), the same task twice, a
    member with NO declared writeset (its disjunction would be vacuously true),
    a ``blocked_on`` link between two members (a task waiting on another is
    not parallel with it — it is behind it), and a ``depends_on`` CHAIN between
    two members, for that same sentence (T-00000530). The chain is followed
    TRANSITIVELY: a direct-edge check would pass ``a -> x -> b`` and group two
    tasks that are one behind the other through a third, which is the very
    vacuity the other four refusals exist to close.
    """
    if len(tids) < 2:
        raise BoardError(
            "parallel expects at least two task ids; a group of one proves nothing"
        )
    with board_lock(root):
        data = load(root)
        members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ref in tids:
            task = find(data, ref)
            if task["id"] in seen:
                raise BoardError(f"{task['id']} is listed twice; a task is parallel with others, not with itself")
            seen.add(task["id"])
            members.append(task)
        for task in members:
            # STATE IS CHECKED, not assumed (T-00000188 review, MEDIUM c). A
            # group says "these will run side by side"; a CLOSED task never will,
            # so grouping one is meaningless — and the same blindness to state is
            # what made the HIGH above possible. `pending`, `running` and
            # `blocked` all stay admissible: a group is normally declared BEFORE
            # the members start.
            if task["state"] == "done":
                raise BoardError(
                    f"{task['id']} is done; a closed task will never run beside another, "
                    f"so it cannot be part of a parallel group"
                )
            if not writeset_of(task):
                raise BoardError(
                    f"{task['id']} declares no writeset, so its disjunction would be "
                    f"vacuously true — declare it with `tasks.py writeset {task['id']} "
                    f"<paths…>` (generated outputs included)"
                )
        graph = _depends_adjacency(data["tasks"])
        for i, one in enumerate(members):
            for other in members[i + 1 :]:
                if one.get("blocked_on") == other["id"] or other.get("blocked_on") == one["id"]:
                    blocked, blocker = (
                        (one, other) if one.get("blocked_on") == other["id"] else (other, one)
                    )
                    raise BoardError(
                        f"{blocked['id']} is blocked on {blocker['id']}: it is behind that "
                        f"task, not parallel with it — release the link before declaring a group"
                    )
                # The SAME sentence, on the persistent axis: a declared order is
                # a "behind", never a "beside". Followed transitively, so a chain
                # through a THIRD task is caught too.
                chain = depends_path_between(graph, one["id"], other["id"]) or depends_path_between(
                    graph, other["id"], one["id"]
                )
                if chain is not None:
                    through = (
                        f" (through {' → '.join(chain[1:-1])})" if len(chain) > 2 else ""
                    )
                    # The remedy drops ONE edge and names what stays (T-00000765,
                    # `remede_coupe`); module absent ⇒ pre-T-765 text kept (A-C4).
                    _pd = plan_depends_module()
                    reste = [d for d in depends_on_of(find(data, chain[0])) if d != chain[1]]
                    remede = (
                        _pd.remede_coupe(data, chain) if _pd is not None
                        else f"`tasks.py depends {chain[0]} {' '.join(reste)} --motif \"…\"`"
                        if reste
                        else f"`tasks.py depends {chain[0]} --clear`"
                    )
                    raise BoardError(
                        f"{chain[0]} depends on {chain[-1]}{through}: it is behind that "
                        f"task, not parallel with it — drop THAT edge with {remede} "
                        f"before declaring a group"
                    )
                clash = writeset_paths_overlap(writeset_of(one), writeset_of(other))
                if clash is not None:
                    mine, theirs = clash
                    raise BoardError(
                        f"{one['id']} and {other['id']} both declare {mine!r} and {theirs!r}, "
                        f"which canonicalise to overlapping paths "
                        f"({canonical_writeset_path(mine)!r} vs {canonical_writeset_path(theirs)!r}) "
                        f"— the writesets are not disjoint, so no group is declared"
                    )
        group = _next_parallel_group(data)
        today = date.today().isoformat()
        for task in members:
            before = copy.deepcopy(task)
            task["parallel_group"] = group
            task["updated"] = today
            enqueue_sync_intent(data, task["id"], before, task)
        # A SECOND GROUP OVER A RUNNING MEMBER OF THE FIRST is no longer refused
        # (T-01M5F7286N1EYGXAXA5244X86B): running tasks in two groups, or in none,
        # are a legitimate board; the overlap refusal above is what `parallel` proves.
        save(root, data)
    named = ", ".join(t["id"] for t in members)
    return (
        f"TASKS: parallel group {group} declared — {named} "
        f"(writesets DECLARED disjoint; nothing observes what is actually written)"
    )


def _next_parallel_group(data: dict[str, Any]) -> str:
    """Allocate a group id no live task carries. MONOTONIC on the ids already
    present rather than on a counter: the group name must never be reused, or a
    task left over from a dissolved group would read as a member of a new one."""
    used = [parallel_group_of(t) for t in data.get("tasks", [])]
    highest = 0
    for value in used:
        match = re.fullmatch(r"PG-(\d{1,9})", value or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"PG-{highest + 1:04d}"
