#!/usr/bin/env bash
# =====================================================================
# BANC — core-scripts/feuille_de_route.py rend-il les sections DÉRIVABLES d'un
# chantier QUELCONQUE, sans dictionnaire éditorial ? (T-00001016)
#
# Le suffixe `.test.sh` est délibéré, comme pour `plan_waves.test.sh` :
# `core-scripts/run-bash-tests.sh` découvre cette suite, et `pytest.ini` ne
# collecte pas `core-scripts/`.
#
# ---------------------------------------------------------------------
# LE BOARD EST SYNTHÉTIQUE, CONSTRUIT PAR tasks.py SAUF TROIS ARÊTES
# ---------------------------------------------------------------------
# Les noms de chantier (`zeta-banc`, `omega-banc`) n'existent sur aucun board
# réel, et les ids sont ceux que `new` A RENDUS, jamais prédits : un moteur qui
# porterait un dictionnaire indexé par id ou par chantier ne pourrait PAS
# produire ces sections. Trois arêtes sont injectées dans le JSON, parce que
# `tasks.py` les refuse à l'écriture (mesuré avant d'écrire ce banc) :
#   - deux `ORDRE PILOTE S-<id>` : `depends` exige que la décision existe au
#     journal (rc 2 sinon) ; l'une porte un S- à 8 chiffres, l'autre un ULID ;
#   - un lien PENDANT vers un id absent du board : `depends` le refuse (rc 2).
# Le cas CYCLE injecte aussi son cycle, comme `plan_waves.test.sh` (g) : aucun
# `tasks.py` ne peut produire un board cyclique.
#
# ---------------------------------------------------------------------
# CE QUE CE BANC NE PROUVE PAS
# ---------------------------------------------------------------------
# Il ne prouve pas la JUSTESSE des vagues : elles viennent de `plan_waves.py`,
# dont `plan_waves.test.sh` est le banc. Il prouve que le moteur les REPREND
# sans les recalculer, et que ses propres dérivations (amonts ouverts, natures
# de motif, ordres pilote, closes en attente) mordent sur un board qui peut
# les faire rougir. Le témoin « aucun dictionnaire éditorial » lit la SOURCE
# (arbre syntaxique) : il refuse un identifiant de tâche, un numéro court, une
# table clé chaîne -> chaîne (ou rangée de constantes) à toute profondeur, un
# `dict(...)` de mots-clés constants, une liste ou un tuple de chaînes en tête de
# module, et un import d'horloge ou de sous-processus (le rendu doit rester
# identique à l'octet). Il ne peut pas refuser une donnée éditoriale écrite sous
# une autre forme — c'est la revue qui la voit.
# =====================================================================
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
FDR="$ROOT/core-scripts/feuille_de_route.py"
TASKS="$ROOT/.agents/bin/tasks.py"

# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# allows-missing: python python3 py
PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi
# Stores jetables, tous sous $TMP (nettoyé par le trap) : aucun board, journal ni
# flux d'événements réel n'est touché, et les temporaires des enfants y naissent.
export CADRE_PROJECT_ROOT="$TMP"
export AGENTS_EVENTS_DIR="$TMP/events"
mkdir -p "$TMP/tmp"
export TMPDIR="$TMP/tmp"
pass=0; fail=0

CH="zeta-banc"
CH2="omega-banc"
# `new` sous <racine>, puis l'id qu'il A RENDU — jamais un id prédit.
nouvelle() { "$PY" "$TASKS" --root "$1" new "$2" --chantier "$3" 2>/dev/null | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p'; }
t() { "$PY" "$TASKS" --root "$TMP" "$@" >/dev/null 2>&1; }
f() { "$PY" "$FDR" --root "$TMP" "$@"; }

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
# La section `## <titre>` d'une sortie Markdown, jusqu'à la section suivante.
sec() { # <fichier> <titre> <sortie>
  awk -v t="## $2" 'index($0, t) == 1 { on = 1; print; next } on && /^## / { exit } on { print }' "$1" > "$3"
}

echo "=== (0) le board synthétique ========================================"
A="$(nouvelle "$TMP" "amont racine | avec barre" "$CH")"
B="$(nouvelle "$TMP" "aval technique de A" "$CH")"
C="$(nouvelle "$TMP" "aval d'un ordre pilote et d'un hors chantier" "$CH")"
D="$(nouvelle "$TMP" "aval d'une close et d'un lien pendant" "$CH")"
Z="$(nouvelle "$TMP" "close satisfaite" "$CH")"
Y="$(nouvelle "$TMP" "close qui attend une ouverte" "$CH")"
E="$(nouvelle "$TMP" "amont hors chantier" "$CH2")"
if [ -n "$A" ] && [ -n "$B" ] && [ -n "$C" ] && [ -n "$D" ] && [ -n "$Z" ] && [ -n "$Y" ] && [ -n "$E" ]; then
  ok "sept ids rendus par new"
else
  ko "new n'a pas rendu d'id : A=$A B=$B C=$C D=$D Z=$Z Y=$Y E=$E"
fi
t depends "$B" "$A" --motif "technique : B consomme ce que A livre"
t depends "$D" "$Z" --motif "technique : Z livre ce que D consomme"
# Parité de lecture avec `tasks.py` : CE motif, il l'accepte en le déclarant
# non canonique (AVERTISSEMENT) ; le moteur doit le classer pareil.
"$PY" "$TASKS" --root "$TMP" depends "$C" "$E" --motif "ORDRE (séquençage de session)" > "$TMP/warn.out" 2>&1
has "$TMP/warn.out" "AVERTISSEMENT" "tasks.py déclare le motif « ORDRE (…) » non canonique"
t done "$Z" --raison "clos par le banc"
t done "$Y" --raison "clos par le banc"
t depends "$Y" "$C" --motif "technique : Y relira C"
SID_ULID="S-01J9ZK3M4N5P6Q7R8S9T0VWXYZ"
"$PY" - "$TMP" "$B" "$C" "$A" "$D" "$SID_ULID" <<'PY'
import json, pathlib, sys
racine, b, c, a, d, sid_ulid = sys.argv[1:7]
p = pathlib.Path(racine) / ".agents/state/board/TASKS.json"
data = json.loads(p.read_text(encoding="utf-8"))
for task in data["tasks"]:
    if task["id"] == c:
        task["depends_on"] = [b] + task.get("depends_on", [])
        task.setdefault("depends_motif", {})[b] = "ORDRE PILOTE S-00000042 : C après B"
    if task["id"] == d:
        task["depends_on"] = task.get("depends_on", []) + [a, "T-99999999"]
        task.setdefault("depends_motif", {})[a] = "ORDRE PILOTE " + sid_ulid + " : D après A"
        task["depends_motif"]["T-99999999"] = "lien pendant"
p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
PY
expect_rc 0 $? "trois arêtes injectées (deux ORDRE PILOTE, un lien pendant)"

echo "=== (a) les sections sont rendues pour un chantier quelconque ======="
f --chantier "$CH" > "$TMP/a.out" 2> "$TMP/a.err"; expect_rc 0 $? "le moteur rend les sections de $CH"
for titre in "Synthèse" "Amonts ouverts" "Arêtes et motifs" "Ordres pilote inscrits en arête" "Vagues" "Cycles"; do
  has "$TMP/a.out" "^## $titre" "la section « $titre » est rendue"
done
has "$TMP/a.out" "\`$CH\`" "le chantier demandé est nommé"
for id in "$A" "$B" "$C" "$D"; do
  has "$TMP/a.out" "$id" "l'ouverte $id est rendue — aucun dictionnaire ne l'a nommée d'avance"
done
has "$TMP/a.out" "amont racine \\\\| avec barre" "un titre portant « | » est échappé : la table reste une table"
f --chantier "$CH" > "$TMP/a2.out" 2>/dev/null
if cmp -s "$TMP/a.out" "$TMP/a2.out"; then ok "deux rendus du même board sont identiques à l'octet"; else ko "le rendu n'est pas déterministe"; fi

echo "=== (b) AMONTS OUVERTS : un amont clos ou pendant n'y est pas ======="
sec "$TMP/a.out" "Amonts ouverts" "$TMP/b.out"
has "$TMP/b.out" "$B.*$A" "B attend A, ouvert"
has "$TMP/b.out" "$C.*$B" "C attend B, ouvert"
has "$TMP/b.out" "$D.*$A" "D attend A, ouvert"
has "$TMP/b.out" "$C.*$E.*hors chantier" "un amont d'un AUTRE chantier est rendu, marqué hors chantier"
has "$TMP/b.out" "$CH2" "le chantier de l'amont hors chantier est nommé"
hasnt "$TMP/b.out" "$Z" "un amont CLOS n'est pas un amont ouvert"
hasnt "$TMP/b.out" "T-99999999" "un lien PENDANT n'est pas un amont ouvert"
if [ "$(grep -c '^| T-' "$TMP/b.out")" = "4" ]; then ok "exactement 4 amonts ouverts"; else ko "attendu 4 rangées d'amonts ouverts"; cat "$TMP/b.out"; fi

echo "=== (c) ARÊTES ET MOTIFS : statut et nature de chaque arête ========="
sec "$TMP/a.out" "Arêtes et motifs" "$TMP/c.out"
has "$TMP/c.out" "$D.*$Z.*satisfaite" "l'arête vers une close est SATISFAITE"
has "$TMP/c.out" "$D.*T-99999999.*pendante" "l'arête vers un id absent est PENDANTE"
has "$TMP/c.out" "$B.*$A.*technique" "un motif quelconque est une dépendance technique"
has "$TMP/c.out" "$C.*$E.*non canonique" "« ORDRE (…) » est lu non canonique, comme tasks.py le lit"
has "$TMP/c.out" "$Y.*$C" "une close qui attend une non close est relevée"
if [ "$(grep -c '^| T-' "$TMP/c.out")" = "7" ]; then ok "6 arêtes des ouvertes + 1 close en attente"; else ko "attendu 7 rangées (6 arêtes + 1 close en attente)"; cat "$TMP/c.out"; fi

echo "=== (d) ORDRES PILOTE : inscrits en arête, par décision ============="
sec "$TMP/a.out" "Ordres pilote inscrits en arête" "$TMP/d.out"
has "$TMP/d.out" "S-00000042.*$C.*$B" "l'ordre pilote à S- numérique nomme sa décision et son arête"
has "$TMP/d.out" "$SID_ULID.*$D.*$A" "l'ordre pilote à S- ULID nomme sa décision et son arête"
has "$TMP/d.out" "2 ordre(s) pilote" "le compte des ordres pilote est rendu"
has "$TMP/d.out" "$C.*$E" "l'arête non canonique est nommée à part, technique"
hasnt "$TMP/d.out" "| S-[0-9A-Z]* | $B" "une arête technique n'est pas un ordre pilote"

echo "=== (e) VAGUES : celles de plan_waves.py, reprises sans recalcul ====="
sec "$TMP/a.out" "Vagues" "$TMP/e.out"
has "$TMP/e.out" "3 vague(s)" "trois vagues (A, E | B, D | C)"
has "$TMP/e.out" "$E.*tirée par $C" "l'amont hors chantier entre par fermeture, nommé"
has "$TMP/e.out" "$A → $B → $C" "le chemin le plus long remonte la chaîne jusqu'à la vague 1"
"$PY" "$ROOT/core-scripts/plan_waves.py" --root "$TMP" waves --chantier "$CH" --json > "$TMP/pw.json" 2>/dev/null
f --chantier "$CH" --json > "$TMP/a.json" 2>/dev/null; expect_rc 0 $? "--json rend rc 0"
"$PY" - "$TMP/a.json" "$TMP/pw.json" <<'PY'
import json, sys
fdr = json.load(open(sys.argv[1], encoding="utf-8"))
pw = json.load(open(sys.argv[2], encoding="utf-8"))
sys.exit(0 if fdr["vagues"] == pw else 1)
PY
expect_rc 0 $? "les vagues du JSON SONT la sortie de plan_waves.py --json, à l'identique"

echo "=== (e2) TIRÉES : une tâche DEMANDÉE n'est jamais comptée « tirée » ==="
# Avant la correction portée par la tâche T-00001249, `plan_waves.close_perimeter`
# rangeait dans `tirees_par` un amont DÉJÀ demandé quand son aval était dépilé avant lui (aval d'id plus petit) — mesuré sur
# le board du kit le 2026-10-09 : 97 des 100 « tirées ». Corrigé à la source (plan_waves
# (v)) ; le filtre du moteur est gardé, inerte, et ce cas tient le rendu des deux côtés.
TI="$TMP/tir"; mkdir -p "$TI"
P1="$(nouvelle "$TI" "aval demandé" "$CH")"
P2="$(nouvelle "$TI" "amont demandé, id plus grand" "$CH")"
P3="$(nouvelle "$TI" "amont hors chantier" "$CH2")"
"$PY" "$TASKS" --root "$TI" depends "$P1" "$P2" "$P3" --motif "technique : P1 consomme P2 et P3" >/dev/null 2>&1
expect_rc 0 $? "deux arêtes posées par tasks.py"
"$PY" "$FDR" --root "$TI" --chantier "$CH" > "$TMP/e2.out" 2>/dev/null; expect_rc 0 $? "rendu du périmètre à amont demandé"
sec "$TMP/e2.out" "Vagues" "$TMP/e2v.out"
has "$TMP/e2v.out" "(2 demandée(s))" "deux demandées"
has "$TMP/e2v.out" "(1 tirée(s) par dépendance)" "une seule tirée : l'amont hors demande"
has "$TMP/e2v.out" "$P2 — .* | demandée |" "l'amont demandé reste « demandée »"
has "$TMP/e2v.out" "$P3 — .*tirée par $P1" "l'amont hors chantier est « tirée par » son aval"
hasnt "$TMP/e2v.out" "$P2 — .*tirée par" "l'amont demandé n'est jamais dit « tirée par »"

echo "=== (f) --json : les comptes dérivés ================================"
"$PY" - "$TMP/a.json" "$A" "$B" "$C" "$D" "$E" "$Y" "$SID_ULID" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
a, b, c, dd, e, y, sid = sys.argv[2:9]
amonts = {(r["aval"], r["amont"]) for r in d["amonts_ouverts"]}
assert amonts == {(b, a), (c, b), (c, e), (dd, a)}, amonts
assert sorted(o["decision"] for o in d["ordres_pilote"]) == sorted(["S-00000042", sid]), d["ordres_pilote"]
assert [(r["aval"], r["amont"]) for r in d["ordres_non_canoniques"]] == [(c, e)], d["ordres_non_canoniques"]
assert [(r["aval"], r["amont"]) for r in d["closes_en_attente"]] == [(y, c)], d["closes_en_attente"]
assert sorted(d["ouvertes"]) == sorted([a, b, c, dd]), d["ouvertes"]
assert d["chantier"] == "zeta-banc"
assert not d["cycles"]
hors = {(r["aval"], r["amont"]): r["hors_chantier"] for r in d["amonts_ouverts"]}
assert hors == {(b, a): False, (c, b): False, (c, e): True, (dd, a): False}, hors
assert [r["amont_chantier"] for r in d["amonts_ouverts"] if r["hors_chantier"]] == ["omega-banc"]
PY
expect_rc 0 $? "amonts, ordres pilote, non canoniques, closes en attente et ouvertes concordent"
has "$TMP/b.out" "4 arête(s) dont l'amont est encore ouvert, dont 1 vers un autre chantier" \
  "le compte des amonts hors chantier est rendu"

echo "=== (g) un AUTRE chantier, même moteur ============================="
f --chantier "$CH2" > "$TMP/g.out" 2>/dev/null; expect_rc 0 $? "le moteur rend aussi $CH2"
has "$TMP/g.out" "\`$CH2\`" "le second chantier est nommé"
has "$TMP/g.out" "$E" "sa tâche est rendue"
hasnt "$TMP/g.out" "$A" "une tâche d'un autre chantier n'y entre pas"

echo "=== (h) chantier inconnu : refus bruyant, jamais une feuille vide ==="
f --chantier "inconnu-banc" > "$TMP/h.out" 2> "$TMP/h.err"; expect_rc 1 $? "un chantier absent du board est refusé"
has "$TMP/h.err" "inconnu-banc" "le refus nomme le chantier demandé"
has "$TMP/h.err" "$CH" "le refus nomme les chantiers présents"
if [ -s "$TMP/h.out" ]; then ko "une feuille a été rendue malgré le refus"; else ok "aucune feuille rendue sur le refus"; fi

echo "=== (i) CYCLE : une section qui nomme le chemin, aucune vague ======="
CY="$TMP/cyc"; mkdir -p "$CY"
X="$(nouvelle "$CY" "X" "$CH")"; W="$(nouvelle "$CY" "W" "$CH")"
"$PY" - "$CY" "$X" "$W" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / ".agents/state/board/TASKS.json"
x_id, w_id = sys.argv[2], sys.argv[3]
data = json.loads(p.read_text(encoding="utf-8"))
for task in data["tasks"]:
    task["depends_on"] = [w_id] if task["id"] == x_id else [x_id]
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
"$PY" "$FDR" --root "$CY" --chantier "$CH" > "$TMP/i.out" 2>&1; expect_rc 0 $? "un cycle est une section, pas un refus"
sec "$TMP/i.out" "Cycles" "$TMP/i2.out"
has "$TMP/i2.out" "$X → $W → $X" "le chemin du cycle est rendu en entier"
has "$TMP/i2.out" "depends .* --retirer" "le remède qui retire UNE arête est nommé"
sec "$TMP/i.out" "Vagues" "$TMP/i3.out"
has "$TMP/i3.out" "aucune vague" "la section des vagues dit qu'il n'y en a pas"
hasnt "$TMP/i3.out" "^| 1 |" "aucune vague partielle n'est rendue"
# Un cycle tenu par des SEULS ordres pilote : un agent n'en retire aucun, la route est
# une SUGGESTION au pilote — jamais le `--retirer` d'une arête technique.
CO="$TMP/cyc-op"; mkdir -p "$CO"
X2="$(nouvelle "$CO" "X2" "$CH")"; W2="$(nouvelle "$CO" "W2" "$CH")"
"$PY" - "$CO" "$X2" "$W2" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / ".agents/state/board/TASKS.json"
x_id, w_id = sys.argv[2], sys.argv[3]
data = json.loads(p.read_text(encoding="utf-8"))
for rang, task in enumerate(data["tasks"], start=1):
    amont = w_id if task["id"] == x_id else x_id
    task["depends_on"] = [amont]
    task["depends_motif"] = {amont: "ORDRE PILOTE S-0000000" + str(rang) + " : ordre du banc"}
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
"$PY" "$FDR" --root "$CO" --chantier "$CH" > "$TMP/i4.out" 2>&1; expect_rc 0 $? "un cycle d'ordres pilote est une section"
sec "$TMP/i4.out" "Cycles" "$TMP/i5.out"
has "$TMP/i5.out" "$X2 → $W2 → $X2" "le chemin du cycle d'ordres pilote est rendu"
has "$TMP/i5.out" "route SUGGESTION" "la route est une SUGGESTION au pilote"
has "$TMP/i5.out" "--retirer-ordre-pilote" "le retrait d'un ordre pilote passe par une décision"
hasnt "$TMP/i5.out" "--retirer T-" "jamais le --retirer d'une arête technique"

echo "=== (j) store malformé : rc 1, jamais une feuille vide =============="
BAD="$TMP/bad"; mkdir -p "$BAD/.agents/state/board"
printf '{' > "$BAD/.agents/state/board/TASKS.json"
"$PY" "$FDR" --root "$BAD" --chantier "$CH" > "$TMP/j.out" 2> "$TMP/j.err"; expect_rc 1 $? "un store illisible sort en 1"
has "$TMP/j.err" "illisible" "la cause est dite"

echo "=== (k) LECTURE SEULE : le moteur n'écrit rien ======================="
# Sur une COPIE neuve du board, jamais rendue avant : une écriture faite par un
# rendu ANTÉRIEUR y serait absente, donc visible. Le moteur et son frère sont COPIÉS
# dans la racine et y tournent, avec `TMPDIR` sur elle : un cache de bytecode
# (`__pycache__/` à côté de `plan_waves.py`), un temporaire ou une écriture au
# répertoire courant y tombent tous.
RO="$TMP/ro"; mkdir -p "$RO/core-scripts"; cp -R "$TMP/.agents" "$RO/.agents"
cp "$FDR" "$ROOT/core-scripts/plan_waves.py" "$RO/core-scripts/"
RO_FDR="$RO/core-scripts/feuille_de_route.py"
( cd "$RO" && find . -type f -print | LC_ALL=C sort | xargs cksum ) > "$TMP/k1" 2>/dev/null
( cd "$RO" && TMPDIR="$RO" "$PY" "$RO_FDR" --root "$RO" --chantier "$CH" > "$TMP/k.md" 2>/dev/null )
( cd "$RO" && TMPDIR="$RO" "$PY" "$RO_FDR" --root "$RO" --chantier "$CH" --json > "$TMP/k.json" 2>/dev/null )
( cd "$RO" && find . -type f -print | LC_ALL=C sort | xargs cksum ) > "$TMP/k2" 2>/dev/null
if [ -s "$TMP/k1" ] && [ -s "$TMP/k.md" ] && cmp -s "$TMP/k1" "$TMP/k2"; then
  ok "aucun fichier créé ni modifié : racine, répertoire courant, temporaire, bytecode"
else
  ko "la racine a changé pendant le rendu (ou rien n'a été rendu)"; diff "$TMP/k1" "$TMP/k2"
fi

echo "=== (l) AUCUN DICTIONNAIRE ÉDITORIAL dans le moteur ================="
"$PY" - "$FDR" <<'PY'
import ast, re, sys
src = open(sys.argv[1], encoding="utf-8").read()
tree = ast.parse(src)
docs = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            docs.add(id(body[0].value))
ident = re.compile(r"\b[TSLP]-(?:\d{3,}|[0-9A-HJKMNP-TV-Z]{26})\b")
court = re.compile(r"\A\d{3,}\Z")
def chaine(n):
    return isinstance(n, ast.Constant) and isinstance(n.value, str)
def rangee(n):
    # une rangée éditoriale : liste ou tuple de constantes, dont au moins une chaîne
    return (isinstance(n, (ast.List, ast.Tuple)) and bool(n.elts)
            and all(isinstance(x, ast.Constant) for x in n.elts) and any(chaine(x) for x in n.elts))
fautes = []
for node in ast.walk(tree):
    if chaine(node) and id(node) not in docs:
        if ident.search(node.value) or court.match(node.value.strip()):
            fautes.append(f"identifiant dans le code : {node.value!r}")
    # à TOUTE profondeur : une table clé chaîne -> chaîne ou rangée de constantes
    if isinstance(node, ast.Dict) and any(k is not None and chaine(k) and (chaine(v) or rangee(v))
                                          for k, v in zip(node.keys, node.values)):
        fautes.append(f"dictionnaire de chaînes constantes, ligne {node.lineno}")
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict"
            and node.keywords and all(isinstance(k.value, ast.Constant) for k in node.keywords)):
        fautes.append(f"dict(...) de mots-clés constants, ligne {node.lineno}")
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        noms = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        for nom in noms:
            if nom.split(".")[0] in ("datetime", "time", "subprocess"):
                fautes.append(f"import {nom} : une horloge ou un sous-processus, ligne {node.lineno}")
for node in tree.body:
    cible = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
    if isinstance(cible, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp)):
        fautes.append(f"dictionnaire ou ensemble littéral de module, ligne {node.lineno}")
    if isinstance(cible, (ast.List, ast.Tuple)):
        if sum(1 for e in cible.elts if chaine(e)) >= 2 or any(rangee(e) for e in cible.elts):
            fautes.append(f"liste ou tuple de chaînes en tête de module, ligne {node.lineno}")
if "refonte-packaging" in src:
    fautes.append("le nom d'un chantier réel est écrit dans le moteur")
for faute in fautes:
    print(faute)
sys.exit(1 if fautes else 0)
PY
expect_rc 0 $? "ni identifiant, ni numéro court, ni table de chaînes, ni horloge, ni chantier réel"

echo "=== (m) amonts RUNNING et BLOCKED, close satisfaite, motif absent, mur ==="
# Le board (a) ne sème que pending/done : la frontière ouvert/satisfaite, les
# ouvertes non pending, les murs et les hors-vagues n'y sont pas exercés.
MR="$TMP/m"; mkdir -p "$MR"
U="$(nouvelle "$MR" "aval de deux amonts actifs" "$CH")"
H="$(nouvelle "$MR" "aval derrière une branche arrêtée" "$CH")"
RU="$(nouvelle "$MR" "amont en cours" "$CH")"
BL="$(nouvelle "$MR" "amont bloqué" "$CH")"
WD="$(nouvelle "$MR" "amont clos" "$CH")"
V="$(nouvelle "$MR" "close à arête satisfaite" "$CH")"
V2="$(nouvelle "$MR" "close qui attend une running" "$CH")"
tm() { "$PY" "$TASKS" --root "$MR" "$@" >/dev/null 2>&1; }
rc_m=0
tm depends "$U" "$RU" --motif "technique : U consomme RU" || rc_m=1
tm depends "$H" "$U" --motif "technique : H consomme U" || rc_m=1
tm done "$WD" --raison "clos par le banc" || rc_m=1
tm done "$V" --raison "clos par le banc" || rc_m=1
tm done "$V2" --raison "clos par le banc" || rc_m=1
tm depends "$V" "$WD" --motif "technique : V relit WD" || rc_m=1
tm depends "$V2" "$RU" --motif "technique : V2 relira RU" || rc_m=1
tm block "$BL" --note "attente decision du banc" || rc_m=1
expect_rc 0 "$rc_m" "le board (m) est construit par tasks.py, geste par geste"
# Deux gestes injectés : l'état `running` (le banc ne joue pas `start`) et une arête
# SANS motif (`depends` l'exige à l'écriture ; le board du kit en porte encore).
"$PY" - "$MR" "$RU" "$U" "$BL" <<'PY'
import json, pathlib, sys
racine, ru, u, bl = sys.argv[1:5]
p = pathlib.Path(racine) / ".agents/state/board/TASKS.json"
data = json.loads(p.read_text(encoding="utf-8"))
for task in data["tasks"]:
    if task["id"] == ru:
        task["state"] = "running"
    if task["id"] == u:
        task["depends_on"] = task.get("depends_on", []) + [bl]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
PY
expect_rc 0 $? "état running et arête sans motif injectés"
"$PY" "$FDR" --root "$MR" --chantier "$CH" > "$TMP/m.out" 2>/dev/null; expect_rc 0 $? "rendu du board (m)"
"$PY" "$FDR" --root "$MR" --chantier "$CH" --json > "$TMP/m.json" 2>/dev/null; expect_rc 0 $? "--json du board (m)"
sec "$TMP/m.out" "Synthèse" "$TMP/m1.out"
has "$TMP/m1.out" "$RU — .*| \`running\` |" "une running est une ouverte"
has "$TMP/m1.out" "$BL — .*| \`blocked\` |" "une blocked est une ouverte"
sec "$TMP/m.out" "Amonts ouverts" "$TMP/m2.out"
has "$TMP/m2.out" "$U — .*$RU — .*| \`running\` | technique |" "un amont RUNNING est un amont ouvert"
has "$TMP/m2.out" "$U — .*$BL — .*| \`blocked\` | motif absent |" \
  "un amont BLOCKED est un amont ouvert, et son arête sans motif dit « motif absent »"
sec "$TMP/m.out" "Arêtes et motifs" "$TMP/m3.out"
has "$TMP/m3.out" "| $V2 — .*$RU — " "une close qui attend une running est relevée"
hasnt "$TMP/m3.out" "| $V — " "une close dont l'arête est satisfaite n'attend rien"
sec "$TMP/m.out" "Vagues" "$TMP/m4.out"
has "$TMP/m4.out" "$RU — .*| tirée par $U |" "l'amont running entre au périmètre, tiré par son aval"
has "$TMP/m4.out" "Murs — 1 branche(s)" "le mur est rendu"
has "$TMP/m4.out" "$U — .* attend $BL — " "le mur nomme l'aval et l'amont bloqué"
has "$TMP/m4.out" "Hors vagues — 2 tâche(s)" "les hors-vagues sont comptées"
has "$TMP/m4.out" "$H — .* dépend de $U — derrière une branche arrêtée" "une hors-vague derrière le mur dit sa raison"
"$PY" - "$TMP/m.json" "$U" "$H" "$RU" "$BL" "$V2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
u, h, ru, bl, v2 = sys.argv[2:7]
assert sorted(d["ouvertes"]) == sorted([u, h, ru, bl]), d["ouvertes"]
amonts = {(r["aval"], r["amont"], r["statut"], r["amont_etat"], r["nature"]) for r in d["amonts_ouverts"]}
assert amonts == {(u, ru, "ouvert", "running", "technique"), (u, bl, "ouvert", "blocked", "motif absent"),
                  (h, u, "ouvert", "pending", "technique")}, amonts
assert [(r["aval"], r["amont"]) for r in d["closes_en_attente"]] == [(v2, ru)], d["closes_en_attente"]
assert d["vagues"]["murs"] == [[u, bl]], d["vagues"]["murs"]
assert sorted(r["tache"] for r in d["vagues"]["hors_vagues"]) == sorted([u, h]), d["vagues"]["hors_vagues"]
assert [r["tache"] for r in d["tirees"]] == [ru], d["tirees"]
PY
expect_rc 0 $? "JSON (m) : ouvertes, amonts actifs, close en attente, mur, hors-vagues, tirée"

echo "=== (n) store malformé dans une arête : refus qui NOMME la tâche porteuse ==="
MF="$TMP/mal"; mkdir -p "$MF"
G="$(nouvelle "$MF" "porteuse d'un id malformé" "$CH")"
G2="$(nouvelle "$MF" "porteuse de motifs illisibles" "$CH")"
"$PY" - "$MF" "$G" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / ".agents/state/board/TASKS.json"
data = json.loads(p.read_text(encoding="utf-8"))
for task in data["tasks"]:
    if task["id"] == sys.argv[2]:
        task["depends_on"] = ["pas-un-id"]
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
"$PY" "$FDR" --root "$MF" --chantier "$CH" > "$TMP/n.out" 2> "$TMP/n.err"; expect_rc 1 $? "un id malformé en arête sort en 1"
has "$TMP/n.err" "$G" "le refus nomme la tâche porteuse"
has "$TMP/n.err" "pas-un-id" "le refus nomme l'id malformé"
if [ -s "$TMP/n.out" ]; then ko "une feuille a été rendue malgré le refus"; else ok "aucune feuille rendue sur l'id malformé"; fi
"$PY" - "$MF" "$G" "$G2" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / ".agents/state/board/TASKS.json"
data = json.loads(p.read_text(encoding="utf-8"))
for task in data["tasks"]:
    if task["id"] == sys.argv[2]:
        task.pop("depends_on", None)
    if task["id"] == sys.argv[3]:
        task["depends_on"] = [sys.argv[2]]
        task["depends_motif"] = ["une liste, pas une table"]
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
"$PY" "$FDR" --root "$MF" --chantier "$CH" > "$TMP/n2.out" 2> "$TMP/n2.err"; expect_rc 1 $? "des motifs qui ne sont pas une table sortent en 1"
has "$TMP/n2.err" "$G2" "le refus nomme la tâche aux motifs illisibles"
hasnt "$TMP/n2.err" "Traceback" "un refus nommé, jamais une trace de pile"

echo "=== (o) usage : --chantier absent ===================================="
f > "$TMP/o.out" 2> "$TMP/o.err"; expect_rc 2 $? "sans --chantier, c'est une erreur d'usage"
has "$TMP/o.err" "--chantier" "l'usage nomme l'option manquante"

echo "=== (p) ids hostiles : un remède collé passe l'id ENTIER, sans l'exécuter ==="
# Un id du board est une DONNÉE. Deux cycles écrits en JSON (aucun `tasks.py` ne les
# écrit) : l'un technique (UN remède `--retirer`), l'autre d'ORDRES PILOTE (DEUX
# commandes : la SUGGESTION `specs.py add`, puis `--retirer-ordre-pilote`). L'oracle
# exige le NOMBRE de commandes, refuse toute expansion vivante (`$` hors guillemets
# simples, `;` `|` `&` nus : `shlex.split` ne modélise pas le `$(…)` d'un `"…"`), puis
# découpe chaque commande par `shlex.split` : un id ENTIER à chaque place, et la
# SUGGESTION en UN argument. Borne : shell POSIX seul, ni PowerShell ni cmd.
# Le troisième id, `o'k>p 9`, porte une apostrophe : il rougit une citation naïve
# `'…'` (indécoupable par `shlex.split`), que les deux premiers laissent verte. Le
# `>` y reste lu entre guillemets ; `vivant()` ne compte pas `<` `>` nus, que le
# gabarit `S-<décision du pilote>` porte à dessein (borne).
PX='x; echo PWN 7'; PW='w$(echo PWN) 8'; PO="o'k>p 9"
cat > "$TMP/p_oracle.py" <<'PY'
import re, shlex, sys
texte = open(sys.argv[1], encoding="utf-8").read()
attendu, x_id, w_id = int(sys.argv[2]), sys.argv[3], sys.argv[4]
ids = {x_id, w_id}
cmds = re.findall(r"`(python \.agents/bin/[^`]*)`", texte)
fautes = [] if len(cmds) == attendu else [f"{len(cmds)} commande(s), {attendu} attendue(s)"]
def vivant(c):
    etat, i = "", 0
    while i < len(c):
        ch = c[i]
        if etat == "'":
            etat = "" if ch == "'" else etat
        elif ch == "\\":
            i += 1
        elif etat == '"':
            if ch == "$":
                return True
            etat = "" if ch == '"' else etat
        elif ch in "'\"":
            etat = ch
        elif ch in "$;|&":
            return True
        i += 1
    return False
def apres(t, opt):
    return t[t.index(opt) + 1] if opt in t[:-1] else None
avals = set()
for c in cmds:
    try:
        t = shlex.split(c)
    except ValueError as exc:
        fautes.append(f"indécoupable ({exc}) : {c}")
        continue
    if vivant(c):
        fautes.append(f"expansion vivante : {c}")
    aval = amont = None
    if t[1] == ".agents/bin/tasks.py" and t[2] == "depends":
        aval = t[3]
        amont = apres(t, "--retirer" if attendu == 1 else "--retirer-ordre-pilote")
    elif t[1] == ".agents/bin/specs.py" and t[2] == "add":
        aval = apres(t, "--task")
        amont = (ids - {aval}).pop() if aval in ids else None
        if apres(t, "delta") != f"SUGGESTION: retirer {aval} <- {amont}":
            fautes.append(f"SUGGESTION coupée : {c}")
    if {aval, amont} != ids:
        fautes.append(f"id coupé ou déplacé : {c}")
    avals.add(aval)
if len(avals) > 1:
    fautes.append(f"les commandes ne retirent pas la même arête : {sorted(map(str, avals))}")
for faute in fautes:
    print(faute)
sys.exit(1 if fautes else 0)
PY
cycle_hostile() { # <étiquette> <id 1> <id 2> — les deux modes, puis les deux oracles
  local tag=$1 i1=$2 i2=$3 mode PR rc_p
  for mode in technique ordre-pilote; do
    PR="$TMP/p-$tag-$mode"; mkdir -p "$PR/.agents/state/board"
    "$PY" - "$PR" "$mode" "$i1" "$i2" "$CH" <<'PY'
import json, pathlib, sys
racine, mode, x_id, w_id, ch = sys.argv[1:6]
taches = []
for rang, (aval, amont) in enumerate(((x_id, w_id), (w_id, x_id)), start=1):
    t = {"id": aval, "task": "id hostile " + str(rang), "state": "pending", "owner": "dev-mono",
         "chantier": ch, "depends_on": [amont], "updated": "2026-10-20"}
    if mode == "ordre-pilote":
        t["depends_motif"] = {amont: "ORDRE PILOTE S-0000000" + str(rang) + " : ordre du banc"}
    taches.append(t)
p = pathlib.Path(racine) / ".agents/state/board/TASKS.json"
p.write_text(json.dumps({"tasks": taches}, indent=2), encoding="utf-8")
PY
    "$PY" "$FDR" --root "$PR" --chantier "$CH" > "$TMP/p-$tag-$mode.out" 2>&1; expect_rc 0 $? "cycle $mode aux ids hostiles ($tag) : rendu"
  done
  "$PY" "$TMP/p_oracle.py" "$TMP/p-$tag-technique.out" 1 "$i1" "$i2" > "$TMP/p1-$tag.w" 2>&1; rc_p=$?
  expect_rc 0 "$rc_p" "cycle technique ($tag) : UNE commande, ids entiers, aucune expansion vivante"
  [ "$rc_p" -eq 0 ] || cat "$TMP/p1-$tag.w"
  "$PY" "$TMP/p_oracle.py" "$TMP/p-$tag-ordre-pilote.out" 2 "$i1" "$i2" > "$TMP/p2-$tag.w" 2>&1; rc_p=$?
  expect_rc 0 "$rc_p" "cycle d'ordres pilote ($tag) : DEUX commandes, ids entiers, SUGGESTION en un argument"
  [ "$rc_p" -eq 0 ] || cat "$TMP/p2-$tag.w"
}
cycle_hostile xw "$PX" "$PW"
cycle_hostile ox "$PO" "$PX"

echo "================================================================"
echo "Resume : $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ]
