#!/usr/bin/env bash
# =====================================================================
# BANC — core-scripts/plan_pool.py classe-t-il encore honnêtement ? (T-00000379 lot D)
#
# Le suffixe `.test.sh` est délibéré : `core-scripts/run-bash-tests.sh` découvre
# cette suite (il élague `.agents/` et `.claude/`, PAS `scripts/`), donc la
# garde du verdict de péremption est DANS la porte qu'elle garde.
#
# ---------------------------------------------------------------------
# POURQUOI DE VRAIS COMMITS GIT SOUS mktemp, ET PAS DES MOCKS
# ---------------------------------------------------------------------
# Le verdict STALE repose sur DEUX faits git : `cat-file -e <sha>^{commit}` et
# `diff --name-only <sha>..HEAD`. Un git simulé mesurerait notre fixture au lieu
# de mesurer le script — un sha court, un sha rebasé, un diff entre ancêtre et
# HEAD sont exactement les endroits où une implémentation se trompe en silence.
# Le mini-dépôt ci-dessous porte DEUX commits pour que « write-set touché » soit
# un fait MESURÉ et non une convention de la suite.
#
# ---------------------------------------------------------------------
# LES FIXTURES SONT DANS NOTRE VOCABULAIRE — c'est le cœur de ce lot
# ---------------------------------------------------------------------
# L'original n'accepte que `PASS|CONCERNS|FAIL`, APRÈS un deux-points
# obligatoire. Mesuré sur nos 182 verdicts `plan-critic` réels : **6 reconnus,
# soit 3 %**. Et la cause dominante n'est pas le vocabulaire (14 `NO_GO`,
# 5 `GO_AVEC_RESERVES`) — c'est le SÉPARATEUR : 155 titres sur 182 n'ont pas de
# deux-points du tout.
#
# Donc les cas de ce banc sont écrits en `GO` / `GO_AVEC_RESERVES` / `NO_GO`,
# SANS deux-points, comme le journal réel. Dans le vocabulaire mort, ils
# passeraient tous sans rien prouver de ce que le pool rencontrera demain. Les
# trois historiques ont leurs propres cas, parce que `/night` les tient pour
# éligibles et qu'un lot qui les périmerait d'un coup casserait le passé.
#
# ---------------------------------------------------------------------
# CE QUE CE BANC NE FAIT PAS
# ---------------------------------------------------------------------
# Il n'asserte AUCUN verdict sur les stores réels du dépôt : ceux-ci bougent à
# chaque tâche et la suite rougirait sans qu'aucun code n'ait bougé. Le seul
# contact avec le réel est le TÉMOIN DE NON-VACUITÉ du cas (18), et il ne
# mesure que le plancher — voir la raison écrite là-bas.
#
# ---------------------------------------------------------------------
# EXTENSION T-00000383 — /reserve devient /planning, et le pool devient un PONT
# ---------------------------------------------------------------------
# Cas ajoutés : (1b) nouveau canon `Plan @ <sha> - <objet>` · (1c) ancien
# préfixe encore admis, COMPAT ADOPTANTS (0 titre de cette forme mesuré ici,
# jamais « non-régression du passé ») · (2b) l'alternance n'est pas un balayage
# (`Planning @ …` et le double espace restent SHA_ABSENT) · (19) amendé aux
# chemins `planning` + bras sur la DISPARITION des anciens · (20) la skill
# prescrit le pont vers la nuit · (21) le résiduel R4 (modif non commitée)
# ÉPINGLÉ, pas corrigé · (22) les trois surfaces /kickoff portent la voie de
# reprise · (23) l'ordre verdict→plan rend 11 · (24) la sous-déclaration du
# write-set est INVISIBLE au banc — la garantie est TEXTUELLE.
# =====================================================================
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

POOL="$ROOT/core-scripts/plan_pool.py"
[ -f "$POOL" ] || { echo "FAIL: core-scripts/plan_pool.py introuvable"; exit 1; }

PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "aucun interpreteur python sur le PATH" >&2; exit 1; fi
command -v git >/dev/null 2>&1 || { echo "git absent du PATH — suite non concluante" >&2; exit 1; }

TMP="$(mktemp -d)"
# Teardown tolérant (Windows : handles git encore tenus par un process fils) —
# jamais d'assertion sur le nettoyage.
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

pass=0; fail=0
ok() { echo "  PASS  $1"; pass=$((pass + 1)); }
ko() { echo "  FAIL  $1"; fail=$((fail + 1)); }

RC=0
run() {  # run <args de plan_pool.py…> — stdout et stderr capturés SÉPARÉMENT
  "$PY" "$POOL" "$@" >"$TMP/out" 2>"$TMP/err"; RC=$?
  return 0
}

# `grep -q -- <motif> <FICHIER>`, jamais `printf | grep -q` : `grep -q` sort dès
# la première correspondance, le `printf` amont prend un SIGPIPE, et sous
# `pipefail` le pipeline rend 141 ALORS MÊME QUE LE MOTIF EST TROUVÉ
# (T-00000544). L'original porte ce défaut ; il n'est pas repris.
expect_rc() {
  if [ "$RC" -eq "$1" ]; then ok "$2 (rc=$RC)"
  else ko "$2 — attendu rc=$1, obtenu rc=$RC"; sed 's/^/          /' "$TMP/out" "$TMP/err"; fi
}
expect_out() {
  if grep -q -- "$1" "$TMP/out"; then ok "$2"
  else ko "$2 — motif « $1 » absent de stdout"; sed 's/^/          /' "$TMP/out"; fi
}
expect_err() {
  if grep -q -- "$1" "$TMP/err"; then ok "$2"
  else ko "$2 — motif « $1 » absent de stderr"; sed 's/^/          /' "$TMP/err"; fi
}

# ---------------------------------------------------------------------
# MINI-DÉPÔT : deux commits réels, `a.txt` modifié entre les deux.
# ---------------------------------------------------------------------
REPO="$TMP/repo"
mkdir -p "$REPO/.agents/state/board" "$REPO/.agents/state/specs"
git -C "$REPO" init -q
git -C "$REPO" config user.email banc@local
git -C "$REPO" config user.name banc
printf 'v1\n' > "$REPO/a.txt"; printf 'stable\n' > "$REPO/b.txt"
git -C "$REPO" add a.txt b.txt >/dev/null
git -C "$REPO" commit -q -m c1
SHA1="$(git -C "$REPO" rev-parse --short HEAD)"
printf 'v2\n' > "$REPO/a.txt"
git -C "$REPO" add a.txt >/dev/null
git -C "$REPO" commit -q -m c2
SHA2="$(git -C "$REPO" rev-parse --short HEAD)"

board() {  # board <state>
  cat > "$REPO/.agents/state/board/TASKS.json" <<EOF
{"next_id": 2, "tasks": [{"id": "T-00000001", "state": "$1", "task": "banc", "owner": "dev-mono"}]}
EOF
}

# specs <titre-plan> <files-json> <titre-verdict|->
specs() {
  local verdict_entry=""
  local verdict_text="${4-}"
  if [ "$3" != "-" ]; then
    verdict_entry=$(cat <<EOF
,
    {"id": "S-00000002", "task": "T-00000001", "kind": "verdict",
     "title": "$3", "text": "$verdict_text", "files": [], "date": "2026-08-26"}
EOF
)
  fi
  cat > "$REPO/.agents/state/specs/SPECS.json" <<EOF
{"next_id": 3, "entries": [
    {"id": "S-00000001", "task": "T-00000001", "kind": "plan",
     "title": "$1", "text": "", "files": $2, "date": "2026-08-26"}$verdict_entry
]}
EOF
}

# specs_verdict_first <titre-plan> <files-json> <titre-verdict|->
# AIDE SŒUR de `specs()`, écrite À CÔTÉ et jamais à sa place : mêmes deux
# entrées, mêmes champs, seuls les ids `S-00000001`/`S-00000002` sont ÉCHANGÉS
# — le verdict prend la tête, le plan suit. C'est la seule façon d'exprimer
# l'ordre de journalisation que `/kickoff` porte AUJOURD'HUI (verdict PUIS
# plan) : `specs()` code plan=1 / verdict=2 en dur et ne peut pas le dire.
# Aucun cas existant ne l'appelle — le seul appelant est le cas (23), donc
# aucune fixture partagée et aucun effet de bord sur les chemins déjà verts.
specs_verdict_first() {
  local verdict_entry=""
  if [ "$3" != "-" ]; then
    verdict_entry=$(cat <<EOF
    {"id": "S-00000001", "task": "T-00000001", "kind": "verdict",
     "title": "$3", "text": "", "files": [], "date": "2026-08-26"},
EOF
)
  fi
  cat > "$REPO/.agents/state/specs/SPECS.json" <<EOF
{"next_id": 3, "entries": [
$verdict_entry
    {"id": "S-00000002", "task": "T-00000001", "kind": "plan",
     "title": "$1", "text": "", "files": $2, "date": "2026-08-26"}
]}
EOF
}

echo "================================================================"
echo "PLAN_POOL — grammaire RE-DERIVEE sur NOTRE journal"
echo "================================================================"

# ---------------------------------------------------------------------
echo "=== (1) READY — NOTRE vocabulaire, SANS deux-points (le cas que la source rejetait)"
board pending
specs "Plan de reserve @ $SHA2 - objet du banc" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "plan-critic GO (sans deux-points) -> READY"
expect_out "READY" "le code est dit"

echo "=== (1b) READY — NOUVEAU CANON \`Plan @ <sha> - <objet>\` (D4)"
# Le préfixe qu'écrit désormais /planning. Sans ce cas, le shard 3 pourrait
# perdre la branche neuve de l'alternance sans que rien ne rougisse.
specs "Plan @ $SHA2 - objet du banc" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "titre au nouveau canon -> READY"

echo "=== (1c) READY — ANCIEN PREFIXE encore admis : COMPAT ADOPTANTS"
# Nommé pour ce qu'il est : 0 titre `Plan de reserve @ …` mesuré dans le
# SPECS.json de CE dépôt (D4). L'alternance ne couvre donc pas « le passé
# d'ici » — elle couvre les journaux des dépôts ADOPTANTS, qui ont pu écrire
# ce préfixe avant le renommage. L'appeler « non-régression du passé » serait
# une garantie que rien ici ne mesure.
specs "Plan de reserve @ $SHA2 - objet du banc" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "ancien prefixe (compat adoptants) -> READY"

echo "=== (2) READY — GO_AVEC_RESERVES passe la porte et ne boucle pas"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic GO_AVEC_RESERVES (iteration 2/8, 0 bloquant)"
run --root "$REPO" check T-00000001
expect_rc 0 "GO_AVEC_RESERVES -> READY"
expect_out "GO_AVEC_RESERVES" "le verdict retenu est NOMME dans le detail"

echo "=== (2b) SHA_ABSENT — l'alternance est ANCREE et CLOSE, pas un balayage"
# Deux voisins immédiats du canon. `Planning @ …` : le nom de la commande n'est
# PAS le préfixe de checkpoint. `Plan  @ …` : double espace. Les deux DOIVENT
# rester hors grammaire, sinon `PLAN_TITLE_RE` se serait relâchée en passant à
# l'alternance et n'importe quel titre approchant tamponnerait une péremption.
specs "Planning @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 12 "\`Planning @ …\` -> SHA_ABSENT, jamais lu comme le canon"
specs "Plan  @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 12 "\`Plan  @ …\` (double espace) -> SHA_ABSENT"

echo "=== (3) NO_GO — refuse, ET n'est PAS lu comme un GO (ordre de l'alternance)"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic NO_GO (iteration 3/8) - 2 bloquants"
run --root "$REPO" check T-00000001
expect_rc 15 "NO_GO -> VERDICT_FAIL, jamais execute"
expect_out "NO_GO" "le detail dit NO_GO — la sous-chaine GO n'a pas ete lue comme un feu vert"

# ---------------------------------------------------------------------
echo "=== (4-6) VOCABULAIRE HISTORIQUE — admis, parce que /night le tient pour eligible"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic : PASS"
run --root "$REPO" check T-00000001
expect_rc 0 "PASS (avec deux-points, forme d'origine) -> READY"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic CONCERNS 0 blocking (11e revue)"
run --root "$REPO" check T-00000001
expect_rc 0 "CONCERNS -> READY"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic FAIL 2/2 (rev2)"
run --root "$REPO" check T-00000001
expect_rc 15 "FAIL -> VERDICT_FAIL"

# ---------------------------------------------------------------------
echo "=== (7) STALE-FICHIER — le write-set a bouge depuis le sha tamponne"
specs "Plan de reserve @ $SHA1 - objet" '["a.txt", "b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 14 "write-set touche -> STALE"
expect_out "a.txt" "le fichier fautif est NOMME"

echo "=== (8) STALE-SHA — sha irresoluble : 14 + mention sur stderr, JAMAIS un crash"
specs "Plan de reserve @ deadbeef - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 14 "sha irresoluble -> STALE"
expect_err "sha deadbeef introuvable" "la mention explicite est sur stderr"

# ---------------------------------------------------------------------
echo "=== (9-13) LES CINQ NON-READY STRUCTURELS"
cat > "$REPO/.agents/state/specs/SPECS.json" <<'EOF'
{"next_id": 1, "entries": []}
EOF
run --root "$REPO" check T-00000001
expect_rc 10 "journal vide -> NO_PLAN"

specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "-"
run --root "$REPO" check T-00000001
expect_rc 11 "aucun verdict posterieur -> PLAN_SANS_VERDICT"

specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "revue faite, tout va bien, GO"
run --root "$REPO" check T-00000001
expect_rc 11 "titre libre CONTENANT GO -> PLAN_SANS_VERDICT, jamais READY"
expect_out "hors grammaire" "la raison est dite"

specs "un titre de plan qui ne tamponne rien" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 12 "titre non canonique -> SHA_ABSENT"

specs "Plan de reserve @ $SHA2 - objet" '[]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 13 "files vide -> WRITE_SET_ABSENT"

# ---------------------------------------------------------------------
echo "=== (14-15) BOARD — seul pending est consommable"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00099999
expect_rc 16 "tache absente du board -> 16"
board done
run --root "$REPO" check T-00000001
expect_rc 16 "state=done -> 16"
expect_out "state=done" "la raison est dite"
board pending

# ---------------------------------------------------------------------
echo "=== (16) STORE MALFORME — echec FRANC, exit 1, jamais degrade en « pas de plan »"
printf '{"entries": [' > "$REPO/.agents/state/specs/SPECS.json"
run --root "$REPO" check T-00000001
expect_rc 1 "JSON tronque -> erreur d'execution"
expect_err "pas un JSON valide" "la cause est nommee sur stderr"

# ---------------------------------------------------------------------
echo "=== (17) LE RELEVE DIT QU'IL NE FAIT PAS AUTORITE (A15)"
specs "Plan de reserve @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" status
expect_rc 0 "status vert"
expect_out "READY" "status porte le meme verdict que check"
expect_out "NON-AUTORITATIF" "le releve se declare NON-AUTORITATIF sur l'eligibilite /night"
expect_out "/night" "et il NOMME la machine qui, elle, fait autorite"

# ---------------------------------------------------------------------
echo "=== (17b) TEMOIN INVERSE — retirer le marqueur de non-autorite rougirait"
# Une copie du script, amputee de son seul marqueur. Sans ce bras, (17) serait
# vert le jour ou la phrase disparait d'une refonte de `cmd_status` — la garde
# asserterait alors sur une chaine qu'elle ne trouve plus nulle part, et c'est
# le `ko` qui le dirait ; ici on prouve l'inverse, que la chaine est bien LA
# porteuse de la propriete.
sed 's/RELEVE AMONT, NON-AUTORITATIF : il ne /RELEVE AMONT : il /' "$POOL" > "$TMP/pool_mute.py"
if grep -q 'NON-AUTORITATIF : il ne ' "$TMP/pool_mute.py"; then
  ko "la mutation n'a pas retire le marqueur — le bras (17) ne prouve rien"
else
  "$PY" "$TMP/pool_mute.py" --root "$REPO" status >"$TMP/mute_out" 2>/dev/null
  if grep -q "NON-AUTORITATIF" "$TMP/mute_out"; then
    ko "le script mute annonce encore la non-autorite"
  else
    ok "script mute : le marqueur disparait de la sortie -> (17) mord bien sur lui"
  fi
fi

# ---------------------------------------------------------------------
echo "=== (18) TEMOIN DE NON-VACUITE SUR LE JOURNAL REEL"
# La grammaire est-elle vivante sur NOTRE corpus, ou verte seulement sur ses
# propres fixtures ? On la charge depuis le MODULE (jamais une copie du motif —
# une copie prouverait la copie) et on la passe sur SPECS.json.
#
# PLANCHER SEULEMENT, et la raison est ecrite : ce banc VOYAGE. Exiger 100 % de
# reconnaissance ferait rougir le premier jour tout projet adoptant dont le
# journal porte des titres libres anterieurs — exactement le defaut « une
# constante qui voyage sans son perimetre » que le lot A a nomme. Le plancher
# prouve la non-vacuite ici ; le taux est IMPRIME pour etre lu.
"$PY" - "$ROOT" > "$TMP/out" 2>"$TMP/err" <<'PYEOF'
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "core-scripts"))
import plan_pool
specs = pathlib.Path(sys.argv[1]) / ".agents" / "state" / "specs" / "SPECS.json"
if not specs.exists():
    print("ABSENT 0 0"); raise SystemExit(0)
entries = json.loads(specs.read_text(encoding="utf-8"))["entries"]
titres = [e["title"] for e in entries if e.get("kind") == "verdict"
          and str(e.get("title", "")).startswith("plan-critic")]
reconnus = [t for t in titres if plan_pool.VERDICT_TITLE_RE.match(t)]
print(f"RECONNUS {len(reconnus)} {len(titres)}")
for t in titres:
    if not plan_pool.VERDICT_TITLE_RE.match(t):
        print(f"  hors grammaire : {t[:88]}")
PYEOF
LIGNE="$(head -1 "$TMP/out")"
NR="$(printf '%s' "$LIGNE" | awk '{print $2}')"
NT="$(printf '%s' "$LIGNE" | awk '{print $3}')"
case "$LIGNE" in
  ABSENT*) ok "aucun SPECS.json sur cette racine — temoin sans objet, DIT" ;;
  RECONNUS*)
    if [ "${NR:-0}" -ge 1 ]; then
      ok "la grammaire MORD sur le journal reel : $NR / $NT titres plan-critic reconnus"
      [ "$NR" != "$NT" ] && sed -n '2,6p' "$TMP/out"
    else
      ko "la grammaire ne reconnait AUCUN des $NT titres reels — verte sur ses seules fixtures"
      sed -n '2,6p' "$TMP/out"
    fi ;;
  *) ko "sonde de non-vacuite illisible : $LIGNE"; sed 's/^/          /' "$TMP/err" ;;
esac

# ---------------------------------------------------------------------
echo "=== (19) NON-DIVERGENCE SKILL/OUTIL — /planning cite plan_pool.py (A15b)"
# A16 force l'EXISTENCE de la skill ; ici c'est son ACCORD avec l'outil. Deux
# proprietes differentes : une skill presente qui ne cite pas son outil laisse
# l'operateur sans la regle de peremption.
SKILL="$ROOT/.agents/skills/planning/SKILL.md"
CMD="$ROOT/.claude/commands/planning.md"
# BRAS NEUF (T-00000383, R6) : un demi-renommage — /reserve ET /planning
# coexistants — serait un agenda ambigu que les deux assertions ci-dessous
# laisseraient passer, puisqu'elles ne parlent que des NOUVEAUX chemins.
if [ ! -e "$ROOT/.agents/skills/reserve" ]; then ok ".agents/skills/reserve a DISPARU"
else ko ".agents/skills/reserve existe encore — renommage a moitie fait, deux skills concurrentes"; fi
if [ ! -e "$ROOT/.claude/commands/reserve.md" ]; then ok ".claude/commands/reserve.md a DISPARU"
else ko ".claude/commands/reserve.md existe encore — deux commandes pour un seul workflow"; fi
for f in "$SKILL" "$CMD"; do
  if [ ! -f "$f" ]; then ko "${f#"$ROOT"/} absent"; continue; fi
  if grep -q 'plan_pool\.py' "$f"; then ok "${f#"$ROOT"/} cite plan_pool.py"
  else ko "${f#"$ROOT"/} ne cite PAS plan_pool.py — la regle de peremption est orpheline"; fi
done
if [ -f "$SKILL" ]; then
  if grep -q '/night' "$SKILL"; then ok "le corps de /planning NOMME /night comme l'autorite"
  else ko "le corps de /planning ne nomme pas /night — les deux machines a verdict se confondront"; fi
  # Bras : retirer la citation rougit.
  grep -v 'plan_pool\.py' "$SKILL" > "$TMP/skill_mute.md"
  if grep -q 'plan_pool\.py' "$TMP/skill_mute.md"; then
    ko "la mutation n'a rien retire — le bras ne prouve rien"
  else
    ok "mutation : la skill amputee de sa citation ne passerait plus l'assertion ci-dessus"
  fi
fi

# ---------------------------------------------------------------------
echo "=== (20) PONT VERS LA NUIT — la skill /planning prescrit l'empreinte et le FICHIER"
# Meme famille que (19) : un net TEXTUEL, pas un net de comportement. Ce que
# /planning produit n'est consommable par /night que si le lot porte les deux
# moities du pont : un FICHIER `docs/tasks/T-NNNNNNNN-plan.md` (condition 5,
# enrolement) et UN `sha256=` dans le TEXTE du verdict (conditions 3 et 4,
# night_approve.verdict_fingerprint). Une skill qui oublie l'une des deux rend
# un lot que la nuit SAUTERA en silence — le pire des echecs, parce qu'il ne
# ressemble pas a un echec.
if [ -f "$SKILL" ]; then
  if grep -q 'sha256=' "$SKILL"; then ok "la skill /planning prescrit l'empreinte sha256="
  else ko "la skill /planning ne prescrit PAS sha256= — la nuit ne pourra jamais fermer sa condition 4"; fi
  if grep -q 'docs/tasks/T-' "$SKILL"; then ok "la skill /planning NOMME le fichier docs/tasks/T-…-plan.md"
  else ko "la skill /planning ne nomme pas docs/tasks/T-…-plan.md — le pont n'a pas de fichier"; fi
  # COUTURE A<->B, les DEUX bouts au meme banc (exec-critic T-00000383) : (1b) prouve que
  # PLAN_TITLE_RE ACCEPTE `Plan @ <sha> - <objet>` ; ceci prouve que la skill PRESCRIT ce
  # titre-la, et pas un voisin que (2b) montre REFUSE. Une regex verte prouve ce qu'elle
  # accepte, jamais ce que l'ecrivain ecrit.
  if grep -qF -- '"Plan @ <sha> - <objet>"' "$SKILL"; then ok "la skill /planning prescrit le titre canonique \"Plan @ <sha> - <objet>\" que PLAN_TITLE_RE accepte"
  else ko "la skill /planning ne prescrit pas le titre canonique — tout plan qu'elle ecrirait tomberait en 12 SHA_ABSENT"; fi
  # Bras : une skill amputee de l'empreinte ne passerait plus l'assertion.
  grep -v 'sha256=' "$SKILL" > "$TMP/skill_mute20.md"
  if grep -q 'sha256=' "$TMP/skill_mute20.md"; then
    ko "la mutation n'a rien retire — le bras (20) ne prouve rien"
  else
    ok "mutation : la skill amputee de sha256= rougirait bien ci-dessus"
  fi
fi

# ---------------------------------------------------------------------
echo "=== (21) MODIFICATION NON COMMITEE du write-set -> encore READY (residuel R4, ASSUME)"
# CE CAS NE DENONCE PAS UN BUG — il EPINGLE une limite assumee. `moved_since`
# (SYM-461) compare `git diff <sha>..HEAD`, donc COMMIT a COMMIT : une
# modification presente dans l'arbre de travail et jamais commitee n'entre dans
# aucun diff, et le releve SOUS-detecte la peremption. Corriger est HORS
# perimetre (R4). Ce qu'on fait a la place : on FIGE le comportement ici, pour
# qu'une refonte de `moved_since` soit VUE, et la voie de reprise /kickoff
# DIVULGUE la limite au pilote (cas 22, 4e assertion). Un READY vert ne prouve
# donc pas que l'arbre est propre — seulement qu'aucun COMMIT n'a bouge.
specs "Plan @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
printf 'modifie mais jamais commite\n' > "$REPO/b.txt"
run --root "$REPO" check T-00000001
expect_rc 0 "b.txt modifie SANS commit -> toujours READY (limite assumee de moved_since)"
printf 'stable\n' > "$REPO/b.txt"   # fixture rendue propre : les cas suivants n'heritent pas de la salissure

# ---------------------------------------------------------------------
echo "=== (22) REPRISE /kickoff — les TROIS surfaces portent la voie de D5"
# Net TEXTUEL sur les trois surfaces /kickoff du depot (mesure : aucun miroir
# sous .codex/ ni .gemini/). Une branche de reprise decrite sur UNE seule des
# trois serait un comportement d'hote, pas une regle du kit — et les deux
# autres replanifieraient un plan deja valide sans que rien ne rougisse.
# BRAS DE MUTATION (documente) : retirer la ligne de divulgation R4 de l'UNE
# des trois DOIT rougir — c'est la 4e assertion, prononcee fichier par fichier
# et non « au moins une surface », donc l'amputation d'une seule est visible.
# Le bras executable est monte plus bas des qu'au moins une surface porte la
# ligne ; tant que le shard 5 n'a pas atterri il est SANS OBJET et le dit.
for f in ".claude/commands/kickoff.md" ".agents/skills/kickoff/SKILL.md" ".github/copilot-instructions.md"; do
  p="$ROOT/$f"
  if [ ! -f "$p" ]; then ko "$f absent"; continue; fi
  if grep -q -- 'plan_pool\.py check' "$p"; then ok "$f invoque plan_pool.py check (sonde 2 de D5)"
  else ko "$f n'invoque PAS plan_pool.py check — la voie de reprise n'a pas de sonde de fraicheur"; fi
  manque=""
  # Codes 10..15 ancres a LEUR nom (vocabulaire de plan_pool.CODES) : un « 14 »
  # nu se confondrait avec un numero d'etape. 16 n'a pas de nom-jeton (sa
  # glose est en prose, donc dependante de la langue de la surface) : on le
  # controle en frontiere numerique, et cette borne est DITE plutot que tue.
  for pair in "10:NO_PLAN" "11:PLAN_SANS_VERDICT" "12:SHA_ABSENT" "13:WRITE_SET_ABSENT" "14:STALE" "15:VERDICT_FAIL"; do
    c="${pair%%:*}"; n="${pair##*:}"
    grep -qE -- "$c[^0-9A-Za-z]{0,4}$n" "$p" || manque="$manque $c/$n"
  done
  grep -qE -- '(^|[^0-9])16([^0-9]|$)' "$p" || manque="$manque 16"
  if [ -z "$manque" ]; then ok "$f NOMME les sept codes de sortie (10..16)"
  else ko "$f ne nomme pas :$manque — un rc non nomme se lit comme une panne, pas comme une replanification"; fi
  if grep -qiE -- 'never skipped|jamais saut' "$p"; then ok "$f dit que la porte humaine n'est JAMAIS sautee"
  else ko "$f ne dit PAS que la porte n'est jamais sautee — une reprise 5/5 se lirait comme une auto-approbation"; fi
  if grep -qiE -- 'modifications non commit.es du write-set ne sont pas vues|uncommitted modifications of the write-set are not seen' "$p"; then
    ok "$f divulgue le residuel R4 a la porte"
  else ko "$f ne divulgue PAS R4 — un READY y passerait pour une preuve de fraicheur de l'arbre"; fi
done
PORTEUR=""
for f in ".claude/commands/kickoff.md" ".agents/skills/kickoff/SKILL.md" ".github/copilot-instructions.md"; do
  if grep -qiE -- 'modifications non commit.es du write-set ne sont pas vues|uncommitted modifications of the write-set are not seen' "$ROOT/$f"; then PORTEUR="$ROOT/$f"; break; fi
done
if [ -z "$PORTEUR" ]; then
  echo "  ----  bras (22) SANS OBJET : aucune des trois surfaces ne porte encore la ligne R4 (shard 5 non atterri) — la 4e assertion ci-dessus est deja rouge, et c'est elle la preuve"
else
  grep -viE -- 'modifications non commit.es du write-set ne sont pas vues|uncommitted modifications of the write-set are not seen' "$PORTEUR" > "$TMP/kickoff_mute.md"
  if grep -qiE -- 'modifications non commit.es du write-set ne sont pas vues|uncommitted modifications of the write-set are not seen' "$TMP/kickoff_mute.md"; then
    ko "la mutation n'a pas retire la ligne R4 — le bras (22) ne prouve rien"
  else
    ok "mutation : la surface amputee de sa ligne R4 rougirait bien ci-dessus"
  fi
fi

# ---------------------------------------------------------------------
echo "=== (23) ORDRE INVERSE (verdict PUIS plan) -> 11, jamais READY"
# La regle dont depend TOUTE la reorganisation du shard 5 : `classify` prend
# `plans[-1]` et exige un verdict d'id numerique SUPERIEUR (plan_pool.py
# :296-300). Journaliser le verdict d'abord — l'ordre que /kickoff porte
# aujourd'hui — rend donc 11 (PLAN_SANS_VERDICT) meme avec un titre canonique,
# un write-set plein et un GO franc : la branche de reprise resterait MORTE.
# Sans ce cas, le jour ou `classify` cesserait d'exiger la posteriorite, la
# reorganisation du shard 5 deviendrait inutile sans que rien ne rougisse.
# BRAS DE MUTATION : echanger les deux ids dans la fixture (donc revenir a
# l'ordre plan -> verdict) DOIT rendre 0 — c'est exactement la fixture du cas
# (1b), verte plus haut sur les memes titre, write-set et verdict ; le bras est
# donc DEJA execute par ce banc, et le nommer ici evite de le doubler.
specs_verdict_first "Plan @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 11 "verdict journalise AVANT le plan -> PLAN_SANS_VERDICT"

# ---------------------------------------------------------------------
echo "=== (24) SOUS-DECLARATION du write-set — ce que le banc NE PEUT PAS voir"
# Le cas (7) INVERSE, sur la meme fixture et SANS commit neuf (un 3e commit
# decalerait HEAD et ferait virer STALE des cas deja verts). Titre canonique,
# tampon $SHA1, mais `--files` OMET `a.txt`, qui a pourtant bouge en c2.
# Resultat : 0 (READY) — et c'est CONFORME : `classify` n'intersecte
# `moved_since` qu'avec le write-set DECLARE (plan_pool.py:314) et n'a AUCUN
# moyen de savoir qu'il est troue. Ce cas ne denonce donc rien ; il EPINGLE que
# la garantie « ni trou ni superflu » est TEXTUELLE — la regle ecrite sur les
# trois surfaces /kickoff — et jamais executable. Aucun banc, celui-ci compris,
# ne peut voir une sous-declaration : un READY vert n'est PAS une preuve de
# completude du write-set, et c'est ecrit ici pour qu'il ne se lise pas ainsi.
specs "Plan @ $SHA1 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "write-set TROUE (a.txt bouge en c2, OMIS) -> 0 : l'outil ne peut pas le voir"
# BRAS DE MUTATION : declaration HONNETE — ajouter le fichier reellement bouge.
# C'est lui qui prouve que le mecanisme fonctionne des que la declaration est
# complete, et donc que le 0 ci-dessus vient bien de l'omission, pas d'une
# panne de `moved_since`.
specs "Plan @ $SHA1 - objet" '["a.txt", "b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 14 "bras : write-set HONNETE -> 14 (STALE) — le 0 ci-dessus vient de l'omission"

# ---------------------------------------------------------------------
echo "=== (25) INTERRUPTION AVANT CRITIC — IN_PROGRESS n'est jamais READY"
PLAN_FILE="$REPO/docs/tasks/T-00000001-plan.md"
mkdir -p "$REPO/docs/tasks"
printf '%s\n' \
  '# PLAN — T-00000001 — draft' \
  'Tâches : T-00000001' \
  "@ $SHA2" \
  'STATUS: IN_PROGRESS' \
  'REVISION: 1' \
  'WRITE-SET: b.txt' > "$PLAN_FILE"
specs "Plan @ $SHA2 - objet rev1" '["b.txt"]' "-"
run --root "$REPO" check T-00000001
expect_rc 11 "draft IN_PROGRESS sans critic -> PLAN_SANS_VERDICT"
expect_out "IN_PROGRESS" "le statut intermediaire est nomme"

# ---------------------------------------------------------------------
echo "=== (26) APRES NO_GO — CRITIC_REJECTED reste non consommable"
printf '%s\n' \
  '# PLAN — T-00000001 — draft refuse' \
  'Tâches : T-00000001' \
  "@ $SHA2" \
  'STATUS: CRITIC_REJECTED' \
  'REVISION: 1' \
  'WRITE-SET: b.txt' > "$PLAN_FILE"
specs "Plan @ $SHA2 - objet rev1" '["b.txt"]' "plan-critic NO_GO" \
  "plan=docs/tasks/T-00000001-plan.md revision=1 status=CRITIC_REJECTED sha256=0000000000000000000000000000000000000000000000000000000000000000"
run --root "$REPO" check T-00000001
expect_rc 11 "draft CRITIC_REJECTED -> non-READY"
expect_out "CRITIC_REJECTED" "le refus progressif est nomme"

# ---------------------------------------------------------------------
echo "=== (27) APRES AMENDEMENT — un ancien verdict n'autorise pas revision 2"
printf '%s\n' \
  '# PLAN — T-00000001 — draft amende' \
  'Tâches : T-00000001' \
  "@ $SHA2" \
  'STATUS: IN_PROGRESS' \
  'REVISION: 2' \
  'WRITE-SET: b.txt' > "$PLAN_FILE"
cat > "$REPO/.agents/state/specs/SPECS.json" <<EOF
{"next_id": 4, "entries": [
  {"id": "S-00000001", "task": "T-00000001", "kind": "plan",
   "title": "Plan @ $SHA2 - objet rev1", "text": "", "files": ["b.txt"], "date": "2026-08-26"},
  {"id": "S-00000002", "task": "T-00000001", "kind": "verdict",
   "title": "plan-critic GO", "text": "", "files": [], "date": "2026-08-26"},
  {"id": "S-00000003", "task": "T-00000001", "kind": "plan",
   "title": "Plan @ $SHA2 - objet rev2", "text": "", "files": ["b.txt"], "date": "2026-08-26"}
]}
EOF
run --root "$REPO" check T-00000001
expect_rc 11 "revision 2 sans nouveau verdict -> PLAN_SANS_VERDICT"

# ---------------------------------------------------------------------
echo "=== (28) WRITE-SET PERDU — une revision incomplete reste refusee"
specs "Plan @ $SHA2 - objet rev2" '[]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 13 "write-set perdu -> WRITE_SET_ABSENT"

# ---------------------------------------------------------------------
echo "=== (29) HASH DIVERGENT — le verdict final ne rend pas READY"
printf '%s\n' \
  '# PLAN — T-00000001 — final' \
  'Tâches : T-00000001' \
  "@ $SHA2" \
  'REVISION: 2' \
  'WRITE-SET: b.txt' > "$PLAN_FILE"
specs "Plan @ $SHA2 - objet final" '["b.txt"]' "plan-critic GO" \
  "plan=docs/tasks/T-00000001-plan.md sha256=0000000000000000000000000000000000000000000000000000000000000000"
run --root "$REPO" check T-00000001
expect_rc 14 "sha256 du verdict different des octets -> STALE"
expect_out "plan modifié" "la divergence d'empreinte est nommee"

# ---------------------------------------------------------------------
echo "=== (30) PLAN FINAL — hash concordant et verdict final restent READY"
PLAN_HASH=$("$PY" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$PLAN_FILE")
specs "Plan @ $SHA2 - objet final" '["b.txt"]' "plan-critic GO" \
  "plan=docs/tasks/T-00000001-plan.md sha256=$PLAN_HASH"
run --root "$REPO" check T-00000001
expect_rc 0 "plan final + verdict final + sha256 concordant -> READY"

# ---------------------------------------------------------------------
# (31) — S-<ULID> : la POSTÉRIORITÉ suit la clé à DEUX ÉTAGES (T-00000726, C1e)
# ---------------------------------------------------------------------
# `(\d+)\Z` LEVAIT sur un `S-<ULID>` à lettre finale (rc 1), et rangeait en
# SILENCE un `S-<ULID>` à chiffre final par sa queue (« …WV6M2 » valait 2). La clé
# `(0, n)` ancien / `(1, ulid)` ULID — recopiée de `tasks.sort_key`, jamais
# importée — met tout ULID APRÈS tout ancien. Fixtures JSON : avant la bascule C2
# aucun `specs.py add` n'émet de `S-<ULID>`. Le plan de (25)-(30) est retiré :
# ces cas jugent le journal, pas un fichier de plan.
rm -f "$PLAN_FILE"
U_LETTER="01M3250V003HCPQKTZ8ENYF4VM"; U_DIGIT="01M3253WN0W4D0K2S3759WV6M2"

# specs_ids <id-plan> <id-verdict> <titre-plan> <files-json> <titre-verdict>
# AIDE SŒUR de `specs()`, écrite À CÔTÉ et jamais à sa place : `specs()` code
# S-00000001/S-00000002 en dur et ne peut pas dire un `S-<ULID>`. Sans `next_id` :
# plan_pool ne le lit pas, et C2 le retire.
specs_ids() {
  cat > "$REPO/.agents/state/specs/SPECS.json" <<EOF
{"entries": [
    {"id": "$1", "task": "T-00000001", "kind": "plan",
     "title": "$3", "text": "", "files": $4, "date": "2026-10-08"},
    {"id": "$2", "task": "T-00000001", "kind": "verdict",
     "title": "$5", "text": "", "files": [], "date": "2026-10-08"}
]}
EOF
}

echo "=== (31) plan S-00000001 + verdict S-<ULID a lettre finale> -> READY"
specs_ids S-00000001 "S-$U_LETTER" "Plan @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "verdict S-<ULID> posterieur a un plan ancien -> READY (jamais rc 1)"
# Bras `status` : le tri des tâches pending (`verdicts_for_pending`) passe AUSSI
# par la clé — `check` ne l'atteint pas. Une `T-<ULID>` pending vient APRÈS T-00000001.
cat > "$REPO/.agents/state/board/TASKS.json" <<EOF
{"tasks": [{"id": "T-$U_LETTER", "state": "pending", "task": "banc ulid", "owner": "dev-mono"},
           {"id": "T-00000001", "state": "pending", "task": "banc", "owner": "dev-mono"}]}
EOF
run --root "$REPO" status
expect_rc 0 "status sur un board mele (ancien + T-<ULID>) : rc 0, jamais une levee"
expect_out "T-00000001 *READY" "status porte le READY de T-00000001"
la="$(grep -n -m 1 -F -- "T-00000001" "$TMP/out" | cut -d: -f1)"
lb="$(grep -n -m 1 -F -- "T-$U_LETTER" "$TMP/out" | cut -d: -f1)"
if [ -n "$la" ] && [ -n "$lb" ] && [ "$la" -lt "$lb" ]; then ok "la ligne T-<ULID> vient APRES T-00000001"
else ko "ordre du status — T-00000001 ligne [$la], T-<ULID> ligne [$lb]"; sed 's/^/          /' "$TMP/out"; fi
board pending

echo "=== (31b) plan S-<ULID> + verdict S-00000002 -> 11 (le verdict ancien est ANTERIEUR)"
specs_ids "S-$U_LETTER" S-00000002 "Plan @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 11 "un verdict ancien n'autorise pas un plan S-<ULID> -> PLAN_SANS_VERDICT"

echo "=== (31c) plan S-00000221 + verdict S-<ULID a chiffre final> -> READY"
# `(\d+)\Z` lisait « …WV6M2 » comme 2 < 221 : verdict jugé ANCIEN, en silence.
specs_ids S-00000221 "S-$U_DIGIT" "Plan @ $SHA2 - objet" '["b.txt"]' "plan-critic GO"
run --root "$REPO" check T-00000001
expect_rc 0 "verdict S-<ULID> a queue chiffree, posterieur a S-00000221 -> READY"

echo "=== (31d) PARITE de la cle avec tasks.sort_key (recopiee, jamais importee)"
"$PY" - "$ROOT" "$U_LETTER" "$U_DIGIT" > "$TMP/out" 2>"$TMP/err" <<'PYEOF'
import pathlib, sys
racine, ul, ud = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(racine / "core-scripts")); sys.path.insert(0, str(racine / ".agents" / "bin"))
import plan_pool, tasks
ids = ["S-1", "S-003", "S-00000002", "S-00000221", "T-00000001", "S-" + ul, "S-" + ud, "T-" + ul, "L-" + ud,
       "S-" + "1" * 15, "S-" + "1" * 16, "S-0" + "1" * 15]
ecarts = []
for i in ids:
    issues = []
    for cle in (plan_pool.sort_key, tasks.sort_key):
        try:
            issues.append(("rang", cle(i)))
        except Exception as exc:  # LEVER des DEUX cotes est une parite ; d'un seul, un ecart
            issues.append(("leve", type(exc).__name__))
    if issues[0] != issues[1] and not (issues[0][0] == issues[1][0] == "leve"):
        ecarts.append(f"{i} {issues}")
print("ecarts", ecarts)
sys.exit(1 if ecarts else 0)
PYEOF
RC=$?
expect_rc 0 "plan_pool.sort_key == tasks.sort_key sur anciens et ULID (T/S/L)"

echo "=== (31e) :360 load_specs — le DERNIER verdict est celui de l'ordre de frappe (U_DIGIT)"
cat > "$REPO/.agents/state/specs/SPECS.json" <<JSON
{"entries": [
    {"id": "S-00000001", "task": "T-00000001", "kind": "plan",
     "title": "Plan @ $SHA2 - objet", "text": "", "files": ["b.txt"], "date": "2026-10-08"},
    {"id": "S-00000221", "task": "T-00000001", "kind": "verdict",
     "title": "plan-critic NO_GO", "text": "", "files": [], "date": "2026-10-08"},
    {"id": "S-$U_DIGIT", "task": "T-00000001", "kind": "verdict",
     "title": "plan-critic GO", "text": "", "files": [], "date": "2026-10-09"}
]}
JSON
run --root "$REPO" check T-00000001
expect_rc 0 "(31e) GO S-<U_DIGIT> posterieur au NO_GO S-00000221 -> READY (jamais VERDICT_FAIL)"
echo "=== (31f) :552 verdicts_for_pending — T-<U_DIGIT> apres T-00000003"
cat > "$REPO/.agents/state/board/TASKS.json" <<JSON
{"tasks": [{"id": "T-$U_DIGIT", "state": "pending", "task": "banc ulid", "owner": "dev-mono"},
           {"id": "T-00000003", "state": "pending", "task": "banc 3", "owner": "dev-mono"},
           {"id": "T-00000001", "state": "pending", "task": "banc", "owner": "dev-mono"}]}
JSON
run --root "$REPO" status
expect_rc 0 "(31f) status sur un board mele a U_DIGIT : rc 0"
la="$(grep -n -m 1 -F -- "T-00000003" "$TMP/out" | cut -d: -f1)"
lb="$(grep -n -m 1 -F -- "T-$U_DIGIT" "$TMP/out" | cut -d: -f1)"
if [ -n "$la" ] && [ -n "$lb" ] && [ "$la" -lt "$lb" ]; then ok "(31f) T-00000003 avant T-<U_DIGIT>"
else ko "(31f) ordre du status — T-00000003 ligne [$la], T-<U_DIGIT> ligne [$lb]"; sed 's/^/          /' "$TMP/out"; fi
board pending

# ---------------------------------------------------------------------
echo "================================================================"
echo "Resume : $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ]
