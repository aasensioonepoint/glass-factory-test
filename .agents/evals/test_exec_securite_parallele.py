"""exec-critic ∥ security-code-review après chaque passe de dev (T-01M551RA0YFH2QD1CEM11AG8KD).

CE QU'IL JUGE : sur chaque surface qui décrit l'après-dev, (a) aucune phrase de la série d'avant ;
(b) l'atome « parallèle » ANCRÉ près d'un `exec-critic` ; (c) sur les surfaces de doctrine, l'atome
littéral « relance les deux » ; (d) la décision de charge citée là où la charge se règle ;
(e) la portée d'hôte du ∥ là où un autre hôte la lit ; (f) la borne de la correction de clôture ;
(g) les places restantes de C30, en anglais ou en français selon la langue de la surface ;
(h) sur les défs des hôtes non mesurés, « on this host: in series, exec-critic first » ;
(i) sur les défs exec-critic, chaque `NEXT: security-gate` glosé « never a second launch » ;
(j) sur kickoff ×2, les étapes de sécurité « (launched with exec-critic above) ».
Sur kickoff ×2, AGENTS.md, copilot-instructions et les orchestrateurs ×3, l'atome (b) est ANCRÉ au
bloc d'étape (BLOC) et la phrase C30 (EXCLU) ne compte pas.
(k) sur CHAQUE surface, aucun ordre série « exec-critic … puis/then/→/first … sécurité » qui ne soit
QUALIFIÉ (« one place ⇒ », « une place : », « in series, ») : les mots NEUFS d'un retour à la série
rougissent, pas seulement les phrases d'hier (exec-critic S-01M56THHVARBYT8ZGR33MG1TQY, mineur 1).
CE QU'IL NE PROUVE PAS : qu'un lanceur lance VRAIMENT les deux juges ensemble — prose, pas code ; un
ordre série dont les deux termes sont à plus de 60 caractères, ou sans marqueur d'ordre, n'est pas vu.
CHEZ L'ADOPTANT CE FILET SAUTE, alors que test_dev_avant_de_rendre y juge (une déf de dev réécrite
par l'adoptant est un défaut de l'adoptant, S-01M550PZ58QH3HQ4HNXGHJR7R1) : la règle diffère par
décision (S-01M56VW5K29XNEPA04C83RHGY0), l'aligner sur le jugement chez l'adoptant est hors de la vague 1.
Décisions pilote S-01M551RDK3PRT4VGTV5BN1ZM30 (point 3) et S-01M559V3Y1KNXD4JQJNQ735AJH (charge) ;
réserves C1-C8 du plan-critic S-01M55W93373973TSBR5WZ3GWYJ.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
KIT = (ROOT / ".agents" / "IS_THE_KIT").exists()
pytestmark = pytest.mark.skipif(not KIT, reason="hors du kit : surfaces réécrivables par l'adoptant (SAUT ANNONCÉ)")

CHG = "S-01M559V3Y1KNXD4JQJNQ735AJH"
SERIE1 = "JUGES UN À UN — une place : exec-critic, puis la sécurité"
DEUX = "relance les deux"
# T-01M5S9338BJP1B5RM3TG14AMYT : les défs (orchestrateurs, exec-critic) sont en anglais — leur atome
# est « relaunches both » ; les surfaces de doctrine en français gardent « relance les deux ». Un
# atome par surface, jamais « l'une ou l'autre langue » : la française dans une déf rougit.
DEUX_EN = "relaunches both"
_DEUX_SOUPLE = {DEUX: r"relance\s+les\s+deux", DEUX_EN: r"relaunches\s+both"}
# S-01M5VCGTEBC76MKR63HJ2K67CE (`.agents/ref/WORKING_LANGUAGE.md`) : un bloc clôturé d'une déf reste en
# français à l'octet. Les orchestrateurs Copilot et Codex ne portent l'atome QUE dans leur diagramme de
# chaîne, clôturé (Codex : rendu à l'octet de develop puis clôturé, correction finale de
# T-01M5S9338BJP1B5RM3TG14AMYT) : sur eux, l'atome est la forme française de ce bloc ; les autres défs le
# portent en prose.
DEUX_IMPRIME = frozenset({".github/agents/orchestrator.agent.md", ".codex/agents/orchestrator.toml"})


def deux(chemin: str) -> str:
    """L'atome « relance les deux » dans la langue de la surface : anglais dans la prose d'une déf,
    français dans un bloc clôturé qui seul le porte, français sur une surface de doctrine."""
    if chemin in DEUX_IMPRIME:
        return DEUX
    return DEUX_EN if "/agents/" in chemin else DEUX
PARALLELE = re.compile(r"∥|en parallèle|in parallel", re.IGNORECASE)
FENETRE = 200
HOTE = "elsewhere in series, exec-critic first"
BORNES = ("hors la correction de clôture", "the fix pass after the closing review is not such a pass",
          "not the fix pass after the closing review")
# C6 : les places que C30 laisse à la sécurité, dans la langue de la surface.
RESTES = {"en": "with the places left once exec-critic holds its own",
          "fr": "avec les places qui restent une fois qu'exec-critic tient la sienne"}
# C4 : la portée d'hôte écrite dans les défs des hôtes où le ∥ n'est pas mesuré.
ICI = "on this host: in series, exec-critic first"
# C1 : chaque `NEXT: security-gate` d'exec-critic rejoint le verdict déjà lancé.
NEXT = "next: security-gate"
GLOSE = "never a second launch"
# C8 : les étapes de sécurité de kickoff ×2 sont celles lancées avec exec-critic.
LANCE = "selected (launched with exec-critic above)"
# C30 (S-01M4Z1WA8GT6VED55AA9SEN6GT) : les étapes de SÉCURITÉ entre elles, jamais exec-critic ∥ sécurité.
EXCLU = ("(both read-only, in parallel",)
# (k) Un ordre série exec-critic → sécurité, dans une même proposition (ni « . » ni « ; » entre).
SERIE = re.compile(r"exec-critic[^.;]{0,60}?(?:\bthen\b|\bpuis\b|→|->|\bwaits?\b|\battend|\bbefore\b|\bavant\b|"
                   r"\bfirst\b|d'abord|\bpremier)[^.;]{0,60}?s[eé]cur")
# Les seules séries légitimes : une place au verdict de charge, ou l'hôte où le ∥ n'est pas mesuré.
QUALIFIE = ("one place ⇒", "une place :", "in series,", "en série,")
# Mutants à MOTS NEUFS (survivants de S-01M56THHV) : chacun, ajouté à n'importe quelle surface, rougit.
SERIES_NEUVES = ("exec-critic leaves first, and security-code-review waits for its GO",
                 "8. `exec-critic` → `security-code-review`", "1. **exec-critic, puis sécurité**",
                 "`exec-critic` puis securite →")
_ORCH_BLOC = "include `exec-critic` after dev-*"
BLOC = {".agents/skills/kickoff/SKILL.md": "invoke **exec-critic** (read-only)",
        ".claude/commands/kickoff.md": "invoke **exec-critic** (read-only)",
        "AGENTS.md": "(human approval) → `dev-*` → `exec-critic`",
        ".github/copilot-instructions.md": "8. `exec-critic`",
        ".claude/agents/orchestrator.md": _ORCH_BLOC,
        ".gemini/agents/orchestrator.md": _ORCH_BLOC,
        ".kimi-code/agents/orchestrator.md": _ORCH_BLOC}
# chemin -> (lot, doctrine ?, charge ?, série ?, hôte ?, borne ?, reste : None | "en" | "fr")
SURFACES = {
    "AGENTS.md": ("A", True, True, False, True, True, "fr"),
    ".agents/skills/kickoff/SKILL.md": ("A", True, True, True, True, True, "en"),
    ".claude/commands/kickoff.md": ("A", True, True, True, True, True, "en"),
    ".agents/skills/night/SKILL.md": ("B", True, True, False, False, True, "fr"),
    ".claude/commands/night.md": ("B", True, True, False, False, True, "fr"),
    ".github/copilot-instructions.md": ("B", True, True, False, True, True, None),
    "README-OTHER-HOSTS.md": ("B", False, False, False, True, True, None),
    "CADRE/index.html": ("B", False, False, False, False, False, None),
    ".claude/agents/orchestrator.md": ("C", True, True, False, False, True, "en"),
    ".gemini/agents/orchestrator.md": ("C", True, True, False, False, True, "en"),
    ".kimi-code/agents/orchestrator.md": ("C", True, True, False, False, True, "en"),
    ".codex/agents/orchestrator.toml": ("C", True, False, False, False, False, None),
    ".github/agents/orchestrator.agent.md": ("C", True, False, False, False, False, None),
    ".claude/agents/exec-critic.md": ("D", True, False, False, False, True, None),
    ".gemini/agents/exec-critic.md": ("D", True, False, False, False, True, None),
    ".kimi-code/agents/exec-critic.md": ("D", True, False, False, False, True, None),
    ".codex/agents/exec-critic.toml": ("D", True, False, False, False, True, None),
    ".github/agents/exec-critic.agent.md": ("D", True, False, False, False, True, None),
    "README.md": ("E", False, False, False, False, False, None),
    "README-CLAUDE.md": ("E", False, False, False, False, False, None),
    "docs/usage.html": ("E", False, False, False, False, False, None),
}
ICI_SURFACES = (".codex/agents/orchestrator.toml", ".gemini/agents/orchestrator.md", ".kimi-code/agents/orchestrator.md",
                ".github/agents/orchestrator.agent.md", ".codex/agents/exec-critic.toml", ".gemini/agents/exec-critic.md",
                ".kimi-code/agents/exec-critic.md", ".github/agents/exec-critic.agent.md")
LANCE_SURFACES = (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md")
_ORCH = ("include `exec-critic` after dev-* and BEFORE the security stage", "after `exec-critic`; skip",
         "exec-critic (EXÉCUTION) ──NO_GO──> dev", "`exec-critic` → securite →", "nothing reaches the security gate",
         "the chain holds as written — `exec-critic`, `security-code-review`",
         "`exec-critic`, `security-code-review` (MANDATORY")
_EC = ("runs after the dev agent and before the security gate", "reach the security gate on the strength")
ABSENT = {
    "AGENTS.md": ("`NO_GO` → retour au dev) → security gate", "restent `exec-critic`, `security-code-review`"),
    ".agents/skills/kickoff/SKILL.md": ("the security stages wait for its", "dev-* agent, then re-run security-code-review.",
                                        "exec-critic, security-code-review, the closing review",
                                        "then exec-critic after any dev pass (replays"),
    ".claude/commands/kickoff.md": ("the security stages wait for its", "`exec-critic` then `security-code-review`",
                                    "exec-critic, security-code-review, index rebuild",
                                    "dev-* agent, then re-run security-code-review."),
    ".agents/skills/night/SKILL.md": ("**Ordre d'après-dev strict** : sécurité (", "règle de charge de `/kickoff` :"),
    ".claude/commands/night.md": ("1. **sécurité** —", "règle de charge de `/kickoff` :"),
    ".github/copilot-instructions.md": ("returns the work to the dev agent — then `security-code-review`",
                                        "— `exec-critic`, `security-code-review`, the closing review"),
    "README-OTHER-HOSTS.md": ("6b. `exec-critic` replays every acceptance criterion with a real output; NO_GO returns to the dev. 7.",
                              "keeps `exec-critic`, the security gate"),
    "CADRE/index.html": ("avant la porte de sécurité",),
    ".claude/agents/orchestrator.md": _ORCH, ".gemini/agents/orchestrator.md": _ORCH, ".kimi-code/agents/orchestrator.md": _ORCH,
    ".codex/agents/orchestrator.toml": ("exec-critic (EXÉCUTION) ──NO_GO──> dev", "→ exec-critic → securite →",
                                        "(exec-critic; security-code-review, MANDATORY"),
    ".github/agents/orchestrator.agent.md": ("exec-critic (EXÉCUTION) ──NO_GO──> dev", "after the dev agent and before the security gate",
                                             "→ `exec-critic` → `security-code-review`", "→ `exec-critic` → securite →"),
    ".claude/agents/exec-critic.md": (*_EC, "Use after dev, before the security gate"),
    ".gemini/agents/exec-critic.md": (*_EC, "Use after dev, before the security gate"),
    ".kimi-code/agents/exec-critic.md": (*_EC, "Use after dev, before the security gate"),
    ".codex/agents/exec-critic.toml": _EC, ".github/agents/exec-critic.agent.md": _EC,
    "README.md": ("after dev and before the security gate",),
    "README-CLAUDE.md": ("after dev and before the security gate", "(NO_GO → back to dev) 5. Security gate:"),
    "docs/usage.html": ("exec-critic → security-code-review", "exec-critic puis security-code-review",
                        "Restent exec-critic, la revue de sécurité"),
}


def plier(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t)).strip().casefold()


def souple(atome: str) -> re.Pattern[str]:
    """L'atome tel qu'écrit, les blancs pouvant enjamber une fin de ligne (pour muter le texte RÉEL)."""
    return re.compile(r"\s+".join(re.escape(m) for m in atome.split()))


def ancre(plat: str, bloc: str | None) -> bool:
    """Un atome « parallèle » dans les FENETRE caractères qui suivent un `exec-critic` — ou, sur une
    surface à BLOC, qui suivent le bloc d'étape ; la phrase C30 (EXCLU) ne compte jamais."""
    for e in EXCLU:
        plat = plat.replace(plier(e), " ")
    if bloc is not None:
        i = plat.find(plier(bloc))
        return i >= 0 and bool(PARALLELE.search(plat[i + len(plier(bloc)):i + len(plier(bloc)) + FENETRE]))
    return any(PARALLELE.search(plat[m.end():m.end() + FENETRE]) for m in re.finditer("exec-critic", plat))


def series_nues(p: str) -> list[str]:
    """(k) Chaque ordre série exec-critic → sécurité de p (plié) qui n'est pas QUALIFIÉ juste avant."""
    nues = []
    for m in SERIE.finditer(p):
        avant = p[max(0, m.start() - 16):m.start()].rstrip("`*( ")
        if not avant.endswith(QUALIFIE):
            nues.append(m.group(0))
    return nues


def fautes(chemin: str, texte: str) -> list[str]:
    _, doctrine, charge, serie, hote, borne, reste = SURFACES[chemin]
    p = plier(texte)
    f = [f"{chemin} : phrase d'avant « {a} »" for a in ABSENT[chemin] if plier(a) in p]
    f += [f"{chemin} : ordre série non qualifié « {s} »" for s in series_nues(p)]
    if chemin in BLOC and p.count(plier(BLOC[chemin])) != 1:
        f.append(f"{chemin} : bloc d'étape « {BLOC[chemin]} » présent {p.count(plier(BLOC[chemin]))} fois (attendu 1)")
    if not ancre(p, BLOC.get(chemin)):
        f.append(f"{chemin} : aucun atome « parallèle » à {FENETRE} car. d'un exec-critic (ou du bloc d'étape)")
    if doctrine and plier(deux(chemin)) not in p:
        f.append(f"{chemin} : « {deux(chemin)} » absent")
    if charge and CHG.casefold() not in p:
        f.append(f"{chemin} : décision de charge {CHG} absente")
    if serie and plier(SERIE1) not in p:
        f.append(f"{chemin} : jeton de série « {SERIE1} » absent")
    if hote and plier(HOTE) not in p:
        f.append(f"{chemin} : portée d'hôte « {HOTE} » absente")
    if borne and not any(plier(b) in p for b in BORNES):
        f.append(f"{chemin} : borne de la correction de clôture absente")
    if reste is not None and plier(RESTES[reste]) not in p:
        f.append(f"{chemin} : places restantes « {RESTES[reste]} » absentes")
    if chemin in ICI_SURFACES and plier(ICI) not in p:
        f.append(f"{chemin} : portée d'hôte « {ICI} » absente")
    if chemin in LANCE_SURFACES and plier(LANCE) not in p:
        f.append(f"{chemin} : « {LANCE} » absent")
    if SURFACES[chemin][0] == "D":
        nexts = [m.end() for m in re.finditer(re.escape(NEXT), p)]
        if not nexts:
            f.append(f"{chemin} : aucun « {NEXT} » (jamais un vert vide)")
        f += [f"{chemin} : « {NEXT} » sans la glose « {GLOSE} »" for i in nexts if GLOSE not in p[i:i + 120]]
    return f


def lire(c: str) -> str:
    return (ROOT / c).read_text(encoding="utf-8")


def test_series_qualifiees_restent_vertes() -> None:
    """(k) Contrôle : les séries QUALIFIÉES de kickoff ×2 sont vues par SERIE, puis acceptées — un vert
    qui viendrait d'un SERIE aveugle ne prouverait rien."""
    for c in LANCE_SURFACES:
        p = plier(lire(c))
        assert len(SERIE.findall(p)) >= 2 and series_nues(p) == [], f"{c} : séries qualifiées non vues ou refusées"


def test_population() -> None:
    assert set(SURFACES) == set(ABSENT), "une surface sans témoin d'absence"
    manquants = [c for c in SURFACES if not (ROOT / c).is_file()]
    assert manquants == [], f"surfaces absentes (jamais un vert vide) : {manquants}"
    assert {v[0] for v in SURFACES.values()} == set("ABCDE")
    assert set(BLOC) <= set(SURFACES)
    assert set(ICI_SURFACES) <= set(SURFACES) and set(LANCE_SURFACES) <= set(SURFACES)


@pytest.mark.parametrize("chemin", list(SURFACES), ids=[f"lot{v[0]}-{c}" for c, v in SURFACES.items()])
def test_surface(chemin: str) -> None:
    f = fautes(chemin, lire(chemin))
    assert f == [], "\n".join(f)


@pytest.mark.parametrize("chemin", list(SURFACES), ids=[f"lot{v[0]}-{c}" for c, v in SURFACES.items()])
def test_mutants(chemin: str) -> None:
    texte = lire(chemin)
    assert fautes(chemin, texte) == [], "base rouge : les mutants ne prouveraient rien"
    muts = {f"absent-{k}": texte + "\n" + a + "\n" for k, a in enumerate(ABSENT[chemin])}
    # (k) Mots NEUFS d'un retour à la série, ajoutés seuls, puis collés au bloc d'étape.
    for k, s in enumerate(SERIES_NEUVES):
        muts[f"serie-neuve-{k}"] = texte + "\n" + s + "\n"
        if chemin in BLOC:
            i = texte.index(BLOC[chemin]) + len(BLOC[chemin])
            muts[f"bloc-serie-neuve-{k}"] = texte[:i] + " — " + s + "." + texte[i:]
    if SURFACES[chemin][3]:
        # la série légitime privée de son qualificatif « une place » doit rougir.
        muts["serie-sans-place"] = re.sub(r"one\s+place\s+⇒\s+(?=exec-critic\s+first)", "", texte)
    muts["sans-parallele"] = PARALLELE.sub("", texte)
    muts["detache"] = texte.replace("exec-critic", "exec-critic" + " x" * FENETRE)
    if SURFACES[chemin][1]:
        muts["sans-deux"] = re.sub(_DEUX_SOUPLE[deux(chemin)], "relance", texte)
        if deux(chemin) == DEUX_EN:
            # la forme française d'avant, remise à la place de l'anglaise, rougit une déf
            muts["deux-en-francais"] = re.sub(_DEUX_SOUPLE[DEUX_EN], DEUX, texte)
    if SURFACES[chemin][2]:
        muts["sans-charge"] = texte.replace(CHG, "S-0")
    if SURFACES[chemin][3]:
        muts["sans-serie"] = texte.replace("JUGES UN À UN", "JUGES")
    if SURFACES[chemin][4]:
        muts["sans-hote"] = texte.replace("elsewhere in series", "elsewhere")
    if SURFACES[chemin][5]:
        m = texte
        for b in BORNES:
            m = souple(b).sub("", m)
        muts["sans-borne"] = m
    if SURFACES[chemin][6] is not None:
        m = texte
        for r in RESTES.values():
            m = souple(r).sub("", m)
        muts["sans-reste"] = m
        # la forme de l'AUTRE langue ne remplace pas celle de la surface (C6).
        autre = "en" if SURFACES[chemin][6] == "fr" else "fr"
        muts["reste-autre-langue"] = souple(RESTES[SURFACES[chemin][6]]).sub(RESTES[autre], texte)
    if chemin in ICI_SURFACES:
        muts["sans-ici"] = souple(ICI).sub("on this host", texte)
    if chemin in LANCE_SURFACES:
        muts["sans-lance"] = texte.replace("(launched with exec-critic above)", "")
    if SURFACES[chemin][0] == "D":
        # UNE glose retirée suffit : chaque `NEXT: security-gate` porte la sienne.
        muts["sans-glose"] = texte.replace(GLOSE, "", 1)
    if chemin in BLOC:
        # l'étape redevient série, le reste (C30, « (5) … ∥ … ») intact : doit rougir.
        i = texte.index(BLOC[chemin]) + len(BLOC[chemin])
        muts["etape-serie"] = texte[:i] + PARALLELE.sub("", texte[i:i + 2 * FENETRE]) + texte[i + 2 * FENETRE:]
        muts["bloc-double"] = texte + "\n" + BLOC[chemin] + "\n"
    for nom, m in muts.items():
        assert m != texte, f"{chemin} : mutant {nom} non appliqué"
        assert fautes(chemin, m), f"{chemin} : mutant {nom} resté vert"
