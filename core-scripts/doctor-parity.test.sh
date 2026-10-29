#!/usr/bin/env bash
# ============================================================================
# PARITÉ INVENTAIRE <-> ARBRE (T-00001001, BK-343) — chaque outil que le kit
# SONDE est-il dans core-scripts/tool-inventory.tsv, que lit core-scripts/doctor.sh ?
#
# Le suffixe `.test.sh` EST l'inscription : core-scripts/run-bash-tests.sh le
# découvre (CI et core-scripts/verify.sh). Aucune entrée de manifeste.
#
# LE BALAYAGE — cinq formes de sonde, lues comme du TEXTE (rien n'est exécuté ;
# la SEULE exécution du banc est core-scripts/doctor.sh lui-même, au cas 10, en
# mode kit, sonde VIDE : aucun outil inventorié n'est lancé),
# sous .agents/ core-scripts/ .claude/hooks/ .codex/ .gemini/ .githooks/, hors
# node_modules/, vendor/, backups/ et .agents/state/ (racines et élagage tenus
# par l'arm 6bis) ; lignes de commentaire ôtées, sauf pour les directives :
#   (a) `command -v <jeton>` dans les .sh — une chaîne de fixture COMPTE, et un
#       `\n` littéral qui la précède est une frontière de mot ;
#   (b) `have <jeton>` dans les SEULS .sh qui DÉFINISSENT `have()` (ailleurs,
#       « have » est de la prose) ;
#   (c) `shutil.which("<jeton>")` dans les .py ;
#   (d) les directives d'en-tête du runner (requires, optional, allows-missing) ;
#   (e) `Get-Command <jeton>` dans les .ps1 — la jambe PowerShell, lue comme du
#       texte : pwsh n'est jamais lancé, donc rien ne saute faute de lui.
# Un jeton non littéral (`$…`, variable Python) est EXCLU ET COMPTÉ.
# BORNES DU BALAYAGE, nommées : `agentic_v3/` et `.agents/vendor/agentic_v3/`,
# `src/` et les fichiers sans
# extension (`.githooks/pre-push`, `commit-msg`) ne sont pas lus ; `type -P`,
# `which` et `hash` ne sont pas des formes de sonde reconnues — la sonde de
# core-scripts/doctor.sh elle-même (`type -P` sur une variable) n'est pas lue.
#
# LES RÈGLES (cas 8) — un FAIL chacune :
#   R1  jeton sondé hors (inventaire ∪ INTERNES) — alias `a|b` expansés ;
#   R2  `probe` ≠ `-` : son ancre tire EXACTEMENT une ligne de son fichier,
#       cherchée sous la racine balayée, quels que soient les sites littéraux ;
#   R3  INTERNES (liste fermée de l'en-tête du TSV) : un jeton que rien ne sonde
#       est MORT ;
#   R4  balayage vide ;
#   R5  ligne outil sans site balayé ni `probe`, HORS de la liste fermée
#       SANS_SITE (une sonde perdue, ou une ligne que rien ne sonde) ;
#   R6  jeton de SANS_SITE qui gagne un site ou une `probe` : la liste ne
#       vieillit pas, elle se raccourcit.
# SANS_SITE (forme EXEMPT de .agents/evals/test_no_compact_case.py) : liste
# FERMÉE et DATÉE des lignes outil sondées par une forme HORS balayage —
# `import`/module, variable, comportement, ou un fichier non balayé (plan
# T-00000529, ouvert n° 7) —, un jeton et SA raison par entrée. Une entrée sans
# raison, ou qui n'est plus une ligne outil de l'inventaire, est un FAIL.
#
# CE BANC VOYAGE (décision pilote S-00004600, option a) ET S'ÉCRIT POUR PASSER
# CHEZ L'ADOPTANT. Il ne lit que des fichiers qui voyagent (l'inventaire et les
# répertoires balayés), et les règles tiennent sur l'arbre que le canal
# livre. UNE différence, nommée : le marqueur du kit est retenu par le canal ;
# sans lui (arbre adoptant), R1, R5 et R6 deviennent des CONSTATS — un adoptant
# qui ajoute sa propre sonde sous ces répertoires, ou que le canal prive d'un
# site, ne peut pas éditer l'inventaire du kit. R2, R3, R4 et la validité de
# SANS_SITE restent des échecs partout ; le cas 10 n'est asserté qu'en mode kit.
# LE DISCRIMINANT EST FONDÉ AVANT D'ÊTRE LU : .template-exclude, qui VOYAGE,
# doit porter la ligne `strip:` du chemin du marqueur ; sinon FAIL — un chemin
# de marqueur faux basculerait en silence le kit en mode adoptant laxiste.
# Sans .template-exclude (un adoptant peut l'avoir retiré) : FAIL si le
# marqueur est présent, une ligne info sinon — l'arbre est adoptant.
# Mesuré le 2026-10-08 sur l'arbre adoptant reconstruit (prédicat de
# .agents/evals/test_adopting_gate.py) : mêmes quatre jetons SANS_SITE qu'en
# mode kit, 244 sites contre 248. Le 2026-10-16, mktemp quitte la liste (R6 :
# site gagné dans .agents/security/semgrep-scan.test.sh, passé depuis
# T-01M55Z3W38 dans .agents/security/semgrep-scan-git.test.sh, qu'aucune ligne
# de .template-exclude ne retient) — trois jetons ; arbre adoptant non remesuré.
#
# DOCTOR_PARITY_TREE=<dir> change UNIQUEMENT la racine balayée du cas 8 (défaut :
# la racine de ce dépôt) ; l'arm 3bis prouve que le chemin de code est le même.
# L'arm 3ter joue le MODE CALCULÉ (les autres arms le passent en littéral) :
# un calcul du mode faussé rougit, dans le kit comme chez l'adoptant.
#
# Exit : 0 tous les cas passent · 1 au moins un cas échoue.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

INV="$ROOT/core-scripts/tool-inventory.tsv"
TREE="${DOCTOR_PARITY_TREE:-$ROOT}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok() { echo "--- PASS $1"; pass=$((pass + 1)); }
ko() { echo "--- FAIL $1"; fail=$((fail + 1)); }
montre() { sed 's/^/      /' "$1"; }

# --- le balayage -------------------------------------------------------------
# dp_sites <racine> : une ligne par site, `forme TAB fichier TAB jeton` ; un
# jeton non littéral sort en `x TAB forme TAB fichier TAB jeton`.
dp_sites() {
  local w
  w="$(mktemp -d "$TMP/s.XXXXXX")"
  (
    cd "$1" || exit 1
    find .agents core-scripts .claude/hooks .codex .gemini .githooks \
      \( -name node_modules -o -name vendor -o -name backups -o -path .agents/state \) -prune \
      -o -type f \( -name '*.sh' -o -name '*.py' -o -name '*.ps1' \) -print 2>/dev/null > "$w/liste"
    : > "$w/have"
    if [ -s "$w/liste" ]; then
      tr '\n' '\000' < "$w/liste" | xargs -0 grep -l -E '^[[:space:]]*have[[:space:]]*\(\)' > "$w/have" 2>/dev/null
      tr '\n' '\000' < "$w/liste" | xargs -0 awk -v hf="$w/have" '
        BEGIN { while ((getline l < hf) > 0) H[l] = 1 }
        function emit(f, t) {
          if (t ~ /[$]/ || t == "") print "x\t" f "\t" FILENAME "\t" t
          else print f "\t" FILENAME "\t" t
        }
        FNR == 1 { sh = (FILENAME ~ /[.]sh$/); py = (FILENAME ~ /[.]py$/); ps = (FILENAME ~ /[.]ps1$/) }
        {
          line = $0
          sub(/\r$/, "", line)
          if (sh && line ~ /^[[:space:]]*#[[:space:]]*(requires|optional|allows-missing):/) {
            d = line
            sub(/^[[:space:]]*#[[:space:]]*[a-z-]+:[[:space:]]*/, "", d)
            n = split(d, w, /[[:space:]]+/)
            for (i = 1; i <= n; i++) if (w[i] != "") emit("d", w[i])
            next
          }
          if (line ~ /^[[:space:]]*#/) next
          if (sh) {
            rest = " " line
            gsub(/\\n/, " ", rest)
            while (match(rest, /[^A-Za-z0-9_]command[[:space:]]+-v[[:space:]]+"?[$A-Za-z0-9_.+-]+/)) {
              s = substr(rest, RSTART, RLENGTH); rest = substr(rest, RSTART + RLENGTH)
              sub(/^.*-v[[:space:]]+"?/, "", s); emit("a", s)
            }
            if (FILENAME in H) {
              rest = " " line
              while (match(rest, /[^A-Za-z0-9_]have[[:space:]]+"?[$A-Za-z0-9_.+-]+/)) {
                s = substr(rest, RSTART, RLENGTH); rest = substr(rest, RSTART + RLENGTH)
                sub(/^.*have[[:space:]]+"?/, "", s); emit("b", s)
              }
            }
          }
          if (py) {
            rest = line
            while (match(rest, /shutil[.]which[(][^)]*/)) {
              s = substr(rest, RSTART + 13, RLENGTH - 13); rest = substr(rest, RSTART + RLENGTH)
              if (match(s, /^[[:space:]]*["\047][^"\047]+["\047]/)) {
                t = substr(s, RSTART, RLENGTH); gsub(/[[:space:]"\047]/, "", t); emit("c", t)
              } else {
                v = s; sub(/[,[:space:]].*$/, "", v); print "x\tc\t" FILENAME "\t" v
              }
            }
          }
          if (ps) {
            rest = line
            while (match(rest, /Get-Command[[:space:]]+(-Name[[:space:]]+)?"?[$A-Za-z0-9_.+-]+/)) {
              s = substr(rest, RSTART, RLENGTH); rest = substr(rest, RSTART + RLENGTH)
              sub(/^Get-Command[[:space:]]+(-Name[[:space:]]+)?"?/, "", s); emit("e", s)
            }
          }
        }'
    fi
  )
}

# dp_check <sites> <racine> <tsv> <kit|adoptant> [sans-site] : lignes FAIL /
# note / info, rc 1 si au moins un FAIL. R1, R3, R4, R5, R6 en awk ; R2 (les
# ancres `probe`) ici. [sans-site] : fichier `jeton : raison` (voir SANS_SITE) ;
# absent, la liste est VIDE — toute ligne outil sans site est alors R5.
dp_check() {
  local sites="$1" racine="$2" tsv="$3" mode="$4" ssf="${5:-}" rc=0 out tool probe pf pa n
  out="$(awk -F'\t' -v mode="$mode" -v ssf="$ssf" '
    function regle(msg) {
      if (mode == "kit") { print "FAIL\t" msg; bad = 1 }
      else print "note\t" msg " (constat sur un arbre adoptant)"
    }
    BEGIN {
      if (ssf != "") while ((getline l < ssf) > 0) { t = l; sub(/[[:space:]].*$/, "", t); if (t != "") ss[t] = 1 }
    }
    FNR == 1 { f++ }
    f == 1 {
      sub(/\r$/, "")
      if ($0 ~ /^# INTERNES/) { inint = 1; next }
      if (inint && $0 ~ /^#[[:space:]][[:space:]]/) { ibuf = ibuf " " substr($0, 2); next }
      inint = 0
      if ($0 ~ /^#/) next
      if (!hdr) {
        hdr = 1
        for (i = 1; i <= NF; i++) c[$i] = i
        if (!("tool" in c) || !("nature" in c) || !("probe" in c)) { print "FAIL\tinventaire sans colonne tool, nature ou probe"; bad = 1; dead = 1 }
        next
      }
      if (dead || $0 ~ /^[[:space:]]*$/ || $c["nature"] != "outil") next
      nl++; tool[nl] = $c["tool"]; probe[nl] = $c["probe"]
      n = split($c["tool"], al, "|")
      for (k = 1; k <= n; k++) inv[al[k]] = 1
      next
    }
    $1 == "x" { nx++; next }
    {
      ns++
      if (!($3 in seen)) nseen++
      seen[$3] = 1
      where[$3] = where[$3] " " $2 " (forme " $1 ")"
    }
    END {
      gsub(/[(][^)]*[)]/, " ", ibuf); gsub(/·/, " ", ibuf); gsub(/[|]/, " ", ibuf)
      ni = split(ibuf, it, /[[:space:]]+/)
      for (k = 1; k <= ni; k++) { t = it[k]; sub(/[.]$/, "", t); if (t ~ /[A-Za-z0-9]/) { internes[t] = 1; nint++ } }
      if (ns == 0) { print "FAIL\tR4 balayage vide : aucune sonde lue sous la racine, le filet ne mesure rien"; bad = 1 }
      for (t in seen) {
        if ((t in inv) || (t in internes)) continue
        if (mode == "kit") { print "FAIL\tR1 jeton sondé non inventorié : " t " —" where[t]; bad = 1 }
        else print "note\tR1 jeton sondé hors inventaire, constat sur un arbre adoptant : " t " —" where[t]
      }
      for (t in internes) if (!(t in seen)) { print "FAIL\tR3 INTERNES mort : retire `" t "` de INTERNES ou nomme sa sonde"; bad = 1 }
      for (k = 1; k <= nl; k++) {
        n = split(tool[k], al, "|"); s = 0
        for (j = 1; j <= n; j++) if (al[j] in seen) s = 1
        if (probe[k] != "-") print "PROBE\t" tool[k] "\t" probe[k]
        if (tool[k] in ss) {
          if (s || probe[k] != "-") regle("R6 jeton de SANS_SITE qui gagne un site ou une probe : " tool[k] " — retire-le de la liste")
          else sans = sans " " tool[k]
        } else if (!s && probe[k] == "-") regle("R5 ligne outil sans site balayé ni probe, hors SANS_SITE : " tool[k])
      }
      print "info\t" ns " sites, " nseen " jetons littéraux, " nx " jetons non littéraux exclus et comptés, " nint " jetons INTERNES"
      print "info\tlignes outil sans site balayé ni probe, toutes dans SANS_SITE :" (sans == "" ? " aucune" : sans)
      exit bad
    }
  ' "$tsv" "$sites")" || rc=1
  printf '%s\n' "$out" | grep -v '^PROBE' | sort
  while IFS="$(printf '\t')" read -r _ tool probe; do
    [ -n "$tool" ] || continue
    pf="${probe%%:*}"
    pa="${probe#*:}"
    if [ ! -f "$racine/$pf" ]; then
      printf 'FAIL\tR2 probe de %s : fichier %s absent sous la racine\n' "$tool" "$pf"
      rc=1
      continue
    fi
    n="$(grep -c -F -- "$pa" "$racine/$pf")"
    if [ "$n" -ne 1 ]; then
      printf 'FAIL\tR2 probe de %s : l ancre « %s » tire %s lignes de %s (attendu 1)\n' "$tool" "$pa" "$n" "$pf"
      rc=1
    fi
  done <<< "$(printf '%s\n' "$out" | grep '^PROBE')"
  return "$rc"
}

# ---------------------------------------------------------------------------
# CAS 8 — l'arbre réel (ou DOCTOR_PARITY_TREE) contre l'inventaire réel
# ---------------------------------------------------------------------------
# adopting-tree: le marqueur du kit est `strip:` — son ABSENCE désigne un arbre adoptant, et choisit le mode
# Le discriminant est FONDÉ avant d'être lu (mutant m7b de l'exec-critic,
# S-00004476 : un chemin de marqueur muté passait vert en mode adoptant).
MARQUEUR='.agents/IS_THE_KIT'
if [ -f "$ROOT/.template-exclude" ]; then
  grep -qxF "strip: $MARQUEUR" "$ROOT/.template-exclude" \
    || ko "cas 8 : discriminant kit/adoptant non fondé — « strip: $MARQUEUR » absent de .template-exclude"
elif [ -f "$ROOT/$MARQUEUR" ]; then
  ko "cas 8 : discriminant kit/adoptant non fondé — marqueur $MARQUEUR présent sans .template-exclude"
else
  echo "  info : .template-exclude absent, marqueur absent — arbre adoptant, discriminant non relu"
fi
if [ -f "$ROOT/$MARQUEUR" ]; then
  MODE=kit
else
  MODE=adoptant
fi

# SANS_SITE — LISTE FERMÉE ET DATÉE (relevé du 2026-10-08 à BASE ffbf7f07,
# T-00001001). `jeton : raison`, une entrée par ligne. Ne se rallonge qu'avec SA
# raison ; R6 la raccourcit dès qu'un jeton gagne un site.
# 2026-10-16 : mktemp retiré par R6 — site `command -v mktemp` (forme a) gagné
# dans .agents/security/semgrep-scan.test.sh (43fc52f9), passé dans
# .agents/security/semgrep-scan-git.test.sh par la scission T-01M55Z3W38 ;
# quatre jetons → trois.
sans_site() {
  printf '%s\n' \
    'pytest : exécuté comme module, `"$PY" -m pytest` (core-scripts/run-pytest-shards.sh) — aucune sonde par nom' \
    'yarn : sondé par VARIABLE, `shutil.which(nom)` (.agents/bin/porte_adoptant.py) — jeton non littéral, exclu' \
    'corepack : lancé par .github/workflows/ci.yml (job adoptant, `corepack enable`), répertoire non balayé'
}
# ss_valide <liste> <tsv> : FAIL par entrée sans raison, ou dont le jeton n'est
# plus une ligne outil du TSV (exemption périmée) ; rc 1 si au moins un FAIL.
ss_valide() {
  awk -F'\t' '
    FNR == 1 { f++ }
    f == 1 {
      if ($0 !~ /^[A-Za-z0-9][A-Za-z0-9._+-]* : .*[^[:space:]]/) { print "FAIL\tSANS_SITE entrée sans raison : " $0; bad = 1; next }
      t = $0; sub(/ .*$/, "", t); ent[++ne] = t; next
    }
    /^#/ { next }
    !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
    $c["nature"] == "outil" { outil[$c["tool"]] = 1 }
    END {
      for (k = 1; k <= ne; k++) if (!(ent[k] in outil)) { print "FAIL\tSANS_SITE exemption périmée : " ent[k] " n est plus une ligne outil de l inventaire"; bad = 1 }
      exit bad
    }
  ' "$1" "$2"
}
sans_site > "$TMP/sans_site"
ss_valide "$TMP/sans_site" "$INV" > "$TMP/o8ss"; rc=$?
if [ "$rc" -eq 0 ] && ! grep -q '^FAIL' "$TMP/o8ss"; then
  ok "cas 8 : SANS_SITE — $(grep -c . "$TMP/sans_site") entrées, chacune avec sa raison, chacune une ligne outil de l'inventaire"
else
  ko "cas 8 : SANS_SITE invalide (rc=$rc)"
  montre "$TMP/o8ss"
fi

echo "  racine balayée : $TREE — mode $MODE"
dp_sites "$TREE" > "$TMP/sites_reel"
dp_check "$TMP/sites_reel" "$TREE" "$INV" "$MODE" "$TMP/sans_site" > "$TMP/o8"; rc=$?
if [ "$rc" -eq 0 ] && ! grep -q '^FAIL' "$TMP/o8"; then
  ok "cas 8 : parité inventaire <-> arbre ($MODE) — R1 à R6 tenues"
  sed -n 's/^info\t/  info : /p; s/^note\t/  note : /p' "$TMP/o8"
else
  ko "cas 8 : parité inventaire <-> arbre ($MODE, rc=$rc)"
  montre "$TMP/o8"
fi

# --- matériaux des arms -------------------------------------------------------
# TSV-FIXTURE : l'en-tête du TSV réel SANS le bloc INTERNES, la ligne de
# colonnes, la PREMIÈRE ligne outil, `probe` forcée à `-`. Rejouée à la main
# contre les quatre règles : INTERNES vide (rien de mort), aucune probe (rien à
# résoudre), un jeton (balayage non vide).
awk -F'\t' -v OFS='\t' '
  /^# INTERNES/ { skip = 1; next }
  skip && /^#[[:space:]][[:space:]]/ { next }
  { skip = 0 }
  /^#/ { print; next }
  !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
  $c["nature"] == "outil" && !done { $c["probe"] = "-"; print; done = 1 }
' "$INV" > "$TMP/tsv_fixture"
T_OK="$(awk -F'\t' '/^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next } { split($c["tool"], a, "|"); print a[1]; exit }' "$TMP/tsv_fixture")"
T_KO="cowsay-t1001"

arbre_fixture() { # arbre_fixture <dir> <jeton> : un .sh qui définit have() et sonde <jeton> par (a) et (b)
  mkdir -p "$1/.agents"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'have() { command -v "$1" >/dev/null 2>&1; }'
    printf 'if have %s; then :; fi\n' "$2"
    printf '[ -n "$x" ] && command -v %s >/dev/null\n' "$2"
  } > "$1/.agents/x.sh"
}

attendu_fail() { # attendu_fail <libellé> <sortie> <rc> <motif littéral>…
  local lib="$1" o="$2" r="$3" m manque=""
  shift 3
  for m in "$@"; do
    grep -qF -- "$m" "$o" || manque="$manque [$m]"
  done
  if [ "$r" -ne 0 ] && [ -z "$manque" ]; then
    ok "$lib — rc $r"
  else
    ko "$lib (rc=$r, motifs absents :${manque:- aucun})"
    montre "$o"
  fi
}

# ---------------------------------------------------------------------------
# CAS 9 — le filet rougit, une règle à la fois
# ---------------------------------------------------------------------------
# arm 1 — R1 sur l'arbre réel : l'inventaire perd la ligne d'un outil SONDÉ.
T_RETIRE="$(awk -F'\t' 'NR == FNR { if ($1 != "x") s[$3] = 1; next }
  /^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["nature"] == "outil" && $c["tool"] !~ /[|]/ && ($c["tool"] in s) { print $c["tool"]; exit }' "$TMP/sites_reel" "$INV")"
awk -F'\t' -v t="$T_RETIRE" '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next } $c["tool"] != t { print }' "$INV" > "$TMP/tsv_arm1"
dp_check "$TMP/sites_reel" "$TREE" "$TMP/tsv_arm1" kit "$TMP/sans_site" > "$TMP/o9a"; rc=$?
attendu_fail "cas 9 arm 1 : $T_RETIRE retiré de l'inventaire — R1 le nomme" "$TMP/o9a" "$rc" "R1 jeton sondé non inventorié : $T_RETIRE"

# arm 2 — R2 : l'ancre de la première `probe` est fausse ; les sites littéraux
# du même outil n'exonèrent pas.
P_TOOL="$(awk -F'\t' '/^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next } $c["probe"] != "-" { print $c["tool"]; exit }' "$INV")"
if [ -z "$P_TOOL" ]; then
  ko "cas 9 arm 2 : l'inventaire ne porte plus aucune probe — arm vacant"
else
  awk -F'\t' -v OFS='\t' -v t="$P_TOOL" '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
    $c["tool"] == t { p = $c["probe"]; sub(/:.*$/, "", p); $c["probe"] = p ":texte-inexistant-t1001" } { print }' "$INV" > "$TMP/tsv_arm2"
  dp_check "$TMP/sites_reel" "$TREE" "$TMP/tsv_arm2" kit "$TMP/sans_site" > "$TMP/o9b"; rc=$?
  attendu_fail "cas 9 arm 2 : probe de $P_TOOL sur une ancre inexistante — R2" "$TMP/o9b" "$rc" "R2 probe de $P_TOOL" "texte-inexistant-t1001"
fi

# arm 3 — R1 sur un arbre-FIXTURE, formes (a) et (b), TSV-fixture.
arbre_fixture "$TMP/t3ko" "$T_KO"
dp_sites "$TMP/t3ko" > "$TMP/s3ko"
dp_check "$TMP/s3ko" "$TMP/t3ko" "$TMP/tsv_fixture" kit > "$TMP/o9c"; rc=$?
attendu_fail "cas 9 arm 3 : $T_KO sondé par une fixture — R1 le nomme, formes a et b" "$TMP/o9c" "$rc" \
  "R1 jeton sondé non inventorié : $T_KO" "(forme a)" "(forme b)"

# arm 3, témoin positif — même fixture, jeton inventorié ($T_OK), même TSV-fixture.
arbre_fixture "$TMP/t3ok" "$T_OK"
dp_sites "$TMP/t3ok" > "$TMP/s3ok"
dp_check "$TMP/s3ok" "$TMP/t3ok" "$TMP/tsv_fixture" kit > "$TMP/o9d"; rc=$?
if [ -n "$T_OK" ] && [ "$rc" -eq 0 ] && ! grep -q '^FAIL' "$TMP/o9d"; then
  ok "cas 9 arm 3 : témoin positif — fixture sondant $T_OK, TSV-fixture, rc 0"
else
  ko "cas 9 arm 3 : témoin positif rouge ($T_OK, rc=$rc)"
  montre "$TMP/o9d"
fi

# arm 3bis — même fixture, TSV RÉEL : R3 tire par le chemin fixture, donc la
# racine balayée est la SEULE chose que change la fixture.
dp_check "$TMP/s3ok" "$TMP/t3ok" "$INV" kit > "$TMP/o9e"; rc=$?
attendu_fail "cas 9 arm 3bis : fixture + inventaire réel — R3 INTERNES mort" "$TMP/o9e" "$rc" "R3 INTERNES mort : retire"

# arm 3ter — le MODE CALCULÉ, jamais un littéral : marqueur présent => R1 FAIL ;
# marqueur absent => constat nommé, rc 0. Un mode forcé, dans un sens ou l'autre, rougit.
dp_check "$TMP/s3ko" "$TMP/t3ko" "$TMP/tsv_fixture" "$MODE" > "$TMP/o9c3"; rc=$?
if [ -f "$ROOT/$MARQUEUR" ]; then
  attendu_fail "cas 9 arm 3ter : mode calculé ($MODE), marqueur présent — R1 FAIL" "$TMP/o9c3" "$rc" "R1 jeton sondé non inventorié : $T_KO"
elif [ "$rc" -eq 0 ] && grep -qF "R1 jeton sondé hors inventaire, constat sur un arbre adoptant : $T_KO" "$TMP/o9c3"; then
  ok "cas 9 arm 3ter : mode calculé ($MODE), marqueur absent — constat nommé, rc 0"
else
  ko "cas 9 arm 3ter : mode calculé ($MODE), marqueur absent (rc=$rc)"
  montre "$TMP/o9c3"
fi

# arm 4 — R3 sur l'arbre réel : un jeton INTERNES que rien ne sonde.
awk '{ print } /^# INTERNES/ { print "#   foobar-t1001 (jeton de fixture du banc) ·" }' "$INV" > "$TMP/tsv_arm4"
dp_check "$TMP/sites_reel" "$TREE" "$TMP/tsv_arm4" kit "$TMP/sans_site" > "$TMP/o9f"; rc=$?
attendu_fail "cas 9 arm 4 : INTERNES + foobar-t1001 — R3 le nomme" "$TMP/o9f" "$rc" "R3 INTERNES mort : retire \`foobar-t1001\`"

# arm 5 — mode adoptant : R1 devient un constat (rc 0, nommé) ; R3 reste un FAIL.
dp_check "$TMP/s3ko" "$TMP/t3ko" "$TMP/tsv_fixture" adoptant > "$TMP/o9g"; rc=$?
if [ "$rc" -eq 0 ] && grep -qF "R1 jeton sondé hors inventaire, constat sur un arbre adoptant : $T_KO" "$TMP/o9g" && ! grep -q '^FAIL' "$TMP/o9g"; then
  ok "cas 9 arm 5 : arbre adoptant — $T_KO hors inventaire est un constat nommé, rc 0"
else
  ko "cas 9 arm 5 : mode adoptant (rc=$rc)"
  montre "$TMP/o9g"
fi
dp_check "$TMP/s3ok" "$TMP/t3ok" "$INV" adoptant > "$TMP/o9h"; rc=$?
attendu_fail "cas 9 arm 5 : arbre adoptant — R3 reste un échec" "$TMP/o9h" "$rc" "R3 INTERNES mort : retire"

# arm 6 — formes (c), (d), (e) et le `\n` littéral de (a), sur fixture.
bs='\'
mkdir -p "$TMP/t6/.agents" "$TMP/t6/core-scripts"
printf 'import shutil\nshutil.which("%s")\n' "cowsay-c" > "$TMP/t6/.agents/y.py"
printf '#!/usr/bin/env bash\n# %s: %s\n' "optional" "cowsay-d" > "$TMP/t6/core-scripts/z.test.sh"
printf '$a = Get-Command %s\n' "cowsay-e" > "$TMP/t6/.agents/w.ps1"
printf '%s\n' "printf 'x${bs}ncommand -v ${T_KO}-n >/dev/null'" > "$TMP/t6/.agents/v.sh"
dp_sites "$TMP/t6" > "$TMP/s6"
dp_check "$TMP/s6" "$TMP/t6" "$TMP/tsv_fixture" kit > "$TMP/o9i"; rc=$?
attendu_fail "cas 9 arm 6 : formes c, d, e et \\n littéral — chacune nommée" "$TMP/o9i" "$rc" \
  "non inventorié : cowsay-c — .agents/y.py (forme c)" \
  "non inventorié : cowsay-d — core-scripts/z.test.sh (forme d)" \
  "non inventorié : cowsay-e — .agents/w.ps1 (forme e)" \
  "non inventorié : ${T_KO}-n — .agents/v.sh (forme a)"

# arm 6bis — chaque RACINE balayée est lue, ni .agents/state/ ni le moteur
# aux deux emplacements ne le sont
# (S-00004538, C4 ; mutants D3 et D5 de plan-critic, S-00004518). Une sonde (a)
# par racine, chacune son jeton, nommée avec son fichier ; une de plus sous
# .agents/state/, que l'élagage doit taire. Le jeton passe TOUJOURS par `%s` :
# une forme (a) littérale écrite dans ce banc serait balayée par le cas 8.
mkdir -p "$TMP/t6b"
: > "$TMP/m6b"
for r6 in .agents core-scripts .claude/hooks .codex .gemini .githooks .agents/state agentic_v3 .agents/vendor/agentic_v3; do
  j6="sonde-$(printf '%s' "${r6#.}" | tr '/' '-')-t1001"
  mkdir -p "$TMP/t6b/$r6"
  printf 'command -v %s >/dev/null\n' "$j6" > "$TMP/t6b/$r6/x.sh"
  case "$r6" in
    .agents/state|agentic_v3|.agents/vendor/agentic_v3) ;;
    *) printf '%s\n' "R1 jeton sondé non inventorié : $j6 — $r6/x.sh (forme a)" >> "$TMP/m6b" ;;
  esac
done
dp_sites "$TMP/t6b" > "$TMP/s6b"
dp_check "$TMP/s6b" "$TMP/t6b" "$TMP/tsv_fixture" kit > "$TMP/o9n"; rc=$?
manque=""
while IFS= read -r m6; do
  grep -qF -- "$m6" "$TMP/o9n" || manque="$manque [$m6]"
done < "$TMP/m6b"
n6b="$(grep -c . "$TMP/m6b")"
lu6b="$(grep -c -F -- 'sonde-agents-state-t1001' "$TMP/s6b")"
lu6b_moteur="$(grep -c -E 'sonde-(agentic_v3|agents-vendor-agentic_v3)-t1001' "$TMP/s6b")"
if [ "$rc" -ne 0 ] && [ "$n6b" -eq 6 ] && [ -z "$manque" ] && [ "$lu6b" -eq 0 ] && [ "$lu6b_moteur" -eq 0 ]; then
  ok "cas 9 arm 6bis : une sonde par racine balayée ($n6b), chacune nommée ; état et moteur aux deux emplacements élagués — rc $rc"
else
  ko "cas 9 arm 6bis : racines non lues :${manque:- aucune} ; sites état : $lu6b ; sites moteur : $lu6b_moteur ($n6b racines, rc=$rc)"
  montre "$TMP/o9n"
fi

# arm 7 — R5 sur l'arbre réel : TOUS les sites d'un outil inventorié (sans
# alias, sans probe, hors SANS_SITE) retirés du relevé ; puis le même relevé en
# mode adoptant, où R5 devient un constat.
T_R5="$(awk -F'\t' 'NR == FNR { if ($1 != "x") s[$3] = 1; next }
  /^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["nature"] == "outil" && $c["tool"] !~ /[|]/ && $c["probe"] == "-" && ($c["tool"] in s) { print $c["tool"]; exit }' "$TMP/sites_reel" "$INV")"
if [ -z "$T_R5" ]; then
  ko "cas 9 arm 7 : aucun outil sondé sans alias ni probe — arm vacant"
else
  awk -F'\t' -v t="$T_R5" '$1 == "x" || $3 != t' "$TMP/sites_reel" > "$TMP/sites_arm7"
  dp_check "$TMP/sites_arm7" "$TREE" "$INV" kit "$TMP/sans_site" > "$TMP/o9j"; rc=$?
  attendu_fail "cas 9 arm 7 : sites de $T_R5 retirés — R5 le nomme" "$TMP/o9j" "$rc" \
    "R5 ligne outil sans site balayé ni probe, hors SANS_SITE : $T_R5"
  dp_check "$TMP/sites_arm7" "$TREE" "$INV" adoptant "$TMP/sans_site" > "$TMP/o9k"; rc=$?
  if [ "$rc" -eq 0 ] && grep -qF "R5 ligne outil sans site balayé ni probe, hors SANS_SITE : $T_R5 (constat" "$TMP/o9k" && ! grep -q '^FAIL' "$TMP/o9k"; then
    ok "cas 9 arm 7 : arbre adoptant — $T_R5 sans site est un constat nommé, rc 0"
  else
    ko "cas 9 arm 7 : R5 en mode adoptant (rc=$rc)"
    montre "$TMP/o9k"
  fi
fi

# arm 8 — R6, chaque jeton de SANS_SITE : un arbre-FIXTURE le sonde par la
# forme (a), son relevé est AJOUTÉ au relevé réel — la liste doit le refuser.
n8=0
while read -r t _; do
  [ -n "$t" ] || continue
  n8=$((n8 + 1))
  mkdir -p "$TMP/t8_$n8/.agents"
  printf 'command -v %s >/dev/null\n' "$t" > "$TMP/t8_$n8/.agents/x.sh"
  dp_sites "$TMP/t8_$n8" > "$TMP/s8_$n8"
  cat "$TMP/sites_reel" "$TMP/s8_$n8" > "$TMP/s8r_$n8"
  dp_check "$TMP/s8r_$n8" "$TREE" "$INV" kit "$TMP/sans_site" > "$TMP/o9l"; rc=$?
  attendu_fail "cas 9 arm 8 : $t (SANS_SITE) gagne un site — R6 le nomme" "$TMP/o9l" "$rc" \
    "R6 jeton de SANS_SITE qui gagne un site ou une probe : $t"
done < "$TMP/sans_site"
[ "$n8" -ge 1 ] || ko "cas 9 arm 8 : SANS_SITE vide — arm vacant"

# arm 9 — la liste elle-même : une entrée sans raison, une entrée périmée.
{
  cat "$TMP/sans_site"
  printf '%s\n' 'cowsay-t1001 : jeton de fixture, absent de l inventaire' 'tee'
} > "$TMP/sans_site_arm9"
ss_valide "$TMP/sans_site_arm9" "$INV" > "$TMP/o9m"; rc=$?
attendu_fail "cas 9 arm 9 : SANS_SITE — entrée sans raison et exemption périmée, chacune nommée" "$TMP/o9m" "$rc" \
  "SANS_SITE entrée sans raison : tee" "SANS_SITE exemption périmée : cowsay-t1001"

# ---------------------------------------------------------------------------
# CAS 10 — mode KIT : le seau 3 du ci.yml RÉEL contre une liste FERMÉE
# ---------------------------------------------------------------------------
# Paquets que la ligne apt de .github/workflows/ci.yml installe SANS ligne
# d'inventaire. Lus par doctor.sh LUI-MÊME (jamais une troisième copie du `sed`,
# que le cas 12 de doctor.test.sh tient à l'octet), sonde VIDE : aucun outil
# n'est exécuté. Liste FERMÉE, relevé du 2026-10-08 : jq — « INSTALLÉ SANS
# BESOIN MESURÉ » (en-tête de l'inventaire, retrait à ouvrir). Un paquet de plus
# ROUGIT ; jq retiré de la ligne apt rougit aussi : la liste se met à jour.
# Chez un adoptant (ci.yml réécrit), rien n'est asserté — capacité nommée dans
# l'en-tête de doctor.test.sh.
SEAU3_FERME=' jq'
seau3() { # seau3 <ci.yml> <sortie> : le seau 3 imprimé par doctor.sh
  mkdir -p "$TMP/vide10"
  env DOCTOR_OS=linux "DOCTOR_PROBE_PATH=$TMP/vide10" bash "$ROOT/core-scripts/doctor.sh" --ci "$1" > "$2" 2>&1
  sed -n 's/^  seau 3 — installés par la ligne apt, NON inventoriés ://p' "$2"
}
if [ "$MODE" = "kit" ]; then
  s3="$(seau3 "$ROOT/.github/workflows/ci.yml" "$TMP/o10")"
  if [ "$s3" = "$SEAU3_FERME" ]; then
    ok "cas 10 : seau 3 du ci.yml réel == liste fermée «$SEAU3_FERME »"
  else
    ko "cas 10 : seau 3 du ci.yml réel « $s3 » ≠ liste fermée «$SEAU3_FERME » — inventorie le paquet, ou mets la liste à jour avec sa raison"
    montre "$TMP/o10"
  fi
  sed 's/^\([[:space:]]*sudo apt-get install -y .*\)$/\1 paquet-hors-inventaire-t1001/' "$ROOT/.github/workflows/ci.yml" > "$TMP/ci10.yml"
  s3m="$(seau3 "$TMP/ci10.yml" "$TMP/o10m")"
  if [ "$s3m" = "$SEAU3_FERME paquet-hors-inventaire-t1001" ]; then
    ok "cas 10 : témoin — un paquet ajouté à la ligne apt sort le seau 3 de la liste fermée"
  else
    ko "cas 10 : témoin — seau 3 « $s3m » après ajout d'un paquet (attendu «$SEAU3_FERME paquet-hors-inventaire-t1001 »)"
    montre "$TMP/o10m"
  fi
else
  echo "  info : cas 10 non asserté — arbre adoptant, son ci.yml n'est pas celui du kit"
fi

echo
echo "doctor-parity.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
