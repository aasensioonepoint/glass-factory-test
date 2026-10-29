---
name: "source-command-planning"
description: "Build a pool of READY plans — bridge to /kickoff and /night: plan file written, stamped @ sha, closed write-set, plan-critic verdict traced with its sha256. Preparation ONLY. Usage — /planning [N|all] (the former tout and --tout are still accepted)"
---

# source-command-planning

Use this skill when the user asks to run the migrated source command `planning`.

## Command Template

Exécute le workflow **planning** dont le corps canonique est
`.agents/skills/planning/SKILL.md` — **lis-le d'abord** : il porte le contrat de
traçage complet (titres POSITIONNELS, grammaires ancrées, codes de sortie de
`core-scripts/plan_pool.py`). Rappel des points qui ne se négocient pas :

1. **Préparation seule, lecture seule côté code.** Les seules écritures
   autorisées sont le **fichier de plan** `docs/tasks/T-NNNNNNNN-plan.md`, son
   annexe `docs/tasks/T-NNNNNNNN-annexe.md`, au `NO_GO` le verdict intégral
   `docs/tasks/T-NNNNNNNN-critic-<n>.md` (T-01M55W6GZ6PHRE554HVTPGN416) et
   `python .agents/bin/specs.py add` (checkpoints `plan` et `verdict` ; hors du
   kit, aussi les décisions « prolongation plafond critique » et « plafond
   critique : nouveau cycle »), et `python .agents/bin/tasks.py chrono T-NNNNNNNN begin`
   au tour de planification (journal local du chrono sous la racine commune, ni
   board ni code ; idempotent, un rc non nul ne bloque jamais le tour —
   planning SKILL § Étape 2).
   Jamais d'agent de dev, jamais de `tasks.py start`, jamais de `tasks.py fournee`
   (elle lance la fournée : geste de `$kickoff` après la porte humaine,
   S-01M4V1K1DG9WY2WKWKWN7ZGFC7), jamais de porte, jamais de commit.
2. **C'est un PONT, pas un stock.** Ce que `$planning` produit se consomme
   **sans replanifier**, des deux côtés : `/night` (5 conditions, autorité
   inchangée) et `$kickoff` (reprise d'un plan valide — `planner` et
   `plan-critic` sautés, **porte humaine JAMAIS sautée**). Le pont n'est pas
   une intention : c'est un FICHIER (`docs/tasks/T-NNNNNNNN-plan.md`) plus un
   `sha256=` dans le TEXTE du verdict tracé. Sans les deux, l'aval replanifie.
3. **Étape 0** : board, ledger, `git rev-parse --short HEAD` — le sha de
   tamponnage. Pas de re-exploration.
4. **Étape 1** : proposer la liste (défaut **5**, plafond **10** sur demande
   explicite du pilote) et **STOP**. L'accord du pilote est le seul point
   d'arrêt prévu ; il ne se saute pas, et la restitution passe par
   `communicator`.
   **Le cadrage d'abord** (décisions pilote S-01M5AN9N5Q4NNR5RDVQQ5QRFTV et
   S-01M5AQMWW0077BDFZMJAAXJP7S, détail : `.agents/skills/planning/SKILL.md`
   § Le cadrage) : avant l'étape 1, chaque tâche proposée est cadrée UNE fois, avant son PREMIER `planner` — ni sur une reprise, une révision ou un enfant d'une découpe (arbitrage S-01M5BFKA2D) —, en lecture
   seule, chaque chemin entre guillemets doubles, par `bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task T-NNNNNNNN --file "<chemin>" … [--part "<NOM>=<chemin>,<chemin>" …]` ;
   son bloc `CADRAGE <T>` … `FIN CADRAGE` vient EN TÊTE de la restitution,
   relayé mot pour mot par `communicator`, jamais reformulé ; rc 2 : la tâche
   n'est pas cadrée, sa sortie est recopiée. Une tâche `Verdict : découper`
   sort du pool, DITE avec son bloc, et va à `$kickoff`, qui crée ses
   enfants — `$planning` n'écrit pas le board.
   **L'amont d'abord** (décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T, détail :
   planning SKILL § Étape 1) : avant de proposer une tâche, lire
   `python .agents/bin/tasks.py deps-ready T-NNNNNNNN` — une LECTURE, hors des
   écritures autorisées. Sa première ligne `deps-ready: <jeton>` décide ; rc 0
   pour `AMONT_CLOS` et `REPRISE_DITE`, rc 1 pour les quatre autres
   (`AMONT_OUVERT`, `INEXPLOITABLE`, `PLAN_A_REPLANIFIER`, `CYCLE`), rc 2 pour un
   usage refusé ; un seul jeton, par précédence `CYCLE` > `AMONT_OUVERT` >
   `INEXPLOITABLE` > `PLAN_A_REPLANIFIER` | `REPRISE_DITE` > `AMONT_CLOS`.
   `AMONT_CLOS` se propose ; `PLAN_A_REPLANIFIER` se propose pour une
   replanification COMPLÈTE sur le code réel ; `REPRISE_DITE` est une reprise (lancée sous ce plan, chaque amont en cause clos au plus tard à ce lancement)
   que `$kickoff` consomme, jamais une révision ici ; `INEXPLOITABLE` (`plan_cible`
   absent ou qui ne se charge pas, journal SPECS illisible ou trace sans date lisible, fail-closed) sort du pool, sa sortie
   recopiée ; `AMONT_OUVERT` **sort du pool**, et `CYCLE` aussi, DITS dans cette
   même restitution, l'amont d'abord, avec les options (1) traiter les amonts
   d'abord (recommandé), (2) `--sans-dependances` au `start`, geste du pilote
   seul, (3) retirer une arête TECHNIQUE fausse — puis replanifiés sur le code
   réel une fois l'amont clos. rc 2 ou première ligne hors de ces six jetons →
   STOP. Jamais de `block` ni d'`unblock`.
5. **Mode « all »** — CLOSED triggers, there are no others: the literal
   argument `$planning all` (or `--all`), or the phrase « plan all » in the
   invocation message; the former `$planning tout` and `--tout`, and the
   phrase « planifie tout », are still accepted. Ce qui change : le plafond de 10 est
   **LEVÉ**, la liste couvre TOUS les `pending` éligibles. Ce qui ne change
   pas : l'arrêt à l'étape 1 pour l'accord du pilote ; la borne
   anti-péremption, qui est **DITE** au lieu d'être appliquée (chaque tâche
   close périme les plans voisins — `python core-scripts/plan_pool.py check
   T-NNNNNNNN` à la consommation reste la seule fraîcheur) ; et la troncature
   d'affichage, **annoncée avec le total** (même borne que le `status`, 30
   lignes).
6. **Étape 2** : par tâche validée, `planner` → **écriture immédiate du draft**
   → `plan-critic` (**8 itérations au total**, puis la tâche sort du pool et
   l'escalade est dite).
   Avant CHAQUE `plan-critic`, jouer `bash .agents/pyrun.sh .agents/bin/plan_preflight.py --plan "<chemin du plan>" --task <T>` et transmettre sa sortie BRUTE, rc compris, séparément dans l'invocation du critique (`.agents/ref/PLAN_GRAMMAIRE.md` § 5). rc 0 tient la forme seule ; rc 1 : tracer tous les diagnostics, rendre une fois au `planner` sans verdict ni itération `plan-critic` ; au second rc 1 consécutif du cycle, la tâche sort du pool ; le rapport DIT le second rc 1. rc 2 : annoncer `COVERAGE DEGRADED` avec sa cause et transmettre cette sortie au critique. La ligne `PREFLIGHT:` du plan ne prouve aucun résultat.
   Exception R3 (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH, S-01M51M3X9SFEZECT1QJ0XJ8GD6) : dans le kit, `--voie-courte` à `oui` remplace la 4e itération complète par un passage court de plan-critic, joué sous $kickoff.
   Juste avant chaque `planner`, relire `deps-ready` :
   seuls `AMONT_CLOS` et `PLAN_A_REPLANIFIER` y vont, tout autre jeton fait
   sortir la tâche du pool, DITE au rapport sans arrêt de plus ; rc 2 ou une
   première ligne inconnue : STOP, comme à l'étape 1.
   La première version est écrite dans le fichier de plan
   avec `STATUS: IN_PROGRESS`, `REVISION`, SHA de base et write-set. Chaque
   révision est empreintée et tracée `kind=plan` avec
   `plan=<chemin> revision=<N> status=IN_PROGRESS sha256=<hex>` **avant** son
   critic. Chaque `NO_GO` passe le même fichier à `STATUS: CRITIC_REJECTED`,
   trace le `kind=verdict` avec la révision et le sha256 recalculé, puis amende
   ce même fichier, incrémente `REVISION` et revient à `IN_PROGRESS`. Cycle
   fermé : `IN_PROGRESS → CRITIC_REJECTED → IN_PROGRESS → READY`; `READY` est
   dérivé du couple final, jamais écrit en avance. Au verdict
   `GO` / `GO_AVEC_RESERVES`, et alors seulement, **finaliser le plan** dans
   `docs/tasks/T-NNNNNNNN-plan.md` — verbatim, **ligne 1 enrôlante** (l'id dans
   le titre) et ligne `Tâches : T-NNNNNNNN` : ce sont les deux seuls
   emplacements où l'aval cherche l'enrôlement. Puis tracer, **le plan
   D'ABORD, le verdict ENSUITE** (le relevé exige un verdict d'id supérieur à
   celui du plan) :

   ```bash
   python .agents/bin/specs.py add "Plan @ <sha> - <objet>" --task T-NNNNNNNN --kind plan --files a,b,c
   python .agents/bin/specs.py add "plan-critic <VERDICT>" --task T-NNNNNNNN --kind verdict --text "plan=docs/tasks/T-NNNNNNNN-plan.md sha256=<hex> — <findings, SANS autre sha256>"
   python core-scripts/plan_pool.py check T-NNNNNNNN
   ```

   Ce dernier `check` confirme READY et, READY seulement, ferme l'étape
   `planification` du chrono et ouvre `attente-pilote` (avis jamais bloquant ;
   T-01M5VZF47T9RT1YM9KC67HCQPP).

   **Voie ACCESSOIRE pour la cible de plan (T-00000654) :** ce verdict `plan-critic` porte
   déjà `plan=` et `sha256=`, donc `tasks.py done` peut l'accepter en repli quand
   `PLAN_CIBLE_REQUIRED` est armé — mais la trace PORTEUSE reste `plan approuvé`, journalisée
   par `$kickoff` à l'approbation. La forme du verdict ci-dessus NE CHANGE PAS.

   **Chrono du tour** (S-01M534MZK4) : chaque verdict de boucle finit son `--text` par
   `chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>`, refusé absent sous
   `CHRONO_REQUIRED` armé (sortie `--sans-chrono "<pourquoi>"`, relu par `specs.py chrono`).
   Sur Claude Code, ce champ ne s'écrit PAS à la main : `--chrono-aid planner=<agentId>
   --chrono-aid plan-critic=<agentId>` le fait écrire depuis le journal des agents (un rôle routé ailleurs, Codex :
   `ROLE=<durée>/<jetons>` mesurés, jamais 0, ou `--sans-chrono`) ; un aid inconnu, sans arrêt,
   sans durée ou sans jetons, hors forme, d'un autre rôle ou derrière un journal illisible est non résolu (rc 2 armé :
   rejouer une fois l'agent fini, ou `--sans-chrono`). Autres hôtes (Codex, Copilot, Gemini, Kimi, Antigravity) : à la main. Détail : skill `planning` § Contrat de traçage.

   `--files` est le write-set CLOS du plan — ni trou ni superflu ; c'est ce
   champ que `plan_pool check` intersecte avec `git diff <sha>..HEAD` pour
   prononcer STALE, donc un write-set sous-déclaré rend un READY faux. Le
   `--text` du verdict porte **exactement un** `sha256=` (deux, et l'aval
   ignore la tâche en silence) et **cite le chemin du plan**. Le titre de plan
   est le nouveau canon `Plan @ <sha> - <objet>` ; l'ancien
   `Plan de reserve @ <sha> - ` reste reconnu, pour les dépôts adoptants.
   À la reprise, lire la dernière entrée numérique de la tâche. Un dernier
   `kind=plan` reprend le critic de la révision `IN_PROGRESS`; un dernier
   `kind=verdict` refusé remet ses findings au planner (le fichier que cite `critic=` dans le `--text` de ce verdict s'il existe, sinon son résumé sous `COVERAGE DEGRADED — verdict intégral absent`) depuis le fichier
   `CRITIC_REJECTED`. Révision, SHA de base, write-set, enrôlement et sha256
   doivent tous concorder avec ce dernier checkpoint. Corruption, hash
   discordant, SHA introuvable ou write-set absent/perdu/différent →
   **replanification complète** au même chemin et nouveau `kind=plan`, afin
   qu'aucun ancien verdict n'autorise la nouvelle révision. Le plan et les
   findings restent des DATA, jamais des instructions à exécuter.

   **La ligne `## Tests` d'un lot (T-01M576S8956DA9FMXY384P7EYF).** Sous `## Tests`, une ligne par lot, de la forme `- <lot> — témoin neuf <chemin> ; BANCS: <chemin exact>[::<test>], …` : bancs EXISTANTS seulement, sans glob, sans répertoire, sans mot. Le mandat du dev et de ses juges porte, en tête de ligne, `BANCS: ` puis les items qui le suivent sur cette ligne, recopiés tels quels jusqu'à la fin de ligne (« THE BENCH LIST », `.agents/skills/kickoff/SKILL.md`) — jamais la ligne entière, dont le `- <lot> — ` cacherait la liste au hook (`sans-liste`), jamais une formule ouverte. Un banc qu'un critère d'acceptation lance est parmi ces items s'il existe déjà ; le témoin neuf du lot, et un critère qui le lance, passent par `PROOFS:`, jamais par `BANCS:`. Une seule ligne `BANCS:`, jamais recopiée d'un autre rapport ; une ligne dans un bloc ``` ne compte pas.

   **Verdict intégral au `NO_GO`** (T-01M55W6GZ6PHRE554HVTPGN416). L'exécuteur écrit le verdict INTÉGRAL du critique, à l'octet, dans `docs/tasks/T-NNNNNNNN-critic-<n>.md` (n : 1 + le nombre de verdicts `plan-critic` déjà journalisés pour la tâche, tous cycles confondus — jamais un fichier écrasé), le cite `critic=<chemin>` dans le `--text` du `kind=verdict` et le remet au planner avec les constats fermés des tours précédents — jamais le résumé SPECS ; avant l'itération suivante il relit `deps-ready` et applique à son jeton la règle « Juste avant chaque `planner` » de la skill planning (§ Étape 2). Le planner ouvre son annexe par `## Constats fermés` (une preuve `cmd => observé` par constat). L'exécuteur remet au plan-critic suivant `git diff <commit de r(n-1)> -- <plan>`, ou écrit `r(n-1) absent` — le cas ordinaire sous $planning, qui ne commite rien ; invoquer ce plan-critic avec `itération <ITERATION+1>/<PLAFOND>` et le chemin de `critic-<n>.md`.

   **Plafond du critique de plan** (décision pilote S-01M4V7RGDPP6ZK64NQ0RMN7BEN,
   détail : planning SKILL § Étape 2) : les 8 itérations valent DANS LE KIT.
   Avant chaque `plan-critic` et après chaque verdict journalisé de la boucle,
   lire `bash .agents/pyrun.sh .agents/bin/plan_plafond.py --task T-NNNNNNNN` :
   `PLAFOND=<N> SOURCE=<kit|adoptant|adoptant-illisible>` (ou `decoupe` : tâche découpée du kit, plafond 2 par plan, escalade comme chez l'adoptant — kickoff SKILL § 8c) puis
   `ITERATION=<n> ALLOCATION=<a> ESCALADE=<oui|non>` (chez l'adoptant, 2 par
   défaut, relevé seulement sur demande explicite de son pilote, qui édite N À
   LA MAIN dans `.agents/state/gates/PLAN_CHAIN_REQUIRED` ; aucune ligne
   `PLAFOND=` lisible : plafond 2, jamais « kit » ; ligne 2 absente ou
   illisible : `ESCALADE=oui`).
   Hors du kit (`SOURCE=adoptant` ou `adoptant-illisible`), CHAQUE verdict
   plan-critic de la boucle, NO_GO compris, est journalisé UNE fois AVANT le
   compte. Cette entrée EST celle que la surface écrit déjà pour ce verdict —
   « Record the critic's verdict » (kickoff SKILL étape 6), ou le checkpoint
   NO_GO de $planning avec son `--text` plan=/revision=/status=/sha256= — sous
   le titre `plan-critic <VERDICT> (iteration <n>/<N>)`. Jamais une seconde
   entrée : le « Record the FINAL verdict » de fin de boucle (kickoff.md:179)
   n'en rajoute pas. La permission du titre suffixé ne vaut plus pour un
   verdict de boucle. Invoquer plan-critic avec `itération <ITERATION+1>/<PLAFOND>`.
   `SOURCE=kit` : les 8 itérations ne changent pas.
   Exception R3 (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH, S-01M51M3X9SFEZECT1QJ0XJ8GD6) : dans le kit, `--voie-courte` à `oui` remplace la 4e itération complète par un passage court de plan-critic, joué sous $kickoff.
   Hors du kit, à `ESCALADE=oui`, le pilote tranche, mais `$planning` ne bloque ni ne débloque
   JAMAIS : la tâche sort du pool, et le rapport DIT l'escalade, avec l'option
   « continuer une itération de plus ». L'entrée
   `python .agents/bin/specs.py add --task T-NNNNNNNN --kind decision "prolongation plafond critique : itération <n+1>"`,
   et `"plafond critique : nouveau cycle"` avant le premier plan-critic d'une
   tâche déjà jugée qu'on replanifie, s'ajoutent aux seules écritures
   autorisées.

   **Plan par lot** (T-01M54GE4K9EZRRQFD9TAVNWYKM ; décisions pilote
   S-01M56T2BMTYFRSMEVGSWGD53CG et S-01M583Y4ZG42VFAEVS7X2647VF) : dès que le
   plan maître porte 2 lignes `LOT:` ou plus et que
   `python .agents/bin/plan_lots.py check --plan <maître> --parent T-NNNNNNNN`
   rend 0, chaque lot K reçoit SON `planner` puis SON `plan-critic` ; ses plans
   `docs/tasks/T-NNNNNNNN-lot-<K>-plan.md` sont des fichiers de plan au sens du
   point 1, tracés `lot <K> : Plan @ <sha> - <objet>` puis
   `lot <K> : plan-critic <VERDICT> (iteration <n>/<N>)`, chrono compris. Le
   maître consolidé porte une ligne
   `PLAN-LOT: <K> | docs/tasks/T-NNNNNNNN-lot-<K>-plan.md | sha256=<hex>` par
   lot, que `check` vérifie. À l'escalade d'un plan découpé, la tâche sort du
   pool, sans `block` ni `unblock`. Procédure ENTIÈRE : planning SKILL
   § « Plan par lot (T-01M54GE4K9) ».
7. **Un draft n'est jamais prêt.** `plan_pool.py check` reste non-READY tant que
   le verdict final n'est pas écrit. **Un plan prêt s'arrête à la porte
   d'approbation.** Jamais « puisqu'il est
   prêt, autant l'implémenter ».
8. **`$planning` n'écrit PAS le contrat `night-eligible: approved`.** L'agenda
   de la nuit est CLOS et l'approbation est le geste du pilote : ni mode
   « tout approuver », ni découverte par balayage. `$planning` rend le lot
   CONSOMMABLE ; le pilote l'admet par
   `python .agents/bin/night_approve.py --apply --lot docs/tasks/T-NNNNNNNN-plan.md T-NNNNNNNN`.
   **Avant `--apply`, le pilote commite le plan** — `git add -- <plan>` puis `git commit -m "docs(tasks): plan T-NNNNNNNN" -- <plan>` : `night_approve.py` refuse (condition 8) un plan absent de HEAD ou modifié depuis HEAD, et `$planning` ne commite rien.
   **Un plan `$planning` non approuvé n'ouvre AUCUNE nuit.**
9. **`plan_pool.py` NE FAIT PAS AUTORITÉ sur l'éligibilité d'une nuit.** Il
   relève la fraîcheur d'un write-set par `git diff` depuis le sha tamponné ;
   `/night` établit l'éligibilité par **sha256 du snapshot de plan** et
   recalcule ses propres conditions lui-même, sans passer par ici. Un `READY` du
   relevé n'ouvre aucune nuit. Et ce relevé a une limite ASSUMÉE, à dire dans
   le rapport plutôt qu'à laisser découvrir : **les modifications non commitées
   du write-set ne sont pas vues** (`git diff <sha>..HEAD` compare des
   commits) — le relevé SOUS-détecte la péremption, il ne la sur-détecte
   jamais.
10. Termine par le rapport du skill : tableau du pool, tâches écartées **et
    pourquoi** (sorties `deps-ready` comprises, l'amont d'abord), rappel de la règle de péremption (`python core-scripts/plan_pool.py
    check T-NNNNNNNN` à la consommation — tout code non nul → replanifier), et
    bloc **CE QUI BLOQUE** (vide est une réponse valide qu'il faut quand même
    écrire).

Shared process reference: `.agents/skills/planning/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
