#!/usr/bin/env bash
# Tests for gitleaks-scan.sh — second half (the gate reads what git commits:
# the index, unreadable perimeters), split out of gitleaks-scan.test.sh
# (T-01M55Z3W38NDBXMTZBP81GKA8R) so the two halves run in parallel. Run: bash
# .agents/security/gitleaks-scan-index.test.sh — also auto-discovered by
# core-scripts/run-bash-tests.sh. The preamble below is RECOPIÉ ON PURPOSE (no
# shared helper) from gitleaks-scan.test.sh; change one, change both.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/gitleaks-scan.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: gitleaks-scan.sh not found"; exit 1; }

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

HAVE_GITLEAKS=0; command -v gitleaks >/dev/null 2>&1 && HAVE_GITLEAKS=1

# NOGL_PATH: PATH with every gitleaks-bearing dir removed, computed ONCE and
# reused by every fallback arm below (the debt-free way to simulate absence on a
# box that HAS gitleaks; on the gitleaks-less CI runner it is just PATH, so the
# plain run already IS the fallback). All other tools stay real.
NOGL_PATH=""
IFS=':' read -r -a _path_dirs <<< "$PATH"
for d in "${_path_dirs[@]}"; do
  [ -n "$d" ] || continue
  if [ -x "$d/gitleaks" ] || [ -x "$d/gitleaks.exe" ]; then continue; fi
  NOGL_PATH="${NOGL_PATH:+$NOGL_PATH:}$d"
done
# T-01M4JC50S6CTJ5HJ697929E6NA : « all other tools stay real » — on a Homebrew box gitleaks and
# timeout(1) (coreutils) share /opt/homebrew/bin, so stripping that dir also
# strips timeout and the script DEGRADES on every arm that expects none (t844j).
# Keep timeout real through a tool dir of symlinks, created only when needed.
_nogl_timeout="$(command -v timeout 2>/dev/null || true)"
if [ -n "$_nogl_timeout" ] && ! PATH="$NOGL_PATH" command -v timeout >/dev/null 2>&1; then
  _nogl_tmpbase="${TMPDIR-}"
  [ -n "$_nogl_tmpbase" ] || _nogl_tmpbase=/tmp
  _nogl_tools="$(mktemp -d "$_nogl_tmpbase/nogl-tools.XXXXXX")" || { echo "FAIL: mktemp for the timeout tool dir"; exit 1; }
  ln -s "$_nogl_timeout" "$_nogl_tools/timeout"
  NOGL_PATH="$_nogl_tools:$NOGL_PATH"
fi

# A syntactically valid AWS Access Key ID, ASSEMBLED AT RUNTIME from split
# literals: the contiguous 20-char token never appears in this file, so the
# repo-diff Stop-hook scan stays clean (no self-inflicted hook loop) while the
# runtime --content payload still trips gitleaks' AWS rule.
#
# The body MUST NOT end in "EXAMPLE": gitleaks' default config allowlists
# `.+EXAMPLE$` on the aws-access-token rule (verified against 8.30.1 and the
# upstream config/gitleaks.toml), so AWS's documented example key
# (…IOSFODNN7EXAMPLE) is silently ignored — that dead fixture is exactly what
# made this suite's case (a) rot (T-00000067). Charset is base32 [A-Z2-7],
# per the rule's regex; this exact token is verified to trip 8.30.1.
akia="AKIA"; body="ZX4QY7GJTMPKQR5T"
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
assert_tmpdir() {  # $1 = candidate throwaway dir
  local tmp="${TMPDIR:-/tmp}"; tmp="${tmp%/}"   # macOS sets TMPDIR WITH a trailing slash; `mktemp -d` output has none, so an unstripped "$TMPDIR"/* glob becomes T//* and matches nothing (Linux/MSYS leave TMPDIR unset => /tmp, no slash, always matched — this is why CI stayed green)
  [ -n "$1" ]              || fail "throwaway dir is EMPTY — refusing (git -C '' would hit the live repo)"
  [ "$1" != "$PWD" ]       || fail "throwaway dir == PWD ($1) — refusing"
  [ "$1" != "$REAL_ROOT" ] || fail "throwaway dir == repo root ($1) — refusing"
  case "$1" in
    /tmp/*|"$tmp"/*) : ;;
    *) fail "throwaway dir outside temp ($1) — refusing" ;;
  esac
}
GIT_ISO="git -c protocol.file.allow=always -c user.name=t -c user.email=t@t.t -c commit.gpgsign=false -c advice.detachedHead=false"
T1PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { T1PY="$c"; break; }; done
t844_json_ok() {  # $1 = stdout capturé  $2 = fragment attendu ; rc 0 si conforme
  if [ -n "$T1PY" ]; then
    printf '%s' "$1" | "$T1PY" -c 'import json, sys
frag = sys.argv[1]
d = json.loads(sys.stdin.read())
assert isinstance(d, dict) and list(d) == ["systemMessage"], d
m = d["systemMessage"]
assert m.startswith("COVERAGE DEGRADED"), m
assert frag in m, m' "$2" >/dev/null 2>&1
    return $?
  fi
  [ "$(printf '%s\n' "$1" | wc -l | tr -d ' ')" = "1" ] || return 1
  case "$1" in
    '{"systemMessage": "COVERAGE DEGRADED'*'"}') ;;
    *) return 1 ;;
  esac
  case "$1" in
    *"$2"*) return 0 ;;
  esac
  return 1
}
# Le bras de bash sous lequel on joue : bash du PATH, puis /bin/bash s'il est
# un 3.2 (le /bin/bash de macOS) — la forme `${CFG[@]+…}` y est vitale.
T844_SHELLS="bash"
if [ -x /bin/bash ] && /bin/bash -c '[ "${BASH_VERSINFO[0]}" -lt 4 ]'; then
  T844_SHELLS="bash /bin/bash"
fi
LC_PY=""
for lc_c in python3 python; do
  "$lc_c" -c 'import sys; sys.exit(sys.version_info[0] != 3)' >/dev/null 2>&1 && { LC_PY="$lc_c"; break; }
done
[ -n "$LC_PY" ] || fail "(vi) python 3 introuvable pour fabriquer le mutant"
# ==== T-01M4X7Q1RR7WPF1GWYFEFHDDM9 + T-01M4X9Y079FMHBQHHQRXV4GK1V : LA PORTE LIT
# CE QUE GIT VA COMMITER, ET NE DIT JAMAIS « clean » D'UN PÉRIMÈTRE NON LU ====
# Avant : un fichier du diff illisible (chmod 000) rendait « clean. » ou « nothing
# to scan », rc 0, et le marqueur de libération du repli ; une clé `git add`ée
# puis réécrite bénigne (ou rendue illisible) passait, et le commit la portait ;
# un sous-module initialisé mais illisible se lisait « not initialized ».
# Après : l'INDEX est un second périmètre, lu BRUT (cat-file : aucun filtre),
# étiqueté `index:` ; ce qui ne peut pas être lu est COMPTÉ et DÉGRADE — rc 0,
# décision pilote S-01M4XWS5NDR78YXVG5E42ZQCM2 — jamais « clean ». Fixtures sous
# UN mktemp -d hors dépôt, droits remis avant rm. Chaque mutant est fabriqué
# hors dépôt en remplaçant une ancre présente EXACTEMENT une fois (forme (a4)) :
# un mutant qui ne mute rien est un témoin muet, et le bras le refuse.
TRR_SKIP=""
if [ "$(id -u 2>/dev/null)" = 0 ]; then
  TRR_SKIP="uid 0 : chmod 000 n'interdit pas la lecture"
else
  _trr_p="$(mktemp)"
  printf 'x\n' > "$_trr_p"; chmod 000 "$_trr_p"
  if cat "$_trr_p" >/dev/null 2>&1; then
    TRR_SKIP="chmod 000 laisse lire ici (ACL ou système de fichiers)"
  fi
  chmod 600 "$_trr_p"; rm -f "$_trr_p"
fi
[ -n "$LC_PY" ] || fail "(trr) python 3 introuvable pour fabriquer les mutants"
TRR_W="$(mktemp -d)"; assert_tmpdir "$TRR_W"
TRR_K="aws_access_key_id = ${akia}${body}"
TRSTUB="$TRR_W/stub"; mkdir "$TRSTUB"
{
  printf '#!/usr/bin/env bash\n'
  printf 'rp=""; prev=""\n'
  printf 'for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n'
  printf '[ -n "$rp" ] && printf "[]" > "$rp"\n'
  printf 'exit 0\n'
} > "$TRSTUB/gitleaks"
chmod +x "$TRSTUB/gitleaks"
TRNOPY="$TRR_W/nopy"; mkdir "$TRNOPY"
for p in python3 python; do
  { printf '#!/bin/sh\n'; printf 'exit 127\n'; } > "$TRNOPY/$p"; chmod +x "$TRNOPY/$p"
done
TRR_MUT="$TRR_W/mut"; mkdir "$TRR_MUT"
TRR_TMP=""   # TMPDIR dédié du script, posé par (trr9) seulement
trr_repo() {  # dépôt jetable sous TRR_W, un commit ; .agents/ exclu : le journal d'audit de la porte n'entre pas au recensement
  local R; R="$(mktemp -d "$TRR_W/r.XXXXXX")"; assert_tmpdir "$R"
  $GIT_ISO init -q "$R"
  printf '.agents/\n' >> "$R/.git/info/exclude"
  printf 'seed\n' > "$R/seed.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1
  $GIT_ISO -C "$R" commit -qm seed >/dev/null 2>&1
  printf '%s' "$R"
}
trr_super() {  # $1 = absorbed|inplace ; super-projet portant vendor/sub, clé COMMITÉE dans vendor/sub/creds.txt
  local S R
  S="$(mktemp -d "$TRR_W/src.XXXXXX")"; assert_tmpdir "$S"
  $GIT_ISO init -q "$S"
  printf '%s\n' "$TRR_K" > "$S/creds.txt"
  $GIT_ISO -C "$S" add -A >/dev/null 2>&1
  $GIT_ISO -C "$S" commit -qm s >/dev/null 2>&1
  R="$(trr_repo)"
  if [ "$1" = inplace ]; then
    $GIT_ISO clone -q "$S" "$R/vendor/sub" >/dev/null 2>&1
  fi
  $GIT_ISO -C "$R" submodule add -q "$S" vendor/sub >/dev/null 2>&1
  $GIT_ISO -C "$R" commit -qm sub >/dev/null 2>&1
  printf '%s' "$R"
}
trr_run() {  # $1 script  $2 dépôt  $3 fb|stub|gl|nopy  [$4 shell] -> TRR_OUT (2>&1) TRR_RC TRR_AUDIT
  local sh="${4:-bash}" p="$PATH" t="${TMPDIR:-/tmp}"
  case "$3" in
    fb)
      p="$NOGL_PATH" ;;
    stub)
      p="$TRSTUB:$NOGL_PATH" ;;
    nopy)
      p="$TRNOPY:$NOGL_PATH" ;;
  esac
  [ -n "$TRR_TMP" ] && t="$TRR_TMP"
  TRR_OUT="$( cd "$2" && TMPDIR="$t" PATH="$p" "$sh" "$1" 2>&1 )"; TRR_RC=$?
  TRR_AUDIT="$(tail -1 "$2/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null)"
}
trr_rc() {  # $1 étiquette  $2 rc attendu
  [ "$TRR_RC" -eq "$2" ] || fail "$1 : rc $TRR_RC, attendu $2 — sortie : $TRR_OUT"
}
trr_dit() {  # $1 étiquette  $2 fragment attendu
  case "$TRR_OUT" in
    *"$2"*)
      return 0 ;;
  esac
  fail "$1 : « $2 » absent — sortie : $TRR_OUT"
}
trr_tait() {  # $1 étiquette  $2 fragment interdit
  case "$TRR_OUT" in
    *"$2"*)
      fail "$1 : « $2 » présent — sortie : $TRR_OUT" ;;
  esac
  return 0
}
trr_loc() {  # $1 étiquette  $2 emplacement attendu dans la ligne d'audit
  case "$TRR_AUDIT" in
    *"\"$2\""*)
      return 0 ;;
  esac
  fail "$1 : emplacement \"$2\" absent de l'audit : $TRR_AUDIT"
}
trr_verdict() {  # $1 étiquette  $2 verdict d'audit attendu
  case "$TRR_AUDIT" in
    *"\"verdict\":\"$2\""*)
      return 0 ;;
  esac
  fail "$1 : verdict d'audit $2 attendu : $TRR_AUDIT"
}
# trr_mutant <nom> : écrit $TRR_MUT/<nom>.sh ; rc 3 si une ancre n'apparaît pas
# EXACTEMENT une fois. Les apostrophes des ancres passent par chr(39).
trr_mutant() {
  "$LC_PY" -c '
import sys
src, dst, nom = sys.argv[1], sys.argv[2], sys.argv[3]
Q = chr(39)
M = {
    "M1": [("if ! cp \"$ROOT/$f\" \"$STAGE/$f\" 2>/dev/null; then",
            "if ! cp \"$ROOT/$f\" \"$STAGE/$f\" 2>/dev/null; then continue; fi; if false; then")],
    "M2": [("injoignable \"$ROOT\" \"$f\"", "false")],
    "M3": [("2>\"$CEN_ERR\"", "2>/dev/null")],
    "M5": [("  index_candidats C \"$ROOT\" \"\"\n", "  :\n")],
    "M6": [("injoignable \"$ROOT\" \"$sub_rel/.git\"", "false")],
    "M6b": [(" --work-tree=\"$IDX\")", ")")],
    "M7": [("os.O_EXCL | getattr(os, \"O_NOFOLLOW\", 0)", "os.O_TRUNC"),
           ("\"$LIRE_INDEX_PY\" \"$_rest\" \"$IDX\"", "\"$LIRE_INDEX_PY\" \"$_rest\" \"$STAGE\"")],
    "M8": [("[ -L \"$ROOT/$f\" ] && continue", ":")],
    "M89": [("[ -L \"$ROOT/$f\" ] && continue", ":"),
            ("rm -rf \"$STAGE\" 2>/dev/null; STAGE=\"$STAGE2\"", "rm -rf \"$STAGE2\" 2>/dev/null")],
    "M11": [("printf " + Q + "%s\\0" + Q + " \"${rec#??}\"", ":")],
    "M12": [("! gitdir_sur \"$name\" \"$rgd\" \"$rcm\"", "false")],
    "M13": [("100644|100755|120000)\n          printf", "100644|100755)\n          printf")],
    "M14": [("seen = written.get(rel) == sha", "seen = True")],
    "M15": [("seen = written.get(rel) == sha", "seen = False")],
    "M14n": [("[ \"$_vu\" = 1 ] && _d=$((_d + 1))", "_d=$((_d + 1))")],
    "M15n": [("[ \"$_vu\" = 1 ] && _d=$((_d + 1))", ":")],
    "M16": [("\"$3\"/modules/?*)", "*)")],
    "M17": [("        parents(comps)\n", "        os.makedirs(os.path.dirname(full), exist_ok=True)\n"),
            ("    if not os.path.isdir(dest):\n", "    if False:\n"),
            ("[ -n \"${_LECTEUR:-}\" ] && { kill \"$_LECTEUR\" 2>/dev/null; wait \"$_LECTEUR\" 2>/dev/null; }", ":")],
    # T-01M4Y09EY4M664896DMGDTMDXF + T-01M4Y09FSEM2QQNA7Y9KRH5DJG (bras gq*, gf*, gs1, gh1, gp*)
    "MQ1": [("diff --name-only -z --no-renames", "diff --name-only --no-renames")],
    "MQ2": [("-C \"$ROOT\" ls-files --others --exclude-standard -z >>", "-C \"$ROOT\" ls-files --others --exclude-standard >>")],
    "MQ3": [("gitn -C \"$ROOT\" ls-files -v -z >", "gitn -C \"$ROOT\" ls-files -v >")],
    "MQ4": [("    while IFS= read -r -d " + Q + Q + " f; do\n      [ -n \"$f\" ] || continue",
             "    while IFS= read -r f; do\n      [ -n \"$f\" ] || continue")],
    "MQ5": [("LC_ALL=C sort -u -z", "sort -u -z")],
    "MF1": [("gitn -c diff.autoRefreshIndex=false", "git -c diff.autoRefreshIndex=false")],
    "MF2": [("\"--config-env=filter.$n.clean=GL_VIDE\" ", "")],
    "MF3": [("--ignore-submodules=dirty ", "")],
    "MF4": [("gitn -C \"$repo\" ls-files -z --stage", "git -C \"$repo\" ls-files -z --stage")],
    "MF5": [("gitn -C \"$ROOT/$sub_rel\" ls-files -z 2>/dev/null", "git -C \"$ROOT/$sub_rel\" ls-files -z 2>/dev/null"),
            ("gitn -C \"$ROOT/$sub_rel\" ls-files --others", "git -C \"$ROOT/$sub_rel\" ls-files --others")],
    "MF6": [(" \"--config-env=filter.$n.required=GL_FAUX\"", "")],
    "MF7": [("opts+=(\"--config-env=filter.$n.clean=GL_VIDE\" \"--config-env=filter.$n.process=GL_VIDE\" \"--config-env=filter.$n.required=GL_FAUX\")",
             "opts+=(-c \"filter.$n.clean=\" -c \"filter.$n.process=\" -c \"filter.$n.required=false\")")],
    "MF8": [("\"--config-env=filter.$n.process=GL_VIDE\" ", "")],
    "MF9": [("--ignore-submodules=dirty", "--ignore-submodules=all")],
    "MF10": [("gitn -C \"$1\" config -z --get-regexp", "gitn -C \"$1\" config --local -z --get-regexp")],
    "MF11": [("opts+=(\"--config-env=filter.$n.clean=GL_VIDE\" \"--config-env=filter.$n.process=GL_VIDE\" \"--config-env=filter.$n.required=GL_FAUX\")",
              "opts+=(-c \"filter.$n.clean=\" -c \"filter.$n.process=\" -c \"filter.$n.required=false\")"),
             ("if [ -n \"${vals[$j]}\" ]; then", "if false; then")],
    "MF12": [("    unset GIT_CONFIG\n", "    :\n")],
    "MH1": [("HEAD -- > \"$CEN_RAW\"", "HEAD > \"$CEN_RAW\"")],
    "MH2": [("diff-index --cached -z --no-renames HEAD --", "diff-index --cached -z --no-renames HEAD")],
    "MP1": [("-c diff.autoRefreshIndex=false ", "")],
    "MP2": [("-c diff.autoRefreshIndex=false ", ""), ("export GIT_NO_LAZY_FETCH=1", ":")],
    "MX": [("export GIT_NO_LAZY_FETCH=1", ":")],
    "MG": [("_ign_ill=$((_ign_ill + n)) ;;", "_ign_ill=$((_ign_ill + 0)) ;;")],
    "MG2": [("    ignores_illisibles \"$ROOT/$sub_rel\"\n", "    :\n")],
    "MG3": [("[ \"$_g\" = 1 ] && garde+=", "garde+=")],
    "MG4": [("printf " + Q + ":0:%s\\0" + Q + " ${garde[@]+\"${garde[@]}\"} | gitn -C \"$1\" cat-file --batch-check -Z > \"$lv\" 2>/dev/null || rc=$?",
             ": > \"$lv\"; for u in ${garde[@]+\"${garde[@]}\"}; do if gitn -C \"$1\" cat-file -e \":0:$u\" 2>/dev/null; then printf \"0 blob 1\\0\" >> \"$lv\"; else printf \"x missing\\0\" >> \"$lv\"; fi; done")],
    "MG5": [("perte_perimetre \"?\" \"skip-worktree .gitignore check failed (git rc $rc)\"", ":")],
    "MG6": [("-c advice.sparseIndexExpanded=false ", "")],
    "MG7": [("[0-9a-f]*\" blob \"[0-9]*)\n            : ;;", "[0-9a-f]*\" blob \"[0-9]*)\n            n=$((n + 1)) ;;")],
    # exec-critic GO_AVEC_RESERVES + revue de sécurité (second commit)
    "MG8": [("ls-files --others --ignored --exclude-standard --directory -z", "ls-files --others --directory -z")],
    "MGBX": [("| gitn -C \"$1\" cat-file --batch-check -Z > \"$lv\"", "| GIT_NO_LAZY_FETCH=0 gitn -C \"$1\" cat-file --batch-check -Z > \"$lv\"")],
    "MS3": [("perte_perimetre \"?\" \"tracked modified file(s) not enumerated (a filter driver could not be neutralized)\"", ":")],
    "MS3B": [("elif [ \"$_neutres_ok\" = 1 ]; then", "elif true; then")],
    "MS3R": [("if [ -n \"${vals[$j]}\" ]; then", "if false; then")],
    "MP3": [("if paresseux ${ga[@]+\"${ga[@]}\"}; then", "if false; then")],
    "MP4": [("if paresseux -C \"$ROOT\"; then", "if false; then")],
    "MP5": [("&& paresseux -C \"$1\"; then\n    rc=paresseux", "&& false; then\n    rc=paresseux")],
    "MCL": [("  [ -n \"${_TMP_FN:-}\" ] && rm -f \"$_TMP_FN\" 2>/dev/null\n", ""),
            ("  [ -n \"${_TMP_SW:-}\" ] && rm -f \"$_TMP_SW\" 2>/dev/null\n", ""),
            ("  [ -n \"${CEN_RAW:-}\" ] && rm -f \"$CEN_RAW\" 2>/dev/null\n", ""),
            ("  [ -n \"${CEN_SORTED:-}\" ] && rm -f \"$CEN_SORTED\" 2>/dev/null\n", "")],
    # revue de clôture (critic-opus) : export ôté du SEUL diff du recensement
    "MD": [("      gitn -c diff.autoRefreshIndex=false", "      GIT_NO_LAZY_FETCH=0 gitn -c diff.autoRefreshIndex=false")],
}
with open(src, encoding="utf-8") as f:
    t = f.read()
for ancre, mute in M[nom]:
    if t.count(ancre) != 1:
        sys.exit(3)
    t = t.replace(ancre, mute, 1)
with open(dst, "w", encoding="utf-8") as f:
    f.write(t)
' "$SCRIPT" "$TRR_MUT/$1.sh" "$1" || fail "(trr6) mutant $1 : une ancre n'apparaît pas EXACTEMENT une fois — un mutant qui ne mute rien est un témoin muet"
}

if [ -n "$TRR_SKIP" ]; then
  echo "  SKIP (trr1-trr5, trr7, trr7b, trr8, trr8b, trrK1, trr9-i, trr13-000 ; mutants M1 M2 M3 M6 M6b M8 M89 M12) : $TRR_SKIP"
else
  # --- (trr1) repli, sous chaque bash : un fichier du diff illisible est COMPTÉ
  for SH844 in $T844_SHELLS; do
    R="$(trr_repo)"; printf 'b\n' > "$R/b.txt"; printf '%s\n' "$TRR_K" > "$R/k.txt"; chmod 000 "$R/k.txt"
    trr_run "$SCRIPT" "$R" fb "$SH844"
    trr_rc "(trr1/$SH844)" 0
    trr_dit "(trr1/$SH844)" "1 of 2 enumerated file(s) unreadable in the working tree (0 index entr"
    trr_dit "(trr1/$SH844)" "fallback scan: DEGRADED ("
    trr_tait "(trr1/$SH844)" " file(s) scanned, "
    trr_verdict "(trr1/$SH844)" DEGRADED
    chmod 644 "$R/k.txt"
    trr_run "$SCRIPT" "$R" fb "$SH844"
    trr_rc "(trr1/$SH844) témoin 644" 2
    ok "(trr1/$SH844) repli : fichier du diff illisible => rc 0, « 1 of 2 … unreadable » dit, jamais le marqueur de libération, audit DEGRADED (témoin 644 : rc 2)"
  done
  R="$(trr_repo)"; printf 'b\n' > "$R/b.txt"; printf '%s\n' "$TRR_K" > "$R/k.txt"; chmod 000 "$R/k.txt"
  trr_mutant M1; trr_run "$TRR_MUT/M1.sh" "$R" fb
  case "$TRR_OUT" in
    *"fallback scan: 1 file(s) scanned, 0 finding(s)"*)
      : ;;
    *)
      fail "(trr6) M1 (échec de cp rendu à « || continue ») : le marqueur de libération était attendu — sans lui le bras (trr1) ne pourrait pas rougir ; sortie : $TRR_OUT" ;;
  esac
  ok "(trr6) M1 : l'échec de cp non compté libère (trr1) — le bras rougirait"

  # --- (trr2) bouchon `[]` et (trr2r) gitleaks réel : jamais « clean. », UN systemMessage JSON
  R="$(trr_repo)"; printf 'b\n' > "$R/b.txt"; printf '%s\n' "$TRR_K" > "$R/k.txt"; chmod 000 "$R/k.txt"
  OUT="$( cd "$R" && PATH="$TRSTUB:$NOGL_PATH" bash "$SCRIPT" 2>/dev/null )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(trr2) bouchon : rc $rc, attendu 0"
  case "$OUT" in
    *"clean."*)
      fail "(trr2) bouchon : « clean. » sur un périmètre non lu : [$OUT]" ;;
  esac
  t844_json_ok "$OUT" "unreadable in the working tree" || fail "(trr2) bouchon : stdout doit être UN systemMessage JSON valide nommant la perte : [$OUT]"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' || fail "(trr2) bouchon : audit DEGRADED attendu"
  chmod 644 "$R/k.txt"
  OUT="$( cd "$R" && PATH="$TRSTUB:$NOGL_PATH" bash "$SCRIPT" 2>/dev/null )"
  [ "$OUT" = "SECRETS GATE (class-0): clean." ] || fail "(trr2) témoin 644 : le bouchon (rapport vide) doit rendre « clean. », got: [$OUT]"
  ok "(trr2) bouchon : fichier illisible => pas de « clean. », UN systemMessage JSON valide, audit DEGRADED (témoin 644 : clean.)"
  if [ "$HAVE_GITLEAKS" -eq 1 ]; then
    R="$(trr_repo)"; printf 'b\n' > "$R/b.txt"; printf '%s\n' "$TRR_K" > "$R/k.txt"; chmod 000 "$R/k.txt"
    OUT="$( cd "$R" && bash "$SCRIPT" 2>/dev/null )"; rc=$?
    [ "$rc" -eq 0 ] || fail "(trr2r) gitleaks réel : rc $rc, attendu 0"
    t844_json_ok "$OUT" "unreadable in the working tree" || fail "(trr2r) gitleaks réel : UN systemMessage JSON valide attendu : [$OUT]"
    tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' || fail "(trr2r) audit DEGRADED attendu"
    chmod 644 "$R/k.txt"
    ( cd "$R" && bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
    [ "$rc" -eq 2 ] || fail "(trr2r) témoin 644 : gitleaks réel doit BLOQUER la clé (rc 2), got $rc"
    ok "(trr2r) gitleaks réel : fichier illisible => DEGRADED dit en JSON, jamais clean (témoin 644 : rc 2)"
  else
    echo "  SKIP (trr2r): gitleaks not installed"
  fi

  # --- (trr3) seul fichier du diff, illisible : « nothing could be read », jamais « nothing to scan »
  R="$(trr_repo)"; printf '%s\n' "$TRR_K" > "$R/k.txt"; chmod 000 "$R/k.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr3)" 0
  trr_dit "(trr3)" "nothing could be read"
  trr_tait "(trr3)" "nothing to scan"
  trr_tait "(trr3)" " file(s) scanned, "
  chmod 644 "$R/k.txt"
  ok "(trr3) repli : rien de lisible => « nothing could be read », jamais « nothing to scan »"

  # --- (trr4) supprimé ≠ injoignable ; avertissement de ls-files --others compté
  R="$(trr_repo)"; mkdir "$R/d"; printf 't\n' > "$R/d/t.txt"; printf 'g\n' > "$R/gone.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm d >/dev/null 2>&1
  printf '%s\n' "$TRR_K" > "$R/d/t.txt"; rm -f "$R/gone.txt"; chmod 000 "$R/d"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr4)" 0
  trr_dit "(trr4)" "1 listed path(s) unreachable in the working tree"
  trr_dit "(trr4)" "warning line(s) from git ls-files --others"
  trr_mutant M2; trr_run "$TRR_MUT/M2.sh" "$R" fb
  trr_tait "(trr6) M2 (injoignable => false) — le bras (trr4) doit perdre la cause, sinon il ne pourrait pas rougir" "unreachable in the working tree"
  chmod 755 "$R/d"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr4) témoin 755" 2
  trr_tait "(trr4) témoin : gone.txt vraiment supprimé" "unreachable"
  ok "(trr4) repli : chemin sous un dossier 000 => « unreachable » ET « warning line(s) » dits (témoins : 755 => rc 2 ; supprimé réel => aucun « unreachable »)"
  ok "(trr6) M2 : injoignable neutralisé => la cause disparaît — le bras (trr4) rougirait"

  # --- (trr5) non suivis cachés sous un dossier illisible : la ligne de ls-files est comptée
  R="$(trr_repo)"; mkdir "$R/vol"; printf '%s\n' "$TRR_K" > "$R/vol/u.txt"; chmod 000 "$R/vol"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr5)" 0
  trr_dit "(trr5)" "warning line(s) from git ls-files --others"
  trr_mutant M3; trr_run "$TRR_MUT/M3.sh" "$R" fb
  trr_tait "(trr6) M3 (stderr de ls-files jeté) — (trr5) doit devenir muet" "warning line(s)"
  printf 'vol/\n' > "$R/.gitignore"
  trr_run "$SCRIPT" "$R" fb
  trr_tait "(trr5) témoin : vol/ ignoré" "warning line(s)"
  chmod 755 "$R/vol"
  ok "(trr5) repli : dossier non suivi illisible => « warning line(s) » compté (témoin : .gitignore vol/ => muet)"
  ok "(trr6) M3 : stderr de ls-files --others jeté => (trr5) muet — le bras rougirait"

  # --- (trr7) clé INDEXÉE puis fichier rendu illisible : lue dans l'index, rc 2
  R="$(trr_repo)"; printf '%s\n' "$TRR_K" > "$R/k.txt"; $GIT_ISO -C "$R" add k.txt; chmod 000 "$R/k.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7)" 2; trr_loc "(trr7)" "index:k.txt:1"
  if [ "$HAVE_GITLEAKS" -eq 1 ]; then
    trr_run "$SCRIPT" "$R" gl
    trr_rc "(trr7/réel)" 2; trr_loc "(trr7/réel)" "index:k.txt:1"
  fi
  chmod 644 "$R/k.txt"
  R="$(trr_repo)"; printf 't\n' > "$R/t.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm t >/dev/null 2>&1
  printf '%s\n' "$TRR_K" > "$R/t.txt"; $GIT_ISO -C "$R" add t.txt; chmod 000 "$R/t.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7) suivi modifié + indexé" 2; trr_loc "(trr7) suivi modifié + indexé" "index:t.txt:1"
  chmod 644 "$R/t.txt"
  R="$(trr_repo)"; printf 'benign\n' > "$R/k.txt"; $GIT_ISO -C "$R" add k.txt; chmod 000 "$R/k.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7) témoin bénin indexé" 0; trr_dit "(trr7) témoin bénin indexé" "(1 index entr"; trr_verdict "(trr7) témoin bénin indexé" DEGRADED
  chmod 644 "$R/k.txt"
  R="$(trr_repo)"; printf 't\n' > "$R/t.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm t >/dev/null 2>&1
  printf '%s\n' "$TRR_K" > "$R/t.txt"; chmod 000 "$R/t.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7) témoin NON indexé" 0; trr_dit "(trr7) témoin NON indexé" "(0 index entr"
  chmod 644 "$R/t.txt"
  ok "(trr7) clé indexée puis 000 (nouveau, ou suivi modifié) => rc 2 à index:<chemin>:1 (témoins : bénin indexé => DEGRADED ; non indexé, non commitable => DEGRADED, 0 index)"

  # --- (trr7b) (i) clé indexée sous un dossier 000 ; (ii) fichier de sous-module illisible relu dans SON index
  R="$(trr_repo)"; mkdir "$R/d"; printf '%s\n' "$TRR_K" > "$R/d/k.txt"; $GIT_ISO -C "$R" add d/k.txt; chmod 000 "$R/d"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7b-i)" 2; trr_loc "(trr7b-i)" "index:d/k.txt:1"
  chmod 755 "$R/d"
  R="$(trr_super absorbed)"; chmod 000 "$R/vendor/sub/creds.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7b-ii)" 2; trr_loc "(trr7b-ii)" "index:vendor/sub/creds.txt:1"
  chmod 644 "$R/vendor/sub/creds.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr7b-ii) témoin 644" 2; trr_loc "(trr7b-ii) témoin 644" "vendor/sub/creds.txt:1"
  ok "(trr7b) clé indexée sous dossier 000 => index:d/k.txt:1 ; fichier de sous-module 000 => relu dans son index, index:vendor/sub/creds.txt:1 (témoin 644 : par l'arbre)"

  # --- (trr8) sous-module initialisé mais INJOIGNABLE : son index lu par son git dir
  R="$(trr_super absorbed)"; chmod 000 "$R/vendor/sub"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr8)" 2; trr_loc "(trr8)" "index:vendor/sub/creds.txt:1"
  trr_dit "(trr8)" "unreachable submodule(s): working tree not read (index read)"
  if [ "$HAVE_GITLEAKS" -eq 1 ]; then
    trr_run "$SCRIPT" "$R" gl
    trr_rc "(trr8/réel)" 2; trr_loc "(trr8/réel)" "index:vendor/sub/creds.txt:1"
  fi
  trr_mutant M6; trr_run "$TRR_MUT/M6.sh" "$R" fb
  [ "$TRR_RC" -eq 0 ] || fail "(trr6) M6 (injoignable de enumerate_submodules => false) : rc 0 attendu (clé jamais lue), got $TRR_RC — sans cela (trr8) ne pourrait pas rougir"
  trr_dit "(trr6) M6" "not initialized"
  trr_mutant M6b; trr_run "$TRR_MUT/M6b.sh" "$R" fb
  [ "$TRR_RC" -eq 0 ] || fail "(trr6) M6b (--work-tree retiré du mode git dir) : rc 0 attendu (chdir refusé), got $TRR_RC — sans cela (trr8) ne pourrait pas rougir"
  trr_dit "(trr6) M6b" "index entries not read"
  chmod 755 "$R/vendor/sub"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr8) témoin lisible" 2; trr_loc "(trr8) témoin lisible" "vendor/sub/creds.txt:1"
  R="$(trr_super absorbed)"; $GIT_ISO -C "$R" submodule deinit -q -f vendor/sub >/dev/null 2>&1
  trr_run "$SCRIPT" "$R" fb
  trr_dit "(trr8) témoin non initialisé" "submodule 'vendor/sub' not initialized"
  trr_tait "(trr8) témoin non initialisé" "unreachable submodule"
  ok "(trr8) sous-module 000 => son index lu par son git dir, rc 2 à index:vendor/sub/creds.txt:1, arbre non lu DIT (témoins : lisible => par l'arbre ; non initialisé => « not initialized »)"
  ok "(trr6) M6 : injoignable pris pour non initialisé => rc 0 ; M6b : sans --work-tree, chdir refusé => DEGRADED — (trr8) rougirait"

  # --- (trr8b) git dir illisible, ou absent (sous-module NON absorbé) : DEGRADED, « may already be committed »
  R="$(trr_super absorbed)"; chmod 000 "$R/vendor/sub"; chmod 000 "$R/.git/modules/vendor/sub"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr8b)" 0
  trr_dit "(trr8b)" "git dir is unreadable or absent — content may already be committed"
  trr_verdict "(trr8b)" DEGRADED
  trr_tait "(trr8b)" " file(s) scanned, "
  chmod 755 "$R/.git/modules/vendor/sub" "$R/vendor/sub"
  R="$(trr_super inplace)"
  [ -d "$R/vendor/sub/.git" ] || fail "(trr8b) fixture : le sous-module non absorbé doit porter un DOSSIER .git"
  chmod 000 "$R/vendor/sub"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr8b) non absorbé" 0
  trr_dit "(trr8b) non absorbé" "git dir is unreadable or absent — content may already be committed"
  trr_tait "(trr8b) non absorbé" " file(s) scanned, "
  chmod 755 "$R/vendor/sub"
  ok "(trr8b) git dir illisible, ou .git en dossier sous le sous-module 000 => rc 0, « content may already be committed », DEGRADED, aucun marqueur de libération"

  # --- (trrK1) nom .gitmodules hors de modules/ (K1) : jamais ouvert, DEGRADED
  R="$(trr_super absorbed)"
  git config -f "$R/.gitmodules" --rename-section "submodule.vendor/sub" "submodule.../x"
  cp -R "$R/.git/modules/vendor/sub" "$R/.git/x"
  chmod 000 "$R/vendor/sub"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trrK1)" 0
  trr_dit "(trrK1)" ".gitmodules name is unsafe"
  trr_tait "(trrK1)" "index:vendor/sub/creds.txt"
  trr_mutant M12; trr_run "$TRR_MUT/M12.sh" "$R" fb
  [ "$TRR_RC" -eq 2 ] || fail "(trr6) M12 (garde du nom retirée) : le git dir planté hors de modules/ doit être lu (rc 2), got $TRR_RC — sans cela (trrK1) ne pourrait pas rougir"
  chmod 755 "$R/vendor/sub"
  ok "(trrK1) nom « ../x » dans .gitmodules => git dir jamais ouvert, DEGRADED (M12 : sans la garde, le git dir planté est lu)"

  # --- (trr13-000) entrée assume-unchanged ILLISIBLE : perdue, comptée, jamais « nothing to scan »
  R="$(trr_repo)"; printf 'a\n' > "$R/au.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm au >/dev/null 2>&1
  git -C "$R" update-index --assume-unchanged au.txt
  printf '%s\n' "$TRR_K" > "$R/au.txt"; chmod 000 "$R/au.txt"
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr13-000)" 0
  trr_dit "(trr13-000)" "unreadable in the working tree"
  trr_tait "(trr13-000)" "nothing to scan"
  trr_verdict "(trr13-000)" DEGRADED
  chmod 644 "$R/au.txt"
  ok "(trr13-000) assume-unchanged illisible => compté, DEGRADED, jamais « nothing to scan »"
fi

# --- (trr9) liens : le stage n'est JAMAIS une porte de sortie (CWE-59), TMPDIR dédié
X9="$(mktemp -d "$TRR_W/x.XXXXXX")"; T9="$(mktemp -d "$TRR_W/t.XXXXXX")"
R9="$X9/repo"; mkdir "$R9"; $GIT_ISO init -q "$R9"; printf '.agents/\n' >> "$R9/.git/info/exclude"
printf 'seed\n' > "$R9/seed.txt"; $GIT_ISO -C "$R9" add -A >/dev/null 2>&1; $GIT_ISO -C "$R9" commit -qm seed >/dev/null 2>&1
printf '%s\n' "$TRR_K" > "$X9/escape-target"     # contenu « attaquant », à côté du dépôt
printf 'VICTIM\n' > "$T9/escape-target"          # victime, à côté du stage
printf 'VICTIM\n' > "$TRR_W/victim.ref"
ln -s ../escape-target "$R9/lnk" 2>/dev/null
if [ ! -L "$R9/lnk" ]; then
  echo "  SKIP (trr9): ln -s ne crée pas de lien ici (MSYS copie)"
else
  TRR_TMP="$T9"
  if [ -z "$TRR_SKIP" ]; then
    printf 'b\n' > "$R9/b.txt"; printf 'z\n' > "$R9/z.txt"; chmod 000 "$R9/z.txt"
    trr_run "$SCRIPT" "$R9" fb
    cmp -s "$T9/escape-target" "$TRR_W/victim.ref" || fail "(trr9-i) la victime HORS du stage a été réécrite (ESC, CWE-59)"
    trr_rc "(trr9-i)" 0
    case "$TRR_AUDIT" in
      *'"lnk:1"'*)
        fail "(trr9-i) le contenu d'un lien a été lu (parité avec tar rompue) : $TRR_AUDIT" ;;
    esac
    trr_mutant M8; trr_run "$TRR_MUT/M8.sh" "$R9" fb
    [ "$TRR_RC" -eq 2 ] || fail "(trr6) M8 (refus des liens retiré) : cp suit le lien et lit la clé hors dépôt (rc 2 attendu), got $TRR_RC — sans cela le refus ne pourrait pas rougir"
    trr_loc "(trr6) M8" "lnk:1"
    printf 'VICTIM\n' > "$T9/escape-target"
    trr_mutant M89; trr_run "$TRR_MUT/M89.sh" "$R9" fb
    if cmp -s "$T9/escape-target" "$TRR_W/victim.ref"; then
      fail "(trr6) M89 (refus des liens ET stage neuf retirés) : la victime devait être réécrite à travers le lien extrait (ESC) — sans cela (trr9-i) ne pourrait pas rougir"
    fi
    printf 'VICTIM\n' > "$T9/escape-target"
    chmod 644 "$R9/z.txt"
    ok "(trr9-i) lien relatif non suivi + voisin 000 : victime intacte octet pour octet, lien non lu"
    ok "(trr6) M8 : sans le refus des liens, la cible est lue (rc 2 à lnk:1) ; M89 : sans refus NI stage neuf, la victime est réécrite (ESC) — (trr9) rougirait"
  fi
  # (ii) SANS voisin illisible : le tar réussit et le lien extrait RESTE dans le stage
  R9b="$X9/repo2"; mkdir "$R9b"; $GIT_ISO init -q "$R9b"; printf '.agents/\n' >> "$R9b/.git/info/exclude"
  printf 'seed\n' > "$R9b/seed.txt"; $GIT_ISO -C "$R9b" add -A >/dev/null 2>&1; $GIT_ISO -C "$R9b" commit -qm seed >/dev/null 2>&1
  printf '%s\n' "$TRR_K" > "$R9b/lnk"; $GIT_ISO -C "$R9b" add lnk
  printf 'VICTIM2\n' > "$T9/victim2"; printf 'VICTIM2\n' > "$TRR_W/victim2.ref"
  rm -f "$R9b/lnk"; ln -s "$T9/victim2" "$R9b/lnk"
  trr_run "$SCRIPT" "$R9b" fb
  cmp -s "$T9/victim2" "$TRR_W/victim2.ref" || fail "(trr9-ii) la victime a été réécrite à travers le lien de l'arbre"
  trr_rc "(trr9-ii)" 2; trr_loc "(trr9-ii)" "index:lnk:1"
  trr_mutant M7; trr_run "$TRR_MUT/M7.sh" "$R9b" fb
  if cmp -s "$T9/victim2" "$TRR_W/victim2.ref"; then
    fail "(trr6) M7 (O_EXCL|O_NOFOLLOW retirés, destination \$STAGE) : la clé devait être écrite DANS la victime — sans cela (trr9-ii) ne pourrait pas rougir"
  fi
  printf 'VICTIM2\n' > "$T9/victim2"
  ok "(trr9-ii) blob indexé + lien ABSOLU dans l'arbre : rc 2 à index:lnk:1, victime intacte"
  ok "(trr6) M7 : sans O_EXCL|O_NOFOLLOW, écrite dans le stage, la clé traverse le lien extrait — (trr9-ii) rougirait"
  TRR_TMP=""
fi

# --- (trr10) T-01M4X9Y079 : `git add` de la clé, puis l'arbre réécrit BÉNIN => rc 2 à index:k.txt:1
R="$(trr_repo)"; printf '%s\n' "$TRR_K" > "$R/k.txt"; $GIT_ISO -C "$R" add k.txt; printf 'benign\n' > "$R/k.txt"
trr_run "$SCRIPT" "$R" fb
trr_rc "(trr10)" 2; trr_loc "(trr10)" "index:k.txt:1"
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  trr_run "$SCRIPT" "$R" gl
  trr_rc "(trr10/réel)" 2; trr_loc "(trr10/réel)" "index:k.txt:1"
fi
# (trr10n) sans python (bouchons 127) : la boucle `cat-file blob` lit le même blob
trr_run "$SCRIPT" "$R" nopy
trr_rc "(trr10n)" 2; trr_loc "(trr10n)" "index:k.txt:1"
ok "(trr10n) sans python : boucle cat-file blob, rc 2 à index:k.txt:1"
trr_mutant M5; trr_run "$TRR_MUT/M5.sh" "$R" stub
case "$TRR_OUT" in
  *"SECRETS GATE (class-0): clean."*)
    : ;;
  *)
    fail "(trr6) M5 (lecture de l'index racine retirée) : « clean. » attendu — sans cela (trr10) ne pourrait pas rougir ; sortie : $TRR_OUT" ;;
esac
$GIT_ISO -C "$R" add k.txt
trr_run "$SCRIPT" "$R" stub
trr_rc "(trr10) témoin bénin indexé" 0; trr_dit "(trr10) témoin bénin indexé" "SECRETS GATE (class-0): clean."
ok "(trr10) clé indexée, arbre réécrit bénin => rc 2 à index:k.txt:1, repli et réel (témoin : bénin indexé => clean.)"
ok "(trr6) M5 : sans la lecture de l'index racine, la clé indexée passe « clean. » — (trr10) rougirait"

# --- (trr11) SMUDGE/ATTR : aucun filtre lancé, d'où qu'il soit déclaré (lecture brute cat-file)
for v in attrs info cfg; do
  R="$(trr_repo)"; MK="$TRR_W/smudge.$v"
  git -C "$R" config filter.evil.smudge "touch $MK; cat"
  case "$v" in
    attrs)
      printf '* filter=evil\n' > "$R/.gitattributes" ;;
    info)
      printf '* filter=evil\n' > "$R/.git/info/attributes" ;;
    cfg)
      printf '* filter=evil\n' > "$TRR_W/attrs.$v"; git -C "$R" config core.attributesFile "$TRR_W/attrs.$v" ;;
  esac
  printf '%s\n' "$TRR_K" > "$R/k.txt"; $GIT_ISO -C "$R" add k.txt; rm -f "$MK"
  trr_run "$SCRIPT" "$R" fb
  [ ! -e "$MK" ] || fail "(trr11/$v) un filtre smudge a été LANCÉ par la porte"
  trr_rc "(trr11/$v)" 2; trr_loc "(trr11/$v)" "index:k.txt:1"
  trr_run "$SCRIPT" "$R" stub
  [ ! -e "$MK" ] || fail "(trr11/$v) bouchon : un filtre smudge a été LANCÉ par la porte"
  git -C "$R" checkout-index --prefix="$TRR_W/co.$v/" k.txt >/dev/null 2>&1
  [ -e "$MK" ] || fail "(trr11/$v) témoin : checkout-index lancé par le banc doit écrire le marqueur (filtre vivant)"
done
ok "(trr11) filtre smudge déclaré dans .gitattributes, info/attributes et core.attributesFile : jamais lancé, clé lue brute (rc 2) ; témoin checkout-index : le filtre est vivant"

# --- (trr12) clé indexée ET arbre identique : deux emplacements (doublon écrit)
R="$(trr_repo)"; printf '%s\n' "$TRR_K" > "$R/k.txt"; $GIT_ISO -C "$R" add k.txt
trr_run "$SCRIPT" "$R" fb
trr_rc "(trr12)" 2; trr_loc "(trr12)" "k.txt:1"; trr_loc "(trr12)" "index:k.txt:1"
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  trr_run "$SCRIPT" "$R" gl
  trr_rc "(trr12/réel)" 2; trr_loc "(trr12/réel)" "k.txt:1"; trr_loc "(trr12/réel)" "index:k.txt:1"
fi
ok "(trr12) clé indexée, arbre identique => rc 2, k.txt:1 ET index:k.txt:1 (doublon, prix écrit)"

# --- (trr13) K2 : entrée assume-unchanged LISIBLE copiée et scannée (git ne la compare jamais)
R="$(trr_repo)"; printf 'a\n' > "$R/au.txt"
$GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm au >/dev/null 2>&1
git -C "$R" update-index --assume-unchanged au.txt
printf '%s\n' "$TRR_K" > "$R/au.txt"
trr_run "$SCRIPT" "$R" fb
trr_rc "(trr13)" 2; trr_loc "(trr13)" "au.txt:1"
trr_mutant M11; trr_run "$TRR_MUT/M11.sh" "$R" fb
[ "$TRR_RC" -eq 0 ] || fail "(trr6) M11 (ajout assume-unchanged retiré) : rc 0 attendu, got $TRR_RC — sans cela (trr13) ne pourrait pas rougir"
trr_dit "(trr6) M11" "nothing to scan"
git -C "$R" update-index --no-assume-unchanged au.txt
trr_run "$SCRIPT" "$R" fb
trr_rc "(trr13) témoin --no-assume-unchanged" 2
ok "(trr13) assume-unchanged lisible => recensé, scanné, rc 2 à au.txt:1 (témoin --no-assume-unchanged : rc 2)"
ok "(trr6) M11 : sans l'ajout assume-unchanged, la clé passe « nothing to scan » — (trr13) rougirait"

# --- (trr14) K3 : un lien INDEXÉ (blob 120000) est lu comme le texte de sa cible
R="$(trr_repo)"; ln -s "$TRR_K" "$R/lnk3" 2>/dev/null
if [ -L "$R/lnk3" ]; then
  $GIT_ISO -C "$R" add lnk3
  trr_run "$SCRIPT" "$R" fb
  trr_rc "(trr14)" 2; trr_loc "(trr14)" "index:lnk3:1"
  trr_mutant M13; trr_run "$TRR_MUT/M13.sh" "$R" fb
  [ "$TRR_RC" -eq 0 ] || fail "(trr6) M13 (mode 120000 retiré du filtre) : rc 0 attendu, got $TRR_RC — sans cela (trr14) ne pourrait pas rougir"
  ok "(trr14) lien indexé dont la cible porte une clé => lu brut, rc 2 à index:lnk3:1 (M13 : sans 120000, rc 0)"
else
  echo "  SKIP (trr14): ln -s ne crée pas de lien ici (MSYS copie)"
fi

# --- (trr16) une destination qui EXISTE n'est lue que si le MÊME objet y a été écrit
# (exec-critic sur b362f13a, mesuré : sur APFS insensible à la casse, index
# `K.txt` bénin + `k.txt` porteur de la clé, arbre bénin => « clean. », rc 0, et
# le commit portait la clé). Les entrées sont posées par `update-index
# --cacheinfo` : aucun fichier de l'arbre ne les porte.
_trr_ci=0; : > "$TRR_W/cAsE.sonde"; [ -e "$TRR_W/CASE.SONDE" ] && _trr_ci=1
# (trr16a) collision de casse : DEGRADED, jamais clean — avec python, sans python, bouchon, réel
if [ "$_trr_ci" = 1 ]; then
  R="$(trr_repo)"
  _a="$(printf 'benign\n' | git -C "$R" hash-object -w --stdin)"
  _b="$(printf '%s\n' "$TRR_K" | git -C "$R" hash-object -w --stdin)"
  git -C "$R" update-index --add --cacheinfo "100644,$_a,K.txt"
  git -C "$R" update-index --add --cacheinfo "100644,$_b,k.txt"
  printf 'benign\n' > "$R/k.txt"
  for m in fb nopy stub gl; do
    [ "$m" = gl ] && [ "$HAVE_GITLEAKS" -ne 1 ] && continue
    trr_run "$SCRIPT" "$R" "$m"
    trr_rc "(trr16a/$m)" 0
    trr_dit "(trr16a/$m)" "index entries not read"
    trr_tait "(trr16a/$m)" "clean."
    trr_tait "(trr16a/$m)" " file(s) scanned, "
    trr_verdict "(trr16a/$m)" DEGRADED
  done
  trr_mutant M14; trr_run "$TRR_MUT/M14.sh" "$R" stub
  trr_dit "(trr6) M14 (existence lue comme lue, python) — (trr16a) doit passer « clean. », sinon il ne pourrait pas rougir" "SECRETS GATE (class-0): clean."
  trr_mutant M14n; trr_run "$TRR_MUT/M14n.sh" "$R" nopy
  trr_dit "(trr6) M14n (existence lue comme lue, sans python) — (trr16a) doit libérer, sinon il ne pourrait pas rougir" " file(s) scanned, 0 finding(s)"
  # (trr16d) collision à contenu IDENTIQUE : même règle pour les deux lecteurs
  # (« même sha au même chemin ») — une perte comptée, sens prudent.
  R="$(trr_repo)"
  _a="$(printf 'benign\n' | git -C "$R" hash-object -w --stdin)"
  git -C "$R" update-index --add --cacheinfo "100644,$_a,K.txt"
  git -C "$R" update-index --add --cacheinfo "100644,$_a,k.txt"
  git -C "$R" cat-file -e "$_a" || fail "(trr16d) fixture : le blob doit être dans CE dépôt (sinon la perte serait un cat-file manquant)"
  for m in fb nopy; do
    trr_run "$SCRIPT" "$R" "$m"
    trr_rc "(trr16d/$m)" 0
    trr_dit "(trr16d/$m)" "index entries not read"
    trr_verdict "(trr16d/$m)" DEGRADED
  done
  ok "(trr16d) collision de casse à contenu identique : perte comptée, DEGRADED, avec et sans python (règle alignée)"
  ok "(trr16a) index K.txt bénin + k.txt clé sur FS insensible à la casse => DEGRADED « index entries not read », jamais clean (repli, sans python, bouchon, réel)"
  ok "(trr6) M14/M14n : une destination existante lue comme lue => « clean. » / libération — (trr16a) rougirait"
else
  echo "  SKIP (trr16a, M14, M14n): système de fichiers sensible à la casse — la collision n'existe pas ici"
fi
# (trr16c) deux chemins qui ne diffèrent que par la normalisation Unicode (NFD bénin
# + NFC clé). `-c core.precomposeunicode=false` : sous macOS git replie sinon NFD
# sur NFC dès update-index (mesuré : une seule entrée). Insensible à la
# normalisation (APFS) => collision, DEGRADED ; sensible => les deux lues, rc 2.
R="$(trr_repo)"
_nfc="$(printf '\303\251').txt"; _nfd="$(printf 'e\314\201').txt"
_a="$(printf 'benign\n' | git -C "$R" hash-object -w --stdin)"
_b="$(printf '%s\n' "$TRR_K" | git -C "$R" hash-object -w --stdin)"
git -C "$R" -c core.precomposeunicode=false update-index --add --cacheinfo "100644,$_a,$_nfd"
git -C "$R" -c core.precomposeunicode=false update-index --add --cacheinfo "100644,$_b,$_nfc"
for m in fb nopy; do
  trr_run "$SCRIPT" "$R" "$m"
  trr_tait "(trr16c/$m)" "clean."
  trr_tait "(trr16c/$m)" " file(s) scanned, 0 finding(s)"
  if [ "$TRR_RC" -eq 2 ]; then
    _trr_nf="les deux lues (rc 2)"
  else
    trr_rc "(trr16c/$m)" 0; trr_dit "(trr16c/$m)" "index entries not read"; _trr_nf="collision (DEGRADED)"
  fi
done
ok "(trr16c) NFD bénin + NFC clé dans l'index => $_trr_nf, jamais clean (dit selon le système de fichiers)"

# ==== T-01M4Y09EY4M664896DMGDTMDXF + T-01M4Y09FSEM2QQNA7Y9KRH5DJG : LE RECENSEMENT
# LIT EN NUL, TRIE EN OCTETS, NE LANCE AUCUN CODE DU DÉPÔT, ET DIT UNE NÉGATION
# PERDUE ====
# Avant : un chemin que git CITE (`"n\303\251.txt"`) ratait le test d'existence et
# tombait comme absent (clé dans `né.txt` : « nothing to scan », rc 0) ; le `diff`
# du recensement lançait fsmonitor, les filtres clean/process, le `git status`
# d'un sous-module sale et, dans un clone partiel, le `remote.origin.uploadpack`
# d'un rapatriement paresseux ; un `.gitignore` skip-worktree au blob absent
# perdait sa négation `!` en silence. Chaque bras a son TÉMOIN PAIRÉ (la commande
# git NUE fait naître le marqueur, sur une fixture NEUVE) et chaque mutant DOIT le
# rougir : gl_rougit rejoue le contrôle du bras dans un sous-shell et refuse qu'il
# passe. Une fixture neuve par exécution : un `git diff` nu réécrit l'index (une
# entrée racée y est lissée), un rapatriement remplit le clone. Témoins
# d'exécution : quatre scripts FIXES (aucune valeur interpolée) qui ne touchent
# que leur marqueur, à côté d'eux.
unset GIT_NO_LAZY_FETCH   # les témoins NUS doivent pouvoir rapatrier ; la porte pose son propre export
GL_W="$TRR_W/gl"; mkdir "$GL_W"
GL_T="$GL_W/temoins"; mkdir "$GL_T"
for _k in clean fsmonitor process lazy; do
  printf '%s\n' '#!/bin/sh' 'd=$(dirname "$0")' 'k=$(basename "$0")' ': > "$d/$k.mark"' \
    'case "$k" in' '  clean)' '    exec cat ;;' '  lazy)' '    exec git-upload-pack "$@" ;;' 'esac' 'exit 1' > "$GL_T/$_k"
  chmod +x "$GL_T/$_k"
done
GL_G="$GIT_ISO -c init.defaultBranch=master -c advice.addEmbeddedRepo=false"
# La ligne FIXE par laquelle un faux git lit le chemin du vrai : une donnée posée
# dans le fichier `real` à côté de lui, jamais interpolée dans son source.
GL_REEL='real="$(cat "$(dirname "$0")/real")"'
GL_LOC=""   # emplacement attendu par le contrôle du bras courant
gl_rm() { rm -f "$GL_T"/*.mark; }
gl_marque() { [ -e "$GL_T/$1.mark" ]; }
gl_aucune() {  # $1 étiquette — aucun témoin d'exécution n'est né
  local m
  for m in clean fsmonitor process lazy; do
    gl_marque "$m" && fail "$1 : le témoin « $m » est né — un code du dépôt a été EXÉCUTÉ ; sortie : $TRR_OUT"
  done
  return 0
}
gl_rougit() {  # $1 étiquette  $2 contrôle du bras (fonction) — il DOIT échouer sur le mutant
  ( "$2" ) >/dev/null 2>&1 && fail "$1 : le mutant SURVIT — le bras ne pourrait pas rougir ; sortie : $TRR_OUT"
  return 0
}
gl_mut() {  # $1 mutant  $2 fabrique (imprime un dépôt NEUF)  $3 mode  $4 contrôle  [$5 shell]
  local R
  R="$("$2")"; gl_rm
  trr_mutant "$1"; trr_run "$TRR_MUT/$1.sh" "$R" "$3" "${5:-bash}"
  gl_rougit "(trr6) $1" "$4"
}
gl_nu() {  # $1 étiquette  $2 marqueur attendu — la commande git NUE qui suit DOIT le faire naître
  local e="$1" k="$2"
  shift 2
  gl_rm
  "$@" >/dev/null 2>&1
  gl_marque "$k" || fail "$e : témoin pairé MUET — la commande nue ne fait pas naître « $k », la fixture ne prouve rien"
  gl_rm
}
gl_runp() {  # $1 script  $2 dépôt  $3 PATH -> TRR_OUT TRR_RC TRR_AUDIT
  TRR_OUT="$( cd "$2" && PATH="$3" bash "$1" 2>&1 )"; TRR_RC=$?
  TRR_AUDIT="$(tail -1 "$2/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null)"
}
_gl_v="$(PATH="$NOGL_PATH" git version 2>/dev/null)"; _gl_v="${_gl_v#git version }"
_gl_maj="${_gl_v%%.*}"; _gl_min="${_gl_v#*.}"; _gl_min="${_gl_min%%.*}"
case "$_gl_maj.$_gl_min" in
  *[!0-9.]*|.*|*.)
    fail "(gp) version de git illisible : « $_gl_v »" ;;
esac
gl_au_moins() {  # $1 majeur  $2 mineur — rc 0 si le git du banc est >= $1.$2
  [ "$_gl_maj" -gt "$1" ] && return 0
  [ "$_gl_maj" -eq "$1" ] && [ "$_gl_min" -ge "$2" ]
}
_gl_msys=0
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    _gl_msys=1 ;;
esac

# --- (gq1)-(gq5) chemins que git CITE : non suivi, modifié, assume-unchanged, guillemet, saut de ligne
_gl_ne="$(printf 'n\303\251').txt"; _gl_nl="$(printf 'nl\nx').txt"
gl_gq() {  # $1 = nonsuivi|modifie|assume|guillemet|saut — la clé posée selon $1 ; imprime le dépôt
  local R; R="$(trr_repo)"
  case "$1" in
    nonsuivi)
      printf '%s\n' "$TRR_K" > "$R/$_gl_ne" ;;
    modifie|assume)
      printf 'benign\n' > "$R/$_gl_ne"
      $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm ne >/dev/null 2>&1
      [ "$1" = assume ] && git -C "$R" update-index --assume-unchanged "$_gl_ne"
      printf '%s\n' "$TRR_K" > "$R/$_gl_ne" ;;
    guillemet)
      printf '%s\n' "$TRR_K" > "$R/q\"uote.txt" ;;
    saut)
      printf '%s\n' "$TRR_K" > "$R/$_gl_nl" ;;
  esac
  printf '%s' "$R"
}
gl_gq_nonsuivi() { gl_gq nonsuivi; }
gl_gq_modifie() { gl_gq modifie; }
gl_gq_assume() { gl_gq assume; }
gl_gq_saut() { gl_gq saut; }
gl_ok_rc2() { trr_rc "(gq)" 2; }
for _gq in nonsuivi modifie assume guillemet saut; do
  if [ "$_gq" = saut ] && [ "$_gl_msys" = 1 ]; then
    echo "  SKIP (gq5) : MSYS ne crée pas de nom de fichier à saut de ligne"
    continue
  fi
  for m in fb nopy; do
    R="$(gl_gq "$_gq")"; trr_run "$SCRIPT" "$R" "$m"
    trr_rc "(gq/$_gq/$m)" 2
  done
done
for SH844 in $T844_SHELLS; do
  R="$(gl_gq nonsuivi)"; trr_run "$SCRIPT" "$R" fb "$SH844"
  trr_rc "(gq1/$SH844)" 2
done
R="$(trr_repo)"; printf 'benign\n' > "$R/$_gl_ne"; trr_run "$SCRIPT" "$R" stub
trr_dit "(gq1) témoin bénin né.txt" "SECRETS GATE (class-0): clean."
trr_tait "(gq1) témoin bénin né.txt" "nothing to scan"
gl_mut MQ1 gl_gq_modifie fb gl_ok_rc2
gl_mut MQ2 gl_gq_nonsuivi fb gl_ok_rc2
gl_mut MQ3 gl_gq_assume fb gl_ok_rc2
if [ "$_gl_msys" = 1 ]; then
  gl_mut MQ4 gl_gq_nonsuivi fb gl_ok_rc2
else
  gl_mut MQ4 gl_gq_saut fb gl_ok_rc2
fi
ok "(gq1-gq5) clé dans un chemin que git CITE (né.txt non suivi / modifié / assume-unchanged, q\"uote.txt, saut de ligne) => rc 2, repli et sans python ; témoin bénin né.txt => « clean. », jamais « nothing to scan »"
ok "(trr6) MQ1-MQ4 : -z ôté du diff / de --others / de -v, lecture sans -d '' => la clé passe — (gq) rougirait"

# --- (gq6) jumeaux qu'une collation UTF-8 confond : a.txt et a<U+200B>.txt, tri en OCTETS
_gl_zw="a$(printf '\342\200\213').txt"; _gl_loc=""; _gl_surv=""
for _l in fr_FR.UTF-8 en_US.UTF-8 fr_FR.utf8 en_US.utf8; do
  _gl_n="$(printf 'a.txt\0%s\0' "$_gl_zw" | LC_ALL="$_l" PATH="$NOGL_PATH" sort -u -z 2>/dev/null | tr -cd '\000' | wc -c | tr -d ' ')"
  if [ "$_gl_n" = 1 ]; then
    _gl_loc="$_l"
    _gl_surv="$(printf 'a.txt\0%s\0' "$_gl_zw" | LC_ALL="$_l" PATH="$NOGL_PATH" sort -u -z 2>/dev/null | tr -d '\000')"
    break
  fi
done
if [ -z "$_gl_loc" ]; then
  echo "  SKIP (gq6, MQ5) : aucune locale UTF-8 présente dont le tri nu confonde les jumeaux (témoin pairé muet)"
else
  gl_gq6() {  # la clé dans le jumeau que le tri NU écarte (témoin pairé : $_gl_surv survit seul)
    local R; R="$(trr_repo)"
    printf 'benign\n' > "$R/$_gl_surv"
    if [ "$_gl_surv" = a.txt ]; then
      printf '%s\n' "$TRR_K" > "$R/$_gl_zw"
    else
      printf '%s\n' "$TRR_K" > "$R/a.txt"
    fi
    printf '%s' "$R"
  }
  R="$(gl_gq6)"; LC_ALL="$_gl_loc" trr_run "$SCRIPT" "$R" fb
  trr_rc "(gq6/$_gl_loc)" 2
  LC_ALL="$_gl_loc" gl_mut MQ5 gl_gq6 fb gl_ok_rc2
  ok "(gq6) jumeaux a.txt / a<U+200B>.txt sous $_gl_loc (le tri nu les confond, témoin pairé) => tri en octets, rc 2"
  ok "(trr6) MQ5 : LC_ALL=C ôté du tri => un jumeau tombe, la clé passe — (gq6) rougirait"
fi

# --- (gf1)-(gf9) aucun code du dépôt : fsmonitor, filtres clean/process, git status de sous-module
# Une entrée RACÉE (mtime futur dans l'index ET l'arbre, ctime ignoré) force git
# à relire le contenu MÊME sous diff.autoRefreshIndex=false (mesuré : un fichier
# seulement stat-sale ne lance plus le filtre, la neutralisation n'y serait pas
# prouvée) ; réécrite à la clé, même taille.
gl_racee() {  # $1 dépôt — k.txt suivi, racé, porteur de la clé
  printf 'aws_access_key_id = BBBBBBBBBBBBBBBBBBBB\n' > "$1/k.txt"; touch -t 203001010000 "$1/k.txt"
  $GIT_ISO -C "$1" add -A >/dev/null 2>&1; $GIT_ISO -C "$1" commit -qm racee >/dev/null 2>&1
  git -C "$1" config core.trustctime false
  printf '%s\n' "$TRR_K" > "$1/k.txt"; touch -t 203001010000 "$1/k.txt"
}
gl_filtre() {  # $1 nom du pilote  — dépôt racé dont *.txt passe par le pilote ; imprime le dépôt
  local R; R="$(trr_repo)"
  printf '*.txt filter=%s\n' "$1" > "$R/.gitattributes"
  gl_racee "$R"
  printf '%s' "$R"
}
gl_gf1() { local R; R="$(trr_repo)"; git -C "$R" config core.fsmonitor "$GL_T/fsmonitor"; printf '%s\n' "$TRR_K" > "$R/seed.txt"; printf '%s' "$R"; }
gl_gf2() { local R; R="$(gl_filtre x)"; git -C "$R" config filter.x.clean "$GL_T/clean"; printf '%s' "$R"; }
gl_gf3() { local R; R="$(gl_gf2)"; git -C "$R" config filter.x.required true; printf '%s' "$R"; }
gl_gf4() { local R; R="$(gl_filtre 'a=b')"; git -C "$R" config 'filter.a=b.clean' "$GL_T/clean"; git -C "$R" config 'filter.a=b.required' true; printf '%s' "$R"; }
gl_gf5() {  # sous-module SALE dont la config porte fsmonitor et un filtre clean ; fichier stat-sale même taille
  local S R
  S="$(mktemp -d "$TRR_W/src.XXXXXX")"; $GIT_ISO init -q "$S"
  printf '*.txt filter=y\n' > "$S/.gitattributes"; printf 'aws_access_key_id = BBBBBBBBBBBBBBBBBBBB\n' > "$S/m.txt"
  $GIT_ISO -C "$S" add -A >/dev/null 2>&1; $GIT_ISO -C "$S" commit -qm s >/dev/null 2>&1
  R="$(trr_repo)"; $GIT_ISO -C "$R" submodule add -q "$S" vendor/sub >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm sub >/dev/null 2>&1
  git -C "$R/vendor/sub" config core.fsmonitor "$GL_T/fsmonitor"
  git -C "$R/vendor/sub" config filter.y.clean "$GL_T/clean"
  printf '%s\n' "$TRR_K" > "$R/vendor/sub/m.txt"; touch -t 202001010000 "$R/vendor/sub/m.txt"
  printf '%s' "$R"
}
gl_gf6() {  # pilote déclaré dans un fichier INCLUS (include.path)
  local R; R="$(gl_filtre inc)"
  git config -f "$R/.git/inc.cfg" filter.inc.clean "$GL_T/clean"
  git -C "$R" config include.path "$R/.git/inc.cfg"
  printf '%s' "$R"
}
gl_gf7() { local R; R="$(gl_filtre p)"; git -C "$R" config filter.p.process "$GL_T/process"; printf '%s' "$R"; }
GL_GLOB="$GL_W/global.cfg"; git config -f "$GL_GLOB" filter.g.clean "$GL_T/clean"
# gf8/gf9 : la variable vaut pour le LANCEMENT seul — jamais pour la fabrique
# (un pilote global lancé par `git add`, une config locale écrite dans "").
gl_gf8() { ( unset GIT_CONFIG_GLOBAL; gl_filtre g ); }   # pilote dans la config GLOBALE
gl_gf9() { ( unset GIT_CONFIG; gl_gf2 ); }               # pilote local, GIT_CONFIG exporté vide au lancement
gl_ok_gf() { trr_rc "(gf)" 2; trr_loc "(gf)" "$GL_LOC"; gl_aucune "(gf)"; }
gl_gf_bras() {  # $1 étiquette  $2 fabrique  $3 marqueur du témoin nu
  local R
  R="$("$2")"; gl_rm; trr_run "$SCRIPT" "$R" fb
  trr_rc "$1" 2; trr_loc "$1" "$GL_LOC"; gl_aucune "$1"
  R="$("$2")"; gl_nu "$1" "$3" git -C "$R" diff --name-only HEAD --
}
GL_LOC="seed.txt:1"; gl_gf_bras "(gf1) fsmonitor racine" gl_gf1 fsmonitor
gl_mut MF1 gl_gf1 fb gl_ok_gf
gl_mut MF4 gl_gf1 fb gl_ok_gf
ok "(gf1) fsmonitor de la racine jamais lancé, rc 2 (témoin pairé : le diff nu le lance)"
ok "(trr6) MF1/MF4 : diff brut / ls-files --stage brut => fsmonitor lancé — (gf1) rougirait"
GL_LOC="vendor/sub/m.txt:1"; gl_gf_bras "(gf5) sous-module sale" gl_gf5 clean
gl_mut MF3 gl_gf5 fb gl_ok_gf
gl_mut MF5 gl_gf5 fb gl_ok_gf
ok "(gf5) sous-module sale : ni son git status, ni son filtre, ni son fsmonitor lancés, rc 2"
ok "(trr6) MF3/MF5 : --ignore-submodules=dirty ôté / ls-files du sous-module brut => son code lancé — (gf5) rougirait"
if ! gl_au_moins 2 31; then
  echo "  SKIP (gf2-gf4, gf6-gf9 ; mutants MF2 MF6-MF8 MF10-MF12) : git $_gl_v < 2.31 — pas de --config-env, la porte n'y lance pas le diff (DEGRADED dit)"
else
  GL_LOC="k.txt:1"; gl_gf_bras "(gf2) filtre clean racine" gl_gf2 clean
  gl_mut MF2 gl_gf2 fb gl_ok_gf
  gl_gf_bras "(gf3) filtre clean required=true" gl_gf3 clean
  gl_mut MF6 gl_gf3 fb gl_ok_gf
  gl_gf_bras "(gf4) pilote nommé a=b" gl_gf4 clean
  gl_mut MF7 gl_gf4 fb gl_ok_gf
  gl_mut MF11 gl_gf4 fb gl_ok_gf
  gl_gf_bras "(gf6) pilote déclaré par include.path" gl_gf6 clean
  gl_gf_bras "(gf7) filtre process seul" gl_gf7 process
  gl_mut MF8 gl_gf7 fb gl_ok_gf
  GIT_CONFIG_GLOBAL="$GL_GLOB" gl_gf_bras "(gf8) pilote de la config globale" gl_gf8 clean
  GIT_CONFIG_GLOBAL="$GL_GLOB" gl_mut MF10 gl_gf8 fb gl_ok_gf
  GIT_CONFIG="" gl_gf_bras "(gf9) GIT_CONFIG exporté vide" gl_gf9 clean
  GIT_CONFIG="" gl_mut MF12 gl_gf9 fb gl_ok_gf
  ok "(gf2-gf4, gf6-gf9) clean, required=true, pilote a=b, include.path, process seul, config globale, GIT_CONFIG vide => rc 2, aucun témoin né (témoins pairés : la commande nue les fait naître)"
  ok "(trr6) MF2, MF6-MF8, MF10-MF12 : clean/required/process ôtés, forme -c, relecture ôtée, lecture --local, unset ôté => chaque bras gf rougirait"

  # --- (gf10)/(gf11) étape 3, la branche FAIL-CLOSED (exec-critic, majeur 2 et BLIND SPOT) :
  # un pilote que la porte ne sait pas neutraliser => le diff n'est PAS lancé, la
  # perte est DITE, rc 0 (décision pilote S-01M4XWS5NDR78YXVG5E42ZQCM2). gf10 : un git
  # qui REFUSE --config-env (comme un git < 2.31) ; gf11 : un git qui l'IGNORE à la
  # relecture (le pilote y garde sa valeur). Faux git FIXES, seul le chemin du vrai
  # git est une DONNÉE, lue dans le fichier `real` posé à côté du faux git — jamais
  # écrite dans son source (AGENTS.md § Conventions : une valeur n'est jamais
  # re-parsée comme du shell ; revue de clôture C5).
  _gl_real="$(command -v git)"
  GL_FCE="$GL_W/faux-config-env"; GL_FRL="$GL_W/faux-relecture"; mkdir "$GL_FCE" "$GL_FRL"
  printf '%s' "$_gl_real" > "$GL_FCE/real"; printf '%s' "$_gl_real" > "$GL_FRL/real"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' "$GL_REEL"
    printf '%s\n' 'for a in "$@"; do' '  case "$a" in' '    --config-env=*)' \
      '      echo "unknown option: --config-env" >&2' '      exit 129 ;;' '  esac' 'done' 'exec "$real" "$@"'
  } > "$GL_FCE/git"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' "$GL_REEL"
    printf '%s\n' 'c=0; g=0' 'for a in "$@"; do' '  case "$a" in' '    config)' '      c=1 ;;' '    --get-regexp)' '      g=1 ;;' '  esac' 'done' \
      '[ "$c$g" = 11 ] || exec "$real" "$@"' 'args=()' 'for a in "$@"; do' '  case "$a" in' '    --config-env=*)' '      : ;;' \
      '    *)' '      args+=("$a") ;;' '  esac' 'done' 'exec "$real" "${args[@]}"'
  } > "$GL_FRL/git"
  chmod +x "$GL_FCE/git" "$GL_FRL/git"
  gl_ok_s3() {
    trr_rc "(gf10/gf11)" 0
    trr_dit "(gf10/gf11)" "tracked modified file(s) not enumerated (a filter driver could not be neutralized)"
    trr_tait "(gf10/gf11)" "clean."; trr_tait "(gf10/gf11)" "nothing to scan"; gl_aucune "(gf10/gf11)"
  }
  gl_s3() {  # $1 script  $2 faux git — sur une fixture gf2 NEUVE (pilote clean racé, clé dans k.txt suivi)
    local R; R="$(gl_gf2)"; gl_rm; gl_runp "$1" "$R" "$2:$NOGL_PATH"
  }
  gl_s3 "$SCRIPT" "$GL_FCE"; gl_ok_s3
  gl_s3 "$SCRIPT" "$GL_FRL"; gl_ok_s3
  trr_mutant MS3; gl_s3 "$TRR_MUT/MS3.sh" "$GL_FCE"; gl_rougit "(trr6) MS3/gf10" gl_ok_s3
  gl_s3 "$TRR_MUT/MS3.sh" "$GL_FRL"; gl_rougit "(trr6) MS3/gf11" gl_ok_s3
  trr_mutant MS3B; gl_s3 "$TRR_MUT/MS3B.sh" "$GL_FCE"; gl_rougit "(trr6) MS3B/gf10" gl_ok_s3
  trr_mutant MS3R; gl_s3 "$TRR_MUT/MS3R.sh" "$GL_FRL"; gl_rougit "(trr6) MS3R/gf11" gl_ok_s3
  ok "(gf10) git qui refuse --config-env => diff NON lancé, « … could not be neutralized » dit, rc 0, pilote jamais lancé"
  ok "(gf11) git qui ignore --config-env à la relecture => même perte dite, rc 0, pilote jamais lancé"
  ok "(trr6) MS3 (la ligne de perte ôtée) => « nothing to scan » — (gf10) et (gf11) rougiraient ; MS3B (diff lancé quand même) => pilote lancé — (gf10) ; MS3R (relecture ôtée) — (gf11)"
fi

# --- (gs1) un gitlink remplacé par un FICHIER porteur de la clé est listé
gl_gs1() {
  local S R
  S="$(mktemp -d "$TRR_W/src.XXXXXX")"; $GIT_ISO init -q "$S"; printf 'benign\n' > "$S/m.txt"
  $GIT_ISO -C "$S" add -A >/dev/null 2>&1; $GIT_ISO -C "$S" commit -qm s >/dev/null 2>&1
  R="$(trr_repo)"; $GIT_ISO -C "$R" submodule add -q "$S" sub >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm sub >/dev/null 2>&1
  rm -rf "$R/sub"; printf '%s\n' "$TRR_K" > "$R/sub"
  printf '%s' "$R"
}
gl_ok_gs1() { trr_rc "(gs1)" 2; trr_loc "(gs1)" "sub:1"; }
R="$(gl_gs1)"; trr_run "$SCRIPT" "$R" fb; gl_ok_gs1
gl_mut MF9 gl_gs1 fb gl_ok_gs1
ok "(gs1) gitlink devenu fichier à clé => listé, rc 2 à sub:1"
ok "(trr6) MF9 : --ignore-submodules=all => le fichier disparaît du diff — (gs1) rougirait"

# --- (gh1) un fichier nommé HEAD à la racine : la révision n'est jamais ambiguë (`--`)
gl_gh1() {  # clé dans un suivi modifié (arbre) ET dans un suivi indexé puis réécrit bénin (index seul)
  local R; R="$(trr_repo)"; printf 'k\n' > "$R/k.txt"; printf 's\n' > "$R/s.txt"
  $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm ks >/dev/null 2>&1
  printf '%s\n' "$TRR_K" > "$R/s.txt"; $GIT_ISO -C "$R" add s.txt; printf 's\n' > "$R/s.txt"
  printf '%s\n' "$TRR_K" > "$R/k.txt"; : > "$R/HEAD"
  printf '%s' "$R"
}
gl_ok_gh1() { trr_rc "(gh1)" 2; trr_loc "(gh1)" "k.txt:1"; trr_loc "(gh1)" "index:s.txt:1"; }
R="$(gl_gh1)"; trr_run "$SCRIPT" "$R" fb; gl_ok_gh1
R="$(gl_gh1)"; git -C "$R" diff --name-only -z HEAD >/dev/null 2>&1; _gl_rc=$?
[ "$_gl_rc" -ne 0 ] || fail "(gh1) témoin pairé : sans --, git diff HEAD devait échouer (révision ambiguë), rc $_gl_rc"
gl_mut MH1 gl_gh1 fb gl_ok_gh1
gl_mut MH2 gl_gh1 fb gl_ok_gh1
ok "(gh1) fichier HEAD à la racine => k.txt:1 ET index:s.txt:1, rc 2 (témoin pairé : sans --, rc $_gl_rc)"
ok "(trr6) MH1/MH2 : -- ôté du diff / du diff-index => une clé passe — (gh1) rougirait"

# --- (gp1)-(gp9) clone partiel : aucun rapatriement paresseux, et une négation perdue est DITE
if [ "$_gl_msys" = 1 ]; then
  echo "  SKIP (gp1-gp9 ; mutants MP1 MP2 MX MG MG2-MG7) : MSYS — clone partiel non mesuré sous Git for Windows"
else
  gl_absent() {  # $1 dépôt  $2 chemin de HEAD — rc 0 si son blob MANQUE (lu sans rapatrier, toute version)
    local s; s="$(git -C "$1" rev-parse "HEAD:$2" 2>/dev/null)" || return 1
    git -C "$1" rev-list --objects --missing=print HEAD 2>/dev/null | grep -qx "?$s"
  }
  gl_valide() {  # $1 étiquette  $2 dépôt  $3 chemin dont le blob DOIT manquer — fixture refusée ⇒ FAIL (C20)
    gl_absent "$2" "$3" || fail "$1 : fixture INVALIDE — le blob de $3 est présent (filtre de clone refusé ?), git $_gl_v"
    return 0
  }
  gl_origine() {  # $1 dossier  $2 contenu de d/.gitignore — racine *.log, d/keep.txt, e/f/.gitignore
    $GL_G init -q "$1"; git -C "$1" config uploadpack.allowFilter true
    mkdir -p "$1/d" "$1/e/f"; printf 'seed\n' > "$1/seed.txt"; printf '*.log\n' > "$1/.gitignore"
    printf 'keep\n' > "$1/d/keep.txt"; printf '%s\n' "$2" > "$1/d/.gitignore"
    printf 'g\n' > "$1/e/f/g.txt"; printf 'tmp/\n' > "$1/e/f/.gitignore"
    $GL_G -C "$1" add -A >/dev/null 2>&1; $GL_G -C "$1" commit -qm c0 >/dev/null 2>&1
  }
  gl_clone() {  # $1 origine  $2 destination  $3 partiel|complet  $4 cone|creux — témoin uploadpack armé APRÈS la mise en place
    if [ "$3" = partiel ]; then
      $GL_G clone -q --filter=blob:none --no-checkout "file://$1" "$2" >/dev/null 2>&1
    else
      $GL_G clone -q --no-checkout "file://$1" "$2" >/dev/null 2>&1
    fi
    git -C "$2" config protocol.file.allow always
    printf '.agents/\n' >> "$2/.git/info/exclude"
    if [ "$4" = cone ]; then
      $GL_G -C "$2" sparse-checkout set --cone >/dev/null 2>&1
    else
      $GL_G -C "$2" sparse-checkout set --no-cone '/seed.txt' '/.gitignore' '/d/keep.txt' >/dev/null 2>&1
    fi
    $GL_G -C "$2" checkout -q master >/dev/null 2>&1
    git -C "$2" config remote.origin.uploadpack "$GL_T/lazy"
  }
  gl_neuf() { mktemp -d "$GL_W/c.XXXXXX"; }
  GL_ONEG="$GL_W/oneg"; gl_origine "$GL_ONEG" '!keep.log'
  GL_OGI2="$GL_W/ogi2"; gl_origine "$GL_OGI2" '*.key'
  GL_OK2="$GL_W/ok2"; $GL_G init -q "$GL_OK2"; git -C "$GL_OK2" config uploadpack.allowFilter true
  printf 'seed\n' > "$GL_OK2/seed.txt"; printf 'aws_access_key_id = BBBBBBBBBBBBBBBBBBBB\n' > "$GL_OK2/k.txt"
  $GL_G -C "$GL_OK2" add -A >/dev/null 2>&1; $GL_G -C "$GL_OK2" commit -qm c0 >/dev/null 2>&1
  $GL_G -C "$GL_OK2" checkout -q -b next >/dev/null 2>&1; printf '%s\n' "$TRR_K" > "$GL_OK2/k.txt"
  $GL_G -C "$GL_OK2" commit -qam c1 >/dev/null 2>&1; $GL_G -C "$GL_OK2" checkout -q master >/dev/null 2>&1
  GL_SWL="skip-worktree .gitignore file(s) unreadable"

  # (gp1) HEAD déplacé sur next SANS checkout, k.txt stat-sale (même taille, mtime passé) porteur de la clé.
  # `reset --soft` puis `read-tree` : un `reset` mixte rafraîchit l'index et
  # RAPATRIE le blob de next (mesuré), la fixture n'y prouverait plus rien.
  gl_gp1() {
    local Q; Q="$(gl_neuf)"
    $GL_G clone -q --filter=blob:none "file://$GL_OK2" "$Q" >/dev/null 2>&1
    git -C "$Q" config protocol.file.allow always; printf '.agents/\n' >> "$Q/.git/info/exclude"
    $GL_G -C "$Q" reset -q --soft origin/next >/dev/null 2>&1
    $GL_G -C "$Q" read-tree origin/next >/dev/null 2>&1
    printf '%s\n' "$TRR_K" > "$Q/k.txt"; touch -t 202001010000 "$Q/k.txt"
    git -C "$Q" config remote.origin.uploadpack "$GL_T/lazy"
    printf '%s' "$Q"
  }
  gl_ok_gp1() { trr_rc "(gp1)" 2; trr_loc "(gp1)" "k.txt:1"; gl_aucune "(gp1)"; }
  GL_PCL="partial clone, git < 2.45: a missing blob would be fetched"
  R="$(gl_gp1)"; gl_valide "(gp1)" "$R" k.txt; gl_rm; trr_run "$SCRIPT" "$R" fb
  if gl_au_moins 2 45; then
    gl_ok_gp1
  else
    # git < 2.45 : la porte sait qu'elle ne peut pas refuser le rapatriement (pas de
    # --no-lazy-fetch) et ne lance PAS le diff — perte dite, jamais une exécution.
    trr_rc "(gp1/< 2.45)" 0; trr_dit "(gp1/< 2.45)" "tracked modified file(s) not enumerated ($GL_PCL"; gl_aucune "(gp1/< 2.45)"
  fi
  R="$(gl_gp1)"; gl_nu "(gp1)" lazy git -C "$R" diff --name-only HEAD --
  if gl_au_moins 2 45; then
    gl_mut MP1 gl_gp1 fb gl_ok_gp1
    gl_mut MP2 gl_gp1 fb gl_ok_gp1
  else
    echo "  SKIP (trr6 MP1, MP2) : git $_gl_v < 2.45 — le diff n'y est pas lancé (clone partiel), le bras (gp12) y tient lieu de preuve"
  fi
  ok "(gp1) clone partiel, fichier stat-sale porteur de la clé => rc 2, uploadpack JAMAIS exécuté (témoin pairé : le diff nu l'exécute)"
  ok "(trr6) MP1/MP2 : rafraîchissement stat rétabli (seul / sans l'export) => DEGRADED / uploadpack exécuté — (gp1) rougirait"

  if ! gl_au_moins 2 45; then
    echo "  SKIP (gp2-gp4s, gp10-gp12b ; mutants MX MG MG2 MG8 MGBX MP3-MP5) : git $_gl_v < 2.45 — GIT_NO_LAZY_FETCH y est SANS EFFET (résidu dit au README ; (gp1) y prouve le saut du diff)"
  else
    # (gp2) index = l'arbre de next par read-tree : le blob de la clé n'a jamais été rapatrié
    gl_gp2() {
      local Q; Q="$(gl_neuf)"
      $GL_G clone -q --filter=blob:none "file://$GL_OK2" "$Q" >/dev/null 2>&1
      git -C "$Q" config protocol.file.allow always; printf '.agents/\n' >> "$Q/.git/info/exclude"
      $GL_G -C "$Q" read-tree origin/next >/dev/null 2>&1
      git -C "$Q" config remote.origin.uploadpack "$GL_T/lazy"
      printf '%s' "$Q"
    }
    gl_ok_gp2() {
      trr_rc "(gp2)" 0; trr_dit "(gp2)" "index entries not read"
      trr_tait "(gp2)" "clean."; trr_tait "(gp2)" " file(s) scanned, 0 finding"; gl_aucune "(gp2)"
    }
    R="$(gl_gp2)"
    gl_absent "$R" k.txt && fail "(gp2) fixture : HEAD (master) doit porter un blob PRÉSENT"
    _gl_s="$(git -C "$R" rev-parse origin/next:k.txt)"
    git -C "$R" rev-list --objects --missing=print origin/next 2>/dev/null | grep -qx "?$_gl_s" \
      || fail "(gp2) fixture INVALIDE : le blob de la clé (next) est présent, git $_gl_v"
    for m in fb nopy; do
      R="$(gl_gp2)"; gl_rm; trr_run "$SCRIPT" "$R" "$m"; gl_ok_gp2
      gl_mut MX gl_gp2 "$m" gl_ok_gp2
    done
    R="$(gl_gp2)"; gl_nu "(gp2)" lazy git -C "$R" cat-file blob "$_gl_s"
    ok "(gp2) read-tree d'un blob filtré => « index entries not read », rc 0, uploadpack jamais exécuté (lecteur python ET shell ; témoin pairé : cat-file nu l'exécute)"
    ok "(trr6) MX sur (gp2) : l'export ôté => le lecteur d'index rapatrie, uploadpack exécuté — rougirait (fb et nopy)"

    # (gp1r) le canal RACÉ du diff (revue de clôture) : entrée racée, blob d'index ABSENT,
    # core.autocrlf=true — git lit le blob d'index (has_crlf_in_index) MÊME sans le
    # rafraîchissement stat. Seul l'export (ou, sous git < 2.45, le saut paresseux) le ferme.
    gl_gp1r() {
      local Q; Q="$(gl_neuf)"
      $GL_G clone -q --filter=blob:none "file://$GL_OK2" "$Q" >/dev/null 2>&1
      git -C "$Q" config protocol.file.allow always; git -C "$Q" config core.trustctime false
      printf '.agents/\n' >> "$Q/.git/info/exclude"
      $GL_G -C "$Q" reset -q --soft origin/next >/dev/null 2>&1; $GL_G -C "$Q" read-tree origin/next >/dev/null 2>&1
      printf '%s\n' "$TRR_K" > "$Q/k.txt"; touch -t 203001010000 "$Q/k.txt"
      GIT_NO_LAZY_FETCH=1 git -C "$Q" update-index -q --refresh
      printf '%s\n' "${TRR_K%?}U" > "$Q/k.txt"; touch -t 203001010000 "$Q/k.txt"   # clé VALIDE, même taille
      git -C "$Q" config core.autocrlf true
      git -C "$Q" config remote.origin.uploadpack "$GL_T/lazy"
      printf '%s' "$Q"
    }
    gl_ok_gp1r() { trr_rc "(gp1r)" 2; trr_loc "(gp1r)" "k.txt:1"; gl_aucune "(gp1r)"; }
    R="$(gl_gp1r)"; gl_valide "(gp1r)" "$R" k.txt; gl_rm; trr_run "$SCRIPT" "$R" fb; gl_ok_gp1r
    R="$(gl_gp1r)"; gl_nu "(gp1r)" lazy git -C "$R" -c diff.autoRefreshIndex=false diff --name-only HEAD --
    gl_mut MD gl_gp1r fb gl_ok_gp1r
    ok "(gp1r) entrée racée sous autocrlf, blob d'index absent => rc 2, uploadpack jamais exécuté (témoin pairé : le diff SANS rafraîchissement l'exécute)"
    ok "(trr6) MD : l'export ôté du seul diff du recensement => uploadpack exécuté — (gp1r) rougirait"

    # (gp12) un git qui ne SAIT PAS refuser le rapatriement (revue de sécurité) : faux git
    # FIXE qui n'a pas --no-lazy-fetch et ignore la variable, comme un git < 2.45. Dans un
    # clone partiel la porte ne lance alors NI le diff NI un cat-file : perte DITE, rc 0.
    _gl_real="$(command -v git)"
    GL_FOLD="$GL_W/faux-vieux"; mkdir "$GL_FOLD"; printf '%s' "$_gl_real" > "$GL_FOLD/real"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'unset GIT_NO_LAZY_FETCH' 'for a in "$@"; do' '  case "$a" in' '    --no-lazy-fetch)' \
        '      echo "unknown option: --no-lazy-fetch" >&2' '      exit 129 ;;' '  esac' 'done' 'exec "$real" "$@"'
    } > "$GL_FOLD/git"
    chmod +x "$GL_FOLD/git"
    gl_ok_gp12() {
      trr_rc "(gp12)" 0
      trr_dit "(gp12)" "tracked modified file(s) not enumerated ($GL_PCL"
      trr_dit "(gp12)" "index entries not read ($GL_PCL"
      trr_tait "(gp12)" "clean."; gl_aucune "(gp12)"
    }
    R="$(gl_gp2)"; gl_rm; gl_runp "$SCRIPT" "$R" "$GL_FOLD:$NOGL_PATH"; gl_ok_gp12
    R="$(gl_gp2)"; gl_nu "(gp12) témoin : l'export est INERTE sous ce git" lazy env GIT_NO_LAZY_FETCH=1 "$GL_FOLD/git" -C "$R" cat-file blob "$_gl_s"
    R="$(gl_gp2)"; gl_rm; trr_mutant MP3; gl_runp "$TRR_MUT/MP3.sh" "$R" "$GL_FOLD:$NOGL_PATH"; gl_rougit "(trr6) MP3" gl_ok_gp12
    R="$(gl_gp2)"; gl_rm; trr_mutant MP4; gl_runp "$TRR_MUT/MP4.sh" "$R" "$GL_FOLD:$NOGL_PATH"; gl_rougit "(trr6) MP4" gl_ok_gp12
    # (gp12b) la sonde skip-worktree, sous le même git : d/ est IGNORÉ par la racine, le
    # recensement n'y descend pas (ne lit pas d/.gitignore), la sonde batch le lirait
    # et rapatrierait — elle n'est PAS jouée, « not checked » est dit.
    GL_OD="$GL_W/od"; $GL_G init -q "$GL_OD"; git -C "$GL_OD" config uploadpack.allowFilter true
    mkdir "$GL_OD/d"; printf 'seed\n' > "$GL_OD/seed.txt"; printf 'd/\n' > "$GL_OD/.gitignore"
    printf 'k\n' > "$GL_OD/d/keep.txt"; printf '!keep.log\n' > "$GL_OD/d/.gitignore"
    $GL_G -C "$GL_OD" add -A >/dev/null 2>&1; $GL_G -C "$GL_OD" add -f d/keep.txt d/.gitignore >/dev/null 2>&1
    $GL_G -C "$GL_OD" commit -qm c0 >/dev/null 2>&1
    gl_gp12b() {
      local Q; Q="$(gl_neuf)"
      $GL_G clone -q --filter=blob:none --no-checkout "file://$GL_OD" "$Q" >/dev/null 2>&1
      git -C "$Q" config protocol.file.allow always; printf '.agents/\n' >> "$Q/.git/info/exclude"
      $GL_G -C "$Q" sparse-checkout set --no-cone '/seed.txt' '/.gitignore' '/d/keep.txt' >/dev/null 2>&1
      $GL_G -C "$Q" checkout -q master >/dev/null 2>&1
      git -C "$Q" config remote.origin.uploadpack "$GL_T/lazy"
      printf 'u\n' > "$Q/d/u.txt"
      printf '%s' "$Q"
    }
    gl_ok_gp12b() {
      trr_rc "(gp12b)" 0; trr_dit "(gp12b)" "skip-worktree .gitignore file(s) not checked ($GL_PCL"
      trr_tait "(gp12b)" "clean."; gl_aucune "(gp12b)"
    }
    R="$(gl_gp12b)"; gl_valide "(gp12b)" "$R" d/.gitignore; gl_rm; gl_runp "$SCRIPT" "$R" "$GL_FOLD:$TRSTUB:$NOGL_PATH"; gl_ok_gp12b
    R="$(gl_gp12b)"; gl_rm; trr_mutant MP5; gl_runp "$TRR_MUT/MP5.sh" "$R" "$GL_FOLD:$TRSTUB:$NOGL_PATH"; gl_rougit "(trr6) MP5" gl_ok_gp12b
    ok "(gp12) clone partiel sous un git sans --no-lazy-fetch => ni diff ni cat-file, deux pertes dites, rc 0, uploadpack jamais exécuté (témoin pairé : l'export y est inerte)"
    ok "(gp12b) même git, sonde skip-worktree => non jouée, « not checked » dit, uploadpack jamais exécuté"
    ok "(trr6) MP3/MP4/MP5 : saut du lecteur d'index / du diff / de la sonde ôté => uploadpack exécuté ou perte tue — (gp12) (gp12b) rougiraient"

    # (gp3) d/.gitignore `*.key` skip-worktree illisible : SUR-listage, la clé est vue ; rien
    # d'IGNORÉ sous d/, donc rien ne peut être caché : AUCUNE ligne de perte (décision
    # orchestrateur sur le majeur 1 de l'exec-critic : seul un non-suivi ignoré compte)
    gl_gp3() { local Q; Q="$(gl_neuf)"; gl_clone "$GL_OGI2" "$Q" partiel creux; printf '%s\n' "$TRR_K" > "$Q/d/u.key"; printf '%s' "$Q"; }
    gl_ok_gp3() { trr_rc "(gp3)" 2; trr_loc "(gp3)" "d/u.key:1"; trr_tait "(gp3)" "$GL_SWL"; gl_aucune "(gp3)"; }
    R="$(gl_gp3)"; gl_valide "(gp3)" "$R" d/.gitignore; gl_rm; trr_run "$SCRIPT" "$R" fb; gl_ok_gp3
    R="$(gl_gp3)"; gl_nu "(gp3)" lazy git -C "$R" ls-files --others --exclude-standard
    gl_mut MG8 gl_gp3 fb gl_ok_gp3
    gl_mut MX gl_gp3 fb gl_ok_gp3
    ok "(gp3) .gitignore skip-worktree illisible (*.key) => clé SUR-listée, rc 2, aucune ligne de perte (rien d'ignoré à cacher) ; uploadpack jamais exécuté (témoin pairé : ls-files nu l'exécute)"

    # (gp4) négation `!keep.log` perdue sous une racine `*.log` : DEGRADED dit, jamais clean
    gl_gp4() {
      local Q; Q="$(gl_neuf)"; gl_clone "$GL_ONEG" "$Q" partiel creux
      printf '%s\n' "$TRR_K" > "$Q/d/keep.log"; printf 'x\n' > "$Q/d/other.log"
      printf '%s' "$Q"
    }
    gl_ok_gp4() {
      trr_rc "(gp4)" 0; trr_dit "(gp4)" "$GL_SWL"
      trr_tait "(gp4)" "clean."; trr_tait "(gp4)" "nothing to scan"; gl_aucune "(gp4)"
    }
    for SH844 in $T844_SHELLS; do
      R="$(gl_gp4)"; gl_valide "(gp4)" "$R" d/.gitignore; gl_rm; trr_run "$SCRIPT" "$R" fb "$SH844"; gl_ok_gp4
    done
    R="$(gl_gp4)"; gl_nu "(gp4)" lazy git -C "$R" ls-files --others --exclude-standard
    gl_mut MG gl_gp4 fb gl_ok_gp4
    gl_mut MX gl_gp4 fb gl_ok_gp4
    # MGBX : la sonde batch SEULE privée de l'export (le recensement le garde) — le
    # marqueur, s'il naît, est attribuable à la sonde (sous MX, le recensement
    # rapatrie d'abord) : la moitié « exécution » du MG4 planifié
    gl_mut MGBX gl_gp4 fb gl_ok_gp4
    ok "(gp4) négation perdue d'un .gitignore skip-worktree illisible => rc 0, la perte DITE, ni « clean. » ni « nothing to scan » (sous chaque bash)"
    ok "(trr6) MGBX : la sonde batch sans l'export => uploadpack exécuté par la sonde elle-même — (gp4) rougirait"

    # (gp4s) le même dépôt partiel, sous-module initialisé d'un super-projet
    gl_gp4s() {
      local S; S="$(trr_repo)"
      gl_clone "$GL_ONEG" "$S/sub" partiel creux
      $GL_G -C "$S" add sub >/dev/null 2>&1; $GL_G -C "$S" commit -qm sub >/dev/null 2>&1
      printf '%s\n' "$TRR_K" > "$S/sub/d/keep.log"
      printf '%s' "$S"
    }
    gl_ok_gp4s() { trr_rc "(gp4s)" 0; trr_dit "(gp4s)" "$GL_SWL"; trr_tait "(gp4s)" "clean."; gl_aucune "(gp4s)"; }
    R="$(gl_gp4s)"
    [ "$(git -C "$R" ls-files -s sub | cut -c1-6)" = 160000 ] || fail "(gp4s) fixture : sub doit être un gitlink 160000"
    gl_valide "(gp4s)" "$R/sub" d/.gitignore; gl_rm; trr_run "$SCRIPT" "$R" stub; gl_ok_gp4s
    R="$(gl_gp4s)"; gl_nu "(gp4s)" lazy git -C "$R/sub" ls-files --others --exclude-standard
    gl_mut MG gl_gp4s stub gl_ok_gp4s
    gl_mut MG2 gl_gp4s stub gl_ok_gp4s
    gl_mut MX gl_gp4s stub gl_ok_gp4s
    ok "(gp4s) même perte dans un sous-module initialisé => rc 0, dite, jamais « clean. »"
    ok "(trr6) MG, MG2, MG8, MX : compte forcé à 0 / appel des sous-modules ôté / tout non-suivi compté / export ôté => (gp3) (gp4) (gp4s) rougiraient"

    # (gp10)/(gp11) cinq répertoires creux d'un clone partiel, .gitignore `!keep.log` illisible
    # chacun ; un non-suivi NON ignoré par répertoire => rien à cacher, « clean. » (gp10) ;
    # plus UN fichier ignoré (d3/x.log, racine `*.log`) => UNE perte dite (gp11)
    GL_O5="$GL_W/o5"; $GL_G init -q "$GL_O5"; git -C "$GL_O5" config uploadpack.allowFilter true
    printf 'seed\n' > "$GL_O5/seed.txt"; printf '*.log\n' > "$GL_O5/.gitignore"
    for _i in 1 2 3 4 5; do mkdir "$GL_O5/d$_i"; printf 'k\n' > "$GL_O5/d$_i/keep.txt"; printf '!keep.log\n' > "$GL_O5/d$_i/.gitignore"; done
    $GL_G -C "$GL_O5" add -A >/dev/null 2>&1; $GL_G -C "$GL_O5" commit -qm c0 >/dev/null 2>&1
    gl_gp10() {
      local Q i; Q="$(gl_neuf)"
      $GL_G clone -q --filter=blob:none --no-checkout "file://$GL_O5" "$Q" >/dev/null 2>&1
      git -C "$Q" config protocol.file.allow always; printf '.agents/\n' >> "$Q/.git/info/exclude"
      $GL_G -C "$Q" sparse-checkout set --no-cone '/seed.txt' '/.gitignore' '/d*/keep.txt' >/dev/null 2>&1
      $GL_G -C "$Q" checkout -q master >/dev/null 2>&1
      git -C "$Q" config remote.origin.uploadpack "$GL_T/lazy"
      for i in 1 2 3 4 5; do printf 'u\n' > "$Q/d$i/u.txt"; done
      printf '%s' "$Q"
    }
    gl_gp11() { local Q; Q="$(gl_gp10)"; printf 'x\n' > "$Q/d3/x.log"; printf '%s' "$Q"; }
    gl_ok_gp10() { trr_rc "(gp10)" 0; trr_dit "(gp10)" "SECRETS GATE (class-0): clean."; trr_tait "(gp10)" "COVERAGE DEGRADED"; gl_aucune "(gp10)"; }
    gl_ok_gp11() {
      trr_rc "(gp11)" 0; trr_dit "(gp11)" "COVERAGE DEGRADED: 1 $GL_SWL"
      trr_tait "(gp11)" "clean."; gl_aucune "(gp11)"
    }
    R="$(gl_gp10)"; gl_valide "(gp10)" "$R" d1/.gitignore; gl_rm; trr_run "$SCRIPT" "$R" stub; gl_ok_gp10
    R="$(gl_gp11)"; gl_rm; trr_run "$SCRIPT" "$R" stub; gl_ok_gp11
    gl_mut MG8 gl_gp10 stub gl_ok_gp10
    gl_mut MG3 gl_gp10 stub gl_ok_gp10
    gl_mut MG8 gl_gp11 stub gl_ok_gp11
    gl_mut MG gl_gp11 stub gl_ok_gp11
    ok "(gp10) 5 .gitignore skip-worktree illisibles, 5 non-suivis NON ignorés => « clean. », aucune perte (rien d'ignoré à cacher)"
    ok "(gp11) le même + un fichier IGNORÉ (d3/x.log) => « COVERAGE DEGRADED: 1 … », jamais clean"
    ok "(trr6) MG8/MG3 : tout non-suivi compté / filtre ôté => DEGRADED faux — (gp10) rougirait ; MG8/MG : 5 au lieu de 1 / compte à 0 — (gp11) rougirait"
  fi

  if ! gl_au_moins 2 42; then
    echo "  SKIP (gp5-gp9 ; mutants MG3-MG7) : git $_gl_v < 2.42 — pas de cat-file --batch-check -Z, la porte y dit « not checked »"
  else
    # (gp5) clone partiel CREUX où rien n'est à perdre : AUCUNE ligne de perte, y compris sous MX
    gl_gp5a() { local Q; Q="$(gl_neuf)"; gl_clone "$GL_ONEG" "$Q" partiel cone; printf '%s' "$Q"; }
    gl_gp5b() { local Q; Q="$(gl_neuf)"; gl_clone "$GL_ONEG" "$Q" partiel creux; printf '%s' "$Q"; }
    gl_ok_gp5() {
      trr_rc "(gp5)" 0; trr_dit "(gp5)" "nothing to scan"
      trr_tait "(gp5)" "COVERAGE DEGRADED"; gl_aucune "(gp5)"
    }
    for SH844 in $T844_SHELLS; do
      for _f in gl_gp5a gl_gp5b; do
        R="$("$_f")"; gl_rm; trr_run "$SCRIPT" "$R" stub "$SH844"; gl_ok_gp5
      done
    done
    R="$(gl_gp5b)"; gl_valide "(gp5b)" "$R" d/.gitignore
    for _f in gl_gp5a gl_gp5b; do
      R="$("$_f")"; gl_rm; trr_mutant MX; trr_run "$TRR_MUT/MX.sh" "$R" stub; gl_ok_gp5
    done
    gl_mut MG3 gl_gp5b stub gl_ok_gp5
    ok "(gp5) clone partiel creux (cône, et non-cône sans non-suivi) => « nothing to scan », AUCUNE ligne COVERAGE DEGRADED (ce qu'un appelant lit), uploadpack jamais exécuté — aussi sous MX, sous chaque bash"
    ok "(trr6) MG3 : le filtre « répertoire avec un non-suivi ignoré » ôté => DEGRADED permanent — (gp5) rougirait"

    # (gp6) clone COMPLET creux : blob PRÉSENT, git le lit, la négation tient — aucune ligne de
    # perte ; d/other.log (ignoré, jamais ré-inclus) fait passer le candidat jusqu'à la sonde
    gl_gp6() {
      local Q; Q="$(gl_neuf)"; gl_clone "$GL_ONEG" "$Q" complet creux
      printf '%s\n' "$TRR_K" > "$Q/d/keep.log"; printf 'x\n' > "$Q/d/other.log"
      printf '%s' "$Q"
    }
    gl_ok_gp6() { trr_rc "(gp6)" 2; trr_loc "(gp6)" "d/keep.log:1"; trr_tait "(gp6)" "skip-worktree .gitignore"; }
    R="$(gl_gp6)"
    [ ! -e "$R/d/.gitignore" ] || fail "(gp6) fixture : d/.gitignore doit être ABSENT du disque (skip-worktree)"
    gl_absent "$R" d/.gitignore && fail "(gp6) fixture : clone complet, le blob doit être présent"
    trr_run "$SCRIPT" "$R" fb; gl_ok_gp6
    gl_mut MG7 gl_gp6 fb gl_ok_gp6
    ok "(gp6) clone complet creux, .gitignore skip-worktree absent du disque mais blob présent => rc 2 sur la clé, aucune ligne de perte"
    ok "(trr6) MG7 : test de présence du blob ôté => perte fantôme — (gp6) rougirait"

    # (gp7) un échec de la sonde est DIT, jamais un compte de 0 (C22) ; git sans -Z : « not checked »
    _gl_real="$(command -v git)"
    GL_FG="$GL_W/faux128"; GL_FG9="$GL_W/faux129"; mkdir "$GL_FG" "$GL_FG9"
    printf '%s' "$_gl_real" > "$GL_FG/real"; printf '%s' "$_gl_real" > "$GL_FG9/real"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'b=0' 'for a in "$@"; do' '  case "$a" in' '    --batch-check)' '      b=1 ;;' '  esac' 'done' \
        '[ "$b" = 1 ] || exec "$real" "$@"' 'n="$(head -c 1 | wc -c | tr -d " ")"' '[ "$n" = 0 ] && exec "$real" "$@" < /dev/null' 'exit 128'
    } > "$GL_FG/git"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'for a in "$@"; do' '  case "$a" in' '    --batch-check)' '      exit 129 ;;' '  esac' 'done' 'exec "$real" "$@"'
    } > "$GL_FG9/git"
    chmod +x "$GL_FG/git" "$GL_FG9/git"
    gl_gp7() {  # dépôt local : d/.gitignore skip-worktree ôté du disque (blob présent), d/u.txt bénin, d/a.tmp ignoré
      local R; R="$(trr_repo)"; mkdir "$R/d"; printf 'keep\n' > "$R/d/keep.txt"; printf '*.tmp\n' > "$R/d/.gitignore"
      $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm d >/dev/null 2>&1
      git -C "$R" update-index --skip-worktree d/.gitignore; rm -f "$R/d/.gitignore"; printf 'benign\n' > "$R/d/u.txt"
      printf 'x\n' > "$R/d/a.tmp"
      printf '%s' "$R"
    }
    gl_ok_gp7() {
      trr_rc "(gp7)" 0; trr_dit "(gp7)" "skip-worktree .gitignore check failed (git rc 128)"
      trr_tait "(gp7)" "clean."
    }
    R="$(gl_gp7)"; gl_runp "$SCRIPT" "$R" "$TRSTUB:$NOGL_PATH"
    trr_dit "(gp7) témoin sans faux git" "SECRETS GATE (class-0): clean."; trr_tait "(gp7) témoin sans faux git" "skip-worktree"
    R="$(gl_gp7)"; gl_runp "$SCRIPT" "$R" "$GL_FG:$TRSTUB:$NOGL_PATH"; gl_ok_gp7
    R="$(gl_gp7)"; trr_mutant MG5; gl_runp "$TRR_MUT/MG5.sh" "$R" "$GL_FG:$TRSTUB:$NOGL_PATH"
    gl_rougit "(trr6) MG5" gl_ok_gp7
    R="$(gl_gp7)"; gl_runp "$SCRIPT" "$R" "$GL_FG9:$TRSTUB:$NOGL_PATH"
    trr_rc "(gp7b)" 0; trr_dit "(gp7b)" "git < 2.42 : skip-worktree .gitignore not checked"; trr_tait "(gp7b)" "clean."
    ok "(gp7) cat-file --batch-check en échec (rc 128) => DEGRADED « check failed (git rc 128) », jamais clean ; (gp7b) sans -Z (rc 129) => « git < 2.42 … not checked » (témoin sans faux git : clean.)"
    ok "(trr6) MG5 : l'échec avalé => « clean. » — (gp7) rougirait"

    # (gp13) GIT_LITERAL_PATHSPECS=1 dans l'environnement : git refuse le relevé des
    # `.gitignore` par motif glob (rc 128) — un échec DIT, jamais un 0 muet (revue de clôture C3)
    gl_ok_gp13() {
      trr_rc "(gp13)" 0; trr_dit "(gp13)" "skip-worktree .gitignore check failed (git rc 128)"
      trr_tait "(gp13)" "clean."
    }
    R="$(gl_gp7)"; GIT_LITERAL_PATHSPECS=1 trr_run "$SCRIPT" "$R" stub; gl_ok_gp13
    R="$(gl_gp7)"; trr_mutant MG5; GIT_LITERAL_PATHSPECS=1 trr_run "$TRR_MUT/MG5.sh" "$R" stub
    gl_rougit "(trr6) MG5/gp13" gl_ok_gp13
    ok "(gp13) GIT_LITERAL_PATHSPECS=1 => le relevé glob des .gitignore refusé, « check failed (git rc 128) » dit, jamais clean"

    # (gp8) index creux (sparse-index) et non-suivi HORS du cône : aucune ligne d'avertissement comptée (C24)
    gl_gp8() {
      local R; R="$(trr_repo)"; mkdir "$R/d"; printf 'keep\n' > "$R/d/keep.txt"; printf '*.tmp\n' > "$R/d/.gitignore"
      $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm d >/dev/null 2>&1
      $GIT_ISO -C "$R" sparse-checkout set --cone --sparse-index >/dev/null 2>&1
      mkdir -p "$R/d"; printf 'benign\n' > "$R/d/u.txt"
      printf '%s' "$R"
    }
    gl_ok_gp8() { trr_rc "(gp8)" 0; trr_dit "(gp8)" "SECRETS GATE (class-0): clean."; trr_tait "(gp8)" "warning line(s)"; }
    R="$(gl_gp8)"
    # Fixture refusée sous un git qui sait écrire un index creux (>= 2.42 ici) : FAIL, jamais SKIP (C20).
    [ "$(git -C "$R" config --get index.sparse 2>/dev/null)" = true ] \
      || fail "(gp8) fixture REFUSÉE : git $_gl_v n'a pas écrit d'index creux (index.sparse) — le bras ne prouverait rien"
    trr_run "$SCRIPT" "$R" stub; gl_ok_gp8
    gl_mut MG6 gl_gp8 stub gl_ok_gp8
    ok "(gp8) index creux + non-suivi hors du cône => aucune « warning line(s) », « clean. »"
    ok "(trr6) MG6 : le conseil sparseIndexExpanded rétabli => ses lignes comptées comme pertes — (gp8) rougirait"

    # (gp9) COÛT : UNE sonde batch par dépôt, jamais un processus par .gitignore ; aucun candidat => aucun processus
    GL_CG="$GL_W/comptegit"; mkdir "$GL_CG"; GL_APP="$GL_W/appels"
    printf '%s' "$_gl_real" > "$GL_CG/real"; printf '%s' "$GL_APP" > "$GL_CG/journal"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'journal="$(cat "$(dirname "$0")/journal")"'
      printf '%s\n' 'printf "%s\n" "$*" >> "$journal"' 'exec "$real" "$@"'
    } > "$GL_CG/git"
    chmod +x "$GL_CG/git"
    gl_gp9() {  # cinq répertoires : chacun un .gitignore skip-worktree ôté du disque ET un non-suivi ignoré
      local R i; R="$(trr_repo)"
      for i in 1 2 3 4 5; do mkdir "$R/d$i"; printf 'k\n' > "$R/d$i/keep.txt"; printf '*.tmp\n' > "$R/d$i/.gitignore"; done
      $GIT_ISO -C "$R" add -A >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm d >/dev/null 2>&1
      for i in 1 2 3 4 5; do
        git -C "$R" update-index --skip-worktree "d$i/.gitignore"; rm -f "$R/d$i/.gitignore"
        printf 'b\n' > "$R/d$i/u.txt"; printf 'b\n' > "$R/d$i/a.tmp"
      done
      printf '%s' "$R"
    }
    gl_ok_gp9() {
      trr_rc "(gp9)" 0; trr_dit "(gp9)" "SECRETS GATE (class-0): clean."
      [ "$(grep -c 'cat-file --batch-check -Z' "$GL_APP")" = 1 ] || fail "(gp9) UNE sonde batch attendue : $(grep -c 'cat-file' "$GL_APP") cat-file"
      [ "$(grep -c 'cat-file -e' "$GL_APP")" = 0 ] || fail "(gp9) aucun cat-file par entrée attendu"
      [ "$(grep -c 'ls-files --others --ignored --exclude-standard --directory' "$GL_APP")" = 1 ] || fail "(gp9) UN relevé des non-suivis ignorés attendu"
    }
    R="$(gl_gp9)"; : > "$GL_APP"; gl_runp "$SCRIPT" "$R" "$GL_CG:$TRSTUB:$NOGL_PATH"; gl_ok_gp9
    R="$(trr_repo)"; printf 'b\n' > "$R/u.txt"; : > "$GL_APP"; gl_runp "$SCRIPT" "$R" "$GL_CG:$TRSTUB:$NOGL_PATH"
    [ "$(grep -c -e 'cat-file' -e 'ls-files --others --ignored --exclude-standard --directory' "$GL_APP")" = 0 ] \
      || fail "(gp9) témoin sans candidat : aucun processus de sonde attendu, journal : $(cat "$GL_APP")"
    R="$(gl_gp9)"; : > "$GL_APP"; trr_mutant MG4; gl_runp "$TRR_MUT/MG4.sh" "$R" "$GL_CG:$TRSTUB:$NOGL_PATH"
    gl_rougit "(trr6) MG4" gl_ok_gp9
    ok "(gp9) coût : 5 .gitignore skip-worktree candidats => UN relevé des non-suivis et UNE sonde batch ; aucun candidat => aucun processus de plus"
    ok "(trr6) MG4 : un cat-file par entrée => 5 processus au lieu d'un — (gp9) rougirait"

    # (gi1) SIGINT au GROUPE de la porte (comme un Ctrl-C) pendant un appel git lent : les
    # fichiers de travail du recensement (gitleaks-filters.*, gitleaks-sw.*) sont retirés
    # par cleanup() (revue de sécurité). Lancé par python, SIGINT remis au défaut AVANT le
    # lancement : un `&` d'un shell non interactif ignore SIGINT, et bash ne peut plus le
    # rétablir. Faux git lent FIXE : il dort sur le relevé des pilotes, ou sur le relevé des
    # non-suivis ignorés.
    GL_SLF="$GL_W/lent-filtres"; GL_SLS="$GL_W/lent-sw"; mkdir "$GL_SLF" "$GL_SLS"
    printf '%s' "$_gl_real" > "$GL_SLF/real"; printf '%s' "$_gl_real" > "$GL_SLS/real"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'for a in "$@"; do' '  case "$a" in' '    "^filter"*)' '      sleep 5 ;;' '  esac' 'done' 'exec "$real" "$@"'
    } > "$GL_SLF/git"
    {
      printf '%s\n' '#!/usr/bin/env bash'
      printf '%s\n' "$GL_REEL"
      printf '%s\n' 'for a in "$@"; do' '  case "$a" in' '    --ignored)' '      sleep 5 ;;' '  esac' 'done' 'exec "$real" "$@"'
    } > "$GL_SLS/git"
    chmod +x "$GL_SLF/git" "$GL_SLS/git"
    gl_sigint() {  # $1 script  $2 dépôt  $3 PATH  $4 motif du fichier de travail — imprime absent | reste | retire
      local T; T="$(mktemp -d "$TRR_W/si.XXXXXX")"
      "$LC_PY" -c '
import glob, os, signal, subprocess, sys, time
script, depot, path, tmp, motif = sys.argv[1:6]
signal.signal(signal.SIGINT, signal.SIG_DFL)
env = dict(os.environ, PATH=path, TMPDIR=tmp)
p = subprocess.Popen(["bash", script], cwd=depot, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
vu = False
fin = time.time() + 20
while time.time() < fin and p.poll() is None:
    if glob.glob(os.path.join(tmp, motif)):
        vu = True
        break
    time.sleep(0.05)
if not vu:
    p.kill()
    p.wait()
    print("absent")
    sys.exit(0)
time.sleep(0.3)
os.killpg(p.pid, signal.SIGINT)
p.wait()
time.sleep(0.5)
print("reste" if glob.glob(os.path.join(tmp, motif)) else "retire")
' "$1" "$2" "$3" "$T" "$4"
    }
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$SCRIPT" "$R" "$GL_SLF:$TRSTUB:$NOGL_PATH" 'gitleaks-filters.*')"
    [ "$_gl_si" = retire ] || fail "(gi1) SIGINT pendant le relevé des pilotes : gitleaks-filters.* « $_gl_si » (retire attendu)"
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$SCRIPT" "$R" "$GL_SLS:$TRSTUB:$NOGL_PATH" 'gitleaks-sw.*')"
    [ "$_gl_si" = retire ] || fail "(gi1) SIGINT pendant la sonde skip-worktree : gitleaks-sw.* « $_gl_si » (retire attendu)"
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$SCRIPT" "$R" "$GL_SLS:$TRSTUB:$NOGL_PATH" 'gitleaks-census.*')"
    [ "$_gl_si" = retire ] || fail "(gi1) SIGINT pendant le recensement : gitleaks-census.* « $_gl_si » (retire attendu)"
    trr_mutant MCL
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$TRR_MUT/MCL.sh" "$R" "$GL_SLS:$TRSTUB:$NOGL_PATH" 'gitleaks-census.*')"
    [ "$_gl_si" = reste ] || fail "(trr6) MCL : sans ses lignes de cleanup(), gitleaks-census.* devait RESTER (« $_gl_si ») — (gi1) ne pourrait pas rougir"
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$TRR_MUT/MCL.sh" "$R" "$GL_SLF:$TRSTUB:$NOGL_PATH" 'gitleaks-filters.*')"
    [ "$_gl_si" = reste ] || fail "(trr6) MCL : sans les deux lignes de cleanup(), gitleaks-filters.* devait RESTER (« $_gl_si ») — (gi1) ne pourrait pas rougir"
    R="$(gl_gp7)"; _gl_si="$(gl_sigint "$TRR_MUT/MCL.sh" "$R" "$GL_SLS:$TRSTUB:$NOGL_PATH" 'gitleaks-sw.*')"
    [ "$_gl_si" = reste ] || fail "(trr6) MCL : sans les deux lignes de cleanup(), gitleaks-sw.* devait RESTER (« $_gl_si ») — (gi1) ne pourrait pas rougir"
    ok "(gi1) SIGINT au groupe pendant un git lent : gitleaks-filters.*, gitleaks-sw.* et gitleaks-census.* retirés par cleanup()"
    ok "(trr6) MCL : les deux lignes de cleanup() ôtées => les fichiers de travail restent sous TMPDIR — (gi1) rougirait"
  fi
fi
# (trr16b) doublon LÉGITIME : un fichier de sous-module indexé (diff-index) ET
# illisible dans l'arbre (FAILLIST) arrive deux fois, même sha => lu, aucune perte
if [ -z "$TRR_SKIP" ]; then
  _s16="$(mktemp -d "$TRR_W/src.XXXXXX")"; $GIT_ISO init -q "$_s16"; printf 'benign\n' > "$_s16/mod.txt"
  $GIT_ISO -C "$_s16" add -A >/dev/null 2>&1; $GIT_ISO -C "$_s16" commit -qm s >/dev/null 2>&1
  R="$(trr_repo)"; $GIT_ISO -C "$R" submodule add -q "$_s16" vendor/sub >/dev/null 2>&1; $GIT_ISO -C "$R" commit -qm sub >/dev/null 2>&1
  # CRLF dans le blob, puis core.autocrlf=true dans le sous-module : la règle ne
  # hache jamais le fichier écrit, aucun filtre ne peut fabriquer une fausse perte.
  printf 'benign2\r\n' > "$R/vendor/sub/new.txt"; git -C "$R/vendor/sub" -c core.autocrlf=false add new.txt
  git -C "$R/vendor/sub" config core.autocrlf true; chmod 000 "$R/vendor/sub/new.txt"
  for m in fb nopy; do
    trr_run "$SCRIPT" "$R" "$m"
    trr_rc "(trr16b/$m)" 0
    trr_tait "(trr16b/$m)" "index entries not read"
    trr_dit "(trr16b/$m)" "(1 index entr"
  done
  trr_mutant M15; trr_run "$TRR_MUT/M15.sh" "$R" fb
  trr_dit "(trr6) M15 (doublon de même sha compté perdu, python) — (trr16b) doit dire une perte, sinon il ne pourrait pas rougir" "index entries not read"
  trr_mutant M15n; trr_run "$TRR_MUT/M15n.sh" "$R" nopy
  trr_dit "(trr6) M15n (doublon de même sha compté perdu, sans python) — (trr16b) doit dire une perte" "index entries not read"
  chmod 644 "$R/vendor/sub/new.txt"
  ok "(trr16b) même sha venu de diff-index ET de l'index relu d'un fichier illisible => lu une fois, aucune perte (python et sans python)"
  ok "(trr6) M15/M15n : le doublon de même sha compté perdu => perte fantôme — (trr16b) rougirait"
  # (trrK1b) realpath (K1) : `.git/modules/evil` est un LIEN vers un git dir hors
  # de modules/ ; le nom passe le contrôle syntaxique, le chemin physique non.
  R="$(trr_super absorbed)"
  git config -f "$R/.gitmodules" --rename-section "submodule.vendor/sub" "submodule.evil"
  _h9="$(mktemp -d "$TRR_W/gdhors.XXXXXX")"; cp -R "$R/.git/modules/vendor/sub/." "$_h9/"
  ln -s "$_h9" "$R/.git/modules/evil" 2>/dev/null
  if [ -L "$R/.git/modules/evil" ]; then
    chmod 000 "$R/vendor/sub"
    trr_run "$SCRIPT" "$R" fb
    trr_rc "(trrK1b)" 0
    trr_dit "(trrK1b)" ".gitmodules name is unsafe"
    trr_tait "(trrK1b)" "index:vendor/sub/creds.txt"
    trr_mutant M16; trr_run "$TRR_MUT/M16.sh" "$R" fb
    [ "$TRR_RC" -eq 2 ] || fail "(trr6) M16 (contrôle realpath retiré) : le git dir hors de modules/ doit être lu (rc 2), got $TRR_RC — sans cela (trrK1b) ne pourrait pas rougir"
    chmod 755 "$R/vendor/sub"
    ok "(trrK1b) modules/evil lien vers un git dir hors de modules/ => refusé « unsafe », DEGRADED (M16 : sans realpath, lu, rc 2)"
  else
    echo "  SKIP (trrK1b): ln -s ne crée pas de lien ici (MSYS copie)"
  fi
fi

# --- (trr17) SIGTERM au SEUL bash pendant la lecture de l'index : aucun écrivain
# ne survit au nettoyage (garde_enfant + on_exit tuent et récoltent le lecteur),
# et le lecteur ne recrée jamais sa destination. Faux git LENT (1 s par objet,
# `cat-file --batch` et `cat-file blob`) ; trois entrées indexées, la clé en
# dernier, aucune dans l'arbre ; TMPDIR dédié par coup. Mesuré sur 02ec9e97 sur
# CE poste : bash différait le TERM jusqu'à la fin de la substitution de commande
# (3 s), l'orphelin n'y apparaissait pas ; la forme en arrière-plan rend la porte
# interruptible à 0 s, d'où le kill d'on_exit. Les trois défenses se masquent
# l'une l'autre : le mutant COMBINÉ M17 rougit, chacune est épinglée en (trr15).
SLOWG="$TRR_W/slowgit"; mkdir "$SLOWG"; command -v git | tr -d '\n' > "$SLOWG/real"   # donnée, jamais source (C5)
{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' "$GL_REEL"
  printf '%s\n' 'lent=0; pre=()' \
    'for a in "$@"; do' \
    '  case "$a" in' \
    '    --batch|blob)' \
    '      lent=1 ;;' \
    '  esac' \
    'done' \
    '[ "$lent" = 1 ] || exec "$real" "$@"' \
    'for a in "$@"; do' \
    '  [ "$a" = cat-file ] && break' \
    '  pre+=("$a")' \
    'done' \
    'case " $* " in' \
    '  *" --batch "*)' \
    '    while IFS= read -r sha; do' \
    '      sleep 1' \
    '      sz="$("$real" "${pre[@]}" cat-file -s "$sha" 2>/dev/null)" || { printf "%s missing\n" "$sha"; continue; }' \
    '      printf "%s blob %s\n" "$sha" "$sz"' \
    '      "$real" "${pre[@]}" cat-file blob "$sha"' \
    '      printf "\n"' \
    '    done' \
    '    exit 0 ;;' \
    'esac' \
    'sleep 1' \
    'exec "$real" "$@"'
} > "$SLOWG/git"
chmod +x "$SLOWG/git"
R17="$(trr_repo)"
printf 'a\n' > "$R17/a.txt"; printf 'b\n' > "$R17/b.txt"; printf '%s\n' "$TRR_K" > "$R17/z.txt"
$GIT_ISO -C "$R17" add a.txt b.txt z.txt; rm -f "$R17/a.txt" "$R17/b.txt" "$R17/z.txt"
_trr_existe() { [ -e "$1" ]; }
trr17_coup() {  # $1 script  $2 PATH -> TRR17_RESTE (1 si un stage survit sous le TMPDIR du coup)
  local T n pid
  T="$(mktemp -d "$TRR_W/t17.XXXXXX")"
  ( cd "$R17" && TMPDIR="$T" PATH="$2" exec bash "$1" ) >/dev/null 2>&1 &
  pid=$!
  n=0
  while [ "$n" -lt 100 ] && ! _trr_existe "$T"/gitleaks-stage.*/.gl-index.*; do
    sleep 0.1; n=$((n + 1))
  done
  _trr_existe "$T"/gitleaks-stage.*/.gl-index.* || fail "(trr17) fixture : la copie d'index n'est jamais apparue (faux git lent inopérant ?)"
  sleep 0.5
  kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  sleep 4
  TRR17_RESTE=0
  _trr_existe "$T"/gitleaks-stage.* && TRR17_RESTE=1
  return 0
}
trr17_coup "$SCRIPT" "$SLOWG:$NOGL_PATH"
[ "$TRR17_RESTE" = 0 ] || fail "(trr17/python) SIGTERM pendant la lecture : un stage (copie d'index) survit sous TMPDIR"
trr17_coup "$SCRIPT" "$TRNOPY:$SLOWG:$NOGL_PATH"
[ "$TRR17_RESTE" = 0 ] || fail "(trr17/sans python) SIGTERM pendant la lecture : un stage survit sous TMPDIR"
trr_mutant M17; trr17_coup "$TRR_MUT/M17.sh" "$SLOWG:$NOGL_PATH"
[ "$TRR17_RESTE" = 1 ] || fail "(trr6) M17 (makedirs rétabli, contrôle du dossier et kill d'on_exit retirés) : l'orphelin devait recréer la copie d'index — sans cela (trr17) ne pourrait pas rougir"
ok "(trr17) SIGTERM au seul bash pendant la lecture (python et sans python) : aucun stage ni blob ne reste sous TMPDIR"
ok "(trr6) M17 : lecteur orphelin + makedirs => la copie d'index et la clé restent sous TMPDIR — (trr17) rougirait"

# --- (trr15) ÉPINGLES TEXTUELLES : ce qu'aucun bras ne peut rejouer sans un état non reproductible
"$LC_PY" -c '
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
def une(ancre, quoi):
    if t.count(ancre) != 1:
        print("FAIL: (trr15) " + quoi + " — ancre vue " + str(t.count(ancre)) + " fois")
        sys.exit(1)
une("if ! mkdir -p \"$STAGE/${f%/*}\" 2>/dev/null; then\n                _non_copies=$((_non_copies + 1))", "M4 : l echec de mkdir est COMPTE")
une("STAGE2=\"$(mktemp -d \"${TMPDIR:-/tmp}/gitleaks-stage.XXXXXX\" 2>/dev/null)\"", "M9 : stage NEUF, meme gabarit, meme parent")
une("rm -rf \"$STAGE\" 2>/dev/null; STAGE=\"$STAGE2\"", "M9 : le stage partiel part avant la premiere ecriture")
une("        040000)\n          vide=$((vide + 1)) ;;", "040000 : une entree de sparse-index jamais ecartee en silence")
une("index read unbounded (no timeout(1), no python)", "sans python ni timeout(1) : la lecture non bornee est DITE")
une("[ \"$stg\" = 0 ] || continue", "K4 : ls-files -s, etape 0 seule")
une("GITN=(git -c core.fsmonitor=false -c core.hooksPath=/dev/null)", "K1 : fsmonitor et hooks neutralises")
une("[ -n \"${_LECTEUR:-}\" ] && { kill \"$_LECTEUR\" 2>/dev/null; wait \"$_LECTEUR\" 2>/dev/null; }", "on_exit tue et recolte le lecteur AVANT tout retrait")
une("    if not os.path.isdir(dest):\n", "le lecteur python verifie sa destination avant chaque entree")
une("garde_enfant \"$PY\" -I -c", "le lecteur python tourne sous garde_enfant")
une("garde_enfant mkdir -p", "le mkdir du lecteur shell tourne sous garde_enfant")
une("if garde_enfant ${pre[@]+", "le cat-file blob du lecteur shell tourne sous garde_enfant")
if "makedirs" in t:
    print("FAIL: (trr15) le lecteur ne doit JAMAIS recreer sa destination : makedirs present")
    sys.exit(1)
# Un appel `git` BRUT (pas gitn, pas ${GITN[@]}) qui porte une sous-commande
# ajoutée par cette tâche est refusé ; les lignes de message (deg, perte) et les
# commentaires ne sont pas des appels. Depuis T-01M4Y09EY4M664896DMGDTMDXF les
# FORMES du recensement aussi (diff --name-only, ls-files --others / --stage,
# ls-files -z) — jamais `ls-files` nu (le texte de CENSUS_WHY le porte) ; mesuré :
# la base en avait 5, toutes vues par ce relevé.
brut = re.compile(r"(?<![\w-])git\s.*(diff-index|diff --name-only|ls-files -v|ls-files -s|ls-files( -z)? --(others|stage)|ls-files -z\b|--git-path|--git-common-dir|config -z|hash-object|cat-file|rev-parse -q --verify)")
vus = 0
sh = re.sub(r"\nLIRE_INDEX_PY=" + chr(39) + r".*?\n" + chr(39) + r"\n", "\n", t, count=1, flags=re.S)
if sh == t:
    print("FAIL: (trr15) K1 : le programme python LIRE_INDEX_PY introuvable — le relevé ne sait plus quoi écarter")
    sys.exit(1)
for n, l in enumerate(sh.splitlines(), 1):
    s = l.strip()
    if s.startswith(("#", "perte_perimetre ", "deg ")):
        continue
    if "gitn " in s or "GITN[@]" in s:
        vus += 1
    if brut.search(s):
        print("FAIL: (trr15) K1 : appel git neuf sans gitn, ligne " + str(n) + " : " + s)
        sys.exit(1)
if vus < 28:
    print("FAIL: (trr15) K1 : " + str(vus) + " appel(s) par gitn seulement — le relevé ne voit plus les appels neufs")
    sys.exit(1)
' "$SCRIPT" || fail "(trr15) épingle textuelle rouge (voir la ligne FAIL ci-dessus)"
ok "(trr15) épingles : mkdir compté (M4), stage neuf (M9), 040000 dit, lecture non bornée dite, étape 0 (K4), gitn sur chaque appel git neuf (K1)"

chmod -R u+rwx "$TRR_W" 2>/dev/null; rm -rf "$TRR_W"

echo "PASS: gitleaks-scan-index ($pass check(s); gitleaks present=$HAVE_GITLEAKS)"
