"""TÉMOIN du lot C (T-01M4ZWNEDCJCNFF4HWQEWZX1J0, décision pilote S-01M51H3PTQ75984NP7ZD7JZBMS) :
kickoff ne renvoie plus au CHANGELOG ni pour borner un constat, ni comme exemple d'INTÉGRATION ;
la borne se trace sur la tâche (`specs.py add --kind delta`), qui voyage avec le kit.
Rouge sur la base (2 failed), vert après le lot C. Portée de la règle : universelle (specs.py
voyage) ; ce banc, lui, saute hors du kit, où kickoff peut être réécrit par l'adoptant.
Ne juge PAS le reste de kickoff, ni les autres surfaces (planner/plan-critic : suite nommée au plan)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

SURFACES = (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md")
INTERDITS = ("bounded in the CHANGELOG", "`CHANGELOG.md` for instance", "`CHANGELOG.md` par exemple")
REQUIS = "specs.py add --kind delta"


def fautes(texte: str) -> list:
    plat = " ".join(texte.split())
    f = [i for i in INTERDITS if i in plat]
    if REQUIS not in plat:
        f.append(f"absent : {REQUIS}")
    return f


@pytest.mark.parametrize("rel", SURFACES)
def test_kickoff_trace_la_borne_sur_la_tache(rel):
    assert fautes((ROOT / rel).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("mutant", INTERDITS)
def test_un_interdit_qui_revient_rougit(mutant):
    assert fautes(f"x {REQUIS} y {mutant} z") != []


@pytest.mark.parametrize(
    ("rel", "attendus"),
    (
        (
            SURFACES[0],
            ("Skip that task, report the refusal", "through `communicator`", "do not retry with an override", "pilot decision", "squash or rebase merge"),
        ),
        (
            SURFACES[1],
            ("saute la tâche et rapporte le refus", "via `communicator`", "ni chaîne ni levée automatique", "décision du pilote", "squash/rebase merge"),
        ),
    ),
)
def test_claim_refusal_reported(rel, attendus):
    texte = (ROOT / rel).read_text(encoding="utf-8")
    debut = texte.index("rc 2 `REVENDICATION`")
    consigne = " ".join(texte[max(0, debut - 80) : debut + 800].split())
    for requis in (*attendus, "start", "fournee", "argparse", "--sans-revendication", "--no-ff"):
        assert requis in consigne, (rel, requis)
    if rel == SURFACES[1]:
        assert texte.splitlines()[178] == "   Record the FINAL verdict: `python .agents/bin/specs.py add --task T-NNN"


# TÉMOIN du lot H (T-01M5HSV3HV0140Q7BA7FX87GPF, parent T-01M5G7RTQ9RY3WGZ8T9W6ZX9RS, décision pilote
# S-01M5HH8QMC, arbitrage S-01M5HPRHV3) : les surfaces de lancement sautent la tâche étrangère, renvoient
# le pilote à SON terminal, n'offrent aucune reprise automatique et disent la borne mesurée — marqueur
# d'agent sous Claude Code et dans les hooks qui posent AGENTS_HOOK_HOST ; Codex, Gemini, Copilot, Kimi
# sans marqueur, TTY + saisie = friction. Rouge si une surface prescrit `--reprise` à l'agent, retire un
# nom d'hôte ou prétend Codex couvert. Ne juge ni le code de `--reprise` (lot A) ni les skills (lot E).
# Lot F de T-01M5MCXKHQS4BME9Z9VVSWD6VT (décision pilote S-01M5MCXYH589THMGDR9XMH41ES) : Copilot CLI pose
# COPILOT_AGENT_SESSION_ID et COPILOT_CLI dans le shell de l'agent (mesuré, 1.0.96) ; kickoff.md le dit
# et ôte Copilot des hôtes de session (`session_hotes`). Lot B de l'aval T-01M5MCXMQVHZ231CW0K2JR76MD
# (T-01M5MY17WGT01198R0GZR1WRRM) : copilot-instructions.md:7 le dit aussi, en anglais, et ôte Copilot de
# ses hôtes de session. `neuves` exigées dans la fenêtre, `anciennes` refusées partout.
FENETRE = 2500
HOTES_SESSION = ("Codex", "Gemini", "Copilot", "Kimi")
HOTES_HOOKS = ("Codex", "Kimi", "Copilot")
NEUVES_KICKOFF = (
    "Codex, Gemini et Kimi sans marqueur",
    "Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent (mesuré, 1.0.96) :"
    " ce marqueur refuse la reprise",
    "faux positif nommé : un terminal du pilote ouvert depuis une session Copilot hérite de `COPILOT_CLI`",
)
ANCIENNES_KICKOFF = ("dans une session Codex, Gemini, Copilot ou Kimi, aucun marqueur",)
NEUVES_COPILOT = (
    "in a Codex, Gemini or Kimi session there is no marker",
    "a Copilot session exports `COPILOT_AGENT_SESSION_ID` and `COPILOT_CLI` in the agent's shell"
    " (measured 2026-10-23, Copilot CLI 1.0.96)",
    "named false positive: `COPILOT_CLI` is inherited by any shell started from Copilot CLI",
)
ANCIENNES_COPILOT = ("in a Codex, Gemini, Copilot or Kimi session there is no marker",)
COUVERT = re.compile(r"\b(?:Codex|Gemini|Copilot|Kimi)\b[^.;:]{0,80}(?<!non )(?<!not )\b(?:couverts?|covered)\b")
BORNE_H = {
    ".claude/commands/kickoff.md": {
        "ancre": "rc 2 `REVENDICATION`",
        "requis": ("saute la tâche et rapporte le refus", "ni chaîne ni levée automatique", "décision du pilote",
                   "terminal du pilote", "aucune reprise automatique", "Un agent ne reprend JAMAIS une tâche",
                   "ne lance, ne prescris ni ne propose `--reprise`", "option REFUSÉE (rc 2)",
                   "saisie exacte de l'identifiant", "winpty bash .agents/pyrun.sh .agents/bin/tasks.py",
                   "Windows Terminal", "TTY + saisie ne sont qu'une friction", "franchissable en une commande",
                   "faux négatif nommé"),
        "hooks": ("sous Claude Code et dans les hooks du kit qui posent `AGENTS_HOOK_HOST` (", ")"),
        "session": ("dans une session ", "aucun marqueur"),
        "couvert": " ; Codex est couvert par le marqueur",
        "session_hotes": ("Codex", "Gemini", "Kimi"),
        "neuves": NEUVES_KICKOFF,
        "anciennes": ANCIENNES_KICKOFF,
        "mutants": 15,
    },
    ".github/copilot-instructions.md": {
        "ancre": "yields `REVENDICATION` rc 2",
        "requis": ("skips and reports that task", "no automatic override", "pilot decision",
                   "pilot's own terminal", "no automatic takeover", "An agent NEVER takes a task over",
                   "never run, prescribe or propose `--reprise`", "REFUSED option (rc 2)",
                   "exact task id typed back", "winpty bash .agents/pyrun.sh .agents/bin/tasks.py",
                   "Windows Terminal", "TTY + typing are only a friction", "crossed in one command",
                   "named false negative"),
        "hooks": ("under Claude Code and in the kit's hooks that set `AGENTS_HOOK_HOST` (", ")"),
        "session": ("in a ", "session there is no marker"),
        "couvert": "; Codex is covered by the marker",
        "session_hotes": ("Codex", "Gemini", "Kimi"),
        "neuves": NEUVES_COPILOT,
        "anciennes": ANCIENNES_COPILOT,
        "mutants": 15,
    },
}


def _segment(plat: str, bornes: tuple, depuis: int) -> tuple:
    """(début, fin) du segment entre les deux bornes, cherché à partir de `depuis` ; (-1, -1) si absent."""
    d = plat.find(bornes[0], depuis)
    if d < 0:
        return (-1, -1)
    f = plat.find(bornes[1], d + len(bornes[0]))
    return (-1, -1) if f < 0 else (d + len(bornes[0]), f)


def fautes_h(texte: str, spec: dict) -> list:
    plat = " ".join(texte.split())
    debut = plat.find(spec["ancre"])
    if debut < 0:
        return [f"ancre absente : {spec['ancre']}"]
    fenetre = plat[debut : debut + FENETRE]
    f = [f"absent : {r}" for r in spec["requis"] if r not in fenetre]
    h = _segment(plat, spec["hooks"], debut)
    s = _segment(plat, spec["session"], h[1] if h[1] >= 0 else debut)
    if h[0] < 0 or s[0] < 0 or s[1] > debut + FENETRE:
        f.append("borne mesurée absente ou hors fenêtre")
    else:
        f += [f"hook sans {x}" for x in HOTES_HOOKS if x not in plat[h[0] : h[1]]]
        f += [f"session sans {x}" for x in spec.get("session_hotes", HOTES_SESSION) if x not in plat[s[0] : s[1]]]
    f += [f"phrase neuve absente : {n}" for n in spec.get("neuves", ()) if n not in fenetre]
    f += [f"ancienne phrase présente : {a}" for a in spec.get("anciennes", ()) if a in plat]
    f += [f"hôte prétendu couvert : {m.group(0)}" for m in COUVERT.finditer(fenetre)]
    # `--reprise` n'apparaît que DEUX fois : le geste du pilote et son interdiction à l'agent, entre
    # l'option refusée et cette interdiction ; toute autre occurrence est une prescription.
    d, fin = plat.find(spec["requis"][7]), plat.find(spec["requis"][6]) + len(spec["requis"][6])
    occ = [m.start() for m in re.finditer(r"--reprise\b", plat)]
    if len(occ) != 2 or not all(0 <= d <= o < fin for o in occ):
        f.append(f"`--reprise` hors de la consigne : {len(occ)} occurrence(s) {occ}")
    return f


@pytest.mark.parametrize("rel", tuple(BORNE_H))
def test_lancement_borne_la_reprise(rel):
    assert fautes_h((ROOT / rel).read_text(encoding="utf-8"), BORNE_H[rel]) == []


def _mutants(texte: str, spec: dict) -> dict:
    plat = " ".join(texte.split())
    debut = plat.find(spec["ancre"])
    h = _segment(plat, spec["hooks"], debut)
    s = _segment(plat, spec["session"], h[1])
    m = {"reprise prescrite hors consigne": plat + " Sur ce refus, relance `tasks.py start T-NNN --reprise \"auto\"`.",
         "reprise prescrite dans la consigne": plat.replace(spec["requis"][6], "lance `--reprise`"),
         "reprise prescrite après la consigne": plat.replace(spec["requis"][6], spec["requis"][6] + " ; relance `--reprise`"),
         "reprise prescrite près de l'ancre": plat.replace(spec["ancre"], spec["ancre"] + " (relance `--reprise`)"),
         "Codex prétendu couvert": plat[: h[1]] + ")" + spec["couvert"] + plat[h[1] + 1 :]}
    for x in HOTES_HOOKS:
        m[f"hook sans {x}"] = plat[: h[0]] + plat[h[0] : h[1]].replace(x, "", 1) + plat[h[1] :]
    for x in spec.get("session_hotes", HOTES_SESSION):
        m[f"session sans {x}"] = plat[: s[0]] + plat[s[0] : s[1]].replace(x, "", 1) + plat[s[1] :]
    for n in spec.get("neuves", ()):
        m[f"phrase neuve retirée : {n}"] = plat.replace(n, "", 1)
    for a in spec.get("anciennes", ()):
        m[f"ancienne phrase remise : {a}"] = plat + " " + a + " : TTY + saisie."
    return m


@pytest.mark.parametrize("rel", tuple(BORNE_H))
def test_chaque_mutant_de_la_borne_rougit(rel):
    texte = (ROOT / rel).read_text(encoding="utf-8")
    mutants = _mutants(texte, BORNE_H[rel])
    assert len(mutants) == BORNE_H[rel].get("mutants", 12)
    verts = [nom for nom, mut in mutants.items() if mut == " ".join(texte.split()) or fautes_h(mut, BORNE_H[rel]) == []]
    assert verts == [], (rel, verts)
