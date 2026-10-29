# Parallélisme des devs, par hôte — la table mesurée

Ce que chaque hôte du kit a MESURÉ du lancement de devs en parallèle, chacun dans son propre
worktree git. Cette table VOYAGE avec le kit ; le relevé brut d'une mesure (sous `docs/tasks/`)
ne voyage pas. Sa portée est écrite sur chaque ligne — date du statut, os-arch, version du CLI :
une ligne vaut pour le poste et la version où son statut a été établi, jamais au-delà
(L-00000079, L-00000250).

## Format

Une ligne par hôte, sept champs séparés par ` | ` après `HOTE:` :

`HOTE: <hôte> | <statut> | <date du statut> | <os-arch|—> | <version du CLI|—> | <source ou cause, une ligne> | <M1 o1,o2 ; M2 o|— ; M1-bis ok|ko|—>`

- **hôte** : `claude`, `codex`, `copilot`, `gemini`, `kimi`, `antigravity` — chacun une fois.
- **statut**, vocabulaire FERMÉ, comparé à l'ÉGALITÉ EXACTE (aucune valeur n'est le préfixe
  d'une autre) :
  - `mesure-parallele` — deux devs lancés ensemble ont tourné en même temps, chacun dans son worktree ;
  - `mesure-serie` — mesuré, et les devs se sont suivis ;
  - `pas-mesure` — aucune mesure qui tienne à ce jour, la cause le dit ;
  - `non-mesurable` — hôte présent sur le poste, sans CLI headless ;
  - `hote-absent` — hôte absent du poste de mesure.
- **date du statut** : le jour où le statut a été ÉTABLI, pas celui où la ligne a été écrite.
- **dernier champ** : recouvrements mesurés en secondes (M1, deux passages ; M2, un passage) et
  la création des worktrees par la session elle-même (M1-bis) ; `—` = non joué.

## Ce que la table commande

Un hôte `mesure-parallele` lance les devs d'une fournée en un seul message par vague, d'au plus
le `PEUT_AJOUTER` de `charge_poste.py verdict`. Tout autre statut
joue les lots en série, et la session le dit par la ligne de son hôte, préfixe
`COVERAGE DEGRADED — parallélisme des devs` — pour `pas-mesure` :
`COVERAGE DEGRADED — parallélisme des devs non mesuré sur <hôte> : lots joués en série`, la
cause restant ici. La déf orchestrator de chaque hôte porte la ligne de son statut (Antigravity :
la déf Gemini CLI ; Kimi Code : les défs Claude Code et Kimi Code). Le README des hôtes
(`README-OTHER-HOSTS.md` § Parallel devs per host) pointe vers cette table ; P4 dans
`.agents/evals/test_parallelisme_hotes.py` rougit si le renvoi manque ou devient ambigu.

## Statuts

```text
HOTE: claude | mesure-parallele | 2026-10-01 | — | — | L-00000551 (T-00001067) relate cinq worktrees PG-0043 (isolation: "worktree") créés sur la mauvaise base, pas un recouvrement temporel mesuré ; task-board SKILL, mode worktree, point 3 | M1 — ; M2 — ; M1-bis —
HOTE: codex | pas-mesure | 2026-10-14 | darwin-arm64 | 0.155.1 | aucune session lancée au 2026-10-14 | M1 — ; M2 — ; M1-bis —
HOTE: copilot | pas-mesure | 2026-10-14 | darwin-arm64 | 1.0.96 | aucune session lancée au 2026-10-14 | M1 — ; M2 — ; M1-bis —
HOTE: gemini | pas-mesure | 2026-10-14 | darwin-arm64 | 0.63.0 | facturation à l'usage (clé d'API, selectedType gemini-api-key) ; profil sandbox strict-open : node de fnm (~/.local/share/fnm) illisible | M1 — ; M2 — ; M1-bis —
HOTE: kimi | hote-absent | 2026-10-14 | darwin-arm64 | — | hôte absent du poste de mesure (which, /Applications, ~/.kimi*, fnm et npm) | M1 — ; M2 — ; M1-bis —
HOTE: antigravity | non-mesurable | 2026-10-14 | darwin-arm64 | — | présent (app 2.22.0), sans CLI headless | M1 — ; M2 — ; M1-bis —
```

Bornes, dites : la ligne `claude` cite une source qui relate des worktrees lancés ensemble, pas
un recouvrement temporel chronométré ; les causes des lignes du 2026-10-14 sont des LECTURES
(aides des CLI, octets du binaire, profil sandbox du paquet), aucune session de modèle d'un hôte
tiers n'ayant été lancée. Une mesure réelle met la ligne de son hôte à jour, avec ses chiffres.

## Le lanceur de fournée

- **Où** : `.claude/workflows/workflow-fournee.js`, qui VOYAGE chez l'adoptant avec le kit.
- **Quel hôte** : Claude Code SEUL, le seul hôte qui ait l'outil Workflow. Sur Codex, GitHub
  Copilot, Gemini CLI, Kimi Code et Antigravity, les lots d'une même fournée se jouent en
  SÉRIE, un worktree à la fois, sous la ligne de leur hôte dans la table ci-dessus.
- **Comment l'appeler** : après `tasks.py fournee <T>`, l'outil Workflow avec
  `scriptPath: .claude/workflows/workflow-fournee.js` et des `args` en JSON, tous validés avant
  le premier agent, sinon rien ne part : `base`, `label` et `grappes` obligatoires, et `bancs`
  obligatoire dans chaque grappe. `session` est le lien de la session, et c'est l'APPELANT qui le
  passe, parce qu'un script Workflow ne lit pas sa propre session ; sans lui, la ligne
  `Claude-Session` est omise des commits et le journal le dit. `repo` est facultatif : un agent
  de contexte dérive la racine par `git rev-parse --show-toplevel`, et un `repo` donné qui ne
  l'égale pas arrête tout avant le premier dev.
- **Où tournent les devs** : sur l'hôte. Aucune route vers un modèle local n'existe plus
  (décision S-01M5PCD282N11RGE73BMQK7M70) ; l'agent de contexte ne lit que la racine et les
  branches des grappes.
- **Statuts d'une grappe qui ne part pas** (une grappe porte un lot ou plus) : `args` (args
  refusés, aucun agent), `contexte` (racine illisible ou différente de `repo`, ou branche d'une
  grappe déjà présente : course interrompue, à fusionner ou retirer avant de relancer),
  `quota` (arrêt `cadre-quota`), `charge` (trois verdicts nuls
  probants de suite : le lanceur rend les grappes restantes, là où le verdict du poste de la
  SKILL kickoff part en série).
- **Ce qu'il garde** : `tasks.py retour` avant chaque fusion, le verdict du poste avant chaque
  vague, le SAST `--at HEAD` après chaque fusion (rendu, jamais bloquant : « SAST À RELIRE »), la
  revue de sécurité du diff fusionné (sautée sans fusion), et, avant tout agent, la règle de
  `bancs-mandat.sh` rejouée sur chaque mandat de dev rendu (existence des bancs exceptée).
- **Ce qui n'est PAS mesuré** :
  - (1) que les hooks PreToolUse se déclenchent sur un `agent()` de Workflow ou sur les outils
    qu'il appelle. Cela vaut pour `bancs-mandat.sh` (matcher `Agent|Task`),
    pour `safe-bash.sh` et `audit-gate.sh` (`Bash`), et pour `protect-paths.sh` (`Edit|Write`).
    Aucune garde n'est promise à l'intérieur d'un Workflow.
  - (2) l'isolation `worktree` d'un `agent()` de Workflow. La source de la ligne `claude`
    ci-dessus relate l'outil Agent (L-00000551), pas l'outil Workflow. Chaque dev la vérifie
    donc lui-même avant toute autre commande git (`git rev-parse --path-format=absolute
    --git-dir --git-common-dir` : deux chemins différents) et s'arrête au statut `stop` sinon.
  - (3) La résolution de `scriptPath` est mesurée le 2026-10-19 (S-01M5APQ7VF, f50096afe) :
    le script se résout et se charge, 0 agent. Les hooks et l'isolation d'un `agent()` restent
    NON MESURÉS.
- **Retour** : `arret` (`{statut, motif}`) dit au premier niveau tout arrêt avant le premier dev,
  même sur des args sans grappe ; un agent de fusion mort rend sa grappe DOUTEUSE (état inconnu,
  write-set relu par la revue de sécurité) ; une revue de sécurité morte rend le bloquant
  « REVUE DE SÉCURITÉ ABSENTE ».
- **Capacités perdues**, nommées dans l'en-tête du lanceur :
  - le mandat local automatique de chaque dev ;
  - l'avis du modèle local (`review_diff`) sur le diff de fusion ;
  - le démarrage du serveur du modèle local (LM Studio), propre au poste ;
  - la ligne `Co-Authored-By` figée : chaque agent suit la consigne d'attribution de son hôte ;
  - l'arrêt de quota là où `cadre-quota` n'est pas installé : le retour dit
    `quota: NON MESURÉ` ;
  - les tests ciblés d'un adoptant NON Python (`go test`, `npm test`, `mvn`…) : `tests`,
    facultatif, n'admet qu'un pytest sur des fichiers de test (décision S-01M5APP7E5) ; absent,
    la fournée ne joue que les bancs des lots, et la porte du projet couvre le reste ;
  - un chemin de write-set non ASCII ou à blanc : seuls `[A-Za-z0-9_.@+/-]` passent (aucun tel
    chemin dans le kit).
