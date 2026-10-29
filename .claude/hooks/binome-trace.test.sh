#!/usr/bin/env bash
# =====================================================================
# BANC — binome-trace.sh écrit-il la preuve que la garde attend ? (T-00000586)
#
# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# allows-missing: python python3 py
#
# ---------------------------------------------------------------------
# CE QU'IL MESURE, ET CE QU'IL NE PEUT PAS MESURER
# ---------------------------------------------------------------------
# Il mesure que le hook ÉCRIT la bonne forme sur la bonne charge : le bon nom,
# la bonne tâche, le bon SHA, et RIEN quand l'agent n'est pas un critique.
#
# Il NE PEUT PAS prouver que l'hôte émet `SubagentStop` avec `agent_type` — aucun
# banc ne le peut, seule une session vivante le peut. ELLE L'A FAIT, LE MÊME JOUR,
# et le relevé vaut mieux qu'une supposition dans les deux sens :
#   .agents/state/local/binome/T-012.critic-opus  → 2026-09-13T11:26:12Z @ 659603f
#   .agents/state/local/binome/T-012.critic-fable → 2026-09-13T11:32:20Z @ 659603f
# Les deux critiques de la passe globale — la PAIRE de clôture que la règle
# exigeait alors (2026-09-13) — ont été tracés, sur la tâche `running`, dans la
# session même qui a enregistré le hook. Donc : le champ existe, la jambe se
# déclenche, et l'enregistrement prend effet SANS redémarrage. Depuis S-00004500
# (2026-10-07), la revue de clôture se joue à UN critique (`critic-opus`, repli
# `critic-fable` puis `critic-sonnet-max`) ; le relevé reste vrai de ce jour-là.
#
# DEUX RÉDACTIONS FAUSSES SE SONT SUCCÉDÉ ICI EN UNE HEURE, et c'est pour ça
# qu'on écrit le relevé plutôt qu'un jugement : la première affirmait « déjà
# consommé en production » (supposé, non mesuré) ; la seconde, corrigeant trop
# loin, affirmait que rien n'était mesuré et qu'il faudrait redémarrer — les
# fichiers ci-dessus l'infirment. Une prudence excessive est aussi une erreur
# de fait.
#
# LE CAS LE PLUS IMPORTANT EST LE CONTRÔLE NÉGATIF (c) : un agent qui n'est PAS
# un critique ne doit RIEN écrire. Sans lui, n'importe quel sous-agent
# fabriquerait la preuve que la garde exige, et la garde ne prouverait plus rien.
# =====================================================================
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT="$(cd "$HERE/../.." && pwd)"
HOOK="$HERE/binome-trace.sh"
TASKS="$KIT/.agents/bin/tasks.py"

PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# T-00000753 : joué DIRECTEMENT, ce banc isole son état machine (le runner le fait déjà, `run-bash-tests.sh`) ;
# une valeur déjà posée est RESPECTÉE. Sous $TMP : nettoyé par le trap ci-dessus.
if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi
export CLAUDE_PROJECT_DIR="$TMP"
pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok  — $1"; }
ko() { fail=$((fail+1)); echo "  FAIL — $1"; }

fire() { # <nom de def> [graphie du champ : agent_type (défaut) | agentType]
  # LA GRAPHIE EST UN PARAMÈTRE, et c'est un correctif du binôme de clôture :
  # le hook accepte les DEUX depuis `T-00000589` — son frère `log_agent_usage`
  # le fait depuis toujours, parce que les hôtes ne nomment pas ce champ pareil
  # — et cette branche neuve n'était couverte par AUCUN cas. Un `sed`
  # malheureux sur `agentType` serait repassé vert.
  printf '{"hook_event_name":"SubagentStop","%s":"%s"}' "${2:-agent_type}" "$1" \
    | bash "$HOOK" >/dev/null 2>&1
  RC=$?
}

# UN FICHIER PAR CRITIQUE — correctif du binôme de clôture : un fichier unique
# lu-modifié-réécrit faisait que deux critiques arrêtés dans la même fenêtre
# s'écrasaient, alors que la doctrine imposait jusqu'à S-00004500 (2026-10-07)
# de lancer la paire EN PARALLÈLE. Depuis, la revue de clôture se joue à UN
# critique (`critic-opus`, repli `critic-fable` puis `critic-sonnet-max`) ; le
# fichier par critique reste, il ne suppose aucun ordre entre deux passages.
BINOME="$TMP/.agents/state/local/binome"
# `$TID` : l'id que `new` A RENDU plus bas, jamais un id prédit (T-00000726, R-BANCS (i)).
trace() { printf '%s' "$BINOME/$TID.$1.json"; }
vus() { ls "$BINOME" 2>/dev/null | sed -n 's/^'"$TID"'\.\(.*\)\.json$/\1/p' | sort | tr '\n' ' '; }

# UN VRAI DÉPÔT GIT, ET C'EST UN CORRECTIF DU BINÔME. Sans lui, `git rev-parse`
# échoue dans l'arbre jetable, le hook écrit sa sentinelle `"?"` comme SHA, et
# l'assertion « la trace porte un SHA » était satisfaite par cette sentinelle :
# le banc annonçait mesurer un SHA sans en avoir jamais vu un.
git init -q "$TMP" 2>/dev/null
git -C "$TMP" -c user.email=b@b -c user.name=b commit -q --allow-empty -m socle 2>/dev/null

TID="$("$PY" "$TASKS" --root "$TMP" new "tache en cours" | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p')"
[ -n "$TID" ] && ok "new rend l'id de la tâche du banc" || ko "new n'a pas rendu d'id"

echo "=== (a) AUCUNE tâche running : la trace part sous le nom RÉSERVÉ ====="
# CE TÉMOIN DISAIT L'INVERSE, ET IL PASSAIT POUR LA MAUVAISE RAISON (T-00000603).
# Il asserta longtemps « rien d'écrit », au motif qu'une preuve sans tâche ne
# prouverait rien. C'était vrai du SEUL consommateur connu alors, `tasks.py
# done`, indexé par identifiant. La garde d'affirmation a changé la donne : elle
# mord sur `tasks.py new`, un geste qui PRÉCÈDE tout `start`, donc sur une
# session neuve le binôme tournait et ne laissait AUCUNE trace — la seule issue
# devenait la dérogation, à chaque fois. Une garde franchissable seulement par
# son échappatoire est décorative.
#
# ET SON `vus()` NE POUVAIT PAS VOIR LE REPLI : il ne relève que
# `<id de la tâche>.*.json` (`$TID`). Le témoin serait donc resté VERT sur le nouveau
# comportement sans rien en dire — vacant. On mesure ici les DEUX moitiés.
fire critic-opus
[ "$RC" -eq 0 ] && ok "le hook rend 0 (advisory, toujours)" || ko "le hook a rendu $RC"
[ -f "$BINOME/_sans-slot.critic-opus.json" ] \
  && ok "la trace existe sous le nom réservé — la garde Stop la verra" \
  || ko "aucune trace hors slot : la garde d'affirmation reste infranchissable"
[ -n "$(vus)" ] && ko "une trace a été écrite sur une tâche qui ne tourne pas" \
                 || ok "aucune trace sur un T-… : la clôture ne peut s'en réclamer"
# LE MOTIF N'ÉTAIT MESURÉ NULLE PART (T-00000845) : on ne voyait que l'existence
# du fichier, donc un `board illisible` écrit sur un board sain — ou l'inverse,
# le défaut réel — passait vert. Non-régression du cas NOMINAL, lu sur le vrai
# `tasks.py` ; le cas incident est mesuré en (j) sur un `tasks.py` factice.
motif_de() { "$PY" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("motif", "-"))' "$1" 2>/dev/null; }
M_A="$(motif_de "$BINOME/_sans-slot.critic-opus.json")"
[ "$M_A" = "aucune running" ] \
  && ok "board sain sans running : motif « aucune running »" \
  || ko "board sain sans running : motif « $M_A » au lieu de « aucune running »"
# LA MOITIÉ QUI COMPTE LE PLUS : le nom réservé n'est PAS un identifiant de
# tâche, donc tasks.py ne peut pas le prendre pour une preuve de clôture.
# MESURÉ plutôt que raisonné — c'est ce qui sépare ce repli d'un trou.
#
# DEUX CORRECTIFS DU BINÔME SUR CE SEUL BLOC, tous deux mesurés, tous deux
# « vert pour la mauvaise raison » — la faute que ce chantier paie en série.
#
# (1) LA GARDE DOIT ÊTRE ARMÉE. Première rédaction : le `done` passait, et j'ai
# failli le lire « le nom réservé vaut preuve ». Il passait parce que
# `BINOME_REQUIRED` est ABSENT d'un dépôt jetable, donc la garde accepte tout. Un
# témoin qui mesure un refus doit armer le refus, sinon il mesure son absence.
#
# (2) DEUX TRACES, écrit quand la clôture en exigeait DEUX (avant S-00004500,
# 2026-10-07) : avec une seule, la clôture échouait alors de toute façon sur
# « il en faut DEUX », que `tasks.py` lise le nom réservé ou non, et l'assertion
# ne DISCRIMINAIT rien. Mutation qui laissait alors le témoin vert malgré le
# trou : faire lire `_sans-slot.{nom}.json` en repli dans `binome_trace`. Depuis
# S-00004500, la revue de clôture se joue à UN critique (`BINOME_MIN` = 1 ;
# `critic-opus`, repli `critic-fable` puis `critic-sonnet-max`) : une seule trace
# discriminerait déjà, la seconde est gardée et discrimine encore. Le refus ne
# peut venir que du COMPTE À ZÉRO — donc du fait que `tasks.py` ne voit pas le
# nom réservé.
fire critic-fable
[ -f "$BINOME/_sans-slot.critic-fable.json" ] \
  && ok "les DEUX critiques hors slot sont tracés — le refus qui suit discrimine" \
  || ko "le second critique hors slot n'a pas été tracé"
mkdir -p "$TMP/.agents/state/gates"
printf 'arme' > "$TMP/.agents/state/gates/BINOME_REQUIRED"
DONE_ERR="$("$PY" "$TASKS" --root "$TMP" done "$TID" --raison "tentative" 2>&1 >/dev/null)" \
  && DONE_RC=0 || DONE_RC=$?
if [ "$DONE_RC" -eq 0 ]; then
  ko "une clôture a été acceptée en se réclamant du nom réservé"
elif printf '%s' "$DONE_ERR" | grep -q '0 critique'; then
  ok "deux traces hors slot, et tasks.py en compte ZÉRO"
else
  ko "refusé, mais pour une AUTRE raison que le compte : $DONE_ERR"
fi
rm -f "$TMP/.agents/state/gates/BINOME_REQUIRED"

"$PY" "$TASKS" --root "$TMP" start "$TID" >/dev/null

echo "=== (a') UNE running SANS portée : rien sur elle, motif « aucune portée » ="
# T-01M5F728FGJ43QJX1RJKTWWKRB : plusieurs `running` coexistent, tracer sur chacune ferait
# créditer A2 par la revue de A1. Sans `review-scope`, la trace part sous le nom réservé.
rm -f "$BINOME/_sans-slot.critic-opus.json"
fire critic-opus
M_AP="$(motif_de "$BINOME/_sans-slot.critic-opus.json")"
[ -z "$(vus)" ] && [ "$M_AP" = "aucune portée" ] \
  && ok "running sans portée : aucune trace sur $TID, motif « aucune portée »" \
  || ko "running sans portée : traces « $(vus) », motif « $M_AP »"
"$PY" "$TASKS" --root "$TMP" review-scope "$TID" >/dev/null

echo "=== (b) UN critique : la trace naît, nommée et datée =================="
fire critic-opus
if [ -f "$(trace critic-opus)" ]; then
  "$PY" - "$(trace critic-opus)" <<'PYEOF' 2>/dev/null && ok "la trace porte un VRAI SHA et un instant UTC" || ko "la trace est incomplète"
import json, re, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
# `fullmatch` sur la forme d'un SHA, JAMAIS une simple vérité : la sentinelle
# `"?"` du hook (dépôt git absent) satisfaisait `assert d["sha"]`.
assert re.fullmatch(r"[0-9a-f]{7,40}", d["sha"]), d
assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", d["at"]), d
PYEOF
else ko "aucune trace écrite pour un critique sur une tâche running"; fi

echo "=== (c) CONTRÔLE NÉGATIF : un non-critique n'écrit RIEN =============="
# LE CAS QUI PORTE LE BANC. Si n'importe quel sous-agent pouvait écrire ici, la
# garde de clôture serait satisfaite par un seul `dev-mono` et ne prouverait plus
# rien du tout.
for agent in dev-mono documenter planner exec-critic security-code-review; do
  fire "$agent"
done
[ "$(vus)" = "critic-opus " ] && ok "cinq non-critiques : la trace n'a pas bougé" \
                              || ko "un non-critique a écrit dans la trace : $(vus)"

echo "=== (d) LE SECOND critique s'AJOUTE, il n'écrase pas le premier ======"
fire critic-fable
[ "$(vus)" = "critic-fable critic-opus " ] \
  && ok "les DEUX angles coexistent — le second n'écrase pas le premier" \
  || ko "le second critique a écrasé le premier : $(vus)"

echo "=== (e) LE REPLI est tracé comme les autres =========================="
fire critic-sonnet-max
[ -f "$(trace critic-sonnet-max)" ] && ok "critic-sonnet-max entre dans le vocabulaire" \
                                    || ko "le repli n'est pas tracé"

echo "=== (f) UN SECOND passage du MÊME critique ÉCRASE son entrée ========="
# Ce qui compte est le DERNIER passage de chaque critique, pas son histoire :
# un empilement ferait qu'une revue d'il y a trois cycles vaudrait encore preuve
# pour la clôture d'aujourd'hui. Et rien ne LIT avant d'écrire, ce qui supprime
# la course entre deux critiques qui s'arrêtent ensemble — la paire lancée en
# parallèle jusqu'à S-00004500 (2026-10-07) ; depuis, la revue de clôture se
# joue à UN critique (`critic-opus`, repli `critic-fable` puis `critic-sonnet-max`).
fire critic-opus
"$PY" - "$(trace critic-opus)" <<'PYEOF' 2>/dev/null && ok "une seule entrée par critique — le dernier passage gagne" || ko "la forme de l'entrée a changé"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(d, dict) and set(d) == {"sha", "at", "portee"}, d
PYEOF
[ "$(vus)" = "critic-fable critic-opus critic-sonnet-max " ] \
  && ok "trois fichiers, trois critiques — aucun empilement, aucun écrasement croisé" \
  || ko "l'ensemble des critiques tracés a dérivé : $(vus)"

echo "=== (g) LA GARDE VOIT la trace que ce hook écrit ====================="
# LES DEUX MOITIÉS DU CONTRAT, LIÉES SUR UN CAS RÉEL. Un banc qui mesurerait
# l'écriture sans jamais vérifier que le lecteur l'accepte laisserait passer un
# désaccord de chemin ou de forme entre les deux fichiers.
mkdir -p "$TMP/.agents/state/gates"
printf 'arme' > "$TMP/.agents/state/gates/BINOME_REQUIRED"
if "$PY" "$TASKS" --root "$TMP" done "$TID" --raison "revue faite" >/dev/null 2>&1
then ok "la clôture passe : la garde a lu ce que le hook a écrit"
else ko "la garde REFUSE une trace que ce hook vient d'écrire — les deux moitiés divergent"; fi

echo "=== (h) FAIL-OPEN : charge vide ou illisible, jamais de plantage ====="
printf '' | bash "$HOOK" >/dev/null 2>&1
[ "$?" -eq 0 ] && ok "charge vide : rc=0" || ko "charge vide : le hook a échoué"
printf 'pas du json' | bash "$HOOK" >/dev/null 2>&1
[ "$?" -eq 0 ] && ok "charge illisible : rc=0" || ko "charge illisible : le hook a échoué"

echo "=== (i) LA GRAPHIE camelCase trace AUSSI (T-00000589) ================"
# Le hook ne lisait que `agent_type`. Sur un hôte qui envoie `agentType` il
# sortait 0 EN SILENCE : aucune trace, donc `tasks.py done` refusant toute
# clôture, donc la sortie tracée comme seule issue. Son frère `log_agent_usage`
# accepte les deux depuis toujours. Sans ce cas, la branche neuve n'est couverte
# NULLE PART, sur le seul hôte pourtant mesuré.
#
# PLACÉ EN DERNIER, DÉLIBÉRÉMENT : il ÉCRIT une trace, et les cas (c) et (d)
# asseyent l'ensemble EXACT des traces présentes. Le mettre plus haut les
# faisait rougir — mesuré — pour une raison qui n'avait rien à voir avec eux.
fire critic-sonnet-max agentType
[ -f "$(trace critic-sonnet-max)" ] \
  && ok "la charge camelCase écrit la trace" \
  || ko "la graphie agentType n'écrit rien — la garde serait infranchissable"

echo "=== (j) BOARD ILLISIBLE : le motif le DIT (T-00000845) ==============="
# LE DÉFAUT MESURÉ. `run()` rendait `""` sur rc non nul, sur exception et sur
# timeout de 5 s ; l'appelant le complétait en `"[]"`, donc un board qui n'avait
# PAS répondu produisait `motif=aucune running` — le faux diagnostic « la tâche
# ne tournait pas », alors qu'une tâche pouvait tourner.
#
# UN KIT FACTICE, PARCE QUE L'OUTILLAGE EST ANCRÉ AU SCRIPT : le hook résout
# `tasks.py` depuis `dirname $0`, aucune variable ne le redirige. On copie donc
# le hook dans un arbre dont `.agents/bin/tasks.py` est un stub piloté par
# `BT_STUB`, et chaque mode écrit sous SON `CLAUDE_PROJECT_DIR` — sinon ses
# `_sans-slot.*` écraseraient ceux du cas (a).
#
# LE TIMEOUT EST UN VRAI TIMEOUT : le hook n'expose aucune variable pour
# réduire ses 5 s, et un stub `exit 124` n'exercerait que le bras rc non nul,
# déjà couvert par `rc1`. `dort` coûte donc ~5 s de banc, et c'est le prix de
# mesurer `TimeoutExpired` plutôt que de le supposer.
#
# LES DEUX TÉMOINS `vide` ET `running` TOURNENT SUR LE MÊME STUB : sans eux, un
# stub cassé (introuvable, mauvais interpréteur) rendrait `board illisible`
# partout et les trois bras incident passeraient vert pour la mauvaise raison.
STUBKIT="$TMP/stubkit"
mkdir -p "$STUBKIT/.claude/hooks" "$STUBKIT/.agents/bin"
cp "$HOOK" "$STUBKIT/.claude/hooks/binome-trace.sh"
cat > "$STUBKIT/.agents/bin/tasks.py" <<'PYEOF'
import json, os, sys, time
mode = os.environ.get("BT_STUB", "")
if mode == "rc1":
    sys.exit(1)
if mode == "dort":
    time.sleep(8)
    print("[]")
elif mode == "dict":
    print("{}")
elif mode == "vide":
    print("[]")
elif mode == "running":
    print(json.dumps([{"id": "T-00000009", "state": "running"}]))
elif mode == "utf8":
    sys.stdout.buffer.write(json.dumps(
        [{"id": "T-00000009", "state": "running", "task": "←"}],
        ensure_ascii=False).encode("utf-8"))
elif mode == "sans_id":
    print(json.dumps([{"id": "T-00000009", "state": "running"},
                      {"state": "running"}, {"id": "", "state": "running"}]))
PYEOF

# LA PORTÉE DU STUB (T-01M5F728FGJ43QJX1RJKTWWKRB) : focus et portée sur T-00000009, sans
# quoi la running du stub n'est plus tracée.
# <dossier> [focus du clone, défaut T-00000009] [membres consommés, JSON, défaut aucun]
portee_stub() {
  mkdir -p "$1/.agents/state/local"
  printf '{"task_id":"%s","updated_at":"2026-10-21T00:00:00.000Z"}' "${2:-T-00000009}" \
    > "$1/.agents/state/local/focus.json"
  printf '{"focus":"T-00000009","members":["T-00000009"],"consumed":[%s],"declared_at":"2026-10-21T00:00:00.000Z"}' \
    "${3:-}" > "$1/.agents/state/local/review-scope.json"
}

fire_stub() { # <mode du stub>
  STUB_DIR="$TMP/stub-$1"
  mkdir -p "$STUB_DIR"
  portee_stub "$STUB_DIR"
  printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}' \
    | CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB="$1" bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
  RC=$?
  STUB_SLOT="$STUB_DIR/.agents/state/local/binome/_sans-slot.critic-opus.json"
}

# LOCALE HOSTILE, pour le seul témoin `utf8` : locale C non coercée et mode
# UTF-8 coupé font décoder `text=True` en US-ASCII — l'équivalent mesurable sur
# un poste non-Windows du cp1252 de Windows.
fire_stub_hostile() { # <mode du stub>
  STUB_DIR="$TMP/stub-$1"
  mkdir -p "$STUB_DIR"
  portee_stub "$STUB_DIR"
  printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}' \
    | LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB="$1" \
      bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
  RC=$?
  STUB_SLOT="$STUB_DIR/.agents/state/local/binome/_sans-slot.critic-opus.json"
}

for mode in rc1 dort dict; do
  fire_stub "$mode"
  M="$(motif_de "$STUB_SLOT")"
  if [ "$RC" -ne 0 ]; then
    ko "tasks.py $mode : le hook a rendu $RC (il doit rester advisory)"
  elif [ "$M" = "board illisible" ]; then
    ok "tasks.py $mode : motif « board illisible »"
  else
    ko "tasks.py $mode : motif « $M » — un board qui n'a pas répondu passe pour un board vide"
  fi
done

fire_stub vide
M="$(motif_de "$STUB_SLOT")"
[ "$M" = "aucune running" ] \
  && ok "témoin : stub sain sans running → « aucune running »" \
  || ko "témoin : stub sain sans running → « $M » (le stub lui-même est cassé ?)"

fire_stub running
T9="$STUB_DIR/.agents/state/local/binome/T-00000009.critic-opus.json"
if [ -f "$STUB_SLOT" ]; then
  ko "témoin : une tâche running et pourtant une trace hors slot"
elif [ -f "$T9" ] && [ "$(motif_de "$T9")" = "-" ]; then
  ok "témoin : stub avec running → trace normale sur T-00000009, sans motif"
else
  ko "témoin : stub avec running → aucune trace normale sur T-00000009"
fi

echo "=== (k) BOARD UTF-8 sous une locale NON UTF-8 : lu, pas illisible ===="
# `tasks.py` écrit de l'UTF-8 (`ensure_ascii=False`) et le vrai board contient
# `←`. Un `run()` qui décode selon la locale levait `UnicodeDecodeError` : faux
# `board illisible`, trace hors slot au lieu de la trace de la tâche running.
fire_stub_hostile utf8
T9="$STUB_DIR/.agents/state/local/binome/T-00000009.critic-opus.json"
if [ -f "$STUB_SLOT" ]; then
  ko "board UTF-8 : trace hors slot, motif « $(motif_de "$STUB_SLOT") » — décodage selon la locale"
elif [ -f "$T9" ] && [ "$(motif_de "$T9")" = "-" ]; then
  ok "board UTF-8 sous locale C : trace normale sur T-00000009"
else
  ko "board UTF-8 sous locale C : aucune trace sur T-00000009"
fi

echo "=== (l) LIGNE running SANS id : la ligne saine reste tracée ========="
# `t["id"]` sans garde levait `KeyError` sur `{"state":"running"}` — avalé par
# le hook, donc la trace de la ligne SAINE perdue ; un `id` vide écrivait
# `.critic-opus.json`, nom que la garde d'affirmation compte.
fire_stub sans_id
SID_DIR="$STUB_DIR/.agents/state/local/binome"
SID_VUS="$(ls "$SID_DIR" 2>/dev/null | tr '\n' ' ')"
if [ "$SID_VUS" = "T-00000009.critic-opus.json " ]; then
  ok "ligne sans id / id vide : seule T-00000009 est tracée"
else
  ko "ligne sans id / id vide : traces « $SID_VUS » au lieu de T-00000009 seule"
fi

echo "=== (m) agent_chrono.py ABSENT ou QUI LÈVE : la charge reste {sha, at, portee}"
# T-01M55Z3ZCS34CDR2EQN1CEBHR7 : le chrono se charge depuis l'OUTILLAGE, SOUS `try`
# (chargement ET appel). Le kit factice ne porte pas le module ; on y pose
# ensuite un module qui lève à l'import. Dans les deux cas la trace DOIT s'écrire,
# et sa forme rester exactement celle d'avant le chrono — sinon un chargeur sorti
# du `try` coûterait la trace, donc la clôture.
cles_de() { "$PY" -c 'import json,sys; print(" ".join(sorted(json.load(open(sys.argv[1], encoding="utf-8")))))' "$1" 2>/dev/null; }
for mode in absent leve; do
  rm -f "$STUBKIT/.agents/bin/agent_chrono.py"
  [ "$mode" = leve ] && printf 'raise RuntimeError("casse")\n' > "$STUBKIT/.agents/bin/agent_chrono.py"
  STUB_DIR="$TMP/stub-chrono-$mode"; mkdir -p "$STUB_DIR"; portee_stub "$STUB_DIR"
  printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus","agent_id":"aid-m"}' \
    | CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB=running bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
  RC=$?
  TM="$STUB_DIR/.agents/state/local/binome/T-00000009.critic-opus.json"
  if [ "$RC" -eq 0 ] && [ "$(cles_de "$TM")" = "at portee sha" ]; then
    ok "module $mode : trace écrite, charge exactement {sha, at, portee}"
  else
    ko "module $mode : rc=$RC, clés « $(cles_de "$TM") » au lieu de « at portee sha »"
  fi
done

echo "=== (n) DÉPART CONNU : la charge porte aid et duration_ms ============="
# Le vrai module, un départ de l'aid posé 4 s plus tôt dans le journal (forme du
# contrat, écrite ici en dur) : la trace du critique porte sa durée.
STUB_DIR="$TMP/stub-chrono-vrai"; mkdir -p "$STUB_DIR/.agents/state/local"; portee_stub "$STUB_DIR"
cp "$KIT/.agents/bin/agent_chrono.py" "$STUBKIT/.agents/bin/agent_chrono.py"
"$PY" -c 'import json,time; print(json.dumps({"ev":"start","aid":"aid-n","agent":"critic-opus","ts":int(time.time()*1000)-4000}))' \
  > "$STUB_DIR/.agents/state/local/agent-chrono.jsonl"
printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus","agent_id":"aid-n"}' \
  | CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB=running bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
TN="$STUB_DIR/.agents/state/local/binome/T-00000009.critic-opus.json"
if "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert d["aid"]=="aid-n" and d["duration_ms"]>=4000, d' "$TN" 2>/dev/null
then ok "départ connu : la trace porte aid et duration_ms"
else ko "départ connu : trace « $(cat "$TN" 2>/dev/null) » sans aid ou sans durée"; fi

echo "=== (o) PORTÉE HORS FOCUS : ignorée, la running n'est pas tracée ====="
# Le focus du clone a quitté la portée déclarée (T-01M5F728FGJ43QJX1RJKTWWKRB) : la portée
# est IGNORÉE, la trace part sous le nom réservé et ne crédite personne.
STUB_DIR="$TMP/stub-hors-focus"; mkdir -p "$STUB_DIR"; portee_stub "$STUB_DIR" T-00000008
printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}' \
  | CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB=running bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
TO="$STUB_DIR/.agents/state/local/binome"
if [ ! -f "$TO/T-00000009.critic-opus.json" ] && [ "$(motif_de "$TO/_sans-slot.critic-opus.json")" = "portée hors focus" ]
then ok "hors focus : aucune trace sur T-00000009, motif « portée hors focus »"
else ko "hors focus : traces « $(ls "$TO" 2>/dev/null | tr '\n' ' ') »"; fi

echo "=== (p) MEMBRE CONSOMMÉ : la running n'est pas tracée ================"
# Le seul membre de la portée active est déjà consommé (son `done` a eu lieu) : le traceur
# ne crédite plus personne, la trace part sous le nom réservé (C-K2, mutant X2d).
STUB_DIR="$TMP/stub-consomme"; mkdir -p "$STUB_DIR"; portee_stub "$STUB_DIR" T-00000009 '"T-00000009"'
printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}' \
  | CLAUDE_PROJECT_DIR="$STUB_DIR" BT_STUB=running bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
TP="$STUB_DIR/.agents/state/local/binome"
if [ ! -f "$TP/T-00000009.critic-opus.json" ] && [ "$(motif_de "$TP/_sans-slot.critic-opus.json")" = "portée consommée" ]
then ok "membre consommé : aucune trace sur T-00000009, motif « portée consommée »"
else ko "membre consommé : traces « $(ls "$TP" 2>/dev/null | tr '\n' ' ') »"; fi

echo "=== (q) RACINE PRINCIPALE : mêmes contrôles que racine_principale ===="
# T-01M5F728FGJ43QJX1RJKTWWKRB (F5) : un VRAI worktree lit focus et portée au dépôt
# principal ; un lien retour périmé, un gitdir hors de `<commun>/worktrees/` ou un `.git`
# lien symbolique se replient sur le clone — là où `tasks.py` les a posés. Le principal
# du repli ne porte AUCUNE portée : lu à tort, la trace part sous le nom réservé.
git_q() { git -c user.email=b@b -c user.name=b "$@" >/dev/null 2>&1; }
fire_q() { # <clone>
  printf '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}' \
    | CLAUDE_PROJECT_DIR="$1" BT_STUB=running bash "$STUBKIT/.claude/hooks/binome-trace.sh" >/dev/null 2>&1
  RC=$?
}
QV="$TMP/q-vrai-principal"; QR="$TMP/q-repli-principal"
for d in "$QV" "$QR"; do git_q init -q "$d"; git_q -C "$d" commit -q --allow-empty -m socle; done
portee_stub "$QV"
git_q -C "$QV" worktree add -q --detach "$TMP/q-vrai"
for n in perime hors lien-cible; do git_q -C "$QR" worktree add -q --detach "$TMP/q-$n"; done
for n in perime hors lien; do mkdir -p "$TMP/q-$n"; portee_stub "$TMP/q-$n"; done
# lien retour périmé : `<gitdir>/gitdir` désigne un autre `.git`
printf '%s\n' "$TMP/ailleurs/.git" > "$QR/.git/worktrees/q-perime/gitdir"
# gitdir hors de `<commun>/worktrees/` : même profondeur, lien retour et commondir intacts
mkdir -p "$QR/.git/autres"; mv "$QR/.git/worktrees/q-hors" "$QR/.git/autres/q-hors"
printf 'gitdir: %s\n' "$QR/.git/autres/q-hors" > "$TMP/q-hors/.git"
# `.git` lien symbolique vers le `.git` d'un vrai worktree du principal sans portée
ln -s "$TMP/q-lien-cible/.git" "$TMP/q-lien/.git" 2>/dev/null
fire_q "$TMP/q-vrai"
[ "$RC" -eq 0 ] && [ -f "$TMP/q-vrai/.agents/state/local/binome/T-00000009.critic-opus.json" ] \
  && ok "vrai worktree : portée lue au dépôt principal, trace sur T-00000009" \
  || ko "vrai worktree : rc=$RC, traces « $(ls "$TMP/q-vrai/.agents/state/local/binome" 2>/dev/null | tr '\n' ' ') »"
for n in perime hors lien; do
  if [ "$n" = lien ] && [ ! -L "$TMP/q-lien/.git" ]; then
    echo "  SKIP — .git lien symbolique : ln -s indisponible sur ce poste"; continue
  fi
  fire_q "$TMP/q-$n"
  QB="$TMP/q-$n/.agents/state/local/binome"
  [ "$RC" -eq 0 ] && [ -f "$QB/T-00000009.critic-opus.json" ] && [ ! -f "$QB/_sans-slot.critic-opus.json" ] \
    && ok "worktree $n : repli sur le clone, trace sur T-00000009" \
    || ko "worktree $n : rc=$RC, traces « $(ls "$QB" 2>/dev/null | tr '\n' ' ') » — portée lue au principal"
done
# LES DEUX PORTS PYTHON (identiques octet pour octet) : `principale()` rend le même verdict.
for hote in .codex .gemini; do
  port="$KIT/$hote/hooks"
  for n in vrai perime hors lien; do
    [ "$n" = lien ] && [ ! -L "$TMP/q-lien/.git" ] && continue
    attendu="$(cd "$TMP/q-$n" && pwd -P)"; [ "$n" = vrai ] && attendu="$(cd "$QV" && pwd -P)"
    vu="$(PYTHONDONTWRITEBYTECODE=1 "$PY" -B -c 'import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import binome_trace
print(binome_trace.principale(Path(sys.argv[2])).resolve())' "$port" "$TMP/q-$n" 2>/dev/null)"
    [ "$vu" = "$attendu" ] \
      && ok "port $hote worktree $n : principale attendue" \
      || ko "port $hote worktree $n : principale « $vu » au lieu de « $attendu »"
  done
done

echo "================================================================"
echo "Resume : $pass PASS / $fail FAIL"
[ "$fail" -eq 0 ]
