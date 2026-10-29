"""TÉMOIN du lot K (T-01M53QXP2T6NK83WAEZHP77FN3, parent T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, décision pilote
S-01M4Z1WA8GT6VED55AA9SEN6GT) : kickoff et night lancent chaque vague sous le verdict de
`charge_poste.py`, et la porte de sécurité part avec un budget, même sur un poste de 4 cœurs (C30).

ZÉRO APPEL LLM, et l'outil n'est PAS importé (le lot T l'écrit en parallèle) : ce banc juge le TEXTE
prescrit — la commande du verdict ; `timeout: 600000` dans la MÊME phrase que chaque `--attendre`
(C33) ; le repli d'une sortie illisible `max(0, 5 − ACTIFS)` (C33, base à cinq de T-01M54B1SXM557Z86N1TXEJSRDE,
décision pilote S-01M54JH0M56AC36A97481DHG8P) ; le budget de la porte
`max(1, PEUT_AJOUTER − 2)` et son départ à C=4 (C30) ; le jeton COVERAGE DEGRADED de la V1 et le
plafond optionnel `A.max_devs` (C29) ; le qualificatif posé APRÈS les jetons gardés (C35) ; les
témoins d'absence des « ONE message » / « UN message » non qualifiés DANS LEUR PROPOSITION (A4, M7) ;
chaque site `--attendre` borné à trois attentes de suite à 0 puis en série, mot pour mot comme le lot P,
sous `COVERAGE DEGRADED — poste surchargé après trois attentes : <lancements> un à un`. Le départ de la porte se
calcule sur un MODÈLE de la règle A3 du premier verdict (ACTIFS=0, sans état), recopié ici.
Rouge sur la base 6687317e, vert après le lot K ; chaque règle a son mutant qui rougit.
Saute hors du kit, où kickoff et night peuvent être réécrits par l'adoptant. Ne juge PAS le reste de
kickoff ni de night, ni l'allowlist headless (test_night_headless_allowlist.py)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

KICKOFF = (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md")
NIGHT = (".agents/skills/night/SKILL.md", ".claude/commands/night.md")
SURFACES = KICKOFF + NIGHT

VERDICT = "bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>"
TIMEOUT = "timeout: 600000"
COVERAGE = ("COVERAGE DEGRADED — redescente active non livrée (V1) : à la surcharge, aucun départ ; "
            "les agents en vol finissent")
REPLI = re.compile(r"max\((\d+), (\d+) − ACTIFS\)")
BUDGET = re.compile(r"`budget = max\((\d+), PEUT_AJOUTER − (\d+)\)`")
SEUIL = re.compile(r"`PEUT_AJOUTER ≥ (\d+)` ⇒ both leave in ONE message")
UN_SEUL = "`PEUT_AJOUTER = 1` ⇒ security-code-review alone, then security-orchestrator at the next verdict"
NO_GO = ("at the THIRD verdict in a row returned at 0, the 1 min load exceeds 2C/3 or `PRESSION ≥ 2`",
         "never because `PLAFOND < 5`", "Overload after three waits is NEVER a GO")  # C1 + avis sécurité (S-01M545PF3V)
NO_GO_ANCIEN = "at that verdict, the 1 min load"
SEUL = re.compile(r"at the next verdict, ALONE, with `budget = max\((\d+), PEUT_AJOUTER − (\d+)\)` \(at 1, one over, SAID\)")
NUIT_JAMAIS_GO = "la surcharge après trois attentes n'est jamais un GO"
NUIT_APPLIQUE = "`timeout: 600000` de Bash, puis appliquer le verdict qu'elle rend"  # C7
PLAFOND_LANCEUR = ("`A.max_devs`", "min(`PEUT_AJOUTER`, ")
GARDES = {  # jeton gardé mot pour mot (C35) -> le qualificatif vient APRÈS, dans le même paragraphe
    ".agents/skills/kickoff/SKILL.md": "devs run in parallel, in git worktrees",
    ".claude/commands/kickoff.md": "Devs run in parallel, in git worktrees",
    ".agents/skills/night/SKILL.md": "6. Parallèle légitime",
    ".claude/commands/night.md": "6. **Parallèle légitime**",
}
ANCIENNES = {  # témoins d'absence : la vague non bornée de la base
    ".agents/skills/kickoff/SKILL.md": ("Code the devs leave in ONE message;",
                                        "(both read-only, run in parallel when both apply):"),
    ".claude/commands/kickoff.md": ("tous lancés en UN message", "(both read-only, in parallel):"),
}
NUIT_HORS_LISTE = ("charge_poste.py releve", "charge_poste.py reading", "charge_poste.py declare")  # SYM-11426 : jamais cités par night
MESSAGE = re.compile(r"\b(?:one|un|a single|un seul) message\b", re.IGNORECASE)
CLAUSE = re.compile(r"[;,:.](?= )|[()]")  # fin de proposition : le jeton se juge DANS la sienne, jamais dans la phrase
BORNE_APRES = re.compile(r" (?:of at most|d'au plus)\b")
CONDITION_AVANT = "`PEUT_AJOUTER ≥"
# borne mot pour mot du lot P (planning, planning-all) : trois attentes de suite à 0, puis série
BORNE_ATTENTES = re.compile(r"at\s+most\s+THREE\s+waits\s+in\s+a\s+row\s+returned\s+at\s+0"
                            r"|au\s+plus\s+TROIS\s+attentes\s+de\s+suite\s+rendues\s+à\s+0", re.IGNORECASE)
RELANCE = re.compile(r"wait again|attendre encore")
SERIE = "COVERAGE DEGRADED — poste surchargé après trois attentes : "
LANCEMENTS = {  # <lancements> du jeton de série, par surface (consigne du coordinateur)
    ".agents/skills/kickoff/SKILL.md": ("devs", "étapes de sécurité"),
    ".claude/commands/kickoff.md": ("devs", "étapes de sécurité"),
    ".agents/skills/night/SKILL.md": ("tâches",),
    ".claude/commands/night.md": ("tâches",),
}
ANCIEN_SERIE = "verdict de charge à 0 après 3 attentes"
FIN_PHRASE = re.compile(r"(?<=[.!?])\s+|\n[ \t]*\n|\n(?=[ \t]*(?:[-*] |\d+[a-z]*\. |#))")
FIN_PARAGRAPHE = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*] |\d+[a-z]*\. |#))")
DEUX = ("security-code-review", "security-orchestrator")


def aplatir(texte: str) -> str:
    """NFC, blancs pliés : une phrase coupée sur deux lignes compte."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", texte)).strip()


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def phrases(texte: str) -> list[str]:
    return [aplatir(p) for p in FIN_PHRASE.split(unicodedata.normalize("NFC", texte)) if p.strip()]


def attentes(texte: str) -> tuple[list[str], list[str]]:
    """(phrases qui citent `--attendre`, celles d'entre elles sans `timeout: 600000`)."""
    avec = [p for p in phrases(texte) if "--attendre" in p]
    return avec, [p for p in avec if TIMEOUT not in p]


def replis(texte: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in REPLI.findall(aplatir(texte))]


def repli(plancher: int, base: int, actifs: int) -> int:
    return max(plancher, base - actifs)


def premier_verdict(c: int, repos: bool = True) -> int:
    """PEUT_AJOUTER du premier verdict à ACTIFS=0 sans état (TENU = 0) — règle A3 recopiée, jamais lue dans
    l'outil (plan T-01M56Q23NHTEXES5CAT0A03TFJ, étape 1) : DUR = min(C, max(1, ⌊2C/3⌋)), PLAFOND = DUR ;
    BASE = max(min(5, PLAFOND), min(PLAFOND, ⌊C/2⌋)) au repos (charges 1 et 5 min < C/4), min(5, PLAFOND)
    ailleurs ; PEUT_AJOUTER = min(BASE, LIBRE) = BASE."""
    plafond = min(c, max(1, (2 * c) // 3))
    hors_repos = min(5, plafond)
    return max(hors_repos, min(plafond, c // 2)) if repos else hors_repos


def porte(texte: str, c: int, repos: bool = True) -> tuple[tuple[str, ...], int | None] | None:
    """Qui part à la porte de sécurité au premier verdict d'un poste à C cœurs, d'après le TEXTE."""
    plat = aplatir(texte)
    seuil, budget = SEUIL.search(plat), BUDGET.search(plat)
    if not (seuil and budget and UN_SEUL in plat):
        return None
    peut = premier_verdict(c, repos)
    if peut >= int(seuil.group(1)):
        return DEUX, max(int(budget.group(1)), peut - int(budget.group(2)))
    if peut == 1:
        return DEUX[:1], None
    return (), None


def budget_seul(texte: str, peut: int) -> int | None:
    """Budget de security-orchestrator parti SEUL au verdict suivant (C5), d'après le TEXTE."""
    m = SEUL.search(aplatir(texte))
    return max(int(m.group(1)), peut - int(m.group(2))) if m else None


def qualifie_apres(texte: str, jeton: str) -> bool:
    texte = unicodedata.normalize("NFC", texte)
    debut = texte.find(jeton)
    if debut == -1:
        return False
    reste = texte[debut + len(jeton):]
    fin = FIN_PARAGRAPHE.search(reste)
    paragraphe = aplatir(reste[:fin.start()] if fin else reste)
    return "charge_poste.py verdict" in paragraphe and "PEUT_AJOUTER" in paragraphe


def messages_non_qualifies(texte: str) -> list[str]:
    """Chaque « ONE/UN message » porte SA borne dans SA proposition : suivi de « of at most » / « d'au plus »
    avec `PEUT_AJOUTER`, ou précédé de la condition « `PEUT_AJOUTER ≥ n` ⇒ » (C30). Un « vague » ailleurs
    dans la phrase ne qualifie rien (mutant M7 de l'exec-critic)."""
    plat = aplatir(texte)
    fautes = []
    for m in MESSAGE.finditer(plat):
        debut = max((d.end() for d in CLAUSE.finditer(plat, 0, m.start())), default=0)
        fin = CLAUSE.search(plat, m.end())
        bout = fin.start() if fin else len(plat)
        apres, avant = plat[m.end():bout], plat[debut:m.start()]
        if not ((BORNE_APRES.match(apres) and "PEUT_AJOUTER" in apres) or CONDITION_AVANT in avant):
            fautes.append(plat[debut:bout].strip())
    return fautes


def bornes_attente(texte: str) -> tuple[int, list[str]]:
    """(nombre de bornes « trois attentes de suite à 0 », phrases qui relancent l'attente sans elle)."""
    n = len(BORNE_ATTENTES.findall(texte))
    return n, [p for p in phrases(texte) if RELANCE.search(p) and not BORNE_ATTENTES.search(p)]


# --- surfaces réelles --------------------------------------------------------------------------
@pytest.mark.parametrize("rel", SURFACES)
def test_chaque_vague_passe_par_le_verdict(rel):
    plat = aplatir(lire(rel))
    assert VERDICT in plat, f"{rel} : commande du verdict absente ({VERDICT})"
    assert COVERAGE in plat, f"{rel} : jeton COVERAGE DEGRADED de la V1 absent"


@pytest.mark.parametrize("rel", SURFACES)
def test_attendre_porte_son_timeout_dans_la_meme_phrase(rel):
    avec, sans = attentes(lire(rel))
    assert avec, f"{rel} : aucune phrase ne cite `--attendre`"
    assert sans == [], f"{rel} : `--attendre` sans `{TIMEOUT}` dans la même phrase :\n" + "\n".join(sans)


@pytest.mark.parametrize("rel", SURFACES)
def test_repli_illisible_cinq_moins_les_actifs(rel):
    trouves = replis(lire(rel))
    assert trouves, f"{rel} : repli `max(0, 5 − ACTIFS)` absent"
    assert set(trouves) == {(0, 5)}, f"{rel} : repli autre que max(0, 5 − ACTIFS) : {trouves}"


@pytest.mark.parametrize("rel", SURFACES)
def test_budget_de_la_porte_ecrit(rel):
    budgets = [(int(a), int(b)) for a, b in BUDGET.findall(aplatir(lire(rel)))]
    attendus = {(1, 2), (1, 1)} if rel in KICKOFF else {(1, 2)}
    assert budgets and set(budgets) == attendus, f"{rel} : budgets attendus {attendus}, lus {budgets}"


@pytest.mark.parametrize("rel", KICKOFF)
@pytest.mark.parametrize(("peut", "attendu"), [(1, 1), (2, 1), (3, 2)])
def test_orchestrateur_seul_au_verdict_suivant(rel, peut, attendu):
    assert budget_seul(lire(rel), peut) == attendu


@pytest.mark.parametrize("rel", NIGHT)
def test_night_applique_le_verdict_et_jamais_go(rel):
    plat = aplatir(lire(rel))
    assert [j for j in (NUIT_APPLIQUE, NUIT_JAMAIS_GO) if j not in plat] == []


@pytest.mark.parametrize("rel", KICKOFF)
@pytest.mark.parametrize(("c", "repos", "attendu"), [(4, True, (DEUX, 1)), (18, True, (DEUX, 7)),
                                                     (18, False, (DEUX, 3)), (1, True, (DEUX[:1], None))])
def test_la_porte_part_meme_a_quatre_coeurs(rel, c, repos, attendu):
    """Sur 18 cœurs au repos, PEUT_AJOUTER = 9 : les deux revues partent, budget 7 ; hors repos 5, budget 3."""
    assert porte(lire(rel), c, repos) == attendu


@pytest.mark.parametrize("rel", KICKOFF)
def test_no_go_de_charge_seulement_sur_surcharge(rel):
    plat = aplatir(lire(rel))
    assert [j for j in NO_GO if j not in plat] == []
    assert NO_GO_ANCIEN not in plat, f"{rel} : NO-GO jugé à « that verdict », pas au troisième 0 de suite (C1)"


@pytest.mark.parametrize("rel", KICKOFF)
def test_plafond_du_lanceur_optionnel(rel):
    plat = aplatir(lire(rel))
    assert [j for j in PLAFOND_LANCEUR if j not in plat] == []


@pytest.mark.parametrize("rel", SURFACES)
def test_qualificatif_apres_le_jeton_garde(rel):
    assert qualifie_apres(lire(rel), GARDES[rel]), f"{rel} : jeton {GARDES[rel]!r} absent ou non qualifié après"


@pytest.mark.parametrize("rel", SURFACES)
def test_aucun_message_unique_non_qualifie(rel):
    texte = lire(rel)
    assert messages_non_qualifies(texte) == []
    assert [a for a in ANCIENNES.get(rel, ()) if a in aplatir(texte)] == []


@pytest.mark.parametrize("rel", SURFACES)
def test_attente_bornee_puis_serie(rel):
    texte = lire(rel)
    n, sans = bornes_attente(texte)
    sites = len(attentes(texte)[0])
    assert n >= sites >= 1, f"{rel} : {n} borne(s) « trois attentes de suite » pour {sites} site(s) `--attendre`"
    assert sans == [], f"{rel} : attente relancée sans borne :\n" + "\n".join(sans)
    plat = aplatir(texte)
    manquants = [x for x in LANCEMENTS[rel] if f"{SERIE}{x} un à un" not in plat]
    assert manquants == [], f"{rel} : jeton de série absent pour {manquants}"
    assert ANCIEN_SERIE not in plat, f"{rel} : ancien jeton de série encore présent"


@pytest.mark.parametrize("rel", SURFACES)
def test_mutant_borne_retiree_dans_la_surface_rougit(rel):
    mutant = BORNE_ATTENTES.sub("", lire(rel), count=1)
    assert bornes_attente(mutant)[0] < len(attentes(mutant)[0])


@pytest.mark.parametrize("rel", SURFACES)
def test_mutant_m7_dans_la_surface_rougit(rel):
    texte = lire(rel)
    m = re.search(r"\b(?:wave|vague)\b", texte)
    assert m, f"{rel} : ni « wave » ni « vague »"
    assert messages_non_qualifies(texte[:m.end()] + " tout part en UN message." + texte[m.end():]) != []


@pytest.mark.parametrize("rel", NIGHT)
def test_night_ne_cite_que_le_verbe_verdict(rel):
    assert [j for j in NUIT_HORS_LISTE if j in lire(rel)] == []


# --- mutants : chaque règle peut rougir ---------------------------------------------------------
def test_modele_a3_du_premier_verdict():
    assert [premier_verdict(c) for c in (1, 2, 3, 4, 18)] == [1, 1, 2, 2, 9]          # au repos : 9 sur 18
    assert [premier_verdict(c, repos=False) for c in (1, 2, 3, 4, 18)] == [1, 1, 2, 2, 5]


def test_mutant_timeout_dans_la_phrase_suivante_rougit():
    assert attentes("Wait with `x --attendre 540`. Then `timeout: 600000`.")[1] != []
    assert attentes("Wait with `x --attendre 540` under `timeout: 600000`.")[1] == []


def test_mutant_repli_rougit():
    assert set(replis("x `max(0, 4 − ACTIFS)` y")) != {(0, 5)}
    assert set(replis("x `max(0, 3 − ACTIFS)` y")) != {(0, 5)}  # l'ancienne base resemée rougit
    assert [repli(0, 5, a) for a in (0, 3, 5)] == [5, 2, 0]


PORTE_OK = ("`PEUT_AJOUTER ≥ 2` ⇒ both leave in ONE message and `budget = max(1, PEUT_AJOUTER − 2)` ; "
            f"{UN_SEUL}.")


@pytest.mark.parametrize("mutant", [
    PORTE_OK.replace("max(1,", "max(0,"),
    PORTE_OK.replace("≥ 2`", "≥ 3`"),
    PORTE_OK.replace("− 2)", "− 1)"),
    PORTE_OK.replace(UN_SEUL, ""),
])
def test_mutant_porte_rougit(mutant):
    attendus = [porte(PORTE_OK, c) for c in (1, 4, 18)]
    assert attendus == [(DEUX[:1], None), (DEUX, 1), (DEUX, 7)]
    assert [porte(mutant, c) for c in (1, 4, 18)] != attendus


SEUL_OK = "at the next verdict, ALONE, with `budget = max(1, PEUT_AJOUTER − 1)` (at 1, one over, SAID)"


@pytest.mark.parametrize("mutant", [SEUL_OK.replace("max(1,", "max(0,"), SEUL_OK.replace("− 1)`", "− 2)`"),
                                    SEUL_OK.replace("ALONE, ", "")])
def test_mutant_orchestrateur_seul_rougit(mutant):
    attendus = [budget_seul(SEUL_OK, p) for p in (1, 2, 3)]
    assert attendus == [1, 1, 2]
    assert [budget_seul(mutant, p) for p in (1, 2, 3)] != attendus


def test_mutant_qualificatif_avant_ou_absent_rougit():
    jeton = "devs run in parallel, in git worktrees"
    assert qualifie_apres(f"{jeton}, by waves of `PEUT_AJOUTER` (`charge_poste.py verdict`).", jeton)
    assert not qualifie_apres(f"`PEUT_AJOUTER` (`charge_poste.py verdict`).\n\n{jeton}, as soon as.", jeton)
    assert not qualifie_apres("by waves of `PEUT_AJOUTER` (`charge_poste.py verdict`).", jeton)


def test_mutant_message_unique_non_qualifie_rougit():
    assert messages_non_qualifies("On Claude Code the devs leave in ONE message.") != []
    assert messages_non_qualifies("Each wave leaves in ONE message of at most `PEUT_AJOUTER`.") == []
    assert messages_non_qualifies("`PEUT_AJOUTER ≥ 2` ⇒ both leave in ONE message, and more.") == []
    # M7 : « vague » dans la phrase ne qualifie pas un « UN message » nu
    assert messages_non_qualifies("Avant CHAQUE vague tout part en UN message.") != []
    assert messages_non_qualifies("une vague part en UN message d'au plus son `PEUT_AJOUTER`, tout part en UN message.") != []
    assert messages_non_qualifies("tout part en UN message d'au plus trois.") != []


def test_mutant_attente_sans_borne_rougit():
    assert bornes_attente("still 0 ⇒ wait again.")[1] != []
    assert bornes_attente("still 0 ⇒ wait again. At most THREE waits in a row returned at 0.")[1] != []
    assert bornes_attente("still 0 ⇒ wait again, at most THREE waits in a row returned at 0.") == (1, [])
    assert bornes_attente("au plus CINQ attentes de suite rendues à 0.")[0] == 0
    assert bornes_attente("au plus TROIS attentes de suite\n   rendues à 0.")[0] == 1
