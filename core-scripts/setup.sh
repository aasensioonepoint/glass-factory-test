#!/usr/bin/env bash
# ============================================================================
# core-scripts/setup.sh — INSTALLE LES PRÉREQUIS DU KIT, macOS ET UBUNTU.
# L'étape 2 « Équipe ton poste » de docs/usage.html (T-01M4WHQQHHGFS6NPSFQ9TSM36V). Windows :
# core-scripts/setup.ps1.
#
# USAGE
#   bash core-scripts/setup.sh [--dry-run] [--inventory <tsv>]
#     --dry-run    dit ce qu'il ferait ; n'installe RIEN, n'écrit rien
#     --inventory  autre inventaire (défaut : core-scripts/tool-inventory.tsv) — bancs
#   SETUP_OS=darwin|linux|<autre>   impose la plateforme (sinon `uname -s`) — bancs
#   SETUP_PROBE_PATH=<PATH>         PATH où sont cherchés les outils, le gestionnaire
#                                   et sudo (défaut : $PATH) ; les bancs y posent des
#                                   bouchons, aucune installation réelle n'y passe
#   SETUP_DOCTOR=<chemin>           autre doctor.sh (défaut : core-scripts/doctor.sh) — bancs
#   SETUP_PROBE_PATH et SETUP_DOCTOR sont RÉSERVÉS AUX BANCS : ne les posez pas à
#   la main, ne les laissez pas dans un profil. Le premier décide QUELS `brew`,
#   `apt-get` et `sudo` sont lancés, le second fait EXÉCUTER un autre script :
#   posés par un tiers, ils feraient lancer autre chose que le gestionnaire du
#   système. La ligne « Plateforme : … gestionnaire : … (<chemin>) » montre d'où
#   vient le gestionnaire retenu — relisez-la avant de taper un mot de passe.
#
# CE QU'IL INSTALLE — DÉRIVÉ DE L'INVENTAIRE, JAMAIS D'UNE LISTE ÉCRITE ICI.
#   Les lignes `nature=outil`, `class=B` de core-scripts/tool-inventory.tsv dont
#   la colonne `os` vaut pour cette plateforme : ce sans quoi la vérification du
#   kit (core-scripts/verify.sh) ne tourne pas. À l'inventaire relevé le
#   2026-10-06 : git >= 2.34, bash >= 4, python3 >= 3.11, pytest, tee. Dans
#   l'arbre du kit (.agents/IS_THE_KIT), rien d'autre : les outils de classe A
#   (scanners, stacks, services) ne sont PAS installés — core-scripts/doctor.sh
#   (l'étape 2) dit ce que chacun coûte.
#   HORS DU KIT (T-01M5VYNMZPG8G0JZG48HV4K0PN ; décision pilote
#   S-01M5W3ZT0G274JQM72E2TC02GF, option A) — deux écarts, lus dans le doctor :
#   - un outil que le doctor dit `doctor: hors classe B ici : <outil> — …`
#     (pytest sans module python, en-tête de doctor.sh, LES MODULES DU PROJET)
#     n'est PAS requis : ni planifié, ni compté « déjà là » ;
#   - les SCANNERS DE SÉCURITÉ sont planifiés PAR DÉFAUT quand le doctor les dit
#     ABSENT en classe A : gitleaks et semgrep toujours, puis l'outil de chaque
#     famille de `doctor: modules` — python → pip-audit, npm → npm,
#     java|swift → dependency-check, iac → trivy ; modules illisibles : les
#     deux premiers seuls. macOS : leurs noms brew sont la table DÉCLARÉE
#     SP_SCANNERS_DARWIN (npm → node), dans la MÊME ligne `brew install --` que
#     la classe B ; dependency-check tire un JDK (openjdk, plusieurs centaines
#     de Mo), ANNONCÉ avant la commande ; brew pose le semgrep de homebrew/core,
#     pas l'épingle de la CI (écart dit). Ubuntu : semgrep==<ci_pin de
#     l'inventaire> et pip-audit par pipx s'il est là — la version extraite de
#     la cellule est validée ([0-9][0-9.]*, sinon REFUSÉE, nommée, rien passé à
#     pipx), et `pipx install` n'est PAS épinglé par empreinte, c'est dit ; un
#     pipx planifié fait dire ~/.local/bin et `pipx ensurepath` (sans pipx :
#     « pipx introuvable », les deux à installer soi-même) ; npm
#     par la colonne apt de l'inventaire, dans la commande apt-get ; gitleaks,
#     trivy et dependency-check nommés « à installer vous-même » avec leur
#     section de README-SECURITY-SCAN-SETUP.md. Après installation, le doctor
#     re-sonde : un scanner encore ABSENT est « manque encore », et le code est 1.
#
# PAR QUEL CANAL — LE GESTIONNAIRE DU SYSTÈME, ET LUI SEUL.
#   macOS : brew (Homebrew). Ubuntu, Debian : apt-get, sous sudo, ANNONCÉ avant
#   d'être lancé (jamais quand on est déjà root). Windows : REFUSÉ (code 2),
#   c'est core-scripts/setup.ps1. Autre plateforme : refusé (2).
#   Jamais `curl | sh`, jamais un installateur téléchargé, jamais une élévation
#   silencieuse. Homebrew absent : le script s'arrête (2) et renvoie à
#   https://brew.sh — à faire soi-même.
#   LE NOM DU PAQUET : la colonne `brew` ou `apt` de l'inventaire quand elle est
#   remplie (c'est ce que la CI du kit installe), sinon la table `sp_paquet`
#   ci-dessous — DÉCLARÉE, pas dérivée. Les noms brew sont ceux de homebrew/core
#   (relevés sur ce poste, 2026-10-14) ; les noms apt sont ceux des dépôts
#   Ubuntu, NON exécutés ici. Un outil sans paquet connu est rapporté « manque
#   encore » avec rien d'inventé. tee sur macOS : AUCUN paquet brew — /usr/bin/tee
#   est livré par le système, et le coreutils de Homebrew pose `gtee`, pas `tee` ;
#   absent, il est rapporté « manque encore », à installer soi-même.
#   LA CELLULE EST VALIDÉE avant d'atteindre le gestionnaire : un nom de paquet,
#   `[A-Za-z0-9@._+-]` seulement, jamais un `-` en tête — une cellule
#   `-oDpkg::Pre-Invoke::=…` passée à `sudo apt-get install` exécuterait ce
#   qu'elle veut. Refusée, elle est dite sur stderr (caractères de contrôle
#   remplacés par `?`) et l'outil passe « sans
#   paquet connu » ; rien n'est passé au gestionnaire. Et la liste des paquets
#   suit un `--`, fin des options pour brew comme pour apt-get (vérifié le
#   2026-10-14 : `brew install -n -- git` ; apt-pkg/contrib/cmndline.cc).
#
# CE QU'IL FAIT, DANS CET ORDRE
#   0. agent : un marqueur d'agent posé (valeur non blanche) et pas --dry-run
#      ⇒ REFUS (code 7), qui nomme le marqueur trouvé. Les marqueurs, lus dans
#      cet ordre : CLAUDECODE et CLAUDE_CODE_ENTRYPOINT (Claude Code, shell de
#      l'agent), AGENTS_HOOK_HOST (posé par les configs de hooks du kit, dans
#      les SOUS-PROCESSUS DE HOOK seulement, jamais dans le shell de l'agent),
#      COPILOT_AGENT_SESSION_ID et COPILOT_CLI (shell de l'agent Copilot CLI,
#      mesurés en 1.0.96) — la liste de .agents/bin/skills_github_fallback.py
#      (AGENT_CALLER_MARKERS). Ce script modifie le poste : il se lance à la
#      main, dans un terminal. C'est une GARDE, pas une frontière : elle freine,
#      elle ne ferme pas ; `env -u <marqueur>` la défait (le banc le fait) ;
#      elle empêche d'oublier, pas de tricher. FAUX NÉGATIF NOMMÉ : Codex,
#      Gemini et Kimi n'exposent aucun marqueur mesuré dans le shell de l'agent
#      (AGENTS_HOOK_HOST n'y est pas) : lancé depuis LEUR shell d'agent, ce
#      script n'est pas refusé.
#      Borne : COPILOT_CLI est hérité par un shell lancé depuis Copilot CLI
#      (échappement `!` compris) — faux positif assumé : lancez depuis un
#      terminal ouvert hors de Copilot CLI ;
#   1. plateforme, puis gestionnaire (cherché dans SETUP_PROBE_PATH) ;
#   2. AVANT : core-scripts/doctor.sh sonde l'inventaire (même PATH de sonde, même
#      inventaire). Ce script ne porte AUCUNE sonde d'outil à lui (exceptions :
#      la sonde python du pilote, étape 6, et celle de pipx sous Ubuntu) : il lit
#      la ligne de résumé du doctor (`B manquants=`, `mauvaise version=`), ses
#      lignes `doctor: modules :` et `doctor: hors classe B ici :`, et, hors du
#      kit, la ligne de classe A de chaque scanner (PRESENT / ABSENT) ;
#   3. plan : un paquet par outil de classe B absent ou en mauvaise version,
#      plus, hors du kit, chaque scanner ABSENT (ci-dessus) — un outil présent
#      à la bonne version n'entre PAS dans le plan, et c'est
#      cela l'idempotence : relancer ne réinstalle rien ;
#   4. --dry-run : le plan, la commande qui serait lancée, et pour chaque outil
#      SANS paquet sa note (macOS : la commande pip de pytest), puis la sortie ;
#      sinon UNE commande du gestionnaire, affichée avant d'être lancée, à qui
#      l'on passe tous les paquets du plan ;
#   5. APRÈS : le doctor re-sonde ; trois listes — installés (absents ou en
#      mauvaise version avant, présents après), déjà là, manque encore (avec la
#      ligne du doctor et la commande à taper) ; puis UNE ligne de résumé :
#        setup: installés=… déjà là=… manque encore=… — exit N
#   6. juste avant la ligne de résumé : pilote de fusion — python ≥ 3.11 (1er
#      de python3|python|py), --verifier ; non installé et stdin terminal :
#      question [o/N], seuls o/oui lancent --installer (--depuis origin/develop
#      dans le kit sur develop) puis --verifier ; --dry-run, marqueur d'agent,
#      non-terminal : rien armé, dit ; le code de sortie n'en dépend jamais ;
#      une sortie 2 ne l'atteint pas.
#
# CE QU'IL NE PROMET PAS — dit plutôt que découvert.
#   - une version qu'apt n'a pas : Ubuntu 22.04 livre python3 3.10 < 3.11 ;
#     après `apt-get install`, le doctor dit encore MAUVAISE VERSION, le script
#     sort 1 et nomme python.org — jamais un PPA, jamais un `curl | sh` ;
#   - un PATH réordonné : brew pose bash sous `$(brew --prefix)/bin` ; si /bin
#     passe avant dans le PATH, le doctor voit toujours 3.2 — le script le dit,
#     il ne prétend pas avoir réussi ;
#   - la sonde du doctor pour pytest : en MODULE (`mode_sonde` de l'inventaire,
#     `module:python3|python|py`), `<python> -m pytest --version` sur le PREMIER
#     python trouvé QUI RÉPOND à `--version`, la règle de la porte — un binaire `pytest` sur le
#     PATH (la formule brew, dans son virtualenv) ne compte plus, et pytest
#     installé pour un AUTRE python que celui-là reste « manque encore » (en-tête
#     de doctor.sh, LE MODE DE SONDE ; cas 19 de doctor.test.sh) ;
#   - pytest sur macOS : AUCUN paquet brew. La formule `pytest` de Homebrew
#     s'installe dans son propre virtualenv (sous python@3.15), invisible du
#     python3 que la porte lance (`python3 -m pytest`, run-pytest-shards.sh) :
#     le script dirait « installé », puis la porte échouerait sur « No module
#     named pytest ». Absent sur macOS, pytest est donc « manque encore », avec
#     la commande pip (ou venv) à taper — l'épingle est celle de la CI du kit.
#
# EXIT
#   0  tous les outils de classe B de la plateforme sont présents — déjà là, ou
#      installés par ce passage ; en --dry-run : rien à installer
#   1  il manque encore quelque chose après l'installation (paquet inconnu,
#      gestionnaire en échec, sudo absent, version restée basse) ; en
#      --dry-run : il y a quelque chose à installer
#   2  usage ; plateforme non prise en charge (Windows → setup.ps1) ;
#      gestionnaire absent (brew, apt-get) ; inventaire ou doctor illisible
#   7  lancé par un agent (marqueur d'agent posé, étape 0) sans --dry-run :
#      rien n'est fait
#
# FORME : bash 3.2, celui que macOS livre — c'est CE script qui installe bash
# >= 4 : ni tableau, ni `mapfile`, ni `${x,,}` ; `set -uo pipefail` ; aucune des
# huit formes que le SAST ne lit pas (.agents/ref/CONVENTIONS_shell.md).
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

INV="$ROOT/core-scripts/tool-inventory.tsv"
DOCTOR="${SETUP_DOCTOR:-$ROOT/core-scripts/doctor.sh}"
DRY=0
US=$'\037'
_pipe='|'

sp_usage() {
  printf '%s\n' 'usage: setup.sh [--dry-run] [--inventory <tsv>]'
}
sp_dire() { printf 'setup: %s\n' "$1"; }
sp_refus() { printf 'setup: %s\n' "$1" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY=1
      shift
      ;;
    --inventory)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        sp_refus '--inventory attend un fichier'
        sp_usage >&2
        exit 2
      fi
      INV="$2"
      shift 2
      ;;
    -h|--help)
      sp_usage
      exit 0
      ;;
    *)
      sp_refus "argument inconnu : $1"
      sp_usage >&2
      exit 2
      ;;
  esac
done

# --- (0) jamais sous un agent quand le poste va être modifié -----------------
# Un marqueur fait de blancs vaut ABSENT (doctrine de skills_github_fallback.py).
# Blancs = espace, \t, \r, \n, \v, \f : les blancs ASCII que setup.ps1
# (IsNullOrWhiteSpace) ôte aussi ; borne : les blancs Unicode (U+00A0…), que
# IsNullOrWhiteSpace ôte, comptent ici comme posés (refus, jamais un passage).
# AGENT porte le NOM du premier marqueur posé (en-tête, étape 0), vide sinon.
# Borne : COPILOT_CLI est hérité d'un shell lancé depuis Copilot CLI — faux
# positif assumé, le remède est un terminal ouvert hors de Copilot CLI.
sp_pose() { [ -n "$(printf '%s' "$1" | tr -d ' \t\r\n\v\f')" ]; }
AGENT=""
if sp_pose "${CLAUDECODE:-}"; then
  AGENT=CLAUDECODE
elif sp_pose "${CLAUDE_CODE_ENTRYPOINT:-}"; then
  AGENT=CLAUDE_CODE_ENTRYPOINT
elif sp_pose "${AGENTS_HOOK_HOST:-}"; then
  AGENT=AGENTS_HOOK_HOST
elif sp_pose "${COPILOT_AGENT_SESSION_ID:-}"; then
  AGENT=COPILOT_AGENT_SESSION_ID
elif sp_pose "${COPILOT_CLI:-}"; then
  AGENT=COPILOT_CLI
fi
if [ -n "$AGENT" ] && [ "$DRY" -eq 0 ]; then
  sp_refus "a lancer par vous-meme dans un terminal, pas par un agent : ce script installe des paquets sur le poste ($AGENT est pose ici)."
  sp_refus 'Rien n a ete fait. --dry-run reste permis.'
  sp_refus "pilote de fusion non proposé sous $AGENT ; rien armé."
  exit 7
fi

# --- (1) plateforme et gestionnaire ------------------------------------------
OS=""
OS_NOTE=""
if [ -n "${SETUP_OS:-}" ]; then
  OS="$SETUP_OS"
  OS_NOTE="imposée par SETUP_OS"
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
    *)
      OS="${UNAME_S:-inconnu}"
      ;;
  esac
  OS_NOTE="uname -s : $UNAME_S"
fi

PROBE_PATH="${SETUP_PROBE_PATH:-$PATH}"

sp_probe() { # sp_probe <nom> : chemin sur stdout, rc 0 si trouvé ET exécutable (la sonde de doctor.sh)
  local p
  p="$( PATH="$PROBE_PATH"; type -P "$1" 2>/dev/null )" || return 1
  [ -x "$p" ] || return 1
  printf '%s\n' "$p"
}

GESTIONNAIRE=""
case "$OS" in
  darwin)
    GESTIONNAIRE=brew
    ;;
  linux)
    GESTIONNAIRE=apt
    ;;
  windows)
    sp_refus 'Windows : ce script ne s y lance pas. Dans PowerShell : powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1'
    exit 2
    ;;
  *)
    sp_refus "plateforme non prise en charge : $OS ($OS_NOTE) — macOS (brew) et Ubuntu (apt) seulement ; Windows : core-scripts/setup.ps1"
    exit 2
    ;;
esac

GEST_BIN=""
if [ "$GESTIONNAIRE" = brew ]; then
  GEST_BIN="$(sp_probe brew)" || GEST_BIN=""
  if [ -z "$GEST_BIN" ]; then
    sp_refus 'Homebrew (brew) introuvable dans le PATH. Installez-le vous-meme depuis https://brew.sh (ce script ne lance jamais un installateur telecharge), puis relancez.'
    exit 2
  fi
else
  GEST_BIN="$(sp_probe apt-get)" || GEST_BIN=""
  if [ -z "$GEST_BIN" ]; then
    sp_refus 'apt-get introuvable dans le PATH : seules les distributions a apt (Ubuntu, Debian) sont prises en charge.'
    exit 2
  fi
fi

if [ ! -f "$INV" ] || [ ! -r "$INV" ]; then
  sp_refus "inventaire illisible : $INV"
  exit 2
fi
if [ ! -f "$DOCTOR" ] || [ ! -r "$DOCTOR" ]; then
  sp_refus "doctor illisible : $DOCTOR"
  exit 2
fi

TMP="$(mktemp -d 2>/dev/null)" || { sp_refus 'mktemp impossible'; exit 2; }
trap 'rm -rf "$TMP"' EXIT

# --- la sonde : le doctor, et sa seule ligne de résumé -----------------------
D_BMANQ=""
D_MV=""
D_MODULES=""
D_HORS_B=""
sp_doctor() { # sp_doctor <sortie> : pose D_BMANQ, D_MV, D_MODULES (familles a,b | aucun | illisible) et D_HORS_B ; rc 1 si le doctor n'a pas rendu de résumé
  local resume
  env "DOCTOR_OS=$OS" "DOCTOR_PROBE_PATH=$PROBE_PATH" bash "$DOCTOR" --inventory "$INV" > "$1" 2>&1
  resume="$(grep '^doctor: .* présents, ' "$1" | sed -n '$p')"
  [ -n "$resume" ] || return 1
  D_BMANQ="$(printf '%s\n' "$resume" | sed -n 's/^.*(B manquants=\([^,]*\), A manquants=.*$/\1/p')"
  D_MV="$(printf '%s\n' "$resume" | sed -n 's/^.*mauvaise version=\([^,]*\),.*$/\1/p')"
  [ "$D_BMANQ" = "aucun" ] && D_BMANQ=""
  [ "$D_MV" = "aucune" ] && D_MV=""
  # Les deux lignes de LES MODULES DU PROJET (en-tête de doctor.sh). Absente ou
  # hors forme : « illisible », et seuls gitleaks et semgrep sont planifiés.
  D_MODULES="$(sed -n 's/^doctor: modules : //p' "$1" | sed -n '$p')"
  case "$D_MODULES" in
    ""|*[!a-z,]*)
      D_MODULES="illisible"
      ;;
  esac
  D_HORS_B="$(sed -n 's/^doctor: hors classe B ici : \([^ ]*\) — .*$/\1/p' "$1" | tr '\n' ' ' | sed 's/ *$//')"
  return 0
}

# LES SCANNERS HORS DU KIT (en-tête, CE QU'IL INSTALLE). Deux tables DÉCLARÉES,
# alignées rang par rang : l'outil tel que le doctor le nomme, et son paquet
# brew. Rangs : 1 gitleaks et 2 semgrep toujours ; 3 famille python ; 4 npm ;
# 5 java ou swift ; 6 iac. La ligne SP_SCANNERS_DARWIN est un CONTRAT (plan
# T-01M5VYNMZPG8G0JZG48HV4K0PN, C17) : une seule, entre apostrophes, en
# colonne 0 — le témoin de parité du bilan la relit telle quelle.
SP_SCANNERS_DARWIN='gitleaks semgrep pip-audit node dependency-check trivy'
SP_SCANNERS_OUTILS='gitleaks semgrep pip-audit npm dependency-check trivy'

sp_mot() { # sp_mot <rang> <liste> : le mot de ce rang, rc 1 s'il n'y en a pas
  local i=0 m
  set -f
  for m in $2; do
    i=$((i + 1))
    if [ "$i" -eq "$1" ]; then
      set +f
      printf '%s\n' "$m"
      return 0
    fi
  done
  set +f
  return 1
}

sp_brew_de() { # sp_brew_de <outil> : son paquet brew, lu au même rang de SP_SCANNERS_DARWIN ; rc 1 hors table
  local i=0 m
  set -f
  for m in $SP_SCANNERS_OUTILS; do
    i=$((i + 1))
    if [ "$m" = "$1" ]; then
      set +f
      sp_mot "$i" "$SP_SCANNERS_DARWIN"
      return
    fi
  done
  set +f
  return 1
}

sp_rangs() { # sp_rangs <familles a,b | aucun | illisible> : les rangs des scanners à considérer
  local fams r
  fams="$(printf '%s' "$1" | tr ',' ' ')"
  r="1 2"
  sp_dans python "$fams" && r="$r 3"
  sp_dans npm "$fams" && r="$r 4"
  if sp_dans java "$fams" || sp_dans swift "$fams"; then
    r="$r 5"
  fi
  sp_dans iac "$fams" && r="$r 6"
  printf '%s\n' "$r"
}

sp_ligne_a() { # sp_ligne_a <sortie du doctor> <outil> <PRESENT|ABSENT> : rc 0 si le doctor rapporte l'outil dans cet état
  local motif='^  PRESENT'
  [ "$3" = "ABSENT" ] && motif='^  ABSENT (optionnel) '
  # `grep -c`, jamais `-q` en bout de tube : sous pipefail, un `-q` qui sort tôt
  # tue le premier grep (SIGPIPE) et rend un faux « non ».
  [ "$(grep -F -- " $2 — " "$1" | grep -c "$motif")" -ge 1 ]
}

sp_cellule() { # sp_cellule <outil> <colonne> : la cellule de l'inventaire (lue par nom de colonne), vide sinon
  awk -F'\t' -v t="$1" -v k="$2" '
    { sub(/\r$/, "") }
    /^#/ { next }
    !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
    (k in c) && $c["tool"] == t { print $c[k]; exit }
  ' "$INV"
}

sp_version_pin() { # sp_version_pin <outil> : la version de sa cellule ci_pin (`1.175.0@pip-hash(…)`), VALIDÉE ; sinon refus sur stderr, rc 1
  local pin ver
  pin="$(sp_cellule "$1" ci_pin)"
  ver="${pin%%@*}"
  # C16 : seule la forme [0-9][0-9.]* atteint pipx ; un motif par ligne, sans
  # antislash dans la classe (CONVENTIONS_shell.md, formes 6 et 8).
  case "$ver" in
    ""|[!0-9]*|*[!0-9.]*)
      sp_refus "inventaire : ci_pin de $1 REFUSÉ, la version n est pas de la forme [0-9][0-9.]* : « $(printf '%s' "$pin" | LC_ALL=C tr '\001-\037\177' '?') » — rien n est passé à pipx"
      return 1
      ;;
  esac
  printf '%s\n' "$ver"
}

sp_scanner_main() { # sp_scanner_main <outil> : la voie à taper soi-même (Ubuntu), une ligne
  case "$1" in
    gitleaks)
      printf '%s\n' 'README-SECURITY-SCAN-SETUP.md § Secrets scan (gitleaks)'
      ;;
    semgrep)
      if [ -n "$SC_SEMGREP_PIPX" ]; then
        printf '%s\n' "pipx install $SC_SEMGREP_PIPX — README-SECURITY-SCAN-SETUP.md § SAST scan (semgrep)"
      else
        printf '%s\n' 'README-SECURITY-SCAN-SETUP.md § SAST scan (semgrep)'
      fi
      ;;
    pip-audit)
      printf '%s\n' 'pipx install pip-audit — README-SECURITY-SCAN-SETUP.md § Python dependency scan (pip-audit)'
      ;;
    npm)
      printf '%s\n' 'le paquet apt de la colonne apt de l inventaire, ou https://nodejs.org/'
      ;;
    dependency-check)
      printf '%s\n' 'README-SECURITY-SCAN-SETUP.md § Per-ecosystem requirements, puis § The NVD API key'
      ;;
    trivy)
      printf '%s\n' 'README-SECURITY-SCAN-SETUP.md § IaC misconfiguration scan (trivy)'
      ;;
  esac
}

sp_dans() { # sp_dans <jeton> <liste séparée par des espaces> : rc 0 si présent
  case " $2 " in
    *" $1 "*)
      return 0
      ;;
  esac
  return 1
}

sp_os_applies() { # sp_os_applies <cellule os>
  [ "$1" = "any" ] && return 0
  case ",$1," in
    *",$OS,"*)
      return 0
      ;;
  esac
  return 1
}

# LA TABLE DES PAQUETS — déclarée (en-tête). Le jeton est la PREMIÈRE
# alternative de la colonne `tool` ; la colonne apt/brew de l'inventaire,
# quand elle est remplie, gagne sur cette table.
sp_paquet() { # sp_paquet <jeton> <colonne apt> <colonne brew> : paquet pour $GESTIONNAIRE sur stdout, rc 0 ; vide : rc 1 inconnu, rc 3 cellule REFUSÉE (dite sur stderr)
  local col premier outil_vu
  if [ "$GESTIONNAIRE" = brew ]; then
    col="$3"
  else
    col="$2"
  fi
  if [ -n "$col" ] && [ "$col" != "-" ]; then
    # La cellule vient d'un fichier : UN nom de paquet, rien qui ressemble à une
    # option (`-o…` sous `sudo apt-get` exécute ce qu'on lui dit), rien hors de
    # [A-Za-z0-9@._+-]. Un motif par ligne (CONVENTIONS_shell.md, forme 6) ; pas
    # d'antislash dans la classe (forme 8). L'outil (cellule `tool`, du même
    # fichier) ET la cellule refusée sont cités avec leurs caractères de
    # contrôle remplacés par `?` (comme sp_version_pin) : un échappement
    # terminal venu du fichier n'atteint pas stderr.
    outil_vu="$(printf '%s' "$1" | LC_ALL=C tr '\001-\037\177' '?')"
    case "$col" in
      -*)
        sp_refus "inventaire : cellule $GESTIONNAIRE de « $outil_vu » REFUSÉE, elle commence par un tiret (une option, pas un paquet) : « $(printf '%s' "$col" | LC_ALL=C tr '\001-\037\177' '?') »"
        return 3
        ;;
      *[!A-Za-z0-9@._+-]*)
        sp_refus "inventaire : cellule $GESTIONNAIRE de « $outil_vu » REFUSÉE, un nom de paquet n a que [A-Za-z0-9@._+-] : « $(printf '%s' "$col" | LC_ALL=C tr '\001-\037\177' '?') »"
        return 3
        ;;
    esac
    printf '%s\n' "$col"
    return 0
  fi
  premier="${1%%"$_pipe"*}"
  # brew,tee n'y est PAS : le coreutils de Homebrew pose gtee, jamais tee.
  # brew,pytest n'y est PAS : la formule s'installe dans son propre virtualenv
  # (python@3.15), invisible de `python3 -m pytest` que la porte lance ; voir
  # sp_conseil pour la commande pip.
  case "$GESTIONNAIRE,$premier" in
    brew,git)
      printf 'git\n'
      ;;
    brew,bash)
      printf 'bash\n'
      ;;
    brew,python3)
      printf 'python\n'
      ;;
    apt,git)
      printf 'git\n'
      ;;
    apt,bash)
      printf 'bash\n'
      ;;
    apt,python3)
      printf 'python3\n'
      ;;
    apt,pytest)
      printf 'python3-pytest\n'
      ;;
    apt,tee)
      printf 'coreutils\n'
      ;;
    *)
      return 1
      ;;
  esac
}

sp_conseil() { # sp_conseil <jeton> : ce que le gestionnaire ne peut pas faire seul (une ligne, ou rien)
  local premier
  premier="${1%%"$_pipe"*}"
  case "$GESTIONNAIRE,$premier" in
    brew,bash)
      printf '%s\n' "brew pose bash sous $("$GEST_BIN" --prefix 2>/dev/null)/bin : ouvrez un nouveau terminal, ou mettez ce dossier en tete de PATH"
      ;;
    apt,python3)
      printf '%s\n' 'si apt ne livre pas python3 >= 3.11 (Ubuntu 22.04 : 3.10), installez-le depuis https://www.python.org/downloads/ -- jamais un PPA ni un curl | sh'
      ;;
    brew,python3)
      printf '%s\n' "brew pose python3 sous $("$GEST_BIN" --prefix 2>/dev/null)/bin : ouvrez un nouveau terminal, ou mettez ce dossier en tete de PATH"
      ;;
    brew,pytest)
      printf '%s\n' 'la porte lance python3 -m pytest : python3 -m pip install --user pytest==9.1.1 (si pip refuse — PEP 668, python de Homebrew —, un venv : python3 -m venv .venv && .venv/bin/pip install pytest==9.1.1, puis activez-le avant la porte : . .venv/bin/activate)'
      ;;
  esac
}

sp_commande() { # sp_commande <paquets> : la commande d'installation, en texte — la même que celle lancée, `--` compris
  if [ "$GESTIONNAIRE" = brew ]; then
    printf 'brew install -- %s\n' "$1"
  elif [ "$(id -u)" = "0" ]; then
    printf 'apt-get update && apt-get install -y -- %s\n' "$1"
  else
    printf 'sudo apt-get update && sudo apt-get install -y -- %s\n' "$1"
  fi
}

# --- (2) AVANT ----------------------------------------------------------------
printf 'setup — prérequis du kit (inventaire : %s)\n' "$INV"
printf 'Plateforme : %s (%s) — gestionnaire : %s (%s)\n' "$OS" "$OS_NOTE" "$GESTIONNAIRE" "$GEST_BIN"
[ "$DRY" -eq 1 ] && sp_dire '--dry-run : rien ne sera installe'

if ! sp_doctor "$TMP/avant"; then
  sed 's/^/  doctor | /' "$TMP/avant"
  sp_refus "le doctor n a pas rendu de ligne de resume : inventaire ou doctor illisible"
  exit 2
fi

# Les lignes outil de classe B de la plateforme : tool US version US apt US brew.
REQUIS="$(awk -F'\t' -v us="$US" '
  { sub(/\r$/, "") }
  /^#/ { next }
  hdr == 0 {
    hdr = 1
    for (i = 1; i <= NF; i++) col[$i] = i
    n = split("tool nature os class version apt brew", req, " ")
    for (j = 1; j <= n; j++) if (!(req[j] in col)) bad = 1
    next
  }
  bad { next }
  /^[[:space:]]*$/ { next }
  $col["nature"] == "outil" && $col["class"] == "B" {
    print $col["tool"] us $col["os"] us $col["version"] us $col["apt"] us $col["brew"]
  }
' "$INV")"

TOUS=""
DEJA=""
A_FAIRE=""
PAQUETS=""
SANS_CANAL=""
HORS_B=""
while IFS="$US" read -r tool os _ apt brew; do
  [ -n "$tool" ] || continue
  sp_os_applies "$os" || continue
  # `doctor: hors classe B ici` (en-tête de doctor.sh) : pas requis ici.
  if sp_dans "$tool" "$D_HORS_B"; then
    HORS_B="${HORS_B:+$HORS_B }$tool"
    continue
  fi
  TOUS="${TOUS:+$TOUS }$tool"
  if sp_dans "$tool" "$D_BMANQ"; then
    etat="absent"
  elif sp_dans "$tool" "$D_MV"; then
    etat="mauvaise version"
  else
    DEJA="${DEJA:+$DEJA }$tool"
    continue
  fi
  A_FAIRE="${A_FAIRE:+$A_FAIRE }$tool"
  p="$(sp_paquet "$tool" "$apt" "$brew")"
  rc_p=$?
  if [ -z "$p" ]; then
    SANS_CANAL="${SANS_CANAL:+$SANS_CANAL }$tool"
    if [ "$rc_p" -eq 3 ]; then
      printf '  %-18s %s — cellule %s de l inventaire REFUSÉE (voir ci-dessus) : rien n est passé au gestionnaire\n' "$etat" "$tool" "$GESTIONNAIRE"
    else
      printf '  %-18s %s — aucun paquet %s connu de ce script\n' "$etat" "$tool" "$GESTIONNAIRE"
    fi
    continue
  fi
  printf '  %-18s %s — paquet %s : %s\n' "$etat" "$tool" "$GESTIONNAIRE" "$p"
  sp_dans "$p" "$PAQUETS" || PAQUETS="${PAQUETS:+$PAQUETS }$p"
done <<< "$REQUIS"

if [ -z "$TOUS" ]; then
  sp_refus "aucun outil de classe B pour $OS dans $INV : rien a installer, rien a verifier"
  exit 2
fi
printf 'Requis (classe B de l inventaire, %s) : %s\n' "$OS" "$TOUS"
if [ -n "$HORS_B" ]; then
  printf '  hors classe B ici (doctor) : %s\n' "$HORS_B"
  grep '^doctor: hors classe B ici : ' "$TMP/avant" | sed 's/^/    /'
fi
printf '  déjà là : %s\n' "${DEJA:-aucun}"

# --- (3b) hors du kit : les scanners (en-tête, CE QU'IL INSTALLE) ------------
SC_A_FAIRE=""
SC_PIPX=""
SC_MAIN=""
SC_SEMGREP_PIPX=""
SC_JDK=0
SC_NOTES=""
PIPX_BIN=""
if [ ! -f "$ROOT/.agents/IS_THE_KIT" ]; then
  printf 'Scanners de sécurité (hors du kit ; doctor: modules : %s)\n' "$D_MODULES"
  [ "$D_MODULES" = "illisible" ] && printf '  modules illisibles : seuls gitleaks et semgrep sont considérés\n'
  [ "$GESTIONNAIRE" = apt ] && { PIPX_BIN="$(sp_probe pipx)" || PIPX_BIN=""; }
  for rang in $(sp_rangs "$D_MODULES"); do
    outil="$(sp_mot "$rang" "$SP_SCANNERS_OUTILS")" || continue
    if sp_ligne_a "$TMP/avant" "$outil" PRESENT; then
      DEJA="${DEJA:+$DEJA }$outil"
      printf '  déjà là            %s\n' "$outil"
      continue
    fi
    if ! sp_ligne_a "$TMP/avant" "$outil" ABSENT; then
      printf '  non sondé          %s — aucune ligne de classe A du doctor pour lui : non planifié\n' "$outil"
      continue
    fi
    SC_A_FAIRE="${SC_A_FAIRE:+$SC_A_FAIRE }$outil"
    [ "$outil" = dependency-check ] && SC_JDK=1
    if [ "$GESTIONNAIRE" = brew ]; then
      p="$(sp_brew_de "$outil")" || p=""
      if [ -z "$p" ]; then
        # Défense : une table SP_SCANNERS_DARWIN plus courte que SP_SCANNERS_OUTILS.
        SC_MAIN="${SC_MAIN:+$SC_MAIN }$outil"
        printf '  %-18s %s — aucun paquet brew au même rang de SP_SCANNERS_DARWIN : a installer vous-meme\n' "absent" "$outil"
        continue
      fi
      printf '  %-18s %s — paquet brew : %s\n' "absent" "$outil" "$p"
      sp_dans "$p" "$PAQUETS" || PAQUETS="${PAQUETS:+$PAQUETS }$p"
      continue
    fi
    case "$outil" in
      semgrep)
        ver="$(sp_version_pin semgrep)" && SC_SEMGREP_PIPX="semgrep==$ver"
        if [ -n "$SC_SEMGREP_PIPX" ] && [ -n "$PIPX_BIN" ]; then
          SC_PIPX="${SC_PIPX:+$SC_PIPX }$SC_SEMGREP_PIPX"
          printf '  %-18s %s — pipx : %s\n' "absent" "$outil" "$SC_SEMGREP_PIPX"
        else
          SC_MAIN="${SC_MAIN:+$SC_MAIN }$outil"
          printf '  %-18s %s — a installer vous-meme : %s\n' "absent" "$outil" "$(sp_scanner_main "$outil")"
        fi
        ;;
      pip-audit)
        if [ -n "$PIPX_BIN" ]; then
          SC_PIPX="${SC_PIPX:+$SC_PIPX }pip-audit"
          printf '  %-18s %s — pipx : pip-audit\n' "absent" "$outil"
        else
          SC_MAIN="${SC_MAIN:+$SC_MAIN }$outil"
          printf '  %-18s %s — a installer vous-meme : %s\n' "absent" "$outil" "$(sp_scanner_main "$outil")"
        fi
        ;;
      npm)
        p="$(sp_paquet "$outil" "$(sp_cellule "$outil" apt)" -)"
        if [ -n "$p" ]; then
          printf '  %-18s %s — paquet apt : %s\n' "absent" "$outil" "$p"
          sp_dans "$p" "$PAQUETS" || PAQUETS="${PAQUETS:+$PAQUETS }$p"
        else
          SC_MAIN="${SC_MAIN:+$SC_MAIN }$outil"
          printf '  %-18s %s — a installer vous-meme : %s\n' "absent" "$outil" "$(sp_scanner_main "$outil")"
        fi
        ;;
      *)
        SC_MAIN="${SC_MAIN:+$SC_MAIN }$outil"
        printf '  %-18s %s — a installer vous-meme : %s\n' "absent" "$outil" "$(sp_scanner_main "$outil")"
        ;;
    esac
  done
  if [ -z "$PIPX_BIN" ] && [ "$GESTIONNAIRE" = apt ]; then
    if sp_dans semgrep "$SC_MAIN" || sp_dans pip-audit "$SC_MAIN"; then
      sp_dire 'pipx introuvable : semgrep et pip-audit sont à installer vous-même (sudo apt-get install pipx, puis les commandes ci-dessus)'
    fi
  fi
fi
# pipx pose ses commandes sous ~/.local/bin, souvent hors du PATH d'un premier
# usage : dit après la boucle pipx, et en --dry-run, dès qu'un pipx est planifié.
SP_PIPX_CHEMIN='pipx pose ses commandes sous ~/.local/bin : si le doctor les dit encore absentes, lancez pipx ensurepath, ouvrez un nouveau terminal, puis relancez setup.sh'
if [ -n "$SC_PIPX" ] || [ -n "$SC_SEMGREP_PIPX" ]; then
  SC_NOTES="pipx install n est PAS épinglé par empreinte (la CI pose semgrep par pip --require-hashes) : la version est fixée, l archive ne l est pas"
fi
if [ "$GESTIONNAIRE" = brew ] && sp_dans semgrep "$SC_A_FAIRE"; then
  ver="$(sp_version_pin semgrep 2>/dev/null)" || ver="illisible"
  SC_NOTES="${SC_NOTES:+$SC_NOTES
}semgrep : brew pose la version de homebrew/core, pas l épingle de la CI ($ver)"
fi

sp_annonces() { # sp_annonces : ce que la commande va tirer en plus, dit AVANT elle (C19)
  if [ "$SC_JDK" -eq 1 ] && [ "$GESTIONNAIRE" = brew ]; then
    sp_dire 'dependency-check : la formule brew tire un JDK (openjdk, plusieurs centaines de Mo), installé avec elle'
  fi
  if [ "$SC_JDK" -eq 1 ]; then
    sp_dire 'dependency-check : sans NVD_API_KEY ni base NVD, son premier scan reste dégradé — README-SECURITY-SCAN-SETUP.md § The NVD API key'
  fi
  if [ -n "$SC_NOTES" ]; then
    printf '%s\n' "$SC_NOTES" | sed 's/^/setup: /'
  fi
}

HOOKS_CONSEIL_DIRECT=0
sp_hookspath() {
  local top rc valeur chemin hooks actifs reponse root_phys
  top="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    sp_dire 'dépôt Git illisible : hooks non proposés ; configuration inchangée.'
    return
  fi
  if [ "$(cd "$top" && pwd -P)" != "$(cd "$ROOT" && pwd -P)" ]; then
    sp_dire "racine Git différente de $ROOT ($top) : hooks non proposés ; configuration inchangée."
    return
  fi
  if [ ! -d "$ROOT/.githooks" ]; then
    sp_dire '.githooks/ absent : hooks non proposés ; configuration inchangée.'
    return
  fi
  if [ -L "$ROOT/.githooks" ]; then
    root_phys="$(cd "$ROOT" && pwd -P)"
    chemin="$(cd "$ROOT/.githooks" && pwd -P)" || chemin=""
    case "$chemin" in
      "$root_phys"/*) ;;
      *) sp_dire '.githooks/ hors de cette racine : hooks non proposés ; configuration inchangée.'; return ;;
    esac
  fi
  valeur="$(git -C "$ROOT" config --get core.hooksPath 2>/dev/null)"
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    sp_dire 'lecture de core.hooksPath en échec : hooks non proposés ; configuration inchangée.'
    return
  fi
  if [ "$rc" -eq 0 ]; then
    chemin="$(cd "$ROOT" && cd "$valeur" 2>/dev/null && pwd -P)" || chemin=""
    if [ "$chemin" = "$(cd "$ROOT/.githooks" && pwd -P)" ]; then
      sp_dire 'Hooks déjà activés dans ce clone ; configuration inchangée.'
    else
      sp_dire "core.hooksPath déjà défini à $(printf '%s' "$valeur" | LC_ALL=C tr '\001-\037\177' '?') : hooks non proposés ; configuration inchangée."
    fi
    return
  fi
  hooks="$(git -C "$ROOT" rev-parse --git-path hooks 2>/dev/null)"
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$hooks" ]; then
    sp_dire 'chemin des hooks Git illisible : hooks non proposés ; configuration inchangée.'
    return
  fi
  case "$hooks" in
    /*) ;;
    *) hooks="$ROOT/$hooks" ;;
  esac
  if [ ! -d "$hooks" ]; then
    sp_dire "inventaire des hooks impossible ($hooks) : hooks non proposés ; configuration inchangée."
    return
  fi
  actifs="$(find "$hooks" -mindepth 1 -maxdepth 1 ! -name '*.sample' -exec basename {} \; 2>/dev/null)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    sp_dire "inventaire des hooks impossible ($hooks) : hooks non proposés ; configuration inchangée."
    return
  fi
  if [ -n "$actifs" ]; then
    sp_dire "hooks actifs dans $hooks : $(printf '%s' "$actifs" | tr '\n' ' ' | LC_ALL=C tr '\001-\037\177' '?') ; hooks non proposés ; configuration inchangée."
    sp_dire 'Intégrez les hooks existants dans .githooks/ en chaînant les noms communs, ou intégrez les hooks du kit dans le répertoire actif sans changer core.hooksPath ; si pre-push existe déjà, chaînez les deux pre-push sans copier par-dessus.'
    return
  fi
  HOOKS_CONSEIL_DIRECT=1
  if [ "$DRY" -eq 1 ]; then
    sp_dire 'hooks non proposés en --dry-run ; configuration inchangée.'
    return
  fi
  if [ -n "$AGENT" ]; then
    # Défense en profondeur, injoignable : sortie 7 en amont.
    sp_dire "hooks non proposés sous $AGENT ; configuration inchangée."
    return
  fi
  if [ ! -t 0 ]; then
    sp_dire 'hooks non proposés : entrée non interactive ; configuration inchangée.'
    return
  fi
  printf '%s' 'Activer les hooks de ce dépôt (tous ses worktrees liés partagent ce réglage) dans .githooks ? core.hooksPath remplace les hooks de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; commit-msg refuse certains sujets ; Git exécute les hooks de l’arbre courant. [o/N] '
  reponse=""
  IFS= read -r reponse || reponse=""
  case "$reponse" in
    o|oui)
      if git -C "$ROOT" config --local core.hooksPath .githooks; then
        HOOKS_CONSEIL_DIRECT=0
        sp_dire 'Hooks activés dans ce dépôt (worktrees liés compris) : core.hooksPath=.githooks.'
      else
        sp_dire 'écriture de core.hooksPath en échec ; configuration inchangée.'
      fi
      ;;
    *) sp_dire 'Hooks non activés dans ce clone ; configuration inchangée.' ;;
  esac
}

sp_pilote_fusion() {
  local py candidat reponse branche rc_inst=0
  if [ "$DRY" -eq 1 ]; then
    sp_dire 'pilote de fusion non proposé en --dry-run ; rien armé.'
    return
  fi
  if [ -n "$AGENT" ]; then
    sp_dire "pilote de fusion non proposé sous $AGENT ; rien armé."
    return
  fi
  py=""
  for candidat in python3 python py; do
    candidat="$(sp_probe "$candidat")" || continue
    if "$candidat" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      py="$candidat"
      break
    fi
  done
  if [ -z "$py" ]; then
    sp_dire 'pilote non proposé : python ≥ 3.11 absent ; rien armé.'
    return
  fi
  if "$py" -I -B "$ROOT/.agents/bin/fusion_enregistrement.py" --verifier; then
    sp_dire 'pilote de fusion déjà installé.'
    return
  fi
  if [ ! -t 0 ]; then
    sp_dire 'pilote de fusion non proposé : entrée non interactive ; rien armé.'
    if [ "$HOOKS_CONSEIL_DIRECT" -eq 1 ]; then
      sp_dire 'sans core.hooksPath → .githooks, aucune alerte de fusion (git config core.hooksPath .githooks).'
    fi
    return
  fi
  printf 'Installer le pilote de fusion dans ce clone ? [o/N] '
  reponse=""
  IFS= read -r reponse || reponse=""
  case "$reponse" in
    o|oui)
      branche="$(git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null)" || branche=""
      if [ -f "$ROOT/.agents/IS_THE_KIT" ] && [ "$branche" = develop ] &&
          git -C "$ROOT" show-ref --verify --quiet refs/remotes/origin/develop; then
        "$py" -I -B "$ROOT/.agents/bin/fusion_enregistrement.py" --installer --depuis origin/develop || rc_inst=$?
      else
        "$py" -I -B "$ROOT/.agents/bin/fusion_enregistrement.py" --installer || rc_inst=$?
      fi
      if [ "$rc_inst" -ne 0 ]; then
        sp_dire "installation du pilote de fusion en échec (code $rc_inst)."
      fi
      if "$py" -I -B "$ROOT/.agents/bin/fusion_enregistrement.py" --verifier; then
        sp_dire 'pilote de fusion vérifié.'
      else
        sp_dire 'pilote de fusion non vérifié ; rien ne garantit son armement.'
      fi
      ;;
    *)
      sp_dire 'pilote de fusion refusé ; rien armé.'
      if [ "$HOOKS_CONSEIL_DIRECT" -eq 1 ]; then
        sp_dire 'sans core.hooksPath → .githooks, aucune alerte de fusion (git config core.hooksPath .githooks).'
      fi
      ;;
  esac
}

sp_bilan() { # sp_bilan <installés> <déjà là> <manque encore> <rc> : la ligne de résumé, puis exit
  sp_hookspath
  sp_pilote_fusion
  printf '\nsetup: installés=%s déjà là=%s manque encore=%s — exit %s\n' "${1:-aucun}" "${2:-aucun}" "${3:-aucun}" "$4"
  exit "$4"
}

# --- (3) (4) le plan, et --dry-run --------------------------------------------
if [ -z "$A_FAIRE" ] && [ -z "$SC_A_FAIRE" ]; then
  sp_dire 'tout est la : rien a installer'
  sp_bilan "" "$DEJA" "" 0
fi
# Ce qui manque, classe B puis scanners (hors du kit) : la liste du --dry-run.
TOUT_A_FAIRE="$A_FAIRE"
[ -n "$SC_A_FAIRE" ] && TOUT_A_FAIRE="${TOUT_A_FAIRE:+$TOUT_A_FAIRE }$SC_A_FAIRE"

CMD=""
[ -n "$PAQUETS" ] && CMD="$(sp_commande "$PAQUETS")"
if [ "$DRY" -eq 1 ]; then
  sp_annonces
  if [ -n "$CMD" ]; then
    sp_dire "--dry-run : lancerait : $CMD"
  fi
  set -f
  for spec in $SC_PIPX; do
    sp_dire "--dry-run : lancerait : pipx install $spec"
  done
  set +f
  [ -n "$SC_PIPX" ] && sp_dire "$SP_PIPX_CHEMIN"
  if [ -n "$SC_MAIN" ]; then
    sp_dire "--dry-run : scanners a installer vous-meme : $SC_MAIN"
  fi
  if [ -n "$SANS_CANAL" ]; then
    sp_dire "--dry-run : sans paquet connu, a installer vous-meme : $SANS_CANAL"
    # La note d'un outil sans paquet est dite AVANT d'installer, pas seulement
    # après : sur macOS, c'est la commande pip de pytest (constat du 2026-10-14).
    # Bornée aux outils SANS paquet : les notes de bash et de python3 suivent une
    # installation par brew et appellent `brew --prefix`, que --dry-run ne lance pas.
    set -f
    for tool in $SANS_CANAL; do
      conseil="$(sp_conseil "$tool")"
      [ -n "$conseil" ] && sp_dire "--dry-run : note $tool : $conseil"
    done
    set +f
  fi
  sp_bilan "" "$DEJA" "$TOUT_A_FAIRE" 1
fi

# --- l'installation : UNE commande, affichée avant --------------------------
RC_GEST=0
sp_annonces
if [ -n "$PAQUETS" ]; then
  sp_dire "lance : $CMD"
  # $PAQUETS est une liste de noms de paquets VALIDÉS (sp_paquet), découpée sur
  # les espaces sous `set -f` (aucun glob) : le découpage est voulu. Elle suit
  # un `--` : fin des options pour brew comme pour apt-get.
  set -f
  # shellcheck disable=SC2086
  if [ "$GESTIONNAIRE" = brew ]; then
    "$GEST_BIN" install -- $PAQUETS
    RC_GEST=$?
  elif [ "$(id -u)" = "0" ]; then
    "$GEST_BIN" update && "$GEST_BIN" install -y -- $PAQUETS
    RC_GEST=$?
  else
    SUDO_BIN="$(sp_probe sudo)" || SUDO_BIN=""
    if [ -z "$SUDO_BIN" ]; then
      sp_refus 'sudo introuvable : apt-get exige root. Tapez vous-meme, en root :'
      sp_refus "  apt-get update && apt-get install -y -- $PAQUETS"
      RC_GEST=1
    else
      sp_dire 'sudo va demander votre mot de passe (apt-get exige root)'
      "$SUDO_BIN" "$GEST_BIN" update && "$SUDO_BIN" "$GEST_BIN" install -y -- $PAQUETS
      RC_GEST=$?
    fi
  fi
  set +f
  [ "$RC_GEST" -ne 0 ] && sp_refus "le gestionnaire a rendu $RC_GEST — voir ci-dessus"
fi
# Ubuntu, hors du kit : semgrep==<version validée> et pip-audit par pipx, sans
# root (pipx installe pour l'utilisateur). Une spécification par appel.
set -f
for spec in $SC_PIPX; do
  sp_dire "lance : pipx install $spec"
  "$PIPX_BIN" install "$spec" || sp_refus "pipx a rendu $? pour $spec — voir ci-dessus"
done
set +f
[ -n "$SC_PIPX" ] && sp_dire "$SP_PIPX_CHEMIN"

# --- (5) APRÈS ----------------------------------------------------------------
if ! sp_doctor "$TMP/apres"; then
  sed 's/^/  doctor | /' "$TMP/apres"
  sp_refus 'le doctor n a pas rendu de ligne de resume apres l installation'
  exit 2
fi

INSTALLES=""
MANQUE=""
printf '\nAprès installation\n'
set -f
for tool in $A_FAIRE; do
  if sp_dans "$tool" "$D_BMANQ" || sp_dans "$tool" "$D_MV"; then
    MANQUE="${MANQUE:+$MANQUE }$tool"
    printf '  manque encore      %s\n' "$tool"
    grep -F -- " $tool — " "$TMP/apres" | sed 's/^ */    doctor : /'
    if sp_dans "$tool" "$SANS_CANAL"; then
      printf '    a installer vous-meme : aucun paquet %s connu de ce script\n' "$GESTIONNAIRE"
    else
      p=""
      while IFS="$US" read -r t _ _ apt brew; do
        [ "$t" = "$tool" ] && p="$(sp_paquet "$t" "$apt" "$brew")"
      done <<< "$REQUIS"
      printf '    a taper : %s\n' "$(sp_commande "$p")"
    fi
    conseil="$(sp_conseil "$tool")"
    [ -n "$conseil" ] && printf '    note : %s\n' "$conseil"
  else
    INSTALLES="${INSTALLES:+$INSTALLES }$tool"
    printf '  installé           %s\n' "$tool"
  fi
done
# Les scanners planifiés (C18) : la ligne de classe A de CHACUN est relue dans la
# seconde sonde ; seul PRESENT vaut « installé », tout le reste manque encore.
for tool in $SC_A_FAIRE; do
  if sp_ligne_a "$TMP/apres" "$tool" PRESENT; then
    INSTALLES="${INSTALLES:+$INSTALLES }$tool"
    printf '  installé           %s\n' "$tool"
    continue
  fi
  MANQUE="${MANQUE:+$MANQUE }$tool"
  printf '  manque encore      %s\n' "$tool"
  grep -F -- " $tool — " "$TMP/apres" | sed 's/^ */    doctor : /'
  p=""
  if [ "$GESTIONNAIRE" = brew ]; then
    p="$(sp_brew_de "$tool")"
  elif [ "$tool" = npm ]; then
    p="$(sp_paquet "$tool" "$(sp_cellule "$tool" apt)" - 2>/dev/null)"
  fi
  if [ -n "$p" ]; then
    printf '    a taper : %s\n' "$(sp_commande "$p")"
  else
    printf '    a installer vous-meme : %s\n' "$(sp_scanner_main "$tool")"
  fi
done
set +f
printf '  déjà là            %s\n' "${DEJA:-aucun}"

RC=0
[ -n "$MANQUE" ] && RC=1
sp_bilan "$INSTALLES" "$DEJA" "$MANQUE" "$RC"
