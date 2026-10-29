#!/usr/bin/env bash
# Stop — if the repo moved on since the index was built, nudge (never block). Advisory only: ALWAYS exits 0.
DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
IDX="$DIR/.agents/state/index/SYMBOLS.md"
[ -f "$IDX" ] || exit 0

stale=""
# Second, INDEPENDENT verdict (T-00000108): the SQLite index store — a MACHINE
# store outside the repository since T-00000668, so there is nothing to commit —
# is ADVISORY in v1, goes stale at EVERY index rebuild, and had no channel to say so
# — the SessionStart hooks discard the builder's stdout, and `--verify` only
# speaks when a human runs it. This nudge already reads the probe's output, so it
# is where that silence ends. Set ONLY on the probe path below: the git/mtime
# fallback knows nothing about the DB and must stay quiet rather than guess.
db_stale=""
db_detail=""
OUT=""

# Lecture de la sortie de la sonde ($OUT) : pose stale / db_stale / db_detail.
# Une FONCTION parce qu'elle sert deux fois — sortie fraîche de la sonde, ou
# sortie REJOUÉE par le cache ci-dessous — et que le message doit être le même
# octet pour octet dans les deux cas.
sr_lire() {
  case "$OUT" in
    *"INDEX STALE"*)
      # LINE-SCOPED, not "${OUT#INDEX STALE @ }": the probe now prints a SECOND
      # line, and a prefix-strip over a multi-line capture would drag it — plus a
      # raw newline — into the JSON payload below and produce invalid JSON.
      #
      # And CONTENT-BOUNDED, not merely line-scoped, exactly like db_detail
      # below: the sha is captured hex-only (or the literal `nogit`) and the
      # reason is picked from the static literals here by matching the probe's
      # own wording. So nothing variable — no quote, backslash or control
      # character — can reach the JSON payload, whatever the probe grows to
      # print later. The producer owes itself the discipline it already applies
      # before handing a header sha to git (L-009).
      stale_sha=$(printf '%s\n' "$OUT" \
        | sed -n 's/^INDEX STALE @ \([0-9a-fA-F]\{4,40\}\|nogit\).*/\1/p' | head -1)
      case "$OUT" in
        *"identity source lost"*) stale_why="identity source lost";;
        *) stale_why="a rebuild would change the index files";;
      esac
      if [ -n "$stale_sha" ]; then stale="$stale_sha - $stale_why"; else stale="$stale_why"; fi
      ;;
  esac
  case "$OUT" in
    *"DB STALE"*)
      db_stale=1
      # ASCII, hex-only capture: the builder's prose carries an em dash that a
      # cp1252 console mangles, so the DETAIL is optional and the flag above —
      # set by the case match alone — is what decides whether we speak.
      db_detail=$(printf '%s\n' "$OUT" \
        | sed -n 's/^DB STALE @ \([0-9a-fA-F]\{4,40\}\) vs files @ \([0-9a-fA-F]\{4,40\}\).*/db @ \1, index files @ \2/p' \
        | head -1)
      [ -n "$db_detail" ] || db_detail="its generation differs from the index files"
      ;;
  esac
  # "INDEX CURRENT", "INDEX BUILD IN FLIGHT" (another build already running),
  # a timeout or an empty output all mean: nothing useful to nudge about.
}

# Three distinct cases, one message each — never a merged half-truth. The event
# stays `index.stale` and only for the INDEX: the emitted-event vocabulary is a
# registry (see .agents/evals/test_events_parity.py) and this task adds no kind.
sr_dire() {
  if [ -n "$stale" ]; then
    bash "$DIR/.claude/hooks/emit-event.sh" index.stale "reason=$stale" >/dev/null 2>&1 || true
  fi
  if [ -n "$stale" ] && [ -n "$db_stale" ]; then
    # ORDER IS LOAD-BEARING: rebuild the FILES first, resync the DB after. Resyncing
    # first would bind the store to a generation the very next rebuild replaces.
    printf '{"systemMessage": "Two stores are stale. INDEX FILES (%s): run python .agents/bin/build_index.py --if-stale (0 LLM) to refresh. THEN the advisory index.db (%s): run python .agents/bin/migrate_index_to_db.py --resync. It is a machine store outside the repository: nothing to commit (annotations_log.jsonl only, if it moved). Invoke the indexer agent afterwards only to annotate purposes/roles."}' "$stale" "$db_detail"
  elif [ -n "$stale" ]; then
    printf '{"systemMessage": "Index is stale (%s). Run python .agents/bin/build_index.py --if-stale (0 LLM) to refresh; invoke the indexer agent afterwards only to annotate purposes/roles."}' "$stale"
  elif [ -n "$db_stale" ]; then
    printf '{"systemMessage": "Index files are CURRENT, but the advisory index.db, a machine store outside the repository, is stale (%s). Nothing resyncs it automatically: run python .agents/bin/migrate_index_to_db.py --resync. Nothing to commit (annotations_log.jsonl only, if it moved); nothing to rebuild otherwise."}' "$db_detail"
  fi
}

# ---- CACHE DE LA SONDE (T-00000837) -----------------------------------------
# `build_index.py --stale-check` coûte ~0,37 s à CHAQUE fin de tour pour un
# rappel qui ne change que si son ENTRÉE change. Ce qu'il lit réellement (relevé
# dans `_build` / `index_is_current` / `db_staleness_line`) : HEAD ; les NOMS
# changés (diff ancre..HEAD, non indexés, indexés, non suivis — des noms, jamais
# des contenus : `scope_currency` filtre par `_keep(f, None, …)`, sans stat) ;
# le CONTENU des fichiers d'index (en-tête built @/backend/threshold/kinds/
# dirscope, borne du delta, génération des corps, identité des shards) ; la
# présence des marqueurs kit/vendoring ; le ctags résolu ; ABK_INDEX_KINDS /
# ABK_INDEX_UNSKIP ; le verrou de build ; et, pour la ligne DB, le store
# index.db MACHINE hors dépôt (cadre.paths). L'empreinte couvre chacun :
# `git status --porcelain=v2 --branch -uall` (HEAD + les trois ensembles de
# noms ; `-uall` est porteur : sans lui un nouveau fichier dans un répertoire
# déjà non suivi ne bougerait rien), le hash `--no-filters` des fichiers d'index
# et du builder (build_index.py, migrate_index_to_db.py), les marqueurs, ctags,
# l'environnement lu, et la LISTE des index.db présents sous la racine d'état.
# Un index.db RÉÉCRIT (--resync) depuis l'estampille du cache le périme aussi
# (mtime ≥ estampille, prise AVANT la sonde, donc une égalité de seconde périme
# plutôt qu'elle ne rejoue). Jamais caché : verrou de build présent, sortie
# vide, IN FLIGHT, timeout, et tout le repli git/mtime (sans python ni timeout).
# `.agents/state/local/` (verrou, cache) est hors de l'empreinte ET hors du
# périmètre de la sonde. BORNES NON TENUES, dites : un aller-retour A→B→A de
# l'arbre PENDANT la sonde rejoue la sortie de B pour A (rappel consultatif,
# jamais une porte) ; un ctags remplacé au même chemin ; un helper du builder
# autre que ces deux fichiers (src/cadre/paths.py) ; un clone partiel qui
# récupère plus tard l'objet manquant du diff ancre..HEAD sans que HEAD bouge ;
# une racine d'état relative ou avec ~ dans CADRE_STATE_DIR / XDG_STATE_HOME
# (le hook ne la résout pas comme Python). Python absent APRÈS une inscription :
# le cache rejoue la dernière sortie de la sonde au lieu du repli.
SR_CACHE="$DIR/.agents/state/local/stop-reindex/sonde"
SR_ETAT="${CADRE_STATE_DIR:-}"
if [ -z "$SR_ETAT" ]; then
  if [ -n "${XDG_STATE_HOME:-}" ]; then SR_ETAT="$XDG_STATE_HOME/cadre"; else SR_ETAT="${HOME:-}/.local/state/cadre"; fi
fi
sr_empreinte() {
  local st h f fic
  [ -f "$DIR/.agents/bin/build_index.py" ] || return 1
  [ -e "$DIR/.agents/state/local/.build_index.lock" ] && return 1
  st="$(git -C "$DIR" --no-optional-locks status --porcelain=v2 --branch -uall -- . ':(exclude).agents/state/local' 2>/dev/null)" || return 1
  fic=("$DIR/.agents/bin/build_index.py")
  [ -f "$DIR/.agents/bin/migrate_index_to_db.py" ] && fic+=("$DIR/.agents/bin/migrate_index_to_db.py")
  for f in "$DIR/.agents/state/index/"*; do
    [ -f "$f" ] || continue
    case "$f" in
      */index.db) continue ;;
    esac
    fic+=("$f")
  done
  h="$(git hash-object --no-filters -- "${fic[@]}" 2>/dev/null)" || return 1
  {
    printf 'sr-v1\nroot %s\n%s\n%s\n' "$DIR" "$st" "$h"
    for f in .agents/IS_THE_KIT .agents/protected-paths.local .claude/hooks/protected-paths.local; do
      [ -f "$DIR/$f" ] && printf 'marqueur %s\n' "$f"
    done
    printf 'env %s|%s|%s|%s|%s\n' "${ABK_INDEX_KINDS-}" "${ABK_INDEX_UNSKIP-}" "${CTAGS-}" "${CTAGS_PATH-}" "${CADRE_PROJECT_ROOT-}"
    printf 'ctags %s\netat %s\n' "$(command -v ctags 2>/dev/null)" "$SR_ETAT"
    for f in "$SR_ETAT"/projets/*/index/index.db*; do
      [ -e "$f" ] && printf 'db %s\n' "$f"
    done
  } | git hash-object --stdin 2>/dev/null
}
# 0 = aucun index.db présent n'a été touché depuis l'estampille du cache.
sr_db_intact() {
  local f
  for f in "$SR_ETAT"/projets/*/index/index.db*; do
    [ -e "$f" ] || continue
    [ "$SR_CACHE" -nt "$f" ] || return 1
  done
  return 0
}
SR_CLE="$(sr_empreinte)" || SR_CLE=""
if [ -n "$SR_CLE" ] && [ -f "$SR_CACHE" ] && [ "$(sed -n '1p' "$SR_CACHE" 2>/dev/null)" = "$SR_CLE" ] \
   && sr_db_intact; then
  OUT="$(sed '1d' "$SR_CACHE" 2>/dev/null)"
  sr_lire
  sr_dire
  exit 0
fi

# Preferred signal (T-00000033): ask the builder ITSELF via its read-only
# probe — `--stale-check` runs exactly the `--if-stale` currency computation
# and writes nothing. One staleness definition, owned by build_index.py, so
# this nudge can never disagree with the refresh it recommends. The previous
# git-diff heuristic here had a wider domain than the index (SKIP_DIRS
# excludes .agents entirely; a commit-sha anchor never accounts for a rebuild
# from a dirty worktree), which made the nudge INEXTINGUISHABLE: it fired at
# every Stop while the refresh it pointed at answered INDEX CURRENT forever.
# Hard 5s wall bound, same rationale as session-start.sh's refresh call.
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
[ -n "$PY" ] || echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
# T-00001191 : aucun `.pyc` (build_index, migrate_index_to_db, src/cadre/paths) ; l'env atteint les enfants.
export PYTHONDONTWRITEBYTECODE=1
if [ -n "$PY" ] && [ -f "$DIR/.agents/bin/build_index.py" ] \
   && command -v timeout >/dev/null 2>&1; then
  # L'estampille du cache est prise AVANT la sonde (sr_db_intact) : un index.db
  # réécrit pendant la sonde la périme au tour suivant au lieu d'être rejoué.
  SR_TAMPON=""
  if [ -n "$SR_CLE" ] && mkdir -p "${SR_CACHE%/*}" 2>/dev/null; then
    SR_TAMPON="$SR_CACHE.$$"
    : > "$SR_TAMPON" 2>/dev/null || SR_TAMPON=""
  fi
  OUT=$(timeout 5 "$PY" -B "$DIR/.agents/bin/build_index.py" --root "$DIR" --stale-check 2>/dev/null)
  sr_rc=$?
  sr_lire
  # Inscription : seulement un verdict COMPLET de la sonde (CURRENT ou STALE)
  # ET une sonde sortie 0 — jamais IN FLIGHT, une sortie vide, ni une sortie
  # PARTIELLE (timeout 124, sonde tuée ou en erreur : « INDEX CURRENT @ … » déjà
  # imprimé ne dit rien de la ligne DB qui manque). Sinon le cache est effacé.
  sr_cachable="$OUT"
  [ "$sr_rc" -eq 0 ] || sr_cachable=""
  case "$sr_cachable" in
    *"INDEX CURRENT"*|*"INDEX STALE"*)
      if [ -n "$SR_TAMPON" ] && printf '%s\n%s\n' "$SR_CLE" "$OUT" > "$SR_TAMPON.w" 2>/dev/null \
         && touch -r "$SR_TAMPON" "$SR_TAMPON.w" 2>/dev/null; then
        mv -f "$SR_TAMPON.w" "$SR_CACHE" 2>/dev/null
      fi
      ;;
    *)
      rm -f "$SR_CACHE" 2>/dev/null
      ;;
  esac
  [ -n "$SR_TAMPON" ] && rm -f "$SR_TAMPON" "$SR_TAMPON.w" 2>/dev/null
else
  # No probe available (no python, no timeout(1), or a tree carrying an index
  # without the builder). Fall back to git, with the SAME domain restriction
  # the probe applies, so the fallback cannot resurrect the inextinguishable
  # nudge T-00000033 removed. Deterministic, unlike mtime: git compares content,
  # and the eval fixture proved mtime alone flakes when a rewrite lands inside
  # the filesystem's timestamp granularity.
  built_sha=$(sed -n 's/.*built @ \([0-9a-fA-F]\{4,\}\).*/\1/p' "$IDX" | head -1)
  if [ -n "$built_sha" ] && git -C "$DIR" rev-parse --git-dir >/dev/null 2>&1 \
     && git -C "$DIR" cat-file -e "$built_sha" 2>/dev/null; then
    # THE DOMAIN MIRRORS THE BUILDER'S EFFECTIVE SCOPE (T-00000062). '.agents'
    # and 'docs' are always out. In a tree the builder treats as a VENDORED kit
    # — one carrying '.agents/protected-paths.local' OR
    # '.claude/hooks/protected-paths.local' at its root — '.claude', '.codex'
    # and '.gemini' are out AT THE ROOT too, because the builder no longer
    # indexes them there. Same discriminator as host_skip_dirs(), never the
    # directory NAME: in the kit's own repo those directories ARE the source
    # code and a change there must still nudge. Without this, editing
    # .codex/hooks/*.py in a consumer nudges at every Stop while the refresh
    # this hook recommends answers INDEX CURRENT forever.
    # The same pathspec carries the builder's KIT CODE ROOTS ('agentic_v3', the
    # V3 engine): the builder stops indexing them under a marker for the same
    # reason, so a domain that kept them here would be WIDER than the index and
    # reintroduce exactly that inextinguishable nudge.
    # RÉALIGNÉ le 2026-09-09 sur `build_index.py` — ce repli REJOUE le domaine du
    # builder, donc toute divergence entre les deux rend ce relevé plus large ou
    # plus étroit que l'index qu'il prétend juger.
    #
    # DEUX DIVERGENCES CORRIGÉES, toutes deux mesurées :
    #
    # 1. `core-scripts` et `.githooks` MANQUAIENT. Ils sont entrés dans
    #    `KIT_CODE_DIRS` (`build_index.py`) le 2026-09-09 : sans eux ici, le
    #    domaine restait PLUS LARGE que l'index chez un adoptant — 23 fichiers
    #    sous `core-scripts` et 1 sous `.githooks` surveillés mais jamais
    #    indexés, c'est-à-dire le rappel inextinguible que T-00000033 avait
    #    justement retiré.
    #
    # 2. `KIT_MARKER` ÉTAIT IGNORÉ, et c'est la divergence qui portait SUR CE
    #    DÉPÔT-CI. `build_index.py` lit `.agents/IS_THE_KIT` AVANT les marqueurs
    #    de vendoring et court-circuite : dans le dépôt du kit, RIEN n'est exclu
    #    de l'index. Or `.agents/protected-paths.local` existait ici (il portait les
    #    motifs de la garde de la route de dev locale, retirée depuis), donc ce test le prenait pour un arbre
    #    VENDORÉ et excluait `.claude`, `.codex`, `.gemini`, `agentic_v3` —
    #    rendant le domaine PLUS ÉTROIT que l'index, sur le seul dépôt où l'écart
    #    ne pouvait être vu par personne. Même misreading que T-00000513, qui
    #    avait coûté 482 symboles tombés à 64.
    #
    # 3. `src/cadre` MANQUAIT (T-00001100) : entré dans `KIT_CODE_DIRS` sans
    #    entrer ici, une modification sous lui seul répondait STALE à chaque Stop
    #    chez un adoptant privé de la sonde. L'égalité des deux portées est
    #    gardée par `.agents/bin/test_stop_reindex_domaine.py`.
    HOST_EXCL=""
    if [ ! -f "$DIR/.agents/IS_THE_KIT" ] \
       && { [ -f "$DIR/.agents/protected-paths.local" ] \
            || [ -f "$DIR/.claude/hooks/protected-paths.local" ]; }; then
      HOST_EXCL=":(exclude,top).claude :(exclude,top).codex :(exclude,top).gemini :(exclude,top)agentic_v3 :(exclude,top)core-scripts :(exclude,top).githooks :(exclude,top)src/cadre"
    fi
    # shellcheck disable=SC2086  # HOST_EXCL is a deliberately word-split pathspec list
    if ! git -C "$DIR" diff --quiet "$built_sha" -- . ':(exclude).agents' ':(exclude)docs' $HOST_EXCL 2>/dev/null; then
      stale="source changed since the index was built @ ${built_sha}"
    # 4. `.agents/vendor` (T-01M5BXTGX5YN8XEXTG1PP7A5ZX) : DANS LE KIT le builder
    #    l'indexe (`KIT_VENDOR` de `build_index.py`), mais `':(exclude).agents'`
    #    ci-dessus le retire du domaine ; une exclusion de git ne se perce pas,
    #    d'où cette seconde lecture, bornée au kit et à la racine vendor. Chez
    #    l'adoptant `.agents` reste hors domaine en entier, comme dans l'index.
    #    `${built_sha}` en accolades : la ligne du domaine reste la SEULE à porter
    #    la forme que `test_stop_reindex_domaine.py` et `test_vendor_scope.py` lisent.
    elif [ -f "$DIR/.agents/IS_THE_KIT" ] \
         && ! git -C "$DIR" diff --quiet "${built_sha}" -- ':(top).agents/vendor' 2>/dev/null; then
      stale="source changed since the index was built @ ${built_sha}"
    fi
  else
    # Last resort: mtime — is any source file newer than the index?
    changed=$(find "$DIR/src" "$DIR/lib" -name '*.*' -newer "$IDX" 2>/dev/null | head -1)
    [ -n "$changed" ] && stale="source changed since last /index"
  fi
fi

sr_dire
exit 0
