#!/usr/bin/env python3
"""Deterministic reader/writer for the task board.

TWO ARTEFACTS, one direction:

- ``.agents/state/board/TASKS.json`` — the SOURCE OF TRUTH. Tracked. One object
  per task, pretty-printed, so a single changed field is a single line of diff.
- ``.agents/state/local/TASKS.md`` — a GENERATED VIEW, regenerated on every write
  and git-ignored. Fixed column widths, so a long title never reflows the rows.

Why not markdown as the store: a table row is silently lossy. One missing ``|``
and the row parses short, gets skipped, and the next unrelated write re-emits the
table WITHOUT it — the task is deleted with no error. JSON is either valid or
loudly broken, which is what you want from a store an LLM might hand-edit.

A task::

    {"id": "T-014", "state": "running", "task": "Auth refresh flow",
     "owner": "dev-multi", "stage": "security-code-review", "updated": "2026-07-22"}

``id``: ``T-<n>`` is the HISTORICAL form — frozen, still valid, never
rewritten (``T-014`` above, or ``T-00000042``); every NEW task is
``T-<ULID>`` (26 upper-case Crockford symbols, ``record_id.mint``), and NO
counter is stored (T-00000726). ``state`` is a CLOSED vocabulary: pending / running /
blocked / done. ``stage`` porte, SELON L'ÉTAT : l'étape de pipeline en vol
(``running``) ; le motif de blocage (``blocked``) ; la raison de clôture
(``done``) ; et, sur une tâche ``pending``, l'étape où elle a été INTERROMPUE —
mémoire de reprise que la sortie de ``running`` préserve depuis ``T-00000577`` — ou la
raison d'un ``reopen``. **Sortir de ``blocked`` n'emporte JAMAIS le motif dans
l'état suivant.**

L'énumération est **BORNÉE PAR L'ÉTAT, jamais close par le nombre** — et dire
« close » ici serait re-commettre ``L-00000187`` dans le correctif qui l'invoque.
Deux états portent DEUX valeurs : ``blocked`` porte un motif OU une étape EN VOL
que ``block --on`` sans note a PRÉSERVÉE (T-00000103), et ``pending`` porte le
vide à la création OU l'étape interrompue. **Conséquence mesurée, et c'est une
dette nommée (``T-00000578``)** : la règle ci-dessus est écrite sur un MOTIF mais
s'applique au CHAMP, donc sortir de ``blocked`` détruit aussi une étape
préservée. Ce n'est PAS une régression — la rédaction d'avant l'écrasait déjà par
un ``--stage`` valant ``""`` — c'est un trou que ce correctif n'a pas fermé,
faute d'un discriminant : rien dans la donnée ne distingue un motif d'une étape.

SEVERAL ``running`` TASKS ARE LEGITIMATE, grouped or not (T-01M5F7286N1EYGXAXA5244X86B,
pilot decision S-01M5DBTHMEAEXGD93Q284GJPJE): two machines, or two clones, each
run their own. ``start`` DEMOTES NOBODY — it keeps every other running task's
state, stage, actor and group — and only an EXPLICIT exit from ``running`` to
``pending`` or ``blocked`` (``block``, ``set_state``) writes ``lancee_sous``. The
DISPLAY focus is the first running task in store order (statusline, SessionStart
injection, Stop recap). The CLONE focus is a separate local fact: ``focus.json``
(``{task_id, updated_at}``), written by ``start``, by ``fournee`` (on the parent)
and by ``focus <T>`` (a running task only) — one active session per clone
(S-01M5E50AJX9V9AP8A8VBBHS6B4). ``review-scope <T> [<T>…]`` writes
``review-scope.json`` (``{focus, members, consumed, declared_at}``): the explicit
list of the next closing review, every member open, the focus among them; a
successful ``done`` consumes its member. Both live under ``.agents/state/local/``
of the MAIN repository (read through the ``.git`` file's ``commondir``, no git
run), ``root`` itself outside Git — a throwaway ``--root`` never reaches the real
repository.

A GROUP IS A COHERENCE GUARD, NOT A SECURITY ONE. ``parallel`` allocates one only
after proving that the writesets its members DECLARE are disjoint — nothing here
observes what an agent actually writes, and the proof is textual (symlinks,
junctions, 8.3 aliases and hard links are outside its reach; an impossible proof
counts as an overlap). A writeset includes the outputs a task GENERATES.
No observed enforcement exists — the disjunction rests on the writesets tasks
DECLARE — and a group is exactly as safe as its declarations are faithful.
See ``writeset_path_refusal`` for the admission
predicate and the discipline that goes with it.

``pending`` is REACHABLE, not just an initial state (T-00000095). It used to be
writable only by ``new`` and by the demotion side effect ``start`` then had, which left a blocked
task with no way home: once the blocker was lifted the only moves were editing
the store by hand — forbidden, and overwritten by the next write — or ``start``,
which forces the task to become THE active one and so lies about its readiness.
``unblock`` is the return path: ``blocked`` → ``pending``, blocking reason
cleared. It is strict about where it starts from, because a silent ``running`` →
``pending`` would be an invisible demotion of a running task.

``block`` NEVER erases what it cannot replace (T-00000103). Its reason lands in
``stage``, but a ``block`` with no ``--note`` used to write ``""`` there — a verb
whose only job is to annotate destroyed the pipeline step in flight and left a
blocked row with an information-free stage column. An absent note now preserves
the field and SAYS no reason was recorded. See ``block_task``.

A BLOCKER CAN BE A TASK, AND THEN THE BOARD RELEASES IT ITSELF (T-00000182).
``block --on T-MMM`` writes ``blocked_on: "T-MMM"`` — a MACHINE link, not prose —
and closing T-MMM turns every task blocked on it back to ``pending``, one loud
line per release. Before that, a dependency lived in the ``stage`` text where
nothing could read it: the blocker closed, and its dependents stayed red until
somebody remembered them. ONE blocker id, never a list: block on the LAST
remaining blocker, or re-block after a release. A task waiting on a HUMAN keeps
``--note`` alone — prose is never auto-released, and that asymmetry is the point.
``blocked_on`` NEVER survives an exit from ``blocked`` (``start``, ``done``,
``set_state`` to ``pending``, ``unblock`` all drop it), so a stale link can never
release a task that was re-blocked for another reason. Deleting a blocker does
NOT release: the work was not done, so the dependents stay blocked and the
dangling link is cleaned WITH a warning. See ``block_task`` and ``set_state``.

THE INVERSE QUESTION — "who waits on T-MMM?" — IS A READ (T-00000185).
``block --on`` records ONE link per task, so a task reads its own blocker with
``list --task``; what the board could not express is the reverse fan-out, and
``list --blocked-by T-MMM`` is exactly that filter: the tasks whose
``blocked_on`` points at T-MMM, short forms (``T-14`` / ``14``) accepted. It is
a FILTER, not a table column — the bare ``list`` never moves — on the same
grounds that kept ``chantier`` out of the table (T-00000184). An unknown id is a
LOUD refusal, never an empty result that would read as "nobody waits", and
``--blocked-by ""`` is refused too (unlike ``--chantier`` an empty value has no
meaning here). A ``done`` blocker legitimately matches nothing, because its links
were already purged when it closed — an announced absence, not a refusal.
See ``filter_tasks``.

``depends_on`` IS AN ORDER, ``blocked_on`` IS A STATE (T-00000530). They look
alike and they are not, so the four separations are written out rather than left
to be re-derived — the graph is useless if a reader "fixes" one into the other.

  1. STATE. ``blocked_on`` moves the task to ``blocked``; ``depends_on`` NEVER
     touches ``state``. A task whose dependency is not done stays ``pending``,
     which is what keeps it eligible for the night gate (see night_approve.py).
  2. LIFETIME. ``blocked_on`` is TRANSIENT — every exit from ``blocked`` drops
     it. ``depends_on`` is PERSISTENT: it survives ``start``, ``block``,
     ``unblock`` AND ``done``. That persistence is an ABSENCE of code in
     ``set_state``, so it is stated here: do not add the ``pop`` by symmetry.
  3. CARDINALITY. ``blocked_on`` is ONE id; ``depends_on`` is a LIST.
  4. COMPOSITION. Both at once is legitimate and reads "behind two, currently
     held by one".

``depends_on`` ORDERS AND GUARDS (S-01M4Z5VMP5E9YN8T6EMDTBAF0T). Every ``start``
whose source is not ``running`` — pending, blocked OR done — and the fournee
refuse an open upstream (transitive), a cycle, an unreadable journal, or a plan
approved BEFORE an upstream closed (``done_at`` against the elected trace); a
task restarted under the trace it was launched with (``lancee_sous``), every causing upstream closed by that launch (``lancee_le``), is a
REPRISE, said, never refused (one closed after it: PLAN_A_REPLANIFIER). ``--sans-dependances "<why>"`` skips it VISIBLY.
``deps-ready <id>`` reads the same judgment. ``done`` stays a DIRE. BOUND: only a
DECLARED dependency is seen.

``done`` ERASES NOTHING. Satisfaction is COMPUTED — an edge is satisfied iff its
target is ``done`` or absent from the board — never cleared. If closing a task
dropped the edges pointing at it, the graph would dissolve as a night proceeds
and nobody could reconstruct in the morning why the order was what it was.

A ``done`` TASK IS AN ADMISSIBLE DEPENDENCY, and this is where the symmetry with
``block --on`` BREAKS ON PURPOSE. ``block_task`` refuses a ``done`` blocker
because the release would have to fire into the past; ``depends_on`` releases
nothing, so a ``done`` dependency is simply a SATISFIED one — precisely what the
topological sort needs to place its dependent in wave 1.

WHAT ``depends_on`` IS NOT: two tasks touching the same file are not in a
dependency, they are in SERIALISATION — already carried by ``writeset`` and by
the night's own ordering rule. ``depends_on`` says "b must be FINISHED for a to
be correct", never "a and b write to the same place". Counting a shared file as
a dependency would make the graph false — EXCEPT when the pilot ORDERS it
(S-00002390 1b, T-00000765): a motif ``ORDRE PILOTE S-<id>`` records that
decision as an edge, protected from erasure (see ``plan_depends.py``).

``owner`` is REWRITABLE, not write-once (T-00000173). It used to be fixed at
creation by ``new --owner``, so a task whose nature changed in flight had no
place to record its new responsible agent and the name got smuggled into the
TITLE, which became a catch-all. ``reassign`` is the ``retitle`` of that one
field: same state-freedom, same single-field write. See ``reassign_task``.

``list`` FILTERS (T-00000103): the board outgrew a single dump, and an agent that
wants one task should not have to read all of them. ``--task`` narrows to one
task and prints every field; ``--state`` narrows to a closed-vocabulary state.
A bare ``list`` keeps its board byte for byte — see ``render_list``.

``chantier`` is a FREE-TEXT thematic group (T-00000184), optional and absent by
default. It is the one thing the board could not say: which tasks belong to the
same piece of work. Free text and unvalidated, exactly like ``owner`` — see
``regroup_task`` for why validating one verb and not the other is what makes a
field unusable. It is deliberately NOT a table column: ``FIELDS``/``WIDTHS``
stay as they are, so the generated view and the bare list do not move by one
column, and the value surfaces through ``list --task`` (every field),
``list --json``, ``list --chantier <name>`` (``""`` = the ungrouped tasks) and
``list --group`` (the same set cut into ``### <chantier> (n)`` sections,
alphabetical, ``(sans chantier)`` last). A task with no ``chantier`` key and a
task with ``""`` are the SAME task to every reader here: legacy entries need no
migration.

A RUNNING TASK GOES STALE IN SILENCE (T-00000183). ``updated`` is stamped by
every verb, so a ``running`` row a week old means the task was forgotten, not
that it is long — and nothing said so. A bare ``list`` now heads its board with
one alert line when that happens (``stale_running_warning``); the three hosts'
SessionStart hooks already read that output, so the alert reaches them without
a single hook edit. Filtered lists, ``--json`` and ``--statusline`` never carry
it.

Agents drive this through the CLI, never by editing either file::

    python tasks.py new "<title>" [--owner AGENT] [--chantier "<groupe>"] [--epic E-NN] [--mesure "<cmd> => <observed>" --motif M | --pas-un-defaut "<why>"]
    python tasks.py epic-new E-01 "<titre>" [--vague N] [--priorite P0|P1|P2] [--exclusive] [--risque TXT] [--maj]
    python tasks.py epic T-014 E-01 | --retirer   # optional epic (T-00001043); "" refused
    python tasks.py epic-list [--json]            # one line per epic, count by state
    python tasks.py start T-014 [--stage AGENT]
    python tasks.py stage T-014 documenter
    python tasks.py block T-014 --note "waiting pilot decision"
    python tasks.py block T-014 --on T-013   # machine link: released when T-013 is done
    python tasks.py unblock T-014    # blocker lifted → back in the queue
    python tasks.py done T-014 --raison "<pourquoi>"   # reason MANDATORY; releases
                                     # every task blocked ON T-014, and REMEMBERS which
    python tasks.py reopen T-014 --raison "<pourquoi>" [--sans-rebloquer]
                                     # the closure was wrong: done → pending, and the
                                     # links that closure released are restored
    python tasks.py retitle T-014 "<new title>"
    python tasks.py reassign T-014 frontend-fidelity   # owner only; "" = unassigned
    python tasks.py regroup T-014 "refonte auth"       # chantier only; "" = ungroups
    python tasks.py responsable T-014 "Ana"            # the HUMAN in charge; "" removes it (owner = agent)
    python tasks.py list --responsable Ana   # "" = nobody; with --state, --chantier, --json only
    python tasks.py limite T-014 --delai 2h | --echeance 2026-10-20T18:00Z | --jetons 500k | --retirer
    python tasks.py conso T-014 120k         # ADD declared tokens (host subagent_tokens: a finished subagent's LAST call, not its spend)
    python tasks.py depassements [--json]    # open tasks over their limit, rc 1 if any (read-only)
    # start/fournee/stage/conso print `LIMITE-DEPASSEE:` on stderr (rc unchanged); under the pilot's
    # .agents/state/gates/LIMITE_ARRET, start and fournee of an overrun task are REFUSED (rc 2).
    # start/fournee print `SESSION-PAIRE:` on stderr when another live Claude Code session holds a
    # running task whose clone focus they take or which they embark (rc unchanged); `list --session` heads with it.
    python tasks.py focus T-014              # clone focus = this RUNNING task (focus.json)
    python tasks.py review-scope T-014 T-015 # explicit list of the next closing review (focus included)
    python tasks.py writeset T-014 src/auth/ docs/auth.md   # declared files (--clear drops)
    python tasks.py direct T-014 [--retirer]  # small task checked by code, stamped: no plan chain
    python tasks.py depends T-014 T-012 T-013 --motif "why 14 waits"  # an ORDER, not a state (--clear drops)
    python tasks.py depends T-014 T-013 --add --motif "…" | --retirer T-012 | --retirer-ordre-pilote T-012 S-NNN  # T-00000765
    python tasks.py start|done T-014 … --sans-dependances "<why>"  # skip the upstream leg (start) and the plan's ARÊTE: control, VISIBLY
    python tasks.py depends-show T-014       # each outgoing edge: state, class, motif
    python tasks.py deps-ready T-014         # upstream closed? `deps-ready: <TOKEN>`, rc 0 AMONT_CLOS|REPRISE_DITE, 1 otherwise
    python tasks.py chrono T-014 step --etape dev --phase begin --lot T-015   # estimate, begin, step, show [--watch|--json]; rc 0/2
    python tasks.py parallel T-014 T-015    # one group, only if the writesets are disjoint
    python tasks.py fournee T-014 [--dry-run] # an approved plan's LOT: lines become parallel sub-tasks
    python tasks.py delete T-014 [--force]
    python tasks.py purge [--state done] [--before YYYY-MM-DD] [--dry-run] [--plafond N]
    python tasks.py list [--json]
    python tasks.py list --task T-014        # one task, every field (T-14 / 14 too)
    python tasks.py list --state blocked     # unknown state = usage error, not a void
    python tasks.py list --chantier auth     # one thematic group ("" = the ungrouped)
    python tasks.py list --blocked-by T-013  # the tasks whose blocked_on points at T-013
    python tasks.py list --depends-on T-013  # the tasks BEHIND T-013 (survives its closure)
    python tasks.py list --group             # sections by chantier, combinable --state
    python tasks.py list --epic E-01         # one epic ("" = no epic); --state, --json only
    python tasks.py render          # rewrite TASKS.md from TASKS.json
    python tasks.py --statusline

Exit code is 0 unless the arguments are invalid, the id is unknown, or the store
is malformed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

# The store is tracked project state; the view is a regenerable local artefact.
# They live in different buckets, hence two relative roots instead of one.
STORE_REL = Path(".agents") / "state" / "board"
VIEW_REL = Path(".agents") / "state" / "local"
STORE_NAME = "TASKS.json"
VIEW_NAME = "TASKS.md"
LOCK_NAME = "TASKS.lock"
# The post-done commit runs under a lock of its OWN, distinct from the board's
# (T-00000189, volet 1): serialising git commits must not serialise board reads.
POST_TASK_DONE_LOCK = "POST_TASK_DONE.lock"
# T-00000677 : le store d'événements V3 (`.agents/state/v3_event_store.db`) a été
# DÉSINDEXÉ — sa base VIVANTE vit hors dépôt sous `state_project()/run/`, et le
# doublon figé suivi a été retiré. Le verbe dédié qui le commitait (T-00000438),
# sa constante de chemin et la borne de sa jambe shell sont retirés avec lui.

# Closed vocabulary. The keyword is the data; the emoji is a rendering detail.
STATES = ("pending", "running", "blocked", "done")
STATE_EMOJI = {"running": "🟢", "blocked": "🔴", "pending": "⚪", "done": "✅"}

# Display order: what is live comes first, then the freshest done rows.
SORT_ORDER = {"running": 0, "blocked": 1, "pending": 2, "done": 3}
MAX_DONE_SHOWN = 3
# SessionStart injects `list --session`: running and blocked in full, then only
# the NEWEST pending rows. Measured 2026-09-29: 339 pending = 46.8 kB (~13k
# tokens) re-read on every model call of every session. The cut is ANNOUNCED
# with its count and the command that shows the rest — never a silent drop.
SESSION_MAX_PENDING = 20

# A running task untouched for this many days is presumed forgotten, not slow.
# Every board verb stamps ``updated``, so the field measures the last GESTURE on
# the task, not its age: a week without one means nobody moved it. Shorter (2-3
# days) would fire across a long weekend on a task nobody abandoned.
STALE_RUNNING_DAYS = 7

SYNC_EVENT_KINDS = (
    "BOARD_TASK_OBSERVED",
    "BOARD_COMMAND_REQUESTED",
    "BOARD_COMMAND_ACKED",
    "BOARD_COMMAND_FAILED",
    "BOARD_RUNNING_REPLACED",
)
SYNC_SNAPSHOT_FIELDS = ("id", "state", "task", "owner", "stage", "updated")
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.01
_LEASE_SECONDS = 30.0
_SUPPRESSED_SYNC_OPERATION: ContextVar[str | None] = ContextVar(
    "suppressed_board_sync_operation",
    default=None,
)
_BOARD_COMMIT_GUARD: ContextVar[Callable[[], bool] | None] = ContextVar(
    "board_commit_guard",
    default=None,
)
_BOARD_LOCK_DEPTH = threading.local()

# The section header a task with no ``chantier`` lands under, and the label the
# empty filter echoes back. ONE constant, because "no chantier" must read the
# same in every surface — a section title that differs from the filter's own
# wording is how a reader concludes the two are different sets.
NO_CHANTIER = "(sans chantier)"

FIELDS = ("id", "state", "task", "owner", "stage", "updated")
# FIXED widths: a long title truncates instead of reflowing every other row.
# This is what keeps the generated view's diff to the lines that changed.
WIDTHS = {"id": 28, "state": 10, "task": 44, "owner": 12, "stage": 22, "updated": 10}  # id: a whole T-<ULID>
EMPTY = "—"

VIEW_HEADER = """# Active tasks — {today}

<!-- GENERATED from TASKS.json by tasks.py — do not edit, edits are overwritten. -->
<!-- state: 🟢 running · 🔴 blocked · ⚪ pending · ✅ done. -->
<!-- Several running tasks may coexist; the clone focus is .agents/state/local/focus.json. -->
<!-- Details per task live in docs/tasks/T-NNN.md, never here. -->
"""


BINOME_CRITIQUES = ("critic-opus", "critic-fable", "critic-sonnet-max")
# LE NOMBRE DE CRITIQUES DISTINCTS QU'EXIGE LA CLÔTURE (S-00004500, T-00001226) : UN
# seul point à muter. Doublé textuellement dans `.claude/hooks/affirmation-guard.sh`
# (même nom, même valeur) ; `test_binome_min.py` lie les deux. Les `< 2` qui comptent
# des CYCLES de porte (`cycle_precedent`, `_verts_frozen`) ne relèvent PAS de lui.
BINOME_MIN = 1
BINOME_GATE = Path(".agents") / "state" / "gates" / "BINOME_REQUIRED"
BINOME_TRACES = Path(".agents") / "state" / "local" / "binome"
# THE MEASURE GUARD (T-00001128), same shape as BINOME_GATE: present, `new`
# refuses a task carrying neither `--mesure "<cmd> => <observed>"` nor
# `--pas-un-defaut "<why>"`; absent, the obligation is INERT (`mesure_refusal`).
MESURE_GATE = Path(".agents") / "state" / "gates" / "MESURE_REQUIRED"
MESURE_SEPARATEUR = "=>"


def commit_run_exports(root: str, lock_timeout: float | None = None) -> str:
    """Commit the versioned run exports under ``runs/`` (T-00000677).

    WHY THIS VERB EXISTS. The V3 event store left the repo with T-00000677 (its
    binary is gone, the store lives OUTSIDE the tree); only its versioned exports
    under ``runs/`` travel in git. Nothing committed them automatically, so the
    night's closing pushed a SHA that never carried its own events — exactly the
    property the removed verb guaranteed, and a defect the closure pair caught
    (S-00001808/S-00001809). The night's closing sequence now calls this verb, so
    a ``M runs/`` at morning goes back to meaning a REALLY interrupted night.

    Same shape as :func:`commit_stores`: it serialises the commit under the
    DEDICATED ``POST_TASK_DONE.lock`` and runs the shell SECTION leg
    (``post-task-done-index.sh --commit-section <root> run-exports``) inside it,
    relaying that leg's single token. ``nothing`` (no export changed) is a silent
    success, never a ``failed`` and never an empty commit. Bash is resolved, never
    the bare string (L-00000166), same rationale as :func:`commit_stores`.

    DELIBERATELY OUT of the ``mutating`` set in :func:`main`: committing run
    exports is not a board mutation, and it must NOT trigger a V3 replay — a
    replay would write new events, which would dirty ``runs/`` again, so the
    night's closing commit would never converge.
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash or "system32" in bash.replace("\\", "/").lower():
        return "bash-introuvable"
    script = Path(root) / ".agents" / "bin" / "post-task-done-index.sh"
    try:
        with board_lock(root, timeout_seconds=lock_timeout, name=POST_TASK_DONE_LOCK):
            proc = subprocess.run(
                [bash, str(script), "--commit-section", str(root), "run-exports"],
                capture_output=True,
                text=True,
            )
            lines = (proc.stdout or "").strip().splitlines()
            return lines[-1] if lines else "failed"
    except BoardError:
        return "locked-out"
    except Exception:
        return "failed"


# LES PARTIES (T-00000788). Le code du board vit dans les dix-sept fichiers
# ci-dessous, EXÉCUTÉS dans l'espace de noms de CE module — pas importés : chaque
# fonction déplacée a `__globals__ is vars(tasks)`, donc un `mock.patch.object(
# tasks, X)` atteint le code déplacé sans liste à tenir, et deux chargements de
# `tasks.py` sous deux noms (le pont V3 en fait un) restent ISOLÉS. Pourquoi pas
# des imports : la règle des 1600 lignes (S-00002684, S-00004034) et le mécanisme A tranché
# par le pilote (S-00002934). Liste FERMÉE, dans l'ordre du fichier d'origine.
# UNE partie lit à sa définition un nom d'une autre (relevé AST au 2026-10-02,
# T-00001071) : `DeverseIllisible(BoardError)`, d'où `tasks_deversement.py` APRÈS
# `tasks_stockage.py` ; (h) tient l'ORDRE, le NOMBRE reste un relevé daté ; le banc
# `test_tasks_decoupe.py` juge l'ensemble en (b), les doublons en (e).
# Chemin résolu depuis CE fichier, jamais `sys.path` ni le cwd. Une partie
# absente lève `FileNotFoundError` en nommant son chemin : une partie n'est pas
# une garde optionnelle, jamais de marche dégradée. Restent ICI, parce que des
# filets lisent le texte de CE fichier : la constante BINOME_CRITIQUES, `def
# commit_run_exports(` et le bloc `mutating` de `main`. Dette nommée : sous
# `src/cadre/`, `check_no_inprocess_load` interdit `exec` — le reconditionnement
# qui y placera ce fichier changera ce chargeur en imports.
PARTIES = (
    "tasks_stockage.py",
    "tasks_sync.py",
    "tasks_deversement.py",
    "tasks_dossier.py",
    "tasks_requetes.py",
    "tasks_rendu.py",
    "tasks_mesure.py",
    "tasks_verbes.py",
    "tasks_epics.py",
    "tasks_gardes.py",
    "tasks_direct.py",
    "tasks_etats.py",
    "tasks_graphe.py",
    "tasks_retour.py",
    "tasks_fournee.py",
    "tasks_jira.py",
    "tasks_cli.py",
)


def _charger_parties() -> None:
    """Exécute chaque partie de ``PARTIES``, dans l'ordre, dans CET espace de noms."""
    dossier = Path(__file__).resolve().parent
    # EN DEUX TEMPS : les octets des dix-sept parties sont TOUS lus, puis compilés et
    # exécutés. Cela RÉDUIT, sans la fermer, la fenêtre où un `git pull` en cours
    # ferait exécuter un arbre panaché (parties d'avant et d'après) : un pull qui
    # écrit entre deux lectures reste possible. Une partie absente lève donc
    # avant qu'aucune ne soit exécutée.
    lues = [(dossier / nom, (dossier / nom).read_bytes()) for nom in PARTIES]
    for chemin, octets in lues:
        code = compile(octets, str(chemin), "exec", dont_inherit=True)
        exec(code, globals())


_charger_parties()


# L'ACTEUR D'UN GESTE BOARD (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot A). `start`, `stage`, `done` et `fournee`
# signent ce qu'ils écrivent : `start_actor` à la 1re prise avec un auteur, gardé d'un cycle à l'autre et
# changé par une reprise prouvée seule (S-01M5HH8QMC4E7SYN4K6AP2SMKE), `stage_actor` à chaque stage réécrit
# (`poser_acteur_stage`, `tasks_etats.py`). Forme FERMÉE : {"auteur": {"nom", "email"}, "copie"}, chaque
# valeur une chaîne ou None. Résolu ICI, par la CLI, HORS DU VERROU et une fois par commande — jamais par
# l'API (`set_state` ne lance aucun git), jamais sous `--dry-run`. L'auteur est `git config --get
# user.name|user.email`, jamais `git var` ni l'hôte ou l'OS ; caviardé PUIS plafonné. La copie est le tirage
# aléatoire de V3 (`identifiant_de_copie`) ; V3 absent (la wheel) : un tirage frère de la partition, jamais
# dedans. Une identité indisponible n'est JAMAIS un refus : le champ vaut None et un avis le DIT sur stderr.
ACTEUR_PLAFOND = 100
ACTEUR_MARQUE = "...<truncated>"
#: Zones jetables du repli (bornées, comme `naissance_partition.ZONES_LITTERALES`), plus `gettempdir()` et
#: `$TMPDIR`/`$TEMP`/`$TMP` ; une zone qui contient le domicile n'est pas retenue.
ACTEUR_ZONES_TEMPORAIRES = ("/tmp", "/var/tmp", "/var/folders")
_ACTEUR_COPIE_RE = re.compile(r"[0-9a-f]{16}")
#: Lecture bornée du fichier de copie : un tirage fait 17 octets (16 hex et une fin de ligne).
ACTEUR_COPIE_OCTETS = 64


def _acteur_module_cadre(nom_module: str, fichier: tuple[str, ...]) -> Any:
    """`cadre.<…>` : le paquet INSTALLÉ d'abord (la wheel), puis — à défaut seulement — le fichier que le
    résolveur `vendor_paths` désigne sous l'arbre du MOTEUR, chargé par chemin sous un nom propre, sans
    toucher `sys.path`. None si rien ne répond (jamais une exception)."""
    import importlib
    import importlib.util

    try:
        return importlib.import_module(nom_module)
    except Exception:
        pass
    try:
        dossier = None if _RESOLVEUR_V3 is None else _RESOLVEUR_V3.dossier_paquet(
            Path(__file__).resolve().parents[2], "cadre")
        if dossier is None or not dossier.joinpath(*fichier).is_file():
            return None
        chemin = dossier.joinpath(*fichier).resolve()
        nom = "_cadre_acteur_" + nom_module.replace(".", "_")
        existant = sys.modules.get(nom)
        if existant is not None and Path(getattr(existant, "__file__", "") or "").resolve() == chemin:
            return existant
        spec = importlib.util.spec_from_file_location(nom, chemin)
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(nom, None)
            raise
        return module
    except Exception:
        return None


def _acteur_git(root: str, cle: str) -> str | None:
    """`git config --get <cle>` lu depuis `root` ; absente, vide ou git en panne : None."""
    import subprocess

    try:
        sortie = subprocess.run(["git", "config", "--get", cle], cwd=root, capture_output=True,
                                encoding="utf-8", errors="replace", timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    valeur = sortie.stdout.strip() if sortie.returncode == 0 else ""
    return valeur or None


def _acteur_texte(valeur: str | None, rediger: Callable[[str], str]) -> str | None:
    """Caviardé PUIS plafonné, l'ordre d'`events._resolve_user` : tronquer d'abord couperait un secret
    que la rédaction ne reconnaîtrait plus. Un dépassement porte `ACTEUR_MARQUE`."""
    if valeur is None:
        return None
    valeur = rediger(valeur)
    if len(valeur) > ACTEUR_PLAFOND:
        valeur = valeur[:ACTEUR_PLAFOND] + ACTEUR_MARQUE
    return valeur or None


def _acteur_racine_jetable(root: str) -> str | None:
    """La zone temporaire qui porte `root` quand `CADRE_STATE_DIR` est absent, sinon None : le repli
    n'écrit jamais l'état machine RÉEL pour une racine jetable (borne de `refus_naissance`, sans sa
    jambe worktree lié)."""
    if os.environ.get("CADRE_STATE_DIR", "").strip():
        return None
    racine = Path(os.path.realpath(root))
    domicile = Path(os.path.realpath(os.path.expanduser("~")))
    brut = [tempfile.gettempdir(), *(os.environ.get(n, "") for n in ("TMPDIR", "TEMP", "TMP")),
            *ACTEUR_ZONES_TEMPORAIRES]
    for zone in brut:
        if not str(zone).strip():
            continue
        z = Path(os.path.realpath(zone))
        if not domicile.is_relative_to(z) and racine.is_relative_to(z):
            return str(z)
    return None


def _acteur_copie_lue(fichier: Path) -> str | None:
    """Le tirage gardé dans `fichier`, ou None : jamais à travers un lien symbolique (`O_NOFOLLOW`, POSIX ;
    Windows : lien suivi), jamais
    un FIFO ni un périphérique (`O_NONBLOCK`, puis fichier ordinaire exigé), au plus `ACTEUR_COPIE_OCTETS`
    octets — au-delà, illisible —, et seulement 16 hex : rien d'autre n'atteint le board suivi."""
    import stat

    drapeaux = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(fichier, drapeaux)
    except OSError:  # absent, ou lien symbolique (ELOOP) : pas de tirage lisible
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        brut = os.read(fd, ACTEUR_COPIE_OCTETS + 1)
    finally:
        os.close(fd)
    if len(brut) > ACTEUR_COPIE_OCTETS:
        return None
    valeur = brut.decode("ascii", "replace").strip()
    return valeur if _ACTEUR_COPIE_RE.fullmatch(valeur) else None


def _acteur_copie_repli(root: str) -> tuple[str | None, str | None]:
    """V3 ABSENT (la wheel) : un tirage `token_hex(8)` gardé dans `<partition>.copie`, FRÈRE de la partition
    `state_project()` — la partition V3 ne naît pas ici. Publié ATOMIQUEMENT (temporaire puis `os.link` :
    le premier gagne, le perdant relit le gagnant). Peut différer de la copie de `runs/` si V3 arrive ensuite."""
    import secrets

    paths = _acteur_module_cadre("cadre.paths", ("paths.py",))
    if paths is None:
        return None, "copie inconnue : ni agentic_v3 ni cadre.paths sous le moteur"
    zone = _acteur_racine_jetable(root)
    if zone:
        return None, (f"copie non tirée : la racine est sous la zone temporaire {zone} "
                      "et CADRE_STATE_DIR est absent")
    try:
        partition = Path(paths.state_project(depuis=root))
        fichier = partition.with_name(partition.name + ".copie")
        lue = _acteur_copie_lue(fichier)
        if lue:
            return lue, None
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=fichier.name + ".", dir=str(fichier.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as flux:
                flux.write(secrets.token_hex(8) + "\n")
            try:
                os.link(tmp, fichier)
            except FileExistsError:
                pass
        finally:
            Path(tmp).unlink(missing_ok=True)
        lue = _acteur_copie_lue(fichier)
        return (lue, None) if lue else (None, f"copie illisible : {fichier}")
    except Exception as exc:
        return None, f"copie indisponible ({type(exc).__name__})"


def _acteur_copie(root: str) -> tuple[str | None, str | None]:
    """La copie V3 quand le résolveur trouve `agentic_v3` sous l'arbre du moteur (la couture du pont,
    `_importer_pont_v3` : provenance vérifiée) ; V3 absent : `_acteur_copie_repli`. Un REFUS de V3
    (provenance, racine jetable, worktree lié…) n'est pas une absence : copie None et avis, aucun repli."""
    depot = Path(__file__).resolve().parents[2]
    if _RESOLVEUR_V3 is None or _RESOLVEUR_V3.resoudre(depot, "agentic_v3") is None:
        return _acteur_copie_repli(root)
    try:
        _importer_pont_v3(depot)
        from agentic_v3.db import run_export

        copie = run_export.identifiant_de_copie(root)
    except Exception as exc:
        premiere = (str(exc).splitlines() or [""])[0][:200]
        return None, f"copie V3 refusée ({type(exc).__name__}) : {premiere}"
    if not _ACTEUR_COPIE_RE.fullmatch(str(copie)):  # le fichier `run/copie` est une donnée machine
        return None, "copie V3 non conforme (16 hex attendus) : non écrite"
    return str(copie), None


def acteur_courant(root: str) -> tuple[dict[str, Any], list[str]]:
    """`(acteur, avis)` du geste en cours. Rédaction introuvable : l'auteur n'est PAS écrit (None), dit."""
    avis: list[str] = []
    nom, email = _acteur_git(root, "user.name"), _acteur_git(root, "user.email")
    module = _acteur_module_cadre("cadre.ledger.redaction", ("ledger", "redaction.py"))
    rediger = getattr(module, "rediger", None)
    if rediger is None:
        if nom or email:
            avis.append("auteur non écrit : rédaction indisponible (cadre.ledger.redaction introuvable)")
        nom = email = None
    else:
        nom, email = _acteur_texte(nom, rediger), _acteur_texte(email, rediger)
    if nom is None and email is None:
        avis.append("auteur inconnu : aucune propriété de tâche attribuée")
    copie, avis_copie = _acteur_copie(root)
    if avis_copie:
        avis.append(avis_copie)
    return {"auteur": {"nom": nom, "email": email}, "copie": copie}, avis


def acteur_de_la_commande(root: str) -> dict[str, Any]:
    """`acteur_courant`, ses avis sur stderr ; une panne imprévue rend un acteur vide, jamais un refus."""
    try:
        acteur, avis = acteur_courant(root)
    except Exception as exc:
        acteur, avis = {"auteur": {"nom": None, "email": None}, "copie": None}, [
            f"acteur indisponible ({type(exc).__name__})"]
    for ligne in avis:
        print(f"TASKS: acteur — {ligne}", file=sys.stderr)
    return acteur


def _focus_apres(root: str, tid: str) -> None:
    """Le verbe a ABOUTI (``start``, ``fournee``) : le focus du clone passe à ``tid``, hors du verrou
    du board. Un échec d'écriture ne défait pas le verbe ; il est DIT, avec le remède. Une portée
    active que ce focus met HORS FOCUS est DITE aussi (``avis_portee_hors_focus``, F1 de la clôture)."""
    avis = avis_portee_hors_focus(portee_active(root), tid)
    try:
        poser_focus(root, tid)
    except (OSError, BoardError) as exc:
        print(f"tasks.py: focus non écrit ({type(exc).__name__}) — `tasks.py focus {tid}`", file=sys.stderr)
        return
    if avis:
        print(avis, file=sys.stderr)


def _consommer_apres(root: str, tid: str) -> None:
    """Le ``done`` a ABOUTI : il consomme son membre de la portée de revue, et le DIT sur stdout."""
    try:
        ligne = consommer_portee(root, tid)
    except (OSError, BoardError) as exc:
        print(f"tasks.py: review-scope non consommée pour {tid} ({exc})", file=sys.stderr)
        return
    if ligne:
        print(ligne)


def _valider_reprise(tid: str, raison: str, verbe: str = "start") -> None:
    """Friction du terminal pilote, avant tout pont V3 ou écriture du board."""
    prefixe = "REVENDICATION : reprise réservée au terminal du pilote, non lancé par un agent"
    if not raison.strip():
        raise BoardError(f"{prefixe} — --reprise exige une raison non vide")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise BoardError(f"{prefixe} — sous Windows : winpty bash .agents/pyrun.sh "
                         f".agents/bin/tasks.py {verbe} {tid} --reprise <raison>, ou Windows Terminal")
    import importlib.util
    chemin = Path(__file__).resolve().parent / "tracabilite_jira.py"
    try:
        spec = importlib.util.spec_from_file_location("_tasks_reprise_tracabilite", chemin)
        if spec is None or spec.loader is None:
            raise ImportError("spécification absente")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        marqueur = module.agent_appelant()
    except Exception as exc:
        raise BoardError(f"REVENDICATION : contrôle du marqueur indisponible ({type(exc).__name__})") from None
    if marqueur:
        raise BoardError(f"{prefixe} — marqueur {marqueur}")


def _confirmer_reprise(tid: str, proprietaire: object, leves: list[str]) -> None:
    """La question du terminal, APRÈS le précontrôle en lecture seule : elle NOMME à qui la reprise
    prend la tâche, et chaque refus que `--reprise` lève est dit avant la saisie."""
    for ligne in leves:
        print(f"{ligne} — levée par --reprise", file=sys.stderr)
    qui = _rev_texte(proprietaire) if proprietaire is not None else "aucun"
    print(f"REVENDICATION : reprise de {tid}, propriétaire courant {qui} ; "
          f"saisir exactement {tid} pour confirmer la reprise : ",
          end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().rstrip("\r\n") != tid:
        raise BoardError("REVENDICATION : identifiant non confirmé, aucune reprise")


# LE CHRONO D'UNE TÂCHE (T-01M5HST80E30DFMV3S7WM68Q7N, S-01M5HSTM4SXJQFMTGZ82807TJT). Le moteur est le
# frère `task_chrono.py`, chargé au premier `chrono` ; la façade VALIDE `tid` (et `--lot`) en LECTURE au
# board de la RACINE COMMUNE — un lot créé après la branche d'un worktree lié y est vu — puis délègue.
_TASK_CHRONO_NOM = "_cadre_task_chrono_bin"


def task_chrono_module() -> Any:
    """Le frère `task_chrono.py`, chargé au premier usage. Absent ⇒ ``BoardError`` nommant le remède."""
    chemin = Path(__file__).resolve().with_name("task_chrono.py")
    existant = sys.modules.get(_TASK_CHRONO_NOM)
    if existant is not None and Path(getattr(existant, "__file__", "") or ".").resolve() == chemin:
        return existant
    if not chemin.is_file():
        raise BoardError(f"le frère {chemin} est ABSENT — remède : `git checkout -- .agents/bin/task_chrono.py`")
    import importlib.util

    spec = importlib.util.spec_from_file_location(_TASK_CHRONO_NOM, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_TASK_CHRONO_NOM] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_TASK_CHRONO_NOM, None)
        raise
    return module


def chrono_verbe(root: str, args: argparse.Namespace) -> str:
    """`tasks.py chrono <tid> <action>` : rc 0 ou 2 seulement (réserve C29) ; un id inconnu au board
    de la racine commune lève `unknown task id` ; une `ChronoErreur` devient une `BoardError`.
    FORME DE LOT : `chrono <lot> …` sans `--lot`, sur un lot de fournée (`fournee.parent`), joue au
    journal du PARENT — `estimate` et `step` sous la clé `--lot <lot>`, `begin` reprend le cycle du
    parent, `show` l'affiche — : c'est le `done` du parent qui clôt le cycle, et l'historique comme
    l'agrégation par lot en sont nourris."""
    tc = task_chrono_module()
    try:
        base = tc.racine(root)
        donnees = load(str(base))
        tid, lot = args.tid, args.lot
        record = find(donnees, tid)
        if lot is not None:
            find(donnees, lot)
        else:
            fournee = record.get("fournee") if isinstance(record, dict) else None
            parent = fournee.get("parent") if isinstance(fournee, dict) else None
            if isinstance(parent, str) and parent:
                find(donnees, parent)
                tid, lot = parent, (args.tid if args.action in ("estimate", "step") else None)
        return tc.executer(base, donnees, tid, args.action, etape_nom=args.etape, phase=args.phase,
                           lot=lot, tentative=args.tentative, watch=args.watch, en_json=args.json)
    except tc.ChronoErreur as exc:
        raise BoardError(str(exc)) from None


#: Les verbes qui relèvent le chrono : un tuple LITTÉRAL (aucun frère chargé pour `list`, `new`…), tenu
#: égal à `task_chrono.VERBES_JALONNES` par le banc (test_tasks_chrono, C20).
_VERBES_CHRONO = ("start", "fournee", "retour", "done", "review-scope")


def _chrono_apres(root: str, args: argparse.Namespace, rc_verbe: int) -> None:
    """LES JALONS POSÉS PAR LE VERBE (T-01M5KKFBCXXEVYR8GJPYFEH3C8) : après `start`, `fournee`, `retour`,
    `done` et `review-scope` ABOUTIS — jamais sous `--statusline`, `--dry-run` ou un `retour` refusé —,
    `task_chrono` relève le cycle au journal local de la racine commune ; `review-scope` relève `juges` et
    ouvre `cloture`, `done` complète `cloture`, `correction` et `porte` (T-01M5PVWHM8KRNRF960PTBV4FE7). Tout ce qu'il dit va sur STDERR ; une erreur, quelle
    qu'elle soit, devient `CHRONO: non relevé (<cause>)` : le rc et le stdout du verbe sont inchangés.
    SOUS LE VERROU DU BOARD de la racine commune, relecture comprise : un verbe concurrent (une `fournee`
    après ce `done`) ne s'intercale pas entre la lecture de l'état et l'écriture des jalons. Le verbe a
    déjà rendu son propre verrou ici ; `board_lock` est réentrant dans le même fil.
    LA FIN DE FUSION (T-01M5PFPSCG0GXM12SK1MRYGZDY), au `retour` et au `done`, en TROIS TEMPS : sous le
    verrou, les fusions ouvertes et leurs pointes (aucun git) ; HORS du verrou, l'heure du commit de fusion
    par `retour_git` (S-00004192, voie (a) : git jamais sous le verrou) ; sous le verrou, le board et le
    journal RELUS avant d'écrire. Sans fusion ouverte à pointe relevée : aucun git. LA PORTE, au `done`, en
    les mêmes trois temps : sous le premier verrou, la fin de clôture (journal, sinon traces `binome_trace`)
    et les lignes de `porte-chrono.tsv` après elle ; hors verrou, `rev-list` par `retour_git` ; sous le
    second verrou, clôture, porte et correction. Sans clé `cloture` ni trace : aucun git."""
    if args.statusline or args.cmd not in _VERBES_CHRONO \
            or getattr(args, "dry_run", False) or rc_verbe:
        return
    try:
        tc = task_chrono_module()
        base = tc.racine(root)
        tids = list(args.tids) if args.cmd in ("retour", "review-scope") else [args.tid]
        mesures, portes, avis_du_verbe = {}, {}, []
        if args.cmd in tc.VERBES_DE_FUSION:
            with board_lock(str(base)):
                donnees = load(str(base))
                candidats = tc.fusions_a_mesurer(base, donnees, args.cmd, tids)
                a_mesurer = tc.portes_a_mesurer(base, donnees, args.cmd, tids,
                                                lambda t: binome_trace(str(base), t))
            git = lambda *a: retour_git(str(base), *a)  # noqa: E731 — résolu à l'appel (bancs : retour_git espionné)
            mesures, avis_du_verbe = tc.fusions_premesurees(candidats, git)
            portes, avis_porte = tc.portes_premesurees(a_mesurer, git)
            avis_du_verbe += avis_porte
        with board_lock(str(base)):
            avis_du_verbe += tc.jalons_du_verbe(base, load(str(base)), args.cmd, tids, fusions=mesures,
                                                portes=portes)
        for avis in avis_du_verbe:
            print(avis, file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne bloque jamais le verbe
        print(f"CHRONO: non relevé ({type(exc).__name__}: {exc})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = _construire_parseur(argv)

    args = ap.parse_args(argv)
    # Normalise the MSYS root the hooks hand us (L-00000063) so the board lock,
    # the POST_TASK_DONE lock and the commit all fall on the SAME resolved tree.
    root = normalize_root(args.root)
    force_utf8_stdio()

    # THE MATRIX IS CLOSED AND LOUD (T-00000184, extended T-00000185). `--group`
    # sections a set; it combines with `--state` (the motivating read: "les
    # pending par chantier") and with nothing else. `--json` has no sections to
    # express, `--task` is one row, `--chantier` is already a single group, and
    # `--blocked-by` is a flat dependency fan-out with no chantier axis to cut.
    # Refused at exit 2 rather than ignored: a flag silently dropped makes the
    # output read as an answer to the question that was asked.
    if args.cmd == "list" and args.group:
        remedies = {
            "--chantier": " — use --chantier alone to read one group",
            "--blocked-by": " — use --blocked-by without --group",
            "--depends-on": " — use --depends-on without --group",
        }
        for flag, forbidden in (
            ("--json", args.json),
            ("--task", args.task is not None),
            ("--chantier", args.chantier is not None),
            ("--blocked-by", args.blocked_by is not None),
            ("--depends-on", args.depends_on is not None),
        ):
            if forbidden:
                ap.error(
                    f"list --group does not combine with {flag}"
                    + remedies.get(flag, " — --group only combines with --state")
                )
    # `--session` is the SessionStart read, a fixed shape: it takes no filter.
    if args.cmd == "list" and args.session:
        for flag, forbidden in (
            ("--json", args.json),
            ("--task", args.task is not None),
            ("--state", args.state is not None),
            ("--chantier", args.chantier is not None),
            ("--blocked-by", args.blocked_by is not None),
            ("--depends-on", args.depends_on is not None),
            ("--group", args.group),
        ):
            if forbidden:
                ap.error(f"list --session does not combine with {flag} — it is the fixed SessionStart view")
    # `--epic` (T-00001043) is one flat set: it combines with `--state` and `--json`
    # and with nothing else — refused at exit 2, never silently dropped.
    if args.cmd == "list" and args.epic is not None:
        for flag, forbidden in (
            ("--group", args.group),
            ("--session", args.session),
            ("--task", args.task is not None),
            ("--chantier", args.chantier is not None),
            ("--blocked-by", args.blocked_by is not None),
            ("--depends-on", args.depends_on is not None),
        ):
            if forbidden:
                ap.error(f"list --epic does not combine with {flag} — it combines with --state and --json only")
    # `--responsable` (T-01M54GEHJBGA5996W0T48JXNQ4): combines with --state, --chantier and
    # --json; every other filter is refused at exit 2, never silently dropped.
    if args.cmd == "list" and args.responsable is not None:
        for flag, forbidden in (
            ("--group", args.group),
            ("--task", args.task is not None),
            ("--session", args.session),
            ("--epic", args.epic is not None),
            ("--blocked-by", args.blocked_by is not None),
            ("--depends-on", args.depends_on is not None),
        ):
            if forbidden:
                ap.error(f"list --responsable does not combine with {flag} — it combines with --state, --chantier and --json only")

    # UN pont par commande : les deux `_replay_v3()` d'un verbe mutant partagent la
    # construction du premier, ou son REFUS — doctrine « refuser le pont plutôt que
    # le verbe » : voir `replay_sync`, `pont_commande` (T-00000782).
    # `differer` (T-00001007) : l'annonce d'un refus attend l'issue du verbe, `_annoncer_refus_pont` ; la fenêtre se
    # ferme AVANT le drain d'après le verbe, qui dit aussitôt ce qu'il refuse (suite vraie : le verbe a abouti).
    _pont_v3: dict[str, Any] = {"differer": True}

    def _replay_v3() -> None:
        replay_sync(root, pont_commande=_pont_v3)

    rc_verbe = 0  # seul `retour` le pose (1 = refus) ; rendu en fin de `main`
    try:
        acteur_revendication = None
        ids_revendication: list[str] = []
        preuves_revendication: dict[str, dict[str, Any]] = {}
        proprietes_revendication: dict[str, dict[str, Any]] = {}
        levees_revendication: dict[str, list[dict[str, Any]]] = {}
        # LIMITE (T-01M54GEMCH3JWA95G61N2J70KS) : DIRE avant `start`/`fournee`/`stage`, rc INCHANGÉ ;
        # sous `LIMITE_ARRET`, `start` et `fournee` d'une tâche dépassée REFUSÉS rc 2 AVANT tout appel
        # du verbe et tout drain (M10 : la fournée crée ses lots avant de démarrer le parent), et avant
        # le précontrôle de REVENDICATION, qui lit le board et interroge le distant : un refus
        # de limite ne coûte aucun fetch, et un board illisible y reste le refus de l'arrêt.
        if args.cmd in ("start", "fournee", "stage") and not args.statusline:
            alerte_limite, refus_limite = limite_jugement(root, args.cmd, args.tid)
            if alerte_limite:
                print(alerte_limite, file=sys.stderr)
            if refus_limite:
                print(f"tasks.py: {refus_limite}", file=sys.stderr)
                return 2
        if args.cmd in ("start", "fournee") and not args.statusline and not getattr(args, "dry_run", False):
            if args.sans_revendication is not None:
                raise BoardError("REVENDICATION : --sans-revendication est retiré ; "
                                 "le pilote utilise --reprise dans son terminal")
            if args.reprise is not None:
                _valider_reprise(args.tid, args.reprise, args.cmd)
            acteur_revendication = acteur_de_la_commande(root)
            if args.reprise is not None and _rev_auteur(acteur_revendication) is None:
                raise BoardError("REVENDICATION : identité du pilote inconnue, reprise refusée")
            ids_rev = args.tid
            if args.cmd == "fournee":
                donnees_rev = load(root)
                ids_rev = [args.tid] + [t["id"] for t in fournee_lots_existants(donnees_rev, args.tid).values()
                                        if t.get("state") in ("pending", "running")]
            ids_revendication = [ids_rev] if isinstance(ids_rev, str) else list(ids_rev)
            if len(ids_revendication) > REVENDICATION_IDS_MAX:
                raise BoardError(f"REVENDICATION: {len(ids_revendication)} tâches ; maximum {REVENDICATION_IDS_MAX}"
                                 " — découper la fournée (--reprise ne lève pas cette borne)")
            refus_rev, avis_rev = precontrole_revendication(root, ids_rev, acteur_revendication,
                                                             preuves=preuves_revendication,
                                                             levees=levees_revendication)
            for avis in avis_rev:
                print(avis, file=sys.stderr)
            if refus_rev and args.reprise is None:
                raise BoardError("\n".join(refus_rev) + "\n"
                                 "REVENDICATION: publier/fusionner la branche, ou reprise par le pilote avec --reprise")
            if args.reprise is not None:
                rang = next((t for t in load(root)["tasks"] if t.get("id") == args.tid), {})
                _confirmer_reprise(args.tid, _rev_auteur(rang.get("start_actor")), refus_rev)
        # `--statusline` saute le verbe (`if args.statusline:` plus bas) : rien à écrire, donc rien à drainer ni à annoncer.
        mutating = args.cmd in {
            "new",
            "start",
            "stage",
            "block",
            "unblock",
            "done",
            "reopen",
            "retitle",
            "reassign",
            "regroup",
            "responsable",
            "limite",
            "conso",
            "epic",
            "epic-new",
            "writeset",
            "direct",
            "depends",
            "parallel",
            "delete",
            "purge",
            "retour",
            "livraison",
            "fournee",
            "jira-import",
            "jira-claim",
        } and not (args.cmd == "purge" and args.dry_run) and not args.statusline and not (args.cmd == "retour" and args.dry_run) \
            and not (args.cmd == "fournee" and args.dry_run) and not (args.cmd in ("jira-import", "jira-claim") and args.dry_run)
        # SESSION-PAIRE (T-01M54GEHJBGA5996W0T48JXNQ4) : FAIRE VOIR, jamais refuser — une
        # ligne stderr avant `start`/`fournee` (`--dry-run` compris), rc INCHANGÉ.
        if args.cmd in ("start", "fournee") and not args.statusline:
            alerte = alerte_session_paire(root, args.cmd, args.tid)
            if alerte:
                print(alerte, file=sys.stderr)
        if mutating:
            _replay_v3()
        # LE PROPRIÉTAIRE SE LIT APRÈS LE DRAIN V3 (contrat W4) : un id inconnu draine puis rend son
        # « unknown task id » au verbe, et `ancien` est celui du board rejoué, revalidé sous verrou.
        if ids_revendication:
            rejoue = {t["id"]: t for t in load(root)["tasks"]}
            for identifiant in ids_revendication:
                ancien = (rejoue.get(identifiant) or {}).get("start_actor")
                proprietes_revendication[identifiant] = {"ancien": copy.deepcopy(ancien)}
                if args.reprise is not None:
                    preuves_revendication[identifiant] = {
                        "ancien": copy.deepcopy(ancien), "nouveau": copy.deepcopy(acteur_revendication),
                        "manuel": True, "raison": args.reprise.strip(),
                        "levees": copy.deepcopy(levees_revendication.get(identifiant, []))}
        if args.statusline:
            print(statusline(root))
        elif args.cmd == "new":
            print(new_task(root, args.title, args.owner, args.chantier, epic=args.epic,
                           mesure=args.mesure, pas_un_defaut=args.pas_un_defaut, motif=args.motif,
                           responsable=args.responsable))
        elif args.cmd == "epic-new":
            print(new_epic(root, args.eid, args.titre, vague=args.vague, priorite=args.priorite,
                           exclusive=args.exclusive, risque=args.risque, maj=args.maj))
        elif args.cmd == "epic":
            print(set_epic(root, args.tid, args.eid, retirer=args.retirer))
        elif args.cmd == "epic-list":
            # READ-ONLY, deliberately OUT of `mutating`: no V3 replay around it.
            print(render_epic_list(load(root), as_json=args.json))
        elif args.cmd == "start":
            acteur = acteur_revendication  # résolu une fois, avant V3 et hors verrou
            print(set_state(root, args.tid, "running", stage=args.stage,
                            sans_chaine=args.sans_chaine,
                            sans_cible=args.sans_cible, sans_dependances=args.sans_dependances,
                            acteur=acteur, preuve_reprise=preuves_revendication.get(args.tid),
                            propriete_attendue=proprietes_revendication.get(args.tid)))
            marquer_session(root, [args.tid])
            _focus_apres(root, args.tid)  # `find` est EXACT : l'id du verbe est l'id stocké
            try:
                jira_avis = jira_claim_after_start(root, args.tid)
            except BoardError as exc:
                jira_avis = f"JIRA: {args.tid} prise en attente ({exc})"
            if jira_avis:
                print(jira_avis)
        elif args.cmd == "focus":
            print(fixer_focus(root, args.tid))
        elif args.cmd == "review-scope":
            print(declarer_portee(root, args.tids))
        elif args.cmd == "stage":
            print(stage_task(root, args.tid, args.stage, acteur=acteur_de_la_commande(root)))
        elif args.cmd == "block":
            print(block_task(root, args.tid, args.note, args.blocked_on))
        elif args.cmd == "unblock":
            print(unblock_task(root, args.tid))
        elif args.cmd == "done":
            # LA PRÉ-MESURE DU RELEVÉ (T-00001182, S-00004192 voie (a)) : git tourne ICI, HORS du
            # verrou que `set_state` prend ; `--sans-cible` la saute (la jambe retour aussi).
            pre = None if args.sans_cible else retour_premesure(root, args.tid)
            acteur = acteur_de_la_commande(root)  # hors verrou, comme la pré-mesure
            print(set_state(root, args.tid, "done", stage=args.raison,
                            sans_binome=args.sans_binome,
                            sans_cible=args.sans_cible, sans_dependances=args.sans_dependances,
                            retour_premesure=pre, acteur=acteur))
            _consommer_apres(root, args.tid)
        elif args.cmd == "reopen":
            print(reopen_task(root, args.tid, args.raison, rebloquer=not args.sans_rebloquer))
        elif args.cmd == "retitle":
            print(retitle_task(root, args.tid, args.title))
        elif args.cmd == "reassign":
            print(reassign_task(root, args.tid, args.owner))
        elif args.cmd == "regroup":
            print(regroup_task(root, args.tid, args.chantier))
        elif args.cmd == "responsable":
            print(responsable_task(root, args.tid, args.responsable))
        elif args.cmd == "limite":
            print(limite_task(root, args.tid, delai=args.delai, echeance=args.echeance,
                              jetons=args.jetons, retirer=args.retirer))
        elif args.cmd == "conso":
            print(conso_task(root, args.tid, args.quantite))
            alerte_limite, _ = limite_jugement(root, "conso", args.tid)
            if alerte_limite:
                print(alerte_limite, file=sys.stderr)
        elif args.cmd == "depassements":
            # READ-ONLY, OUT of `mutating` : rc 1 dès une entrée (dépassement ou valeur illisible),
            # la RÉPONSE sur STDOUT comme `deps-ready` ; `--json` = C-json, `[]` à rc 0.
            rc_depassements, texte_depassements = render_depassements(root, as_json=args.json)
            print(texte_depassements)
            return rc_depassements
        elif args.cmd == "writeset":
            print(set_writeset(root, args.tid, args.paths, clear=args.clear))
        elif args.cmd == "direct":
            print(estampiller(root, args.tid, retirer=args.retirer))
        elif args.cmd == "depends":
            print(set_depends(root, args.tid, args.deps, clear=args.clear, motif=args.motif,
                              add=args.add, retirer=args.retirer,
                              retirer_ordre_pilote=args.retirer_ordre_pilote))
        elif args.cmd == "parallel":
            print(declare_parallel_group(root, args.tids))
        elif args.cmd == "delete":
            print(delete_task(root, args.tid, force=args.force))
        elif args.cmd == "purge":
            print(purge_tasks(root, state=args.state, before=args.before, dry_run=args.dry_run, plafond=args.plafond))
        elif args.cmd == "retour":
            # `tasks_retour.py` : une ligne par contrôle, puis `RETOUR: ok|refus`.
            # rc 1 sur refus, rendu par `rc_verbe` APRÈS le second `_replay_v3`.
            releve = retour_inscrire(root, args.tids, args.base, args.branche, dry_run=args.dry_run,
                                     vers=args.vers)
            print(retour_rendu(releve))
            rc_verbe = 0 if releve["verdict"] == "ok" else 1
        elif args.cmd == "livraison":
            # `tasks_gardes.py` : le MÊME dict sur chaque tâche nommée ; un refus liste TOUTES ses causes (rc 2).
            print(livraison_declarer(root, args.tids, args.branche, retirer=args.retirer))
        elif args.cmd == "fournee":
            # `tasks_fournee.py` : prévol pur, puis six étapes sous UN verrou ; un refus
            # est une `BoardError` (rc 2) qui liste TOUTES ses causes.
            # `--dry-run` reste PUR : aucun git, aucune copie tirée ; sinon l'acteur est résolu hors verrou.
            print(fournee(root, args.tid, dry_run=args.dry_run, sans_chaine=args.sans_chaine,
                          sans_cible=args.sans_cible, sans_dependances=args.sans_dependances,
                          sans_revendication=args.sans_revendication or "",
                          acteur=acteur_revendication, preuves_reprise=preuves_revendication,
                          proprietes_attendues=proprietes_revendication))
            if not args.dry_run:
                marquer_session(root, [args.tid], fournee_de=args.tid)
                _focus_apres(root, args.tid)  # la fournée fixe le focus sur son PARENT
                try:
                    jira_avis = jira_claim_after_start(root, args.tid)
                except BoardError as exc:
                    jira_avis = f"JIRA: {args.tid} prise en attente ({exc})"
                if jira_avis:
                    print(jira_avis)
        elif args.cmd == "jira-import":
            rapport_jira, collision_jira = jira_import(root, args.project, issue_key=args.issue, dry_run=args.dry_run)
            print(rapport_jira)
            if collision_jira:
                rc_verbe = 2
        elif args.cmd == "jira-claim":
            print(jira_claim_retry(root, args.retry, dry_run=args.dry_run))
        elif args.cmd == "render":
            render_view(root)
            print(f"TASKS.md regenerated from {STORE_NAME}")
        elif args.cmd == "replay-sync":
            # Verbe EXPLICITE, sans board écrit : refus = ÉCHEC rc 1, annonce adaptée (T-782).
            pont: dict[str, Any] = {"explicite": True}
            rejoues = replay_sync(root, pont_commande=pont)
            if pont.get("refus"):
                return 1
            print(f"TASKS: replayed {rejoues} sync intent(s)")
        elif args.cmd == "commit-stores":
            # `--exiger`: same opt-in exit code as `commit-run-exports` below
            # (T-00001044); the `done` hook never passes it, so rc 0 there holds.
            jeton = commit_stores(root, lock_timeout=args.lock_timeout)
            print(jeton)
            if getattr(args, "exiger", False) and jeton not in ("committed", "nothing"):
                return 1
        elif args.cmd == "binome-purge":
            # OUT of `mutating` (T-00000842): the board is only READ, under its lock
            # so the purge never interleaves with a `done` reading the same traces.
            # An unknown id is refused by `find` (exact match, "unknown task id").
            with board_lock(root):
                cible = find(load(root), args.tid)
                tid = cible["id"]
                if cible.get("state") == "running":
                    # Fail-closed, but SAID: a running slot's purge also removes
                    # the proof its chantier sub-tasks would borrow at `done`.
                    print(
                        f"TASKS: {tid} is running — its chantier sub-tasks lose the borrowed proof",
                        file=sys.stderr,
                    )
                retires = purge_binome_trace(root, tid)
            if retires:
                print(f"TASKS: {tid} binome traces purged — {', '.join(retires)}")
            else:
                print(f"TASKS: {tid} binome traces — aucune trace")
        elif args.cmd == "commit-run-exports":
            # `--exiger` turns the token into an EXIT CODE so the night's closing can
            # chain the gate with `&&` instead of re-reading a prose token (T-00000677
            # B1): a failure token that only PRINTS lets a caller push a SHA without
            # the night's events — the guarantee was prose, not mechanism (L-00000111).
            # The `done` hook NEVER passes `--exiger`, so its "always exit 0" contract
            # is intact — the non-zero exit is opt-in, reserved to the night's chain.
            jeton = commit_run_exports(root, lock_timeout=args.lock_timeout)
            print(jeton)
            if getattr(args, "exiger", False) and jeton not in ("committed", "nothing"):
                return 1
        elif args.cmd == "list":
            if args.session:
                print(render_session_board(root))
            elif args.epic is not None:
                # BEFORE the bare `--json` branch below: placed after it, `list --json
                # --epic E-01` would print the whole board (T-00001043).
                sortie, absence = render_epic_tasks(load(root), args.epic, state=args.state, as_json=args.json)
                print(sortie)
                if absence:
                    print(f"tasks.py: {absence}", file=sys.stderr)
            elif not args.json:
                print(render_list(root, task=args.task, state=args.state, chantier=args.chantier, group=args.group, blocked_by=args.blocked_by, depends_on=args.depends_on, responsable=args.responsable))
            elif args.task is None and args.state is None and args.chantier is None and args.blocked_by is None and args.depends_on is None and args.responsable is None:
                print(json.dumps(sorted_tasks(load(root)["tasks"]), indent=2, ensure_ascii=False))
            else:
                matched = filter_tasks(load(root), task=args.task, state=args.state, chantier=args.chantier, blocked_by=args.blocked_by, depends_on=args.depends_on, responsable=args.responsable)
                # STDOUT stays parseable JSON — `[]` is the right answer to a
                # machine. The absence is announced on STDERR so the human or
                # agent reading along still hears it, without a prose line
                # landing in a stream something is piping to a JSON parser.
                print(json.dumps(matched, indent=2, ensure_ascii=False))
                if not matched:
                    label = filter_label(task=args.task, state=args.state, chantier=args.chantier, blocked_by=args.blocked_by, depends_on=args.depends_on, responsable=args.responsable)
                    print(f"tasks.py: no task matching {label}", file=sys.stderr)
        elif args.cmd == "depends-show":
            # READ-ONLY, so deliberately OUT of the `mutating` set above: no V3
            # replay runs around it, it classifies the outgoing edges and prints.
            print(render_depends_show(root, args.tid))
        elif args.cmd == "deps-ready":
            # READ-ONLY, OUT of `mutating` (S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : rc 0 AMONT_CLOS ou
            # REPRISE_DITE, rc 1 tout autre jeton — la RÉPONSE du contrôle, sur STDOUT ; un id
            # inconnu est une `BoardError` (rc 2).
            rc_deps, texte_deps = render_deps_ready(root, args.tid)
            print(texte_deps)
            return rc_deps
        elif args.cmd == "chrono":
            # OUT of `mutating` : écrit le journal LOCAL du chrono (begin, step), jamais le board ni V3.
            texte_chrono = chrono_verbe(root, args)
            if texte_chrono:
                print(texte_chrono)
        elif args.cmd == "cible-check":
            # READ-ONLY. `plan_cible.cible_check` returns (rc, message): rc 0 all
            # steps annotated, rc 1 some step has no target (message NAMES them),
            # rc 2 a config error (no spec, unreadable file). rc 2 goes to STDERR
            # like every other usage error here; 0/1 are the check's ANSWER and go
            # to STDOUT. We return the rc directly — no V3 replay, nothing to
            # commit, no board mutation.
            _pc = plan_cible_module()
            if _pc is None:
                print("cible-check: .agents/bin/plan_cible.py est absent de cet "
                      "arbre — rien à vérifier.", file=sys.stderr)
                return 2
            rc_cible, msg_cible = _pc.cible_check(root, args.plan, args.spec)
            print(msg_cible, file=sys.stderr if rc_cible == 2 else sys.stdout)
            return rc_cible
        else:
            ap.print_help()
        if mutating:
            _annoncer_refus_pont(_pont_v3)  # verbe abouti : « board écrit » est vrai, AVANT le drain d'après (donc avant `AU SEUIL`)
            _pont_v3.pop("differer", None)  # le verbe est fini : un refus né au drain d'après se dit aussitôt
            _replay_v3()
        _chrono_apres(root, args, rc_verbe)  # verbe abouti : stderr seul, ne lève jamais
    except BoardError as exc:
        _annoncer_refus_pont(_pont_v3, "verbe refusé — board NON écrit")
        print(f"tasks.py: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:  # `RecordIdError` du frère d'allocation (générateur absent) : un refus, jamais une trace
        if not isinstance(exc, getattr(sys.modules.get(_RECORD_ID_NOM), "RecordIdError", ())):
            raise
        _annoncer_refus_pont(_pont_v3, "verbe refusé — board NON écrit")
        print(f"tasks.py: {exc}", file=sys.stderr)
        return 2
    finally:  # une levée hors `BoardError` ne fait pas disparaître le refus ; vide si déjà dit
        _annoncer_refus_pont(_pont_v3, "verbe interrompu — écriture du board NON confirmée")
    return rc_verbe


if __name__ == "__main__":
    sys.exit(main())
