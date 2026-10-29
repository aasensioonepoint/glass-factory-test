#!/usr/bin/env bash
# =============================================================================
# SUITE DE `core-scripts/check-stale-justification.sh` (T-00000322)
#
# Decouverte par `core-scripts/run-bash-tests.sh` (elagage, pas liste blanche), qui
# est lui-meme une etape de `scripts/ci-steps.sh` PLACEE AVANT la garde : une
# regression du scanner rougit donc AVANT que la porte ne s appuie sur lui.
#
# =============================================================================
# AUCUN IDENTIFIANT DE TACHE EN CLAIR DANS CE FICHIER — CONTRAINTE, PAS STYLE
# =============================================================================
# Meme discipline, et meme raison, que `class0-scan.test.sh` et ses secrets
# assembles a l execution : la garde que cette suite teste BALAYE TOUT LE DEPOT,
# donc elle balaye AUSSI ce fichier-ci. Poser ici une forme conditionnelle suivie
# d un identifiant de tache EN CLAIR ferait rougir la porte sur les fixtures
# elles-memes — mesure : 18 violations, toutes dans ce seul fichier, a la
# premiere redaction.
#
# Les deux corrections possibles etaient d exclure `*.test.sh` du balayage, ou
# d assembler les identifiants a l execution. LA PREMIERE EST REFUSEE : une
# justification perimee dans un fichier de test est une justification perimee, et
# une garde qui s aveugle sur une famille de fichiers finit par etre contournee
# en y deplacant le texte. Les identifiants sont donc CONSTRUITS par `mk_tid`, et
# le littéral complet n existe qu en memoire, le temps du test.
#
#   (a)  arbre propre                              -> 0
#   (b)  forme conditionnelle sur tache CLOSE      -> 1, E1
#   (c)  alias de version V1-NN (T-CLOSE)          -> 1, E1
#   (d)  tache ABSENTE du board                    -> 1, E2
#   (e)  forme conditionnelle sur tache OUVERTE    -> 0
#   (f)  LES SEPT QUASI-CORRESPONDANCES            -> 0   <-- le coeur de la suite
#   (g)  les NEUF formes retenues, EN DEUX GRAPHIES-> 1 chacune
#   (h)  perimetre : .md ignore, .agents/ elague
#   (i)  une ligne fautive NON-ASCII s imprime     -> regression mesuree
#   (j)  la garde tourne sur le DEPOT REEL (motif maison) + temoin que le juge mord
#   (k)  aucun chemin ne rend 4
#   (l)  le board n est JAMAIS ecrit
#   (m)  checkouts IMBRIQUES : un worktree ou un clone NON ENREGISTRE est elague,
#        tout chemin ENREGISTRE (sous-module, fichier suivi) reste balaye ; la
#        config du depot interroge (core.fsmonitor) n est jamais executee
#
# L ENVIRONNEMENT GIT EST PURGE EN PREMIERES LIGNES EXECUTABLES (T-00001073).
# Cette suite cree des depots, des worktrees et des commits ; elle est ramassee
# par `run-bash-tests.sh`, lui-meme appele par `verify.sh`, appelable DEPUIS UN
# HOOK GIT — et git exporte GIT_DIR a ses hooks. Mesure sur le banc du plan :
# sans la purge, la matrice commitait et posait des worktrees DANS LE DEPOT
# HOTE. La purge est PAR PREFIXE (tout GIT_* sauf GIT_CONFIG_GLOBAL,
# GIT_CONFIG_SYSTEM, GIT_CONFIG_NOSYSTEM) : une liste de noms se perime. Elle
# precede tout `git`, tout `mktemp` et tout `cd` ; la deplacer plus bas rouvre
# le defaut.
# HOME ET XDG_CONFIG_HOME SONT JETABLES, JUSTE APRES LA PURGE ET AVANT TOUT `git`
# (S-00003664). `GIT_CONFIG_GLOBAL=/dev/null` ecarte la config globale, PAS les
# fichiers que git derive de ces deux variables (`git/ignore` et
# `git/attributes` par defaut) : ceux de l hote entraient dans chaque bras. Ils
# pointent sous le `TMP` de la suite, cree pour cela des la purge. BORNE : un
# outillage dont l interpreteur se resout par HOME (shim pyenv sans
# `PYENV_ROOT`) casse la detection de python de la suite ET le `python3` du
# scanner — un echec BRUYANT (exit 1 ou erreur du scanner), jamais un faux vert.
#
# LE CAS (f) EST LA RAISON D ETRE DE CETTE SUITE. Le depot porte 250 mentions de
# `T-NNNNNNNN` dans 141 fichiers et l immense majorite sont des references
# HISTORIQUES legitimes. Une garde qui les toucherait serait desarmee dans la
# semaine. Les sept fixtures de (f) sont toutes COPIEES DU DEPOT REEL, pas
# inventees — c est ce qui rend leur silence significatif.
#
# LE CAS (g) EN DEUX GRAPHIES vient d une faille MESUREE par cette suite : la
# premiere redaction du scanner n acceptait que la forme accentuee, et trois des
# neuf formes s echappaient en graphie ASCII (« jusqu a » sans apostrophe). Ce
# depot ecrit dans les DEUX styles ; les deux sont donc exercees.
# =============================================================================
for _v in $(compgen -e); do
  case "$_v" in
    GIT_CONFIG_GLOBAL|GIT_CONFIG_SYSTEM|GIT_CONFIG_NOSYSTEM) ;;
    GIT_*) unset "$_v" ;;
  esac
done
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/_home" XDG_CONFIG_HOME="$TMP/_xdg"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" || exit 1
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

SCAN="$ROOT/core-scripts/check-stale-justification.sh"

PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "no python interpreter on PATH" >&2
  exit 1
fi

pass=0
fail=0
note() { echo "  $*"; }
ok()   { echo "--- PASS $1"; pass=$((pass + 1)); }
ko()   { echo "--- FAIL $1"; fail=$((fail + 1)); }

# --- IDENTIFIANTS ASSEMBLES A L EXECUTION ------------------------------------
# `mk_tid 2` rend l identifiant de la deuxieme tache du board truque. Le prefixe
# et les huit chiffres ne se rencontrent JAMAIS dans le texte de ce fichier.
mk_tid() { printf 'T-%08d' "$1"; }
TID_OUVERTE="$(mk_tid 1)"
TID_CLOSE="$(mk_tid 2)"
TID_BLOQUEE="$(mk_tid 3)"
TID_FANTOME="$(mk_tid 99999)"

OUT=""
RC=0
run_scan() {
  OUT="$("$@" 2>&1)"
  RC=$?
}

expect_rc() {
  if [ "$RC" -eq "$1" ]; then ok "$2 (rc=$RC)"; else
    ko "$2 — attendu rc=$1, obtenu rc=$RC"
    echo "$OUT" | sed 's/^/      | /'
  fi
}

expect_out() {
  if printf '%s' "$OUT" | grep -qF -- "$1"; then ok "$2"; else
    ko "$2 — motif « $1 » absent de la sortie"
    echo "$OUT" | sed 's/^/      | /'
  fi
}

expect_not_out() {
  if printf '%s' "$OUT" | grep -qF -- "$1"; then
    ko "$2 — motif « $1 » PRESENT alors qu il ne devait pas l etre"
    echo "$OUT" | sed 's/^/      | /'
  else ok "$2"; fi
}

# -----------------------------------------------------------------------------
# FABRIQUE D ARBRES TRUQUES
# -----------------------------------------------------------------------------
# La tache 1 est OUVERTE, la 2 est CLOSE, la 3 est BLOQUEE. Toute fixture hostile
# conditionne sur la 2, toute fixture verte sur la 1 ou la 3 : le rouge est donc
# toujours attribuable a l ETAT de la tache, jamais a la forme employee.
mk_tree() {
  local d="$1"
  mkdir -p "$d/.agents/state/board" "$d/src"
  cat > "$d/.agents/state/board/TASKS.json" <<JSON
{"tasks": [
  {"id": "$TID_OUVERTE", "state": "pending", "task": "encore ouverte"},
  {"id": "$TID_CLOSE", "state": "done", "task": "close"},
  {"id": "$TID_BLOQUEE", "state": "blocked", "task": "bloquee"}
]}
JSON
}

# Ecrit un commentaire TypeScript dans un fichier neuf.
mk_src() { printf '// %s\nexport const x = 1;\n' "$2" > "$1/src/exemple.ts"; }

echo "=== (a) arbre propre -> VERT"
A="$TMP/a"; mk_tree "$A"; mk_src "$A" "un commentaire qui ne conditionne rien du tout"
run_scan bash "$SCAN" --root "$A"
expect_rc 0 "un arbre sans forme conditionnelle sort vert"
expect_out "0 forme(s) conditionnelle(s)" "le compte des formes est restitue"

echo
echo "=== (b) forme conditionnelle sur tache CLOSE -> E1"
B="$TMP/b"; mk_tree "$B"; mk_src "$B" "cette page reste hors coquille jusqu'a $TID_CLOSE"
run_scan bash "$SCAN" --root "$B"
expect_rc 1 "une echeance sur une tache close fait rougir"
expect_out "[E1]" "la violation est nommee E1"
expect_out "$TID_CLOSE" "la tache expiree est designee"
expect_out "src/exemple.ts:1" "le site est designe par fichier et par ligne"

echo
echo "=== (c) alias de version V1-NN (T-CLOSE) -> E1"
note "forme REELLE du depot (docker-compose.yml) : la tache est atteinte via un"
note "alias de lot. L ignorer aurait manque le seul vrai positif du depot."
C="$TMP/c"; mk_tree "$C"; mk_src "$C" "LOCALE FIGEE, REPORTEE a V1-20 ($TID_CLOSE). Le levier est ailleurs."
run_scan bash "$SCAN" --root "$C"
expect_rc 1 "l alias de version ne masque pas la tache"
expect_out "[E1]" "la violation est nommee E1"

echo
echo "=== (d) tache ABSENTE du board -> E2"
D="$TMP/d"; mk_tree "$D"; mk_src "$D" "en attendant $TID_FANTOME rien ne bouge"
run_scan bash "$SCAN" --root "$D"
expect_rc 1 "une condition sur une tache inexistante fait rougir"
expect_out "[E2]" "la violation est nommee E2"

echo
echo "=== (e) forme conditionnelle sur tache OUVERTE -> VERT"
E="$TMP/e"; mk_tree "$E"; mk_src "$E" "cette page reste hors coquille jusqu'a $TID_OUVERTE"
run_scan bash "$SCAN" --root "$E"
expect_rc 0 "une echeance encore portee ne fait pas rougir"
expect_out "1 forme(s) conditionnelle(s)" "elle est comptee sans etre sanctionnee"

echo
echo "=== (e2) tache BLOQUEE -> VERT (bloquee n est pas close)"
E2="$TMP/e2"; mk_tree "$E2"; mk_src "$E2" "tant que $TID_BLOQUEE n est pas tranchee, on ne bouge pas"
run_scan bash "$SCAN" --root "$E2"
expect_rc 0 "une tache bloquee porte encore la condition"

echo
echo "=== (f) LES SEPT QUASI-CORRESPONDANCES — toutes sur une tache CLOSE, toutes SILENCIEUSES"
note "chacune est copiee du depot reel. Si l une d elles declenchait, la garde"
note "rougirait sur des textes corrects et serait desarmee dans la semaine."
F="$TMP/f"; mk_tree "$F"
{
  printf '// 1. reference historique explicite : corrige par %s, rien a rouvrir.\n' "$TID_CLOSE"
  printf '// 2. anteriorite : Avant %s, l appel ci-dessous levait une erreur.\n' "$TID_CLOSE"
  printf '// 3. posteriorite : apres %s, la base compte ZERO detenteur.\n' "$TID_CLOSE"
  printf '// 4. renvoi de suivi : privileges par defaut (suivi %s).\n' "$TID_CLOSE"
  printf '// 5. attribution : forme validee AVANT la base (gate de securite %s).\n' "$TID_CLOSE"
  printf '// 6. la preposition gouverne AUTRE CHOSE : reporte jusqu a la gravite d App Insights (%s).\n' "$TID_CLOSE"
  printf '// 7. quantite, pas echeance : ce chemin EN ENVOIE JUSQU A VINGT-CINQ (%s, revue).\n' "$TID_CLOSE"
  printf 'export const y = 2;\n'
} > "$F/src/references.ts"
run_scan bash "$SCAN" --root "$F"
expect_rc 0 "aucune des sept references historiques ne declenche"
expect_out "0 forme(s) conditionnelle(s)" "elles ne sont meme pas comptees comme conditionnelles"
expect_not_out "[E1]" "aucune violation E1"
expect_not_out "[E2]" "aucune violation E2"

echo
echo "=== (f2) le meme fichier PLUS une vraie echeance : le bruit ne masque pas le signal"
printf '// 8. ET CELLE-CI EST UNE VRAIE ECHEANCE : on garde ce repli jusqu a %s.\n' "$TID_CLOSE" \
  >> "$F/src/references.ts"
run_scan bash "$SCAN" --root "$F"
expect_rc 1 "la huitieme ligne, elle, fait rougir"
expect_out "1 forme(s) conditionnelle(s)" "une seule des huit lignes est conditionnelle"
expect_out "[E1]" "et elle est sanctionnee"

echo
echo "=== (g) les NEUF formes retenues declenchent, EN GRAPHIE ACCENTUEE ET EN ASCII"
note "la graphie ASCII est une faille MESUREE : trois formes s en echappaient."
FORMES_ACCENTUEES=(
  "on garde ce repli jusqu'à %s"
  "on garde ce repli en attendant %s"
  "on garde ce repli dans l'attente de %s"
  "on garde ce repli tant que %s n a pas atterri"
  "on garde ce repli d'ici %s"
  "on garde ce repli le temps de %s"
  "chose reportée à %s"
  "chose différée à %s"
  "chose remise à %s"
)
FORMES_ASCII=(
  "on garde ce repli jusqu a %s"
  "on garde ce repli en attendant %s"
  "on garde ce repli dans l attente de %s"
  "on garde ce repli tant que %s n a pas atterri"
  "on garde ce repli d ici %s"
  "on garde ce repli le temps de %s"
  "chose reportee a %s"
  "chose differee a %s"
  "chose remise a %s"
)
n=0
for gabarit in "${FORMES_ACCENTUEES[@]}" "${FORMES_ASCII[@]}"; do
  n=$((n + 1))
  G="$TMP/g$n"; mk_tree "$G"
  # shellcheck disable=SC2059
  texte="$(printf "$gabarit" "$TID_CLOSE")"
  mk_src "$G" "$texte"
  run_scan bash "$SCAN" --root "$G"
  if [ "$RC" -eq 1 ]; then ok "forme reconnue : $texte"; else
    ko "forme NON reconnue : $texte"
    echo "$OUT" | sed 's/^/      | /'
  fi
done

echo
echo "=== (g2) GRAMMAIRE D ID MIXTE (T-00001040) : une condition sur un T-<ULID> est lue ENTIERE"
note "Corps ULID ASSEMBLES a l execution (meme discipline que mk_tid) : le prefixe et le"
note "corps ne se rencontrent jamais dans ce fichier. UC finit par une lettre (CLOSE) ; U8"
note "ouvre par DIX chiffres (OUVERTE) — un motif qui lirait l ancien d abord la couperait."
note "MUTANTS : M26 (\`(?-i:…)\` retire) => (g2-c) rouge ; branche ULID retiree => (g2-a)"
note "rouge ; ULID en second (M3) => (g2-b) rouge ; borne (?![0-9A-Za-z]) retiree => (g2-d) rouge."
mk_ulid() { printf 'T-%s' "$1"; }
UC_CORPS="01M3250V003HCPQKTZ8ENYF4VM"; U8_CORPS="0123456789ABCDEFGHJKMNPQRS"
TID_ULID_CLOSE="$(mk_ulid "$UC_CORPS")"
TID_ULID_OUVERTE="$(mk_ulid "$U8_CORPS")"
mk_tree_ulid() {
  mk_tree "$1"
  cat > "$1/.agents/state/board/TASKS.json" <<JSON
{"tasks": [
  {"id": "$TID_OUVERTE", "state": "pending", "task": "encore ouverte"},
  {"id": "$TID_CLOSE", "state": "done", "task": "close"},
  {"id": "$TID_ULID_CLOSE", "state": "done", "task": "ulid close"},
  {"id": "$TID_ULID_OUVERTE", "state": "pending", "task": "ulid ouverte"}
]}
JSON
}
G2="$TMP/g2a"; mk_tree_ulid "$G2"; mk_src "$G2" "on garde ce repli jusqu a $TID_ULID_CLOSE"
run_scan bash "$SCAN" --root "$G2"
expect_rc 1 "(g2-a) une echeance sur un T-<ULID> CLOS fait rougir"
expect_out "[E1]" "(g2-a) la violation est nommee E1"
expect_out "$TID_ULID_CLOSE, CLOSE" "(g2-a) l id ULID est designe ENTIER"
G2="$TMP/g2b"; mk_tree_ulid "$G2"; mk_src "$G2" "on garde ce repli jusqu a $TID_ULID_OUVERTE"
run_scan bash "$SCAN" --root "$G2"
expect_rc 0 "(g2-b) une echeance sur un T-<ULID> OUVERT (dix chiffres en tete) ne rougit pas"
expect_out "1 forme(s) conditionnelle(s)" "(g2-b) elle est comptee, entiere"
G2="$TMP/g2c"; mk_tree_ulid "$G2"
mk_src "$G2" "on garde ce repli jusqu a $(mk_ulid "$(printf '%s' "$UC_CORPS" | tr 'A-Z' 'a-z')")"
run_scan bash "$SCAN" --root "$G2"
expect_rc 0 "(g2-c) un corps ULID en MINUSCULES n est pas un id (la casse ignoree ne s y etend pas)"
expect_out "0 forme(s) conditionnelle(s)" "(g2-c) aucune forme comptee"
G2="$TMP/g2d"; mk_tree_ulid "$G2"; mk_src "$G2" "on garde ce repli jusqu a $(mk_ulid "0$UC_CORPS")"
run_scan bash "$SCAN" --root "$G2"
expect_rc 0 "(g2-d) T-0<ULID> (27 symboles) n est pas un id"
expect_out "0 forme(s) conditionnelle(s)" "(g2-d) aucune forme comptee"

echo
echo "=== (h) perimetre RE-DERIVE pour ce depot (T-00000379)"
note "CE BRAS AFFIRMAIT L INVERSE, et c est le point de la reprise. Il exigeait"
note "que .md soit ignore et .agents/ elague — le contrat de l arbre TS/Next"
note "d origine. Mesure ici : ces constantes balayaient 9 fichiers sur 226 et"
note "laissaient la garde VERTE POUR TOUJOURS, .py absent de EXTS et .agents/"
note ".claude/ .codex/ .gemini/ elagues alors qu ils portent 181 fichiers de code."
note "Le contrat neuf : .md EST balaye (la doctrine est une surface qui VOYAGE,"
note "une justification perimee y atteint chaque adoptant), sauf docs/tasks/ et"
note "les vues generees qui CITENT des taches par nature ; et seul .agents/state/"
note "est elague, pas .agents/ entier."
H="$TMP/h"; mk_tree "$H"; mk_src "$H" "commentaire sain"
mkdir -p "$H/docs/tasks" "$H/.agents/bin"
# 1. la prose de doctrine EST balayee -> rouge
printf 'On garde ce repli jusqu a %s.\n' "$TID_CLOSE" > "$H/NOTES.md"
run_scan bash "$SCAN" --root "$H"
expect_rc 1 "la prose .md de doctrine EST balayee (elle voyage chez l adoptant)"
expect_out "NOTES.md" "et le fichier est nomme"
rm -f "$H/NOTES.md"
# 2. docs/tasks/ est ECARTE — un plan cite des taches par nature
printf 'gele jusqu a %s\n' "$TID_CLOSE" > "$H/docs/tasks/T-00000001-plan.md"
run_scan bash "$SCAN" --root "$H"
expect_rc 0 "docs/tasks/ reste ecarte : un plan CITE des taches, il n en porte pas"
rm -f "$H/docs/tasks/T-00000001-plan.md"
# 3. .agents/state/ reste elague — les stores citent au lieu de porter
printf 'note: gele jusqu a %s\n' "$TID_CLOSE" > "$H/.agents/state/board/annexe.yml"
run_scan bash "$SCAN" --root "$H"
expect_rc 0 "les STORES restent elagues : la garde ne rougit pas sur sa propre memoire"
# 4. MAIS .agents/bin/ ne l est PLUS — c est la ou vit le code du kit
printf '# fige jusqu a %s\n' "$TID_CLOSE" > "$H/.agents/bin/outil.py"
run_scan bash "$SCAN" --root "$H"
expect_rc 1 ".agents/bin/ N EST PLUS elague : 134 fichiers de code y vivent"
expect_out ".agents/bin/outil.py" "et le .py y est vu — il etait hors EXTS a l origine"

echo
echo "=== (i) une ligne fautive NON-ASCII s imprime — REGRESSION MESUREE"
note "la premiere execution reelle du scanner a leve UnicodeEncodeError sur la fleche"
note "d un commentaire de docker-compose.yml : sortie cp1252 sur poste Windows. La"
note "garde plantait au moment precis ou elle avait quelque chose a dire."
I="$TMP/i"; mk_tree "$I"
printf '#   * LOCALE / COLLATION FIG\xc3\x89E \xe2\x86\x92 REPORT\xc3\x89E \xc3\xa0 V1-20 (%s). Le levier\n' \
  "$TID_CLOSE" > "$I/src/compose.yml"
run_scan bash "$SCAN" --root "$I"
expect_rc 1 "la ligne non-ASCII fait rougir"
expect_out "[E1]" "et le constat s imprime au lieu de planter"
expect_not_out "UnicodeEncodeError" "aucune trace d encodage"
expect_not_out "Traceback" "aucune trace d exception"

echo
echo "=== (j) LA GARDE TOURNE SUR LE DEPOT REEL — motif MAISON, pas CI_STEPS"
note "CE BRAS EXIGEAIT UNE ENTREE DANS UNE LISTE CI_STEPS. C est le cablage de"
note "l auteur d origine ; le NOTRE est meilleur et il existe deja : la suite d une"
note "garde l INVOQUE sur le vrai depot (voir check-workflow-pins.test.sh:116),"
note "run-bash-tests.sh decouvre toute *.test.sh, et verify.sh lance run-bash-tests."
note "La garde tourne donc dans la porte SANS AUCUNE ENUMERATION A PERIMER."
note ""
note "Et ce bras est AUSSI le temoin de non-vacuite : il prouve que le balayage"
note "elargi tourne sur l arbre reel, pas seulement sur des fixtures."
note ""
note "CE BRAS EXIGEAIT rc 0 SUR « LE DEPOT REEL » — vrai ICI, FAUX sur un checkout"
note "d adoptant frais. Mesure du 2026-09-03 sur la branche template : 30 passed /"
note "1 failed, et l unique rouge etait celui-ci. Cause : .agents/state/ est strip:,"
note "donc un adoptant recoit l arbre SANS board, la garde sort 1 avec [E0], et ce"
note "bras — qui VOYAGE — reclamait 0. Meme classe que le banc de la vitrine qui"
note "partait sans son sujet : une suite qui voyage et qui SUPPOSE un etat qui ne"
note "voyage pas rend la porte de chaque adoptant rouge des le premier jour."
note ""
note "LE BRAS FAIT DONC CE QU UN ADOPTANT FAIT : il provisionne d abord. C est la"
note "premiere commande du guide d installation, et elle est idempotente — sur CE"
note "depot le board existe deja, donc l appel ne change rien et le bras mesure"
note "exactement ce qu il mesurait avant. La garde, elle, n est PAS relachee :"
note "board absent reste ROUGE, decision inchangee, epinglee plus bas."
python3 "$ROOT/.agents/bin/project_init.py" --ensure-stores >/dev/null 2>&1 || true
run_scan bash "$SCAN" --root "$ROOT"
expect_rc 0 "depot reel (board provisionne) : aucune justification perimee"
expect_out "fichier(s) balaye(s)" "le relevé dit COMBIEN il a lu"
real_n="$(printf '%s' "$OUT" | sed -n 's/.*: \([0-9]*\) fichier(s) balaye(s).*/\1/p' | head -1)"

# LE JUGE DU BALAYAGE, EN FONCTION — ET POURQUOI CE N EST PAS UN DETAIL DE STYLE.
# Ce plancher INVOQUAIT `pass` et `fail` COMME DES COMMANDES, en `… && … || …`.
# Or ce sont les COMPTEURS ENTIERS declares plus haut, jamais des verbes : les
# seuls juges de cette suite sont `ok` et `ko`. Les deux bras sortaient en rc 127 —
# « pass: commande introuvable » sur stderr, avale par le `||` — et `set -uo
# pipefail` SANS `-e` ne fait rien d un 127. Aucun compteur ne bougeait : le bras
# ne pouvait NI passer NI echouer, et la suite concluait 54/0 en n ayant jamais
# mesure ce qu elle annonce mesurer. Un plancher qui ne peut pas rougir est vert
# par VACUITE — exactement le defaut que ce bras-ci pretend interdire aux autres.
# La forme FONCTION sert deux fois : sur la mesure reelle, puis sur un temoin.
juge_couverture() {
  local n="${1:-}"
  if [ -n "$n" ] && [ "$n" -gt 200 ]; then
    ok "le balayage reel couvre $n fichiers (>200 : les constantes d origine en donnaient 9)"
  else
    ko "balayage reel a $n fichiers — les constantes n ont pas ete re-derivees, la garde est verte par VACUITE"
  fi
}
juge_couverture "$real_n"

note ""
note "(j-temoin) UN PLANCHER SE PROUVE, IL NE SE DECLARE PAS. On rejoue le meme"
note "juge sur 9 — la valeur exacte que rendaient les constantes d origine — et on"
note "exige qu il ROUGISSE. Le sous-shell de la substitution isole les compteurs du"
note "parent : ce rouge-la est CAPTURE dans une variable, jamais compte. La preuve"
note "reste donc dans l arbre, au lieu de vivre dans une mutation manuelle que le"
note "prochain lecteur devra refaire pour se convaincre."
temoin="$(juge_couverture 9)"
case "$temoin" in
  *"--- FAIL"*) ok "(j) témoin : le juge rougit sur 9 fichiers" ;;
  *) ko "(j) témoin : le juge N A PAS rougi sur 9 fichiers — il ne juge rien : « $temoin »" ;;
esac


echo
echo "=== (k) aucun chemin ne rend 4 (un 4 serait lu SAUTÉ par ci-steps.sh = faux vert)"
K="$TMP/k"; mk_tree "$K"; mk_src "$K" "sain"
rm -f "$K/.agents/state/board/TASKS.json"
run_scan bash "$SCAN" --root "$K"
expect_rc 1 "board absent = ROUGE, jamais SAUTÉ"
expect_out "[E0]" "la cause est nommee"

K2="$TMP/k2"; mk_tree "$K2"; mk_src "$K2" "sain"
printf 'ceci n est pas du JSON\n' > "$K2/.agents/state/board/TASKS.json"
run_scan bash "$SCAN" --root "$K2"
expect_rc 1 "board illisible = ROUGE, jamais SAUTÉ"

echo
echo "=== (l) le board n est JAMAIS ecrit"
note "tasks.py est le seul ecrivain du board ; une garde qui le toucherait"
note "corromprait la source de verite qu elle interroge."
L="$TMP/l"; mk_tree "$L"; mk_src "$L" "on garde ce repli jusqu a $TID_CLOSE"
EMPREINTE='import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())'
AVANT="$("$PY" -c "$EMPREINTE" "$L/.agents/state/board/TASKS.json")"
run_scan bash "$SCAN" --root "$L"
APRES="$("$PY" -c "$EMPREINTE" "$L/.agents/state/board/TASKS.json")"
if [ "$AVANT" = "$APRES" ]; then ok "le board est bit pour bit identique apres un run ROUGE"; else ko "le board a ete MODIFIE par la garde"; fi

echo
echo "=== (m) CHECKOUTS IMBRIQUES — NON ENREGISTRE : elague ; ENREGISTRE : balaye (T-00001073)"
note "un worktree lie ou un clone pose dans l arbre n est pas ce depot : le balayer"
note "doublait le compte et lisait des textes etrangers. Mais un chemin ENREGISTRE"
note "(sous-module, fichier suivi sous un .git) doit rester lu, sinon la garde"
note "devient verte sur du contenu cache. Un VRAI arbre git par bras, une"
note "justification perimee dans chaque candidat : elague -> rc 0 et la ligne"
note "nomme le chemin ; balaye -> rc 1 et aucune ligne d elagage."
note "Regles de construction : identite LOCALE par depot (jamais GIT_AUTHOR_*),"
note "-c protocol.file.allow=always sur les sous-modules, gitfile relatif de W8"
note "ECRIT, fichiers SUIVIS de W7/W12 commites AVANT le gitfile ou le git init,"
note "options git >= 2.40 seulement, ni tableau associatif ni mapfile (bash 3.2)."
REALGIT="$(command -v git || true)"
GITBASH=0
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) GITBASH=1 ;;
esac
if [ -z "$REALGIT" ]; then
  ko "(m) git absent du PATH : cette suite exige git (la porte l exige deja)"
else
M="$TMP/m"
mkdir -p "$M"
mkrepo() { "$REALGIT" init -q -b main "$1" && "$REALGIT" -C "$1" config user.email t@t && "$REALGIT" -C "$1" config user.name t; }
G() { "$REALGIT" -c protocol.file.allow=always "$@"; }
stale_in() { mkdir -p "$1"; printf '// gele jusqu a %s\nexport const x = 1;\n' "$TID_CLOSE" > "$1/a.ts"; }
gitroot() { mk_tree "$1"; mkrepo "$1"; G -C "$1" add -A; G -C "$1" commit -q -m r0; }
mode_of() { G -C "$1" ls-files -s -- "$2" | cut -c1-6; }
gitmod() { mk_tree "$1"; stale_in "$1/vendor/emb"; mkdir -p "$1/vendor/emb/.git"; printf '%s' "$2" > "$1/.gitmodules"; }

# RC8 — les bras « racine non git » supposent un TMP HORS de tout depot : sous un
# depot ancetre, c est l index de l ancetre qui fait foi (borne nommee), et
# NGborne y serait juge pour une autre raison. Constate, jamais suppose.
HORS_OUT="$(cd "$M" && LC_ALL=C LANGUAGE='' "$REALGIT" rev-parse --is-inside-work-tree 2>&1)"
HORS_RC=$?
TMP_HORS=0
if [ "$HORS_RC" -eq 128 ]; then
  case "$HORS_OUT" in
    *"not a git repository (or any"*) TMP_HORS=1 ;;
  esac
fi

mkrepo "$M/_src1"; stale_in "$M/_src1/x"; printf 'ok\n' > "$M/_src1/README"
G -C "$M/_src1" add -A; G -C "$M/_src1" commit -q -m s1
SRC1="$M/_src1"
mkrepo "$M/_src2"; printf 'ok\n' > "$M/_src2/README"; G -C "$M/_src2" add -A; G -C "$M/_src2" commit -q -m s2
SRC2="$M/_src2"

mkarm() {
  local a="$1" T="$M/$1"
  case "$a" in
    W1) gitroot "$T"; G -C "$T" worktree add -q --detach .claude/worktrees/w1 HEAD; stale_in "$T/.claude/worktrees/w1/x" ;;
    W8) gitroot "$T"; G -C "$T" worktree add -q --detach .claude/worktrees/w8 HEAD
        printf 'gitdir: ../../../.git/worktrees/w8\n' > "$T/.claude/worktrees/w8/.git"; stale_in "$T/.claude/worktrees/w8/x"
        if [ "$(G -C "$T/.claude/worktrees/w8" rev-parse --show-toplevel)" != "$(cd "$T/.claude/worktrees/w8" && pwd -P)" ]; then
          ko "(m) PRECONDITION W8 : le gitfile relatif ecrit ne designe pas le worktree"
        fi ;;
    W8r) gitroot "$T"; G -C "$T" worktree add -q --relative-paths --detach .claude/worktrees/w8r HEAD; stale_in "$T/.claude/worktrees/w8r/x" ;;
    W9) gitroot "$T"; stale_in "$T/.claude/w9"; printf 'gitdir: %s/.git/worktrees/gone\n' "$T" > "$T/.claude/w9/.git" ;;
    W2) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/w2"; stale_in "$T/vendor/w2/x" ;;
    W10) gitroot "$T"; G clone -q "$SRC1" "$M/_w10real"; stale_in "$T/vendor/w10"; ln -s "$M/_w10real/.git" "$T/vendor/w10/.git" ;;
    W10b) gitroot "$T"; stale_in "$T/vendor/w10b"; ln -s "$M/_nope/.git" "$T/vendor/w10b/.git" ;;
    W11) mkrepo "$T"; mk_tree "$T"; mkdir -p "$T/vendor"; printf 'suivi\n' > "$T/vendor/README"
         G -C "$T" add -A; G -C "$T" commit -q -m r0; G clone -q "$SRC1" "$T/vendor/w11"; stale_in "$T/vendor/w11/x" ;;
    LIT) gitroot "$T"; G -C "$T" submodule add -q "$SRC2" vendor/y; G -C "$T" commit -q -m s
         G clone -q "$SRC1" "$T/vendor/[y]"; stale_in "$T/vendor/[y]/x" ;;
    DEREG) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/d"; G -C "$T" submodule add -q "$SRC1" vendor/d >/dev/null 2>&1
           G -C "$T" commit -q -m s; G -C "$T" rm -q --cached -f vendor/d
           G -C "$T" config -f .gitmodules --remove-section submodule.vendor/d; G -C "$T" add .gitmodules
           G -C "$T" commit -q -m d; stale_in "$T/vendor/d/x" ;;
    W5e) gitroot "$T"; stale_in "$T/vendor/w5e"; mkdir -p "$T/vendor/w5e/.git" ;;
    W3) gitroot "$T"; G -C "$T" submodule add -q "$SRC1" vendor/w3; G -C "$T" commit -q -m s; stale_in "$T/vendor/w3/x" ;;
    W3b) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/w3b"; G -C "$T" submodule add -q "$SRC1" vendor/w3b >/dev/null 2>&1
         G -C "$T" commit -q -m s; stale_in "$T/vendor/w3b/x" ;;
    W3g) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/w3g"; G -C "$T" add vendor/w3g 2>/dev/null; G -C "$T" commit -q -m s
         rm -f "$T/vendor/w3g/.git/HEAD" ;;
    W3c) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/w3c"; G -C "$T" add vendor/w3c 2>/dev/null; G -C "$T" commit -q -m s
         stale_in "$T/vendor/w3c/x" ;;
    R) gitroot "$T"; G -C "$T" submodule add -q "$SRC1" docs/worktrees/foo; G -C "$T" commit -q -m s
       stale_in "$T/docs/worktrees/foo/x" ;;
    W3d) gitroot "$T"; G -C "$T" submodule add -q "$SRC2" vendor/w3; G -C "$T" commit -q -m s
         G clone -q "$SRC1" "$T/vendor/w3/inner"; G -C "$T/vendor/w3" submodule add -q "$SRC1" inner >/dev/null 2>&1
         stale_in "$T/vendor/w3/inner/x" ;;
    W3gd) gitroot "$T"; G -C "$T" submodule add -q "$SRC2" vendor/w3; G -C "$T" commit -q -m s
          G clone -q "$SRC1" "$T/vendor/w3/inner"; G -C "$T/vendor/w3" submodule add -q "$SRC1" inner >/dev/null 2>&1
          rm -f "$T/vendor/w3/inner/.git/HEAD" ;;
    W4) gitroot "$T"; stale_in "$T/.claude/skills/w4"
        printf 'gitdir: ../../../../../../.git/worktrees/agent-x/modules/.claude/skills/w4\n' > "$T/.claude/skills/w4/.git" ;;
    W5) gitroot "$T"; stale_in "$T/vendor/w5"; : > "$T/vendor/w5/.git" ;;
    W5b) gitroot "$T"; stale_in "$T/vendor/w5b"; printf 'gitdir: /nonexistent\n' > "$T/vendor/w5b/.git" ;;
    W6) gitroot "$T"; stale_in "$T/src" ;;
    W7) gitroot "$T"; stale_in "$T/vendor/w7"; G -C "$T" add -A; G -C "$T" commit -q -m t
        printf 'gitdir: %s/.git/worktrees/agent-x\n' "$T" > "$T/vendor/w7/.git"
        if [ "$(mode_of "$T" vendor/w7/a.ts)" != "100644" ]; then ko "(m) PRECONDITION W7 : vendor/w7/a.ts n est pas un fichier SUIVI"; fi ;;
    W12) gitroot "$T"; stale_in "$T/src/inl"; G -C "$T" add -A; G -C "$T" commit -q -m t; mkrepo "$T/src/inl"
         if [ "$(mode_of "$T" src/inl/a.ts)" != "100644" ]; then ko "(m) PRECONDITION W12 : src/inl/a.ts n est pas un fichier SUIVI"; fi ;;
    IDX) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/idx"; stale_in "$T/vendor/idx/x"; printf 'garbage' > "$T/.git/index" ;;
    W5c) gitroot "$T"; mkdir -p "$T/vendor/w5"; : > "$T/vendor/w5/.git"; G clone -q "$SRC1" "$T/vendor/w5/c"; stale_in "$T/vendor/w5/c/x" ;;
    W5d) gitroot "$T"; mkdir -p "$T/vendor/w5b"; printf 'gitdir: /nonexistent\n' > "$T/vendor/w5b/.git"
         G clone -q "$SRC1" "$T/vendor/w5b/c"; stale_in "$T/vendor/w5b/c/x" ;;
    DEREG2) gitroot "$T"; G clone -q "$SRC1" "$T/vendor/d"; G -C "$T" submodule add -q "$SRC1" vendor/d >/dev/null 2>&1
            G -C "$T" commit -q -m s; G -C "$T" rm -q --cached -f vendor/d; G -C "$T" commit -q -m d; stale_in "$T/vendor/d/x" ;;
    RACBOGUS) mk_tree "$T"; printf 'gitdir: /nonexistent\n' > "$T/.git"; stale_in "$T/vendor/emb"; mkdir -p "$T/vendor/emb/.git" ;;
    NGmod) gitmod "$T" "$(printf '[submodule "e"]\n\tpath = vendor/emb\n\turl = x\n')" ;;
    NGquote) gitmod "$T" "$(printf '[submodule "e"]\n\tpath = "vendor/emb"\n\turl = x\n')" ;;
    NGsp) gitmod "$T" "$(printf '[submodule "e"]\n  path=vendor/emb   \n')" ;;
    NGborne) mk_tree "$T"; stale_in "$T/vendor/emb"; mkdir -p "$T/vendor/emb/.git" ;;
    CLEAN) mk_tree "$T"; printf '// encore porte jusqu a %s\n' "$TID_OUVERTE" > "$T/src/a.ts" ;;
  esac
}

# Le chemin que la ligne d elagage doit nommer, pour les bras elagues.
chemin_elague() {
  case "$1" in
    W1) echo ".claude/worktrees/w1" ;;
    W8) echo ".claude/worktrees/w8" ;;
    W8r) echo ".claude/worktrees/w8r" ;;
    W9) echo ".claude/w9" ;;
    W2) echo "vendor/w2" ;;
    W10) echo "vendor/w10" ;;
    W11) echo "vendor/w11" ;;
    LIT) echo "vendor/[y]" ;;
    DEREG) echo "vendor/d" ;;
    W5e) echo "vendor/w5e" ;;
    NGborne) echo "vendor/emb" ;;
  esac
}

# P = elague (rc 0, ligne, chemin nomme) ; S = balaye (rc 1, aucune ligne) ;
# H = racine hors depot (elague + note) ; C = arbre sans checkout (sortie d avant).
juge_bras() {
  local a="$1" attendu="$2" p
  p="$(chemin_elague "$a")"
  case "$attendu" in
    P)
      expect_rc 0 "(m) $a ELAGUE : la justification qu il porte n est pas lue"
      expect_out "checkout(s) imbrique(s) elague(s)" "(m) $a : la ligne d elagage est imprimee"
      expect_out "$p" "(m) $a : la ligne nomme $p"
      expect_not_out "hors depot" "(m) $a : racine git, aucune note hors depot"
      ;;
    H)
      expect_rc 0 "(m) $a ELAGUE hors depot"
      expect_out "$p" "(m) $a : la ligne nomme $p"
      expect_out "hors depot : .gitmodules seul" "(m) $a : la note dit sur quoi la garde s est appuyee"
      ;;
    S)
      expect_rc 1 "(m) $a BALAYE : sa justification perimee est lue"
      expect_not_out "checkout(s) imbrique(s)" "(m) $a : aucune ligne d elagage"
      ;;
  esac
}

ARMS_P="W1 W8 W9 W2 W10 W11 LIT DEREG W5e"
ARMS_S="W3 W3b W3g W3c R W3d W3gd W4 W5 W5b W10b W6 W7 W12 IDX W5c W5d NGmod NGquote NGsp DEREG2 RACBOGUS"
note ""
note "elagues : $ARMS_P ; balayes : $ARMS_S ; hors depot : NGborne ; temoin : CLEAN"
note "W5e (DOSSIER .git VIDE sous un dossier non suivi) : ELAGUE, borne nommee —"
note "git le rattache a la racine, mais rien n y est suivi : seul du contenu NON"
note "SUIVI est ecarte. NGmod/NGquote/NGsp/DEREG2 : la ligne path = de .gitmodules"
note "suffit a les BALAYER. RACBOGUS : racine dont le propre .git est bidon ->"
note "git ne sait pas la lire -> tout candidat BALAYE (jamais « hors depot »)."
note "W3gd : depot embarque CORROMPU enregistre dans l index d un SOUS-MODULE (donc"
note "hors du .gitmodules de la racine) — ls-files --recurse-submodules y rend"
note "rc 0 et ZERO ligne : seul l index du parent direct le voit enregistre."
for a in $ARMS_P $ARMS_S; do
  case "$a" in
    W10|W10b)
      if [ "$GITBASH" -eq 1 ]; then echo "SKIP (m) $a : ln -s non mesure sous Git Bash"; continue; fi ;;
  esac
  mkarm "$a"
done
for a in $ARMS_P; do
  case "$a" in
    W10) if [ "$GITBASH" -eq 1 ]; then continue; fi ;;
  esac
  run_scan bash "$SCAN" --root "$M/$a"
  juge_bras "$a" P
done
for a in $ARMS_S; do
  case "$a" in
    W10b) if [ "$GITBASH" -eq 1 ]; then continue; fi ;;
  esac
  run_scan bash "$SCAN" --root "$M/$a"
  juge_bras "$a" S
done

# W8r — le VRAI `--relative-paths` (git >= 2.48). Hors des bras comptes : joue
# seulement si ce git le connait, sinon une note (W8, ECRIT, couvre la forme).
# L aide est CAPTUREE d abord : `worktree add -h` sort en 129, et sous pipefail
# un `| grep -q` rendrait ce 129 — W8r ne serait jamais joue, en silence.
W8R_AIDE="$(G worktree add -h 2>&1)"
W8R_CONNU=0
case "$W8R_AIDE" in
  *relative-paths*) W8R_CONNU=1 ;;
esac
if [ "$W8R_CONNU" -eq 1 ]; then
  mkarm W8r
  run_scan bash "$SCAN" --root "$M/W8r"
  juge_bras W8r P
else
  note "(m) W8r non joue : ce git ne connait pas --relative-paths (W8 ecrit couvre la forme)"
fi

if [ "$TMP_HORS" -eq 1 ]; then
  mkarm NGborne
  run_scan bash "$SCAN" --root "$M/NGborne"
  juge_bras NGborne H
  note "(m) second temoin de locale : NGborne sous LC_ALL=fr_FR.UTF-8 (mord la ou git est traduit)"
  run_scan env LC_ALL=fr_FR.UTF-8 LANGUAGE=fr bash "$SCAN" --root "$M/NGborne"
  juge_bras NGborne H
else
  echo "SKIP (m) NGborne : le TMP de cette suite est SOUS un depot ($M) — racine non git non constructible ici"
fi

mkarm CLEAN
note ""
note "(m) CLEAN — un arbre sans checkout imbrique rend la sortie d AVANT, octet pour"
note "octet : ces trois lignes sont celles du script anterieur a la garde (mesure"
note "par cmp base/corrige dans l annexe du plan)."
run_scan bash "$SCAN" --root "$M/CLEAN"
CLEAN_ATTENDU="$(printf '%s\n%s\n%s' \
  "check-stale-justification: 1 fichier(s) balaye(s), 1 forme(s) conditionnelle(s)" \
  "  1 encore portee(s) par une tache ouverte / 0 perimee(s)" \
  "check-stale-justification: VERT — aucune condition future n a expire.")"
expect_rc 0 "(m) CLEAN : vert"
if [ "$OUT" = "$CLEAN_ATTENDU" ]; then ok "(m) CLEAN : sortie identique a celle d avant la garde"; else
  ko "(m) CLEAN : la sortie a change sur un arbre sans checkout imbrique"
  echo "$OUT" | sed 's/^/      | /'
fi

echo
echo "=== (m) NOGIT — git ABSENT du PATH : .gitmodules seul, et c est DIT"
if [ "$GITBASH" -eq 1 ]; then
  echo "SKIP (m) NOGIT : ln -s non mesure sous Git Bash"
else
  NG="$M/_nogit"; mkdir -p "$NG"
  for t in bash "$PY" dirname; do ln -sf "$(command -v "$t")" "$NG/$(basename "$t")"; done
  run_scan env PATH="$NG" bash "$SCAN" --root "$M/W2"
  expect_rc 0 "(m) NOGIT-W2 : elague sans git"
  expect_out "git absent : .gitmodules seul" "(m) NOGIT-W2 : la note dit que git manquait"
  run_scan env PATH="$NG" bash "$SCAN" --root "$M/W3b"
  expect_rc 1 "(m) NOGIT-W3b : .gitmodules suffit a le BALAYER"
  run_scan env PATH="$NG" bash "$SCAN" --root "$M/W3c"
  expect_rc 0 "(m) NOGIT-W3c : BORNE epinglee — gitlink sans .gitmodules, sans git : elague"
  expect_out "git absent : .gitmodules seul" "(m) NOGIT-W3c : et c est dit"
fi

echo
echo "=== (m) ENV — un environnement git HOSTILE ne fait rien elaguer d ENREGISTRE"
mkrepo "$M/_other"; echo q > "$M/_other/q"; G -C "$M/_other" add q; G -C "$M/_other" commit -q -m o
for h in "GIT_LITERAL_PATHSPECS=1" "GIT_INDEX_FILE=$M/_other/.git/index" "GIT_DIR=$M/_other/.git"; do
  run_scan env "$h" bash "$SCAN" --root "$M/W3c"
  expect_rc 1 "(m) ENV ${h%%=*} : W3c reste BALAYE"
done
note "(m) GIT_CEILING_DIRECTORIES=<racine du bras> : la variable que la purge par liste"
note "laissait passer — un enfant ENREGISTRE y repond « hors depot »."
for a in W3c W7 W12; do
  run_scan env "GIT_CEILING_DIRECTORIES=$M/$a" bash "$SCAN" --root "$M/$a"
  expect_rc 1 "(m) PLAFOND sur $a : reste BALAYE"
  expect_not_out "checkout(s) imbrique(s)" "(m) PLAFOND sur $a : aucune ligne d elagage"
done
run_scan env "GIT_CEILING_DIRECTORIES=$M/W2" bash "$SCAN" --root "$M/W2"
expect_rc 0 "(m) PLAFOND sur W2 : la garde lit l index malgre le plafond, W2 est elague"
expect_not_out "decouverte bloquee" "(m) PLAFOND sur W2 : la garde n a pas herite du plafond"
run_scan env "GIT_CEILING_DIRECTORIES=$M" bash "$SCAN" --root "$M/W2"
expect_rc 0 "(m) controle : plafond AU-DESSUS de la racine, W2 elague comme sans plafond"
run_scan env "GIT_CEILING_DIRECTORIES=$M" bash "$SCAN" --root "$M/W3c"
expect_rc 1 "(m) controle : plafond AU-DESSUS de la racine, W3c balaye comme sans plafond"

echo
echo "=== (m) FSMONITOR — la config du depot interroge n est JAMAIS executee (S-00003664)"
note "un clone embarque issu d une archive non fiable peut porter core.fsmonitor=<cmd>,"
note "que git execute a chaque ls-files -s (mesure git 2.55). La garde passe"
note "-c core.fsmonitor=false -c core.hooksPath=/dev/null. Controle POSITIF d abord :"
note "le MEME ls-files sans ces options doit faire naitre le marqueur, sinon le zero"
note "qui suit ne prouve rien. La config est posee APRES la construction du bras."
if [ "$GITBASH" -eq 1 ]; then
  echo "SKIP (m) FSMONITOR : script fsmonitor sh non mesure sous Git Bash"
else
  FS="$M/FS"; FSM="$M/_fsm.marque"
  gitroot "$FS"; G clone -q "$SRC1" "$FS/vendor/fs"; stale_in "$FS/vendor/fs/x"
  printf '#!/bin/sh\necho "fsmonitor $*" >> "%s"\nexit 1\n' "$FSM" > "$M/_fsm.sh"
  chmod +x "$M/_fsm.sh"
  "$REALGIT" -C "$FS" config core.fsmonitor "$M/_fsm.sh"
  rm -f "$FSM"
  LC_ALL=C LANGUAGE='' "$REALGIT" -C "$FS/vendor" ls-files -s -- ":(literal)fs" >/dev/null 2>&1
  if [ -e "$FSM" ]; then ok "(m) FSMONITOR controle : un ls-files -s NU execute core.fsmonitor"; else
    ko "(m) FSMONITOR controle : le ls-files nu n execute pas core.fsmonitor — le temoin ne mesure rien"; fi
  rm -f "$FSM"
  run_scan bash "$SCAN" --root "$FS"
  expect_rc 0 "(m) FSMONITOR : vendor/fs ELAGUE, la garde a repondu"
  expect_out "vendor/fs" "(m) FSMONITOR : la ligne nomme vendor/fs"
  if [ -e "$FSM" ]; then
    ko "(m) FSMONITOR : la garde a EXECUTE le core.fsmonitor du depot interroge"
    sed 's/^/      | /' "$FSM"
  else ok "(m) FSMONITOR : aucun marqueur apres la garde"; fi
fi

echo
echo "=== (m) SHIM — paresse et locale de chaque appel git (temoin UNIVERSEL)"
if [ "$GITBASH" -eq 1 ]; then
  echo "SKIP (m) SHIM : script sh en tete de PATH non mesure sous Git Bash"
else
  SH="$M/_shim"; mkdir -p "$SH"
  printf '#!/bin/sh\nprintf "%%s|%%s|%%s\\n" "${LC_ALL-}" "${LANGUAGE-}" "$*" >> "$GITLOG"\nexec "%s" "$@"\n' "$REALGIT" > "$SH/git"
  chmod +x "$SH/git"
  for a in CLEAN W6 NGborne W1; do
    if [ "$a" = NGborne ] && [ "$TMP_HORS" -ne 1 ]; then continue; fi
    L="$M/_gitlog.$a"; : > "$L"
    GITLOG="$L" PATH="$SH:$PATH" LC_ALL=fr_FR.UTF-8 LANGUAGE=fr bash "$SCAN" --root "$M/$a" >/dev/null 2>&1
    n_tous="$(grep -c . "$L")"
    n_garde="$(grep -c 'ls-files -s --' "$L")"
    n_locale="$(grep -vc '^C||' "$L")"
    note "(m) SHIM $a : $n_tous appel(s) git dont $n_garde de garde, $n_locale hors locale C"
    if [ "$n_locale" -eq 0 ]; then ok "(m) SHIM $a : chaque appel git voit LC_ALL=C et LANGUAGE vide"; else
      ko "(m) SHIM $a : $n_locale appel(s) git hors locale C — le message lu serait traduit"; fi
    case "$a" in
      CLEAN|W6)
        if [ "$n_tous" -eq 0 ]; then ok "(m) SHIM $a : 0 appel git sans candidat (paresse)"; else
          ko "(m) SHIM $a : $n_tous appel(s) git alors que rien n est candidat"; fi ;;
      NGborne)
        if [ "$n_garde" -eq 0 ]; then ok "(m) SHIM NGborne : hors depot, 0 appel de garde"; else
          ko "(m) SHIM NGborne : $n_garde appel(s) de garde hors depot"; fi ;;
      W1)
        if [ "$n_garde" -ge 1 ]; then ok "(m) SHIM W1 : la garde a bien interroge git"; else
          ko "(m) SHIM W1 : aucun appel de garde — le temoin ne mesure rien"; fi ;;
    esac
  done
  note "(m) un enfant qui repond « hors depot » DANS un depot est une decouverte"
  note "BLOQUEE, jamais une absence : shim qui fait echouer ls-files ainsi, W2 BALAYE."
  SH2="$M/_shim_bloque"; mkdir -p "$SH2"
  printf '#!/bin/sh\nfor a in "$@"; do\n  if [ "$a" = ls-files ]; then\n    echo "fatal: not a git repository (or any of the parent directories): .git" >&2\n    exit 128\n  fi\ndone\nexec "%s" "$@"\n' "$REALGIT" > "$SH2/git"
  chmod +x "$SH2/git"
  run_scan env PATH="$SH2:$PATH" bash "$SCAN" --root "$M/W2"
  expect_rc 1 "(m) DECOUVERTE BLOQUEE sur W2 : BALAYE, jamais lu comme hors depot"
  expect_not_out "checkout(s) imbrique(s)" "(m) DECOUVERTE BLOQUEE sur W2 : aucune ligne d elagage"
fi

echo
echo "=== (m) ESPION — un chemin elague n est JAMAIS ouvert (os.scandir)"
note "la racine attendue passe par le MEME interpreteur que le script (sous Git Bash,"
note "argv est converti) : sa presence au journal est le controle POSITIF."
SP="$M/_spy"; mkdir -p "$SP"
printf 'import os\n_log = os.environ.get("SPY_LOG")\nif _log:\n    _orig = os.scandir\n    def _scandir(path="."):\n        with open(_log, "a", encoding="utf-8") as fh:\n            fh.write(os.fspath(path).replace("\\\\", "/") + "\\n")\n        return _orig(path)\n    os.scandir = _scandir\n' > "$SP/sitecustomize.py"
for a in W1 W2; do
  p="$(chemin_elague "$a")"
  racine="$("$PY" -c 'import sys; print(sys.argv[1].replace("\\", "/"))' "$M/$a")"
  L="$M/_spylog.$a"; : > "$L"
  PYTHONPATH="$SP" SPY_LOG="$L" bash "$SCAN" --root "$M/$a" >/dev/null 2>&1
  vue="$(grep -cxF "$racine" "$L")"
  sous="$(grep -cF "$racine/$p" "$L")"
  if [ "$vue" -ge 1 ]; then ok "(m) ESPION $a : la racine est au journal (controle positif)"; else
    ko "(m) ESPION $a : racine absente du journal — l espion ne voit rien, le zero ci-dessous ne prouve rien"; fi
  if [ "$sous" -eq 0 ]; then ok "(m) ESPION $a : 0 entree sous $p"; else
    ko "(m) ESPION $a : $sous entree(s) sous $p — le chemin est ouvert puis filtre"; fi
done

echo
echo "=== (m) DELAI — git sans reponse : le candidat est BALAYE, jamais elague (S-00003664)"
note "un sitecustomize espion fait lever TimeoutExpired a la requete d index et note"
note "le delai recu : la garde doit passer timeout=60 et BALAYER W2. Aucune ligne"
note "d elagage n est imprimee — les notes voyagent avec elle (borne de l en-tete)."
SPT="$M/_spy_delai"; mkdir -p "$SPT"
printf 'import os, subprocess\n_log = os.environ.get("SPY_DELAI_LOG")\nif _log:\n    _orig = subprocess.run\n    def _run(argv, *a, **k):\n        if "ls-files" in argv:\n            with open(_log, "a", encoding="utf-8") as fh:\n                fh.write("timeout=%%r\\n" %% (k.get("timeout"),))\n            raise subprocess.TimeoutExpired(argv, k.get("timeout") or 0)\n        return _orig(argv, *a, **k)\n    subprocess.run = _run\n' > "$SPT/sitecustomize.py"
LD="$M/_spy_delai.log"; : > "$LD"
run_scan env PYTHONPATH="$SPT" SPY_DELAI_LOG="$LD" bash "$SCAN" --root "$M/W2"
expect_rc 1 "(m) DELAI : git sans reponse sur W2 -> BALAYE, sa justification est lue"
expect_not_out "checkout(s) imbrique(s)" "(m) DELAI : aucune ligne d elagage"
if grep -qx 'timeout=60' "$LD"; then ok "(m) DELAI : la requete d index porte timeout=60"; else
  ko "(m) DELAI : la requete d index ne porte pas timeout=60 (journal : $(tr '\n' ' ' < "$LD"))"; fi
fi

echo
echo "================================================================"
echo "check-stale-justification.test.sh : $pass réussi(s) / $fail échoué(s)"
[ "$fail" -eq 0 ] || exit 1
echo "OK"
