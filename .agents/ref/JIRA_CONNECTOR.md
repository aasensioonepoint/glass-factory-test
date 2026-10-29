# Connecteur Jira Cloud du board

Le connecteur importe des tickets Jira dans le board local et peut signaler une
prise en ajoutant un label sur le ticket d'origine. Il utilise l'API REST v3 de
Jira Cloud. Les commandes du moteur sont `jira-import` et `jira-claim` ; leur
forme exacte est suivie dans `TASKS_CLI_CONTRACT.md`.

## Configuration

- `CADRE_JIRA_SITE` : URL du site, par exemple
  `https://groupeonepoint.atlassian.net`.
- `CADRE_JIRA_EMAIL` : adresse du compte Jira qui porte le jeton. Choisir un
  compte autorisé à lire le projet et, pour la prise, à modifier ses tickets.
- À défaut de ces variables, le connecteur peut lire le site et l'e-mail dans
  `~/.config/cadre/jira.json`, fichier local **hors du dépôt** limité à ces deux
  valeurs. Aucun jeton n'y figure.
- `JIRA_API_TOKEN` : jeton fourni par l'environnement du processus. À défaut,
  dans Trousseaux d'accès, créer un élément « mot de passe » avec le service
  `cadre-jira`, le compte égal à l'e-mail du fichier local, et le jeton comme
  mot de passe. Ne placer le jeton ni dans les arguments de commande, ni dans
  un fichier de configuration ou du dépôt.

Le trousseau macOS n'est lu que pour le site et l'e-mail de
`~/.config/cadre/jira.json`. Un site ou un e-mail d'environnement différent est
refusé. Aucun trousseau n'est lu pour `http://localhost` ou
`http://127.0.0.1` ; les bancs utilisent un jeton d'environnement ou un
trousseau simulé. La recherche est limitée à 50 pages ; au-delà, l'import est
refusé.

Le projet prévu pour ce site est `GNTC`. L'absence de site ou d'e-mail est une
erreur d'usage (code 2) avant toute requête réseau ou consultation du trousseau.
Le site distant doit être un domaine `*.atlassian.net` ; `localhost` et
`127.0.0.1` servent seulement aux bancs avec un faux Jira local.

## Configuration guidée

`python3 .agents/bin/jira_setup.py` a trois verbes (décision pilote
S-01M5FQ7YS37N3HV9BQ1B32S0HQ) :

- `etat` lit `~/.config/cadre/jira.json` seul et nomme la source du jeton,
  sans consulter le trousseau. `JIRA_API_TOKEN` d'environnement est
  prioritaire.
- `verifier` est en lecture seule. Il fait trois `GET` : `/myself`,
  `/project/<CLÉ>`, puis `/mypermissions` pour `BROWSE_PROJECTS`,
  `CREATE_ISSUES`, `EDIT_ISSUES`, `TRANSITION_ISSUES` et `ASSIGN_ISSUES`. Il
  imprime une ligne par droit.
- `configurer [--changer-jeton]` se joue uniquement au terminal du pilote. Il
  rend le code 2 sans rien écrire sous un marqueur d'agent (la liste fait foi
  dans le tuple `tracabilite_jira.AGENT_CALLER_MARKERS`), quand un argument commence par
  `--tok` ou `--jet`, ou quand stdin n'est pas un terminal. Dans ces cas, il
  imprime la commande à taper.

Les étapes de `configurer` suivent toujours le même ordre :

1. demander le site, le projet et l'e-mail ;
2. valider l'e-mail (254 caractères au plus) et la clé du projet ;
3. écrire `jira.json` (`site`, `email`, `project`) en mode 0600 ;
4. consulter le trousseau et le presse-papiers.

Si l'élément `cadre-jira` existe déjà pour cet e-mail, aucune saisie n'est
demandée et la vérification part directement. S'il est absent, ou si
`--changer-jeton` est passé, le jeton est lu dans le presse-papiers. Il est
aussi lu quand Jira répond 401 ou 403 et que le pilote accepte le
remplacement. Le jeton doit compter 16 à 1024 caractères pris dans
`[A-Za-z0-9_=+/.-]`. Il est écrit par `security -i`, la commande arrivant sur
stdin et jamais dans les arguments. La sortie de `security` est caviardée, puis
le presse-papiers est vidé.

`setup_projet.py` propose cette configuration avec la question
`Board : local ou Jira ? [L/j]`. Le choix par défaut est local. La question
n'est pas posée sous `--dry-run`, sous un agent ou sans terminal.

Bornes :

- macOS 26 garde un historique du presse-papiers que le vidage ne purge pas.
  Le jeton copié peut y rester.
- Lancée par `setup_projet.py`, la configuration a 900 s pour finir. Au-delà,
  `jira_setup.py` est tué sans pouvoir vider le presse-papiers : videz-le
  vous-même si vous y aviez copié le jeton.
- Le contrôle du terminal ne détecte pas un agent lancé sous un pty. Un hôte
  qui ne pose aucun marqueur d'agent dans son shell, comme Codex, passe ce
  contrôle. Seule la doctrine lui interdit alors `configurer`.
- Hors macOS, aucun trousseau n'est écrit. Le jeton doit venir de
  `JIRA_API_TOKEN`.
- L'écriture est jugée sur le code de retour de `security -i` et sur la
  présence de l'élément ; un échec est dit sans le jeton. Mesuré : une
  commande interne en échec propage son code (44 sur un élément absent, 1 sur
  `-25300` ou une commande inconnue). Un stderr non vide sous un code nul est
  DIT, caviardé, sans compter comme un échec. NON mesurés : le stderr d'un
  `add-generic-password -U` réussi, et un `-U` en échec sur un élément
  existant ; dans ce dernier cas l'ancien élément reste présent, et seul
  `jira_setup.py verifier` (401 sur un jeton périmé) le révèle.

## Import et prise

`python3 .agents/bin/tasks.py jira-import --project GNTC` lit les tickets non
terminés du projet par pages. `--issue CLÉ` limite l'import à un ticket.
L'identité Jira évite les doublons. Une identité supprimée du board ne peut
pas être réimportée par la même commande.

Après une prise Git admise, le connecteur tente d'ajouter au ticket le label
`pris-par-<acteur>`. Si un jeton est disponible, cette tentative est active par
défaut. `JIRA_AGENT_CLAIM=0` la désactive. Une panne Jira laisse une attente
locale ; `python3 .agents/bin/tasks.py jira-claim --retry T-…` retente la prise
pour la tâche indiquée. Les diagnostics et les traces ne doivent contenir ni
jeton ni en-tête d'authentification. Un avis du connecteur ne prend pas le
préfixe `REVENDICATION:`, réservé au refus de prise Git.
Le board conserve l'e-mail de l'acteur dans la fiche ; le label Jira
`pris-par-...` inclut un slug dérivé de cet e-mail, visible par les personnes
ayant accès au ticket.

### Transfert de propriété

Quand la propriété d'une tâche passe à un autre pilote (reprise motivée depuis
son terminal, décision pilote S-01M5HH8QMC4E7SYN4K6AP2SMKE), le board garde
l'intention Jira du transfert : le nouveau label dans `jira_claim_label`,
l'ancien dans `jira_claim_retrait`, statut `attente`. Le connecteur tente un
seul `PUT` qui retire l'ancien label et ajoute le nouveau. L'intention n'est
acquittée qu'après un HTTP 204 ; sinon elle reste en attente pour
`python3 .agents/bin/tasks.py jira-claim --retry T-…`. Sans Jira configuré,
la propriété du board tient et l'intention reste en attente.

`jira_request` n'admet un retrait que pour la tâche qui le porte : clé du
ticket égale à sa `jira_key`, labels retirés pris dans son
`jira_claim_retrait`, ajout égal à son `jira_claim_label`. Un remplacement de
labels (`fields.labels`, opération `set`) est refusé. Sous un marqueur d'agent
(`agent_appelant()`), aucun retrait n'est admis : `jira-claim --retry` laisse
alors le transfert en attente et le dit ; le pilote le relance depuis son
terminal.

`--dry-run` permet de prévisualiser l'opération sans créer de tâche ni envoyer
de `PUT` de label. Pour un import, la lecture `GET` de Jira peut encore avoir
lieu : utiliser le faux serveur local si aucune requête réelle n'est voulue.

### Deux clones, un même ticket

L'enregistrement importé ne garde pas la date `updated` de Jira : son champ
`updated` est la date de création du ticket. Deux clones qui importent le même
ticket sans que son résumé, son type ni son parent aient changé dans Jira entre
les deux imports écrivent donc les mêmes octets, quelle que soit la date
`updated` de Jira, et un `git merge` sans pilote de fusion reste propre
(arbitrage orchestrateur S-01M5HAKRWKB2N5NBPASPWN3R4Y, sur l'import existant
arbitré par S-01M5GZ4TQQ985TWGAV508ZAFB6). Un parent déplacé ou un type
renommé dans Jira entre les deux imports donne des octets différents : conflit
sans pilote ; avec lui, conflit nommé `record/jira_parent_key` ou
`record/jira_type`.

Avec le pilote `cadre-enregistrement` installé dans le clone
(`python3 .agents/bin/fusion_enregistrement.py --installer`, geste du pilote),
deux ajouts du même ticket dont l'un porte des éditions locales (`start`,
`stage`, prise Jira) se fusionnent. La base de cette fusion est l'enregistrement
d'import, reconstruit depuis la liste fermée `task`, `jira_updated` s'il existe,
`jira_site`, `jira_issue_id`, `jira_created`, `jira_key`, `jira_url`,
`jira_type` et `jira_parent_key`. Ces champs doivent concorder des deux côtés,
et l'opération d'import `uuid5(jira:<site>|<id>)` doit figurer dans les deux
`sync_operations`, dont la fusion garde l'union. Les autres champs suivent les
règles à trois voies du pilote, acteurs compris. Une copie posée avant cette
version garde l'ancien comportement (conflit) : `--verifier` la dit `périmé`
et `.githooks/post-merge` alerte ; relancer `--installer`.

Deux résumés différents restent un conflit nommé `record/task` : rien de
persisté ne dit lequel est le plus récent dans Jira. Un `tasks.py retitle`
local, d'un seul côté, avant la première fusion, sort sous le même nom : la
base ne connaît que le titre importé. Un autre champ divergent
de la liste, une provenance incomplète ou une opération d'import absente sont
aussi des conflits nommés. Sans pilote, deux ajouts aux octets différents
restent en conflit, comme avant.

Retour arrière : rétablir le pilote, puis relancer `--installer` et
`--verifier` dans chaque clone ; les enregistrements déjà fusionnés restent.

## Extension

Sous un agent, `jira_request` permet seulement d'ajouter le label de prise à
un ticket Jira. Toute autre écriture est refusée, retrait de label compris.
Hors agent, un retrait reste lié au transfert de la tâche (section
« Transfert de propriété »). Les futures transitions ou
créations de sous-tâches devront étendre explicitement cette liste fermée.

## Bancs et livraison

Les bancs emploient un serveur Jira simulé sur `localhost`, fidèle à
`GET /rest/api/3/search/jql` paginé et au `PUT` des labels (ajout, ou
retrait et ajout lors d'un transfert).
Ils ne contactent jamais un Jira réel et ne requièrent aucune variable `JIRA_*`
dans la porte adoptant. Le manifeste `pyproject.toml` du kit est exclu du
modèle adoptant ; la wheel du kit, elle, doit embarquer `tasks_jira.py`,
`tracabilite_jira.py`, `etat_lecture.py` et `ledger.py` lors de l'intégration.
