# GRAFFARD RACING — Spécification fonctionnelle V0

> Spécification fonctionnelle du nouveau système de gestion d'écurie.
> Version 0 à confronter aux exigences utilisateurs et à valider — 13 octobre 2026.
>
> **Conversion Markdown** du fichier `GRAFFARD RACING-specification fonctionnelle V0.docx`
> (même dossier), faite le 29 octobre 2026 pour que les agents puissent la lire.
> Le texte et les tableaux sont repris tels quels ; seuls le sommaire a été retiré
> et les critères du §12 numérotés (C1 à C13) pour pouvoir les citer.
> **Les maquettes (images) du §6 ne sont pas reprises** : les consulter dans le `.docx`.
> Ce document **fait foi** quand il contredit le MCD (`schema/DATA_MODEL.md`).

## 1. Objet et ambition

Le produit cible est un site web métier, utilisable sur mobile, tablette, ordinateur et écran partagé, conçu pour assister une écurie de course de grand renom sans ralentir l'activité terrain. Il combine la simplicité de Racing TrackTable, notamment l'action « + Ajouter » et le glisser-déposer des lots, la couverture fonctionnelle de Racing Claudia, le déroulement réel de la journée décrit dans « Vis ma vie », et la structuration des données proposée dans le MCD VDraft 2.

Principe directeur : saisir uniquement ce qui est indispensable au moment où l'action se produit. Les informations administratives, documentaires et réglementaires sont complétées au bureau ou préremplies par le système. Une action normale doit demander une confirmation ; seuls les écarts exigent une précision.

La cible est une source de vérité opérationnelle par cheval, reliant travail, santé, mouvements, engagements, documents et communications, tout en conservant les systèmes officiels sur leurs périmètres.

### 1.1 Résultats attendus

- Réduire les doubles saisies, les oublis et la dépendance aux tableaux, fichiers isolés et mémoires individuelles.
- Reconduire et ajuster les lots du matin en quelques gestes.
- Tracer le réalisé sans transformer les cavaliers et responsables en agents administratifs.
- Relier traitements, délais de retrait, vaccinations et engagements.
- Disposer d'un historique fiable, daté et consultable par cheval.
- Fonctionner malgré une connectivité instable, avec état de synchronisation visible.

## 2. Principes de conception

| Principe | Traduction produit | Critère mesurable |
|---|---|---|
| Terrain d'abord | Écrans utilisables debout, d'une main, sous contrainte de temps. | Action courante en trois interactions maximum hors sélection du cheval. |
| Saisie par exception | Une situation normale se confirme ; l'écart ouvre les champs utiles. | Aucun commentaire obligatoire lorsqu'il n'y a pas d'anomalie. |
| Contexte prérempli | Cheval, auteur, cour, date et heure repris depuis l'écran d'origine. | Aucune ressaisie d'une donnée déjà connue. |
| Prévu ≠ réalisé | Planning, prescription et engagement restent distincts de leur exécution. | Une absence de confirmation ne devient jamais « réalisé ». |
| Progressivité | Le détail s'affiche seulement selon le type d'action et le rôle. | Pas de formulaire générique surchargé. |
| Continuité hors ligne | Consultation locale, file d'attente et synchronisation idempotente. | Statuts « sur cet appareil », « synchronisé », « à résoudre » visibles. |
| Sécurité utile | Droits minimaux par rôle, cour et cheval. | Aucun compte partagé ; contrôles côté serveur. |
| IA supervisée | Dictée, OCR et synthèse produisent des brouillons à confirmer. | Aucune décision médicale, sportive ou réglementaire autonome. |

### 2.1 Budget de saisie

- Confirmation d'une tâche normale : moins de 5 secondes.
- Température ou poids : cheval puis valeur, avec clavier numérique.
- Observation : choix rapide, texte ou dictée facultative.
- Traitement sensible : lecture explicite du produit, de la dose et du cheval avant confirmation.
- Toute information pouvant être dérivée d'un contexte fiable doit être préremplie.

## 3. Utilisateurs et droits

| Persona | Besoins prioritaires | Actions principales |
|---|---|---|
| Entraîneur / direction | Priorités, alertes, engagements, vision consolidée. | Arbitrer, valider le programme, consulter la synthèse. |
| Assistant entraîneur | Préparer et publier les lots, gérer les aléas. | Reconduire, affecter, déplacer, publier. |
| Responsable de cour | Programme de cour, soins, exceptions. | Suivre l'exécution, réaffecter, alerter. |
| Cavalier / lad | Consigne immédiate et saisie minimale. | Consulter son programme, confirmer, signaler un écart. |
| Vétérinaire / maréchal / spécialiste | Dossier ciblé, intervention, justificatif. | Prescrire ou tracer l'acte selon mandat. |
| Bureau / administration / RH | Effectif, mouvements, documents, planning, rapprochement. | Compléter, contrôler, exporter et communiquer. |
| Chargé des engagements | Courses, restrictions, preuves officielles. | Préparer, contrôler et enregistrer le statut. |
| Propriétaire | Nouvelles publiées et documents autorisés. | Consulter et échanger dans un périmètre limité. |
| Administrateur | Accès, référentiels, interfaces, audit. | Paramétrer, superviser et résoudre les anomalies. |

Les rôles métier et applicatifs sont distincts. Une personne peut cumuler plusieurs rôles. Les droits portent sur une action, un périmètre et une période. Les détails RH, médicaux et propriétaires sont masqués lorsqu'ils ne sont pas utiles à l'action.

## 4. Parcours utilisateur de référence

### 4.1 Journée terrain

- 5 h 15 — nourrissage : consulter les régimes spéciaux ; ne saisir que refus, consommation partielle ou anomalie.
- 5 h 45 — préparation des lots : reprendre le brouillon de la veille ; retirer les absents ; déplacer chevaux et cavaliers ; choisir l'exercice ; résoudre les conflits ; publier.
- 6 h 15 — travail : chaque cavalier ouvre son programme, lit la consigne et confirme au retour. Un écart ouvre le retour détaillé.
- 8 h 30 — soins : consulter les tâches, vérifier le cheval et les paramètres, confirmer ce qui a réellement été administré.
- Vers 9 h — bureau : joindre les documents, rapprocher les pièces, contrôler les restrictions, préparer les communications et exports.

### 4.2 Parcours lots

Accueil → Lots du jour → Reprendre la veille → Recalculer disponibilités et restrictions → Glisser-déposer cheval et cavalier → Choisir l'activité → Contrôler les exceptions → Publier → Diffuser aux cours → Confirmer le réalisé.

### 4.3 Parcours santé-course

Prescription vérifiée → Administrations planifiées → Acte réel confirmé → Restriction recalculée selon un protocole validé → Contrôle avant engagement → Preuve officielle conservée → Levée validée, jamais implicite.

### 4.4 Parcours arrivée-départ

Mouvement planifié → Contrôle identité et carnet → Confirmation de l'événement réel → Fermeture/ouverture du séjour → Mise à jour des systèmes externes → Bon de sortie prérempli → Notification validée.

## 5. Architecture d'écrans optimisée

| Écran principal | Fonctions regroupées | Navigation optimisée |
|---|---|---|
| 01 Aujourd'hui | Dashboard, prochain lot, tâches, alertes, raccourcis. | Page d'entrée par rôle ; toutes les actions urgentes accessibles en un clic. |
| 02 Planning | Lots, affectations, exercices, calendrier, équipe et disponibilités. | Onglets Lots / Calendrier / Équipe ; panneau latéral d'affectation sans changement de page. |
| 03 Chevaux | Effectif, identité, localisation, historique, mouvements et documents du cheval. | Liste persistante à gauche, dossier à droite ; changement de cheval sans retour arrière. |
| 04 Santé | Soins, prescriptions, administrations, vaccins, mesures, interventions et restrictions. | Onglets par usage ; « + Ajouter » ouvre le bon formulaire contextuel. |
| 05 Courses | Engagements, éligibilité, dossier course, transport et checklist départ. | Une ligne d'engagement ouvre le dossier complet dans un panneau. |
| 06 Plus | Propriétaires, communication, documents, assistant, alertes, administration et aide. | Hub réservé aux usages moins fréquents ; raccourcis personnalisés par rôle. |
| 07 Propriétaires | Portefeuille, détention, espaces partagés, messages et publications. | Sous-module de Plus, accessible directement au bureau et à la direction. |
| 08 Documents & administration | Bibliothèque, imports/exports, rapprochement, référentiels et accès. | Onglets bureau ; aucune entrée visible pour les profils terrain. |
| 09 + Ajouter | Observation, température, poids, soin, vaccination, mouvement et course. | Panneau superposé depuis tout écran ; retour automatique au contexte initial. |
| 10 Mon programme mobile | Consigne, matériel, confirmation et retour de piste. | Vue terrain dédiée, séquentielle, sans menu complexe. |
| 11 Intervention & restriction | Ordonnance, administration réelle, restriction et impact course. | Assistant en quatre étapes dans Santé ; une validation par étape sensible. |
| 12 Audit & synchronisation | Journal, file hors ligne, conflits et intégrations. | Visible aux responsables ; état réseau toujours accessible dans l'en-tête. |

## 6. Navigation et maquettes de référence

La navigation primaire est volontairement limitée à six entrées : Aujourd'hui, Planning, Chevaux, Santé, Courses et Plus. Les fonctions fréquentes restent à un clic ; les fonctions spécialisées sont regroupées dans des onglets ou panneaux contextuels. Les maquettes ci-dessous sont des références de conception avec données fictives ; les règles métier du document prévalent en cas de simplification visuelle.

### 6.1 Plan fonctionnel de l'écurie, acteurs et tâches

Plan fonctionnel inspiré de la slide fournie. Les implantations, rôles nominatifs et circuits physiques restent à confirmer lors d'un relevé sur site.

### 6.2 Écran 01 — Dashboard « Aujourd'hui »

Parcours : ouverture de session → prochain lot ou tâche prioritaire → action directe → retour au dashboard. Règles : aucune statistique décorative ; priorité aux actions du jour ; état réseau permanent ; « + Ajouter » toujours visible ; personnalisation par rôle. Toute carte de lot affiche son numéro et sa cour, sans horaire. Le prochain lot est déterminé par l'ordre des lots et leur état d'avancement.

### 6.3 Écrans 02 à 05 — Planning, Chevaux, Santé, Courses

Planning : composition des lots par glisser-déposer avec alternative tactile et clavier. Les en-têtes affichent uniquement le numéro du lot et la cour, par exemple « Lot 1 — Grand Cour », sans plage horaire. Chevaux : liste et dossier sur le même écran. Santé : onglets et confirmations explicites. Courses : engagements, contrôle d'éligibilité et transport réunis sans ressaisie.

### 6.4 Écrans 06 à 08 — Calendrier, Propriétaires, Documents et Plus

Calendrier & équipe : planning opérationnel et disponibilités dans un même espace, avec confidentialité RH. Les lots y sont présentés par date et ordre de passage, sans créneau horaire ; les horaires des autres événements et les disponibilités RH restent inchangés. Propriétaires : portefeuille, chevaux et communication prévisualisée. Documents : bibliothèque et rapprochement. Plus : assistant, alertes, hors ligne et paramètres regroupés.

### 6.5 Écrans 09 à 12 — Ajouter, Programme mobile, Intervention et Audit

+ Ajouter : catégories simples puis formulaire progressif. Programme mobile : une tâche à la fois et retour en un geste. Les lots du programme sont présentés dans leur ordre de passage, avec numéro et cour, sans horaire. Intervention : continuité entre ordonnance, acte réel, restriction et engagement. Audit : synchronisation, conflits et intégrations visibles aux responsables.

## 7. Règles de gestion transverses

- Chaque donnée métier est rattachée à un identifiant stable, un auteur, une date réelle, une date de réception et une source.
- Le système distingue systématiquement brouillon, validé, publié, réalisé, annulé et corrigé.
- Les corrections conservent la valeur initiale, l'auteur, l'horodatage et le motif.
- Un cheval ne possède qu'un séjour courant, mais tous ses séjours antérieurs restent accessibles.
- Un lot est une rotation de travail et non un lieu. Il est identifié par son numéro, sa cour et la date du programme, sans heure de début, heure de fin ni plage horaire. Le nombre et l'ordre des lots sont paramétrables.
- Un cheval au repos box, sorti de l'effectif ou soumis à une restriction incompatible ne peut pas être affecté sans résolution explicite.
- Un cavalier indisponible ou déjà affecté à un cheval dans le même lot ne peut pas être affecté à un second cheval de ce lot. Ce contrôle repose sur le lot et la date du programme, et non sur une plage horaire.
- Le planning publié est versionné. Un brouillon ne remplace jamais silencieusement une version visible sur le terrain.
- Une prescription planifie ; seule une administration confirmée trace l'acte réel.
- Les délais, seuils et protocoles sanitaires sont versionnés et validés par une personne compétente. L'IA ne les invente pas.
- Un engagement local ne remplace jamais le statut de l'organisme officiel.
- Une date dépassée ne déclenche pas automatiquement une levée médicale.
- Les notifications sont dédupliquées. La lecture ne clôt pas l'action.
- Les échanges externes sont idempotents et conservent l'accusé, les erreurs et les identifiants de correspondance.
- Les données sensibles sont filtrées côté serveur, y compris dans les exports, l'assistant IA et les liens directs.

## 8. Modèle de données cible

| Domaine | Entités principales | Évolutions recommandées |
|---|---|---|
| Référentiels | Cheval, acteur, écurie, lieu, compte, rôle. | Séparer personne, rôle métier, emploi et compte applicatif. |
| Effectif | Séjour, mouvement, détention. | Un séjour courant, mouvements réels distincts des mouvements planifiés. |
| Terrain | Lot, séance, affectation, ration, mesure, observation. | Version du planning, prévu/réalisé, provenance et état de synchronisation. |
| Santé | Produit, prescription, administration, acte, examen, vaccination, restriction. | Protocole versionné, validateur, source, contrôle d'éligibilité. |
| Courses | Course, engagement, résultat, transport, prise en charge. | Identifiants externes, statuts sourcés, coûts et échéances internationales. |
| RH | Employé, créneau, affectation RH, pointage, absence. | Séparer disponibilité et affectation cheval. |
| Communication | Événement, publication, destinataire, notification, document. | Visibilité, preuve d'envoi, lien multi-objet, versions. |
| Fiabilité | Commande de synchronisation, conflit, échange, audit. | Identifiant idempotent, avant/après, résolution humaine. |

### 8.1 Contraintes de cardinalité clés

- Un cheval possède plusieurs événements, séances, actes, engagements et mouvements.
- Un lot contient plusieurs séances ; une séance concerne un seul cheval et peut avoir plusieurs affectations datées.
- Un transport contient plusieurs prises en charge ; une prise en charge concerne un cheval.
- Une prescription peut donner lieu à plusieurs administrations ; une administration peut référencer une prescription.
- Une restriction doit référencer sa source, son périmètre et son validateur.
- Un document peut être lié à plusieurs objets sans duplication physique.

## 9. Direction UX/UI inspirée de Graffard Racing

La direction visuelle reprend l'esprit institutionnel du site Graffard Racing : élégance sobre, exigence, précision et respiration. L'interface métier ne copie pas le site vitrine ; elle transpose son identité dans un outil lisible et robuste. Le site officiel met en avant une écurie internationale à Chantilly, une narration premium et la signature « Excellence. Précision. Passion. »

| Élément | Spécification |
|---|---|
| Palette | Bleu nuit #142E3B, ivoire #F5F2EB, or doux #B89C63, gris texte #56666D, blanc. |
| Typographie | Titres éditoriaux élégants ; police sans sérif très lisible pour données et actions. |
| Hiérarchie | Un objectif principal par écran ; actions secondaires discrètes ; grands espaces respirants au bureau. |
| Terrain | Boutons larges, contraste élevé, zones tactiles d'au moins 44 px, texte essentiel visible sans défilement. |
| Cartes cheval | Nom, box/cour, statut, alerte et activité uniquement ; détails à la demande. |
| Couleurs d'état | Jamais seules : icône et libellé obligatoires. Or pour priorité, rouge pour blocage, vert uniquement si contrôle positif explicite. |
| Photographie | Réservée à l'identité et à la communication, pas aux listes opérationnelles denses. |
| Responsive | Mobile : liste et actions rapides ; tablette : lots et tournées ; bureau : calendriers, rapprochements et administration ; TV : lecture seule. |

### 9.1 Maquette fonctionnelle de l'accueil

En-tête : cour, date, état réseau et profil. Bloc principal : prochain lot dans l'ordre du programme ou prochaine tâche. Le lot est libellé par son numéro et sa cour uniquement, sans horaire. Bloc secondaire : alertes nécessitant une action. Navigation : Aujourd'hui, Lots, Chevaux, Soins, Calendrier. Action flottante : « + Ajouter » toujours accessible. Aucun indicateur décoratif ni classement individuel.

## 10. Architecture fonctionnelle et exigences techniques

- Front web responsive / PWA : mobile, tablette, bureau et TV ; cache chiffré limité au périmètre autorisé.
- API métier : règles centralisées, contrôle d'accès serveur, transactions atomiques et journalisation.
- Base relationnelle : identifiants stables, contraintes d'intégrité, historique et versionnement.
- Stockage documentaire : fichiers privés, antivirus, versions, rétention et liens temporaires.
- Synchronisation : file locale, identifiant unique de commande, reprise, accusé, détection de conflit.
- Observabilité : erreurs, latence, synchronisations bloquées, connecteurs et journaux d'audit.
- Performance : ouverture du programme local immédiate ; réponse cible inférieure à deux secondes en ligne pour les écrans courants.
- Accessibilité : navigation clavier, libellés explicites, contrastes conformes, alternative au drag-and-drop.
- Internationalisation : français et anglais, dates/heures locales, unités et fuseaux explicites.

### 10.1 Intégrations

| Système | Périmètre | Règle |
|---|---|---|
| France Galop | Engagements, statuts, vaccinations, effectif. | Reste source officielle ; API si contractuellement disponible, sinon import contrôlé. |
| Equitop | Facturation, pension, présence et éventuellement localisation. | Arbitrer les données maîtres ; export validé tant qu'aucune API fiable n'existe. |
| The Racing Manager | Communication propriétaire, replays et nouvelles. | Réutiliser le canal existant ; synchroniser seulement les données autorisées. |
| Messagerie | Ordonnances, notifications et communications formelles. | Classer les pièces après rapprochement humain. |
| Capteurs | Données de travail ou biométriques. | Extension, jamais prérequis au socle ; consentement, qualité et contrat à valider. |

## 11. Exigences IA

| Capacité | Comportement attendu | Garde-fou |
|---|---|---|
| Dictée | Transcrire, proposer cheval et type d'événement. | Confirmation obligatoire ; ambiguïtés affichées. |
| OCR ordonnance | Extraire les champs et montrer leur provenance. | Brouillon uniquement ; incertitude visible ; validation habilitée. |
| Assistant | Répondre à partir des données autorisées et citer les fiches utilisées. | Pas de diagnostic, prescription, engagement ou correction autonome. |
| Synthèse quotidienne | Regrouper lots, écarts, soins et échéances. | Distinguer fait, prévu, manquant et hypothèse. |
| Détection d'anomalies | Signaler incohérences, doublons et conflits. | Ne jamais supprimer ou corriger sans validation. |
| Aide au développement | Utiliser cette spécification, le dictionnaire de données et les critères d'acceptation. | Toute hypothèse non validée doit être marquée explicitement. |

Les journaux de requêtes IA sont protégés, soumis aux mêmes droits que les données sources et exclus de l'entraînement de modèles externes sans accord explicite. Les réponses affichent la date de fraîcheur et indiquent clairement les informations manquantes.

## 12. Critères d'acceptation prioritaires

- **C1** — Un assistant peut reprendre le planning de la veille, corriger les indisponibilités et publier une nouvelle version sans ressaisir toutes les séances.
- **C2** — Le drag-and-drop fonctionne au tactile, à la souris et possède une alternative clavier.
- **C3** — Un cavalier consulte son programme sans accéder à des données non nécessaires.
- **C4** — Un retour normal se confirme en une action ; un écart crée une trace et un suivi.
- **C5** — La saisie d'une température ne comporte aucun champ texte obligatoire.
- **C6** — Une tâche de traitement non confirmée reste « à faire » ou « en retard », jamais « réalisée ».
- **C7** — Une restriction active ou inconnue empêche localement une validation d'engagement et affiche la justification.
- **C8** — Une vaccination, le carnet et la mise à jour officielle peuvent être suivis séparément.
- **C9** — Une saisie hors ligne porte un état clair et ne crée pas de doublon à la reconnexion.
- **C10** — Un conflit de planning ou de santé conserve les deux versions et exige une résolution habilitée.
- **C11** — Chaque correction sensible est auditée avec avant/après et motif.
- **C12** — Le propriétaire ne peut consulter que les chevaux et contenus explicitement partagés.
- **C13** — Sur tous les écrans affichant des lots, notamment Aujourd'hui, Planning, Calendrier, le dossier cheval et Mon programme mobile, aucun lot ne présente d'heure de début, d'heure de fin ou de plage horaire. L'affichage conserve le numéro du lot, la cour et l'ordre de passage ; la date est portée par le programme. Aucun horaire n'est demandé lors de la création, de la modification, de la reconduction ou de la publication d'un lot. Les horaires des soins, courses, transports et autres événements restent inchangés.

### 12.1 Indicateurs de réussite du pilote

- Temps de préparation et de modification des lots.
- Nombre moyen d'interactions pour une action terrain.
- Taux de confirmations effectuées le jour même.
- Nombre de doubles saisies supprimées.
- Taux d'échecs et conflits de synchronisation.
- Nombre d'alertes pertinentes versus alertes ignorées.
- Satisfaction par rôle et observation directe en situation réelle.

## 13. Feuille de route proposée

| Phase | Périmètre | Condition de sortie |
|---|---|---|
| P0 — Pilote terrain | Effectif, dossier cheval, lots, programme, retours, soins, mesures, restrictions, hors ligne, audit. | Usage accepté dans une cour ; règles critiques validées ; aucune perte de données. |
| P1 — Exploitation complète | Mouvements, transports, engagements, vaccinations, documents, RH, propriétaires, interfaces contrôlées. | Sources maîtres arbitrées ; processus bureau opérationnels ; droits validés. |
| P2 — Assistance avancée | Dictée, OCR avancé, assistant IA, biosécurité, stocks, capteurs et transferts. | Valeur démontrée, risques maîtrisés et contrats disponibles. |
| Option séparée | Facturation native, paiements, signature et coffre-fort probant. | Arbitrage économique, juridique et fonctionnel dédié. |

### 13.1 Décisions avant développement

- Terminaux retenus, autonomie, réseau et durée maximale hors connexion.
- Liste nominative des validateurs et règles sanitaires applicables.
- Système maître par domaine et interfaces réellement accessibles.
- Droits par rôle, politique de conservation et périmètre propriétaire.
- Budget de saisie accepté par action après tests terrain.
- Contenu exact du P0 et critères de go/no-go.

## 14. Références de conception

La spécification a été consolidée à partir des documents Racing TrackTable, Racing Claudia, « Graffard Racing — Vis ma vie du 20 juillet 2026 » et Racing Processus et MCD VDraft 2. La direction visuelle s'inspire du site officiel Graffard Racing et de sa présentation institutionnelle premium. Les maquettes sources restent des inspirations : le présent document fait foi pour la cible fonctionnelle proposée.

Statut : base complète prête pour cadrage UX, ateliers métier et découpage en récits utilisateurs. Les règles sanitaires, juridiques, RH et les interfaces externes doivent être ratifiées avant mise en production.
