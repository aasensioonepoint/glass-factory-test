#!/usr/bin/env bash
# Tests for post-task-done-index.sh. Run: bash .agents/bin/post-task-done-index.test.sh
#
# Ce hook fait TROIS choses à la clôture d'une tâche : commiter les stores d'état
# (board, ledger, journal), puis les exports de run sous runs/ (seconde jambe,
# T-00000703), puis, si le dépôt en pose un, enchaîner son rafraîchisseur
# d'index. Les cas ci-dessous couvrent le déclencheur, le commit des stores, le
# commit des exports, les refus de commit, et les modes de silence.
#
# CONTRÔLE NÉGATIF OBLIGATOIRE : les cas 1 et 2 prouvent que le hook ne se
# déclenche PAS sur une commande qui ne clôt aucune tâche. Sans eux, un hook qui
# commiterait à chaque appel passerait tous les autres cas.
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/post-task-done-index.sh"
command -v git >/dev/null 2>&1 || { echo "SKIP: no git"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/.agents/state/board" "$TMP/.agents/state/memory" "$TMP/.agents/state/specs"
# The hook now delegates the commit to `tasks.py commit-stores` (the lock leg,
# T-00000189), which re-invokes THIS script's section leg by its path in the
# tree. A faithful repo therefore carries both files, so the harness provisions
# them — the real repo has them at exactly these paths.
mkdir -p "$TMP/.agents/bin"
cp "$HERE"/tasks*.py "$HERE/post-task-done-index.sh" "$TMP/.agents/bin/"
git -C "$TMP" init -q
git -C "$TMP" config user.email t@t
git -C "$TMP" config user.name t
# T-00000724 — l'interrupteur de signature est posé FAUX dans le dépôt du banc : les cas
# 1-34 restent au défaut (non signé) même si le poste porte la clé en global — la clé
# locale l'emporte. Les cas de signature (35-43, 53-57) ont leurs dépôts à eux.
git -C "$TMP" config cadre.signStateCommits false
# The POST_TASK_DONE lock is born under .agents/state/local/, which the real
# repo gitignores (.gitignore:12). The temp repo has no such entry, so the lock
# file would show as untracked and break the "stores propres après le commit"
# assertion (case 3). Write the ignore line before the first case and carry it
# in the initial commit; the existing assertion is NOT touched (plan step 5).
printf '/.agents/state/local/\n' > "$TMP/.gitignore"
printf '{"tasks":[]}\n'   > "$TMP/.agents/state/board/TASKS.json"
printf '{"entries":[]}\n' > "$TMP/.agents/state/memory/LEDGER.json"
printf '{"entries":[]}\n' > "$TMP/.agents/state/specs/SPECS.json"
git -C "$TMP" add -A && git -C "$TMP" commit -qm init

fail() { echo "FAIL: $1"; exit 1; }
# Le hook lit le JSON de l'événement sur stdin et n'inspecte que la commande.
run() { printf '{"tool_input":{"command":"%s"}}' "$1" \
        | CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK"; }
head_sha() { git -C "$TMP" rev-parse HEAD; }

# DÉTENTEUR AUXILIAIRE NOMMÉ (cas 12 et 13). Git Bash n'a PAS de `flock` et créer
# le fichier de verrou ne tient rien : les deux cas d'exclusion passent donc par
# ce processus python, qui prend le VRAI verrou POST_TASK_DONE via
# `tasks.board_lock(root, name=…)` et le tient jusqu'à ce qu'un marqueur de
# relâchement apparaisse. Aucune horloge dans l'ordonnancement — que des
# marqueurs (L-00000035).
cat > "$TMP/holder.py" <<'PYEOF'
import os, sys, time
root, ready, release = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, os.path.join(root, ".agents", "bin"))
import tasks
with tasks.board_lock(root, name=tasks.POST_TASK_DONE_LOCK):
    open(ready, "w").close()
    deadline = time.monotonic() + 30.0  # borne de SÉCURITÉ, expiration = échec
    while not os.path.exists(release):
        if time.monotonic() > deadline:
            break
        time.sleep(0.01)
PYEOF

# Attente d'un marqueur : événement causal, jamais une durée. L'expiration est
# un ÉCHEC (elle sort du until-loop et le cas asserte l'absence), non un vert.
wait_marker() {  # $1 = chemin du marqueur
  local i=0
  while [ ! -e "$1" ] && [ $i -lt 3000 ]; do sleep 0.01; i=$((i + 1)); done
}
PYBIN=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done
# Contenu DIFFÉRENT à chaque appel : réécrire deux fois la même chose ne salit
# rien du point de vue de git, et un cas suivant mesurerait alors le vide.
DIRT=0
dirty() {
  DIRT=$((DIRT + 1))
  printf '{"tasks":[{"id":"T-%s"}]}\n' "$DIRT" > "$TMP/.agents/state/board/TASKS.json"
}

# 1. NÉGATIF — une commande qui n'est pas `tasks.py done` ne commite RIEN.
#    C'est ce cas qui rend les suivants signifiants.
dirty
BEFORE="$(head_sha)"
run "python .agents/bin/tasks.py list" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] || fail "tasks.py list ne doit RIEN commiter"
[ -n "$(git -C "$TMP" status --porcelain)" ] || fail "l'arbre devait rester sale"

# 2. NÉGATIF — le faux positif historique : une commande qui MENTIONNE le nom du
#    hook (lequel contient « done ») ne doit pas déclencher le commit.
BEFORE="$(head_sha)"
run "git add .agents/bin/post-task-done-index.sh" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] || fail "mentionner le nom du hook ne doit rien commiter"

# 3. `tasks.py done` avec des stores modifiés -> commit des stores.
BEFORE="$(head_sha)"
run "python .agents/bin/tasks.py done T-1 --raison "clos par le banc"" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "done avec stores sales doit commiter"
git -C "$TMP" show --stat --oneline HEAD | grep -q 'TASKS.json' \
  || fail "le commit doit porter TASKS.json"
[ -z "$(git -C "$TMP" status --porcelain -- .agents/state)" ] \
  || fail "les stores doivent être propres après le commit"

# 4. `tasks.py done` avec des stores PROPRES -> aucun commit (pas de bruit).
BEFORE="$(head_sha)"
run "python .agents/bin/tasks.py done T-2 --raison "clos par le banc"" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] || fail "stores propres : aucun commit ne doit naître"

# 5. Le pathspec ne balaye pas ce que l'utilisateur a mis en index par ailleurs.
echo "brouillon" > "$TMP/autre.txt"
git -C "$TMP" add autre.txt
dirty
run "python .agents/bin/tasks.py done T-3 --raison "clos par le banc"" >/dev/null
git -C "$TMP" show --stat --oneline HEAD | grep -q 'autre.txt' \
  && fail "le commit du hook ne doit JAMAIS emporter un fichier tiers"
git -C "$TMP" diff --cached --name-only | grep -q 'autre.txt' \
  || fail "le fichier tiers devait rester en index, intact"

# 6. Un store DÉJÀ indexé à la main est tout de même commité (c'est pourquoi le
#    hook lit `status --porcelain` et non `diff --quiet`, qui ignore l'index).
dirty
git -C "$TMP" add .agents/state/board/TASKS.json
BEFORE="$(head_sha)"
run "python .agents/bin/tasks.py done T-4 --raison "clos par le banc"" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "un store déjà indexé doit être commité"

# 7. Opération git en cours -> report, JAMAIS un commit posé au milieu d'un
#    merge ou d'un rebase que l'utilisateur devrait ensuite réparer à la main.
dirty
: > "$TMP/.git/MERGE_HEAD"
BEFORE="$(head_sha)"
OUT7="$(run "python .agents/bin/tasks.py done T-5 --raison "clos par le banc"")"
[ "$(head_sha)" = "$BEFORE" ] || fail "aucun commit pendant un merge en cours"
printf '%s' "$OUT7" | grep -q 'MERGE_HEAD' \
  || fail "le report doit être dit, pas silencieux"
rm -f "$TMP/.git/MERGE_HEAD"

# 8. HEAD détaché -> même refus : un commit y serait un orphelin introuvable.
BEFORE="$(head_sha)"
git -C "$TMP" checkout -q --detach HEAD
run "python .agents/bin/tasks.py done T-6 --raison "clos par le banc"" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] || fail "aucun commit sur un HEAD détaché"
git -C "$TMP" checkout -q -

# 9. Reprise après le report : les stores toujours sales sont bien commités une
#    fois l'opération git terminée. Sans ce cas, un hook qui abandonnerait
#    définitivement passerait le cas 7.
BEFORE="$(head_sha)"
run "python .agents/bin/tasks.py done T-7 --raison "clos par le banc"" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "après le merge, les stores doivent partir"

# 10. Toujours advisory : hors dépôt git, le hook sort proprement sans casser.
OUTSIDE="$(mktemp -d)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-8 --raison "clos par le banc""}}' \
  | CLAUDE_PROJECT_DIR="$OUTSIDE" bash "$HOOK" >/dev/null 2>&1 \
  || fail "le hook doit rester advisory hors dépôt git (exit 0)"
rm -rf "$OUTSIDE"

# 11. SANS CLAUDE_PROJECT_DIR — le cas des hôtes Codex, Copilot et Kimi Code, qui
#     ne posent pas cette variable. La racine doit venir de `git rev-parse
#     --show-toplevel`, et depuis un SOUS-RÉPERTOIRE, sinon un `pwd` nu
#     ferait chercher les stores au mauvais endroit et le hook serait
#     silencieusement inerte sur ces trois hôtes.
mkdir -p "$TMP/sous/repertoire"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-9 --raison "clos par le banc""}}' \
  | (cd "$TMP/sous/repertoire" && env -u CLAUDE_PROJECT_DIR bash "$HOOK") >/dev/null
[ "$(head_sha)" != "$BEFORE" ] \
  || fail "sans CLAUDE_PROJECT_DIR, la racine doit venir de git rev-parse"

# --- CONCURRENCE : les trois jambes, un arm chacune (T-00000189, volet 1) ----

# 12. JAMBE VERROU — un détenteur tient le verrou AU-DELÀ de la borne courte :
#     le verbe rend `locked-out`, sort 0, et NE commite RIEN (les stores restent
#     sales). C'est la valeur 3 de la classification, le motif DIT.
if [ -n "$PYBIN" ]; then
  dirty
  "$PYBIN" "$TMP/holder.py" "$TMP" "$TMP/ready12" "$TMP/release12" &
  H12=$!
  wait_marker "$TMP/ready12"
  [ -f "$TMP/ready12" ] || fail "cas12: le détenteur auxiliaire n'a pas pris le verrou"
  BEFORE="$(head_sha)"
  TOK12="$("$PYBIN" "$TMP/.agents/bin/tasks.py" --root "$TMP" commit-stores --lock-timeout 0.3)"
  RC12=$?
  : > "$TMP/release12"; wait $H12
  [ "$TOK12" = "locked-out" ] || fail "cas12: attendu 'locked-out', obtenu [$TOK12]"
  [ "$RC12" = "0" ] || fail "cas12: le verbe doit sortir 0 même verrouillé dehors"
  [ "$(head_sha)" = "$BEFORE" ] || fail "cas12: rien ne doit être commité verrou tenu dehors"
  [ -n "$(git -C "$TMP" status --porcelain -- .agents/state/board)" ] \
    || fail "cas12: les stores doivent rester sales quand le verrou est tenu"
else
  echo "SKIP cas12: aucun python (précédent test_dashboard.py:5773-5793)"
fi

# 13. JAMBE VERROU — un détenteur tient brièvement puis relâche ; le verbe
#     CONTEND, attend, puis commite. L'ordre est prouvé par la SÉMANTIQUE du
#     verrou (committer exige d'avoir pris le verrou, donc d'attendre le
#     relâchement), asserté sur le JETON, jamais sur une durée.
if [ -n "$PYBIN" ]; then
  dirty
  "$PYBIN" "$TMP/holder.py" "$TMP" "$TMP/ready13" "$TMP/release13" &
  H13=$!
  wait_marker "$TMP/ready13"
  [ -f "$TMP/ready13" ] || fail "cas13: le détenteur auxiliaire n'a pas pris le verrou"
  BEFORE="$(head_sha)"
  ( "$PYBIN" "$TMP/.agents/bin/tasks.py" --root "$TMP" commit-stores > "$TMP/tok13" 2>/dev/null ) &
  V13=$!
  : > "$TMP/release13"; wait $H13; wait $V13
  [ "$(cat "$TMP/tok13")" = "committed" ] \
    || fail "cas13: le verbe devait committer APRÈS relâchement, obtenu [$(cat "$TMP/tok13")]"
  [ "$(head_sha)" != "$BEFORE" ] || fail "cas13: HEAD doit avancer après le relâchement"
else
  echo "SKIP cas13: aucun python"
fi

# 14. JAMBE EXTERNE — (a) PATH vidé de tout python → dégradé, commit QUAND MÊME
#     sans verrou, exit 0, classification dite ; (b) variante « résolu mais
#     mort » : un python3 en tête qui échoue à --version, suivi d'un vrai → le
#     résolveur le SAUTE (c'est l'arm qui distingue absent de résolu-mais-mort).
# Les stubs SHADOWENT les vrais python par leur NOM (placés en tête de PATH) :
# le reste de PATH — git, bash, coreutils — demeure, donc le hook tourne mais
# aucun python ne résout.
STUB="$TMP/stub"; mkdir -p "$STUB"
for n in python3 python py; do printf '#!/usr/bin/env bash\nexit 1\n' > "$STUB/$n"; chmod +x "$STUB/$n"; done
dirty
BEFORE="$(head_sha)"
OUT14="$(printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-14 --raison "clos par le banc""}}' \
  | PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK")"
RC14=$?
[ "$RC14" = "0" ] || fail "cas14a: le hook doit sortir 0 sans python"
[ "$(head_sha)" != "$BEFORE" ] || fail "cas14a: le commit dégradé sans python doit avoir lieu"
printf '%s' "$OUT14" | grep -qE 'sans verrou.*interpr' \
  || fail "cas14a: la classification dégradée (interpréteur introuvable) doit être dite, obtenu [$OUT14]"

# 14b. Un python3 mort en tête, un vrai python derrière : le résolveur SAUTE le
#      mort et prend le vivant, donc PAS de dégradé et un commit via le verrou.
#      Le « vrai python derrière » est un SHIM `python` VIVANT fabriqué ici — un
#      script qui exec le python réel du système par CHEMIN ABSOLU (résolu hors
#      du PATH pollué), posé dans le MÊME répertoire de PATH que le stub `python3`
#      mort. Sans lui, le cas dépendrait d'un `python` nu du système : absent sur
#      macOS (seul `python3` existe), le résolveur sauterait le python3 mort, ne
#      trouverait ni `python` ni `py`, et DÉGRADERAIT — un faux rouge. Avec le
#      shim, les trois plateformes prouvent réellement « saute le mort, prend le
#      vivant suivant », sans dépendre d'un interpréteur nu du système. Le shim
#      exec un chemin ABSOLU, donc il est immunisé au python3 mort en tête de
#      PATH (aucune ré-résolution par nom).
if [ -n "$PYBIN" ]; then
  STUB2="$TMP/stub2"; mkdir -p "$STUB2"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$STUB2/python3"; chmod +x "$STUB2/python3"
  REALPY="$(command -v "$PYBIN")"
  printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$REALPY" > "$STUB2/python"; chmod +x "$STUB2/python"
  dirty
  BEFORE="$(head_sha)"
  OUT14B="$(printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-14 --raison "clos par le banc"b"}}' \
    | PATH="$STUB2:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK")"
  [ "$(head_sha)" != "$BEFORE" ] || fail "cas14b: commit doit avoir lieu via le python vivant"
  printf '%s' "$OUT14B" | grep -q 'sans verrou' \
    && fail "cas14b: un python3 mort ne doit PAS forcer le dégradé — le suivant vivant est pris"
  printf '%s' "$OUT14B" | grep -q 'stores commit' \
    || fail "cas14b: classification 'stores commités' attendue, obtenu [$OUT14B]"
else
  echo "SKIP cas14b: aucun python réel pour fabriquer le shim vivant (résolu-mais-mort)"
fi

# 15. normalize_root — la forme MSYS /c/... que les hooks produisent et la
#     racine native résolvent au MÊME verrou (verrou et commit ne divergent
#     pas) ; no-op sur une racine native. Windows uniquement (le /c/ n'existe
#     comme arbre natif que là) ; ailleurs, SKIP nommé.
if [ -n "$PYBIN" ] && command -v cygpath >/dev/null 2>&1; then
  # La forme /c/... est fabriquée EN PYTHON, pas passée en argv : l'argv d'un
  # python.exe NATIF lancé sous Git Bash subit la conversion de chemins MSYS,
  # qui re-transforme /c/Users -> C:\Users avant que python ne la voie (le piège
  # « Traduction d'argv » du plan). La vraie valeur /c/... atteint normalize_root
  # par le DÉFAUT d'environnement CLAUDE_PROJECT_DIR, jamais par argv (L-00000063),
  # donc on reconstruit la chaîne à l'intérieur, intacte.
  MIXED="$(cygpath -m "$TMP")"   # C:/Users/.../tmp.XXXX (natif, sûr en argv)
  OUT15="$("$PYBIN" - "$MIXED" "$TMP" <<'PYEOF'
import os, sys
native, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, ".agents", "bin"))
import tasks
assert tasks.normalize_root(native) == native, "no-op natif casse"
assert native[1:2] == ":", f"racine native inattendue: {native!r}"
msys = "/" + native[0].lower() + native[2:].replace("\\", "/")  # /c/Users/...
got = tasks.normalize_root(msys)
a = str(tasks.lock_path(got, tasks.POST_TASK_DONE_LOCK).resolve())
b = str(tasks.lock_path(native, tasks.POST_TASK_DONE_LOCK).resolve())
assert a == b, f"verrou sous deux arbres: {a!r} != {b!r}"
# non-vacuite : la branche de traduction a bien couru (msys != got)
assert msys.startswith("/") and got != msys, f"traduction inerte: {msys!r} -> {got!r}"
print("CAS15_OK")
PYEOF
)"
  [ "$OUT15" = "CAS15_OK" ] || fail "cas15: normalize_root diverge, sortie [$OUT15]"
else
  echo "SKIP cas15: pas de cygpath (non Windows) — /c/ n'existe pas comme arbre natif"
fi

# 16. JAMBE GRAPHE DE SPECS — le canal se vérifie à SON bout ÉCRIVAIN
#     (T-00000379 lot E). Le lecteur est prouvé ailleurs, par
#     `test_specs_graph.py` (round-trip par le vrai `dashboard_readers`) ; ici
#     on prouve que quelqu'un ÉCRIT, sans quoi la vue serait un cadre vide
#     branché sur rien.
#
#     Le harnais ne provisionnait pas le générateur : la garde d'existence du
#     hook le rendait donc muet dans TOUS les cas précédents — c'est voulu, ils
#     restent inchangés. Ici on l'installe, avec ses trois dépendances de store
#     et l'interface de lecture par laquelle il les lit (`etat_lecture.py`).
mkdir -p "$TMP/.agents/state/index"
cp "$HERE/specs_graph.py" "$HERE/specs.py" "$HERE/ledger.py" "$HERE/etat_lecture.py" "$TMP/.agents/bin/"
printf '{"next_id":2,"tasks":[{"id":"T-00000001","state":"pending","task":"graphe","owner":"","stage":"","updated":"2026-08-26"}]}\n' \
  > "$TMP/.agents/state/board/TASKS.json"
printf '{"next_id":2,"entries":[{"id":"S-00000001","task":"T-00000001","kind":"plan","title":"p","text":"","files":[],"date":"2026-08-26"}]}\n' \
  > "$TMP/.agents/state/specs/SPECS.json"
GRAPHE="$TMP/.agents/state/index/SPECS_GRAPH.json"
rm -f "$GRAPHE"
run "python .agents/bin/tasks.py done T-16 --raison "clos par le banc"" >/dev/null
[ -f "$GRAPHE" ] || fail "cas16: la cloture n a PAS publie le graphe — la vue serait branchee sur rien"
grep -q '"generator"' "$GRAPHE" \
  || fail "cas16: le graphe publie ne porte pas le marqueur generator"

#     Et la precedence tient A TRAVERS le hook : une publication MANUELLE (sans
#     marqueur) survit a une cloture. C'est ce qui rend sur de laisser ce
#     declencheur tourner sans surveillance.
printf '{"version":1,"nodes":[{"id":"E-01","title":"a la main"}]}\n' > "$GRAPHE"
run "python .agents/bin/tasks.py done T-16 --raison "clos par le banc"b" >/dev/null
grep -q '"a la main"' "$GRAPHE" \
  || fail "cas16: une publication MANUELLE a ete ecrasee par le hook"
grep -q '"generator"' "$GRAPHE" \
  && fail "cas16: le hook a marque une publication manuelle comme generee"
rm -f "$GRAPHE"

# 17. JAMBE EXTERNE — une sortie d'index contenant \, " et \r : le JSON émis
#     PARSE (le trou de sanitisation préexistant est fermé). Ce cas est LE
#     dernier : il installe un scripts/index-refresh.sh qui change la sortie.
mkdir -p "$TMP/scripts"
cat > "$TMP/scripts/index-refresh.sh" <<'EOS'
#!/usr/bin/env bash
printf 'a\\b"c\rd'
EOS
chmod +x "$TMP/scripts/index-refresh.sh"
dirty
OUT17="$(run "python .agents/bin/tasks.py done T-17 --raison "clos par le banc"")"
printf '%s' "$OUT17" \
  | "${PYBIN:-python}" -c "import sys,json; json.loads(sys.stdin.buffer.read().decode('utf-8'))" \
  || fail "cas17: le JSON émis ne parse pas — le trou de sanitisation est rouvert [$OUT17]"

# --- SÉLECTEUR run-exports : le commit des exports de run (T-00000677) --------
# La nuit ne pouvait plus clore son état — rien ne commitait `runs/`, donc le SHA
# poussé ne portait jamais les événements de la nuit (S-00001808/S-00001809). La
# jambe section porte désormais un second sélecteur ; ces cas l'exercent EN
# DIRECT (`--commit-section <root> run-exports`).

# 18. run-exports commite un export de run MODIFIÉ, et NE commite PAS les trois
#     stores d'état (pas de mélange de sujets), sous un sujet `chore(runs):`.
#     Les fixtures ont la PROFONDEUR du contrat, `runs/<auteur>/<copie>/<mois>.jsonl`
#     — c'est la forme que le pathspec `:(glob)runs/*/*/*.jsonl` de la jambe capte,
#     et un fichier posé un cran plus haut n'est pas un export (cas 27).
mkdir -p "$TMP/runs/lot/copie"
printf 'a\n' > "$TMP/runs/lot/copie/2026-09.jsonl"
git -C "$TMP" add runs/lot/copie/2026-09.jsonl
git -C "$TMP" commit -qm "seed runs export"
printf 'a\nb\n' > "$TMP/runs/lot/copie/2026-09.jsonl"   # export tracké MODIFIÉ
printf 'nuit\n' > "$TMP/runs/lot/copie/2026-10.jsonl"   # export NOUVEAU (untracked) : les
                                                        # événements de la nuit (S-00001808)
dirty                                                   # store d'état sale EN MÊME TEMPS
BEFORE="$(head_sha)"
TOK18="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
[ "$TOK18" = "committed" ] || fail "cas18: attendu 'committed', obtenu [$TOK18]"
[ "$(head_sha)" != "$BEFORE" ] || fail "cas18: un export modifié doit être commité"
git -C "$TMP" show --stat --oneline HEAD | grep -q 'runs/lot/copie/2026-09.jsonl' \
  || fail "cas18: le commit doit porter l'export tracké modifié"
git -C "$TMP" show --stat --oneline HEAD | grep -q 'runs/lot/copie/2026-10.jsonl' \
  || fail "cas18: le commit doit porter le NOUVEL export untracked (événements de la nuit)"
git -C "$TMP" show --stat --oneline HEAD | grep -q 'TASKS.json' \
  && fail "cas18: run-exports ne doit PAS emporter les stores d'état (mélange de sujets)"
git -C "$TMP" show -s --format='%s' HEAD | grep -q '^chore(runs):' \
  || fail "cas18: sujet de commit attendu 'chore(runs): ...'"
[ -n "$(git -C "$TMP" status --porcelain -- .agents/state/board)" ] \
  || fail "cas18: les stores d'état doivent rester sales — run-exports ne les touche pas"

# 19. Un sélecteur inconnu reste un `failed` explicite, jamais un balayage.
TOK19="$(bash "$HOOK" --commit-section "$TMP" selecteur-inexistant)"
[ "$TOK19" = "failed" ] || fail "cas19: un sélecteur inconnu doit rendre 'failed', obtenu [$TOK19]"

# 20. Rien à commiter sous runs/ (propre après le cas 18) -> aucun commit, succès
#     silencieux (jeton 'nothing'), jamais un commit vide ni un 'failed'.
[ -z "$(git -C "$TMP" status --porcelain -- runs)" ] \
  || fail "cas20: pré-condition — runs/ doit être propre après le commit du cas 18"
BEFORE="$(head_sha)"
TOK20="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
[ "$TOK20" = "nothing" ] || fail "cas20: rien à commiter doit rendre 'nothing', obtenu [$TOK20]"
[ "$(head_sha)" = "$BEFORE" ] || fail "cas20: aucun commit ne doit naître quand runs/ est propre"

# 21. VERBE CLI — `tasks.py commit-run-exports` : la jambe verrou du commit des
#     exports, calquée sur `commit-stores`. Prend le verrou POST_TASK_DONE, joue
#     la jambe section avec le sélecteur run-exports, relaie le jeton. Prouve le
#     câblage verbe -> verrou -> sélecteur (l'entrée que joue la clôture de nuit).
if [ -n "$PYBIN" ]; then
  printf 'a\nb\nc\n' > "$TMP/runs/lot/copie/2026-09.jsonl"   # nouvel export à commiter
  BEFORE="$(head_sha)"
  TOK21="$("$PYBIN" "$TMP/.agents/bin/tasks.py" --root "$TMP" commit-run-exports)"
  RC21=$?
  [ "$TOK21" = "committed" ] || fail "cas21: attendu 'committed', obtenu [$TOK21]"
  [ "$RC21" = "0" ] || fail "cas21: le verbe doit sortir 0"
  [ "$(head_sha)" != "$BEFORE" ] || fail "cas21: HEAD doit avancer après le commit des exports"
  git -C "$TMP" show --stat --oneline HEAD | grep -q 'runs/lot/copie/2026-09.jsonl' \
    || fail "cas21: le commit du verbe doit porter l'export de run"
else
  echo "SKIP cas21: aucun python pour le verbe commit-run-exports"
fi

# --- JAMBE RUN-EXPORTS DU HOOK DE `done` (T-00000703) ----------------------
# Jusqu'ici la jambe externe ne commitait que les stores : un `done` de journée
# laissait `runs/` sale (l'écrit d'export du pont V3 PRÉCÈDE le hook), et seule la
# clôture de nuit jouait le verbe. Le hook enchaîne désormais une SECONDE jambe,
# `tasks.py commit-run-exports`, sous le même verrou, en un commit DISTINCT.

# 22. ENCHAÎNEMENT RÉEL par la jambe externe : stores ET runs/ sales → DEUX
#     commits, jamais fusionnés — HEAD porte `chore(runs):`, HEAD~1 `chore(state):`,
#     et la sortie dit les deux jambes. Mutation qui rougit : retirer la jambe.
if [ -n "$PYBIN" ]; then
  dirty
  printf 'a\nb\nc\nd\n' > "$TMP/runs/lot/copie/2026-09.jsonl"
  BEFORE="$(head_sha)"
  OUT22="$(run "python .agents/bin/tasks.py done T-22 --raison "clos par le banc"")"
  [ "$(head_sha)" != "$BEFORE" ] || fail "cas22: done avec stores et runs/ sales doit commiter"
  git -C "$TMP" show -s --format='%s' HEAD | grep -q '^chore(runs):' \
    || fail "cas22: HEAD doit être le commit des exports, obtenu [$(git -C "$TMP" show -s --format='%s' HEAD)]"
  git -C "$TMP" show -s --format='%s' HEAD~1 | grep -q '^chore(state):' \
    || fail "cas22: HEAD~1 doit être le commit des stores, obtenu [$(git -C "$TMP" show -s --format='%s' HEAD~1)]"
  git -C "$TMP" show --stat --oneline HEAD | grep -q 'TASKS.json' \
    && fail "cas22: le commit des exports ne doit PAS emporter les stores (mélange de sujets)"
  printf '%s' "$OUT22" | grep -q 'stores commit' \
    || fail "cas22: la jambe stores doit être dite, obtenu [$OUT22]"
  printf '%s' "$OUT22" | grep -q 'exports commit' \
    || fail "cas22: la jambe exports doit être dite, obtenu [$OUT22]"
  [ -z "$(git -C "$TMP" status --porcelain -- runs .agents/state)" ] \
    || fail "cas22: stores et runs/ doivent être propres après les deux commits"
else
  echo "SKIP cas22: aucun python pour la jambe run-exports"
fi

# 22b. Stores PROPRES, runs/ sale : la seconde jambe commite seule, et la sortie
#      ne prétend pas un commit de stores qui n'a pas eu lieu.
if [ -n "$PYBIN" ]; then
  printf 'a\nb\nc\nd\ne\n' > "$TMP/runs/lot/copie/2026-09.jsonl"
  BEFORE="$(head_sha)"
  OUT22B="$(run "python .agents/bin/tasks.py done T-22b --raison "clos par le banc"")"
  [ "$(head_sha)" != "$BEFORE" ] || fail "cas22b: runs/ sale seul doit commiter"
  git -C "$TMP" show -s --format='%s' HEAD | grep -q '^chore(runs):' \
    || fail "cas22b: HEAD doit être le commit des exports"
  printf '%s' "$OUT22B" | grep -q 'exports commit' \
    || fail "cas22b: 'exports commités' attendu, obtenu [$OUT22B]"
  printf '%s' "$OUT22B" | grep -q 'stores commit' \
    && fail "cas22b: stores propres — 'stores commités' ne doit PAS être dit [$OUT22B]"
else
  echo "SKIP cas22b: aucun python pour la jambe run-exports"
fi

# 23. NÉGATIF — opération git en cours : la jambe stores rend `busy:`, et la
#     jambe exports n'est PAS tentée (elle refuserait pareil et doublerait le
#     texte). La sortie ne parle donc pas d'exports. Mutation qui rougit :
#     remplacer l'arm `committed|nothing|failed|locked-out)` par `*)`.
if [ -n "$PYBIN" ]; then
  dirty
  printf 'a\nb\nc\nd\ne\nf\n' > "$TMP/runs/lot/copie/2026-09.jsonl"
  : > "$TMP/.git/MERGE_HEAD"
  BEFORE="$(head_sha)"
  OUT23="$(run "python .agents/bin/tasks.py done T-23 --raison "clos par le banc"")"
  rm -f "$TMP/.git/MERGE_HEAD"
  [ "$(head_sha)" = "$BEFORE" ] || fail "cas23: aucun commit pendant un merge en cours"
  printf '%s' "$OUT23" | grep -q 'MERGE_HEAD' \
    || fail "cas23: le report des stores doit être dit, obtenu [$OUT23]"
  printf '%s' "$OUT23" | grep -q 'exports' \
    && fail "cas23: sur busy la jambe exports ne doit PAS être tentée ni dite [$OUT23]"
  [ -n "$(git -C "$TMP" status --porcelain -- runs)" ] \
    || fail "cas23: runs/ doit rester sale quand la jambe est sautée"
else
  echo "SKIP cas23: aucun python pour la jambe run-exports"
fi

# 24. TRONCATURE — un détenteur tient POST_TASK_DONE au-delà de la borne : les
#     DEUX jambes rendent `locked-out`, et les DEUX motifs survivent à la borne
#     de classification (240, plus 120 : la paire fait 131 octets). Mutation qui
#     rougit : borne 240 → 120, le second motif est coupé, le compte tombe à 1.
#     Frère non vide du même run : la jambe stores est dite exactement une fois.
if [ -n "$PYBIN" ]; then
  dirty
  "$PYBIN" "$TMP/holder.py" "$TMP" "$TMP/ready24" "$TMP/release24" &
  H24=$!
  wait_marker "$TMP/ready24"
  [ -f "$TMP/ready24" ] || fail "cas24: le détenteur auxiliaire n'a pas pris le verrou"
  BEFORE="$(head_sha)"
  OUT24="$(run "python .agents/bin/tasks.py done T-24 --raison "clos par le banc"")"
  : > "$TMP/release24"; wait $H24
  [ "$(head_sha)" = "$BEFORE" ] || fail "cas24: rien ne doit être commité verrou tenu dehors"
  N24="$(printf '%s' "$OUT24" | grep -o 'au-delà de la borne)' | grep -c .)"
  [ "$N24" = "2" ] \
    || fail "cas24: les DEUX motifs locked-out doivent survivre à la borne, compte [$N24] dans [$OUT24]"
  [ "$(printf '%s' "$OUT24" | grep -c 'stores non commit')" = "1" ] \
    || fail "cas24: la jambe stores doit être dite exactement une fois [$OUT24]"
else
  echo "SKIP cas24: aucun python pour tenir le verrou"
fi

# 25. PIN NÉGATIF DOC — la doctrine ne dit plus que le hook de `done` ne porte
#     que les stores : les deux clauses d'exclusivité de task-board/SKILL.md ont
#     été réécrites avec la jambe (l'autre « those three paths and nothing else »
#     est le pathspec des stores, qui reste vrai et n'est pas chassé).
SKILL25="$(dirname "$0")/../skills/task-board/SKILL.md"
[ -f "$SKILL25" ] || fail "cas25: task-board/SKILL.md introuvable à côté du hook"
grep -q 'stores and nothing else' "$SKILL25" \
  && fail "cas25: la doctrine affirme encore que le hook ne porte que les stores"
grep -q 'never sweeps' "$SKILL25" \
  && fail "cas25: la doctrine affirme encore que le hook ne balaie jamais runs/"

# --- CORRECTION T-00000703 (binôme + sécurité) : pathspec de FORME, refus des
# liens, index propre sur échec, chemin dégradé DIT, garde de réponse -----------

# Pré-condition commune : runs/ porte encore la saleté des cas 23-24 (report et
# verrou). On la ravale par la jambe elle-même, pour que chaque cas ci-dessous
# mesure SA fixture et rien d'autre.
TOKPRE="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
[ "$TOKPRE" = "committed" ] || fail "pré-26: ravaler runs/ devait rendre 'committed', obtenu [$TOKPRE]"
[ -z "$(git -C "$TMP" status --porcelain --untracked-files=all -- runs)" ] \
  || fail "pré-26: runs/ doit être propre avant les cas 26-31"

# 26. `status.showUntrackedFiles=no` posé dans le dépôt : un NOUVEAU mois d'export
#     (untracked, seul changement sous runs/) doit quand même être vu et commité —
#     la jambe passe `--untracked-files=all` sur la ligne de commande, qui prime
#     sur la config. Mutation qui rougit : retirer `--untracked-files=all` du
#     `status` de la jambe (le nouveau mois devient invisible → `nothing`).
git -C "$TMP" config status.showUntrackedFiles no
printf 'novembre\n' > "$TMP/runs/lot/copie/2026-11.jsonl"
BEFORE="$(head_sha)"
TOK26="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
git -C "$TMP" config --unset status.showUntrackedFiles
[ "$TOK26" = "committed" ] || fail "cas26: attendu 'committed' malgré showUntrackedFiles=no, obtenu [$TOK26]"
[ "$(head_sha)" != "$BEFORE" ] || fail "cas26: le nouveau mois d'export doit être commité"
git -C "$TMP" show --stat --oneline HEAD | grep -q 'runs/lot/copie/2026-11.jsonl' \
  || fail "cas26: le commit doit porter le nouveau mois d'export"

# 27. PATHSPEC DE FORME — ce qui n'est pas `runs/<auteur>/<copie>/<mois>.jsonl` n'est
#     JAMAIS commité : un `.borne.tmp` à la bonne profondeur, un fichier d'outil
#     tiers `runs/X/events.out.tfevents.1`, un `.jsonl` un cran trop profond. La
#     jambe rend `nothing` (rien de sa forme n'a bougé), HEAD ne bouge pas, et
#     aucun des trois n'entre dans l'index. Mutation qui rougit : revenir au
#     pathspec `runs` nu (les trois partent dans un `chore(runs):`).
mkdir -p "$TMP/runs/X" "$TMP/runs/lot/copie/profond"
printf 'tmp\n' > "$TMP/runs/lot/copie/.borne.tmp"
printf 'tf\n'  > "$TMP/runs/X/events.out.tfevents.1"
printf 'x\n'   > "$TMP/runs/lot/copie/profond/2026-09.jsonl"
BEFORE="$(head_sha)"
TOK27="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
[ "$TOK27" = "nothing" ] || fail "cas27: hors forme, la jambe doit rendre 'nothing', obtenu [$TOK27]"
[ "$(head_sha)" = "$BEFORE" ] || fail "cas27: aucun commit ne doit naître pour des fichiers hors forme"
git -C "$TMP" diff --cached --quiet || fail "cas27: l'index doit rester vide"
git -C "$TMP" ls-files -- runs | grep -qE 'borne\.tmp|tfevents|profond/' \
  && fail "cas27: un fichier hors forme est entré dans git : [$(git -C "$TMP" ls-files -- runs)]"
rm -rf "$TMP/runs/X" "$TMP/runs/lot/copie/profond"
rm -f "$TMP/runs/lot/copie/.borne.tmp"

# 28. LIEN SYMBOLIQUE sous runs/ → `failed`, index propre, rien de commité : un lien
#     nommé comme un export pointerait hors de l'arbre. SKIP nommé là où `ln -s`
#     n'est pas permis (Windows sans privilège). Mutation qui rougit : retirer le
#     `find -type l` de la jambe (le lien est commité tel quel → `committed`).
if ln -s /cible/inexistante "$TMP/runs/lot/copie/lien.jsonl" 2>/dev/null; then
  BEFORE="$(head_sha)"
  TOK28="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
  [ "$TOK28" = "failed" ] || fail "cas28: un lien symbolique sous runs/ doit rendre 'failed', obtenu [$TOK28]"
  [ "$(head_sha)" = "$BEFORE" ] || fail "cas28: aucun commit avec un lien symbolique sous runs/"
  git -C "$TMP" diff --cached --quiet || fail "cas28: l'index doit rester propre après le refus"
  rm -f "$TMP/runs/lot/copie/lien.jsonl"
else
  echo "SKIP cas28: ln -s refusé sur cette plateforme"
fi

# 28b. LIEN SYMBOLIQUE sous `sync_outbox/` (T-00001058, clôture) → `failed` pour la jambe
#      `stores`, index propre, rien de commité : un lien nommé comme un fichier d'intent
#      entrerait dans l'historique, comme sous runs/. Lien retiré, la jambe commite.
#      SKIP nommé là où `ln -s` n'est pas permis. Mutation qui rougit : retirer le
#      `find -type l` de la jambe `stores` (le lien est commité → `committed`).
OUTBOX28="$TMP/.agents/state/board/sync_outbox"
mkdir -p "$OUTBOX28"
if ln -s /cible/inexistante "$OUTBOX28/00000000000000000001-lien.json" 2>/dev/null; then
  dirty
  BEFORE="$(head_sha)"
  TOK28B="$(bash "$HOOK" --commit-section "$TMP" stores)"
  [ "$TOK28B" = "failed" ] || fail "cas28b: un lien sous sync_outbox/ doit rendre 'failed', obtenu [$TOK28B]"
  [ "$(head_sha)" = "$BEFORE" ] || fail "cas28b: aucun commit avec un lien symbolique sous sync_outbox/"
  git -C "$TMP" diff --cached --quiet || fail "cas28b: l'index doit rester propre après le refus"
  rm -f "$OUTBOX28/00000000000000000001-lien.json"
  TOK28C="$(bash "$HOOK" --commit-section "$TMP" stores)"
  [ "$TOK28C" = "committed" ] || fail "cas28b: lien retiré, la jambe doit commiter, obtenu [$TOK28C]"
else
  echo "SKIP cas28b: ln -s refusé sur cette plateforme"
fi
rmdir "$OUTBOX28" 2>/dev/null

# 29. ÉCHEC DE COMMIT (identité absente, `user.useConfigOnly`) → `failed` ET index
#     PROPRE, pour les DEUX jambes : l'`add` de la jambe est défait avant le jeton,
#     sinon le prochain geste git de l'utilisateur emporte ces chemins sans le
#     savoir. Mutation qui rougit : retirer le `git reset -q --` du chemin d'échec
#     (`git diff --cached --quiet` rend 1).
mkdir -p "$TMP/nohome"
git -C "$TMP" config user.useConfigOnly true
git -C "$TMP" config --unset user.email
git -C "$TMP" config --unset user.name
printf 'decembre\n' > "$TMP/runs/lot/copie/2026-12.jsonl"
dirty
BEFORE="$(head_sha)"
TOK29E="$(env -u EMAIL -u GIT_AUTHOR_EMAIL -u GIT_AUTHOR_NAME -u GIT_COMMITTER_EMAIL -u GIT_COMMITTER_NAME \
  HOME="$TMP/nohome" XDG_CONFIG_HOME="$TMP/nohome" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  bash "$HOOK" --commit-section "$TMP" run-exports)"
TOK29S="$(env -u EMAIL -u GIT_AUTHOR_EMAIL -u GIT_AUTHOR_NAME -u GIT_COMMITTER_EMAIL -u GIT_COMMITTER_NAME \
  HOME="$TMP/nohome" XDG_CONFIG_HOME="$TMP/nohome" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  bash "$HOOK" --commit-section "$TMP" stores)"
git -C "$TMP" config --unset user.useConfigOnly
git -C "$TMP" config user.email t@t
git -C "$TMP" config user.name t
[ "$TOK29E" = "failed" ] || fail "cas29: sans identité la jambe exports doit rendre 'failed', obtenu [$TOK29E]"
[ "$TOK29S" = "failed" ] || fail "cas29: sans identité la jambe stores doit rendre 'failed', obtenu [$TOK29S]"
[ "$(head_sha)" = "$BEFORE" ] || fail "cas29: aucun commit ne doit naître sans identité"
git -C "$TMP" diff --cached --quiet \
  || fail "cas29: l'index doit être propre après un commit en échec : [$(git -C "$TMP" diff --cached --name-only)]"
[ -n "$(git -C "$TMP" status --porcelain --untracked-files=all -- runs .agents/state)" ] \
  || fail "cas29: l'arbre doit rester sale (rien n'a été perdu, rien n'a été commité)"

# 30. CHEMIN DÉGRADÉ (aucun python) : la jambe exports n'est PAS tentée, mais un
#     export non commité sous runs/ est DIT — « non tentés » — plutôt que tu, car
#     le silence se lisait « rien à commiter » (F4). Stores PROPRES pour isoler la
#     clause ; runs/ reste sale (repris au prochain `done`). Mutation qui rougit :
#     revenir à `*) : ;;` (silence sur le chemin dégradé).
TOKPRE30="$(bash "$HOOK" --commit-section "$TMP" stores)"
[ "$TOKPRE30" = "committed" ] || fail "pré-30: ravaler les stores devait rendre 'committed', obtenu [$TOKPRE30]"
[ -z "$(git -C "$TMP" status --porcelain -- .agents/state)" ] || fail "pré-30: stores propres attendus"
BEFORE="$(head_sha)"
OUT30="$(printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-30 --raison "clos par le banc""}}' \
  | PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" 2>/dev/null)"
[ "$(head_sha)" = "$BEFORE" ] || fail "cas30: stores propres et exports non tentés — rien ne doit être commité"
printf '%s' "$OUT30" | grep -q 'exports non commités (non tentés : chemin dégradé)' \
  || fail "cas30: le chemin dégradé doit DIRE les exports non tentés, obtenu [$OUT30]"
[ -n "$(git -C "$TMP" status --porcelain --untracked-files=all -- runs)" ] \
  || fail "cas30: runs/ doit rester sale sur le chemin dégradé"
TOKPOST30="$(bash "$HOOK" --commit-section "$TMP" run-exports)"
[ "$TOKPOST30" = "committed" ] || fail "post-30: ravaler runs/ devait rendre 'committed', obtenu [$TOKPOST30]"

# 31. GARDE DE RÉPONSE — la ligne de succès se cherche dans `tool_response` SEUL
#     (S-00001927, mesuré avec dégât : 858c5ac/fcc7b2d sur le dépôt vivant).
#     (a) une commande qui CITE la ligne, réponse sans elle → AUCUN commit, avec
#     python comme sans (repli textuel) ; (b) la ligne dans la réponse, flèche
#     brute → commit ; (c) flèche échappée `→` → commit, avec python comme
#     sans ; (d) clé `tool_response` IMBRIQUÉE dans `tool_input` d'une charge
#     sans section de réponse → comportement d'avant (commit), le parse ne
#     refuse pas ce que l'en-tête `grep` a pris pour une section. La ligne est
#     ASSEMBLÉE ici, jamais écrite en clair : ce fichier est lu par des commandes
#     que le hook de CE dépôt inspecte. La commande de (a) enchaîne par `&&` et
#     non `;` : le déclencheur exige un BLANC après `done`, et un `;` collé le
#     ferait sortir AVANT la garde — le cas serait alors vert sous toute
#     mutation (mesuré : la forme `done;` passait la mutation M1). Mutation qui
#     rougit : chercher la ligne dans toute la charge (a commite).
ARROW="$(printf '\342\206\222')"
OKLINE="TASKS: T-31 ${ARROW} done"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"echo tasks.py done && echo %s"},"tool_response":{"stdout":"x"}}' "$OKLINE" \
  > "$TMP/charge31a.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31a.json" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] \
  || fail "cas31a: une commande qui CITE la ligne de succès ne doit rien commiter (parse JSON)"
PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31a.json" >/dev/null 2>&1
[ "$(head_sha)" = "$BEFORE" ] \
  || fail "cas31a: une commande qui CITE la ligne de succès ne doit rien commiter (repli sans python)"
[ -n "$(git -C "$TMP" status --porcelain -- .agents/state/board)" ] || fail "cas31a: les stores doivent rester sales"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-31"},"tool_response":{"stdout":"%s\\n"}}' "$OKLINE" \
  > "$TMP/charge31b.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31b.json" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "cas31b: la ligne de succès dans la réponse doit commiter"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-31"},"tool_response":{"stdout":"TASKS: T-31 \\u2192 done"}}' \
  > "$TMP/charge31c.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31c.json" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "cas31c: la flèche échappée dans la réponse doit commiter (parse JSON)"
dirty
BEFORE="$(head_sha)"
PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31c.json" >/dev/null 2>&1
[ "$(head_sha)" != "$BEFORE" ] || fail "cas31c: la flèche échappée dans la réponse doit commiter (repli sans python)"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-31","tool_response":"citee"}}' \
  > "$TMP/charge31d.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31d.json" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] \
  || fail "cas31d: sans section de réponse au premier niveau, le comportement d'avant (commit) doit tenir"

# 31e. GRAMMAIRE D'ID MIXTE (T-00001040, étape 4 du plan de T-00000726) : la ligne
#      de succès d'une tâche `T-<ULID>` déclenche le commit comme celle d'une
#      ancienne (31b), flèche brute (parse JSON) ET échappée (repli sans python) ;
#      (f) contrôle négatif : `T-0<ULID>` (27 symboles) n'est PAS une ligne de
#      succès. Fixture FIXE, corps qui finit par une lettre. MUTANT M4 : motif du
#      hook revenu à l'ancienne grammaire (chiffres seuls) ⇒ (e) ne commite pas, rouge.
ULID31="01M3250V003HCPQKTZ8ENYF4VM"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-%s"},"tool_response":{"stdout":"TASKS: T-%s %s done\\n"}}' \
  "$ULID31" "$ULID31" "$ARROW" > "$TMP/charge31e.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31e.json" >/dev/null
[ "$(head_sha)" != "$BEFORE" ] || fail "cas31e: la ligne de succès d'un T-<ULID> doit commiter (parse JSON)"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-%s"},"tool_response":{"stdout":"TASKS: T-%s \\u2192 done"}}' \
  "$ULID31" "$ULID31" > "$TMP/charge31e2.json"
PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31e2.json" >/dev/null 2>&1
[ "$(head_sha)" != "$BEFORE" ] || fail "cas31e: T-<ULID>, flèche échappée, repli sans python : doit commiter"
dirty
BEFORE="$(head_sha)"
printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-0%s"},"tool_response":{"stdout":"TASKS: T-0%s %s done\\n"}}' \
  "$ULID31" "$ULID31" "$ARROW" > "$TMP/charge31f.json"
CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK" < "$TMP/charge31f.json" >/dev/null
[ "$(head_sha)" = "$BEFORE" ] || fail "cas31f: T-0<ULID> (27 symboles) n'est pas une ligne de succès, aucun commit"
git -C "$TMP" add -A -- .agents/state && git -C "$TMP" commit -qm "cas31f: remise au propre"

# --- MONOREPO (T-00000691, S-00002557 MOYENNE) : `.agents/` sous apps/foo/, runs/ à
# la RACINE GIT — là où `run_export.chemin_export` l'écrit (`project_root` = racine
# git). La jambe reçoit `--commit-section <apps/foo>` : un pathspec et un `find`
# RELATIFS au sous-projet ne voyaient jamais runs/, donc les exports n'étaient
# JAMAIS commités. Dépôt JETABLE à part, sous "$TMP" (nettoyé par le trap).
MONO="$TMP/mono"
mkdir -p "$MONO/apps/foo/.agents" "$MONO/runs/aut/cop"
git -C "$MONO" init -q
git -C "$MONO" config user.email t@t
git -C "$MONO" config user.name t
git -C "$MONO" config cadre.signStateCommits false
printf 'monorepo\n' > "$MONO/README"
git -C "$MONO" add README && git -C "$MONO" commit -qm init

# 32. MONOREPO : un export NEUF sous <racine git>/runs/ est COMMITÉ depuis la jambe
#     appelée sur le sous-projet. Mutations qui rougissent : pathspec sans `top`
#     (`:(glob)runs/*/*/*.jsonl` — relatif à apps/foo, rien ne correspond →
#     `nothing`) ; garde `[ -d "$dir/runs" ]` au lieu de la racine git (→ `nothing`).
printf '{"ulid":"01ARZ3NDEKTSV4RRFFQ69G5FAV"}\n' > "$MONO/runs/aut/cop/2026-09.jsonl"
BEFORE32="$(git -C "$MONO" rev-parse HEAD)"
TOK32="$(bash "$HOOK" --commit-section "$MONO/apps/foo" run-exports)"
[ "$TOK32" = "committed" ] || fail "cas32: monorepo, attendu 'committed', obtenu [$TOK32]"
[ "$(git -C "$MONO" rev-parse HEAD)" != "$BEFORE32" ] || fail "cas32: aucun commit né"
git -C "$MONO" show --stat --oneline HEAD | grep -q 'runs/aut/cop/2026-09.jsonl' \
  || fail "cas32: le commit doit porter l'export de la racine git"

# 33. MONOREPO + LIEN SYMBOLIQUE sous <racine git>/runs/ → `failed`, rien commité. Le
#     `find -type l` cherchait sous apps/foo/runs (absent) : il ne voyait pas le lien,
#     que le pathspec `top` aurait alors commité. Mutation qui rougit : `find` sous
#     "$dir/runs" (→ `committed`, le lien entre dans l'historique).
if ln -s /cible/inexistante "$MONO/runs/aut/cop/lien.jsonl" 2>/dev/null; then
  BEFORE33="$(git -C "$MONO" rev-parse HEAD)"
  TOK33="$(bash "$HOOK" --commit-section "$MONO/apps/foo" run-exports)"
  [ "$TOK33" = "failed" ] || fail "cas33: lien sous runs/ en monorepo, attendu 'failed', obtenu [$TOK33]"
  [ "$(git -C "$MONO" rev-parse HEAD)" = "$BEFORE33" ] || fail "cas33: aucun commit avec un lien sous runs/"
  git -C "$MONO" diff --cached --quiet || fail "cas33: l'index doit rester propre après le refus"
else
  echo "SKIP cas33: ln -s refusé sur cette plateforme"
fi

# 34. PIN DOC (T-00000724) — « un commit en échec ne laisse pas d'index sale » ne vaut
#     que pour le `failed` ÉMIS PAR LA JAMBE SHELL (elle défait son propre `add`, cas
#     29) : un appelant qui TUE bash en plein commit laisse ce que git tenait. Les deux
#     formes NUES ont disparu et que chaque qualificatif reste présent. L'historique
#     est strip: chez l'adoptant ; sa moitié LOG34 saute alors, et le test du SKILL
#     continue de juger le texte livré.
case34() {
  local root="$1" skill="$1/.agents/skills/task-board/SKILL.md"
  local log="$1/docs/HISTORIQUE-0.1.0.md"
  [ -f "$skill" ] || fail "cas34: task-board/SKILL.md introuvable à côté du hook"
  grep -qF 'and a failed commit leaves no dirty index;' "$skill" \
    && fail "cas34: task-board/SKILL.md porte encore la forme nue, sans sa portée"
  grep -qF 'that the shell leg itself reports' "$skill" \
    || fail "cas34: le qualificatif de task-board/SKILL.md a disparu (non-vacuité)"
  if [ ! -f "$root/.agents/IS_THE_KIT" ]; then
    echo 'SKIP cas34 LOG34: .agents/IS_THE_KIT absent (projet adoptant)'
    return 0
  fi
  [ -f "$log" ] || fail "cas34: docs/HISTORIQUE-0.1.0.md introuvable dans l'arbre"
  grep -qF "et un commit en échec ne laisse pas d'index sale)" "$log" \
    && fail "cas34: docs/HISTORIQUE-0.1.0.md porte encore la forme nue, sans sa portée"
  grep -qF 'émis par la jambe shell' "$log" \
    || fail "cas34: le qualificatif de docs/HISTORIQUE-0.1.0.md a disparu (non-vacuité)"
}
case34 "$HERE/../.."
mkdir -p "$TMP/cas34-adoptant/.agents/skills/task-board"
cp "$HERE/../skills/task-board/SKILL.md" "$TMP/cas34-adoptant/.agents/skills/task-board/SKILL.md"
( case34 "$TMP/cas34-adoptant" ) > "$TMP/cas34-saut" || { cat "$TMP/cas34-saut"; exit 1; }
cat "$TMP/cas34-saut"
grep -qFx 'SKIP cas34 LOG34: .agents/IS_THE_KIT absent (projet adoptant)' "$TMP/cas34-saut" \
  || fail 'cas34: annonce du saut LOG34 absente'
if (case34 "$TMP/cas34-avec-skill-absent") > "$TMP/cas34-rouge" 2>&1; then
  fail 'cas34: SKILL34 a été sauté avec LOG34 dans l’arbre adoptant'
fi
grep -qF 'cas34: task-board/SKILL.md introuvable' "$TMP/cas34-rouge" \
  || fail 'cas34: le témoin négatif du SKILL34 n’a pas rougi'

# --- SIGNATURE DES COMMITS D'ÉTAT (T-00000724, décision pilote S-00003331) ----------
# Par défaut la jambe section commite avec `--no-gpg-sign` ; la clé git
# `cadre.signStateCommits=true` du dépôt (l'interrupteur opt-in) le retire, sans rien
# forcer. FIXTURE NEUVE par cas : dépôt, HOME, XDG_CONFIG_HOME et TMPDIR jetables sous
# GIT_CONFIG_NOSYSTEM=1, `commit.gpgsign=true`, et un FAUX SIGNATAIRE (openpgp, x509,
# ssh) qui pose le marqueur `started` puis échoue : un signataire lancé se VOIT au
# marqueur, jamais à une durée. CWD DÉCLARÉ : `$SF/ailleurs`, HORS du dépôt, sous un
# GIT_CEILING_DIRECTORIES qui l'empêche d'en découvrir un — une lecture de la clé qui
# perdrait son `-C "$dir"` n'y lit que la config globale jetable, jamais celle du dépôt
# du cas (S4 et S5 rougissent), ni celle d'un dépôt d'où le banc serait lancé.
sg() { env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" GIT_CONFIG_NOSYSTEM=1 git -C "$SR" "$@"; }
sig_fixture() {  # $1 = nom du cas ; pose SF (racine jetable du cas) et SR (son dépôt)
  SF="$TMP/sig-$1"; SR="$SF/repo"
  mkdir -p "$SF/home" "$SF/xdg" "$SF/tmp" "$SF/ailleurs" "$SR/.agents/state/board"
  printf '#!/usr/bin/env bash\n: > %q\nexit 1\n' "$SF/started" > "$SF/faux-signataire"
  chmod +x "$SF/faux-signataire"
  sg init -q
  sg config user.email t@t
  sg config user.name t
  sg config commit.gpgsign true
  sg config gpg.program "$SF/faux-signataire"
  sg config gpg.x509.program "$SF/faux-signataire"
  sg config gpg.ssh.program "$SF/faux-signataire"
  printf '{"tasks":[]}\n' > "$SR/.agents/state/board/TASKS.json"
  sg add -A
  sg -c commit.gpgsign=false commit -qm init
  printf '{"tasks":[{"id":"%s"}]}\n' "$1" > "$SR/.agents/state/board/TASKS.json"
}
sig_run() {  # $1 = cwd déclaré, $2 = sélecteur — la jambe section, environnement du cas
  (cd "$1" && env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" TMPDIR="$SF/tmp" GIT_CONFIG_NOSYSTEM=1 \
     GIT_CEILING_DIRECTORIES="$SF" bash "$HOOK" --commit-section "$SR" "$2")
}
sig_count() { sg cat-file commit HEAD | grep -c '^gpgsig' || true; }

# CAPACITÉ ssh, sondée UNE fois (S2, S4) : un commit jetable `-S` avec une clé ed25519
# et `gpg.format=ssh` doit porter UN `gpgsig`. Sinon S2 et S4 SAUTENT, nommément.
SSHKG="$(command -v ssh-keygen 2>/dev/null || true)"
SSH_OK=""
if [ -n "$SSHKG" ]; then
  SF="$TMP/sig-sonde"; SR="$SF/repo"
  mkdir -p "$SF/home" "$SF/xdg" "$SR"
  if "$SSHKG" -q -t ed25519 -N '' -f "$SF/cle" </dev/null >/dev/null 2>&1 \
     && sg init -q && sg config user.email t@t && sg config user.name t \
     && sg config gpg.format ssh && sg config user.signingkey "$SF/cle" \
     && sg commit -q --allow-empty -S -m sonde >/dev/null 2>&1 \
     && [ "$(sig_count)" = "1" ]; then
    SSH_OK=1
  fi
fi

# 35. S1 — clé ABSENTE, `commit.gpgsign=true`, format openpgp : le commit d'état passe
#     NON signé — `committed`, `started` absent, 0 `gpgsig`, HEAD avancé. Mutation qui
#     rougit : retirer `--no-gpg-sign` (le faux signataire tourne et échoue → `failed`).
sig_fixture s1
B35="$(sg rev-parse HEAD)"
T35="$(sig_run "$SF/ailleurs" stores)"
[ "$T35" = "committed" ] || fail "cas35: clé absente, attendu 'committed', obtenu [$T35]"
[ ! -e "$SF/started" ] || fail "cas35: clé absente, un signataire a été LANCÉ"
[ "$(sig_count)" = "0" ] || fail "cas35: clé absente, le commit d'état ne doit pas être signé"
[ "$(sg rev-parse HEAD)" != "$B35" ] || fail "cas35: HEAD doit avancer"

# 36. S2 — format ssh + `gpg.ssh.defaultKeyCommand` à marqueur, clé absente : `committed`,
#     et NI le signataire NI la commande de clé n'ont tourné (deux marqueurs absents).
#     Mutation qui rougit : retirer `--no-gpg-sign`. SAUTE sans signature ssh.
if [ -n "$SSH_OK" ]; then
  sig_fixture s2
  printf '#!/usr/bin/env bash\n: > %q\nexit 1\n' "$SF/dkc-started" > "$SF/commande-de-cle"
  chmod +x "$SF/commande-de-cle"
  sg config gpg.format ssh
  sg config gpg.ssh.defaultKeyCommand "$SF/commande-de-cle"
  T36="$(sig_run "$SF/ailleurs" stores)"
  [ "$T36" = "committed" ] || fail "cas36: ssh, clé absente, attendu 'committed', obtenu [$T36]"
  [ ! -e "$SF/started" ] || fail "cas36: ssh, clé absente, le signataire a été LANCÉ"
  [ ! -e "$SF/dkc-started" ] || fail "cas36: ssh, clé absente, gpg.ssh.defaultKeyCommand a été LANCÉE"
else
  echo "SKIP S2/S4 : signature ssh indisponible (git < 2.34 ou OpenSSH < 8.0) — cas36"
fi

# 37. S3 — format x509, clé absente : `committed`, `started` absent. Mutation qui
#     rougit : retirer `--no-gpg-sign`.
sig_fixture s3
sg config gpg.format x509
T37="$(sig_run "$SF/ailleurs" stores)"
[ "$T37" = "committed" ] || fail "cas37: x509, clé absente, attendu 'committed', obtenu [$T37]"
[ ! -e "$SF/started" ] || fail "cas37: x509, clé absente, le signataire a été LANCÉ"

# 38. S4 — clé `true` + VRAIE signature ssh (ed25519 jetable ; `gpg.ssh.program` = un
#     enveloppeur à marqueur qui exec ssh-keygen) : `committed`, `started` présent, UN
#     `gpgsig`. Mutation qui rougit : interrupteur ignoré (0 `gpgsig`). SAUTE sans ssh.
if [ -n "$SSH_OK" ]; then
  sig_fixture s4
  "$SSHKG" -q -t ed25519 -N '' -f "$SF/cle" </dev/null >/dev/null 2>&1 \
    || fail "cas38: la clé ed25519 jetable n'a pas pu être créée"
  printf '#!/usr/bin/env bash\n: > %q\nexec %q "$@"\n' "$SF/started" "$SSHKG" > "$SF/signataire-ssh"
  chmod +x "$SF/signataire-ssh"
  sg config gpg.format ssh
  sg config user.signingkey "$SF/cle"
  sg config gpg.ssh.program "$SF/signataire-ssh"
  sg config cadre.signStateCommits true
  T38="$(sig_run "$SF/ailleurs" stores)"
  [ "$T38" = "committed" ] || fail "cas38: clé true + ssh réelle, attendu 'committed', obtenu [$T38]"
  [ -e "$SF/started" ] || fail "cas38: clé true, le signataire n'a PAS été lancé"
  [ "$(sig_count)" = "1" ] || fail "cas38: clé true, le commit d'état doit porter UNE signature, compte [$(sig_count)]"
else
  echo "SKIP S2/S4 : signature ssh indisponible (git < 2.34 ou OpenSSH < 8.0) — cas38"
fi

# 39. S5 — clé `true` + faux signataire : le commit ÉCHOUE comme un commit normal —
#     `failed`, `started` présent, HEAD inchangé, index PROPRE (l'`add` est défait).
#     Bras ON sans dépendance à ssh-keygen. Mutation qui rougit : interrupteur ignoré
#     (→ `committed` non signé).
sig_fixture s5
sg config cadre.signStateCommits true
B39="$(sg rev-parse HEAD)"
T39="$(sig_run "$SF/ailleurs" stores)"
[ "$T39" = "failed" ] || fail "cas39: clé true + faux signataire, attendu 'failed', obtenu [$T39]"
[ -e "$SF/started" ] || fail "cas39: clé true, le faux signataire n'a PAS été lancé"
[ "$(sg rev-parse HEAD)" = "$B39" ] || fail "cas39: aucun commit ne doit naître quand le signataire échoue"
sg diff --cached --quiet || fail "cas39: l'index doit rester propre après l'échec du signataire"

# 40. S6 — clé `true` + `commit.gpgsign=false` : la clé ne FORCE pas la signature —
#     `committed`, `started` absent, 0 `gpgsig`. Mutation qui rougit : `-S` forcé
#     quand la clé vaut true.
sig_fixture s6
sg config cadre.signStateCommits true
sg config commit.gpgsign false
T40="$(sig_run "$SF/ailleurs" stores)"
[ "$T40" = "committed" ] || fail "cas40: clé true + gpgsign=false, attendu 'committed', obtenu [$T40]"
[ ! -e "$SF/started" ] || fail "cas40: la clé ne doit pas FORCER la signature (signataire lancé)"
[ "$(sig_count)" = "0" ] || fail "cas40: clé true + gpgsign=false, aucune signature attendue"

# 41. S7a — clé GLOBALE `true` (HOME jetable du cas) + clé LOCALE `false` : la locale
#     l'emporte, défaut non signé. Mutation qui rougit : retirer `--no-gpg-sign`.
sig_fixture s7a
env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" GIT_CONFIG_NOSYSTEM=1 git config --global cadre.signStateCommits true
[ "$(env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" GIT_CONFIG_NOSYSTEM=1 git config --global --get cadre.signStateCommits)" = "true" ] \
  || fail "pré-41: la clé globale jetable doit valoir true"
sg config cadre.signStateCommits false
T41="$(sig_run "$SF/ailleurs" stores)"
[ "$T41" = "committed" ] || fail "cas41: globale true + locale false, attendu 'committed', obtenu [$T41]"
[ ! -e "$SF/started" ] || fail "cas41: la clé locale false doit l'emporter (signataire lancé)"

# 42. S7b — valeur INVALIDE (`maybe`, refusée par `git config --bool`) : non signé, sans
#     message. Mutation qui rougit : retirer `--no-gpg-sign`.
sig_fixture s7b
sg config cadre.signStateCommits maybe
if sg config --bool --get cadre.signStateCommits >/dev/null 2>&1; then
  fail "pré-42: 'maybe' doit être une valeur que git config --bool refuse"
fi
T42="$(sig_run "$SF/ailleurs" stores)"
[ "$T42" = "committed" ] || fail "cas42: valeur invalide, attendu 'committed' non signé, obtenu [$T42]"
[ ! -e "$SF/started" ] || fail "cas42: valeur invalide, un signataire a été LANCÉ"

# 43. S8 — CHEMIN DÉGRADÉ (aucun python, `$STUB`) : `degraded_commit` passe par la même
#     jambe, donc hérite du défaut — « stores commités sans verrou (dégradé : … »,
#     `started` absent — et sa clause DIT la signature sautée (`commit.gpgsign=true`, clé
#     absente). Mutations qui rougissent : retirer `--no-gpg-sign` ; mention `UNSIGNED`
#     jamais posée.
sig_fixture s8
O43="$(printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-43 --raison banc"}}' \
  | (cd "$SF/ailleurs" && env PATH="$STUB:$PATH" HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" TMPDIR="$SF/tmp" \
       GIT_CONFIG_NOSYSTEM=1 GIT_CEILING_DIRECTORIES="$SF" CLAUDE_PROJECT_DIR="$SR" bash "$HOOK" 2>/dev/null))"
printf '%s' "$O43" | grep -qF 'stores commités sans verrou (dégradé : ' \
  || fail "cas43: le dégradé doit commiter non signé, obtenu [$O43]"
[ ! -e "$SF/started" ] || fail "cas43: chemin dégradé, un signataire a été LANCÉ"
printf '%s' "$O43" | grep -qF 'sans verrou (dégradé : interpréteur introuvable) (non signés : voir cadre.signStateCommits)' \
  || fail "cas43: la clause dégradée doit dire la signature sautée, obtenu [$O43]"

# 44. D1 — TÉMOIN HOOK ↔ README DU KIT (S-00003351). La clé que le hook lit est écrite
#     UNE fois (`SIGN_SWITCH_KEY`), et toute graphie `cadre.*sign*` du hook est CETTE clé
#     (balayage BORNÉ aux mots qui contiennent `sign`). Le README DU KIT porte la
#     commande qui pose la clé, celle qui la retire, la phrase « ne force pas », le
#     statut de réglage du NOYAU (S-00003364), le paragraphe des ignores (option C) et
#     la mention de signature sautée que le hook émet (cas 43 et 55 en tiennent l'autre
#     bout) ; et son paragraphe V3 dit le commit AUTOMATIQUE des exports (bras (m)).
#     `docs/usage.html` n'est PAS lu : documenté, non épinglé (S-00003351). Le README
#     peut appartenir au PROJET (L-016) : le marqueur `.agents/IS_THE_KIT` ne voyage
#     pas, donc chez un adoptant D1-README SAUTE nommément ; dans le kit, README absent,
#     remplacé ou privé d'une chaîne = ROUGE. Résidu nommé : D1 tient la PRÉSENCE des
#     chaînes, pas le sens du paragraphe.
N44="$(grep -cE "^SIGN_SWITCH_KEY='[^']+'\$" "$HOOK" || true)"
[ "$N44" = "1" ] || fail "cas44: le hook doit porter UNE ligne SIGN_SWITCH_KEY='…', compte [$N44]"
KEY44="$(sed -n "s/^SIGN_SWITCH_KEY='\([^']*\)'\$/\1/p" "$HOOK")"
GRAPHIES44="$(grep -oE 'cadre\.[A-Za-z]*[Ss]ign[A-Za-z]*' "$HOOK" | sort -u)"
[ "$GRAPHIES44" = "$KEY44" ] \
  || fail "cas44: graphies divergentes de la clé dans le hook : [$GRAPHIES44] contre la constante [$KEY44]"
README44="$HERE/../../README.md"
if [ ! -f "$HERE/../IS_THE_KIT" ]; then
  echo "SKIP D1-README : README.md appartient au projet (L-016) — marqueur .agents/IS_THE_KIT absent"
else
  [ -f "$README44" ] || fail "cas44: README.md du kit introuvable alors que .agents/IS_THE_KIT est présent"
  for s44 in "git config $KEY44 true" "git config --unset $KEY44" 'core.excludesFile' '.git/info/exclude' \
             'The key does not force signing: it only removes `--no-gpg-sign`; `commit.gpgsign=true` is still required.' \
             'a core setting, not promised by the v0 contract: it may change without notice' \
             "(non signés : voir $KEY44)"; do
    grep -qF "$s44" "$README44" || fail "cas44: le README du kit ne porte pas [$s44]"
  done
  grep -qF 'commit-run-exports' "$README44" \
    || fail "cas44 (m): le README du kit ne nomme pas commit-run-exports"
  grep -qF 'still auto-commits only' "$README44" \
    && fail "cas44 (m): le README du kit dit encore que le hook ne commite que les stores"
  grep -qF 'there is no dedicated commit verb anymore' "$README44" \
    && fail "cas44 (m): le README du kit nie encore le verbe de commit des exports"
fi

# --- IGNORES PERSONNELS NEUTRALISÉS SUR LA JAMBE D'EXPORTS (T-00000724, option C de
# S-00003331, lue à la lettre) ---------------------------------------------------------
# `-c core.excludesFile=/dev/null` au `status` et à l'`add` du SEUL sélecteur
# `run-exports`, et au `status` dégradé des exports ; `.gitignore` et
# `.git/info/exclude` restent obéis ; la jambe `stores` ne change pas. Fixture neuve
# par cas, environnement jetable passé AU HOOK (HOME, XDG_CONFIG_HOME), cwd déclaré.
xg() { env HOME="$XF/home" XDG_CONFIG_HOME="$XF/xdg" GIT_CONFIG_NOSYSTEM=1 git -C "$XR" "$@"; }
xfix() {  # $1 = nom du cas ; pose XF (racine jetable) et XR (dépôt, runs/ à la forme du contrat)
  XF="$TMP/exc-$1"; XR="$XF/repo"
  mkdir -p "$XF/home" "$XF/xdg/git" "$XF/tmp" "$XF/ailleurs" "$XR/runs/a/b" "$XR/.agents/state/board"
  xg init -q
  xg config user.email t@t
  xg config user.name t
  printf 'seed\n' > "$XR/runs/a/b/2026-09.jsonl"
  printf '{"tasks":[]}\n' > "$XR/.agents/state/board/TASKS.json"
  xg add -A
  xg commit -qm init
  mkdir -p "$XR/.git/info"
}
xrun() {  # $1 = cwd déclaré, $2 = sélecteur
  (cd "$1" && env HOME="$XF/home" XDG_CONFIG_HOME="$XF/xdg" TMPDIR="$XF/tmp" GIT_CONFIG_NOSYSTEM=1 \
     GIT_CEILING_DIRECTORIES="$XF" bash "$HOOK" --commit-section "$XR" "$2")
}
xnames() { xg show --name-only --format= HEAD; }

# 45. X1 — un ignore XDG personnel (`~/.config/git/ignore` : `*.jsonl`) cachait un export
#     NEUF : la jambe d'exports le VOIT et le commite. PRÉ-ASSERTIONS : l'export est bien
#     ignoré (`check-ignore` rc 0) et le `status` brut est VIDE — sans elles le cas
#     passerait sur un ignore inopérant. Mutation qui rougit : `status` sans `gx`.
xfix x1
printf '*.jsonl\n' > "$XF/xdg/git/ignore"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10.jsonl || fail "pré-45: l'ignore XDG doit cacher l'export"
[ -z "$(xg status --porcelain --untracked-files=all -- runs)" ] || fail "pré-45: le status brut doit être vide"
T45="$(xrun "$XF/ailleurs" run-exports)"
[ "$T45" = "committed" ] || fail "cas45: ignore XDG, attendu 'committed', obtenu [$T45]"
xnames | grep -qx 'runs/a/b/2026-10.jsonl' || fail "cas45: le commit doit porter l'export que l'ignore XDG cachait"

# 46. X2 — même chose par un `core.excludesFile` GLOBAL (`$HOME/.gitconfig` jetable).
#     Mutation qui rougit : `add` sans `gx` (l'`add` refuse le chemin ignoré → `failed`).
xfix x2
printf '*.jsonl\n' > "$XF/perso-ignore"
xg config --global core.excludesFile "$XF/perso-ignore"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10.jsonl || fail "pré-46: le core.excludesFile global doit cacher l'export"
[ -z "$(xg status --porcelain --untracked-files=all -- runs)" ] || fail "pré-46: le status brut doit être vide"
T46="$(xrun "$XF/ailleurs" run-exports)"
[ "$T46" = "committed" ] || fail "cas46: core.excludesFile global, attendu 'committed', obtenu [$T46]"
xnames | grep -qx 'runs/a/b/2026-10.jsonl' || fail "cas46: le commit doit porter l'export que la clé globale cachait"

# 47. X3a — `.git/info/exclude` qui liste `runs/` reste OBÉI : `nothing`, HEAD inchangé.
#     Mutation qui rougit : `status --ignored` (le chemin ignoré remonte, l'`add` le
#     refuse → `failed`).
xfix x3a
printf 'runs/\n' >> "$XR/.git/info/exclude"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10.jsonl || fail "pré-47: .git/info/exclude doit cacher l'export"
B47="$(xg rev-parse HEAD)"
T47="$(xrun "$XF/ailleurs" run-exports)"
[ "$T47" = "nothing" ] || fail "cas47: .git/info/exclude doit rester obéi, attendu 'nothing', obtenu [$T47]"
[ "$(xg rev-parse HEAD)" = "$B47" ] || fail "cas47: aucun commit ne doit naître"

# 48. X3b — `.gitignore` qui liste `runs/` reste OBÉI : `nothing`, HEAD inchangé.
#     Mutation qui rougit : `status --ignored`.
xfix x3b
printf 'runs/\n' > "$XR/.gitignore"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10.jsonl || fail "pré-48: .gitignore doit cacher l'export"
B48="$(xg rev-parse HEAD)"
T48="$(xrun "$XF/ailleurs" run-exports)"
[ "$T48" = "nothing" ] || fail "cas48: .gitignore doit rester obéi, attendu 'nothing', obtenu [$T48]"
[ "$(xg rev-parse HEAD)" = "$B48" ] || fail "cas48: aucun commit ne doit naître"

# 49. X3c — un export VISIBLE et un export que `.gitignore` cache : `committed`, et le
#     commit ne porte QUE le visible. Mutation qui rougit : `add -f` (le caché part aussi).
xfix x3c
printf 'runs/a/b/2026-10-hidden.jsonl\n' > "$XR/.gitignore"
printf 'cache\n' > "$XR/runs/a/b/2026-10-hidden.jsonl"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10-hidden.jsonl || fail "pré-49: .gitignore doit cacher l'export caché"
T49="$(xrun "$XF/ailleurs" run-exports)"
[ "$T49" = "committed" ] || fail "cas49: export visible, attendu 'committed', obtenu [$T49]"
xnames | grep -qx 'runs/a/b/2026-10.jsonl' || fail "cas49: le commit doit porter l'export visible"
xnames | grep -qF '2026-10-hidden.jsonl' \
  && fail "cas49: l'export que .gitignore cache est entré dans le commit : [$(xnames)]"

# 50. X4 — CONFINEMENT : sélecteur `stores`, ignore XDG `*.json`, TASKS.json DÉSUIVI puis
#     modifié — la jambe stores GARDE son comportement (S-00003331 ne nomme que les
#     exports) : `nothing`, HEAD inchangé. PRÉ-ASSERTIONS : le store est ignoré, le status
#     brut est vide, le status neutralisé le voit. Mutation qui rougit : confinement
#     retiré (`gx+=` sans condition → `committed`).
xfix x4
xg rm -q --cached .agents/state/board/TASKS.json
xg commit -qm desuivi
printf '*.json\n' > "$XF/xdg/git/ignore"
printf '{"tasks":[{"id":"x4"}]}\n' > "$XR/.agents/state/board/TASKS.json"
xg check-ignore -q .agents/state/board/TASKS.json || fail "pré-50: l'ignore XDG doit cacher le store désuivi"
[ -z "$(xg status --porcelain --untracked-files=all -- .agents/state)" ] || fail "pré-50: le status brut doit être vide"
[ -n "$(xg -c core.excludesFile=/dev/null status --porcelain --untracked-files=all -- .agents/state)" ] \
  || fail "pré-50: neutralisé, le status doit voir le store désuivi"
B50="$(xg rev-parse HEAD)"
T50="$(xrun "$XF/ailleurs" stores)"
[ "$T50" = "nothing" ] || fail "cas50: la jambe stores doit rester inchangée, attendu 'nothing', obtenu [$T50]"
[ "$(xg rev-parse HEAD)" = "$B50" ] || fail "cas50: aucun commit de stores ne doit naître"

# 51. X5 — CONSÉQUENCE ÉCRITE de C : un fichier privé de la forme des exports que seule
#     la clé LOCALE cachait EST commité avec l'export visible (LES DEUX chemins). cwd
#     DÉCLARÉ : LE DÉPÔT DU CAS — une variante C′ qui lirait la clé locale dans le cwd en
#     tête de script n'est rouge QUE grâce à ce `cd` (run-bash-tests.sh lance depuis le
#     kit). Mutations qui rougissent : C′ dans la fonction, C′ en tête.
xfix x5
printf '2026-10-private.jsonl\n' > "$XF/local-ignore"
xg config core.excludesFile "$XF/local-ignore"
printf 'prive\n' > "$XR/runs/a/b/2026-10-private.jsonl"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10-private.jsonl || fail "pré-51: la clé locale doit cacher le fichier privé"
T51="$(xrun "$XR" run-exports)"
[ "$T51" = "committed" ] || fail "cas51: attendu 'committed', obtenu [$T51]"
xnames | grep -qx 'runs/a/b/2026-10.jsonl' || fail "cas51: le commit doit porter l'export visible"
xnames | grep -qx 'runs/a/b/2026-10-private.jsonl' \
  || fail "cas51: sous C le fichier privé que seule la clé locale cachait est commité — absent : [$(xnames)]"

# 52. X6 — CHEMIN DÉGRADÉ (aucun python) + export que seul un ignore XDG cachait : la
#     clause « non tentés » le DIT (même neutralisation au `status` dégradé). Mutation
#     qui rougit : `-c` retiré du `status` dégradé (silence).
xfix x6
printf '*.jsonl\n' > "$XF/xdg/git/ignore"
printf 'nuit\n' > "$XR/runs/a/b/2026-10.jsonl"
xg check-ignore -q runs/a/b/2026-10.jsonl || fail "pré-52: l'ignore XDG doit cacher l'export"
O52="$(printf '{"tool_input":{"command":"python .agents/bin/tasks.py done T-52 --raison banc"}}' \
  | (cd "$XF/ailleurs" && env PATH="$STUB:$PATH" HOME="$XF/home" XDG_CONFIG_HOME="$XF/xdg" TMPDIR="$XF/tmp" \
       GIT_CONFIG_NOSYSTEM=1 GIT_CEILING_DIRECTORIES="$XF" CLAUDE_PROJECT_DIR="$XR" bash "$HOOK" 2>/dev/null))"
printf '%s' "$O52" | grep -qF 'exports non commités (non tentés : chemin dégradé)' \
  || fail "cas52: le chemin dégradé doit DIRE l'export que seul un ignore personnel cachait, obtenu [$O52]"

# --- SIGNATURE, SUITE DU BINÔME DE CLÔTURE (T-00000724) ------------------------------
# Mêmes fixtures que 35-43 (`sig_fixture` : HOME, XDG, TMPDIR jetables, `commit.gpgsign=true`,
# faux signataire à marqueur, cwd déclaré hors du dépôt).

# 53. S9 — JAMBE D'EXPORTS, clé ABSENTE, `commit.gpgsign=true` : `chore(runs)` passe NON
#     signé lui aussi — `committed`, `started` absent, 0 `gpgsig`, sujet `chore(runs):`.
#     Les cas 35-43 ne passaient tous que par `stores`. Mutation qui rougit :
#     `--no-gpg-sign` réservé au sélecteur `stores` (le faux signataire tourne → `failed`).
sig_fixture s9
mkdir -p "$SR/runs/a/b"
printf 'nuit\n' > "$SR/runs/a/b/2026-10.jsonl"
T53="$(sig_run "$SF/ailleurs" run-exports)"
[ "$T53" = "committed" ] || fail "cas53: exports, clé absente, attendu 'committed', obtenu [$T53]"
[ ! -e "$SF/started" ] || fail "cas53: exports, clé absente, un signataire a été LANCÉ"
[ "$(sig_count)" = "0" ] || fail "cas53: le commit d'exports ne doit pas être signé"
sg show -s --format=%s HEAD | grep -q '^chore(runs):' || fail "cas53: sujet 'chore(runs):' attendu"

# 54. S7c — clé GLOBALE invalide (`maybe`) + LOCALE `true` : `git config --bool` refuse la
#     lecture ENTIÈRE (rc 128), la locale ne l'emporte PAS — non signé, `committed`,
#     `started` absent (borne écrite dans les docs). PRÉ-ASSERTIONS : la locale vaut bien
#     `true`, et la lecture `--bool` combinée échoue — sans elles un git futur qui
#     tolérerait les niveaux mêlés ferait passer le cas à vide. Mutation qui rougit :
#     lecture SANS `--bool` (`git config --get` rend la DERNIÈRE valeur, `true` → signataire
#     lancé → `failed`).
sig_fixture s7c
env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" GIT_CONFIG_NOSYSTEM=1 git config --global cadre.signStateCommits maybe
sg config cadre.signStateCommits true
[ "$(sg config --local --get cadre.signStateCommits)" = "true" ] || fail "pré-54: la clé locale doit valoir true"
if sg config --bool --get cadre.signStateCommits >/dev/null 2>&1; then
  fail "pré-54: globale 'maybe' + locale 'true', la lecture --bool combinée doit échouer"
fi
T54="$(sig_run "$SF/ailleurs" stores)"
[ "$T54" = "committed" ] || fail "cas54: globale invalide + locale true, attendu 'committed', obtenu [$T54]"
[ ! -e "$SF/started" ] || fail "cas54: globale invalide + locale true, un signataire a été LANCÉ"

# SIGNAL D'UNE SIGNATURE SAUTÉE (55-57) : la jambe EXTERNE sur son chemin NORMAL — le dépôt
# du cas reçoit `tasks*.py` et le hook sous `.agents/bin/` (motif de la ligne 26), la charge
# arrive sur stdin, `CLAUDE_PROJECT_DIR` = le dépôt du cas. SAUTENT sans python.
sig_hook() {  # $1 = identifiant de tâche de la charge ; la sortie du hook sur stdout
  mkdir -p "$SR/.agents/bin"
  cp "$HERE"/tasks*.py "$HOOK" "$SR/.agents/bin/"
  printf '{"tool_input":{"command":"python .agents/bin/tasks.py done %s --raison banc"}}' "$1" \
    | (cd "$SF/ailleurs" && env HOME="$SF/home" XDG_CONFIG_HOME="$SF/xdg" TMPDIR="$SF/tmp" GIT_CONFIG_NOSYSTEM=1 \
         GIT_CEILING_DIRECTORIES="$SF" CLAUDE_PROJECT_DIR="$SR" bash "$HOOK" 2>/dev/null)
}

# 55. S10 — TÉMOIN : `commit.gpgsign=true`, clé ABSENTE, stores ET runs/ sales : les DEUX
#     clauses de commit portent « (non signés : voir cadre.signStateCommits) », aucun
#     signataire lancé. Mutations qui rougissent : mention retirée (UNSIGNED jamais posée) ;
#     mention retirée du seul bras exports.
if [ -n "$PYBIN" ]; then
  sig_fixture s10
  mkdir -p "$SR/runs/a/b"
  printf 'nuit\n' > "$SR/runs/a/b/2026-10.jsonl"
  O55="$(sig_hook T-55)"
  printf '%s' "$O55" | grep -qF 'stores commités (non signés : voir cadre.signStateCommits)' \
    || fail "cas55: la clause stores doit dire la signature sautée, obtenu [$O55]"
  printf '%s' "$O55" | grep -qF 'exports commités (non signés : voir cadre.signStateCommits)' \
    || fail "cas55: la clause exports doit dire la signature sautée, obtenu [$O55]"
  printf '%s' "$O55" | grep -q 'sans verrou' \
    && fail "cas55: chemin normal attendu, pas le dégradé [$O55]"
  [ ! -e "$SF/started" ] || fail "cas55: clé absente, un signataire a été LANCÉ"
  sg show -s --format=%s HEAD | grep -q '^chore(runs):' || fail "cas55: HEAD doit être le commit des exports"
  sg show -s --format=%s HEAD~1 | grep -q '^chore(state):' || fail "cas55: HEAD~1 doit être le commit des stores"
else
  echo "SKIP cas55: aucun python pour la jambe externe normale"
fi

# 56. S10b — CONTRÔLE NÉGATIF : `commit.gpgsign=false`, clé absente — rien n'a été sauté,
#     donc AUCUNE mention. Mutation qui rougit : mention posée sans condition.
if [ -n "$PYBIN" ]; then
  sig_fixture s10b
  sg config commit.gpgsign false
  O56="$(sig_hook T-56)"
  printf '%s' "$O56" | grep -q 'stores commit' || fail "cas56: 'stores commités' attendu, obtenu [$O56]"
  printf '%s' "$O56" | grep -q 'non signés' \
    && fail "cas56: commit.gpgsign=false, aucune mention de signature sautée attendue [$O56]"
else
  echo "SKIP cas56: aucun python pour la jambe externe normale"
fi

# 57. S10c — CONTRÔLE NÉGATIF, bras ON : clé `true` + VRAIE signature ssh (comme S4) — le
#     commit est signé, donc AUCUNE mention, UN `gpgsig`. Mutation qui rougit : condition
#     qui ignore la clé (mention dès que `commit.gpgsign=true`). SAUTE sans python ou sans ssh.
if [ -n "$PYBIN" ] && [ -n "$SSH_OK" ]; then
  sig_fixture s10c
  "$SSHKG" -q -t ed25519 -N '' -f "$SF/cle" </dev/null >/dev/null 2>&1 \
    || fail "cas57: la clé ed25519 jetable n'a pas pu être créée"
  printf '#!/usr/bin/env bash\n: > %q\nexec %q "$@"\n' "$SF/started" "$SSHKG" > "$SF/signataire-ssh"
  chmod +x "$SF/signataire-ssh"
  sg config gpg.format ssh
  sg config user.signingkey "$SF/cle"
  sg config gpg.ssh.program "$SF/signataire-ssh"
  sg config cadre.signStateCommits true
  O57="$(sig_hook T-57)"
  printf '%s' "$O57" | grep -q 'stores commit' || fail "cas57: 'stores commités' attendu, obtenu [$O57]"
  printf '%s' "$O57" | grep -q 'non signés' \
    && fail "cas57: clé true, commit signé — aucune mention de signature sautée attendue [$O57]"
  [ -e "$SF/started" ] || fail "cas57: clé true, le signataire n'a PAS été lancé"
  [ "$(sig_count)" = "1" ] || fail "cas57: clé true, le commit d'état doit porter UNE signature, compte [$(sig_count)]"
else
  echo "SKIP cas57: python ou signature ssh indisponible"
fi

# --- FORMES DES MAGASINS (T-00001012, BK-419, E-26) ------------------------------------
# La jambe `stores` commite les DEUX formes : les trois monolithes ET les fichiers par
# enregistrement (`board/tasks/T-*.json`, `board/epics/E-*.json`, domicile
# S-01M4N1G4VXD01A3W54Y9FR9856 ; `memory/entries/L-*.json` ; `specs/SPECS.jsonl`), y compris
# la SUPPRESSION d'un monolithe au commit de migration. UN dépôt jetable, remis à sa base
# entre deux cas (`dreset`), jamais un dépôt neuf par cas. D1-D5 sont ROUGES à la base
# (`nothing`) ; D6 et D7 sont des CONTRÔLES verts à la base.
DF="$TMP/formes"; DR="$DF/repo"
dg() { git -C "$DR" "$@"; }
mkdir -p "$DR/.agents/state/board" "$DR/.agents/state/memory" "$DR/.agents/state/specs"
dg init -q
dg config user.email t@t
dg config user.name t
dg config cadre.signStateCommits false
printf '/.agents/state/local/\n' > "$DR/.gitignore"
printf '{"tasks":[{"id":"T-1"}]}\n' > "$DR/.agents/state/board/TASKS.json"
printf '{"entries":[]}\n' > "$DR/.agents/state/memory/LEDGER.json"
printf '{"entries":[]}\n' > "$DR/.agents/state/specs/SPECS.json"
dg add -A
dg -c commit.gpgsign=false commit -qm init
D0="$(dg rev-parse HEAD)"
dreset() { dg reset -q --hard "$D0"; dg clean -fdq; rm -f "$DR/.git/MERGE_HEAD"; }
drun() { bash "$HOOK" --commit-section "$DR" stores; }
dnoms() { dg show --name-only --format= HEAD | sort | tr '\n' ' '; }
# $1 = chemin relatif, $2 = id, $3 = record (JSON, ou null) — l'enveloppe de T-00001008.
denr() {
  mkdir -p "$(dirname "$DR/$1")"
  printf '{"format": 1, "id": "%s", "record": %s}\n' "$2" "$3" > "$DR/$1"
}

# 58. D1 — enregistrements NEUFS seuls (tâche, épopée, entrée de ledger) : `committed`, et le
#     commit nomme EXACTEMENT ces trois fichiers. Base : `nothing`. Mutant qui rougit :
#     M-glob-absent (un des trois globs retiré de STORE_SPECS).
dreset
denr .agents/state/board/tasks/T-00000001.json T-00000001 '{"id": "T-00000001"}'
denr .agents/state/board/epics/E-01.json E-01 '{"id": "E-01"}'
denr .agents/state/memory/entries/L-00000001.json L-00000001 '{"id": "L-00000001"}'
T58="$(drun)"
[ "$T58" = "committed" ] || fail "cas58: enregistrements neufs, attendu 'committed', obtenu [$T58]"
ATT58='.agents/state/board/epics/E-01.json .agents/state/board/tasks/T-00000001.json .agents/state/memory/entries/L-00000001.json '
[ "$(dnoms)" = "$ATT58" ] || fail "cas58: le commit doit nommer exactement les 3 enregistrements, obtenu [$(dnoms)]"

# 59. D2 — MIGRATION : `TASKS.json` supprimé + `tasks/T-1.json` + une TOMBE `tasks/T-177.json` :
#     `committed`, le monolithe n'est plus à HEAD, les deux enregistrements y sont, et
#     `.agents/state` est propre. Base : `nothing` (la suppression était perdue). Mutant qui
#     rougit : M-mono-f (le `[ -f ]` des monolithes gardé).
dreset
rm -f "$DR/.agents/state/board/TASKS.json"
denr .agents/state/board/tasks/T-1.json T-1 '{"id": "T-1"}'
denr .agents/state/board/tasks/T-177.json T-177 null
T59="$(drun)"
[ "$T59" = "committed" ] || fail "cas59: migration, attendu 'committed', obtenu [$T59]"
[ -z "$(dg ls-tree --name-only HEAD -- .agents/state/board/TASKS.json)" ] \
  || fail "cas59: la suppression du monolithe doit partir dans le commit"
[ "$(dg ls-tree -r --name-only HEAD -- .agents/state/board/tasks | tr '\n' ' ')" = '.agents/state/board/tasks/T-1.json .agents/state/board/tasks/T-177.json ' ] \
  || fail "cas59: le commit doit porter T-1.json et la tombe T-177.json, obtenu [$(dg ls-tree -r --name-only HEAD -- .agents/state/board/tasks)]"
[ -z "$(dg status --porcelain --untracked-files=all -- .agents/state)" ] \
  || fail "cas59: .agents/state doit être propre après le commit : [$(dg status --porcelain -- .agents/state)]"

# 60. D3 — la FORME seule entre : à côté d'un enregistrement, un temporaire pointé, un `.tmp`,
#     un nom pointé en `.json`, un sous-dossier et un `x.txt` restent HORS du commit. Base :
#     `nothing`. Mutant qui rougit : M-glob-large (`tasks/*` ou le dossier nu).
dreset
denr .agents/state/board/tasks/T-5.json T-5 '{"id": "T-5"}'
printf '{}\n' > "$DR/.agents/state/board/tasks/.T-2.json.tmp"
printf '{}\n' > "$DR/.agents/state/board/tasks/T-3.json.tmp"
printf '{}\n' > "$DR/.agents/state/board/tasks/.T-6.json"
mkdir -p "$DR/.agents/state/board/tasks/sub"
printf '{}\n' > "$DR/.agents/state/board/tasks/sub/T-4.json"
printf 'x\n' > "$DR/.agents/state/board/tasks/x.txt"
T60="$(drun)"
[ "$T60" = "committed" ] || fail "cas60: attendu 'committed', obtenu [$T60]"
[ "$(dnoms)" = '.agents/state/board/tasks/T-5.json ' ] \
  || fail "cas60: seul l'enregistrement doit être commité, obtenu [$(dnoms)]"

# 61. D4 — un LIEN SYMBOLIQUE nommé comme un enregistrement → `failed`, HEAD fixe, index
#     propre ; trois variantes : sous `tasks/`, sous `entries/`, et `SPECS.jsonl` lui-même.
#     Base : `nothing`. Mutant qui rougit : M-lien (le `find` borné à `sync_outbox/`). SKIP
#     nommé là où `ln -s` est refusé.
dreset
mkdir -p "$DR/.agents/state/board/tasks"
if ln -s /cible/inexistante "$DR/.agents/state/board/tasks/T-9.json" 2>/dev/null; then
  for _v61 in tasks entries jsonl; do
    dreset
    mkdir -p "$DR/.agents/state/board/tasks" "$DR/.agents/state/memory/entries"
    case "$_v61" in
      tasks) ln -s /cible/inexistante "$DR/.agents/state/board/tasks/T-9.json" ;;
      entries) ln -s /cible/inexistante "$DR/.agents/state/memory/entries/L-9.json" ;;
      jsonl) ln -s /cible/inexistante "$DR/.agents/state/specs/SPECS.jsonl" ;;
    esac
    B61="$(dg rev-parse HEAD)"
    T61="$(drun)"
    [ "$T61" = "failed" ] || fail "cas61/$_v61: un lien doit rendre 'failed', obtenu [$T61]"
    [ "$(dg rev-parse HEAD)" = "$B61" ] || fail "cas61/$_v61: aucun commit avec un lien"
    dg diff --cached --quiet || fail "cas61/$_v61: l'index doit rester propre après le refus"
  done
else
  echo "SKIP cas61: ln -s refusé sur cette plateforme"
fi

# 62. D5 — bascule de SPECS : `SPECS.json` supprimé + `SPECS.jsonl` neuf → les deux dans le
#     commit. Base : `nothing`. Mutant qui rougit : M-jsonl-absent.
dreset
rm -f "$DR/.agents/state/specs/SPECS.json"
printf '{"id": "S-1"}\n' > "$DR/.agents/state/specs/SPECS.jsonl"
T62="$(drun)"
[ "$T62" = "committed" ] || fail "cas62: bascule SPECS, attendu 'committed', obtenu [$T62]"
[ "$(dg ls-tree -r --name-only HEAD -- .agents/state/specs | tr '\n' ' ')" = '.agents/state/specs/SPECS.jsonl ' ] \
  || fail "cas62: HEAD doit porter SPECS.jsonl et plus SPECS.json, obtenu [$(dg ls-tree -r --name-only HEAD -- .agents/state/specs)]"

# 63. D6 — CONTRÔLE : `LEDGER.json` seul modifié, aucun dossier → `committed` (vert à la base).
#     Mutant qui rougit : M-sans-status (chaque entrée ajoutée sans condition : un glob sans
#     correspondance fait rendre 128 à l'`add` et échouer le `commit` → `failed`).
dreset
printf '{"entries":[{"id":"L-1"}]}\n' > "$DR/.agents/state/memory/LEDGER.json"
T63="$(drun)"
[ "$T63" = "committed" ] || fail "cas63: LEDGER.json seul, attendu 'committed', obtenu [$T63]"
[ "$(dnoms)" = '.agents/state/memory/LEDGER.json ' ] || fail "cas63: le commit doit porter LEDGER.json seul, obtenu [$(dnoms)]"

# 64. D7 — CONTRÔLE : `MERGE_HEAD` et RIEN de sale → `busy:MERGE_HEAD`, rien de commité (vert à
#     la base, où les monolithes présents remplissaient toujours le sélecteur). Le contrôle `busy`
#     précède le compte des entrées. Mutant qui rougit : M-busy-après (le `busy` déplacé après le
#     compte : sélecteur vide → `nothing`).
dreset
: > "$DR/.git/MERGE_HEAD"
B64="$(dg rev-parse HEAD)"
T64="$(drun)"
[ "$T64" = "busy:MERGE_HEAD" ] || fail "cas64: MERGE_HEAD sans rien de sale, attendu 'busy:MERGE_HEAD', obtenu [$T64]"
[ "$(dg rev-parse HEAD)" = "$B64" ] || fail "cas64: aucun commit pendant un merge"
dreset

# 65. T-01M4RWC6VHHN479J2A9RRY1BE3 — RÉTENTION d'une LECTURE sous Copilot. Ce script ne porte PAS
#     le bloc de sortie précoce (plan, étape 5) : son filtre `grep` sort déjà avant tout python, et
#     un bloc lu par $PY ajouterait une à deux sondes python3 (au moins le double du coût). Charge
#     `view`, AGENTS_HOOK_HOST=copilot, CLAUDE_PROJECT_DIR posé comme sous la CLI (M-P4), depuis
#     un `mktemp -d` hors dépôt : rc 0, aucun artefact, bouchons `git` et `python3` jamais appelés
#     (bouchon écrit pour un chemin ABSOLU seulement). Vert avant ET après la tâche : son témoin
#     est le MUTANT — une copie jetable où un appel python3 précède le filtre (ancre EXACTEMENT
#     une fois) — sur lequel le bouchon python3 est appelé, donc le bras rougirait.
lc_bouchons() {  # $1 répertoire des bouchons, $2 trace
  local n reel
  for n in git python3; do
    reel="$(command -v "$n" 2>/dev/null || true)"
    case "$reel" in
      /*)
        {
          printf '#!/bin/sh\n'
          printf 'printf "%%s\\n" "%s" >> "%s"\n' "$n" "$2"
          printf 'exec "%s" "$@"\n' "$reel"
        } > "$1/$n"
        chmod +x "$1/$n"
        ;;
    esac
  done
}
lc_retention() {  # $1 script -> LC_RC LC_GIT LC_PY3 LC_ARTEFACTS LC_STUB_PY3
  local p
  p="$(mktemp -d)"
  mkdir -p "$p/w" "$p/bouchons" "$p/tmp"
  : > "$p/trace"
  lc_bouchons "$p/bouchons" "$p/trace"
  LC_STUB_PY3=0
  [ -x "$p/bouchons/python3" ] && LC_STUB_PY3=1
  LC_RC=0
  ( cd "$p/w" && printf '%s' '{"toolName":"view","toolArgs":{"path":"src/a.py"}}' \
      | env PATH="$p/bouchons:$PATH" TMPDIR="$p/tmp" AGENTS_HOOK_HOST=copilot CLAUDE_PROJECT_DIR="$p/w" bash "$1" ) \
      >/dev/null 2>&1 || LC_RC=$?
  LC_GIT="$(grep -c '^git$' "$p/trace" || true)"
  LC_PY3="$(grep -c '^python3$' "$p/trace" || true)"
  # `ls -A` de deux dossiers jetables, jamais un parcours d'arbre (test_repo_walk_census).
  LC_ARTEFACTS="$( { ls -A "$p/w"; ls -A "$p/tmp"; } | wc -l | tr -d ' ')"
  rm -rf "$p"
}
lc_retention "$HOOK"
[ "$LC_RC" -eq 0 ] || fail "cas65: copilot + view, attendu rc 0, obtenu $LC_RC"
[ "$LC_GIT" -eq 0 ] || fail "cas65: copilot + view, bouchon git appelé $LC_GIT fois, attendu 0"
[ "$LC_PY3" -eq 0 ] || fail "cas65: copilot + view, bouchon python3 appelé $LC_PY3 fois, attendu 0 (le filtre grep précède tout python)"
[ "$LC_ARTEFACTS" -eq 0 ] || fail "cas65: copilot + view, $LC_ARTEFACTS artefact(s) écrit(s), attendu aucun"
if [ "$LC_STUB_PY3" -eq 1 ]; then
  LC_PY=""
  for lc_c in python3 python; do
    "$lc_c" -c 'import sys; sys.exit(sys.version_info[0] != 3)' >/dev/null 2>&1 && { LC_PY="$lc_c"; break; }
  done
  [ -n "$LC_PY" ] || fail "cas65: python 3 introuvable pour fabriquer le mutant"
  LC_MUT="$(mktemp -d)"
  "$LC_PY" -c '
import sys
source, cible, ancre = sys.argv[1], sys.argv[2], sys.argv[3]
with open(source, encoding="utf-8") as f:
    lignes = f.readlines()
cibles = [i for i, l in enumerate(lignes) if l.lstrip().startswith("printf") and ancre in l]
if len(cibles) != 1:
    sys.exit(3)
lignes.insert(cibles[0], "python3 -c pass >/dev/null 2>&1\n")
with open(cible, "w", encoding="utf-8") as f:
    f.writelines(lignes)
' "$HOOK" "$LC_MUT/post-task-done-index.sh" '"$PAYLOAD" | grep -Eq' \
    || fail "cas65: mutant — l'ancre du filtre n'apparaît pas EXACTEMENT une fois (un mutant qui ne mute rien est un témoin muet)"
  lc_retention "$LC_MUT/post-task-done-index.sh"
  rm -rf "$LC_MUT"
  [ "$LC_PY3" -ge 1 ] || fail "cas65: sur le mutant (python3 avant le filtre), le bouchon python3 doit être appelé — sinon le bras ne pourrait pas rougir"
else
  echo "  SKIP cas65 (mutant) : python3 hors chemin absolu, aucun bouchon possible — la rétention reste tenue"
fi

# LE COMPTE SE DÉRIVE DU FICHIER, IL NE S'ÉCRIT PLUS (T-00000379 lot E).
# Cette ligne annonçait « 16/16 » alors que le fichier déclarait DÉJÀ 17 cas
# (14b avait été ajouté sans que personne ne re-touche le total) : un littéral
# de comptage périmé, exactement ce que ce dépôt traque ailleurs. Il est dérivé
# des en-têtes de cas, avec un plancher — si le motif cessait de correspondre,
# un « 0 cas » se lirait comme un vert.
CAS="$(grep -cE '^# [0-9]+[a-z]?\. ' "$0")"
[ "$CAS" -ge 2 ] || fail "sonde de comptage VIDE — $CAS en-tete(s) de cas lue(s) dans ce fichier"
echo "PASS: post-task-done-index ($CAS cas)"
