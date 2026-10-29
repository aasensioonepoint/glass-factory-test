#!/usr/bin/env bash
# Suite for sca-scan.sh's EMPTY-ARRAY expansions under bash 3.2 (T-00000837 F3).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. The defect it pins: with
# `.agents/security/audit-dev-deps.local` present, NPM_SCOPE / PNPM_SCOPE are
# EMPTY arrays, and under bash < 4.4 + `set -u` a bare `"${NPM_SCOPE[@]}"` is an
# "unbound variable" that kills the audit subshell BEFORE npm runs —
# npm-audit.json holds 0 bytes, and the verdict read GO. macOS ships bash 3.2 as
# /bin/bash, so this is the configuration of every Mac adopter whose hook
# resolves `bash` to /bin/bash.
#
# Two arms:
#  (1) TEXTUAL, always: no live line of sca-scan.sh expands a possibly-empty
#      array bare. Every `"${X[@]}"` must either carry the `${X[@]+…}` guard on
#      the same site or name an array whose use is fenced by a size test
#      (listed below, each with its fence). Non-vacuity: the probe must see a
#      bare expansion when shown one.
#  (2) BEHAVIOURAL, only when /bin/bash is a real bash < 4: replays the case
#      (opt-in file present, fake npm) under that very interpreter and requires
#      that npm WAS invoked and that npm-audit.json is NOT empty.
#      Elsewhere it prints SKIP and says why — arm (1) still holds the line.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

echo "=== 1. NO BARE EXPANSION OF A POSSIBLY-EMPTY ARRAY (textual)"
# Arrays whose EVERY bare use sits behind a size test in sca-scan.sh:
#   MODULES   — `[ "${#MODULES[@]}" -eq 0 ]` exits before both loops;
#   py_locks  — inside `if [ "${#py_locks[@]}" -gt 0 ]`;
#   pin_args  — inside `if [ "${#pin_args[@]}" -gt 0 ]`.
# Anything else expanded bare is a finding. Adding a name here requires its fence.
FENCED=" MODULES py_locks pin_args "
bare_uses() {  # stdin: shell text ; stdout: array names expanded bare, one per line
  grep -v '^[[:space:]]*#' \
    | grep -oE '(\+)?"\$\{[A-Za-z_][A-Za-z0-9_]*\[@\]\}"' \
    | grep -v '^+' \
    | sed -E 's/^"\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\}"$/\1/'
}
BAD=""
while IFS= read -r name; do
  [ -n "$name" ] || continue
  case "$FENCED" in
    *" $name "*) ;;
    *) BAD="$BAD $name" ;;
  esac
done < <(bare_uses < "$SCAN")
[ -z "$BAD" ] \
  && ok "every possibly-empty array is expanded with the \${X[@]+\"\${X[@]}\"} guard" \
  || ko "bare expansion of a possibly-empty array in sca-scan.sh:$BAD"
for name in NPM_SCOPE PNPM_SCOPE; do
  grep -q "\${$name\[@\]+\"\${$name\[@\]}\"}" "$SCAN" \
    && ok "$name is expanded through the guard" \
    || ko "$name guard missing — the audit subshell dies under bash 3.2 when the opt-in is present"
done
# Non-vacuity: the probe must SEE a bare use, and must NOT see a guarded one.
[ "$(printf '%s\n' '  ( npm audit "${NPM_SCOPE[@]}" --json )' | bare_uses)" = "NPM_SCOPE" ] \
  && ok "the probe recognises a bare expansion when shown one" \
  || ko "the probe cannot detect what it is meant to ban — it measures nothing"
[ -z "$(printf '%s\n' '  ( npm audit ${NPM_SCOPE[@]+"${NPM_SCOPE[@]}"} --json )' | bare_uses)" ] \
  && ok "the probe does not flag the guarded form" \
  || ko "the probe flags the guarded form — it would reject the fix"

echo
echo "=== 2. REPLAY UNDER THE REAL bash 3.2 (behavioural)"
if [ -x /bin/bash ] && /bin/bash -c '[ "${BASH_VERSINFO[0]}" -lt 4 ]' 2>/dev/null; then
  ROOT="$TMP/repo"; BIN="$TMP/bin"; TRACE="$TMP/npm.trace"
  mkdir -p "$ROOT/.agents/security" "$ROOT/.agents/state/local/sca-reports" "$ROOT/.claude/hooks" "$BIN"
  git -C "$ROOT" init -q
  git -C "$ROOT" -c user.email=t@t.t -c user.name=t -c commit.gpgsign=false commit -q --allow-empty -m init
  printf '%s\n' '{"name":"f3-fixture","version":"1.0.0"}' > "$ROOT/package.json"
  printf '%s\n' '{"name":"f3-fixture","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"f3-fixture","version":"1.0.0"}}}' > "$ROOT/package-lock.json"
  printf '%s\n' '{"version":1,"waivers":[]}' > "$ROOT/.agents/security/sca-waivers.json"
  : > "$ROOT/.agents/security/audit-dev-deps.local"          # the opt-in: SCOPE arrays EMPTY
  { printf '#!/bin/sh\n'
    printf 'printf "%%s\\n" "$*" >> "%s"\n' "$TRACE"
    printf '%s\n' "printf '%s\\n' '{\"auditReportVersion\":2,\"vulnerabilities\":{},\"metadata\":{\"vulnerabilities\":{\"info\":0,\"low\":0,\"moderate\":0,\"high\":0,\"critical\":0,\"total\":0}}}'"
  } > "$BIN/npm"
  { printf '#!/bin/sh\n'; printf 'exit 1\n'; } > "$BIN/socket"
  { printf '#!/bin/sh\n'; printf 'exit 0\n'; } > "$BIN/trivy"
  { printf '#!/bin/sh\n'; printf 'exit 0\n'; } > "$ROOT/.claude/hooks/emit-event.sh"
  chmod +x "$BIN/npm" "$BIN/socket" "$BIN/trivy" "$ROOT/.claude/hooks/emit-event.sh"
  OUT="$( cd "$ROOT" && PATH="$BIN:$PATH" SCA_AUDIT_DEV_DEPS='' CLAUDE_PROJECT_DIR="$ROOT" /bin/bash "$SCAN" 2>&1 )"
  printf '%s' "$OUT" | grep -q "scope: dev dependencies INCLUDED" \
    && ok "precondition: the opt-in emptied the scope arrays" \
    || ko "precondition not met — the replay does not exercise empty arrays: $(printf '%s' "$OUT" | head -5)"
  [ -s "$TRACE" ] \
    && ok "bash 3.2 + opt-in: npm audit WAS invoked (args: $(head -1 "$TRACE"))" \
    || ko "bash 3.2 + opt-in: npm audit was NEVER invoked — the subshell died on an empty array"
  [ -s "$ROOT/.agents/state/local/sca-reports/npm-audit.json" ] \
    && ok "bash 3.2 + opt-in: npm-audit.json is not empty" \
    || ko "bash 3.2 + opt-in: npm-audit.json is EMPTY — the verdict would rest on no audit"
  printf '%s' "$OUT" | grep -q "unbound variable" \
    && ko "bash 3.2 + opt-in: 'unbound variable' on the output: $(printf '%s' "$OUT" | grep 'unbound variable' | head -1)" \
    || ok "bash 3.2 + opt-in: no 'unbound variable' anywhere"
else
  echo "  SKIP (2): /bin/bash is absent or bash >= 4 — the replay needs the 3.2 interpreter; arm (1) holds the line"
fi

echo
echo "=== 3. SORTIE PRÉCOCE SOUS COPILOT, postToolUse (T-01M4RWC6VHHN479J2A9RRY1BE3)"
# UN OBSERVABLE NOMMÉ (C3 du plan). Le script tourne comme la registration
# postToolUse de Copilot (AGENTS_HOOK_HOST=copilot, SCA_CHANGED_ONLY=1, aucun
# argument) depuis un `mktemp -d` hors dépôt (ROOT = ce répertoire), TMPDIR à
# côté, la charge sur stdin, et un bouchon `git` en tête de PATH qui consigne
# son appel puis exécute le vrai binaire — écrit seulement pour un chemin ABSOLU
# (un bouchon de fonction shell se rappelle lui-même : 17 123 appels mesurés).
# Mesuré à la base, charge `view` : bouchon git x2 et
# ./.agents/state/local/sca-reports/.degraded écrit. Attendu : un nom LISTÉ sort
# avant tout git, mktemp ou mkdir. Les témoins (un exclu, bash, un nom vide, la
# forme groupée, `view` sous codex) gardent les observables de la base.
lc_run() {  # $1 hôte, $2 charge -> LC_RC LC_GIT LC_AGENTS
  local hote="$1" charge="$2" p reel
  p="$(mktemp -d)"
  mkdir -p "$p/w" "$p/bouchons" "$p/tmp" "$p/ev"
  : > "$p/trace"
  reel="$(command -v git 2>/dev/null || true)"
  case "$reel" in
    /*)
      {
        printf '#!/bin/sh\n'
        printf 'printf "%%s\\n" "git" >> "%s"\n' "$p/trace"
        printf 'exec "%s" "$@"\n' "$reel"
      } > "$p/bouchons/git"
      chmod +x "$p/bouchons/git"
      ;;
  esac
  ( cd "$p/w" && printf '%s' "$charge" \
      | env PATH="$p/bouchons:$PATH" TMPDIR="$p/tmp" AGENTS_EVENTS_DIR="$p/ev" AGENTS_HOOK_HOST="$hote" SCA_CHANGED_ONLY=1 bash "$SCAN" ) >/dev/null 2>&1
  LC_RC=$?
  LC_GIT="$(grep -c '^git$' "$p/trace" || true)"
  LC_AGENTS=0
  [ -e "$p/w/.agents" ] && LC_AGENTS=1
  rm -rf "$p"
}
if [ -x "$(command -v git 2>/dev/null || true)" ]; then
  LC_VUE='{"toolName":"view","toolArgs":{"path":"src/a.py"}}'
  lc_run copilot "$LC_VUE"
  [ "$LC_GIT" -eq 0 ] && [ "$LC_AGENTS" -eq 0 ] && [ "$LC_RC" -eq 0 ] \
    && ok "copilot + view (listé) : sortie avant tout git/mktemp/mkdir — 0 git, aucun ./.agents, rc 0" \
    || ko "copilot + view (listé) : bouchon git appelé $LC_GIT fois (attendu 0, base : 2), ./.agents créé=$LC_AGENTS (attendu 0), rc $LC_RC"
  lc_temoin() {  # $1 étiquette, $2 hôte, $3 charge
    lc_run "$2" "$3"
    [ "$LC_GIT" -ge 1 ] && [ "$LC_AGENTS" -eq 1 ] \
      && ok "$1 : chemin de la base gardé (git appelé $LC_GIT fois, ./.agents écrit)" \
      || ko "$1 : chemin de la base PERDU — git appelé $LC_GIT fois, ./.agents créé=$LC_AGENTS"
  }
  lc_temoin "copilot + exclu web_fetch" copilot '{"toolName":"web_fetch","toolArgs":{"url":"https://x.invalid/"}}'
  lc_temoin "copilot + bash" copilot '{"toolName":"bash","toolArgs":{"command":"ls"}}'
  lc_temoin "copilot + nom vide" copilot '{"toolName":"","toolArgs":{"path":"a"}}'
  lc_temoin "copilot + forme groupée" copilot '{"toolCalls":[{"toolName":"view","toolArgs":{"path":"a"}}]}'
  lc_temoin "codex + view" codex "$LC_VUE"
else
  echo "  SKIP (3): git absent ou hors chemin absolu — l'observable nommé est le bouchon git"
fi

echo
echo "================================================================"
echo "sca-scan: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
