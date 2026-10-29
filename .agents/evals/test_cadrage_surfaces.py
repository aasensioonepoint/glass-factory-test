#!/usr/bin/env python3
"""Témoin des relais du cadrage dans les commandes et les routeurs (T-01M5AVF2MC8Y9SFYBK63NY4EAK, cadrage B).

La règle vit UNE fois, dans `.agents/skills/planning/SKILL.md` § Le cadrage (cadrage A, avec
`.agents/skills/kickoff/SKILL.md` § CADRAGE FIRST) ; les surfaces de B la RENVOIENT par nom, sans
reformuler aucune condition. Ce banc tient :
  * LISTES — les quatre listes `start` (ouvertes par « `start` reste pour » / « `start` stays for »)
    portent le 4e cas DANS la liste, de son littéral d'ouverture à la fin de sa phrase ; un littéral
    posé ailleurs dans le fichier ne compte pas ; les anciennes formulations (« du précédent »,
    « previous child is MERGED ») y sont refusées ;
  * ROUTEURS — « cadrage (cadrage_plan.py) » précède le jeton de détection RÉELLEMENT présent :
    `language-detector` (ligne `Pipeline mandatory` d'AGENTS.md, item 1 du miroir Copilot),
    « language detector » (item 2 de README-OTHER-HOSTS.md) ;
  * RELAIS — la CLI et le bloc `CADRAGE <T>` … `FIN CADRAGE` dans les trois commandes ; dans
    kickoff.md, AVANT « Show me its routing plan » ; dans /planning et /planning-all, EN TÊTE de la
    restitution, `découper` vers `/kickoff`, sans écriture au board ; les deux titres `lot <K> : …` ;
  * ACCORD AVEC A — les renvois se résolvent (titre de section présent), le libellé EN est celui de
    la kickoff SKILL, et l'ordre des `done` de la section renvoyée tient ;
  * `kickoff.md:179` porte toujours « Record the FINAL verdict » (0 ligne insérée avant) ;
  * VOYAGE — les sept chemins de B sont pris (TAKE) par `sync_template` (sauté, et dit, sans lui).

Étendu par le cadrage C1 (T-01M5AVF4FRY2GQ7GN74PFE91E8) aux orchestrateurs Claude et Codex :
  * LISTES — leur liste `start` porte `CAS_EN` DANS la liste (même règle que B) ;
  * RANGÉE — la rangée CALLING SESSION de `cadrage_plan.py` OUVRE le `PIPELINE:` (arbitrage
    S-01M5B5B36R : avant deps-ready, comme 2bis avant 3-amont dans la kickoff SKILL), puis
    deps-ready, `language-detector`, planner, dans cet ordre ; elle porte le relais EN PREMIER du
    bloc, « none on the DIRECT route … » et le renvoi `découper` vers § Le cadrage ;
  * PLAFOND — la ligne du plafond (45 lignes, Claude et Codex depuis l'arbitrage S-01M5BFKA2D) dit le bloc
    relayé hors plafond ;
  * DIRECT — la règle de la route directe dit qu'elle n'a pas de rangée cadrage, et son refus vers le planner
    fait jouer le cadrage par la session appelante (relais et verdicts de la rangée, deps-ready déjà lu) ;
    « never to your judgment » y reste ;
  * SANS SHELL — `tools: Read, Grep, Glob` (Claude) et `sandbox_mode = "read-only"` (Codex) ;
  * VOYAGE — les quatre chemins de C1 sont pris (TAKE).
Étendu par le cadrage C2 (T-01M5AVF6AHW0KTBSWM3ZX77Z6P) aux orchestrateurs Gemini, Copilot et Kimi
(cas `C2SurfacesTests::test_gemini`, `::test_copilot`, `::test_kimi`) :
  * Gemini et Kimi — les règles C1 (liste, rangée en tête du `PIPELINE:` avant deps-ready, relais,
    plafond, jetons DIRECT) plus le commentaire C1 de `1. language-detector`, aucune rangée dans la
    règle DIRECT, et un frontmatter `tools:` sans shell ;
  * Copilot (déf condensée sous 30 000 points de code) — UNE rangée sous `**Dependencies first**`,
    avant la ligne deps-ready, avec les jetons du brouillon mesuré (réserve C14) ; `**ORDER,
    EXPLICITLY**` situe cadrage puis deps-ready avant `language-detector` ; `**Direct route**` porte
    `JETONS_DIRECTE`, le refus vers cadrage avant planner et « never your judgment » (réserve C13),
    sans rangée ;
  * les trois listes `start` portent `CAS_EN` DANS la liste ; VOYAGE — les cinq chemins de C2 (TAKE).
Étendu par la passe de correction de la revue de clôture globale (parent T-01M5AN76HCMVQ1DDCZTB3J2K1J) :
  * PORTÉE (T2, arbitrage S-01M5BFKA2D) — `PORTEE_EN` / `PORTEE_FR` sur chaque surface qui exécute ou route ;
  * R1 (T3) — l'exception écrite de la découpe dans la ligne R1 d'AGENTS.md et de son miroir Copilot ;
  * LISTES — chaque liste `start` garde `/night` et les reprises ; GUILLEMETS — aucun chemin nu ;
  * M-f, M-g (fin de section obligatoire), M-h (renvoi des `done` dans le paragraphe du lot) ;
  * C1 — clause du refus de direct, repli exact, « never to your judgment », rangée en double sous toute forme ;
  * Copilot — aucun plafond de lignes fantôme (T10), éligibilité lue dans le bon sens (T9), objets de :17 et :19.
Le paquet `cadre` est lu où qu'il vive (`.agents/vendor/cadre/` d'abord, sinon `src/cadre/`), par
`vendor_paths.py` chargé par chemin (`cadre_rel`). La parité de `data/roster/orchestrator.json` avec les défs est jugée par
`.agents/evals/test_cadre_roster.py`, pas ici ; la longueur de la déf Copilot, par
`.agents/evals/test_copilot_def_plafond.py`.

Le cadrage reste HORS de `data/socle.json` du paquet `cadre` (arbitrage S-01M5B2M28W) : socle.json déclare la chaîne des GATES du noyau, et `cadrage_plan.py` est une mesure en lecture seule avant toute planification, sans verdict bloquant — pas un nœud de gate.

Chaque famille de fautes est une fonction PURE sur un dict {chemin: texte} ; les tests `Etalonnage*`
la rejouent sur des copies mutées en mémoire et exigent une faute qui nomme la surface.
Borne : le banc lit des LITTÉRAUX ; il ne juge pas qu'une surface est vraie, seulement qu'elle dit
le même renvoi au même endroit.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"


def _vendor_paths():
    """`vendor_paths.py` chargé PAR CHEMIN (patron v3prep) : `sys.path` n'est pas touché."""
    spec = importlib.util.spec_from_file_location("_cadrage_surfaces_vendor_paths", BIN / "vendor_paths.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


VP = _vendor_paths()


def cadre_rel(racine: Path = ROOT) -> str:
    """Le paquet `cadre` relatif à `racine`, où qu'il vive (le neuf gagne) ; absent : l'ancien lieu, nommé au refus."""
    dossier = VP.dossier_paquet(racine, "cadre")
    return (dossier.relative_to(Path(racine).resolve()) if dossier else VP.ANCIENS["cadre"]).as_posix()


ROSTER_ORCH = f"{cadre_rel()}/data/roster/orchestrator.json"

KICKOFF_CMD = ".claude/commands/kickoff.md"
PLANNING_CMD = ".claude/commands/planning.md"
PLANNING_ALL_CMD = ".claude/commands/planning-all.md"
AGENTS = "AGENTS.md"
COPILOT = ".github/copilot-instructions.md"
README = "README-OTHER-HOSTS.md"
PLANNING_SKILL = ".agents/skills/planning/SKILL.md"
KICKOFF_SKILL = ".agents/skills/kickoff/SKILL.md"
WRITE_SET = (KICKOFF_CMD, PLANNING_CMD, PLANNING_ALL_CMD, AGENTS, COPILOT, README,
             ".agents/evals/test_cadrage_surfaces.py")
ORCH_MD = ".claude/agents/orchestrator.md"
ORCH_TOML = ".codex/agents/orchestrator.toml"
WRITE_SET_C1 = (ORCH_MD, ORCH_TOML, ROSTER_ORCH, ".agents/evals/test_cadrage_surfaces.py")
ORCH_GEMINI = ".gemini/agents/orchestrator.md"
ORCH_COPILOT = ".github/agents/orchestrator.agent.md"
ORCH_KIMI = ".kimi-code/agents/orchestrator.md"
WRITE_SET_C2 = (ORCH_GEMINI, ORCH_COPILOT, ORCH_KIMI, ROSTER_ORCH, ".agents/evals/test_cadrage_surfaces.py")
LUS = (KICKOFF_CMD, PLANNING_CMD, PLANNING_ALL_CMD, AGENTS, COPILOT, README, PLANNING_SKILL, KICKOFF_SKILL,
       ORCH_MD, ORCH_TOML, ORCH_GEMINI, ORCH_COPILOT, ORCH_KIMI)

RENVOI = "(`.agents/skills/planning/SKILL.md` § Le cadrage)"
CAS_FR = ("l'enfant suivant d'une découpe de cadrage, après la FUSION des enfants qu'il attend " + RENVOI
          + ", puis `fournee` si son plan porte des `LOT:`")
CAS_EN = ("the next child of a cadrage cut, after the MERGE of the earlier children it waits for " + RENVOI
          + ", then `fournee` if its plan carries `LOT:` lines")
ANCIENS = ("du précédent", "previous child is MERGED")
LISTES = {
    KICKOFF_CMD: ("`start` reste pour", CAS_FR),
    AGENTS: ("`start` reste pour", CAS_FR),
    COPILOT: ("`start` stays for", CAS_EN),
    README: ("`start` stays for", CAS_EN),
}

CADRAGE = "cadrage (cadrage_plan.py)"
CLI = "bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task"
BLOC = "`CADRAGE <T>` … `FIN CADRAGE`"
ROUTAGE = "Show me its routing plan"
TITRES_LOT = ("`lot <K> : Plan @ <sha> - <objet>`", "`lot <K> : plan-critic <VERDICT> (iteration <n>/<N>)`")
# Paragraphe de chaque commande de planification : (ouverture, fin exclue, jetons exigés).
PARAGRAPHES = {
    PLANNING_CMD: ("**Le cadrage d'abord**", "**L'amont d'abord**",
                   ("avant l'étape 1", CLI, BLOC, "EN TÊTE de la restitution", "mot pour mot par `communicator`",
                    "`Verdict : découper`", "`/kickoff`", "`/planning` n'écrit pas le board")),
    PLANNING_ALL_CMD: ("**Le cadrage, avant la phase 2**", "4. **Le graphe de specs",
                       (CLI, BLOC, "EN TÊTE de la restitution", "mot pour mot par `communicator`",
                        "`Verdict : découper`", "`/kickoff`", "`/planning-all` n'écrit pas le board pour elle",
                        "sans arête `depends_on`", "chaque arête `DÉPEND` coûte une porte")),
}
ECRITURE_BOARD = "tasks.py new"
RENVOI_DONE = "une découpe de cadrage clôt ses `done` dans l'ordre de `.agents/skills/planning/SKILL.md` § Le cadrage"
# Ordre de clôture de la section renvoyée (A) : (début de section, fin de section, jetons dans l'ordre).
ORDRE_DONE = {
    PLANNING_SKILL: ("## Le cadrage — AVANT tout planner", "\n## ",
                     ("puis `done` des lots de fournée", "puis des autres enfants (toujours `running`)",
                      "PUIS du dernier", "PUIS du parent par")),
    KICKOFF_SKILL: ("**§ CADRAGE FIRST — step 2bis, in full**", "\n3-amont.",
                    ("then `done` of the batch lots", "of the other children (still `running`",
                     "THEN the last child", "THEN the parent with")),
}
LIGNE_179 = "Record the FINAL verdict"
# Passe de correction de la revue de clôture globale (parent T-01M5AN76HCMVQ1DDCZTB3J2K1J).
#: T2 (arbitrage S-01M5BFKA2D) — le cadrage se joue une fois, avant le PREMIER planner ; ni reprise, ni révision,
#: ni enfant d'une découpe. Un libellé EN et un FR, les mêmes sur chaque surface qui EXÉCUTE ou route.
PORTEE_EN = "a resumption, a revision or a child of a cadrage cut"
PORTEE_FR = "ni sur une reprise, une révision ou un enfant d'une découpe"
#: T3 — l'exception écrite à R1 FERMER AVANT D'OUVRIR, dans la ligne R1 du routeur et de son miroir.
R1_EXCEPTION = ("exception écrite : l'enfant suivant d'une découpe de cadrage (S-01M5ATNMNBYQGYF65SNNZ5JHBN), dont "
                "les `done` se ferment ensemble sous la porte unique de la découpe")
R1_ANCRES = {AGENTS: "**(R1) FERMER AVANT D'OUVRIR**", COPILOT: "**(R1) FERMER AVANT D'OUVRIR**"}
#: T13 — les chemins des commandes composées entre guillemets doubles : jamais `--file <`, `--part <`, `--chantier <`.
CHEMIN_NU = re.compile(r"--(?:file|part|chantier) <")
CHEMIN_GUILLEMETS = re.compile(r'--file "<[^"]+>"')
#: Chaque liste `start` garde ses cas anciens : `/night` et les reprises (C2, mutants M07/M08 survivants).
LISTE_NIGHT = "/night"
LISTE_REPRISE = re.compile(r"reprise|resum")
#: M-h — le renvoi de l'ordre des `done` est lu DANS le paragraphe du lancement par lot de kickoff.md.
LOT_KICKOFF = ("**`fournee` remplace `start`**", "\n4b. ")
#: L'ouverture UNIQUE de la liste `start` de la kickoff SKILL, où vit le 4e cas de A.
LISTE_KICKOFF_SKILL = "`start` stays for the"

# Cadrage C1 — orchestrateurs Claude et Codex.
LISTES_ORCH = {
    ORCH_MD: ("`start` stays for", CAS_EN),
    ORCH_TOML: ("start stays for", CAS_EN),
}
DEPS_READY = "python .agents/bin/tasks.py deps-ready <T>"
DETECTEUR = re.compile(r"^\s*1\. language-detector\b")
PLANNER = re.compile(r"^\s*2\. <?planner\b")
SANS_DIRECT = "none on the DIRECT route (no planner; § Le cadrage: before the FIRST planner)"
JETONS_RANGEE = (CLI, "CALLING SESSION", "task on the board", SANS_DIRECT, "routes it and never runs it",
                 BLOC, "relayed FIRST, verbatim", "before this routing plan", "`Verdict : découper`",
                 "`.agents/skills/planning/SKILL.md` § Le cadrage", PORTEE_EN)
#: Une rangée cadrage est une INVOCATION de l'outil (`cadrage_plan.py --task`), quelle que soit sa forme (`bash
#: .agents/pyrun.sh`, `python3`…) : une rangée en double se voit au-delà du littéral exact de `CLI` (C1).
RANGEE_CADRAGE = re.compile(r"cadrage_plan\.py`?\s+--task")
HORS_PLAFOND = BLOC + " block the CALLING SESSION relays FIRST stays outside this cap"
PLAFONDS = {ORCH_MD: "## Output format (mandatory, ≤ 45 lines", ORCH_TOML: "Output at most 45 lines"}
REGLES_DIRECTES = {ORCH_MD: "the CALLING SESSION's `tasks.py deps-ready <T>`",
                   ORCH_TOML: "The calling session runs tasks.py deps-ready <T>"}
JETONS_DIRECTE = ("no cadrage row on this route, which has no planner", "§ Le cadrage runs before the FIRST planner")
#: C1 — la clause du refus de direct (le cadrage AVANT le planner) et son repli exact : au refus, deps-ready et
#: language-detector ont déjà tourné, la session ne rejoue que le relais et les verdicts de la rangée.
REFUS_DIRECT = {ORCH_MD: "a refusal below that sends the task to `planner` has the CALLING SESSION run "
                         "`cadrage_plan.py` first",
                ORCH_TOML: "a refusal below that sends the task to planner has the CALLING SESSION run "
                           "cadrage_plan.py first"}
REPLI_DIRECT = "with the PIPELINE row's relay and verdicts — deps-ready already read, not replayed"
REPLI_INEXACT = "as in the PIPELINE row"
JUGEMENT = "never to your judgment"
OUTILS_CLAUDE = "tools: Read, Grep, Glob"
SANS_SHELL_CLAUDE = "you hold no shell"
SANDBOX_CODEX = 'sandbox_mode = "read-only"'
CLE_SANDBOX = re.compile(r"^sandbox_mode\s*=")  # la clé TOML ; la prose qui ouvre par le mot ne compte pas

# Cadrage C2 — orchestrateurs Gemini, Copilot et Kimi.
LISTES_C2 = {chemin: ("`start` stays for", CAS_EN) for chemin in (ORCH_GEMINI, ORCH_COPILOT, ORCH_KIMI)}
MIROIRS_C2 = (ORCH_GEMINI, ORCH_KIMI)  # miroirs de la déf Claude : mêmes ancres que C1
PLAFONDS_C2 = {chemin: PLAFONDS[ORCH_MD] for chemin in MIROIRS_C2}
REGLES_DIRECTES_C2 = {chemin: REGLES_DIRECTES[ORCH_MD] for chemin in MIROIRS_C2}
COMMENTAIRE_C1 = "(the cadrage and deps-ready rows above are the calling session's)"
# Le frontmatter `tools:` de chaque déf C2, à l'identique : aucun outil shell (l'orchestrateur ne joue rien).
OUTILS_C2 = {ORCH_GEMINI: 'tools: ["read_file", "grep_search", "glob"]',
             ORCH_COPILOT: 'tools: ["read", "search"]',
             ORCH_KIMI: "tools: Read, Grep, Glob"}
DEPS_COPILOT = "**Dependencies first** (pilot decision S-01M4Z5VMP5E9YN8T6EMDTBAF0T):"
ORDRE_COPILOT = "**ORDER, EXPLICITLY**"
ORDRE_JETONS = ("cadrage", "deps-ready", "`language-detector`", "`planner`")  # dans cet ordre
DIRECTE_COPILOT = "**Direct route**"
# Réserve C14 : les jetons du brouillon Copilot MESURÉ, pas les JETONS_RANGEE de C1 ; passe de correction de la revue
# globale (T2, T10) : la portée « premier planner », `communicator`, rc 2, `Verdict : planifier`, et AUCUN plafond de
# lignes (la déf Copilot n'en porte pas : « 45-line » était un plafond fantôme).
JETONS_RANGEE_COPILOT = (CLI, "CALLING SESSION", "FIRST planner only (none on DIRECT, " + PORTEE_EN + ")",
                         "for a board task", "before `tasks.py deps-ready <T>`, `language-detector` and `planner`",
                         "relay " + BLOC + " FIRST, verbatim", "via `communicator`", "outside the routing plan",
                         "rc 2 → rerun", "`Verdict : planifier` → on", "`Verdict : découper`",
                         "`.agents/skills/planning/SKILL.md` § Le cadrage")
PLAFOND_FANTOME = re.compile(r"\b\d+-line\b")
# Réserve C13 : « never your judgment » reste dans la règle directe condensée ; T9 : l'éligibilité se lit dans le
# bon sens (« no » porté jusqu'à la sécurité, SPECS LISIBLE) et la re-déclaration interdite est celle qui esquive.
JETONS_DIRECTE_COPILOT = JETONS_DIRECTE + ("CALLING SESSION runs `cadrage_plan.py` before full chain from `planner`",
                                           "never your judgment", "never re-declare write-set to dodge the verb",
                                           "no guard path, no open decision/security, readable SPECS")
# Exec-critic de C2 (survivants M11 à M16) et objets rétablis : la lecture du board (:19) et le lancement par lot (:17).
LECTURE_COPILOT = "Read `.agents/state/local/TASKS.md`"
JETONS_LECTURE_COPILOT = ("git-ignored", "if absent or unreadable, write `board illisible` in the routing plan, "
                          "never guess", "a STALE view may omit a task", "Read-only adversarial critics",
                          "`plan-critic` follows `planner` before the human gate")
LOT_COPILOT = "**Batch launch**"
JETONS_LOT_COPILOT = ("its security verdict traced on the lot", "writes the plan's `INTÉGRATION:` paths",
                      "ONE closing review and ONE gate cover whole batch",
                      "foreign `running` tasks `fournee` prints as sharing it", "`done` lots, then parent")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


FIN_DE_PHRASE = re.compile(r"\.(?=\s|$)")


def lire(root: Path = ROOT) -> dict[str, str]:
    return {c: (root / c).read_text(encoding="utf-8") for c in LUS}


def liste(texte: str, ouverture: str) -> str | None:
    """La liste `start` : du littéral d'ouverture (UNIQUE) à la fin de sa phrase, blancs normalisés."""
    t = norm(texte)
    if t.count(ouverture) != 1:
        return None
    i = t.index(ouverture)
    m = FIN_DE_PHRASE.search(t, i)
    return t[i:m.end() if m else len(t)]


def section(texte: str, debut: str, fin: str) -> str | None:
    """De l'ouverture UNIQUE à la fin, exclue — les deux ancres OBLIGATOIRES : une fin absente rend None (M-g),
    jamais le reste du fichier, où un jeton posé plus loin passerait pour présent."""
    if texte.count(debut) != 1:
        return None
    i = texte.index(debut)
    j = texte.find(fin, i + len(debut))
    if j < 0:
        return None
    return norm(texte[i:j])


def item(texte: str, numero: str) -> list[str]:
    """Les lignes `<numero>. …` de la première liste sous `## Pipeline`."""
    if "\n## Pipeline\n" not in texte:
        return []
    corps = texte.split("\n## Pipeline\n", 1)[1].split("\n## ", 1)[0]
    return [l for l in corps.splitlines() if l.startswith(numero + ". ")][:1]


def fautes_listes(textes: dict[str, str], listes: dict[str, tuple[str, str]] = LISTES) -> list[str]:
    out = []
    for chemin, (ouverture, cas) in listes.items():
        seg = liste(textes[chemin], ouverture)
        if seg is None:
            out.append(f"{chemin} : « {ouverture} » absent ou non unique")
            continue
        if cas not in seg:
            out.append(f"{chemin} : le 4e cas manque DANS la liste ouverte par « {ouverture} »")
        if LISTE_NIGHT not in seg or not LISTE_REPRISE.search(seg):
            out.append(f"{chemin} : la liste « {ouverture} » a perdu `/night` ou les reprises")
        out += [f"{chemin} : ancienne formulation « {a} » dans la liste « {ouverture} »" for a in ANCIENS if a in seg]
    return out


def lignes_routeurs(textes: dict[str, str]) -> dict[str, tuple[list[str], str]]:
    return {
        AGENTS: ([l for l in textes[AGENTS].splitlines() if "Pipeline mandatory" in l], "`language-detector`"),
        COPILOT: (item(textes[COPILOT], "1"), "`language-detector`"),
        README: (item(textes[README], "2"), "language detector"),
    }


def fautes_routeurs(textes: dict[str, str]) -> list[str]:
    out = []
    for chemin, (lignes, detecteur) in lignes_routeurs(textes).items():
        if len(lignes) != 1:
            out.append(f"{chemin} : ancre de la chaîne introuvable ou double ({len(lignes)})")
            continue
        l = lignes[0]
        if CADRAGE not in l or detecteur not in l:
            out.append(f"{chemin} : « {CADRAGE} » ou « {detecteur} » absent de l'ancre")
        elif l.index(CADRAGE) > l.index(detecteur):
            out.append(f"{chemin} : « {CADRAGE} » ne précède pas « {detecteur} »")
        if chemin != AGENTS and PORTEE_EN not in l:
            out.append(f"{chemin} : l'ancre ne borne pas le cadrage au PREMIER planner (« {PORTEE_EN} »)")
    return out


def fautes_r1(textes: dict[str, str]) -> list[str]:
    """T3 : la ligne R1 du routeur et de son miroir Copilot écrit l'exception de la découpe de cadrage."""
    out = []
    for chemin, ancre in R1_ANCRES.items():
        lignes = [l for l in textes[chemin].splitlines() if ancre in l]
        if len(lignes) != 1:
            out.append(f"{chemin} : ligne R1 « {ancre} » absente ou double")
        elif R1_EXCEPTION not in lignes[0]:
            out.append(f"{chemin} : R1 sans l'exception écrite de la découpe de cadrage")
    return out


def fautes_chemins_nus(chemin: str, texte: str) -> list[str]:
    """T13 : la commande composée ne porte aucun chemin nu et porte au moins un `--file "<…>"`."""
    if CHEMIN_NU.search(texte) or not CHEMIN_GUILLEMETS.search(texte):
        return [f"{chemin} : chemin nu dans la commande du cadrage (attendu `--file \"<…>\"`)"]
    return []


def fautes_relais(textes: dict[str, str]) -> list[str]:
    out = []
    etape2 = [l for l in textes[KICKOFF_CMD].splitlines() if ROUTAGE in l]
    if len(etape2) != 1:
        out.append(f"{KICKOFF_CMD} : « {ROUTAGE} » absent ou double")
    else:
        l = etape2[0]
        # M-f : la branche `découper` et son renvoi à § CADRAGE FIRST ; T2 : la portée « premier planner »
        for jeton in (CLI, BLOC, "FIRST, verbatim", "`communicator`",
                      "`Verdict : découper` → the task never goes to the planner", "§ CADRAGE FIRST",
                      "before its FIRST planner only", PORTEE_EN):
            if jeton not in l:
                out.append(f"{KICKOFF_CMD} : étape 2 sans « {jeton} »")
            elif l.index(jeton) > l.index(ROUTAGE):
                out.append(f"{KICKOFF_CMD} : « {jeton} » vient après « {ROUTAGE} » — le CADRAGE passe EN PREMIER")
        out += fautes_chemins_nus(KICKOFF_CMD, l)
    lot = section(textes[KICKOFF_CMD], *LOT_KICKOFF)
    if lot is None or RENVOI_DONE not in lot:
        out.append(f"{KICKOFF_CMD} : l'ordre des `done` d'une découpe ne renvoie plus à § Le cadrage (paragraphe "
                   f"« {LOT_KICKOFF[0]} »)")
    for chemin, (debut, fin, jetons) in PARAGRAPHES.items():
        par = section(textes[chemin], debut, fin)
        if par is None:
            out.append(f"{chemin} : paragraphe « {debut} » absent ou double")
            continue
        out += [f"{chemin} : « {j} » absent du paragraphe « {debut} »" for j in (*jetons, PORTEE_FR) if j not in par]
        out += fautes_chemins_nus(chemin, par)
        if ECRITURE_BOARD in textes[chemin]:
            out.append(f"{chemin} : « {ECRITURE_BOARD} » — la commande écrirait le board (découper → /kickoff)")
    t = norm(textes[PLANNING_CMD])
    out += [f"{PLANNING_CMD} : titre {titre} absent" for titre in TITRES_LOT if titre not in t]
    return out


def fautes_accord_a(textes: dict[str, str]) -> list[str]:
    out = []
    if sum(1 for l in textes[PLANNING_SKILL].splitlines() if l.startswith("## Le cadrage")) != 1:
        out.append(f"{PLANNING_SKILL} : § Le cadrage ne se résout pas (titre absent ou double)")
    # Le 4e cas est lu DANS la liste `start` de la kickoff SKILL (ancre unique), jamais dans le fichier entier.
    kickoff_skill = liste(textes[KICKOFF_SKILL], LISTE_KICKOFF_SKILL) or ""
    if CAS_EN.replace(RENVOI, "(§ CADRAGE FIRST)") not in kickoff_skill:
        out.append(f"{KICKOFF_SKILL} : le 4e cas de A ne dit plus le libellé EN de B — réaligner B sur A")
    for chemin, (debut, fin, jetons) in ORDRE_DONE.items():
        sec = section(textes[chemin], debut, fin)
        if sec is None or any(j not in sec for j in jetons):
            out.append(f"{chemin} : ordre des `done` de « {debut} » illisible")
            continue
        pos = [sec.index(j) for j in jetons]
        if pos != sorted(pos):
            out.append(f"{chemin} : ordre des `done` inversé dans « {debut} »")
    return out


def faute_179(textes: dict[str, str]) -> list[str]:
    lignes = textes[KICKOFF_CMD].splitlines()
    if len(lignes) < 179 or LIGNE_179 not in lignes[178]:
        return [f"{KICKOFF_CMD}:179 ne porte plus « {LIGNE_179} » (une ligne insérée avant ?)"]
    return []


def premier(lignes: list[str], depuis: int, ok) -> int | None:
    return next((i for i in range(depuis, len(lignes)) if ok(lignes[i])), None)


def rangs_pipeline(texte: str, plafond: str) -> dict[str, int | None]:
    """Rangs (index de ligne) de `PIPELINE:` (le premier après la ligne du plafond) et de ses rangées."""
    lignes = texte.splitlines()
    p = premier(lignes, 0, lambda l: l.startswith(plafond))
    pi = None if p is None else premier(lignes, p, lambda l: l.strip() == "PIPELINE:")
    if pi is None:
        return {"PIPELINE:": None}
    return {
        "PIPELINE:": pi,
        "cadrage": premier(lignes, pi, lambda l: CLI in l),
        "deps-ready": premier(lignes, pi, lambda l: l.lstrip().startswith(DEPS_READY)),
        "language-detector": premier(lignes, pi, lambda l: DETECTEUR.match(l) is not None),
        "planner": premier(lignes, pi, lambda l: PLANNER.match(l) is not None),
    }


def fautes_pipeline(textes: dict[str, str], plafonds: dict[str, str] = PLAFONDS) -> list[str]:
    out = []
    for chemin, plafond in plafonds.items():
        texte = textes[chemin]
        lignes = texte.splitlines()
        if sum(1 for l in lignes if RANGEE_CADRAGE.search(l)) != 1 or sum(1 for l in lignes if CLI in l) != 1:
            out.append(f"{chemin} : rangée cadrage (« {CLI} ») absente ou double")
            continue
        rangs = rangs_pipeline(texte, plafond)
        if any(v is None for v in rangs.values()):
            out.append(f"{chemin} : PIPELINE illisible ({', '.join(k for k, v in rangs.items() if v is None)})")
            continue
        if rangs["cadrage"] != rangs["PIPELINE:"] + 1:
            out.append(f"{chemin} : la rangée cadrage n'ouvre pas le PIPELINE (arbitrage S-01M5B5B36R)")
        ordre = [rangs[k] for k in ("cadrage", "deps-ready", "language-detector", "planner")]
        if ordre != sorted(ordre):
            out.append(f"{chemin} : ordre cadrage → deps-ready → language-detector → planner rompu {ordre}")
        rangee = lignes[rangs["cadrage"]]
        out += [f"{chemin} : rangée cadrage sans « {j} »" for j in JETONS_RANGEE if j not in rangee]
        out += fautes_chemins_nus(chemin, rangee)
    return out


def fautes_plafonds(textes: dict[str, str], plafonds: dict[str, str] = PLAFONDS) -> list[str]:
    out = []
    for chemin, plafond in plafonds.items():
        lignes = [l for l in textes[chemin].splitlines() if l.startswith(plafond)]
        if len(lignes) != 1:
            out.append(f"{chemin} : ligne du plafond « {plafond} » absente ou double")
        elif HORS_PLAFOND not in lignes[0]:
            out.append(f"{chemin} : la ligne du plafond ne dit pas le bloc CADRAGE hors plafond")
    return out


def bloc_de(texte: str, ancre: str) -> str:
    """Le paragraphe (blancs normalisés, coupé aux lignes vides) qui porte l'ancre ; vide sinon."""
    return next((norm(p) for p in re.split(r"\n\s*\n", texte) if ancre in norm(p)), "")


def fautes_directe(textes: dict[str, str], regles: dict[str, str] = REGLES_DIRECTES) -> list[str]:
    out = []
    for chemin, ancre in regles.items():
        phrase = liste(textes[chemin], ancre)  # même découpe : de l'ancre UNIQUE à la fin de sa phrase
        if phrase is None:
            out.append(f"{chemin} : règle directe « {ancre} » absente ou non unique")
            continue
        refus = REFUS_DIRECT[ORCH_TOML if chemin == ORCH_TOML else ORCH_MD]
        out += [f"{chemin} : la règle directe ne dit pas « {j} »"
                for j in (*JETONS_DIRECTE, refus, REPLI_DIRECT) if j not in phrase]
        if REPLI_INEXACT in phrase:
            out.append(f"{chemin} : repli « {REPLI_INEXACT} » — au refus, deps-ready a déjà tourné")
        if JUGEMENT not in bloc_de(textes[chemin], ancre):
            out.append(f"{chemin} : la règle directe a perdu « {JUGEMENT} »")
    return out


def fautes_sans_shell(textes: dict[str, str]) -> list[str]:
    out = []
    outils = [l for l in textes[ORCH_MD].splitlines() if l.startswith("tools:")]
    if outils != [OUTILS_CLAUDE]:
        out.append(f"{ORCH_MD} : outils {outils} — attendu « {OUTILS_CLAUDE} » (l'orchestrateur n'a pas de shell)")
    if SANS_SHELL_CLAUDE not in textes[ORCH_MD]:
        out.append(f"{ORCH_MD} : « {SANS_SHELL_CLAUDE} » absent")
    if [l for l in textes[ORCH_TOML].splitlines() if CLE_SANDBOX.match(l)] != [SANDBOX_CODEX]:
        out.append(f"{ORCH_TOML} : « {SANDBOX_CODEX} » absent ou modifié")
    return out


def ligne_unique(texte: str, ok) -> int | None:
    """L'index de L'UNIQUE ligne qui satisfait `ok` ; None si aucune ou plusieurs (jamais la première venue)."""
    rangs = [i for i, l in enumerate(texte.splitlines()) if ok(l)]
    return rangs[0] if len(rangs) == 1 else None


def fautes_outils(textes: dict[str, str], chemin: str) -> list[str]:
    outils = [l for l in textes[chemin].splitlines() if l.startswith("tools:")]
    if outils != [OUTILS_C2[chemin]]:
        return [f"{chemin} : outils {outils} — attendu « {OUTILS_C2[chemin]} » (l'orchestrateur n'a pas de shell)"]
    return []


def fautes_sans_rangee_directe(textes: dict[str, str], chemin: str, ancre: str) -> list[str]:
    """La règle de la route directe (la ligne de son ancre) ne porte AUCUNE rangée cadrage."""
    i = ligne_unique(textes[chemin], lambda l: ancre in l)
    if i is None:
        return [f"{chemin} : règle directe « {ancre} » absente ou non unique"]
    if CLI in textes[chemin].splitlines()[i]:
        return [f"{chemin} : une rangée cadrage (« {CLI} ») sur la route directe, qui n'a pas de planner"]
    return []


def fautes_miroir_c2(textes: dict[str, str], chemin: str) -> list[str]:
    """Gemini ou Kimi : les règles C1 de la déf Claude, plus le commentaire C1 et l'absence de shell."""
    plafond = {chemin: PLAFONDS_C2[chemin]}
    out = fautes_listes(textes, {chemin: LISTES_C2[chemin]}) + fautes_pipeline(textes, plafond)
    out += fautes_plafonds(textes, plafond) + fautes_directe(textes, {chemin: REGLES_DIRECTES_C2[chemin]})
    out += fautes_sans_rangee_directe(textes, chemin, REGLES_DIRECTES_C2[chemin])
    detecteur = rangs_pipeline(textes[chemin], PLAFONDS_C2[chemin]).get("language-detector")
    if detecteur is not None and COMMENTAIRE_C1 not in textes[chemin].splitlines()[detecteur]:
        out.append(f"{chemin} : `1. language-detector` sans le commentaire « {COMMENTAIRE_C1} »")
    return out + fautes_outils(textes, chemin)


def fautes_copilot(textes: dict[str, str]) -> list[str]:
    """Copilot : la rangée sous **Dependencies first** avant deps-ready, l'ORDER, la route directe."""
    texte = textes[ORCH_COPILOT]
    lignes = texte.splitlines()
    out = fautes_listes(textes, {ORCH_COPILOT: LISTES_C2[ORCH_COPILOT]}) + fautes_outils(textes, ORCH_COPILOT)
    entete = ligne_unique(texte, lambda l: l.startswith(DEPS_COPILOT))
    rangee = ligne_unique(texte, lambda l: CLI in l)
    if ligne_unique(texte, lambda l: RANGEE_CADRAGE.search(l) is not None) is None:
        rangee = None  # une rangée en double sous une autre forme que `CLI` (C1)
    if entete is None or rangee is None:
        out.append(f"{ORCH_COPILOT} : « {DEPS_COPILOT} » ou la rangée cadrage (« {CLI} ») absent ou double")
    else:
        deps = premier(lignes, entete + 1, lambda l: DEPS_READY in l)
        if rangee != entete + 1:
            out.append(f"{ORCH_COPILOT} : la rangée cadrage n'est pas sous « {DEPS_COPILOT} »")
        if deps is None or deps <= rangee:
            out.append(f"{ORCH_COPILOT} : la rangée cadrage ne précède pas la ligne deps-ready (S-01M5B5B36R)")
        out += [f"{ORCH_COPILOT} : rangée cadrage sans « {j} »"
                for j in JETONS_RANGEE_COPILOT if j not in lignes[rangee]]
    ordre = ligne_unique(texte, lambda l: l.startswith(ORDRE_COPILOT))
    if ordre is None:
        out.append(f"{ORCH_COPILOT} : « {ORDRE_COPILOT} » absent ou double")
    else:
        pos = [lignes[ordre].find(j) for j in ORDRE_JETONS]
        if -1 in pos or pos != sorted(pos):
            out.append(f"{ORCH_COPILOT} : l'ORDER ne situe pas cadrage puis deps-ready avant `language-detector` {pos}")
    out += fautes_sans_rangee_directe(textes, ORCH_COPILOT, DIRECTE_COPILOT)
    directe = ligne_unique(texte, lambda l: l.startswith(DIRECTE_COPILOT))
    if directe is not None:
        out += [f"{ORCH_COPILOT} : la règle directe ne dit pas « {j} »"
                for j in JETONS_DIRECTE_COPILOT if j not in lignes[directe]]
    if PLAFOND_FANTOME.search(texte):
        out.append(f"{ORCH_COPILOT} : plafond de lignes « {PLAFOND_FANTOME.search(texte).group(0)} » — la déf n'en a pas")
    for ancre, jetons in ((LECTURE_COPILOT, JETONS_LECTURE_COPILOT), (LOT_COPILOT, JETONS_LOT_COPILOT)):
        i = ligne_unique(texte, lambda l, a=ancre: l.startswith(a))
        if i is None:
            out.append(f"{ORCH_COPILOT} : paragraphe « {ancre} » absent ou double")
            continue
        out += [f"{ORCH_COPILOT} : « {ancre} » ne dit plus « {j} »" for j in jetons if j not in lignes[i]]
    return out


def fautes_c2(textes: dict[str, str], chemin: str) -> list[str]:
    return fautes_copilot(textes) if chemin == ORCH_COPILOT else fautes_miroir_c2(textes, chemin)


def fautes_voyage(exclude: str, chemins: tuple[str, ...] = WRITE_SET) -> list[str]:
    sys.path.insert(0, str(BIN))
    try:
        from sync_template import match_rule, parse_exclude
    finally:
        sys.path.remove(str(BIN))
    regles = parse_exclude(exclude)
    out = []
    for chemin in chemins:
        r = match_rule(chemin, regles)
        if r is not None and r.polarity in ("strip", "keep", "own"):
            out.append(f"{chemin} : {r.polarity} — ne voyage plus chez l'adoptant")
    return out


class SurfacesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.textes = lire()

    def test_les_quatre_listes_start_portent_le_4e_cas(self):
        self.assertEqual(fautes_listes(self.textes), [])

    def test_le_cadrage_precede_la_detection_dans_les_trois_routeurs(self):
        self.assertEqual(fautes_routeurs(self.textes), [])

    def test_les_commandes_relaient_le_cadrage(self):
        self.assertEqual(fautes_relais(self.textes), [])

    def test_les_renvois_s_accordent_avec_a(self):
        self.assertEqual(fautes_accord_a(self.textes), [])

    def test_kickoff_md_179_reste_la_ligne_du_verdict_final(self):
        self.assertEqual(faute_179(self.textes), [])

    def test_r1_ecrit_l_exception_de_la_decoupe(self):
        self.assertEqual(fautes_r1(self.textes), [])

    def test_les_listes_start_des_orchestrateurs_portent_le_4e_cas(self):
        self.assertEqual(fautes_listes(self.textes, LISTES_ORCH), [])

    def test_la_rangee_cadrage_ouvre_le_pipeline_des_orchestrateurs(self):
        self.assertEqual(fautes_pipeline(self.textes), [])

    def test_le_bloc_cadrage_est_hors_plafond(self):
        self.assertEqual(fautes_plafonds(self.textes), [])

    def test_la_route_directe_dit_sans_cadrage(self):
        self.assertEqual(fautes_directe(self.textes), [])

    def test_les_orchestrateurs_restent_sans_shell(self):
        self.assertEqual(fautes_sans_shell(self.textes), [])

    def test_orchestrators_declare_scope(self):
        """Plan T-01M5DBFPWC, Tests H+INTÉGRATION : chaque déf de l'orchestrateur, et le roster, déclarent
        `review-scope` juste avant le critique et lisent la portée active au diagnostic d'un `done` refusé."""
        textes = textes_portee_orch()
        self.assertEqual(fautes_portee_orch(textes), [])
        for rel, texte in textes.items():
            with self.subTest(mutant="review-scope retiré", rel=rel):
                mutant = {**textes, rel: texte.replace("review-scope <focus>", "review-zzzzz <focus>", 1)}
                self.assertNotEqual(mutant[rel], texte)
                self.assertTrue(any(f.startswith(f"{rel} : review-scope") for f in fautes_portee_orch(mutant)))
            with self.subTest(mutant="diagnostic d'avant réinjecté", rel=rel):
                mutant = {**textes, rel: texte + "\nThen check that the task was `running` when it stopped.\n"}
                self.assertTrue(any(f.startswith(f"{rel} : diagnostic d'avant") for f in fautes_portee_orch(mutant)))
            for nom, motif in PRESENTS_PORTEE:
                with self.subTest(mutant=f"{nom} retiré", rel=rel):
                    retire, nombre = motif.subn("", texte, count=1)
                    self.assertEqual(nombre, 1, (rel, nom))
                    mutant = {**textes, rel: retire}
                    self.assertTrue(any(f.startswith(f"{rel} : {nom} vu ") for f in fautes_portee_orch(mutant)))
            for nom, motif, ancien in ANCIENS_PORTEE:
                with self.subTest(mutant=f"{nom} réinjecté", rel=rel):
                    mutant = {**textes, rel: texte + "\n" + ancien + "\n"}
                    self.assertTrue(motif.search(mutant[rel]), (rel, nom))
                    self.assertTrue(any(f.startswith(f"{rel} : forme d'avant encore écrite ({nom})")
                                        for f in fautes_portee_orch(mutant)))


# Revue de clôture critic-opus de T-01M5DBFPWC (F3, I-K1) : le témoin promis par le plan (Tests
# H+INTÉGRATION). Borne : un JETON par déf (le roster : un par hôte), pas l'ordre déclarer-puis-lancer.
DEFS_PORTEE = (".claude/agents/orchestrator.md", ".codex/agents/orchestrator.toml",
               ".github/agents/orchestrator.agent.md", ".gemini/agents/orchestrator.md",
               ".kimi-code/agents/orchestrator.md")
APPEL_PORTEE_ORCH = re.compile(r"review-scope <focus> <T>…`?(?: declares)? JUST BEFORE the critic")
#: Le blanc entre deux mots peut être un saut de ligne de la déf TOML, que le roster JSON range en
#: deux éléments de liste (`",` puis `"`).
_COUPURE = r'(?:\s|",\s*")+'
DIAG_PORTEE = re.compile(r"the task was in the active scope, `?running`? or not, when it" + _COUPURE + "stopped")
DIAG_AVANT = re.compile(r"the task was `?running`? when it" + _COUPURE + "stopped")
PRESENTS_PORTEE = (
    ("demotes nobody", re.compile(r"demotes" + _COUPURE + r"nobody")),
    ("never by chantier", re.compile(r"never" + _COUPURE + r"by" + _COUPURE + r"chantier")),
    ("outside the active scope", re.compile(r"outside" + _COUPURE + r"the" + _COUPURE + r"active" + _COUPURE + r"scope")),
    ("aucune portée", re.compile(r"aucune" + _COUPURE + r"portée")),
    ("portée hors focus", re.compile(r"portée" + _COUPURE + r"hors" + _COUPURE + r"focus")),
    ("portée consommée", re.compile(r"portée" + _COUPURE + r"consommée")),
)
ANCIENS_PORTEE = (
    ("write nothing without a running",
     re.compile(r"write" + _COUPURE + r"nothing" + _COUPURE + r"without" + _COUPURE + r"a" + _COUPURE + r"`?running`?"),
     "write nothing without a `running` task"),
    ("scope and say board illisible",
     re.compile(r"scope" + _COUPURE + r"and" + _COUPURE + r"say" + _COUPURE + r"`?board" + _COUPURE + r"illisible`?"),
     "scope and say `board illisible`"),
    ("portee consommee or board illisible",
     re.compile(r"`?portee" + _COUPURE + r"consommee" + _COUPURE + r"--" + _COUPURE + r"aucune" + _COUPURE + r"trace" + _COUPURE + r"ecrite`?,?" + _COUPURE + r"or" + _COUPURE + r"`?board" + _COUPURE + r"illisible`?"),
     "`portee consommee -- aucune trace ecrite`, or `board illisible`"),
)


def textes_portee_orch() -> dict[str, str]:
    return {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in (*DEFS_PORTEE, ROSTER_ORCH)}


def fautes_portee_orch(textes: dict[str, str]) -> list[str]:
    fautes = []
    for rel, texte in textes.items():
        attendu = len(DEFS_PORTEE) if rel == ROSTER_ORCH else 1
        for nom, motif in (("review-scope", APPEL_PORTEE_ORCH), ("diagnostic", DIAG_PORTEE)):
            vu = len(motif.findall(texte))
            if vu < attendu:
                fautes.append(f"{rel} : {nom} vu {vu} fois, attendu {attendu}")
        for nom, motif in PRESENTS_PORTEE:
            vu = len(motif.findall(texte))
            if vu < attendu:
                fautes.append(f"{rel} : {nom} vu {vu} fois, attendu {attendu}")
        for nom, motif, _ in ANCIENS_PORTEE:
            if motif.search(texte):
                fautes.append(f"{rel} : forme d'avant encore écrite ({nom})")
        if DIAG_AVANT.search(texte):
            fautes.append(f"{rel} : diagnostic d'avant (« the task was `running` when it stopped ») encore écrit")
    return fautes


class C2SurfacesTests(unittest.TestCase):
    """Cadrage C2 : un cas par hôte, toutes les familles de fautes de cet hôte."""

    def setUp(self) -> None:
        self.textes = lire()

    def test_gemini(self):
        self.assertEqual(fautes_c2(self.textes, ORCH_GEMINI), [])

    def test_copilot(self):
        self.assertEqual(fautes_c2(self.textes, ORCH_COPILOT), [])

    def test_kimi(self):
        self.assertEqual(fautes_c2(self.textes, ORCH_KIMI), [])


@unittest.skipUnless((ROOT / ".template-exclude").is_file() and (BIN / "sync_template.py").is_file(),
                     "SAUT ANNONCÉ : canal de synchro absent (dépôt adoptant) — le voyage se juge dans le kit")
class VoyageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exclude = (ROOT / ".template-exclude").read_text(encoding="utf-8")

    def test_les_sept_chemins_voyagent(self):
        self.assertEqual(fautes_voyage(self.exclude), [])
        for chemin in WRITE_SET:
            self.assertTrue((ROOT / chemin).is_file(), chemin)

    def test_etalonnage_un_strip_par_chemin_rougit(self):
        for chemin in WRITE_SET:
            with self.subTest(chemin=chemin):
                fautes = fautes_voyage(self.exclude + f"\nstrip: {chemin}\n")
                self.assertTrue(any(f.startswith(chemin + " :") for f in fautes), fautes)

    def test_les_quatre_chemins_de_c1_voyagent(self):
        self.assertEqual(fautes_voyage(self.exclude, WRITE_SET_C1), [])
        for chemin in WRITE_SET_C1:
            self.assertTrue((ROOT / chemin).is_file(), chemin)

    def test_etalonnage_un_strip_par_chemin_de_c1_rougit(self):
        for chemin in WRITE_SET_C1:
            with self.subTest(chemin=chemin):
                fautes = fautes_voyage(self.exclude + f"\nstrip: {chemin}\n", WRITE_SET_C1)
                self.assertTrue(any(f.startswith(chemin + " :") for f in fautes), fautes)

    def test_les_cinq_chemins_de_c2_voyagent(self):
        self.assertEqual(fautes_voyage(self.exclude, WRITE_SET_C2), [])
        for chemin in WRITE_SET_C2:
            self.assertTrue((ROOT / chemin).is_file(), chemin)

    def test_etalonnage_un_strip_par_chemin_de_c2_rougit(self):
        for chemin in WRITE_SET_C2:
            with self.subTest(chemin=chemin):
                fautes = fautes_voyage(self.exclude + f"\nstrip: {chemin}\n", WRITE_SET_C2)
                self.assertTrue(any(f.startswith(chemin + " :") for f in fautes), fautes)


class EtalonnageTests(unittest.TestCase):
    """Chaque mutant de l'annexe du plan, rejoué en mémoire : une faute qui nomme la surface."""

    def setUp(self) -> None:
        self.textes = lire()

    def muter(self, chemin: str, nouveau: str) -> dict[str, str]:
        self.assertNotEqual(self.textes[chemin], nouveau, f"mutant inerte sur {chemin}")
        return {**self.textes, chemin: nouveau}

    def rouge(self, fautes: list[str], chemin: str) -> None:
        self.assertTrue(any(f.startswith(chemin) for f in fautes), fautes)

    def test_4e_cas_retire_de_la_liste_mais_laisse_ailleurs(self):
        for chemin, (_o, cas) in LISTES.items():
            with self.subTest(chemin=chemin):
                t = norm(self.textes[chemin])
                self.assertEqual(t.count(cas), 1)
                mute = t.replace(cas, "x") + "\n\n" + cas + ".\n"
                self.rouge(fautes_listes(self.muter(chemin, mute)), chemin)

    def test_anciennes_formulations_reinserees_dans_chaque_liste(self):
        for chemin, (ouverture, _c) in LISTES.items():
            for ancien in ANCIENS:
                with self.subTest(chemin=chemin, ancien=ancien):
                    t = norm(self.textes[chemin])
                    mute = t.replace(ouverture, f"{ouverture} {ancien},", 1)
                    self.rouge(fautes_listes(self.muter(chemin, mute)), chemin)

    def test_cadrage_retire_ou_deplace_apres_la_detection(self):
        for chemin, (lignes, detecteur) in lignes_routeurs(self.textes).items():
            l = lignes[0]
            retire = l.replace(CADRAGE, "cadrage")
            deplace = l.replace(CADRAGE, "cadrage") + " " + CADRAGE
            for nom, nouvelle in (("retiré", retire), ("déplacé", deplace)):
                with self.subTest(chemin=chemin, mutant=nom):
                    self.rouge(fautes_routeurs(self.muter(chemin, self.textes[chemin].replace(l, nouvelle))), chemin)

    def test_cadrage_retire_de_chaque_commande(self):
        for chemin in (KICKOFF_CMD, PLANNING_CMD, PLANNING_ALL_CMD):
            with self.subTest(chemin=chemin):
                self.rouge(fautes_relais(self.muter(chemin, self.textes[chemin].replace(BLOC, "le bloc"))), chemin)

    def test_relais_kickoff_deplace_apres_le_routage(self):
        l = next(x for x in self.textes[KICKOFF_CMD].splitlines() if ROUTAGE in x)
        avant, apres = l.split(ROUTAGE, 1)
        nouvelle = "2. " + ROUTAGE + apres + " " + avant[len("2. "):]
        self.rouge(fautes_relais(self.muter(KICKOFF_CMD, self.textes[KICKOFF_CMD].replace(l, nouvelle))), KICKOFF_CMD)

    def test_ecriture_board_autorisee_dans_la_branche_decouper(self):
        for chemin, ancien in ((PLANNING_CMD, "`/planning` n'écrit pas le board"),
                               (PLANNING_ALL_CMD, "`/planning-all` n'écrit pas le board pour elle")):
            for nom, nouveau in (("négation levée", ancien.replace("n'écrit pas", "écrit")),
                                 ("tasks.py new", ancien + " ; il crée les enfants par `tasks.py new`")):
                with self.subTest(chemin=chemin, mutant=nom):
                    t = norm(self.textes[chemin])
                    self.rouge(fautes_relais(self.muter(chemin, t.replace(ancien, nouveau))), chemin)

    def test_chaque_titre_de_lot_modifie(self):
        for titre in TITRES_LOT:
            with self.subTest(titre=titre):
                t = norm(self.textes[PLANNING_CMD])
                self.rouge(fautes_relais(self.muter(PLANNING_CMD, t.replace(titre, titre.replace("lot <K> : ", "lot <K> - ")))),
                           PLANNING_CMD)

    def test_ordre_de_cloture_de_a_inverse(self):
        for chemin, (_d, _f, jetons) in ORDRE_DONE.items():
            with self.subTest(chemin=chemin):
                t = norm(self.textes[chemin])
                a, b = jetons[2], jetons[3]
                mute = t.replace(a, "\0").replace(b, a).replace("\0", b)
                self.rouge(fautes_accord_a(self.muter(chemin, mute)), chemin)

    def test_renvoi_des_done_retire_de_kickoff(self):
        t = norm(self.textes[KICKOFF_CMD])
        self.rouge(fautes_relais(self.muter(KICKOFF_CMD, t.replace(RENVOI_DONE, "x"))), KICKOFF_CMD)

    def test_libelle_de_a_change(self):
        t = self.textes[KICKOFF_SKILL]
        self.rouge(fautes_accord_a(self.muter(KICKOFF_SKILL, t.replace("next child of a cadrage cut", "next child of a cadrage split"))),
                   KICKOFF_SKILL)

    def test_ligne_inseree_avant_179(self):
        self.rouge(faute_179(self.muter(KICKOFF_CMD, "\n" + self.textes[KICKOFF_CMD])), KICKOFF_CMD)

    # --- Passe de correction de la revue de clôture globale ---

    def test_m_f_branche_decouper_retiree_de_kickoff(self):
        """M-f : la branche `découper` de l'étape 2 (et son renvoi § CADRAGE FIRST) retirée rougit."""
        for jeton in ("`Verdict : découper` → the task never goes to the planner", "§ CADRAGE FIRST"):
            with self.subTest(jeton=jeton):
                l = next(x for x in self.textes[KICKOFF_CMD].splitlines() if ROUTAGE in x)
                mute = self.textes[KICKOFF_CMD].replace(l, l.replace(jeton, "x"))
                self.rouge(fautes_relais(self.muter(KICKOFF_CMD, mute)), KICKOFF_CMD)

    def test_m_g_ancre_de_fin_absente_rougit(self):
        """M-g : la fin d'un paragraphe absente ne laisse plus lire le reste du fichier."""
        self.assertIsNone(section("début A milieu", "début", "FIN"))
        for chemin, (_debut, fin, _j) in PARAGRAPHES.items():
            with self.subTest(chemin=chemin):
                self.rouge(fautes_relais(self.muter(chemin, self.textes[chemin].replace(fin, "x"))), chemin)

    def test_m_h_renvoi_des_done_hors_du_paragraphe_du_lot(self):
        """M-h : le renvoi déplacé hors du paragraphe du lancement par lot (toujours dans le fichier) rougit."""
        t = norm(self.textes[KICKOFF_CMD])
        self.assertEqual(t.count(RENVOI_DONE), 1)
        mute = t.replace(RENVOI_DONE, "x") + "\n\n" + RENVOI_DONE + ".\n"
        self.rouge(fautes_relais(self.muter(KICKOFF_CMD, mute)), KICKOFF_CMD)

    def test_t2_portee_retiree_rougit(self):
        """T2 : la portée « premier planner » retirée d'une commande ou d'un routeur rougit."""
        l = next(x for x in self.textes[KICKOFF_CMD].splitlines() if ROUTAGE in x)
        self.rouge(fautes_relais(self.muter(KICKOFF_CMD, self.textes[KICKOFF_CMD].replace(l, l.replace(PORTEE_EN, "x")))),
                   KICKOFF_CMD)
        for chemin in PARAGRAPHES:
            with self.subTest(chemin=chemin):
                t = norm(self.textes[chemin])
                self.rouge(fautes_relais(self.muter(chemin, t.replace(PORTEE_FR, "x"))), chemin)
        for chemin in (COPILOT, README):
            with self.subTest(chemin=chemin):
                self.rouge(fautes_routeurs(self.muter(chemin, self.textes[chemin].replace(PORTEE_EN, "x", 1))), chemin)

    def test_t3_exception_r1_retiree_rougit(self):
        for chemin in R1_ANCRES:
            with self.subTest(chemin=chemin):
                self.rouge(fautes_r1(self.muter(chemin, self.textes[chemin].replace(R1_EXCEPTION, "x"))), chemin)

    def test_t13_chemin_nu_rougit(self):
        """Un `--file "<…>"` redevenu nu, dans chaque commande composée, rougit."""
        for chemin in (KICKOFF_CMD, PLANNING_CMD, PLANNING_ALL_CMD):
            with self.subTest(chemin=chemin):
                t = self.textes[chemin]
                m = CHEMIN_GUILLEMETS.search(t)
                self.assertIsNotNone(m)
                nu = m.group(0).replace('"', "")
                self.rouge(fautes_relais(self.muter(chemin, t.replace(m.group(0), nu, 1))), chemin)

    def test_night_ou_reprise_retire_de_chaque_liste_rougit(self):
        """Mutants M07/M08 de l'exec-critic de C2 : `/night` retiré d'une liste `start` rougit, partout."""
        for listes in (LISTES, LISTES_ORCH, LISTES_C2):
            for chemin, (ouverture, _cas) in listes.items():
                with self.subTest(chemin=chemin):
                    t = norm(self.textes[chemin])
                    seg = liste(t, ouverture)
                    for jeton in ("`/night`", "/night"):
                        if jeton in seg:
                            mute = t.replace(seg, seg.replace(jeton, "la nuit"))
                            break
                    self.rouge(fautes_listes(self.muter(chemin, mute), listes), chemin)
                    reprise = LISTE_REPRISE.search(seg).group(0)
                    mute = t.replace(seg, LISTE_REPRISE.sub("x", seg))
                    self.assertNotEqual(reprise, "")
                    self.rouge(fautes_listes(self.muter(chemin, mute), listes), chemin)

    # --- Cadrage C1 : orchestrateurs Claude et Codex ---

    def test_4e_cas_retire_de_la_liste_orchestrateur_mais_laisse_ailleurs(self):
        for chemin, (_o, cas) in LISTES_ORCH.items():
            with self.subTest(chemin=chemin):
                t = norm(self.textes[chemin])
                self.assertEqual(t.count(cas), 1)
                mute = t.replace(cas, "x") + "\n\n" + cas + ".\n"
                self.rouge(fautes_listes(self.muter(chemin, mute), LISTES_ORCH), chemin)

    def test_anciennes_formulations_dans_la_liste_orchestrateur(self):
        for chemin, (ouverture, _c) in LISTES_ORCH.items():
            for ancien in ANCIENS:
                with self.subTest(chemin=chemin, ancien=ancien):
                    mute = norm(self.textes[chemin]).replace(ouverture, f"{ouverture} {ancien},", 1)
                    self.rouge(fautes_listes(self.muter(chemin, mute), LISTES_ORCH), chemin)

    def deplacer_rangee(self, chemin: str, apres: str) -> str:
        """La rangée cadrage retirée de sa place et réinsérée juste après la rangée `apres`."""
        lignes = self.textes[chemin].splitlines(keepends=True)
        rangs = rangs_pipeline(self.textes[chemin], PLAFONDS[chemin])
        rangee = lignes.pop(rangs["cadrage"])
        cible = rangs[apres] - (1 if rangs[apres] > rangs["cadrage"] else 0)
        lignes.insert(cible + 1, rangee)
        return "".join(lignes)

    def test_rangee_cadrage_deplacee_apres_planner_rougit(self):
        """C11 : la rangée cadrage déplacée après la rangée planner, dans chaque déf, isolément."""
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                self.rouge(fautes_pipeline(self.muter(chemin, self.deplacer_rangee(chemin, "planner"))), chemin)

    def test_rangee_cadrage_deplacee_apres_deps_ready_rougit(self):
        """Arbitrage S-01M5B5B36R : la rangée cadrage précède deps-ready."""
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                self.rouge(fautes_pipeline(self.muter(chemin, self.deplacer_rangee(chemin, "deps-ready"))), chemin)

    def test_rangee_cadrage_retiree_rougit(self):
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                rangee = self.textes[chemin].splitlines()[rangs_pipeline(self.textes[chemin], PLAFONDS[chemin])["cadrage"]]
                self.rouge(fautes_pipeline(self.muter(chemin, self.textes[chemin].replace(rangee + "\n", ""))), chemin)

    def test_chaque_jeton_de_la_rangee_retire_rougit(self):
        for chemin in PLAFONDS:
            rangee = self.textes[chemin].splitlines()[rangs_pipeline(self.textes[chemin], PLAFONDS[chemin])["cadrage"]]
            for jeton in JETONS_RANGEE[1:]:  # le 1er (la CLI) est l'ancre : son retrait est le mutant précédent
                with self.subTest(chemin=chemin, jeton=jeton):
                    mute = self.textes[chemin].replace(rangee, rangee.replace(jeton, "x"))
                    self.rouge(fautes_pipeline(self.muter(chemin, mute)), chemin)

    def test_hors_plafond_retire_rougit(self):
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                self.rouge(fautes_plafonds(self.muter(chemin, self.textes[chemin].replace(HORS_PLAFOND, "x"))), chemin)

    def test_regle_directe_sans_mention_du_cadrage_rougit(self):
        for chemin in REGLES_DIRECTES:
            for jeton in JETONS_DIRECTE:
                with self.subTest(chemin=chemin, jeton=jeton):
                    self.rouge(fautes_directe(self.muter(chemin, self.textes[chemin].replace(jeton, "x"))), chemin)

    def test_rangee_en_double_sous_une_autre_forme_rougit(self):
        """C1 : une seconde rangée cadrage, écrite autrement que le littéral `CLI`, rougit."""
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                rangee = next(l for l in self.textes[chemin].splitlines() if CLI in l)
                double = rangee + "\n     python3 .agents/bin/cadrage_plan.py --task <T> --file \"<path>\""
                self.rouge(fautes_pipeline(self.muter(chemin, self.textes[chemin].replace(rangee, double, 1))), chemin)

    def test_rangee_aux_chemins_nus_rougit(self):
        for chemin in PLAFONDS:
            with self.subTest(chemin=chemin):
                mute = self.textes[chemin].replace('--file "<path>"', "--file <path>", 1)
                self.rouge(fautes_pipeline(self.muter(chemin, mute)), chemin)

    def test_clause_du_refus_de_direct_retiree_ou_repli_inexact_rougit(self):
        """C1 : la clause du refus de direct retirée, le repli « as in the PIPELINE row » remis, ou « never to
        your judgment » levé en « to your judgment », rougit — chaque déf isolément."""
        for chemin in REGLES_DIRECTES:
            refus = REFUS_DIRECT[chemin]
            t = self.textes[chemin]
            jugement = re.search(r"never\s+to\s+your\s+judgment", t)
            for nom, mute in (("refus retiré", t.replace(refus, "x", 1)),
                              ("repli inexact", t.replace(REPLI_DIRECT, REPLI_INEXACT, 1)),
                              ("jugement levé", t[:jugement.start()] + "to your judgment" + t[jugement.end():])):
                with self.subTest(chemin=chemin, mutant=nom):
                    self.rouge(fautes_directe(self.muter(chemin, mute)), chemin)

    def test_bash_ajoute_a_l_orchestrateur_claude_rougit(self):
        mute = self.textes[ORCH_MD].replace(OUTILS_CLAUDE, OUTILS_CLAUDE + ", Bash", 1)
        self.rouge(fautes_sans_shell(self.muter(ORCH_MD, mute)), ORCH_MD)

    def test_sandbox_codex_ouvert_rougit(self):
        mute = self.textes[ORCH_TOML].replace(SANDBOX_CODEX, 'sandbox_mode = "workspace-write"', 1)
        self.rouge(fautes_sans_shell(self.muter(ORCH_TOML, mute)), ORCH_TOML)


class C2EtalonnageTests(unittest.TestCase):
    """Mutants du cadrage C2, rejoués en mémoire hôte par hôte : chacun rougit le cas de SON hôte."""

    HOTES = (ORCH_GEMINI, ORCH_COPILOT, ORCH_KIMI)
    ANCRES_DIRECTES = {**REGLES_DIRECTES_C2, ORCH_COPILOT: DIRECTE_COPILOT}

    def setUp(self) -> None:
        self.textes = lire()

    def muter(self, chemin: str, nouveau: str) -> dict[str, str]:
        self.assertNotEqual(self.textes[chemin], nouveau, f"mutant inerte sur {chemin}")
        return {**self.textes, chemin: nouveau}

    def rouge(self, chemin: str, nouveau: str) -> None:
        fautes = fautes_c2(self.muter(chemin, nouveau), chemin)
        self.assertTrue(any(f.startswith(chemin) for f in fautes), fautes)

    def rangee(self, chemin: str) -> str:
        return next(l for l in self.textes[chemin].splitlines() if CLI in l)

    def test_rangee_retiree_rougit(self):
        for chemin in self.HOTES:
            with self.subTest(chemin=chemin):
                self.rouge(chemin, self.textes[chemin].replace(self.rangee(chemin) + "\n", "", 1))

    def test_rangee_deplacee_apres_deps_ready_rougit(self):
        """Arbitrage S-01M5B5B36R : la rangée cadrage précède deps-ready, sur chaque hôte."""
        for chemin in self.HOTES:
            with self.subTest(chemin=chemin):
                lignes = self.textes[chemin].splitlines(keepends=True)
                i = next(k for k, l in enumerate(lignes) if CLI in l)
                rangee = lignes.pop(i)
                j = premier(lignes, i, lambda l: DEPS_READY in l)
                lignes.insert(j + 1, rangee)
                self.rouge(chemin, "".join(lignes))

    def test_rangee_deplacee_dans_la_route_directe_rougit(self):
        """Arbitrage S-01M5B4Q9PG : aucune rangée cadrage sur la route directe, qui n'a pas de planner."""
        for chemin, ancre in self.ANCRES_DIRECTES.items():
            with self.subTest(chemin=chemin):
                rangee = self.rangee(chemin)
                t = self.textes[chemin].replace(rangee + "\n", "", 1)
                directe = next(l for l in t.splitlines() if ancre in l)
                mute = self.muter(chemin, t.replace(directe, directe + " " + rangee.strip(), 1))
                self.assertTrue(fautes_sans_rangee_directe(mute, chemin, ancre))
                self.rouge(chemin, mute[chemin])

    def test_cas_retire_de_la_liste_mais_laisse_ailleurs_rougit(self):
        for chemin in self.HOTES:
            with self.subTest(chemin=chemin):
                t = self.textes[chemin]
                self.assertEqual(t.count(CAS_EN), 1)
                self.rouge(chemin, t.replace(CAS_EN, "x", 1) + "\n\n" + CAS_EN + ".\n")

    def test_relais_ou_renvoi_retire_de_la_rangee_rougit(self):
        for chemin in self.HOTES:
            rangee = self.rangee(chemin)
            jetons = JETONS_RANGEE_COPILOT if chemin == ORCH_COPILOT else JETONS_RANGEE
            for jeton in jetons[1:]:  # le 1er (la CLI) est l'ancre : son retrait est le mutant « retirée »
                with self.subTest(chemin=chemin, jeton=jeton):
                    self.assertIn(jeton, rangee)
                    self.rouge(chemin, self.textes[chemin].replace(rangee, rangee.replace(jeton, "x"), 1))

    def test_shell_ajoute_rougit(self):
        shells = {ORCH_GEMINI: ('"glob"]', '"glob", "run_shell_command"]'),
                  ORCH_COPILOT: ('"search"]', '"search", "shell"]'),
                  ORCH_KIMI: ("Glob", "Glob, Bash")}
        for chemin, (ancien, nouveau) in shells.items():
            with self.subTest(chemin=chemin):
                outils = OUTILS_C2[chemin]
                self.rouge(chemin, self.textes[chemin].replace(outils, outils.replace(ancien, nouveau), 1))

    def test_jeton_de_la_regle_directe_retire_rougit(self):
        for chemin in self.HOTES:
            for jeton in (JETONS_DIRECTE_COPILOT if chemin == ORCH_COPILOT else JETONS_DIRECTE):
                with self.subTest(chemin=chemin, jeton=jeton):
                    self.assertEqual(self.textes[chemin].count(jeton), 1)
                    self.rouge(chemin, self.textes[chemin].replace(jeton, "x", 1))

    def test_refus_repli_ou_jugement_des_miroirs_rougit(self):
        """Gemini et Kimi : la clause du refus, son repli exact et « never to your judgment » (M10 de l'exec-critic
        de C2 : « never to your judgment » levé dans Gemini ne rougissait rien)."""
        for chemin in MIROIRS_C2:
            t = self.textes[chemin]
            for nom, mute in (("refus retiré", t.replace(REFUS_DIRECT[ORCH_MD], "x", 1)),
                              ("repli inexact", t.replace(REPLI_DIRECT, REPLI_INEXACT, 1)),
                              ("jugement levé", t.replace(JUGEMENT, "to your judgment", 1))):
                with self.subTest(chemin=chemin, mutant=nom):
                    self.rouge(chemin, mute)

    def test_rangee_en_double_sous_une_autre_forme_rougit(self):
        for chemin in self.HOTES:
            with self.subTest(chemin=chemin):
                rangee = self.rangee(chemin)
                double = rangee + "\n     python3 .agents/bin/cadrage_plan.py --task <T> --file \"<path>\""
                self.rouge(chemin, self.textes[chemin].replace(rangee, double, 1))

    def test_commentaire_c1_retire_rougit(self):
        for chemin in MIROIRS_C2:
            with self.subTest(chemin=chemin):
                self.rouge(chemin, self.textes[chemin].replace(
                    COMMENTAIRE_C1, "(the deps-ready row above is the calling session's)", 1))

    def test_hors_plafond_retire_rougit(self):
        for chemin, jeton in ((ORCH_GEMINI, HORS_PLAFOND), (ORCH_KIMI, HORS_PLAFOND),
                              (ORCH_COPILOT, "outside the routing plan")):
            with self.subTest(chemin=chemin):
                self.rouge(chemin, self.textes[chemin].replace(jeton, "x", 1))

    def test_plafond_fantome_remis_dans_copilot_rougit(self):
        """T10 : la déf Copilot n'a pas de plafond de lignes ; « 45-line » remis rougit."""
        t = self.textes[ORCH_COPILOT]
        self.rouge(ORCH_COPILOT, t.replace("outside the routing plan", "outside the 45-line routing plan", 1))

    def test_objets_rendus_de_copilot_retires_rougissent(self):
        """Survivants M11 à M16 de l'exec-critic de C2 et objets rétablis : chaque jeton retiré rougit ; l'ordre des
        `done` inversé (« parent, then lots ») aussi ; l'éligibilité directe relue à l'envers aussi."""
        t = self.textes[ORCH_COPILOT]
        for jeton in (*JETONS_LECTURE_COPILOT, *JETONS_LOT_COPILOT, *JETONS_DIRECTE_COPILOT[-2:]):
            with self.subTest(jeton=jeton):
                self.assertEqual(t.count(jeton), 1, jeton)
                self.rouge(ORCH_COPILOT, t.replace(jeton, "x", 1))
        for nom, ancien, nouveau in (
                ("ordre des done inversé", "`done` lots, then parent", "`done` parent, then lots"),
                ("éligibilité inversée", "no open decision/security, readable SPECS",
                 "open decision/security or unreadable SPECS")):
            with self.subTest(mutant=nom):
                self.rouge(ORCH_COPILOT, t.replace(ancien, nouveau, 1))

    def test_ordre_copilot_cadrage_apres_la_detection_ou_retire_rougit(self):
        t = self.textes[ORCH_COPILOT]
        ancien = "cadrage then deps-ready precede `language-detector`;"
        self.assertEqual(t.count(ancien), 1)
        for nom, nouveau in (("déplacé", "deps-ready precedes `language-detector`, then cadrage;"),
                             ("retiré", "deps-ready precedes `language-detector`;")):
            with self.subTest(mutant=nom):
                self.rouge(ORCH_COPILOT, t.replace(ancien, nouveau, 1))


if __name__ == "__main__":
    unittest.main()
