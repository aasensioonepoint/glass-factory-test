#!/usr/bin/env bash
# ============================================================================
# core-scripts/doctor.sh — LE DOCTOR DES OUTILS DU POSTE ET DE LA CI DU KIT.
# Il RAPPORTE ; il n'installe rien (T-00001001, BK-343, volet b de T-00000529).
#
# PÉRIMÈTRE — BORNÉ À L'INVENTAIRE. Pour chaque ligne de
# `core-scripts/tool-inventory.tsv`, il dit si l'outil externe est PRESENT,
# ABSENT ou en MAUVAISE VERSION sur CE poste : les outils du poste de
# développement et de la CI DU KIT, et eux seuls. Il ne porte AUCUNE liste
# d'outils : chaque ligne du rapport vient d'une ligne du TSV, et
# `core-scripts/doctor.test.sh` le prouve par grep. Un outil que l'inventaire
# ne nomme pas n'existe pas pour lui.
#
# CE N'EST PAS LE DOCTOR DE L'ADOPTANT. L'installation et la santé d'un projet
# adoptant relèvent de `cadre doctor` — nom RÉSERVÉ par le contrat du kit
# (Phase 6) et PAS ENCORE LIVRÉ : aujourd'hui `cadre doctor` refuse (rc 2). Ce
# script ne le remplace pas ; chez un adoptant, il ne dit que ce que
# l'inventaire DU KIT attend d'un poste.
#
# USAGE
#   doctor.sh [--inventory <tsv>] [--ci <ci.yml>] [--verify <verify.sh>] [--list]
#     --inventory  autre inventaire (défaut : core-scripts/tool-inventory.tsv)
#     --ci         workflow dont on dérive le canal apt (défaut : .github/workflows/ci.yml) ;
#                  passé EXPLICITEMENT, un canal apt non dérivable rend rc 1
#     --verify     porte dont on lit RUNNER_PREINSTALLED (défaut : core-scripts/verify.sh)
#     --list       imprime l'inventaire SANS rien sonder, rc 0
#   DOCTOR_OS=darwin|linux|windows   impose la plateforme (sinon `uname -s`)
#   DOCTOR_PROBE_PATH=<PATH>         PATH de la sonde (défaut : $PATH) ; les bancs y posent des bouchons
#   DOCTOR_DISCOVERY_DELAI=<s>       borne de la découverte des modules (défaut : 30) — RÉSERVÉE AUX BANCS
#
# VOCABULAIRE — PRESENT · ABSENT (requis | optionnel) · MAUVAISE VERSION · N/A (plateforme …).
#   Classe B (colonne `class`) : son ABSENCE rend la porte nue du kit ROUGE.
#   Classe A : son absence est annoncée (saut ou COVERAGE DEGRADED), porte verte.
#   Les lignes `nature=condition` ne se sondent JAMAIS : elles sont comptées et nommées.
#
# LA SONDE — UNE RECHERCHE PAR NOM DANS LE PATH. Chaque jeton est cherché par
# `type -P`, dans un sous-shell dont le PATH est DOCTOR_PROBE_PATH (défaut :
# $PATH), PUIS le chemin rendu doit passer `[ -x ]`. `type -P` rend le premier
# fichier EXÉCUTABLE du nom ; un fichier non exécutable du même nom placé plus
# tôt dans le PATH est SAUTÉ, et c'est l'exécutable plus loin qui est PRESENT,
# son chemin rapporté. Mais quand AUCUN exécutable du nom n'existe dans le
# PATH, `type -P` rend le premier fichier du nom, même en mode 644, rc 0
# (relevé bash 5.3.15 et /bin/bash 3.2.57, 2026-10-08) : le `[ -x ]` ferme ce
# cas, un non-exécutable seul est ABSENT. Un builtin, un mot-clé,
# une fonction ou un alias du même nom n'est JAMAIS « PRESENT » — `command -v`,
# la sonde d'avant, rendait `printf` ou `test` présents sous un PATH vide
# (relevé /bin/bash 3.2, 2026-10-08 ; cas 17 de doctor.test.sh, qui tient aussi
# le non-exécutable seul).
# LE MODE DE SONDE — colonne `mode_sonde` de l'inventaire (requise). `-` : la
# recherche par nom ci-dessus. `module:<interpréteur>[|<alternative>…]` : l'outil
# est un MODULE que la porte lance par son interpréteur (`"$PY" -m pytest`) ; un
# binaire du même nom dans le PATH ne prouve rien (relevé 2026-10-14 : bouchon
# `pytest` sur le PATH, « PRESENT », alors que `/usr/bin/python3 -m pytest` rend
# « No module named pytest »). Le PREMIER interpréteur trouvé par nom ET qui
# répond à `--version` (rc 0) — la règle de la porte, boucle
# « for c in python3 python py » de run-pytest-shards.sh — est EXÉCUTÉ :
# `<interpréteur> -m <outil> --version`, entrée fermée, nom du module en argument
# positionnel, jamais re-parsé ; rc 0 = PRESENT, sinon ABSENT avec ce rc et la
# 1re ligne de la sortie (sans caractère de contrôle). Un interpréteur trouvé
# qui rend rc ≠ 0 à `--version` (le bouchon `python3` du Microsoft Store sous
# Git Bash, rc 9) est sauté, comme la porte le saute (cas 20 de doctor.test.sh).
# Aucune alternative d'interpréteur n'est essayée après la première qui répond :
# ce serait un faux vert de plus. La ligne doit être `nature=outil` et son jeton UN nom (pas de `|`).
# Sa version, quand la colonne `version` en écrit une, se lit dans cette même
# sortie. Ce mode est une EXÉCUTION, sans chien de garde, comme `--version`.
#
# LA VERSION — MESURÉE, ET BORNÉE. Pour une ligne `nature=outil` dont la
# colonne `version` n'est pas `-`, et SEULEMENT si l'outil est présent, le
# doctor exécute `<chemin résolu> --version`, entrée fermée. `>=X.Y` compare le
# premier numéro pointé de la sortie ; toute autre contrainte (`GNU`) est un
# texte cherché dans la sortie. Aucun numéro lisible : PRESENT et « version non
# mesurée », avec le code de retour de `--version` et sa première ligne, jamais
# un rouge. Ce code de retour est RAPPORTÉ, il ne décide pas : un numéro lu
# dans une sortie à rc ≠ 0 est comparé comme un autre. BORNE NOMMÉE : six lignes à contrainte à BASE,
# toutes des utilitaires de base, exécutées SANS chien de garde ; une ligne
# FUTURE dont `--version` bloquerait ou attendrait une saisie bloquerait le
# doctor. `ssh-keygen` n'a pas d'option `--version` : il rend son usage, sans
# numéro pointé (relevé OpenSSH macOS, 2026-10-08) — sa version est donc
# toujours « non mesurée », jamais un faux verdict. Les lignes sans contrainte
# ne sont jamais exécutées : `type -P` et `[ -x ]` seuls — sauf une ligne en
# mode `module:`, dont la sonde même est une exécution. La première ligne
# rapportée de `--version` perd ses caractères de contrôle (ESC, CR, DEL… ; la
# tabulation reste) : une sortie d'outil n'écrit pas de séquence de terminal
# dans le rapport (avis sécurité, S-00004490) — « version non mesurée » comme
# version d'une contrainte textuelle (S-00004538, cas 16 de doctor.test.sh) ;
# une sortie vide s'y lit « sortie vide ».
#
# LA FORME DU JETON. Une ligne `nature=outil` dont la colonne `tool` sort de
# `[A-Za-z0-9][A-Za-z0-9._+-]*`, alternatives séparées par `|`, rend
# l'inventaire illisible (rc 1) : ni `/` (un chemin court-circuiterait la
# sonde par PATH), ni glob, ni `-` ou `.` initial (une option, ou le builtin
# `.`). Les jetons sont découpés sous `set -f`.
#
# LES MODULES DU PROJET (T-01M5VYNMZPG8G0JZG48HV4K0PN). Avant le résumé, deux
# lignes que nul lecteur du résumé ne prend pour lui (aucune ne porte
# « présents, ») :
#   doctor: modules : <familles séparées par des virgules | aucun | illisible>
#   doctor: hors classe B ici : <outil> — <raison>      (zéro, une ou plusieurs)
# Les familles sont celles de `discover()` de .agents/security/module_discovery.py
# — la découverte de la porte adoptant (porte_adoptant.py), modules sous
# `.agents/` écartés comme elle les écarte —, dans l'ordre de son FAMILIES, plus
# `iac` quand un `*.tf` est à la racine (seule borne : la racine, pas l'arbre).
# L'interpréteur est le PREMIER qui répond à `--version` parmi les alternatives
# de la première ligne outil en mode `module:` de l'inventaire (la règle de la
# porte, celle de LE MODE DE SONDE) ; il exécute un texte CONSTANT, valeurs en
# argv, sous `-I -B` ; découverte dans un fil, BORNÉE à 30 s côté interpréteur
# (macOS n'a pas de binaire `timeout`) : au-delà, `os._exit` et « illisible ».
# Pas d'interpréteur, module absent, erreur, sortie hors forme : « illisible ».
# LA RÈGLE DE CLASSE, PAR PROPRIÉTÉ ET JAMAIS PAR NOM (le cas 13 de
# doctor.test.sh interdit tout jeton de l'inventaire dans ce code) : HORS du
# kit (pas de .agents/IS_THE_KIT), une ligne outil de classe B en mode `module:`
# — un module lancé par son interpréteur — passe en classe A quand la
# découverte est LISIBLE et ne rend AUCUNE famille qui porte le nom d'une de
# ses alternatives d'interpréteur. À l'inventaire du 2026-10-26 c'est pytest
# (`module:python3|python|py`, famille `python`) : sans module python, la porte
# adoptant ne lance pas pytest, il ne rougit rien. Illisible : la classe B
# reste (fail-closed). Dans le kit : les classes de l'inventaire, inchangées.
# setup.sh lit ces deux lignes ; la jambe outils du bilan aussi.
#
# EXIT — 0 : tous les outils de classe B de la plateforme sont présents.
#   1 : un outil de classe B ABSENT ; inventaire illisible (pas de ligne de
#       colonnes, colonne requise absente, ligne au mauvais nombre de champs,
#       champ vide, `nature`/`class`/`mode_sonde` hors vocabulaire, jeton `tool`
#       d'une ligne outil hors forme, `cost` ouvrant par le mot que le relevé du
#       runner compte) ; `--ci` explicite sans canal apt.
#   2 : usage.
#   MAUVAISE VERSION ne change JAMAIS le code : l'en-tête du TSV définit la
#   classe par l'ABSENCE, et la colonne `cost` dit ce qu'une version basse coûte.
#
# CANAL APT DE LA CI — DÉRIVÉ, PAS DÉCLARÉ. La ligne `apt-get install -y` du
# workflow et RUNNER_PREINSTALLED de la porte sont lus par les MÊMES trois
# `sed` que core-scripts/check-ci-parity.sh — mêmes octets, une seule
# expression entre apostrophes par ligne physique (cas 12 de doctor.test.sh).
# Les seaux s'apparient par la colonne `apt` (nom de PAQUET), jamais par le nom
# d'outil. Les canaux épinglés (curl, pip, zip, setup-python, image) ne sont
# PAS dérivés : ils sont DÉCLARÉS par `ci_pin` et cités — toute ligne outil à
# `ci_pin` ≠ `-`, qu'elle ait un paquet apt ou non (ctags : apt sous linux, zip
# épinglé sous windows). brew (macOS, non épinglé) ne l'est pas : ce rapport ne
# cite pas la colonne `brew` (il la veut seulement non vide).
# Porte absente, ou sans ligne `RUNNER_PREINSTALLED="…"` hors commentaire : le
# seau 2 et les préinstallés runner sont « non dérivable », jamais calculés à vide.
# Workflow sans ligne apt (un adoptant réécrit ci.yml) : « non dérivable », rc
# intact — sauf `--ci` explicite.
#
# PLATEFORME. DOCTOR_OS, sinon `uname -s` : Darwin→darwin, Linux→linux,
# MINGW*/MSYS*/CYGWIN*→windows ; autre → « os inconnu », toutes les lignes
# sondées. Sous Windows le RAPPORT n'est pas mesuré (en-tête de l'inventaire) ;
# la SUITE doctor.test.sh, elle, tourne sur les trois jambes.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

INV="$ROOT/core-scripts/tool-inventory.tsv"
CI_FILE="$ROOT/.github/workflows/ci.yml"
VERIFY_FILE="$ROOT/core-scripts/verify.sh"
CI_EXPLICIT=0
LIST=0
US=$'\037'
_pipe='|'
_ge='>='
_mod='module:'

dr_usage() {
  printf '%s\n' 'usage: doctor.sh [--inventory <tsv>] [--ci <ci.yml>] [--verify <verify.sh>] [--list]'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --inventory|--ci|--verify)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        printf 'doctor: %s attend un fichier\n' "$1" >&2
        dr_usage >&2
        exit 2
      fi
      case "$2" in
        --*)
          printf 'doctor: %s attend un fichier, pas %s\n' "$1" "$2" >&2
          dr_usage >&2
          exit 2
          ;;
      esac
      if [ "$1" = "--inventory" ]; then
        INV="$2"
      elif [ "$1" = "--ci" ]; then
        CI_FILE="$2"
        CI_EXPLICIT=1
      else
        VERIFY_FILE="$2"
      fi
      shift 2
      ;;
    --list)
      LIST=1
      shift
      ;;
    -h|--help)
      dr_usage
      exit 0
      ;;
    *)
      printf 'doctor: argument inconnu : %s\n' "$1" >&2
      dr_usage >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$INV" ] || [ ! -r "$INV" ]; then
  printf 'doctor: inventaire illisible : %s\n' "$INV" >&2
  exit 1
fi

# --- LECTURE DE L'INVENTAIRE ------------------------------------------------
# Par NOM de colonne, `awk -F'\t'` : jamais `read` sur des tabulations, où deux
# tabulations consécutives fusionnent et décalent les colonnes (plan
# T-00000529, R7). Sortie normalisée : `=` + champs séparés par US (0x1F, un
# séparateur qui n'est pas un blanc IFS, donc jamais fusionné) ; une erreur =
# une ligne `!`. Ordre des champs : NR, tool, nature, os, class, version,
# ci_pin, apt, cost, mode_sonde.
NORM="$(awk -F'\t' -v us="$US" '
  { sub(/\r$/, "") }
  /^#/ { next }
  hdr == 0 {
    hdr = 1
    nc = NF
    for (i = 1; i <= NF; i++) { col[$i] = i; nom[i] = $i }
    nreq = split("tool nature os class version ci_pin apt cost mode_sonde", req, " ")
    for (j = 1; j <= nreq; j++) {
      if (!(req[j] in col)) { print "!colonne requise absente de la ligne de colonnes : " req[j]; hdrbad = 1 }
    }
    next
  }
  hdrbad { next }
  /^[[:space:]]*$/ { next }
  {
    if (NF != nc) { print "!ligne " NR " : " NF " champs, " nc " attendus"; next }
    vide = 0
    for (i = 1; i <= NF; i++) {
      if ($i == "") { print "!ligne " NR ", colonne " nom[i] " : champ vide (ecrire - pour sans objet)"; vide = 1 }
    }
    if (vide) next
    nat = $col["nature"]; cls = $col["class"]; cost = $col["cost"]
    if (nat != "outil" && nat != "condition") print "!ligne " NR ", colonne nature : " nat " hors vocabulaire (outil | condition)"
    if (cls != "A" && cls != "B") print "!ligne " NR ", colonne class : " cls " hors vocabulaire (A | B)"
    if (nat == "outil" && $col["tool"] !~ /^[A-Za-z0-9][A-Za-z0-9._+-]*([|][A-Za-z0-9][A-Za-z0-9._+-]*)*$/) print "!ligne " NR ", colonne tool : " $col["tool"] " hors forme (jetons [A-Za-z0-9._+-] ouvrant par une lettre ou un chiffre, separes par |)"
    if (cost ~ /^[[:space:]]*SKIP/) print "!ligne " NR ", colonne cost : ouvre par SKIP, que le releve du runner compterait"
    mode = $col["mode_sonde"]
    if (mode != "-") {
      if (mode !~ /^module:[A-Za-z0-9][A-Za-z0-9._+-]*([|][A-Za-z0-9][A-Za-z0-9._+-]*)*$/) print "!ligne " NR ", colonne mode_sonde : " mode " hors vocabulaire (- | module:<interpreteur>, alternatives separees par |, jetons de la forme de tool)"
      else if (nat != "outil") print "!ligne " NR ", colonne mode_sonde : " mode " sur une ligne " nat " (seule une ligne outil se sonde)"
      else if ($col["tool"] ~ /[|]/) print "!ligne " NR ", colonne mode_sonde : " mode " sur le jeton a alternatives " $col["tool"] " (un module est UN nom)"
    }
    print "=" NR us $col["tool"] us nat us $col["os"] us cls us $col["version"] us $col["ci_pin"] us $col["apt"] us cost us mode
    n++
  }
  END {
    if (!hdr) print "!aucune ligne de colonnes"
    else if (!hdrbad && n == 0) print "!inventaire vide : aucune ligne de donnees"
  }
' "$INV")"
AWK_RC=$?
if [ "$AWK_RC" -ne 0 ]; then
  printf 'doctor: lecture de l inventaire impossible (lecteur rc %s) : %s\n' "$AWK_RC" "$INV" >&2
  exit 1
fi
ERRS="$(printf '%s\n' "$NORM" | sed -n 's/^!//p')"
if [ -n "$ERRS" ]; then
  while IFS= read -r e; do
    printf 'doctor: inventaire %s : %s\n' "$INV" "$e" >&2
  done <<< "$ERRS"
  exit 1
fi
DATA="$(printf '%s\n' "$NORM" | sed -n 's/^=//p')"

# --- --list : l'inventaire, sans aucune sonde --------------------------------
if [ "$LIST" -eq 1 ]; then
  printf 'Inventaire %s — rien n est sondé\n' "$INV"
  nl=0
  while IFS="$US" read -r _ tool nature os klass version _; do
    nl=$((nl + 1))
    printf '  %-34s %-9s classe %s  os %-12s version %s\n' "$tool" "$nature" "$klass" "$os" "$version"
  done <<< "$DATA"
  printf 'doctor --list : %s lignes, aucune sondée — exit 0\n' "$nl"
  exit 0
fi

# --- plateforme -------------------------------------------------------------
OS=""
OS_NOTE=""
UNAME_S=""
if [ -n "${DOCTOR_OS:-}" ]; then
  case "$DOCTOR_OS" in
    darwin|linux|windows)
      OS="$DOCTOR_OS"
      OS_NOTE="imposée par DOCTOR_OS"
      ;;
    *)
      printf 'doctor: DOCTOR_OS=%s inconnu (darwin | linux | windows)\n' "$DOCTOR_OS" >&2
      exit 2
      ;;
  esac
else
  UNAME_S="$(uname -s 2>/dev/null)"
  case "$UNAME_S" in
    Darwin)
      OS=darwin
      ;;
    Linux)
      OS=linux
      ;;
    MINGW*|MSYS*|CYGWIN*)
      OS=windows
      ;;
  esac
  OS_NOTE="uname -s : $UNAME_S"
fi

dr_os_applies() { # dr_os_applies <cellule os> : rc 0 si la ligne vaut pour cette plateforme
  [ -z "$OS" ] && return 0
  [ "$1" = "any" ] && return 0
  case ",$1," in
    *",$OS,"*)
      return 0
      ;;
  esac
  return 1
}

dr_probe() { # dr_probe <jeton> : chemin résolu sur stdout, rc 0 si trouvé ET exécutable
  local p
  p="$( PATH="${DOCTOR_PROBE_PATH:-$PATH}"; type -P "$1" 2>/dev/null )" || return 1
  # `type -P` rend un fichier 644 quand aucun exécutable du nom n'est dans le PATH.
  [ -x "$p" ] || return 1
  printf '%s\n' "$p"
}

dr_ge() { # dr_ge <vu> <seuil> : rc 0 si vu >= seuil, champ numérique par champ
  awk -v a="$1" -v b="$2" 'BEGIN {
    na = split(a, x, "."); nb = split(b, y, ".")
    n = (na > nb) ? na : nb
    for (i = 1; i <= n; i++) {
      xi = (i <= na) ? x[i] + 0 : 0
      yi = (i <= nb) ? y[i] + 0 : 0
      if (xi > yi) exit 0
      if (xi < yi) exit 1
    }
    exit 0
  }'
}

dr_premiere_ligne() { # dr_premiere_ligne <sortie> : 1re ligne sans caractère de contrôle, « sortie vide » sinon
  local l1
  l1="$(printf '%s\n' "$1" | sed -n 1p | LC_ALL=C tr -d '\000-\010\013-\037\177')"
  [ -z "$l1" ] && l1="sortie vide"
  printf '%s\n' "$l1"
}

dr_interprete() { # dr_interprete <interpréteurs a|b> : chemin du 1er trouvé qui répond rc 0 à --version, sur stdout ; rc 1 sinon
  local alt alts ip
  alts="${1//$_pipe/ }"
  set -f
  for alt in $alts; do
    if ip="$(dr_probe "$alt")" && "$ip" --version </dev/null >/dev/null 2>&1; then
      set +f
      printf '%s\n' "$ip"
      return 0
    fi
  done
  set +f
  return 1
}

dr_dans() { # dr_dans <jeton> <liste séparée par des espaces> : rc 0 si présent
  case " $2 " in
    *" $1 "*)
      return 0
      ;;
  esac
  return 1
}

dr_probe_module() { # dr_probe_module <module> <interpréteurs a|b> : pose M_IP (1er trouvé qui répond rc 0 à --version), M_RC, M_L1, M_OUT ; rc 0 si `<interpréteur> -m <module> --version` rend 0
  M_IP=""
  M_RC=""
  M_L1=""
  M_OUT=""
  M_IP="$(dr_interprete "$2")" || M_IP=""
  [ -n "$M_IP" ] || return 1
  M_OUT="$("$M_IP" -m "$1" --version </dev/null 2>&1)"
  M_RC=$?
  M_L1="$(dr_premiere_ligne "$M_OUT")"
  [ "$M_RC" -eq 0 ]
}

dr_version() { # dr_version <chemin> <contrainte> : exécute `<chemin> --version`, puis dr_version_lue
  local out rc
  out="$("$1" --version </dev/null 2>&1)"
  rc=$?
  dr_version_lue "$out" "$rc" "$2"
}

dr_version_lue() { # dr_version_lue <sortie> <rc> <contrainte> : pose V_ETAT (ok | ko | nm), V_VU, V_RC et V_L1
  local out num seuil contrainte
  out="$1"
  V_RC="$2"
  contrainte="$3"
  V_L1="$(dr_premiere_ligne "$out")"
  V_VU=""
  V_ETAT="nm"
  case "$contrainte" in
    ">="*)
      num="$(printf '%s\n' "$out" | grep -oE '[0-9]+([.][0-9]+)+' | sed -n 1p)"
      [ -z "$num" ] && return 0
      V_VU="$num"
      seuil="${contrainte#"$_ge"}"
      if dr_ge "$num" "$seuil"; then
        V_ETAT=ok
      else
        V_ETAT=ko
      fi
      ;;
    *)
      V_VU="$V_L1"
      case "$out" in
        *"$contrainte"*)
          V_ETAT=ok
          ;;
        *)
          V_ETAT=ko
          ;;
      esac
      ;;
  esac
  return 0
}

printf 'doctor — outils du poste et de la CI du kit (inventaire : %s)\n\n' "$INV"
printf 'Plateforme\n'
if [ -n "$OS" ]; then
  printf '  %s (%s)\n' "$OS" "$OS_NOTE"
else
  printf '  os inconnu (%s) — toutes les plateformes sondées\n' "$UNAME_S"
fi

# --- les modules du projet (en-tête, LES MODULES DU PROJET) -----------------
# Texte CONSTANT, valeurs en argv (dossier de la découverte, racine, borne) :
# rien n'y est interpolé. Sortie : UNE ligne `modules=<a,b>` (rc 0),
# `borne=<s>` (rc 3) ou `erreur=<type>` (rc 4). Le dossier de la découverte
# est AJOUTÉ en FIN de sys.path : un json.py ou re.py posé à côté de
# module_discovery.py ne masque pas la bibliothèque standard (cas 21g de
# doctor.test.sh).
DR_DECOUVERTE='import os, sys, threading
dossier, racine, delai = sys.argv[1], sys.argv[2], int(sys.argv[3])
res = {}
def lire():
    try:
        sys.path.append(dossier)
        import module_discovery
        trouves = module_discovery.discover(racine)
        fams = set()
        for rel, info in trouves.items():
            if rel.parts[:1] != (".agents",):
                fams |= set(info["families"])
        ordre = [f for f in module_discovery.FAMILIES if f in fams]
        if any(n.endswith(".tf") and os.path.isfile(os.path.join(racine, n)) for n in os.listdir(racine)):
            ordre.append("iac")
        res["familles"] = ordre
    except BaseException as exc:
        res["erreur"] = type(exc).__name__
fil = threading.Thread(target=lire, daemon=True)
fil.start()
fil.join(delai)
if fil.is_alive():
    print("borne=%d" % delai, flush=True)
    os._exit(3)
if "erreur" in res:
    print("erreur=" + res["erreur"], flush=True)
    os._exit(4)
print("modules=" + ",".join(res["familles"]), flush=True)
'
DR_KIT=0
[ -f "$ROOT/.agents/IS_THE_KIT" ] && DR_KIT=1
DR_DELAI=30
case "${DOCTOR_DISCOVERY_DELAI:-}" in
  "")
    ;;
  *[!0-9]*)
    printf 'doctor: DOCTOR_DISCOVERY_DELAI ignorée (un entier de secondes attendu) : borne de 30 s\n' >&2
    ;;
  *)
    DR_DELAI="$DOCTOR_DISCOVERY_DELAI"
    ;;
esac
DR_MODULES="illisible"
DR_MOD_NOTE=""
DR_MOD_ALTS=""
while IFS="$US" read -r _ tool nature os klass _ _ _ _ mode; do
  [ "$nature" = "outil" ] && [ "$mode" != "-" ] || continue
  dr_os_applies "$os" || continue
  DR_MOD_ALTS="${mode#"$_mod"}"
  break
done <<< "$DATA"
if [ -z "$DR_MOD_ALTS" ]; then
  DR_MOD_NOTE="aucune ligne outil en mode module: pour cette plateforme dans l inventaire : pas d interpréteur pour la découverte"
elif ! dr_ip="$(dr_interprete "$DR_MOD_ALTS")"; then
  DR_MOD_NOTE="aucun interpréteur $DR_MOD_ALTS qui réponde à --version dans le PATH de la sonde"
else
  dr_out="$("$dr_ip" -I -B -c "$DR_DECOUVERTE" "$ROOT/.agents/security" "$ROOT" "$DR_DELAI" </dev/null 2>/dev/null)"
  dr_rc=$?
  dr_l1="$(dr_premiere_ligne "$dr_out")"
  if [ "$dr_rc" -eq 0 ]; then
    case "$dr_l1" in
      modules=)
        DR_MODULES="aucun"
        ;;
      modules=*[!a-z,]*)
        DR_MOD_NOTE="sortie hors forme de $dr_ip : $dr_l1"
        ;;
      modules=*)
        DR_MODULES="${dr_l1#modules=}"
        ;;
      *)
        DR_MOD_NOTE="sortie hors forme de $dr_ip : $dr_l1"
        ;;
    esac
  elif [ "$dr_rc" -eq 3 ]; then
    DR_MOD_NOTE="découverte au-delà de la borne de $DR_DELAI s ($dr_ip)"
  else
    DR_MOD_NOTE="découverte en échec ($dr_ip, rc $dr_rc : $dr_l1)"
  fi
  [ "$DR_MODULES" != "illisible" ] && DR_MOD_NOTE="interpréteur $dr_ip, borne $DR_DELAI s"
fi
# LA RÈGLE DE CLASSE (en-tête) : par propriété — mode `module:` et aucune famille
# au nom d'une alternative d'interpréteur —, hors du kit, découverte lisible.
DR_HORS_B=""
DR_HORS_NOTE=""
if [ "$DR_KIT" -eq 0 ] && [ "$DR_MODULES" != "illisible" ]; then
  dr_fams="$(printf '%s' "$DR_MODULES" | tr ',' ' ')"
  while IFS="$US" read -r _ tool nature os klass _ _ _ _ mode; do
    [ "$nature" = "outil" ] && [ "$klass" = "B" ] && [ "$mode" != "-" ] || continue
    dr_os_applies "$os" || continue
    alts="${mode#"$_mod"}"
    alts="${alts//$_pipe/ }"
    dr_fam=""
    set -f
    for alt in $alts; do
      dr_dans "$alt" "$dr_fams" && dr_fam="$alt"
    done
    set +f
    [ -n "$dr_fam" ] && continue
    DR_HORS_B="${DR_HORS_B:+$DR_HORS_B }$tool"
    DR_HORS_NOTE="${DR_HORS_NOTE}doctor: hors classe B ici : $tool — hors du kit, aucun module dont la famille porte le nom de son interpréteur (${mode#"$_mod"}) : la porte adoptant ne le lance pas
"
  done <<< "$DATA"
fi

N=0
NB_PRES=0
NB_NA=0
NB_ABS=0
A_MANQ=0
B_MANQ=""
MV=""

for CLS in B A; do
  if [ "$CLS" = "B" ]; then
    printf '\nClasse B — absence : porte nue du kit ROUGE\n'
  else
    printf '\nClasse A — absence : annoncée (saut ou COVERAGE DEGRADED), porte verte\n'
  fi
  while IFS="$US" read -r _ tool nature os klass version cipin _ cost mode; do
    [ "$nature" = "outil" ] || continue
    # Hors classe B ici (LA RÈGLE DE CLASSE) : rangé, sondé et compté en classe A.
    dr_dans "$tool" "$DR_HORS_B" && klass=A
    [ "$klass" = "$CLS" ] || continue
    N=$((N + 1))
    if ! dr_os_applies "$os"; then
      NB_NA=$((NB_NA + 1))
      printf '  %-24s %s\n' "N/A (plateforme $os)" "$tool"
      continue
    fi
    trouve=""
    chemin=""
    note=""
    if [ "$mode" = "-" ]; then
      alts="${tool//$_pipe/ }"
      # Découpage SANS glob : la forme du jeton est déjà refusée à la lecture,
      # `set -f` ferme le second verrou (avis sécurité, S-00004475).
      set -f
      for alt in $alts; do
        if chemin="$(dr_probe "$alt")"; then
          trouve="$alt"
          break
        fi
      done
      set +f
    elif dr_probe_module "$tool" "${mode#"$_mod"}"; then
      # LE MODE DE SONDE (en-tête) : un module, lancé par son interpréteur.
      trouve="$tool"
      chemin="$M_IP -m $tool"
    elif [ -n "$M_IP" ]; then
      note=" — sonde module : $M_IP -m $tool --version, rc $M_RC : $M_L1"
    else
      note=" — sonde module : aucun interpréteur ${mode#"$_mod"} qui réponde à --version dans le PATH de la sonde"
    fi
    if [ -z "$trouve" ]; then
      NB_ABS=$((NB_ABS + 1))
      if [ "$CLS" = "B" ]; then
        etat="ABSENT (requis)"
        B_MANQ="${B_MANQ:+$B_MANQ }$tool"
      else
        etat="ABSENT (optionnel)"
        A_MANQ=$((A_MANQ + 1))
      fi
      att="$version"
      [ "$att" = "-" ] && att="aucune contrainte écrite"
      pin=""
      [ "$cipin" != "-" ] && pin=" ; pin CI : $cipin"
      printf '  %-24s %s — version attendue : %s%s — coût : %s%s\n' "$etat" "$tool" "$att" "$pin" "$cost" "$note"
      continue
    fi
    NB_PRES=$((NB_PRES + 1))
    lib="PRESENT"
    [ "$trouve" != "$tool" ] && lib="PRESENT ($trouve)"
    if [ "$version" = "-" ]; then
      printf '  %-24s %s — %s\n' "$lib" "$tool" "$chemin"
      continue
    fi
    if [ "$mode" = "-" ]; then
      dr_version "$chemin" "$version"
    else
      dr_version_lue "$M_OUT" "$M_RC" "$version"
    fi
    case "$V_ETAT" in
      ok)
        printf '  %-24s %s — %s — version %s, attendue %s\n' "$lib" "$tool" "$chemin" "$V_VU" "$version"
        ;;
      ko)
        MV="${MV:+$MV }$tool"
        printf '  %-24s %s — %s — version %s, attendue %s — coût : %s\n' "MAUVAISE VERSION" "$tool" "$chemin" "$V_VU" "$version" "$cost"
        ;;
      *)
        printf '  %-24s %s — %s — version non mesurée (--version rc %s : %s), attendue %s\n' "$lib" "$tool" "$chemin" "$V_RC" "$V_L1" "$version"
        ;;
    esac
  done <<< "$DATA"
done

NB_COND=0
CONDS=""
while IFS="$US" read -r _ tool nature _; do
  [ "$nature" = "condition" ] || continue
  NB_COND=$((NB_COND + 1))
  CONDS="${CONDS:+$CONDS }$tool"
done <<< "$DATA"
printf '\nConditions — jamais sondées par ce script : %s (%s)\n' "${CONDS:-aucune}" "$NB_COND"

if [ "$OS" = "windows" ]; then
  printf "\nWindows : rapport non mesuré — la jambe windows-latest de la CI joue les suites, pas ce rapport (en-tête de l'inventaire)\n"
fi

# --- canal apt de la CI ------------------------------------------------------
dr_strip() { sed -E 's/^[[:space:]]*#.*$//' "$1"; }

printf '\nCanal apt de la CI (seaux appariés par la colonne apt)\n'
CI_RC=0
CI_APT=""
if [ -f "$CI_FILE" ]; then
  CI_APT="$(dr_strip "$CI_FILE" | sed -n -E 's/^[[:space:]]*(sudo[[:space:]]+)?apt-get[[:space:]]+install[[:space:]]+-y[[:space:]]+(.+)$/\2/p' | sed -n 1p)"
fi
RUNNER=""
RUNNER_OK=0
if [ -f "$VERIFY_FILE" ]; then
  RUNNER="$(dr_strip "$VERIFY_FILE" | sed -n -E 's/^[[:space:]]*RUNNER_PREINSTALLED="([^"]*)".*$/\1/p' | sed -n 1p)"
  # `grep -c`, jamais `-q` : sous pipefail, un `-q` qui sort tôt tue dr_strip (SIGPIPE).
  [ "$(dr_strip "$VERIFY_FILE" | grep -cE '^[[:space:]]*RUNNER_PREINSTALLED="')" -ge 1 ] && RUNNER_OK=1
fi
if [ -z "$CI_APT" ]; then
  if [ -f "$CI_FILE" ]; then
    printf '  CI : non dérivable (aucune ligne apt-get install -y dans %s)\n' "$CI_FILE"
  else
    printf '  CI : non dérivable (%s absent)\n' "$CI_FILE"
  fi
  [ "$CI_EXPLICIT" -eq 1 ] && CI_RC=1
else
  printf '%s\n' "$DATA" | awk -F"$US" -v ci="$CI_APT" -v run="$RUNNER" -v runok="$RUNNER_OK" '
    $3 == "outil" && $8 != "-" {
      if (!($8 in outils)) { ord[++no] = $8; outils[$8] = $2 } else outils[$8] = outils[$8] "," $2
    }
    $3 == "outil" && $7 != "-" { pins = pins " " $2 }
    END {
      nci = split(ci, c, " "); nr = split(run, r, " ")
      for (i = 1; i <= nci; i++) inci[c[i]] = 1
      for (i = 1; i <= nr; i++) inrun[r[i]] = 1
      for (i = 1; i <= nci; i++) {
        p = c[i]
        if (p in outils) s1 = s1 " " p " (" outils[p] ")"; else s3 = s3 " " p
      }
      for (k = 1; k <= no; k++) {
        p = ord[k]
        if (!(p in inci) && !(p in inrun)) s2 = s2 " " p " (" outils[p] ")"
      }
      for (i = 1; i <= nr; i++) if (!(r[i] in outils)) s4 = s4 " " r[i]
      print "  seau 1 — installés par la ligne apt de la CI ET inventoriés :" (s1 == "" ? " aucun" : s1)
      if (runok) print "  seau 2 — paquets inventoriés que ni la ligne apt ni le runner ne fournissent :" (s2 == "" ? " aucun" : s2)
      else print "  seau 2 — non dérivable : préinstallés runner inconnus (porte absente ou sans ligne RUNNER_PREINSTALLED)"
      print "  seau 3 — installés par la ligne apt, NON inventoriés :" (s3 == "" ? " aucun" : s3)
      if (runok) print "  préinstallés runner (RUNNER_PREINSTALLED), non inventoriés :" (s4 == "" ? " aucun" : s4)
      else print "  préinstallés runner : non dérivable (porte absente ou sans ligne RUNNER_PREINSTALLED)"
      print "  épinglés par la colonne ci_pin, apt ou non (déclaré, non dérivé ; colonne brew non citée) :" (pins == "" ? " aucun" : pins)
    }'
fi

RC=0
[ -n "$B_MANQ" ] && RC=1
if [ "$CI_RC" -eq 1 ]; then
  RC=1
  printf 'doctor: --ci explicite et canal apt non dérivable : %s\n' "$CI_FILE" >&2
fi
# LES MODULES DU PROJET (en-tête) : AVANT le résumé, jamais « présents, ».
printf '\nModules du projet (discover() de .agents/security, la découverte de la porte adoptant)\n'
if [ "$DR_MODULES" = "illisible" ]; then
  printf '  illisible — %s ; les classes de l inventaire restent\n' "$DR_MOD_NOTE"
else
  printf '  %s — %s\n' "$DR_MODULES" "$DR_MOD_NOTE"
fi
if [ "$DR_KIT" -eq 1 ]; then
  printf '  arbre du kit (.agents/IS_THE_KIT) : classes de l inventaire inchangées\n'
fi
printf 'doctor: modules : %s\n' "$DR_MODULES"
printf '%s' "$DR_HORS_NOTE"
printf '\ndoctor: %s/%s présents, %s N/A, %s absents (B manquants=%s, A manquants=%s), mauvaise version=%s, %s conditions non sondées — exit %s\n' \
  "$NB_PRES" "$N" "$NB_NA" "$NB_ABS" "${B_MANQ:-aucun}" "$A_MANQ" "${MV:-aucune}" "$NB_COND" "$RC"
exit "$RC"
