#!/usr/bin/env bash
# ============================================================================
# LOCALE ET SORTIE INCOMPLÈTE — `shellcheck-scan.sh` rend-il un verdict sur une
# sortie qu'il n'a PAS reçue en entier ? (T-00001181)
#
# Le suffixe `.test.sh` EST l'enregistrement : `core-scripts/run-bash-tests.sh`
# découvre cette suite par glob. Suite NEUVE, et non des arms ajoutés à la suite
# du scanner : `shellcheck-scan.test.sh` est GELÉ par T-00001088 (S-00004121, C1).
#
# LE DÉFAUT (S-00004110) : le scanner appelait l'outil sans fixer la locale. Sous
# locale C, la version 0.10.0 (glibc, jambe conteneur) plante en écrivant un nom
# non ASCII (`hPutChar: invalid argument`) : sortie tronquée avant `[SC2164]`,
# stderr jeté, refus sans chemin ni code — et en mode ciblé, un nom relatif
# `é.sh` rendait « propre », rc 0. Un verdict sur une population non lue.
#
# CE QUE CETTE SUITE PROUVE, ET POURQUOI CHAQUE ARM EXISTE :
#   (i)  durci — nom non ASCII, locale héritée, `--hook` : rc 2, SC2164 ET la
#        ligne `<nom>:2:1` (le cas (i) de la suite gelée n'exige pas la ligne,
#        et une sortie tronquée après le code le passerait). Le NOM DE BASE,
#        jamais le chemin absolu : sous Git Bash, `shellcheck.exe` écrit le
#        chemin en `C:\…` (binôme S-00004133 B-2). Le nom porte le `é` : une
#        sortie tronquée ou abîmée sur ce caractère rougit toujours.
#   (n)  le même sous `LC_ALL=C LANG=C`
#   (n2) nom RELATIF non ASCII, mode ciblé, sous C : rc 1, jamais « propre »
#        (le faux propre M4)
#   (o)  outil factice rc 1 MUET : refus SORTIE INCOMPLÈTE, jamais « propre »
#   (p)  outil factice qui écrit sur stderr (`hPutChar`) avec rc 0 PUIS rc 1 :
#        refus SORTIE INCOMPLÈTE, rc 2 en `--hook`, le stderr rendu
#   (q)  outil factice rc 3 : ECHEC EXECUTION, rc 2 en `--hook`, rc 1 sinon
#   (r)  `locale` factice bavarde sur stderr : un `--hook` propre reste à ZÉRO
#        octet (la sonde de locale ne fuit pas dans le canal du hook)
#   (u)  outil factice qui écrit sur stderr en SUCCÈS (un wrapper bavard) : le
#        refus SORTIE INCOMPLÈTE nomme ses remèdes — locale UTF-8, nom hors
#        UTF-8 valide à renommer, binaire à appeler sans wrapper (B-3, A-4)
#   (s)  la locale choisie est EXPORTÉE vers l'outil, graphie VERBATIM, et
#        aucune n'est posée quand aucune candidate n'est UTF-8 — variables de
#        locale NON DÉFINIES (`env -u`), jamais vides : une variable héritée
#        vide garde son attribut export et masquerait un `export` retiré
#
# HÔTE-DÉPENDANCE, DITE : (i)(n)(n2) n'échouent que là où l'outil plante sous C
# (0.10.0, glibc) ; brew 0.11.0 écrit la ligne entière sous C. Les factices
# (o)(p)(q)(r)(s)(u) rougissent partout sur le scanner d'avant le correctif.
# Sans locale UTF-8 sur l'hôte (UTF8_DISPO=0, musl/busybox), (i)(n)(n2)
# acceptent un refus SORTIE INCOMPLÈTE au même rc : le banc n'y prouve pas le
# correctif, il prouve seulement qu'aucun « propre » n'est rendu.
#
# Aucun `git init`, aucun balayage d'arbre : chaque arm passe par `--hook
# <fichier>` ou une cible explicite sous $TMP, donc ni python ni dépôt requis.
#
# Exit : 0 tout passe · 1 au moins un cas échoue.
# ============================================================================
set -uo pipefail

# Un banc lancé depuis un hook git hérite de GIT_DIR (patron de
# `.githooks/commit-msg.test.sh`) : rien ici n'appelle git, et rien ne doit en
# hériter si un arm futur l'appelait.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"   # .agents/security -> .agents -> racine
SCAN="$ROOT/.agents/security/shellcheck-scan.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
ok() { echo "  ok: $1"; pass=$((pass + 1)); }
ko() { echo "  KO: $1"; fail=$((fail + 1)); }

[ -f "$SCAN" ] || { echo "FAIL: $SCAN absent"; exit 1; }

# contient <texte> <motif> : motif LITTÉRAL (grep -F), jamais une regex.
contient() { printf '%s' "$1" | grep -qF -- "$2"; }

# fabrique <rép> <nom> <corps> : un exécutable factice sous $TMP, sur le modèle
# de l'espion de la suite gelée. Le corps est écrit tel quel sous le shebang.
fabrique() {
  mkdir -p "$1"
  { printf '#!/usr/bin/env bash\n'; printf '%s\n' "$3"; } > "$1/$2"
  chmod +x "$1/$2"
}

# trace : ce que le `shellcheck` factice de (s) a reçu dans LC_ALL.
trace() {
  if [ -f "$TMP/trace" ]; then
    cat "$TMP/trace"
  else
    printf '<absente>'
  fi
}

# L'ORACLE D'UNE AUTRE MÉTHODE que le choix du scanner : le scanner VÉRIFIE des
# candidates (`locale charmap`), ce banc COMPTE ce que `locale -a` liste. Deux
# lectures distinctes, pour qu'une candidate oubliée rougisse au lieu de
# s'accorder avec elle-même.
UTF8_DISPO=0
if command -v locale >/dev/null 2>&1; then
  UTF8_DISPO="$(locale -a 2>/dev/null | grep -ciE '^(C|en_US)[.]utf-?8$')"
  [ -n "$UTF8_DISPO" ] || UTF8_DISPO=0
fi
echo "  note: UTF8_DISPO=$UTF8_DISPO (locales C ou en_US UTF-8 listées par locale -a)"

# verdict_non_ascii <rc attendu> <rc> <sortie> <chemin> : le bon verdict sur un
# nom non ASCII est le rc attendu ET SC2164 ET la ligne `<nom de base>:2:1` —
# le nom de base, parce que `shellcheck.exe` (Git Bash) écrit `C:\…` là où le
# banc a un chemin POSIX. Sinon, SEULEMENT sur un hôte sans locale UTF-8, un
# refus nommé SORTIE INCOMPLÈTE au même rc. Jamais un « propre ».
verdict_non_ascii() {
  if contient "$3" ': propre'; then
    return 1
  fi
  [ "$2" -eq "$1" ] || return 1
  if contient "$3" 'SC2164' && contient "$3" "${4##*/}:2:1"; then
    return 0
  fi
  [ "$UTF8_DISPO" -eq 0 ] && contient "$3" 'SORTIE INCOMPLÈTE'
}

printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$TMP/mord.sh"
printf '#!/usr/bin/env bash\necho sain\n' > "$TMP/propre.sh"

# --- (i) durci, (n), (n2) — le VRAI outil sur un nom non ASCII ---------------
if command -v shellcheck >/dev/null 2>&1; then
  DANS="$TMP/a b'é.sh"
  printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$DANS"

  out="$(bash "$SCAN" --hook "$DANS" 2>&1)"; rc=$?
  if verdict_non_ascii 2 "$rc" "$out" "$DANS"; then
    ok "(i) durci : nom non ASCII, locale héritée : rc 2, SC2164 et la ligne <nom>:2:1"
  else
    ko "(i) durci : attendu rc 2 + SC2164 + ${DANS##*/}:2:1, obtenu rc=$rc [$out]"
  fi

  out="$(LC_ALL=C LANG=C bash "$SCAN" --hook "$DANS" 2>&1)"; rc=$?
  if verdict_non_ascii 2 "$rc" "$out" "$DANS"; then
    ok "(n) nom non ASCII sous LC_ALL=C : rc 2, SC2164 et la ligne <nom>:2:1"
  else
    ko "(n) nom non ASCII sous LC_ALL=C : attendu rc 2 + SC2164 + ${DANS##*/}:2:1, obtenu rc=$rc [$out]"
  fi

  # SOUS-SHELL : le `cd` ne doit pas déplacer le cwd des arms suivants (C3).
  mkdir -p "$TMP/rel"
  printf '#!/usr/bin/env bash\ncd /tmp\necho ok\n' > "$TMP/rel/é.sh"
  out="$(cd "$TMP/rel" && LC_ALL=C LANG=C bash "$SCAN" 'é.sh' 2>&1)"; rc=$?
  if verdict_non_ascii 1 "$rc" "$out" 'é.sh'; then
    ok "(n2) nom RELATIF non ASCII, mode ciblé, sous C : rc 1, la ligne é.sh:2:1, jamais propre"
  else
    ko "(n2) nom relatif non ASCII sous C : attendu rc 1 + SC2164 + é.sh:2:1, obtenu rc=$rc [$out]"
  fi

  # --- (r) la sonde de locale ne fuit pas dans le canal du hook --------------
  # Une `locale` qui se plaint sur stderr ET ne rend aucune UTF-8 : le vrai
  # outil tourne alors sous la locale héritée, sur un fichier ASCII propre.
  # UN fichier, pas l'arbre : (b)/(c) de la suite gelée portent déjà l'arbre.
  fabrique "$TMP/s_r" locale 'printf "%s\n" "locale: Cannot set LC_CTYPE to default locale: No such file or directory" >&2
printf "%s\n" "ANSI_X3.4-1968"'
  out="$(PATH="$TMP/s_r:$PATH" bash "$SCAN" --hook "$TMP/propre.sh" 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | wc -c | tr -d ' ')"
  if [ "$rc" -eq 0 ] && [ "$n" -eq 0 ]; then
    ok "(r) locale bavarde sur stderr : --hook propre rend rc 0 et ZÉRO octet"
  else
    ko "(r) locale bavarde : attendu rc 0 et zéro octet, obtenu rc=$rc, $n octets [$out]"
  fi
else
  echo "  SKIP (i)(n)(n2)(r) : shellcheck absent — le vrai outil sur un nom non ASCII n'est PAS mesuré ici"
fi

# --- (o) outil rc 1 MUET : jamais « propre » ---------------------------------
# rc 1 dit « findings », et aucune ligne n'est arrivée : la sortie est perdue,
# pas vide. Le scanner d'avant comptait N=0 et rendait « propre », rc 0.
fabrique "$TMP/s_o" shellcheck 'exit 1'
out="$(PATH="$TMP/s_o:$PATH" bash "$SCAN" "$TMP/mord.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 1 ] && contient "$out" 'SORTIE INCOMPLÈTE' && ! contient "$out" ': propre'; then
  ok "(o) outil rc 1 muet : refus SORTIE INCOMPLÈTE, rc 1, jamais propre"
else
  ko "(o) outil rc 1 muet : attendu rc 1 + SORTIE INCOMPLÈTE sans propre, obtenu rc=$rc [$out]"
fi

# --- (p) stderr NON VIDE : refus, quel que soit le rc ------------------------
# Le rc d'un plantage d'écriture n'est pas mesuré (M5) : joué à 0 PUIS à 1. Une
# ligne partielle sur stdout donne N=1, donc le compte seul ne voit rien.
fabrique "$TMP/s_p" shellcheck 'if [ "${1-}" = -f ]; then
  printf "%s\n" "mord.sh:2:1: warning: Use"
  printf "%s\n" "shellcheck: <stdout>: hPutChar: invalid argument (invalid character)" >&2
fi
exit "${RC_FAUX:-0}"'
for RC_FAUX in 0 1; do
  out="$(RC_FAUX="$RC_FAUX" PATH="$TMP/s_p:$PATH" bash "$SCAN" --hook "$TMP/mord.sh" 2>&1)"; rc=$?
  if [ "$rc" -eq 2 ] && contient "$out" 'SORTIE INCOMPLÈTE' && contient "$out" 'hPutChar'; then
    ok "(p) stderr non vide, outil rc $RC_FAUX : --hook refuse SORTIE INCOMPLÈTE, rc 2, stderr rendu"
  else
    ko "(p) stderr non vide, outil rc $RC_FAUX : attendu rc 2 + SORTIE INCOMPLÈTE + hPutChar, obtenu rc=$rc [$out]"
  fi
done

# --- (u) le refus nomme ses REMÈDES ------------------------------------------
# Un wrapper (shim npm, snap) qui écrit sur stderr en SUCCÈS déclenche le refus à
# chaque appel (B-3) ; un nom hors UTF-8 valide fait planter l'outil même sous
# C.UTF-8 (A-4, mesuré sur 0.11.0). Le refus doit dire quoi faire, pas seulement
# refuser : les trois remèdes, jugés en texte LITTÉRAL.
fabrique "$TMP/s_u" shellcheck 'printf "%s\n" "npm WARN config: wrapper bavard" >&2
exit 0'
out="$(PATH="$TMP/s_u:$PATH" bash "$SCAN" --hook "$TMP/propre.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 2 ] && contient "$out" 'SORTIE INCOMPLÈTE' \
  && contient "$out" 'relancer sous LC_ALL=C.UTF-8' \
  && contient "$out" 'renommez le fichier' \
  && contient "$out" 'appelez le binaire directement'; then
  ok "(u) wrapper bavard en succès : refus SORTIE INCOMPLÈTE, rc 2, les trois remèdes nommés"
else
  ko "(u) wrapper bavard : attendu rc 2 + SORTIE INCOMPLÈTE + remèdes locale / renommer / binaire direct, obtenu rc=$rc [$out]"
fi

# --- (q) outil rc 3 : ECHEC EXECUTION, au code de refus du mode --------------
# En `--hook`, seul un exit 2 va au MODÈLE : un refus rendu en 1 n'est jamais lu.
fabrique "$TMP/s_q" shellcheck 'exit 3'
out="$(PATH="$TMP/s_q:$PATH" bash "$SCAN" --hook "$TMP/mord.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 2 ] && contient "$out" 'ECHEC EXECUTION'; then
  ok "(q) outil rc 3 en --hook : ECHEC EXECUTION, rc 2 (rendu au modèle)"
else
  ko "(q) outil rc 3 en --hook : attendu rc 2 + ECHEC EXECUTION, obtenu rc=$rc [$out]"
fi
out="$(PATH="$TMP/s_q:$PATH" bash "$SCAN" "$TMP/mord.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 1 ] && contient "$out" 'ECHEC EXECUTION'; then
  ok "(q) outil rc 3 en mode ciblé : ECHEC EXECUTION, rc 1"
else
  ko "(q) outil rc 3 en mode ciblé : attendu rc 1 + ECHEC EXECUTION, obtenu rc=$rc [$out]"
fi

# --- (s) la locale choisie ATTEINT l'outil, graphie VERBATIM -----------------
# `locale` factice : UTF-8 pour la seule graphie LOC_OK. `shellcheck` factice :
# écrit le LC_ALL qu'il a REÇU. macOS n'accepte que `C.UTF-8` : une graphie
# normalisée par le scanner rougit ici. `aucune` : rien ne doit être posé.
# LA TRACE SEULE est jugée, jamais le rc ni la sortie : la `locale` factice
# affirme une graphie que l'hôte peut ne pas avoir, et bash lui-même écrit
# alors `setlocale: … cannot change locale` sur stderr — mesuré sur macOS pour
# `C.utf8` et `en_US.utf8`, au refus SORTIE INCOMPLÈTE, rc 2 : la réponse
# prudente à une `locale` qui ment. Le zéro octet d'un hook propre est porté
# par (r), et par (c) de la suite gelée.
fabrique "$TMP/s_s" locale 'if [ "${LC_ALL-}" = "${LOC_OK-}" ]; then
  printf "%s\n" "UTF-8"
else
  printf "%s\n" "ANSI_X3.4-1968"
fi'
fabrique "$TMP/s_s" shellcheck 'if [ "${1-}" = -f ]; then
  printf "%s" "${LC_ALL-}" > "$LC_TRACE"
fi
exit 0'
for LOC_OK in C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8 aucune; do
  rm -f "$TMP/trace"
  attendu="$LOC_OK"
  [ "$LOC_OK" = aucune ] && attendu=""
  out="$(env -u LC_ALL -u LANG -u LC_CTYPE LOC_OK="$LOC_OK" LC_TRACE="$TMP/trace" PATH="$TMP/s_s:$PATH" bash "$SCAN" --hook "$TMP/propre.sh" 2>&1)"; rc=$?
  if [ -f "$TMP/trace" ] && [ "$(trace)" = "$attendu" ]; then
    ok "(s) candidate $LOC_OK : l'outil reçoit LC_ALL=[$attendu], verbatim, sous env -u"
  else
    ko "(s) candidate $LOC_OK : attendu LC_ALL=[$attendu] chez l'outil ; obtenu trace=[$(trace)], rc=$rc [$out]"
  fi
done

echo
echo "shellcheck-scan-locale: $pass passed / $fail failed"
[ "$fail" -eq 0 ] || exit 1
