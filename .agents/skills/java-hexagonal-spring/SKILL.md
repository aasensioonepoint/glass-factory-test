---
name: java-hexagonal-spring
description: Java 25 and Spring conventions, Spring Boot 4 on Spring Framework 7, with the Framework 6 line still labelled — hexagonal or n-tier boundaries held by ArchUnit, constructor injection, transactions, SecurityFilterChain, MockitoBean and Testcontainers ServiceConnection tests. Use when writing, reviewing or refactoring Java or Spring code.
---

# java-hexagonal-spring

LIRE QUAND : tu ecris, relis ou refactores du Java ou du Spring.

La feuille `.agents/ref/CONVENTIONS_java.md` existe et porte la couche langage et porte (types, frontières, bancs, SCA), les arborescences de reference et les tests d'architecture sous `src/test` ; **cette skill + la section `## java / kotlin` de `DOCS_REGISTRY.md`** portent le fond, la couche Spring et hexagonale — lis les deux, et lis la feuille avant de creer un module ou un paquet : elles ne sont PAS disjointes (entre autres `record`, `Optional` en retour, exception jamais avalée, champ `final`, domaine testé en JUnit nu figurent des deux côtés ; la feuille y ajoute le détail de porte), et un désaccord entre elles est un défaut à signaler. Kotlin a sa propre feuille, `.agents/ref/CONVENTIONS_kotlin.md`, que `language-detector` ne nomme pas (aucun jeton `kotlin` dans son jeu fermé) : résidu à ouvrir après T-01M5BZBWTT.

## Cible de version, et ce qu'elle n'affirme pas

- La cible du kit est **Java 25** (LTS) avec **Spring Boot 4** sur **Spring Framework 7** — https://docs.oracle.com/en/java/javase/25/ .
- Spring Boot 4 n'EXIGE PAS Java 25 : son minimum est Java 17, et Java 25 est dans sa plage de compatibilite. Ne jamais ecrire l'inverse dans un plan ou un README — https://docs.spring.io/spring-boot/system-requirements.html .
- La ligne stable de Boot 4 avance (4.0 puis 4.1) : ne fige jamais un numero mineur comme « derniere version », lis la page des prerequis du jour — https://docs.spring.io/spring-boot/system-requirements.html .
- Un adoptant encore sur Framework 6 garde ses regles `[FW6]` : la cible du kit n'est pas la version du projet, c'est son manifeste (`pom.xml`, `build.gradle*`) qui la dit.

## Les étiquettes de version, et pourquoi elles sont obligatoires

Spring n'a pas une version, il en a deux qui cohabitent chez les adoptants, et une règle vraie sur l'une peut être fausse sur l'autre. Une règle sans étiquette se lit donc comme universelle et se retrouve appliquée là où elle ne vaut pas — c'est la faute que ce jeu fermé ferme.

Jeu **fermé** de cinq étiquettes, une par règle, jamais deux :

| étiquette | portée |
|---|---|
| `[FW6]` | la ligne Framework 6.x seulement |
| `[FW7]` | la ligne Framework 7.x seulement |
| `[FW6+7]` | vrai sur les deux lignes de version |
| `[BOOT]` | vaut parce que Spring Boot est là (auto-configuration, starters) |
| `[HORS-BOOT]` | Spring Framework nu, sans Boot — le cas que tout le monde oublie |

« Hexagonal » et « n-tier » ci-dessous sont des STYLES d'architecture, pas des étiquettes : ils titrent des sous-sections, le jeu fermé reste à cinq.

Toute ligne de règle qui NOMME un numéro de version porte sa source (`https://`) ou le marqueur `à vérifier`. `à vérifier` n'est pas une excuse : c'est une dette adressée au pilote, et elle se ferme en relisant la source officielle.

## Règles étiquetées

### Architecture hexagonale

- [FW6+7] Le domaine n'importe aucun type `org.springframework`. Pas d'annotation, pas d'`ApplicationContext`, pas de `@Component` : un domaine qui dépend du conteneur ne se teste plus sans lui, et la dépendance ne se voit qu'au démarrage.
- [FW6+7] Un port est une interface **déclarée par le domaine** et implémentée par l'infrastructure. Exposer un `JpaRepository` au domaine inverse la dépendance : le domaine se met alors à parler JPA, et la couche qu'on voulait isoler porte le vocabulaire de la base.
- [FW6+7] Un adaptateur traduit, il ne décide pas. Toute règle métier trouvée dans un `@RestController` ou dans un `@Repository` est une règle que le test unitaire du domaine ne couvre pas.
- [FW6+7] L'entité JPA n'est pas l'agrégat du domaine. Les fusionner marche jusqu'au premier besoin de mapping divergent, puis fige le schéma de base dans la signature des cas d'usage.
- [FW6+7] La frontière se TESTE, elle ne se promet pas : un test ArchUnit `Architectures.onionArchitecture()` déclare `domainModels`, `domainServices`, `applicationServices` et un `adapter(...)` par adaptateur, et rougit au premier import qui traverse — https://www.archunit.org/userguide/html/000_Index.html . Deux adaptateurs ne dépendent jamais l'un de l'autre : c'est la règle que ce style ajoute et qu'aucune revue ne tient seule.
- [FW6+7] Une règle jMolecules à la place d'ArchUnit nu ne se prescrit qu'après avoir lu son API dans le dépôt officiel ; tant qu'aucun nom de méthode n'y est relu, écris le test avec `onionArchitecture()` — https://github.com/xmolecules/jmolecules .

### Architecture n-tier

- [FW6+7] En n-tier (contrôleur → service → persistance), le sens des appels est la seule frontière : il se tient par `Architectures.layeredArchitecture().consideringAllDependencies()`, une couche par paquet, `whereLayer(...).mayOnlyBeAccessedByLayers(...)` sur chacune — https://www.archunit.org/userguide/html/000_Index.html .
- [FW6+7] Un projet n-tier n'est pas un hexagonal raté : ne le force pas en ports et adaptateurs sans décision, et ne lui applique pas le test de l'autre style — un test qui ne décrit pas l'architecture réelle rougit à tort ou passe à vide.

### Injection et cycle de vie

- [FW6+7] Injection par **constructeur**, jamais par champ. Un champ `@Autowired` rend le bean inconstructible en test sans conteneur, autorise un état non initialisé, et repousse la découverte d'un cycle de dépendances au démarrage de l'application.
- [FW6+7] Un champ injecté par constructeur est `final`. C'est ce qui rend la dépendance manquante visible à la compilation plutôt qu'au runtime.
- [FW6+7] `@Value` sur un champ est un raccourci coûteux : préférer un type `@ConfigurationProperties` validé, qui rend le contrat de configuration lisible en un seul endroit et échoue au démarrage plutôt qu'à la première requête.
- [BOOT] Ne jamais recréer par `@Bean` ce que l'auto-configuration fournit déjà sans avoir lu la classe d'auto-configuration correspondante — https://docs.spring.io/spring-boot/reference/ . Une redéfinition silencieuse désactive des réglages que personne ne sait plus nommer.
- [HORS-BOOT] Sans Boot il n'y a **aucune** auto-configuration : `DataSource`, `TransactionManager`, `ObjectMapper` et le serveur web sont à déclarer à la main. Une règle écrite pour Boot recopiée ici produit un contexte qui ne démarre pas, et le message d'erreur ne nomme pas la cause.

### Transactions

- [FW6+7] `@Transactional` appartient à la couche **application** (le cas d'usage). Sur le contrôleur elle garde la transaction ouverte pendant la sérialisation ; sur le repository elle découpe un cas d'usage en N transactions indépendantes, donc en N points de cohérence perdus.
- [FW6+7] Un appel **interne** à une méthode `@Transactional` du même bean ne traverse pas le proxy : la transaction n'est pas ouverte, et rien ne le signale. Elle se corrige en déplaçant la méthode dans un autre bean, jamais en ajoutant une annotation.
- [FW6+7] `@Transactional(readOnly = true)` sur les lectures : ce n'est pas une décoration, c'est ce qui évite le flush automatique du contexte de persistance en fin de méthode.
- [FW6+7] Une exception **contrôlée** ne déclenche pas le rollback par défaut. Si le cas d'usage lève une exception métier contrôlée, la transaction **commit** — comportement documenté, jamais intuitif : https://docs.spring.io/spring-framework/reference/ .

### Couche web

- [FW6] Spring Framework 6.x — le client HTTP synchrone de référence pour du code neuf est `RestClient` ; `RestTemplate` reste supporté mais n'est plus le point de départ recommandé. Version d'introduction de `RestClient` : à vérifier — https://docs.spring.io/spring-framework/reference/ .
- [FW7] Spring Framework 7.x change des defaults et retire des API dépréciées de la ligne précédente : lire les notes de version **avant** de recopier une règle 6.x, notamment sur le client HTTP et la configuration web — https://docs.spring.io/spring-framework/reference/ .
- [BOOT] Spring Boot 4 renomme les starters web : `spring-boot-starter-web` est déprécié au profit de `spring-boot-starter-webmvc`, et Jackson 3 devient la bibliothèque JSON préférée. Vérifie les starters et les dépendances de test au passage de 3 à 4 — https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide .
- [FW6+7] Le DTO d'entrée borne les champs acceptés ; `@Valid` valide ses contraintes, il ne filtre pas les champs. Ne lie jamais une entité directement à la requête : cela ouvre l'écriture de champs que le client n'a pas le droit de toucher.
- [FW6+7] Une exception métier se traduit en réponse HTTP dans un `@RestControllerAdvice` unique, pas dans chaque contrôleur. Deux traductions concurrentes du même cas produisent deux codes de statut pour la même faute.
- [BOOT] Les endpoints Actuator exposés sont à énumérer explicitement, jamais laissés au défaut d'une version antérieure recopiée — https://docs.spring.io/spring-boot/reference/ .

### Sécurité

- [FW6+7] La configuration web de Spring Security est un bean `SecurityFilterChain` construit sur `HttpSecurity` ; on n'étend aucune classe de base de configuration. Une chaîne par périmètre (API, actuator), chacune avec son `securityMatcher` — https://docs.spring.io/spring-security/reference/servlet/configuration/java.html .
- [FW6+7] Toute route est fermée par défaut (`anyRequest().authenticated()` en dernier) ; une ouverture se nomme, une fermeture ne s'oublie pas. Ne désactive CSRF que pour une API stateless authentifiée par jeton en en-tête, jamais pour une session cookie.
- [FW6+7] Aucun secret en dur dans `application*.yml` : fournis-le par une variable d'environnement ou un coffre de secrets ; ne le journalise pas.
- [FW6+7] Toute requête SQL ou JPQL utilise des paramètres liés, jamais une chaîne concaténée avec une entrée externe.
- [FW6+7] Ne désérialise jamais une entrée externe avec `ObjectInputStream` ni avec le polymorphic typing de Jackson.

### Langage

- [FW6+7] Java 25 : `record` pour les DTO et les value objects, `sealed` pour fermer une hiérarchie métier, pattern matching de `switch` pour la traiter sans branche oubliée — https://docs.oracle.com/en/java/javase/25/ .
- [FW6+7] Threads virtuels : à activer par décision mesurée, jamais par défaut recopié ; un code qui épingle le thread porteur (bloc `synchronized` long autour d'une I/O) perd le gain — https://docs.oracle.com/en/java/javase/25/ .
- [FW6+7] `Optional` en type de **retour**, jamais en champ ni en paramètre : en champ il n'est pas sérialisable proprement, en paramètre il déplace la décision chez l'appelant sans la rendre plus sûre.
- [FW6+7] Une exception ne s'avale pas. `catch (Exception e) {}` est le mécanisme qui fait disparaître une panne : au minimum re-lever en enrichissant, sinon journaliser avec la cause.

### Tests

- [BOOT] Une **slice** (`@WebMvcTest`, `@DataJpaTest`) plutôt qu'un `@SpringBootTest` complet dès que la slice suffit : le contexte complet est lent, et sa lenteur est ce qui fait qu'on arrête d'écrire des tests.
- [BOOT] Doublure d'un bean dans un test Spring : `@MockitoBean`. L'ancien `@MockBean` de Boot est retiré dans Boot 4 et remplacé par `@MockitoBean` ; de même `@SpyBean` est retiré et remplacé par `@MockitoSpyBean` — https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide . Ces annotations se posent sur les champs de la classe de test, pas dans une classe `@Configuration`.
- [BOOT] Testcontainers plutôt qu'une base en mémoire pour tout test qui touche SQL, branché par `@ServiceConnection` sur le conteneur déclaré : Boot en dérive l'URL et les identifiants, sans propriété recopiée à la main — https://docs.spring.io/spring-boot/reference/testing/testcontainers.html . Une base en mémoire valide une syntaxe que la base de production refuse.
- [BOOT] Le test d'architecture (`onionArchitecture()` ou `layeredArchitecture()` selon le style réel) vit sous `src/test` et tourne dans la commande de test ordinaire : un test d'architecture lancé à part est un test qu'on oublie — https://www.archunit.org/userguide/html/000_Index.html .
- [HORS-BOOT] Sans Boot, le contexte de test se construit à la main (`@ContextConfiguration`) et les slices n'existent pas : un test recopié d'un projet Boot ne démarre pas ici.
- [FW6+7] Le domaine se teste **sans** Spring, en JUnit nu — https://junit.org/junit5/docs/current/user-guide/ . Si un test du domaine a besoin du conteneur, c'est la frontière hexagonale qui a fui, pas le test qui est mal écrit.

## Commandes de vérification

Lance la commande du wrapper PRÉSENT dans le projet, jamais celle d'un outil installé à côté :

- `mvnw` à la racine : `./mvnw -B verify`.
- `gradlew` à la racine : `./gradlew test`.
- Aucun wrapper : dis-le dans ton rapport, ne devine pas un outil global.

Une commande de lint (Checkstyle, Spotless, PMD…) ne se lance QUE si son plugin est déclaré dans `pom.xml` ou `build.gradle*` ; un lint absent du manifeste ne s'invente pas. La feuille `.agents/ref/CONVENTIONS_java.md` porte le détail par outil.

Une montée de version (Java ou Spring) relève d'une skill de migration : si `.agents/skills/java-migration/SKILL.md` existe dans le dépôt, lis-la ; sinon, cette skill ne couvre pas la migration, et le guide officiel de migration de Boot est la seule référence à suivre.

## Sources et provenance

Cette skill est une **synthèse originale**, rédigée pour le kit : aucune copie substantielle, aucune recette importée. Sources consultées le 2026-10-23, à relire avant de durcir une règle :

- rrezartprebreza/spring-boot-skills — licence MIT — https://github.com/rrezartprebreza/spring-boot-skills/blob/main/LICENSE
- sivaprasadreddy/sivalabs-agent-skills — licence MIT — https://github.com/sivaprasadreddy/sivalabs-agent-skills/blob/main/LICENSE
- Documentation officielle : prérequis de Spring Boot — https://docs.spring.io/spring-boot/system-requirements.html ; guide de migration de Boot 4 — https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide ; ArchUnit — https://www.archunit.org/userguide/html/000_Index.html ; Spring Security — https://docs.spring.io/spring-security/reference/servlet/configuration/java.html .

## Où lire la suite

La section `## java / kotlin` de `.agents/ref/DOCS_REGISTRY.md` porte les racines officielles (Java, Spring Boot, Spring Framework, Spring Data, Spring Security, Gradle, Maven, JUnit, Testcontainers, ArchUnit) et la clé `kit_skill:` qui renvoie ici. Ouvre la page précise dont tu as besoin, ne recopie jamais son contenu dans le contexte parent.
