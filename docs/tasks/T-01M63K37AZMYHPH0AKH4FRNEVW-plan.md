# PLAN — T-01M63K37AZMYHPH0AKH4FRNEVW socle api (Fastify 5 + PGlite + Drizzle, /api/health)

## Impacted symbols (by ID)
- hors index : api/ n'existe pas sur la base c013e93 (SYMBOLS.md ne couvre aucun chemin api/) ; 10 créations
- SYM-new `api/package.json` (create)
- SYM-new `api/tsconfig.json` (create)
- SYM-new `api/vitest.config.ts` (create)
- SYM-new `api/src/server.ts` (create)
- SYM-new `api/src/app.ts` (create)
- SYM-new `api/src/routes/health.ts` (create)
- SYM-new `api/src/routes/health.test.ts` (create)
- SYM-new `api/src/db/client.ts` (create)
- SYM-new `api/src/db/migrate.ts` (create)
- SYM-new `api/src/db/migrations/0001_mcd_v0.ts` (create)

## Steps
1. Créer api/package.json — "type":"module", engines node>=24, scripts dev `node --watch src/server.ts`, test `vitest run`, build `tsc --noEmit` (typecheck seul : Node 24 exécute le .ts, rien à émettre) ; deps fastify ^5, @electric-sql/pglite ^0.5, drizzle-orm ^0.45 ; devDeps typescript (>=5.8, erasableSyntaxOnly), vitest, @types/node — rien d'autre (ni tsx, ni concurrently, ni drizzle-kit) — cible: « contrat déclaré »
2. Créer api/tsconfig.json (extends "../tsconfig.base.json" ; target es2024, module/moduleResolution nodenext, noEmit, allowImportingTsExtensions, verbatimModuleSyntax, erasableSyntaxOnly, types ["node"], include ["src"] ; rewriteRelativeImportExtensions inutile sans émission) et api/vitest.config.ts (environment node, include src/**/*.test.ts) — cible: « contrat déclaré »
3. Créer api/src/db/client.ts — createDb(dataDir?) : PGlite mémoire sans argument, sinon mkdirSync récursif puis PGlite(dataDir) ; drizzle({ client }) ; export DATA_DIR = fileURLToPath(new URL('../../../data/pglite', import.meta.url)), jamais process.cwd() — décision pilote: S-01M63K3VPZ0S8VQK9FE0VA35F0
4. Créer api/src/db/migrations/0001_mcd_v0.ts — { id:'0001_mcd_v0', sql lu tel quel depuis new URL('../../../../schema/graffard_racing_mcd_v0.sql', import.meta.url) } ; fichier SQL jamais modifié — cible: « plan avant édition »
5. Créer api/src/db/migrate.ts — migrator maison sans drizzle-kit : CREATE SCHEMA IF NOT EXISTS meta + table meta.migrations(id pk, applied_at) HORS public (sinon 50 tables), liste ordonnée, chaque migration non appliquée exécutée par pg.exec + insert dans UNE pg.transaction — cible: « contrat déclaré »
6. Créer api/src/routes/health.ts (GET /api/health, schéma de réponse Fastify déclaré {status:'ok', tables:integer}, compte des BASE TABLE de public via db.execute), api/src/app.ts (buildApp({ db }) injecté) et api/src/server.ts (createDb(DATA_DIR) → migrate → listen PORT défaut 3000, host 127.0.0.1) — cible: « contrat déclaré »
7. Créer api/src/routes/health.test.ts — PGlite mémoire injectée : avant migrate tables=0 ; après migrate 200 {"status":"ok","tables":49} ; second migrate sans erreur, toujours 49, meta.migrations = 1 ligne — cible: « tests au plus près du code »
8. Vérifier après fusion des trois enfants (racine, api, web) : critères d'acceptation ci-dessous — cible: « contrat déclaré »

LOTS: aucun | un seul comportement (contrat /api/health) traverse les 10 fichiers sous un seul témoin, api/package.json est un manifeste interdit en lot, et c'est déjà un enfant de cadrage
ARÊTES: aucune
no mockup: partie api sans écran
INTERACTION: sans objet | partie api sans écran

## Risks
- Prémisse SQL tenue : chargé tel quel dans PGlite 0.5.13 (Node 24.14), 49 tables, 80 FK, rc 0 (annexe) ; si un écart réapparaît (version PGlite), STOP, angle mort au pilote — jamais retoucher schema/.
- Vérif seule impossible avant fusion de racine (extends ../tsconfig.base.json, workspaces) → critères joués après intégration, aucune arête (décision S-01M63K3VPZ0S8VQK9FE0VA35F0).
- Table de suivi dans public → tables=50 ; parée par le schéma meta, épinglée par le test.
- Syntaxe non effaçable (enum, namespace, paramètres de propriété) → erasableSyntaxOnly la refuse au build.

## Tests
- parent — témoin neuf api/src/routes/health.test.ts ; BANCS: aucun | aucun banc existant, projet neuf
- Manual: `npm install && npm test` => rc 0, 3 tests verts ; `npm run build -w api` => rc 0
- Manual: `npm run dev` puis `curl -s http://127.0.0.1:3000/api/health` => {"status":"ok","tables":49}, idem au 2e lancement (data/pglite persisté) ; `git status --porcelain data/` => vide ; `test -d data/pglite && test ! -e api/data` => rc 0 (racine, pas cwd)
- Manual: `git diff --exit-code c013e93 -- schema/` => rc 0 ; `node -p "Object.keys({...require('./api/package.json').dependencies,...require('./api/package.json').devDependencies}).sort().join()"` => @electric-sql/pglite,@types/node,drizzle-orm,fastify,typescript,vitest

## Rollback
- git revert -m 1 du merge de la branche api ; data/ supprimable (ignoré).

PREFLIGHT: à jouer par l’exécuteur

## Approval requested
Ready to hand off to dev-multi. Await user OK.
