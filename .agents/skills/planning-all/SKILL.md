---
name: planning-all
description: Plan an ORDERED BATCH — closes the scope over depends_on, plans wave by wave, and returns ONE night_approve line to type. Preparation only; the gate stays the pilot's gesture. Usage — /planning-all [T-NNN …|--workstream X] (the former `--chantier X` still accepted)
---

# planning-all — le lot ordonné, et la ligne unique

## Quand lire ce fichier

Avant `/planning-all`, ou quand une nuit doit dépiler **plusieurs tâches liées**
plutôt qu'une liste choisie à la main.

Pour planifier 5 tâches indépendantes, c'est `/planning` qu'il faut — pas ceci.
`planning-all` existe pour le cas où **l'ordre compte**.

## Ce qui le distingue de `/planning`

Trois différences, et elles justifient une commande à part plutôt qu'un
troisième déclencheur :

1. **Le périmètre d'écriture.** `/planning` porte une garde textuelle — « les
   seules écritures autorisées sont le fichier de plan, son annexe, au `NO_GO`
   le verdict intégral `critic-<n>.md` et `specs.py add` », plus
   `python .agents/bin/tasks.py chrono T-NNNNNNNN begin` au tour de planification
   (journal local du chrono, ni board ni code). `planning-all` écrit **aussi sur le board** (`tasks.py depends`,
   `tasks.py writeset`). L'ajouter sous le même nom effacerait cette garde pour
   tout le monde, y compris pour l'usage à 5 tâches.
2. **Le point d'arrêt.** `/planning` s'arrête UNE fois (la liste).
   `planning-all` s'arrête **DEUX** fois : sur le GRAPHE, puis sur la LIGNE.
3. **Le vocabulaire.** `/planning all` (alias `/planning tout`) veut dire « pas de plafond ».
   `/planning-all`, un seul mot à trait d'union, veut dire « le graphe, l'ordre, et la ligne ».
   Depuis S-01M5S9NJN15 le mot `all` porte les deux : seul le trait d'union les sépare,
   et la phrase « plan all » n'arme que le mode de `/planning` déjà invoqué, jamais `planning-all`.

## LE CONTRAT DE TRAÇAGE N'EST PAS RECOPIÉ ICI

L'étape de planification par tâche est celle de `/planning` —
`.agents/skills/planning/SKILL.md` § Étape 2 — **sans une virgule de
différence** : `planner` → préflight (`plan_preflight.py`) → `plan-critic`, 8 itérations au total, écriture du
plan enrôlant, sha256, puis les deux checkpoints dans l'ordre **plan D'ABORD,
verdict ENSUITE**, avec EXACTEMENT UN `sha256=` dans le texte du verdict.
Tout verdict `plan-critic …` de la boucle, NO_GO compris, porte le chrono du tour
(`CHRONO_REQUIRED`) : `--chrono-aid` sur Claude Code (un rôle routé ailleurs : `ROLE=<durée>/<jetons>`
mesurés, jamais 0), champ `chrono: planner=…` ailleurs,
sortie `--sans-chrono "<pourquoi>"` sur TOUT hôte, relu par `specs.py chrono` — la règle
entière, causes d'un aid non résolu comprises, est celle de `.agents/skills/planning/SKILL.md`
§ Contrat de traçage, jamais recopiée ici.
Exception R3 (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH, S-01M51M3X9SFEZECT1QJ0XJ8GD6) :
dans le kit, `--voie-courte` à `oui` remplace la 4e itération complète par un
passage court de plan-critic, joué sous $kickoff — une clause du plafond
ci-dessous, pas une seconde exception. Sous deux comptes, la session de planification
ajoute `--fait-log <dossier d'échange>/FAIT.log` à cette lecture (planning SKILL § Sous
deux comptes).

Une seule exception, recopiée parce qu'elle s'épingle mot pour mot sur chaque
surface d'exécution : le **plafond du critique de plan** (décision pilote
S-01M4V7RGDPP6ZK64NQ0RMN7BEN, planning SKILL § Étape 2). Les 8 itérations valent
DANS LE KIT ; avant chaque `plan-critic` et après chaque verdict journalisé de
la boucle, `bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNNNNNNN`
imprime `PLAFOND=<N> SOURCE=<kit|adoptant|adoptant-illisible>` (ou `decoupe` : tâche découpée du kit, plafond 2 par plan, escalade comme chez l'adoptant — kickoff SKILL § 8c) puis
`ITERATION=<n> ALLOCATION=<a> ESCALADE=<oui|non>` (chez l'adoptant, 2 par
défaut, relevé seulement sur demande explicite de son pilote, qui édite N À LA
MAIN dans `.agents/state/gates/PLAN_CHAIN_REQUIRED` ; aucune ligne `PLAFOND=`
lisible : plafond 2, jamais « kit » ; ligne 2 absente ou illisible :
`ESCALADE=oui`).
Hors du kit (`SOURCE=adoptant` ou `adoptant-illisible`), CHAQUE verdict
plan-critic de la boucle, NO_GO compris, est journalisé UNE fois AVANT le
compte. Cette entrée EST celle que la surface écrit déjà pour ce verdict —
« Record the critic's verdict » (kickoff SKILL étape 6), ou le checkpoint
NO_GO de /planning avec son `--text` plan=/revision=/status=/sha256= — sous le
titre `plan-critic <VERDICT> (iteration <n>/<N>)`. Jamais une seconde entrée :
le « Record the FINAL verdict » de fin de boucle (kickoff.md:179) n'en rajoute
pas. La permission du titre suffixé ne vaut plus pour un verdict de boucle.
Invoquer plan-critic avec `itération <ITERATION+1>/<PLAFOND>`.
`SOURCE=kit` : les 8 itérations ne changent pas.
Exception R3 (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH, S-01M51M3X9SFEZECT1QJ0XJ8GD6) :
dans le kit, `--voie-courte` à `oui` remplace la 4e itération complète par un
passage court de plan-critic, joué sous $kickoff ; sous deux comptes, la session de
planification ajoute `--fait-log <dossier d'échange>/FAIT.log` à cette lecture (planning
SKILL § Sous deux comptes). Hors du kit, à `ESCALADE=oui`,
le pilote tranche, mais `planning-all` ne bloque ni ne débloque JAMAIS : la
tâche sort du pool, et le relevé DIT l'escalade, avec l'option « continuer une
itération de plus » ; l'entrée `--kind decision` de la prolongation
(`"prolongation plafond critique : itération <n+1>"`) reste admise, comme
`"plafond critique : nouveau cycle"` avant le premier plan-critic d'une tâche
déjà jugée qu'on replanifie.

Ce fichier ne décrit **que ce qui l'entoure**. Un contrat recopié dérive, et
c'est l'adoptant qui hérite du désaccord.

## Les cinq phases

### Phase 0 — relevé, lecture seule

```bash
python .agents/bin/tasks.py list --state pending --json
python core-scripts/plan_pool.py status --json
python .agents/bin/ledger.py list | tail -30
git rev-parse --short HEAD      # LE sha de tamponnage, UN SEUL pour tout le run
git status --porcelain          # obligatoire — voir ci-dessous
```

`git status` n'est pas décoratif. Tout le résiduel de `plan_pool` tient au fait
que `git diff <sha>..HEAD` compare des **COMMITS** : une modification NON
COMMITÉE d'un fichier du write-set n'y est pas vue, donc le relevé
**SOUS-détecte** la péremption et peut rendre `READY` sur un arbre déjà
divergent. Un arbre sale se DIT au rapport, il ne se découvre pas à la nuit.

### Phase 1 — le graphe PROPOSÉ, puis ARRÊT DUR

Le graphe de specs donne les **candidats**, jamais les arêtes :

```bash
python .agents/bin/specs_graph.py generate --stdout   # ou lire l'artefact publié
```

**Une arête de `SPECS_GRAPH.json` est une CITATION CROISÉE, pas une
dépendance** — `specs_graph.py` le dit lui-même : « a journal or ledger text
that names another task id links the two nodes ». Elle n'est pas orientée
causalement. Et ce dépôt a déjà payé le piège : `LOT-3-plan.md` cite
`T-00000209` **pour dire qu'il ne le traite PAS**, `LOT-1-plan.md` cite
`T-00000203` comme « non touché ». **Une citation peut signifier l'inverse
d'une dépendance.**

Le graphe sert donc à réduire le problème — de toutes les paires possibles à
quelques dizaines à examiner. Trancher exige de **lire le texte citant**.

Restitue **un tableau**, une ligne par paire :

| paire | sens proposé | citation qui le justifie | verdict |
|---|---|---|---|
| T-00000503 / T-00000501 | 503 dépend de 501 | `T-00000503-plan.md:105` « collision réelle : séquentiel » | `DÉPEND` |
| T-00000501 / T-00000502 | — | `LOT-3-plan.md:62` « non touché » | `NON` |
| T-00000501 / T-00000494 | ? | citation sans direction lisible | `AMBIGU` |

**Un `AMBIGU` n'est JAMAIS écrit.** Une arête manquante est invisible et sans
coût d'ordre ; une arête fausse réordonne **silencieusement** toutes les nuits
suivantes, et l'erreur ne se voit qu'au matin.

Puis annonce la **FERMETURE** : combien de tâches demandées, combien tirées,
combien planifiables DANS CETTE PASSE — prévision : celles dont aucun amont,
inscrit ou proposé, n'est ouvert ; `deps-ready` tranche en phase 3 —, et **pour
chaque tâche tirée, QUI l'a tirée**. Une fermeture qui triple le lot est une
information que le pilote doit avoir **avant** de dire go.

**Le cadrage, avant la phase 2** (`planning/SKILL.md` § Le cadrage ; décisions pilote
S-01M5AN9N5Q4NNR5RDVQQ5QRFTV et S-01M5APXEG72MTVFYGRT82C75QE, porte unique). Chaque tâche de la
fermeture est cadrée UNE fois, avant son PREMIER `planner`, en lecture seule — ni sur une reprise, une
révision ou un enfant d'une découpe (arbitrage S-01M5BFKA2D : sa `--part` a été mesurée au cadrage du
parent), chaque chemin entre guillemets doubles :

```bash
bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task T-NNNNNNNN --file "<chemin>" … [--part "<NOM>=<chemin>,<chemin>" …]
```

Les blocs `CADRAGE` viennent EN TÊTE de la restitution de cet arrêt, tels quels ; rc 2 : la tâche
n'est pas cadrée, sa sortie est recopiée. Une tâche `découper` sort du lot : `planning-all` ne crée
pas ses enfants, il relaie le verdict vers `$kickoff`, qui les crée et les lance. La restitution
expose deux coûts : les enfants d'une découpe s'ordonnent par FUSION sous une porte unique, sans
arête `depends_on` entre eux ; chaque arête `DÉPEND` du tableau coûte une porte — l'amont doit être
`done` avant le `start` de l'aval —, et leur nombre est dit avec la fermeture.

**ARRÊT. Aucune arête n'est écrite avant le « go ».** Restitution par
`communicator`.

### Phase 2 — écrire les liens, puis RELIRE

```bash
python .agents/bin/tasks.py depends T-NNNNNNNN T-MMMMMMMM … --add --motif "<pourquoi aval attend amont>"
python core-scripts/plan_waves.py waves --task T-NNNNNNNN …
```

`--add` (T-00000765) : les arêtes déjà inscrites restent — une réécriture totale
effacerait celles qu'un autre plan a posées, et elle est refusée si elle perd un
`ORDRE PILOTE`. Les vagues se relisent **depuis l'outil**, jamais depuis le souvenir de la
phase 1. `plan_waves` sort en **3** sur un cycle : la phase s'arrête et le cycle
est restitué avec son chemin et son remède — `depends <aval> --retirer <amont>` sur
UNE arête technique, ou la route SUGGESTION si le cycle ne tient qu'à des
`ORDRE PILOTE` ; jamais `--clear`.

### Phase 3 — planifier, vague par vague

**L'amont d'abord** (décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T). Les arêtes de
la phase 2 sont maintenant au board : avant chaque `planner`, lire
`python .agents/bin/tasks.py deps-ready T-NNNNNNNN` — une LECTURE, hors des
écritures autorisées. Première ligne `deps-ready: <jeton>` ; rc 0 pour
`AMONT_CLOS` et `REPRISE_DITE`, rc 1 pour les quatre autres, rc 2 pour un usage
refusé ; un seul jeton, par précédence `CYCLE` > `AMONT_OUVERT` > `INEXPLOITABLE` >
`PLAN_A_REPLANIFIER` | `REPRISE_DITE` > `AMONT_CLOS`.
**`planning-all` ne planifie QUE la vague dont l'amont est clos** :
`AMONT_CLOS`, ou `PLAN_A_REPLANIFIER` replanifiée en entier sur le code réel.
Une vague suivante a, par construction, un amont ouvert dans le lot : elle rend
`AMONT_OUVERT`, sort du pool de CETTE passe, est DITE au rapport l'amont d'abord,
et se replanifie sur le code réel une fois son amont clos — une vague par passe.
`REPRISE_DITE` est une reprise (lancée sous ce plan, chaque amont en cause clos au plus tard à ce lancement ; un amont clos APRÈS rend `PLAN_A_REPLANIFIER`) que `/kickoff` consomme, jamais replanifiée ici ;
`CYCLE` se restitue comme en phase 2 ; `INEXPLOITABLE` (`plan_cible` absent ou qui ne se charge pas,
journal SPECS illisible ou trace sans date lisible, fail-closed) sort du pool, sa sortie recopiée ; rc 2 ou une
première ligne hors de ces six jetons → STOP. Jamais de `block` ni d'`unblock`.

Pour chaque tâche de cette vague : l'étape 2 de `/planning`
**verbatim**, chrono compris : une fois `deps-ready` admis, avant le premier
`planner` du tour, `python .agents/bin/tasks.py chrono T-NNNNNNNN begin` ouvre le
cycle au journal local du chrono sous la racine commune, ni board ni code.
`begin` est idempotent : une révision, une reprise ou une passe suivante de la
même tâche ne rouvre jamais un second cycle, il reprend le cycle ouvert. Un rc non
nul de `chrono` ne bloque jamais le tour : le plan continue et le rapport dit le
rc. Un historique venu d'un autre poste n'est pas au journal local : ses étapes
restent inconnues, `chrono show` signale le cycle incomplet et ne donne aucun
écart total. Les tâches d'une **même vague** se planifient en parallèle, sous
le verdict du poste : `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>`
avant CHAQUE lancement (`<n>` = agents en vol), un message par lancement d'au
plus son `PEUT_AJOUTER` — une vague de `plan_waves` plus large que lui part en
plusieurs lancements ; à `PEUT_AJOUTER=0` avec des plans restants, attendre
DANS LE TOUR par `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n> --attendre 540`,
lancée sous le `timeout: 600000` de Bash, puis appliquer le verdict qu'elle
rend ; sortie sans ligne `PLAFOND=` lisible, ou commande tuée : cinq moins les
agents actifs, jamais sous zéro (`max(0, 5 − ACTIFS)`) ; au plus TROIS attentes
de suite rendues à 0, puis départ EN SÉRIE — un agent à la fois — et
`COVERAGE DEGRADED — poste surchargé après trois attentes : plans un à un` dit
au rapport — la planification est en lecture seule, aucun conflit possible ; la
preuve de write-set ne concerne que l'EXÉCUTION.

Puis, pour chaque plan `GO` / `GO_AVEC_RESERVES` :

```bash
python .agents/bin/tasks.py writeset T-NNNNNNNN <chemins de la section WRITE-SET: du plan>
```

Ça convertit une extraction en prose — ce que `night.md` demande sinon à la nuit
de faire à 1 h du matin — en un champ déclaré, et c'est ce qui rend les bottes
de `plan_waves` réellement déclarables.

**`tasks.py parallel` n'est JAMAIS appelé ici.** Écrire un write-set **RÉTRACTE**
le `parallel_group` de la tâche : déclarer le groupe maintenant poserait une
preuve qu'une correction de write-set dissoudrait en silence. Le groupe est une
déclaration d'EXÉCUTION, allouée quand la nuit démarre ses membres.

### Phase 4 — `--check`, puis la ligne, puis ARRÊT

```bash
python .agents/bin/night_approve.py --check --lot docs/tasks/T-…-plan.md T-… [--lot …]
```

`--check` est le défaut et **n'écrit rien**. Recopie sa liste de `SAUTÉE` au
rapport : le pilote n'approuve plus à l'aveugle pour découvrir six SKIP.

**Un plan non commité sort SAUTÉ par la condition 8** (absent de HEAD, ou modifié depuis HEAD), la DERNIÈRE évaluée : sauté pour ce seul motif, il est approuvable une fois commité. La ligne rendue s'ouvre donc par `git add -- <plans>` puis `git commit -m "docs(tasks): plans T-… T-…" -- <plans>`, gestes du pilote — `/planning-all` ne commite rien.

Puis rends la ligne, et **arrête-toi**.

## La ligne rendue

Un plan enrôle une tâche, donc **un `--lot` par tâche** (`--lot` est
`append`/`nargs="+"` : une seule ligne portant N groupes est la forme native de
l'outil). Seules les tâches planifiées dans cette passe y figurent : une tâche
sortie du pool par `deps-ready` n'a pas de plan, donc pas de `--lot`.

```bash
git add -- docs/tasks/T-00000501-plan.md docs/tasks/T-00000504-plan.md && \
  git commit -m "docs(tasks): plans T-00000501 T-00000504" -- docs/tasks/T-00000501-plan.md docs/tasks/T-00000504-plan.md ; \
python .agents/bin/night_approve.py --apply \
  --lot docs/tasks/T-00000501-plan.md T-00000501 \
  --lot docs/tasks/T-00000504-plan.md T-00000504
```

**L'ordre des `--lot` n'ordonne PAS la nuit.** `night_approve` écrit N contrats
indépendants ; la nuit reconstruit son ordre en phase 3 à partir de
`depends_on` et des write-sets. L'ordre ci-dessus est là pour se relire, pas
pour commander — le dire évite le malentendu le plus coûteux de ce mécanisme.

Au-delà de **2 000 caractères**, la ligne passe en continuations `\` et le
nombre de caractères est annoncé. **Jamais coupée en deux gestes** : le commit et `--apply` tiennent dans le même bloc ; `;` avant `--apply`, car un plan déjà commité fait rendre 1 à `git commit`, et la condition 8 rejoue le commit.

## Ce qui accompagne la ligne

1. **Le sha de tamponnage** (un seul pour tout le run) et la propreté de l'arbre.
2. **Un débit réaliste qui dit QUI SAIT QUOI** : « N tâches approuvables en V
   vagues ; la fenêtre est calculée par `/night` en phase 0, ce relevé ne la
   connaît pas et ne prétend pas la connaître. »
   Un plan SAUTÉ par la condition 8 SEULE compte parmi les approuvables une fois commité : `/planning-all` ne commite jamais, tout plan frais en sort sauté.
3. **Les tâches qui resteront bloquées**, depuis les seaux `MURS` et
   `HORS VAGUES` de `plan_waves` — nommées avec ce qui les retient.
4. **Les tâches écartées**, dans un vocabulaire **déjà fermé**, jamais de la
   prose neuve : codes `plan_pool` (`NO_PLAN` 10 · `PLAN_SANS_VERDICT` 11 ·
   `SHA_ABSENT` 12 · `WRITE_SET_ABSENT` 13 · `STALE` 14 · `VERDICT_FAIL` 15),
   l'escalade à 8 itérations, les raisons de SKIP recopiées **mot pour mot** de
   `night_approve --check`, et les jetons `deps-ready` (`AMONT_OUVERT`, `CYCLE`,
   `INEXPLOITABLE`, `REPRISE_DITE`) avec leur première ligne recopiée, l'amont
   d'abord.
   Hors du kit, l'escalade est celle du plafond (`ESCALADE=oui` de
   `bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNNNNNNN`), dite avec
   n/N et l'option « continuer une itération de plus ».
   Un saut par la condition 8 SEULE n'est jamais listé parmi les tâches écartées : il compte au point 2, approuvable une fois commité.
5. **Le rappel de péremption** : `plan_pool.py check T-NNNNNNNN` à la
   consommation, tout code non nul → replanifier. Et que **`/night` ne l'appelle
   jamais**.
6. Un balayage `tasks.py list` **relu, jamais remémoré**, et un bloc
   **`CE QUI BLOQUE`** — vide est une réponse valide qu'il faut quand même
   écrire.

## Ce qu'il n'écrit JAMAIS

`night-eligible: approved` · `tasks.py start` / `block` / `unblock` / `done` / `retitle` ·
`tasks.py parallel` · `tasks.py fournee` (elle LANCE la fournée, geste de `/kickoff`
après la porte humaine — S-01M4V1K1DG9WY2WKWKWN7ZGFC7) · du code · une migration ·
un test · un commit · un push.

**`planning-all` ne lance jamais `--apply`, même si le pilote le demande dans le
même message.** La porte est un geste, et un geste demandé n'est pas un geste
donné. L'invariant T-00000233 — pas de mode « tout approuver », pas de
découverte des lots en balayant le board — reste intact : les lots sont NOMMÉS,
et c'est le pilote qui tape la ligne.

## Bornes déclarées

- **La fermeture peut faire exploser le lot.** 3 tâches sur un graphe dense
  peuvent en tirer 30, chacune coûtant un cycle `planner` → `plan-critic`.
  L'expansion est chiffrée et annoncée au premier arrêt ; rien ne la **borne**
  mécaniquement, parce qu'une borne arbitraire produirait un périmètre
  incomplet — le défaut même que la fermeture corrige.
- **La fermeture s'arrête à `blocked`**, et c'est un mur, pas un contournement.
  Le lot livré est alors plus petit que demandé, et il le dit.
- **La profondeur de vague ne se planifie plus d'avance.** Seule la vague dont
  l'amont est clos est planifiée (phase 3) : un plan de vague 3 aurait décrit un
  arbre que les vagues 1 et 2 auront changé. Le prix : une passe par vague, et
  un lot livré plus petit que la fermeture, DIT. Reste, au MÊME sha de
  tamponnage, deux tâches d'une même vague qui partagent un fichier sans arête :
  la seconde décrit un arbre que la première aura changé, et `/night` n'appelle
  jamais `plan_pool.py`. C'est la borne la plus lourde du mécanisme.
- **`/planning` (le mode simple) NE ferme PAS son périmètre** — contrat
  inchangé. Une tâche planifiée seule alors qu'elle dépend d'une autre garde le
  défaut qu'elle avait.
- **Le parallélisme proposé par `plan_waves` n'est pas prouvé**, et la preuve de
  `tasks.py parallel` est elle-même TEXTUELLE : liens symboliques, jonctions
  Windows, alias 8.3 et liens durs sont hors de sa portée.
