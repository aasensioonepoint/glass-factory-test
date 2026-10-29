#!/usr/bin/env bash
# ============================================================================
# core-scripts/install-tools.sh — INSTALLE LES OUTILS ÉPINGLÉS DE L'INVENTAIRE,
# macOS ET LINUX, À LA VERSION QUE LA CI DU KIT ÉPINGLE (BK-344, volet d de
# T-00000529). Il complète core-scripts/setup.sh (classe B, gestionnaire du
# système, NON épinglé) : celui-ci n'installe QUE ce qui a une épingle.
#
# USAGE
#   bash core-scripts/install-tools.sh [--plan | --appliquer] [--prefix <dir>]
#                                      [--hors-home] [--inventory <tsv>] [--ci <ci.yml>]
#     --plan       (DÉFAUT) dit ce qui serait installé ; n'écrit RIEN, aucun réseau
#     --appliquer  installe, sous --prefix seulement
#     --prefix     racine d'installation (défaut : $HOME/.local/share/cadre-outils) ;
#                  chemin absolu, SOUS $HOME (ni `.` ni `..` dans le chemin), sinon
#                  refus (exit 2) ; aucun profil édité
#     --hors-home  admet un --prefix hors de $HOME (geste explicite : le système
#                  n'est alors touché que parce que vous l'avez demandé)
#     --inventory  autre inventaire (défaut : core-scripts/tool-inventory.tsv) — bancs
#     --ci         autre workflow source des épingles (défaut : .github/workflows/ci.yml) — bancs
#   INSTALL_TOOLS_OS=darwin|linux|windows   impose la plateforme (sinon `uname -s`)
#   INSTALL_TOOLS_ARCH=x64|arm64            impose l'architecture (sinon `uname -m`)
#   INSTALL_TOOLS_PROBE_PATH=<PATH>         PATH où l'interpréteur est cherché
#                                           (défaut : $PATH) ; les bancs y posent un bouchon
#   Ces trois variables sont RÉSERVÉES AUX BANCS (précédent : SETUP_PROBE_PATH de
#   core-scripts/setup.sh) : ne les posez pas à la main, ne les laissez pas dans
#   un profil — la troisième décide QUEL interpréteur télécharge et crée les venvs.
#
# CE QU'IL INSTALLE — DÉRIVÉ DE L'INVENTAIRE, JAMAIS D'UNE LISTE ÉCRITE ICI.
#   Les lignes `nature=outil` de core-scripts/tool-inventory.tsv dont la colonne
#   `os` vaut pour cette plateforme ET dont `ci_pin` n'est pas `-`. Le code ne
#   nomme AUCUN outil (cas I9 de install-tools.test.sh). Toute autre ligne outil
#   de la plateforme est dite « aucun épinglage : non installé » — par exemple
#   k6 (licence AGPL) et terraform (licence BUSL), qui n'ont pas de `ci_pin` :
#   ce script ne les installe jamais. À l'inventaire relevé à develop @ d4624d4ec :
#   pytest 9.1.1 (pip-hash, job tests), gitleaks 8.30.1 (curl-sha256, job
#   adoptant), semgrep 1.175.0 (pip-hash, job adoptant). Les autres canaux
#   (setup-python, image-python-slim, zip-sha256) ne sont pas installables ici : dits.
#
# L'ÉPINGLE EST LUE À SA SOURCE, JAMAIS INVENTÉE (fail-closed).
#   pip-hash    : un fichier d'exigences qui porte `<outil>==<version>` avec
#                 `--hash=` — le bloc en ligne de ci.yml (extrait par la règle de
#                 core-scripts/verify.sh, le `sed` de CI_REQS) ou un `-r <chemin>`
#                 LITTÉRAL de ci.yml (un `-r "$VAR"` est exclu), relatif à la racine
#                 du dépôt de ce ci.yml. Installé par
#                   <venv>/bin/<interpréteur> -I -m pip install --require-hashes
#                     --only-binary :all: --disable-pip-version-check -r <fichier>
#                 — les drapeaux de ci.yml (cas I6) ; UN VENV PAR FICHIER SOURCE
#                 (`<prefix>/venvs/<nom>`) : pygments diffère entre les deux sources,
#                 un venv unique basculerait à chaque relance.
#   curl-sha256 : une URL de ci.yml dont le nom de fichier ouvre par
#                 `<outil>_<version>_` et porte `_<os>_<arch>.`, avec le sha256 écrit
#                 dans la même étape. Téléchargée par l'interpréteur de l'inventaire
#                 (urllib, https ou file seulement), sha256 vérifié AVANT toute
#                 écriture, SEUL le membre nommé comme l'outil extrait, fichier
#                 ordinaire seulement (ni lien, ni chemin), posé sous `<prefix>/bin`.
#   Épingle introuvable dans ses sources, ou job de l'épingle sans `runs-on`
#   lisible : « épinglage introuvable », rc 1, jamais un pip sans hash. Plateforme : l'épingle vaut là où le job de la CI qui la pose
#   tourne (`runs-on`, matrice `os:` comprise) ; ailleurs, dit, non installé, rc
#   inchangé. pip-hash exige EN PLUS l'architecture du runner (ubuntu-*,
#   windows-* : x64, `-arm` : arm64 ; macos-* : arm64, macos-10..13 et `intel` :
#   x64) et la version `python-version:` du job (majeure.mineure, comparée à
#   l'interpréteur) : la fermeture hachée n'est résolue que pour eux ; sinon
#   « non installable ici », raison nommée, rc inchangé. Aujourd'hui gitleaks et
#   semgrep ne sont épinglés que pour linux x86_64 (job adoptant ; semgrep pour
#   CPython 3.12 seulement) : sur un Mac Apple Silicon dont le premier python3
#   est un 3.14, seul pytest s'installe.
#
# L'INTERPRÉTEUR — celui de l'inventaire : les alternatives de la PREMIÈRE colonne
#   `mode_sonde` en `module:`, le premier trouvé (type -P, puis exécutable) qui
#   répond à `--version` — la règle de core-scripts/doctor.sh et de la porte.
#
# IDEMPOTENT — un reçu par outil (`<prefix>/recus/<outil>` : version, canal,
#   empreinte de l'artefact ou du fichier d'exigences) ; pour pip-hash, la version
#   de la distribution est AUSSI relue dans le venv (importlib.metadata). Relancer :
#   « déjà installé », rien n'est retéléchargé ; une version dérivée : réinstallée.
#   --appliquer pose `<prefix>/.verrou` (mkdir) et le retire en sortie ; un
#   verrou déjà là : refus, exit 1, rien n'est fait.
#
# AU PATH — `<prefix>/bin`, puis le venv d'un outil lancé en MODULE (mode_sonde
#   `module:`, pytest) seulement : un outil CLI d'un venv (semgrep) est un lien
#   `<prefix>/bin/<outil>` vers son point d'entrée, son venv n'est PAS au PATH.
#   BORNE : le venv d'un outil module met son python3 et son pip devant ceux de
#   l'utilisateur, dans l'ordre de l'inventaire.
#
# APRÈS --appliquer — core-scripts/doctor.sh sonde l'inventaire AVANT (PATH de
#   sonde seul) puis APRÈS (DOCTOR_PROBE_PATH préfixé de la ligne PATH) ; la ligne
#   de résumé est relayée. rc 1, nommé, si un outil posé ou déjà là n'est pas dit
#   PRESENT après (preuve positive : un doctor illisible ou sorti avant son
#   rapport ne prouve rien), ou si un outil PRESENT avant ne l'est plus (masqué).
#   La ligne `export PATH=…` à ajouter soi-même est imprimée, préfixe cité pour
#   le shell (printf %q) ; aucun profil n'est édité.
#
# JAMAIS SOUS UN AGENT QUAND LE POSTE VA ÊTRE MODIFIÉ — un marqueur d'agent posé
#   (valeur non blanche) avec --appliquer : REFUS, code 7, rien écrit. Les
#   marqueurs (MARQUEURS ci-dessous) sont AGENT_CALLER_MARKERS de
#   .agents/bin/skills_github_fallback.py, dans son ordre (cas I2). Une GARDE,
#   pas une frontière : `env -u` la défait ; Codex, Gemini et Kimi n'exposent aucun
#   marqueur mesuré dans le shell de l'agent (faux négatif nommé, comme setup.sh).
#
# CE QUI N'EST PAS REDISTRIBUÉ — rien : l'éditeur de chaque outil sert l'artefact
#   au geste de l'utilisateur ; ce dépôt ne porte que des épingles.
#
# EXIT
#   0  plan : chaque épingle de la plateforme résolue ; appliquer : chacune
#      installée ou déjà là
#   1  une épingle introuvable, ou un téléchargement, un sha256, une extraction,
#      un venv ou un pip en échec ; un venv qui est un lien ; un outil posé que
#      le doctor ne dit pas PRESENT, un outil masqué, un doctor illisible ;
#      le verrou déjà posé
#   2  usage ; plateforme non prise en charge (Windows : core-scripts/setup.ps1) ;
#      inventaire illisible ; aucun interpréteur ; préfixe non absolu, à `.`,
#      `..` ou `:`, ou hors de $HOME sans --hors-home
#   7  --appliquer sous un marqueur d'agent : rien n'est fait
#
# FORME : bash 3.2 (celui de macOS) ; `set -uo pipefail` ; aucune des huit formes
# que le SAST ne lit pas (.agents/ref/CONVENTIONS_shell.md) ; aucun `eval` ;
# chaque valeur passe en argument positionnel. Le téléchargement passe par
# l'interpréteur, jamais par un outil réseau du système : le code ne nomme aucun
# outil (doctor-parity.test.sh lit le TEXTE).
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

INV="$ROOT/core-scripts/tool-inventory.tsv"
CI="$ROOT/.github/workflows/ci.yml"
DOCTOR="$ROOT/core-scripts/doctor.sh"
PREFIX=""
HORS_HOME=0
MODE=plan
US=$'\037'
_pipe='|'
_pv=';'
_par='('
_parf=')'
MARQUEURS='CLAUDECODE CLAUDE_CODE_ENTRYPOINT AGENTS_HOOK_HOST COPILOT_AGENT_SESSION_ID COPILOT_CLI'
JPY_ILLISIBLE='illisible (version Python du job absente ou non littérale)'
DRAPEAUX_PIP='--require-hashes --only-binary :all: --disable-pip-version-check'

it_usage() {
  printf '%s\n' 'usage: install-tools.sh [--plan | --appliquer] [--prefix <dir>] [--hors-home] [--inventory <tsv>] [--ci <ci.yml>]'
}
it_dire() { printf 'install-tools: %s\n' "$1"; }
it_refus() { printf 'install-tools: %s\n' "$1" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --plan)
      MODE=plan
      shift
      ;;
    --appliquer)
      MODE=appliquer
      shift
      ;;
    --hors-home)
      HORS_HOME=1
      shift
      ;;
    --prefix|--inventory|--ci)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        it_refus "$1 attend une valeur"
        it_usage >&2
        exit 2
      fi
      case "$1" in
        --prefix)
          PREFIX="$2"
          ;;
        --inventory)
          INV="$2"
          ;;
        *)
          CI="$2"
          ;;
      esac
      shift 2
      ;;
    -h|--help)
      it_usage
      exit 0
      ;;
    *)
      it_refus "argument inconnu : $1"
      it_usage >&2
      exit 2
      ;;
  esac
done

# --- (0) jamais sous un agent quand le poste va être modifié -----------------
it_pose() { [ -n "$(printf '%s' "$1" | tr -d ' \t\r\n\v\f')" ]; }
AGENT=""
for m in $MARQUEURS; do
  if it_pose "${!m:-}"; then
    AGENT="$m"
    break
  fi
done
if [ -n "$AGENT" ] && [ "$MODE" = "appliquer" ]; then
  it_refus "a lancer par vous-meme dans un terminal, pas par un agent : --appliquer installe sur le poste ($AGENT est pose ici)."
  it_refus 'Rien n a ete fait. --plan reste permis.'
  exit 7
fi

# --- (1) plateforme -----------------------------------------------------------
OS="${INSTALL_TOOLS_OS:-}"
if [ -z "$OS" ]; then
  case "$(uname -s 2>/dev/null)" in
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
      OS=inconnue
      ;;
  esac
fi
case "$OS" in
  darwin|linux)
    ;;
  windows)
    it_refus 'Windows : non pris en charge ici — core-scripts/setup.ps1 (exit 2).'
    exit 2
    ;;
  *)
    it_refus "plateforme non prise en charge : $OS (darwin | linux) — exit 2."
    exit 2
    ;;
esac
ARCH="${INSTALL_TOOLS_ARCH:-}"
if [ -z "$ARCH" ]; then
  ARCH="$(uname -m 2>/dev/null)"
fi
case "$ARCH" in
  x86_64|amd64)
    ARCH=x64
    ;;
  aarch64)
    ARCH=arm64
    ;;
esac

if [ -z "$PREFIX" ]; then
  if [ -z "${HOME:-}" ]; then
    it_refus 'HOME vide et --prefix absent : aucune racine d installation (exit 2).'
    exit 2
  fi
  PREFIX="$HOME/.local/share/cadre-outils"
fi
case "$PREFIX" in
  /*)
    ;;
  *)
    it_refus "--prefix doit etre un chemin absolu : $PREFIX (exit 2)."
    exit 2
    ;;
esac
case "$PREFIX/" in
  */./*|*/../*)
    it_refus "--prefix sans . ni .. : $PREFIX (exit 2)."
    exit 2
    ;;
  *:*)
    it_refus "--prefix sans deux-points (separateur du PATH) : $PREFIX (exit 2)."
    exit 2
    ;;
esac
H="${HOME:-}"
H="${H%/}"
SOUS_HOME=0
if [ -n "$H" ]; then
  case "$PREFIX" in
    "$H"/?*)
      SOUS_HOME=1
      ;;
  esac
fi
if [ "$HORS_HOME" -eq 0 ] && [ "$SOUS_HOME" -eq 0 ]; then
  it_refus "--prefix hors de HOME (${HOME:-vide}) : $PREFIX — refuse ; --hors-home pour l admettre (exit 2)."
  exit 2
fi
if [ ! -r "$INV" ]; then
  it_refus "inventaire illisible : $INV (exit 2)."
  exit 2
fi
if [ ! -r "$CI" ]; then
  it_refus "workflow illisible : $CI (exit 2)."
  exit 2
fi
CIROOT="$(cd "$(dirname "$CI")/../.." && pwd)"

# --- (2) l'inventaire, par NOM de colonne -------------------------------------
# Sortie : `!` + erreur, `M` + interpréteurs du 1er mode module:, ou
# `=` tool US os US ci_pin US mode_sonde pour chaque ligne outil.
NORM="$(awk -F'\t' -v us="$US" '
  { sub(/\r$/, "") }
  /^#/ { next }
  hdr == 0 {
    hdr = 1
    for (i = 1; i <= NF; i++) col[$i] = i
    n = split("tool nature os ci_pin mode_sonde", req, " ")
    for (j = 1; j <= n; j++) if (!(req[j] in col)) { print "!colonne absente : " req[j]; bad = 1 }
    next
  }
  bad || /^[[:space:]]*$/ { next }
  $col["nature"] != "outil" { next }
  {
    m = $col["mode_sonde"]
    if (!mod && m ~ /^module:/) { sub(/^module:/, "", m); print "M" m; mod = 1 }
    print "=" $col["tool"] us $col["os"] us $col["ci_pin"] us $col["mode_sonde"]
  }
  END { if (!hdr) print "!aucune ligne de colonnes" }
' "$INV")"
ERRS="$(printf '%s\n' "$NORM" | sed -n 's/^!//p')"
if [ -n "$ERRS" ]; then
  it_refus "inventaire $INV : $ERRS (exit 2)."
  exit 2
fi
DATA="$(printf '%s\n' "$NORM" | sed -n 's/^=//p')"
ALTS="$(printf '%s\n' "$NORM" | sed -n 's/^M//p')"

# --- (3) l'interpréteur de l'inventaire ---------------------------------------
PROBE="${INSTALL_TOOLS_PROBE_PATH:-$PATH}"
PY=""
alts="${ALTS//$_pipe/ }"
set -f
for a in $alts; do
  p="$( PATH="$PROBE"; type -P "$a" 2>/dev/null )" || continue
  [ -x "$p" ] || continue
  if "$p" --version </dev/null >/dev/null 2>&1; then
    PY="$p"
    break
  fi
done
set +f
if [ -z "$PY" ]; then
  it_refus "aucun interpréteur de l inventaire (module: ${ALTS:-absent}) ne répond dans le PATH de sonde (exit 2)."
  exit 2
fi
# majeure.mineure de l'interpréteur, comparée au `python-version:` du job (pip-hash)
PYV="$("$PY" -I -c 'import sys;print("%d.%d"%sys.version_info[:2])' </dev/null 2>/dev/null)"

# L'aide en ligne : empreinte et téléchargement. Lancée en `-I` (isolé), chaque
# valeur en argument positionnel. Les lignes commentées sont lues par I9 comme
# des commentaires ; le code ne nomme aucun outil.
read -r -d '' PYCODE <<'PYEOF'
import hashlib
import io
import os
import sys
import tarfile
import tempfile
import urllib.request


def refus(msg):
    sys.stderr.write("install-tools: refus : " + msg + "\n")
    sys.exit(1)


def empreinte(chemin):
    h = hashlib.sha256()
    if chemin == "-":
        h.update(sys.stdin.buffer.read())
    else:
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 16), b""):
                h.update(bloc)
    return h.hexdigest()


def fetch(url, attendu, membre, dest):
    if not (url.startswith("https://") or url.startswith("file://")):
        refus("schema non admis (https ou file seulement) : " + url)
    if membre in ("", ".", "..") or "/" in membre or "\\" in membre:
        refus("nom de membre invalide : " + membre)
    try:
        with urllib.request.urlopen(url, None, 120) as r:
            data = r.read()
    except (OSError, ValueError) as e:
        refus("telechargement en echec : %s (%s)" % (url, e))
    vu = hashlib.sha256(data).hexdigest()
    if vu != attendu:
        refus("sha256 %s, attendu %s : rien n est ecrit" % (vu, attendu))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            try:
                info = tf.getmember(membre)
            except KeyError:
                refus("membre %s absent de l archive : rien n est ecrit" % membre)
            if not info.isfile():
                refus("membre %s n est pas un fichier ordinaire (lien ou dossier) : rien n est ecrit" % membre)
            contenu = tf.extractfile(info).read()
    except tarfile.TarError as e:
        refus("archive illisible : %s" % e)
    os.makedirs(dest, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + membre + ".", dir=dest)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu)
        os.chmod(tmp, 0o755)
        os.replace(tmp, os.path.join(dest, membre))
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        refus("ecriture en echec : %s" % e)


def main(argv):
    if len(argv) == 2 and argv[0] == "sha":
        print(empreinte(argv[1]))
        return 0
    if len(argv) == 5 and argv[0] == "fetch":
        fetch(argv[1], argv[2], argv[3], argv[4])
        return 0
    sys.stderr.write("install-tools: aide interne : arguments invalides\n")
    return 2


sys.exit(main(sys.argv[1:]))
PYEOF

it_aide() { "$PY" -I -c "$PYCODE" "$@"; }

# --- (4) les sources d'épingles de ci.yml --------------------------------------
# Le bloc en ligne : la règle de core-scripts/verify.sh (CI_REQS), à l'octet.
INLINE="$(sed -n 's/^[[:space:]]*\([A-Za-z0-9_.-]\{1,\}[=;].*--hash=.*\)$/\1/p' "$CI")"
# Les `-r <chemin>` LITTÉRAUX d'une ligne d'installation hachée (jamais `"$VAR"`).
RFILES="$(grep -F -- '--require-hashes' "$CI" | sed -n 's/^.* -r \([^"$[:space:]][^[:space:]]*\)[[:space:]]*$/\1/p')"

it_porte() { # it_porte <outil==version> : rc 0 si stdin porte cette exigence, hachée
  awk -v p="$1" '
    index($0, p) == 1 {
      c = substr($0, length(p) + 1, 1)
      if ((c == " " || c == ";") && index($0, "--hash=sha256:")) f = 1
    }
    END { exit !f }'
}

# it_job_py <job> : majeure.mineure de la 1re clé de version Python de ce job de
# ci.yml (vide : illisible). `p[y]thon` dans le motif : la clé YAML est écrite
# sans le jeton d'inventaire `python`, que I9 refuse dans le code.
it_job_py() {
  awk -v job="$1" '
    /^jobs:/ { inj = 1; next }
    inj && /^[^[:space:]#]/ { inj = 0 }
    inj && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { cur = $1; sub(/:$/, "", cur); next }
    inj && cur == job && v == "" && /^[[:space:]]+p[y]thon-version:/ {
      l = $0; sub(/^[^:]*:[[:space:]]*/, "", l); gsub(/["\047]/, "", l)
      if (match(l, /^[0-9]+[.][0-9]+/)) v = substr(l, 1, RLENGTH); else v = "?"
    }
    END { if (v != "?") print v }' "$CI"
}

it_job_os() { # it_job_os <job> : couples os/arch (linux/x64 darwin/arm64 …) où ce job de ci.yml tourne
  awk -v job="$1" '
    /^jobs:/ { inj = 1; next }
    inj && /^[^[:space:]#]/ { inj = 0 }
    inj && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { cur = $1; sub(/:$/, "", cur); next }
    inj && cur == job && /^[[:space:]]+runs-on:/ { r = $0; sub(/^[^:]*:[[:space:]]*/, "", r) }
    inj && cur == job && /^[[:space:]]+os:[[:space:]]*[[]/ {
      m = $0; i = index(m, "["); m = substr(m, i + 1); j = index(m, "]"); if (j) m = substr(m, 1, j - 1)
    }
    END {
      if (r ~ /matrix[.]os/) r = m
      gsub(/,/, " ", r)
      n = split(r, a, /[[:space:]]+/)
      for (i = 1; i <= n; i++) {
        x = (a[i] ~ /arm/) ? "arm64" : "x64"
        if (a[i] ~ /^macos/) {
          x = "arm64"
          if (a[i] !~ /xlarge/ && (a[i] ~ /^macos-1[0-3]([^0-9]|$)/ || a[i] ~ /intel/)) x = "x64"
        }
        if (a[i] ~ /^ubuntu/) s = s " linux/" x
        else if (a[i] ~ /^macos/) s = s " darwin/" x
        else if (a[i] ~ /^windows/) s = s " windows/" x
      }
      print s
    }' "$CI"
}

it_urls() { # it_urls : `url TAB sha256` pour chaque URL de ci.yml suivie d'un sha256 dans la même étape
  awk -F'\t' '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*- name:/ { u = "" }
    {
      l = $0
      if (match(l, /(https|file):\/\/[^[:space:]"\047]+/)) { u = substr(l, RSTART, RLENGTH); next }
      if (u == "") next
      n = split(l, w, /[^0-9a-f]+/)
      for (i = 1; i <= n; i++) if (length(w[i]) == 64) { print u "\t" w[i]; u = ""; break }
    }' "$CI"
}
URLS="$(it_urls)"

it_recu_ok() { # it_recu_ok <outil> <attendu> <cible exécutable> : rc 0 si le reçu dit déjà ceci
  [ -f "$PREFIX/recus/$1" ] && [ -x "$3" ] && [ "$(sed -n 1p "$PREFIX/recus/$1")" = "$2" ]
}
it_recu() { # it_recu <outil> <contenu>
  mkdir -p "$PREFIX/recus" && printf '%s\n' "$2" > "$PREFIX/recus/$1"
}
# it_version_ok <interpréteur du venv> <distribution> <version> : rc 0 si le venv
# porte cette distribution à cette version (le reçu seul ne prouve pas l'état).
it_version_ok() {
  [ "$("$1" -I -c 'import importlib.metadata as m,sys;print(m.version(sys.argv[1]))' "$2" </dev/null 2>/dev/null)" = "$3" ]
}

INSTALLES=""
DEJA=""
A_FAIRE=""
NON=""
SANS=""
ECHECS=""
VENVS=""
SRC_FAITES=" "
SRC_ECHEC=" "

it_venv_path() { # it_venv_path <venv> : ajoute <venv>/bin à VENVS (séparateur US : un préfixe peut porter une espace), une fois
  case "$VENVS$US" in
    *"$US$1/bin$US"*)
      ;;
    *)
      VENVS="$VENVS$US$1/bin"
      ;;
  esac
}
it_non() { # it_non <outil> : ajoute l'outil aux non installés, une fois
  case " $NON " in
    *" $1 "*)
      ;;
    *)
      NON="$NON $1"
      ;;
  esac
}

it_curl() { # it_curl <outil> <version> : canal curl-sha256
  local t="$1" v="$2" u s b cand="" ici="" vus=""
  while IFS="$(printf '\t')" read -r u s; do
    [ -n "$u" ] || continue
    b="${u##*/}"
    case "$b" in
      "${t}_${v}_"*)
        cand="$cand $b"
        case "$b" in
          *"_${OS}_${ARCH}."*)
            ici="$u $s"
            ;;
        esac
        ;;
    esac
  done <<< "$URLS"
  if [ -z "$cand" ]; then
    it_dire "  $t $v : épinglage introuvable (aucune URL ${t}_${v}_… suivie d'un sha256 dans $CI) — non installé"
    ECHECS="$ECHECS $t"
    return
  fi
  if [ -z "$ici" ]; then
    it_dire "  $t $v : pas d'artefact épinglé pour $OS/$ARCH (épinglés :$cand) — non installé"
    it_non "$t"
    return
  fi
  u="${ici%% *}"
  s="${ici#* }"
  vus="$v@curl-sha256 $s"
  if it_recu_ok "$t" "$vus" "$PREFIX/bin/$t"; then
    it_dire "  $t $v : déjà installé ($PREFIX/bin/$t)"
    DEJA="$DEJA $t"
    return
  fi
  if [ "$MODE" = "plan" ]; then
    it_dire "  $t $v : à installer — $u (sha256 $s) -> $PREFIX/bin/$t"
    A_FAIRE="$A_FAIRE $t"
    return
  fi
  it_dire "  $t $v : téléchargement : $u"
  if it_aide fetch "$u" "$s" "$t" "$PREFIX/bin" </dev/null && it_recu "$t" "$vus"; then
    it_dire "  $t $v : installé ($PREFIX/bin/$t)"
    INSTALLES="$INSTALLES $t"
  else
    it_dire "  $t $v : ÉCHEC — rien n'est posé hors de $PREFIX"
    ECHECS="$ECHECS $t"
  fi
}

it_pip() { # it_pip <outil> <version> <mode_sonde> : canal pip-hash
  local t="$1" v="$2" mode="$3" f="" nom="" req="" fp vus venv vpy cible
  if printf '%s\n' "$INLINE" | it_porte "$t==$v"; then
    nom=ci-yml
  else
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      case "$f" in
        /*)
          req="$f"
          ;;
        *)
          req="$CIROOT/$f"
          ;;
      esac
      [ -r "$req" ] || continue
      if it_porte "$t==$v" < "$req"; then
        nom="$(basename "$req")"
        nom="${nom%.txt}"
        nom="$(printf '%s' "$nom" | tr -c 'A-Za-z0-9._-' '_')"
        break
      fi
      req=""
    done <<< "$RFILES"
  fi
  if [ -z "$nom" ]; then
    it_dire "  $t $v : épinglage introuvable ($t==$v --hash= absent du bloc en ligne et des -r de $CI) — non installé, jamais un pip sans hash"
    ECHECS="$ECHECS $t"
    return
  fi
  venv="$PREFIX/venvs/$nom"
  vpy="$venv/bin/${PY##*/}"
  if [ "$nom" = "ci-yml" ]; then
    req="$PREFIX/venvs/ci-yml.requirements.txt"
    fp="$(printf '%s\n' "$INLINE" | it_aide sha -)"
  else
    fp="$(it_aide sha "$req" </dev/null)"
  fi
  vus="$v@pip-hash $fp"
  # Un outil MODULE : son venv va au PATH (l'interpréteur le lance). Un outil
  # CLI : seul son point d'entrée, lié sous <prefix>/bin — jamais le python3/pip
  # de son venv devant ceux de l'utilisateur.
  case "$mode" in
    module:*)
      it_venv_path "$venv"
      cible="$vpy"
      ;;
    *)
      cible="$PREFIX/bin/$t"
      ;;
  esac
  if it_recu_ok "$t" "$vus" "$cible" && it_version_ok "$vpy" "$t" "$v"; then
    it_dire "  $t $v : déjà installé (venv $venv)"
    DEJA="$DEJA $t"
    return
  fi
  if [ "$MODE" = "plan" ]; then
    it_dire "  $t $v : à installer — venv $venv, -I -m pip install $DRAPEAUX_PIP -r $req"
    A_FAIRE="$A_FAIRE $t"
    return
  fi
  if [ -L "$venv" ] || [ -L "$PREFIX/venvs" ]; then
    it_dire "  $t $v : ÉCHEC — $venv ou son dossier parent est un lien : refusé avant tout venv --clear"
    ECHECS="$ECHECS $t"
    return
  fi
  case "$SRC_ECHEC" in
    *" $nom "*)
      it_dire "  $t $v : ÉCHEC — la source $nom a déjà échoué"
      ECHECS="$ECHECS $t"
      return
      ;;
  esac
  case "$SRC_FAITES" in
    *" $nom "*)
      ;;
    *)
      mkdir -p "$PREFIX/venvs" || {
        ECHECS="$ECHECS $t"
        return
      }
      if [ "$nom" = "ci-yml" ]; then
        printf '%s\n' "$INLINE" > "$req"
      fi
      it_dire "  $t $v : venv $venv, -I -m pip install $DRAPEAUX_PIP -r $req"
      set -f
      # DRAPEAUX_PIP est découpé exprès (mots fixes, sans motif : set -f).
      if "$PY" -I -m venv --clear "$venv" </dev/null && "$vpy" -I -m pip install $DRAPEAUX_PIP -r "$req" </dev/null; then
        SRC_FAITES="$SRC_FAITES$nom "
      else
        set +f
        SRC_ECHEC="$SRC_ECHEC$nom "
        it_dire "  $t $v : ÉCHEC du venv ou de pip (source $nom) — rien n'est posé hors de $PREFIX"
        ECHECS="$ECHECS $t"
        return
      fi
      set +f
      ;;
  esac
  if [ "$cible" = "$PREFIX/bin/$t" ]; then
    if mkdir -p "$PREFIX/bin" && ln -sfn "$venv/bin/$t" "$PREFIX/bin/$t" && [ -x "$PREFIX/bin/$t" ]; then
      :
    else
      it_dire "  $t $v : ÉCHEC — point d'entrée $venv/bin/$t absent ou non lié sous $PREFIX/bin"
      ECHECS="$ECHECS $t"
      return
    fi
  fi
  if it_recu "$t" "$vus"; then
    it_dire "  $t $v : installé (venv $venv)"
    INSTALLES="$INSTALLES $t"
  else
    ECHECS="$ECHECS $t"
  fi
}

# --- (4bis) --appliquer : verrou, puis le doctor AVANT (le PATH de sonde seul) --
it_doctor() { # it_doctor <PATH de sonde> : rapport du doctor sur l'inventaire, stdout+stderr
  env DOCTOR_OS="$OS" "DOCTOR_PROBE_PATH=$1" "$BASH" "$DOCTOR" --inventory "$INV" </dev/null 2>&1
}
it_presents() { # it_presents : sur stdin un rapport du doctor ; un outil PRESENT par ligne
  sed -n -e 's/^  PRESENT ([^)]*)  *\([^ ]*\) .*$/\1/p' -e 's/^  PRESENT  *\([^ ]*\) .*$/\1/p'
}
AVANT=""
if [ "$MODE" = "appliquer" ]; then
  if ! mkdir -p "$PREFIX" || ! mkdir "$PREFIX/.verrou" 2>/dev/null; then
    it_refus "verrou $PREFIX/.verrou deja pose (une autre installation tourne, ou une installation interrompue) : rien n est fait ; retirez-le vous-meme si aucune ne tourne (exit 1)."
    exit 1
  fi
  trap 'rmdir "$PREFIX/.verrou" 2>/dev/null' EXIT
  if [ -r "$DOCTOR" ]; then
    AVANT="$(it_doctor "$PROBE" | it_presents)"
  fi
fi

# --- (5) chaque ligne outil de la plateforme ------------------------------------
it_dire "mode $MODE — plateforme $OS/$ARCH — préfixe $PREFIX — interpréteur $PY"
HORS=0
# Chaque commande de la boucle a son entrée propre (</dev/null, tube ou fichier) :
# aucune ne mange les lignes de DATA.
while IFS="$US" read -r tool os pin mode; do
  [ -n "$tool" ] || continue
  case ",$os," in
    ",any,"|*",$OS,"*)
      ;;
    *)
      HORS=$((HORS + 1))
      continue
      ;;
  esac
  if [ "$pin" = "-" ]; then
    SANS="$SANS $tool"
    continue
  fi
  rest="$pin"
  while [ -n "$rest" ]; do
    one="${rest%%$_pv*}"
    if [ "$one" = "$rest" ]; then
      rest=""
    else
      rest="${rest#*$_pv}"
    fi
    v="${one%%@*}"
    canal="${one#*@}"
    job="${canal#*$_par}"
    job="${job%%$_parf*}"
    job="${job%% *}"
    canal="${canal%%$_par*}"
    case "$canal" in
      pip-hash|curl-sha256)
        ;;
      *)
        it_dire "  $tool $v : canal $canal non installable par ce script — non installé"
        it_non "$tool"
        continue
        ;;
    esac
    case "$tool$v" in
      *[!A-Za-z0-9._+-]*)
        it_dire "  $tool $v : jeton ou version hors forme — non installé"
        ECHECS="$ECHECS $tool"
        continue
        ;;
    esac
    plats="$(it_job_os "$job")"
    if [ -z "$plats" ]; then
      it_dire "  $tool $v : épinglage introuvable (job $job sans runs-on lisible dans $CI) — non installé"
      ECHECS="$ECHECS $tool"
      continue
    fi
    case " $plats " in
      *" $OS/"*)
        ;;
      *)
        it_dire "  $tool $v : épinglé par le job $job pour :${plats:- aucune plateforme lue} — pas pour $OS, non installé"
        it_non "$tool"
        continue
        ;;
    esac
    if [ "$canal" = "curl-sha256" ]; then
      it_curl "$tool" "$v"
      break
    fi
    case " $plats " in
      *" $OS/$ARCH "*)
        ;;
      *)
        it_dire "  $tool $v : non installable ici — fermeture pip-hash résolue par le job $job pour :$plats, pas pour $OS/$ARCH"
        it_non "$tool"
        continue
        ;;
    esac
    jpy="$(it_job_py "$job")"
    [ -n "$jpy" ] || jpy="$JPY_ILLISIBLE"
    if [ "$jpy" != "$PYV" ]; then
      it_dire "  $tool $v : non installable ici — fermeture pip-hash résolue par le job $job pour CPython $jpy, interpréteur ${PYV:-illisible}"
      it_non "$tool"
      continue
    fi
    it_pip "$tool" "$v" "$mode"
    break
  done
done <<< "$DATA"

n_sans="$(printf '%s\n' $SANS | grep -c .)"
it_dire "aucun épinglage : non installés ($n_sans) :${SANS:- aucun}"
it_dire "hors de la plateforme $OS : $HORS lignes"

NEWPATH="$PREFIX/bin${VENVS//$US/:}"
it_dire 'ligne PATH a ajouter vous-meme (aucun profil n est edite) :'
printf '  export PATH=%q:"$PATH"\n' "$NEWPATH"

VUS_ABSENTS=""
MASQUES=""
if [ "$MODE" = "appliquer" ] && [ ! -r "$DOCTOR" ]; then
  it_dire "doctor illisible : $DOCTOR — aucun outil n'est prouvé présent, exit 1"
  VUS_ABSENTS=" doctor"
elif [ "$MODE" = "appliquer" ]; then
  dout="$(it_doctor "$NEWPATH:$PROBE")"
  drc=$?
  it_dire "doctor (re-sonde sous ce PATH, rc $drc) : $(printf '%s\n' "$dout" | sed -n '$p')"
  APRES="$(printf '%s\n' "$dout" | it_presents)"
  # Preuve POSITIVE : chaque outil posé ou déjà là doit être dit PRESENT (un
  # doctor sorti avant son rapport ne dit rien, donc rien n'est prouvé).
  for t in $INSTALLES $DEJA; do
    if ! printf '%s\n' "$APRES" | grep -qxF -- "$t"; then
      VUS_ABSENTS="$VUS_ABSENTS $t"
    fi
  done
  # Filet : un outil PRESENT avant l'installation et plus après est masqué par le PATH imprimé.
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    if ! printf '%s\n' "$APRES" | grep -qxF -- "$t"; then
      MASQUES="$MASQUES $t"
    fi
  done <<< "$AVANT"
  if [ -n "$VUS_ABSENTS" ]; then
    it_dire "doctor : posé ou déjà là, mais pas PRESENT sous ce PATH :$VUS_ABSENTS — exit 1"
  fi
  if [ -n "$MASQUES" ]; then
    it_dire "doctor : PRESENT avant, plus PRESENT sous ce PATH (masqué) :$MASQUES — exit 1"
  fi
fi

rc=0
[ -n "$ECHECS" ] && rc=1
[ -n "$VUS_ABSENTS" ] && rc=1
[ -n "$MASQUES" ] && rc=1
it_dire "$MODE : installés=${INSTALLES:- aucun} déjà là=${DEJA:- aucun} à installer=${A_FAIRE:- aucun} non installés=${NON:- aucun} échecs=${ECHECS:- aucun} — exit $rc"
exit "$rc"
