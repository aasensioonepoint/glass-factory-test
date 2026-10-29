# Mode Expert (cross-host) — doctrine et capture autoritaire

Doctrine du mécanisme piloté par `core-scripts/apply-mode.py {expert|restore|status}`.
Ce fichier est à la fois la **doctrine** (la prose ci-dessous) et la **capture
autoritaire** (le bloc `GRID` du § 5, lu par le script). Les deux se lisent
ensemble : la prose dit *pourquoi*, la grille dit *quoi*.

Importé de `op-agentic-builder-kit` et **RÉDUIT** par T-00000393.

---

## 1. Ce que ce mécanisme est, et ce qu'il n'est pas

Le mécanisme réécrit le **tier de modèle** et l'**effort de raisonnement**
inscrits dans le frontmatter des définitions d'agents, sur les hôtes qui portent
réellement ces clés. Il ne change aucun comportement d'agent, aucune route,
aucun plancher de sécurité : il ne touche que deux axes dans un vocabulaire clos.

**UPGRADE SEULEMENT.** Il n'existe qu'un mode, `expert`, et il **monte** d'un
cran. La source d'où vient ce moteur en portait deux autres, descendants ; ils
ne sont **pas importés**, et ce n'est pas un oubli — `AGENTS.md` § Full power
interdit d'abaisser un tier pour dépenser moins. Un levier qui descend serait
la contradiction de cette règle, livrée clés en main.

`restore` **n'est donc pas un mode**. C'est le retour EXACT à la colonne de
référence — la valeur committée agent par agent, jamais un palier moyen — et
l'**absence** du fichier `.agents/state/local/MODEL_MODE` EST l'état de
référence. Le dépôt vit dans cet état ; il ne se committe jamais autrement.

---

## 2. Périmètre

Les comptes ci-dessous ont été **mesurés sur cet arbre** au moment de la
rédaction (35 defs par hôte, sur les cinq hôtes). Ils sont **re-dérivés du
disque** par `core-scripts/apply-mode.test.sh` à chaque passage de la porte CI :
s'ils périment, le banc le dit avant qu'une doctrine ne mente.

### 2.1 Périmètre à levier réel

| hôte | defs pilotées | clés présentes |
|---|---|---|
| `claude` (`.claude/agents/*.md`) | **29** sur 35 | `model:` + `effort:` |
| `gemini` (`.gemini/agents/*.md`) | **30** sur 35 | `model:` seul — aucun `effort:`, gemini-cli 0.57.0 refuse la clé (S-00002854, T-00000779) |
| `codex` (`.codex/agents/*.toml`) | **30** sur 35 | `model_reasoning_effort` piloté ; modèles épinglés hors levier (§ 3.3) |

- **Le binôme de clôture est exclu sur les CINQ hôtes** (T-012, 2026-09-12) :
  `critic-opus`, `critic-fable` et `critic-sonnet-max`. Ce n'est pas une
  commodité, c'est le bon régime — ce levier **échange les modèles** entre les
  modes, et ces trois agents sont **nommés d'après le leur**. Les échanger leur
  ôterait leur raison d'être. Conséquence arithmétique vérifiée avant d'écrire :
  le roster passe de 26 à 29 et **les cinq compteurs restent identiques**,
  puisque les trois ajouts sont exclus partout.
- **Même geste, même arithmétique, le 2026-09-14 (`T-00000624`)** : la PAIRE DE
  PLAN ajoute `plan-critic-sonnet-max` et `planner-sonnet`, eux aussi nommés
  d'après le modèle qu'ils portent sur Claude Code, donc eux aussi exclus du
  levier sur les cinq hôtes. Le roster passe de 29 à **31** et **les cinq
  compteurs restent encore identiques**. C'est la vérification qui doit être
  faite AVANT d'écrire, pas le constat qu'on fait après : si un ajout n'était
  pas exclu, `EXPECTED_TOUCHED` bougerait et `apply-mode.test.sh` rougirait —
  ce qui est exactement son travail.
- **Le cas inverse, le 2026-10-08 (`T-01M4JC50S6CTJ5HJ697929E6N8`)** : `load-tester` porte le
  roster à **32** et n'est **PAS** exclu — son modèle n'est pas son identité ; il
  produit du code (le scénario k6) au tier des défs dev (décision pilote Q8).
  Les cinq compteurs prennent donc **+1 chacun**, remesurés dans
  `EXPECTED_TOUCHED` dans le même commit, et la grille gagne quatre lignes
  (deux `claude`, une `gemini`, une `codex`) par `restore --recapture`.
- **Même cas, le 2026-10-18 (`T-01M52X1W3WPKCWX1DC36NMKJB6`)** : `terraform-deployer`
  porte le roster à **33** et n'est **PAS** exclu — il produit l'IaC (décision
  pilote Q2), au tier des défs dev, épinglé au rang Sol côté `codex` (`gpt-6-sol`
  depuis le 2026-10-20, § 3.3). Les cinq
  compteurs prennent **+1 chacun**, remesurés dans `EXPECTED_TOUCHED` dans le
  même commit que sa déf, et la grille gagne encore quatre lignes par
  `restore --recapture`.
- **Même cas, le 2026-10-21 (`T-01M5BZC1Y0T36EHTZY9AKZ650F`, branche reprise/2026-10-20)** : `seo-specialist`
  porte le roster à **34** et n'est **PAS** exclu — relecteur SEO en lecture
  seule, il n'est pas nommé d'après son modèle (`claude-opus-5-5` / `high` côté
  `claude`, `gpt-6-astra` / `high` côté `codex`, `gemini-3.1-pro`). Les cinq
  compteurs prennent **+1 chacun**, remesurés dans `EXPECTED_TOUCHED`, et la
  grille gagne quatre lignes par `restore --recapture`.
- **Même cas, le 2026-10-22 (`T-01M5HEJYSJEYA8K3834FZVT60N`, develop)** : `reverse-engineer`
  porte le roster à **34** et n'est **PAS** exclu — son tier tient au
  raisonnement sur du code décompilé hostile, sans produire de code ; épinglé au
  rang Astra côté `codex` (`gpt-6-astra`, S-01M5HG8ZF5VY9T8DTV9TS86DT0). Les cinq
  compteurs prennent **+1 chacun**, remesurés dans `EXPECTED_TOUCHED` dans la
  même livraison que sa déf, pas dans le même commit (parent
  `T-01M5HEBP3C3R9DCZ6G5XYH8J9Q`, enfants DEFS `T-01M5HEJYSJEYA8K3834FZVT60N` et
  DOCTRINE `T-01M5HEJZ9XVXWQ61XMZYGA3YT0`, porte unique), et la grille gagne
  quatre lignes (deux `claude`, une `gemini`, une `codex`), celles que capture
  `restore --recapture`.
- **Les deux réunis le 2026-10-25** (fusion de develop dans reprise/2026-10-20) : le roster
  compte **35**, les cinq compteurs prennent **+2** sur 33, remesurés dans
  `EXPECTED_TOUCHED` (29 / 30 / 30 / 29 / 29), et la grille compte huit lignes de plus.
- Côté `claude`, `orchestrator.md` est **exclu à demeure** (§ 3.1).
  35 − 1 − 3 − 2 = **29**. `communicator.md` y portait **24** jusqu'au 2026-09-05 parce
  qu'il n'avait aucune clé de tier et n'était donc **pas pilotable** ; le pilote
  lui en a donné (`haiku` / `medium`), il est devenu pilotable et il entre dans
  le compte — **compté, jamais agité** : il reste gelé (§ 3.2), donc `expert`
  égale `défaut` sur ses deux lignes.
- Côté `gemini` et `codex`, `communicator` porte ses clés depuis toujours et
  compte donc dans les 30, avec le même gel. 35 − 3 − 2 = **30**.

**Total à levier : 29 + 30 + 30 = 89 défs pilotées, 118 lignes de grille** (chaque
agent compte pour deux lignes chez `claude` — un axe modèle, un axe effort — et
pour une seule chez `gemini`, modèle seul, et chez `codex`, effort seul). Avant
T-00000779 cette phrase disait « 77 lignes » quand le moteur en lisait 128 : faute corrigée. Voir le § 5 pour le compte exact.

### 2.2 Volet indicatif

Deux hôtes ne portent **aucun levier réel** : leurs définitions d'agents ne
contiennent aucune clé de tier.

| hôte | defs annotées | clé de tier |
|---|---|---|
| `github` (`.github/agents/*.agent.md`) | **29** sur 35 | aucune |
| `kimi` (`.kimi-code/agents/*.md`) | **29** sur 35 | aucune |

(`communicator` exclu des deux côtés par symétrie avec son gel, et le binôme de
clôture exclu comme partout, la paire de plan avec lui : 35 − 1 − 3 − 2 = **29**.)

**`github` n'était pas nommé par la tâche.** Il est conservé tel quel depuis
l'import, en symétrie stricte de `kimi`, et cette conservation a été **ratifiée
au gate** plutôt que subie : retirer le volet indicatif d'un des deux hôtes
sans levier aurait produit une asymétrie que rien ne motive. Cette phrase
voyage avec le fichier, pour que l'adoptant sache que c'est une décision et non
un reste.

Ces defs reçoivent, à **chaque** `expert` (pas seulement à la première fois),
un jeton strictement indicatif :

```
<!-- MODEL-MODE: expert — non appliqué sur cet hôte (aucune clé de tier) ; voir .agents/ref/MODEL_MODES.md -->
```

Le jeton dit ce qu'il est : une **information honnête**, jamais une
application. Il est inséré juste après la fermeture du frontmatter, dont la
position est **localisée dynamiquement à l'écriture** et jamais codée en dur —
mesuré sur ce dépôt, côté `kimi`, cette ligne de fermeture ne tombe pas au même
endroit d'une def à l'autre. `restore` **retire** le jeton : le retrait est
l'inverse exact de l'insertion, donc l'aller-retour est fidèle à l'octet.

**Rien n'est affirmé sur l'effet runtime de ce jeton côté `kimi`.** Le câblage
de cet hôte est prouvé au niveau fichier ; son comportement à l'exécution reste
un résidu ouvert (T-00000395). Le jeton est indicatif précisément parce qu'on
ne peut pas prétendre l'appliquer.

Deux gardes encadrent ce texte, et elles sont mécaniques :

1. Le script **refuse** d'insérer une ligne qui matcherait `^model:`,
   `^effort:` ou `^model_reasoning_effort` — protection contre une future
   retouche du libellé qui glisserait une clé parasite dans un fichier réputé
   sans levier.
2. Le texte ne doit contenir **aucun mot-clé de la fonction `probe()`** de
   `.agents/evals/test_golden_transcripts.py`. Ces mots-clés sont des sondes
   textuelles sur le contenu brut des defs : un jeton mal libellé basculerait
   un invariant de golden transcript sans rapport. La vérification se fait par
   **introspection** de `probe()` — jamais par recopie de sa liste — dans
   `core-scripts/apply-mode.test.sh`.

---

## 3. Exclusions et gels

### 3.1 `orchestrator` (hôte `claude`) — EXCLU À DEMEURE

Son frontmatter `model:` / `effort:` n'est **JAMAIS** réécrit. Il n'apparaît pas
dans la grille du § 5.

Raison, à citer : l'entrée **`L-00000068`** du registre d'`op-agentic-builder-kit`
— l'hôte Claude Code **réécrit seul** certains frontmatters en cours de session.
Gérer programmatiquement une valeur que l'hôte peut écraser sans prévenir ferait
porter au mécanisme une **garantie qu'il ne peut pas vérifier**.

**PORTÉE NON RE-MESURÉE ICI.** Cette exclusion est un **héritage prudent, pas
une mesure locale** : ce chantier n'a pas re-observé le phénomène sur ce dépôt,
et ne prétend donc pas en connaître l'étendue exacte. S'y ajoute une prudence
propre : `orchestrator` est la def de l'agent qui pilote la session en cours.
Le dire est le seul moyen qu'un adoptant sache qu'il hérite d'une précaution et
non d'un relevé.

Corollaire de transparence : `apply-mode.py status` ne **garantit** pas
l'absence de dérive. Il **constate** l'écart entre le disque et le mode
enregistré, et il le dit dans sa propre sortie.

### 3.2 `communicator` — GELÉ sur les cinq hôtes

Sa valeur `expert` est égale à sa valeur de référence sur les hôtes à levier, et
il ne reçoit aucun jeton sur les hôtes indicatifs. Il est le traducteur du
pilote : le monter ne change rien à une tâche de reformulation, et l'agiter
ferait bouger la seule surface que le pilote lit.

**Le gel ne dit RIEN du palier lui-même** — seulement que le mécanisme ne le
bouge pas. Côté `claude`, `communicator` n'a longtemps porté aucune clé, et
cette vacuité était épinglée (`S-00000897`) : à défaut de tier, l'agent hérite
du modèle de session. **Décision pilote du 2026-09-05** : il porte désormais
`haiku` / `medium`, valeur choisie à la main et assumée comme telle. Le gel
s'applique inchangé — il est compté dans la grille et jamais monté.

Côté `codex`, il est épinglé sur `gpt-6-luna` / `medium`; `expert` et
`restore` préservent ces deux valeurs.

### 3.3 Vocabulaires clos — MESURÉS SUR CET ARBRE

Les échelles ci-dessous ne sont **pas** celles de la source : nos defs
committent à HEAD des valeurs que la sienne ne connaissait pas. Elles ont été
relevées sur l'arbre, et leur ordre est celui de `CLAUDE_MODEL_RANK` /
`EFFORT_RANK` de `.agents/evals/test_golden_transcripts.py`, du plus faible au
plus fort.

| hôte | axe | échelle fermée (croissante) |
|---|---|---|
| `claude` | model | `haiku` → `sonnet` → `opus` → `fable` |
| `claude` | effort | `low` → `medium` → `high` → `xhigh` → `max` |
| `gemini` | model | `gemini-3.5-flash` → `gemini-3.1-pro` |
| `codex` | effort | `low` → `medium` → `high` → `xhigh` → `max` |

Depuis T-00000553, la décision explicite du pilote répartit les 30 defs Codex pilotées (35 au roster, moins les défs exclues du levier, en gras ci-dessous : `EXCLUDED` de `core-scripts/apply-mode.py`)
entre quatre modèles épinglés, hors levier d'effort :

| modèle Codex | agents |
|---|---|
| `gpt-6-astra` | `orchestrator`, `planner`, `modeler`, `plan-critic`, `exec-critic`, `design-review`, `security-code-review`, `security-code-review-global`, `reverse-engineer`, `seo-specialist`, **`critic-opus`** |
| `gpt-6-sol` | `dev-mono`, `dev-multi`, `frontend-fidelity`, `optimizer`, `load-tester`, `terraform-deployer`, **`critic-fable`** |
| `gpt-5.6-terra` | `analyzer`, `custom-docs-curator`, `documenter`, `indexer`, `skills-resolver`, `security-orchestrator`, `security-remediation`, `security-sca`, **`critic-sonnet-max`**, **`plan-critic-sonnet-max`**, **`planner-sonnet`** |
| `gpt-6-luna` | `language-detector`, `board-reporter`, `communicator`, `sca-java`, `sca-mobile`, `sca-npm` |

Les efforts définis lors de T-00000552 sont conservés, à une exception près :
depuis la décision pilote du 2026-10-11 (`S-01M4N2VNE3FP8YT1QH028ZQYJY`), `max`
est le plafond du levier Codex du kit — `xhigh` l'était jusque-là —, sans
prétendre être la limite des modèles. `plan-critic`, `critic-fable` et, depuis
la décision pilote `S-01M51GNKV9FM9WWXSKXEJQSEQY` (2026-10-16),
`security-code-review-global` y portent `max`, et en mode `expert` cinq défs
Codex pilotées passent de `xhigh` à `max` (`design-review`, `exec-critic`,
`load-tester`, depuis le 2026-10-18 `terraform-deployer`, depuis le 2026-10-22
`reverse-engineer`) — compte à rejouer :
les `.codex/agents/*.toml` à `model_reasoning_effort = "xhigh"` hors `EXCLUDED`
de `core-scripts/apply-mode.py` ; `dev-mono`, `dev-multi` et `frontend-fidelity`, en `high`
depuis S-01M551RDK3PRT4VGTV5BN1ZM30, y passent à `xhigh`. `max` est relevé dans le cache local de codex-cli, jamais par un
run réel.
Cette répartition est une décision de rôle du pilote, non un précédent de baisse
autonome motivée par le coût. `expert` et `restore` ne pilotent que
`model_reasoning_effort` et préservent donc les modèles épinglés comme la
distribution ci-dessus. Les descriptions de niveau — Astra pour le travail le
plus difficile, Sol pour le complexe, Terra pour le quotidien et Luna pour le
clair/répétable — viennent de la [documentation officielle des modèles](https://learn.chatgpt.com/docs/models).
Elles ne constituent pas un benchmark inter-fournisseurs ni une affirmation de
disponibilité runtime : la disponibilité a été vérifiée dans le cache local, pas
par une évaluation live des 29 agents pilotés. Depuis le 2026-10-20
(`T-01M5CYKCF6S7T5N2GCD6VXQTR7`), les rangs Sol et Luna sont tenus par `gpt-6-sol`
et `gpt-6-luna`, seuls slugs de ces rangs présents dans le cache local relevé ce
jour-là ; `gpt-5.6-terra` et `gpt-6-astra` ne bougent pas. `gpt-6-luna` reste donc
rangé SOUS `gpt-5.6-terra` : cet ordre est **déclaratif** — la politique de rôle du
pilote —, aucune mesure ne compare ces deux modèles. Le format des sous-agents est documenté
dans la [documentation officielle des sous-agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

### 3.4 Le binôme de clôture — ce que chaque hôte peut réellement en tenir

**Depuis la décision pilote du 2026-10-07 (`S-00004500`), UN SEUL critique de
clôture tourne : `critic-opus`**, qui porte seul les angles A et B ; `critic-fable`
est son premier repli et `critic-sonnet-max` le second, chacun invoqué SEUL quand
le précédent est indisponible (quota, panne). La garde de `tasks.py done` exige
`BINOME_MIN` critique(s) — un. **L'indépendance de deux modèles différents est
ABANDONNÉE par décision**, jamais affaiblie en silence. La table ci-dessous reste
juste sur les paliers, une colonne par rang de la cascade ; la colonne « propriété
tenue » décrit la PAIRE telle qu'elle a tourné jusqu'au 2026-10-07, gardée comme
historique : *deux modèles différents ne se trompent pas de la même façon*.

| hôte | nominal · `critic-opus` | 1er repli · `critic-fable` | 2e repli · `critic-sonnet-max` | propriété tenue (paire, jusqu'au 2026-10-07) |
|---|---|---|---|---|
| `claude` | `claude-opus-5-5` / `xhigh` | `claude-opus-5-5` / `max` | `sonnet` / `max` | **oui** jusqu'au 2026-10-11 — trois modèles distincts (`opus`, `fable`, `sonnet`). Depuis `S-01M4N02D2KFYQVV92ZXGSXBG2G`, les rangs 1 et 2 partagent `claude-opus-5-5` (`xhigh` / `max`) : seul le 2e repli porte un autre modèle |
| `codex` | `gpt-6-astra` / `xhigh` | `gpt-6-sol` / `max` | `gpt-5.6-terra` / `max` | **oui** — même forme : le plus fort, un autre fort, un plus bas compensé par l'effort |
| `gemini` | `gemini-3.1-pro` / — | `gemini-3.1-pro` / — | `gemini-3.1-pro` / — | **NON** — l'échelle fermée ne porte que deux modèles, et `gemini-3.5-flash` est le tier « clair/répétable ». Un second critique sur flash aurait été plus faible que le premier, ce qui est pire qu'un doublon. Les deux angles restaient séparés, les modèles non |
| `github` | — | — | — | **NON** — hôte non tiéré, mesuré : zéro déf sur 35 porte `model:` |
| `kimi` | — | — | — | **NON** — hôte non tiéré, même mesure |

**Le repli qui survit à un quota Opus.** Sur Claude Code, `critic-fable` partage
le modèle de `critic-opus` (`claude-opus-5-5`) depuis la décision pilote du
2026-10-11 (`S-01M4N02D2KFYQVV92ZXGSXBG2G`) : un quota Opus épuisé les rend
indisponibles tous les deux, et le repli qui survit est `critic-sonnet-max`. Le
premier repli ne couvre donc plus, sur cet hôte, qu'une indisponibilité propre à
`critic-opus` ; sur `codex`, `critic-fable` reste sur `gpt-6-sol`, distinct.

**Un point de rigueur sur l'effort côté Codex, relevé par la revue de clôture.**
`critic-sonnet-max` et, depuis le 2026-10-11, `critic-fable` portent `max` côté
Codex. `max` **est dans** `SCALES[("codex", "effort")]` depuis la décision pilote
`S-01M4N2VNE3FP8YT1QH028ZQYJY` ; avant, l'échelle s'arrêtait à `xhigh`, et ce
n'était pas une incohérence : elle borne ce que le **levier écrit**, et ces trois
défs en sont exclues, donc le levier ne les écrit jamais. Ce qui **n'est pas
mesuré**, en revanche, c'est si le modèle Codex honore `max` — le cache local de
codex-cli le liste, ce qui n'est pas un run ; le tableau ci-dessus dit « compensé
par l'effort », et cette compensation est une **intention déclarée, pas un
relevé**. La mesurer demande une exécution réelle qu'aucun banc ne fait.

**Ce qui reste vrai partout** : un critique de clôture, read-only, qui porte seul
les angles A et B et rend les trois blocs obligatoires, et une cascade de repli
fixe — `critic-opus`, puis `critic-fable`, puis `critic-sonnet-max`, jamais deux
à la fois. **Ce qui ne l'est plus nulle part** : la diversité de modèle entre deux
relectures — abandonnée par `S-00004500`. Sur `gemini`, `github` et `kimi`, elle
n'était déjà pas tenue ; la revue y protège contre l'angle mort, pas contre le
biais d'un modèle.

Les ids `gemini` sont des **littéraux complets**, jamais composés par préfixe ou
suffixe : `gemini-3.5-pro` n'existe pas.

### 3.4 bis La paire de plan — la même table, un cran plus tôt (`T-00000624`)

**Depuis la décision pilote du 2026-10-13 (`S-01M4TZZ13Y`), la planification se
fait sur Opus : `planner-sonnet` et `plan-critic-sonnet-max` sont HORS CHAÎNE**
— débranchés, pas supprimés : leurs défs restent sur disque, l'orchestrateur ne
les invoque plus, et leurs traces restent acceptées par la garde de `start`, sans
échéance ; chaque trace expire 24 h après son écriture, comme toute trace. Au `NO_GO`, `planner` reprend son plan avec les constats de
`plan-critic` ; `plan-critic` indisponible (quota Opus épuisé, qui retire aussi le
planner sur Claude Code) : `COVERAGE DEGRADED — plan-critic unavailable, verdict absent`.

**Du 2026-10-03 (`S-00003871`) au 2026-10-13, UN SEUL critique de plan
tournait : `plan-critic`**, dont le verdict EST le verdict et qui porte aussi
l'attaque des prémisses ; `plan-critic-sonnet-max` n'était plus que son
remplaçant sur quota, annoncé `COVERAGE DEGRADED`, et un `NO_GO` passait le plan
à `planner-sonnet` (historique, clos par S-01M4TZZ13Y). La règle reste nominative : **`plan-critic` domine
le planner ACTIF, `planner`, sur chaque axe que l'hôte porte**
(`test_golden_transcripts.py` l'exige par nom). Depuis S-01M57F0BHB
(2026-10-18), `planner-sonnet`, hors chaîne, reste en `xhigh` au-dessus du
critique : le rebrancher exige de remonter `plan-critic` d'abord. La
table ci-dessous reste juste sur les paliers (colonne B = l'ancien remplaçant) ;
le reste de cette section décrit la PAIRE telle qu'elle a tourné du 2026-09-14
au 2026-10-03, gardé comme historique.

Avant cette décision, `plan-critic` et `plan-critic-sonnet-max` tournaient
**toujours les deux**, en parallèle, sur le MÊME plan, avant la porte humaine. Même propriété recherchée
que le binôme de clôture, donc **même table et mêmes bornes** : la recopier
plutôt que renvoyer au § 3.4 est délibéré, parce qu'un lecteur qui trouve une
paire sans sa table conclut que la propriété est tenue partout.

| hôte | A · structure du plan | B · prémisses du plan | planner | escalade | propriété tenue |
|---|---|---|---|---|---|
| `claude` | `claude-opus-5-5` / `high` | `sonnet` / `max` | `claude-opus-5-5` / `medium` | `sonnet` / `xhigh` | **oui** jusqu'au 2026-10-11 — trois modèles distincts : `fable` sur le jugement de structure, `sonnet` sur les prémisses et l'escalade, `claude-opus-5-5` (rang `opus`) sur la production ; du 2026-09-24 (`S-00002148`) au 2026-10-11, Critique A dominait le planner nominal STRICTEMENT sur les deux axes, un cran de modèle et un cran d'effort. **Depuis la décision pilote du 2026-10-11 (`S-01M4N02D2KFYQVV92ZXGSXBG2G`), A partage le modèle du planner** : la domination a tenu par l'ÉGALITÉ de modèle et deux crans d'effort (`max` contre `high`) ; **depuis la décision pilote du 2026-10-18 (`S-01M57F0BHB`, vitesse, jamais coût), par un cran** (`high` contre `medium`). Sur Claude Code un quota Opus épuisé retire A et le planner ensemble. Historique : `opus` / `opus` à `271ca73`, puis les deux sur `fable` du 2026-09-20 au 2026-09-24 (domination par l'effort seul, B et l'escalade à DEUX paliers sous le planner). Aujourd'hui B et l'escalade sont à UN palier sous le planner sur l'axe MODÈLE (sur l'effort, l'escalade `sonnet`/`xhigh` le dépasse de deux crans, et A d'un cran) |
| `codex` | `gpt-6-astra` / `high` | `gpt-5.6-terra` / `max` | `gpt-6-astra` / `medium` | `gpt-5.6-terra` / `xhigh` | **oui** — même forme |
| `gemini` | `gemini-3.1-pro` / — | `gemini-3.1-pro` / — | `gemini-3.1-pro` / — | `gemini-3.1-pro` / — | **NON** — même cause qu'au § 3.4, et **pire ici pour l'escalade** : le planner d'escalade y est identique au planner sur le seul axe qui existe (`gemini` ne porte aucun axe d'effort — gemini-cli 0.57.0 refuse la clé, S-00002854). Elle n'achète qu'une seconde dérivation indépendante, rien de tiéré, et la déf le dit en toutes lettres |
| `github` | — | — | — | — | **NON** — hôte non tiéré, mesuré : zéro déf sur 35 porte `model:` |
| `kimi` | — | — | — | — | **NON** — hôte non tiéré, même mesure |

**LA RÈGLE « CRITIQUE ≥ PLANNER » EST RÉÉCRITE, ET C'EST UNE DÉCISION PILOTE DU
2026-09-14, PAS UN ASSOUPLISSEMENT SUBI.** Elle disait « le critique du plan
domine le planner sur chaque axe » ; elle dit désormais **« AU MOINS UN des deux
critiques de plan domine le planner sur chaque axe »**. Motif : la règle existe
contre le tampon-encreur — un relecteur plus faible que l'auteur —, et cette
protection est tenue dès qu'UN critique domine. Exiger que les DEUX dominent
interdirait la diversité de modèles, c'est-à-dire la propriété même que la paire
existe pour porter : sur `claude`, `sonnet`(1) est sous `opus`(2) dans
`CLAUDE_MODEL_RANK`, donc un Critique B en sonnet était **rouge par
construction**.

**Ce qui la TIENT mécaniquement n'a pas bougé d'un octet** :
`test_golden_transcripts.py` compare toujours `plan-critic` à `planner`, par
nom — **mais ce qu'elle MESURE a changé trois fois** : le 2026-09-20 les deux
sont passés sur `fable` (`opus` / `opus` avant), la domination ne tenant plus
que par l'ÉGALITÉ sur le modèle et par l'effort (`xhigh` contre `high`), le test
comparant en `>=` ; puis la **décision pilote du 2026-09-24 (`S-00002148`)** a
remis le planner sur `claude-opus-5-5`, que `CLAUDE_MODEL_RANK` résout en `opus`
(rang 2) par ses jetons. `plan-critic` restant sur `fable` (rang 3), la
domination était redevenue STRICTE sur les deux axes — un cran de modèle, un cran
d'effort — jusqu'à la **décision pilote du 2026-10-11
(`S-01M4N02D2KFYQVV92ZXGSXBG2G`)**, qui a passé `plan-critic` sur
`claude-opus-5-5` / `max` : au rang `opus` comme le planner, la domination a tenu
par l'ÉGALITÉ de modèle et par deux crans d'effort (`max` contre `high`).
**Depuis la décision pilote du 2026-10-18 (`S-01M57F0BHB`, vitesse, jamais
coût), `plan-critic` est en `high` et `planner` en `medium` : la domination tient
par l'ÉGALITÉ de modèle et UN cran d'effort**, que `test_golden_transcripts.py`
exige STRICT ; remonter le planner en `high` la ramènerait à une égalité sur les
deux axes. Sur
Claude Code, un quota Opus épuisé retire le critique et le planner ensemble.
`plan-critic-sonnet-max`, en `sonnet` (rang 1), reste SOUS le planner
sur l'axe modèle : il ne compte pas parmi les dominants. C'est `plan-critic` qui porte la
règle ; `plan-critic-sonnet-max` apporte l'angle, jamais la domination. La
conséquence à ne pas manquer : **abaisser `plan-critic` sous le planner casserait
la règle quoi que porte le second critique**, et c'est pour ça que sa ligne 5 le
dit explicitement.

**L'invariant de la source « n'écrit jamais `fable` ni `xhigh` » NE VOYAGE PAS
ici**, et c'est délibéré : `xhigh` est committé à HEAD sur cet arbre, donc un
mécanisme qui le proscrirait refuserait l'arbre qu'il doit servir.
L'invariant conservé est **« jamais hors échelle fermée »** — plus faible en
apparence, mais c'est le seul qui soit vrai ici.

**AUCUNE def `claude` n'écrit `fable` depuis le 2026-10-11**
(`S-01M4N02D2KFYQVV92ZXGSXBG2G`) — relevé à rejouer plutôt qu'à citer :
`grep -l '^model: fable' .claude/agents/*.md` rend vide. Historique : jusqu'à
cette décision, deux defs l'écrivaient, `critic-fable` et `plan-critic`, toutes
deux passées sur `claude-opus-5-5` / `max`. La décision du 2026-09-08 avait repassé
sur `opus` les cinq defs qui le portaient (`orchestrator`, `planner`,
`plan-critic`, `exec-critic`, `design-review`) ; **elle a été annulée EN PARTIE,
deux fois** — `critic-fable` l'écrit depuis sa création, la déf étant nommée
d'après lui, et la **décision pilote du 2026-09-20 a remis `planner` et
`plan-critic` dessus**. `planner` en est ressorti le 2026-09-24 (`S-00002148`) :
il est ÉPINGLÉ sur `claude-opus-5-5`, comme les trois ci-dessous. Les trois autres — `orchestrator`, `exec-critic`,
`design-review` — sont restées sur `opus` **jusqu'au 2026-09-22**, puis ont été
ÉPINGLÉES sur `claude-opus-5-5` (§ 3.4) : même palier par token, mais hors de
l'échelle fermée, donc **plus dérivées du tout** par le levier. Ne pas lire cette
ligne comme si `expert` les montait encore en `fable`. La phrase qui vivait ici (« aucune def ne
l'écrit plus ») était donc **déjà fausse avant ce geste**, à cause de
`critic-fable` : mesuré par `git show HEAD:.claude/agents/critic-fable.md`. Elle
n'est redevenue vraie que le 2026-10-11, par le relevé qui ouvre ce paragraphe.
Conséquence sur le levier, à ne pas découvrir : sur la ligne `plan-critic`
(seule des deux dans la grille, `critic-fable` étant dans `EXCLUDED`),
`expert` == `défaut` sur les DEUX axes depuis le 2026-10-11 — le modèle est
ÉPINGLÉ (§ 3.4 épinglé : `derive()` ne réécrit pas une valeur hors échelle) et
l'effort `max` est déjà au plafond. Sur `fable`, jusque-là, le modèle était au
plafond et seul l'EFFORT y bougeait.

### 3.4 Axe ÉPINGLÉ — une valeur hors échelle n'est jamais réécrite

**Dix-sept** defs `claude` portent `model: claude-opus-5-5` au 2026-10-25, un id
complet qui n'est pas dans l'échelle fermée ci-dessus — compte à rejouer plutôt
qu'à citer : `grep -l '^model: claude-opus-5-5' .claude/agents/*.md | wc -l`.
Ce sont `dev-mono`, `dev-multi`, `frontend-fidelity`, `critic-opus`,
`design-review`, `exec-critic`, `modeler`, `optimizer`, `orchestrator`, depuis le
2026-09-24 (`S-00002148`) `planner`, depuis le 2026-10-08
(`T-01M4JC50S6CTJ5HJ697929E6N8`) `load-tester`, née épinglée, et depuis le
2026-10-11 (`S-01M4N02D2KFYQVV92ZXGSXBG2G`) `plan-critic` et `critic-fable`, et
depuis le 2026-10-16 (`S-01M51GNKV9FM9WWXSKXEJQSEQY`) `security-code-review-global`,
et depuis le 2026-10-18 (`T-01M52X1W3WPKCWX1DC36NMKJB6`) `terraform-deployer`, née épinglée,
et depuis le 2026-10-21 (`T-01M5BZC1Y0T36EHTZY9AKZ650F`) `seo-specialist`, née épinglée,
et depuis le 2026-10-22 (`T-01M5HEJYSJEYA8K3834FZVT60N`) `reverse-engineer`, née épinglée.
**Quatorze d'entre elles sont des axes de la grille du § 5** ; `critic-opus`,
`critic-fable` et `orchestrator` n'y figurent pas, étant dans `EXCLUDED`
(`core-scripts/apply-mode.py`, constante `EXCLUDED`).

**Elles étaient trois jusqu'au 2026-09-22** ; les six autres portaient l'alias
`opus` et sont passées à l'id complet sur **décision pilote `S-00001882`** ; la
dixième, `planner`, venait de `fable` (`S-00002148`, 2026-09-24). **POURQUOI ÉPINGLER,
et c'est une MESURE, pas une lecture de doc** : la résolution de l'alias `opus`
a été relevée MOBILE le 2026-09-22 **sous un CLI inchangé (2.1.280)** — un
sous-agent lancé à 19:08 et un autre à 19:44 ont été servis `claude-opus-5`, un
troisième à 22:17 `claude-opus-5-5`. Le témoin est
`~/.claude/projects/<projet>/<session>/subagents/agent-*.jsonl`, champ
`message.model` (le modèle SERVI), à croiser avec le `tool_use` Task du fichier
parent (le modèle DEMANDÉ). **Borne, parce qu'un point n'est pas une tendance** :
la bascule repose sur UN sous-agent après 22:17, aucun alias `opus` n'ayant été
lancé ensuite. L'id complet est donc ce qui ÉPINGLE, et ce qu'il coûte en
retour — déjà vu avec `claude-opus-4-8` — est le **retard d'id** : le kit restera
sur 5.5 quand l'alias servira le modèle suivant, jusqu'à une édition manuelle des
défs épinglées. On échange la dérive d'alias contre le retard d'id ; ce n'est pas un
gain net, c'est un choix.

CE QUE ÇA COÛTE AUSSI, écrit plutôt que découvert : `design-review`,
`exec-critic`, `modeler`, `optimizer` — et `planner` depuis `S-00002148`, qui
passe en `expert` de `fable`/`xhigh` à `claude-opus-5-5`/`xhigh`, un cran de
modèle perdu — avaient `fable` pour cible `expert` et ne l'ont plus — elles sont désormais non classables, donc le levier ne les monte
plus d'un cran. Les deux autres ne perdent rien, étant déjà dans `EXCLUDED`
(`critic-opus` comme relecteur nommé d'après son modèle, `orchestrator` à
demeure). `plan-critic`, épinglé le 2026-10-11 (`S-01M4N02D2KFYQVV92ZXGSXBG2G`),
passe en `expert` de `fable`/`max` à `claude-opus-5-5`/`max` : un cran de modèle
perdu par décision, l'effort restant au plafond ; `critic-fable`, dans
`EXCLUDED`, ne perd rien au levier. Pour ces axes-là, **`expert` = la valeur de référence** :
non classable ⇒ non dérivable ⇒ **jamais réécrite**. C'est un no-op
**documenté, pas une erreur** — et c'est le comportement sûr, puisque deviner un
cran au-dessus d'une valeur qu'on ne sait pas classer serait une invention.

### 3.5 Relations d'ordre préservées

Trois relations que `.agents/evals/test_golden_transcripts.py` asserte sur
l'arbre doivent tenir **aussi** dans la colonne `expert`, sinon basculer en
`expert` rendrait la porte rouge :

- `plan-critic` **≥** `planner` ;
- `exec-critic` **≥** `dev-mono` et `dev-multi` ;
- `design-review` **≥** `frontend-fidelity`, par axe (S-01M558S8VVRGHACABYMWB2C6EM) — en `expert`, une égalité au plafond `max` passe ; voir § 6 (6).

Pour Codex, le même test rend explicite le rang de politique locale
`Luna < Terra < Sol < Astra`, sans benchmark inter-fournisseurs, afin que chaque
critic reste **≥** à son auteur. Cet ordre est déclaratif, jamais mesuré :
`gpt-6-luna` y reste sous `gpt-5.6-terra` (§ 3.3).

La seconde tient aujourd'hui **par ÉGALITÉ des épingles** — `exec-critic` et les
deux defs dev portent toutes `claude-opus-5-5` — **et non par la seule
construction** ; depuis S-01M5F3KT36B9S58WNC6T92E0BM (2026-10-21), elle tient en
outre par deux crans d'effort sur Claude Code (`xhigh` contre `medium` ; `max`
contre `high` en `expert`), Codex restant à un cran (`xhigh` contre `high`).
La première, depuis `S-01M4N02D2KFYQVV92ZXGSXBG2G` (2026-10-11), tient par
ÉGALITÉ des épingles sur le modèle et par l'effort ; depuis `S-01M57F0BHB` (2026-10-18), `plan-critic`, modèle épinglé, effort
`high` (`xhigh` en `expert`), face à un `planner` épinglé en `medium` (`high`
en `expert`) — le critique reste au-dessus d'un cran dans les deux colonnes ;
du 2026-10-11 au 2026-10-18, il était au plafond (`max`) face à `high`, puis
`xhigh` en `expert`. Du 2026-09-24 (`S-00002148`) au 2026-10-11, elle
tenait par un couple MIXTE : `plan-critic`, classable et déjà au plafond
(`fable`), face au même `planner` épinglé — sûr dans CE sens (le critique ne
pouvait que rester au plafond), pas dans l'autre. La nuance n'est pas cosmétique : « +1 plafonné » n'est monotone
qu'**entre deux valeurs CLASSABLES**. Un axe épinglé ne bouge pas, un axe
classable monte ; mélanger les deux casse l'ordre.
Scénario concret, mesuré le 2026-10-21 : remettre `dev-mono` sur l'alias
`opus` en `xhigh` le rendrait `fable/max` en `expert`, face à un `exec-critic`
resté `claude-opus-5-5/max` — le critique serait DOMINÉ et le § 13 du banc
rougit ; à l'effort livré (`medium`), l'alias seul donne `fable/high`, un
échange que le § 13, qui ne refuse que la dominance, laisse passer.
Elles sont en outre **vérifiées ligne par ligne** sur la grille committée par `core-scripts/apply-mode.test.sh`, avec des rangs
re-dérivés des échelles du § 3.3 et jamais écrits en littéraux : le filet joue
en CI, pas seulement au moment où quelqu'un bascule.

---

## 4. Comment la grille est construite

**La colonne de référence est un instantané du frontmatter committé à HEAD.**
Elle n'est **jamais** dérivée des tableaux de routage en prose des README ou de
`TOKEN_BUDGETS.md` : ces tableaux sont de la documentation, pas la source de
vérité du frontmatter, et rien ne garantit qu'ils soient à jour contre HEAD.

À partir de cette colonne, le principe est mécanique :

- **`expert`** = un cran **au-dessus** dans l'échelle de l'hôte, sur chaque axe,
  **plafonné** au sommet de l'échelle fermée du § 3.3 et jamais au-delà. Un
  agent déjà au plafond **reste tel quel** : no-op documenté, pas une erreur.
- Un agent **gelé** (§ 3.2) ou un **axe épinglé** (§ 3.4) reste à sa valeur de
  référence.

Il n'y a **aucune table d'agents protégés d'une descente** dans ce moteur, parce
qu'il n'y a **aucune descente** : la question ne se pose pas.

---

## 5. La grille

Le bloc ci-dessous est **la capture autoritaire** lue par
`core-scripts/apply-mode.py`. Il ne se modifie pas à la main :
`python core-scripts/apply-mode.py restore --recapture` le réécrit depuis les
fichiers vivants.

Avant d'écrire le moindre octet en `expert`, le script compare le disque à la
colonne du **mode actuellement enregistré** dans `.agents/state/local/MODEL_MODE`
(fichier absent ⇒ colonne de référence). Toute divergence **nomme précisément la
def fautive** et fait **échouer le run sans écrire un seul octet** (code 2).

Trois précisions sur cette garde, parce qu'elles ne vont pas de soi :

- **La comparaison porte sur le mode ENREGISTRÉ, pas sur la colonne de
  référence.** Comparer systématiquement à la référence rendrait tout
  aller-retour impossible : en `expert`, le disque diverge de la référence *par
  construction*.
- **Elle est FERMANTE, pas par fichier.** Une seule def en dérive annule tout le
  run. Un refus fichier par fichier laisserait un arbre **mixte** — mesuré chez
  la source pendant la mise au point du moteur : 76 fichiers écrits avant
  l'abandon, avec un fichier d'état resté sur la référence, c'est-à-dire
  exactement l'état incohérent que cette garde existe pour empêcher.
- **Elle protège `expert` et JAMAIS `restore`.** `restore` EST la réparation :
  une réparation qui se refuse quand l'arbre est abîmé ne répare rien.

Si le bloc de marqueurs ci-dessous est **absent ou malformé**, le script échoue
**proprement** en nommant ce fichier et les deux marqueurs attendus — jamais par
une exception brute, parce que c'est un fichier que des humains éditent.

<!-- GRID:BEGIN — bloc généré, lu par core-scripts/apply-mode.py ; ne pas éditer à la main (utiliser `restore --recapture`) -->

| hôte | agent | axe | défaut | expert |
|---|---|---|---|---|
| `claude` | `analyzer` | effort | `medium` | `high` |
| `claude` | `analyzer` | model | `sonnet` | `opus` |
| `claude` | `board-reporter` | effort | `low` | `medium` |
| `claude` | `board-reporter` | model | `haiku` | `sonnet` |
| `claude` | `communicator` | effort | `medium` | `medium` |
| `claude` | `communicator` | model | `haiku` | `haiku` |
| `claude` | `custom-docs-curator` | effort | `medium` | `high` |
| `claude` | `custom-docs-curator` | model | `sonnet` | `opus` |
| `claude` | `design-review` | effort | `xhigh` | `max` |
| `claude` | `design-review` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `dev-mono` | effort | `medium` | `high` |
| `claude` | `dev-mono` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `dev-multi` | effort | `medium` | `high` |
| `claude` | `dev-multi` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `documenter` | effort | `low` | `medium` |
| `claude` | `documenter` | model | `sonnet` | `opus` |
| `claude` | `exec-critic` | effort | `xhigh` | `max` |
| `claude` | `exec-critic` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `frontend-fidelity` | effort | `high` | `xhigh` |
| `claude` | `frontend-fidelity` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `indexer` | effort | `low` | `medium` |
| `claude` | `indexer` | model | `sonnet` | `opus` |
| `claude` | `language-detector` | effort | `low` | `medium` |
| `claude` | `language-detector` | model | `haiku` | `sonnet` |
| `claude` | `load-tester` | effort | `xhigh` | `max` |
| `claude` | `load-tester` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `modeler` | effort | `high` | `xhigh` |
| `claude` | `modeler` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `optimizer` | effort | `high` | `xhigh` |
| `claude` | `optimizer` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `plan-critic` | effort | `high` | `xhigh` |
| `claude` | `plan-critic` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `planner` | effort | `medium` | `high` |
| `claude` | `planner` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `reverse-engineer` | effort | `xhigh` | `max` |
| `claude` | `reverse-engineer` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `sca-java` | effort | `low` | `medium` |
| `claude` | `sca-java` | model | `haiku` | `sonnet` |
| `claude` | `sca-mobile` | effort | `low` | `medium` |
| `claude` | `sca-mobile` | model | `haiku` | `sonnet` |
| `claude` | `sca-npm` | effort | `low` | `medium` |
| `claude` | `sca-npm` | model | `haiku` | `sonnet` |
| `claude` | `security-code-review` | effort | `high` | `xhigh` |
| `claude` | `security-code-review` | model | `sonnet` | `opus` |
| `claude` | `security-code-review-global` | effort | `max` | `max` |
| `claude` | `security-code-review-global` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `security-orchestrator` | effort | `high` | `xhigh` |
| `claude` | `security-orchestrator` | model | `sonnet` | `opus` |
| `claude` | `security-remediation` | effort | `medium` | `high` |
| `claude` | `security-remediation` | model | `sonnet` | `opus` |
| `claude` | `security-sca` | effort | `medium` | `high` |
| `claude` | `security-sca` | model | `sonnet` | `opus` |
| `claude` | `seo-specialist` | effort | `high` | `xhigh` |
| `claude` | `seo-specialist` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `claude` | `skills-resolver` | effort | `low` | `medium` |
| `claude` | `skills-resolver` | model | `sonnet` | `opus` |
| `claude` | `terraform-deployer` | effort | `xhigh` | `max` |
| `claude` | `terraform-deployer` | model | `claude-opus-5-5` | `claude-opus-5-5` |
| `codex` | `analyzer` | effort | `medium` | `high` |
| `codex` | `board-reporter` | effort | `low` | `medium` |
| `codex` | `communicator` | effort | `medium` | `medium` |
| `codex` | `custom-docs-curator` | effort | `medium` | `high` |
| `codex` | `design-review` | effort | `xhigh` | `max` |
| `codex` | `dev-mono` | effort | `high` | `xhigh` |
| `codex` | `dev-multi` | effort | `high` | `xhigh` |
| `codex` | `documenter` | effort | `medium` | `high` |
| `codex` | `exec-critic` | effort | `xhigh` | `max` |
| `codex` | `frontend-fidelity` | effort | `high` | `xhigh` |
| `codex` | `indexer` | effort | `medium` | `high` |
| `codex` | `language-detector` | effort | `medium` | `high` |
| `codex` | `load-tester` | effort | `xhigh` | `max` |
| `codex` | `modeler` | effort | `high` | `xhigh` |
| `codex` | `optimizer` | effort | `high` | `xhigh` |
| `codex` | `orchestrator` | effort | `high` | `xhigh` |
| `codex` | `plan-critic` | effort | `high` | `xhigh` |
| `codex` | `planner` | effort | `medium` | `high` |
| `codex` | `reverse-engineer` | effort | `xhigh` | `max` |
| `codex` | `sca-java` | effort | `low` | `medium` |
| `codex` | `sca-mobile` | effort | `low` | `medium` |
| `codex` | `sca-npm` | effort | `low` | `medium` |
| `codex` | `security-code-review` | effort | `high` | `xhigh` |
| `codex` | `security-code-review-global` | effort | `max` | `max` |
| `codex` | `security-orchestrator` | effort | `high` | `xhigh` |
| `codex` | `security-remediation` | effort | `medium` | `high` |
| `codex` | `security-sca` | effort | `medium` | `high` |
| `codex` | `seo-specialist` | effort | `high` | `xhigh` |
| `codex` | `skills-resolver` | effort | `medium` | `high` |
| `codex` | `terraform-deployer` | effort | `xhigh` | `max` |
| `gemini` | `analyzer` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `board-reporter` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `communicator` | model | `gemini-3.5-flash` | `gemini-3.5-flash` |
| `gemini` | `custom-docs-curator` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `design-review` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `dev-mono` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `dev-multi` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `documenter` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `exec-critic` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `frontend-fidelity` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `indexer` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `language-detector` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `load-tester` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `modeler` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `optimizer` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `orchestrator` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `plan-critic` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `planner` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `reverse-engineer` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `sca-java` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `sca-mobile` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `sca-npm` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `security-code-review` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `security-code-review-global` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `security-orchestrator` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `security-remediation` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `security-sca` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `seo-specialist` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |
| `gemini` | `skills-resolver` | model | `gemini-3.5-flash` | `gemini-3.1-pro` |
| `gemini` | `terraform-deployer` | model | `gemini-3.1-pro` | `gemini-3.1-pro` |

<!-- GRID:END -->

---

## 6. Utilisation

```
python core-scripts/apply-mode.py status              # état réel vs mode enregistré, écarts listés
python core-scripts/apply-mode.py expert              # monte d'un cran le périmètre pilotable
python core-scripts/apply-mode.py restore             # revient EXACTEMENT à la capture de référence
python core-scripts/apply-mode.py restore --recapture # ré-ancre la capture sur le disque
```

**Changer l'effort ou le modèle d'un dev (défaut voyageur,
S-01M54WXT38HZ52GCMQSQ44CB5F).** Le DÉFAUT livré est `medium` sur Claude Code
pour `dev-mono` et `dev-multi`, `high` sur Claude Code pour `frontend-fidelity`
(revenu à `high` par S-01M5N24P2Y0SH6S0W0YNG3TAN6), et `high` sur Codex pour les
trois (S-01M5F3KT36B9S58WNC6T92E0BM ; la déf Copilot n'épingle aucun effort) ;
vous pouvez le changer à vos risques.
(1) Éditer `effort:` du rendu `claude` (et, s'il le faut, `model_reasoning_effort`
du rendu `codex`) dans `agents/<dev>.md`, puis `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`
(rc 2 tant qu'apply-mode est actif) ; une édition directe de
`.claude/agents/` est réécrite au rendu suivant — si Claude passe
au-dessus de Codex, `test_role_parity_and_effort_floor` rougit (codex ≥ claude) ;
Codex au-dessus de Claude passe : c'est l'écart voulu du défaut livré.
(2) Éditer la ligne du rôle dans `README.md` (lignes `dev-mono`, `dev-multi`,
`frontend-fidelity` du tableau des tiers, aujourd'hui :40/:43/:53) ET dans
`README-CLAUDE.md` (:125/:128/:138), puis COMMITTER : `test_tier_surfaces`
compare les README à la déf committée (`git show HEAD:`) et rougit sur un écart.
(3) `python core-scripts/apply-mode.py restore --recapture` (`restore` nu d'abord
si `MODEL_MODE` est monté) — sinon `test_expert_restore…` rougit.
(4) Un changement de MODÈLE édite aussi `EXPECTED_MODELS` de
`.agents/evals/test_codex_model_alignment.py`.
(5) `dev-mono` ou `dev-multi` porté à ou au-dessus d'exec-critic sur les deux
axes, et au-dessus sur un : `test_golden_transcripts` rougit (DOMINATED, voulu).
(6) `frontend-fidelity` porté au-dessus de `design-review` sur UN axe (effort ou
modèle, Claude Code ou Codex) :
`test_golden_transcripts::test_design_review_at_or_above_frontend_fidelity_on_every_axis`
rougit (voulu, décision pilote S-01M558S8VVRGHACABYMWB2C6EM) — relevez d'abord
`design-review` par les mêmes points (1) à (3), ses lignes README.md:58 et
README-CLAUDE.md:143 comprises. `apply-mode.test.sh` § 13 ne double ce filet que
sur la colonne `expert` : il rougit quand `design-review` est abaissé sous
`frontend-fidelity` en effort (Claude Code ou Codex) ou sur le modèle Claude,
jamais sur le modèle Codex, que seul le golden garde, ni quand
`frontend-fidelity` monte au-dessus d'un juge en `xhigh` (les deux plafonnent à
`max` en `expert`).
Les rosters `data/roster/` du paquet `cadre` (`src/cadre/data/roster/` ou
`.agents/vendor/cadre/data/roster/`, l'emplacement que résout `vendor_paths`)
ne concernent que le kit (la classe d'équivalence de `test_cadre_roster` saute hors kit).

Le mode appliqué est écrit **en dernier** dans `.agents/state/local/MODEL_MODE`
(une ligne, `expert`) : si une écriture échoue en cours de route, le fichier
d'état ne ment pas sur un état qui n'a pas été atteint. Au retour, ce fichier est
**supprimé** — l'absence de fichier EST l'état de référence, pas une valeur à
écrire. Ce chemin est git-ignoré (`.agents/.gitignore` ignore `state/local/`).

**Le dépôt ne se committe JAMAIS en `expert`.** Repasser par `restore` avant tout
commit — la porte de vérification, la CI et les filets de test mesurent l'arbre
de référence.

### AVERTISSEMENT — `--recapture` grave une nouvelle référence

`restore --recapture` réécrit la colonne de référence **depuis le disque**.
Lancé sur un arbre monté en `expert`, il graverait l'état monté comme nouvelle
référence : le retour en arrière deviendrait impossible, en silence.

Le script s'en défend **mécaniquement** : si `.agents/state/local/MODEL_MODE`
existe, `--recapture` est **refusé** (code 2, aucun octet écrit) avec le remède
nommé dans le message — `restore` d'abord, sans `--recapture`, puis
`restore --recapture` sur l'arbre revenu à sa référence.

**Ce que la garde ne couvre pas, et il faut le savoir :** un fichier d'état
**supprimé à la main** alors que les defs sont restées montées. Le script n'a
alors plus aucun témoin mécanique, et il ré-ancrera la référence sur un arbre
monté. Ce trou résiduel est couvert par cet avertissement **seul**. En cas de
doute : `git status --porcelain -- .claude/agents .gemini/agents .codex/agents`
avant tout `--recapture`.

### `--recapture` n'est accepté qu'avec `restore`

Il ré-ancre la colonne de **référence** ; l'associer à `expert` n'aurait aucun
sens. La combinaison est refusée par la ligne de commande (code 2, aucun octet
écrit).

---

## 7. Filets de test

- **`bash core-scripts/apply-mode.test.sh`** — découvert et joué par la porte CI
  (`core-scripts/run-bash-tests.sh` découvre tout `*.test.sh` du dépôt, et
  `core-scripts/verify.sh` l'appelle). Sort **0** avec un `SKIP` **qui nomme les
  fichiers sales** si les defs d'agents ne sont pas propres : avoir des defs
  modifiées entre un `expert` et un commit est un usage **légitime** du
  mécanisme, mais un résidu de `kill` doit rester bruyant.
- **Aucun filet `pytest` n'accompagne ce mécanisme, et c'est délibéré.** La
  source en portait un ; sa raison d'être chez elle (« la porte de test bash
  élague `.agents/` ») est **fausse ici** : notre porte joue le banc bash
  directement. Un filet joué vaut mieux que deux dont un dort. Les assertions
  que ce filet portait — comptes par hôte, absence de mot-clé `probe()`,
  relations d'ordre du § 3.5 — sont **toutes** dans le banc bash ci-dessus.

- **`python3 -m pytest .agents/evals/test_gemini_agent_schema.py`** (T-00000779) —
  le frontmatter des 35 défs Gemini LIVRÉES PAR LE KIT, jugées par leur nom et
  strictement (plus strict que gemini-cli 0.57.0, exprès), dans le SEUL dépôt du
  kit (marqueur `.agents/IS_THE_KIT`). **Portée du marqueur, bornée au canal** :
  `sync_template.py` le retire (règle `strip:`) ; une copie BRUTE de l'arbre
  l'emporte — il faut alors le supprimer (QUICK-SETUP.md § 3), sinon le filet juge
  les défs du kit chez l'adoptant. Marqueur absent, le filet
  SAUTE en le disant et ne juge RIEN — ni ses défs, ni une déf du kit qu'il a
  modifiée (décisions S-00002966, S-00003009) : leur validité se vérifie à la main,
  au chargeur réel (commande dans `GEMINI.md`).
  Copie DATÉE des 27 noms d'outils : le chargeur réel reste le témoin d'une
  montée de version.

## 8. Ce que ce mécanisme NE dit PAS

- **L'effet runtime des tiers écrits n'est pas mesuré**, et n'est pas affirmé :
  ni l'acceptation de `max` par l'hôte Claude Code ou par Codex, ni la lecture du
  jeton indicatif par `kimi` (résidu T-00000395). Les valeurs que le mécanisme
  peut écrire sont **déjà committées quelque part à HEAD**, SAUF `opus` : la
  colonne expert de la grille (§ 5) l'écrit sur l'axe `model` de défs Claude, et
  aucune déf ne le porte à HEAD (mesuré le 2026-10-11) — pour lui, même cela
  n'est pas établi. Hors cette exception, c'est la seule chose qui soit établie ;
  le filet (f) de `.agents/evals/test_juges_sans_fable.py` tient la liste des
  exceptions égale à la grille, dans les deux sens.
- **La portée de `L-00000068` n'a pas été re-mesurée sur ce dépôt** (§ 3.1).
- **`/mode` n'existe pas comme commande** sur ce dépôt, et n'est pas demandée :
  ce mécanisme est un **script**, invoqué par le pilote. Voir le commentaire
  d'arbitrage de `core-scripts/host_sync.test.sh` § 3.
