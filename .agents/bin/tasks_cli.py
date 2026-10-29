# tasks_cli.py — PARTIE de `tasks.py` (T-00000788) : le PARSEUR de la CLI,
# extrait de `main` à l'identique ; `main` garde la répartition des verbes.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations


def _construire_parseur(argv: list[str] | None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Task board reader/writer for the agentic kit.")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    ap.add_argument("--statusline", action="store_true", help="print the compact statusline form")
    sub = ap.add_subparsers(dest="cmd")
    # T-00000765 help strings: `plan_depends.AIDE_CLI` (R3), read ONLY under -h/--help; absent OR broken => fallback.
    _aide_lue = {"-h", "--help"} & set(sys.argv[1:] if argv is None else argv)
    _aide = getattr(plan_depends_module(lecture=True), "AIDE_CLI", {}) if _aide_lue else {}
    _h = lambda cle, repli: _aide.get(cle, repli + " (help: .agents/bin/plan_depends.py)")  # noqa: E731
    # T-01M5QC86XNEJ5NEX6DGZJ0AJZ5 (S-01M5S9S55X02Z3J0WATVQD0ZH9): the ENGLISH name heads every
    # flag and verb, the former French one stays an alias. Each aliased flag keeps its former
    # `dest` EXPLICITLY (an English head would derive another one, and `getattr(args, "exiger")`
    # would go silent); each aliased verb pins `set_defaults(cmd=<former>)`, since argparse sets
    # `args.cmd` to the TYPED name and `main` dispatches on the former one. Help texts unchanged.

    p_new = sub.add_parser("new", help="add a pending task")
    p_new.add_argument("title")
    p_new.add_argument("--owner", default="")
    p_new.add_argument(
        "--workstream",
        "--chantier",
        dest="chantier",
        default="",
        metavar="GROUP",
        help="free-text thematic group; absent = no chantier (regroup changes it later)",
    )
    # T-01M54GEHJBGA5996W0T48JXNQ4: the HUMAN in charge, free text like --chantier;
    # `owner` stays the agent. ASCII ONLY in help (exits before force_utf8_stdio).
    p_new.add_argument(
        "--assignee",
        "--responsable",
        dest="responsable",
        default="",
        metavar="NAME",
        help="the human in charge, free text; absent = nobody (the `responsable` verb changes it later)",
    )
    # default=None, never "": an empty epic is REFUSED on every write (T-00001043),
    # so absent must stay distinguishable from `--epic ""`. ASCII ONLY in help.
    p_new.add_argument(
        "--epic",
        default=None,
        metavar="E-NN",
        help="an epic of the registry (epic-new declares it); validated before any id is allocated",
    )
    # THE MEASURE GUARD (T-00001128). default=None, never "": an empty
    # `--pas-un-defaut` is REFUSED, so absent must stay distinguishable from
    # `--pas-un-defaut ""`. ASCII ONLY in these help strings: `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_new.add_argument(
        "--measure",
        "--mesure",
        dest="mesure",
        default=None,
        metavar='"CMD => OBSERVED"',
        help="the command that reproduces the defect, `=>`, then what it printed; "
        "one of --mesure / --pas-un-defaut is REQUIRED when "
        ".agents/state/gates/MESURE_REQUIRED exists (AGENTS.md, Golden rules)",
    )
    p_new.add_argument(
        "--not-a-defect",
        "--pas-un-defaut",
        dest="pas_un_defaut",
        default=None,
        metavar="WHY",
        help="the traced exit for a feature, a decision or a chantier -- nothing to "
        "reproduce; non-empty, exclusive with --mesure, and REFUSED when the title "
        "opens on the lexicon of a defect (fix, bug, defaut, regression, ...)",
    )
    # No `choices=`: an off-list motif is refused INSIDE the lock by `mesure_refusal`,
    # with the doctrine sentence, never by a bare argparse usage error.
    p_new.add_argument(
        "--motive",
        "--motif",
        dest="motif",
        default=None,
        metavar="M",
        help="with --mesure only, REQUIRED there: why this defect is not fixed on the "
        "spot. Closed list: " + ", ".join(MOTIFS) + " (garde: touches a guard or a "
        "hook; securite: class 0 or 1; decision-pilote: needs a pilot decision; gros: "
        "6 files or more, or a plan; sans-fournee: found outside any dev in flight). "
        "`mineur` is REFUSED: a minor defect is fixed on the spot, with a witness",
    )

    # THE OPTIONAL EPIC (T-00001043). ASCII ONLY in these help strings: `--help`
    # exits inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_epic_new = sub.add_parser(
        "epic-new",
        help="declare an epic in the registry (root key `epics` of TASKS.json); --maj replaces it",
    )
    p_epic_new.add_argument("eid", metavar="E-NN", help="the epic id, E- then two digits or more")
    p_epic_new.add_argument("titre", metavar="TITLE", help="one non-empty line")
    p_epic_new.add_argument("--wave", "--vague", dest="vague", type=int, default=None, metavar="N")
    p_epic_new.add_argument("--priority", "--priorite", dest="priorite", default=None, choices=["P0", "P1", "P2"])
    p_epic_new.add_argument("--exclusive", action="store_true", help="a LABEL, never a lock")
    p_epic_new.add_argument("--risk", "--risque", dest="risque", default=None, metavar="TXT", help="one line")
    p_epic_new.add_argument(
        "--replace", "--maj", dest="maj", action="store_true",
        help="REPLACE an existing entry (a duplicate is refused without it)"
    )

    p_epic = sub.add_parser(
        "epic",
        help="set a task's epic (any state, running included), or detach it with --retirer",
    )
    p_epic.add_argument("tid")
    p_epic.add_argument(
        "eid",
        nargs="?",
        default=None,
        metavar="E-NN",
        help='an epic of the registry; "" is refused, detach with --retirer',
    )
    p_epic.add_argument("--remove", "--retirer", dest="retirer", action="store_true",
                        help="remove the epic key from the task")

    p_epic_list = sub.add_parser(
        "epic-list",
        help="one line per epic: id, title, attributes, count by state (tasks carrying an unregistered epic included)",
    )
    p_epic_list.add_argument("--json", action="store_true")

    p_start = sub.add_parser("start", help="mark running and take the clone focus (demotes no other running task)")
    p_start.add_argument("tid")
    # `default=None` ET NON `""` — second volet de T-00000577. Avec `""`, un
    # `start` sans `--stage` passait une chaîne VIDE, que `set_state` écrivait
    # (`if stage is not None`), donc **démarrer une tâche effaçait aussi SON
    # propre point d'étape**. `None` veut dire « ne touche pas au champ », ce qui
    # est le sens voulu : on démarre une tâche, on ne prétend pas savoir où elle
    # en est. Les deux effacements — celui de la tâche rétrogradée et celui de la
    # tâche démarrée — ont été mesurés le même jour, dans le même geste.
    p_start.add_argument("--stage", default=None)
    # ASCII ONLY in argparse help (see the `block --on` note): `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs, so an accented letter
    # lands on a cp1252 console as mojibake.
    p_start.add_argument(
        "--without-chain",
        "--sans-chaine",
        dest="sans_chaine",
        default="",
        metavar="WHY",
        help=(
            "start WITHOUT the mandatory plan chain, and SAY WHY. The guard "
            "refuses a start when no plan critic (plan-critic) or no planner "
            "(planner) was traced by the host on SubagentStop; the traces of "
            "either def taken out of the chain by pilot decision S-01M4TZZ13Y "
            "stay accepted by the guard, with no end date - each trace expires "
            "24 h after it is written, like any trace - and are never proposed. "
            "It is ARMED "
            "by the presence of .agents/state/gates/PLAN_CHAIN_REQUIRED (absent: "
            "nothing changes); the template sync SEEDS that marker into an "
            "adopter, which therefore starts ARMED. The "
            "reason lands in `stage` and stays VISIBLE on the board: the "
            "exception shows, the oversight no longer passes. A SMALL task "
            "takes the direct route instead: `tasks.py direct <id>` checks it by "
            "code and stamps it, then `start` needs no chain"
        ),
    )
    # ASCII ONLY in argparse help (see the `block --on` note): `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_start.add_argument(
        "--without-target",
        "--sans-cible",
        dest="sans_cible",
        default="",
        metavar="WHY",
        help=(
            "start WITHOUT annotating the plan's target, and SAY WHY. ARMED by "
            "the presence of .agents/state/gates/PLAN_CIBLE_REQUIRED and only for "
            "a task in the chantier its `chantier=` line names (`chantier=*`: "
            "every task of the board, with or without a chantier -- the marker "
            "the template sync SEEDS into an adopter). At `start` it only "
            "bites when an approval trace already exists for the task; the reason "
            "lands in `stage` and stays VISIBLE on the board"
        ),
    )
    p_start.add_argument("--without-deps", "--sans-dependances", dest="sans_dependances", default="",
                         metavar="WHY",
                         help=_h("start_sans_dependances", "start WITHOUT the upstream leg (deps-ready) and the "
                                 "plan's ARETE: control, and SAY WHY"))
    p_start.add_argument("--without-claim", "--sans-revendication", dest="sans_revendication", default=None,
                         metavar="WHY",
                         help="retired: a claim can only be transferred by the pilot with --reprise")
    p_start.add_argument("--takeover", "--reprise", dest="reprise", default=None, metavar="REASON",
                         help="pilot-only transfer: interactive terminal and exact task id confirmation")

    p_jira_import = sub.add_parser("jira-import", help="import open Jira Cloud issues into the board")
    p_jira_import.add_argument("--project", required=True, metavar="KEY")
    p_jira_import.add_argument("--issue", default=None, metavar="KEY")
    p_jira_import.add_argument("--dry-run", action="store_true")
    p_jira_claim = sub.add_parser("jira-claim", help="retry the Jira label for a claimed task")
    p_jira_claim.add_argument("--retry", required=True, metavar="T-ID")
    p_jira_claim.add_argument("--dry-run", action="store_true")

    p_stage = sub.add_parser("stage", help="update the pipeline stage without changing state")
    p_stage.add_argument("tid")
    p_stage.add_argument("stage")

    p_block = sub.add_parser("block", help="mark blocked; the reason goes to the stage column")
    p_block.add_argument("tid")
    p_block.add_argument("--note", default="")
    # ONE blocker, no list: block on the LAST remaining one, or re-block after a
    # release. The help says what --note alone does NOT do, because that is the
    # choice the caller is actually making.
    p_block.add_argument(
        "--on",
        dest="blocked_on",
        default="",
        metavar="T-NNN",
        # ASCII ONLY in argparse help, like every other help string here: `--help`
        # exits inside `parse_args`, BEFORE `force_utf8_stdio` runs, so a dash or
        # an arrow lands on a cp1252 console as mojibake (measured on Windows).
        help=(
            "block on another TASK: released automatically when that task is done. "
            'Waiting on a human decision stays --note "<why>" alone, since prose is '
            "never auto-released; combine both when the task waits on the two"
        ),
    )

    p_unblock = sub.add_parser("unblock", help="blocker lifted: blocked -> pending, reason cleared")
    p_unblock.add_argument("tid")

    p_done = sub.add_parser("done", help="mark done, with a MANDATORY reason")
    p_done.add_argument("tid")
    # ASCII ONLY in argparse help (see the `block --on` note): `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_done.add_argument(
        "--reason",
        "--raison",
        dest="raison",
        required=True,
        metavar="WHY",
        help=(
            "what closes the task. MANDATORY: `done` was the only terminal verb "
            "with no explanation, so the board asserted \'finished\' without ever "
            "saying on what grounds. It lands in `stage`, replacing the in-flight "
            "step, where `block` and `reopen` put theirs"
        ),
    )
    p_done.add_argument(
        "--without-review",
        "--sans-binome",
        dest="sans_binome",
        default="",
        metavar="WHY",
        help=(
            "close WITHOUT the mandatory critical review, and SAY WHY. The guard "
            "refuses a closure when fewer than BINOME_MIN (one, S-00004500) "
            "distinct closing critics were traced by the host. This escape exists "
            "because a duplicate, a stale "
            "ticket or a pure decision has nothing to review -- the reason is "
            "appended to the closing stage, so the exception stays VISIBLE on "
            "the board. An oversight no longer passes; an exception still does, "
            "out loud"
        ),
    )
    p_done.add_argument(
        "--without-target",
        "--sans-cible",
        dest="sans_cible",
        default="",
        metavar="WHY",
        help=(
            "close WITHOUT annotating the plan's target, and SAY WHY. ARMED by "
            "the presence of .agents/state/gates/PLAN_CIBLE_REQUIRED and only for "
            "a task in the chantier its `chantier=` line names (`chantier=*`: "
            "every task of the board, with or without a chantier -- the marker "
            "the template sync SEEDS into an adopter). At `done` the "
            "controlled plan is the task's last `plan approuve` trace, or the "
            "`running` slot of the same chantier when that plan NAMES the task; "
            "the reason lands in `stage` and stays VISIBLE on the board"
        ),
    )
    p_done.add_argument("--without-deps", "--sans-dependances", dest="sans_dependances", default="",
                        metavar="WHY",
                        help=_h("done_sans_dependances", "close WITHOUT the plan's ARETE: control, and SAY WHY"))

    p_reopen = sub.add_parser(
        "reopen",
        help="closure was wrong: done -> pending, with a MANDATORY reason",
    )
    p_reopen.add_argument("tid")
    # ASCII ONLY in argparse help, like every other help string here (see the
    # `block --on` note): `--help` exits inside `parse_args`, BEFORE
    # `force_utf8_stdio` runs.
    p_reopen.add_argument(
        "--reason",
        "--raison",
        dest="raison",
        required=True,
        metavar="WHY",
        help=(
            "why the closure was wrong. MANDATORY: reopening is a claim about a "
            "closure someone pronounced, and an unexplained one is an invisible "
            "board move. It lands in `stage`, where `block` puts its own reason"
        ),
    )
    p_reopen.add_argument(
        "--without-reblock",
        "--sans-rebloquer",
        dest="sans_rebloquer",
        action="store_true",
        help=(
            "do NOT restore the blocked_on links this closure had released. "
            "Restoring is the default, for the same reason the release is "
            "automatic: a move that needs a second command is a move nobody makes"
        ),
    )

    # T-00000842: the morning path of /night purges a task's DIRECT closing-review
    # traces before its closing review runs (binome_preuve never expires direct traces), and
    # the `rm` it used to prescribe is refused by safe-bash.sh ("outside"). NOT a
    # board mutator: it reads the board to refuse an unknown id and deletes local,
    # git-ignored files under .agents/state/local/binome/ — kept OUT of `mutating`.
    # ASCII ONLY in argparse help (see the `block --on` note).
    p_bpurge = sub.add_parser(
        "review-purge",
        aliases=["binome-purge"],
        help=(
            "delete ALL closing-review traces of ONE task "
            "(.agents/state/local/binome/<tid>.*.json) and say which; rc 0"
        ),
    )
    p_bpurge.set_defaults(cmd="binome-purge")
    p_bpurge.add_argument("tid")

    p_retitle = sub.add_parser("retitle", help="update a task's title only")
    p_retitle.add_argument("tid")
    p_retitle.add_argument("title")

    p_reassign = sub.add_parser("reassign", help="update a task's owner only (any state, running included)")
    p_reassign.add_argument("tid")
    # Free text, no `choices`: symmetrical with `new --owner`. An empty value is
    # a supported call ("" = unassigned), which is why there is no default here —
    # the owner is always stated explicitly, never inherited.
    p_reassign.add_argument("owner", help='the responsible agent; "" returns the task to unassigned')

    p_regroup = sub.add_parser("regroup", help="update a task's chantier only (any state, running included)")
    p_regroup.add_argument("tid")
    # Free text, no `choices`: symmetrical with `new --chantier`, same argument
    # as `reassign`. An empty value un-groups, so no default here either.
    p_regroup.add_argument("chantier", metavar="WORKSTREAM", help='the thematic group; "" removes the task from any')

    p_responsable = sub.add_parser(
        "assignee", aliases=["responsable"],
        help="update a task's human in charge only (any state, running included); owner untouched"
    )
    p_responsable.set_defaults(cmd="responsable")
    p_responsable.add_argument("tid")
    p_responsable.add_argument("responsable", metavar="ASSIGNEE", help='the human in charge, free text; "" removes the key')

    # LIMITS (T-01M54GEMCH3JWA95G61N2J70KS, E-48 C4): ALERT on overrun; STOP only under the
    # pilot's `.agents/state/gates/LIMITE_ARRET`. ASCII-only help, like `writeset` below.
    p_limite = sub.add_parser(
        "limite", help="set, raise or remove a task's deadline and token limit (any state, done included)"
    )
    p_limite.add_argument("tid")
    p_limite.add_argument("--delai", default=None, metavar="N(m|h|j)",
                          help="deadline = now + N minutes, hours or days (exclusive with --echeance)")
    p_limite.add_argument("--echeance", default=None, metavar="YYYY-MM-DDTHH:MMZ",
                          help="absolute UTC deadline (exclusive with --delai)")
    p_limite.add_argument("--jetons", default=None, metavar="N[k|M]", help="token limit, an integer > 0")
    p_limite.add_argument("--retirer", action="store_true",
                          help="remove the deadline and the token limit; the declared count is kept")
    p_conso = sub.add_parser(
        "conso", help="ADD declared tokens to a task (the host's subagent_tokens of a finished subagent: its last call, not its spend)"
    )
    p_conso.add_argument("tid")
    p_conso.add_argument("quantite", metavar="N[k|M]", help="tokens to add, an integer > 0")
    p_depassements = sub.add_parser(
        "depassements", help="list the open tasks over their deadline or token limit (read-only, rc 0/1)"
    )
    p_depassements.add_argument("--json", action="store_true",
                                help="a JSON array of {tache, type, valeur, limite, etat, arret}; [] when none")

    # ASCII ONLY in these help strings, like every other one here: `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_writeset = sub.add_parser(
        "writeset",
        help="declare the files a task may write (any state); --clear drops the declaration",
    )
    p_writeset.add_argument("tid")
    p_writeset.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help=(
            "relative paths, forward or back slashes, a trailing / for a directory. "
            "GENERATED OUTPUTS COUNT: a task that rebuilds a bundle writes that bundle. "
            "Writing a writeset retracts the proof that used it, so any declared "
            "parallel group is dropped from this task: re-declare it with `parallel`"
        ),
    )
    p_writeset.add_argument(
        "--clear", action="store_true", help="drop the whole declaration (takes no path)"
    )

    # THE DIRECT ROUTE (`tasks_direct.py`). ASCII ONLY in these help strings:
    # `--help` exits inside `parse_args`, BEFORE `force_utf8_stdio` runs. The
    # threshold is READ from the constant, never written here.
    _aide_direct = (
        f"stamp a SMALL task for the direct route: no planner, no plan critic, "
        f"no human gate. CHECKED BY CODE: a declared writeset of 1 to "
        f"{MAX_FICHIERS_DIRECT} exact paths, no guard path, no open decision, "
        f"no open security, SPECS readable. A refusal lists EVERY cause and "
        f"writes nothing. `start` and `done` replay the check where the stamp "
        f"crosses an ARMED guard; a direct task never consumes a plan chain. "
        f"The mark [DIRECT SANS PLAN] (current and validated counts) stays on "
        f"the board; `reopen` keeps the stamp, replayed at the next `start`, "
        f"without the closed cycle's mark; --retirer is refused on an open (not "
        f"done) task whose start crossed the chain (remedy: done, or reopen then "
        f"--retirer)"
    )
    p_direct = sub.add_parser("direct", help=_aide_direct, description=_aide_direct)
    p_direct.add_argument("tid")
    p_direct.add_argument(
        "--remove",
        "--retirer",
        dest="retirer",
        action="store_true",
        help="remove the stamp: the only way back from the direct route to the planned one; "
        "refused on an open (not done) task whose start crossed the chain (remedy: done, or reopen then --retirer)",
    )

    # THE RETURN CHECK (`tasks_retour.py`). ASCII ONLY in these help strings, like
    # `direct` above: `--help` exits inside `parse_args`, BEFORE `force_utf8_stdio`.
    _aide_retour = (
        "MECHANICAL return check of a dev branch BEFORE its merge, run at the main "
        "checkout. (a) --base and --branche each resolve to ONE commit; the base is an "
        "ancestor of the branch tip AND of HEAD, else (c)-(f) are not evaluated. (b) at "
        "least one commit since the base. (c) every path of the base..tip diff, renames "
        "split, is covered at a segment boundary by the DECLARED writeset of one of the "
        "named tasks; a task without a writeset refuses. A task stamped direct names "
        "itself alone: naming it with another task refuses (c) before the merge. "
        "(d) the diff is not empty. "
        "(e) HEAD touched none of its files since the base: a check taken after the "
        "merge is refused. (f) every worktree on the branch is clean; a prunable one "
        "refuses. (g) at the main checkout the index is empty, no diff file is modified "
        "and the branch is not the current one. (h) a worktree-<folder> duplicate with "
        "commits of its own refuses; a pristine one is a note. (i) on a task stamped "
        "direct, the previous record: if its tip entered HEAD, it must have been ok and "
        "merged --no-ff as is (no extra file, no fast-forward, no nested merge); else "
        "refused, and that refusal carries over to every later record until reopen. "
        "EVERY cause is listed, each with its remedy. The record `retour` is written on "
        "EACH named task, a refusal too; the last one replaces the previous, never "
        "before being compared to HEAD. Exit 0 ok, 1 refused, 2 unknown or closed "
        "task, check (i) not concluded, or a record changed during the measure "
        "(nothing written)"
    )
    p_retour = sub.add_parser(
        "return",
        aliases=["retour"],
        help="mechanical return check of a dev branch before its merge (rc 0 ok, 1 refused, 2 error)",
        description=_aide_retour,
    )
    p_retour.set_defaults(cmd="retour")
    p_retour.add_argument("tids", nargs="+", metavar="T-NNN",
                          help="the task(s) the branch delivers; their declared writesets are united")
    p_retour.add_argument("--base", required=True, metavar="SHA",
                          help="the common base the dev branch was cut from: a sha, 7 to 40 hex")
    p_retour.add_argument("--branch", "--branche", dest="branche", required=True, metavar="REF",
                          help="the local dev branch, refs/heads/ optional")
    p_retour.add_argument("--dry-run", action="store_true", help="measure and print, write nothing")
    p_retour.add_argument("--into", "--vers", dest="vers", default=None, metavar="L",
                          help="(v) the branch was cut from the integration branch L and merges into L, not "
                               "into HEAD: (a) and (e) read the tip of L instead of HEAD, (h) also excludes "
                               "HEAD; (v) requires L to exist, to differ from --branche, and every named task "
                               "to carry the delivery L (`tasks.py livraison`). The record gains the key "
                               "`vers`; the `done` of a direct task then requires its tip merged into L and L "
                               "merged into HEAD: exactly two levels")

    # THE DELIVERY (`tasks_gardes.py`). ASCII ONLY in these help strings, like `direct`
    # above: `--help` exits inside `parse_args`, BEFORE `force_utf8_stdio`.
    _aide_livraison = (
        "declare that the named tasks are delivered by ONE integration branch L (their lots "
        "merged into L, then L into the target): the SAME record {branche, taches, le} is "
        "written on each. Read by the closing review (a member's critic trace is borrowed by "
        "the others, only if dated after the declaration and after every member's later "
        "`retour --vers L`), by `retour --vers L` and by the `done` of a direct task. "
        "Declaring again REPLACES the record on the named tasks, and says so. An unknown id, "
        "a closed task, an empty branch, one starting with '-', or holding a space or a "
        "control character refuses with EVERY cause, rc 2, nothing written. `reopen` and a "
        "`start` from done drop the record"
    )
    p_livraison = sub.add_parser("delivery", aliases=["livraison"],
                                 help="declare the tasks delivered by one integration branch",
                                 description=_aide_livraison)
    p_livraison.set_defaults(cmd="livraison")
    p_livraison.add_argument("tids", nargs="+", metavar="T-NNN", help="the member tasks of the delivery")
    p_livraison.add_argument("--branch", "--branche", dest="branche", required=True, metavar="L",
                             help="the integration branch, refs/heads/ optional")
    p_livraison.add_argument("--remove", "--retirer", dest="retirer", action="store_true",
                             help="remove the delivery L from the named tasks instead")

    # THE BATCH (`tasks_fournee.py`). ASCII ONLY in these help strings, like `direct`
    # above: `--help` exits inside `parse_args`, BEFORE `force_utf8_stdio`.
    _aide_fournee = (
        "launch an APPROVED plan cut into lots (LOT: / INTEGRATION: / LOTS: lines, "
        "plan_lots.py) as parallel sub-tasks, in one gesture. Reads the parent's LAST "
        "decision titled exactly `plan approuve` (plan= and sha256=, recomputed "
        "identical; night-eligible never launches). A PURE preflight lists EVERY "
        "refusal and writes nothing: grammar, enrolment, parent state, no direct stamp "
        "on the parent, existing OPEN lots on the same sha256, the measure guard per lot, the "
        "parent's start legs, and the running tasks outside the batch (a live group is "
        "joined only if ALL its open members run; never a demotion). Then, under one "
        "lock, each step COMPLETES what is missing: lots created with their link, "
        "writesets, `direct` tried per lot, one parallel group, start of the parent "
        "(pays the plan chain once, in its name), start of the pending lots (borrow "
        "named after the parent, or the direct leg). A failure names what was written; "
        "re-running is the remedy"
    )
    p_fournee = sub.add_parser("batch", aliases=["fournee"],
                               help="launch an approved plan's lots as parallel sub-tasks",
                               description=_aide_fournee)
    p_fournee.set_defaults(cmd="fournee")
    p_fournee.add_argument("tid", metavar="T-PARENT")
    p_fournee.add_argument("--dry-run", action="store_true",
                           help="the preflight alone: print what would be done, write nothing")
    for _anglais, _drapeau, _quoi in (
            ("--without-chain", "--sans-chaine", "the plan chain"),
            ("--without-target", "--sans-cible", "the plan target"),
            ("--without-deps", "--sans-dependances", "the upstream leg (deps-ready) and the plan's ARETE: control")):
        p_fournee.add_argument(_anglais, _drapeau, dest=_drapeau[2:].replace("-", "_"), default="",
                               metavar="WHY",
                               help=f"start every member WITHOUT {_quoi}, and SAY WHY: the reason "
                                    "lands on each member, VISIBLE on the board")
    p_fournee.add_argument("--without-claim", "--sans-revendication", dest="sans_revendication", default=None,
                           metavar="WHY",
                           help="retired: a claim can only be transferred by the pilot with --reprise")
    p_fournee.add_argument("--takeover", "--reprise", dest="reprise", default=None, metavar="REASON",
                            help="pilot-only transfer: interactive terminal and exact parent id confirmation")

    # ASCII-only help, like `writeset` above: `--help` prints before
    # `force_utf8_stdio` has had a chance to run.
    p_depends = sub.add_parser(
        "depends",
        help="declare which tasks this one is BEHIND (an order that guards start, never a state)",
    )
    p_depends.add_argument("tid")
    p_depends.add_argument(
        "deps",
        nargs="*",
        metavar="T-NNN",
        help=_h("depends_deps", "task ids this one must wait for. TOTAL REWRITE by default, "
                "GUARDED since T-00000765 (an ORDRE PILOTE edge is never erased this way)"),
    )
    p_depends.add_argument(
        "--clear", action="store_true", help="drop the whole declaration (takes no id; refused if it would erase an ORDRE PILOTE)"
    )
    p_depends.add_argument("--add", action="store_true",
                           help=_h("depends_add", "ADD these edges, the existing ones stay"))
    p_depends.add_argument("--remove", "--retirer", dest="retirer", default=None, metavar="T-NNN",
                           help=_h("depends_retirer", "drop EXACTLY this technical edge"))
    p_depends.add_argument("--remove-pilot-order", "--retirer-ordre-pilote", dest="retirer_ordre_pilote",
                           default=None, nargs=2, metavar=("T-NNN", "S-NNN"),
                           help=_h("depends_retirer_ordre_pilote", "drop an ORDRE PILOTE edge under a DISTINCT pilot decision"))
    # ASCII-only help, like the args above: `--help` prints before
    # `force_utf8_stdio` runs, so an accented letter would raise on a cp1252
    # console. The refusal itself lives in `set_depends`, not here.
    p_depends.add_argument(
        "--motive",
        "--motif",
        dest="motif",
        metavar="MOTIVE",
        action="append",
        default=[],
        help=(
            "why this task waits on those; a dependency is an ORDER, so state it. "
            "Required unless --clear. Repeatable: give it ONCE and it applies to "
            "every edge, or once per id in order. A single line each"
        ),
    )

    # ASCII-only help, same reason as `depends` above.
    p_depends_show = sub.add_parser(
        "depends-show",
        help="show each edge this task is behind: dependency, state, class, motif",
    )
    p_depends_show.add_argument(
        "tid", help="the task whose outgoing dependencies to show"
    )

    # READ-ONLY (S-01M4Z5VMP5E9YN8T6EMDTBAF0T), OUT of `mutating` like `depends-show`.
    # ASCII-only help, same reason as `depends` above.
    _aide_deps_ready = (
        "is this task's upstream closed? First line `deps-ready: <TOKEN>`, by precedence "
        "CYCLE > AMONT_OUVERT > INEXPLOITABLE > PLAN_A_REPLANIFIER | REPRISE_DITE > AMONT_CLOS; "
        "then the open upstream in order (upstream first: rank, id, state, motif, pulled by), "
        "dangling ids, notices. rc 0 on AMONT_CLOS and REPRISE_DITE, 1 otherwise, 2 on usage or "
        "unknown id. Only DECLARED depends_on is read: an undeclared dependency is not seen"
    )
    p_deps_ready = sub.add_parser("deps-ready", help="read whether this task's upstream is closed (read-only, "
                                  "rc 0/1)", description=_aide_deps_ready)
    p_deps_ready.add_argument("tid", help="the task whose upstream to judge")

    # T-01M5HST80E30DFMV3S7WM68Q7N: the task chrono, FLAT options validated per action by
    # `task_chrono.executer`; journal under the COMMON root, never the board. rc 0/2. ASCII ONLY in help.
    p_chrono = sub.add_parser("chrono", help="estimate each step before it starts, then show real step times "
                                             "(local journal under the common root; rc 0/2)")
    p_chrono.add_argument("tid", help="the task (validated read-only on the common root board)")
    p_chrono.add_argument("action", choices=["estimate", "begin", "step", "show"])
    p_chrono.add_argument("--step", "--etape", dest="etape", metavar="STEP", default=None, help="estimate, step: the step (closed list in task_chrono.ETAPES)")
    p_chrono.add_argument("--phase", default=None, choices=["begin", "end"], help="step: begin or end")
    p_chrono.add_argument("--lot", default=None, help="estimate, step: the lot task id (validated on the board); "
                                                        "a fournee lot given as tid plays on its parent's journal")
    p_chrono.add_argument("--attempt", "--tentative", dest="tentative", metavar="ATTEMPT", default=None, type=int, help="step: attempt number (default: next/open)")
    p_chrono.add_argument("--watch", action="store_true", help="show: refresh until the cycle closes (Ctrl-C)")
    p_chrono.add_argument("--json", action="store_true", help="show: the summary as JSON")

    p_parallel = sub.add_parser(
        "parallel",
        help="declare N tasks parallel, only if their declared writesets are disjoint",
    )
    p_parallel.add_argument(
        "tids",
        nargs="+",
        metavar="T-NNN",
        help=(
            "two or more task ids. COHERENCE guard, not security: the disjunction is "
            "proven on what the tasks DECLARE, never on what agents write (T-00000189)"
        ),
    )

    # T-01M5F7286N1EYGXAXA5244X86B: the clone's focus and the closing review's scope, two LOCAL
    # JSON files of the main repository (`.agents/state/local/`); no V3 replay. ASCII ONLY in help.
    p_focus = sub.add_parser("focus", help="set the clone focus to a RUNNING task (focus.json; one active "
                                           "session per clone)")
    p_focus.add_argument("tid")
    p_scope = sub.add_parser("review-scope", help="declare the explicit task list of the next closing review "
                                                  "(review-scope.json): every member open, the focus among them")
    p_scope.add_argument("tids", nargs="+", metavar="T-NNN")

    p_delete = sub.add_parser("delete", help="remove one task from the board (its id is never reused)")
    p_delete.add_argument("tid")
    p_delete.add_argument("--force", action="store_true", help="allow deleting the running task")

    p_purge = sub.add_parser("purge", help="bulk-remove tasks by state (default: done)")
    p_purge.add_argument("--state", default="done", choices=[s for s in STATES if s != "running"])
    p_purge.add_argument("--before", default=None, metavar="YYYY-MM-DD", help="only tasks updated strictly before this date")
    p_purge.add_argument("--dry-run", action="store_true", help="report what would be removed without writing")
    p_purge.add_argument("--cap", "--plafond", dest="plafond", type=int, default=50, metavar="N",
                         help="refuse to remove more than N tasks in one call (default 50; interim until the archive, "
                              "S-01M4NFRZS1XK1BEQVGH43Z3EDN)")

    p_list = sub.add_parser("list", help="print the sorted board, optionally filtered")
    p_list.add_argument("--json", action="store_true")
    # default=None, never "": absent must be distinguishable from an explicitly
    # empty value, and it is what keeps the bare `list` on its original path.
    p_list.add_argument(
        "--task",
        default=None,
        metavar="T-NNN",
        help="one task, every field untruncated (short forms T-14 / 14 accepted)",
    )
    # choices closes the vocabulary at the CLI boundary: an unknown state is a
    # usage error (exit 2), never an empty result that reads as an empty board.
    p_list.add_argument(
        "--state",
        default=None,
        choices=STATES,
        help="only tasks in this state; combinable with --task",
    )
    # default=None like --state, and for the same reason twice over: absent must
    # stay distinguishable from an explicitly empty value, which HERE is itself a
    # filter ("the tasks with no chantier"), not a no-op.
    p_list.add_argument(
        "--workstream",
        "--chantier",
        dest="chantier",
        default=None,
        metavar="GROUP",
        help='only tasks in this thematic group; "" = the tasks with no chantier',
    )
    # default=None: absent is "no filter". An empty value has no meaning here
    # (no task waits on "nothing"), so it is refused rather than treated as a
    # filter, and an unknown id is a loud refusal, never an empty result.
    p_list.add_argument(
        "--blocked-by",
        default=None,
        metavar="T-NNN",
        help='only tasks whose blocked_on points at this one ("who waits on T-NNN?"); short forms T-14 / 14 accepted',
    )
    # Same contract as --blocked-by, on the PERSISTENT axis. One difference worth
    # knowing: a `done` task legitimately matches SEVERAL here, because
    # depends_on edges survive closure.
    p_list.add_argument(
        "--depends-on",
        default=None,
        metavar="T-NNN",
        help='only tasks whose depends_on names this one ("who is behind T-NNN?"); short forms T-14 / 14 accepted',
    )
    p_list.add_argument(
        "--group",
        action="store_true",
        help="cut the board into chantier sections; combinable with --state only",
    )
    p_list.add_argument(
        "--session",
        action="store_true",
        help="the SessionStart view: running and blocked in full, the newest "
        "SESSION_MAX_PENDING pending, the cut announced; takes no other flag",
    )
    # default=None like --chantier: `""` is itself a READ filter here ("the tasks
    # with no epic"). An unknown id is refused. Combines with --state and --json only.
    p_list.add_argument(
        "--epic",
        default=None,
        metavar="E-NN",
        help='only tasks under this epic; "" = the tasks with no epic; combinable with --state and --json only',
    )
    # default=None like --chantier: `""` is a READ filter ("the tasks with no human in
    # charge"). Combines with --state, --chantier and --json; main refuses the rest (rc 2).
    p_list.add_argument(
        "--assignee",
        "--responsable",
        dest="responsable",
        default=None,
        metavar="NAME",
        help='only tasks with this human in charge; "" = the tasks with none; combinable with --state, --chantier, --json',
    )

    sub.add_parser("render", help="regenerate TASKS.md from TASKS.json")
    sub.add_parser("replay-sync", help="replay pending/expired board sync intents")

    # The LOCK leg of the post-done commit hook (T-00000189). Not a board
    # mutator: it takes the POST_TASK_DONE lock, never the board's, and touches
    # no TASKS.json. Kept out of the `mutating` set below for that reason.
    p_commit = sub.add_parser(
        "commit-stores",
        help="lock leg of the post-done hook: commit the 3 state stores under a dedicated lock",
    )
    p_commit.add_argument(
        "--lock-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="seconds to wait for the POST_TASK_DONE lock (tests pass a short bound)",
    )
    # Same opt-in as `commit-run-exports --exiger` below (T-00001044): the night's
    # closing chains `commit-stores --exiger && commit-run-exports --exiger && verify`
    # because `claude -p` refuses the `tok=$(...); case ... esac` form in headless.
    # ASCII ONLY in argparse help (see the `block --on` note).
    p_commit.add_argument(
        "--require",
        "--exiger",
        dest="exiger",
        action="store_true",
        help="exit NON-ZERO when the token is neither `committed` nor `nothing`; the "
             "night's closing then chains the next leg with `&&` (T-00001044)",
    )

    # Commit the versioned run exports under `runs/` (T-00000677). Like
    # `commit-stores` it is a LOCK leg, NOT a board mutator: it takes the
    # POST_TASK_DONE lock, never the board's, and touches no TASKS.json. Kept OUT
    # of the `mutating` set below — committing run exports is not a board change,
    # and a V3 replay around it would write new events that dirty `runs/` again,
    # so the night's closing commit would never converge.
    p_runs = sub.add_parser(
        "commit-run-exports",
        help="lock leg: commit the versioned run exports under runs/ under a dedicated lock",
    )
    p_runs.add_argument(
        "--lock-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="seconds to wait for the POST_TASK_DONE lock (tests pass a short bound)",
    )
    # ASCII ONLY in argparse help (see the `block --on` note): `--help` exits inside
    # `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_runs.add_argument(
        "--require",
        "--exiger",
        dest="exiger",
        action="store_true",
        help="exit NON-ZERO when the token is neither `committed` nor `nothing` -- the "
             "night's closing then chains the gate with `&&` instead of re-reading a "
             "prose token (T-00000677 B1)",
    )

    # READ-ONLY plan-target checker (T-00000654). It never writes and never takes
    # a lock; it just reports which steps of a plan carry no target. Not in the
    # `mutating` set below, so no V3 replay runs around it.
    p_cible = sub.add_parser(
        "target-check",
        aliases=["cible-check"],
        help="check a plan annotates every step with a target (read-only, rc 0/1)",
    )
    p_cible.set_defaults(cmd="cible-check")
    p_cible.add_argument("plan", help="path to the plan .md (repo-root-relative or absolute)")
    # ASCII ONLY in argparse help (see the `block --on` note): `--help` exits
    # inside `parse_args`, BEFORE `force_utf8_stdio` runs.
    p_cible.add_argument(
        "--spec",
        default=None,
        metavar="PATH",
        help=(
            "the spec whose invariant names build the registry. When omitted, the "
            "spec is read from the armed PLAN_CIBLE_REQUIRED marker; with neither, "
            "the check errors (rc 2) rather than guessing"
        ),
    )
    return ap
