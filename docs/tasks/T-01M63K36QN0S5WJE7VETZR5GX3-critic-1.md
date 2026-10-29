# plan-critic — T-01M63K36QN0S5WJE7VETZR5GX3 — itération 1/2 — NO_GO

Plan jugé : docs/tasks/T-01M63K36QN0S5WJE7VETZR5GX3-plan.md sha256=e17d99002b473b9ac760fa13aee489a8a9ec6b97851ef60cfcd2ffb5cf16b311

VERDICT: NO_GO
ITERATION: 1/2
CHECKLIST
  scope-fit             GO               plan:1-45. Préflight relayé rc 0, sha256 rejoué identique ; `plan_lots.py check` => `LIGNES: 35/45`, `CHECK: ok` ; `PREFLIGHT:` présente (l.42) ; `INTERACTION: sans objet` juste ; `LOTS: aucun` cohérent (5 chemins au board).
  index-fidelity        GO               plan:6-11. Aucun SYM-ID cité ; 4 `SYM-new` absents de la base.
  blast-radius          GO_AVEC_RESERVES plan:14, plan:28. `"type":"module"` ne casse rien (workflow-fournee.js déjà ESM, app.js navigateur) ; `porte_adoptant.py` replie les workspaces (`module_discovery.py:67`). Mais l.28 « aucun npm install dans les worktrees de lot » rend injouables les témoins vitest d'api et web. Voir C4.
  test-adequacy         GO_AVEC_RESERVES plan:36. Témoin `check-ignore` capable de rougir (mutant `/data/`→`data/`) ; `node -e` rejoue juste sous `"type":"module"`. `scripts/dev.mjs` n'a que `node --check` + manuel. Voir C5.
  rollback-viability    GO_AVEC_RESERVES plan:40. Au moins deux commits (fusion `--no-ff` => `revert -m 1`, commit du lockfile) ; sort d'api/ et web/ non dit. Voir C6.
  constraint-compliance NO_GO            plan:21. L'étape 5 fait entrer l'arbre de dépendances sans porte SCA. Voir C2.
  cost-realism          GO_AVEC_RESERVES plan:17-21. 5 fichiers = write-set du board ; FORECAST non relayé.
FINDINGS
  C1  blocking  step 4  Sous Windows, `child.kill()` sur npm laisse le petit-enfant vivant (mesuré : `npm exit null SIGTERM`, `tasklist` => node.exe 37316 vivant) ; un Vite orphelin garde :5173. Remède mesuré : `spawn("taskkill",["/pid",String(pid),"/T","/F"])` sans shell => 3 processus arrêtés. → Étape 4 : « arrêt de l'autre enfant : sous win32, `spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {stdio:"ignore"})` (sans shell) ; ailleurs, `child.kill("SIGTERM")` » + témoin d'orphelin (C5).
  C2  blocking  step 5  Le lockfile naît après les portes de sécurité des enfants ; aucun SCA possible avant lui (`npm audit --package-lock-only` => ENOLOCK rc 1, `sca-scan.sh:1245`) ; l'étape 5 ne nomme ni `security-orchestrator` ni `sca-scan.sh` et ne place pas le commit avant revue de clôture et porte (`porte_adoptant.py:629-631` rouge sans lockfile, puis `npm ci`). → « après fusion de racine, api et web : `npm install` → commit de `package-lock.json` → `security-orchestrator` (SCA npm) sur ce lockfile, verdict tracé sur cette tâche → acceptation d'intégration (l.37) → `review-scope` puis revue de clôture → porte unique → `done` ; toute correction qui touche un `package.json` rejoue `npm install`, le commit et le SCA avant la porte ».
  C3  concern   contrat (l.14)  (a) proxy `/api` réécrit ou non ? route `/api/health` ou `/health` ? (b) `<repo>/data/pglite` vs cwd `api/`. → « routes API préfixées `/api`, proxy Vite sans réécriture vers `http://127.0.0.1:3000` ; chemin des données résolu depuis la racine du dépôt » ; ajouter `api/data/pglite/x` au témoin `check-ignore`, attendu NON ignoré.
  C4  concern   Risks l.28  Règle « aucun npm install dans les worktrees » absente du contrat ; témoins vitest injouables. → Porter au contrat : tests des enfants dans un clone jetable `/tmp/cadre-*` qui reçoit le `package.json` racine du contrat ; jamais de lockfile ni `node_modules` commités hors étape 5.
  C5  concern   Tests l.36  `node --check` ne rougit que sur la syntaxe. → Trois témoins : (i) `env -u npm_execpath node scripts/dev.mjs` => rc 1 ET message exact ; (ii) `npm_execpath=<script qui sort 3> node scripts/dev.mjs` => rc 3 ; (iii) petit-enfant absent de `tasklist` après sortie d'un enfant.
  C6  concern   Rollback l.40  → « `git revert -m 1 <fusion racine>` + `git revert <commit lockfile>` ; retirer la racine laisse api/ et web/ sans workspace : rollback coordonné des trois enfants ; `data/` et `node_modules/` locaux supprimables ».
  C7  concern   step 4 / step 2  (1) S-01M63K3VPZ0S8VQK9FE0VA35F0 ne justifie pas la conception de dev.mjs → `cible: « contrat déclaré »`. (2) Options strictes non vérifiées si typescript absent → « options lues par l'éditeur seulement » ou `angle mort: autoriser typescript en devDependency ?`.
STRONGEST OBJECTION: Le lockfile, donc toutes les dépendances du socle, sort du flux normal du kit vers une étape d'intégration sans critique ni SCA nommés.
UNKNOWNS: (1) lecture par `sca-scan.sh` du JSON ENOLOCK (dégradé ou faux GO) ; (2) tolérance de Vite/tsconfck à `erasableSyntaxOnly` et à l'`extends` ; (3) plans api et web non lus ; (4) Ctrl+C sous mintty ; (5) FORECAST non relayé.
CAUSE_RACINE: PAS_DE_VERIFICATION
LECON_CANDIDATE: Un artefact généré à l'intégration hérite des portes du flux qu'il contourne : son plan nomme le SCA ou le critique qui le juge, et le place avant la porte unique.
NEXT: planner-revise
