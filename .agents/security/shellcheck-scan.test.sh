#!/usr/bin/env bash
# ============================================================================
# GARDE DE LA GARDE — `shellcheck-scan.sh` peut-il encore rougir ?
#
# Le suffixe `.test.sh` EST l'enregistrement : `core-scripts/run-bash-tests.sh`
# découvre cette suite par glob, et ce runner est une étape de `verify.sh` ET de
# `.github/workflows/ci.yml`. Aucune étape CI n'est ajoutée — c'est la promesse
# que `check-ci-parity` garde.
#
# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# allows-missing: shellcheck
#
# CE QUE CETTE SUITE PROUVE, ET POURQUOI CHAQUE ARM EXISTE :
#   (a) le scanner MORD sur la classe qui a motivé son câblage (`cd` sans garde)
#   (b) il est PROPRE sur l'arbre réel — sinon il serait désarmé dans la semaine
#   (c) `--hook` est SILENCIEUX quand c'est propre : un hook bavard est un hook
#       qu'on retire
#   (d) sans `shellcheck`, il DÉGRADE et le DIT — jamais un faux propre
#   (e) chaque exclusion porte sa RAISON dans le corps du scanner — une
#       exclusion muette est une porte dérobée
#   (f) il est ENREGISTRÉ en PostToolUse : un scanner non câblé ne trouve rien
#       « vite », il ne trouve rien du tout
#   (h)…(m) `--hook` ne lit QUE le fichier de la charge : un .md ne lance rien,
#       un .sh fautif sort 2 (rendu au modèle), hors racine / ignoré / sans
#       file_path sort 0 sans scan, et sans python la dégradation est ANNONCÉE
#
# Exit : 0 tout passe · 1 au moins un cas échoue.
# ============================================================================
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"   # .agents/security -> .agents -> racine
SCAN="$ROOT/.agents/security/shellcheck-scan.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
ok() { echo "  ok: $1"; pass=$((pass + 1)); }
ko() { echo "  KO: $1"; fail=$((fail + 1)); }

[ -f "$SCAN" ] || { echo "FAIL: $SCAN absent"; exit 1; }

# --- (0) AUCUN COMMENTAIRE DE PROSE NE COMMENCE PAR LE MOT « shellcheck » -----
# Il serait lu comme une DIRECTIVE, et le fichier ENTIER sortirait de l'analyse
# sur SC1073/SC1072 — mesuré sur 0.10.0 et 0.11.0, et payé une fois le
# 2026-09-13 sur `core-scripts/verify.sh`. Ce contrôle est PLACÉ AVANT le test
# de présence de l'outil, et c'est délibéré : il doit tenir SANS shellcheck
# installé, puisque c'est précisément là que le scanner ne peut rien attraper.
# LES DEUX FORMES, et la seconde a failli passer : `# shellcheck : prose` ET
# `# shellcheck: prose` (deux-points COLLÉ) cassent toutes deux le parseur —
# mesuré sur 0.11.0, SC1073 + SC1072 sur les deux. Un motif exigeant une espace
# après le mot n'attrape que la première, et laisse la seconde retirer un fichier
# entier en silence, sur un hôte sans shellcheck, c'est-à-dire là où ce filet est
# la SEULE protection. Trouvé par le binôme de PLAN, vérifié à la main.
faux="$(git -C "$ROOT" grep -nE '^[[:space:]]*#[[:space:]]*shellcheck([[:space:]]|:)' -- '*.sh' '*.command' '.githooks/*' 2>/dev/null \
  | grep -vE '#[[:space:]]*shellcheck[[:space:]]+(disable|source|shell|enable|external-sources)=' || true)"
if [ -z "$faux" ]; then
  ok "(0) aucun commentaire de prose ne commence par le mot shellcheck"
else
  ko "(0) directive-prose qui retire un fichier entier de l analyse : $faux"
fi

if ! command -v shellcheck >/dev/null 2>&1; then
  # LA DÉGRADATION EST MESURÉE, PAS SUPPOSÉE : c'est le seul arm qui puisse
  # tourner ici, et il doit tourner — sinon l'absence de l'outil rendrait la
  # suite vide ET verte.
  out="$(bash "$SCAN" 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'COVERAGE DEGRADED'; then
    ok "(d) shellcheck absent => COVERAGE DEGRADED annoncé, exit 0, jamais un faux propre"
  else
    ko "(d) shellcheck absent : attendu exit 0 + COVERAGE DEGRADED, obtenu rc=$rc [$out]"
  fi
  echo "  SKIP (a)(b)(c) : shellcheck absent — la correction du shell n'est PAS mesurée ici"
  echo "shellcheck-scan: $pass passed / $fail failed"
  [ "$fail" -eq 0 ] || exit 1
  exit 0
fi

# --- (a) IL MORD — la classe qui a motivé le câblage -------------------------
printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$TMP/mord.sh"
out="$(bash "$SCAN" "$TMP/mord.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'SC2164'; then
  ok "(a) un \`cd\` sans garde est REFUSÉ (rc 1) et le code SC2164 est nommé"
else
  ko "(a) le scanner ne mord pas sur \`cd\` sans garde (rc=$rc)"
fi

# --- (a2) LE REFUS PORTE SON REMÈDE, jamais un compte nu ---------------------
if printf '%s' "$out" | grep -q 'Remède'; then
  ok "(a2) le refus nomme le remède ET dit qu'une exclusion sans raison est une porte dérobée"
else
  ko "(a2) le refus ne porte aucun remède — un compte nu n'apprend rien"
fi

# --- (b) PROPRE SUR L'ARBRE RÉEL --------------------------------------------
# Une garde qui naît rouge est une garde qu'on désarme. Cet arm est ce qui
# oblige à corriger AVANT de câbler, jamais après.
out="$(bash "$SCAN" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then
  ok "(b) l'arbre réel est propre — la garde naît verte"
else
  ko "(b) l'arbre réel n'est PAS propre : $(printf '%s' "$out" | head -3)"
fi

# --- (c) `--hook` SILENCIEUX QUAND C'EST PROPRE ------------------------------
# stdin FERMÉ exprès : sans charge, `--hook` retombe sur l'arbre entier.
out="$(bash "$SCAN" --hook </dev/null 2>&1)"; rc=$?
n="$(printf '%s' "$out" | wc -c | tr -d ' ')"
if [ "$rc" -eq 0 ] && [ "$n" -eq 0 ]; then
  ok "(c) --hook rend ZÉRO octet quand c'est propre — un hook bavard est un hook retiré"
else
  ko "(c) --hook bavarde (rc=$rc, $n octets) alors que l'arbre est propre"
fi

# --- (h)…(m) `--hook` NE LIT QUE LE FICHIER DE LA CHARGE ---------------------
# La première forme relisait l'arbre entier à chaque Edit/Write (~60 s mesurées
# le 2026-09-29, `.md` compris). Le témoin n'est PAS un chronomètre — un seuil
# de temps rougit sur une machine chargée : c'est un `shellcheck` factice qui
# laisse une trace s'il est appelé. Tout arm qui attend « rien lancé » l'exige,
# sinon un parseur cassé retombant sur un arbre propre le rendrait vert à tort.
# Aucune écriture dans le dépôt : (i) et (m) tournent sur une RACINE FACTICE
# sous $TMP (le scanner dérive ROOT de son propre chemin).
# La garde EXÉCUTE python : `command -v` est vrai sur le stub du Microsoft Store.
if python3 -c 'import json' >/dev/null 2>&1; then
  charge() { printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$1"; }
  mkdir -p "$TMP/espion"
  printf '#!/usr/bin/env bash\necho appel >> "%s/espion/trace"\nexit 0\n' "$TMP" > "$TMP/espion/shellcheck"
  chmod +x "$TMP/espion/shellcheck"
  trace() { [ -f "$TMP/espion/trace" ] && echo oui || echo non; }

  out="$(charge "$ROOT/README.md" | PATH="$TMP/espion:$PATH" bash "$SCAN" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ] && [ "$(trace)" = non ]; then
    ok "(h) édition d'un .md : exit 0, zéro octet, shellcheck JAMAIS lancé"
  else
    ko "(h) édition d'un .md : rc=$rc, sortie [$out], trace=$(trace)"
  fi

  RAC="$TMP/racine"
  mkdir -p "$RAC/.agents/security"
  cp "$SCAN" "$RAC/.agents/security/"
  git -C "$RAC" init -q 2>/dev/null
  printf 'ignore.sh\n' > "$RAC/.gitignore"
  DANS="$RAC/a b'é.sh"
  printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$DANS"
  out="$(charge "$DANS" | bash "$RAC/.agents/security/shellcheck-scan.sh" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q 'SC2164'; then
    ok "(i) .sh fautif dans la racine (espace, apostrophe, accent) : exit 2 (rendu au modèle), SC2164 nommé"
  else
    ko "(i) .sh fautif dans la racine : attendu rc 2 + SC2164, obtenu rc=$rc [$out]"
  fi

  out="$(charge "$TMP/mord.sh" | PATH="$TMP/espion:$PATH" bash "$SCAN" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ] && [ "$(trace)" = non ]; then
    ok "(j) .sh fautif HORS de la racine : ignoré, exit 0, shellcheck JAMAIS lancé"
  else
    ko "(j) .sh hors racine : attendu rc 0 silencieux sans appel, obtenu rc=$rc [$out], trace=$(trace)"
  fi

  mkdir -p "$TMP/sanspy"
  for c in bash cat head grep dirname git mktemp printf wc sed tr uname; do
    p="$(command -v "$c" 2>/dev/null)" && [ -x "$p" ] && ln -sf "$p" "$TMP/sanspy/$c"
  done
  # Python ABSENT se SIMULE par des stubs rc 127, jamais par un PATH qui ne les
  # porte pas : le capteur de `run-bash-tests.sh` journaliserait `python3` et
  # `python` en MISSING DEP et rougirait la suite (mesuré sous le runner).
  for t in python3 python py; do
    { printf '#!%s\n' "$(command -v bash)"; printf 'exit 127\n'; } > "$TMP/sanspy/$t"
    chmod +x "$TMP/sanspy/$t"
  done
  ln -sf "$TMP/espion/shellcheck" "$TMP/sanspy/shellcheck"
  out="$(charge "$DANS" | PATH="$TMP/sanspy" bash "$RAC/.agents/security/shellcheck-scan.sh" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'COVERAGE DEGRADED' && [ "$(trace)" = non ]; then
    ok "(k) sans python : COVERAGE DEGRADED annoncé, exit 0, pas de scan de l'arbre en silence"
  else
    ko "(k) sans python : attendu rc 0 + COVERAGE DEGRADED sans appel, obtenu rc=$rc [$out], trace=$(trace)"
  fi

  out="$(printf '{"tool_name":"Edit","tool_input":{}}' | PATH="$TMP/espion:$PATH" bash "$SCAN" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ] && [ "$(trace)" = non ]; then
    ok "(l) charge sans file_path : exit 0 silencieux, JAMAIS l'arbre entier"
  else
    ko "(l) charge sans file_path : rc=$rc, sortie [$out], trace=$(trace)"
  fi

  printf '#!/usr/bin/env bash\ncd /tmp\n' > "$RAC/ignore.sh"
  out="$(charge "$RAC/ignore.sh" | bash "$RAC/.agents/security/shellcheck-scan.sh" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
    ok "(m) .sh ignoré par git : sauté, comme la porte qui ne le lit pas"
  else
    ko "(m) .sh ignoré par git : attendu rc 0 silencieux, obtenu rc=$rc [$out]"
  fi
else
  echo "  SKIP (h)…(m) : python 3 non exécutable — le ciblage du hook n'est PAS vérifié"
fi

# --- (d) SANS SHELLCHECK — dégradation annoncée ------------------------------
# PATH réduit aux commandes dont le scanner a besoin, `shellcheck` retiré. Un
# PATH VIDE retirerait aussi `git`/`head`/`grep` et prouverait autre chose.
mkdir -p "$TMP/bin"
# LA LISTE EST CELLE QUE LE SCANNER UTILISE, et elle est EXHAUSTIVE : un PATH
# trop maigre retire une commande dont le scanner a besoin, il sort en 127, et
# le capteur de « 127 avalé » du runner (T-00000427) rougit la suite — mesuré
# ici avec `dirname`, que `ROOT="$(cd "$(dirname …)")"` appelle à la ligne 1 du
# scanner. Ce n'est PAS un faux positif du capteur : c'est ce banc qui simulait
# mal l'absence d'UN outil en retirant les autres.
for c in git head grep bash mktemp printf dirname wc cat sed tr; do
  p="$(command -v "$c" 2>/dev/null)" && [ -x "$p" ] && ln -sf "$p" "$TMP/bin/$c"
done
out="$(PATH="$TMP/bin" bash "$SCAN" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'COVERAGE DEGRADED'; then
  ok "(d) shellcheck absent => COVERAGE DEGRADED, exit 0, jamais un faux propre"
else
  ko "(d) sans shellcheck : attendu exit 0 + COVERAGE DEGRADED, obtenu rc=$rc [$out]"
fi

# --- (e) CHAQUE EXCLUSION PORTE SA RAISON ------------------------------------
# L'ensemble est CLOS et commenté dans le corps du scanner. Un code ajouté à
# `EXCLUS` sans apparaître dans le pavé d'arbitrage est une porte dérobée.
codes="$(grep -oE 'EXCLUS="[^"]+"' "$SCAN" | head -1 | tr -d '"' | cut -d= -f2 | tr ',' ' ')"
manquants=""
for c in $codes; do
  grep -q "$c" "$SCAN" || manquants="$manquants $c"
  # la raison vit dans le tableau d'arbitrage, repéré par le code SUIVI de texte
  grep -qE "^#.*$c" "$SCAN" || manquants="$manquants $c(sans-raison)"
done
if [ -z "$manquants" ] && [ -n "$codes" ]; then
  ok "(e) les $(printf '%s' "$codes" | wc -w | tr -d ' ') exclusions portent chacune leur raison mesurée"
else
  ko "(e) exclusion sans raison dans le corps du scanner :$manquants"
fi

# --- (f) ENREGISTRÉ EN PostToolUse -------------------------------------------
# Un scanner non câblé ne trouve rien « vite » : il ne trouve rien du tout.
# LE REGISTRE EST DU JSON : on le PARSE, on ne le grep pas. Un `grep` sur le
# texte brut voit `shellcheck-scan.sh\"` — le guillemet est échappé — et rend un
# faux négatif. C'est le piège « filet textuel sur une structure », et il a
# mordu ici à la première écriture de ce banc.
if command -v python3 >/dev/null 2>&1; then
  # LE HEREDOC N'EST PAS LA CONDITION DU `if` — c'est la forme n°5 du catalogue
  # de `.agents/ref/CONVENTIONS_shell.md` : `if <cmd> <<MOT` est du bash valide
  # que tree-sitter-bash NE PARSE PAS, et un seul site retire le fichier ENTIER
  # du compte des cibles inspectées par la porte SAST. Écrite ici à la première
  # rédaction de ce banc, et attrapée par `test_no_compact_case.py` — le filet
  # a mordu sur le banc du scanner qu'on venait d'écrire.
  python3 - "$ROOT/.claude/settings.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
legs = [h.get("command", "")
        for ev in d.get("hooks", {}).values()
        for blk in ev for h in blk.get("hooks", [])]
sys.exit(0 if any("shellcheck-scan.sh" in c and "--hook" in c for c in legs) else 1)
PYEOF
  rc_reg=$?
  if [ "$rc_reg" -eq 0 ]; then
    ok "(f) enregistré en hook — il mord à l'ÉDITION, pas seulement à la porte"
  else
    ko "(f) shellcheck-scan.sh n'est PAS enregistré dans .claude/settings.json"
  fi
else
  echo "  SKIP (f) : python3 absent — l'enregistrement du hook n'est PAS vérifié"
fi

# --- (g) ÉTAPE DE LA PORTE ---------------------------------------------------
if grep -q 'shellcheck-scan.sh' "$ROOT/core-scripts/verify.sh"; then
  ok "(g) étape de core-scripts/verify.sh — donc de la CI, sans étape CI en plus"
else
  ko "(g) absent de core-scripts/verify.sh"
fi

echo
echo "shellcheck-scan: $pass passed / $fail failed"
[ "$fail" -eq 0 ] || exit 1
