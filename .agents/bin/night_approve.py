#!/usr/bin/env python3
"""Write the `/night` eligibility contracts of N NAMED lots in one gesture.

WHY this exists (T-00000233). `/night` has a CLOSED agenda: a task enters it
only if it carries a `night-eligible: approved` contract written by
`/kickoff --defer-night`. That contract is born of a PER-LOT approval — twelve
ready lots meant twelve stops for the pilot. What makes that cost absurd is
measured: once launched, the night asks for nothing more (20 commits and 3
pushes on `main` between the 2026-08-18 go and its closure, without a single
solicitation). The only friction point is the ENTRANCE to the agenda.

**THIS TOOL DOES NOT APPROVE IN THE PILOT'S PLACE.** It EXECUTES, in one
gesture, an approval he gives once, by **explicitly NAMING** the lots. There is
therefore:

- no "approve everything" mode,
- no implicit default,
- **no discovery of lots by sweeping the board** — that would be the open
  agenda, ruled out by the pilot himself after restitution of the arbitration.

CLI, modelled EXACTLY on `sync_template.py` (the repo already has that couple;
a third dialect would be a memory load for nothing)::

    python .agents/bin/night_approve.py [--check | --apply]
                                        --lot <plan.md> T-a T-b [...]
                                        [--lot <plan.md> T-c ...]
                                        [--root DIR]

`--check` is the DEFAULT: it describes and writes nothing. `--apply` writes.
`--lot` is repeatable. **A `--lot` naming no task is REFUSED loudly**, never
treated as a silent no-op: an empty lot is a command the pilot believes he
issued and which did nothing.

THE CONDITIONS, fail-closed (five below, 6 — draft —, 7 — night-delivered — and 8 — committed)
----------------------------------------------------------------------------------------------
They are EXACTLY the ones the night re-checks by itself, plus one. The tool
must not be able to write a contract the night will then refuse, or it produces
an approval that serves nothing while the pilot believes he approved:

1. the task is `pending` (never `running`, `blocked`, `done`, never absent);
2. the plan file EXISTS;
3. a `plan-critic` verdict `GO` or `GO_AVEC_RESERVES` (or a historic `PASS` or
   `CONCERNS`) exists for that plan in the journal;
4. the RECOMPUTED sha256 of the plan is identical to the one recorded in that
   verdict;
5. **the plan ENROLS the task** — the id appears in the plan's **title** or in
   its **roster line** (`Tâches : T-… · T-…`), **never just anywhere in the
   bytes**.

Condition 5 closes a defect that already exists in the CURRENT mechanism: today
a typo in a `--defer-night` produces a perfectly valid contract pointing at a
plan that never mentions the task, and the night then executes it against a
plan that does not describe it. The "anywhere in the bytes" version was BEATEN
BY THIS REPO ITSELF — `LOT-3-plan.md:62` cites `T-00000209` to say it is
deferred and NOT handled, `LOT-1-plan.md:93` cites `T-00000203` as "untouched".
A typo between adjacent ids would have produced a valid contract for exactly
the task the plan says it does not treat.

ROSTER EXTRACTION RULE, named as precisely as the verdict one. Two locations
and two only: **line 1** (the title) and the **FIRST** line matching
`^Tâches\\s*:`. The pattern is `T-<ULID>` (first, right-bounded) or `T-\\d{8}`
(T-00001040), **never a split on a separator** —
`LOT-8A-plan.md:1` separates its ids with COMMAS where the others use `·`, so
any parser assuming a separator breaks on that plan. A `Tâches :` line further
down the document is NOT read: otherwise a future plan citing a second roster
would widen the matching without anyone having wanted it.

RESIDUAL, named and not closed: a title stays free prose. The day a title cites
a context task — as the BODIES already cite `T-00000203` — matching by title
would reopen the widening this condition closes. Verified that no title cites a
foreign id today; **nothing pins it for tomorrow**.

**The report PRINTS THE MATCHED LINE for every task**, in `--check` as in
`--apply`. Without it the pilot reads "12 approved" without ever seeing what
the matching was made on — and a guard whose work is invisible is a guard one
stops reading. It is also the only thing that makes the residual above visible
to the eye.

VERDICT EXTRACTION RULE, named rather than guessed: the status is read in the
verdict entry's TITLE (`GO` / `GO_AVEC_RESERVES` / `NO_GO`, or the historic
`PASS` / `CONCERNS` / `FAIL` — SPECS.json keeps both, brief §1.2), the
fingerprint in its TEXT at the pattern `sha256=<hex>`, associated with the
plan's PATH. When SEVERAL verdicts cite the same plan — the normal case, a
critique iterates — **the most recent one prevails**. A plan whose last verdict
is `NO_GO` (or a historic `FAIL`) is not eligible, even if an older
`GO_AVEC_RESERVES`/`CONCERNS` exists.

Condition 4 is the load-bearing one: **a plan modified since its critique loses
its eligibility without anyone having to remember it.**

Condition 6 (draft) and condition 7 (night-delivered) are documented on their
functions. Condition 7 (T-00000847): a task the night DELIVERED carries a
`night-delivered: …` journal entry and is refused while it is not closed — the
night never closes (T-00000842), so a delivered task that falls back to
`pending` without its morning binôme (a manual `unblock`, an explicit exit
from `running`, a `reopen`) must not be replayed unattended.

Condition 8 (committed, T-01M5T4NRDNZ0ESYGFR3154RRJM), evaluated LAST: the plan
is in HEAD and identical to it, its disk BYTES equal to HEAD's blob or to its
checkout form (never git's index view alone) — a plan outside git, or edited
since HEAD, is refused with its remedy (`git add -- <plan>` then `git commit -- <plan>`). Last,
so that a `--check` names every other cause first.

Any condition that cannot be ESTABLISHED — unreadable journal, verdict not
found, plan absent — makes the task SKIPPED, never approved. A tool that cannot
conclude does not conclude green.

CONDITION 3, THE PAIR FORM NAMED (T-00000673). The journal also carries verdicts
titled in the PAIR form (`T-… itération N : paire …`): one trace per iteration
of the plan-critic pair, against ONE final verdict per approved plan. Condition 3
does not read them — it reads the FINAL verdict titled `plan-critic <VERDICT>`
whose text cites `plan=<path> sha256=<64 hex>`. The refusal was silent about it;
it is now NAMED, never widened: `condition_pair_form` REFUSES and names, it never
approves and never reads a status. Two rules, inside condition 3, between
condition 2 and `condition_verdict` (unchanged): (a) no plan-critic verdict cites
the plan and a pair is attached to the task → the pair is named with
`PAIR_FORM_EXPECTED`; (b) a pair MORE RECENT than the latest plan-critic verdict,
WHATEVER ITS STATUS → refused: the iteration resumed after the final, so the
final no longer describes the state critiqued; the exit (a newer final) is said
in the message. Both rules speak ONLY for a task the plan ENROLS
(`enrolling_line`): on a task it does not enrol, condition 5 is the true refusal
and a pair must not mask it. Pilot decision S-00003319 (option A): once T-00001049 mechanises
the go, the night still enters only on the FINAL verdict, which the mechanical
go writes after each favourable pair — `PAIR_FORM_EXPECTED` and rule (b) stand.
What the condition reads lives in ONE constant (`PAIR_FORM_EXPECTED`), the rule
in ONE function: a later task that widens condition 3 changes those two only.

NAMING IS PER TASK. A pair is attached to a TASK by its `task` key ALONE,
compared numerically (`_same_task`), NEVER by a path cited in its text — 11 live
pairs cite ANOTHER task's plan in prose; a verdict is attached to a PLAN. The
refusal is therefore carried by the task's line; the lot header stays per plan
and names no pair. ASYMMETRY, named: `/kickoff --defer-night` writes its
contract from the FINAL verdict it has just journaled and `/night` re-reads that
contract — neither runs this function, so neither names a pair. A contract
already written stays in force for `/night` (cited verdict): rule (b) turns
`--check` from ALREADY to SKIP and REVOKES NOTHING — whether a later pair should
revoke a contract is a pilot decision, carried by T-00001049.

RESIDUALS of the pair naming, named and NOT closed (measured 2026-10-01):

- R-a: titles per critic `plan-critic-<x>` (97 verdicts: 84
  `plan-critic-sonnet-max`, 13 `plan-critic-a`) stay refused under the generic
  message — `PLAN_CRITIC_TITLE` refuses them by construction (T-00000345).
- R-b: a plan-critic verdict attached to the task but citing no path (265 of
  572 plan-critic verdicts; 8 pending tasks) stays « aucun verdict plan-critic
  ne cite … »; rule (a) says « rattache a la tache » and never claims the pair
  is the only cause.
- R-c: rule (b) compares a TASK's pair with the PLAN's latest final. A plan
  that enrols several tasks therefore refuses an enrolled task whose own pair is
  newer than the plan's final — fail-closed, measured on 1 couple of 74
  (`T-00000658-plan.md` × T-00000665, approve → skip, its pair S-00002821 being
  newer; couples = the `.md` files under `docs/` and `plan/` × the pending tasks
  they enrol: a BOUNDED survey, not a closed one).
- R-d: the plural `paires` is not read (`\\bpaire\\b`): 2 live titles
  (S-00001622, S-00001624) stay refused under the generic message.

IDEMPOTENT, and identity compares on the EXTRACTED FIELDS, never on the byte.
Two contracts are "identical" when their `plan=` and their `sha256=` coincide;
the rest is prose. **Measured, not theoretical**: the 14 contracts already
written are phrased as sentences ("Approuve par le pilote le …") and carry NO
`approved=` field — a byte comparison would class all 14 as "different" and the
tool would append 14 duplicates. Contract present and identical => not
rewritten, the task is reported "already approved", not in error: replaying
after an interruption is safe. Contract present but DIFFERENT (the plan was
re-critiqued, its fingerprint changed) => the new contract is **APPENDED**,
never substituted: the journal is append-only, and rewriting a past approval
would erase the trace of what had been approved before. The night accepts a
task carrying **at least one** entry satisfying its conditions.

A BAD LOT IS SKIPPED AND NAMED, IT DOES NOT BLOCK THE OTHERS. Refusing the
whole block for one faulty lot would miss eleven healthy ones, and would push
the pilot to remove the faulty lot from the command line — that is, to work
around the control.

Exit codes: 0 when a report was produced (skipped tasks are a NORMAL, reported
outcome — see D4 above); 2 on an argument refusal (an empty `--lot`, a
malformed task id) or on a malformed state store.

`--delivered T-NNNNNNNN|T-<ULID> [...]` (T-00000847) is a separate, READ-ONLY mode that
exposes condition 7 alone — the one read `/night` delegates to this tool: rc 0
no night-delivered marker in force, 1 at least one in force (named with its
`S-`), 2 refusal / journal absent or unreadable (fail-closed: NOT eligible).
See `delivered_report`.

Writes go through the `specs.py` API, NEVER directly into `SPECS.json`: the
doctrine forbids it and the store has its own guards.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import specs  # noqa: E402  (same-directory sibling, after the path insertion)
import tasks  # noqa: E402

# The contract, to the letter — surveyed from `.claude/commands/kickoff.md:339`,
# never recopied from memory. The night re-reads {title, plan=, sha256=,
# verdict=} (`night.md:219-220`); kickoff produces those PLUS `approved=`. The
# relation is an INCLUSION, said rather than suffered: we write the kickoff
# form, the richer one.
CONTRACT_TITLE = "night-eligible: approved"
CONTRACT_KIND = "decision"

# `T-<ULID>` or `T-\d{8}` — the roster pattern (T-00001040 : the 26-symbol
# Crockford ULID FIRST, so a body opening with eight digits is never cut to a
# legacy id). NEVER a split on a separator (LOT-8A uses commas, the others `·`).
#
# EVERY pattern here is RIGHT-BOUNDED, and that boundary is the guard, not a
# detail of style. `findall` returns the longest match it can start, never the
# whole token: an unanchored `T-\d{8}` therefore TRUNCATES a 9-digit run and
# reports `T-000002099` as a match for `T-00000209` — the exact inverse of the
# invariant condition 5 claims, since it enrols a task the plan never names.
# The ULID branch carries its own bound (`(?![0-9A-Za-z])`): `T-<ULID>A` is not
# a ULID. Witnesses: test_night_approve_ulid.py.
# Same class of defect, closed for the same reason rather than for a known
# exploit: `sha256=` truncating a 65-hex run, and `.md` matching a path that
# continues past the extension.
#
# The `.md` boundary is TWO lookaheads, not one, because a single `.` plays two
# roles here. A TERMINAL dot is PUNCTUATION, not a continuation: `plan.md.` at
# the end of a sentence is a citation of `plan.md`, so the first lookahead drops
# `.` from the class it forbids and lets a bare final dot through. A dot that
# CONTINUES the token is still a different path: `plan.md.bak` must not read as
# `plan.md`, so the second lookahead re-refuses a `.` FOLLOWED by a path char.
# The residue is assumed and safe by direction: an ellipsis `plan.md...` stays
# refused (the tool declines, it never approves in error).
TASK_PATTERN = re.compile(r"T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d{8}(?!\d))")
TASK_ID_EXACT = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\Z")
ROSTER_HEAD = re.compile(r"^Tâches\s*:")
SHA256_FIELD = re.compile(r"sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")
PLAN_FIELD = re.compile(r"plan=(\S+)")
MD_PATH = re.compile(r"[A-Za-z0-9_./\\-]+\.md(?![A-Za-z0-9_/\\-])(?!\.[A-Za-z0-9_./\\-])")
VERDICT_ID = re.compile(r"S-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d+)")

# The report prints the matched LINE. It is bounded so a pathological plan
# cannot flood the console; the truncation is ANNOUNCED, never silent, and the
# SOURCE of the match (title / roster + line number) is always exact.
MATCHED_LINE_MAX = 300

PENDING = "pending"


class NightApproveError(Exception):
    """An argument refusal, or a state store that fails validation."""


# ---------------------------------------------------------------------------
# Paths and fingerprints
# ---------------------------------------------------------------------------

def normalize_plan_path(root: str | os.PathLike[str], raw: str) -> str:
    """Repo-relative, forward-slashed. Windows hands us backslashes and the
    pilot may paste an absolute path; the journal stores `docs/tasks/x.md`, so
    every comparison happens in that one shape."""
    text = str(raw).replace("\\", "/").strip()
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            text = candidate.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            text = candidate.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def plan_fingerprint(root: str | os.PathLike[str], plan_rel: str) -> str | None:
    """sha256 of the plan's BYTES, or None when the file cannot be read. Same
    computation the night runs, and the same one `kickoff` records."""
    path = Path(root) / plan_rel
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def plan_text(root: str | os.PathLike[str], plan_rel: str) -> str | None:
    path = Path(root) / plan_rel
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Roster — condition 5
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RosterLine:
    """One of the two — and only two — places a task may be enrolled from."""

    source: str  # "titre" | "roster"
    lineno: int
    text: str

    def label(self) -> str:
        shown = " ".join(self.text.split())
        if len(shown) > MATCHED_LINE_MAX:
            shown = shown[: MATCHED_LINE_MAX - 1] + "… (ligne tronquee a %d car.)" % MATCHED_LINE_MAX
        return f"{self.source} (ligne {self.lineno}) : {shown}"


def roster_lines(text: str) -> list[RosterLine]:
    """Line 1, and the FIRST `^Tâches\\s*:` line. Nothing else, ever."""
    lines = text.splitlines()
    found: list[RosterLine] = []
    if lines:
        found.append(RosterLine("titre", 1, lines[0]))
    for i, line in enumerate(lines, start=1):
        if ROSTER_HEAD.match(line):
            found.append(RosterLine("roster", i, line))
            break  # a second roster further down is NOT read
    return found


def enrolling_line(text: str, task_id: str) -> RosterLine | None:
    """The line that ENROLS `task_id`, or None. Matching is by PATTERN over the
    two admitted lines — never a substring search over the whole file, which
    this repo's own plans defeat (see the module docstring)."""
    for line in roster_lines(text):
        if task_id in TASK_PATTERN.findall(line.text):
            return line
    return None


# ---------------------------------------------------------------------------
# Journal reading — verdicts and existing contracts
# ---------------------------------------------------------------------------

def cited_plan_paths(root: str | os.PathLike[str], text: str) -> set[str]:
    return {normalize_plan_path(root, m) for m in MD_PATH.findall(text or "")}


# Les DEUX vocabulaires — les verdicts historiques de SPECS.json ne sont jamais
# réécrits (brief §1.2) et doivent rester lisibles. Ordre LE PLUS CONSERVATEUR
# D'ABORD sur les deux : un titre portant NO_GO et GO lit NO_GO — l'ordre le
# garantit en plus du \b (« _ » est un caractère de mot, donc \bGO\b ne matche
# ni NO_GO ni GO_AVEC_RESERVES ; on ne s'appuie pas sur cette seule finesse,
# L-00000143 : décision sur structure ET ordre, jamais sur un fragment).
# C2 it.1 — LE JETON CONSERVATEUR SE MATCHE EN VARIANTES DE SÉPARATEUR AVANT
# TOUTE SONDE GO : « NO-GO » et « NO GO » sont de la prose ordinaire dans un
# dépôt bilingue, et un \bGO\b nu les lisait GO (fail-open vers l'éligibilité
# nuit — pire que le None fail-closed d'aujourd'hui).
# HIGH-1 (T-00000323) — L'ÉNUMÉRATION DE SÉPARATEURS ÉTAIT UN FAIL-OPEN
# D'AUTORISATION. `[\s_-]*` ÉNUMÉRAIT trois séparateurs ASCII ; tout autre
# séparateur faisait retomber le titre sur la sonde `\bGO\b` et rendait ÉLIGIBLE
# À LA NUIT un plan REFUSÉ par le plan-critic. Mesuré `decision='approve'` sur
# sept orthographes : NO—GO (U+2014), NO–GO (U+2013), NO‑GO (U+2011), NO/GO,
# NO.GO, NON GO, NON-GO. On ne rallonge donc PAS la liste (L-00000187 : là où
# l'on ne peut pas énumérer, on BORNE) : la classe est fermée sur la propriété
# « ce qui n'est ni lettre ni chiffre », bornée à 3 caractères pour que la sonde
# reste locale, et le N final de NON est optionnel pour couvrir le français.
# 11/11 orthographes de refus refusées, 0 régression sur les 5 témoins éligibles.
NO_GO_PATTERN = r"\bNON?[^A-Z0-9]{0,3}GO\b"  # NO_GO, NO-GO, NON GO, NO—GO, NOGO…
VERDICT_PROBES = (
    ("NO_GO", NO_GO_PATTERN),
    ("FAIL", r"\bFAIL\b"),
    ("GO_AVEC_RESERVES", r"\bGO[\s_-]*AVEC[\s_-]*R[EÉ]SERVES\b"),  # C5 it.2: « RÉSERVES » accentué survit à .upper()
    ("CONCERNS", r"\bCONCERNS\b"),
    ("GO", r"\bGO\b"),
    ("PASS", r"\bPASS\b"),
)
ELIGIBLE_STATUSES = ("GO", "GO_AVEC_RESERVES", "PASS", "CONCERNS")


# THE VERDICT IS READ FROM AN ANCHORED GRAMMAR, NOT FOUND ANYWHERE IN THE TITLE
# (T-00000345). `re.search` over the whole title is a FAIL-OPEN of authorisation:
# a title whose PROSE carries a token in a NEGATIVE sentence read permissive.
# Measured: `plan-critic : refus, pas de GO` returned GO — a REFUSED plan, made
# eligible for unattended overnight execution by the word it used to refuse.
#
# THE GRAMMAR IS DERIVED FROM THE REAL CORPUS, never invented: prefix, optional
# separator, OPTIONAL ITERATION MARKER, then the verdict token IMMEDIATELY. The
# iteration marker is not decoration — `plan-critic it.2: CONCERNS` is a real,
# frequent shape, and a first version of this grammar that omitted it sent FIVE
# genuine CONCERNS titles to None. That is what measuring before landing is for.
#
# MEASURED IMPACT on the 180 real plan-critic titles in this repo's SPECS.json:
# 7 labels change, **ZERO toward refusal**, and all 7 are CORRECTIONS toward the
# true status — e.g. S-00000008 read FAIL because the word appeared later in its
# prose, and is really CONCERNS; S-00000655 read NO_GO and is really
# GO_AVEC_RESERVES. The "5 broken historical titles" the earlier arbitration
# feared do not exist: they would be REPAIRED.
#
# OUTSIDE THE GRAMMAR IT RETURNS None, WHICH IS FAIL-CLOSED: None is not in
# ELIGIBLE_STATUSES, so an unreadable title makes the task INELIGIBLE rather than
# approved. A verdict nobody can parse must never be a yes.
ANCHORED_VERDICT = re.compile(
    r"^\s*PLAN-CRITIC\s*[:\-–—]?\s*"
    r"(?:(?:IT\.?|ITERATION|ITER\.?)\s*\d+(?:\s*/\s*\d+)?|\d+\s*/\s*\d+)?"
    r"\s*[:\-–—]?\s*"
    r"(?P<verdict>"
    r"NON?[^A-Z0-9]{0,3}GO|FAIL|GO[\s_-]*AVEC[\s_-]*R[EÉ]SERVES|CONCERNS|GO|PASS"
    r")(?![\w-])"
)


def verdict_status(title: str) -> str | None:
    """Read in the TITLE, both vocabularies, most-conservative FIRST.

    NFC FIRST (T-00000323, advisory) : « GO AVEC RÉSERVES » saisi en forme
    DÉCOMPOSÉE (E + U+0301) ne matchait pas `R[EÉ]SERVES` et retombait sur la
    sonde `\\bGO\\b` — même statut d'éligibilité, mais une ÉTIQUETTE fausse dans
    le rapport lu par le pilote. On normalise APRÈS `.upper()` : la casse haute
    d'un caractère décomposé reste décomposée."""
    upper = unicodedata.normalize("NFC", (title or "").upper())
    m = ANCHORED_VERDICT.match(upper)
    if not m:
        return None
    token = m.group("verdict")
    for status, pattern in VERDICT_PROBES:
        if re.fullmatch(pattern.replace(r"", ""), token):
            return status
    return None  # unreachable: the alternation IS the probe list


def verdict_fingerprint(text: str) -> str | None:
    """The fingerprint in the TEXT. Two DIFFERENT sha256 in one verdict makes
    the condition unestablishable, so it returns None — never a guess."""
    found = {m.lower() for m in SHA256_FIELD.findall(text or "")}
    if len(found) != 1:
        return None
    return found.pop()


# HIGH-2 (T-00000323) — LA SONDE EST ANCRÉE SUR L'AGENT QUI FAIT AUTORITÉ.
# `kind=verdict` ne dit RIEN de l'auteur : le gate sécurité et `design-review`
# écrivent des verdicts dans le même journal. C'était inoffensif tant que le
# vocabulaire lu était PASS/CONCERNS/FAIL ; le nouveau vocabulaire y ajoute
# `GO`, QUI EST LE MOT DE `design-review` ET DU GATE SÉCURITÉ. Mesuré :
# `plan-critic NO_GO` puis `design-review GO` citant le même plan rendait
# `decision='approve'` — un plan refusé, éligible à l'exécution autonome.
# Sur ce dépôt, 257 entrées `kind=verdict` dont 170 seulement portent un titre
# de plan-critic : 87 verdicts d'autres agents pouvaient devenir « le dernier
# verdict du plan ».
# La comparaison est ANCRÉE et STRUCTURELLE, jamais un fragment trouvé quelque
# part (L-00000143), et la frontière est `(?![\w-])` plutôt que `\b` : le nom
# contient déjà un tiret, donc `\b` laisserait passer l'EXTENSION DE PRÉFIXE
# `plan-critic-<autre>` — exactement le « ce qui ressemble est admis » de la
# leçon. Condition 3 disait déjà « aucun verdict plan-critic » : le code dit
# enfin ce que la doc promettait.
PLAN_CRITIC_TITLE = re.compile(r"^\s*plan-critic(?![\w-])", re.IGNORECASE)


def is_plan_critic_verdict(entry: dict[str, Any]) -> bool:
    """The entry is a verdict AUTHORED by `plan-critic` — read on the title,
    anchored at its start. A verdict from another agent is not an authority on
    night eligibility, however it spells its own verdict."""
    return bool(PLAN_CRITIC_TITLE.match(entry.get("title") or ""))


def latest_verdict_for_plan(
    root: str | os.PathLike[str], entries: list[dict[str, Any]], plan_rel: str
) -> dict[str, Any] | None:
    """The MOST RECENT `plan-critic` verdict citing this plan. A critique
    iterates, so several verdicts cite one plan; the newest prevails, which is
    what makes a `NO_GO` after a `GO_AVEC_RESERVES` (or a historic `FAIL` after
    a `CONCERNS`) actually disqualify."""
    matches = [
        e
        for e in entries
        if e.get("kind") == "verdict"
        and is_plan_critic_verdict(e)
        and plan_rel in cited_plan_paths(root, e.get("text", ""))
    ]
    if not matches:
        return None
    # `specs.sort_key`, never `numeric_id` (S-00004585) : a `S-<ULID>` is AFTER
    # every legacy id, and `numeric_id` would raise on a body ending in a letter.
    return max(matches, key=lambda e: specs.sort_key(e["id"]))


def contract_identity(root: str | os.PathLike[str], text: str) -> tuple[str, str] | None:
    """`(plan, sha256)` EXTRACTED from a contract's text — never the byte. The
    14 contracts already in this store are prose and carry no `approved=`
    field; comparing bytes would class every one of them as different."""
    plan = PLAN_FIELD.search(text or "")
    sha = SHA256_FIELD.search(text or "")
    if not plan or not sha:
        return None
    return (normalize_plan_path(root, plan.group(1)), sha.group(1).lower())


def existing_contracts(entries: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    return [
        e
        for e in entries
        if e.get("task") == task_id
        and e.get("kind") == CONTRACT_KIND
        and (e.get("title") or "").strip() == CONTRACT_TITLE
    ]


def contract_text(plan_rel: str, sha: str, verdict_id: str, approved: str) -> str:
    """The canonical form, `kickoff.md:339`. `approved=` IS part of it — a
    one-field divergence makes the whole device mute, since the night re-reads
    this format and does not guess it."""
    return f"plan={plan_rel} sha256={sha} verdict={verdict_id} approved={approved}"


# ---------------------------------------------------------------------------
# The eight conditions, each its own function so a mutation can neutralise
# exactly one and no more (non-vacuity proof, plan step 3). The sixth was added
# on 2026-09-12: the draft check lived only in `plan_pool.py`, which PREPARES
# and does not ADMIT, so a `STATUS: IN_PROGRESS` plan carrying a `GO` verdict
# came out APPROVE here — measured, not feared.
# ---------------------------------------------------------------------------

def condition_state(task_id: str, board_states: dict[str, str]) -> str | None:
    """Condition 1 — the task is `pending`."""
    state = board_states.get(task_id)
    if state is None:
        return "condition 1 : tache inconnue du board (attendu : pending)"
    if state != PENDING:
        return f"condition 1 : tache {state} (attendu : pending)"
    return None


def condition_plan_exists(fingerprint: str | None, plan_rel: str) -> str | None:
    """Condition 2 — the plan file exists (and could be read)."""
    if fingerprint is None:
        return f"condition 2 : plan introuvable ou illisible ({plan_rel})"
    return None


def condition_verdict(verdict: dict[str, Any] | None, plan_rel: str) -> str | None:
    """Condition 3 — a `GO`/`GO_AVEC_RESERVES` (or historic `PASS`/`CONCERNS`) plan-critic verdict cites this plan."""
    if verdict is None:
        return f"condition 3 : aucun verdict plan-critic ne cite {plan_rel}"
    status = verdict_status(verdict.get("title", ""))
    if status is None:
        return f"condition 3 : verdict {_vid(verdict)} sans statut lisible (ni GO, ni GO_AVEC_RESERVES, ni NO_GO, ni PASS, ni CONCERNS, ni FAIL)"
    if status not in ELIGIBLE_STATUSES:
        return f"condition 3 : dernier verdict {_vid(verdict)} = {status}"
    return None


def condition_fingerprint(
    verdict: dict[str, Any] | None, fingerprint: str | None
) -> str | None:
    """Condition 4 — the RECOMPUTED fingerprint is the recorded one. This is
    the load-bearing condition: a plan edited since its critique loses its
    eligibility without anyone having to remember the edit."""
    if verdict is None or fingerprint is None:
        return "condition 4 : empreinte non etablissable (verdict ou plan absent)"
    recorded = verdict_fingerprint(verdict.get("text", ""))
    if recorded is None:
        return f"condition 4 : verdict {_vid(verdict)} ne porte pas une empreinte sha256 unique"
    if recorded != fingerprint:
        return (
            f"condition 4 : plan modifie depuis la critique "
            f"(verdict {recorded[:12]}…, recalcule {fingerprint[:12]}…)"
        )
    return None


#: Les marqueurs que `/planning` pose sur un plan TANT QU'IL N'EST PAS FINI.
#: Ils sont ecrits par le planner des sa premiere sortie et RETIRES quand le
#: verdict final est rendu.
DRAFT_MARKERS = frozenset({"IN_PROGRESS", "CRITIC_REJECTED"})

_STATUS_ORNEMENTS = "*_# -\t"


def plan_draft_marker(text: str | None) -> str | None:
    """Le marqueur de brouillon porte par le plan, ou `None`.

    ANALYSE TOLERANTE, ET C'EST DELIBERE. Ce depot ecrit ses plans a la main et
    en francais : `**STATUS:** IN_PROGRESS`, une indentation, une espace avant
    les deux-points ou un suffixe de revision sont tous plausibles. Un
    `startswith("STATUS:")` strict les laisserait TOUS passer, et un marqueur
    manque ne se voit pas — il se lit « plan fini ».

    TOUTE ligne `STATUS` est examinee, pas seulement la premiere : un plan amende
    EMPILE ses statuts, et ne lire que le plus ancien reviendrait a juger une
    revision qui n'est plus la bonne. Un seul marqueur suffit a refuser.
    """
    if not text:
        return None
    for ligne in text.splitlines():
        nu = ligne.strip().lstrip(_STATUS_ORNEMENTS).strip()
        if not nu.upper().startswith("STATUS"):
            continue
        _, _, valeur = nu.partition(":")
        mots = valeur.strip().strip(_STATUS_ORNEMENTS).upper().split()
        if mots and mots[0] in DRAFT_MARKERS:
            return mots[0]
    return None


def condition_draft(text: str | None, plan_rel: str) -> str | None:
    """Condition 6 — le plan n'est pas un BROUILLON de `/planning`.

    POURQUOI ELLE EXISTE, ET POURQUOI ICI. `core-scripts/plan_pool.py` refuse
    deja les brouillons, mais AGENTS.md dit lui-meme qu'il « n'est PAS
    autoritaire sur `/night` » : il PREPARE, il n'ADMET pas. La surface qui admet
    est CE fichier, et elle ignorait les marqueurs — mesure du 2026-09-12, un
    plan `STATUS: IN_PROGRESS` accompagne d'un verdict `GO` ressortait APPROVE.

    LA FENETRE EST REELLE, pas theorique : `plan-critic` rend `GO`, le verdict
    est trace, et le planner est interrompu AVANT de reecrire le plan sans son
    marqueur. Le fichier reste `IN_PROGRESS`, son empreinte concorde donc avec
    celle du verdict — la condition 4 est satisfaite — et la nuit part travailler
    sur un plan que le critic n'a pas fini de juger. C'est le seul mecanisme du
    depot qui tourne sans surveillance.

    Elle vient APRES la condition 5 : les cinq premieres etablissent qu'il y a un
    plan, un verdict et un enrolement ; celle-ci juge ce que le plan DIT de
    lui-meme, ce qui n'a de sens qu'une fois le reste etabli.
    """
    if text is None:
        return None  # deja dit par la condition 2, qu'on ne double pas
    marqueur = plan_draft_marker(text)
    if marqueur is not None:
        return (f"condition 6 : {plan_rel} porte STATUS: {marqueur} — brouillon "
                "/planning, le verdict final n'a pas encore ete rendu sur CETTE revision")
    return None


def condition_roster(text: str | None, task_id: str) -> str | None:
    """Condition 5 — the plan ENROLS the task, in its title or its roster line.
    Never anywhere in the bytes: this repo's own plans cite ids in their BODIES
    precisely to say they do NOT treat them."""
    if text is None:
        return "condition 5 : plan illisible, enrolement non etablissable"
    if enrolling_line(text, task_id) is None:
        places = ", ".join(f"{r.source} l.{r.lineno}" for r in roster_lines(text)) or "aucune"
        return (
            f"condition 5 : {task_id} n'est enrole ni par le titre ni par la ligne roster "
            f"(examine : {places})"
        )
    return None


#: The trace the night journals on a task it DELIVERED, right BEFORE its
#: `tasks.py block … --note "NUIT : attente binôme du matin — …"` (night.md,
#: § « La nuit NE CLÔT PAS »). Exact form the night writes:
#:     specs.py add --task T-NNN --kind decision "night-delivered: attente binome du matin" --text …
NIGHT_DELIVERED_TITLE = "night-delivered: attente binome du matin"
#: The PILOT's clearing entry — never a gesture of the night. Needed after a
#: `reopen` (done → pending) or an `unblock` (blocked → pending): the morning
#: `done` already takes the task out of play through condition 1.
NIGHT_DELIVERED_CLEARED_TITLE = "night-delivered: cleared"
NIGHT_DELIVERED_KIND = "decision"

# The PROBE is anchored at the start of the title and right-bounded by
# `(?![\w-])`, like `PLAN_CRITIC_TITLE`: `night-delivered-lite` is not the
# marker. It is deliberately WIDER than the exact title the night writes, and
# kind-agnostic: a marker spelled with a different tail or journaled under
# another kind still refuses (fail-closed). The CLEARING, by contrast, is read
# NARROWLY — exact title byte for byte, kind `decision` — since a lax clearing
# would be the fail-open direction.
NIGHT_DELIVERED_PROBE = re.compile(r"^\s*night-delivered(?![\w-])", re.IGNORECASE)


def _is_night_delivered_clearing(entry: dict[str, Any]) -> bool:
    """EXACT title, no casefold, no whitespace folding: the clearing is the
    fail-open side, so only the one form the pilot's documented gesture writes
    counts (T4, critic-opus)."""
    return (
        entry.get("kind") == NIGHT_DELIVERED_KIND
        and entry.get("title") == NIGHT_DELIVERED_CLEARED_TITLE
    )


#: A task id as `_same_task` admits it: `T-<ULID>` FIRST, then the legacy
#: `T-<digits>`, anchored at both ends (T-00001040).
_TASK_ID_FORM = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d+)\Z")


def _same_task(recorded: Any, task_id: str) -> bool:
    """Same task by IDENTITY, never by raw string (T1, critic-opus): `tasks.py` READ
    verbs accept the short form `T-848` for `T-00000848`, and `specs.py add` records
    the id AS TYPED — a string comparison made such a marker invisible. Compared
    through `specs.identity_key` (T-00001040) — the SAMENESS question, never the
    ORDER one that `specs.sort_key` answers: two legacy ids by NUMERIC value, two
    `T-<ULID>` by their exact body, and a ULID against a legacy id NEVER — even
    when the ULID body ends with the legacy digits (MIXED is false). The `T-`
    prefix is required on both sides; anything malformed is not a match (a
    `SpecsError` reads False)."""
    if not isinstance(recorded, str):
        return False
    if not (_TASK_ID_FORM.match(recorded) and _TASK_ID_FORM.match(task_id or "")):
        return False
    try:
        return specs.identity_key(recorded) == specs.identity_key(task_id)
    except specs.SpecsError:
        return False


def active_night_delivered(
    entries: list[dict[str, Any]], task_id: str
) -> dict[str, Any] | None:
    """The night-delivered marker IN FORCE on `task_id`, or None.

    Among THIS task's `night-delivered…` entries the MOST RECENT prevails (same
    idiom as `latest_verdict_for_plan`): a marker is in force unless a later
    pilot clearing supersedes it, and a delivery after a clearing re-arms it.
    Another task's marker is never read — the filter is on `task` first, by
    IDENTITY (`T-848` and `T-00000848` are one task, a `T-<ULID>` is only itself),
    and the order is `specs.sort_key` (a `S-<ULID>` comes after every legacy id)."""
    family = [
        e
        for e in entries
        if _same_task(e.get("task"), task_id)
        and NIGHT_DELIVERED_PROBE.match(e.get("title") or "")
    ]
    if not family:
        return None
    latest = max(family, key=lambda e: specs.sort_key(e["id"]))
    return None if _is_night_delivered_clearing(latest) else latest


def condition_night_delivered(entries: list[dict[str, Any]], task_id: str) -> str | None:
    """Condition 7 — the night has not ALREADY DELIVERED this task, awaiting its
    morning binôme (T-00000847).

    WHY. Since T-00000842 the night never closes: a delivered task ends
    `blocked`, and condition 1 keeps it out while it stays so. But `blocked` is
    a STATE, and a state moves: an `unblock`, an explicit `set_state` to
    `pending`, a `reopen` — and the task
    is `pending` again, contract and sha256 intact, so conditions 1-6 hold and
    the next night would REPLAY work already delivered, without a binôme. The
    journal is append-only and survives every transition: the trace does not.

    ERASURE. The morning `done` suffices in the nominal route — condition 1
    refuses a `done` task before this one is read, so a marker left in the
    journal of a closed task costs nothing. A `reopen` or an `unblock` brings it
    into play; the pilot then journals `night-delivered: cleared` if he really wants
    the night to take the task again.

    Evaluated LAST, after 1-6: the refusal names the first unmet condition, so
    a pending task whose plan also changed reads `condition 4`."""
    marker = active_night_delivered(entries, task_id)
    if marker is None:
        return None
    return (
        f"condition 7 : {task_id} deja livree par la nuit ({_titre_affichable(marker['id'])} "
        f"« {' '.join(_titre_affichable(marker.get('title') or '').split())} ») et non close — le "
        "binome du matin n'a pas eu lieu ; sortie : `done` du matin, ou, apres un "
        f"`reopen` ou un `unblock`, une entree decision « {NIGHT_DELIVERED_CLEARED_TITLE} » du pilote"
    )


#: Environment of the git children of condition 8. Every `GIT_*` by which git
#: lets itself be pointed at ANOTHER repository is removed — `GIT_DIR`,
#: `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_COMMON_DIR`,
#: `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CONFIG_PARAMETERS`… (a `pre-push`
#: exports `GIT_DIR`, measured: the plan of ANOTHER repo then reads committed).
#: The three configuration LOCATIONS are KEPT, after the kit precedent
#: `GIT_CONSERVE` of `.agents/bin/porte_adoptant.py:190`: the benches set them.
GIT_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
GIT_TIMEOUT_S = 30

COMMIT_REMEDY = "remede : `git add -- {p}` puis `git commit -m \"docs(tasks): plan {t}\" -- {p}`"


def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in GIT_CONSERVE}


def _git_rc(root: str | os.PathLike[str], *args: str) -> int | None:
    """The rc of a READ-ONLY git call under `root`, or None when git cannot be
    run at all (absent, timeout). fsmonitor off, as `porte_adoptant.git`."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "--literal-pathspecs", "-c", "core.fsmonitor=false", *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=_git_env(), timeout=GIT_TIMEOUT_S, check=False,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return None


def _git_bytes(root: str | os.PathLike[str], *args: str) -> bytes | None:
    """The stdout BYTES of a READ-ONLY git call under `root`, or None when git
    cannot be run or answers non-zero — the caller reads None as « non verifiable »."""
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=_git_env(), timeout=GIT_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def condition_committed(root: str | os.PathLike[str], plan_rel: str, task_id: str) -> str | None:
    """Condition 8 — the plan is COMMITTED and identical to HEAD au sens de
    l'index git (T-01M5T4NRDNZ0ESYGFR3154RRJM).

    WHY. The night re-reads the plan it executes; a plan outside git (69 measured
    untracked under `docs/tasks/`) or edited since HEAD is a contract on bytes no
    commit holds. Four legs: `rev-parse --verify -q HEAD` (git readable, HEAD
    born), `cat-file -e HEAD:./<plan>` (in HEAD; `./` resolves against `root`, a
    sub-directory included; an IGNORED plan gets the `git add -f --` remedy, read by
    `ls-files --others --ignored --exclude-standard --error-unmatch`, because
    `check-ignore` refuses `--literal-pathspecs`, rc 128 measured), `diff --quiet
    HEAD -- <plan>` (identical to HEAD; CRLF-normalised by git, never a raw blob
    sha), `diff --cached --quiet HEAD -- <plan>` (the index too: the `MM` state,
    worktree back to HEAD over a staged revision, which the night's own
    `git status --porcelain` reading refuses). An indexed but uncommitted plan
    reads « absent de HEAD », never « modifie ». Then the BYTES: the disk bytes must
    equal `cat-file blob HEAD:./<plan>` (raw) OR `cat-file --filters HEAD:./<plan>`
    (the form a checkout writes: CRLF under autocrlf, `$Id: <sha> $` under `ident`),
    because `diff HEAD` goes through the index and the clean filters — measured, an
    `ident` collapse (`$Id: <anything> $` -> `$Id$`), `--assume-unchanged` and
    `--skip-worktree` all read 0 there while the disk bytes are in no commit. A git
    call that cannot run, on any leg, reads « non verifiable », never « non suivi ».

    A SYMLINK plan is refused before git is asked: committed (mode 120000), HEAD
    holds the link text while `plan_fingerprint` reads the TARGET's bytes, which no
    commit holds — measured, `cat-file -e` 0 and `diff --quiet` 0 on a link to an
    untracked file outside the repo, its content changed.

    BOUNDS, named: (a) the byte leg accepts the SMUDGED form, so a
    `filter.<x>.smudge` (or `clean`, during `diff HEAD`) declared in the repo's own
    `.git/config` RUNS and decides what « HEAD » means — it requires control of
    `.git/config`, the trust level of the hooks, so no `-c filter…` override is
    added here; (b) `.gitattributes` is read from the worktree, so an uncommitted
    attribute changes the checkout form compared — through git's built-in
    transforms only (`eol`, `ident`, `working-tree-encoding`), each a rendering of
    HEAD's blob; an arbitrary rewrite needs a filter driver, bound (a).

    Evaluated LAST, after 1-7: a `--check` names every other cause first, and a
    plan skipped for this sole reason is approvable once committed."""
    remedy = COMMIT_REMEDY.format(p=plan_rel, t=task_id)
    rc = _git_rc(root, "rev-parse", "--verify", "-q", "HEAD")
    if rc is None:
        return (f"condition 8 : git non lance (absent du PATH ou delai de {GIT_TIMEOUT_S} s depasse) — "
                f"{plan_rel} non verifiable ; {remedy}")
    if rc != 0:
        return f"condition 8 : git illisible sous la racine (HEAD non etabli) — {plan_rel} non verifiable ; {remedy}"
    if os.path.islink(Path(root) / plan_rel):
        return (f"condition 8 : {plan_rel} est un lien symbolique — HEAD n'en tient que la cible "
                "nommee, jamais les octets lus ; remplacer le lien par le fichier, puis "
                f"{remedy.removeprefix('remede : ')}")
    rc = _git_rc(root, "cat-file", "-e", f"HEAD:./{plan_rel}")
    if rc is None:
        return (f"condition 8 : git non lance (cat-file, absent du PATH ou delai de {GIT_TIMEOUT_S} s depasse) — "
                f"{plan_rel} non verifiable ; {remedy}")
    if rc != 0:
        if _git_rc(root, "ls-files", "--others", "--ignored", "--exclude-standard",
                   "--error-unmatch", "--", plan_rel) == 0:
            return (f"condition 8 : {plan_rel} absent de HEAD et ignore par git (.gitignore) ; "
                    f"{remedy.replace('git add --', 'git add -f --', 1)}")
        return f"condition 8 : {plan_rel} absent de HEAD (non suivi par git) ; {remedy}"
    rc = _git_rc(root, "diff", "--quiet", "HEAD", "--", plan_rel)
    if rc == 1:
        return f"condition 8 : {plan_rel} modifie depuis HEAD ; {remedy}"
    if rc != 0:
        return f"condition 8 : git illisible (diff rc={rc}) — {plan_rel} non verifiable ; {remedy}"
    rc = _git_rc(root, "diff", "--cached", "--quiet", "HEAD", "--", plan_rel)
    if rc == 1:
        return (f"condition 8 : {plan_rel} indexe differemment de HEAD (etat MM, refuse par la nuit) ; "
                f"remede : `git restore --staged -- {plan_rel}`")
    if rc != 0:
        return f"condition 8 : git illisible (diff --cached rc={rc}) — {plan_rel} non verifiable ; {remedy}"
    blob = _git_bytes(root, "cat-file", "blob", f"HEAD:./{plan_rel}")
    smudged = _git_bytes(root, "cat-file", "--filters", f"HEAD:./{plan_rel}")
    if blob is None or smudged is None:
        return (f"condition 8 : git illisible ou non lance (cat-file blob/--filters) — "
                f"{plan_rel} non verifiable ; {remedy}")
    try:
        disk = (Path(root) / plan_rel).read_bytes()
    except OSError as exc:
        return f"condition 8 : {plan_rel} illisible ({exc.__class__.__name__}) — non verifiable ; {remedy}"
    if disk not in (blob, smudged):
        return (f"condition 8 : {plan_rel} : octets disque differents de HEAD (ni le blob ni sa forme "
                "extraite ; index marque assume-unchanged/skip-worktree, ou filtre clean/ident) ; "
                f"remede : `git update-index --no-assume-unchanged --no-skip-worktree -- {plan_rel}` "
                f"puis `git checkout -- {plan_rel}` (ou, si le disque est le bon plan, le commiter)")
    return None


# ---------------------------------------------------------------------------
# Condition 3, THE PAIR FORM NAMED (T-00000673) — an EXPLANATION, never an
# authority (module docstring). Outside the grammar parity:
# `test_parite_grammaire_night_approve` reads five constants BY NAME and none of
# them is touched here. `core-scripts/plan_pool.py` carries a COPY of `PAIR_VERDICT_TITLE`
# (`PAIRE_RE`, parity pinned by `test_night_approve.py`; NO copy of `ITERATION_VERDICT_TITLE`,
# S-00003871) and a COPY of `_titre_affichable`, each copy pinned by its own witness there.
# ---------------------------------------------------------------------------
PAIR_VERDICT_TITLE = re.compile(r"\bpaire\b")
ITERATION_VERDICT_TITLE = re.compile(r"\bit[ée]ration\s+\d+\s*/\s*\d+\s*:", re.IGNORECASE)

PAIR_FORM_EXPECTED = (
    "cette condition lit un verdict titre « plan-critic <VERDICT> » dont le texte cite "
    "plan=<chemin> sha256=<64 hex> (kickoff.md) ; la forme paire n'y est pas lue"
)

_PAIR_TITLE_SHOWN = 80


def _titre_affichable(t: str) -> str:
    """A FREE journal field made printable BEFORE it is quoted in a reason: every
    non-printable character — ESC `\\x1b`, the C1 CSI `\\x9b`, a newline — becomes
    a space, BEFORE the `split()` and the cut (S-00003335). A journal title is typed
    by any agent; the reason is printed on a terminal. Applied to every FREE journal
    title this module prints — the pair (condition 3), the night-delivered marker
    (condition 7 and `--delivered`) — and to the marker's entry id at those two
    sites (T-00001057: `specs.load` checks only the id's numeric SUFFIX, so a
    hand-edited store can lodge an ESC or a newline in it). Survey BOUNDED, NOT
    closed: at least the entry id elsewhere (the pair's, a verdict's), the plan's
    roster line, the `SpecsError` and `tasks.load` messages relayed on stderr, and
    `--root` / `CLAUDE_PROJECT_DIR` are still printed raw.
    `core-scripts/plan_pool.py` carries a COPY (it imports nothing from `.agents/bin`)."""
    return "".join(c if c.isprintable() else " " for c in t)


def _vid(entry: dict[str, Any]) -> str:
    """An entry's id made printable BEFORE it is quoted in a reason (T-00001057
    residual: `specs.load` checks only the id's numeric SUFFIX, so a hand-edited
    store can lodge an ESC or a newline in a verdict's or a pair's id)."""
    return _titre_affichable(str(entry.get("id", "?")))


def latest_pair_verdict_for_task(
    entries: list[dict[str, Any]], task_id: str
) -> dict[str, Any] | None:
    """The MOST RECENT `kind=verdict` journaled ON THIS TASK whose title is not `plan-critic`
    (`is_plan_critic_verdict`) and carries `\\bpaire\\b` or the single critic's `itération N/M :`.

    ASSOCIATED BY THE TASK KEY ALONE, compared by IDENTITY by `_same_task` (a legacy
    id by numeric value, a `T-<ULID>` by its exact body), NEVER
    by a path cited in the text: 11 live pair verdicts cite ANOTHER task's plan
    file in prose, and a path leg would let them mask a plan they do not concern.
    `kind=verdict` only: 40 live plan/decision/delta entries carry the word too."""
    matches = [
        e
        for e in entries
        if e.get("kind") == "verdict"
        and not is_plan_critic_verdict(e)
        and (PAIR_VERDICT_TITLE.search(e.get("title") or "") or ITERATION_VERDICT_TITLE.search(e.get("title") or ""))
        and _same_task(e.get("task"), task_id)
    ]
    if not matches:
        return None
    return max(matches, key=lambda e: specs.sort_key(e["id"]))


def condition_pair_form(
    pair: dict[str, Any] | None, verdict: dict[str, Any] | None, plan_rel: str
) -> str | None:
    """Condition 3, the PAIR FORM named. It REFUSES, it never approves, and it
    never reads a status — a pair title is free prose (« paire FAVORABLE --
    GO_AVEC_RESERVES des DEUX »): reading it to authorise is the class T-00000345
    closed, reading it to refuse is the same bet.

    (a) no plan-critic verdict cites the plan, a pair is attached to the task;
    (b) the pair is MORE RECENT (`specs.sort_key` of the S-id : a `S-<ULID>` comes
    after every legacy id) than the latest plan-critic verdict."""
    if pair is None:
        return None
    title = " ".join(_titre_affichable(pair.get("title") or "").split())[:_PAIR_TITLE_SHOWN]
    if verdict is None:
        return (
            f"condition 3 : aucun verdict plan-critic ne cite {plan_rel} — {_vid(pair)} "
            f"(rattache a la tache, « {title} ») est en forme PAIRE ; {PAIR_FORM_EXPECTED}"
        )
    if specs.sort_key(pair["id"]) > specs.sort_key(verdict["id"]):
        return (
            f"condition 3 : la paire {_vid(pair)} (« {title} ») est plus recente que le dernier "
            f"verdict plan-critic {_vid(verdict)} ; sortie : un verdict FINAL « plan-critic <VERDICT> » "
            f"plus recent (plan=<chemin> sha256=<64 hex>)"
        )
    return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

APPROVE = "approve"
ALREADY = "already"
SKIP = "skip"


@dataclass
class TaskOutcome:
    task: str
    decision: str
    reason: str = ""
    matched: RosterLine | None = None
    contract: str = ""
    written_id: str = ""


@dataclass
class LotOutcome:
    plan: str
    outcomes: list[TaskOutcome] = field(default_factory=list)
    plan_sha: str | None = None
    verdict_id: str = ""
    verdict_status: str = ""
    duplicates: list[str] = field(default_factory=list)


@dataclass
class Lot:
    plan: str
    tasks: list[str]


def evaluate_lot(
    root: str | os.PathLike[str],
    lot: Lot,
    board_states: dict[str, str],
    entries: list[dict[str, Any]],
    approved_on: str,
) -> LotOutcome:
    plan_rel = normalize_plan_path(root, lot.plan)
    fingerprint = plan_fingerprint(root, plan_rel)
    text = plan_text(root, plan_rel)
    verdict = latest_verdict_for_plan(root, entries, plan_rel)

    out = LotOutcome(plan=plan_rel, plan_sha=fingerprint)
    if verdict is not None:
        out.verdict_id = verdict["id"]
        out.verdict_status = verdict_status(verdict.get("title", "")) or "?"

    seen: set[str] = set()
    for task_id in lot.tasks:
        if task_id in seen:
            out.duplicates.append(task_id)
            continue
        seen.add(task_id)

        # Strict CONDITION ORDER 1..8, condition 8 (committed) LAST. It is what makes
        # a refusal name the FIRST unmet condition, and what lets one test isolate one.
        # The pair probe is condition 3 (not a condition of its own), PER TASK: a
        # pair is attached to a task, the verdict to the plan (T-00000673). It
        # speaks ONLY for a task the plan ENROLS: on a task it does not enrol,
        # condition 5 is the true refusal and a pair must not mask it.
        matched = enrolling_line(text, task_id) if text is not None else None
        reason = (
            condition_state(task_id, board_states)
            or condition_plan_exists(fingerprint, plan_rel)
            or (condition_pair_form(latest_pair_verdict_for_task(entries, task_id), verdict, plan_rel)
                if matched is not None else None)
            or condition_verdict(verdict, plan_rel)
            or condition_fingerprint(verdict, fingerprint)
            or condition_roster(text, task_id)
            or condition_draft(text, plan_rel)
            or condition_night_delivered(entries, task_id)
            or condition_committed(root, plan_rel, task_id)
        )
        if reason is not None:
            out.outcomes.append(TaskOutcome(task_id, SKIP, reason=reason, matched=matched))
            continue

        assert fingerprint is not None and verdict is not None  # conditions 2-4 passed
        wanted = (plan_rel, fingerprint)
        already = any(
            contract_identity(root, e.get("text", "")) == wanted
            for e in existing_contracts(entries, task_id)
        )
        contract = contract_text(plan_rel, fingerprint, verdict["id"], approved_on)
        out.outcomes.append(
            TaskOutcome(
                task_id,
                ALREADY if already else APPROVE,
                matched=matched,
                contract=contract,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

STATUS_LABEL = {
    (APPROVE, False): "APPROUVABLE",
    (APPROVE, True): "APPROUVEE",
    (ALREADY, False): "DEJA APPROUVEE",
    (ALREADY, True): "DEJA APPROUVEE",
    (SKIP, False): "SAUTEE",
    (SKIP, True): "SAUTEE",
}


def report(lots: list[LotOutcome], apply: bool) -> list[str]:
    mode = "apply (ecriture)" if apply else "check (rien n'est ecrit)"
    lines = [f"night_approve — mode : {mode}", ""]
    approved = already = skipped = 0
    skips: list[str] = []

    for lot in lots:
        lines.append(f"LOT {lot.plan} — {len(lot.outcomes)} tache(s) nommee(s)")
        if lot.plan_sha is None:
            lines.append("  plan     : ABSENT ou illisible")
        else:
            lines.append(f"  plan     : present, sha256={lot.plan_sha}")
        if lot.verdict_id:
            lines.append(f"  verdict  : {lot.verdict_id} — {lot.verdict_status}")
        else:
            lines.append("  verdict  : AUCUN verdict plan-critic ne cite ce plan")
        for dup in lot.duplicates:
            lines.append(f"  note     : {dup} nommee plusieurs fois — traitee une seule fois")

        for o in lot.outcomes:
            label = STATUS_LABEL[(o.decision, apply)]
            lines.append(f"  {o.task}  {label}")
            # The matched line is PRINTED for every task, in --check as in
            # --apply: a guard whose work is invisible is a guard one stops
            # reading, and this is the only thing that makes the free-prose
            # title residual visible to the eye.
            if o.matched is not None:
                lines.append(f"      appariee sur {o.matched.label()}")
            else:
                lines.append("      appariee sur : AUCUNE ligne (ni titre, ni roster)")
            if o.decision == SKIP:
                skipped += 1
                lines.append(f"      raison : {o.reason}")
                skips.append(f"{o.task} ({lot.plan}) — {o.reason}")
            elif o.decision == ALREADY:
                already += 1
                lines.append("      contrat identique deja au journal — non reecrit")
            else:
                approved += 1
                lines.append(f"      contrat : {CONTRACT_TITLE} | {o.contract}")
                if o.written_id:
                    lines.append(f"      ecrit   : {o.written_id}")
        lines.append("")

    lines.append("RECAPITULATIF")
    lines.append(f"  {'approuvees' if apply else 'approuvables'} : {approved}")
    lines.append(f"  deja approuvees : {already}")
    lines.append(f"  sautees         : {skipped}")
    for s in skips:
        lines.append(f"    {s}")
    if not apply and approved:
        lines.append("")
        lines.append("Rien n'a ete ecrit. Relance avec --apply pour ecrire ces contrats.")
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_lots(raw_lots: list[list[str]] | None) -> list[Lot]:
    """`--lot <plan> T-a T-b …`, repeatable. A lot naming NO task is refused
    LOUDLY — an empty lot is a command the pilot believes he issued and which
    did nothing."""
    lots: list[Lot] = []
    for raw in raw_lots or []:
        plan = raw[0]
        ids = raw[1:]
        if not ids:
            raise NightApproveError(
                f"--lot {plan} ne nomme aucune tache. Un lot vide est refuse, jamais "
                f"traite en non-operation silencieuse. Forme : --lot {plan} T-00000123 T-00000124"
            )
        for tid in ids:
            if not TASK_ID_EXACT.match(tid):
                raise NightApproveError(
                    f"--lot {plan} : identifiant de tache invalide {tid!r}. La forme attendue est "
                    f"T-<ULID> ou T-NNNNNNNN, celle du motif de roster sur lequel "
                    f"l'enrolement est verifie."
                )
        lots.append(Lot(plan=plan, tasks=list(ids)))
    if not lots:
        raise NightApproveError(
            "aucun --lot nomme. Les lots sont NOMMES en argument, jamais decouverts : "
            "un outil qui decouvre ses propres lots est un agenda ouvert deguise."
        )
    return lots


def board_states(root: str | os.PathLike[str]) -> dict[str, str]:
    try:
        data = tasks.load(root)
    except tasks.BoardError as exc:
        raise NightApproveError(f"board illisible : {exc}") from exc
    return {t["id"]: t.get("state", "") for t in data.get("tasks", [])}


def journal_entries(root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    try:
        return specs.load(root)["entries"]
    except specs.SpecsError as exc:
        raise NightApproveError(f"journal illisible : {exc}") from exc


def run(
    root: str | os.PathLike[str],
    lots: list[Lot],
    apply: bool = False,
    approved_on: str | None = None,
) -> list[LotOutcome]:
    """Evaluate every lot, and in `--apply` write ONE contract per approved
    task through the `specs.py` API. `--check` writes nothing at all."""
    approved_on = approved_on or date.today().isoformat()
    states = board_states(root)
    results: list[LotOutcome] = []
    for lot in lots:
        # Re-read the journal per lot: in --apply the previous lot's writes are
        # part of the state the next lot must see, or a task named twice across
        # two lots would get two contracts for one identity.
        entries = journal_entries(root)
        out = evaluate_lot(root, lot, states, entries, approved_on)
        if apply:
            for o in out.outcomes:
                if o.decision != APPROVE:
                    continue
                msg = specs.add_entry(
                    root, o.task, CONTRACT_KIND, CONTRACT_TITLE, text=o.contract
                )
                found = VERDICT_ID.search(msg)
                o.written_id = found.group(0) if found else msg
        results.append(out)
    return results


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Writes in one gesture the night-eligible contracts of N NAMED lots.",
        epilog="Lots are named, never discovered. No 'approve all' mode.",
    )
    ap.add_argument(
        "--root",
        default=os.environ.get("CLAUDE_PROJECT_DIR", "."),
        help="repository root (default: CLAUDE_PROJECT_DIR or the current directory)",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="dry run - the default")
    mode.add_argument("--apply", action="store_true", help="write the contracts")
    ap.add_argument(
        "--lot",
        action="append",
        nargs="+",
        metavar=("PLAN", "T-NNNNNNNN|T-<ULID>"),
        help="a plan then the tasks it enrolls; repeatable",
    )
    ap.add_argument(
        "--delivered",
        nargs="+",
        metavar="T-NNNNNNNN|T-<ULID>",
        help=(
            "READ ONLY: tells, per task, whether a night-delivered marker is in "
            "force (condition 7). rc 0 = none, 1 = at least one in force, "
            "2 = error or journal absent/unreadable (the task is then NOT eligible). "
            "Exclusive of --lot/--check/--apply."
        ),
    )
    return ap


# `--delivered` accepts the long AND the short form: the point is precisely to
# see a marker journaled under `T-848` when asking about `T-00000848`. And a
# `T-<ULID>`, FIRST (T-00001040), which has no short form.
DELIVERED_ID = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d+)\Z")

DELIVERED_NONE = 0
DELIVERED_IN_FORCE = 1
DELIVERED_ERROR = 2


def delivered_report(
    root: str | os.PathLike[str], task_ids: list[str]
) -> tuple[int, list[str]]:
    """`--delivered` — the ONE read the night delegates to this tool (T-00000847).

    Why a sub-command rather than `specs.py list --task … --kind decision`:
    `specs.py` filters on the task STRING (`filter_entries`), so an entry
    journaled under the short form `T-848` is invisible to a read on
    `T-00000848` — measured, and the real journal carries entries in short
    form. This exposes `active_night_delivered` alone, which compares by
    IDENTITY (a legacy id by NUMERIC value, a `T-<ULID>` by its body).
    Read-only: it never writes, never looks at the board or at a
    plan. rc: 0 no marker in force for any named task; 1 at least one in force
    (each named with its `S-`); 2 a refusal — malformed id, journal ABSENT or
    unreadable — which the night reads as NOT eligible (fail-closed: a journal
    that cannot be read cannot prove the absence of a marker)."""
    for tid in task_ids:
        if not DELIVERED_ID.match(tid):
            raise NightApproveError(
                f"--delivered : identifiant de tache invalide {tid!r} (attendu T-<ULID>, T-NNNNNNNN ou T-NNN)"
            )
    # « absent » ssi NI le monolithe NI le journal (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : la forme se lit par
    # `specs.load` (`journal_entries`), qui refuse aussi les DEUX formes — jamais un « absent » par erreur.
    if not (specs.store_path(root).exists() or specs.journal_store_path(root).exists()):
        raise NightApproveError(
            f"--delivered : journal absent ({specs.journal_store_path(root)} ni {specs.store_path(root)}) — "
            "absence de marqueur non etablissable, tache NON eligible"
        )
    try:
        entries = journal_entries(root)  # SpecsError -> NightApproveError
    except (OSError, ValueError) as exc:  # ⊃ UnicodeDecodeError: never a traceback rc 1
        raise NightApproveError(f"--delivered : journal illisible : {exc}") from exc
    lines: list[str] = []
    rc = DELIVERED_NONE
    for tid in task_ids:
        marker = active_night_delivered(entries, tid)
        if marker is None:
            lines.append(f"{tid} : aucun marqueur night-delivered en vigueur")
            continue
        rc = DELIVERED_IN_FORCE
        title = " ".join(_titre_affichable(marker.get("title") or "").split())
        lines.append(
            f"{tid} : MARQUEUR night-delivered EN VIGUEUR — {_titre_affichable(marker['id'])} "
            f"(task={marker.get('task')}) « {title} » — tache NON eligible a la nuit"
        )
    return rc, lines


def main(argv: list[str] | None = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    specs.force_utf8_stdio()
    if args.delivered is not None:
        if args.lot or args.check or args.apply:
            print(
                "night_approve.py: --delivered est une LECTURE seule, exclusive de "
                "--lot/--check/--apply",
                file=sys.stderr,
            )
            return DELIVERED_ERROR
        try:
            rc, lines = delivered_report(args.root, args.delivered)
        except NightApproveError as exc:
            print(f"night_approve.py: {exc}", file=sys.stderr)
            return DELIVERED_ERROR
        print("\n".join(lines))
        return rc
    try:
        lots = parse_lots(args.lot)
        results = run(args.root, lots, apply=args.apply)
    except NightApproveError as exc:
        print(f"night_approve.py: {exc}", file=sys.stderr)
        return 2
    print("\n".join(report(results, apply=args.apply)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
