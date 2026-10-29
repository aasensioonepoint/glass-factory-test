# PLAN — socle Graffard, partie racine (T-01M63K36QN0S5WJE7VETZR5GX3) — révision 2

no mockup: partie racine sans écran
INTERACTION: sans objet | partie racine sans écran, aucun fichier d'interface dans le write-set

## Impacted symbols (by ID)
- `.gitignore` (modify) — hors index : aucun SYM-ID, fichier non indexé
- SYM-new `package.json` (create)
- SYM-new `package-lock.json` (create)
- SYM-new `tsconfig.base.json` (create)
- SYM-new `scripts/dev.mjs` (create)

## Contrat d'interface partagé (aligné sur les plans api T-01M63K37AZ et web T-01M63K37YX ; cible: « contrat déclaré »)
Racine `private`, `"type":"module"`, `workspaces ["api","web"]`, `engines.node ">=24"`, aucune dépendance ; scripts `dev` = `node scripts/dev.mjs`, `test` = `npm test --workspaces`, `build` = `npm run build --workspaces` ; chaque workspace porte `dev`/`test`/`build` et `typescript` en devDependency (son `build` lance `tsc --noEmit`, qui vérifie les options de la base).
API : routes préfixées `/api` (`/api/health`), écoute 127.0.0.1:PORT (défaut 3000) ; web :5173, proxy Vite `/api` SANS réécriture vers `http://127.0.0.1:3000` (pas `localhost` : ::1 possible sous Windows/Node 24) ; données `<repo>/data/pglite`, résolu depuis `import.meta.url`, jamais depuis le cwd.
`api/tsconfig.json` et `web/tsconfig.json` étendent `../tsconfig.base.json`. Avant intégration, aucun lockfile ni `node_modules` commité : installs locales des enfants en `--no-package-lock`, seule l'étape 5 écrit `package-lock.json`.

## Steps
1. Créer `package.json` racine selon le contrat — package.json — cible: « contrat déclaré »
2. Créer `tsconfig.base.json` : options strictes partagées seules (strict, noUncheckedIndexedAccess, isolatedModules, verbatimModuleSyntax, skipLibCheck, target ES2022) ; `module`/`moduleResolution`/`lib`/`jsx` aux workspaces — tsconfig.base.json — cible: « contrat déclaré »
3. Ajouter à `.gitignore` `/data/` (ANCRÉ : `.agents/vendor/cadre/data/` est suivi) et `dist/` ; `node_modules/` déjà couvert (l.49) — .gitignore — cible: « plan avant édition »
4. Créer `scripts/dev.mjs` : `spawn(process.execPath, [process.env.npm_execpath, "run", "dev", "-w", ws])` pour api puis web, stdio hérité, sans shell ; npm_execpath absent → stderr `dev.mjs : lancer par « npm run dev »`, exit 1 ; un enfant qui sort, ou SIGINT/SIGTERM, arrête l'autre — win32 : `spawn("taskkill", ["/pid", String(pid), "/T", "/F"], {stdio:"ignore"})` sans shell, ailleurs `kill("SIGTERM")` — et dev.mjs ne sort, avec le code du premier enfant sorti, qu'à l'`exit` (ou à l'`error`) du taskkill sous win32, jamais dans le même tick que son spawn (orphelin mesuré sinon, C8) — scripts/dev.mjs — cible: « contrat déclaré »
5. Après fusion de racine, api et web, AVANT `review-scope` : `npm install` racine → commit de `package-lock.json` sous cette tâche → `security-orchestrator` (SCA npm) sur ce lockfile, verdict tracé sur cette tâche → acceptation d'intégration → `review-scope` → revue de clôture → corrections (toute correction d'un `package.json` rejoue install, commit et SCA) → porte unique → `done` — package-lock.json — cible: « plan avant édition »

LOTS: aucun | 5 fichiers, sous le seuil de 6 ; le lockfile est généré à l'étape 5, jamais écrit à la main
ARÊTES: aucune
DÉPENDANCES HORS PLAN: ordre SUGGESTION racine, api, web (décision S-01M63K3VPZ0S8VQK9FE0VA35F0), aucun depends_on

## Risks
- `npm test` racine rouge tant que api/ ou web/ manquent (`No workspaces found!`, mesuré) → acceptation d'intégration jouée après les trois fusions seulement
- Lecture par `sca-scan.sh` d'un ENOLOCK (dégradé ou faux GO) → le SCA ne tourne qu'après le commit du lockfile (étape 5)
- Ctrl+C sous mintty non mesuré → témoin (iii) joué depuis le terminal du pilote ; aucune dépendance hors mandat ajoutée

## Tests
- racine — pas de témoin neuf (pas de runner à la racine) ; BANCS: aucun | contrôles par commandes ci-dessous
- `node -e "const p=require('./package.json');console.log(p.private,p.type,p.workspaces.join(),p.engines.node,p.scripts.dev,p.scripts.test,p.scripts.build)"` => `true module api,web >=24 node scripts/dev.mjs npm test --workspaces npm run build --workspaces`
- `git check-ignore data/pglite/x api/dist/x web/node_modules/x .agents/vendor/cadre/data/neuf.json api/data/pglite/x` => exactement les 3 premiers chemins (base commitée : seul `web/node_modules/x`)
- dev.mjs : (i) `env -u npm_execpath node scripts/dev.mjs; echo $?` => message de l'étape 4 puis `1` ; (ii) `npm_execpath=<script hors dépôt qui sort 3> node scripts/dev.mjs; echo $?` => `3` ; (iii) contrôle manuel : après Ctrl+C sur `npm run dev`, `netstat -ano | grep -E ':(3000|5173) .*LISTEN'` => vide ; (iv) clone jetable, workspaces stub a=`node -e "setInterval(()=>{},1000)"`, b=`node -e "setTimeout(()=>process.exit(3),3000)"` : `npm run dev; echo $?` => `3`, puis `powershell "(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | ? CommandLine -like '*setInterval*').Count"` => `0` ; mutants `process.exit` sans attente, `child.kill()` sous win32 => `1`
- Intégration : `npm install`, `npm test` => rc 0 ; `npm run build` => rc 0 ; `npm run dev` => :5173 affiche la nav, `curl -s localhost:5173/api/health` => `{"status":"ok","tables":49}`

## Rollback
- `git revert -m 1 <fusion racine>` + `git revert <commit lockfile>` ; retirer la racine laisse api/ et web/ sans workspace : rollback coordonné des trois enfants ; `data/`, `node_modules/` locaux supprimables

PREFLIGHT: à jouer par l’exécuteur

## Approval requested
Ready to hand off to dev-multi. Await user OK.
