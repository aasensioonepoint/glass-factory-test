# Annexe — T-01M63K37YX42JH0T9JERBBDY0G
## Mesures (scratchpad hors dépôt ; node v24.14.0, npm 11.9.0 ; versions npm du 2026-10-29 : vite 8.3.5, vitest 5.0.5, vite-plugin-pwa 2.0.0, react/react-dom 19.3.1, typescript 7.0.2)
M1 — TSX sans @vitejs/plugin-react ni option esbuild : npx vitest run (renderToString, environment node) => « Tests 1 passed ». Vite 8 transforme par Oxc, JSX automatique par défaut.
M2 — tsconfig extends ../tsconfig.base.json absent : vitest run => vert ; vite build => « error during build ». Base présente : tsc --noEmit -p . => rc 0 ; vite build => rc 0.
M3 — vite build + VitePWA (manifest, 2 icônes) => dist/manifest.webmanifest, dist/sw.js, registerSW.js. Les PNG sont des fichiers binaires, produits une seule fois puis commités, sans script versionné :
  node --input-type=module -e "<script>" lancé depuis web/ ; script : import {deflateSync,crc32} from 'node:zlib' ; IHDR n×n, 8 bits, type 2 RGB ; chaque ligne = octet de filtre 0 + n×[0x14,0x2e,0x3b] ; IDAT = deflateSync(lignes) ; CRC = crc32(type+données) ; écrire public/icon-${n}.png pour n ∈ {192,512}
  => `file` : « PNG image data, 192 x 192 » (548 o) et « 512 x 512 » (1882 o).
M4 — Mutant : sur une copie du scratchpad, retirer <button>+ Ajouter</button> => « AssertionError: expected '<nav>…</nav>' to contain '+ Ajouter' », « Tests 1 failed ». Remis en place : vert.
M5 — Contrastes WCAG (calcul de luminance relative) : F5F2EB/142E3B 12,66 ; B89C63/142E3B 5,37 ; 56666D/F5F2EB 5,34 ; B89C63/F5F2EB 2,36 (interdit au texte).
## Grille de critique (auto-passe)
- index-fidelity : aucun symbole existant ; web/ est absent de l'arbre (ls => « No such file »). Les 12 chemins sont en SYM-new.
- constraint-compliance : aucune dépendance hors mandat. react-dom fait partie de React 19 et le mandat cite react-dom/server ; workbox est transitif. SQL sans objet (pas de .agents/IS_THE_KIT).
- Témoin : M4.
- Sites du motif : sans objet (création pure ; aucun motif corrigé ailleurs).
- Spec : six entrées et « + Ajouter » toujours visible (specification-fonctionnelle.md:108, :116) ; zones tactiles de 44 px (:179).
## Points signalés par le planner
- Chaîne JSX : Vite 8 compile par Oxc en runtime automatique, aucune option JSX (M1).
- Build seul avant la racine : rouge (M2), vérifié après fusion de racine.
- « + Ajouter » visible sans action : volontaire (panneau d'ajout = fonction métier hors socle).
