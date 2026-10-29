#!/usr/bin/env bash
# requires: git
# ============================================================================
# SCAN D'ARBRE ET NOM NON ASCII — `shellcheck-scan.sh` lit-il TOUS les fichiers
# suivis, ou en perd-il un sans un mot ? (T-00001181, binôme S-00004134 A-2)
#
# Le suffixe `.test.sh` EST l'enregistrement : `core-scripts/run-bash-tests.sh`
# découvre cette suite par glob. Suite NEUVE et à part : la suite locale
# (`shellcheck-scan-locale.test.sh`) exclut tout `git init` par construction, et
# ce défaut vit dans `git ls-files`. `shellcheck-scan.test.sh` reste GELÉ par
# T-00001088.
#
# LE DÉFAUT (mesuré à 7ca2ec85) : le périmètre de l'arbre lisait `git ls-files`
# SANS `-z`. Sous `core.quotePath` (le défaut de git), un nom non ASCII sort
# entre guillemets, octets échappés en octal ; `[ -f ]` échoue sur ce texte, et
# le fichier sort du scan sans un mot : « propre — 1 fichier(s) LUS », rc 0, sur
# un `é.sh` suivi qui porte un SC2164. Le compte de fichiers lus ne le trahit
# pas : il compte ce qui est ENTRÉ, jamais ce qui est TOMBÉ.
#
# CE QUE CETTE SUITE PROUVE :
#   (t0) contrôle de non-vacuité : sans `-z`, git CITE le nom du dépôt jetable.
#        Sinon le témoin (t) ne pourrait pas rougir sur le mutant « sans -z ».
#   (t)  arbre jetable — copie du scanner sous `.agents/security/`, `é.sh` suivi
#        avec `cd /tmp` sans garde : rc 1, SC2164, la ligne `é.sh:2:1` et les
#        2 fichiers lus, jamais « propre ». Joué sous la locale héritée PUIS
#        sous `LC_ALL=C LANG=C` (la locale de la jambe conteneur).
#   (u0) contrôle de non-vacuité : le dossier jetable SANS `.git` n'est dans
#        aucun dépôt (`GIT_CEILING_DIRECTORIES` borne la remontée de git à lui).
#        Sinon (u) lirait un dépôt parent et ne prouverait rien.
#   (u)  hors dépôt — copie du scanner, `x.sh` fautif, pas de `.git` : le scan
#        d'ARBRE REFUSE, `ECHEC EXECUTION`, rc 1 (rc 2 en `--hook` sans charge),
#        jamais « propre » ni « rien à mesurer ». Mesuré à 50300cdb : « rien à
#        mesurer », rc 0 — le rc de `git ls-files` était jeté (L-00000136).
#   (v)  le mode CIBLÉ et le `--hook` À CHARGE, au même endroit, lisent toujours
#        `x.sh` (SC2164) : ils nomment leurs fichiers, `git ls-files` n'y entre
#        pas, et le correctif ne les touche pas.
#   (w0) contrôle de non-vacuité : le `mktemp` de CE PATH échoue sous un TMPDIR
#        absent. Le `/usr/bin/mktemp` de macOS, appelé sans gabarit, IGNORE
#        TMPDIR (mesuré : rc 0, fichier sous `/var/folders/…/T/`) — sans ce
#        contrôle, (w) ne prouverait rien ; il est alors SKIP, nommé.
#   (w)  TMPDIR absent, dans un dépôt git : le refus nomme `mktemp` et le TMPDIR
#        lu, rc 1 ; le scan d'ARBRE n'accuse JAMAIS `git ls-files`, le mode
#        CIBLÉ jamais la sortie de l'outil (SORTIE INCOMPLÈTE). Mesuré à
#        e9d4379b : « ECHEC EXECUTION (git ls-files rc=1) » en arbre, SORTIE
#        INCOMPLÈTE en ciblé (binôme S-00004148 B-1, S-00004149 A-5).
#   (x0) contrôle : `GIT_TEST_ASSUME_DIFFERENT_OWNER=1` fait refuser le dépôt
#        par git (« dubious ownership », rc 128) ; sinon (x) est SKIP, nommé.
#   (x)  dépôt d'un autre propriétaire : le remède PROPRE au scanner nomme
#        `safe.directory`. Le témoin lit la ligne « Remède, propriétaire
#        différent », jamais le mot seul : le `fatal` de git cite DÉJÀ
#        `safe.directory`, et un grep nu passait sur e9d4379b (binôme
#        S-00004148 B-4).
#   (y)  dépôt jetable, un `*.sh` SUIVI puis retiré du disque sans `git rm` :
#        PÉRIMÈTRE INCOMPLET, le fichier nommé, rc 1 (rc 2 en `--hook` sans
#        charge), jamais « propre — N fichier(s) LUS ». Mesuré à e9d4379b :
#        « propre — 2 fichier(s) LUS », rc 0 (binôme S-00004149 A-6). Dépôt À
#        PART : dans l'arbre de (t), `é.sh` porte un finding, et la base
#        rendrait un refus pour une autre raison.
#   (z0) contrôle : quand l'outil démarre, les fichiers temporaires du scan
#        sont DANS le TMPDIR jetable — le bouchon les compte ; sinon (z) est
#        SKIP, nommé (un mktemp qui ignore TMPDIR les pose ailleurs).
#   (z)  scan d'arbre tué par TERM pendant l'outil (bouchon `shellcheck` lent,
#        3 s) : rc 143, et le TMPDIR jetable est VIDE. Mesuré à e9d4379b : le
#        fichier de stderr de l'outil restait (binôme S-00004149 A-4). Puis la
#        sortie ORDINAIRE (finding, rc 1) le laisse vide aussi : depuis A-4, le
#        piège EXIT est le SEUL nettoyage.
#   (i0) contrôle : une tâche `&` d'un shell non interactif IGNORE INT, et un
#        signal ignoré à l'entrée ne se piège pas. Sous `set -m`, une tâche de
#        fond tuée par INT doit rendre rc 130 ; sinon (i) est SKIP, nommé (un
#        INT hérité ignoré, par exemple d'un lanceur qui met les suites en `&`).
#   (i)  le cas (z) sur INT, dans un sous-shell `set -m` : rc 130, et le TMPDIR
#        jetable est VIDE. CE QU'IL PROUVE : le NETTOYAGE sur INT, pas la ligne
#        `trap … INT` du scanner — sans elle, (i) reste VERT (bash joue le piège
#        EXIT sur INT) ; « sur_signal sans nettoyer » le fait rougir (mesuré le
#        2026-10-05 sous le bash de PATH et /bin/bash 3.2). MESURÉ EN AVANT-PLAN
#        ET EN SÉRIE SEULEMENT : sous le `&` d'un pool local, INT arrive ignoré,
#        et (i0)(i) sont SKIP, nommés.
#
# `core.quotePath=true` est posé dans la config LOCALE du dépôt jetable : une
# config globale `core.quotePath false` ferait sortir le nom brut, et le témoin
# passerait sur le scanner d'avant le correctif.
#
# Sans shellcheck : SKIP nommé, exit 0 — le scan d'arbre n'est PAS mesuré.
# Exit : 0 tout passe · 1 au moins un cas échoue.
# ============================================================================
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
# FORME A de T-00001088 ci-dessus. Plus les autres GIT_CONFIG_* (clés
# injectées, config globale ou système déplacée) : retirées par préfixe. Si
# `compgen` manquait, la boucle ne ferait rien, et sans GIT_CONFIG_COUNT git ne
# lit pas les clés injectées.
for _git_var in $(compgen -e 2>/dev/null); do
  case "$_git_var" in
    GIT_CONFIG|GIT_CONFIG_*)
      unset "$_git_var"
      ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"   # .agents/security -> .agents -> racine
SCAN="$ROOT/.agents/security/shellcheck-scan.sh"

pass=0; fail=0
ok() { echo "  ok: $1"; pass=$((pass + 1)); }
ko() { echo "  KO: $1"; fail=$((fail + 1)); }

[ -f "$SCAN" ] || { echo "FAIL: $SCAN absent"; exit 1; }

# contient <texte> <motif> : motif LITTÉRAL (grep -F), jamais une regex.
contient() { printf '%s' "$1" | grep -qF -- "$2"; }

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "  SKIP (t0)(t)(u0)(u)(v)(w0)(w)(x0)(x)(y)(z0)(z)(i0)(i) : shellcheck absent — le scan d'arbre (nom non ASCII, hors dépôt, mktemp, propriétaire, suivis absents, nettoyage sur TERM et INT) n'est PAS mesuré ici"
  echo
  echo "shellcheck-scan-arbre: $pass passed / $fail failed"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# L'ARBRE JETABLE : le scanner y est COPIÉ, pour que sa racine (`../..` de son
# propre chemin) soit ce dépôt-ci, jamais celui du kit.
ARB="$TMP/arbre"
mkdir -p "$ARB/.agents/security"
cp "$SCAN" "$ARB/.agents/security/shellcheck-scan.sh"
printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$ARB/é.sh"

# git du banc : hooks coupés — ni ceux de l'hôte, ni ceux d'un gabarit d'init.
g() { git -c core.hooksPath=/dev/null -C "$ARB" "$@"; }

if ! g init -q || ! g config core.quotePath true || ! g add -A; then
  ko "dépôt jetable : git init / config / add a échoué sous $ARB"
  echo
  echo "shellcheck-scan-arbre: $pass passed / $fail failed"
  exit 1
fi

# --- (t0) le témoin PEUT rougir ----------------------------------------------
# La forme d'avant le correctif : la liste nue. Un nom cité commence par `"`.
nue="$(g ls-files)"
if contient "$nue" '"'; then
  ok "(t0) contrôle : sans -z, git cite le nom non ASCII (le mutant « sans -z » est visible)"
else
  ko "(t0) contrôle : git ne cite pas le nom non ASCII — (t) ne prouverait rien ; liste=[$nue]"
fi

# --- (t) le scan d'ARBRE lit `é.sh` --------------------------------------------
for mode in héritée C; do
  if [ "$mode" = C ]; then
    out="$(LC_ALL=C LANG=C bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  else
    out="$(bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  fi
  if [ "$rc" -eq 1 ] && contient "$out" 'SC2164' && contient "$out" 'é.sh:2:1' \
    && contient "$out" 'sur 2 fichier(s)' && ! contient "$out" ': propre'; then
    ok "(t) scan d'arbre, locale $mode : é.sh suivi est LU — rc 1, é.sh:2:1, 2 fichiers, jamais propre"
  else
    ko "(t) scan d'arbre, locale $mode : attendu rc 1 + SC2164 + é.sh:2:1 + 2 fichiers, obtenu rc=$rc [$out]"
  fi
done

# --- (u0) le dossier jetable n'est dans AUCUN dépôt -----------------------------
# La remontée de git s'arrête SOUS `$TMP` (chemin physique : git résout les
# liens d'un plafond) — un TMPDIR posé dans un dépôt ne fausse donc pas (u).
HORS="$TMP/horsdepot"
mkdir -p "$HORS/.agents/security"
cp "$SCAN" "$HORS/.agents/security/shellcheck-scan.sh"
printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$HORS/x.sh"
PLAFOND="$(cd "$TMP" && pwd -P)"
if GIT_CEILING_DIRECTORIES="$PLAFOND" git -C "$HORS" rev-parse --git-dir >/dev/null 2>&1; then
  ko "(u0) contrôle : $HORS est dans un dépôt git — (u) ne prouverait rien"
else
  ok "(u0) contrôle : $HORS n'est dans aucun dépôt git (le rc jeté de git est visible)"
fi

# --- (u) hors dépôt, le scan d'ARBRE REFUSE ---------------------------------------
# Sans charge : `</dev/null` n'est pas un terminal, la charge lue est vide, et
# `--hook` retombe sur l'arbre — c'est le seul autre chemin vers `git ls-files`.
for arg in arbre --hook; do
  if [ "$arg" = --hook ]; then
    attendu=2
    out="$(GIT_CEILING_DIRECTORIES="$PLAFOND" bash "$HORS/.agents/security/shellcheck-scan.sh" --hook </dev/null 2>&1)"; rc=$?
  else
    attendu=1
    out="$(GIT_CEILING_DIRECTORIES="$PLAFOND" bash "$HORS/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  fi
  if [ "$rc" -eq "$attendu" ] && contient "$out" 'ECHEC EXECUTION' && contient "$out" 'git ls-files' \
    && ! contient "$out" ': propre' && ! contient "$out" 'rien à mesurer'; then
    ok "(u) hors dépôt, $arg : le scan d'arbre REFUSE — rc $attendu, ECHEC EXECUTION, jamais propre ni rien à mesurer"
  else
    ko "(u) hors dépôt, $arg : attendu rc $attendu + ECHEC EXECUTION (git ls-files), obtenu rc=$rc [$out]"
  fi
done

# --- (v) hors dépôt, ciblé et --hook À CHARGE lisent toujours x.sh ---------------
out="$(GIT_CEILING_DIRECTORIES="$PLAFOND" bash "$HORS/.agents/security/shellcheck-scan.sh" "$HORS/x.sh" </dev/null 2>&1)"; rc=$?
if [ "$rc" -eq 1 ] && contient "$out" 'SC2164' && contient "$out" 'x.sh:2:1' \
  && ! contient "$out" 'ECHEC EXECUTION'; then
  ok "(v) hors dépôt, ciblé : x.sh est LU — rc 1, SC2164, x.sh:2:1"
else
  ko "(v) hors dépôt, ciblé : attendu rc 1 + SC2164 + x.sh:2:1, obtenu rc=$rc [$out]"
fi
# Chemin RELATIF dans la charge : le scanner le lit contre sa racine, et aucun
# caractère du chemin jetable n'entre dans le JSON.
if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  out="$(printf '%s' '{"tool_input":{"file_path":"x.sh"}}' \
    | GIT_CEILING_DIRECTORIES="$PLAFOND" bash "$HORS/.agents/security/shellcheck-scan.sh" --hook 2>&1)"; rc=$?
  if [ "$rc" -eq 2 ] && contient "$out" 'SC2164' && ! contient "$out" 'ECHEC EXECUTION'; then
    ok "(v) hors dépôt, --hook à charge : x.sh est LU — rc 2, SC2164"
  else
    ko "(v) hors dépôt, --hook à charge : attendu rc 2 + SC2164, obtenu rc=$rc [$out]"
  fi
else
  echo "  SKIP (v) --hook à charge : aucun python — la charge n'est pas lisible, ce cas n'est PAS mesuré ici"
fi

# --- (w0) le mktemp de CE PATH échoue sous un TMPDIR absent ---------------------
# Un mktemp qui réussirait (BSD de macOS, sans gabarit) a créé un fichier
# ailleurs : il est retiré.
ABSENT="$TMP/tmpdir-absent"
W_MESURE=0
if f0="$(TMPDIR="$ABSENT" mktemp 2>/dev/null)"; then
  [ -z "$f0" ] || rm -f "$f0"
  echo "  SKIP (w0)(w) : le mktemp de ce PATH ignore TMPDIR (mktemp BSD de macOS, sans gabarit) — le refus mktemp n'est PAS mesuré ici"
else
  W_MESURE=1
  ok "(w0) contrôle : sous un TMPDIR absent, le mktemp de ce PATH échoue (le refus mktemp est atteignable)"
fi

# --- (w) TMPDIR absent : le refus nomme mktemp, jamais git ni l'outil ------------
if [ "$W_MESURE" -eq 1 ]; then
  out="$(TMPDIR="$ABSENT" bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  if [ "$rc" -eq 1 ] && contient "$out" 'ECHEC EXECUTION (mktemp a échoué' \
    && contient "$out" "TMPDIR=$ABSENT" && ! contient "$out" 'git ls-files' \
    && ! contient "$out" ': propre' && ! contient "$out" 'rien à mesurer'; then
    ok "(w) TMPDIR absent, scan d'arbre : refus mktemp — rc 1, TMPDIR nommé, git jamais accusé"
  else
    ko "(w) TMPDIR absent, scan d'arbre : attendu rc 1 + « mktemp a échoué » + TMPDIR=$ABSENT, sans « git ls-files », obtenu rc=$rc [$out]"
  fi
  out="$(TMPDIR="$ABSENT" bash "$ARB/.agents/security/shellcheck-scan.sh" "$ARB/é.sh" </dev/null 2>&1)"; rc=$?
  if [ "$rc" -eq 1 ] && contient "$out" 'ECHEC EXECUTION (mktemp a échoué' \
    && ! contient "$out" 'SORTIE INCOMPLÈTE' && ! contient "$out" ': propre'; then
    ok "(w) TMPDIR absent, mode ciblé : refus mktemp — rc 1, la sortie de l'outil jamais accusée"
  else
    ko "(w) TMPDIR absent, mode ciblé : attendu rc 1 + « mktemp a échoué », sans SORTIE INCOMPLÈTE, obtenu rc=$rc [$out]"
  fi
fi

# --- (x0) git refuse un dépôt d'un autre propriétaire ----------------------------
# Config globale et système écartées : un `safe.directory=*` posé ailleurs
# rendrait le dépôt de confiance, et (x) ne prouverait rien.
GIT_TEST_ASSUME_DIFFERENT_OWNER=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  git -C "$ARB" ls-files -z >/dev/null 2>&1
rc_x0=$?
if [ "$rc_x0" -eq 128 ]; then
  ok "(x0) contrôle : sous GIT_TEST_ASSUME_DIFFERENT_OWNER=1, git refuse le dépôt (rc 128)"
  # --- (x) le remède du scanner nomme safe.directory -----------------------------
  out="$(GIT_TEST_ASSUME_DIFFERENT_OWNER=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  if [ "$rc" -eq 1 ] && contient "$out" 'ECHEC EXECUTION (git ls-files rc=128)' \
    && contient "$out" 'Remède, propriétaire différent (git : dubious ownership) : git config --global --add safe.directory' \
    && ! contient "$out" ': propre'; then
    ok "(x) propriétaire différent : refus rc 1, et le remède du scanner nomme safe.directory"
  else
    ko "(x) propriétaire différent : attendu rc 1 + git ls-files rc=128 + « Remède, propriétaire différent … safe.directory », obtenu rc=$rc [$out]"
  fi
else
  echo "  SKIP (x0)(x) : ce git n'honore pas GIT_TEST_ASSUME_DIFFERENT_OWNER (rc=$rc_x0) — le remède safe.directory n'est PAS mesuré ici"
fi

# --- (y) un *.sh SUIVI absent du disque : PÉRIMÈTRE INCOMPLET, jamais propre --------
ABS="$TMP/absents"
mkdir -p "$ABS/.agents/security"
cp "$SCAN" "$ABS/.agents/security/shellcheck-scan.sh"
printf '#!/usr/bin/env bash\necho ok\n' > "$ABS/ok.sh"
printf '#!/usr/bin/env bash\necho parti\n' > "$ABS/parti.sh"
ga() { git -c core.hooksPath=/dev/null -C "$ABS" "$@"; }
if ga init -q && ga add -A && rm -f "$ABS/parti.sh" && [ ! -e "$ABS/parti.sh" ] \
  && contient "$(ga ls-files)" 'parti.sh'; then
  for arg in arbre --hook; do
    if [ "$arg" = --hook ]; then
      attendu=2
      out="$(bash "$ABS/.agents/security/shellcheck-scan.sh" --hook </dev/null 2>&1)"; rc=$?
    else
      attendu=1
      out="$(bash "$ABS/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
    fi
    if [ "$rc" -eq "$attendu" ] && contient "$out" 'PÉRIMÈTRE INCOMPLET — 1 fichier(s) *.sh SUIVI(S) ABSENT(S)' \
      && contient "$out" '  parti.sh' && ! contient "$out" ': propre'; then
      ok "(y) .sh suivi absent du disque, $arg : PÉRIMÈTRE INCOMPLET — rc $attendu, parti.sh nommé, jamais propre"
    else
      ko "(y) .sh suivi absent du disque, $arg : attendu rc $attendu + PÉRIMÈTRE INCOMPLET + parti.sh, obtenu rc=$rc [$out]"
    fi
  done
else
  ko "(y) dépôt jetable : init / add / retrait de parti.sh a échoué sous $ABS — (y) ne prouverait rien"
fi

# --- (z) scan d'arbre tué pendant l'outil : le TMPDIR jetable reste vide ------------
# Le bouchon remplace `shellcheck` pour CET appel seul : il compte ce que le
# scan a posé dans TMPDIR (z0), signale son départ, dort 3 s, signale sa fin.
# Il sort hors du TMPDIR jetable, que le témoin lit.
BOUCHON="$TMP/bouchon-lent"
TMPZ="$TMP/tmpdir-z"
MARQ="$TMP/marques-z"
mkdir -p "$BOUCHON" "$TMPZ" "$MARQ"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'if [ "${1-}" = --version ]; then echo "version: 0.0-bouchon"; exit 0; fi' \
  'ls -A "$TMPDIR" >"$BOUCHON_MARQ/vu" 2>/dev/null' \
  ': >"$BOUCHON_MARQ/parti"' \
  'sleep 3' \
  ': >"$BOUCHON_MARQ/fini"' \
  'exit 0' > "$BOUCHON/shellcheck"
chmod +x "$BOUCHON/shellcheck"
PATH="$BOUCHON:$PATH" TMPDIR="$TMPZ" BOUCHON_MARQ="$MARQ" \
  bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null >"$MARQ/sortie" 2>&1 &
pid=$!
i=0
while [ ! -e "$MARQ/parti" ] && [ "$i" -lt 300 ]; do
  sleep 0.1
  i=$((i + 1))
done
kill -s TERM "$pid" 2>/dev/null
{ wait "$pid"; } 2>/dev/null
rc=$?
# Sans piège, le scan meurt AVANT le bouchon : on attend sa fin (borné), pour
# lire le TMPDIR une fois tout le monde sorti.
j=0
while [ -e "$MARQ/parti" ] && [ ! -e "$MARQ/fini" ] && [ "$j" -lt 100 ]; do
  sleep 0.1
  j=$((j + 1))
done
reste="$(ls -A "$TMPZ")"
if [ ! -e "$MARQ/parti" ]; then
  ko "(z) le bouchon shellcheck n'a pas démarré en 30 s — rc=$rc [$(cat "$MARQ/sortie" 2>/dev/null)]"
elif [ ! -s "$MARQ/vu" ]; then
  echo "  SKIP (z0)(z) : le scan n'a rien posé dans le TMPDIR jetable (un mktemp qui ignore TMPDIR) — le nettoyage sur TERM n'est PAS mesuré ici"
else
  ok "(z0) contrôle : au départ de l'outil, le TMPDIR jetable porte les fichiers du scan [$(tr '\n' ' ' <"$MARQ/vu")]"
  if [ "$rc" -eq 143 ] && [ -z "$reste" ]; then
    ok "(z) scan d'arbre tué par TERM pendant l'outil : rc 143, TMPDIR jetable vide"
  else
    ko "(z) scan d'arbre tué par TERM : attendu rc 143 + TMPDIR vide, obtenu rc=$rc, reste=[$reste]"
  fi
  # Sortie ORDINAIRE, vrai shellcheck : le seul nettoyage est le piège EXIT.
  # Sans ce cas, retirer `trap nettoyer EXIT` laissait la liste et le stderr de
  # l'outil à CHAQUE scan, banc vert (mutant mesuré : 17 / 0, 11 fichiers).
  TMPZO="$TMP/tmpdir-zo"
  mkdir -p "$TMPZO"
  out="$(TMPDIR="$TMPZO" bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null 2>&1)"; rc=$?
  reste="$(ls -A "$TMPZO")"
  if [ "$rc" -eq 1 ] && contient "$out" 'é.sh:2:1' && [ -z "$reste" ]; then
    ok "(z) scan d'arbre, sortie ordinaire sur finding : rc 1, TMPDIR jetable vide"
  else
    ko "(z) scan d'arbre, sortie ordinaire : attendu rc 1 + é.sh:2:1 + TMPDIR vide, obtenu rc=$rc, reste=[$reste] [$out]"
  fi
fi

# --- (i) scan d'arbre tué par INT pendant l'outil : le TMPDIR jetable reste vide ------------
# Le cas (z), sur INT. Un shell NON interactif lance ses tâches `&` avec INT
# IGNORÉ, et un signal ignoré à l'entrée ne se piège pas : lancé comme en (z),
# le scan ne verrait jamais l'INT. D'où le sous-shell `set -m` (contrôle de
# tâches : la tâche de fond garde INT). (i0) vérifie qu'il le garde ICI ;
# sinon (i) est SKIP, nommé. Même bouchon que (z) ; le rc sort du sous-shell
# par un fichier, et son stderr (avis de tâche) est jeté.
TMPI="$TMP/tmpdir-i"
MARQI="$TMP/marques-i"
mkdir -p "$TMPI" "$MARQI"
(
  set -m
  sleep 2 &
  p=$!
  sleep 0.2
  kill -s INT "$p" 2>/dev/null
  wait "$p"
  echo "$?" >"$MARQI/rc-i0"
) 2>/dev/null
rc_i0="$(cat "$MARQI/rc-i0" 2>/dev/null)"
if [ "$rc_i0" != 130 ]; then
  echo "  SKIP (i0)(i) : sous \`set -m\`, une tâche de fond tuée par INT rend rc=[$rc_i0], pas 130 (INT ignoré par la tâche) — le nettoyage sur INT n'est PAS mesuré ici"
else
  ok "(i0) contrôle : sous \`set -m\`, une tâche de fond tuée par INT rend rc 130"
  (
    set -m
    PATH="$BOUCHON:$PATH" TMPDIR="$TMPI" BOUCHON_MARQ="$MARQI" \
      bash "$ARB/.agents/security/shellcheck-scan.sh" </dev/null >"$MARQI/sortie" 2>&1 &
    p=$!
    i=0
    while [ ! -e "$MARQI/parti" ] && [ "$i" -lt 300 ]; do
      sleep 0.1
      i=$((i + 1))
    done
    kill -s INT "$p" 2>/dev/null
    wait "$p"
    echo "$?" >"$MARQI/rc"
  ) 2>/dev/null
  rc="$(cat "$MARQI/rc" 2>/dev/null)"
  # Comme en (z) : on attend la fin du bouchon (bornée) avant de lire le TMPDIR.
  j=0
  while [ -e "$MARQI/parti" ] && [ ! -e "$MARQI/fini" ] && [ "$j" -lt 100 ]; do
    sleep 0.1
    j=$((j + 1))
  done
  reste="$(ls -A "$TMPI")"
  if [ ! -e "$MARQI/parti" ]; then
    ko "(i) le bouchon shellcheck n'a pas démarré en 30 s — rc=$rc [$(cat "$MARQI/sortie" 2>/dev/null)]"
  elif [ ! -s "$MARQI/vu" ]; then
    echo "  SKIP (i) : le scan n'a rien posé dans le TMPDIR jetable (un mktemp qui ignore TMPDIR) — le nettoyage sur INT n'est PAS mesuré ici"
  elif [ "$rc" = 130 ] && [ -z "$reste" ]; then
    ok "(i) scan d'arbre tué par INT pendant l'outil : rc 130, TMPDIR jetable vide"
  else
    ko "(i) scan d'arbre tué par INT : attendu rc 130 + TMPDIR vide, obtenu rc=$rc, reste=[$reste]"
  fi
fi

echo
echo "shellcheck-scan-arbre: $pass passed / $fail failed"
[ "$fail" -eq 0 ] || exit 1
