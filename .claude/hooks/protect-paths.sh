#!/usr/bin/env bash
# PreToolUse [Edit|Write] — deterministic enforcement of the "do-not-touch" rules.
# Exit 2 = block (stderr is shown to Claude). Exit 0 = allow.
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
[ -n "$PY" ] || echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
FILE=""
# EN OCTETS, DANS LES DEUX SENS (binôme de clôture sur 119f81e5) : `json.load`
# sur `sys.stdin` et `print` dépendaient de l'encodage de la console — sous
# `PYTHONIOENCODING=ascii`, `docs/é/.env` faisait lever `print`, `$FILE` restait
# vide et le hook sortait 0 en silence (mesuré). Lu sur `sys.stdin.buffer`,
# écrit en UTF-8 `surrogateescape` : aucun octet du chemin ne dépend du locale.
[ -n "$PY" ] && FILE=$(printf '%s' "$INPUT" | "$PY" -c "import sys,json;d=json.load(sys.stdin.buffer);sys.stdout.buffer.write(str(d.get('tool_input',{}).get('file_path','')).encode('utf-8','surrogateescape'))" 2>/dev/null)
PP_CHARGE_RC=$?
# SANS PYTHON ET SOUS MARQUEUR KIT-CODE (T-00000763) : sans interpréteur, le
# chemin visé ne peut même pas être lu, donc aucune écriture ne peut être triée.
# Désarmé, le régime historique tient (rien n'est jugé, exit 0 ci-dessous) ;
# armé, TOUTE écriture est refusée — plus large que le refus nominal, et nommé.
if [ -z "$PY" ] && [ -f "$CLAUDE_PROJECT_DIR/.agents/state/gates/KIT_CODE_PROTEGE" ]; then
  echo "BLOCKED by hook: KIT_CODE_PROTEGE est posé et aucun interpréteur python 3 ne lit le chemin visé — toute écriture est refusée plutôt que jugée à l'aveugle (T-00000763). Remède : installer python 3, ou le pilote retire .agents/state/gates/KIT_CODE_PROTEGE." >&2
  exit 2
fi
# PYTHON PRÉSENT, EXTRACTION EN ÉCHEC : REFUS NOMMÉ `charge-illisible`, même
# principe que la fermeture (F1). TROIS RÉGIMES, distingués et non confondus :
# python ABSENT (`$PY` vide) — régime historique ci-dessus et ci-dessous,
# inchangé ; charge LUE mais sans `file_path` (rc 0, `$FILE` vide) — sortie 0
# ci-dessous, inchangée (un outil qui n'écrit pas par ce champ n'est pas jugé
# ici) ; charge ILLISIBLE (python présent, rc ≠ 0 : JSON invalide, `tool_input`
# qui n'est pas un objet, chemin inencodable) — le chemin visé est inconnu,
# donc refus plutôt qu'accord.
if [ -n "$PY" ] && [ "$PP_CHARGE_RC" -ne 0 ]; then
  echo "BLOCKED by hook: python 3 est présent mais la charge PreToolUse ne se lit pas (rc $PP_CHARGE_RC) — le chemin visé est inconnu, refus plutôt qu'accord (T-00000722). Remède : vérifier la charge JSON de l'outil (tool_input.file_path) et que python 3 exécute un programme -c." >&2
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=charge-illisible "path=" >/dev/null 2>&1 || true
  exit 2
fi
[ -z "$FILE" ] && exit 0

# Blocked path prefixes / patterns. TWO extension files, both optional, both
# one pattern per line:
#   .agents/protected-paths.local   SHARED by all four hosts (T-00000031) —
#     this is where a consumer project protects vendored code such as
#     .agents/bin/. A guard only one host honours is a false sense of one.
#   .claude/hooks/protected-paths.local   Claude-only, kept for compatibility
#     with projects that already use it.
# `#` comments and blank lines are stripped so the shared file can explain
# itself; the sh word-split below would otherwise turn a comment into patterns.
BLOCKED_PATTERNS="src/legacy/ generated/ .env"
for EXTRA in "$CLAUDE_PROJECT_DIR/.agents/protected-paths.local" \
             "$CLAUDE_PROJECT_DIR/.claude/hooks/protected-paths.local"; do
  [ -f "$EXTRA" ] || continue
  BLOCKED_PATTERNS="$BLOCKED_PATTERNS $(sed -e 's/#.*$//' "$EXTRA" | tr '\n' ' ')"
done
# LA LISTE MINUSCULISÉE, SUR UNE LIGNE À ELLE (T-00000722). La ligne
# `BLOCKED_PATTERNS="…"` ci-dessus reste littérale et en colonne 0 — safe-bash
# l'extrait par ce texte exact, et L-013 interdit de la retoucher. Mais un motif
# local écrit en majuscules (`Vendor/`) laissait passer `vendor/x.py`, qui est le
# MÊME fichier sous NTFS (mesuré : 0 ici, refusé par les jumeaux) : la boucle de
# `juger` lit donc les deux listes, la brute puis celle-ci.
BLOCKED_PATTERNS_LC=$(printf '%s' "$BLOCKED_PATTERNS" | tr '[:upper:]' '[:lower:]')
# Exception scoped to the ".env" pattern ONLY. A committed template carries the
# NAMES of the variables and never their values, and it is precisely the file an
# agent must update when it adds a configuration variable — so the four
# recognized template suffixes are editable. A template is recognized BY ITS
# SUFFIX, never by intent: `.env`, `.env.local`, `.env.production` and anything
# else stay blocked.
# ON THE RISK, stated rather than used as a reason to refuse: if a project puts
# real values in a `.env.example`, this exception makes them editable — but they
# were already committed, hence already leaked and already to be rotated. A path
# guard cannot rattrap that; the class-0 gitleaks gate is what detects it, and it
# still scans whatever content lands on disk here.
# CASE-INSENSITIVE (decision S-01M5X79JTGRSSTB872R4YBPVMF, which replaces
# S-01M5SZJE11): the candidate is folded to lowercase before the suffix test, so
# `.env.EXAMPLE` is a template here as in the Python twins; `.env.LOCAL` and
# `.env.Example.bak` stay refused. The arm line below is kept BYTE FOR BYTE:
# safe-bash.sh extracts the `*…)` arms of this file (Trap 1).
is_env_template() {
  local n
  n=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$n" in
    *.env.example|*.env.sample|*.env.template|*.env.dist) return 0;;
    *) return 1;;
  esac
}

# LE PLI NTFS (T-00000722). Sur la plateforme de développement déclarée du kit
# (Windows/NTFS), `KICKOFF_REQUIRED.`, `KICKOFF_REQUIRED ` et
# `KICKOFF_REQUIRED::$DATA` ouvrent LE MÊME fichier que le nom canonique : Win32
# retire le point et l'espace finaux de chaque segment, et `:` ouvre un flux ADS.
# Même corps que `_nt_fold` des jumeaux Python et que `ntf` du snippet de
# safe-bash.sh — quatre copies, tenues par un différentiel ÉNUMÉRÉ
# (.agents/evals/test_protect_paths_hardening.py). Le chemin passe par STDIN,
# jamais en argv (Git Bash réécrit un argv qui ressemble à un chemin).
#
# DEUX LECTURES d'un segment fait SEULEMENT de points et d'espaces (security-
# code-review à db1a65d9) : la lecture ROGNÉE (`dots=False`) le vide — `...` et
# `.. ` deviennent `` ; la lecture POINTS (`dots=True`) y lit `..` s'il porte au
# moins deux points, `.` sinon. Le hook appelle `f` avec `dots` en ARGUMENT : sa
# DERNIÈRE LIGNE (qui lit `NT_DOTS` dans l'environnement) est coupée à
# `$PP_COUPE` et n'est JAMAIS exécutée par le hook — elle ne sert qu'au
# différentiel énuméré, qui lance `NT_FOLD` seul comme programme autonome
# (`NT_DOTS=1` pour la lecture points). Win32 ne documente le rognage que pour le DERNIER
# élément (Forshaw, Project Zero 2016) : les deux lectures sont jugées, union de
# refus, parce qu'aucune seule ne couvre l'autre (`gates/.. /KICKOFF_REQUIRED`
# n'est refusé que ROGNÉ, `gates/z/.. /KICKOFF_REQUIRED` que POINTS). La
# tabulation n'est pas rognée (caractère interdit dans un nom Win32).
NT_FOLD='import os, sys
def f(p, dots=False):
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
sys.stdout.buffer.write(f(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"), os.environ.get("NT_DOTS") == "1").encode("utf-8", "surrogateescape"))'

# CE QUE LE POINT FIXE CI-DESSOUS ABSORBE, dit pour qu'on ne le cherche pas :
# `NT_NORM` (le `..` que le pli fait naître, exec-critic constat 1 :
# `z/..:s/KICKOFF_REQUIRED` replié vaut `z/../kickoff_required`, que seule la
# renormalisation ramène au marqueur) et `RP_RESOLVE` (le chemin résolu, revue
# de sécurité du lot T-00000721 finding 1 : `x/../<cible>` et un lien vers un
# dossier protégé rendaient 0). Ce sont désormais deux des cinq opérations de
# chaque tour, appliquées à CHAQUE forme et non plus à une seule.

# LE POINT FIXE DES FORMES CANONIQUES (T-00000722 ; revue du lot T-00000721,
# HIGH « pli avant résolution »). La liste FIXE de passes d'avant — brute, LC,
# pli rogné, pli renormalisé, lecture points, puis les mêmes sur la forme
# résolue — n'était pas CLOSE : la résolution physique ne s'appliquait qu'à la
# forme BRUTE, donc une forme obtenue par PLI pouvait encore porter un lien
# symbolique que rien ne résolvait (`ln -s <cible> nom_neutre` puis
# `z/.../nom_neutre` : rc 0, mesuré sur les trois hôtes). `PP_FERMETURE` calcule
# l'ensemble COMPLET comme un POINT FIXE : depuis {brute}, à chaque tour, chaque
# forme ajoute sa casse repliée, ses deux plis NT (`f` de `NT_FOLD`, corps
# INCHANGÉ : le programme exécuté est `NT_FOLD` privé de sa dernière ligne —
# coupée à `$PP_COUPE` —, suivi de celui-ci), sa renormalisation lexicale et sa
# résolution physique (`os.path.realpath`, relative à la racine sous l'une de
# ses orthographes — telle quelle, résolue, à lettre de lecteur `C:/x` ↔ `/c/x`
# (`lecteurs` ; runtime Windows NON mesuré), minusculisée, pliée —, absolue
# sinon). La lecture du pli est un ARGUMENT de `f`, jamais l'environnement : un
# `NT_DOTS` ambiant ne change rien (security-code-review sur 14fc95b5, HIGH 1).
# BORNE : 5 tours, stabilité constatée au plus tard au 5e ; sinon `INSTABLE` et
# REFUS nommé `formes-instables` (fail-closed). POURQUOI 5 : un alias (point,
# espace, flux ADS, détour de points) d'un lien dont la cible porte un segment
# de points (`courte1 -> z/.../courte2`) ne se stabilise qu'au 5e — à 4, ce
# fichier ordinaire était refusé (exec-critic sur fdc7cd75, M2) ; une CHAÎNE de
# tels liens dépasse la borne. La marge mesurée est écrite une seule fois, à
# `canonical_forms` de `.codex/hooks/protect_paths.py`. COÛT : un seul processus
# python au lieu de quatre à neuf ; au plus 5 × 5 opérations par forme, dont un
# realpath.
# SI LA DERNIÈRE LIGNE DE `NT_FOLD` CHANGE (mesuré, exec-critic m3) : SUPPRIMÉE,
# rien n'est coupé et le programme reste juste (`OK`, mêmes formes) ; MODIFIÉE
# sans plus porter `$PP_COUPE`, elle s'EXÉCUTE et consomme STDIN — la fermeture
# lisait alors un chemin vide et rendait `OK` sans aucune forme, brut et LC
# seuls jugés. D'où l'état `VIDE` : STDIN vide ici n'arrive jamais par le
# chemin nominal (`$FILE` est non vide), et tout état autre que `OK` est un
# REFUS nommé.
# Canal : le chemin par STDIN, les formes en sortie séparées par NUL (aucun
# chemin n'en porte), jamais une chaîne re-parsée. SORTIE VIDE = PROGRAMME EN
# ÉCHEC, et c'est un REFUS `formes-illisibles` (binôme de clôture sur ae45e199,
# F1, mesuré) : python est PRÉSENT à ce point — il vient de lire `$FILE` —,
# donc rien ne sort que si ce programme a planté. À f47fa1e8, `RP_RESOLVE`
# était un processus distinct et SURVIVAIT à une panne du pli (`lnk/…`,
# `z/../…` refusés) ; le point fixe en un seul processus supprimait cette
# survie, et « ensemble sauté » laissait passer ces chemins (rc 0, mesuré).
# PYTHON ABSENT est un autre régime, inchangé : `$PY` vide, `$FILE` ne se lit
# pas, sortie 0 avant tout jugement (refus total sous `KIT_CODE_PROTEGE`).
PP_COUPE='sys.stdout.buffer.write'
PP_FERMETURE='
import posixpath
BORNE = 5
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
            out.update((r, r.lower(), f(r)))
    return sorted(out, key=len, reverse=True)
def relativiser(r, rs):
    for s in rs:
        if r == s:
            return "."
        if r.startswith(s + "/"):
            return r[len(s) + 1:]
    return r
def physique(p, root, rs):
    q = p.replace(chr(92), "/")
    if not os.path.isabs(q):
        q = os.path.join(root, q)
    return relativiser(os.path.realpath(q).replace(chr(92), "/"), rs)
def fermer(brut, root):
    rs = racines(root)
    formes = [brut] if brut else []
    vues = set(formes)
    for _ in range(BORNE):
        neuves = []
        for x in formes:
            try:
                ph = physique(x, root, rs)
            except (OSError, ValueError):
                return formes, False
            for y in (x.lower(), f(x), f(x, True), posixpath.normpath(x), ph):
                if y and y not in vues:
                    vues.add(y)
                    neuves.append(y)
        if not neuves:
            return formes, True
        formes.extend(neuves)
    return formes, False
brut = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
formes, stable = fermer(brut, os.environ.get("PP_ROOT") or os.getcwd())
sortie = [("OK" if stable else "INSTABLE") if brut else "VIDE"] + formes[1:]
sys.stdout.buffer.write(b"".join(x.encode("utf-8", "surrogateescape") + bytes(1) for x in sortie))'

# UN SEUL RÉGIME, UN ENSEMBLE DE CANDIDATS (T-00000722). `juger` est appelée sur
# le chemin BRUT, sur `$FILE_LC` (minuscule + `\` → `/`, sans coupe) — tous deux
# calculés par bash seul, donc jugés même python en panne —, puis sur chaque
# forme de l'ensemble `PP_FERMETURE` ; chaque règle teste le candidat TEL
# QU'ELLE LE REÇOIT, sans pli interne. Pourquoi pas le seul pli : il peut
# EFFACER le jeton qui refusait (`x/foo:MCP.JSON` replié vaut `x/foo`), donc la
# forme minusculisée reste jugée, et la forme brute aussi. Un gabarit est
# reconnu SANS CASSE, sur le motif comparé (`.env`, `.ENV`, `.Env` de la liste
# locale) ET sur le candidat (`x.env.EXAMPLE` admis, comme chez les jumeaux —
# décision S-01M5X79JTGRSSTB872R4YBPVMF, qui remplace S-01M5SZJE11). Seul refus
# propre au brut : un motif local à antislash (`a\B\` contre `a\b\x.py`),
# refusé ici, admis par les jumeaux — divergence antislash, épinglée par la
# ligne `ext-antislash-brut` du banc hardening.
# UNION DE REFUS, jamais d'exemption : un gabarit vu sur un candidat ne lève
# jamais le refus d'un autre (`.env.example.` reste refusé). Le message et
# `path=` portent toujours `$FILE` brut.
#
# L-013 N'EST PAS CONTREDIT : il porte sur le piège de NOMMAGE `generated/` et
# sur la liste, qui reste mot pour mot `src/legacy/ generated/ .env`. Ce qui
# change est le CANDIDAT : la casse est repliée par candidat, donc la liste et
# les jetons credential sont désormais insensibles à la casse, alignés sur les
# jumeaux Python (`SRC/LEGACY/x.ts`, `.ENV.LOCAL`, `docs/SecretsRotation.md`
# refusés) — et un `Generated/` est refusé partout, ce que L-013 conseille déjà
# d'éviter.
juger() {
  local c="$1"
  local p
  for p in $BLOCKED_PATTERNS $BLOCKED_PATTERNS_LC; do
    case "$c" in
      *"$p"*)
        if [ "$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')" = ".env" ] && is_env_template "$c"; then
          continue
        fi
        echo "BLOCKED by hook: '$FILE' matches protected pattern '$p' (CLAUDE.md do-not-touch). Ask the user for explicit approval; they can edit .claude/hooks/protected-paths.local or bypass manually." >&2
        bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths "rule=$p" "path=$FILE" >/dev/null 2>&1 || true
        exit 2;;
    esac
  done
  # Never allow writing secrets-looking files. LA LISTE DES JUMEAUX PYTHON,
  # jeton pour jeton (T-00000721) : `SECRET_NAMES` sans `.env` (jugé par la
  # boucle ci-dessus) et `SECRET_EXTENSIONS`.
  case "$c" in
    *id_rsa*|*credential*|*secret*|*private-key*|*private_key*|*.pem|*.key|*.p12|*.pfx|*.crt)
      echo "BLOCKED by hook: '$FILE' looks credential-related. Secrets are never edited by agents." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=credential-pattern "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
  esac
  # MCP configuration is human-audited (.agents/ref/MCP_REGISTRY.md), never
  # agent-writable.
  case "$c" in
    *mcp.json|*.codex/config.toml|*.gemini/settings.json|*.github/copilot/settings.json)
      echo "BLOCKED by hook: MCP configuration is human-audited — see .agents/ref/MCP_REGISTRY.md; agents may not write it." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=mcp-config "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
  esac
  # LES INTERNES GIT (T-00000763 B) : `.git/config` porte `core.hooksPath`,
  # `core.fsmonitor`, `alias.*` — une écriture qui arme une commande. TOUT
  # segment `.git` (sous-module et gitfile compris). UNE SEULE LIGNE, et c'est
  # porteur : safe-bash extrait les bras qui COMMENCENT par `*`, donc éclatée,
  # `.git/*` ne serait plus extrait.
  case "$c" in
    */.git/*|*/.git|.git/*|.git)
      echo "BLOCKED by hook: '$FILE' is inside a .git directory — git internals (config, hooks, info) are never agent-written (T-00000763)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=git-internals "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
  esac
  # The kickoff guard's ARMING FILE (T-00000243). It is the switch of that guard,
  # so it must never be agent-writable: a lock whose key sits in the prisoner's
  # pocket is no lock. This is precisely why the arming lives in a PATH rather than
  # in a board field — `tasks.py unharden` would have travelled through Bash,
  # which no path guard covers, and the constrained agent could have freed itself.
  #
  # CES BRAS SONT EN MINUSCULES ET NE MORDENT QUE SUR UN CANDIDAT REPLIÉ :
  # `.agents\state\gates\KICKOFF_REQUIRED`, `.AGENTS/STATE/GATES/kickoff_required`
  # et le nom canonique ouvrent UN SEUL fichier sous NTFS, et c'est `$FILE_LC`
  # (casse et `\`) puis les formes pliées de `PP_FERMETURE` (point, espace, flux
  # ADS finaux, liens résolus) qui les ramènent à cette forme. Un bras par nom,
  # chacun en tête de ligne `*` :
  # safe-bash en dérive la liste de sa règle du nom.
  case "$c" in
    *.agents/state/gates/kickoff_required)
      echo "BLOCKED by hook: '$FILE' is the kickoff guard's arming file — only the pilot edits it, by hand (T-00000243). Agents may not arm or DISARM themselves." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kickoff-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # MÊME RAISON, AUTRE GARDE (T-00000586). `BINOME_REQUIRED` arme le refus de
    # clore sans revue critique, et il est armé PAR DÉFAUT sur ce dépôt. Sans cette
    # ligne, un agent bloqué par ce refus pourrait le retirer d'une seule écriture
    # — un désarmement d'un geste est exactement ce que la garde existe pour
    # empêcher, et la sortie légitime est `--sans-binome "<pourquoi>"`, qui TRACE.
    *.agents/state/gates/binome_required)
      echo "BLOCKED by hook: '$FILE' arme la revue critique de clôture (UN critique, S-00004500) — seul le pilote le retire, à la main (T-00000586). La sortie d'un agent est \`tasks.py done <id> --raison \"…\" --sans-binome \"<pourquoi>\"\`, qui reste VISIBLE sur le board." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=binome-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # MÊME RAISON, TROISIÈME GARDE (T-00000602). `AFFIRMATION_REQUIRED` arme le
    # refus de FINIR UN TOUR qui a écrit une affirmation durable sans double
    # vérification. Le binôme de clôture a relevé que ce marqueur-ci n'était
    # protégé NULLE PART, quand ses deux jumeaux le sont deux fois : l'agent que
    # la garde contraint pouvait donc la désarmer d'un `Edit` autorisé, ce qui est
    # exactement ce qu'elle existe pour empêcher. La sortie légitime est
    # `AFFIRMATION_SANS_BINOME`, qui est CONSOMMÉE et JOURNALISÉE.
    *.agents/state/gates/affirmation_required)
      echo "BLOCKED by hook: '$FILE' arme le refus d'affirmation non vérifiée — seul le pilote le retire, à la main (T-00000602). La sortie d'un agent est d'écrire sa raison dans \`.agents/state/gates/AFFIRMATION_SANS_BINOME\`, qui est consommée une fois et JOURNALISÉE." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=affirmation-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LA CHAÎNE DE PLAN (T-00000624), et elle est entrée ici APRÈS COUP, ce qui est
    # la leçon à retenir : le binôme de clôture a mesuré que `PLAN_CHAIN_REQUIRED`
    # n'était protégé NULLE PART — ni ici, ni dans `permissions.deny`, ni chez les
    # jumeaux `.codex`/`.gemini` — alors que ses trois aînés le sont tous. Le
    # marqueur n'étant pas encore posé sur ce dépôt, personne n'aurait buté dessus
    # avant l'armement : le trou serait né armé. Un levier neuf doit entrer dans
    # cette liste DANS LE MÊME GESTE que sa garde, jamais dans un lot d'après.
    *.agents/state/gates/plan_chain_required)
      echo "BLOCKED by hook: '$FILE' arme la chaîne de plan — seul le pilote le retire, à la main (T-00000624). La sortie d'un agent est \`tasks.py start <id> --sans-chaine \"<pourquoi>\"\`, dont la raison reste VISIBLE au board." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=plan-chain-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # CINQUIÈME GARDE (T-00000654), entrée DANS LE MÊME GESTE que sa garde — la
    # leçon de `PLAN_CHAIN_REQUIRED` juste au-dessus : un levier neuf rejoint cette
    # liste avec sa garde, jamais dans un lot d'après. `PLAN_CIBLE_REQUIRED` arme le
    # refus de clore, de démarrer (quand une trace d'approbation existe déjà) ou
    # d'enregistrer un verdict `plan-critic` tant que le plan n'annote pas chaque
    # étape d'une cible. Le marqueur DE CE DÉPÔT ne voyage pas ; l'adoptant reçoit
    # sa GRAINE (bras ci-dessous), armée avec `chantier=*` (T-00001093) ; la
    # sortie tracée est `--sans-cible`, jamais un désarmement.
    *.agents/state/gates/plan_cible_required)
      echo "BLOCKED by hook: '$FILE' arme la cible de plan — seul le pilote le retire, à la main (T-00000654). La sortie d'un agent est \`--sans-cible \"<pourquoi>\"\` sur \`tasks.py start|done\` ou \`specs.py add\`, dont la raison reste VISIBLE au board." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=plan-cible-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # SIXIÈME GARDE (T-00001128), et elle est entrée ici UN GESTE APRÈS son
    # armement (f3d47430), par la passe de correction du binôme (S-00003956) —
    # exactement le trou que la règle de `PLAN_CHAIN_REQUIRED` nomme. Le
    # marqueur arme le refus de `tasks.py new` sans mesure ni sortie tracée ;
    # ni semé ni graine à ce jour (T-00001129), seul le pilote le pose.
    *.agents/state/gates/mesure_required)
      echo "BLOCKED by hook: '$FILE' arme la mesure avant d'ouvrir — seul le pilote le retire, à la main (T-00001128). La sortie d'un agent est \`tasks.py new … --mesure \"<cmd> => <observé>\" --motif <M>\` pour un défaut, ou \`--pas-un-defaut \"<pourquoi>\"\` sinon, dont la valeur reste VISIBLE au board." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=mesure-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # SEPTIÈME GARDE (T-01M55Z3ZCS34CDR2EQN1CEBHR7), entrée DANS LE MÊME GESTE
    # que sa graine — la leçon de `PLAN_CHAIN_REQUIRED`. `CHRONO_REQUIRED` arme le
    # refus de `specs.py add` d'un verdict `plan-critic …` sans le chrono du tour.
    # Le marqueur DE CE DÉPÔT n'est pas posé ici (armement réservé à une tâche
    # d'après) ; l'adoptant reçoit sa GRAINE, armée ; la sortie tracée est
    # `--sans-chrono`, jamais un désarmement.
    *.agents/state/gates/chrono_required)
      echo "BLOCKED by hook: '$FILE' arme le chrono du tour de plan — seul le pilote le retire, à la main (T-01M55Z3ZCS34CDR2EQN1CEBHR7). La sortie d'un agent est \`specs.py add … --sans-chrono \"<pourquoi>\"\`, dont la raison rejoint le texte de l'entrée, VISIBLE." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=chrono-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LES GRAINES DES TROIS GARDES DE PIPELINE (T-00001093, décision pilote
    # S-00003693), entrées APRÈS les graines elles-mêmes. `sync_template.py` écrit
    # chacune vers `.agents/state/gates/<NOM>` sur la template : chaque adoptant
    # naît armé de CES octets. Un agent qui les éditerait réarmerait — ou
    # désarmerait — tous les adoptants à venir d'un seul geste : c'est un geste du
    # pilote. Portée MESURÉE, la même que celle des marqueurs du kit : Edit/Write
    # et redirection shell par NOM refusés ; `cp`, `sed -i`, `tee`, `python3 -c`
    # NE le sont PAS — ça empêche l'OUBLI, pas la triche.
    *.agents/adopter-seed/gates/binome_required)
      echo "BLOCKED by hook: '$FILE' est la GRAINE du marqueur BINOME_REQUIRED que la sync template pose chez chaque adoptant (T-00001093) — seul le pilote la modifie, à la main." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=seed-binome-required "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/adopter-seed/gates/plan_chain_required)
      echo "BLOCKED by hook: '$FILE' est la GRAINE du marqueur PLAN_CHAIN_REQUIRED que la sync template pose chez chaque adoptant (T-00001093) — seul le pilote la modifie, à la main." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=seed-plan-chain-required "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/adopter-seed/gates/plan_cible_required)
      echo "BLOCKED by hook: '$FILE' est la GRAINE du marqueur PLAN_CIBLE_REQUIRED que la sync template pose chez chaque adoptant (T-00001093) — seul le pilote la modifie, à la main." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=seed-plan-cible-required "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LA QUATRIÈME GRAINE (T-01M55Z3ZCS34CDR2EQN1CEBHR7), entrée DANS LE MÊME GESTE
    # que la graine elle-même et que le bras de son marqueur armé ci-dessus. Même
    # raison, même portée que les trois du dessus.
    *.agents/adopter-seed/gates/chrono_required)
      echo "BLOCKED by hook: '$FILE' est la GRAINE du marqueur CHRONO_REQUIRED que la sync template pose chez chaque adoptant (T-01M55Z3ZCS34CDR2EQN1CEBHR7) — seul le pilote la modifie, à la main." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=seed-chrono-required "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # QUATRIÈME GARDE (T-00000595), ET ICI LES DEUX FICHIERS SONT PROTÉGÉS, pas
    # seulement l'armement. `PUSH_DEFAUT_PROTEGE` arme le refus de pousser vers la
    # branche par défaut ; `PUSH_DEFAUT_AUTORISE` est sa sortie tracée. La décision
    # pilote est littérale — « je ne veux pas un merge par hasard d'un agent vers
    # main » — donc un agent qui pourrait ÉCRIRE la sortie s'accorderait lui-même
    # la revue humaine que la garde exige, ce qui la viderait entièrement. Le
    # binôme l'a mesuré : un `Write` vers la sortie rendait rc 0 et zéro octet.
    *.agents/state/gates/push_defaut_protege)
      echo "BLOCKED by hook: '$FILE' arme le refus de pousser vers la branche par défaut — seul le pilote le retire, à la main (T-00000595)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=push-defaut-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/state/gates/push_defaut_autorise)
      echo "BLOCKED by hook: '$FILE' est la sortie tracée de « aucun merge vers la branche par défaut sans revue humaine » — SEUL LE PILOTE l'écrit, à la main (T-00000595). Un agent qui l'écrirait s'accorderait la revue qu'elle exige." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=push-defaut-sortie "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LES FICHIERS PILOTE-SEULS (T-00000723, T-00000750). Ce ne sont pas des
    # marqueurs d'une garde, mais leur écriture par un agent vaut une élévation
    # qu'il s'accorderait lui-même. Les deux premiers vivent sous `gates/`, donc
    # ils rejoignent AUSSI la règle du nom de safe-bash ; le suivant non.
    # `AUDIT_LOG` reste écrivable (S-00002524).
    *.agents/state/gates/night_headless.allow)
      echo "BLOCKED by hook: '$FILE' est l'allowlist de la nuit SANS SURVEILLANCE (/night --headless) — seul le pilote l'écrit, à la main (T-00000723). Un agent qui l'écrirait choisirait les outils avec lesquels il tourne quand personne ne regarde." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=night-headless "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/state/gates/mcp_allowlist.md)
      echo "BLOCKED by hook: '$FILE' est le registre d'audit MCP — seul l'humain qui audite y ajoute une ligne (T-00000723, .agents/ref/MCP_REGISTRY.md)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=mcp-allowlist "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LE REGISTRE D'EXCEPTIONS DE LA PORTE CLASS-0 (T-00000844). `.gitleaks.toml`
    # est l'allowlist d'une porte NON LEVABLE : un Edit qui l'élargit exempte un
    # secret, un Edit qui le corrompt éteignait la porte aux deux hooks (Stop et
    # PreToolUse --content). Pilote seul. Le suffixe attrape aussi un
    # `<x>.gitleaks.toml` ou un sous-répertoire — même largeur que ses voisins.
    *.gitleaks.toml)
      echo "BLOCKED by hook: '$FILE' est le registre d'exceptions de la porte secrets class-0, NON LEVABLE — seul le pilote l'édite, à la main (T-00000844). Un vrai secret se retire et se fait tourner ; un faux positif se signale au pilote, qui décide de l'exempter." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=gitleaks-allowlist "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LE REGISTRE D'EXCEPTIONS DU SCANNER UNICODE (T-01M5CN9FM2MPY8Z00AS7FTXXWH),
    # calque de `.gitleaks.toml` : une entrée y admet un caractère invisible ou
    # bidi dans un texte d'instructions, donc l'écrire est un geste du pilote.
    # Hors `gates/`, donc HORS de la règle du nom (arming-marker-name) : safe-bash
    # refuse une redirection vers une cible NON CITÉE par ce SUFFIXE (jusque hors
    # de la racine) ; une cible citée, ou le nom nu après un `cd`, passe — comme
    # `.gitleaks.toml`. Portée : Edit/Write et redirection par chemin refusés ;
    # `cp`, `sed -i`, `tee`, `python -c` passent — ça empêche d'oublier, pas de
    # tricher.
    *.agents/security/unicode-allowlist.json)
      echo "BLOCKED by hook: '$FILE' est le registre d'exceptions du scanner Unicode, réservé au pilote (T-01M5CN9FM2MPY8Z00AS7FTXXWH) : une entrée s'ajoute par sa décision tracée (\`specs.py add --kind decision\`) puis par le pilote, à la main. Un agent qui l'écrirait s'exempterait lui-même d'un caractère invisible." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=unicode-allowlist "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LE JOURNAL DE SPECS (T-00000847, décision pilote). `SPECS.json` est
    # append-only et ne s'écrit QUE par `specs.py` (Python, `save` atomique —
    # jamais l'outil Edit/Write). Il porte les contrats `night-eligible` et le
    # marqueur `night-delivered` que `/night` relit sans surveillance : un Edit
    # d'agent qui en retirerait une entrée rendrait une tâche livrée éligible
    # une nuit de plus. Hors `gates/` : pas dans la règle du nom de safe-bash.
    *.agents/state/specs/specs.json)
      echo "BLOCKED by hook: '$FILE' est le journal de specs, append-only — il ne s'écrit que par \`python .agents/bin/specs.py add\` (T-00000847). Un Edit/Write pourrait effacer un contrat ou un marqueur night-delivered que /night relit sans surveillance." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=specs-journal "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # SA FORME JOURNAL (T-01M4KKMY43ZKCW1YD2Y8JX9MKH, S-01M4KR9W2NSCD5E4T18MW2BESN) : `SPECS.jsonl`, une ligne par
    # entrée, APPEND-ONLY, même règle. La règle `SPECS.json` reste (monolithe de l'adoptant, fenêtre « deux formes »).
    *.agents/state/specs/specs.jsonl)
      echo "BLOCKED by hook: '$FILE' est le journal de specs (forme SPECS.jsonl), append-only — il ne s'écrit que par \`python .agents/bin/specs.py add\` (T-00000847, T-01M4KKMY43ZKCW1YD2Y8JX9MKH). Un Edit/Write pourrait effacer un contrat ou un marqueur night-delivered que /night relit sans surveillance." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=specs-journal "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.claude/settings.local.json)
      echo "BLOCKED by hook: '$FILE' porte les permissions LOCALES de Claude Code — seul le pilote l'écrit (T-00000750). Un agent qui l'écrirait s'accorderait des permissions." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=claude-settings-local "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LE CODE DU KIT, ARMABLE (T-00000763 A) : son armement et ses octrois sont
    # pilote-seuls, pour la raison de la paire PUSH_DEFAUT juste au-dessus.
    *.agents/state/gates/kit_code_protege)
      echo "BLOCKED by hook: '$FILE' arme la garde du code du kit — seul le pilote le pose ou le retire, à la main (T-00000763)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kit-code-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/state/gates/kit_code_autorise)
      echo "BLOCKED by hook: '$FILE' porte les octrois du PILOTE pour écrire le code du kit (T-00000763). Un agent qui l'écrirait s'accorderait l'exception." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kit-code-sortie "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LA CONFIG LINT/FORMAT EXISTANTE (T-01M5C1AHZM41P9C3QH6X7PEQY1), calque de la
    # paire kit-code : son marqueur (suivi, posé par le pilote), ses octrois et sa
    # GRAINE sont pilote-seuls. Les deux premiers vivent sous `gates/` : safe-bash
    # en dérive aussi le refus par le nom.
    *.agents/state/gates/config_qualite_protege)
      echo "BLOCKED by hook: '$FILE' arme le refus de modifier une config lint/format EXISTANTE — seul le pilote le pose ou le retire, à la main (T-01M5C1AHZM41P9C3QH6X7PEQY1). Corrige le code plutôt que d'affaiblir la config." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=config-qualite-arming "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/state/gates/config_qualite_autorise)
      echo "BLOCKED by hook: '$FILE' porte les octrois du PILOTE pour modifier une config lint/format existante (T-01M5C1AHZM41P9C3QH6X7PEQY1). Un agent qui l'écrirait s'accorderait l'exception." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=config-qualite-sortie "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.agents/adopter-seed/gates/config_qualite_protege)
      echo "BLOCKED by hook: '$FILE' est la GRAINE du marqueur CONFIG_QUALITE_PROTEGE que la sync template pose chez chaque adoptant (T-01M5C1AHZM41P9C3QH6X7PEQY1) — seul le pilote la modifie, à la main." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=seed-config-qualite-protege "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LA BANNIÈRE DE MARQUE (T-00001228, S-00004529) : ses données — le message
    # encodé, la clé publique du pilote, `allowed_signers`, `revoked` — et son
    # hook. Un agent qui les écrirait éteindrait la bannière ou désarmerait sa
    # révocation. SOUS-CHAÎNE comme les voisins : un worktree et une copie hors
    # dépôt sont couverts ; safe-bash DÉRIVE ces deux bras pour les
    # redirections. Le retrait légitime passe par un jeton signé posé au poste
    # du pilote (guardrails/SKILL.md § Bannière de marque), jamais par une
    # écriture. Le banc `test_session_banner.py` n'est PAS verrouillé.
    *.agents/security/banner/*)
      echo "BLOCKED by hook: '$FILE' est une donnée de la bannière de marque (message encodé, clé publique, signataires, révocations) — seul le pilote l'écrit, à la main (T-00001228). La bannière se retire par un jeton signé posé au poste du pilote, jamais par une écriture (guardrails/SKILL.md § Bannière de marque)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=banniere-donnees "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    *.claude/hooks/session-banner.sh)
      echo "BLOCKED by hook: '$FILE' est le hook de la bannière de marque — seul le pilote l'écrit, à la main (T-00001228). La bannière se retire par un jeton signé posé au poste du pilote, jamais par une écriture (guardrails/SKILL.md § Bannière de marque)." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=banniere-hook "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
    # LE LANCEUR DES JAMBES ENVELOPPÉES (T-01M4JRFS0T, revue de sécurité
    # S-01M5Y0WXYETFX3KY8A58A4FAKZ) : la règle de contenu admet une jambe de
    # garde sous `garde-fermee.sh` ; ce lanceur réécrit en `exit 0` ferait lire
    # un accord à toutes les jambes qu'il enveloppe. SOUS-CHAÎNE comme les bras
    # de la bannière ; safe-bash le dérive pour les redirections.
    *.agents/security/garde-fermee.sh)
      echo "BLOCKED by hook: '$FILE' est le lanceur des jambes de garde enveloppées (garde-fermee.sh) — seul le pilote l'écrit, à la main (T-01M4JRFS0T). Le réécrire ferait lire un accord à chaque garde qu'il enveloppe." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=garde-fermee "path=$FILE" >/dev/null 2>&1 || true
      exit 2;;
  esac
}

# LE BRUT ET `$FILE_LC` D'ABORD, par bash seul : ils sont jugés même si la
# fermeture plante, et la règle qu'ils touchent garde son nom. PUIS CHAQUE FORME
# DE L'ENSEMBLE (`PP_FERMETURE`, point fixe), union de refus. Le premier
# enregistrement est l'état (`OK` / `INSTABLE` / `VIDE`), les suivants les
# formes autres que la brute ; AUCUN enregistrement (programme en échec) :
# REFUS `formes-illisibles` ci-dessous, jamais un accord (F1).
FILE_LC=$(printf '%s' "$FILE" | tr '[:upper:]' '[:lower:]' | tr '\\' '/')
juger "$FILE"
juger "$FILE_LC"
PP_ETAT=""
PP_FORMES=()
while IFS= read -r -d '' pp_forme; do
  if [ -z "$PP_ETAT" ]; then
    PP_ETAT="$pp_forme"
  else
    PP_FORMES+=("$pp_forme")
  fi
done < <(printf '%s' "$FILE" | PP_ROOT="$CLAUDE_PROJECT_DIR" "$PY" -c "${NT_FOLD%%"$PP_COUPE"*}$PP_FERMETURE" 2>/dev/null)
for pp_forme in "${PP_FORMES[@]}"; do
  juger "$pp_forme"
done
# LA BORNE ATTEINTE SANS STABILITÉ : REFUS NOMMÉ, jamais un jugement partiel.
# Après les formes calculées : une règle vue sur l'une d'elles garde son nom.
if [ "$PP_ETAT" = "INSTABLE" ]; then
  echo "BLOCKED by hook: '$FILE' — ses formes canoniques (plis NTFS, renormalisation, casse, résolution physique) ne se stabilisent pas en 5 tours : refus plutôt qu'un jugement partiel (T-00000722). Cause habituelle : une chaîne de liens symboliques dont les cibles portent des segments de points ; écris le chemin résolu." >&2
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=formes-instables "path=$FILE" >/dev/null 2>&1 || true
  exit 2
fi
# TOUT AUTRE ÉTAT que `OK` — `VIDE`, un programme mal assemblé, ou AUCUN état
# parce que le programme a planté (python présent : il a lu `$FILE`) : le
# chemin n'a pas été lu par la fermeture — REFUS nommé, jamais un accord.
if [ "$PP_ETAT" != "OK" ]; then
  _pp_aucun='aucun (programme en échec)'
  _pp_rien='aucune sortie au rejeu'
  # LA TRACEBACK, CITÉE (binôme de clôture sur 119f81e5) : `2>/dev/null` la
  # jetait au premier passage, et ce refus ne disait pas POURQUOI. Elle n'est
  # pas capturée au passage nominal — la sortie porte des NUL, donc pas de
  # `$(… 2>&1)`, et un fichier `mktemp` + `trap` coûtait +10 à +13 ms sur CHAQUE
  # Edit (mesuré, médiane de 20). La fermeture est REJOUÉE ici seulement, dans
  # cette branche de refus : stderr dans une variable, stdout jeté. Le programme
  # est déterministe et ne fait que lire ; un échec qui ne se reproduit pas au
  # rejeu est dit (« aucune sortie au rejeu »), jamais maquillé.
  PP_ERR_LAST=$(printf '%s' "$FILE" | PP_ROOT="$CLAUDE_PROJECT_DIR" "$PY" -c "${NT_FOLD%%"$PP_COUPE"*}$PP_FERMETURE" 2>&1 >/dev/null | tail -n 1)
  echo "BLOCKED by hook: '$FILE' — la fermeture des formes canoniques a rendu l'état « ${PP_ETAT:-$_pp_aucun} » au lieu de OK : le chemin n'a pas été lu, refus plutôt qu'un jugement partiel (T-00000722) — python : ${PP_ERR_LAST:-$_pp_rien}. Remède : restaurer .claude/hooks/protect-paths.sh (NT_FOLD et PP_FERMETURE) depuis git, et vérifier que python 3 exécute un programme -c." >&2
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=formes-illisibles "path=$FILE" >/dev/null 2>&1 || true
  exit 2
fi

# LA RÈGLE DE CONTENU DE LA BANNIÈRE (T-00001228, S-00004529) —
# `garder_enregistrement_banniere`. Les bras de `juger` jugent un CHEMIN ;
# l'enregistrement de la bannière vit DANS `.claude/settings.json`, qu'on édite
# tous les jours : il se juge sur le CONTENU. La règle SIMULE l'écriture (Write :
# le contenu ; Edit : `old_string` → `new_string` sur l'état actuel) et compare
# l'état d'AVANT à l'état d'APRÈS :
#   - toute GARANTIE présente avant doit l'être après : l'enregistrement, jugé
#     par ÉGALITÉ et jamais par sous-chaîne (L-00000143) — `command` = LE
#     préfixe UNIQUE des jambes protect-paths.sh et safe-bash.sh du MÊME état
#     + la queue `exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/session-banner.sh"`,
#     `shell` = bash, clés EXACTEMENT {type, shell, command} (une liste
#     blanche : ni `timeout`, ni `async`, ni clé future), matcher couvrant
#     `startup`, `resume` ET `clear` (décision pilote S-00004662) —, les
#     jambes de GARDE elles-mêmes (même préfixe : protect-paths.sh à matcher
#     couvrant Edit ET Write, safe-bash.sh à matcher couvrant Bash — en retirer
#     une ou neutraliser son matcher éteindrait, au tour suivant, cette règle ou
#     la garde des redirections), sous DEUX formes fermées (décision pilote
#     S-01M5DJH0BQWAWZ8FS7A947ZXDT, T-01M4JRFS0T) : la NUE, clés EXACTEMENT
#     {type, shell, command} et la queue `exec bash -p` de la jambe, ou
#     l'ENVELOPPÉE, clés EXACTEMENT {type, shell, command, timeout}, queue
#     `AGENTS_HOOK_HOST=claude exec bash -p` + le lanceur
#     `.agents/security/garde-fermee.sh` + `--echeance=N` (N entier ≥ 1) + la
#     garde, et `timeout` entier non booléen, N + 2 ≤ timeout ≤ 600 (un booléen
#     est un int pour python, et tombe sous la borne N + 2 ≥ 3) ; ENVELOPPE
#     est jugée par re.fullmatch, et son préfixe compte dans la règle des deux
#     préfixes (garde_exacte ne le recompare pas : la règle du préfixe unique
#     le tient déjà égal au seul p). Ce préfixe unique doit être CLOS
#     (PREFIXE_CLOS : vide, ou terminé par `;` puis des blancs) : un préfixe
#     ouvert (`env -u `, `true ||`, `echo`) ferait sortir les gardes rc 125
#     ou 0, lus comme un accord (clôture T-01M4JRFS0T). La règle est MONOTONE :
#     une garde garantie ENVELOPPÉE avant l'écriture doit le rester après
#     (garantie « … (enveloppée sous garde-fermee.sh) ») ; le retour à la
#     forme nue est refusé. Un `timeout` sur une jambe NUE est refusé : sans l'échéance
#     interne il n'avance que l'accord (T-00000832 § Gravité). La jambe de la
#     bannière reste à trois clés exactes. Borne héritée : un lanceur ABSENT,
#     ILLISIBLE ou VIDE donne rc 127, 126 ou 0, lu comme un accord (126 et
#     vide mesurés à la clôture T-01M4JRFS0T ; T-01M5CH9GATN) ;
#     et chacune des deux lignes `permissions.deny` de la bannière ;
#   - les clés `env` sont en LISTE BLANCHE (décision pilote S-00004646) :
#     les clés de télémétrie du bloc utilisateur recommandé, admises aussi
#     dans le fichier projet par cette liste, bien que l'hôte les y ignore
#     (T-01M4WNKCBX ; refus en portée projet : décision pilote à prendre ;
#     S-01M4X6HVWK2E67ARX45NV6FB17 : le settings.json du projet n'en porte
#     plus aucune) —
#     CLAUDE_CODE_ENABLE_TELEMETRY, OTEL_EXPORTER_OTLP_ENDPOINT,
#     OTEL_EXPORTER_OTLP_PROTOCOL, OTEL_LOGS_EXPORTER, OTEL_METRICS_EXPORTER,
#     OTEL_METRIC_EXPORT_INTERVAL —, comparés sans la casse ; aucun préfixe
#     (OTEL_EXPORTER_OTLP_HEADERS enverrait des en-têtes, revue de sécurité
#     S-00004661), et OTEL_EXPORTER_OTLP_ENDPOINT doit être une CHAÎNE de forme
#     stricte `http(s)://` + boucle locale (127.0.0.1, localhost, [::1]) + port
#     et chemin facultatifs, jugée par re.fullmatch (BOUCLE_URL) — jamais par
#     urlsplit, qui lisait l'hôte 127.0.0.1 dans `http://tiers\@127.0.0.1`
#     (clôture du lot 95d6220a..c964c9a6, F2) ; casse ASCII seule (re.I | re.A :
#     sous re.I seul, ſ U+017F se repliait sur s, `http://localhoſt` passait —
#     revue de sécurité S-00004713) ; au projet toujours, dans les autres
#     réglages dès qu'il est AJOUTÉ, que sa valeur CHANGE ou que sa clé est
#     RENOMMÉE : hors_boucle rend des couples (clé exacte, valeur), une valeur
#     préexistante sous une clé minuscule inerte ne s'active pas par renommage
#     (S-00004713).
#     Une clé `env` des réglages atteint le shell des hooks — `env.PATH`
#     détourne le `bash` des jambes, `env.SHELLOPTS=noexec` n'en exécute AUCUNE
#     (mesuré, exec-critic it. 2 et 3) — et une liste noire ne se ferme pas.
#     Dans le `.claude/settings.json` du projet, toute clé hors liste est
#     refusée ; dans les autres réglages (utilisateur, qui peuvent porter des
#     clés posées à la main), seule une clé hors liste AJOUTÉE ou dont la
#     VALEUR change est refusée (fichier absent ou illisible avant : toutes ses
#     clés comptent comme ajoutées). Un matcher « couvre »
#     une valeur s'il est absent, vide ou `*`, ou s'il est une liste exacte
#     `[A-Za-z0-9_|]*` qui la contient — RIEN d'autre : une regex, une liste à
#     espace ou à virgule ne couvre jamais une jambe garantie (échec fermé). Deux préfixes
#     distincts parmi ces jambes : l'enregistrement n'est PAS porté — une jambe
#     de garde FACTICE ajoutée ne suffit pas à aligner la bannière sur un
#     préfixe neutre. Coût : une migration du préfixe (T-964) se fait en UNE
#     écriture ; jambe par jambe, elle est refusée dès la première garde ;
#   - l'état d'après ne pose pas `disableAllHooks` (toute valeur autre que
#     `false`, ou l'absence, est refusée).
# PORTÉE : tout `settings.json` / `settings.local.json` dont le dossier parent
# commence par `.claude` — projet, worktree, `~/.claude/`, `~/.claude-op/`.
# REFUS aussi : JSON d'après illisible — lu avec `parse_constant` qui refuse
# NaN, Infinity et -Infinity, que Python accepte et que l'hôte (JSON.parse)
# rejette : un tel état rendrait les réglages illisibles pour l'hôte, gardes
# comprises (revue de sécurité S-00004661) —, Edit non simulable (dont un
# `replace_all` qui n'est pas un booléen JSON), outil autre
# qu'Edit/Write — la branche MultiEdit est RETIRÉE (la doc de l'hôte ne nomme
# plus cet outil, et le matcher `Edit|Write` est une liste EXACTE). Un programme
# qui ne rend pas de verdict lisible est un REFUS, jamais un accord.
# AUCUN BRAS DE `case` QUI COMMENCE PAR UNE ÉTOILE ICI : safe-bash extrairait
# le motif et étendrait la garde des redirections ; le tri de portée commence
# par `?*`. Python ABSENT : `$FILE` ne se lit pas, sortie 0 plus haut — la règle
# est éteinte, comme tout le régime historique (dit dans guardrails/SKILL.md).
# Canal : les formes séparées par NUL, un NUL vide, puis la charge ; le verdict
# en retour est `OK` ou `REFUS<tab><règle><tab><motif>`.
PP_BANNIERE='
import json, re
QUEUE ="exec bash -p \"$CLAUDE_PROJECT_DIR/.claude/hooks/"
JAMBE = QUEUE + "session-banner.sh\""
ANCRES = (QUEUE + "protect-paths.sh\"", QUEUE + "safe-bash.sh\"")
DENY = ("Edit(./.agents/security/banner/**)", "Edit(./.claude/hooks/session-banner.sh)")
LISTE_EXACTE = re.compile(r"[A-Za-z0-9_|]*")
CLES = {"type", "shell", "command"}
ENVELOPPE = re.compile(r"(.*)AGENTS_HOOK_HOST=claude exec bash -p \"[$]CLAUDE_PROJECT_DIR/[.]agents/security/garde-fermee[.]sh\" --echeance=([1-9][0-9]*) \"[$]CLAUDE_PROJECT_DIR/[.]claude/hooks/(protect-paths[.]sh|safe-bash[.]sh)\"", re.S)
PREFIXE_CLOS = re.compile(r"(?:.*;)?[ \t\n]*", re.S)
DELAI_MAX = 600
GARDES = (
    (ANCRES[0], ("Edit", "Write"), "jambe protect-paths.sh sur Edit et Write"),
    (ANCRES[1], ("Bash",), "jambe safe-bash.sh sur Bash"),
)
ENV_PERMISES = ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL",
                "OTEL_LOGS_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_METRIC_EXPORT_INTERVAL")
BOUCLE_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~/-]*)?", re.I | re.A)
SOURCES = ("startup", "resume", "clear")
NOMS = ("settings.json", "settings.local.json")
class Refus(Exception):
    pass
def objet(x):
    return x if isinstance(x, dict) else {}
def liste(x):
    return x if isinstance(x, list) else []
def permise(k):
    k = str(k).upper()
    return k in ENV_PERMISES
def hors_boucle(doc):
    sortie = []
    for k, v in objet(objet(doc).get("env")).items():
        if str(k).upper() == "OTEL_EXPORTER_OTLP_ENDPOINT":
            if not (isinstance(v, str) and BOUCLE_URL.fullmatch(v)):
                sortie.append((str(k), str(v)))
    return sortie
def _constante(c):
    raise ValueError(c)
def hors_liste(doc):
    return {(str(k).upper(), json.dumps(v, sort_keys=True)) for k, v in objet(objet(doc).get("env")).items() if not permise(k)}
def est_projet(formes):
    return any(f(x) == ".claude/settings.json" for x in formes)
def dans_portee(formes):
    for x in formes:
        segs = f(x).split("/")
        if len(segs) >= 2 and segs[-1] in NOMS and segs[-2].startswith(".claude"):
            return True
    return False
def couvre(m, valeur):
    if m is None or m == "" or m == "*":
        return True
    if isinstance(m, str) and LISTE_EXACTE.fullmatch(m):
        return valeur in m.split("|")
    return False
def jambes(doc, evenement):
    for b in liste(objet(objet(doc).get("hooks")).get(evenement)):
        for h in liste(objet(b).get("hooks")):
            if isinstance(h, dict):
                yield objet(b), h
def prefixes(doc):
    vus = set()
    for _, h in jambes(doc, "PreToolUse"):
        c = h.get("command")
        for a in ANCRES:
            if isinstance(c, str) and c.endswith(a):
                vus.add(c[:len(c) - len(a)])
        m = ENVELOPPE.fullmatch(c) if isinstance(c, str) else None
        if m is not None:
            vus.add(m.group(1))
    return vus
def jambe_exacte(h, attendu):
    return set(h) == CLES and h.get("type") == "command" and h.get("shell") == "bash" and h.get("command") == attendu
def garde_exacte(h, p, queue):
    if set(h) == CLES:
        return jambe_exacte(h, p + queue)
    c = h.get("command")
    m = ENVELOPPE.fullmatch(c) if isinstance(c, str) else None
    if set(h) != CLES | {"timeout"} or m is None:
        return False
    t = h.get("timeout")
    if not isinstance(t, int):
        return False
    return h.get("type") == "command" and h.get("shell") == "bash" and QUEUE + m.group(3) + "\"" == queue and int(m.group(2)) + 2 <= t <= DELAI_MAX
def garanties(doc):
    g = set()
    if not isinstance(doc, dict):
        return g
    vus = prefixes(doc)
    if len(vus) == 1 and all(PREFIXE_CLOS.fullmatch(x) for x in vus):
        for p in vus:
            for b, h in jambes(doc, "SessionStart"):
                if all(couvre(b.get("matcher"), v) for v in SOURCES) and jambe_exacte(h, p + JAMBE):
                    g.add("enregistrement session-banner.sh")
            for queue, valeurs, nom in GARDES:
                for b, h in jambes(doc, "PreToolUse"):
                    if all(couvre(b.get("matcher"), v) for v in valeurs) and garde_exacte(h, p, queue):
                        g.add(nom)
                        if set(h) != CLES:
                            g.add(nom + " (enveloppée sous garde-fermee.sh)")
    deny = liste(objet(doc.get("permissions")).get("deny"))
    for d in DENY:
        if d in deny:
            g.add(d)
    return g
def lire_actuel(brut, racine):
    q = brut if os.path.isabs(brut) else os.path.join(racine, brut)
    try:
        with open(q, "rb") as fh:
            return fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
def simuler(charge, actuel):
    outil = charge.get("tool_name")
    ti = objet(charge.get("tool_input"))
    if outil == "Write":
        c = ti.get("content")
        if not isinstance(c, str):
            raise Refus("banniere-reglages-illisibles", "Write sans contenu texte vers des réglages Claude Code")
        return c
    if outil == "Edit":
        if "replace_all" in ti and not isinstance(ti["replace_all"], bool):
            raise Refus("banniere-edit-non-simulable", "replace_all doit etre un booleen JSON (true ou false) : une autre valeur, que l hote pourrait convertir, ne se simule pas")
        a = ti.get("old_string")
        n = ti.get("new_string")
        if actuel is None or not isinstance(a, str) or not isinstance(n, str) or a == "" or a not in actuel:
            raise Refus("banniere-edit-non-simulable", "cet Edit de réglages Claude Code ne se simule pas sur le fichier actuel (absent ou illisible, ou old_string introuvable)")
        return actuel.replace(a, n) if ti.get("replace_all") is True else actuel.replace(a, n, 1)
    raise Refus("banniere-outil-inconnu", "outil %r non simulé sur des réglages Claude Code (Edit et Write seuls, MultiEdit retiré)" % (outil,))
donnees = sys.stdin.buffer.read()
coupe = donnees.find(bytes(2))
formes = [x.decode("utf-8", "surrogateescape") for x in donnees[:coupe].split(bytes(1))]
charge = json.loads(donnees[coupe + 2:])
sortie = "OK"
if coupe > 0 and dans_portee(formes):
    try:
        if not isinstance(charge, dict):
            raise Refus("banniere-reglages-illisibles", "charge de outil illisible (pas un objet JSON)")
        actuel = lire_actuel(formes[0], os.environ.get("PP_ROOT") or os.getcwd())
        try:
            avant = json.loads(actuel) if actuel is not None else None
        except ValueError:
            avant = None
        texte = simuler(charge, actuel)
        try:
            apres = json.loads(texte, parse_constant=_constante)
        except ValueError:
            raise Refus("banniere-reglages-illisibles", "réglages illisibles après écriture (JSON invalide)") from None
        if not isinstance(apres, dict):
            raise Refus("banniere-reglages-illisibles", "réglages après écriture : pas un objet JSON")
        if "disableAllHooks" in apres and apres.get("disableAllHooks") is not False:
            raise Refus("banniere-disable-all-hooks", "cette écriture pose disableAllHooks, qui couperait la bannière de marque et toutes les gardes")
        nouvelles = hors_liste(apres) if est_projet(formes) else hors_liste(apres) - hors_liste(avant)
        if nouvelles:
            raise Refus("banniere-env-hors-liste", "clé env hors de la liste blanche du kit (CLAUDE_CODE_ENABLE_TELEMETRY et les cinq OTEL_ du bloc utilisateur recommandé) : " + ", ".join(sorted(set(k for k, _ in nouvelles))) + " ; refusée dans les réglages du projet, ailleurs si elle est ajoutée ou si sa valeur change ; une clé env des réglages atteint le shell des hooks (PATH, SHELLOPTS=noexec mesurés) ; en ajouter une au kit est un geste du pilote (S-00004646)")
        if est_projet(formes) and hors_boucle(apres):
            raise Refus("banniere-otel-hors-boucle", "OTEL_EXPORTER_OTLP_ENDPOINT des réglages du projet hors de la boucle locale (127.0.0.1, localhost, ::1 seuls) : " + ", ".join(v for _, v in hors_boucle(apres)) + " ; la télémétrie du kit ne quitte pas le poste par une écriture")
        ajoutes = [c for c in hors_boucle(apres) if c not in hors_boucle(avant)]
        if not est_projet(formes) and ajoutes:
            raise Refus("banniere-otel-hors-boucle", "OTEL_EXPORTER_OTLP_ENDPOINT hors de la boucle locale (127.0.0.1, localhost, ::1 seuls) AJOUTÉ, CHANGÉ ou RENOMMÉ par cette écriture de réglages : " + ", ".join(k + "=" + v for k, v in ajoutes) + " ; une valeur préexistante inchangée sous sa clé exacte reste tolérée, la télémétrie ne quitte pas le poste par une écriture")
        perdues = sorted(garanties(avant) - garanties(apres))
        if perdues:
            raise Refus("banniere-enregistrement", "cette écriture retire ou altère une garantie de la bannière de marque : " + ", ".join(perdues))
    except Refus as e:
        sortie = "REFUS" + chr(9) + e.args[0] + chr(9) + e.args[1]
elif coupe <= 0:
    sortie = "ILLISIBLE"
sys.stdout.buffer.write(sortie.encode("utf-8"))'
PP_TAB="$(printf '\t')"
garder_enregistrement_banniere() {
  local verdict regle motif
  verdict=$( { printf '%s\0' "$FILE" "$FILE_LC" "${PP_FORMES[@]}"; printf '\0'; printf '%s' "$INPUT"; } | PP_ROOT="$CLAUDE_PROJECT_DIR" "$PY" -c "${NT_FOLD%%"$PP_COUPE"*}$PP_BANNIERE" 2>/dev/null)
  case "$verdict" in
    OK)
      return 0 ;;
    REFUS"$PP_TAB"?*"$PP_TAB"?*)
      regle=${verdict#REFUS"$PP_TAB"}
      motif=${regle#*"$PP_TAB"}
      regle=${regle%%"$PP_TAB"*}
      echo "BLOCKED by hook: '$FILE' — $motif (règle $regle, T-00001228 ; guardrails/SKILL.md § Bannière de marque). Le retrait de la bannière passe par un jeton signé au poste du pilote, jamais par les réglages." >&2
      bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths "rule=$regle" "path=$FILE" >/dev/null 2>&1 || true
      exit 2 ;;
  esac
  echo "BLOCKED by hook: '$FILE' — la règle de contenu de la bannière (garder_enregistrement_banniere) n'a pas rendu de verdict lisible : refus plutôt qu'accord (T-00001228). Remède : vérifier que python 3 exécute un programme -c, et restaurer .claude/hooks/protect-paths.sh depuis git." >&2
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=banniere-regle-illisible "path=$FILE" >/dev/null 2>&1 || true
  exit 2
}
# Le tri de portée, par bash : un SUR-ENSEMBLE (un `.claude…` n'importe où au-dessus
# d'un `settings*.json` visé) ; le programme refait le tri exact. Motifs en `?*`.
PP_REGLAGES=0
for pp_forme in "$FILE_LC" "${PP_FORMES[@]}"; do
  case "$pp_forme" in
    ?*/.claude*/settings.json|?*/.claude*/settings.local.json) PP_REGLAGES=1 ;;
    .claude*/settings.json|.claude*/settings.local.json) PP_REGLAGES=1 ;;
  esac
done
if [ "$PP_REGLAGES" = 1 ]; then
  garder_enregistrement_banniere
fi

# LA CONFIG LINT/FORMAT EXISTANTE (T-01M5C1AHZM41P9C3QH6X7PEQY1), APRÈS les règles
# absolues et AVANT le code du kit : un octroi ne lève que CE refus-ci, et le bloc
# kit-code juge encore le même chemin. SEULEMENT si le marqueur existe — absent,
# rien n'est chargé. La décision est dans .agents/bin/config_qualite_guard.py (0 rien,
# 3 octroi, 2 refus) ; tout autre code, le module absent, un rc 0 SANS le verdict
# positif `CONFIG_QUALITE_OK` comme sortie entière (module vide, `sys.exit(0)` à
# l'import), ou un rc 3 SANS le préfixe `CONFIG_QUALITE_OCTROI ` (`sys.exit(3)` à
# l'import), est un refus nommé `config-qualite-illisible`. Les formes (brut, LC, ensemble) passent par STDIN,
# séparées par NUL — jamais en argv, que Git Bash réécrit. Aucun bras de `case` ici :
# safe-bash extrairait un motif de ce bloc. PYTHON ABSENT : sortie 0 plus haut,
# régime historique (décision pilote S-01M5CD5753GQ5KXWSXTTF9CM02).
CQ_MARQUEUR="$CLAUDE_PROJECT_DIR/.agents/state/gates/CONFIG_QUALITE_PROTEGE"
if [ -f "$CQ_MARQUEUR" ]; then
  CQ_GARDE="$CLAUDE_PROJECT_DIR/.agents/bin/config_qualite_guard.py"
  if [ ! -f "$CQ_GARDE" ]; then
    echo "BLOCKED by hook: CONFIG_QUALITE_PROTEGE est posé mais .agents/bin/config_qualite_guard.py est absent — aucune écriture ne peut être jugée (T-01M5C1AHZM41P9C3QH6X7PEQY1). Remède : restaurer ce fichier (git checkout), ou le pilote retire .agents/state/gates/CONFIG_QUALITE_PROTEGE." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=config-qualite-illisible "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  fi
  CQ_SORTIE=$(printf '%s\0' "$FILE" "$FILE_LC" "${PP_FORMES[@]}" | "$PY" "$CQ_GARDE" --root "$CLAUDE_PROJECT_DIR" 2>&1)
  CQ_RC=$?
  CQ_PREFIXE='CONFIG_QUALITE_OCTROI '
  CQ_LIGNE=${CQ_SORTIE#"$CQ_PREFIXE"}
  if [ "$CQ_RC" -eq 3 ] && [ "$CQ_LIGNE" != "$CQ_SORTIE" ]; then
    echo "NOTE by hook: '$FILE' est une config lint/format existante, écrite sous l'octroi pilote « $CQ_LIGNE » (T-01M5C1AHZM41P9C3QH6X7PEQY1)." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.warn guard=protect-paths rule=config-qualite-octroi "path=$FILE" >/dev/null 2>&1 || true
  elif [ "$CQ_RC" -eq 2 ]; then
    echo "$CQ_SORTIE" >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=config-qualite "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  elif [ "$CQ_RC" -ne 0 ] || [ "$CQ_SORTIE" != "CONFIG_QUALITE_OK" ]; then
    echo "BLOCKED by hook: CONFIG_QUALITE_PROTEGE est posé et .agents/bin/config_qualite_guard.py a échoué (rc $CQ_RC) ou n'a pas rendu son verdict positif (CONFIG_QUALITE_OK en rc 0, le préfixe CONFIG_QUALITE_OCTROI en rc 3) — refus plutôt qu'accord par défaut (T-01M5C1AHZM41P9C3QH6X7PEQY1). Sortie reçue (200 premiers caractères) : « ${CQ_SORTIE:0:200} ». Remède : réparer ce fichier, ou le pilote retire .agents/state/gates/CONFIG_QUALITE_PROTEGE." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=config-qualite-illisible "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  fi
fi

# LE CODE DU KIT (T-00000763 A), APRÈS les règles absolues : un octroi ne lève
# que CE refus-ci. SEULEMENT si le marqueur existe — livré DÉSARMÉ, donc sur ce
# dépôt ce bloc ne s'ouvre pas. La décision est dans .agents/bin/kit_code_guard.py
# (0 rien, 3 octroi, 2 refus) ; tout autre code est un refus, jamais un accord.
# Aucun bras de `case` ici : safe-bash extrairait un motif de ce bloc. La garde
# reçoit L'ENSEMBLE (brut, LC, formes) et le referme encore elle-même.
KIT_MARQUEUR="$CLAUDE_PROJECT_DIR/.agents/state/gates/KIT_CODE_PROTEGE"
if [ -f "$KIT_MARQUEUR" ]; then
  KIT_GARDE="$CLAUDE_PROJECT_DIR/.agents/bin/kit_code_guard.py"
  if [ ! -f "$KIT_GARDE" ]; then
    echo "BLOCKED by hook: KIT_CODE_PROTEGE est posé mais .agents/bin/kit_code_guard.py est absent — aucune écriture ne peut être jugée (T-00000763). Remède : restaurer ce fichier (git checkout), ou le pilote retire .agents/state/gates/KIT_CODE_PROTEGE." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kit-code-guard-illisible "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  fi
  KIT_SORTIE=$("$PY" "$KIT_GARDE" --root "$CLAUDE_PROJECT_DIR" -- "$FILE" "$FILE_LC" "${PP_FORMES[@]}" 2>&1)
  KIT_RC=$?
  if [ "$KIT_RC" -eq 3 ]; then
    echo "NOTE by hook: '$FILE' est du code du kit, écrit sous l'octroi pilote « $KIT_SORTIE » (T-00000763)." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.warn guard=protect-paths rule=kit-code-octroi "path=$FILE" >/dev/null 2>&1 || true
    exit 0
  fi
  if [ "$KIT_RC" -eq 2 ]; then
    echo "$KIT_SORTIE" >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kit-code "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  fi
  if [ "$KIT_RC" -ne 0 ]; then
    echo "BLOCKED by hook: KIT_CODE_PROTEGE est posé et .agents/bin/kit_code_guard.py a échoué (rc $KIT_RC) — refus plutôt qu'accord par défaut (T-00000763). Remède : réparer ce fichier, ou le pilote retire .agents/state/gates/KIT_CODE_PROTEGE." >&2
    bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.deny guard=protect-paths rule=kit-code-guard-illisible "path=$FILE" >/dev/null 2>&1 || true
    exit 2
  fi
fi
exit 0
