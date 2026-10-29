# Annexe — T-01M63K37YX42JH0T9JERBBDY0G

## Constats fermés (révision 2, après critic-1 NO_GO)
C1 — étape 1 / M2 — (réplique 12 fichiers + tsconfig.base.json racine r2, typescript 7.0.2) npx tsc --noEmit -p . => rc 0 ; même chose sans "types":["vite/client"] => « src/main.tsx(4,8): error TS2882: Cannot find module or type declarations for side-effect import of './styles.css'. » rc 1 ; npx vite build => « dist/manifest.webmanifest », « dist/sw.js », rc 0. Repli « ^5 » retiré ; typescript ^7.0.2 / vitest ^5.0.5 alignés sur api.
C2 — étape 7 — npx vitest run => « Tests 3 passed (3) » ; mutant sans aria-current => « AssertionError: Target cannot be null or undefined. » ; sans aria-pressed => « expected '<nav class="nav" aria-label="Main nav…' to match /lang="en" aria-pressed="true"/ » ; App en 'en' par défaut => « expected '<main class="main"><h1>Today</h1></ma…' to contain '<h1>Aujourd\'hui</h1>' » ; libellé « Plu » => « Tests 1 failed | 2 passed (3) » ; remis en place => « Tests 3 passed (3) ».
C3 — non fermé : réserve gardée ; défaut « no mockup: socle sans écran métier » à confirmer par le pilote ; aucune tâche créée.
C4 — étape 5 / INTERACTION — « + Ajouter » rendu FRÈRE de <nav> dans un fragment ; empilement : même contexte racine, z-index 20 > 10.
C5 — INTERACTION — anneau or retiré ; double anneau 3 px bleu nuit + 2 px ivoire : 142E3B/F5F2EB 12,66:1.
C6 — INTERACTION — largeurs, survol et focus clavier attribués à design-review ; le témoin couvre FR par défaut, EN, entrée active, langue pressée.
C7 — étape 8 / M3 — script exact ci-dessous => « PNG image data, 192 x 192, 8-bit/color RGB » et « 512 x 512 ».
C8 — annexe — vite-plugin-pwa@2.0.0 : workbox-build et workbox-window en peerDependencies ET dependencies (^7.4.1), installés sans déclaration (« added 364 packages », build PWA vert) ; typescript couvert par docs/mission2/DECISIONS.md:22 et par le contrat racine r2.

## Mesures (scratchpad hors dépôt ; node v24.14.0, npm 11.9.0 ; versions npm du 2026-10-29 : vite 8.3.5, vitest 5.0.5, vite-plugin-pwa 2.0.0, react/react-dom 19.3.1, typescript 7.0.2)
M1 — TSX sans @vitejs/plugin-react ni option esbuild : npx vitest run (renderToString, environment node) => « Tests 1 passed ». Vite 8 transforme par Oxc, JSX automatique par défaut.
M2 — réplique 12 fichiers + base racine r2 : npx tsc --noEmit -p . => rc 0 (TS 7.0.2) ; npx vitest run => « Tests 3 passed (3) » ; npx vite build => rc 0, dist/manifest.webmanifest + dist/sw.js. Sans ../tsconfig.base.json : vite build => « error during build ».
M3 — script PNG exact, lancé une fois depuis web/ (Node ≥ 22.2 pour zlib.crc32 ; mesuré v24.14.0) :
node --input-type=module -e "import{deflateSync,crc32}from'node:zlib';import{writeFileSync}from'node:fs';const ck=(t,d)=>{const b=Buffer.alloc(4);b.writeUInt32BE(d.length);const td=Buffer.concat([Buffer.from(t),d]);const c=Buffer.alloc(4);c.writeUInt32BE(crc32(td)>>>0);return Buffer.concat([b,td,c])};for(const n of[192,512]){const h=Buffer.alloc(13);h.writeUInt32BE(n,0);h.writeUInt32BE(n,4);h[8]=8;h[9]=2;const px=Buffer.alloc(1+3*n);for(let i=0;i<n;i++)px.set([0x14,0x2e,0x3b],1+3*i);writeFileSync('public/icon-'+n+'.png',Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),ck('IHDR',h),ck('IDAT',deflateSync(Buffer.concat(Array(n).fill(px)))),ck('IEND',Buffer.alloc(0))]))}"
=> file public/*.png : « PNG image data, 192 x 192, 8-bit/color RGB, non-interlaced » et « 512 x 512 ». Fichiers binaires, commités ; le script n'est pas versionné.
M4 — mutants : voir C2 ; plus tsconfig sans types vite/client => TS2882 (voir C1).
M5 — Contrastes WCAG : F5F2EB/142E3B 12,66 ; B89C63/142E3B 5,37 ; 56666D/F5F2EB 5,34 ; B89C63/F5F2EB 2,36 (interdit au texte et au focus).
