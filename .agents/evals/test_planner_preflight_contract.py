"""La boucle planner <-> plan-critic porte ses textes de T-01M55W6GZ6 (partie texte).

CE QU'IL JUGE (decision pilote S-01M55W6WMBNSMT0NWCPC4YQG8F ; decoupe S-01M572P34JZRG1J2TJV43EQCVC) :
* planner x5 : la section « Before you hand back », ANCREE avant `## Rules` (md) ou avant
  « Hand the plan to the ONE plan critic » (Codex, Copilot), porte ses atomes DANS sa portee :
  les 7 lignes du critique, une commande et sa sortie par premisse sur la base COMMITEE, un
  mutant par temoin, chaque site d'un motif, le verdict INTEGRAL `docs/tasks/<T>-critic-<n>.md`
  lu en entier, `## Constats fermes`, `verdict integral absent`.
* plan-critic x5 : la puce « Iteration 1 is exhaustive », ANCREE entre « One line per finding »
  et « Attack the plan » (Copilot : avant « A verifying shell »), APRES le bareme de severite
  qu'elle cite ; tous les bloquants des le tour 1, `cmd => observed`, constats fermes puis diff
  r(n-1) -> r(n), `tardif`, gradation par le bareme, aucune ligne de checklist ni valeur de
  CAUSE_RACINE neuve ; la phrase « ephemeral console output » a quitte la def.
* relais NO_GO : kickoff x2 sur la ligne T7 (UNIQUE, par contenu, jamais par numero de ligne :
  le `:179` reste a test_plan_plafond), planning x2 dans le paragraphe « Verdict integral au
  NO_GO », copilot-instructions sur sa ligne T-01M55W6GZ6 ; les quatre reprises lisent le fichier
  `critic=`, sinon `COVERAGE DEGRADED — verdict integral absent` ; orchestrateurs x5 sur leur
  phrase NO_GO.
* preflight de forme (T-01M572N5Q3JVJWJDXC0D734ZDE, decision pilote S-01M57JCYTZWRR3D3Z593SMFDZ4) :
  l'outil `.agents/bin/plan_preflight.py` EXISTE (le bras « outil absent » qui le precedait est clos) ;
  planner x5 : la ligne `PREFLIGHT: à jouer par l’exécuteur` juste avant `## Approval requested`
  et le renvoi `PLAN_GRAMMAIRE.md § 5` ; plan-critic x5 : les bloquants de FORME sous `scope-fit`
  (ligne absente, sortie brute rc 0 non relayee, la ligne seule ne prouve rien), DANS le bareme ;
  orchestrateurs x5, kickoff x2, planning x2, copilot-instructions : le pas, ancre sur la commande
  UNIQUE `plan_preflight.py --plan`, avant chaque plan-critic, sortie brute, rc 1 rendu une fois au
  planner sans verdict ni iteration, second rc 1 consecutif au pilote (sous /planning : la tache
  sort du pool et le rapport le dit), rc 2 COVERAGE DEGRADED, que le critique range sous UNKNOWNS,
  jamais un NO_GO ; AGENTS.md : sa phrase. KIT SEUL : l'outil, son banc, ce banc et
  PLAN_GRAMMAIRE.md VOYAGENT (aucune regle `strip:` de `.template-exclude` ne les retire).
  Aucune de ces surfaces, ni CHANGELOG.md, n'ecrit que la ligne `PREFLIGHT:` « garantit » le
  preflight (L-00000111) : seule la sortie relayee le prouve.
* efforts, KIT SEUL : grille de MODEL_MODES colonne defaut planner `medium`, plan-critic `high`
  (S-01M57F0BHB, qui amende S-01M55W6WMB), et
  frontmatter `.claude` egal quand aucun MODEL_MODE n'est pose ; chez l'adoptant
  le bras saute en l'annoncant (override a ses risques, S-01M54WXT38HZ52GCMQSQ44CB5F).
Mutants, en memoire sur le texte REEL : chaque atome retire de sa portee rougit ; la section
retiree de son ancre rougit ; chaque atome du preflight retire de sa surface rougit, la ligne
`PREFLIGHT:` eloignee de `## Approval requested` rougit, une « garantie » injectee rougit ;
la puce critique remontee au-dessus du bareme rougit ; `medium` -> `high` sur la grille rougit.
Le texte est compare APLATI : `**` et backticks retires, blancs reduits, tiret cadratin lu comme
un tiret ASCII, casse ignoree (la def Codex est en ASCII).
CE QU'IL NE PROUVE PAS. Un atome present n'est pas une regle obeie : le planner peut ecrire ses
preuves sans les avoir jouees, l'executeur peut oublier d'ecrire le fichier `critic-<n>.md` —
plan-critic et exec-critic rejouent ; aucun code ne lit `critic=`. Les rosters sont tenus par
test_cadre_roster.py, le bareme par test_plan_critic_contract.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOTES = (".claude/agents/{}.md", ".gemini/agents/{}.md", ".kimi-code/agents/{}.md",
         ".codex/agents/{}.toml", ".github/agents/{}.agent.md")
PLANNER = tuple(h.format("planner") for h in HOTES)
CRITIC = tuple(h.format("plan-critic") for h in HOTES)
ORCH = tuple(h.format("orchestrator") for h in HOTES)
KICKOFF = (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md")
PLANNING = (".agents/skills/planning/SKILL.md", ".claude/commands/planning.md")
COPILOT_INSTR = ".github/copilot-instructions.md"
SURFACES = PLANNER + CRITIC + ORCH + KICKOFF + PLANNING + (COPILOT_INSTR,)
OUTIL = ROOT / ".agents" / "bin" / "plan_preflight.py"
#: L'ouverture APLATIE du bareme de severite des plan-critic x5 (reecrit par le lot E de T-01M572N5Q3).
RUBRIQUE = "severity rubric - blocking is reserved"


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def plat(texte: str) -> str:
    """Aplati : `**` et backticks retires, tiret cadratin -> tiret, blancs reduits, minuscules."""
    t = texte.replace("**", "").replace("`", "").replace("—", "-")
    return re.sub(r"\s+", " ", t).lower()


def forme(rel: str) -> str:
    if rel.endswith(".toml"):
        return "codex"
    return "copilot" if rel.endswith(".agent.md") else "md"


BORNES = {
    ("planner", "md"): ("## before you hand back - play the critic's checklist yourself", "## rules"),
    ("planner", "codex"): ("before you hand back - play the critic's checklist yourself",
                           "hand the plan to the one plan critic"),
    ("planner", "copilot"): ("before you hand back - play the critic's checklist yourself",
                             "hand the plan to the one plan critic"),
    ("critic", "md"): ("- iteration 1 is exhaustive (", "- attack the plan, never the planner."),
    ("critic", "codex"): ("- iteration 1 is exhaustive (", "- attack the plan, never the planner."),
    ("critic", "copilot"): ("iteration 1 is exhaustive (", "a verifying shell, never a writing one (t-00000707)."),
}
ATOMES = {
    "planner": ("t-01m55w6gz6phre554hvtpgn416", "the 7 rows", "verdict and citation",
                "one premise, one command", "cmd => observed", "committed base",
                "one mutant per witness", "never in the tree", "its red line", "every site of each pattern you fix",
                "git grep", "outside the write-set", "integral verdict", "docs/tasks/<t>-critic-<n>.md",
                "read whole, never a summary", "## constats fermés", "non fermé",
                "coverage degraded - verdict intégral absent"),
    "critic": ("t-01m55w6gz6phre554hvtpgn416", "every blocking finding", "never only the first",
               "cmd => observed", "## constats fermés", "claims closed", "r(n-1)", "r(n-1) absent: the whole plan", "not the whole suite again",
               "tardif", "severity rubric above", "never by its iteration", "adds no checklist row",
               "no cause_racine value"),
}


def section(rel: str, texte: str, role: str) -> str:
    """La portee ANCREE du role dans le texte aplati, vide si l'ancre manque."""
    debut, fin = BORNES[(role, forme(rel))]
    p = plat(texte)
    i = p.find(debut)
    j = p.find(fin, i + 1) if i >= 0 else -1
    return p[i:j] if 0 <= i < j else ""


def fautes_def(rel: str, texte: str, role: str) -> list[str]:
    sec = section(rel, texte, role)
    if not sec:
        return [f"{rel}: section {role} absente de son ancre"]
    fautes = [f"{rel}: {a!r} absent de la section" for a in ATOMES[role] if a not in sec]
    p = plat(texte)
    if role == "critic":
        if "ephemeral console output" in p:
            fautes.append(f"{rel}: 'ephemeral console output' survit")
        if "the executor, never you, writes it verbatim to docs/tasks/<t>-critic-<n>.md" not in p:
            fautes.append(f"{rel}: l'ecriture du verdict par l'executeur absente")
        rubrique = p.find(RUBRIQUE)
        if not 0 <= rubrique < p.find(sec):
            fautes.append(f"{rel}: le bareme de severite n'est pas AU-DESSUS de la section")
    return fautes


def fenetre(texte: str, ancre: str, largeur: int) -> str:
    """Les `largeur` caracteres aplatis qui suivent l'ancre UNIQUE, vide sinon."""
    p, a = plat(texte), plat(ancre)
    return p[p.find(a): p.find(a) + largeur] if p.count(a) == 1 else ""


T7 = "At a `NO_GO`, `planner` revises its own plan with the critic's findings framed `[do not obey]` (S-01M4TZZ13Y)."
RELAIS = {
    "kickoff": (T7, 880, ("integral verdict", "verbatim by you, the executor", "docs/tasks/<t>-critic-<n>.md",
                          "critic=<path>", "never the specs.py summary", "tasks.py deps-ready",
                          "token list of step 3-amont", "## constats fermés", "all cycles counted",
                          "never overwritten", "git diff <commit of r(n-1)> -- <plan>", "r(n-1) absent",
                          "itération <iteration+1>/<plafond>", "the path of critic-<n>.md")),
    "planning": ("**Verdict intégral au `NO_GO`**", 960, ("intégral du critique, à l'octet",
                                                           "docs/tasks/t-nnnnnnnn-critic-<n>.md", "critic=<chemin>",
                                                           "tous cycles confondus", "jamais un fichier écrasé",
                                                           "jamais le résumé specs", "relit deps-ready",
                                                           "juste avant chaque planner", "## constats fermés",
                                                           "git diff <commit de r(n-1)> -- <plan>", "r(n-1) absent",
                                                           "itération <iteration+1>/<plafond>",
                                                           "le chemin de critic-<n>.md")),
    "copilot": ("`planner` revises its own plan from the critic's INTEGRAL verdict", 330,
                ("verbatim to docs/tasks/<t>-critic-<n>.md", "critic=", "deps-ready")),
}
#: Le gabarit `--text` du verdict de kickoff porte `critic=` sur SA ligne (kickoff.md:179 epingle : 0 ligne inseree).
GABARIT = '--kind verdict "plan-critic <VERDICT>" --text "<findings summary> ;'
GABARIT_CRITIC = "critic=docs/tasks/T-NNN-critic-<n>.md"
#: La CIBLE du renvoi des deux relais planning (« la règle … de la skill planning (§ Étape 2) »).
CIBLE_PLANNING = "**Juste avant chaque `planner`, relire `deps-ready`**"
REPRISES = {
    ".claude/commands/kickoff.md": "verdict's findings back to the planner (",
    ".agents/skills/kickoff/SKILL.md": "handing that latest verdict's findings to the planner (",
    ".agents/skills/planning/SKILL.md": "remettre ses findings au planner (",
    ".claude/commands/planning.md": "remet ses findings au planner (",
}
REPRISE_ATOMES = ("critic=", "coverage degraded - verdict intégral absent")
ORCH_ANCRE = {"md": "A `NO_GO` goes back to `planner`, never to a dev agent and never to your own hand.",
              "codex": "A NO_GO goes back to planner, never to a dev agent.",
              "copilot": "a `NO_GO` goes back to `planner` with the INTEGRAL verdict"}
ORCH_ATOMES = {"md": ("integral verdict", "executor writes verbatim", "docs/tasks/<t>-critic-<n>.md", "critic="),
               "codex": ("integral verdict", "executor writes verbatim", "docs/tasks/<t>-critic-<n>.md", "critic="),
               "copilot": ("integral verdict", "<t>-critic-<n>.md")}


def fautes_relais(rel: str, texte: str) -> list[str]:
    nature = "kickoff" if rel in KICKOFF else "planning" if rel in PLANNING else "copilot"
    ancre, largeur, atomes = RELAIS[nature]
    zone = fenetre(texte, ancre, largeur)
    if not zone:
        return [f"{rel}: ancre de relais absente ou non unique"]
    fautes = [f"{rel}: {a!r} absent du relais" for a in atomes if a not in zone]
    if nature == "kickoff":
        ligne = [lg for lg in texte.splitlines() if T7 in lg]
        if len(ligne) != 1 or "INTEGRAL verdict" not in ligne[0]:
            fautes.append(f"{rel}: le relais n'est pas sur la ligne T7")
        if not re.search(r"(?m)^3-amont\. \*\*L'amont d'abord", texte):
            fautes.append(f"{rel}: cible « step 3-amont » absente")
        gabarit = [lg for lg in texte.splitlines() if GABARIT in lg]
        if len(gabarit) != 1 or GABARIT_CRITIC not in gabarit[0]:
            fautes.append(f"{rel}: gabarit --text sans {GABARIT_CRITIC!r}")
    if nature == "planning" and CIBLE_PLANNING not in lire(".agents/skills/planning/SKILL.md"):
        fautes.append(f"{rel}: cible « Juste avant chaque planner » absente")
    if rel in REPRISES:
        reprise = fenetre(texte, REPRISES[rel], 230)
        fautes += [f"{rel}: reprise sans {a!r}" for a in REPRISE_ATOMES if a not in reprise]
    return fautes


def fautes_orch(rel: str, texte: str) -> list[str]:
    zone = fenetre(texte, ORCH_ANCRE[forme(rel)], 330)
    if not zone:
        return [f"{rel}: phrase NO_GO absente ou non unique"]
    return [f"{rel}: {a!r} absent de la phrase NO_GO" for a in ORCH_ATOMES[forme(rel)] if a not in zone]


# --- le preflight de forme (T-01M572N5Q3JVJWJDXC0D734ZDE) : nomme sur chaque surface, a sa place ------
PREFLIGHT_LIGNE = "preflight: à jouer par l’exécuteur"
APPROVAL = "## approval requested"
#: Défs en anglais depuis T-01M5S9338BJP1B5RM3TG14AMYT : le titre cité « Préflight de forme » reste
#: (nom de section de la fiche), la consigne est anglaise ; la française d'avant ne satisfait plus.
RENVOI_P5 = "préflight de forme. read .agents/ref/plan_grammaire.md § 5 before writing."
RENVOI_P5_FR = "préflight de forme. lis .agents/ref/plan_grammaire.md § 5 avant d'écrire."
CRITIC_FORME = "form blockers under scope-fit:"
CRITIC_FIN = "(pilot decision s-01m52y43ba)"
CRITIC_ATOMES = ("a plan over 45 non-blank lines (plan_lots.py check rc 1)",
                 "a missing preflight: à jouer par l’exécuteur line",
                 "missing raw rc 0 plan_preflight.py output relayed in the invocation",
                 "a relayed rc 2 under coverage degraded is written under unknowns, a concern, never a no_go",
                 "read that output; do not rerun the tool", "the plan line alone proves nothing")
COMMANDE = "plan_preflight.py --plan"
_ORCH_MD = ("preflight: calling session runs", "before each plan-critic and relays raw output + rc",
            "rc 0 continues", "rc 1 logs and sends the diagnostic to planner once",
            "never a plan-critic verdict or iteration",
            "a second consecutive rc 1 stops and asks the pilot", "rc 2 reports coverage degraded with cause",
            "never claims a preflight: line proves execution")
_SKILL_FR = ("avant chaque plan-critic, y compris le passage court r3", "sortie brute, rc compris",
             "plan_grammaire.md § 5", "rc 0 tient la forme seule",
             "renvoie une fois au planner, sans verdict ni itération plan-critic",
             "au second rc 1 consécutif du cycle, arrêter et saisir le pilote",
             "rc 2 annonce coverage degraded avec sa cause", "la ligne preflight: du plan ne prouve aucun résultat")
PAS = {
    ".claude/agents/orchestrator.md": _ORCH_MD, ".gemini/agents/orchestrator.md": _ORCH_MD,
    ".kimi-code/agents/orchestrator.md": _ORCH_MD,
    ".codex/agents/orchestrator.toml": (
        "preflight (calling session, before each plan-critic)", "relay raw output + rc", "rc 0 continues",
        "rc 1 logs the diagnostic and returns it to planner once, never a plan-critic verdict or iteration",
        "a second consecutive rc 1 stops, logs the diagnostic and asks the pilot",
        "rc 2 reports coverage degraded with cause", "a preflight: line alone proves nothing"),
    ".github/agents/orchestrator.agent.md": (
        "before each plan-critic, executor runs", "relay raw output and rc", "rc 0 proceeds",
        "rc 1 logs and returns diagnostics to planner once", "never a plan-critic verdict or iteration",
        "second consecutive rc 1 stops for pilot",
        "rc 2 reports coverage degraded with cause", "preflight: proves nothing"),
    ".agents/skills/kickoff/SKILL.md": _SKILL_FR,
    ".agents/skills/planning/SKILL.md": tuple(a.replace(
        "au second rc 1 consécutif du cycle, arrêter et saisir le pilote",
        "au second rc 1 consécutif du cycle, la tâche sort du pool ; le rapport dit le second rc 1")
        for a in _SKILL_FR),
    ".claude/commands/kickoff.md": (
        "before each plan-critic call (full or short r3)", "raw output and rc separately",
        "plan_grammaire.md § 5", "rc 0 = form held, not substance",
        "return the plan to planner once, without a plan-critic verdict or iteration",
        "a second consecutive rc 1 in this cycle stops and asks the pilot",
        "rc 2 = announce coverage degraded with its cause", "never read the plan's preflight: line as proof of a run"),
    ".claude/commands/planning.md": (
        "avant chaque plan-critic, jouer", "sortie brute, rc compris", "plan_grammaire.md § 5",
        "rc 0 tient la forme seule", "rendre une fois au planner sans verdict ni itération plan-critic",
        "au second rc 1 consécutif du cycle, la tâche sort du pool ; le rapport dit le second rc 1",
        "rc 2 : annoncer coverage degraded avec sa cause", "la ligne preflight: du plan ne prouve aucun résultat"),
    COPILOT_INSTR: (
        "before each plan-critic invocation, including short r3", "raw output and rc separately",
        "plan_grammaire.md § 5", "rc 0 holds form only",
        "returns the plan once to planner, with no plan-critic verdict or iteration",
        "second consecutive rc 1 of the cycle, stop and ask the pilot",
        "rc 2 announces coverage degraded with its cause",
        "a plan's preflight: line is a declaration, never proof of execution"),
    "AGENTS.md": (
        "avant chaque plan-critic, l'exécuteur joue", "relaie sa sortie brute",
        "rc 1 rend le plan au planner sans compter d'itération", "second rc 1 consécutif : le pilote",
        "rc 2 = coverage degraded", "forme seule : aucun banc rejoué, aucune donnée du plan exécutée",
        "la ligne preflight: du plan ne prouve rien", "plan_grammaire.md § 5"),
}
#: C13 / L-00000111 : la ligne `PREFLIGHT:` est une constante, jamais la preuve d'un passage.
GARANTIE = re.compile(r"pr[eé]flight[^.;]{0,120}(garanti|guarantee)|(garanti|guarantee)[^.;]{0,60}pr[eé]flight")
SANS_GARANTIE = SURFACES + ("AGENTS.md", "CHANGELOG.md")


def zone_pas(p: str) -> str:
    """Autour de la commande UNIQUE du texte aplati : 160 caracteres avant, 760 apres ; vide sinon."""
    i = p.find(COMMANDE)
    return p[max(0, i - 160): i + 760] if p.count(COMMANDE) == 1 else ""


def fautes_pas(rel: str, texte: str) -> list[str]:
    zone = zone_pas(plat(texte))
    if not zone:
        return [f"{rel}: commande {COMMANDE!r} absente ou non unique"]
    return [f"{rel}: {a!r} absent du pas preflight" for a in PAS[rel] if a not in zone]


def fautes_preflight_planner(rel: str, texte: str) -> list[str]:
    p, fautes = plat(texte), []
    k = p.find(APPROVAL)
    if p.count(APPROVAL) != 1 or PREFLIGHT_LIGNE not in p[max(0, k - 60):k]:
        fautes.append(f"{rel}: {PREFLIGHT_LIGNE!r} absent juste avant {APPROVAL!r}")
    if RENVOI_P5 not in p:
        fautes.append(f"{rel}: {RENVOI_P5!r} absent")
    return fautes


def fautes_preflight_critic(rel: str, texte: str) -> list[str]:
    p = plat(texte)
    i, rubrique = p.find(CRITIC_FORME), p.find(RUBRIQUE)
    if p.count(CRITIC_FORME) != 1:
        return [f"{rel}: {CRITIC_FORME!r} absent ou non unique"]
    fautes = [f"{rel}: {a!r} absent des bloquants de forme" for a in CRITIC_ATOMES if a not in p[i:i + 420]]
    if not 0 <= rubrique < i < p.find(CRITIC_FIN, max(rubrique, 0)):
        fautes.append(f"{rel}: les bloquants de forme ne sont pas DANS le bareme de severite")
    return fautes


def fautes_garantie(rel: str, texte: str) -> list[str]:
    m = GARANTIE.search(plat(texte))
    return [f"{rel}: le preflight y est dit « garanti » : {m.group(0)!r}"] if m else []


@pytest.mark.parametrize("rel", PLANNER)
def test_planner_porte_la_section(rel: str) -> None:
    assert fautes_def(rel, lire(rel), "planner") == []


@pytest.mark.parametrize("rel", CRITIC)
def test_critic_porte_la_section(rel: str) -> None:
    assert fautes_def(rel, lire(rel), "critic") == []


@pytest.mark.parametrize("rel", KICKOFF + PLANNING + (COPILOT_INSTR,))
def test_doctrine_relaie(rel: str) -> None:
    assert fautes_relais(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", ORCH)
def test_orchestrateur_relaie(rel: str) -> None:
    assert fautes_orch(rel, lire(rel)) == []


def test_l_outil_existe() -> None:
    assert OUTIL.is_file(), "les surfaces prescrivent plan_preflight.py : l'outil doit exister"


@pytest.mark.parametrize("rel", PLANNER)
def test_planner_rend_la_ligne_preflight(rel: str) -> None:
    assert fautes_preflight_planner(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", CRITIC)
def test_critic_bloque_la_forme(rel: str) -> None:
    assert fautes_preflight_critic(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", sorted(PAS))
def test_pas_preflight(rel: str) -> None:
    assert fautes_pas(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", SANS_GARANTIE)
def test_aucune_surface_ne_dit_le_preflight_garanti(rel: str) -> None:
    assert fautes_garantie(rel, lire(rel)) == []


# --- mutants en memoire, sur le texte REEL : chaque atome retire de sa portee rougit ---------------
def _retire(texte: str, atome: str, ancre: str = "", largeur: int = 0) -> str:
    """Le texte reel aplati, l'atome efface partout — ou, l'ancre donnee, dans sa seule fenetre."""
    p = plat(texte)
    if not ancre:
        return p.replace(atome, "#" * len(atome))
    i = p.find(plat(ancre))
    return p[:i] + p[i: i + largeur].replace(atome, "#" * len(atome)) + p[i + largeur:]


def _nomme(fautes: list[str], atome: str) -> bool:
    """Le rouge est celui de l'atome, pas un rouge de passage."""
    return any(repr(atome) in f for f in fautes)


@pytest.mark.parametrize("rel,role", [(r, "planner") for r in PLANNER] + [(r, "critic") for r in CRITIC])
def test_mutant_atome_de_def(rel: str, role: str) -> None:
    texte = lire(rel)
    assert fautes_def(rel, texte, role) == [], "base rouge : le mutant ne prouverait rien"
    for atome in ATOMES[role]:
        assert _nomme(fautes_def(rel, _retire(texte, atome), role), atome), f"{rel}: retirer {atome!r} ne rougit pas"
    debut, _ = BORNES[(role, forme(rel))]
    assert fautes_def(rel, plat(texte).replace(debut, "x"), role), f"{rel}: ancre retiree ne rougit pas"
    if role == "critic":
        sec = section(rel, texte, role)
        remonte = sec + " " + plat(texte).replace(sec, "")
        assert any("AU-DESSUS" in f for f in fautes_def(rel, remonte, role)), f"{rel}: puce au-dessus du bareme"
        assert fautes_def(rel, texte + "\nThe verdict is ephemeral console output.\n", role)


@pytest.mark.parametrize("rel", KICKOFF + PLANNING + (COPILOT_INSTR,))
def test_mutant_relais(rel: str) -> None:
    texte = lire(rel)
    assert fautes_relais(rel, texte) == [], "base rouge : le mutant ne prouverait rien"
    nature = "kickoff" if rel in KICKOFF else "planning" if rel in PLANNING else "copilot"
    ancre, largeur, atomes = RELAIS[nature]
    for atome in atomes:
        mute = _retire(texte, atome, ancre, largeur)
        assert _nomme(fautes_relais(rel, mute), atome), f"{rel}: retirer {atome!r} ne rougit pas"
    for atome in REPRISE_ATOMES if rel in REPRISES else ():
        mute = _retire(texte, atome, REPRISES[rel], 230)
        assert any(f"reprise sans {atome!r}" in f for f in fautes_relais(rel, mute)), f"{rel}: reprise {atome!r}"
    if nature == "kickoff":
        deplace = texte.replace(T7 + " Hand it", T7 + "\n Hand it", 1)
        assert any("ligne T7" in f for f in fautes_relais(rel, deplace)), f"{rel}: relais hors de la ligne T7"
        renomme = texte.replace("\n3-amont. **L'amont d'abord", "\n3-bis. **L'amont d'abord", 1)
        assert any("step 3-amont" in f for f in fautes_relais(rel, renomme)), f"{rel}: cible renommee"
        sans_critic = texte.replace(GABARIT_CRITIC, "critic=?", 1)
        assert any("gabarit --text" in f for f in fautes_relais(rel, sans_critic)), f"{rel}: gabarit sans critic="


@pytest.mark.parametrize("rel", ORCH)
def test_mutant_orchestrateur(rel: str) -> None:
    texte = lire(rel)
    assert fautes_orch(rel, texte) == [], "base rouge : le mutant ne prouverait rien"
    ancre = ORCH_ANCRE[forme(rel)]
    for atome in ORCH_ATOMES[forme(rel)]:
        if atome in plat(ancre):
            continue  # l'atome EST l'ancre : son retrait est le mutant « phrase absente » ci-dessous
        assert _nomme(fautes_orch(rel, _retire(texte, atome, ancre, 330)), atome), f"{rel}: retirer {atome!r}"
    assert fautes_orch(rel, plat(texte).replace(plat(ancre), "x")), f"{rel}: phrase NO_GO retiree ne rougit pas"


@pytest.mark.parametrize("rel", PLANNER)
def test_mutant_preflight_planner(rel: str) -> None:
    p = plat(lire(rel))
    assert fautes_preflight_planner(rel, p) == [], "base rouge : le mutant ne prouverait rien"
    sans = p.replace(PREFLIGHT_LIGNE, "#" * len(PREFLIGHT_LIGNE))
    assert _nomme(fautes_preflight_planner(rel, sans), PREFLIGHT_LIGNE), f"{rel}: ligne retiree"
    eloignee = PREFLIGHT_LIGNE + " " + p.replace(PREFLIGHT_LIGNE, "", 1)
    assert _nomme(fautes_preflight_planner(rel, eloignee), PREFLIGHT_LIGNE), f"{rel}: ligne hors de sa place"
    assert _nomme(fautes_preflight_planner(rel, p.replace(RENVOI_P5, "")), RENVOI_P5), f"{rel}: renvoi § 5"
    francais = p.replace(RENVOI_P5, RENVOI_P5_FR)
    assert francais != p and _nomme(fautes_preflight_planner(rel, francais), RENVOI_P5), f"{rel}: renvoi § 5 en français"


@pytest.mark.parametrize("rel", CRITIC)
def test_mutant_preflight_critic(rel: str) -> None:
    p = plat(lire(rel))
    assert fautes_preflight_critic(rel, p) == [], "base rouge : le mutant ne prouverait rien"
    for atome in CRITIC_ATOMES:
        mute = _retire(p, atome, CRITIC_FORME, 420)
        assert _nomme(fautes_preflight_critic(rel, mute), atome), f"{rel}: retirer {atome!r} ne rougit pas"
    assert fautes_preflight_critic(rel, p.replace(CRITIC_FORME, "x")), f"{rel}: bloquants de forme retires"
    i = p.find(CRITIC_FORME)
    hors = p[:i] + p[p.find(CRITIC_FIN, i) + len(CRITIC_FIN):] + " " + p[i:p.find(CRITIC_FIN, i)]
    assert any("DANS le bareme" in f for f in fautes_preflight_critic(rel, hors)), f"{rel}: hors du bareme"


@pytest.mark.parametrize("rel", sorted(PAS))
def test_mutant_pas_preflight(rel: str) -> None:
    p = plat(lire(rel))
    assert fautes_pas(rel, p) == [], "base rouge : le mutant ne prouverait rien"
    zone = zone_pas(p)
    for atome in PAS[rel]:
        mute = p.replace(zone, zone.replace(atome, "#" * len(atome)))
        assert _nomme(fautes_pas(rel, mute), atome), f"{rel}: retirer {atome!r} ne rougit pas"
    assert fautes_pas(rel, p.replace(zone, "")), f"{rel}: pas retire ne rougit pas"
    assert fautes_pas(rel, p + " " + COMMANDE), f"{rel}: commande dupliquee ne rougit pas"


@pytest.mark.parametrize("rel", SANS_GARANTIE)
def test_mutant_garantie_injectee(rel: str) -> None:
    for phrase in ("La ligne PREFLIGHT: garantit le préflight.", "The PREFLIGHT: line guarantees the run."):
        assert fautes_garantie(rel, lire(rel) + "\n" + phrase + "\n"), f"{rel}: {phrase!r}"


# adopting-tree: le marqueur d'identite du kit ne voyage pas ; son absence EST le signal « projet adoptant ».
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()


# --- le preflight voyage : kit seul (.template-exclude ne voyage pas) -----------------------------
VOYAGEURS = (".agents/bin/plan_preflight.py", ".agents/bin/test_plan_preflight.py",
             ".agents/evals/test_planner_preflight_contract.py", ".agents/ref/PLAN_GRAMMAIRE.md")


def fautes_voyage(exclude: str) -> list[str]:
    sys.path.insert(0, str(ROOT / ".agents" / "bin"))
    import sync_template as st
    regles = st.parse_exclude(exclude)
    return [f"{p}: ne voyage plus ({r.raw})" for p in VOYAGEURS
            if (r := st.match_rule(p, regles)) is not None and r.polarity == "strip"]


@pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCÉ : .template-exclude est du kit seul")
def test_l_outil_voyage() -> None:
    t = (ROOT / ".template-exclude").read_text(encoding="utf-8")
    assert fautes_voyage(t) == []
    assert fautes_voyage(t + "\nstrip: .agents/bin/plan_preflight.py\n"), "mutant strip ne rougit pas"


# --- efforts : kit seul -----------------------------------------------------------------------------
GRILLE = re.compile(r"^\| `(claude|codex)` \| `(planner|plan-critic)` \| effort \| `(\w+)` \|", re.M)


def efforts(texte: str) -> dict[tuple[str, str], str]:
    return {(h, r): e for h, r, e in GRILLE.findall(texte)}


@pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : projet adoptant, efforts a ses risques (S-01M54WXT38HZ52GCMQSQ44CB5F)")
def test_efforts_grille_defaut() -> None:
    g = efforts(lire(".agents/ref/MODEL_MODES.md"))
    assert g.get(("claude", "planner")) == "medium" and g.get(("claude", "plan-critic")) == "high", g
    assert g.get(("codex", "planner")) == "medium" and g.get(("codex", "plan-critic")) == "high", g
    # adopting-tree: l'etat local du mode n'existe que chez qui l'a pose ; absent, les defs valent la colonne defaut
    if (ROOT / ".agents" / "state" / "local" / "MODEL_MODE").is_file():
        pytest.skip("SAUT ANNONCE : MODEL_MODE pose, les defs suivent le mode")
    assert "effort: medium" in lire(".claude/agents/planner.md")
    assert "effort: high" in lire(".claude/agents/plan-critic.md")


def test_mutant_effort_grille() -> None:
    reel = lire(".agents/ref/MODEL_MODES.md")
    ligne = "| `claude` | `planner` | effort | `medium` |"
    assert reel.count(ligne) == 1, "ligne de grille introuvable : le mutant ne prouverait rien"
    assert efforts(reel.replace(ligne, ligne.replace("`medium`", "`high`"))).get(("claude", "planner")) == "high"
