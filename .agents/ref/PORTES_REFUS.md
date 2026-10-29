# Portes du kit — refus, cause, remède

Une section par porte : `où:` (le geste qui la déclenche et son marqueur d'armement), `refus:` (le texte du code, recopié à l'octet), `source:`, `cause:`, `remède:`, `sortie tracée:`. Lue par chemin depuis `task-board` et `verification-discipline` ; atteinte sur Claude Code par la skill `portes-refus-pointer`. Banc : `.agents/evals/test_portes_refus.py`.

## Avant de rejouer : trois réflexes

1. **Un refus est une information.** Lis la cause avant de rejouer : le même geste rejoué donne le même refus.
2. **Ne reformule jamais pour passer à côté du motif.** `python -c`, `cp`, `tee` ou `sed -i` à la place d'une redirection refusée, une écriture par le shell à la place d'un Edit refusé, une autre forme de la même commande : c'est contourner la garde, pas la satisfaire (AGENTS.md § Enforcement layer).
3. **Une sortie tracée est un geste VISIBLE, réservé à son cas.** Elle reste au board (ou au journal) avec sa raison. Hors de son cas, ou quand la sortie est un geste du pilote : rapporte le refus au pilote, avec sa cause.

## BORNE — ce que cette fiche ne dit pas

- **Hôte de référence : Claude Code.** Les textes sont ceux que le code écrit sur Claude Code (stderr d'un hook, exception de `tasks.py`/`specs.py`). Ailleurs, un hook refuse par une enveloppe JSON `permissionDecision: deny` (skill `guardrails`) dont le texte n'est pas garanti identique.
- **Un `refus:` est un SEGMENT FIXE d'UN SEUL littéral du code**, jamais le message entier : un message bâti par f-string ou par variable n'est cité que par sa partie fixe. Une section peut porter plusieurs `refus:` ; elle ne liste pas TOUS les refus de sa porte (safe-bash en a plus de dix).
- **Le banc prouve le littéral, jamais la cause ni le remède** : ceux-ci se relisent contre le code cité.
- **Liste FERMÉE de 21 portes**, tenue par le banc. Une règle de prose (par exemple l'arrêt de `/kickoff` au routage) n'est pas une porte du code et n'est pas ici.
- **Marqueur d'armement** : chaque `où:` nomme le fichier `.agents/state/gates/<NOM>` qui arme la porte, ou dit qu'elle n'en a pas. Un agent ne pose ni ne retire un marqueur : c'est un geste du pilote.

## porte et push

- où: `bash core-scripts/verify.sh` (la porte, périmètre de la CI) puis `git push`, que `.githooks/pre-push` juge là où `core.hooksPath` pointe sur `.githooks/` ; marqueur d'armement : aucun pour le tampon, `.agents/state/gates/PUSH_DEFAUT_PROTEGE` pour la branche par défaut.
- refus: « nothing here says this tree was ever verified. »
- refus: « the stamp records mode=live — a live-tree run is not anchored to a frozen checkout. »
- refus: « --at: refusing to report a verdict — »
- refus: « --rouges: aucune porte rouge mémorisée »
- source: `.githooks/pre-push`, `core-scripts/verify.sh`
- cause: le SHA poussé n'est pas couvert par un verdict vert ancré : pas de tampon, tampon malformé, porte jouée en arbre vivant (`mode=live`), verdict pour un autre SHA, ou porte rouge (sa dernière ligne dit alors `VERIFY FAILED @ <sha> — do not push.`). `verify.sh --rouges` ne rejoue que les rouges de la dernière porte complète ROUGE (`.agents/state/local/PORTE_ROUGES`, effacée à l'entrée de chaque porte complète) : sans elle, rien à rejouer ; un `REJEU VERT` n'écrit aucun tampon.
- remède: `bash core-scripts/verify.sh --at HEAD --linux` dans le kit (sur CE dépôt `--at HEAD` seul, dérogation pilote), `--at HEAD` chez l'adoptant ; jamais `| tail` ni `| head` ; porte rouge : lire la première étape `--- FAIL`, corriger, `bash core-scripts/verify.sh --rouges` (kit seul) pour rejouer les seules rouges, puis la porte complète ; puis pousser CE SHA-là.
- sortie tracée: aucune pour le tampon (`git push --no-verify` n'en est pas une : plus rien n'atteste le SHA, et `safe-bash` la refuse aux agents, règle `git-hooks-bypass`) ; vers la branche par défaut, la raison non vide dans `.agents/state/gates/PUSH_DEFAUT_AUTORISE`, consommée et journalisée — geste du pilote seul.

## revendication

- où: `tasks.py start` et la vraie `tasks.py fournee` avant toute mutation ; marqueur d'armement : aucun, toujours armée.
- refus: « REVENDICATION: publier/fusionner la branche, ou reprise par le pilote avec --reprise »
- refus: « REVENDICATION : reprise réservée au terminal du pilote, non lancé par un agent »
- source: `.agents/bin/tasks.py`, `.agents/bin/tasks_fournee.py`, `.agents/bin/tasks_requetes.py`
- cause: « publier/fusionner la branche… » : propriété attribuée à un autre pilote, même si le board local du clone non fusionné nomme encore l'ancien, sans `--reprise` ; « réservée au terminal du pilote… » : `--reprise` sans raison non blanche, sans stdin et stderr TTY, ou sous un marqueur d'agent — la reprise exige la saisie exacte de l'identifiant, demandée APRÈS le précontrôle : l'invite nomme le propriétaire courant et chaque refus levé est dit, suffixé « levée par --reprise ». Deux avis, jamais un refus : `REVENDICATION: ancien pilote a poussé après reprise` si la pointe distante n'est contenue, par filiation, dans aucune des pointes gardées à la reprise (une pointe gardée absente du clone : le commit de transfert la remplace ; sans pointe gardée : prise déjà fusionnée dans HEAD, ou pointe hors du commit de transfert), sinon — pointe contenue ou filiation illisible — `REVENDICATION: prise levée par reprise encore publiée` ; aucun ne réattribue la propriété.
- remède: l'agent saute la tâche et rapporte le refus ; jamais de `--reprise` automatique ni de `--sans-revendication` (option refusée). Le pilote peut transférer de jour dans son terminal interactif avec `--reprise "<raison>"` et la confirmation ; sous Windows, Windows Terminal ou `winpty bash .agents/pyrun.sh .agents/bin/tasks.py start <T> --reprise "<raison>"`. Sous Claude Code et les hooks du kit qui posent `AGENTS_HOOK_HOST` (Codex, Kimi, Copilot) — Kimi : supposé, non mesuré —, le marqueur d'agent refuse ; Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent (mesuré, 1.0.96) : ce marqueur refuse la reprise — faux positif : `COPILOT_CLI` est hérité par un shell que le pilote lance depuis Copilot CLI (échappement `!` compris), d'où il reprend alors depuis un terminal ouvert hors de Copilot CLI. Codex, Gemini et Kimi sans marqueur franchissent TTY + saisie en une commande : seule la doctrine interdit à l'agent de reprendre.
- sortie tracée: aucune pour l'agent ; le transfert motivé et confirmé du pilote est écrit au board et son intention de label Jira reste en attente jusqu'à acquittement.

## commit-msg

- où: `git commit`, que `.githooks/commit-msg` juge là où `core.hooksPath` pointe sur `.githooks/` ; marqueur d'armement : aucun (l'armement est le réglage `core.hooksPath`).
- refus: « REFUSE par commit-msg : le sujet ne porte aucun type connu. »
- refus: « REFUSE par commit-msg : aucun numéro de tâche. »
- source: `.githooks/commit-msg`
- cause: (type) le sujet n'ouvre sur aucun des dix types `feat:` `fix:` `chore:` `docs:` `refactor:` `perf:` `test:` `revert:` `ci:` `build:` (une `(portée)` et un `!` de rupture sont admis). (numéro, jugé après le type et chaque exemption) le message ne porte ni `T-<id>` ni `Sans-tache:`, ET le palier est atteint : parmi les 200 derniers commits hors fusion de HEAD, au moins 20 éligibles (sujet autre que `chore(state): ` / `chore(runs): `) dont 95 % au moins portent un numéro ; en dessous, un AVERTISSEMENT seul, rc 0.
- remède: (type) réécrire le sujet `type(portée): sujet`, puis recommiter. (numéro) porter `T-<id>` — 3 à 15 chiffres ou 10 à 26 caractères d'ULID — sur une ligne non commentée (pas `#`) au-dessus de la ligne de coupe `>8` : dans le sujet `fix(x): le sujet (T-<id>)`, ou une ligne de corps `Tâche: T-<id>`.
- sortie tracée: (type) aucune. (numéro) une ligne `Sans-tache: <pourquoi>`, au moins 10 caractères non blancs après les deux-points (`git commit -m "<sujet>" -m "Sans-tache: <pourquoi>"`), comptée par `tracabilite.py bilan`. La garde juge la FORME ; `--no-verify` lui échappe côté git, ce n'est pas une sortie — et `safe-bash` le refuse aux agents (§ safe-bash, règle `git-hooks-bypass`).

## SAST

- où: `.agents/security/semgrep-scan.sh`, en hook (`--hook`, `PostToolUse` Edit|Write et `Stop`, bloquant sur stderr et exit 2) et dans la revue de sécurité ; marqueur d'armement : aucun (enregistrement dans `.claude/settings.json`).
- refus: « finding(s) on the diff — route to security-code-review triage »
- source: `.agents/security/semgrep-scan.sh`
- cause: un finding semgrep sur le diff : classe 1, code produit.
- remède: triage par `security-code-review` ; un HIGH ou CRITICAL se corrige. Un `COVERAGE DEGRADED` n'est pas un vert : le vide n'y prouve rien.
- sortie tracée: aucune pour un HIGH ou CRITICAL (classe 1, non waivable).

## SCA

- où: `.agents/security/sca-scan.sh`, quand un manifeste de dépendances ou un fichier IaC a changé (`security-orchestrator`) ; marqueur d'armement : aucun.
- refus: « SCA GATE (effective, waivers applied): NO-GO »
- source: `.agents/security/sca-scan.sh`
- cause: une dépendance vulnérable connue reste bloquante après application des dérogations du registre `.agents/security/sca-waivers.json`.
- remède: classe 2 actionnable : monter la version (politique `.agents/security/sca-policy.json`) ; classe 3 : décision du pilote. Une dépendance ne bloque jamais le développement : le correctif va dans sa propre tâche.
- sortie tracée: la dérogation de classe 3, décision du pilote tracée au registre — jamais un geste d'agent.

## secrets

- où: `.agents/security/gitleaks-scan.sh` (hook et porte) ; marqueur d'armement : aucun, toujours armée.
- refus: « SECRETS GATE (class-0, NON-WAIVABLE): »
- refus: « secret(s) detected — BLOCKED »
- source: `.agents/security/gitleaks-scan.sh`
- cause: un secret détecté dans le périmètre scanné : classe 0.
- remède: retirer le secret ET faire tourner le credential. Faux positif : le rapporter au pilote, qui exempte son LITTÉRAL dans `.gitleaks.toml` ; `gitleaks:allow` et `.gitleaksignore` sont ignorés par cette porte.
- sortie tracée: aucune — classe 0, absolue, non waivable.

## chemins protégés

- où: Edit/Write, que `.claude/hooks/protect-paths.sh` juge en `PreToolUse` (ailleurs, les jumeaux à l'octet `protect_paths.py` de `.codex/` et `.gemini/`) ; marqueur d'armement : aucun, toujours armée (motifs du script et `.claude/hooks/protected-paths.local`), SAUF la règle `config-qualite`, armée par `.agents/state/gates/CONFIG_QUALITE_PROTEGE` — cinquième graine, semée armée chez l'adoptant, absente du kit tant que le pilote ne l'y pose pas.
- refus: « (CLAUDE.md do-not-touch). Ask the user for explicit approval; »
- refus: « looks credential-related. Secrets are never edited by agents. »
- refus: « is the kickoff guard's arming file — only the pilot edits it, by hand »
- refus: « est une config lint/format EXISTANTE du projet et CONFIG_QUALITE_PROTEGE est posé »
- refus: « ne couvre un chemin hors racine ; seul le pilote lève ce refus, en retirant le marqueur. »
- refus: « est le registre d'exceptions du scanner Unicode, réservé au pilote »
- refus: « is the exception register of the Unicode scanner, reserved to the pilot »
- source: `.claude/hooks/protect-paths.sh`, `.codex/hooks/protect_paths.py` (jumeau `.gemini/hooks/protect_paths.py`), `.agents/bin/config_qualite_guard.py` — `config_qualite_reason`, `UNICODE_ALLOWLIST_DENY_REASON`
- cause: le chemin visé est protégé : motif interdit (`src/legacy/`, `generated/`…), fichier d'allure credential, configuration MCP, internes d'un `.git`, fichier d'armement ou de sortie d'une garde. Règle `config-qualite` (T-01M5C1AHZM41P9C3QH6X7PEQY1), marqueur posé seulement : le nom de base replié est une config lint/format de la liste FERMÉE de `config_qualite_guard.py` ou de ses deux motifs, et une de ses formes EXISTE déjà (la créer reste permis) ; une forme hors de la racine du projet ne s'octroie pas. Règle `unicode-allowlist` (T-01M5CN9FM2MPY8Z00AS7FTXXWH) : `.agents/security/unicode-allowlist.json`, suffixe replié, jusque hors de la racine. Bornes, écrites dans le code : `cp`, `sed -i`, `tee`, `python3 -c` écrivent encore ces fichiers ; vers le registre Unicode, une redirection à cible CITÉE ou par le nom nu après un `cd` passe (safe-bash ne refuse que la cible non citée) ; `pyproject.toml`, `setup.cfg`, `tsconfig*`, `jest`/`vitest`, `pytest.ini` et `package.json` sont hors liste ; une config imbriquée ABSENTE se crée ; sur Claude, marqueur posé sans python 3, rien n'est jugé.
- remède: rapporter au pilote, qui édite lui-même ou approuve ; jamais une écriture par le shell pour passer à côté. `config-qualite` : corriger le code plutôt qu'affaiblir la config ; un changement légitime s'ouvre par le pilote seul, une ligne `<chemin|préfixe/> T-<8 chiffres ou ULID> <AAAA-MM-JJTHH:MMZ>` (UTC) dans `.agents/state/gates/CONFIG_QUALITE_AUTORISE` ; hors racine, aucun octroi ne vaut, seul le retrait du marqueur lève le refus. `unicode-allowlist` : la décision tracée (`specs.py add --kind decision`), puis le pilote écrit l'entrée à la main.
- sortie tracée: aucune pour un agent ; l'octroi de `CONFIG_QUALITE_AUTORISE` (journalisé `hook.warn`, règle `config-qualite-octroi`) est un geste du pilote, qui ne lève que ce refus-là.

## safe-bash

- où: toute commande Bash, que `.claude/hooks/safe-bash.sh` juge en `PreToolUse` (ailleurs, les jumeaux à l'octet `safe_bash.py` de `.codex/` et `.gemini/`, dont le juge git est `safe_bash_git.py`) ; marqueur d'armement : aucun, toujours armée.
- refus: « WARNING by hook: rm/mv via Bash bypasses Claude Code checkpoints (not rewindable). »
- refus: « BLOCKED: this command redirects a write (>, >>, &>, ...) to a tracked or protected file »
- refus: « BLOCKED: refusing catastrophic rm. »
- refus: « this git command skips the repository's git hooks (rule git-hooks-bypass) »
- refus: « bounded, not closed: these are the holes we know. »
- source: `.claude/hooks/safe-bash.sh`, `.codex/hooks/safe_bash_hooks.py` — `HOOKS_REASON`
- cause: la commande écrit, déplace ou supprime hors du chemin Edit/Write (rm/mv d'un fichier suivi, redirection vers un fichier suivi ou protégé), ou relève d'une autre règle nommée dans le message (wipe git non borné, `git … --output`, `git grep -O`, ripgrep absent). Règle `git-hooks-bypass` (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) : la commande git lancerait son verbe SANS les hooks du dépôt (pre-commit, commit-msg, pre-push) — `--no-verify` et toute abréviation dès `--no-v` sur commit, push, merge, rebase, am et pull ; `-n` dans une grappe courte de `commit` ou `am` (`-an`, `am -n`) ; une expansion NON citée parmi les options de ces six verbes ; `-c`/`--config-env` dont la valeur porte `hookspath` ou `include` sur un verbe qui lance des hooks (ces six, cherry-pick, revert), `alias.` sur tout verbe ; un `git config` qui écrit, édite ou retire `core.hooksPath`, `core.worktree`, `alias.*` ou `include.*` (`--unset` compris) ; une affectation `GIT_CONFIG_*`, `HUSKY=`, `HUSKY_SKIP_HOOKS=`, `LEFTHOOK=` ou `SKIP=` dans une commande qui lance un tel verbe. Exemption EXACTE : `core.hooksPath=.githooks` — clé dans toute casse, valeur telle qu'écrite (`.GITHOOKS` refusé) —, en `-c` comme en `git config [set] core.hooksPath .githooks`. Passent : `push -n`, `rebase -n`, `cherry-pick -n`, `commit -m "--no-verify"`, `config --get`, `config --list`. Faux positifs nommés : un message de commit qui cite `HUSKY=` ou `SKIP=`, `git merge -m "--no-verify"`, la lecture implicite `git config core.hooksPath` (écrire `--get`). Bornes nommées et NON refusées, liste non close : `<(…)` avant une option, `send-pack`, `update-ref`, `commit-tree`, `git config "$K" v`, `@{u}` avant une option, `--git-dir`/`--work-tree`, `HOME=`/`XDG_CONFIG_HOME=`, `bash -c "…"`, un alias déjà configuré — le message entier les énumère.
- remède: Edit/Write pour un fichier suivi ; un chemin hors dépôt (`/tmp/`) pour un jetable ; sinon demander au pilote d'approuver la commande exacte. Le message dit lui-même ce qu'il ne tient pas : ce n'est pas une invitation. `git-hooks-bypass` : rejouer sans le contournement et corriger ce que le hook signale ; il n'y a pas de sortie pour un agent — désarmer ou retirer les hooks (`git config --unset core.hooksPath` compris) est un geste du pilote, à la main.
- sortie tracée: aucune.

## audit des skills

- où: `npx skills add`, que `.claude/hooks/audit-gate.sh` juge, et le repli GitHub `skills_github_fallback.py install` (et `search`), qui passe le texte téléchargé au scanner `unicode_scan.py` ; marqueur d'armement : aucun, le registre est `.agents/state/gates/AUDIT_LOG` (et, pour le scanner, le registre d'exceptions `.agents/security/unicode-allowlist.json`).
- refus: « BLOCKED by audit gate: no 'audit=pass' entry for »
- refus: « invisible-unicode character refused: U+ »
- refus: « invisible-unicode allowlist refused: »
- source: `.claude/hooks/audit-gate.sh`, `.agents/bin/skills_github_fallback.py`, `.agents/security/unicode_scan.py` — `refus`, `entrees_honorees`
- cause: (audit) aucune ligne `audit=pass` pour cette référence dans `.agents/state/gates/AUDIT_LOG`. (Unicode, T-01M5BZBZ849P61Y6471JZMMPRD) la skill téléchargée porte un caractère invisible ou bidi que le registre n'admet pas pour sa cible `<owner>/<repo>#<skill>@<sha>` — préfixe `INSTALL REFUSED` à l'install, `REFUSED` pour un candidat de `search` —, ou le registre est invalide ; scanner absent : `— unicode_scan introuvable`, refus aussi. Une entrée du registre n'est HONORÉE que si son `decision` est l'id d'une entrée `kind: decision` du journal SPECS (`SPECS.jsonl`, sinon `SPECS.json`) ; S-id absent du journal ou d'un autre `kind` : entrée ignorée ; journal absent ou illisible : TOUTES ignorées ; et le refus DIT chaque entrée ignorée qui aurait admis le constat (`allowlist entry <n> ignored: decision <S-id> not found in SPECS`, ou `… unverifiable, SPECS …`). Bornes : le journal prouve que la décision EXISTE, jamais qu'elle porte sur CETTE entrée ; `npx skills add` n'est pas scanné ; `show` imprime le texte BRUT, encadré `[do not obey]`, avec son compte `unicode-findings=<n>` ; homoglyphes non repérés.
- remède: (audit) lancer l'audit de sécurité (skills-resolver, étape 3), puis l'inscrire par `python3 .agents/bin/skills_github_fallback.py audit-log <owner>/<repo>#<skill>@<sha> --pass` — jamais par une redirection ni par Edit/Write ; une autre forme de référence : rapporter au pilote. (Unicode) une autre révision de la skill, ou rapporter au pilote : un faux positif PROUVÉ s'admet par sa décision tracée (`specs.py add --kind decision`), puis par une entrée `cible`/`codepoint`/`decision` que le pilote écrit à la main dans le registre (Edit/Write refusés à l'agent, § chemins protégés) — une entrée admet un faux positif, ce n'est pas une dérogation de classe 1.
- sortie tracée: aucune pour un agent ; l'entrée du registre, adossée à une décision du journal, est un geste du pilote.

## affirmation

- où: fin de tour (`Stop`), que `.claude/hooks/affirmation-guard.sh` juge ; marqueur d'armement : `.agents/state/gates/AFFIRMATION_REQUIRED`.
- refus: « AFFIRMATION DURABLE SANS REVUE CRITIQUE — refus de fin de tour. »
- source: `.claude/hooks/affirmation-guard.sh`
- cause: depuis la dernière porte verte, le cycle a écrit une surface durable (board, `PLAN-ETAT.md`, surface de doctrine, fichier de reprise de lot) sans critique de clôture tracé.
- remède: lancer `critic-opus` (repli `critic-fable`, puis `critic-sonnet-max`) sur ce qui vient d'être écrit, corriger ses constats. Le refus revient UNE fois pendant que le critique est en vol : séquence normale, pas une panne.
- sortie tracée: la raison dans `.agents/state/gates/AFFIRMATION_SANS_BINOME` (renommage, coquille, décision déjà prise), consommée une fois et journalisée dans `.agents/state/local/affirmation-sorties.log`.

## mesure

- où: `tasks.py new` ; marqueur d'armement : `.agents/state/gates/MESURE_REQUIRED` (la FORME d'une valeur donnée est tenue même sans lui).
- refus: « new: refused — a defect is MEASURED before it becomes a task »
- refus: « new --mesure: --motif <M> is REQUIRED — why is this defect not fixed on the »
- refus: « new --pas-un-defaut: refused — the title opens on the lexicon of a DEFECT »
- source: `.agents/bin/tasks_mesure.py` — SYM-12893 `mesure_refusal`
- cause: une tâche ouverte sans dire si c'est un défaut mesuré, une mesure sans motif de la liste fermée, ou `--pas-un-defaut` sur un titre au lexique d'un défaut.
- remède: `tasks.py new "<titre>" --mesure "<commande qui reproduit> => <observé>" --motif <M>`, M parmi `garde`, `securite`, `decision-pilote`, `gros`, `sans-fournee` ; un défaut mineur se corrige sur place, sans tâche.
- sortie tracée: `--pas-un-defaut "<pourquoi>"` pour une fonctionnalité, une décision ou un chantier.

## chaîne de plan

- où: `tasks.py start` ; marqueur d'armement : `.agents/state/gates/PLAN_CHAIN_REQUIRED` (absent du kit, semé armé chez l'adoptant).
- refus: « la chaîne de plan n'est pas tracée. »
- refus: « aucun plan tracé (attendu : `planner`) »
- source: `.agents/bin/tasks_gardes.py` — SYM-11062 `plan_chain_refusal`
- cause: il faut les DEUX traces de l'hôte dans les 24 h, un `planner` (rôle planner) ET un `plan-critic` (rôle reviewer) : le refus tombe dès que L'UN des deux manque (une trace plus vieille est périmée, ignorée).
- remède: faire tourner `planner`, puis `plan-critic` sur le plan — l'hôte écrit la trace. Petite tâche (5 fichiers ou moins, sans garde, sans décision ni sécurité ouverte) : `tasks.py direct <T>`, puis `start`.
- sortie tracée: `tasks.py start <T> --sans-chaine "<pourquoi>"` (coquille, renommage, ticket caduc, `plan-critic` indisponible), visible au board.

## amont d'abord

- où: `tasks.py start` (depuis `pending`, `blocked` ou `done`) et `tasks.py fournee` ; marqueur d'armement : aucun, armée sur tout `depends_on` déclaré.
- refus: « Un cycle ne se satisfait jamais : coupe-le, puis relance. »
- refus: « Traite d'abord ces amonts, dans cet ordre (`tasks.py deps-ready »
- refus: « Sortie tracée : `--sans-dependances »
- source: `.agents/bin/tasks_graphe.py` — SYM-19643 `refus_amont`
- cause: `deps-ready` rend un jeton non passant : `CYCLE`, `AMONT_OUVERT`, `INEXPLOITABLE` ou `PLAN_A_REPLANIFIER` (un amont clos à ou après la trace `plan approuvé`).
- remède: `tasks.py deps-ready <T>`, puis traiter les amonts dans l'ordre donné ; `PLAN_A_REPLANIFIER` : réviser le plan (`planner` puis `plan-critic`), nouvelle trace `plan approuvé` ; une arête TECHNIQUE fausse se retire par `tasks.py depends <aval> --retirer <amont>`, jamais un ordre du pilote.
- sortie tracée: `--sans-dependances "<pourquoi>"` — décision du pilote seul, visible au board.

## critique de clôture

- où: `tasks.py done` ; marqueur d'armement : `.agents/state/gates/BINOME_REQUIRED`.
- refus: « exige la REVUE CRITIQUE, et elle n'a pas eu lieu »
- refus: « exige la REVUE CRITIQUE, et la preuve empruntée est »
- refus: « l'état COURANT des fichiers de reprise »
- source: `.agents/bin/tasks_gardes.py` — SYM-11068 `binome_refusal` ; `.agents/bin/tasks_etats.py` — SYM-11806 `binome_reprise_refusal`
- cause: aucun critique de clôture tracé par l'hôte ; une preuve empruntée au slot périmée (antérieure à la porte verte précédente) ; ou une revue antérieure à la dernière écriture des fichiers de reprise de lot et de `PLAN-ETAT.md`.
- remède: lancer `critic-opus` (repli `critic-fable`, puis `critic-sonnet-max` à effort maximal) sur le travail qu'on ferme, corriger ses constats, puis la porte, puis `done`. Fichiers de reprise : les commiter d'abord, le critique APRÈS.
- sortie tracée: `tasks.py done <T> --raison "<pourquoi>" --sans-binome "<pourquoi pas de revue>"` pour un doublon, un ticket caduc ou une décision sans code — jamais pour franchir le refus des fichiers de reprise, qui est une décision du pilote.

## cible

- où: `tasks.py start`, `tasks.py done` et `specs.py add` d'un verdict `plan-critic …` ; marqueur d'armement : `.agents/state/gates/PLAN_CIBLE_REQUIRED`, pour le chantier de sa ligne `chantier=`.
- refus: « Chaque étape porte AU MOINS une valeur »
- refus: « Sortie tracée si la cible ne s'applique pas : »
- refus: « SPECS: refus — le verdict plan-critic de »
- source: `.agents/bin/plan_cible.py` — SYM-13436 `_message_refus`, SYM-08876 `refus_au_start`, SYM-08877 `refus_au_done`, SYM-08878 `refus_au_verdict`
- cause: une étape du plan approuvé ne porte ni `cible: « <nom> »`, ni `angle mort: <question>`, ni `décision pilote: S-<id>` ; ou le `plan=` d'un verdict n'est pas un chemin sûr.
- remède: annoter chaque étape nommée par le refus (grammaire : `.agents/ref/PLAN_GRAMMAIRE.md`), puis rejouer le geste.
- sortie tracée: `--sans-cible "<pourquoi>"`, visible au board.

## chrono

- où: `specs.py add` d'un verdict de boucle `plan-critic …` ou `lot <K> : plan-critic …` ; marqueur d'armement : `.agents/state/gates/CHRONO_REQUIRED`.
- refus: « SANS chrono du tour, et `CHRONO_REQUIRED` est »
- refus: « champ `chrono:` présent mais ILLISIBLE dans le --text d'un verdict »
- source: `.agents/bin/specs.py` — constantes `REFUS_CHRONO_ABSENT` et `REFUS_CHRONO_ILLISIBLE` (hors index)
- cause: le `--text` du verdict ne porte pas le chrono du tour, ou le porte sous une forme illisible.
- remède: ajouter au `--text` `chrono: planner=<durée>/<jetons> plan-critic=<durée>/<jetons>` (durée `3m12s`, `45s`, `1h2m` ou `12:34` ; jetons `45200`, `45.2k` ou `1.2M`).
- sortie tracée: `--sans-chrono "<pourquoi>"` quand l'hôte ne donne pas ces chiffres, visible dans l'entrée.

## voie directe

- où: `tasks.py direct <T>`, et son rejeu au `start` et au `done` là où l'estampille franchit une garde armée ; marqueur d'armement : aucun propre (le rejeu suit `PLAN_CHAIN_REQUIRED` et `PLAN_CIBLE_REQUIRED`).
- refus: « La voie directe est réservée aux petites tâches que ce code VÉRIFIE »
- refus: « C1 aucun write-set déclaré : `tasks.py writeset <id> <chemins>` d'abord, »
- refus: « Jamais une bascule silencieuse vers la consommation de la chaîne de plan. »
- source: `.agents/bin/tasks_direct.py` — SYM-13574 `refus_direct`, SYM-13576 `direct_message_refus`
- cause: une ou plusieurs des causes C1 à C6, toutes listées : write-set absent, de plus de 5 fichiers ou non exact ; chemin de garde ; décision ou sécurité ouverte ; estampille absente ou dépassée ; tâche close.
- remède: le chemin planifié (`planner`, `plan-critic`, porte humaine) ; ou corriger chaque cause listée et ré-estampiller ; `tasks.py direct <T> --retirer` rend la tâche au chemin planifié ; tâche close : `reopen` d'abord.
- sortie tracée: aucune pour l'estampille ; au `done` d'une directe qui franchit une garde armée, `done --sans-cible "<pourquoi>"`, visible au board.

## fournée

- où: `tasks.py fournee <T>`, à l'approbation d'un plan (`--dry-run` : le prévol seul) ; marqueur d'armement : aucun propre (la fournée rejoue chaîne, cible et amont).
- refus: « TASKS: refus de la fournée de »
- refus: « un lot ne lance pas de fournée »
- refus: « la fournée ne tourne pas »
- source: `.agents/bin/tasks_fournee.py`
- cause: le prévol liste TOUTES ses causes : trace `plan approuvé` absente ou pour un autre plan, plan qui n'enrôle pas la tâche, découpe `LOT:` refusée, write-set qui recouvre une tâche `running`, lien `depends_on` ou `blocked_on` entre membres, amont ouvert, parent dans un état qui ne lance pas.
- remède: `tasks.py fournee <T> --dry-run`, corriger chaque cause, relancer ; un recouvrement avec une tâche qui tourne : attendre sa clôture, ou sérialiser.
- sortie tracée: `--sans-chaine`, `--sans-cible` ou `--sans-dependances "<pourquoi>"`, posée sur chaque membre et visible au board — chacune réservée au cas de sa porte.

## lots

- où: `plan_lots.py check` (lu par `plan-critic`), et la fournée qui relit la même découpe ; marqueur d'armement : aucun.
- refus: « lignes non vides, plafond »
- refus: « `LOTS: aucun` à côté d'un `LOT:` — le plan dit deux choses »
- refus: « aucune ligne `INTÉGRATION:` alors qu'un `LOT:` existe — écris »
- refus: « ligne proche de `PLAN-LOT:` »
- refus: « la clé d'un plan de lot est celle d'un lot déclaré »
- refus: « écrit deux fois — un plan de lot par lot »
- refus: « sans ligne `PLAN-LOT:` valide — un maître consolidé couvre TOUS ses lots »
- source: `.agents/bin/plan_lots.py`
- cause: plan de plus de 45 lignes non vides, ligne `LOTS:`, `LOT:` ou `INTÉGRATION:` malformée ou contradictoire, recouvrement entre lots, manifeste de dépendances dans un lot ; ligne `PLAN-LOT:` proche, sans `LOT:` correspondant, doublée, ou lot sans `PLAN-LOT:` au maître consolidé.
- remède: déporter mesures, couverture détaillée et tables dans `docs/tasks/<T>-annexe.md` ; corriger la ligne nommée ; rejouer `plan_lots.py check`.
- sortie tracée: aucune.

## garde de kickoff

- où: Edit/Write, que `.agents/bin/kickoff_guard.py` juge ; désarmée par défaut ; marqueur d'armement : `.agents/state/gates/KICKOFF_REQUIRED` (un id de tâche par ligne), édité à la main par le pilote seul.
- refus: « and none of them satisfies the three »
- refus: « conditions (running + kind=plan snapshot in SPECS + path in the declared »
- source: `.agents/bin/kickoff_guard.py`
- cause: le chemin visé est couvert par une tâche armée qui n'est pas `running`, n'a pas d'instantané `kind=plan` dans SPECS, ou ne déclare pas ce chemin dans son write-set.
- remède: passer par le pipeline de la tâche (plan tracé, `start`, write-set déclaré) ; un chemin hors du write-set : rapporter au pilote.
- sortie tracée: aucune pour un agent ; désarmer est un geste du pilote, qui retire l'id du fichier à la main.

## limite de tâche

- où: `tasks.py start` et `tasks.py fournee` (le parent ou un lot existant ; `--dry-run` compris ; dossier `gates` illisible = armé) d'une tâche au-delà de son échéance ou de sa limite de jetons, et `tasks.py conso` qui laisse le cumul au-delà de la limite (franchissement ou cumul déjà au-delà) d'une tâche `pending` ou `running` ; marqueur d'armement : `.agents/state/gates/LIMITE_ARRET`, posé par le pilote, jamais semé — absent, la ligne `LIMITE-DEPASSEE:` sur stderr seule, rc inchangé.
- refus: « dépasse sa limite et LIMITE_ARRET est armé »
- refus: « jugement des limites illisible et LIMITE_ARRET est armé »
- source: `.agents/bin/tasks_requetes.py` — `limite_jugement`, constante `LIMITE_REFUS`
- cause: la tâche (ou un lot de la fournée) n'est pas `done` et l'instant présent dépasse son `echeance`, ou ses `jetons` déclarés par `tasks.py conso` dépassent sa `limite_jetons`. `start` et `fournee` sont refusés (rc 2) avant toute écriture ; `conso` écrit le cumul puis passe la tâche `blocked`, la note gardant l'étape d'avant. Un jugement qui lève (board illisible) refuse aussi `start` et `fournee` sous l'arrêt ; désarmé, il le dit par une ligne `LIMITE-ILLISIBLE:`.
- remède: rapporter au pilote, qui tranche : relever (`tasks.py limite <T> --jetons <N>[k|M]` ou `--delai <N>(m|h|j)`), retirer (`tasks.py limite <T> --retirer`) ou arrêter la tâche ; `tasks.py depassements` liste tout ce qui dépasse.
- sortie tracée: aucune — relever ou retirer la limite est un geste du pilote.
