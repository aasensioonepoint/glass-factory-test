---
name: angular-modern
description: Angular 20-22 conventions for signals, components, templates, HTTP, change detection and tests. Use when writing, reviewing or refactoring Angular code.
---

# angular-modern — Angular 20-22 — https://angular.dev/reference/releases

LIRE QUAND : tu écris, relis ou refactores du code Angular. Lis d'abord la version de `@angular/core` dans le `package.json` du projet ; applique la ligne correspondante du tableau et vérifie sa compatibilité avec l'`angular.json` local. La feuille `.agents/ref/CONVENTIONS_angular.md`, si elle est présente, complète cette skill.

## Versions prises en charge

| Version du projet | Support et choix de détection de changement | Source |
| --- | --- | --- |
| Angular 20 | LTS jusqu'au 2026-11-28 ; à partir de v20.2, activer explicitement `provideZonelessChangeDetection()` pour passer en zoneless et vérifier les polyfills. Sur v20.0-v20.1, vérifier l'API disponible avant migration. OnPush n'est pas le défaut : déclare `changeDetection: ChangeDetectionStrategy.OnPush` sur tout composant neuf. | https://angular.dev/reference/releases ; https://angular.dev/api/core/provideZonelessChangeDetection |
| Angular 21 | LTS ; zoneless est le défaut, sauf configuration explicite `provideZoneChangeDetection()`. OnPush n'est pas le défaut : déclare `changeDetection: ChangeDetectionStrategy.OnPush` sur tout composant neuf. | https://angular.dev/reference/releases ; https://angular.dev/guide/zoneless |
| Angular 22 | Active ; zoneless est le défaut et `ChangeDetectionStrategy.OnPush` est le défaut des composants ; `ChangeDetectionStrategy.Eager` reste le choix explicite pour les composants qui exigent la vérification empressée. | https://angular.dev/reference/releases ; https://angular.dev/guide/components/advanced-configuration |

La table est une photographie du support : reconsulte https://angular.dev/reference/releases avant une migration. Une application existante peut déroger aux défauts de sa version ; inspecte son bootstrap, ses composants et ses tests avant de modifier la détection de changement.

Hors 20-22 : n'applique aucune ligne par proximité ; dis-le au rapport et relis https://angular.dev/reference/releases .

## Composants et état

- Préfère les composants `standalone` pour le code neuf ; garde les `NgModule` là où ils portent une intégration existante. Sépare l'état de présentation de la logique métier réutilisable.
- Utilise `inject()` dans un contexte d'injection pour les services, gardes et intercepteurs ; ne l'appelle pas depuis une fonction ordinaire sans ce contexte. https://angular.dev/guide/di/dependency-injection-context
- Déclare une entrée avec `input()`, une sortie événementielle avec `output()` et une valeur modifiable par le parent avec `model()` ; `model()` crée aussi la sortie de changement correspondante. Choisis selon le contrat du composant, sans convertir mécaniquement les API existantes. https://angular.dev/guide/components/inputs ; https://angular.dev/guide/components/outputs
- Garde l'état local dans `signal()` et calcule l'état dérivé avec `computed()`. Réserve `effect()` à une synchronisation externe ; n'utilise pas un effet pour propager un état calculable. https://angular.dev/guide/signals
- Pour le mode zoneless, les mises à jour doivent notifier Angular : signal lu dans le template, `AsyncPipe`, événement lié ou `markForCheck()`. Dans un composant existant, vérifie ces notifications avant de retirer ZoneJS. https://angular.dev/guide/zoneless

## Gabarits, routes et HTTP

- Utilise `@if` pour les branches et `@for (...; track item.id)` avec une clé stable. Un index convient seulement à une collection statique ; une mauvaise clé perd l'état du DOM. https://angular.dev/guide/templates/control-flow
- Utilise `@defer` pour le contenu secondaire ; vérifie que les dépendances à différer sont `standalone` et ne sont pas aussi référencées hors du bloc. Évite de différer le contenu visible immédiatement. https://angular.dev/guide/templates/defer
- Diffère les routes secondaires avec `loadComponent` ou `loadChildren` lorsque le chargement initial le justifie. https://angular.dev/guide/routing/define-routes
- Configure les intercepteurs HTTP fonctionnels avec `provideHttpClient(withInterceptors([interceptorFn]))`. Un intercepteur peut utiliser `inject()` dans son contexte d'injection ; garde l'ordre explicite. N'écris aucun jeton en dur dans un intercepteur. https://angular.dev/guide/http/interceptors
- Garde la protection XSRF de `HttpClient` active et configure-la avec `withXsrfConfiguration()` quand le serveur utilise d'autres noms de cookie ou d'en-tête. https://angular.dev/best-practices/security#httpclient-xsrf-csrf-security
- Pour les formulaires non triviaux, préfère les formulaires réactifs typés. N'injecte pas directement une chaîne utilisateur dans `innerHTML` ; n'appelle jamais `bypassSecurityTrust*` sur une valeur issue de l'utilisateur. https://angular.dev/guide/forms/typed-forms ; https://angular.dev/best-practices/security

## RxJS et tests

- Donne une durée de vie aux souscriptions : `AsyncPipe` dans le template, ou `takeUntilDestroyed()` dans un contexte d'injection. Choisis `switchMap` pour annuler un travail précédent, `concatMap` pour sérialiser des écritures. https://angular.dev/ecosystem/rxjs-interop/take-until-destroyed
- Teste les services simples sans `TestBed` si leurs dépendances se passent directement. Teste les composants par le DOM et les interactions observables ; pour HTTP, utilise `HttpTestingController` et vérifie les requêtes en attente. https://angular.dev/guide/testing/services ; https://angular.dev/guide/http/testing
- Lis le `test` target d'`angular.json` : depuis v21, les nouveaux projets CLI utilisent Vitest (en v20, Karma) ; les projets existants peuvent encore utiliser Karma. Ne remplace pas le runner par supposition. https://angular.dev/guide/testing
- Dans le projet concerné, lance `ng build`, puis `ng test --watch=false` pour une exécution bornée ; lance `ng lint` seulement si la cible `lint` existe dans `angular.json`. Avec npm, les drapeaux passent après `--` : `npm run ng -- test --watch=false` (mesuré avec npm 11 : sans `--`, npm garde le drapeau pour lui et Karma reste en watch). https://angular.dev/cli/build ; https://angular.dev/cli/test ; https://angular.dev/cli/lint

## Sources et provenance

Règles adaptées de `angular/skills`, skill `angular-developer`, au commit `b1eb9a0a5e156a3640b07cfdd86a136abc65f31f` : https://github.com/angular/skills/blob/b1eb9a0a5e156a3640b07cfdd86a136abc65f31f/angular-developer/SKILL.md . Son frontmatter déclare la licence MIT et `Copyright 2026 Google LLC`. La présente rédaction est propre au kit ; les liens officiels ci-dessus fondent les choix versionnés.

La section `## angular` de `.agents/ref/DOCS_REGISTRY.md` porte les racines documentaires et la clé `kit_skill:` qui renvoie ici. Ouvre la page officielle précise au besoin.
