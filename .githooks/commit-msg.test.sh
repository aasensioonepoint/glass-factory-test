#!/usr/bin/env bash
# Tests for .githooks/commit-msg. Run: bash .githooks/commit-msg.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# requires: git
#
# REQUIRED, not auto-skipped, and for the same reason as `pre-push.test.sh`: the
# last two arms drive a REAL `git commit` through a REAL installed hook. Without
# git they would establish nothing, and announcing that with `exit 0` would have
# the runner count it as a pass.
#
# THE ARM THAT MATTERS IS THE NEGATIVE CONTROL (arms 13-14). Every arm above it
# calls the script directly, so together they prove the LOGIC and nothing about
# the WIRING — a hook that git never runs would pass all of them. That is the
# shape of a decorative witness, measured twice on this repo the same day this
# suite was written.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/commit-msg"

# `git init <dir>` HONORE $GIT_DIR — mesure : avec GIT_DIR exporte, `git init X`
# ne cree PAS X/.git et reutilise le depot herite. Ce banc est ramasse par
# core-scripts/run-bash-tests.sh, appele par verify.sh, lui-meme appelable
# DEPUIS UN HOOK GIT — et git y exporte GIT_DIR. Sans ce nettoyage, les arms 8
# plus bas commiteraient dans le depot HOTE et compteraient ses commits : faux
# rouge, plus des ecritures hors perimetre. Defaut herite de pre-push.test.sh,
# releve par le binome. Noms = conftest.py::GIT_REDIRECTIONS (T-00001088) : les
# 5 d'origine, plus les redirections et injections de configuration qui manquaient.
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }

# Les sections REELLEMENT jouees : chaque en-tete `# --- N.` appelle `jouee`, la
# ligne finale imprime ce compte et refuse s il ne vaut pas SECTIONS_ATTENDUES —
# une section retiree ou court-circuitee ne s annonce plus jouee.
SECTIONS=0
SECTIONS_ATTENDUES=12
jouee() { SECTIONS=$((SECTIONS + 1)); }

# run_bounded <rep> <hook> <fichier> : lance le hook DEPUIS <rep>, en fond, et
# l attend au plus 5 s (50 tours de 0,1 s). RC = son code, 124 s il vit encore
# (tue alors) ; ERR = son stderr.
#
# POURQUOI UN WATCHDOG EN BASH, ET PAS `timeout 5`. Mesure du 2026-10-19 : sur un
# poste macOS ni `timeout` ni `gtimeout` n existent — seule la CI pose coreutils
# (ci.yml) — et l arm 7bis rendait rc 127, banc ROUGE sur le poste du dev, VERT
# sur la CI seule. Un banc qui ne tourne que la-bas ne garde rien ici.
#
# `exec` EST PORTANT : sans lui le sous-shell reste le parent du hook, `kill`
# tue le sous-shell et le hook en boucle survit, orphelin (mesure au critique,
# mutant M-H0). Avec `exec` le PID tue EST le hook.
run_bounded() {
  ( cd "$1" && exec "$2" "$3" ) 2>"$TMP/err" 1>/dev/null &
  BOUNDED_PID=$!
  tours=0
  while kill -0 "$BOUNDED_PID" 2>/dev/null; do
    tours=$((tours + 1))
    if [ "$tours" -gt 50 ]; then
      kill -9 "$BOUNDED_PID" 2>/dev/null || true
      wait "$BOUNDED_PID" 2>/dev/null || true
      RC=124
      ERR="$(cat "$TMP/err")"
      return 0
    fi
    sleep 0.1
  done
  set +e
  wait "$BOUNDED_PID"
  RC=$?
  set -e
  ERR="$(cat "$TMP/err")"
}

NL="$(printf '\nx')"
NL="${NL%x}"
# Un numero de tache valide, pose en CORPS des bras qui ne jugent pas la tache.
ID="${NL}${NL}T-00000001"

# commit_fi <message> : un commit sur refs/heads/main au format `git fast-import`
# (arbre vide). Messages ASCII : `data` compte des octets, ${#1} des caracteres.
commit_fi() {
  printf 'commit refs/heads/main\ncommitter Banc <banc@example.invalid> 1700000000 +0000\ndata %s\n%s\n' "${#1}" "$1"
}

# depot <rep> <conformes> <sans_id> <chore_state> <sans_tache_nus> : un depot
# JETABLE dont l historique FIXE le palier, ecrit en UN processus fast-import.
# Le hook ne tourne JAMAIS dans le depot hote : son palier (57 % le jour de
# l ecriture) rendrait le banc dependant du jour.
depot() {
  git init -q "$1"
  git -C "$1" symbolic-ref HEAD refs/heads/main
  {
    i=0
    while [ "$i" -lt "$2" ]; do i=$((i + 1)); commit_fi "feat: conforme $i (T-00000001)"; done
    i=0
    while [ "$i" -lt "$3" ]; do i=$((i + 1)); commit_fi "feat: sans numero $i"; done
    i=0
    while [ "$i" -lt "$4" ]; do i=$((i + 1)); commit_fi "chore(state): etat $i"; done
    i=0
    while [ "$i" -lt "$5" ]; do
      i=$((i + 1))
      # Une sortie `Sans-tache:` NUE ou trop courte ne passe pas le predicat
      # unitaire : le palier ne doit pas la compter non plus (C16).
      if [ $((i % 2)) -eq 0 ]; then
        commit_fi "feat: nu $i${NL}${NL}Sans-tache:"
      else
        commit_fi "feat: court $i${NL}${NL}Sans-tache: court"
      fi
    done
  } | git -C "$1" fast-import --quiet
}

# run_in <depot> <message> <bras> : le hook sur un message, DEPUIS <depot>.
# RC = son code, ERR = son stderr ; une boucle infinie est dite BOUCLE INFINIE.
run_in() {
  printf '%s' "$2" > "$TMP/msg"
  run_bounded "$1" "$HOOK" "$TMP/msg"
  [ "$RC" -ne 124 ] || fail "$3: BOUCLE INFINIE (hook toujours vivant a 5 s)"
}

# Drive the hook on a message, return its rc in RC and its stderr in ERR —
# dans le depot `refus` (20 commits conformes), sauf mention.
run_msg() {
  run_in "$TMP/refus" "$1" "$2"
}

accepts() {
  run_msg "$1" "$2"
  [ "$RC" -eq 0 ] || fail "$2: attendu accepte, obtenu rc=$RC — $ERR"
}

refuses() {
  run_msg "$1" "$2"
  [ "$RC" -ne 0 ] || fail "$2: attendu REFUSE, obtenu rc=0 — le hook laisse passer"
}

# Un refus de TYPE porte un numero en CORPS (jamais au sujet : `fix: T-...`
# rendrait 3d acceptable) et doit dire `aucun type connu` — sinon le controle
# de tache le ferait rougir A LA PLACE du type : temoin vacant.
refuses_type() {
  refuses "$1$ID" "$2"
  echo "$ERR" | grep -q "aucun type connu" \
    || fail "$2: refuse, mais PAS sur le type — $ERR"
}

depot "$TMP/refus" 20 0 0 0
depot "$TMP/avert" 5 0 0 0

# --- 1. les dix types de AGENTS.md -------------------------------------------
jouee
# `revert`, `ci` et `build` sont entres le 2026-09-14 sur decision pilote, apres
# mesure : 1054 sujets conformes sur 1065, et les trois manquants etaient
# precisement ceux-la. Les refuser aurait enseigne le reflexe `--no-verify`.
# Piege 2 (T-01M54GEQ68NTP1C34EYTF0SDHX) : chaque acceptation porte un numero de
# tache, sans quoi le palier `refus` la ferait rougir pour une autre raison que
# son type.
for t in feat fix chore docs refactor perf test revert ci build; do
  accepts "$t: un sujet (T-00000001)" "1 ($t)"
done
refuses_type "wip: un sujet"   "1bis la liste reste FERMEE — sinon ces dix arms ne prouvent rien"

# --- 2. portee et rupture -----------------------------------------------------
jouee
accepts "fix(dash): un sujet (T-00000001)"     "2a portee"
accepts "feat(porte)!: un sujet (T-00000001)"  "2b rupture avec portee"
accepts "fix!: un sujet (T-00000001)"          "2c rupture sans portee"

# --- 3. ce qui doit etre REFUSE ----------------------------------------------
jouee
# Sans ces arms, tout ce qui precede serait satisfait par un hook qui rend
# toujours 0 — c'est-a-dire par rien du tout.
refuses_type "wip: un sujet"           "3a type inconnu"
refuses_type "un sujet sans type"      "3b aucun prefixe"
refuses_type "fix un sujet"            "3c type sans deux-points"
refuses_type "fix:"                    "3d deux-points sans sujet"
refuses_type "fix:colle"               "3e deux-points sans espace"
refuses_type "Fix: majuscule"          "3f la casse compte"
refuses_type "feat(: portee ouverte"   "3g portee malformee"

# --- 4. le refus NOMME le remede ---------------------------------------------
jouee
# Un refus qui ne dit pas quoi faire se contourne au lieu de se corriger.
run_msg "wip: un sujet$ID" "4"
echo "$ERR" | grep -q "feat:" || fail "4a: le refus ne liste pas les types connus"
echo "$ERR" | grep -q "fix(dash):" || fail "4b: le refus ne montre pas la forme avec portee"
echo "$ERR" | grep -q "wip: un sujet" || fail "4c: le refus ne rend pas le sujet qu'il a lu"
echo "$ERR" | grep -q "FORME" || fail "4d: le refus n'ecrit pas sa borne — il juge la forme, pas la verite"

# --- 5. le sujet est la premiere ligne NON VIDE ET NON COMMENTEE -------------
jouee
# Lire la ligne 1 aveuglement jugerait le gabarit de git, pas le sujet retenu.
accepts "$(printf '# un commentaire\n# un autre\nfix: le vrai sujet (T-00000001)\n')" "5a commentaires sautes"
accepts "$(printf '\n\nfix: le vrai sujet (T-00000001)\n')"                            "5b lignes vides sautees"
# CONTROLE NEGATIF DE 5b, ET IL MANQUAIT : mesure du binome, retirer la branche
# `"") continue` du hook laissait le banc a 9/9, parce que les deux
# comportements rendent 0 — sujet trouve d un cote, fail-open de l autre. Un
# `accepts` ne peut pas temoigner d un saut.
refuses_type "$(printf '\n\nwip: le vrai sujet\n')" "5b' les lignes vides sont SAUTEES, pas avalees en fail-open"
refuses_type "$(printf '# fix: piege dans un commentaire\nwip: le vrai sujet\n')" "5c un commentaire bien forme ne sauve pas un sujet mauvais"

# --- 5bis. LE TROU MESURE, EPINGLE PLUTOT QUE FERME --------------------------
jouee
# Sur le chemin `-m`/`-F`, git utilise `--cleanup=whitespace` et GARDE les
# commentaires : il enregistre donc `#` comme sujet pendant que ce hook le saute
# et lit la ligne suivante. Mesure : `git commit -m "$(printf '#\nfix: x')"` est
# ACCEPTE et stocke `#` en sujet. Le fermer demanderait de modeliser les modes
# de cleanup de git — un mecanisme plus gros que celui qu on garde. L arm fige
# donc la divergence CONNUE : le jour ou quelqu un la ferme, il rougit ici et
# lit pourquoi, au lieu de croire a une regression.
accepts "$(printf '#\nfix: le hook lit la ligne suivante (T-00000001)\n')" \
  "5bis divergence CONNUE : git enregistrerait '#', le hook lit la suite"

# --- 6. les exemptions, et chacune est un message que git ECRIT lui-meme ------
jouee
# Un numero en CORPS : ces bras jugent l exemption du TYPE (sans elle, aucun de
# ces sujets n a de type) ; l exemption de la TACHE est jugee seule en 10f.
accepts "Merge branch 'x' into y$ID"        "6a merge"
accepts "Revert \"fix: quelque chose\"$ID"  "6b revert"
accepts "fixup! fix: quelque chose$ID"      "6c fixup"
accepts "squash! fix: quelque chose$ID"     "6d squash"
accepts "amend! fix: quelque chose$ID"      "6e amend"
accepts "Squashed commit of the following:$ID" "6e' merge --squash — sujet ECRIT PAR GIT"

# CONTROLE NEGATIF DES EXEMPTIONS. `Merge ` et `Revert ` etaient des MOTS
# LIBRES : mesure du binome, « Merge les deux configs sans type » passait, et le
# texte du refus ENUMERAIT les prefixes exemptes — un lecteur refuse n avait
# qu a recopier le premier. Les motifs exigent desormais les formes que git
# ECRIT, et les vraies fusions restent couvertes par MERGE_HEAD.
refuses_type "Merge les deux configs sans type" "6f Merge n est pas un mot-cle libre"
refuses_type "Revert le chantier entier"        "6g Revert sans guillemet n est pas un revert de git"
refuses_type "amend!hop"                        "6h amend! sans espace n est pas un marqueur git"
refuses_type "fixup!nimporte quoi"              "6i fixup! sans espace non plus"

# --- 7. FAIL-OPEN : pas de fichier, pas de sujet -----------------------------
jouee
# Un hook qui refuse quand il ne sait pas bloquerait un git dont on ne modelise
# pas l'etat. Toutes les surfaces advisory de ce kit echouent ouvertes.
set +e
"$HOOK" "$TMP/inexistant" 2>/dev/null; RC=$?
set -e
[ "$RC" -eq 0 ] || fail "7a: fichier absent doit passer (fail-open), obtenu rc=$RC"

set +e
"$HOOK" 2>/dev/null; RC=$?
set -e
[ "$RC" -eq 0 ] || fail "7b: aucun argument doit passer (fail-open), obtenu rc=$RC"

accepts ""                                   "7c message vide (git refuse deja)"
accepts "$(printf '# que des commentaires\n')" "7d que des commentaires"

# --- 7bis. PAS DE BOUCLE INFINIE sur une derniere ligne sans saut de ligne ----
jouee
# Le correctif de l'arm 3a ajoute `|| [ -n "$line" ]` a la condition de boucle.
# Si `read` ne vidait PAS la variable en fin de fichier, un commentaire en
# derniere ligne sans `\n` final relancerait le corps avec la MEME valeur,
# indefiniment — dans un hook de commit, donc sur le chemin de chaque commit.
# Mesure : rc 0 sur les trois formes, jamais 124. Le delai passe par
# `run_bounded` (watchdog bash), jamais par `timeout` : absent de macOS, il
# rendait rc 127 et le banc ROUGE sur le poste du dev.
for probe in '# commentaire sans saut final' '' '# a
# b'; do
  printf '%s' "$probe" > "$TMP/loop"
  run_bounded "$TMP" "$HOOK" "$TMP/loop"
  [ "$RC" -ne 124 ] || fail "7bis: BOUCLE INFINIE sur une derniere ligne sans saut de ligne"
  [ "$RC" -eq 0 ] || fail "7bis: attendu fail-open (rc 0) sans sujet, obtenu rc=$RC"
done

# --- 8. NEGATIVE CONTROL DU CABLAGE : un vrai git commit ---------------------
jouee
# Tout ce qui precede appelle le script a la main. Un hook que git n'execute
# jamais passerait chacun de ces arms.
# Le depot NAIT au palier refus (20 commits conformes) : le cablage de la tache
# (8f, 8g) s y juge en mode refus, et les comptes 8c/8e partent de 20.
REPO="$TMP/repo"
depot "$REPO" 20 0 0 0
mkdir -p "$REPO/.githooks"
cp "$HOOK" "$REPO/.githooks/commit-msg"
chmod +x "$REPO/.githooks/commit-msg"
git -C "$REPO" config core.hooksPath .githooks
git -C "$REPO" config user.email "banc@example.invalid"
git -C "$REPO" config user.name "Banc"
# Une config GLOBALE de l hote ne doit pas decider du verdict : un
# `commit.gpgsign=true` sans clef fait rougir l arm 8d sous le message MAL
# ATTRIBUE « le hook mord trop large », et un `commit.template` injecterait un
# gabarit dans les messages du banc.
git -C "$REPO" config commit.gpgsign false
git -C "$REPO" config commit.template ""
echo "un" > "$REPO/a.txt"
git -C "$REPO" add a.txt
compte() { git -C "$REPO" rev-list --count --all; }
AVANT="$(compte)"

set +e
OUT_BAD="$(git -C "$REPO" commit -m "wip: mauvais type" 2>&1)"
RC_BAD=$?
set -e
[ "$RC_BAD" -ne 0 ] || fail "8a: git a ACCEPTE un sujet mauvais — le hook n'est pas execute"
echo "$OUT_BAD" | grep -q "REFUSE par commit-msg" \
  || fail "8b: le refus de git ne porte pas le message du hook: $OUT_BAD"
[ "$(compte)" = "$AVANT" ] \
  || fail "8c: le commit a ete cree malgre le refus (compte $AVANT -> $(compte))"

set +e
OUT_OK="$(git -C "$REPO" commit -m "feat(banc): bon type (T-00000001)" 2>&1)"
RC_OK=$?
set -e
[ "$RC_OK" -eq 0 ] || fail "8d: un sujet BON a ete refuse — le hook mord trop large: $OUT_OK"
[ "$(compte)" = "$((AVANT + 1))" ] || fail "8e: le bon commit n'a pas ete cree (compte $AVANT -> $(compte))"

# --- 9. un rebase rejoue des sujets DEJA juges -------------------------------
jouee
# Les refuser une seconde fois transforme un vieux manquement en mur qui arrete
# une operation sans rapport.
# run_marker <message> <bras> : le hook installe du depot $REPO, depuis $REPO.
run_marker() {
  printf '%s' "$1" > "$REPO/msg"
  run_bounded "$REPO" "$REPO/.githooks/commit-msg" "$REPO/msg"
  [ "$RC" -ne 124 ] || fail "$2: BOUCLE INFINIE (hook toujours vivant a 5 s)"
}

# LES QUATRE MARQUEURS, PAS LE PREMIER SEUL. L arm d origine ne touchait que
# `rebase-merge` : retirer les trois autres de la boucle du hook laissait le
# banc VERT. `REVERT_HEAD` est entre le 2026-09-14 avec le resserrement des
# prefixes — tant que « Revert » etait un mot libre, il ne servait a rien.
for marker in rebase-merge rebase-apply CHERRY_PICK_HEAD REVERT_HEAD MERGE_HEAD; do
  touch "$REPO/.git/$marker"
  run_marker "wip: rejoue par une operation de git$ID" "9a ($marker)"
  [ "$RC" -eq 0 ] || fail "9a ($marker): un sujet rejoue sous ce marqueur doit passer, obtenu rc=$RC"
  rm -f "$REPO/.git/$marker"
  run_marker "wip: rejoue par une operation de git$ID" "9b ($marker)"
  [ "$RC" -ne 0 ] \
    || fail "9b ($marker): sans le marqueur le meme sujet doit etre REFUSE — sinon l'arm precedent ne prouve rien"
  echo "$ERR" | grep -q "aucun type connu" \
    || fail "9b ($marker): refuse, mais PAS sur le type — $ERR"
done

# --- 10. LE NUMERO DE TACHE ET SON PALIER (T-01M54GEQ68NTP1C34EYTF0SDHX) ------
jouee
# Mode refus (depot `refus`, 20/20 conformes) sauf mention. L ORDRE DES BRAS EST
# PORTANT : ce banc s arrete au premier FAIL, et chaque mutant doit rougir
# d abord sur SON bras — 10a (le hook PARLE, mode avertissement) avant 10h (le
# refus du palier), 10e (borne de 10) avant la suite de 10h (`Sans-tache:` nus).

# 10a : sans numero, le hook PARLE — mutant M-H1 (controle retire).
run_in "$TMP/avert" "feat: x" "10a (avertissement)"
[ "$RC" -eq 0 ] || fail "10a (avertissement): sous le palier le hook avertit et laisse passer, obtenu rc=$RC — $ERR"
for mot in "AVERTISSEMENT" "aucun numéro de tâche" "Sans-tache:" "palier 5/5"; do
  echo "$ERR" | grep -q "$mot" || fail "10a (avertissement): stderr ne porte pas « $mot » — $ERR"
done

# 10h : le palier — mutants M-H7 (toujours avertir) et M-H8 (chore non exclu).
depot "$TMP/p19" 19 1 0 0
run_in "$TMP/p19" "feat: x" "10h (19/20)"
[ "$RC" -eq 1 ] || fail "10h (19/20): 95 % pile = REFUS, obtenu rc=$RC — $ERR"
echo "$ERR" | grep -q "palier 19/20" || fail "10h (19/20): le refus ne dit pas son palier — $ERR"
depot "$TMP/p18" 18 2 0 0
run_in "$TMP/p18" "feat: x" "10h (18/20)"
[ "$RC" -eq 0 ] || fail "10h (18/20): 90 % = AVERTISSEMENT rc 0, obtenu rc=$RC — $ERR"
echo "$ERR" | grep -q "AVERTISSEMENT" || fail "10h (18/20): pas d AVERTISSEMENT — $ERR"
echo "$ERR" | grep -q "18/20" || fail "10h (18/20): l avertissement ne dit pas 18/20 — $ERR"
run_in "$TMP/avert" "feat: x" "10h (moins de 20)"
[ "$RC" -eq 0 ] || fail "10h (moins de 20): N < 20 = AVERTISSEMENT rc 0, obtenu rc=$RC — $ERR"
depot "$TMP/chore" 20 0 5 0
run_in "$TMP/chore" "feat: x" "10h (chore exclus)"
[ "$RC" -eq 1 ] || fail "10h (chore exclus): 20 conformes + 5 chore(state) = REFUS, obtenu rc=$RC — $ERR"
echo "$ERR" | grep -q "palier 20/20" || fail "10h (chore exclus): les chore(state) ont ete comptes — $ERR"

# 10a (suite) : en mode refus, le refus dit son remede et son palier.
refuses "feat: x" "10a (refus)"
for mot in "aucun numéro de tâche" "Sans-tache:" "palier 20/20" "sujet lu : feat: x"; do
  echo "$ERR" | grep -q "$mot" || fail "10a (refus): stderr ne porte pas « $mot » — $ERR"
done
echo "$ERR" | grep -q "aucun type connu" && fail "10a (refus): refuse sur le TYPE, pas sur la tache — $ERR"

# 10b : les trois porteurs acceptes.
accepts "feat: x (T-01M5A1138QQC59ZVVPB47SCAG3)"                "10b ULID de 26 au sujet"
accepts "feat: x${NL}${NL}Corps qui cite T-00001240."           "10b 8 chiffres en corps"
accepts "$(printf 'feat: x\n\nTâche: T-01M54GEQ68\n')"          "10b prefixe de 10 en ligne Tache:"

# 10c : un numero en COMMENTAIRE ne compte pas — mutant M-H2 (commentaires lus).
refuses "$(printf 'feat: x\n# T-00000001\n')" "10c numero seulement en commentaire"

# 10d : les bornes du numero — mutant M-H5 (bornes retirees).
refuses "feat: x ABT-12345"                          "10d ABT-12345 (cle Jira)"
refuses "feat: x T-12"                               "10d T-12 (2 chiffres)"
refuses "feat: x T-01M4XZWZ"                         "10d T-01M4XZWZ (8 de ULID)"
refuses "feat: x T-01M5A1138QQC59ZVVPB47SCAG3X"      "10d ULID de 27"

# 10e : la sortie tracee — mutant M-H3 (borne de 10 retiree).
accepts "feat: x${NL}${NL}Sans-tache: commit du pilote hors board" "10e Sans-tache: motive"
refuses "feat: x${NL}${NL}Sans-tache:"                             "10e Sans-tache: vide"
refuses "feat: x${NL}${NL}Sans-tache: court"                       "10e Sans-tache: court"

# 10f : exemptions et marqueurs AVANT la tache — mutant M-H4 (controle avant).
for msg in "Merge branch 'x' into y" "Revert \"fix: quelque chose\"" "fixup! fix: x" \
  "squash! fix: x" "amend! fix: x" "Squashed commit of the following:"; do
  accepts "$msg" "10f exemption sans numero ($msg)"
done
for marker in rebase-merge rebase-apply CHERRY_PICK_HEAD REVERT_HEAD MERGE_HEAD; do
  touch "$REPO/.git/$marker"
  run_marker "feat: rejoue sans numero" "10f ($marker)"
  [ "$RC" -eq 0 ] || fail "10f ($marker): rejoue sous ce marqueur, sans numero, doit passer — rc=$RC $ERR"
  rm -f "$REPO/.git/$marker"
  run_marker "feat: rejoue sans numero" "10f ($marker, retire)"
  [ "$RC" -ne 0 ] || fail "10f ($marker, retire): sans le marqueur, sans numero, doit etre REFUSE"
  echo "$ERR" | grep -q "aucun numéro de tâche" \
    || fail "10f ($marker, retire): refuse, mais pas sur la tache — $ERR"
done

# 10g : la coupe `>8` de `git commit -v` — mutant M-H6 (coupe retiree).
refuses "$(printf 'feat: x\n# ------------------------ >8 ------------------------\n+ligne T-00000001\n')" \
  "10g numero seulement SOUS la ligne de coupe"
accepts "$(printf 'feat: x\nT-00000001\n# ------------------------ >8 ------------------------\n+ligne\n')" \
  "10g numero AU-DESSUS de la ligne de coupe (la coupe n avale pas tout)"

# 10h (suite) : 200 `Sans-tache:` nus ou courts ne passent pas le predicat
# unitaire, le palier ne les compte pas — mutant M-H9 (le palier compte une
# ligne `Sans-tache:` sans sa borne de 10, C16).
depot "$TMP/nus" 0 0 0 200
run_in "$TMP/nus" "feat: x" "10h (200 Sans-tache: nus)"
[ "$RC" -eq 0 ] || fail "10h (200 Sans-tache: nus): toujours AVERTISSEMENT, obtenu rc=$RC — $ERR"
echo "$ERR" | grep -q "palier 0/200" || fail "10h (200 Sans-tache: nus): palier attendu 0/200 — $ERR"

# --- 8 (suite). LE CABLAGE DE LA TACHE : un vrai git commit, mode refus -------
# Joues APRES 10 pour que M-H1, M-H6 et M-H7 rougissent d abord sur leur bras
# nomme ; ils rougissent aussi ici.
echo "deux" > "$REPO/a.txt"
git -C "$REPO" add a.txt
AVANT="$(compte)"
set +e
OUT_T="$(git -C "$REPO" commit -m "feat(banc): sans tache" 2>&1)"
RC_T=$?
set -e
[ "$RC_T" -ne 0 ] || fail "8f: git a ACCEPTE un commit sans numero en mode refus"
echo "$OUT_T" | grep -q "aucun numéro de tâche" || fail "8f: le refus ne vient pas du controle de tache: $OUT_T"
[ "$(compte)" = "$AVANT" ] || fail "8f: le commit a ete cree malgre le refus"

# 8g : `git commit -v` par l editeur — le fichier recu porte le gabarit, la
# ligne de coupe PUIS le diff indexe (mesure, git 2.54.0). Le numero n est que
# dans le diff : refus. L editeur bouchon est appele PAR SON NOM via PATH —
# aucun chemin interpole dans la chaine que git passe a sh.
mkdir -p "$TMP/bin"
printf '%s\n' '#!/bin/sh' 'cat "$1" > "$1.banc"' \
  'echo "feat(banc): par l editeur sans tache" > "$1"' 'cat "$1.banc" >> "$1"' \
  > "$TMP/bin/editeur-banc"
chmod +x "$TMP/bin/editeur-banc"
# `commit.template ""` (pose plus haut contre un gabarit GLOBAL) suffit sur `-m`,
# mais le chemin editeur LIT le gabarit : `fatal: could not read ''` (mesure).
# Un fichier vide garde la neutralisation sans casser l editeur.
: > "$TMP/gabarit-vide"
git -C "$REPO" config commit.template "$TMP/gabarit-vide"
echo "ligne T-00000002 seulement dans le diff" > "$REPO/b.txt"
git -C "$REPO" add b.txt
AVANT="$(compte)"
set +e
OUT_V="$(PATH="$TMP/bin:$PATH" GIT_EDITOR=editeur-banc git -C "$REPO" commit -v 2>&1)"
RC_V=$?
set -e
[ "$RC_V" -ne 0 ] || fail "8g: git commit -v ACCEPTE un numero lu dans le diff, sous la coupe"
echo "$OUT_V" | grep -q "aucun numéro de tâche" || fail "8g: le refus ne vient pas du controle de tache: $OUT_V"
[ "$(compte)" = "$AVANT" ] || fail "8g: le commit a ete cree malgre le refus"

# Sections : 1, 2, 3, 4, 5, 5bis, 6, 7, 7bis, 8, 9, 10 — comptees par `jouee`.
[ "$SECTIONS" -eq "$SECTIONS_ATTENDUES" ] || fail "$SECTIONS section(s) jouee(s) sur $SECTIONS_ATTENDUES attendues"
echo "PASS: commit-msg ($SECTIONS/$SECTIONS_ATTENDUES)"
