# plan-critic — T-01M63K37YX42JH0T9JERBBDY0G — itération 1/2 — NO_GO

Plan jugé : docs/tasks/T-01M63K37YX42JH0T9JERBBDY0G-plan.md sha256=81f29f435cd99ba0224ed1e3239967334e07721b8766106fe979bbc37f560c47

VERDICT: NO_GO
ITERATION: 1/2
CHECKLIST
  scope-fit             NO_GO  plan:18 INTERACTION — états annoncés non témoignés (C2) ; check 41/45 ok ; sha256 rejoué identique.
  index-fidelity        GO     SYM-new seulement ; web/ absent.
  blast-radius          NO_GO  build web rouge sous TS 7 (C1) => `npm run build` racine rouge ; api aussi en 7.0.2 ; repli « ^5 » sur web seul = deux compilateurs.
  test-adequacy         GO_AVEC_RESERVES  M4 rejoué rouge ; aria-current, aria-pressed, FR par défaut non témoignés (C2).
  rollback-viability    GO_AVEC_RESERVES  revert de web/ seul casse la racine (workspaces, lock) ; non coordonné.
  constraint-compliance GO     cibles existantes (PROMPT-projet.md:16,18,19,22) ; mandat de dépendances tenu.
  cost-realism          GO_AVEC_RESERVES  FORECAST non relayé.
FINDINGS
  C1 blocking step 1/3, M2 — TS 7.0.2 (non épinglé) : `import './styles.css'` => `src/main.tsx(4,8): error TS2882: Cannot find module or type declarations for side-effect import of './styles.css'`, rc=1 ; `tsc --noEmit -p . --types vite/client` => rc 0 ; TS 5.9.3 => rc 0. → épingler `typescript ^7`, ajouter `"types": ["vite/client"]` à web/tsconfig.json, retirer « si tsc casse, épingler ^5 », refaire M2 sur les 12 fichiers et relayer la sortie brute.
  C2 blocking step 7 / plan:18 — retirer aria-current et aria-pressed => `Tests 2 passed` ; FR par défaut non témoigné. → 3e `it` : `renderToString(<Navigation lang="en" active="horses" …/>)` : un seul `aria-current="page"` sur `data-nav="horses"`, `aria-pressed="true"` sur EN, `"false"` sur FR ; `renderToString(<App/>)` contient « Aujourd&#x27;hui » et `aria-current` sur today ; acceptation « Tests 3 passed ».
  C3 concern plan:17 — le .docx porte 6 images (maquettes §6) ; défaut « no mockup » non tracé, aucune tâche de reprise. → décision tracée, ou `mockup not reproduced: <docx> + <tâche au board>`.
  C4 concern step 5 vs plan:18 — « + Ajouter » dans `<nav>` contredit « hors de la barre » ; z-index local. → bouton frère de la nav, ou corriger `empilement`.
  C5 concern plan:18 — anneau or sur ivoire 2,36:1 < 3:1 (WCAG 1.4.11). → anneau bleu nuit ou double anneau.
  C6 concern plan:18 — largeurs, survol, focus vérifiés par design-review seul ; le dire au plan.
  C7 concern step 8 / M3 — script PNG en prose seulement. → écrire le script exact dans M3.
  C8 concern annexe — typescript hors liste du mandat (couvert par DECISIONS.md:22) ; workbox-build et workbox-window sont des peerDependencies de vite-plugin-pwa@2.0.0.
STRONGEST OBJECTION: M2 mesuré sur un autre jeu de fichiers ; le premier `npm run build` est rouge et entraîne le build racine.
UNKNOWNS: ledger non injecté ; M2 « vitest vert sans base » non rejoué ; images du .docx non vues ; dev/proxy non rejoués ; api sous TS 7 non jugée.
CAUSE_RACINE: PAS_DE_VERIFICATION
LECON_CANDIDATE: Une dépendance non épinglée se mesure à la version que npm résout le jour même, sur le jeu de fichiers planifié entier.
NEXT: planner-revise
