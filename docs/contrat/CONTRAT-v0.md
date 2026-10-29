# Contrat public du kit Cadre — v0

Ce document dit **ce que le kit promet** à un projet adoptant, et rien d'autre.
Tout le reste est du noyau : privé, packagé, sans garantie interne, libre de
changer sans préavis.

- **Forme machine** : `contract.lock.json`, à la racine.
- **Checks** : `contract_diff` et `check_changelog_contract`,
  `.agents/evals/test_contract_diff.py` ; témoins de l'index et des trois noms
  adoptants : `.agents/evals/test_contract_index.py`.
- **Version du contrat** : `0.6.0`.

---

## 1. Le principe qui gouverne ce document : la parcimonie

**Ce qui n'a pas besoin d'être public reste noyau.** Une promotion se justifie
par écrit, ou elle n'a pas lieu. Le check refuse une entrée dont la note fait
moins de vingt caractères, pour que « promu sans raison » soit un test rouge
plutôt qu'une habitude.

La raison est asymétrique. Ne pas promettre coûte une gêne à un adoptant qui
voulait s'appuyer sur quelque chose, et cette gêne se répare en promouvant plus
tard. Promettre de trop coûte une rupture à la version 1.0, ou un contrat qu'on
ne peut plus tenir. Les deux erreurs ne se rattrapent pas au même prix.

**Le contrat a démarré déclaratif, il ne l'est plus qu'en partie.** Avant la
Phase 1, aucune interface en ligne de commande n'existait : `contract_diff` ne
confrontait le verrou qu'à lui-même — unicité, cohérence, justification — et
aux fichiers du dépôt — événements déclarés par les hôtes, workflows, chemins
promis. Depuis la Phase 1, il introspecte aussi ce qui tourne : la ligne de
commande réelle et les variables `CADRE_` que le noyau lit, dans les deux sens.

## 2. Politique de version

| Règle | Valeur |
|---|---|
| Première release | `0.1.0` |
| Passage en `1.0` | Décision explicite du pilote, jamais par accumulation |
| En `0.x` | Une suppression ou un changement d'entrée exige une entrée au CHANGELOG, rubrique **Contrat**, et au moins une montée de mineure de `version_contrat` ; un correctif (`0.y.Z`) n'ajoute, ne change ni ne retire aucune entrée |
| À partir de `1.0` | Une suppression exige un bump majeur |

Trois statuts. **`public`** est promis. **`reserve`** signifie que le nom est
pris et ne servira pas à autre chose, sans que l'implémentation existe.
**`deprecie`** est encore là, part au prochain majeur, et sa note doit nommer sa
date et son remplaçant — un déprécié sans remplaçant est une impasse.

## 3. Ce qui est promis

### 3.1 La ligne de commande — en partie publique, le reste réservé

**Sont implémentées, donc publiques** : `cadre --version`, `cadre paths` et
`cadre config explain` depuis la Phase 1, `cadre lessons promote` depuis la
Phase 2, `cadre hook` depuis la Phase 3. Un nom qui fait quelque chose et
resterait `reserve` ferait mentir le verrou dans l'autre sens : la promotion se
fait dans le commit qui l'implémente.

Restent **réservés** : `cadre` lui-même et ses sous-commandes `cadre init`,
`cadre init --upgrade`, `cadre hosts`, `cadre doctor`,
`cadre dashboard`, `cadre uninstall`, `cadre disarm`, les trois points d'entrée
adoptants `cadre tasks`, `cadre ledger`, `cadre specs` (réservés en Phase 3,
apportés en Phase 4), plus deux espaces de noms, `cadre lessons` — dont seule
la sous-commande `cadre lessons promote` est livrée — et `cadre remote`, qui
n'existera pas avant longtemps.

**Pourquoi réserver un nom avant de l'implémenter.** Parce que le coût est nul
aujourd'hui et prohibitif plus tard. `lessons` a été réservé avant que sa
première feuille, `cadre lessons promote`, soit livrée, et il était libre ce
jour-là ; `remote` l'est pour la même raison. S'il avait servi entre-temps à
autre chose, il aurait fallu soit le renommer, soit choisir un mot moins juste.

`cadre disarm` mérite son mot. Le pilote a décidé le 2026-09-12 que tout arrive
armé et que le désarmement est un geste explicite et tracé. Cette commande est
la contrepartie de cette doctrine : sans elle, « tout armé » n'aurait pas de
sortie honnête.

### 3.2 Les événements de hook — dix, déclarés

**Ce qui est relevé, c'est la déclaration, pas le déclenchement.** La première
rédaction disait « mesuré sur les six hôtes », ce qui promettait plus que la
mesure : le dépôt fixe lui-même la couverture réelle du déclenchement à trois
hôtes mesurés, aucun hérité, un supposé et deux inertes-mesurés. Ce qui est vérifié
ici, c'est que l'événement figure dans le registre que le kit dédie à chaque
hôte — pour Gemini CLI, `.agents/hooks.json`, que l'hôte ne charge pas (G0,
mesuré le 2026-10-12) —, et un test le contrôle hôte par hôte.

Six sont universels, déclarés par les six hôtes : `hook:SessionStart`,
`hook:PreToolUse`, `hook:PostToolUse`, `hook:Stop`, `hook:SubagentStop`,
`hook:PreCompact`. `hook:PreToolUse` est le seul que les cinq registres
déclarent bloquant ; il ne bloque rien sur Gemini CLI ni sur Antigravity,
inertes-mesurés.

Quatre n'existent que sur Claude Code : `hook:SessionEnd`, `hook:PostCompact`,
`hook:SubagentStart`, `hook:Notification`. Ils sont **quand même publics**, et
c'est délibéré : un hôte qui ne les expose pas est `assiste` pour les gates qui
s'y ancrent, ce qui est une information utile, alors que les taire rendrait le
niveau d'un hôte inexplicable.

Deux tests tiennent cette promesse **dans les deux sens**. Un événement dit
universel doit être déclaré par **chaque** hôte, pas par au moins un — la
première rédaction se contentait de l'union, donc `Stop` pouvait disparaître de
Codex sans que rien ne rougisse. Et un événement dit propre à Claude Code ne doit
être déclaré **nulle part ailleurs**, sinon un hôte serait classé assisté à tort.
Copilot épelle `Stop` en `agentStop` : la correspondance est une table nommée,
après qu'un premier essai l'ait bricolée dans la boucle sous la forme d'un
remplacement qui ne remplaçait rien.

### 3.3 Le contrat de hook — trois promesses

`contrat-hook:payload-stdin-json`, le payload arrive en JSON sur l'entrée
standard.

`contrat-hook:verdict-stdout-json` **ne vaut que pour les hôtes à enveloppe** —
Codex, Gemini et Antigravity, Copilot. La première rédaction promettait ce
verdict JSON partout, et la revue croisée du 2026-09-12 l'a **mesuré faux sur
l'hôte de référence** : les refus de Claude Code sortent en texte sur la sortie
d'erreur avec un code 2, et n'écrivent pas un octet sur la sortie standard. Un
adoptant qui aurait suivi la promesse aurait émis un JSON que ce refus n'utilise
pas, et son édition serait passée en silence.

`contrat-hook:refus-par-hote` **fait foi** sur la forme du refus. Claude Code :
sortie d'erreur et code 2, le seul canal mesuré de bout en bout. Codex, Gemini
et Antigravity, Copilot : `permissionDecision: deny` et code 0. **Kimi n'est pas
mesuré** : la garde de mandat d'écriture ne le connaît pas comme hôte à
enveloppe, alors que l'implémentation partagée lui rend un code 0. Un marqueur
absent déclenche les deux canaux.

**`cadre hook` applique ces trois promesses.** Il lit le payload sur l'entrée
standard — un objet JSON en UTF-8 strict, un BOM étant refusé — et rend tout
refus, celui d'une garde comme le sien (payload illisible ou qui n'est pas un
objet, événement hors du verrou, événement que le registre de l'hôte ne déclare
pas), par le canal de l'hôte : sortie d'erreur et code 2 pour Claude Code ;
l'enveloppe `permissionDecision: deny` sur la sortie standard et code 0 pour
Codex, Gemini et Antigravity, Copilot et Kimi. Kimi reçoit l'enveloppe par
décision du pilote ; que l'hôte l'honore n'est pas mesuré. Le refus est honoré
sur `hook:PreToolUse` là où l'hôte charge et lit ses hooks — Claude Code et
Codex, mesurés ; Copilot en dossier approuvé seulement ; Gemini CLI et
Antigravity INERTES-MESURÉS (`.agents/skills/guardrails/SKILL.md` § Statut des
gardes par hôte) ; Kimi non mesuré ; sur les autres événements, la forme est
rendue et son effet n'est pas mesuré. **Aucune garde n'est encore branchée sur `cadre hook`** :
tant qu'aucune ne l'est, un payload valide sur un événement déclaré est laissé
passer. Cet état est transitoire, le verrou ne le promet pas.

### 3.4 Les variables d'environnement

`AGENTS_HOOK_HOST` est publique parce qu'elle **l'est déjà de fait** : c'est elle
qui sélectionne la branche de refus par hôte, et elle est citée dans les
déclarations natives des hôtes (cinq fichiers : Antigravity partage celui de
Gemini). La première rédaction avançait « 210 usages mesurés », un nombre que la
revue croisée n'a pu reproduire par aucune méthode nommée. Un chiffre qu'on ne
peut pas rejouer ne vaut rien, donc il est retiré plutôt que corrigé au hasard :
le relevé se refait par `git grep -o AGENTS_HOOK_HOST | wc -l`. `CADRE_CONFIG_HOME` et
`CADRE_STATE_DIR` sont publiques : le noyau les lit depuis la Phase 1 pour placer
la configuration de l'utilisateur et l'état machine, hors du dépôt.
`CADRE_PROJECT_ROOT` l'est aussi : elle force la racine de projet, devant la
racine git. `NVD_API_KEY`, `NVD_DATA_DIR` et `NVD_OFFLINE` sont publiques parce
que la documentation d'installation de la porte sécurité les nomme déjà à un
adoptant.

Désormais, les créateurs du paquet `agentic_v3` (store V3, journal
d'attente, verrou et identifiant d'export) refusent la NAISSANCE d'une partition
d'état quand la racine du projet est sous une zone temporaire (`gettempdir()`,
`$TMPDIR`/`$TEMP`/`$TMP`, `/tmp`, `/var/tmp`, `/var/folders`) et que
`CADRE_STATE_DIR` est absent ou blanc : le miroir V3 n'est pas créé, le refus est
annoncé, le board reste écrit et ses événements attendent dans son outbox ; poser
`CADRE_STATE_DIR` vers un dossier jetable garde le miroir. Bornes : une partition
qui EXISTE est adoptée, jamais refusée ; `migrate_index_to_db.py` et `cadre init`
ne passent pas par ce refus — une partition qu'ils font naître est ensuite adoptée
par le miroir V3 ; une zone qui contient le domicile (`$HOME` sous `/tmp`) n'est
pas retenue ; `XDG_STATE_HOME` n'est pas une isolation (le refus vaut aussi sous
`$XDG_STATE_HOME/cadre/projets`) ; tout `CADRE_STATE_DIR` non blanc vaut isolation,
même s'il désigne l'état réel ; liste de zones finie ; comparaison sensible à la
casse (une racine tapée dans une autre casse sur un système insensible n'est pas
refusée) ; mesuré sous macOS seul, Linux et Windows non mesurés.

**Le noyau sous un préfixe système : mode optionnel pour les postes gérés.** Un
administrateur peut installer le noyau une fois pour tous les utilisateurs d'un
poste, sous un préfixe système qu'ils ne peuvent pas écrire — par exemple en
dirigeant les variables de uv `UV_TOOL_DIR` (le venv de l'outil) et
`UV_TOOL_BIN_DIR` (la commande `cadre`) vers `/opt/cadre` et vers un répertoire
du `PATH`. Le venv de l'outil n'embarque pas son interpréteur : il pointe sur
celui que uv a choisi, un Python géré sous le domicile de l'administrateur dès
que uv en possède un ou en télécharge un (préférence `managed` par défaut).
Installer avec `--python <interpréteur ≥ 3.11 lisible par
tous, hors de tout domicile>` et `--compile-bytecode`. La racine du paquet se
résout alors sous ce préfixe ; la configuration et l'état machine restent PAR
UTILISATEUR — `CADRE_CONFIG_HOME` et `CADRE_STATE_DIR` quand ils sont posés,
sinon un emplacement résolu depuis l'environnement de qui lance la commande
(`$HOME` compris), dont la forme exacte n'est pas promise ici —, et l'état d'équipe
reste dans le `.agents/state/` du projet. Le noyau n'écrit ni configuration ni
état sous le préfixe, qui peut donc rester en lecture seule ; un
`CADRE_STATE_DIR` dirigé dedans fait échouer l'écriture de l'état par une erreur
qui nomme le chemin refusé. Ce mode n'ajoute ni variable ni commande. Bornes :
mesuré sous macOS, sur une installation par `uv tool install` rendue non
inscriptible par `chmod` — ni élévation réelle, ni Linux, ni Windows, ni une
autre forme d'installation ne sont mesurés ; un second utilisateur réel n'est
pas mesuré ; sans `--compile-bytecode`, l'interpréteur écrit son cache sous un
préfixe qu'on lui laisse inscriptible.

Toutes les autres variables du kit restent noyau. `AGENTS_EVENTS_DIR`,
`AGENTS_PROJECT_JSON`, `AGENTS_OTEL_DIR` et les autres sont des détails
d'implémentation, et les promouvoir figerait des chemins internes.

### 3.5 L'arborescence

`.agents/` **est le nom de contrat** : aucun renommage, c'est la décision D2 du
plan. Sous elle, cinq chemins sont promis — `.agents/state/board/TASKS.json`,
`.agents/state/memory/LEDGER.json`, `.agents/state/specs/SPECS.json`,
`.agents/state/gates/`, et `.agents/kit.lock` (JSON, format 1, trois clés
`version_contrat` / `version_kit` / `version_format` ; sera écrit par `cadre init`,
réservé, voir l'index des identifiants ; la mise en œuvre de la comparaison relève de la Phase 4bis).
Depuis le contrat `0.2.0`, les trois magasins d'état ont **deux formes** sous le même nom
promis : leur monolithe, OU leur forme enregistrement — le dossier
`.agents/state/board/tasks/` (et `epics/`), le dossier `.agents/state/memory/entries/`,
le journal `.agents/state/specs/SPECS.jsonl` (append-only, protégé comme le monolithe).
Un magasin neuf naît monolithe. Les deux formes à la fois sont refusées par nom à
l'écriture (`tasks.py`, `ledger.save`, `specs`). À la lecture, le journal SPECS les refuse
toujours (`specs.store_mode`) ; le board et le ledger ne les lisent par leur module
(`tasks.load`, `ledger.load`) que si elles portent les mêmes enregistrements, sinon refus
nommé ; `plan_pool`, `plan_waves`, `check-stale-justification` et les gardes de plan
`plan_cible`, `plan_depends` refusent un board en deux formes quand ils le lisent. Un
lecteur hors de ces cas n'est pas tenu par cette phrase. Seul le module propriétaire écrit
l'une ou l'autre. Un est réservé :
`.agents/hooks/<hote>/<evenement>` pour la surcharge adoptant. Chez un adoptant
qui tire ce fichier avant `cadre init`, les valeurs qu'il porte restent celles du
kit tant que `cadre init` ne l'a pas réécrit.

Ce que la comparaison de `cadre hook` appliquera est fixé dès maintenant, sa mise en œuvre restant à la Phase 4bis : la clé est `version_contrat`, jamais la version du noyau ; un écart de majeure est refusé, bruyamment, dans les deux sens — et, tant que `version_contrat` est en `0.x`, un écart de mineure l'est aussi, puisqu'en `0.x` une rupture d'entrée est portée par une montée de mineure (§ 2) —, et un écart de correctif, ou de mineure à partir de `1.0`, avertit sans refuser ; sens (1) le projet est en retard sur le noyau du poste ⇒ `cadre init --upgrade` (réservé) ; sens (2) le noyau du poste est en retard sur le `kit.lock` d'un dépôt ⇒ monter l'installation du poste, par une commande qui n'a pas encore de nom — donc rien n'est encore réservé —, et qui entrera à l'index des identifiants avec le lot qui la livre ; aucune dégradation en silence, jamais un « mode réduit ».

**Les marqueurs de `.agents/state/gates/` n'ont pas tous la même polarité**, et
la première rédaction simplifiait à tort en écrivant « leur présence arme ». Il y
en a trois sortes, et un adoptant ne devinera aucune des deux dernières.

| Marqueur | Ce que sa présence fait |
|---|---|
| `KICKOFF_REQUIRED`, `UI_GATE.local` | **arme** une garde qui refusait jusque-là |
| `AUDIT_LOG`, `NIGHT_HEADLESS.allow` | **autorise** — ce sont des listes blanches, l'absence refuse |
| `GITLEAKS_FALLBACK.off` | **désarme** le repli, polarité inversée |

### 3.6 Les formats

`format:def-agent` est le plus important, et sa formulation a été corrigée en
Phase 0. **Un fichier par agent, dans le format natif de l'hôte** — Markdown
pour Claude Code, Gemini, Copilot et Kimi, **TOML pour Codex**. Le compte par
format se dérive du dépôt, il ne se recopie pas ici. L'adoptant dépose les siens
à côté, sans aucune déclaration. Dire « les agents sont des `.md` » aurait été
faux sur un hôte sur cinq.

`format:lecon` est **réservé et non promis**. La première rédaction le
présentait comme public alors que la forme n'existait pas. Depuis la Phase 2, le
noyau porte la portée, l'origine, le statut de partage et la forme généralisée
(`.agents/vendor/cadre/ledger/lessons.py`) et `cadre lessons promote` écrit un fichier par
leçon : la forme existe, mais elle n'est pas promise. Sa promotion passera par
le verrou et une ligne au CHANGELOG.

`format:frontmatter-cadre-managed` et `format:gate-declaratif` sont réservés eux
aussi, ils arrivent en Phase 3bis.

### 3.7 Les commandes et les workflows

`core-scripts/verify.sh` est **la porte**, et elle voyage : c'est l'adoptant qui
la lance. Ses deux drapeaux sont orthogonaux et voyagent ensemble avant un
push — `--at` ancre le verdict à un SHA, `--linux` rejoue la jambe conteneur.

**La porte refuse un fichier ignoré que pytest ou run-bash-tests chargerait** (décision
pilote) : un fichier non suivi sous un chemin git-ignoré que pytest 9.1.1 (portée :
`testpaths` et `norecursedirs` de `pytest.ini` racine) ou `run-bash-tests.sh` chargerait
rend pytest rc 4 et le runner rc 2, fichier nommé ; remède : le suivre (`git add -f`) ou le
sortir de l'arbre. **Borne (f), déclarée** (décision pilote, « limite déclarée ») : un
argument EXPLICITE vers un dossier élagué — dossier point, venv, `norecursedirs` —, à la
racine ou sous un testpath (`pytest .hid/`), n'est pas contrôlé ; un `pytest` lancé depuis
un sous-dossier non plus.

Treize workflows sont publics : `kickoff`, `audit`, `index`, `skills-sync`,
`docs-sync`, `specs-sync`, `planning`, `planning-all`, `dash`, `lang`, `night`,
`jira` et `setup`. Un test refuse un workflow promis sans définition sur disque.

Un seul d'entre eux est **Claude Code seul**, `night`, et son refus
ailleurs se cite dans une ligne exacte plutôt que reformulé.

### 3.8 Les surfaces

Ces trois surfaces sont **réservées** : le nom est pris, la garantie ne l'est
pas encore. `dashboard:hors-ligne` réserve la traçabilité complète d'un run,
consultable sans réseau, assets empaquetés — elle n'est pas tenue aujourd'hui.
`niveau-hote:enforce` et `niveau-hote:assiste` réservent les deux niveaux de
support et, pour le second, la mention « mode assisté » à l'initialisation, au
diagnostic, au tableau de bord et au registre de chaque run. Leur définition et
la règle qui classe chaque hôte sont au § 3.10 ; rien ne lit encore ce
classement, et les deux identifiants restent réservés.


### 3.9 Les surfaces que l'adoptant écrit — ajoutées après la revue croisée

**La sous-promesse est le risque le plus grave, et il a fallu deux relecteurs
pour le voir.** Une surface dont un adoptant dépend réellement mais qui n'est pas
au contrat peut être déplacée par une phase suivante sans qu'un seul test
rougisse. Sept l'étaient.

Les trois répertoires de skills — `.agents/skills/`, `.claude/skills/` et
`.github/skills/` — sont **découverts nativement** par Codex, Gemini et Copilot.
**Antigravity en est l'exception** : son répertoire de skills est
`<workspace>/.agent/skills/`, au singulier, et `.agents/skills/` n'y est **pas
supporté** — les skills l'atteignent par CHEMIN depuis `GEMINI.md`, jamais par
découverte, et l'adoptant y dépose les siennes. `.github/instructions/` est sa
surface d'instruction Copilot. `.agents/protected-paths.local` est l'extension
adoptant des chemins protégés, lue par les gardes de quatre hôtes.
`.gitleaks.toml` a une forme TOML que le scanner lui **dicte**, donc elle est
déjà un contrat de fait. `.githooks/pre-push` voyage et s'installe par
`core.hooksPath`.

### 3.10 Les niveaux d'hôte — `enforce` et `assisté`, classés par la preuve

**Un niveau se prouve, il ne se déclare pas.** Le kit reconnaît deux niveaux de
support, et un seul critère les sépare : la garde bloquante d'avant-outil,
`hook:PreToolUse`, le seul événement que les six registres déclarent bloquant
(§ 3.2).

| Niveau | Identifiant | Ce qu'il dit de l'hôte |
|---|---|---|
| **enforce** | `niveau-hote:enforce` | L'hôte peut **refuser mécaniquement** : son refus d'avant-outil est mesuré de bout en bout — l'hôte lancé a refusé un appel d'outil sur le verdict d'une garde |
| **assisté** | `niveau-hote:assiste` | L'hôte est **guidé par la doctrine sans refus mesuré** : les gardes y sont câblées, leur morsure n'est pas prouvée |

L'identifiant s'écrit sans accent, `assiste`, au verrou comme dans la table ;
« assisté » est sa graphie de prose.

**La règle de classement.** Un hôte est `enforce` si et seulement si son refus
d'avant-outil est **mesuré de bout en bout**. Tout autre statut le classe
`assisté` : une garde bloquante **supposée**, **héritée** d'un autre hôte,
**inerte-mesurée**, **non mesurée**, **absente**, ou mesurée sur le seul
**jumeau** — l'implémentation du hook éprouvée sur une charge synthétique, sans
que l'hôte ait été lancé. Un hôte dont la garde bloquante n'est que supposée est
donc `assisté`, jamais `enforce`. Un hôte ne change de niveau que par une mesure
nouvelle, tracée, dont le témoin peut rougir, inscrite dans la cellule qui la
porte — jamais par la seule édition de son niveau, sans la cellule mesurée qui
le justifie. Le « `assiste` pour les gates qui s'y ancrent » du § 3.2 est une
information par gate ; le niveau d'hôte, lui, ne se juge que sur
`hook:PreToolUse`.

La mesure sur le jumeau ne suffit pas, et la raison est déjà écrite au § 3.3 :
elle prouve que le hook rend la forme que l'hôte documente, pas que l'hôte lit
le registre, déclenche le hook et honore le refus. C'est cet écart qui a fait
annoncer un verdict JSON partout, puis mesurer qu'il n'était pas lu sur l'hôte
de référence.

**La source unique est `.agents/vendor/cadre/data/capacites_hotes.json`.** Son relevé du
2026-10-08 est PÉRIMÉ depuis l'alignement des hôtes du 2026-10-12
(l'héritage des mesures Codex par Copilot est réfuté ; Gemini CLI ne charge pas
son registre, G0). Sa mise à jour reste à faire ; d'ici là, les légendes des
surfaces font foi. Elle porte, hôte
par hôte et capacité par capacité, le statut que le dépôt a tracé — `mesure`,
`herite`, `suppose`, `inerte-mesure`, `non-mesure` ou `absent` —, sa portée
quand il est mesuré, et sa source `fichier:ligne`. Ce document fixe les deux
niveaux et la règle ; la table fixe les cellules et le niveau qui en découle, et
c'est elle, non ce texte, que le noyau lira. Aucun niveau d'hôte n'est recopié
ici : une copie vieillirait sans qu'un test rougisse. La table n'énumère que les
capacités que le dépôt a déjà relevées hôte par hôte ; une capacité qui n'y
figure pas n'est ni mesurée ni niée.

**Antigravity a sa ligne sans être activable.** Il hérite du registre de Gemini
et s'activera sous le nom `gemini` ; la table nomme cet héritage au lieu de le
laisser implicite : aujourd'hui `--host gemini` ne distingue pas les deux
postes, et rien ne lit la ligne d'Antigravity.

**Ce qui n'est pas tranché.** Les deux identifiants restent réservés (§ 3.8) :
la règle est fixée et la table écrite, mais aucune commande ne la lit et la
mention « mode assisté » n'est affichée nulle part. Ce que le noyau fera d'un
hôte `assisté` reste ouvert. La spécification refuse l'activation d'un hôte qui
ne peut pas ancrer tous les gates ; ce qui reste à trancher est le sens
d'« ancrer » — équivalent natif déclaré, ou refus mesuré : dans le premier sens,
un hôte `assisté` s'active en le disant ; dans le second, son activation est
refusée. La table le porte comme tel, et la réponse précède le check qui la
lira.

## 4. Ce qui reste noyau, et pourquoi

Par parcimonie, ne sont **pas** promis : les 52 outils de `.agents/bin/`, les
scanners de `.agents/security/`, le référentiel embarqué de `.agents/ref/`, le
schéma de l'index SQLite, le magasin d'événements V3, les implémentations de
hooks des répertoires d'hôtes, et l'ensemble du paquet V3, qu'il réside dans
`agentic_v3/` ou dans `.agents/vendor/agentic_v3/`. Ces deux chemins sont des
emplacements internes, sans garantie de chemin public.

Un adoptant n'a besoin d'aucun d'eux pour utiliser le kit. Les promettre
figerait des signatures internes que la refonte doit justement être libre de
déplacer — c'est tout l'objet du passage à un paquet installable.

## 5. Renommages et conventions — tranchés maintenant

C'est la seule fenêtre où ils coûtent zéro : aucune version publiée, aucun
adoptant, aucun tag dans le dépôt.

| Question | Décision |
|---|---|
| Renommer `.agents/` | **Non.** C'est le nom de contrat, D2 le tranche |
| Renommer les douze workflows | **Non.** Ils sont déjà cités dans la doctrine des six hôtes |
| Préfixe des variables du kit | **`CADRE_`** pour les nouvelles ; `AGENTS_HOOK_HOST` garde son nom |
| Nom de la distribution | **`cadre-kit`** : le nom `cadre` est pris sur l'index public par un autre paquet |
| Nom du paquet d'import et de la commande | **`cadre`** pour le paquet d'import ; la commande porte aujourd'hui le même nom |
| Nom du dépôt de publication | **`glass-dist`**, distinct et sans aucune source |
| Format des défs d'agents | **Natif de l'hôte**, jamais uniformisé |

## 6. Les limites de ce document

1. **Il est en partie déclaratif.** Le check introspecte la ligne de commande et
   les variables `CADRE_` du noyau ; restent déclarés, sans être confrontés à du
   code qui tourne, au moins les trois promesses du contrat de hook, les formats,
   les surfaces, les variables hors `CADRE_` et les commandes hors workflows.
2. **`0.x` autorise l'évolution.** Une entrée peut changer ou disparaître avec
   une ligne au CHANGELOG et au moins une montée de mineure de `version_contrat`. À partir de `1.0`, il faudra un bump majeur.
3. **Le niveau de chaque hôte est classé, pas encore appliqué.** La table du
   § 3.10 l'attribue à partir des seuls statuts que le dépôt a tracés : aucune
   mesure nouvelle n'a été jouée pour la remplir, et aucune commande ne la lit.
   Jusque-là, `niveau-hote:enforce` et `niveau-hote:assiste` restent réservés.

---

## 7. Index des identifiants

Les 74 identifiants exacts du verrou — **54 publics et 20 réservés** —
tels que les checks les lisent. C'est cette orthographe qui fait foi, pas la
prose des sections précédentes.

| Identifiant | Type | Statut |
|---|---|---|
| `cadre` | cli | reserve |
| `cadre --version` | cli | public |
| `cadre paths` | cli | public |
| `cadre init` | cli | reserve |
| `cadre init --upgrade` | cli | reserve |
| `cadre hook` | cli | public |
| `cadre hosts` | cli | reserve |
| `cadre doctor` | cli | reserve |
| `cadre dashboard` | cli | reserve |
| `cadre uninstall` | cli | reserve |
| `cadre config explain` | cli | public |
| `cadre disarm` | cli | reserve |
| `cadre lessons` | cli | reserve |
| `cadre lessons promote` | cli | public |
| `cadre remote` | cli | reserve |
| `cadre tasks` | cli | reserve |
| `cadre ledger` | cli | reserve |
| `cadre specs` | cli | reserve |
| `hook:SessionStart` | evenement | public |
| `hook:PreToolUse` | evenement | public |
| `hook:PostToolUse` | evenement | public |
| `hook:Stop` | evenement | public |
| `hook:SubagentStop` | evenement | public |
| `hook:PreCompact` | evenement | public |
| `hook:SessionEnd` | evenement | public |
| `hook:PostCompact` | evenement | public |
| `hook:SubagentStart` | evenement | public |
| `hook:Notification` | evenement | public |
| `contrat-hook:payload-stdin-json` | protocole | public |
| `contrat-hook:verdict-stdout-json` | protocole | public |
| `contrat-hook:refus-par-hote` | protocole | public |
| `AGENTS_HOOK_HOST` | variable | public |
| `CADRE_CONFIG_HOME` | variable | public |
| `CADRE_STATE_DIR` | variable | public |
| `CADRE_PROJECT_ROOT` | variable | public |
| `NVD_API_KEY` | variable | public |
| `NVD_DATA_DIR` | variable | public |
| `NVD_OFFLINE` | variable | public |
| `.agents/` | arborescence | public |
| `.agents/state/board/TASKS.json` | arborescence | public |
| `.agents/state/memory/LEDGER.json` | arborescence | public |
| `.agents/state/specs/SPECS.json` | arborescence | public |
| `.agents/hooks/<hote>/<evenement>` | arborescence | reserve |
| `.agents/kit.lock` | arborescence | public |
| `.agents/state/gates/` | arborescence | public |
| `format:def-agent` | format | public |
| `format:frontmatter-cadre-managed` | format | reserve |
| `format:lecon` | format | reserve |
| `format:gate-declaratif` | format | reserve |
| `core-scripts/verify.sh` | commande | public |
| `workflow:kickoff` | commande | public |
| `workflow:audit` | commande | public |
| `workflow:index` | commande | public |
| `workflow:skills-sync` | commande | public |
| `workflow:docs-sync` | commande | public |
| `workflow:specs-sync` | commande | public |
| `workflow:planning` | commande | public |
| `workflow:planning-all` | commande | public |
| `workflow:dash` | commande | public |
| `workflow:lang` | commande | public |
| `workflow:night` | commande | public |
| `workflow:jira` | commande | public |
| `workflow:setup` | commande | public |
| `dashboard:hors-ligne` | surface | reserve |
| `niveau-hote:enforce` | surface | reserve |
| `niveau-hote:assiste` | surface | reserve |
| `.agents/skills/` | arborescence | public |
| `.claude/skills/` | arborescence | public |
| `.github/skills/` | arborescence | public |
| `.github/instructions/` | arborescence | public |
| `.agents/protected-paths.local` | arborescence | public |
| `.gitleaks.toml` | format | public |
| `.githooks/pre-push` | commande | public |
| `.agents/state/gates/GITLEAKS_FALLBACK.off` | arborescence | public |
