"""Banc du LOT safe-bash, côté Python (T-01M5D6XV3JV057D1SQP4PBXRR6 ; T-01M55CF5, T-01M55BRE,
T-01M53RGW, T-01M53HV4, T-01M55TRZ, T-01M56ZE6).

CE QU'IL TIENT. Les témoins (sb)/(sc)/(sd) de .claude/hooks/safe-bash-t-y.test.sh @05c8182b
(la garde Claude livrée), PORTÉS sur le hook Python LIVRÉ — `.codex/hooks/safe_bash.py` et son
jumeau `.gemini/hooks/safe_bash.py`, joués tous deux par un sous-processus, la charge en JSON
sur stdin — avec la RÈGLE du refus lue dans l'événement `hook.deny` (jamais seulement le texte) ;
les négatifs (sbNn…, la forme de commit C1a/C1b comprise) ; les bornes de temps et de panne
(jamais rc ≠ 0 ni traceback) ; trois INJECTIONS d'exception (étage 1 via `_opaque`, décodeur
ANSI-C, étage 1.5) qui doivent REFUSER ; et un échantillon rejoué sous `AGENTS_HOOK_HOST=copilot`
avec la charge au format Copilot (`toolName`/`toolArgs`, objet ou chaîne JSON) : le refus est lu
dans l'enveloppe Copilot (décision à la RACINE et imbriquée), les négatifs passent.

Deux témoins sont PROPRES au Python (sbP1, sbP2) : un `<<'E'` dans `$((…))` ou `((…))` au premier
niveau n'ouvre aucun corps (l'étage 0.5 lit ces blocs d'un seul tenant) — la garde Claude
blanchit encore la ligne suivante.

CE QU'IL NE TIENT PAS (bornes écrites) : il ne lance aucun hôte (Codex, Gemini, Copilot réels :
§ G du plan, accord du pilote) ; il ne rejoue pas les oracles de shell (repris du journal CLAUDE
S-01M5DXYQ49, et des mesures de la tâche pour sbP1/sbP2) ; il juge A/D et la règle, jamais l'effet
réel d'une commande ; les 41 négatifs de l'annexe CLAUDE ne sont pas tous recopiés.

Vecteurs de commande : du TEXTE passé au hook, jamais exécuté (classe `donnee` du recensement).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOOK_DIRS = {"codex": ROOT / ".codex" / "hooks", "gemini": ROOT / ".gemini" / "hooks"}

WIPE = "git-wipe-unscoped"
RMMV = "rm-mv-bypass-checkpoint"
BRANCH = "git-branch-force-delete"
OUTPUT = "git-output-write"
BRACE = "brace-expansion-unread"
HIDDEN = "git-subcommand-hidden"
QUOTE = "quote-scan-unread"

SQ = "'"
BIG = "{r{m..m},-rf,{1..300}} src"
EC_T1 = "echo \"$(cat <<$'EOF'\nx\nEOF\necho hi)\" ; {X} ; echo \"\n$EOF\n)\""


def _run(hook_dir, payload, tmp_path, host=None, timeout=60, prelude=None):
    """`(rc, stdout, stderr, rule)` — the hook in a subprocess, its deny event read back."""
    events = tmp_path / f"ev{time.monotonic_ns()}"
    events.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR")}
    env["AGENTS_EVENTS_DIR"] = str(events)
    if host:
        env["AGENTS_HOOK_HOST"] = host
    hook = str(hook_dir / "safe_bash.py")
    argv = [sys.executable, "-B", hook]
    if prelude:
        argv = [sys.executable, "-B", "-c", prelude, str(hook_dir), hook]
    run = subprocess.run(argv, input=json.dumps(payload).encode(), capture_output=True, cwd=ROOT, env=env,
                         timeout=timeout, check=False)
    rule = ""
    for path in events.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("kind") == "hook.deny":
                rule = event.get("data", {}).get("rule", "")
    return run.returncode, run.stdout.decode("utf-8", "replace"), run.stderr.decode("utf-8", "replace"), rule


def _verdict(stdout):
    if not stdout.strip():
        return "allow", ""
    out = json.loads(stdout)
    nested = out.get("hookSpecificOutput", {})
    if nested.get("permissionDecision") == "deny":
        return "deny", nested.get("permissionDecisionReason", "")
    return "allow", ""


# (label, command, rule, phrase) — every one REFUSED, under that rule, the phrase in the reason.
DENY = [
    # (sb1) étape 2 — `$'…'` est une citation ANSI-C.
    ("sb1a", "echo $'\\'' ; git reset --hard ; echo 'x'", WIPE, "unscoped"),
    ("sb1b", "echo $'\\'' ; git reset --hard", WIPE, "unscoped"),
    ("sb1c", "echo $'\\'' ; rm -rf src ; echo 'x'", RMMV, "checkpoint"),
    ("sb1d", "echo $'\\'' ; git branch -D wt/T-1 ; echo 'x'", BRANCH, "git branch -D"),
    ("sb1e", "git branch $'\\055D' wt/T-1", BRANCH, "git branch -D"),
    ("sb1f", "git branch $'\\U0000002dD' wt/T-1", BRANCH, "git branch -D"),
    # (sb2) étape 2 — `$(…)`/backtick dans "…" sont du code ; corps de heredoc cité dans `$(…)`.
    ("sb2a", 'echo "$(# c \\\ngit reset --hard\n)"', WIPE, "unscoped"),
    ("sb2b", 'cat <<EOF\n"\nEOF\necho ok # c \\\ngit reset --hard # "', WIPE, "unscoped"),
    ("sb2c", "$X git branch -D wt/T-1", BRANCH, "git branch -D"),
    ("sb2d", 'echo "$(git reset --hard)"', WIPE, "unscoped"),
    ("sb2d2", 'echo "$(rm -rf src)"', RMMV, "checkpoint"),
    ("sb2e", "git commit -m \"$(cat <<'EOF'\nx\nEOF)\"\ngit reset --hard", WIPE, "unscoped"),
    ("sb2f", "git commit -m \"$(cat <<'EOF'\nx\nEOF)\"\ngit reset --hard\nEOF\n#)\"", WIPE, "unscoped"),
    ("sb2g", 'git commit -m "$(cat <<EOF\nx\n$(git reset --hard)\nEOF\n)"', WIPE, "unscoped"),
    ("sb2h", "git commit -m \"$(cat <<-'EOF'\nx\n\tEOF)\"\ngit reset --hard\nEOF\n#)\"", WIPE, "unscoped"),
    ("sb2fp", "git commit -m \"$(cat <<'EOF'\nEOFX\ngit reset --hard\nEOF\n)\"", WIPE, "unscoped"),
    ("sb2j", "git commit -m \"$(cat <<'EOF'\nx\nEOF)\"\ngit reset --hard\nEOF\n)\"", WIPE, "unscoped"),
    ("sb2k", "git commit -m \"$(cat <<-'EOF'\nx\n\tEOF)\"\ngit reset --hard\nEOF\n)\"", WIPE, "unscoped"),
    ("sb2i", "echo " + '"$(' * 70 + "x" + ')"' * 70 + ' ; echo "$(date)" ; git reset --hard ; echo "x"', WIPE,
     "unscoped"),
    # (sbP) étape 3 — propres au Python : `${…}`, `$((…))`, `((…))` d'un bloc avant tout `<<`.
    ("sbP1", "echo $((1<<'E'))\ngit reset --hard\nE", WIPE, "unscoped"),
    ("sbP2", "((x<<'A'))\ngit reset --hard\nA", WIPE, "unscoped"),
    # (sb3) étape 5 — accolades développées.
    ("sb3a", "{git,reset,--hard}", WIPE, "unscoped"),
    ("sb3b", "{git,branch,-D} wt/T-1", BRANCH, "git branch -D"),
    ("sb3c", "sudo {git,} reset --hard", WIPE, "unscoped"),
    ("sb3d", "git diff --{output=AGENTS.md,}", OUTPUT, "--output"),
    ("sb3e", "git reset --{h..h}ard", WIPE, "unscoped"),
    ("sb3f", "git branch -{D..D} wt/T-1", BRANCH, "git branch -D"),
    ("sb3g", "{r{m,},{1..300}} -rf src", BRACE, "brace expansion in this command cannot be read"),
    ("sb3j", "git restore {.,}", WIPE, "unscoped"),
    ("sb4c", "{rm,-rf} src", RMMV, "checkpoint"),
    ("sb3q", "{git,'reset',--hard}", BRACE, "holds a quoted piece"),
    ("sb3q2", '{rm,"-rf"} src', BRACE, "cannot be read"),
    # (sb4) étape 6 — alias caché ; étape 4 — option de reset à expansion ; `xargs` en tête.
    ("sb4a", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D' git bd wt/T-1", HIDDEN,
     "git ALIAS is defined"),
    ("sb4a2", "git -c alias.bd='branch -D' bd wt/T-1", HIDDEN, "git ALIAS is defined"),
    ("sb4a3", "git --config-env=alias.bd=V bd wt/T-1", HIDDEN, "git ALIAS is defined"),
    ("sb4a4", "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D' git bd wt/T-1",
     HIDDEN, "git ALIAS is defined"),
    ("sb4a5", "GIT_CONFIG_PARAMETERS=\"'alias.bd=branch -D'\" git bd wt/T-1", HIDDEN, "git ALIAS is defined"),
    ("sb4a6", "git -c alias.bd=x bd", HIDDEN, "exported by an EARLIER command"),
    ("sb4b", "git reset $x", WIPE, "unscoped"),
    ("sb4d", "xargs git checkout --", WIPE, "unscoped"),
    ("sb4d2", "xargs -0 -r git checkout --", WIPE, "unscoped"),
    ("sb4d3", "printf wt/T-1 | xargs git branch -D", BRANCH, "git branch -D"),
    ("gp3", "xargs -n 1 git restore .", WIPE, "unscoped"),
    # (sb5) étape 4 — primaire de find, `git stash #c`, `$'…'` et expansion dans l'option de reset.
    ("sb5a", "find . $'-exec' rm -rf src {} +", RMMV, "come from a pipe"),
    ("sb5b", "find . -ex${x}ec rm -rf src {} +", RMMV, "come from a pipe"),
    ("sb5c", "find . -\\exec rm -rf src {} +", RMMV, "come from a pipe"),
    ("sb5c2", "find . -e\\xec rm -rf src {} +", RMMV, "come from a pipe"),
    ("sb5c3", 'find . "-exec" rm -rf src {} +', RMMV, "come from a pipe"),
    ("sb5d", "git stash #c", WIPE, "unscoped"),
    ("sb5e", "git stash push {x}>/dev/null", WIPE, "unscoped"),
    ("sb5f", "git reset --hard$x", WIPE, "unscoped"),
    ("sb5g", "git reset $'--hard'", WIPE, "unscoped"),
    ("sb5g2", "git reset $'\\x2d\\x2dhard'", WIPE, "unscoped"),
    ("sb5g3", "git reset $'\\U0000002d\\U0000002dhard'", WIPE, "unscoped"),
    ("sb5u", "git reset $'\\udfff-D'", WIPE, "unscoped"),
    ("sb5u2", "git branch $'\\c' wt/T-1", BRANCH, "git branch -D"),
    # (sb6) étape 7 — crédit de dry run option par option.
    ("sb6a", "git clean -n --no-dry-run -fd", WIPE, "unscoped"),
    ("sb6b", "git clean -fde -n", WIPE, "unscoped"),
    ("sb6c", "git clean -fd -e\\ -n", WIPE, "unscoped"),
    ("sb6d", "git clean -fd -e $x -n", WIPE, "unscoped"),
    ("sb6e", "git clean -f -?n", WIPE, "unscoped"),
    ("sb6f", "git clean -fd", WIPE, "unscoped"),
    ("sb6g", "git clean -fd", WIPE, "option by option"),
    # (sc1) étape 5 — l'étage 1.5 ne tombe jamais en panne : illisible, refusé ou lu.
    ("sc1a", "{a,}" * 1000 + " ; git reset --hard", BRACE, "cannot be read"),
    ("sc1b", "{a," * 1000 + "b" + "}" * 1000 + " ; git reset --hard", BRACE, "cannot be read"),
    ("sc1c", "rm -rf " + "{a,b}" * 1500, BRACE, "cannot be read"),
    ("sc1d", "echo " + "{a,b}" * 1500 + " ; git reset --hard", WIPE, "unscoped"),
    ("sc1e", "echo {1.." + "1" * 5000 + "} ; git reset --hard", WIPE, "unscoped"),
    ("sc1f", "rm -rf {1.." + "9" * 5000 + "}", BRACE, "cannot be read"),
    # Bornes rejetées AVANT calcul : plus de 256 accolades dans un mot, un nombre de plus de 9 chiffres.
    ("sc1g", "git status " + "{x}" * 300, BRACE, "cannot be read"),
    ("sc1h", "git status {1..0000000001}", BRACE, "cannot be read"),
    # Plus de 64 niveaux : la lecture S'ARRÊTE (tout est analysé), jamais un débordement de récursion.
    ("sb2i600", "echo " + '"$(' * 600 + "x" + ')"' * 600 + " ; git reset --hard", WIPE, "unscoped"),
    # (sc2) étape 4 — un demi-codet UTF-16 en ANSI-C est illisible, jamais une panne.
    ("sc2a", "echo $'\\uD800' ; git reset --hard", WIPE, "unscoped"),
    ("sc2b", "echo $'\\U0000DC80' ; git reset --hard", WIPE, "unscoped"),
    ("sc2c", "rm $'\\uD800' ; git reset --hard", WIPE, "unscoped"),
    # (sc3)(sd1) étapes 2-3 — `${…}` et `$((…))` d'un bloc ; `$'`, `$(`, backtick dedans : arrêt.
    ("sc3a", "echo \"$(echo ${y:-<<'EOF'}\ngit reset --hard\nEOF})\"", WIPE, "unscoped"),
    ("sc3b", "echo \"`echo ${y:-<<'EOF'}\ngit reset --hard\nEOF}`\"", WIPE, "unscoped"),
    ("sc3c", "echo \"$(echo ${y:-<<'EOF'}\nrm -rf src\nEOF})\"", RMMV, "checkpoint"),
    ("sc3d", "echo \"$(echo $((1<<'E'))\ngit reset --hard\nE)\"", WIPE, "unscoped"),
    ("sc3e", 'echo "$(echo ${y:-)} ; git reset --hard)"', WIPE, "unscoped"),
    ("sd1a", "echo ${x:-$'\\''} ; echo 'q' ; echo '}' ; echo 'z' ; git reset --hard ; echo 'w'", WIPE, "unscoped"),
    ("sd1b", 'echo ${x:-"$(echo "}" ; git reset --hard ; echo "a")"}', WIPE, "unscoped"),
    ("sd1c", 'echo ${x:-"`echo "}" ; git reset --hard ; echo "a"`"}', WIPE, "unscoped"),
    # (sc4)(sc5)(sd3) étape 5 — accolade ouverte avant une substitution ; enveloppes et mots réservés.
    ("sc4a", "{git,reset,--hard,$(true)}", BRACE, "cannot be read"),
    ("sc4b", "{git,reset,--hard,`true`}", BRACE, "cannot be read"),
    ("sc4c", "{rm,-rf,src,$(true)}", BRACE, "cannot be read"),
    ("sc4d", "{git,reset,--hard,$((1))}", BRACE, "cannot be read"),
    ("sc4e", "{git,reset,--hard,<(true)}", BRACE, "cannot be read"),
    ("sc4f", "{git,reset,--$(echo hard)}", BRACE, "cannot be read"),
    ("sc5a", "env " + BIG, BRACE, "cannot be read"),
    ("sc5b", "command " + BIG, BRACE, "cannot be read"),
    ("sc5c", "nice -n 5 " + BIG, BRACE, "cannot be read"),
    ("sc5d", "time " + BIG, BRACE, "cannot be read"),
    ("sc5e", "sudo -u root " + BIG, BRACE, "cannot be read"),
    ("sc5f", "exec " + BIG, BRACE, "cannot be read"),
    ("sc5g", "nohup " + BIG, BRACE, "cannot be read"),
    ("sd3a", "timeout 5 " + BIG, BRACE, "cannot be read"),
    ("sd3b", "! " + BIG, BRACE, "cannot be read"),
    ("sd3c", "then " + BIG, BRACE, "cannot be read"),
    ("sd3d", "eval " + BIG, BRACE, "cannot be read"),
    ("sd3e", "env -S x " + BIG, BRACE, "cannot be read"),
    # (sd4) étape 6 — chrt, taskset, builtin sont des enveloppes.
    ("sd4a", "chrt -i 0 rm -rf src", RMMV, "checkpoint"),
    ("sd4b", "taskset 1 rm -rf src", RMMV, "checkpoint"),
    ("sd4c", "builtin rm -rf src", RMMV, "checkpoint"),
    # (sc6)(sd2) étape 2 — une ligne `)` du corps cité : chemin d'arrêt.
    ("sc6a", "x=\"$(cat <<'EOF'\n)\"\ngit reset --hard\nEOF\n)\"", WIPE, "unscoped"),
    ("sc6b", "x=\"$(cat <<'EOF'\n  )\"\nrm -rf src\nEOF\n)\"", RMMV, "checkpoint"),
    ("sd2a", "git commit -m \"$(cat <<'EOF'\n)\"\nEOF\n)\" ; git reset --hard ; echo \"x\"", WIPE, "unscoped"),
    ("sd2b", "git commit -m \"$(cat <<'EOF'\nfix: x\n)\"\nmore\nEOF\n)\"\ngit reset --hard\necho \"y\"", WIPE,
     "unscoped"),
    # (ec) passe de correction (exec-critic) : bash APPLIQUE la suppression des guillemets au délimiteur (`$'EOF'` ->
    # EOF, `"E\$F"` -> E$F) ; ce lecteur ne la reproduit pas, donc tout délimiteur hors [A-Za-z0-9_] est illisible et
    # prend le chemin d'arrêt (oracle bash 3.2 et 5.3 : la commande d'après s'exécute).
    ("ec-t1", EC_T1.format(X="git reset --hard"), WIPE, "unscoped"),
    ("ec-t1rm", EC_T1.format(X="rm -rf src"), RMMV, "checkpoint"),
    ("ec-t1br", EC_T1.format(X="git branch -D wt/T-1"), BRANCH, "git branch -D"),
    ("ec-v1", "echo \"$(cat <<\"E\\$F\"\nx\nE$F\necho hi)\" ; git reset --hard ; echo \"\nE\\$F\n)\"", WIPE, "unscoped"),
    ("ec-v4", "echo \"$(cat <<\"E\\\\F\"\nx\nE\\F\necho hi)\" ; git reset --hard ; echo \"\nE\\\\F\n)\"", WIPE,
     "unscoped"),
    ("ec-v4rm", "echo \"$(cat <<\"E\\\\F\"\nx\nE\\F\necho hi)\" ; rm -rf src ; echo \"\nE\\\\F\n)\"", RMMV, "checkpoint"),
    # Chemin d'ARRÊT, pas une simple lecture en code : l'apostrophe du corps s'apparierait avec du code plus loin.
    ("ec-w1", "echo \"$(cat <<$'EOF'\nit's\nEOF\necho hi)\" ; git reset --hard ; echo ')\"'", WIPE, "unscoped"),
    ("ec-w3", "echo \"$(cat <<\"E\\$F\"\nit's\nE$F\necho hi)\" ; git reset --hard ; echo ')\"'", WIPE, "unscoped"),
    ("ec-t8","echo \"$(cat <<'EOF'$'x'\nx\nEOFx\necho hi)\" ; git reset --hard ; echo \"\nEOF$x\n)\"", WIPE, "unscoped"),
    ("ec-t17", "echo \"$(cat <<'EOF'\nx\nEOF\necho \"$(cat <<$'G'\ny\nG\necho z)\" ; git reset --hard ; echo \"\n$G\n)\"\n)\"",
     WIPE, "unscoped"),
    # (sc8) le `)` de `case` dans "$(…)" est NOMMÉ aux refus.
    ("sc8a", "git reset --hard", WIPE, "the `)` of a `case` pattern ends the substitution early"),
    ("sc8b", "git branch -D wt/T-1", BRANCH, "the `)` of a `case` pattern inside a quoted"),
    ("sc8b2", "rm -rf src", RMMV, "the `)` of a `case` pattern inside a quoted"),
    # (bn) T-01M5F4GJZD : la liste lue développée garde ses refus — un nom `wt/`, une accolade qui n'est ni liste
    # ni séquence dans les mots développés, un antislash ou un glob hors quotes dans le segment (PY_STRICTER).
    ("bn1", "git branch -D {feat,wt/x}", BRANCH, "git branch -D"),
    ("bn2", "git branch -D wt/{a,b}", BRANCH, "git branch -D"),
    ("bn3", "git branch -D {feat-a,feat-b} }", BRANCH, "a fail-closed false positive for a non-wt name"),
    ("bn4", "echo {a,b}; git branch -D feat }", BRANCH, "git branch -D"),
    ("bn5", "git branch -D {WT/x,y}", BRANCH, "git branch -D"),
    ("bn6", "git branch -D {a,b} \\\nwt/x", BRANCH, "a character outside a closed set"),
    ("bn7", "git branch -D {a,b} \\; wt/x", BRANCH, "a character outside a closed set"),
    ("bn8", "git branch -D {a,b} w?/x", BRANCH, "a character outside a closed set"),
    # Rév. 4 : la liste blanche `_REREAD_SAFE` juge le segment BRUT, quotes comprises. Trous fermés : bn9-bn12
    # (la marche s'arrête à `<(`/`>(` où bash continue), bn15-bn16 (antislash-retour dans des quotes).
    ("bn9", "git branch -D {a,b} <(echo) wt/x", BRANCH, "a character outside a closed set"),
    ("bn10", "git branch -D {a,b} >(cat) wt/x", BRANCH, "a character outside a closed set"),
    ("bn11", "git branch -D {1..2} <(echo) wt/x", BRANCH, "a character outside a closed set"),
    ("bn12", "git branch -D {a,b} <(echo) @{-1}", BRANCH, "a character outside a closed set"),
    # bn13 : bash refuse le `)` orphelin (rien ne tourne) ; refus fail-closed épinglé.
    ("bn13", "git branch -D {a,b} ) wt/x", BRANCH, "a character outside a closed set"),
    # bn14 : faux positif épinglé (bash supprime `a` et `b` seulement) — `(` hors de l'ensemble.
    ("bn14", "(git branch -D {a,b})", BRANCH, "a character outside a closed set"),
    ("bn15", 'git branch -D {a,b} "w\\\nt/x"', BRANCH, "a character outside a closed set"),
    ("bn16", 'git branch -D {a,b} w"\\\n"t/x', BRANCH, "git branch -D"),
    # bn17 : faux positif épinglé (comme bn14) — bash passe `w<CR>t/x` en UN argument, pas un nom `wt/` ; le CR
    # est exclu de l'ensemble, fail-closed, parce qu'il n'est pas lu comme bash le lit (réserve C4).
    ("bn17", 'git branch -D {a,b} "w\rt/x"', BRANCH, "a character outside a closed set"),
    # bn18-bn19 (NO_GO S-01M5GFV8SH) : bash 5 traverse `[ \ ] ^ _` et le backtick et relit ce qu'il émet
    # (`{V..a..6}wt/x` donne `Vwt/x wt/x`) ; l'expansion du garde n'est pas EXACTE, la coupe compte `wt/`.
    ("bn18", "git branch -D {V..a..6}wt/x", BRANCH, "reproduces bash's exactly"),
    ("bn19", "git branch -D w{V..a..6}t/x", BRANCH, "reproduces bash's exactly"),
]

# (label, command) — every one ALLOWED.
ALLOW = [
    ("sb1n", "echo $'a\\tb' ; git status"),
    ("sb1n2", "printf %s $'it\\'s' ; echo 'x'"),
    ("sbu1", "echo $'\\U00110000' ; git status"),
    ("sb2n", 'echo "$(date) # c"'),
    ("sb2n2", 'cat <<EOF\nhello "\nEOF\necho ok'),
    ("sb2n3", "git commit -m \"$(cat <<'EOF'\nfix: x\ngit reset --hard\nEOF\n)\""),
    ("sb2n4", "git commit -m \"$(cat <<'EOF'\nfix: x\nrm -rf src\nEOF\n)\""),
    ("sb2n5", 'echo "\\$(git reset --hard)"'),
    ("sb2n6", 'echo "\\`git reset --hard\\`"'),
    ("sb2n6b", 'echo "\\` git reset --hard \\`"'),
    ("sb2n7", "$X status"),
    ("sb2n8", '"$PY" -m pytest -q'),
    ("sb2n9", "$EDITOR README.md"),
    ("sb2n10", 'git commit -m "wip $(date)"'),
    ("sb2n11", 'echo "$(git status)"'),
    ("sb2n12", 'echo "$(git log -1) # x"'),
    ("sb2n13", "git commit -m \"$(cat <<-'EOF'\nfix: x\n\tEOF\n)\""),
    ("sb2n14", 'git commit -m "wip; git reset --hard $(date)"'),
    # sbP3 (Python, étage 0.5) : `$'\''` est UN segment, le `<<'EOF'` qui suit ouvre son corps — donnée.
    ("sbP3", "cat $'\\'' <<'EOF'\ngit reset --hard\nEOF"),
    ("sb3n", "echo {a,b}"),
    ("sb3n2", "ls {src,docs}"),
    ("sb3n3", "git diff --{stat,}"),
    ("sb3n4", "echo 'a {x,y} b'"),
    ("sb3n5", "echo {1..300}"),
    ("sb3n6", "cp f{,.bak}"),
    ("sb3n7", "mkdir -p a/{b,c}"),
    ("sb3n8", "{ls,-la} src"),
    ("sb3n10", 'git commit -m "a {x,y} ; git reset --hard ."'),
    ("sb4a7", "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd GIT_CONFIG_VALUE_0='branch -D'; git bd wt/T-1"),
    ("sb4n", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=cat git log"),
    ("sb4n2", "git reset --soft HEAD~1"),
    ("sb4n3", "xargs git add"),
    ("sb4n4", "xargs -n 1 git status"),
    ("sb4n5", "git reset HEAD~1"),
    ("sb4n6", "git reset --keep HEAD~1"),
    ("sb4n7", "git reset -- src/a.py"),
    ("sb4n8", 'git reset -- "$f"'),
    ("sb5n", "find . -name '*.o' -print"),
    ("sb5n2", "git stash list"),
    ("sb5n3", "git stash push -- src/a.py"),
    ("sb5n4", "git stash push -- src/x # note"),
    ("sb5n5", "find . -name '*.o' -exec grep -l x {} +"),
    ("sb5n6", "find . -name rm -print"),
    ("sb6n", "git clean -n"),
    ("sb6n2", "git clean -nd"),
    ("sb6n3", "git clean -n -e build"),
    ("sb6n4", "git clean -n -e '*.log'"),
    ("sb6n5", "git clean --dry-run -fd"),
    ("sb6n6", "git clean -fdn"),
    ("sc2n", "echo $'\\u00e9'"),
    ("sc4n", "echo {a,$(date)}"),
    ("sb3qn", "echo {a,'b'}"),
    ("sb2i600n", "echo " + '"$(' * 600 + "x" + ')"' * 600),
    ("sc4n2", "{ ls; }"),
    ("sc5n", "sudo echo {1..300}"),
    ("sd1n", "echo ${HOME:-/tmp}"),
    ("sd3n", "timeout 5 echo {1..300}"),
    ("sd4n", "chrt -i 0 ls"),
    ("sc3n", "echo \"$(( 1 <<'E' ))\ngit reset --hard\nE\""),
    # NAMED GAP, kept named: the `)` of a `case` pattern in "$(…)" closes the substitution early.
    ("sc8c", 'echo "$(case x ' + "in\nx) git reset --hard;; esac)" + '"'),
    ("gp1", "timeout 5 git reset --hard"),
    # (bn) T-01M5F4GJZD : une liste ou une séquence de noms non-wt passe, lue développée, comme sur Claude.
    ("bn1n", "git branch -D {feat-a,feat-b}"),
    ("bn2n", "git branch -D x{,}"),
    ("bn3n", "git branch -D feat{1..3}"),
    ("bn4n", "git branch -d -f {a,b}"),
    # Rév. 4 : un segment brut fait de l'ensemble fermé (redirection, commentaire, quotes) passe aussi.
    ("bn5n", "git branch -D {a,b} 2>/dev/null"),
    ("bn6n", "git branch -D {a,b} >/dev/null 2>&1"),
    ("bn7n", "git branch -D {a,b} # done"),
    ("bn8n", "git branch -D {a,b} 'x y'"),
]


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
@pytest.mark.parametrize("label,command,rule,phrase", DENY, ids=[c[0] for c in DENY])
def test_temoin_refuse(label, command, rule, phrase, host, tmp_path):
    rc, out, err, got = _run(HOOK_DIRS[host], {"tool_input": {"command": command}}, tmp_path)
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    verdict, reason = _verdict(out)
    assert verdict == "deny" and got == rule, f"expected deny rule={rule}, got {verdict} rule={got or '-'}"
    assert phrase in reason, f"{label}: the reason lacks <{phrase}>"


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
@pytest.mark.parametrize("label,command", ALLOW, ids=[c[0] for c in ALLOW])
def test_negatif_passe(label, command, host, tmp_path):
    rc, out, err, got = _run(HOOK_DIRS[host], {"tool_input": {"command": command}}, tmp_path)
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    assert _verdict(out)[0] == "allow", f"expected allow, got deny rule={got}"


# --- Le contrat ENTIER d'ansi_decode (annexe C1, safe-bash.sh:1350-1397 @05c8182b) ------------
ANSI = [
    ("simples", "\\a\\b\\e\\E\\f\\n\\r\\t\\v\\\\\\'\\\"\\?", "\a\b\x1b\x1b\f\n\r\t\v\\'\"?"),
    ("octal", "\\055D\\0101\\101", "-D\x08" + "1A"),
    ("octal-mod-256", "\\777", chr(0o777 % 256)),
    ("hex", "\\x2d\\x2dhard", "--hard"),
    ("hex-sans-chiffre", "\\xg\\u!\\U", "\\xg\\u!\\U"),
    ("u4", "\\u00e9x", "éx"),
    ("U8", "\\U0000002dD", "-D"),
    ("autre-litteral", "\\q\\z", "\\q\\z"),
    ("nul-tronque", "ab\\x00cd", "ab"),
    ("U-hors-unicode", "\\U00110000", None),
    ("demi-codet-haut", "\\ud800", None),
    ("demi-codet-bas", "\\U0000DC80", None),
    ("c", "\\cA", None),
]


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
@pytest.mark.parametrize("label,body,want", ANSI, ids=[a[0] for a in ANSI])
def test_ansi_decode_contrat(label, body, want, host):
    # The sibling is a LEAF (stdlib only): loaded from its file, never through sys.path.
    spec = importlib.util.spec_from_file_location(f"_sbg_{host}", HOOK_DIRS[host] / "safe_bash_git.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.ansi_decode(body) == want, label


# --- Le drapeau `inexact` d'expand_braces (T-01M5F4GJZD) : témoins FIXES, tirés du différentiel contre bash 5.3
# (72 648 séquences, 16 601 écarts, tous lettres traversant `[ \ ] ^ _` et le backtick, ou nombres signés `+`).
INEXACT = [
    ("lettres-traversent", "{V..a..6}", True),
    ("lettres-descendent", "{a..Z}", True),
    ("signe-plus", "{+01..3}", True),
    ("majuscules", "{A..E}", False),
    ("minuscules", "{a..e}", False),
    ("zeros-de-tete-pas", "{01..10..3}", False),
    ("signes-meles-zeros", "{-05..5..5}", False),
    ("pas-negatif", "{5..1..-2}", False),
    ("pas-nul", "{1..3..0}", False),
    ("liste", "{a,b}", False),
]


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
@pytest.mark.parametrize("label,word,want", INEXACT, ids=[i[0] for i in INEXACT])
def test_expansion_inexacte_contrat(label, word, want, host):
    spec = importlib.util.spec_from_file_location(f"_sbgi_{host}", HOOK_DIRS[host] / "safe_bash_git.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    raw, scr, unread, inexact = module.expand_braces(word, word)
    assert scr != word and not unread and inexact is want, label


# --- Bornes de temps et de panne --------------------------------------------------------------
BORNES = [
    ("brace20000", "echo " + "{" * 20000 + " ; git reset --hard", 5, "deny"),
    ("nested200", "echo " + '"$(' * 200 + "x", 30, None),
    ("word7MB", "echo " + ("{" + "a" * 30000) * 250, 20, None),
    ("seq5000", "echo {1.." + "1" * 5000 + "}", 30, None),
    ("list1500", "echo " + "{a,b}" * 1500, 30, None),
    ("ud800", "echo $'\\ud800'", 30, None),
    ("udfffD", "git branch -d $'\\udfff-D' x", 30, None),
]


@pytest.mark.parametrize("label,command,limit,want", BORNES, ids=[b[0] for b in BORNES])
def test_borne_de_temps_et_de_panne(label, command, limit, want, tmp_path):
    t0 = time.monotonic()
    rc, out, err, _rule = _run(HOOK_DIRS["codex"], {"tool_input": {"command": command}}, tmp_path,
                               timeout=limit + 30)
    elapsed = time.monotonic() - t0
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    assert elapsed < limit, f"{label}: {elapsed:.1f} s >= {limit} s"
    if want:
        assert _verdict(out)[0] == want


# --- Coût de `reread` (T-01M5F4GJZD, critic-opus S-01M5HSPQ7T) : jugé UNE fois par segment, jamais par site
# git. Témoin de COMPTE, pas de chronomètre : les appels à expand_braces ne croissent pas avec le nombre de
# sites d'un même segment (mesuré : 2/2 pour 10/40 sites ; recalculé par site : 11/41).
_PRELUDE_COMPTE = (
    "import atexit, runpy, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import safe_bash_git as g\n"
    "calls, real = [], g.expand_braces\n"
    "def counted(*a, **k):\n"
    "    calls.append(1)\n"
    "    return real(*a, **k)\n"
    "g.expand_braces = counted\n"
    "atexit.register(lambda: sys.stderr.write(f'EXPAND_BRACES_CALLS={len(calls)}\\n'))\n"
    "hook = sys.argv[2]\n"
    "sys.argv = [hook]\n"
    "runpy.run_path(hook, run_name='__main__')\n"
)


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
def test_reread_une_fois_par_segment(host, tmp_path):
    counts = []
    for sites in (10, 40):
        command = "env -S x " + "git " * sites + "branch -D {a,b}"
        rc, out, err, _rule = _run(HOOK_DIRS[host], {"tool_input": {"command": command}}, tmp_path,
                                   prelude=_PRELUDE_COMPTE)
        assert rc == 0 and "Traceback" not in err, f"{sites} sites: rc {rc} {err[-400:]}"
        assert _verdict(out)[0] == "allow", f"{sites} sites: {out[-400:]}"
        counts += [int(line.split("=", 1)[1]) for line in err.splitlines() if line.startswith("EXPAND_BRACES_CALLS=")]
    assert len(counts) == 2 and counts[0] == counts[1], f"expand_braces calls grow with git sites: {counts}"


# --- Injections : toute exception REFUSE, jamais un traceback ----------------------------------
# argv : <dossier du hook> <hook> ; le frère est patché AVANT que le hook ne l'importe.
_PRELUDE = (
    "import runpy, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import safe_bash_git as g\n"
    "def boom(*a, **k):\n"
    "    raise RuntimeError('injected')\n"
    "setattr(g, {name!r}, boom)\n"
    "hook = sys.argv[2]\n"
    "sys.argv = [hook]\n"
    "runpy.run_path(hook, run_name='__main__')\n"
)
INJECTIONS = [
    ("inj-opaque", "_opaque", "echo ${x} ; ls", QUOTE),
    ("inj-ansi", "ansi_decode", "git reset $'--hard'", WIPE),
    ("inj-ansi-branch", "ansi_decode", "git branch $'-D' wt/T-1", BRANCH),
    ("inj-brace", "_brace_expand", "{git,reset,--hard}", BRACE),
    # A2 : une exception hors des étages gardés (ici le juge git) atteint le bloc __main__ : refus explicite.
    ("inj-main", "judge_git", "git status", "guard-internal-fault"),
]


@pytest.mark.parametrize("host", sorted(HOOK_DIRS))
@pytest.mark.parametrize("label,name,command,rule", INJECTIONS, ids=[i[0] for i in INJECTIONS])
def test_injection_refuse(label, name, command, rule, host, tmp_path):
    rc, out, err, got = _run(HOOK_DIRS[host], {"tool_input": {"command": command}}, tmp_path,
                             prelude=_PRELUDE.format(name=name))
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    assert _verdict(out)[0] == "deny" and got == rule, f"expected deny rule={rule}, got rule={got or '-'}"


# --- Copilot : le MÊME fichier `.codex/hooks/safe_bash.py`, sous AGENTS_HOOK_HOST=copilot ---------
# (.github/hooks/agent-guardrails.json, jambes bash et powershell). Échantillon : au moins un
# témoin par étape 2 à 7, la forme de commit négative, un cas de panne (injection).
COPILOT_DENY = ["sb1a", "sb2d", "sbP1", "sc3e", "sb5g", "sb5d", "sb3a", "sc1c", "sb4a2", "sb4d", "sd4a", "sb6b",
                "bn3", "bn6", "bn7", "bn8", "bn9", "bn15", "bn18", "bn19"]
COPILOT_ALLOW = ["sb2n3", "sb2n4", "sb3n5", "sb6n", "sb4n3", "bn1n", "bn5n"]


def _copilot_payload(command, tool):
    if tool == "powershell":
        return {"toolName": "powershell", "toolArgs": json.dumps({"command": command})}
    return {"toolName": "bash", "toolArgs": {"command": command}}


@pytest.mark.parametrize("tool", ("bash", "powershell"))
@pytest.mark.parametrize("label", COPILOT_DENY)
def test_copilot_refus_dans_son_enveloppe(label, tool, tmp_path):
    _lab, command, rule, _phrase = next(c for c in DENY if c[0] == label)
    rc, out, err, got = _run(HOOK_DIRS["codex"], _copilot_payload(command, tool), tmp_path, host="copilot")
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    body = json.loads(out)
    assert body["permissionDecision"] == "deny" and body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert body["permissionDecisionReason"] == body["hookSpecificOutput"]["permissionDecisionReason"]
    assert got == rule, f"expected deny rule={rule}, got rule={got or '-'}"


@pytest.mark.parametrize("tool", ("bash", "powershell"))
@pytest.mark.parametrize("label", COPILOT_ALLOW)
def test_copilot_negatif_passe(label, tool, tmp_path):
    command = dict(ALLOW)[label]
    rc, out, err, _got = _run(HOOK_DIRS["codex"], _copilot_payload(command, tool), tmp_path, host="copilot")
    assert rc == 0 and "Traceback" not in err, f"{label}: rc {rc} {err[-400:]}"
    assert "deny" not in out, f"{label}: refused under copilot"


def test_copilot_panne_refuse(tmp_path):
    rc, out, err, got = _run(HOOK_DIRS["codex"], _copilot_payload("echo ${x} ; ls", "bash"), tmp_path,
                             host="copilot", prelude=_PRELUDE.format(name="_opaque"))
    assert rc == 0 and "Traceback" not in err, err[-400:]
    assert json.loads(out)["permissionDecision"] == "deny" and got == QUOTE
