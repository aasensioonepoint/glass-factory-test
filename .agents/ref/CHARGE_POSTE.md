# CHARGE_POSTE — contrat du verdict de parallélisme, calibré seul

Outil : `.agents/bin/charge_poste.py` (stdlib seule). Banc : `.agents/bin/test_charge_poste.py`.
Décisions pilote : S-01M4Y10HZ6Y0TAXNNK0S1VRFC1 (le poste décide de son plafond), S-01M537VBGG5RVBCF3KHFV3JMN5
(la calibration est AUTOMATIQUE, jamais une commande à lancer), S-01M54NGJ3S0NHR7BEFZY94PF7W (un plafond sous
cinq, appris ou déclaré, reste gardé : cinq n'est jamais un plancher), S-01M54W6K0CMZRZM3EJKBHBX7A8 (surcharge
modérée ⇒ BASE, sévère ⇒ min(3, BASE)). Les décisions antérieures décrivent la cadence historique
(S-01M4Y2Q1QK4AGNCSPMQ7ES126Y, deux de plus par mesure ; S-01M54B1KQ6SVNCA9ZSRPWHCCFP, base à cinq) :
S-01M56T0DBKR9Q20XRXVJBMP619 fixe BASE au repos ; S-01M56VTWNDV9VYGTS94E81GWZH et S-01M56Z5GT8VR9QSGGJYNYTPS2Z
(décisions de l'orchestrateur, la seconde affine la première) fixent le plafond partagé, et
S-01M5BSJ7PBQD79HMY19BSSBGH2 (décision de l'orchestrateur) révise sa retenue (§ 4) ; S-01M59PGM83GXXV8ZNGQ8NZFH9T
fixe l'accord rapide sous 2C/3. Plans : T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, annexe A3 (règles) et A4 (bancs) ; base à
cinq livrée par T-01M54B1SXM557Z86N1TXEJSRDE ; première vague et accord rapide : T-01M56Q23NHTEXES5CAT0A03TFJ.

Ce fichier dit ce que l'outil GARANTIT et ce qu'il NE fait PAS. Les lanceurs (kickoff, night, planning, /audit, défs
orchestrator et security-orchestrator, lanceur des fournées du kit) consomment ses lignes ; aucun ne recalcule
la règle.

## 1. Les trois commandes

| commande | qui | écrit |
|---|---|---|
| `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n> [--attendre <s>] [--poste <hôte>]` | tout lanceur, avant CHAQUE vague | un relevé + le plafond appris (§ 4) |
| `… charge_poste.py releve [--poste <hôte>]` | diagnostic, à la main | rien, aucun verrou |
| `… charge_poste.py declarer --max <M> --motif <S-…> [--poste <hôte>]` | geste du pilote, facultatif | `config_home()/parallelisme.json` |

- `--actifs` : les agents de CETTE session déjà en vol. Déclaratif : il empêche d'OUBLIER, pas de TRICHER.
- `--attendre <s>` (0 à 540) : re-mesure toutes les 30 s jusqu'à un accord ou la fin du délai. **Toute phrase
  qui cite `verdict --attendre` porte `timeout: 600000` dans la même phrase** (le Bash par défaut coupe à 120 s)
  — C33. État non inscriptible : l'attente continue tant qu'une SURCHARGE présente retient (`DOIT_REDESCENDRE_A`
  posé), car elle peut retomber ; sans surcharge, elle s'arrête d'elle-même (le verdict reste 1 à ACTIFS = 0,
  0 sinon).
- `--poste` : clé de poste ; défaut, le nom d'hôte court en minuscules (`MacBook-Pro.local` ⇒ `macbook-pro`).
  La clé réelle est poste + nombre de cœurs (`<poste>|<C>`).
- Codes de sortie : `verdict` et `releve` rendent 0 dès que leurs lignes sont imprimées, dégradées comprises ;
  2 sur un usage invalide (`--actifs` négatif, `--attendre` hors 0..540). `declarer` rend 1 sur un refus
  d'écrire (emplacement introuvable ou dans un dépôt, fichier illisible), rien n'est alors écrit.

## 2. Sortie de `verdict`

```
PLAFOND=<n> BASE=<b> SOURCE=<appris|defaut|declare|illisible|non-mesurable>
PEUT_AJOUTER=<k> DOIT_REDESCENDRE_A=<d|-> ACTIFS=<n>
CHARGE=<1m>/<5m>/<15m> C=<c> PRESSION=<1|2|4|inconnu> EDR_CPU=<x|inconnu>
CALIBRATION=<monte|descend|relache|stable|non-inscriptible> RELEVES=<k> ETAT=<ok|non-inscriptible>
```

Puis, seulement quand elles s'appliquent, des lignes `COVERAGE DEGRADED — …` (§ 6). Les avertissements
(plafond déclaré borné, fichier illisible, verrou tenu, état dans un dépôt) vont sur stderr, préfixés
`AVERTISSEMENT:`.

`SOURCE` nomme la borne qui LIE : `non-mesurable` (charge illisible), puis `illisible` (plafond.json cassé ⇒
DUR), puis `appris` (plafond appris sous DUR), puis `declare` (un M déclaré), sinon `defaut` (⌊2C/3⌋).

`BASE` imprime la base EFFECTIVE de ce verdict, celle du § 3 à la charge mesurée : sur 18 cœurs, 9 au repos et
5 hors repos.

**Côté lanceur, une sortie sans ligne `PLAFOND=` lisible** (commande tuée, rc différent de 0, sortie tronquée)
**vaut `max(0, 5 − ACTIFS)`, jamais la dernière valeur connue** — C33 ; sans borne de cœurs, le lanceur ne
connaissant pas C (§ 7). L'outil, lui, imprime toujours ses quatre lignes, même tout dégradé.

## 3. Le verdict (règles A3)

- C = `os.cpu_count()`. M = plafond déclaré pour `<poste>|<C>` s'il existe, sinon ⌊2C/3⌋.
  **UNE règle** (C46) : DUR = min(C, max(1, M)) — un M hors 1..C est borné et DIT.
- PLAFOND = min(DUR, PLAFOND_APPRIS) ; **au repos** (charges 1 ET 5 min < C/4, strict),
  BASE = max(min(5, PLAFOND), min(PLAFOND, ⌊C/2⌋)) (S-01M56T0DBKR9Q20XRXVJBMP619) ; ailleurs BASE = min(5, PLAFOND).
  Donc BASE ≥ 1 — sous cinq quand le plafond l'est (⌊2C/3⌋ sous huit cœurs, déclaré ou appris) : jamais un
  plancher (S-01M54NGJ3S0NHR7BEFZY94PF7W).
- LIBRE = PLAFOND − ACTIFS − TENU, où TENU est la retenue entre appelants du même poste (§ 4).
- **En priorité, la charge l'emporte** : 1 min > 2C/3 (strict) ou PRESSION ≥ 2 ⇒ PEUT_AJOUTER = 0 et
  DOIT_REDESCENDRE_A = BASE (surcharge modérée) ; surcharge SÉVÈRE, 1 min > C (strict) ou PRESSION 4 ⇒
  DOIT_REDESCENDRE_A = min(3, BASE) (S-01M54W6K0CMZRZM3EJKBHBX7A8).
- ACTIFS = 0 ⇒ PEUT_AJOUTER = max(0, min(BASE, LIBRE)) ; cet accord est HORODATÉ (C45).
- ACTIFS > 0 et charges 1 min ET 5 min < 2C/3 (strict) ⇒ PEUT_AJOUTER = max(0, LIBRE), sans délai entre deux
  accords ni limite de deux places ; sinon 0. À l'égalité 2C/3, 0 (S-01M59PGM83GXXV8ZNGQ8NZFH9T). Jamais négatif
  (C45).
- État non inscriptible ⇒ 1 à ACTIFS = 0, 0 sinon : les agents partent un à un (C31).
- Charge non mesurable ⇒ PLAFOND = BASE = min(5, DUR), aucune calibration. La pression, si elle se lit, retient
  D'ABORD, état inscriptible ou non : PRESSION ≥ 2 ⇒ PEUT_AJOUTER = 0 et DOIT_REDESCENDRE_A = BASE (PRESSION 4 ⇒
  min(3, BASE)). Sinon PEUT_AJOUTER = max(0, BASE − ACTIFS) (non inscriptible : 1 à ACTIFS = 0, 0 sinon).
  Ni ce repli ni celui de l'état non inscriptible ne lisent TENU (§ 7).
- PRESSION ∈ {1, 2, 4, inconnu} (C38). 1 = un Mac normal (mesuré), aucune retenue. `inconnu` ne retient rien
  et ne compte jamais comme un relevé sain pour la montée (§ 4).
- V1 : DOIT_REDESCENDRE_A < ACTIFS ⇒ aucun départ, **jamais un arrêt** d'agent en vol. L'outil rend 0 à
  toute surcharge PRÉSENTE ; la série d'un agent à la fois après TROIS attentes rendues à 0 est une règle des
  LANCEURS, jamais de l'outil (§ 7).
- **GARANTIE** : PLAFOND ≥ 1 et BASE ≥ 1. Hors surcharge PRÉSENTE, PEUT_AJOUTER à ACTIFS = 0 peut néanmoins
  valoir 0 lorsque TENU occupe le plafond : jusqu'à 300 s après des accords retenus, jusqu'à une heure après le
  dernier relevé d'une autre session vivante, ou sans borne tant qu'elle relève. Sans TENU, à ACTIFS = 0 hors
  surcharge PRÉSENTE, PEUT_AJOUTER ≥ 1.

Exemple, C = 18 et PLAFOND = 12 (DUR = ⌊2C/3⌋ = 12) : au repos 3/3, BASE = 9 et premier départ 9 ; à 5,05/5,05
(hors repos, BASE = 5) avec ACTIFS = 5 et TENU = 0, accord 7 ; à 11,99/11,99, accord 7 ; à 11,99/12,00, accord 0,
sans repli ; à 12,01 en 1 min, accord 0 et DOIT_REDESCENDRE_A = 5 (modérée, comme PRESSION 2) ; à 18,00, encore
5 ; à 18,01 ou PRESSION 4, DOIT_REDESCENDRE_A = 3 (sévère). C = 8 : PLAFOND 5, BASE 5. C = 6 : PLAFOND 4,
BASE 4. C = 4 : PLAFOND 2, BASE 2. C = 1 : 1.

**Porte de sécurité (C30, règle des lanceurs K et S, rappelée ici)** : PEUT_AJOUTER ≥ 2 ⇒ security-code-review
et security-orchestrator ensemble, `budget = max(1, PEUT_AJOUTER − 2)` (un dépassement de +1 est DIT au
rapport) ; PEUT_AJOUTER = 1 ⇒ security-code-review seul, security-orchestrator au verdict suivant ; NO-GO de
charge SEULEMENT si, à ce verdict, 1 min > 2C/3 ou PRESSION ≥ 2 — jamais parce que PLAFOND < 5. Au premier
verdict sur 18 cœurs au repos, PEUT_AJOUTER = 9 : les deux revues partent ensemble, budget 7. À C = 4 sans
fichier, le verdict rend 2 et aucun repli : la porte part, budget 1 (témoin au banc).

## 4. La calibration automatique

Aucune commande : chaque `verdict` la fait, sous un verrou `O_EXCL` (repris s'il a plus de 30 s).

- **Relevé** : (ts, ACTIFS, 1 min, 5 min, PRESSION, EDR_CPU, accordés, CLAUDE_PID, tenu) ajouté à
  `state_home()/charge_poste/releves.jsonl` ; les 500 derniers sont gardés. Chaque relevé porte les champs
  `claude_pid` (`null` pour un appelant anonyme) et `tenu` (le TENU lu à ce verdict). `CLAUDE_PID` est celui de la
  session appelante quand la variable est posée et le processus vivant ; sinon l'appelant est ANONYME. Un PID
  invérifiable (Windows) est SUPPOSÉ vivant.
  `tenu` est un entier ≥ 0 (un booléen n'en est pas un) ; un ancien relevé sans `tenu`, ou un `tenu` invalide,
  vaut 0.
- **Retenue** (TENU, accords horodatés, RETENUE_S = 300 s) : appelant identifié, TENU = Σ (actifs + garde (ci-dessous) du
  dernier relevé de chaque AUTRE session identifiée vivante, de moins d'une heure) + accords anonymes de moins
  de 300 s + max(0, accords propres de moins de 300 s − ACTIFS) ; appelant anonyme, TENU = Σ (actifs + garde
  des sessions identifiées vivantes de moins d'une heure) + max(0, accords anonymes de moins de 300 s − ACTIFS).
  L'ACTIFS d'une session identifiée ne se déduit jamais des accords anonymes. Une session dont le PID est mort,
  ou dont le dernier relevé a plus d'une heure, ne tient plus rien.
  **Les accordés d'une autre session** (S-01M5BSJ7PB, qui révise S-01M56Z5GT8) — la garde : son dernier relevé tient ses
  accordés seulement s'il a moins de 300 s ou s'il est à ACTIFS = 0, sinon 0 ; ses actifs restent tenus jusqu'à
  une heure. Ainsi les accords des autres sessions sont tenus 300 s, et un accord à ACTIFS = 0 (lanceur à vague
  bloquante, déjà borné par BASE) est tenu une heure. Un accord de tout LIBRE à ACTIFS ≥ 1 ne bloque donc plus le
  poste une heure : sur C = 18 au repos, A reçoit 11 à ACTIFS = 1 ; B, à ACTIFS = 0, reçoit 0 dans les 300 s,
  puis 9.
- **Probant** : ACTIFS ≥ 1 ET au moins 300 s après le dernier accord (FENETRE_PROBANTE_S, distincte de la
  retenue de 300 s ci-dessus) — la charge reflète alors la vague. Sans accord, aucun relevé n'est probant :
  aucune vague n'a été mesurée.
- **Saturé** (1 min > 2C/3 ou PRESSION ≥ 2) et probant ⇒ PLAFOND_APPRIS = max(1, min(PLAFOND_APPRIS, a − 1)),
  a = ACTIFS + accordés + tenu du DERNIER ACCORD, lus dans `releves.jsonl` — jamais l'ACTIFS du relevé, la charge
  1 min est en retard (C44) ; le `tenu` y compte : la saturation est celle du poste entier. `CALIBRATION=descend`.
- **Sain** (1 min ET 5 min < C/2, PRESSION = 1) et probant, à ACTIFS ≥ PLAFOND_APPRIS ⇒ +1. `monte`. Ce seuil C/2
  est celui de la MONTÉE du calibrateur, distinct du seuil 2C/3 des départs (§ 3).
- **24 h sans relevé saturé** (probant ou non) ⇒ +1 au verdict suivant, **au plus une fois par 24 h**
  (`relache_le` dans plafond.json, C43). `relache`.
- Jamais au-dessus de DUR, jamais sous 1. **La borne DUR s'applique à l'USAGE, jamais sur disque** : un
  plafond déclaré abaissé puis relevé (`declarer --max 2` puis `--max 12`) rend `PLAFOND=12 SOURCE=declare`, et
  une valeur apprise survit intacte à une déclaration plus basse. Rien d'appris (`plafond` absent ou `null`) ⇒
  le DUR du moment (initial = DUR).
- plafond.json ne se réécrit que s'il CHANGE : descente, montée, relâche, relevé saturé (il rouvre la fenêtre
  de 24 h) ou réparation. Un plafond.json illisible (JSON cassé, imbriqué sans fond, entrée absurde) ⇒ DUR, DIT
  (`SOURCE=illisible`) ; le fichier cassé est gardé sous `plafond.json.illisible`.

## 5. Où vit l'état — jamais dans un dépôt

| fichier | contenu |
|---|---|
| `state_home()/charge_poste/releves.jsonl` | les relevés (500 derniers) |
| `state_home()/charge_poste/plafond.json` | plafond appris par clé poste + C (`null` = rien d'appris), `cree_le`, `dernier_sature`, `relache_le` |
| `state_home()/charge_poste/verrou` | le verrou, le temps d'un verdict |
| `config_home()/parallelisme.json` | les plafonds déclarés par le pilote (`declarer`) |

`state_home()` et `config_home()` sont ceux de `cadre.paths` (`$CADRE_STATE_DIR` / `$CADRE_CONFIG_HOME`,
sinon XDG). Un emplacement qui tombe sous un `.git` est REFUSÉ : `verdict` ne l'écrit pas (état non
inscriptible) et ignore une déclaration qui s'y trouve ; `declarer` refuse d'écrire. Un HOME lui-même
versionné par git rend donc l'état non inscriptible — posez `CADRE_STATE_DIR` hors de lui.

Retour arrière : effacer `state_home()/charge_poste/` (et `config_home()/parallelisme.json` s'il existe).

## 6. Couverture par plateforme

| plateforme | charge | pression | EDR | état |
|---|---|---|---|---|
| darwin-arm64 | MESURÉ (`os.getloadavg` ; repli `sysctl -n vm.loadavg`, virgule ou point) | MESURÉ (`kern.memorystatus_vm_pressure_level`, 1 sur un Mac normal) | MESURÉ (`ps -Ao pcpu=,comm=` sous `LC_ALL=C`) | MESURÉ |
| Codex, bac à sable `:workspace` | — | — | — | MESURÉ au plan (Codex 0.155.1 `-P :workspace`) : non inscriptible ⇒ un à un |
| Linux | ASSUMÉ (`os.getloadavg`, `/proc/loadavg`) | ASSUMÉ (`/proc/pressure/memory` : full avg10 ≥ 10 ⇒ 4, some avg10 ≥ 10 ⇒ 2 ; repli MemAvailable < 5 % ⇒ 4, < 10 % ⇒ 2) | ASSUMÉ | ASSUMÉ |
| Windows | `non-mesurable` | `inconnu` | `inconnu` | ASSUMÉ |
| Gemini, bac à sable Claude Code | NON MESURÉ | NON MESURÉ | NON MESURÉ | NON MESURÉ |

EDR, liste FERMÉE comparée au début du nom de l'exécutable : `com.jamf.protect`, `JamfProtectAgent`,
`JamfDaemon`, `zdp` (mesurés) ; `falcond`, `sentineld`, `wdavdaemon` (NON MESURÉS). Un seul découpage par
ligne `ps` (les chemins portent des espaces), virgule décimale tolérée. INFO seulement : l'EDR n'entre pas
dans la règle, sa charge se lit déjà dans la charge 1 min.

Lignes de dégradation imprimées par l'outil :
- `COVERAGE DEGRADED — charge du poste non mesurable sur Windows` (ou sur la plateforme nommée) ;
- `COVERAGE DEGRADED — état de charge non inscriptible : agents un à un`.

## 7. Bornes — ce que l'outil ne fait pas

- `COVERAGE DEGRADED — redescente active non livrée (V1) : à la surcharge, aucun départ ; les agents en vol
  finissent`. Ce « aucun départ » est celui de l'outil ; la sortie des lanceurs est la puce suivante. La
  surveillance continue et la descente active sont la V2 (T-01M537RYERF2ZBHGZBWXR6T7Q4).
- Au-dessus de 2C/3 ou à pression mémoire ≥ 2, aucun départ — sauf, après TROIS attentes de suite rendues
  à 0, un agent à la fois sous `COVERAGE DEGRADED — poste surchargé après trois attentes` (kickoff,
  night, planning, planning-all) ; le lanceur des fournées rend `charge` (AGENTS.md § ÉCONOMIE DE LA MACHINE, décision
  S-01M545PF3V). Après trois attentes rendues à 0 à cause de TENU, ce secours peut lancer un agent sous « poste
  surchargé » sans surcharge réelle et dépasser le plafond partagé ; ce dépassement est dit.
- Un lanceur dont la vague bloque le tour (kickoff, night, planning, planning-all) n'appelle `verdict` qu'à
  ACTIFS = 0 : chaque vague reçoit max(0, min(BASE, LIBRE)), soit neuf sur 18 cœurs au repos lorsque TENU = 0
  (cinq hors repos) ; deux vagues à moins de 300 s : la seconde reçoit min(BASE, PLAFOND − accord précédent) —
  9, 3, puis 0 sur PLAFOND 12 au repos. Sans agent actif au relevé, sa propre calibration probante ne monte
  pas (probant : ACTIFS ≥ 1) ; seul le lanceur des fournées mesure aussi les agents en vol. Capacité perdue : la calibration
  probante de ces lanceurs.
- **Moyenne 1 min tardive** : sous 2C/3, LIBRE est accordé d'un coup, et la charge 1 min ne montre la vague
  qu'après son lancement. Le dépassement transitoire de 2C/3 est ACCEPTÉ (S-01M59PGM83GXXV8ZNGQ8NZFH9T) ; les
  filets sont la coupure > 2C/3 et `DOIT_REDESCENDRE_A`, qui retiennent les départs suivants ; aucun agent en vol
  n'est arrêté.
- **Calibrateur sous LIBRE** : un accord de tout LIBRE porte a ≈ PLAFOND ; à chaque saturation probante,
  PLAFOND_APPRIS = a − 1 peut donc descendre de 1 par cycle, jamais sous 1 ; la montée saine et la relâche de
  24 h le rendent.
- Cinq sans mesure, et sans borne de cœurs là où C manque : charge non mesurable : min(5, DUR, plafond appris) sans mesure ;
  nombre de cœurs inconnu : DUR = 5, sans borne de cœurs — un poste de deux cœurs dont `os.cpu_count()` échoue
  reçoit cinq. Le repli des lanceurs sur une sortie illisible, `max(0, 5 − ACTIFS)` (§ 2), n'a pas de borne de
  cœurs non plus. Cinq n'est jamais un plancher : un plafond appris ou déclaré sous cinq le tient — sauf à C
  inconnu, où aucune clé `<poste>|<C>` n'est lisible (S-01M54NGJ3S0NHR7BEFZY94PF7W).
- **Accord d'un lanceur à vague bloquante tenu une heure** (résidu de S-01M5BSJ7PB) : un accord à ACTIFS = 0
  d'une autre session reste tenu jusqu'à une heure après son relevé, même si elle n'en lance qu'une partie, puis
  se tait — sur C = 18 au repos, A reçoit 9 à ACTIFS = 0 ; B, à ACTIFS = 0, reçoit 3 jusqu'à t3599, puis 9 à
  t3600. Ce surcompte est prudent (moins de départs, jamais plus) ; il est borné par BASE et par la vie d'une
  heure, et s'éteint à la mort du PID.
- ACTIFS est celui d'UNE session. TENU (§ 4) lit les actifs des AUTRES sessions identifiées dont le dernier
  relevé a moins d'une heure, et leurs accordés 300 s (une heure quand ce relevé est à ACTIFS = 0) ; les accords
  anonymes de moins de 300 s sont retenus séparément. Le
  plafond partagé a au moins ces six trous (L-00000187), les quatre premiers mesurés au plan sur C = 18,
  PLAFOND = 12 :
  - **sous-agent au PID du principal** : un sous-agent hérite du `CLAUDE_PID` du `claude` principal et se lit
    comme la même session ; ses accords propres sont déduits de SES ACTIFS, pas de ceux du principal — deux
    appelants au même PID, ACTIFS = 3 puis ACTIFS = 2, reçoivent 9 puis 3 : 17 en vol pour un plafond de 12, malgré la retenue ;
  - **appelant anonyme** (Codex sans session) : compté par ses accords de moins de 300 s, jamais par ses agents
    en vol — anonyme ACTIFS = 3 reçoit 9, puis Claude ACTIFS = 0 reçoit 3 : 15 en vol pour un plafond de 12 ;
  - **PID réutilisé, relevé remplacé** : surcompte prudent (moins de départs, jamais plus) ;
  - **accords propres non encore en vol** : à t120, ACTIFS = 6 après 9 + 3 accordés, max(0, propres − ACTIFS)
    retient encore 6 places jusqu'à 300 s ;
  - **replis sans TENU** : la charge non mesurable et l'état non inscriptible (§ 3) ne lisent pas TENU, chaque
    session reçoit son repli seule — non mesurable, max(0, BASE − ACTIFS) : ACTIFS = 0 et TENU = 12 reçoit
    encore 5 (mesuré sur `decider` de `charge_poste.py`) ; non inscriptible, 1 à ACTIFS = 0 dans chaque session ;
  - **accord lancé sans nouveau relevé** (envers de S-01M5BSJ7PB) : une session à ACTIFS ≥ 1 qui lance tout
    son accord sans relever de nouveau dans les 300 s n'est plus comptée que par ses actifs du dernier relevé —
    A, ACTIFS = 1, reçoit 11 et les lance ; B reçoit 9 à t301 : 21 en vol pour un plafond de 12 ; une fournée 9 puis 3, puis
    B à t400 reçoit 3 : 15 en vol pour un plafond de 12 — le lanceur des fournées relève avant chaque vague, jamais après la
    dernière. Le filet est la coupure > 2C/3 ; aucun agent en vol n'est arrêté.
  `CLAUDE_PID` sous l'outil Workflow et sous `claude -p` : NON MESURÉ.
- Une charge étrangère (une compilation du pilote) peut faire descendre le plafond appris ; la montée saine
  et la relâche de 24 h le rendent, jamais sous 1.
- Deux reprises simultanées du même verrou périmé (plus de 30 s) ne sont pas départagées : fenêtre étroite,
  un verrou n'étant tenu que le temps d'une lecture et de deux écritures.
- `--attendre` n'est pas mesuré sous l'outil Workflow.
