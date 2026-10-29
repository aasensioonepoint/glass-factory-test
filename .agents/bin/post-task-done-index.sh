#!/usr/bin/env bash
# PostToolUse(Bash) — à la clôture d'une tâche, commiter les stores d'état (board,
# ledger, journal), puis les exports de run, puis rafraîchir l'index si possible.
#
# POURQUOI CE FICHIER VIT DANS .agents/bin/ ET NON DANS .claude/hooks/
# Il est enregistré par PLUSIEURS hôtes (Claude Code, Codex, Copilot, Kimi Code), donc le
# loger chez l'un d'eux ferait dépendre les autres d'un répertoire qui ne les
# concerne pas — un projet qui supprime `.claude/` perdrait silencieusement son
# hook Codex. `.agents/bin/` est le seul domicile qui satisfait les trois
# contraintes du kit à la fois : neutre vis-à-vis des hôtes, voisin des trois
# outils dont il commite les stores (`tasks.py`, `ledger.py`, `specs.py`), et
# déjà listé dans `.agents/protected-paths.local` chez un consommateur, donc
# protégé en écriture sans ajouter une règle (T-00000031). Un `.agents/hooks/`
# neuf y aurait été éditable par un agent.
#
# Déclencheur : la seule commande qui signifie « une tâche est terminée » dans ce
# kit est `tasks.py done`. On ne réagit donc pas à chaque Stop (qui commiterait
# à chaque tour de conversation, y compris quand rien n'a bougé) mais exactement
# à cet événement — c'est la définition de « fin de tâche valide ».
#
# CONCURRENCE RÉELLE (T-00000189, volet 1). Deux clôtures simultanées faisaient
# la course sur le commit git : mesuré 6/6 sur le code précédent, le perdant
# échouait et son échec était AVALÉ (silence total, aucune projection). Le commit
# est désormais sérialisé sous un verrou dédié `POST_TASK_DONE.lock` porté par
# `tasks.py commit-stores` (la JAMBE VERROU). Ce script porte deux autres jambes :
# la JAMBE EXTERNE (le mode normal ci-dessous, déclenché par le JSON de
# l'événement) et la JAMBE SECTION (`--commit-section <racine>`, le seul
# `status → add → commit`, lancée par la jambe verrou À L'INTÉRIEUR du verrou).
#
# Advisory : TOUJOURS exit 0, jamais de blocage — un hook qui échoue ne doit pas
# empêcher la clôture d'une tâche.
set -u

# Pathspec des exports de run : la FORME du contrat (`runs/<auteur>/<copie>/<AAAA-MM>.jsonl`)
# et rien d'autre. `:(glob)` fait que `*` ne traverse PAS `/` : un fichier plus profond,
# un `.borne.tmp`, un `events.out.tfevents.1` d'un outil tiers ne sont ni comptés ni
# commités (T-00000703, correction A2). UNE constante pour les DEUX jambes qui la
# lisent (la section et le chemin dégradé), sinon elles divergeraient en silence.
# `top` (T-00000691, S-00002557) : runs/ vit à la RACINE GIT — c'est là que
# `run_export.chemin_export` l'écrit (`project_root` = racine git) — et la jambe
# peut être appelée sur un SOUS-PROJET (monorepo, `.agents/` sous apps/foo) : un
# pathspec relatif au cwd n'y trouvait jamais runs/, les exports n'étaient jamais
# commités.
RUN_EXPORTS_SPEC=':(top,glob)runs/*/*/*.jsonl'

# Pathspec des fichiers d'intent O2 (T-00001058, S-00003918 (3), qui amende S-00003368) :
# la FORME `sync_outbox/<ordre>-<operation_id>.json`, à côté de TASKS.json, et rien
# d'autre — `:(glob)` : `*` ne traverse pas `/`, un temporaire `.tmp` n'y entre pas. Le
# retrait d'un intent acquitté part dans le MÊME commit que son ajout ou que TASKS.json.
# Ajouté au sélecteur `stores` SEULEMENT si `status` y voit quelque chose : sans
# correspondance, `git add` rend 128 et `git commit` 1 (mesuré, M8). T-00001012 a fait
# l'extension à SES fichiers : `STORE_SPECS` ci-dessous, même règle pour chaque entrée.
SYNC_OUTBOX_SPEC=':(glob).agents/state/board/sync_outbox/[0-9]*-*.json'

# LES DEUX FORMES DES MAGASINS (T-00001012, BK-419, E-26 ; pathspec ordonné par la décision
# pilote S-01M4KKMXW2ZSGFY6SW42HJJN96 et CONSOMMÉ ici — la tâche de bascule n'y revient pas).
# Le sélecteur `stores` est cette liste, et rien d'autre : les trois MONOLITHES, les intents O2,
# puis les fichiers UN PAR ENREGISTREMENT de T-00001008 — `board/tasks/T-*.json` et
# `board/epics/E-*.json` (domicile tranché par S-01M4N1G4VXD01A3W54Y9FR9856, que T-00001009
# reprend ou modifie dans le même commit), `memory/entries/L-*.json` (T-00001010),
# `specs/SPECS.jsonl` (T-00001011). `:(glob)` : `*` ne traverse pas `/` — un sous-dossier, un
# temporaire pointé (`.T-1.json`, `.tasks-….tmp`), un `.json.tmp` ou un `x.txt` n'entrent pas (M4).
# Chaque entrée n'entre au sélecteur que si `status` y voit quelque chose (règle M8 de T-00001058,
# jamais d'`add` sans correspondance) — et c'est `status`, non plus `[ -f ]`, qui VOIT la
# SUPPRESSION d'un monolithe : au commit de migration, elle part avec les enregistrements au lieu
# d'être perdue (M3 B/C). Un magasin en DEUX formes à la fois est commité tel quel, les deux ;
# le refus « deux formes » appartient à son outil (`ledger.py`, T-00001010), jamais à ce hook.
# Ce fichier est UN, partagé par Claude, Codex, Copilot et Kimi : l'extension vaut pour tous ;
# les lecteurs de SessionStart de Codex et Gemini (`session_context.py`) lisent les deux formes depuis
# T-01M4KKMY43ZKCW1YD2Y8JX9MKH (272e27cd).
STORE_SPECS=(
  .agents/state/board/TASKS.json
  .agents/state/memory/LEDGER.json
  .agents/state/specs/SPECS.json
  "$SYNC_OUTBOX_SPEC"
  ':(glob).agents/state/board/tasks/T-*.json'
  ':(glob).agents/state/board/epics/E-*.json'
  ':(glob).agents/state/memory/entries/L-*.json'
  .agents/state/specs/SPECS.jsonl
)
# Les dossiers d'enregistrements où un LIEN SYMBOLIQUE est refusé (voir la jambe `stores`).
STORE_RECORD_DIRS=(
  .agents/state/board/sync_outbox
  .agents/state/board/tasks
  .agents/state/board/epics
  .agents/state/memory/entries
)

# SIGNATURE DES COMMITS D'ÉTAT (T-00000724, décision pilote S-00003331). Par défaut la
# jambe section commite avec `--no-gpg-sign` : un `commit.gpgsign=true` lançait sinon un
# signataire (pinentry, clé matérielle) que rien ne borne, verrou POST_TASK_DONE tenu
# (S-00001930). L'INTERRUPTEUR opt-in est la clé git cadre.signStateCommits, lue par
# `git config --bool` dans le dépôt : `true` → le hook n'ajoute RIEN et le
# `commit.gpgsign` du dépôt s'applique comme à tout commit (la clé ne FORCE pas la
# signature) ; absente, fausse ou invalide → non signé — et une valeur invalide à UN
# niveau (globale `maybe`, locale `true`) fait refuser TOUTE la lecture (rc 128), donc
# non signé aussi. Aucune erreur propre : le seul signal est la mention « non signés »
# que la jambe externe ajoute à ses clauses de commit (voir `UNSIGNED`) quand le dépôt
# porte `commit.gpgsign=true`. `--bool` et non
# `--type=bool`, qui exige git ≥ 2.18 et rendrait l'opt-in inerte en silence. Une clé
# git et non une variable d'environnement : elle se lit dans le dépôt quel que soit le
# lanceur (CLI, nuit, hôtes, tableau de bord). Réglage du NOYAU, non promis par le
# contrat v0 (S-00003364) ; documenté dans README.md et docs/usage.html.
SIGN_SWITCH_KEY='cadre.signStateCommits'

# IGNORES PERSONNELS NEUTRALISÉS SUR LA SEULE JAMBE D'EXPORTS (T-00000724, option C de
# S-00003331, lue à la lettre : « aux status/add de la jambe d'exports »). Un
# `core.excludesFile` hors dépôt — global, XDG (`~/.config/git/ignore`) ou LOCAL — qui
# attrapait `*.jsonl` cachait un export de run NEUF : la jambe rendait `nothing` et le
# SHA poussé partait sans les événements. `-c core.excludesFile=/dev/null` les neutralise
# tous ; `.gitignore` et `.git/info/exclude` restent obéis. CONSÉQUENCE, écrite : tout
# `*.jsonl` à trois niveaux sous `runs/` (`runs/*/*/*.jsonl`), quel que soit son nom,
# que seule cette clé cachait EST commité — son remède :
# `printf '%s\n' <chemin> >> "$(git rev-parse --git-path info/exclude)"` (un
# `.git/info/exclude` écrit en dur échoue depuis un worktree lié, où `.git` est un
# fichier). La jambe `stores` (et `degraded_commit`)
# garde son comportement : la décision ne nomme que la jambe d'exports.
EXCLUDES_OFF='core.excludesFile=/dev/null'

# JSON-safe : retire les deux caractères qui cassent un littéral de chaîne JSON
# (`"` et `\`), le CR compris, puis borne. UNE fonction pour les DEUX champs
# émis (le résumé d'index et la classification du commit), ce qui ferme un trou
# préexistant : l'ancien `tr -d '"'` en ligne laissait passer `\` et `\r`, et un
# antislash dans la sortie de `index-refresh.sh` cassait DÉJÀ le JSON aujourd'hui.
# La borne est un argument : 300 pour le résumé d'index, 240 pour la
# classification (deux jambes, T-00000703). Invariant « un seul objet JSON ou rien » préservé.
json_sanitize() {
  # $1 = texte, $2 = longueur max
  printf '%s' "$1" | tr -d '"\\\r' | tr '\n' ' ' | cut -c1-"$2"
}

# --- UN SEUL POINT D'APPEL GIT (T-00000801, S-00003226 et S-00003742) --------------
# TOUT appel git de ce fichier passe par `git_hote`, jamais par `git` nu : le test
# `test_post_task_done_git_shield.py` le refuse (recensement) et tue un mutant par site.
# 1. RESTAURATION (S-00003226). Le préfixe des jambes Claude retire GIT_DIR et
#    GIT_WORK_TREE à TOUS les hooks, après en avoir recopié la valeur héritée dans
#    `_CADRE_GIT_DIR` / `_CADRE_GIT_WORK_TREE` (absente si la variable l'était, vide si
#    elle l'était). Ce fichier, et lui seul, les rend à SES appels git : sans eux, un
#    dépôt nu exporté logé SOUS un autre arbre git faisait commiter les stores dans le
#    dépôt PARENT (mesuré). Sous-shell : rien n'en fuit vers les ENFANTS du hook
#    (tasks.py, specs_graph.py, scripts/index-refresh.sh) — témoin `nu/enfants` du test,
#    mutants MX1 à MX4. Copies ABSENTES (Codex, Copilot, Kimi : pas de préfixe) : rien
#    n'est touché, un GIT_DIR hérité reste tel quel.
# 2. BLINDAGE (S-00003742, option A' ; S-00003821 pour le préfixe). Le préfixe des jambes
#    Claude ne rend aux hooks, de GIT_CONFIG_PARAMETERS / GIT_CONFIG_COUNT, que les entrées
#    `safe.directory` ; un hôte SANS préfixe (Codex, Copilot, Kimi) les passe entiers, et
#    GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM, XDG_CONFIG_HOME et HOME traversent toujours : par
#    au moins ces six canaux (mesurés avec témoin) git EXÉCUTE `core.fsmonitor`
#    (au moins : status, add, commit, reset, ls-files, diff, diff-index, check-ignore,
#    grep, update-index --refresh — relevé non clos, table au SKILL guardrails, tenue
#    par `test_fsmonitor_verbs_listed`) et les hooks de `core.hooksPath` (`post-index-change`
#    dès qu'un verbe réécrit l'index, tous les hooks de commit au commit). `-c` est de
#    portée ligne de commande : il l'emporte sur ces canaux et laisse
#    `safe.directory` passer. CONSÉQUENCES ÉCRITES, deux capacités perdues : (a) un hook
#    du dépôt (pre-commit, commit-msg…) ne s'exécute plus sur le commit d'état — ses
#    sujets fixes `chore(state): …` / `chore(runs): …` passent le commit-msg du kit ;
#    (b) l'index que l'`add` blindé réécrit perd l'extension FSMN d'un dépôt réglé
#    `core.fsmonitor=true` : le `git status` suivant la rebâtit par un balayage complet
#    (mesuré git 2.54/2.55 : 719 → 622 octets, FSMN rendue au status normal). RÉSIDU NOMMÉ,
#    relevé « au moins » : d'autres clés exécutent encore du code, qu'elles viennent de ces
#    canaux OU de la config du dépôt DÉSIGNÉ par la copie privée (`filter.<nom>.clean` via
#    `core.attributesFile` à l'`add`, `gpg.program` quand l'interrupteur de signature est
#    posé) — seuls les hooks et le `core.fsmonitor` de ce dépôt sont neutralisés ; le
#    blindage est une liste de clés, pas une purge du canal (témoins `nu/residu-filtre` et
#    `nu/residu-gpg`, `test_named_residues`).
# 3. STDIN FERMÉ (binôme de clôture de T-00000801, F6). Aucun git de ce fichier ne lit
#    stdin ; sans `</dev/null`, un include de `/dev/stdin` (config globale, ou P/C d'un
#    hôte sans préfixe) faisait AVALER au `rev-parse` de la racine la charge que la jambe
#    externe lit APRÈS lui — `grep` échouait, sortie 0, stores non commités, sans un mot
#    (mesuré). Témoin : `.agents/evals/test_hook_prefix_trace.py`.
git_hote() {
  (
    if [ -n "${_CADRE_GIT_DIR+x}" ]; then
      GIT_DIR="$_CADRE_GIT_DIR"
      export GIT_DIR
    fi
    if [ -n "${_CADRE_GIT_WORK_TREE+x}" ]; then
      GIT_WORK_TREE="$_CADRE_GIT_WORK_TREE"
      export GIT_WORK_TREE
    fi
    exec git -c core.fsmonitor=false -c core.hooksPath=/dev/null "$@" </dev/null
  )
}

# --- JAMBE SECTION : status → add → commit, UN jeton sur stdout --------------
# Appelée SOUS le verrou POST_TASK_DONE par `tasks.py commit-stores`, et
# DIRECTEMENT (sans verrou) par la jambe externe quand la jambe verrou a dégradé.
# N'émet qu'un seul jeton : committed | nothing | busy:<marqueur> | failed.
#
# SÉLECTEUR : deux valeurs reconnues. `stores` (défaut — les magasins d'état sous
# leurs deux formes, `STORE_SPECS`, 1re jambe du hook de `done`). `run-exports` (sa 2e jambe, T-00000703) — les exports
# de run VERSIONNÉS sous runs/, joués en CLÔTURE de nuit (T-00000677 : la base
# d'événements V3 a été retirée avec son binaire, elle vit désormais hors dépôt ;
# ce sont ses exports git sous runs/ qui portent seuls l'historique, et rien ne
# les commitait — le SHA poussé ne portait donc jamais les événements de la nuit).
# Un sélecteur inconnu est une erreur de programmation : `failed`, jamais un
# balayage par défaut.
commit_state_stores() {
  local dir="$1" selector="${2:-stores}"
  git_hote -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || { printf 'nothing'; return; }
  # TABLEAU et non chaîne éclatée : le pathspec des exports porte des `*` qu'une
  # expansion non citée ferait GLOBBER dans le cwd de l'hôte. Il n'est JAMAIS
  # développé vide — bash 3.2 (macOS stock) sous `set -u` refuse `"${a[@]}"` sur
  # un tableau vide (« unbound variable », mesuré) — la garde `${#specs[@]}`
  # précède toute expansion.
  local -a specs=()
  local f msg top=""
  case "$selector" in
    stores)
      # PAR FORME (`STORE_SPECS`, T-00001012) : une entrée n'entre que si `status` y voit
      # quelque chose — ajout, modification OU suppression. Le `[ -f ]` d'avant perdait la
      # suppression d'un monolithe (témoins : cas 58-64 du banc).
      for f in "${STORE_SPECS[@]}"; do
        [ -n "$(git_hote -C "$dir" status --porcelain --untracked-files=all -- "$f" 2>/dev/null)" ] \
          && specs+=("$f")
      done
      msg="chore(state): board, ledger et journal apres cloture de tache" ;;
    run-exports)
      # Pathspec de FORME (`RUN_EXPORTS_SPEC`), jamais `runs` nu ni -A : il capte
      # les exports MODIFIÉS et les NOUVEAUX (untracked) de la nuit, et RIEN de ce
      # qu'un outil tiers ou un fichier temporaire pose sous runs/. « Rien à
      # commiter » reste un `nothing` (succès silencieux) grâce au garde-fou
      # status --porcelain plus bas — jamais un commit vide. Un adoptant sans
      # runs/ est simplement sauté. runs/ se cherche à la RACINE GIT (voir
      # `RUN_EXPORTS_SPEC`), jamais sous "$dir" : en monorepo ce dernier est le
      # sous-projet, qui n'a pas de runs/.
      top="$(git_hote -C "$dir" rev-parse --show-toplevel 2>/dev/null)"
      [ -n "$top" ] && [ -d "$top/runs" ] && specs+=("$RUN_EXPORTS_SPEC")
      msg="chore(runs): exports de run apres cloture de tache" ;;
    *) printf 'failed'; return ;;
  esac

  # Jamais de commit au milieu d'une opération git en cours : un merge, un
  # rebase ou un cherry-pick interrompu par un commit automatique laisse un
  # dépôt que l'utilisateur doit réparer à la main. Idem pour un HEAD détaché.
  # `--absolute-git-dir`, jamais `--git-dir` : ce dernier rend « .git », un
  # chemin RELATIF au dépôt, cherché dans le cwd de l'hôte et jamais trouvé.
  local gitdir busy="" marker
  gitdir="$(git_hote -C "$dir" rev-parse --absolute-git-dir 2>/dev/null)"
  for marker in MERGE_HEAD REBASE_HEAD rebase-merge rebase-apply \
                CHERRY_PICK_HEAD BISECT_LOG; do
    [ -e "$gitdir/$marker" ] && busy="$marker"
  done
  git_hote -C "$dir" symbolic-ref -q HEAD >/dev/null 2>&1 || busy="${busy:-detached HEAD}"
  if [ -n "$busy" ]; then printf 'busy:%s' "$busy"; return; fi

  # APRÈS le contrôle `busy`, jamais avant : le sélecteur n'est plus rempli d'office par
  # les monolithes présents (T-00001012), donc un `MERGE_HEAD` sur des stores PROPRES doit
  # encore rendre `busy:`, pas `nothing` (cas 64).
  [ "${#specs[@]}" -gt 0 ] || { printf 'nothing'; return; }

  # Options git du `status` et de l'`add` : `-C "$dir"` TOUJOURS en tête (le tableau
  # n'est donc jamais vide — bash 3.2 sous `set -u` refuse `"${a[@]}"` vide), plus
  # `-c "$EXCLUDES_OFF"` pour le SEUL sélecteur `run-exports` (voir `EXCLUDES_OFF`).
  local -a gx=(-C "$dir")
  [ "$selector" = "run-exports" ] && gx+=(-c "$EXCLUDES_OFF")

  # Un LIEN SYMBOLIQUE sous runs/ est REFUSÉ (`failed`), jamais commité : le
  # pathspec ne trie que par NOM, et un lien nommé `<mois>.jsonl` pointant hors
  # de l'arbre entrerait dans l'historique comme un export (A2). `find -type l`
  # ne suit pas les liens, donc il ne descend nulle part hors de runs/. Sous la
  # RACINE GIT (T-00000691) : sous "$dir" il cherchait un runs/ de sous-projet
  # absent, ne voyait pas le lien, et le pathspec `top` l'aurait commité.
  if [ "$selector" = "run-exports" ] && [ -n "$(find "$top/runs" -type l 2>/dev/null)" ]; then
    printf 'failed'; return
  fi
  # Même refus pour la jambe `stores` sous CHAQUE dossier d'enregistrements
  # (`STORE_RECORD_DIRS` : `sync_outbox/`, T-00001058 ; `tasks/`, `epics/`, `entries/`,
  # T-00001012) et sur `SPECS.jsonl` lui-même : un lien nommé comme un enregistrement
  # entrerait dans l'historique, et le lecteur Python le refuse déjà (`_ouvrir_sans_lien`).
  # UN `find`, sans `-L` : un dossier qui est lui-même un lien est vu aussi (le point de
  # départ n'est pas suivi), et un chemin absent ne masque pas les autres (mesuré, M4).
  if [ "$selector" = "stores" ]; then
    local -a liens=()
    for f in "${STORE_RECORD_DIRS[@]}"; do
      liens+=("$dir/$f")
    done
    liens+=("$dir/.agents/state/specs/SPECS.jsonl")
    if [ -n "$(find "${liens[@]}" -type l 2>/dev/null)" ]; then
      printf 'failed'; return
    fi
  fi

  # `status --porcelain` et non `diff --quiet` : le second ignore ce qui est
  # DÉJÀ indexé, et laisserait donc passer un store mis en index à la main.
  # `--untracked-files=all` sur la LIGNE DE COMMANDE : un dépôt qui porte
  # `status.showUntrackedFiles=no` cacherait sinon le NOUVEAU mois d'export, et
  # la jambe rendrait `nothing` sur un export jamais commité (F2).
  [ -n "$(git_hote "${gx[@]}" status --porcelain --untracked-files=all -- "${specs[@]}" 2>/dev/null)" ] \
    || { printf 'nothing'; return; }

  # Pathspec explicite à l'`add` ET au `commit` : jamais de `-A`, jamais de
  # balayage de ce que l'utilisateur aurait mis en index par ailleurs. Commit
  # SÉPARÉ de l'index et AVANT lui (l'index estampille son en-tête avec le SHA).
  # Le commit ne reçoit pas `-c "$EXCLUDES_OFF"` : il ne prend que ce que l'`add` a
  # mis en index. `--no-gpg-sign` sauf interrupteur (voir `SIGN_SWITCH_KEY`) ; tableau
  # jamais vide, `commit -q` en tête.
  git_hote "${gx[@]}" add -- "${specs[@]}" >/dev/null 2>&1
  local -a commit_cmd=(commit -q)
  [ "$(git_hote -C "$dir" config --bool --get "$SIGN_SWITCH_KEY" 2>/dev/null)" = "true" ] \
    || commit_cmd+=(--no-gpg-sign)
  if git_hote -C "$dir" "${commit_cmd[@]}" \
       -m "$msg" \
       -- "${specs[@]}" >/dev/null 2>&1; then
    printf 'committed'
  else
    # Un commit qui ÉCHOUE (identité absente, signataire en échec…) laisse en
    # index ce que l'`add` vient d'y mettre : on le RETIRE — mêmes chemins,
    # jamais un `reset` nu — AVANT de dire `failed`, sinon l'échec laisse un
    # index sale que le prochain geste git emporte sans le savoir (A3, les deux
    # jambes).
    git_hote -C "$dir" reset -q -- "${specs[@]}" >/dev/null 2>&1
    printf 'failed'
  fi
}

# La jambe verrou nous rappelle ICI, sous le verrou, pour le seul commit. Le
# troisième argument est le sélecteur ; absent, c'est `stores` — l'appel de
# `tasks.py commit-stores` ne le passe pas et ne change pas.
if [ "${1:-}" = "--commit-section" ]; then
  commit_state_stores "${2:-}" "${3:-stores}"
  exit 0
fi

# --- JAMBE EXTERNE ----------------------------------------------------------
# La racine, sans supposer l'hôte : `CLAUDE_PROJECT_DIR` n'existe que chez
# Claude Code ; Codex, Copilot et Kimi Code ancrent sur `git rev-parse --show-toplevel`
# (contrat asserté par .codex/hooks/test_hook_contracts.py). `pwd` reste le
# dernier recours hors dépôt git.
DIR="${CLAUDE_PROJECT_DIR:-}"
[ -n "$DIR" ] || DIR="$(git_hote rev-parse --show-toplevel 2>/dev/null || pwd)"
PAYLOAD="$(cat 2>/dev/null || true)"

# Pas de dépendance à jq — mais pas de correspondance de sous-chaîne large non
# plus. On exige la forme réelle de la commande, `tasks.py [--options] done`.
printf '%s' "$PAYLOAD" | grep -Eq \
  'tasks\.py([[:space:]]+--[a-zA-Z-]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+done([[:space:]]|\\?"|$)' \
  || exit 0

# Résolution d'interpréteur par PROBE D'EXÉCUTION, jamais `command -v` : le stub
# `python3` du Microsoft Store EXISTE comme fichier (donc `command -v` le
# sélectionne) mais échoue à l'exécution. Même ordre que .agents/pyrun.sh.
# Résolu AVANT la garde de réponse ci-dessous, qui parse le JSON quand elle peut.
PY=""
PY_PROBE='import sys; sys.stdout.write(sys.executable); sys.exit(sys.version_info[0] != 3)'
PY_CR="$(printf '\r')"
for c in python3 python; do
  PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
  case "$PY_CANDIDATE" in
    *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
  esac
  if [ -n "$PY_CANDIDATE" ]; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  PY_UNAME=""
  command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"
  case "${OS-}:$PY_UNAME" in
    Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
      PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
      case "$PY_CANDIDATE" in
        *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
      esac
      [ -n "$PY_CANDIDATE" ] && PY="$PY_CANDIDATE"
      ;;
  esac
fi

# LA COMMANDE DEMANDÉE N'EST PAS LA TÂCHE FERMÉE, et depuis `T-00000586` l'écart
# est devenu observable : `tasks.py done` peut être REFUSÉ par la garde de double
# revue, et ce hook committait quand même les trois stores sous le message
# « après clôture de tâche » — mesuré deux fois le 2026-09-13 par le binôme, sur
# des commits qui ne contenaient AUCUNE clôture. Un message d'historique faux
# coûte plus cher qu'un commit manquant : il fait chercher une clôture qui
# n'existe pas.
#
# LA GARDE EST ASYMÉTRIQUE, ET C'EST DÉLIBÉRÉ. La preuve d'une clôture réussie
# est la ligne `TASKS: T-NNN → done`, contrat de consommateur déclaré dans
# `set_state`. Mais tous les hôtes ne mettent pas la sortie de l'outil dans la
# charge — ce hook tourne sur Claude, Codex, Copilot ET Kimi Code, et son propre banc
# n'envoie que `tool_input`. Exiger la ligne inconditionnellement couperait les
# commits d'état EN SILENCE là où le champ n'existe pas, ce qui est bien pire
# que le faux message qu'on corrige.
#
# Donc : on ne refuse QUE si la charge porte une section de réponse ET que la
# ligne de succès n'y est pas. Pas de section de réponse ⇒ comportement d'avant.
# La perte est nommée : sur un hôte sans ce champ, le faux commit subsiste.
#
# ET LA LIGNE SE CHERCHE DANS `tool_response` SEUL, JAMAIS DANS TOUTE LA CHARGE
# (S-00001927, mesuré avec dégât) : `tool_input.command` fait partie de la charge,
# donc une commande qui CITAIT la ligne de succès — un `grep` sur ce banc, un
# `cat` de sa doc — satisfaisait la garde et déclenchait les DEUX commits sur le
# dépôt vivant sans qu'aucune tâche ait été fermée (858c5ac/fcc7b2d). La garde
# vit donc APRÈS la résolution de l'interpréteur, pour parser le JSON quand il y
# en a un ; le repli sans python ne regarde que ce qui SUIT la dernière clé
# `"tool_response"` — résidu écrit : une réponse dont une chaîne contiendrait la
# clé nue (elle y serait échappée `\"`, donc sans le `"` fermant collé) ne
# déplace pas la coupe, mais une charge dont la réponse PRÉCÈDE la commande
# (aucun hôte connu) rendrait ce repli aussi large que la charge.
tool_response_or_absent() {
  # stdin = la charge ; stdout = la section `tool_response` re-sérialisée, ou le
  # jeton `__ABSENT__` quand la clé n'existe pas au premier niveau (la clé lue
  # par le `grep` d'en-tête vivait alors dans une chaîne, p. ex. dans la
  # commande) ; rc 1 sur un JSON illisible → repli textuel.
  "$PY" -c 'import json, sys
try:
    charge = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
except ValueError:
    sys.exit(1)
if not isinstance(charge, dict) or "tool_response" not in charge:
    sys.stdout.write("__ABSENT__")
    sys.exit(0)
sys.stdout.buffer.write(json.dumps(charge["tool_response"], ensure_ascii=False).encode("utf-8"))
'
}
if printf '%s' "$PAYLOAD" | grep -q '"tool_response"'; then
  _cle='"tool_response"'
  RESP=""
  if [ -n "$PY" ]; then
    RESP="$(printf '%s' "$PAYLOAD" | tool_response_or_absent 2>/dev/null)" \
      || RESP="${PAYLOAD##*$_cle}"
  else
    RESP="${PAYLOAD##*$_cle}"
  fi
  if [ "$RESP" != "__ABSENT__" ]; then
    # Les deux graphies de la flèche : la charge peut la rendre échappée en JSON.
    # L'id : `T-<ULID>` (26 symboles Crockford) ou l'ancien `T-<chiffres>`
    # (T-00001040 ; témoins : cas 31e/31f de post-task-done-index.test.sh).
    # `LC_ALL=C` : les plages de la classe sont des plages d'OCTETS ASCII, jamais
    # celles d'une collation locale (clôture du lot 95d6220a..c964c9a6, F9).
    printf '%s' "$RESP" | LC_ALL=C grep -Eq 'TASKS: T-([0-9A-HJKMNP-TV-Z]{26}|[0-9]+) (→|\\u2192) done' || exit 0
  fi
fi

# La jambe verrou prend le verrou dédié et lance la jambe section dessous, en
# relayant un jeton. Si aucun python ne résout, la jambe externe — qui EST déjà
# bash — fait le commit ELLE-MÊME, SANS verrou : refuser rendrait *probabiliste*
# le commit des trois sources de vérité là où il n'est aujourd'hui que concurrent.
if [ -n "$PY" ]; then
  TOKEN="$("$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-stores 2>/dev/null)"
else
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  TOKEN="interp-introuvable"
fi

# SIGNATURE SAUTÉE, DITE (T-00000724, binôme de clôture). Le dépôt demande la signature
# (`commit.gpgsign=true`) et l'interrupteur ne se lit pas `true` (absent, faux, invalide —
# rc 128 compris) : la jambe section a commité avec `--no-gpg-sign`, et chaque clause qui
# annonce un commit le DIT. Mêmes lectures `--bool` dans "$DIR" que la jambe section.
# Ajoutée aux SEULS bras `committed` : aucune clause « non commités » ne la porte, et elle
# ne contient aucun jeton dégradé lu par `dashboard.py::_classify_commit_stdout`. CANAL,
# écrit : le `systemMessage` de ce hook — le tableau de bord classe la phrase `ok` et
# n'affiche rien, `commit-stores` / `commit-run-exports` lancés en direct (la clôture de
# nuit) ne rendent que leur jeton.
UNSIGNED=""
if [ "$(git_hote -C "$DIR" config --bool --get commit.gpgsign 2>/dev/null)" = "true" ] \
   && [ "$(git_hote -C "$DIR" config --bool --get "$SIGN_SWITCH_KEY" 2>/dev/null)" != "true" ]; then
  UNSIGNED=" (non signés : voir $SIGN_SWITCH_KEY)"
fi

# Le dégradé commite QUAND MÊME, sans verrou, mais le DIT : la jambe externe EST
# déjà bash, et refuser rendrait *probabiliste* le commit des trois sources de
# vérité. Un seul chemin de repli pour toutes les causes (bash/interpréteur
# introuvable, verbe injoignable — p. ex. `tasks.py` absent d'un dépôt minimal),
# le motif nommé. `locked-out` n'est JAMAIS un dégradé : le verrou est tenu par
# une autre clôture qui commite, s'auto-commiter la doublerait.
degraded_commit() {  # $1 = phrase du motif
  local t2; t2="$(commit_state_stores "$DIR")"
  case "$t2" in
    committed) CLASS="stores commités sans verrou (dégradé : $1)$UNSIGNED" ;;
    nothing)   CLASS="" ;;
    busy:*)    CLASS="stores non commités (opération git en cours : ${t2#busy:})" ;;
    *)         CLASS="stores non commités (motif : échec capturé)" ;;
  esac
}

# Classification FERMÉE à quatre valeurs (+ silence).
CLASS=""
case "$TOKEN" in
  committed)          CLASS="stores commités$UNSIGNED" ;;
  nothing)            CLASS="" ;;
  busy:*)             CLASS="stores non commités (opération git en cours : ${TOKEN#busy:})" ;;
  failed)             CLASS="stores non commités (motif : échec capturé)" ;;
  locked-out)         CLASS="stores non commités (motif : verrou tenu au-delà de la borne)" ;;
  bash-introuvable)   degraded_commit "bash introuvable" ;;
  interp-introuvable) degraded_commit "interpréteur introuvable" ;;
  *)                  degraded_commit "verbe injoignable" ;;
esac

# --- JAMBE RUN-EXPORTS (T-00000703) : APRÈS les stores, même verrou POST_TASK_DONE,
# verbe DISTINCT (`tasks.py commit-run-exports`, SYM-9339). Tentée seulement quand
# le verbe est ATTEIGNABLE (jeton d'un verbe qui a tourné). Sur `busy:*` le dépôt
# refuserait pareil : la jambe n'est pas tentée et AUCUNE clause exports n'est
# émise. Sur un dégradé (bash/interpréteur/verbe injoignable) le verbe n'est pas
# là pour la jouer et la jambe externe ne la rejoue PAS sans verrou (contrairement
# aux stores : un export peut attendre le prochain `done`, une source de vérité
# non) — mais se TAIRE se lisait « rien à commiter » (F4) : si un export non
# commité existe, la clause le DIT, « non tentés », et le prochain `done` reprend.
CLASS2=""
case "$TOKEN" in
  committed|nothing|failed|locked-out)
    TOKEN2="$("$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-run-exports 2>/dev/null)"
    case "$TOKEN2" in
      committed)        CLASS2="exports commités$UNSIGNED" ;;
      nothing)          CLASS2="" ;;
      busy:*)           CLASS2="exports non commités (opération git en cours : ${TOKEN2#busy:})" ;;
      locked-out)       CLASS2="exports non commités (motif : verrou tenu au-delà de la borne)" ;;
      bash-introuvable) CLASS2="exports non commités (motif : bash introuvable)" ;;
      *)                CLASS2="exports non commités (motif : échec capturé)" ;;
    esac
    ;;
  busy:*) : ;;
  *)
    # Même pathspec que la jambe : un `.borne.tmp` ou un fichier tiers sous runs/
    # n'est pas un export non commité, et le dire serait faux. Mêmes ignores aussi
    # (`EXCLUDES_OFF`) : un export que seule une clé personnelle cachait sera commité
    # par la jambe au prochain `done`, donc il est DIT ici plutôt que tu.
    [ -n "$(git_hote -C "$DIR" -c "$EXCLUDES_OFF" status --porcelain --untracked-files=all -- "$RUN_EXPORTS_SPEC" 2>/dev/null)" ] \
      && CLASS2="exports non commités (non tentés : chemin dégradé)" ;;
esac
_sep=' · '
[ -n "$CLASS2" ] && CLASS="${CLASS:+$CLASS$_sep}$CLASS2"

# Borne 240 et non 120 (T-00000703) : deux jambes concaténées ; la paire la plus
# longue (locked-out × locked-out) fait < 240 — mesuré `printf '%s · %s' … | wc -c`
# = 131 octets. Avec la mention `UNSIGNED` (T-00000724), le produit ENTIER des clauses
# des deux jambes, mention posée, culmine à 180 octets (dégradé « interpréteur
# introuvable » × exports `locked-out`, mesuré `wc -c`) : toujours < 240.
STORE_MSG=""
[ -n "$CLASS" ] && STORE_MSG="$(json_sanitize "$CLASS$_sep" 240)"

# --- Graphe de specs --------------------------------------------------------
# Le graphe que sert la page `#/specs` du dashboard est un DÉRIVÉ des trois
# stores qui viennent d'être commités : c'est donc ici, et nulle part ailleurs,
# qu'il se rafraîchit — le seul instant où l'on sait que les stores ont bougé.
#
# ADVISORY comme tout ce hook, et trois propriétés le rendent sûr à laisser
# tourner sans surveillance : la génération est IDEMPOTENTE (un graphe inchangé
# n'est pas réécrit, donc pas de churn), elle n'écrase JAMAIS une publication
# manuelle (marqueur `generator`, `--force` est le seul contournement), et son
# échec est silencieux — le graphe est une VUE, jamais un invariant, et un hook
# qui ferait échouer une clôture de tâche pour une vue serait un défaut.
#
# `|| true` explicite : `set -e` n'est pas actif ici, mais le contrat du hook est
# « toujours exit 0 » et une commande finale non nulle le romprait par accident.
if [ -n "$PY" ] && [ -f "$DIR/.agents/bin/specs_graph.py" ]; then
  "$PY" "$DIR/.agents/bin/specs_graph.py" --root "$DIR" generate >/dev/null 2>&1 || true
fi

# --- Index ------------------------------------------------------------------
# Ce kit ne commite pas son index tout seul. Un projet consommateur peut poser
# un `scripts/index-refresh.sh` ; s'il existe, on l'enchaîne ici, APRÈS le commit
# des stores et HORS du verrou. Absent, le hook s'arrête sur le message des stores.
[ -f "$DIR/scripts/index-refresh.sh" ] || {
  [ -n "$STORE_MSG" ] && printf '{"systemMessage": "post-task-done: %s"}' "${STORE_MSG% · }"
  exit 0
}

OUT="$(bash "$DIR/scripts/index-refresh.sh" 2>&1)"
SUMMARY="$(json_sanitize "$OUT" 300)"
[ -n "$SUMMARY$STORE_MSG" ] && \
  printf '{"systemMessage": "%sindex-refresh: %s"}' "$STORE_MSG" "$SUMMARY"

exit 0
