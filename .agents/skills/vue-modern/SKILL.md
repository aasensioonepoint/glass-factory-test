---
name: vue-modern
description: Modern Vue and Nuxt conventions — Composition API with script setup, reactivity rules, props and events contracts, composables, Nuxt data fetching and rendering modes, testing. Use when writing, reviewing or refactoring Vue or Nuxt code.
---

# vue-modern

LIRE QUAND : tu ecris, relis ou refactores du Vue ou du Nuxt.

Aucune feuille `CONVENTIONS_vue.md` n'existe pour cette stack : **cette skill + la section `## vue / nuxt` de `DOCS_REGISTRY.md` SONT** la surface de conventions. Résidu du champ `conventions_file` → **T-00000436**.

## AUCUNE URL OFFICIELLE N'EST CITÉE ICI, ET C'EST MESURÉ

La section `## vue / nuxt` du registre ne porte aucune racine de documentation : ses deux entrées valent littéralement `source: à ré-établir — T-00000239`. Cette skill ne cite donc **aucune adresse**, et elle n'en invente pas.

Précision mesurée, parce qu'une formule trop large se lirait comme une panne plus grande qu'elle : deux adresses `vue`/`nuxt` existent bien ailleurs dans le registre, sur la puce `- vue/nuxt` de `### frameworks` sous `## typescript`. Elles ne sont pas reprises ici — c'est la SECTION de la stack qui fait autorité pour elle, et c'est elle qui est vide. Le résidu se referme en rétablissant ces deux racines-là.

Conséquence tenue à la ligne : **toute affirmation qui nomme un numéro de version porte le marqueur `à vérifier`**, sans exception. Ce n'est pas une précaution de style, c'est l'état réel du sourçage de cette stack dans ce dépôt — et il se referme en rétablissant les deux racines du registre, pas en supprimant les marqueurs.

## Composition et frontières

- `<script setup>` avec l'API de composition pour tout composant neuf. L'API par options reste lisible sur du code existant, mais elle ne compose pas : la logique partagée y redevient un mixin, et un mixin ne dit pas d'où vient une propriété.
- Un composant affiche et délègue. La logique réutilisable vit dans un **composable** (`useX()`), qui se teste sans monter le moindre composant.
- Un composable retourne de l'état et des actions, jamais un composant ni un élément du DOM. Un composable qui rend du balisage est un composant qui s'ignore.
- Un composable qui pose un écouteur, un intervalle ou un observateur le retire dans `onScopeDispose` / `onUnmounted`. Sans cela la fuite survit à la navigation et ne se voit qu'à la mémoire.
- Les `props` sont **en lecture seule**. Muter une prop marche parfois et casse le flux de données descendant ; l'enfant émet, le parent décide.

## Réactivité

- `ref()` par défaut, `reactive()` seulement pour un objet dont on ne déstructure jamais rien. La déstructuration d'un objet réactif **perd la réactivité** en silence — c'est la panne Vue la plus recopiée.
- L'état dérivé passe par `computed()`, jamais par un second `ref` tenu à jour à la main. Le champ synchronisé manuellement finit par diverger, et la divergence n'apparaît qu'à l'écran.
- `watch` avec une source explicite plutôt que `watchEffect` dès que les dépendances sont connues : `watchEffect` capture tout ce qu'il lit, y compris ce qu'on ne voulait pas suivre, et le déclenchement surnuméraire n'a pas de coupable lisible.
- Ne pas écrire dans un `computed` depuis un `watch` qui en dépend. Le cycle produit un rendu instable dont la trace ne nomme pas l'origine.
- `shallowRef` pour une grosse structure remplacée en bloc (résultat d'API, instance de bibliothèque tierce) : la réactivité profonde sur un objet volumineux coûte à chaque écriture, pour rien.

## Contrats de composant

- `props` et `emits` **déclarés et typés**, toujours. Un événement non déclaré traverse le composant sans contrat, et le parent le reçoit ou pas selon l'héritage d'attributs.
- Un `v-for` porte une `key` **stable et métier** — jamais l'index. L'index recycle le mauvais nœud dès qu'un élément est inséré au milieu, et ce qui se perd est l'état des enfants : focus, saisie en cours, sélection.
- `v-if` et `v-for` ne cohabitent pas sur le même élément : filtrer en amont dans un `computed`. La priorité entre les deux directives dépend de la version majeure du framework — à vérifier.
- Un slot nommé plutôt qu'une prop de configuration qui gonfle. Le jour où la prop devient un objet d'options, le composant a une deuxième API que personne ne documente.
- Jamais de `v-html` avec une donnée venue de l'utilisateur : c'est une injection de script directe, et c'est un défaut de sécurité de classe 1, pas une préférence de style.

## Nuxt

- Le mode de rendu se choisit **par route** et se déclare (`routeRules`), pas par défaut implicite. Une page statique servie en rendu serveur coûte un serveur pour rien ; une page personnalisée pré-rendue sert la donnée d'un autre utilisateur.
- La récupération de données passe par les composables dédiés du framework, jamais par un `fetch` nu dans `<script setup>` : le `fetch` nu s'exécute deux fois, une fois au serveur et une fois à l'hydratation, et double la charge sans que rien ne le signale.
- Aucun secret dans la configuration publique. Une clé posée du côté exposé de la configuration part dans le bundle client, où elle est lisible par tout le monde.
- Le code qui ne tourne qu'au serveur vit dans le répertoire serveur, jamais gardé par un simple test d'environnement dans un composant : un test d'environnement ne retire pas le code du bundle.
- L'auto-import masque l'origine d'un symbole : quand deux répertoires exposent le même nom, la règle de priorité est une règle de version — à vérifier.

## Versions

- Les règles qui supposent Vue 3.5 ou plus récent — nouvelles primitives de réactivité, changements de defaults — sont à vérifier avant application ; le numéro qui arbitre est celui de `vue` dans `package.json`.
- Les règles qui supposent Nuxt 3 ou plus récent, notamment sur la récupération de données et les règles de route, sont à vérifier ; le numéro qui arbitre est celui de `nuxt` dans `package.json`.
- Toute règle recopiée d'un tutoriel écrit pour la ligne 2 du framework est fausse ici par défaut : la réactivité, le montage et le contrat d'événements y diffèrent — à vérifier avant réemploi.

## Tests

- Le composable se teste **seul**, sans monter de composant. S'il faut un composant pour le tester, il porte du rendu qu'il ne devrait pas porter.
- Le composant se teste par le DOM rendu et par les événements émis, jamais par ses variables internes : un test qui lit l'implémentation rougit à chaque refactor sans mesurer un comportement.
- Requêter par rôle et par texte accessible plutôt que par sélecteur CSS ou par classe utilitaire. Un sélecteur de classe casse au premier changement de style.
- Les appels réseau sont doublés au niveau du transport, et chaque test **vérifie** qu'aucune requête n'est restée en attente.

## Où lire la suite

La section `## vue / nuxt` de `.agents/ref/DOCS_REGISTRY.md` porte la clé `kit_skill:` qui renvoie ici. Ses deux racines de documentation, elles, sont à rétablir — c'est le résidu nommé ci-dessus, et la raison pour laquelle cette skill ne cite aucune adresse officielle.
