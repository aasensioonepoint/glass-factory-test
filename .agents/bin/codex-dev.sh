#!/usr/bin/env bash
# codex-dev.sh — lanceur VERIFIE du dev Codex (T-01M5PTFPBDBXE3KMZNHP5DE31A, lot A ; decision pilote S-01M5Q52QHWWC0YTFFK39EEH3EG).
#
# Seule forme pre-approuvee dans .claude/settings.json : `bash .agents/bin/codex-dev.sh …`, lancee depuis la RACINE.
# Grammaire FERMEE :
#   codex-dev.sh --worktree <nom> --model <m> [--effort low|medium|high|xhigh] --mandat <fichier> [--dry-run]
#   codex-dev.sh --help            (seul)
# Toute autre option (-s, -c, --add-dir, --dangerously-*, -C, -p, --, --x=y), un doublon, un positionnel, une valeur
# manquante ou commencant par « - », --help combine : `codex-dev: REFUS — <cause>` sur stderr, rc 3, codex jamais lance.
#
# Cible : <racine reelle>/.claude/worktrees/<nom>, un worktree LIE de la racine (worktree PRINCIPAL), dont l'arbre
# .codex/ est ENTIER egal au HEAD de la racine (aucun ecart, aucun non-suivi, ignores compris).
# Appel : `codex exec -C <cible> -s workspace-write`, network_access=false et writable_roots=[] DEMANDES (effet sous
# Codex non mesure), mandat sur stdin.
#
# BORNES (ce lanceur NE CONFINE PAS) : Codex echappe aux gardes de Claude, lit tout le disque, ecrit /tmp et $TMPDIR ;
# BASH_ENV, SHELLOPTS (xtrace + PS4 a substitution : code execute, mesure) et BASHOPTS sont lus par bash AVANT la
# 1re ligne (l'unset ci-dessous ne protege que les enfants) ; une fenetre TOCTOU separe les controles de l'exec ;
# une copie de ce fichier dans un worktree, lancee depuis ce worktree, n'est pas lui ; `codex`, `git` et `dirname`
# sont resolus par PATH (le premier `codex` du PATH est lance tel quel) ; les fonctions exportees des commandes
# ci-dessous sont retirees, mais une fonction exportee nommee `builtin` n'est pas couverte.
# Mandat : fichier regulier, chemin reel sous <racine>/docs/tasks/, /tmp/, /private/tmp/ ou $TMPDIR, sinon REFUS ;
# la zone n'est PAS une frontiere : un lien dur ou un $TMPDIR forge y fait entrer tout fichier lisible.
builtin unset -f builtin unset set command exec exit printf echo test '[' : compgen shift cd pwd dirname git codex read continue

set -uo pipefail

# Avant le premier git : tout GIT_* exporte, puis CODEX_HOME, BASH_ENV, ENV, CDPATH.
for _v in $(compgen -e); do
  case "$_v" in
    GIT_*) unset "$_v" ;;
  esac
done
unset CODEX_HOME BASH_ENV ENV CDPATH

refus() {
  printf 'codex-dev: REFUS — %s\n' "$1" >&2
  exit 3
}

usage() {
  printf '%s\n' \
    "usage: bash .agents/bin/codex-dev.sh --worktree <nom> --model <m> [--effort low|medium|high|xhigh] --mandat <fichier> [--dry-run]" \
    "       bash .agents/bin/codex-dev.sh --help" \
    "Lance \`codex exec -s workspace-write\` (reseau coupe DEMANDE, effet non mesure) dans <racine>/.claude/worktrees/<nom>, mandat sur stdin." \
    "Refus : codex-dev: REFUS — <cause> sur stderr, rc 3, codex jamais lance."
}

# chemin reel d'un repertoire, vide s'il n'existe pas
reel() {
  (cd -P -- "$1" 2>/dev/null && pwd -P)
}

if [ "$#" -eq 1 ] && [ "$1" = "--help" ]; then
  usage
  exit 0
fi
[ "$#" -gt 0 ] || refus "aucun argument (attendu : --worktree, --model, --mandat, ou --help seul)"

WT=""
MODEL=""
EFFORT=""
MANDAT=""
DRY=0
_vu_wt=0
_vu_model=0
_vu_effort=0
_vu_mandat=0
while [ "$#" -gt 0 ]; do
  _opt="$1"
  case "$_opt" in
    --worktree|--model|--effort|--mandat)
      [ "$#" -ge 2 ] || refus "valeur manquante pour $_opt"
      _val="$2"
      case "$_val" in
        "") refus "valeur vide pour $_opt" ;;
        -*) refus "valeur de $_opt commencant par « - »" ;;
      esac
      case "$_opt" in
        --worktree)
          [ "$_vu_wt" -eq 0 ] || refus "option en double : $_opt"
          _vu_wt=1
          WT="$_val"
          ;;
        --model)
          [ "$_vu_model" -eq 0 ] || refus "option en double : $_opt"
          _vu_model=1
          MODEL="$_val"
          ;;
        --effort)
          [ "$_vu_effort" -eq 0 ] || refus "option en double : $_opt"
          _vu_effort=1
          EFFORT="$_val"
          ;;
        --mandat)
          [ "$_vu_mandat" -eq 0 ] || refus "option en double : $_opt"
          _vu_mandat=1
          MANDAT="$_val"
          ;;
      esac
      shift 2
      ;;
    --dry-run)
      [ "$DRY" -eq 0 ] || refus "option en double : $_opt"
      DRY=1
      shift
      ;;
    --help)
      refus "--help se joue seul"
      ;;
    *)
      refus "argument hors grammaire : $_opt"
      ;;
  esac
done

[ "$_vu_wt" -eq 1 ] || refus "--worktree manquant"
[ "$_vu_model" -eq 1 ] || refus "--model manquant"
[ "$_vu_mandat" -eq 1 ] || refus "--mandat manquant"
if [ "$_vu_effort" -eq 1 ]; then
  case "$EFFORT" in
    low|medium|high|xhigh) : ;;
    *) refus "--effort hors liste (low|medium|high|xhigh) : $EFFORT" ;;
  esac
fi

_motif='^[A-Za-z0-9][A-Za-z0-9._-]*$'
[[ "$WT" =~ $_motif ]] || refus "nom de worktree hors motif : $WT"
[[ "$MODEL" =~ $_motif ]] || refus "modele hors motif : $MODEL"
case "$WT" in
  *..*) refus "nom de worktree avec « .. » : $WT" ;;
esac
case "$MODEL" in
  *..*) refus "modele avec « .. » : $MODEL" ;;
esac

# Racine = le depot qui porte CE fichier, et il doit en etre le worktree PRINCIPAL.
_ici="$(reel "$(dirname -- "${BASH_SOURCE[0]}")")"
[ -n "$_ici" ] || refus "repertoire du lanceur illisible"
RACINE="$(reel "$_ici/../..")"
[ -n "$RACINE" ] || refus "racine illisible"
_top="$(git -C "$RACINE" rev-parse --show-toplevel 2>/dev/null)" || refus "racine hors depot git : $RACINE"
[ "$(reel "$_top")" = "$RACINE" ] || refus "le lanceur n'est pas a la racine de son depot"
_gd="$(git -C "$RACINE" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || refus "git-dir de la racine illisible"
_cd="$(git -C "$RACINE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || refus "common-dir de la racine illisible"
_gd="$(reel "$_gd")"
_cd_racine="$(reel "$_cd")"
[ -n "$_cd_racine" ] || refus "common-dir de la racine illisible"
[ "$_gd" = "$_cd_racine" ] || refus "racine non principale (lanceur lance depuis un worktree lie)"

# Cible = <racine reelle>/.claude/worktrees/<nom>, sans lien, worktree lie de CETTE racine.
CIBLE="$RACINE/.claude/worktrees/$WT"
[ ! -L "$CIBLE" ] || refus "la cible est un lien : $CIBLE"
[ -d "$CIBLE" ] || refus "worktree absent : $CIBLE"
[ "$(reel "$CIBLE")" = "$CIBLE" ] || refus "chemin reel de la cible different de $CIBLE"
_top="$(git -C "$CIBLE" rev-parse --show-toplevel 2>/dev/null)" || refus "cible hors depot git : $CIBLE"
[ "$(reel "$_top")" = "$CIBLE" ] || refus "la cible n'est pas la racine d'un worktree : $CIBLE"
_gd="$(git -C "$CIBLE" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || refus "git-dir de la cible illisible"
_cd="$(git -C "$CIBLE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || refus "common-dir de la cible illisible"
_gd="$(reel "$_gd")"
_cd="$(reel "$_cd")"
[ "$_gd" != "$_cd" ] || refus "la cible n'est pas un worktree lie (clone ou depot propre)"
[ "$_cd" = "$_cd_racine" ] || refus "la cible n'est pas un worktree de la racine (common-dir different)"
# git-dir de la cible = <common-dir>/worktrees/<id> exactement : un git-dir deplace porte un index forge.
case "$_gd" in
  "$_cd_racine"/worktrees/*/*) refus "git-dir de la cible hors de $_cd_racine/worktrees/<id> : $_gd" ;;
  "$_cd_racine"/worktrees/?*) : ;;
  *) refus "git-dir de la cible hors de $_cd_racine/worktrees/<id> : $_gd" ;;
esac

# Arbre .codex/ ENTIER egal au HEAD de la racine.
_head="$(git -C "$RACINE" rev-parse --verify -q 'HEAD^{commit}' 2>/dev/null)" || refus "HEAD de la racine illisible"
# skip-worktree (S) ou assume-unchanged (minuscule) masquent un ecart au diff : seul le marqueur H est admis.
_marques="$(git -C "$CIBLE" ls-files -v -- .codex 2>/dev/null)" || refus "relevé des marqueurs de .codex/ illisible"
while IFS= read -r _l; do
  [ -n "$_l" ] || continue
  case "$_l" in
    "H "*) : ;;
    *) refus ".codex/ de la cible porte un fichier marque skip-worktree ou assume-unchanged : $_l" ;;
  esac
done <<< "$_marques"
git -C "$CIBLE" diff --quiet --no-ext-diff --no-textconv "$_head" -- .codex >/dev/null 2>&1
_rc=$?
[ "$_rc" -eq 0 ] || refus ".codex/ de la cible differe du HEAD de la racine (rc $_rc) — remede : rebaser la branche du worktree sur ce HEAD"
_hors="$(git -C "$CIBLE" ls-files -o -- .codex 2>/dev/null)" || refus "relevé des non-suivis de .codex/ illisible"
if [ -n "$_hors" ]; then
  IFS= read -r _premier <<< "$_hors"
  refus ".codex/ de la cible porte des fichiers non suivis (ignores compris), dont $_premier — remede : commiter le travail, git worktree remove, worktree neuf ; jamais d'exclusion de __pycache__"
fi

# Mandat : fichier regulier existant, non lie.
[ ! -L "$MANDAT" ] || refus "le mandat est un lien : $MANDAT"
[ -e "$MANDAT" ] || refus "mandat absent : $MANDAT"
[ -f "$MANDAT" ] || refus "le mandat n'est pas un fichier regulier : $MANDAT"
[ -r "$MANDAT" ] || refus "mandat illisible : $MANDAT"
# Chemin reel (repertoire resolu sans lien) sous une zone admise : <racine>/docs/tasks/, /tmp/, /private/tmp/, $TMPDIR.
_mdir="$(reel "$(dirname -- "$MANDAT")")"
[ -n "$_mdir" ] || refus "repertoire du mandat illisible : $MANDAT"
MANDAT_REEL="$_mdir/${MANDAT##*/}"
_admis=0
case "$MANDAT_REEL" in
  "$RACINE"/docs/tasks/*) _admis=1 ;;
  /tmp/*) _admis=1 ;;
  /private/tmp/*) _admis=1 ;;
esac
if [ "$_admis" -eq 0 ] && [ -n "${TMPDIR:-}" ]; then
  _tmpd="$(reel "$TMPDIR")"
  if [ -n "$_tmpd" ] && [ "$_tmpd" != "/" ]; then
    case "$MANDAT_REEL" in
      "$_tmpd"/*) _admis=1 ;;
    esac
  fi
fi
[ "$_admis" -eq 1 ] || refus "mandat hors des zones admises (<racine>/docs/tasks/, /tmp/, /private/tmp/, \$TMPDIR) : $MANDAT_REEL"

ARGV=(codex exec -C "$CIBLE" -s workspace-write
  -c sandbox_workspace_write.network_access=false
  -c 'sandbox_workspace_write.writable_roots=[]'
  -m "$MODEL")
if [ -n "$EFFORT" ]; then
  ARGV+=(-c "model_reasoning_effort=\"$EFFORT\"")
fi
ARGV+=(-)

if [ "$DRY" -eq 1 ]; then
  printf '%q ' "${ARGV[@]}"
  printf '< %q\n' "$MANDAT_REEL"
  exit 0
fi
exec "${ARGV[@]}" < "$MANDAT_REEL"
