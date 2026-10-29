#!/usr/bin/env python3
"""DOCS-ONLY SCOPE — mesure APRÈS écriture de la route docs-only (T-00000356).

Décision pilote S-00002152 (option B) : AUCUNE porte avant l'écriture du
`documenter` sur la route « Docs-only request », une mesure DÉTERMINISTE après.
Ce script est cette mesure. Il est exécuté par la SESSION APPELANTE (celle qui
porte le shell et `Task`) — jamais par l'orchestrateur (aucun shell) ni par le
`documenter` (mesuré, jamais mesureur) :

    git --no-replace-objects rev-parse HEAD:.agents/bin/docs_only_scope.py
        -> SCOPE_BLOB, gardé dans le contexte de la session avec HEAD_SNAP.
    git --no-replace-objects cat-file blob <SCOPE_BLOB>
        | python3 -I -S - snapshot --state <fichier HORS du dépôt>
        -> imprime `SNAPSHOT <sha256>` ; la session garde ce digest dans SON
           contexte, jamais dans un fichier (le documenter a `Write` partout).
    git --no-replace-objects cat-file blob <SCOPE_BLOB>
        | python3 -I -S - check --state <fichier>
        --digest <sha256> --declared <chaque chemin de DOCS UPDATED>
        -> une ligne `<BUCKET>\\t<chemin>` par chemin, puis `PATHSPEC\\t<chemin>`
           (seulement si rc 0), puis `RESULT\\trc=<n>`. `--declared` est le
           DERNIER argument : tout ce qui le suit est un CHEMIN, jamais une
           option (`--help` et `--` déclarés sortent `DECLARED-OUT`, rc 1),
           lu HORS d'argparse (qui retirait `--` sous Python 3.9, même de
           `--declared=--`). Un `--declared` répété est un séparateur, jamais
           un chemin (`--declared a --declared b` déclare a et b : l'UNION des
           passes) ; `--declared` nu, ou absent, ne déclare rien — jamais
           `''`, qui est un chemin hors liste.

rc 0 : rien hors liste. rc 1 : au moins un chemin hors liste, non déclaré, ou déjà sale au snapshot — rien
n'est commité. rc 2 : mesure impossible (état illisible ou falsifié, autre dépôt, HEAD réécrit, racines
surveillées changées pendant la fenêtre, surface de contrôle git changée, drapeau d'index posé ou fichier qu'il
cache écrit, le script lui-même commité pendant la fenêtre, membre de contrôle ou exécutable caché illisible ou
remplacé pendant sa lecture au snapshot, lien vers un dossier sous un arbre de pytest (hors `.venv/` et `venv/`,
que pytest élague avant de suivre), dossier que git ne peut ouvrir (`chmod 311` ou `111`) hors des racines
surveillées, git en échec ou au-delà de 300 s, arguments invalides) — toujours une ligne `ERROR` puis
`RESULT\\trc=2`, argparse compris.

ATTRIBUTION PAR AUTEUR. Le `documenter` DÉCLARE ses chemins (`DOCS UPDATED`),
`--declared` les compare à ce qui a changé. Un chemin est CHANGÉ s'il est sale
maintenant avec une empreinte différente du snapshot, ou sale au snapshot et
propre maintenant SANS être dans `HEAD_snap..HEAD` (un retour arrière est une
écriture). Un dépôt imbriqué ou un sous-module sale a une empreinte CONSTANTE
(`DIR`) qui ne peut rien montrer : il est donc TOUJOURS changé, et jamais dans
la liste ni signalé (`git add` y poserait un gitlink). Le domaine est :
sales au snapshot ∪ sales maintenant ∪ `git diff --name-only HEAD_snap HEAD` ∪
fichiers des racines surveillées ACTIVES au snapshot (voir BORNES), comparées
en casse EXACTE — celle que le parcours ouvre.

Buckets (classés sur le `realpath` relatif au dépôt, casse repliée ; « dans la
liste » et « signalé » exigent en plus que le chemin APPARENT le soit — un lien
neuf hors liste qui pointe dans `docs/` reste hors liste) :
  DECLARED-IN          déclaré, dans la liste                         rc 0, seul contenu du PATHSPEC
  DECLARED-MIXED       déclaré, dans la liste, DÉJÀ sale au snapshot   rc 1 (un commit par pathspec
                       d'un tronçon que ni HEAD_snap ni HEAD ne       balaierait un tronçon étranger
                       portent                                        non commité)
  DECLARED-OUT         déclaré, hors liste (ou hors dépôt)             rc 1
  UNDECLARED-IN        dans la liste, non déclaré                      rc 1
  SIGNALED             non déclaré, TASKS/SPECS/LEDGER ou `runs/`      rc 0, listé avec empreintes
  OUT                  tout autre changé non déclaré, index compris    rc 1
  COMMITTED-EXOGENOUS  dans HEAD_snap..HEAD (commité pendant la        rc 0, listé ; réécrit APRÈS
                       fenêtre)                                       ce commit, il est classé EN
                                                                      PLUS comme tout chemin changé
  DECLARED-UNSEEN      déclaré, dans la liste, inchangé                rc 0, hors PATHSPEC
  WATCHED-IGNORED      fichier d'une racine surveillée active changé   rc 0, listé avec empreintes

Aucun seau rc 0 ne porte SEUL un fichier de contrôle git (`.gitignore`,
`.gitattributes`, `.gitmodules`, `.mailmap` — `GIT_CONTROL_BASENAMES`, sur le
realpath OU le chemin apparent, casse repliée) écrit, changé ou commité dans
la fenêtre : ni SIGNALED ni WATCHED-IGNORED ne le prennent (il sort OUT),
COMMITTED-EXOGENOUS garde sa ligne et OUT / DECLARED-OUT s'y ajoute, rc 1 ;
déclaré sans être écrit, il sort DECLARED-OUT (T-00000811, décision pilote
S-00003181 : une exception étroite à S-00002367, parce qu'un fichier de
contrôle commité CACHE sans se nommer). Un exécutable (`EXEC_SUFFIXES`) n'est
ni SIGNALED ni WATCHED-IGNORED non plus ; commité, lui se nomme dans sa
propre ligne et reste COMMITTED-EXOGENOUS, rc 0 — sauf un exécutable ignoré
LISTÉ au snapshot (P2) qu'un `git add -f` commité dans la fenêtre fait suivre :
sorti du listage, il sort AUSSI OUT, rc 1.

Liste (S-00002152) : `README*` à la racine, `docs/**` hors `docs/tech/**`, aucun
`CHANGELOG*`. RESSERREMENT fail-closed, non écrit par le plan et mesuré sans
effet ici (0 chemin suivi concerné sur 306, le 2026-09-24) : est HORS liste un
nom hors ASCII imprimable, portant un caractère de pathspec (`* ? [ ] \\`, `:`
initial), un métacaractère shell (`$`, backtick, `'`, `"`, `;`, `|`, `&`, `<`,
`>`, `(`, `)`, `{`, `}`, `!`, `#`, `~`, `^`) ou un blanc — sans quoi le
PATHSPEC que la session recopie dans `git add -- …` / `git commit -- …`
pourrait glober un fichier non déclaré ou EXÉCUTER une substitution (mesuré par
le binôme de clôture avant ce resserrement : `docs/$(touch PWNED).md` déclaré
sortait au PATHSPEC, rc 0), ou la sortie ligne à ligne être forgée.

BORNES, écrites pour ne pas être relues comme une garantie :
  * elle n'EMPÊCHE aucune écriture, et ne tourne que si l'appelant la lance ;
  * elle ne voit que le NON commité : un commit pendant la fenêtre sort
    `COMMITTED-EXOGENOUS`, rc 0, listé — hors fichier de contrôle git, qui
    sort EN PLUS OUT / DECLARED-OUT, rc 1 ;
  * elle surveille aussi `.claude/settings.local.json` (hooks, permissions),
    listé `WATCHED-IGNORED` sans bloquer S'IL EST GITIGNORÉ au snapshot
    (S-00002194 — rc 0, jamais rc 1 : Claude Code l'écrit lui-même quand le
    pilote clique « ne plus demander ») ; suivi (ou non ignoré), `git status`
    le voit et un changement sort OUT, rc 1 (S-00002195) ; son statut changé
    pendant la fenêtre rend la mesure impossible, rc 2. Le marqueur de la
    route de dev locale n'est plus surveillé depuis le retrait de cette route.
    Tout AUTRE chemin gitignoré reste invisible, hors fichier de contrôle ignoré
    (P1) et hors exécutable ignoré (P2) — liste NON close
    (`.env`, config MCP locale…) ; la protection à l'écriture est portée par
    T-00000750 ;
  * un parent lien symbolique (`.claude/`, `.agents/`, `.agents/state/`,
    `.agents/state/local/`) fait sortir CHAQUE snapshot en rc 2 (`git
    check-ignore` rc 128, « au-delà d'un lien symbolique » — mesuré sur les
    quatre le 2026-09-25) : aucune ligne `SNAPSHOT`, donc la route n'est pas
    praticable sur un tel arbre, et le documenter n'est pas invoqué ;
  * une racine surveillée qui est elle-même un lien symbolique — ou un lien
    sous elle, dossier ou fichier — (ex. `.agents/state/events` → ailleurs,
    `events/sub` → ailleurs, `binome/T-1.critic-opus.json` → ailleurs) fait
    sortir snapshot ET check en rc 2 : une écriture À TRAVERS le lien ne
    change pas son empreinte `LINK:<cible>` (mesuré par le binôme de clôture
    sur e54ef888 pour une racine, sur 2f82708d pour un lien sous elle :
    écriture par le lien, rc 0 muet — une trace de binôme forgée passait) ;
  * un fichier NON RÉGULIER (FIFO, socket, périphérique) sous une racine
    surveillée fait sortir snapshot ET check en rc 2 en le nommant : `git
    hash-object` l'attendrait sans fin (mesuré par le binôme de clôture sur
    52665124 : snapshot bloqué, timeout 124). Une racine FICHIER remplacée par
    une FIFO (`VERIFY_STAMP`) aussi — elle était sautée, `after=ABSENT` (binôme
    sur 2bfc424b). Un chemin SUIVI remplacé par une FIFO est listé par `git
    status` et refusé de même (rc 2 — il pendait, binôme sur 2bfc424b) ; une
    FIFO non suivie n'apparaît pas à `git status`, donc hors des racines elle
    n'est ni vue ni lue. Toute commande git est bornée à 300 s (rc 2) ;
  * un dossier illisible sous une racine surveillée (`chmod 000`) fait sortir
    snapshot ET check en rc 2 en le nommant — `os.walk` le sautait en silence
    (binôme sur 2bfc424b) ; un dossier ou un fichier DISPARU pendant le
    parcours aussi, dit « vanished during the walk » et jamais « unreadable »
    (binôme sur 14205a22+25bdbf4f) ;
  * le fichier d'état qui est un lien symbolique (même pendant) ou un fichier
    non régulier (FIFO) fait sortir snapshot ET check en rc 2, et le snapshot
    refuse aussi un fichier d'état à plusieurs liens durs : ouvert sur son
    realpath, le lien était SUIVI et sa cible tronquée puis réécrite, et la
    FIFO attendue sans fin (binôme sur 14205a22+25bdbf4f, mesuré) ;
  * un fichier surveillé qui est un lien (ex. `.claude/settings.local.json`,
    gitignoré, lié vers des dotfiles) arrête toute la route docs-only sur ce
    poste (rc 2, dès le snapshot) : fail-closed choisi, la cible n'est pas
    mesurée ;
  * depuis T-00000757 le script s'exécute depuis SON blob de HEAD (`git
    --no-replace-objects cat-file blob <SCOPE_BLOB> | python3 -I -S -`),
    jamais depuis l'arbre de travail : le réécrire pendant la fenêtre ne
    change plus la mesure ; ce que la forme blob NE ferme PAS : l'interpréteur,
    git et leurs arbres d'installation (`-S` neutralise un `.pth`, pas la
    stdlib), un processus laissé en vie par le mesuré, les hooks de l'hôte qui
    exécutent des scripts suivis PENDANT la fenêtre ;
  * les motifs d'ignore et les attributs sont tenus depuis T-00000811 par
    deux règles. P1 : un fichier de contrôle git (`.gitignore`,
    `.gitattributes`, `.gitmodules`, `.mailmap`, realpath OU chemin apparent,
    casse repliée) écrit, changé ou commité dans la fenêtre, ignoré ou
    visible, sort TOUJOURS rc 1 (OUT, ou DECLARED-OUT s'il est déclaré) ;
    déclaré sans être écrit, il sort DECLARED-OUT. P2 (T-00000816) : dans
    TOUT le dépôt, chaque exécutable IGNORÉ (`EXEC_SUFFIXES`, plus `.pyc`) est
    listé au snapshot et empreint fichier par fichier, hors `node_modules/` et
    hors `.py`/`.pyc` sous `.venv/` ou `venv/` (pytest les y saute ; un `.sh`
    y reste listé), noms à casse EXACTE (j) ; au check, tout chemin neuf,
    changé ou disparu sort OUT (ou DECLARED-OUT), sans attribution — la base
    est le snapshot. Ce que ces règles laissent, écrit :
    (a) FERMÉE par T-00000816 et le refus rc 2 de S-00004298 : un exécutable que cache un fichier de contrôle
        changé est listé comme tout exécutable ignoré — NOMMÉ OUT — là où git ouvre son dossier ; un dossier que
        git ne peut ouvrir (`chmod 311`/`111` : git le saute en rc 0, l'import le traverse) sort rc 2 en le nommant,
        hors des racines surveillées (dedans, leur parcours le refuse) ; reste BORNÉ : ce refus lit l'avertissement
        « could not open directory » de git sous `LC_ALL=C` (git 2.55, POSIX) — un git qui le tait le rouvre ;
    (b) FERMÉE de même : un exécutable écrit sous une règle d'ignore DÉJÀ présente au snapshot (`__pycache__/`,
        `.agents/state/local/`) est listé : OUT ; son dossier rendu illisible à git sort rc 2 (borne de (a)) ;
    (c) un exécutable commité dans la fenêtre sous `docs/**` reste COMMITTED-EXOGENOUS, rc 0 (S-00002367), sauf
        l'exécutable ignoré listé au snapshot (P2) qu'un `git add -f` commité fait suivre, qui sort AUSSI OUT, rc 1 ;
    (d) un `.gitattributes` écrit dans la fenêtre peut désigner un pilote
        `clean` déjà configuré, et le check l'EXÉCUTE : `git hash-object
        --stdin-paths` de `fingerprints` sur CHAQUE chemin qu'elle reçoit
        (neufs ou changés, fichiers des racines surveillées même inchangés,
        chemins masqués par un drapeau d'index), et `git status` sur les
        entrées d'index « racily clean » ; P1 refuse la ligne (OUT, rc 1),
        pas l'exécution ;
    (e) les suffixes listés sont ceux d'`EXEC_SUFFIXES` et `.pyc`, seuls ;
    (f) FERMÉE par T-00000816 : un dépôt git imbriqué ignoré DÉJÀ présent, où qu'il soit (un `.git` planté dans
        un `__pycache__/`, S-00004281), est listé comme UNE entrée dossier et PARCOURU : un `.py`/`.sh`/`.pyc`
        écrit dedans sort OUT, y compris dans les worktrees d'agents (`.claude/worktrees/*`) ; tout autre suffixe
        y reste muet (rc 0) — une session concurrente qui y écrit un exécutable fait sortir le check OUT, faux
        rouge fail-closed ; créé dans la fenêtre, il sort OUT ;
    (g) non mesuré (aucun arbre d'adoptant relevé) : un `.py` ou un `.sh`
        ignoré qu'un build d'adoptant régénère sous `docs/**` (un arbre
        `docs/_build/`, une sortie sphinx-gallery) sort OUT à chaque
        régénération dans la fenêtre, rc 1 — un faux rouge fail-closed, pas un
        trou ;
    (h) `RUNNER_TREES` copie `testpaths` du KIT (chez l'adoptant, la porte joue chaque module :
        `porte_adoptant.py`) ; un lien vers un dossier hors d'eux, sous `.venv/` ou `venv/` (que pytest élague
        avant de suivre), DANS un dépôt imbriqué, ou VISIBLE non suivi déjà présent au snapshot, n'est pas vu ;
    (i) un `.pyc` régénéré dans la fenêtre (le `pytest` du `documenter`, un `python3` nu, un enfant lancé en `-E`/`-I`,
        `post-edit-check.sh` hors route ; `pyrun.sh`, `pyrun.ps1` et les hooks du banc `test_event_emitters_bytecode_1191.py` n'en
        écrivent plus, T-00001191), ou un `.sh` qu'un `pip install` écrit sous `.venv/`, sort OUT, rc 1 : faux rouge fail-closed ;
        un exécutable ignoré ILLISIBLE, n'importe où, arrête CHAQUE snapshot, rc 2 nommé `hidden:<chemin>` ; un dossier illisible
        sous `node_modules/` (exclu du listage) ou `.venv/` (`.py`/`.pyc` seuls exclus), que `git ls-files` ouvre quand même
        (mesuré sous `node_modules/`), arrête de même CHAQUE snapshot, rc 2 nommé (borne de (a)) : faux rouge permanent chez un
        adoptant (cache d'un autre utilisateur, volume Docker) ; remède des deux : le rendre lisible ou le retirer ;
    (j) non listés : autres suffixes, `.so`, `.pth`, ni un `.py`/`.pyc` sous un dossier `.venv/` ou `venv/`,
        ni rien sous `node_modules/` — noms EXACTS, en minuscules, ceux que pytest (`fnmatch`) et
        run-bash-tests.sh (`find -name`) sautent : un `Venv/` ou `Node_Modules/` est listé ; sous Windows
        pytest replie la casse (`normcase`) : un `Venv/` peuplé y sort OUT, faux rouge fail-closed, non mesuré.
        L'exclusion tient aux DÉFAUTS `norecursedirs` de pytest 9 (`venv`, `.*`) et à sa détection
        `pyvenv.cfg` : un adoptant qui les remplace sans `venv` ni `.*` n'est pas couvert (non mesuré). Un
        `.py`/`.pth` sous `.venv/` reste exécuté au démarrage de l'interpréteur du venv : hors périmètre
        (découverte des runners), déjà nommé sur la ligne de route. Un `.pyc` VISIBLE déclaré sous `docs/**`
        reste DECLARED-IN ;
    (k) la mesure NOMME un exécutable caché, elle ne l'ôte pas et n'empêche pas un runner de l'exécuter : il
        reste sur le disque jusqu'à la clause RESTORE ou au pilote, et un `pytest` ou `run-bash-tests.sh` joué
        sur l'arbre vivant avant ce retrait l'exécute (`verify.sh --at` joue un clone propre : non) ;
  * `status`, `diff` nu, `ls-files -v`, `ls-files -o -i --exclude-standard` et
    `check-ignore` EXÉCUTENT `core.fsmonitor` dès le premier appel (git 2.55,
    mesuré) : ce script les appelle TOUS sous `-c core.fsmonitor=false -c
    core.untrackedCache=false` ; `rev-parse`, `cat-file`, `config --list`,
    `merge-base`, `diff` à deux révisions, `hash-object`, `ls-tree`,
    `for-each-ref` et `log A..B` n'en dépendent pas. Chaque appel porte aussi
    `GIT_NO_REPLACE_OBJECTS=1` : une ref `refs/replace/` ne substitue rien de
    ce qu'il lit (T-00000757) ;
  * la SURFACE DE CONTRÔLE git est NOMMÉE et comparée AVANT tout appel git qui
    exécute (`status`, et `hash-object`, qui applique un filtre `clean`) :
    familles `hooks`, `config`, `info`, `excludes`, `replace`, `alternates` ;
    un membre changé pendant la fenêtre sort rc 2 en le nommant
    `<famille>:<chemin relatif au dépôt>` (absolu hors du dépôt). `info` =
    QUATRE membres nommés (`info/exclude`, `info/attributes`,
    `info/sparse-checkout`, `info/grafts`), chacun résolu par son propre
    `--git-path` (`info/sparse-checkout` est PAR WORKTREE) ; `info/refs` est
    exclu (un `git gc` le crée). `excludes` = les fichiers d'exclusion et
    d'attributs EFFECTIFS (`core.excludesFile`, `core.attributesFile`, défaut
    sous `$XDG_CONFIG_HOME/git/` puis `~/.config/git/`) — liste bornée, non
    close —, empreints par `lstat` : un non-régulier porte son TYPE (un lien,
    sa cible et ce qu'elle contient), jamais un refus — sauf un membre
    illisible ou remplacé pendant sa lecture au snapshot (`CHANGED-TYPE`,
    `:UNREADABLE`), qui sort rc 2 en le nommant, avant d'écrire l'état. Une ref
    `refs/replace/` PRÉSENTE au snapshot sort rc 2 immédiatement, avant
    d'écrire l'état ;
  * dossier de hooks portant un sous-répertoire ou un lien (husky
    `.husky/_/`, lefthook, pre-commit) → rc 2, route morte sur cet hôte,
    fail-closed choisi ;
  * l'empreinte couvre tous les scopes de config, PAR CLÉ : une écriture
    globale/système pendant la fenêtre sort rc 2 et nomme ses clés — RENDUES,
    sous-section hachée, valeur jamais imprimée (la clé brute ne quitte jamais
    le parseur : une sous-section `url.<base>` ou `credential.<url>` peut
    porter un credential). Le préfixe `GIT_HARDENING` ajoute à CHAQUE
    empreinte de config deux clés constantes sous l'origine `command line:`
    (`core.fsmonitor`, `core.untrackedcache`) : identiques au snapshot et au
    check, elles s'annulent dans `control_changes` et n'y sont jamais nommées ;
  * un chemin SUIVI que cache un drapeau d'index (`--skip-worktree`,
    `--assume-unchanged`) est invisible à `git status` : un drapeau posé ou
    retiré pendant la fenêtre sort rc 2, et un tel chemin écrit aussi ; un
    fichier de contrôle git NON suivi et ignoré (`.claude/commands/.gitignore`
    = `*`), neuf ou changé, entre au domaine et sort OUT, jamais DECLARED-IN ;
    le script lui-même commité pendant la fenêtre sort rc 2 (T-00000757) ;
  * un suffixe exécutable (`.py`, `.sh`) sous `README*` ou `docs/**` n'est
    JAMAIS DOCS-ONLY valide, sur le realpath comme sur le chemin apparent :
    déclaré → DECLARED-OUT, écrit sans être déclaré → OUT, quand `git status`
    le voit OU que le listage du dépôt le liste, ignoré (P2) — hors ces deux
    canaux il n'est pas vu (T-00000757, T-00000811) ;
  * la liste inclut les plans approuvés (`docs/tasks/**`, tenus par leur
    empreinte à /kickoff et /night), `docs/specs/**` (avalé par specs-sync
    sans garde) et la spec PLAN_CIBLE (`docs/PROMPT-refonte-packaging-cadre.md`)
    — résidu conservé par décision pilote S-00002195 ;
  * un tronçon étranger écrit PENDANT la fenêtre dans un fichier `docs/**`
    que le documenter déclare sort `DECLARED-IN` et part dans le commit —
    inséparable par construction (mesure après, S-00002152) ;
  * `SIGNALED` ne distingue pas une écriture non déclarée du documenter d'un
    lot concurrent sur un store (résidu accepté, S-00002179).

STDLIB SEULE, aucun import du kit. N'écrit que le fichier d'état désigné par
`--state`, et refuse qu'il soit dans le dépôt, un lien, un fichier non régulier
ou un fichier à plusieurs liens durs — tronqué seulement APRÈS ce contrôle.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import json
import os
import re
import stat
# La surface de contrôle (T-00000757) lit les types de fichier par SA liaison :
# MUT12 du banc substitue `stat` par un `S_ISREG` constant, qui ne vise que le
# garde non-régulier du domaine mesuré.
import stat as _stat
import subprocess
import sys
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

RC_OK = 0
RC_OUT = 1
RC_ABORT = 2

STATE_VERSION = 5

# Borne de toute commande git : au-delà, mesure impossible (rc 2), jamais une
# attente sans fin (binôme sur 2bfc424b : `git hash-object` sur une FIFO).
GIT_TIMEOUT_S = 300
# Un nom d'objet git : SHA-1 (40) ou SHA-256 (64, `extensions.objectFormat`).
# `head` d'un état relu part en ARGUMENT git : il est validé avant (revue
# sécurité S-00002313, advisory).
OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")

# --- La liste (S-00002152). Comparaisons casse-repliée, séparateur `/`. ---
ALLOW_ROOT_BASENAME_PREFIX = "readme"
ALLOW_TREE_PREFIX = "docs/"
ALLOW_EXCLUDED_TREE_PREFIX = "docs/tech/"
ALLOW_FORBIDDEN_BASENAME_PREFIX = "changelog"
# Resserrement fail-closed (voir le docstring) : jamais dans la liste.
# Pathspec (`* ? [ ] \`) + métacaractères shell + espace : le PATHSPEC est
# recopié par la session dans une commande shell (binôme de clôture, classe 1).
ALLOW_FORBIDDEN_CHARS = frozenset("*?[]\\$`'\";|&<>(){}!#~^ ")

# --- Résidu SIGNALÉ (S-00002179) : listé, jamais commité par la route. ---
SIGNALED_EXACT = (".agents/state/board/TASKS.json", ".agents/state/specs/SPECS.json",  # + forme ENREGISTREMENT
                  ".agents/state/specs/SPECS.jsonl", ".agents/state/memory/LEDGER.json")  # (T-01M4KKMY43ZKCW1YD2Y8JX9MKH)
SIGNALED_PREFIXES = ("runs/", ".agents/state/board/tasks/", ".agents/state/board/epics/",
                     ".agents/state/memory/entries/")
# `.agents/state/index/` n'est PAS signalé : il tombe dans OUT (rc 1).

# --- Racines gitignorées surveillées par PARCOURS EXPLICITE : `git status`
# ne les voit jamais (`.agents/.gitignore:2`, `.gitignore:23`). ---
WATCHED_IGNORED_ROOTS = (
    ".agents/state/local/binome/",
    ".agents/state/local/plan/",
    ".agents/state/local/VERIFY_STAMP",
    ".agents/state/local/VERIFY_STAMP.log",
    ".agents/state/events/",
)
# --- Surveillées SEULEMENT si gitignorées au snapshot (S-00002194, puis
# S-00002195 option b) : suivies ou non ignorées, `git status` les voit et un
# changement sort OUT, rc 1 — jamais avalé en WATCHED-IGNORED. Ignorées sur ce
# dépôt par `.claude/.gitignore:1`. ---
WATCHED_IF_IGNORED = (
    ".claude/settings.local.json",
)
# Sondé par `git check-ignore`, jamais surveillé : garde le rc 2 d'un parent lien (S-01M5PCD282N11RGE73BMQK7M70).
SONDE_PARENT_LIEN = ".agents/state/local/.sonde-parent-lien"

BUCKET_RC = {
    "DECLARED-IN": RC_OK,
    "DECLARED-MIXED": RC_OUT,
    "DECLARED-OUT": RC_OUT,
    "UNDECLARED-IN": RC_OUT,
    "SIGNALED": RC_OK,
    "OUT": RC_OUT,
    "COMMITTED-EXOGENOUS": RC_OK,
    "DECLARED-UNSEEN": RC_OK,
    "WATCHED-IGNORED": RC_OK,
}

FP_CLEAN = "CLEAN"
FP_ABSENT = "ABSENT"
FP_DELETED = "DELETED"
FP_DIR = "DIR"

# --- T-00000757 : préfixe de CHAQUE appel git du script. `status`, `diff` nu,
# `ls-files -v`, `ls-files -o -i --exclude-standard` et `check-ignore`
# EXÉCUTENT `core.fsmonitor` dès le premier appel (git 2.55, mesuré) ; la ligne
# de commande l'emporte sur tout scope de config. ---
GIT_HARDENING = ("-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false")

# --- T-00000757 : SURFACE DE CONTRÔLE git, NOMMÉE par famille et comparée
# AVANT tout appel git qui exécute. L'ordre est celui des membres de la ligne
# ERROR ; la clause RESTORE des orchestrateurs porte un geste par famille. ---
CONTROL_FAMILIES = ("hooks", "config", "info", "excludes", "replace", "alternates")
# Quatre membres NOMMÉS, jamais un balayage : `info/refs` est exclu par
# construction (un `git gc` le crée : repack → update-server-info).
INFO_MEMBERS = ("info/exclude", "info/attributes", "info/sparse-checkout", "info/grafts")
ALTERNATES_MEMBERS = ("objects/info/alternates", "objects/info/http-alternates")
# Empreinte des valeurs d'une clé de config : jointes par NUL (jamais présent
# dans une valeur git ; une jointure nue ou par `\n` collisionne :
# [".githooks"] = [".git", "hooks"]). Une clé SANS valeur (`[x] flag`,
# booléen implicite) porte une sentinelle qu'aucune sortie décodée ne peut
# porter : `surrogateescape` ne rend que U+DC80..U+DCFF, jamais U+D800.
CONFIG_VALUE_SEP = "\0"
CONFIG_NO_VALUE = "\ud800"
# Le script lui-même : commité pendant la fenêtre, la mesure est impossible.
SCOPE_SCRIPT = ".agents/bin/docs_only_scope.py"
# Suffixes qu'un runner de la porte DÉCOUVRE et exécute (`pytest.ini`
# `python_files = test_*.py`, `run-bash-tests.sh` `-name '*.test.sh'`) :
# jamais DOCS-ONLY, sous `README*` comme sous `docs/**` (T-00000757). L'OUT
# d'un tel chemin vient de `git status`, ou, ignoré, du listage du dépôt
# `ignored_zone_exec` (T-00000811, étendu à tout le dépôt par T-00000816).
EXEC_SUFFIXES = (".py", ".sh")
# Fichiers de contrôle git : écrits, changés ou commités dans la fenêtre, ils
# disent à git ce qu'il voit (ignore, attributs, sous-modules, identités) —
# jamais DOCS-ONLY, sur le realpath comme sur le chemin apparent, et aucun seau
# rc 0 ne les porte seuls (T-00000811).
GIT_CONTROL_BASENAMES = (".gitignore", ".gitattributes", ".gitmodules", ".mailmap")
# Une glob PAR membre, dérivée : un nom ajouté à la liste est listé sans
# seconde copie ; `icase` : `.GITIGNORE` est le même fichier sur un FS replié.
TREE_CONTROL_GLOBS = tuple(f":(glob,icase)**/{name}" for name in GIT_CONTROL_BASENAMES)
# `testpaths` de pytest.ini : pytest y suit un lien vers un dossier et y parcourt un dépôt imbriqué (T-00000816).
RUNNER_TREES = (".agents/", ".codex/", ".gemini/", "agentic_v3/")
LISTED_SUFFIXES = (*EXEC_SUFFIXES, ".pyc")  # `.pyc` : listé, jamais `is_executable`
# Ce que `ignored_zone_exec` liste : TOUT le dépôt × suffixes listés, plus tout fichier ignoré des arbres (un lien
# vers un dossier n'a pas de suffixe) ; hors `node_modules` (élagué par pytest et run-bash-tests.sh) et, pour
# `.py`/`.pyc`, hors `.venv`/`venv` (élagués par pytest). Positifs `icase`, exclusions EXACTES : pytest (`fnmatch`)
# et run-bash-tests.sh (`find -name`) apparient ces noms à casse exacte — `Venv/` est collecté, donc listé.
VENV_DIRS, VENV_SKIPPED = (".venv", "venv"), (".py", ".pyc")
_EXCLUDE_EXACT = ":(exclude,glob)"
RUNNER_EXEC_PATHSPECS = (
    *(f":(glob,icase)**/*{suffix}" for suffix in LISTED_SUFFIXES),
    *(f":(glob,icase){tree}**" for tree in RUNNER_TREES),
    f"{_EXCLUDE_EXACT}**/node_modules/**",
    *(f"{_EXCLUDE_EXACT}**/{d}/**/*{s}" for d in VENV_DIRS for s in VENV_SKIPPED),
)


class Abort(Exception):
    """Mesure impossible — rc 2, rien n'est commité."""


@dataclass(frozen=True)
class PathFacts:
    """Ce que la mesure sait d'un chemin du domaine (entrée PURE de `classify`)."""

    path: str  # chemin git apparent, `/` — ce que porte le PATHSPEC
    key: str | None  # realpath relatif au dépôt, casse repliée ; None = hors dépôt
    shown: str  # realpath relatif au dépôt (casse d'origine), ou `path` si hors dépôt
    changed: bool
    committed_exogenous: bool
    foreign_at_snapshot: bool  # sale au snapshot, empreinte != blob de HEAD_snap ET != blob de HEAD
    watched: bool
    before: str
    after: str
    # Fichier NON suivi et ignoré que la mesure liste elle-même, neuf, changé ou
    # disparu : fichier de contrôle git (`GIT_CONTROL_BASENAMES`) ou exécutable de
    # la zone (P2, T-00000811) — jamais dans la liste ni signalé, il sort OUT (ou
    # DECLARED-OUT), rc 1.
    ignored_gitignore: bool = False


@dataclass(frozen=True)
class Declared:
    raw: str
    key: str | None
    shown: str


@dataclass(frozen=True)
class Row:
    bucket: str
    shown: str
    path: str
    before: str = ""
    after: str = ""


# ---------------------------------------------------------------- pur


def _fold(s: str) -> str:
    return s.casefold()


def in_allowlist(key: str | None) -> bool:
    """`README*` racine, `docs/**` hors `docs/tech/**`, aucun `CHANGELOG*`."""
    if not key:
        return False
    if key.startswith(":") or any(c in ALLOW_FORBIDDEN_CHARS for c in key):
        return False
    if any(not (0x20 <= ord(c) < 0x7F) for c in key):
        return False
    base = key.rsplit("/", 1)[-1]
    if base.startswith(ALLOW_FORBIDDEN_BASENAME_PREFIX):
        return False
    if "/" not in key and base.startswith(ALLOW_ROOT_BASENAME_PREFIX):
        return True
    excluded = ALLOW_EXCLUDED_TREE_PREFIX
    if key == excluded.rstrip("/") or key.startswith(excluded):
        return False
    return key.startswith(ALLOW_TREE_PREFIX)


def is_executable(*keys: str | None) -> bool:
    """Vrai si UNE des clés, casse repliée, finit par un suffixe de `EXEC_SUFFIXES`.

    Testé sur le realpath ET sur le chemin apparent : un lien `README.test.sh ->
    docs/a.md` déclaré passait `DECLARED-IN` et `git commit -- README.test.sh`
    commitait le lien (T-00000757, M22)."""
    return any(_fold(k).endswith(EXEC_SUFFIXES) for k in keys if k)


def is_git_control(*keys: str | None) -> bool:
    """Vrai si UNE des clés, casse repliée, a pour dernier composant un nom de
    `GIT_CONTROL_BASENAMES` — realpath ET chemin apparent, comme `is_executable` :
    un lien `docs/.gitignore -> a.md` écrit À TRAVERS son nom, et un lien
    `docs/alias.md -> real/.gitignore` écrit À TRAVERS sa cible (T-00000811)."""
    return any(_fold(k).rsplit("/", 1)[-1] in GIT_CONTROL_BASENAMES for k in keys if k)


def is_signaled(key: str | None) -> bool:
    if not key:
        return False
    if key in {_fold(p) for p in SIGNALED_EXACT}:
        return True
    return any(key.startswith(_fold(p)) for p in SIGNALED_PREFIXES)


def under_watched(path: str, roots: Sequence[str]) -> bool:
    """Casse EXACTE (binôme de clôture, critic-opus F2) : `walk_watched` ouvre
    la casse exacte, donc un repli ici retirait `.claude/Settings.local.json`
    de `git status` sans que le parcours le voie — disparu sans trace sur un
    système de fichiers sensible à la casse."""
    for root in roots:
        if root.endswith("/"):
            if path.startswith(root):
                return True
        elif path == root:
            return True
    return False


def allowed_roots() -> frozenset[str]:
    """Toute racine qu'un état peut porter : les fixes + les conditionnelles."""
    return frozenset(WATCHED_IGNORED_ROOTS) | frozenset(WATCHED_IF_IGNORED)


def classify(facts: Sequence[PathFacts], declared: Sequence[Declared]) -> tuple[list[Row], list[str], int]:
    """Buckets, PATHSPEC et rc. PUR : aucun accès disque ni git."""
    declared_keys = {d.key for d in declared if d.key is not None}
    matched: set[str] = set()
    rows: list[Row] = []
    pathspec: list[str] = []
    for f in facts:
        is_declared = f.key is not None and f.key in declared_keys
        # Le chemin APPARENT (celui que porte le PATHSPEC) ET son realpath doivent
        # être dans la liste : sinon un lien neuf `.claude/x -> ../docs/a.md`
        # déclaré passerait IN et `git commit -- .claude/x` le commiterait.
        apparent = _fold(f.path)
        # Un dépôt imbriqué ou un sous-module (empreinte `DIR`) n'est JAMAIS
        # dans la liste ni signalé : `git add -- docs/sub/` y poserait un
        # gitlink, pas un document — il sort toujours OUT / DECLARED-OUT, rc 1.
        nested = not f.watched and FP_DIR in (f.before, f.after)
        # T-00000757 : un exécutable qu'un runner découvre (realpath OU chemin
        # apparent) et un `.gitignore` ignoré ne sont JAMAIS dans la liste.
        # T-00000811 : un fichier de contrôle git non plus, et aucun des deux
        # n'est SIGNALED ni WATCHED-IGNORED — ces seaux rc 0 ne les portent pas.
        refused = is_executable(f.key, apparent) or is_git_control(f.key, apparent)
        listed = (
            in_allowlist(f.key)
            and in_allowlist(apparent)
            and not nested
            and not f.ignored_gitignore
            and not refused
        )
        signaled = is_signaled(f.key) and is_signaled(apparent) and not nested and not f.ignored_gitignore and not refused
        if f.committed_exogenous:
            if is_declared:
                matched.add(f.key)  # type: ignore[arg-type]
            rows.append(Row("COMMITTED-EXOGENOUS", f.shown, f.path))
            # Réécrit APRÈS le commit tiers (passe 2 sur un fichier qu'un
            # `commit -a` a emporté) : listé ET classé comme tout chemin changé.
            # Un fichier de contrôle commité CACHE sans se nommer : il sort
            # AUSSI OUT / DECLARED-OUT, rc 1 (T-00000811, décision S-00003181).
            if not f.changed and not is_git_control(f.key, apparent):
                continue
        elif not f.changed:
            continue
        if is_declared:
            matched.add(f.key)  # type: ignore[arg-type]
            if not listed:
                rows.append(Row("DECLARED-OUT", f.shown, f.path))
            elif f.foreign_at_snapshot:
                rows.append(Row("DECLARED-MIXED", f.shown, f.path))
            else:
                rows.append(Row("DECLARED-IN", f.shown, f.path))
                pathspec.append(f.path)
        elif f.watched and not refused:
            rows.append(Row("WATCHED-IGNORED", f.shown, f.path, f.before, f.after))
        elif signaled:
            rows.append(Row("SIGNALED", f.shown, f.path, f.before, f.after))
        elif listed:
            rows.append(Row("UNDECLARED-IN", f.shown, f.path))
        else:
            rows.append(Row("OUT", f.shown, f.path))
    seen: set[str] = set()
    for d in declared:
        ident = d.key if d.key is not None else "\0" + d.raw
        if ident in seen:
            continue
        seen.add(ident)
        # T-00000757 : un exécutable DÉCLARÉ mais non écrit sort aussi DECLARED-OUT ;
        # T-00000811 : un fichier de contrôle git aussi (realpath OU chemin déclaré).
        if d.key is None or not in_allowlist(d.key) or is_executable(d.key, _fold(d.raw)) or is_git_control(d.key, _fold(d.raw)):
            if d.key is None or d.key not in matched:
                rows.append(Row("DECLARED-OUT", d.shown, d.raw))
        elif d.key not in matched:
            rows.append(Row("DECLARED-UNSEEN", d.shown, d.raw))
    rows.sort(key=lambda r: (r.shown, r.bucket))
    rc = max((BUCKET_RC[r.bucket] for r in rows), default=RC_OK)
    return rows, sorted(set(pathspec)), rc


def digest_matches(raw: bytes, digest: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest.strip().lower())


def _ascii(s: str) -> str:
    """Une ligne, ASCII imprimable : tout le reste est échappé (anti-forge)."""
    if all(0x20 <= ord(c) < 0x7F and c != "\\" for c in s):
        return s
    return s.encode("unicode_escape").decode("ascii").replace("\t", "\\t")


def render(rows: Iterable[Row], pathspec: Sequence[str], rc: int) -> list[str]:
    out = []
    for r in rows:
        line = f"{r.bucket}\t{_ascii(r.shown)}"
        if r.path != r.shown:
            line += f"\tvia={_ascii(r.path)}"
        if r.bucket in ("SIGNALED", "WATCHED-IGNORED"):
            line += f"\tbefore={_ascii(r.before)}\tafter={_ascii(r.after)}"
        out.append(line)
    if rc == RC_OK:
        out.extend(f"PATHSPEC\t{_ascii(p)}" for p in pathspec)
    out.append(f"RESULT\trc={rc}")
    return out


# ---------------------------------------------------------------- git / disque


def _git(args: Sequence[str], cwd: str, *, stdin: bytes | None = None, ok: tuple[int, ...] = (0,),
         whole: Sequence[str] | None = None) -> subprocess.CompletedProcess:
    # T-00000757 : `-c core.fsmonitor=false -c core.untrackedCache=false` sur CHAQUE appel, `GIT_NO_REPLACE_OBJECTS=1` ;
    # messages avec `args[0]`. `whole` (S-00004298), sous LC_ALL=C : un dossier non ouvert hors de ces racines -> rc 2.
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1", LC_ALL="C")
    try:
        cp = subprocess.run(
            ["git", *GIT_HARDENING, *args], cwd=cwd, input=stdin, capture_output=True, check=False, env=env,
            timeout=GIT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise Abort(f"git {args[0]} timed out") from exc
    except OSError as exc:
        raise Abort(f"git unavailable: {exc.__class__.__name__}") from exc
    if cp.returncode not in ok:
        raise Abort(f"git {args[0]} failed rc={cp.returncode}")
    for e in [] if whole is None else [x for x in os.fsdecode(cp.stderr).splitlines() if "could not open directory" in x]:
        if not ((m := re.fullmatch(r"warning: could not open directory '(.+)/': [^']*", e)) and under_watched(m[1] + "/", whole)):
            raise Abort(f"git {args[0]} could not open directory: {_ascii(m[1] if m else e)}")
    return cp


def _split_z(raw: bytes) -> list[str]:
    return [os.fsdecode(x) for x in raw.split(b"\0") if x]


def git_toplevel(cwd: str) -> str:
    cp = _git(["rev-parse", "--show-toplevel"], cwd)
    top = os.fsdecode(cp.stdout).strip()
    if not top:
        raise Abort("not inside a git work tree")
    return os.path.realpath(top)


def git_head(top: str) -> str:
    return os.fsdecode(_git(["rev-parse", "--verify", "HEAD"], top).stdout).strip()


def dirty_paths(top: str) -> list[str]:
    raw = _git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], top, whole=()).stdout
    entries = raw.split(b"\0")
    paths: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        xy = entry[:2]
        paths.append(os.fsdecode(entry[3:]))
        if b"R" in xy or b"C" in xy:
            if i < len(entries) and entries[i]:
                paths.append(os.fsdecode(entries[i]))
            i += 1
    return paths


def _is_regular(full: str, p: str) -> bool:
    try:
        return stat.S_ISREG(os.lstat(full).st_mode)
    except OSError as exc:
        raise Abort(f"file unreadable in the measured domain: {p}") from exc


def fingerprints(top: str, paths: Iterable[str]) -> dict[str, str]:
    """Empreinte `git hash-object` (sans `-w`) ; lien -> `LINK:<cible>` ; un NON-RÉGULIER (FIFO, socket,
    périphérique) est REFUSÉ, rc 2 : `git hash-object` l'attendrait sans fin (binôme sur 2bfc424b) ; une racine
    FICHIER surveillée non régulière l'est ici (`walk_watched` la transmet)."""
    out: dict[str, str] = {}
    batch: list[str] = []
    for p in paths:
        full = os.path.join(top, p)
        if os.path.islink(full):
            out[p] = "LINK:" + os.readlink(full)
        elif not os.path.lexists(full):
            out[p] = FP_DELETED
        elif os.path.isdir(full):
            out[p] = FP_DIR
        elif not _is_regular(full, p):
            raise Abort(f"non-regular file in the measured domain: {p}")
        elif "\n" in p or "\r" in p:
            cp = _git(["hash-object", "--", p], top)
            out[p] = os.fsdecode(cp.stdout).strip()
        else:
            batch.append(p)
    if batch:
        payload = b"".join(os.fsencode(p) + b"\n" for p in batch)
        cp = _git(["hash-object", "--stdin-paths"], top, stdin=payload)
        shas = os.fsdecode(cp.stdout).split()
        if len(shas) != len(batch):
            raise Abort("git hash-object returned an unexpected count")
        out.update(zip(batch, shas))
    return out


def active_roots(top: str) -> tuple[str, ...]:
    """Les racines fixes + celles de `WATCHED_IF_IGNORED` que git ignore MAINTENANT.

    `git check-ignore` consulte l'index : un fichier SUIVI n'en sort jamais,
    même quand un motif le couvre (mesuré le 2026-09-25) — il reste alors dans
    le domaine de `git status`, et un changement sort OUT, rc 1 (S-00002195).
    Un parent lien symbolique fait échouer git (rc 128) : mesure impossible —
    `SONDE_PARENT_LIEN` (statut ignoré sans effet) en couvre `.agents/state/local/`.
    """
    payload = b"".join(os.fsencode(p) + b"\0" for p in (*WATCHED_IF_IGNORED, SONDE_PARENT_LIEN))
    cp = _git(["check-ignore", "-z", "--stdin"], top, stdin=payload, ok=(0, 1))
    ignored = set(_split_z(cp.stdout))
    return tuple(WATCHED_IGNORED_ROOTS) + tuple(p for p in WATCHED_IF_IGNORED if p in ignored)


def _gone_or_unreadable(exc: OSError) -> str:
    # critic-opus 4 (binôme sur 14205a22+25bdbf4f) : un chemin DISPARU pendant le parcours sortait « unreadable »
    # — cause fausse. Partagé par `walk_watched` et la marche des dépôts imbriqués (`_listed_paths`, T-00000816).
    return "vanished during the walk" if isinstance(exc, FileNotFoundError) else "unreadable"


def walk_watched(top: str, roots: Sequence[str]) -> dict[str, str]:
    """Parcours EXPLICITE et récursif des racines actives, indépendant du gitignore. REFUSÉS, rc 2 : une racine
    lien (son `LINK:<cible>` ne voit rien d'écrit À TRAVERS elle, e54ef888), un lien SOUS une racine (2f82708d),
    un fichier NON RÉGULIER (FIFO, 52665124 F5), un dossier illisible (`onerror`, T6) ; une racine qui n'est pas
    un dossier part TELLE QUELLE à `fingerprints`, qui refuse un non-régulier (2bfc424b T1)."""

    def _unreadable(exc: OSError) -> None:
        rel = os.path.relpath(exc.filename or top, top).replace(os.sep, "/")
        raise Abort(f"watched directory {_gone_or_unreadable(exc)}: {rel}")

    files: list[str] = []
    for root in roots:
        full = os.path.join(top, root.rstrip("/"))
        if os.path.islink(full):
            raise Abort(f"watched root is a symbolic link: {root}")
        if os.path.isdir(full):
            for dirpath, dirnames, filenames in os.walk(full, onerror=_unreadable, followlinks=False):
                dirnames.sort()
                # `os.walk` range un lien vers un dossier dans `dirnames` (sans y
                # descendre) et un lien vers un fichier, ou cassé, dans `filenames`.
                for name in sorted(dirnames + filenames):
                    if os.path.islink(os.path.join(dirpath, name)):
                        rel = os.path.relpath(os.path.join(dirpath, name), top).replace(os.sep, "/")
                        raise Abort(f"symbolic link inside a watched root: {rel}")
                for name in sorted(filenames):
                    path = os.path.join(dirpath, name)
                    rel = os.path.relpath(path, top).replace(os.sep, "/")
                    # Après le test de lien : `lstat` ne suit rien. Un fichier qui
                    # disparaît entre le parcours et ce test rend la mesure
                    # impossible (rc 2), jamais une trace Python.
                    try:
                        mode = os.lstat(path).st_mode
                    except OSError as exc:
                        raise Abort(f"watched file {_gone_or_unreadable(exc)}: {rel}") from exc
                    if not stat.S_ISREG(mode):
                        raise Abort(f"non-regular file inside a watched root: {rel}")
                    files.append(rel)
        elif os.path.lexists(full):
            files.append(root.rstrip("/"))
    return fingerprints(top, files)


def resolve_key(top: str, rel: str) -> tuple[str | None, str]:
    """(clé casse-repliée, chemin affiché) sur le REALPATH ; hors dépôt -> (None, rel)."""
    candidate = rel.replace("\\", "/")
    full = candidate if os.path.isabs(candidate) else os.path.join(top, candidate)
    real = os.path.realpath(full)
    if not _inside(top, real) or _fold(real) == _fold(top):
        return None, rel
    shown = os.path.relpath(real, top).replace(os.sep, "/")
    return _fold(shown), shown


def _inside(top: str, target: str) -> bool:
    try:
        return os.path.commonpath([_fold(top), _fold(target)]) == _fold(top)
    except ValueError:
        return False


def head_blobs(top: str, head: str, paths: Sequence[str]) -> dict[str, str]:
    """Empreinte attendue de chaque chemin dans HEAD_snap (absent -> pas de clé)."""
    if not paths:
        return {}
    raw = _git(["--literal-pathspecs", "ls-tree", "-r", "-z", "--full-tree", head, "--", *paths], top).stdout
    out: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry or b"\t" not in entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, _type, sha = meta.decode("ascii").split(" ")
        path = os.fsdecode(name)
        if mode == "120000":
            target = _git(["cat-file", "blob", sha], top).stdout
            out[path] = "LINK:" + os.fsdecode(target)
        elif mode == "160000":
            out[path] = FP_DIR
        else:
            out[path] = sha
    return out


# ---------------------------------------------------------------- surface de contrôle (T-00000757)


def _decode(raw: bytes) -> str:
    """Octets git -> texte, sans perte : `surrogateescape` rend U+DC80..U+DCFF
    pour un octet non décodable, jamais la sentinelle `CONFIG_NO_VALUE`."""
    return raw.decode("utf-8", "surrogateescape")


def _control_member(top: str, path: str) -> str:
    """Membre RENDU : relatif au dépôt s'il y est, absolu sinon, séparateur `/`."""
    full = os.path.normpath(path if os.path.isabs(path) else os.path.join(top, path))
    if _inside(top, full) and _fold(full) != _fold(top):
        return os.path.relpath(full, top).replace(os.sep, "/")
    return full.replace(os.sep, "/")


def _sha256_regular(full: str, *, follow: bool = False) -> str | None:
    """sha256 du contenu si `full` est un fichier régulier À L'OUVERTURE, sinon None
    (`O_NONBLOCK` : une FIFO substituée n'est jamais attendue). `O_NOFOLLOW` par
    défaut : un fichier régulier au `lstat`, remplacé par un lien avant
    l'ouverture, n'est jamais lu comme `FILE:<empreinte de la cible>` (binôme
    S-00003100) ; `follow=True` pour la seule branche lien de `_control_file_fp`,
    qui hache la cible À DESSEIN sous `SYMLINK:<cible>:`. Borne : `O_NOFOLLOW`
    vaut 0 sous Windows, la course y reste ouverte (comme pour `_open_state`) ;
    et `O_NOFOLLOW` ne tient que le DERNIER composant du chemin — un dossier
    parent remplacé par un lien est encore traversé."""
    try:
        fd = os.open(full, os.O_RDONLY | _NONBLOCK | _BINARY | (0 if follow else _NOFOLLOW))
    except OSError:
        return None
    try:
        if not _stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        h = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fd)


def _type_of(mode: int) -> str:
    for test, name in (
        (_stat.S_ISDIR, "DIR"),
        (_stat.S_ISCHR, "CHARDEV"),
        (_stat.S_ISBLK, "BLOCKDEV"),
        (_stat.S_ISFIFO, "FIFO"),
        (_stat.S_ISSOCK, "SOCKET"),
    ):
        if test(mode):
            return name
    return "OTHER"


def _unreadable(exc: OSError, family: str, member: str) -> Abort:
    """Le refus d'un `lstat`/`readlink` en échec : un exécutable caché du dépôt
    (famille `hidden`) se nomme comme tel ; toute autre famille, `tree:` compris,
    est un fichier de contrôle git."""
    if family == "hidden":
        return Abort(f"hidden executable unreadable ({exc.__class__.__name__}): {family}:{member}")
    return Abort(f"git control member unreadable ({exc.__class__.__name__}): {family}:{member}")


def _control_file_fp(full: str, family: str, member: str) -> str:
    """Empreinte par `lstat` (réserve R3) : régulier -> `FILE:<sha256>` ; absent -> `ABSENT` ; AUTRE TYPE -> le
    TYPE, jamais un refus (`core.excludesFile` = `os.devnull` au banc) ; un lien -> `SYMLINK:<cible>:<sha256 |
    ABSENT | TYPE | UNREADABLE>` (une écriture À TRAVERS lui se voit ; UNREADABLE = EACCES ou ELOOP, SYM-11051).
    `CHANGED-TYPE` (régulier au `lstat`, illisible ou remplacé à l'ouverture) et `:UNREADABLE` sont INSTABLES :
    `run_snapshot` refuse l'état qui en porte un (`_unstable_members`). Borne : un lien reciblé entre le readlink
    et l'ouverture sort une empreinte HYBRIDE, un rc 2 de trop au pire, jamais un rc 0 de trop."""
    try:
        st = os.lstat(full)
    except FileNotFoundError:
        return FP_ABSENT
    except OSError as exc:
        raise _unreadable(exc, family, member) from exc
    if _stat.S_ISREG(st.st_mode):
        digest = _sha256_regular(full)
        return f"FILE:{digest}" if digest else "CHANGED-TYPE"
    if _stat.S_ISLNK(st.st_mode):
        try:
            target = os.readlink(full)
        except OSError as exc:
            raise _unreadable(exc, family, member) from exc
        digest = _sha256_regular(full, follow=True)
        if digest:
            return f"SYMLINK:{target}:{digest}"
        try:
            tst = os.stat(full)
        except FileNotFoundError:
            return f"SYMLINK:{target}:ABSENT"
        except OSError:
            return f"SYMLINK:{target}:UNREADABLE"
        return f"SYMLINK:{target}:UNREADABLE" if _stat.S_ISREG(tst.st_mode) else f"SYMLINK:{target}:{_type_of(tst.st_mode)}"
    return _type_of(st.st_mode)


def _git_paths(top: str, names: Sequence[str]) -> dict[str, str]:
    """Chaque nom résolu par SON PROPRE `--git-path` : `info/sparse-checkout` est
    PAR WORKTREE (`.git/worktrees/<nom>/info/`) quand les autres membres de
    `info/` sont communs — `--git-path info` suivi d'une jointure lirait celui du
    worktree PRINCIPAL (mesuré, M26)."""
    args = ["rev-parse"]
    for name in names:
        args += ["--git-path", name]
    lines = _decode(_git(args, top).stdout).split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) != len(names):
        raise Abort("git rev-parse --git-path returned an unexpected count")
    return dict(zip(names, lines))


def render_config_key(key: str) -> str:
    """Clé RENDUE au parseur (M16) : section avant le PREMIER `.`, nom après le
    DERNIER, sous-section entre les deux — dès qu'il y a DEUX points, même vide
    (`url..insteadof`, réserve R4) — HACHÉE en 64 hex : elle peut porter un
    credential (`url.<base>`, `credential.<url>`). La clé brute ne sort jamais."""
    if key.count(".") < 2:
        return key
    section, rest = key.split(".", 1)
    subsection, name = rest.rsplit(".", 1)
    digest = hashlib.sha256(subsection.encode("utf-8", "surrogateescape")).hexdigest()
    return f"{section}.{digest}.{name}"


def _shown_config_key(rendered: str) -> str:
    """Forme de la ligne ERROR : le hash de sous-section tronqué à 12 hex."""
    if rendered.count(".") < 2:
        return rendered
    section, digest, name = rendered.split(".", 2)
    return f"{section}.{digest[:12]}.{name}"


def _config_values_digest(values: Sequence[str | None]) -> str:
    joined = CONFIG_VALUE_SEP.join(CONFIG_NO_VALUE if v is None else v for v in values)
    return hashlib.sha256(joined.encode("utf-8", "surrogatepass")).hexdigest()


def config_fingerprint(top: str, raw: bytes) -> dict[str, dict[str, str]]:
    """`git config --list --show-origin -z` (TOUS les scopes, includes compris) ->
    `{origine: {clé rendue: sha256(valeurs)}}`. Une entrée est `<origine>\\0<clé>\\n
    <valeur>\\0`, ou `<origine>\\0<clé>\\0` pour une clé sans valeur ; une clé
    multi-valuée sort une entrée par valeur (M15). Coupée au PREMIER `\\n` : une
    valeur peut en porter un, une clé jamais."""
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    if len(tokens) % 2:
        raise Abort("git config --list returned a malformed listing")
    grouped: dict[str, dict[str, list[str | None]]] = {}
    for i in range(0, len(tokens), 2):
        origin = _decode(tokens[i])
        entry = _decode(tokens[i + 1])
        key, sep, value = entry.partition("\n")
        rendered = render_config_key(key)
        if origin.startswith("file:"):
            origin = _control_member(top, origin[len("file:"):])
        grouped.setdefault(origin, {}).setdefault(rendered, []).append(value if sep else None)
    return {o: {k: _config_values_digest(v) for k, v in keys.items()} for o, keys in grouped.items()}


def _effective_file(top: str, key: str, default_name: str) -> str | None:
    """Le fichier d'exclusion ou d'attributs EFFECTIF (gitignore(5),
    gitattributes(5), git-config(1) à git 2.55 — liste bornée, non close)."""
    cp = _git(["config", "--type=path", "--get", key], top, ok=(0, 1))
    value = _decode(cp.stdout).rstrip("\n") if cp.returncode == 0 else ""
    if value:
        return value if os.path.isabs(value) else os.path.join(top, value)
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    if not base:
        home = os.environ.get("HOME") or ""
        if not home:
            return None
        base = os.path.join(home, ".config")
    return os.path.join(base, "git", default_name)


def _hooks_members(top: str, hooks_path: str) -> dict[str, str]:
    """Chaque fichier du dossier de hooks EFFECTIF (qui suit `core.hooksPath`),
    avec son bit x et son contenu. Un sous-répertoire ou un lien SOUS lui ->
    rc 2 en le nommant : route morte sur cet hôte, fail-closed choisi (husky
    `.husky/_/`, lefthook, pre-commit)."""
    full = os.path.normpath(hooks_path if os.path.isabs(hooks_path) else os.path.join(top, hooks_path))
    root = _control_member(top, full)
    out: dict[str, str] = {}
    try:
        st = os.lstat(full)
    except FileNotFoundError:
        return out
    except OSError as exc:
        raise Abort(f"git control member unreadable ({exc.__class__.__name__}): hooks:{root}") from exc
    if _stat.S_ISLNK(st.st_mode):
        out[root] = _control_file_fp(full, "hooks", root)
    if not os.path.isdir(full):
        out.setdefault(root, _control_file_fp(full, "hooks", root))
        return out
    try:
        names = sorted(os.listdir(full))
    except OSError as exc:
        raise Abort(f"git control member unreadable ({exc.__class__.__name__}): hooks:{root}") from exc
    for name in names:
        path = os.path.join(full, name)
        member = f"{root}/{name}"
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise Abort(f"git control member unreadable ({exc.__class__.__name__}): hooks:{member}") from exc
        if _stat.S_ISLNK(mode) or _stat.S_ISDIR(mode):
            raise Abort(f"git hooks directory holds a sub-directory or a link: hooks:{member}")
        fp = _control_file_fp(path, "hooks", member)
        out[member] = ("x:" if mode & 0o111 else "-:") + fp
    return out


def git_control_fingerprint(top: str) -> dict:
    """La SURFACE DE CONTRÔLE git, NOMMÉE par famille (`CONTROL_FAMILIES`) :
    tout ce qui change la façon dont git lit l'arbre ou ce qu'il exécute. Aucun
    appel ici n'exécute `core.fsmonitor` ni un filtre (`config --list`,
    `rev-parse`, `for-each-ref`)."""
    raw = _git(["config", "--list", "--show-origin", "-z"], top).stdout
    paths = _git_paths(top, ("hooks", *INFO_MEMBERS, *ALTERNATES_MEMBERS))
    families: dict[str, dict] = {"hooks": _hooks_members(top, paths["hooks"]), "config": config_fingerprint(top, raw)}
    for family, names in (("info", INFO_MEMBERS), ("alternates", ALTERNATES_MEMBERS)):
        members: dict[str, str] = {}
        for name in names:
            member = _control_member(top, paths[name])
            members[member] = _control_file_fp(os.path.join(top, paths[name]), family, member)
        families[family] = members
    excludes: dict[str, str] = {}
    for key, default in (("core.excludesFile", "ignore"), ("core.attributesFile", "attributes")):
        path = _effective_file(top, key, default)
        if path is not None:
            member = _control_member(top, path)
            excludes[member] = _control_file_fp(path, "excludes", member)
    families["excludes"] = excludes
    refs = _git(["for-each-ref", "--format=%(refname) %(objectname)", "refs/replace/"], top).stdout
    replace_refs: dict[str, str] = {}
    for line in _decode(refs).splitlines():
        name, _sp, oid = line.rpartition(" ")
        replace_refs[name] = oid
    families["replace"] = replace_refs
    return {family: families[family] for family in CONTROL_FAMILIES}


def control_changes(before: dict, after: dict) -> list[str]:
    """Les membres changés, NOMMÉS `<famille>:<membre>` dans l'ordre des familles ;
    `config:<fichier>[<clé>,…]` porte ses clés RENDUES (ajoutées, retirées ou
    changées), jamais une sous-section brute ni une valeur."""
    members: list[str] = []
    for family in CONTROL_FAMILIES:
        b, a = before.get(family, {}), after.get(family, {})
        if family == "config":
            for origin in sorted(set(b) | set(a)):
                kb, ka = b.get(origin, {}), a.get(origin, {})
                keys = sorted(k for k in set(kb) | set(ka) if kb.get(k) != ka.get(k))
                if keys:
                    members.append(f"config:{origin}[{','.join(_shown_config_key(k) for k in keys)}]")
            continue
        for member in sorted(set(b) | set(a)):
            if b.get(member) != a.get(member):
                members.append(f"{family}:{member}")
    return members


def hidden_index_flags(top: str) -> dict[str, str]:
    """Chemins SUIVIS que cache un drapeau d'index (`ls-files -v` : tag `S`
    skip-worktree ou minuscule assume-unchanged) -> empreinte disque (`ABSENT`
    s'il manque — sparse-checkout). `git status` ne les voit pas."""
    raw = _git(["ls-files", "-v", "-z"], top).stdout
    hidden: list[str] = []
    for entry in raw.split(b"\0"):
        if len(entry) < 3:
            continue
        tag = entry[:1].decode("ascii", "replace")
        if tag == "S" or tag.islower():
            hidden.append(os.fsdecode(entry[2:]))
    fps = fingerprints(top, hidden)
    return {p: FP_ABSENT if fps[p] == FP_DELETED else fps[p] for p in hidden}


def ignored_gitignores(top: str, roots: Sequence[str]) -> dict[str, str]:
    """Les fichiers de contrôle git (`GIT_CONTROL_BASENAMES`, casse repliée) NON
    suivis et ignorés (`.claude/commands/.gitignore` = `*` s'ignore lui-même) ->
    empreinte : invisibles à `git status`, ils le rendent aveugle à ce qu'ils
    couvrent. Hors des racines surveillées (déjà parcourues). Empreints par
    `_control_file_fp` (famille `tree`), jamais par `git hash-object` : aucun
    filtre `clean` ne tourne sur eux (T-00000811). Le nom est gardé : des bancs
    le visent."""
    raw = _git(["ls-files", "-o", "-i", "--exclude-standard", "-z", "--", *TREE_CONTROL_GLOBS], top, whole=roots).stdout
    return {
        p: _control_file_fp(os.path.join(top, p), "tree", p)
        for p in _split_z(raw)
        if not under_watched(p, roots)
    }


def _listed_paths(top: str, listing: Sequence[str]) -> list[str]:
    """Du listage git à ce qu'on empreint : un suffixe listé ; une entrée DOSSIER (dépôt imbriqué ignoré), gardée
    et PARCOURUE où qu'elle soit (un `.git` planté dans `__pycache__/` y cachait le `.pyc` que la porte importe,
    S-00004281) ; un lien vers un dossier sous un
    arbre, hors `.venv/` et `venv/` que pytest élague avant de le suivre (`lib64 -> lib` d'un venv Linux) : rc 2
    (pytest le suit, git ne dit pas où il mène). La marche filtre comme le listage : `.git` et
    `node_modules` élagués, `.py`/`.pyc` sautés sous un composant EXACT de `VENV_DIRS`, `.sh` gardé."""

    def _gone(exc: OSError) -> None:
        rel = os.path.relpath(exc.filename or top, top).replace(os.sep, "/")
        raise Abort(f"nested repository {_gone_or_unreadable(exc)}: {rel}")

    keep: list[str] = []
    for p in listing:
        low, full = _fold(p), os.path.join(top, p)
        in_tree = low.startswith(RUNNER_TREES)
        if p.endswith("/"):
            keep.append(p)
            for dirpath, dirnames, filenames in os.walk(full, onerror=_gone):
                dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
                rel = os.path.relpath(dirpath, top).replace(os.sep, "/")
                venv = not set(rel.split("/")).isdisjoint(VENV_DIRS)
                keep += [f"{rel}/{n}" for n in filenames
                         if _fold(n).endswith(LISTED_SUFFIXES) and not (venv and n.endswith(VENV_SKIPPED))]
        elif in_tree and set(p.split("/")).isdisjoint(VENV_DIRS) and os.path.islink(full) and os.path.isdir(full):
            raise Abort(f"symbolic link to a directory under a runner tree: {p}")
        elif low.endswith(LISTED_SUFFIXES):
            keep.append(p)
    return keep


def ignored_zone_exec(top: str, roots: Sequence[str]) -> dict[str, str]:
    """Les exécutables IGNORÉS du dépôt (`RUNNER_EXEC_PATHSPECS` : tout le dépôt × `LISTED_SUFFIXES`, plus les
    arbres de pytest) -> empreinte, fichier PAR fichier, base = le snapshot (T-00000811, T-00000816) : invisibles
    à `git status`, un runner de la porte les découvre quand même. Empreints par `_control_file_fp` (famille
    `hidden`), jamais par `git hash-object`. Le filtre des racines surveillées passe AVANT `_listed_paths`."""
    raw = _git(["ls-files", "-o", "-i", "--exclude-standard", "-z", "--", *RUNNER_EXEC_PATHSPECS], top, whole=roots).stdout
    return {
        p: _control_file_fp(os.path.join(top, p), "hidden", p)
        for p in _listed_paths(top, [q for q in _split_z(raw) if not under_watched(q, roots)])
    }


def _unstable_fp(fp: str) -> bool:
    return fp.endswith("CHANGED-TYPE") or fp.endswith(":UNREADABLE")


def _unstable_members(control: dict, gitignores: dict, ignored_exec: dict) -> list[str]:
    """Les membres dont l'empreinte ne tient pas au snapshot (`_unstable_fp`) :
    `<famille>:<membre>` (familles de contrôle hors `config` et `replace`),
    `tree:<chemin>`, `hidden:<chemin>`. Un état qui en porte un n'est pas écrit."""
    out: list[str] = []
    for family in CONTROL_FAMILIES:
        if family == "config":
            continue
        for member, fp in sorted(control[family].items()):
            if family != "replace" and _unstable_fp(fp):
                out.append(f"{family}:{member}")
    out.extend(f"tree:{p}" for p, fp in sorted(gitignores.items()) if _unstable_fp(fp))
    out.extend(f"hidden:{p}" for p, fp in sorted(ignored_exec.items()) if _unstable_fp(fp))
    return out


def _refuse_moved_control(state: dict, top: str) -> None:
    moved = control_changes(state["control"], git_control_fingerprint(top))
    if moved:
        raise Abort("git control surface changed during the window: " + ", ".join(moved))


def _refuse_hidden_writes(state: dict, top: str) -> None:
    before, after = state["hidden"], hidden_index_flags(top)
    if set(before) != set(after):
        raise Abort("index flags changed during the window: " + ", ".join(sorted(set(before) ^ set(after))))
    written = sorted(p for p in before if before[p] != after.get(p))
    if written:
        raise Abort("tracked path hidden by an index flag was written: " + ", ".join(written))


# ---------------------------------------------------------------- commandes


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_BINARY = getattr(os, "O_BINARY", 0)


def _open_state(path: str, flags: int, fail: str) -> int:
    """Ouvre le fichier d'état SANS suivre un lien final ni attendre une FIFO, puis exige, sur le descripteur
    OUVERT, un fichier régulier (critic-opus 2 sur 14205a22+25bdbf4f) : `lstat` d'abord pour nommer le refus ;
    `O_NOFOLLOW`, `O_NONBLOCK` et le `fstat` ferment la course. Aucun `O_TRUNC` : sur un LIEN DUR il tronquerait
    la victime — l'appelant tronque après."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    except OSError as exc:
        raise Abort(f"{fail}: {exc.__class__.__name__}") from exc
    if st is not None and stat.S_ISLNK(st.st_mode):
        raise Abort("state file is a symbolic link")
    if st is not None and not stat.S_ISREG(st.st_mode):
        raise Abort("state file is not a regular file")
    try:
        fd = os.open(path, flags | _NOFOLLOW | _NONBLOCK | _BINARY, 0o600)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise Abort("state file is a symbolic link") from exc
        if exc.errno == errno.ENXIO:
            raise Abort("state file is not a regular file") from exc
        raise Abort(f"{fail}: {exc.__class__.__name__}") from exc
    try:
        regular = stat.S_ISREG(os.fstat(fd).st_mode)
    except OSError as exc:
        os.close(fd)
        raise Abort(f"{fail}: {exc.__class__.__name__}") from exc
    if not regular:
        os.close(fd)
        raise Abort("state file is not a regular file")
    return fd


def run_snapshot(state_path: str) -> str:
    top = git_toplevel(os.getcwd())
    target = os.path.realpath(os.path.abspath(state_path))
    if _inside(top, target):
        raise Abort("state file inside the repository")
    head = git_head(top)
    # T-00000757 : la surface de contrôle AVANT tout appel git qui exécute ; une
    # ref de remplacement déjà là rend la fenêtre non mesurable, avant l'état.
    control = git_control_fingerprint(top)
    if control["replace"]:
        raise Abort(
            "git replace refs present at snapshot: " + ", ".join(f"replace:{r}" for r in sorted(control["replace"]))
        )
    roots = active_roots(top)
    dirty = [p for p in dirty_paths(top) if not under_watched(p, roots)]
    state = {
        "version": STATE_VERSION,
        "tool": "docs_only_scope",
        "toplevel": top,
        "head": head,
        "roots": list(roots),
        "control": control,
        "hidden": hidden_index_flags(top),
        "gitignores": ignored_gitignores(top, roots),
        "ignored_exec": ignored_zone_exec(top, roots),
        "dirty": fingerprints(top, dirty),
        "watched": walk_watched(top, roots),
    }
    # T-00000811 : une base qui ne tient pas (membre illisible ou remplacé
    # pendant la lecture) n'est jamais écrite — sinon ce membre, lu CHANGED-TYPE
    # au snapshot puis au check, se comparerait égal à lui-même.
    unstable = _unstable_members(state["control"], state["gitignores"], state["ignored_exec"])
    if unstable:
        raise Abort("git control member or hidden executable unreadable or replaced while read: " + ", ".join(unstable))
    data = (json.dumps(state, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")
    # Le chemin APPARENT, jamais `target` : ouvrir le realpath suivait le lien.
    fd = _open_state(os.path.abspath(state_path), os.O_WRONLY | os.O_CREAT, "cannot write state file")
    try:
        with os.fdopen(fd, "wb") as fh:
            if os.fstat(fh.fileno()).st_nlink > 1:
                raise Abort("state file has another hard link")
            os.ftruncate(fh.fileno(), 0)
            fh.write(data)
    except OSError as exc:
        raise Abort(f"cannot write state file: {exc.__class__.__name__}") from exc
    return hashlib.sha256(data).hexdigest()


def _flat_str_map(value: object) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def _control_shape_ok(control: object) -> bool:
    """`control` (v3) : exactement `CONTROL_FAMILIES` ; `config` porte un niveau
    de plus (origine -> clé rendue -> empreinte)."""
    if not isinstance(control, dict) or set(control) != set(CONTROL_FAMILIES):
        return False
    config = control["config"]
    return (
        isinstance(config, dict)
        and all(isinstance(o, str) and _flat_str_map(keys) for o, keys in config.items())
        and all(_flat_str_map(control[f]) for f in CONTROL_FAMILIES if f != "config")
    )


def _load_state(state_path: str, digest: str) -> dict:
    fd = _open_state(os.path.abspath(state_path), os.O_RDONLY, "state file unreadable")
    try:
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise Abort(f"state file unreadable: {exc.__class__.__name__}") from exc
    if not digest_matches(raw, digest):
        raise Abort("state digest mismatch")
    try:
        state = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Abort("state file malformed") from exc
    # Un état d'une version antérieure (sans `roots`, v1) se lisait « malformed » :
    # vrai mais muet sur la cause. Le message la NOMME sans prescrire de remède :
    # `check` tourne APRÈS le documenter, et un snapshot neuf pris à ce moment
    # avalerait ses écritures — le point (4) des lignes de routage l'interdit.
    # La fenêtre n'est pas mesurable, point. `isinstance` d'abord : un JSON qui
    # n'est pas un objet n'a pas de `.get` et reste « malformed », jamais une
    # trace Python.
    if isinstance(state, dict) and state.get("version") != STATE_VERSION:
        raise Abort(
            "state file version mismatch: snapshot taken by another version of this script,"
            " this window cannot be measured"
        )
    ok = (
        isinstance(state, dict)
        and state.get("version") == STATE_VERSION
        and isinstance(state.get("toplevel"), str)
        and isinstance(state.get("head"), str)
        and isinstance(state.get("roots"), list)
        and isinstance(state.get("dirty"), dict)
        and isinstance(state.get("watched"), dict)
        and all(isinstance(r, str) for r in state["roots"])
        and len(set(state["roots"])) == len(state["roots"])
        and set(state["roots"]) <= allowed_roots()
        and all(isinstance(k, str) and isinstance(v, str) for k, v in state["dirty"].items())
        and all(isinstance(k, str) and isinstance(v, str) for k, v in state["watched"].items())
        and _flat_str_map(state.get("hidden"))
        and _flat_str_map(state.get("gitignores"))
        and _flat_str_map(state.get("ignored_exec"))
        and _control_shape_ok(state.get("control"))
    )
    if not ok:
        raise Abort("state file malformed")
    # `head` part en argument de `git merge-base`/`diff`/`ls-tree` : un nom
    # d'objet, rien d'autre (revue sécurité S-00002313). `roots` porte des
    # CHEMINS, pas des SHA — déjà bornés à `allowed_roots()` ci-dessus ; les
    # empreintes de `dirty`/`watched` ne sont que comparées, jamais passées à git.
    if not OBJECT_ID.fullmatch(state["head"]):
        raise Abort("state file malformed: head is not an object id")
    return state


def build_facts(top: str, state: dict) -> list[PathFacts]:
    head_snap = state["head"]
    head_now = git_head(top)
    anc = _git(["merge-base", "--is-ancestor", head_snap, head_now], top, ok=(0, 1, 128))
    if anc.returncode != 0:
        raise Abort("snapshot HEAD is not an ancestor of HEAD")
    # Les racines du SNAPSHOT font foi ; si le statut ignoré d'une racine
    # conditionnelle a bougé pendant la fenêtre (`git add -f`, `.gitignore`
    # réécrit), aucune des deux lectures n'est juste : mesure impossible.
    roots: tuple[str, ...] = tuple(state["roots"])
    now_roots = active_roots(top)
    if sorted(roots) != sorted(now_roots):
        # La ou les racines en cause sont NOMMÉES : sans elles le pilote ne sait
        # pas laquelle a bougé (`git add -f`, `.gitignore` réécrit, état forgé).
        moved = ", ".join(sorted(set(roots) ^ set(now_roots)))
        raise Abort(f"watched roots changed since the snapshot: {moved}")
    diff = _git(["diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", head_snap, head_now], top)
    committed = {p for p in _split_z(diff.stdout) if not under_watched(p, roots)}
    # T-00000757 (M10) : la mesure commitée PENDANT la fenêtre — forme à DEUX
    # révisions, qui n'exécute pas `core.fsmonitor`. Le blob épinglé a mesuré ;
    # la version commitée est la mesure des fenêtres suivantes.
    if SCOPE_SCRIPT in committed:
        raise Abort("the measure itself was committed during the window")
    snap_dirty: dict[str, str] = {p: v for p, v in state["dirty"].items() if not under_watched(p, roots)}
    now_list = [p for p in dirty_paths(top) if not under_watched(p, roots)]
    now_dirty = fingerprints(top, now_list)
    blobs = head_blobs(top, head_snap, sorted(snap_dirty))
    # Un tronçon étranger sale au snapshot que son auteur a COMMITÉ pendant la
    # fenêtre n'est plus étranger au fichier : HEAD le porte (binôme de clôture).
    blobs_now = head_blobs(top, head_now, sorted(snap_dirty))
    facts: list[PathFacts] = []
    for p in sorted(set(snap_dirty) | set(now_dirty) | committed):
        in_now, in_snap = p in now_dirty, p in snap_dirty
        committed_exo = p in committed
        if in_now:
            # `DIR` (dépôt imbriqué, sous-module) est une empreinte CONSTANTE :
            # elle ne peut rien montrer, donc un tel chemin sale est toujours changé.
            changed = now_dirty[p] == FP_DIR or now_dirty[p] != snap_dirty.get(p)
        elif committed_exo:
            changed = False
        else:
            changed = in_snap  # sale au snapshot, propre maintenant, non commité
        foreign = in_snap and snap_dirty[p] != blobs.get(p) and snap_dirty[p] != blobs_now.get(p)
        key, shown = resolve_key(top, p)
        facts.append(
            PathFacts(
                path=p,
                key=key,
                shown=shown,
                changed=changed,
                committed_exogenous=committed_exo,
                foreign_at_snapshot=foreign,
                watched=False,
                before=snap_dirty.get(p, FP_CLEAN),
                after=now_dirty.get(p, FP_CLEAN),
            )
        )
    # T-00000757 (M9), T-00000811 (P1) : un fichier de contrôle git NON suivi et
    # ignoré, neuf ou changé, entre au domaine comme fait changé ; `classify` ne le
    # range jamais dans la liste.
    snap_ig: dict[str, str] = state["gitignores"]
    now_ig = ignored_gitignores(top, roots)
    known = {f.path: i for i, f in enumerate(facts)}
    for p in sorted(set(snap_ig) | set(now_ig)):
        before, after = snap_ig.get(p, FP_ABSENT), now_ig.get(p, FP_ABSENT)
        if before == after:
            continue
        if p in known:
            facts[known[p]] = replace(facts[known[p]], changed=True, ignored_gitignore=True)
            continue
        key, shown = resolve_key(top, p)
        facts.append(
            PathFacts(
                path=p,
                key=key,
                shown=shown,
                changed=True,
                committed_exogenous=False,
                foreign_at_snapshot=False,
                watched=False,
                before=before,
                after=after,
                ignored_gitignore=True,
            )
        )
    # T-00000811 (P2) : un exécutable IGNORÉ du dépôt (T-00000816), neuf, changé
    # ou disparu depuis le snapshot, fichier par fichier, sort OUT / DECLARED-OUT.
    # `known` est RECALCULÉ : un dépôt imbriqué ignoré créé dans la fenêtre est
    # listé par les DEUX listages, et sortirait sinon deux lignes OUT.
    snap_ex: dict[str, str] = state["ignored_exec"]
    now_ex = ignored_zone_exec(top, roots)
    known = {f.path: i for i, f in enumerate(facts)}
    for p in sorted(set(snap_ex) | set(now_ex)):
        before, after = snap_ex.get(p, FP_ABSENT), now_ex.get(p, FP_ABSENT)
        if before == after:
            continue
        if p in known:
            facts[known[p]] = replace(facts[known[p]], changed=True, ignored_gitignore=True)
            continue
        key, shown = resolve_key(top, p)
        facts.append(
            PathFacts(
                path=p,
                key=key,
                shown=shown,
                changed=True,
                committed_exogenous=False,
                foreign_at_snapshot=False,
                watched=False,
                before=before,
                after=after,
                ignored_gitignore=True,
            )
        )
    snap_w: dict[str, str] = state["watched"]
    now_w = walk_watched(top, roots)
    for p in sorted(set(snap_w) | set(now_w)):
        before, after = snap_w.get(p, FP_ABSENT), now_w.get(p, FP_ABSENT)
        key, shown = resolve_key(top, p)
        facts.append(
            PathFacts(
                path=p,
                key=key,
                shown=shown,
                changed=before != after,
                committed_exogenous=False,
                foreign_at_snapshot=False,
                watched=True,
                before=before,
                after=after,
            )
        )
    return facts


def run_check(state_path: str, digest: str, declared_raw: Sequence[str]) -> tuple[list[Row], list[str], int]:
    # Le confinement AVANT toute lecture de l'état (revue sécurité S-00002313) :
    # un fichier d'état DANS le dépôt n'est jamais lu, quel que soit son digest.
    top = git_toplevel(os.getcwd())
    if _inside(top, os.path.realpath(os.path.abspath(state_path))):
        raise Abort("state file inside the repository")
    state = _load_state(state_path, digest)
    if state["toplevel"] != top:
        raise Abort("repository differs from the snapshot")
    # T-00000757 : surface de contrôle, puis drapeaux d'index, AVANT `build_facts`
    # — son `git status` et son `hash-object` (filtres `clean`) exécutent.
    _refuse_moved_control(state, top)
    _refuse_hidden_writes(state, top)
    facts = build_facts(top, state)
    declared = []
    for raw in declared_raw:
        key, shown = resolve_key(top, raw)
        declared.append(Declared(raw=raw, key=key, shown=shown))
    return classify(facts, declared)


class _Parser(argparse.ArgumentParser):
    """Une erreur d'arguments sort comme toute mesure impossible : une ligne
    `ERROR`, puis `RESULT\\trc=2` — argparse n'écrivait que l'usage sur stderr,
    rc 2 sans ligne lisible (binôme sur 2bfc424b, critic-opus T5). Les
    sous-parsers en héritent : `add_subparsers` prend `type(self)` pour classe."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"ERROR\t{_ascii(message)}")
        print(f"RESULT\trc={RC_ABORT}")
        sys.exit(RC_ABORT)


DECLARED_OPT = "--declared"


def _parser() -> argparse.ArgumentParser:
    # `allow_abbrev=False` sur CHAQUE parser : un sous-parser n'hérite pas du
    # réglage, et `--dig` valait `--digest` (binôme sur 52665124, critic-opus F1).
    ap = _Parser(
        prog="docs_only_scope.py", description="Docs-only route: measure after the write (S-00002152).", allow_abbrev=False
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("snapshot", help="record the tree BEFORE the documenter call", allow_abbrev=False)
    sp.add_argument("--state", required=True, help="state file, OUTSIDE the repository")
    cp = sub.add_parser(
        "check",
        help="classify every change AFTER the documenter call",
        allow_abbrev=False,
        epilog=(
            f"{DECLARED_OPT} PATH... -- LAST argument, read OUTSIDE argparse: every token after it is a path,"
            f" never an option ('--' included); a repeated {DECLARED_OPT} is a separator, never a path;"
            f" a bare {DECLARED_OPT} declares nothing."
        ),
    )
    cp.add_argument("--state", required=True)
    cp.add_argument("--digest", required=True, help="sha256 printed by snapshot, kept by the caller")
    return ap


def _split_declared(raw: Sequence[str]) -> tuple[list[str], list[str] | None]:
    """Sur `check`, (arguments pour argparse, chemins déclarés) — la queue ouverte par le premier `--declared`
    n'est JAMAIS confiée à argparse (`--help`, `--` sous 3.9, un `--declared` répété : binôme sur 52665124).
    Un `--declared` répété — nu ou `--declared=<p>` — est un SÉPARATEUR, jamais un chemin ; un `--state` ou
    `--digest` placé après lui est un chemin (argparse refuse alors faute d'état, rc 2). Hors `check` : `None`."""
    toks = list(raw)
    if toks[:1] != ["check"]:
        return toks, None
    prefix = DECLARED_OPT + "="
    for i, tok in enumerate(toks):
        if tok == DECLARED_OPT or tok.startswith(prefix):
            declared = [tok[len(prefix):]] if tok != DECLARED_OPT else []
            for t in toks[i + 1 :]:
                if t == DECLARED_OPT:
                    continue
                declared.append(t[len(prefix):] if t.startswith(prefix) else t)
            return toks[:i], declared
    return toks, []


def main(argv: Sequence[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    head, declared = _split_declared(raw)
    args = _parser().parse_args(head)
    # `None` hors `check` ; sur `check`, jamais la lecture d'argparse.
    args.declared = declared if declared is not None else []
    try:
        if args.cmd == "snapshot":
            print(f"SNAPSHOT {run_snapshot(args.state)}")
            return RC_OK
        rows, pathspec, rc = run_check(args.state, args.digest, args.declared)
    except Abort as exc:
        print(f"ERROR\t{_ascii(str(exc))}")
        print(f"RESULT\trc={RC_ABORT}")
        return RC_ABORT
    for line in render(rows, pathspec, rc):
        print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
