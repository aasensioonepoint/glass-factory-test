# Contrat CLI de `tasks.py` — le moteur du board

Source machine : `.agents/ref/TASKS_CLI_CONTRACT.json`. Banc qui le tient : `.agents/evals/test_tasks_cli_contract.py`. Tâche d'origine : T-01M4V7R7CCHA59Q8VZ0GFKX4R2.

## 1. Portée

- **C'est le contrat du MOTEUR** : ce que `.agents/bin/tasks.py` accepte (verbes, positionnels, options, défauts) et ce qu'il rend (codes de sortie, flux, sorties stables).
- **Ce n'est PAS le verrou public.** Le verrou est `contract.lock.json` ; `cadre tasks` y reste au statut `reserve`, sans verbe, et `docs/contrat/CONTRAT-v0.md` § 3.1 dit la même chose. La bascule au verrou est la tâche T-00000797 (BK-159), qui consommera ce JSON ; la délégation `cadre tasks` est T-00000962 (BK-157).
- **`promis` ne vaut pas `public`.** `promis` dit que la forme est tenue par le banc et ne change qu'avec le JSON, dans le même commit. Ce n'est pas une promesse SemVer à l'adoptant : la bascule du verrou de contrat, suivie dans le kit par T-00000797, n'a pas eu lieu à cette version.
- **`noyau`** : appelable et décrit ici, sans garantie au-delà du moteur.
- **Le partage** suit la décision S-01M4JPBTF82G4PW7DDDYRSVZC1 (« B + reopen ») : les 22 verbes `public` de la mesure BK-156 (option B), plus `reopen`, font 23 `promis` ; `deps-ready`, que la décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T fait lire par les lanceurs, en fait 24 (T-01M4Z5VJ1DYQZM67AYHTACKFTA) ; `responsable` (le responsable HUMAIN d'une tâche, `owner` restant l'agent) en fait 25 (T-01M54GEHJBGA5996W0T48JXNQ4, E-48 D2) ; `limite`, `conso` et `depassements` (délai et limite de jetons par tâche, décision pilote S-01M54GFZ2VCYVA8RSJYBV6539H) en font 28 (T-01M54GEMCH3JWA95G61N2J70KS, E-48 C4) ; `chrono` (estimer chaque étape avant son départ, relever son temps réel) en fait 29 (T-01M5HST80E30DFMV3S7WM68Q7N, plan approuvé S-01M5JKBMKPNNMENNYTSAMGYQ0X). `epic`, `epic-new`, `epic-list`, `reassign`, `delete`, `fournee`, `livraison`, `focus`, `review-scope`, `jira-import` et `jira-claim` sont `noyau` (11 ; les deux verbes Jira relèvent de l'arbitrage de T-01M5DBTVRD2YSC59E7M4Q62MME, approuvé à la porte).
- **`fournee`** est `noyau`, candidat public. Le critère B (invoqué par une surface hors test qui voyage) est rempli (§ 6). Son admission au verrou se tranche avec T-00000797 (BK-159), au LOT-7.
- **Propriété et revendication Git** : `start` et la vraie `fournee` lisent le board local, puis rafraîchissent au plus six remotes sous un budget Git total de 30 s. La prise inscrit durablement `start_actor` comme pilote. Un transfert publié et vérifié vers autrui, ou une propriété locale étrangère sans reprise, rend rc 2 avec `REVENDICATION` sur stderr avant écriture. `--reprise "<raison>"` demande au pilote une raison non blanche, stdin et stderr TTY, puis la saisie exacte de l'identifiant de la tâche ; le transfert est revalidé sous verrou après les gardes et concerne le parent et les lots admissibles, jamais un lot `blocked`. Sur Windows, le remède TTY indique `winpty bash .agents/pyrun.sh .agents/bin/tasks.py …` ou Windows Terminal. Sous Claude Code et dans les hooks du kit qui posent `AGENTS_HOOK_HOST` (Codex, Kimi, Copilot) — Kimi : supposé, non mesuré —, le marqueur d'agent refuse. Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent (mesuré, 1.0.96) : ce marqueur refuse la reprise — faux positif : `COPILOT_CLI` est hérité par un shell que le pilote lance depuis Copilot CLI (échappement `!` compris), d'où il reprend alors depuis un terminal ouvert hors de Copilot CLI. Ailleurs (Codex, Gemini et Kimi sans marqueur), TTY et saisie sont une friction franchissable en une commande par un agent ; la doctrine interdit à tout agent de reprendre une tâche. `--sans-revendication` est refusé avec le remède `--reprise`, jamais une levée. Une preuve Git incomplète est annoncée comme avis et ne transfère pas la propriété ; publier la branche reste un geste manuel. Le squash ou rebase merge ne prouve pas l'ascendance du commit de prise.
- **Levée durable et avis** : `reprise_levee` est une liste d'entrées `{auteur, transition[, pointe, pointes]}` du board : ancien pilote, commit de sa prise, et pointes distantes lues au moment de la reprise si disponibles — `pointes` les garde toutes (au plus 16 ; au-delà, une ref divergente non gardée peut dire « a poussé »), `pointe` la plus avancée, seule lue dans les records d'avant `pointes`. Le `start/fournee --reprise` manuel l'écrit avec `start_actor` sous verrou ; chaque nouvelle reprise remplace la liste ou retire le champ si aucune prise n'est levée. Un changement de cycle ne l'efface pas, car une nouvelle prise porte une autre transition et reste refusée. La même prise levée devient un avis : `REVENDICATION: ancien pilote a poussé après reprise` seulement si sa pointe distante n'est contenue, par filiation, dans aucune des pointes enregistrées (miroir périmé ou ref divergente de la même prise compris ; une pointe enregistrée absente du clone : le commit de transfert la remplace ; sans pointe enregistrée : prise déjà fusionnée dans HEAD, ou pointe hors du commit de transfert) ; sinon — pointe contenue ou filiation illisible — `REVENDICATION: prise levée par reprise encore publiée`. Une pointe enregistrée qui n'est pas un SHA hexadécimal compte comme absente. Comme `start_actor`, cette preuve repose sur le board local : une édition à la main peut lever une prise distante. Ça empêche d'oublier, pas de tricher. Borne : après un rebase de la branche de l'ancien pilote, la reprise se redemande une fois (T-01M5J1FVGE). Un précontrôle refuse plus de 32 ids avant toute lecture de HEAD ; la fournée trop grande doit être découpée.

## 2. Règle de stabilité

- **Tout changement de la surface met le JSON à jour dans le MÊME commit** : un verbe, un positionnel, une option, un défaut littéral, un `nargs`, des choix, un requis, un code de sortie, un `mutant`, une sortie stable. Sinon le banc rougit.
- **Régénérer** :
  - `python3 .agents/evals/test_tasks_cli_contract.py --squelette` imprime la surface extraite du parseur. Les champs sémantiques (`statut`, `mutant`, `rc`, `sorties`) sont recopiés du JSON courant ; un verbe neuf porte `A_REMPLIR`.
  - Relire champ par champ, puis écrire le JSON.
  - `--tableau` imprime le bloc GEN du § 5, à recopier tel quel.
- **Non contractuel** : les textes d'aide (`help`, `description`, `metavar`), le nom interne (`dest`) des options et l'ordre des options. La forme est contractuelle, la prose ne l'est pas. Une exception : une option à deux noms garde la `dest` de son ancien nom, tenue par le banc (`AliasAnglais`).

## 2 bis. Noms anglais, anciens noms acceptés

T-01M5QC86XNEJ5NEX6DGZJ0AJZ5 (décision pilote S-01M5S9S55X02Z3J0WATVQD0ZH9) : le nom ANGLAIS vient en tête, l'ancien nom français reste accepté tel quel, et les messages imprimés restent en français.
- **Un verbe** : `add_parser(<anglais>, aliases=[<ancien>])` puis `set_defaults(cmd=<ancien>)`. argparse pose sinon dans `args.cmd` le nom TAPÉ, et `main` répartit sur l'ancien. La clé du JSON reste l'ancien nom ; le champ `alias` porte l'anglais. Six verbes : `batch` (`fournee`), `return` (`retour`), `delivery` (`livraison`), `assignee` (`responsable`), `target-check` (`cible-check`), `review-purge` (`binome-purge`).
- **Une option** : `--<anglais> --<ancien>`, `dest` = celle de l'ancien nom, posée explicitement (sinon argparse la dériverait de l'anglais, et `getattr(args, "exiger", False)` se tairait). Le contrat la note sous ses deux noms.
- **Témoins** : `AliasAnglais` tient la liste FERMÉE des verbes et des options aliasés, l'ordre des noms (l'anglais en tête), la `dest` ancienne et les métavars `TITLE`, `WORKSTREAM` et `ASSIGNEE`. Il vérifie aussi qu'un verbe anglais joue comme l'ancien (même rc, mêmes flux, même drain), que `--require` rend 1 sur `failed` et que `--takeover` garde le refus `REVENDICATION`.
- **Abréviations** : argparse accepte un préfixe sans ambiguïté (`allow_abbrev`). Un préfixe qui désignait un seul nom peut désormais en désigner deux (`--ri` sur `epic-new`). Aucun appelant abrégé n'a été relevé ; le banc ne le tient pas.

## 3. Les champs

- **`statut`** : `promis` ou `noyau` (§ 1).
- **`mutant`** : le verbe draine-t-il le rejeu V3 ? C'est l'ensemble `mutating` de `main`.
  - `oui` : drain avant ET après le verbe.
  - `sauf --dry-run` : idem, sauf sous `--dry-run` (`purge`, `retour`, `fournee`).
  - `non` : aucun drain.
  - **`non` ne veut PAS dire lecture seule.** Huit verbes `non` écrivent quand même (`non_mutants_qui_ecrivent`) :
    - `render` régénère la vue `TASKS.md` ;
    - `binome-purge` supprime les traces locales de revue d'une tâche ;
    - `commit-stores` et `commit-run-exports` commitent sous le verrou `POST_TASK_DONE` ;
    - `replay-sync` rejoue l'outbox V3 par un drain EXPLICITE, hors `mutating` ;
    - `focus` et `review-scope` écrivent un fichier local du dépôt principal ; `review-scope` abouti écrit aussi le journal `task-chrono` de la racine commune (`juges` relevés, `cloture` ouverte — T-01M5PVWHM8KRNRF960PTBV4FE7), et `done` y complète `cloture`, `correction` et `porte` ;
    - `chrono` (`begin`, `step`) écrit le journal local `task-chrono/<tid>.jsonl` de la racine commune (celui du PARENT pour un lot).
  - **Quatre verbes mutants écrivent aussi ce journal** (T-01M5KKFBCXXEVYR8GJPYFEH3C8), APRÈS le verbe abouti : `start`, `fournee` et `retour` (hors `--dry-run` ; `retour` sur `RETOUR: ok` seulement) et `done`, comme le non-mutant `review-scope` ci-dessus. Ce que le chrono dit va sur STDERR (`CHRONO: avis …`, `CHRONO: non relevé (<cause>)`) ; il ne change ni le rc ni le stdout du verbe.
- **`alias`** (facultatif) : le nom anglais, accepté et affiché en tête, d'un verbe dont la clé reste l'ancien nom (§ 2 bis). Le tableau du § 5 l'écrit `` `anglais` (`ancien`) ``.
- **`rc`** : les codes que le verbe peut rendre (§ 4).
- **`sorties`** : la forme stable d'une sortie, éprouvée par le banc. Quatre contrôles possibles :
  - `derniere_ligne` : regex sur la dernière ligne non vide de stdout ;
  - `json` : stdout est un tableau JSON ;
  - `jeton` : la dernière ligne appartient à `jetons_commit` ;
  - `prefixe` : stdout ouvre par ce texte.
  Le reste de la sortie n'est pas contractuel.
- **`defaut`** : figé seulement s'il est littéral. `--root` porte un défaut SYMBOLIQUE `{env, repli}` : `CLAUDE_PROJECT_DIR`, lu à la construction du parseur, sinon `.`. Le banc extrait la surface variable retirée, puis posée.
- **`jetons_commit`** : `committed`, `nothing`, `failed`, `locked-out`, `bash-introuvable`, et tout jeton qui ouvre par `busy:`.

## 4. Codes de sortie et flux

**La sémantique R2** :

- **0** : succès ; le résultat va sur stdout.
- **1** : réponse négative d'un contrôle. Sept verbes seulement : `depassements`, `retour`, `deps-ready`, `replay-sync`, `commit-stores`, `commit-run-exports`, `cible-check`.
- **2** : faute d'usage (`usage:` sur stderr, par argparse), identifiant inconnu ou refus de garde (une ligne `tasks.py: …` sur stderr).

**Les exceptions, mesurées et tenues par le banc** :

1. **`cible-check`**
   - rc 1 (étapes sans cible) : le message va sur **stdout**, préfixé `cible-check:`.
   - rc 2 (configuration) : sur stderr, préfixé `cible-check:`, jamais `tasks.py:`.
2. **`retour`** — rc 1 = refus. Le détail ET la ligne finale `RETOUR: refus` vont sur **stdout**. Deux mesures :
   - hors dépôt git (le contrôle (a) n'est pas mesurable) ;
   - dans un dépôt git jetable (un fichier hors write-set).
3. **`replay-sync`** — rc 1 = pont refusé ou drain en échec. La ligne stderr ouvre par `TASKS:` (`TASKS: pont V3 REFUSÉ …`), pas par `tasks.py:`. Cause mesurée : la partition d'état est occupée par un fichier.
4. **`commit-stores` et `commit-run-exports`** — le jeton va sur stdout.
   - rc 1 seulement sous `--exiger`, sur un jeton autre que `committed` ou `nothing`.
   - Sans `--exiger` : rc 0, quel que soit le jeton.
   - Script `post-task-done-index.sh` absent : jeton `failed` (rc 1 sous `--exiger`).
   - Script présent hors dépôt git : jeton `nothing` (rc 0).
5. **Des lignes `tasks.py:` sur stderr à rc 0.**
   - `list --json` filtré à vide : `tasks.py: no task matching …` (mesuré).
   - `list --epic` sur une épopée sans tâche : même forme (lu dans `main`, non mesuré ici).
   - Une ligne `tasks.py:` ne veut donc pas dire refus : seul le rc le dit.
6. **Une trace Python non rattrapée sort aussi en rc 1.** À rc 1, le code seul ne distingue pas une réponse d'un plantage : lire stdout et stderr.
7. **`--statusline` avale le verbe.** `tasks.py --statusline <verbe> …` imprime la statusline et rend 0. Le verbe n'est ni exécuté ni drainé : seul argparse l'a validé.
8. **Le bruit `event_store:` peut précéder la ligne `tasks.py:`.** Ce sont les journaux d'attente du rejeu V3, sur stderr. Un appelant cherche la ligne ; il ne lit jamais la seule première ligne.
9. **`tasks.py` sans verbe** imprime l'aide sur stdout et rend 0.
10. **`deps-ready`** (décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T) — la réponse va sur **stdout** à rc 0 comme à rc 1. Sa 1re ligne est `deps-ready: <JETON>`, et le **registre** des jetons est FERMÉ, dans l'ordre de précédence (le premier qui s'applique est rendu) :
    - `CYCLE` (rc 1) : un cycle atteignable, chemin complet et coupe proposée ;
    - `AMONT_OUVERT` (rc 1) : les amonts non clos, fermeture transitive, amont d'abord ;
    - `INEXPLOITABLE` (rc 1) : un amont est clos mais la replanification ne se juge pas (`plan_cible.py` absent ou qui ne se charge pas, SPECS illisible, trace sans date lisible) — fail-closed ;
    - `PLAN_A_REPLANIFIER` (rc 1) : un amont a été clos à ou après la trace `plan approuvé` élue ;
    - `REPRISE_DITE` (rc 0) : la même condition, sur une tâche lancée sous cette trace (`lancee_sous`) dont chaque amont en cause était clos au plus tard à ce lancement (`lancee_le`) — « lancée sous S-… : reprise DITE », jamais une révision ; un amont clos APRÈS le lancement reste `PLAN_A_REPLANIFIER` ;
    - `AMONT_CLOS` (rc 0) : rien de ce qui précède ; les avis (même jour, trace non élue) suivent.
    Un id inconnu rend 2 (`tasks.py: unknown task id`). Source : `DEPS_READY_JETONS` (`tasks_graphe.py`), recopiée dans `definitions` du JSON ; le banc (W9) les confronte.
11. **`chrono`** (T-01M5HST80E30DFMV3S7WM68Q7N) — rc **0 ou 2, jamais 1**. Les quatre actions (`estimate`, `begin`, `step`, `show`) valident `tid`, et `--lot` s'il est donné, en LECTURE au board de la racine COMMUNE (`agent_chrono.racine_commune`) : un id inconnu y rend 2 (`tasks.py: unknown task id`), même depuis un worktree lié dont la branche précède le lot. Une option hors de son action, une étape hors liste fermée (`task_chrono.ETAPES` : `cadrage`, `planification`, `attente-pilote`, `dev`, `juges`, `fusion`, `integration`, `cloture`, `correction`, `porte`, `done`, l'ordre d'AGENTS.md) ou une fin sans début dans le cycle COURANT rendent 2 (`tasks.py: …`) ; une ligne de journal hors schéma est ignorée, jamais une trace. Le cycle se clôt à la fin du jalon `done`, après correction et porte ; `tasks.py done` le pose lui-même, et un `step --etape done --phase begin` joué ensuite, cycle déjà clos, est ignoré (aucun cycle fantôme). La lecture d'un cycle clos borne une étape restée sans fin à la fin de ce jalon. Un lot de fournée donné comme `tid`, sans `--lot`, joue au journal de son PARENT (`estimate` et `step` sous la clé `--lot <lot>`, `begin` et `show` sur le cycle du parent). Un appelant n'en fait jamais un blocage : le chrono observe, il ne garde rien. Témoins : `.agents/bin/test_task_chrono.py`, `.agents/bin/test_tasks_chrono.py`.
12. **`depassements`** (T-01M54GEMCH3JWA95G61N2J70KS) — la réponse va sur **stdout** à rc 0 comme à rc 1 : rc 1 dès une tâche non `done` au-delà de son échéance ou de sa limite de jetons, ou une valeur de limite illisible ; une ligne `LIMITE-DEPASSEE:` ou `LIMITE-ILLISIBLE:` par entrée, puis une ligne `LIMITE:`. `--json` : la forme de `definitions["depassements"]`, `[]` à rc 0.
13. **`LIMITE-DEPASSEE:` sur stderr, rc inchangé**, avant `start`, `fournee` et `stage`, et après `conso`, pour la tâche visée (et les lots existants d'une fournée). Sous `.agents/state/gates/LIMITE_ARRET`, `start` et `fournee` (`--dry-run` compris) d'une tâche dépassée rendent **2** (`tasks.py: … dépasse sa limite et LIMITE_ARRET est armé …`) AVANT tout drain — un jugement illisible sous l'arrêt les refuse aussi ; `conso` qui laisse le cumul au-delà de la limite (franchissement ou cumul déjà au-delà) d'une tâche `pending` ou `running` rend 0 et la passe `blocked` (blocage en échec : rc 2, conso écrite, dite). `list --session` porte alors en tête UNE ligne `LIMITE-DEPASSEE: <n> tâche(s) au-delà de leur limite[, <m> valeur(s) illisible(s)] (arrêt armé | alerte seule)`, puis 3 lignes au plus au total, la coupe dite.
14. **`conso` compte un nombre DÉCLARÉ, jamais une consommation.** L'orchestrateur recopie le `subagent_tokens` (`totalTokens`) que l'hôte rend pour chaque sous-agent terminé — la taille de son DERNIER appel (contexte final et sortie), mesuré 1× à 194× sous les jetons réellement traités, médiane 39× (107 exécutions de sous-agents, session 383a61a7), sur Claude Code seul. La limite borne cette somme déclarée, jamais une dépense. Un sous-agent REPRIS rend à chaque tour la taille de son dernier appel, qui porte déjà le contexte des tours précédents : déclarer la DIFFÉRENCE entre deux relevés, jamais le relevé brut.

## 5. Le tableau — GÉNÉRÉ depuis le JSON

Bloc rendu par `--tableau` ; le banc (W3) refuse tout écart et imprime le bloc attendu.

<!-- TASKS_CLI:GEN:verbes:debut -->
| verbe | statut | mutant | rc | positionnels | options (★ requise) | sortie stable |
|---|---|---|---|---|---|---|
| `new` | promis | oui | 0, 2 | `<title>` | `--owner` `--workstream --chantier` `--assignee --responsable` `--epic` `--measure --mesure` `--not-a-defect --pas-un-defaut` `--motive --motif` | `TASKS: <id> → pending` |
| `epic-new` | noyau | oui | 0, 2 | `<eid>` `<titre>` | `--wave --vague` `--priority --priorite{P0,P1,P2}` `--exclusive` `--risk --risque` `--replace --maj` | — |
| `epic` | noyau | oui | 0, 2 | `<tid>` `<eid>?` | `--remove --retirer` | — |
| `epic-list` | noyau | non | 0, 2 | — | `--json` | — |
| `start` | promis | oui | 0, 2 | `<tid>` | `--stage` `--without-chain --sans-chaine` `--without-target --sans-cible` `--without-deps --sans-dependances` `--without-claim --sans-revendication` `--takeover --reprise` | — |
| `jira-import` | noyau | sauf --dry-run | 0, 2 | — | `--project`★ `--issue` `--dry-run` | — |
| `jira-claim` | noyau | sauf --dry-run | 0, 2 | — | `--retry`★ `--dry-run` | — |
| `stage` | promis | oui | 0, 2 | `<tid>` `<stage>` | — | — |
| `block` | promis | oui | 0, 2 | `<tid>` | `--note` `--on` | — |
| `unblock` | promis | oui | 0, 2 | `<tid>` | — | — |
| `done` | promis | oui | 0, 2 | `<tid>` | `--reason --raison`★ `--without-review --sans-binome` `--without-target --sans-cible` `--without-deps --sans-dependances` | — |
| `reopen` | promis | oui | 0, 2 | `<tid>` | `--reason --raison`★ `--without-reblock --sans-rebloquer` | — |
| `review-purge` (`binome-purge`) | promis | non | 0, 2 | `<tid>` | — | — |
| `retitle` | promis | oui | 0, 2 | `<tid>` `<title>` | — | — |
| `reassign` | noyau | oui | 0, 2 | `<tid>` `<owner>` | — | — |
| `regroup` | promis | oui | 0, 2 | `<tid>` `<chantier>` | — | — |
| `assignee` (`responsable`) | promis | oui | 0, 2 | `<tid>` `<responsable>` | — | — |
| `limite` | promis | oui | 0, 2 | `<tid>` | `--delai` `--echeance` `--jetons` `--retirer` | — |
| `conso` | promis | oui | 0, 2 | `<tid>` `<quantite>` | — | — |
| `depassements` | promis | non | 0, 1, 2 | — | `--json` | `--json` : un tableau JSON sur stdout, objets `{tache, type, valeur, limite, etat, arret}` (`[]` à rc 0) |
| `writeset` | promis | oui | 0, 2 | `<tid>` `<paths>*` | `--clear` | — |
| `direct` | promis | oui | 0, 2 | `<tid>` | `--remove --retirer` | — |
| `return` (`retour`) | promis | sauf --dry-run | 0, 1, 2 | `<tids>+` | `--base`★ `--branch --branche`★ `--dry-run` `--into --vers` | dernière ligne `RETOUR: ok` ou `RETOUR: refus` |
| `delivery` (`livraison`) | noyau | oui | 0, 2 | `<tids>+` | `--branch --branche`★ `--remove --retirer` | — |
| `batch` (`fournee`) | noyau | sauf --dry-run | 0, 2 | `<tid>` | `--dry-run` `--without-chain --sans-chaine` `--without-target --sans-cible` `--without-deps --sans-dependances` `--without-claim --sans-revendication` `--takeover --reprise` | — |
| `depends` | promis | oui | 0, 2 | `<tid>` `<deps>*` | `--clear` `--add` `--remove --retirer` `--remove-pilot-order --retirer-ordre-pilote` `--motive --motif` | — |
| `depends-show` | promis | non | 0, 2 | `<tid>` | — | — |
| `deps-ready` | promis | non | 0, 1, 2 | `<tid>` | — | rc 0 et 1 : stdout ouvre par `deps-ready: ` puis un jeton fermé (`definitions`) |
| `chrono` | promis | non | 0, 2 | `<tid>` `<action>` | `--step --etape` `--phase{begin,end}` `--lot` `--attempt --tentative` `--watch` `--json` | — |
| `parallel` | promis | oui | 0, 2 | `<tids>+` | — | — |
| `focus` | noyau | non | 0, 2 | `<tid>` | — | — |
| `review-scope` | noyau | non | 0, 2 | `<tids>+` | — | — |
| `delete` | noyau | oui | 0, 2 | `<tid>` | `--force` | — |
| `purge` | promis | sauf --dry-run | 0, 2 | — | `--state{pending,blocked,done}` `--before` `--dry-run` `--cap --plafond` | — |
| `list` | promis | non | 0, 2 | — | `--json` `--task` `--state{pending,running,blocked,done}` `--workstream --chantier` `--blocked-by` `--depends-on` `--group` `--session` `--epic` `--assignee --responsable` | `--json` : un tableau JSON sur stdout (`[]` si rien ; l'absence dite sur stderr) |
| `render` | promis | non | 0, 2 | — | — | `TASKS.md regenerated from TASKS.json` |
| `replay-sync` | promis | non | 0, 1, 2 | — | — | `TASKS: replayed <N> sync intent(s)` |
| `commit-stores` | promis | non | 0, 1, 2 | — | `--lock-timeout` `--require --exiger` | un jeton de `jetons_commit`, en dernière ligne |
| `commit-run-exports` | promis | non | 0, 1, 2 | — | `--lock-timeout` `--require --exiger` | un jeton de `jetons_commit`, en dernière ligne |
| `target-check` (`cible-check`) | promis | non | 0, 1, 2 | `<plan>` | `--spec` | rc 0 et 1 : stdout ouvre par `cible-check: ` |

40 verbes au contrat : 29 `promis`, 11 `noyau`. Options globales : `--root`, `--statusline`. Rejeu V3 (`mutant`) : 21 `oui`, 5 `sauf --dry-run`, 14 `non` — dont 8 qui écrivent quand même : `render`, `binome-purge`, `commit-stores`, `commit-run-exports`, `replay-sync`, `focus`, `review-scope`, `chrono`. rc 1 possible : 7 verbes (`depassements`, `retour`, `deps-ready`, `replay-sync`, `commit-stores`, `commit-run-exports`, `cible-check`).
<!-- TASKS_CLI:GEN:verbes:fin -->

## 6. Cardinaux mesurés — un relevé daté, que le banc ne tient PAS

Relevé du 2026-10-14 sur develop (`a94b3ad9`), après la fusion de la fournée. Ces nombres bougent avec la prose ; ils ne sont pas rejoués par le banc.

- **Méthode.**
  - Fichiers : `git ls-files`, lus en UTF-8 ; les 5 fichiers qui ne se décodent pas sont écartés.
  - Exclus : `.agents/state/`, `runs/`, `retro/`, `plan/`, `docs/interne/`, `docs/tasks/`.
  - Regex STRICTE (Python `re`), comptée par occurrence : `tasks\.py(\s+--root\s+\S+|\s+--statusline)*\s+<verbe>(?![\w-])`.
    - La fin `(?![\w-])` est nécessaire : avec `\b`, `depends` compterait aussi `depends-show` et `epic` compterait `epic-new` et `epic-list` (total 1 433, pas 1 379).
    - `\s` franchit une fin de ligne : une invocation coupée sur deux lignes compte.
- **Total** : 1 379 invocations dans 188 fichiers ; hors `.md`, 841 dans 122.
- **Par verbe (invocations / fichiers)** : `list` 235/58 · `start` 180/64 · `done` 176/48 · `direct` 132/28 · `new` 119/53 · `fournee` 78/25 · `depends` 75/39 · `writeset` 50/31 · `depends-show` 47/30 · `parallel` 41/21 · `commit-run-exports` 34/14 · `retour` 32/17 · `block` 31/16 · `delete` 26/11 · `render` 24/16 · `replay-sync` 18/10 · `commit-stores` 15/7 · `binome-purge` 11/10 · `purge` 11/8 · `unblock` 9/7 · `epic` 7/3 · `reopen` 7/3 · `epic-new` 5/4 · `stage` 5/4 · `retitle` 5/4 · `epic-list` 2/2 · `regroup` 2/2 · `reassign` 1/1 · `cible-check` 1/1.
- **Le « 116 » du titre d'origine est un compte de FICHIERS, pas d'invocations.** Le planner l'a reproduit à 117 fichiers hors `.md` le 2026-10-13, avant la fusion de la fournée, avec sa propre regex. Avec la regex ci-dessus, on en compte 122 aujourd'hui.
- **`fournee`** : 78 invocations dans 25 fichiers (regex stricte). En regex LARGE (`tasks\.py[^\n]*?\bfournee\b` : `tasks.py` puis le mot sur la même ligne, comptée par occurrence) : 93 dans 25.
  - Ce ne sont PAS les mêmes 25 fichiers. La large prend `.claude/hooks/context-retro.sh` et perd `test_plan_cible_fournee.py`, où une fin de ligne sépare `tasks.py` de `fournee`.
  - Les retraits ci-dessous partent des 25 fichiers de la regex STRICTE.
  - Implémentation, retirée du compte : `tasks.py`, `tasks_fournee.py`, `plan_lots.py`.
  - Tests, retirés du compte : `test_tasks_fournee.py`, `test_fournee_doctrine.py`, `test_plan_cible_fournee.py`, `context-retro.test.sh`.
  - Restent **18 surfaces hors test**, toutes prises par la synchronisation du template (prédicat TAKE de `sync_template.py`, mesuré) :
    - `plan_cible.py` ;
    - les skills `kickoff`, `planning`, `planning-all`, `task-board` ;
    - les cinq défs `orchestrator` (`.claude`, `.codex`, `.gemini`, `.github`, `.kimi-code`) ;
    - les commandes `kickoff`, `planning`, `planning-all` ;
    - `copilot-instructions.md`, `AGENTS.md`, `CHANGELOG.md`, `README-OTHER-HOSTS.md` ;
    - `src/cadre/data/roster/orchestrator.json` (chemin au relevé ; quand le paquet `cadre` vit sous `.agents/vendor/cadre/`, le même roster y est, `.agents/vendor/cadre/data/roster/orchestrator.json`, pris par le même TAKE).
  - Le critère B est donc rempli ; le verbe est classé `noyau` à cette version ; son passage en public est suivi dans le kit par T-00000797.
- **La mesure BK-156** comptait 28 verbes, avant `fournee` ; le parseur en porte 30 depuis `livraison`, 31 depuis `deps-ready` (ni l'un ni l'autre comptés dans le relevé ci-dessus, antérieur aux deux verbes).
- **Bornes du relevé.**
  - La regex est textuelle : elle compte aussi la prose des commentaires et docstrings des fichiers non `.md`.
  - Elle ne voit ni les appels en processus `tasks.main(` (30 dans 14 fichiers au relevé du planner), ni les argv assemblés à l'exécution.
  - Elle ne voit pas un verbe cité sans le préfixe `tasks.py`.

## 7. Ce que le banc tient, et ce qu'il ne tient pas

**Il tient**, avec 30 mutants en mémoire qui doivent chacun rendre leur comparateur rouge :

- **W1** : les verbes du parseur sont les verbes du contrat, dans les deux sens.
- **W2** : la forme de chaque verbe et des options globales, et le défaut symbolique de `--root`.
- **W3** : le bloc du § 5 est le rendu du JSON.
- **W4** : `mutant`, observé en processus, `replay_sync` remplacé par un enregistreur ; et `--statusline` avale le verbe.
- **W5** : rc 2 sur une option inconnue, pour chaque verbe.
  - L'argv est COMPLET : positionnels et options requis fournis, puis `--zz-inconnu`. Le banc exige `unrecognized arguments: --zz-inconnu` sur stderr.
  - Pourquoi : argparse refuse d'abord un positionnel manquant. Avec le verbe seul, 24 verbes sur 31 s'arrêtent là, et l'option inconnue n'est jamais atteinte (mesuré, Python 3.14.7, après `deps-ready` ; 23 sur 30 avant, 22 sur 29 avant `livraison`).
  - Et sur un identifiant inconnu (argv complet, en sous-processus) : `unknown task id` sur stderr et une ligne `tasks.py: `.
- **W6** : chaque rc 1 du contrat rendu réellement, avec un jumeau rc 0. Plus le refus de pont injecté de `replay-sync`.
- **W7** : les verbes dont la branche de `main` peut rendre 1, lus par AST, sont l'ensemble `rc:1` du contrat.
- **W8** :
  - les sorties stables ;
  - l'aide en rc 0 sans verbe ;
  - aucun verbe sans branche dans `main` (AST) ni retombé sur l'aide (comportement) ;
  - les exceptions du § 4.
- **W9** : les jetons de `deps-ready` (`DEPS_READY_JETONS`) sont ceux de `definitions["deps-ready"]`, dans l'ordre de précédence, et chacun est au § 4.
- **C7** : les jeux en processus voient l'environnement du banc et rien de l'hôte (liste blanche, `HOME` jetable, `os.environ` remplacé). Un `HOME` et une variable plantés côté hôte n'atteignent pas `main`.

**Il ne tient pas** :

- **Les appelants.** Plus de 80 mots de prose suivent `tasks.py` dans le dépôt. Les confronter à ce contrat est la suite S1.
- **Le rc 0 de chaque verbe.** Il n'est asserté que pour `new`, `list --json`, `render`, `replay-sync`, `commit-stores`, `commit-run-exports`, `retour`, `cible-check`, `deps-ready`, `depassements` et `tasks.py` sans verbe. Les refus et l'alerte de `LIMITE_ARRET` (§ 4, point 12) sont tenus par `.agents/bin/test_tasks_limites.py`, hors de ce banc.
- **Chaque jeton de `deps-ready` rendu.** Le banc ne rend qu'`AMONT_OUVERT` et `AMONT_CLOS` ; les quatre autres sont tenus par `.agents/bin/test_tasks_amont.py`, hors de ce banc.
- **Les refus de garde à rc 2** (`MESURE_REQUIRED`, `BINOME_REQUIRED`…). Ce banc ne les rejoue pas.
- **Toutes les causes d'un rc 1.** Une seule cause est mesurée par chemin rc 1 : pour `replay-sync`, la partition d'état occupée par un fichier ; pour `retour`, un fichier hors write-set et l'absence de dépôt git.
- **Une répartition sortie de `main`.** W7 ne lit que `main` dans `tasks.py` : un refactor qui en sortirait la répartition rougit W7, à dessein.
- **Un rc 1 que l'AST ne reconnaît pas.** W7 ne voit que trois formes :
  - `return 1` ;
  - `return <nom>` ;
  - une affectation `rc_verbe = …` qui contient le littéral `1`.

  Échappent, mesuré : `return int("1")`, `return 0 + 1`, `return f()`, `return self.rc`, `return True`, `sys.exit(1)`, `raise SystemExit(1)`, et `rc = 1` sous un autre nom que `rc_verbe`. À l'inverse, tout `return <nom>` compte, même un nom qui ne vaut jamais 1.
- **Une autre variable d'environnement que `CLAUDE_PROJECT_DIR`.** Un défaut lu dans une autre variable passerait pour littéral.
- **Windows.** Mesuré sous macOS seulement.

## 8. Arête et suites

- **Arête** : `T-01M4V7R7CCHA59Q8VZ0GFKX4R2 <- T-01M4V1JD628K07PXF7FFDSN0Q3`. Le motif, recopié du plan : « le contrat doit inclure le verbe `fournee`, que la fournée ajoute au parseur (tasks_cli.py) et à la répartition (tasks.py) ; le banc lit le parseur après la fusion, sans l'éditer ».
- **Suites proposées** :
  - **S1** : contrôle côté appelants.
  - **S2** : même contrat pour `ledger.py` et `specs.py`.
  - **S3** : T-00000797 consomme ce JSON.
  - L'arête `T-00000962 <- T-01M4V7R7CCHA59Q8VZ0GFKX4R2`.
  - **S4** : un pointeur depuis la skill `task-board`.
