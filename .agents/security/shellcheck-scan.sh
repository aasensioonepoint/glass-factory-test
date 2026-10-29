#!/usr/bin/env bash
# Le shell du dépôt passe `shellcheck`, à l'ÉDITION.
#
# NOM DU FICHIER EN SECONDE LIGNE : NON. Un commentaire ouvrant par
# `# shellcheck` est lu comme une DIRECTIVE par l'outil, qui refuse alors de
# parser le fichier (SC1073/SC1072). Mesuré sur ce fichier même, au premier
# passage du scanner sur lui-même — il a trouvé son propre défaut avant de
# trouver celui des autres.
#
# ── POURQUOI IL EXISTE, ET CE QU'IL AJOUTE AUX GARDES DÉJÀ LÀ ────────────────
# Le dépôt avait trois lecteurs de shell, et un trou entre eux :
#   * `bash -n`            — la syntaxe, rien de plus. Il accepte `cd "$X"` sans
#                            garde, une variable non quotée, un `$?` qui parle
#                            d'autre chose que ce qu'on croit.
#   * `semgrep`            — des motifs de SÉCURITÉ nommés, pas la correction du
#                            shell.
#   * `bash-parse-oldest`  — le parse sous un bash < 4.4, une panne d'analyseur.
# Aucun ne voit un `cd` qui échoue et laisse le script continuer dans le mauvais
# répertoire. Mesuré le 2026-09-09 : **7 sites**, dont `core-scripts/verify.sh`
# lui-même — la porte de vérification.
#
# ── LA CONFIGURATION EST UN ARBITRAGE MESURÉ, PAS UN DÉFAUT D'OUTIL ─────────
# `shellcheck` **0.11.0** nu rend **574 findings à sévérité `style` sur les 78
# fichiers `*.sh` suivis de l'ARBRE DE TRAVAIL** (re-mesuré le 2026-09-13 ; le
# « 582 » d'avant avait vieilli). UN CHIFFRE DE RELEVÉ SE CITE AVEC SES TROIS
# COORDONNÉES — population, version, état de l'arbre — et il en manquait deux :
#   · population : le périmètre de CE scan comptait **80** fichiers ce jour-là
#     (`git ls-files` plus deux sans extension entrés par leur shebang) et
#     rendait le MÊME 574, au finding près — les deux fichiers ajoutés n'en
#     portent aucun. **CETTE POPULATION BOUGE À CHAQUE FICHIER SHELL AJOUTÉ** :
#     elle est passée à 82 le même jour avec `binome-trace.sh` et son banc. Le
#     verdict la REND à chaque passage (« N fichier(s) LUS ») — c'est lui qui
#     fait foi, jamais ce commentaire, qui date son relevé plutôt que de
#     prétendre le tenir à jour ;
#   · version : les mêmes 80 fichiers rendaient **613** sous 0.10.0 ;
#   · arbre : « 573 » était le compte à `787b384`, et le +1 vient d'un `SC2016`
#     introduit par CE correctif lui-même.
# La première rédaction attribuait l'écart 574/573 à la POPULATION : faux, il
# était TEMPOREL. Une explication causale fausse est pire qu'un chiffre périmé —
# elle enseigne la mauvaise règle.
# Câblé tel quel, il serait rouge au premier jour et on le désarmerait dans la
# semaine — la friction sans le bénéfice. Le tri, mesuré code par code :
#
#   SC2015  372  `A && B || C` — l'idiome de CE dépôt, partout. Bruit.
#   SC2016   76  quotes simples empêchant l'expansion — presque toujours voulu.
#   SC2034   53  variable « inutilisée » — faux dans un fichier sourcé.
#   SC1010   17  « ; avant done » — FAUX POSITIF ici : `tasks done T-…` passe
#                `done` en ARGUMENT de CLI, ce n'est pas un `for`.
#   SC1112    6  apostrophe typographique dans un commentaire français.
#   SC1087    2  « accolades pour un tableau » — FAUX POSITIF : `"$L[[:space:]]"`
#                est une classe de caractères d'un motif `grep`.
#
# Reste, après ce tri : **13 findings, tous vrais ou discutables** — 7 `cd` sans
# garde, 3 `ls | grep`, un `NVDK=set` ambigu, un `$?` fragile, et un vrai bug de
# quoting (`core-scripts/cadre.test.sh` affichait `defs ·6 hotes`, l'espace
# manquait). Les 13 ont été corrigés ou commentés avant ce câblage : la garde
# naît VERTE, ce qui est la seule façon qu'elle survive.
#
# ── CE QU'IL NE FAIT PAS ────────────────────────────────────────────────────
# Il ne remplace aucune des trois gardes ci-dessus, et il ne prétend pas à la
# sécurité : `shellcheck` lit la CORRECTION du shell, `semgrep` lit les motifs
# dangereux. Les deux sont nécessaires et aucun n'absorbe l'autre.
#
# ── SANS SHELLCHECK SUR LE PATH ─────────────────────────────────────────────
# `COVERAGE DEGRADED` sur stderr, exit 0. Jamais un faux propre, jamais un
# blocage. Même discipline que gitleaks et semgrep.
#
# Usage :
#   bash .agents/security/shellcheck-scan.sh            # arbre entier, verdict
#   bash .agents/security/shellcheck-scan.sh --hook     # post-édition : le fichier de la charge
#                                                       # stdin seulement, silencieux si propre
#   bash .agents/security/shellcheck-scan.sh <fichier…> # ciblé
#
# Sortie : 0 propre ou dégradé annoncé · 1 au moins un finding retenu, ou refus
#          (outil en échec, sortie incomplète, PÉRIMÈTRE NON LU) · 2 en --hook,
#          pour que le modèle le lise · 130 / 143 tué par INT / TERM, fichiers
#          temporaires retirés.
#          PÉRIMÈTRE NON LU, scan d'ARBRE seul (sans fichier nommé, ou --hook
#          sans charge) — refus, jamais « propre » ni « rien à mesurer » :
#            · `git ls-files` en échec — hors dépôt git, ou dépôt d'un autre
#              propriétaire (remède : `git config --global --add
#              safe.directory <racine>`) ;
#            · `mktemp` en échec — sous un mktemp GNU, TMPDIR absent, non
#              inscriptible ou non traversable ; illisible SEUL, il réussit
#              (mesuré, mode 300). Le `/usr/bin/mktemp` de macOS, sans
#              gabarit, IGNORE TMPDIR (mesuré : rc 0, sous /var/folders/…/T/).
#              Le message nomme le TMPDIR lu, et n'accuse jamais git ;
#            · un `*.sh` SUIVI absent du disque (sparse-checkout, `rm` sans
#              `git rm`) — compté, nommé, PÉRIMÈTRE INCOMPLET.
#          Le mode ciblé et le --hook à charge ne lisent JAMAIS `git ls-files` :
#          ils nomment leurs fichiers, et seul `mktemp` peut y refuser.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# SÉVÉRITÉ RETENUE — `warning` et au-dessus. `info`/`style` portent les 491
# notes du relevé, dont les 371 `A && B || C` : les inclure noierait le signal.
SEVERITE="warning"

# EXCLUSIONS — ensemble CLOS, chaque entrée avec la RAISON mesurée qui la
# justifie. Une exclusion sans raison est une porte dérobée ; le filet
# `shellcheck-scan.test.sh` refuse une entrée non commentée.
EXCLUS="SC1010,SC1087,SC2034,SC1112"

HOOK=0
FICHIERS=()
for arg in "$@"; do
  case "$arg" in
    --hook) HOOK=1 ;;
    -*)     printf 'shellcheck-scan: option inconnue « %s »\n' "$arg" >&2; exit 2 ;;
    *)      FICHIERS+=("$arg") ;;
  esac
done

# UN SHELL, AU SENS DE CE SCAN : `*.sh`, ou un shebang sh/bash/zsh/dash/ksh.
# La même règle sert au périmètre de l'arbre (plus bas) et au fichier du hook.
est_shell() {
  case "$1" in
    *.sh) return 0 ;;
  esac
  head -n1 "$1" 2>/dev/null | grep -qE '^#!.*\b(ba|z|da|k)?sh\b'
}

# MODE HOOK : LE FICHIER ÉDITÉ, PAS L'ARBRE. La première forme ignorait la charge
# PostToolUse et relisait tout le dépôt à CHAQUE Edit/Write — mesuré le
# 2026-09-29 : ~60 s par édition (dont ~33 s de shellcheck sur 83 fichiers et le
# reste en un `head | grep` par fichier suivi), y compris pour un `.md`. On lit
# `tool_input.file_path` sur stdin ; un fichier absent, hors de la racine,
# ignoré par git (la porte ne le lit pas non plus) ou qui n'est pas du shell
# sort 0 sans rien lancer, et une charge sans `file_path` aussi — rien à lire.
# SANS python, même doctrine que `semgrep-scan.sh --hook` : COVERAGE DEGRADED
# annoncé, exit 0, et `verify.sh` reste l'arbitre — jamais 60 s par édition en
# silence. Sans charge DU TOUT (stdin vide : un appel à la main), l'arbre entier.
# CAPACITÉ PERDUE, ET DITE : un `.sh` modifié HORS Edit/Write (Bash, sed…)
# n'est plus rattrapé au rescan que déclenchait l'édition suivante de n'importe
# quel fichier — `verify.sh` et la CI seuls le lisent désormais. ÉCART DE
# PÉRIMÈTRE, dans l'autre sens : un fichier NON suivi et non ignoré (un `Write`
# neuf) EST scanné ici, quand la porte, bornée à `git ls-files`, ne le lit pas.
if [ "$HOOK" -eq 1 ] && [ "${#FICHIERS[@]}" -eq 0 ] && [ ! -t 0 ]; then
  CHARGE="$(cat)"
  if [ -n "$CHARGE" ]; then
    # Résolveur CANONIQUE des hooks (copie tenue par test_python_hook_launchers).
    PY=""
    PY_PROBE='import sys; sys.stdout.write(sys.executable); sys.exit(sys.version_info[0] != 3)'
    PY_CR="$(printf '\r')"
    for c in python3 python; do
      PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
      case "$PY_CANDIDATE" in
        *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
      esac
      if [ -n "$PY_CANDIDATE" ]; then
        PY="$c"
        break
      fi
    done
    if [ -z "$PY" ]; then
      PY_UNAME=""
      command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"
      case "${OS-}:$PY_UNAME" in
        Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
          PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
          case "$PY_CANDIDATE" in
            *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
          esac
          [ -n "$PY_CANDIDATE" ] && PY="$PY_CANDIDATE"
          ;;
      esac
    fi
    if [ -z "$PY" ]; then
      echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
      echo "COVERAGE DEGRADED: shellcheck --hook — aucun python pour lire la charge ; hook INACTIF, verify.sh reste l'arbitre" >&2
      exit 0
    fi
    # OCTETS UTF-8 EN SORTIE, SANS FIN DE LIGNE : un `print()` sous Windows
    # écrit `\r\n`, `$(…)` ne retire que `\n`, et le `\r` restant faisait
    # échouer `[ -f ]` — donc exit 0, un faux propre sur chaque finding.
    # rc 3 = pas de `file_path` dans la charge.
    CIBLE="$(printf '%s' "$CHARGE" | "$PY" -c 'import sys,json
d=json.loads(sys.stdin.buffer.read().decode("utf-8"))
t=d.get("tool_input") if isinstance(d,dict) else None
p=t.get("file_path") if isinstance(t,dict) else None
if not isinstance(p,str) or not p:
    sys.exit(3)
sys.stdout.buffer.write(p.encode("utf-8"))' 2>/dev/null)"
    RC_PY=$?
    [ "$RC_PY" -eq 3 ] && exit 0
    if [ "$RC_PY" -ne 0 ]; then
      echo "COVERAGE DEGRADED: shellcheck --hook — charge illisible (rc=$RC_PY) ; fichier NON vérifié, verify.sh reste l'arbitre" >&2
      exit 0
    fi
    # Forme Windows (`C:\…`) : même conversion que le préfixe des hooks.
    case "$CIBLE" in
      ?:*|*\\*) _u="$(cygpath -u "$CIBLE" 2>/dev/null)" && CIBLE="$_u" ;;
    esac
    # Un chemin RELATIF se lit contre la racine, comme protect-paths.sh sur la
    # même charge — jamais contre le cwd du hook (un exit 0 muet sinon).
    case "$CIBLE" in
      /*) ;;
      *) CIBLE="$ROOT/$CIBLE" ;;
    esac
    [ -f "$CIBLE" ] || exit 0
    _dir="$(cd "$(dirname "$CIBLE")" 2>/dev/null && pwd -P)" || exit 0
    _root="$(cd "$ROOT" && pwd -P)"
    case "$_dir/" in
      "${_root%/}"/*) ;;
      *) exit 0 ;;
    esac
    git -C "$ROOT" check-ignore -q -- "$CIBLE" 2>/dev/null && exit 0
    est_shell "$CIBLE" || exit 0
    FICHIERS=("$CIBLE")
  fi
fi

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "COVERAGE DEGRADED: shellcheck absent du PATH — la correction du shell n'est PAS mesurée (install : README-SECURITY-SCAN-SETUP.md § shellcheck)" >&2
  exit 0
fi

# LE VERDICT NOMME SA VERSION, parce qu'il y en a AU MOINS TROIS en circulation
# et qu'aucune n'est épinglée : 0.11.0 sur un poste brew, 0.10.0 dans la jambe
# conteneur (Debian), plus celle de chaque runner CI — l'étape n'a pas d'`if:` et
# la matrice porte trois OS, donc « trois » est une BORNE BASSE, pas un compte.
#
# CE QUI EST MESURÉ, et la nuance décide tout (2026-09-13) : à la sévérité de
# CETTE porte — `warning` plus les quatre exclusions — 0.11.0 et 0.10.0 rendent
# tous deux `propre` sur les 80 fichiers : MÊME VERDICT. À sévérité `style`, en
# revanche, elles DIVERGENT — 574 findings en 0.11.0 contre 613 en 0.10.0, et
# `SC2317` (40 occurrences) n'existe plus en 0.11, remplacé par `SC2329`.
# L'écart est donc inerte LÀ OÙ LA PORTE DÉCIDE, et seulement là : d'où
# l'enregistrement de la version plutôt que l'épinglage, et d'où l'obligation
# que TOUT chiffre de relevé brut cité quelque part nomme la sienne.
# (Première rédaction : « les trois rendent le même relevé code par code ».
#  FAUX — généralisé d'une sévérité à toutes. Mesuré, puis corrigé.)
VERSION_SC="$(shellcheck --version 2>/dev/null | sed -n 's/^version: //p' | head -1)"
[ -n "$VERSION_SC" ] || VERSION_SC="inconnue"

# UN CODE DE REFUS, DÉFINI UNE FOIS, POUR TOUS LES REFUS — finding retenu,
# ECHEC EXECUTION (de git ou de `mktemp` au périmètre, ou de l'outil),
# PÉRIMÈTRE INCOMPLET, SORTIE INCOMPLÈTE.
# Défini AVANT le périmètre, dont le refus le lit. EN HOOK, 2 ET NON 1 : sur
# `PostToolUse`, Claude Code ne rend au MODÈLE que le stderr d'un exit 2 — un
# exit 1 ne va qu'à l'utilisateur, et le finding n'était jamais corrigé par
# l'agent qui venait de l'introduire. Même canal que `semgrep-scan.sh --hook`
# pour un FINDING ; sur une panne d'outil, semgrep dégrade (exit 0) et ce scan
# refuse (exit 2) — écart voulu, T-00001181. Seul
# `.claude/settings.json` enregistre ce hook. Un refus rendu en 1 en hook
# n'était jamais lu (mesuré : outil rc 3 en `--hook`, exit 1, ECHEC EXECUTION
# jeté) — L-00000136 : un refus dont le canal est jeté n'existe pas.
RC_REFUS=1
[ "$HOOK" -eq 1 ] && RC_REFUS=2

# LES FICHIERS TEMPORAIRES MEURENT AVEC LE SCAN, MÊME TUÉ (binôme S-00004149
# A-4). Sans piège, un SIGTERM pendant le scan d'arbre laissait la liste de
# `git ls-files` dans TMPDIR (mesuré : rc 143, 58 Ko laissés), et ERRS pendant
# l'outil. UN seul point de nettoyage, `nettoyer`, sur EXIT : aucun `rm` épars
# avant un `exit`. Sur INT et TERM, il nettoie puis RE-LÈVE le signal, pour que
# l'appelant voie une mort par signal (rc 130 / 143), jamais une sortie
# ordinaire. `nettoyer` rend le statut qu'il a reçu : un `exit N` garde son N.
# BORNE DITE : bash diffère un piège jusqu'à la fin de la commande au premier
# plan — un TERM reçu pendant l'outil attend la fin de l'outil (mesuré sous
# 3.2 et 5.x : nettoyé, rc 143, rien d'autre ne tourne après). Témoin : le
# banc `shellcheck-scan-arbre.test.sh`, cas (z) — tué par TERM, PUIS sortie
# ordinaire : `trap nettoyer EXIT` retiré, le banc restait vert sans ce
# second cas (mutant mesuré : 11 fichiers laissés).
LISTE=""
ERRS=""
nettoyer() {
  _rc_net=$?
  [ -z "$LISTE" ] || rm -f "$LISTE"
  [ -z "$ERRS" ] || rm -f "$ERRS"
  return "$_rc_net"
}
sur_signal() {
  nettoyer
  trap - EXIT INT TERM
  kill -s "$1" "$$"
  exit "$2"
}
trap nettoyer EXIT
trap 'sur_signal INT 130' INT
trap 'sur_signal TERM 143' TERM

# UN ÉCHEC DE `mktemp` EST LE SIEN, JAMAIS CELUI DE GIT NI DE L'OUTIL (binôme
# S-00004148 B-1, S-00004149 A-5). La forme d'avant, `LISTE="$(mktemp)" &&
# git …`, rendait le rc de mktemp sous le nom de git — mesuré, TMPDIR absent :
# « ECHEC EXECUTION (git ls-files rc=1) », et un remède qui envoyait chercher
# un dépôt git ; en mode ciblé, `2>""` faisait accuser l'OUTIL (« SORTIE
# INCOMPLÈTE … vise la sortie de shellcheck »). Le refus nomme la panne ET le
# TMPDIR lu. $1 : ce qui reste non lu, dit en clair. Le remède dit ce qui
# compte, mesuré sous mktemp GNU : exister, être inscriptible et traversable —
# pas « lisible » (un TMPDIR en mode 300 réussit). Témoin : le banc
# `shellcheck-scan-arbre.test.sh`, cas (w), sous son contrôle (w0).
refus_mktemp() {
  {
    printf 'shellcheck-scan: ECHEC EXECUTION (mktemp a échoué, TMPDIR=%s) — %s, aucun verdict rendu\n' \
      "${TMPDIR:-non posé}" "$1"
    printf 'Remède : TMPDIR doit nommer un répertoire existant, inscriptible et traversable, ou être retiré (mktemp prend alors son répertoire par défaut).\n'
  } >&2
  exit "$RC_REFUS"
}

# PÉRIMÈTRE — les fichiers SUIVIS qui sont du shell. `git ls-files`, jamais un
# glob nu : un glob ramasserait un backup d'éditeur et rougirait là où aucune
# autre machine ne le fait. Le shebang fait entrer `.githooks/pre-push` et
# `CADRE/serve.command`, qui n'ont pas d'extension.
# `-z`, ET `read -d ''` (bash 3.2 compris) : sans `-z`, `core.quotePath` (le
# défaut de git) rend un nom non ASCII entre guillemets, octets échappés en
# octal ; `[ -f ]` échouait sur ce texte et le fichier sortait du scan sans un
# mot — mesuré à 7ca2ec85 : `é.sh` suivi, porteur d'un SC2164, rendait
# « propre — 1 fichier(s) LUS », rc 0 (T-00001181, binôme S-00004134 A-2).
# Le témoin est `shellcheck-scan-arbre.test.sh`.
# LE RC DE GIT EST UN CANAL, ET IL ÉTAIT JETÉ : la liste arrivait par
# `< <(git … ls-files -z)`, dont bash 3.2 ne rend pas le code. Hors dépôt
# (mesuré à 50300cdb, un `x.sh` fautif dans un dossier sans `.git`) : `fatal`
# de git, puis « aucun fichier shell suivi — rien à mesurer », rc 0 — un faux
# propre (L-00000136). La liste passe donc par un fichier, et un rc non nul
# de git REFUSE le scan, au code du mode ; un `mktemp` en échec a SON refus
# (`refus_mktemp`, plus haut). Le remède nomme `safe.directory` : un dépôt d'un
# autre propriétaire fait échouer git (« dubious ownership », rc 128 — binôme
# S-00004148 B-4 ; témoin : cas (x), qui lit la ligne « Remède, propriétaire
# différent », le `fatal` de git citant déjà `safe.directory`). Le mode ciblé
# et le `--hook` à charge n'entrent pas ici : ils nomment leurs fichiers et ne
# lisent pas `git ls-files`.
# UNE ABSENCE N'EST PAS UN ZÉRO (binôme S-00004149 A-6) : `[ -f ] || continue`
# écartait EN SILENCE un `*.sh` SUIVI mais absent du disque — mesuré en
# sparse-checkout : « propre — 88 fichier(s) LUS » avec 2 `.sh` suivis jamais
# lus. Le compte de fichiers lus ne le trahit pas : il compte ce qui est ENTRÉ.
# Les `*.sh` suivis absents sont donc COMPTÉS, nommés (10 au plus, borne dite),
# et le scan REFUSE — PÉRIMÈTRE INCOMPLET, au code du mode, AVANT l'outil :
# un « propre » sur les seuls présents se lirait comme la population entière.
# BORNE DITE : un fichier suivi SANS extension et absent n'a pas de shebang à
# lire ; il n'est pas compté. Un lien symbolique suivi dont la cible manque
# compte comme absent : il n'est pas lu non plus. Témoin : cas (y).
if [ "${#FICHIERS[@]}" -eq 0 ]; then
  LISTE="$(mktemp)" || LISTE=""
  [ -n "$LISTE" ] || refus_mktemp "périmètre NON lu"
  git -C "$ROOT" ls-files -z >"$LISTE"
  RC_GIT=$?
  if [ "$RC_GIT" -ne 0 ]; then
    {
      printf 'shellcheck-scan: ECHEC EXECUTION (git ls-files rc=%s) — périmètre NON lu, aucun verdict rendu\n' \
        "$RC_GIT"
      printf 'Racine du scan : %s\n' "$ROOT"
      printf 'Remède : lancer le scan dans un dépôt git, ou nommer les fichiers (bash .agents/security/shellcheck-scan.sh <fichier…>).\n'
      printf 'Remède, propriétaire différent (git : dubious ownership) : git config --global --add safe.directory %s\n' \
        "$ROOT"
    } >&2
    exit "$RC_REFUS"
  fi
  ABSENTS=0
  ABS_NOMS=()
  while IFS= read -r -d '' rel; do
    [ -n "$rel" ] || continue
    f="$ROOT/$rel"
    if [ ! -f "$f" ]; then
      case "$rel" in
        *.sh)
          ABSENTS=$((ABSENTS + 1))
          [ "${#ABS_NOMS[@]}" -ge 10 ] || ABS_NOMS+=("$rel")
          ;;
      esac
      continue
    fi
    est_shell "$f" && FICHIERS+=("$f")
  done <"$LISTE"
  if [ "$ABSENTS" -gt 0 ]; then
    {
      printf 'shellcheck-scan: PÉRIMÈTRE INCOMPLET — %s fichier(s) *.sh SUIVI(S) ABSENT(S) du disque — NON lus, aucun verdict rendu\n' \
        "$ABSENTS"
      printf '(%s fichier(s) shell présent(s), non scannés : un « propre » sur eux seuls se lirait comme la population entière)\n' \
        "${#FICHIERS[@]}"
      [ "$ABSENTS" -le 10 ] || printf '(liste bornée aux 10 premiers sur %s)\n' "$ABSENTS"
      printf '  %s\n' "${ABS_NOMS[@]}"
      printf 'Remède : restaurer (git checkout -- <fichier>) ou retirer (git rm <fichier>) ; en sparse-checkout, élargir le cône (git sparse-checkout disable) ou nommer les fichiers présents (bash .agents/security/shellcheck-scan.sh <fichier…>).\n'
    } >&2
    exit "$RC_REFUS"
  fi
fi

if [ "${#FICHIERS[@]}" -eq 0 ]; then
  [ "$HOOK" -eq 1 ] && exit 0
  echo "shellcheck-scan: aucun fichier shell suivi — rien à mesurer" >&2
  exit 0
fi

# LA LOCALE DE L'OUTIL EST VÉRIFIÉE, JAMAIS SUPPOSÉE (T-00001181). Sous locale
# C, la 0.10.0 (glibc, jambe conteneur) plante en ÉCRIVANT un nom non ASCII
# (`hPutChar: invalid argument`) : sortie tronquée avant le code, refus sans
# chemin, et en mode ciblé un faux « propre ». Une locale UTF-8 est donc posée
# pour le SEUL appel de l'outil, et chaque candidate est VÉRIFIÉE (`locale
# charmap` doit rendre UTF-8). La graphie est reprise VERBATIM de la liste :
# macOS accepte `C.UTF-8` et refuse `C.utf8`, glibc liste `C.utf8` — ni regex
# ni casse à deviner. UN seul site `locale`, stderr jeté : une locale absente
# s'y plaint, et un hook propre doit rester à zéro octet.
# LISTE BORNÉE, quatre graphies : hors d'elles, la locale héritée reste, et une
# sortie que l'outil n'a pas pu écrire devient le refus SORTIE INCOMPLÈTE plus
# bas, jamais un verdict. `command -v` d'abord : un hôte sans `locale` (musl,
# busybox) ne lance pas une commande absente. Sous Windows, le binaire natif
# `shellcheck.exe` ignore LC_ALL : même filet, le refus nommé.
LOC_SC=""
if command -v locale >/dev/null 2>&1; then
  for cand in C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8; do
    CM_SC="$(LC_ALL="$cand" locale charmap 2>/dev/null)"
    if [ "$CM_SC" = "UTF-8" ]; then
      LOC_SC="$cand"
      break
    fi
  done
fi

ERRS="$(mktemp)" || ERRS=""
[ -n "$ERRS" ] || refus_mktemp "population NON lue"
# L'`export` est CONFINÉ au sous-shell de la substitution : `grep`, `sed` et
# `head` plus bas gardent la locale de l'appelant. Un seul appel, et aucun
# tableau d'environnement vide à développer (bash 3.2).
SORTIE="$( [ -n "$LOC_SC" ] && export LC_ALL="$LOC_SC"; shellcheck -f gcc -s bash -S "$SEVERITE" -e "$EXCLUS" "${FICHIERS[@]}" 2>"$ERRS")"
RC_SC=$?
# LE CODE DE RETOUR DE L'OUTIL EST UN CANAL, ET IL ÉTAIT JETÉ. La forme d'avant —
# `2>/dev/null) || true` — détruisait à la fois le rc ET stderr : toute panne
# d'EXÉCUTION (option refusée, fichier illisible, argv trop long, binaire cassé)
# laissait `SORTIE` vide, donc N=0, donc « propre », donc exit 0. Reproduit au
# stub le 2026-09-13 : rc=3 de l'outil, verdict « propre — 80 fichier(s) », sur
# une population JAMAIS LUE. C'est exactement le faux propre que l'en-tête de ce
# fichier jure de ne pas produire (L-00000136 : un mécanisme dont le canal de
# retour est jeté n'existe pas).
#   rc 0 = propre · rc 1 = findings · rc >= 2 = l'outil n'a pas lu la population.
if [ "$RC_SC" -ge 2 ]; then
  {
    printf 'shellcheck %s: ECHEC EXECUTION (rc=%s) — population NON lue, aucun verdict rendu\n' \
      "$VERSION_SC" "$RC_SC"
    printf '(stderr borné aux 20 premières lignes)\n'
    head -n 20 "$ERRS"
    printf 'Remède : rejouer `shellcheck -f gcc -s bash -S %s -e %s <un fichier>` à la main.\n' \
      "$SEVERITE" "$EXCLUS"
  } >&2
  exit "$RC_REFUS"
fi
# Le refus qui suit lit le compte ET stderr ; ERRS est retiré par `nettoyer`.
N="$(printf '%s' "$SORTIE" | grep -c . || true)"
# SORTIE INCOMPLÈTE — UN VERDICT N'EST RENDU QUE SUR UN RÉSULTAT COHÉRENT.
# Deux signes qu'il ne l'est pas : (1) l'outil a écrit sur stderr, alors qu'il
# n'y écrit RIEN en rc 0 comme en rc 1 (mesuré sur 0.11.0, 0 octet) — un
# plantage d'écriture (`hPutChar`) y laisse sa trace et tronque stdout, quel
# que soit son rc ; (2) rc non nul sans une seule ligne reçue — le faux propre
# latent : N=0 donnait « propre », exit 0, sur une sortie PERDUE. Ce n'est PAS
# un COVERAGE DEGRADED, dont le jeton est exit 0 ici : c'est un refus, au code
# du mode, et il dit que la panne est celle de l'outil.
# BORNE DITE (binôme S-00004133 B-3) : le « 0 octet sur stderr » est mesuré sur
# le binaire 0.11.0 seul ; un wrapper qui écrit sur stderr en succès (shim npm,
# snap) déclenche ce refus à chaque appel — le remède imprimé le nomme. Un nom
# hors UTF-8 valide fait planter l'outil même sous C.UTF-8 (mesuré sur 0.11.0,
# macOS, argv : `hPutChar … cannot encode character`) : renommer est le remède.
if [ -s "$ERRS" ] || { [ "$RC_SC" -ne 0 ] && [ "${N:-0}" -eq 0 ]; }; then
  {
    printf 'shellcheck %s: SORTIE INCOMPLÈTE (rc=%s, locale=%s) — population NON certifiée, aucun verdict rendu\n' \
      "$VERSION_SC" "$RC_SC" "${LOC_SC:-héritée}"
    printf '(stdout reçu, tel quel)\n'
    printf '%s\n' "$SORTIE"
    printf '(stderr borné aux 20 premières lignes)\n'
    head -n 20 "$ERRS"
    printf 'Ce refus vise la sortie de shellcheck, pas votre édition.\n'
    printf 'Remède : relancer sous LC_ALL=C.UTF-8 ; locale -a doit lister une locale UTF-8 (C.UTF-8, C.utf8, en_US.UTF-8 ou en_US.utf8).\n'
    printf 'Un nom de fichier hors UTF-8 valide fait planter shellcheck même sous C.UTF-8 (hPutChar, mesuré sur 0.11.0) : renommez le fichier.\n'
    printf 'Un wrapper (npm, snap) qui écrit sur stderr en succès déclenche ce refus : appelez le binaire directement.\n'
  } >&2
  exit "$RC_REFUS"
fi

if [ "${N:-0}" -eq 0 ]; then
  [ "$HOOK" -eq 1 ] && exit 0
  printf 'shellcheck %s: propre — %s fichier(s) LUS, sévérité >= %s, exclusions [%s]\n' \
    "$VERSION_SC" "${#FICHIERS[@]}" "$SEVERITE" "$EXCLUS"
  exit 0
fi

# LE REFUS NOMME SON MOTIF ET SON REMÈDE, jamais un compte nu.
{
  printf 'shellcheck %s: %s finding(s) sur %s fichier(s) — sévérité >= %s\n' \
    "$VERSION_SC" "$N" "${#FICHIERS[@]}" "$SEVERITE"
  printf '%s\n' "$SORTIE"
  printf '\nRemède : corriger, ou — si le motif est un FAUX POSITIF mesuré — poser\n'
  printf '`# shellcheck disable=SCxxxx` sur la ligne AVEC une phrase qui dit pourquoi.\n'
  printf 'Une exclusion sans raison est une porte dérobée.\n'
} >&2
# 2 en hook, 1 sinon : voir RC_REFUS, plus haut.
exit "$RC_REFUS"
