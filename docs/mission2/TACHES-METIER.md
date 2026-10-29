# Graffard Racing — Tâches métier après le socle (D2-A, puis D2-C si le temps)

> Branche `mission2`. Socle livré : `api/` (Fastify 5, PGlite, migrateur maison), `web/` (React 19 PWA, 6 entrées, FR/EN).
> Arbitrages appliqués : D2 = A puis C ; D4 = A ; D5 à D9 = recommandations ; D10 = règle retenue (`DECISIONS.md` § Récapitulatif).
> Toutes les tâches tiennent en **5 fichiers au plus**, en chemins exacts, sans chemin de garde : elles visent `tasks.py direct`.
> Aucune dépendance nouvelle : `node:crypto` suffit pour le jeton signé.

## 0. À régler AVANT de lancer

### Questions au pilote — tranchées le 2026-10-29 : **Q1 = oui** (ajouter `produit.delai_retrait_jours`), **Q2 = N = 30 jours**

| # | Question | Bloque | Proposition |
|---|---|---|---|
| **Q1** | Le MCD porte `delai_retrait_jours` sur `acte_sante`, pas sur `produit`. D10 dit « administration + `delai_retrait_jours` **du produit** » et « produit sans délai renseigné ». On ajoute `produit.delai_retrait_jours` ? | **T1** (schéma) | **Oui** : ajout dans la migration 0002. `acte_sante.delai_retrait_jours` reste la copie figée au moment de l'acte (§7 : protocoles versionnés). |
| **Q2** | D10 : « statut inconnu = rien depuis **N** jours ». Quelle valeur pour N ? | **T4** (règle) | N = 30, en constante nommée et affichée comme hypothèse dans la démo. |

Tant que Q1 ou Q2 reste ouverte, la tâche qu'elle bloque ne prend pas la voie directe (le critère C3 de `direct` ne voit pas une question non écrite au titre : la règle est de ne rien supposer).

### Hypothèses non bloquantes (écrites dans `schema/DATA_MODEL.md` par T1)
- **H1 — D8.** Les colonnes communes (`auteur_id`, `date_reelle`, `date_reception`, `source`, `statut`) portent sur les tables du périmètre A seulement : `ration`, `acte_sante`, `administration`, `engagement`, et les nouvelles `restriction`, `mesure`, `regime_special`.
- **H2 — D10.** Six personas : les cinq de D4, plus **entraîneur**, parce que D10 lui donne le droit de lever une restriction.
- **H3 — D13 non tranché.** Pas de hors ligne en A : C9 n'est pas couvert. `COMMANDE_SYNC` sert seulement de clé d'idempotence aux confirmations.
- **H4 — Lots (D2-C).** L'avertissement « restriction → lot » de D10 part avec le défi B.

### P0 — Extraire les maquettes (exécuteur, hors chaîne, 2 min)
Le `.docx` est une archive zip. Commande :
`mkdir -p docs/mission2/maquettes && unzip -j -o "docs/mission2/GRAFFARD RACING-specification fonctionnelle V0.docx" "word/media/*" -d docs/mission2/maquettes/`
Ensuite, nommer chaque image selon sa section (§6.2, §6.3, §6.5) et remplacer `<§6.x>` dans les lignes `mockup:` ci-dessous par le chemin exact.
**Sans P0**, chaque tâche UI porte `mockup not reproduced: docs/mission2/GRAFFARD RACING-specification fonctionnelle V0.docx §6.x + <T-P0>`, et P0 doit exister au board.

## 1. Vue d'ensemble — deux couloirs disjoints

| Tâche | Couloir | Titre | Fichiers | depends_on | UI | Estim. |
|---|---|---|---|---|---|---|
| T1 | api | Schéma 0002 : lot sans heure, tables santé et traçabilité | 5 | — (Q1) | non | 35 min |
| T2 | api | Données de démonstration fictives | 3 | T1 | non | 25 min |
| T3 | api | Connexion par persona de démonstration | 5 | T1 | non | 35 min |
| T4 | api | Restriction de retrait et soins à confirmer | 4 | T1, T3 (Q2) | non | 40 min |
| T5 | api | Engagement bloqué sous restriction | 2 | T4 | non | 25 min |
| T6 | api | Checklist de nourrissage par exception | 2 | T1, T3 | non | 30 min |
| T7 | api | Dossier cheval filtré par rôle | 2 | T1, T3 | non | 30 min |
| TA | api | Branchement des routes métier et parcours de démo | 2 | T2, T4, T5, T6, T7 | non | 25 min |
| W1 | web | Sélecteur de profil de démonstration | 5 | — | **oui** | 35 min |
| W2 | web | Écran nourrissage | 2 | W1 | **oui** | 30 min |
| W3 | web | Écran dossier cheval | 2 | W1 | **oui** | 30 min |
| W4 | web | Écran santé : soins et levée de restriction | 2 | W1 | **oui** | 35 min |
| W5 | web | Écran courses : validation d'engagement | 2 | W1 | **oui** | 25 min |
| TW | web | Branchement des écrans dans l'application | 2 | W2, W3, W4, W5 | **oui** | 25 min |

**Vagues** (les write-sets sont disjoints à l'intérieur d'une vague ; à prouver par `tasks.py writeset` puis `tasks.py parallel` dans chaque clone) :
- **V1** : T1 ∥ W1
- **V2** : T2 ∥ T3 ∥ W2 ∥ W3 ∥ W4 ∥ W5
- **V3** : T4 ∥ T6 ∥ T7
- **V4** : T5
- **V5** : TA ∥ TW

**Deux clones.** Claude Code prend le couloir `api/`, Copilot le couloir `web/`. Aucun fichier n'est commun aux deux.
- Copilot joue ses lots **en série** : le parallélisme par worktree n'est mesuré que sur Claude Code.
- Un pilote ne prend jamais une tâche de l'autre couloir (propriété `start_actor`).
- Le web code contre le **contrat déclaré** dans chaque demande. L'intégration réelle est prouvée par TA et TW.

**Pourquoi ce découpage.** Trois fichiers sont partagés :
- `api/src/routes/health.test.ts` (compte de tables) et `api/src/db/migrate.ts` (liste des migrations) : toute migration les touche, donc les migrations sont **sérialisées** ;
- `api/src/app.ts` : seuls T3 et TA le touchent ;
- `web/src/App.tsx` : seuls W1 et TW le touchent.

Chaque route ou écran se teste seul : une instance Fastify nue pour l'API, `renderToString` pour le web.

---

## 2. Couloir API

### T1 — Schéma 0002 : lot sans heure, tables santé et traçabilité
- **Write-set** :
  - `api/src/db/migrations/0002_schema_mission2.ts`
  - `api/src/db/migrations/0002_schema_mission2.test.ts`
  - `api/src/db/migrate.ts`
  - `api/src/routes/health.test.ts`
  - `schema/DATA_MODEL.md`
- **Cibles** : « lot sans heure », « correction tracée », « prévu ≠ réalisé », « synchronisation idempotente », « aucune suppression sans trace », « contrat déclaré », « tests au plus près du code »
- **depends_on** : — (attend **Q1**) · **UI** : non · **Estim.** 35 min

**Demande `/kickoff`** :
> **Objectif** — Ajouter la migration `0002_schema_mission2`, appliquée après `0001_mcd_v0`, qui met en œuvre D5, D6, D8 et D9 (retenus) :
> - **D5** : `lot` perd `heure`, gagne `ordre_passage integer NOT NULL` et une contrainte `UNIQUE (libelle, lieu_id, date)` (numéro, cour, date du programme).
> - **D6** : tables `restriction` (`cheval_id`, `source` CHECK administration|examen|manuel, `source_id`, `debut`, `fin_prevue`, `statut` CHECK active|levee, `validateur_id`, `leve_par_id`, `leve_le`, `motif_levee`, et CHECK : levée ⇒ `leve_par_id`, `leve_le` et `motif_levee` non nuls), `mesure`, `regime_special`, selon `DECISIONS.md` § D6.
> - **Q1** : `produit.delai_retrait_jours integer` (nullable : NULL = délai inconnu).
> - **D8** : table `audit` (objet, objet_id, avant jsonb, apres jsonb, motif, auteur_id, horodatage) et table `commande_sync` (`id_commande text UNIQUE`, statut, accuse, erreur, recu_le). Colonnes communes `auteur_id`, `date_reelle`, `date_reception`, `source`, `statut` sur les tables de H1.
> - **D9** : type `statut_enregistrement` ENUM (brouillon, valide, publie, realise, annule, corrige), utilisé par ces colonnes `statut`. « En retard » n'est PAS stocké : il est calculé.
> - Enregistrer la migration dans `MIGRATIONS` et documenter chaque changement dans `schema/DATA_MODEL.md` (une ligne par arbitrage, H1 compris).
>
> **Hors périmètre** — `PROGRAMME` (D7, D2-C), `CONFLIT` (D8, hors ligne), toute route, toute donnée de démo. `schema/graffard_racing_mcd_v0.sql` n'est jamais modifié.
>
> **Contraintes** — Le SQL vit inline dans le `.ts`, comme `0001`. Ajout en fin de liste, jamais de réordonnancement. La migration est transactionnelle, comme le migrateur. Les colonnes `statut` existantes en `text` sont converties sans perte (`USING`) ou laissées en place et doublées : le choix est écrit dans DATA_MODEL.
>
> **Attendu** — Après `migrate` : 54 tables dans `public` (49 + 5). `INSERT` d'un `lot` avec `heure` → erreur. Doublon (libelle, lieu, date) → violation d'unicité. Restriction `levee` sans motif → violation de CHECK. Second `migrate` → `[]`.
>
> **Pour vérifier**
> - `npm -w api test` → rc 0, `Test Files` tous `passed`, 0 `failed` ; `health.test.ts` attend `tables: 54` et `['0001_mcd_v0','0002_schema_mission2']`
> - `npm -w api run build` → rc 0, aucune sortie d'erreur tsc
> - `git grep -n "heure" api/src/db/migrations/0002_schema_mission2.ts` → seulement le `DROP COLUMN heure`

### T2 — Données de démonstration fictives
- **Write-set** :
  - `api/src/db/seed.ts`
  - `api/src/db/seed.test.ts`
  - `api/src/server.ts`
- **Cibles** : « droits côté serveur », « prévu ≠ réalisé », « aucun secret au dépôt », « tests au plus près du code »
- **depends_on** : T1 · **UI** : non · **Estim.** 25 min · **Parallèle** avec T3

**Demande `/kickoff`** :
> **Objectif** — `seed(client)` idempotent, appelé par `server.ts` après `migrate` quand la table `compte` est vide. Il crée des données **entièrement fictives** :
> - 1 écurie, 2 cours (`lieu` de type cour) ;
> - 6 acteurs avec leur compte et une habilitation, rôles `entraineur`, `assistant_entraineur`, `cavalier`, `veterinaire`, `charge_engagements`, `proprietaire` (libellés EXACTS : T3 les lit) ;
> - 6 chevaux, dont 2 détenus par le propriétaire et 2 affectés au cavalier ;
> - 3 produits : un avec délai de 7 j, un avec délai de 2 j, un sans délai (NULL) ;
> - 2 régimes spéciaux ;
> - des administrations planifiées (`statut = valide`) : une échue (pour « en retard »), une du jour ;
> - 1 course dans 3 jours, avec un engagement en brouillon sur un cheval qui sera traité.
>
> **Hors périmètre** — Les routes, toute donnée réelle (aucun nom réel de personne ni de cheval).
>
> **Contraintes** — Pas de mot de passe ni de clé dans le seed. Un second appel n'insère rien.
>
> **Attendu** — Comptes : 6 par rôle distinct. Second `seed` → mêmes comptes.
>
> **Pour vérifier**
> - `npm -w api test -- src/db/seed.test.ts` → rc 0, tous `passed`
> - `npm -w api run build` → rc 0

### T3 — Connexion par persona de démonstration
- **Write-set** :
  - `api/src/auth/session.ts`
  - `api/src/auth/session.test.ts`
  - `api/src/routes/session.ts`
  - `api/src/routes/session.test.ts`
  - `api/src/app.ts`
- **Cibles** : « droits côté serveur », « aucun secret au dépôt », « contrat déclaré », « tests au plus près du code »
- **depends_on** : T1 · **UI** : non · **Estim.** 35 min · **Parallèle** avec T2 · `security-code-review` est obligatoire sur ce diff

**Demande `/kickoff`** :
> **Objectif** — D4-A, comptes de démo par persona.
> - `auth/session.ts` : jeton signé HMAC-SHA256 avec `node:crypto`, format `base64url(payload).base64url(mac)`, payload `{compteId, exp}`, durée 12 h, comparaison en temps constant (`timingSafeEqual`).
> - La clé vient de `GRAFFARD_CLE_SIGNATURE` ; si elle est absente, une clé aléatoire est tirée au démarrage (jetons perdus au redémarrage, assumé). Aucune clé n'est écrite au dépôt.
> - `registerAuth(app, db)` : hook qui pose `request.compte = {compteId, acteurId, roles[]}`. Les rôles sont **relus en base** (habilitation → role), jamais lus depuis le jeton.
> - `requireRole(...roles)` : preHandler qui renvoie 401 sans jeton valide et 403 si le rôle manque.
> - Routes :
>   - `GET /api/personas` → `[{compteId, nom, role}]`
>   - `POST /api/session {compteId}` → `{jeton, compte}`
>   - `GET /api/moi`
> - Brancher `registerAuth` et `registerSession` dans `app.ts`.
>
> **Hors périmètre** — Mots de passe, OIDC (D4-B), les routes métier.
>
> **Contraintes** — Pas de dépendance nouvelle. Les tests insèrent leurs propres comptes : ils ne dépendent pas de T2. Libellés de rôles exactement ceux de T2.
>
> **Attendu** — Jeton altéré d'un octet → 401. Jeton expiré → 401. `requireRole('veterinaire')` avec le cavalier → 403.
>
> **Pour vérifier**
> - `npm -w api test -- src/auth src/routes/session.test.ts` → rc 0, tous `passed`
> - `npm -w api test` → rc 0 (`health.test.ts` reste vert)
> - `git grep -nE "GRAFFARD_CLE_SIGNATURE=|cle.*=.*['\"][A-Za-z0-9+/]{16,}" -- api` → aucune sortie

### T4 — Restriction de retrait et soins à confirmer
- **Write-set** :
  - `api/src/domain/restriction.ts`
  - `api/src/domain/restriction.test.ts`
  - `api/src/routes/sante.ts`
  - `api/src/routes/sante.test.ts`
- **Cibles** : « aucun engagement sous restriction », « prévu ≠ réalisé », « correction tracée », « droits côté serveur », « contrat déclaré »
- **depends_on** : T1, T3 (attend **Q2**) · **UI** : non · **Estim.** 40 min · **Parallèle** avec T6, T7

**Demande `/kickoff`** :
> **Objectif** — Règle D10 et C6.
>
> Fonctions pures dans `domain/restriction.ts` :
> - `finRetrait(dateAdmin, delaiJours) = dateAdmin + delaiJours` ;
> - `eligibilite(chevalId, maintenant, faits)` → `{eligible: boolean, motifs: [{type: 'restriction_active'|'statut_inconnu', detail, source}]}`.
>   - Une restriction `active` bloque, **même si `fin_prevue` est dépassée**.
>   - Statut inconnu = un produit administré sans délai renseigné, OU aucun acte santé depuis `N_JOURS_STATUT_INCONNU` (= valeur de Q2, constante exportée).
> - `statutSoin(adm, maintenant)` → `a_faire` | `en_retard` | `realise`. « Réalisé » n'est rendu que si l'administration est confirmée.
>
> Routes de `routes/sante.ts`, exportées par `registerSante(app, db)` :
> - `GET /api/soins?date=` → administrations avec leur statut calculé.
> - `POST /api/administrations/:id/confirmer` (veterinaire, entraineur, assistant_entraineur ; en-tête `Idempotency-Key` enregistré dans `commande_sync`) → passe à `realise`, crée une `restriction` (`source = administration`, `fin_prevue = finRetrait`) si le délai est > 0. Un délai NULL est signalé comme statut inconnu, sans restriction inventée.
> - `POST /api/restrictions/:id/lever {motif}` (veterinaire, entraineur ; motif non vide obligatoire) → `statut = levee` et une ligne `audit` avec avant, après et motif.
> - `GET /api/chevaux/:id/eligibilite`.
>
> **Hors périmètre** — L'engagement (T5), le branchement dans `app.ts` (TA), l'avertissement sur les lots (D2-C).
>
> **Contraintes** — Les tests montent un `Fastify()` nu avec `registerAuth` et `registerSante`. Aucune levée automatique par date. Un second POST avec la même `Idempotency-Key` → même réponse, aucune seconde restriction.
>
> **Attendu** — Cavalier qui lève → 403. Levée sans motif → 400. Restriction à `fin_prevue` passée → toujours `eligible:false`. Administration non confirmée et échue → `en_retard`.
>
> **Pour vérifier**
> - `npm -w api test -- src/domain/restriction.test.ts src/routes/sante.test.ts` → rc 0, tous `passed`
> - `npm -w api run build` → rc 0

### T5 — Engagement bloqué sous restriction
- **Write-set** :
  - `api/src/routes/courses.ts`
  - `api/src/routes/courses.test.ts`
- **Cibles** : « aucun engagement sous restriction », « droits côté serveur », « prévu ≠ réalisé »
- **depends_on** : T4 · **UI** : non · **Estim.** 25 min

**Demande `/kickoff`** :
> **Objectif** — C7, exporté par `registerCourses(app, db)` :
> - `GET /api/engagements` → avec l'éligibilité de chaque cheval (`eligibilite` de T4).
> - `POST /api/engagements/:id/valider` (charge_engagements, entraineur) → 409 `{bloque: true, motifs: [...]}` si le cheval n'est pas éligible ; sinon `statut = valide`, `resultat_controle` et `date_controle` renseignés. Le statut officiel reste distinct (§7 : un engagement local ne remplace jamais l'organisme).
>
> **Hors périmètre** — Transport, résultats, connecteur France Galop, branchement.
>
> **Contraintes** — Réutiliser `domain/restriction.ts`, sans dupliquer la règle.
>
> **Attendu** — Restriction active → 409 et justification lisible. Après levée → 200. Statut inconnu → 409.
>
> **Pour vérifier**
> - `npm -w api test -- src/routes/courses.test.ts` → rc 0, tous `passed`

### T6 — Checklist de nourrissage par exception
- **Write-set** :
  - `api/src/routes/nourrissage.ts`
  - `api/src/routes/nourrissage.test.ts`
- **Cibles** : « saisie par exception », « prévu ≠ réalisé », « synchronisation idempotente », « droits côté serveur »
- **depends_on** : T1, T3 · **UI** : non · **Estim.** 30 min · **Parallèle** avec T4, T7

**Demande `/kickoff`** :
> **Objectif** — Défi A et C4, exporté par `registerNourrissage(app, db)` :
> - `GET /api/nourrissage?date=&repas=&cour=` → chevaux de la cour, avec leur régime spécial actif et leur état (`a_confirmer` | `normal` | `ecart`).
> - `POST /api/nourrissage/confirmer {date, repas, cour}` → **une seule action** : une `ration` `part_consommee = totale` pour chaque cheval encore `a_confirmer`.
> - `POST /api/nourrissage/ecart {chevalId, date, repas, part: refus|partielle|anomalie, remarque?}` → la remarque est **facultative**.
> - Les deux POST exigent `Idempotency-Key`. Auteur, date réelle et réception sont préremplis depuis la session.
>
> **Hors périmètre** — Hors ligne (D13 non tranché), branchement.
>
> **Contraintes** — Un cheval non confirmé n'est jamais compté « normal ». Un écart déjà saisi n'est pas écrasé par la confirmation globale.
>
> **Attendu** — Rejouer la même clé → aucun doublon de `ration`. Écart sans remarque → 201.
>
> **Pour vérifier**
> - `npm -w api test -- src/routes/nourrissage.test.ts` → rc 0, tous `passed`

### T7 — Dossier cheval filtré par rôle
- **Write-set** :
  - `api/src/routes/chevaux.ts`
  - `api/src/routes/chevaux.test.ts`
- **Cibles** : « droits côté serveur », « contrat déclaré »
- **depends_on** : T1, T3 · **UI** : non · **Estim.** 30 min · **Parallèle** avec T4, T6

**Demande `/kickoff`** :
> **Objectif** — Palier 1, C3 et C12, exporté par `registerChevaux(app, db)` :
> - `GET /api/chevaux` → filtré **côté serveur** :
>   - cavalier : chevaux de ses affectations du jour ;
>   - propriétaire : chevaux de sa `detention` en cours ;
>   - autres rôles : tout l'effectif.
> - `GET /api/chevaux/:id` → dossier : identité, séjour courant, régime spécial, dernières mesures, restrictions. Champs masqués selon le rôle : le propriétaire ne voit pas les restrictions détaillées.
>
> **Hors périmètre** — Mouvements, documents, édition.
>
> **Contraintes** — Un id hors périmètre → 404 (pas 403), pour ne pas révéler l'existence du cheval.
>
> **Attendu** — Cavalier : 2 chevaux. Propriétaire sur un cheval non détenu → 404.
>
> **Pour vérifier**
> - `npm -w api test -- src/routes/chevaux.test.ts` → rc 0, tous `passed`

### TA — Branchement des routes métier et parcours de démo
- **Write-set** :
  - `api/src/app.ts`
  - `api/src/app.test.ts`
- **Cibles** : « aucun engagement sous restriction », « contrat déclaré », « double revue avant clôture »
- **depends_on** : T2, T4, T5, T6, T7 · **UI** : non · **Estim.** 25 min · **Parallèle** avec TW

**Demande `/kickoff`** :
> **Objectif** — Enregistrer `registerSante`, `registerCourses`, `registerNourrissage` et `registerChevaux` dans `buildApp`. `app.test.ts` joue le parcours de démo de bout en bout sur une base en mémoire, avec `migrate` puis `seed` :
> 1. le vétérinaire confirme l'administration → restriction ;
> 2. le chargé des engagements valide → 409 avec justification ;
> 3. le vétérinaire lève avec motif → ligne d'audit ;
> 4. nouvelle validation → 200 ;
> 5. l'assistant confirme le nourrissage → rations.
>
> **Hors périmètre** — Toute nouvelle règle.
>
> **Pour vérifier**
> - `npm -w api test` → rc 0, tous `passed`
> - `npm run build` → rc 0

---

## 3. Couloir web (toutes les tâches sont UI : `frontend-fidelity` puis `design-review`)

Contraintes communes à W1–W5, à recopier dans chaque demande :
- Les chaînes FR/EN restent **locales au composant** (objet `{fr, en}` typé par `Lang` de `i18n.ts`) : `i18n.ts` n'est pas touché.
- Chaque écran exporte une vue pure (props → rendu), testée par `renderToString` en environnement node, et un conteneur qui appelle `web/src/api.ts`.
- `<App />` rend toujours `<h1>Aujourd’hui</h1>` (`Navigation.test.tsx:44`).
- Aucun écran n'affiche d'heure de lot.

### W1 — Sélecteur de profil de démonstration
- **Write-set** :
  - `web/src/api.ts`
  - `web/src/api.test.ts`
  - `web/src/components/ProfilePicker.tsx`
  - `web/src/components/ProfilePicker.test.tsx`
  - `web/src/App.tsx`
- **Cibles** : « droits côté serveur », « contrat déclaré », « tests au plus près du code »
- **depends_on** : — (contrat de T3 déclaré ci-dessous) · **UI** : oui · **Estim.** 35 min · **Parallèle** avec T1
- `mockup: no mockup: aucune maquette §6 ne couvre la connexion ; sélecteur de démonstration hors maquette (D4-A)`
- `INTERACTION: focus=premier persona à l'ouverture, ordre DOM ; echap=sans objet (pas de modale) ; modal=non, panneau dans <main> sous le h1 ; empilement=contexte racine, sous « + Ajouter » ; wcag=2.2 AA (cible ≥ 24 px, contraste 4.5:1, nom accessible = nom + rôle) ; largeurs=360/768/1280 ; etats=chargement/vide/erreur réseau/connecté`

**Demande `/kickoff`** :
> **Objectif** — `api.ts` : client `fetch` qui garde le jeton en mémoire (et dans `sessionStorage`, avec try/catch) et envoie `Authorization: Bearer`. Il expose `personas()`, `connecter(compteId)` et `moi()` selon le contrat de T3 : `GET /api/personas` → `[{compteId, nom, role}]`, `POST /api/session` → `{jeton, compte}`. `ProfilePicker` liste les personas et affiche le rôle connecté avec un bouton « Changer de profil ». Monté dans `App.tsx`.
>
> **Hors périmètre** — Les écrans métier, toute dépendance nouvelle.
>
> **Contraintes** — Communes, ci-dessus.
>
> **Attendu** — Sans session, le sélecteur est visible et le h1 est conservé. Une réponse 401 vide la session.
>
> **Pour vérifier**
> - `npm -w web test` → rc 0, tous `passed` (`Navigation.test.tsx` compris)
> - `npm -w web run build` → rc 0

### W2 — Écran nourrissage
- **Write-set** :
  - `web/src/screens/Feeding.tsx`
  - `web/src/screens/Feeding.test.tsx`
- **Cibles** : « saisie par exception », « prévu ≠ réalisé »
- **depends_on** : W1 · **UI** : oui · **Estim.** 30 min · **Parallèle** avec W3, W4, W5
- `mockup: <§6.2 Écran 01 Aujourd'hui, image extraite par P0>`
- `INTERACTION: focus=bouton « Tout est normal » ; echap=ferme le volet d'écart et rend le focus à la ligne ; modal=volet d'écart non modal ; empilement=sous la nav ; wcag=2.2 AA, cible ≥ 24 px ; largeurs=360/768/1280 ; etats=chargement/vide/erreur/confirmé/écart`

**Demande `/kickoff`** :
> **Objectif** — Checklist par cour et par repas, en consommant le contrat de T6 :
> - `GET /api/nourrissage` → `[{chevalId, nom, regime?, etat}]` ;
> - `POST /api/nourrissage/confirmer` ;
> - `POST /api/nourrissage/ecart`.
>
> Le régime spécial est mis en évidence. Le bouton unique « Tout est normal » confirme en une action. Un écart s'ouvre par ligne : refus, partielle ou anomalie, remarque facultative. Une `Idempotency-Key` est générée par action (`crypto.randomUUID`).
>
> **Hors périmètre** — Hors ligne, branchement (TW).
>
> **Attendu** — Pas de champ texte obligatoire. Au plus 3 interactions pour un écart, hors sélection du cheval.
>
> **Pour vérifier**
> - `npm -w web test -- src/screens/Feeding.test.tsx` → rc 0, tous `passed`

### W3 — Écran dossier cheval
- **Write-set** :
  - `web/src/screens/Horses.tsx`
  - `web/src/screens/Horses.test.tsx`
- **Cibles** : « droits côté serveur », « contrat déclaré »
- **depends_on** : W1 · **UI** : oui · **Estim.** 30 min
- `mockup: <§6.3 Écran 03 Chevaux, image extraite par P0>`
- `INTERACTION: focus=liste, puis dossier au choix d'un cheval ; echap=sans objet ; modal=non, liste à gauche et dossier à droite (empilés sous 768 px) ; empilement=sous la nav ; wcag=2.2 AA, liste navigable au clavier ; largeurs=360/768/1280 ; etats=chargement/vide/erreur/404 hors périmètre`

**Demande `/kickoff`** :
> **Objectif** — Liste persistante et dossier sur le même écran (§5, écran 03), en consommant le contrat de T7 : `GET /api/chevaux` et `GET /api/chevaux/:id`. Afficher les restrictions et l'éligibilité seulement si l'API les renvoie. Le filtrage par rôle est fait par le serveur, jamais par le client.
>
> **Pour vérifier**
> - `npm -w web test -- src/screens/Horses.test.tsx` → rc 0, tous `passed`

### W4 — Écran santé : soins et levée de restriction
- **Write-set** :
  - `web/src/screens/Health.tsx`
  - `web/src/screens/Health.test.tsx`
- **Cibles** : « prévu ≠ réalisé », « aucun engagement sous restriction », « correction tracée »
- **depends_on** : W1 · **UI** : oui · **Estim.** 35 min
- `mockup: <§6.5 Écran 11 Intervention & restriction, et §6.3 Santé, images extraites par P0>`
- `INTERACTION: focus=première tâche « en retard » ; echap=ferme le dialogue de confirmation ou de levée, focus rendu au déclencheur ; modal=oui pour confirmer une administration (lecture produit, dose et cheval, §2.1) et pour la levée (motif obligatoire), focus piégé ; empilement=au-dessus de la nav et de « + Ajouter » ; wcag=2.2 AA, rôle dialog et aria-modal ; largeurs=360/768/1280 ; etats=à faire/en retard/réalisé/erreur/403`

**Demande `/kickoff`** :
> **Objectif** — Liste des soins avec leur statut calculé (jamais « réalisé » sans confirmation, C6), et confirmation explicite qui montre produit, dose et cheval. Liste des restrictions actives ; « Lever » (vétérinaire ou entraîneur) avec motif obligatoire.
>
> Contrat de T4 :
> - `GET /api/soins` ;
> - `POST /api/administrations/:id/confirmer` ;
> - `POST /api/restrictions/:id/lever {motif}` ;
> - `GET /api/chevaux/:id/eligibilite`.
>
> Afficher « Hypothèse D10 » à côté de la règle du statut inconnu.
>
> **Pour vérifier**
> - `npm -w web test -- src/screens/Health.test.tsx` → rc 0, tous `passed`

### W5 — Écran courses : validation d'engagement
- **Write-set** :
  - `web/src/screens/Races.tsx`
  - `web/src/screens/Races.test.tsx`
- **Cibles** : « aucun engagement sous restriction »
- **depends_on** : W1 · **UI** : oui · **Estim.** 25 min
- `mockup: <§6.3 Écran 05 Courses, image extraite par P0>`
- `INTERACTION: focus=ligne d'engagement ; echap=ferme le panneau de dossier ; modal=panneau latéral non modal ; empilement=sous « + Ajouter » ; wcag=2.2 AA, justification annoncée par role="alert" ; largeurs=360/768/1280 ; etats=éligible/bloqué avec motifs/validé/erreur`

**Demande `/kickoff`** :
> **Objectif** — Liste des engagements avec l'éligibilité de chaque cheval. « Valider » appelle `POST /api/engagements/:id/valider`. Sur 409, afficher les motifs (restriction active : produit, fin prévue, source ; ou statut inconnu) et garder le bouton désactivé.
>
> **Pour vérifier**
> - `npm -w web test -- src/screens/Races.test.tsx` → rc 0, tous `passed`

### TW — Branchement des écrans dans l'application
- **Write-set** :
  - `web/src/App.tsx`
  - `web/src/App.test.tsx`
- **Cibles** : « contrat déclaré », « droits côté serveur »
- **depends_on** : W2, W3, W4, W5 · **UI** : oui · **Estim.** 25 min · **Parallèle** avec TA
- `mockup: <§6.2 Écran 01 pour la coque>`
- `INTERACTION: focus=h1 de l'écran au changement d'entrée ; echap=sans objet ; modal=non ; empilement=inchangé ; wcag=2.2 AA ; largeurs=360/768/1280 ; etats=non connecté/connecté par rôle`

**Demande `/kickoff`** :
> **Objectif** — Brancher les écrans sur les entrées de la navigation :
> - today → nourrissage ;
> - horses → dossier cheval ;
> - health → santé ;
> - races → courses.
>
> Une entrée inutile au rôle connecté est masquée (le cavalier ne voit pas Courses) : simple confort, le droit reste vérifié par l'API.
>
> **Pour vérifier**
> - `npm -w web test` → rc 0, tous `passed`
> - `npm run build` → rc 0
> - Démo manuelle : `npm run dev`, puis le parcours de TA dans le navigateur.

---

## 4. Si le temps — D2-C (défi B : lots)

À ne lancer qu'une fois TA et TW clos (règle R1 : fermer avant d'ouvrir).

| Tâche | Titre | Write-set | depends_on | UI | Estim. |
|---|---|---|---|---|---|
| C-1 | Schéma 0003 : programme versionné | `api/src/db/migrations/0003_programme.ts`, `…/0003_programme.test.ts`, `api/src/db/migrate.ts`, `api/src/routes/health.test.ts`, `schema/DATA_MODEL.md` | T1 | non | 25 min |
| C-2 | Reprise de la veille et publication versionnée | `api/src/domain/programme.ts`, `…/programme.test.ts`, `api/src/routes/planning.ts`, `…/planning.test.ts` | C-1, T3, T4 | non | 45 min |
| C-3 | Branchement planning (API) | `api/src/app.ts`, `api/src/app.test.ts` | C-2, TA | non | 15 min |
| C-4 | Écran lots : composition au clavier, à la souris et au tactile | `web/src/screens/Planning.tsx`, `…/Planning.test.tsx` | W1 | oui | 60 min+ |
| C-5 | Branchement planning (web) | `web/src/App.tsx`, `web/src/App.test.tsx` | C-4, TW | oui | 15 min |

**Détail des tâches C :**
- **C-1** — D7. Table `programme` (date, cour, version, statut brouillon/publié, publié_par, publié_le) et `lot.programme_id`. Cibles « lot sans heure », « correction tracée ».
- **C-2** — C1 (reprendre la veille → brouillon, retirer les absents, publier en nouvelle version sans écraser la version publiée), C13, et §7 : conflit cavalier (même lot et même date → refus), avertissement de restriction sur un lot (D10). Cibles « lot sans heure », « aucun engagement sous restriction », « prévu ≠ réalisé ».
- **C-4** — C2 : glisser-déposer avec alternative clavier, sans dépendance nouvelle (Pointer Events natifs, plus boutons « Déplacer vers lot N »). Mockup §6.3 Écran 02 Planning. Ligne INTERACTION à écrire, glisser et clavier compris.
  - **Risque** : C-4 est l'écran le plus cher (voir D2). Tests et accessibilité clavier peuvent déborder 2 fichiers. Si c'est le cas, découper en `LotBoard.tsx` + test (vue) et `Planning.tsx` + test (conteneur), soit 4 fichiers, ou ne livrer que l'alternative clavier en premier.

C-1 et C-3 touchent les mêmes fichiers partagés que T1 et TA : sérialisés après eux, jamais en parallèle.

## 5. Rappels pour le lancement
- **Création** — `tasks.py new` avec ce titre puis `tasks.py writeset <T> <chemins>`, puis `tasks.py direct <T>`. Un refus liste ses causes ; dans ce cas, revenir au chemin planifié.
- **Vocabulaire des titres** — Aucun titre ni stage ne contient « option », « décision », « arbitrer », « sécurité » ou « secret » (lexiques fermés de `tasks_direct.py`). Citer « D10 » plutôt que « décision D10 ».
- **Chaîne d'une directe** — `dev-*` (ou `frontend-fidelity` puis `design-review`), puis `exec-critic` ∥ `security-code-review`, puis la revue de clôture, puis `verify.sh`, puis `done`.
- **Avant le push de 16:00** — `bash core-scripts/verify.sh --at HEAD`, sur un SHA vert.

## Non couvert
- Le hors ligne (C9) : D13 n'est pas tranché.
- Les défis D, E et F.
- C8, C10 et C11 ne sont couverts qu'en partie : seule la levée de restriction est auditée.
- Les commandes « Pour vérifier » n'ont pas été rejouées à la rédaction ; les estimations sont des ordres de grandeur.
