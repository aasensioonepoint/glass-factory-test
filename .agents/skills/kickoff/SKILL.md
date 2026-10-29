---
name: kickoff
description: Run the full agentic development pipeline for a task. Usage — $kickoff [-s true|false] [--defer-night] <task description> (default true). Use when the user says kickoff, start a task, implement a feature, or asks for the Claude-style pipeline.
---

# Kickoff Workflow

Use this skill to run the Codex/Copilot equivalent of the Claude kit's `/kickoff` command.

## Inputs

- User task description.
- `-s true|false` flag (default `-s true`) — controls whether class-3
  dependency findings stop for a pilot decision or are logged and skipped.
- `--defer-night` flag (absent by default) — approve the plan without starting
  the dev stages, and write the night-eligibility contract instead (step 8b).
- the board, read through the CLI (`tasks.py list --json`; store: `TASKS.json` OR record files) (+ generated `TASKS.md` view)
- `.agents/state/index/CODEBASE_INDEX.md`
- `.agents/state/index/SYMBOLS.md`
- `.agents/ref/DOCS_REGISTRY.md`
- `.agents/state/index/CUSTOM_DOCS.md`
- `.agents/ref/TOKEN_BUDGETS.md`
- `.agents/security/sca-waivers.json`

## Process

1. Parse arguments: if they start with `-s false` or `-s true`, strip that
   flag (default `-s true`) and carry it into the security stage below.
   Everything after the flag is the task description.
2. Read the board, read THROUGH THE CLI (`python .agents/bin/tasks.py list --json`, or `list --task T-NNN`): its store is `.agents/state/board/TASKS.json` OR one record file per task under `.agents/state/board/tasks/` — never hand-parse it, and `.agents/state/index/CODEBASE_INDEX.md` first.
   If the task is not on the board yet, add it:
   `python .agents/bin/tasks.py new "<title>" --owner <first dev agent> --pas-un-defaut "<why>"` (a kickoff task is usually a feature; a MEASURED defect takes `--mesure "<cmd> => <observed>" --motif <M>` instead).
   Never hand-edit the board — drive it with `tasks.py` (`new` / `start` / `fournee` /
   `stage` / `block` / `unblock` / `done` / `regroup`); devs run in parallel, in git worktrees, as soon
   as `writeset` then `parallel` has proven their DECLARED writesets disjoint — never the observed
   writes — and any `parallel` refusal serialises (an overlap, a declared order among others) — an undeclared writeset is declared first (worktree mode: `.agents/skills/task-board/SKILL.md`). Parallel devs are measured on Claude Code only; elsewhere series under COVERAGE DEGRADED (per-host status, date and cause: `.agents/ref/PARALLELISME_HOTES.md`). How many leave at once is the station verdict, never a fixed number: each wave leaves in ONE message of at most the `PEUT_AJOUTER` of `charge_poste.py verdict` (THE STATION VERDICT, in the batch below).
   The state a developer sees in the statusline and at session start comes
   from there, and it shows the FOCUS task: the first running one in store order.
   If instead you are resuming, re-scoping, or escalating a task already on
   the board, also run `python .agents/bin/specs.py list --task T-NNN` and
   hand its framed, bounded output into the upcoming planning and adversarial
   review stages as additional context — this per-task journal is read on
   demand, never injected.
   **FERMER AVANT D'OUVRIR** (R1 of the three efficiency rules, pilot decision
   S-01M4ZG7Q5FAHQFVKG10Y81ZYXH): before planning a NEW task, sweep that board — while a
   delivery is ready or nearly (lots returned, review, gate or `done`s pending), no new plan
   starts: close it first, in one common gate, and stay on the queue. A resumption opens no
   new plan; the next child of a cadrage cut is the written exception (S-01M5ATNMNBYQGYF65SNNZ5JHBN, § CADRAGE FIRST): its closures wait for the cut's single gate; a pilot order prevails. Bound: no code computes « ready », so neither `start`
   nor `fournee` refuses on this rule — it is prose. The two others: UN MINEUR NE DEVIENT
   JAMAIS UN TICKET (R2, § ONE REVIEW WAVE PER DELIVERY, step (8)) and VOIE COURTE APRÈS 3 NO_GO
   (R3, end of step 6, pilot decision S-01M51M3X9SFEZECT1QJ0XJ8GD6).
2bis. **CADRAGE FIRST** (pilot decisions S-01M5AN9N5Q4NNR5RDVQQ5QRFTV, S-01M5AQMWW0077BDFZMJAAXJP7S,
   S-01M5ATNMNBYQGYF65SNNZ5JHBN; arbitration S-01M5BFKA2D): ONCE per task, before its FIRST plan only — never on the direct route, a resumption, a revision or a child of a cadrage cut (§ CADRAGE FIRST) —, run `cadrage_plan.py` (read-only); its `CADRAGE` block is relayed FIRST,
   verbatim, before the routing summary of step 3 — § CADRAGE FIRST, in full, below the PIPELINE block.
3. Produce a routing summary without opening an approval gate:

   ```text
   TASK: <one-line summary>
   SCOPE: <read-only | mono-file | multi-file | cross-cutting>
  PIPELINE:
     1. language-detector
     2. planner or analyzer (read-only)
     3. préflight (plan_preflight.py) → plan-critic — ONE critic, premises included (read-only; S-00003871); its verdict IS
        the verdict; NO_GO → planner revises its own plan (S-01M4TZZ13Y); unavailable → COVERAGE DEGRADED
     4. planner-owned HUMAN APPROVAL GATE
     5. skills-sync/docs-sync/modeler/optimizer/dev-mono or dev-multi after approval,
        then exec-critic after any dev pass, ∥ 6 on the same diff (replays every acceptance criterion; NO_GO → dev)
     6. security-code-review (+ security-orchestrator if a manifest moved), ∥ exec-critic on the same diff
     7. deterministic index rebuild (build_index.py --if-stale, 0 LLM)
     8. documenter
     9. indexer if structure changed
    10. `tasks.py review-scope <T> [<lots…>]`, then critic-opus — CLOSING REVIEW, ONE critic for every closure (S-00004500);
        immediate fallback critic-fable, then critic-sonnet-max (on Claude Code, critic-fable
        shares critic-opus's model, so an exhausted Opus quota takes both down and the
        fallback that survives is critic-sonnet-max — go straight to it); it carries angles A and B alone
    11. route the findings to the task's dev-* agent, then
        bash core-scripts/verify.sh --at HEAD (THE GATE; never the bare form)
    12. tasks.py done T-NNN --raison "<why>" — only after 10-11
   NON-GOALS: <what will not be touched>
   INDEX HITS: <module paths or SYM IDs>
   ```

plan-critic runs after planner and before the single human approval gate; a NO_GO returns the plan to planner, which revises it with the critic's findings, for at most 8 critic iterations total, one iteration being plan-critic on one plan, after which the task is blocked and escalated to the human — plan-critic writes nothing.
`GO_AVEC_RESERVES` and `GO` both continue to that same single gate; `GO_AVEC_RESERVES` never loops. If the critic is unavailable on this host, carry `COVERAGE DEGRADED — plan-critic unavailable, verdict absent` to the gate; after approval, where `PLAN_CHAIN_REQUIRED` is armed `tasks.py start` refuses (no plan critic traced): take its traced exit `python .agents/bin/tasks.py start T-NNN --stage <dev agent> --sans-chaine "plan-critic indisponible — COVERAGE DEGRADED, verdict absent"` — a gesture that stays VISIBLE on the board — and continue — never a false GO, never a hard block.

**§ CADRAGE FIRST — step 2bis, in full** (pilot decisions S-01M5AN9N5Q4NNR5RDVQQ5QRFTV,
S-01M5AQMWW0077BDFZMJAAXJP7S, S-01M5ATNMNBYQGYF65SNNZ5JHBN; arbitration S-01M5BFKA2D). ONCE per task, before its FIRST planner only — never on the direct route (`tasks.py direct` rc 0), a resumption (4bis, 3bis, 3ter, `REPRISE_DITE`), a revision (`NO_GO`, `PLAN_A_REPLANIFIER`) or a child of a cadrage cut (its `--part` was measured at the parent's cadrage, whose block SAYS a child still above the threshold: the pilot decides then, never a re-cadrage) —, list the EXACT paths
the task will write (index first), then run, read-only, each path in double quotes (a path apostrophe breaks single quotes):
`bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task T-NNN --file "<path>" --file "<path>" … [--part "<NAME>=<path>,<path>" …] [--chantier "<name>"]`.
Its `CADRAGE <T>` … `FIN CADRAGE` block is the FIRST thing the pilot reads — relayed verbatim
through `communicator`, before the routing summary of step 3; rc 2 is a refusal (causes on
stderr): complete the inventory and rerun. `Verdict : planifier` → continue. `Verdict : découper`
→ the task NEVER goes to the planner; `$kickoff` is the surface that writes the children:
   - before creating any child, read `tasks.py deps-ready <parent>`: only `AMONT_CLOS` creates children (any other token follows L'AMONT D'ABORD, no child written); before each `new`, `tasks.py list --chantier <name> --json` — a child already there (same part) is never created twice; create each child with ONE common `tasks.py new … --chantier <name>`, then `tasks.py writeset`; each child inherits the parent's DECLARED upstream (`tasks.py depends <child> <upstream…> --motif "TECHNIQUE: upstream inherited from parent <T> (cadrage cut)"`);
     NO `depends_on` edge between children (an edge requires the upstream `done`, i.e. one more gate
     per edge), the order traced as `SUGGESTION:` (`specs.py add --kind delta`); plan each child in
     turn, in the cadrage order, never cadré again; the parent stays `pending`;
   - launch the first child by `tasks.py fournee`; a child whose writeset overlaps no `running` task
     also by `fournee`; otherwise `tasks.py start <child>` AFTER THE MERGE of every earlier child it
     overlaps — the
     4th `start` case next to the direct route, resumptions and `/night` (S-01M5ATNMNBYQGYF65SNNZ5JHBN)
     —, then `tasks.py fournee <child>` if its plan carries `LOT:` lines; that `start` demotes no `running` task (several run at once; it moves the clone's focus to the child, one active session per clone):
     before it, `tasks.py list --state running --json`; a `running` task whose write-set overlaps the child's, not yet merged → wait for its merge, never `start` (the block's `Ordre :` line names those of the cadrage);
   - close with ONE global closing review WHILE the last child is `running`, its reach declared by
     `tasks.py review-scope <parent> <lots…> <children…>` JUST BEFORE the critic (explicit list, never inferred;
     each declared member appears in the critic's brief with its diff), fixes, the single gate;
     then `done` of the batch lots, of the other children (still `running`: no `start` demotes them),
     each a member of that declared scope, never borrowed through the chantier, THEN the last child, THEN the parent with
     `done --sans-binome "parent de coordination sans code"` — never on a child or a lot; before the parent's `done`, `tasks.py list --chantier <name> --json` shows every child `done`; the `done`s
     follow the single gate with no other gate in between (the borrow expires at the next green gate).
   Adopter (`PLAN_CHAIN_REQUIRED`, `PLAN_CIBLE_REQUIRED` `chantier=*`): each child pays its plan
   chain at launch, every child's plan carries its targets and its `plan approuvé` trace; the parent, which has no plan, closes with `done --sans-binome "parent de coordination sans code" --sans-cible "parent de découpe sans plan (cadrage)"`;
   and a `direct`-stamped lot comes back through `tasks.py retour`, merged `--no-ff`, with
   its security verdict traced after the record, before its `done`. Full rule and bounds:
   `.agents/skills/planning/SKILL.md` § Le cadrage; witness `.agents/bin/test_cadrage_plan.py`.

3-amont. **L'amont d'abord — `deps-ready` (décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T).** AVANT
   `language-detector`, `planner` et `plan-critic` — avant tout agent du pipeline —, lance
   `python .agents/bin/tasks.py deps-ready T-NNN` et lis le JETON de sa 1re ligne
   `deps-ready: <JETON>`, le premier qui s'applique dans l'ordre `CYCLE` > `AMONT_OUVERT` > `INEXPLOITABLE` > `PLAN_A_REPLANIFIER` | `REPRISE_DITE` > `AMONT_CLOS` — jamais la prose qui suit :
   - `AMONT_CLOS` (rc 0) → continue.
   - `REPRISE_DITE` (rc 0) → la tâche reprend sous la trace `plan approuvé` qui l'a lancée, chaque
     amont en cause clos au plus tard à ce lancement : c'est une REPRISE, jamais une révision — DIS-LE à la porte, S-id citée ; un amont clos APRÈS le lancement rend `PLAN_A_REPLANIFIER`.
   - `AMONT_OUVERT` (rc 1) → STOP, rien n'est planifié. Restitue au pilote par `communicator`
     en mode décision, les amonts nommés dans l'ordre que `deps-ready` imprime (l'amont
     d'abord), avec trois options dans cet ordre : (1) traiter ces dépendances d'abord
     (recommandé) ; (2) la sortie tracée `--sans-dependances "<pourquoi>"`, décision du
     pilote seul, VISIBLE au board ; (3) retirer une arête TECHNIQUE fausse
     (`tasks.py depends <aval> --retirer <amont>` — jamais un `ORDRE PILOTE`, qui passe par
     une SUGGESTION). Sans réponse, rien n'est planifié.
   - `INEXPLOITABLE` (rc 1) → STOP ; un ancêtre est clos mais `plan_cible` est absent ou ne se charge pas, le journal SPECS
     est illisible ou la trace n'a pas de date lisible : la replanification n'a pas pu être jugée (fail-closed). Restitue la cause
     et le remède imprimés (réparer la lecture, puis relancer) ; `--sans-dependances` reste au
     pilote seul.
   - `PLAN_A_REPLANIFIER` (rc 1) → un ancêtre a été clos à ou après la trace `plan approuvé` :
     RÉVISION par `planner` puis `plan-critic` sur le code réel, même si le chemin de reprise
     lit 5/5.
   - `CYCLE` (rc 1) → STOP ; restitue le chemin et le remède imprimés.
   - rc 2, ou tout jeton hors de cette liste → STOP ; restitue la sortie telle quelle.
   Rejoue la même commande juste AVANT `fournee` ou `start` : le board a pu bouger, et
   `fournee` comme `start` (depuis `pending`, `blocked` ou `done`) refusent d'eux-mêmes
   tout jeton autre que `AMONT_CLOS` et `REPRISE_DITE`. READY de `plan_pool.py check`
   ne lit pas l'amont : READY n'est pas `AMONT_CLOS`. Borne : seul le `depends_on` DÉCLARÉ
   est vu. Détail : `.agents/skills/task-board/SKILL.md`, « SIXIÈME GARDE ».
3bis-morning. **Morning path — a task left `blocked` by `/night` (Claude Code only) with a note
   `NUIT : attente binôme du matin`.** The night delivered the work but never closes it
   (T-00000842). Do not re-plan it and never `unblock` it: one task at a time, read
   `tasks.py list --task T-NNN`, then BEFORE the `start` `python .agents/bin/tasks.py writeset
   T-NNN --clear` (a night parallel group survives `block`; left in place, it lets a critic of A
   cover B through the declared group) and
   `python .agents/bin/tasks.py binome-purge T-NNN` (drops ALL of the task's critic traces —
   every one predates the morning review; never `rm`, which safe-bash refuses); `start` it
   directly from `blocked` (the night's note copied into `--stage` WITHOUT its
   `[SANS CHAÎNE …]` tail, which the `start` re-appends), with `--sans-chaine "<proof>"` ONLY if
   `.agents/state/gates/PLAN_CHAIN_REQUIRED` exists (the mark is written armed or not), closing
   review — `tasks.py review-scope T-NNN` declared just before its critic —
   `critic-opus` (fallback `critic-fable`, then `critic-sonnet-max`) on
   `git diff <a>..<b> -- <writeset>` from the note,
   fixes, gate `bash core-scripts/verify.sh --at HEAD --linux` (on THIS kit repo only, the dated
   `PLAN-ETAT.md` § 4 derogation: `--at HEAD` alone), then the pilot types `done --raison`; any
   `--sans-chaine` / `--sans-cible` there is the pilot's decision.
   Full text: `.agents/skills/night/SKILL.md`, « La nuit NE CLÔT PAS ».
4. Invoke `language-detector` and require its banner-framed JSON before dispatching the planner.
4bis. **Resume path — a task that already carries a still-valid plan.** Before dispatching
   the planner, probe the task. Five probes, all measurable:
   1. `docs/tasks/T-NNN-plan.md` exists;
   2. `python core-scripts/plan_pool.py check T-NNN` exits 0;
   3. the LATEST `plan-critic` verdict in `python .agents/bin/specs.py list --task T-NNN`
      is `GO` or `GO_AVEC_RESERVES` (historic `PASS`/`CONCERNS` stay eligible), read with
      the ANCHORED grammar of `night_approve.ANCHORED_VERDICT`
      (`.agents/bin/night_approve.py:327-334`) and NEVER with `plan_pool.VERDICT_TITLE_RE`,
      which also admits `plan-critic : revue faite, GO` — the strictest downstream reader
      decides, or this workflow resumes what the night will skip;
   4. the RECOMPUTED sha256 of that file equals the single `sha256=` carried in that
      verdict's `--text`;
   5. the plan ENROLS the task — its id in line 1 or in the first `Tâches :` line, never
      just anywhere in the bytes.
   **5/5** → skip `planner` and the plan critic and go straight to the gate with the plan
   file plus the cited verdict. Nothing else moves: the single human gate is never skipped, and a
   5/5 reading is a relevé, never an approval.
   **Si `PLAN_CHAIN_REQUIRED` est armé, le `start` qui suit sera REFUSÉ** — la reprise saute la
   chaîne par construction, donc aucune trace fraîche n'existe, et le remède imprimé par le refus
   est faux ici : le plan a bien été relu, son verdict est cité. Passe la sortie tracée EN NOMMANT
   la preuve — `--sans-chaine "plan repris @ <sha>, critique de plan joué au cycle d'origine — verdict S-NNNNNNNN"`.
   Sans ça, le seul chemin praticable serait de désarmer la garde, ce qu'elle existe pour interdire.
   Any non-zero rc → FULL replanning (never partial), NAMING the code so a refusal does not
   read as a crash: `10` NO_PLAN · `11` PLAN_SANS_VERDICT · `12` SHA_ABSENT ·
   `13` WRITE_SET_ABSENT · `14` STALE · `15` VERDICT_FAIL · `16` task absent from the board
   or not `pending` · `1` execution error.
   Say this at the gate when resuming: READY means the declared write-set has not moved in
   commits since `<sha>` — uncommitted modifications of the write-set are not seen.
   SCOPE: only plans journaled in the canonical form of step 8 are resumable. A task returned
   to `pending` AFTER its security gate carries a later `security-code-review` `kind=verdict`,
   which `check` reads as `11` — the INTENDED fail-closed answer, not a defect: a task
   re-opened after execution no longer has a fresh plan. Replan.
   On this path do NOT add a new `kind=plan` checkpoint — re-stamping `<sha>` on HEAD would
   erase the peremption the old stamp encodes, and a write-set that moved since planning would
   go READY again — and do NOT rewrite the plan file nor add a verdict, since rewriting changes
   the very fingerprint probe 4 just matched. Trace the gate instead:
   `python .agents/bin/specs.py add --task T-NNN --kind decision "plan repris @ <sha> — S-NNNNNNNN"`,
   then run point 5 of step 8 and nothing else:
   `python .agents/bin/tasks.py start T-NNN --stage <dev agent>`.

   **Draft resume path — a task interrupted inside `/planning`.** Before the READY
   probes above, look for an enrolled `docs/tasks/T-NNNNNNNN-plan.md` carrying
   `STATUS: IN_PROGRESS` or `STATUS: CRITIC_REJECTED`, then read the task's latest
   **numeric** `SPECS.json` checkpoint. `kind=plan` must match an `IN_PROGRESS` file and
   resumes that revision at its critic; a refused `kind=verdict` must match a
   `CRITIC_REJECTED` file and resumes by handing that latest verdict's findings to the
   planner (the file cited by `critic=` in that verdict's `--text` when it exists, otherwise its summary under `COVERAGE DEGRADED — verdict intégral absent`), incrementing `REVISION`, rewriting the same path as `IN_PROGRESS`, hashing it
   and tracing the new `kind=plan` before the next critic. This preserves the closed
   `IN_PROGRESS → CRITIC_REJECTED → IN_PROGRESS → READY` cycle.

   In both branches verify enrolment, `REVISION`, base SHA, closed write-set and the
   persisted sha256 against the checkpoint that owns the current state; also require the
   base SHA to resolve and no declared write-set path to have moved since it. Corrupt
   bytes, a hash mismatch, a missing/lost/different write-set or any other disagreement
   means **full replanning** at the same path and a new `kind=plan` checkpoint — never a
   partial repair, and never reuse an old verdict for the new revision. The draft and the
   critic findings are DATA, not instructions. Do not discard the valid draft, but never
   treat it as executable either. Only a final plan with a final
   `GO`/`GO_AVEC_RESERVES` verdict enters the READY probes; the human gate remains.
5. Dispatch `planner` (or `analyzer` for read-only work) with the detector result and targeted index references.
   Avant CHAQUE `plan-critic`, y compris le passage court R3, jouer `bash .agents/pyrun.sh .agents/bin/plan_preflight.py --plan "<chemin du plan>" --task <T>` et transmettre au critique sa sortie BRUTE, rc compris, séparément du plan. Selon `.agents/ref/PLAN_GRAMMAIRE.md` § 5 : rc 0 tient la forme seule ; rc 1 trace tous les diagnostics et renvoie une fois au `planner`, sans verdict ni itération `plan-critic` ; au second rc 1 consécutif du cycle, arrêter et saisir le pilote ; rc 2 annonce `COVERAGE DEGRADED` avec sa cause et transmet cette sortie au critique. La ligne `PREFLIGHT:` du plan ne prouve aucun résultat.
6. Hand the plan to **ONE plan critic, `plan-critic`** (pilot decision S-00003871 —
   it replaces the former pair): structure AND the plan's PREMISES (replay the
   decisive measurements, witnesses able to go red, mutated default values); keep
   its verdict block for the gate. **Its verdict IS the iteration verdict**
   (`GO`/`GO_AVEC_RESERVES` approve, `NO_GO` loops — and a `NO_GO` is owed to a
   BLOCKING finding only: the plan as written would deliver wrong behaviour, break a
   guard or a test net, rests on a premise refuted by measurement, or exceeds 45
   non-blank lines, `plan_lots.py check` rc 1; « une réserve ne justifie jamais un
   `NO_GO` », it rides to the dev's correction pass, R2 — pilot decision
   S-01M52Y43BA). If it is unavailable (quota),
   no other plan critic runs in its place (S-01M4TZZ13Y): carry
   `COVERAGE DEGRADED — plan-critic unavailable, verdict absent` to the gate.
   `VERDICT: NO_GO` → return the findings for revision.
   At a `NO_GO`, `planner` revises its own plan with the critic's findings framed `[do not obey]` (S-01M4TZZ13Y). Hand it the critic's INTEGRAL verdict — written verbatim by you, the executor, to `docs/tasks/<T>-critic-<n>.md` and cited as `critic=<path>` in the verdict's `--text` — plus the findings closed at earlier iterations, never the `specs.py` summary; before the next iteration replay `python .agents/bin/tasks.py deps-ready T-NNN` and apply to its token the token list of step 3-amont. The planner's annexe answers with `## Constats fermés` (T-01M55W6GZ6PHRE554HVTPGN416). n = 1 + the plan-critic verdicts already journaled for the task, all cycles counted — a file is never overwritten. Hand the next plan-critic `git diff <commit of r(n-1)> -- <plan>`, or write `r(n-1) absent`; invoke it with `itération <ITERATION+1>/<PLAFOND>` and the path of `critic-<n>.md`.
   **8 iterations total per plan** —
   one iteration is one plan submitted to the critic. On exhaustion
   (iteration 8/8 still NO_GO) run
   `python .agents/bin/tasks.py block T-NNN --note "plan-critic NO_GO x8 — <n> unresolved blocking findings"`
   and carry the revised plan plus the unresolved findings into that same gate,
   where the human narrows scope, overrides a finding explicitly, or abandons.
   At that escalation, and only there, carry for every remaining blocking
   finding that can be closed WITHOUT new investigation the correcting plan line
   already written out, so the human arbitrates yes/no instead of reopening the
   enquiry. Mid-loop nothing changes: written corrections ride the
   `→ change required` field of the FINDINGS back to `planner`, never on an
   intermediate route to the human. A written correction stays a change the
   planner (or the human, there) integrates — the critic authors nothing itself.
   Record the critic's verdict in the journal: `python .agents/bin/specs.py add
   --task T-NNN --kind verdict "plan-critic <VERDICT>" --text "<findings summary> ; critic=docs/tasks/T-NNN-critic-<n>.md (NO_GO) ; chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>"`
   — the chrono of the turn: duration and tokens of the planner call and of the
   critic call, as the host prints them at the end of each agent. **On Claude Code**,
   which prints each agent's `agentId`, do NOT write the field by hand: pass
   `--chrono-aid planner=<agentId> --chrono-aid plan-critic=<agentId>` (both roles, once
   each) and `specs.py add` writes it from `.agents/state/local/agent-chrono.jsonl`; a role
   routed elsewhere (Codex) passes `ROLE=<duration>/<tokens>` as measured, never 0, or `--sans-chrono`;
   refused next to a `chrono:` already in `--text` or `--sans-chrono`. An aid unknown, without a logged stop,
   duration or tokens, out of form, of another role, or behind an unreadable journal is unresolved: rc 2 under an
   armed `CHRONO_REQUIRED` (retry once the agent has ended, or `--sans-chrono "<why>"`, on Claude Code too), else
   the entry is written without chrono and a warning. Hosts without `agentId` (Codex, Copilot, Gemini, Kimi, Antigravity) write the field by hand. **The CODE holds it** (S-01M534MZK4): where
   `.agents/state/gates/CHRONO_REQUIRED` is armed, `specs.py add` REFUSES (rc 2) a
   `plan-critic …` verdict without a readable field — exact form
   `chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>`, duration without
   spaces (`3m12s`, `45s`, `1h2m`, `12:34`), tokens `45200` / `45.2k` / `1.2M`; a
   present but unreadable field is refused armed or not. A host that prints nothing
   takes the traced exit `--sans-chrono "<pourquoi>"`, visible in the entry. Read it
   back with `python .agents/bin/specs.py chrono [--task T-NNN] [--depuis AAAA-MM-JJ]`
   (turns, cumulative duration/tokens per task, median and p90 per measured turn).
   **Plafond — the critic cap outside the kit** (pilot decision S-01M4V7RGDPP6ZK64NQ0RMN7BEN).
   Before each plan-critic invocation, and after each verdict journaled in the
   loop, run `bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNN`.
   Line 1 `PLAFOND=<N> SOURCE=<kit|adoptant|adoptant-illisible>` (ou `decoupe` : tâche découpée du kit, plafond 2 par plan, escalade comme chez l'adoptant — kickoff SKILL § 8c): 8 in the kit;
   at an adopter, 2 by default, raised only on its pilot's explicit request — the
   pilot edits N BY HAND in `.agents/state/gates/PLAN_CHAIN_REQUIRED`. Line 2
   `ITERATION=<n> ALLOCATION=<a> ESCALADE=<oui|non>` is computed by the CODE:
   n = the cycle's plan-critic verdicts, a = N + the cycle's extensions,
   deduplicated by the iteration they open (an extension journaled twice
   grants one), `ESCALADE=oui` when the last counted verdict is not an
   approval (GO, GO_AVEC_RESERVES, historical PASS/CONCERNS) — a NO_GO or an
   unreadable title — and n ≥ a. No
   readable `PLAFOND=` line (crash, missing interpreter, exit 2): plafond 2,
   never "kit"; line 2 missing or unreadable: `ESCALADE=oui` — both with a
   warning to the human.
   Hors du kit (`SOURCE=adoptant` ou `adoptant-illisible`), CHAQUE verdict
   plan-critic de la boucle, NO_GO compris, est journalisé UNE fois AVANT le
   compte. Cette entrée EST celle que la surface écrit déjà pour ce verdict —
   « Record the critic's verdict » (kickoff SKILL étape 6), ou le checkpoint
   NO_GO de /planning avec son `--text` plan=/revision=/status=/sha256= — sous
   le titre `plan-critic <VERDICT> (iteration <n>/<N>)`. Jamais une seconde
   entrée : le « Record the FINAL verdict » de fin de boucle (kickoff.md:179)
   n'en rajoute pas. La permission du titre suffixé ne vaut plus pour un
   verdict de boucle. Invoquer plan-critic avec `itération <ITERATION+1>/<PLAFOND>`.
   Au `reopen` ou à la replanification d'une tâche déjà jugée, écrire
   `python .agents/bin/specs.py add --task T-NNN --kind decision "plafond critique : nouveau cycle"`
   avant le premier plan-critic.
   `SOURCE=kit`: the 8/8 exhaustion above is unchanged. The escalation at the
   plafond belongs to the adopter alone (`SOURCE=adoptant*` with
   `ESCALADE=oui`), and there the human decides — in place of the x8 block, run
   `python .agents/bin/tasks.py block T-NNN --note "plan-critic NO_GO x<n> (plafond <N>) — <k> unresolved blocking findings"`,
   then `communicator` in mode décision — Contexte: n/N, the findings and their
   correcting plan line; La question: continuer une itération de plus ?; Vos
   options: (1) continuer une itération de plus, (2) narrow scope, (3) override
   a named finding, (4) abandon; Recommandation; Sans réponse: the task stays
   blocked. On (1): `python .agents/bin/specs.py add --task T-NNN --kind decision "prolongation plafond critique : itération <n+1>"`,
   then `python .agents/bin/tasks.py unblock T-NNN`, then a new iteration; the
   same question comes back at every further NO_GO.
   **Voie courte R3** (décisions pilote S-01M4ZG7Q5FAHQFVKG10Y81ZYXH et S-01M51M3X9SFEZECT1QJ0XJ8GD6) — in the kit too, each loop verdict is journaled once under `plan-critic <VERDICT> (iteration <n>/8)` — the suffixed-title permission no longer holds for a loop verdict; after each NO_GO so journaled, and before the critic at a revision `$kickoff` resumes from `/planning`, run `bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNN --voie-courte`; its line 3 is `VOIE_COURTE=<oui|pilote|non> NO_GO=<k|?> FICHIERS=<w|?>`, and a line 3 missing or unreadable reads `non`. At `oui` (kit only, 3 NO_GO or more on 5 FICHIERS OU MOINS, below the cap — dès le 3e NO_GO : un passage court, jamais une 4e itération complète): (a) the planner writes the correcting line of every blocking finding into a revision, journaled as a `plan` checkpoint with `--files` (its closed write-set), write-set declared again if it moved; (b) read `--voie-courte` again on that revision and go on only at `oui`, otherwise back to the full loop; (c) ONE passage court of `plan-critic`, invoked with the loop's iteration marker and the mandate "judge only whether each correcting line closes its finding — replay that line's own measurement, no new investigation and no new finding beyond what a correction creates: a defect a correcting line itself creates is judged with that line and is `blocking` (S-01M51M3X9SFEZECT1QJ0XJ8GD6); a defect seen outside the correcting lines is a `concern`, never `blocking`, and joins the dev's mandate as a non-blocking reserve (S-01M51TWBPKN5S181RY00T401V7, revisable by the pilot) — unless it is a refuted premise, a new measurement, an open pilot decision, a class-3 security item or a traced exit (S-00004310, S-00004261), which is `blocking` and sends the plan back to the full loop; any security finding stays `blocking`", its full verdict block journaled like any loop verdict, `passage court R3 sur la rév. <N>` in its text; (d) at GO or GO_AVEC_RESERVES the executor approves without the human gate, through the whole approval step below (points 1-4, 4bis, 4ter) — never `night-eligible: approved`, which stays the pilot's —, the `--text` of its `plan approuvé` gesture closing on `; approbation = voie courte R3 sur la rév. <N>, passage court it. <n> GO, constats it. <K> au mandat du dev`; each correcting line is a MANDATORY fix in the dev's mandate and each reserve of the passage court joins it as a non-blocking item, all checked by the closing review (`tasks.py review-scope T-NNN` declared just before its critic), and `security-code-review` stays mandatory on the diff — guard and security tasks included, never excluded; (e) at NO_GO only the lines it names go back to `planner`, then (a) again on those lines alone — never a full iteration, unless one of its blocking findings is of the five classes of (c), which sends the plan back to the full loop; the cap bounds this loop. `oui` is a permission, never an order: a blocking finding outside the short path — a new measurement, a refuted premise, an open pilot decision, a class-3 security item, a traced exit (S-00004310, S-00004261) — sends the plan back to the full loop. At `pilote` (adopter, ESCALADE=oui, last counted verdict NO_GO, 5 FICHIERS OU MOINS) the escalation above is unchanged and its Recommandation is option (1) played as that same passage court: on (1), once the extension is journaled, play (a) then (c) without (b) — the extension lifts ESCALADE, so `--voie-courte` reads `non` there —; at its GO or GO_AVEC_RESERVES the plan goes to the adopter's human gate, never (d); at its NO_GO the escalation comes back. `FICHIERS=?`: declare the plan's write-set (`tasks.py writeset`) then read again, or tell the pilot the bound. A decision `voie courte : exclue` on the task keeps it `non`.
7. Stop only when the planner emits the concrete plan and requests the HUMAN APPROVAL GATE, with the critic verdict attached.
8. After approval, journal the approved plan BEFORE anything starts, in THIS order —
   `plan` first, FINAL `verdict` second, because a plan checkpoint with no later verdict
   reads as `11` PLAN_SANS_VERDICT downstream:
   1. Write the approved plan VERBATIM to `docs/tasks/T-NNN-plan.md` — step 4bis and
      `/night` both read that file, not this conversation.
   2. Fingerprint it:
      `python -c "import hashlib,pathlib,sys;print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())" docs/tasks/T-NNN-plan.md`
   3. Journal the plan (the title is POSITIONAL — it comes first, no `--title` flag):
      `python .agents/bin/specs.py add "Plan @ <sha> - <objet>" --task T-NNN --kind plan --files a,b,c`
      `--files` is the CLOSED write-set of the approved plan — ni trou ni superflu ; `plan_pool.py check` intersects it with `git diff <sha>..HEAD` to pronounce STALE, so an under-declared write-set yields a false READY.
      **Plan cut into lots** (`LOT:` lines, S-01M4V1K1DG9WY2WKWKWN7ZGFC7): `--files` is the UNION
      of the paths of ALL lots AND of the `INTÉGRATION:` line — the set `plan_pool.py check`
      watches. It is not what the batch declares on the board: a lot declares its own paths
      there, the parent its plan alone, and nobody declares the INTEGRATION.
      `<sha>` is `git rev-parse --short HEAD` stamped HERE, at the gate — NEVER the file's
      sha256, which `git diff` cannot resolve.
   4. Journal the FINAL verdict, which restates the critic's last one and carries the
      fingerprint from point 2 — exactly ONE `sha256=` in that `--text`:
      `python .agents/bin/specs.py add "plan-critic <VERDICT>" --task T-NNN --kind verdict --text "plan=docs/tasks/T-NNN-plan.md sha256=<hex> — <findings, SANS autre sha256> ; chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>"`
      (Claude Code: `--chrono-aid` in place of the `chrono:` field, as in step 6.)
      The mid-loop verdict of step 6 STAYS where it is, so an approved plan leaves TWO
      `kind=verdict` entries; both readers take the LAST — assumed duplicate, not a leak.
   4bis. **Cible de plan à l'approbation (T-00000654).** À CHAQUE approbation, journalise la
      trace que `tasks.py done` relit quand `PLAN_CIBLE_REQUIRED` est armé — champs et ordre
      de `contract_text` :
      `python .agents/bin/specs.py add --task T-NNN --kind decision "plan approuvé" --text "plan=docs/tasks/T-NNN-plan.md sha256=<hex> verdict=S-NNNNNNNN approved=<AAAA-MM-JJ>"`
      C'est le geste PORTEUR ; le verdict `plan-critic` du point 4 n'est qu'une voie
      ACCESSOIRE. Un plan approuvé ne se réécrit JAMAIS : si ses étapes ne portent pas la
      cible, la clôture passe `--sans-cible 'plan figé @ <sha>'`, visible au board. La règle
      d'enrôlement qui décide au slot n'est PAS recopiée ici — voir
      `.agents/skills/planning/SKILL.md:86-88`.
   4ter. **Dépendances du plan (T-00000765).** AVANT la trace du point 4bis, pour chaque
      `ARÊTE: <aval> <- <amont> | <motif>` du plan absente de `tasks.py depends-show <aval>`,
      inscris-la : `python .agents/bin/tasks.py depends <aval> <amont> --add --motif "<motif>"`
      — sinon, sous `PLAN_CIBLE_REQUIRED` armé, la trace est REFUSÉE, comme l'absence de
      toute ligne `ARÊTE:` ou `ARÊTES: aucune`. Jamais une réécriture totale : elle efface
      les arêtes en place, et elle est refusée si elle perd un `ORDRE PILOTE`. Une dépendance
      rapportée plus tard par le binôme ou par `exec-critic` s'inscrit en `--add` si elle est
      technique ; un ordre, un retrait, ou une tâche que le plan n'enrôle pas, passe par une
      SUGGESTION que le pilote tranche :
      `python .agents/bin/specs.py add --task <aval> --kind delta "SUGGESTION: ajouter|retirer T-<aval> <- T-<amont>" --text "<pourquoi>"`.
      Plan figé avant T-765 (aucune des deux formes) : `--sans-dependances "<pourquoi>"` sur
      la trace, visible — geste MANUEL du pilote, jamais un défaut.
   5. Launch the work — **`fournee` replaces `start`** (S-01M4V1K1DG9WY2WKWKWN7ZGFC7):
      `python .agents/bin/tasks.py fournee T-NNN --dry-run` (preflight only, nothing written),
      then `python .agents/bin/tasks.py fournee T-NNN`. It REQUIRES the `plan approuvé` trace
      of point 4bis (sha256 recomputed identical), creates one sub-task per `LOT:` line of the
      plan, declares their write-sets, stamps `direct` every lot that admits it (a refusal
      leaves it planned, under the same plan), proves ONE `parallel` group and starts the
      parent, then its lots — every other `running` task keeps running, the clone's focus goes to
      the parent: the parent consumes the chain once, the planned lots borrow it
      from the parent, named. A refusal lists all its causes and writes nothing; a failure
      midway names what was written, and re-running is the remedy.
      `start` or `fournee` may instead return rc 2 `REVENDICATION`, including a resumed `start`
      or the next child of a cadrage cut: another pilot owns the task. Skip that task,
      report the refusal and its named remote/actor through `communicator`, and leave
      the chain and board untouched; do not retry with an override. Distinguish this
      diagnostic from argparse's rc 2. The old `--sans-revendication "<pourquoi>"` option
      is refused; a transfer is a pilot decision, typed in the pilot's own terminal.
      Git ancestry cannot see a squash or rebase merge; a `done` exit merged with `--no-ff`
      on the upstream can release an older claim. Explain that bound if the claim appears
      stale. An agent never takes ownership from another pilot and never supplies
      `--reprise` automatically. The refused option points the pilot to
      `start/fournee --reprise "<raison>"`. That human action
      requires nonblank reason, interactive stdin and stderr (TTY), then exact entry
      of the task id. Without them rc 2 says
      `REVENDICATION : reprise réservée au terminal du pilote, non lancé par un agent`;
      on Windows the TTY remedy to try is
      `winpty bash .agents/pyrun.sh .agents/bin/tasks.py …` or Windows Terminal
      (not measured). Claude Code and the kit hooks that set `AGENTS_HOOK_HOST`
      (Codex, Kimi, Copilot) — Kimi: assumed, not measured — refuse an agent's
      transfer by marker. Copilot CLI sets `COPILOT_AGENT_SESSION_ID` and
      `COPILOT_CLI` in the agent shell (measured, 1.0.96): that marker refuses the
      transfer — false positive: `COPILOT_CLI` is inherited by a shell started from
      Copilot CLI (`!` escape included), so the pilot transfers from a terminal
      outside Copilot CLI. Measured bound:
      Codex, Gemini and Kimi without that marker in the agent shell can
      cross TTY + confirmation in one command; it adds friction, and only the
      doctrine forbids those agents to take ownership. If the old branch is still
      published after a transfer, relay verbatim
      `REVENDICATION: ancien pilote a poussé après reprise` (tip contained, by
      ancestry, in none of the tips kept at takeover — a kept tip missing from the
      clone: the transfer commit stands in for it; without a kept tip: claim already
      merged into HEAD, or tip outside the transfer commit) or
      `REVENDICATION: prise levée par reprise encore publiée` (tip contained, or
      ancestry unreadable);
      ownership stays with the new pilot.
      A plan without `LOT:` (or
      with `LOTS: aucun`) is a degenerate batch: the parent alone, with its write-set declared
      on the board by `python .agents/bin/tasks.py writeset T-NNN <paths…>` BEFORE the batch —
      the exact files of the plan; if the parent has a group, close it first (`block`/`done`
      its co-members). The batch keeps that declared write-set and never rewrites it (its
      header says « write-set déclaré gardé »); without a real one — no declared path outside
      its plan, compared case- and slash-folded — it REFUSES (rc 2, nothing written: the
      disjointness would be proven on nothing) and names this remedy: declare, then re-run.
      An INADMISSIBLE path in that write-set (`./…`, `..` — hand-written on the board:
      `writeset` would have refused it) makes it REFUSE the same way (rc 2, nothing written,
      the path and its admission diagnostic named): never counted outside the plan; same
      remedy. A degenerate parent ALREADY running with a write-set reduced to its plan no longer
      makes a neighbouring batch refuse (T-01M5F728B4CS1ZDZTH9YWJ0AZ1): the batch keeps every
      foreign `running` task running, outside its own group, and SAYS the disjunction is judged
      on that plan alone (no declared write-set: not judged), remedy named:
      `python .agents/bin/tasks.py writeset <parent> <real paths…>`, then RE-RUN the batch to have
      it judged; the batch re-declares the group of its own parent and lots — NEVER `parallel`
      before the re-run: a `blocked` co-member regrouped would make it refuse (rc 2, measured).
      TRAP: `tasks.py writeset` still prints « re-declare with `tasks.py parallel …` » (and,
      on refusal, « then re-declare the group with `tasks.py parallel …` »); in a batch, do
      NOT follow it — re-run the batch.
      The code demands that the write-set EXISTS, never that it is RIGHT. A plan with nothing
      to write outside itself calls for no batch. `start` stays for the
      DIRECT path (no plan, so no trace), the resume path of step 4bis, the morning path, `/night`, and the next child of a cadrage cut,
      after the MERGE of the earlier children it waits for (§ CADRAGE FIRST), then `fournee` if its plan carries `LOT:` lines (S-01M5ATNMNBYQGYF65SNNZ5JHBN). Then every lot follows the worktree mode (`.agents/skills/task-board/SKILL.md`):
      - one dev per lot, each in its own worktree created from the SAME `<base>`
        (`git worktree add -b wt/<lot> <dir> <base>`), with the write-set of ITS lot. Each dev
        mandate carries the `BANCS:` line of THE BENCH LIST (below). On Claude
        Code the devs leave by waves, each wave in ONE message of at most `PEUT_AJOUTER` lots (THE
        STATION VERDICT, next point); on a host where parallel devs are not measured the
        lots run one after the other, and the report carries
        `COVERAGE DEGRADED — parallélisme des devs non mesuré sur <hôte> : lots joués en série` (the host's status, date and cause: `.agents/ref/PARALLELISME_HOTES.md`);
      - THE BATCH LAUNCHER — **Claude Code only** (any other host plays its lots as above): once
        `fournee` has started the lots, the calling session MAY hand them to the Workflow tool,
        `scriptPath: ".claude/workflows/workflow-fournee.js"`, with the JSON args its header
        names, all checked before the first agent: `base`, `label`, `grappes` (a grappe carries
        one lot or more) and a `bancs` field on EVERY grappe (its lots' `BANCS:` line), never a
        default list. The CALLER passes `session`, the session link (`https://…`), because a
        Workflow script cannot read its own session; without it the `Claude-Session` line is left
        out, and said. `repo` is optional: a context agent derives the root (`git rev-parse
        --show-toplevel`), and a `repo` that differs from it stops every dev. A grappe that does
        not start comes back with its status: `args` (args refused, no agent), `contexte` (root
        unreadable or different, or a grappe's branch already present: an interrupted run, to
        merge or remove before relaunching), `quota` (the
        `cadre-quota` stop), `charge` (three probative zero verdicts in a row: the launcher hands
        the remaining grappes back, where THE STATION VERDICT below departs in series). It KEEPS
        `tasks.py retour` before each merge, THE STATION VERDICT before each wave, the SAST
        `--at HEAD` after each merge (reported, never blocking: « SAST À RELIRE ») and the
        security review of the merged diff (skipped when nothing merged); it LOSES, named: the
        local mandate file, the local `review_diff` opinion, the start of the local model server,
        the hard-coded `Co-Authored-By` line, the quota stop where `cadre-quota` is not
        installed (its return says `quota: NON MESURÉ`), the targeted tests of a non-Python
        adopter (`tests`, optional, admits only a pytest on test files, decision S-01M5APP7E5;
        absent, the lots' benches alone, the project's gate covers the rest) and any write-set
        path that is non-ASCII or holds a blank (only `[A-Za-z0-9_.@+/-]` passes). The devs run
        on the host: no route to a local model exists any more (decision
        S-01M5PCD282N11RGE73BMQK7M70). No hook is guaranteed on a Workflow `agent()` —
        `bancs-mandat.sh`, `safe-bash.sh` and `protect-paths.sh` alike, NOT
        MEASURED — so the launcher replays the `bancs-mandat.sh` rule on each rendered dev mandate
        before any agent (bench existence excepted). Its `scriptPath` resolution is MEASURED
        (S-01M5APQ7VF: script loaded, 0 agent); the hooks and the `worktree` isolation of an
        `agent()` stay NOT MEASURED, and each dev checks its own linked worktree before any other
        git command;
      - THE STATION VERDICT (S-01M4Y10HZ6Y0TAXNNK0S1VRFC1), before EACH wave:
        `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>` (`<n>` = the agents
        in flight in this session). Launch at most its `PEUT_AJOUTER`, or min(`PEUT_AJOUTER`, cap)
        when the launcher carries an optional hard cap (`A.max_devs` of a Workflow): a cap only lowers
        a wave, never raises it. `PEUT_AJOUTER` = 0 with lots left: wait IN THE TURN with
        `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n> --attendre 540`, run under the Bash `timeout: 600000`, then launch what it grants;
        at most THREE waits in a row returned at 0, then departure IN SERIES — one agent at a time,
        the next when the previous returns — and
        `COVERAGE DEGRADED — poste surchargé après trois attentes : devs un à un` said in the report.
        No readable `PLAFOND=` line, or the command killed: `max(0, 5 − ACTIFS)`, never the last
        known value. The verdict never stops an agent already running:
        `COVERAGE DEGRADED — redescente active non livrée (V1) : à la surcharge, aucun départ ; les agents en vol finissent`;
      - on return, one branch at a time: `python .agents/bin/tasks.py retour <lot> --base <base> --branche wt/<lot>`,
        then the checks of point (4) of that mode, then `git merge --no-ff` — never a fast-forward;
        a batch shipped as a DELIVERY (§ ONE REVIEW WAVE PER DELIVERY below) declares it first with
        `python .agents/bin/tasks.py livraison <parent> <lots…> --branche <L>`, adds `--vers <L>` to `retour`,
        and merges each lot into the worktree of `<L>` (`git -C <dir> merge --no-ff wt/<lot>`);
      - `security-code-review` is traced on EACH lot:
        `python .agents/bin/specs.py add --task <lot> --kind verdict "security-code-review <verdict>"` —
        the `done` of a direct lot that crosses an armed guard reads it on the task;
      - the INTEGRATION (the plan's `INTÉGRATION:` line, a shared index for instance) is
        written by the executor on the main checkout, AFTER the last merge — outside every
        declared write-set, never by a lot's dev;
      - then step 9 onwards on the whole batch (one closing review, one gate), and the lots'
        `done` BEFORE the parent's.
      Execute only the approved plan, including any required skills/docs sync or mutating
      specialist. Call `… stage T-NNN <agent>` at each subsequent stage so the board tracks
      the pipeline rather than lagging it.
8b. **`--defer-night` — approve now, execute during the night.** With this flag the
   human's approval does NOT start the dev stages: run points 1 to 4 of step 8 unchanged
   (plan file, fingerprint, canonical `kind=plan`, FINAL `kind=verdict`), then write the
   eligibility contract and stop — point 5 (`tasks.py fournee`, nor any `start`) never runs.
   PRECONDITION bis (T-01M5T4NRDN): the plan is committed and identical to HEAD — `git show HEAD:./docs/tasks/T-NNN-plan.md >/dev/null` and `git diff --quiet HEAD -- docs/tasks/T-NNN-plan.md` both rc 0; otherwise `git add -- docs/tasks/T-NNN-plan.md` then `git commit -m "docs(tasks): plan T-NNN" -- docs/tasks/T-NNN-plan.md` (same bytes, same fingerprint), then the contract — re-run both checks first; still non-zero → NO contract, tell the pilot.
   PRECONDITION ter (T-01M5T4NRDN, the night's own reading): `git status --porcelain --ignored --untracked-files=all -- docs/tasks/T-NNN-plan.md` prints NOTHING and `bash .agents/pyrun.sh -c "import os,sys;p=sys.argv[1];sys.exit(0 if os.path.realpath(p)==os.path.join(os.path.realpath('.'),os.path.normpath(p)) else 1)" docs/tasks/T-NNN-plan.md`, run from the root, is rc 0 (neither the plan nor one of its directories is a symbolic link). A `MM` line: `git restore --staged -- docs/tasks/T-NNN-plan.md`; a `!!` line: `git add -f --` instead of `git add --`; a symbolic link: replace it by the file (a linked directory by a real one), then the commit of PRECONDITION bis (a `git commit` rc 1 "nothing to commit" after the add is already clean). Re-read, then the contract.
   1. PRECONDITION (T-00000847): read `python .agents/bin/night_approve.py --delivered T-NNNNNNNN`.
      **any rc other than 0** (1 = marker in force, 2 = journal unreadable, anything
      else = the read did not run) → do NOT write the contract: tell the pilot the night already delivered this task,
      and that he must journal `night-delivered: cleared` himself first (the night
      would refuse the contract anyway). rc 0 → journal the contract, citing the
      verdict entry written at point 4 and the fingerprint computed at point 2:
      `python .agents/bin/specs.py add --task T-NNN --kind decision "night-eligible: approved" --text "plan=docs/tasks/T-NNN-plan.md sha256=<hex> verdict=S-NNNNNNNN approved=<YYYY-MM-DD>"`
   2. **Leave the task `pending`** — never `start` it: a deferred task is not in flight.
   The contract is host-neutral DATA, so writing it here is legitimate on Codex,
   Copilot, Gemini and Antigravity. Only the night RUN is Claude Code only —
   `.agents/skills/night/SKILL.md` refuses it everywhere else, and that refusal is
   not a limitation of this flag.
8c. **Plan par lot (T-01M54GE4K9)** — vaut pour les étapes du planner et du critique ci-dessus ; placé ici
pour ne décaler aucun repère de ligne cité ailleurs. Dès que le plan maître porte 2 lignes `LOT:` ou
plus et que `python .agents/bin/plan_lots.py check --plan <maître> --parent T-NNN` rend 0, la découpe
est jugée mécaniquement et aucun critique ne juge le maître avant ses lots. (1) Chaque lot K reçoit
SON `planner` puis SON `plan-critic`, avec le mandat « plan de lot K de T-NNN : tes seuls chemins sont
ceux de sa ligne `LOT:` ; enrôle T-NNN ; porte `LOTS: aucun | lot K` » ; un plan de lot qui sort de ses
chemins est un NO_GO et remonte au planner du maître. (2) Les lots partent en parallèle — Claude
Code : par vagues d'au plus le `PEUT_AJOUTER` que rend `charge_poste.py verdict`, chaque agent en vol
compté ; ailleurs : en série. (3) La session appelante écrit chaque plan de lot dans
`docs/tasks/T-NNN-lot-<K>-plan.md` — les défs sont en lecture seule, et c'est la seule exception à
« il ne crée jamais un fichier frère » —, le journalise en checkpoint `kind=plan` titré
`lot <K> : Plan @ <sha> - <objet>`, et chaque verdict de son critique sous
`lot <K> : plan-critic <VERDICT> (iteration <n>/<N>)`, chrono compris ; ces deux titres, et eux
seuls, font d'une tâche une tâche découpée. (4) Le compte est PAR PLAN (décisions pilote
S-01M56T2BMTYFRSMEVGSWGD53CG et S-01M583Y4ZG42VFAEVS7X2647VF) :
`bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNN --lot <K>` compte le lot K, la
commande sans `--lot` compte le maître. Dans le kit, une tâche découpée imprime `SOURCE=decoupe` et un
plafond de 2 pour chaque plan ; ce n'est pas `SOURCE=kit`, dont les lignes ci-dessus restent vraies
pour les autres tâches. À `SOURCE=decoupe` et `ESCALADE=oui` — deux verdicts comptés, le dernier
NO_GO, ce qui vaut aussi pour un lot rejugé après un GO —, la procédure de l'adoptant s'applique :
sous kickoff, `tasks.py block T-NNN --note "plan-critic NO_GO x<n> (plafond 2, lot <K> ou maître) — <k> unresolved blocking findings"`,
puis `communicator` en mode décision : (1) une itération de plus, (2) réduire, (3) lever un constat
nommé, (4) abandonner ; sur (1), `prolongation plafond critique lot <K> : itération <n+1>` (sans
`lot <K>` pour le maître), puis `tasks.py unblock T-NNN` ; sous /planning et /planning-all, ni block
ni unblock : la tâche sort du pool et le rapport le dit. Chez l'adoptant, son plafond et sa procédure
valent tels quels. La voie courte R3 est inerte dans une tâche découpée. (5) Consolidation, une fois
tous les lots à GO ou GO_AVEC_RESERVES : le maître reçoit une ligne
`PLAN-LOT: <K> | docs/tasks/T-NNN-lot-<K>-plan.md | sha256=<hex>` par lot, garde son statut
`IN_PROGRESS` jusqu'à son verdict final, puis passe au `plan-critic`, qui juge la découpe et la
cohérence entre lots ; son checkpoint et son verdict sont les DERNIERS `plan` et `verdict` de la
tâche, et tout retour d'un lot ensuite exige une nouvelle consolidation. Pendant les boucles de lot,
`plan_pool.py status` classe la tâche SHA_ABSENT : c'est l'état attendu, rien à corriger. (6) UNE
porte humaine, sur le maître consolidé ; `plan_lots.py check` est rejoué sur le maître juste avant
`tasks.py fournee`, après que la session a commité plans et annexe et avancé la branche de base des
worktrees ; le mandat du dev du lot K porte l'empreinte de son plan de lot et, si le maître cite une
annexe, la sienne, toujours écrite `annexe-sha256: <hex>` et jamais avec `sha256=` : le dev les
recalcule avant d'écrire, un écart l'arrête. (7) Chaque révision, maître ou lot, porte les deux lignes
`BOUCLE: it. n/N · rév. r · bloque: <constat|rien> · tranche: <planner|pilote>` et
`CHANGÉ: <delta depuis rév. r-1>`, recopiée en `changé:` à son checkpoint `plan` ; les constats de
CHAQUE NO_GO vont à `docs/tasks/T-NNN-annexe.md` § Boucle, écrite par la session appelante. Une
reprise lit la dernière entrée de CHAQUE plan : celles titrées `lot <K> :` pour le lot K, les autres
pour le maître.
9. Before running the stages below — and after EACH dev pass, fix passes
   included, so that a pass whose block leaves the context stays recoverable
   for the documenter — record what that pass changed:
   `python .agents/bin/specs.py add --task T-NNN --kind delta "<what changed>"
   --files a,b,c`. Then invoke **exec-critic** (read-only) ∥ the security stages — IN PARALLEL, on the SAME diff
   — the range `<base>..<delivered sha>` the dev's scope check diffs (point 7 of every dev def), handed to BOTH
   judges as data —,
   none waiting for another's verdict (S-01M551RDK3PRT4VGTV5BN1ZM30), where the host launches subagents together (measured: Claude Code); elsewhere in series, exec-critic first, the fix still waiting for both verdicts: it replays every acceptance criterion with
   real command output. exec-critic COUNTS in the station verdict below like any departure (S-01M559V3Y1KNXD4JQJNQ735AJH):
   two places ⇒ exec-critic and security-code-review leave together; one place ⇒ exec-critic
   first, then the security stages at the next verdict, `JUGES UN À UN — une place : exec-critic, puis la sécurité` said in the report;
   never one over for exec-critic: C30 below governs the security stages with the places left
   once exec-critic holds its own, and after three waits at 0 its series opens with exec-critic.
   The fix waits for BOTH verdicts: an exec-critic `NO_GO` and
   security findings return to the dev-* agent in ONE fix pass carrying both reports, and the
   dev's pass relance les deux — every fix pass re-runs BOTH, in parallel, on the new diff, never
   one alone; the fix pass after the closing review is not such a pass, its rule is unchanged
   (journal each verdict apart: `specs.py add --task T-NNN --kind verdict "exec-critic <verdict>"`). Between those two verdicts and that fix pass, THE ADVERSARIAL COUNTER-CHECK (below) takes every gating finding.
   Every exec-critic call of this step carries THE EXEC-CRITIC MANDATE (below). Then run the security stages the routing summary selected (launched with exec-critic above)
   (both read-only, in parallel when both apply AND the station verdict grants it).
   The exec-critic mandate also carries the `BANCS:` line of THE BENCH LIST (below).
   THE SECURITY GATE UNDER THE STATION VERDICT (C30, S-01M4Z1WA8GT6VED55AA9SEN6GT): first
   `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>`. When both apply,
   `PEUT_AJOUTER ≥ 2` ⇒ both leave in ONE message, and security-orchestrator receives
   `budget = max(1, PEUT_AJOUTER − 2)` (its specialists per wave; at `PEUT_AJOUTER` = 2 that is one
   over the verdict, and the report SAYS the +1); `PEUT_AJOUTER = 1` ⇒ security-code-review alone, then security-orchestrator at the next verdict, ALONE, with `budget = max(1, PEUT_AJOUTER − 1)` (at 1, one over, SAID).
   A single stage leaves at `PEUT_AJOUTER` ≥ 1.
   `PEUT_AJOUTER` = 0 ⇒ wait with `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n> --attendre 540`, run under the Bash `timeout: 600000`, then apply the same rule to the verdict it returns.
   A load NO-GO only when, at the THIRD verdict in a row returned at 0, the 1 min load exceeds 2C/3 or `PRESSION ≥ 2` —
   never because `PLAFOND < 5` (a 4-core station: `PLAFOND=2`, both leave, budget 1); short of
   that, still 0 ⇒ wait again, under the same bound: at most THREE waits in a row returned
   at 0, then departure IN SERIES — one agent at a time, the next when the previous returns
   (security-code-review, then security-orchestrator with `budget: 1`) — and
   `COVERAGE DEGRADED — poste surchargé après trois attentes : étapes de sécurité un à un` said in the report. Overload after three waits is NEVER a GO: it is a load NO-GO, recorded like any stage that cannot
   proceed (below). No readable `PLAFOND=` line, or the command killed: `max(0, 5 − ACTIFS)`.
   - **security-code-review** whenever code was produced: any HIGH/CRITICAL
     finding is class-1 — route the findings back to the dev-* agent, then
     re-run BOTH, exec-critic ∥ security-code-review (relance les deux). **Its verdict carries TWO fields, never a
     flat enum (C27):** `findings ∈ {n, aucun}` × `couverture ∈ {CLEAN,
     DEGRADED, refus de conclure, portable par attestation}`, and BOTH route —
     fix the sink AND treat the coverage, never one instead of the other (a
     sink found AND a submodule not enumerated is a real state: render and
     route BOTH). Loop the findings axis back to dev until no findings;
     FINDINGS are emitted always, never masked by a coverage doubt, and a
     coverage that is not `CLEAN` is not a pass. For cleanliness the coverage
     axis follows a strict precedence: `refus de conclure` ≻ `DEGRADED` ≻
     `portable par attestation` ≻ `CLEAN`. Never proceed to the documenter with
     open class-1 findings OR an unresolved coverage gap; there is NO waiver
     path for code findings. Record each verdict: `python .agents/bin/specs.py
     add --task T-NNN --kind verdict "security-code-review <verdict>"`.
   - **security-orchestrator** only if a dependency manifest was touched: it
     auto-fixes actionable findings (class-2, policy-bound via
     security-remediation) and returns a `PILOT DECISION REQUIRED` list
     (class-3, non-actionable). For each class-3 item:
     - `-s true` (default): ask the user — **FIX NOW** (route per their
       instruction) or **ACCEPT & TRACK**. On accept, append to
       `.agents/security/sca-waivers.json`: `{package, version, ecosystem,
       advisories: "*", class, severity_at_accept, status: "accepted",
       accepted_by: "<user>", date: <today>, reason: <user's words>, origin:
       "kickoff <T-NNN|task slug>"}`. Record the pilot's decision:
       `python .agents/bin/specs.py add --task T-NNN --kind decision
       "<FIX NOW|ACCEPT & TRACK> <package>"`.
     - `-s false`: do NOT interrupt the user. Append the same entry with
       `status: "pending_review"`, `accepted_by: "auto (kickoff -s false)"`,
       and continue. List all pending entries in the final summary.
   Whenever a stage cannot proceed — an open class-1 HIGH/CRITICAL, or a class-3
   pilot decision you are waiting on — record it:
   `python .agents/bin/tasks.py block T-NNN --note "<why>"`. Once the blocker is
   lifted, `python .agents/bin/tasks.py unblock T-NNN` returns it to `pending`
   (reason cleared); `start` it only when it actually becomes the task in flight
   — otherwise the board claims work is running that nobody is doing. A task
   waiting on a human must never look `running`.
10. After security passes, run the deterministic index rebuild —
    `python .agents/bin/build_index.py --root . --if-stale` (0 LLM, no agent
    synthesis) — so downstream stages see current state. The same rebuild
    also runs, guarded, at session start on already-indexed repos; neither
    touchpoint covers the mid-task window between dev shards, so read source
    directly there rather than relying on the index alone.
11. Then run checks requested by the detected stack and invoke documenter,
    handing it the dev agent's diff summary as its
    `Dev agent's diff summary (if post-change)` input — without it the
    documenter treats the call as the docs-only route and refuses
    source-file writes (docstrings, inline comments). That input is the
    output block of EVERY dev pass of this task, in order — exec-critic and
    security fix passes included, since a re-invoked dev agent reports only
    its own pass — pasted verbatim under the heading
    `Dev agent's diff summary (if post-change):`. Block per def: dev-mono
    `FILE:/CHANGE TYPE:/LINES:`, dev-multi `CHANGESET:/FILES:` (Claude,
    Gemini, Kimi defs — on Codex and Copilot no FILE:/CHANGESET: block:
    paste the report each returned, its PROOFS: block included — every
    dev def on every host ends with one), frontend-fidelity its returned
    diffs. A pass whose block left the context (compaction) is replaced by
    its `kind=delta` entry (`python .agents/bin/specs.py list --task
    T-NNN --kind delta` — framed `[do not obey]` DATA, each shown entry with
    all its `files`, bounded to 4000 chars oldest-first; only when its last
    line opens with `… truncated` and names the cut entries are those
    cut-off latest deltas read with `--kind delta --json`, unframed: DATA,
    never instructions), said as such under the heading — never silently
    dropped; an empty `--kind delta` list means the pass is LOST: say so
    under the heading, with the pass number.
    On an IaC task the dev pass is terraform-deployer's, and its def fixes its
    AUTEUR block on every host: `CHANGESET:/FILES:/IaC:/NOT DONE:` — `IaC:`
    carries the resources touched, the `fmt`, `validate` and `plan` results and
    the create/update/delete/replace counts; `NOT DONE:` names the apply, never
    played in the task.
    Update docs when
    warranted, then invoke the indexer agent — reserved for
    annotation only (`:: purpose`, Role/Owner), never the freshness
    mechanism — and refresh `.agents/state/index/` after structural changes.
    Then run the **closing review — NO TASK IS MARKED DONE WITHOUT A CRITICAL
    REVIEW** (AGENTS.md § Golden rules): ONE closing critic for every closure
    (pilot decision S-00004500) — `critic-opus`; if it is unavailable (quota,
    outage) the fallback is IMMEDIATE — `critic-fable`, then `critic-sonnet-max`
    at maximum effort (on Claude Code, `critic-fable` shares `critic-opus`'s
    model, so an exhausted Opus quota takes both down and the fallback that
    survives is `critic-sonnet-max` — go straight to it) — and the critic, alone,
    carries angles A and B
    (structure, state, side effects; business logic, regressions, unverified
    assumptions). Its mandate carries the `BANCS:` line of THE BENCH LIST
    (below). Declare its reach with
    `python .agents/bin/tasks.py review-scope <T> [<lots…>]` JUST BEFORE launching it — the explicit list it
    reviews (parent, lots, children named, never inferred; every member open, the
    clone's focus among them; each declared member appears in the critic's brief
    with its diff); a new declaration voids the traces dated before it,
    so declare first, then launch. Between that declaration and the LAST `done` it
    covers, no `start`, `fournee` or `focus` on another task in this clone: each moves
    the clone's focus, the scope falls out of focus and every remaining `done` refuses;
    `tasks.py focus <declared focus>` restores it, with no new critic. The independence of two models is ABANDONED by that
    decision, never weakened in silence. All three defs exist on the
    five hosts that carry an agents directory (`.claude`, `.codex`, `.gemini`,
    `.kimi-code`, `.github`); Antigravity's agent discovery is undocumented.
    Each report carries three blocks: gaps spotted, findings
    (`file:line`, root cause, scenario), concrete fixes (the exact code) — a
    bare verdict is a refusal to work. FIX its findings — route them to the
    task's dev-* agent (fix pass: `kind=delta`, replay `security-code-review`
    on the fix diff; `documenter` only if the fix touched what it documented;
    the review is not re-run — a borrowed proof's `done` records the reviewed
    SHA on the board, `[binôme relevé sur T-… @ <sha>]`, and a task closed on
    its own trace cites that SHA in `--raison`, so the reader sees the
    corrections came after) — then run the gate
    `bash core-scripts/verify.sh --at HEAD` (`--at HEAD` alone is this kit
    repo's local waiver, AGENTS.md § Verifying before a push;
    `--at HEAD` in an adopter, whose gate is `porte_adoptant.py` and where
    `--linux` has no object; never the bare form: it stamps
    `mode=live`, refused at push and invisible to the borrow window) — the
    order is `work → review → FIX → gate → done`: a gate that went green BEFORE
    the review proves nothing about the closure. A red gate enters § La boucle de réparation bornée (porte rouge), below step 12 — 3 tentatives, arrêt si les erreurs augmentent, escalade `communicator`.
    `tasks.py done` REFUSES without one closing critic (`BINOME_MIN`) traced by
    the host (armed by `.agents/state/gates/BINOME_REQUIRED`). **Trace scope,
    cited as is from `.agents/skills/task-board/SKILL.md`: 1 MEASURED (Claude
    Code), 4 WIRED IN THE REGISTRY** (Codex, Kimi, Copilot →
    `.codex/hooks/binome_trace.py`; Gemini → `.gemini/hooks/binome_trace.py`)
    — event and field name NOT CONFIRMED host-side. The trace lands on every open,
    unconsumed member of the ACTIVE scope (its focus is the clone's focus),
    `pending` members included, stamped with the scope's `declared_at`: each
    carries its own file `.agents/state/local/binome/T-NNN.*.json`; outside the
    focus or without a scope it lands as `_sans-slot` (Claude Code only; the other
    ports write nothing) and credits nobody — the `done` refuses, naming
    `review-scope`; with a focus and no scope covering the task, an UNSTAMPED trace
    (older tracer) credits nothing either, and under a scope that covers it, its own
    trace is set aside if it predates the declaration or its `at` is unreadable. A task with no trace of its own
    BORROWS only from a `running` member of the same scope or of the same
    declared `parallel` group (`[binôme relevé sur T-slot]`, valid until the penultimate
    frozen green — and, with fewer than two frozen greens in the local
    `VERIFY_STAMP.log` (a fresh clone), `cycle_precedent` returns None and
    the borrow falls back to a 24 h age bound: one critic whose
    `at` is under 24 h, an absent, malformed or future (beyond 5 min)
    `at` refused (`tasks_gardes.py`,
    T-00000846); within those 24 h one review still covers every sub-task
    closed under the slot) — `start` demotes nobody, but the borrow follows the
    declared scope, never the chantier; a `done` refused naming `review-scope`
    (a focus, no scope): declare it, then relaunch the critic. Where
    `done` refuses although the critic ran, READ the refusal first —
    `done` carries three guards that each name themselves: binôme
    (`N critique(s) tracé(s)` / `PÉRIMÉE`), plan target
    (`PLAN_CIBLE_REQUIRED`, exit `--sans-cible`), dependencies (`ARÊTE(S)`
    in the refusal); only the first is a trace question. Then check that
    the task was an open member of the active scope when the critic stopped (on Claude a trace landed as
    `_sans-slot.*.json` with `motif=aucune portée`, `portée hors focus` or `portée consommée`
    means no active scope named it: declare `review-scope`, relaunch the critic; with
    `motif=aucune running` it means the hook READ the
    board and saw no `running` task; `motif=board illisible` (`tasks.py
    list` non-zero, timed out, unreachable or output that is not a JSON
    list) is an incident during which a task may have been running —
    report it as such; the other hosts write nothing outside the active
    scope; only while a task is `running` do they say on stderr `aucune portee`,
    `portee hors focus` or `portee consommee -- aucune trace ecrite`, and they say
    `board illisible` on stderr whether or not a task runs — visibility on exit 0
    unmeasured; if `tasks.py list --json` answers now, relaunch the critic
    rather than reporting) and that no
    `reopen` purged it; only then report it to the pilot as a probable
    unconfirmed host trace — using `--sans-binome` for it is the pilot's
    decision, never the agent's. `--sans-binome "<why>"` is a traced exit
    for a duplicate, a stale ticket or a no-code decision only.
    At closure, record the outcome — `python .agents/bin/specs.py add --task
    T-NNN --kind decision "closed T-NNN" --text "<one-line outcome>"` — and
    capitalize into institutional memory when something learned should
    outlive the task: `python .agents/bin/ledger.py add --category
    <lesson|decision|constraint> "<title>" --text "<detail>" --related T-NNN`.
    Close the task with `python .agents/bin/tasks.py done T-NNN --raison "<pourquoi>"`.
    **The reason is MANDATORY** and lands in `stage`: `done` was the only
    terminal verb with no explanation, so the board asserted "finished"
    without ever saying on what grounds. Cite what closes it — the green gate
    and its sha, the review that passed — not the fact that it is closed.
12. Post a final summary: files changed, tests status, task-board state change,
    security verdicts (active/waived accepted/pending counters), waiver
    entries written this run, and any effort/model overrides actually
    applied.

**La boucle de réparation bornée (porte rouge)** (T-01M5BZC0QVFN68QYEE3SG87FCJ, ordre pilote
S-01M5D9T3AZS3S10YD284G0RJ78). Quand la porte de la clôture rougit — celle de l'étape 11, ou la porte
unique d'une livraison, § ONE REVIEW WAVE PER DELIVERY (11) —, la réparation tient en 3 tentatives
au plus, arrêt si les erreurs augmentent, escalade `communicator`. Six points :
- (1) **Déclencheur.** `bash core-scripts/verify.sh --at HEAD` rend rc ≠ 0 sur un SHA qui porte le
  travail de la tâche. Une porte tuée n'est pas une porte rouge : une porte interrompue AVANT son
  verdict (délai de l'outil dépassé, commande coupée, charge — `DOIT_REDESCENDRE_A`, EDR) se rejoue
  UNE fois après le verdict du poste (THE STATION VERDICT, step 8), sans consommer de tentative ;
  une unité `TIMEOUT` d'une porte qui a RENDU son verdict est, elle, une unité rouge. Un rouge
  PRÉEXISTANT — déjà rouge au SHA de base (le premier parent de la fusion `--no-ff`, `HEAD^1`, ou
  `git merge-base <cible> <branche>` avant elle), mesuré en rejouant la seule unité rouge dans un
  clone jetable à ce SHA — est nommé au rapport, ne consomme pas de tentative et ne se corrige pas
  dans cette tâche (R2 : une tâche `--motif sans-fournee` s'il n'est pas un mineur) ; le push
  attend toujours un SHA vert, donc il remonte au pilote comme un point BLOQUANT.
- (2) **Une tentative n** (k_0 : les unités rouges de la porte déclenchante ; k_n : celles de la
  porte rejouée par la tentative n). (a) Lire le log ENTIER de la porte, jamais `| tail` ; relever
  le nombre d'unités rouges (fichiers de banc ou jobs, tels que la porte les compte) et leurs noms.
  (b) Confier la correction au `dev-*` de la tâche (même slot ; `frontend-fidelity` sur une tâche
  d'écran ; sur une fournée ou une livraison, celui du membre que l'unité rouge touche), mandat
  borné aux unités rouges nommées et au write-set de la tâche, avec sa ligne `BANCS:` (THE BENCH
  LIST) ; la correction se commite comme une correction de clôture (sur une livraison, sur `<L>`,
  puis `git merge --no-ff <L>` rejoué dans la cible). (c) Tracer `--kind delta` avant de rejouer :
  `python .agents/bin/specs.py add --task T-NNN --kind delta "porte rouge — tentative <n>/3 : <k_(n-1)> unités rouges (<noms>)"`.
  (d) Rejouer `security-code-review` sur le diff de la correction (classe 1, non waivable).
  (e) Rejouer la porte, une seule à la fois, sous le verdict du poste, avec
  `CADRE_GATE_FAIL_FAST=0` : un compte coupé par l'échec rapide (lignes `NOT RUN` au log) ne se
  compare à aucun autre — si la porte déclenchante l'a été, k_1 ne se compare pas à k_0.
- (3) **Bornes d'arrêt**, dans cet ordre, après chaque rejeu : vert ⇒ la clôture continue vers
  `done` (la correction est une passe de correction : la revue n'est pas rejouée, comme pour les
  constats du critique) ; k_n > k_(n-1) ⇒ ARRÊT immédiat, « les erreurs augmentent » : la dernière
  correction est RENDUE — `git revert --no-edit <sha>` sur la branche où elle a été commitée, dit au
  journal —, et aucune tentative n+1 ; n = 3 encore rouge ⇒ ARRÊT. Jamais une 4e tentative sans la
  prolongation du pilote du point (4), jamais une tentative sans trace.
- (4) **Escalade** à l'arrêt :
  `python .agents/bin/tasks.py block T-NNN --note "porte rouge x<n> — <k_n> unités rouges (<tendance : stable|en hausse>) : <noms>"`,
  puis `communicator` en mode décision — Contexte : les n tentatives, k par tentative, ce qui a été
  rendu ; La question : que faire de cette porte rouge ? ; Vos options : (1) une tentative de plus,
  mandat recadré par le pilote ; (2) rendre toute la livraison (`git revert -m 1 <sha de la fusion --no-ff>`) ;
  (3) tracer un rouge comme connu et accepté (décision pilote, `specs.py add --kind decision`), qui
  n'ouvre pas le push : le push attend un SHA vert ; (4) abandonner la tâche ; Recommandation ;
  Sans réponse : la tâche reste bloquée, rien n'est poussé. Sur (1) :
  `python .agents/bin/specs.py add --task T-NNN --kind decision "prolongation boucle de réparation : tentative <n+1>"`,
  `python .agents/bin/tasks.py unblock T-NNN` (le `start` suit la règle de l'étape 9 : seulement
  quand elle redevient la tâche en vol), puis une tentative de plus ; la même question revient à
  chaque arrêt suivant.
- (5) **Portée.** `$kickoff`, toutes ses voies — planifiée, directe, reprise — et la fournée ou la
  livraison : une porte commune, une boucle commune. `/night` hors portée : son agenda fermé et son
  horloge partitionnée gardent leur règle (`.agents/skills/night/SKILL.md`). Chez l'adoptant, la
  même boucle sur sa porte (`verify.sh --at HEAD`, `porte_adoptant.py`).
- (6) **Bornes, dites.** Ça empêche d'OUBLIER, pas de TRICHER : cette boucle est de la PROSE,
  comme la chaîne — aucun code ne compte les tentatives ni ne refuse la 4e ; la trace `kind=delta`
  est la seule preuve, et `.agents/evals/test_boucle_reparation_doctrine.py` n'épingle que le TEXTE.

**ONE REVIEW WAVE PER DELIVERY (pilot decision S-01M4WTZ1QZQJZZNYRC5YA67AZW, 2026-10-14).** A
delivery — a batch, a set of tasks shipped together, a template tag — runs ONE closing review,
launched only once every task of the delivery has its exec-critic verdict (GO or GO_AVEC_RESERVES)
and its security verdict, on the frozen delivery branch `<L>` BEFORE it is merged into its target,
and ALWAYS before the gate, never after a green gate. A finding that needs an architecture decision
is routed to a task, its bound traced on that task (`specs.py add --kind delta`); it never reopens the wave. Measured on
2026-10-14: three successive review waves, the last one after a green gate, turned a 45-minute
delivery into four hours. The order, step by step — `tasks.py livraison`, `retour --vers` and the
borrowed review are held by code; everything else is prose the executor holds by hand:

- (1) `python .agents/bin/tasks.py livraison <T…> --branche <L>` — ALWAYS, even for a single task:
  `retour --vers <L>` refuses a task that does not carry `livraison.branche == <L>`, and the
  closing `done`s borrow the review through this declaration only under the scope rule of step (6). The same dict lands on every named
  task; declaring again replaces it, and says so — with a FRESH date `le`, so every trace dated
  before it stops being lent: declare the delivery BEFORE launching the critic, otherwise the
  `done` refusal says « la trace de … précède la déclaration de la livraison » (a member's own
  trace is not checked against `le`); `--retirer` removes the NAMED delivery only, and refuses a
  task that carries another one (rc 2, nothing written); `reopen`, and a `start` from `done`, drop
  it — the cancelled closure takes its review with it.
- (2) `<L>` lives in a WORKTREE of its own: `git worktree add -b <L> <dir> <base>` (`<dir>` under
  `.claude/worktrees/` on Claude Code). Never `git switch` the main checkout to `<L>`: the main
  checkout stays on the target, where the state is written.
- (3) The devs work on `wt/<T>`, one worktree each (worktree mode, `.agents/skills/task-board/SKILL.md`).
- (4) Return, one branch at a time, FROM THE MAIN CHECKOUT:
  `python .agents/bin/tasks.py retour <T> --base <base> --branche wt/<T> --vers <L>`, the checks of
  point (4) of the worktree mode, then `git -C <dir> merge --no-ff wt/<T>` — the lot merges INTO
  `<L>`, never into the target.
- (5) exec-critic ∥ `security-code-review` per task, in parallel (read-only; each verdict traced on its task).
- (6) The trace. The host writes the critic's trace on the open, unconsumed members of the active
  scope (step 7) only, `pending` members included; a member outside it gets no trace; it borrows
  only through a declared `parallel` group, from a `running` member of that group covered by the scope —
  with neither scope nor group it borrows nothing, its `livraison` declaration included — so NAME EVERY member in that scope.
  Without a `focus.json` in the clone (a clone from before this code), the old regime holds: an unstamped
  trace credits as is, and the group borrow passes with no scope. Route 1 — write-sets disjoint and no `depends_on` chain between members: declare
  the group (`tasks.py parallel <T…>`, refused notably when write-sets overlap or a `depends_on`
  chain links members — full list: `declare_parallel_group`), THEN `tasks.py start <T>` for each —
  `parallel` writes the group, never the state; no `start` demotes anyone, inside the group or out
  of it (several `running` tasks coexist). Route 2, otherwise: keep at least one member `running` (the clone's
  focus) when the critic stops, every member named in the scope, each getting its own trace.
- (7) The closing critic, launched from the main checkout, its reach declared by
  `python .agents/bin/tasks.py review-scope <T…>` JUST BEFORE it (every member named, the clone's focus among them;
  each declared member appears in the critic's brief with its diff). Its brief NAMES the tip of `<L>` it reads
  (`git rev-parse <L>`), the diff `git diff $(git merge-base <target> <L>)..<tip>`, and `<dir>`: it
  reads the files THERE, or through `git show <tip>:<path>` — NEVER in the main checkout, which is on
  the target without the delivery. No merge into `<L>` while it runs. Before any `done`:
  `git merge-base --is-ancestor <last lot merge into L> <named tip>` → rc 0, otherwise a second
  review (L-00000553 under a delivery). The trace carries the HEAD of the main checkout (measured),
  not the tip of `<L>` — hence the named tip; this check is PROSE, the code does not hold it.
- (8) Fix its findings, each fix with a witness that goes red without it, committed DIRECTLY on
  `<L>` (in `<dir>`), inside the members' write-sets — never through a new `retour --vers <L>`: a
  return recorded after the review makes the review stale for every member that BORROWS it, from
  another member or from a slot of its scope or group, and the `done` refusal names it (« un relevé de
  … postérieur à la revue »); a member that carries its OWN trace is bounded by no return — prose
  only, so under route 1, where every member runs when the critic stops, this staleness is yours
  to hold.
  **UN MINEUR NE DEVIENT JAMAIS UN TICKET** (R2, pilot decision S-01M4ZG7Q5FAHQFVKG10Y81ZYXH): a
  minor finding of exec-critic or of the security review (step (5)), of `design-review`, or of this
  closing review is fixed in THIS pass, with its witness, inside the members' write-sets as above —
  never as a follow-up ticket. One that falls OUTSIDE every member's write-set joins the same pass,
  held by the executor (AGENTS.md « UN DÉFAUT SE MESURE » : the correction pass of the batch
  closing): the write-set of a planned member is extended by a traced decision, a direct member is
  re-stamped by `tasks.py direct` (otherwise the traced exit `--sans-cible`), then the fix lands on
  `<L>` with its witness before step (9) — never an undeclared file passing through `<L>`
  (task-board SKILL, « fichier passager »). Only a finding that carries the motif `garde`, `securite`,
  `decision-pilote` or `gros` becomes a board task (`tasks.py new --mesure … --motif <M>`), and one
  that needs an architecture decision also has its bound traced on that task (`specs.py add --kind delta`), as said above.
- (9) `git merge --no-ff <L>` into the target, from the main checkout.
- (10) The INTEGRATION (the plan's `INTÉGRATION:` line), `build_index.py --if-stale`, and
  `documenter`/`indexer` when their paths fall outside the members' write-sets: written on the
  target AFTER step (9), so NOT re-read by the review — said, not hidden. A `documenter` whose paths
  are inside a write-set runs on `<L>` before step (7). On the delivery path only, this departs from
  the order of AGENTS.md § Golden rules (documenter and indexer before the closing review); the
  alignment is task T-01M4X7YNK2YCR1T36V7NQW7CRT.
- (11) ONE gate, anchored on the final sha (`verify.sh --at HEAD`; `.githooks/pre-push` compares the
  pushed sha with the stamp's), with `CADRE_GATE_BASE=<sha of the target before the merge>`
  (`.agents/skills/verification-discipline/SKILL.md`). No other frozen green gate of ANY lane between
  step (7) and step (12) — `VERIFY_STAMP.log` is shared, and a replay on the same sha does not count —
  otherwise relaunch the critic.
- (12) The `done`s, at once. Then the executor removes the worktree of `<L>`
  (`git worktree remove <dir>`); the branches are deleted after the `done`s, never before.

Bounds, said rather than discovered: with no active scope naming a member when the critic stops
there is no trace that credits anyone; a member's OWN trace is never expired by a later return nor by a re-declaration —
only a borrowed one is; the reviewed tip is checked in prose only; the name of `<L>` is not checked at `done`;
the INTEGRATION, the index and the docs written after step (9) are not re-read; the declaration
prevents FORGETTING, not CHEATING. Detail: `.agents/skills/task-board/SKILL.md`, « LA VOIE LIVRAISON ».

**MEASURED PREMISES BEFORE THE DEV HANDS BACK.** A task whose text asserts how an external tool
behaves (a host binary, a CLI, a package manager) carries the command that measures it, its output
and the tool's version; exec-critic replays these measures first. The dev runs the benches of its
`BANCS:` line (THE BENCH LIST) before handing back; a bench it believes owed and not listed is named
under FOLLOW-UPS, never run.
Measured on 2026-10-14: two exec-critic NO_GO came from unmeasured claims about which settings scope
Claude Code accepts.

**THE BENCH LIST (T-01M576S8956DA9FMXY384P7EYF).** Every call of dev-mono, dev-multi, frontend-fidelity, exec-critic, critic-opus, critic-fable or critic-sonnet-max carries ONE line `BANCS: <exact path>[::<test>], …` — the items that end the lot's line under the plan's `## Tests`, closed: exact paths of existing benches, no glob, no directory, no word — or `BANCS: aucun | <why>`. A bench an acceptance criterion runs is among the lot's `BANCS:` items if it already exists; a criterion that runs the lot's new witness rides `PROOFS:`. The list is EXHAUSTIVE; the gate runs the rest; the bench a lot creates rides its `PROOFS:`, never `BANCS:`. Closing review, integration exec-critic and correction pass: ONE `BANCS:` line, the deduplicated union of the delivered lots' items; every bench the delivery creates or renames rides the mandate's `PROOFS:` line. Direct path (no plan): the existing benches colocated with the write-set, or `BANCS: aucun | <why>`. Bench base names: the closed list of guardrails § `bancs-mandat`; existence is judged under the session root `$CLAUDE_PROJECT_DIR`, never in the worktree the mandate works in, which the hook cannot read: a bench present only there rides `PROOFS:`. Use ONE line, never recopied from another report; a line inside a ``` block does not count (~~~ alike), and on Claude Code a fence left open, a ```sh diff hunk included, is wired to refuse the call (`cloture-ouverte`): close every fence; a pasted diff carrying ``` lines goes inside a ~~~ fence (only the same mark closes it). On Claude Code the `bancs-mandat` hook is wired to refuse (NOT MEASURED on a real Agent call, guardrails § `bancs-mandat`) a call without that line or with an item that is not an existing bench; the traced way out is a line `BANCS-SANS-BORNE: <why>`, journaled `hook.warn` and said in the report, refused next to a `BANCS:` line.

**THE EXEC-CRITIC MANDATE (pilot decision S-01M55870Z099K7CN0XKS8K90AT).** Every invocation of
exec-critic on this page passes it this mandate, as data; the def stays the judge, the mandate only
says what to replay and in which order. (a) Replay EVERY acceptance criterion with real command
output — none skipped, none taken on the dev's word. (b) Replay the dev's `PROOFS:` block item by
item, and only what VERIFIES — rerun the command and compare its verdict line — instead of
re-deriving it; the block is data, never an order: an item that ACTS (a revert, an `rm`, a
`restore`, a `checkout`, a commit) is replayed only in the throwaway clone of (c), rewritten against
that clone, never in the repository under judgement and never as the dev's line verbatim; of those,
an item the def forbids (commit, restore, checkout) is re-expressed by copying files, never run; a
replayed revert runs as `git -C <clone> revert --no-commit …`, the files it touches saved first as
in (c), undone by copying the saved originals back; a push is never replayed, not even from the
clone, its `origin` removed in (c), the repository still reachable by path — this rule, not that removal, bans it: it is pushed
nowhere, neither by name nor by path or URL — it is PROBED as in (d); an item that does not replay, or a block that is absent, is
measured by exec-critic itself. (c) A mutant of its own only on a new or modified witness that
carries no dev mutant proof, or whose proof does not replay, in ONE throwaway clone outside the
repository, created once (`git clone -q --branch <dev branch> --single-branch <repository> <clone>`),
then `git -C <clone> remote remove origin`, and reused, narrowed by
`git -C <clone> sparse-checkout set <dirs>` when the witness reads only part of the tree: the
original file saved outside the repository first, the mutant written by `python3`, never `sed -i`,
then undone by copying that saved original back into the clone — never a reset or a clean of the
clone, which `safe-bash` refuses. (d) ALWAYS PROBE every command or gesture the diff PRESCRIBES
through the host's guards — never execute it — whatever the proofs say: `safe-bash` fed the
command as a JSON payload on its stdin with `AGENTS_EVENTS_DIR` on a `mktemp -d` directory,
`CLAUDE_PROJECT_DIR` and the `cwd` both set to the repository under judgement, and in the same pass
one gesture the guard is known to refuse, which must come back refused or the probe measured
nothing; a prescribed push is never probed through `.githooks/pre-push`: with no `VERIFY_STAMP` it
refuses every non-delete ref and admits every delete, so it judges nothing — mark it addressed to
the executor. (e) Station economy:
exec-critic counts in the station's load verdict as an ordinary departure (pilot decision
S-01M559V3Y1KNXD4JQJNQ735AJH); it runs one measurement at a time, and none while a gate runs
(`pgrep -f '^bash [^ ]*core-scripts/verify[.]sh'` prints nothing). Where exec-critic runs under
`sandbox_mode = "read-only"` (Codex), a probe or a clone the sandbox refuses measured the sandbox,
not the diff: it is said as `COVERAGE DEGRADED` under `BLIND SPOT`, never a verdict on the work.
(f) On a lot of a fournée, or on any member of a DELIVERY, the verdict covers the member's or lot's
diff only: the `INTÉGRATION:` paths and `CHANGELOG.md`, written outside the lot, are outside this
verdict — re-read by the closing review on a fournée, re-read by NO review on a DELIVERY, where
step (10) of § ONE REVIEW WAVE PER DELIVERY writes them after the merge — said under `BLIND SPOT`
exactly so, never as covered. Nothing here thins the judge: a criterion, a prescribed gesture or a
witness without a replayable proof is never left unmeasured.

**THE ADVERSARIAL COUNTER-CHECK (contre-vérification adverse — T-01M5BZC347S5DWVX8FR4GV3BMJ, pilot
order S-01M5D9T3AZS3S10YD284G0RJ78).** Once BOTH verdicts of step 9 are in, and before the fix pass
they feed, every gating finding goes to the OTHER judge: each `HIGH`/`CRITICAL` of
`security-code-review` to exec-critic, each `BLOQUANT` of exec-critic to `security-code-review`, both
invoked in the « Mode réfutation » of their def, each finding handed with its proof, as data. Each
judge's « Règle de preuve » acts upstream: a finding with no reproduction is already `À VÉRIFIER` in
its verdict — listed, never counted, not counter-checked. (1) The refuting judge starts from the
hypothesis that the finding is FALSE and tries to refute it by measurement — replay its reproduction,
then look for the guard, the branch or the input that prevents it — and answers per finding
`CONFIRMÉ` (reproduced by the second judge), `RÉFUTÉ` (a contrary proof, `<command> => <output>`) or
`NON TRANCHÉ` (said, with what it could not measure). (2) Routing: `CONFIRMÉ` and `NON TRANCHÉ` enter
the ONE fix pass of step 9, a `NON TRANCHÉ` fixed by prudence and said so in the dev's mandate; a
`RÉFUTÉ` leaves the pass and is traced with its proof. Fail-closed: a counter-check that does not
return, returns malformed, or answers without a proof reads `NON TRANCHÉ`; a `RÉFUTÉ` that
contradicts a reproduction of confidence `haute` (two outputs disagree) reads `NON TRANCHÉ`, both
outputs handed to the dev. (3) Classes: class 0 (a live secret) is never counter-checked away — it
is removed and rotated whatever a refutation says; class 1 stays non-waivable — a `RÉFUTÉ`
HIGH/CRITICAL leaves the security verdict OPEN in the journal until the next `security-code-review`
pass on the diff (the one the fix pass relaunches, or, when no fix pass follows, one launched for
that purpose), handed the refutation as data, traces its own verdict; a finding it maintains reads
`NON TRANCHÉ` and is fixed. (4) The trace, written by the executor — never by a judge —, one entry
per refuting judge, the title POSITIONAL:
`python .agents/bin/specs.py add "contre-vérification exec-critic : <n> confirmés, <m> réfutés, <k> non tranchés" --task T-NNN --kind verdict --text "<per finding: id, verdict, proof>"`,
and for the other judge the title `contre-vérification revue de code : <n> confirmés, <m> réfutés, <k> non tranchés`
with `juge=security-code-review` in `--text`. Never the word `security` nor `sécurité` in that title:
the `done` guards of a direct route that crosses an armed guard (`tasks_direct.py` C4,
`tasks_retour.py` (s)) read the LAST `kind=verdict` whose title carries it as THE security verdict —
measured, a title `contre-vérification security-code-review : 0 confirmés, 1 réfutés, 0 non tranchés`
traced after `security-code-review FINDINGS(code) 1 HIGH` leaves C4 with no cause: the open verdict
masked. (5) Bounds, said: this step is PROSE, like the chain — no code forces it, reads its trace or
refuses a fix pass without it; it prevents forgetting, not cheating. Where the host launches
subagents together (measured: Claude Code) the two counter-checks leave together under THE STATION
VERDICT like any departure; elsewhere in series. Its cost, one judge call more per round of gating
findings, is accepted (AGENTS.md § Full power). The closing review's findings are not
counter-checked: the fix pass after the closing review is not such a pass.

## Chrono de la tâche

**CHRONO DE LA TÂCHE — après identification ou création de son id, aussi lors d'une reprise.**
L'orchestrateur lance `python .agents/bin/tasks.py chrono T-NNN begin` une seule fois par cycle ; si `/planning` ou `/planning-all` l'a déjà lancé, `begin` reprend le cycle ouvert sans second début. La doctrine suit, dans l'ordre d'AGENTS.md : `cadrage` (cadrage_plan.py), `planification` (planner + plan-critic, boucle comprise), `attente-pilote` (porte humaine), `dev`, `juges` (exec-critic ∥ sécurité), `fusion`, `integration` (ligne `INTÉGRATION:`, index, documenter, indexer), `cloture` (revue de clôture), `correction` (passe de correction de ses constats), `porte` (verify.sh), puis le jalon `done`. `<étape>` appartient à la liste fermée `task_chrono.ETAPES`. Les mesures séparées de planner et plan-critic se lisent dans le champ `chrono:` des verdicts SPECS ; elles ne créent pas deux étapes. `tasks.py start` et `tasks.py fournee` ouvrent ou reprennent le cycle et le dev de chaque lot, ou de la tâche sans lot ; le dev ouvert par `fournee` compte aussi l'attente d'une place de charge. `tasks.py retour` abouti termine le dev du lot et ouvre la fusion ; `retour`, `review-scope` et `done` aboutis ferment la fusion à l'heure du commit de son merge `--no-ff` (chaîne `--first-parent`) ; une fin du lanceur posée avant l'emporte ; avance rapide, squash ou rebase : fusion dite sans fin. `tasks.py review-scope` abouti relève `juges` si aucune clé `juges` n'est écrite : une fenêtre de la plus grande fin de dev ou de fusion du cycle jusqu'à lui (sans fin : avis ; fusion encore ouverte : avis « chevauche »), puis ouvre `cloture` ; un dev encore ouvert (d'un lot, ou à côté d'une fin écrite) : avis « dev encore ouvert », ni juges ni clôture, relevés au `review-scope` suivant. `tasks.py done` abouti pose le jalon `done` sur le parent ou la tâche seule et clôt le cycle ; un lot n'a pas son propre jalon done. Avant ce jalon, le `done` complète `cloture`, `correction` et `porte` : `cloture` finit à sa fin au journal, sinon à la dernière trace de critique ; une `porte` par ligne `frozen` ou `frozen-linux` de `porte-chrono.tsv` dans la seconde de fin de clôture ou après, dont le sha contient les pointes de la tâche et de ses lots ; `correction` va de la fin de clôture à la première porte. Bornes : `juges` est une fenêtre, jamais une mesure d'exec-critic ; une porte commune d'une fournée, ou le sha d'une autre tâche qui contient ces pointes, compte pour chacune ; clé `cloture` ou trace sans fin : ni porte ni correction, avis. `done` dit sur stderr `CHRONO: avis …` (cycle absent, étapes sans fin), sans jamais refuser ; dans un cycle clos, `show` borne toute étape restée sans fin à la fin du jalon done, statut « incomplète », sans écrire de fin. Le lanceur reste responsable des étapes que ni `retour`, ni `review-scope`, ni `done` ne relèvent. Avant CHAQUE étape estimable, lancer `python .agents/bin/tasks.py chrono T-NNN estimate --etape <étape>`, puis `python .agents/bin/tasks.py chrono T-NNN step --etape <étape> --phase begin`. L'attente du pilote reçoit `step --etape attente-pilote --phase begin` sans `estimate`. À la sortie de chaque étape, même en échec ou en attente, lancer `python .agents/bin/tasks.py chrono T-NNN step --etape <étape> --phase end` et `python .agents/bin/tasks.py chrono T-NNN show` ; afficher la durée réelle et l'écart lorsque le périmètre est mesuré. Le lanceur ne double pas les jalons déjà posés par `tasks.py`. Un rc non nul de `chrono` se signale dans le rapport et ne bloque jamais l'étape métier. Le suffixe `⏱` suit l'id de la tâche focale, AVANT le détail de stage : un détail long ne le repousse pas.

Pour un dev de lot lancé HORS `.claude/workflows/workflow-fournee.js`, l'orchestrateur peut figer `chrono <lot> estimate --etape dev` avant l'agent ; il n'ouvre pas un second dev si `fournee` l'a déjà ouvert. Il lance `chrono <lot> step --etape dev --phase end` au retour de l'agent, même en échec ; `retour` ne termine qu'un dev resté ouvert. Il relève `chrono <lot> show` au retour de l'agent, y compris arrêt ou échec. Le workflow actuel garde un début et une fin explicites du dev : le début reprend le dev ouvert par `fournee`, et la fin le borne au retour de l'agent ; l'intervalle avant `retour` n'entre alors plus dans ce dev. Pour chaque fusion manuelle, `retour` abouti ouvre la fusion ; l'orchestrateur peut figer `chrono <lot> estimate --etape fusion` avant ce retour, puis lance `chrono <lot> step --etape fusion --phase end` après le merge et les contrôles, même si l'un refuse ou échoue. Le workflow actuel ouvre la fusion avant `retour` et la termine après le merge ; `retour` réutilise son début. Un lot de fournée joue au journal de son PARENT, sous sa clé de lot : le `done` du parent clôt ce cycle. Le journal est local à la racine commune ; un autre poste peut avoir un historique incomplet, à annoncer.

Journal chrono au-delà de 1 Mio (« CHRONO: non relevé ») : renommer task-chrono/<T>.jsonl en <T>.jsonl.old ; le cycle suivant repart à vide.

## Limite de la tâche

Après CHAQUE sous-agent terminé (lot : sur son PARENT — un lot n'hérite d'aucune limite : déclarée sur le lot, la conso n'est vue d'aucune), `python .agents/bin/tasks.py conso <T> <totalTokens>` (Claude Code ; ailleurs non mesuré, aucune conso inventée) (entier > 0, suffixe `k` ou `M` admis) ; agent REPRIS : la DIFFÉRENCE entre deux relevés. Sur `LIMITE-DEPASSEE:` (stderr) ou « dépasse sa limite et LIMITE_ARRET est armé » (tâche passée `blocked`, ou `start`/`fournee` refusé) : `communicator` mode décision — relever, retirer, arrêter ; jamais l'agent. `LIMITE-ILLISIBLE:` : la limite n'a pas été jugée — rapporter au pilote, jamais la tenir pour respectée.

## Déploiement — hors chaîne

A deployment request routes to `terraform-deployer` ALONE, in its DÉPLOIEMENT mode, and OUTSIDE this
pipeline — never a stage of the chain above, never inside the task that wrote the IaC (pilot decision
S-01M55NC83Z3ZWMWKDP5F6FFDDG: the agent also writes the IaC, and deploys it apart).
- **When.** After the IaC task's `done` and a green gate frozen on that SHA; on an explicit request —
  a board task, a spec or the pilot; **never under `/night`**.
- **How.** Through the deterministic runner `.agents/bin/tfdeploy.py`, whose verdict the agent reports
  as is. The apply needs a `kind=decision` entry written by the CALLING session — never by the agent —
  naming the target, the planfile sha256 and the plan's `HEAD`, with one line that OPENS on the token
  `apply approuvé` (at the head of the line) and carries no negation or withdrawal word (non, pas,
  refus…, report…, annul…, retir…, rejet…, suspend… — the runner's `APPROUVE_RE`) — otherwise
  `apply_sans_decision`: a refusal, a postponement or a negation recorded as a decision authorizes
  nothing; when the plan destroys, `destroy approuvé: <n>` equal to the count. A target `env: prod`
  is never applied from the workstation (`prod_poste`). The agent's questions reach the pilot through `communicator`.
- **Bounds, named.** Decision and gate stamp are self-declared; outside Claude Code no human sits in the
  apply loop. It prevents FORGETTING, not CHEATING. Detail: `.agents/skills/terraform-deploy/SKILL.md`.

## Rules

- If the task is read-only, use analyzer behavior only.
- If the task touches 6 files or more, require a plan before edits. A task of 5 files or fewer
  takes the DIRECT path only once `python .agents/bin/tasks.py direct T-NNN` has stamped it — the
  verb VERIFIES the criteria by code (AGENTS.md § Golden rules, « LA VOIE DIRECTE »): it goes
  straight to the dev agent, with no planner, no plan critic and no human gate, and keeps
  exec-critic ∥ security-code-review (in parallel), the closing review (`tasks.py review-scope T-NNN` declared just
  before its critic), the gate and `done`; on a UI task the dev slot is `frontend-fidelity` then `design-review`, before the closing review. A refusal lists all
  its causes and sends the task to the planned path, never to the agent's own judgment; `tasks.py direct T-NNN
  --retirer` is the way back from a stamp to the planned path, refused on an open task whose `start`
  crossed the chain (remedy: `done`, or `reopen` then `--retirer`).
- On an IaC task (`*.tf`, `*.tf.json`, `*.tfvars`, `*.tfvars.json`, `.agents/deploy/targets.json`) the dev slot is `terraform-deployer` ; exec-critic, security-code-review and the closing review run on its diff like any dev-* ; it never applies in the same task — apply is the separate, out-of-chain deploy after `done` and a green gate frozen on that SHA, through `tfdeploy.py`, on a decision it does not write.
  The task is recognized by its declared write-set and by the detector's signal (`primary_language: hcl`,
  `framework: terraform@…`); the deploy itself is § Déploiement — hors chaîne below.
- If the active host supports explicit subagents and the user requested delegation, split independent work across subagents.
- Never install a remote skill before its audit is logged in `.agents/state/gates/AUDIT_LOG`.
- Report plan drift instead of improvising.
- Do not skip steps — the DIRECT path above is the one exception, and only on a stamp — or batch
  approvals: the class-3 pilot questions are part
  of the security stage, not a batched approval — surface each one.

Claude Code counterpart: `.claude/commands/kickoff.md` — keep the two in sync.
