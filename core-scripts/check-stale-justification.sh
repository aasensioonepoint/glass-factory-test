#!/usr/bin/env bash
# =============================================================================
# GARDE DE JUSTIFICATION PERIMEE (T-00000322)
#
#   bash core-scripts/check-stale-justification.sh [--root <dir>] [--list]
#
# ROUGIT quand un texte du code DATE SA PROPRE PEREMPTION sur une tache du board
# qui est desormais CLOSE. Autrement dit : « ceci restera ainsi jusqu a T-XXX »
# alors que T-XXX est `done` — la condition a expire, et personne n a rouvert la
# question.
#
# CE QU ELLE FERME, ET C EST MESURE. La page d accueil justifiait son absence de
# style par « la coquille appartient a E-03 » ; E-03 a ete livree depuis, et rien
# n a reexamine la justification. Ce n est pas un cas isole : QUATRE textes du
# depot ont ete corriges le 2026-08-06 pour cette raison exacte. Une justification
# est un contrat a terme, et ce depot n avait aucun mecanisme pour constater
# l echeance. Un commentaire perime est pire qu un commentaire absent : il fait
# croire que la question est deja tranchee, donc personne ne la rouvre.
#
# =============================================================================
# LE PIEGE CENTRAL : TOUTES LES MENTIONS DE T-NNNNNNNN NE SONT PAS DES
# JUSTIFICATIONS
# =============================================================================
# Le depot porte 250 mentions de `T-NNNNNNNN` dans 141 fichiers. L IMMENSE
# MAJORITE sont des REFERENCES HISTORIQUES parfaitement legitimes — « corrige par
# T-00000123 », « suivi T-00000222 », « gate de securite T-00000130 » — et une
# garde qui les toucherait serait desarmee dans la semaine. Seules declenchent
# les formes exprimant une CONDITION FUTURE dont la tache est l objet IMMEDIAT.
#
# LES FORMES RETENUES, ET POURQUOI CHACUNE. Etablies en BALAYANT LE DEPOT REEL,
# pas en les imaginant :
#     jusqu'a / jusqu’a        (4 occurrences reelles, toutes conditionnelles)
#     reporte(e) a            (1 occurrence reelle, et c est le seul vrai positif
#                              du depot au 2026-08-06)
#     differe(e) a            \
#     en attendant             |  aucune occurrence aujourd hui, retenues comme
#     dans l attente de        |  synonymes directs des deux precedentes : une
#     tant que                 |  garde qui ne connait que les formes deja
#     d'ici                    |  presentes ne verrait jamais la suivante.
#     le temps de              |  (« le temps de » est nommement l expression que
#     remis(e) a              /   l en-tete de ci-steps.sh accuse de desarmer les
#                                 portes.)
#
# LES FORMES REJETEES, ET POURQUOI — c est la partie qui compte :
#   * `avant T-…`   REJETEE. Le brief la proposait ; LE DEPOT LA DEMENT. Sa seule
#                   occurrence reelle est HISTORIQUE :
#                   `packages/db/src/sql/conflict-nonworked.int.test.ts:260`,
#                   « Avant T-00000144, l appel ci-dessous levait … ». En francais
#                   technique, « avant T-X » raconte un etat ANTERIEUR bien plus
#                   souvent qu il ne pose une echeance. La retenir aurait produit
#                   un faux positif garanti pour zero vrai positif.
#   * `apres T-…`   REJETEE, meme mesure, meme raison
#                   (`visibility.repository.ts:331`, « apres T-00000277 et
#                   T-00000278, la base compte ZERO detenteur »).
#   * `a T-…` nu    REJETEE : aucune occurrence, et la forme est trop faible —
#                   « conforme a T-X », « suite a T-X » sont historiques.
#
# LA REGLE D ADJACENCE, ET LES QUATRE FAUX POSITIFS QU ELLE TUE. La tache doit
# etre l OBJET IMMEDIAT de la preposition, pas un simple renvoi entre parentheses
# plus loin dans la phrase. Sans cette regle, ces quatre textes — tous corrects —
# rougiraient :
#     rate-cap.ts:14     « EN ENVOIE JUSQU'A VINGT-CINQ (T-00000260, …) »
#     rate-cap.ts:538    « reporte jusqu'a la gravite d'App Insights (T-00000304) »
#     log-digest.ts:211  « jusqu'a la gravite d'App Insights (T-00000304) »
#     origin-throttle.ts:177  idem
# Dans les quatre, la preposition gouverne autre chose (« vingt-cinq », « la
# gravite ») et le `T-` n est qu une reference. Seul un chainon COURT et EXPLICITE
# est tolere entre la forme et l identifiant : « la tache », « le lot », ou un
# alias de version `V1-NN (T-NNNNNNNN)` — cette derniere forme est reelle
# (`docker-compose.yml:106`) et l ignorer aurait manque le seul vrai positif.
#
# =============================================================================
# LA REGLE A CONNAITRE AVANT DE CORRIGER UN CONSTAT DE CETTE GARDE :
#            UNE RETRACTATION PARAPHRASE, ELLE NE CITE PAS.
# =============================================================================
# Quand on retire une echeance perimee, le reflexe naturel est d expliquer ce
# qu on retire en le CITANT : « l echeance "jusqu a T-NNNNNNNN" qui figurait ici
# est retiree » — et l identifiant est ecrit ICI en substitut, PAS en clair, pour
# la raison meme que ce paragraphe expose : un exemple pedagogique redige avec un
# vrai identifiant serait une mine de plus, dans le fichier qui explique comment
# ne pas en poser. La premiere redaction de cet en-tete en portait une, sur
# T-00000300, et c est la garde elle-meme qui l a relevee.
# Ce reflexe de citation REARME la mine. Un controle syntaxique ne peut pas
# distinguer une citation d une promesse vivante — les deux sont, caractere pour
# caractere, le meme texte. Le commentaire redevient donc un faux positif en
# puissance, qui tirera le jour ou la tache citee se fermera, sur un texte
# pourtant DEJA corrige. Le suivant le lira, ne verra rien a corriger, et
# conclura que la garde crie pour rien : c est ainsi qu une porte se desarme.
#
# CE N EST PAS THEORIQUE. Le depot portait TROIS textes de cette forme
# (`administration/layout.tsx`, `design-system/page.tsx`,
# `design-system/tableau/page.tsx`) : tous trois RETIRAIENT correctement une
# echeance, tous trois en citaient la formulation mot pour mot, tous trois
# auraient tire a la fermeture de T-00000300. Ils ont ete desamorces avec cette
# garde. Et la premiere redaction du correctif de `docker-compose.yml` est
# tombee dans le meme piege, immediatement : elle citait l echeance qu elle
# supprimait, et la garde est repartie rouge sur la ligne meme du correctif.
#
# LA FORME CORRECTE decrit l echeance au lieu de la reciter — « l echeance qui
# figurait ici, datee sur T-NNNNNNNN, est retiree ». Meme information, meme
# tracabilite, meme identifiant de tache conserve pour qui veut remonter le fil ;
# simplement plus aucune preposition conditionnelle collee a l identifiant. Ce
# n est PAS un contournement de la garde : le texte ne porte plus de condition
# future, donc il n y a plus rien a detecter. La garde et le texte disent enfin
# la meme chose.
#
# =============================================================================
# CE QUE LE SCANNER LIT, ET CE QU IL NE LIT PAS
# =============================================================================
# Il lit des LIGNES, pas des commentaires analyses syntaxiquement. C est un choix,
# et il est argumente : distinguer commentaire et litteral demanderait six
# analyseurs (ts, css, sql, sh, yaml, prisma), et un analyseur faux est bien plus
# probable que le defaut qu il previendrait — la ligne SQL
# `migrations/…/migration.sql:164` porte justement une prose de ce genre dans un
# litteral `COMMENT ON`. Consequence MESUREE a l entree au tableau : 5
# occurrences de forme conditionnelle sur tout le depot, ZERO faux positif. Le
# jour ou un litteral legitime declencherait, la reponse est de reformuler le
# texte, jamais d elargir la regle.
#
# CODE DE SORTIE : 0 ou 1, JAMAIS 4. `ci-steps.sh` lit un 4 comme « NON EXECUTE,
# ni succes ni echec » : une justification perimee rendue 4 serait comptee SAUTEE,
# donc un faux vert.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
LIST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "argument inconnu : $1" >&2; exit 1 ;;
  esac
done

PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  # Rouge et NON 4 : python est indispensable a ce depot (sept suites bash
  # l invoquent). Son absence est une panne de poste, pas un « non applicable ».
  echo "check-stale-justification: aucun interpreteur python sur le PATH" >&2
  exit 1
fi

"$PY" - "$ROOT" "$LIST" "$HERE" <<'PYEOF'
"""Detecteur de justification perimee. 0 = vert, 1 = rouge. Jamais 4."""

import json
import os
import re
import subprocess
import sys

# SORTIE FORCEE EN UTF-8, ET C EST UN DEFAUT MESURE, PAS UNE PRECAUTION. Ce
# scanner RECOPIE la ligne fautive dans son rapport, et les commentaires de ce
# depot sont ecrits en francais avec des fleches et des tirets cadratins. Sur un
# poste Windows, la sortie standard de python est en cp1252 : la premiere
# execution reelle a leve `UnicodeEncodeError` sur le `→` de
# `docker-compose.yml:106` — c est-a-dire que la garde PLANTAIT au moment precis
# ou elle avait quelque chose a dire, et rendait 1 pour la mauvaise raison. Une
# garde qui ne sait pas imprimer son constat n en est pas une.
#
# CE QUI REND CE DEFAUT GRAVE ET PAS COSMETIQUE : la garde n echouait que sur son
# SEUL CHEMIN UTILE — le chemin vert ne recopie aucune ligne fautive, donc ne
# plante jamais, et le defaut restait invisible tant qu il n y avait rien a
# signaler. Et un plantage ne se lit pas comme une violation : il se lit comme un
# incident d outillage, qu on relance ou qu on contourne. Meme famille que le
# code de sortie 4 lu comme « saute » par ci-steps.sh — dans les deux cas la
# porte dit autre chose que « ce depot a un defaut ».
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # interpreteur trop ancien : on continue
    pass

ROOT = sys.argv[1]
LIST = sys.argv[2] == "1"
# Le dossier DE CE SCRIPT (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : `plan_pool.py`, qui lit le board en dossier, se charge
# DE LÀ, jamais de `--root` — un `plan_pool.py` posé sous la racine scannée n'est jamais exécuté.
HERE = sys.argv[3]

BOARD = os.path.join(ROOT, ".agents", "state", "board", "TASKS.json")
BOARD_DOSSIERS = [os.path.join(ROOT, ".agents", "state", "board", d) for d in ("tasks", "epics")]


def _taches_du_board():
    """Les taches du board dans SA forme. Sans dossier d enregistrements : TASKS.json lu ici, comme avant. Sinon
    `plan_pool.lire_board_forme`, charge par chemin depuis HERE sans bytecode : le dossier, ou le refus nomme des
    DEUX formes (PoolError, lu [E0] illisible par l appelant)."""
    if not any(os.path.isdir(d) or os.path.islink(d) for d in BOARD_DOSSIERS):
        with open(BOARD, encoding="utf-8") as fh:
            return json.load(fh).get("tasks", [])
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("_check_stale_plan_pool", os.path.join(HERE, "plan_pool.py"))
    if spec is None or spec.loader is None:
        raise ValueError(f"plan_pool.py introuvable a cote du script ({HERE})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except OSError as exc:
        raise ValueError(f"plan_pool.py illisible a cote du script ({exc})") from exc
    try:
        return module.lire_board_forme(Path(ROOT))["tasks"]
    except module.PoolError as exc:
        raise ValueError(str(exc)) from exc

# Extensions PORTEUSES DE COMMENTAIRES. `.md` en est volontairement absent : la
# doctrine et les specs se relisent, le code non — et etendre la garde a la prose
# du depot en ferait une police de redaction plutot qu une garde de coherence.
# EXTENSIONS — RE-DERIVEES POUR CE DEPOT (T-00000379).
# La liste d origine servait un arbre TS/Next. Ici le langage principal est
# PYTHON, et `.py` en etait absent : adoptee telle quelle, la garde balayait
# 9 fichiers sur 226 et restait verte pour toujours.
#
# `.md` EST INCLUS, et c est une DECISION, pas un oubli. Chez l auteur d origine
# la prose n est pas le produit, et etendre la garde a la prose en aurait fait
# une police de redaction. ICI la doctrine EST une surface livree qui VOYAGE
# chez chaque adoptant : une justification perimee y atteint tout le monde.
# Exclusions ciblees plus bas : `docs/tasks/` (un plan CITE des taches par
# nature), `docs/interne/chantier/` (arcs, notes de seance et prompts de reprise
# deplaces depuis `docs/tasks/` le 2026-09-21 — memes journaux, meme motif,
# et le dossier est `strip:` donc ne voyage pas) et les vues generees
# (TASKS.md, LEDGER.md, SPECS.md).
#
# CES CONSTANTES VOYAGENT ET NE SONT PAS UNIVERSELLES. Chez un adoptant TS/Next,
# `.md` fait de cette garde la police de redaction que l en-tete d origine
# refusait. Le motif robuste — des constantes surchargeables par fichier local,
# facon `.agents/protected-paths.local` — est une dette NOMMEE : T-00000380.
EXTS = {
    ".py",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".css", ".scss", ".sql", ".sh", ".yml", ".yaml", ".prisma", ".tf",
    ".md",
}

# Fichiers `.md` ECARTES nommement : ils citent des taches par nature.
MD_EXCLUS = ("docs/tasks/", "docs/interne/chantier/", "TASKS.md", "LEDGER.md", "SPECS.md")

# ELAGAGE, PAS LISTE BLANCHE — meme discipline que `run-bash-tests.sh` : tout
# nouveau repertoire applicatif est balaye sans qu on ait a l inscrire ici.
# `.agents/` et consorts sortent parce qu ils portent les STORES d etat (board,
# ledger, journal) : ces fichiers CITENT des justifications au lieu d en porter,
# et les scanner ferait rougir la garde sur sa propre memoire.
# ELAGAGE — RE-DERIVE (T-00000379). L intention d origine est SAINE : les STORES
# d etat CITENT des justifications au lieu d en porter, donc les scanner ferait
# rougir la garde sur sa propre memoire. Mais la regle etait ecrite TROP LARGE :
# ce sont `.agents/state/` qui portent les stores, pas `.agents/` entier — et
# `.claude/`, `.codex/`, `.gemini/` portent 47 fichiers de code de ce depot.
PRUNE = {
    ".git", "node_modules", ".next", ".turbo", "dist", "coverage",
    "generated", "__pycache__", ".worktrees",
}
# Chemins RELATIFS elagues (les stores, pas leur repertoire parent).
# `runs/` AJOUTE LE 22/09 (T-00000695), et ce n'est PAS une exclusion
# cérémonielle : ce contrôle balaye l'arbre ENTIER par `os.walk` et LIT le
# contenu, or les exports de run RECOPIENT le texte des tâches du board — donc
# du récit d'équipe, jamais du code qui s'exécute. Exactement la raison déjà
# écrite pour `.agents/state/` juste au-dessus, d'où la symétrie.
# POURQUOI MAINTENANT alors que rien ne rougissait : l'immunité tenait à l'ABSENCE
# de `.jsonl` dans `EXTS` — une LISTE, donc extensible. Ajouter `.json` à `EXTS`
# (un fichier de configuration, par exemple) y ferait entrer les exports EN
# SILENCE. Une protection qui tient à une liste qu'on étend se périme sans bruit ;
# celle-ci tient au chemin. Zéro changement de comportement aujourd'hui : aucun
# fichier sous `runs/` ne passe `EXTS`.
# BORNE DE L'AUDIT, écrite ici parce que c'est ici qu'on la cherchera : ce
# contrôle n'était dans AUCUNE des deux énumérations de balayeurs du 22/09 — ni
# le motif `ls-files` (18 fichiers), ni le motif `git grep` (2) — parce qu'il
# balaye par `os.walk`. Troisième canal, troisième bornage.
PRUNE_REL = (".agents/state/", "runs/")

# --- LES FORMES CONDITIONNELLES ---------------------------------------------
# L APOSTROPHE ET L ACCENT SONT OPTIONNELS, ET C EST UNE FAILLE MESUREE PAR LA
# SUITE, PAS une elegance. Ce depot ecrit ses textes dans DEUX styles : accentue
# dans les commentaires de code (`jusqu'a` avec accent grave), et ASCII PUR dans
# le board, le ledger et plusieurs scripts (`jusqu a`, `d ici`, sans apostrophe
# ni accent). Une redaction n acceptant que la forme accentuee laissait passer la
# forme ASCII de TROIS des neuf formes retenues — c est-a-dire qu il suffisait
# d ecrire son echeance sans apostrophe pour echapper a la garde. Les separateurs
# sont donc `['’\s]*` et les voyelles accentuees `[àa]` / `[ée]`.
FORMES = (
    r"(?:\bjusqu['’\s]*[àa]"
    r"|\ben\s+attendant"
    r"|\bdans\s+l['’\s]*attente\s+de"
    r"|\btant\s+que"
    r"|\bd['’\s]*ici"
    r"|\ble\s+temps\s+de"
    r"|\breport[ée]{1,2}s?\s+[àa]"
    r"|\bdiff[ée]r[ée]{0,2}s?\s+[àa]"
    r"|\bremise?\s+[àa])"
)

# CHAINON : rien, ou « la tache » / « le lot », ou un alias de version
# `V1-NN`, eventuellement suivi d une parenthese ouvrante. Volontairement COURT :
# c est lui qui distingue « jusqu a T-300 » de « jusqu a la gravite (T-304) ».
CHAINON = r"\s*(?:(?:la\s+t[âa]che|le\s+lot)\s+)?(?:V1-\d+\s*)?\(?\s*"

# L'id : `T-<ULID>` EN PREMIER (T-00000726), corps en MAJUSCULES Crockford —
# `(?-i:…)` : la casse ignoree des FORMES ne s'etend pas au corps — et borne a
# droite ; puis l'ancien `T-<8 chiffres>` (T-00001040 ; temoins : (g2) du banc).
MOTIF = re.compile(
    FORMES + CHAINON + r"(T-(?:(?-i:[0-9A-HJKMNP-TV-Z]{26})(?![0-9A-Za-z])|\d{8}))",
    re.IGNORECASE)

# --- LE BOARD (JAMAIS ECRIT, SEULEMENT LU) -----------------------------------
etats = {}
if not os.path.isfile(BOARD) and not any(os.path.isdir(d) or os.path.islink(d) for d in BOARD_DOSSIERS):
    # BOARD ABSENT = ROUGE, JAMAIS SAUTE — decision deliberee, epinglee par
    # `check-stale-justification.test.sh:319`. Elle n'est PAS assouplie ici : un
    # board manquant sur un projet qui utilise le kit est une anomalie, et une garde
    # qui se saute toute seule finit par masquer la panne qu'elle existe pour voir.
    # Le cas du projet ADOPTANT au premier jour (`.agents/state/` est `strip:`, donc
    # la branche d'adoption arrive sans board et la porte y etait rouge des le
    # premier jour — mesure du 2026-09-03) se resout a l'AUTRE bout, et le
    # mecanisme n'est PAS celui que ce commentaire decrivait : il n'existe aucune
    # regle `own:` sur le board, et il n'y en a jamais eu qu'en projet. Les seules
    # regles `own:` de .template-exclude portent sur `TEMPLATE.md` et
    # `.agents/protected-paths.local` (releve du 2026-09-03). Le board n'est donc
    # EMBARQUE nulle part : il est PROVISIONNE A L'USAGE par `project_init.py`
    # (`_ensure_stores`), qui demande sa structure a `tasks.py` et ne reecrit
    # jamais un board present (T-00000425). L'etat est FOURNI plutot que la garde
    # relachee — la difference tient au moment, pas au principe.
    # LE REMEDE EST NOMME ICI PARCE QUE C EST LE SEUL ENDROIT QUE CETTE
    # POPULATION-LA REGARDE. Un projet initialise AVANT l existence du drapeau
    # `--ensure-stores` n a pas de board, et il ne repassera pas par un init :
    # un second `--name` REFUSE (rc 2, « identite deja initialisee ») et ne
    # provisionne rien — mesure du 2026-09-03. La seule sortie que ce projet
    # voit est donc la ligne ci-dessous ; sans le remede, elle nomme une panne
    # sans nommer le geste qui la repare, et le geste ne vit alors que dans un
    # commentaire de code et dans un `--help` que personne n a de raison
    # d ouvrir. Le code de retour ne bouge pas et aucune forme n est excusee :
    # c est du texte qui rend l action possible.
    print(f"[E0] board introuvable : {BOARD}")
    print("         remede : python3 .agents/bin/project_init.py --ensure-stores")
    print("         (provisionne le board sans toucher l identite ; idempotent,")
    print("          il laisse un board present bit pour bit intact)")
    print("check-stale-justification: ROUGE (1 violation)")
    sys.exit(1)
try:
    for t in _taches_du_board():
        etats[t["id"]] = t.get("state", "")
except (ValueError, KeyError, TypeError) as exc:
    # Le board est NOMME DANS SA FORME (passe de correction F5, exec-critic de la bascule constat 6) : sous un dossier
    # d enregistrements, nommer TASKS.json envoyait le lecteur vers un fichier absent ou hors de cause.
    _forme = os.path.dirname(BOARD) if any(os.path.isdir(d) or os.path.islink(d) for d in BOARD_DOSSIERS) else BOARD
    print(f"[E0] board illisible ({_forme}) : {exc}")
    print("check-stale-justification: ROUGE (1 violation)")
    sys.exit(1)

# --- LES CHECKOUTS IMBRIQUES (T-00001073) ------------------------------------
# UN WORKTREE LIE OU UN CLONE POSE DANS L ARBRE N EST PAS CE DEPOT. Un dev qui
# travaille en worktree (`.claude/worktrees/agent-*`) pose une COPIE ENTIERE du
# depot sous la racine : balayee, elle doublait le compte (676 fichiers sans
# elle, 1386 avec elle et trois petits clones de banc, mesure sur un clone) et y
# lisait des textes qui ne sont pas ceux de la porte.
# Le nom ne discrimine rien (`.worktrees` est deja elague par nom, l agent ecrit
# ailleurs) : le discriminant est la PROPRIETE, un `.git` a soi.
#
# DEUX ETAGES, ET LE SECOND EST LA GARANTIE. Le bloc ci-dessous dit « ce dossier
# porte son propre `.git` » (dossier, lien vers un dossier, ou gitfile de
# WORKTREE `gitdir: .../worktrees/<n>`) ; il est TEXTUELLEMENT identique dans les
# quatre fichiers qui parcourent l arbre avec lui (epingle par empreinte dans
# `.agents/evals/test_repo_walk_census.py`). La garde dit ensuite si ce chemin est
# ENREGISTRE : une ligne `path =` du `.gitmodules` de la RACINE, ou une entree
# dans l index du checkout qui CONTIENT directement le candidat
# (`git -C <parent> ls-files -s -- ":(literal)<nom>"`, git remonte lui-meme au
# premier `.git`). ENREGISTRE => JAMAIS ELAGUE : un sous-module (absorbe,
# embarque, gitlink nu, sous-module de sous-module) et tout dossier portant des
# fichiers SUIVIS restent balayes. Seul du contenu NON SUIVI peut etre ecarte
# — sous une racine git LISIBLE, git sur le PATH ; git absent, un dossier suivi
# portant un `.git` parasite est elague (mesure, note `git absent`).
#
# LES BORNES, ECRITES PARCE QUE CE SCRIPT VOYAGE :
#   * mode decide UNE fois a la racine, paresseusement (0 appel git sur un arbre
#     sans candidat) : depot git -> la garde interroge l index ; HORS DEPOT ou git
#     ABSENT -> `.gitmodules` seul, note dans la ligne d elagage ; racine que git
#     ne sait pas lire -> tout candidat est BALAYE (jamais cache) ;
#   * dans un depot, un enfant que git declare « hors depot » est une DECOUVERTE
#     BLOQUEE (plafond, point de montage), jamais une absence : BALAYE ; tout
#     autre echec de git sur un enfant (gitfile invalide, index corrompu,
#     propriete douteuse) : BALAYE ;
#   * environnement git PURGE PAR PREFIXE : tout `GIT_*` est retire sauf
#     GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM et GIT_CONFIG_NOSYSTEM — une liste de
#     noms laissait passer GIT_CEILING_DIRECTORIES, qui fait repondre « hors
#     depot » a un enfant ENREGISTRE ; locale C, sinon le message est traduit ;
#   * un DOSSIER `.git` quel que soit son contenu (meme vide) rend le bloc vrai :
#     sous une racine git il n est elague que si rien n est suivi dessous ;
#   * la requete d index NEUTRALISE la config du depot interroge : `-c
#     core.fsmonitor=false -c core.hooksPath=/dev/null` avant `-C`. Sans eux, un
#     clone embarque (archive non fiable) executait son `core.fsmonitor` a chaque
#     `ls-files -s` (mesure git 2.55, S-00003664) ; temoin : (m) FSMONITOR de la
#     suite. Le `rev-parse` de la racine n en porte pas : il ne lit pas l index ;
#   * chaque appel git est borne a 60 s : passe ce delai, git est ILLISIBLE et le
#     candidat est BALAYE (note `git sans reponse (60 s)`), jamais elague ;
#   * la ligne d elagage ne s imprime que si au moins un chemin est elague, donc
#     un arbre sans checkout imbrique rend la MEME sortie qu avant. Les notes
#     voyagent AVEC elle : un echec qui fait tout BALAYER (racine ou index
#     illisible, git sans reponse) n imprime rien — balayer est le cote sur.
# checkout imbrique : debut (T-00001073)
def _checkout_imbrique(chemin):
    marqueur = os.path.join(chemin, ".git")
    if os.path.isdir(marqueur):
        return True
    if not os.path.isfile(marqueur):
        return False
    try:
        with open(marqueur, encoding="utf-8", errors="replace") as fh:
            ligne = fh.readline(4096)
    except OSError:
        return False
    m = re.match(r"gitdir:\s*(.+?)\s*$", ligne)
    return bool(m and re.search(r"/worktrees/[^/]+/?$", m.group(1).replace("\\", "/")))
# checkout imbrique : fin (T-00001073)


# garde d'index (T-00001073) : debut
_GARDE_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_GARDE_HORS_DEPOT = "not a git repository (or any"
_garde_notes = set()
_garde_etat = {}


def _garde_env():
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    e["LC_ALL"] = "C"
    e["LANGUAGE"] = ""
    return e


def _garde_gitmodules():
    if "gitmodules" not in _garde_etat:
        chemins = set()
        try:
            with open(os.path.join(ROOT, ".gitmodules"), encoding="utf-8", errors="replace") as fh:
                for m in re.finditer(r"(?m)^\s*path\s*=\s*(.+?)\s*$", fh.read()):
                    v = m.group(1)
                    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                        v = v[1:-1]
                    chemins.add(v.replace("\\", "/"))
        except OSError:
            pass
        _garde_etat["gitmodules"] = chemins
    return _garde_etat["gitmodules"]


def _garde_mode():
    if "mode" not in _garde_etat:
        try:
            p = subprocess.run(["git", "-C", ROOT, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True, env=_garde_env(), timeout=60)
        except OSError:
            _garde_etat["mode"] = "absent"
        except subprocess.TimeoutExpired:
            _garde_notes.add("git sans reponse (60 s) : balaye")
            _garde_etat["mode"] = "illisible"
        else:
            if p.returncode == 0 and p.stdout.strip() == "true":
                _garde_etat["mode"] = "git"
            elif p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
                _garde_etat["mode"] = "none"
            else:
                _garde_etat["mode"] = "illisible"
    return _garde_etat["mode"]


def _enregistre(chemin):
    if os.path.relpath(chemin, ROOT).replace(os.sep, "/") in _garde_gitmodules():
        return True
    mode = _garde_mode()
    if mode == "absent":
        _garde_notes.add("git absent : .gitmodules seul")
        return False
    if mode == "none":
        _garde_notes.add("hors depot : .gitmodules seul")
        return False
    if mode != "git":
        _garde_notes.add("racine illisible : balaye")
        return True
    try:
        p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                            "-C", os.path.dirname(chemin), "ls-files", "-s", "--",
                            ":(literal)" + os.path.basename(chemin)],
                           capture_output=True, text=True, env=_garde_env(), timeout=60)
    except OSError:
        _garde_notes.add("git absent : balaye")
        return True
    except subprocess.TimeoutExpired:
        _garde_notes.add("git sans reponse (60 s) : balaye")
        return True
    if p.returncode == 0:
        return bool(p.stdout.strip())
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        _garde_notes.add("decouverte bloquee : balaye")
        return True
    _garde_notes.add("index illisible : balaye")
    return True
# garde d'index (T-00001073) : fin


# --- LE BALAYAGE -------------------------------------------------------------
fichiers = 0
occurrences = []
elagues = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in PRUNE]
    # T-00000379 — elagage par chemin RELATIF, en plus du nom de repertoire :
    # `.agents/state/` porte les stores (ils CITENT des taches au lieu d en
    # porter), mais `.agents/` entier porte 134 fichiers de code de ce depot.
    rel_dir = os.path.relpath(dirpath, ROOT).replace(os.sep, "/") + "/"
    # ANCRÉ À LA RACINE — la disjonction par SOUS-CHAÎNE élaguait `runs` à TOUTE
    # profondeur (mesuré : `services/runs` → True, `apps/api/runs` → True), donc
    # un adoptant portant un répertoire applicatif homonyme perdait son balayage
    # EN SILENCE. C'est exactement la péremption silencieuse que le commentaire
    # de `PRUNE_REL` dit vouloir éviter — et ce script VOYAGE dans `core-scripts/`.
    # Le premier terme suffit : `rel_dir` porte déjà son `/` final, et les
    # descendants d'un répertoire élagué commencent par le préfixe du parent.
    if any(rel_dir.startswith(x) for x in PRUNE_REL):
        dirnames[:] = []
        continue
    # T-00001073 — APRES l elagage relatif, pour qu un dossier deja ecarte ne
    # coute jamais un appel git : un enfant qui porte son propre `.git` et que
    # rien n enregistre n est pas descendu (voir LES CHECKOUTS IMBRIQUES).
    _gardes = []
    for d in dirnames:
        _candidat = os.path.join(dirpath, d)
        if _checkout_imbrique(_candidat) and not _enregistre(_candidat):
            elagues.append(os.path.relpath(_candidat, ROOT).replace(os.sep, "/"))
        else:
            _gardes.append(d)
    dirnames[:] = _gardes
    for nom in sorted(filenames):
        ext = os.path.splitext(nom)[1]
        if ext not in EXTS:
            continue
        chemin = os.path.join(dirpath, nom)
        rel_tmp = os.path.relpath(chemin, ROOT).replace(os.sep, "/")
        # `.md` : la doctrine est balayee, les plans et les vues generees non —
        # ils CITENT des taches par nature, les rougir serait un faux positif
        # permanent (et le genre de bruit qui fait cesser de lire une garde).
        if ext == ".md" and any(x in rel_tmp or rel_tmp.endswith(x) for x in MD_EXCLUS):
            continue
        try:
            with open(chemin, encoding="utf-8") as fh:
                contenu = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        fichiers += 1
        rel = os.path.relpath(chemin, ROOT).replace(os.sep, "/")
        for no, ligne in enumerate(contenu.split("\n"), 1):
            for m in MOTIF.finditer(ligne):
                occurrences.append((rel, no, m.group(1), m.group(0).strip(), ligne.strip()))

violations = []
for rel, no, tid, extrait, ligne in occurrences:
    etat = etats.get(tid)
    if etat is None:
        violations.append(
            f"[E2] {rel}:{no} justification conditionnee a une tache ABSENTE du board ({tid})\n"
            f"      forme : « {extrait} »\n"
            f"      texte : {ligne[:160]}"
        )
    elif etat == "done":
        violations.append(
            f"[E1] {rel}:{no} justification PERIMEE : sa condition est {tid}, CLOSE au board\n"
            f"      forme : « {extrait} »\n"
            f"      texte : {ligne[:160]}"
        )

# --- RESTITUTION -------------------------------------------------------------
ouvertes = len(occurrences) - len(violations)
print(f"check-stale-justification: {fichiers} fichier(s) balaye(s), {len(occurrences)} forme(s) conditionnelle(s)")
# T-00001073 — LA LIGNE N EXISTE QUE S IL Y A QUELQUE CHOSE A DIRE : un arbre sans
# checkout imbrique rend la sortie d avant, octet pour octet. Les notes disent
# sur quoi la garde s est appuyee (`.gitmodules` seul, git absent, balaye).
if elagues:
    print(f"  {len(elagues)} checkout(s) imbrique(s) elague(s) : " + " ".join(sorted(elagues))
          + ("" if not _garde_notes else " (" + "; ".join(sorted(_garde_notes)) + ")"))
print(f"  {ouvertes} encore portee(s) par une tache ouverte / {len(violations)} perimee(s)")

# T-00000425 — L ECHEC BRUYANT NE DEVIENT PAS SILENCIEUX, IL SE SITUE.
# Un board PRESENT et VIDE est l etat NORMAL d un projet le jour ou il installe le
# kit : `project_init.py` provisionne le magasin, et personne n y a encore ouvert
# de tache. Toute justification datee sur une tache y est alors rapportee comme
# absente du board — ce qui est exact, et se lit pourtant comme un defaut du texte
# alors que c est l etat du board qui explique le constat.
#
# CE QUE CETTE LIGNE NE FAIT PAS, ET C EST LA MOITIE DE SA DEFINITION : elle ne
# touche NI le code de retour, NI la liste des constats. Aucune forme n est
# excusee, aucun compte ne bouge. Elle ajoute une nuance de lecture, au seul
# endroit ou elle est vraie — board lisible, ZERO tache, et au moins un constat a
# rapporter. Un board non vide citant une tache absente reste un constat nu, et
# il est correct : ce projet-la tient un board, donc l identifiant qu il cite
# devrait s y trouver.
#
# Le libelle DECRIT au lieu de citer (meme discipline que l en-tete plus haut,
# `:99-105`) : il ne recopie aucune etiquette de constat, pour qu une suite qui
# verifie l ABSENCE d une etiquette ne soit pas mise en defaut par une nuance.
#
# DEVIATION ASSUMEE ET DECLAREE : ce libelle porte `—`, `«` et `»`, alors que la
# decision d origine demandait de l ASCII pur. Le peril que cette demande visait
# est l incident d encodage documente plus haut (une sortie cp1252 qui levait
# `UnicodeEncodeError` au moment precis ou la garde avait quelque chose a dire),
# et il est deja ferme par le `sys.stdout.reconfigure(...)` de ce fichier.
# Verifie le 2026-09-03 sous `LC_ALL=C PYTHONIOENCODING=ascii` : sortie
# identique, aucun traceback. Les accents, eux, restent proscrits — c est la
# moitie de la regle qui protege encore quelque chose, et le reste du fichier
# s y tient.
if not etats and violations:
    print("[E0-bis] board PRESENT mais VIDE (0 tache) — les constats ci-dessous")
    print("         peuvent signifier « ce projet n a pas encore adopte le board »")
    print("         plutot que « la tache citee n existe pas ».")

if LIST:
    for rel, no, tid, extrait, _ in occurrences:
        print(f"  - {rel}:{no}  {tid}={etats.get(tid, 'ABSENTE')}  « {extrait} »")

if violations:
    print()
    for x in violations:
        print(x)
    print()
    print(f"check-stale-justification: ROUGE ({len(violations)} justification(s) perimee(s))")
    print("  Une condition expiree se corrige en REECRIVANT le texte, jamais en elargissant la garde.")
    sys.exit(1)

print("check-stale-justification: VERT — aucune condition future n a expire.")
sys.exit(0)
PYEOF
