#!/usr/bin/env bash
# core-scripts/build-submodule-corpus.sh — T-00000295
#
# Builds an OUT-OF-REPO git superproject carrying an INITIALIZED submodule
# (itself carrying a NESTED submodule) so the three kit security scanners can be
# MEASURED against real git-submodule states instead of DEDUCED. Persisted on
# purpose: T-00000293's plan declares it will reuse this constructor, so it must
# survive the mktemp -d that holds the corpus.
#
# TOPOLOGY, and it is load-bearing. The kit's `.agents/security/` and
# `.gitleaks.toml` are VENDORED (copied) to the corpus ROOT, and it is those
# COPIES the scanners run against (cwd = corpus). That is EXACTLY an adopter's
# topology — `.agents/security/` at the root — and NOT the kit's own repo. Every
# verdict measured here is anchored to that topology; any other montage is
# declared NON MESURÉ in the issue document.
#
# CLASS-0 DECOY. The AWS-style access-key literal is a FIXED token assembled at
# runtime from two halves (`akia` + `body`) — SPLIT so no `AKIA`+16 literal lives
# in any tracked file, this script included, and it is NEVER echoed to
# stdout/stderr. It is byte-for-byte the verified-detectable token of the
# deterministic suite (`.agents/security/gitleaks-scan.test.sh`), and an
# OPPORTUNISTIC detectability assertion re-checks at each build that gitleaks
# still trips on it (three-armed on the return channel — gitleaks absent OR
# erroring ⇒ « corpus non défendu », never fail-open). The code sink is
# `os.system(...)`, verified-red by semgrep.yml's
# python-command-injection-shell-true rule (ERROR). The word EXAMPLE never
# appears in any generated content.
#
# FILES ARE WRITTEN WITH printf, NEVER A HEREDOC (L-00000197).
#
# Usage:  build-submodule-corpus.sh [CASE]
#   CASE in C0 C1 C2 C3 C4 C5 C6 C7  (default C1 = the clean initialized rest state)
#     C0  secret + injection decoys UNTRACKED at the superproject root, tree
#         otherwise clean — the CONTROL (must go red, else nothing is attributable)
#     C1  submodule initialized, everything committed, tree clean
#     C2  committed file MODIFIED inside the submodule, gitlink unchanged
#     C3  gitlink UPDATED (commit advanced inside the submodule, not committed up)
#     C4  UNTRACKED file inside the submodule
#     C5  submodule NOT initialized (deinit — a fresh CI clone)
#     C6  gitlink REMOVED (git rm, staged deletion)
#     C7  same populated corpus as C1; measured for the NESTED submodule
#
# Prints, as its LAST stdout line:  CORPUS=<absolute path to the superproject>
# All progress goes to stderr, so a caller captures the path cleanly.
#
# NE PEUT PLUS ANNONCER UN SUCCÈS QU'IL N'A PAS EU. Toute commande dont l'échec
# fausserait le corpus porte `|| die "<étape>"` (le script tourne sous
# `set -uo pipefail` SANS `-e`, choisi pour nommer l'étape fautive et préserver
# le repli voulu de KIT_ROOT) : les commandes structurantes git ET chaque écriture
# de contenu. Le secret n'est plus tiré ni assuré en forme — c'est un jeton fixe
# SCINDÉ, vérifié-détectable HORS de ce script (cf. CLASS-0 DECOY ci-dessus).
# CORPUS= ne s'imprime qu'APRÈS le contrôle de complétude `verify_corpus_baseline`,
# qui vérifie la STRUCTURE git de la ligne de base (deux sous-modules initialisés,
# arbre propre), PAS le contenu des fichiers — le contenu est garanti par le
# `|| die` de chaque écriture, rien d'autre. Un `|| die` oublié sur une écriture
# de contenu n'est rattrapé par aucun contrôle structurel : c'est la limite, elle
# est dite. Et l'assertion de détectabilité est OPPORTUNISTE : elle refuse
# d'imprimer CORPUS= si gitleaks tourne et ne voit RIEN (rc=0), mais ne garantit
# rien quand gitleaks est absent ou en erreur — elle le DIT (« corpus non défendu »),
# elle ne le tait pas.
set -uo pipefail

say() { printf '%s\n' "$*" >&2; }
die() { printf 'build-submodule-corpus: %s\n' "$*" >&2; exit 1; }

# verify_corpus_baseline — contrôle de complétude STRUCTUREL de la ligne de base
# (== C1), appelé APRÈS le commit "add submodule sub (with nested)" et AVANT toute
# dérivation (qui salit l'arbre exprès). LECTURE SEULE : ne crée aucun fichier
# (sinon il polluerait le périmètre ls-files --others que C0 mesure). Les relevés
# git sont CAPTURÉS en variable et comparés en bash — jamais relayés sur stdout,
# où seul CORPUS= a le droit d'écrire. Tout échec sort par die (pas de CORPUS=).
# Il vérifie la STRUCTURE git, PAS le contenu des fichiers : le contenu est garanti
# par le || die de chaque écriture, rien d'autre.
verify_corpus_baseline() {
  local status_out porcelain_out paths
  status_out="$($GIT -C "$SUPER" submodule status --recursive)" \
    || die "contrôle de complétude : 'submodule status --recursive' a échoué"
  # (a) exactement deux sous-modules, {sub, sub/nested}, TOUS DEUX initialisés.
  #     Le préfixe d'état ('-' non initialisé, '+' désynchronisé, 'U' conflit)
  #     est collé au SHA (champ 1) ; le chemin reste le champ 2 dans tous les cas.
  if printf '%s\n' "$status_out" | grep -qE '^[-+U]'; then
    die "contrôle de complétude : sous-module non initialisé/désynchronisé — $status_out"
  fi
  paths="$(printf '%s\n' "$status_out" | awk 'NF{print $2}' | sort | tr '\n' ',')"
  [ "$paths" = "sub,sub/nested," ] \
    || die "contrôle de complétude : sous-modules attendus {sub, sub/nested}, obtenus {$paths}"
  # (b) arbre propre.
  porcelain_out="$($GIT -C "$SUPER" status --porcelain)" \
    || die "contrôle de complétude : 'git status --porcelain' a échoué"
  [ -z "$porcelain_out" ] \
    || die "contrôle de complétude : arbre non propre après la baseline — $porcelain_out"
  say "baseline C1 vérifiée : 2 sous-modules initialisés (sub, sub/nested), arbre propre"
}

CASE="${1:-C1}"
case "$CASE" in
  C0|C1|C2|C3|C4|C5|C6|C7) : ;; *) die "unknown CASE '$CASE'";;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KIT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"
[ -n "$KIT_ROOT" ] || KIT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KIT_ROOT="$(cd "$KIT_ROOT" && pwd)"
[ -d "$KIT_ROOT/.agents/security" ] || die "cannot find .agents/security under $KIT_ROOT"
[ -f "$KIT_ROOT/.gitleaks.toml" ]   || die "cannot find .gitleaks.toml under $KIT_ROOT"

# CLASS-0 DECOY — jeton fixe SCINDÉ, assemblé à l'exécution. Octet-pour-octet
# celui de la suite déterministe .agents/security/gitleaks-scan.test.sh:29 :
# charset base32 [A-Z2-7], VÉRIFIÉ-détectable par gitleaks 8.30.1, hors allowlist
# `.+EXAMPLE$` de la règle aws-access-token. La forme SCINDÉE garantit que le
# littéral AKIA+16 n'apparaît dans AUCUN fichier suivi (ce script compris). Le
# tirage aléatoire d'antan passait sous le plancher d'entropie de la règle
# (~3 détectables sur 12, doc de mesure) : ce jeton fixe le remplace, et
# l'assertion de détectabilité opportuniste ci-dessous re-vérifie à chaque build.
akia="AKIA"; body="ZX4QY7GJTMPKQR5T"; SECRET="${akia}${body}"

# file protocol is required for local-path submodules since git 2.38; fixed
# identity so commits succeed without touching global git config.
GIT="git -c protocol.file.allow=always -c user.name=corpus -c user.email=corpus@invalid.test -c commit.gpgsign=false -c advice.detachedHead=false"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/submodule-corpus.XXXXXX")" || die "mktemp failed"
NESTED_SRC="$WORK/nested_src"
SUB_SRC="$WORK/sub_src"
SUPER="$WORK/super"
say "corpus work dir: $WORK   (case $CASE)"

# ---- ASSERTION DE DÉTECTABILITÉ (opportuniste, jamais fail-open) -------------
# Un jeton fixe COMMITÉ recrée les préconditions d'une pourriture d'allowlist
# amont (T-00000067) : on RE-VÉRIFIE donc, à chaque construction et SI gitleaks
# est présent, que le jeton trip encore la règle aws-access-token. La sortie
# gitleaks est JETÉE (un finding échoerait le secret) et les messages sont
# STATIQUES — $SECRET n'est JAMAIS interpolé (le rc l'est, le secret non).
# TROIS bras sur le CANAL DE RETOUR, jamais le défaut exit 1 que gitleaks 8.x
# confond avec une erreur fatale (L-00000136 — d'où --exit-code 99) :
#   rc=99      ⇒ jeton détecté, corpus défendu, poursuite ;
#   rc=0       ⇒ die (gitleaks a tourné et n'a rien vu — le corpus ne vaut rien
#                pour l'arme gitleaks : on refuse d'imprimer CORPUS=) ;
#   tout autre ⇒ say « corpus non défendu » + poursuite — même posture que
#                gitleaks ABSENT : un environnement en panne ne certifie NI ne
#                bloque, jamais fail-open.
if command -v gitleaks >/dev/null 2>&1; then
  ASSERT_DIR="$WORK/detectability_probe"
  mkdir -p "$ASSERT_DIR" || die "assertion détectabilité : mkdir probe"
  printf '[default]\naws_access_key_id = %s\n' "$SECRET" > "$ASSERT_DIR/probe.txt" \
    || die "assertion détectabilité : écriture probe"
  # --source "." depuis un cd : AUCUN chemin absolu passé au binaire gitleaks
  # natif, donc rien à (dé)traduire côté MSYS ; seul --config reste absolu et sa
  # traduction MSYS automatique est PRÉSERVÉE (jamais neutralisée par un opt-out).
  ( cd "$ASSERT_DIR" && gitleaks detect --no-git --source "." --exit-code 99 \
      --config "$KIT_ROOT/.gitleaks.toml" ) >/dev/null 2>&1
  rc=$?
  if [ "$rc" -eq 99 ]; then
    say "assertion détectabilité : jeton vu par gitleaks — corpus défendu"
  elif [ "$rc" -eq 0 ]; then
    die "assertion détectabilité : jeton non détecté par gitleaks"
  else
    say "assertion détectabilité : gitleaks en erreur (rc=$rc) — corpus non défendu"
  fi
  rm -rf "$ASSERT_DIR" 2>/dev/null || :
else
  say "assertion détectabilité : gitleaks absent — corpus non défendu"
fi

# ---- nested submodule source repo -------------------------------------------
mkdir -p "$NESTED_SRC" || die "mkdir nested_src"
$GIT init -q "$NESTED_SRC" || die "git init nested_src"
printf '{\n  "name": "nested-sub",\n  "version": "1.0.0",\n  "dependencies": {}\n}\n' > "$NESTED_SRC/package.json" || die "écriture nested package.json"
printf 'import os\n\n\ndef nested_run(x):\n    os.system("echo " + x)\n' > "$NESTED_SRC/nested_vuln.py" || die "écriture nested_vuln.py"
$GIT -C "$NESTED_SRC" add -A || die "git add nested_src"
$GIT -C "$NESTED_SRC" commit -qm "nested baseline" || die "git commit nested baseline"

# ---- submodule source repo (secret + injection + manifest + nested) ---------
mkdir -p "$SUB_SRC/config" || die "mkdir sub_src/config"
printf '[default]\naws_access_key_id = %s\n' "$SECRET" > "$SUB_SRC/config/credentials.txt" || die "écriture sub credentials.txt (secret)"
printf 'import os\n\n\ndef run(cmd):\n    os.system("echo " + cmd)\n' > "$SUB_SRC/vuln.py" || die "écriture sub vuln.py"
printf '{\n  "name": "sub",\n  "version": "1.0.0",\n  "dependencies": {}\n}\n' > "$SUB_SRC/package.json" || die "écriture sub package.json"
$GIT init -q "$SUB_SRC" || die "git init sub_src"
$GIT -C "$SUB_SRC" submodule add -q "$NESTED_SRC" nested || die "submodule add nested"
$GIT -C "$SUB_SRC" add -A || die "git add sub_src"
$GIT -C "$SUB_SRC" commit -qm "sub baseline (secret + os.system + nested)" || die "git commit sub baseline"

# ---- superproject: vendor the kit scanners, THEN add the submodule ----------
mkdir -p "$SUPER/.agents" || die "mkdir super/.agents"
cp -r "$KIT_ROOT/.agents/security" "$SUPER/.agents/security" || die "cp .agents/security"
cp "$KIT_ROOT/.gitleaks.toml" "$SUPER/.gitleaks.toml" || die "cp .gitleaks.toml"
printf 'corpus superproject — vendored kit security tooling at the root (adopter topology)\n' > "$SUPER/README.md" || die "écriture super README.md"
$GIT init -q "$SUPER" || die "git init super"
# THE VENDORISATION IS COMMITTED INTO THE BASELINE BEFORE ANY DERIVATION, so the
# vendored *.test.sh fixtures never enter ls-files --others and never pollute a
# measured perimeter (C0 included).
$GIT -C "$SUPER" add -A || die "git add super (vendorisation)"
$GIT -C "$SUPER" commit -qm "vendored kit security tooling (baseline)" || die "git commit vendorisation"
$GIT -C "$SUPER" submodule add -q "$SUB_SRC" sub || die "submodule add sub"
$GIT -C "$SUPER" submodule update -q --init --recursive || die "submodule update --init --recursive"
$GIT -C "$SUPER" add -A || die "git add super (submodule sub)"
$GIT -C "$SUPER" commit -qm "add submodule sub (with nested)" || die "git commit add submodule sub"

# baseline now == C1 (initialized, everything committed, tree clean).
# Contrôle de complétude AVANT toute dérivation : la structure git est vérifiée
# ici, jamais le contenu des fichiers (garanti, lui, par le || die de chaque
# écriture ci-dessus — rien d'autre). Toute anomalie sort par die, qui n'imprime
# jamais CORPUS=.
verify_corpus_baseline

# ---- derive the requested case ----------------------------------------------
case "$CASE" in
  C0)
    # decoys UNTRACKED at the superproject root, ALONE above a clean tree.
    printf '[default]\naws_access_key_id = %s\n' "$SECRET" > "$SUPER/leaked_credentials.txt" || die "C0: écriture leaked_credentials.txt"
    printf 'import os\n\n\ndef danger(p):\n    os.system("rm -rf " + p)\n' > "$SUPER/decoy_vuln.py" || die "C0: écriture decoy_vuln.py"
    ;;
  C1) : ;;
  C2)
    # committed file modified INSIDE the submodule; gitlink unchanged, not committed.
    printf '\n# working-tree modification, not committed\n' >> "$SUPER/sub/vuln.py" || die "C2: écriture sub/vuln.py"
    ;;
  C3)
    # advance the submodule HEAD (commit inside sub), NOT committed at the superproject.
    printf '\n# committed line inside the submodule\n' >> "$SUPER/sub/vuln.py" || die "C3: écriture sub/vuln.py"
    $GIT -C "$SUPER/sub" add -A || die "C3: git add sub"
    $GIT -C "$SUPER/sub" commit -qm "advance submodule HEAD" || die "C3: git commit advance submodule HEAD"
    ;;
  C4)
    # untracked file INSIDE the submodule (carries a fresh secret too).
    printf '[default]\naws_access_key_id = %s\n' "$SECRET" > "$SUPER/sub/untracked_leak.txt" || die "C4: écriture sub/untracked_leak.txt"
    ;;
  C5)
    # deinitialize the submodule -> empty dir (a fresh clone without --recurse-submodules).
    # stderr n'est plus jeté : seul stdout est mis au silence (die a besoin de la cause).
    $GIT -C "$SUPER" submodule deinit -f sub >/dev/null || die "C5: submodule deinit -f sub"
    # TÉMOIN C5 : la ligne 'sub' du status doit désormais porter le préfixe '-'
    # (non initialisé). Relevé capturé en variable, jamais relayé sur stdout.
    c5_status="$($GIT -C "$SUPER" submodule status)" || die "C5: submodule status"
    printf '%s\n' "$c5_status" | grep -qE '^-.*[[:space:]]sub([[:space:]]|$)' \
      || die "C5: témoin manquant — 'sub' n'est pas marqué non initialisé (-)"
    ;;
  C6)
    # remove the gitlink (git rm -> staged deletion, working tree dir gone).
    $GIT -C "$SUPER" rm -q sub || die "C6: git rm sub"
    # TÉMOIN C6 : 'sub' ABSENT du submodule status ET suppression stagée visible
    # au porcelain. Relevés capturés en variable, jamais relayés sur stdout.
    c6_status="$($GIT -C "$SUPER" submodule status)" || die "C6: submodule status"
    if printf '%s\n' "$c6_status" | awk 'NF{print $2}' | grep -qx 'sub'; then
      die "C6: témoin manquant — 'sub' encore présent dans submodule status"
    fi
    c6_porcelain="$($GIT -C "$SUPER" status --porcelain)" || die "C6: git status --porcelain"
    printf '%s\n' "$c6_porcelain" | grep -qE '^D[[:space:]]+sub$' \
      || die "C6: témoin manquant — suppression stagée de 'sub' absente du porcelain"
    ;;
  C7) : ;;  # populated corpus (== C1); the NESTED submodule is what gets measured.
esac

printf 'CORPUS=%s\n' "$SUPER"
