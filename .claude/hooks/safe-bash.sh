#!/usr/bin/env bash
# PreToolUse [Bash] — des gardes NUMÉROTÉES ci-dessous et des motifs DISTINCTS,
# un par règle de refus (la liste se relève par grep des `deny <règle>` et du
# `rule=` de redirect_stage_down ; jamais close par un chiffre, L-00000187 — le
# « SIX gardes, SIX motifs » d'origine était périmé), UN SEUL étage de
# reconnaissance (plus la passe PAR OPÉRANDE de la garde 1b, jouée seulement
# quand l'étage 2 a reconnu un rm/mv). Le motif n'est pas décoratif : c'est lui
# qui décide où la garde mord, et le message qui le porte est la seule chose que
# l'agent bloqué apprenne. Ils restent donc séparés, jamais fondus en « commande
# dangereuse ».
#
#   1. `rm` / `mv` sur TOUT CE QUI N'EST PAS UN RÉPERTOIRE JETABLE — bloqué
#      parce qu'il CASSE LE REWIND des checkpoints : l'opération n'est pas
#      rejouable en arrière. Remède : Edit/Write.
#      LE PÉRIMÈTRE EST LA LISTE BLANCHE ANCRÉE ; LE SUIVI GIT N'ÉLARGIT JAMAIS,
#      IL AJOUTE UN VETO DEDANS ; OPÉRANDE NON VIDE, NON NOURRI PAR UN TUBE
#      (T-00000762, 2026-09-25). CHAQUE opérande est jugé, et un seul refusé
#      refuse la commande : un chemin ABSOLU doit être STRICTEMENT sous `/tmp/`
#      tel qu'écrit ET une fois résolu (l'ancre résolue — `/private/tmp/` sur
#      macOS — est CALCULÉE, jamais codée en dur) ; un chemin RELATIF doit
#      ouvrir sur `.tmp`, `node_modules`, `dist`, `build` ou `.cache` (premier
#      composant, tel qu'écrit ET résolu contre la RACINE du projet — jamais
#      contre un `cd` de la même commande), et git ne doit y suivre aucun
#      fichier. Tout le reste est refusé — un brouillon NON SUIVI hors de ces
#      répertoires compris. Sont refusés aussi, par construction : un verbe
#      SANS opérande (`rm` nu), un verbe nourri par un tube (`xargs`,
#      `parallel`, `find -exec|-ok`) quel que soit son opérande statique — y
#      compris derrière une enveloppe à arguments (`nice -n 10 xargs rm …`), à
#      travers une substitution de processus (`xargs -a <(…) rm …`) ou une
#      redirection en tête (`< liste xargs rm …`) —, un opérande DISSOUS
#      (jugé par son seul préfixe littéral : `/tmp/$X` s'arrête à `/tmp/`).
#      PASSE BINÔME (T-00000762) : la destination COLLÉE de `mv` (`-tDIR`,
#      `--target-directory=DIR`) est un opérande ; le veto de suivi est
#      INSENSIBLE À LA CASSE (`:(icase)`, APFS/NTFS) ; la tranche d'un verbe
#      s'arrête à un `)` non imbriqué et à un ` #` de commentaire, jamais à un
#      `}` ni à un caractère échappé ; une cible de redirection ou une
#      expansion ne prend plus la place de la commande (`< f rm x`, `sudo $X
#      rm x` passaient sur les trois hôtes).
#      POURQUOI CE N'EST PLUS UNE SOUS-CHAÎNE : l'ancienne liste cherchait
#      `/tmp/`, `.tmp/`, `node_modules`, `dist/`, `build/`, `.cache` N'IMPORTE
#      OÙ dans la commande, donc `rm README.md /tmp/x` passait sur la seule foi
#      de `/tmp/x`, et `rm docs/build/x.md` sur celle de `build/` — rc 0
#      mesurés par le dev de T-00000738.
#      CE PARAGRAPHE NE DOIT JAMAIS RÉTRÉCIR LA RÈGLE. Il a longtemps dit « sur
#      un fichier suivi », ce qui est PLUS ÉTROIT que ce que la garde fait : le
#      suivi git n'est qu'un veto DANS la liste, jamais le périmètre. Ce n'est
#      pas un débordement, c'est le dessein : le jumeau
#      `.codex/hooks/safe_bash.py` l'écrit « a tracked OR SOURCE path », et
#      `test_safe_bash_receiver_is_complete_for_every_envelope_and_keyword`
#      épingle `rm -rf src/x` — un chemin NI suivi NI existant — comme devant
#      être REFUSÉ, « la seule direction dans laquelle cette garde ne doit
#      jamais bouger ». Corrigé le 2026-09-14 après qu'un agent eut lu cette
#      ligne comme le périmètre complet, conclu à une divergence code/doc, et
#      commencé à ÉLARGIR la garde pour l'y conformer : 45 arms rouges ont
#      arrêté la manœuvre. Un résumé plus étroit que la règle coûte donc dans
#      les deux sens — il fait chercher au mauvais endroit, et il invite à
#      « réparer » ce qui n'est pas cassé.
#   2. `rg` ABSENT du PATH — bloqué parce qu'il FABRIQUE DE FAUSSES
#      AFFIRMATIONS D'ABSENCE : son échec est indiscernable d'un résultat vide.
#      Remède : l'outil Grep, qui échoue bruyamment.
#   3. Effacement git NON SCOPÉ — `git restore|checkout .`, `git clean`, et
#      depuis T-00000762 `git reset --hard` et `git stash` sans pathspec —
#      bloqué parce qu'il DÉTRUIT DU TRAVAIL non commité, celui de TOUS les
#      agents : une édition jamais indexée ne laisse AUCUN objet git et rien au
#      reflog, et un stash part dans la pile PARTAGÉE par toutes les sessions,
#      où le `pop`/`drop`/`clear` d'une autre le prend. Remède, dit PAR
#      SOUS-COMMANDE et toujours possible : un pathspec précis, `git reset
#      --keep`, `git clean -n` (un dry run, qui passe), ou committer d'abord.
#      PASSE BINÔME (T-00000762) : toute abréviation d'option longue compte
#      (`reset --h` efface déjà, mesuré git 2.55) ; un pathspec LARGE ne scope
#      rien — `.`, `*`, `:/`, `:(top)`, `./.`, une exclusion seule, une liste
#      lue sur l'entrée standard, une expansion NON citée — et un pathspec
#      CITÉ est lu dans la charge brute ; une expansion non citée là où git lit
#      sa SOUS-COMMANDE (`git $sub .`) est refusée fail-closed (règle
#      git-subcommand-hidden) ; une option ou une sous-commande CITÉE n'est pas
#      lue (DIVERGENCE 7, nommée par décision) — SAUF, depuis T-01M5D6XS2S
#      (3e passe), une option de `reset` et le mot de commande, lus guillemets
#      retirés quand chaque morceau est lisible (`git reset '--hard'`, `"rm"`).
#   4. ÉCRITURE shell par REDIRECTION vers un fichier suivi ou protégé — voir
#      l'étage redirection plus bas (T-00000244).
#   5. `git … --output[=<f>]` (T-00000762) — bloqué parce qu'il ÉCRIT UN
#      FICHIER, suivi compris, en contournant Edit/Write et leurs gardes :
#      `git show --output=f HEAD` a écrasé un fichier SUIVI (mesuré). Refusé
#      quelle que soit la sous-commande et où que pointe la cible. Remède :
#      `git log … > /tmp/x`, que la garde 4 JUGE.
#   6. `git grep -O` / `--open-files-in-pager` (T-00000762) — bloqué parce
#      qu'il EXÉCUTE UNE COMMANDE ARBITRAIRE (la valeur de l'option, ou le
#      pager de l'environnement) sur les fichiers trouvés. Remède : `git grep`
#      sans pager, puis l'outil Read.
#   7. `git branch -D` (ou `-d --force`) sur une branche `wt/…` (T-00001090) —
#      bloqué parce qu il DÉTRUIT les commits que seule cette branche porte :
#      le travail non fusionné d un dev en worktree. Remède : `git branch -d
#      wt/<T>` après la fusion (git refuse une branche non fusionnée, et un
#      refus de `-d` se rapporte, jamais ne se force). Le MÉCANISME est décrit
#      au message du refus (garde 7), seule référence : les mots de `branch`
#      sont lus jusqu à la fin de la commande ou jusqu à la première coupe
#      (substitution, accolade hors guillemets et hors `${…}` qui n est ni
#      liste ni séquence — celles-ci sont DÉVELOPPÉES d abord, étage 1.5,
#      T-01M5D6XS2S, mais leur coupe telle qu écrite compte encore `wt/` quand
#      le segment de commande, guillemets compris, porte un caractère hors
#      d un jeu fermé ou une séquence que la garde ne développe pas comme bash,
#      T-01M5GFV9CE ; faux positifs nommés : `(git branch -D {a,b})`,
#      `{a,b} x[1]`, `"w<TAB>t/x"`), casse repliée,
#      antislash retiré ; ce qu il compte `wt/` (fail-closed) et ce qu il ne
#      lit pas y sont nommés. Non couverts, NOMMÉS au message entre autres —
#      liste bornée, non close : `branch -M|-C … wt/x`, `branch -f wt/x`,
#      `update-ref -d`, `push . :wt/x`, une option écrite APRÈS une
#      substitution, `checkout -B`/`switch -C wt/…`, `env -S '…'`/`env -v`,
#      une enveloppe hors table (`timeout 5`, `nice -n 5`), une commande portée
#      par une chaîne citée (`bash -c "…"`), `xargs` derrière une enveloppe
#      hors tables (trou S1, T-00001200 ; `xargs` EN TÊTE est lu depuis
#      T-01M5D6XS2S), la lecture de l option de
#      suppression (T-00001202) et la continuation antislash-retour à la ligne
#      (T-00001198). Garde 3 : une liste ou une séquence d accolades est
#      développée puis lue (`git reset {--hard,}`, `git {reset,--hard}`,
#      T-01M5D6XS2S) ; au-delà de sa borne, règle brace-expansion-unread.
#   8. Accolade ILLISIBLE (T-01M5D6XS2S) — un développement au-delà de 256 mots
#      par mot ou 1024 par commande, ou un mot d accolade qui porte un segment
#      cité, dans une commande qui nomme git, rm, find ou xargs ou au mot de
#      commande : refusé (règle brace-expansion-unread), voir l étage 1.5.
#
# PROVENANCE (fusion, T-00000088). Les gardes 2 et 3 sont RAPATRIÉES d'un projet
# consommateur, où elles ont été écrites sur mesure le 2026-08-06 (leur ledger :
# L-00000206 pour `rg`, L-00000220 pour la restauration git — identifiants de LEUR
# store, volontairement absents des messages runtime : un consommateur frais n'a
# pas ces entrées). Elles y matchaient sur la charge utile BRUTE ; ici elles
# reposent sur l'étage 1 + l'étage 2 ci-dessous, strictement meilleurs : chez eux
# `git commit -m "wip; rg motif"` et `git commit -m "git restore . efface tout"`
# étaient REFUSÉS — un métacaractère à l'intérieur des guillemets fabriquait une
# fausse position de commande. La mention citée est de la DONNÉE.
#
# LE DÉFAUT CORRIGÉ (T-00000146, mesuré en session le 2026-08-06). Ce garde
# matchait par SOUS-CHAÎNE : il pliait TOUT en espaces — guillemets compris —
# puis cherchait " rm " / " mv ". Une écriture de mémoire institutionnelle dont
# le TEXTE, entre guillemets, DÉCRIVAIT une suppression récursive a donc été
# refusée : aucune suppression n'était exécutée. C'est le TROISIÈME garde du kit
# à porter cette erreur (`.agents/bin/post-task-done-index.sh` l. 36-44, puis
# `audit-gate.sh`), et le correctif est le même, dans le même ordre :
#   1. les segments ENTRE GUILLEMETS (simples ou doubles) sont neutralisés AVANT
#      toute reconnaissance : une commande citée dans un titre de tâche, un
#      message de commit ou une entrée de ledger est une DONNÉE, pas une
#      exécution ;
#   2. ce qui reste est lu en POSITION DE COMMANDE — début de ligne, après un
#      séparateur shell, après un mot-clé, après une enveloppe qui prend une
#      commande en argument — jamais en sous-chaîne. `git rm x` et
#      `grep rm f` ne sont pas des `rm`.
# Aucun `eval`, aucun `xargs` : la charge utile n'est jamais rendue à un shell.
# Un scanner python la neutralise (sur STDIN, jamais en argv), awk la lit — ni
# l'un ni l'autre n'interprète les guillemets ou les métacaractères qu'elle
# contient.
#
# LE CONTOURNEMENT DE CLASSE 1 FERMÉ (T-00000181). L'étage 1 était un sed en une
# passe, `s/'[^']*'|"[^"]*"/ @@ /g`, AVEUGLE À L'ÉCHAPPEMENT : il lisait un
# guillemet précédé d'un `\` comme un délimiteur ouvrant. Or bash le rend
# LITTÉRAL, donc dans `echo \" ; rm -rf src/x \"` le sed voyait un seul segment
# cité couvrant tout l'intervalle — le séparateur ET la commande destructrice —
# l'étage 2 ne coupait rien, et le rm partait sans un mot. Le sed a été remplacé
# par le PORT du scanner conscient de l'échappement des hôtes python
# (`quoted_spans()`, .codex/hooks/safe_bash.py l. 124-180). Le contrat de sortie
# ne bouge pas — un segment cité devient toujours ` @@ ` — donc l'étage 2 est
# inchangé, à la ligne près.
#
# CE QUI NE DOIT PAS S'AFFAIBLIR. Le garde rm/mv protège le rewind des
# checkpoints : son faux négatif coûte cher, bien plus que son faux positif. La
# position de commande est donc TRANSPARENTE (a) aux séparateurs sous toutes
# leurs formes (`&&`, `;`, `|`, `(`, `$(`, backtick, retour à la ligne,
# tabulation), (b) aux enveloppes qui exécutent une commande (`sudo`, `env`,
# `xargs`, `timeout`, `find -exec`…), (c) aux mots-clés (`do`, `then`…), (d) aux
# affectations qui précèdent un verbe (`FOO=bar rm x`) et (e) au chemin ou à
# l'échappement du verbe (`/bin/rm`, `rm.exe`, `\rm`) — tous strictement PLUS
# larges que l'ancienne reconnaissance par sous-chaîne. Les 29 cas d'origine
# restent verts dans safe-bash.test.sh, qui pin aussi ces formes-là et les deux
# trous assumés (verbe ou charge utile CITÉS : `bash -c "rm x"`, `"rm" x`).
#
# UNE PARTIE DE L'ÉTAT DE SHELL HÉRITÉ EST RÉTABLIE AVANT TOUTE COMMANDE
# (T-00000784, passes 2 et 3). Le hook est lancé par
# `bash "<racine>/.claude/hooks/safe-bash.sh"` (.claude/settings.json) : un bash
# NON interactif, qui source `$BASH_ENV` et importe `SHELLOPTS` AVANT la
# première ligne de ce fichier. Mesuré sur e69aa011 : un `set -e` venu de l'un
# ou de l'autre faisait sortir le hook avec le code du juge planté (9) — ni 0 ni
# 2, donc une erreur NON bloquante, commande exécutée sans un mot ; un
# `trap "exit 0" EXIT` venu de BASH_ENV réécrivait TOUT refus en rc 0, et un
# `trap "exit 0" ERR` le plantage de l'étage redirection. Ce fichier est écrit
# pour les options PAR DÉFAUT et ne pose aucun trap : les trois lignes
# ci-dessous rétablissent errexit, nounset, pipefail et les traps ERR et EXIT —
# CELA SEUL (pour nounset et pipefail aucune casse mesurée : la remise à zéro
# suit la même règle, elle ne corrige rien de vu). DEUX DÉFENSES, ORDONNÉES :
# celle-ci d'abord ; puis chaque capture de statut d'un étage en liste AND-OR
# (`X=$(…) || X_RC=$?`), qu'aucun errexit ne coupe — et dont le `$?` n'est le
# code du juge que si rien d'autre n'a fait sortir la substitution, ce que la
# présente remise à zéro garantit. BORNE, dite, et elle est LARGE (passe 3,
# exec-critic) : ce qui agit AVANT la première ligne, ou qu'aucune ligne de ce
# fichier n'atteint, n'est PAS rétabli — un trap DEBUG posé par BASH_ENV (il
# s'exécute avant chaque commande, remise à zéro comprise), `SHELLOPTS=noexec`
# (bash lit le fichier sans rien exécuter : sortie 0, rien de jugé),
# `SHELLOPTS=onecmd` (bash exécute UNE commande puis sort 0 — mesuré sur
# 33761009 : `echo x > AGENTS.md` rc 0, 0 octet ; F4 du binôme de clôture), une
# FONCTION exportée ou définie par BASH_ENV qui masquerait `exit` ou `printf`,
# un builtin désactivé par `enable -n`, et les variables que git lit
# (`GIT_DIR`, `GIT_INDEX_FILE` — mesuré sur a342b9bd : `echo x > AGENTS.md`
# passe rc 0). Ces vecteurs ne se ferment que depuis l'INVOCATION, hors de ce
# fichier : T-00000801.
set +e +u
set +o pipefail
trap - ERR EXIT
INPUT=$(cat)
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

# --- Étage 0 : la charge utile est-elle LISIBLE ? ----------------------------
# T-00000140, même doctrine que `audit-gate.sh`. La charge utile PreToolUse est
# du JSON : sans interpréteur pour la lire, ce garde ne voit RIEN. Il ne doit
# pas bloquer (un garde absent qui bloque fait boucler l'hôte) — mais il ne doit
# pas non plus se taire : un garde qui disparaît sans le dire se lit comme un
# garde qui a vérifié. Format aligné sur `gitleaks-scan.sh` /
# `semgrep-scan.sh` (« COVERAGE DEGRADED: … »), doublé d'un `systemMessage` sur
# stdout — précédent `post-edit-check.sh` l. 18 : c'est la seule surface qu'un
# humain voit vraiment sur un hook qui sort 0. Exit 0 impératif sur ce chemin.
degraded() { # degraded <why> — le dire, ne jamais bloquer.
  echo "COVERAGE DEGRADED: safe-bash — $1; rm/mv, rg-absent, unscoped git wipe, git --output, git grep pager, git hooks bypass and redirect-write are NOT guarded for this call." >&2
  # `%s` reçoit un littéral défini ICI (jamais la charge utile) : aucun
  # guillemet ne peut s'y glisser et casser le JSON.
  printf '{"systemMessage": "COVERAGE DEGRADED: safe-bash (rm/mv checkpoint, rg-absent, unscoped git wipe, git --output, git grep pager, git hooks bypass, redirect-write) — %s. Bash commands are NOT guarded for this call."}' "$1"
  exit 0
}
# --- Étage redirection PLANTÉ, python PRÉSENT : REFUS (T-00000784) -----------
# LA SEULE EXCEPTION À LA POSTURE DÉGRADÉE CI-DESSUS, décidée par le pilote
# (S-00002848, rectifiée S-00002849). Sous degraded(), un juge de redirection
# qui plante laissait passer toute écriture `>` vers un fichier suivi ou
# protégé — un marqueur d'armement compris — sans que rien ne la juge : le
# fail-open même que la garde 4 existe pour fermer. La commande qui fait
# planter le juge est REFUSÉE ; et tant que la panne tient au hook ou à son
# environnement (une panne DURABLE), TOUTE commande portant un `>` hors
# guillemets et hors corps de heredoc à délimiteur cité l'est aussi, `2>&1`
# compris (coût accepté). Une exception propre à UNE cible pathologique ne
# refuse que sa commande — le message le dit (passe 4 : la boucle de liens
# sous CPython <= 3.12, qui la produisait, est désormais attrapée par
# normalize(), (z26)) ;
# une commande sans `>` n'ouvre pas l'étage et passe, ce qui laisse le remède
# tapable (les cinq lignes `  $ `, rejouées sous la cale par (z9) du morceau
# safe-bash-em-z.test.sh). L'ABSENCE de python reste degraded() : sans interpréteur
# aucune garde ne lit rien, et un refus universel ferait boucler l'hôte. Aucun
# `COVERAGE DEGRADED` ici — c'est un refus, pas une dégradation (précédent
# 119f81e5 ; la matrice de parité lève sur ce mot). Seule la PHRASE DE CAUSE
# ($1) diffère d'une branche à l'autre. Les verbes `cadre` y sont RÉSERVÉS,
# jamais cités comme une commande livrée (S-00002849), et sans numéro de
# phase. L'interpréteur de la sonde est `$PY` DÉVELOPPÉ, celui que l'étage a
# réellement lancé. L'appel emit DUPLIQUE celui de deny() (même forme, même
# `|| true`) plutôt que de hisser deny() au-dessus de l'étage : aucun gain.
redirect_stage_down() { # redirect_stage_down <why> — refus, exit 2.
  RSB_PROBE='import os, re, sys, subprocess, posixpath; from pathlib import Path; print("stdlib ok")'
  {
    printf 'BLOCKED: safe-bash — the redirect stage crashed: %s.\n' "$1"
    printf '%s\n' 'This command is refused (rule redirect-stage-broken). If the crash comes from the hook or its environment rather than from the target of this command, EVERY command carrying a > outside quotes and outside a quoted-delimiter heredoc body is refused until it is repaired, descriptor duplication like 2>&1 included: a crashed judge cannot tell a write to a tracked or protected file from a harmless one, so it refuses rather than guesses. A command with no such > still runs, and so does every line below.'
    printf '%s\n' 'The Python traceback printed above, if any, is the cause; none → run the probe below.'
    printf '%s\n' 'KIT TEAM (a clone of this repository) — diagnose, then repair, in this order:'
    printf '%s\n' '  $ git diff --stat HEAD -- .claude/hooks/safe-bash.sh .claude/hooks/protect-paths.sh'
    printf '%s\n' '    a local edit of the stage or of the sibling it reads is the usual cause; restore both from HEAD:'
    printf '%s\n' '  $ git checkout HEAD -- .claude/hooks/safe-bash.sh'
    printf '%s\n' '  $ git checkout HEAD -- .claude/hooks/protect-paths.sh'
    printf '%s\n' '  $ git ls-files --error-unmatch .claude/hooks/safe-bash.sh'
    printf '%s\n' '    it fails → this copy of the hook is not tracked here, so git has nothing to restore it from: no tooled remedy, report it to the pilot.'
    printf "  \$ \"%s\" -c '%s'\n" "$PY" "$RSB_PROBE"
    printf '%s\n' '    anything but the single line "stdlib ok" → a stray *.py in the working directory or on PYTHONPATH shadows the standard library (a loud ImportError, a silent exit 0, or extra lines printed at import): `git status --short` names an untracked one; removing it is a pilot decision.'
    printf '%s\n' 'ADOPTING PROJECT (kit installed with uv): once shipped, reinstalling the core by the pinned-source command of the kit README, § Install the core (glass-dist; distribution `cadre-kit`) restores the hook logic; a locally modified shim is flagged by `cadre doctor` and regenerated by `cadre init --upgrade` — `cadre init`, `cadre hook`, `cadre doctor` are RESERVED, not shipped; today the `git checkout` path above is the only actionable remedy.'
  } >&2
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=safe-bash rule=redirect-stage-broken "cmd_sha256=$CMD_SHA256" "cmd_len:=$CMD_LEN" >/dev/null 2>&1 || true
  exit 2
}
if [ -z "$PY" ]; then
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  degraded "no python on PATH to read the PreToolUse payload"
fi
CMD=$(printf '%s' "$INPUT" | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(d.get('tool_input',{}).get('command',''))" 2>/dev/null) \
  || degraded "the PreToolUse payload is not readable JSON"
# Charge utile LUE et commande vide : rien à garder, et ce n'est pas une
# dégradation — ne pas confondre les deux (le silence est correct ici).
[ -n "$CMD" ] || exit 0

# Non-reversible fingerprint for the audit trail ONLY — $CMD (the whole,
# model-controlled shell command, e.g. containing `curl -H "Authorization:
# Bearer <token>"`) must NEVER reach events.py, not even truncated: gitleaks
# scans Edit/Write content and the working-tree diff, never a hook's own
# JSONL append, so a leaked credential in $CMD would land unredacted in a
# file this design intends to become tracked (security-code-review finding,
# T-00000018). Hash+length let the audit trail correlate/de-duplicate
# denials of the SAME command without ever carrying the payload.
CMD_LEN=${#CMD}
# Deliberately UNSALTED (independent review, T-00000018 addendum, do not
# change): this makes cmd_sha256 a stable cross-session correlation key —
# the same denied command hashes to the same value every time, which is
# exactly the de-dup property the audit trail wants. Tradeoff, noted rather
# than hidden: an unsalted hash also lets a party who ALREADY knows (or
# guesses) a candidate whole command confirm a match against this trail.
# Rated low practical risk (the guard only fires on already-suspicious
# rm/mv/rm-rf commands, not on arbitrary secret-bearing text) and accepted.
CMD_SHA256=$(printf '%s' "$CMD" | "$PY" -c "import sys,hashlib;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())" 2>/dev/null)

# --- Étage 0.5 : un CORPS DE HEREDOC est de la DONNÉE, pas du code ------------
# Mesuré le 2026-08-06, sur cette garde et pour la TROISIÈME fois : un message de
# commit passé en heredoc a été REFUSÉ parce qu il DÉCRIVAIT une commande gardée,
# ses métacaractères fabriquant au passage de fausses frontières de segment.
# L étage 1 ne pouvait rien y faire : un corps de heredoc n est pas CITÉ, il est
# REDIRIGÉ. Son contenu part sur l entrée standard d une commande et n est jamais
# exécuté. Le consommateur avait déjà cet étage et le nommait ainsi ; c est donc
# une redescente.
#
# LA DISTINCTION QUE LE CONSOMMATEUR NE FAIT PAS, ET QUI EST UNE FAILLE CHEZ LUI :
# seul un délimiteur CITÉ (`<<'FIN'`, `<<"FIN"`, et depuis T-00000210 `<<\FIN`,
# `<<F"I"N`, `<<'F'IN` — toute forme portant AU MOINS une pièce citée, cf. (c))
# rend le corps littéral. Avec un
# délimiteur NU (`<<FIN`), le shell y développe paramètres ET SUBSTITUTIONS DE
# COMMANDE — un `$(…)` dans ce corps s exécute vraiment. Retirer les deux serait
# donc FAIL-OPEN. On ne retire que les corps à délimiteur cité ; les autres
# continuent d être analysés.
#
# ANTI-FAIL-OPEN N°2 : un `<<'FIN'` qui apparaît DANS un segment cité (le cas de
# l incident lui-même, où le texte parle de heredocs) n ouvre aucun corps. Le test
# est direct et n exige pas de masque : si la ligne, une fois ses citations
# neutralisées, ne montre plus de `<<`, alors ce `<<` était cité. Sans ce garde-fou
# un simple message mentionnant un heredoc effacerait les commandes suivantes.
# LA RÈGLE DE CONCEPTION DE CET ÉTAGE, ÉCRITE AVANT SES CLAUSES (T-00000187) :
# ON COUPE PLUS QUE BASH, JAMAIS MOINS — TOUTE RECONNAISSANCE INCOMPLÈTE DOIT
# DÉGRADER VERS TEXTE ANALYSÉ, JAMAIS VERS EFFACEMENT.
# L'étage n'a qu'une primitive dangereuse, le BLANCHIMENT, donc son erreur
# admissible est unique : garder du texte que bash aurait traité en donnée (au
# pire un faux positif aux étages 1-2), jamais effacer du texte que bash exécute
# (fail-open). Chaque clause ci-dessous DIT de quel côté elle tombe quand elle se
# trompe, et TOUTE CLAUSE FUTURE SE JUGE AU MÊME CRITÈRE. C'est la réponse à la
# dérive qui a produit le défaut : on ne réimporte pas le lexer de bash clause
# par clause — chaque rustine fermait le dernier contre-exemple en élargissant
# d'un cran la définition d'un mot, et recréait le même effacement à la frontière
# suivante. On borne l'erreur de chaque clause du côté sûr, une fois.
#
# CE QUE T-00000187 A FERMÉ. L'awk précédent faisait deux gsub naïfs
# (`'[^']*'` puis `"[^"]*"`) AVEUGLES À L'ÉCHAPPEMENT, puis cherchait le `<<` PAR
# SOUS-CHAÎNE avec un `match()` FLOTTANT sur la ligne brute. CINQ formes d'une
# seule faute, toutes fail-open, toutes fermées ici et chacune pinnée par un arm
# de la section (o) : guillemet ÉCHAPPÉ apparié avec un vrai ouvrant (o1) ;
# guillemet NON APPARIÉ enjambant le retour à la ligne (o5) ; `match()` au plus à
# gauche prenant le délimiteur d'une mention citée (o4) ; `<<` reconnu en
# sous-chaîne là où bash n'en voit aucun — `\<` (o7), commentaire (o8)(o8b) ;
# HERESTRING `<<<` lu comme un heredoc à l'offset+1 (o9).
#
# CE QUE LA REVUE DE SÉCURITÉ A ENSUITE FERMÉ, et la leçon vaut plus que les deux
# correctifs : la règle de conception ci-dessus était ÉCRITE mais pas TENUE PAR LE
# CODE sur deux frontières que l'énumération ne nommait pas — et les deux
# tombaient du côté interdit, l'EFFACEMENT. Une énumération existe précisément
# pour empêcher cela, donc elle les nomme désormais (section (p) des tests) :
#   - LIGNE PHYSIQUE contre LIGNE LOGIQUE : le corps s'ouvrait après la ligne
#     physique suivante, alors que bash l'ouvre après la ligne LOGIQUE. Fermé
#     par (b') élargie — quatre formes de prolongement (p1)-(p4).
#   - PRÉFIXE DE DÉLIMITEUR : la RE matchait sans exiger de frontière de mot,
#     capturait un délimiteur plus court que celui de bash et sur-blanchissait
#     jusqu'à la fin. Fermé par la frontière de mot en (c) — (p5).
#   - ET LA MÊME ERREUR UNE COUCHE PLUS BAS, à la re-revue : le correctif du
#     premier point était lui-même une ÉNUMÉRATION (trois constructions) sous un
#     titre universel. Quatre formes de plus passaient — `${x:-`, `$[1`, `(( 1`,
#     `<(echo` — toutes fail-open. Fermé par le PRÉDICAT CLOS de (b'), section
#     (q) des tests. La leçon est celle de la règle de conception, et elle vaut
#     plus que les trois correctifs : une énumération sous un titre universel est
#     un mensonge à retardement ; là où l'on ne peut pas énumérer, on borne.
#
# LES CLAUSES, chacune avec SON CÔTÉ D'ERREUR. Le scanner fait UNE passe par
# ligne, de gauche à droite, en tenant l'état échappement/citation :
#   (a) spans cités conscients de l'échappement — nombre impair de `\` = guillemet
#       LITTÉRAL, l'ouvrant le plus à gauche gagne, un non apparié n'ouvre aucun
#       span. En erreur : texte non neutralisé -> ANALYSÉ.
#   (b) le `<<` est détecté PAR L'AUTOMATE, jamais par sous-chaîne : un `<`
#       précédé d'un `\` actif ne forme JAMAIS `<<`, et un `<<` situé dans un span
#       est une mention citée, donc de la DONNÉE. En erreur : pas de candidat
#       -> ANALYSÉ.
#   (b') LA LIGNE PHYSIQUE DOIT SE TERMINER DANS UN ÉTAT NEUTRE, sinon aucun
#       corps n'ouvre. Bash ouvre le corps après la ligne LOGIQUE, pas après la
#       ligne physique : tout ce qui prolonge la commande décale le début du
#       corps, et l'étage blanchirait l'intervalle.
#       CE PRÉDICAT EST CLOS, ET C'EST LA SEULE FORME ACCEPTABLE ICI. Il l'est
#       devenu en deux temps, et le premier était FAUX : la version d'avant
#       ÉNUMÉRAIT trois constructions de prolongement (`\` final, `$(`, backtick)
#       sous un titre qui promettait l'universel — bash en a au moins sept, et
#       quatre passaient (`${x:-`, `$[1`, `(( 1`, `<(echo`), toutes fail-open
#       mesurées. Ce n'est pas une clause qui manquait, c'est la FORME de la
#       clause qui était mauvaise ; `plan-critic` l'avait nommé à son itération 3.
#       L'état non neutre est donc décidé par des invariants GÉNÉRIQUES, tenus
#       hors des spans cités et après traitement de l'échappement :
#         - un guillemet ouvrant NON APPARIÉ n'importe où sur la ligne
#           (`loose >= 0`, AVANT comme APRÈS le `<<`) ;
#         - un `\` final non échappé ;
#         - un backtick non refermé (parité) ;
#         - `()`, `[]` ou `{}` DÉSÉQUILIBRÉS — trois compteurs, plancher à 0,
#           qui attrapent d'un coup `$(`, `${`, `$[`, `((`, `<(`, `>(` et toute
#           construction future bâtie sur ces trois paires, sans qu'aucune ait à
#           être nommée.
#       Sur-refuser sur un déséquilibre ne coûte qu'ANALYSÉ, donc l'erreur est
#       bornée du côté sûr UNE FOIS, pas construction par construction. Trois
#       groupes, mesurés, et il faut les distinguer sous peine d'affirmer plus
#       que le code ne tient :
#         - NE prolongent pas ET ne sont pas refusés : `&&`, `||`, `|`, `if`,
#           `for`, `case` en fin de ligne, ainsi qu'un `(` de sous-shell ou un
#           `{` de groupe REFERMÉS — le corps démarre bien à la ligne suivante.
#         - NE prolongent pas MAIS SONT refusés : un `(` ou un `{` laissés
#           OUVERTS en fin de ligne. Le compteur ne distingue pas le groupe de
#           l'expansion, donc il sur-refuse ici. C'est le prix ASSUMÉ de la
#           clôture du prédicat, et il se paie en ANALYSÉ — jamais en effacement.
#         - Ne prolongent rien parce que rien ne s'exécute : `a=(1`, `[[ x` sont
#           des erreurs de syntaxe bash, donc aucune commande à cacher.
#       En erreur -> ANALYSÉ.
#   (b'') un `#` NON CITÉ, non échappé, en DÉBUT DE MOT coupe la ligne — début de
#       mot = précédé d'un blanc, du début de ligne, OU d'un séparateur non cité
#       (`;`, `&`, `|`, `(`, `)`, backtick) ; JAMAIS après `$` ni `{`, sinon `$#`
#       et `${#v}` cesseraient d'être des expansions — et bash n'y lit pas non
#       plus un commentaire, donc l'exception ne recrée aucun fail-open. Une
#       coupe ne peut jamais OUVRIR un corps, donc jamais effacer : couper trop
#       large perd un candidat -> ANALYSÉ. Clause fail-safe par construction.
#   (c) à l'offset du PREMIER candidat de l'automate — JAMAIS de retry sur un
#       candidat suivant, un retry rouvrirait le trou herestring — un PARSEUR DE
#       PIÈCES CLOS lit le mot délimiteur, ANCRÉ là (T-00000210).
#       BASH CONSTRUIT CE MOT PAR CONCATÉNATION DE PIÈCES, PUIS RETIRE LES
#       QUOTES : `<<'A'B` a pour délimiteur `AB`, `<<\EOF` et `<<E"O"F` ont pour
#       délimiteur `EOF`. Les pièces admises sont ÉNUMÉRÉES ET FERMÉES — `'X'`,
#       `"X"`, `\c`, ou une suite NUE — et le contenu de chacune est borné au jeu
#       `[A-Za-z0-9_]` ; le délimiteur est leur concaténation après retrait des
#       quotes.
#       LE CORPS N'EST BLANCHI QUE SI AU MOINS UNE PIÈCE EST CITÉE, et c'est la
#       clause qui porte la polarité de tout l'étage : un délimiteur entièrement
#       NU laisse son corps ANALYSÉ, parce que bash y développe `$(…)` et que le
#       blanchir serait fail-open (mesuré par (m3)).
#       LA FRONTIÈRE DE MOT EN FIN EST CONSERVÉE : après la dernière pièce il
#       faut la fin de ligne ou un séparateur (blanc, `;`, `&`, `|`, `(`, `)`,
#       `<`, `>`, backtick). Sans elle le parseur retiendrait un PRÉFIXE du
#       délimiteur, ne trouverait jamais sa ligne de clôture et SUR-BLANCHIRAIT
#       jusqu'à la fin (fail-open mesuré, (p5)).
#       CE QUE CETTE FORME REMPLACE : une RE `<<-?[ \t]*('W'|"W")` qui n'admettait
#       qu'UNE pièce, entièrement citée. Elle ratait `<<\EOF` et `<<E"O"F` —
#       CITÉS pour bash, donc corps 100 % littéral — dont le corps restait
#       ANALYSÉ : de la DONNÉE pouvait être refusée. Faux positif, jamais
#       fail-open, mais exactement le faux positif que l'incident fondateur de
#       cet étage décrit mot pour mot.
#       EN ERREUR — pièce non reconnue, caractère hors jeu, quote non refermée,
#       frontière manquante, aucune pièce citée : `""`, donc corps CONSERVÉ ->
#       ANALYSÉ. Le parseur n'a QUE cette sortie de secours, et c'est le côté
#       d'erreur imposé par la règle de conception.
#   (d) contrat de sortie INCHANGÉ, et quatre propriétés en dépendent : le `\r`
#       final est retiré de CHAQUE ligne au stockage (pas des seules lignes de
#       corps, sinon `EOF\r` != `EOF` et le corps ne ferme jamais) ; la
#       comparaison de clôture trime tête ET queue ; la ligne fermante est
#       imprimée VERBATIM ; un corps ouvert sans fermant blanchit jusqu'à la fin —
#       sûr, parce qu'un vrai heredoc non fermé est une erreur de parse bash :
#       rien ne s'exécute. Intro imprimée, corps -> lignes vides, étages 1-2
#       intouchés.
#
# CE QUI N'EST PAS COUVERT — ÉNUMÉRATION, JAMAIS UN UNIVERSEL, avec la polarité
# dite en toutes lettres :
#   - CLASSE FAIL-OPEN, différée sur arbitrage explicite : `<<'W'` apparaissant
#     dans une position lexicale où `<<` n'est PAS un opérateur de redirection
#     ouvre encore un faux corps et blanchit la suite. Deux instances connues, et
#     fermer l'une ne ferme pas l'autre : l'expansion de paramètre (`${v#<<'X'}`)
#     ET l'arithmétique avec délimiteur cité alphabétique (`((x<<'A'))`,
#     `$((x<<'A'))`) — le parsing diffère, un correctif scopé aux `${…}`
#     n'attraperait pas le frère arithmétique. Suivi au board.
#   - FERMÉ PAR T-00000210 : `<<\EOF` et `<<E"O"F` tombaient hors de la RE, leur
#     corps restait ANALYSÉ et un refus sur de la DONNÉE était possible. Le
#     parseur de pièces de (c) les reconnaît désormais, avec `<<'A'B`. CE QUI
#     RESTE hors du jeu `[A-Za-z0-9_]` — un délimiteur portant un espace
#     (`<<'E F'`), un `$`, un point — n'est toujours pas reconnu et son corps
#     reste ANALYSÉ : MÊME faux positif, borné, pinné par (r5), jamais un
#     fail-open. Le jeu s'élargit avec son arm, ou pas.
#   - Lignes de CONTINUATION d'un segment cité multi-ligne : analysées comme du
#     code par les étages 1-2. FAUX POSITIF, même prix qu'à l'étage 1.
#   - L'arithmétique NUMÉRIQUE `$((1<<2))` : le parseur de (c) n'y voit AUCUNE
#     pièce citée, donc ANALYSÉ. Côté sûr, pas d'arm dédié.
#   - LE BACKTICK DANS `TAIL`, la classe de frontière de mot de (c) : mesuré, le
#     mot délimiteur n'est JAMAIS développé par bash, donc un backtick collé au
#     délimiteur en fait partie et n'est pas une frontière. La garde ferme alors
#     PLUS TÔT que bash et blanchit MOINS : faux positif, sûr dans les deux sens.
#     GARDÉ TEL QUEL, décision assumée — le retirer serait exact, mais aucun arm
#     ne mesure ce caractère, et modifier une règle de reconnaissance qu'aucun
#     test ne pin est exactement la dérive « clause au coup par coup » que ce
#     fichier vient de payer trois fois. Se corrige avec son arm, ou pas.
#   - `>#` et `<#` : un `#` en début de mot APRÈS un opérateur de redirection est
#     un commentaire pour bash, mais `head` y est faux ici — `<` et `>` ne sont
#     pas dans la classe de séparateurs. Advisory de la revue de sécurité, NON
#     EXPLOITABLE et laissé tel quel : une redirection sans cible est une erreur
#     de syntaxe bash, donc rien ne s'exécute et il n'y a aucune commande à
#     cacher. Nommé ici plutôt que corrigé de travers — élargir la classe de
#     séparateurs toucherait (b'') et (c) sans qu'aucun arm ne le mesure.
# Panne d'instrument : exit 0 ANNONCÉ, jamais exit 2 — doctrine (j)/(n5)(n6).
HEREFREE=$(printf '%s\n' "$CMD" | "$PY" -c '
import sys
SQ = "\x27"
DQ = "\x22"
BS = "\x5c"
BT = "\x60"
NL = "\x0a"
SEP = " \t;&|()" + BT + NL
TAIL = SEP + "<>"
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
def scrub_spans(text):
    # T-01M5D6XS2S : une lecture RÉCURSIVE. Dans "…", un $(…) ou un backtick NON
    # échappé est du CODE (le segment cité se coupe autour) ; dans ce code, un
    # corps de heredoc à délimiteur CITÉ est une DONNÉE jusqu à la première ligne
    # qui COMMENCE par le délimiteur, blancs de tête retirés (EOF) compris) ; un
    # corps de heredoc NU, ou de premier niveau, garde ses guillemets LITTÉRAUX.
    # Une construction IMBRIQUÉE qui ne se ferme pas (ou plus de 64 niveaux)
    # ARRÊTE la lecture : rien après le guillemet qui l ouvre n est neutralisé,
    # donc tout y est ANALYSÉ (bash n exécute rien après une construction non
    # fermée) — et aucune relecture spéculative, qui serait exponentielle.
    spans = []
    n = len(text)
    meta = " \t;&|()<>" + NL
    stop = [False]
    def single(i):
        k = i + 2 if text[i] == "$" else i + 1
        while k < n:
            if text[i] == "$" and text[k] == BS:
                k += 2
                continue
            if text[k] == SQ:
                return k + 1
            k += 1
        return -1
    def opaque(i, close):
        # F3 : `${…}` (close "}") et `$((…))`/`((…))` (close "))") lus d un
        # bloc, guillemets sautés : ni segment ni heredoc dedans, texte ANALYSÉ.
        # -2 : pas une arithmétique ; -1 : jamais fermé, la lecture S ARRÊTE.
        # N1 (2e passe) : une citation ANSI-C, une substitution ou un backtick
        # DANS le bloc — guillemets doubles compris — ne se lit pas d un bloc :
        # CHEMIN D ARRÊT, tout ce qui suit est analysé (jamais modélisé).
        depth = 0
        k = i
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] in "(" + SQ):
                stop[0] = True
                return -1
            if c == SQ or c == DQ:
                k += 1
                while k < n and text[k] != c:
                    if c == DQ and text[k] == BS:
                        k += 1
                    elif c == DQ and (text[k] == BT or (text[k] == "$" and k + 1 < n and text[k + 1] == "(")):
                        stop[0] = True
                        return -1
                    k += 1
                k += 1
                continue
            if close == "}":
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return k + 1
                    depth -= 1
            elif c == "(":
                depth += 1
            elif c == ")":
                if depth > 0:
                    depth -= 1
                elif k + 1 < n and text[k + 1] == ")":
                    return k + 2
                else:
                    return -2
            k += 1
        stop[0] = True
        return -1
    def double(i, lvl):
        start = i
        k = i + 1
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == DQ:
                spans.append((start, k + 1))
                return k + 1
            if c == "$" and text.startswith("((", k + 1):
                j = opaque(k + 3, "))")
                if j == -1:
                    return -1
                if j > 0:
                    if k > start:
                        spans.append((start, k))
                    start = j
                    k = j
                    continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                if k > start:
                    spans.append((start, k))
                k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                if k < 0:
                    return -1
                start = k
                continue
            k += 1
        return -1
    def delimiter(i):
        dash = i < n and text[i] == "-"
        if dash:
            i += 1
        while i < n and text[i] in " \t":
            i += 1
        # 3e passe : le mot délimiteur n est lu que s il est fait de pièces
        # SÛRES — caractères de `safe`, entre `'…'` ou `"…"` sans rien d autre,
        # ou `\c` avec c sûr. Tout autre caractère ($'…', $"…", \$, \\, backtick,
        # accolade, retour à la ligne échappé…) : bash le transforme par sa
        # suppression des guillemets, la garde ne le modélise pas — CHEMIN D
        # ARRÊT, tout ce qui suit est analysé.
        safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.+,:@%/"
        word = []
        quoted = False
        while i < n and text[i] not in meta:
            c = text[i]
            if c == SQ or c == DQ:
                j = text.find(c, i + 1)
                if j < 0:
                    return i, None
                if any(x not in safe for x in text[i + 1:j]):
                    stop[0] = True
                    return n, None
                spans.append((i, j + 1))
                word.append(text[i + 1:j])
                quoted = True
                i = j + 1
                continue
            if c == BS and i + 1 < n and text[i + 1] in safe:
                word.append(text[i + 1])
                quoted = True
                i += 2
                continue
            if c not in safe:
                stop[0] = True
                return n, None
            word.append(c)
            i += 1
        if not word:
            return i, None
        return i, ("".join(word), quoted, dash)
    def bare(i, word, dash, close, lvl):
        while i < n:
            e = text.find(NL, i)
            line = text[i:] if e < 0 else text[i:e]
            first = line.lstrip("\t") if dash else line
            if first == word or (close == ")" and first.startswith(word + ")")):
                return i
            k = i
            while k < n and text[k] != NL:
                c = text[k]
                if c == BS:
                    k += 2
                    continue
                if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                    k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                    if k < 0:
                        return n
                    continue
                k += 1
            i = k + 1
        return n
    def bodies(i, docs, close, lvl):
        for at, (word, quoted, dash) in enumerate(docs):
            last = at == len(docs) - 1
            if i >= n:
                return n
            if quoted and close:
                k = i
                found = -1
                while True:
                    e = text.find(NL, k)
                    if e < 0:
                        e = n
                    if text[k:e].lstrip(" \t").startswith(word):
                        found = k
                        break
                    # F6 : sous bash 3.2, une ligne `)` DU CORPS referme le
                    # `$(…)` et la suite s exécute (mesuré). 2e passe : CHEMIN
                    # D ARRÊT, jamais une reprise en code — tout ce qui suit le
                    # guillemet ouvrant est ANALYSÉ.
                    if text[k:e].lstrip(" \t").startswith(")"):
                        stop[0] = True
                        return n
                    if e >= n:
                        break
                    k = e + 1
                if found >= 0:
                    if found - 1 > i:
                        spans.append((i, found - 1))
                    i = found
                    if not last:
                        e = text.find(NL, i)
                        i = n if e < 0 else e + 1
                    continue
            i = bare(i, word, dash, close, lvl)
            if not last and i < n:
                e = text.find(NL, i)
                i = n if e < 0 else e + 1
        return i
    def code(i, close, lvl):
        if lvl > 64:
            stop[0] = True
            return -1
        head = True
        depth = 0
        docs = []
        while i < n:
            c = text[i]
            if c == NL and docs:
                i = bodies(i + 1, docs, close, lvl)
                docs = []
                head = True
                continue
            if c == BS:
                i += 2
                head = False
                continue
            if c == "#" and head:
                j = text.find(NL, i)
                if j < 0:
                    break
                i = j
                continue
            if close and c == close and (close == BT or depth == 0):
                return i + 1
            if (c == "$" and i + 1 < n and text[i + 1] == "{") or (c == "$" and text.startswith("((", i + 1)) or (c == "(" and text.startswith("(", i + 1)):
                if text[i + 1] == "{":
                    j = opaque(i + 2, "}")
                else:
                    j = opaque(i + (3 if c == "$" else 2), "))")
                if j == -1:
                    if close:
                        return -1
                    break
                if j > 0:
                    i = j
                    head = False
                    continue
            if c == SQ or (c == "$" and i + 1 < n and text[i + 1] == SQ):
                j = single(i)
                if j < 0:
                    i += 1
                    head = False
                    continue
                spans.append((i, j))
                i = j
                head = False
                continue
            if c == DQ:
                mark = len(spans)
                j = double(i, lvl)
                if j < 0:
                    del spans[mark:]
                    if stop[0]:
                        if close:
                            return -1
                        break
                    i += 1
                    head = False
                    continue
                i = j
                head = False
                continue
            if c == "<" and i + 1 < n and text[i + 1] == "<":
                if i + 2 < n and text[i + 2] == "<":
                    i += 3
                    head = True
                    continue
                i, doc = delimiter(i + 2)
                if doc:
                    docs.append(doc)
                head = False
                continue
            if c == "(":
                depth += 1
            elif c == ")" and depth > 0:
                depth -= 1
            i += 1
            head = c in SEP
        if close:
            stop[0] = True
            return -1
        return n
    code(0, "", 0)
    return spans
def heredoc_delimiter(line, at):
    n = len(line)
    i = at + 2
    if i < n and line[i] == "-":
        i += 1
    while i < n and line[i] in " \t":
        i += 1
    parts = []
    quoted = False
    while i < n:
        ch = line[i]
        if ch == SQ or ch == DQ:
            end = line.find(ch, i + 1)
            if end < 0:
                return ""
            inner = line[i + 1:end]
            for c in inner:
                if c not in CHARS:
                    return ""
            parts.append(inner)
            quoted = True
            i = end + 1
            continue
        if ch == BS:
            if i + 1 >= n or line[i + 1] not in CHARS:
                return ""
            parts.append(line[i + 1])
            quoted = True
            i += 2
            continue
        if ch in CHARS:
            parts.append(ch)
            i += 1
            continue
        break
    if not quoted:
        return ""
    if i < n and line[i] not in TAIL:
        return ""
    return "".join(parts)
def scan(line):
    n = len(line)
    i = 0
    loose = -1
    par = 0
    brk = 0
    brc = 0
    tick = 0
    cont = False
    cands = []
    head = True
    while i < n:
        ch = line[i]
        if ch == BS:
            if i + 1 >= n:
                cont = True
            i += 2
            head = False
            continue
        ansi = ch == "$" and i + 1 < n and line[i + 1] == SQ
        if ch == SQ or ch == DQ or ansi:
            end = i + 2 if ansi else i + 1
            if ansi:
                ch = SQ
            while end < n:
                if (ch == DQ or ansi) and line[end] == BS:
                    end += 2
                    continue
                if line[end] == ch:
                    break
                end += 1
            if end >= n:
                if loose < 0:
                    loose = i
                i += 1
            else:
                i = end + 1
            head = False
            continue
        if ch == "#" and head:
            break
        if ch == "<" and i + 1 < n and line[i + 1] == "<":
            cands.append(i)
            i += 2
            head = True
            continue
        if ch == "(":
            par += 1
        elif ch == ")":
            if par > 0:
                par -= 1
        elif ch == "[":
            brk += 1
        elif ch == "]":
            if brk > 0:
                brk -= 1
        elif ch == "{":
            brc += 1
        elif ch == "}":
            if brc > 0:
                brc -= 1
        elif ch == BT:
            tick = 1 - tick
        i += 1
        head = ch in SEP
    if tick or par > 0 or brk > 0 or brc > 0:
        cont = True
    return loose, cont, cands
def opener(line, base, spans):
    loose, cont, cands = scan(line)
    if not cands:
        return ""
    if loose >= 0 or cont:
        return ""
    at = cands[0]
    for lo, hi in spans:
        if lo <= base + at < hi:
            return ""
    return heredoc_delimiter(line, at)
data = sys.stdin.read()
if data.endswith("\n"):
    data = data[:-1]
src = []
for raw in data.split("\n"):
    if raw.endswith("\r"):
        raw = raw[:-1]
    src.append(raw)
spans = scrub_spans(NL.join(src))
bases = []
pos = 0
for line in src:
    bases.append(pos)
    pos += len(line) + 1
out = []
total = len(src)
i = 0
while i < total:
    out.append(src[i])
    delim = opener(src[i], bases[i], spans)
    if delim:
        i += 1
        while i < total and src[i].strip(" \t") != delim:
            out.append("")
            i += 1
        if i < total:
            out.append(src[i])
    i += 1
sys.stdout.write("\n".join(out))
') || degraded "the heredoc stage failed"
# POSTURE DÉGRADÉE, symétrique de celle de l'étage 1 ci-dessous : deux symptômes,
# le statut de sortie et une sortie VIDE sur une entrée qui ne l'était pas (cet
# étage imprime TOUJOURS au moins la ligne d'introduction, donc un vide ne peut
# venir que d'une panne). Annoncé, exit 0, JAMAIS exit 2.
if [ -n "$CMD" ] && [ -z "$HEREFREE" ]; then
  degraded "the heredoc stage failed (empty output on a non-empty command)"
fi

# --- Étage 1 : neutraliser les segments cités --------------------------------
# Scanner CONSCIENT DE L'ÉCHAPPEMENT (T-00000181), port règle pour règle de
# `quoted_spans()` (.codex/hooks/safe_bash.py l. 124-180), sur le TEXTE ENTIER :
#   - hors citation un `\` échappe le caractère SUIVANT, donc un nombre IMPAIR de
#     `\` devant un guillemet le rend LITTÉRAL et n'ouvre AUCUN segment ; un
#     nombre PAIR le laisse ouvrir un vrai segment, et `echo \\" … \\"` reste de
#     la donnée (c'est le contrôle qui interdit le correctif « ignorer tous les
#     backslashes », lequel refuserait des charges utiles bien formées) ;
#   - dans `"…"` le `\` échappe encore ; dans `'…'` il n'échappe rien ;
#   - `$'…'` est une citation ANSI-C : le `\` y échappe, donc `$'\''` est UN
#     segment qui contient une apostrophe (T-01M5D6XS2S, T-01M55CF5 — lu comme
#     `'…'`, il ouvrait un faux segment qui avalait `; git reset --hard ;` sur
#     les trois hôtes). Même clause, à l'identique, dans les trois copies de
#     `scrub_spans` et dans l'automate `scan` de l'étage 0.5 ;
#   - un guillemet NON APPARIÉ ne ferme rien, donc n'ouvre rien : le reste du
#     texte redevient analysable (`echo l'index && rm -rf x` reste refusé) ;
#   - c'est le guillemet OUVRANT le plus à gauche qui gagne, donc `"… '…' …"` est
#     un seul segment double et n'est pas coupé au guillemet simple interne.
# CE QUI NE VOYAGE PAS depuis le python : son contrat ISOMÉTRIQUE (un `@` par
# caractère). L'étage 2 lit le texte NEUTRALISÉ lui-même (split, RSTART/RLENGTH
# sur SCRUBBED), jamais un offset reporté sur la charge brute — le contrat de
# sortie reste donc ` @@ `, à l'identique, et l'étage 2 ne change pas d'une ligne.
# TEXTE ENTIER, JAMAIS LIGNE PAR LIGNE (T-00000208, D1 — ceci REVIENT sur C1 de
# S-00000285, qui avait imposé le par-ligne). Ce scanner lit la charge comme UN
# texte, exactement comme `quoted_spans()`/`scrub_quoted()` côté python : un
# segment cité qui enjambe un retour à la ligne EST neutralisé, parce que bash le
# cite vraiment. Le balayage par ligne prétendait fermer un fail-open ; il en
# OUVRAIT un, et il a été MESURÉ : sur `echo 'a` ⏎ `b' && rm -rf src/x && echo
# 'x'`, la ligne 2 ne montre au scanner que deux apostrophes orphelines, qu'il
# apparie l'une à l'autre en neutralisant tout l'intervalle — le `rm` compris —
# alors que bash, lui, l'exécute. Le garde se taisait sur une suppression réelle,
# en zone CODE, la plus exposée.
#
# LA FRONTIÈRE DE COMMENTAIRE, ET LA PROSE QU'ELLE CORRIGE (revue de sécurité de
# classe 1, CRITICAL). Ce paragraphe affirmait que le résidu du texte entier
# vivait « en zone NON-CODE (corps de heredoc à délimiteur nu, commentaires) ».
# C'ÉTAIT FAUX, et pas d'un cheveu : un `#` de commentaire portant un guillemet
# non apparié s'appariait avec un vrai guillemet situé PLUS LOIN et blanchissait
# tout l'intervalle — Y COMPRIS UNE LIGNE DE CODE RÉELLE, sur une AUTRE ligne
# physique, que bash exécute pour de bon. Mesuré par exécution contre ce hook :
# `# don't run this` ⏎ `rm -rf src/x && echo 'ok'` sortait 0 EN SILENCE (HEAD
# sortait 2), et les mêmes deux lignes emportaient aussi `git clean -fdx` ici et
# `npx skills add other/pkg` dans `audit-gate.sh`. Le résidu n'était donc pas
# cantonné à la donnée : il ATTEIGNAIT le code. Dit, pas tu.
# LE CORRECTIF RÉUTILISE LA RÈGLE QUI EXISTAIT DÉJÀ, il n'en écrit pas une
# seconde : c'est la clause (b'') de l'étage 0.5 ci-dessus, mot pour mot — un `#`
# NON CITÉ, non échappé, en DÉBUT DE MOT (précédé d'un blanc, d'un début de
# ligne, ou d'un séparateur de `SEP`) coupe la LIGNE PHYSIQUE courante. Même
# constante `SEP`, même suivi de `head`, mêmes exceptions : jamais après `$` ni
# `{`, sinon `$#` et `${#v}` cesseraient d'être des expansions. La coupe est
# appliquée PENDANT le balayage des guillemets, donc un guillemet situé après un
# tel `#` ne peut jamais participer à un appariement qui traverse la fin de cette
# ligne — ce qui est exactement la sémantique de bash, où un commentaire s'arrête
# à sa ligne physique quel que soit son contenu.
# CE QUE LA COUPE NE FAIT PAS, ET C'EST DÉLIBÉRÉ : elle n'EFFACE rien. Le texte
# du commentaire n'est pas blanchi, il est seulement exclu de l'appariement des
# guillemets, donc il redescend TEL QUEL aux étages suivants et y est ANALYSÉ.
# La règle de conception de l'étage 0.5 vaut ici mot pour mot — dégrader vers
# ANALYSÉ, jamais vers effacement : blanchir un commentaire collerait mieux à
# bash, mais une reconnaissance fautive effacerait alors du code, et un corps de
# heredoc à délimiteur NU (dont bash développe les `$(…)`, cf. (m3)) verrait ses
# lignes en `#` disparaître — fail-open. En erreur, cette clause ne produit donc
# qu'un FAUX POSITIF : un commentaire qui contient `; rm -rf x` peut être refusé
# alors que bash ne l'exécute pas. Côté sûr, assumé, et c'est le prix nommé.
# UNE DIVERGENCE ASSUMÉE avec (b''), dans le sens sûr : l'étage 0.5 rouvre un
# début de mot après un `<<` (son automate en a besoin), pas ce scanner-ci — `<`
# n'est pas dans `SEP`. Ce scanner coupe donc MOINS souvent, ce qui ne peut
# produire qu'un ANALYSÉ de plus. Élargir `SEP` toucherait (b'') et (c) sans
# qu'aucun arm ne le mesure : nommé plutôt que corrigé de travers.
# LE TROU DU CORPS NU (T-00000224, arm (m7)) EST FERMÉ PAR T-01M5D6XS2S : le
# scanner lit les heredocs. Un corps NU, ou de premier niveau, garde ses
# guillemets LITTÉRAUX (seuls ses `$(…)` et backticks y sont du code), donc une
# apostrophe qui y vit n'ouvre plus rien. FAUX POSITIF BORNÉ, côté sûr, épinglé
# par (sd7a) : le corps d'un heredoc à délimiteur NU dans "$(…)" reste du texte
# ANALYSÉ, donc une ligne qui y porte une commande destructrice est refusée
# alors que bash ne l'exécute pas ; à délimiteur CITÉ (`<<'EOF'`), ce corps est
# une donnée et passe ((sb2n3)). DANS "…", un `$(…)` ou un backtick
# NON échappé est du CODE : le segment cité se coupe autour (un commentaire
# continué `# c \` y finit à sa ligne, comme pour bash) ; et dans ce code, le
# corps d'un heredoc à délimiteur CITÉ est une DONNÉE jusqu'à la première ligne
# qui COMMENCE par le délimiteur, blancs de tête retirés (`EOF)` compris, et
# `<<-` + tabulation) — un corps jamais fermé reste analysé. FAUX POSITIF
# BORNÉ, côté sûr (C18) : une ligne de corps `EOFX…`, ou `EOF` suivi de blancs,
# ou ` EOF)` sous `<<`, ferme ici PLUS TÔT que bash ; la suite est analysée et
# peut être refusée (arm (sb2fp)). Un heredoc ouvert ET fermé par `)` sur une
# même ligne (substitution qui ouvre le heredoc et se referme aussitôt) n'ouvre aucun corps : bash 5.3 lirait les
# lignes suivantes comme corps, bash 3.2 et zsh les EXÉCUTENT (mesuré) — elles
# restent analysées. Une construction imbriquée non fermée, ou de plus de 64
# niveaux, ARRÊTE la lecture : rien après son guillemet ouvrant n'est
# neutralisé (tout est analysé ; bash n'exécute rien après elle). PASSE DE
# CORRECTION F3 : `${…}`, `$((…))` et `((…))` sont lus D'UN BLOC (aide
# `opaque`, guillemets sautés) — ni segment ni heredoc dedans, leur texte est
# ANALYSÉ ; un `<<'EOF'` qui y vit n'ouvre aucun corps, et un délimiteur cité qui
# porte `{` ou `}` hors guillemets non plus ; jamais fermé, il ARRÊTE la
# lecture. Le `${y:-)}` d'un `"$(…)"` ne ferme donc plus la substitution.
# PASSE DE CORRECTION F6 : sous bash 3.2, une ligne du corps cité qui commence
# par `)` referme le `$(…)` et la suite s'exécute (mesuré) — le blanchiment
# s'arrête à cette ligne et la suite est analysée (faux positif sous bash 5.3,
# côté sûr). BORNE nommée :
# un `)` de motif de `case` DANS un `$(…)` entre guillemets ferme la
# substitution trop tôt pour ce scanner, et la suite redevient de la donnée
# citée — comme avant T-01M5D6XS2S, où le segment entier l'était.
# QUOTAGE, ET C'EST LA PARTIE FRAGILE : le programme est tenu par des guillemets
# SIMPLES bash et n'en contient AUCUN — les deux caractères de citation, et le
# backslash lui-même, y sont écrits `\x27` / `\x22` / `\x5c` dans des littéraux
# python. Jamais de splice `'\''`. La charge utile arrive par STDIN, jamais par
# argv : elle n'est à aucun moment rendue à un shell.
# Il est tenu dans SCRUB_PY et lancé DEUX fois au plus : le texte neutralisé
# ici, la table des segments cités pour l'étage 2 (mode `table`, seulement si
# un `@@` est produit). L'étage 1 de `audit-gate.sh` en portait la copie
# VERBATIM ; il garde l'ANCIENNE version (sans citation ANSI-C ni substitution
# dans "…") jusqu'à T-01M5D8B1JJ. Pas de fichier d'aide partagé : un hook qui
# `source` un voisin acquiert un mode de panne (fichier absent, non lisible) que
# le hook autonome n'a pas.
SCRUB_PY='
import sys
SQ = "\x27"
DQ = "\x22"
BS = "\x5c"
BT = "\x60"
NL = "\x0a"
TAB = "\x09"
SEP = " \t;&|()" + BT + NL
def scrub_spans(text):
    # T-01M5D6XS2S : une lecture RÉCURSIVE. Dans "…", un $(…) ou un backtick NON
    # échappé est du CODE (le segment cité se coupe autour) ; dans ce code, un
    # corps de heredoc à délimiteur CITÉ est une DONNÉE jusqu à la première ligne
    # qui COMMENCE par le délimiteur, blancs de tête retirés (EOF) compris) ; un
    # corps de heredoc NU, ou de premier niveau, garde ses guillemets LITTÉRAUX.
    # Une construction IMBRIQUÉE qui ne se ferme pas (ou plus de 64 niveaux)
    # ARRÊTE la lecture : rien après le guillemet qui l ouvre n est neutralisé,
    # donc tout y est ANALYSÉ (bash n exécute rien après une construction non
    # fermée) — et aucune relecture spéculative, qui serait exponentielle.
    spans = []
    n = len(text)
    meta = " \t;&|()<>" + NL
    stop = [False]
    def single(i):
        k = i + 2 if text[i] == "$" else i + 1
        while k < n:
            if text[i] == "$" and text[k] == BS:
                k += 2
                continue
            if text[k] == SQ:
                return k + 1
            k += 1
        return -1
    def opaque(i, close):
        # F3 : `${…}` (close "}") et `$((…))`/`((…))` (close "))") lus d un
        # bloc, guillemets sautés : ni segment ni heredoc dedans, texte ANALYSÉ.
        # -2 : pas une arithmétique ; -1 : jamais fermé, la lecture S ARRÊTE.
        # N1 (2e passe) : une citation ANSI-C, une substitution ou un backtick
        # DANS le bloc — guillemets doubles compris — ne se lit pas d un bloc :
        # CHEMIN D ARRÊT, tout ce qui suit est analysé (jamais modélisé).
        depth = 0
        k = i
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] in "(" + SQ):
                stop[0] = True
                return -1
            if c == SQ or c == DQ:
                k += 1
                while k < n and text[k] != c:
                    if c == DQ and text[k] == BS:
                        k += 1
                    elif c == DQ and (text[k] == BT or (text[k] == "$" and k + 1 < n and text[k + 1] == "(")):
                        stop[0] = True
                        return -1
                    k += 1
                k += 1
                continue
            if close == "}":
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return k + 1
                    depth -= 1
            elif c == "(":
                depth += 1
            elif c == ")":
                if depth > 0:
                    depth -= 1
                elif k + 1 < n and text[k + 1] == ")":
                    return k + 2
                else:
                    return -2
            k += 1
        stop[0] = True
        return -1
    def double(i, lvl):
        start = i
        k = i + 1
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == DQ:
                spans.append((start, k + 1))
                return k + 1
            if c == "$" and text.startswith("((", k + 1):
                j = opaque(k + 3, "))")
                if j == -1:
                    return -1
                if j > 0:
                    if k > start:
                        spans.append((start, k))
                    start = j
                    k = j
                    continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                if k > start:
                    spans.append((start, k))
                k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                if k < 0:
                    return -1
                start = k
                continue
            k += 1
        return -1
    def delimiter(i):
        dash = i < n and text[i] == "-"
        if dash:
            i += 1
        while i < n and text[i] in " \t":
            i += 1
        # 3e passe : le mot délimiteur n est lu que s il est fait de pièces
        # SÛRES — caractères de `safe`, entre `'…'` ou `"…"` sans rien d autre,
        # ou `\c` avec c sûr. Tout autre caractère ($'…', $"…", \$, \\, backtick,
        # accolade, retour à la ligne échappé…) : bash le transforme par sa
        # suppression des guillemets, la garde ne le modélise pas — CHEMIN D
        # ARRÊT, tout ce qui suit est analysé.
        safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.+,:@%/"
        word = []
        quoted = False
        while i < n and text[i] not in meta:
            c = text[i]
            if c == SQ or c == DQ:
                j = text.find(c, i + 1)
                if j < 0:
                    return i, None
                if any(x not in safe for x in text[i + 1:j]):
                    stop[0] = True
                    return n, None
                spans.append((i, j + 1))
                word.append(text[i + 1:j])
                quoted = True
                i = j + 1
                continue
            if c == BS and i + 1 < n and text[i + 1] in safe:
                word.append(text[i + 1])
                quoted = True
                i += 2
                continue
            if c not in safe:
                stop[0] = True
                return n, None
            word.append(c)
            i += 1
        if not word:
            return i, None
        return i, ("".join(word), quoted, dash)
    def bare(i, word, dash, close, lvl):
        while i < n:
            e = text.find(NL, i)
            line = text[i:] if e < 0 else text[i:e]
            first = line.lstrip("\t") if dash else line
            if first == word or (close == ")" and first.startswith(word + ")")):
                return i
            k = i
            while k < n and text[k] != NL:
                c = text[k]
                if c == BS:
                    k += 2
                    continue
                if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                    k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                    if k < 0:
                        return n
                    continue
                k += 1
            i = k + 1
        return n
    def bodies(i, docs, close, lvl):
        for at, (word, quoted, dash) in enumerate(docs):
            last = at == len(docs) - 1
            if i >= n:
                return n
            if quoted and close:
                k = i
                found = -1
                while True:
                    e = text.find(NL, k)
                    if e < 0:
                        e = n
                    if text[k:e].lstrip(" \t").startswith(word):
                        found = k
                        break
                    # F6 : sous bash 3.2, une ligne `)` DU CORPS referme le
                    # `$(…)` et la suite s exécute (mesuré). 2e passe : CHEMIN
                    # D ARRÊT, jamais une reprise en code — tout ce qui suit le
                    # guillemet ouvrant est ANALYSÉ.
                    if text[k:e].lstrip(" \t").startswith(")"):
                        stop[0] = True
                        return n
                    if e >= n:
                        break
                    k = e + 1
                if found >= 0:
                    if found - 1 > i:
                        spans.append((i, found - 1))
                    i = found
                    if not last:
                        e = text.find(NL, i)
                        i = n if e < 0 else e + 1
                    continue
            i = bare(i, word, dash, close, lvl)
            if not last and i < n:
                e = text.find(NL, i)
                i = n if e < 0 else e + 1
        return i
    def code(i, close, lvl):
        if lvl > 64:
            stop[0] = True
            return -1
        head = True
        depth = 0
        docs = []
        while i < n:
            c = text[i]
            if c == NL and docs:
                i = bodies(i + 1, docs, close, lvl)
                docs = []
                head = True
                continue
            if c == BS:
                i += 2
                head = False
                continue
            if c == "#" and head:
                j = text.find(NL, i)
                if j < 0:
                    break
                i = j
                continue
            if close and c == close and (close == BT or depth == 0):
                return i + 1
            if (c == "$" and i + 1 < n and text[i + 1] == "{") or (c == "$" and text.startswith("((", i + 1)) or (c == "(" and text.startswith("(", i + 1)):
                if text[i + 1] == "{":
                    j = opaque(i + 2, "}")
                else:
                    j = opaque(i + (3 if c == "$" else 2), "))")
                if j == -1:
                    if close:
                        return -1
                    break
                if j > 0:
                    i = j
                    head = False
                    continue
            if c == SQ or (c == "$" and i + 1 < n and text[i + 1] == SQ):
                j = single(i)
                if j < 0:
                    i += 1
                    head = False
                    continue
                spans.append((i, j))
                i = j
                head = False
                continue
            if c == DQ:
                mark = len(spans)
                j = double(i, lvl)
                if j < 0:
                    del spans[mark:]
                    if stop[0]:
                        if close:
                            return -1
                        break
                    i += 1
                    head = False
                    continue
                i = j
                head = False
                continue
            if c == "<" and i + 1 < n and text[i + 1] == "<":
                if i + 2 < n and text[i + 2] == "<":
                    i += 3
                    head = True
                    continue
                i, doc = delimiter(i + 2)
                if doc:
                    docs.append(doc)
                head = False
                continue
            if c == "(":
                depth += 1
            elif c == ")" and depth > 0:
                depth -= 1
            i += 1
            head = c in SEP
        if close:
            stop[0] = True
            return -1
        return n
    code(0, "", 0)
    return spans
def ansi_decode(body):
    simple = {"a": chr(7), "b": chr(8), "e": chr(27), "E": chr(27), "f": chr(12), "n": NL, "r": chr(13), "t": TAB, "v": chr(11), BS: BS, SQ: SQ, DQ: DQ, "?": "?"}
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c != BS or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        x = body[i + 1]
        if x in simple:
            out.append(simple[x])
            i += 2
            continue
        if x in "01234567":
            j = i + 1
            v = 0
            while j < n and j < i + 4 and body[j] in "01234567":
                v = v * 8 + int(body[j])
                j += 1
            out.append(chr(v % 256))
            i = j
            continue
        if x in "xuU":
            lim = 2 if x == "x" else (4 if x == "u" else 8)
            j = i + 2
            v = 0
            while j < n and j < i + 2 + lim and body[j] in "0123456789abcdefABCDEF":
                v = v * 16 + int(body[j], 16)
                j += 1
            if j == i + 2:
                out.append(BS + x)
                i += 2
                continue
            if v >= 1114112 or 55296 <= v <= 57343:
                return None
            out.append(chr(v))
            i = j
            continue
        if x == "c":
            return None
        out.append(BS + x)
        i += 2
    s = "".join(out)
    if chr(0) in s:
        s = s[:s.index(chr(0))]
    return s
text = sys.stdin.read()
_DQ_ETAT = {"text": None, "i": 0, "stack": [""]}
def dq_open_at(text, e):
    # True when a double quote is OPEN at text[e]: a backslash escapes outside single quotes, single quotes
    # are literal outside double ones, and a $( or a backtick opens a NEW quoting context.
    # The walk is deterministic, and the table calls it with growing offsets: it RESUMES where the previous
    # call stopped (same text, e not behind), otherwise restarts at 0 — one pass per command, never
    # quadratic (security review, a command of n quoted segments followed by $ cost n full walks).
    etat = _DQ_ETAT
    if etat["text"] is text and etat["i"] <= e:
        stack, i = etat["stack"], etat["i"]
    else:
        stack, i = [""], 0
    while i < e:
        c, top = text[i], stack[-1]
        if top == SQ:
            if c == SQ:
                stack.pop()
        elif c == BS:
            i += 2
            continue
        elif c == DQ:
            if top == DQ:
                stack.pop()
            else:
                stack.append(DQ)
        elif c == SQ and top != DQ:
            stack.append(SQ)
        elif c == "$" and text[i + 1:i + 2] == "(":
            stack.append("(")
            i += 2
            continue
        elif c == "(" and top == "(":
            stack.append("(")
        elif c == ")" and top == "(":
            stack.pop()
        elif c == BT:
            if top == BT:
                stack.pop()
            else:
                stack.append(BT)
        i += 1
    etat["text"], etat["i"], etat["stack"] = text, i, stack
    return stack[-1] == DQ
if sys.argv[1:] == ["table"]:
    GLUE = " \t|&;()<>" + NL
    UNSAFE = set(" \t;&|()<>{}#@$" + BT + SQ + DQ + BS + NL + chr(13) + chr(28) + chr(29) + chr(30) + chr(31))
    spans = scrub_spans(text)
    rows = [str(len(spans)) + TAB + ("1" if "@@" in text else "0")]
    for s, e in spans:
        seg = text[s:e]
        locale = seg.startswith(DQ) and s > 0 and text[s - 1] == "$"
        left = s - 1 if locale else s
        glued_l = "1" if left > 0 and text[left - 1] not in GLUE else "0"
        glued_r = "1" if e < len(text) and text[e] not in GLUE else "0"
        kind = "0"
        if seg.startswith("$" + SQ) and seg.endswith(SQ) and len(seg) >= 3:
            body = ansi_decode(seg[2:-1])
            if body is not None and body and not (set(body) & UNSAFE):
                kind = "1"
            content = body if kind == "1" else chr(29)
        else:
            content = seg
            if content[:1] in (SQ, DQ):
                content = content[1:]
            if content[-1:] == seg[:1] and seg[:1] in (SQ, DQ):
                content = content[:-1]
            # 3e passe : un segment ENTIER entre apostrophes (2), ou entre
            # guillemets sans $, backtick ni antislash (3), est un texte
            # littéral que l étage 2 peut recoller à son mot.
            if len(seg) >= 2 and seg[0] == SQ and seg[-1] == SQ:
                kind = "2"
            elif len(seg) >= 2 and seg[0] == DQ and seg[-1] == DQ and not (set(content) & set("$" + BT + BS)):
                kind = "3"
        multi = "0"
        if kind != "1" and content != chr(29) and set(content) & set(NL + TAB + chr(13) + chr(28) + chr(30) + chr(31)):
            multi = "1"
            kind = "0"
            content = ""
        # 7e colonne (garde 8, T-01M5C1AF6GB3ZRX5QF9SF6R80Y) : ce segment OUVRE une substitution ENTRE
        # guillemets doubles — il commence par un guillemet, ne porte pas son guillemet fermant, et un `$(` ou un
        # backtick le suit : la substitution est lue entre guillemets, UN mot.
        qopen = "1" if (e < len(text) and text[e] in ("$", BT) and dq_open_at(text, e)) else "0"
        rows.append(kind + TAB + glued_l + TAB + glued_r + TAB + multi + TAB + content
                    + TAB + ("1" if locale else "0") + TAB + qopen)
    # F2 (passe de correction) : un caractère que la sortie ne sait pas encoder
    # ne fait jamais planter la table (posture dégradée) ; ansi_decode refuse
    # déjà les demi-codets UTF-16 (D800-DFFF), comme ceux au-delà de 10FFFF.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stdout.write(NL.join(rows) + NL)
    sys.exit(0)
buf = []
last = 0
for start, end in scrub_spans(text):
    buf.append(text[last:start])
    buf.append(" @@ ")
    last = end
buf.append(text[last:])
sys.stdout.write("".join(buf))
'
SCRUBBED=$(printf '%s' "$HEREFREE" | "$PY" -c "$SCRUB_PY") || degraded "the quote scrub failed"
# POSTURE DÉGRADÉE (T-00000181). Si le scanner échoue, ce garde N'A PAS VU la
# commande : il le DIT et sort 0, exactement comme le chemin « pas de python »
# ci-dessus. Jamais un exit 2 — un garde qui bloque quand son instrument casse
# bloque TOUS les appels Bash et fait boucler l'hôte — et jamais un fail-open
# muet, qui se lirait comme un garde ayant vérifié. Deux symptômes sont
# couverts : le statut de sortie ci-dessus, et une sortie VIDE sur une entrée qui
# ne l'était pas (le scanner ne peut jamais raccourcir une ligne jusqu'au vide,
# donc ce cas ne peut venir que d'une panne).
if [ -n "$HEREFREE" ] && [ -z "$SCRUBBED" ]; then
  degraded "the quote scrub failed (empty output on a non-empty command)"
fi

# --- Étage redirection : une ÉCRITURE SHELL vers un fichier SUIVI OU PROTÉGÉ --
# Garde 4 (T-00000244). `> fichier`, `>> fichier`, `&>`, `N>fichier` contournent
# le chemin Edit/Write et ses gardes de checkpoint et de mandat. Le prédicat a
# DEUX clauses : refus si la cible littérale est GIT-SUIVIE *OU* couverte par le
# garde de chemins protégés — la seconde étant ce qui rattrape les deux fichiers
# SENSIBLES que git ne suit pas (`> KICKOFF_REQUIRED` désarmerait le garde de
# mandat ; `> .mcp.json` échapperait au déni d'Edit). Le prédicat est MESURÉ dans
# `core-scripts/measure_shell_write_fp.py`, qui le PORTE : FP 0,033 % des exécutés,
# zéro rouge sur les formes closes de polarité (corpus de T-00000244). REMESURÉ le
# 2026-09-26 pour le prédicat de T-00000721 (clones jetables à 9582d114 et
# bab7ea2f, mêmes corpus) : 0/3762 positif brut sur les transcripts de ce dépôt
# (tous postérieurs à la garde, donc aveugles à ses propres refus), 3 → 12/10428
# sur le corpus plus ancien du checkout frère ; des 9 neufs, 2 écrivaient par
# redirection le marqueur de la route de dev locale, retirée depuis (vrais
# positifs alors, T-00000750) et 7 des écritures de
# `.git/config` après un `cd` dans un dépôt jetable (faux positifs : une cible
# relative est jugée contre la racine, jamais le cd) — FP +0,067 %. La duplication de descripteur
# (`2>&1`, `>&2`), les cibles CITÉES (déjà ` @@ ` après l'étage 1) et à EXPANSION
# passent par construction — dont l'idiome `cmd > out 2>&1` que la doctrine ORDONNE.
#
# PASSE DÉDIÉE, AVANT la tokenisation de l'étage 2 : l'awk et le walk restent
# INCHANGÉS AU BYTE PRÈS. Elle lit le TEXTE SCRUBBED (heredoc retiré, segments
# cités neutralisés), donc un `>` vivant dans une chaîne ou un corps de heredoc à
# délimiteur cité est déjà invisible, exactement comme pour rm/mv.
#
# LES MOTIFS PROTÉGÉS SONT LUS DU GARDE CANONIQUE DE CETTE FAMILLE — le SIBLING
# `protect-paths.sh` — par EXTRACTION TEXTUELLE, jamais un `source` (doctrine
# d'autonomie des hooks) ni une COPIE de la liste (l'exemption dériverait de la
# règle qui dénie réellement). Le canon a DEUX surfaces : `BLOCKED_PATTERNS` ET
# les bras `*…)` de la fonction `juger` (credential, MCP, `.git`, marqueurs,
# pilote-seuls), tenus HORS de la liste par contrat (L-013) — un lecteur de la
# seule liste manquerait EXACTEMENT les fichiers qui motivent la clause. La ligne
# d'EXEMPTION `is_env_template` est reconnue et écartée, pas traitée comme un
# blocage. Chaque cible est jugée minusculisée PUIS repliée NT (`ntf`, T-00000722).
#
# STRICT, DIT À VOIX HAUTE : si le sibling est illisible OU si l'extraction ne
# retrouve pas les motifs SENSIBLES (kickoff, mcp), la clause protégée est
# ANNONCÉE-ÉTEINTE sur stderr — les écritures vers un fichier SUIVI restent
# gardées, mais jamais une exemption vide et muette. Panne de l'instrument
# (python PRÉSENT qui sort non nul ; ou qui sort 0 sans rien imprimer sur une
# entrée non vide, ou avec une sentinelle qui n'est pas EXACTEMENT `OK` ou
# `DEGRADED`, ou avec une ligne hors de sa grammaire fermée — passe 2) : REFUS,
# exit 2, règle redirect-stage-broken — l'EXCEPTION à
# la posture des autres étages depuis T-00000784 (S-00002848, S-00002849 ; voir
# redirect_stage_down() plus haut). Le sibling illisible n'est PAS une panne :
# il reste l'annonce REDIR_DEGRADED ci-dessous. Python ABSENT reste degraded(),
# à l'étage 0.
#
# LA RÈGLE DU NOM (T-00000698, correction — B#1 du binôme de clôture, mesuré
# sur les hooks vivants) : `cd .agents/state/gates && printf y > PUSH_DEFAUT_
# AUTORISE` et `printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"` sortaient
# 0 tous deux — le cd cache le RÉPERTOIRE à la résolution contre la racine (la
# cible se lit `<racine>/PUSH_DEFAUT_AUTORISE`, qu'aucun glob ne rattrape), la
# citation rend la cible invisible à l'étage 1 par construction. Le NOM, lui, ne
# se cache ni par l'un ni par l'autre. Le snippet reçoit donc AUSSI le texte
# HEREFREE (brut, heredocs retirés), séparé de SCRUBBED par un NUL — jamais une
# variable d'environnement, dont la taille est bornée par ARG_MAX et dont le
# dépassement ferait dégrader TOUTES les gardes sur une commande assez longue —,
# et juge le DERNIER SEGMENT de chaque cible de redirection, nue, citée ou sous
# un répertoire à expansion, replié, contre les noms du bloc
# `*.agents/state/gates/<nom>)` de protect-paths.sh, DÉRIVÉS des globs déjà
# extraits (jamais une troisième copie). Liste FERMÉE par conception : le cas
# général — cd ou guillemets pour une cible ORDINAIRE — est T-00000720.
# `REDIR` EST INITIALISÉ ICI (T-00000784, passe 3) : le `case` ci-dessous ne le
# pose qu'à `__SKIP__`, et le test qui suit le lisait tel quel — donc un
# `REDIR=__SKIP__` EXPORTÉ par l'environnement sautait tout l'étage, marqueur
# d'armement et fichier suivi rc 0 (mesuré sur 347889ea comme sur a342b9bd ;
# (z25)). Balayage de la passe 3 : c'était la SEULE variable du shell de ce
# fichier lue avant d'être affectée sur tous les chemins ; les lectures
# d'environnement voulues sont `CLAUDE_PROJECT_DIR`, `OS` et `PATH`.
REDIR=""; REDIR_REFUSED=""; REDIR_DEGRADED=0; REDIR_RC=0
case "$SCRUBBED" in
  *">"*) ;;                       # au moins un opérateur de redirection candidat
  *) REDIR="__SKIP__";;           # aucun `>` : rien à garder, on n'ouvre pas python
esac
if [ "${REDIR:-}" != "__SKIP__" ]; then
REDIR=$(printf '%s\0%s' "$HEREFREE" "$SCRUBBED" | \
  REDIR_REPO="${CLAUDE_PROJECT_DIR:-.}" \
  REDIR_PROTECT_SH="$(dirname "$0")/protect-paths.sh" \
  "$PY" -c '
import sys, os, re, subprocess, posixpath
from pathlib import Path
REPO = os.environ.get("REDIR_REPO") or "."
SH = os.environ.get("REDIR_PROTECT_SH", "")
ENV_TPL = (".env.example", ".env.sample", ".env.template", ".env.dist")
def load_protected():
    prefixes = []
    globs = []
    try:
        text = open(SH, encoding="utf-8", errors="replace").read()
    except Exception:
        return prefixes, globs, False, False
    # ANCHORED at column 0 with re.M: a floating search otherwise falls back on
    # the LOOP line (indented BLOCKED_PATTERNS that REFERENCES itself and pipes a
    # sed) and yields SHELL GARBAGE as prefixes while the canary stays green.
    # That was the HIGH fail-open of the security review. Only the top-level
    # assignment is the one we want.
    m = re.search(r"^BLOCKED_PATTERNS=" + chr(34) + "([^" + chr(34) + "]*)" + chr(34), text, re.M)
    if m:
        for p in m.group(1).split():
            # Belt and braces: never a prefix carrying a shell metacharacter; an
            # extraction that produces one is a broken extraction.
            if p and p != ".env" and not any(c in p for c in "$()" + chr(39) + chr(34)):
                prefixes.append(p.lower())
    for rel in (".agents/protected-paths.local", ".claude/hooks/protected-paths.local"):
        try:
            loc = open(os.path.join(REPO, rel), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for line in loc.splitlines():
            line = re.sub(r"#.*$", "", line).strip()
            if line:
                prefixes.append(line.lower())
    for mm in re.finditer(r"^[ \t]*(\*[^)\n]*)\)", text, re.M):
        group = mm.group(1)
        if ".env." in group or "$" in group or chr(34) in group:
            continue
        for g in group.split("|"):
            g = g.strip().lower()
            if g and g != "*":
                globs.append(g)
    return prefixes, globs, True, (m is not None)
PREF, GLOBS, READ, BLOCKED_OK = load_protected()
# COMPLETE depends ALSO on BLOCKED_PATTERNS extraction succeeding (BLOCKED_OK),
# not only on the sensitive globs being present: the canary must detect an
# INCOMPLETE extraction (the source of src/legacy/ and generated/ lost), not
# only an ABSENT one -- the incomplete case is the dangerous one, since it would
# otherwise trigger no strict branch at all (security review, HIGH class 1).
COMPLETE = READ and BLOCKED_OK and any("kickoff_required" in g for g in GLOBS) and any("mcp.json" in g for g in GLOBS)
# The arming/exit marker NAMES, derived from the globs just read: the last
# segment of every `*.agents/state/gates/<name>` arm, already case-folded there.
MARKERS = set(g.rsplit("/", 1)[-1] for g in GLOBS if g.startswith("*.agents/state/gates/"))
def gmatch(g, s):
    left = g.startswith("*"); right = g.endswith("*")
    core = g.strip("*")
    if not core:
        return False
    if left and right:
        return core in s
    if left:
        return s.endswith(core)
    if right:
        return s.startswith(core)
    return s == core
# LE PLI NTFS (T-00000722), TROISIÈME COPIE : même corps que `NT_FOLD` de
# protect-paths.sh et `_nt_fold` des jumeaux Python, tenu par le différentiel
# énuméré de .agents/evals/test_protect_paths_hardening.py (qui extrait CE bloc).
def ntf(p, dots=False):
    segs = p.lower().replace(chr(92), "/").split("/")
    out = []
    for i, s in enumerate(segs):
        head = ""
        if i == 0 and len(s) >= 2 and s[1] == ":" and s[0].isalpha():
            head, s = s[:2], s[2:]
        s = s.split(":", 1)[0]
        if dots and "." in s and not s.strip(". "):
            s = ".." if s.count(".") >= 2 else "."
        elif s not in (".", ".."):
            s = s.rstrip(". ")
        out.append(head + s)
    return "/".join(out)
def protected_one(s):
    name = s.rsplit("/", 1)[-1]
    env_template = name.endswith(ENV_TPL)
    for p in PREF:
        if s.startswith(p):
            return p
    if (name == ".env" or name.startswith(".env.")) and not env_template:
        return ".env"
    # `.env` EN SOUS-CHAÎNE, gabarits exemptés (T-00000721) : la règle des
    # jumeaux Python (`.env` est un jeton de SECRET_NAMES) et celle du refus
    # Edit de protect-paths.sh (`.env` dans BLOCKED_PATTERNS) — `.envrc` et
    # `x.environment/f` étaient refusés partout sauf ici.
    if ".env" in s and not env_template:
        return ".env"
    for g in GLOBS:
        if env_template and ".env" in g:
            continue
        if gmatch(g, s):
            return g
    return ""
# LE POINT FIXE DES FORMES CANONIQUES (T-00000722 ; revue du lot T-00000721,
# HIGH « pli avant résolution ») : même fermeture que `PP_FERMETURE` de
# protect-paths.sh et `canonical_forms` des jumeaux Python. Les quatre candidats
# fixes d avant (minusculisé, replié, replié renormalisé, lecture « points »)
# n étaient pas clos : `normalize()` résout UNE fois, donc un lien révélé par un
# pli (`z/.../nom_neutre`) passait. Depuis {cand}, chaque tour ajoute à chaque
# forme sa casse repliée, ses deux plis (`ntf`, corps inchangé), sa
# renormalisation et sa résolution physique (realpath, relative à la racine
# sous l une de ses orthographes). BORNE : 5 tours, stabilité constatée au plus
# tard au 5e, sinon règle `formes-instables` (refus). POURQUOI 5 : un alias
# (point, espace, flux ADS, détour de points) d un lien dont la cible porte un
# segment de points (`courte1 -> z/.../courte2`) ne se stabilise qu au 5e ; une
# CHAÎNE de tels liens dépasse la borne. La marge mesurée est écrite une seule
# fois, à `canonical_forms` des jumeaux Python. COÛT : au plus 5 x 5 opérations
# par forme, dont un realpath.
BORNE = 5
# Les orthographes à lettre de lecteur de la racine (`C:/x` et `/c/x`, lettre
# dans ses deux casses) : la racine arrive en `/c/...` (cygpath) quand realpath
# rend `C:/...`. Runtime Windows NON mesuré ; `relativiser` est testée pure.
def lecteurs(r):
    out = set()
    if len(r) >= 2 and r[1] == ":" and r[0].isalpha() and (len(r) == 2 or r[2] == "/"):
        out.update("/" + x + r[2:] for x in (r[0].lower(), r[0].upper()))
    if len(r) >= 2 and r[0] == "/" and r[1].isalpha() and (len(r) == 2 or r[2] == "/"):
        out.update(x + ":" + r[2:] for x in (r[1].lower(), r[1].upper()))
    return out
def racines(root):
    base = root.replace(chr(92), "/").rstrip("/")
    vues = {base, os.path.realpath(base).replace(chr(92), "/").rstrip("/")}
    for r in list(vues):
        vues |= lecteurs(r)
    out = set()
    for r in vues:
        if r:
            out.update((r, r.lower(), ntf(r)))
    return sorted(out, key=len, reverse=True)
RACINES = racines(REPO)
def relativiser(r, rs):
    for s in rs:
        if r == s:
            return "."
        if r.startswith(s + "/"):
            return r[len(s) + 1:]
    return r
def physique(p):
    q = p.replace(chr(92), "/")
    if not os.path.isabs(q):
        q = os.path.join(REPO, q)
    return relativiser(os.path.realpath(q).replace(chr(92), "/"), RACINES)
def fermer(cand):
    formes = [cand] if cand else []
    vues = set(formes)
    for _ in range(BORNE):
        neuves = []
        for x in formes:
            try:
                ph = physique(x)
            except (OSError, ValueError):
                return formes, False
            for y in (x.lower(), ntf(x), ntf(x, True), posixpath.normpath(x), ph):
                if y and y not in vues:
                    vues.add(y)
                    neuves.append(y)
        if not neuves:
            return formes, True
        formes.extend(neuves)
    return formes, False
def protected(cand):
    # CHAQUE FORME DE L ENSEMBLE, minusculisée (`protected_one` est défini sur la
    # forme minusculisée), union de refus ; ensemble instable : refus nommé.
    formes, stable = fermer(cand)
    for s in dict.fromkeys(x.lower().replace(chr(92), "/") for x in formes):
        rule = protected_one(s)
        if rule:
            return rule
    return "" if stable else "formes-instables"
def normalize(v):
    if not v:
        return ""
    t = str(v).replace(chr(92), "/")
    try:
        p = Path(t)
        cand = p if p.is_absolute() else Path(REPO) / p
        res = cand.resolve()
        try:
            t = res.relative_to(Path(REPO).resolve()).as_posix()
        except ValueError:
            t = res.as_posix()
    except Exception:
        # ANY failure falls back on the lexical form (T-00000784, pass 4): on
        # CPython <= 3.12 Path.resolve() raises RuntimeError on a symlink loop
        # (measured: 3.9, 3.11, 3.12 raise; 3.13, 3.14 return the path), which
        # crashed the whole judge for ONE pathological target. Class-wide catch,
        # as T-00000785 did for its twins; the verdict is the same on every
        # version, since 3.13+ already falls back on the unresolved path.
        pass
    while t.startswith("./"):
        t = t[2:]
    return t
def lit_prefix(t):
    m = re.search(r"[$" + chr(96) + "]", t)
    return t[:m.start()] if m else t
def outside(cand):
    return cand.startswith("/") or bool(re.match(r"^[A-Za-z]:", cand))
def tracked(cand):
    if not cand or outside(cand):
        return False
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", "--", cand],
            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
raw, sep, s = sys.stdin.read().partition(chr(0))
if not sep:
    raw, s = "", raw
STOP = set(" \t;&|(){}<>" + chr(96) + chr(10))
QCH = (chr(39), chr(34))
BSL = chr(92)
def fd_dup(w):
    # `>&word` duplicates a fd only when word is digits or `-` (`2>&1`, `>&-`,
    # `3>&4-`); any OTHER word is a FILE bash opens for stdout+stderr
    # (`printf y >& MARKER`, measured created) — T-00000698, third correction (M3).
    return re.fullmatch(r"[0-9]*-?", w) is not None
def opaque_end(text, pos):
    # End (exclusive) of the `${...}`, `$(...)` or backtick span opening at pos
    # on the RAW text, -1 when it does not close. Walked as an OPAQUE part of a
    # redirect target word so its literal LAST segment is still judged
    # (`${D}/MARKER`, `$(pwd)/MARKER` — T-00000698, third correction, M2): the
    # `{`, `(` and backtick members of STOP used to cut the word at `$`, leaving
    # nothing to compare. Braces and parentheses nest; a quoted span inside is
    # skipped whole; a backslash escapes the next character.
    n = len(text)
    if text[pos] == chr(96):
        end = text.find(chr(96), pos + 1)
        return -1 if end < 0 else end + 1
    if text[pos] != "$" or pos + 1 >= n or text[pos + 1] not in "{(":
        return -1
    open_ch = text[pos + 1]
    close_ch = "}" if open_ch == "{" else ")"
    depth = 0; i = pos + 1
    while i < n:
        c = text[i]
        if c == BSL:
            i += 2; continue
        if c in QCH:
            end = i + 1
            while end < n and text[end] != c:
                if c == chr(34) and text[end] == BSL:
                    end += 1
                end += 1
            i = end + 1; continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1
def marker_hits(text):
    # The NAME rule: `[(target as written, last segment folded, bare|quoted)]`
    # for every write-redirect target whose last segment names an arming
    # marker. Walks the heredoc-stripped RAW text with its own quote tracking,
    # because the scrubbed copy blanks a quoted target — precisely the form
    # this rule exists to see. Same operator grammar as the scan below; a `#`
    # opening a WORD skips to its line end, as bash does; `>&word` is a fd dup
    # only for digits or `-`, a file otherwise (fd_dup); a `${...}`, `$(...)`
    # or backtick span is walked opaquely inside the word (opaque_end); the last
    # segment must be literal (`$D/KICKOFF_REQUIRED`, `${D}/...`, `$(pwd)/...`
    # are judged on the name, `$NAME` and `${X}KICKOFF_REQUIRED` have nothing
    # to compare and pass).
    hits = []
    if not MARKERS:
        return hits
    n = len(text); i = 0; head = True
    while i < n:
        ch = text[i]
        if ch == BSL:
            i += 2; head = False; continue
        if ch in QCH:
            end = i + 1
            while end < n and text[end] != ch:
                if ch == chr(34) and text[end] == BSL:
                    end += 1
                end += 1
            if end >= n:
                i += 1; head = False; continue
            i = end + 1; head = False; continue
        if ch == "#" and head:
            j = text.find(chr(10), i)
            if j < 0:
                break
            i = j + 1; head = True; continue
        if ch != ">":
            # A `#` opens a comment only at the head of a WORD: after blank,
            # `;`, `&`, `|`, `(` or a newline — NEVER after `{`, `}`, `)` or a
            # backtick (`${#x}`, `$(pwd)#y`, a backtick then `#`: bash runs
            # them, measured). STOP as the head class read `echo ${#x} >
            # "…/MARKER"` as a comment, so it passed on Claude alone
            # (T-00000698, third correction, M1). A subshell `)#comment` is
            # now read as code: one refusal MORE at worst, as on the Python
            # hosts, never one less.
            i += 1; head = ch in " \t;&|(" + chr(10); continue
        if i > 0 and text[i - 1] == ">":
            i += 1; head = False; continue
        op_end = i + 2 if (i + 1 < n and text[i + 1] == ">") else i + 1
        if op_end < n and text[op_end] == "|":
            op_end += 1
        t = op_end
        while t < n and text[t] in " \t":
            t += 1
        if t < n and text[t] == "&":
            w = t + 1
            while w < n and text[w] in " \t":
                w += 1
            we = w
            while we < n and text[we] not in STOP:
                we += 1
            if fd_dup(text[w:we]):
                i = op_end; head = False; continue
            t = w
        word = []; quoted = False; te = t
        while te < n:
            c = text[te]
            if c in QCH:
                end = te + 1
                while end < n and text[end] != c:
                    if c == chr(34) and text[end] == BSL:
                        end += 1
                    end += 1
                if end >= n:
                    break
                word.append(text[te + 1:end]); quoted = True; te = end + 1; continue
            if c == BSL and te + 1 < n:
                word.append(text[te + 1]); te += 2; continue
            if c == "$" or c == chr(96):
                end = opaque_end(text, te)
                if end > 0:
                    word.append(text[te:end]); te = end; continue
            if c in STOP:
                break
            word.append(c); te += 1
        i = max(te, op_end); head = False
        last = "".join(word).replace(BSL, "/").rsplit("/", 1)[-1]
        # Le nom est comparé minusculisé PUIS replié NT (T-00000722), et le test
        # de littéralité porte sur CHAQUE candidat après son pli : le pli retire
        # le `$` de `MARKER::$DATA`, qui est le marqueur sous NTFS.
        for folded in (last.lower(), ntf(last)):
            if folded and lit_prefix(folded) == folded and folded in MARKERS:
                shown = text[t:te].replace("\t", " ").replace(chr(10), " ")
                hits.append((shown, folded, "quoted" if quoted else "bare"))
                break
    return hits
refused = []
n = len(s); i = 0
while i < n:
    ch = s[i]
    if ch == "<":
        i += 1; continue
    if ch != ">":
        i += 1; continue
    if i > 0 and s[i - 1] == ">":
        i += 1; continue
    op_end = i + 2 if (i + 1 < n and s[i + 1] == ">") else i + 1
    if op_end < n and s[op_end] == "|":
        op_end += 1
    t = op_end
    while t < n and s[t] in " \t":
        t += 1
    if t < n and s[t] == "&":
        w = t + 1
        while w < n and s[w] in " \t":
            w += 1
        we = w
        while we < n and s[we] not in STOP:
            we += 1
        if fd_dup(s[w:we]):
            i = op_end; continue
        t = w
    te = t
    while te < n and s[te] not in STOP:
        te += 1
    target = s[t:te]
    i = op_end
    if not target or "@" in target:
        continue
    prefix = lit_prefix(target)
    if not prefix.strip():
        continue
    cand = normalize(prefix)
    if not cand:
        continue
    if prefix.endswith(("/", chr(92))) and not cand.endswith("/"):
        cand += "/"
    # HOW the target was read, said per path in the refusal (T-00000698):
    # outside is tested FIRST, so a relative prefix that leaves the root
    # (../...) is outside and never relative; inside needs an ABSOLUTE prefix
    # under the root; everything else is relative.
    how = "outside" if outside(cand) else ("relative" if not outside(prefix.replace(chr(92), "/")) else "inside")
    if tracked(cand):
        refused.append(("git-tracked", cand, how)); continue
    if COMPLETE:
        rule = protected(cand)
        if rule:
            refused.append((rule, cand, how))
# ONCE PER TARGET: a marker already refused by its PATH above is not listed a
# second time by its name — the name rule only adds what the path clauses could
# not see (a cd, a quote, an expanded directory). Gated on COMPLETE like the
# protected clause: under the strict branch both are announced-off together.
named = set(p.replace(BSL, "/").rsplit("/", 1)[-1].lower() for _, p, _ in refused)
named |= set(ntf(n) for n in named)
if COMPLETE:
    for target, last, how in marker_hits(raw):
        if last in named:
            continue
        named.add(last)
        refused.append(("arming-marker-name", target, how))
sys.stdout.write("OK\n" if COMPLETE else "DEGRADED\n")
# CLOSED OUTPUT GRAMMAR (T-00000784, pass 2): the sentinel, then one
# rule<TAB>path<TAB>how line per refusal. A TAB, newline or carriage return
# INSIDE a path (a quoted target can carry one) would make a line outside the
# grammar, which the reader refuses as a breakdown under the wrong rule: each
# becomes a space, as in the rm/mv pass.
for rule, path, how in refused:
    path = path.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    sys.stdout.write(rule + "\t" + path + "\t" + how + "\n")
') || REDIR_RC=$?
# CAPTURE EN LISTE AND-OR (T-00000784, passe 2) : la forme `X=$(…); X_RC=$?` de
# la passe 1 sortait avec le code du juge sous un errexit hérité (mesuré) ; un
# `||` n'est jamais coupé par errexit. Seconde défense, derrière la remise à
# zéro de tête. Chaque branche dit SA cause, dans cet ordre : rc non nul ;
# sortie MUETTE — rien sur une commande non vide, ce qu'atteignent la cale
# REDEMPTY et un module qui masque la stdlib dans le cwd en sortant 0 lui-même
# ((z11b) ; un `pathlib.py` ORDINAIRE lève une ImportError bruyante, rc 1, et
# prend la première branche) ; puis, ligne à ligne, la grammaire ci-dessous.
[ "$REDIR_RC" -eq 0 ] || redirect_stage_down "the python judge exited $REDIR_RC while reading a redirect target"
if [ -n "$SCRUBBED" ] && [ -z "$REDIR" ]; then
  redirect_stage_down "the python judge exited 0 but printed nothing for a non-empty command — a silent exit"
fi
# LA SORTIE EST UNE GRAMMAIRE FERMÉE, VALIDÉE LIGNE À LIGNE (T-00000784, passe
# 2 — exec-critic NO_GO @ e69aa011, reproduit). Ligne 1 : EXACTEMENT `OK` ou
# `DEGRADED` (L-00000308 dit « exit non nul OU première ligne absente » : une
# première ligne étrangère EST une absence). Chaque ligne suivante : EXACTEMENT
# trois champs, règle et chemin non vides, `how` dans l'ensemble fermé que le
# programme émet — outside, relative, inside pour les clauses de chemin, bare,
# quoted pour la règle du nom (la règle, elle, n'est PAS un vocabulaire fermé :
# protected() rend un préfixe ou un glob lu dans protect-paths.sh). La passe 1
# lisait `OK` tout ce qui n'était pas `DEGRADED`, et toute ligne suivante comme
# une cible : un module masquant qui IMPRIME puis sort 0 faisait passer
# `> KICKOFF_REQUIRED` en silence, et un `subprocess.py` qui imprime à l'import
# faisait lire `OK` comme une cible refusée — `( (OK, ))`, sous la mauvaise
# règle. POURQUOI UNE GRAMMAIRE ET NON UN JETON SECRET : un module qui s'exécute
# DANS le juge peut aussi lire et recopier un jeton ; le cas accidentel — du
# bruit avant, pendant ou après la sortie du juge — est fermé par la grammaire,
# et un bruit n'y peut qu'AJOUTER un refus, jamais en retirer un. BORNES, dites
# (la seconde relevée par l'exec-critic, passe 3) : une ligne FORGÉE exactement
# à la forme d'un refus serait lue comme une cible de plus — un refus en trop ;
# mais un module qui FORGE la sortie ENTIÈRE — la sentinelle `OK` seule, puis
# sortie 0 — CACHE toutes les cibles (mesuré sur a342b9bd : `> KICKOFF_REQUIRED`
# rc 0), et un `DEGRADED` forgé rend fausse l'annonce « git-tracked redirect
# writes are still guarded » plus bas. L'exécution de code DANS le juge est hors
# du modèle de cette lecture ; le vecteur cwd / PYTHONPATH qui la permet est
# T-00000789 (`-I` / `-P`). Le retour chariot final
# est retiré des trois champs : python écrit en mode texte, donc en CRLF sous
# Windows ((z20)), et la seule ligne où il tombe dépend du nombre de champs.
redir_first=1
while IFS="$(printf '\t')" read -r rr_rule rr_path rr_how; do
  case "$rr_how" in
    *"$PY_CR") rr_how="${rr_how%?}" ;;
  esac
  case "$rr_path" in
    *"$PY_CR") rr_path="${rr_path%?}" ;;
  esac
  case "$rr_rule" in
    *"$PY_CR") rr_rule="${rr_rule%?}" ;;
  esac
  if [ "$redir_first" -eq 1 ]; then
    redir_first=0
    [ -z "$rr_path$rr_how" ] || redirect_stage_down "the python judge exited 0 but its sentinel line is missing or malformed"
    case "$rr_rule" in
      OK) ;;
      DEGRADED) REDIR_DEGRADED=1 ;;
      *) redirect_stage_down "the python judge exited 0 but its sentinel line is missing or malformed" ;;
    esac
    continue
  fi
  case "$rr_how" in
    outside|relative|inside|bare|quoted) ;;
    *) redirect_stage_down "the python judge exited 0 but printed a line outside its output grammar (rule, path, how)" ;;
  esac
  if [ -z "$rr_rule" ] || [ -z "$rr_path" ]; then
    redirect_stage_down "the python judge exited 0 but printed a line outside its output grammar (rule, path, how)"
  fi
  REDIR_REFUSED="${REDIR_REFUSED:+$REDIR_REFUSED, }$rr_path ($rr_rule, $rr_how)"
done <<EOF
$REDIR
EOF
fi
if [ "$REDIR_DEGRADED" -eq 1 ]; then
  echo "COVERAGE DEGRADED: safe-bash redirect — the protected-path patterns could not be read from protect-paths.sh; git-tracked redirect writes are still guarded, but the protected-path clause is OFF for this call, the arming-marker-name clause with it." >&2
fi

# --- Étage 1.5 : DÉVELOPPER les accolades, comme bash (T-01M5D6XS2S) ----------
# T-01M53RGW, T-01M53HV4 : `{git,reset,--hard}`, `{git,branch,-D} wt/x`,
# `sudo {git,} reset --hard`, `git diff --{output=AGENTS.md,}`, `{rm,-rf} src`,
# `git reset --{h..h}ard` passaient sur les trois hôtes — l'étage 2 coupait le
# mot à la première accolade et ne lisait pas au-delà. bash développe AVANT
# d'exécuter ; la garde le fait donc aussi, sur le texte EXÉCUTABLE seul (après
# les étages 0.5 et 1 : une accolade citée est déjà ` @@ `, un corps de heredoc
# cité est déjà blanchi), et l'étage 2 lit le résultat. Sont développées une
# LISTE `{a,b}` (virgule hors accolade imbriquée) et une SÉQUENCE `{x..y[..n]}`
# d'entiers ou d'une lettre seule ; une expansion de paramètre entre accolades
# et une accolade échappée ne le sont jamais, comme pour bash. Une accolade qui n'est ni l'une ni l'autre (`{x}`,
# `@{-1}`, `${x:-{y}}`) reste, et l'étage 2 s'y COUPE comme avant (bc23, bc28,
# bc31, garde 7).
# BORNE : 256 mots par mot, 1024 par commande. Au-delà — ou pour un mot
# d'accolade qui porte un segment cité (`{git,'reset'}`, illisible ici) — le mot
# reste tel quel, et la commande est REFUSÉE (règle brace-expansion-unread) si
# son segment nomme git, rm, find ou xargs, ou si ce mot tient le mot de
# commande ou un mot qui le précède (`{r{m,},{1..300}} -rf src`, C15) ;
# sinon elle passe (`echo {1..300}`). Le refus est porté par une ligne
# sentinelle (octet \037) que l'awk lit en dernière ligne ; une charge qui la
# forgerait ne fait qu'AJOUTER un refus.
# Panne de l'étage (rc non nul, ou sortie vide sur une entrée non vide) :
# annoncée, exit 0, comme les étages 0.5 et 1. Zéro coût sans `{`.
# LA COUPE TELLE QU'ÉCRITE RESTE LUE (T-01M5GFV9CE). Développer ne vaut que si
# l'étage lit le segment comme bash : `git branch -D {a,b} \; wt/x`, `… w?/x`,
# `… <(echo) wt/x`, `… {V..a..6}wt/x` passaient rc 0 une fois développés (la
# coupe `{` qui comptait `wt/` avait disparu). Le texte développé est donc gardé,
# et le segment GROSSIER (même coupe que COARSE, plus bas) d'un mot développé
# n'est FIABLE que si l'expansion est exacte (ni lettre de séquence hors
# [A-Za-z], ni `+` dans une séquence entière), si son texte, guillemets compris,
# tient dans un jeu FERMÉ de caractères (SAFE : lettres ASCII, chiffres, blanc,
# tabulation, `{},._/@:=+%#<>&`, apostrophe, guillemet, `-`) et si chaque segment
# cité qu'il porte est, par la table de l'étage 1 PROUVÉE, entre apostrophes ou
# entre guillemets simples (type 2 ou 3), sur une ligne, hors dollar-guillemet
# (traduction de locale), de contenu
# dans SAFE. Un segment NON fiable est recopié TEL QU'ÉCRIT (préfixe `sudo`,
# `FOO=1`, `then` compris ; chaque ` @@ ` changé en `_` sans ses blancs, pour ne
# pas décaler la table de END ni détacher la citation de son mot) en ligne propre après le texte développé : l'étage 2 s'y
# coupe au `{` et compte `wt/`, comme avant le développement. Faux positifs
# NOMMÉS, fail-closed : `(git branch -D {a,b})`, `git branch -D {a,b} x[1]`,
# `{a,b} ~x`, `{+1..2}`, `{Z..a}`, un dollar-guillemet dans le segment, et, plus strict que
# les hôtes python, `"w<TAB>t/x"`. BORNE : SAFE est choisi à la main, sans
# preuve que l'étage 2 lise comme bash tout segment fait de ces caractères.
# La table arrive sur STDIN, devant le texte et close par une ligne sentinelle
# (\037TABLE-END) — jamais par l'environnement ni argv, qu'une charge d'un Mo
# ferait échouer (E2BIG). En-tête et CHAQUE ligne sont validés (2 et 7
# colonnes, la 7e posée par la garde 8) ; une ligne non conforme, un compte faux ou un `@@` littéral : la
# correspondance n'est pas prouvée et aucun segment cité n'est fiable ; sentinelle
# absente : refus brace-expansion-unread. Le texte n'est jamais raccourci.
SPANTAB=""
case "$SCRUBBED" in
  *"@@"*)
    SPANTAB=$(printf '%s' "$HEREFREE" | "$PY" -c "$SCRUB_PY" table) || degraded "the quote table (stage 1, table mode) failed"
    ;;
esac
BRACED="$SCRUBBED"
case "$SCRUBBED" in
  *"{"*)
    SPANHEAD=$SPANTAB
    [ -n "$SPANHEAD" ] || SPANHEAD=$(printf '0\t1')
    BRACED=$(printf '%s\n\037TABLE-END\n%s' "$SPANHEAD" "$SCRUBBED" | "$PY" -c '
import sys, re, bisect
BS = "\x5c"
NL = "\x0a"
MARK = chr(31) + "BRACE-UNREAD"
WORD = 256
TOTAL = 1024
HEADS = set(["git", "rm", "find", "xargs"])
# N3 (2e passe) : la table d enveloppes de l étage 2 (wrap), plus chrt, taskset,
# builtin ; les mots réservés ; une durée ou un nombre derrière une enveloppe
# (`timeout 5`, `chrt -i 0`, `taskset 1`) ; les options à valeur, `-S` compris.
ENVS = set("sudo doas env command exec eval time nohup nice ionice stdbuf timeout xargs watch parallel setsid chrt taskset builtin".split())
RESERVED = set("! { if then elif else do while until coproc".split())
ENVVAL = set("-u -g -n -c -C -D -p -r -t -U -T -P -a -h -S -s -k --user --group --chdir --unset --argv0 --adjustment --prompt --split-string --signal --kill-after --class --classdata".split())
NUMERIC = re.compile("^(0[xX][0-9a-fA-F]+|[0-9][0-9.]*[smhd]?)$")
CUT = re.compile("([ \t;&|()<>" + NL + "\x60]+)")
SEGCUT = set(";&|()" + NL + "\x60")
ASSIGN = re.compile("^[A-Za-z_][0-9A-Za-z_]*=")
SEQ_INT = re.compile("^([+-]?[0-9]+)[.][.]([+-]?[0-9]+)(?:[.][.]([+-]?[0-9]+))?$")
SEQ_CHR = re.compile("^([A-Za-z])[.][.]([A-Za-z])(?:[.][.]([+-]?[0-9]+))?$")
class Over(Exception):
    pass
def table(w):
    # F7 (passe de correction) : UNE passe à pile par mot — accolade fermante
    # et virgules de premier niveau de chaque accolade ouvrante — au lieu d un
    # balayage depuis chaque `{` (quadratique).
    match = {}
    commas = {}
    stack = []
    k = 0
    n = len(w)
    while k < n:
        c = w[k]
        if c == BS:
            k += 2
            continue
        if c == "$" and k + 1 < n and w[k + 1] == "{":
            j = w.find("}", k + 2)
            if j < 0:
                break
            k = j + 1
            continue
        if c == "{":
            stack.append(k)
            commas[k] = []
        elif c == "}":
            if stack:
                match[stack.pop()] = k
        elif c == "," and stack:
            commas[stack[-1]].append(k)
        k += 1
    return match, commas
def sequence(inner):
    m = SEQ_INT.match(inner) or SEQ_CHR.match(inner)
    if m and any(g and len(g.lstrip("+-")) > 9 for g in m.groups()):
        raise Over()
    m = SEQ_INT.match(inner)
    if m:
        # T-01M5GFV9CE : un `+` dans une séquence entière n est pas développé
        # comme bash le développe ; le résultat reste, le segment n est pas fiable.
        if "+" in inner:
            FL["inexact"] = True
        a = int(m.group(1))
        b = int(m.group(2))
        step = abs(int(m.group(3))) if m.group(3) else 1
        step = step or 1
        if abs(b - a) // step + 1 > WORD:
            raise Over()
        width = 0
        for g in (m.group(1), m.group(2)):
            digits = g.lstrip("+-")
            if len(digits) > 1 and digits[0] == "0":
                width = max(len(m.group(1)), len(m.group(2)))
        sign = 1 if b >= a else -1
        return [str(v).zfill(width) for v in range(a, b + sign, sign * step)]
    m = SEQ_CHR.match(inner)
    if m:
        a = ord(m.group(1))
        b = ord(m.group(2))
        step = abs(int(m.group(3))) if m.group(3) else 1
        step = step or 1
        sign = 1 if b >= a else -1
        # T-01M5GFV9CE : bash rend tel quel un caractère hors [A-Za-z] d une
        # plage de lettres (`{V..a}` passe par `[`, `\`, `]`…) ; la sortie `_`
        # reste, et le segment n est pas fiable.
        chars = [chr(v) for v in range(a, b + sign, sign * step)]
        if not all(("A" <= c <= "Z") or ("a" <= c <= "z") for c in chars):
            FL["inexact"] = True
        return [c if c.isalpha() else "_" for c in chars]
    return None
def expand(w, lo, hi, match, commas):
    i = lo
    while i < hi:
        c = w[i]
        if c == BS:
            i += 2
            continue
        if c == "$" and i + 1 < hi and w[i + 1] == "{":
            j = w.find("}", i + 2, hi)
            if j < 0:
                return [w[lo:hi]]
            i = j + 1
            continue
        if c == "{":
            j = match.get(i, -1)
            if i < j < hi:
                items = None
                if commas[i]:
                    items = []
                    cuts = [i] + commas[i] + [j]
                    for a, b in zip(cuts, cuts[1:]):
                        items.extend(expand(w, a + 1, b, match, commas))
                        if len(items) > WORD:
                            raise Over()
                else:
                    items = sequence(w[i + 1:j])
                if items is not None:
                    tail = expand(w, j + 1, hi, match, commas)
                    if len(items) * len(tail) > WORD:
                        raise Over()
                    return [w[lo:i] + x + y for x in items for y in tail]
        i += 1
    return [w[lo:hi]]
def base(w):
    b = w[1:] if w.startswith(BS) else w
    b = b.lower().split("/")[-1]
    return b[:-4] if b.endswith(".exe") else b
# T-01M5GFV9CE : la table de l étage 1 précède le texte, close par la PREMIÈRE
# ligne sentinelle (aucune ligne de table n en porte : chr(31) y est `multi` ou
# refusé en ANSI-C). Le texte commence après elle et n est jamais raccourci.
allin = sys.stdin.read()
tab, sep, data = allin.partition(NL + chr(31) + "TABLE-END" + NL)
NOFRAME = not sep
FL = {"inexact": False}
SAFE = re.compile("[A-Za-z0-9 \t{},._/@:=+%#<>&" + chr(39) + chr(34) + "-]*")
COARSE = re.compile("[;" + NL + "]+|(?<![<>])(?!&>)[&|]+")
HDR = re.compile("[0-9]+\t[01]")
ROW = re.compile("[0-3]\t[01]\t[01]\t[01]\t[^\t]*\t[01]\t[01]")
tlines = tab.split(NL)
ROWS = [r.split("\t") for r in tlines[1:]]
PROVEN = (not NOFRAME and HDR.fullmatch(tlines[0]) is not None
          and tlines[0].split("\t")[1] == "0"
          and tlines[0].split("\t")[0] == str(len(ROWS))
          and all(ROW.fullmatch(r) is not None for r in tlines[1:]))
QT = sum(1 for ln in data.split(NL) for x in ln.split() if x == "@@")
PROVEN = PROVEN and QT == len(ROWS)
QB = [0]
COPIES = []
def span_ok(i):
    # colonnes : type, collé à gauche, collé à droite, multi, contenu, locale, et la 7e de la
    # garde 8 (ouvre une substitution entre guillemets doubles), non lue ici : un tel segment
    # porte un `$` ou un backtick, que la règle des noms compte déjà comme wt/
    if not PROVEN or i >= len(ROWS):
        return False
    r = ROWS[i]
    return r[0] in ("2", "3") and r[3] == "0" and r[5] == "0" and SAFE.fullmatch(r[4]) is not None
used = 0
unread = False
out = []
def braced_line(line):
    global used, unread
    bounds = [0]
    for mm in COARSE.finditer(line):
        bounds += [mm.start(), mm.end()]
    bounds.append(len(line))
    cseg = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2)]
    starts = [s for s, _ in cseg]
    untrusted = set()
    expanded_in = set()
    parts = CUT.split(line)
    offs = []
    o = 0
    for x in parts:
        offs.append(o)
        o += len(x)
    segs = [[]]
    for k in range(len(parts)):
        if k % 2 == 1:
            if set(parts[k]) & SEGCUT:
                segs.append([])
        elif parts[k]:
            segs[-1].append(k)
    for seg in segs:
        # F5 (passe de correction) : le mot de commande saute les affectations,
        # les enveloppes (sudo, env, command, exec, nice, time, nohup, doas) et
        # leurs options — avec la valeur de celles qui en prennent une.
        cmd = -1
        inenv = False
        skipval = False
        for pos, k in enumerate(seg):
            w = parts[k]
            if skipval:
                skipval = False
                continue
            if ASSIGN.match(w) or w in RESERVED:
                continue
            if base(w) in ENVS:
                inenv = True
                continue
            if inenv and w.startswith("-"):
                skipval = w in ENVVAL
                continue
            if inenv and NUMERIC.match(w):
                continue
            cmd = pos
            break
        names = any(base(parts[k]) in HEADS for k in seg)
        failed = False
        at_head = False
        for pos, k in enumerate(seg):
            w = parts[k]
            if "{" not in w:
                continue
            ok = True
            # F4 (passe de correction) : un mot dont une accolade reste ouverte
            # est coupé par un séparateur — une substitution `$(…)`, `<(…)`,
            # `$((…))`, un backtick, ou un segment cité (` @@ `) — que bash, lui,
            # garde DANS le mot (`{git,reset,--hard,$(true)}`) : illisible si
            # le séparateur qui le suit porte `(` ou un backtick, ou si un mot
            # suivant du segment porte la `}`.
            if w.count("{") > w.count("}"):
                nxt = parts[k + 1] if k + 1 < len(parts) else ""
                if "(" in nxt or "\x60" in nxt or any("}" in parts[x] for x in seg[pos + 1:]):
                    ok = False
            items = [w]
            if ok:
                # T-01M5D6XS2S, passe de correction F1 : AUCUNE exception ne sort
                # de cet étage vers la posture dégradée (exit 0, rien de jugé).
                # Rejet AVANT calcul (plus de 256 accolades dans le mot, nombre
                # de plus de 9 chiffres dans une séquence), et toute autre
                # exception (récursion, int géant…) rend le mot ILLISIBLE.
                try:
                    if w.count("{") > WORD:
                        raise Over()
                    match, commas = table(w)
                    FL["inexact"] = False
                    items = expand(w, 0, len(w), match, commas)
                    if used + len(items) > TOTAL:
                        raise Over()
                except Exception:
                    items = [w]
                    ok = False
            if not ok:
                failed = True
                if cmd < 0 or pos <= cmd:
                    at_head = True
                continue
            if items != [w]:
                # dernier segment qui commence avant le mot, en O(log n) (un
                # balayage par mot était quadratique). Aucun : la ligne entière
                # devient illisible (Over, rattrapé plus bas : brace-expansion-unread),
                # jamais un repli silencieux sur le segment 0.
                ci = bisect.bisect_right(starts, offs[k]) - 1
                if ci < 0:
                    raise Over()
                expanded_in.add(ci)
                if FL["inexact"]:
                    untrusted.add(ci)
                used += len(items)
                names = names or any(base(x) in HEADS for x in items)
                parts[k] = " ".join(items)
        if failed and (names or at_head):
            unread = True
    # T-01M5GFV9CE : un segment grossier dont un mot est développé et qui n est
    # pas FIABLE est recopié tel qu écrit, ` @@ ` changé en `_` SANS ses blancs :
    # la citation reste collée à ses voisins (`"src (v2)"/{a,b}.py` donne
    # `_/{a,b}.py`, jamais un pathspec `/` détaché, lu non scopé).
    for i, (s0, e0) in enumerate(cseg):
        st = line[s0:e0]
        nq = sum(1 for x in st.split() if x == "@@")
        ok = SAFE.fullmatch(st) is not None and all(span_ok(QB[0] + j) for j in range(nq))
        QB[0] += nq
        if i in expanded_in and (i in untrusted or not ok):
            COPIES.append(st.replace(" @@ ", "_"))
    return "".join(parts)
for line in data.split(NL):
    try:
        out.append(braced_line(line))
    except Exception:
        unread = True
        out.append(line)
text = NL.join(out + COPIES)
if NOFRAME:
    text = ""
    unread = True
if unread:
    text += NL + MARK
sys.stdout.write(text)
') || degraded "the brace expansion stage failed"
    if [ -n "$SCRUBBED" ] && [ -z "$BRACED" ]; then
      degraded "the brace expansion stage failed (empty output on a non-empty command)"
    fi
    ;;
esac

# --- Étage 2 : reconnaître la FORME EXÉCUTÉE ---------------------------------
# Un seul passage awk : les séparateurs shell deviennent un jeton `;` (ils ne
# sont PAS pliés en espaces — c'est justement l'information de position que
# l'ancienne normalisation détruisait), puis on marche les jetons en suivant un
# état « on est en position de commande ». Classes écrites en intervalles
# explicites plutôt qu'en `[[:space:]]` : CI tourne sur ubuntu, où awk est mawk.
#
# Verdicts imprimés, UN PAR LIGNE, dédupliqués, et TOUS ceux rencontrés — pas
# seulement le premier : les trois gardes sont indépendantes et l'une ne doit
# pas masquer l'autre. `rm -rf /tmp/x && git clean -fdx` doit tomber sur la
# liste blanche temp POUR le rm ET rester bloqué POUR le git clean ; l'ancien
# `exit` au premier verbe reconnu l'aurait laissé passer entièrement.
#   ROOT              — `rm -rf /` (racine exactement)
#   HIT               — rm/mv réel
#   RG <jeton>        — `rg` exécuté ; le jeton BRUT est rendu pour que la
#                       résolution soit testée sur ce qui serait vraiment lancé
#                       (`rg`, `rg.exe`, `/usr/bin/rg`) et non sur un nom deviné
#   GITWIPE <sous-cmd>— effacement git non scopé (restore, checkout, clean,
#                       reset --hard, stash)
#   GITOUT            — `git … --output[=f]` (garde 5, T-00000762)
#   GITPAGER          — `git grep -O` / `--open-files-in-pager` (garde 6)
#   GITHIDDEN         — une expansion NON CITÉE là où git lit sa sous-commande
#                       (`git $sub .`, `git $(…) …`) : bras fail-closed des
#                       gardes 3, 5 et 6 (T-00000762, décision 3)
#   GITHOOKS          — une commande git qui SAUTE les hooks du dépôt (garde 8,
#                       T-01M5C1AF6GB3ZRX5QF9SF6R80Y ; règle dans decide_git)
# Le corps awk ne porte AUCUNE apostrophe (il est tenu entre apostrophes bash)
# et aucun nom de fonction intégrée awk comme variable (sub, gsub, index,
# length, match, split, substr).
#
# LA MARCHE LIT DES UNITÉS, PLUS DES SÉPARATEURS (T-00000762, passe binôme).
# L'ancien gsub repliait `|;&(){}$<>` et le backtick en un `;` qui ROUVRAIT la
# position de commande, et ce n'était pas le côté sûr qu'il semblait : le mot
# suivant prenait la place de la commande et cachait le vrai verbe. `< list.txt
# rm -rf src/x`, `> out.txt rm -rf src/x`, `2>/dev/null rm -rf src/x`, `sudo $X
# rm -rf src/x` et `FOO=$x rm -rf src/x` passaient rc 0 sur les TROIS hôtes
# (mesuré). toklin() pose donc des MARQUEURS (octet \034, jamais dans la charge :
# \034 et \035 y sont d'abord remplacés) : `\034R` un opérateur de redirection,
# numéro de fd compris — le mot SUIVANT est sa cible, il ne prend pas la place ;
# `\034S` la substitution de commande, `\034P` celle de processus, `\034(` et
# `\034)` les parenthèses, et le backtick ouvrent ou ferment un CADRE dont la
# fermeture RESTAURE l'état interrompu ;
# `\035` remplace une expansion simple (`$x`, `$1`, `${x}`) DANS son mot — ni
# séparateur, ni commande (`FOO=\035` reste une affectation) ; un mot qui
# COMMENCE par elle, en position de commande, est une commande inconnue, donc la
# suite est lue comme une fenêtre d'enveloppe. Un `)` que rien n'a ouvert sur la
# LIGNE ouvre aussi cette fenêtre : l'étage 2 n'a pas besoin d'exactitude, il
# doit voir TOUT verbe que la passe par opérande pourrait juger (sinon celle-ci
# ne tourne pas), et la passe, elle, est exacte.
#
# LE PATHSPEC CITÉ EST LU (décision 1). Un segment cité est ` @@ ` ici ; pour
# `git checkout -- "."`, `git restore ":(top)"`, `git stash push -- "*"`, END
# lit sur le descripteur 3 la TABLE des segments cités que le programme de
# l'étage 1 imprime lui-même (SCRUB_PY, mode `table` ; T-01M5D6XS2S — elle
# remplace `rawspans`, un port awk de `scrub_spans` qui aurait dû suivre chaque
# règle neuve de l'étage 1) : le k-ième `@@` est le k-ième segment, avec son
# CONTENU et s'il est COLLÉ à un mot voisin (`--git-dir=
# "$d"` : un morceau du mot précédent, jamais une sous-commande). Cette
# correspondance n'est retenue que si elle est PROUVÉE — autant de segments que
# de `@@`, et aucun `@@` littéral dans la charge ; sinon un pathspec cité est lu
# comme une expansion non citée, donc LARGE (fail-closed). Elle n'est calculée
# que si la commande porte un `@@` : zéro coût sinon. Les OPTIONS et la
# SOUS-COMMANDE citées (`git "stash"`) ne sont pas lues : DIVERGENCE 7, nommée
# (décision 4) — sauf une citation ANSI-C entière, décodée comme bash la décode
# (dollar-apostrophe : -D, ou --hard écrit en \x2d, T-01M5D6XS2S). L'option de
# reset est lue depuis T-01M5D6XS2S (3e passe : `git reset "--hard"` refusé,
# voir mword), comme le mot de commande cité.
# LE DESCRIPTEUR 3 EST OUVERT PAR UN `exec` À PART, et refermé après : la même
# herestring collée à la commande awk, dans la substitution, fait échouer le
# parseur du SAST sur le fichier ENTIER (mesuré, fichier par fichier, comme le
# troisième heredoc plus bas) — `bash -n` l'acceptait.
# Statut capturé en liste AND-OR (T-00000784, passe 2), comme l'étage
# redirection : sous un errexit hérité, `X=$(…); X_RC=$?` sortait avec le code
# d'awk au lieu de l'annoncer ((z22)).
# La TABLE elle-même (SPANTAB) est calculée AVANT l'étage 1.5, qui la lit aussi
# (T-01M5GFV9CE) ; ce descripteur en porte la même valeur.
AWK_RC=0
# Garde 8 (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) : le descripteur 4 porte la charge HEREFREE, lue pour le
# prefixe d environnement.
exec 3<<< "$SPANTAB"
exec 4<<< "$HEREFREE"
VERDICTS=$(printf '%s\n' "$BRACED" | awk '
function note(v) { if (!(v in seen)) { seen[v] = 1; m++; out[m] = v } }

# toklin() : une ligne du texte NEUTRALISÉ, prête à découper sur les blancs.
# Ordre OBLIGATOIRE : `${…}` simple avant `$(`, `$(` et `<(` avant les
# expansions et les redirections, les redirections avant le repli de `|;&`.
function toklin(line) {
  sub(/\r$/, "", line)
  gsub(/[\034\035\036]/, "_", line)
  gsub(/[$] @@ /, "  @@ ", line)
  gsub(/[$][{][^}$`(]*[}]/, "\035", line)
  gsub(/[$][(]/, " \034S ", line)
  gsub(/[<>][(]/, " \034P ", line)
  gsub(/[$][A-Za-z_][A-Za-z0-9_]*/, "\035", line)
  gsub(/[$][0-9@*#?!$-]/, "\035", line)
  gsub(/[$]/, "\035", line)
  gsub(/[0-9]*(&>>|&>|<<<|<<-|<<|<>|>>|>&|<&|>[|]|>|<)/, " \034R ", line)
  gsub(/[|;&]/, " ; ", line)
  gsub(/[(]/, " \034( ", line)
  gsub(/[)]/, " \034) ", line)
  gsub(/`/, " \034` ", line)
  # Une accolade est un `;` pour la marche, mais END la retient (BR) : bash la
  # garde DANS le mot ou la developpe (`@{-1}`, `{wt/x,y}`), et decide_git le lit.
  gsub(/[{}]/, " \036 ", line)
  return line
}

# readspans() : la TABLE des segments cités, calculée par le programme de
# l étage 1 lui-même (SCRUB_PY, mode `table`) et lue sur le descripteur 3 —
# jamais un second port de `scrub_spans` (T-01M5D6XS2S : le port awk aurait dû
# suivre les citations ANSI-C, les substitutions dans "…" et les corps de
# heredoc ; deux reconnaisseurs du même texte dérivent). Ligne 1 : le nombre de
# segments, puis 1 si la charge porte un `@@` littéral. Puis une ligne par
# segment : ANSI-C décodé et lisible (QA), collé à gauche (QG), à droite (QD),
# multi-ligne, contenu, citation locale `$"…"`. Remplit QC et QL ; rend le nombre de segments lus, ou -1 si la
# correspondance ne peut pas être prouvée.
function readspans(   rl, hh, ff, k, want, at) {
  k = 0; want = -1; at = 1
  if ((getline rl < "/dev/fd/3") > 0) {
    split(rl, hh, "\t"); want = hh[1] + 0; at = (hh[2] != "0")
    while ((getline rl < "/dev/fd/3") > 0) {
      if (rl == "") continue
      split(rl, ff, "\t")
      k++
      QA[k] = (ff[1] == "1"); QK[k] = ff[1]; QG[k] = (ff[2] == "1"); QD[k] = (ff[3] == "1")
      QC[k] = (ff[4] == "1") ? "\n" : ff[5]
      QL[k] = (ff[6] == "1"); QO[k] = (ff[7] == "1")
    }
  }
  close("/dev/fd/3")
  if (at || k != want) return -1
  return k
}

# mword(j) : 3e passe de T-01M5D6XS2S. Le MOT que bash forme à partir du jeton j
# et des segments cités qui lui sont COLLÉS (`r"m"`, `r` + ANSI-C `m`,
# `--` + `hard` cité, `"git"`), guillemets retirés ; mend reçoit le dernier
# jeton consommé. Un morceau illisible (segment non prouvé, contenu à `$`,
# backtick ou antislash, multi-ligne) y est l expansion EXP : le mot n est
# alors pas substitué (voir walkline et decide_git).
function mpiece(k,   q) {
  if (t[k] != "@@") return t[k]
  if (!qv) return EXP
  q = qi[k]
  if (QK[q] == "1" || QK[q] == "2" || QK[q] == "3") return QC[q]
  return EXP
}
function glued(k) {
  if (!qv || k >= n || !gitword(t[k]) || !gitword(t[k + 1])) return 0
  return ((t[k] == "@@" && QD[qi[k]]) || (t[k + 1] == "@@" && QG[qi[k + 1]]))
}
function mword(j,   s, k) {
  s = mpiece(j); k = j
  while (glued(k)) { k++; s = s mpiece(k) }
  mend = k
  return s
}

# decide_rm() : un verbe destructeur a été reconnu au jeton idx. Distingue la
# forme catastrophique `rm -rf /` — RACINE EXACTEMENT, pas tout chemin absolu :
# lancien préfixe `rm -rf /*` lisait `rm -rf /tmp/x` comme catastrophique au
# lieu de le laisser tomber sur la liste blanche temp plus bas.
function decide_rm(idx, verb,   j, sawr, sawf, root) {
  root = 0
  if (verb == "rm") {
    sawr = 0; sawf = 0
    for (j = idx + 1; j <= n; j++) {
      if (t[j] == "") continue
      if (substr(t[j], 1, 1) == "-") {
        if (index(t[j], "r") > 0 || index(t[j], "R") > 0) sawr = 1
        if (index(t[j], "f") > 0) sawf = 1
        continue
      }
      if (t[j] == "/" && sawr && sawf) root = 1
      break
    }
  }
  note(root ? "ROOT" : "HIT")
}

# decide_git() : `git` est en position de commande au jeton idx. On lit SA
# sous-commande puis SES opérandes, jusquau prochain séparateur.
#
# LA GARDE 3 EST BORNÉE À LABSENCE DE CHEMIN. `git restore src/foo.ts` reste
# permis — geste scopé, dont lauteur sait ce quil défait. Ce qui est refusé,
# cest la forme qui prend TOUT : `.`, `./`, `:/`, `--all`, et tout `git clean`
# (qui na pas de forme inoffensive du point de vue du travail non suivi).
# `git restore --staged <chemin>` ne touche QUE lindex, donc ne détruit aucun
# travail : il reste permis même sur `.`, sauf si `--worktree` le ramène dans
# larbre.
# T-00000762 y ajoute, MÊME règle et même motif : `reset` avec un jeton
# `--hard` ; `stash` IMPLICITE ou `push` sans pathspec, et `save` toujours (il
# ne prend aucun pathspec). Un pathspec est tout jeton non-option après `push`
# ou après `--`, ou `--pathspec-from-file[=]` ; la valeur de `-m`/`--message`
# est SAUTÉE, sinon `-m @@` compterait comme pathspec ; un pathspec LARGE (`.`,
# `./`, `:/`) vaut refus. Jamais refusés : `stash list show pop apply drop
# clear branch create store`, `reset --soft --mixed --keep --merge` et
# `reset <commit> -- <chemin>`. PORTÉE GLOBALE, comme la règle checkout : ce
# texte ne dit pas où un `cd` ou un `-C` atterrira.
# Les options globales À VALEUR SÉPARÉE — `-C`, `-c`, `--git-dir`,
# `--work-tree`, `--namespace`, `--config-env` — sont sautées avec leur valeur,
# sans quoi `git -C repo restore .` ou `git --work-tree /x checkout .` ne
# seraient pas reconnus (la valeur était lue comme sous-commande). Une valeur
# qui serait un séparateur nest jamais sautée.
#
# GARDES 5 ET 6 (T-00000762), sur les MÊMES jetons et quelle que soit la
# sous-commande pour la 5 : un jeton `--output` ou `--output=…` avant `--` note
# GITOUT (exact : `--output-indicator-*` passe ; `-o` jamais, son sens change
# par sous-commande). Sous `grep` seul, un jeton long dont le nom (deux lettres
# au moins) ouvre `open-files-in-pager`, ou une grappe courte où `O` précède
# toute lettre à valeur `e f A B C m`, note GITPAGER ; la valeur dun `-e -f -A
# -B -C -m` isolé est sautée ; casse respectée.
#
# PASSE BINÔME (T-00000762). git accepte TOUTE abréviation non ambiguë dune
# option longue (mesuré, git 2.55 : `reset --h` efface comme `--hard`, `restore
# --w .` comme `--worktree`, `stash push --m wip` prend `wip` pour message ;
# `--pathspec-f` est ambigu et refusé, donc `--pathspec-fr` est la plus courte) :
# gitlong() les lit toutes. Un pathspec LARGE (broadspec) ne scope rien : `.`,
# `*`, `:/`, `:(top)`, `./.`, une magie dexclusion seule, et une expansion NON
# citée (elle se découpe, se globe, ou est vide). `--pathspec-from-file=-` (ou
# `-` en mot suivant) lit la liste sur un tube : non scopé. Une valeur qui est
# une expansion (`git -C $d …`) est sautée comme toute valeur ; une expansion
# là où git lit sa SOUS-COMMANDE note GITHIDDEN. `git clean` en DRY RUN (`-n`,
# `--dry-run` et ses abréviations, une grappe portant `n` avant `e`) ne détruit
# rien et nest plus refusé (décision 5) : cest le remède que le refus nomme.
function git_output(tok) {
  return (tok == "--output" || substr(tok, 1, 9) == "--output=")
}
function gitlong(tok, opt, shortest,   nm, eq) {
  if (substr(tok, 1, 2) != "--") return 0
  nm = substr(tok, 3)
  eq = index(nm, "=")
  if (eq > 0) nm = substr(nm, 1, eq - 1)
  return (length(nm) >= shortest && substr(opt, 1, length(nm)) == nm)
}
function gitword(x) { return (x != "" && x != ";" && substr(x, 1, 1) != MK) }
function qword(j) {
  if (t[j] != "@@") return t[j]
  if (!qv) return EXP
  return QC[qi[j]]
}
function broadspec(p,   c, mg, e) {
  if (index(p, EXP) > 0) return 1
  gsub(/\\/, "", p)
  if (substr(p, 1, 2) == ":(") {
    c = index(p, ")")
    if (c == 0) return 0
    mg = "," substr(p, 3, c - 3) ","
    gsub(/[ \t]/, "", mg)
    if (index(mg, ",exclude,") > 0) return 1
    p = substr(p, c + 1)
  } else if (substr(p, 1, 1) == ":") {
    e = 2
    while (e <= length(p) && index("/!^", substr(p, e, 1)) > 0) e++
    mg = substr(p, 2, e - 2)
    if (index(mg, "!") > 0 || index(mg, "^") > 0) return 1
    if (substr(p, e, 1) == ":") e++
    p = substr(p, e)
  }
  return (p ~ /^[.\/*]*$/)
}
# aliasval() : T-01M5D6XS2S (T-01M53HV4). Une valeur de configuration git qui
# DÉFINIT un alias (`alias.<x>=…`), ou qu on ne peut pas lire (expansion, segment
# cité non prouvé) : la sous-commande que git lancera est alors cachée. La
# valeur est lue telle qu écrite, ou à travers son segment cité (qword).
function aliasval(v, anywhere) {
  if (index(v, EXP) > 0) return 1
  v = tolower(v)
  if (anywhere) return (index(v, "alias.") > 0)
  return (substr(v, 1, 6) == "alias.")
}
function aliasword(j) {
  if (t[j] == "@@") return aliasval(qword(j), 0)
  return aliasval(t[j], 0)
}
# aliasasg(i) : une AFFECTATION en tête de commande (`GIT_CONFIG_KEY_<n>=…`,
# `GIT_CONFIG_PARAMETERS=…`, derrière `env` compris) qui définit un alias pour
# le git de CE segment. Valeur vide collée à un segment cité : celui-ci est la
# valeur.
function aliasasg(i,   eq, nm, v) {
  eq = index(t[i], "=")
  nm = substr(t[i], 1, eq - 1)
  if (nm != "GIT_CONFIG_PARAMETERS" && nm !~ /^GIT_CONFIG_KEY_[0-9]+$/) return 0
  v = substr(t[i], eq + 1)
  if (v == "" && t[i + 1] == "@@") v = qword(i + 1)
  return aliasval(v, nm == "GIT_CONFIG_PARAMETERS")
}
function git_pager(tok,   nm, eq, k, ch) {
  if (substr(tok, 1, 2) == "--") {
    nm = substr(tok, 3)
    eq = index(nm, "=")
    if (eq > 0) nm = substr(nm, 1, eq - 1)
    return (length(nm) >= 2 && substr("open-files-in-pager", 1, length(nm)) == nm)
  }
  if (substr(tok, 1, 1) != "-") return 0
  for (k = 2; k <= length(tok); k++) {
    ch = substr(tok, k, 1)
    if (ch == "O") return 1
    if (index("efABCm", ch) > 0) return 0
  }
  return 0
}
# GARDE 8 (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) : une commande git qui SAUTE les hooks du depot. PORT, regle
# pour regle, de safe_bash_git.py (_hook_setting, _cluster, _config_read_option, _config_safe_option,
# _config_edits, _config_bypass) : memes verbes, memes noms d options, meme liste fermee. Ses variables
# lui sont PROPRES (hcmd, hb, hq, HALIAS, HSET, CW, CV, HV) : scmd et les autres gardes sont inchanges.
# Les mots sont lus A TRAVERS qword : un @@ prouve rend son contenu, sinon EXP (refus sous mention de
# git config, sous option de V, et en sous-commande) ; un segment cite COLLE reste saute (borne
# T-00001202, divergence de parite nommee). Le prefixe d environnement est lu en END, sur la charge sans
# corps de heredoc a delimiteur cite (Python lit ces corps : divergence nommee).
# hookset() : la CLE core.hookspath se replie, la VALEUR .githooks reste EXACTE (git garde sa casse :
# .GITHOOKS est un autre repertoire sur un disque sensible a la casse).
function hookset(v,   f, eq) {
  f = tolower(v)
  eq = index(v, "=")
  if (index(f, "alias.") > 0) HALIAS = 1
  if ((index(f, "hookspath") > 0 && !(eq > 0 && substr(f, 1, eq - 1) == "core.hookspath" && substr(v, eq + 1) == ".githooks")) || index(f, "include") > 0) HSET = 1
}
# hcluster() : 1 si `n` est lu avant une lettre a valeur, 2 si la grappe FINIT sur une lettre a valeur
# separee (la valeur est le mot suivant), 0 sinon ; commit et am seuls.
function hcluster(w, verb,   sep, opt, k, ch) {
  sep = (verb == "commit") ? "FmcCtU" : "Cp"
  opt = (verb == "commit") ? "uS" : "S"
  for (k = 2; k <= length(w); k++) {
    ch = substr(w, k, 1)
    if (index(opt, ch) > 0) return 0
    if (index(sep, ch) > 0) return (k == length(w)) ? 2 : 0
    if (ch == "n") return 1
  }
  return 0
}
function cfgread(w,   nm, eq) {
  if (w == "-l") return 1
  if (substr(w, 1, 1) == "-" && substr(w, 2, 1) != "-" && length(w) > 2) return (w ~ /^-[zl]+$/ && index(w, "l") > 0)
  if (substr(w, 1, 2) != "--") return 0
  nm = substr(w, 3)
  eq = index(nm, "=")
  if (eq > 0) nm = substr(nm, 1, eq - 1)
  if (nm == "get" || nm == "li" || nm == "lis" || nm == "list") return 1
  return (length(nm) >= 5 && substr(nm, 1, 4) == "get-" && index(" get-all get-regexp get-urlmatch get-color get-colorbool", " " nm) > 0)
}
function cfgsafe(w) {
  if ((w in cfgok) || cfgread(w)) return 1
  if (substr(w, 1, 7) == "--file=" || substr(w, 1, 7) == "--blob=" || substr(w, 1, 7) == "--type=") return 1
  if (substr(w, 1, 10) == "--default=" || substr(w, 1, 8) == "--value=" || substr(w, 1, 6) == "--url=") return 1
  return (length(w) > 2 && (substr(w, 1, 2) == "-f" || (substr(w, 1, 2) == "-t" && substr(w, 1, 3) != "-t-")))
}
function cfgedit(n,   i, w, nm, eq) {
  if (CW[1] == "edit" || CW[1] == "remove-section" || CW[1] == "rename-section") return 1
  for (i = 1; i <= n; i++) {
    w = CW[i]
    if (w == "-e") return 1
    if (substr(w, 1, 2) != "--") continue
    nm = substr(w, 3)
    eq = index(nm, "=")
    if (eq > 0) nm = substr(nm, 1, eq - 1)
    if (length(nm) >= 2 && substr("edit", 1, length(nm)) == nm) return 1
    if (length(nm) >= 3 && (substr("remove-section", 1, length(nm)) == nm || substr("rename-section", 1, length(nm)) == nm)) return 1
  }
  return 0
}
# cfgbypass() : git config de mots CW[1..n] qui peut desarmer les hooks (annexe 3 du plan).
function cfgbypass(n,   i, f, men, nv, lo, rd, sc0, se) {
  if (cfgedit(n)) return 1
  men = 0
  for (i = 1; i <= n; i++) {
    f = tolower(CW[i])
    if (index(f, EXP) > 0 || index(f, "hookspath") > 0 || index(f, "core.worktree") > 0 || index(f, "alias.") > 0 || index(f, "include") > 0) men = 1
  }
  if (!men) return 0
  nv = 0; lo = 1
  for (i = 1; i <= n; i++) {
    if (substr(CW[i], 1, 1) == "-") { if (CW[i] != "--local" && CW[i] != "--worktree") lo = 0; continue }
    if (i == 1 && CW[i] == "set") continue
    nv++; CV[nv] = CW[i]
  }
  if (nv == 2 && tolower(CV[1]) == "core.hookspath" && CV[2] == ".githooks" && lo) return 0
  rd = 0
  if (CW[1] == "get" || CW[1] == "list") { rd = 1; sc0 = 2; se = n }
  else {
    sc0 = 1; se = 0
    while (se < n && substr(CW[se + 1], 1, 1) == "-") se++
    for (i = 1; i <= se; i++) if (cfgread(CW[i])) rd = 1
  }
  for (i = sc0; i <= se; i++) if (substr(CW[i], 1, 1) == "-" && !cfgsafe(CW[i])) return 1
  return !rd
}
function cleanodd(tok,   c) {
  c = substr(tok, 1, 1)
  if (c == EXP || c == "*" || c == "?" || c == "[") return 1
  if (c != "-") return 0
  return (index(tok, EXP) > 0 || index(tok, BS) > 0 || index(tok, "*") > 0 || index(tok, "?") > 0 || index(tok, "[") > 0)
}
# qsubst(j) : 1 si la substitution ouverte au jeton j l est ENTRE guillemets doubles (QO, 7e colonne de la table :
# le morceau cite qui la precede s ouvre sur un guillemet sans le refermer) ; QEND recoit le jeton du morceau
# fermant, ou -1 si elle reste ouverte jusqu au bout de la ligne.
function qsubst(j,   m, d) {
  QEND = -1
  if (!qv || t[j - 1] != "@@" || !QO[qi[j - 1]]) return 0
  d = 1
  for (m = j + 1; m <= n; m++) {
    if (t[m] == BTK && t[j] == BTK) { d = 0; break }
    if (t[j] == OS && (t[m] == OS || t[m] == OPAR || t[m] == OP)) d++
    if (t[j] == OS && t[m] == CPAR && --d == 0) break
  }
  if (m > n) { QDEPTH = (t[j] == BTK) ? -1 : d; return 1 }
  if (t[m + 1] != "@@") return 0
  QEND = m + 1
  return 1
}
# hookcarry() : une substitution citee d un verbe de V restee OUVERTE en fin de ligne (PEND, verbe PH ; -1 pour un
# backtick) : sa fermeture est cherchee sur les lignes suivantes, puis hookrest lit les options apres elle.
function hookcarry(   j, start) {
  for (j = 1; j <= n; j++) {
    if (PEND < 0) { if (t[j] == BTK) break; continue }
    if (t[j] == OS || t[j] == OPAR || t[j] == OP) PEND++
    else if (t[j] == CPAR && --PEND == 0) break
  }
  if (j > n) return
  PEND = 0
  start = j + 1
  if (t[start] == "@@") start++
  hookrest(start)
}
# hookrest(j0) : les mots de la garde 8 apres une substitution citee fermee sur une autre ligne (verbe PH).
function hookrest(j0,   j, tok, hw, hk) {
  for (j = j0; j <= n; j++) {
    tok = t[j]
    if (tok == "") continue
    if (tok == RED) { if (gitword(t[j + 1])) j++; continue }
    if (tok == OS || tok == BTK) {
      if (qsubst(j)) { if (QEND < 0) { PEND = QDEPTH; return } j = QEND; continue }
      note("GITHOOKS"); return
    }
    if (tok == ";" || substr(tok, 1, 1) == MK || tok == "--") return
    if (tok == "@@" && qv && (QG[qi[j]] || QD[qi[j]])) continue
    hw = qword(j)
    if (index(hw, EXP) > 0 || gitlong(hw, "no-verify", 4)) { note("GITHOOKS"); return }
    if ((PH == "commit" || PH == "am") && substr(hw, 1, 1) == "-" && length(hw) > 1 && substr(hw, 2, 1) != "-") {
      hk = hcluster(hw, PH)
      if (hk == 1) { note("GITHOOKS"); return }
      if (hk == 2 && gitword(t[j + 1])) j++
    }
  }
}
function decide_git(idx,   j, tok, p, scmd, gotsub, staged, worktree, wipe, hard, spec, broad, smode, dd, gout, gpager, dry, hidden, k, ch, bdel, bforce, bwt, bexp, bglue, bq, halias, nocred, hcmd, hb, hq, hw, hk, cn) {
  gotsub = 0; scmd = ""; staged = 0; worktree = 0; wipe = 0; dry = 0; hidden = 0; halias = 0; nocred = 0
  bdel = 0; bforce = 0; bwt = 0; bexp = 0; bglue = 0
  hard = 0; spec = 0; broad = 0; smode = 0; dd = 0; gout = 0; gpager = 0
  hcmd = ""; hb = 0; hq = 0; cn = 0; HALIAS = 0; HSET = 0
  split("", CW)
  for (j = idx + 1; j <= n; j++) {
    tok = t[j]
    if (tok == "") continue
    # Une redirection est sautée AVEC sa cible ; `$(` ou un backtick avant la
    # sous-commande la cache ; tout autre séparateur ou cadre clôt les mots. Après un verbe
    # de V et avant `--`, la coupure vaut contournement : une option écrite après elle
    # reste non lue (`git push -u origin $(git branch --show-current) --no-verify`).
    if (tok == RED) { if (gitword(t[j + 1])) j++; continue }
    # Garde 8 apres la fusion de develop (T-01M5D6XS2S) : une substitution COLLEE entre deux morceaux cites
    # (`"wip $(date)"`) est lue entre guillemets, UN mot : sous un verbe de V elle ne coupe plus les mots, la
    # lecture reprend apres son morceau fermant ; ouverte jusqu au bout de la ligne (heredoc), les mots s arretent.
    if ((tok == OS || tok == BTK) && gotsub && !dd && (hcmd in hverify) && qsubst(j)) { if (QEND < 0) { PEND = QDEPTH; PH = hcmd; break } j = QEND; continue }
    if (tok == OS || tok == BTK) { if (!gotsub) hidden = 1; if (scmd == "reset" && !dd) hard = 1; if (scmd == "branch") bexp = 1; if (gotsub && !dd && (hcmd in hverify)) hb = 1; break }
    if (tok == ";" || substr(tok, 1, 1) == MK) { if (BR[j] && scmd == "branch") bwt = 1; break }
    # Un segment cité COLLÉ à un mot voisin en est un morceau (`--git-dir="$d"`).
    # 3e passe : une option de `reset` est lue GUILLEMETS RETIRÉS (`--` + `hard`
    # cité, `--hard` entre guillemets) quand ses morceaux sont lisibles —
    # DIVERGENCE 7 fermée pour reset seul ; `git branch` reste à T-00001202.
    if (gotsub && scmd == "reset" && (tok == "@@" || glued(j))) {
      bq = mword(j)
      if (bq != "" && index(bq, EXP) == 0) { tok = bq; j = mend }
    }
    if (tok == "@@" && qv && (QG[qi[j]] || QD[qi[j]])) { if (gotsub && scmd == "branch") bglue = 1; continue }
    if (!gotsub) {
      if (tok in gitval) {
        if (gitword(t[j + 1])) {
          if ((tok == "-c" || tok == "--config-env") && aliasword(j + 1)) halias = 1
          if (tok == "-c" || tok == "--config-env") {
            if (t[j + 1] == "@@" && !qv) HSET = 1
            else hookset(qword(j + 1))
          }
          j++
        }
        continue
      }
      if (substr(tok, 1, 13) == "--config-env=") hookset(substr(tok, 14))
      if (substr(tok, 1, 1) == "-") {
        if (git_output(tok)) gout = 1
        if (substr(tok, 1, 2) == "-c" && length(tok) > 2 && aliasval(substr(tok, 3), 0)) halias = 1
        if (substr(tok, 1, 13) == "--config-env=" && aliasval(substr(tok, 14), 0)) halias = 1
        continue
      }
      if (index(tok, EXP) > 0) { hidden = 1; break }
      scmd = tolower(tok); gotsub = 1
      hcmd = tolower(qword(j))
      if (index(hcmd, EXP) > 0) hq = 1
      continue
    }
    # `git stash #c` : un `#` en tête de mot ouvre un commentaire, qui clôt les
    # mots et les pathspecs — bash lance `git stash` NU (T-01M5D6XS2S,
    # T-01M55TRZ). Lu sous stash seul : sous branch, un commentaire reste lu
    # (faux positifs nommés de la garde 7).
    if (scmd == "stash" && substr(tok, 1, 1) == "#") break
    # smode du stash : 1 push, 2 implicite, 3 jamais refusé, 4 save, 5 inconnu
    # (git le refuse lui-même, rien ne part).
    if (scmd == "stash" && smode == 0) {
      if (substr(tok, 1, 1) != "-") {
        if (index(tok, EXP) > 0) { hidden = 1; break }
        if (tok == "push") smode = 1
        else if (tok == "save") smode = 4
        else if (tok in stashsafe) smode = 3
        else smode = 5
        continue
      }
      smode = 2
    }
    if (tok == "--" && !dd) { dd = 1; continue }
    if (!dd) {
      if ((scmd == "restore" || scmd == "checkout" || scmd == "stash") && gitlong(tok, "pathspec-from-file", 11)) {
        spec = 1
        p = ""
        if (index(tok, "=") > 0) p = substr(tok, index(tok, "=") + 1)
        else if (gitword(t[j + 1])) { j++; p = t[j] }
        if (p == "-") { wipe = 1; broad = 1 }
        continue
      }
      if (scmd == "grep" && (tok in grepval)) { if (gitword(t[j + 1])) j++; continue }
      if (scmd == "stash" && (tok == "-m" || (gitlong(tok, "message", 1) && index(tok, "=") == 0))) {
        if (gitword(t[j + 1])) j++
        continue
      }
      if (git_output(tok)) gout = 1
      if (scmd == "grep" && git_pager(tok)) gpager = 1
    }
    if (hcmd == "config") { CW[++cn] = qword(j); continue }
    if (hcmd in hverify) {
      if (dd) continue
      hw = qword(j)
      if (index(hw, EXP) > 0 || gitlong(hw, "no-verify", 4)) hb = 1
      else if ((hcmd == "commit" || hcmd == "am") && substr(hw, 1, 1) == "-" && length(hw) > 1 && substr(hw, 2, 1) != "-") {
        hk = hcluster(hw, hcmd)
        if (hk == 1) hb = 1
        if (hk == 2 && gitword(t[j + 1])) j++
      }
      continue
    }
    if (scmd == "branch") {
      if (!dd && substr(tok, 1, 1) == "-") {
        if (substr(tok, 2, 1) == "-") {
          if (gitlong(tok, "delete", 1)) bdel = 1
          if (gitlong(tok, "force", 4)) bforce = 1
        } else {
          for (k = 2; k <= length(tok); k++) {
            ch = substr(tok, k, 1)
            if (ch == "d" || ch == "D") bdel = 1
            if (ch == "f" || ch == "D") bforce = 1
          }
        }
        continue
      }
      bq = qword(j)
      if (index(bq, EXP) > 0 || index(bq, "$") > 0 || index(bq, "`") > 0) bexp = 1
      gsub(/\\/, "", bq)
      if (substr(tolower(bq), 1, 3) == "wt/" || index(bq, "@{") > 0) bwt = 1
      continue
    }
    if (scmd == "restore" || scmd == "checkout") {
      if (tok == "--staged" || tok == "-S") { staged = 1; continue }
      if (tok == "-W" || (!dd && gitlong(tok, "worktree", 1))) { worktree = 1; continue }
      if (tok == "--all") { wipe = 1; continue }
      if (substr(tok, 1, 1) == "-") continue
      if (broadspec(qword(j))) wipe = 1
      continue
    }
    # Un mot d option de `reset` qui porte une expansion NON citée (`$x`,
    # `--hard$x`) peut être --hard une fois développé : compté --hard
    # (T-01M5D6XS2S, T-01M53HV4 et T-01M55TRZ). Un mot qui ne COMMENCE ni par
    # elle ni par `-` (`HEAD~$n`) reste un commit.
    if (scmd == "reset") {
      if (!dd && (gitlong(tok, "hard", 1) || substr(tok, 1, 1) == EXP || (substr(tok, 1, 1) == "-" && index(tok, EXP) > 0))) hard = 1
      continue
    }
    if (scmd == "stash") {
      if (dd || (smode == 1 && substr(tok, 1, 1) != "-")) {
        spec = 1
        if (broadspec(qword(j))) broad = 1
      }
      continue
    }
    # T-01M5D6XS2S (T-01M56ZE6) : le crédit de dry run se lit OPTION PAR OPTION.
    # Le dernier de -n / --dry-run / --no-dry-run gagne ; -e / --exclude
    # consomme sa valeur, grappe comprise (`-fde -n` : -n est le motif) ; un mot
    # qui peut devenir une option une fois développé — expansion non citée,
    # antislash ou glob dans un mot `-…`, mot qui OUVRE sur une expansion ou un
    # glob — ôte TOUT crédit (nocred), la valeur de -e comprise.
    if (scmd == "clean" && !dd) {
      if (tok == "-e" || (gitlong(tok, "exclude", 1) && index(tok, "=") == 0)) {
        if (gitword(t[j + 1])) { j++; if (cleanodd(t[j])) nocred = 1 }
        continue
      }
      if (cleanodd(tok)) nocred = 1
      if (tok == "-n" || gitlong(tok, "dry-run", 1)) dry = 1
      else if (gitlong(tok, "no-dry-run", 4)) dry = 0
      else if (substr(tok, 1, 1) == "-" && substr(tok, 2, 1) != "-") {
        for (k = 2; k <= length(tok); k++) {
          ch = substr(tok, k, 1)
          if (ch == "e") {
            if (k == length(tok) && gitword(t[j + 1])) { j++; if (cleanodd(t[j])) nocred = 1 }
            break
          }
          if (ch == "n") dry = 1
        }
      }
    }
  }
  if (gout) note("GITOUT")
  if (gpager) note("GITPAGER")
  # Garde 8 : 2 de safe_bash_git ici, et HV (un verbe de V lu) pour le prefixe d environnement, lu en END.
  if (hcmd in hverb) HV = 1
  if (HALIAS || hq || ((hcmd in hverb) && (HSET || hb)) || (hcmd == "config" && cfgbypass(cn))) note("GITHOOKS")
  # Ce qui tournerait est inconnu : aucun verdict deffacement nest deviné.
  if (hidden) { note("GITHIDDEN"); return }
  # Un alias défini pour CE git (option `-c`/`--config-env`, ou affectation en
  # tête du segment, galias) cache sa sous-commande : même refus, son message.
  if (halias || galias) { note("GITALIAS"); return }
  # `xargs` en tête (gfed) : les opérandes viennent du tube — une liste lue sur
  # lentrée standard, donc LARGE, et un nom de branche venu de là compte wt/.
  if (gfed) {
    if (scmd == "restore" || scmd == "checkout") wipe = 1
    if (scmd == "stash") broad = 1
    if (scmd == "branch") bwt = 1
  }
  if (scmd == "branch") { if (bdel && bforce && (bwt || bexp || bglue)) note("GITBRANCHD"); return }
  if (scmd == "clean") { if (!dry || nocred) note("GITWIPE clean"); return }
  if (scmd == "reset") { if (hard) note("GITWIPE reset --hard"); return }
  if (scmd == "stash") {
    if (smode == 4 || (smode <= 2 && (!spec || broad))) note("GITWIPE stash")
    return
  }
  if (scmd != "restore" && scmd != "checkout") return
  if (!wipe) return
  if (scmd == "restore" && staged && !worktree) return
  note("GITWIPE " scmd)
}

# recognize() : le dispatch des gardes sur UN jeton reconnu en position de
# commande (git porte les gardes 3, 5 et 6). Le jeton BRUT accompagne `rg` (voir plus haut) ; rm/mv et git nen
# ont pas besoin, leur décision ne dépend pas de la résolution PATH.
function recognize(idx, base, raw) {
  # Une SONDE DE PRÉSENCE n est pas une exécution, et les trois gardes doivent la
  # laisser passer. Mesuré sur ce dépôt le 2026-08-06, sur la garde ELLE-MÊME :
  # `command -v rg` a été REFUSÉ, parce que `command` est une enveloppe et garde
  # donc la position de commande ouverte — la garde lisait un lancement là où la
  # commande demandait seulement si l outil existe. C était donc la commande de
  # DIAGNOSTIC de la garde que la garde bloquait, c est-à-dire le seul geste qui
  # permet de constater la panne qu elle décrit.
  # Pourquoi c est sûr, garde par garde : `command -v X` et `which X` IMPRIMENT un
  # chemin ou échouent, ils ne lancent jamais X — un `command -v rm` ne supprime
  # rien, un `which git` ne restaure rien, et une sonde `rg` ne peut pas fabriquer
  # le faux vide que la garde 2 combat, puisque sa SORTIE porte sur la présence et
  # non sur des occurrences. Le drapeau est remis à zéro à chaque séparateur, donc
  # `command -v rg && rg motif` reste bloqué sur son second segment : la sonde n
  # ouvre aucune fenêtre de contournement, elle ne couvre que son propre mot.
  if (probe) return
  if (base == "rm" || base == "mv") { decide_rm(idx, base); return }
  if (base == "rg") { note("RG " raw); return }
  if (base == "git") { decide_git(idx); return }
}
BEGIN {
  m = 0
  # Enveloppes : elles PRENNENT une commande, donc la position de commande
  # reste ouverte derrière elles — sans quoi `sudo rm x`, `xargs rm` et
  # `timeout 5 rm x` deviendraient des faux négatifs. `sh`/`bash` en sont
  # volontairement absents : leur charge utile est CITÉE, donc déjà neutralisée
  # par létage 1 (trou assumé, pin dans la suite).
  # chrt, taskset, builtin : T-01M5D6XS2S (2e passe) — `chrt -i 0 rm -rf src`
  # passait (mesuré, dès bfa51a8f) ; hors tables, comme timeout.
  split("sudo doas env command exec eval time nohup nice ionice stdbuf timeout xargs watch parallel setsid chrt taskset builtin", w, " ")
  for (i in w) wrap[w[i]] = 1
  # Mots-clés : `if [ x ]; then rm f; fi`, `for f in *; do rm $f; done` — sans
  # `then`/`do`, le rm nétait plus en position de commande et passait.
  split("if then elif else do while until ! coproc", k, " ")
  for (i in k) kw[k[i]] = 1
  # Sondes de PRESENCE (voir recognize()) : elles impriment un chemin ou echouent,
  # elles ne lancent jamais le nom sonde. `command` est absent de cette liste car
  # c est une enveloppe : seule sa forme -v/-V est une sonde.
  split("which type hash whence", p, " ")
  for (i in p) prb[p[i]] = 1
  # decide_git() : options globales git à VALEUR SÉPARÉE, sous-commandes de
  # stash jamais refusées, options à valeur de grep et de stash (T-00000762).
  split("-C -c --git-dir --work-tree --namespace --config-env", gv, " ")
  for (i in gv) gitval[gv[i]] = 1
  split("list show pop apply drop clear branch create store", ss, " ")
  for (i in ss) stashsafe[ss[i]] = 1
  split("-e -f -A -B -C -m", ge, " ")
  for (i in ge) grepval[ge[i]] = 1
  # Garde 8 : V, les six verbes a --no-verify, la liste fermee des options dune lecture pure.
  split("commit push merge rebase am pull cherry-pick revert", hv1, " ")
  for (i in hv1) hverb[hv1[i]] = 1
  split("commit push merge rebase am pull", hv2, " ")
  for (i in hv2) hverify[hv2[i]] = 1
  split("--local --global --system --worktree --show-origin --show-scope --show-names --name-only -z --null --includes --no-includes --fixed-value --bool --int --bool-or-int --bool-or-str --path --expiry-date --all --regexp -l", hv3, " ")
  for (i in hv3) cfgok[hv3[i]] = 1
  HV = 0
  MK = "\034"; EXP = "\035"; RED = "\034R"; OS = "\034S"; OP = "\034P"
  OPAR = "\034("; CPAR = "\034)"; BTK = "\034`"
  BS = "\\"
  # T-00001102 : TABLES FERMEES (options SANS valeur / A valeur separee) des six enveloppes dont on
  # PROUVE larite. Tout le reste est ambigu.
  split("env sudo doas command nohup time", et, " ")
  for (i in et) envt[et[i]] = 1
  etab_load("env", "- -i -0 --ignore-environment --null --debug --list-signal-handling --block-signal --default-signal --ignore-signal --", "-u -C -P -a --unset --chdir --argv0")
  etab_load("sudo", "-A -B -b -E -H -k -N -n -P -S -i -s --askpass --bell --background --preserve-env --set-home --reset-timestamp --login --non-interactive --preserve-groups --stdin --shell --no-update --", "-C -D -g -p -R -T -U -u -r -t --close-from --chdir --group --prompt --chroot --command-timeout --other-user --user --role --type")
  etab_load("doas", "-L -n -s --", "-C -u")
  etab_load("command", "-p --", "")
  etab_load("nohup", "--", "")
  etab_load("time", "-p --", "")
}
{ L[++nl] = $0 }
function etab_load(name, v0, v1,   a, b, i) {
  split(v0, a, " "); for (i in a) ev0[name, a[i]] = 1
  split(v1, b, " "); for (i in b) ev1[name, b[i]] = 1
}
function envbase(tok,   b) {
  b = tok
  sub(/^\\/, "", b)
  b = tolower(b)
  sub(/^.*\//, "", b)
  sub(/\.exe$/, "", b)
  return b
}
# scan_window(i) : T-00001102. Lenveloppe est au jeton i, en position de commande. On LIT la suite, sans rien
# modifier, pour savoir quel jeton sera la vraie commande. Rend 0 : rien a dire, la marche de base continue
# seule (aussi pour une enveloppe HORS tables : S1, inchange) ; -1 : fenetre AMBIGUE dune enveloppe de table (option hors table, valeur a expansion, charge opaque) ;
# k > 0 : git PROUVE en position de commande au jeton k (chaine de tables, aucune ambiguite).
# PIEGE MESURE : lire wrap[b] CREE la cle ; la lecture anticipee teste donc la VALEUR, jamais b in wrap.
function scan_window(i,   e, k, tok, nm, eq, b, amb, evn, lasta) {
  e = envbase(t[i])
  if (!(e in envt)) return 0
  amb = 0; evn = 0; lasta = 0
  for (k = i + 1; k <= n; k++) {
    tok = t[k]
    if (tok == "") continue
    if (tok == ";" || tok == CPAR) return amb ? -1 : 0
    if (substr(tok, 1, 1) == MK) return -1
    if (tok == "@@" && lasta) { lasta = 0; continue }
    lasta = 0
    if (evn) { evn = 0; if (index(tok, EXP) > 0) amb = 1; continue }
    if (tok == "@@") {
      if (qv && QL[qi[k]] && QK[qi[k]] == "3" && !QG[qi[k]] && !QD[qi[k]]) tok = QC[qi[k]]
      else return -1
    }
    if (substr(tok, 1, 1) == "-") {
      if ((e, tok) in ev0) continue
      if ((e, tok) in ev1) { evn = 1; continue }
      eq = index(tok, "=")
      if (substr(tok, 1, 2) == "--") {
        if (eq > 0) {
          nm = substr(tok, 1, eq - 1)
          if (((e, nm) in ev0) || ((e, nm) in ev1)) { if (index(tok, EXP) > 0) amb = 1; continue }
        }
      } else if (length(tok) > 2 && ((e, substr(tok, 1, 2)) in ev1)) {
        if (index(tok, EXP) > 0) amb = 1
        continue
      }
      amb = 1; continue
    }
    if ((e == "env" || e == "sudo") && tok ~ /^[A-Za-z_][0-9A-Za-z_]*=/) { lasta = 1; if (index(tok, EXP) > 0) amb = 1; continue }
    if (substr(tok, 1, 1) == EXP) return -1
    b = envbase(tok)
    if (b in envt) { e = b; continue }
    if (wrap[b]) return 0
    if (b == "git") return amb ? -1 : k
    return amb ? -1 : 0
  }
  return amb ? -1 : 0
}
# git_subpos(k) : T-00001102. Le jeton k est git. Rend lindice du jeton que git lira comme SOUS-COMMANDE (les options
# globales sont sautees, celles a valeur separee avec leur valeur, comme decide_git), ou 0 si elle est cachee.
function git_subpos(k,   j, tok) {
  for (j = k + 1; j <= n; j++) {
    tok = t[j]
    if (tok == "") continue
    if (tok == ";" || tok == "@@" || substr(tok, 1, 1) == MK) return 0
    if (tok in gitval) { if (gitword(t[j + 1])) j++; continue }
    if (substr(tok, 1, 1) == "-") continue
    return j
  }
  return 0
}
# walkline() : la marche dUNE ligne, sur t[1..n]. Une pile de CADRES (sp)
# sauvegarde cmdpos/wrapped/probe à louverture et les restaure à la fermeture ;
# la fermeture dune SUBSTITUTION ouverte en position de commande (`$(cmd) rm`)
# laisse une commande inconnue, donc une fenêtre denveloppe.
# findexec(i, raw) : T-01M5D6XS2S (T-01M55TRZ). Sous `find`, un mot qui PEUT être
# -exec, -execdir, -ok ou -okdir une fois lu par bash rouvre la position de
# commande : la primaire décitée (segment cité dont le contenu en est une, ou
# collé à un `-`), décodée (ANSI-C, déjà substituée), ou un mot `-…` qui porte
# une expansion ou un antislash (`-ex${x}ec`, `-\exec`, `-e\xec`). Fail-closed :
# un segment cité non prouvé (qv nul) compte aussi.
function findexec(i, raw,   c) {
  if (raw == "-exec" || raw == "-execdir" || raw == "-ok" || raw == "-okdir") return 1
  if (substr(raw, 1, 1) == "-" && (index(raw, EXP) > 0 || index(raw, BS) > 0)) return 1
  if (t[i] != "@@") return 0
  if (!qv) return 1
  c = QC[qi[i]]
  if (c == "-exec" || c == "-execdir" || c == "-ok" || c == "-okdir") return 1
  return (QG[qi[i]] && substr(t[i - 1], 1, 1) == "-") || (QD[qi[i]] && substr(c, 1, 1) == "-")
}
function walkline(   i, tok, raw, base, lastasg, r) {
  cmdpos = 1; wrapped = 0; probe = 0; skip = 0; sp = 0; lastasg = 0; gpos = 0; exm = 0; galias = 0; gfed = 0; cmdname = ""
  for (i = 1; i <= n; i++) {
    tok = t[i]
    if (tok == "") continue
    # `FOO="bar" rm x` : le segment cité est la VALEUR de laffectation.
    if (tok == "@@" && lastasg) continue
    lastasg = 0
    if (tok == ";") { cmdpos = 1; wrapped = 0; probe = 0; skip = 0; galias = 0; gfed = 0; cmdname = ""; continue }
    if (tok == RED) { skip = 1; continue }
    if (tok == OS || tok == OP || tok == OPAR || (tok == BTK && !(sp > 0 && sk[sp] == "bt"))) {
      sp++
      sc[sp] = cmdpos; sw[sp] = wrapped; sq[sp] = probe; sg[sp] = skip; sa[sp] = galias; sf[sp] = gfed; sn[sp] = cmdname
      sk[sp] = (tok == OS) ? "sub" : ((tok == OP) ? "proc" : ((tok == OPAR) ? "par" : "bt"))
      cmdpos = 1; wrapped = 0; probe = 0; skip = 0; galias = 0; gfed = 0; cmdname = ""
      continue
    }
    if (tok == CPAR || tok == BTK) {
      if (sp > 0) {
        cmdpos = sc[sp]; wrapped = sw[sp]; probe = sq[sp]; galias = sa[sp]; gfed = sf[sp]; cmdname = sn[sp]
        if (cmdpos && !sg[sp] && (sk[sp] == "sub" || sk[sp] == "bt")) { cmdpos = 0; wrapped = (wrapped == 2) ? 2 : 1 }
        sp--
      } else { cmdpos = 0; wrapped = 1 }
      skip = 0
      continue
    }
    # La cible dune redirection ne prend jamais la place de la commande.
    if (skip) { skip = 0; continue }
    # 3e passe : en position de commande, le mot est lu GUILLEMETS RETIRÉS
    # (`"rm"`, `r"m"`, `git` cité, `r` + ANSI-C `m`) quand chacun de ses morceaux
    # est lisible ; sinon il reste tel quel.
    if (cmdpos && (tok == "@@" || glued(i)) && tok !~ /^[A-Za-z_][0-9A-Za-z_]*=/) {
      mw = mword(i)
      if (mw != "" && index(mw, EXP) == 0) { tok = mw; i = mend }
    }
    raw = tok
    gsub(/\\/, "", raw)          # `\rm` et `r\m` contournent un alias, pas ce garde
    base = tolower(raw)
    sub(/^.*\//, "", base)       # /bin/rm -> rm
    sub(/\.exe$/, "", base)
    # T-00001102 : git PROUVE en position de commande derriere une chaine denveloppes de table : il est
    # juge (ici sil nest pas deja en position de commande) ; sa SOUS-COMMANDE rm|mv (git rm, git mv) nest plus
    # lue comme un rm|mv de la fenetre : exm. Tout autre rm|mv de la fenetre reste juge.
    if (i == gpos) {
      if (!cmdpos && !probe) decide_git(i)
      if (wrapped == 1) exm = git_subpos(i)
      gpos = 0
    }
    if (cmdpos) {
      recognize(i, base, raw)
      # Sonde de presence : ce qui SUIT est un NOM a resoudre, pas une commande a
      # lancer. `which rm` n efface rien, `type git` ne restaure rien.
      if (prb[base]) { probe = 1; cmdpos = 0; continue }
      # T-01M5D6XS2S (T-01M53HV4) : `xargs` en tête — seul, ou derrière une
      # chaîne d enveloppes de table — reste HORS tables, mais sa fenêtre est lue
      # comme AMBIGUË (wrapped 2) : git y est jugé, ses opérandes venant du tube
      # (gfed). Derrière une enveloppe hors tables (wrapped 3), trou S1 inchangé.
      if (base == "xargs" && wrapped != 3) { wrapped = 2; gfed = 1; continue }
      if (wrap[base]) { if (wrapped < 1) wrapped = 1; if (!(base in envt)) { if (wrapped == 1) wrapped = 3 } else if (wrapped != 3) { r = scan_window(i); if (r < 0) wrapped = 2; else if (r > 0 && wrapped == 1) gpos = r }; continue }     # enveloppe
      if (kw[base]) continue                        # mot-clé
      # `command -v X` / `command -V X` : seule cette forme de l enveloppe est une
      # sonde. Le drapeau meurt au separateur suivant, donc `command -v rg && rg x`
      # reste garde sur son second segment.
      if (wrapped && (raw == "-v" || raw == "-V")) { probe = 1; continue }
      if (raw ~ /^-/) continue                      # option DE lenveloppe
      if (raw ~ /^[A-Za-z_][0-9A-Za-z_]*=/) { lastasg = 1; if (aliasasg(i)) galias = 1; continue }  # FOO=bar rm x
      # `$X rm x`, `sudo $X rm x` : une expansion PREND la place de la commande,
      # inconnue — ce qui suit est lu comme sa fenêtre denveloppe. T-01M5D6XS2S :
      # fenêtre AMBIGUË (wrapped 2), comme `sudo $X git …` — git y est jugé
      # partout (`$X git branch -D wt/x` passait sur les trois hôtes).
      if (substr(raw, 1, 1) == EXP) { cmdpos = 0; wrapped = 2; continue }
      cmdpos = 0; cmdname = base                    # vraie commande, pas rm/mv
    } else {
      # `find … -exec rm {} \;` : -exec rouvre une position de commande, donc
      # les TROIS gardes y voient de nouveau clair. `-ok`/`-okdir` aussi.
      if (raw == "-exec" || raw == "-execdir" || raw == "-ok" || raw == "-okdir") { cmdpos = 1; continue }
      if (cmdname == "find" && findexec(i, raw)) { cmdpos = 1; continue }
      # Dans une fenêtre denveloppe on ne sait pas, en général, où sarrêtent SES
      # arguments (`sudo -u root rm`, `timeout 5 rm`, `nice -n 10 rm`) : on y
      # préfère le faux positif, cest-à-dire exactement la sémantique par
      # sous-chaîne de lancien garde, restreinte à ce seul cas. RÉSERVÉ À rm/mv,
      # délibérément : eux sont dangereux PARTOUT, le faux positif y est le
      # moindre mal. `rg` et `git restore` ne sont dangereux quEXÉCUTÉS, et
      # élargir leur garde ici bloquerait `sudo npm install rg` ou `sudo apt
      # install git`.
      # T-00001102 : pour les SIX enveloppes de TABLE (env, sudo, doas, command,
      # nohup, time), scan_window LIT larité de chaque option (tables fermées,
      # tirées des manuels). Chaîne PROUVÉE (chaque option en table, chaque
      # valeur un mot) : git y est en position de commande et jugé là, et sa
      # sous-commande rm|mv (exm) nest plus un rm|mv de la fenêtre. Chaîne NON
      # prouvable (option hors table, abréviation, grappe, valeur à expansion,
      # mot cité opaque) : wrapped == 2, git est jugé PARTOUT dans la fenêtre.
      # Une enveloppe HORS tables (timeout, nice, xargs, ionice, exec, eval…) ôte
      # la preuve à toute la chaîne (wrapped == 3) et laisse lancien régime :
      # trou S1 nommé et épinglé, `timeout 5 git reset --hard` et `nice -n 10
      # git restore .` passent encore. Rien nest dit couvert que les tables ne
      # prouvent pas. EXCEPTION, T-01M5D6XS2S : `xargs` EN TÊTE (seul, ou
      # derrière des enveloppes de table) ouvre une fenêtre AMBIGUË (wrapped 2,
      # gfed) — git y est jugé, ses opérandes venus du tube sont LARGES.
      if (wrapped == 2 && !probe && base == "git") decide_git(i)
      if (wrapped && !probe && (base == "rm" || base == "mv") && i != exm) decide_rm(i, base)
    }
  }
}
# END : chaque ligne est découpée UNE fois ; la table des segments cités nest
# lue sur le descripteur 3 que si la commande porte un `@@`, et elle nest
# retenue (qv) que si la correspondance est prouvée. Un segment en citation
# ANSI-C (dollar-apostrophe) NON collé, décodé en un mot lisible (QA), prend la
# place de son `@@` : bash le lit ainsi, option comprise (`git branch` suivi de
# -D écrit en ANSI-C, `\x2d\x2dhard`, `\055D`, la primaire -exec de find,
# T-01M5D6XS2S). Collé, ou indécodable, il reste opaque.
END {
  qtot = 0; hasgit = 0; qv = 0
  # La sentinelle de l étage 1.5 (accolades illisibles ou hors borne), toujours
  # en DERNIÈRE ligne : un verdict, jamais du texte à marcher.
  if (nl > 0 && L[nl] == "\037BRACE-UNREAD") { note("BRACEUNREAD"); nl-- }
  for (li = 1; li <= nl; li++) {
    TL[li] = toklin(L[li])
    if (L[li] ~ /git/) hasgit = 1
    if (index(TL[li], "@@") > 0) {
      nn = split(TL[li], tt, /[ \t]+/)
      for (qq = 1; qq <= nn; qq++) if (tt[qq] == "@@") qtot++
    }
  }
  # Garde 8 : la charge HEREFREE, portee par le descripteur 4 (le 3 porte la table SPANTAB depuis
  # T-01M5D6XS2S), est lue pour le prefixe d environnement (envp), ancre sur un caractere hors nom
  # (FOO_SKIP=, NOHUSKY=, GIT_CONFIG_NOSYSTEM= ne le sont pas) ; meme ERE que _HOOK_ENV.
  envp = 0
  if (hasgit) {
    while ((gr = (getline rl < "/dev/fd/4")) > 0)
      if ((" " rl) ~ /[^A-Za-z0-9_](GIT_CONFIG_(PARAMETERS|COUNT|KEY_[0-9]+|VALUE_[0-9]+|GLOBAL|SYSTEM)|HUSKY|HUSKY_SKIP_HOOKS|LEFTHOOK|SKIP)=/) envp = 1
    if (gr < 0) envp = 1  # canal illisible : refus bruyant, jamais un passage muet
    close("/dev/fd/4")
  }
  if (qtot > 0) qv = (readspans() == qtot)
  qn = 0
  for (li = 1; li <= nl; li++) {
    n = split(TL[li], t, /[ \t]+/)
    for (qq = 1; qq <= n; qq++) {
      if (t[qq] == "@@") {
        qi[qq] = ++qn
        if (qv && QA[qn] && !QG[qn] && !QD[qn]) t[qq] = QC[qn]
      }
      BR[qq] = (t[qq] == "\036")
      if (BR[qq]) t[qq] = ";"
    }
    if (PEND) hookcarry()
    walkline()
  }
  if (HV && envp) note("GITHOOKS")
  for (i = 1; i <= m; i++) print out[i]
}
') || AWK_RC=$?
exec 3<&-
exec 4<&-
# L ÉTAGE AWK ÉCHOUE OUVERT, ET LE DIT (T-00000762, réserve R3) : une erreur de
# syntaxe dans ce programme rend VERDICTS vide, donc AUCUNE garde ne mord — 126
# arms de refus passaient rc 0 sans un mot, mesuré. Même posture que les étages
# 0, 0.5 et 1 : annoncé, exit 0, jamais exit 2 — l étage redirection en est la
# seule exception depuis T-00000784 (panne d un juge présent : refus, règle
# redirect-stage-broken).
[ "$AWK_RC" -eq 0 ] || degraded "the recognition stage (awk) failed"

RM_ROOT=0; RM_HIT=0; RG_TOK=""; GIT_WIPE=""; GIT_OUT_WRITE=0; GIT_PAGER_EXEC=0; GIT_HIDDEN=0; GIT_BRANCH_FORCE=0; BRACE_UNREAD=0; GIT_ALIAS=0; GIT_HOOKS=0
while IFS= read -r v; do
  case "$v" in
    ROOT) RM_ROOT=1;;
    HIT) RM_HIT=1;;
    "RG "*) [ -n "$RG_TOK" ] || RG_TOK="${v#RG }";;
    "GITWIPE "*) [ -n "$GIT_WIPE" ] || GIT_WIPE="${v#GITWIPE }";;
    GITOUT) GIT_OUT_WRITE=1;;
    GITPAGER) GIT_PAGER_EXEC=1;;
    GITHIDDEN) GIT_HIDDEN=1;;
    GITBRANCHD) GIT_BRANCH_FORCE=1;;
    BRACEUNREAD) BRACE_UNREAD=1;;
    GITALIAS) GIT_ALIAS=1;;
    GITHOOKS) GIT_HOOKS=1;;
  esac
done <<EOF
$VERDICTS
EOF

deny() { # deny <rule> — trace puis refus. Le message est déjà sur stderr.
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=safe-bash "rule=$1" "cmd_sha256=$CMD_SHA256" "cmd_len:=$CMD_LEN" >/dev/null 2>&1 || true
  exit 2
}

# --- Garde des accolades : un développement que la garde ne lit pas ---------
# T-01M5D6XS2S, étage 1.5 : au-delà de sa borne, ou avec un segment cité dans
# le mot, l'accolade n'est pas développée ; si la commande nomme git, rm, find
# ou xargs, ou si ce mot tient le mot de commande (ou le précède), ce qui
# tournerait ne peut pas être lu — refus plutôt que supposition.
if [ "$BRACE_UNREAD" -eq 1 ]; then
  echo "BLOCKED: an unquoted brace expansion in this command cannot be read: it grows past the bound the guard expands (256 words per word, 1024 per command), or it holds a quoted piece (\`{git,'reset'}\`) or a substitution, a process substitution, an arithmetic or a backtick before its closing brace (\`{git,reset,--hard,\$(true)}\`, \`{git,reset,--\$(echo hard)}\`) — and the command names git, rm, find or xargs, or the brace stands in or before its command word (\`{r{m,},{1..300}} -rf src\`; an envelope — sudo, doas, env (with -S), command, exec, eval, time, nohup, nice, ionice, stdbuf, timeout and its duration, xargs, watch, parallel, setsid, chrt, taskset, builtin — its options, and a reserved word (!, {, if, then, elif, else, do, while, until) are not the command word: \`sudo -u root {r{m,},{1..300}} -rf src\` is refused too). What bash would run is unknown, so it is refused rather than guessed. Write the words out, or quote the braces. Within that bound a brace list or sequence outside quotes (\`{a,b}\`, \`{1..3}\`) is expanded as bash expands it before any guard reads the words." >&2
  deny brace-expansion-unread
fi

# --- Garde 1a : `rm -rf /` ---------------------------------------------------
if [ "$RM_ROOT" -eq 1 ]; then
  echo "BLOCKED: refusing catastrophic rm." >&2
  deny rm-rf-root
fi

# --- Garde 3 : effacement git NON SCOPÉ --------------------------------------
# Mesuré sur un projet consommateur le 2026-08-06 : pendant un fan-out, toutes
# les modifications de fichiers SUIVIS ont été rétablies à HEAD — les éditions
# de l'agent qui travaillait, le `.gitignore` d'un autre, et les écritures
# d'état de l'orchestrateur. Seuls les fichiers NON SUIVIS ont survécu.
# `.agents/state/board/TASKS.json` étant suivi, DEUX tâches créées la minute
# d'avant ont disparu et leurs identifiants ont été réattribués.
#
# CE QUE LA DISJONCTION DES WRITE-SETS NE PROTÈGE PAS. Elle empêche deux
# écrivains de se marcher dessus ; elle n'empêche pas un nettoyage GLOBAL d'en
# effacer un troisième. CE QUI RESTE APRÈS COUP, dit par sous-commande
# (T-00000762 — cette ligne disait « contrairement à un `reset` », et c'était
# faux : `reset --hard` perd l'édition jamais indexée exactement de la même
# façon) : restore, checkout, clean et reset --hard ne laissent AUCUN objet git
# d'une édition jamais indexée, et rien au reflog ; stash déplace le travail
# dans la pile PARTAGÉE par toutes les sessions, où le `pop`/`drop`/`clear`
# d'une autre le prend.
# LE REMÈDE EST DIT PAR SOUS-COMMANDE, ET CHACUN EST POSSIBLE (T-00000762,
# décision 5) : l'ancien « donnez un chemin précis » était impossible pour
# `reset --hard` (il n'en prend aucun) et pour `git clean` (refusé quel que soit
# son chemin) ; `git clean -n`, lui, n'efface rien et passe désormais.
if [ -n "$GIT_WIPE" ]; then
  WIPE_BROAD=" \`.\`, \`*\`, \`:/\`, \`:(top)\`, an exclude-only pathspec, a list read from stdin (\`--pathspec-from-file=-\`, or the operands \`xargs\` feeds from a pipe: \`xargs git checkout --\`) and an UNQUOTED expansion (\`\$f\`, which may split, glob or be empty) all count as the whole tree — quote an expansion (\`\"\$f\"\`)."
  case "$GIT_WIPE" in
    stash)
      WIPE_TRUTH="It moves that work into the stash stack SHARED by every session of this repository, where another session's \`git stash pop\`, \`drop\` or \`clear\` takes it — its owner never sees it again."
      WIPE_REMEDY="Stash a PRECISE PATH instead (\`git stash push -- src/foo.ts\`), or commit first.$WIPE_BROAD" ;;
    "reset --hard")
      WIPE_TRUTH="An edit that was never staged leaves NO git object and NOTHING in the reflog, so it cannot be recovered afterwards."
      WIPE_REMEDY="\`git reset --hard\` takes no pathspec: drop one file's edits with \`git restore -- src/foo.ts\`, move the branch with \`git reset --keep <commit>\` (it refuses to lose local edits), or commit first. Every abbreviation of --hard (\`--h\`) is refused too, and so is an option word holding an UNQUOTED expansion (\`git reset \$x\`, \`--hard\$x\`), which may expand to --hard." ;;
    clean)
      WIPE_TRUTH="An edit that was never staged leaves NO git object and NOTHING in the reflog, so it cannot be recovered afterwards."
      WIPE_REMEDY="Run \`git clean -n\` first — a dry run, allowed, that deletes nothing and lists what would go — then delete what it lists by name, or ask the user to approve this exact command. The dry run is credited option by option (T-01M5D6XS2S): the last of \`-n\`, \`--dry-run\`, \`--no-dry-run\` wins, \`-e\` takes its value even at the end of a cluster (\`-fde -n\` excludes the pattern -n, no dry run), and a word that may expand into an option — an unquoted expansion, a glob, a backslash (\`-e \$x -n\`, \`-?n\`, \`-e\\ -n\`) — withdraws the credit." ;;
    *)
      WIPE_TRUTH="An edit that was never staged leaves NO git object and NOTHING in the reflog, so it cannot be recovered afterwards."
      WIPE_REMEDY="Give a PRECISE PATH instead (\`git restore src/foo.ts\`, \`git checkout -- src/foo.ts\`), or commit first.$WIPE_BROAD" ;;
  esac
  echo "BLOCKED: an unscoped \`git $GIT_WIPE\` wipes the UNCOMMITTED work of every agent running right now out of the working tree — including the tracked state registers (TASKS.json, LEDGER.json, SPECS.json). $WIPE_TRUTH Measured on a consumer project 2026-08-06: two board tasks created a minute earlier vanished during a fan-out and their ids were reassigned. $WIPE_REMEDY Not read, bounded and not closed: a command carried in a quoted string (\`bash -c \"…\"\`, \`env -S \"…\"\`), \`env -v …\`, an envelope outside the table (\`timeout 5 git …\`) and a brace that is no list nor sequence (\`HEAD@{1}\`), where the words are cut; a brace list or sequence (\`git reset {--hard,}\`, \`git {reset,--hard}\`) is expanded and read (T-01M5D6XS2S), and refused on its own rule past its bound. Named, not closed: inside a quoted \`\"\$(…)\"\`, the \`)\` of a \`case\` pattern ends the substitution early for this guard, which reads the rest as quoted data (a \`git reset --hard\` written after such a pattern passes unread); a \`)\` inside \`\${x:-)}\` no longer does (the expansion is read as one block)." >&2
  deny git-wipe-unscoped
fi

# --- Garde 5 : `git … --output` ÉCRIT UN FICHIER (T-00000762) ---------------
# Mesuré dans un dépôt jetable : `--output=<f>` ET `--output <f>` écrivent, et
# `git show --output=f HEAD` a ÉCRASÉ le fichier SUIVI `f` — une écriture qui
# contourne Edit/Write, ses checkpoints et ses gardes de mandat. Refus
# INCONDITIONNEL, quelle que soit la sous-commande et où que pointe la cible :
# le remède (une redirection) passe par la garde 4, qui, elle, JUGE sa cible.
if [ "$GIT_OUT_WRITE" -eq 1 ]; then
  echo "BLOCKED: \`git … --output\` writes a FILE — a tracked one included (\`git show --output=f HEAD\` overwrote a tracked file, measured) — and bypasses the Edit/Write path with its checkpoint and mandate guards. Redirect instead (\`git log … > /tmp/x\`): the redirect guard JUDGES that target, and a path outside the repository passes. (Refused whatever the subcommand and wherever the target points; \`-o\` is never read as --output.)" >&2
  deny git-output-write
fi

# --- Garde 6 : `git grep -O` EXÉCUTE UNE COMMANDE (T-00000762) ---------------
# Mesuré : `-O<cmd>`, `-O` nu (le pager de l'environnement), `-nO<cmd>`,
# `-iO<cmd>`, `--open-files-in-pager=<cmd>` et ses abréviations `--open=`,
# `--op=` lancent une commande sur les fichiers trouvés ; `git grep -e Ofoo`
# n'exécute rien et passe.
if [ "$GIT_PAGER_EXEC" -eq 1 ]; then
  echo "BLOCKED: \`git grep -O\` / \`--open-files-in-pager\` RUNS A COMMAND — the option's value, or the environment's pager when it has none — on the files it finds: an arbitrary execution no guard reads. Run \`git grep\` without it and open the files with the Read tool. (Every abbreviation of --open-files-in-pager, and every short cluster carrying O before a value letter, is refused.)" >&2
  deny git-grep-pager-exec
fi

# --- Bras fail-closed des gardes 3, 5 et 6 : sous-commande CACHÉE -----------
# T-00000762, décision 3. Une expansion NON citée là où git lit sa
# sous-commande (`git $sub .`, `git $(echo reset) --hard`) cache ce qui
# tournerait : effacement, écriture `--output`, pager — rien ne peut être jugé,
# donc refus. Une VALEUR qui est une expansion (`git -C $d status`) ne cache
# rien et passe.
if [ "$GIT_HIDDEN" -eq 1 ]; then
  echo "BLOCKED: an UNQUOTED expansion (\`\$x\`, \`\$(…)\`, a backtick) stands where git reads its subcommand, so whether this is an unscoped wipe, a \`--output\` write or a \`grep -O\` cannot be read — refused rather than guessed. Quote an expansion that is a VALUE (\`d=\$(pwd); git -C \"\$d\" status\`) and write the subcommand itself literally." >&2
  deny git-subcommand-hidden
fi
# T-01M5D6XS2S (T-01M53HV4) : un ALIAS défini pour ce git cache sa sous-commande
# de la même façon — `git bd` lancerait `branch -D`. Même règle, son message.
if [ "$GIT_ALIAS" -eq 1 ]; then
  echo "BLOCKED: a git ALIAS is defined for this command — \`git -c alias.<x>=…\`, \`git --config-env=alias.<x>=…\`, or a \`GIT_CONFIG_KEY_<n>=alias.…\` / \`GIT_CONFIG_PARAMETERS\` assignment before git (behind \`env\` too; a value that is an expansion, or a quoted one that cannot be read, counts) — so the subcommand git runs is hidden behind the alias: whether this is an unscoped wipe, a forced branch delete, a \`--output\` write or a \`grep -O\` cannot be read — refused rather than guessed. Write the git command itself, without the alias. Not read, named: an alias exported by an EARLIER command of the same call (\`export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.bd …; git bd …\`) or set in a git config file." >&2
  deny git-subcommand-hidden
fi

# --- Garde 7 : git branch -D wt/* (T-00001090) --------------------------------
# Une branche wt/<T> porte le travail dun dev en worktree tant quelle nest pas
# fusionnee : -D (ou -d --force) la supprime sans regarder, et ses commits ne
# sont plus atteignables que par le reflog. Le MECANISME est celui du message
# ci-dessous, seule reference : decide_git lit les mots de branch jusqu a la
# fin de la commande ou jusqu a la premiere coupe (substitution, accolade hors
# guillemets et hors `${…}`, qui finit a son premier `}`), une option apres
# lopérande comprise, casse repliee, antislash retire ; un mot non option qui
# porte `$` ou un backtick, `@{` (interdit dans un nom de ref, resolu par git :
# `@{-1}` est la branche precedente) et une coupe lue APRES la suppression
# forcee comptent wt/ (fail-closed, `feat }`, `# {x}`) ; une coupe
# AVANT elle laisse la suite non lue (`git branch wt/x {x} -D`, trou T-00001196) ;
# une LISTE ou une SEQUENCE d accolades n est plus une coupe : l etage 1.5 la
# developpe d abord (`{wt/x,y}`, `{-D,}`, T-01M5D6XS2S) ;
# `-D -r wt/x` est refuse aussi, faux positif fail-closed (`--sort -r` fait de
# `-r` une valeur, mesure). Bornes NOMMEES dans le message, liste bornee et non
# close (trous T-00001198, T-00001200, T-00001202) : ce qui nest pas lu ici ne
# lest nulle part ailleurs.
if [ "$GIT_BRANCH_FORCE" -eq 1 ]; then
  echo "BLOCKED: \`git branch -D\` (or \`-d --force\`) on a \`wt/\` branch deletes the commits only that branch carries: the unmerged work of a worktree dev. Run \`git branch -d wt/<T>\` after the merge instead — git refuses to delete an unmerged branch, and a refused \`-d\` is reported, never forced. Bounds: \`wt/\` only, letters folded (\`WT/x\` names the same branch on an APFS or NTFS disk); a name held in an expansion or a substitution (\`\$b\`, \`\"\$b\"\`, \`\$(…)\`) and a name holding \`@{…}\`, quoted or not (\`@{-1}\`), count as \`wt/\`, and so does any word after \`branch\` that is not an option and holds a \`\$\` or a backtick, even one bash does not expand — quoted (\`'\$b'\`), escaped (\`\\\$b\`) or in a trailing comment (\`# \$HOME\`), a fail-closed false positive — while a \`\$\` inside an option word is not read as a name (\`--sort=\$x\`); \`-D -r wt/…\` is refused too (fail-closed false positive); so is a \`-D\` read in a trailing comment (\`git branch wt/x # -D\`). Braces: an unquoted brace list or sequence (\`{wt/x,y}\`, \`{-D,}\`, \`-{D..D}\`, \`{branch,-D}\`) is first expanded as bash expands it (T-01M5D6XS2S; past its bound — 256 words per word, 1024 per command — it is refused on its own rule), and its cut as written still counts as \`wt/\` when its command segment, inside quotes too, holds a character outside a closed set (ASCII letters, digits, blank, tab, \`{},._/@:=+%#<>&\`, quotes, \`-\`), a quoted span that is not plain single or double quotes on one line, or a sequence the guard does not expand as bash does (\`{V..a}\`, \`{+1..2}\`) — fail-closed false positives, named (T-01M5GFV9CE): \`(git branch -D {a,b})\`, \`git branch -D {a,b} x[1]\`, \`git branch -D {a,b} \"w<TAB>t/x\"\`; then the guard stops reading a \`git\` command at its first \`{\` or \`}\` outside quotes and outside a \`\${…}\`, a brace that is no list nor sequence (\`{x}\`, \`@{…}\`) (read as an expansion; a \`\${…}\` ends at its first \`}\`: \`\${x:-{y}}\` cuts there, so \`git branch \${x:-{y}} -D wt/…\` passes unread) — a backslash does not protect it, and one in a comment or a redirect target counts (the words end with the command, e.g. at \`;\`, \`&\`, \`|\`, an unescaped newline or a closing \`)\`: a brace after that is not read; a backslash-newline is NOT joined, so \`git branch -D \\<LF>wt/…\` and \`git branch -D feat \\<LF>{wt/x,y}\` pass unread on the three hosts — gap carried by T-00001198). If a forced delete (\`-D\`, or \`-d\`/\`--delete\` with \`-f\`/\`--force\`) was read before that point, the command is refused as if the name were \`wt/\` (a fail-closed false positive for a non-wt name: \`feat }\`, \`# {x}\`); if not, it passes unread (named gap, T-00001196: \`git branch wt/… {x} -D\`). On the Claude host only, a word after \`branch\` glued to a quoted span (\`feat-\"old\"\`, \`--sort=\"x\"\`) counts as \`wt/\` too, and so does, once the command holds a literal \`@@\` anywhere, every quoted word after \`branch\` and a \`@@\` among those words (\`git branch -D 'feat' # @@\`, \`git branch -D feat # @@\`) (fail-closed false positive). The delete option is not read as bash reads it — gap carried by T-00001202: on the Claude host only, a quoted or glued option (\`git branch '-D' wt/…\`, even with a literal \`@@\` in the command, \`-\"D\"\`, \`-d '-f'\`) or one behind a backslash (\`\\-D\`), and on the three hosts an option glued after an expansion that may be empty (\`\$b-D\`, \`\${b}-D\`; \`\"\$b\"-D\` on the Codex and Gemini hosts only), and a \`--\` taken by git as the value of \`--sort\`/\`--format\` (\`git branch --sort -- -D wt/…\`) pass unread; an option in ANSI-C quotes standing as a whole word is decoded and read on the Claude host (\`\$'-D'\`, \`\$'\\055D'\`, T-01M5D6XS2S) — glued to another word it stays unread there —, not yet on the Codex and Gemini hosts. Not covered, named: \`branch -M|-C <x> wt/…\`, \`branch -f wt/…\`, \`update-ref -d\`, \`push . :wt/x\`, an option written after a substitution (\`git branch \$(…) -D\`), \`checkout -B\`/\`switch -C wt/…\`, \`env -S '…'\`/\`env -v\`, an envelope outside the table (\`timeout 5 git …\`, \`nice -n 5 git …\`), a command carried in a quoted string (\`bash -c \"…\"\`) and \`xargs\` behind an envelope outside the table (\`timeout 5 xargs git branch -D\`) — bounded, not closed. \`xargs\` at the head of the command (alone, or behind table envelopes) IS read: a branch name it feeds from the pipe counts as \`wt/\` (T-01M5D6XS2S). Named, not closed: the \`)\` of a \`case\` pattern inside a quoted \`\"\$(…)\"\` ends the substitution early for this guard, the rest is read as quoted data; a \`)\` inside \`\${x:-)}\` no longer does." >&2
  deny git-branch-force-delete
fi

# --- Garde 8 : une commande git qui SAUTE les hooks (T-01M5C1AF6GB3ZRX5QF9SF6R80Y) ---
# Mesuré (git 2.54) : `--no-verify` et ses abréviations, `-n`/`-an` sur commit et am,
# `-c`/`--config-env` sur core.hooksPath, `GIT_CONFIG_*`, et un `git config` qui écrit,
# édite ou retire core.hooksPath (sous `--fil`, `--ty`, `--comm`, `unset`, `remove-section`,
# une option de lecture APRÈS la clé, qui est une valeur…) lancent le verbe sans ses hooks.
# La règle est celle de decide_git (garde 8) ; le texte est celui de HOOKS_REASON de
# safe_bash_git.py, mot pour mot (test_garde_contournement_hooks les compare). Elle empêche
# d'OUBLIER, pas de TRICHER : ses bornes sont nommées dans le message (décision pilote
# S-01M5CZ8SYGNDWC7BZN8DTZ1NN7). Même place que sur les hôtes python : après la garde 7.
if [ "$GIT_HOOKS" -eq 1 ]; then
  echo "BLOCKED: this git command skips the repository's git hooks (rule git-hooks-bypass) — the pre-commit, commit-msg and pre-push gates, so what they would refuse ships unseen. Read here: \`--no-verify\` and every abbreviation from \`--no-v\` on commit, push, merge, rebase, am and pull; \`-n\` in a short cluster of \`commit\` or \`am\` (\`-an\`; \`-uno\` and the text of a value letter do not count); an UNQUOTED expansion among the options of those six verbs (\`\$F\`, \`\$(…)\`, a backtick: an option after one is unread); \`-c\`/\`--config-env\` (\`=\` or separated) whose value holds \`hookspath\` (\`core.hooksPath=.githooks\` exactly excepted: the key in any case, the value as written, \`.GITHOOKS\` refused) or \`include\` on a verb that runs hooks (those six, cherry-pick, revert), and \`alias.\` on any verb; an assignment \`GIT_CONFIG_PARAMETERS=\`, \`GIT_CONFIG_COUNT=\`, \`GIT_CONFIG_KEY_<n>=\`, \`GIT_CONFIG_VALUE_<n>=\`, \`GIT_CONFIG_GLOBAL=\`, \`GIT_CONFIG_SYSTEM=\`, \`HUSKY=\`, \`HUSKY_SKIP_HOOKS=\`, \`LEFTHOOK=\` or \`SKIP=\` anywhere in a command that runs such a verb; a \`git config\` with a word holding \`hookspath\`, \`core.worktree\`, \`alias.\`, \`include\` or an unquoted expansion, unless it is a pure read; and \`git config -e\`/\`--edit\`/\`edit\`, \`remove-section\`, \`rename-section\` (\`--rem…\`, \`--ren…\`) always. Remedy: run the command without the bypass and fix what the hook reports, or ask the user to approve this exact command. A pure read passes: \`get\`/\`list\` as the first word, or \`--get\`, \`--get-all\`…, \`--list\`, \`-l\` among the options BEFORE the first other word (after it an option is a value: \`git config core.hooksPath --get\` writes \`--get\`), every option from the closed read list, a value glued (\`-f.git/config\`, \`--file=x\`, \`--type=bool\`); so does \`git config [set] core.hooksPath .githooks\` (\`--local\` or \`--worktree\` at most). Named false positives: \`--no-verify --verify\`; two substitutions in one quoted string (\`git commit -m \"\$(a)\$(b)\"\`: the second one cuts the words); a value spelled like an option outside a commit/am cluster (\`git commit --message \"--no-verify\"\`, \`git merge -m \"--no-verify\"\`); a \`git config\` whose VALUE holds one of those words (\`git config user.name alias.x\`) or an unquoted expansion; the implicit read \`git config core.hooksPath\` (write \`--get\`); a read with a separated value (\`-f x --get …\`: write \`-fx\` or \`--file=x\`) or an option outside the closed list; \`git -c core.hooksPath=/dev/null commit\` in a throwaway repository; such an environment name quoted, or in a heredoc body (Codex and Gemini hosts), beside such a verb; \`git push origin \$b\`, \`git merge \$b\`, \`git push origin \$(git branch --show-current)\` (quote it); on the Claude host, once the command holds a literal \`@@\`, a quoted word after a \`git\` (its subcommand, a \`-c\` value, an option of such a verb, a word of \`git config\`). Bounds, named and NOT refused — this guard prevents forgetting, not cheating: \`--git-dir=<d>\`/\`--git-dir <d>\`, \`--work-tree=<d>\`/\`--work-tree <d>\`, \`GIT_DIR=\` and \`GIT_WORK_TREE=\` with such a verb (a relative hooksPath then resolves elsewhere); a configuration redirected by \`HOME=\` or \`XDG_CONFIG_HOME=\` (a forged ~/.gitconfig acts when no local core.hooksPath is set); a quoted expansion in option position (\`\"\$F\"\`), a quoted expansion as a \`git config\` key (\`git config \"\$K\" v\`) and an expansion as a \`-c\` value; on the Claude host, a quoted span glued to a word (\`--no-\"verify\"\`, \`core.hooks\"Path\"\`, \`co\"mmit\"\`, T-00001202); \`--attr-source\` (T-00001193); a brace (\`{--no-verify,}\`) and an option after a brace, \`@{u}\` included (\`git rebase @{u} --no-verify\`); \`<(…)\` before an option (\`git commit -F <(printf x) --no-verify\`); \`\$'--no-verify'\`; a backslash-newline (T-00001198); \`printf … >> .git/config\` (the redirect guard's to refuse); an alias already configured (\`git ci\`); plumbing that writes refs or pushes without porcelain (\`commit-tree\`, \`update-ref\`, \`send-pack\`); an earlier \`export HUSKY=0\`; a command carried in a quoted string (\`bash -c \"…\"\`); an envelope outside the table (\`timeout 5 git …\`); \`chmod -x .githooks/*\`; the admitted \`.githooks\` disarming \`.husky\`; a failed awk stage (Claude: degraded, announced) and a crashed Python hook (T-00001194) — bounded, not closed: these are the holes we know." >&2
  deny git-hooks-bypass
fi

# --- Garde 2 : `rg` ABSENT du PATH -------------------------------------------
# Mesuré sur un projet consommateur le 2026-08-06 : deux agents ont conclu
# « zéro occurrence » sur des balayages qui n'avaient jamais tourné. Le
# mécanisme est le même dans les deux formes usuelles — `rg MOTIF || echo
# AUCUN` prend la branche d'échec sur le 127 de « command not found » et
# imprime AUCUN ; `rg MOTIF 2>/dev/null` mange le message et n'imprime rien.
# La SORTIE a exactement la forme d'une recherche vide. Sur un dépôt dont la
# méthode repose sur des « zéro occurrence mesurée », un instrument qui ment
# par le vide invalide le raisonnement sans laisser de trace.
#
# La garde ne porte QUE sur l'absence : `rg` présent, elle laisse passer.
# Bloquer un outil qui fonctionne n'apporterait rien, et le mode de défaillance
# visé n'existe alors plus. `command -v` reçoit le jeton en ARGUMENT (jamais
# via un shell) : la charge utile n'est toujours pas interprétée.
if [ -n "$RG_TOK" ] && ! command -v "$RG_TOK" >/dev/null 2>&1; then
  echo "BLOCKED: \`$RG_TOK\` does not resolve on this machine, and an absent ripgrep fails INDISCERNIBLY from an empty result: \`rg PAT || echo NONE\` takes the failure branch on the 127 of command-not-found and prints NONE; \`rg PAT 2>/dev/null\` swallows the message and prints nothing. A sweep that never ran then reads as 'zero occurrences' — measured on a consumer project 2026-08-06, two agents concluded absence from scans that had never executed. Use the Grep tool, which fails loudly. (This guard only fires when the tool is MISSING; a working rg is never blocked.)" >&2
  deny rg-absent-silent-failure
fi

# --- Garde 4 : ÉCRITURE SHELL par redirection vers un fichier suivi/protégé ---
# Placée AVANT la garde rm/mv : celle-ci sort 0 tôt sur la liste blanche temp,
# donc une écriture redirigée gardée ne doit pas dépendre de cet ordre.
if [ -n "$REDIR_REFUSED" ]; then
  # The clause after the existing sentence says HOW each path was judged
  # (T-00000698). Single quotes only — an unescaped backtick inside this echo
  # would be a command substitution on every refusal; ${CLAUDE_PROJECT_DIR:-.}
  # is the ONE expansion wanted, and it carries the SAME default as the
  # resolution itself (REDIR_REPO, above): without the variable the root the
  # message names is `.`, the one the paths were judged against — never `()`
  # (exec-critic on b7055f0). <root> and the example paths are literals. The
  # credential sentence names BOTH hosts' lists because they DIFFER, and this
  # lot does not align them (T-00000721 does): it says the truth of the
  # verdict, it does not move it. The "never blocked" clause is kept TRUE for an
  # ordinary name and written with its one exception, the arming-marker-name
  # rule (correction of T-00000698): a quoted marker name IS read.
  echo "BLOCKED: this command redirects a write (>, >>, &>, ...) to a tracked or protected file ($REDIR_REFUSED). A shell redirect bypasses the Edit/Write path and its checkpoint and mandate guards — use Edit/Write, or redirect to a path outside the repository. (Descriptor duplication like \`2>&1\` and quoted or \$-expanded targets are never blocked for an ORDINARY name; a target whose last segment names an arming marker is the one exception, below.) HOW EACH TARGET WAS JUDGED: a relative target is resolved against the PROJECT ROOT (${CLAUDE_PROJECT_DIR:-.}), never against a cd internal to the command — 'cd /tmp/x && echo > AGENTS.md' is judged as '<root>/AGENTS.md'; write the absolute path or use the Write tool instead. A protected name (one of the arming/exit markers and pilot-only files protect-paths.sh names — NIGHT_HEADLESS.allow and MCP_ALLOWLIST.md among them since T-00000723, AUDIT_LOG alone is not among them (S-00002524) —, .claude/settings.local.json, .gitleaks.toml (the class-0 exception register, T-00000844 — any *.gitleaks.toml), mcp.json, .codex/config.toml, .gemini/settings.json, a .git segment, .env by name or as a substring, a credential-looking token) is refused by its own reason wherever it lives, including outside this repository; no exemption, and a directory segment counts too ('/tmp/secrets/x' is refused by the credential rule). An arming/exit marker is ALSO refused by its NAME alone (rule arming-marker-name): a redirect whose target's last segment is one of those names is refused whether the target is bare after a cd internal to the command, quoted, or under an expanded directory — this holds the NAME, not the directory, so neither a cd nor a throwaway clone arms a marker. WHAT THIS GUARD DOES NOT HOLD, said rather than implied: it prevents forgetting, not cheating — tee, cp, python -c and sed -i pass; and for any OTHER tracked or protected target a cd internal to the command or a quoted target still hides it (T-00000720). A credential-looking token is judged against the list of THIS host, and the lists are ALIGNED since T-00000721: id_rsa, credential(s), secret, private-key/private_key, .env as a SUBSTRING (so .envrc) and the .pem/.key/.p12/.pfx/.crt extensions, on every host. Every name is judged case-folded AND NTFS-folded (T-00000722): a trailing dot or space and a ':' stream are stripped per segment, so 'MARKER.', 'MARKER ' and 'MARKER::\$DATA' are the marker. A target refused with rule formes-instables is one whose canonical forms (NTFS folds, lexical renormalisation, lowercasing, physical resolution of links) do not reach a fixed point within 5 rounds (T-00000722) — usually a chain of symbolic links whose targets carry dot segments — so it is refused rather than judged in part: write the resolved path; formes-illisibles, the Edit guard's name for a closure that produced nothing, does not occur here, where a crashed redirect stage refuses the call (rule redirect-stage-broken). Everything else is the simple inside case." >&2
  deny redirect-write-guarded
fi

# --- Passe rm/mv PAR OPÉRANDE (T-00000762) -----------------------------------
# JOUÉE SEULEMENT SI L'ÉTAGE 2 A NOTÉ `HIT` : zéro coût sur une commande sans
# rm/mv (le bras x-nohit le tient, par un shim qui journalise le programme
# lancé). Bloc SÉPARÉ de la garde 1b pour que la condition `HIT` reste une
# propriété de COÛT, mesurable seule.
# CE QU'ELLE FAIT. Elle refait le scan isométrique de l'étage 1 (port de
# `scrub_spans`, un `@` par caractère), coupe sur `;` `&` `|` et le retour à la
# ligne du texte neutralisé (même coupe que `_COARSE_CUT` des hôtes python), et
# marche les jetons EXACTEMENT comme `main` de `.codex/hooks/safe_bash.py` —
# enveloppes, mots-clés, sondes, affectations, `-exec|-execdir` — PLUS un
# drapeau `fed`, posé par l'enveloppe `xargs` ou `parallel` et par
# `-exec|-execdir`, mort au séparateur. Pour chaque rm/mv : les redirections
# (`N>f`, `>`, `>>`, `2>&1`, `<`…) sont retirées avec leur cible sur le texte
# NEUTRALISÉ (un `">"` cité n'est pas un opérateur et reste un opérande), puis
# `shlex` de la tranche BRUTE, options sautées avant `--`, tout opérande après,
# et les jetons vides après retrait des guillemets exclus AVANT le compte (un
# `"` isolé n'est pas un opérande). Un opérande est jugé contre la liste ANCRÉE
# de l'en-tête (point 1), tel qu'écrit ET résolu (copie de `normalize` de
# l'étage redirection) ; les relatifs retenus passent par UN SEUL
# `git ls-files -z` (LC_ALL=C, 5 s, à la racine) : un chemin rendu égal à
# l'opérande ou sous lui (ou qui le vérifie par `fnmatch` s'il porte `*?[`) est
# SUIVI, donc refusé ; une sortie non attribuable refuse tout.
# BORNE DU `cd` INTERNE, écrite (réserve R1) : un opérande RELATIF est jugé
# contre la RACINE du projet, jamais contre un `cd` de la même commande — même
# borne que l'étage redirection (T-00000720) — donc le veto de suivi ne vaut
# que pour un opérande écrit depuis la racine.
# SENTINELLE TOUJOURS IMPRIMÉE (L-00000308) : `OK`, `NONE` (aucune occurrence
# retrouvée), ou une ligne `DENY<tab><motif><tab><chemin>` par refus. FAIL-CLOSED
# : `NONE`, sentinelle absente, statut non nul, git en panne ou muet — REFUS.
# Deux reconnaisseurs vivent donc dans ce fichier (l'awk et cette passe) : leur
# dérive tombe du côté du refus, jamais de l'effacement.
# QUOTAGE : programme entre apostrophes bash, AUCUNE apostrophe dedans (chr(39)),
# texte par STDIN, jamais par argv — comme l'étage 1.
RMMV=""; RMMV_RC=0
if [ "$RM_HIT" -eq 1 ]; then
RMMV=$(printf '%s' "$HEREFREE" | RMMV_REPO="${CLAUDE_PROJECT_DIR:-.}" "$PY" -c '
import sys, os, re, shlex, subprocess, fnmatch
from pathlib import Path
MARK = "T762-RMMV-PASS"
REPO = os.environ.get("RMMV_REPO") or "."
SQ = chr(39)
DQ = chr(34)
BS = chr(92)
BT = chr(96)
NL = chr(10)
TAB = chr(9)
SEP = " " + TAB + ";&|()" + BT + NL
COARSE = re.compile("[;" + NL + "]+|(?<![<>])(?!&>)[&|]+")
UNIT_REDIR = re.compile("[0-9]*(?:&>>|&>|<<<|<<-|<<|<>|>>|>&|<&|>[|]|>|<)")
UNIT_STOP = set(" " + TAB + "|;&()<>{}" + BT)
SIMPLE_BRACE = re.compile("[$][{][^}$" + BT + "(]*[}]")
ASSIGN = re.compile("^[A-Za-z_][0-9A-Za-z_]*=")
EXPANSION = re.compile("[$" + BT + "]")
ENVELOPES = set("sudo doas env command exec eval time nohup nice ionice stdbuf timeout xargs watch parallel setsid chrt taskset builtin".split())
FEEDERS = set(["xargs", "parallel"])
FIND_EXEC = set(["-exec", "-execdir", "-ok", "-okdir"])
KEYWORDS = set("if then elif else do while until ! coproc".split())
PROBES = set("which type hash whence".split())
VERBS = set(["rm", "mv"])
ENV_OPTIONS = {
    "env": (set("- -i -0 --ignore-environment --null --debug --list-signal-handling --block-signal --default-signal --ignore-signal --".split()), set("-u -C -P -a --unset --chdir --argv0".split())),
    "sudo": (set("-A -B -b -E -H -k -N -n -P -S -i -s --askpass --bell --background --preserve-env --set-home --reset-timestamp --login --non-interactive --preserve-groups --stdin --shell --no-update --".split()), set("-C -D -g -p -R -T -U -u -r -t --close-from --chdir --group --prompt --chroot --command-timeout --other-user --user --role --type".split())),
    "doas": (set("-L -n -s --".split()), set("-C -u".split())),
    "command": (set("-p --".split()), set()),
    "nohup": (set(["--"]), set()),
    "time": (set("-p --".split()), set()),
}
LISTED = set([".tmp", "node_modules", "dist", "build", ".cache"])
ANCHORS = sorted(set(["/tmp/", str(Path("/tmp").resolve()).rstrip("/") + "/"]))
GLOB = set("*?[")
def scrub_spans(text):
    # T-01M5D6XS2S : une lecture RÉCURSIVE. Dans "…", un $(…) ou un backtick NON
    # échappé est du CODE (le segment cité se coupe autour) ; dans ce code, un
    # corps de heredoc à délimiteur CITÉ est une DONNÉE jusqu à la première ligne
    # qui COMMENCE par le délimiteur, blancs de tête retirés (EOF) compris) ; un
    # corps de heredoc NU, ou de premier niveau, garde ses guillemets LITTÉRAUX.
    # Une construction IMBRIQUÉE qui ne se ferme pas (ou plus de 64 niveaux)
    # ARRÊTE la lecture : rien après le guillemet qui l ouvre n est neutralisé,
    # donc tout y est ANALYSÉ (bash n exécute rien après une construction non
    # fermée) — et aucune relecture spéculative, qui serait exponentielle.
    spans = []
    n = len(text)
    meta = " \t;&|()<>" + NL
    stop = [False]
    def single(i):
        k = i + 2 if text[i] == "$" else i + 1
        while k < n:
            if text[i] == "$" and text[k] == BS:
                k += 2
                continue
            if text[k] == SQ:
                return k + 1
            k += 1
        return -1
    def opaque(i, close):
        # F3 : `${…}` (close "}") et `$((…))`/`((…))` (close "))") lus d un
        # bloc, guillemets sautés : ni segment ni heredoc dedans, texte ANALYSÉ.
        # -2 : pas une arithmétique ; -1 : jamais fermé, la lecture S ARRÊTE.
        # N1 (2e passe) : une citation ANSI-C, une substitution ou un backtick
        # DANS le bloc — guillemets doubles compris — ne se lit pas d un bloc :
        # CHEMIN D ARRÊT, tout ce qui suit est analysé (jamais modélisé).
        depth = 0
        k = i
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] in "(" + SQ):
                stop[0] = True
                return -1
            if c == SQ or c == DQ:
                k += 1
                while k < n and text[k] != c:
                    if c == DQ and text[k] == BS:
                        k += 1
                    elif c == DQ and (text[k] == BT or (text[k] == "$" and k + 1 < n and text[k + 1] == "(")):
                        stop[0] = True
                        return -1
                    k += 1
                k += 1
                continue
            if close == "}":
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return k + 1
                    depth -= 1
            elif c == "(":
                depth += 1
            elif c == ")":
                if depth > 0:
                    depth -= 1
                elif k + 1 < n and text[k + 1] == ")":
                    return k + 2
                else:
                    return -2
            k += 1
        stop[0] = True
        return -1
    def double(i, lvl):
        start = i
        k = i + 1
        while k < n:
            c = text[k]
            if c == BS:
                k += 2
                continue
            if c == DQ:
                spans.append((start, k + 1))
                return k + 1
            if c == "$" and text.startswith("((", k + 1):
                j = opaque(k + 3, "))")
                if j == -1:
                    return -1
                if j > 0:
                    if k > start:
                        spans.append((start, k))
                    start = j
                    k = j
                    continue
            if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                if k > start:
                    spans.append((start, k))
                k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                if k < 0:
                    return -1
                start = k
                continue
            k += 1
        return -1
    def delimiter(i):
        dash = i < n and text[i] == "-"
        if dash:
            i += 1
        while i < n and text[i] in " \t":
            i += 1
        # 3e passe : le mot délimiteur n est lu que s il est fait de pièces
        # SÛRES — caractères de `safe`, entre `'…'` ou `"…"` sans rien d autre,
        # ou `\c` avec c sûr. Tout autre caractère ($'…', $"…", \$, \\, backtick,
        # accolade, retour à la ligne échappé…) : bash le transforme par sa
        # suppression des guillemets, la garde ne le modélise pas — CHEMIN D
        # ARRÊT, tout ce qui suit est analysé.
        safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.+,:@%/"
        word = []
        quoted = False
        while i < n and text[i] not in meta:
            c = text[i]
            if c == SQ or c == DQ:
                j = text.find(c, i + 1)
                if j < 0:
                    return i, None
                if any(x not in safe for x in text[i + 1:j]):
                    stop[0] = True
                    return n, None
                spans.append((i, j + 1))
                word.append(text[i + 1:j])
                quoted = True
                i = j + 1
                continue
            if c == BS and i + 1 < n and text[i + 1] in safe:
                word.append(text[i + 1])
                quoted = True
                i += 2
                continue
            if c not in safe:
                stop[0] = True
                return n, None
            word.append(c)
            i += 1
        if not word:
            return i, None
        return i, ("".join(word), quoted, dash)
    def bare(i, word, dash, close, lvl):
        while i < n:
            e = text.find(NL, i)
            line = text[i:] if e < 0 else text[i:e]
            first = line.lstrip("\t") if dash else line
            if first == word or (close == ")" and first.startswith(word + ")")):
                return i
            k = i
            while k < n and text[k] != NL:
                c = text[k]
                if c == BS:
                    k += 2
                    continue
                if c == BT or (c == "$" and k + 1 < n and text[k + 1] == "("):
                    k = code(k + 1 if c == BT else k + 2, c if c == BT else ")", lvl + 1)
                    if k < 0:
                        return n
                    continue
                k += 1
            i = k + 1
        return n
    def bodies(i, docs, close, lvl):
        for at, (word, quoted, dash) in enumerate(docs):
            last = at == len(docs) - 1
            if i >= n:
                return n
            if quoted and close:
                k = i
                found = -1
                while True:
                    e = text.find(NL, k)
                    if e < 0:
                        e = n
                    if text[k:e].lstrip(" \t").startswith(word):
                        found = k
                        break
                    # F6 : sous bash 3.2, une ligne `)` DU CORPS referme le
                    # `$(…)` et la suite s exécute (mesuré). 2e passe : CHEMIN
                    # D ARRÊT, jamais une reprise en code — tout ce qui suit le
                    # guillemet ouvrant est ANALYSÉ.
                    if text[k:e].lstrip(" \t").startswith(")"):
                        stop[0] = True
                        return n
                    if e >= n:
                        break
                    k = e + 1
                if found >= 0:
                    if found - 1 > i:
                        spans.append((i, found - 1))
                    i = found
                    if not last:
                        e = text.find(NL, i)
                        i = n if e < 0 else e + 1
                    continue
            i = bare(i, word, dash, close, lvl)
            if not last and i < n:
                e = text.find(NL, i)
                i = n if e < 0 else e + 1
        return i
    def code(i, close, lvl):
        if lvl > 64:
            stop[0] = True
            return -1
        head = True
        depth = 0
        docs = []
        while i < n:
            c = text[i]
            if c == NL and docs:
                i = bodies(i + 1, docs, close, lvl)
                docs = []
                head = True
                continue
            if c == BS:
                i += 2
                head = False
                continue
            if c == "#" and head:
                j = text.find(NL, i)
                if j < 0:
                    break
                i = j
                continue
            if close and c == close and (close == BT or depth == 0):
                return i + 1
            if (c == "$" and i + 1 < n and text[i + 1] == "{") or (c == "$" and text.startswith("((", i + 1)) or (c == "(" and text.startswith("(", i + 1)):
                if text[i + 1] == "{":
                    j = opaque(i + 2, "}")
                else:
                    j = opaque(i + (3 if c == "$" else 2), "))")
                if j == -1:
                    if close:
                        return -1
                    break
                if j > 0:
                    i = j
                    head = False
                    continue
            if c == SQ or (c == "$" and i + 1 < n and text[i + 1] == SQ):
                j = single(i)
                if j < 0:
                    i += 1
                    head = False
                    continue
                spans.append((i, j))
                i = j
                head = False
                continue
            if c == DQ:
                mark = len(spans)
                j = double(i, lvl)
                if j < 0:
                    del spans[mark:]
                    if stop[0]:
                        if close:
                            return -1
                        break
                    i += 1
                    head = False
                    continue
                i = j
                head = False
                continue
            if c == "<" and i + 1 < n and text[i + 1] == "<":
                if i + 2 < n and text[i + 2] == "<":
                    i += 3
                    head = True
                    continue
                i, doc = delimiter(i + 2)
                if doc:
                    docs.append(doc)
                head = False
                continue
            if c == "(":
                depth += 1
            elif c == ")" and depth > 0:
                depth -= 1
            i += 1
            head = c in SEP
        if close:
            stop[0] = True
            return -1
        return n
    code(0, "", 0)
    return spans
def ansi_decode(body):
    simple = {"a": chr(7), "b": chr(8), "e": chr(27), "E": chr(27), "f": chr(12), "n": NL, "r": chr(13), "t": TAB, "v": chr(11), BS: BS, SQ: SQ, DQ: DQ, "?": "?"}
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c != BS or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        x = body[i + 1]
        if x in simple:
            out.append(simple[x])
            i += 2
            continue
        if x in "01234567":
            j = i + 1
            v = 0
            while j < n and j < i + 4 and body[j] in "01234567":
                v = v * 8 + int(body[j])
                j += 1
            out.append(chr(v % 256))
            i = j
            continue
        if x in "xuU":
            lim = 2 if x == "x" else (4 if x == "u" else 8)
            j = i + 2
            v = 0
            while j < n and j < i + 2 + lim and body[j] in "0123456789abcdefABCDEF":
                v = v * 16 + int(body[j], 16)
                j += 1
            if j == i + 2:
                out.append(BS + x)
                i += 2
                continue
            if v >= 1114112 or 55296 <= v <= 57343:
                return None
            out.append(chr(v))
            i = j
            continue
        if x == "c":
            return None
        out.append(BS + x)
        i += 2
    s = "".join(out)
    if chr(0) in s:
        s = s[:s.index(chr(0))]
    return s
def find_exec(raw, word, sub):
    # T-01M5D6XS2S : sous `find`, un mot qui PEUT être -exec/-execdir/-ok/-okdir
    # une fois lu par bash — ANSI-C décodé (indécodable : compté), ou `-…` qui
    # porte une expansion ou un antislash — rouvre la commande, comme l awk.
    if raw.startswith("$" + SQ) and raw.endswith(SQ) and len(raw) >= 3:
        w = ansi_decode(raw[2:-1])
        return w is None or w in FIND_EXEC
    return word.startswith("-") and (sub == "exp" or "$" in raw or BS in raw)
def scrub(text):
    buf = []
    last = 0
    for start, end in scrub_spans(text):
        buf.append(text[last:start])
        buf.append("@" * (end - start))
        last = end
    buf.append(text[last:])
    return "".join(buf)
def segments(text, scr):
    out = []
    start = 0
    for cut in COARSE.finditer(scr):
        out.append((text[start:cut.start()], scr[start:cut.start()]))
        start = cut.end()
    out.append((text[start:], scr[start:]))
    return out
def tokenize(text):
    try:
        return shlex.split(text, posix=True), True
    except ValueError:
        return text.split(), False
def executed_word(tok):
    if "$" + DQ in tok:
        tok = tok.replace("$" + DQ, DQ)
    words, honest = tokenize(tok)
    return (words[0] if words else ""), honest
def base_name(word):
    raw = word[1:] if word.startswith(BS) else word
    base = raw.lower().replace(BS, "/").split("/")[-1]
    return re.sub("[.](?:cmd|exe)$", "", base)
def lit_prefix(t):
    m = EXPANSION.search(t)
    return t[:m.start()] if m else t
def normalize(v):
    if not v:
        return ""
    t = str(v).replace(BS, "/")
    try:
        p = Path(t)
        cand = p if p.is_absolute() else Path(REPO) / p
        res = cand.resolve()
        try:
            t = res.relative_to(Path(REPO).resolve()).as_posix()
        except ValueError:
            t = res.as_posix()
    except Exception:
        # Same class-wide catch as the redirect stage copy (T-00000784, pass
        # 4): a symlink loop raised RuntimeError on CPython <= 3.12 and made
        # this pass answer nothing, so an allowlisted rm was refused.
        pass
    while t.startswith("./"):
        t = t[2:]
    return t
def first(x):
    parts = Path(x.replace(BS, "/")).parts
    return parts[0] if parts else ""
def under(x):
    return any(x.startswith(a) and len(x) > len(a) for a in ANCHORS)
def walk_units(scr, frames):
    units = []
    i = 0
    n = len(scr)
    while i < n:
        ch = scr[i]
        if ch == " " or ch == TAB:
            i += 1
            continue
        glued = (i > 0 and scr[i - 1] not in UNIT_STOP) or bool(
            units and units[-1][0] == "close" and units[-1][2] == i
            and units[-1][3] in ("sub", "bt", "param"))
        nxt = scr[i + 1] if i + 1 < n else ""
        if ch in "<>" and nxt == "(":
            frames.append("proc")
            units.append(("open", i, i + 2, "proc", glued))
            i += 2
            continue
        if ch == "$" and (nxt == "(" or (nxt == "{" and not SIMPLE_BRACE.match(scr, i))):
            kind = "sub" if nxt == "(" else "param"
            frames.append(kind)
            units.append(("open", i, i + 2, kind, glued))
            i += 2
            continue
        redir = UNIT_REDIR.match(scr, i)
        if redir:
            units.append(("redir", i, redir.end(), "", False))
            i = redir.end()
            continue
        if ch == "(":
            frames.append("par")
            units.append(("open", i, i + 1, "par", glued))
        elif ch == BT and not (frames and frames[-1] == "bt"):
            frames.append("bt")
            units.append(("open", i, i + 1, "bt", glued))
        elif ch == ")" or ch == BT or (ch == "}" and frames and frames[-1] == "param"):
            units.append(("close", i, i + 1, frames.pop() if frames else "", False))
        elif ch in "|;&{}":
            units.append(("sep", i, i + 1, "", False))
        else:
            j = i
            while j < n and scr[j] not in UNIT_STOP:
                if scr[j] == "$" and j + 1 < n and scr[j + 1] in "({":
                    simple = SIMPLE_BRACE.match(scr, j)
                    if not simple:
                        break
                    j = simple.end()
                    continue
                j += 1
            if j == i:
                j = i + 1
            units.append(("word", i, j, "exp" if "$" in scr[i:j] else "", glued))
            i = j
            continue
        i += 1
    return units
GIT_GLOBAL_VALUE = set("-C -c --git-dir --work-tree --namespace --config-env".split())
def git_subcommand_unit(raw_seg, units, index):
    skip = False
    for pos in range(index + 1, len(units)):
        kind, start, end, sub, glued = units[pos]
        if kind == "redir":
            skip = True
            continue
        if kind != "word":
            return -1
        if skip:
            skip = False
            continue
        if glued:
            continue
        word = executed_word(raw_seg[start:end])[0]
        if word in GIT_GLOBAL_VALUE:
            skip = True
            continue
        if word.startswith("-"):
            continue
        return pos if base_name(word) in VERBS else -1
    return -1
def scan_window(raw_seg, units, index, env):
    amb = False
    evn = False
    for pos in range(index + 1, len(units)):
        kind, start, end, sub, glued = units[pos]
        if kind == "sep" or kind == "close":
            return ("amb" if amb else "none"), 0
        if kind != "word":
            return "amb", 0
        if glued:
            continue
        raw = raw_seg[start:end]
        quoted = SQ in raw or DQ in raw
        word = executed_word(raw)[0]
        if evn:
            evn = False
            if sub == "exp":
                amb = True
            continue
        if quoted and not ASSIGN.match(raw):
            return "amb", 0
        if word.startswith("-"):
            v0, v1 = ENV_OPTIONS[env]
            if word in v0:
                continue
            if word in v1:
                evn = True
                continue
            if word.startswith("--"):
                name, eq, rest = word.partition("=")
                if eq and (name in v0 or name in v1):
                    if sub == "exp":
                        amb = True
                    continue
            elif len(word) > 2 and word[:2] in v1:
                if sub == "exp":
                    amb = True
                continue
            amb = True
            continue
        if env in ("env", "sudo") and ASSIGN.match(word):
            if sub == "exp":
                amb = True
            continue
        if sub == "exp" and word.startswith("$"):
            return "amb", 0
        base = base_name(word)
        if base in ENV_OPTIONS:
            env = base
            continue
        if base in ENVELOPES:
            return "none", 0
        if base == "git":
            return ("amb", 0) if amb else ("git", pos)
        return ("amb" if amb else "none"), 0
    return ("amb" if amb else "none"), 0
def slice_end(scr, offset):
    depth = 0
    k = offset
    n = len(scr)
    while k < n:
        c = scr[k]
        if c == BS:
            k += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return k
            depth -= 1
        elif c == "#" and k > offset and scr[k - 1] in " " + TAB:
            return k
        k += 1
    return n
def mv_glued(word):
    if word.startswith("--"):
        name, eq, value = word[2:].partition("=")
        return value if (eq and name and "target-directory".startswith(name)) else ""
    for k in range(1, len(word)):
        if word[k] == "S":
            return ""
        if word[k] == "t":
            return word[k + 1:]
    return ""
def strip_redirects(raw, scr):
    out = list(raw)
    n = len(scr)
    i = 0
    while i < n:
        if scr[i] not in "<>":
            i += 1
            continue
        start = i
        k = i
        while k > 0 and scr[k - 1].isdigit():
            k -= 1
        if k < i and (k == 0 or scr[k - 1] in " " + TAB):
            start = k
        if i > 0 and scr[i] == ">" and scr[i - 1] == "&":
            start = i - 1
        j = i
        while j < n and scr[j] in "<>&|":
            j += 1
        while j < n and scr[j] in " " + TAB:
            j += 1
        while j < n and scr[j] not in " " + TAB:
            j += 1
        for x in range(start, j):
            out[x] = " "
        i = j
    return "".join(out)
FOUND = []
DENIES = []
PENDING = []
def judge_verb(raw_seg, scr_seg, offset, honest, fed):
    FOUND.append(offset)
    end = slice_end(scr_seg, offset)
    raw = raw_seg[offset:end]
    scr = scr_seg[offset:end]
    if fed:
        DENIES.append(("fed", raw.strip()))
        return
    tokens, readable = tokenize(strip_redirects(raw, scr))
    if not (readable and honest):
        DENIES.append(("shlex", raw.strip()))
        return
    is_mv = bool(tokens) and base_name(tokens[0]) == "mv"
    operands = []
    dd = False
    for tok in tokens[1:]:
        if not dd and tok == "--":
            dd = True
            continue
        if not dd and tok.startswith("-"):
            if is_mv and mv_glued(tok):
                operands.append(mv_glued(tok))
            continue
        operands.append(tok)
    targets = [s for s in (t.strip(DQ + SQ) for t in operands) if s]
    if not targets:
        DENIES.append(("empty", tokens[0] if tokens else ""))
        return
    for tgt in targets:
        lit = lit_prefix(tgt)
        motif = "dissolved" if lit != tgt else "outside"
        if not lit.strip():
            DENIES.append(("dissolved", tgt))
            continue
        r = normalize(lit)
        if not r:
            DENIES.append(("dissolved", tgt))
            continue
        if r.startswith("/"):
            if not (under(lit) and under(r)):
                DENIES.append((motif, tgt if lit != tgt else r))
            continue
        if first(r) not in LISTED or (not lit.startswith("/") and first(lit) not in LISTED):
            DENIES.append((motif, tgt if lit != tgt else r))
            continue
        PENDING.append(r)
text = sys.stdin.read()
scrubbed = scrub(text)
unit_frames = []
frames = []
for raw_seg, scr_seg in segments(text, scrubbed):
    cmdpos, wrapped, probe, fed, skip = True, False, False, False, False
    cmdname = ""
    gpos = -1
    exempt = -1
    units = walk_units(scr_seg, unit_frames)
    for index, (kind, start, end, sub, glued) in enumerate(units):
        if kind == "sep":
            cmdpos, wrapped, probe, fed, skip = True, False, False, False, False
            cmdname = ""
            continue
        if kind == "redir":
            skip = True
            continue
        if kind == "open":
            frames.append((cmdpos, wrapped, probe, fed, sub, glued or skip, cmdname))
            cmdpos, wrapped, probe, fed, skip = sub != "param", False, False, False, False
            cmdname = ""
            continue
        if kind == "close":
            skip = False
            if frames:
                cmdpos, wrapped, probe, fed, sub, glued, cmdname = frames.pop()
                if cmdpos and not glued and sub in ("sub", "bt", "param"):
                    cmdpos, wrapped, fed = False, True, True
            else:
                cmdpos, wrapped, probe, fed = True, False, False, False
            continue
        if skip or glued:
            skip = False
            continue
        word, honest = executed_word(raw_seg[start:end])
        base = base_name(word)
        if index == gpos:
            if wrapped == 1:
                exempt = git_subcommand_unit(raw_seg, units, index)
            gpos = -1
        if cmdpos:
            if not probe and base in VERBS:
                judge_verb(raw_seg, scr_seg, start, honest, fed)
            if base in PROBES:
                probe, cmdpos = True, False
                continue
            if base in ENVELOPES:
                if not wrapped:
                    wrapped = 1
                if base not in ENV_OPTIONS:
                    if wrapped == 1:
                        wrapped = 3
                elif wrapped != 3:
                    state, where = scan_window(raw_seg, units, index, base)
                    if state == "amb":
                        wrapped = 2
                    elif state == "git" and wrapped == 1:
                        gpos = where
                if base in FEEDERS:
                    fed = True
                continue
            if base in KEYWORDS:
                continue
            if wrapped and word in ("-v", "-V"):
                probe = True
                continue
            if word.startswith("-"):
                continue
            if ASSIGN.match(word):
                continue
            if sub == "exp" and scr_seg[start] == "$":
                cmdpos, wrapped, fed = False, True, True
                continue
            cmdpos = False
            cmdname = base
        else:
            if word in FIND_EXEC or (cmdname == "find" and find_exec(raw_seg[start:end], word, sub)):
                cmdpos = True
                fed = True
                continue
            if wrapped and not probe and base in FEEDERS:
                fed = True
            if wrapped and not probe and base in VERBS and index != exempt:
                judge_verb(raw_seg, scr_seg, start, honest, fed)
if PENDING:
    rels = sorted(set(PENDING))
    answer = None
    try:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        proc = subprocess.run(["git", "ls-files", "-z", "--"] + [":(icase)" + r for r in rels],
            cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        if proc.returncode == 0:
            answer = [p for p in proc.stdout.decode("utf-8", "surrogateescape").split(chr(0)) if p]
        elif proc.returncode == 128 and b"not a git repository" in proc.stderr:
            answer = []
    except Exception:
        answer = None
    hit = set()
    if answer is not None:
        for p in answer:
            pl = p.lower()
            owners = [r for r in rels if pl == r.lower() or pl.startswith(r.lower() + "/") or (
                any(c in GLOB for c in r) and (fnmatch.fnmatchcase(pl, r.lower()) or fnmatch.fnmatchcase(pl, r.lower() + "/*")))]
            if not owners:
                answer = None
                break
            hit.update(owners)
    for r in rels:
        if answer is None:
            DENIES.append(("git", r))
        elif r in hit:
            DENIES.append(("tracked", r))
if not FOUND:
    sys.stdout.write("NONE" + NL)
elif not DENIES:
    sys.stdout.write("OK" + NL)
else:
    for motif, path in DENIES:
        sys.stdout.write("DENY" + TAB + motif + TAB + path.replace(TAB, " ").replace(NL, " ") + NL)
') || RMMV_RC=$?
# ^ liste AND-OR (T-00000784, passe 2) : sous un errexit hérité, la forme
# `X=$(…); X_RC=$?` sortait avec le code de la passe plantée (9) au lieu du
# refus fail-closed ci-dessous — `rm -rf src/x` partait ((z21)).
fi
# Lecture de la sentinelle AU NIVEAU SUPÉRIEUR, par une HERESTRING et non un
# heredoc. Mesuré à l'écriture de T-00000762, fichier par fichier : un TROISIÈME
# `done <<EOF` dans ce fichier (après ceux de l'étage redirection et des
# verdicts) fait échouer le parseur du SAST sur le fichier ENTIER — retirer
# n'importe lequel des trois le rend lisible, changer de délimiteur non — et un
# heredoc qui nourrit un `while` imbriqué dans deux `if` échoue aussi, alors que
# `bash -n` accepte les deux. Même lecture pour bash (redirection, pas de
# sous-shell, même saut de ligne final). RMMV est vide sans `HIT`.
# GRAMMAIRE FERMÉE (T-00000784, passe 2 — même classe que l'étage redirection,
# relevée et mesurée sur 10ed6894) : ce lecteur gardait le DERNIER état lu, donc
# une ligne `OK` parasite APRÈS des lignes DENY rendait la passe « ok » et
# `rm -rf src/x` partait rc 0 ((z23)). Désormais `OK` et `NONE` ne valent que
# SEULS, `DENY` jamais après eux, et toute autre ligne est hors grammaire :
# RMMV_BAD, lu plus bas comme une passe qui n'a pas répondu — un refus. Le
# retour chariot final est retiré des trois champs, comme à l'étage
# redirection (python en mode texte sous Windows). Ce retrait LAISSE PASSER ce
# qui était refusé À TORT (correction de la passe 3 : ce commentaire disait
# qu'il ne changeait rien côté laisser-passer) — sans lui, `OK\r` se lisait
# « pas de sentinelle », donc toute commande rm/mv reconnue était refusée sous
# Windows, liste blanche comprise. Voulu, et épinglé dans les deux sens par
# (z24) (la liste blanche passe) et (z24b) (hors liste, refus par opérande,
# chemin lu sans `\r`). Sans `HIT`, la ligne vide de RMMV pose RMMV_BAD, que seul le
# bloc `HIT` lit.
RMMV_STATE=""; RMMV_BAD=0; RMMV_NAMED=""; RMMV_COUNT=0; RMMV_LIT=0; RMMV_PIPE=0; RMMV_SHLEX=0; RMMV_GITQ=0
while IFS="$(printf '\t')" read -r rv_kind rv_motif rv_path; do
  case "$rv_kind" in
    *"$PY_CR") rv_kind="${rv_kind%?}" ;;
  esac
  case "$rv_motif" in
    *"$PY_CR") rv_motif="${rv_motif%?}" ;;
  esac
  case "$rv_path" in
    *"$PY_CR") rv_path="${rv_path%?}" ;;
  esac
  case "$rv_kind" in
    OK)
      [ -z "$RMMV_STATE" ] || RMMV_BAD=1
      RMMV_STATE="ok" ;;
    NONE)
      [ -z "$RMMV_STATE" ] || RMMV_BAD=1
      RMMV_STATE="none" ;;
    DENY)
      case "$RMMV_STATE" in
        ok|none) RMMV_BAD=1 ;;
      esac
      RMMV_STATE="deny"
      case "$rv_motif" in
        dissolved) RMMV_LIT=1 ;;
        empty|fed) RMMV_PIPE=1 ;;
        shlex) RMMV_SHLEX=1 ;;
        git) RMMV_GITQ=1 ;;
        *)
          RMMV_COUNT=$((RMMV_COUNT + 1))
          if [ "$RMMV_COUNT" -le 3 ]; then
            RMMV_NAMED="${RMMV_NAMED:+$RMMV_NAMED, }$rv_path ($rv_motif)"
          fi
          ;;
      esac
      ;;
    *) RMMV_BAD=1 ;;
  esac
done <<< "$RMMV"

# --- Garde 1b : rm/mv réel, JUGÉ PAR OPÉRANDE --------------------------------
# Le pré-test `..` sur la commande ENTIÈRE reste (revue de sécurité, lot 3,
# HIGH) : `rm -rf /tmp/../etc` sort de `/tmp/`, et une traversée ne chevauche
# jamais la liste. Puis le verdict de la passe ci-dessus, lu motif par motif,
# chacun porteur de « checkpoint » : (i) opérande DISSOUS, jugé par son préfixe
# littéral seul ; (ii) aucun opérande, ou opérandes venus d'un tube ; (iii)
# jugé et refusé — trois chemins NOMMÉS, le reste COMPTÉ ; (iv) git n'a pas
# répondu (Claude seul : les hôtes python lisent une panne git comme « non
# suivi », asymétrie nommée au plan de T-00000762).
if [ "$RM_HIT" -eq 1 ]; then
  RMMV_WHY=""
  case "$CMD" in
    *".."*) RMMV_WHY=" A '..' anywhere in the command disqualifies it first: a traversal (rm -rf /tmp/../etc) never rides the list." ;;
  esac
  if [ -z "$RMMV_WHY" ]; then
    if [ "$RMMV_RC" -ne 0 ] || [ -z "$RMMV_STATE" ] || [ "$RMMV_BAD" -eq 1 ]; then
      RMMV_WHY=" The per-operand pass did not answer (exit $RMMV_RC, no sentinel, or a line outside its output): refused rather than guessed."
    elif [ "$RMMV_STATE" = "none" ]; then
      RMMV_WHY=" The per-operand pass found no rm/mv where the recognition stage saw one: refused rather than guessed."
    elif [ "$RMMV_STATE" = "deny" ]; then
      if [ "$RMMV_COUNT" -gt 3 ]; then
        RMMV_NAMED="$RMMV_NAMED, +$((RMMV_COUNT - 3)) more"
      fi
      if [ "$RMMV_COUNT" -gt 0 ]; then
        RMMV_WHY="$RMMV_WHY Judged operand by operand and refused: $RMMV_NAMED."
      fi
      if [ "$RMMV_LIT" -eq 1 ]; then
        RMMV_WHY="$RMMV_WHY An operand carrying an expansion (\$HOME, \$(pwd), a backtick) is judged by its LITERAL prefix only — the text before the expansion — and that prefix is empty or reaches nothing STRICTLY below an accepted directory (/tmp/\$X stops at /tmp/ itself; the expansion is dissolved, not judged)."
      fi
      if [ "$RMMV_PIPE" -eq 1 ]; then
        RMMV_WHY="$RMMV_WHY No destructive-verb operand could be resolved, or its operands come from a pipe (xargs, parallel, find -exec/-ok — through an envelope, a process substitution or a redirect too) or from a command an expansion hides (\$X rm …): a bare rm, or one fed by a pipe, is refused whatever its static operands."
      fi
      if [ "$RMMV_SHLEX" -eq 1 ]; then
        RMMV_WHY="$RMMV_WHY The quoting of a rm/mv could not be read (shlex refused it): refused rather than guessed."
      fi
      if [ "$RMMV_GITQ" -eq 1 ]; then
        RMMV_WHY="$RMMV_WHY git ls-files gave no usable answer (timeout, error, or output this pass could not attribute), so whether those paths are tracked is unknown: refused."
      fi
    fi
  fi
  if [ -n "$RMMV_WHY" ]; then
    echo "WARNING by hook: rm/mv via Bash bypasses Claude Code checkpoints (not rewindable).$RMMV_WHY Prefer Edit/Write for tracked files; otherwise write the path literally, under /tmp/ (its resolved form, e.g. /private/tmp/ on macOS, is accepted too) or under a repository .tmp/, node_modules/, dist/, build/ or .cache/ that git does not track — or ask the user to approve this exact command. A relative path is judged against the project root, never a cd in the command. Named, not closed: the \`)\` of a \`case\` pattern inside a quoted \`\"\$(…)\"\` ends the substitution early for this guard, which reads the rest as quoted data." >&2
    deny rm-mv-bypass-checkpoint
  fi
fi
exit 0
