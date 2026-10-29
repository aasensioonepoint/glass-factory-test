---
name: portes-refus-pointer
description: "Pointer to the kit's gate refusal sheet .agents/ref/PORTES_REFUS.md: for each of the 21 gates, the exact refusal text, its cause, its remedy and its traced exit. Use whenever a hook answers BLOCKED or REFUSE, when tasks.py or specs.py refuses a write (start, done, new, direct, fournee, add), when verify.sh comes back red or a git push is refused, before replaying or rephrasing the refused gesture."
---

# portes-refus (pointeur)

Un refus de porte : sa cause, son remède, sa sortie tracée.

**La substance vit dans `.agents/ref/PORTES_REFUS.md` — lis ce fichier**, la section de la porte qui vient de refuser. Ce skill est un POINTEUR, pas une copie : la fiche a une seule source de vérité, lue par chemin par Codex, Gemini et Kimi depuis les skills `task-board` et `verification-discipline`, et atteinte ici sur Claude Code (Copilot lit aussi `.claude/skills/`) — rien ne dérive entre deux copies. Motif maison, identique aux autres `*-pointer`.

Les trois réflexes de l'en-tête de la fiche, à tenir avant d'ouvrir quoi que ce soit :

1. Un refus est une information : lis la cause avant de rejouer.
2. Ne reformule jamais pour passer à côté du motif (`python -c`, `cp`, `tee` à la place d'une redirection refusée) : c'est contourner la garde.
3. Une sortie tracée est un geste visible, réservé à son cas ; sinon, rapporte le refus au pilote.
