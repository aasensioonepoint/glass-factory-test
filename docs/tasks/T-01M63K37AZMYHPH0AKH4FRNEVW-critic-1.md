# plan-critic — T-01M63K37AZMYHPH0AKH4FRNEVW — itération 1/2 — GO_AVEC_RESERVES

Plan jugé : docs/tasks/T-01M63K37AZMYHPH0AKH4FRNEVW-plan.md sha256=a8000db1c05d5ead636d5f951c1184e00ad14e0b9aa63880e6ae91f6ea5bee17

VERDICT: GO_AVEC_RESERVES — 0 bloquant, 7 réserves (à la passe de correction du dev, R2)
CHECKLIST
  scope-fit GO ; index-fidelity GO ; blast-radius GO (base racine compatible, tsc rc 0 ; `fetch('http://localhost:3000/api/health')` => 49 sous Node 24.14/Windows) ; test-adequacy GO_AVEC_RESERVES (« Tests 3 passed (3) » rejoué hors dépôt ; M2, M3 rougissent) ; rollback-viability GO_AVEC_RESERVES ; constraint-compliance GO_AVEC_RESERVES (deps rejouées conformes, schema/ lu seulement) ; cost-realism GO_AVEC_RESERVES (FORECAST absent).
RÉSERVES
  C1 step 5 — `pg.exec` sur le client externe dans le callback de `pg.transaction` bloque (DEADLOCK mesuré, « Test timed out in 5000ms »). → « tx.exec(sql) puis tx.query(insert) sur le `tx` du callback, jamais le client externe ».
  C2 step 1 — versions ouvertes résolues à typescript 7.0.2, vitest 5.0.5, @types/node 26.6.6 pour un runtime Node 24. → `typescript ^7.0.2`, `vitest ^5.0.5`, `@types/node ^24`.
  C3 step 3 — S-01M63K3VPZ0S8VQK9FE0VA35F0 ne décide pas DATA_DIR. → `cible: « contrat déclaré »`.
  C4 step 7 — mutant `process.cwd()` non attrapé. → cas : `DATA_DIR === fileURLToPath(new URL('../../../data/pglite', <URL de client.ts>))` et ne finit pas par `api/data/pglite`.
  C5 step 2 — timeout 5000 ms trop juste (1,3–1,8 s par cas au repos, EDR). → `testTimeout: 30000`.
  C6 Tests — « 3 tests verts » ambigu après fusion. → `npm test -w api` => « Tests 3 passed (3) » et `npm test` => rc 0.
  C7 Rollback — lockfile racine périmé après revert d'api. → « puis `npm install` racine et commit du lockfile régénéré sous la tâche racine ».
STRONGEST OBJECTION: le migrateur pris à la lettre bloque PGlite ; dépendances non épinglées résolues à des majeures non nommées.
UNKNOWNS: installation conjointe des trois workspaces non mesurée ; Windows seulement ; deux serveurs sur le même data/pglite ; ledger absent ; FORECAST absent.
NEXT: human-gate
