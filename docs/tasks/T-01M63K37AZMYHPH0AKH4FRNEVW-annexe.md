# Annexe — T-01M63K37AZMYHPH0AKH4FRNEVW (socle Graffard, partie api)

## Prémisses (base c013e93, mesurées par le planner dans un script jetable hors dépôt)
- P1 — `node m.mjs schema/graffard_racing_mcd_v0.sql` (pglite 0.5.13) => `tables 49` / `fks 80` / rc=0. En-tête SQL : « 49 tables, 287 columns, 80 foreign keys » ; `grep -ci 'create table'` => 49 ; ni BEGIN/COMMIT, ni extension, ni fonction.
- P2 — `node a.ts` (import `./b.ts` + `drizzle-orm/pglite`, `db.execute(sql\`…\`)`) => `1 [{"n":0}]` rc=0, sans avertissement.
- P3 — `node --version` => v24.14.0. Versions npm publiées : fastify 5.12.7, drizzle-orm 0.45.4, pglite 0.5.13.
- P4 — `plan_lots.py check` => `LIGNES: 41/45` `CHECK: ok`.
- `.agents/IS_THE_KIT` absent : pas de ligne `SQL:`.

## Mutants (un par cas du témoin api/src/routes/health.test.ts)
- M1 — liste des migrations vide => rouge « expected 0 to be 49 ».
- M2 — `migrations` créée dans `public` => rouge « expected 50 to be 49 ».
- M3 — migrate rejoue sans regarder l'appliqué => second migrate rouge « relation "cheval" already exists ».
- M4 — health renvoie 49 en dur => cas « avant migrate tables=0 » rouge.
- M5 — DATA_DIR depuis `process.cwd()` : pas de témoin automatique ; contrôle manuel `test ! -e api/data` (npm run dev -w api tourne avec api/ comme cwd).

## Non couvert
- Grille du critique non déroulée ligne par ligne (aucun SYM-ID existant, fichiers hors index).
