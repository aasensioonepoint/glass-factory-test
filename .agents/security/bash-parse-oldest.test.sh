#!/usr/bin/env bash
# bash-parse-oldest.test.sh — SIBLING net for the T-00000477 class.
#
# ── LA CLASSE, CORRIGÉE LE 2026-09-09 (T-00000481) ────────────────────────────
# La rédaction d'origine disait « a QUOTED "$( … )" command substitution », et
# prescrivait la DÉQUOTE comme remède. LES DEUX SONT FAUX, mesuré sous
# /bin/bash 3.2.57 contre bash 5.3.15 :
#
#   forme                         apostrophes dans le corps   bash 3.2 -n
#   X="$(cat <<FIN … FIN)"                 0                     rc 0
#   X="$(cat <<FIN … FIN)"                 1                     rc 2
#   X=$(cat <<FIN … FIN)     <- DÉQUOTÉ    1                     rc 2   <- !!
#   X="$(cat <<FIN … FIN)"                 2                     rc 0
#   X=$(cat <<FIN … FIN)     <- DÉQUOTÉ    2                     rc 0
#   X="$(cat <<FIN … FIN)"                 3                     rc 2
#
# LA QUOTE N'Y EST POUR RIEN. Le discriminant est un nombre IMPAIR d'apostrophes
# dans la région de la substitution : le scanner de comsub de bash < 4.4 lit le
# corps du heredoc comme du shell et laisse une quote ouverte. Déquoter ne
# protège de RIEN.
#
# CE QUE LE FAUX REMÈDE A COÛTÉ. Il était écrit ici ET dans semgrep-scan.sh, et
# il a été suivi : trois sites ont été écrits en graphie déquotée
# (semgrep-scan.sh:1347 et :1541, .claude/hooks/pre-ask-arbitrate.sh:52) — et le
# localisateur (p2), dont le motif EXIGEAIT la quote, était aveugle sur eux. Le
# dépôt a fabriqué son propre angle mort en appliquant sa propre consigne.
#
# LE REMÈDE RÉEL : sortir le heredoc de la substitution (l'écrire dans un
# fichier, puis le lire), ou renoncer à la substitution. La parité paire n'est
# PAS un remède : elle est accidentelle, personne ne la maintient, et une
# apostrophe ajoutée demain la casse.
#
# Auto-discovered by core-scripts/run-bash-tests.sh (glob *.test.sh).
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# allows-missing: bash
#
# ── PÉRIMÈTRE, ET POURQUOI IL N'EST PAS « TOUT LE DÉPÔT » ─────────────────────
# T-00000481 demandait d'étendre au-delà de `.agents/security/`. C'est fait —
# mais sur les préfixes que LE KIT POSSÈDE, jamais sur l'arbre entier.
#
# La raison est écrite dans le sinistre que ce dépôt a déjà payé : une suite qui
# VOYAGE, qui est découverte par le glob de run-bash-tests.sh, et qui juge du
# code que l'adoptant a écrit, ROUGIT LA PORTE DE CHAQUE PROJET ADOPTANT. Ce
# filet voyage (aucune règle `strip:`/`keep:`/`own:` de .template-exclude ne le
# vise). Il ne juge donc que les fichiers du kit, qui sont les mêmes chez tout
# le monde.
#
# `.codex/hooks/` est cité par T-00000481 mais ne contient AUCUN `.sh` (14
# fichiers suivis, tous `.py`) : rien à y étendre, et le dire vaut mieux que de
# laisser croire à une couverture.
#
# BORNES DÉCLARÉES :
#   - `-n` SEULEMENT. Un script peut passer `-n` sous 3.2 et mourir au runtime
#     (tableaux associatifs, ${var^^}, mapfile). Ce filet ne dit rien de ça.
#   - Là où aucun bash < 4 n'existe, (p1) SKIPPE et l'annonce. La CI Linux n'a
#     que du bash 5.x : la couverture RÉELLE est macOS avec /bin/bash 3.2, pas
#     « la CI ».
#   - Les fichiers non suivis, et les .sh fabriqués à l'exécution par les
#     fixtures, sont hors `git ls-files` donc hors filet.
#   - Le jour de son élargissement, ce filet est VERT sur les 61 fichiers
#     nouvellement couverts : c'est un filet de NON-RÉGRESSION, pas un
#     correctif. Il ne trouve rien aujourd'hui — c'est voulu, et c'est dit.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

# --- OLDEST bash selection -----------------------------------------------------
# Duplicated from semgrep-scan.test.sh S2.4 ON PURPOSE (no shared helper): this
# suite must stay autonomous for étage A of test_adopting_gate. SUITE_BASH is
# defined HERE, BEFORE CANDS_STR, or `set -u` kills the suite on an unbound
# variable before it can announce its SKIP. `${SUITE_BASH_CANDIDATES-…}` uses NO
# colon: UNSET => default list; SET even EMPTY => it REPLACES the list (the
# set-but-empty case is what run-bash-tests.sh's channel proof exercises; a `:-`
# would fold it into "default" and kill that proof silently).
SUITE_BASH="${BASH:-$(command -v bash)}"
CANDS_STR="${SUITE_BASH_CANDIDATES-$SUITE_BASH /bin/bash /usr/bin/bash}"
read -r -a CANDS <<< "$CANDS_STR" || true
OLDEST=""; OLDEST_MAJ=""; SEEN=""; SKIPPED=""
for cand in ${CANDS[@]+"${CANDS[@]}"}; do
  if [ ! -x "$cand" ]; then SKIPPED="$SKIPPED $cand(absent)"; continue; fi
  maj="$("$cand" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null)" || maj=""
  case "$maj" in
    ''|*[!0-9]*) SKIPPED="$SKIPPED $cand(sonde-KO)"; continue ;;
  esac
  SEEN="$SEEN $cand:$maj"
  if [ -z "$OLDEST_MAJ" ] || [ "$maj" -lt "$OLDEST_MAJ" ]; then OLDEST_MAJ="$maj"; OLDEST="$cand"; fi
done

# --- PÉRIMÈTRE — les préfixes que LE KIT POSSÈDE, jamais l'arbre de l'adoptant --
# Liste CLOSE et commentée. `core-scripts/` y est parce que c'est là que vivent
# verify.sh et run-bash-tests.sh ; un adoptant qui y dépose ses propres scripts
# les verra donc mesurés — conséquence ASSUMÉE et dite, pas découverte.
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null)" || ROOT=""
[ -n "$ROOT" ] || fail "(perimetre) racine git introuvable depuis $HERE"
PREFIXES=".agents/ .claude/ .codex/ .gemini/ .kimi-code/ .githooks/ core-scripts/"

# Un fichier est du SHELL s'il porte `.sh` OU un shebang shell. Le shebang fait
# entrer `.githooks/pre-push` et `CADRE/serve.command`, qui n'ont pas
# d'extension — un `#!…python3` reste dehors.
est_shell() {
  case "$1" in
    *.sh) return 0 ;;
  esac
  head -n1 "$ROOT/$1" 2>/dev/null | grep -qE '^#!.*\b(ba|z|da|k)?sh\b'
}
dans_perimetre() {
  for p in $PREFIXES; do
    case "$1" in
      "$p"*) return 0 ;;
    esac
  done
  return 1
}

# --- (p1) MEASURE — the AUTHORITY where a bash < 4 exists -----------------------
# Tout fichier shell SUIVI sous les préfixes du kit — *.test.sh COMPRIS, qui
# portent la forme dans leurs fixtures, voyagent, et tournent sous le bash du
# PATH — doit PARSER sous le plus vieux bash. `git ls-files`, JAMAIS un glob nu :
# un glob ramasserait un backup d'éditeur ou un x.sh égaré et rougirait là où
# aucune autre machine ne le fait.
if [ -z "$OLDEST" ] || [ "$OLDEST_MAJ" -ge 4 ]; then
  cand_desc="${SEEN# }"
  [ -n "$cand_desc" ] || cand_desc="aucun — SUITE_BASH_CANDIDATES défini vide"
  [ -z "$SKIPPED" ] || cand_desc="$cand_desc ; écartés :${SKIPPED}"
  echo "  SKIP (p1): aucun bash < 4 sur cette machine (candidats : $cand_desc) — parse des .sh sous /bin/bash 3.2 NON mesuré"
else
  [ -z "$SKIPPED" ] || ok "(p1) candidats écartés, nommés et non silencieux :${SKIPPED}"
  n=0
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    dans_perimetre "$rel" || continue
    f="$ROOT/$rel"
    [ -f "$f" ] || continue
    est_shell "$rel" || continue
    "$OLDEST" -n "$f"; rc=$?
    [ "$rc" -eq 0 ] || fail "(p1) $rel ne parse pas sous bash $OLDEST_MAJ ($OLDEST), rc=$rc — la classe T-00000477 a récidivé. Cause : un nombre IMPAIR d'apostrophes dans une substitution de commande qui ouvre un heredoc. Remède : SORTIR le heredoc de la substitution (l'écrire dans un fichier, puis le lire) — déquoter ne protège de RIEN, c'est mesuré."
    n=$((n + 1))
  done < <(git -C "$ROOT" ls-files)
  # Un `ok` par fichier noierait le journal (des dizaines de lignes) ; on rend le
  # COMPTE, qui est ce qui prouve la non-vacuité.
  [ "$n" -gt 0 ] || fail "(p1) aucun fichier shell balayé — git ls-files n'a rien rendu sous les préfixes du kit"
  # PLANCHER DE NON-VACUITÉ, calibré bas EXPRÈS : il doit rougir si le périmètre
  # s'effondre (préfixe renommé, est_shell cassé), sans jamais rougir chez un
  # adoptant qui aurait élagué des surfaces d'hôtes qu'il n'utilise pas.
  [ "$n" -ge 20 ] || fail "(p1) périmètre anormalement petit : $n fichier(s) — un préfixe a-t-il été renommé ?"
  ok "(p1) $n fichier(s) shell du kit parsent sous bash $OLDEST_MAJ ($OLDEST)"
fi

# --- (p2) LOCALISATEUR — text-only, interpreter-independent, BOUNDED TO NON-TESTS
# The *.test.sh carry the form in their fixtures BY CONSTRUCTION and are covered
# by (p1) alone, so (p2) skips them. It pins the deliberate debt: gitleaks-scan.sh
# carries the form at :272 and :307 (its correction is a task of its own —
# security-gate: out of this write-set). RED IN BOTH DIRECTIONS: a NEW site, or
# the debt paid without removing the pin.
#
# BLIND SPOTS — named here rather than fixed (widening the pattern widens the
# false positive, and (p1) covers them ALL where a bash < 4 exists):
#   - a heredoc on the NEXT line             (assign, then  cmd redirects a heredoc)
#   - a quoted comsub NOT in an assignment   (echo of a comsub that opens a heredoc)
#   - a double-quoted heredoc delimiter, and a space before the delimiter word
#   - a comsub that does NOT open the string (a prefix before the comsub)
#   - a tableau element                      (the comsub is an array item)
# — the last two because the motif needs `="$(` ADJACENT. SEES TOO MUCH: a
# here-string, and any assign+heredoc pair sharing one line. It says WHERE to
# look; it proves nothing — (p1) proves.
# LE MOTIF NE PEUT PLUS EXIGER LA QUOTE. `=\"?\$\(` voit les DEUX graphies :
# c'est la correction qui rend visibles les trois sites écrits en suivant le
# faux remède (semgrep-scan.sh:1347 et :1541, pre-ask-arbitrate.sh:52).
# `"` n'a rien à échapper en ERE — un `\"` y est un échappement PARASITE, et
# grep l'avertit sur stderr (bruit qui se lit comme une panne du filet).
MOTIF='="?\$\(.*<<-?'"'"'?[A-Za-z_]+'

# DETTE ÉPINGLÉE — chemin relatif à la RACINE depuis l'élargissement, et une
# ligne par fichier. Ces sites parsent aujourd'hui parce que leurs corps portent
# un nombre PAIR d'apostrophes : c'est ACCIDENTEL, personne ne le maintient, et
# c'est (p1) — pas cette épingle — qui les garde. L'épingle sert à refuser un
# site NOUVEAU. Rouge DANS LES DEUX SENS : un site de plus, ou une dette payée
# sans retrait de son épingle.
DETTE="\
.agents/security/gitleaks-scan.sh 2
.agents/security/semgrep-scan.sh 2
.claude/hooks/pre-ask-arbitrate.sh 1"

dette_attendue() {  # $1 = chemin relatif racine ; rend le compte, ou vide
  printf '%s\n' "$DETTE" | while IFS=' ' read -r chemin compte; do
    [ "$chemin" = "$1" ] && printf '%s' "$compte"
  done
}

p2_bad=0
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  dans_perimetre "$rel" || continue
  case "$rel" in
    *.test.sh) continue ;;   # fixtures : ils PORTENT la forme par construction, (p1) les couvre
  esac
  f="$ROOT/$rel"
  [ -f "$f" ] || continue
  est_shell "$rel" || continue
  c="$(grep -cE "$MOTIF" "$f" 2>/dev/null || true)"
  [ -n "$c" ] || c=0
  attendu="$(dette_attendue "$rel")"
  if [ -n "$attendu" ]; then
    [ "$c" -eq "$attendu" ] \
      || fail "(p2) dette épinglée $rel attendue à $attendu site(s), vue $c — corrigée sans retrait de l'épingle, ou nouveau site apparu"
  else
    if [ "$c" -ne 0 ]; then
      p2_bad=1
      echo "  (p2) site hors dette : $rel ($c) :"
      grep -nE "$MOTIF" "$f"
    fi
  fi
done < <(git -C "$ROOT" ls-files)
[ "$p2_bad" -eq 0 ] \
  || fail "(p2) un site de la forme hors dette épinglée — SORS le heredoc de la substitution (écris-le dans un fichier, puis lis-le). NE LE DÉQUOTE PAS : c'est mesuré inopérant, la quote n'est pas la cause."
# Chaque épingle doit désigner un fichier qui EXISTE, sinon elle ne mesure rien.
printf '%s\n' "$DETTE" | while IFS=' ' read -r chemin _compte; do
  git -C "$ROOT" ls-files --error-unmatch -- "$chemin" >/dev/null 2>&1 \
    || fail "(p2) $chemin introuvable — l'épingle ne mesure plus rien"
done
ok "(p2) localisateur: $(printf '%s\n' "$DETTE" | grep -c .) fichier(s) de dette épinglés, zéro site hors dette"

echo "PASS: bash-parse-oldest ($pass check(s))"
