# Journal des versions — Cadre

Chaque version liste ce qui change dans votre dépôt depuis la précédente : un titre, puis ce que ça change pour vous ; la première section, `0.1.0.dev14`, reprend tout ce que `0.1.0` apporte depuis son début. Les versions `0.1.0.devN` précèdent la version `0.1.0`.

## 0.1.0.dev14 — 2026-10-28

### Ce que fait le kit

**Un cadre de travail pour agents de code, posé dans votre dépôt.**
Ce que ça change pour vous : vos agents suivent une chaîne fixe — plan, critique du plan, accord du pilote, développement, revue, sécurité, porte de vérification — et un tableau des tâches garde la trace de chaque étape.

### Ajouté

**Claude Code lance le dev Codex par un lanceur vérifié, sans invite.**
Ce que ça change pour vous : seule `bash .agents/bin/codex-dev.sh …` depuis la racine est pré-approuvée ; bac `workspace-write` demandé, `-s`, `-c`, `--add-dir`, `..` des noms refusés. Rien de confiné : Codex lit tout le disque, écrit /tmp, ne commite pas ; `.claude/settings.json` existant : ajoutez la ligne à la main.

**Un agent de rétro-ingénierie qui pilote rea, et ne le refait jamais.**
Ce que ça change pour vous : `reverse-engineer` (35e agent) analyse un binaire, un paquet ou une application que vous NOMMEZ et déclarez autorisés, en pilotant la CLI externe rea épinglée par un runner déterministe : inspections statiques en liste fermée, jamais l'exécution de la cible, Evidence hors git.

**Une seule source pour les défs d'agents et les commandes.**
Ce que ça change pour vous : vous éditez `agents/<nom>.md` ou `commands/<nom>.md`, puis `render_hosts.py --ecrire` réécrit les défs des cinq hôtes, le roster, `.claude/commands/` et les miroirs `source-command-*` ; `--check` signale toute copie éditée à la main.

**Des règles et commandes Cursor, rendues mais pas mesurées.**
Ce que ça change pour vous : le même rendu écrit `.cursor/rules/*.mdc` et `.cursor/commands/*.md` ; Cursor n'est pas un hôte du kit, aucune garde ne l'atteint, et rien ne prouve encore qu'il lise ces fichiers. Vos défs et commandes posées à la main, sans témoin du kit du même nom, restent intactes.

**Un agent et une skill SEO.**
Ce que ça change pour vous : `seo-specialist` relit le SEO technique d'un site et `seo_mesure.py` mesure ce qu'il affirme.

**Des fiches de conventions pour sept langages de plus.**
Ce que ça change pour vous : un projet PHP, Ruby, Dart, Kotlin, Rust, Swift ou C++ reçoit sa fiche `.agents/ref/CONVENTIONS_<stack>.md`, choisie par le détecteur de langage ; les fiches Java et .NET sont enrichies.

**Les caractères Unicode invisibles sont refusés dans ce que lisent les agents.**
Ce que ça change pour vous : un caractère invisible ou bidirectionnel dans une déf, une skill ou une règle fait rougir un banc, et une skill tierce qui en porte est refusée par le repli GitHub de `/skills-sync` ; une exception passe par un registre que les agents ne peuvent pas écrire.

**Le poste décide combien d'agents partent.**
Ce que ça change pour vous : avant chaque vague, `charge_poste.py verdict` dit combien d'agents partent : un premier lot borné par le nombre de cœurs de votre machine, puis toute la place libre tant qu'elle n'est pas surchargée ; le plafond est partagé par les sessions du poste.

**Un tableau de bord lu depuis une base locale.**
Ce que ça change pour vous : les vues Gouvernance, Mémoire et Timeline lisent une base SQLite reconstruite depuis le journal des checkpoints et la mémoire, paginée et tenue hors du dépôt.

**Une commande de préparation du projet.**
Ce que ça change pour vous : `setup_projet.py` prépare le projet (identité, stores, index, specs) et dit étape par étape ce qui reste dégradé ; les prérequis du poste, dont Python 3.11 ou plus, s'installent avant par `core-scripts/setup.sh` ou `setup.ps1`.

**Un plafond du critique de plan que vous réglez.**
Ce que ça change pour vous : chez vous, le critique de plan s'arrête à 2 itérations avant de vous faire trancher ; relevez-le à la main par la ligne `plafond-critique=N` de `.agents/state/gates/PLAN_CHAIN_REQUIRED` — une copie de la branche template remet 2, un delta appliqué à trois voies garde votre valeur.

**Un contrôle de forme avant le critique de plan.**
Ce que ça change pour vous : avant chaque passage du critique, `plan_preflight.py` vérifie la forme du plan — lots, cibles, dépendances, chemins, bancs ; un plan mal formé revient au planificateur sans consommer d'itération ; au 2e refus de suite vous tranchez (/planning : il sort du pool). Le fond reste au critique.

**Un cadrage avant le premier plan.**
Ce que ça change pour vous : avant le premier planificateur d'une tâche, `cadrage_plan.py` (lecture seule) dit sa taille, ses surfaces, s'il faut la `découper`, l'ordre des enfants (chacun après la fusion de ceux qu'il recouvre) et une estimation ; câblé sur les cinq hôtes.

**Une section Équipe dans la page d'usage.**
Ce que ça change pour vous : `docs/usage.html` dit ce qui part sur git et ce qui reste local, et l'accueil d'un coéquipier qui clone un dépôt déjà équipé ; `.claude/.gitignore` ignore `.claude/worktrees/` et `.claude/scheduled_tasks.lock`.

**La frise des étapes de chaque tâche, sur l'Accueil et le Board.**
Ce que ça change pour vous : chaque tâche en cours montre ses 12 étapes, du cadrage au done — l'étape en cours pulse (fixe si animations réduites), une tâche bloquée est en pause —, temps réel, estimé, dépassement (journal local au poste) ; le Board (« En cours ») range les lots sous leur mère ; un clic ouvre la fiche.

**La durée de chaque lot, au Board et dans la fiche.**
Ce que ça change pour vous : sous une tâche découpée, chaque lot montre sa durée mesurée dans le chrono de sa mère, fusion comprise quand sa fin est écrite (sinon « incomplète ») ; un lot sans mesure bornée affiche « — non borné », jamais « 0 s » ; un lot clos ou une mère en pause ne tourne plus.

**Une configuration guidée de Jira et la commande `/jira`.**
Ce que ça change pour vous : la préparation du projet propose un board local ou Jira ; Jira se configure dans votre terminal, le jeton va au trousseau macOS sans passer en argument (ailleurs, la variable `JIRA_API_TOKEN`), et `/jira` vérifie la connexion et les droits en lecture seule.

**Une commande `/setup` prépare le projet depuis l'assistant.**
Ce que ça change pour vous : `/setup` (`$setup` ailleurs) lance la préparation du projet et relaie son bilan étape par étape, sans rien écraser ; l'assistant ne pose aucune question : board local ou Jira, hooks git et pilote de fusion se règlent dans votre terminal, par la commande que le bilan vous donne.

**Des conventions Java, Angular et React à jour.**
Ce que ça change pour vous : vos agents suivent Java 25 et Spring Boot 4 (`CONVENTIONS_java.md`, architecture hexagonale ou en couches au choix), Angular 20 à 22 (`CONVENTIONS_angular.md`, commandes lues dans votre `package.json`) et React 19 avec Next 15 ou 16 (build et lint selon votre version de Next).

### Changé

**La porte du kit joue pytest et les suites bash en même temps, dès 16 cœurs.**
Ce que ça change pour vous : `run-pytest-shards.sh` en `auto` monte à 12 jobs au lieu de 8 (9 sur 18 cœurs) ; sur la porte du kit seule, les suites bash tournent en même temps, à 4 jobs. Verdict et tampon inchangés ; `CADRE_GATE_JAMBES=serie` rend la série, `CADRE_GATE_JOBS=8` l'ancien comportement.

**Un gabarit `.env.EXAMPLE` s'édite quelle que soit sa casse ; un vrai `.env` reste refusé.**
Ce que ça change pour vous : sous Claude Code, `.env.Example`, `.ENV.SAMPLE` et les autres casses des gabarits `.env.example/.sample/.template/.dist` s'éditent comme leur forme minuscule, alors que `.env`, `.ENV` et `.env.LOCAL` restent refusés ; Codex et Gemini décidaient déjà ainsi.

**Sous Codex, un scan de secrets trop long refuse l'écriture.**
Ce que ça change pour vous : sous Codex (macOS, Linux), une écriture dont le scan gitleaks `--content` dure plus de 50 s est refusée au lieu de passer ; un secret trouvé ou un scanner planté la refusent aussi, raison générique « garde sortie en echec » ; ré-approuvez les hooks par `/hooks`.

**`/setup` dit la version de la copie, les scanners et le dashboard.**
Ce que ça change pour vous : `bash core-scripts/setup.sh` équipe aussi gitleaks, semgrep et l'outil d'audit de chaque famille de modules (macOS ; Linux en partie, le reste nommé) ; pytest n'est exigé que si votre projet a un module Python ; le bilan de `/setup` passe à sept jambes, de la version au dashboard.

**Un plan non commité n'ouvre plus de nuit.**
Ce que ça change pour vous : `night_approve.py` et `/night` refusent un plan hors de git, modifié depuis HEAD ou masqué (`assume-unchanged`, `skip-worktree`, `ident`) ; commitez le plan avant `--apply` — `/planning` et `/planning-all` vous rendent la ligne de commit, `/kickoff --defer-night` le commite lui-même.

**Toutes les définitions d'agents sont rédigées en anglais ; ce qu'elles vous impriment reste en français.**
Ce que ça change pour vous : rien dans le comportement — les agents vous répondent toujours en français, et ce qu'ils vous impriment (rapports, bannières `▸`, citations «…») reste en français ; seules leurs instructions internes passent en anglais. Vos propres défs restent libres.

**Le README de votre projet est en anglais et va à l'essentiel.**
Ce que ça change pour vous : `README.md` dit ce que fait l'usine, comment l'installer (`/setup`, `$setup` sur Codex et Copilot), où ouvrir le tutoriel `docs/usage.html` et vos commandes ; le détail reste dans `QUICK-SETUP.md` et les guides par hôte.

**Les agents ne contournent plus les hooks git.**
Ce que ça change pour vous : `--no-verify`, `-n` sur un commit et toute réécriture de `core.hooksPath` sont refusés à un agent ; défaire les hooks reste votre geste.

**Votre configuration de qualité est protégée.**
Ce que ça change pour vous : une fois la graine `CONFIG_QUALITE_PROTEGE` posée (elle arrive armée chez vous), un agent ne modifie plus par Edit/Write une config lint ou format qui existe déjà ; en créer une reste permis, et vous accordez une écriture par une ligne de `.agents/state/gates/CONFIG_QUALITE_AUTORISE`.

**Les critiques vérifient avant de corriger.**
Ce que ça change pour vous : un défaut bloquant de sécurité ne compte qu'avec sa reproduction, l'autre juge le contre-vérifie avant la correction, et les critiques cherchent aussi les échecs silencieux.

**Une porte rouge à la clôture se répare en 3 tentatives au plus.**
Ce que ça change pour vous : l'agent ne boucle plus sans fin sur une porte rouge ; il s'arrête dès que les erreurs augmentent ou à la troisième tentative, puis vous demande quoi faire.

**Dans une fournée, chaque lot est relu par `exec-critic` dès sa fusion, sans attendre les autres.**
Ce que ça change pour vous : un `exec-critic` relit chaque lot dès sa fusion, pendant que les autres devs avancent ; verdict et rapport arrivent dans le retour. Il attend et tient une place de charge (`max_devs: 1` : série). `exec_par_lot: false` : aucun exec-critic ; le SAST final lit toujours toute la fournée.

**La plupart des commandes et de leurs options parlent anglais, l'ancien nom reste accepté.**
Ce que ça change pour vous : `/planning all`, `tasks.py batch`, `--without-review`… : l'aide affiche le nom anglais ; chaque ancien nom reste accepté, vos scripts ne cassent pas (sauf une option abrégée : tapez le nom entier) ; `fusion_enregistrement.py` et les messages des scripts restent en français.

**Sur AWS, l'agent Terraform pose les tags `Project` et `Env` sur chaque ressource taguable.**
Ce que ça change pour vous : sur aws seulement, `terraform-deployer` pose `Project` (nom du projet) et `Env` (`POC`, `DEV` ou `PROD`) sur chaque ressource taguable, sans les inventer : `POC` si vos specs le disent, sinon `dev` → `DEV`, `prod` → `PROD`, le reste choisi par vous parmi ces trois. Azure, GCP : inchangés.

**Le noyau `cadre` déménage sous `.agents/vendor/cadre/`.**
Ce que ça change pour vous : le noyau `cadre` vit sous `.agents/vendor/cadre/` et arrive avec `.agents/`. À la mise à jour, retirez l'ancien dossier (`git rm -r src/cadre`) ; si un `.gitignore` ou une exclusion globale ignore `vendor/`, vérifiez que `.agents/vendor/` est commité. La roue installée ne change pas.

**Jalons de la queue après le dev.**
Ce que ça change pour vous : `tasks.py chrono <T> show` mesure aussi la fin d'une tâche : `review-scope` relève les juges et ouvre la clôture, puis `done` complète la clôture, la correction et la porte (lignes `frozen` et `frozen-linux`), sans jamais refuser le verbe.

**Une nouvelle page de démarrage.**
Ce que ça change pour vous : `docs/usage.html` devient « Démarrer la Glass Factory », en quatre onglets (Installer, Travailler, Dashboard, Avancé), et le README l'ouvre en tête. Ouvrez-la dans un navigateur pour installer la factory et la prendre en main.

**Les agents de développement travaillent plus vite.**
Ce que ça change pour vous : `dev-mono`, `dev-multi` et `frontend-fidelity` réfléchissent moins longtemps, pour aller plus vite ; les juges restent au-dessus. Pour garder votre réglage, rééditez-le après la mise à jour puis lancez `apply-mode.py restore --recapture`.

**exec-critic et la revue de sécurité jugent le même diff en même temps.**
Ce que ça change pour vous : après chaque passe de dev, `exec-critic` et `security-code-review` partent ensemble là où l'hôte lance des sous-agents en parallèle (mesuré : Claude Code), ailleurs en série, exec-critic d'abord ; la correction attend les deux verdicts et relance les deux.

**Le lanceur dit à exec-critic quoi rejouer.**
Ce que ça change pour vous : `/kickoff` et `/night` passent à exec-critic un mandat écrit — chaque critère rejoué avec sa sortie réelle, les preuves du dev rejouées seulement là où elles vérifient, les gestes prescrits sondés à travers les gardes, jamais exécutés, et jamais un push.

**Le dev rejoue la liste du juge avant de rendre.**
Ce que ça change pour vous : `dev-mono`, `dev-multi` et `frontend-fidelity` rejouent eux-mêmes chaque critère, un mutant par témoin neuf et les commandes qu'ils prescrivent, dans un clone sans `origin`, et rendent un bloc `PROOFS:` que le juge relit.

**Le planificateur rejoue la grille du critique avant de rendre son plan.**
Ce que ça change pour vous : le planificateur joint à son plan une commande par prémisse, un mutant par témoin et la grille du critique ; le critique donne tous ses bloquants dès le premier tour ; à un refus, le planificateur reçoit le verdict entier, écrit dans un fichier à côté du plan, plus jamais un résumé.

**Un dev ou un juge ne joue que les bancs nommés dans son mandat.**
Ce que ça change pour vous : chaque mandat porte une ligne `BANCS:` de bancs exacts ; un hook refuse un mandat de dev ou de juge qui n'en a pas ou qui y glisse une formule ouverte ; la suite complète reste jouée par la porte. Fini le dev qui rejoue cent bancs avant la porte.

**Le critique de plan rend son verdict plus vite, et l'advisor n'est plus appelé sans votre demande.**
Ce que ça change pour vous : le critique de plan rend son verdict plus vite, au prix de quelques bloquants de moins trouvés au premier tour, et le planificateur est allégé ; l'outil `advisor` n'est plus appelé, sauf si vous le demandez dans le mandat.

**`/qwen-dev` : un pont plus fiable, et la garde dite exactement.**
Ce que ça change pour vous : `indexer` et `board-reporter` restent sur Claude ; deux hooks par écriture, quatre gardes rejouées par étape, autres hooks coupés sans rejeu ; ce qu'ils lisent (board, index, code) peut donc quitter le poste ; `--on` avertit si le label manque ou est refusé (macOS, service launchctl).

**Le chrono réel des agents et des portes.**
Ce que ça change pour vous : sur Claude Code, durée et jetons des agents nommés sont relevés ; la durée de chaque porte, sur tout hôte ; `--chrono-aid` écrit le chrono du tour de plan, jamais 0 (anciens à 0 : non mesurés). Graine `CHRONO_REQUIRED` armée ; pour la retirer, effacez `.agents/state/gates/CHRONO_REQUIRED`.

**Le chrono de chaque tâche, même sans /kickoff.**
Ce que ça change pour vous : `tasks.py start`, `fournee`, `retour` et `done` posent eux-mêmes les jalons de la tâche ; la ligne d'état de Claude Code montre l'étape en cours et son temps (` · ⏱ dev 12m/~20m`), ailleurs `tasks.py chrono <T> show --watch` ; `done` avertit d'un cycle incomplet, sans refuser.

**La porte note l'étape où elle rougit.**
Ce que ça change pour vous : `porte-chrono.tsv` gagne une 6e colonne — `-` au vert, la première étape rouge, `?` si rien n'a pu être noté ; `specs.py chrono --etapes` compte les rouges par étape. C'est cette mesure qui décidera comment accélérer la porte.

**Toute porte purge à l'entrée cinq réglages qui comptaient une suite sans la jouer.**
Ce que ça change pour vous : `verify.sh` retire à l'entrée `BASH_ENV`, `BASH_TEST_TIMEOUT_BIN`, `CADRE_GATE_TIMEOUT_BIN`, `PYTEST_ADDOPTS` et `PYTEST_PLUGINS`, et le dit ; une option de pytest dont vos tests ont besoin va dans `pytest.ini` (`addopts`) ou `scripts/verify-projet.sh`.

**Les écrans se planifient avec leur spec d'interaction.**
Ce que ça change pour vous : un plan d'écran sans ligne `INTERACTION:` (focus, Échap, modale, empilement, WCAG, largeurs, états) est refusé ; le dev d'écran joue la grille du juge avant de rendre et repasse en `high` sur Claude Code ; l'aide « ? » du tableau de bord devient une vraie modale.

**Consignes d'outil dans les défs dev et exec-critic.**
Ce que ça change pour vous : chaque hôte reçoit ses gestes d'outil (une commande simple par appel, globs bornés, lecture avant édition sur Claude Code) ; en worktree Claude Code, la mesure sur clone se joue en deux appels au chemin littéral, `rev-parse` puis `checkout -f --detach`, et leur ordre reste une consigne.

**La fin de fusion d'un lot s'écrit seule.**
Ce que ça change pour vous : la durée de chaque lot inclut sa fusion sans geste de l'orchestrateur ; `tasks.py retour` et `done` la ferment à l'heure du commit de fusion, dans HEAD ou dans la livraison `--vers`. La première fin écrite l'emporte. Avance rapide, squash ou rebase : la fusion reste dite sans fin.

**Des docs livrées propres.**
Ce que ça change pour vous : README, manuel, journal et guides livrés sont écrits pour vous, sans identifiant interne ni mesure de mainteneur ; le journal du kit d'avant `0.1.0` ne vous parvient plus.

**Sous Copilot CLI, une garde qui tombe refuse l'outil.**
Ce que ça change pour vous : sous Copilot CLI (bash), une garde `preToolUse` qui plante, dépasse 7 s ou échoue refuse l'outil, sans Python 3 tout outil ; `--reprise`, l'installation de skills et la configuration Jira sont refusées depuis un shell lancé par Copilot CLI : utilisez votre propre terminal.

### Corrigé

**Le noyau livré reste suivi quand votre dépôt ignore `vendor/` ou `bin/`.**
Ce que ça change pour vous : un `git add -A` d'adoption garde `.agents/vendor/`, `.agents/skills/vendor/` et `.agents/bin/`. Déjà adopté : ajoutez `!/vendor/`, `!/skills/vendor/` et `!/bin/` à `.agents/.gitignore`, puis `git add .agents/.gitignore .agents/vendor .agents/skills/vendor .agents/bin`.

### Contrat

**`/qwen-dev` et la route de dev locale sont retirés : le contrat passe en `0.6.0`.**
Ce que ça change pour vous : la commande `workflow:qwen-dev` sort du contrat ; plus aucun dev ne part vers un modèle local, les devs tournent sur Claude ; un fichier `.agents/state/local/DEV_ROUTE` resté chez vous devient inerte.

**Le contrat passe en `0.5.0` : les commandes `jira` et `setup` y entrent.**
Ce que ça change pour vous : `jira` et `setup` (`/jira`, `/setup` sur Claude Code, `$jira`, `$setup` ailleurs) deviennent des commandes publiques du contrat ; aucun élément n'est retiré ni changé.

### Limites connues

**L'attribution du tableau de bord se colle à la main.**
Ce que ça change pour vous : la garde refuse `OTEL_RESOURCE_ATTRIBUTES` dans `.claude/settings.json` ; collez la sortie de `project_init.py --print-otel-env --format=json` dans `.claude/settings.local.json`.

**Le mode nuit sans surveillance demande votre liste d'autorisation.**
Ce que ça change pour vous : `/night --headless` refuse sans `.agents/state/gates/NIGHT_HEADLESS.allow`, qui ne voyage pas ; si vous en écrivez une, ajoutez-y les lignes `charge_poste.py verdict`.

**`index.db` ne se reconstruit plus dès qu'un chemin porte une espace.**
Ce que ça change pour vous : la migration refuse alors la base entière et `symbols.py` lit une base périmée ou absente ; l'installation le dit dégradé, et l'index Markdown reste complet.

**Le plafond appris ne se calibre pas encore chez vous.**
Ce que ça change pour vous : `charge_poste.py` n'apprend qu'avec des agents en vol, ce que les lanceurs livrés ne lui donnent pas encore ; vos vagues restent à la base de départ.

**Le chrono des tâches n'est jamais purgé.**
Ce que ça change pour vous : chaque tâche laisse un journal de chrono local, sous `.agents/state/local/task-chrono/`, qu'aucun outil ne purge ; le tableau de bord les relit tous à chaque lecture et ralentit à mesure qu'ils s'accumulent.

**Des bancs du kit rougissent encore chez vous.**
Ce que ça change pour vous : les bancs bornés au kit ne jugent plus vos ajouts (agents, skills, commandes, README, hooks, `*.test.sh`) ; restent jugés la forme de vos défs, un agent hors de la grille des modes ou sur le seul hôte Claude, et une surface du kit réécrite. Une CI qui lance `.agents/evals` rougira.

**Vos hooks ajoutés ne sont plus vérifiés par le kit.**
Ce que ça change pour vous : les bancs du kit ne jugent que ses hooks ; durcir les vôtres (préfixe, lanceur, zéro appel LLM) est à votre charge. Restent jugées : une jambe sans script `.py`, `.sh` ou `.ps1`, ou au script posé sous un dossier du kit ; une jambe du kit que vous modifiez, même en y chaînant le vôtre.

**Des gardes restent contournables.**
Ce que ça change pour vous : les refus mécaniques empêchent d'oublier une étape, pas de tricher ; plusieurs gardes (shell, gardes jumelles des hôtes, hooks, installation) se contournent encore, et leur fermeture est planifiée après `0.1.0`.

**Couverture inégale selon l'hôte.**
Ce que ça change pour vous : une garde ne tient pas de la même façon sur chaque hôte ; l'état hôte par hôte est dans `AGENTS.md` (Enforcement layer) et dans `README-OTHER-HOSTS.md`.
