#!/usr/bin/env bash
# Stop — REFUS D'UNE AFFIRMATION DURABLE NON VÉRIFIÉE (T-00000602).
#
# POURQUOI CE FICHIER EXISTE. Le 2026-09-13, l'orchestrateur a mesuré CINQ
# chemins et UNE ligne de `pyproject.toml`, puis a annoncé au pilote un défaut
# systémique — « un adoptant qui installe la wheel ne reçoit ni dashboard ni
# skills », « ce défaut n'est porté par personne ». Les DEUX conclusions étaient
# fausses, établies par revue adversariale que le pilote a dû RÉCLAMER. L'erreur
# avait déjà été propagée dans trois tickets neufs. Demande pilote : « avant
# d'affirmer ou de prendre des décisions de ce genre, mets en place un hook qui
# mandatera deux agents pour aller vérifier. »
#
# CE QU'IL NE FAIT PAS, ET NE FERA JAMAIS : mandater les deux agents. AUCUN hook
# de ce dépôt n'invoque de modèle — `.agents/evals/test_hooks_zero_llm.py` le
# prouve et porte même `test_reject_bootstrap_llm_injection`. Ce script CONSTATE
# l'artefact que la revue laisse derrière elle ; il ne la déclenche pas. C'est la
# leçon de `T-00000586`, reprise telle quelle.
#
# L'ARTEFACT. `SubagentStop` fait écrire à l'HÔTE
# `.agents/state/local/binome/<tâche>.<def>.json`, contenu `{"at": <ISO8601 UTC>,
# "sha": <sha court>}`. Écrit par l'hôte, jamais par l'agent qui se relirait
# lui-même : c'est ce qui le rend probant.
#
# LES QUATRE SURFACES QUI MORDENT — décision pilote du 2026-09-13, « elle doit
# mordre sur les 3 surfaces », étendue par S-00003374 (T-00001064) :
#   1. le BOARD, et seulement quand une tâche est AJOUTÉE (un `stage` ou un
#      `done` ne sont pas des affirmations neuves) ;
#   2. `PLAN-ETAT.md` ;
#   3. les surfaces de DOCTRINE nommées dans SURFACES_DOCTRINE ci-dessous ;
#   4. les FICHIERS DE REPRISE DE LOT (motifs REPRISES ci-dessous), non suivis
#      compris : `docs/interne/chantier/lots/` et le prompt vivant de
#      `reprises/` n'existent que dans le kit (`docs/interne/` ne voyage pas) ;
#      `docs/tasks/LOT-*-REPRISE.md` voyage.
#
# L'ANCRAGE EST LE TAMPON DE PORTE, ET C'EST LE CŒUR DU DESIGN. Exiger que la
# revue soit POSTÉRIEURE AU TRAVAIL serait le piège mesuré sur `T-00000592` : le
# binôme passe AVANT la porte, et l'on CORRIGE ses constats APRÈS lui — donc la
# surface est toujours plus récente que la trace, et la garde refuserait le cas
# NOMINAL. On demande donc : « depuis le CYCLE PRÉCÉDENT, `BINOME_MIN` critique(s)
# DISTINCT(s) — UN depuis S-00004500 — ont-ils tourné » — le diff part de la DERNIÈRE porte verte, la
# fenêtre des critiques de l'AVANT-DERNIÈRE (option A du 22/09), lue par la
# MÊME définition que `tasks.py::cycle_precedent` (S-00001884, D1). Les bornes
# existent déjà, rien n'est inventé. DEUX ÉCARTS AVEC LA JUMELLE sont ASSUMÉS et
# écrits dans `horodatage_stamp` (décision pilote par défaut du 23/09) : faute de
# deux verts, ici une fenêtre de 12 h et au `done` une borne d'ÂGE de 24 h sur
# l'emprunt (T-00000846 — avant, aucune) : deux fenêtres, pas la même ; et le binôme d'un
# cycle couvre les écritures du cycle suivant. UN TROISIÈME, NON ARBITRÉ : un `at`
# malformé (sans `Z`) à l'avant-dernier vert fait retomber la garde sur 12 h,
# quand `done` périme encore par comparaison de chaînes contre ce même `at`.
#
# ET UNE GARDE ARMÉE QUI NE PEUT PAS LIRE SON INFRASTRUCTURE REFUSE (S-00001884,
# D2) : voir `Illisible` et `_refus_de_panne` ci-dessous. Désarmée, elle ne lit
# rien et ne refuse rien.
#
# CE QU'IL N'ATTRAPE PAS — écrit ici plutôt que laissé croire.
#   · Un hook lit des OCTETS. Il ne distingue pas une AFFIRMATION d'une
#     DESCRIPTION, et ne le fera jamais. Il mord sur l'ÉCRITURE, pas sur la
#     prétention de vérité.
#   · La faute d'origine s'est produite EN CONVERSATION, où aucun hook n'existe.
#     Cette garde attrape la PROPAGATION vers une surface durable, jamais
#     l'ÉMISSION. Une affirmation dite et jamais écrite passe entière.
#   · Elle compte des NOMS de critiques dans le cycle, PAS une couverture : un
#     critique tombé sur une AUTRE TÂCHE la satisfait. Elle prouve
#     qu'une revue critique a tourné depuis la dernière porte, jamais qu'elle
#     portait sur CE qui vient d'être écrit.
#   · Elle empêche d'OUBLIER, pas de TRICHER : la trace est un fichier d'état
#     ordinaire. Le mode de défaillance visé est celui qu'on a MESURÉ.
#   · TROU CONNU, ET IL RESTE OUVERT : un tour qui suit le blocage d'un AUTRE
#     hook `Stop` porte lui aussi `stop_hook_active=true` et échappe donc à
#     cette garde. `context-retro.sh` est précisément dans ce cas, et il DEMANDE
#     un `tasks.py new`. Le fermer exige de distinguer « mon propre replay »
#     d'un replay tiers, donc une clé de session de plus et le risque de boucle
#     qui va avec — c'est un arbitrage, pas un patch, et il est porté au board.
#   · TROIS HÔTES SUR SIX, et c'est une couverture INÉGALE, pas une
#     couverture. Claude Code (`Stop`, `.claude/settings.json`) ; depuis
#     l'alignement des hôtes (2026-10-12, lot L2), Codex (`Stop`,
#     `.codex/hooks.json`) et Copilot (`agentStop`,
#     `.github/hooks/agent-guardrails.json`) appellent CE MÊME fichier, racine en
#     argument 1. Hors Claude, le canal `decision:block` et `stop_hook_active`
#     sont MESURÉS sur un canari (Codex X3/X3b, Copilot P3), PAS sur cette garde
#     lancée par l'hôte. Copilot émet `agentStop` aussi pour un SOUS-AGENT :
#     la jambe `agent-guardrails.json` l'exempte plus bas (`sous_agent_copilot`).
#     Copilot exécute AUSSI le `Stop` de `.claude/settings.json`, MESURÉ (P4,
#     2026-10-13, Copilot CLI 1.0.95, macOS) : il tire DEUX fois (fin du
#     sous-agent, puis racine), charge snake_case sans marqueur d'hôte, avec un
#     `transcript_path` sous `~/.copilot/session-state/`. Cette jambe-là s'y TAIT
#     en fin de sous-agent (`copilot_par_le_registre_claude`), et à la racine
#     seulement si `.github/hooks/agent-guardrails.json` câble cette garde sur
#     `agentStop` (qui juge alors la racine) ; sinon elle juge la racine
#     elle-même. NON MESURÉ : Windows, une autre version de Copilot, un état
#     Copilot relocalisé, un sous-agent qui ÉCRIT une affirmation, une reprise de
#     session Copilot (`--resume`/`--continue`).
#     Gemini CLI, Antigravity et Kimi : rien.
#
# LE CANAL DE RETOUR EST `decision:block`, MESURÉ ET NON SUPPOSÉ. Sur `Stop`,
# `stderr + exit 2` n'est PAS lu : `context-retro.sh` l'écrit — « le SEUL canal
# de retour est decision:block » — et c'est ce que ce script émet, avec exit 0.
# Une garde dont le canal est ignoré n'existe pas (L-00000136).
#
# ET L'HÔTE REJOUE UN `Stop` DÉJÀ BLOQUÉ : sans le test `stop_hook_active`
# ci-dessous, la garde boucle à l'infini. Elle ne se redéclenche donc pas DANS
# LE TOUR qu'elle vient de bloquer — mais elle REBLOQUERA au tour suivant tant
# que la surface reste non revue, et c'est voulu. (La rédaction précédente
# disait « au plus une fois » : c'était faux, et ça aurait fait lire un second
# refus légitime comme une panne.)
#
# DÉSARMÉE PAR DÉFAUT chez l'adoptant : sans
# `.agents/state/gates/AFFIRMATION_REQUIRED`, ce script rend zéro octet.
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
# Pas de Python : ADVISORY. Un Stop qui échoue fermé sur l'absence d'un
# interpréteur enfermerait la session, ce qui est pire que la règle non tenue.
[ -n "$PY" ] || exit 0

# Sous Claude Code, la racine vient de l'HÔTE (`CLAUDE_PROJECT_DIR`). Le premier
# argument la surcharge, et il sert DEUX fois : au BANC (sans lui, la garde ne
# serait éprouvable que sur l'arbre réel, donc pas du tout) et, en production,
# aux registres Codex et Copilot, qui n'exportent pas `CLAUDE_PROJECT_DIR` et
# passent la racine du dépôt. Sans l'un ni l'autre, repli sur `.` : la jambe
# Windows de Codex s'y fie, `pyrun.ps1` lançant bash depuis la racine.
RACINE_ARG="${1-}"
[ -n "$RACINE_ARG" ] || RACINE_ARG="${CLAUDE_PROJECT_DIR-}"
[ -n "$RACINE_ARG" ] || RACINE_ARG="."

# LA CHARGE PASSE EN ARGUMENT, JAMAIS PAR STDIN — même choix que
# `binome-trace.sh:68`, et ce n'est pas cosmétique : `python -` lit le PROGRAMME
# sur stdin, donc le heredoc ci-dessous l'y écrase. Une première rédaction
# pipait la charge dans le même stdin ; `sys.stdin.read()` rendait alors une
# chaîne VIDE, la charge était lue comme `{}`, et le garde-fou anti-boucle
# `stop_hook_active` ne voyait jamais rien. Trouvé par le banc, cas 10.
"$PY" -B - "$INPUT" "$RACINE_ARG" <<'PYEOF'
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

BRUT = sys.argv[1] if len(sys.argv) > 1 else "{}"
RACINE = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else ".")

# Les surfaces de DOCTRINE. Une liste NOMMÉE, jamais un motif : un motif large
# ferait mordre la garde sur du travail ordinaire, et une garde qui mord à tort
# est désarmée dans la semaine.
# SEPT ICI, MAIS QUATRE SEULEMENT VOYAGENT — et le dire est le point (relevé du
# binôme, 2026-09-14). Les trois dernières sont `strip:` dans `.template-exclude`
# (`strip: .agents/evals/classification_rules.py`, `strip: docs/interne/`,
# `strip: docs/PROMPT-refonte-packaging-cadre.md`), donc ABSENTES de tout dépôt adoptant. La garde n'y
# produit pas de faux positif — un fichier qui n'existe pas ne change jamais —
# mais cette liste ANNONÇAIT une couverture de sept surfaces là où l'adoptant n'en
# a que quatre. C'est la faute que la règle d'or nomme : une déclaration qui
# promet ce que le code ne tient pas empêche de voir l'écart.
#
# ON NE LES RETIRE PAS : sur CE dépôt elles sont la doctrine la plus lourde du
# chantier, et c'est précisément là qu'une affirmation non vérifiée coûte cher.
# Ce qui change, c'est qu'on ne peut plus lire « sept surfaces couvertes » sans
# lire aussi « dont trois n'existent que dans le kit ».
SURFACES_DOCTRINE = (
    # Voyagent : présentes chez tout adoptant.
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    # Depuis T-00000838, le détail de CLAUDE.md vit ici mot pour mot : le
    # sortir de la garde en même temps que de CLAUDE.md l'aurait soustrait à la
    # double vérification par un simple déménagement.
    "README-CLAUDE.md",
    # LES SKILLS N'Y SONT PAS, ET C'EST UNE DÉCISION PILOTE (2026-09-29,
    # T-00000838), pas un oubli : le détail d'AGENTS.md est parti dans douze
    # `.agents/skills/*/SKILL.md` (sections « Détail déplacé d'AGENTS.md »), mais
    # ces skills sont édités par du travail ORDINAIRE, et une garde qui mord à
    # tort est désarmée dans la semaine. Ce qui reste gardé : AGENTS.md, qui porte
    # la phrase actionnable de chaque règle (contrôle MANUEL en revue T-00000838,
    # non outillé) ; ce qui est parti est l'historique et la justification,
    # instantané mot pour mot de ec31545c.
    # NE VOYAGENT PAS — `strip:`, donc inertes hors du kit.
    "docs/PROMPT-refonte-packaging-cadre.md",
    "docs/interne/classification.md",
    ".agents/evals/classification_rules.py",
)
SURFACES_QUI_VOYAGENT = 4
# DEUX fichiers depuis le split du 2026-09-14, et c'est le point : `PLAN-ETAT.md`
# a ete coupe en une tete COURTE (injectee en entier, < 6 000 octets) et un
# `PLAN-ETAT-DETAIL.md` qui porte la file, les decisions closes, les leviers et
# les points ouverts. Garder le seul nom d'origine aurait fait du split une
# ECHAPPATOIRE : tout l'etat durable aurait migre dans un fichier que la garde ne
# regarde pas, et une affirmation non verifiee y serait passee sans binome.
PLAN_ETAT = ("PLAN-ETAT.md", "PLAN-ETAT-DETAIL.md")
# LES FICHIERS DE REPRISE DE LOT (S-00003374, T-00001064) : l'ÉTAT du chantier a
# quitté `PLAN-ETAT.md` pour eux. Ne pas les garder aurait refait du routeur une
# ÉCHAPPATOIRE, exactement comme le split du 14/09 l'aurait fait sans DÉTAIL :
# l'état aurait migré dans un fichier que la garde ne regarde pas. Des MOTIFS
# `fnmatch` et non une liste nommée : un fichier de reprise s'ouvre par lot, et
# un répertoire VIVANT (`lots/`) se garde par répertoire sans mordre sur les
# archives de `reprises/`.
# PORTÉE — `docs/interne/chantier/lots/` et le prompt vivant de `reprises/` sont
# sous `docs/interne/` (`strip:` : KIT SEULEMENT) ; `docs/tasks/LOT-*-REPRISE.md`
# est sous `docs/tasks/` (`keep:`) : il VOYAGE chez l'adoptant.
# LECTURE PROPRE À CETTE JAMBE (`suivis_reprise`, `non_suivis`), jamais par
# `modifies()` : non suivis COMPRIS, ignores personnels NEUTRALISÉS
# (`core.excludesFile` vers le néant ; `.gitignore` et `.git/info/exclude`
# restent obéis — le remède d'un faux positif est `.git/info/exclude`), `-z`.
# BORNES, écrites plutôt que découvertes :
#   (1) la garde compte des NOMS de critiques : sous la porte unique de fin de
#       lot (S-00003259), sa fenêtre contient presque toujours des critiques
#       d'AUTRES tâches. C'est `tasks.py done` (`binome_reprise_refusal`) qui
#       ancre la revue sur le CONTENU ;
#   (2) une reprise SUPPRIMÉE, ou RENOMMÉE hors des motifs sans successeur,
#       n'est pas relue (filtre d'existence) ;
#   (3) un fichier de reprise hors de ces motifs ET hors `lots/` échappe ;
#   (4) un git qui échoue POUR CETTE JAMBE SEULE (délai, panne entre deux
#       appels) la rend MUETTE — comme toute la garde l'est déjà quand
#       `modifies()` est None (advisory) : cette jambe est l'AVERTISSEUR,
#       `done` est la SERRURE, et lui refuse un git en échec.
REPRISES = (
    "docs/interne/chantier/lots/*",
    "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md",
    "docs/tasks/LOT-*-REPRISE.md",
)
# Le pathspec DÉRIVÉ des motifs (aucun second littéral à tenir) : la partie
# avant le premier `*`, coupée au dernier `/` ; un motif SANS `*` est un FICHIER
# NOMMÉ, gardé entier (un pathspec vide ferait rendre 128 à git).
SPEC = sorted({(p.split("*", 1)[0].rsplit("/", 1)[0] if "*" in p else p) or "."
               for p in REPRISES})
BOARD = ".agents/state/board/TASKS.json"
# LA FORME DOSSIER DU BOARD (T-00001012, BK-419, E-26) : un fichier par tâche,
# `<id>.json`, enveloppe de T-00001008. Domicile tranché par la décision pilote
# S-01M4N1G4VXD01A3W54Y9FR9856 (`board/tasks/`, à côté de `board/epics/`), que
# T-00001009 reprend ou modifie dans le même commit. Aucune parité à tenir
# ailleurs : Claude, Codex et Copilot appellent CE fichier, aucun hôte n'en a
# de copie.
BOARD_DOSSIER = ".agents/state/board/tasks"

ARME = os.path.join(RACINE, ".agents/state/gates/AFFIRMATION_REQUIRED")
SORTIE = os.path.join(RACINE, ".agents/state/gates/AFFIRMATION_SANS_BINOME")
JOURNAL = os.path.join(RACINE, ".agents/state/local/affirmation-sorties.log")
TRACES = os.path.join(RACINE, ".agents/state/local/binome")
# LE NOMBRE DE CRITIQUES DISTINCTS EXIGÉ (S-00004500, T-00001226) : DOUBLE TEXTUEL de
# `BINOME_MIN` dans `.agents/bin/tasks.py` — même nom, même valeur, liés par
# `.agents/evals/test_binome_min.py`. Les `< 2` sur des CYCLES n'en relèvent pas.
BINOME_MIN = 1
STAMP = os.path.join(RACINE, ".agents/state/local/VERIFY_STAMP")


def sortir(code=0):
    sys.exit(code)


try:
    charge = json.loads(BRUT or "{}")
except (ValueError, TypeError, RecursionError):
    # `RecursionError` : une charge imbriquée assez profond (mesuré : `'['*200000`,
    # 200 Ko, sous ARG_MAX) la lève, et elle PLANTAIT ici, AVANT le crochet — trace
    # sur stderr, stdout vide. Une charge illisible reste ADVISORY, comme un JSON
    # invalide : on ne bloque jamais sur une entrée qu'on n'a pas.
    sortir()
if not isinstance(charge, dict):
    sortir()

# L'hôte REJOUE un Stop déjà bloqué. Sans ceci, boucle infinie.
if charge.get("stop_hook_active"):
    sortir()

# COPILOT ÉMET `agentStop` AUSSI À LA FIN DE CHAQUE SOUS-AGENT — mesuré sur le
# canari P4 (2026-10-12), relevé par l'exec-critic du lot L2 de l'alignement des
# hôtes : la charge d'un sous-agent porte SON `sessionId` (l'`agentId` de son
# `subagentStop`) mais le `transcriptPath` de la session RACINE
# (`…/session-state/<id racine>/events.jsonl`) — même motif MESURÉ de nouveau le
# 2026-10-13 (P4, Copilot CLI 1.0.95, macOS). Cette garde juge la fin de tour
# de l'agent PRINCIPAL (sous Claude, `Stop` et non `SubagentStop`) : sans ce
# filtre elle bloquerait chaque sous-agent, critiques en lecture seule compris,
# qui ne peuvent ni lancer `critic-opus` ni écrire la sortie tracée. Ce filtre-ci
# ne vaut que pour la jambe NATIVE (marqueur `copilot`, camelCase) ; la jambe du
# registre Claude, sans marqueur, est traitée juste après.
# DISCRIMINANT BORNÉ, pour ne JAMAIS affaiblir la garde racine : sous
# `AGENTS_HOOK_HOST=copilot` SEUL, `sessionId` et `transcriptPath` sont des
# chaînes non vides, le dossier parent du transcript a la FORME d'un identifiant
# de session (UUID), et il DIFFÈRE de `sessionId` ⇒ sous-agent ⇒ zéro octet.
# Tout autre cas — champ absent ou d'un autre type, autre disposition du
# transcript, autre hôte — garde le comportement d'avant. Le séparateur `\`
# (Windows) est lu aussi : DÉDUIT, jamais mesuré sur un hôte.
# CE QUI PASSE ICI N'EST PAS PERDU : une affirmation écrite par un sous-agent
# reste dans l'arbre, et l'`agentStop` de la session racine la juge au même
# tampon, dans le même cycle. Banc : `affirmation-guard.test.sh` § 17 et
# `.agents/evals/test_hotes_fin_de_tour.py`.
_FORME_SESSION = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")


def sous_agent_copilot(charge):
    """Vrai si la charge est l'`agentStop` Copilot d'un SOUS-AGENT (voir ci-dessus)."""
    if os.environ.get("AGENTS_HOOK_HOST") != "copilot":
        return False
    session = charge.get("sessionId")
    transcript = charge.get("transcriptPath")
    if not isinstance(session, str) or not isinstance(transcript, str):
        return False
    if not session or not transcript:
        return False
    morceaux = [m for m in transcript.replace("\\", "/").split("/") if m]
    if len(morceaux) < 2 or not _FORME_SESSION.match(morceaux[-2]):
        return False
    return morceaux[-2] != session


if sous_agent_copilot(charge):
    sortir()


# COPILOT EXÉCUTE AUSSI LE `Stop` DE `.claude/settings.json` — MESURÉ (P4,
# 2026-10-13, Copilot CLI 1.0.95, macOS). Il tire DEUX fois, à la fin du
# sous-agent puis à la racine, chacun au même instant que son jumeau `agentStop`
# natif. Copilot TRADUIT la charge en snake_case : sept clés (`cwd`,
# `hook_event_name`, `session_id`, `stop_hook_active`, `stop_reason`,
# `timestamp`, `transcript_path`), aucun marqueur d'hôte, pas de
# `permission_mode`, et `transcript_path` vaut
# `~/.copilot/session-state/<id racine>/events.jsonl` aux DEUX tirs. Sans ce
# filtre, la garde jugeait deux fois de plus et pouvait bloquer un sous-agent
# dont la trace binôme n'existe pas encore (le `SubagentStop` tire APRÈS son
# `Stop`). Cette jambe-ci se tait en fin de sous-agent (id ≠ dossier) ; à la
# racine, elle ne se tait que si `.github/hooks/agent-guardrails.json` câble
# cette garde sur `agentStop` ; sinon elle juge la racine.
# BORNE : ce câblage est lu sur DISQUE (`_jambe_native_enregistree`), jamais son
# chargement effectif par l'hôte ; illisible ou absent, la racine est jugée ici.
# DISCRIMINANT BORNÉ, pour ne JAMAIS affaiblir la garde racine sous Claude :
# `AGENTS_HOOK_HOST` ABSENT, `transcript_path` chaîne, et ses segments (`\` lu
# comme `/`, segments vides retirés) portent soit la PAIRE CONSÉCUTIVE
# `.copilot`, `session-state`, soit la FIN `session-state`, `<UUID>`,
# `events.jsonl` — Copilot honore `COPILOT_HOME` et `--config-dir`, qui
# relocalisent l'état. Un transcript Claude
# (`~/.claude*/projects/<slug>/<uuid>.jsonl`) ne porte ni l'une ni l'autre.
# PUIS : fin de SOUS-AGENT (`session_id` chaîne non vide, dossier parent en forme
# d'UUID et DIFFÉRENT de lui) OU jambe `agentStop` câblée ; sinon, jugée ici.
# BRAS REFUSÉ — « hors `/.claude/projects/`, avec `timestamp`, sans
# `permission_mode` » : ce poste compte cinq dossiers de config Claude
# (`CLAUDE_CONFIG_DIR`), un transcript Claude vit donc aussi hors de
# `~/.claude/projects/` ; ce bras aurait tu la racine sous Claude.
# BRAS RETIRÉ — l'ancien filtre camelCase (`sessionId` sans `session_id`), jamais
# vu sur ce registre (15 charges sur 15 en snake_case). Mort établie deux fois :
# appelant unique (ci-dessous) ; `git grep` sur l'arbre entier, qui ne trouvait
# que le cas 17g du banc et cinq surfaces de doc, toutes réécrites.
# CAPACITÉ PERDUE : une charge camelCase, marqueur d'hôte absent, est de nouveau
# JUGÉE.
# NON MESURÉ : Windows (séparateur `\` DÉDUIT), une autre version de Copilot, un
# état Copilot relocalisé (forme de fin DÉDUITE), un sous-agent qui ÉCRIT une
# affirmation, une reprise de session Copilot (`--resume`/`--continue`). Un état
# relocalisé hors de ces deux formes rend le filtre inerte : retour au double
# jugement, le sens sûr.
# Banc : `affirmation-guard.test.sh` § 17 (17g, 17l à 17q'') et
# `.agents/evals/test_hotes_fin_de_tour.py`.
def _transcript_copilot(transcript):
    """Vrai si le chemin a la disposition d'un transcript Copilot (voir ci-dessus)."""
    morceaux = [m for m in transcript.replace("\\", "/").split("/") if m]
    if any(a == ".copilot" and b == "session-state"
           for a, b in zip(morceaux, morceaux[1:])):
        return True
    return (len(morceaux) >= 3 and morceaux[-3] == "session-state"
            and bool(_FORME_SESSION.match(morceaux[-2]))
            and morceaux[-1] == "events.jsonl")


_REGISTRE_NATIF_MAX = 1000000  # caractères ; au-delà, « non câblé »


def _jambe_native_enregistree():
    """Vrai si `.github/hooks/agent-guardrails.json` de la racine câble cette garde sur
    `agentStop` : c'est alors elle qui juge la racine sous Copilot. Illisible, absent,
    hors borne ou d'une forme inattendue => False : la jambe du registre Claude juge la
    racine (le sens sûr).

    TOUT ÉCHEC REND False, JAMAIS UNE EXCEPTION : cette lecture tourne AVANT la pose
    de `_refus_de_panne`, un plantage ici rendrait zéro octet — garde armée MUETTE
    (security-code-review, HIGH classe 1 : un registre imbriqué profond levait
    RecursionError ; `agentStop: null` levait TypeError). D'où `except Exception`,
    une lecture BORNÉE (un fichier plus long vaut « non câblé ») et un fichier
    RÉGULIER exigé (un FIFO ferait bloquer `open()` sans fin). Appelée garde ARMÉE
    seulement (le marqueur est testé avant). Banc : 17l'-nul, 17l'-prof,
    17l'-désarmée-prof, 17l'-gros, 17l'-espaces, 17l'-fifo."""
    chemin = os.path.join(RACINE, ".github", "hooks", "agent-guardrails.json")
    try:
        if not os.path.isfile(chemin):
            return False
        with open(chemin, encoding="utf-8") as fh:
            brut = fh.read(_REGISTRE_NATIF_MAX + 1)
        if len(brut) > _REGISTRE_NATIF_MAX:
            return False
        jambes = json.loads(brut).get("hooks", {}).get("agentStop", [])
        return any(isinstance(j, dict) and "affirmation-guard.sh" in str(j.get("bash", ""))
                   for j in jambes)
    except Exception:
        return False


def copilot_par_le_registre_claude(charge):
    """Vrai si la charge est le `Stop` de `.claude/settings.json` exécuté par Copilot
    (MESURÉ P4, 2026-10-13 : snake_case, sans marqueur, transcript sous
    `session-state`) en fin de SOUS-AGENT, ou à la racine quand la jambe `agentStop`
    de `agent-guardrails.json` câble cette garde (elle juge alors la racine)."""
    if os.environ.get("AGENTS_HOOK_HOST"):
        return False
    transcript = charge.get("transcript_path")
    if not isinstance(transcript, str) or not _transcript_copilot(transcript):
        return False
    morceaux = [m for m in transcript.replace("\\", "/").split("/") if m]
    session = charge.get("session_id")
    sous_agent = (isinstance(session, str) and bool(session) and len(morceaux) >= 2
                  and bool(_FORME_SESSION.match(morceaux[-2])) and morceaux[-2] != session)
    return sous_agent or _jambe_native_enregistree()


# DÉSARMÉE PAR DÉFAUT : absence du marqueur = régime de référence. Testé AVANT
# `copilot_par_le_registre_claude`, qui LIT `.github/hooks/agent-guardrails.json` :
# désarmée, la garde ne lit rien (borne écrite plus bas).
if not os.path.isfile(ARME):
    sortir()

if copilot_par_le_registre_claude(charge):
    sortir()


# ─── À PARTIR D'ICI LA GARDE EST ARMÉE, ET ELLE NE PLANTE PLUS EN SILENCE ───
#
# DÉCISION PILOTE S-00001884, D2 = B. Un `VERIFY_STAMP.log` portant un octet non
# UTF-8 faisait lever `UnicodeDecodeError`, non attrapée ; le `exit 0` terminal
# du `.sh` rendait alors la main avec un stdout VIDE, et sur `Stop` stderr n'est
# pas lu. Un octet DÉSARMAIT la garde, sans un mot : « un mécanisme dont le canal
# de retour est jeté n'existe pas » (L-00000136). `errors="replace"` a été
# ÉCARTÉ : il fermait l'instance, pas la classe.
#
# LA CLASSE EST DONC FERMÉE À SON POINT DE SORTIE : tout plantage du code qui
# SUIT le crochet `sys.excepthook = _refus_de_panne` — posé ci-dessous, une fois
# le marqueur d'armement constaté — devient un `{"decision":"block"}` qui dit
# qu'elle n'a PAS PU MESURER.
#   · lecture d'un fichier de SA PROPRE infrastructure (tampon, journal des
#     verts, traces du binôme) — `Illisible`, le fichier est NOMMÉ ;
#   · tout autre plantage — l'exception est nommée.
# Le remède est vrai dans les deux cas : réparer, ou la sortie ponctuelle
# `AFFIRMATION_SANS_BINOME`, que `_refus_de_panne` honore lui aussi.
#
# CE QUI RESTE ADVISORY, DÉLIBÉRÉMENT ET INCHANGÉ : pas de Python, pas de git
# exploitable, un board vivant introuvable. Ce ne sont pas des plantages, ce sont
# des mesures qu'on n'a pas pu faire et que ce fichier a choisi de ne pas
# opposer — l'arbitrage D2 porte sur le CRASH, pas sur ces choix-là.
#
# LA BORNE, À NE PAS RELIRE COMME UNIVERSELLE : rien de ceci n'existe garde
# DÉSARMÉE. Le crochet est posé APRÈS le test du marqueur, et rien avant lui ne
# lit l'infrastructure — désarmée, la garde ne lit rien et ne refuse rien.
# ET CE QUI PRÉCÈDE LE CROCHET N'EST PAS COUVERT, garde armée ou non : la
# lecture de la charge (JSON invalide, type inattendu ou imbrication trop
# profonde -> sortie ADVISORY, ci-dessus), le test du marqueur, et la lecture
# BORNÉE du registre natif (`_jambe_native_enregistree`, armée seulement, False
# sur tout échec). Une charge plus
# grande qu'ARG_MAX n'atteint même pas Python : elle passe en ARGUMENT, le shell
# échoue à le lancer (« Argument list too long », mesuré à 2 Mo), et le `exit 0`
# terminal du `.sh` rend la main SANS UN OCTET.
#
# CE QUE ÇA COÛTE, dit plutôt que découvert — DEUX cas où la garde refuse
# même un tour qui n'a RIEN écrit. Le coût est BORNÉ à UN refus par tour : la
# relance de l'hôte porte `stop_hook_active` et sort avant toute mesure (plus
# haut), donc ce n'est jamais un verrou (critic-fable T2, S-00001894). Chacun
# est épinglé sur un arbre PROPRE (rien d'écrit) par
# `.agents/evals/test_affirmation_guard_fenetre.py` (`test_cout_D2_…`) :
#   · le tampon COURANT est ILLISIBLE : `_tampon` le lit EN PREMIER, pour
#     l'ANCRAGE DU DIFF (`BASE`), avant de savoir si une surface a bougé ;
#   · le tampon courant est ABSENT ou n'est pas `frozen`, et le JOURNAL est
#     illisible : `_tampon` retombe alors sur le journal pour ce même ancrage.
# Dans les deux cas la garde refuse TOUTE fin de tour armée — y compris un tour
# de pure lecture sur un arbre où rien n'a été écrit — et non seulement celles
# qui écrivent : sans ancrage, elle ne sait plus ce que le cycle a écrit.


class Illisible(Exception):
    """Un fichier de la PROPRE infrastructure de la garde existe et ne se lit pas."""

    def __init__(self, chemin, cause):
        Exception.__init__(self, "%s : %r" % (chemin, cause))
        self.chemin = chemin
        self.cause = cause


def lire_infra(chemin):
    """Le TEXTE d'un fichier d'infrastructure, ou None s'il est ABSENT.

    ABSENT n'est pas ILLISIBLE : un dépôt adoptant n'a ni tampon ni journal, et
    c'est son régime de référence. Toute AUTRE erreur de lecture — droits, octet
    non UTF-8, composant de chemin qui n'est pas un répertoire — lève
    `Illisible`, que `_refus_de_panne` transforme en refus nommé."""
    try:
        with open(chemin, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise Illisible(chemin, exc)


#: Pourquoi une sortie PRÉSENTE n'a pas été honorée dans ce tour — vide si elle
#: l'a été, ou s'il n'y en avait pas. Les DEUX refus (ordinaire et de panne) le
#: disent : une sortie posée par le pilote ne disparaît jamais en silence.
#: Chaque entrée est un couple (pourquoi, suite) : la SUITE porte le remède, qui
#: n'est pas le même pour un dossier non inscriptible et pour deux sorties qui
#: se font face.
SORTIE_NON_HONOREE = []

#: La suite du cas le plus fréquent : un dossier d'état non inscriptible.
SUITE_INSCRIPTIBLE = (
    "Une sortie qu'on ne peut pas tracer serait une sortie MUETTE : elle reste\n"
    "en place, et sera honorée au premier tour où elle pourra être retirée\n"
    "puis journalisée. REMÈDE : rends `.agents/state/local/` et\n"
    "`.agents/state/gates/` inscriptibles (après un conteneur, ils peuvent\n"
    "appartenir à root)."
)


def _echapper(texte):
    """`\\t`, `\\n` et `\\r` rendus VISIBLES, jamais écrits bruts dans le journal.

    ADVISORY SÉCURITÉ S-00001891. Le journal est un format LIGNE PAR LIGNE, champs
    séparés par TAB : une surface portant un saut de ligne FORGEAIT une seconde
    ligne, horodatage compris. Mesuré sur la garde d'avant : un id de tâche
    ajoutée au board (`"T-2\\n2026-01-01T00:00:00Z\\tsurfaces=FORGEE"`) faisait
    d'UNE sortie DEUX lignes, dont une fausse. Le vecteur nommé par l'advisory —
    un nom de trace lu par `os.listdir` — est, lui, INATTEIGNABLE en séquence :
    la sortie est consommée par le chemin normal AVANT toute lecture de trace
    (mesuré : 1 ligne, nom absent). On échappe donc à l'ÉCRITURE, pour les deux."""
    return texte.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def consommer_sortie(surfaces):
    """Honore `AFFIRMATION_SANS_BINOME` si elle existe ET si elle a pu être
    RETIRÉE PUIS JOURNALISÉE : rend True. Rend False si elle n'existe pas — ou si
    l'un des deux temps a échoué, auquel cas la raison est posée dans
    `SORTIE_NON_HONOREE` et le refus la dira.

    POURQUOI NE PAS L'HONORER QUAND LE JOURNAL ÉCHOUE (exec-critic,
    T-00000695/696). La version précédente journalisait ET retirait dans un seul
    `try … except OSError: pass`, puis rendait True quoi qu'il arrive. Journal
    non inscriptible (`.agents/state/local/` à root après un conteneur) : la
    sortie n'était ni journalisée NI retirée — et UNE seule
    `AFFIRMATION_SANS_BINOME` désarmait la garde POUR TOUJOURS, sans un mot.
    Honorer une sortie qu'on ne peut pas tracer, c'est une sortie MUETTE.

    RETIRER D'ABORD, JOURNALISER ENSUITE (critic-opus T4, exec-critic). L'ordre
    inverse — journaliser, retirer, puis ajouter une ligne `NON HONORÉE` si le
    retrait échouait — laissait DEUX lignes horodatées par tour bloqué, et
    `session-start.sh`, qui compte les lignes ouvrant sur un horodatage, les
    annonçait comme deux sorties FRANCHIES : mesuré, 6 pour 0 honorée après 3
    tours, et l'alarme « DEUX OU PLUS SOUS LA MÊME PORTE ». Le journal ne porte
    plus que des sorties HONORÉES. Un temps de REPRISE, puis trois temps, aucun
    muet :
      0. reprendre un ORPHELIN — un `<sortie>.en-cours` laissé par un tour
         interrompu (voir plus bas) ;
      1. retirer — `os.replace` vers `<sortie>.en-cours` ; échec : non honorée,
         RIEN au journal, le fichier reste en place ;
      2. journaliser — TOUTE `Exception` (pas seulement `OSError`) : le fichier
         est REMIS EN PLACE (`os.replace` retour), non honorée ; si la remise
         échoue aussi, le refus nomme où il est resté, et le temps 0 du tour
         suivant le reprend ;
      3. effacer `<sortie>.en-cours` — un échec n'est PLUS inerte depuis le
         temps 0, et c'est l'identité `id=` du journal qui le neutralise : le
         temps 0 reconnaît un orphelin DÉJÀ journalisé et l'efface sans
         l'honorer une seconde fois.

    LE TEMPS 0, ET POURQUOI (exec-critic, passes post-binôme de T-00000695/696).
    La version précédente n'avait que les temps 1 à 3 : un kill entre le retrait
    et le journal — ou une exception AUTRE qu'`OSError` pendant le journal,
    mesurée avec un id de tâche portant un surrogate isolé (`"T-2\\ud800"`,
    fichier 100 % ASCII) — laissait la raison du pilote dans `.en-cours`, que
    PERSONNE ne relisait : le tour passait ou refusait sans un mot, et une
    nouvelle sortie écrasait l'orpheline au retrait suivant. Trois cas :
      · orphelin seul — il est REMIS à la place de la sortie, puis consommé par
        les temps 1 à 3 comme une sortie ordinaire ; échec de la reprise : non
        honorée, et dit ;
      · orphelin DÉJÀ journalisé (kill entre le temps 2 et le temps 3) — son
        identité est au journal : on l'efface, on ne l'honore pas deux fois ;
      · orphelin ET nouvelle sortie — RIEN n'est écrasé ni consommé : non
        honorée, et le refus NOMME les deux fichiers. Le pilote garde une raison.

    L'IDENTITÉ `id=` = inode et mtime en nanosecondes, que `os.replace` CONSERVE
    : la sortie et son `.en-cours` ont la même. BORNES, écrites plutôt que
    découvertes : (a) journal ILLISIBLE au temps 0 ⇒ l'orphelin est traité comme
    non journalisé et repris — une seconde ligne n'est possible que si ce même
    journal reste pourtant INSCRIPTIBLE ; (b) `stat` impossible ⇒ `id=inconnu`,
    aucun dédoublonnage pour cette sortie-là ; (c) deux sorties portant le MÊME
    inode ET la MÊME mtime (une copie `cp -p` d'un même modèle ET un inode
    réattribué ET un kill entre les temps 1 et 2) seraient confondues : la
    seconde serait effacée sans être honorée — aucun tour ne passe PAR elle,
    mais le refus qui suit ne la nomme pas ; (d) orphelin + nouvelle sortie sur un tour que les critiques
    satisfont déjà : le tour passe sans rien consommer, et le refus qui nomme
    les deux fichiers ne vient qu'au tour où la sortie sert.

    LE JOURNAL S'ÉCRIT EN `errors="backslashreplace"` : un surrogate isolé y
    devient le texte `\\ud800`, au lieu de lever `UnicodeEncodeError`. Le
    journal reste de l'UTF-8 valide, et l'`except Exception` du temps 2 ne sert
    plus qu'aux pannes que personne n'a encore nommées.

    BRANCHE RETRAIT IMPOSSIBLE : témoin sauté sous root/Windows
    (`DROITS_SANS_EFFET`) ; couverture jambe conteneur = 0, la porte ne le nomme
    pas (`pytest -q` sans `-rs`). Le témoin est
    `test_retrait_impossible_la_sortie_nest_pas_honoree` : un dossier en `chmod
    555` ne refuse rien à root, et la jambe conteneur de `verify.sh` tourne en
    root (`docker run` sans `--user`).

    SA RAISON EST FACULTATIVE, SA PRÉSENCE EST LE GESTE : un fichier vide passe
    déjà (« aucune raison donnée »). Une raison illisible n'empêche donc aucune
    MESURE — elle est consommée et journalisée comme telle, visible, au lieu de
    faire planter la garde ou de refuser la seule sortie que ses refus nomment."""
    en_cours = SORTIE + ".en-cours"
    # TEMPS 0 — reprendre un orphelin.
    if os.path.isfile(en_cours):
        if _deja_journalisee(_id_sortie(en_cours)):
            # Tué entre le journal et l'effacement : ce tour-là l'a HONORÉE.
            try:
                os.remove(en_cours)
            except OSError:
                pass  # déjà journalisée : son id la neutralise à chaque tour
        elif os.path.isfile(SORTIE):
            SORTIE_NON_HONOREE.append((
                "DEUX sorties se font face, et AUCUNE n'est écrasée :\n"
                "  %s\n"
                "  %s\n"
                "  (la seconde est ORPHELINE : un tour interrompu l'a retirée sans\n"
                "  la journaliser)"
                % (os.path.relpath(SORTIE, RACINE), os.path.relpath(en_cours, RACINE)),
                "Honorer l'une écraserait l'autre, et une raison du pilote\n"
                "disparaîtrait sans trace. REMÈDE : garde UNE raison — reporte ce\n"
                "qui compte de l'orpheline dans `AFFIRMATION_SANS_BINOME`, efface\n"
                "`AFFIRMATION_SANS_BINOME.en-cours`, puis refais un tour.",
            ))
            return False
        else:
            try:
                os.replace(en_cours, SORTIE)
            except OSError as exc:
                SORTIE_NON_HONOREE.append((
                    "une sortie ORPHELINE (un tour interrompu l'a retirée sans la\n"
                    "journaliser) n'a pas pu être REPRISE :\n  %s\n  (%s: %s)"
                    % (os.path.relpath(en_cours, RACINE), type(exc).__name__, exc),
                    SUITE_INSCRIPTIBLE,
                ))
                return False
    if not os.path.isfile(SORTIE):
        return False
    ident = _id_sortie(SORTIE) or "inconnu"
    try:
        with open(SORTIE, encoding="utf-8") as fh:
            # APLATIE ET BORNÉE À L'ÉCRITURE, et c'est un correctif du binôme.
            # `fh.read().strip()` laissait passer les retours à la ligne et
            # n'avait AUCUNE borne : une raison multiligne devenait N lignes
            # physiques de journal — donc un compte de dérogations faux — et une
            # raison énorme devenait une ligne énorme. Mesuré par le binôme : UNE
            # dérogation produisait 112 082 octets sur 3 lignes, réinjectés en
            # entier à chaque démarrage de session, ce qui est précisément le
            # déclencheur de compaction que le routeur nomme.
            # `split()` sans argument avale tabulations et sauts de ligne — les
            # deux séparateurs de CE format.
            raison = " ".join(fh.read().split())[:500] or "(aucune raison donnée)"
    except (OSError, UnicodeDecodeError) as exc:
        raison = "(raison illisible : %s)" % type(exc).__name__
    quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    surfaces = _echapper(surfaces)
    # TEMPS 1 — retirer.
    try:
        os.replace(SORTIE, en_cours)
    except OSError as exc:
        SORTIE_NON_HONOREE.append((
            "elle n'a pas pu être RETIRÉE (rien n'a été journalisé) :\n  %s\n  (%s: %s)"
            % (os.path.relpath(SORTIE, RACINE), type(exc).__name__, exc),
            SUITE_INSCRIPTIBLE,
        ))
        return False
    # TEMPS 2 — journaliser.
    try:
        os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8", errors="backslashreplace") as fh:
            fh.write("%s\tsurfaces=%s\traison=%s\tid=%s\n"
                     % (quand, surfaces, raison, ident))
    except Exception as exc:
        pourquoi = ("elle n'a pas pu être JOURNALISÉE dans\n  %s\n  (%s: %s)"
                    % (os.path.relpath(JOURNAL, RACINE), type(exc).__name__, exc))
        try:
            os.replace(en_cours, SORTIE)
        except OSError as exc_retour:
            pourquoi += (
                "\n  et n'a pas pu être REMISE EN PLACE : elle est restée dans\n"
                "  %s\n  (%s: %s) — le tour suivant la reprendra ; si ce refus\n"
                "  revient, renomme-la en `AFFIRMATION_SANS_BINOME`."
                % (os.path.relpath(en_cours, RACINE), type(exc_retour).__name__,
                   exc_retour)
            )
        SORTIE_NON_HONOREE.append((pourquoi, SUITE_INSCRIPTIBLE))
        return False
    # TEMPS 3 — effacer.
    try:
        os.remove(en_cours)
    except OSError:
        pass  # PAS inerte : le temps 0 la retrouvera, et son `id=` l'écartera
    return True


def _id_sortie(chemin):
    """L'IDENTITÉ d'une sortie : `<inode>-<mtime en ns>`, que `os.replace`
    CONSERVE (la sortie et son `.en-cours` ont donc la même) ; None si le fichier
    ne se `stat` pas. Bornes : docstring de `consommer_sortie`."""
    try:
        st = os.stat(chemin)
    except OSError:
        return None
    return "%d-%d" % (st.st_ino, st.st_mtime_ns)


def _deja_journalisee(ident):
    """Vrai si une ligne du journal FINIT par `\\tid=<ident>` : la sortie a été
    journalisée, seul l'effacement de son `.en-cours` a manqué. Identité inconnue
    ou journal illisible ⇒ False : l'orphelin sera repris (borne (a))."""
    if not ident:
        return False
    fin = "\tid=" + ident
    try:
        with open(JOURNAL, encoding="utf-8", errors="replace") as fh:
            return any(ligne.rstrip("\r\n").endswith(fin) for ligne in fh)
    except Exception:
        return False


def _dire_sortie_non_honoree():
    """Le paragraphe que les DEUX refus ajoutent quand une sortie présente n'a pas
    été honorée dans ce tour ; chaîne vide sinon."""
    if not SORTIE_NON_HONOREE:
        return ""
    pourquoi, suite = SORTIE_NON_HONOREE[-1]
    return (
        "\n\nSORTIE `AFFIRMATION_SANS_BINOME` PRÉSENTE MAIS NON HONORÉE — %s\n%s"
    ) % (pourquoi, suite)


def _refus_de_panne(typ, val, tb):
    """`sys.excepthook` de la garde ARMÉE : un plantage devient un REFUS dit.

    La trace part sur stderr comme avant (pour qui débogue) ; le REFUS part sur
    stdout, le seul canal que l'hôte lit sur `Stop`. `KeyboardInterrupt` et
    consorts (hors `Exception`) gardent le comportement par défaut."""
    sys.__excepthook__(typ, val, tb)
    if not issubclass(typ, Exception):
        return
    if isinstance(val, Illisible):
        chemin = os.path.relpath(val.chemin, RACINE)
        quoi = "infrastructure illisible — %s" % chemin
        detail = (
            "Elle ne peut pas lire un fichier de SA PROPRE infrastructure :\n"
            "  %s\n"
            "  (%s: %s)\n"
            "\n"
            "REMÈDE. Répare ce fichier, ou retire la ligne ou l'octet fautif\n"
            "(fichier d'état git-ignoré, écrit par l'outillage : le tampon et\n"
            "son journal par `core-scripts/verify.sh`, une trace de binôme par\n"
            "l'hôte au prochain passage du critique)."
            % (chemin, type(val.cause).__name__, val.cause)
        )
        if val.chemin == STAMP + ".log":
            # Le tampon COURANT est réécrit par `stamp_write` (`mv -f`) : une porte
            # verte le remplace. Son journal, lui, est ajouté par `>>` (critic-fable T2).
            detail += (
                "\nRejouer `verify.sh` n'efface pas l'octet : `VERIFY_STAMP.log` est\n"
                "APPEND-ONLY, retire la ligne fautive à la main."
            )
    else:
        quoi = "garde en panne — %s" % typ.__name__
        detail = (
            "Elle a planté pendant sa mesure :\n"
            "  %s: %s\n"
            "\n"
            "REMÈDE. La trace complète est sur stderr ; corrige la cause (un\n"
            "fichier corrompu qu'elle lit, le plus souvent)."
            % (typ.__name__, val)
        )
    try:
        # Une sortie déjà tentée DANS CE TOUR (chemin normal) et non honorée ne
        # se retente pas : on la journaliserait une seconde fois pour rien.
        if not SORTIE_NON_HONOREE and consommer_sortie(quoi):
            return
    except Exception:
        pass
    raison = (
        "AFFIRMATION-GUARD INCAPABLE DE MESURER — refus de fin de tour.\n"
        "\n"
        "%s\n"
        "\n"
        "POURQUOI UN REFUS ET NON UN SILENCE (décision pilote S-00001884) : sur\n"
        "`Stop`, un plantage rendait exit 0 avec un stdout vide, et stderr n'y\n"
        "est pas lu. La garde passait donc EN SILENCE sur tout ce qu'elle devait\n"
        "compter. Elle dit désormais qu'elle n'a pas pu mesurer.\n"
        "\n"
        "CE REFUS VAUT POUR CE TOUR, PAS AU-DELÀ : la relance que l'hôte envoie\n"
        "ensuite porte `stop_hook_active`, et cette garde la laisse passer sans\n"
        "mesurer. Il reviendra, une fois par tour, tant que la cause demeure.\n"
        "\n"
        "SORTIE PONCTUELLE, si la réparation attend : écris la raison dans\n"
        "`.agents/state/gates/AFFIRMATION_SANS_BINOME` et refais un tour. Elle\n"
        "est consommée une fois et JOURNALISÉE dans\n"
        "`.agents/state/local/affirmation-sorties.log`, avec ce qui a manqué."
    ) % detail
    raison += _dire_sortie_non_honoree()
    sys.stdout.write(json.dumps({"decision": "block", "reason": raison}) + "\n")
    sys.stdout.flush()


sys.excepthook = _refus_de_panne


def git(*args):
    # UTF-8 IMPOSÉ, ET NON LA LOCALE (critic-opus T3, T-00000695/696). `text=True`
    # décodait dans la locale : sous `LC_ALL=en_US.US-ASCII`, `git show
    # BASE:TASKS.json` sur un board portant un caractère non ASCII levait
    # `UnicodeDecodeError`, que D2 transformait en REFUS sur un arbre PROPRE, avec
    # un remède faux. Git rend ses contenus en octets et ce dépôt les écrit en
    # UTF-8 ; un octet invalide devient U+FFFD au lieu de planter la mesure.
    # Ce n'est PAS l'`errors="replace"` que D2 a écarté plus haut : celui-là aurait
    # MASQUÉ un fichier d'infrastructure corrompu ; ici un octet VALIDE de la
    # sortie de git était rendu illisible par la locale, et le refus était faux.
    # BORNE, écrite plutôt que découverte (exec-critic, passes post-binôme) : un id
    # INVALIDE dans le board de `BASE` devient U+FFFD, donc égal à un id de l'arbre
    # qui porte U+FFFD au même endroit — un tel id AJOUTÉ est alors MASQUÉ (mesuré :
    # BASE `T-\xff`, arbre `T-�`, aucun ajout vu, PASS). Un tel `BASE` n'est
    # pas productible par `tasks.py`, qui écrit le board en UTF-8 STRICT
    # (`json.dumps(…, ensure_ascii=False)` puis `encoding="utf-8"`) : il y faut un
    # board écrit et commité à la main.
    try:
        r = subprocess.run(
            ["git", "-C", RACINE, *args],
            capture_output=True, encoding="utf-8", errors="replace",
            check=False, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _lignes_stamp(chemin):
    """Les lignes d'un fichier de tampon ; [] s'il est ABSENT ; `Illisible` s'il
    existe et ne se lit pas (D2). SEUL lecteur du tampon et de son journal :
    `_tampon` et `_verts_frozen` passent tous deux par lui — deux lecteurs qui
    divergent, c'est exactement le défaut que le filtre `mode=frozen` a déjà
    coûté une fois à cette garde. Défini AVANT `BASE`, qui l'appelle au
    chargement."""
    texte = lire_infra(chemin)
    return texte.splitlines() if texte is not None else []


def sha_stamp():
    """Le sha du dernier verdict vert — l'ancrage du DIFF, comme celui du temps.

    ANCRER SUR `HEAD` RENDAIT LA GARDE AVEUGLE AU GESTE LE PLUS NORMAL D'ICI, et
    c'est le binôme de clôture qui l'a mesuré : un tour qui écrit `PLAN-ETAT.md`
    PUIS COMMITE ne montre plus rien à `git diff HEAD`, et le board commité par
    le hook post-`done` n'a plus d'id « ajouté ». Relevé sur dépôt jetable :
    `block` avant le commit, ZÉRO OCTET après. La garde annonçait donc la règle
    tenue alors qu'elle venait d'être contournée par un `git commit` — un faux
    vert, c'est-à-dire pire qu'une garde absente.

    Le tampon est le bon ancrage parce que c'est déjà celui de tout le reste du
    design : « depuis la dernière porte verte »."""
    return _tampon()[0]


def _tampon():
    """(sha, at) du dernier verdict vert **FROZEN**, ou (None, None).

    LE MODE EST FILTRÉ, ET SON ABSENCE ÉTAIT UN FAUX VERT — relevé du binôme,
    2026-09-14. La forme NUE de `verify.sh` mesure l'arbre vivant et écrit
    `sha=$HEAD_FULL` avec `mode=live` (`core-scripts/verify.sh:728`), un verdict
    que `.githooks/pre-push` REFUSE déjà au push. Ces deux lecteurs-ci ne lisaient
    que `sha=` et `at=`. Conséquence : après une forme nue, l'ancrage du diff
    redevient HEAD — c'est-à-dire EXACTEMENT l'état aveugle que la docstring
    ci-dessus dit avoir fermé : le tour commite, `git diff HEAD` ne montre rien,
    la garde se tait sans avoir compté un seul critique.
    L'effet symétrique est aussi vrai : une forme nue jouée ENTRE le binôme et
    l'écriture avancerait la borne de temps et périmerait une revue valide.
    `tasks.py:1815` filtrait déjà ce mode pour sa propre borne — les deux moitiés
    du même design ne lisaient pas le même tampon.

    REPLI SUR L'HISTORIQUE, JAMAIS SUR HEAD. `$STAMP.log` est append-only et
    porte le sha COMPLET de chaque verdict vert ; on y prend le dernier `frozen`.
    Un `live` doit faire retomber la garde sur la dernière porte HONNÊTE, pas la
    rendre aveugle.

    MÊME LECTEUR QUE `_verts_frozen` (`_lignes_stamp`), et ce n'était PAS le cas :
    la docstring de `_lignes_stamp` l'affirmait alors que `_tampon` gardait son
    propre lecteur imbriqué. Deux lecteurs qui divergent, c'est le défaut que le
    filtre `mode=frozen` a déjà coûté une fois — et D2 l'aurait rejoué : un octet
    non UTF-8 aurait refusé par l'un et planté par l'autre."""
    champs = {}
    for ligne in _lignes_stamp(STAMP):
        if "=" in ligne:
            cle, val = ligne.split("=", 1)
            champs[cle.strip()] = val.strip()
    if champs.get("mode") == "frozen" and champs.get("sha"):
        return champs["sha"], (champs.get("at") or None)
    for ligne in reversed(_lignes_stamp(STAMP + ".log")):
        c = dict(x.split("=", 1) for x in ligne.split("\t") if "=" in x)
        if c.get("mode", "").strip() == "frozen" and c.get("sha", "").strip():
            at = (c.get("at") or "").strip()
            return c["sha"].strip(), (at if at and at != "unknown" else None)
    return None, None


BASE = sha_stamp() or "HEAD"


def modifies():
    """Chemins suivis touchés DEPUIS LE DERNIER VERDICT VERT (commits compris)."""
    sortie = git("diff", "--name-only", BASE)
    if sortie is None and BASE != "HEAD":
        # Le sha tamponné peut ne plus être joignable (rebase, clone partiel).
        # On retombe sur HEAD plutôt que de ne rien mesurer — une garde qui se
        # tait sur une mesure ratée est une garde absente.
        sortie = git("diff", "--name-only", "HEAD")
    if sortie is None:
        return None
    return {l.strip() for l in sortie.splitlines() if l.strip()}


def suivis_reprise():
    """Fichiers SUIVIS sous `SPEC` touchés depuis le dernier vert (commits
    compris), même repli BASE → HEAD que `modifies()`. `-z` porte la correction
    des noms non ASCII et des guillemets (git les CITE sinon, et un nom cité ne
    correspond plus au motif) ; `core.quotePath=false` est redondant avec `-z`,
    gardé comme consigne. Un git en échec → set() POUR CETTE JAMBE (borne 4) :
    jamais l'advisory de `modifies()`, qui éteindrait aussi `PLAN-ETAT.md`, la
    doctrine et le board."""
    sortie = git("-c", "core.quotePath=false", "diff", "-z", "--name-only", BASE,
                 "--", *SPEC)
    if sortie is None and BASE != "HEAD":
        sortie = git("-c", "core.quotePath=false", "diff", "-z", "--name-only",
                     "HEAD", "--", *SPEC)
    if sortie is None:
        return set()
    return {c for c in sortie.split("\0") if c}


def non_suivis():
    """Fichiers NON SUIVIS sous `SPEC`. Ignores PERSONNELS neutralisés
    (`core.excludesFile` → `os.devnull`, comme `EXCLUDES_OFF` de T-00000724) :
    un `~/.config/git/ignore` qui porte `LOT-*` cacherait sinon une reprise
    neuve. `.gitignore` et `.git/info/exclude` restent obéis. Un git en échec
    → set() POUR CETTE JAMBE (borne 4)."""
    sortie = git("-c", "core.excludesFile=" + os.devnull, "ls-files", "-z",
                 "--others", "--exclude-standard", "--", *SPEC)
    if sortie is None:
        return set()
    return {c for c in sortie.split("\0") if c}


def _noms_dossier(noms):
    """Les ids d'un dossier d'enregistrements : chaque nom en `.json` NON pointé,
    l'id étant le nom sans `.json` — l'alias STOCKÉ, jamais réécrit (règle
    `record_file` de T-00001008). Un nom pointé est le temporaire d'une écriture
    atomique, ignoré à la lecture (`read_records`) : il ne compte jamais."""
    return {n[:-len(".json")] for n in noms
            if n.endswith(".json") and not n.startswith(".")}


def taches_ajoutees():
    """Ids présents dans le board de l'arbre et absents de celui de BASE
    (repli HEAD).

    Un `stage` ou un `done` ne sont PAS des affirmations neuves : seule une
    tâche AJOUTÉE compte.

    LES DEUX FORMES (T-00001012). L'union porte sur les ENTRÉES : ids de
    l'arbre = ids du monolithe ∪ noms de `BOARD_DOSSIER`, ids de BASE de même,
    puis `arbre − base` — c'est ce qui tient la forme MIXTE du commit de
    migration (le monolithe de BASE, le dossier de l'arbre) sans compter comme
    ajoutée une tâche qui n'a fait que changer de forme. Un monolithe absent
    contribue ∅. La branche MONOLITHE est celle d'avant, en place (`ids`,
    lecture de l'arbre, `git show BASE:BOARD` et son repli HEAD) : le banc
    `test_affirmation_guard_fenetre.py` épingle le `TypeError` qu'elle lève.
    Côté dossier, un candidat dont l'enveloppe se lit avec `record` à `null`
    (une TOMBE) est retiré ; un candidat illisible COMPTE (fermeture prudente).
    Aucune forme lisible à BASE ⇒ set(), comme avant (une mesure ratée se tait).
    LE DOSSIER NÉ APRÈS BASE SE LIT VIDE À BASE (K1, exec-critic T-00001012) :
    `BASE:<dossier>` absent alors que `BASE:<monolithe>` y est ⇒ ∅ côté dossier,
    jamais `HEAD:<dossier>` — une migration ET un ajout COMMITÉS après le dernier
    vert font donc parler l'ajout (témoin A7, contrôle A7c). Le repli sur HEAD ne
    vaut plus que si BASE ne porte AUCUNE des deux formes (BASE injoignable, ou
    board né après elle) : BORNE, un ajout commité depuis s'y tait encore.
    """
    vivant = os.path.join(RACINE, BOARD)

    def ids(texte):
        try:
            d = json.loads(texte)
        except (ValueError, TypeError):
            return None
        taches = d.get("tasks") if isinstance(d, dict) else d
        if not isinstance(taches, list):
            return None
        return {t.get("id") for t in taches if isinstance(t, dict) and t.get("id")}

    def tombe(tid):
        # Une SEULE lecture d'enveloppe par candidat, bornée comme celle de
        # `tasks_stockage` (4 Mio) ; un fichier non régulier n'est pas ouvert
        # (un FIFO bloquerait le `Stop`).
        chemin = os.path.join(RACINE, BOARD_DOSSIER, tid + ".json")
        if not os.path.isfile(chemin):
            return False
        try:
            with open(chemin, "rb") as fh:
                brut = fh.read(4 * 1024 * 1024 + 1)
            if len(brut) > 4 * 1024 * 1024:
                return False
            enveloppe = json.loads(brut.decode("utf-8"))
        except (OSError, ValueError, RecursionError):
            return False
        return (isinstance(enveloppe, dict) and enveloppe.get("id") == tid
                and "record" in enveloppe and enveloppe["record"] is None)

    # Branche DOSSIER : lue seulement si le dossier existe dans l'arbre — sans
    # lui, aucun `ls-tree` par `Stop`.
    try:
        noms_arbre = _noms_dossier(os.listdir(os.path.join(RACINE, BOARD_DOSSIER)))
    except OSError:
        noms_arbre = None
    noms_base = None
    if noms_arbre is not None:
        sortie = git("ls-tree", "-z", "--name-only", BASE + ":" + BOARD_DOSSIER)
        # K1 : BASE joignable et porteuse du monolithe, sans le dossier — le
        # dossier est NÉ après BASE et s'y lit VIDE, jamais à HEAD.
        if sortie is None and git("cat-file", "-e", BASE + ":" + BOARD) is not None:
            sortie = ""
        if sortie is None and BASE != "HEAD":
            sortie = git("ls-tree", "-z", "--name-only", "HEAD:" + BOARD_DOSSIER)
        if sortie is not None:
            noms_base = _noms_dossier(sortie.split("\0"))
    if not os.path.isfile(vivant) and noms_arbre is None:
        return set()

    maintenant = set()
    if os.path.isfile(vivant):
        try:
            with open(vivant, encoding="utf-8") as fh:
                maintenant = ids(fh.read())
        except OSError:
            return set()
    avant_txt = git("show", BASE + ":" + BOARD)
    if avant_txt is None and BASE != "HEAD":
        avant_txt = git("show", "HEAD:" + BOARD)
    avant = ids(avant_txt) if avant_txt is not None else None
    if avant is None and noms_base is None:
        return set()
    ids_arbre = (maintenant or set()) | (noms_arbre or set())
    ids_base = (avant or set()) | (noms_base or set())
    neuves = ids_arbre - ids_base
    for tid in neuves & ((noms_arbre or set()) - (maintenant or set())):
        if tombe(tid):
            neuves.discard(tid)
    return neuves


def _verts_frozen():
    """Les CYCLES verts, du plus ancien au plus récent : [(at, sha), …] — la
    MÊME définition que `tasks.py::cycle_precedent`, RECOPIÉE et non paraphrasée
    (décision pilote S-00001884, D1 = A : « une seule définition de "cycle
    précédent" dans le dépôt »). Toute modification ici se reporte là-bas, et
    inversement ; `.agents/evals/test_affirmation_guard_fenetre.py` épingle
    chaque filtre par un témoin qui rougit à sa mutation, et SA CLASSE
    `PariteJumellesTests` fait lire le MÊME journal aux deux jumelles et exige la
    même borne : une mutation d'UN SEUL côté la fait rougir. Rien ne les reliait
    avant elle — la règle « PREMIÈRE borne » n'avait aucun témoin, et sa
    mutation « dernière borne » restait verte des deux côtés (exec-critic).

    CE QUI DIVERGEAIT, ET NON DEUX POINTS MAIS QUATRE — relevé en lisant la
    jumelle avant de la recopier :
      (1) pas de déduplication d'un même sha : une porte REJOUÉE comptait pour
          deux cycles et périmait la revue du lot qu'on ferme ;
      (2) un seul vert rendait CE vert au lieu de « pas de borne » : la toute
          première porte d'un adoptant refusait un cycle CONFORME ;
      (3) une ligne `at=unknown` (repli de `date` dans `stamp_write`) restait un
          cycle SANS date — la jumelle l'écarte ;
      (4) le tampon COURANT était ajouté quand il manquait au journal — la
          jumelle ne lit que le journal.
    (1) et (2) sont les deux nommés par la décision ; (3) et (4) sont alignés au
    même motif, et chacun a son témoin.

    LES FILTRES, DANS L'ORDRE DE LA JUMELLE :
      · `mode` différent de `frozen` → écarté : une forme NUE ne borne rien ;
      · `at` vide ou `unknown` → écarté ;
      · même sha que la ligne PRÉCÉDENTE retenue → écarté (même cycle ; on
        garde la PREMIÈRE borne).

    ANGLE MORT PARTAGÉ, ÉCRIT : `stamp_write` écrit le tampon ET le journal
    ensemble, mais l'ajout au journal est `|| true`. S'il échoue, le dernier vert
    manque au journal, et les DEUX moitiés du design comptent un cycle de moins
    — la même erreur des deux côtés, plutôt que deux vérités différentes."""
    cycles = []
    for ligne in _lignes_stamp(STAMP + ".log"):
        if not ligne.strip():
            continue
        champs = dict(c.split("=", 1) for c in ligne.split("\t") if "=" in c)
        if champs.get("mode", "").strip() != "frozen":
            continue
        at = champs.get("at", "").strip()
        sha = champs.get("sha", "").strip()
        if not at or at == "unknown":
            continue
        if cycles and cycles[-1][1] == sha:
            continue  # même sha = même cycle ; on garde la PREMIÈRE borne
        cycles.append((at, sha))
    return cycles


def horodatage_stamp():
    """`at` de l'AVANT-DERNIER cycle vert, en epoch UTC — ou None s'il n'y a pas
    DEUX cycles distincts, auquel cas la fenêtre de 12 h s'applique.

    LES DEUX BORNES DE CETTE GARDE NE VIENNENT PLUS DU MÊME VERDICT, ET C'EST
    DÉLIBÉRÉ — décision pilote du 2026-09-22, option A. L'ancrage du DIFF reste
    sur le DERNIER vert (`sha_stamp`) : il dit ce que CE cycle a écrit, et le
    reculer élargirait ce sur quoi la garde mord. L'ancrage du TEMPS recule d'un
    cran : il dit quelles revues COMPTENT.

    POURQUOI, ET CE N'EST PAS UNE PRÉFÉRENCE — la garde JUMELLE a déjà appris
    cette leçon, et `AGENTS.md` la porte mot pour mot : « La borne n'est PAS
    `trace.sha == stamp.sha`, et c'est mesuré : le binôme passe AVANT la porte,
    donc la trace naît toujours avec le sha précédent, et cette règle-là aurait
    refusé le cas NOMINAL. » La garde de `done` s'ancre donc sur l'avant-dernier
    vert. Celle-ci était restée sur le dernier, c'est-à-dire sur la règle que sa
    jumelle avait mesurée fausse.

    MESURE DU 2026-09-22 QUI L'A RÉVÉLÉ : traces de binôme à 18:19:03 et 18:24:42,
    tampon de porte à 18:28:36. Le binôme avait tourné QUATRE et NEUF minutes
    avant la porte — exactement l'ordre que la doctrine IMPOSE (travail → binôme
    → correction → porte → `done`). Sur un cycle CONFORME, la fenêtre « depuis la
    dernière porte verte » est donc VIDE PAR CONSTRUCTION juste après chaque
    porte, et la sortie tracée devenait le régime nominal — une échappatoire
    empruntée à chaque cycle ne garde plus rien. Elle avait servi DEUX fois dans
    la même journée.

    CE QUE ÇA COÛTE, dit plutôt que caché : une revue du cycle PRÉCÉDENT peut
    désormais satisfaire la garde. C'est le même coût que sa jumelle accepte déjà.
    CE N'EST PAS BORNÉ COMME CHEZ LA JUMELLE : `done` ferme le lot relu sous P_k ;
    cette garde juge ce qui est écrit APRÈS P_k, donc le cycle k+1, que le binôme
    de k couvre jusqu'à P_(k+1). Sur un flux conforme elle ne mord que sur un
    cycle SANS AUCUN binôme — y compris pour des tâches ajoutées au board. Borne
    ASSUMÉE (décision pilote par défaut du 23/09). Mesurée par critic-opus (T2) et
    épinglée par `test_affirmation_guard_fenetre.py::FenetreTests::
    test_8_borne_assumee_le_binome_du_cycle_k_couvre_le_cycle_k_plus_1` : binôme
    à t-50, porte à t-40, trois tâches ajoutées après elle → PASS.

    MOINS DE DEUX CYCLES : PAS DE BORNE — None, comme `cycle_precedent` rend None
    (décision pilote S-00001884, D1). MAIS LES DEUX JUMELLES N'EN FONT PAS LA MÊME
    CHOSE : ici None devient la fenêtre de 12 h (repli ci-dessous) ; `tasks.py
    done`, lui, borne alors l'EMPRUNT à 24 h (`EMPRUNT_SANS_BORNE_TTL_HEURES`,
    T-00000846, décision pilote du 2026-09-30) — avant, il n'appliquait AUCUNE
    fenêtre et un emprunt n'expirait pas. Deux fenêtres, de durées DIFFÉRENTES :
    DIVERGENCE CONNUE ET ASSUMÉE (décision pilote par défaut du 23/09 pour les
    12 h de cette garde), et non une parité : `PariteJumellesTests` l'épingle
    comme telle. La version
    précédente rendait ici CE vert-là ; sa docstring disait « le régime de
    référence doit rester la fenêtre de 12 h » pendant que son code faisait
    l'inverse, et la toute première porte d'un adoptant — ou une porte REJOUÉE,
    sans la déduplication — refusait un cycle CONFORME : le binôme tourne AVANT
    la porte, donc AVANT le seul vert connu. Trop strict, exactement dans le sens
    du défaut que l'option A voulait fermer. CE QUE ÇA COÛTE, assumé par la
    décision : à la toute première porte, la borne est la fenêtre de 12 h, et
    non la porte."""
    cycles = _verts_frozen()
    if len(cycles) < 2:
        return None
    brut = cycles[-2][0]
    try:
        return datetime.strptime(brut, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def critiques_depuis(borne):
    """Noms DISTINCTS de critiques dont la trace est postérieure à `borne`.

    D2 : un répertoire de traces qui ne se LISTE pas, ou une trace du vocabulaire
    qui existe et ne se LIT pas (droits, octet non UTF-8), lève `Illisible`. Une
    trace LUE mais de forme inattendue (JSON invalide, `at` absent ou mal formé)
    reste ignorée comme avant — c'est un jugement du CONTENU, déjà fail-closed
    (un critique de moins), et `tasks.py::binome_trace` fait de même."""
    if not os.path.isdir(TRACES):
        return set()
    try:
        noms = os.listdir(TRACES)
    except FileNotFoundError:
        return set()
    except OSError as exc:
        raise Illisible(TRACES, exc)
    vus = set()
    for nom in noms:
        if not nom.endswith(".json"):
            continue
        morceaux = nom[:-len(".json")].split(".")
        if len(morceaux) < 2:
            continue
        agent = morceaux[-1]
        # VOCABULAIRE CLOS, le MÊME que `BINOME_CRITIQUES` dans `tasks.py` : deux
        # surfaces qui voyagent ensemble doivent dire la même chose. Un
        # `startswith("critic-")` acceptait un nom hors vocabulaire, donc un
        # fichier posé à la main suffisait à satisfaire la garde.
        if agent not in ("critic-opus", "critic-fable", "critic-sonnet-max"):
            continue
        chemin = os.path.join(TRACES, nom)
        texte = lire_infra(chemin)
        if texte is None:
            continue  # retirée entre le listage et la lecture
        try:
            d = json.loads(texte)
        except ValueError:
            continue
        brut = d.get("at") if isinstance(d, dict) else None
        if not isinstance(brut, str):
            continue
        try:
            quand = datetime.strptime(brut, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        if quand > borne:
            vus.add(agent)
    return vus


touches = []
modifs = modifies()
if modifs is None:
    # Pas de git exploitable : ADVISORY. On ne bloque jamais sur une mesure
    # qu'on n'a pas pu faire — un refus non fondé est pire qu'une règle non tenue.
    sortir()

for _pe in PLAN_ETAT:
    if _pe in modifs:
        touches.append(_pe)
for chemin in SURFACES_DOCTRINE:
    if chemin in modifs:
        touches.append(chemin)
# Les fichiers de reprise de lot : un chemin rejoint `touches` s'il correspond à
# un motif ET existe (un chemin supprimé n'est pas cité, borne 2).
for chemin in sorted(suivis_reprise() | non_suivis()):
    if (any(fnmatch.fnmatchcase(chemin, motif) for motif in REPRISES)
            and os.path.isfile(os.path.join(RACINE, chemin))):
        touches.append(chemin)
neuves = taches_ajoutees()
if neuves:
    touches.append(
        "board : %d tâche(s) ajoutée(s) — %s"
        % (len(neuves), ", ".join(sorted(neuves)[:6]))
    )

if not touches:
    sortir()

# SORTIE TRACÉE, consommée une fois et VISIBLE pour toujours. Sans elle, la
# garde serait désarmée dans la semaine ; avec une sortie muette, elle serait
# décorative. Le prix est qu'elle reste écrite — et une sortie qui ne PEUT PAS
# l'être (journal ou dossier des marqueurs non inscriptible) n'est pas honorée :
# le refus plus bas le dit. Le corps vit dans `consommer_sortie`, partagé avec
# `_refus_de_panne` : la sortie que nomment les refus d'infrastructure doit les
# franchir aussi.
if consommer_sortie("|".join(touches)):
    sortir()

# SANS TAMPON, LA BORNE EST UNE FENÊTRE — ET SANS ELLE LA GARDE ÉTAIT DÉSARMÉE
# À VIE CHEZ L'ADOPTANT (T-00000603, relevé du binôme de clôture).
#
# LE DÉFAUT, MESURÉ. `critiques_depuis` faisait `if borne is None or quand >
# borne` : quand `VERIFY_STAMP` est ABSENT — l'état PAR DÉFAUT d'un dépôt
# adoptant, ce fichier étant git-ignoré — la borne vaut None, donc TOUTE trace
# comptait, quel que soit son âge. Deux traces datées de 2020 faisaient passer la
# garde sans un octet de refus.
#
# CE N'EST PAS LE REPLI `_sans-slot` QUI L'A CRÉÉ, et le dire compte pour qui
# relira : le trou vaut pour N'IMPORTE QUELLE trace, y compris un
# `T-….critic-opus.json` oublié. Le repli le rend seulement ATTEIGNABLE plus
# souvent, puisqu'il écrit sous un nom stable que rien ne purge. On corrige donc
# la CLASSE — la borne — et non l'instance.
#
# DOUZE HEURES EST UN NOMBRE DÉCLARÉ, PAS UNE MESURE, exactement comme le seuil
# du régime d'atterrissage : rien dans ce dépôt n'établit 12 plutôt que 6 ou 24.
# Ce qu'on sait, c'est qu'une revue de la veille ne vaut pas pour le travail
# d'aujourd'hui, et qu'un dépôt sans tampon n'a aucun autre repère. Là où le
# journal porte DEUX verts distincts — ce dépôt — l'avant-dernier reste le
# repère, et cette fenêtre ne sert pas. Depuis D1 (S-00001884) elle sert AUSSI
# quand il n'y en a qu'UN : première porte d'un adoptant, ou porte rejouée.
#
# CE REPLI N'A PAS DE JUMELLE À 12 H. Sur la même absence de borne, `tasks.py
# done` (`cycle_precedent` → None) borne l'emprunt à 24 h depuis T-00000846
# (avant : aucune fenêtre, un emprunt n'expirait pas) ; cette garde garde SES
# 12 h. Deux fenêtres différentes — divergence CONNUE et ASSUMÉE, écrite ici,
# dans `horodatage_stamp`, dans `cycle_precedent` et dans `PariteJumellesTests`.
borne = horodatage_stamp()
sans_tampon = borne is None
if sans_tampon:
    borne = time.time() - 12 * 3600
vus = critiques_depuis(borne)
if len(vus) >= BINOME_MIN:
    sortir()

repere = (
    "les 12 dernières heures" if sans_tampon else "l'avant-dernière porte verte"
)
raison = (
    "AFFIRMATION DURABLE SANS REVUE CRITIQUE — refus de fin de tour.\n"
    "\n"
    # « CE TOUR ÉCRIT » ÉTAIT FAUX, et c'est la faute que cette garde traque.
    # Son périmètre est `git diff` DEPUIS LE TAMPON, donc il voit les commits
    # déjà faits — et déjà revus — depuis la dernière porte. Mesuré :
    # `PLAN-ETAT.md` propre dans l'arbre (`git status` vide) et pourtant listé
    # ici. Le refus n'est donc PAS tour-local : il se reproduit à chaque fin de
    # tour jusqu'à la porte suivante, y compris sur un tour de pure lecture.
    # L'ancrage RESTE le tampon — l'ancrer sur l'arbre ramènerait le faux vert
    # « commiter désarme la garde » que `sha_stamp` dit avoir fermé. Ce qui
    # change est ce que le message PROMET.
    "Depuis la dernière porte verte, ce CYCLE a écrit sur une surface durable\n"
    "— y compris par un commit d'un tour PRÉCÉDENT, déjà revu ou non. Ce refus\n"
    "n'est donc pas tour-local et se reproduira jusqu'à la prochaine porte :\n"
    "  - %s\n"
    "\n"
    "Or depuis %s, %s critique(s) distinct(s) ont tourné : %s.\n"
    "Il en faut %d (S-00004500) : UN critique de clôture porte seul les angles A et B.\n"
    "\n"
    "POURQUOI. Le 2026-09-13, cinq chemins mesurés ont produit une alerte\n"
    "systémique fausse, propagée dans trois tickets avant d'être rattrapée par\n"
    "une revue que le pilote a dû réclamer. Cette garde constate la revue ;\n"
    "elle ne la lance pas — aucun hook de ce dépôt n'invoque de modèle.\n"
    "\n"
    "CE QU'IL FAUT FAIRE. Lancer `critic-opus` (repli `critic-fable`, puis\n"
    "`critic-sonnet-max` à effort maximal) sur ce qui\n"
    "vient d'être écrit, en lui demandant de te CONTREDIRE, puis corriger\n"
    "ses constats. L'hôte écrit la trace tout seul : rien à déclarer.\n"
    "\n"
    "CE REFUS SE REPRODUIRA UNE FOIS, ET CE N'EST PAS UNE PANNE. Un critique\n"
    "lancé dans un tour ne rend la main qu'APRÈS ce tour : sa trace n'existe\n"
    "donc pas encore au moment où cette garde te lit. La séquence NORMALE est\n"
    "  refus -> tu lances le critique -> refus une seconde fois -> le critique\n"
    "  rend -> le tour suivant passe.\n"
    "Ce n'est PAS un motif de sortie tracée : la revue est due, elle est\n"
    "simplement encore en vol. Attends-la et corrige ses constats.\n"
    "\n"
    "SI LA REVUE N'A PAS D'OBJET — un renommage, une coquille, une décision\n"
    "déjà prise que tu ne fais que consigner — écris la raison dans\n"
    "`.agents/state/gates/AFFIRMATION_SANS_BINOME` et refais un tour. Elle est\n"
    "consommée une fois et JOURNALISÉE dans\n"
    "`.agents/state/local/affirmation-sorties.log`, donc elle reste visible.\n"
    "\n"
    "BORNE : cette garde mord sur l'ÉCRITURE, pas sur la prétention de vérité —\n"
    "un hook lit des octets. Une affirmation dite et jamais écrite lui échappe.\n"
    "Et elle compte des NOMS de critiques dans le cycle, pas une COUVERTURE :\n"
    "un critique tombé sur une autre tâche la satisfait. Elle prouve\n"
    "qu'une revue critique a tourné, jamais qu'elle portait sur CECI."
) % ("\n  - ".join(touches), repere, len(vus), ", ".join(sorted(vus)) or "aucun", BINOME_MIN)
raison += _dire_sortie_non_honoree()

print(json.dumps({"decision": "block", "reason": raison}))
sortir()
PYEOF
exit 0
