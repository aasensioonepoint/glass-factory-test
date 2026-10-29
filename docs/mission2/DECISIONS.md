# Graffard Racing — Mission 2 : décisions à prendre

> Hackathon du 29 octobre 2026. Dernier push évalué : **16h00**.
> Sources : `docs/mission2/README.md` (énoncé), la spécification fonctionnelle V0
> (`.docx`, §2, §3, §7, §8, §10, §11, §13.1) et `schema/DATA_MODEL.md`.
> La spécification fait foi quand elle contredit le MCD.

**Mode d'emploi.** Chaque décision donne les options, une recommandation et ce
qu'elle débloque. Le pilote coche une option et remplit la ligne `Décision`.
Les décisions du **bloc 1** sont à prendre avant le premier `/kickoff`. Les
décisions du **bloc 3** sont des **hypothèses** : la démo doit les présenter
comme telles (exigence de l'énoncé, défi E et §11).

---

## Bloc 1 — À trancher avant le premier kickoff

### D1. Stack technique

| Option | Pour | Contre |
|---|---|---|
| **A. Tout TypeScript** : React + Vite (PWA, `vite-plugin-pwa`, IndexedDB via Dexie), API Fastify, PostgreSQL 17, Vitest + Playwright | Un seul langage ; même stack que le socle de la mission 1 ; le kit est entièrement outillé (guides React et Playwright, scan des dépendances npm) | — |
| **B. API .NET** : ASP.NET Core (Minimal API, EF Core + Npgsql) + front React/TS PWA, PostgreSQL 17 | Pertinent si l'équipage est nettement plus à l'aise en C# | Dépendances NuGet **non scannées** par le kit (`COVERAGE DEGRADED`), aucun guide .NET installé, SDK .NET absent du poste, la détection de stack du kit ne reconnaît pas .NET |
| **C. API FastAPI** (Python) + front React/TS PWA, PostgreSQL 17 | Pertinent si l'équipage est plus à l'aise en Python | Deux langages à maintenir |

Front Blazor déconseillé : le hors ligne avec synchronisation sans doublon
(critère 9, défi F) est plus simple et mieux documenté côté React.

**Recommandation : A**, sauf si l'équipage est nettement plus productif en C# ou en Python.
**Débloque :** le squelette du projet, puis `/skills-sync`.
**À justifier dans la démo :** oui, c'est un livrable.

- [ ] A — TypeScript  - [ ] B — .NET  - [ ] C — FastAPI
- Décision :

### D2. Périmètre visé à 16h00

La profondeur compte plus que la largeur : chaque palier atteint doit respecter
les règles métier de bout en bout.

| Option | Contenu | Risque |
|---|---|---|
| **A. Socle + règle critique** | Palier 1 (modèle, référentiels, dossier cheval) + défi C complet (administration → restriction → engagement bloqué, critères 6 et 7) + défi A (nourrissage, critère 4) | Faible ; démontre le risque n° 1 du client |
| **B. Socle + A à E** | Palier 1 + les cinq défis métier, chacun au minimum | Largeur sans profondeur, ce que l'énoncé pénalise |
| **C. A + défi B** | Option A + lots (reprise de la veille, publication versionnée, conflit cavalier, critères 1, 2, 13) | Moyen ; le glisser-déposer accessible au clavier coûte cher |

**Recommandation : A, puis C si le temps le permet.** Le défi F (voix) et le
hors ligne complet passent en bonus.

- [ ] A  - [ ] B  - [ ] C
- Décision :

### D3. Découpage entre les membres de l'équipage

Une seule personne lance le plan avec la rubrique `Découpage`. Les autres
attendent qu'il soit poussé, puis chacun lance `/kickoff T-…` sur sa tâche.
Règle : **pas de fichier en commun** entre deux tâches parallèles.

Proposition pour 3 personnes, avec l'option D2-A :

| Personne | Tâche | Fichiers |
|---|---|---|
| 1 | Schéma + migrations + données de démo fictives | `db/` |
| 2 | API : chevaux, soins, restrictions, engagements | `api/` |
| 3 | PWA : Aujourd'hui, dossier cheval, nourrissage, soins | `web/` |

Dépendance à déclarer : la tâche 1 est l'amont des tâches 2 et 3 (le contrat de
schéma doit être fixé en premier).

- Décision :

### D4. Authentification et rôles pour la démo

La spec exige « aucun compte partagé » et des contrôles côté serveur (§2, §7).

| Option | Description |
|---|---|
| **A. Comptes de démo par persona** | Un compte fictif par rôle (assistant entraîneur, cavalier, vétérinaire, chargé des engagements, propriétaire), connexion simple (sélecteur de profil + jeton signé), droits vérifiés côté serveur |
| **B. Vraie authentification** (OIDC, mots de passe) | Plus réaliste, mais coûteux pour la journée |
| **C. Utilisateur fixe** | Rapide, mais contredit les critères 3 et 12 |

**Recommandation : A.** Elle permet de démontrer les critères 3 (le cavalier ne
voit que son programme) et 12 (le propriétaire ne voit que ce qui lui est partagé).

- [ ] A  - [ ] B  - [ ] C
- Décision :

---

## Bloc 2 — Arbitrages entre le MCD et la spécification

Livrable explicite : « le schéma implémenté, avec ses changements expliqués ».
Chaque décision ci-dessous devient une ligne du document d'architecture.

### D5. `LOT.heure`

La spec (§7, critère 13) : un lot n'a **ni heure de début, ni heure de fin, ni
plage horaire** ; il est identifié par son numéro, sa cour et la date du programme.

**Recommandation : supprimer la colonne** et ajouter un `ordre_passage`.
Contrainte d'unicité sur (numéro, cour, date du programme).

- Décision :

### D6. Tables manquantes

| Table | Besoin (spec) | Proposition |
|---|---|---|
| `RESTRICTION` | Défi C, §8.1 : une restriction référence sa source, son périmètre et son validateur | `cheval_id`, `source` (administration, examen, manuel), `source_id`, `debut`, `fin_prevue`, `statut` (active, levée), `validateur_id`, `leve_par_id`, `leve_le`, `motif_levee` |
| `MESURE` | Température et poids (§2.1, critère 5) | `cheval_id`, `type` (temperature, poids), `valeur`, `unite`, `auteur_id`, `date_reelle` |
| `REGIME_SPECIAL` | Défi A : régimes visibles sur la checklist | `cheval_id`, `description`, `debut`, `fin`, `valide_par_id` |

- Décision :

### D7. Versions du planning

La spec (§7) : le planning publié est versionné ; un brouillon ne remplace
jamais silencieusement la version visible sur le terrain.

| Option | Description |
|---|---|
| **A. Table `PROGRAMME`** (date, cour, version, statut brouillon/publié, publié_par, publié_le) qui porte les lots | Clair, et requêtable |
| **B. Instantané JSON** de la version publiée | Rapide, mais historique difficile à interroger |

**Recommandation : A.** Hors périmètre si D2-C n'est pas retenu.

- Décision :

### D8. Traçabilité, audit et synchronisation

La spec (§7, §8 « Fiabilité ») exige pour chaque donnée : identifiant stable,
auteur, date réelle, date de réception, source et statut ; une correction garde
l'avant, l'après et le motif.

Proposition :
- colonnes communes sur les tables métier : `auteur_id`, `date_reelle`,
  `date_reception`, `source`, `statut` ;
- table `AUDIT` : objet, identifiant, avant, après, motif, auteur, horodatage ;
- table `COMMANDE_SYNC` : `id_commande` unique généré par l'appareil (clé
  d'idempotence), statut, accusé, erreur ;
- table `CONFLIT` : les deux versions, la résolution et la personne habilitée qui a tranché.

**Recommandation :** l'`AUDIT` et la clé d'idempotence dès le palier 1 (peu
coûteux et transverse). `CONFLIT` seulement si le hors ligne est traité.

- Décision :

### D9. Statuts des enregistrements

La spec (§7) impose de distinguer : brouillon, validé, publié, réalisé, annulé, corrigé.
Pour les soins, une tâche non confirmée est « à faire » ou « en retard », jamais
« réalisée » (critère 6).

**Recommandation :** une énumération unique partagée par toutes les tables
métier, plus un statut calculé « en retard » pour les soins non confirmés.

- Décision :

---

## Bloc 3 — Hypothèses métier (à afficher comme telles dans la démo)

### D10. Règle de restriction et d'éligibilité

Ce que la spec impose : une administration confirmée d'un produit à délai de
retrait crée une restriction ; une restriction active **ou un statut inconnu**
bloque l'engagement, avec la justification affichée ; une date dépassée ne lève
**jamais** une restriction automatiquement (levée validée, jamais implicite).

À décider :
- Qui peut lever une restriction ? Proposition : le vétérinaire ou l'entraîneur, avec motif obligatoire.
- Comment se calcule la fin de retrait ? Proposition : date d'administration + `delai_retrait_jours` du produit.
- Que veut dire « statut inconnu » ? Proposition : aucun soin ni examen enregistré depuis N jours, ou un produit sans délai renseigné.
- Une restriction bloque-t-elle ou avertit-elle ? Proposition : **bloque** l'engagement en course, **avertit** pour l'affectation à un lot.

- Décision :

### D11. Scoring de forme (défi E)

L'énoncé le dit : les 3 niveaux et les règles d'alerte **ne sont pas définis**.
L'équipage les propose et les présente comme des hypothèses.

Proposition :
- niveaux : « Bien » / « À surveiller » / « Préoccupant » ;
- alerte : 2 niveaux « Préoccupant », ou 3 « À surveiller », sur 7 jours glissants ;
- aucun diagnostic automatique ni classement des personnes.

- Décision :

### D12. IA : dictée et transcription (défi F)

La spec (§11) : l'IA produit des brouillons à confirmer ; les journaux de
requêtes IA sont protégés.

| Option | Description |
|---|---|
| **A. Transcription simulée** | Une transcription factice déterministe, avec l'enregistrement audio réel conservé |
| **B. Web Speech API du navigateur** | Gratuite, mais ne fonctionne pas hors ligne et dépend du navigateur |
| **C. Service de transcription** (Whisper ou Azure Speech) | Réaliste, mais demande une clé, du réseau et une revue des données envoyées |

**Recommandation : A pour la démo.** On montre le circuit enregistrement → brouillon
→ confirmation humaine, qui est ce que l'énoncé évalue. Ne jamais mettre de clé
dans le dépôt : la factory refuse les secrets.

- Décision :

### D13. Périmètre du hors ligne

La spec (§2, critère 9) : consultation locale, file d'attente, synchronisation
idempotente, états « sur cet appareil » / « synchronisé » / « à résoudre ».

| Option | Description |
|---|---|
| **A. Nourrissage seul hors ligne** | La checklist du défi A marche sans réseau, avec la file et les trois états |
| **B. Toutes les saisies terrain** | Nourrissage, retours de piste, mesures, remarques vocales |
| **C. Pas de hors ligne** | Assumé et documenté comme une limite |

**Recommandation : A.** Elle suffit à démontrer le critère 9.

- Décision :

---

## Bloc 4 — Décisions de la spec §13.1, réponses pour le hackathon

La spec liste six décisions à prendre « avant développement ». Elles ne peuvent
pas être tranchées par le client aujourd'hui. Proposition : y répondre par une
hypothèse écrite, citée dans la démo.

| Décision §13.1 | Hypothèse proposée pour la démo |
|---|---|
| Terminaux, autonomie, réseau, durée hors connexion | Téléphone Android ou iOS récent, navigateur à jour ; 4 h hors ligne maximum |
| Validateurs nominatifs et règles sanitaires | Un vétérinaire fictif valide les délais de retrait ; produits fictifs avec délais fictifs |
| Système maître par domaine | France Galop pour les engagements et vaccinations ; l'application pour le terrain et la santé ; connecteurs simulés en bonus |
| Droits par rôle, conservation, périmètre propriétaire | Les 9 personas de la spec §3 ; propriétaire limité aux chevaux qui lui sont partagés |
| Budget de saisie par action | Celui de la spec : 3 interactions au plus, confirmation normale en moins de 5 s |
| Contenu exact du P0 et critères de go/no-go | La réponse à D2 |

- Décision :

---

## Bloc 5 — Préparation de la factory

### D14. Cibles du projet dans `docs/PROMPT-projet.md`

Chaque étape d'un plan doit citer une cible de ce fichier, sinon le plan est
refusé. Il ne contient aujourd'hui que les sept cibles génériques du kit.

Proposition d'ajouts (noms courts et stables) :
- **« prévu ≠ réalisé »**
- **« aucun engagement sous restriction »**
- **« lot sans heure »**
- **« saisie par exception »**
- **« IA en brouillon »**
- **« synchronisation idempotente »**

- Décision :

### D15. Lisibilité des documents source par les agents

Les agents ne lisent pas le `.docx` ni le `.pptx`. Or la spécification fait foi.

**Recommandation :** convertir la spécification en Markdown
(`docs/mission2/specification-fonctionnelle.md`) avant le premier plan.

- Décision :

---

## Récapitulatif

| # | Décision | Bloque | Recommandation | Décidé |
|---|---|---|---|---|
| D1 | Stack | Squelette | TypeScript | |
| D2 | Périmètre à 16h00 | Tout | Socle + règle critique + nourrissage | |
| D3 | Découpage | Kickoffs parallèles | db / api / web | |
| D4 | Authentification | Critères 3 et 12 | Comptes de démo par persona | |
| D5 | `LOT.heure` | Schéma | Supprimer, ajouter `ordre_passage` | |
| D6 | Tables manquantes | Schéma | `RESTRICTION`, `MESURE`, `REGIME_SPECIAL` | |
| D7 | Versions du planning | Défi B | Table `PROGRAMME` | |
| D8 | Audit et synchronisation | Schéma | `AUDIT` + clé d'idempotence | |
| D9 | Statuts | Schéma | Énumération unique | |
| D10 | Règle de restriction | Défi C | Bloque l'engagement, levée validée | |
| D11 | Scoring | Défi E | 3 niveaux, hypothèse affichée | |
| D12 | IA vocale | Défi F | Transcription simulée | |
| D13 | Hors ligne | Critère 9 | Nourrissage seul | |
| D14 | Cibles du projet | Tous les plans | 6 cibles métier | |
| D15 | Spec en Markdown | Qualité des plans | Convertir | |
