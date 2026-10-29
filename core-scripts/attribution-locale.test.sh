#!/usr/bin/env bash
# core-scripts/attribution-locale.test.sh — T-01M4TRY5VZF9FGXRD3PH9AVNGE
#
# Prouve que core-scripts/attribution-locale.ps1 pose l'identité du projet dans
# .claude/settings.local.json SANS jq, sans rien perdre ni rien corrompre.
# Auto-découvert par core-scripts/run-bash-tests.sh (find *.test.sh).
#
# Directives lues par core-scripts/run-bash-tests.sh :
# optional: pwsh git
#
# `pwsh` est OPTIONNEL : sans lui, seul le cas (0), une LECTURE statique, est
# joué, et le banc l'ANNONCE par une ligne `SKIP:` que le lanceur relève et
# compte. Un vert sans pwsh n'est jamais une couverture. `git` est OPTIONNEL
# aussi : sans lui, (n1) et (n2) seuls sont annoncés SKIP. Python 3 est REQUIS par le script
# lui-même (classe B de l'inventaire) : son absence rougit, elle ne saute pas.
#
# Chaque cas tourne dans un dépôt JETABLE (mktemp -d) : un faux
# `.agents/bin/project_init.py` qui imprime SEPT clés d'env et vérifie ses
# arguments et son répertoire courant, ou le VRAI (cas h et n, le paquet
# `cadre` copié depuis `.agents/vendor/cadre` ou `src/cadre`, selon vendor_paths). Le vrai `.claude/settings.local.json` du dépôt n'est jamais touché :
# chaque appel passe `-Root <jetable>`, sauf (i), qui exécute une COPIE du
# script posée sous `<jetable>/core-scripts/`. Chaque appel est lancé
# `env -u CLAUDECODE` : le script refuse de tourner sous un agent (cas m), et
# ce banc tourne souvent sous Claude Code.
#
# Cas, dont les NOMS portent leur borne :
#   (0) statique 5.1 : lignes de code en ASCII, ni `??`, ni `?.`, ni `&&`, ni
#       `||`, ni `-AsHashtable`, ni `$IsWindows` — une LECTURE, pas une
#       exécution sous 5.1 ; le ternaire n'est pas détectable ainsi (borne) ;
#   (a) fichier absent : créé, octets EXACTS, une seule clé d'env sur sept ;
#       `.claude/` absent : créé aussi ;
#   (b) fichier vide (0 octet) et blancs seuls : traités comme `{}` ;
#   (c) permissions et autres env (http_proxy ET HTTP_PROXY, une date +02:00,
#       des accents) : TOUT gardé, ordre compris, ancienne valeur remplacée —
#       octets exacts ; et l'INODE change : écriture par remplacement, jamais
#       sur place. Un ConvertFrom-Json, lui, REFUSE ce JSON (deux clés égales
#       à la casse près : erreur mesurée sous pwsh 7.6.6 par ce banc, (h2)
#       sous la mutation qui le réintroduit ; la bannière relève la version) ;
#   (d) JSON invalide, à commentaires, `env` non objet, racine tableau, clé en
#       double, nombre hors double (`1e400`, qui ressortirait `Infinity`) :
#       refus code 4, octets INCHANGÉS, aucun temporaire laissé ;
#   (e) second passage : octets identiques, témoin identique, « inchange »,
#       inode inchangé (aucune réécriture) ;
#   (f) pas de BOM : premiers octets ≠ EF BB BF ; un BOM hérité (PS 5.1) est ôté,
#       même quand la valeur était déjà posée ;
#   (g) project.json absent : refus code 3, rien créé (ni settings, ni identité) ;
#   (h) le VRAI project_init.py : la valeur vient de l'identité fixture ; et
#       (h2) avec http_proxy ET HTTP_PROXY dans `.claude/settings.json`, que
#       project_init recopie dans sa sortie : rc 0, la seule valeur extraite ;
#   (i) racine par défaut : le parent du dossier du script ;
#   (j) project_init.py qui échoue : code 5, son message relayé, rien créé ;
#   (k) Python introuvable (PATH vidé) : code 127 ;
#   (l) Python sous un chemin ACCENTUÉ (venv sous `Zoé-Noël/`) avec
#       PYTHONIOENCODING=cp1252, l'encodage de pipe de Windows : trouvé, rc 0 ;
#   (m) CLAUDECODE posé : refus code 7, rien créé ;
#   (n) dépôt git IMBRIQUÉ, SANS GIT_CEILING_DIRECTORIES : `-Root <git>/sub`
#       écrit sous la racine GIT, avec l'identité de la racine git — celle que
#       project_init.py lit —, que sub ne porte pas (n2) ou porte (n1) sa
#       propre identité ;
#   (o) project_init qui sort `agentkit.project_id=…\n` (saut de ligne
#       échappé) : refus code 5, rien créé ;
#   (p) monodépôt, kit sous `<git>/kit` : refus code 2, aucun settings.local.json
#       écrit, le message nomme la racine git ET le kit qui est dessous ;
#   (q) CLAUDECODE vide, puis fait de blancs : vaut ABSENT, rc 0 (doctrine de
#       `.agents/bin/skills_github_fallback.py`, marqueur compté après strip) ;
#   (s) settings.local.json lien symbolique : refus code 4, lien et cible
#       intacts ; SKIP annoncé là où `ln -s` copie (Git Bash sans winsymlinks) ;
#   (t) remplacement REFUSÉ par le système (macOS : drapeau `uchg` ; Git Bash :
#       `chmod 444`, l'attribut lecture seule) : code 6, octets intacts, AUCUN
#       `.tmp` laissé. Le `chmod 0o600` du temporaire avant son effacement n'est
#       observable que sous Windows, où un fichier en lecture seule ne s'efface
#       pas ; ailleurs le témoin tient le nettoyage, pas le chmod. Linux : aucun
#       moyen sans root de faire échouer le remplacement, SKIP annoncé ;
#   (u) voie 5.1 FORCÉE (ATTRIBUTION_LOCALE_FORCE_ARGUMENTS : la ligne de
#       commande citée de Join-NativeArguments, pas ArgumentList) : (c) rejoué
#       sur une racine « avec espace/l'apostrophe », octets exacts.
#
# PREUVE DE MUTATION : ATTRIBUTION_LOCALE_PS1=<copie mutée> rejoue le banc sur
# une copie du script ; le fichier suivi n'est jamais modifié pour la prouver.
#
# NON MESURÉ ICI : Windows PowerShell 5.1 (jamais exécuté, (0) le borne par
# lecture) et la jambe Windows de ce banc tant que la CI ne l'a pas jouée.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DEFAUT_PS1="$HERE/attribution-locale.ps1"
SCRIPT="${ATTRIBUTION_LOCALE_PS1:-$DEFAUT_PS1}"
[ -f "$SCRIPT" ] || { echo "FAIL: $SCRIPT introuvable"; exit 1; }

pass=0; fail=0
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
ko() { echo "FAIL: $1"; fail=$((fail + 1)); }
bilan() {
  echo "TOTAL: $((pass + fail)) témoins — $pass PASS, $fail FAIL"
  [ "$fail" -eq 0 ]
}

echo "== attribution-locale.test.sh ($SCRIPT) =="

# --- (0) statique : ce que Windows PowerShell 5.1 lirait --------------------
# Les `\r` ôtés d'abord : .gitattributes pose `*.ps1 eol=crlf`.
LIGNES_CODE="$(tr -d '\r' < "$SCRIPT" | grep -v '^[[:space:]]*#')"
MOTIF_PS7='\?\?|\?\.|&&|\|\||-AsHashtable|[$]Is(Windows|Linux|MacOS)'
n_nonascii="$(printf '%s\n' "$LIGNES_CODE" | LC_ALL=C grep -c '[^[:print:][:space:]]')"
n_ps7="$(printf '%s\n' "$LIGNES_CODE" | grep -cE "$MOTIF_PS7")"
if [ "$n_nonascii" -eq 0 ] && [ "$n_ps7" -eq 0 ]; then
  ok "(0) statique 5.1 : lignes de code ASCII, aucune forme 7-only (lecture, pas une exécution 5.1)"
else
  ko "(0) statique 5.1 : $n_nonascii ligne(s) de code non ASCII, $n_ps7 forme(s) 7-only"
  printf '%s\n' "$LIGNES_CODE" | LC_ALL=C grep -n -m3 '[^[:print:][:space:]]'
  printf '%s\n' "$LIGNES_CODE" | grep -nE -m3 "$MOTIF_PS7"
fi

PWSH="$(command -v pwsh 2>/dev/null || true)"
if [ -z "$PWSH" ]; then
  echo "SKIP: pwsh absent — cas (a) à (s) NON joués, seul (0), une lecture statique, l'a été"
  bilan
  exit $?
fi

# La version jouée, RELEVÉE à chaque passage plutôt que supposée.
echo "pwsh : $("$PWSH" -NoProfile -NonInteractive -Command "\$PSVersionTable.PSVersion.ToString()" 2>/dev/null | tr -d '\r')"

TMPROOT="$(mktemp -d)" || { echo "FAIL: mktemp"; exit 1; }
trap 'rm -rf "$TMPROOT"' EXIT
# Le vrai project_init.py résout sa racine par `git rev-parse` depuis le
# répertoire courant : le plafond l'empêche de remonter hors du dépôt jetable.
# Le cas (n) le retire, parce que c'est cette remontée qu'il mesure.
GIT_CEILING_DIRECTORIES="$TMPROOT"
export GIT_CEILING_DIRECTORIES
OUT="$TMPROOT/stdout"
ERR="$TMPROOT/stderr"
RC=0
ID_FAUX='faux-0123'
TEMOIN_FAUX="attribution-locale: OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=$ID_FAUX"

# Faux project_init.py : sept clés d'env, comme le vrai sur ce dépôt. Il REFUSE
# (codes 8 et 9) d'autres arguments ou un autre répertoire courant que la racine.
# Mode `nl` : la valeur porte un saut de ligne final (échappé `\n` en JSON).
faux_project_init() {  # $1 = racine ; $2 = ok | echec | nl
  local valeur='agentkit.project_id=faux-0123'
  mkdir -p "$1/.agents/bin"
  if [ "$2" = "echec" ]; then
    printf '%s\n' 'import sys' \
      'sys.stderr.write("faux project_init : identite corrompue\n")' \
      'sys.exit(2)' > "$1/.agents/bin/project_init.py"
    return 0
  fi
  if [ "$2" = "nl" ]; then
    valeur='agentkit.project_id=faux-0123\n'
  fi
  {
    printf '%s\n' 'import json, os, sys' \
      'racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))' \
      'if sys.argv[1:] != ["--print-otel-env", "--format", "json"]:' \
      '    sys.exit(9)' \
      'if os.path.realpath(os.getcwd()) != os.path.realpath(racine):' \
      '    sys.exit(8)' \
      'env = {' \
      '    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",' \
      '    "OTEL_METRICS_EXPORTER": "otlp",' \
      '    "OTEL_LOGS_EXPORTER": "otlp",' \
      '    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",' \
      '    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",' \
      '    "OTEL_METRIC_EXPORT_INTERVAL": "10000",'
    printf '    "OTEL_RESOURCE_ATTRIBUTES": "%s",\n' "$valeur"
    printf '%s\n' '}' \
      'sys.stdout.write(json.dumps({"env": env}, indent=2) + "\n")'
  } > "$1/.agents/bin/project_init.py"
}

identite() {  # $1 = racine ; $2 = project_id
  mkdir -p "$1/.agents/state"
  printf '{"project_id": "%s", "slug": "banc", "name": "banc"}\n' "$2" \
    > "$1/.agents/state/project.json"
}

# T-01M5BXTPQE3JZV3KZA6WD9P5XC (S-01M5BXT85VP4JBBMXVXR9STP5F) : le paquet `cadre` copié
# est celui que `vendor_paths.exiger` désigne sous ROOT (neuf `.agents/vendor/cadre`
# d'abord, ancien `src/cadre` ensuite), vendor_paths chargé PAR CHEMIN ; vide si
# Python ou le paquet manquent (copie_kit échoue alors, (h) le dit).
CADRE_REL="$(for c in python3 python py; do
  "$c" -I -B -c 'import importlib.util as u, sys
from pathlib import Path
s = u.spec_from_file_location("vendor_paths", sys.argv[1])
m = sys.modules[s.name] = u.module_from_spec(s); s.loader.exec_module(m)
sys.stdout.write(m.exiger(sys.argv[2], "cadre").relative_to(Path(sys.argv[2]).resolve()).as_posix())' \
    "$ROOT/.agents/bin/vendor_paths.py" "$ROOT" 2>/dev/null && break
done)"

copie_kit() {  # $1 = racine : le VRAI project_init.py, son résolveur vendor_paths.py et son paquet cadre, au MÊME emplacement relatif que sous ROOT
  [ -n "$CADRE_REL" ] || return 1
  mkdir -p "$1/.agents/bin" "$1/$(dirname "$CADRE_REL")"
  cp -R "$ROOT/$CADRE_REL" "$1/$CADRE_REL"
  cp "$ROOT/.agents/bin/project_init.py" "$1/.agents/bin/project_init.py"
  cp "$ROOT/.agents/bin/vendor_paths.py" "$1/.agents/bin/vendor_paths.py"
}

depot() {  # $1 = nom ; $2 = avec-identite | sans-identite ; imprime le chemin
  local d="$TMPROOT/$1"
  mkdir -p "$d/.agents/state"
  faux_project_init "$d" ok
  if [ "$2" = "avec-identite" ]; then
    identite "$d" "$ID_FAUX"
  fi
  printf '%s' "$d"
}

lance() {  # $1 = racine passée en -Root ; code dans RC
  env -u CLAUDECODE "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$1" > "$OUT" 2> "$ERR"
  RC=$?
}

ligne() {  # $1 = numéro de ligne de la sortie standard, sans `\r`
  tr -d '\r' < "$OUT" | sed -n "$1p"
}

diag() {
  tr -d '\r' < "$ERR"
}

inode() {  # GNU stat d'abord (Linux, Git Bash), BSD stat ensuite (macOS)
  stat -c %i "$1" 2>/dev/null || stat -f %i "$1"
}

attendu_seul() {  # $1 = project_id ; le fichier attendu quand rien n'existait
  printf '{\n  "env": {\n    "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=%s"\n  }\n}\n' "$1"
}

# --- (a) fichier absent -------------------------------------------------------
cas_a() {
  local d f
  d="$(depot a avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  attendu_seul "$ID_FAUX" > "$TMPROOT/a.attendu"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(a) absent : code $RC ≠ 0 — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(a) absent : octets inattendus — $(cat "$f")"; return; }
  [ "$(ligne 1)" = "$TEMOIN_FAUX" ] || { ko "(a) absent : témoin « $(ligne 1) »"; return; }
  ok "(a) fichier absent : créé, une seule clé d'env sur sept, octets exacts, témoin affiché"

  d="$(depot a2 avec-identite)"; f="$d/.claude/settings.local.json"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(a) .claude/ absent : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(a) .claude/ absent : octets inattendus"; return; }
  ok "(a) .claude/ absent : dossier et fichier créés, octets exacts"
}

# --- (b) fichier vide et blancs seuls -----------------------------------------
cas_b() {
  local d f
  d="$(depot b1 avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  : > "$f"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(b) vide (0 octet) : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(b) vide (0 octet) : octets inattendus"; return; }
  ok "(b) fichier de 0 octet : traité comme {}, octets exacts"

  d="$(depot b2 avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '  \n\t\n' > "$f"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(b) blancs seuls : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(b) blancs seuls : octets inattendus"; return; }
  ok "(b) fichier de blancs seuls : traité comme {}, octets exacts"
}

# --- (c) permissions et autres env gardés --------------------------------------
ENTREE_C='{"permissions":{"allow":["Bash(npm test)","Read(./src/**)"],"deny":[]},"env":{"http_proxy":"http://p:1","HTTP_PROXY":"http://P:2","STAMP":"2026-10-13T10:00:00+02:00","OTEL_RESOURCE_ATTRIBUTES":"agentkit.project_id=ancien"},"model":"opus","note":"écrit à la main"}'
attendu_c() {
  printf '%s\n' '{' \
    '  "permissions": {' \
    '    "allow": [' \
    '      "Bash(npm test)",' \
    '      "Read(./src/**)"' \
    '    ],' \
    '    "deny": []' \
    '  },' \
    '  "env": {' \
    '    "http_proxy": "http://p:1",' \
    '    "HTTP_PROXY": "http://P:2",' \
    '    "STAMP": "2026-10-13T10:00:00+02:00",' \
    '    "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=faux-0123"' \
    '  },' \
    '  "model": "opus",' \
    '  "note": "écrit à la main"' \
    '}'
}
cas_c() {
  local d f i_avant i_apres
  d="$(depot c avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '%s' "$ENTREE_C" > "$f"
  attendu_c > "$TMPROOT/c.attendu"
  i_avant="$(inode "$f")"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(c) clés gardées : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/c.attendu" || { ko "(c) clés gardées : octets inattendus — $(cat "$f")"; return; }
  ok "(c) permissions, http_proxy ET HTTP_PROXY, date +02:00, accents : tout gardé dans l'ordre, ancienne valeur remplacée"
  i_apres="$(inode "$f")"
  if [ -z "$i_avant" ] || [ "$i_avant" = "$i_apres" ]; then
    ko "(c) écriture SUR PLACE : inode « $i_avant » avant, « $i_apres » après"
    return
  fi
  ok "(c) écriture par remplacement : inode $i_avant → $i_apres"
}

# --- (d) contenus refusés : code 4, octets inchangés ------------------------------
refus_attendu() {  # $1 = nom du dépôt ; $2 = libellé ; le fichier est déjà écrit
  local d="$TMPROOT/$1" f n_entrees
  f="$d/.claude/settings.local.json"
  cp "$f" "$TMPROOT/$1.avant"
  lance "$d"
  [ "$RC" -eq 4 ] || { ko "(d) $2 : code $RC ≠ 4 — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/$1.avant" || { ko "(d) $2 : fichier MODIFIÉ malgré le refus"; return; }
  # `ls -A` et non `find` : un banc qui parcourt l'arbre doit être recensé
  # (test_repo_walk_census) ; ici on ne lit qu'UN dossier, à plat.
  n_entrees="$(ls -A "$d/.claude" | wc -l | tr -d ' ')"
  [ "$n_entrees" = "1" ] \
    || { ko "(d) $2 : résidu dans .claude/ — $(ls -A "$d/.claude" | tr '\n' ' ')"; return; }
  diag | grep -q 'refuse' || { ko "(d) $2 : message de refus absent — $(diag)"; return; }
  ok "(d) $2 : refus code 4, octets inchangés, aucun temporaire laissé"
}
cas_d() {
  local d
  d="$(depot d1 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '{"env": {"A": "1",}' > "$d/.claude/settings.local.json"
  refus_attendu d1 "JSON invalide"

  d="$(depot d2 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '{' '  // commentaire' '  "env": {}' '}' > "$d/.claude/settings.local.json"
  refus_attendu d2 "JSON à commentaires"

  d="$(depot d3 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '{"env": "pas un objet"}' > "$d/.claude/settings.local.json"
  refus_attendu d3 "env non objet"

  d="$(depot d4 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '[]' > "$d/.claude/settings.local.json"
  refus_attendu d4 "racine tableau"

  d="$(depot d5 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '{"env": {"A": "1", "A": "2"}}' > "$d/.claude/settings.local.json"
  refus_attendu d5 "clé en double"

  d="$(depot d6 avec-identite)"; mkdir -p "$d/.claude"
  printf '%s\n' '{"seuil": 1e400}' > "$d/.claude/settings.local.json"
  refus_attendu d6 "nombre hors double (1e400)"
}

# --- (e) second passage ---------------------------------------------------------
cas_e() {
  local d f t1 i1
  d="$(depot e avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '%s' "$ENTREE_C" > "$f"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(e) premier passage : code $RC — $(diag)"; return; }
  cp "$f" "$TMPROOT/e.passage1"
  t1="$(ligne 1)"
  i1="$(inode "$f")"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(e) second passage : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/e.passage1" || { ko "(e) second passage : octets DIFFÉRENTS"; return; }
  [ "$(ligne 1)" = "$t1" ] || { ko "(e) second passage : témoin « $(ligne 1) » ≠ « $t1 »"; return; }
  ligne 2 | grep -q 'inchange' || { ko "(e) second passage : réécrit au lieu d'inchangé — $(ligne 2)"; return; }
  [ "$(inode "$f")" = "$i1" ] || { ko "(e) second passage : inode changé, fichier réécrit"; return; }
  ok "(e) second passage : octets identiques, témoin identique, fichier non réécrit (inode inchangé)"
}

# --- (f) pas de BOM ---------------------------------------------------------------
tete() {  # les trois premiers octets, en hexadécimal
  od -An -tx1 -N3 "$1" | tr -d ' \n'
}
cas_f() {
  local d f
  f="$TMPROOT/a/.claude/settings.local.json"
  [ -f "$f" ] || { ko "(f) sans BOM : la sortie de (a) manque"; return; }
  [ "$(tete "$f")" != "efbbbf" ] || { ko "(f) sans BOM : le fichier écrit commence par EF BB BF"; return; }
  ok "(f) fichier écrit sans BOM : premiers octets $(tete "$f")"

  d="$(depot f avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '\357\273\277%s\n' '{"env": {"OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=faux-0123"}}' > "$f"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(f) BOM hérité : code $RC — $(diag)"; return; }
  [ "$(tete "$f")" != "efbbbf" ] || { ko "(f) BOM hérité : toujours là après passage"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(f) BOM hérité : octets inattendus — $(cat "$f")"; return; }
  ok "(f) BOM hérité (PS 5.1) : ôté, même valeur déjà posée, octets exacts"
}

# --- (g) project.json absent ------------------------------------------------------
cas_g() {
  local d
  d="$(depot g sans-identite)"
  lance "$d"
  [ "$RC" -eq 3 ] || { ko "(g) identité absente : code $RC ≠ 3 — $(diag)"; return; }
  [ ! -e "$d/.claude/settings.local.json" ] || { ko "(g) identité absente : settings.local.json créé"; return; }
  [ ! -e "$d/.agents/state/project.json" ] || { ko "(g) identité absente : project.json CRÉÉ par le script"; return; }
  diag | grep -q 'project_init.py' || { ko "(g) identité absente : l'init n'est pas nommée — $(diag)"; return; }
  ok "(g) project.json absent : refus code 3, renvoi à l'init, rien créé"
}

# --- (h) le vrai project_init.py ----------------------------------------------------
ID_REEL='01JBANCREEL000000000000000'
cas_h() {
  local d="$TMPROOT/h" f
  f="$d/.claude/settings.local.json"
  [ -n "$CADRE_REL" ] && [ -d "$ROOT/$CADRE_REL" ] \
    || { ko "(h) vrai project_init : paquet cadre introuvable sous $ROOT (ni .agents/vendor/cadre ni src/cadre, ou Python absent)"; return; }
  copie_kit "$d"; identite "$d" "$ID_REEL"; mkdir -p "$d/.claude"
  attendu_seul "$ID_REEL" > "$TMPROOT/h.attendu"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(h) vrai project_init : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/h.attendu" || { ko "(h) vrai project_init : octets inattendus — $(cat "$f")"; return; }
  [ "$(ligne 1)" = "attribution-locale: OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=$ID_REEL" ] \
    || { ko "(h) vrai project_init : témoin « $(ligne 1) »"; return; }
  ok "(h) vrai project_init.py : valeur tirée de l'identité, seule clé posée"

  # (h2) les deux proxies dans settings.json : project_init les recopie dans
  # sa sortie, que le script doit lire sans ConvertFrom-Json.
  d="$TMPROOT/h2"; f="$d/.claude/settings.local.json"
  copie_kit "$d"; identite "$d" "$ID_REEL"; mkdir -p "$d/.claude"
  printf '%s\n' '{"env": {"http_proxy": "http://p:1", "HTTP_PROXY": "http://P:2"}}' \
    > "$d/.claude/settings.json"
  lance "$d"
  [ "$RC" -eq 0 ] || { ko "(h2) http_proxy ET HTTP_PROXY dans settings.json : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/h.attendu" || { ko "(h2) octets inattendus — $(cat "$f")"; return; }
  ok "(h2) http_proxy ET HTTP_PROXY dans settings.json : rc 0, la seule valeur extraite"
}

# --- (i) racine par défaut ------------------------------------------------------------
cas_i() {
  local d f
  d="$(depot i avec-identite)"; mkdir -p "$d/.claude" "$d/core-scripts"; f="$d/.claude/settings.local.json"
  cp "$SCRIPT" "$d/core-scripts/attribution-locale.ps1"
  env -u CLAUDECODE "$PWSH" -NoProfile -NonInteractive -File "$d/core-scripts/attribution-locale.ps1" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(i) racine par défaut : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(i) racine par défaut : octets inattendus"; return; }
  ok "(i) sans -Root : racine = parent du dossier du script"
}

# --- (j) project_init.py qui échoue -------------------------------------------------
cas_j() {
  local d
  d="$(depot j avec-identite)"
  faux_project_init "$d" echec
  lance "$d"
  [ "$RC" -eq 5 ] || { ko "(j) project_init en échec : code $RC ≠ 5 — $(diag)"; return; }
  diag | grep -q 'faux project_init : identite corrompue' \
    || { ko "(j) project_init en échec : message non relayé — $(diag)"; return; }
  [ ! -e "$d/.claude/settings.local.json" ] || { ko "(j) project_init en échec : fichier créé"; return; }
  ok "(j) project_init.py en échec : code 5, son message relayé, rien créé"
}

# --- (k) Python introuvable -----------------------------------------------------------
cas_k() {
  local d
  d="$(depot k avec-identite)"
  env -u CLAUDECODE PATH="$TMPROOT/vide" "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 127 ] || { ko "(k) Python introuvable : code $RC ≠ 127 — $(diag)"; return; }
  ok "(k) Python introuvable (PATH vidé) : code 127"
}

# --- (l) Python sous un chemin accentué, pipe en cp1252 -------------------------------
cas_l() {
  local py venv bin d f
  py="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
  [ -n "$py" ] || { ko "(l) chemin accentué : ni python3 ni python pour créer le venv (Python est REQUIS)"; return; }
  venv="$TMPROOT/Zoé-Noël/venv"
  "$py" -m venv --without-pip "$venv" > "$TMPROOT/l.venv" 2>&1 \
    || { ko "(l) chemin accentué : venv non créé — $(cat "$TMPROOT/l.venv")"; return; }
  bin="$venv/bin"
  if [ -d "$venv/Scripts" ]; then
    bin="$venv/Scripts"
  fi
  d="$(depot Zoé-Noël/l avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  env -u CLAUDECODE PATH="$bin" PYTHONIOENCODING=cp1252 \
    "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(l) Python sous Zoé-Noël/, PYTHONIOENCODING=cp1252 : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/a.attendu" || { ko "(l) chemin accentué : octets inattendus — $(cat "$f")"; return; }
  ok "(l) Python sous un chemin accentué, PYTHONIOENCODING=cp1252 : trouvé, rc 0, octets exacts"
}

# --- (m) lancé sous un agent ----------------------------------------------------------
cas_m() {
  local d
  d="$(depot m avec-identite)"
  env CLAUDECODE=1 "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 7 ] || { ko "(m) CLAUDECODE posé : code $RC ≠ 7 — $(diag)"; return; }
  diag | grep -q 'pas par un agent' || { ko "(m) CLAUDECODE posé : message absent — $(diag)"; return; }
  [ ! -e "$d/.claude/settings.local.json" ] || { ko "(m) CLAUDECODE posé : fichier créé"; return; }
  ok "(m) CLAUDECODE posé : refus code 7, « pas par un agent », rien créé"
}

# --- (n) dépôt git imbriqué, sans plafond ----------------------------------------------
imbrique() {  # $1 = nom ; $2 = id de la racine git ; $3 = id de sub, ou vide
  local o="$TMPROOT/$1" s="$TMPROOT/$1/sub"
  git init -q "$o" || return 1
  copie_kit "$o"; identite "$o" "$2"
  copie_kit "$s"
  if [ -n "$3" ]; then
    identite "$s" "$3"
  fi
  env -u CLAUDECODE -u GIT_CEILING_DIRECTORIES \
    "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$s" > "$OUT" 2> "$ERR"
  RC=$?
  attendu_seul "$2" > "$TMPROOT/$1.attendu"
  return 0
}
GIT_PRESENT=1
if ! command -v git >/dev/null 2>&1; then
  GIT_PRESENT=0
fi
cas_n2() {
  local o="$TMPROOT/n2"
  if [ "$GIT_PRESENT" -eq 0 ]; then
    echo "SKIP: (n2) git absent — dépôt imbriqué NON joué"
    return
  fi
  imbrique n2 '01JRACINEGIT2000000000000' '' || { ko "(n2) git init a échoué"; return; }
  [ "$RC" -eq 0 ] || { ko "(n2) identité à la seule racine git : code $RC — $(diag)"; return; }
  cmp -s "$o/.claude/settings.local.json" "$TMPROOT/n2.attendu" \
    || { ko "(n2) identité à la seule racine git : fichier de la racine git absent ou inattendu"; return; }
  [ ! -e "$o/sub/.claude/settings.local.json" ] || { ko "(n2) écrit sous sub au lieu de la racine git"; return; }
  ok "(n2) -Root <git>/sub sans identité propre : rc 0, écrit sous la racine git avec SON identité"
}
cas_n1() {
  local o="$TMPROOT/n1"
  if [ "$GIT_PRESENT" -eq 0 ]; then
    echo "SKIP: (n1) git absent — dépôt imbriqué NON joué"
    return
  fi
  imbrique n1 '01JRACINEGIT1000000000000' '01JSOUSDOSSIER00000000000' || { ko "(n1) git init a échoué"; return; }
  [ "$RC" -eq 0 ] || { ko "(n1) sub avec sa propre identité : code $RC — $(diag)"; return; }
  [ ! -e "$o/sub/.claude/settings.local.json" ] \
    || { ko "(n1) écrit sous sub — $(cat "$o/sub/.claude/settings.local.json")"; return; }
  cmp -s "$o/.claude/settings.local.json" "$TMPROOT/n1.attendu" \
    || { ko "(n1) la racine git n'a pas reçu SON identité"; return; }
  ok "(n1) -Root <git>/sub avec sa propre identité : rien sous sub, la racine git reçoit l'identité que project_init lit"
}

# --- (o) valeur suivie d'un saut de ligne ----------------------------------------------
cas_o() {
  local d
  d="$(depot o avec-identite)"
  faux_project_init "$d" nl
  lance "$d"
  [ "$RC" -eq 5 ] || { ko "(o) valeur suivie de \\n : code $RC ≠ 5 — $(diag) — $(cat "$d/.claude/settings.local.json" 2>/dev/null)"; return; }
  [ ! -e "$d/.claude/settings.local.json" ] || { ko "(o) valeur suivie de \\n : fichier créé"; return; }
  ok "(o) valeur suivie d'un saut de ligne échappé : refus code 5, rien créé"
}

# --- (s) settings.local.json lien symbolique ---------------------------------------------
cas_s() {
  local d f cible
  d="$(depot s avec-identite)"; mkdir -p "$d/.claude"
  f="$d/.claude/settings.local.json"; cible="$d/cible.json"
  printf '%s\n' '{"env": {}}' > "$cible"
  cp "$cible" "$TMPROOT/s.avant"
  ln -s "$cible" "$f" 2>/dev/null
  if [ ! -L "$f" ]; then
    echo "SKIP: (s) ln -s ne crée pas de lien ici (Git Bash sans winsymlinks) — lien symbolique NON joué"
    return
  fi
  lance "$d"
  [ "$RC" -eq 4 ] || { ko "(s) lien symbolique : code $RC ≠ 4 — $(diag)"; return; }
  [ -L "$f" ] || { ko "(s) lien symbolique : remplacé par un fichier ordinaire"; return; }
  cmp -s "$cible" "$TMPROOT/s.avant" || { ko "(s) lien symbolique : cible modifiée"; return; }
  diag | grep -q 'lien symbolique' || { ko "(s) lien symbolique : message absent — $(diag)"; return; }
  diag | grep -q 'cible.json' || { ko "(s) lien symbolique : la cible n'est pas nommée — $(diag)"; return; }
  ok "(s) settings.local.json lien symbolique : refus code 4, lien et cible intacts, cible nommée"
}

# --- (p) monodépôt : le kit n'est pas à la racine git -------------------------------------
cas_p() {
  local g="$TMPROOT/p" k="$TMPROOT/p/kit" n_ecrits
  if [ "$GIT_PRESENT" -eq 0 ]; then
    echo "SKIP: (p) git absent — monodépôt NON joué"
    return
  fi
  git init -q "$g" || { ko "(p) git init a échoué"; return; }
  copie_kit "$k"; identite "$k" "$ID_REEL"
  lance "$k"
  [ "$RC" -eq 2 ] || { ko "(p) monodépôt : code $RC ≠ 2 — $(diag)"; return; }
  # Les deux seuls endroits où le script peut écrire : la racine git et le kit.
  n_ecrits=0
  for cible in "$g/.claude/settings.local.json" "$k/.claude/settings.local.json"; do
    [ -e "$cible" ] && n_ecrits=$((n_ecrits + 1))
  done
  [ "$n_ecrits" = "0" ] || { ko "(p) monodépôt : $n_ecrits settings.local.json écrit(s)"; return; }
  diag | grep -q 'racine git' || { ko "(p) monodépôt : la racine git n'est pas nommée — $(diag)"; return; }
  diag | grep -qF "le kit est sous $k" || { ko "(p) monodépôt : le kit sous la racine git n'est pas nommé — $(diag)"; return; }
  if diag | grep -q 'pas un depot du kit'; then
    ko "(p) monodépôt : ancien message « pas un depot du kit »"
    return
  fi
  ok "(p) monodépôt (kit sous <git>/kit) : refus code 2, rien écrit, racine git et kit nommés"
}

# --- (q) CLAUDECODE vide ou fait de blancs : vaut absent -----------------------------------
cas_q() {
  local d
  d="$(depot q1 avec-identite)"
  env CLAUDECODE= "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(q) CLAUDECODE vide : code $RC ≠ 0 — $(diag)"; return; }
  cmp -s "$d/.claude/settings.local.json" "$TMPROOT/a.attendu" || { ko "(q) CLAUDECODE vide : octets inattendus"; return; }
  d="$(depot q2 avec-identite)"
  env CLAUDECODE='   ' "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(q) CLAUDECODE fait de blancs : code $RC ≠ 0 — $(diag)"; return; }
  cmp -s "$d/.claude/settings.local.json" "$TMPROOT/a.attendu" || { ko "(q) CLAUDECODE blancs : octets inattendus"; return; }
  ok "(q) CLAUDECODE vide, puis fait de blancs : vaut absent, rc 0, octets exacts"
}

# --- (t) remplacement refusé par le système : aucun temporaire laissé -----------------------
cas_t() {
  local d f n_tmp verrou
  d="$(depot t avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '%s' "$ENTREE_C" > "$f"
  cp "$f" "$TMPROOT/t.avant"
  verrou=''
  case "$(uname -s)" in
    Darwin) chflags uchg "$f" && verrou='uchg' ;;
    MINGW*|MSYS*|CYGWIN*) chmod 444 "$f" && verrou='lecture-seule' ;;
    *) verrou='' ;;
  esac
  if [ -z "$verrou" ]; then
    echo "SKIP: (t) aucun moyen sans root de faire échouer le remplacement ici ($(uname -s)) — NON joué"
    return
  fi
  lance "$d"
  if [ "$verrou" = "uchg" ]; then
    chflags nouchg "$f"
  else
    chmod 644 "$f"
  fi
  [ "$RC" -eq 6 ] || { ko "(t) remplacement refusé ($verrou) : code $RC ≠ 6 — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/t.avant" || { ko "(t) remplacement refusé : fichier MODIFIÉ"; return; }
  n_tmp=0
  for cible in "$d/.claude"/*.tmp "$d/.claude"/.*.tmp; do
    [ -e "$cible" ] && n_tmp=$((n_tmp + 1))
  done
  [ "$n_tmp" = "0" ] || { ko "(t) remplacement refusé : $n_tmp temporaire(s) laissé(s) dans .claude/"; return; }
  ok "(t) remplacement refusé par le système ($verrou) : code 6, octets intacts, aucun .tmp laissé"
}

# --- (u) voie 5.1 forcée : ligne de commande citée, racine à espace et apostrophe -----------
cas_u() {
  local d f
  d="$(depot "avec espace/l'apostrophe" avec-identite)"; mkdir -p "$d/.claude"; f="$d/.claude/settings.local.json"
  printf '%s' "$ENTREE_C" > "$f"
  env -u CLAUDECODE ATTRIBUTION_LOCALE_FORCE_ARGUMENTS=1 \
    "$PWSH" -NoProfile -NonInteractive -File "$SCRIPT" -Root "$d" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(u) voie 5.1 forcée : code $RC — $(diag)"; return; }
  cmp -s "$f" "$TMPROOT/c.attendu" || { ko "(u) voie 5.1 forcée : octets inattendus — $(cat "$f")"; return; }
  ok "(u) voie 5.1 forcée (Join-NativeArguments) sur « avec espace/l'apostrophe » : (c) rejoué, octets exacts"
}

cas_a
cas_b
cas_c
cas_d
cas_e
cas_f
cas_g
cas_h
cas_i
cas_j
cas_k
cas_l
cas_m
cas_n2
cas_n1
cas_o
cas_p
cas_q
cas_s
cas_t
cas_u

bilan
