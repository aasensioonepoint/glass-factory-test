#!/usr/bin/env bash
# SubagentStop — TRACE MÉCANIQUE DU BINÔME DE CLÔTURE (T-00000586).
#
# POURQUOI CE FICHIER EXISTE. La règle « aucune tâche n'est marquée terminée sans
# une revue critique » (UN critique depuis S-00004500) est la plus lourde du dépôt et la
# seule qui ne soit tenue par RIEN : `.agents/skills/task-board/SKILL.md` l'écrit
# lui-même — « le refus est DOCTRINAL et non mécanique ». Une règle tenue par la
# mémoire d'un orchestrateur est une règle qu'on oublie, et le pilote la réclame
# à chaque clôture. Demande du 2026-09-13, formulée comme un agacement, et c'en
# est un légitime.
#
# CE QU'IL NE FAIT PAS, ET NE FERA JAMAIS : lancer les critiques. AUCUN hook de
# ce dépôt n'invoque de modèle — `.agents/evals/test_hooks_zero_llm.py` le
# prouve et c'est un invariant. Ce script MESURE ce qui a tourné ; c'est
# `tasks.py done` qui REFUSE.
#
# LE SIGNAL, ET C'EST LUI QUI REND LA CHOSE POSSIBLE. La charge `SubagentStop`
# porte `agent_type` — le NOM de la def qui vient de finir. Le dépôt sait donc,
# sans aucun modèle et sans croire personne sur parole, que `critic-opus` et
# `critic-fable` ont réellement tourné. Même champ que celui que
# `log-agent-usage.sh` consomme déjà pour les tokens, sur le même événement.
#
# CE QUE ÇA EMPÊCHE, ET CE QUE ÇA N'EMPÊCHE PAS — dit ici plutôt que découvert.
# Ça empêche d'OUBLIER. Ça n'empêche pas de TRICHER : la trace est un fichier
# d'état ordinaire, qu'un agent déterminé peut écrire à la main. La fermer
# vraiment demanderait une signature que rien dans ce dépôt ne porte. Le mode de
# défaillance visé est l'oubli, qui est celui qu'on a MESURÉ.
#
# ADVISORY, TOUJOURS `exit 0`. Un hook `SubagentStop` qui échoue fermé coûterait
# un sous-agent ; le refus, lui, vit dans `tasks.py`, au seul endroit que toutes
# les portes traversent.
INPUT=$(cat 2>/dev/null || true)
[ -n "$INPUT" ] || exit 0

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
[ -n "$PY" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-.}"
# L'OUTILLAGE EST ANCRÉ AU SCRIPT, l'ÉTAT suit CLAUDE_PROJECT_DIR — même
# séparation que context-retro.sh, et pour la même raison mesurée : résoudre
# `tasks.py` depuis la racine d'état rend un board VIDE en silence.
KIT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHONDONTWRITEBYTECODE=1 "$PY" -B - "$INPUT" "$ROOT" "$KIT" <<'PYEOF' 2>/dev/null
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

try:
    payload = json.loads(sys.argv[1])
    root = Path(sys.argv[2])
    kit = Path(sys.argv[3])
except Exception:
    sys.exit(0)

# LE VOCABULAIRE EST CLOS, et il vit ici ET dans `tasks.py` — les deux moitiés
# d'un même contrat. Un banc lie les deux listes pour qu'elles ne divergent pas :
# une trace écrite sous un nom que le refus ne reconnaît pas serait une preuve
# invisible, donc une clôture refusée sans raison compréhensible.
CRITIQUES = ("critic-opus", "critic-fable", "critic-sonnet-max")

# LES DEUX GRAPHIES, ET CE N'EST PAS DE LA COURTOISIE (T-00000589). Le frère de
# ce script sur le même événement — `log_agent_usage.py`, enregistré par Codex,
# Kimi, Gemini et Copilot — lit `agentType` OU `agent_type` depuis toujours,
# parce que les hôtes ne nomment pas ce champ pareil. Celui-ci ne lisait que le
# snake_case : sur un hôte qui envoie du camelCase, il sortait 0 en SILENCE, donc
# aucune trace, donc `tasks.py done` refusait toute clôture et la seule issue
# restait la sortie tracée. Une garde qu'on ne peut franchir que par son
# échappatoire ne garde rien — et l'écart aurait été invisible, puisqu'un hook
# qui ne trouve pas son champ se tait exactement comme un sous-agent non critique.
agent = str(payload.get("agent_type") or payload.get("agentType") or "").strip()
if agent not in CRITIQUES:
    sys.exit(0)


# `None` VEUT DIRE « PAS DE RÉPONSE », et c'est un correctif (T-00000845).
# La première rédaction rendait `""` sur exception, sur timeout de 5 s, ET la
# stdout vide d'une commande sortie non-zéro ; l'appelant la complétait en
# `"[]"`, donc un board ILLISIBLE se lisait « board vide » et la trace de repli
# disait `aucune running` — faux diagnostic « la tâche ne tournait pas », alors
# qu'une tâche pouvait parfaitement tourner. Une réponse vide et une absence de
# réponse ne sont pas la même mesure : rc ≠ 0, timeout ou exception → `None`.
#
# DÉCODAGE EXPLICITE EN UTF-8 (T-00000845, relevé du binôme). `tasks.py` écrit
# de l'UTF-8 (`ensure_ascii=False`) et le vrai board porte `←`. `text=True`
# sans `encoding` décode selon la LOCALE — cp1252 sous Windows, où 0x90 n'est
# pas défini : `UnicodeDecodeError`, donc `None`, donc « board illisible » À
# TORT et `done` refusé après une revue réelle. `errors="replace"` : un octet
# invalide abîme un libellé, il ne doit pas rendre le board illisible.
def run(*args):
    try:
        p = subprocess.run(args, cwd=str(root), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=5)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip()


# LES TÂCHES VISÉES SONT LES MEMBRES DE LA PORTÉE DE REVUE (T-01M5F728FGJ43QJX1RJKTWWKRB,
# S-01M5E50ABADJA72966YQF4J285). Plusieurs `running` coexistent désormais (deux sessions,
# deux sujets) : tracer sur chacune ferait créditer A2 par la revue de A1. On ne trace
# donc que sur les membres NON consommés et non clos de la portée ACTIVE — le
# `review-scope.json` du dépôt PRINCIPAL dont le `focus` est celui de `focus.json` (hors
# focus, la portée est IGNORÉE) — et chaque trace porte `portee` = son `declared_at`, que
# `tasks.py done` compare : une nouvelle déclaration invalide les anciennes traces. Les
# membres sont relus contre le board : un id que le board ne porte pas ne nomme aucun
# fichier. Sans portée active, la trace part sous le nom réservé ci-dessous, qui ne
# crédite personne.
#
# ET SANS PORTÉE NI `running`, ON ÉCRIT QUAND MÊME — sous un nom réservé. La
# première rédaction sortait ici en disant « une trace sans destinataire ne
# prouverait rien et polluerait ». C'était vrai du SEUL consommateur qu'elle
# connaissait, `tasks.py done`, qui est indexé par identifiant de tâche. Ça a
# cessé de l'être avec la garde d'affirmation (T-00000602), qui mord sur
# `tasks.py new` — un geste qui PRÉCÈDE tout `start`.
#
# SCÉNARIO MESURÉ PAR LE BINÔME DE CLÔTURE : session neuve, aucune tâche
# `running`, `tasks.py new`, le Stop bloque, le binôme est lancé, AUCUNE trace
# n'est écrite, le Stop REBLOQUE « 0 critique ». La seule issue devenait la
# sortie tracée À CHAQUE FOIS — c'est-à-dire une garde DÉCORATIVE, et son
# message « l'hôte écrit la trace tout seul » était FAUX dans ce cas précis.
# Masqué jusqu'ici par un chantier qui se trouvait être `running`.
#
# `_sans-slot` N'EST PAS UN IDENTIFIANT DE TÂCHE, et c'est ce qui rend le repli
# sûr : la garde d'affirmation lit TOUS les `*.<critique>.json` du dossier et ne
# lit que le dernier segment du nom, donc elle le voit ; `tasks.py done`
# cherche `<tid>.<critique>.json` pour un `tid` réel, donc il ne le voit jamais
# et aucune clôture ne peut s'en réclamer. Le tiret bas en tête le distingue à
# l'œil d'un `T-…` dans un listing de répertoire.
# PAS DE REPLI `or "[]"` ICI, et c'est le cœur du correctif T-00000845 : c'est
# lui qui changeait un `None` (pas de réponse) en board vide, donc en
# `lisible=True`. `tasks.py list --json` rend `[]` LUI-MÊME sur un board vide ;
# une stdout vide à rc 0 n'est donc pas un board vide, c'est une anomalie, et
# `json.loads("")` la range avec les illisibles. Un JSON qui n'est pas une liste
# aussi : itérer un dict ne donnerait « aucune running » que par accident.
brut = run(sys.executable, "-B", str(kit / ".agents" / "bin" / "tasks.py"),
           "--root", str(root), "list", "--json")
try:
    if brut is None:
        raise ValueError("tasks.py list : rc non nul, expiré ou injoignable")
    board = json.loads(brut)
    if not isinstance(board, list):
        raise ValueError("tasks.py list : JSON qui n'est pas une liste")
    lisible = True
except Exception:
    board, lisible = [], False
# L'`id` EST GARDÉ (relevé du binôme, T-00000845) : `t["id"]` nu levait
# `KeyError` sur une ligne `running` sans `id` — avalé plus haut, donc la trace
# de la ligne SAINE perdue — et un `id` vide écrivait `.critic-opus.json`, nom
# que la garde d'affirmation compte puisqu'elle ne lit que le dernier segment.
lignes = [t for t in board
          if isinstance(t, dict) and isinstance(t.get("id"), str) and t["id"]]
running = [t["id"] for t in lignes if t.get("state") == "running"]


# LA RACINE PRINCIPALE, LUE SUR LE DISQUE SANS GIT (mêmes contrôles que
# `racine_principale`, `tasks_requetes.py`) : `<root>/.git` FICHIER, jamais un lien
# symbolique → son `gitdir`, dossier DIRECT de `<commun>/worktrees/`, dont le lien retour
# `<gitdir>/gitdir` désigne `<root>/.git` → le parent du `.git` commun. Sinon — `.git`
# dossier, absent, lien, illisible, pointeur forgé ou lien retour périmé — `root`
# lui-même : là où `tasks.py` a posé focus et portée. Aucun sous-processus : l'unique
# enfant Python reste l'appel `tasks.py list` ci-dessus.
def principale(base):
    try:
        point = base / ".git"
        if point.is_symlink() or not point.is_file():
            return base
        ligne = point.read_text(encoding="utf-8").strip()
        if not ligne.startswith("gitdir:"):
            return base
        gitdir = Path(ligne[len("gitdir:"):].strip())
        gitdir = (gitdir if gitdir.is_absolute() else base / gitdir).resolve()
        commun = Path((gitdir / "commondir").read_text(encoding="utf-8").strip())
        commun = (commun if commun.is_absolute() else gitdir / commun).resolve()
        retour = Path((gitdir / "gitdir").read_text(encoding="utf-8").strip())
        retour = (retour if retour.is_absolute() else gitdir / retour).resolve()
        vrai = gitdir.parent == commun / "worktrees" and retour == point.resolve()
    except (OSError, RuntimeError, ValueError):
        return base
    return commun.parent if vrai and commun.name == ".git" and commun.parent.is_dir() else base


def portee_active(base):
    local = principale(base) / ".agents" / "state" / "local"
    try:
        focus = json.loads((local / "focus.json").read_text(encoding="utf-8"))
        portee = json.loads((local / "review-scope.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "aucune portée"
    if not (isinstance(focus, dict) and isinstance(portee, dict)
            and isinstance(portee.get("focus"), str) and isinstance(portee.get("declared_at"), str)
            and isinstance(portee.get("members"), list) and isinstance(portee.get("consumed"), list)):
        return None, "aucune portée"
    if focus.get("task_id") != portee["focus"]:
        return None, "portée hors focus"
    return portee, None


portee, motif_portee = portee_active(root) if lisible else (None, None)
cibles = [t["id"] for t in lignes if portee is not None and t.get("state") != "done"
          and t["id"] in portee["members"] and t["id"] not in portee["consumed"]]
# LE MOTIF DU REPLI EST ÉCRIT, sinon deux causes très différentes se lisent
# pareil — relevé du binôme. « Aucune tâche ne tourne » est le cas NOMINAL d'une
# session neuve ; « le board est illisible » est un incident — `tasks.py list`
# sorti non-zéro, expiré à 5 s, injoignable, ou une sortie qui n'est pas une
# liste JSON — pendant lequel une tâche pouvait parfaitement tourner. Les deux
# produisent la même trace ; seule la charge les distingue, et sans elle
# personne ne saurait qu'il y a eu incident. Un rc non nul ou un timeout ne se
# lit donc JAMAIS `aucune running` (l'ancien repli `or "[]"` le faisait). Une
# tâche tourne mais aucune portée active ne nomme de membre ouvert : `aucune
# portée`, `portée hors focus` ou `portée consommée` — le remède est
# `tasks.py review-scope`, jamais une trace sur la `running`.
motif = None
if not cibles:
    if not lisible:
        motif = "board illisible"
    elif not running:
        motif = "aucune running"
    else:
        motif = motif_portee or "portée consommée"
    cibles = ["_sans-slot"]

sha = run("git", "rev-parse", "--short", "HEAD") or "?"
quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# LE CHRONO RÉEL, EN PLUS ET JAMAIS À LA PLACE (T-01M55Z3ZCS34CDR2EQN1CEBHR7) :
# `aid`, `duration_ms`, `tokens` du frère `agent_chrono.py` de l'OUTILLAGE, clés
# posées SEULEMENT quand elles sont connues. CHARGEMENT ET APPEL SOUS `try` : ce
# traceur est une garde armée chez l'adoptant — module absent, cassé ou qui lève,
# la charge reste exactement `{sha, at}` (+ `motif`), et la trace s'écrit quand même.
chrono = {}
try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_cadre_agent_chrono_binome", kit / ".agents" / "bin" / "agent_chrono.py")
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
    _c = _mod.chrono_de(root, payload)
    chrono = {k: _c[k] for k in ("aid", "duration_ms", "tokens") if k in _c}
except Exception:
    chrono = {}
dossier = root / ".agents" / "state" / "local" / "binome"
try:
    dossier.mkdir(parents=True, exist_ok=True)
except OSError:
    sys.exit(0)

# UN FICHIER PAR CRITIQUE, ET C'EST UN CORRECTIF DU BINÔME DE CLÔTURE.
# La première version tenait UN fichier par tâche, lu-modifié-réécrit à chaque
# passage. Or la doctrine lançait deux critiques EN PARALLÈLE avant S-00004500, et
# un critique et son repli peuvent encore s'arrêter dans la même fenêtre : deux
# arrêts lisaient tous deux l'état vide, et le second écrasait le premier — une
# seule entrée, donc une clôture REFUSÉE après une revue réellement faite. Le
# mécanisme aurait échoué exactement sur le
# cas qu'il existe pour servir, et l'échec aurait eu l'air d'un oubli.
#
# Ici chaque critique écrit SON fichier, et rien ne lit avant d'écrire : plus de
# course possible, et un fichier tronqué ne coûte que sa propre entrée. Écraser
# reste voulu — ce qui compte est le DERNIER passage de chaque critique, pas son
# histoire ; un empilement ferait qu'un binôme d'il y a trois cycles vaudrait
# encore preuve aujourd'hui.
for tid in cibles:
    charge = {"sha": sha, "at": quand, **chrono}
    if motif:
        charge["motif"] = motif
    else:
        charge["portee"] = portee["declared_at"]
    try:
        (dossier / f"{tid}.{agent}.json").write_text(
            json.dumps(charge, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        pass
sys.exit(0)
PYEOF
exit 0
