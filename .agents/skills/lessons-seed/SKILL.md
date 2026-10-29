---
name: lessons-seed
description: Cross-cutting lessons worth knowing BEFORE starting a project, curated from measured incidents. Use at project bootstrap, before a first plan, or when deciding where a universal lesson should land.
---

# lessons-seed — les leçons transverses, à connaître AVANT de commettre l'erreur

## Quand lire ce fichier

- **Au démarrage d'un projet**, avant le premier plan.
- **Quand une leçon universelle cherche sa destination** et qu'aucune skill de domaine ne la couvre.

Cette skill est le canal transverse des leçons universelles vers les projets adoptants. Elle
**VOYAGE** — c'est tout son intérêt : le journal `retro/LESSONS.md` et le registre
`.agents/state/memory/LEDGER.json` restent chez le mainteneur, la leçon curée arrive chez l'adoptant.

## LE COÛT D'UNE PROMOTION — à lire AVANT d'y déposer quoi que ce soit

Promouvoir vers une skill RETIRE la leçon de l'injection SessionStart : `context()` l'exclut du corps
injecté et ne laisse qu'une annonce BORNÉE à 5 ids, puis un simple `+N autres`. SUR CE DÉPÔT (mesuré
2026-08-25) 27 entrées sont déjà atterries, et une entrée nouvellement promue est ajoutée en fin de
registre : elle arrive donc en position 28 et n'est JAMAIS nommée, seulement comptée. SUR UN PROJET
ADOPTANT le registre démarre vide et l'id est encore nommé — vérifiez avec `python
.agents/bin/ledger.py context`. Une skill n'est lue que lorsqu'elle est invoquée ; le corps du
routeur, lui, est lu à chaque session. Réserver `--ref <corps du routeur AGENTS.md>` aux invariants de
1er ordre qui doivent rester lus à chaque session ; `lessons-seed` est le canal des ADOPTANTS (la
skill voyage), pas un canal d'injection.

## Comment une leçon entre ici

Jamais par une écriture d'agent. Le chemin est :

1. `python .agents/bin/retro.py consolidate` marque la leçon répétée et restitue la commande.
2. `python .agents/bin/ledger.py add --category lesson "<titre>" --text "<leçon>"` crée l'entrée de
   registre — `promote` en exige une.
3. `python .agents/bin/ledger.py promote L-NNN --ref ".agents/skills/lessons-seed/SKILL.md"` MARQUE
   l'entrée et imprime un bloc à coller. **Il n'écrit aucune surface d'atterrissage.**
4. Un humain colle le bloc ici, dans une PR. C'est la revue qui fait la curation et le scrub.

Retirer une ligne d'ici est une **rétraction** : `ledger.py archive L-NNN`, qui imprime la tâche à
créer pour la tracer.

## Les leçons

*(vide pour l'instant — chaque entrée arrive par la PR décrite ci-dessus, avec son marqueur collé
mot pour mot.)*

## Evidence for the router's Golden rules (P5 — C5)

The five Golden-rules lessons keep their RULE and their promotion MARKER in the
router — the layer every session loads on all six hosts. Only the `Measured: …`
evidence lives here, one level down, still in a surface that TRAVELS.

It is deliberately NOT in `retro/LESSONS.md`: that path is `strip:`-ed, so a
promotion landed there would be retracted for adopters without anyone being told,
and then destroyed by the 90-day purge. The rule stays where it is read; the proof
moves where it can be looked up.

### A DEFECT DIAGNOSIS IS CROSS-CHECKED BEFORE IT IS FIXED, EVEN WHEN IT COMES FROM AN AGENT.

Measured: a diagnosis arrived with three remedies, and instrumenting one real tick REFUTED it — all three would have weakened a correct invariant to compensate for a broken test clock, one of them reopening a hole another lesson had just closed. A remedy shipped alongside a diagnosis is a HYPOTHESIS, not an instruction; the executor must be able to refute it on measurement, and must be asked to try.

### A DOC ASSERTING A GUARANTEE THE CODE DOES NOT HOLD PREVENTS ANYONE FROM SEEING THE DEFECT.

Measured: the doctrine said every active constraint was reinjected at session start. It had been false for a long time — six out of twenty-eight — and nobody had seen it, PRECISELY BECAUSE the sentence said all was well: there was no reason to go and measure. Write what the code does, or write the limit; a reassuring sentence is a defect with a shield.

### A PLATFORM-SCOPED CONSTRAINT MUST CARRY ITS SCOPE, OR IT IS RE-READ AS UNIVERSAL.

Measured: a socket rule established on Windows was written without naming its platform; applied under POSIX, where the option concedes nothing, it protected nothing and broke a legitimate re-bind. A lesson that does not say where it holds will be applied where it does not.

### AN ENUMERATION UNDER A UNIVERSAL TITLE IS A DELAYED LIE — WHERE YOU CANNOT ENUMERATE, BOUND.

Paid four times on one file in one night: each round a clause was written as a LIST of constructs under a comment announcing a universal, and each round the next boundary was a fail-open. If the title claims "all", the code must decide on a closed property; otherwise say what the list covers and what it does not.

### A MECHANISM WHOSE RETURN CHANNEL IS DISCARDED DOES NOT EXIST — CHECK THE CHANNEL BEFORE DESIGNING THE TRIGGER.

Measured over three plan iterations: every caller of a refresh discarded the builder's stdout, so any device that "prints a warning" from there was mute by construction. Before wiring a signal, establish that something reads it.
