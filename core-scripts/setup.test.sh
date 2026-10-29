#!/usr/bin/env bash
# core-scripts/setup.test.sh — T-01M4WHQQHHGFS6NPSFQ9TSM36V
#
# Prouve core-scripts/setup.sh (macOS, Ubuntu) et core-scripts/setup.ps1
# (Windows) SANS RIEN INSTALLER : brew, apt-get, sudo et winget sont des
# BOUCHONS dans un PATH jetable (mktemp -d). Chaque bouchon journalise ses
# arguments dans un fichier et « installe » en posant un bouchon d'outil dans
# le même dossier — c'est ce que la seconde sonde du doctor voit ensuite. Le
# vrai gestionnaire de CE poste n'est jamais appelé : SETUP_PROBE_PATH (bash)
# et PATH (pwsh) ne contiennent que le dossier jetable.
# Auto-découvert par core-scripts/run-bash-tests.sh (glob *.test.sh).
#
# Directives lues par core-scripts/run-bash-tests.sh :
# optional: pwsh
#
# `pwsh` est OPTIONNEL : sans lui, seul (W0), une LECTURE statique de
# setup.ps1, est joué, et le banc l'ANNONCE par une ligne `SKIP:`. Sous Git
# Bash (MINGW*/MSYS*), les cas (W1) à (W10) sont aussi SKIP : pwsh n'y lance pas
# un bouchon `winget` sans extension.
# SETUP_TEST_ONLY=pilote rejoue le dialogue Bash ; =pilote_ps1 ajoute le
# dialogue PowerShell (sur le même dépôt jetable), sans la matrice générale ni
# son rejeu (14) sous bash 3.2 ; (W0), (W1) et (18), des lectures, restent joués.
#
# Cas bash, dont les NOMS portent leur borne :
#   (1)  tout présent : rc 0, déjà là = chaque outil B de la plateforme, le
#        gestionnaire n'est PAS appelé (journal absent) ;
#   (2)  git et pytest absents (darwin) : `brew install -- git` SEUL journalisé
#        — pytest n'a AUCUN paquet brew (la formule vit dans son virtualenv,
#        invisible de `python3 -m pytest` que la porte lance) —, installés=git,
#        manque encore=pytest avec la note pip, rc 1, aucun bouchon pytest posé ;
#   (3)  idempotence : (2) relancé sur le même PATH → journal VIDE, manque
#        encore=pytest, rc 1 ; pytest posé à la main → journal VIDE, rc 0 ;
#   (4)  --dry-run avec des absents : rc 1, « lancerait : brew install -- git »,
#        pytest « a installer vous-meme » AVEC la commande pip (la note dite
#        avant d'installer, pas seulement après),
#        journal ABSENT, aucun bouchon posé — et permis sous CLAUDECODE ; linux
#        en --dry-run : ni update ni install (journal ABSENT), « lancerait :
#        … apt-get update && … apt-get install -y -- git » ; un apt-get dont
#        `update` rend 1 : install JAMAIS lancé (`&&`), rc 1 ;
#   (5)  refus d'usage, rc 2 : SETUP_OS=freebsd ; SETUP_OS=windows (nomme
#        setup.ps1) ; argument inconnu ; --inventory sans fichier ; inventaire
#        introuvable ; inventaire illisible pour le doctor (colonne absente) ;
#   (6)  brew absent sur darwin : rc 2, nomme brew.sh, journal absent ;
#   (7)  gestionnaire en échec (brew rend 1, ne pose rien) : rc 1, manque
#        encore=…, la commande à taper est affichée ;
#   (8)  outil B sans paquet connu (inventaire fixture, jeton `frob`), git
#        absent : rc 1, « aucun paquet brew connu », frob absent de la commande,
#        git posé ;
#   (9)  chaque marqueur d'agent seul (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT,
#        AGENTS_HOOK_HOST, COPILOT_AGENT_SESSION_ID, COPILOT_CLI) à 1 sans
#        --dry-run : rc 7, journal absent, rien posé, le message nomme CE
#        marqueur ; le même en --dry-run : permis (rc 1, journal absent) ; les
#        cinq faits de blancs (espace, \t, \v, \f) : valent absents, rc 0 ;
#   (10) linux, non root : sudo ANNONCÉ avant, `sudo apt-get update` puis
#        `sudo apt-get install -y -- git` journalisés, rc 0 ; apt-get absent → 2 ;
#        sudo absent → rc 1 et la commande root affichée ;
#   (10r) linux EN ROOT, joué par un faux `id` (`-u` → 0) en tête du PATH du
#        script, sans aucun privilège réel : --dry-run dit « lancerait :
#        apt-get update && apt-get install -y -- git » sans sudo ; installé :
#        journal `update` puis `install -y -- git`, AUCUN sudo annoncé ni
#        appelé, rc 0 ; sans sudo sur le poste : rc 0 quand même ; `update` qui
#        rend 1 : install jamais lancé, rc 1 ;
#   (11) mauvaise version : un bouchon bash 3.2 entre dans le plan (brew
#        install bash) ; brew qui pose un bash 99 → installé ; brew qui ne pose
#        rien → manque encore, note « tete de PATH », rc 1 ;
#   (12) le doctor est la sonde : SETUP_DOCTOR pointé sur un faux doctor qui
#        déclare `B manquants=git` alors que git est posé → setup suit le
#        doctor et planifie git (aucune sonde propre) ;
#   (13) la ligne de résumé est UNE ligne `setup: installés=… déjà là=… manque
#        encore=… — exit N`, et N est le code rendu ;
#   (14) bash 3.2 : (1), (2), (3), (4), (19) et (22) rejoués sous /bin/bash
#        quand c'est un 3.2 (macOS) ; sinon SKIP annoncé ;
#   (15) les cinq outils B de l'inventaire RÉEL (git bash python3 pytest tee)
#        sont ceux que le script liste comme requis — lus, pas codés ;
#   (16) la TABLE sp_paquet est traversée (python3, pytest, tee n'ont pas de
#        colonne apt/brew dans l'inventaire réel) : linux, les trois absents →
#        `install -y -- python3 python3-pytest coreutils`, rc 0 ; darwin, python3,
#        pytest et tee absents → `install -- python` seul, pytest SANS paquet
#        brew (virtualenv de la formule) et tee non plus (le coreutils de
#        Homebrew pose gtee), manque encore=pytest tee, rc 1 ;
#   (17) une cellule apt/brew qui n'est pas un nom de paquet (fixture :
#        `-oDpkg::Pre-Invoke::=/tmp/evil`, puis `git pytest` avec un espace) est
#        REFUSÉE sur stderr, darwin et linux : journal ABSENT, manque encore, rc 1 ;
#        une cellule refusée qui porte un ESC (branche tiret, branche nom) est
#        citée avec `?` à sa place, aucun octet ESC en sortie ; un outil
#        (cellule `tool`) à ESC, mené par un doctor substitué, est cité avec
#        `?` dans le refus, aucun octet ESC sur stderr ;
#   (18) le pin `pytest==N` de la note macOS de setup.sh est celui de
#        .github/workflows/ci.yml (SKIP annoncé si ce fichier n'est pas là).
#
# Cas bash HORS DU KIT (T-01M5VYNMZPG8G0JZG48HV4K0PN, étape 2 ; décision pilote
# S-01M5W3ZT0G274JQM72E2TC02GF) : un arbre COPIÉ dans $TMP sans
# .agents/IS_THE_KIT — setup.sh, doctor.sh, module_discovery.py —, le VRAI
# doctor de la copie, et un interpréteur RÉEL (venv sans pip, python >= 3.11
# du poste, FAIL nommé sinon) qui sert la découverte des modules et la ligne
# python3 ; les autres outils B sont des bouchons, gitleaks et semgrep absents.
#   (19) --dry-run, darwin, sans manifeste : pytest « hors classe B ici », ni
#        requis ni « manque encore », « lancerait : brew install -- gitleaks
#        semgrep », manque encore=gitleaks semgrep, rc 1 ; avec pyproject.toml :
#        pytest requis avec la note pip, pip-audit planifié ;
#   (20) --dry-run, darwin, pyproject.toml + package.json + pom.xml + main.tf,
#        six scanners absents : UNE ligne « lancerait : brew install -- gitleaks
#        semgrep pip-audit node dependency-check trivy » (C11), la ligne du JDK
#        AVANT elle (C19), la ligne SP_SCANNERS_DARWIN unique, en colonne 0
#        (C17) ;
#   (21) installation, darwin, brew INERTE (ne pose rien) : journal « install --
#        gitleaks semgrep », la ligne de classe A de chaque scanner relue après :
#        manque encore=gitleaks semgrep, « a taper : brew install -- gitleaks »,
#        rc 1 (C18) ; brew qui pose : installés=gitleaks semgrep, rc 0 ;
#   (22) Ubuntu, pipx bouchon, python + npm + iac : --dry-run « lancerait :
#        pipx install semgrep==<version du ci_pin> » et « pipx install
#        pip-audit », npm dans la commande apt-get, « PAS épinglé par
#        empreinte » dit, ~/.local/bin et `pipx ensurepath` dits, gitleaks et
#        trivy à installer soi-même ; installation : pipx journalisé, la ligne
#        ~/.local/bin APRÈS la boucle pipx ; une cellule ci_pin `-x1@…` REFUSÉE
#        sur stderr, rien passé à pipx (C16) ;
#   (23) --dry-run, darwin, Package.swift seul : `modules : swift`, UNE ligne
#        « lancerait : brew install -- gitleaks semgrep dependency-check », le
#        JDK et la ligne NVD_API_KEY dits AVANT elle, rc 1 ;
#   (24) --dry-run, Ubuntu SANS pipx, pyproject.toml : « pipx introuvable »
#        dit, aucune commande pipx, pas de ligne ~/.local/bin, « scanners a
#        installer vous-meme : gitleaks semgrep pip-audit », rc 1.
# Mutants nommés (copie hors dépôt, SETUP_SH=…) : ajout des scanners retiré →
# (19), (20), (21) ; exclusion `hors classe B ici` retirée (pytest « déjà là »)
# → (19) ; un nom ôté de SP_SCANNERS_DARWIN → (20) ; annonce du JDK ôtée →
# (20), (23) ; relecture d'après installation qui croit le scanner posé → (21) ;
# validation de la version du ci_pin ôtée → (22) ; famille swift ôtée de
# sp_rangs, ou ligne NVD_API_KEY ôtée → (23) ; garde `-n "$PIPX_BIN"` de
# pip-audit forcée vraie, ou « pipx introuvable » ôté → (24) ; ligne
# ~/.local/bin ôtée → (22), dite sans pipx planifié → (24) ; filtre des
# caractères de contrôle ôté de sp_paquet, sur la cellule ou sur l'outil → (17).
#
# Cas PowerShell :
#   (W0) statique 5.1 : lignes de code en ASCII, ni `??`, ni `?.`, ni `&&`, ni
#        `||`, ni `-AsHashtable`, ni `$IsWindows` (lecture, pas une exécution
#        sous 5.1) ; le pin `$script:PytestPin = 'pytest==N'` est celui de
#        .github/workflows/ci.yml (SKIP annoncé si ce fichier n'est pas là) ;
#        (W1) parse : Parser::ParseFile sans erreur (pwsh) ;
#   (W2) -DryRun, git et pytest absents : rc 1, winget NON appelé, « lancerait » ;
#   (W3) winget bouchon : `install --id Git.Git …` journalisé, pip pour
#        pytest==<pin> journalisé, rc 0, installes=… ;
#   (W4) idempotence : (W3) relancé → rc 0, journal vide ;
#   (W5) chaque marqueur d'agent seul à 1 sans -DryRun : rc 7, journal absent,
#        le message nomme CE marqueur ; le même en -DryRun : permis (rc 1) ;
#        les cinq faits de blancs (mêmes blancs que (9)) : valent absents, pas
#        de refus 7 ;
#   (W6) hors Windows sans SETUP_PS1_OS : rc 2 et nomme setup.sh ;
#   (W7) winget absent : rc 2, nomme App Installer ;
#   (W8) python absent : winget Python.Python.3.12, python RE-SONDÉ, pip pytest,
#        rc 0 ; winget inerte (ne pose rien) : python et pytest manquent encore,
#        commandes et note PATH affichées, rc 1 ;
#   (W9) le repli `Arguments` de 5.1, FORCÉ sur une copie dont seule la ligne
#        d'aiguillage change : (W3) rejoué dessus, rc 0 ; valeurs piégées
#        (vide, espace, guillemets, antislashs, tabulation) passées par son
#        Invoke-CapturedProcess, reçues intactes — contrôle par ArgumentList.
#   (W10) dialogue réel sous pty : seuls o/oui minuscules arment, avec vrai git,
#         vrai Python >= 3.11 et winget factice ; non-TTY, --depuis et Python
#         3.9 sont aussi vérifiés ; échec d'installation annoncé sans changer
#         le code de retour du setup ; CLAUDECODE vide ou blanc : la question
#         est posée ; hors kit, jamais --depuis ; git config --local du kit
#         inchangée ; sans pwsh, SKIP annoncé.
#
# PREUVE DE MUTATION : SETUP_SH=<copie mutée> et SETUP_PS1=<copie mutée>
# rejouent le banc sur une copie ; le fichier suivi n'est jamais modifié.
# Mutants nommés : « arme brew,pytest réintroduite » dans sp_paquet → (2), (4)
# et (16) rougissent (revue de clôture, F1) ; aiguillage root de l'installation
# (`= "0"` → `= "x"`) ou `&&` → `;` sous root → (10r) ; note de --dry-run ôtée
# → (4) ; ConvertTo-NativeArgument qui ne cite plus, repli qui ne pose plus
# Arguments, ou `[AllowEmptyString()]` ôté de Join-NativeArguments (le défaut
# que (W9) a trouvé le 2026-10-14 : un argument vide faisait jeter le repli)
# → (W9).
#
# NON MESURÉ ICI : une installation réelle (brew, apt, winget) ; Windows
# PowerShell 5.1 (W0 le borne par lecture ; W9 joue le code de son repli sous
# pwsh, pas l'aiguillage sous .NET Framework ni le découpage de Windows) ; les
# identifiants winget. Le FAUX VERT de la sonde pytest du doctor (binaire
# `pytest` présent, `python3 -m pytest` en échec) est fermé par le mode `module:`
# de l'inventaire et tenu par le cas 19 de doctor.test.sh ; ici, les bouchons
# d'interpréteur suivent la même règle (stub : `-m <module>`).
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
# Marqueurs d'agent autres que CLAUDECODE (en-tête de setup.sh, étape 0) : un
# banc joué sous Claude Code (CLAUDE_CODE_ENTRYPOINT) ou Copilot CLI ne doit pas
# voir chaque cas refusé en 7 ; AGENTS_HOOK_HOST n'est posé que dans un
# sous-processus de hook du kit, jamais dans le shell de l'agent — sous Codex,
# Kimi ou Gemini, le shell de l'agent ne porte AUCUN marqueur mesuré (faux
# négatif nommé de setup.sh : la garde freine, elle ne ferme pas) ; il est ôté
# ici pour un banc lancé depuis un hook. CLAUDECODE reste ôté appel par appel
# (`env -u CLAUDECODE`), les cas (9) et (W5) posent chaque marqueur eux-mêmes.
unset CLAUDE_CODE_ENTRYPOINT AGENTS_HOOK_HOST COPILOT_AGENT_SESSION_ID COPILOT_CLI
MARQUEURS_AGENT="CLAUDECODE CLAUDE_CODE_ENTRYPOINT AGENTS_HOOK_HOST COPILOT_AGENT_SESSION_ID COPILOT_CLI"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SCRIPT="${SETUP_SH:-$HERE/setup.sh}"
PS1_SCRIPT="${SETUP_PS1:-$HERE/setup.ps1}"
INV="$ROOT/core-scripts/tool-inventory.tsv"
[ -f "$SCRIPT" ] || { echo "FAIL: $SCRIPT introuvable"; exit 1; }
[ -f "$PS1_SCRIPT" ] || { echo "FAIL: $PS1_SCRIPT introuvable"; exit 1; }
[ -f "$INV" ] || { echo "FAIL: $INV introuvable"; exit 1; }

pass=0; fail=0
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
ko() { echo "FAIL: $1"; fail=$((fail + 1)); }
bilan() {
  echo "TOTAL: $((pass + fail)) témoins — $pass PASS, $fail FAIL"
  [ "$fail" -eq 0 ]
}

echo "== setup.test.sh ($SCRIPT, $PS1_SCRIPT) =="

TMP="$(mktemp -d)" || { echo "FAIL: mktemp"; exit 1; }
trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/stdout"
ERR="$TMP/stderr"
RC=0
BASHX="bash"

# Les cas (1)-(17) jouent setup.sh EN MODE KIT, quel que soit l'arbre qui porte
# ce banc : une copie de $SCRIPT dans un arbre jetable qui porte
# .agents/IS_THE_KIT. Hors du kit, setup.sh planifie aussi les scanners
# (en-tête, CE QU'IL INSTALLE ; cas (19)-(22)) : sans cette copie, un arbre
# adoptant, ou une copie mutée SETUP_SH=… posée hors de tout arbre, verrait
# gitleaks et semgrep entrer dans chaque commande attendue.
SCRIPT_KIT="$TMP/arbre-kit/core-scripts/setup.sh"
mkdir -p "$TMP/arbre-kit/core-scripts" "$TMP/arbre-kit/.agents"
cp "$SCRIPT" "$SCRIPT_KIT"
: > "$TMP/arbre-kit/.agents/IS_THE_KIT"

# --- les cinq jetons B de l'inventaire réel, lus par nom de colonne -----------
jetons_b() { # jetons_b <os> : les jetons `tool` de classe B valant pour <os>, un par ligne
  awk -F'\t' -v os="$1" '
    { sub(/\r$/, "") }
    /^#/ { next }
    !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
    /^[[:space:]]*$/ { next }
    $c["nature"] == "outil" && $c["class"] == "B" && ($c["os"] == "any" || index("," $c["os"] ",", "," os ",")) { print $c["tool"] }
  ' "$INV"
}
B_DARWIN="$(jetons_b darwin | tr '\n' ' ' | sed 's/ $//')"
B_LINUX="$(jetons_b linux | tr '\n' ' ' | sed 's/ $//')"
B_WINDOWS="$(jetons_b windows | tr '\n' ' ' | sed 's/ $//')"

# --- bouchons -----------------------------------------------------------------
# stub <dir> <nom> <ligne de --version> [rc] : un outil factice (forme de doctor.test.sh).
# Lancé en interpréteur (`-m <module> …`, la sonde `module:` du doctor pour pytest),
# il ne réussit QUE si un bouchon <module> est posé dans son propre dossier — « pytest
# installé » ; sinon « No module named », rc 1, comme un python3 sans pytest. Un
# bouchon qui rendrait rc 0 à tout ferait passer pytest pour présent dès que python3
# l'est. Une copie (le faux gestionnaire) lit le dossier où elle est posée.
stub() {
  case "$2" in
    */*|"")
      echo "stub: nom refusé « $2 »" >&2
      return 1
      ;;
  esac
  mkdir -p "$1"
  printf '#!/bin/sh\nif [ "$1" = "-m" ]; then\n  if [ -e "$(dirname "$0")/$2" ]; then echo "$2 (%s)"; exit 0; fi\n  echo "No module named $2" >&2\n  exit 1\nfi\necho "%s"\nexit %s\n' "$3" "$3" "${4:-0}" > "$1/$2"
  chmod +x "$1/$2"
}

# premier <jeton> : la première alternative d'un jeton `a|b|c`
_pipe='|'
premier() { printf '%s\n' "${1%%"$_pipe"*}"; }

# pose_tous <dir> <liste de jetons> : un bouchon par jeton (première alternative), version 99
pose_tous() {
  local j
  for j in $2; do
    stub "$1" "$(premier "$j")" "x 99.0.0" || ko "pose_tous : bouchon refusé pour $j"
  done
}

# faux_gestionnaire <dir> <brew|apt-get> [echec|inerte|update-echec] : journalise
# dans <dir>/../journal, « installe » en COPIANT le bouchon de réserve
# <dir>/../reserve/outil (version 99) sous le nom de l'outil pour chaque paquet
# (table du bouchon : python→python3, python3-pytest→pytest, et pour apt-get
# SEUL coreutils→tee — le coreutils de Homebrew pose gtee, jamais tee —, les
# autres à leur nom ; `-y` et `--` sont ignorés). `echec` : `install` rend 1
# sans rien poser ; `inerte` : rend 0 sans rien poser ; `update-echec` :
# `update` rend 1 (apt-get).
faux_gestionnaire() {
  local dir="$1" nom="$2" mode="${3:-}" journal reserve rc_update
  journal="$(dirname "$dir")/journal"
  reserve="$(dirname "$dir")/reserve"
  mkdir -p "$dir"
  stub "$reserve" outil "x 99.0.0"
  rc_update=0
  [ "$mode" = "update-echec" ] && rc_update=1
  {
    printf '#!/bin/sh\n'
    printf 'PATH=/usr/bin:/bin:$PATH\n'
    printf 'DIR=%s\n' "'$dir'"
    printf 'JOURNAL=%s\n' "'$journal'"
    printf 'RESERVE=%s\n' "'$reserve'"
    printf '%s\n' 'echo "$@" >> "$JOURNAL"' \
      'if [ "$1" = "--prefix" ]; then echo "$DIR/prefix"; exit 0; fi'
    printf 'if [ "$1" = "update" ]; then exit %s; fi\n' "$rc_update"
    printf '%s\n' 'if [ "$1" != "install" ]; then exit 2; fi' \
      'shift'
    if [ "$mode" = "echec" ]; then
      printf '%s\n' 'echo "faux gestionnaire : echec demande" >&2' 'exit 1'
    elif [ "$mode" = "inerte" ]; then
      printf '%s\n' 'exit 0'
    else
      printf '%s\n' 'for p in "$@"; do' \
        '  case "$p" in' \
        '    -y|--) continue ;;' \
        '    python) t=python3 ;;' \
        '    python3-pytest) t=pytest ;;'
      [ "$nom" = apt-get ] && printf '%s\n' '    coreutils) t=tee ;;'
      printf '%s\n' '    *) t="$p" ;;' \
        '  esac' \
        '  cp "$RESERVE/outil" "$DIR/$t"' \
        'done' \
        'exit 0'
    fi
  } > "$dir/$nom"
  chmod +x "$dir/$nom"
}

# faux_sudo <dir> : exécute ses arguments, journalise `sudo …`
faux_sudo() {
  mkdir -p "$1"
  {
    printf '#!/bin/sh\n'
    printf 'JOURNAL=%s\n' "'$(dirname "$1")/journal'"
    printf '%s\n' 'echo "sudo $*" >> "$JOURNAL"' 'echo "faux sudo : appel $1"' 'exec "$@"'
  } > "$1/sudo"
  chmod +x "$1/sudo"
}

# poste <nom> <darwin|linux> <jetons déjà posés> [mode gestionnaire] : un PATH jetable ; imprime son dossier bin
poste() {
  local d="$TMP/$1/bin"
  mkdir -p "$d"
  if [ "$2" = darwin ]; then
    faux_gestionnaire "$d" brew "${4:-}"
  else
    faux_gestionnaire "$d" apt-get "${4:-}"
    faux_sudo "$d"
  fi
  pose_tous "$d" "$3"
  printf '%s' "$d"
}

# L'inventaire et le doctor sont passés EXPLICITEMENT : une copie mutée du script
# (SETUP_SH=…) vit hors de core-scripts/ et ne les trouverait pas à côté d'elle.
# Un cas qui passe son propre --inventory après gagne (le dernier l'emporte).
DOC="$ROOT/core-scripts/doctor.sh"
lance() { # lance <os> <bin> [args…] : code dans RC, sans CLAUDECODE
  local os="$1" bin="$2"
  shift 2
  env -u CLAUDECODE "SETUP_OS=$os" "SETUP_PROBE_PATH=$bin" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" "$@" > "$OUT" 2> "$ERR"
  RC=$?
}

# faux_id <dir> : un `id` dont `-u` rend 0 — root SANS aucun privilège réel ; tout
# autre appel passe au vrai id. setup.sh cherche `id` dans SON PATH (pas dans
# SETUP_PROBE_PATH) : lance_root le pose en tête de ce PATH-là.
faux_id() {
  mkdir -p "$1"
  printf '%s\n' '#!/bin/sh' 'if [ "$1" = "-u" ]; then echo 0; exit 0; fi' 'exec /usr/bin/id "$@"' > "$1/id"
  chmod +x "$1/id"
}
lance_root() { # lance_root <bin> [args…] : comme `lance linux`, mais `id -u` rend 0 ; code dans RC
  local bin="$1" racine
  shift
  racine="$(dirname "$bin")/racine"
  faux_id "$racine"
  env -u CLAUDECODE "PATH=$racine:$PATH" "SETUP_OS=linux" "SETUP_PROBE_PATH=$bin" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" "$@" > "$OUT" 2> "$ERR"
  RC=$?
}

journal() { cat "$(dirname "$1")/journal" 2>/dev/null; }
journal_absent() { [ ! -e "$(dirname "$1")/journal" ]; }
resume() { grep '^setup: installés=' "$OUT"; }
diag() { cat "$ERR"; }

# ============================================================================
# (1) tout présent
# ============================================================================
cas_1() {
  local b
  b="$(poste c1 darwin "$B_DARWIN")"
  lance darwin "$b"
  [ "$RC" -eq 0 ] || { ko "(1) tout présent : rc $RC ≠ 0 — $(diag)"; return; }
  journal_absent "$b" || { ko "(1) tout présent : le gestionnaire a été appelé — $(journal "$b")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$B_DARWIN manque encore=aucun — exit 0" ] \
    || { ko "(1) tout présent : résumé « $(resume) »"; return; }
  ok "(1) tout présent : rc 0, déjà là = $B_DARWIN, gestionnaire jamais appelé"
}

# ============================================================================
# (2) git et pytest absents, (3) idempotence
# ============================================================================
cas_2_3() {
  local b reste sans_pytest
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/git //; s/ pytest//')"
  sans_pytest="$(printf '%s\n' "$B_DARWIN" | sed 's/ pytest//')"
  b="$(poste c2 darwin "$reste")"
  lance darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(2) absents : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  # pytest n'a AUCUN paquet brew : la formule s'installe dans son virtualenv,
  # invisible de `python3 -m pytest` — jamais un `install … pytest` au journal.
  [ "$(journal "$b")" = "install -- git" ] || { ko "(2) absents : journal « $(journal "$b") » ≠ « install -- git » (pytest n'a aucun paquet brew)"; return; }
  [ -x "$b/git" ] || { ko "(2) absents : bouchon git non posé"; return; }
  [ ! -e "$b/pytest" ] || { ko "(2) absents : un bouchon pytest a été posé — brew a reçu pytest"; return; }
  # Le bouchon posé RÉPOND (sinon le doctor dirait « version non mesurée », et PRESENT à tort).
  [ "$("$b/git" --version 2>/dev/null)" = "x 99.0.0" ] || { ko "(2) absents : le bouchon git posé ne répond pas « x 99.0.0 »"; return; }
  grep -q '^setup: lance : brew install -- git$' "$OUT" || { ko "(2) absents : « lance : brew install -- git » non annoncé avant — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=git déjà là=$reste manque encore=pytest — exit 1" ] \
    || { ko "(2) absents : résumé « $(resume) »"; return; }
  grep -q '^  installé           git$' "$OUT" || { ko "(2) absents : ligne « installé git » absente"; return; }
  grep -q '^  manque encore      pytest$' "$OUT" || { ko "(2) absents : ligne « manque encore pytest » absente — $(cat "$OUT")"; return; }
  grep -qF '    a installer vous-meme : aucun paquet brew connu de ce script' "$OUT" || { ko "(2) absents : pytest n'est pas dit « a installer vous-meme » — $(cat "$OUT")"; return; }
  grep -qF '    note : la porte lance python3 -m pytest : python3 -m pip install --user pytest==' "$OUT" \
    || { ko "(2) absents : la note pip de pytest est absente — $(cat "$OUT")"; return; }
  ok "(2) git et pytest absents : brew install -- git SEUL, installés=git, manque encore=pytest avec la note pip, rc 1"

  : > "$(dirname "$b")/journal"
  lance darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(3) idempotence : rc $RC ≠ 1 — $(diag)"; return; }
  [ -z "$(journal "$b")" ] || { ko "(3) idempotence : le gestionnaire a été rappelé — $(journal "$b")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$sans_pytest manque encore=pytest — exit 1" ] \
    || { ko "(3) idempotence : résumé « $(resume) »"; return; }
  ok "(3) idempotence : relancé, journal vide (git pas réinstallé), manque encore=pytest seul, rc 1"

  # pytest posé à la main (la note pip suivie) : plus rien à faire, rc 0.
  stub "$b" pytest "pytest 9.1.1"
  lance darwin "$b"
  [ "$RC" -eq 0 ] || { ko "(3) pytest posé à la main : rc $RC ≠ 0 — $(diag)"; return; }
  [ -z "$(journal "$b")" ] || { ko "(3) pytest posé à la main : le gestionnaire a été rappelé — $(journal "$b")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$B_DARWIN manque encore=aucun — exit 0" ] \
    || { ko "(3) pytest posé à la main : résumé « $(resume) »"; return; }
  ok "(3) idempotence : pytest posé à la main, relancé, rc 0, journal vide, tout déjà là"
}

# ============================================================================
# (4) --dry-run
# ============================================================================
cas_4() {
  local b reste bl reste_l
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/git //; s/ pytest//')"
  b="$(poste c4 darwin "$reste")"
  lance darwin "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(4) dry-run : rc $RC ≠ 1 — $(diag)"; return; }
  journal_absent "$b" || { ko "(4) dry-run : le gestionnaire a été appelé — $(journal "$b")"; return; }
  [ ! -e "$b/git" ] && [ ! -e "$b/pytest" ] || { ko "(4) dry-run : un bouchon a été posé"; return; }
  grep -q '^setup: --dry-run : lancerait : brew install -- git$' "$OUT" || { ko "(4) dry-run : « lancerait : brew install -- git » absent (pytest n'a aucun paquet brew) — $(cat "$OUT")"; return; }
  grep -q '^setup: --dry-run : sans paquet connu, a installer vous-meme : pytest$' "$OUT" \
    || { ko "(4) dry-run : pytest n'est pas dit « a installer vous-meme » — $(cat "$OUT")"; return; }
  # La commande pip est dite AVANT d'installer : sans elle, --dry-run sur macOS
  # laisse l'utilisateur sans la seule commande qui pose pytest (constat du 2026-10-14).
  grep -qF 'setup: --dry-run : note pytest : la porte lance python3 -m pytest : python3 -m pip install --user pytest==' "$OUT" \
    || { ko "(4) dry-run : la commande pip de pytest n'est pas donnée — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste manque encore=git pytest — exit 1" ] \
    || { ko "(4) dry-run : résumé « $(resume) »"; return; }
  ok "(4) --dry-run : rc 1, « lancerait : brew install -- git », pytest à installer soi-même AVEC la commande pip, rien appelé, rien posé"

  env "CLAUDECODE=1" "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" --dry-run > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 1 ] || { ko "(4) dry-run sous CLAUDECODE : rc $RC ≠ 1 — $(diag)"; return; }
  journal_absent "$b" || { ko "(4) dry-run sous CLAUDECODE : gestionnaire appelé"; return; }
  ok "(4) --dry-run sous CLAUDECODE=1 : permis (rc 1, rien n'est modifié)"

  # linux en --dry-run : ni `update` ni `install` (journal ABSENT — un
  # `apt-get update` glissé dans la branche dry-run y laisserait une ligne), et
  # la commande annoncée porte le `--`. Root-agnostique (sans sudo sous root) :
  # (14) rejoue ce cas sous /bin/bash 3.2.
  reste_l="$(printf '%s\n' "$B_LINUX" | sed 's/git //')"
  bl="$(poste c4l linux "$reste_l")"
  lance linux "$bl" --dry-run
  [ "$RC" -eq 1 ] || { ko "(4) dry-run linux : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$bl" || { ko "(4) dry-run linux : apt-get ou sudo appelé — $(journal "$bl")"; return; }
  [ ! -e "$bl/git" ] || { ko "(4) dry-run linux : un bouchon a été posé"; return; }
  grep -q '^setup: --dry-run : lancerait : .*apt-get update && .*apt-get install -y -- git$' "$OUT" \
    || { ko "(4) dry-run linux : « lancerait » absent — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste_l manque encore=git — exit 1" ] \
    || { ko "(4) dry-run linux : résumé « $(resume) »"; return; }
  ok "(4) --dry-run linux : rc 1, « lancerait : … apt-get update && … apt-get install -y -- git », ni update ni install appelés"

  # `apt-get update` qui rend 1 : `install` n'est JAMAIS lancé (`&&`, pas `;`),
  # le code est rapporté, rc 1.
  bl="$(poste c4u linux "$reste_l" update-echec)"
  lance linux "$bl"
  [ "$RC" -eq 1 ] || { ko "(4) update en échec : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  grep -q 'update' "$(dirname "$bl")/journal" 2>/dev/null || { ko "(4) update en échec : update jamais appelé — $(journal "$bl")"; return; }
  if grep -q 'install' "$(dirname "$bl")/journal"; then
    ko "(4) update en échec : install lancé malgré l'échec d'update — $(journal "$bl")"
    return
  fi
  [ ! -e "$bl/git" ] || { ko "(4) update en échec : un bouchon a été posé"; return; }
  grep -q '^setup: le gestionnaire a rendu 1' "$ERR" || { ko "(4) update en échec : code non rapporté — $(diag)"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste_l manque encore=git — exit 1" ] \
    || { ko "(4) update en échec : résumé « $(resume) »"; return; }
  ok "(4) apt-get update qui rend 1 : install jamais lancé, « le gestionnaire a rendu 1 », manque encore=git, rc 1"
}

# ============================================================================
# (5) refus d'usage, rc 2
# ============================================================================
cas_5() {
  local b
  b="$(poste c5 darwin "$B_DARWIN")"
  lance freebsd "$b" --dry-run
  [ "$RC" -eq 2 ] && grep -q 'non prise en charge : freebsd' "$ERR" || { ko "(5) freebsd : rc $RC — $(diag)"; return; }
  journal_absent "$b" || { ko "(5) freebsd : gestionnaire appelé"; return; }
  ok "(5) SETUP_OS=freebsd : rc 2, plateforme non prise en charge, rien appelé"

  lance windows "$b" --dry-run
  [ "$RC" -eq 2 ] && grep -q 'setup.ps1' "$ERR" || { ko "(5) windows : rc $RC — $(diag)"; return; }
  ok "(5) SETUP_OS=windows : rc 2, renvoie à core-scripts/setup.ps1"

  lance darwin "$b" --frobnicate
  [ "$RC" -eq 2 ] && grep -q 'argument inconnu : --frobnicate' "$ERR" || { ko "(5) argument inconnu : rc $RC — $(diag)"; return; }
  ok "(5) argument inconnu : rc 2"

  lance darwin "$b" --inventory
  [ "$RC" -eq 2 ] || { ko "(5) --inventory nu : rc $RC — $(diag)"; return; }
  ok "(5) --inventory sans fichier : rc 2"

  lance darwin "$b" --inventory "$TMP/absent.tsv"
  [ "$RC" -eq 2 ] && grep -q 'inventaire illisible' "$ERR" || { ko "(5) inventaire absent : rc $RC — $(diag)"; return; }
  ok "(5) inventaire introuvable : rc 2"

  # Inventaire sans colonne `class` : le doctor le refuse, setup ne devine pas.
  awk -F'\t' -v OFS='\t' '!/^#/ && !h { h = 1; for (i = 1; i <= NF; i++) if ($i == "class") $i = "klass" } { print }' "$INV" > "$TMP/c5-sans-class.tsv"
  lance darwin "$b" --inventory "$TMP/c5-sans-class.tsv"
  [ "$RC" -eq 2 ] && grep -q 'n a pas rendu de ligne de resume' "$ERR" || { ko "(5) inventaire sans colonne class : rc $RC — $(diag)"; return; }
  journal_absent "$b" || { ko "(5) inventaire sans colonne class : gestionnaire appelé"; return; }
  ok "(5) inventaire que le doctor refuse (colonne class absente) : rc 2, rien appelé"
}

# ============================================================================
# (6) brew absent
# ============================================================================
cas_6() {
  local b
  b="$TMP/c6/bin"
  mkdir -p "$b"
  pose_tous "$b" "$B_DARWIN"
  lance darwin "$b"
  [ "$RC" -eq 2 ] && grep -q 'https://brew.sh' "$ERR" || { ko "(6) brew absent : rc $RC — $(diag)"; return; }
  grep -q 'installateur telecharge' "$ERR" || { ko "(6) brew absent : ne dit pas qu'il ne lance jamais un installateur"; return; }
  ok "(6) brew absent sur darwin : rc 2, renvoie à brew.sh, aucun installateur lancé"
}

# ============================================================================
# (7) gestionnaire en échec
# ============================================================================
cas_7() {
  local b reste
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/git //')"
  b="$(poste c7 darwin "$reste" echec)"
  lance darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(7) échec : rc $RC ≠ 1 — $(diag)"; return; }
  [ "$(journal "$b")" = "install -- git" ] || { ko "(7) échec : journal « $(journal "$b") »"; return; }
  grep -q '^setup: le gestionnaire a rendu 1' "$ERR" || { ko "(7) échec : code du gestionnaire non rapporté — $(diag)"; return; }
  grep -q '^    a taper : brew install -- git$' "$OUT" || { ko "(7) échec : commande à taper absente — $(cat "$OUT")"; return; }
  grep -q '^    doctor : ABSENT (requis) *git — ' "$OUT" || { ko "(7) échec : ligne du doctor absente — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste manque encore=git — exit 1" ] \
    || { ko "(7) échec : résumé « $(resume) »"; return; }
  ok "(7) brew install qui échoue : rc 1, manque encore=git, ligne du doctor et commande à taper affichées"
}

# ============================================================================
# (8) outil B sans paquet connu (inventaire fixture)
# ============================================================================
cas_8() {
  local b reste
  # git absent (pytest n'a pas de paquet brew : il ne prouverait pas que frob
  # reste hors d'une commande qui part quand même).
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/git //')"
  b="$(poste c8 darwin "$reste")"
  # Une ligne B `frob`, sans canal, ajoutée à l'inventaire réel (13 colonnes après tool,
  # la dernière `mode_sonde` = `-` : recherche par nom).
  cp "$INV" "$TMP/c8.tsv"
  printf 'frob\toutil\tany\tB\t-\t-\t-\t-\t-\t-\tfixture : sans ce jeton le banc ne prouve rien\t-\t-\t-\n' >> "$TMP/c8.tsv"
  lance darwin "$b" --inventory "$TMP/c8.tsv"
  [ "$RC" -eq 1 ] || { ko "(8) sans canal : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "install -- git" ] || { ko "(8) sans canal : journal « $(journal "$b") » — frob ne doit pas y être"; return; }
  grep -q '^  absent             frob — aucun paquet brew connu de ce script$' "$OUT" || { ko "(8) sans canal : ligne « aucun paquet » absente — $(cat "$OUT")"; return; }
  grep -q '^    a installer vous-meme : aucun paquet brew connu' "$OUT" || { ko "(8) sans canal : rien à taper ?"; return; }
  [ "$(resume)" = "setup: installés=git déjà là=$reste manque encore=frob — exit 1" ] \
    || { ko "(8) sans canal : résumé « $(resume) »"; return; }
  ok "(8) outil B sans paquet connu : hors de la commande, « aucun paquet brew connu », git installé quand même, rc 1"
}

# ============================================================================
# (9) sous un agent
# ============================================================================
cas_9() {
  local b reste m blanc
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/git //')"
  b="$(poste c9 darwin "$reste")"
  for m in $MARQUEURS_AGENT; do
    # Un marqueur SEUL : les quatre autres ôtés (CLAUDECODE vient de l'hôte).
    env -u CLAUDECODE "$m=1" "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" > "$OUT" 2> "$ERR"
    RC=$?
    [ "$RC" -eq 7 ] || { ko "(9) $m=1 : rc $RC ≠ 7 — $(diag)"; return; }
    journal_absent "$b" || { ko "(9) $m=1 : gestionnaire appelé"; return; }
    [ ! -e "$b/git" ] || { ko "(9) $m=1 : bouchon posé"; return; }
    grep -q 'pas par un agent' "$ERR" || { ko "(9) $m=1 : message — $(diag)"; return; }
    grep -qF "($m est pose ici)" "$ERR" || { ko "(9) $m=1 : le message ne nomme pas $m — $(diag)"; return; }
    ok "(9) $m=1 sans --dry-run : rc 7, rien appelé, rien posé, $m nommé"

    env -u CLAUDECODE "$m=1" "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" --dry-run > "$OUT" 2> "$ERR"
    RC=$?
    [ "$RC" -eq 1 ] || { ko "(9) --dry-run sous $m=1 : rc $RC ≠ 1 — $(diag)"; return; }
    journal_absent "$b" || { ko "(9) --dry-run sous $m=1 : gestionnaire appelé"; return; }
    ok "(9) --dry-run sous $m=1 : permis (rc 1, rien appelé)"
  done

  # \v et \f compris : blancs pour setup.ps1 (IsNullOrWhiteSpace) comme ici.
  blanc="$(printf ' \t\v\f ')"
  env "CLAUDECODE=$blanc" "CLAUDE_CODE_ENTRYPOINT=$blanc" "AGENTS_HOOK_HOST=$blanc" "COPILOT_AGENT_SESSION_ID=$blanc" "COPILOT_CLI=$blanc" \
    "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$DOC" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(9) marqueurs de blancs : rc $RC ≠ 0 — $(diag)"; return; }
  [ "$(journal "$b")" = "install -- git" ] || { ko "(9) marqueurs de blancs : journal « $(journal "$b") »"; return; }
  ok "(9) les cinq marqueurs faits de blancs (espace, \\t, \\v, \\f) : valent absents, l'installation passe (rc 0)"
}

# ============================================================================
# (10) linux : sudo annoncé, apt-get absent, sudo absent
# ============================================================================
cas_10() {
  local b reste
  [ "$(id -u)" != "0" ] || { echo "SKIP: (10) lancé en root — la voie sudo n'est pas jouable ici"; return; }
  reste="$(printf '%s\n' "$B_LINUX" | sed 's/git //')"
  b="$(poste c10 linux "$reste")"
  lance linux "$b"
  [ "$RC" -eq 0 ] || { ko "(10) linux : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf 'sudo %s update\nupdate\nsudo %s install -y -- git\ninstall -y -- git' "$b/apt-get" "$b/apt-get")" ] \
    || { ko "(10) linux : journal inattendu — $(journal "$b")"; return; }
  grep -q '^setup: lance : sudo apt-get update && sudo apt-get install -y -- git$' "$OUT" || { ko "(10) linux : commande non annoncée — $(cat "$OUT")"; return; }
  grep -q '^setup: sudo va demander votre mot de passe' "$OUT" || { ko "(10) linux : sudo non annoncé"; return; }
  # L'annonce PRÉCÈDE l'appel : le faux sudo écrit « faux sudo : appel » sur la
  # sortie standard au moment où il est appelé ; les deux annonces doivent être
  # au-dessus de ce marqueur.
  l_annonce="$(grep -n '^setup: sudo va demander' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_lance="$(grep -n '^setup: lance : ' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_appel="$(grep -n '^faux sudo : appel ' "$OUT" | sed -n 1p | cut -d: -f1)"
  [ -n "$l_annonce" ] && [ -n "$l_lance" ] && [ -n "$l_appel" ] && [ "$l_annonce" -lt "$l_appel" ] && [ "$l_lance" -lt "$l_appel" ] \
    || { ko "(10) linux : l'annonce (lignes $l_lance, $l_annonce) ne précède pas l'appel de sudo (ligne $l_appel)"; return; }
  [ "$(resume)" = "setup: installés=git déjà là=$reste manque encore=aucun — exit 0" ] \
    || { ko "(10) linux : résumé « $(resume) »"; return; }
  ok "(10) linux non root : sudo annoncé avant, apt-get update puis install -y -- git sous sudo, rc 0"

  b="$TMP/c10b/bin"
  mkdir -p "$b"
  pose_tous "$b" "$B_LINUX"
  lance linux "$b"
  [ "$RC" -eq 2 ] && grep -q 'apt-get introuvable' "$ERR" || { ko "(10) apt-get absent : rc $RC — $(diag)"; return; }
  ok "(10) linux sans apt-get : rc 2"

  b="$(poste c10c linux "$reste")"
  rm -f "$b/sudo"
  lance linux "$b"
  [ "$RC" -eq 1 ] || { ko "(10) sudo absent : rc $RC ≠ 1 — $(diag)"; return; }
  journal_absent "$b" || { ko "(10) sudo absent : apt-get appelé sans root — $(journal "$b")"; return; }
  grep -q '^setup:   apt-get update && apt-get install -y -- git$' "$ERR" || { ko "(10) sudo absent : commande root absente — $(diag)"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste manque encore=git — exit 1" ] \
    || { ko "(10) sudo absent : résumé « $(resume) »"; return; }
  ok "(10) linux sans sudo : rien lancé, la commande root est affichée, rc 1"
}

# ============================================================================
# (10r) linux EN ROOT : `update && install`, jamais sudo — joué par un faux `id`
# ============================================================================
cas_10r() {
  local b reste
  reste="$(printf '%s\n' "$B_LINUX" | sed 's/git //')"
  b="$(poste c10r linux "$reste")"
  [ "$(PATH="$(dirname "$b")/racine:$PATH"; faux_id "$(dirname "$b")/racine"; id -u)" = "0" ] \
    || { ko "(10r) root : le faux id ne rend pas 0 — le cas ne jouerait pas la voie root"; return; }

  lance_root "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(10r) root, dry-run : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(10r) root, dry-run : apt-get ou sudo appelé — $(journal "$b")"; return; }
  grep -q '^setup: --dry-run : lancerait : apt-get update && apt-get install -y -- git$' "$OUT" \
    || { ko "(10r) root, dry-run : « lancerait » sans sudo absent — $(cat "$OUT")"; return; }
  ok "(10r) root, --dry-run : « lancerait : apt-get update && apt-get install -y -- git », sans sudo, rien appelé"

  lance_root "$b"
  [ "$RC" -eq 0 ] || { ko "(10r) root : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf 'update\ninstall -y -- git')" ] \
    || { ko "(10r) root : journal « $(journal "$b") » ≠ « update » puis « install -y -- git », sans sudo"; return; }
  grep -q '^setup: lance : apt-get update && apt-get install -y -- git$' "$OUT" || { ko "(10r) root : commande sans sudo non annoncée — $(cat "$OUT")"; return; }
  if grep -qE '^setup: sudo va demander|^faux sudo : appel ' "$OUT"; then
    ko "(10r) root : sudo annoncé ou appelé sous root — $(grep -E '^setup: sudo|^faux sudo' "$OUT")"
    return
  fi
  [ "$(resume)" = "setup: installés=git déjà là=$reste manque encore=aucun — exit 0" ] \
    || { ko "(10r) root : résumé « $(resume) »"; return; }
  ok "(10r) linux en root (faux id) : apt-get update puis install -y -- git SANS sudo, rien de sudo annoncé, rc 0"

  # Root SANS sudo sur le poste : la voie root n'en a pas besoin — c'est ce qui
  # la distingue de (10) « sudo absent » (rien lancé, rc 1).
  b="$(poste c10s linux "$reste")"
  rm -f "$b/sudo"
  lance_root "$b"
  [ "$RC" -eq 0 ] || { ko "(10r) root sans sudo : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf 'update\ninstall -y -- git')" ] \
    || { ko "(10r) root sans sudo : journal « $(journal "$b") »"; return; }
  ok "(10r) root sans sudo sur le poste : installe quand même, rc 0 — la voie root ne passe jamais par sudo"

  # Root, `update` qui rend 1 : `install` n'est JAMAIS lancé (`&&`, pas `;`).
  b="$(poste c10u linux "$reste" update-echec)"
  lance_root "$b"
  [ "$RC" -eq 1 ] || { ko "(10r) root, update en échec : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "update" ] || { ko "(10r) root, update en échec : journal « $(journal "$b") » ≠ « update » seul"; return; }
  grep -q '^setup: le gestionnaire a rendu 1' "$ERR" || { ko "(10r) root, update en échec : code non rapporté — $(diag)"; return; }
  ok "(10r) root, apt-get update qui rend 1 : install jamais lancé, rc 1"
}

# ============================================================================
# (11) mauvaise version
# ============================================================================
cas_11() {
  local b reste
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/bash //')"
  b="$(poste c11 darwin "$reste")"
  stub "$b" bash "GNU bash, version 3.2.57(1)-release"
  lance darwin "$b"
  [ "$RC" -eq 0 ] || { ko "(11) mauvaise version : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "install -- bash" ] || { ko "(11) mauvaise version : journal « $(journal "$b") »"; return; }
  grep -q '^  mauvaise version   bash — paquet brew : bash$' "$OUT" || { ko "(11) mauvaise version : ligne du plan absente — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=bash déjà là=$reste manque encore=aucun — exit 0" ] \
    || { ko "(11) mauvaise version : résumé « $(resume) »"; return; }
  ok "(11) bash 3.2 : entre dans le plan (mauvaise version), brew install bash, bash 99 vu après → installé"

  b="$(poste c11b darwin "$reste" inerte)"
  stub "$b" bash "GNU bash, version 3.2.57(1)-release"
  lance darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(11) version restée basse : rc $RC ≠ 1 — $(diag)"; return; }
  grep -q '^    doctor : MAUVAISE VERSION *bash — ' "$OUT" || { ko "(11) version restée basse : ligne du doctor absente — $(cat "$OUT")"; return; }
  grep -q "^    note : brew pose bash sous $b/prefix/bin : ouvrez un nouveau terminal, ou mettez ce dossier en tete de PATH$" "$OUT" \
    || { ko "(11) version restée basse : note PATH absente — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$reste manque encore=bash — exit 1" ] \
    || { ko "(11) version restée basse : résumé « $(resume) »"; return; }
  ok "(11) brew qui ne change rien : bash reste en mauvaise version, manque encore=bash, note sur le PATH, rc 1"
}

# ============================================================================
# (12) le doctor est la sonde
# ============================================================================
cas_12() {
  local b faux
  b="$(poste c12 darwin "$B_DARWIN")"
  faux="$TMP/c12/doctor.sh"
  # Un faux doctor qui déclare git manquant, quoi que le PATH contienne.
  printf '%s\n' '#!/bin/sh' \
    'echo "doctor: 4/5 présents, 0 N/A, 1 absents (B manquants=git, A manquants=0), mauvaise version=aucune, 0 conditions non sondées — exit 1"' \
    'exit 1' > "$faux"
  chmod +x "$faux"
  env -u CLAUDECODE "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$faux" "$BASHX" "$SCRIPT_KIT" --inventory "$INV" --dry-run > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 1 ] || { ko "(12) faux doctor : rc $RC ≠ 1 — $(diag)"; return; }
  grep -q '^setup: --dry-run : lancerait : brew install -- git$' "$OUT" || { ko "(12) faux doctor : setup n'a pas suivi le doctor — $(cat "$OUT")"; return; }
  ok "(12) SETUP_DOCTOR : git posé mais le doctor le dit manquant → setup planifie git (la sonde est le doctor, pas le script)"
}

# ============================================================================
# (13) une seule ligne de résumé, et son code
# ============================================================================
cas_13() {
  local b n
  b="$(poste c13 darwin "$B_DARWIN")"
  lance darwin "$b"
  n="$(grep -c '^setup: installés=' "$OUT")"
  [ "$n" -eq 1 ] || { ko "(13) résumé : $n lignes de résumé"; return; }
  [ "$(resume | sed 's/.* — exit //')" = "$RC" ] || { ko "(13) résumé : « exit $(resume | sed 's/.* — exit //') » ≠ rc $RC"; return; }
  [ "$(tail -n 1 "$OUT")" = "$(resume)" ] || { ko "(13) résumé : pas la dernière ligne"; return; }
  ok "(13) une ligne de résumé, la dernière, dont le « exit N » est le code rendu"
}

# ============================================================================
# (15) les outils requis sont LUS dans l'inventaire
# ============================================================================
cas_15() {
  local b
  b="$(poste c15 darwin "$B_DARWIN")"
  lance darwin "$b" --dry-run
  grep -q "^Requis (classe B de l inventaire, darwin) : $B_DARWIN$" "$OUT" || { ko "(15) requis : « $(grep '^Requis' "$OUT") » ≠ « $B_DARWIN »"; return; }
  [ "$(printf '%s\n' "$B_DARWIN" | wc -w | tr -d ' ')" -ge 5 ] || { ko "(15) requis : moins de 5 jetons B dans l'inventaire réel"; return; }
  ok "(15) requis = les $(printf '%s\n' "$B_DARWIN" | wc -w | tr -d ' ') jetons B de l'inventaire réel ($B_DARWIN), lus et non codés"
}

# ============================================================================
# (16) la TABLE sp_paquet est traversée : python3, pytest et tee n'ont pas de
#      colonne apt/brew dans l'inventaire réel, leur nom vient de la table
# ============================================================================
cas_16() {
  local b reste
  reste="$(printf '%s\n' "$B_LINUX" | sed 's/ python3|python|py//; s/ pytest//; s/ tee//')"
  b="$(poste c16l linux "$reste")"
  lance linux "$b"
  [ "$RC" -eq 0 ] || { ko "(16) table apt : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  grep -q '^install -y -- python3 python3-pytest coreutils$' "$(dirname "$b")/journal" 2>/dev/null \
    || { ko "(16) table apt : journal « $(journal "$b") » sans « install -y -- python3 python3-pytest coreutils »"; return; }
  [ "$(resume)" = "setup: installés=python3|python|py pytest tee déjà là=$reste manque encore=aucun — exit 0" ] \
    || { ko "(16) table apt : résumé « $(resume) »"; return; }
  ok "(16) table apt : python3, pytest, tee absents → install -y -- python3 python3-pytest coreutils, les trois installés, rc 0"

  # darwin : python3, pytest et tee absents → `install -- python` SEUL ; pytest
  # n'a aucun paquet brew (la formule vit dans son virtualenv, invisible de
  # `python3 -m pytest` que la porte lance), tee non plus (le coreutils de
  # Homebrew pose gtee, pas tee) : les deux manquent encore.
  reste="$(printf '%s\n' "$B_DARWIN" | sed 's/ python3|python|py//; s/ pytest//; s/ tee//')"
  b="$(poste c16d darwin "$reste")"
  lance darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(16) table brew : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "install -- python" ] || { ko "(16) table brew : journal « $(journal "$b") » ≠ « install -- python » (ni pytest ni tee n'ont de paquet brew)"; return; }
  [ ! -e "$b/pytest" ] || { ko "(16) table brew : un bouchon pytest a été posé — brew a reçu pytest"; return; }
  grep -q '^  absent             pytest — aucun paquet brew connu de ce script$' "$OUT" || { ko "(16) table brew : pytest devrait être sans paquet brew — $(cat "$OUT")"; return; }
  grep -q '^  absent             tee — aucun paquet brew connu de ce script$' "$OUT" || { ko "(16) table brew : tee devrait être sans paquet brew — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=python3|python|py déjà là=$reste manque encore=pytest tee — exit 1" ] \
    || { ko "(16) table brew : résumé « $(resume) »"; return; }
  ok "(16) table brew : python3 absent → install -- python ; pytest (virtualenv) et tee (gtee ≠ tee) sans paquet brew → manque encore=pytest tee, rc 1"
}

# ============================================================================
# (17) une cellule apt/brew de l'inventaire qui n'est pas un nom de paquet est
#      REFUSÉE avant d'atteindre le gestionnaire
# ============================================================================
cas_17() {
  local b os evil deja
  # Une option dpkg : sous `sudo apt-get install -y`, elle exécuterait /tmp/evil.
  evil='-oDpkg::Pre-Invoke::=/tmp/evil'
  cp "$INV" "$TMP/c17.tsv"
  printf 'evil\toutil\tany\tB\t-\t-\t-\t%s\t%s\t-\tfixture : une option, pas un paquet\t-\t-\t-\n' "$evil" "$evil" >> "$TMP/c17.tsv"
  for os in darwin linux; do
    if [ "$os" = darwin ]; then
      deja="$B_DARWIN"
      b="$(poste c17d darwin "$deja")"
    else
      deja="$B_LINUX"
      b="$(poste c17l linux "$deja")"
    fi
    lance "$os" "$b" --inventory "$TMP/c17.tsv"
    [ "$RC" -eq 1 ] || { ko "(17) $os : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
    journal_absent "$b" || { ko "(17) $os : le gestionnaire a été appelé — $(journal "$b")"; return; }
    grep -q 'REFUSÉE, elle commence par un tiret' "$ERR" || { ko "(17) $os : refus absent de stderr — $(diag)"; return; }
    grep -qF -- "$evil" "$ERR" || { ko "(17) $os : la cellule refusée n'est pas citée — $(diag)"; return; }
    grep -q '^  absent             evil — cellule .* de l inventaire REFUSÉE' "$OUT" || { ko "(17) $os : ligne du plan absente — $(cat "$OUT")"; return; }
    [ "$(resume)" = "setup: installés=aucun déjà là=$deja manque encore=evil — exit 1" ] \
      || { ko "(17) $os : résumé « $(resume) »"; return; }
    ok "(17) $os : cellule « $evil » REFUSÉE, rien passé au gestionnaire, manque encore=evil, rc 1"
  done

  # Deux paquets dans une cellule (un espace), ou tout caractère hors de
  # [A-Za-z0-9@._+-] : refusé aussi, même rien d'appelé.
  cp "$INV" "$TMP/c17b.tsv"
  printf 'evil\toutil\tany\tB\t-\t-\t-\tgit pytest\tgit pytest\t-\tfixture : deux noms dans une cellule\t-\t-\t-\n' >> "$TMP/c17b.tsv"
  b="$(poste c17e darwin "$B_DARWIN")"
  lance darwin "$b" --inventory "$TMP/c17b.tsv"
  [ "$RC" -eq 1 ] || { ko "(17) cellule « git pytest » : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(17) cellule « git pytest » : le gestionnaire a été appelé — $(journal "$b")"; return; }
  grep -q 'REFUSÉE, un nom de paquet n a que \[A-Za-z0-9@._+-\] : « git pytest »' "$ERR" || { ko "(17) cellule « git pytest » : refus absent — $(diag)"; return; }
  ok "(17) cellule « git pytest » (un espace) : REFUSÉE, rien passé au gestionnaire, rc 1"

  # Une cellule refusée qui porte un caractère de contrôle (ESC, une séquence
  # terminal) est citée avec `?` à sa place, dans les deux branches du refus.
  local esc
  esc="$(printf '\033')"
  cp "$INV" "$TMP/c17c.tsv"
  printf 'evc1\toutil\tany\tB\t-\t-\t-\t%s\t%s\t-\tfixture : tiret et ESC\t-\t-\t-\n' "-o${esc}[31m" "-o${esc}[31m" >> "$TMP/c17c.tsv"
  printf 'evc2\toutil\tany\tB\t-\t-\t-\t%s\t%s\t-\tfixture : ESC dans un nom\t-\t-\t-\n' "ab${esc}cd" "ab${esc}cd" >> "$TMP/c17c.tsv"
  b="$(poste c17c darwin "$B_DARWIN")"
  lance darwin "$b" --inventory "$TMP/c17c.tsv"
  [ "$RC" -eq 1 ] || { ko "(17) cellules à ESC : rc $RC ≠ 1 — $(diag)"; return; }
  journal_absent "$b" || { ko "(17) cellules à ESC : le gestionnaire a été appelé — $(journal "$b")"; return; }
  grep -qF 'REFUSÉE, elle commence par un tiret (une option, pas un paquet) : « -o?[31m »' "$ERR" \
    && grep -qF 'REFUSÉE, un nom de paquet n a que [A-Za-z0-9@._+-] : « ab?cd »' "$ERR" \
    || { ko "(17) cellules à ESC : la cellule refusée n'est pas citée avec « ? » — $(diag | LC_ALL=C tr '\001-\037\177' '?')"; return; }
  [ "$(LC_ALL=C grep -c "$esc" "$ERR")" -eq 0 ] && [ "$(LC_ALL=C grep -c "$esc" "$OUT")" -eq 0 ] \
    || { ko "(17) cellules à ESC : un octet ESC atteint la sortie"; return; }
  ok "(17) cellules à ESC (tiret, puis nom) : REFUSÉES, citées avec « ? » à la place du contrôle, aucun ESC en sortie, rc 1"

  # L'outil (cellule `tool`, du même fichier) cité dans le refus porte un ESC :
  # cité avec `?` lui aussi, dans les deux branches, aucun ESC sur stderr. Le
  # vrai doctor refuse un tel jeton (inventaire hors forme, rc 2) avant
  # sp_paquet : seul un doctor substitué (SETUP_DOCTOR, comme (12)) l'y mène.
  # stdout n'est PAS tenu ici : le plan, « Requis » et le résumé y citent
  # l'outil hors de sp_paquet.
  local faux
  cp "$INV" "$TMP/c17t.tsv"
  printf '%s\toutil\tany\tB\t-\t-\t-\t%s\t%s\t-\tfixture : outil à ESC, tiret\t-\t-\t-\n' "t${esc}[31m" "-o${esc}[32m" "-o${esc}[32m" >> "$TMP/c17t.tsv"
  printf '%s\toutil\tany\tB\t-\t-\t-\t%s\t%s\t-\tfixture : outil à ESC, nom\t-\t-\t-\n' "u${esc}[33m" "ab${esc}cd" "ab${esc}cd" >> "$TMP/c17t.tsv"
  b="$(poste c17t darwin "$B_DARWIN")"
  faux="$TMP/c17t/doctor.sh"
  printf '#!/bin/sh\necho "doctor: 5/7 présents, 0 N/A, 2 absents (B manquants=%s %s, A manquants=0), mauvaise version=aucune, 0 conditions non sondées — exit 1"\nexit 1\n' "t${esc}[31m" "u${esc}[33m" > "$faux"
  chmod +x "$faux"
  env -u CLAUDECODE "SETUP_OS=darwin" "SETUP_PROBE_PATH=$b" "SETUP_DOCTOR=$faux" "$BASHX" "$SCRIPT_KIT" --inventory "$TMP/c17t.tsv" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 1 ] || { ko "(17) outil à ESC : rc $RC ≠ 1 — $(diag | LC_ALL=C tr '\001-\037\177' '?')"; return; }
  journal_absent "$b" || { ko "(17) outil à ESC : le gestionnaire a été appelé — $(journal "$b")"; return; }
  grep -qF 'cellule brew de « t?[31m » REFUSÉE, elle commence par un tiret (une option, pas un paquet) : « -o?[32m »' "$ERR" \
    && grep -qF 'cellule brew de « u?[33m » REFUSÉE, un nom de paquet n a que [A-Za-z0-9@._+-] : « ab?cd »' "$ERR" \
    || { ko "(17) outil à ESC : l'outil n'est pas cité avec « ? » — $(diag | LC_ALL=C tr '\001-\037\177' '?')"; return; }
  [ "$(LC_ALL=C grep -c "$esc" "$ERR")" -eq 0 ] \
    || { ko "(17) outil à ESC : un octet ESC atteint stderr"; return; }
  ok "(17) outil à ESC (tiret, puis nom) : cité avec « ? » dans le refus, aucun ESC sur stderr, rc 1"
}

# ============================================================================
# (19)-(22) HORS DU KIT : arbre copié sans marqueur, vrai doctor, venv réel
# ============================================================================
VENV_HK=""
hk_venv() { # hk_venv : pose VENV_HK (bin du venv sans pip, python >= 3.11 du poste) ; rc 1 sinon
  local c py d
  [ -n "$VENV_HK" ] && return 0
  for c in python3 python; do
    py="$(command -v "$c" 2>/dev/null)" || continue
    "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1 || continue
    "$py" -m venv --without-pip "$TMP/hk-venv" >/dev/null 2>&1 || continue
    for d in "$TMP/hk-venv/bin" "$TMP/hk-venv/Scripts"; do
      [ -d "$d" ] && VENV_HK="$d"
    done
    [ -n "$VENV_HK" ] && return 0
  done
  return 1
}
hk_arbre() { # hk_arbre <nom> [manifestes…] : un arbre sans marqueur sous $TMP/<nom>/arbre ; imprime sa racine
  local a="$TMP/$1/arbre" m
  shift
  mkdir -p "$a/core-scripts" "$a/.agents/security" "$a/.agents/bin"
  cp "$SCRIPT" "$a/core-scripts/setup.sh"
  cp "$DOC" "$a/core-scripts/doctor.sh"
  cp "$ROOT/.agents/security/module_discovery.py" "$a/.agents/security/module_discovery.py"
  # Le pilote de fusion (étape 6 de setup.sh) est lu dans l'arbre copié : sans
  # lui, son --verifier échouerait sur un fichier absent, pas sur un pilote absent.
  cp "$ROOT/.agents/bin/fusion_enregistrement.py" "$a/.agents/bin/fusion_enregistrement.py"
  for m in "$@"; do
    printf '{}\n' > "$a/$m"
  done
  printf '%s' "$a"
}
hk_lance() { # hk_lance <arbre> <os> <bin> [args…] : setup.sh de l'arbre, son doctor, sonde bin + venv ; code dans RC
  local a="$1" os="$2" bin="$3"
  shift 3
  env -u CLAUDECODE "SETUP_OS=$os" "SETUP_PROBE_PATH=$bin:$VENV_HK" "SETUP_DOCTOR=$a/core-scripts/doctor.sh" \
    "$BASHX" "$a/core-scripts/setup.sh" --inventory "$INV" "$@" > "$OUT" 2> "$ERR" < /dev/null
  RC=$?
}
# Les jetons B sans la ligne python3 ni pytest (le venv les sert, sans pytest).
B_HK_DARWIN="$(printf '%s\n' "$B_DARWIN" | sed 's/ python3|python|py//; s/ pytest//')"
B_HK_LINUX="$(printf '%s\n' "$B_LINUX" | sed 's/ python3|python|py//; s/ pytest//')"
# Les jetons B requis hors du kit sans module python : tous, moins pytest.
REQ_HK_DARWIN="$(printf '%s\n' "$B_DARWIN" | sed 's/ pytest//')"
REQ_HK_LINUX="$(printf '%s\n' "$B_LINUX" | sed 's/ pytest//')"
SEMGREP_PIN="$(awk -F'\t' '/^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next } $c["tool"] == "semgrep" { print $c["ci_pin"]; exit }' "$INV")"
SEMGREP_VER="${SEMGREP_PIN%%@*}"
# La ligne que setup.sh dit dès qu'un pipx est planifié (SP_PIPX_CHEMIN).
PIPX_CHEMIN_MOTIF='^setup: pipx pose ses commandes sous ~/.local/bin : .*pipx ensurepath'

cas_19() {
  local a b
  hk_venv || { ko "(19) hors du kit : aucun python >= 3.11 du poste ne crée de venv — le cas exige un interpréteur réel"; return; }
  a="$(hk_arbre c19)"
  b="$(poste c19 darwin "$B_HK_DARWIN")"
  hk_lance "$a" darwin "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(19) sans manifeste : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(19) sans manifeste : gestionnaire appelé en --dry-run"; return; }
  grep -q '^  hors classe B ici (doctor) : pytest$' "$OUT" || { ko "(19) sans manifeste : pytest n'est pas dit « hors classe B ici » — $(cat "$OUT")"; return; }
  grep -qxF "Requis (classe B de l inventaire, darwin) : $REQ_HK_DARWIN" "$OUT" \
    || { ko "(19) sans manifeste : pytest reste requis — $(grep '^Requis' "$OUT")"; return; }
  grep -q '^setup: --dry-run : lancerait : brew install -- gitleaks semgrep$' "$OUT" \
    || { ko "(19) sans manifeste : « lancerait : brew install -- gitleaks semgrep » absent — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$REQ_HK_DARWIN manque encore=gitleaks semgrep — exit 1" ] \
    || { ko "(19) sans manifeste : résumé « $(resume) »"; return; }
  ok "(19) hors du kit, sans manifeste : pytest hors classe B ici (ni requis ni manquant), lancerait brew install -- gitleaks semgrep, rc 1"

  printf '[project]\nname = "t19"\n' > "$a/pyproject.toml"
  hk_lance "$a" darwin "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(19) pyproject.toml : rc $RC ≠ 1 — $(diag)"; return; }
  grep -q '^setup: --dry-run : lancerait : brew install -- gitleaks semgrep pip-audit$' "$OUT" \
    || { ko "(19) pyproject.toml : « lancerait : brew install -- gitleaks semgrep pip-audit » absent — $(cat "$OUT")"; return; }
  grep -qF 'setup: --dry-run : note pytest : la porte lance python3 -m pytest : python3 -m pip install --user pytest==' "$OUT" \
    || { ko "(19) pyproject.toml : la note pip de pytest est absente — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$REQ_HK_DARWIN manque encore=pytest gitleaks semgrep pip-audit — exit 1" ] \
    || { ko "(19) pyproject.toml : résumé « $(resume) »"; return; }
  ok "(19) hors du kit, pyproject.toml : pytest requis avec la note pip, pip-audit planifié avec gitleaks et semgrep, rc 1"
}

cas_20() {
  local a b l_jdk l_cmd
  hk_venv || { ko "(20) hors du kit : aucun python >= 3.11 du poste ne crée de venv"; return; }
  a="$(hk_arbre c20 package.json pom.xml main.tf)"
  printf '[project]\nname = "t20"\n' > "$a/pyproject.toml"
  b="$(poste c20 darwin "$B_HK_DARWIN")"
  hk_lance "$a" darwin "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(20) six scanners : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  grep -q '^Scanners de sécurité (hors du kit ; doctor: modules : npm,java,python,iac)$' "$OUT" \
    || { ko "(20) six scanners : familles du doctor — $(grep '^Scanners' "$OUT")"; return; }
  [ "$(grep -c '^setup: --dry-run : lancerait : brew install -- ' "$OUT")" -eq 1 ] \
    && grep -q '^setup: --dry-run : lancerait : brew install -- gitleaks semgrep pip-audit node dependency-check trivy$' "$OUT" \
    || { ko "(20) six scanners : UNE ligne « brew install -- gitleaks semgrep pip-audit node dependency-check trivy » attendue — $(grep 'lancerait' "$OUT")"; return; }
  l_jdk="$(grep -n '^setup: dependency-check : la formule brew tire un JDK' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_cmd="$(grep -n '^setup: --dry-run : lancerait : brew install' "$OUT" | sed -n 1p | cut -d: -f1)"
  [ -n "$l_jdk" ] && [ -n "$l_cmd" ] && [ "$l_jdk" -lt "$l_cmd" ] \
    || { ko "(20) six scanners : le JDK n'est pas annoncé AVANT la commande brew (lignes « $l_jdk » / « $l_cmd »)"; return; }
  grep -q '^setup: semgrep : brew pose la version de homebrew/core' "$OUT" || { ko "(20) six scanners : l'écart de version de semgrep n'est pas dit"; return; }
  [ "$(grep -c "^SP_SCANNERS_DARWIN='gitleaks semgrep pip-audit node dependency-check trivy'$" "$SCRIPT")" -eq 1 ] \
    && [ "$(grep -c 'SP_SCANNERS_DARWIN=' "$SCRIPT")" -eq 1 ] \
    || { ko "(20) la ligne contrat SP_SCANNERS_DARWIN (C17) n'est pas unique, en colonne 0, entre apostrophes"; return; }
  ok "(20) hors du kit, quatre familles : UNE commande brew install -- gitleaks semgrep pip-audit node dependency-check trivy, JDK annoncé avant, table SP_SCANNERS_DARWIN unique"
}

cas_21() {
  local a b
  hk_venv || { ko "(21) hors du kit : aucun python >= 3.11 du poste ne crée de venv"; return; }
  a="$(hk_arbre c21)"
  b="$(poste c21 darwin "$B_HK_DARWIN" inerte)"
  hk_lance "$a" darwin "$b"
  [ "$RC" -eq 1 ] || { ko "(21) brew inerte : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "install -- gitleaks semgrep" ] || { ko "(21) brew inerte : journal « $(journal "$b") »"; return; }
  grep -q '^  manque encore      gitleaks$' "$OUT" && grep -q '^  manque encore      semgrep$' "$OUT" \
    || { ko "(21) brew inerte : les scanners non posés ne sont pas « manque encore » — $(cat "$OUT")"; return; }
  grep -q '^    doctor : ABSENT (optionnel) *gitleaks — ' "$OUT" || { ko "(21) brew inerte : ligne de classe A du doctor non relue — $(cat "$OUT")"; return; }
  grep -q '^    a taper : brew install -- gitleaks$' "$OUT" || { ko "(21) brew inerte : commande à taper absente — $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$REQ_HK_DARWIN manque encore=gitleaks semgrep — exit 1" ] \
    || { ko "(21) brew inerte : résumé « $(resume) »"; return; }
  ok "(21) brew qui ne pose rien : chaque scanner relu après, manque encore=gitleaks semgrep, commande à taper, rc 1"

  b="$(poste c21b darwin "$B_HK_DARWIN")"
  hk_lance "$a" darwin "$b"
  [ "$RC" -eq 0 ] || { ko "(21) brew qui pose : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(resume)" = "setup: installés=gitleaks semgrep déjà là=$REQ_HK_DARWIN manque encore=aucun — exit 0" ] \
    || { ko "(21) brew qui pose : résumé « $(resume) »"; return; }
  ok "(21) brew qui pose les scanners : installés=gitleaks semgrep, rc 0"
}

faux_pipx() { # faux_pipx <dir> : journalise `pipx …` dans <dir>/../journal et pose le bouchon de réserve sous le nom du paquet (avant ==)
  {
    printf '#!/bin/sh\n'
    printf 'JOURNAL=%s\n' "'$(dirname "$1")/journal'"
    printf 'DIR=%s\n' "'$1'"
    printf 'RESERVE=%s\n' "'$(dirname "$1")/reserve'"
    printf '%s\n' 'echo "pipx $*" >> "$JOURNAL"' 'n="${2%%==*}"' 'cp "$RESERVE/outil" "$DIR/$n"' 'exit 0'
  } > "$1/pipx"
  chmod +x "$1/pipx"
}

cas_22() {
  local a b l_pipx l_chemin
  hk_venv || { ko "(22) hors du kit : aucun python >= 3.11 du poste ne crée de venv"; return; }
  case "$SEMGREP_VER" in
    ""|[!0-9]*|*[!0-9.]*)
      ko "(22) la cellule ci_pin de semgrep de l'inventaire réel n'a pas de version lisible : « $SEMGREP_PIN »"
      return
      ;;
  esac
  a="$(hk_arbre c22 package.json main.tf)"
  printf '[project]\nname = "t22"\n' > "$a/pyproject.toml"
  b="$(poste c22 linux "$B_HK_LINUX")"
  faux_pipx "$b"
  hk_lance "$a" linux "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(22) Ubuntu --dry-run : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(22) Ubuntu --dry-run : pipx ou apt-get appelé — $(journal "$b")"; return; }
  grep -q "^setup: --dry-run : lancerait : pipx install semgrep==$SEMGREP_VER$" "$OUT" \
    && grep -q '^setup: --dry-run : lancerait : pipx install pip-audit$' "$OUT" \
    || { ko "(22) Ubuntu --dry-run : pipx semgrep==$SEMGREP_VER et pip-audit attendus — $(grep 'lancerait' "$OUT")"; return; }
  grep -q '^setup: --dry-run : lancerait : .*apt-get install -y -- python3-pytest npm$' "$OUT" \
    || { ko "(22) Ubuntu --dry-run : npm absent de la commande apt-get — $(grep 'lancerait' "$OUT")"; return; }
  grep -q '^setup: pipx install n est PAS épinglé par empreinte' "$OUT" || { ko "(22) Ubuntu --dry-run : l'absence d'empreinte de pipx n'est pas dite"; return; }
  grep -q '^setup: --dry-run : scanners a installer vous-meme : gitleaks trivy$' "$OUT" \
    || { ko "(22) Ubuntu --dry-run : gitleaks et trivy pas nommés à la main — $(cat "$OUT")"; return; }
  grep -q "$PIPX_CHEMIN_MOTIF" "$OUT" || { ko "(22) Ubuntu --dry-run : ~/.local/bin et pipx ensurepath ne sont pas dits — $(cat "$OUT")"; return; }
  ok "(22) Ubuntu --dry-run : pipx install semgrep==$SEMGREP_VER et pip-audit, npm par apt-get, non-épinglage dit, ~/.local/bin et pipx ensurepath dits, gitleaks et trivy à la main"

  : > "$(dirname "$b")/journal"
  hk_lance "$a" linux "$b"
  grep -qx "pipx install semgrep==$SEMGREP_VER" "$(dirname "$b")/journal" && grep -qx 'pipx install pip-audit' "$(dirname "$b")/journal" \
    || { ko "(22) Ubuntu, installation : pipx non journalisé — $(journal "$b")"; return; }
  grep -q 'install -y -- python3-pytest npm$' "$(dirname "$b")/journal" || { ko "(22) Ubuntu, installation : apt-get sans npm — $(journal "$b")"; return; }
  l_pipx="$(grep -n '^setup: lance : pipx install pip-audit$' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_chemin="$(grep -n "$PIPX_CHEMIN_MOTIF" "$OUT" | sed -n 1p | cut -d: -f1)"
  [ -n "$l_pipx" ] && [ -n "$l_chemin" ] && [ "$l_pipx" -lt "$l_chemin" ] \
    || { ko "(22) Ubuntu, installation : ~/.local/bin et pipx ensurepath ne sont pas dits après la boucle pipx (lignes « $l_pipx » / « $l_chemin »)"; return; }
  # python3-pytest posé par apt ne sert pas le python de la sonde (le venv) :
  # pytest manque encore, c'est la règle de la porte (en-tête de setup.sh).
  [ "$RC" -eq 1 ] && [ "$(resume)" = "setup: installés=semgrep pip-audit npm déjà là=$REQ_HK_LINUX manque encore=pytest gitleaks trivy — exit 1" ] \
    || { ko "(22) Ubuntu, installation : rc $RC, résumé « $(resume) »"; return; }
  ok "(22) Ubuntu, installation : apt-get … npm, pipx install semgrep==$SEMGREP_VER puis pip-audit, relus présents ; gitleaks et trivy manquent encore, rc 1"

  awk -F'\t' -v OFS='\t' '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next } $c["tool"] == "semgrep" { $c["ci_pin"] = "-x1@pip-hash(adoptant)" } { print }' "$INV" > "$TMP/c22-pin.tsv"
  rm -f "$(dirname "$b")/journal" "$b/semgrep" "$b/pip-audit" "$b/npm" "$b/pytest"
  hk_lance "$a" linux "$b" --dry-run --inventory "$TMP/c22-pin.tsv"
  grep -q 'ci_pin de semgrep REFUSÉ' "$ERR" && grep -qF -- '-x1@pip-hash(adoptant)' "$ERR" \
    || { ko "(22) ci_pin « -x1@… » : refus absent de stderr — $(diag)"; return; }
  if grep -q 'pipx install semgrep' "$OUT"; then
    ko "(22) ci_pin « -x1@… » : une commande pipx semgrep est annoncée — $(grep 'pipx install semgrep' "$OUT")"
    return
  fi
  grep -q '^setup: --dry-run : scanners a installer vous-meme : gitleaks semgrep trivy$' "$OUT" \
    || { ko "(22) ci_pin « -x1@… » : semgrep pas nommé à la main — $(cat "$OUT")"; return; }
  ok "(22) ci_pin « -x1@pip-hash(adoptant) » : version REFUSÉE sur stderr, rien passé à pipx, semgrep à installer soi-même"
}

cas_23() {
  local a b l_jdk l_nvd l_cmd
  hk_venv || { ko "(23) hors du kit : aucun python >= 3.11 du poste ne crée de venv"; return; }
  a="$(hk_arbre c23 Package.swift)"
  b="$(poste c23 darwin "$B_HK_DARWIN")"
  hk_lance "$a" darwin "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(23) swift seul : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(23) swift seul : gestionnaire appelé en --dry-run"; return; }
  grep -q '^Scanners de sécurité (hors du kit ; doctor: modules : swift)$' "$OUT" \
    || { ko "(23) swift seul : familles du doctor — $(grep '^Scanners' "$OUT")"; return; }
  [ "$(grep -c '^setup: --dry-run : lancerait : brew install -- ' "$OUT")" -eq 1 ] \
    && grep -q '^setup: --dry-run : lancerait : brew install -- gitleaks semgrep dependency-check$' "$OUT" \
    || { ko "(23) swift seul : UNE ligne « brew install -- gitleaks semgrep dependency-check » attendue — $(grep 'lancerait' "$OUT")"; return; }
  l_jdk="$(grep -n '^setup: dependency-check : la formule brew tire un JDK' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_nvd="$(grep -n '^setup: dependency-check : sans NVD_API_KEY ni base NVD, son premier scan reste dégradé' "$OUT" | sed -n 1p | cut -d: -f1)"
  l_cmd="$(grep -n '^setup: --dry-run : lancerait : brew install' "$OUT" | sed -n 1p | cut -d: -f1)"
  [ -n "$l_jdk" ] && [ -n "$l_cmd" ] && [ "$l_jdk" -lt "$l_cmd" ] \
    || { ko "(23) swift seul : le JDK n'est pas annoncé AVANT la commande brew (lignes « $l_jdk » / « $l_cmd »)"; return; }
  [ -n "$l_nvd" ] && [ "$l_nvd" -lt "$l_cmd" ] \
    || { ko "(23) swift seul : la ligne NVD_API_KEY n'est pas dite avant la commande (lignes « $l_nvd » / « $l_cmd »)"; return; }
  [ "$(resume)" = "setup: installés=aucun déjà là=$REQ_HK_DARWIN manque encore=gitleaks semgrep dependency-check — exit 1" ] \
    || { ko "(23) swift seul : résumé « $(resume) »"; return; }
  ok "(23) hors du kit, Package.swift seul : modules : swift, lancerait brew install -- gitleaks semgrep dependency-check, JDK et NVD_API_KEY dits avant, rc 1"
}

cas_24() {
  local a b
  hk_venv || { ko "(24) hors du kit : aucun python >= 3.11 du poste ne crée de venv"; return; }
  a="$(hk_arbre c24)"
  printf '[project]\nname = "t24"\n' > "$a/pyproject.toml"
  b="$(poste c24 linux "$B_HK_LINUX")"
  [ ! -e "$b/pipx" ] || { ko "(24) le poste-bouchon porte un pipx — le cas serait vacant"; return; }
  hk_lance "$a" linux "$b" --dry-run
  [ "$RC" -eq 1 ] || { ko "(24) Ubuntu sans pipx : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(24) Ubuntu sans pipx : gestionnaire appelé en --dry-run — $(journal "$b")"; return; }
  grep -q '^setup: pipx introuvable : semgrep et pip-audit sont à installer vous-même' "$OUT" \
    || { ko "(24) Ubuntu sans pipx : « pipx introuvable » absent — $(cat "$OUT")"; return; }
  if [ "$(grep 'lancerait' "$OUT" | grep -c 'pipx')" -ne 0 ]; then
    ko "(24) Ubuntu sans pipx : une commande pipx est annoncée — $(grep 'lancerait' "$OUT")"
    return
  fi
  if grep -q "$PIPX_CHEMIN_MOTIF" "$OUT"; then
    ko "(24) Ubuntu sans pipx : ~/.local/bin et pipx ensurepath dits alors qu'aucun pipx n'est planifié"
    return
  fi
  grep -q '^setup: --dry-run : scanners a installer vous-meme : gitleaks semgrep pip-audit$' "$OUT" \
    || { ko "(24) Ubuntu sans pipx : semgrep et pip-audit pas nommés à la main — $(cat "$OUT")"; return; }
  ok "(24) Ubuntu sans pipx : « pipx introuvable » dit, aucune commande pipx, semgrep et pip-audit à la main, rc 1"
}

if [ "${SETUP_TEST_ONLY:-}" != pilote ] && [ "${SETUP_TEST_ONLY:-}" != pilote_ps1 ] && [ "${SETUP_TEST_ONLY:-}" != hookspath ] && [ "${SETUP_TEST_ONLY:-}" != hookspath_ps1 ]; then
  cas_1; cas_2_3; cas_4; cas_5; cas_6; cas_7; cas_8; cas_9; cas_10; cas_10r; cas_11; cas_12; cas_13; cas_15; cas_16; cas_17
  cas_19; cas_20; cas_21; cas_22; cas_23; cas_24
fi

# ::hookspath — dépôt jetable, setup lancé depuis un cwd extérieur.
hook_prepare() {
  HOOKS_DEPOT="$TMP/hooks/depot"
  HOOKS_BIN="$TMP/hooks/bin"
  HOOKS_INV="$TMP/hooks/inventory.tsv"
  HOOKS_SCRIPT="$HOOKS_DEPOT/core-scripts/setup.sh"
  HOOKS_PS1="$HOOKS_DEPOT/core-scripts/setup.ps1"
  HOOKS_QUESTION='Activer les hooks de ce dépôt (tous ses worktrees liés partagent ce réglage) dans .githooks ? core.hooksPath remplace les hooks de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; commit-msg refuse certains sujets ; Git exécute les hooks de l’arbre courant. [o/N]'
  mkdir -p "$HOOKS_DEPOT/core-scripts" "$HOOKS_DEPOT/.githooks" "$HOOKS_DEPOT/.agents/bin" "$TMP/hooks/outside" "$TMP/hooks/home" "$HOOKS_BIN"
  awk -F '\t' '/^tool\t/ || /^git\t/' "$INV" > "$HOOKS_INV"
  cp "$SCRIPT" "$HOOKS_SCRIPT"
  cp "$PS1_SCRIPT" "$HOOKS_PS1"
  cp "$ROOT/.agents/bin/fusion_enregistrement.py" "$HOOKS_DEPOT/.agents/bin/fusion_enregistrement.py"
  git -C "$HOOKS_DEPOT" init -q
  HOOKS_REAL_GIT="$(command -v git)"
  printf '%s\n' '#!/bin/sh' 'if [ "${HOOKS_GIT_ERROR:-}" = 1 ]; then' '  case " $* " in' '    *" config --get core.hooksPath "*) exit 2 ;;' '  esac' 'fi' 'exec "$HOOKS_REAL_GIT" "$@"' > "$HOOKS_BIN/git"
  chmod +x "$HOOKS_BIN/git"
  faux_gestionnaire "$HOOKS_BIN" brew
  printf '%s\n' '#!/bin/sh' 'exit 0' > "$HOOKS_BIN/winget"
  printf '%s\n' '#!/bin/sh' 'if [ "$1" = "-c" ]; then exit 1; fi' 'echo Python 3.9.6' > "$HOOKS_BIN/python3"
  chmod +x "$HOOKS_BIN/winget" "$HOOKS_BIN/python3"
}
hook_reset() {
  git -C "$HOOKS_DEPOT" config --local --unset-all core.hooksPath 2>/dev/null || true
  rm -f "$HOOKS_DEPOT/.git/hooks/pre-push" "$HOOKS_DEPOT/.git/hooks/pre-commit"
}
hook_lance() { # bash|ps1, réponse, scénario ; code dans RC, sorties dans OUT/ERR
  env -u CLAUDECODE HOOKS_DEPOT="$HOOKS_DEPOT" HOOKS_BIN="$HOOKS_BIN" \
    HOOKS_INV="$HOOKS_INV" HOOKS_SCRIPT="$HOOKS_SCRIPT" HOOKS_PS1="$HOOKS_PS1" \
    HOOKS_DOC="$DOC" HOOKS_OUT="$OUT" HOOKS_ERR="$ERR" HOOKS_PWSH="${PWSH:-}" \
    HOOKS_HOME="$TMP/hooks/home" HOOKS_CWD="$TMP/hooks/outside" HOOKS_REAL_GIT="$HOOKS_REAL_GIT" \
    HOOKS_BASH="${HOOKS_BASH:-bash}" \
    python3 -c '
import os, pty, subprocess, sys
mode, answer, scenario = sys.argv[1:]
env = os.environ.copy()
env.update(HOME=env["HOOKS_HOME"], GIT_CONFIG_GLOBAL=env["HOOKS_HOME"] + "/global",
           GIT_CONFIG_NOSYSTEM="1")
if mode == "bash":
    env.update(SETUP_OS="darwin", SETUP_PROBE_PATH=env["HOOKS_BIN"],
               SETUP_DOCTOR=env["HOOKS_DOC"], PATH=env["HOOKS_BIN"] + os.pathsep + env["PATH"])
    args = [env["HOOKS_BASH"], env["HOOKS_SCRIPT"], "--inventory", env["HOOKS_INV"]]
    if scenario == "dry-run": args.append("--dry-run")
else:
    env.update(SETUP_PS1_OS="windows", PATH=env["HOOKS_BIN"])
    args = [env["HOOKS_PWSH"], "-NoProfile", "-File", env["HOOKS_PS1"],
            "-Inventory", env["HOOKS_INV"]]
    if scenario == "dry-run": args.append("-DryRun")
if scenario == "claudecode": env["CLAUDECODE"] = "1"
if scenario == "git-error": env["HOOKS_GIT_ERROR"] = "1"
master, slave = pty.openpty()
stdin = subprocess.DEVNULL if answer == "non-tty" else slave
proc = subprocess.Popen(args, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=env, cwd=env["HOOKS_CWD"])
os.close(slave)
if answer not in ("non-tty", "eof"):
    os.write(master, (("\n" if answer == "vide" else answer + "\n") + "Non\n").encode())
elif answer == "eof":
    os.write(master, b"\x04")
out, err = proc.communicate(timeout=60)
os.close(master)
open(env["HOOKS_OUT"], "wb").write(out)
open(env["HOOKS_ERR"], "wb").write(err)
sys.exit(proc.returncode)
  ' "$1" "$2" "$3"
  RC=$?
}
hook_valeur_absente() {
  if git -C "$HOOKS_DEPOT" config --local --get core.hooksPath > /dev/null; then
    ko "::hookspath $1 : core.hooksPath écrit malgré le refus"
    return 1
  fi
}
hook_pas_question() {
  if grep -Fq 'Activer les hooks de ce' "$OUT" "$ERR"; then
    ko "::hookspath $1 : question interdite — $(cat "$OUT" "$ERR")"
    return 1
  fi
}
cas_hookspath() { # mode bash|ps1, mêmes contrôles et réponses
  local mode="$1" cas attendu
  ln -sf "$(command -v python3)" "$HOOKS_BIN/python3"
  for cas in pre-push pre-commit; do
    hook_reset
    if [ "$cas" = pre-commit ]; then
      printf '%s\n' 'hook existant' > "$TMP/hooks/cible"
      ln -s "$TMP/hooks/cible" "$HOOKS_DEPOT/.git/hooks/$cas"
    else
      printf '%s\n' 'hook existant' > "$HOOKS_DEPOT/.git/hooks/$cas"
    fi
    hook_lance "$mode" Non normal
    [ "$RC" -eq 0 ] || { ko "::hookspath $mode $cas : rc $RC — $(cat "$OUT" "$ERR")"; return; }
    grep -Fq 'pilote de fusion refu' "$OUT" || { ko "::hookspath $mode $cas : pilote non atteint, conseil non éprouvé"; return; }
    grep -Fq "$cas" "$OUT" || { ko "::hookspath $mode $cas : hook actif non nommé"; return; }
    grep -Fq 'chaîn' "$OUT" || grep -Fq 'chain' "$OUT" || { ko "::hookspath $mode $cas : chaînage absent"; return; }
    if grep -Fq 'git config core.hooksPath .githooks' "$OUT" "$ERR"; then ko "::hookspath $mode $cas : conseil de contournement dans la sortie entière"; return; fi
    grep -Fq 'sans copier par-dessus' "$OUT" || { ko "::hookspath $mode $cas : interdiction d'écraser le hook absente"; return; }
    if grep -Fq 'cp .githooks/pre-push' "$OUT" "$ERR"; then ko "::hookspath $mode $cas : copie par-dessus conseillée"; return; fi
    hook_pas_question "$mode $cas" || return
    hook_valeur_absente "$mode $cas" || return
    [ "$(cat "$HOOKS_DEPOT/.git/hooks/$cas")" = 'hook existant' ] || { ko "::hookspath $mode $cas : hook modifié"; return; }
    ok "::hookspath $mode $cas : nom conservé, aucune question/écriture, chaînage sans contournement"
  done
  hook_reset
  local controle
  controle="$(printf '\033')"
  printf '%s\n' 'hook existant' > "$HOOKS_DEPOT/.git/hooks/pre-${controle}push"
  hook_lance "$mode" Non normal
  if grep -Fq "$controle" "$OUT" "$ERR"; then ko "::hookspath $mode : contrôle du nom de hook imprimé"; return; fi
  rm "$HOOKS_DEPOT/.git/hooks/pre-${controle}push"
  hook_reset
  git -C "$HOOKS_DEPOT" config --local core.hooksPath "autre-${controle}dossier"
  hook_lance "$mode" Non normal
  if grep -Fq "$controle" "$OUT" "$ERR"; then ko "::hookspath $mode : contrôle de core.hooksPath imprimé"; return; fi
  ok "::hookspath $mode : noms de hooks et valeur Git sans caractères de contrôle"
  rm "$HOOKS_BIN/python3"
  printf '%s\n' '#!/bin/sh' 'if [ "$1" = "-c" ]; then exit 1; fi' 'echo Python 3.9.6' > "$HOOKS_BIN/python3"
  chmod +x "$HOOKS_BIN/python3"
  hook_reset
  for cas in vide eof Non Oui OUI ' o ' ok ouii; do
    hook_lance "$mode" "$cas" normal
    [ "$RC" -eq 0 ] || { ko "::hookspath $mode $cas : rc $RC — $(cat "$OUT" "$ERR")"; return; }
    grep -Fq "$HOOKS_QUESTION" "$OUT" || { ko "::hookspath $mode $cas : question commune absente ou différente"; return; }
    hook_valeur_absente "$mode $cas" || return
    grep -Fq 'Hooks non activés dans ce clone ; configuration inchangée.' "$OUT" || { ko "::hookspath $mode $cas : réponse figée absente"; return; }
    ok "::hookspath $mode $cas : Non par défaut, valeur locale absente"
  done
  for cas in o oui; do
    hook_reset
    hook_lance "$mode" "$cas" normal
    [ "$RC" -eq 0 ] || { ko "::hookspath $mode $cas : rc $RC — $(cat "$OUT" "$ERR")"; return; }
    attendu="$(git -C "$HOOKS_DEPOT" config --local --get core.hooksPath)"
    [ "$attendu" = .githooks ] || { ko "::hookspath $mode $cas : valeur locale $attendu"; return; }
    grep -Fq 'Hooks activés dans ce dépôt (worktrees liés compris) : core.hooksPath=.githooks.' "$OUT" || { ko "::hookspath $mode $cas : succès figé absent"; return; }
    if grep -Fq 'sans core.hooksPath' "$OUT" "$ERR"; then ko "::hookspath $mode $cas : avertissement sans hooks après activation"; return; fi
    hook_lance "$mode" non-tty normal
    grep -Fq 'Hooks déjà activés dans ce clone ; configuration inchangée.' "$OUT" || { ko "::hookspath $mode $cas : rejeu non idempotent"; return; }
    git -C "$HOOKS_DEPOT" config --local core.hooksPath .githooks/
    hook_lance "$mode" non-tty normal
    grep -Fq 'Hooks déjà activés dans ce clone ; configuration inchangée.' "$OUT" || { ko "::hookspath $mode $cas : séparateur final mal classé"; return; }
    hook_pas_question "$mode $cas rejeu" || return
    ok "::hookspath $mode $cas : valeur locale exacte, rejeu sans question"
  done
  hook_reset
  git -C "$HOOKS_DEPOT" config --local core.hooksPath autre-dossier
  hook_lance "$mode" o normal
  [ "$(git -C "$HOOKS_DEPOT" config --local --get core.hooksPath)" = autre-dossier ] || { ko "::hookspath $mode conflit : valeur écrasée"; return; }
  grep -Fq 'autre-dossier' "$OUT" || { ko "::hookspath $mode conflit : valeur étrangère non nommée"; return; }
  if grep -Fq 'git config core.hooksPath .githooks' "$OUT" "$ERR"; then ko "::hookspath $mode conflit : activation proposée"; return; fi
  hook_pas_question "$mode conflit" || return
  ok "::hookspath $mode conflit : valeur étrangère conservée sans question"
  hook_reset
  hook_lance "$mode" o git-error
  grep -Fq 'core.hooksPath' "$OUT" || { ko "::hookspath $mode git-error : diagnostic absent — $(cat "$OUT" "$ERR")"; return; }
  if grep -Fq 'git config core.hooksPath .githooks' "$OUT" "$ERR"; then ko "::hookspath $mode git-error : activation proposée"; return; fi
  hook_valeur_absente "$mode git-error" || return
  hook_pas_question "$mode git-error" || return
  ok "::hookspath $mode git-error : échec Git nommé, aucune question/écriture"
  mv "$HOOKS_DEPOT/.githooks" "$TMP/hooks/sans-githooks"
  hook_lance "$mode" o normal
  grep -Fq '.githooks/ absent : hooks non proposés ; configuration inchangée.' "$OUT" || { ko "::hookspath $mode absent : diagnostic absent"; return; }
  hook_valeur_absente "$mode absent" || return
  hook_pas_question "$mode absent" || return
  mv "$TMP/hooks/sans-githooks" "$HOOKS_DEPOT/.githooks"
  ok "::hookspath $mode absent : .githooks absent, aucune question/écriture"
  mv "$HOOKS_DEPOT/.githooks" "$TMP/hooks/sans-githooks"
  ln -s "$TMP/hooks/outside" "$HOOKS_DEPOT/.githooks"
  hook_lance "$mode" o normal
  grep -Fq '.githooks/ hors de cette racine' "$OUT" || { ko "::hookspath $mode lien externe : diagnostic absent"; return; }
  hook_valeur_absente "$mode lien externe" || return
  hook_pas_question "$mode lien externe" || return
  rm "$HOOKS_DEPOT/.githooks"
  mv "$TMP/hooks/sans-githooks" "$HOOKS_DEPOT/.githooks"
  ok "::hookspath $mode lien externe : aucune question/écriture"
  mv "$HOOKS_DEPOT/.githooks" "$TMP/hooks/sans-githooks"
  mkdir -p "$TMP/hooks/outside/hooks"
  ln -s "$TMP/hooks/outside" "$HOOKS_DEPOT/dedans"
  ln -s "$HOOKS_DEPOT/dedans/hooks" "$HOOKS_DEPOT/.githooks"
  hook_lance "$mode" o normal
  grep -Fq '.githooks/ cible avec lien imbriqué' "$OUT" || grep -Fq '.githooks/ hors de cette racine' "$OUT" || { ko "::hookspath $mode lien imbriqué : diagnostic absent"; return; }
  hook_valeur_absente "$mode lien imbriqué" || return
  hook_pas_question "$mode lien imbriqué" || return
  rm "$HOOKS_DEPOT/.githooks" "$HOOKS_DEPOT/dedans"
  mv "$TMP/hooks/sans-githooks" "$HOOKS_DEPOT/.githooks"
  ok "::hookspath $mode lien imbriqué : aucune question/écriture"
  mv "$HOOKS_DEPOT/.git/hooks" "$TMP/hooks/sans-hooks"
  hook_lance "$mode" o normal
  grep -Fq 'inventaire des hooks impossible' "$OUT" || { ko "::hookspath $mode inventaire : diagnostic absent"; return; }
  hook_valeur_absente "$mode inventaire" || return
  hook_pas_question "$mode inventaire" || return
  mv "$TMP/hooks/sans-hooks" "$HOOKS_DEPOT/.git/hooks"
  ok "::hookspath $mode inventaire : échec nommé, aucune question/écriture"
  for cas in non-tty dry-run; do
    if [ "$cas" = non-tty ]; then
      hook_lance "$mode" non-tty "$cas"
    else
      hook_lance "$mode" o "$cas"
    fi
    hook_valeur_absente "$mode $cas" || return
    hook_pas_question "$mode $cas" || return
    ok "::hookspath $mode $cas : aucune question/écriture"
  done
  hook_lance "$mode" o claudecode
  hook_valeur_absente "$mode claudecode" || return
  hook_pas_question "$mode claudecode" || return
  ok "::hookspath $mode CLAUDECODE : aucune question/écriture"
  local original="$HOOKS_SCRIPT" outer="$TMP/hooks/outer"
  if [ "$mode" = ps1 ]; then original="$HOOKS_PS1"; fi
  mkdir -p "$outer/adoptant/core-scripts" "$outer/adoptant/.githooks"
  git -C "$outer" init -q
  cp "$original" "$outer/adoptant/core-scripts/$(basename "$original")"
  HOOKS_SCRIPT="$outer/adoptant/core-scripts/setup.sh"
  HOOKS_PS1="$outer/adoptant/core-scripts/setup.ps1"
  hook_lance "$mode" o normal
  grep -Fq 'racine Git diff' "$OUT" || { ko "::hookspath $mode toplevel : diagnostic absent — $(cat "$OUT" "$ERR")"; return; }
  hook_pas_question "$mode toplevel" || return
  hook_valeur_absente "$mode toplevel" || return
  if git -C "$outer" config --local --get core.hooksPath > /dev/null; then ko "::hookspath $mode toplevel : configuration du dépôt parent modifiée"; return; fi
  HOOKS_SCRIPT="$HOOKS_DEPOT/core-scripts/setup.sh"
  HOOKS_PS1="$HOOKS_DEPOT/core-scripts/setup.ps1"
  ok "::hookspath $mode toplevel : racine distincte, aucune question/écriture"
}

if [ "${SETUP_TEST_ONLY:-}" = hookspath ] || [ "${SETUP_TEST_ONLY:-}" = hookspath_ps1 ] || [ -z "${SETUP_TEST_ONLY:-}" ]; then
  hook_prepare
  if [ "${SETUP_TEST_ONLY:-}" != hookspath_ps1 ]; then
    cas_hookspath bash
    if [ "$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}')" = 3 ]; then
      HOOKS_BASH=/bin/bash cas_hookspath bash
    else
      echo 'SKIP: ::hookspath bash 3.x — /bin/bash n’est pas en version 3.x'
    fi
  fi
  if [ "${SETUP_TEST_ONLY:-}" != hookspath ]; then
    PWSH="$(command -v pwsh 2>/dev/null || true)"
    if [ -n "$PWSH" ]; then cas_hookspath ps1; else echo 'SKIP: ::hookspath ps1 — pwsh absent'; fi
  fi
fi
if [ "${SETUP_TEST_ONLY:-}" = hookspath ] || [ "${SETUP_TEST_ONLY:-}" = hookspath_ps1 ]; then
  bilan
  exit $?
fi

# ::pilote — un clone jetable avec origin nu ; le setup et le pilote sont des
# copies. Le code de retour et la configuration du kit sont relevés séparément.
cas_pilote() {
  local depot="$TMP/pilote/depot" origine="$TMP/pilote/origin.git" bin py cas mode attendu
  mkdir -p "$TMP/pilote/home" "$depot/core-scripts" "$depot/.agents/bin" "$depot/.githooks"
  PILOTE_HOME="$TMP/pilote/home"
  PILOTE_GLOBAL="$TMP/pilote/global"
  PILOTE_DEPOT="$depot"
  PILOTE_INV="$TMP/pilote/inventory.tsv"
  PILOTE_SCRIPT="$depot/core-scripts/setup.sh"
  git -C "$ROOT" config --local --list > "$TMP/pilote/kit-avant"
  awk -F '\t' '/^tool\t/ || /^git\t/' "$INV" > "$PILOTE_INV"
  cp "$SCRIPT" "$PILOTE_SCRIPT"
  cp "$PS1_SCRIPT" "$depot/core-scripts/setup.ps1"
  cp "$ROOT/.agents/bin/fusion_enregistrement.py" "$depot/.agents/bin/fusion_enregistrement.py"
  pilote_git init -q --bare "$origine"
  pilote_git -C "$depot" init -q -b develop
  pilote_git -C "$depot" config --local user.email pilote@example.invalid
  pilote_git -C "$depot" config --local user.name pilote
  pilote_git -C "$depot" remote add origin "$origine"
  pilote_git -C "$depot" add .agents/bin/fusion_enregistrement.py core-scripts/setup.sh
  pilote_git -C "$depot" commit -q -m 'test: fixture pilote'
  pilote_git -C "$depot" push -q -u origin develop
  pilote_git -C "$depot" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop
  bin="$(poste pilote darwin git)"
  py="$(command -v python3)"
  PILOTE_PY="$py"
  if ! "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    ko '::pilote : Python >= 3.11 absent du poste de test'
    return
  fi
  ln -sf "$py" "$bin/python3"
  PILOTE_BIN="$bin"

  for cas in o oui Non Oui O vide eof non-tty dry-run; do
    pilote_desarme
    mode="$cas"
    if [ "$cas" = dry-run ]; then mode=vide; fi
    pilote_lance "$mode" "$bin" "$cas"
    attendu=0
    [ "$RC" -eq "$attendu" ] || { ko "::pilote $cas : rc $RC, attendu $attendu — $(cat "$ERR")"; return; }
    if [ "$cas" = o ] || [ "$cas" = oui ]; then
      pilote_git -C "$depot" config --local --get merge.cadre-enregistrement.driver > /dev/null || { ko '::pilote o : driver absent'; return; }
      pilote_git -C "$depot" config --local --get merge.cadre-enregistrement.driver | grep -Fq "$depot/.git/cadre/" || { ko "::pilote $cas : driver ne vise pas la copie du dépôt"; return; }
      grep -q 'pilote de fusion vérifié' "$OUT" || { ko '::pilote o : vérification finale absente'; return; }
    else
      if pilote_git -C "$depot" config --local --get merge.cadre-enregistrement.driver > /dev/null; then
        ko "::pilote $cas : driver armé malgré le refus"
        return
      fi
      if [ "$cas" = Non ] || [ "$cas" = Oui ] || [ "$cas" = O ] || [ "$cas" = vide ] || [ "$cas" = eof ] || [ "$cas" = non-tty ]; then
        grep -q 'sans core.hooksPath → .githooks' "$OUT" || { ko "::pilote $cas : borne C42 absente"; return; }
        grep -Fq 'git config core.hooksPath .githooks' "$OUT" || { ko "::pilote $cas : commande d'armement absente"; return; }
        if grep -Eq 'T-0[0-9A-Z]{4}' "$OUT"; then ko "::pilote $cas : identifiant de tâche du kit affiché"; return; fi
      fi
    fi
    if [ "$cas" = dry-run ] || [ "$cas" = non-tty ]; then
      if grep -q 'Installer le pilote de fusion' "$OUT"; then ko "::pilote $cas : question interdite"; return; fi
    else
      grep -q 'Installer le pilote de fusion' "$OUT" || { ko "::pilote $cas : question absente"; return; }
    fi
    ok "::pilote $cas : rc $RC, question et armement conformes"
  done
  pilote_desarme
  PILOTE_HOOKS_RESPONSE=o pilote_lance Non "$bin" Non
  [ "$RC" -eq 0 ] && [ "$(pilote_git -C "$depot" config --local --get core.hooksPath)" = .githooks ] || { ko '::pilote hooks o : activation absente'; return; }
  if grep -Fq 'sans core.hooksPath' "$OUT" "$ERR"; then ko '::pilote hooks o : conseil devenu faux après activation'; return; fi
  pilote_git -C "$depot" config --local --unset core.hooksPath
  ok '::pilote hooks o puis pilote Non : aucun conseil sans hooks après activation'
  for cas in claudecode-vide claudecode-blanc; do
    pilote_desarme
    pilote_lance vide "$bin" "$cas"
    [ "$RC" -eq 0 ] && grep -q 'Installer le pilote de fusion' "$OUT" || { ko "::pilote $cas : question absente — $(cat "$OUT" "$ERR")"; return; }
    if grep -q 'non proposé sous CLAUDECODE' "$OUT"; then ko "::pilote $cas : CLAUDECODE blanc lu comme posé"; return; fi
    ok "::pilote $cas : CLAUDECODE fait de blancs vaut absent, la question est posée"
  done

  pilote_desarme
  : > "$depot/.agents/IS_THE_KIT"
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && grep -q 'depuis=origin/develop' "$OUT" || { ko "::pilote kit : --depuis origin/develop absent — $(cat "$OUT" "$ERR")"; return; }
  ok '::pilote kit develop : --depuis origin/develop transmis'
  pilote_desarme
  rm "$depot/.agents/IS_THE_KIT"
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && grep -q 'pilote de fusion vérifié' "$OUT" && ! grep -q 'depuis=origin/develop' "$OUT" || { ko "::pilote adoptant : --depuis transmis ou installation absente — $(cat "$OUT" "$ERR")"; return; }
  ok '::pilote sans IS_THE_KIT : --depuis absent'

  pilote_desarme
  : > "$depot/.agents/IS_THE_KIT"
  pilote_git -C "$depot" update-ref -d refs/remotes/origin/develop
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && ! grep -q 'depuis=origin/develop' "$OUT" || { ko '::pilote sans origin/develop : --depuis transmis'; return; }
  ok '::pilote kit sans ref origin/develop : --depuis absent'
  pilote_git -C "$depot" fetch -q origin develop:refs/remotes/origin/develop
  pilote_git -C "$depot" switch -q -c feature
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && ! grep -q 'depuis=origin/develop' "$OUT" || { ko '::pilote branche feature : --depuis transmis'; return; }
  ok '::pilote kit hors develop : --depuis absent'
  pilote_git -C "$depot" switch -q develop
  rm "$depot/.agents/IS_THE_KIT"

  pilote_desarme
  rm "$bin/python3"
  printf '%s\n' '#!/bin/sh' 'if [ "$1" = "-c" ]; then exit 1; fi' 'if [ "$4" = "--verifier" ]; then exit 1; fi' 'echo Python 3.9.6' > "$bin/python3"
  chmod +x "$bin/python3"
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] || { ko "::pilote Python 3.9 : rc $RC"; return; }
  grep -q 'pilote non proposé : python ≥ 3.11 absent' "$OUT" || { ko '::pilote Python 3.9 : refus absent'; return; }
  if grep -q 'Installer le pilote de fusion' "$OUT"; then ko '::pilote Python 3.9 : question posée'; return; fi
  ok '::pilote Python 3.9 : aucune question ni armement'
  printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$*" >> "$PILOTE_LOG"' 'exec "$PILOTE_REAL_PY" "$@"' > "$bin/python"
  chmod +x "$bin/python"
  : > "$TMP/pilote/python-journal"
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && grep -q -- '--installer' "$TMP/pilote/python-journal" || { ko "::pilote repli Python : interpréteur python non choisi — $(cat "$OUT" "$ERR")"; return; }
  ok '::pilote python3 3.9 puis python 3.14 : premier interpréteur admissible choisi'
  pilote_desarme
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] || { ko "::pilote K : setup de la copie rc $RC"; return; }
  git -C "$ROOT" config --local --list > "$TMP/pilote/kit-apres"
  cmp -s "$TMP/pilote/kit-avant" "$TMP/pilote/kit-apres" || { ko '::pilote K : configuration locale du kit modifiée'; return; }
  ok '::pilote K : git config --local du kit inchangée'

  pilote_desarme
  rm "$bin/python3"
  printf '%s\n' '#!/bin/sh' 'if [ "$4" = "--installer" ]; then exit 23; fi' 'exec "$PILOTE_REAL_PY" "$@"' > "$bin/python3"
  chmod +x "$bin/python3"
  pilote_lance o "$bin" o
  [ "$RC" -eq 0 ] && grep -q 'installation du pilote de fusion en échec (code 23)' "$OUT" || { ko "::pilote install échoué : code ou diagnostic absent — $(cat "$OUT" "$ERR")"; return; }
  if pilote_git -C "$depot" config --local --get merge.cadre-enregistrement.driver > /dev/null; then ko '::pilote install échoué : driver armé'; return; fi
  ok '::pilote install échoué : diagnostic et rc initial 0 conservés'
}

pilote_git() {
  env HOME="$PILOTE_HOME" GIT_CONFIG_GLOBAL="$PILOTE_GLOBAL" GIT_CONFIG_NOSYSTEM=1 git "$@"
}
pilote_desarme() {
  pilote_git -C "$PILOTE_DEPOT" config --local --unset merge.cadre-enregistrement.driver 2>/dev/null || true
  pilote_git -C "$PILOTE_DEPOT" config --local --unset merge.cadre-enregistrement.name 2>/dev/null || true
  rm -rf "$PILOTE_DEPOT/.git/cadre"
}
pilote_lance() { # réponse, PATH de sonde, scénario ; stdin pty sauf non-tty
  env -u CLAUDECODE PILOTE_HOME="$PILOTE_HOME" PILOTE_GLOBAL="$PILOTE_GLOBAL" \
    PILOTE_BIN="$2" PILOTE_SCRIPT="$PILOTE_SCRIPT" PILOTE_INV="$PILOTE_INV" \
    PILOTE_LOG="$TMP/pilote/python-journal" PILOTE_REAL_PY="$PILOTE_PY" PILOTE_HOOKS_RESPONSE="${PILOTE_HOOKS_RESPONSE:-Non}" \
    PILOTE_DOC="$DOC" PILOTE_OUT="$OUT" PILOTE_ERR="$ERR" \
    python3 -c '
import os, pty, subprocess, sys
answer, scenario = sys.argv[1:]
env = os.environ.copy()
env.update(HOME=env["PILOTE_HOME"], GIT_CONFIG_GLOBAL=env["PILOTE_GLOBAL"],
           GIT_CONFIG_NOSYSTEM="1", SETUP_OS="darwin", SETUP_PROBE_PATH=env["PILOTE_BIN"],
           SETUP_DOCTOR=env["PILOTE_DOC"])
if scenario.startswith("claudecode-"):
    env["CLAUDECODE"] = "" if scenario == "claudecode-vide" else " "
args = ["bash", env["PILOTE_SCRIPT"], "--inventory", env["PILOTE_INV"]]
if scenario == "dry-run": args.append("--dry-run")
master, slave = pty.openpty()
stdin = subprocess.DEVNULL if answer == "non-tty" else slave
proc = subprocess.Popen(args, stdin=stdin, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, env=env)
os.close(slave)
if answer not in ("non-tty", "eof"):
    os.write(master, (env["PILOTE_HOOKS_RESPONSE"] + "\n" + ("\n" if answer == "vide" else answer + "\n")).encode())
elif answer == "eof":
    os.write(master, b"Non\n\x04")
out, err = proc.communicate(timeout=60)
os.close(master)
open(env["PILOTE_OUT"], "wb").write(out)
open(env["PILOTE_ERR"], "wb").write(err)
sys.exit(proc.returncode)
  ' "$1" "$3"
  RC=$?
}

cas_pilote
if [ "${SETUP_TEST_ONLY:-}" = pilote ]; then
  bilan
  exit $?
fi

# ============================================================================
# (14) sous /bin/bash 3.2
# ============================================================================
if [ "${SETUP_TEST_ONLY:-}" = pilote_ps1 ]; then
  echo "SKIP: (14) SETUP_TEST_ONLY=pilote_ps1 — rejeu sous bash 3.2 NON joué"
elif [ -x /bin/bash ] && /bin/bash -c '[ "${BASH_VERSINFO[0]}" -eq 3 ]'; then
  BASHX=/bin/bash
  echo "-- (14) rejeu sous /bin/bash $(/bin/bash -c 'echo "$BASH_VERSION"')"
  TMP_PREFIX_SAVE="$TMP"
  TMP="$TMP/b32"; mkdir -p "$TMP"; OUT="$TMP/stdout"; ERR="$TMP/stderr"
  cas_1; cas_2_3; cas_4; cas_19; cas_22
  TMP="$TMP_PREFIX_SAVE"; OUT="$TMP/stdout"; ERR="$TMP/stderr"
  BASHX=bash
else
  echo "SKIP: (14) /bin/bash n'est pas un bash 3.2 ici — rejeu sous le plus vieux bash NON joué"
fi

# ============================================================================
# (W0) setup.ps1, statique 5.1 : une LECTURE (forme de attribution-locale.test.sh)
# ============================================================================
LIGNES_CODE="$(tr -d '\r' < "$PS1_SCRIPT" | grep -v '^[[:space:]]*#')"
MOTIF_PS7='\?\?|\?\.|&&|\|\||-AsHashtable|[$]Is(Windows|Linux|MacOS)'
n_nonascii="$(printf '%s\n' "$LIGNES_CODE" | LC_ALL=C grep -c '[^[:print:][:space:]]')"
n_ps7="$(printf '%s\n' "$LIGNES_CODE" | grep -cE "$MOTIF_PS7")"
if [ "$n_nonascii" -eq 0 ] && [ "$n_ps7" -eq 0 ]; then
  ok "(W0) statique 5.1 : lignes de code ASCII, aucune forme 7-only (lecture, pas une exécution 5.1)"
else
  ko "(W0) statique 5.1 : $n_nonascii ligne(s) de code non ASCII, $n_ps7 forme(s) 7-only"
  printf '%s\n' "$LIGNES_CODE" | LC_ALL=C grep -n -m3 '[^[:print:][:space:]]'
  printf '%s\n' "$LIGNES_CODE" | grep -nE -m3 "$MOTIF_PS7"
fi
# Les refus sont documentés en tête, et la garde agent est bien là.
for m in $MARQUEURS_AGENT; do
  grep -q "^    foreach (.nom in @(.*'$m'" "$PS1_SCRIPT" || ko "(W0) setup.ps1 : Get-MarqueurAgent ne lit pas $m"
done
grep -q '^#   7    lancé par un agent' "$PS1_SCRIPT" || ko "(W0) setup.ps1 : le code 7 n'est pas documenté en tête"

# Le pin pytest de setup.ps1 ($script:PytestPin = 'pytest==N') est celui que la
# CI du kit épingle (.github/workflows/ci.yml, ligne `pytest==N --hash=…`) ;
# lu dans les deux fichiers, jamais codé ici. ci.yml absent (adoptant) : SKIP dit.
PIN_PS1="$(tr -d '\r' < "$PS1_SCRIPT" | grep -o "^.script:PytestPin = 'pytest==[0-9][0-9.]*'" | grep -o '[0-9][0-9.]*' | sed -n 1p)"
if [ -z "$PIN_PS1" ]; then
  ko "(W0) pin pytest : \$script:PytestPin = 'pytest==<version>' introuvable dans setup.ps1"
  PIN_PS1="introuvable"
fi
CI_YML="$ROOT/.github/workflows/ci.yml"
if [ -f "$CI_YML" ]; then
  PIN_CI="$(sed -n 's/^ *pytest==\([0-9][0-9.]*\) .*/\1/p' "$CI_YML" | sed -n 1p)"
  if [ -n "$PIN_CI" ] && [ "$PIN_CI" = "$PIN_PS1" ]; then
    ok "(W0) pin pytest : setup.ps1 épingle pytest==$PIN_PS1, comme ci.yml"
  else
    ko "(W0) pin pytest : setup.ps1 épingle « $PIN_PS1 », ci.yml « ${PIN_CI:-introuvable} » — alignez \$script:PytestPin"
  fi
else
  echo "SKIP: (W0) pin pytest : $CI_YML absent — l'alignement sur la CI du kit n'est pas jouable ici"
fi
PIP_PYTEST="pytest==$PIN_PS1"

# (18) Le pin de la note macOS de setup.sh (sp_conseil, brew,pytest) est aussi
# celui de ci.yml : lu dans les deux fichiers, jamais codé ici.
if [ -f "$CI_YML" ]; then
  PINS_SH="$(grep -o 'pytest==[0-9][0-9.]*' "$SCRIPT" | sed 's/^pytest==//' | sort -u | tr '\n' ' ' | sed 's/ $//')"
  if [ -n "$PINS_SH" ] && [ "$PINS_SH" = "${PIN_CI:-}" ]; then
    ok "(18) pin pytest : la note macOS de setup.sh épingle pytest==$PINS_SH, comme ci.yml"
  else
    ko "(18) pin pytest : setup.sh épingle « ${PINS_SH:-rien} », ci.yml « ${PIN_CI:-introuvable} » — alignez la note brew,pytest de sp_conseil"
  fi
else
  echo "SKIP: (18) pin pytest de setup.sh : $CI_YML absent — l'alignement sur la CI du kit n'est pas jouable ici"
fi

PWSH="$(command -v pwsh 2>/dev/null || true)"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    echo "SKIP: (W1)-(W10) sous Git Bash, pwsh ne lance pas un bouchon winget sans extension — cas PowerShell NON joués"
    PWSH=""
    ;;
esac
if [ -z "$PWSH" ]; then
  [ -n "$(command -v pwsh 2>/dev/null || true)" ] || echo "SKIP: pwsh absent — cas (W1) à (W10) NON joués (dont le dialogue du pilote et le repli Arguments de 5.1), seul (W0), une lecture statique, l'a été"
  bilan
  exit $?
fi
echo "pwsh : $("$PWSH" -NoProfile -NonInteractive -Command "\$PSVersionTable.PSVersion.ToString()" 2>/dev/null | tr -d '\r')"

# ============================================================================
# (W1) parse par l'analyseur PowerShell, sans exécution
# ============================================================================
SETUP_PS1_FICHIER="$PS1_SCRIPT" "$PWSH" -NoProfile -NonInteractive -Command \
  '$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($env:SETUP_PS1_FICHIER,[ref]$t,[ref]$e); if ($e.Count -gt 0) { $e | ForEach-Object { $_.Message }; exit 1 }; exit 0' > "$OUT" 2> "$ERR"
if [ $? -eq 0 ]; then
  ok "(W1) Parser::ParseFile : aucune erreur de syntaxe"
else
  ko "(W1) Parser::ParseFile : $(cat "$OUT" "$ERR")"
fi

# ============================================================================
# (W10) dialogue PowerShell du pilote de fusion, sur le dépôt jetable de ::pilote
# ============================================================================
pilote_ps1_lance() { # réponse [scénario] ; stdin pty sauf non-tty
  env -u CLAUDECODE PILOTE_HOME="$PILOTE_HOME" PILOTE_GLOBAL="$PILOTE_GLOBAL" \
    PILOTE_PS1_BIN="$PILOTE_PS1_BIN" PILOTE_PS1_SCRIPT="$PILOTE_DEPOT/core-scripts/setup.ps1" \
    PILOTE_INV="$PILOTE_INV" PILOTE_OUT="$OUT" PILOTE_ERR="$ERR" PILOTE_PWSH="$PWSH" PILOTE_REAL_PY="$PILOTE_PY" PILOTE_HOOKS_RESPONSE="${PILOTE_HOOKS_RESPONSE:-Non}" \
    python3 -c '
import os, pty, subprocess, sys
answer, scenario = sys.argv[1], sys.argv[2]
env = os.environ.copy()
env.update(HOME=env["PILOTE_HOME"], GIT_CONFIG_GLOBAL=env["PILOTE_GLOBAL"],
           GIT_CONFIG_NOSYSTEM="1", SETUP_PS1_OS="windows", PATH=env["PILOTE_PS1_BIN"])
if scenario.startswith("claudecode-"):
    env["CLAUDECODE"] = "" if scenario == "claudecode-vide" else " "
args = [env["PILOTE_PWSH"], "-NoProfile", "-File", env["PILOTE_PS1_SCRIPT"],
        "-Inventory", env["PILOTE_INV"]]
master, slave = pty.openpty()
stdin = subprocess.DEVNULL if answer == "non-tty" else slave
proc = subprocess.Popen(args, stdin=stdin, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, env=env)
os.close(slave)
if answer != "non-tty":
    os.write(master, (env["PILOTE_HOOKS_RESPONSE"] + "\n" + ("\n" if answer == "vide" else answer + "\n")).encode())
out, err = proc.communicate(timeout=60)
os.close(master)
open(env["PILOTE_OUT"], "wb").write(out)
open(env["PILOTE_ERR"], "wb").write(err)
sys.exit(proc.returncode)
  ' "$1" "${2:-}"
  RC=$?
}
cas_pilote_ps1() {
  local cas bin vrai_python
  bin="$TMP/pilote/ps1-bin"
  mkdir -p "$bin"
  printf '%s\n' '#!/bin/sh' 'exit 0' > "$bin/winget"
  chmod +x "$bin/winget"
  ln -sf "$(command -v git)" "$bin/git"
  vrai_python="$(command -v python3)"
  ln -sf "$vrai_python" "$bin/python3"
  PILOTE_PS1_BIN="$bin"
  for cas in o oui vide Non Oui O non-tty; do
    pilote_desarme
    pilote_ps1_lance "$cas"
    [ "$RC" -eq 0 ] || { ko "(W10) $cas : rc $RC — $(cat "$OUT" "$ERR")"; return; }
    if [ "$cas" = o ] || [ "$cas" = oui ]; then
      pilote_git -C "$PILOTE_DEPOT" config --local --get merge.cadre-enregistrement.driver | grep -Fq "$PILOTE_DEPOT/.git/cadre/" || { ko "(W10) $cas : driver absent ou hors du clone"; return; }
      grep -q 'pilote de fusion verifie' "$OUT" || { ko "(W10) $cas : vérification absente"; return; }
      if grep -q 'depuis=origin/develop' "$OUT"; then ko "(W10) $cas : --depuis hors kit"; return; fi
    else
      if pilote_git -C "$PILOTE_DEPOT" config --local --get merge.cadre-enregistrement.driver > /dev/null; then
        ko "(W10) $cas : driver armé malgré le refus"
        return
      fi
      grep -q 'sans core.hooksPath -> .githooks' "$OUT" || { ko "(W10) $cas : avertissement absent"; return; }
      grep -Fq 'git config core.hooksPath .githooks' "$OUT" || { ko "(W10) $cas : commande d'armement absente"; return; }
      if grep -Eq 'T-0[0-9A-Z]{4}' "$OUT"; then ko "(W10) $cas : identifiant de tâche du kit affiché"; return; fi
    fi
    if [ "$cas" = non-tty ]; then
      if grep -q 'Installer le pilote de fusion' "$OUT"; then ko '(W10) non-tty : question interdite'; return; fi
    else
      grep -q 'Installer le pilote de fusion' "$OUT" || { ko "(W10) $cas : question absente"; return; }
    fi
    ok "(W10) $cas : dialogue PowerShell et armement conformes"
  done
  pilote_desarme
  PILOTE_HOOKS_RESPONSE=o pilote_ps1_lance Non
  [ "$RC" -eq 0 ] && [ "$(pilote_git -C "$PILOTE_DEPOT" config --local --get core.hooksPath)" = .githooks ] || { ko '(W10) hooks o : activation absente'; return; }
  if grep -Fq 'sans core.hooksPath' "$OUT" "$ERR"; then ko '(W10) hooks o : conseil devenu faux après activation'; return; fi
  pilote_git -C "$PILOTE_DEPOT" config --local --unset core.hooksPath
  ok '(W10) hooks o puis pilote Non : aucun conseil sans hooks après activation'
  for cas in claudecode-vide claudecode-blanc; do
    pilote_desarme
    pilote_ps1_lance vide "$cas"
    [ "$RC" -eq 0 ] && grep -q 'Installer le pilote de fusion' "$OUT" || { ko "(W10) $cas : question absente — $(cat "$OUT" "$ERR")"; return; }
    if grep -q 'non propose sous CLAUDECODE' "$OUT"; then ko "(W10) $cas : CLAUDECODE blanc lu comme posé"; return; fi
    ok "(W10) $cas : CLAUDECODE fait de blancs vaut absent, la question est posée"
  done
  pilote_desarme
  : > "$PILOTE_DEPOT/.agents/IS_THE_KIT"
  pilote_ps1_lance o
  [ "$RC" -eq 0 ] && grep -q 'depuis=origin/develop' "$OUT" || { ko "(W10) kit develop : --depuis absent — $(cat "$OUT" "$ERR")"; return; }
  ok '(W10) kit develop : --depuis origin/develop transmis'
  pilote_desarme
  rm "$PILOTE_DEPOT/.agents/IS_THE_KIT"
  rm "$bin/python3"
  printf '%s\n' '#!/bin/sh' 'if [ "$1" = "-c" ]; then exit 1; fi' 'echo Python 3.9.6' > "$bin/python3"
  chmod +x "$bin/python3"
  pilote_ps1_lance o
  [ "$RC" -eq 0 ] && grep -q 'pilote non propose : python >= 3.11 absent' "$OUT" || { ko "(W10) Python 3.9 : refus absent — $(cat "$OUT" "$ERR")"; return; }
  if grep -q 'Installer le pilote de fusion' "$OUT"; then ko '(W10) Python 3.9 : question posée'; return; fi
  ok '(W10) Python 3.9 : aucune question ni armement'
  pilote_desarme
  printf '%s\n' '#!/bin/sh' 'if [ "$4" = "--installer" ]; then exit 23; fi' 'exec "$PILOTE_REAL_PY" "$@"' > "$bin/python3"
  chmod +x "$bin/python3"
  pilote_ps1_lance o
  [ "$RC" -eq 0 ] && grep -q 'installation du pilote de fusion en echec (code 23)' "$OUT" || { ko "(W10) install échoué : code ou diagnostic absent — $(cat "$OUT" "$ERR")"; return; }
  if pilote_git -C "$PILOTE_DEPOT" config --local --get merge.cadre-enregistrement.driver > /dev/null; then ko '(W10) install échoué : driver armé'; return; fi
  ok '(W10) install échoué : diagnostic et rc initial 0 conservés'
  ln -sf "$vrai_python" "$bin/python3"
}

git -C "$ROOT" config --local --list > "$TMP/pilote/kit-avant-ps1"
cas_pilote_ps1
git -C "$ROOT" config --local --list > "$TMP/pilote/kit-apres-ps1"
if cmp -s "$TMP/pilote/kit-avant-ps1" "$TMP/pilote/kit-apres-ps1"; then
  ok '(W10) K : git config --local du kit inchangée'
else
  ko '(W10) K : configuration locale du kit modifiée par le dialogue PowerShell'
fi
if [ "${SETUP_TEST_ONLY:-}" = pilote_ps1 ]; then
  bilan
  exit $?
fi

# --- bouchons PowerShell ------------------------------------------------------
# faux_python <fichier> <dir> <journal> : un python3 factice — --version 3.12 ;
# `-m pytest --version` rend 0 seulement après `-m pip install --user pytest`,
# qui journalise et pose un marqueur.
faux_python() {
  {
    printf '#!/bin/sh\n'
    printf 'PATH=/usr/bin:/bin:$PATH\n'
    printf 'DIR=%s\n' "'$2'"
    printf 'JOURNAL=%s\n' "'$3'"
    printf '%s\n' 'if [ "$1" = "--version" ]; then echo "Python 3.12.0"; exit 0; fi' \
      'if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then' \
      '  if [ -e "$DIR/.pytest-pip" ]; then echo "pytest 9.0.0"; exit 0; fi' \
      '  exit 1' \
      'fi' \
      'if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then echo "pip $*" >> "$JOURNAL"; : > "$DIR/.pytest-pip"; exit 0; fi' \
      'exit 1'
  } > "$1"
  chmod +x "$1"
}

# faux_winget <dir> : journalise ; `install --id Git.Git …` copie le bouchon de
# réserve (version 99) sous git, bash et tee ; `--id Python.Python.3.12` copie le
# faux python3 ; un marqueur `.inerte` fait rendre 0 sans rien poser ; tout autre
# identifiant rend 1.
faux_winget() {
  local dir="$1" journal reserve
  journal="$(dirname "$dir")/journal"
  reserve="$(dirname "$dir")/reserve"
  mkdir -p "$dir"
  stub "$reserve" outil "x 99.0.0"
  faux_python "$reserve/python3" "$dir" "$journal"
  {
    printf '#!/bin/sh\n'
    # Sous pwsh, PATH ne contient que le dossier jetable : cp vient d'ici.
    printf 'PATH=/usr/bin:/bin:$PATH\n'
    printf 'DIR=%s\n' "'$dir'"
    printf 'JOURNAL=%s\n' "'$journal'"
    printf 'RESERVE=%s\n' "'$reserve'"
    printf '%s\n' 'echo "$@" >> "$JOURNAL"' \
      'if [ "$1" != "install" ]; then exit 2; fi' \
      'id=""' \
      'while [ $# -gt 0 ]; do' \
      '  if [ "$1" = "--id" ]; then id="$2"; fi' \
      '  shift' \
      'done' \
      'if [ -e "$DIR/.inerte" ]; then exit 0; fi' \
      'case "$id" in' \
      '  Git.Git)' \
      '    cp "$RESERVE/outil" "$DIR/git"' \
      '    cp "$RESERVE/outil" "$DIR/bash"' \
      '    cp "$RESERVE/outil" "$DIR/tee"' \
      '    ;;' \
      '  Python.Python.3.12)' \
      '    cp "$RESERVE/python3" "$DIR/python3"' \
      '    ;;' \
      '  *)' \
      '    exit 1' \
      '    ;;' \
      'esac' \
      'exit 0'
  } > "$dir/winget"
  chmod +x "$dir/winget"
}

# poste_w <nom> <jetons posés> [python] : un PATH jetable avec winget ; `python`
# pose le faux python3 (sans pytest) ; imprime le dossier bin
poste_w() {
  local d="$TMP/$1/bin"
  faux_winget "$d"
  pose_tous "$d" "$2"
  if [ "${3:-}" = "python" ]; then
    cp "$TMP/$1/reserve/python3" "$d/python3"
  fi
  printf '%s' "$d"
}

lance_w() { # lance_w <bin> [args…] : code dans RC, sans CLAUDECODE, branche Windows forcée, inventaire explicite
  local bin="$1"
  shift
  env -u CLAUDECODE "PATH=$bin" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" "$@" > "$OUT" 2> "$ERR"
  RC=$?
}
resume_w() { tr -d '\r' < "$OUT" | grep '^setup: installes='; }
WINGET_GIT='install --id Git.Git --exact --silent --accept-package-agreements --accept-source-agreements'
WINGET_PY='install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements'
B_W_SANS_GIT_PYTEST="$(printf '%s\n' "$B_WINDOWS" | sed 's/git //; s/ pytest//')"

# ============================================================================
# (W2) -DryRun
# ============================================================================
cas_w2() {
  local b
  b="$(poste_w w2 "bash tee" python)"
  lance_w "$b" -DryRun
  [ "$RC" -eq 1 ] || { ko "(W2) -DryRun : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  journal_absent "$b" || { ko "(W2) -DryRun : winget appelé — $(journal "$b")"; return; }
  [ ! -e "$b/git" ] || { ko "(W2) -DryRun : bouchon posé"; return; }
  grep -q "^setup: -DryRun : lancerait : winget $WINGET_GIT$" "$OUT" || { ko "(W2) -DryRun : « lancerait winget » absent — $(cat "$OUT")"; return; }
  grep -q "^setup: -DryRun : lancerait : $b/python3 -m pip install --user $PIP_PYTEST$" "$OUT" || { ko "(W2) -DryRun : « lancerait pip $PIP_PYTEST » absent — $(cat "$OUT")"; return; }
  [ "$(resume_w)" = "setup: installes=aucun deja la=$B_W_SANS_GIT_PYTEST manque encore=git pytest -- exit 1" ] \
    || { ko "(W2) -DryRun : résumé « $(resume_w) »"; return; }
  ok "(W2) -DryRun, git et pytest absents : rc 1, « lancerait » winget Git.Git et pip pytest, rien appelé, rien posé"

  env "CLAUDECODE=1" "PATH=$b" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" -DryRun > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 1 ] && journal_absent "$b" || { ko "(W2) -DryRun sous CLAUDECODE : rc $RC — $(diag)"; return; }
  ok "(W2) -DryRun sous CLAUDECODE=1 : permis (rc 1, rien n'est modifié)"
}

# ============================================================================
# (W3) winget et pip factices, (W4) idempotence
# ============================================================================
cas_w3_w4() {
  local b
  b="$(poste_w w3 "bash tee" python)"
  lance_w "$b"
  [ "$RC" -eq 0 ] || { ko "(W3) installation : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf '%s\npip -m pip install --user %s' "$WINGET_GIT" "$PIP_PYTEST")" ] \
    || { ko "(W3) installation : journal inattendu — $(journal "$b")"; return; }
  grep -q "^setup: lance : winget $WINGET_GIT$" "$OUT" || { ko "(W3) installation : winget non annoncé avant — $(cat "$OUT")"; return; }
  grep -q "^setup: lance : $b/python3 -m pip install --user $PIP_PYTEST$" "$OUT" || { ko "(W3) installation : pip $PIP_PYTEST non annoncé — $(cat "$OUT")"; return; }
  [ "$(resume_w)" = "setup: installes=git pytest deja la=$B_W_SANS_GIT_PYTEST manque encore=aucun -- exit 0" ] \
    || { ko "(W3) installation : résumé « $(resume_w) »"; return; }
  ok "(W3) winget factice : Git.Git une fois, pip $PIP_PYTEST (épinglé), annoncés avant, installes=git pytest, rc 0"

  : > "$(dirname "$b")/journal"
  lance_w "$b"
  [ "$RC" -eq 0 ] || { ko "(W4) idempotence : rc $RC ≠ 0 — $(diag)"; return; }
  [ -z "$(journal "$b")" ] || { ko "(W4) idempotence : winget ou pip rappelé — $(journal "$b")"; return; }
  [ "$(resume_w)" = "setup: installes=aucun deja la=$B_WINDOWS manque encore=aucun -- exit 0" ] \
    || { ko "(W4) idempotence : résumé « $(resume_w) »"; return; }
  ok "(W4) idempotence : relancé, rc 0, journal vide, tout deja la"
}

# ============================================================================
# (W5) sous un agent, (W6) hors Windows, (W7) winget absent
# ============================================================================
cas_w5_w6_w7() {
  local b m blanc
  b="$(poste_w w5 "bash tee" python)"
  for m in $MARQUEURS_AGENT; do
    env -u CLAUDECODE "$m=1" "PATH=$b" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" > "$OUT" 2> "$ERR"
    RC=$?
    [ "$RC" -eq 7 ] || { ko "(W5) $m=1 : rc $RC ≠ 7 — $(diag)"; return; }
    journal_absent "$b" || { ko "(W5) $m=1 : winget appelé"; return; }
    grep -q 'pas par un agent' "$ERR" || { ko "(W5) $m=1 : message — $(diag)"; return; }
    grep -qF "($m est pose ici)" "$ERR" || { ko "(W5) $m=1 : le message ne nomme pas $m — $(diag)"; return; }
    ok "(W5) $m=1 sans -DryRun : rc 7, rien appelé, $m nommé"

    env -u CLAUDECODE "$m=1" "PATH=$b" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" -DryRun > "$OUT" 2> "$ERR"
    RC=$?
    [ "$RC" -eq 1 ] && journal_absent "$b" || { ko "(W5) -DryRun sous $m=1 : rc $RC — $(diag)"; return; }
    ok "(W5) -DryRun sous $m=1 : permis (rc 1, rien appelé)"
  done

  # Les cinq faits de blancs valent absents : sans -DryRun, pour que le
  # refus 7 soit atteignable ; le bouchon winget du poste w5 est alors appelé
  # (git et pytest y manquent) — c'est la preuve que le refus n'a pas mordu.
  blanc="$(printf ' \t\v\f ')"
  env "CLAUDECODE=$blanc" "CLAUDE_CODE_ENTRYPOINT=$blanc" "AGENTS_HOOK_HOST=$blanc" "COPILOT_AGENT_SESSION_ID=$blanc" "COPILOT_CLI=$blanc" \
    "PATH=$b" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -ne 7 ] || { ko "(W5) marqueurs de blancs : refusé en 7 — $(diag)"; return; }
  ! journal_absent "$b" || { ko "(W5) marqueurs de blancs : winget jamais appelé (rc $RC) — $(diag)"; return; }
  ok "(W5) les cinq marqueurs faits de blancs : valent absents, winget appelé (rc $RC)"

  env -u CLAUDECODE "PATH=$b" "$PWSH" -NoProfile -NonInteractive -File "$PS1_SCRIPT" -Inventory "$INV" -DryRun > "$OUT" 2> "$ERR"
  RC=$?
  if [ "$(uname -s)" = "Darwin" ] || [ "$(uname -s)" = "Linux" ]; then
    [ "$RC" -eq 2 ] && grep -q 'bash core-scripts/setup.sh' "$ERR" || { ko "(W6) hors Windows : rc $RC — $(diag)"; return; }
    ok "(W6) hors Windows sans SETUP_PS1_OS : rc 2, renvoie à core-scripts/setup.sh"
  else
    echo "SKIP: (W6) plateforme $(uname -s) — le refus hors Windows n'est pas jouable ici"
  fi

  mkdir -p "$TMP/w7/bin"
  pose_tous "$TMP/w7/bin" "$B_WINDOWS"
  lance_w "$TMP/w7/bin" -DryRun
  [ "$RC" -eq 2 ] && grep -q 'App Installer' "$ERR" || { ko "(W7) winget absent : rc $RC — $(diag)"; return; }
  ok "(W7) winget absent : rc 2, renvoie à App Installer"
}

# ============================================================================
# (W8) python absent : winget Python puis pip ; winget inerte : manque encore
# ============================================================================
cas_w8() {
  local b
  b="$(poste_w w8 "git bash tee")"
  lance_w "$b"
  [ "$RC" -eq 0 ] || { ko "(W8) python absent : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf '%s\npip -m pip install --user %s' "$WINGET_PY" "$PIP_PYTEST")" ] \
    || { ko "(W8) python absent : journal inattendu — $(journal "$b")"; return; }
  [ "$(resume_w)" = "setup: installes=python3|python|py pytest deja la=git bash tee manque encore=aucun -- exit 0" ] \
    || { ko "(W8) python absent : résumé « $(resume_w) »"; return; }
  ok "(W8) python absent : winget Python.Python.3.12, python re-sondé, pip pytest, rc 0"

  b="$(poste_w w8b "git bash tee")"
  : > "$b/.inerte"
  lance_w "$b"
  [ "$RC" -eq 1 ] || { ko "(W8) winget inerte : rc $RC ≠ 1 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$WINGET_PY" ] || { ko "(W8) winget inerte : journal inattendu — $(journal "$b")"; return; }
  grep -q '^setup: pip : Python n est pas visible de cette session' "$OUT" || { ko "(W8) winget inerte : pip non expliqué — $(cat "$OUT")"; return; }
  grep -q "^    a taper, dans un NOUVEAU terminal : python -m pip install --user $PIP_PYTEST$" "$OUT" || { ko "(W8) winget inerte : commande pip $PIP_PYTEST absente — $(cat "$OUT")"; return; }
  grep -q "^    a taper : winget $WINGET_PY$" "$OUT" || { ko "(W8) winget inerte : commande winget absente — $(cat "$OUT")"; return; }
  grep -q '^    note : winget ecrit le PATH systeme' "$OUT" || { ko "(W8) winget inerte : note PATH absente"; return; }
  [ "$(resume_w)" = "setup: installes=aucun deja la=git bash tee manque encore=python3|python|py pytest -- exit 1" ] \
    || { ko "(W8) winget inerte : résumé « $(resume_w) »"; return; }
  ok "(W8) winget qui ne pose rien : python et pytest manquent encore, commandes et note PATH affichées, rc 1"
}

# ============================================================================
# (W9) le repli `Arguments` d'Invoke-CapturedProcess, celui de Windows PowerShell 5.1
# ============================================================================
# Sous 5.1 (.NET Framework), ProcessStartInfo n'a pas ArgumentList : setup.ps1
# passe alors par `$startInfo.Arguments = Join-NativeArguments …`. pwsh 7 a
# ArgumentList : sans aide, ce repli n'est JAMAIS pris ici. Le banc le force sur
# une COPIE dont la SEULE ligne changée est l'aiguillage
# (`if ($null -ne $argumentListProperty) {` → `if ($false) {`), puis :
#   (a) rejoue (W3) sur la copie — les sondes `--version` et `-m pytest
#       --version` passent par Arguments — : même journal, rc 0 ;
#   (b) fait passer des valeurs piégées (vide, espace, guillemets, antislash
#       final, antislash devant guillemet, tabulation) par l'Invoke-CapturedProcess
#       de la copie jusqu'à un bouchon qui les réimprime une par ligne : elles
#       reviennent intactes. Contrôle : la même chose par le fichier SUIVI
#       (ArgumentList) — s'il rougit, c'est le banc qui est cassé, pas le repli.
# NON COUVERT : l'aiguillage lui-même sous .NET Framework (que la propriété y
# soit absente) ; le découpage de la ligne par Windows — ici c'est le découpeur
# de .NET sous Unix qui lit Arguments, aux règles de la CRT Microsoft ; Windows
# PowerShell 5.1 n'est jamais exécuté.
w9_argv() { # w9_argv <setup.ps1> : imprime ce que le bouchon a reçu ; code dans RC
  env -u CLAUDECODE "PATH=$TMP/w9/bin" "$PWSH" -NoProfile -NonInteractive -File "$TMP/w9/argv.ps1" \
    -Fichier "$1" -Echo "$TMP/w9/bin/echo-args" -Valeurs "$TMP/w9/valeurs" > "$OUT" 2> "$ERR"
  RC=$?
}
cas_w9() {
  local b copie n attendu
  mkdir -p "$TMP/w9/bin"
  copie="$TMP/w9/setup-repli.ps1"
  n="$(grep -c 'if (\$null -ne \$argumentListProperty) {' "$PS1_SCRIPT")"
  [ "$n" -eq 1 ] || { ko "(W9) repli Arguments : l'aiguillage « if (\$null -ne \$argumentListProperty) { » est là $n fois dans setup.ps1 (1 attendu) — le banc ne sait plus forcer le repli"; return; }
  sed 's/if (\$null -ne \$argumentListProperty) {/if ($false) {/' "$PS1_SCRIPT" > "$copie"
  [ "$(grep -c 'if (\$false) {' "$copie")" -eq 1 ] || { ko "(W9) repli Arguments : la copie n'a pas UN aiguillage forcé"; return; }

  # (a) le déroulé complet sur la copie
  b="$(poste_w w9a "bash tee" python)"
  env -u CLAUDECODE "PATH=$b" "SETUP_PS1_OS=windows" "$PWSH" -NoProfile -NonInteractive -File "$copie" -Inventory "$INV" > "$OUT" 2> "$ERR"
  RC=$?
  [ "$RC" -eq 0 ] || { ko "(W9) repli Arguments, déroulé : rc $RC ≠ 0 — $(diag) $(cat "$OUT")"; return; }
  [ "$(journal "$b")" = "$(printf '%s\npip -m pip install --user %s' "$WINGET_GIT" "$PIP_PYTEST")" ] \
    || { ko "(W9) repli Arguments, déroulé : journal inattendu — $(journal "$b")"; return; }
  [ "$(resume_w)" = "setup: installes=git pytest deja la=$B_W_SANS_GIT_PYTEST manque encore=aucun -- exit 0" ] \
    || { ko "(W9) repli Arguments, déroulé : résumé « $(resume_w) »"; return; }
  ok "(W9) repli Arguments forcé : (W3) rejoué sur la copie, sondes --version et -m pytest --version par Arguments, rc 0, même journal"

  # (b) les valeurs piégées, aller-retour
  printf '%s\n' '#!/bin/sh' 'echo "$#"' 'for a in "$@"; do printf "[%s]\n" "$a"; done' > "$TMP/w9/bin/echo-args"
  chmod +x "$TMP/w9/bin/echo-args"
  printf '%s\n' '' 'a b' 'say "hi"' "C:\\dir with space\\" 'x\"y' "trail\\" 'pytest==9.1.1' "tab$(printf '\t')there" > "$TMP/w9/valeurs"
  printf '%s\n' \
    'param([string] $Fichier, [string] $Echo, [string] $Valeurs)' \
    'Set-StrictMode -Version 2.0' \
    '$ErrorActionPreference = "Stop"' \
    '$jetons = $null' \
    '$erreurs = $null' \
    '$ast = [System.Management.Automation.Language.Parser]::ParseFile($Fichier, [ref] $jetons, [ref] $erreurs)' \
    'foreach ($nom in @("ConvertTo-NativeArgument", "Join-NativeArguments", "Invoke-CapturedProcess")) {' \
    '    $predicat = { param($n) ($n -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and ($n.Name -eq $nom) }.GetNewClosure()' \
    '    $def = $ast.Find($predicat, $true)' \
    '    if ($null -eq $def) { [Console]::Error.WriteLine("fonction absente de setup.ps1 : " + $nom); exit 3 }' \
    '    . ([scriptblock]::Create($def.Extent.Text))' \
    '}' \
    '$r = Invoke-CapturedProcess -FileName $Echo -ArgumentValues ([System.IO.File]::ReadAllLines($Valeurs))' \
    '[Console]::Out.Write($r.Stdout)' \
    '[Console]::Error.Write($r.Stderr)' \
    'exit $r.ExitCode' > "$TMP/w9/argv.ps1"
  attendu="$(grep -c '' "$TMP/w9/valeurs"; while IFS= read -r v; do printf '[%s]\n' "$v"; done < "$TMP/w9/valeurs")"

  w9_argv "$PS1_SCRIPT"
  [ "$RC" -eq 0 ] && [ "$(tr -d '\r' < "$OUT")" = "$attendu" ] \
    || { ko "(W9) contrôle ArgumentList (fichier suivi) : rc $RC, reçu « $(cat "$OUT") » ≠ « $attendu » — $(diag)"; return; }
  w9_argv "$copie"
  [ "$RC" -eq 0 ] && [ "$(tr -d '\r' < "$OUT")" = "$attendu" ] \
    || { ko "(W9) repli Arguments, valeurs piégées : rc $RC, reçu « $(cat "$OUT") » ≠ « $attendu » — $(diag)"; return; }
  ok "(W9) repli Arguments forcé : $(grep -c '' "$TMP/w9/valeurs") valeurs piégées (vide, espace, guillemets, antislash final ou devant guillemet, tabulation) reviennent intactes, comme par ArgumentList"
}

cas_w2; cas_w3_w4; cas_w5_w6_w7; cas_w8; cas_w9

bilan
exit $?
