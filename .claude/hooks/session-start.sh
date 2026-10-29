#!/usr/bin/env bash
# SessionStart — silently inject the compressed index so no agent starts cold.
# The task board goes in SORTED (running → blocked → pending → recent done) so
# the active task is the first thing the agent sees, not line 1 of a raw file.
# Layout: .agents/bin = tooling, .agents/state = what the kit generates.
BIN="$CLAUDE_PROJECT_DIR/.agents/bin"
STATE="$CLAUDE_PROJECT_DIR/.agents/state"
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
[ -n "$PY" ] || {
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  exit 0
}
# session.start emitted here — AFTER $PY resolves but BEFORE either early
# exit 0 below (empty CTX at the tail of this script) — so it fires even on
# an un-indexed or empty-context repo (T-00000018 item 4).
bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" session.start >/dev/null 2>&1 || true
CTX=""
# Blocs qui doivent TOUJOURS passer (sorties sans binôme) :
# placés en tête et hors de toute coupe par le budget en fin de script.
_SS_CRIT=""
# Deterministic, 0-LLM index freshness refresh — reader-side, no new hook
# registration. Guarded on SYMBOLS.md already existing: this refresh never does
# a first full scan. An adopter's first scan comes from the bootstrap launched
# below, detached (amorcage_auto.py -> setup_projet.py, index leg, T-00001103);
# in the kit, or on a repo the bootstrap skips, it stays an explicit /index decision.
# Best-effort only — a failed or slow refresh must never cost the agent its
# index/board/ledger, so failures are swallowed.
# `|| true` neutralises the exit code but NOT a hang — a stalled git inside the
# builder would freeze every SessionStart, so the call carries a hard 5s wall
# bound, mirroring the Python hooks' subprocess timeout. If timeout(1) is absent
# on this shell, the refresh is skipped entirely: blocking risk beats freshness.
if [ -f "$BIN/build_index.py" ] && [ -f "$STATE/index/SYMBOLS.md" ] \
   && command -v timeout >/dev/null 2>&1; then
  timeout 5 "$PY" "$BIN/build_index.py" --root "$CLAUDE_PROJECT_DIR" --if-stale >/dev/null 2>&1 || true
fi
# L'index est LU ici mais AJOUTÉ après board, ledger et CI (T-00000834) : sous
# le budget d'injection, ce qui déborde est coupé par la fin, et c'est le board
# qui doit survivre, pas le détail des modules.
_SS_IDX=""
[ -f "$STATE/index/CODEBASE_INDEX.md" ] && _SS_IDX="$(cat "$STATE/index/CODEBASE_INDEX.md")"
# ---- LES DEUX FORMES D'UN MAGASIN (T-00001012, BK-419, E-26) ---------------
# Un magasin est PRÉSENT sous son monolithe OU dès qu'un `*.json` régulier NON
# pointé vit dans son dossier d'enregistrements (format de T-00001008 ; un nom
# pointé est le temporaire d'une écriture atomique, ignoré à la lecture). Seule
# la GARDE change : le contenu vient toujours de l'API (`tasks.py list
# --session`, `ledger.py context`), donc la sortie sur le monolithe ne bouge pas
# d'un octet, et le budget `SS_BUDGET` plus bas s'applique aux deux formes.
# BORNES ÉCRITES. (a) Les miroirs Codex, Copilot, Kimi (`.codex/hooks/
# session_context.py`) et Gemini (`.gemini/hooks/session_context.py`) ne voient
# PAS la forme dossier avant la tâche de bascule (S-01M4KKMXW2ZSGFY6SW42HJJN96) :
# parité INÉGALE, inerte tant qu'aucun magasin réel n'a basculé. (b) Domicile du
# board = `board/tasks/` (et `board/epics/`), décision S-01M4N1G4VXD01A3W54Y9FR9856,
# que T-00001009 reprend ou modifie dans le même commit. (c) Le périmètre de
# T-00001012 est celui des HOOKS : un lecteur brut du monolithe hors hooks
# (`core-scripts/check-stale-justification.sh:183,317`) est porté à T-00000727.
# Glob sans `dotglob` : `*.json` n'attrape aucun nom pointé ; sans
# correspondance il reste littéral et `[ -f ]` le rejette (mesuré bash 3.2).
_ss_forme_presente() {  # $1 = monolithe, $2 = dossier d'enregistrements
  [ -f "$1" ] && return 0
  local _f
  for _f in "$2"/*.json; do
    [ -f "$_f" ] && return 0
  done
  return 1
}
if _ss_forme_presente "$STATE/board/TASKS.json" "$STATE/board/tasks"; then
  # TASKS.json is the source of truth; TASKS.md is its generated view. Fall back
  # to that view if tasks.py is missing or the store is malformed — a broken
  # board must never cost the agent its index.
  # `list --session` bounds the pending rows (T-00000834: 339 pending weighed
  # 46.8 kB on every call of every session); the cut is announced in the view.
  # A tasks.py without the flag falls back to the bare list, then to the view.
  BOARD="$("$PY" "$BIN/tasks.py" --root "$CLAUDE_PROJECT_DIR" list --session 2>/dev/null)" \
    || BOARD="$("$PY" "$BIN/tasks.py" --root "$CLAUDE_PROJECT_DIR" list 2>/dev/null)" \
    || BOARD="## TASK BOARD"$'\n'"$(head -30 "$STATE/local/TASKS.md" 2>/dev/null)"
  CTX="$CTX$BOARD"
fi
if _ss_forme_presente "$STATE/memory/LEDGER.json" "$STATE/memory/entries"; then
  # LEDGER.json is the source of truth for institutional memory; context() is
  # the single selection point (all active constraints + the 5 most recent
  # active lesson/decision entries, capped ~2500 chars). Same silent fallback
  # as the board — a broken ledger must never cost the agent its index or board.
  LEDGER="$("$PY" "$BIN/ledger.py" --root "$CLAUDE_PROJECT_DIR" context 2>/dev/null)" || LEDGER=""
  [ -n "$LEDGER" ] && CTX="$CTX"$'\n\n'"$LEDGER"
fi
# ---- AMORÇAGE LANCÉ (T-00001103, décision pilote S-01M5WBHK9H374YBEMAY51ES754) --
# Placé APRÈS board et ledger : ils sont lus avant que le run détaché n'écrive
# les stores. amorcage_auto.py lance setup_projet.py DÉTACHÉ (nouvelle session,
# stdin fermé, sorties au journal : il ne tient pas le pipe du hook) et rend une
# ligne de STATUT (lancé / en cours / échec + journal + remède / non lancé :
# cause) ou rien (kit, amorçage déjà réussi). Bloc CRITIQUE : hors coupe.
# `timeout 5` borne un appel bloqué là où timeout(1) existe ; un macOS nu ne l'a
# pas (mesuré, rc 127) : appel direct, l'appel ne fait qu'un Popen (< 1 s).
# Échec non bloquant : `|| _SS_AMO=""`, le contexte n'est jamais perdu.
if [ -f "$BIN/amorcage_auto.py" ]; then
  if command -v timeout >/dev/null 2>&1; then
    _SS_AMO="$(timeout 5 "$PY" "$BIN/amorcage_auto.py" --root "$CLAUDE_PROJECT_DIR" </dev/null 2>/dev/null)" || _SS_AMO=""
  else
    _SS_AMO="$("$PY" "$BIN/amorcage_auto.py" --root "$CLAUDE_PROJECT_DIR" </dev/null 2>/dev/null)" || _SS_AMO=""
  fi
  # Séparateur APRÈS la ligne : _SS_CRIT part en tête, collé au board qui suit.
  [ -n "$_SS_AMO" ] && _SS_CRIT="$_SS_CRIT$_SS_AMO"$'\n\n'
fi
# ---- ÉTAT DE CHANTIER — LE RÉVEIL D'UN TRAVAIL EN COURS (T-012) -------------
# CE QUE CE BLOC RÉPARE. Le board dit QUELLE tâche tourne, le ledger dit ce que
# le projet a APPRIS. Aucun des deux ne dit PAR OÙ REPRENDRE un chantier long :
# où l'état se lit, ce qui refusera, la porte. Depuis S-00003374 (T-00001064),
# `PLAN-ETAT.md` est ce POINT D'ENTRÉE — un routeur court ; l'état lui-même vit
# au board, dans le journal des checkpoints et dans la reprise du lot. Sans ce bloc, une reprise
# le lendemain recommençait par une enquête que quelqu'un avait déjà faite.
#
# LA CONVENTION EST UN FICHIER À LA RACINE, `PLAN-ETAT.md`. Sa PRÉSENCE arme le
# bloc et son ABSENCE est le régime normal : un dépôt sans chantier long n'a pas
# ce fichier, ne voit rien, et ne paie rien. C'est pour ça que le bloc VOYAGE
# sans risque — chez un adoptant il est inerte jusqu'au jour où il décide de
# s'en servir, et ce jour-là il n'a rien à configurer.
#
# BORNÉ, ET LA TRONCATURE EST DITE. Un état de chantier grossit — c'est même le
# but, puisqu'il accumule décisions et file. Injecté en entier il finirait par
# écraser l'index et le board qui le précèdent, et une troncature muette se lit
# « le chantier s'arrête là ». La borne est donc en OCTETS — `wc -c` et `head -c`
# comptent des octets, pas des caractères — et quand elle mord elle l'écrit dans
# le contexte. Cette ligne a dit « CARACTÈRES » jusqu'au 2026-09-14, et le
# message de troncature avec elle : sur un fichier en français, où un accent
# pèse deux octets, les deux unités divergent d'environ 3 % — assez pour qu'un
# rédacteur qui vise la borne au caractère la dépasse en octets sans le voir.
#
# `head -c` COUPE À L'OCTET et peut donc trancher au milieu d'un caractère
# accentué. Le résidu est illisible mais inoffensif — il part dans du JSON que
# Python sérialise, pas dans un terminal. Couper proprement demanderait un
# passage Python de plus au démarrage, et ce bloc tient à ne rien coûter quand
# il ne sert pas.
_PLAN_ETAT="$CLAUDE_PROJECT_DIR/PLAN-ETAT.md"
if [ -f "$_PLAN_ETAT" ]; then
  # 50 000 DEPUIS LE 2026-09-21, DÉCISION PILOTE — TROISIÈME relèvement, même
  # symptôme et même motif : « pourquoi le fichier ne fait que grossir ? passe
  # le fichier à 50k ». Ce jour-là la tête pesait 19 944 octets, à 56 du
  # plafond, et la mise à jour de T-650 avait coûté QUATRE réécritures plus le
  # retrait de deux passages périmés — dont un qu'il a fallu établir au board
  # avant d'y toucher. CE QUE LA RÉPÉTITION ENSEIGNE, et qui n'était pas écrit
  # aux deux premiers coups : le budget n'est pas ce qui fait grossir le
  # fichier, il ne fait que rendre la croissance douloureuse au plus mauvais
  # moment — à l'écriture, quand on a autre chose à finir. La croissance a une
  # cause STRUCTURELLE : ajouter est sans friction, retirer exige d'ÉTABLIR
  # qu'un passage est périmé (relevé au board, à la trace), donc l'ajout gagne
  # toujours. Relever la borne ne corrige pas ça ; ça cesse seulement de faire
  # payer l'arbitrage à celui qui écrit. Le vrai remède reste éditorial et vit
  # au § 7 du fichier : l'ÉTAT se REMPLACE, la doctrine reste, le reste descend
  # dans PLAN-ETAT-DETAIL.md.
  # HISTORIQUE. À 6 000, la tête de PLAN-ETAT.md
  # rasait la borne (5 988) et chaque édition devenait un arbitrage de budget :
  # trois fois dans la même journée, du contenu utile a été rogné pour faire
  # tenir un ajout. Le pilote a tranché le 2026-09-14 : « augmente le budget au
  # lieu de me faire perdre du temps », et la borne est passée à 12 000.
  # LE MÊME SYMPTÔME EST REVENU LE 2026-09-19 : la tête pesait 11 984 octets,
  # à 16 du plafond ; noter qu'une consigne pilote avait été LEVÉE a suffi à
  # faire déborder, et il a fallu réécrire l'ajout deux fois pour le faire
  # tenir. Même décision, même motif — d'où 20 000, puis 50 000 deux jours plus
  # tard.
  # LA BORNE RESTE DÉCLARÉE ET NON MESURÉE : rien n'établit que 50 000 soit le
  # bon chiffre, et ce commentaire ne prétend pas le contraire. Ce qui est
  # établi, c'est le SENS de l'erreur à commettre — on écrit ce qu'il faut et
  # on POUSSE au détail quand ça déborde, au lieu de tailler dans l'utile.
  # LA VALEUR NE SE RECOPIE NULLE PART : `test_plan_etat_decisions.py:53-55` la
  # LIT ici par regex sur `_PE_MAX`. Changer ce chiffre suffit ; un nombre écrit
  # en dur ailleurs se périmerait sans faire rougir personne.
  _PE_MAX=50000
  _PE_TAILLE="$(wc -c < "$_PLAN_ETAT" 2>/dev/null)" || _PE_TAILLE=0
  _PE_CORPS="$(head -c "$_PE_MAX" "$_PLAN_ETAT" 2>/dev/null)" || _PE_CORPS=""
  # `_PE_MAX` BORNE LA LECTURE ET LA TAILLE DU FICHIER (décision pilote, tenue
  # par test_plan_etat_decisions.py) ; ce qui est INJECTÉ est borné plus bas par
  # SS_BUDGET, et l'état de chantier y passe EN DERNIER, dans ce qui reste.
  if [ -n "$_PE_CORPS" ]; then
    _PE_ENTETE=$'\n\n'"## ÉTAT DE CHANTIER — PLAN-ETAT.md"$'\n'
    _PE_ENTETE="$_PE_ENTETE""Un chantier long est en cours dans ce dépôt. Lis PLAN-ETAT.md AVANT"$'\n'
    _PE_ENTETE="$_PE_ENTETE""d'enquêter : il dit par où commencer et où l'ÉTAT se lit (board, journal)."$'\n'
    _PE_ENTETE="$_PE_ENTETE""Il n'est PAS un journal : n'y écris que si un invariant change."$'\n\n'
  fi
fi
# ---- SORTIES SANS BINÔME — RENDRE VISIBLE CE QUI SE PROMETTAIT VISIBLE ------
# T-00000603 (3), relevé du binôme de clôture. La garde d'affirmation
# (T-00000602) offre une échappatoire ponctuelle et écrit chaque usage dans
# `.agents/state/local/affirmation-sorties.log`, en promettant que la sortie
# « reste visible ». ELLE NE L'ÉTAIT PAR PERSONNE : ce journal est git-ignoré, et
# `git grep` ne rendait ZÉRO consommateur hors le hook qui l'écrit. Une garde qui
# promet une visibilité qu'elle ne tient pas est de la même famille que le défaut
# que ce lot corrige ailleurs — une doc qui affirme une garantie absente.
#
# LE SEUL ENDROIT OÙ ÇA SE LIT EST LE DÉMARRAGE DE SESSION, parce que c'est le
# seul moment où quelqu'un regarde l'état sans l'avoir cherché. Trois dernières
# lignes : assez pour qu'une dérogation répétée saute aux yeux, assez peu pour
# ne jamais concurrencer l'index et le board.
#
# SILENCIEUX QUAND IL N'Y A RIEN, et c'est le régime normal — un dépôt qui n'a
# jamais dérogé ne voit pas ce bloc et ne paie rien.
#
# BORNÉ EN OCTETS, PAS EN LIGNES, et le compte porte sur les DÉROGATIONS. Ma
# première rédaction affirmait que ces lignes étaient « bornées à la source » :
# c'était FAUX, et le binôme l'a mesuré — la garde lisait sa raison sans borne et
# sans aplatir les sauts de ligne, donc UNE dérogation produisait 112 082 octets
# sur 3 lignes physiques, réinjectés en entier à chaque session, sous un en-tête
# annonçant « 3 au total ». La source est corrigée aussi ; ici on se protège des
# journaux déjà écrits par l'ancienne forme, et d'un fichier binaire, puisqu'une
# ligne qui n'ouvre pas sur un horodatage n'est plus comptée ni montrée.
#
# Le bon patron est à vingt lignes au-dessus — le bloc PLAN-ETAT borne en octets
# ET annonce sa troncature. Il aurait suffi de le regarder.
_SORTIES="$CLAUDE_PROJECT_DIR/.agents/state/local/affirmation-sorties.log"
if [ -s "$_SORTIES" ]; then
  _SO_MOTIF='^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T'
  _SO_N="$(grep -c "$_SO_MOTIF" "$_SORTIES" 2>/dev/null)" || _SO_N=0
  _SO_CORPS="$(grep "$_SO_MOTIF" "$_SORTIES" 2>/dev/null | tail -3 | cut -c1-400)"
  _SO_CORPS="$(printf '%s' "$_SO_CORPS" | head -c 1400)"
  if [ -n "$_SO_CORPS" ]; then
    # BLOC CRITIQUE : il va dans _SS_CRIT, que le budget plus bas place EN TÊTE
    # et ne coupe jamais (T-00000834).
    _SS_CRIT="$_SS_CRIT"$'\n\n'"## SORTIES SANS BINÔME — $_SO_N au total, 3 dernières"$'\n'
    _SS_CRIT="$_SS_CRIT""La garde d'affirmation a été franchie par son échappatoire. Chacune"$'\n'
    _SS_CRIT="$_SS_CRIT""était censée rester VISIBLE : les voici, bornées à 400 caractères."$'\n'
    _SS_CRIT="$_SS_CRIT""DEUX OU PLUS SOUS LA MÊME PORTE : ouvre une tâche qui nomme la règle"$'\n'
    _SS_CRIT="$_SS_CRIT""contournée — ce n'est plus une exception, c'est la garde qui ne tient"$'\n'
    _SS_CRIT="$_SS_CRIT""pas. Journal entier : .agents/state/local/affirmation-sorties.log"$'\n\n'
    _SS_CRIT="$_SS_CRIT""$_SO_CORPS"
  fi
fi
# ---- RELEVÉ CI (T-00000379, lot B) ------------------------------------------
# LE CANAL A DEUX BOUTS, ET CELUI-CI EST LE LECTEUR. `--cached` ne touche NI le
# réseau NI `gh` : il rend la dernière mesure connue, DATÉE. L'écrivain est
# l'étape avant-push de la skill `verification-discipline` — le moment où l'état
# de la CI compte, et où l'on s'apprête de toute façon à attendre.
#
# ZÉRO ATTENTE AU DÉMARRAGE, ET C'EST LE POINT. L'auteur d'origine appelle ici le
# script complet, donc il paie le mur réseau (8 s + 1 s par workflow) à chaque
# session. Un rafraîchissement détaché a été écarté : sous Git-Bash il échoue en
# silence, et un écrivain incertain rendrait le mécanisme inerte.
#
# GARDE ANCRÉE SUR $CLAUDE_PROJECT_DIR, JAMAIS LE CWD NU — reprise de l'auteur
# d'origine, et elle porte : les fixtures d'`events-wiring` n'ont pas de
# `core-scripts/`, donc la garde est fausse sur les DEUX jambes du différentiel
# byte-à-byte, et aucun test n'écrit le cache du vrai dépôt.
if [ -f "$CLAUDE_PROJECT_DIR/core-scripts/ci-last-run.sh" ]; then
  CI_LINES="$(bash "$CLAUDE_PROJECT_DIR/core-scripts/ci-last-run.sh" --cached 2>/dev/null)" || CI_LINES=""
  [ -n "$CI_LINES" ] && CTX="$CTX"$'

'"## CI — dernier run sur main"$'
'"$CI_LINES"
fi
[ -n "$_SS_IDX" ] && CTX="$CTX"$'\n\n'"$_SS_IDX"

# ---- BUDGET D'INJECTION (T-00000834, décision pilote du 2026-09-29) ---------
# CLAUDE CODE NE REND AU MODÈLE UN additionalContext QU'EN DESSOUS D'ENVIRON
# 10 000 CARACTÈRES ; au-delà il l'écrit dans un fichier et ne transmet qu'un
# APERÇU de 2 ko. Relevé le 2026-09-29 sur 72 injections de hook, tous dépôts :
# la plus grosse passée entière pèse 9 615 caractères (9 943 octets), la plus
# petite réduite 19,7 ko — le seuil est donc entre les deux, et l'hôte compte en
# CARACTÈRES. TOUTES les injections de ce hook depuis le 2026-09-24 (72 à 85 ko)
# ont été réduites à l'aperçu — le début de l'index. Board, ledger et état de
# chantier n'atteignaient donc JAMAIS le modèle, sans un seul message d'erreur.
# D'où un budget TOTAL, en octets (un octet ne compte jamais moins qu'un
# caractère), sous la borne basse relevée. Ordre : blocs CRITIQUES en tête et
# jamais coupés, puis index/board/ledger/CI, puis l'état de chantier dans ce
# qui reste ; toute coupe est DITE.
# BORNE NON MESURÉE : une coupe `head -c` au milieu d'un caractère UTF-8 rend un
# caractère de remplacement côté hôte (mesuré POSIX) ; sous Git Bash, où argv
# passe en UTF-16, ce cas n'est PAS mesuré.
SS_BUDGET=9400
_SS_N_CRIT="$(printf '%s' "$_SS_CRIT" | wc -c | tr -d ' ')"
_SS_PLAFOND=$(( SS_BUDGET - _SS_N_CRIT ))
# L'état de chantier se compose À PART (_SS_PE) : son en-tête et son pointeur
# sont hors coupe comme les blocs critiques — sans eux la session ne sait même
# pas qu'un chantier est en cours.
_SS_PE=""
if [ -n "${_PE_ENTETE:-}" ]; then
  _SS_N_CTX="$(printf '%s' "$CTX" | wc -c | tr -d ' ')"
  _SS_N_ENT="$(printf '%s' "$_PE_ENTETE" | wc -c | tr -d ' ')"
  _PE_N_CORPS="$(printf '%s' "$_PE_CORPS" | wc -c | tr -d ' ')"
  # 300 octets réservés à la ligne de coupe qui suit.
  _SS_RESTE=$(( _SS_PLAFOND - _SS_N_CTX - _SS_N_ENT - 300 ))
  if [ "$_PE_N_CORPS" -le "$_SS_RESTE" ] && [ "$_PE_TAILLE" -le "$_PE_MAX" ]; then
    _SS_PE="$_PE_ENTETE$_PE_CORPS"
  elif [ "$_SS_RESTE" -ge 1500 ]; then
    # Une tête qui porte au moins un paragraphe, et la coupe dite.
    _SS_TETE="$(printf '%s' "$_PE_CORPS" | head -c "$_SS_RESTE")"
    _SS_N_TETE="$(printf '%s' "$_SS_TETE" | wc -c | tr -d ' ')"
    _SS_PE="$_PE_ENTETE$_SS_TETE"$'\n\n'"[TRONQUÉ : $_SS_N_TETE octets injectés sur $_PE_TAILLE (budget d'injection $SS_BUDGET) — lis PLAN-ETAT.md en entier avant d'enquêter]"
  else
    # Moins qu'un paragraphe vaut moins qu'un pointeur : on n'injecte que lui.
    _SS_PE="$_PE_ENTETE""[NON INJECTÉ : $_PE_TAILLE octets, budget d'injection $SS_BUDGET épuisé — lis PLAN-ETAT.md en entier avant d'enquêter]"
  fi
fi
# GARDE-FOU : quoi qu'aient pesé les blocs précédents, jamais au-delà du budget,
# et jamais une coupe muette — un aperçu silencieux est exactement la panne
# que ce budget répare. Blocs critiques et état de chantier sont hors coupe ;
# la coupe mord par la FIN du reste, donc sur l'index avant le board.
# LA RÉSERVE DE LA LIGNE DE COUPE se prend AU MOMENT de la coupe, et là seulement
# (T-01M4NBTSPT14QQD75XG0AB36X2) : la tête coupée laisse 300 octets à sa ligne
# `[CONTEXTE TRONQUÉ : …]`, sans quoi cette ligne débordait le budget qu'elle
# annonce tenir (9 558 octets pour 9 400, mesuré). Prise sur tout le plafond,
# elle couperait à tort un contexte qui tenait sans coupe (9 221 octets, mesuré).
# Un plafond sous 300 borne la tête à 0 : `head -c` négatif rend « tout sauf la
# fin », rc 0 (mesuré head macOS et GNU) — un débordement muet.
_SS_N_PE="$(printf '%s' "$_SS_PE" | wc -c | tr -d ' ')"
_SS_PLAFOND=$(( _SS_PLAFOND - _SS_N_PE ))
_SS_N_CTX="$(printf '%s' "$CTX" | wc -c | tr -d ' ')"
if [ "$_SS_N_CTX" -gt "$_SS_PLAFOND" ]; then
  _SS_COUPE=$(( _SS_PLAFOND - 300 ))
  [ "$_SS_COUPE" -lt 0 ] && _SS_COUPE=0
  CTX="$(printf '%s' "$CTX" | head -c "$_SS_COUPE")"
  CTX="$CTX"$'\n\n'"[CONTEXTE TRONQUÉ : $_SS_COUPE octets sur $_SS_N_CTX — python .agents/bin/tasks.py list et ledger.py context donnent le reste ; PLAN-ETAT.md dit où l'état se lit]"
fi
CTX="$_SS_CRIT$CTX$_SS_PE"

[ -z "$CTX" ] && exit 0
"$PY" - "$CTX" << 'PYEOF'
import json, sys
try:
    # T-00000025 shard 2 - dashboard daemon, launched fully DETACHED (GATE B,
    # S-00000041: DEVNULL on all three stdio handles + DETACHED_PROCESS |
    # CREATE_NEW_PROCESS_GROUP on Windows; start_new_session on POSIX). The
    # child dedupes against state/local/dashboard.lock on its own. Fail-open
    # by contract: this block may never raise and never touch stdout - the
    # hook's stdout stays the single JSON line below, byte-identical whether
    # the launch works, dedupes, or crashes at import (GATE B item 5).
    import os, re, subprocess
    _root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if _root and not os.path.exists(_root):
        _m = re.match(r"^/([A-Za-z])/(.*)$", _root)  # MSYS /c/... -> c:/... (L-003)
        if _m and os.path.exists(_m.group(1) + ":/" + _m.group(2)):
            _root = _m.group(1) + ":/" + _m.group(2)
    _daemon = os.path.join(_root, ".agents", "bin", "dashboard_daemon.py")
    if _root and os.path.exists(_daemon):
        _kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if _flags:
            _kw["creationflags"] = _flags
        else:
            _kw["start_new_session"] = True
        subprocess.Popen([sys.executable, _daemon, "--daemon", "--root", _root], **_kw)
except Exception:
    pass
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[AUTO-INJECTED INDEX — do not re-read these files]\n" + sys.argv[1]}}))
PYEOF
exit 0
