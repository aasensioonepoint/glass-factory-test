#!/usr/bin/env bash
# =====================================================================
# BANC — core-scripts/plan_waves.py ordonne-t-il encore honnêtement ? (T-00000531)
#
# Le suffixe `.test.sh` est délibéré : `core-scripts/run-bash-tests.sh` découvre
# cette suite (il élague `.agents/` et `.claude/`, PAS `scripts/`), donc la
# garde du tri est DANS la porte qu'elle garde. `pytest.ini` ne collecte pas
# `scripts/`, c'est pourquoi ce banc est en bash et non en python.
#
# ---------------------------------------------------------------------
# LE BOARD EST CONSTRUIT PAR tasks.py, JAMAIS ÉCRIT À LA MAIN
# ---------------------------------------------------------------------
# Une seule exception, le cas CYCLE : `set_depends` PROUVE l'acyclicité avant
# d'écrire, donc aucun `tasks.py` ne peut produire le board qu'on veut mesurer.
# Ce cas-là injecte le cycle directement dans le JSON — c'est précisément le
# scénario que le script existe pour rattraper, et c'est aussi ce qui prouve
# que `load()` accepte un board cyclique (sans quoi le remède serait injouable).
#
# ---------------------------------------------------------------------
# CE QUE CE BANC NE PROUVE PAS
# ---------------------------------------------------------------------
# Il ne prouve AUCUNE disjonction de write-sets. `plan_waves` sur-détecte par
# construction : une botte qu'il propose reste non prouvée, et `tasks.py
# parallel` reste le seul prouveur. Les cas ci-dessous mesurent que la botte est
# PROPOSÉE et ANNONCÉE comme telle, jamais qu'elle est valide.
# =====================================================================
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
WAVES="$ROOT/core-scripts/plan_waves.py"
TASKS="$ROOT/.agents/bin/tasks.py"

# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# allows-missing: python python3 py
PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# T-00000753 : joué DIRECTEMENT, ce banc isole son état machine (le runner le fait déjà, `run-bash-tests.sh`) ;
# une valeur déjà posée est RESPECTÉE. Sous $TMP : nettoyé par le trap ci-dessus.
if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi
pass=0; fail=0

t() { "$PY" "$TASKS" --root "$TMP" "$@" >/dev/null; }
w() { "$PY" "$WAVES" --root "$TMP" "$@"; }
# `new` sous <racine>, puis l'id qu'il A RENDU (« TASKS: <id> → pending ») — jamais un id prédit :
# sous l'allocateur P-<ULID> (T-00000726, C2) aucune valeur n'est devinable (règle R-BANCS (i)).
nouvelle() { "$PY" "$TASKS" --root "$1" new "$2" | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p'; }

ok()  { pass=$((pass+1)); echo "  ok  — $1"; }
ko()  { fail=$((fail+1)); echo "  FAIL — $1"; }
expect_rc() { # <attendu> <obtenu> <titre>
  if [ "$1" = "$2" ]; then ok "$3 (rc=$2)"; else ko "$3 — attendu rc=$1, obtenu rc=$2"; fi
}
has() { # <fichier> <motif> <titre>
  if grep -q -- "$2" "$1"; then ok "$3"; else ko "$3 — motif absent : $2"; echo "--- sortie ---"; cat "$1"; fi
}
hasnt() { # <fichier> <motif> <titre>
  if grep -q -- "$2" "$1"; then ko "$3 — motif PRÉSENT alors qu'il ne devrait pas : $2"; else ok "$3"; fi
}

echo "=== (a) VAGUES : l'ordre dur, et la botte proposée ==================="
A="$(nouvelle "$TMP" "tache A")"; B="$(nouvelle "$TMP" "tache B")"
C="$(nouvelle "$TMP" "tache C")"; D="$(nouvelle "$TMP" "tache D")"
if [ -n "$A" ] && [ -n "$B" ] && [ -n "$C" ] && [ -n "$D" ]; then ok "quatre ids rendus par new"; else ko "new n'a pas rendu d'id : A=$A B=$B C=$C D=$D"; fi
t writeset "$A" src/a/
t writeset "$D" src/d/
t depends "$B" "$A" --motif "amont livre ce que aval consomme"
t depends "$C" "$B" --motif "amont livre ce que aval consomme"
w waves > "$TMP/a.out" 2>&1; expect_rc 0 $? "des vagues sont produites"
has "$TMP/a.out" "VAGUE 1" "la vague 1 existe"
has "$TMP/a.out" "VAGUE 3" "la profondeur de chaîne est respectée (A -> B -> C)"
has "$TMP/a.out" "botte (parallélisme PROPOSÉ, non prouvé ici)" \
  "la botte est annoncée comme PROPOSÉE, jamais comme prouvée"
has "$TMP/a.out" "tasks.py parallel" "la commande qui la rendrait réelle est donnée"
has "$TMP/a.out" "NON-AUTORITATIF" "le relevé dit ce qu'il EST, à chaque appel"

echo "=== (b) NON-VACUITÉ : la vague 1 n'est pas tout le monde ============="
# Sans cette assertion, un tri qui rendrait TOUT en vague 1 passerait (a).
if [ "$(grep -c '^VAGUE' "$TMP/a.out")" -ge 3 ]; then
  ok "au moins 3 vagues distinctes — l'ordre n'est pas un aplatissement"
else
  ko "un seul palier : le tri n'ordonne rien"; cat "$TMP/a.out"
fi

echo "=== (c) SÉRIALISATION : pas de writeset => jamais en botte ==========="
has "$TMP/a.out" "writeset non déclaré" "une tâche sans writeset est sérialisée, avec sa raison"

echo "=== (d) FERMETURE TRANSITIVE du périmètre ==========================="
w waves --task "$C" > "$TMP/d.out" 2>&1; expect_rc 0 $? "un périmètre explicite ferme et rend des vagues"
has "$TMP/d.out" "FERMETURE — 1 demandée(s), 3 planifiée(s)" \
  "l'expansion est CHIFFRÉE : 1 demandée, 3 planifiées"
has "$TMP/d.out" "tirée par" "chaque tâche tirée nomme QUI l'a tirée"
has "$TMP/d.out" "$A" "la dépendance transitive (A, à deux crans) est bien entrée"

echo "=== (e) DÉPENDANCE done : satisfaite, elle ne tire RIEN =============="
t done "$A" --raison "clos par le banc"
w waves --task "$B" > "$TMP/e.out" 2>&1; expect_rc 0 $? "une dépendance close ne bloque pas"
hasnt "$TMP/e.out" "FERMETURE" "aucune expansion : une dépendance done est SATISFAITE"
has "$TMP/e.out" "VAGUE 1" "la dépendante tombe en vague 1"

echo "=== (f) MUR : une dépendance blocked ARRÊTE la branche et la NOMME ==="
t block "$B" --note "attente decision pilote"
w waves --task "$C" > "$TMP/f.out" 2>&1; expect_rc 0 $? "un mur n'est pas une erreur d'exécution"
has "$TMP/f.out" "MURS" "le mur est nommé"
has "$TMP/f.out" "blocked" "la raison du mur est dite"
has "$TMP/f.out" "HORS VAGUES" "la dépendante sort du périmètre, nommée"
hasnt "$TMP/f.out" "^VAGUE" "AUCUNE vague creuse n'est produite derrière un mur"

echo "=== (g) CYCLE : exit 3, chemin nommé, RIEN d'autre rendu ============="
CY="$TMP/cyc"; mkdir -p "$CY/.agents/state/board"
X="$(nouvelle "$CY" "X")"; Y="$(nouvelle "$CY" "Y")"
"$PY" - "$CY" "$X" "$Y" <<'PY'
import json,sys,pathlib
p=pathlib.Path(sys.argv[1])/".agents/state/board/TASKS.json"
x_id, y_id = sys.argv[2], sys.argv[3]
d=json.loads(p.read_text(encoding="utf-8"))
for x in d["tasks"]:
    x["depends_on"]=[y_id] if x["id"]==x_id else [x_id]
p.write_text(json.dumps(d,indent=2),encoding="utf-8")
PY
"$PY" "$WAVES" --root "$CY" waves > "$TMP/g.out" 2>&1; expect_rc 3 $? "un cycle sort en 3, jamais en 0"
has "$TMP/g.out" "CYCLE" "le refus se nomme"
has "$TMP/g.out" "→" "le chemin du cycle est rendu en entier"
has "$TMP/g.out" "depends .* --retirer" "un remède EXÉCUTABLE est nommé — il retire UNE arête (T-00000765)"
hasnt "$TMP/g.out" "depends .* --clear" "le remède n'est plus la réécriture destructrice --clear"
hasnt "$TMP/g.out" "VAGUE" "aucune vague n'est rendue : pas d'ordre partiel qui aurait l'air complet"
# Et le remède TOURNE — c'est ce qui justifie que `load()` accepte un cycle.
"$PY" "$TASKS" --root "$CY" depends "$X" --retirer "$Y" >/dev/null 2>&1
expect_rc 0 $? "le remède tourne sur le board cyclique lui-même"

echo "=== (g2) CYCLE à côté d'un ORDRE PILOTE : --retirer, jamais --clear ===="
# T1 dépend de T2 (cycle, sans motif) ET de T3 (ORDRE PILOTE, injecté en JSON par
# STDIN — Piège 3 : aucune valeur argv ne commence par `/`). Le remède retire
# l'arête technique T1←T2 seule ; T1←T3 et son motif SURVIVENT au rejeu.
CY2="$TMP/cyc2"; mkdir -p "$CY2/.agents/state/board"
T1="$(nouvelle "$CY2" "X")"; T2="$(nouvelle "$CY2" "Y")"; T3="$(nouvelle "$CY2" "Z")"
"$PY" - "$CY2" "$T1" "$T2" "$T3" <<'PY'
import json,sys,pathlib
p=pathlib.Path(sys.argv[1])/".agents/state/board/TASKS.json"
t1, t2, t3 = sys.argv[2], sys.argv[3], sys.argv[4]
d=json.loads(p.read_text(encoding="utf-8"))
for x in d["tasks"]:
    if x["id"]==t1:
        x["depends_on"]=[t2,t3]
        x["depends_motif"]={t3:"ORDRE PILOTE S-00000001 : x"}
    elif x["id"]==t2:
        x["depends_on"]=[t1]
p.write_text(json.dumps(d,indent=2),encoding="utf-8")
PY
"$PY" "$WAVES" --root "$CY2" waves > "$TMP/g2.out" 2>&1; expect_rc 3 $? "le cycle sort en 3"
has "$TMP/g2.out" "depends $T1 --retirer $T2" "le remède vise l'arête TECHNIQUE du cycle"
hasnt "$TMP/g2.out" "depends .* --clear" "jamais --clear : il effacerait aussi l'ORDRE PILOTE"
has "$TMP/g2.out" "restent : $T3" "le remède nomme l'arête qui RESTE"
"$PY" "$TASKS" --root "$CY2" depends "$T1" --retirer "$T2" >/dev/null 2>&1
expect_rc 0 $? "le remède rejoué tourne"
"$PY" "$TASKS" --root "$CY2" depends-show "$T1" > "$TMP/g2.show" 2>&1
has "$TMP/g2.show" "$T3 → .*ORDRE PILOTE S-00000001 : x" "T1←T3 et son motif ORDRE PILOTE sont INTACTS"
"$PY" "$WAVES" --root "$CY2" waves > "$TMP/g2b.out" 2>&1; expect_rc 0 $? "le board réparé rend des vagues (rc 0)"

echo "=== (g3) CYCLE tout ORDRE PILOTE : route SUGGESTION, jamais --retirer T- ="
CY3="$TMP/cyc3"; mkdir -p "$CY3/.agents/state/board"
P="$(nouvelle "$CY3" "P")"; Q="$(nouvelle "$CY3" "Q")"
"$PY" - "$CY3" "$P" "$Q" <<'PY'
import json,sys,pathlib
p=pathlib.Path(sys.argv[1])/".agents/state/board/TASKS.json"
p_id, q_id = sys.argv[2], sys.argv[3]
d=json.loads(p.read_text(encoding="utf-8"))
for x in d["tasks"]:
    autre=q_id if x["id"]==p_id else p_id
    x["depends_on"]=[autre]
    x["depends_motif"]={autre:"ORDRE PILOTE S-00000001 : a" if x["id"]==p_id else "ORDRE PILOTE S-00000002 : b"}
p.write_text(json.dumps(d,indent=2),encoding="utf-8")
PY
"$PY" "$WAVES" --root "$CY3" waves > "$TMP/g3.out" 2>&1; expect_rc 3 $? "le cycle tout ordre pilote sort en 3"
has "$TMP/g3.out" "SUGGESTION:" "la route est une SUGGESTION que le pilote tranche"
has "$TMP/g3.out" "retirer-ordre-pilote" "puis --retirer-ordre-pilote après décision"
hasnt "$TMP/g3.out" "--retirer T-" "un agent ne retire JAMAIS un ORDRE PILOTE : pas de --retirer T-"

echo "=== (h) --json : non tronqué, et le code de sortie suit =============="
"$PY" "$WAVES" --root "$CY" waves --json > "$TMP/h.out" 2>&1
expect_rc 0 $? "--json sur un board réparé sort en 0"
"$PY" - "$TMP/h.out" <<'PY'
import json,sys
json.load(open(sys.argv[1], encoding="utf-8"))
PY
expect_rc 0 $? "--json rend du JSON valide"

echo "=== (i) store malformé : exit 1, JAMAIS dégradé en graphe plat ======="
BAD="$TMP/bad"; mkdir -p "$BAD/.agents/state/board"
printf 'pas du json' > "$BAD/.agents/state/board/TASKS.json"
"$PY" "$WAVES" --root "$BAD" waves > "$TMP/i.out" 2>&1
expect_rc 1 $? "un store illisible est une erreur d'exécution, pas un verdict"
hasnt "$TMP/i.out" "VAGUE" "aucun ordre n'est inventé sur un store illisible"

echo "=== (j) id inconnu : refus bruyant, jamais un périmètre plus petit ==="
w waves --task T-00009999 > "$TMP/j.out" 2>&1
expect_rc 1 $? "un id inconnu refuse"
has "$TMP/j.out" "inconnu au board" "le refus nomme la cause"

echo "=== (k) T-<ULID> : clé à DEUX ÉTAGES, anciens d'abord (T-00000726, C1e) ======"
# FIXTURES JSON, deuxième exception à « construit par tasks.py » (E7 du plan de
# T-00000726) : avant la bascule C2, aucun `tasks.py new` n'émet de `T-<ULID>`.
# U_LETTER et UB finissent par une LETTRE — l'ancienne clé `(\d+)\Z` lève dessus ;
# une `T-<ULID>` à chiffre final (U_DIGIT, queue « 2 ») passerait en silence AVANT
# T-00000003 : témoin d'ORDRE du seul site :377 ; les autres sites sont tenus par (k7).
U_LETTER="01M3250V003HCPQKTZ8ENYF4VM"; U_DIGIT="01M3253WN0W4D0K2S3759WV6M2"
UB_LETTER="01M3260V003HCPQKTZ8ENYF4VQ"
UL="T-$U_LETTER"; UD="T-$U_DIGIT"; UB="T-$UB_LETTER"
# pose_board <racine> <id>=<état>[;<dépendance>,…[;<chemin>,…[;<responsable>]]] … — le board
# ENTIER, sans `next_id` (plan_waves ne le lit pas, et C2 le retire). Le 4e champ est le
# `responsable` humain (D2) : clé absente quand il est vide, comme au board.
pose_board() {
  "$PY" - "$@" <<'PY'
import json, pathlib, sys
racine, taches = pathlib.Path(sys.argv[1]), []
for spec in sys.argv[2:]:
    tid, _, reste = spec.partition("=")
    etat, deps, chemins, responsable = (reste.split(";") + ["", "", ""])[:4]
    tache = {"id": tid, "state": etat, "task": "banc " + tid, "owner": ""}
    if deps:
        tache["depends_on"] = deps.split(",")
    if chemins:
        tache["writeset"] = chemins.split(",")
    if responsable:
        tache["responsable"] = responsable
    taches.append(tache)
p = racine / ".agents/state/board/TASKS.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({"tasks": taches}, indent=2), encoding="utf-8")
PY
}
# avant <fichier> <d'abord> <ensuite> <titre> — par PREMIÈRE occurrence, en clair (-F).
avant() {
  la="$(grep -n -m 1 -F -- "$2" "$1" | cut -d: -f1)"; lb="$(grep -n -m 1 -F -- "$3" "$1" | cut -d: -f1)"
  if [ -n "$la" ] && [ -n "$lb" ] && [ "$la" -lt "$lb" ]; then ok "$4"
  else ko "$4 — $2 ligne [$la], $3 ligne [$lb]"; cat "$1"; fi
}
K="$TMP/k"
pose_board "$K" "T-00000010=pending" "$UD=pending" "T-00000003=pending" "$UL=pending"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k.out" 2>&1; expect_rc 0 $? "board mêlé (anciens + ULID), sans --task : des vagues sont produites"
avant "$TMP/k.out" "T-00000003" "T-00000010" "les anciens entre eux : par NUMÉRO"
avant "$TMP/k.out" "T-00000010" "$UL" "la ligne ULID vient APRÈS le dernier ancien"
avant "$TMP/k.out" "$UL" "$UD" "les ULID entre eux : dans l'ordre de frappe (queue chiffrée « 2 » comprise)"
pose_board "$K" "T-00000003=pending" "T-01m3250v003hcpqktz8enyf4vm=pending"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k1.out" 2>&1; expect_rc 1 $? "un id ni ancien ni ULID (ULID en minuscules) : refus, jamais rangé"
has "$TMP/k1.out" "id de tâche malformé" "le refus nomme la cause"

echo "=== (k2) T-<ULID> en --task EXPLICITE (compute :396) ======================"
pose_board "$K" "$UL=pending" "T-00000003=pending"
"$PY" "$WAVES" --root "$K" waves --task "$UL" --task T-00000003 --json > "$TMP/k2.out" 2>&1
expect_rc 0 $? "--task mêlant ULID et ancien : rc 0"
"$PY" - "$TMP/k2.out" T-00000003 "$UL" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if d["demandees"] == sys.argv[2:] else 1)
PY
expect_rc 0 $? "« demandees » rangées ancien PUIS ULID, quel que soit l'ordre des --task"

echo "=== (k3) CYCLE mêlant ULID et ancien (find_cycles :205) ; MUR derrière ULID (build_waves :328/:329) ="
pose_board "$K" "$UL=pending;T-00000003" "T-00000003=pending;$UL"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k3.out" 2>&1; expect_rc 3 $? "le cycle mêlé sort en 3"
has "$TMP/k3.out" "T-00000003 → $UL → T-00000003" "le chemin part de l'ANCIEN (origines rangées par la clé)"
pose_board "$K" "$UB=pending;$UL" "$UL=pending;T-00000004" "T-00000004=blocked"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k3b.out" 2>&1; expect_rc 0 $? "un mur derrière des ULID n'est pas une erreur"
has "$TMP/k3b.out" "MURS" "le mur est nommé"
has "$TMP/k3b.out" "$UB .*dépend de $UL — derrière une branche arrêtée" "la ULID tenue derrière le mur sort NOMMÉE, avec sa dépendance ULID"

echo "=== (k4) BOTTE à membre ULID ; sérialisées rangées par la clé (bundle_wave :377) ="
pose_board "$K" "T-00000005=pending;;src/x/" "$UL=pending;;src/y/" "$UD=pending" "T-00000007=pending"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k4.out" 2>&1; expect_rc 0 $? "botte et sérialisées mêlées : rc 0"
has "$TMP/k4.out" "non prouvé ici) : T-00000005 $UL" "la botte porte l'ancien PUIS la ULID"
avant "$TMP/k4.out" "T-00000007" "$UD" "la ULID sérialisée vient APRÈS l'ancien sérialisé (U_DIGIT n'est pas « 2 »)"

echo "=== (k5) FERMETURE : tirées ULID et ancienne, rangées par la clé (render :490) ="
pose_board "$K" "T-00000009=pending;$UL,T-00000008" "$UL=pending" "T-00000008=pending"
"$PY" "$WAVES" --root "$K" waves --task T-00000009 > "$TMP/k5.out" 2>&1; expect_rc 0 $? "une fermeture qui tire une ULID : rc 0"
has "$TMP/k5.out" "FERMETURE — 1 demandée(s), 3 planifiée(s)" "l'expansion est chiffrée"
avant "$TMP/k5.out" "T-00000008" "$UL" "les tirées : l'ancienne PUIS la ULID"

echo "=== (k6) PARITÉ de la clé avec tasks.sort_key (recopiée, jamais importée) ======"
"$PY" - "$ROOT" "$U_LETTER" "$U_DIGIT" <<'PY'
import pathlib, sys
racine, ul, ud = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(racine / "core-scripts")); sys.path.insert(0, str(racine / ".agents" / "bin"))
import plan_waves, tasks
ids = ["T-1", "T-003", "T-00000003", "T-00000221", "S-00000002", "T-" + ul, "T-" + ud, "S-" + ul, "L-" + ud,
       "T-" + "1" * 15, "T-" + "1" * 16, "T-0" + "1" * 15]
ecarts = []
for i in ids:
    issues = []
    for cle in (plan_waves.numeric_id, tasks.sort_key):
        try:
            issues.append(("rang", cle(i)))
        except Exception as exc:  # LEVER des DEUX côtés est une parité ; d'un seul, un écart
            issues.append(("leve", type(exc).__name__))
    if issues[0] != issues[1] and not (issues[0][0] == issues[1][0] == "leve"):
        ecarts.append(f"{i} {issues}")
print("ecarts", ecarts)
sys.exit(1 if ecarts else 0)
PY
expect_rc 0 $? "plan_waves.numeric_id == tasks.sort_key sur anciens et ULID (T/S/L)"

echo "=== (k7) TÉMOINS D'ORDRE PAR SITE : U_DIGIT (queue « 2 ») face à des anciens > 2 ="
# La clé recopiée est tenue par (k6) ; ces cas tiennent CHAQUE APPELANT : un site qui
# cesserait d'appeler `numeric_id` (clé ancienne d'abord, ULID ensuite) rangerait U_DIGIT
# comme « 2 » SANS lever. (k)-(k5) n'y voient que :377.
pose_board "$K" "$UD=pending;T-00000003" "T-00000003=pending;$UD"
"$PY" "$WAVES" --root "$K" waves > "$TMP/k7a.out" 2>&1; expect_rc 3 $? "(k7a) cycle mêlé à U_DIGIT : 3"
has "$TMP/k7a.out" "T-00000003 → $UD → T-00000003" "(k7a) :205 le chemin part de l'ANCIEN"
pose_board "$K" "T-00000010=pending" "$UD=pending" "T-00000003=pending"
"$PY" "$WAVES" --root "$K" waves --json > "$TMP/k7b.out" 2>&1; expect_rc 0 $? "(k7b) rc 0"
"$PY" - "$TMP/k7b.out" taches T-00000003 T-00000010 "$UD" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
v = d["vagues"][0]["taches"] if sys.argv[2] == "taches" else d["demandees"]
sys.exit(0 if v == sys.argv[3:] else 1)
PY
expect_rc 0 $? "(k7b) :323 la vague 1 range les anciens par numéro PUIS U_DIGIT"
"$PY" - "$TMP/k7b.out" demandees T-00000003 T-00000010 "$UD" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
v = d["vagues"][0]["taches"] if sys.argv[2] == "taches" else d["demandees"]
sys.exit(0 if v == sys.argv[3:] else 1)
PY
expect_rc 0 $? "(k7c) :405 « demandees » sans --task : anciens PUIS U_DIGIT"
"$PY" "$WAVES" --root "$K" waves --task "$UD" --task T-00000003 --json > "$TMP/k7d.out" 2>&1
"$PY" - "$TMP/k7d.out" T-00000003 "$UD" <<'PY'
import json, sys
sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8"))["demandees"] == sys.argv[2:] else 1)
PY
expect_rc 0 $? "(k7d) :396 « demandees » en --task : l'ancien PUIS U_DIGIT"
pose_board "$K" "$UL=pending;T-00000004" "T-00000004=blocked" "$UD=pending;$UL" \
  "T-00000005=pending;$UL" "T-00000006=pending;$UD,T-00000005"
"$PY" "$WAVES" --root "$K" waves --json > "$TMP/k7e.out" 2>&1; expect_rc 0 $? "(k7e) rc 0"
"$PY" - "$TMP/k7e.out" "$UL" T-00000005 T-00000006 "$UD" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1], encoding="utf-8"))["hors_vagues"]
sys.exit(0 if [r["tache"] for r in rows] == sys.argv[2:] else 1)
PY
expect_rc 0 $? "(k7e) :328 hors vagues : le mur (UL), les anciens par numéro, PUIS U_DIGIT"
"$PY" - "$TMP/k7e.out" T-00000006 "T-00000005, $UD" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1], encoding="utf-8"))["hors_vagues"]
sys.exit(0 if [r["dependance"] for r in rows if r["tache"] == sys.argv[2]] == [sys.argv[3]] else 1)
PY
expect_rc 0 $? "(k7f) :329 dépendances tenues de T-00000006 : l'ancien PUIS U_DIGIT"
pose_board "$K" "T-00000009=pending;$UD,T-00000008" "$UD=pending" "T-00000008=pending"
"$PY" "$WAVES" --root "$K" waves --task T-00000009 > "$TMP/k7g.out" 2>&1; expect_rc 0 $? "(k7g) rc 0"
avant "$TMP/k7g.out" "T-00000008" "$UD" "(k7g) :490 tirées : l'ancienne PUIS U_DIGIT"

# json_vaut <fichier> <clé> <json attendu> <titre> — égalité STRICTE d'une clé de premier niveau.
json_vaut() {
  "$PY" - "$1" "$2" "$3" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if d.get(sys.argv[2], "<absente>") == json.loads(sys.argv[3]) else 1)
PY
  if [ $? -eq 0 ]; then ok "$4"
  else
    ko "$4 — $2 attendu $3, obtenu :"
    "$PY" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], "<absente>"))' "$1" "$2"
  fi
}

echo "=== (t) CHEMIN CRITIQUE et LIBERATIONS : A <- B <- C, D isolée (D2) ============"
pose_board "$K" "T-00000011=pending;;;Ana" "T-00000012=pending;T-00000011" \
  "T-00000013=pending;T-00000012" "T-00000014=pending"
"$PY" "$WAVES" --root "$K" waves --json > "$TMP/t.json" 2>&1; expect_rc 0 $? "(t) --json rc 0"
json_vaut "$TMP/t.json" chemin_critique '["T-00000011", "T-00000012", "T-00000013"]' \
  "(t) chemin_critique = la PLUS LONGUE chaîne, amont d'abord (la chaîne isolée D ne l'est pas)"
json_vaut "$TMP/t.json" liberations '[{"tache": "T-00000011", "libere": ["T-00000012", "T-00000013"], "directes": ["T-00000012"], "responsable": "Ana"}, {"tache": "T-00000012", "libere": ["T-00000013"], "directes": ["T-00000013"], "responsable": null}]' \
  "(t) A libère 2 (B, C) dont 1 directe, responsable lu au board ; la plus libérante d'abord"
"$PY" "$WAVES" --root "$K" waves > "$TMP/t.out" 2>&1; expect_rc 0 $? "(t) texte rc 0"
has "$TMP/t.out" "CHEMIN CRITIQUE — 3 tâche(s) : T-00000011 → T-00000012 → T-00000013" "(t) la ligne CHEMIN CRITIQUE nomme la chaîne"
has "$TMP/t.out" "T-00000011   libère 2 (T-00000012, T-00000013) dont 1 directe(s) — responsable : Ana" \
  "(t) la ligne LIBERATIONS dit le compte, les ids, les directes et le responsable"

echo "=== (u) DÉPARTAGE : deux chaînes de même longueur, par numeric_id (SYM-07044) ==="
# T-9 et T-00000010 : la clé NUMÉRIQUE range T-9 d'abord, la chaîne brute range
# « T-00000010 » d'abord — un départage par chaîne, inversé ou absent rougit.
pose_board "$K" "T-00000010=pending" "T-00000020=pending;T-00000010" \
  "T-9=pending" "T-00000030=pending;T-9"
"$PY" "$WAVES" --root "$K" waves --json > "$TMP/u.json" 2>&1; expect_rc 0 $? "(u) rc 0"
json_vaut "$TMP/u.json" chemin_critique '["T-9", "T-00000030"]' \
  "(u) à longueur égale, la plus petite suite de clés numeric_id, amont d'abord"

echo "=== (v) TIRÉES : une tâche DEMANDÉE n'est jamais « tirée » (T-00001249) ========"
# L'aval demandé a l'id INFÉRIEUR à l'amont demandé : seul ordre qui révèle le défaut
# (l'aval est dépilé avant son amont, comme feuille_de_route.test.sh (e2)).
pose_board "$K" "T-00000001=pending;T-00000002,T-00000003" "T-00000002=pending" "T-00000003=pending"
"$PY" "$WAVES" --root "$K" waves --task T-00000001 --task T-00000002 --json > "$TMP/v.json" 2>&1
expect_rc 0 $? "(v) rc 0"
json_vaut "$TMP/v.json" tirees_par '{"T-00000003": "T-00000001"}' \
  "(v) tirees_par : l'amont DEMANDÉ n'y est pas, l'amont non demandé y est, tiré par son aval"
"$PY" "$WAVES" --root "$K" waves --task T-00000001 --task T-00000002 > "$TMP/v.out" 2>&1
has "$TMP/v.out" "FERMETURE — 2 demandée(s), 3 planifiée(s) : 1 tirée(s) par dépendance." "(v) le compte de la FERMETURE suit"
hasnt "$TMP/v.out" "T-00000002 *tirée par" "(v) l'amont demandé n'est jamais dit « tirée par »"

echo "=== (w) ORDRE des blocs : vagues, murs, hors-vagues, PUIS chemin et libérations ="
pose_board "$K" "T-00000011=pending" "T-00000012=pending;T-00000011" "T-00000013=pending;T-00000012" \
  "T-00000015=pending;T-00000016" "T-00000016=blocked"
"$PY" "$WAVES" --root "$K" waves > "$TMP/w.out" 2>&1; expect_rc 0 $? "(w) rc 0"
avant "$TMP/w.out" "VAGUE 1" "MURS" "(w) VAGUE avant MURS"
avant "$TMP/w.out" "MURS" "HORS VAGUES" "(w) MURS avant HORS VAGUES"
avant "$TMP/w.out" "HORS VAGUES" "CHEMIN CRITIQUE" "(w) HORS VAGUES avant CHEMIN CRITIQUE"
avant "$TMP/w.out" "CHEMIN CRITIQUE" "LIBERATIONS" "(w) CHEMIN CRITIQUE avant LIBERATIONS"
avant "$TMP/w.out" "LIBERATIONS" "NON-AUTORITATIF" "(w) LIBERATIONS avant la ligne NON-AUTORITATIF"

echo "=== (x) AUCUNE ARÊTE dans le périmètre : ligne annoncée, JSON vides ==========="
pose_board "$K" "T-00000001=pending" "T-00000002=pending"
"$PY" "$WAVES" --root "$K" waves > "$TMP/x.out" 2>&1; expect_rc 0 $? "(x) rc 0"
has "$TMP/x.out" "CHEMIN CRITIQUE — aucune dépendance entre les tâches placées" "(x) l'absence de chemin est DITE"
hasnt "$TMP/x.out" "LIBERATIONS" "(x) aucun bloc LIBERATIONS sans arête"
avant "$TMP/x.out" "CHEMIN CRITIQUE" "NON-AUTORITATIF" "(x) la ligne vient avant NON-AUTORITATIF"
"$PY" "$WAVES" --root "$K" waves --json > "$TMP/x.json" 2>&1; expect_rc 0 $? "(x) --json rc 0"
json_vaut "$TMP/x.json" chemin_critique '[]' "(x) chemin_critique : []"
json_vaut "$TMP/x.json" liberations '[]' "(x) liberations : []"

echo "=== (y) ID DU BOARD porteur d'ESC : CHEMIN CRITIQUE et LIBERATIONS le filtrent ="
# `numeric_id` ne lit que la queue (« 7 ») : l'id se range sans lever. Sans le filtre
# `_id_imprime`, la séquence ESC sort brute dans les deux blocs ; avec lui, `T-??31m7`.
ESC_ID=$'T-\033[31m7'
pose_board "$K" "$ESC_ID=pending" "T-00000008=pending;$ESC_ID"
"$PY" "$WAVES" --root "$K" waves > "$TMP/y.out" 2>&1; expect_rc 0 $? "(y) rc 0"
sed -n '/^CHEMIN CRITIQUE/,/NON-AUTORITATIF/p' "$TMP/y.out" > "$TMP/y.blocs"
has "$TMP/y.blocs" "CHEMIN CRITIQUE — 2 tâche(s) : T-??31m7 → T-00000008" "(y) CHEMIN CRITIQUE imprime l'id filtré"
has "$TMP/y.blocs" "T-??31m7     libère 1 (T-00000008)" "(y) LIBERATIONS imprime l'id filtré"
hasnt "$TMP/y.blocs" $'\033' "(y) aucun octet ESC dans CHEMIN CRITIQUE ni LIBERATIONS"

echo "=== (z) IDS HOSTILES : une commande imprimée passe l'id ENTIER, sans l'exécuter ="
# Un id du board est une DONNÉE (T-01M5CS8B2EJR8P4D4TSVJ2GJYZ). Trois boards écrits en
# JSON (aucun `tasks.py` n'écrit ces ids) : un cycle technique X/Q (UN remède `--retirer`),
# un cycle d'ORDRES PILOTE W/Q (DEUX commandes : la SUGGESTION `specs.py add`, puis
# `--retirer-ordre-pilote`), une botte X/W/D à writesets disjoints (UNE commande
# `parallel`). L'oracle exige le NOMBRE de commandes, refuse toute expansion vivante
# (`$ ; | & < >` et accent grave hors guillemets simples ; seuls les placeholders
# `"<pourquoi>"` et `S-<décision du pilote>` sont exemptés, littéralement), puis découpe
# chaque commande par `shlex.split` : un id ENTIER à chaque place, la SUGGESTION en UN
# argument, `--` puis les trois ids pour `parallel`. Le suffixe de diagnostic du remède
# technique (« (restent : …) », « (c'était sa seule arête) ») n'est pas une commande :
# il est coupé avant l'oracle. Borne : shell POSIX seul, ni PowerShell ni cmd.
ZX='x; echo PWN 7'; ZW='w$(echo PWN) 8'; ZQ="q'> z 9"; ZD="-d'>z10"
# z_board <racine> <mode> <X> <W> <Q> <D>
z_board() {
  "$PY" - "$@" <<'PY'
import json, pathlib, sys
racine, mode, x_id, w_id, q_id, d_id = sys.argv[1:7]
def tache(tid, **champs):
    return {"id": tid, "state": "pending", "task": "banc (z) " + mode, "owner": "", **champs}
if mode == "technique":
    taches = [tache(x_id, depends_on=[q_id], depends_motif={q_id: "technique : banc"}),
              tache(q_id, depends_on=[x_id], depends_motif={x_id: "technique : banc"})]
elif mode == "ordre-pilote":
    taches = [tache(w_id, depends_on=[q_id], depends_motif={q_id: "ORDRE PILOTE S-00000001 : banc"}),
              tache(q_id, depends_on=[w_id], depends_motif={w_id: "ORDRE PILOTE S-00000002 : banc"})]
else:
    taches = [tache(tid, writeset=[f"src/z{rang}/"]) for rang, tid in enumerate((x_id, w_id, d_id))]
p = pathlib.Path(racine) / ".agents/state/board/TASKS.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({"tasks": taches}, indent=2), encoding="utf-8")
PY
}
# z_oracle <sortie> <mode> <nombre attendu> <id>… — rc 0 si tout tient, rc 1 et une ligne par faute sinon.
z_oracle() {
  "$PY" - "$@" <<'PY'
import shlex, sys
sortie, mode, attendu, ids = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4:]
SUFFIXES = (" (restent : ", " (c'était sa seule arête)")
PLACEHOLDERS = ('"<pourquoi>"', "S-<décision du pilote>")
cmds = []
for ligne in open(sortie, encoding="utf-8").read().splitlines():
    ligne = ligne.strip()
    if not ligne.startswith("python .agents/bin/"):
        continue
    for suffixe in SUFFIXES:
        ligne = ligne.split(suffixe, 1)[0]
    cmds.append(ligne)
fautes = [] if len(cmds) == attendu else [f"{len(cmds)} commande(s), {attendu} attendue(s)"]
def vivant(c):
    for p in PLACEHOLDERS:
        c = c.replace(p, "")
    etat, i = "", 0
    while i < len(c):
        ch = c[i]
        if etat == "'":
            etat = "" if ch == "'" else etat
        elif ch == "\\":
            i += 1
        elif etat == '"':
            if ch in "$`":
                return True
            etat = "" if ch == '"' else etat
        elif ch in "'\"":
            etat = ch
        elif ch in "$;|&<>`":
            return True
        i += 1
    return False
def apres(t, opt):
    return t[t.index(opt) + 1] if opt in t[:-1] else None
avals = set()
for c in cmds:
    if vivant(c):
        fautes.append(f"expansion vivante : {c}")
    try:
        t = shlex.split(c)
    except ValueError as exc:
        fautes.append(f"indécoupable {exc} : {c}")
        continue
    if mode == "botte":
        if t[1:3] != [".agents/bin/tasks.py", "parallel"] or t[3:4] != ["--"] or sorted(t[4:]) != sorted(ids):
            fautes.append(f"ids ou -- : {c}")
        continue
    aval = amont = None
    if t[1:3] == [".agents/bin/tasks.py", "depends"]:
        aval = t[3]
        amont = apres(t, "--retirer" if mode == "technique" else "--retirer-ordre-pilote")
    elif t[1:3] == [".agents/bin/specs.py", "add"]:
        aval = apres(t, "--task")
        amont = (set(ids) - {aval}).pop() if aval in ids else None
        if apres(t, "delta") != f"SUGGESTION: retirer {aval} <- {amont}":
            fautes.append(f"SUGGESTION coupée : {c}")
    if {aval, amont} != set(ids):
        fautes.append(f"id coupé ou déplacé : {c}")
    avals.add(aval)
if len(avals) > 1:
    fautes.append(f"les commandes ne retirent pas la même arête : {sorted(map(str, avals))}")
for faute in fautes:
    print(faute)
sys.exit(1 if fautes else 0)
PY
}
for mode in technique ordre-pilote botte; do
  z_board "$TMP/z-$mode" "$mode" "$ZX" "$ZW" "$ZQ" "$ZD"
  "$PY" "$WAVES" --root "$TMP/z-$mode" waves > "$TMP/z-$mode.out" 2>&1; echo "$?" > "$TMP/z-$mode.rc"
done
expect_rc 3 "$(cat "$TMP/z-technique.rc")" "(z) cycle technique aux ids hostiles : CYCLE"
expect_rc 3 "$(cat "$TMP/z-ordre-pilote.rc")" "(z) cycle d'ordres pilote aux ids hostiles : CYCLE"
expect_rc 0 "$(cat "$TMP/z-botte.rc")" "(z) botte aux ids hostiles : vagues"
z_oracle "$TMP/z-technique.out" technique 1 "$ZX" "$ZQ" > "$TMP/z1.w" 2>&1; rc_z=$?
expect_rc 0 "$rc_z" "(z) cycle technique : UNE commande, ids entiers, aucune expansion vivante"
[ "$rc_z" -eq 0 ] || cat "$TMP/z1.w"
z_oracle "$TMP/z-ordre-pilote.out" ordre-pilote 2 "$ZW" "$ZQ" > "$TMP/z2.w" 2>&1; rc_z=$?
expect_rc 0 "$rc_z" "(z) cycle d'ordres pilote : DEUX commandes, ids entiers, SUGGESTION en un argument"
[ "$rc_z" -eq 0 ] || cat "$TMP/z2.w"
z_oracle "$TMP/z-botte.out" botte 1 "$ZX" "$ZW" "$ZD" > "$TMP/z3.w" 2>&1; rc_z=$?
expect_rc 0 "$rc_z" "(z) botte : UNE commande parallel, -- puis les trois ids entiers"
[ "$rc_z" -eq 0 ] || cat "$TMP/z3.w"

echo "================================================================"
echo "Resume : $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ]
