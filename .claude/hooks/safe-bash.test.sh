#!/usr/bin/env bash
# Tests for safe-bash.sh (T-00000030, étendu par T-00000146 / T-00000140, puis
# par la fusion T-00000088 qui rapatrie les gardes `rg`-absent et
# restauration-git-non-scopée d'un projet consommateur).
# Style matches log-agent-usage.test.sh / run-recap.test.sh: plain bash,
# PASS/FAIL lines, non-zero exit on any failure. Each case feeds the hook
# the real PreToolUse JSON shape on stdin and asserts the exit code
# (0 = allowed, 2 = blocked) — the guard's whole contract — plus, where it
# matters, what the guard SAID.
#
# La charge utile est sérialisée par json.dumps, jamais par un printf de format :
# sinon un payload contenant des guillemets fabriquerait un JSON invalide et le
# test mesurerait le sérialiseur, pas le garde.
#
# NON-VACUITÉ : la suite est SCINDÉE en quatre fichiers contigus (T-01M4WTYT8M :
# la jambe bash de la porte les répartit entre ses jobs). Jouer la suite contre
# un autre exemplaire du garde, c'est jouer les QUATRE :
#   for s in .claude/hooks/safe-bash*.test.sh; do SAFE_BASH_HOOK=<mutant> bash "$s"; done
# QUEL MORCEAU PORTE QUELS ARMS — coupes aux bannières `# ====`, ordre d'origine :
#   safe-bash.test.sh        cette carte, (split0), puis les 29 cas d'origine et
#                            (g)(h)(i)(j)(k)(m)(l1)-(l22)(n)(o)(p)(q)(r)(s)
#   safe-bash-t-y.test.sh    (t) garde 4, (h2bis)(h2ter), (l23)-(l55), (w)(x)(y)
#   safe-bash-ew-eo.test.sh  (ew)(ef)(en)(gp)(fp)(kr)(ct)(eo)
#   safe-bash-em-z.test.sh   (em)(bd)(bc), puis la section (z)
# La carte ci-dessous nomme des arms des QUATRE fichiers ; elle ne vit qu'ICI. Le
# prologue (purge FORME A, helpers) est recopié octet pour octet en tête de chaque
# morceau, entre ses deux marqueurs `>>>` / `<<<` safe-bash-prologue ; (split0)
# rougit dès qu'une copie diverge. C'est ainsi que la mutation
# est prouvée — le mutant qui supprime l'étage 1 (neutralisation des segments
# cités) fait rougir (g12)-(g14) et NON (g1) : mesuré (T-00000278), l'étage 1
# supprimé laisse passer (g1)-(g11) (cf. (g12)-(g14)) ; (g1) tombe, lui, contre le
# mutant « garde en sous-chaîne » (cf. (g1)/(g15)). Celui qui supprime la fenêtre
# d'enveloppe fait rougir (h1), celui qui rend la dégradation muette fait rougir
# (j2). Pour les deux
# gardes RAPATRIÉES, mutants et arms sont appariés explicitement — chaque arm est
# tué par au moins un mutant, sinon il ne mesure rien :
#   garde `rg` neutralisée         -> (k1)(k2)(k3)(k11)(k12)(k15)(k16)
#   garde `rg` qui mord même quand l'outil résout -> (g4)(k4)(k5)
#   garde git-non-scopée neutralisée -> (l1)-(l7)(l16)(l17)(l18)(l19)
#   garde rm/mv neutralisée, ou étage 1 qui blanchit AU-DELÀ de ses guillemets
#                                   -> (g15), le JUMEAU NÉGATIF de (g1) : la même
#                                      écriture de ledger, description NON citée,
#                                      que bash exécute vraiment
#   étage 1 (segments cités) supprimé -> (g12)(g13)(g14)(k13)(k14)(l12)
#   garde git ramenée en SOUS-CHAÎNE (sa forme d'origine chez le consommateur)
#                                   -> (l12)(l13)(l14)(l16)(l18)(l22), dont
#                                      (l13)(l14) que SEUL ce mutant-là tue
#   étage 1 ramené au sed AVEUGLE À L'ÉCHAPPEMENT (T-00000181, la forme d'avant
#   le port de `quoted_spans()`) -> (n1)(n2), que SEUL ce mutant-là tue ; le
#   scanner qui ignorerait tous les backslashes tombe sur (n3), celui qui
#   REVIENDRAIT au balayage ligne par ligne (l'état d'avant T-00000208) sur (n7)
#   étage 1 SANS frontière de commentaire — l'état d'avant le correctif du
#   CRITICAL de la revue de classe 1, où une apostrophe de commentaire s'appariait
#   avec un guillemet de CODE situé plus loin et blanchissait la ligne exécutée
#   -> (n8)(n9), une par garde touchée ; le correctif NAÏF qui coupe à tout `#`
#   (donc à `$#` et `${#v}`, en élargissant `SEP`) tombe sur (n10), que SEUL ce
#   mutant-là tue ; et (n11) fixe la polarité choisie — la coupe n'efface pas,
#   elle expose, donc un commentaire reste ANALYSÉ et son refus est un faux
#   positif assumé, jamais un effacement
#   étage 0.5 ramené à l'awk AVEUGLE de T-00000187 (gsub naïf + `match()`
#   flottant en sous-chaîne) -> (o1)(o4)(o5)(o7)(o8)(o8b)(o9), les sept tracées
#   ROUGES contre lui avant le correctif ; les mutants plus fins de cet étage
#   sont appariés arm par arm en tête de la section (o), dont (o6) que SEUL le
#   mutant « `\r` retiré des seules lignes de corps » tue, et (o2)(o3) qui
#   interdisent de fermer le fail-open en blanchissant plus largement
#   étage 0.5 qui ouvre un corps sur une ligne PHYSIQUE non terminée dans un état
#   neutre, alors que bash l'ouvre après la ligne LOGIQUE -> (p1)(p2)(p3)(p4),
#   une par forme de prolongement ; et étage 0.5 dont la RE capture un PRÉFIXE du
#   mot délimiteur au lieu d'exiger une frontière de mot -> (p5). Les cinq
#   viennent de la revue de sécurité de T-00000187, toutes mesurées deux fois
#   (bash exécute vraiment la ligne / la garde sortait 0 en silence)
#   étage 0.5 dont la détection de prolongement est une ÉNUMÉRATION de
#   constructions au lieu d'un PRÉDICAT CLOS sur l'équilibre `()` `[]` `{}`
#   -> (q1)(q2)(q3)(q4), une par forme qui échappait à la liste. C'est le même
#   mutant que (p1)-(p4) une couche plus bas, et c'est pour cela qu'il a fallu
#   deux tours : le premier correctif avait la bonne intention et la mauvaise
#   FORME
#   étage 0.5 dont le mot délimiteur est lu par une RE À UNE SEULE PIÈCE CITÉE
#   au lieu du PARSEUR DE PIÈCES de bash (concaténation `'X'` | `"X"` | `\c` |
#   nue, puis retrait des quotes) -> (r1)(r2)(r3), les trois mesurées ROUGES
#   contre l'état d'avant T-00000210 ; le corps qui ne se refermerait jamais sur
#   la forme échappée tombe sur (r4), le jeu de caractères non vérifié sur (r5),
#   la frontière de mot TAIL retirée sur (r6), et le délimiteur réduit à sa
#   PREMIÈRE pièce sur (p5). La polarité de l'étage est tenue à part, par (m3) :
#   un corps à délimiteur NU reste ANALYSÉ, le blanchir serait fail-open
#   message de la Garde 1b (:1115) remplacé par celui de la Garde 1a — mutant à
#   COMPORTEMENT IDENTIQUE (toujours rc 2), donc invisible pour un arm qui ne lit
#   que le code de sortie -> (g15), et c'est pourquoi cet arm asserte son MOTIF
#   (T-00000227) : le garde porte PLUSIEURS motifs distincts — rm-rf-root,
#   git-wipe-unscoped, git-output-write, git-grep-pager-exec,
#   git-subcommand-hidden, rg-absent-silent-failure, redirect-write-guarded,
#   rm-mv-bypass-checkpoint, depuis T-00000784 redirect-stage-broken et, depuis
#   T-00001090, git-branch-force-delete ; liste
#   relevée par grep des `deny <règle>` et du `rule=` de l'étage redirection,
#   jamais close par un chiffre (L-00000187) —, un rc 2 n'en nomme aucun.
#   DOMMAGE COLLATÉRAL MESURÉ, dit ici parce
#   qu'un mutant qui tue plusieurs arms s'écrit pour CHACUN : la substitution
#   retire aussi le mot `checkpoint` du message de la Garde 1b, donc les 27 arms
#   qui assertent ce motif — (n1)(n2)(n7)(n8), la famille (o), (p), (q), (r4)-(r6)
#   et (s1)(s2)(s4) — rougissent AVEC lui. C'est cohérent, pas une surprise : ils
#   épinglent tous le même message. Relevé : 165 passed, 28 failed sous M1
#   même substitution portée aux hôtes python (safe_bash.py:917) -> l'arm codex et
#   l'arm gemini du jumeau fondateur, qui assertent la même formulation longue
#   RE d'extraction de BLOCKED_PATTERNS (:709) rendue agnostique au guillemet —
#   le correctif du HIGH annulé par le HAUT : l'extraction REDEVIENT complète,
#   COMPLETE redevient vrai, aucune branche stricte -> (t18), et (t16) AUSSI
#   `and BLOCKED_OK` retiré de COMPLETE (:740) — l'ÉTAT PRÉ-CORRECTIF EXACT du
#   HIGH de la revue de classe 1 -> (t16)(t17) ET (t19) ; (t18) reste VERT, car
#   PREF est vide mais les GLOBS survivent (regex INDÉPENDANTE, :725), donc
#   .mcp.json reste REFUSÉ pendant que src/legacy/ passe. Un mutant qui tue
#   plusieurs arms est écrit pour CHACUN : le taire ici rendrait l'appariement
#   faux. La valeur de (t18)(t19) n'est pas une exclusivité de mutant, c'est la
#   FIDÉLITÉ À LA CIBLE du PoC — src/legacy/, NON git-suivie, donc seule la
#   clause protégée peut la refuser
#   étage redirection PLANTÉ ramené à degraded() — l'état de 347889ea, avant
#   T-00000784 : exit 0 annoncé au lieu du refus -> la section (z), sauf ses
#   contrôles (z8)(z8b)(z8b2)(z10)(z11)(z20-ctl)(z20)(z20b), verts avant comme
#   après
#   sentinelle NON validée, sortie lue SANS grammaire, captures `X=$(…); X_RC=$?`
#   sans remise à zéro de l'état de shell hérité — l'état de e69aa011, la passe
#   1 de T-00000784 -> (z12)-(z19), (z18b), (z21), (z22)
#   lecteur de la passe rm/mv au DERNIER état lu (l'état de 10ed6894) -> (z23)
#   (z23b) ; lecteur rm/mv SANS retrait du retour chariot -> (z24)(z24b)
#   `REDIR` non initialisé avant son `case` (l'état de a342b9bd) -> (z25)(z25b)
#   normalize() qui n'attrape que OSError (l'état de 33761009), sous CPython
#   <= 3.12 -> (z26-3.11)(z26-3.12)
#   T-00001102 + T-00001090, sections (ew)…(bd) — mutants joués sur CLONE par
#   mutants.py de l'annexe du plan T-00001090 (jamais sur ce hook) ; les hôtes
#   python sont tenus par la parité, ici seulement les arms Claude :
#   M1 exemption awk de la sous-commande git rm|mv retirée -> (ew2)(ew6)(ew9)
#   M2 exemption de la passe embarquée retirée -> (ew10)
#   M3 exemption des jumeaux retirée -> parité (gitenv/lifted-*)
#   M4 ×29 option À VALEUR d une table déclarée SANS valeur -> l arm (eo<n>)
#   de cette option (env 7, sudo 20, doas 2)
#   M5 option inconnue lue sans valeur -> (en4)(ef20)
#   M6p valeur à expansion non marquée ambiguë -> (en5)
#   M6s expansion consommée sans juger le mot suivant -> (ef7)(ef8)(ef10)(ef20)
#   M7 fermeture pour toute commande, sans base git -> (en8)
#   M9a enveloppe de table imbriquée lue ambiguë -> (ew11)(ew12) ; M9b ignorée
#   -> (ef13)
#   M11a substitution refermée, ambiguïté perdue -> (ef14) ; M11b commande =
#   expansion, ambiguïté perdue -> (ef15)
#   M12 exemption élargie à tout rm|mv de la fenêtre -> (en21)(en22)(en23)
#   M13 options globales de git non sautées -> (ew19)(ew20)
#   M14 enveloppe hors tables, chaîne encore prouvée -> (en27)
#   M15 lecture anticipée `if (wrap[b])` devenue `if (b in wrap)` -> (em44)
#   (em45)(em47)
#   B10 grappe D non lue -> (bd1)(bd12) ; B11 lettre f non lue -> (bd2)-(bd4)
#   (bd7) ; B12 force à 5 lettres -> (bd6) ; B13 casse -> (bd10) ; B14 arrêt au
#   premier opérande -> (bd8)(bd13) ; B15 expansion non refusée -> (bd14)(bd15) ;
#   B16 `--` clôt les mots -> (bd9) ; B17 5e valeur des jumeaux ignorée ->
#   parité (branch/*) ; B18 message sans « git branch -D » -> toutes les (bd) ;
#   B19a antislash non normalisé -> (bd18) ; B19b segment cité collé accepté ->
#   (bd19)(bd20) ; B21 substitution non citée en opérande acceptée -> (bd28)
#   (bd29)(bd30), contrôle (bc16)
#   B20 (jumeaux, `.replace` de l antislash retiré) est ÉQUIVALENT : shlex lit
#   déjà l antislash ; le code est CONSERVÉ (réserve (4) de S-00003937)
#   T-01M5D6XS2SJ6021Y97X3Z7BX8V, section (sb) de safe-bash-t-y.test.sh (et
#   bc20-bc22, bc37, bd38 d em-z, gp3 d ew-eo, (m7) et (s5b) ici) — mutants
#   joués sur une COPIE hors dépôt (SAFE_BASH_HOOK), un à la fois :
#   M1abc une copie de scrub_spans sans citation ANSI-C -> (s5), et (sb1a) si
#   c est celle de l étage 1 ; M1d aucun décodage ANSI-C -> (sb1e)(sb5g)(sb5g2)
#   (bc37) ; M1e décodage sans \xHH ni \NNN -> (sb1e)(sb5g2), et (s5b) dès qu une
#   seule copie d ansi_decode diverge
#   M2a $(…)/backtick dans "…" restent du texte -> (sb2a)(sb2d)(sb2d2) ; M2b
#   corps nu lu comme du code -> (sb2b) ; M2c `$X` sans fenêtre ambiguë ->
#   (sb2c) ; M2d corps cité dans $(…) analysé -> (sb2n3)(sb2n4) ; M2e antislash
#   ignoré dans "…" -> (sb2n5)(sb2n6b) ((sb2n6) y survit : son antislash final
#   masque l option) ; M2f clôture à la ligne exacte -> (sb2j)(sb2k) ; M2h
#   clôture sans retrait des blancs de tête (C17) -> (sb2k) — (sb2e)(sb2f)(sb2h)
#   survivent à M2f/M2h par construction : leur `#)"` laisse la substitution
#   ouverte, la lecture s arrête et tout est analysé ; M2g corps NU traité comme
#   cité -> (sb2g) ; M2n les morceaux de "…" autour d une substitution non
#   neutralisés -> (sb2n14) ; M2stop pas d arrêt sur une construction imbriquée
#   non fermée -> (sb2l) (relecture spéculative exponentielle, délai dépassé)
#   M3 étage 1.5 contourné -> (sb3a)-(sb3g)(sb3j)(sb4c) ; M3s séquences non
#   développées -> (sb3e)(sb3f) ; M3b refus sur le seul nom git/rm/find/xargs
#   (C15) -> (sb3g) ; M3n2 refus dès la borne -> (sb3n5) ; M3n3 développement
#   sur le texte brut (avant l étage 1) -> (sb3n10) ; M3n refus de tout
#   développement -> (sb3n6)
#   M4a affectation d alias en tête non lue -> (sb4a)(sb4a4)(sb4a5) ; M4a2
#   `-c`/`--config-env` d alias non lus -> (sb4a2)(sb4a3) ; M4b expansion d
#   option de reset non comptée -> (sb4b)(sb5f) ; M4c `xargs` en tête non lu ->
#   (sb4d)(sb4d2)(sb4d3)(gp3) ; M4c2 fenêtre de `xargs` lue au seul mot de
#   commande -> (gp3) ; M4c3 opérandes du tube non larges -> (sb4d)(sb4d2)
#   (sb4d3) ; sur-blocage : M4o toute clé GIT_CONFIG_KEY lue comme alias ->
#   (sb4n) ; M4o2 mot cité ou après `--` compté --hard -> (sb4n8)
#   M5a primaire de find non relue dans l awk -> (sb5b)(sb5c)(sb5c2)(sb5c3) ;
#   M5a2 non relue dans la passe rm/mv -> (sb5a)(sb5b) ; M5b `#` du stash non lu
#   -> (sb5d) ; sur-blocage : M5o tout mot `-…` rouvre la commande -> (sb5n6)
#   M6a --no-dry-run ignoré -> (sb6a) ; M6b `-e` en fin de grappe sans valeur ->
#   (sb6b) ; M6c expansion/glob/antislash sans effet -> (sb6c)(sb6d)(sb6e) ;
#   sur-blocage : M6n aucun crédit de dry run -> (y55)-(y57)(sb6n)
#   PASSE DE CORRECTION, section (sc) : MF1x les trois couches de F1 retirées
#   (borne de 256 accolades, `except Exception` du mot, rattrapage de la ligne)
#   -> (sc1a)(sc1b)(sc1c) — chaque couche seule suffit (MF1, MF1b, MF1c
#   survivent : redondance voulue) ; MF2 vérification des demi-codets ET
#   sortie tolérante retirées -> (sc2a)(sc2b)(sc2c) — chacune seule suffit
#   (MF2a, MF2b survivent) ; MF3a `${…}` non opaque -> (sc3e) ; MF3b `$((…))`
#   non opaque -> (sc3d) ; MF3c (délimiteur à accolade) et MF3d (arithmétique
#   dans "…") survivent : l opacité les couvre déjà ; MF4 -> (sc4a)-(sc4f) ;
#   MF5 enveloppes non sautées -> (sc5a)-(sc5g) ; MF6 ligne `)` non lue ->
#   (sc6a)(sc6b) ; MF7 table recalculée à chaque accolade (quadratique) ->
#   (sc7a) ; MF8 phrase du `case` retirée -> (sc8a)
#   2e PASSE, section (sd) : MN1 opaque() sans arrêt sur $', $( et backtick
#   -> (sd1a) ; MN1b sans arrêt dans un "…" sauté -> (sd1b)(sd1c) ; MN2 ligne
#   `)` reprise en code -> (sd2a)(sd2b) ; MN3a mots réservés non sautés ->
#   (sd3b)(sd3c) ; MN3b durée de timeout non sautée -> (sd3a) ; MN3c ancienne
#   liste d enveloppes -> (sd3a)(sd3d) ; MN3d `-S` sans valeur -> (sd3e) ; MN3e
#   chrt/taskset/builtin hors de la table de l étage 2 -> (sd4a)-(sd4c)
#   3e PASSE : MP1 délimiteur à caractère non sûr lu -> (sd5a)(sd5b) ; MP1b
#   pièce citée non sûre lue -> (sd5c)(sd5e) ; MP2 mot de commande non recollé
#   -> (sd6a)(sd6d)(sd6e) ; MP2b option de reset non recollée -> (sd6b)(sd6c) ;
#   MP2c segments littéraux non distingués -> (sd6c)(sd6d)(sd6e)
# >>> safe-bash-prologue
# PROLOGUE COMMUN des quatre suites .claude/hooks/safe-bash*.test.sh
# (T-01M4WTYT8M) : le MÊME, octet pour octet, dans chacune ; (split0) de
# safe-bash.test.sh compare les quatre copies. Le modifier ici, c'est le
# modifier dans les QUATRE fichiers.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${SAFE_BASH_HOOK:-$HERE/safe-bash.sh}"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "SKIP: ${0##*/} needs python to build the payloads"; exit 0; fi
# REAL_PY : l'interpréteur RÉSOLU, que les cales des sections (n)(s)(x)(z)
# exécutent derrière leur filtre. Au prologue (T-01M4WTYT8M) : trois des quatre
# morceaux l'emploient, et aucun ne lit l'état qu'un autre a construit.
REAL_PY="$(command -v "$PY")"
# Events from the guard's own emit calls must never land in the real store.
EVTMP="$(mktemp -d)"
export AGENTS_EVENTS_DIR="$EVTMP"
OUTF="$EVTMP/stdout"; ERRF="$EVTMP/stderr"

PASS=0; FAIL=0

# json_payload <command> — la forme PreToolUse réelle.
# WINDOWS (fait mesuré, et la raison pour laquelle ces deux variables sont là) :
# sous Git Bash / MSYS, argv passé à un binaire natif (python.exe) subit une
# TRADUCTION DE CHEMIN — `/bin/rm secrets.txt` arrivait à python comme
# `C:/Program Files/Git/usr/bin/rm secrets.txt`. La suite mesurait alors une
# charge utile réécrite par le shell, pas celle qu'elle décrit : l'arm (h9)
# passait en vert sans que le garde ait jamais vu un `/bin/rm`. Les deux
# variables neutralisent la conversion ; sur Linux (CI) elles sont inertes.
json_payload() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    "$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$1"
}

check() { # check <expected_exit> <label> <command-string>
  expected="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_deny_msg() { # check_deny_msg <motif> <label> <command-string>
  # REFUSÉ, ET POUR LA BONNE RAISON. Le code de sortie seul ne suffit pas
  # (L-00000161) : ce garde porte PLUSIEURS motifs distincts — rm-rf-root,
  # git-wipe-unscoped, git-output-write, git-grep-pager-exec,
  # git-subcommand-hidden, rg-absent-silent-failure, redirect-write-guarded,
  # rm-mv-bypass-checkpoint, depuis T-00000784 redirect-stage-broken et, depuis
  # T-00001090, git-branch-force-delete — donc
  # un arm satisfait par le mauvais d'entre eux serait un faux vert ; c'est
  # exactement ce que la matrice de parité assert de son côté avec ses `motive`.
  # Le compte a été porté de TROIS à CINQ (T-00000227), puis le CHIFFRE a été
  # RETIRÉ (T-00000784, L-00000187) : il était de nouveau périmé — huit règles
  # `deny` quand il en disait cinq — DANS le helper même dont la thèse est « un
  # code de sortie n'est pas un motif ». La liste se relève par grep des
  # `deny <règle>` et du `rule=` de l'étage redirection de safe-bash.sh ; elle
  # n'est close par aucun chiffre.
  motive="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  msg="$(cat "$ERRF")"
  case "$msg" in
    *"$motive"*) if [ "$got" -eq 2 ]; then PASS=$((PASS+1)); echo "PASS: $label"; return; fi;;
  esac
  FAIL=$((FAIL+1))
  echo "FAIL: $label (expected exit 2 carrying <$motive>, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
}

check_silent() { # check_silent <label> <command-string> — laissé passer ET sans
  # un mot sur aucune des deux sorties. C'est l'assertion qui attrape le défaut
  # de T-00000146 : le garde ne doit pas seulement laisser passer une commande
  # qui MENTIONNE une suppression, il ne doit pas non plus la commenter.
  label="$1"; cmd="$2"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

# check_path <PATH> <expected_exit> <label> <command-string>
# Même contrat que `check`, mais joue le hook sous un PATH imposé — la garde
# `rg` se comporte différemment selon que l'outil résout ou non, et un test qui
# hériterait du PATH du poste basculerait de vert à rouge le jour d'une
# installation de ripgrep. Les deux branches sont donc FORCÉES, pas observées.
# La charge utile est sérialisée AVANT la substitution de PATH : c'est le garde
# qu'on déplace, pas le harnais.
check_path() {
  forced_path="$1"; expected="$2"; label="$3"; cmd="$4"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_silent_path() { # check_silent_path <PATH> <label> <command-string>
  forced_path="$1"; label="$2"; cmd="$3"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

assert() { # assert <rc 0=ok> <label>
  if [ "$1" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $2"; else FAIL=$((FAIL+1)); echo "FAIL: $2"; fi
}
# <<< safe-bash-prologue

# (split0) T-01M4WTYT8M — LE PROLOGUE EST LE MÊME DANS LES QUATRE MORCEAUX. Il est
# recopié, faute de fichier d'aide : un `.sh` non-`*.test.sh` sous .claude/hooks/
# serait classé NOYAU, c'est-à-dire un hook livré. Une copie qui dériverait ferait
# mesurer un morceau avec d'autres helpers que les trois autres. Les OCTETS entre
# les deux marqueurs, marqueurs compris, sont comparés ; chaque extrait doit être
# NON VIDE, sinon un marqueur perdu dans deux fichiers donnerait deux extraits
# vides, donc égaux, donc un faux vert.
split0_ref="$EVTMP/split0.safe-bash.test.sh"
awk '/^# >>> safe-bash-prologue$/{f=1} f{print} /^# <<< safe-bash-prologue$/{exit}' "$HERE/safe-bash.test.sh" > "$split0_ref"
split0_bad=""
if [ ! -s "$split0_ref" ]; then split0_bad=" safe-bash.test.sh(vide)"; fi
for split0_s in safe-bash-t-y.test.sh safe-bash-ew-eo.test.sh safe-bash-em-z.test.sh; do
  split0_f="$EVTMP/split0.$split0_s"
  if [ -f "$HERE/$split0_s" ]; then
    awk '/^# >>> safe-bash-prologue$/{f=1} f{print} /^# <<< safe-bash-prologue$/{exit}' "$HERE/$split0_s" > "$split0_f"
  else
    : > "$split0_f"
  fi
  if [ ! -s "$split0_f" ]; then
    split0_bad="$split0_bad $split0_s(vide)"
  elif ! cmp -s "$split0_ref" "$split0_f"; then
    split0_bad="$split0_bad $split0_s(diverge)"
  fi
done
if [ -z "$split0_bad" ]; then r=0; else r=1; echo "split0: prologue absent or divergent in:$split0_bad"; fi
assert "$r" "(split0) prologue byte-identical in the 4 safe-bash suites"

# PATH sans aucun `rg` : on RETIRE les répertoires qui en portent un, au lieu de
# vider le PATH — le hook a besoin de python, sed, awk et printf pour
# s'exécuter, et un PATH vide testerait un plantage, pas la garde.
PATH_NO_RG=""
old_ifs="$IFS"; IFS=:
for d in $PATH; do
  [ -n "$d" ] || continue
  if [ -x "$d/rg" ] || [ -x "$d/rg.exe" ]; then continue; fi
  PATH_NO_RG="${PATH_NO_RG:+$PATH_NO_RG:}$d"
done
IFS="$old_ifs"

# PATH avec un `rg` factice : la garde ne doit regarder QUE la résolution, pas
# le comportement de l'outil.
RG_STUB_DIR="$EVTMP/rgstub"; mkdir -p "$RG_STUB_DIR"
printf '#!/bin/sh\nexit 1\n' > "$RG_STUB_DIR/rg"
chmod +x "$RG_STUB_DIR/rg"
PATH_WITH_RG="$RG_STUB_DIR:$PATH_NO_RG"

# Le PATH amputé doit rester un PATH VIABLE pour le garde : si le seul python de
# ce poste vit à côté d'un `rg`, l'amputation ferait tomber le garde sur son
# chemin DÉGRADÉ (exit 0, muet sur les gardes) et la section (k) mesurerait ce
# chemin-là au lieu de la garde. Bound explicitement annoncé plutôt que subi.
RG_SECTION_OK=1
if ! PATH="$PATH_NO_RG" sh -c 'for c in python3 python py; do "$c" --version >/dev/null 2>&1 && exit 0; done; exit 1'; then
  RG_SECTION_OK=0
  echo "SKIP-BOUND: (k) rg-absent arms skipped — removing every rg-bearing PATH dir also removed python, so the guard would take its COVERAGE DEGRADED path and the section would measure nothing."
fi

# =============================================================================
# LES 29 CAS D'ORIGINE (T-00000030) — aucun retiré, aucun affaibli. Ils pinnent
# le contrat que la réécriture de T-00000146 ne devait pas entamer, et que la
# fusion T-00000088 ne devait pas entamer non plus.
# =============================================================================

# --- benign commands stay allowed -------------------------------------------
check 0 "plain command"                    "ls -la"
check 0 "word containing rm is not rm"     "grep -n format file.txt"
check 0 "rm at end of a word (npm)"        "npm install"
check 0 "git rm is rewindable"             "git rm old.txt"
check 0 "git mv is rewindable"             "git mv a.txt b.txt"
check 0 "git rm with option"               "git rm --cached x.py"

# --- the classic shapes the guard always caught ------------------------------
check 2 "leading rm"                       "rm file.txt"
check 2 "rm after pipe"                    "true | rm file.txt"
check 2 "rm after semicolon"               "true ; rm file.txt"
check 2 "leading mv"                       "mv a.txt b.txt"
check 2 "mv mid-command"                   "cd src && mv a.txt b.txt"

# --- normalization holes (the reason T-00000030 existed) ---------------------
check 2 "rm after newline"                 "echo hi
rm file.txt"
check 2 "rm separated by tab"              "rm$(printf '\t')file.txt"
check 2 "rm inside subshell parens"        "(rm file.txt)"
check 2 "rm inside command substitution"   "echo \$(rm file.txt)"
check 2 "rm glued to &&"                   "true &&rm file.txt"
check 2 "mv glued to pipe (verb asymmetry)"    "true |mv a.txt b.txt"
check 2 "mv glued to semicolon (verb asymmetry)" "true ;mv a.txt b.txt"
check 2 "raw rm hiding behind a git rm"    "git rm tracked.txt && rm other.txt"

# --- catastrophic root rm ----------------------------------------------------
check 2 "rm -rf root"                      "rm -rf /"
check 2 "rm -fr root"                      "rm -fr /"
check 2 "rm -rf root with trailing space"  "rm -rf / "

# --- temp/build allowlist ----------------------------------------------------
check 0 "rm under /tmp"                    "rm -rf /tmp/scratch"
check 0 "rm in node_modules"               "rm -rf node_modules"
check 0 "rm in dist"                       "rm -rf dist/bundle.js"
# T-00000762 (réserve A-C4 de la paire it. 2) : ce bras ÉPINGLAIT LE DÉFAUT. Il
# passait sur la seule sous-chaîne `build/`, alors que la SOURCE `out.bin` —
# hors de toute liste, peut-être suivie — quittait sa place sans rewind. `mv`
# juge désormais source ET destination, comme les hôtes python qui le
# refusaient déjà (mesuré ALLOW|DENY|DENY) : parité, pas durcissement isolé.
check_deny_msg "checkpoint" "mv into build dir: the SOURCE out.bin is judged too" "mv out.bin build/out.bin"

# --- traversal never rides the allowlist (lot 3 security review, HIGH) -------
check 2 "rm -rf escaping /tmp via .."      "rm -rf /tmp/../etc"
check 2 "rm escaping node_modules via .."  "rm node_modules/../src/main.py"
check 2 "mv escaping build via .."         "mv build/../src/a.py /elsewhere"

# =============================================================================
# (g) T-00000146 — L'ARM DE REPRODUCTION. Une commande dont le TEXTE parle
#     d'une suppression n'est pas une suppression. Mesuré en session le
#     2026-08-06 : l'écriture de mémoire institutionnelle (g1) a été REFUSÉE.
#     `check_silent` : ni refus, ni warning — le garde n'a rien à dire ici.
# =============================================================================
check_silent "(g1) REPRO ledger add whose --text describes a recursive delete" \
  'python .agents/bin/ledger.py add --category lesson "safe-bash" --text "le garde refusait une ecriture parce que le texte parlait de rm -rf" --related T-00000146'
check_silent "(g2) tasks.py new whose title quotes a recursive delete" \
  'python .agents/bin/tasks.py new "safe-bash: rm -rf cite dans un titre ne doit pas bloquer" --stage dev'
check_silent "(g3) git commit -m mentioning the destructive verb" \
  'git commit -m "fix(hooks): rm -rf mentionne dans un message nest pas une suppression"'
# (g4) : l'arm tourne sous un PATH portant un `rg` factice — depuis la fusion
# T-00000088, `rg` EXÉCUTÉ est lui-même une garde, donc laisser cet arm hériter
# du PATH du poste le rendrait vert ou rouge selon qu'un ripgrep y est installé.
if [ "$RG_SECTION_OK" -eq 1 ]; then
  check_silent_path "$PATH_WITH_RG" "(g4) rg searching the tree for the destructive verb" \
    "rg -n 'rm -rf' .claude"
fi
check_silent "(g5) doc append mentioning the destructive verb" \
  "printf '%s\\n' 'never run rm -rf on tracked files' >> docs/tech/hooks.md"
check_silent "(g6) both quote kinds around the mention" \
  'python .agents/bin/specs.py add --task T-00000146 --kind delta "garde: '"'"'rm -rf'"'"' est une donnee ici" '
check_silent "(g7) unbalanced single quote (French apostrophe) plus a mention" \
  "echo l'index parle de rm -rf et c'est tout"
check_silent "(g8) unquoted mention mid-sentence is not a command" \
  'echo do not run rm -rf on tracked files'
check_silent "(g9) nested quotes inside a python -c payload" \
  "python -c \"print('rm -rf x')\""
check_silent "(g10) mv mentioned as a grep pattern" \
  'git log --grep mv --oneline'
check_silent "(g11) empty command"                                 ''
# (g12)-(g14) : les arms qui rendent l'ÉTAGE 1 non vacuous. Sans neutralisation
# des segments cités, un MÉTACARACTÈRE à l'intérieur du texte cité (`;`, `(`,
# `&&`) fabrique une fausse position de commande juste devant le verbe, et la
# mention redevient un refus. Mesuré : le mutant qui supprime l'étage 1 laisse
# passer (g1)-(g11) et ne tombe QUE sur ces trois-là.
check_silent "(g12) quoted mention preceded by a ';' inside the SAME quotes" \
  'git commit -m "wip; rm -rf stale artefacts"'
check_silent "(g13) quoted mention inside parentheses" \
  'python .agents/bin/ledger.py add --category lesson "le rewind casse (rm -rf) dans un hook"'
check_silent "(g14) quoted mention preceded by '&&' inside the SAME quotes" \
  'git commit -m "avant: echo x && rm y bloquait"'
# (g15) LE CONTRÔLE NÉGATIF JUMEAU DE (g1) — sans lui, l'arm de reproduction ne
# mesure RIEN. C'est la MÊME écriture de mémoire institutionnelle, même verbe et
# même chemin, dont la description n'est PLUS citée : le `;` redevient un vrai
# séparateur et bash exécute pour de bon `rm -rf src/x`. (g1) doit passer, (g15)
# doit être REFUSÉ, et c'est l'ÉCART entre les deux qui prouve que le garde lit
# les guillemets plutôt que de tout blanchir — un étage 1 qui déborderait de ses
# guillemets rendrait (g1) vert pour la mauvaise raison, et seul cet arm-ci le
# dirait. Appariement MESURÉ (T-00000146, vérification-clôture, contre l'état du
# fichier APRÈS T-00000208) : (g1) tombe contre le mutant « garde en SOUS-CHAÎNE »
# — la forme d'origine du consommateur, qui plie tout en espaces, guillemets
# compris — et (g15) tombe contre tout mutant qui neutralise la garde rm/mv ou
# qui sur-blanchit l'étage 1.
# ASSERTION DE MOTIF, pas de code de sortie (T-00000227) : le garde porte
# PLUSIEURS refus distincts — leur liste est celle de `check_deny_msg`, jamais un
# chiffre (L-00000187 ; celui qui était écrit ici, CINQ, était périmé) — et un
# rc 2 n'en nomme aucun, donc cet arm resterait VERT sous
# un mutant qui échange le message de la Garde 1b contre celui de la Garde 1a —
# comportement identique, verdict identique, motif faux. `check_deny_msg` exige
# DÉJÀ rc==2 : l'assertion de code de sortie n'est pas perdue, elle est
# RENFORCÉE. La charge utile est inchangée, octet pour octet.
check_deny_msg "rm/mv via Bash bypasses" "(g15) TWIN CONTROL: the SAME ledger write with its description UNQUOTED" \
  'python .agents/bin/ledger.py add --category lesson safe-bash --text le garde refusait une ecriture ; rm -rf src/x --related T-00000146'

# =============================================================================
# (h) UNE VRAIE SUPPRESSION / UN VRAI DÉPLACEMENT RESTE BLOQUÉ — raison d'être
#     du garde : son faux négatif coûte un rewind de checkpoint. Formes que la
#     reconnaissance par POSITION DE COMMANDE doit couvrir, y compris celles que
#     l'ancienne sous-chaîne attrapait par accident.
# =============================================================================
check 2 "(h1) sudo rm"                             'sudo rm -rf /etc/nginx'
check 2 "(h2) rm behind xargs"                     'ls | xargs rm -f'
check 2 "(h3) rm behind find -exec"                'find . -name "*.bak" -exec rm {} \;'
check 2 "(h4) rm behind timeout and its duration"  'timeout 5 rm tracked.txt'
check 2 "(h5) rm behind sudo -u <user>"            'sudo -u root rm -rf /var/data'
check 2 "(h6) mv behind nice -n <n>"               'nice -n 10 mv a.py b.py'
check 2 "(h7) rm behind env"                       'env rm tracked.txt'
check 2 "(h8) rm behind eval, unquoted"            'eval rm tracked.txt'
check 2 "(h9) absolute path to the verb"           '/bin/rm secrets.txt'
check 2 "(h10) absolute path to mv"                '/usr/bin/mv a.py b.py'
check 2 "(h11) Windows .exe shim"                  'rm.exe tracked.txt'
check 2 "(h12) backslash-escaped verb (alias bypass)" '\rm tracked.txt'
check 2 "(h13) uppercase verb (case-insensitive FS)" 'RM tracked.txt'
check 2 "(h14) env assignment before the verb"     'FOO=bar rm tracked.txt'
check 2 "(h15) rm after then, inside an if"        'if [ -f x.py ]; then rm x.py; fi'
check 2 "(h16) mv after do, inside a for loop"     'for f in *.log; do mv "$f" archive; done'
check 2 "(h17) rm after && with options first"     'cd /etc && rm -r --force conf.d'
check 2 "(h18) REAL rm in the same command as a quoted MENTION" \
  'git commit -m "docs: explain why rm -rf is banned" && rm scratch_tracked.txt'
check 2 "(h19) REAL rm on the line after a quoted MENTION" \
  'python .agents/bin/ledger.py add --category lesson "beware of rm -rf"
rm tracked.txt'
check 2 "(h20) rm at command position after a redirect" 'echo x > out.log; rm tracked.txt'

# =============================================================================
# (i) LIMITES ASSUMÉES, pas des oublis. Neutraliser les segments cités est ce
#     qui fait passer (g) ; le prix est qu'une suppression VOLONTAIREMENT cachée
#     dans une chaîne échappe au garde. Même trou que audit-gate.test.sh (f1).
#     Arms présents pour que ces trous soient VISIBLES et changent bruyamment
#     s'ils sont un jour comblés. Aucun n'était couvert par l'ancien garde non
#     plus : ce ne sont pas des régressions.
# =============================================================================
check 0 "(i1) KNOWN GAP: rm hidden inside a quoted bash -c"  'bash -c "rm tracked.txt"'
check 0 "(i2) KNOWN GAP: rm hidden inside a quoted eval"     'eval "rm tracked.txt"'
# (i3) FERMÉ par T-01M5D6XS2S (3e passe) : le mot de commande est lu guillemets
# retirés quand ses morceaux sont lisibles — le verbe cité est vu, comme sur les
# hôtes python (DIVERGENCE 1).
check 2 "(i3) CLOSED: the verb itself quoted as a word is read through its quotes" '"rm" tracked.txt'
check 0 "(i4) KNOWN GAP: verb assembled from a variable"     'V=rm; $V tracked.txt'

# =============================================================================
# (j) T-00000140 — LE GARDE NE DOIT PAS S'EFFACER EN SILENCE. Sans python la
#     charge utile PreToolUse (du JSON) est illisible : le garde ne voit RIEN.
#     Il ne bloque pas (un garde absent qui bloque fait boucler l'hôte) mais il
#     doit le DIRE. Python est simulé absent par des shims en tête de PATH qui
#     échouent au `--version` — sed/awk/cat restent disponibles, donc c'est bien
#     l'absence d'interpréteur qui est mesurée et rien d'autre.
# =============================================================================
STUB="$EVTMP/nopy"; mkdir -p "$STUB"
for c in python3 python py; do printf '#!/bin/sh\nexit 127\n' > "$STUB/$c"; chmod +x "$STUB/$c"; done
# La charge utile est construite AVANT, avec le vrai interpréteur : c'est le
# garde qu'on prive de python, pas le harnais.
DEG_PAYLOAD="$(json_payload 'rm tracked.txt')"
printf '%s' "$DEG_PAYLOAD" | PATH="$STUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
DEG_RC=$?
DEG_OUT="$(cat "$OUTF")"; DEG_ERR="$(cat "$ERRF")"
assert "$([ "$DEG_RC" -eq 0 ] && echo 0 || echo 1)" \
  "(j1) python absent => exit 0, never a block (got $DEG_RC)"
case "$DEG_ERR" in
  *"COVERAGE DEGRADED"*) assert 0 "(j2) python absent => COVERAGE DEGRADED on stderr";;
  *) assert 1 "(j2) python absent => COVERAGE DEGRADED on stderr (got: $DEG_ERR)";; esac
case "$DEG_OUT" in
  *"COVERAGE DEGRADED"*) assert 0 "(j3) python absent => COVERAGE DEGRADED in the systemMessage";;
  *) assert 1 "(j3) python absent => COVERAGE DEGRADED in the systemMessage (got: $DEG_OUT)";; esac
# Le systemMessage doit être du JSON VALIDE : un hook qui rend du JSON cassé sur
# stdout est un hook dont l'hôte ignore la sortie — donc muet à nouveau.
printf '%s' "$DEG_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'systemMessage' in d" 2>/dev/null
assert $? "(j4) the degraded systemMessage is valid JSON carrying systemMessage"
# NON-VACUITÉ de (j2)/(j3) : avec python PRÉSENT, le même rm est BLOQUÉ et ne
# parle pas de dégradation. Sans cet arm, un garde qui crierait COVERAGE
# DEGRADED en permanence passerait la suite.
printf '%s' "$DEG_PAYLOAD" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
OK_RC=$?
OK_ERR="$(cat "$ERRF")$(cat "$OUTF")"
case "$OK_ERR" in
  *"COVERAGE DEGRADED"*) assert 1 "(j5) python present => NO degradation claim";;
  *) assert "$([ "$OK_RC" -eq 2 ] && echo 0 || echo 1)" "(j5) python present => the same rm is blocked (exit 2, got $OK_RC) and claims no degradation";; esac

# =============================================================================
# (k) GARDE RAPATRIÉE — `rg` ABSENT DU PATH. Motif PROPRE : l'échec de ripgrep
#     est INDISCERNABLE d'un résultat vide, donc l'outil manquant FABRIQUE des
#     affirmations d'absence fausses. Mesuré sur un projet consommateur le
#     2026-08-06 : deux agents ont conclu « zéro occurrence » sur des balayages
#     qui n'avaient jamais tourné. La garde ne mord QUE sur l'absence — un rg
#     qui fonctionne ne peut pas produire ce mode de défaillance.
#     (k1)-(k10) viennent tels quels de la suite du consommateur ; (k11)-(k15)
#     sont l'apport du kit : l'ancrage en position de commande passe désormais
#     par la neutralisation des segments cités (étage 1), ce que leur version
#     par découpage de la charge utile BRUTE ne faisait pas.
# =============================================================================
if [ "$RG_SECTION_OK" -eq 1 ]; then
check_path "$PATH_NO_RG"   2 "(k1) rg absent est bloque"            "rg 'motif' src/"
check_path "$PATH_NO_RG"   2 "(k2) rg absent derriere un tube"      "cat f | rg motif"
check_path "$PATH_NO_RG"   2 "(k3) rg absent avec repli trompeur"   "rg motif || echo AUCUN"
check_path "$PATH_WITH_RG" 0 "(k4) rg present passe"                "rg 'motif' src/"
check_path "$PATH_WITH_RG" 0 "(k5) rg present derriere un tube"     "cat f | rg motif"
# Un mot CONTENANT rg n'est pas la commande rg — la reconnaissance porte sur un
# JETON en position de commande, comme pour rm/mv.
check_path "$PATH_NO_RG"   0 "(k6) argv n'est pas rg"               "echo \$argv"
check_path "$PATH_NO_RG"   0 "(k7) un chemin contenant rg"          "ls /srv/rgdata"
# La garde ne matche qu'en POSITION DE COMMANDE — mesure du terrain chez le
# consommateur : la version en sous-chaine bloquait le message de commit qui
# DECRIT la garde.
check_path "$PATH_NO_RG"   0 "(k8) rg cite dans du texte"           "git commit -m 'rg absent est bloque'"
check_path "$PATH_NO_RG"   0 "(k9) rg en argument, pas en commande" "grep -n ' rg ' notes.md"
check_path "$PATH_NO_RG"   0 "(k10) rg dans un nom de fichier"      "cat docs/rg-guard.md"
check_path "$PATH_NO_RG"   2 "(k11) rg apres && reste une commande" "make && rg motif src/"
check_path "$PATH_NO_RG"   2 "(k12) rg en substitution de commande" "echo \$(rg -c motif)"
# (k13)-(k14) — L'APPORT DU KIT, et les arms qui le rendent non vacuous : un
# MÉTACARACTÈRE à l'intérieur du texte cité fabriquait, chez le consommateur,
# une fausse position de commande juste devant `rg`. Ces deux formes-là étaient
# REFUSÉES chez eux ; l'étage 1 en fait de la donnée. Un mutant qui ramène la
# garde `rg` en découpage de la charge utile BRUTE ne tombe QUE sur ces deux-là.
check_silent_path "$PATH_NO_RG" "(k13) quoted rg mention preceded by a ';' inside the SAME quotes" \
  'git commit -m "wip; rg motif ne doit pas bloquer ici"'
# Le séparateur cité PRÉCÈDE la mention : c'est ce qui fabrique la fausse
# position de commande. Un `||` APRÈS `rg` ne prouverait rien (mesuré : l'arm
# restait vert contre le mutant qui supprime l'étage 1).
check_silent_path "$PATH_NO_RG" "(k14) ledger add whose --text quotes an rg command after a separator" \
  'python .agents/bin/ledger.py add --category lesson "rg absent" --text "make && rg motif imprimait AUCUN sans avoir tourne" --related T-00000088'
# (k15)-(k16) : les enveloppes SANS argument propre gardent la position de
# commande ouverte, donc la garde rapatriée en bénéficie comme rm/mv.
check_path "$PATH_NO_RG"   2 "(k15) rg derriere sudo"               "sudo rg motif src/"
check_path "$PATH_NO_RG"   2 "(k16) rg derriere xargs"              "ls | xargs rg motif"
# (k17) LIMITE ASSUMÉE, nommée plutôt que comblée de travers : la fenêtre
# d'enveloppe à arguments propres (`timeout 5 …`, `nice -n 10 …`) préfère le
# faux positif pour rm/mv — dangereux PARTOUT — mais pas pour `rg`, qui n'est
# dangereux qu'EXÉCUTÉ : l'élargir y bloquerait `sudo npm install rg`.
check_path "$PATH_NO_RG"   0 "(k17) KNOWN GAP: rg behind timeout and its duration" "timeout 5 rg motif"
# (k18)-(k23) UNE GARDE NE BLOQUE JAMAIS SON PROPRE DIAGNOSTIC. Defaut mesure sur
# ce depot le 2026-08-06 : `command -v rg` etait REFUSE, parce que `command` est
# une enveloppe et garde donc la position de commande ouverte. La seule commande
# qui etablit POURQUOI la garde mord se faisait mordre par elle. Une sonde imprime
# un chemin ou echoue ; elle ne lance jamais le nom sonde, donc elle ne peut pas
# produire le faux vide que cette garde-la combat.
check_path "$PATH_NO_RG"   0 "(k18) command -v rg est une SONDE, pas un lancement" "command -v rg"
check_path "$PATH_NO_RG"   0 "(k19) command -V rg de meme"           "command -V rg"
check_path "$PATH_NO_RG"   0 "(k20) which rg est une sonde"          "which rg"
check_path "$PATH_NO_RG"   0 "(k21) type rg est une sonde"           "type rg"
# (k22)-(k23) LA SONDE N OUVRE AUCUNE FENETRE : le drapeau meurt au separateur.
# Sans la remise a zero, ces deux formes passeraient — ce sont elles qui rendent
# le correctif sur et non seulement permissif.
check_path "$PATH_NO_RG"   2 "(k22) sonde PUIS lancement reste bloque" "command -v rg && rg motif src/"
check_path "$PATH_NO_RG"   2 "(k23) sonde PUIS lancement sur un tube"  "which rg; cat f | rg motif"
fi
# (k24)-(k26) L exemption de sonde vaut pour les TROIS gardes, pas seulement `rg`.
# Dans une fenetre d enveloppe, rm/mv preferent deliberement le faux positif — mais
# une SONDE n est pas un cas douteux, c est une commande qui n execute rien.
# (k26) prouve que la porte reste fermee juste apres : c est l arm qui distingue
# « exempter la sonde » de « exempter tout ce qui suit une enveloppe ».
check 0 "(k24) sudo which rm ne supprime rien"        "sudo which rm"
check 0 "(k25) command -v git ne restaure rien"       "command -v git"
check 2 "(k26) la sonde ne couvre que son mot"        "command -v git; git restore ."

# =============================================================================
# (m1)-(m6) UN CORPS DE HEREDOC EST DE LA DONNEE REDIRIGEE, PAS DU CODE
#   Incident du 2026-08-06, TROISIEME fois que cette garde bloque un texte qui
#   parle d elle : un message de commit passe en heredoc, decrivant une commande
#   gardee, a ete refuse. L etage 1 ne pouvait rien y faire — un corps de heredoc
#   n est pas CITE, il est REDIRIGE.
#   Les arms vont PAR PAIRES, et chaque paire porte le fail-open que le retrait
#   aurait pu introduire :
#     (m1)(m2) le corps litteral est de la donnee   <-> (m3) le corps a
#              delimiteur NU developpe `$(…)`, donc il reste analyse
#   (m1)(m2) ENONCENT LEUR PROPRE NON-VACUITE, sur le modele de (r1)-(r3)
#   (`:966-968`) : leurs corps portent les verbes gardes EN POSITION DE COMMANDE,
#   pas en simple mention derriere un mot de phrase. Un corps que le garde
#   laisserait passer de toute facon — parce que `rm` y suit un mot ordinaire —
#   ne mesurerait rien : il sortirait 0 avec OU sans l etage 0.5, donc l arm
#   resterait vert quand on retire ce qu il surveille. Corps en position de
#   commande, le mutant qui neutralise l etage 0.5 les fait analyser comme du
#   code et rougir.
#     (m4)     une mention CITEE de heredoc n ouvre aucun corps <-> (m5)(m6) la
#              ligne d introduction, elle, reste du code
#   (m7) n est pas une paire mais un TROU NOMME : le residu que le scrub
#   texte-entier assume dans le CORPS D UN HEREDOC A DELIMITEUR NU (T-00000208,
#   D2). Cette ligne annoncait « en zone NON-CODE » et couvrait aussi les
#   commentaires : c etait FAUX dans les deux sens — la variante commentaire
#   atteignait du CODE reel sur une autre ligne physique, et elle est desormais
#   FERMEE, epinglee par (n8)(n9). Voir le commentaire de (m7). Le corps NU est
#   ferme a son tour par T-01M5D6XS2S : (m7) asserte desormais le refus.
# =============================================================================
# (m1) NON-VACUITÉ : le corps porte les verbes gardés EN POSITION DE COMMANDE
# (chacun ouvre sa ligne), sur le modèle de (r1)-(r3) — un corps qui se
# contenterait de MENTIONNER `rm` derrière un mot de phrase (« la garde bloque
# rm -rf ») ne mesurerait rien : l'étage 2 ne tient un verbe pour exécuté qu'en
# position de commande, donc un tel corps sortirait 0 même sans l'étage 0.5. Ici
# le mutant qui neutralise l'étage 0.5 fait analyser ces deux lignes comme du
# code et rougir l'arm.
check 0 "(m1) corps litteral portant des commandes gardees EN POSITION DE COMMANDE" \
  "$(printf 'git commit -F - <<%sMSG%s\nrm -rf /\ngit restore .\nMSG' "'" "'")"
# (m2) NON-VACUITÉ, et pourquoi une ligne-témoin `rm` : `command -v rg && rg …`
# est bien en position de commande, MAIS la garde `rg` ne mord que si `rg` ne
# résout pas sur le poste — sur une machine portant ripgrep ce corps sortirait 0
# même sans l'étage 0.5, donc la vacuité dépendait du PATH. La ligne `rm -rf src/x`
# est le témoin DÉTERMINISTE : la garde rm mord partout, donc le mutant rougit
# indépendamment du poste.
check 0 "(m2) corps litteral portant sonde, lancement et suppression EN POSITION DE COMMANDE" \
  "$(printf 'cat <<%sEOF%s > notes.md\ncommand -v rg && rg motif src/\nrm -rf src/x\nEOF' "'" "'")"
# FAIL-OPEN QUE (m3) FERME : avec un delimiteur NU le shell developpe les
# substitutions de commande DANS le corps. Le consommateur retirait les deux.
check 2 "(m3) delimiteur NU : la substitution de commande s execute vraiment" \
  "$(printf 'cat <<EOF > f\n$(rm -rf /)\nEOF')"
# (m7) LE RÉSIDU ASSUMÉ DU SCRUB TEXTE-ENTIER (T-00000208, D2), épinglé ICI pour
# que les suites ne revendiquent pas plus que le garde ne tient. Depuis que
# l'étage 1 scanne le TEXTE ENTIER, une apostrophe vivant dans un corps de
# heredoc à DÉLIMITEUR NU peut s'apparier avec une apostrophe de code plus loin
# et neutraliser tout l'intervalle. L'étage 0.5 ne blanchit pas ce corps, et il a
# raison — cf. (m3) : le shell y développe `$(…)`, le retirer serait fail-open.
# Ici l'apostrophe de « don't » ouvre un segment que ferme celle de `echo 'x'`,
# et le `rm -rf` qui les sépare disparaît du texte analysé : ALLOW.
#
# CE COMMENTAIRE A ÉTÉ CORRIGÉ, ET LE MENSONGE VAUT D'ÊTRE DIT (revue de sécurité
# de classe 1, CRITICAL). Il annonçait DEUX zones résiduelles — le corps de
# heredoc nu ET LES COMMENTAIRES — en les rangeant toutes deux sous « zone
# NON-CODE », c'est-à-dire en affirmant que le trou ne touchait que de la donnée.
# C'était FAUX pour la variante commentaire, et mesuré par exécution contre le
# hook : `# don't run this` ⏎ `rm -rf src/x && echo 'ok'` sortait 0 EN SILENCE.
# Le `#` est bien du non-code, mais l'appariement qu'il ouvrait ATTEIGNAIT une
# LIGNE DE CODE RÉELLE, sur une autre ligne physique, que bash exécute. Une zone
# non-code qui blanchit du code n'est pas un trou « en zone non-code » : c'est un
# fail-open en zone code, de la même famille que (n7). La variante commentaire
# est donc FERMÉE (clause de frontière de commentaire à l'étage 1, réutilisant
# (b'') de l'étage 0.5) et épinglée par (n8)(n9) ; seul le corps de heredoc NU
# subsiste ici.
# CE QUI RESTE N'EST PAS UNE RÉGRESSION DÉGUISÉE, et l'arbitrage est écrit : le
# par-ligne qu'on remplace avait son PROPRE fail-open (n7), en zone CODE — la
# plus exposée — tandis que celui-ci est borné au corps d'un heredoc nu et est
# déjà porté par les trois hôtes python. Trou NOMMÉ, porté au board par
# T-00000224 (l'id, pas la prose : « versé au board » est invérifiable), jamais tu.
# Le jour où il se comble, cet arm rougit BRUYAMMENT et c'est ce qu'on lui
# demande.
# COMBLÉ PAR T-01M5D6XS2S (étape 2) : `scrub_spans` lit désormais les corps de
# heredoc — un corps NU (ou de premier niveau) garde ses guillemets LITTÉRAUX,
# seuls ses `$(…)` et backticks y sont du code —, donc l'apostrophe de « don't »
# n'ouvre plus rien et le `rm -rf` est vu. L'arm a rougi comme demandé ; il
# asserte maintenant le refus, pour la bonne raison.
check_deny_msg "checkpoint" "(m7) CLOSED (T-01M5D6XS2S): an apostrophe in a BARE heredoc body is literal, the rm after it is seen" \
  "$(printf 'cat <<EOF > f\ndon%st do this\nEOF\nrm -rf src/x && echo %sx%s' "'" "'" "'")"
# (m8) LA JUMELLE DU CRITICAL n°2 (T-00000208, revue de sécurité de classe 1).
# C'est la charge qui a DÉSIGNÉ le correctif de `audit-gate.sh` : jouée contre ce
# hook-ci elle sortait DÉJÀ 2, correctement bloquée, parce que l'étage 0.5
# blanchit le corps cité AVANT l'étage 1 — le faux appariement entre l'apostrophe
# de « don't » et le guillemet ouvrant de `echo 'end'` n'a jamais lieu. Le même
# texte contre `audit-gate.sh`, qui n'avait AUCUN étage heredoc, sortait 0 en
# silence. L'arm est ajouté ICI, alors qu'il était déjà vert, pour une raison
# précise : l'étage 0.5 est désormais DUPLIQUÉ VERBATIM dans les deux hooks, et
# les deux suites doivent épingler LA MÊME charge sur LE MÊME scanner — sans quoi
# une divergence entre les copies ne rougirait que d'un seul côté. Jumelle de
# (j1) dans audit-gate.test.sh. DEPUIS T-01M5D6XS2S les copies DIFFÈRENT :
# `scrub_spans` et l'automate `scan` de ce hook lisent la citation ANSI-C et les
# substitutions dans "…", ceux d'`audit-gate.sh` pas encore (T-01M5D8B1JJ).
check 2 "(m8) CRITICAL n2 twin: apostrophe in a QUOTED heredoc body must not mask the later rm" \
  "$(printf 'cat <<%sEOF%s\nit%ss not code\nEOF\nrm -rf src/legacy\necho %send%s' "'" "'" "'" "'" "'")"
# FAIL-OPEN QUE (m4) FERME : sans le test « le << survit-il a la neutralisation
# des citations », un message MENTIONNANT un heredoc effacerait la suite.
# LA CHARGE UTILE DOIT ETRE MULTI-LIGNE, et c est mesure : ecrit sur UNE ligne,
# cet arm etait VACUOUS — sans ligne suivante il n y a rien a effacer, donc le
# mutant qui retire le test survivait. Ici la ligne 2 est la victime du fail-open,
# et aucun delimiteur ne vient jamais la fermer.
check 2 "(m4) mention citee d un heredoc n ouvre aucun corps" \
  "$(printf 'echo %s<<%sEOF%s%s\nrm -rf /' '"' "'" "'" '"')"
check 2 "(m5) la ligne d introduction reste du code"  \
  "$(printf 'rm -rf / <<%sEOF%s\ndonnee\nEOF' "'" "'")"
check 2 "(m6) apres le delimiteur fermant, on est de nouveau du code" \
  "$(printf 'cat <<%sEOF%s > f\ntexte\nEOF\nrm -rf /' "'" "'")"

# =============================================================================
# (l) GARDE RAPATRIÉE — RESTAURATION GIT NON SCOPÉE. Motif PROPRE, distinct des
#     deux autres : elle DÉTRUIT du travail non commité, celui de TOUS les
#     agents, et ne laisse RIEN dans le reflog. Mesuré sur un projet
#     consommateur le 2026-08-06 : pendant un fan-out, deux tâches du board
#     créées la minute d'avant ont disparu et leurs identifiants ont été
#     réattribués. La garde est bornée à la forme qui prend TOUT ; un chemin
#     précis reste permis.
#     (l1)-(l11) viennent tels quels de la suite du consommateur ; (l12)-(l18)
#     sont l'apport du kit (étage 1 + position de commande + transparence aux
#     enveloppes), là où leur version matchait en SOUS-CHAÎNE.
# =============================================================================
check 2 "(l1) git restore ."                   "git restore ."
check 2 "(l2) git restore :/"                  "git restore :/"
check 2 "(l3) git restore --all"               "git restore --all"
check 2 "(l4) git checkout -- ."               "git checkout -- ."
check 2 "(l5) git checkout ."                  "git checkout ."
check 2 "(l6) git clean -fdx"                  "git clean -fdx"
check 2 "(l7) git restore . apres un tube"     "make build | git restore ."
check 0 "(l8) git restore d un CHEMIN precis"  "git restore packages/ui/src/styles.css"
check 0 "(l9) git checkout d une BRANCHE"      "git checkout main"
check 0 "(l10) git checkout -- un fichier"     "git checkout -- apps/web/app/page.tsx"
check 0 "(l11) git restore --staged un fichier" "git restore --staged src/a.ts"
# (l12)-(l14) — L'APPORT DU KIT, et les arms qui le rendent non vacuous. Chez le
# consommateur la garde matchait ` git restore . ` en SOUS-CHAÎNE de la charge
# utile normalisée, donc le message de commit et l'entrée de ledger qui
# DÉCRIVENT l'incident étaient eux-mêmes REFUSÉS. Chaque arm est apparié au
# mutant qui le TUE, ce qui est la seule façon de savoir qu'il mesure quelque
# chose (mesuré : (l13)/(l14) restent VERTS contre le mutant qui supprime
# l'étage 1, parce que le `(` et le `:` de `fix(hooks):` cassent la position de
# commande à eux seuls — il fallait donc un arm dédié pour l'étage 1) :
#   (l12) tombe contre le mutant « étage 1 supprimé » (séparateur cité AVANT) ;
#   (l13)-(l14) tombent contre le mutant « garde en SOUS-CHAÎNE », c'est-à-dire
#               contre l'implémentation d'origine du consommateur.
check_silent "(l12) quoted unscoped restore preceded by a ';' inside the SAME quotes" \
  'git commit -m "wip; git restore . a efface le travail de deux agents"'
check_silent "(l13) commit message quoting the unscoped restore it describes" \
  'git commit -m "fix(hooks): git restore . efface le travail non commite de tous"'
check_silent "(l14) ledger add whose --text quotes git clean -fdx" \
  'python .agents/bin/ledger.py add --category constraint "git clean" --text "ne jamais lancer git clean -fdx pendant un fan-out" --related T-00000088'
# (l15) `--staged` seul ne touche QUE l'index : aucun travail détruit, donc
# permis même sur `.`. C'est plus fin que la garde d'origine, jamais plus
# permissif sur l'arbre de travail — `--worktree` le ramène dans le périmètre.
check 0 "(l15) git restore --staged . touches the index only"  "git restore --staged ."
check 2 "(l16) git restore --staged --worktree . reaches the tree" "git restore --staged --worktree ."
# (l17)-(l18) : position de commande — enveloppe transparente, et option globale
# `-C <chemin>` qui prend une valeur (sans le saut, la sous-commande était
# manquée).
check 2 "(l17) unscoped restore behind sudo"   "sudo git restore ."
check 2 "(l18) unscoped restore behind git -C" "git -C repo restore ."
# (l19) LES VERDICTS NE SE MASQUENT PAS. Un `rm` sur la liste blanche temp dans
# la MÊME commande qu'un `git clean` : l'ancien étage 2 sortait au premier verbe
# reconnu, la liste blanche l'aurait donc laissée passer ENTIÈREMENT.
check 2 "(l19) whitelisted temp rm must not mask a git clean" \
  "rm -rf /tmp/scratch && git clean -fdx"
# (l20)-(l22) LIMITES ASSUMÉES, nommées : `git checkout -f <branche>` détruit
# aussi du travail non commité, et un glob (`git restore *`) aussi — ni l'un ni
# l'autre n'était couvert chez le consommateur, et les combler est un
# ÉLARGISSEMENT de la garde, pas un rapatriement. Arms présents pour que le trou
# soit visible et change bruyamment le jour où il est comblé.
# (l21) A CHANGÉ BRUYAMMENT, comme prévu : la passe binôme de T-00000762 lit `*`
# comme un pathspec LARGE (le shell le déploie en toutes les entrées du
# sommet), donc le trou est fermé et l'arm asserte désormais le refus.
check 0 "(l20) KNOWN GAP: git checkout -f <branch> also discards work" "git checkout -f main"
check_deny_msg "unscoped" "(l21) a glob pathspec is not a scope: git restore * is refused (gap closed by T-00000762)" "git restore *"
check 0 "(l22) KNOWN GAP: unscoped restore behind nice -n <n>"         "nice -n 10 git restore ."

# =============================================================================
# (n) T-00000181 — LE CONTOURNEMENT DE CLASSE 1 PAR GUILLEMET ÉCHAPPÉ.
#   L'étage 1 était un sed AVEUGLE À L'ÉCHAPPEMENT. Or `\"` est un guillemet
#   LITTÉRAL pour bash : dans (n1) le shell exécute vraiment le `rm -rf`, mais le
#   sed lisait les deux guillemets échappés comme UN segment cité couvrant tout
#   l'intervalle — le `;` ET le verbe — donc l'étage 2 ne coupait rien et le
#   garde se taisait. Reproduit par la revue de sécurité de T-00000151, laissé
#   ouvert et ÉPINGLÉ dans .agents/evals/test_guard_decision_parity.py (les
#   quatre lignes DIVERGENCE 5), fermé ici par le port de `quoted_spans()`.
#   Le motif est asserté, pas seulement le code de sortie (L-00000161).
#   Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#     étage 1 ramené au sed aveugle -> (n1)(n2)
#     scanner qui ignore TOUS les backslashes -> (n3)
#     scanner REVENU au balayage LIGNE PAR LIGNE (avant T-00000208) -> (n7)
#     dégradation muette / bloquante sur panne du scanner -> (n5)(n6)
# =============================================================================
check_deny_msg "checkpoint" "(n1) escaped DOUBLE quotes must not mask the separator and the rm" \
  'echo \" ; rm -rf src/x \"'
check_deny_msg "checkpoint" "(n2) escaped SINGLE quotes, same bypass" \
  "echo \\' ; rm -rf src/x \\'"
# (n3) LE CONTRÔLE, et il est ce qui interdit le correctif « ignorer les
# backslashes » : un nombre PAIR de `\` laisse le guillemet ouvrir un VRAI
# segment, donc bash n'exécute rien ici et le garde a raison de se taire.
check_silent "(n3) an EVEN backslash run leaves a genuine quoted segment" \
  'echo \\" ; rm -rf src/x \\"'
# (n4) CET ARM ÉPINGLAIT UN FAUX POSITIF, et le flip est DÉRIVÉ de bash, pas d'un
# confort de suite (T-00000208). Charge : `echo "unterminated \"` ⏎ `rm -rf src/x
# "`. Le `\"` est un guillemet ÉCHAPPÉ à l'intérieur du segment double ouvert par
# le premier `"` : il ne le ferme pas. La chaîne CONTINUE donc par-dessus le
# retour à la ligne jusqu'au `"` final de la ligne 2, et le tout est UN SEUL
# argument d'`echo`. Bash ne supprime RIEN ici, aucun checkpoint n'est menacé, et
# le garde a raison de se taire ; exiger un DENY revenait à refuser une charge
# inoffensive — exactement le défaut de T-00000146 que cette suite mesure par
# ailleurs. La direction inverse — les charges que bash EXÉCUTE vraiment — est
# mesurée par (n7), et c'est elle qui porte la non-régression.
check_silent "(n4) a double-quoted string CONTINUED across the newline is one echo argument" \
  'echo "unterminated \"
rm -rf src/x "'
# (n7) SONDE D'INVERSION MESURÉE — la charge que le balayage par ligne laissait
# passer, et la raison d'être de T-00000208. Bash ouvre un segment SIMPLE à la
# ligne 1 et le ferme à la ligne 2 (il enjambe le retour à la ligne) ; ce qui
# suit — le `rm -rf` — est donc du CODE NU que le shell EXÉCUTE, et la fin de
# ligne est un second segment cité. Le scanner par-ligne, lui, ne voyait de la
# ligne 2 que deux apostrophes orphelines, les appariait l'une à l'autre et
# neutralisait TOUT l'intervalle, le `rm` compris : ALLOW, fail-open, MESURÉ à
# exit 0 avant le correctif — un checkpoint cassé sans un mot. C'est le mutant
# tueur du retour au par-ligne.
check_deny_msg "checkpoint" "(n7) INVERSION: a quote pairing ACROSS the newline must not mask the rm" \
  "$(printf "echo 'a\nb' && rm -rf src/x && echo 'x'")"
# (n8)-(n11) LA FRONTIÈRE DE COMMENTAIRE DE L'ÉTAGE 1 — le CRITICAL de la revue de
# sécurité de classe 1, et la non-régression qui l'épingle. Le correctif de (n7)
# fermait le fail-open du par-ligne et en OUVRAIT un autre, mesuré par exécution
# contre le hook et non par lecture : un `#` de commentaire portant une
# apostrophe non appariée s'appariait, dans le scan TEXTE ENTIER, avec un vrai
# guillemet situé PLUS LOIN, et blanchissait tout l'intervalle — Y COMPRIS la
# ligne de code suivante, que bash exécute pour de bon. Bash, lui, n'ouvre JAMAIS
# rien avec un guillemet situé dans un commentaire : le commentaire s'arrête à sa
# ligne physique quel que soit son contenu.
#   HEAD (avant le passage au texte entier) -> exit 2, message « checkpoint »
#   après le passage au texte entier         -> exit 0, AUCUNE sortie, ALLOW muet
# (n8)(n9) SONT LA CHARGE EXACTE DU CRITICAL, une par garde touchée, et elles
# tuent le mutant « étage 1 sans frontière de commentaire » — c'est-à-dire le
# retour à l'état d'avant ce correctif. Elles assertent aussi le MOTIF : le seul
# code de sortie ne dirait pas laquelle des trois gardes a mordu.
check_deny_msg "checkpoint" "(n8) COMMENT BOUNDARY: an apostrophe in a # comment must not mask a later rm" \
  "$(printf "# don't run this\nrm -rf src/x && echo 'ok'")"
check_deny_msg "git clean" "(n9) COMMENT BOUNDARY: same payload, the unscoped-git guard" \
  "$(printf "# don't run this\ngit clean -fdx && echo 'ok'")"
# (n10) LE CONTRÔLE QUI INTERDIT LE CORRECTIF NAÏF, et sans lui (n8)(n9) seraient
# satisfaits par un scanner qui coupe à TOUT `#`. `$#` et `${#v}` sont des
# EXPANSIONS, pas des commentaires — bash n'y lit aucun commentaire — donc la
# clause exige un DÉBUT DE MOT et exclut `$` et `{` de `SEP`.
# SA FORME EST DÉRIVÉE, PAS DEVINÉE, et la première version écrite ici était
# VACUOUS : on avait posé `echo $# ${#v} ; rm -rf src/x` en DENY, en croyant
# qu'une coupe fautive « effacerait » la fin de ligne. Elle ne l'efface pas — la
# coupe n'exclut le reste de la ligne que de l'APPARIEMENT DES GUILLEMETS, le
# texte redescend intact — donc le mutant refusait aussi, et l'arm ne mesurait
# rien. Sur-couper ne peut donc produire qu'un FAUX POSITIF, et c'est LUI qu'il
# faut piéger : ici le `' ; rm -rf src/x'` final est un segment CITÉ que bash
# n'exécute pas, donc le garde doit se TAIRE. Si `$` ou `{` entraient dans `SEP`,
# la ligne serait coupée à `$#`, l'apostrophe ouvrante ne serait plus appariée,
# le `;` et le `rm` du segment cité redeviendraient du code aux yeux de l'étage 2
# — et le garde refuserait une charge inoffensive. Mesuré dans les deux sens.
check_silent "(n10) CONTROL: \$# and \${#v} are expansions, never a comment start" \
  'echo $# ${#v} '"'"' ; rm -rf src/x'"'"''
# (n11) LE FAUX POSITIF ASSUMÉ, épinglé pour qu'il soit MESURÉ et non découvert.
# La coupe n'EFFACE pas le commentaire : elle l'exclut seulement de l'appariement
# des guillemets, donc son texte redescend TEL QUEL aux étages 1-2 et y est
# analysé. Un commentaire qui contient un séparateur suivi d'un verbe gardé est
# donc REFUSÉ alors que bash ne l'exécute pas. C'est le côté sûr, et il est
# choisi : blanchir le commentaire collerait mieux à bash, mais ferait de cette
# clause une primitive d'EFFACEMENT — une reconnaissance fautive effacerait alors
# du code, et les lignes en `#` d'un corps de heredoc NU (où bash développe
# `$(…)`, cf. (m3)) disparaîtraient. Fail-open contre faux positif : on prend le
# faux positif, comme partout ailleurs dans ce fichier.
check 2 "(n11) KNOWN FALSE POSITIVE: a comment is analysed, not blanked" \
  '# nettoyage ; rm -rf src/x'

# (n5)-(n6) LA POSTURE DÉGRADÉE DU SCANNER. Même doctrine que (j1)-(j4), mais sur
# une panne DE L'ÉTAGE 1 et non sur l'absence d'interpréteur : si le scanner
# échoue, le garde n'a rien vu — il le DIT et sort 0. Jamais un exit 2 (un garde
# qui bloque quand son instrument casse bloque TOUS les appels Bash et fait
# boucler l'hôte), jamais un fail-open muet.
# LE SHIM EST SÉLECTIF, et c'est ce qui rend l'arm non vacuous : un python qui
# échouerait sur TOUT ferait retomber le garde sur le chemin (j) « pas de
# python », dont l'annonce est la même — l'arm mesurerait alors ce chemin-là.
# Ici seul le programme de l'étage 1 échoue, la lecture JSON et le hachage
# passent au vrai interpréteur, et le MOTIF est asserté pour prouver que c'est
# bien la panne du scrub qui est annoncée.
# LE DISCRIMINATEUR A DÛ ÊTRE RE-DÉRIVÉ (T-00000235) : il était `scrub_spans`,
# c'est-à-dire le NOM DE LA FONCTION, et ce nom ne distingue plus rien depuis que
# l'étage 0.5 porte la MÊME fonction, recopiée verbatim pour son veto. Le shim
# tuait alors l'étage 0.5, qui tourne AVANT, et l'arm mesurait sa panne à lui.
# La clé est donc `buf.append`, présent dans le seul programme de l'étage 1
# (l'étage 0.5 n'a ni `buf` ni le marqueur ` @@ `). La panne de l'étage 0.5 par
# la même racine est mesurée à part, par (s6) : on ne perd pas un chemin, on en
# nomme deux.
SCRUBSTUB="$EVTMP/scrubfail"; mkdir -p "$SCRUBSTUB"
for c in python3 python py; do
  cat > "$SCRUBSTUB/$c" <<EOSTUB
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *buf.append*) exit 9;;
esac
exec "$REAL_PY" "\$@"
EOSTUB
  chmod +x "$SCRUBSTUB/$c"
done
SCRUB_PAYLOAD="$(json_payload 'rm tracked.txt')"
printf '%s' "$SCRUB_PAYLOAD" | PATH="$SCRUBSTUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
SCRUB_RC=$?
SCRUB_OUT="$(cat "$OUTF")"; SCRUB_ERR="$(cat "$ERRF")"
case "$SCRUB_ERR" in
  *"COVERAGE DEGRADED"*"quote scrub failed"*)
    assert "$([ "$SCRUB_RC" -eq 0 ] && echo 0 || echo 1)" \
      "(n5) scrub en panne => COVERAGE DEGRADED nommant le scrub, et exit 0 (got $SCRUB_RC)";;
  *) assert 1 "(n5) scrub en panne => COVERAGE DEGRADED nommant le scrub (got: $SCRUB_ERR)";;
esac
printf '%s' "$SCRUB_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'COVERAGE DEGRADED' in d['systemMessage']" 2>/dev/null
assert $? "(n6) scrub en panne => systemMessage JSON valide portant l'annonce"

# =============================================================================
# (o) T-00000187 — L'ÉTAGE 0.5 (HEREDOC) AVEUGLE À L'ÉCHAPPEMENT ET À LA POSITION.
#   Même racine que (n), un étage plus haut : le `scrub()` interne de l'awk était
#   resté l'ALTERNANCE NAÏVE `'[^']*'|"[^"]*"`, et son `match()` cherchait le `<<`
#   PAR SOUS-CHAÎNE sur la ligne brute. Cinq formes d'une seule faute, toutes
#   FAIL-OPEN : l'étage 0.5 n'a qu'une primitive dangereuse, le BLANCHIMENT, donc
#   un faux corps ouvert EFFACE les lignes suivantes — les commandes qu'elles
#   portent ne sont jamais vues, et la garde sort 0 sans un mot.
#
#   RÈGLE DE CONCEPTION que ces arms pinnent, et qui prime sur les clauses : on
#   coupe PLUS que bash, jamais moins — toute reconnaissance incomplète dégrade
#   vers TEXTE ANALYSÉ (au pire un faux positif aux étages 1-2), jamais vers
#   effacement. Chaque arm « DOIT » ci-dessous a été tracé ROUGE contre l'awk
#   d'avant, un par un : aucun ne mesure rien.
#
#   Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#     étage 0.5 ramené à l'awk aveugle (gsub naïf + match flottant)
#                                        -> (o1)(o4)(o5)(o7)(o8)(o8b)(o9)
#     spans de l'étage 0.5 ignorant l'échappement       -> (o1)
#     `<<` cherché en SOUS-CHAÎNE au lieu de l'automate -> (o7)(o9)
#     `match()` flottant / retry sur un candidat suivant -> (o4)(o9)
#     clause (b') retirée (non apparié qui n'ouvre rien) -> (o5)
#     clause (b'') retirée, ou bornée au seul blanc      -> (o8)(o8b)
#     `\r` retiré des SEULES lignes de corps au lieu de TOUTES -> (o6)
#     étage 0.5 qui blanchit dès qu'un `<<` traîne quelque part -> (o2)(o3)
# =============================================================================
OSQ="'"; ODQ='"'; OBS='\'
# (o1) LE PAYLOAD DE TÊTE. Bash lit `\"` comme un guillemet LITTÉRAL, donc
# `"b <<'EOF' c"` est un segment CITÉ — de la donnée — aucun heredoc n'ouvre et la
# ligne 2 exécute vraiment le `rm`. Le gsub naïf appariait le guillemet ÉCHAPPÉ
# avec le vrai ouvrant, le `<<` survivait à la neutralisation, et le faux corps —
# jamais fermé — blanchissait jusqu'à la fin de la commande.
check_deny_msg "checkpoint" "(o1) an ESCAPED quote must not fabricate a heredoc that blanks the rm" \
  "$(printf 'echo %s%s a %sb <<%sEOF%s c%s\nrm -rf src/x' "$OBS" "$ODQ" "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
# (o2) LE CONTRÔLE de (o1) : la visibilité rendue ne doit pas devenir un faux
# positif sur du bénin. Même ligne 1, ligne 2 inoffensive.
check_silent "(o2) the same escaped-quote line over a benign second line stays silent" \
  "$(printf 'echo %s%s a %sb <<%sEOF%s c%s\necho done' "$OBS" "$ODQ" "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
# (o3) LE CONTRÔLE INVERSE : un VRAI corps reste de la DONNÉE. (b') ne casse pas
# cet arm — `\"` est un guillemet ÉCHAPPÉ, jamais un ouvrant non apparié pour
# l'automate — et le corps PORTE deux commandes gardées EN POSITION DE COMMANDE
# (une par ligne) sans être refusé. La position de commande est ce qui rend l arm
# NON-VACUOUS : un corps qui se contenterait de mentionner `rm` derrière un mot de
# phrase sortirait 0 même sans l étage 0.5 ; ici le mutant qui le neutralise fait
# analyser ces lignes comme du code et rougit l arm.
check_silent "(o3) a GENUINE heredoc body carrying guarded commands AT COMMAND POSITION stays data" \
  "$(printf 'echo %s%s ; git commit -F - <<%sMSG%s\nrm -rf /\ngit restore .\nMSG' "$OBS" "$ODQ" "$OSQ" "$OSQ")"
# (o4) MAUVAIS DÉLIMITEUR. Une mention CITÉE `<<'B'` précède un VRAI `<<'A'` : le
# `match()` leftmost prenait `B`, jamais fermé, donc le corps courait jusqu'au
# bout. Le motif asserté est « checkpoint », PAS « catastrophic » : c'est ce qui
# prouve que le corps (`rm -rf /`, ligne 2) a bien été blanchi ET que la ligne 4
# a survécu. Un correctif qui n'ouvrirait aucun corps ferait remonter ROOT et
# rougir cet arm.
check_deny_msg "checkpoint" "(o4) a quoted <<'B' must not steal the delimiter of the real <<'A'" \
  "$(printf 'echo %sx <<%sB%s%s <<%sA%s\nrm -rf /\nA\nrm -rf src/x' "$ODQ" "$OSQ" "$OSQ" "$ODQ" "$OSQ" "$OSQ")"
# (o5) GUILLEMET NON APPARIÉ ENJAMBANT LE RETOUR À LA LIGNE. Bash lit un segment
# cité sur deux lignes : aucun heredoc. Un scan ligne-par-ligne où « non apparié
# n'ouvre rien » compterait `<<'X'` comme hors span et BLANCHIRAIT la ligne 2 —
# ce choix, fail-CLOSED à l'étage 1, est fail-OPEN ici. Fermé par (b').
check_deny_msg "checkpoint" "(o5) an unmatched quote before the << opens no body" \
  "$(printf 'echo %sa <<%sX%s\nb%s ; rm -rf src/x' "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
# (o6) PIN DE CONTRAT, VERTE AVANT ET APRÈS — fins de ligne CRLF. Le `\r` est
# retiré de CHAQUE ligne au stockage, pas des seules lignes de corps : sans ce
# retrait GLOBAL, `EOF\r` != `EOF`, le corps ne ferme jamais et le `rm` de la
# ligne 4 est blanchi. Elle tue ce mutant-là et lui seul.
check_deny_msg "checkpoint" "(o6) CRLF line endings must not stop the closing delimiter from matching" \
  "$(printf 'cat <<%sEOF%s > f\r\ndata\r\nEOF\r\nrm -rf src/x' "$OSQ" "$OSQ")"
# (o7) `<<` RECONNU PAR SOUS-CHAÎNE. Bash lit `\<` littéral puis une simple
# redirection `<'X'` : aucun heredoc. Fermé par (b) — un `<` précédé d'un `\`
# actif ne forme JAMAIS `<<`.
check_deny_msg "checkpoint" "(o7) an escaped \\< never forms a << operator" \
  "$(printf 'echo %s<<%sX%s\nrm -rf src/x' "$OBS" "$OSQ" "$OSQ")"
# (o8)(o8b) COMMENTAIRE. Rien au-delà d'un `#` non cité en DÉBUT DE MOT n'ouvre
# de corps. Le début de mot bash inclut l'après-séparateur, d'où (o8b) : borner
# la clause au seul blanc laisserait `;#` ouvrir un faux corps. Les exceptions
# `$` et `{` (pour `$#` et `${#v}`) sont conformes à bash et ne recréent aucun
# fail-open — bash n'y lit pas non plus un commentaire.
check_deny_msg "checkpoint" "(o8) a << inside a comment after a blank opens no body" \
  "$(printf 'echo x # <<%sX%s\nrm -rf src/x' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(o8b) a << inside a comment after a ';' separator opens no body" \
  "$(printf 'echo x;# <<%sX%s\nrm -rf src/x' "$OSQ" "$OSQ")"
# (o9) HERESTRING. `<<<` n'est pas un heredoc. Le `match()` flottant trouvait
# `<<'X'` à l'offset+1 et blanchissait la suite. Fermé par l'ANCRAGE au PREMIER
# candidat de l'automate, SANS retry : la RE échoue à l'offset 0 (le troisième
# `<` n'est pas un délimiteur), et l'on ne réessaie pas à l'offset 1 — un retry
# rouvrirait exactement ce trou.
check_deny_msg "checkpoint" "(o9) a herestring <<< must not be read as a heredoc" \
  "$(printf 'cat <<<%sX%s\nrm -rf src/x' "$OSQ" "$OSQ")"

# =============================================================================
# (p) T-00000187, REVUE DE SÉCURITÉ — DEUX FRONTIÈRES QUE L'ÉNUMÉRATION (o) NE
#     NOMMAIT PAS, ET QUI TOMBAIENT TOUTES DEUX DU CÔTÉ INTERDIT : L'EFFACEMENT.
#   La règle de conception de l'étage était écrite mais pas TENUE PAR LE CODE.
#   Chaque charge ci-dessous a été mesurée deux fois : bash exécute vraiment la
#   ligne, et la garde sortait 0 en silence.
#
#   F1 — LE CORPS S'OUVRAIT À LA LIGNE PHYSIQUE SUIVANTE, ALORS QUE BASH L'OUVRE
#   APRÈS LA LIGNE LOGIQUE. La clause (b') ne regardait que les guillemets non
#   appariés situés AVANT le `<<` (`0 <= loose < at`), et aucune autre forme de
#   continuation. Une ligne qui ne se termine pas dans un état NEUTRE prolonge la
#   commande : le corps ne commence pas là où l'étage le croyait, et tout ce qui
#   sépare les deux était blanchi.
#     (p1) guillemet non apparié APRÈS le `<<`      -> `loose >= 0`
#     (p2) segment cité multi-ligne portant lui-même la mention `<<'EOF'`
#     (p3) `\` final : continuation de ligne         -> `cont`
#     (p4) `$(` non refermé en fin de ligne          -> `cont`
#
#   F2 — LA RE MATCHAIT UN PRÉFIXE DU MOT DÉLIMITEUR. (p5) : sur `cat <<'A'B`
#   bash concatène après suppression des quotes, son délimiteur est `AB` ; la
#   garde capturait `A`, ne trouvait jamais de ligne `A` nue, et SUR-BLANCHISSAIT
#   jusqu'à la fin. La POLARITÉ est ce qui range ce défaut ici et non parmi les
#   trous assumés : la RE RÉUSSISSAIT sur un préfixe -> EFFACEMENT, là où une RE
#   qui ÉCHOUE ne coûte qu'un texte analysé.
#   T-00000187 avait fermé F2 en EXIGEANT une frontière de mot, ce qui faisait
#   ÉCHOUER la RE sur `<<'A'B` — sûr, mais faux positif. T-00000210 la ferme pour
#   de bon : le parseur de pièces lit `AB`, le vrai délimiteur de bash, et (p5)
#   mesure désormais que le corps se referme LÀ. L'arm n'a pas changé de charge
#   ni de verdict ; il a changé de mutant tueur, et c'est écrit plutôt que tu.
#
#   Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#     (b') rendue au test borné `0 <= loose < at`      -> (p1)(p2)
#     détection de continuation `\` retirée            -> (p3)
#     suivi de `$(` / backtick non refermé retiré      -> (p4)
#     délimiteur = PREMIÈRE pièce au lieu de la concaténation des pièces -> (p5)
#     frontière de mot TAIL retirée après la dernière pièce -> (r6)
#   La ligne 4 de (p5) porte un verbe GARDÉ là où la sonde du reviewer portait un
#   marqueur inerte : un arm qui ne peut pas rougir ne mesure rien.
# =============================================================================
check_deny_msg "checkpoint" "(p1) an unmatched quote AFTER the << continues the logical line" \
  "$(printf 'cat <<%sEOF%s %sabc\ndef%s ; rm -rf src/x\nEOF' "$OSQ" "$OSQ" "$ODQ" "$ODQ")"
check_deny_msg "checkpoint" "(p2) a multi-line quoted segment carrying the <<'EOF' mention opens no body" \
  "$(printf 'echo %sabc\ndef <<%sEOF%s ghi%s ; ls\nrm -rf src/x\nEOF' "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
check_deny_msg "checkpoint" "(p3) a trailing backslash continues the line, so the body starts later" \
  "$(printf 'cat <<%sEOF%s %s\n; rm -rf src/x\nEOF' "$OSQ" "$OSQ" "$OBS")"
check_deny_msg "checkpoint" "(p4) an unclosed \$( continues the line, so the body starts later" \
  "$(printf 'cat <<%sEOF%s $(echo\nrm -rf src/x\n)\nEOF' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(p5) the delimiter is the CONCATENATION of the pieces, never a PREFIX of it" \
  "$(printf 'cat <<%sA%sB\ndata\nAB\nrm -rf src/x' "$OSQ" "$OSQ")"

# =============================================================================
# (q) T-00000187, RE-REVUE DE SÉCURITÉ — LA MÊME ERREUR STRUCTURELLE UNE COUCHE
#     PLUS BAS : `cont` ÉTAIT UNE ÉNUMÉRATION, BASH A PLUS DE FORMES QU'ELLE.
#   (p) avait fermé « la ligne physique doit se terminer dans un état neutre » en
#   listant TROIS constructions de prolongement. Le commentaire énonçait un
#   universel que sa propre liste démentait — exactement le défaut que
#   `plan-critic` avait nommé à son itération 3, et que la règle de conception
#   interdit : on borne l'erreur du côté sûr UNE FOIS, pas clause par clause.
#   Quatre formes échappaient, chacune mesurée deux fois (bash exécute vraiment
#   la ligne suivante / la garde sortait 0 en silence), chacune avec son contrôle
#   de non-vacuité (même charge sans le heredoc -> rc=2) :
#     (q1) `${x:-`  — `$` n'était suivi que si le caractère d'après était `(`
#     (q2) `$[1`    — idem, `$[` échappait
#     (q3) `(( 1`   — seul `$(` incrémentait, une parenthèse NUE n'était jamais
#                     comptée
#     (q4) `<(echo` — substitution de processus, même cause que (q3)
#   Le remède n'est pas une cinquième, sixième, septième clause : c'est un
#   PRÉDICAT CLOS — trois compteurs d'équilibre génériques sur `()`, `[]`, `{}`,
#   tenus hors des spans cités et après échappement, plancher à 0. Sur-refuser
#   sur un déséquilibre ne coûte qu'ANALYSÉ, le côté sûr.
#
#   Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#     compteur `{}` retiré (ou `$` suivi seulement de `(`)   -> (q1)
#     compteur `[]` retiré                                    -> (q2)
#     compteur `()` restreint au seul `$(`                    -> (q3)(q4)
#   NE PROLONGENT PAS, et ne doivent donc PAS être refusés — mesuré par le
#   reviewer, pinné par les heredocs légitimes déjà verts ((m1)(m2)(m6)(o3)(o6)) :
#   `&&`, `||`, `|`, un `(` de sous-shell, `{`, `if`, `for`, `case` en fin de
#   ligne. `a=(1` et `[[ x` sont des erreurs de syntaxe bash : rien ne s'exécute.
# =============================================================================
check_deny_msg "checkpoint" "(q1) an unclosed \${ continues the line, so the body starts later" \
  "$(printf 'cat <<%sEOF%s ${x:-\ny} ; rm -rf src/x\nEOF' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(q2) an unclosed \$[ continues the line, so the body starts later" \
  "$(printf 'cat <<%sEOF%s $[1\n+2] ; rm -rf src/x\nEOF' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(q3) a BARE unbalanced (( continues the line, so the body starts later" \
  "$(printf 'cat <<%sEOF%s ; (( 1\n)) ; rm -rf src/x\nEOF' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(q4) an unclosed <( process substitution continues the line" \
  "$(printf 'cat <<%sEOF%s <(echo\nrm -rf src/x\n)\nEOF' "$OSQ" "$OSQ")"

# =============================================================================
# (r) T-00000210 — LE MOT DÉLIMITEUR EST UNE CONCATÉNATION DE PIÈCES, PAS UN MOT
#     CITÉ D'UN SEUL TENANT. La RE `<<-?[ \t]*('W'|"W")` n'admettait qu'UNE
#     pièce, entièrement citée. Bash, lui, construit le délimiteur en concaténant
#     des pièces citées ET nues, PUIS retire les quotes : `<<\EOF` et `<<E"O"F`
#     valent `EOF`, `<<'A'B` vaut `AB`, et dans les trois cas AU MOINS une pièce
#     est citée — donc le corps est de la DONNÉE 100 % littérale pour bash.
#     LE DÉFAUT ÉTAIT UN FAUX POSITIF, jamais un fail-open, et c'est ce qui le
#     distingue de (o)(p)(q) : la RE ÉCHOUAIT, donc le corps restait ANALYSÉ et
#     un refus tombait sur de la donnée. Mesuré avant le correctif sur les DEUX
#     gardes : (r1)(r2)(r3) sortaient 2 — un message de commit refusé parce qu'il
#     décrit une commande gardée, c'est-à-dire l'incident fondateur de l'étage,
#     rejoué par une autre porte.
#
#     LA POLARITÉ EST INCHANGÉE, et c'est la condition de tout le reste : le
#     corps n'est blanchi que si AU MOINS UNE PIÈCE EST CITÉE. Un délimiteur
#     entièrement NU garde son corps ANALYSÉ, parce que bash y développe `$(…)`
#     — (m3) le mesure et doit rester VERT ; le mutant qui blanchirait les corps
#     nus est tué là, pas ici.
#
#     LE PARSEUR EST CLOS, DONC IL REFUSE PLUS QU'IL N'ADMET : pièces `'X'`,
#     `"X"`, `\c`, ou nue, contenu borné au jeu `[A-Za-z0-9_]`, frontière de mot
#     exigée en fin. Toute non-reconnaissance rend `""` — corps CONSERVÉ, donc
#     ANALYSÉ. (r5)(r6) épinglent ce côté d'erreur : ce sont des FAUX POSITIFS
#     ASSUMÉS (bash traiterait ces corps en donnée), et ils sont là pour qu'un
#     élargissement futur du jeu soit un choix mesuré, jamais un glissement.
#
#     Appariement aux mutants — chaque arm doit être TUÉ par au moins un :
#       parseur ramené à la RE `('W'|"W")` (l'état d'avant)  -> (r1)(r2)(r3)
#       le corps de la forme échappée ne se referme jamais    -> (r4)
#       jeu de caractères d'une pièce CITÉE non vérifié       -> (r5)
#       frontière de mot TAIL retirée après la dernière pièce -> (r6)
#       délimiteur = PREMIÈRE pièce au lieu de la concaténation -> (p5), qui
#         reste l'arm de cette propriété : sous ce mutant `<<'A'B` retient `A`,
#         ne trouve jamais sa clôture et sur-blanchit jusqu'à la fin
#       `quoted` ignoré, corps NU blanchi                     -> (m3)
# =============================================================================
# (r1)(r2) LES DEUX FORMES DE L'INCIDENT. Corps en position de COMMANDE, pas une
# simple mention : un corps que le garde laisserait passer de toute façon ne
# mesurerait rien (le piège de non-vacuité que (l13)/(l14) documentent).
check_silent "(r1) a backslash-quoted delimiter <<\\EOF makes its body literal data" \
  "$(printf 'git commit -F - <<%sEOF\nrm -rf src/x\nEOF' "$OBS")"
check_silent "(r2) a partially quoted delimiter <<E\"O\"F makes its body literal data" \
  "$(printf 'git commit -F - <<E%sO%sF\nrm -rf src/x\nEOF' "$ODQ" "$ODQ")"
# (r3) `<<'A'B` — LA MOITIÉ « CORPS BLANCHI » de l'arm dédié. Bash attend `AB` ;
# la ligne 4 prouve que la commande gardée de la ligne 2 a bien été effacée du
# texte analysé, et non que la garde s'est tue pour une autre raison.
check_silent "(r3) <<'A'B closes on AB, and the body in between is data" \
  "$(printf 'cat <<%sA%sB\nrm -rf src/x\nAB\necho ok' "$OSQ" "$OSQ")"
# (r4) LA MOITIÉ « LE CODE REPREND » pour la forme échappée — jumelle de (p5),
# qui tient la même propriété pour `<<'A'B`. Sans elle, un parseur qui reconnaît
# `<<\EOF` mais ne referme jamais son corps blanchirait la ligne 4 et rendrait
# (r1) vert pour la mauvaise raison : le fail-open exact que (r1) pourrait cacher.
check_deny_msg "checkpoint" "(r4) after the closing EOF of a <<\\EOF body, we are code again" \
  "$(printf 'git commit -F - <<%sEOF\ndata\nEOF\nrm -rf src/x' "$OBS")"
# (r5)(r6) LE CÔTÉ D'ERREUR IMPOSÉ : toute non-reconnaissance laisse le corps
# ANALYSÉ. Les deux sont des FAUX POSITIFS DÉLIBÉRÉS — bash tient ces deux corps
# pour de la donnée (une pièce citée est présente dans chacun), la garde refuse
# quand même parce que le délimiteur sort du jeu clos. C'est le prix ASSUMÉ de la
# clôture du parseur, et il se paie en ANALYSÉ, jamais en effacement.
#   (r5) espace dans une pièce citée : `<<'E F'` -> hors jeu `[A-Za-z0-9_]`
#   (r6) `$` après la dernière pièce : `<<'A'$x` -> pas de frontière de mot
check_deny_msg "checkpoint" "(r5) a delimiter piece outside the closed charset leaves the body ANALYSED" \
  "$(printf 'cat <<%sE F%s\nrm -rf src/x\nE F' "$OSQ" "$OSQ")"
check_deny_msg "checkpoint" "(r6) a missing word boundary after the last piece leaves the body ANALYSED" \
  "$(printf 'cat <<%sA%s$x\nrm -rf src/x\nA' "$OSQ" "$OSQ")"

# (s1)-(s5) L'ÉTAT DE CITATION INTER-LIGNES — T-00000235, le CRITICAL RACINE dont
# (o)(p)(q)(r) ne sont que les copies. L'étage 0.5 décide ouvreur / pas-ouvreur
# sur une ligne PHYSIQUE isolée : son garde-fou `loose` ne voit qu'une quote non
# refermée SUR CETTE LIGNE-LÀ, et n'a aucune mémoire du fait que la ligne est
# déjà à l'intérieur d'un guillemet ouvert PLUS HAUT — état que seul le balayage
# TEXTE ENTIER de l'étage 1 connaît, et qui tourne APRÈS par construction.
# Il croit donc à un ouvreur, blanchit jusqu'au délimiteur (absent) donc jusqu'à
# la FIN, et efface au passage le guillemet fermant RÉEL **et** la commande
# gardée qui le suit, hors de toute citation. L'étage 1 ne voit jamais cette
# commande : elle a disparu avant son tour. FAIL-OPEN, en zone CODE.
#   MESURÉ le 2026-08-19 sur les SIX gardes des QUATRE hôtes, avec contrôle de
#   non-vacuité : charge nue -> exit 2 ; même charge précédée des deux lignes
#   -> exit 0, AUCUNE sortie, ALLOW muet.
# CORRECTIF : un candidat `<<` n'est un ouvreur que si son offset n'est à
# l'intérieur d'AUCUN segment cité du texte entier — la règle de l'étage 1,
# RECOPIÉE VERBATIM, jamais paraphrasée. (s5) épingle cette copie.
# (s1) LA CHARGE EXACTE. Trois lignes, n'utilisant AUCUN des contournements déjà
# fermés : ni échappement (o1), ni prolongement (p)(q), ni parseur de pièces (r),
# ni frontière de commentaire (n8). Elle tue le mutant « étage 0.5 sans veto ».
check_deny_msg "checkpoint" "(s1) ROOT: a heredoc opener INSIDE a string opened on an EARLIER line must not blank the rm" \
  "$(printf 'echo %sline1\ncat <<%sX%s\n%s && rm -rf src/x' "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
# (s2) LE CONTRÔLE DE NON-VACUITÉ de (s1), et il n'est pas décoratif : sans lui,
# un garde qui refuserait TOUT rendrait (s1) vert sans rien mesurer.
check_deny_msg "checkpoint" "(s2) NON-VACUITY of (s1): the bare payload is refused" \
  'rm -rf src/x'
# (s3) LE CONTRÔLE NÉGATIF ANTI-RÉGRESSION, et c'est lui qui interdit le
# correctif paresseux « ne reconnaître aucun heredoc ». Un heredoc à délimiteur
# CITÉ, non précédé d'une quote ouverte, dont le corps DÉCRIT une commande
# gardée, reste de la DONNÉE — c'est l'incident FONDATEUR de l'étage 0.5. Un veto
# qui sur-tire le refuserait, la suite resterait verte sur (s1), et l'étage
# entier serait mort sans que rien ne le dise.
check_silent "(s3) ANTI-REGRESSION: a legitimate quoted-delimiter body is still DATA" \
  "$(printf 'git commit -F - <<%sEOF%s\nrm -rf src/x\nEOF' "$OSQ" "$OSQ")"
# (s4) LA MÊME CHARGE EN CRLF — le piège d'offsets, et il vise CETTE machine.
# L'étage 0.5 retire le `\r` de CHAQUE ligne au stockage. Si les segments cités
# sont calculés sur le texte D'ORIGINE et les candidats `<<` repérés sur le texte
# RECONSTRUIT, les offsets se décalent d'un caractère par ligne portant un `\r` :
# le veto vise à côté et le fail-open revient, sur un dépôt Windows c'est-à-dire
# partout ici. Le veto se calcule donc APRÈS la reconstruction.
check_deny_msg "checkpoint" "(s4) CRLF: the same payload with CRLF endings is refused too (offset alignment)" \
  "$(printf 'echo %sline1\r\ncat <<%sX%s\r\n%s && rm -rf src/x' "$ODQ" "$OSQ" "$OSQ" "$ODQ")"
# (s5) LE PRIX NOMMÉ DE LA TROISIÈME COPIE. Les étages 0.5 et 1 sont deux
# programmes python SÉPARÉS : rien ne peut être appelé de l'un à l'autre, et un
# fichier d'aide partagé est exclu (un hook qui `source` un voisin acquiert un
# mode de panne que le hook autonome n'a pas). `scrub_spans` est donc recopiée
# VERBATIM dans l'étage 0.5. Une duplication qu'un test surveille est une
# duplication ; une duplication que personne ne mesure est la prochaine
# divergence — et c'est EXACTEMENT le mécanisme qui a produit (s1).
# (s6) LA CONSÉQUENCE ASSUMÉE DU VETO SUR LA POSTURE DÉGRADÉE, et elle se pinne
# plutôt qu'elle ne se subit. L'étage 0.5 dépend désormais de la MÊME règle que
# l'étage 1 : si cette règle casse, c'est l'étage 0.5 qui tombe D'ABORD, puisqu'il
# tourne avant. Le contrat, lui, ne bouge pas d'un cheveu — annonce nommée,
# `systemMessage` JSON valide, exit 0, JAMAIS exit 2. Sans cet arm, ce chemin
# deviendrait le seul de la posture dégradée à n'être mesuré nulle part, et
# (n5) semblerait l'avoir remplacé alors qu'elle mesure l'autre.
HDSTUB="$EVTMP/heredocfail"; mkdir -p "$HDSTUB"
for c in python3 python py; do
  cat > "$HDSTUB/$c" <<EOSTUB2
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *heredoc_delimiter*) exit 9;;
esac
exec "$REAL_PY" "\$@"
EOSTUB2
  chmod +x "$HDSTUB/$c"
done
printf '%s' "$(json_payload 'rm tracked.txt')" | PATH="$HDSTUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
HD_RC=$?
HD_OUT="$(cat "$OUTF")"; HD_ERR="$(cat "$ERRF")"
case "$HD_ERR" in
  *"COVERAGE DEGRADED"*"heredoc stage failed"*)
    assert "$([ "$HD_RC" -eq 0 ] && echo 0 || echo 1)" \
      "(s6) stage 0.5 down => COVERAGE DEGRADED naming the heredoc stage, exit 0 (got $HD_RC)";;
  *) assert 1 "(s6) stage 0.5 down => COVERAGE DEGRADED naming the heredoc stage (got: $HD_ERR)";;
esac
printf '%s' "$HD_OUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); assert 'COVERAGE DEGRADED' in d['systemMessage']" 2>/dev/null
assert $? "(s6b) stage 0.5 down => valid JSON systemMessage carrying the announcement"
# T-00000762 : la passe rm/mv PAR OPÉRANDE est un TROISIÈME programme python
# séparé, qui refait le scan isométrique de l'étage 1 — donc une TROISIÈME copie
# de `scrub_spans`, pour la même raison (aucun fichier d'aide partagé). Le bras
# ne se relâche pas, il s'étend : il compte TROIS copies et les compare TOUTES.
# Une copie qui dériverait dans la passe rougit ici, comme les deux autres.
sb_copies=$(grep -c 'def scrub_spans(text):' "$HOOK")
sb_a="$(awk '/def scrub_spans\(text\):/{n++} n==1{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK")"
sb_b="$(awk '/def scrub_spans\(text\):/{n++} n==2{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK")"
sb_c="$(awk '/def scrub_spans\(text\):/{n++} n>=3{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK")"
# Le statut passe par un `if`, jamais par un `$?` posé derrière une liste
# AND : `A && B && C; rc=$?` marche, mais toute ligne insérée entre les deux
# le casse EN SILENCE, et shellcheck le refuse (SC2319).
if [ "$sb_copies" -eq 3 ] && [ -n "$sb_a" ] && [ "$sb_a" = "$sb_b" ] && [ "$sb_a" = "$sb_c" ]; then sb_rc=0; else sb_rc=1; fi
assert "$sb_rc" "(s5) the three scrub_spans copies (stage 0.5, stage 1, per-operand rm/mv pass) are byte-identical"
# (s5) ÉTENDU AUX AIDES (T-01M5D6XS2S, C6). Les aides de `scrub_spans` (single,
# opaque — ajoutée par la passe de correction F3 —, double, delimiter, bare,
# bodies, code) sont IMBRIQUÉES dans la fonction, donc
# comparées avec elle ci-dessus ; une aide de premier niveau qu une copie
# appelle et pas l autre échapperait à la comparaison — elle n existe pas (le
# compte des `def` ci-dessous le tient). Le décodeur ANSI-C est l aide PARTAGÉE
# hors de `scrub_spans` : deux copies (table de l étage 1, passe rm/mv),
# comparées octet pour octet.
sb_nested=$(awk '/def scrub_spans\(text\):/{n++} n==1{print; if ($0 ~ /^    return spans$/) exit}' "$HOOK" | grep -c '^    def ')
ad_copies=$(grep -c 'def ansi_decode(body):' "$HOOK")
ad_a="$(awk '/def ansi_decode\(body\):/{n++} n==1{print; if ($0 ~ /^    return s$/) exit}' "$HOOK")"
ad_b="$(awk '/def ansi_decode\(body\):/{n++} n==2{print; if ($0 ~ /^    return s$/) exit}' "$HOOK")"
if [ "$sb_nested" -eq 7 ] && [ "$ad_copies" -eq 2 ] && [ -n "$ad_a" ] && [ "$ad_a" = "$ad_b" ]; then ad_rc=0; else ad_rc=1; fi
assert "$ad_rc" "(s5b) the scrub_spans helpers are nested (7) and the two ansi_decode copies (stage 1 table, rm/mv pass) are byte-identical (nested $sb_nested, copies $ad_copies)"

echo "----------------------------------------"
echo "safe-bash.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
