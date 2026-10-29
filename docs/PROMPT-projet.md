# Cibles du projet — gabarit à enrichir

Ce fichier est la SPEC que lit la garde de cible de plan. Le marqueur
`.agents/state/gates/PLAN_CIBLE_REQUIRED`, posé chez l'adoptant par la sync
template, porte `spec=docs/PROMPT-projet.md` et `chantier=*`.

`*` = toute tâche du board, avec ou sans chantier. Chaque étape d'un plan porte
donc au moins une valeur : `cible: « <nom> »` avec un des noms ci-dessous,
`angle mort: <question au pilote>`, ou `décision pilote: <id d'une décision
tracée>`. Sinon `done`, un `start` déjà approuvé et le verdict `plan-critic`
sont refusés ; la sortie tracée est `--sans-cible "<pourquoi>"`, et la raison
reste VISIBLE au board.

## Les sept cibles génériques

- **« zéro boîte noire »** — ce que fait le projet se relit après coup : une fonctionnalité qui réduit la traçabilité consultable est refusée.
- **« aucune suppression sans trace »** — rien n'est supprimé (fichier, donnée, test, règle) sans une trace écrite de quoi et de pourquoi.
- **« contrat déclaré »** — une interface publique est déclarée avant d'être livrée, et toute rupture est écrite.
- **« plan avant édition »** — aucune édition avant un plan approuvé, sauf une tâche DIRECTE estampillée par `tasks.py direct` : le code y vérifie un write-set déclaré sous la borne `MAX_FICHIERS_DIRECT`, aucun chemin de garde, ni décision ni sécurité ouverte, et `exec-critic`, la revue de sécurité, la revue de clôture et la porte restent dues.
- **« double revue avant clôture »** — aucune tâche close sans une revue critique tracée (UN critique : `critic-opus`, repli `critic-fable` puis `critic-sonnet-max`) ; le nom de la cible est gardé tel quel pour les plans qui la citent.
- **« aucun secret au dépôt »** — aucun credential, jeton ni clé n'entre dans le dépôt ; un secret exposé se retire et se fait tourner.
- **« tests au plus près du code »** — un test vit à côté du code qu'il éprouve, selon la convention de la stack.

## Enrichis ce fichier

Ces sept noms sont un point de départ générique. Un nom ajouté sur le modèle des
lignes ci-dessus (en gras, entre guillemets, en tête de puce) devient une cible
valide ; un nom retiré cesse de l'être. Garde un nom court et stable : les plans
le citent mot pour mot.

## À savoir

- Écart nommé : les définitions d'agents du kit disent de la cible de plan
  « hors chantier : rien ne change ». Sous `chantier=*` ce n'est pas vrai : une
  tâche SANS chantier est armée aussi — le premier plan qui omet ses cibles sera
  refusé une fois.
- Une recopie de la template (ou d'un checkout du kit) ÉCRASE ce fichier :
  sauvegarde-le avant si tu l'as enrichi.
- Désarmer la garde = retirer `.agents/state/gates/PLAN_CIBLE_REQUIRED`, geste du
  pilote du projet.
