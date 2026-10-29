#!/usr/bin/env bash
# PreToolUse [Bash] — bloque une INSTALLATION de skill non auditée. Le
# skills-resolver journalise chaque artefact vérifié dans
# .agents/state/gates/AUDIT_LOG, une ligne par artefact, au format documenté en
# tête de ce fichier : `<owner>/<repo>[#<skill>] audit=pass|fail pinned=<sha> …`.
#
# LE DÉFAUT CORRIGÉ (mesuré en session le 2026-08-06). Ce garde matchait par
# SOUS-CHAÎNE (`case "$CMD" in *"skills add"*`) : il bloquait donc toute commande
# qui PARLE de l'installation au lieu d'en être une. Un `tasks.py new "corriger
# le garde: npx skills add bloque le board"` a été refusé — écriture de board
# perdue — avec en prime un `xargs: unmatched double quote`, parce que le ref
# extrait passait par `xargs`, qui réinterprète les guillemets de la charge utile.
# Même défaut, même correctif que `.agents/bin/post-task-done-index.sh` (l. 36-44,
# où un `*"tasks.py"*"done"*` matchait toute commande MENTIONNANT le nom du
# hook) : on ancre sur la FORME RÉELLE de la commande exécutée, jamais sur une
# mention.
#
# Trois étages, dans cet ordre :
#   0.5. les CORPS DE HEREDOC À DÉLIMITEUR CITÉ (`<<'FIN'`, `<<"FIN"`) sont
#      blanchis AVANT tout balayage de guillemets : bash n'y exécute rien et n'y
#      cite rien non plus — c'est une REDIRECTION, donc de la donnée 100 %
#      littérale — et une apostrophe qui y vit ne doit jamais pouvoir s'apparier
#      avec un guillemet de CODE situé plus loin (voir le CRITICAL n°2 ci-dessous);
#   1. les segments ENTRE GUILLEMETS (simples ou doubles) sont neutralisés avant
#      toute reconnaissance, par un scanner CONSCIENT DE L'ÉCHAPPEMENT : une
#      commande d'installation citée dans un titre de tâche, un message de commit
#      ou une entrée de ledger est une DONNÉE, pas une exécution ;
#   2. ce qui reste doit matcher une forme d'invocation ANCRÉE (runner + verbe),
#      options éventuelles admises entre les deux.
# Aucun `xargs`, aucun `eval` : la charge utile n'est jamais re-découpée par un
# shell. Un scanner python la neutralise (sur STDIN, jamais en argv), awk la lit
# — ni l'un ni l'autre n'interprète les guillemets ou les métacaractères qu'elle
# contient.
#
# LE CONTOURNEMENT DE CLASSE 1 FERMÉ (T-00000181). L'étage 1 était un sed en une
# passe, `s/'[^']*'|"[^"]*"/ @@ /g`, AVEUGLE À L'ÉCHAPPEMENT : il lisait un
# guillemet précédé d'un `\` comme un délimiteur ouvrant. Or bash le rend
# LITTÉRAL, donc dans `echo \" && npx skills add other/pkg \"` le sed voyait un
# seul segment cité couvrant l'installation entière — le séparateur, le runner et
# le ref — l'étage 2 ne reconnaissait plus rien, et un skill NON AUDITÉ
# s'installait sans que l'AUDIT_LOG soit jamais consulté. Le sed a été remplacé
# par le PORT du scanner des hôtes python (`quoted_spans()`,
# .codex/hooks/audit_gate.py). Le contrat de sortie ne bouge pas — un segment
# cité devient toujours ` @@ ` — donc l'étage 2 est inchangé, à la ligne près.
#
# LE CONTOURNEMENT DE CLASSE 1 FERMÉ N°2 : L'ÉTAGE HEREDOC MANQUANT (T-00000208,
# revue de sécurité, CRITICAL). Ce hook passait de la commande brute au balayage
# de guillemets TEXTE ENTIER sans aucun étage heredoc — ni délimiteur cité, ni
# délimiteur nu. Mesuré par exécution : sur `cat <<'EOF'` ⏎ `it's not code` ⏎
# `EOF` ⏎ `npx skills add other/pkg` ⏎ `echo 'end'`, l'apostrophe de « it's » —
# qui vit dans un corps à délimiteur CITÉ, donc de la donnée 100 % littérale que
# bash ne cite ni n'exécute — s'appariait avec le guillemet ouvrant de
# `echo 'end'` et blanchissait tout l'intervalle, LIGNE D'INSTALLATION RÉELLE
# COMPRISE : exit 0, silencieux, l'AUDIT_LOG jamais consulté, un skill NON AUDITÉ
# installé. Ce n'est pas un cas tordu — `git commit -F - <<'EOF' … EOF` est
# l'idiome que ce dépôt prescrit pour ses messages de commit, et l'anglais est
# plein d'apostrophes. Contre-contrôle qui a désigné le correctif : la MÊME
# construction contre `safe-bash.sh` sortait 2, correctement bloquée, parce que
# son étage 0.5 blanchit le corps cité AVANT l'étage 1 — le faux appariement n'a
# jamais lieu. Correctif : cet étage 0.5 est PORTÉ ICI VERBATIM, comme l'étage 1
# l'était déjà, jamais réécrit en une seconde variante.
# LA DÉCISION QUE CELA SUPPLANTE, dite plutôt que tue : D4 du plan (« ne pas
# toucher aux audit-gate, la symétrie inter-hôtes est déjà là ») reposait sur une
# prémisse que le passage au texte entier invalide — l'absence d'étage heredoc
# était inoffensive sous le balayage PAR LIGNE, elle est un FAIL-OPEN sous le
# texte entier. Un CRITICAL de classe 1 n'est pas waivable : D4 est supplantée
# par la mesure, et c'est journalisé (S-00000404).
#
# Sortie : 2 = bloqué (installation sans entrée `audit=pass`), 0 = laissé passer.
#
# PLANTAGE = REFUS, CÔTÉ JAMBE (T-01M5CH9GATN4G2SP1VKCVR1HC3). La jambe Claude de
# `.claude/settings.json` lance ce script sous `.agents/security/garde-fermee.sh
# --echeance=7` : rc 0 et rc 2 sont transmis tels quels, mais tout autre rc (un
# plantage que ce script n'a pas rattrapé : signal, `set -u`, interpréteur
# absent) et un délai de 7 s dépassé deviennent un REFUS (`BLOCKED:`, exit 2).
# Cela CONTREDIT la posture T-00000181 pour ces cas-là, par décision : un
# plantage persistant refuse désormais tous les appels Bash. Les pannes
# d'INSTRUMENT que ce script rattrape (`degraded`, ci-dessous) restent un exit 0
# annoncé. Le comportement de ce script n'a pas changé ; seule sa jambe l'a fait.
#
# CHARGE UTILE ILLISIBLE ⇒ 0, MAIS À VOIX HAUTE (T-00000140). Ce garde sortait 0
# en SILENCE quand python était absent : la charge utile PreToolUse est du JSON,
# sans interpréteur pour la lire il ne voit rien. Le comportement était juste —
# un garde absent ne doit jamais bloquer, sinon l'hôte boucle — mais muet, et la
# ligne de commentaire qui tenait ici revendiquait déjà « COVERAGE DEGRADED »
# alors qu'aucun code ne le disait : le défaut était exactement cet écart. Un
# garde de sécurité qui disparaît sans le dire se lit comme un garde qui a
# vérifié, ce que la doctrine du kit refuse (AGENTS.md § Full power : « un log()
# est dû chaque fois qu'une borne a été appliquée : une troncature silencieuse se
# lit comme une couverture complète »). Format aligné sur `gitleaks-scan.sh` /
# `semgrep-scan.sh` (« COVERAGE DEGRADED: … » sur stderr), doublé d'un
# `systemMessage` sur stdout — précédent `post-edit-check.sh` l. 18 : c'est la
# seule surface qu'un humain voit vraiment sur un hook qui sort 0. Exit 0
# impératif sur ce chemin.
set -u

# La racine, sans supposer l'hôte (même ancre que post-task-done-index.sh).
DIR="${CLAUDE_PROJECT_DIR:-}"
[ -n "$DIR" ] || DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

degraded() { # degraded <why> — le dire, ne jamais bloquer.
  echo "COVERAGE DEGRADED: audit-gate — $1; skill installs are NOT gated for this call." >&2
  # `%s` reçoit un littéral défini ICI (jamais la charge utile) : aucun
  # guillemet ne peut s'y glisser et casser le JSON rendu à l'hôte.
  printf '{"systemMessage": "COVERAGE DEGRADED: audit-gate (unaudited skill-install gate) — %s. Skill installs are NOT gated for this call."}' "$1"
  exit 0
}

INPUT=$(cat 2>/dev/null || true)
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
  degraded "no python on PATH to read the PreToolUse payload"
fi
CMD=$(printf '%s' "$INPUT" | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(d.get('tool_input',{}).get('command',''))" 2>/dev/null) \
  || degraded "the PreToolUse payload is not readable JSON"
# Charge utile LUE et commande vide : rien à garder, et ce n'est PAS une
# dégradation — ne pas confondre les deux, le silence est correct ici (arm d5).
[ -n "$CMD" ] || exit 0

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
# Un plantage NON rattrapé du script, lui, est refusé par sa jambe (en-tête,
# « PLANTAGE = REFUS, CÔTÉ JAMBE »).
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
    spans = []
    i = 0
    n = len(text)
    head = True
    while i < n:
        ch = text[i]
        if ch == BS:
            i += 2
            head = False
            continue
        if ch == "#" and head:
            j = text.find(NL, i)
            if j < 0:
                break
            i = j + 1
            head = True
            continue
        if ch != SQ and ch != DQ:
            i += 1
            head = ch in SEP
            continue
        end = i + 1
        while end < n:
            if ch == DQ and text[end] == BS:
                end += 2
                continue
            if text[end] == ch:
                break
            end += 1
        if end >= n:
            i += 1
            head = False
            continue
        spans.append((i, end + 1))
        i = end + 1
        head = False
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
        if ch == SQ or ch == DQ:
            end = i + 1
            while end < n:
                if ch == DQ and line[end] == BS:
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

# --- Étage 1 : neutraliser les segments cités -------------------------------
# Scanner CONSCIENT DE L'ÉCHAPPEMENT (T-00000181), port règle pour règle de
# `quoted_spans()` (.codex/hooks/safe_bash.py l. 124-180, dont audit_gate.py porte
# la copie), appliqué au TEXTE ENTIER :
#   - hors citation un `\` échappe le caractère SUIVANT, donc un nombre IMPAIR de
#     `\` devant un guillemet le rend LITTÉRAL et n'ouvre AUCUN segment ; un
#     nombre PAIR le laisse ouvrir un vrai segment, et
#     `echo \\" && npx skills add x \\"` reste une MENTION (c'est le contrôle qui
#     interdit le correctif « ignorer tous les backslashes ») ;
#   - dans `"…"` le `\` échappe encore ; dans `'…'` il n'échappe rien ;
#   - un guillemet NON APPARIÉ ne ferme rien, donc n'ouvre rien : le reste du
#     texte redevient analysable (l'apostrophe de « l'index ») ;
#   - c'est le guillemet OUVRANT le plus à gauche qui gagne, donc `"… '…' …"` est
#     un seul segment double et n'est pas coupé au guillemet simple interne.
# CE QUI NE VOYAGE PAS depuis le python : son contrat ISOMÉTRIQUE (un `@` par
# caractère). L'étage 2 lit le texte NEUTRALISÉ lui-même (match/RSTART/RLENGTH sur
# SCRUBBED), jamais un offset reporté sur la charge brute — le contrat de sortie
# reste donc ` @@ `, à l'identique, et l'étage 2 ne change pas d'une ligne.
# TEXTE ENTIER, JAMAIS LIGNE PAR LIGNE (T-00000208, D1). Ce scanner lit la charge
# comme UN texte, exactement comme `scrub_quoted()` côté python — un segment cité
# qui enjambe un retour à la ligne est donc neutralisé, parce que bash le cite
# VRAIMENT. Le balayage par ligne qui vivait ici prétendait fermer un fail-open ;
# il en OUVRAIT un, mesuré : sur `echo 'a` ⏎ `b' && npx skills add other/pkg &&
# echo 'x'`, la ligne 2 appariait le `'` de `b'` avec celui de `echo 'x'` et
# masquait l'installation que bash exécute pour de bon — le garde se taisait. En
# texte entier c'est le `'a` ⏎ `b'` de bash qui est neutralisé, l'installation
# reste nue et l'étage 2 la voit.
#
# LA FRONTIÈRE DE COMMENTAIRE, ET LA PROSE QU'ELLE CORRIGE (revue de sécurité de
# classe 1, CRITICAL). Ce paragraphe affirmait que le résidu du texte entier
# vivait « en zone NON-CODE (corps de heredoc à délimiteur nu, commentaires),
# pas en zone code ». C'ÉTAIT FAUX : un `#` de commentaire portant un guillemet
# non apparié s'appariait avec un vrai guillemet situé PLUS LOIN et blanchissait
# tout l'intervalle — Y COMPRIS UNE LIGNE DE CODE RÉELLE, sur une AUTRE ligne
# physique, que bash exécute pour de bon. Mesuré par exécution contre ce hook :
# `# don't run this` ⏎ `npx skills add other/pkg && echo 'ok'` sortait 0 EN
# SILENCE là où HEAD sortait 2 — un skill NON AUDITÉ s'installait sans que
# l'AUDIT_LOG soit jamais consulté. Le résidu n'était donc pas cantonné à la
# donnée : il ATTEIGNAIT le code. Dit, pas tu.
# LE CORRECTIF RÉUTILISE UNE RÈGLE QUI EXISTAIT DÉJÀ, il n'en écrit pas une
# seconde : c'est la clause (b'') de l'étage 0.5 de `safe-bash.sh`, mot pour mot
# — un `#` NON CITÉ, non échappé, en DÉBUT DE MOT (précédé d'un blanc, d'un début
# de ligne, ou d'un séparateur de `SEP`) coupe la LIGNE PHYSIQUE courante. Même
# constante `SEP`, même suivi de `head`, mêmes exceptions : jamais après `$` ni
# `{`, sinon `$#` et `${#v}` cesseraient d'être des expansions. La coupe est
# appliquée PENDANT le balayage des guillemets, donc un guillemet situé après un
# tel `#` ne peut jamais participer à un appariement traversant la fin de cette
# ligne — la sémantique de bash, où un commentaire s'arrête à sa ligne physique
# quel que soit son contenu. Ce hook a désormais SA PROPRE jumelle locale — la
# clause (b'') de l'étage 0.5 ci-dessus, porté verbatim depuis `safe-bash.sh`
# (CRITICAL n°2) — exactement comme `safe-bash.sh` : les deux fichiers portent
# donc les deux copies, et les deux suites épinglent LA MÊME charge sur LE MÊME
# scanner dupliqué, donc une divergence entre les copies rougit.
# CE QUE LA COUPE NE FAIT PAS, ET C'EST DÉLIBÉRÉ : elle n'EFFACE rien. Le texte
# du commentaire n'est pas blanchi, seulement exclu de l'appariement des
# guillemets, donc il redescend TEL QUEL à l'étage 2 et y est ANALYSÉ. Dégrader
# vers ANALYSÉ, jamais vers effacement : en erreur cette clause ne produit qu'un
# FAUX POSITIF — un commentaire qui contient une vraie forme d'installation peut
# être refusé alors que bash ne l'exécute pas. Côté sûr, assumé, prix nommé.
# CE QUI RESTE UN TROU, réduit mais NON refermé — ET CETTE PHRASE A DÉJÀ ÉTÉ
# FAUSSE UNE FOIS, ce qui est la raison de la réécrire ici plutôt que de la
# retoucher. Elle bornait le résidu au corps d'un heredoc à délimiteur NU en
# laissant croire que le délimiteur CITÉ, lui, était couvert : ce hook n'avait
# alors AUCUN étage heredoc, ni cité ni nu (CRITICAL n°2, mesuré par exécution —
# `cat <<'EOF'` ⏎ `it's not code` ⏎ `EOF` ⏎ `npx skills add other/pkg` ⏎ `echo
# 'end'` sortait 0 EN SILENCE). Une prose plus ÉTROITE que le code est la même
# forme de défaut que celle du CRITICAL précédent, et elle se paie deux fois :
# elle cache le trou ET elle justifie de ne pas le fermer. L'état RÉEL, maintenant
# que l'étage 0.5 est là : le corps à délimiteur CITÉ est BLANCHI, donc plus
# aucune apostrophe n'en sort ; le corps à délimiteur NU reste ANALYSÉ, et c'est
# DÉLIBÉRÉ — bash y développe `$(…)`, donc le blanchir serait fail-open — si bien
# qu'une apostrophe qui y vit peut encore s'apparier avec du code plus loin. Ce
# résidu-là est le seul qui subsiste sur cet axe, et CE QUI LE TIENT EST NOMMÉ
# AVEC SON IDENTIFIANT, jamais en prose vague : l'arm KNOWN-GAP (j6) de
# `audit-gate.test.sh`, qui rougira bruyamment le jour où le trou se comble, ET
# la tâche board T-00000224, qui le porte pour ce hook comme pour `safe-bash.sh`
# (T-00000225 porte les mêmes contournements sur les quatre gardes python de
# `.codex`/`.gemini`). L'IDENTIFIANT EST LE POINT, et il est payé : « versé au
# board » est invérifiable, donc indistinguable d'une prose qui affirme plus que
# l'état ne tient — un relevé de ce fichier a manqué T-00000224 et a conclu à son
# absence. Un id se vérifie en une commande. Dit, pas tu.
# Les résidus PROPRES à l'étage 0.5
# (`<<'W'` en position non-redirection, `<<\EOF`, lignes de continuation) sont
# énumérés dans son propre en-tête ci-dessus, avec leur polarité.
# QUOTAGE, ET C'EST LA PARTIE FRAGILE : le programme est tenu par des guillemets
# SIMPLES bash et n'en contient AUCUN — les deux caractères de citation, et le
# backslash lui-même, y sont écrits `\x27` / `\x22` / `\x5c` dans des littéraux
# python. Jamais de splice `'\''`. La charge utile arrive par STDIN, jamais par
# argv : elle n'est à aucun moment rendue à un shell.
# DUPLIQUÉ VERBATIM depuis l'étage 1 de `safe-bash.sh`, délibérément : un hook qui
# `source` un fichier d'aide voisin acquiert un mode de panne (fichier absent, non
# lisible) que le hook autonome n'a pas.
SCRUBBED=$(printf '%s' "$HEREFREE" | "$PY" -c '
import sys
SQ = "\x27"
DQ = "\x22"
BS = "\x5c"
BT = "\x60"
NL = "\x0a"
SEP = " \t;&|()" + BT + NL
def scrub_spans(text):
    spans = []
    i = 0
    n = len(text)
    head = True
    while i < n:
        ch = text[i]
        if ch == BS:
            i += 2
            head = False
            continue
        if ch == "#" and head:
            j = text.find(NL, i)
            if j < 0:
                break
            i = j + 1
            head = True
            continue
        if ch != SQ and ch != DQ:
            i += 1
            head = ch in SEP
            continue
        end = i + 1
        while end < n:
            if ch == DQ and text[end] == BS:
                end += 2
                continue
            if text[end] == ch:
                break
            end += 1
        if end >= n:
            i += 1
            head = False
            continue
        spans.append((i, end + 1))
        i = end + 1
        head = False
    return spans
text = sys.stdin.read()
buf = []
last = 0
for start, end in scrub_spans(text):
    buf.append(text[last:start])
    buf.append(" @@ ")
    last = end
buf.append(text[last:])
sys.stdout.write("".join(buf))
') || degraded "the quote scrub failed"
# POSTURE DÉGRADÉE (T-00000181). Si le scanner échoue, ce garde N'A PAS VU la
# commande : il le DIT et sort 0, exactement comme le chemin « pas de python »
# ci-dessus. Jamais un exit 2 — un garde qui bloque quand son instrument casse
# bloque TOUS les appels Bash et fait boucler l'hôte (ce que la jambe enveloppée
# accepte désormais pour un plantage NON rattrapé du script : en-tête,
# « PLANTAGE = REFUS, CÔTÉ JAMBE ») — et jamais un fail-open
# muet, qui se lirait comme un garde ayant vérifié. Deux symptômes sont
# couverts : le statut de sortie ci-dessus, et une sortie VIDE sur une entrée qui
# ne l'était pas (le scanner ne peut jamais raccourcir une ligne jusqu'au vide,
# donc ce cas ne peut venir que d'une panne).
if [ -n "$CMD" ] && [ -z "$SCRUBBED" ]; then
  degraded "the quote scrub failed (empty output on a non-empty command)"
fi

# --- Étage 2-bis : `skills_github_fallback.py … install <id>` en position de
# commande (T-00000461). Même style awk que l'étage 2 (mawk-safe, intervalles
# explicites). La mention CITÉE de la commande est déjà réduite à ` @@ ` par
# l'étage 1 (donc inoffensive) ; une mention NUE est VUE et gatée — même prix de
# faux positif que les runners npx. On extrait l'`<id>` et la présence de
# `--confirmed-by`, puis on appelle la sous-commande `gate` (policy +
# agent-caller SEULS, ni AUDIT_LOG ni réseau ni écriture) EN POSANT le marqueur
# `AGENTS_HOOK_HOST` — un hook EST un contexte agent, et sans ce marqueur un
# `--confirmed-by x` traverserait. rc 0 → on continue vers l'étage 2 ; rc ≠ 0 →
# refus + exit 2 ; script/py absent → degraded (annoncé, exit 0). NOTE : le motif
# suit l'étage 2 et n'admet que des options SANS valeur avant `install` (un
# `--root <val> install` échappe, non gaté — borne dite, comme le reste).
# Token-based extraction, deliberately WITHOUT RSTART/RLENGTH: the (q13) test
# shims any awk program carrying RSTART to prove the STAGE-2 degraded posture, and
# that shim must keep hitting the SOLE RSTART program (stage 2). So this stage
# finds the `.../skills_github_fallback.py` token, skips dash-options, and takes
# the token after `install` as the id (a `--root <val> install` escapes — stated).
FB=$(printf '%s\n' "$SCRUBBED" | awk '
{
  sub(/\r$/, "")
  py = 0; id = ""; conf = ""
  m = split($0, u, /[ \t]+/)
  for (i = 1; i <= m; i++) {
    if (u[i] ~ /skills_github_fallback\.py$/) py = i
    if (u[i] == "--confirmed-by" && i < m) conf = u[i+1]
  }
  if (py > 0) {
    j = py + 1
    while (j <= m && substr(u[j], 1, 1) == "-") j++
    if (j <= m && u[j] == "install" && j < m) id = u[j+1]
  }
  sub(/[;&|)`].*$/, "", id)
  sub(/[;&|)`].*$/, "", conf)
  if (id != "") { print id; print conf; exit }
}
') || degraded "the fallback-install scan failed"
FB_ID=$(printf '%s\n' "$FB" | sed -n '1p')
FB_CONF=$(printf '%s\n' "$FB" | sed -n '2p')
if [ -n "$FB_ID" ]; then
  FBSCRIPT="$DIR/.agents/bin/skills_github_fallback.py"
  if [ -n "$PY" ] && [ -f "$FBSCRIPT" ]; then
    # Assignation PRÉFIXÉE (comme EVT_HOST de gitleaks-scan.sh:61), visible du
    # sous-processus, jamais exportée au hook entier ; valeur de l'appelant
    # conservée (`:-`), `claude` n'étant que le défaut de l'hôte dont le registre
    # ne passe aucune variable.
    if [ -n "$FB_CONF" ]; then
      GATE_OUT=$(AGENTS_HOOK_HOST="${AGENTS_HOOK_HOST:-claude}" "$PY" "$FBSCRIPT" --root "$DIR" gate "$FB_ID" --confirmed-by "$FB_CONF" 2>&1); grc=$?
    else
      GATE_OUT=$(AGENTS_HOOK_HOST="${AGENTS_HOOK_HOST:-claude}" "$PY" "$FBSCRIPT" --root "$DIR" gate "$FB_ID" 2>&1); grc=$?
    fi
    if [ "$grc" -ne 0 ]; then
      printf '%s\n' "$GATE_OUT" >&2
      echo "BLOCKED by audit gate: skills_github_fallback install refused by its confirm gate (rc $grc)" >&2
      bash "$DIR/.claude/hooks/emit-event.sh" hook.deny guard=audit-gate rule=skills-fallback-install-unconfirmed "path=$FB_ID" >/dev/null 2>&1 || true
      exit 2
    fi
  else
    degraded "skills_github_fallback.py or python missing — fallback-install not gated"
  fi
fi

# --- Étage 2 : reconnaître la forme exécutée, en extraire le ref -------------
# awk, pas grep+sed+xargs : une seule passe fait la reconnaissance ET
# l'extraction, sans jamais rendre la charge utile à un shell. La casse est
# ignorée en matchant sur tolower() — même longueur, donc RSTART/RLENGTH
# indexent la ligne d'origine et le ref sort dans sa casse réelle.
REF=$(printf '%s\n' "$SCRUBBED" | awk '
BEGIN {
  # Classes écrites en intervalles explicites, pas en `[[:space:]]`/`[[:alnum:]]` :
  # CI tourne sur ubuntu, où `awk` est mawk et non gawk. `\t` et `0-9A-Za-z`
  # sont compris par toutes les implémentations, les classes POSIX pas partout.
  s    = "[ \t]"
  # `w` ≈ \b : le runner ne doit pas être le suffixe d’un autre mot. `.`, `/` et
  # `-` sont des FRONTIÈRES gauches (T-00000240) : `/usr/bin/npx`, `my-npx`,
  # `./node_modules/.bin/npx` sont donc reconnus, exactement comme les hôtes
  # python le faisaient déjà via `\b` — cet édit SUPPRIME une divergence.
  w    = "(^|[^0-9A-Za-z_])"
  opts = "(-[^ \t]+" s "+)*"
  # `q` : préfixe de CHEMIN optionnel devant la CLI `skills` globale (position de
  # commande). Ne franchit ni espace ni séparateur shell, se termine par `/` ou
  # `\`. QUATRE antislashs -> valeur `[/\\]`, classe {/,\} valide sous gawk ET
  # mawk (prouvé étape 2 : rc 0, stderr vide) ; deux auraient donné `[/\]`, classe
  # non terminée, non compilable, fail-open MUET.
  q    = "([^ \t;&|(`{]*[/\\\\])?"
  # `a` (T-00000256) : préfixe d’AFFECTATION et jetons `@@` admis ENTRE l’ancre
  # de position de commande et la CLI globale. `NOM=valeur` (valeur bornée aux
  # non-espaces/non-séparateurs, vide si citée — le `@@` voisin la porte) puis
  # `@@` neutralisant une citation, chacun suivi d’un espace, répétés. Intervalles
  # explicites, jamais de classe POSIX (mawk). Une affectation ne FERME pas la
  # position de commande : `FOO=1 skills add x` reste une installation.
  a    = "(([A-Za-z_][A-Za-z0-9_]*=[^ \t;&|(`{]*|@@)" s "+)*"
  n = 0
  pat[++n] = w "npx(\\.cmd)?" s "+" opts "skills" s "+add" s "+";                 two[n] = 0
  pat[++n] = w "npm(\\.cmd)?" s "+exec" s "+" opts "skills" s "+add" s "+";       two[n] = 0
  pat[++n] = w "(pnpm|yarn)(\\.cmd)?" s "+dlx" s "+" opts "skills" s "+add" s "+"; two[n] = 0
  pat[++n] = w "bunx(\\.cmd)?" s "+" opts "skills" s "+add" s "+";                two[n] = 0
  pat[++n] = w "codex(\\.exe|\\.cmd)?" s "+skills?" s "+(install|add)" s "+";     two[n] = 0
  # `gh skill install <owner/repo> [<skill>]` : ref sur DEUX jetons, comme les
  # homologues .codex/hooks/audit_gate.py et .gemini/hooks/audit_gate.py.
  pat[++n] = w "gh(\\.exe|\\.cmd)?" s "+skill" s "+install" s "+";                two[n] = 1
  # CLI `skills` installée globalement : pas de runner devant, donc la seule
  # ancre disponible est la POSITION DE COMMANDE (début de ligne ou après un
  # séparateur shell). Sans elle, « … discuss skills add … » suffirait.
  # Un chemin CITÉ est réduit à ` @@ ` à l’étage 1 : `@@ add x` (CLI absorbée) et
  # `@@ skills add x` (préfixe seul cité) sont donc aussi des installations (P8).
  pat[++n] = "(^|[;&|(`{])" s "*" a "(" q "skills(\\.cmd)?|@@)" s "+add" s "+";             two[n] = 0
}
{
  sub(/\r$/, "")
  low = tolower($0)
  for (i = 1; i <= n; i++) {
    if (match(low, pat[i])) {
      k = split(substr($0, RSTART + RLENGTH), t, /[ \t]+/)
      ref = (k >= 1 ? t[1] : "")
      if (two[i] && k >= 2 && t[2] !~ /^-/) ref = ref " " t[2]
      # Un ref s’arrête au premier métacaractère shell : `add owner/pkg && x`.
      sub(/[;&|)`].*$/, "", ref)
      if (ref != "") { print ref; exit }
    }
  }
}
') || degraded "the install-form scan failed"
# POSTURE DÉGRADÉE (T-00000240), strict décalque du scrub l.646. Si awk ne
# COMPILE pas le motif (classe non terminée sous une sémantique), le garde N'A
# PAS VU la commande : il le DIT et sort 0. Un seul des deux symptômes du scrub
# est observable ici : à cet étage une sortie VIDE est le cas NORMAL (aucune
# installation vue), donc seul le STATUT DE SORTIE reste — raison de plus pour
# que l'étape 2 prouve la compilation AVANT l'écriture.
[ -n "$REF" ] || exit 0

# --- Le journal d’audit -----------------------------------------------------
# Comparaison par CHAMPS, pas par sous-chaîne : `grep -F "$REF audit=pass"`
# acceptait `notowner/pkg audit=pass` pour un install de `owner/pkg` (extension
# de préfixe) et se laissait valider par une ligne de commentaire `#`. Ici les
# jetons du ref doivent être les PREMIERS champs de la ligne, `audit=pass` doit
# être un champ ENTIER situé après — donc `audit=fail-as-shipped` ne vaut pas un
# pass, et les lignes `#` de l’en-tête documenté sont ignorées.
LOG="$DIR/.agents/state/gates/AUDIT_LOG"
audited=1
if [ -f "$LOG" ]; then
  awk -v ref="$REF" '
    BEGIN { want = split(ref, expect, /[ \t]+/) }
    # `\r` retiré AVANT tout découpage : un AUDIT_LOG en CRLF (édité sous
    # Windows) collerait sinon un `\r` au dernier champ, et une ligne
    # `<ref> audit=pass` valide serait lue comme `audit=pass\r` — refus à tort.
    { sub(/\r$/, "") }
    /^[ \t]*#/ { next }
    NF < want  { next }
    {
      for (i = 1; i <= want; i++) if ($i != expect[i]) next
      for (i = want + 1; i <= NF; i++) if ($i == "audit=pass") { ok = 1; exit }
    }
    END { exit(ok ? 0 : 1) }
  ' "$LOG" && audited=0
fi

if [ "$audited" -ne 0 ]; then
  echo "BLOCKED by audit gate: no 'audit=pass' entry for '$REF' in .agents/state/gates/AUDIT_LOG. Run the security audit (skills-resolver step 3) and log it with the kit appender, never a shell redirect (refused where AUDIT_LOG is git-tracked) nor an Edit/Write rewrite (it drops the lock): python3 .agents/bin/skills_github_fallback.py audit-log <owner>/<repo>#<skill>@<sha> --pass — it covers a ref of the form <owner>/<repo>#<skill>; any other ref has no documented writer: report it to the pilot. Then retry." >&2
  # `path` ne porte que le REF (identifiant court et borné), jamais la ligne de
  # commande : elle peut contenir un secret (L-00000043).
  bash "$DIR/.claude/hooks/emit-event.sh" hook.deny guard=audit-gate rule=skills-add-unaudited "path=$REF" >/dev/null 2>&1 || true
  exit 2
fi
exit 0
