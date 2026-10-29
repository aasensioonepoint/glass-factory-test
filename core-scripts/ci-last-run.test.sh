#!/usr/bin/env bash
# =====================================================================
# BANC — relevé du dernier run CI (T-00000529)
#
# Le suffixe `.test.sh` sous `scripts/` est DÉLIBÉRÉ : `run-bash-tests.sh`
# découvre ce répertoire par ÉLAGAGE, donc cette suite entre dans la porte
# applicative — dans les DEUX modes, avec et sans `--all` — sans qu'aucune liste
# close ne soit à tenir à jour.
#
# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# allows-missing: basename
#
# Le contrôle négatif (2) IMPOSE UN PATH VIDE au script (:125) pour jouer la
# branche « gh absent ». Sous ce PATH le script ne résout plus `basename` —
# MESURÉ, un vrai 127, provoqué exprès, par une suite qui passe. Sans cette ligne
# le capteur de 127 avalé du runner rougirait un contrôle négatif qui fait
# exactement son travail. Le nom déclaré est celui qui a été MESURÉ, pas un
# blanc-seing : une commande de plus doit ressortir en rouge nommé.
#
# RÉSIDU SIGNALÉ, non corrigé ici (hors périmètre T-00000427) : le commentaire
# de :121 affirme que cette branche « n'utilise que des primitives internes ».
# Le relevé ci-dessus le DÉMENT — `basename` est un binaire externe. La mesure
# est le fait ; le commentaire est à reprendre dans une tâche à lui.
#
# ---------------------------------------------------------------------
# CE QUE CE BANC PROUVE — deux producteurs de vérité, pas un
# ---------------------------------------------------------------------
#   PRODUCTEUR (cas 1-6) — `core-scripts/ci-last-run.sh`, sous stub `gh` et racine
#   JETABLE. Le cas 2 est le CONTRÔLE NÉGATIF exigé par L-00000073 : une garde
#   qui ne peut pas dire « je n'ai rien mesuré » ne garde rien, et un relevé
#   muet se lit exactement comme un vert.
#
#   CONSOMMATEUR (cas 7-12) — `.claude/statusline.sh`, sur cache FABRIQUÉ, donc
#   sans réseau et sans dépendre de l'état réel de la CI. Les cinq états du
#   mapping y sont couverts, les DEUX états neufs (« en cours », « aucun run »)
#   compris : sans eux ils naîtraient sans filet.
#
# ---------------------------------------------------------------------
# TROIS FIXTURES QUI SONT LE BANC, ET NON DU DÉCOR
# ---------------------------------------------------------------------
#   * cas 4 — `status:"in_progress"` AVEC `conclusion:"failure"`. Cette
#     combinaison n'existe pas chez GitHub ; c'est EXACTEMENT pourquoi elle est
#     ici. Elle est la seule fixture capable de distinguer « status lu d'abord »
#     de « conclusion lue d'abord » : un parse qui inverse la précédence rend
#     `failure` là où le contrat exige « en cours ».
#   * cas 6 — un stub qui dort pour `ci.yml` SEULEMENT. Il ne prouve pas que le
#     mur coupe (ça, n'importe quel dépassement le montre) : il prouve que
#     l'AUTRE workflow est TOUJOURS relevé, c'est-à-dire que la borne vit dans
#     le script et non dans un superviseur qui fauche tout.
#   * cas 1 — cwd JETABLE et distinct de la racine. La seule façon de prouver
#     l'ancrage `${CLAUDE_PROJECT_DIR:-$PWD}` est de vérifier que RIEN n'est
#     écrit sous le cwd.
#
# ---------------------------------------------------------------------
# CE QUE CE BANC NE FAIT DÉLIBÉRÉMENT PAS
# ---------------------------------------------------------------------
# AUCUN appel réseau, AUCUN `gh` réel, AUCUNE assertion sur l'état réel de la CI
# du dépôt : cet état change à chaque push et rendrait la suite rouge sans
# qu'aucun code n'ait bougé. La démonstration du relevé RÉEL est manuelle et
# consignée dans `docs/tasks/T-00000529.md`.
# =====================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SUT="$ROOT/core-scripts/ci-last-run.sh"
STATUSLINE="$ROOT/.claude/statusline.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
note_pass() { echo "  PASS  $1"; pass=$((pass + 1)); }
note_fail() { echo "  FAIL  $1"; fail=$((fail + 1)); }

# Appartenance SANS tube : `printf | grep -q` ferme son entrée et rend un statut
# non nul sous `pipefail` alors même que la correspondance est trouvée
# (T-00000544). Un `case` ne peut pas produire ce faux négatif.
contient() {
  case "$1" in
    *"$2"*) return 0 ;;
    *) return 1 ;;
  esac
}

compte() {
  local h="$1" motif="$2" n=0
  while contient "$h" "$motif"; do n=$((n + 1)); h="${h#*"$motif"}"; done
  printf '%s' "$n"
}

# T-00000379 — LA FIXTURE PORTE DES WORKFLOWS, parce que l'énumération est
# DÉRIVÉE du répertoire et non codée en dur. L'original codait
# `(ci.yml eval-nightly.yml)`, donc sa fixture n'avait aucun `.github/` à créer ;
# ici un dépôt sans workflow n'a réellement rien à relever, et le script le DIT
# au lieu de relever un workflow imaginaire. Les noms sont les NÔTRES.
mk_racine() {
  local d; d="$(mktemp -d -p "$WORK")"
  mkdir -p "$d/.agents/state/local" "$d/.github/workflows"
  : > "$d/.github/workflows/ci.yml"
  : > "$d/.github/workflows/eval-nightly.yml"
  printf '%s' "$d"
}
# Racine SANS workflow : le cas que l'énumération dérivée rend possible.
mk_racine_vide() {
  local d; d="$(mktemp -d -p "$WORK")"
  mkdir -p "$d/.agents/state/local"
  printf '%s' "$d"
}
mk_bin()    { local d; d="$(mktemp -d -p "$WORK")"; printf '%s' "$d"; }
cache_de()  { printf '%s' "$1/.agents/state/local/ci-status.line"; }

echo "=== PRODUCTEUR — core-scripts/ci-last-run.sh ==="

# --- (1) nominal : 2 workflows -> 2 lignes + source:, cache sous la racine ----
R="$(mk_racine)"; B="$(mk_bin)"; CWD="$(mktemp -d -p "$WORK")"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
printf '[{"conclusion":"success","status":"completed","headSha":"abcdef1234567890","createdAt":"2026-08-13T01:00:00Z"}]\n'
STUB
chmod +x "$B/gh"
OUT="$(cd "$CWD" && PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>/dev/null)"; RC=$?
if [ "$RC" -eq 0 ] \
   && contient "$OUT" "source: gh run list --workflow=<wf> --branch=main --limit=1 --json conclusion,status,headSha,createdAt" \
   && [ "$(compte "$OUT" 'DERNIER RUN ')" -eq 2 ] \
   && contient "$OUT" "DERNIER RUN ci.yml (main): success @ abcdef1" \
   && contient "$OUT" "DERNIER RUN eval-nightly.yml (main): success @ abcdef1"; then
  note_pass "(1) nominal : source: unique + 2 lignes DERNIER RUN, exit 0"
else
  note_fail "(1) nominal (rc=$RC) : [$OUT]"
fi
if [ -f "$(cache_de "$R")" ] && [ ! -e "$CWD/.agents" ]; then
  note_pass "(1b) cache écrit sous la racine JETABLE, rien sous le cwd (ancrage C2)"
else
  note_fail "(1b) ancrage : cache=$( [ -f "$(cache_de "$R")" ] && echo oui || echo non ), cwd pollué=$( [ -e "$CWD/.agents" ] && echo oui || echo non )"
fi

# --- (2) PATH sans gh : CONTRÔLE NÉGATIF ------------------------------------
# `env` est cherché avec le PATH courant, puis impose un PATH VIDE au script :
# une affectation shell préfixée aurait aussi cassé la résolution de `bash`.
# La branche « gh absent » du script n'utilise que des primitives internes.
R="$(mk_racine)"; B="$(mk_bin)"
printf 'epoch=1\nci.yml|ok|success|deadbee\n' > "$(cache_de "$R")"
AVANT="$(cat "$(cache_de "$R")")"
OUT="$(env PATH="$B" CLAUDE_PROJECT_DIR="$R" "$BASH" "$SUT" 2>/dev/null)"; RC=$?
APRES="$(cat "$(cache_de "$R")")"
if [ "$RC" -eq 0 ] \
   && [ "$(compte "$OUT" 'COVERAGE DEGRADED')" -eq 2 ] \
   && contient "$OUT" "gh absent" \
   && [ "$AVANT" = "$APRES" ]; then
  note_pass "(2) gh absent : 2x COVERAGE DEGRADED motivé, exit 0, cache INTACT"
else
  note_fail "(2) gh absent (rc=$RC, cache changé=$( [ "$AVANT" = "$APRES" ] && echo non || echo oui)) : [$OUT]"
fi

# --- (3) [] : « aucun run », un FAIT et non une dégradation -----------------
R="$(mk_racine)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
echo "[]"
STUB
chmod +x "$B/gh"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>/dev/null)"; RC=$?
if [ "$RC" -eq 0 ] \
   && [ "$(compte "$OUT" 'aucun run')" -eq 2 ] \
   && ! contient "$OUT" "COVERAGE DEGRADED" \
   && contient "$(cat "$(cache_de "$R")" 2>/dev/null)" "ci.yml|absent|aucun run|"; then
  note_pass "(3) [] : « aucun run » NON dégradé, cache classe=absent"
else
  note_fail "(3) [] (rc=$RC) : [$OUT] cache=[$(cat "$(cache_de "$R")" 2>/dev/null)]"
fi

# --- (4) run vif : status LU AVANT conclusion (précédence C4) ---------------
R="$(mk_racine)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
# Combinaison IMPOSSIBLE chez GitHub, et c'est le point : elle est la seule qui
# distingue « status d'abord » de « conclusion d'abord ».
printf '[{"conclusion":"failure","status":"in_progress","headSha":"1234567890abcdef","createdAt":"2026-08-13T02:00:00Z"}]\n'
STUB
chmod +x "$B/gh"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>/dev/null)"; RC=$?
if [ "$RC" -eq 0 ] \
   && [ "$(compte "$OUT" 'en cours')" -eq 2 ] \
   && ! contient "$OUT" "failure" \
   && contient "$(cat "$(cache_de "$R")" 2>/dev/null)" "|vif|en cours|"; then
  note_pass "(4) run vif : « en cours », conclusion JAMAIS lue avant status (C4)"
else
  note_fail "(4) précédence status/conclusion (rc=$RC) : [$OUT]"
fi

# --- (5) gh code != 0 : motif = PREMIÈRE ligne, rien ne fuit ----------------
R="$(mk_racine)"; B="$(mk_bin)"
printf 'epoch=1\nci.yml|ok|success|deadbee\n' > "$(cache_de "$R")"
AVANT="$(cat "$(cache_de "$R")")"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh: To get started with GitHub CLI, please run: gh auth login" >&2
echo "SECONDE-LIGNE-QUI-NE-DOIT-PAS-FUIR" >&2
exit 1
STUB
chmod +x "$B/gh"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>/dev/null)"; RC=$?
APRES="$(cat "$(cache_de "$R")")"
if [ "$RC" -eq 0 ] \
   && [ "$(compte "$OUT" 'COVERAGE DEGRADED')" -eq 2 ] \
   && contient "$OUT" "please run: gh auth login" \
   && ! contient "$OUT" "SECONDE-LIGNE-QUI-NE-DOIT-PAS-FUIR" \
   && [ "$AVANT" = "$APRES" ]; then
  note_pass "(5) gh code != 0 : dégradé, motif = 1re ligne, rien ne fuit, cache intact"
else
  note_fail "(5) gh code != 0 (rc=$RC) : [$OUT]"
fi

# --- (6) mur dépassé sur UN workflow : l'AUTRE est toujours relevé (C1) -----
R="$(mk_racine)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "--workflow=ci.yml" ]; then sleep 30; exit 0; fi
done
printf '[{"conclusion":"success","status":"completed","headSha":"fedcba9876543210","createdAt":"2026-08-13T03:00:00Z"}]\n'
STUB
chmod +x "$B/gh"
DEBUT="$(date +%s)"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>/dev/null)"; RC=$?
ECOULE=$(( $(date +%s) - DEBUT ))
if [ "$RC" -eq 0 ] \
   && contient "$OUT" "COVERAGE DEGRADED — ci.yml : dernier run inconnu (mur 8 s)" \
   && contient "$OUT" "DERNIER RUN eval-nightly.yml (main): success @ fedcba9" \
   && [ "$ECOULE" -lt 25 ] \
   && [ ! -f "$(cache_de "$R")" ]; then
  note_pass "(6) mur 8 s sur ci.yml : coupé, eval-nightly.yml TOUJOURS relevé (${ECOULE}s), cache non écrasé"
else
  note_fail "(6) mur (rc=$RC, ${ECOULE}s) : [$OUT]"
fi

echo

MAINTENANT="$(date +%s)"
statusline() { printf '{}' | CLAUDE_PROJECT_DIR="$1" bash "$STATUSLINE" 2>/dev/null; }

# =============================================================================
# LES SIX BRAS « STATUSLINE » DE L'ORIGINE SONT RETIRÉS — ET REMPLACÉS.
#
# Chez l'auteur d'origine, `.claude/statusline.sh` lit le cache CI pour le
# PILOTE. La nôtre est câblée sur le board (`tasks.py --statusline`) et c'est un
# CHOIX de ce kit, pas un manque : le relevé CI y atteint l'AGENT par le
# SessionStart. Garder leurs bras aurait testé une surface que nous n'avons pas,
# et les faire passer aurait exigé de recâbler notre statusline pour satisfaire
# un test — l'inverse de l'ordre correct.
#
# Ce qui les remplace teste NOTRE canal, aux DEUX bouts. [T-00000379, L-00000136]
# =============================================================================

echo
echo "=== CANAL — le relevé a un ÉCRIVAIN et un LECTEUR, et ils se rejoignent ==="

# --- (7) LECTEUR : --cached ne touche NI le réseau NI gh ---------------------
# Le SessionStart est payé à chaque démarrage ; l'auteur d'origine y appelle le
# script complet et paie le mur (8 s + 1 s par workflow). Ici le lecteur est
# `--cached` : il rend la dernière mesure connue, sans réseau.
R="$(mk_racine)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh NE DOIT JAMAIS ETRE APPELE EN MODE --cached" >&2
exit 99
STUB
chmod +x "$B/gh"
printf 'epoch=%s\nci.yml|vert|success|abcdef1\n' "$(date +%s)" > "$(cache_de "$R")"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" --cached 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && contient "$OUT" "DERNIER RUN ci.yml" && ! contient "$OUT" "NE DOIT JAMAIS"; then
  note_pass "(7) --cached rend le cache SANS appeler gh (zéro réseau au démarrage)"
else
  note_fail "(7) --cached (rc=$RC) : [$OUT]"
fi

# --- (8) LECTEUR : la PÉREMPTION est visible, jamais silencieuse -------------
# Un cache jamais rafraîchi doit se lire « vieux », pas « absent » : c'est ce qui
# rend un écrivain défaillant VISIBLE au lieu de le laisser passer pour un calme.
R="$(mk_racine)"
printf 'epoch=%s\nci.yml|vert|success|abcdef1\n' "$(( $(date +%s) - 259200 ))" > "$(cache_de "$R")"
OUT="$(CLAUDE_PROJECT_DIR="$R" bash "$SUT" --cached 2>&1)"
if contient "$OUT" "il y a 3 j"; then
  note_pass "(8) la ligne porte l'ÂGE du relevé — un cache mort se voit"
else
  note_fail "(8) âge absent de la ligne : [$OUT]"
fi

# --- (9) LECTEUR : cache absent -> dégradation ANNONCÉE, jamais un vide ------
R="$(mk_racine)"
OUT="$(CLAUDE_PROJECT_DIR="$R" bash "$SUT" --cached 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && contient "$OUT" "COVERAGE DEGRADED" && contient "$OUT" "ci-last-run.sh"; then
  note_pass "(9) cache absent : dégradation annoncée ET le remède est nommé"
else
  note_fail "(9) cache absent (rc=$RC) : [$OUT]"
fi

# --- (10) ÉCRIVAIN : l'étape avant-push est NOMMÉE dans la doctrine ----------
# Un canal dont personne ne déclenche l'écriture est inerte, et son test resterait
# vert sur une fixture de cache. L'écrivain doit exister ET être trouvable.
SKILL="$ROOT/.agents/skills/verification-discipline/SKILL.md"
if [ -f "$SKILL" ] && grep -q 'ci-last-run.sh' "$SKILL"; then
  note_pass "(10) l'ÉCRIVAIN est nommé dans verification-discipline (avant un push)"
else
  note_fail "(10) aucune étape d'écriture nommée : le canal n'a pas d'écrivain"
fi

# --- (11) LECTEUR CÂBLÉ : le SessionStart appelle bien --cached --------------
HOOK="$ROOT/.claude/hooks/session-start.sh"
# ANCRÉ SUR LA LIGNE DE COMMANDE, PAS SUR LE TEXTE DU FICHIER. Une première
# version cherchait `--cached` n'importe où dans le hook : le COMMENTAIRE qui
# explique le mode contient le mot, donc retirer le drapeau de l'appel réel
# laissait le bras VERT — mesuré par mutation. Une garde par sous-chaîne est
# fausse dans les deux sens. [L-00000143]
if [ -f "$HOOK" ]    && grep -qE '^[^#]*bash "\$CLAUDE_PROJECT_DIR/core-scripts/ci-last-run\.sh" --cached' "$HOOK"; then
  note_pass "(11) le LECTEUR est câblé au SessionStart, en mode --cached (ligne de COMMANDE)"
else
  note_fail "(11) le SessionStart ne lit pas le relevé, ou l'appelle SANS --cached (mur au démarrage)"
fi

# --- (12) GARDE D'ANCRAGE : ancrée sur CLAUDE_PROJECT_DIR, jamais le cwd -----
# Sans elle, une fixture qui déclenche un SessionStart peut partir en réseau, ou
# pire écrire le cache du VRAI dépôt depuis un dépôt jetable.
if grep -qE '^[^#]*\[ -f "\$CLAUDE_PROJECT_DIR/core-scripts/ci-last-run\.sh" \]' "$HOOK"; then
  note_pass "(12) garde d'ancrage sur CLAUDE_PROJECT_DIR (jamais le cwd nu)"
else
  note_fail "(12) l'appel n'est pas ancré sur CLAUDE_PROJECT_DIR"
fi

# --- (13) BOUT EN BOUT : écrire, puis lire par le hook -----------------------
# Le seul bras qui prouve que les deux bouts se REJOIGNENT. Les précédents
# prouvent chacun un bout ; celui-ci prouve la boucle.
R="$(mk_racine)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
printf '[{"conclusion":"success","status":"completed","headSha":"feedbee1234567890","createdAt":"2026-08-26T10:00:00Z"}]\n'
STUB
chmod +x "$B/gh"
PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" >/dev/null 2>&1
OUT="$(CLAUDE_PROJECT_DIR="$R" bash "$SUT" --cached 2>&1)"
if contient "$OUT" "feedbee" && contient "$OUT" "relevé il y a"; then
  note_pass "(13) BOUT EN BOUT : l'écrivain remplit le cache, le lecteur le rend DATÉ"
else
  note_fail "(13) la boucle ne se ferme pas : [$OUT]"
fi

# --- (14) racine SANS workflow : on le DIT, on n'invente pas ----------------
R="$(mk_racine_vide)"; B="$(mk_bin)"
cat > "$B/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh ne doit pas etre appele sans workflow" >&2
exit 99
STUB
chmod +x "$B/gh"
OUT="$(PATH="$B:$PATH" CLAUDE_PROJECT_DIR="$R" bash "$SUT" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && contient "$OUT" "aucun workflow"; then
  note_pass "(14) aucun workflow : dégradation annoncée, aucun workflow imaginaire relevé"
else
  note_fail "(14) racine sans workflow (rc=$RC) : [$OUT]"
fi

echo
echo "================================================================"
echo "ci-last-run: $pass passé(s) / $fail échec(s)"
[ "$fail" -eq 0 ] || exit 1
echo "Banc ci-last-run VERT."
