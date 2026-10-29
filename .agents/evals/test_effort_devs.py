"""Effort des trois devs, asymétrique par hôte (T-01M5EN6SZBDKXB5KNNYRWJMAC9).

Décision pilote S-01M5F3KT36B9S58WNC6T92E0BM : `medium` sur Claude Code SEUL ;
Codex reste `high` ; la déf Copilot de frontend-fidelity n'épingle aucun effort
et garde « the strongest available tier ». Décision pilote S-01M5N24P2Y0SH6S0W0YNG3TAN6 :
frontend-fidelity revient à `high` sur Claude Code, dev-mono et dev-multi restent
`medium`. Valeurs en LITTÉRAL (L-00000261)."""
from pathlib import Path
import re
import sys
import tomllib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import EST_LE_KIT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEC = "S-01M5F3KT36B9S58WNC6T92E0BM"
DEC_ECRAN = "S-01M5N24P2Y0SH6S0W0YNG3TAN6"
DEVS = ("dev-mono", "dev-multi", "frontend-fidelity")
#: Effort Claude Code attendu par dev (défaut, puis expert) : frontend-fidelity revenu à `high`.
CLAUDE_ATTENDU = {"dev-mono": ("medium", "high"), "dev-multi": ("medium", "high"),
                  "frontend-fidelity": ("high", "xhigh")}
JUGE = {"dev-mono": "exec-critic", "dev-multi": "exec-critic", "frontend-fidelity": "design-review"}
RANG = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
COPILOT_FF = "This host pins no model or effort field — run at the strongest available tier"
BUDGETS_DISQUE = "is still `opus`/`medium` on disk"
SAUT_ADOPTANT = "SAUT ANNONCE : projet adoptant, efforts a ses risques (S-01M54WXT38HZ52GCMQSQ44CB5F)"


def lire(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def effort_claude(texte):
    return re.search(r"^effort:\s*(\S+)", texte.split("---", 2)[1], re.M).group(1)


def effort_codex(texte):
    return tomllib.loads(texte)["model_reasoning_effort"]


def grille(texte):
    return {(h, a): (d, e) for h, a, d, e in re.findall(
        r"^\| `(claude|codex)` \| `([\w-]+)` \| effort \| `(\w+)` \| `(\w+)` \|$", texte, re.M)}


def defs_ok(claude, codex):
    fautes = []
    for dev in DEVS:
        if effort_claude(claude[dev]) != CLAUDE_ATTENDU[dev][0]:
            fautes.append(f"claude {dev} != {CLAUDE_ATTENDU[dev][0]}")
        if effort_codex(codex[dev]) != "high":
            fautes.append(f"codex {dev} != high")
        if RANG[effort_claude(claude[JUGE[dev]])] <= RANG[effort_claude(claude[dev])]:
            fautes.append(f"claude {JUGE[dev]} pas au-dessus de {dev}")
        if RANG[effort_codex(codex[JUGE[dev]])] <= RANG[effort_codex(codex[dev])]:
            fautes.append(f"codex {JUGE[dev]} pas au-dessus de {dev}")
    return fautes


def textes_ok(g, agents, copilot, budgets):
    fautes = []
    for dev in DEVS:
        if g.get(("claude", dev)) != CLAUDE_ATTENDU[dev]:
            fautes.append(f"grille claude {dev}")
        if g.get(("codex", dev)) != ("high", "xhigh"):
            fautes.append(f"grille codex {dev}")
    # Ancres suivies (T-01M5PCCHMWXTRCM5QJT8J5KNEH) : la première exception nommée est
    # retirée d'AGENTS.md § Full power, celle-ci devient « A named », la suivante « Another ».
    i = agents.index("(A named exception")
    fen = agents[i:agents.index("(Another, pilot S-01M57F0BHB", i)].replace("**", "")
    for besoin in (DEC, "Claude Code only", "`dev-mono` and `dev-multi` run at `medium`",
                   f"`frontend-fidelity` back at `high`, {DEC_ECRAN}", "keep `high` on Codex", "not a precedent"):
        if besoin not in fen:
            fautes.append(f"AGENTS fenetre sans {besoin!r}")
    if COPILOT_FF not in copilot or re.search(r"^effort:", copilot, re.M):
        fautes.append("copilot frontend-fidelity a change")
    if budgets.count(BUDGETS_DISQUE) != 1:
        fautes.append("TOKEN_BUDGETS : effort sur disque de dev-mono")
    return fautes


def charger():
    noms = DEVS + ("exec-critic", "design-review")
    claude = {a: lire(f".claude/agents/{a}.md") for a in noms}
    codex = {a: lire(f".codex/agents/{a}.toml") for a in noms}
    return (claude, codex, grille(lire(".agents/ref/MODEL_MODES.md")), lire("AGENTS.md"),
            lire(".github/agents/frontend-fidelity.agent.md"), lire(".agents/ref/TOKEN_BUDGETS.md"))


def mode_pose():
    # adopting-tree: l'etat local du mode n'existe que chez qui l'a pose ; absent, les defs valent la colonne defaut
    return (ROOT / ".agents" / "state" / "local" / "MODEL_MODE").is_file()


def _mute(texte, old, new):
    assert texte.count(old) == 1, old
    return texte.replace(old, new)


@pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)
def test_textes_efforts_par_hote():
    _, _, g, agents, copilot, budgets = charger()
    assert textes_ok(g, agents, copilot, budgets) == []


@pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)
def test_defs_efforts_par_hote():
    if mode_pose():
        pytest.skip("SAUT ANNONCE : MODEL_MODE pose, les defs suivent le mode")
    claude, codex, *_ = charger()
    assert defs_ok(claude, codex) == []


@pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)
def test_mutants_defs_rougissent():
    if mode_pose():
        pytest.skip("SAUT ANNONCE : MODEL_MODE pose, les defs suivent le mode")
    claude, codex, *_ = charger()
    for hote, agent, old, new in (
        ("claude", "dev-mono", "\neffort: medium\n", "\neffort: high\n"),
        ("claude", "frontend-fidelity", "\neffort: high\n", "\neffort: medium\n"),
        ("codex", "dev-multi", 'model_reasoning_effort = "high"', 'model_reasoning_effort = "medium"'),
        ("claude", "design-review", "\neffort: xhigh\n", "\neffort: medium\n"),
        ("codex", "exec-critic", 'model_reasoning_effort = "xhigh"', 'model_reasoning_effort = "high"'),
    ):
        c, x = dict(claude), dict(codex)
        cible = c if hote == "claude" else x
        cible[agent] = _mute(cible[agent], old, new)
        assert defs_ok(c, x), (hote, agent)


@pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)
def test_mutants_textes_rougissent():
    _, _, g, agents, copilot, budgets = charger()
    g1 = dict(g); g1[("claude", "frontend-fidelity")] = ("medium", "high")
    g2 = dict(g); g2[("codex", "dev-mono")] = ("medium", "high")
    g3 = dict(g); g3[("claude", "dev-multi")] = ("high", "xhigh")
    assert all(textes_ok(x, agents, copilot, budgets) for x in (g1, g2, g3))
    for old, new in (
        ("`dev-mono` and `dev-multi` run at `medium`", "`dev-mono`, `dev-multi` and `frontend-fidelity` run at `medium`"),
        ("`dev-mono` and `dev-multi`", "`dev-mono`"),
        ("`frontend-fidelity` back at `high`", "`frontend-fidelity` back at `medium`"),
        (f"back at `high`, {DEC_ECRAN}", "back at `high`"),
        ("keep `high` on Codex", "keep `medium` on Codex"),
        ("It is **not a precedent**: it authorises no other lowered effort.", ""),
        ("S-01M5F3KT36B9S58WNC6T92E0BM, Claude Code only:", "S-01M5F3KT36B9S58WNC6T92E0BM:"),
    ):
        assert textes_ok(g, _mute(agents, old, new), copilot, budgets), old
    assert textes_ok(g, agents, _mute(copilot, "run at the strongest available tier", "take `medium`"), budgets)
    assert textes_ok(g, agents, copilot, _mute(budgets, BUDGETS_DISQUE, "is still `opus`/`high` on disk"))


# Trois cas relogés depuis le banc de la route locale retirée (T-01M5PCCHMWXTRCM5QJT8J5KNEH,
# C16, C-r2) : SANS skipif, ils voyagent comme avant — AGENTS.md et copilot-instructions.md
# voyagent. S-01M57F0BHB : l'effort abaissé de la planification est une exception nommée à la
# règle, près d'elle : fenêtre de 1 400 caractères depuis que la mesure S-01M57Q5ZK y est
# chiffrée (n=1, high 2 bloquants de référence / max 4, planner medium non mesuré).
_EXCEPTION_PLANIF = re.compile(
    r"\(Another, pilot S-01M57F0BHB: `plan-critic` at `high`, `planner` at `medium`,"
    r" for speed, never cost;[^)]*S-01M57Q5ZK[^)]*n=1[^)]*`high` finds 2 reference blockers"
    r" where `max` finds 4, `planner` at `medium` unmeasured;[^)]*not a precedent\.\)"
)
_FENETRE_PLANIF = 1400


def _exception_planif_nommee(texte):
    i = texte.index("Never downgrade a model")
    return _EXCEPTION_PLANIF.search(texte[i:i + _FENETRE_PLANIF]) is not None


def test_exception_effort_planification_nommee():
    """L'effort abaissé de `planner` et `plan-critic` (vitesse, jamais coût)
    est écrit près de la règle qu'il amende ; retiré, le témoin rougit."""
    texte = lire("AGENTS.md")
    assert _exception_planif_nommee(texte), "AGENTS.md § Full power : exception S-01M57F0BHB absente de la fenêtre"
    sans = _EXCEPTION_PLANIF.sub("", texte)
    assert sans != texte, "mutant vide"
    assert not _exception_planif_nommee(sans), "le prédicat ne mord pas sur l'exception retirée"


def test_mesure_planification_chiffree():
    """« quality measured » sans le résultat se lirait « qualité égale » : le
    chiffre (n=1, 2 contre 4, planner non mesuré) est exigé ; ôté, rouge."""
    texte = lire("AGENTS.md")
    vieux = ("measured once, S-01M57Q5ZK on the T-01M55W6GZ6 r1 benchmark, n=1: `high` finds 2 reference"
             " blockers where `max` finds 4, `planner` at `medium` unmeasured;")
    assert texte.count(vieux) == 1, "mesure chiffrée absente ou doublée"
    vague = texte.replace(vieux, "quality measured S-01M57Q5ZK;")
    assert not _exception_planif_nommee(vague), "mutant SURVIVANT : mesure sans résultat"


def test_advisor_interdit_a_la_session_comme_aux_defs():
    """S-01M57FKBYM : l'outil advisor sort totalement, session principale comprise."""
    regle = "**The `advisor` tool is never called**, by any session or def on any host,"
    assert lire("AGENTS.md").count(regle) == 1
    copilot = lire(".github/copilot-instructions.md")
    assert "the `advisor` tool only on the pilot's explicit request (S-01M57FKBYM)" in copilot
