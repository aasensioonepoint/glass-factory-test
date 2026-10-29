#!/usr/bin/env bash
# =====================================================================
# BANC — PARITÉ DES SURFACES D'HÔTES (T-00000379, lot C)
#
# REPRIS de `op-agentic-builder-kit/core-scripts/host_sync.test.sh`, mais RÉÉCRIT :
# ce n'est pas une copie. L'original porte DIX sections, dont quatre exigent des
# surfaces que le plan de reprise REFUSE, et toutes ses assertions sont des
# LITTÉRAUX de comptage (« 25 fichiers », « 11 commandes », « 10 skills »). Un
# littéral périme en silence : il rougit le jour où le dépôt bouge légitimement,
# et l'auteur le « corrige » en changeant le nombre — la garde ne garde plus rien.
#
# ICI TOUT COMPTE EST DÉRIVÉ DE L'ARBRE AU MOMENT DU RUN. Aucun nombre d'agents,
# de commandes ou de skills n'est écrit dans ce fichier.
#
# ---------------------------------------------------------------------
# LES DIX SECTIONS DE L'ORIGINAL, STATUÉES UNE PAR UNE
# ---------------------------------------------------------------------
#   §1  cardinal des répertoires d'agents (25 × 5 hôtes, littéral)
#       -> RE-DÉRIVÉ. Hôtes découverts par GLOB, cardinal pris sur l'hôte de
#          référence. `.kimi-code/` EST désormais énuméré : T-00000394 l'a adopté
#          comme 6e hôte (parité surface + câblage), et le glob l'a pris tout seul
#          — exactement le renversement que ce commentaire anticipait (T-00000379
#          refusait ce 6e hôte ; la directive pilote de pleine parité l'a tranché).
#   §2  parité des NOMS d'agents
#       -> REPRIS, comparateur factorisé et MUTÉ (arm §2b).
#   §3  existence des skills d'atelier (liste close, `mode` compris)
#       -> RE-DÉRIVÉ sur NOS surfaces : chaque commande doit avoir sa skill
#          homonyme. « `mode` exclu » serait un NO-OP ici — `mode` ne sera jamais
#          une de nos commandes. RÉVISION D'ARBITRAGE (T-00000393) : `/mode`
#          reste refusé comme COMMANDE, mais le motif d'origine (« il contredit
#          AGENTS.md "Never downgrade a model" ») ne portait que sur les modes
#          DESCENDANTS. T-00000393 importe `core-scripts/apply-mode.py
#          {expert|restore|status}` — UPGRADE SEULEMENT, les modes descendants
#          de la source ne sont pas repris — donc un SCRIPT, jamais une
#          commande, et cette section reste inchangée. Le cas RÉEL fut `dash` :
#          commande d'observabilité longtemps SANS skill, exclue AVEC sa raison.
#          T-00000544 lui a donné une skill voyageuse, donc l'exclusion est
#          RETIRÉE — la vraie liste est vide, et les gardes anti-no-op /
#          exclusion-morte sont désormais exercées par des témoins SYNTHÉTIQUES.
#   §3b pointeurs `.github/skills/` (10, littéral)
#       -> SUPPRIMÉE et REMPLACÉE PAR SON INVERSE. Nous refusons de créer ces
#          pointeurs : Copilot lit DÉJÀ `.agents/skills/` nativement, donc leur
#          valeur est nulle et leur risque — une précédence indocumentée entre
#          les trois répertoires — ne l'est pas. La section assertée est donc :
#          AUCUN HOMONYME NEUF entre les trois répertoires que Copilot lit.
#          Le mutant `r4c` fait passer son unique homonyme PAR `.github/skills` —
#          témoin re-semé, celui de cette forme ayant disparu au renommage
#          `9694012` — pour que retirer ce répertoire de `REPERTOIRES_COPILOT`
#          rougisse au lieu de rendre la garde muette.
#   §3c comptes croisés de commandes (11 / 10 / 10, littéraux)
#       -> RE-DÉRIVÉ : la ligne `Commands:` de CLAUDE.md doit énumérer
#          EXACTEMENT les fichiers de `.claude/commands/`. Une doctrine qui
#          énumère est une doctrine qui périme (L-00000187) ; ici elle est
#          confrontée à la surface qu'elle prétend décrire.
#   §4  pointeurs de skills Claude (5 noms en dur)
#       -> RE-DÉRIVÉ ET ÉLARGI à la FORME : AGENTS.md documente deux fautes qui
#          cachent une skill EN SILENCE — `SKILL.md` sous la profondeur 1, et un
#          frontmatter qui n'ouvre pas en ligne 1. Ce banc les asserte sur les
#          trois répertoires. `vendor/` est exclu AVEC sa raison et sa garde
#          anti-no-op.
#   §4-bis `name:` == nom du RÉPERTOIRE (section NEUVE, sans original)
#       -> AJOUTÉE : le renommage `<n>` -> `<n>-pointer` (T-00000371) devait
#          suffixer LES DEUX — le répertoire ET le `name:` du frontmatter — et
#          rien ne l'épinglait. Bornée aux `.claude/skills/*-pointer/` : ni
#          `.agents/skills/<n>/` ni `.github/skills/` (L-00000187).
#   §5  références de comptage périmées (liste NOIRE de nombres morts)
#       -> RÉ-ANCRÉ, et inversé : une liste noire ne connaît que les erreurs
#          d'hier. Ici toute phrase de comptage de rôle doit porter le cardinal
#          DÉRIVÉ du roster. Elle ne peut donc plus périmer.
#   §5b présence de `/mode` dans les docs pilote
#       -> SUPPRIMÉE : la commande est refusée (§1 du plan), la section serait
#          rouge par construction. REMPLACÉE par la propriété que le §5 ne couvre
#          pas : les TABLEAUX d'agents des README énumèrent tout le roster. Une
#          phrase juste au-dessus d'un tableau incomplet reste un mensonge.
#   §6  lignes de TOKEN_BUDGETS.md (25, littéral)
#       -> RE-DÉRIVÉ : le barème doit porter une ligne par agent du roster, NOM
#          par NOM. Le compte seul laisserait passer un renommage.
#   §7  déclaration read-only du communicator
#       -> REPRIS, mais sur les hôtes DÉCOUVERTS et non sur trois chemins en dur
#          (l'original omet `.claude/`, qui est justement l'hôte de référence).
#
# ---------------------------------------------------------------------
# DISCIPLINE : CHAQUE GARDE EST MUTÉE
# ---------------------------------------------------------------------
# Un banc qui n'asserte que sur l'arbre réel est vert le jour où sa propre
# logique est cassée. Chaque comparateur est donc une FONCTION, appelée deux
# fois : sur `$ROOT` (le contrat), et sur des arbres SYNTHÉTIQUES où l'on sème
# exactement la faute qu'elle doit voir (le témoin). Les arms « témoin » et
# « mutation » sont cela ; sans eux le vert ne prouve rien.
# =====================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
ok() { echo "  PASS  $1"; pass=$((pass + 1)); }
ko() { echo "  FAIL  $1"; fail=$((fail + 1)); }

# Un fichier de lignes contient-il EXACTEMENT cette ligne ?
# `grep -qxF <motif> <fichier>` — jamais `printf | grep -q`, qui ferme son
# entrée et rend un statut non nul sous `pipefail` alors même que la
# correspondance est trouvée (T-00000544).
ligne_presente() { grep -qxF -- "$2" "$1" 2>/dev/null; }

# Nombre de lignes non vides d'un fichier (0 si absent, 0 si vide).
# `grep -c` IMPRIME « 0 » ET REND 1 quand rien ne correspond : un
# `grep -c … || printf 0` naïf imprime donc « 0\n0 », que `[ … -eq … ]` refuse.
# La substitution capture d'abord, le repli ne joue que sur la capture vide.
nb_lignes() {
  local n
  n="$(grep -c . "$1" 2>/dev/null)"
  [ -n "$n" ] || n=0
  printf '%s' "$n"
}

vide() { [ "$(nb_lignes "$1")" -eq 0 ]; }

# Un relevé d'écarts VIDE vaut PASS ; sinon FAIL et les écarts s'impriment.
juge() {
  local fichier="$1" libelle="$2"
  if vide "$fichier"; then
    ok "$libelle"
  else
    ko "$libelle"
    sed 's/^/          /' "$fichier"
  fi
}

# Inverse : le relevé DOIT contenir au moins un écart (arm de mutation).
juge_mord() {
  local fichier="$1" libelle="$2"
  if vide "$fichier"; then
    ko "$libelle — la garde est RESTÉE MUETTE sur une faute semée : elle ne mord pas"
  else
    ok "$libelle"
  fi
}

# =====================================================================
# SURFACES DÉRIVÉES — aucune liste close, aucun compte écrit
# =====================================================================

# Répertoires d'agents des hôtes, DÉCOUVERTS par glob `<racine>/.*/agents`.
# `.` et `..` sont écartés nommément : le glob `.*` les produit, et
# `<racine>/../agents` désignerait un arbre voisin.
hotes_agents() {
  local racine="$1" d
  for d in "$racine"/.*/agents; do
    case "$d" in
      "$racine"/./agents|"$racine"/../agents) continue ;;
    esac
    [ -d "$d" ] || continue
    printf '%s\n' "$d"
  done | LC_ALL=C sort
}

# Nom d'agent = base du fichier, débarrassée du suffixe de l'hôte.
# `.agent.md` (Copilot) AVANT `.md`, sinon il resterait un `.agent` résiduel.
#
# TOUT EN EXPANSION DE PARAMÈTRES, AUCUN `basename`/`sed`. Ce n'est pas de la
# coquetterie : ce banc dérive 4 × 26 noms d'agents plus une centaine de noms de
# skills, et sous Git-Bash un `fork` coûte ~100 ms. La première écriture, à deux
# sous-processus par nom, dépassait les deux minutes de mur et se serait fait
# tuer en porte. À zéro sous-processus elle tient en quelques secondes.
nom_agent() {
  local base="${1##*/}"
  case "$base" in
    *.agent.md) printf '%s\n' "${base%.agent.md}" ;;
    *.toml)     printf '%s\n' "${base%.toml}" ;;
    *.md)       printf '%s\n' "${base%.md}" ;;
    *)          printf '%s\n' "$base" ;;
  esac
}

roster() {
  local d="$1" f
  for f in "$d"/*; do
    [ -f "$f" ] || continue
    nom_agent "$f"
  done | LC_ALL=C sort
}

# Noms de skills à PROFONDEUR 1 (règle de comptage de AGENTS.md) : un
# répertoire ne compte que s'il porte lui-même un `SKILL.md`.
skills_profondeur1() {
  local d="$1" p parent
  [ -d "$d" ] || return 0
  for p in "$d"/*/SKILL.md; do
    [ -f "$p" ] || continue
    parent="${p%/SKILL.md}"
    printf '%s\n' "${parent##*/}"
  done | LC_ALL=C sort
}

# TOUS les répertoires à profondeur 1, `SKILL.md` ou pas — c'est la population
# sur laquelle la FORME se vérifie (§4).
repertoires_skills() {
  local d="$1" p nu
  [ -d "$d" ] || return 0
  for p in "$d"/*/; do
    [ -d "$p" ] || continue
    nu="${p%/}"
    printf '%s\n' "${nu##*/}"
  done | LC_ALL=C sort
}

commandes() {
  local d="$1/.claude/commands" f base
  [ -d "$d" ] || return 0
  for f in "$d"/*.md; do
    [ -f "$f" ] || continue
    base="${f##*/}"
    printf '%s\n' "${base%.md}"
  done | LC_ALL=C sort
}

# Les commandes que la DOCTRINE énumère (CLAUDE.md, ligne `Commands:`).
#
# DEUX BORNES, et les deux ont été posées après une fausse capture MESURÉE :
#  1. L'ÉNUMÉRATION S'ARRÊTE À LA PREMIÈRE PARENTHÈSE. La suite de la ligne est
#     de la prose — « A `$name` workflow in shared docs maps to `/name` here » —
#     et `/name` s'y lit exactement comme une commande. Le premier run de ce banc
#     a signalé « COMMANDE CITEE MAIS ABSENTE: /name » : un faux positif qui
#     aurait forcé une exception nominative si la borne n'était pas structurelle.
#  2. Seules les formes CLOSES par un backtick comptent : la ligne porte aussi
#     `/audit [-global]` et `.claude/commands/`, qu'un motif ancré sur la seule
#     barre oblique ramasserait à tort.
commandes_doctrine() {
  local f="$1/CLAUDE.md" ligne
  [ -f "$f" ] || return 0
  ligne="$(grep -m1 -E '^- Commands:' "$f")" || return 0
  # `(` sort du motif littéral : tree-sitter-bash ne parse pas `${x%% (*}`, et
  # le fichier ENTIER sortirait du compte des cibles inspectées par le SAST.
  _par=' ('
  ligne="${ligne%%$_par*}"
  printf '%s\n' "$ligne" \
    | grep -oE '`/[a-z0-9][a-z0-9-]*`' \
    | tr -d '`/' | LC_ALL=C sort -u
}

# Les trois répertoires que GitHub Copilot lit (AGENTS.md § Cross-agent
# surfaces — mesuré, pas supposé).
REPERTOIRES_COPILOT=".github/skills .claude/skills .agents/skills"

homonymes_copilot() {
  local racine="$1" d tmp
  tmp="$(mktemp)"
  for d in $REPERTOIRES_COPILOT; do
    skills_profondeur1 "$racine/$d" >> "$tmp"
  done
  LC_ALL=C sort "$tmp" | uniq -d
  rm -f "$tmp"
}

# Lignes de données du barème, NOM par nom. La cellule d'en-tête vaut
# littéralement `agent` ; aucun agent ne porte ce nom, elle est écartée ici.
noms_bareme() {
  local f="$1/.agents/ref/TOKEN_BUDGETS.md"
  [ -f "$f" ] || return 0
  grep -E '^\| [a-z][a-z0-9-]* +\|' "$f" \
    | sed -E 's/^\| *([a-z][a-z0-9-]*) *\|.*/\1/' \
    | grep -vx 'agent' | LC_ALL=C sort -u
}

# Noms cités dans le TABLEAU d'agents d'un README (bloc d'en-tête
# `| Agent | Model | Effort | Role |` jusqu'à la première ligne hors tableau).
noms_tableau_agents() {
  local f="$1"
  [ -f "$f" ] || return 0
  awk '
    /^\| *Agent *\| *Model *\| *Effort *\| *Role *\|/ { dedans=1; next }
    dedans && $0 !~ /^\|/ { dedans=0 }
    dedans { print }
  ' "$f" | grep -oE '`[a-z][a-z0-9-]*`' | tr -d '`' | LC_ALL=C sort -u
}

# =====================================================================
# COMPARATEURS — une seule implémentation, appelée sur l'arbre réel ET sur des
# arbres synthétiques mutés. Chacun rend UNE LIGNE PAR ÉCART ; silence = OK.
# =====================================================================

ecarts_roster() {
  local racine="$1" tmp ref d n refn
  tmp="$(mktemp -d)"
  hotes_agents "$racine" > "$tmp/hotes"
  if [ "$(nb_lignes "$tmp/hotes")" -lt 2 ]; then
    printf 'VACUITE: %s repertoire(s) d hote decouvert(s) — une parite en exige au moins 2\n' \
      "$(nb_lignes "$tmp/hotes")"
    rm -rf "$tmp"; return 0
  fi
  ref="$(head -1 "$tmp/hotes")"
  roster "$ref" > "$tmp/ref.names"
  refn="$(nb_lignes "$tmp/ref.names")"
  if [ "$refn" -eq 0 ]; then
    printf 'VACUITE: l hote de reference %s ne porte aucun agent\n' "$ref"
    rm -rf "$tmp"; return 0
  fi
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    roster "$d" > "$tmp/cur.names"
    n="$(nb_lignes "$tmp/cur.names")"
    [ "$n" -eq "$refn" ] || \
      printf 'CARDINAL: %s porte %s defs, %s en porte %s\n' "$d" "$n" "$ref" "$refn"
    if ! diff -q "$tmp/ref.names" "$tmp/cur.names" >/dev/null 2>&1; then
      printf 'NOMS: %s diverge de %s\n' "$d" "$ref"
      comm -23 "$tmp/ref.names" "$tmp/cur.names" | sed "s|^|  seulement dans $ref: |"
      comm -13 "$tmp/ref.names" "$tmp/cur.names" | sed "s|^|  seulement dans $d: |"
    fi
  done < "$tmp/hotes"
  rm -rf "$tmp"
}

# LISTE VIDE PAR ÉTAT DU DÉPÔT, pas par oubli. `dash` fut la seule exclusion :
# commande d'observabilité longtemps SANS skill par conception (`/dash` ouvre le
# tableau de bord local, aucune procédure à porter chez les autres hôtes).
# T-00000544 lui a donné une skill voyageuse (`.agents/skills/dash/SKILL.md`) —
# l'exclusion est donc RETIRÉE. La garde anti-no-op (`EXCLUSION NO-OP`) et la
# garde « exclusion morte » (`EXCLUSION MORTE`) de `ecarts_commande_skill`
# restent ACTIVES et reprendront leur office dès qu'une exclusion sera
# réintroduite ; les témoins du §3 les exercent aujourd'hui sur une exclusion
# SYNTHÉTIQUE passée en argument, la vraie liste étant vide.
COMMANDES_SANS_SKILL=""

# L'exclusion est un ARGUMENT ($2), non plus la globale directement : l'arm réel
# passe `$COMMANDES_SANS_SKILL` (vide), les témoins passent une exclusion
# SYNTHÉTIQUE. Ainsi les trois mécanismes restent exercés quand la vraie est vide.
ecarts_commande_skill() {
  local racine="$1" excl="$2" tmp c
  tmp="$(mktemp -d)"
  commandes "$racine" > "$tmp/cmds"
  if vide "$tmp/cmds"; then
    printf 'VACUITE: aucune commande decouverte sous %s/.claude/commands\n' "$racine"
    rm -rf "$tmp"; return 0
  fi
  for c in $excl; do
    ligne_presente "$tmp/cmds" "$c" || \
      printf 'EXCLUSION MORTE: « %s » est exclue mais n est pas une commande\n' "$c"
    [ -f "$racine/.agents/skills/$c/SKILL.md" ] && \
      printf 'EXCLUSION NO-OP: « %s » a desormais une skill homonyme — retirer l exclusion\n' "$c"
  done
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    case " $excl " in
      *" $c "*) continue ;;
    esac
    [ -f "$racine/.agents/skills/$c/SKILL.md" ] || \
      printf 'SANS SKILL: la commande /%s n a pas de .agents/skills/%s/SKILL.md\n' "$c" "$c"
  done < "$tmp/cmds"
  rm -rf "$tmp"
}

# Les homonymes CONNUS entre les trois répertoires que Copilot lit. Ce n'est pas
# un compte : c'est le registre d'un défaut. T-00000371 est CLOS — les cinq skills
# en collision ont été renommées `<n>-pointer/` sous `.claude/skills/`, distinctes
# des `<n>` de `.agents/skills/`, donc le registre est VIDE. L'égalité reste exigée
# DANS LES DEUX SENS : tout homonyme de RÉPERTOIRE neuf rougit, et un homonyme
# résolu rougirait aussi, pour qu'une régression vienne mettre ce registre à jour
# au lieu de le laisser mentir.
HOMONYMES_CONNUS=""

ecarts_homonymes() {
  local racine="$1" tmp
  tmp="$(mktemp -d)"
  homonymes_copilot "$racine" > "$tmp/vus"
  printf '%s\n' "$HOMONYMES_CONNUS" | grep . | LC_ALL=C sort > "$tmp/connus"
  comm -13 "$tmp/connus" "$tmp/vus" | sed 's/^/HOMONYME NEUF: /'
  comm -23 "$tmp/connus" "$tmp/vus" | sed 's/^/HOMONYME DISPARU (registre a mettre a jour): /'
  rm -rf "$tmp"
}

# L'index de skills de AGENTS.md : sa PHRASE DE COMPTAGE et sa LISTE, toutes
# deux confrontées à la surface avec LA RÈGLE DE COMPTAGE DE LA DOCTRINE —
# `SKILL.md` à PROFONDEUR 1. Un `ls` de répertoires compterait `vendor/` et
# donnerait un de plus : c'est exactement l'erreur qui avait failli remplacer un
# compte VRAI par un faux dans une surface qui voyage chez chaque adoptant.
#
# La phrase ET la liste, pas l'une ou l'autre : un nombre juste au-dessus d'une
# liste incomplète est un mensonge d'un autre genre, et c'est la même faute que
# le §5b traite sur les tableaux d'agents.
noms_index_skills() {
  local f="$1/AGENTS.md"
  [ -f "$f" ] || return 0
  awk '
    /^[0-9]+ skills, profondeur 1/ { dedans=1; next }
    dedans && $0 !~ /^- `/ { if (vus) dedans=0 }
    dedans && /^- `/ { vus=1; print }
  ' "$f" | grep -oE '^- `[a-z][a-z0-9-]*`' | tr -d '`' | sed 's/^- //' | LC_ALL=C sort -u
}

compte_index_skills() {
  local f="$1/AGENTS.md"
  [ -f "$f" ] || return 0
  grep -oE '^[0-9]+ skills, profondeur 1' "$f" | grep -oE '^[0-9]+' | head -1
}

ecarts_index_skills() {
  local racine="$1" tmp annonce reel
  tmp="$(mktemp -d)"
  skills_profondeur1 "$racine/.agents/skills" > "$tmp/reels"
  noms_index_skills "$racine"                 > "$tmp/cites"
  reel="$(nb_lignes "$tmp/reels")"
  annonce="$(compte_index_skills "$racine")"
  if [ "$reel" -eq 0 ]; then
    printf 'VACUITE: aucune skill a profondeur 1 sous .agents/skills\n'
    rm -rf "$tmp"; return 0
  fi
  if [ -z "$annonce" ]; then
    printf 'PHRASE DE COMPTAGE ABSENTE de AGENTS.md — plus rien ne peut perimer, ni etre verifie\n'
  elif [ "$annonce" != "$reel" ]; then
    printf 'INDEX DE SKILLS: AGENTS.md annonce %s skills, la surface en porte %s (SKILL.md a profondeur 1)\n' \
      "$annonce" "$reel"
  fi
  comm -23 "$tmp/reels" "$tmp/cites" | sed 's/^/SKILL NON CITEE par l index de AGENTS.md: /'
  comm -13 "$tmp/reels" "$tmp/cites" | sed 's/^/SKILL CITEE MAIS ABSENTE de .agents\/skills: /'
  rm -rf "$tmp"
}

ecarts_doctrine_commandes() {
  local racine="$1" tmp
  tmp="$(mktemp -d)"
  commandes "$racine"          > "$tmp/reelles"
  commandes_doctrine "$racine" > "$tmp/citees"
  if vide "$tmp/reelles"; then
    printf 'VACUITE: aucune commande decouverte, la comparaison ne prouve rien\n'
    rm -rf "$tmp"; return 0
  fi
  comm -23 "$tmp/reelles" "$tmp/citees" | sed 's|^|COMMANDE NON CITEE par CLAUDE.md § Commands: /|'
  comm -13 "$tmp/reelles" "$tmp/citees" | sed 's|^|COMMANDE CITEE MAIS ABSENTE de .claude/commands/: /|'
  rm -rf "$tmp"
}

# `vendor` — sous-répertoire de `.agents/skills/` qui NE PORTE PAS de `SKILL.md`
# à profondeur 1, PAR CONCEPTION : il héberge des skills tierces à profondeur 2,
# invisibles à la découverte, et AGENTS.md le documente explicitement. Exclusion
# nommée, avec sa garde anti-no-op.
SKILLS_SANS_SKILLMD=".agents/skills/vendor"

ecarts_forme_skills() {
  local racine="$1" d n chemin premiere vus=0
  for d in $REPERTOIRES_COPILOT; do
    [ -d "$racine/$d" ] || continue
    while IFS= read -r n; do
      [ -n "$n" ] || continue
      vus=$((vus + 1))
      chemin="$racine/$d/$n/SKILL.md"
      case " $SKILLS_SANS_SKILLMD " in
        *" $d/$n "*)
          [ -f "$chemin" ] && \
            printf 'EXCLUSION NO-OP: %s/%s porte maintenant un SKILL.md — retirer l exclusion\n' "$d" "$n"
          continue ;;
      esac
      if [ ! -f "$chemin" ]; then
        printf 'FORME: %s/%s/ n a pas de SKILL.md a profondeur 1 — skill INVISIBLE, sans erreur\n' "$d" "$n"
        continue
      fi
      # `read` builtin plutôt que `head -1 | tr` : deux forks par skill, sur une
      # centaine de skills, pour lire un seul octet utile.
      IFS= read -r premiere < "$chemin" || premiere=""
      premiere="${premiere%$'\r'}"
      [ "$premiere" = "---" ] || \
        printf 'FORME: %s/%s/SKILL.md n ouvre pas son frontmatter en ligne 1 — skill INVISIBLE, sans erreur\n' "$d" "$n"
    done < <(repertoires_skills "$racine/$d")
  done
  [ "$vus" -eq 0 ] && printf 'VACUITE: aucun repertoire de skill balaye\n'
  return 0
}

# §4-bis — le `name:` du frontmatter doit ÉGALER le nom du répertoire, sur les
# répertoires-pointeurs de `.claude/skills/`.
#
# CE QUE ÇA FERME. Le renommage `<n>` -> `<n>-pointer` (T-00000371) fermait une
# collision de noms entre les trois répertoires que Copilot lit. Il devait
# suffixer LES DEUX faces : le répertoire ET le `name:`. Rien ne l'épinglait —
# un `name:` resté nu re-crée la collision par le champ, alors que les NOMS DE
# RÉPERTOIRE, eux, restent bien distincts : aucune autre section ne peut le voir.
# La clé de découverte de Claude Code est le RÉPERTOIRE (mesuré) ; celle de
# Copilot ne l'est PAS — d'où l'exigence sur les deux faces plutôt qu'un pari.
#
# FONCTION À PART, et non greffe dans `ecarts_forme_skills` : y greffer la
# propriété l'élargirait aux dizaines de skills des trois répertoires, dont rien
# n'exige aujourd'hui que le `name:` égale le répertoire — un rouge à la
# livraison — et brouillerait les deux mutants de forme de cette section.
#
# UN `SKILL.md` ABSENT EST IGNORÉ ICI : c'est la faute du §4, qui la nomme déjà.
# Deux sections rougissant sur un même défaut donnent deux dettes pour une.
ecarts_nom_pointeurs() {
  local racine="$1" p nu n chemin ligne valeur dans vus=0
  for p in "$racine"/.claude/skills/*-pointer/; do
    [ -d "$p" ] || continue
    nu="${p%/}"; n="${nu##*/}"
    vus=$((vus + 1))
    chemin="$nu/SKILL.md"
    [ -f "$chemin" ] || continue
    # Valeur = la première ligne `name:` DANS le frontmatter (ligne 1 `---`
    # jusqu'au `---` suivant) ; absente ou hors frontmatter = vide, donc
    # signalée. `read` builtin, zéro fork — même raison qu'au §4.
    valeur=""; dans=0
    while IFS= read -r ligne || [ -n "$ligne" ]; do
      ligne="${ligne%$'\r'}"
      if [ "$dans" -eq 0 ]; then
        [ "$ligne" = "---" ] || break
        dans=1; continue
      fi
      [ "$ligne" = "---" ] && break
      case "$ligne" in
        name:*)
          valeur="${ligne#name:}"
          valeur="${valeur#"${valeur%%[![:space:]]*}"}"
          valeur="${valeur%"${valeur##*[![:space:]]}"}"
          break ;;
      esac
    done < "$chemin"
    [ "$valeur" = "$n" ] || \
      printf "NOM: .claude/skills/%s/SKILL.md porte name: '%s' — attendu '%s'\n" \
        "$n" "$valeur" "$n"
  done
  [ "$vus" -eq 0 ] && printf 'VACUITE: aucun repertoire-pointeur sous .claude/skills\n'
  return 0
}

# Une phrase de comptage de ROSTER : un nombre suivi IMMÉDIATEMENT du nom du
# rôle, éventuellement qualifié par « specialized » ou « role-scoped ».
# Les autres populations ne portent pas cette forme et ne sont donc pas visées :
# « 8 dedicated agents » et « 17 core + 8 security » intercalent un qualifiant,
# « Eight agents manage the security gate » n'a pas de chiffre. C'est ce qui
# permet de comparer au cardinal du roster sans liste d'exceptions à tenir.
MOTIF_COMPTAGE='[0-9]+ (specialized |role-scoped )?(agents|subagents)'

# QUALIFIANTS POSTPOSÉS — T-00000567, appliqué le 2026-09-13 avec ses témoins.
# `MOTIF_COMPTAGE` échappe aux populations qualifiées, mais son échappement est
# ANGLAIS et PRÉFIXÉ (« 8 dedicated agents ») : le français POSTPOSE son
# qualifiant, donc « 26 agents pilotés » et « 8 agents de sécurité » étaient lus
# comme des cardinaux de roster et rougissaient à tort. Les deux témoins sont
# réels et mesurés : `.agents/ref/MODEL_MODES.md` § 3.3 (26 = les agents pilotés
# par le levier sur codex, `EXPECTED_TOUCHED["codex"]`) et `CADRE/index.html:244`
# (8 = les agents de sécurité).
#
# C'EST UNE LISTE BORNÉE, PAS UNE RÈGLE UNIVERSELLE, et le dire fait partie du
# correctif : aucun motif ne sait distinguer linguistiquement une population
# qualifiée d'un cardinal nu. Un qualifiant absent de cette liste produira un
# ROUGE — bruyant, avec la ligne fautive nommée, donc réparable en l'ajoutant
# ici. C'est l'échec dans le bon sens : jamais un vrai comptage périmé qui passe.
QUALIFIANTS_POSTPOSES=' (de sécurité|de securite|pilotés|pilotes|dédiés|dedies)'

# Docs balayées : tout `*.md` à la racine (GLOB — un README neuf est couvert
# sans revenir ici), plus les deux surfaces hors racine qui portent la doctrine
# et le manuel.
docs_balayees() {
  local racine="$1" f
  for f in "$racine"/*.md; do
    [ -f "$f" ] && printf '%s\n' "$f"
  done
  [ -f "$racine/.github/copilot-instructions.md" ] && printf '%s\n' "$racine/.github/copilot-instructions.md"
  # SURFACES DE DOCTRINE AJOUTÉES le 2026-09-13 (T-00000565) : elles PORTENT le
  # cardinal sans être balayées. Le relevé de la dette nommait sept surfaces, ce
  # balayage n'en couvrait que quatre — d'où des écarts découverts UN PAR UN sur
  # cinq passes de porte, alors que la fonction les liste pourtant tous d'un coup.
  #
  # UNE PREMIÈRE RÉDACTION AJOUTAIT `CADRE/architecture.html` ET
  # `docs/interne/classification.md` : élargissement NUL, mesuré. Le motif ne mord
  # sur AUCUNE ligne de ces deux fichiers — `architecture.html` porte le cardinal
  # en tuile et en « N rôles », `classification.md` en COLONNE de tableau (`| 29 |`),
  # que le motif de prose ne voit pas. Les témoins passaient sur des formes
  # SYNTHÉTIQUES que les vrais fichiers n'ont pas : une couverture crue, jamais
  # mesurée. Le fichier que la dette nommait est `CADRE/index.html`, et lui porte
  # bien quatre occurrences.
  # `MODEL_MODES.md` ENTRE ICI le 2026-09-13, et il ne le pouvait pas avant :
  # son § 3.3 dit « 26 agents pilotés », que l'ancien motif lisait comme un
  # cardinal de roster périmé. C'est l'échappement des qualifiants POSTPOSÉS
  # (T-00000567) qui le rend balayable — les deux tâches n'en faisaient qu'une.
  #
  # DEUX AUTRES FICHIERS ONT ÉTÉ AJOUTÉS PUIS RETIRÉS le même jour, et les deux
  # retraits sont des mesures, pas des renoncements. `CADRE/architecture.html` et
  # `docs/interne/classification.md` : couverture NULLE — le motif ne mord sur
  # aucune de leurs lignes (l'un porte le cardinal en tuile et en « N rôles », que juge
  # `test_roster_cardinal.py`, kit seul, plancher de surface ; l'autre en COLONNE). `CADRE/index.html` :
  # déjà couvert par `core-scripts/cadre.test.sh`, qui dérive le compte du disque
  # et porte son assertion négative — l'ajouter ici DUPLIQUAIT la couverture et,
  # pire, faisait référencer un préfixe `strip:` (`.template-exclude:74`) depuis
  # un banc qui VOYAGE : §5 s'y serait rétréci chez l'adoptant sans l'annoncer.
  [ -f "$racine/.agents/ref/MODEL_MODES.md" ] && printf '%s\n' "$racine/.agents/ref/MODEL_MODES.md"
  # POURQUOI UNE LISTE ET NON UN BALAYAGE DE L'ARBRE — relevé du 2026-09-13, et
  # la réponse tient en TROIS catégories, pas une. Hors population, 27 fichiers
  # suivis portent le motif avec un nombre != 29 :
  #   (1) 22 RAPPELS HISTORIQUES légitimes — les trois stores d'état, 16
  #       `docs/tasks/*`, 2 `docs/design/*` — qu'un balayage large ferait rougir
  #       à tort : un rappel n'est pas une affirmation périmée ;
  #   (2) 2 POPULATIONS QUALIFIÉES, justes, que l'échappement postposé écarte ;
  #   (3) 2 SURFACES VIVANTES ET PÉRIMÉES, qui ne sont NI l'un NI l'autre.
  # La première rédaction de ce commentaire fondait les trois en une seule et
  # concluait « les journaux citent d'anciens cardinaux » : elle PROTÉGEAIT ainsi
  # deux affirmations fausses en les décrivant comme de l'histoire. Les deux ont
  # été corrigées le 2026-09-13 (`docs/usage.html`, 4 occurrences, page qui VOYAGE
  # chez l'adoptant ; `contract.lock.json`).
  # ET LA BORNE N'EST PAS « PAS D'HISTORIQUE » : `PLAN-ETAT.md` entre par le glob
  # racine et il porte des rappels datés, sans être pour autant une surface de
  # doctrine. C'est une liste de SURFACES DE DOCTRINE, et c'est elle qu'il faut
  # tenir à jour — pas le cardinal.
  # `docs/usage.html` RETIRÉ du balayage le 2026-09-09, décision du pilote :
  # page de présentation pour les adoptants, pas une surface de doctrine. Elle
  # VOYAGE toujours vers eux — c'est `test_sync_template.py` qui le garantit, en
  # exigeant qu'elle sorte en FROZEN/OWN et jamais en DELETE. Ce qui change ici,
  # c'est seulement qu'un compteur périmé dans la page ne rougit plus la porte.
  # NE PAS REMETTRE sans arbitrage du pilote.
  return 0
}

# Rend une ligne par phrase de comptage DIVERGENTE, et une ligne `VACUITE:` si
# le balayage n'a trouvé aucune phrase de comptage du tout — sans quoi la
# section serait verte sur un corpus muet.
ecarts_comptage() {
  local racine="$1" attendu="$2" f tmp hit n
  tmp="$(mktemp -d)"
  : > "$tmp/trouvees"
  docs_balayees "$racine" > "$tmp/docs"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    # On capture le comptage AVEC son éventuel qualifiant postposé, puis on
    # retire les lignes qui en portent un : sans cette seconde passe, « 8 agents
    # de sécurité » serait tronqué à « 8 agents » et compté comme un cardinal.
    grep -nEio "$MOTIF_COMPTAGE($QUALIFIANTS_POSTPOSES)?" "$f" 2>/dev/null \
      | grep -viE "$QUALIFIANTS_POSTPOSES$" > "$tmp/hits" || true
    while IFS= read -r hit; do
      [ -n "$hit" ] || continue
      echo x >> "$tmp/trouvees"
      n="$(printf '%s' "${hit#*:}" | sed -E 's/^([0-9]+).*/\1/')"
      [ "$n" = "$attendu" ] || \
        printf 'COMPTAGE PERIME: %s:%s — « %s », le roster en compte %s\n' \
          "${f#"$racine"/}" "${hit%%:*}" "${hit#*:}" "$attendu"
    done < "$tmp/hits"
  done < "$tmp/docs"
  [ "$(nb_lignes "$tmp/trouvees")" -eq 0 ] && \
    printf 'VACUITE: aucune phrase de comptage trouvee — le motif ne mord sur rien\n'
  rm -rf "$tmp"
  return 0
}

# LA VACUITÉ GLOBALE NE VOIT PAS UNE SURFACE QUI SE TAIT (T-00000580).
#
# LE DÉFAUT, mesuré le 2026-09-13. `ecarts_comptage` ne signale la vacuité que
# si le corpus ENTIER ne rend AUCUNE phrase. Or cinq fichiers la saturent : une
# surface NOMMÉE peut donc cesser de porter le cardinal — reformulation, coupe,
# déplacement — sans que rien ne rougisse. Scénario : on reformule un README, on
# laisse `AGENTS.md` dériver, le filet reste VERT. Un total qui ne descend jamais
# à zéro est un total qui ne prouve rien sur ses membres.
#
# CE QUE LE RELEVÉ A MONTRÉ, et qui a décidé de la forme : `AGENTS.md` PORTE le
# cardinal — « le roster reste à 29 », « zéro déf sur 29 » — mais dans des formes
# que le motif ne voit pas, faute du mot qui suit le nombre. Il a donc été
# REFORMULÉ plutôt qu'exempté : mettre la surface la plus lue SOUS le filet vaut
# mieux que de l'inscrire à côté. `.github/copilot-instructions.md`, lui,
# n'énonce aucun cardinal de roster : il est dans la population pour une autre
# raison, et c'est une exemption NOMMÉE, jamais un trou.
SURFACES_COMPTAGE="README.md README-CLAUDE.md README-OTHER-HOSTS.md QUICK-SETUP.md AGENTS.md .agents/ref/MODEL_MODES.md"
# EXEMPTIONS NOMMÉES, chacune avec sa raison — une exemption muette serait le
# trou que ce contrôle existe pour fermer.
#   .github/copilot-instructions.md — n'énonce aucun cardinal de roster ; il est
#     balayé comme surface de doctrine Copilot, pas comme porteur du compte.
EXEMPTES_COMPTAGE=".github/copilot-instructions.md"

# LE README RACINE N'EST PORTEUR QUE DANS LE KIT (`.agents/IS_THE_KIT`). Chez
# l'adoptant, README.md est le guide de SON projet : il ne porte ni cardinal ni
# tableau d'agents, et ne doit pas en porter — modèles et efforts y sont renvoyés
# à README-CLAUDE.md, qui reste jugé sur les deux arbres. Capacité perdue hors
# kit, NOMMÉE : un tableau ou un cardinal ajouté au README adoptant n'est plus
# exigé par §5-surfaces ni par §5b ; une phrase de comptage qu'il porterait reste
# jugée par §5 (glob des `*.md` racine).
readme_porteur() {
  [ -f "$1/.agents/IS_THE_KIT" ]
}

ecarts_comptage_par_surface() {
  local racine="$1" f n e exempte
  for f in $SURFACES_COMPTAGE; do
    # L EXEMPTION ETAIT DECORATIVE, et c est le binome qui l a mesure :
    # `EXEMPTES_COMPTAGE` etait DEFINIE et JAMAIS LUE — `git grep` n en rendait
    # qu une occurrence, sa propre definition. L exemption ne tenait que par
    # l ABSENCE de la surface dans `SURFACES_COMPTAGE`, donc quiconque l y
    # ajoutait en croyant l exemption active obtenait un `SURFACE MUETTE`
    # permanent, sur le cas EXACT pour lequel elle avait ete nommee. Et le motif
    # de cloture de T-00000580 annoncait « des exemptions NOMMEES » : la moitie
    # annoncee n existait pas. Une exemption qui n est pas APPLIQUEE ne doit pas
    # avoir la forme d un mecanisme.
    exempte=0
    for e in $EXEMPTES_COMPTAGE; do
      [ "$e" = "$f" ] && exempte=1
    done
    [ "$exempte" -eq 1 ] && continue
    if [ "$f" = README.md ] && ! readme_porteur "$racine"; then
      continue
    fi
    if [ ! -f "$racine/$f" ]; then
      printf 'SURFACE ABSENTE: %s est nommee comme porteuse du cardinal et n existe pas\n' "$f"
      continue
    fi
    n="$(grep -cEio "$MOTIF_COMPTAGE" "$racine/$f" 2>/dev/null || true)"
    [ -n "$n" ] || n=0
    [ "$n" -eq 0 ] && printf 'SURFACE MUETTE: %s ne rend AUCUNE phrase de comptage — reformulation ou coupe ?\n' "$f"
  done
  return 0
}

# Le roster doit être un SOUS-ENSEMBLE des noms cités dans le tableau. Un token
# en trop (un nom de fichier entre backticks) est sans conséquence ; un agent
# MANQUANT est le défaut qu'on cherche.
ecarts_tableau() {
  local racine="$1" rosterf="$2" f tmp
  tmp="$(mktemp -d)"
  for f in README.md README-CLAUDE.md; do
    [ -f "$racine/$f" ] || continue
    if [ "$f" = README.md ] && ! readme_porteur "$racine"; then
      continue
    fi
    noms_tableau_agents "$racine/$f" > "$tmp/vus"
    if vide "$tmp/vus"; then
      printf 'VACUITE: aucun tableau d agents reconnu dans %s\n' "$f"
      continue
    fi
    comm -23 "$rosterf" "$tmp/vus" | sed "s|^|AGENT ABSENT DU TABLEAU $f: |"
  done
  rm -rf "$tmp"
  return 0
}

# =====================================================================
echo "================================================================"
echo "PARITE DES SURFACES D HOTES — tous les comptes sont DERIVES"
echo "================================================================"

hotes_agents "$ROOT" > "$WORK/hotes"
HOTE_REF="$(head -1 "$WORK/hotes")"
roster "$HOTE_REF" > "$WORK/roster"
CARDINAL_ROSTER="$(nb_lignes "$WORK/roster")"
commandes "$ROOT" > "$WORK/cmds"

echo
echo "  releve : $(nb_lignes "$WORK/hotes") hotes · $CARDINAL_ROSTER agents (ref. ${HOTE_REF#"$ROOT"/})"
skills_profondeur1 "$ROOT/.agents/skills" > "$WORK/sk"
echo "           $(nb_lignes "$WORK/cmds") commandes · $(nb_lignes "$WORK/sk") skills a profondeur 1"
echo

# ---------------------------------------------------------------------
echo "=== §1+§2 — cardinal ET noms d agents, parite entre hotes decouverts"
ecarts_roster "$ROOT" > "$WORK/r1"
juge "$WORK/r1" "les hotes decouverts portent le meme roster ($CARDINAL_ROSTER agents)"

echo "=== §2-temoins — le comparateur MORD (une def retiree sur UN SEUL hote)"
FAUX="$WORK/faux_roster"
mkdir -p "$FAUX/.claude/agents" "$FAUX/.codex/agents" "$FAUX/.gemini/agents"
for n in alpha beta gamma; do
  : > "$FAUX/.claude/agents/$n.md"
  : > "$FAUX/.codex/agents/$n.toml"
  : > "$FAUX/.gemini/agents/$n.agent.md"
done
ecarts_roster "$FAUX" > "$WORK/r2a"
juge "$WORK/r2a" "temoin : trois hotes synthetiques identiques -> silence"
rm -f "$FAUX/.gemini/agents/gamma.agent.md"
ecarts_roster "$FAUX" > "$WORK/r2b"
juge_mord "$WORK/r2b" "mutation : gamma retire du SEUL hote gemini -> ecart signale (L-00000232)"

SOLO="$WORK/faux_solo"; mkdir -p "$SOLO/.claude/agents"; : > "$SOLO/.claude/agents/alpha.md"
ecarts_roster "$SOLO" > "$WORK/r2c"
juge_mord "$WORK/r2c" "un seul hote : la VACUITE est dite au lieu d etre verte"

# ---------------------------------------------------------------------
echo "=== §3 — chaque commande a sa skill homonyme (exclusions nommees + anti-no-op)"
ecarts_commande_skill "$ROOT" "$COMMANDES_SANS_SKILL" > "$WORK/r3"
juge "$WORK/r3" "commandes -> skills homonymes ; aucune exclusion declaree (liste vide)"

echo "=== §3-temoins — l exclusion (SYNTHETIQUE) ne peut ni mourir ni devenir un no-op"
# La vraie liste COMMANDES_SANS_SKILL est VIDE (T-00000544). Ces temoins exercent
# donc les trois mecanismes sur une exclusion SYNTHETIQUE, VISIBLEMENT distincte
# de la vraie et passee en 2e argument : « omega »/« sigma »/« fantome » ne sont
# PAS des commandes du depot. Chaque arm ROUGIT si son mecanisme disparait.
EXCL_TEMOIN="omega"
FCS="$WORK/faux_cmd"
mkdir -p "$FCS/.claude/commands" "$FCS/.agents/skills/omega" "$FCS/.agents/skills/sigma"
: > "$FCS/.claude/commands/omega.md"; : > "$FCS/.claude/commands/sigma.md"
: > "$FCS/.agents/skills/sigma/SKILL.md"
ecarts_commande_skill "$FCS" "$EXCL_TEMOIN" > "$WORK/r3a"
juge "$WORK/r3a" "temoin : omega exclu (sans skill) + sigma appaire -> silence"
: > "$FCS/.agents/skills/omega/SKILL.md"
ecarts_commande_skill "$FCS" "$EXCL_TEMOIN" > "$WORK/r3b"
juge_mord "$WORK/r3b" "mutation : omega gagne une skill -> l exclusion est denoncee comme NO-OP"
rm -f "$FCS/.agents/skills/omega/SKILL.md" "$FCS/.agents/skills/sigma/SKILL.md"
ecarts_commande_skill "$FCS" "$EXCL_TEMOIN" > "$WORK/r3c"
juge_mord "$WORK/r3c" "mutation : sigma perd sa skill -> commande orpheline signalee (SANS SKILL)"
# EXCLUSION MORTE : exclure « fantome », qui n est PAS une commande. omega et
# sigma reprennent une skill pour que SEUL ce mecanisme morde ici.
: > "$FCS/.agents/skills/omega/SKILL.md"; : > "$FCS/.agents/skills/sigma/SKILL.md"
ecarts_commande_skill "$FCS" "fantome" > "$WORK/r3d"
juge_mord "$WORK/r3d" "mutation : « fantome » exclu mais absent des commandes -> EXCLUSION MORTE"

echo "=== §3-etat — aucune exclusion declaree aujourd hui, la vraie liste est vide"
# Epingle l etat T-00000544 : sans cet arm, une exclusion reintroduite en douce
# (donc non re-armee par un temoin non vacueux) ne serait vue par personne.
if [ -z "$COMMANDES_SANS_SKILL" ]; then
  ok "COMMANDES_SANS_SKILL est vide : aucune commande exclue de la parite skill"
else
  ko "COMMANDES_SANS_SKILL non vide (« $COMMANDES_SANS_SKILL ») — reintroduire aussi un temoin NON VACUEUX pour chaque nom exclu"
fi

# ---------------------------------------------------------------------
echo "=== §3b (INVERSE du refus) — aucun homonyme NEUF entre les 3 repertoires que Copilot lit"
ecarts_homonymes "$ROOT" > "$WORK/r4"
juge "$WORK/r4" "homonymes observes == registre T-00000371, dans les deux sens"

echo "=== §3b-temoins — le renommage <n>-pointer resout la collision (silence), un doublon de repertoire rougit"
FH="$WORK/faux_homo"
# Temoin de silence : la realite POST-renommage T-00000371 — <n> sous .agents/skills,
# <n>-pointer sous .claude/skills : noms DISTINCTS, aucun homonyme, registre vide -> silence.
for n in composition-patterns frontend-fidelity playwright-best-practices react-best-practices web-interface-guidelines; do
  mkdir -p "$FH/.agents/skills/$n" "$FH/.claude/skills/$n-pointer"
  : > "$FH/.agents/skills/$n/SKILL.md"; : > "$FH/.claude/skills/$n-pointer/SKILL.md"
done
ecarts_homonymes "$FH" > "$WORK/r4a"
juge "$WORK/r4a" "temoin : <n> sous .agents/skills + <n>-pointer sous .claude/skills -> aucun homonyme, silence"
# Mutation : re-semer le MEME nom NU sous .claude/skills, en collision avec .agents/skills
# -> 5 homonymes NEUFS (registre vide depuis T-00000371, tout doublon de repertoire rougit).
for n in composition-patterns frontend-fidelity playwright-best-practices react-best-practices web-interface-guidelines; do
  mkdir -p "$FH/.claude/skills/$n"
  : > "$FH/.claude/skills/$n/SKILL.md"
done
ecarts_homonymes "$FH" > "$WORK/r4b"
juge_mord "$WORK/r4b" "mutation : les 5 noms nus re-semes sous .claude/skills (deja sous .agents/skills) -> 5 homonymes neufs"
# Mutation (2) : l'unique homonyme traverse `.github/skills`. ARBRE NEUF, et non
# `$FH` : les 5 homonymes de r4b y masqueraient ce témoin unique, qui serait alors
# vert pour la mauvaise raison. Ce mutant EST ce qui épingle l'appartenance de
# `.github/skills` à `REPERTOIRES_COPILOT` — sorti de cette liste, `ecarts_homonymes`
# deviendrait MUETTE ici. Le témoin de cette forme avait disparu au renommage
# `9694012` ; il est re-semé. Avec r4b (`.claude` et `.agents`), chaque répertoire
# de la liste est désormais épinglé par un mutant.
FG="$WORK/faux_homo_gh"
mkdir -p "$FG/.github/skills/kickoff" "$FG/.agents/skills/kickoff"
: > "$FG/.github/skills/kickoff/SKILL.md"; : > "$FG/.agents/skills/kickoff/SKILL.md"
ecarts_homonymes "$FG" > "$WORK/r4c"
juge_mord "$WORK/r4c" "mutation : kickoff seme sous .github/skills ET .agents/skills -> homonyme neuf"

# ---------------------------------------------------------------------
echo "=== §3c — la ligne « Commands: » de CLAUDE.md enumere EXACTEMENT .claude/commands/"
ecarts_doctrine_commandes "$ROOT" > "$WORK/r5"
juge "$WORK/r5" "doctrine == surface ($(nb_lignes "$WORK/cmds") commandes)"

echo "=== §3c-temoins — une commande omise par la doctrine rougit"
FD="$WORK/faux_doc"; mkdir -p "$FD/.claude/commands"
: > "$FD/.claude/commands/kickoff.md"; : > "$FD/.claude/commands/dash.md"
printf -- '- Commands: `/kickoff`, `/dash` (defined in `.claude/commands/`).\n' > "$FD/CLAUDE.md"
ecarts_doctrine_commandes "$FD" > "$WORK/r5a"
juge "$WORK/r5a" "temoin : doctrine complete -> silence"
printf -- '- Commands: `/kickoff` (defined in `.claude/commands/`).\n' > "$FD/CLAUDE.md"
ecarts_doctrine_commandes "$FD" > "$WORK/r5b"
juge_mord "$WORK/r5b" "mutation : /dash retire de la ligne -> commande non citee signalee"

# ---------------------------------------------------------------------
echo "=== §3c-bis — l index de skills de AGENTS.md : la PHRASE et la LISTE"
ecarts_index_skills "$ROOT" > "$WORK/r5c"
juge "$WORK/r5c" "AGENTS.md annonce et enumere les $(nb_lignes "$WORK/sk") skills a profondeur 1"

echo "=== §3c-bis-temoins — le compte se derive avec LA REGLE, pas avec un ls"
FS="$WORK/faux_skills"
mkdir -p "$FS/.agents/skills/alpha" "$FS/.agents/skills/beta" "$FS/.agents/skills/vendor/tierce"
: > "$FS/.agents/skills/alpha/SKILL.md"; : > "$FS/.agents/skills/beta/SKILL.md"
: > "$FS/.agents/skills/vendor/tierce/SKILL.md"
{ echo '2 skills, profondeur 1 sous `.agents/skills/` — `nom` · LIRE QUAND.'
  echo '- `alpha` · a'; echo '- `beta` · b'; echo; } > "$FS/AGENTS.md"
ecarts_index_skills "$FS" > "$WORK/r5d"
juge "$WORK/r5d" "temoin : 2 annonces / 2 reelles, vendor/ NON compte (SKILL.md a profondeur 2)"
{ echo '3 skills, profondeur 1 sous `.agents/skills/` — `nom` · LIRE QUAND.'
  echo '- `alpha` · a'; echo '- `beta` · b'; echo; } > "$FS/AGENTS.md"
ecarts_index_skills "$FS" > "$WORK/r5e"
juge_mord "$WORK/r5e" "mutation : « 3 skills » (le compte d un ls, vendor/ inclus) -> ecart signale"
{ echo '2 skills, profondeur 1 sous `.agents/skills/` — `nom` · LIRE QUAND.'
  echo '- `alpha` · a'; echo; } > "$FS/AGENTS.md"
ecarts_index_skills "$FS" > "$WORK/r5f"
juge_mord "$WORK/r5f" "mutation : beta retiree de la LISTE (compte encore juste) -> skill non citee"

# ---------------------------------------------------------------------
echo "=== §4 — FORME de chaque skill : SKILL.md a profondeur 1, frontmatter en ligne 1"
ecarts_forme_skills "$ROOT" > "$WORK/r6"
juge "$WORK/r6" "forme des skills des 3 repertoires ; seule exclusion : $SKILLS_SANS_SKILLMD"

echo "=== §4-temoins — les DEUX fautes silencieuses de AGENTS.md sont vues"
FF="$WORK/faux_forme"
mkdir -p "$FF/.agents/skills/bonne"
printf -- '---\nname: bonne\n---\n' > "$FF/.agents/skills/bonne/SKILL.md"
ecarts_forme_skills "$FF" > "$WORK/r6a"
juge "$WORK/r6a" "temoin : une skill bien formee -> silence"
mkdir -p "$FF/.agents/skills/profonde/vendor-x"
printf -- '---\nname: x\n---\n' > "$FF/.agents/skills/profonde/vendor-x/SKILL.md"
ecarts_forme_skills "$FF" > "$WORK/r6b"
juge_mord "$WORK/r6b" "mutation A : SKILL.md a profondeur 2 -> skill invisible, signalee"
rm -rf "$FF/.agents/skills/profonde"
mkdir -p "$FF/.agents/skills/tardive"
printf -- '\n---\nname: tardive\n---\n' > "$FF/.agents/skills/tardive/SKILL.md"
ecarts_forme_skills "$FF" > "$WORK/r6c"
juge_mord "$WORK/r6c" "mutation B : frontmatter en ligne 2 -> skill invisible, signalee"

# ---------------------------------------------------------------------
echo "=== §4-bis — le name: du frontmatter egale le nom du repertoire (pointeurs .claude)"
ecarts_nom_pointeurs "$ROOT" > "$WORK/r6d"
juge "$WORK/r6d" "chaque .claude/skills/*-pointer/ porte un name: egal a son repertoire"

echo "=== §4-bis-temoins — un name: reste nu quand le repertoire, lui, a ete renomme"
FN="$WORK/faux_nom"
mkdir -p "$FN/.claude/skills/beta-pointer"
# La forme PRE-renommage, exactement : repertoire suffixe, `name:` laisse nu.
printf -- '---\nname: beta\n---\n' > "$FN/.claude/skills/beta-pointer/SKILL.md"
ecarts_nom_pointeurs "$FN" > "$WORK/r6e"
juge_mord "$WORK/r6e" "mutation : repertoire beta-pointer mais name: beta -> ecart signale"

# ---------------------------------------------------------------------
echo "=== §5 — toute phrase de comptage de role porte le cardinal DERIVE du roster"
ecarts_comptage "$ROOT" "$CARDINAL_ROSTER" > "$WORK/r7"
juge "$WORK/r7" "phrases de comptage == $CARDINAL_ROSTER (docs racine + copilot-instructions + 2 surfaces de doctrine ; usage.html RETIRE le 2026-09-09)"

echo "=== §5-surfaces — chaque porteuse NOMMEE rend au moins une phrase (T-00000580)"
ecarts_comptage_par_surface "$ROOT" > "$WORK/r7s"
juge "$WORK/r7s" "aucune surface nommee n est MUETTE (la vacuite globale ne le voyait pas)"

echo "=== §5-surfaces-temoin — une surface muette est SIGNALEE"
# NON-VACUITÉ. Sans ce témoin, le contrôle ci-dessus serait vert sur une liste
# vide, sur un motif cassé, ou sur un `grep` qui ne trouve jamais rien — trois
# façons d'être vert sans rien prouver.
TMP_MUET="$(mktemp -d)"
mkdir -p "$TMP_MUET/.agents/ref"
for f in README.md README-CLAUDE.md README-OTHER-HOSTS.md QUICK-SETUP.md AGENTS.md; do
  printf 'le roster reste a %s agents\n' "$CARDINAL_ROSTER" > "$TMP_MUET/$f"
done
printf 'aucun cardinal ici\n' > "$TMP_MUET/.agents/ref/MODEL_MODES.md"
ecarts_comptage_par_surface "$TMP_MUET" > "$WORK/r7t"
if grep -q 'SURFACE MUETTE: .agents/ref/MODEL_MODES.md' "$WORK/r7t"; then
  ok "une surface qui cesse de porter le cardinal est NOMMEE"
else
  ko "le controle par surface ne mord pas : il serait vert sur une derive"
fi
# README.md MUET : NOMMÉ dans le kit, tu chez l'adoptant (readme_porteur).
printf 'aucun cardinal ici\n' > "$TMP_MUET/README.md"
ecarts_comptage_par_surface "$TMP_MUET" > "$WORK/r7u"
if grep -q 'SURFACE MUETTE: README.md' "$WORK/r7u"; then
  ko "adoptant : un README.md sans cardinal est exige comme porteur"
else
  ok "adoptant (sans .agents/IS_THE_KIT) : README.md n est pas une surface porteuse"
fi
mkdir -p "$TMP_MUET/.agents"; : > "$TMP_MUET/.agents/IS_THE_KIT"
ecarts_comptage_par_surface "$TMP_MUET" > "$WORK/r7v"
if grep -q 'SURFACE MUETTE: README.md' "$WORK/r7v"; then
  ok "kit (.agents/IS_THE_KIT) : un README.md muet est NOMME"
else
  ko "kit : README.md muet n est plus signale"
fi
rm -rf "$TMP_MUET"

echo "=== §5-population — .agents/ref/MODEL_MODES.md est reellement balaye"
# TÉMOIN DE L'ÉLARGISSEMENT (T-00000565). Élargir une population sans prouver
# qu'elle mord, c'est croire un filet plus large qu'il n'est — trois fichiers ont
# été ajoutés puis retirés le 2026-09-13 pour cette raison exacte.
# CE QUE CETTE ENTRÉE COUVRE, DIT SANS ENJOLIVER : `MODEL_MODES.md` ne porte
# AUJOURD'HUI aucun cardinal de roster NU (sa seule phrase de comptage est « 26
# agents pilotés », qualifiée et donc échappée). La couverture est donc
# PROSPECTIVE : elle mord le jour où un cardinal nu y apparaîtra et vieillira.
# C'est peu, c'est réel, et c'est dit — plutôt qu'une couverture affirmée qui
# serait nulle.
FP="$WORK/faux_population"
mkdir -p "$FP/.agents/ref"
printf 'un kit de %s agents.\n' "$CARDINAL_ROSTER" > "$FP/README.md"
printf 'le roster porte 7 agents sur cet arbre.\n' > "$FP/.agents/ref/MODEL_MODES.md"
ecarts_comptage "$FP" "$CARDINAL_ROSTER" > "$WORK/r7d"
juge_mord "$WORK/r7d" "mutation : cardinal nu perime dans MODEL_MODES.md -> signale"

echo "=== §5-postposes — un qualifiant FRANCAIS postpose echappe, T-00000567"
# LES DEUX TÉMOINS SONT RÉELS, pris sur l'arbre : `MODEL_MODES.md` § 3.3 porte
# « 26 agents pilotés » (26 = les agents pilotés par le levier sur codex,
# `EXPECTED_TOUCHED`) et `CADRE/index.html:244` porte « 8 agents de sécurité ».
# Sans l'échappement postposé, ces deux-là rougissaient comme des cardinaux
# périmés — c'est ce qui a tenu `MODEL_MODES.md` hors de la population.
printf '%s agents au roster.\n8 agents de sécurité.\n26 agents pilotés.\n' \
  "$CARDINAL_ROSTER" > "$FP/.agents/ref/MODEL_MODES.md"
ecarts_comptage "$FP" "$CARDINAL_ROSTER" > "$WORK/r7f"
juge "$WORK/r7f" "populations qualifiees postposees en francais -> silence, aucun faux rouge"
# CONTRÔLE NÉGATIF : l'échappement ne doit pas avaler un vrai cardinal nu posé
# JUSTE À CÔTÉ d'une population qualifiée.
printf '7 agents au roster.\n8 agents de sécurité.\n' > "$FP/.agents/ref/MODEL_MODES.md"
ecarts_comptage "$FP" "$CARDINAL_ROSTER" > "$WORK/r7g"
juge_mord "$WORK/r7g" "un cardinal NU perime rougit encore, a cote d une population qualifiee"

echo "=== §5-temoins — le motif mord, et il ne mord PAS les autres populations"
FC="$WORK/faux_compte"; mkdir -p "$FC"
printf 'un kit de %s agents, dont 8 dedicated agents et 17 core + 8 security.\n' "$CARDINAL_ROSTER" > "$FC/README.md"
ecarts_comptage "$FC" "$CARDINAL_ROSTER" > "$WORK/r7a"
juge "$WORK/r7a" "temoin : compte juste + populations qualifiees -> silence (aucun faux positif)"
printf 'un kit de 22 specialized agents.\n' > "$FC/README.md"
ecarts_comptage "$FC" "$CARDINAL_ROSTER" > "$WORK/r7b"
juge_mord "$WORK/r7b" "mutation : « 22 specialized agents » -> comptage perime signale"
printf 'aucune phrase de comptage ici.\n' > "$FC/README.md"
ecarts_comptage "$FC" "$CARDINAL_ROSTER" > "$WORK/r7c"
juge_mord "$WORK/r7c" "corpus muet : la VACUITE est dite au lieu d etre verte"

# ---------------------------------------------------------------------
# RÉVISION D'ARBITRAGE (T-00000393) — le « remplace /mode » du libellé ci-dessous
# reste EXACT : `/mode` n'est toujours pas une commande de ce dépôt, donc la
# section originale serait toujours rouge par construction. Ce que T-00000393 a
# importé est un SCRIPT, `core-scripts/apply-mode.py {expert|restore|status}`,
# UPGRADE SEULEMENT — voir `.agents/ref/MODEL_MODES.md`. Aucune assertion de
# cette section ne change ; ce commentaire empêche seulement de relire son
# libellé comme un arbitrage périmé.
echo "=== §5b (remplace /mode) — les tableaux d agents enumerent TOUT le roster"
ecarts_tableau "$ROOT" "$WORK/roster" > "$WORK/r8"
juge "$WORK/r8" "README.md et README-CLAUDE.md citent les $CARDINAL_ROSTER agents"

echo "=== §5b-temoins — un agent absent du tableau rougit"
FT="$WORK/faux_tab"; mkdir -p "$FT/.agents"; : > "$FT/.agents/IS_THE_KIT"
printf 'alpha\nbeta\n' > "$WORK/roster_faux"
{ echo '| Agent | Model | Effort | Role |'; echo '|---|---|---|---|'
  echo '| `alpha` | haiku | low | a |'; echo '| `beta` | haiku | low | b |'; echo; } > "$FT/README.md"
ecarts_tableau "$FT" "$WORK/roster_faux" > "$WORK/r8a"
juge "$WORK/r8a" "temoin : tableau complet -> silence"
{ echo '| Agent | Model | Effort | Role |'; echo '|---|---|---|---|'
  echo '| `alpha` | haiku | low | a |'; echo; } > "$FT/README.md"
ecarts_tableau "$FT" "$WORK/roster_faux" > "$WORK/r8b"
juge_mord "$WORK/r8b" "mutation : beta retire du tableau -> agent absent signale"

echo "=== §5b-adoptant — hors kit, README.md n est pas juge ; README-CLAUDE.md l est"
FA="$WORK/faux_tab_adoptant"; mkdir -p "$FA"
printf '# Cadre — guide de votre projet\n' > "$FA/README.md"
{ echo '| Agent | Model | Effort | Role |'; echo '|---|---|---|---|'
  echo '| `alpha` | haiku | low | a |'; echo '| `beta` | haiku | low | b |'; echo; } > "$FA/README-CLAUDE.md"
ecarts_tableau "$FA" "$WORK/roster_faux" > "$WORK/r8c"
juge "$WORK/r8c" "adoptant : README.md sans tableau + README-CLAUDE.md complet -> silence"
{ echo '| Agent | Model | Effort | Role |'; echo '|---|---|---|---|'
  echo '| `alpha` | haiku | low | a |'; echo; } > "$FA/README-CLAUDE.md"
ecarts_tableau "$FA" "$WORK/roster_faux" > "$WORK/r8d"
juge_mord "$WORK/r8d" "adoptant : beta retire du tableau de README-CLAUDE.md -> agent absent signale"

# ---------------------------------------------------------------------
echo "=== §6 — TOKEN_BUDGETS.md porte une ligne par agent, NOM par nom"
noms_bareme "$ROOT" > "$WORK/bareme"
{ comm -23 "$WORK/roster" "$WORK/bareme" | sed 's/^/SANS BUDGET: /'
  comm -13 "$WORK/roster" "$WORK/bareme" | sed 's/^/BUDGET ORPHELIN: /'; } > "$WORK/r9"
juge "$WORK/r9" "bareme == roster ($(nb_lignes "$WORK/bareme") lignes / $CARDINAL_ROSTER agents)"

# ---------------------------------------------------------------------
echo "=== §7 — le communicator declare read-only sur CHAQUE hote decouvert"
vus_comm=0
: > "$WORK/r10"
while IFS= read -r d; do
  [ -n "$d" ] || continue
  for f in "$d"/*; do
    [ -f "$f" ] || continue
    # Les trois suffixes d'hôte en clair plutôt qu'un `$(nom_agent …)` : la
    # substitution de commande forke, et ce filtre passe sur 4 × 26 fichiers.
    case "${f##*/}" in
      communicator.md|communicator.toml|communicator.agent.md) ;;
      *) continue ;;
    esac
    vus_comm=$((vus_comm + 1))
    grep -qiE 'read[-_ ]?only' "$f" || \
      printf 'SANS DECLARATION: %s ne dit pas read-only\n' "${f#"$ROOT"/}" >> "$WORK/r10"
  done
done < "$WORK/hotes"
[ "$vus_comm" -eq 0 ] && printf 'VACUITE: aucun communicator trouve sur aucun hote\n' >> "$WORK/r10"
juge "$WORK/r10" "communicator read-only sur les $vus_comm hotes qui le portent"

# ---------------------------------------------------------------------
echo "================================================================"
echo "Resume : $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ]
