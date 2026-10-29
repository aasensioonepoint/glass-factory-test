# PLAN — T-01M63K37YX42JH0T9JERBBDY0G — socle web : PWA React vide aux couleurs Graffard (révision 2)

## Impacted symbols (by ID) — dépôt sans web/ : tout est créé, aucun SYM existant touché
- SYM-new `web/package.json` (create)
- SYM-new `web/tsconfig.json` (create)
- SYM-new `web/vite.config.ts` (create)
- SYM-new `web/index.html` (create)
- SYM-new `web/src/main.tsx` (create)
- SYM-new `web/src/App.tsx` (create)
- SYM-new `web/src/i18n.ts` (create)
- SYM-new `web/src/styles.css` (create)
- SYM-new `web/src/components/Navigation.tsx` (create)
- SYM-new `web/src/components/Navigation.test.tsx` (create)
- SYM-new `web/public/icon-192.png` (create)
- SYM-new `web/public/icon-512.png` (create)

no mockup: socle sans écran métier, seule la coque (maquettes du .docx réservées aux tâches métier)
INTERACTION: focus=ordre DOM nav (6 entrées) puis FR/EN puis « + Ajouter », double anneau :focus-visible (3 px bleu nuit + 2 px ivoire, 12,66:1 sur les deux fonds), l'entrée choisie reste focalisée ; echap=sans effet, aucune couche ouverte ; modal=aucune (panneau « + Ajouter » hors socle) ; empilement=nav fixe z-index 10, « + Ajouter » frère de la nav (hors de la barre), fixe, z-index 20, même contexte racine ; wcag=1.4.3 contraste (ivoire/bleu nuit 12,66, or/bleu nuit 5,37, gris/ivoire 5,34, or sur ivoire 2,36 banni du texte et du focus), 1.4.11 focus 3:1, 2.4.7, 2.5.8 cible 44 px, 4.1.2 aria-current/aria-pressed, 3.1.1 html lang ; largeurs=360, 768, 1280 px (design-review) ; etats=FR par défaut, EN, entrée active, langue pressée (témoin) puis survol et focus clavier (design-review)

## Steps
1. Créer web/package.json (deps react, react-dom ^19.3.1 ; dev typescript ^7.0.2, vitest ^5.0.5, vite ^8.3.5, vite-plugin-pwa ^2.0.0, @types/react, @types/react-dom ^19 ; scripts dev=vite, test=vitest run, build=tsc --noEmit -p . && vite build) et web/tsconfig.json (extends ../tsconfig.base.json ; jsx react-jsx, lib ES2022+DOM, module ESNext, moduleResolution bundler, types ["vite/client"], noEmit ; include src, vite.config.ts) — cible: « contrat déclaré »
2. Créer web/vite.config.ts (defineConfig de vitest/config ; VitePWA manifest nom, lang fr, theme #142E3B, fond #F5F2EB, standalone, 2 icônes ; server 5173 strictPort, proxy '/api' → http://127.0.0.1:3000 sans réécriture ; test environment node ; aucune option JSX, M1) — cible: « contrat déclaré »
3. Créer web/index.html (lang fr, viewport-fit=cover, theme-color) et web/src/main.tsx (createRoot + StrictMode + App, import './styles.css') — cible: « plan avant édition »
4. Créer web/src/i18n.ts : Lang 'fr'|'en', NAV_KEYS (today…more), dictionnaire manuel (Aujourd'hui/Today, Planning, Chevaux/Horses, Santé/Health, Courses/Races, Plus/More, « + Ajouter »/« + Add »), t(lang, clé) — cible: « plan avant édition »
5. Créer Navigation.tsx (fragment : nav aria-label, 6 boutons data-nav + aria-current, groupe FR/EN lang + aria-pressed ; puis bouton « + Ajouter » FRÈRE de la nav, sans action métier) et App.tsx (lang 'fr', entrée 'today', h1 de section, documentElement.lang) — cible: « plan avant édition »
6. Créer web/src/styles.css : variables palette, mobile-first barre basse, barre haute dès 768 px, cibles min 44 px, safe-area, double anneau de focus — cible: « plan avant édition »
7. Créer Navigation.test.tsx, 3 it en renderToString (env node) : libellés FR + « + Ajouter » ; libellés EN + « + Add » ; aria-current unique sur horses, aria-pressed EN true / FR false, App FR sur Aujourd'hui — cible: « tests au plus près du code »
8. Produire les deux PNG binaires (aplat #142E3B) par le one-off node:zlib exact de l'annexe M3, jamais versionné — cible: « zéro boîte noire »

LOTS: aucun | décision pilote: S-01M63K3VPZ0S8VQK9FE0VA35F0 — enfant web gardé entier ; main→App→Navigation→i18n couplés
ARÊTES: aucune

## Risks
- Avant fusion racine, base tsconfig absente : build web rouge (M2) → build après fusion ; installs `npm install --no-package-lock`, ni lock ni node_modules commité
- TS 7.0.2 sans types vite/client : TS2882 sur import './styles.css' (C1, mesuré) → types ["vite/client"] au tsconfig, même majeure TS/vitest que api
- Revert de web/ seul casse workspaces racine → rollback coordonné avec T-01M63K36QN0S5WJE7VETZR5GX3
- Maquettes du .docx non reproduites (C3) : défaut « no mockup » à confirmer par le pilote à la porte

## Tests
- web (parent) — témoin neuf web/src/components/Navigation.test.tsx ; BANCS: aucun | aucun banc existant sous web/
- Acceptation : npm test -w web => « Tests 3 passed (3) » ; npm run build -w web => « dist/manifest.webmanifest » et « dist/sw.js » ; npm run dev puis http://localhost:5173 => 6 entrées, « + Ajouter », bascule FR/EN
- Mutants (M4) : sans aria-current, sans aria-pressed, lang 'en' par défaut, libellé « Plu » => chacun « Tests 1 failed » ; sans types vite/client => TS2882

## Rollback
- Commit de revert de web/, avec retrait de "web" des workspaces côté racine.

PREFLIGHT: à jouer par l’exécuteur

## Approval requested
Ready to hand off to frontend-fidelity (puis design-review). Await user OK.
