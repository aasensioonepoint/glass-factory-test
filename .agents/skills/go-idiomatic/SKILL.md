---
name: go-idiomatic
description: Idiomatic Go conventions — errors as values, context propagation, interfaces at the consumer, goroutine lifetime and ownership, table tests. Use when writing, reviewing or refactoring Go code.
---

# go-idiomatic

LIRE QUAND : tu ecris, relis ou refactores du Go.

La feuille `.agents/ref/CONVENTIONS_go.md` existe (T-00000488) et porte les règles de porte ; cette skill + la section `## go` de `DOCS_REGISTRY.md` portent le fond. Résidu `conventions_file` → **T-00000449** (T-00000436 est close).

## La règle avant les règles

Go n'a presque pas de style à débattre : `gofmt` tranche la forme, `go vet` tranche une partie du fond. Ce qui reste à décider tient dans quatre sujets — les erreurs, le `context`, la propriété d'une goroutine, et où vit une interface. Le reste est du bruit.

Toute affirmation qui NOMME un numéro de version porte sa source (`https://`) ou le marqueur `à vérifier` : la directive `go` du `go.mod` change la sémantique du langage, donc une règle non datée est une règle non vérifiable.

## Erreurs

- Une erreur est une **valeur**, pas un événement. On la retourne, on ne la lève pas — et le point de décision est chez l'appelant, à la ligne suivante, jamais dix cadres plus haut.
- `if err != nil { return err }` **nu** perd le lieu de la faute. Envelopper avec `fmt.Errorf("ouverture de %s : %w", nom, err)` : le `%w` conserve la chaîne pour `errors.Is` / `errors.As`, un `%v` la coupe.
- Comparer par `errors.Is` (valeur sentinelle) et `errors.As` (type), jamais par `err.Error() == "…"`. Une comparaison de chaîne casse le jour où le message est reformulé, et rien ne le signale.
- Une erreur sentinelle est exportée et déclarée une seule fois (`var ErrIntrouvable = errors.New("introuvable")`). Deux sentinelles pour la même condition rendent `errors.Is` faux pour un appelant sur deux.
- `panic` est réservé à l'impossible — un invariant de programme violé, pas une entrée utilisateur invalide. Une bibliothèque qui `panic` sur une donnée d'entrée impose son mode de défaillance à tous ses appelants.
- Ne jamais ignorer une erreur par `_ =` sans un commentaire disant pourquoi elle est ignorable. C'est le seul mécanisme qui distingue un choix d'un oubli à la relecture.

## Context

- `context.Context` est le **premier** paramètre, nommé `ctx`, et il ne se stocke jamais dans une structure. Un `ctx` en champ survit à la requête qui l'a créé, donc son annulation ne veut plus rien dire.
- Tout appel bloquant — réseau, base, verrou d'attente — prend le `ctx` et l'honore. Un appel qui l'ignore rend l'annulation cosmétique : le serveur répond, la goroutine continue.
- `context.WithTimeout` retourne un `cancel` qui s'appelle **toujours**, en `defer`, y compris sur le chemin d'erreur. Ne pas l'appeler fuit le timer jusqu'à l'échéance.
- `context.Value` transporte des données de requête (trace, identité), jamais des dépendances. Une dépendance passée par le contexte est une dépendance que la signature ne déclare pas et que le compilateur ne vérifie pas.

## Concurrence

- Une goroutine a un **propriétaire** : celui qui la démarre sait comment elle s'arrête. Une goroutine lancée sans réponse à cette question est une fuite qui ne se voit qu'en production, à la mémoire.
- Ne jamais démarrer une goroutine dans une bibliothèque sans donner à l'appelant le moyen de l'attendre ou de l'annuler. Sinon la durée de vie appartient à la bibliothèque et le programme ne peut plus s'arrêter proprement.
- Le canal est possédé par l'**écrivain** : c'est lui qui ferme, jamais le lecteur. Fermer côté lecture provoque une panique sur l'écriture concurrente, et la trace ne nomme pas le fautif.
- Un `sync.Mutex` protège des champs nommés, pas « la structure ». Écrire au-dessus du mutex quels champs il garde est ce qui permet à la relecture suivante de voir l'accès non protégé.
- `-race` sur les tests de tout code concurrent, en CI. Une course de données ne se reproduit pas à la demande : elle se détecte ou elle passe.

## Interfaces et API

- L'interface se déclare **chez le consommateur**, pas chez le producteur. Une interface exportée à côté de son unique implémentation est un couplage inutile ; l'appelant déclare le petit contrat dont il a besoin, et le test le double sans effort.
- Petites interfaces : une ou deux méthodes. `io.Reader` est le modèle, pas l'exception.
- Retourner des types **concrets**, accepter des interfaces. L'inverse prive l'appelant des méthodes qu'il aurait pu utiliser, sans rien lui garantir de plus.
- Zéro valeur utilisable : une structure dont le zéro fonctionne évite un constructeur, et donc évite toute une classe d'états non initialisés. `sync.Mutex` et `bytes.Buffer` sont les modèles — https://pkg.go.dev/std .
- Pas de `getters` préfixés `Get`. Le champ ou la méthode se nomme par ce qu'il rend — https://go.dev/doc/effective_go .

## Modules, versions et outillage

- La directive `go` du `go.mod` fixe la sémantique du langage : une règle qui suppose une version plus récente que celle-ci ne compile pas, ou compile autrement — https://go.dev/doc/ .
- Les génériques et `any` sont disponibles depuis la ligne 1.18 du langage ; l'itérateur de boucle par valeur unique par itération a changé plus tard. La version exacte de ce changement de sémantique est à vérifier — https://go.dev/doc/ .
- Les fonctions de la bibliothèque standard récentes (`slices`, `maps`, `min`/`max` intégrés) ne sont pas disponibles sur toutes les directives `go` : leur version d'apparition est à vérifier — https://pkg.go.dev/std .
- `go vet` et `gofmt` en CI, sans exception. Ce sont les deux seuls contrôles que tout le monde dans l'écosystème accepte sans discussion, donc les seuls qui ne coûtent rien à imposer.

## Tests

- Tests **en table**, sous-tests nommés par `t.Run`. Le nom du sous-test est ce qui apparaît en cas d'échec : `cas 3` ne dit rien, `entree_vide` dit tout.
- `t.Parallel()` dans les sous-tests dès que le cas le permet, et la variable de cas capturée explicitement si la sémantique de la boucle de la version cible ne le fait pas — https://go.dev/doc/ .
- `t.Cleanup` plutôt qu'un `defer` en fin de test : il s'exécute aussi quand le test échoue par `t.Fatal`.
- `t.TempDir()` plutôt qu'un chemin temporaire construit à la main — il est nettoyé, et il est unique par test parallèle.
- Le test compare la **valeur**, jamais le message d'erreur formaté. Un message est de la prose ; le jour où il change, le test rougit sans qu'aucun comportement n'ait bougé.

## Où lire la suite

La section `## go` de `.agents/ref/DOCS_REGISTRY.md` porte les racines officielles (doc du langage, bibliothèque standard, Effective Go) et la clé `kit_skill:` qui renvoie ici. Ouvre la page précise dont tu as besoin, ne recopie jamais son contenu dans le contexte parent.
