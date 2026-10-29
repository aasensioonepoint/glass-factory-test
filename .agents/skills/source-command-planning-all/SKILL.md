---
name: "source-command-planning-all"
description: "Plan an ORDERED BATCH — closes the scope over depends_on, plans wave by wave, and returns ONE night_approve line to type. Preparation only. Usage — /planning-all [T-NNN …|--workstream X] (the former `--chantier X` still accepted)"
---

# source-command-planning-all

Use this skill when the user asks to run the migrated source command `planning-all`.

## Command Template

Exécute le workflow **planning-all** dont le corps canonique est
`.agents/skills/planning-all/SKILL.md` — **lis-le d'abord**. Rappel des points
qui ne se négocient pas :

1. **Le contrat de traçage est celui de `$planning`**, sans une virgule de
   différence : `.agents/skills/planning/SKILL.md` § Étape 2. Ne le recopie pas
   ici — un contrat dupliqué dérive, et c'est l'adoptant qui hérite du
   désaccord.
2. **Le périmètre est FERMÉ sur `depends_on`.** Tu demandes T-A, T-A dépend de
   T-B : T-B entre, et récursivement. Une dépendance `done` ne tire rien
   (satisfaite). Une dépendance `blocked` **arrête la branche et la NOMME** — on
   ne fabrique pas un plan pour une tâche qui attend une décision humaine.
   **L'amont d'abord** (décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T, détail :
   planning-all SKILL § Phase 3) : les arêtes écrites, lis
   `python .agents/bin/tasks.py deps-ready T-NNNNNNNN` avant chaque `planner` —
   une LECTURE, dont le jeton de 1re ligne est le premier qui s'applique dans l'ordre `CYCLE` > `AMONT_OUVERT` > `INEXPLOITABLE` > `PLAN_A_REPLANIFIER` | `REPRISE_DITE` > `AMONT_CLOS`. Tu ne planifies QUE la vague dont l'amont est clos
   (`AMONT_CLOS`, ou `PLAN_A_REPLANIFIER` replanifiée en entier sur le code
   réel). T-A rend `AMONT_OUVERT` tant que T-B n'est pas clos : T-A sort du pool
   de cette passe, DITE au rapport l'amont d'abord, et se replanifie sur le code
   réel une fois T-B clos. `REPRISE_DITE` est une reprise (lancée sous ce plan, chaque amont en cause clos au plus tard à ce lancement ; un amont clos APRÈS rend `PLAN_A_REPLANIFIER`), jamais replanifiée
   ici ; `CYCLE` se restitue avec son chemin et son remède ; `INEXPLOITABLE`
   (`plan_cible` absent ou qui ne se charge pas, journal SPECS illisible ou trace sans date lisible, fail-closed) sort du pool, sa
   sortie recopiée ; rc 2 ou une première ligne hors de ces six jetons → STOP.
   Jamais de `block` ni d'`unblock`.
3. **DEUX arrêts durs, pas un.** Le premier sur le GRAPHE proposé — avec, pour
   chaque arête, la **preuve** qui la justifie, et l'expansion de la fermeture
   **chiffrée**, chaque tâche tirée nommant qui l'a tirée. Le second sur la
   LIGNE rendue.
   **Le cadrage, avant la phase 2** (décisions pilote S-01M5AN9N5Q4NNR5RDVQQ5QRFTV
   et S-01M5APXEG72MTVFYGRT82C75QE, détail : `.agents/skills/planning/SKILL.md`
   § Le cadrage et planning-all SKILL § Phase 1) : chaque tâche de la fermeture
   est cadrée UNE fois, avant son PREMIER `planner` — ni sur une reprise, une révision ou un enfant d'une découpe (arbitrage S-01M5BFKA2D) —, en lecture seule, chaque chemin entre guillemets doubles, par `bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task T-NNNNNNNN --file "<chemin>" … [--part "<NOM>=<chemin>,<chemin>" …]` ;
   les blocs `CADRAGE <T>` … `FIN CADRAGE` viennent EN TÊTE de la restitution du
   premier arrêt, relayés mot pour mot par `communicator` ; rc 2 : la tâche n'est
   pas cadrée, sa sortie est recopiée. Une tâche `Verdict : découper` sort du lot
   et va à `$kickoff`, qui crée et lance ses enfants — `$planning-all` n'écrit
   pas le board pour elle. La restitution dit le coût sous porte unique : les
   enfants d'une découpe s'ordonnent par FUSION, sans arête `depends_on` entre
   eux ; chaque arête `DÉPEND` coûte une porte (l'amont `done` avant le `start`
   de l'aval), et leur nombre est dit avec la fermeture.
4. **Le graphe de specs donne des CANDIDATS, jamais des arêtes.** Une arête de
   `SPECS_GRAPH.json` est une CITATION CROISÉE : `LOT-3-plan.md` cite
   `T-00000209` **pour dire qu'il ne le traite pas**. Un verdict `AMBIGU` n'est
   **jamais** écrit — une arête manquante est invisible, une arête fausse
   réordonne silencieusement toutes les nuits suivantes.
5. **Écritures autorisées** : le fichier de plan et son annexe, au `NO_GO` le
   verdict intégral `docs/tasks/T-NNNNNNNN-critic-<n>.md`, `specs.py add` (`plan`,
   `verdict` ; hors du kit, les décisions « prolongation plafond critique » et
   « plafond critique : nouveau cycle » ; TOUT verdict `plan-critic` de boucle porte le chrono
   du tour, `CHRONO_REQUIRED` : Claude Code
   `--chrono-aid planner=<agentId> --chrono-aid plan-critic=<agentId>`, sans champ écrit à la main (un rôle
   routé ailleurs : `ROLE=<durée>/<jetons>` mesurés, jamais 0) ; ailleurs
   `chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>` à la main ; `--sans-chrono "<pourquoi>"`
   sur tout hôte, relu par `specs.py chrono`), `tasks.py depends … --add` (T-00000765 : jamais une réécriture
   totale, qui effacerait les arêtes d'un autre plan), `tasks.py writeset`,
   `python .agents/bin/tasks.py chrono T-NNNNNNNN begin` au tour de planification
   de chaque tâche (journal local du chrono sous la racine commune, ni board ni
   code ; idempotent, un rc non nul ne bloque jamais le tour — planning-all SKILL
   § Phase 3). **Rien d'autre.**
   Jamais `tasks.py parallel` — écrire un write-set RÉTRACTE le groupe, donc le
   déclarer maintenant poserait une preuve qu'une correction dissoudrait en
   silence. Jamais `tasks.py fournee` non plus : elle LANCE la fournée, et c'est
   le geste de `$kickoff` après la porte humaine (S-01M4V1K1DG9WY2WKWKWN7ZGFC7).
6. **Tu n'écris JAMAIS `night-eligible: approved`, et tu ne lances jamais
   `--apply`** — même si le pilote le demande dans le même message. Tu rends la
   ligne ; c'est lui qui la tape. La porte est un geste, et un geste demandé
   n'est pas un geste donné (invariant T-00000233). Tu joues en revanche
   `night_approve.py --check` avec EXACTEMENT la ligne que tu t'apprêtes à
   rendre, et tu recopies ses `SAUTÉE` au rapport : `--check` est le défaut et
   **n'écrit rien**, donc le pilote n'approuve plus à l'aveugle pour découvrir
   six SKIP.
   **Un plan non commité sort SAUTÉ par la condition 8** (absent de HEAD, ou modifié depuis HEAD), la DERNIÈRE évaluée : sauté pour ce seul motif, il est approuvable une fois commité. La ligne rendue s'ouvre donc par `git add -- <plans>` puis `git commit -m "docs(tasks): plans T-… T-…" -- <plans>`, gestes du pilote — `$planning-all` ne commite rien.
   `--check` se joue sur la SEULE commande `night_approve.py` du bloc (ses `--lot`), jamais sur ses commandes git.
7. **L'ordre des `--lot` n'ordonne pas la nuit** — dis-le sous la ligne.
   `night_approve` écrit N contrats indépendants ; `/night` reconstruit son
   ordre en phase 3 à partir de `depends_on` et des write-sets.

Restitution par `communicator`, et le rapport finit toujours par un bloc
**`CE QUI BLOQUE`** — vide est une réponse valide qu'il faut quand même écrire.

Shared process reference: `.agents/skills/planning-all/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
