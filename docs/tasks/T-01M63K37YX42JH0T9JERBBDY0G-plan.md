# PLAN — T-01M63K37YX42JH0T9JERBBDY0G — socle web : PWA React vide aux couleurs Graffard

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
INTERACTION: focus=ordre DOM nav (6 entrées) puis FR/EN puis « + Ajouter », anneau :focus-visible or doux 3 px, l'entrée choisie reste focalisée ; echap=sans effet, aucune couche ouverte ; modal=aucune (panneau « + Ajouter » hors socle) ; empilement=barre nav z-index 10, bouton « + Ajouter » flottant z-index 20 au-dessus du contenu, hors de la barre ; wcag=1.4.3 contraste (ivoire/bleu nuit 12,66, or/bleu nuit 5,37, gris/ivoire 5,34, or sur ivoire 2,36 interdit au texte), 2.4.7 focus visible, 2.5.8 cible 44 px, 4.1.2 aria-current/aria-pressed, 3.1.1 html lang suivi ; largeurs=360, 768, 1280 px ; etats=FR par défaut, EN, entrée active, survol, focus clavier

## Steps
1. Créer web/package.json (react+react-dom 19 ; dev : vite 8, vite-plugin-pwa 2, vitest 5, typescript, @types/react, @types/react-dom ; scripts dev=vite, test=vitest run, build=tsc --noEmit -p . && vite build), web/tsconfig.json (extends ../tsconfig.base.json ; jsx react-jsx, lib DOM, module ESNext, moduleResolution bundler) — cible: « contrat déclaré »
2. Créer web/vite.config.ts (defineConfig de vitest/config ; VitePWA manifest nom, theme #142E3B, fond #F5F2EB, standalone, 2 icônes ; server 5173 strictPort, proxy /api → http://localhost:3000 ; test environment node ; aucune option JSX : Vite 8 compile en runtime automatique, mesuré annexe M1) — cible: « contrat déclaré »
3. Créer web/index.html (lang fr, viewport, theme-color) et web/src/main.tsx (createRoot + StrictMode + App, import styles.css) — cible: « plan avant édition »
4. Créer web/src/i18n.ts : type Lang 'fr'|'en', dictionnaire manuel (Aujourd'hui/Today, Planning, Chevaux/Horses, Santé/Health, Courses/Races, Plus/More, « + Ajouter »/« + Add »), t(lang, clé) — cible: « plan avant édition »
5. Créer web/src/components/Navigation.tsx (nav aria-label, 6 boutons data-nav + aria-current, groupe FR/EN aria-pressed, bouton « + Ajouter » sans action métier) et web/src/App.tsx (état lang et entrée, titre de section seul, document.documentElement.lang) — cible: « plan avant édition »
6. Créer web/src/styles.css : variables palette, mobile-first barre basse, barre haute dès 768 px, cibles min 44 px, safe-area — cible: « plan avant édition »
7. Créer le témoin colocalisé Navigation.test.tsx (renderToString, env node : 6 entrées, « + Ajouter », libellés FR puis EN, deux it) — cible: « tests au plus près du code »
8. Produire les deux PNG binaires (aplat #142E3B) par un one-off node:zlib (deflateSync + crc32, Node ≥ 22.2, mesuré v24) écrit en annexe M3, jamais versionné — cible: « zéro boîte noire »

LOTS: aucun | décision pilote: S-01M63K3VPZ0S8VQK9FE0VA35F0 — enfant web gardé entier ; main→App→Navigation→i18n couplés
ARÊTES: aucune

## Risks
- web/ seul (racine non fusionnée) : vite build ROUGE (base tsconfig absente, mesuré M2), vitest vert → build vérifié après fusion racine ; npm install --no-package-lock dans web/, aucun lock ni node_modules commité
- renderToString échappe l'apostrophe (Aujourd&#x27;hui) → le témoin compte data-nav et compare au texte décodé
- react-dom non nommé au mandat mais imposé par React 19 et par react-dom/server qu'il cite ; workbox-* viennent transitivement de vite-plugin-pwa ; TypeScript 7 résolu par npm → si tsc casse, épingler ^5 (dev)
- Contrat partagé : scripts dev/test/build, port 5173 strictPort, proxy /api → 3000, extends ../tsconfig.base.json (racine) ; lock à l'intégration

## Tests
- web (parent) — témoin neuf web/src/components/Navigation.test.tsx ; BANCS: aucun | aucun banc existant sous web/
- Acceptation : npm test -w web => « Tests 2 passed » ; npm run build -w web => dist/manifest.webmanifest + dist/sw.js ; npm run dev -w web puis http://localhost:5173 => 6 entrées, « + Ajouter », bascule FR/EN
- Mutant (annexe M4) : retirer « + Ajouter » de Navigation => « AssertionError … to contain '+ Ajouter' »

## Rollback
- Supprimer web/ (création pure) par commit de revert tracé.

PREFLIGHT: à jouer par l’exécuteur

## Approval requested
Ready to hand off to frontend-fidelity (puis design-review). Await user OK.
