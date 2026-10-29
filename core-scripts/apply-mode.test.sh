#!/usr/bin/env bash
# =====================================================================
# apply-mode — banc joue par la porte CI.
#
# `core-scripts/run-bash-tests.sh` decouvre TOUT `*.test.sh` du depot : ce fichier
# est donc joue par `core-scripts/verify.sh` sans aucun cablage a ecrire.
#
# AUCUN FILET pytest N ACCOMPAGNE CE MECANISME, ET C EST DELIBERE (T-00000393).
# La source en portait un ; sa raison d etre chez elle (« la porte bash elague
# .agents/ ») est FAUSSE ici — notre porte joue ce banc directement. Les
# assertions que ce filet portait (comptes par hote, absence de mot-cle
# `probe()`, relations d ordre de la grille) sont TOUTES ici : une garde qui
# n est jouee nulle part ne garde rien.
#
# ---------------------------------------------------------------------
# POURQUOI CE FICHIER EST EXCLU DU GREP D ACCEPTATION `eco|normal`
# ---------------------------------------------------------------------
# Le critere d acceptation de la tache est :
#   grep -rwniE 'eco|normal' core-scripts/apply-mode.py .agents/ref/MODEL_MODES.md
# et il porte sur le MOTEUR et la DOCTRINE, jamais sur ce banc. La raison est
# mecanique : le scenario 12 doit INVOQUER `eco`, `normal` et `pro` pour prouver
# que la ligne de commande les REJETTE. Un banc qui ne peut pas nommer le mot
# rejete ne peut pas prouver le rejet — il ne resterait qu une affirmation.
# Ces trois mots n existent ici que comme ENTREES REFUSEES.
#
# ---------------------------------------------------------------------
# TOUT COMPTE EST RE-DERIVE DE L ARBRE AU MOMENT DU RUN.
# Aucun nombre d agents, de defs, de lignes de grille ou de rang d echelle
# n est ecrit dans ce fichier : un litteral perime en silence.
# =====================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

DEF_DIRS=(.claude/agents .gemini/agents .codex/agents .github/agents .kimi-code/agents)
LEVER_DIRS=(.claude/agents .gemini/agents .codex/agents)
MODE_FILE=".agents/state/local/MODEL_MODE"
DOC=".agents/ref/MODEL_MODES.md"

# `python3` n existe PAS sur toutes les boites de dev de ce depot (mesure :
# absent en Git Bash sous Windows, ou seuls `python` et `py` repondent). Meme
# sonde que `verify.sh` et que les autres bancs du repertoire.
PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "SKIP: aucun interpreteur python sur le PATH — banc non joue (annonce, pas silencieux)"
  exit 0
fi

# ---------------------------------------------------------------------
# PREMIERE verification : refuser de tourner sur un arbre sale, et sortir 0.
#
# Sortir non-zero serait un FAUX ECHEC de la porte : `run-bash-tests.sh` traite
# tout code non nul comme un echec, et avoir des defs modifiees entre un
# `expert` et un commit est un usage legitime du mecanisme.
#
# [C4] MAIS LE SKIP NOMME LES FICHIERS SALES QU IL A VUS. Un residu de `kill`
# — un banc interrompu qui n a pas restaure — produit exactement le meme etat
# qu un usage legitime ; sans la liste, il passerait vert en silence pour
# toujours. Le skip est bruyant par construction.
# ---------------------------------------------------------------------
DIRTY="$(git status --porcelain -- "${DEF_DIRS[@]}" 2>/dev/null)"
if [ -n "$DIRTY" ]; then
  echo "SKIP: defs d agents sales — apply-mode.test.sh exige un arbre propre."
  echo "      Fichiers sales VUS (si vous n avez rien bascule, c est un residu"
  echo "      d interruption : restaurez-les avant de conclure quoi que ce soit) :"
  printf '%s\n' "$DIRTY" | sed 's/^/        /'
  exit 0
fi

# ---------------------------------------------------------------------
# Restauration. [C4] Le trap couvre EXIT, INT et TERM — jamais seulement la fin
# de course : un banc tue au milieu d un `expert` laisserait 100 defs montees.
# Il est INDEPENDANT du script sous test : jamais `apply-mode.py restore`,
# puisque c est justement l artefact mesure.
#
# `MODEL_MODES.md` est restaure depuis une COPIE et non par `git checkout` :
# le fichier peut etre encore non suivi (creation de la meme tache), auquel cas
# `git checkout` ne le restaurerait pas et ne dirait rien.
# ---------------------------------------------------------------------
WORK="$(mktemp -d)"
cp "$DOC" "$WORK/doc.snapshot"
MODE_EXISTED=0
MODE_BEFORE=""
if [ -f "$MODE_FILE" ]; then
  MODE_EXISTED=1
  MODE_BEFORE="$(cat "$MODE_FILE")"
fi

restore_tree() {
  git checkout -- .claude/agents .gemini/agents .codex/agents 2>/dev/null
  git checkout -- .github/agents .kimi-code/agents 2>/dev/null
  [ -f "$WORK/doc.snapshot" ] && cp -f "$WORK/doc.snapshot" "$DOC"
  if [ "$MODE_EXISTED" -eq 1 ]; then
    printf '%s\n' "$MODE_BEFORE" > "$MODE_FILE"
  else
    rm -f "$MODE_FILE"
  fi
  rm -rf "$WORK"
}
trap restore_tree EXIT INT TERM

pass=0
fail=0
ok() { echo "--- PASS $1"; pass=$((pass + 1)); }
ko() { echo "--- FAIL $1"; fail=$((fail + 1)); }

expert() { "$PY" core-scripts/apply-mode.py expert --quiet >/dev/null 2>&1; }
back() { "$PY" core-scripts/apply-mode.py restore --quiet >/dev/null 2>&1; }

lever_dirty() { git status --porcelain -- "${LEVER_DIRS[@]}"; }
all_dirty() { git status --porcelain -- "${DEF_DIRS[@]}"; }

# Chargement du moteur comme module, pour interroger SES tables plutot que de
# les recopier. Repris a l identique par tous les payloads python du banc.
read -r -d '' LOAD_AM <<'PY'
import importlib.util, re, sys
_spec = importlib.util.spec_from_file_location('am', 'core-scripts/apply-mode.py')
am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(am)
PY

# ---------------------------------------------------------------------
echo "=== 1. Non-vacuite, puis aller-retour expert -> restore"
if expert; then
  if [ -z "$(lever_dirty)" ]; then
    ko "expert n a modifie AUCUNE def a levier — le mecanisme ne fait rien (vacuite)"
  else
    ok "non-vacuite : expert a modifie au moins une def a levier"
    if [ ! -f "$MODE_FILE" ]; then
      ko "expert n a pas ecrit le fichier d etat"
    else
      ok "expert a ecrit le fichier d etat en dernier"
    fi
    if back; then
      resid="$(all_dirty)"
      if [ -z "$resid" ] && [ ! -f "$MODE_FILE" ]; then
        ok "aller-retour expert -> restore : diff VIDE sur les 5 repertoires, etat ABSENT"
      else
        echo "    diff residuel :"
        printf '%s\n' "$resid" | head -10
        [ -f "$MODE_FILE" ] && echo "    fichier d etat encore present : $MODE_FILE"
        ko "aller-retour expert -> restore laisse un diff ou un fichier d etat"
      fi
    else
      ko "restore a echoue"
    fi
  fi
else
  ko "expert a echoue"
fi

# ---------------------------------------------------------------------
echo "=== 2. orchestrator (claude) jamais reecrit"
expert
if git diff --quiet -- .claude/agents/orchestrator.md; then
  ok "claude/orchestrator intact en expert (exclusion heritee L-00000068)"
else
  ko "claude/orchestrator a ete reecrit alors qu il est exclu a demeure"
fi
back

# ---------------------------------------------------------------------
echo "=== 3. Axes EPINGLES : une valeur hors echelle fermee n est jamais reecrite"
# Les axes epingles sont DECOUVERTS (valeur de reference hors de SCALES), jamais
# nommes : si une def sort de l echelle demain, elle est couverte d office.
expert
pin_out="$("$PY" - <<PY
$LOAD_AM
grid = am.load_grid()
pinned = [k for k, v in grid.items() if v[am.BASELINE] not in am.SCALES[(k[0], k[2])]]
print("PINNED=%d" % len(pinned))
for host, agent, axis in sorted(pinned):
    v = grid[(host, agent, axis)]
    if v[am.EXPERT] != v[am.BASELINE]:
        print("BAD grille: %s/%s.%s derive un axe epingle" % (host, agent, axis))
    disk = am.read_axis(host, agent, axis)
    if disk != v[am.BASELINE]:
        print("BAD disque: %s/%s.%s reecrit en expert (%r)" % (host, agent, axis, disk))
PY
)"
back
pin_n="$(printf '%s\n' "$pin_out" | sed -n 's/^PINNED=//p')"
pin_bad="$(printf '%s\n' "$pin_out" | grep -c '^BAD ')"
if [ "${pin_n:-0}" -eq 0 ]; then
  ko "aucun axe epingle trouve — la garde ne garde rien (vacuite), ou l arbre a change"
elif [ "$pin_bad" -ne 0 ]; then
  printf '%s\n' "$pin_out" | grep '^BAD ' | sed 's/^/    /'
  ko "un axe epingle a ete derive ou reecrit"
else
  ok "$pin_n axe(s) epingle(s) : ni derive(s) dans la grille, ni reecrit(s) sur disque"
fi

# ---------------------------------------------------------------------
echo "=== 4. Jeton indicatif : unique et a jour en expert, ABSENT apres restore"
# T-012 — LA LISTE DES DEFS NON JETONNEES EST DERIVEE, PLUS RECOPIEE. Elle
# valait `communicator*` en dur, ce qui etait exact tant que le gel etait la
# seule raison de ne pas jetonner. Le binome de cloture en ajoute une seconde :
# il est EXCLU du levier sur les cinq hotes, donc il ne recoit aucun jeton non
# plus. Recopier une exclusion la fait diverger au premier ajout — c'est
# exactement ce qui a rougi ici. La source est `apply-mode.py`, et elle seule.
token_ok=1
SKIP_JETON="$("$PY" -c 'import importlib.util as u; s=u.spec_from_file_location("m","core-scripts/apply-mode.py"); m=u.module_from_spec(s); s.loader.exec_module(m); print(" ".join(sorted({a for h,a in m.EXCLUDED if h in m.INDICATIVE_HOSTS} | set(m.FROZEN))))')"
if [ -z "$SKIP_JETON" ]; then
  echo "    liste des defs non jetonnees VIDE — la derivation a echoue, ce test ne prouverait rien"
  token_ok=0
fi
expert
for f in .github/agents/* .kimi-code/agents/*; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  base="${base%%.*}"
  case " $SKIP_JETON " in
    *" $base "*)
      continue
      ;;
  esac
  n="$(grep -c 'MODEL-MODE:' "$f")"
  if [ "$n" -ne 1 ]; then
    echo "    $f porte $n jeton(s) MODEL-MODE (attendu 1)"
    token_ok=0
  fi
  if ! grep -q 'MODEL-MODE: expert ' "$f"; then
    echo "    $f ne declare pas le mode expert"
    token_ok=0
  fi
done
back
for f in .github/agents/* .kimi-code/agents/*; do
  [ -f "$f" ] || continue
  if grep -q 'MODEL-MODE:' "$f"; then
    echo "    $f porte encore un jeton apres restore"
    token_ok=0
  fi
done
[ "$token_ok" -eq 1 ] \
  && ok "jeton indicatif : un seul, a jour en expert, retire par restore" \
  || ko "jeton indicatif duplique, desynchronise, ou non retire"

# ---------------------------------------------------------------------
echo "=== 5. communicator exclu / gele sur les 5 hotes"
comm_ok=1
expert
for f in .github/agents/communicator.agent.md .kimi-code/agents/communicator.md; do
  if grep -q 'MODEL-MODE:' "$f"; then
    echo "    $f porte un jeton alors que communicator est exclu"
    comm_ok=0
  fi
done
for f in .claude/agents/communicator.md .gemini/agents/communicator.md \
         .codex/agents/communicator.toml; do
  if ! git diff --quiet -- "$f"; then
    echo "    $f a ete modifie alors que communicator est gele"
    comm_ok=0
  fi
done
back
[ "$comm_ok" -eq 1 ] \
  && ok "communicator : gele sur les 3 hotes a levier, sans jeton sur les 2 indicatifs" \
  || ko "communicator n est pas exclu comme annonce"

# ---------------------------------------------------------------------
echo "=== 6. Insertion sur le frontmatter a fermeture la plus TARDIVE (kimi)"
# La def temoin est DECOUVERTE (fermeture la plus basse), jamais nommee : une
# ligne fixe casserait ici, et un nom fixe perimerait au premier remaniement.
LATE=""
LATE_N=0
for f in .kimi-code/agents/*.md; do
  [ -f "$f" ] || continue
  case "$(basename "$f")" in
    communicator*) continue ;;
  esac
  n="$(grep -n '^---[[:space:]]*$' "$f" | sed -n 2p | cut -d: -f1)"
  [ -n "$n" ] || continue
  if [ "$n" -gt "$LATE_N" ]; then LATE_N="$n"; LATE="$f"; fi
done
if [ -z "$LATE" ]; then
  ko "aucune def kimi avec frontmatter referme — temoin introuvable (vacuite)"
else
  expert
  tok_line="$(grep -n 'MODEL-MODE:' "$LATE" | head -1 | cut -d: -f1)"
  back
  if [ "$tok_line" = "$((LATE_N + 1))" ]; then
    ok "insertion dynamique : $LATE ferme ligne $LATE_N, jeton ligne $tok_line"
  else
    ko "insertion dynamique : $LATE jeton ligne ${tok_line:-absent}, attendu $((LATE_N + 1))"
  fi
fi

# ---------------------------------------------------------------------
echo "=== 7. Comptes de defs par hote : RE-DERIVES du disque"
# Deuxieme implementation, volontairement independante de `managed_agents()` :
# elle relit les fichiers et applique la regle de doctrine (une def a levier
# compte si elle porte une cle de tier ; un hote indicatif compte tout sauf le
# gel), puis confronte le resultat A LA FOIS a `managed_agents()` et au seul
# litteral du moteur, `EXPECTED_TOUCHED`. C est ce litteral qui perime.
counts_out="$("$PY" - <<PY
$LOAD_AM
KEY = {
    'claude': re.compile(r'^(model|effort):', re.M),
    'gemini': re.compile(r'^(model|effort):', re.M),
    'codex': re.compile(r'^model_reasoning_effort\s*=', re.M),
}
for host in list(am.LEVER_HOSTS) + list(am.INDICATIVE_HOSTS):
    lever = host in am.LEVER_HOSTS
    directory, pattern = (am.LEVER_HOSTS[host][:2] if lever
                          else am.INDICATIVE_HOSTS[host])
    suffix = pattern.replace('{agent}', '')
    names = sorted(p.name[:-len(suffix)] for p in (am.ROOT / directory).iterdir()
                   if p.is_file() and p.name.endswith(suffix))
    kept = 0
    for agent in names:
        if (host, agent) in am.EXCLUDED:
            continue
        if lever:
            head = '\n'.join((am.ROOT / directory / (agent + suffix))
                             .read_text(encoding='utf-8').split('\n')[:40])
            if not KEY[host].search(head):
                continue
        elif agent in am.FROZEN:
            continue
        kept += 1
    got = len(am.managed_agents(host))
    exp = am.EXPECTED_TOUCHED[host]
    print('INFO %-7s fichiers=%d re-derive=%d managed_agents=%d EXPECTED_TOUCHED=%d'
          % (host, len(names), kept, got, exp))
    if kept != got:
        print('BAD %s: re-derive=%d mais managed_agents()=%d' % (host, kept, got))
    if kept != exp:
        print('BAD %s: EXPECTED_TOUCHED=%d PERIME (disque=%d) — remesurez-le'
              % (host, exp, kept))
PY
)"
printf '%s\n' "$counts_out" | grep '^INFO ' | sed 's/^INFO /    /'
if printf '%s\n' "$counts_out" | grep -q '^BAD '; then
  printf '%s\n' "$counts_out" | grep '^BAD ' | sed 's/^/    /'
  ko "compte de defs divergent entre le disque, managed_agents() et EXPECTED_TOUCHED"
else
  ok "comptes par hote re-derives du disque == managed_agents() == EXPECTED_TOUCHED"
fi

# ---------------------------------------------------------------------
echo "=== 8. Jeton indicatif : aucun mot-cle probe(), aucune cle de tier"
# La liste de mots-cles n est JAMAIS recopiee : `probe()` est appelee par
# INTROSPECTION, de sorte qu un mot-cle ajoute en amont soit couvert d office.
# Le heredoc ne sert PLUS de condition à `if` : `if <cmd> <<MOT` est du bash
# valide que tree-sitter-bash ne parse pas, et un seul site retire ce fichier
# ENTIER du compte des cibles inspectées par la porte SAST. Le statut est relevé
# juste après — même exécution, même verdict.
"$PY" - <<PY
$LOAD_AM
_g = importlib.util.spec_from_file_location('gt', '.agents/evals/test_golden_transcripts.py')
gt = importlib.util.module_from_spec(_g)
_g.loader.exec_module(gt)
line = am.render_token(am.EXPERT)
hit = sorted(k for k, v in gt.probe(line).items() if v)
bad = list(hit)
if am.FORBIDDEN_IN_TOKEN.match(line):
    bad.append('cle-de-tier')
if bad:
    print('SONDES DECLENCHEES: %s' % bad, file=sys.stderr)
    sys.exit(1)
PY
_rc_jeton=$?
if [ "$_rc_jeton" -eq 0 ]; then
  ok "jeton indicatif : aucune sonde probe() declenchee, aucune cle de tier"
else
  ko "le jeton indicatif declenche une sonde golden ou porte une cle de tier"
fi

# ---------------------------------------------------------------------
echo "=== 9. Garde de derive FERMANTE sur expert : refus, aucun octet ecrit"
back
"$PY" - <<PY >/dev/null 2>&1
$LOAD_AM
cur = am.read_axis('claude', 'analyzer', 'model')
scale = am.SCALES[('claude', 'model')]
other = scale[0] if cur != scale[0] else scale[1]
am.write_axis('claude', 'analyzer', 'model', other)
PY
"$PY" core-scripts/apply-mode.py expert --quiet >/dev/null 2>&1
rc=$?
dirty_n="$(lever_dirty | wc -l | tr -d ' ')"
mode_after=0
[ -f "$MODE_FILE" ] && mode_after=1
git checkout -- .claude/agents 2>/dev/null
if [ "$rc" -eq 2 ] && [ "$dirty_n" = "1" ] && [ "$mode_after" -eq 0 ]; then
  ok "derive detectee : code $rc, aucun octet ecrit hors la derive injectee, etat non ecrit"
else
  ko "garde de derive : code $rc (attendu 2), $dirty_n def(s) sale(s) (attendu 1), etat=$mode_after (attendu 0)"
fi

echo "=== 9b. La garde ne se declenche PAS sur restore (restore EST la reparation)"
"$PY" - <<PY >/dev/null 2>&1
$LOAD_AM
cur = am.read_axis('claude', 'analyzer', 'model')
scale = am.SCALES[('claude', 'model')]
other = scale[0] if cur != scale[0] else scale[1]
am.write_axis('claude', 'analyzer', 'model', other)
PY
"$PY" core-scripts/apply-mode.py restore --quiet >/dev/null 2>&1
rc=$?
resid="$(all_dirty)"
if [ "$rc" -eq 0 ] && [ -z "$resid" ]; then
  ok "restore repare un arbre derive (code 0, arbre revenu a sa reference)"
else
  echo "    code $rc, residuel :"; printf '%s\n' "$resid" | head -5
  ko "restore ne repare pas un arbre derive"
fi
git checkout -- "${DEF_DIRS[@]}" 2>/dev/null

# ---------------------------------------------------------------------
echo "=== 10. [C3] --recapture REFUSE quand un mode est enregistre"
cp "$DOC" "$WORK/doc.before_c3"
expert
c3_msg="$("$PY" core-scripts/apply-mode.py restore --recapture 2>&1)"
rc=$?
if [ "$rc" -eq 2 ] && cmp -s "$DOC" "$WORK/doc.before_c3"; then
  if printf '%s' "$c3_msg" | grep -q 'REM' && printf '%s' "$c3_msg" | grep -q 'restore'; then
    ok "recapture refusee : code 2, $DOC inchange a l octet, remede nomme"
  else
    echo "    message : $c3_msg"
    ko "recapture refusee mais le message ne nomme pas le remede"
  fi
else
  echo "    code $rc ; $DOC modifie : $(cmp -s "$DOC" "$WORK/doc.before_c3" && echo non || echo OUI)"
  ko "[C3] recapture acceptee alors qu un mode est enregistre"
fi
cp -f "$WORK/doc.before_c3" "$DOC"
back

echo "=== 10b. --recapture n est pas accepte avec expert"
"$PY" core-scripts/apply-mode.py expert --recapture >/dev/null 2>&1
rc=$?
if [ "$rc" -ne 0 ] && [ -z "$(all_dirty)" ] && [ ! -f "$MODE_FILE" ]; then
  ok "expert --recapture refuse (code $rc), aucun octet ecrit"
else
  ko "expert --recapture : code $rc, ou des octets ont ete ecrits"
fi

# ---------------------------------------------------------------------
echo "=== 11. status : 0 a l etat de reference, 1 sur derive"
back
"$PY" core-scripts/apply-mode.py status >/dev/null 2>&1
rc_ref=$?
"$PY" - <<PY >/dev/null 2>&1
$LOAD_AM
cur = am.read_axis('claude', 'analyzer', 'effort')
scale = am.SCALES[('claude', 'effort')]
other = scale[0] if cur != scale[0] else scale[1]
am.write_axis('claude', 'analyzer', 'effort', other)
PY
"$PY" core-scripts/apply-mode.py status >/dev/null 2>&1
rc_drift=$?
git checkout -- .claude/agents 2>/dev/null
if [ "$rc_ref" -eq 0 ] && [ "$rc_drift" -eq 1 ]; then
  ok "status : code 0 a l etat de reference, code 1 sur derive"
else
  ko "status : reference=$rc_ref (attendu 0), derive=$rc_drift (attendu 1)"
fi

# ---------------------------------------------------------------------
echo "=== 12. Les modes descendants de la source sont REJETES par la CLI"
# Ce banc DOIT nommer les mots rejetes pour prouver le rejet — voir l en-tete.
reject_ok=1
for bad_mode in eco normal pro; do
  out="$("$PY" core-scripts/apply-mode.py "$bad_mode" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "    '$bad_mode' ACCEPTE (code 0) — le mecanisme ne devrait pas le connaitre"
    reject_ok=0
  fi
  if ! printf '%s' "$out" | grep -q "invalid choice"; then
    echo "    '$bad_mode' rejete (code $rc) mais sans erreur de choix argparse"
    reject_ok=0
  fi
done
if [ -n "$(all_dirty)" ] || [ -f "$MODE_FILE" ]; then
  echo "    des octets ont ete ecrits par un mode refuse"
  reject_ok=0
fi
[ "$reject_ok" -eq 1 ] \
  && ok "eco / normal / pro rejetes par la CLI, aucun octet ecrit" \
  || ko "un mode descendant n est pas rejete proprement"

# ---------------------------------------------------------------------
echo "=== 13. [C5] La colonne expert : plan-critic par axe, exec-critic par DOMINANCE"
# Rangs RE-DERIVES des echelles du moteur, jamais des litteraux. Le filet joue
# donc en CI sur la grille COMMITTEE, pas seulement au moment d une bascule.
c5_out="$("$PY" - <<PY
$LOAD_AM
grid = am.load_grid()
DEV = ('dev-mono', 'dev-multi')

def rank(host, axis, value):
    scale = am.SCALES[(host, axis)]
    if value in scale:
        return scale.index(value)
    # Axe epingle : id complet portant le palier comme UN TOKEN (jamais une
    # sous-chaine — 'opus' dans 'claude-opus-4-8' matche, 'opusculum' non).
    tokens = set(re.split(r'[-_.]', value))
    hits = [i for i, name in enumerate(scale) if name in tokens]
    if len(hits) == 1:
        return hits[0]
    print('BAD %s/%s: valeur %r inclassable (%d palier(s))' % (host, axis, value, len(hits)))
    return None

def col(host, agent, axis):
    key = (host, agent, axis)
    if key not in grid:
        print('BAD grille sans %s/%s.%s' % (host, agent, axis))
        return None
    return grid[key][am.EXPERT]

seen = 0

# (a) plan-critic >= planner : PAR AXE, relation stricte conservee. Aucun
#     echange n y est demande, et un garde qui tient au niveau strict ne se
#     desserre pas par symetrie.
for host, spec in am.LEVER_HOSTS.items():
    for axis in spec[2]:
        sv, wv = col(host, 'plan-critic', axis), col(host, 'planner', axis)
        if sv is None or wv is None:
            continue
        sr, wr = rank(host, axis, sv), rank(host, axis, wv)
        if sr is None or wr is None:
            continue
        seen += 1
        if sr < wr or (axis == 'effort' and sr == wr):
            print('BAD %s/%s: plan-critic=%s (rang %d) SOUS planner=%s (rang %d)'
                  % (host, axis, sv, sr, wv, wr))

# (b) exec-critic vs dev-* : DOMINANCE, jamais axe par axe — miroir exact de
#     test_exec_critic_is_never_dominated_by_a_dev_agent. Est refuse le seul
#     cas ou le dev est >= sur TOUS les axes portes par l hote et > sur au
#     moins un. Un hote a un seul axe (codex) retombe sur cet axe : il n y a
#     rien a echanger. Comparer axe par axe interdirait tout ECHANGE, ce qui
#     est plus strict que la regle enoncee, et ferait passer un critique d une
#     generation de modele au-dessus pour « plus faible ».
for host, spec in am.LEVER_HOSTS.items():
    axes = list(spec[2])
    for dev in DEV:
        mine, theirs, usable = [], [], True
        for axis in axes:
            sv, wv = col(host, 'exec-critic', axis), col(host, dev, axis)
            if sv is None or wv is None:
                usable = False
                break
            sr, wr = rank(host, axis, sv), rank(host, axis, wv)
            if sr is None or wr is None:
                usable = False
                break
            mine.append(sr)
            theirs.append(wr)
        if not usable:
            continue
        seen += 1
        if (all(t >= m for t, m in zip(theirs, mine))
                and any(t > m for t, m in zip(theirs, mine))):
            print('BAD %s: %s DOMINE exec-critic sur les axes %s — critique %s, dev %s'
                  % (host, dev, ','.join(axes), mine, theirs))

# (c) design-review >= frontend-fidelity : PAR AXE (S-01M558S8VVRGHACABYMWB2C6EM),
#     sous-ensemble expert de test_design_review_at_or_above_frontend_fidelity_on_every_axis
#     (gemini/model compté, codex/model absent : LEVER_HOSTS codex = effort seul).
for host, spec in am.LEVER_HOSTS.items():
    for axis in spec[2]:
        sv, wv = col(host, 'design-review', axis), col(host, 'frontend-fidelity', axis)
        if sv is None or wv is None:
            continue
        sr, wr = rank(host, axis, sv), rank(host, axis, wv)
        if sr is None or wr is None:
            continue
        seen += 1
        if sr < wr:
            print('BAD %s/%s: design-review=%s (rang %d) SOUS frontend-fidelity=%s (rang %d)'
                  % (host, axis, sv, sr, wv, wr))

expected = (2 * sum(len(s[2]) for s in am.LEVER_HOSTS.values())
            + len(am.LEVER_HOSTS) * len(DEV))
print('SEEN=%d EXPECTED=%d' % (seen, expected))
PY
)"
c5_seen="$(printf '%s\n' "$c5_out" | sed -n 's/^SEEN=\([0-9]*\) .*/\1/p')"
c5_exp="$(printf '%s\n' "$c5_out" | sed -n 's/^SEEN=[0-9]* EXPECTED=//p')"
if printf '%s\n' "$c5_out" | grep -q '^BAD '; then
  printf '%s\n' "$c5_out" | grep '^BAD ' | sed 's/^/    /'
  ko "[C5] une relation d ordre est rompue dans la colonne expert"
elif [ "${c5_seen:-0}" -ne "${c5_exp:-1}" ]; then
  ko "[C5] population comparee $c5_seen != population declaree $c5_exp (vacuite)"
else
  ok "[C5] colonne expert : plan-critic >= planner par axe, exec-critic jamais DOMINE, design-review >= frontend-fidelity par axe ($c5_seen comparaisons)"
fi

# ---------------------------------------------------------------------
echo "=== 14. host_sync.test.sh vert apres les bascules"
back
if bash core-scripts/host_sync.test.sh >"$WORK/host_sync.log" 2>&1; then
  ok "host_sync.test.sh vert apres les bascules de mode"
else
  tail -20 "$WORK/host_sync.log"
  ko "host_sync.test.sh rouge apres les bascules de mode"
fi

# ---------------------------------------------------------------------
echo "=== 15. Etat final : l arbre est revenu a sa reference"
resid="$(all_dirty)"
if [ -z "$resid" ] && [ ! -f "$MODE_FILE" ] && cmp -s "$DOC" "$WORK/doc.snapshot"; then
  ok "arbre, jetons, fichier d etat et grille revenus a leur etat d entree"
else
  printf '%s\n' "$resid" | head -10
  ko "le banc laisse un residu (le trap va le nettoyer, mais c est un defaut)"
fi

echo
echo "===================================================================="
echo "apply-mode.test.sh : $pass passe(s), $fail echec(s)"
echo "===================================================================="
[ "$fail" -eq 0 ]
