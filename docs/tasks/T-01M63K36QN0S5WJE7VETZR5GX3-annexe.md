# Annexe — T-01M63K36QN0S5WJE7VETZR5GX3 (socle Graffard, partie racine)

## Mesures (base c013e93)
- `ls .agents/IS_THE_KIT` => absent : dépôt adoptant, pas de ligne `SQL:` (grammaire § 4).
- `grep spec= .agents/state/gates/PLAN_CIBLE_REQUIRED` => `spec=docs/PROMPT-projet.md`, `chantier=*` ; les trois cibles existent dans `docs/PROMPT-projet.md` (l. 18, 19, 22).
- `git check-ignore -v data/pglite/x dist/x node_modules/x` => seul `node_modules/` ignoré (`.gitignore:49`).
- `git ls-files | grep -E '(^|/)data/'` => fichiers suivis sous `.agents/vendor/cadre/data/` : `data/` non ancré les masquerait.
- `git ls-files | grep -cE '(^|/)dist/'` => 0.
- `node --version` => v24.14.0 ; `npm --version` => 11.9.0.

## Mutants
- Workspaces absents (copie hors dépôt, `workspaces ["api"]` sans `api/`) : `npm test` => `npm error No workspaces found!`.
- `/data/` réécrit en `data/` : `.agents/vendor/cadre/data/neuf.json` sortirait de `check-ignore` (déduit, non rejoué).
- Script ou clé changés dans `package.json` : la ligne `node -e` diffère.

## Non couvert
- `scripts/dev.mjs` sans test automatisé : `node --check` puis `npm run dev` manuel à l'intégration.
- Refus de `.cmd` sans shell sous Windows (Node ≥ 20, CVE-2024-27980) : non re-mesuré.
- Fichiers neufs hors index, aucun SYM-ID.

## Constats fermés (révision 2, après critic-1 NO_GO)
- C1 — étape 4 — `taskkill /pid <pid> /T /F` sans shell sous win32, `kill("SIGTERM")` ailleurs ; témoin (iii) manuel (netstat :3000/:5173 vide après Ctrl+C) ; mesure du critique reprise, non rejouée.
- C2 — étape 5 — install → commit lockfile → `security-orchestrator` (verdict tracé sur la tâche) → acceptation → `review-scope` → clôture → corrections (rejeu install/commit/SCA si un package.json bouge) → porte → `done`.
- C3 — contrat — routes `/api`, proxy sans réécriture vers `http://127.0.0.1:3000`, données depuis `import.meta.url` ; `git check-ignore api/data/pglite/x` => rc 1 (mesuré), ajouté au témoin, attendu non ignoré.
- C4 — contrat — aucun lockfile ni node_modules commité avant intégration ; installs locales `--no-package-lock`.
- C5 — Tests — trois témoins (i) rc 1 + message, (ii) rc 3, (iii) ports libres ; mutants : vérification retirée, `process.exit(0)` en dur, `child.kill()` sous win32.
- C6 — Rollback — `revert -m 1` de la fusion + `revert` du lockfile, coordonné entre les trois enfants.
- C7 — étape 4 cite `cible: « contrat déclaré »` ; `typescript` en devDependency de chaque workspace au contrat ; `erasableSyntaxOnly` retiré de la base (inconnue Vite/tsconfck), laissé à `api/tsconfig.json`.
