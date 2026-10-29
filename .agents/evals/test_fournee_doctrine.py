"""Témoin de T-01M4V1JD628K07PXF7FFDSN0Q3 : le parallélisme automatique, la DOCTRINE.

Décision pilote S-01M4V1K1DG9WY2WKWKWN7ZGFC7 : l'approbation du plan lance la
fournée (`tasks.py fournee <T>`), le planner découpe PAR DÉFAUT en lots, et les
commandes de préparation n'en lancent jamais. Ce banc tient l'Annexe T du plan,
ENTIÈRE, sur toutes ses surfaces — un cas par surface, un mutant par hôte :

(a) planner x5 : `LOT:`, `INTÉGRATION:`, `plan_lots.py check`, `from <N + 1> files on` (les défs
    sont en anglais depuis T-01M5S9338BJP1B5RM3TG14AMYT ; l'ancienne forme `dès <N + 1> fichiers`
    ne satisfait plus le jeton — contrôle synthétique dédié).
(b) plan-critic x5 : `plan_lots.py check`, `recouvrement`, `INTÉGRATION:`.
(c) orchestrator x5 : `tasks.py fournee`, le pointeur `.agents/ref/PARALLELISME_HOTES.md`, et la
    ligne de statut de chaque hôte, DÉRIVÉE de la table, (i).
(d) kickoff x2, AGENTS.md, copilot-instructions : `tasks.py fournee`.
(e) planning SKILL, planning-all SKILL, `planning.md`, `planning-all.md` : `fournee`
    DANS LES INTERDITS — lu dans la tranche des interdits de chaque surface (deux
    ancres fermées par surface, celle de début UNIQUE), jamais n'importe où dans le
    fichier : un `fournee` déplacé hors de la tranche rougit.
(f) « Tout seuil chiffré suit la règle W24 » : chaque surface est passée à la règle
    de `test_direct_mode_doctrine.py` — sa famille de motifs et sa constante
    `MAX_FICHIERS_DIRECT`, IMPORTÉES et jamais recopiées (L-00000057) — élargie de
    deux formes de la découpe, `dès N fichiers` et `N fichiers au plus` (et
    `N files at most`). Le jeton de (a) n'est pas écrit en dur : il est DÉRIVÉ de la
    constante, si bien qu'une constante qui bouge fait rougir la phrase qui ne
    suit pas.
(g) AJOUT hors Annexe T, dit : la task-board SKILL porte « le porteur de fournée est
    membre du groupe » (étape 7 du plan, lot D1) — `tasks.py fournee` à moins de
    FENETRE caractères de `membre du groupe`. Sans ce cas, rien ne tiendrait la
    phrase.
(h) AJOUT de T-01M4VX9GRQ82YMJHS37XTW6VAY : la fournée dégénérée (`LOTS: aucun`)
    garde le write-set DÉCLARÉ, posé par `tasks.py writeset` AVANT la fournée,
    sinon elle refuse. Branché sur trois surfaces DÉJÀ listées (kickoff_skill,
    kickoff_cmd, task_board_skill), par leur identifiant, dans `violations()` —
    aucune ligne `Surface` de plus : l'ancre (`degenerate` en anglais,
    `dégénérée` en français) porte `tasks.py writeset` à moins de FENETRE
    caractères. Sur les mêmes trois surfaces, le remède du parent dégénéré
    qui TOURNE déjà réduit à son plan (refus du lot A, 78298b1e) finit par la
    relance qui « redéclare le groupe » (`re-declares the group`), JAMAIS par
    « puis `parallel` » (`then `parallel``) : lu dans la tranche « TOURNE
    déjà » … « PIÈGE : » (« ALREADY running » … « TRAP: »), début UNIQUE.
(i) AJOUT de T-01M4VBZFB6KWTW22618C0VWB13 (lot O) : le statut de parallélisme des devs
    PAR HÔTE vient de la table `.agents/ref/PARALLELISME_HOTES.md` (lignes `HOTE:`,
    statut comparé à l'ÉGALITÉ EXACTE au vocabulaire fermé — `non-mesure` refusé,
    un préfixe ne passe pas), jamais d'une phrase recopiée ici. Chaque hôte exige SA
    ligne dans les défs qui la portent (`HOTES_TABLE` : la sienne, plus claude et
    kimi, miroirs l'un de l'autre ; antigravity -> déf gemini ; kimi -> défs claude
    et kimi) : N `… non mesuré sur <X>[ (<cause fermée>, <date>)] : lots joués en
    série`, S `… mesuré en série sur <X> : …`, P `**<X>** — PARALLÈLE MESURÉ (<date>`
    (claude : sa puce MEASURED) ; et une ligne d'une AUTRE famille pour ce même hôte
    y rougit — une déf qui garde « non mesuré » après un P à la table est vue.
    Table ABSENTE (fichier ni lien) : le contrat d'avant, fail-closed — `COVERAGE
    DEGRADED — parallélisme des devs non mesuré` exigé sur les cinq défs. Table
    présente mais illisible, incomplète ou en double : ROUGE, jamais un repli.
    TÉMOIN : la table de la nuit (Annexe D du plan, `TABLE_NUIT`) juge les défs
    RÉELLES tant que la vraie table est absente — c'est elle qui prouve, avant la
    fusion du lot qui écrit la table, que la branche « présente » mord ; dès que la
    vraie table existe, elle la remplace (jamais périmée par un statut qui bouge).
(j) AJOUT du lot O de T-01M4XZWZ9C0ZFVXN3MFSFY1G5V (décision pilote S-01M4Y10HZ6Y0TAXNNK0S1VRFC1) :
    les surfaces de O SEULES (PIÈGE 1 du plan : défs orchestrator x5, task-board SKILL,
    GEMINI.md, la table des hôtes) lancent par VAGUES d'au plus le `PEUT_AJOUTER` de
    `charge_poste.py verdict`. Chaque passage ouvre sur le jeton d'A1 GARDÉ mot pour mot (C35 :
    CLAUDE_P compris) et porte son qualificatif APRÈS lui, jamais à sa place ; témoins d'absence
    (C32 : « as wide as independence allows » ; les phrases d'avant de chaque surface) ; et chaque
    « ONE message », « UN seul message », « MAXIMAL fan-out », « in parallel with » d'une surface de O
    porte `PEUT_AJOUTER` dans les FENETRE_O caractères qui le suivent (non qualifié : rouge), FENETRE_O
    épinglée par des écarts écrits en dur. Passe exec-critic : la porte de sécurité des défs (C30) —
    en parallèle au `PEUT_AJOUTER` ≥ 2 quand les deux s'appliquent, en série à 1.

Mutants, sur le texte RÉEL, base verte d'abord ; une mutation sans effet est un
échec, jamais un vert (L-00000161) : chaque jeton retiré de chaque surface (donc de
chaque hôte, pour les défs) ; `fournee` retiré de la tranche des interdits, puis
retiré ET recopié en fin de fichier ; le premier seuil capturé passé à 4 ; la
constante abaissée d'un cran ; pour (h), sur chacune des trois surfaces,
`tasks.py writeset` éloigné de l'ancre, puis l'ancre retirée, puis « puis
`parallel` » réintroduit dans le remède, puis la relance qui redéclare le
groupe retirée ; pour (i), sur les défs RÉELLES : le jeton du contrat d'avant retiré
(table absente), chaque ligne de statut du témoin retirée, chaque hôte basculé vers
chacun des quatre autres statuts, la date du statut changée là où la ligne la porte,
une ligne d'une autre famille ajoutée pour le même hôte. Contrôles
synthétiques de la règle, sans aucune surface lue. Non-vacuité : 24 surfaces
distinctes, lues, non vides ; chaque rôle a au moins un jeton ; chaque surface des
interdits a sa paire d'ancres ; chaque porteuse du seuil en capture au moins un ;
les trois surfaces de (h) sont listées.
(k) AJOUT du lot G de T-01M5DBFPWCXH54VW0VMN8HWRX7 : plusieurs `running`, une session par clone, et
    `tasks.py review-scope` lu dans la tranche de CHAQUE site de critique de clôture des deux kickoff
    (cadrage, gabarit PIPELINE étape 10, matin, R3, clôture, livraison, directe), plus AGENTS.md § Task
    tracking et l'invariant de la task-board SKILL, avec l'ORDRE « déclarer puis lancer » (l'appel suivi
    de « just before … critic ») ; le contrat d'avant (rétrogradation, groupe unique) absent ; la tranche
    « ALREADY running » … « TRAP: » gardée (C18). Mutants : l'appel retiré d'un site, l'ordre renversé
    (« just after », « once the critic has returned »), le contrat d'avant réinjecté, l'ancre doublée.

EN ATTENTE DE FUSION, PAR CONSTRUCTION. (a), (b) et (c) lisent les défs que les lots
J1 et J2 écrivent EN PARALLÈLE du lot D1 qui crée ce banc : leurs cas rougissent
dans le worktree de D1 seul, et le banc complet ne se joue qu'après la fusion
(plan, section « Lots »). Les identifiants de cas sont choisis pour que
`-k "kickoff or skill or agents_md or copilot or planning"` ne sélectionne QUE
les surfaces des lots D1 et D2 (49 cas, les six de (h) compris) : hôte Copilot
des défs nommé `github`.
MESURÉ (pytest 9.1) : `-k` compare aussi les noms des DOSSIERS parents, et
`.agents/` porte « agents » — le filtre écrit avec `agents` nu sélectionne le
fichier entier, défs comprises ; d'où `agents_md`.

BORNES, dites plutôt que découvertes (L-00000187) : ce banc lit l'arbre de travail,
pas HEAD ; il épingle des JETONS, pas le sens — un interdit réécrit en permission
DANS la tranche passe, une phrase de seuil hors de la famille élargie n'est pas
vue ; (d) cherche le jeton dans le fichier entier ; (g) et (h) jugent un
voisinage — (h) ne voit ni l'ordre « writeset AVANT fournee » ni le refus écrit ;
son remède du parent réduit juge deux JETONS dans une tranche : un `parallel`
écrit autrement (« et `parallel` », « `tasks.py parallel` ») y passe. (i) lit de
la table l'hôte, le statut et la date SEULS — les autres colonnes (os-arch, version,
cause recopiée, chiffres d'un P) relèvent de `test_parallelisme_hotes.py` ; il ne
voit pas la ligne d'un hôte écrite dans une déf hors de `HOTES_TABLE` (une déf
gemini qui nommerait Codex), ni la ligne générique `sur <hôte>` d'un hôte que la
table ne liste pas ; et une ligne de grammaire `HOTE: <…>` est sautée, si bien
qu'une ligne d'hôte dont le nom ouvre par `<` l'est aussi — l'hôte manque alors, rouge.
(j) tient les passages NOMMÉS et quatre jetons nus, pas toute phrase de parallélisme des huit
fichiers (« in parallel » sans « with » n'est pas lu) ; « qualifié » veut dire `PEUT_AJOUTER` dans la
fenêtre qui suit, pas une phrase juste ; il ne prouve pas qu'un lanceur appelle le verdict avant
chaque vague (ACTIFS reste déclaratif : la règle empêche d'OUBLIER, pas de TRICHER).
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# La règle W24, importée de son banc — un seul porteur de la famille de motifs.
_SPEC_W24 = importlib.util.spec_from_file_location(
    "_regle_w24_fournee", Path(__file__).resolve().parent / "test_direct_mode_doctrine.py"
)
w24 = importlib.util.module_from_spec(_SPEC_W24)
sys.modules[_SPEC_W24.name] = w24  # `@dataclass` relit son module dans sys.modules
_SPEC_W24.loader.exec_module(w24)

DECISION = "S-01M4V1K1DG9WY2WKWKWN7ZGFC7"
FENETRE = 200

HOTES = (
    ("claude", ".claude/agents", ".md"),
    ("codex", ".codex/agents", ".toml"),
    ("gemini", ".gemini/agents", ".md"),
    ("github", ".github/agents", ".agent.md"),
    ("kimi", ".kimi-code/agents", ".md"),
)


@dataclass(frozen=True)
class Surface:
    ident: str
    chemin: str
    role: str


def _defs(nom: str, role: str) -> tuple[Surface, ...]:
    return tuple(Surface(f"{role}-{hote}", f"{dossier}/{nom}{ext}", role) for hote, dossier, ext in HOTES)


SURFACES: tuple[Surface, ...] = (
    *_defs("planner", "planner"),
    *_defs("plan-critic", "plan_critic"),
    *_defs("orchestrator", "orchestrator"),
    Surface("kickoff_cmd", ".claude/commands/kickoff.md", "annonce"),
    Surface("kickoff_skill", ".agents/skills/kickoff/SKILL.md", "annonce"),
    Surface("agents_md", "AGENTS.md", "annonce"),
    Surface("copilot_instructions", ".github/copilot-instructions.md", "annonce"),
    Surface("planning_skill", ".agents/skills/planning/SKILL.md", "interdit"),
    Surface("planning_all_skill", ".agents/skills/planning-all/SKILL.md", "interdit"),
    Surface("planning_cmd", ".claude/commands/planning.md", "interdit"),
    Surface("planning_all_cmd", ".claude/commands/planning-all.md", "interdit"),
    Surface("task_board_skill", ".agents/skills/task-board/SKILL.md", "porteur"),
)
PAR_IDENT = {s.ident: s for s in SURFACES}

# La tranche des interdits de chaque surface (e) : début UNIQUE, fin la première après.
INTERDITS: dict[str, tuple[str, str]] = {
    "planning_skill": ("- Interdits :", "- Un plan prêt"),
    "planning_all_skill": ("## Ce qu'il n'écrit JAMAIS", "**`planning-all` ne lance jamais"),
    "planning_cmd": ("Jamais d'agent de dev", "2. **C'est un PONT"),
    "planning_all_cmd": ("**Rien d'autre.**", "6. **Tu n'écris JAMAIS"),
}
INTERDIT = "fournee"
PORTEUR = ("tasks.py fournee", "membre du groupe")

# (h) La fournée dégénérée garde le write-set DÉCLARÉ — par identifiant de surface
# EXISTANTE (aucune ligne `Surface` de plus) : (ancre, commande voisine exigée).
WRITESET = "tasks.py writeset"
DEGENEREE: dict[str, tuple[str, str]] = {
    "kickoff_skill": ("is a degenerate batch: the parent alone", WRITESET),
    "kickoff_cmd": ("est une fournée dégénérée : le parent seul", WRITESET),
    "task_board_skill": ("Une fournée dégénérée (plan `LOTS: aucun`", WRITESET),
}
# (h) Le remède du parent dégénéré qui TOURNE déjà réduit à son plan : (début UNIQUE,
# fin, jeton exigé, jeton interdit) — la relance redéclare le groupe, `parallel` avant
# elle ferait refuser la fournée (lot A, 78298b1e).
REMEDE_R: dict[str, tuple[str, str, str, str]] = {
    "kickoff_skill": ("ALREADY running", "TRAP:", "re-declares the group", "then `parallel`"),
    "kickoff_cmd": ("TOURNE déjà", "PIÈGE :", "redéclare le groupe", "puis `parallel`"),
    "task_board_skill": ("TOURNE déjà", "PIÈGE :", "redéclare le groupe", "puis `parallel`"),
}

# (i) Le statut de parallélisme des devs PAR HÔTE, lu dans la table (lot O de FB6).
TABLE = ".agents/ref/PARALLELISME_HOTES.md"
STATUTS = ("mesure-parallele", "mesure-serie", "pas-mesure", "non-mesurable", "hote-absent")
FAMILLE = {"mesure-parallele": "P", "mesure-serie": "S"}  # tout autre statut : N
NON_MESURE = "COVERAGE DEGRADED — parallélisme des devs non mesuré"
EN_SERIE = " : lots joués en série"
# La cause FERMÉE d'une ligne N, écrite avec la date du statut (Annexe B) ; None : sans parenthèse.
CAUSE_N = {"pas-mesure": None, "hote-absent": "hôte absent du poste de mesure",
           "non-mesurable": "présent sans CLI headless"}
CLAUDE_P = ("**Claude Code** — the lots' devs are launched in ONE message, each in its own worktree "
            '(`isolation: "worktree"`): MEASURED')
# Hôte de la table -> (nom écrit dans les défs, clé d'identifiant de cas, défs qui portent sa ligne).
# La clé de copilot est `github`, comme l'hôte des défs : voir le filtre des lots D.
_MIROIRS = ("orchestrator-claude", "orchestrator-kimi")
HOTES_TABLE: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "claude": ("Claude Code", "claude", _MIROIRS),
    "codex": ("Codex", "codex", ("orchestrator-codex", *_MIROIRS)),
    "copilot": ("GitHub Copilot", "github", ("orchestrator-github", *_MIROIRS)),
    "gemini": ("Gemini CLI", "gemini", ("orchestrator-gemini", *_MIROIRS)),
    "antigravity": ("Antigravity", "antigravity", ("orchestrator-gemini", *_MIROIRS)),
    "kimi": ("Kimi Code", "kimi", _MIROIRS),
}
# Le TÉMOIN : la table de la nuit (plan FB6, Annexe D) — hôte, statut, date du statut jugés
# seuls. Il ne juge les défs réelles que tant que la vraie table est ABSENTE.
TABLE_NUIT = """\
HOTE: claude | mesure-parallele | 2026-10-01 | — | — | L-00000551 ; task-board SKILL point 3 | —
HOTE: codex | pas-mesure | 2026-10-14 | darwin-arm64 | 0.155.1 | aucune session lancée au 2026-10-14 | —
HOTE: copilot | pas-mesure | 2026-10-14 | darwin-arm64 | 1.0.96 | aucune session lancée au 2026-10-14 | —
HOTE: gemini | pas-mesure | 2026-10-14 | darwin-arm64 | 0.63.0 | facturation à l'usage ; profil strict-open | —
HOTE: kimi | hote-absent | 2026-10-14 | darwin-arm64 | — | hôte absent du poste de mesure | —
HOTE: antigravity | non-mesurable | 2026-10-14 | darwin-arm64 | — | présent (app 2.22.0), sans CLI headless | —
"""
LIGNE_HOTE = re.compile(r"^\s*(?:[-*]\s+)?`?HOTE:(.*)$")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Les surfaces qui DOIVENT porter un seuil chiffré : le jeton dérivé de (a), les
# porteurs W24 déjà connus, et la découpe par défaut de la planning SKILL.
PORTEUSES_SEUIL = frozenset(
    {s.ident for s in SURFACES if s.role in ("planner", "orchestrator", "annonce")} | {"planning_skill"}
)

# Deux formes de la découpe, absentes de la famille W24 : `plan_des` est le premier
# compte de fichiers qui exige la découpe — « dès 6 » -> 6 ; « 5 au plus » -> 6.
FAMILLE_DECOUPE: tuple[tuple[str, re.Pattern[str], int], ...] = tuple(
    (nom, re.compile(motif, re.IGNORECASE), decalage)
    for nom, motif, decalage in (
        ("dès N fichiers", rf"\bd[èe]s\s+{w24._N}\s+fichiers?\b", 0),
        ("N fichiers au plus", rf"{w24._N}\s+fichiers?\s+au\s+plus\b", 1),
        ("N files at most", rf"{w24._N}\s+files?\s+at\s+most\b", 1),
        ("from N files on", rf"\bfrom\s+{w24._N}\s+files?\s+on\b", 0),
    )
)


def jetons(role: str, seuil: int) -> tuple[tuple[str, str, bool], ...]:
    """(nom court, jeton, casse exigée) de chaque rôle de l'Annexe T."""
    return {
        "planner": (
            ("LOT", "LOT:", True),
            ("INTEGRATION", "INTÉGRATION:", True),
            ("plan_lots_check", "plan_lots.py check", True),
            ("seuil_decoupe", f"from {seuil + 1} files on", False),
        ),
        "plan_critic": (
            ("plan_lots_check", "plan_lots.py check", True),
            ("recouvrement", "recouvrement", False),
            ("INTEGRATION", "INTÉGRATION:", True),
        ),
        "orchestrator": (  # la ligne de statut par hôte : (i), `fautes_statut`
            ("tasks_fournee", "tasks.py fournee", True),
            ("table_parallelisme", TABLE, True),
        ),
        "annonce": (("tasks_fournee", "tasks.py fournee", True),),
        "interdit": (("interdit", INTERDIT, False),),
        "porteur": (("tasks_fournee", PORTEUR[0], True), ("membre_du_groupe", PORTEUR[1], False)),
    }[role]


# ---------------------------------------------------------------------------
# Fonctions pures — les mutants rejouent CES fonctions
# ---------------------------------------------------------------------------
def nfc(texte: str) -> str:
    return unicodedata.normalize("NFC", texte)


def _plat(texte: str, casse: bool) -> str:
    plat = re.sub(r"\s+", " ", nfc(texte))
    return plat if casse else plat.casefold()


def present(texte: str, jeton: str, casse: bool) -> bool:
    """Le jeton, blancs pliés (une phrase coupée sur deux lignes compte)."""
    return _plat(jeton, casse) in _plat(texte, casse)


def retirer(texte: str, jeton: str, casse: bool) -> str:
    """TOUTES les occurrences, blancs pliés : un jeton répété ne masque pas son mutant."""
    motif = r"\s+".join(re.escape(mot) for mot in nfc(jeton).split())
    return re.sub(motif, "", texte, flags=0 if casse else re.IGNORECASE)


def tranche(texte: str, debut: str, fin: str) -> str | None:
    """Le texte entre deux ancres. None si l'ancre de début manque ou est ambiguë,
    ou si la fin manque : l'appelant le traite en ÉCHEC (L-00000186)."""
    if texte.count(debut) != 1:
        return None
    i = texte.find(debut)
    j = texte.find(fin, i + len(debut))
    return None if j < 0 else texte[i:j]


def voisins(texte: str, a: str, b: str, fenetre: int = FENETRE) -> bool:
    """Une occurrence de `a` porte `b` à moins de `fenetre` caractères (blancs pliés)."""
    plat_a, plat = _plat(a, True), _plat(texte, True)
    cible = _plat(b, False)
    for m in re.finditer(re.escape(plat_a), plat):
        if cible in plat[max(0, m.start() - fenetre): m.end() + fenetre].casefold():
            return True
    return False


def captures_etendues(texte: str) -> list:
    """La famille W24 importée, plus les formes de la découpe ; une capture par nombre."""
    vues = {c.debut: c for c in w24.captures(texte)}
    for nom, motif, decalage in FAMILLE_DECOUPE:
        for m in motif.finditer(texte):
            debut, fin = m.span(1)
            if debut in vues:
                continue
            n = w24._valeur(m.group(1))
            vues[debut] = w24.Capture(nom, n, n + decalage, debut, fin, texte.count("\n", 0, debut) + 1)
    return [vues[k] for k in sorted(vues)]


class TableIllisible(ValueError):
    """La table existe mais ne se lit pas : rouge, jamais un repli sur le contrat d'avant."""


def lire_table(texte: str) -> dict[str, tuple[str, str]]:
    """hôte -> (statut, date du statut). Lève TableIllisible avec TOUTES ses fautes."""
    fautes: list[str] = []
    statuts: dict[str, tuple[str, str]] = {}
    for n, ligne in enumerate(nfc(texte).splitlines(), 1):
        m = LIGNE_HOTE.match(ligne)
        if m is None:
            continue
        champs = [c.strip().strip("`").strip() for c in m.group(1).split("|")]
        if champs[0].startswith("<"):
            continue  # la ligne de GRAMMAIRE `HOTE: <claude|codex|…> | …`
        if len(champs) < 3:
            fautes.append(f"l.{n} : moins de trois champs (hôte | statut | date)")
            continue
        hote, statut, date = champs[:3]
        if hote not in HOTES_TABLE:
            fautes.append(f"l.{n} : hôte inconnu « {hote} »")
        elif hote in statuts:
            fautes.append(f"l.{n} : hôte « {hote} » en double")
        if statut not in STATUTS:  # ÉGALITÉ EXACTE : `non-mesure`, `pas-mesurex` refusés
            fautes.append(f"l.{n} : statut « {statut} » hors du vocabulaire fermé {STATUTS}")
        if not DATE.fullmatch(date):
            fautes.append(f"l.{n} : date du statut « {date} » illisible")
        if hote in HOTES_TABLE and hote not in statuts:
            statuts[hote] = (statut, date)
    manquants = sorted(set(HOTES_TABLE) - set(statuts))
    if manquants:
        fautes.append(f"hôtes sans ligne `HOTE:` : {manquants}")
    if fautes:
        raise TableIllisible("\n".join(fautes))
    return statuts


def famille(statut: str) -> str:
    return FAMILLE.get(statut, "N")


def prefixe(hote: str, fam: str) -> str:
    """Ce qui NOMME la famille `fam` pour cet hôte dans une déf."""
    nom = HOTES_TABLE[hote][0]
    if fam == "N":
        return f"{NON_MESURE} sur {nom}"
    if fam == "S":
        return f"COVERAGE DEGRADED — parallélisme des devs mesuré en série sur {nom}"
    return CLAUDE_P if hote == "claude" else f"**{nom}** — PARALLÈLE MESURÉ"


def ligne_exigee(hote: str, statut: str, date: str) -> str:
    """La ligne exacte (ou son ouverture, pour un P) que le statut exige (Annexe B)."""
    fam = famille(statut)
    if fam == "P":
        return CLAUDE_P if hote == "claude" else f"{prefixe(hote, 'P')} ({date}"
    if fam == "S":
        return prefixe(hote, "S") + EN_SERIE
    cause = CAUSE_N[statut]
    return prefixe(hote, "N") + (f" ({cause}, {date})" if cause else "") + EN_SERIE


DEFS_ORCHESTRATOR = tuple(f"orchestrator-{hote}" for hote, _, _ in HOTES)


def exigences_statut(statuts: dict[str, tuple[str, str]] | None) -> dict[str, list[tuple[str, str]]]:
    """déf -> [(clé d'hôte, ligne exigée)] ; table absente (None) : le contrat d'avant."""
    if statuts is None:
        return {i: [("non_mesure", NON_MESURE)] for i in DEFS_ORCHESTRATOR}
    exige: dict[str, list[tuple[str, str]]] = {i: [] for i in DEFS_ORCHESTRATOR}
    for hote, (statut, date) in sorted(statuts.items()):
        _, cle, porteuses = HOTES_TABLE[hote]
        for i in porteuses:
            exige[i].append((cle, ligne_exigee(hote, statut, date)))
    return exige


def interdits_statut(statuts: dict[str, tuple[str, str]] | None) -> dict[str, list[tuple[str, str]]]:
    """déf -> [(clé d'hôte, préfixe d'une AUTRE famille que celle de la table)]."""
    interdit: dict[str, list[tuple[str, str]]] = {i: [] for i in DEFS_ORCHESTRATOR}
    for hote, (statut, _) in sorted((statuts or {}).items()):
        _, cle, porteuses = HOTES_TABLE[hote]
        for autre in "NSP":
            if autre != famille(statut):
                for i in porteuses:
                    interdit[i].append((cle, prefixe(hote, autre)))
    return interdit


def fautes_statut(ident: str, texte: str, statuts: dict[str, tuple[str, str]] | None) -> list[str]:
    """(i) sur UNE déf orchestrator : chaque ligne exigée présente, aucune famille contraire."""
    fautes = [f"{ident} : (i) ligne de statut absente ({cle}) « {jeton} »"
              for cle, jeton in exigences_statut(statuts)[ident] if not present(texte, jeton, True)]
    fautes += [f"{ident} : (i) « {pref} » contredit le statut de {cle} à la table"
               for cle, pref in interdits_statut(statuts)[ident] if present(texte, pref, True)]
    return fautes


def violations_seuil(texte: str, seuil: int) -> list[str]:
    return [
        f"l.{c.ligne} « {c.motif} » n={c.nombre} -> découpe dès {c.plan_des}, le code dit dès {seuil + 1}"
        for c in captures_etendues(texte)
        if c.plan_des != seuil + 1
    ]


_TABLE_REELLE = object()  # sentinelle : `violations` lit la vraie table, sauf statuts passés


def violations(surface: Surface, texte: str, seuil: int, statuts: object = _TABLE_REELLE) -> list[str]:
    """L'Annexe T sur UNE surface. Une liste vide est le seul vert."""
    fautes = []
    if surface.role == "orchestrator":
        fautes += fautes_statut(surface.ident, texte, statuts_reels() if statuts is _TABLE_REELLE else statuts)
    if surface.role == "interdit":
        debut, fin = INTERDITS[surface.ident]
        tr = tranche(nfc(texte), debut, fin)
        if tr is None:
            fautes.append(f"{surface.ident} : tranche des interdits « {debut} » … « {fin} » introuvable ou ambiguë")
        elif not present(tr, INTERDIT, False):
            fautes.append(f"{surface.ident} : interdit absent — `{INTERDIT}` hors de la tranche des interdits")
    elif surface.role == "porteur":
        for nom, jeton, casse in jetons("porteur", seuil):
            if not present(texte, jeton, casse):
                fautes.append(f"{surface.ident} : jeton absent ({nom}) « {jeton} »")
        if not fautes and not voisins(texte, *PORTEUR):
            fautes.append(f"{surface.ident} : `{PORTEUR[0]}` sans « {PORTEUR[1]} » à moins de {FENETRE} caractères")
    else:
        for nom, jeton, casse in jetons(surface.role, seuil):
            if not present(texte, jeton, casse):
                fautes.append(f"{surface.ident} : jeton absent ({nom}) « {jeton} »")
    if surface.ident in DEGENEREE:
        ancre, voisin = DEGENEREE[surface.ident]
        if not present(texte, ancre, True):
            fautes.append(f"{surface.ident} : (h) ancre absente « {ancre} »")
        elif _plat(texte, True).count(_plat(ancre, True)) != 1:
            fautes.append(f"{surface.ident} : (h) ancre « {ancre} » non unique")
        elif not voisins(texte, ancre, voisin):
            fautes.append(f"{surface.ident} : (h) « {ancre} » sans `{voisin}` à moins de {FENETRE} caractères")
    if surface.ident in REMEDE_R:
        debut, fin, exige, interdit = REMEDE_R[surface.ident]
        tr = tranche(nfc(texte), debut, fin)
        if tr is None:
            fautes.append(f"{surface.ident} : (h) remède du parent réduit « {debut} » … « {fin} » introuvable ou ambigu")
        else:
            if not present(tr, exige, False):
                fautes.append(f"{surface.ident} : (h) remède du parent réduit sans « {exige} »")
            if present(tr, interdit, False):
                fautes.append(f"{surface.ident} : (h) remède du parent réduit par « {interdit} » — la relance "
                              "redéclare le groupe, `parallel` avant elle fait refuser la fournée")
    fautes += [f"{surface.ident} : seuil W24 {v}" for v in violations_seuil(nfc(texte), seuil)]
    return fautes


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def seuil_du_code() -> int:
    return w24.lire_seuil((ROOT / w24.SOURCE_SEUIL).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def lire(chemin: str) -> str:
    return nfc((ROOT / chemin).read_text(encoding="utf-8"))


def statuts_reels() -> dict[str, tuple[str, str]] | None:
    """La vraie table : None si ABSENTE (ni fichier ni lien) ; un lien cassé, un dossier ou
    un texte illisible LÈVENT — rouge, jamais le contrat d'avant par repli. Lue sans le
    cache de `lire` : une table d'un cas (racine factice) ne fuit jamais dans un autre."""
    if not os.path.lexists(ROOT / TABLE):
        return None
    return lire_table((ROOT / TABLE).read_text(encoding="utf-8"))


def statuts_temoin() -> dict[str, tuple[str, str]]:
    """La table qui juge les défs réelles au témoin : la vraie, sinon celle de la nuit."""
    reels = statuts_reels()
    return lire_table(TABLE_NUIT) if reels is None else reels


def _collecte(fonction):
    """Les statuts au moment de la COLLECTE : une table illisible y vaut la nuit (pour les
    identifiants seuls) — `test_table_lisible_ou_absente` et chaque cas la relisent et rougissent."""
    try:
        return fonction()
    except (TableIllisible, OSError):
        return lire_table(TABLE_NUIT)


def _base_verte(surface: Surface) -> str:
    texte = lire(surface.chemin)
    assert violations(surface, texte, seuil_du_code()) == [], f"{surface.ident} : base rouge"
    return texte


IDS = [s.ident for s in SURFACES]
CAS_JETONS = [  # les NOMS seuls : ils ne dépendent pas du seuil, lu à l'exécution du cas
    (s, nom) for s in SURFACES for nom, _, _ in jetons(s.role, 0)
]
# (i) Les cas du témoin, par (déf, clé d'hôte) ; les bascules, par (hôte, autre statut).
_TEMOIN_COLLECTE = _collecte(statuts_temoin)
CAS_TEMOIN = [(i, cle) for i, lignes in exigences_statut(_TEMOIN_COLLECTE).items() for cle, _ in lignes]
CAS_CONTRAIRE = [(i, cle, pref) for i, prefs in interdits_statut(_TEMOIN_COLLECTE).items() for cle, pref in prefs]
CAS_BASCULE = [(hote, autre) for hote in sorted(HOTES_TABLE) for autre in STATUTS
               if autre != _TEMOIN_COLLECTE[hote][0]]
CAS_DATE = [hote for hote, (statut, date) in sorted(_TEMOIN_COLLECTE.items()) if date in ligne_exigee(hote, statut, date)]
IDS_TEMOIN = [f"{i}-{cle}" for i, cle in CAS_TEMOIN]
IDS_CONTRAIRE = [f"{i}-{cle}-{n}" for n, (i, cle, _) in enumerate(CAS_CONTRAIRE)]
IDS_BASCULE = [f"{HOTES_TABLE[h][1]}-{a}" for h, a in CAS_BASCULE]
IDS_DATE = [HOTES_TABLE[h][1] for h in CAS_DATE]


# ---------------------------------------------------------------------------
# Non-vacuité
# ---------------------------------------------------------------------------
def test_non_vacuite_annexe_t_et_ajout() -> None:
    assert len(SURFACES) == 24, "Annexe T : 5 + 5 + 5 + 4 + 4, plus la task-board SKILL"
    assert len({s.chemin for s in SURFACES}) == len(SURFACES), "surface listée deux fois"
    assert len(PAR_IDENT) == len(SURFACES), "identifiant de cas en double"
    assert {s.ident for s in SURFACES if s.role == "interdit"} == set(INTERDITS)
    assert PORTEUSES_SEUIL <= set(PAR_IDENT)
    assert len(DEGENEREE) == 3 and set(DEGENEREE) <= set(PAR_IDENT), "(h) : une surface hors de la liste"
    assert set(REMEDE_R) == set(DEGENEREE), "(h) : le remède du parent réduit sur les trois mêmes surfaces"
    for role in {s.role for s in SURFACES}:
        assert jetons(role, seuil_du_code()), f"rôle {role} sans jeton"
    assert seuil_du_code() >= 1


def test_ids_des_defs_hors_du_filtre_des_lots_d() -> None:
    """Les cas des défs (lots J1, J2) ne sont pas sélectionnés par le filtre des lots D."""
    filtre = ("kickoff", "skill", "agents_md", "copilot", "planning")  # `agents` nu attrape `.agents/`
    for s in SURFACES:
        attrape = any(mot in s.ident for mot in filtre)
        assert attrape == (s.role not in ("planner", "plan_critic", "orchestrator")), s.ident
    # (i) : ses cas jugent les défs orchestrator, jamais une surface des lots D.
    for ident in (*IDS_TEMOIN, *IDS_CONTRAIRE, *IDS_BASCULE, *IDS_DATE, *DEFS_ORCHESTRATOR):
        assert not any(mot in ident for mot in filtre), ident


def test_non_vacuite_statut_par_hote() -> None:
    """(i) : chaque déf orchestrator porte au moins une ligne de statut, au témoin comme
    au contrat d'avant ; chaque hôte de la table a au moins une déf porteuse ; la
    table de la nuit se lit et couvre les six hôtes."""
    assert set(DEFS_ORCHESTRATOR) == {s.ident for s in SURFACES if s.role == "orchestrator"}
    nuit = lire_table(TABLE_NUIT)
    assert set(nuit) == set(HOTES_TABLE) and len(HOTES_TABLE) == 6
    for statuts in (None, nuit, statuts_temoin()):
        assert all(exigences_statut(statuts)[i] for i in DEFS_ORCHESTRATOR), statuts
    assert all(set(porteuses) <= set(DEFS_ORCHESTRATOR) for _, _, porteuses in HOTES_TABLE.values())
    assert len(CAS_TEMOIN) == sum(len(p) for _, _, p in HOTES_TABLE.values()) == 16
    assert CAS_CONTRAIRE and CAS_DATE and len(CAS_BASCULE) == 6 * (len(STATUTS) - 1)


@pytest.mark.parametrize("surface", SURFACES, ids=IDS)
def test_surface_lue_non_vide(surface: Surface) -> None:
    assert (ROOT / surface.chemin).is_file(), f"{surface.chemin} absent"
    assert lire(surface.chemin).strip(), f"{surface.chemin} vide"


# ---------------------------------------------------------------------------
# L'Annexe T, une surface par cas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("surface", SURFACES, ids=IDS)
def test_annexe_t(surface: Surface) -> None:
    fautes = violations(surface, lire(surface.chemin), seuil_du_code())
    assert fautes == [], "\n".join(fautes)


@pytest.mark.parametrize("ident", sorted(PORTEUSES_SEUIL))
def test_porteuse_du_seuil_en_capture_un(ident: str) -> None:
    assert captures_etendues(lire(PAR_IDENT[ident].chemin)), f"{ident} : aucun seuil chiffré vu (non-vacuité de (f))"


# ---------------------------------------------------------------------------
# Mutants — un par jeton, donc un par hôte pour les défs
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("surface", "nom"), CAS_JETONS, ids=[f"{s.ident}-{n}" for s, n in CAS_JETONS])
def test_mutant_jeton_retire(surface: Surface, nom: str) -> None:
    texte = _base_verte(surface)
    seuil = seuil_du_code()
    _, jeton, casse = next(j for j in jetons(surface.role, seuil) if j[0] == nom)
    if surface.role == "interdit":
        tr = tranche(texte, *INTERDITS[surface.ident])
        mutant = texte.replace(tr, retirer(tr, jeton, casse), 1)
    else:
        mutant = retirer(texte, jeton, casse)
    assert mutant != texte, f"{surface.ident} : le mutant n'a rien changé — il ne mesure rien"
    assert violations(surface, mutant, seuil), f"{surface.ident} : LA RÈGLE NE MORD PAS sans « {jeton} »"


@pytest.mark.parametrize("ident", sorted(INTERDITS))
def test_mutant_interdit_deplace_hors_tranche(ident: str) -> None:
    """`fournee` retiré des interdits mais recopié en fin de fichier : rouge — la
    présence n'importe où ne vaut pas interdiction."""
    surface = PAR_IDENT[ident]
    texte = _base_verte(surface)
    tr = tranche(texte, *INTERDITS[ident])
    mutant = texte.replace(tr, retirer(tr, INTERDIT, False), 1) + "\n\nJamais `tasks.py fournee`.\n"
    assert mutant != texte
    assert present(mutant, INTERDIT, False), "le mutant doit garder `fournee` ailleurs"
    assert violations(surface, mutant, seuil_du_code()), f"{ident} : un `fournee` hors tranche passe"


@pytest.mark.parametrize("ident", ["task_board_skill"])
def test_mutant_porteur_eloigne(ident: str) -> None:
    """(g) : le porteur nommé loin de « membre du groupe » rougit."""
    surface = PAR_IDENT[ident]
    texte = _base_verte(surface)
    mutant = retirer(texte, PORTEUR[1], False) + "\n" + ("x" * (2 * FENETRE)) + "\nmembre du groupe\n"
    assert mutant != texte
    assert violations(surface, mutant, seuil_du_code()), f"{ident} : un voisinage rompu passe"


def fautes_h(surface: Surface, texte: str) -> list[str]:
    """Les seules fautes de (h) : un rouge d'une autre règle ne compte pas pour elle."""
    return [f for f in violations(surface, texte, seuil_du_code()) if "(h)" in f]


@pytest.mark.parametrize("ident", sorted(DEGENEREE))
def test_h_degeneree_writeset(ident: str) -> None:
    """(h) : la fournée dégénérée nomme `tasks.py writeset` à côté d'elle."""
    fautes = fautes_h(PAR_IDENT[ident], lire(PAR_IDENT[ident].chemin))
    assert fautes == [], "\n".join(fautes)


@pytest.mark.parametrize("ident", sorted(DEGENEREE))
def test_mutant_h_writeset_eloigne_puis_ancre_retiree(ident: str) -> None:
    """(h) : `tasks.py writeset` éloigné de l'ancre rougit ; l'ancre retirée aussi ;
    « puis `parallel` » réintroduit dans le remède du parent réduit rougit, la
    relance qui redéclare le groupe gardée ; cette relance retirée rougit aussi."""
    surface = PAR_IDENT[ident]
    texte = _base_verte(surface)
    ancre, voisin = DEGENEREE[ident]
    eloigne = retirer(texte, voisin, True) + "\n" + ("x" * (2 * FENETRE)) + f"\n`{voisin}`\n"
    assert eloigne != texte and present(eloigne, voisin, True), f"{ident} : le mutant doit garder la commande ailleurs"
    assert fautes_h(surface, eloigne), f"{ident} : (h) NE MORD PAS sur un voisinage rompu"
    sans_ancre = retirer(texte, ancre, True)
    assert sans_ancre != texte, f"{ident} : le mutant n'a rien changé"
    assert fautes_h(surface, sans_ancre), f"{ident} : (h) NE MORD PAS sans « {ancre} »"
    debut, fin, exige, interdit = REMEDE_R[ident]
    tr = tranche(texte, debut, fin)
    assert tr is not None and exige in tr, f"{ident} : tranche du remède introuvable"
    avec_parallel = texte.replace(tr, tr.replace(exige, f"{interdit}, {exige}", 1), 1)
    assert avec_parallel != texte and present(tranche(avec_parallel, debut, fin), exige, False)
    assert fautes_h(surface, avec_parallel), f"{ident} : (h) NE MORD PAS sur « {interdit} » réintroduit"
    sans_relance = texte.replace(tr, retirer(tr, exige, False), 1)
    assert sans_relance != texte, f"{ident} : le mutant n'a rien changé"
    assert fautes_h(surface, sans_relance), f"{ident} : (h) NE MORD PAS sans « {exige} »"


@pytest.mark.parametrize("ident", sorted(PORTEUSES_SEUIL))
def test_mutant_seuil_a_4_et_constante_mutee(ident: str) -> None:
    surface = PAR_IDENT[ident]
    texte = _base_verte(surface)
    seuil = seuil_du_code()
    premiere = captures_etendues(texte)[0]
    mutant = texte[: premiere.debut] + "4" + texte[premiere.fin:]
    assert mutant != texte, f"{ident} : le mutant n'a rien changé"
    assert violations_seuil(mutant, seuil), f"{ident} : LA RÈGLE NE MORD PAS sur un seuil à 4"
    assert violations_seuil(texte, seuil - 1), f"{ident} : la règle ne suit pas la constante"


# ---------------------------------------------------------------------------
# (i) Le statut par hôte — la table, le contrat d'avant, le témoin
# ---------------------------------------------------------------------------
def _def(ident: str) -> Surface:
    return PAR_IDENT[ident]


def test_table_lisible_ou_absente() -> None:
    """La vraie table est absente (contrat d'avant) ou se lit ENTIÈRE : six hôtes, statuts
    fermés, dates lisibles. Illisible : rouge ici, et dans chaque cas qui la lit."""
    statuts = statuts_reels()  # lève TableIllisible ou OSError : rouge, avec toutes les fautes
    assert statuts is None or set(statuts) == set(HOTES_TABLE)


@pytest.mark.parametrize("ident", DEFS_ORCHESTRATOR)
def test_mutant_contrat_table_absente(ident: str) -> None:
    """Table absente : « non mesuré » exigé sur les cinq défs — retiré, rouge. Une déf
    qui ne le porte plus (son hôte passé P à une table PRÉSENTE) reçoit la ligne en base :
    le contrat d'avant reste jugé, sans rougir une déf que la vraie table juge verte."""
    texte = lire(_def(ident).chemin)
    if statuts_reels() is not None and not present(texte, NON_MESURE, True):
        texte += f"\n{NON_MESURE} sur <hôte>{EN_SERIE}\n"
    assert fautes_statut(ident, texte, None) == [], f"{ident} : contrat d'avant rouge"
    mutant = retirer(texte, NON_MESURE, True)
    assert mutant != texte, f"{ident} : le mutant n'a rien changé"
    assert violations(_def(ident), mutant, seuil_du_code(), None), f"{ident} : (i) NE MORD PAS sans « {NON_MESURE} »"


@pytest.mark.parametrize("ident", DEFS_ORCHESTRATOR)
def test_temoin_defs_reelles(ident: str) -> None:
    """Les défs RÉELLES portent la ligne de chaque hôte au statut du témoin."""
    fautes = fautes_statut(ident, lire(_def(ident).chemin), statuts_temoin())
    assert fautes == [], "\n".join(fautes)


def _texte_vert_au_temoin(ident: str) -> str:
    texte = lire(_def(ident).chemin)
    assert fautes_statut(ident, texte, statuts_temoin()) == [], f"{ident} : base du témoin rouge"
    return texte


@pytest.mark.parametrize(("ident", "cle"), CAS_TEMOIN, ids=IDS_TEMOIN)
def test_mutant_temoin_ligne_retiree(ident: str, cle: str) -> None:
    statuts = statuts_temoin()
    texte = _texte_vert_au_temoin(ident)
    jeton = dict(exigences_statut(statuts)[ident])[cle]
    mutant = retirer(texte, jeton, True)
    assert mutant != texte, f"{ident} : le mutant n'a rien changé"
    assert fautes_statut(ident, mutant, statuts), f"{ident} : (i) NE MORD PAS sans la ligne de {cle}"


@pytest.mark.parametrize(("ident", "cle", "pref"), CAS_CONTRAIRE, ids=IDS_CONTRAIRE)
def test_mutant_temoin_statut_contraire(ident: str, cle: str, pref: str) -> None:
    """Une ligne d'une AUTRE famille pour le même hôte, ajoutée à la déf : rouge."""
    texte = _texte_vert_au_temoin(ident)
    mutant = texte + f"\n{pref} (2099-01-01, x){EN_SERIE}\n"
    assert fautes_statut(ident, mutant, statuts_temoin()), f"{ident} : (i) NE MORD PAS sur « {pref} » ajouté"


@pytest.mark.parametrize(("hote", "autre"), CAS_BASCULE, ids=IDS_BASCULE)
def test_mutant_temoin_bascule_de_statut(hote: str, autre: str) -> None:
    """L'hôte passé à chacun des quatre autres statuts, défs inchangées : chaque déf porteuse rougit."""
    statuts = dict(statuts_temoin())
    statuts[hote] = (autre, statuts[hote][1])
    for ident in HOTES_TABLE[hote][2]:
        texte = _texte_vert_au_temoin(ident)
        assert fautes_statut(ident, texte, statuts), f"{ident} : (i) NE MORD PAS sur {hote} -> {autre}"


@pytest.mark.parametrize("hote", CAS_DATE, ids=IDS_DATE)
def test_mutant_temoin_date(hote: str) -> None:
    """La date du statut changée à la table, là où la ligne la porte : chaque déf porteuse rougit."""
    statuts = dict(statuts_temoin())
    statuts[hote] = (statuts[hote][0], "2099-12-31")
    for ident in HOTES_TABLE[hote][2]:
        assert fautes_statut(ident, _texte_vert_au_temoin(ident), statuts), f"{ident} : (i) date de {hote} non jugée"


# ---------------------------------------------------------------------------
# Contrôles synthétiques — aucune surface lue
# ---------------------------------------------------------------------------
def test_controle_synthetique_famille_de_la_decoupe() -> None:
    for phrase in ("la découpe se fait dès 6 fichiers", "des lots de 5 fichiers au plus",
                   "Dès six fichiers, découpe", "lots of 5 files at most", "6 files or more",
                   "SPLIT BY DEFAULT, from 6 files on"):
        assert captures_etendues(phrase), phrase
        assert violations_seuil(phrase, 5) == [], phrase
    for phrase in ("dès 4 fichiers", "des lots de 3 fichiers au plus", "dès 16 fichiers", "8 files at most",
                   "from 4 files on", "from 16 files on"):
        assert violations_seuil(phrase, 5), phrase
    assert captures_etendues("8 fichiers quand docs/tasks/** en vaut 216") == []


def test_controle_synthetique_tranche_et_voisinage() -> None:
    texte = "A\n- Interdits : `tasks.py start`, `tasks.py fournee`.\n- Un plan prêt\nZ"
    tr = tranche(texte, "- Interdits :", "- Un plan prêt")
    assert tr is not None and present(tr, INTERDIT, False)
    assert tranche(texte + "\n- Interdits :", "- Interdits :", "- Un plan prêt") is None, "ancre ambiguë"
    assert tranche(texte, "- Interdits :", "absente") is None
    assert voisins("le porteur de `tasks.py fournee` EST membre du groupe", *PORTEUR)
    assert not voisins("`tasks.py fournee`" + "x" * (FENETRE + 10) + "membre du groupe", *PORTEUR)
    assert retirer("LOT:\nLOT: x", "LOT:", True) == "\n x"
    assert present("dès 6\n   fichiers", "dès 6 fichiers", False)
    assert voisins("une fournée dégénérée : `tasks.py writeset <T> <chemins…>` AVANT", "dégénérée", WRITESET)
    assert not voisins("fournée dégénérée" + "x" * (FENETRE + 10) + WRITESET, "dégénérée", WRITESET)
    tb = Surface("task_board_skill", "t", "porteur")
    porteur = "`tasks.py fournee` : le parent EST membre du groupe. "
    assert fautes_h(tb, porteur), "(h) : ancre absente, rouge"
    remede = " Un parent qui TOURNE déjà réduit : `tasks.py writeset`, puis relance, qui redéclare le groupe. PIÈGE : x."
    vert = porteur + "Une fournée dégénérée (plan `LOTS: aucun`) : `tasks.py writeset` AVANT." + remede
    assert violations(tb, vert, 5) == []
    assert fautes_h(tb, vert.replace("puis relance", "puis `parallel`, puis relance")), "(h) : `parallel` au remède"
    assert fautes_h(tb, vert.replace("redéclare le groupe", "repart")), "(h) : relance sans redéclaration"
    assert fautes_h(tb, vert.replace("PIÈGE :", "Note.")), "(h) : tranche du remède sans fin, rouge"


def test_controle_synthetique_regle_par_role() -> None:
    seuil = 5
    planner = Surface("p", "p", "planner")
    bon = "LOT: A | x\nINTÉGRATION: aucune\n`plan_lots.py check`\nSPLIT BY DEFAULT, from 6 files on"
    assert violations(planner, bon, seuil) == []
    assert violations(planner, bon.replace("from 6", "from 4"), seuil), "seuil faux : rouge"
    assert violations(planner, bon.replace("from 6 files on", "dès 6 fichiers"), seuil), \
        "forme française d'avant : le jeton anglais manque, rouge"
    assert violations(planner, bon, seuil - 1), "jeton dérivé de la constante : rouge à 4"
    assert violations(planner, bon.replace("INTÉGRATION:", "integration:"), seuil), "casse exigée"


def _refusee(texte: str) -> str:
    with pytest.raises(TableIllisible) as exc:
        lire_table(texte)
    return str(exc.value)


def test_controle_synthetique_table_lue_et_refusee() -> None:
    nuit = lire_table(TABLE_NUIT)
    assert nuit["claude"] == ("mesure-parallele", "2026-10-01")
    assert nuit["kimi"] == ("hote-absent", "2026-10-14") and nuit["antigravity"] == ("non-mesurable", "2026-10-14")
    grammaire = "`HOTE: <claude|codex|copilot|gemini|kimi|antigravity> | <mesure-parallele|pas-mesure> | <date> |`\n"
    assert lire_table(grammaire + TABLE_NUIT) == nuit, "la ligne de grammaire est sautée"
    assert lire_table(TABLE_NUIT.replace("HOTE: ", "- `HOTE: ").replace(" | —\n", " | —`\n")) == nuit
    assert "non-mesure" in _refusee(TABLE_NUIT.replace("| pas-mesure |", "| non-mesure |", 1)), "C40 : préfixe refusé"
    assert "pas-mesurex" in _refusee(TABLE_NUIT.replace("| pas-mesure |", "| pas-mesurex |", 1)), "égalité exacte"
    for tronque in ("non-mesur", "pas-mesur", "mesure-"):  # un statut tronqué, préfixe d'un statut fermé
        assert tronque in _refusee(TABLE_NUIT.replace("| pas-mesure |", f"| {tronque} |", 1)), tronque
    assert "kimi" in _refusee("\n".join(ligne for ligne in TABLE_NUIT.splitlines() if "kimi" not in ligne)), "hôte manquant"
    assert "double" in _refusee(TABLE_NUIT + "HOTE: codex | pas-mesure | 2026-10-14\n")
    assert "inconnu" in _refusee(TABLE_NUIT + "HOTE: cursor | pas-mesure | 2026-10-14\n")
    assert "date" in _refusee(TABLE_NUIT.replace("| 2026-10-01 |", "| hier |"))
    assert "trois champs" in _refusee(TABLE_NUIT + "HOTE: codex\n")
    assert "hôtes sans ligne" in _refusee("# table vide\n"), "aucune ligne : rouge, jamais le contrat d'avant"


def test_controle_racine_factice_table_absente_lien_dossier(tmp_path, monkeypatch) -> None:
    """La lecture de la vraie table sur une racine factice : absente -> None (contrat
    d'avant) ; lien cassé, dossier, texte illisible -> rouge ; lisible -> ses statuts."""
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    chemin = tmp_path / TABLE
    chemin.parent.mkdir(parents=True)
    assert statuts_reels() is None
    chemin.symlink_to(tmp_path / "absente.md")
    with pytest.raises(OSError):
        statuts_reels()
    chemin.unlink()
    chemin.mkdir()
    with pytest.raises(OSError):
        statuts_reels()
    chemin.rmdir()
    chemin.write_text(TABLE_NUIT.replace("| pas-mesure |", "| non-mesure |", 1), encoding="utf-8")
    with pytest.raises(TableIllisible):
        statuts_reels()
    with pytest.raises(TableIllisible):
        statuts_temoin()  # le témoin ne se replie pas sur la nuit quand la vraie table est illisible
    chemin.write_text(TABLE_NUIT, encoding="utf-8")
    assert statuts_reels() == lire_table(TABLE_NUIT) == statuts_temoin()


def test_controle_synthetique_lignes_par_statut() -> None:
    assert ligne_exigee("codex", "pas-mesure", "2026-10-14") == (
        "COVERAGE DEGRADED — parallélisme des devs non mesuré sur Codex : lots joués en série")
    assert ligne_exigee("kimi", "hote-absent", "2026-10-14") == (
        "COVERAGE DEGRADED — parallélisme des devs non mesuré sur Kimi Code "
        "(hôte absent du poste de mesure, 2026-10-14) : lots joués en série")
    assert ligne_exigee("antigravity", "non-mesurable", "2026-10-14") == (
        "COVERAGE DEGRADED — parallélisme des devs non mesuré sur Antigravity "
        "(présent sans CLI headless, 2026-10-14) : lots joués en série")
    assert ligne_exigee("copilot", "mesure-serie", "2026-11-02") == (
        "COVERAGE DEGRADED — parallélisme des devs mesuré en série sur GitHub Copilot : lots joués en série")
    assert ligne_exigee("gemini", "mesure-parallele", "2026-11-02") == "**Gemini CLI** — PARALLÈLE MESURÉ (2026-11-02"
    assert ligne_exigee("claude", "mesure-parallele", "2026-10-01") == CLAUDE_P
    # Une déf synthétique : codex N puis basculé P à la table — la ligne N restée rougit.
    n_codex = "x " + ligne_exigee("codex", "pas-mesure", "2026-10-14") + " y"
    nuit = lire_table(TABLE_NUIT)
    seul = {"codex": nuit["codex"]}
    assert fautes_statut("orchestrator-codex", n_codex, seul) == []
    bascule = {"codex": ("mesure-parallele", "2026-11-02")}
    fautes = fautes_statut("orchestrator-codex", n_codex, bascule)
    assert any("absente" in f for f in fautes) and any("contredit" in f for f in fautes), fautes
    p_codex = "**Codex** — PARALLÈLE MESURÉ (2026-11-02, darwin-arm64, 0.160.0, table) : recette"
    assert fautes_statut("orchestrator-codex", p_codex, bascule) == []
    assert fautes_statut("orchestrator-codex", p_codex + "\n" + n_codex, bascule), "P et N à la fois : rouge"


# ---------------------------------------------------------------------------
# (j) Lot O de T-01M4XZWZ9C0ZFVXN3MFSFY1G5V : les surfaces de O lancent PAR VAGUES
# ---------------------------------------------------------------------------
QUALIF_O = "PEUT_AJOUTER"
FENETRE_O = 120  # plus long écart mesuré, CLAUDE_P -> `PEUT_AJOUTER` : 85 ; épinglée par test_o_mutant_fenetre_epinglee
_EN_VAGUE = "one message per wave of at most `PEUT_AJOUTER` (`charge_poste.py verdict`)"
_APRES_MEASURED = ", in waves of at most `PEUT_AJOUTER` (`charge_poste.py verdict`)."
_C32 = "run in waves of at most the `PEUT_AJOUTER` of `charge_poste.py verdict`"
_PAR_VAGUE = "par vague, d'au plus le `PEUT_AJOUTER` de `charge_poste.py verdict`."
_MD_DEFS = {"claude": ".claude/agents/orchestrator.md", "gemini": ".gemini/agents/orchestrator.md",
            "kimi": ".kimi-code/agents/orchestrator.md"}
_CODEX, _GITHUB = ".codex/agents/orchestrator.toml", ".github/agents/orchestrator.agent.md"
_TASK_BOARD = ".agents/skills/task-board/SKILL.md"
# Nom court -> chemin : les huit surfaces du lot O, et elles SEULES (PIÈGE 1).
SURFACES_O: dict[str, str] = {
    **{f"o-{h}": c for h, c in _MD_DEFS.items()}, "o-codex": _CODEX, "o-github": _GITHUB,
    "o-task-board": _TASK_BOARD, "o-gemini-md": "GEMINI.md", "o-table-hotes": TABLE,
}
# Les surfaces des AUTRES lots (D, K, P), tenues par leurs propres bancs : jamais lues ici.
HORS_O = frozenset({"AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md", ".agents/skills/kickoff/SKILL.md",
                    ".claude/commands/kickoff.md", ".agents/skills/planning/SKILL.md",
                    ".agents/skills/planning-all/SKILL.md", "README.md", "README-CLAUDE.md"})


@dataclass(frozen=True)
class PassageO:
    ident: str
    chemin: str
    debut: str  # le jeton d'A1 GARDÉ mot pour mot : le qualificatif le SUIT (C35), jamais à sa place
    fin: str
    jeton: str  # le qualificatif exigé dans la tranche


def _nom(h: str, agent: str) -> str:
    """Le nom d'agent tel que la déf l'écrit : gemini le met entre backticks."""
    return f"`{agent}`" if h == "gemini" else agent


def _passages_md(h: str, c: str) -> tuple[PassageO, ...]:
    scr, so = _nom(h, "security-code-review"), _nom(h, "security-orchestrator")
    return (
        # C30 (passe exec-critic) : les deux sécurités en parallèle au verdict qui l'accorde, en série à 1.
        PassageO(f"o-{h}-securite", c, f"in parallel with {scr}", "(both read-only)",
                 f"when both apply and the station verdict grants it (`PEUT_AJOUTER` ≥ 2); "
                 f"at `PEUT_AJOUTER` = 1, {scr} first, then {so}"),
        PassageO(f"o-{h}-lot-dev", c, "one dev per LOT: of the plan — Claude Code: in ONE message",
                 "elsewhere: in series", "per wave of at most `PEUT_AJOUTER` (`charge_poste.py verdict`);"),
        PassageO(f"o-{h}-statut", c, CLAUDE_P, "- **any other host", _APRES_MEASURED),
        PassageO(f"o-{h}-shards", c, "Throughput via MAXIMAL fan-out", "State the wave layout.",
                 ", in waves of at most the `PEUT_AJOUTER` of `charge_poste.py verdict`:"),
        PassageO(f"o-{h}-hard-rule", c, "Fan out independent subagents in parallel —",
                 "token cost is never a reason to sequence", _EN_VAGUE),
    )


PASSAGES_O: tuple[PassageO, ...] = (
    *(p for h, c in _MD_DEFS.items() for p in _passages_md(h, c)),
    PassageO("o-codex-shards", _CODEX, "emit a SHARDED PLAN", "plus a final RECONCILE", _C32),
    PassageO("o-codex-statut", _CODEX, "in ONE message, each in its own worktree: MEASURED", "On THIS host",
             _APRES_MEASURED),
    PassageO("o-github-statut", _GITHUB, "in ONE message, each in its own worktree: MEASURED", "On THIS host",
             _APRES_MEASURED),
    PassageO("o-github-shards", _GITHUB, "emit a SHARDED PLAN", "plus a final RECONCILE", _C32),
    PassageO("o-task-board-point3", _TASK_BOARD, "les devs indépendants partent dans UN seul message", "(4)",
             _PAR_VAGUE),
    PassageO("o-gemini-md-full-power", "GEMINI.md", "Full power made concrete: launch independent agents in parallel",
             "run any stage", f", {_EN_VAGUE};"),
    PassageO("o-table-hotes-commande", TABLE, "lance les devs d'une fournée en un seul message",
             "Tout autre statut", _PAR_VAGUE),
)
# Les phrases d'avant (base 60c75321), NON qualifiées : absentes depuis le lot O.
_ABSENT_MD = ("Claude Code: all in ONE message;", "in parallel — in one message —", "MAXIMAL fan-out: run every")
_ABSENT_STATUT = ("as wide as independence allows", "worktree: MEASURED. On THIS host")  # C32
ABSENT_O: dict[str, tuple[str, ...]] = {
    **{c: (*_ABSENT_MD, f"in parallel with {_nom(h, 'security-code-review')} (both read-only)")
       for h, c in _MD_DEFS.items()},
    _CODEX: _ABSENT_STATUT, _GITHUB: _ABSENT_STATUT,
    _TASK_BOARD: ("partent dans UN seul message. (4)",), "GEMINI.md": ("launch independent agents in parallel; run",),
    TABLE: ("en un seul message. Tout autre statut",),
}
# Repliés en casse : « one message » compte ; « in parallel with » : la porte de sécurité (C30).
NUS_O = ("ONE message", "UN seul message", "MAXIMAL fan-out", "in parallel with")


def _tranche_o(plat: str, p: PassageO) -> str | None:
    debut, fin = _plat(p.debut, True), _plat(p.fin, True)
    if plat.count(debut) != 1:
        return None
    i = plat.find(debut)
    j = plat.find(fin, i + len(debut))
    return None if j < 0 else plat[i:j]


def faute_jeton_o(p: PassageO) -> str:
    return f"{p.chemin} [{p.ident}] : qualificatif absent « {_plat(p.jeton, True)} »"


def _nus_non_qualifies(plie: str) -> list[tuple[str, int]]:
    """(jeton nu, position) de chaque occurrence, dans un texte DÉJÀ plié (blancs et casse), sans
    `PEUT_AJOUTER` entier dans les FENETRE_O caractères qui la suivent."""
    return [(nu, m.start()) for nu in NUS_O for m in re.finditer(re.escape(nu.casefold()), plie)
            if QUALIF_O.casefold() not in plie[m.end(): m.end() + FENETRE_O]]


def fautes_non_qualifie(chemin: str, texte: str) -> list[str]:
    """Chaque jeton nu d'A1, plié en casse, porte `PEUT_AJOUTER` dans les FENETRE_O caractères qui suivent."""
    return [f"{chemin} : « {nu} » non qualifié — sans `{QUALIF_O}` dans les {FENETRE_O} caractères qui suivent"
            for nu, _ in _nus_non_qualifies(_plat(texte, False))]


def fautes_o(chemin: str, texte: str) -> list[str]:
    """(j) sur UNE surface de O : ses passages, ses absences, ses jetons nus. Vide : le seul vert."""
    plat = _plat(texte, True)
    fautes: list[str] = []
    for p in (p for p in PASSAGES_O if p.chemin == chemin):
        tr = _tranche_o(plat, p)
        if tr is None:
            fautes.append(f"{chemin} [{p.ident}] : passage introuvable ou ambigu (« {p.debut} » … « {p.fin} »)")
        elif _plat(p.jeton, True) not in tr:
            fautes.append(faute_jeton_o(p))
    fautes += [f"{chemin} : phrase d'avant revenue « {ph} »" for ph in ABSENT_O[chemin] if _plat(ph, True) in plat]
    return fautes + fautes_non_qualifie(chemin, texte)


def _texte_o_vert(chemin: str) -> str:
    texte = lire(chemin)
    assert fautes_o(chemin, texte) == [], f"{chemin} : base (j) rouge"
    return texte


CAS_ABSENT_O = [(c, ph) for c, phs in ABSENT_O.items() for ph in phs]


def test_o_non_vacuite_et_piege_1() -> None:
    assert len(set(SURFACES_O.values())) == len(SURFACES_O) == 8, "les huit surfaces du lot O, chacune une fois"
    assert not set(SURFACES_O.values()) & HORS_O, "PIÈGE 1 : une surface d'un autre lot lue par (j)"
    assert {p.chemin for p in PASSAGES_O} == set(SURFACES_O.values()), "une surface de O sans passage tenu"
    assert set(ABSENT_O) == set(SURFACES_O.values()), "une surface de O sans témoin d'absence"
    assert len({p.ident for p in PASSAGES_O}) == len(PASSAGES_O) == 22, "identifiants de passage"
    filtre = ("kickoff", "skill", "agents_md", "copilot", "planning")  # le filtre des lots D, plus haut
    assert not any(m in i for i in (*SURFACES_O, *(p.ident for p in PASSAGES_O)) for m in filtre)
    tout = " ".join(_plat(lire(c), False) for c in SURFACES_O.values())
    for nu in NUS_O:
        assert nu.casefold() in tout, f"« {nu} » absent des surfaces de O : le témoin nu n'y mesure rien"


@pytest.mark.parametrize("chemin", list(SURFACES_O.values()), ids=list(SURFACES_O))
def test_o_surface_verte(chemin: str) -> None:
    fautes = fautes_o(chemin, lire(chemin))
    assert fautes == [], "\n".join(fautes)


@pytest.mark.parametrize("p", PASSAGES_O, ids=[p.ident for p in PASSAGES_O])
def test_o_mutant_qualificatif_retire(p: PassageO) -> None:
    """Le qualificatif retiré de SON passage : rouge sur CE passage seul (les autres restent verts)."""
    plat = _plat(_texte_o_vert(p.chemin), True)
    tr = _tranche_o(plat, p)
    assert tr is not None
    mutant = plat.replace(tr, tr.replace(_plat(p.jeton, True), " "), 1)
    assert mutant != plat, f"{p.ident} : le mutant n'a rien changé — il ne mesure rien"
    fautes = fautes_o(p.chemin, mutant)
    assert faute_jeton_o(p) in fautes, f"{p.ident} : retirer le qualificatif ne rougit pas"
    autres = [f for f in fautes if "[" in f and f"[{p.ident}]" not in f]
    assert autres == [], f"{p.ident} : le mutant rougit un AUTRE passage\n" + "\n".join(autres)


@pytest.mark.parametrize("p", PASSAGES_O, ids=[p.ident for p in PASSAGES_O])
def test_o_mutant_jeton_garde_touche(p: PassageO) -> None:
    """C35 : le jeton d'A1 réécrit (son dernier mot remplacé, qualificatif À SA PLACE) ou dédoublé : rouge."""
    plat = _plat(_texte_o_vert(p.chemin), True)
    debut = _plat(p.debut, True)
    garde, _, dernier = debut.rpartition(" ")
    remplace = plat.replace(debut, f"{garde} by-wave", 1)
    assert remplace != plat and dernier != "by-wave"
    assert any(f"[{p.ident}] : passage introuvable" in f for f in fautes_o(p.chemin, remplace)), p.ident
    double = plat + " " + debut
    assert any(f"[{p.ident}] : passage introuvable ou ambigu" in f for f in fautes_o(p.chemin, double)), p.ident


@pytest.mark.parametrize(("chemin", "phrase"), CAS_ABSENT_O, ids=[f"o-absent-{i}" for i in range(len(CAS_ABSENT_O))])
def test_o_mutant_phrase_d_avant_reinjectee(chemin: str, phrase: str) -> None:
    mutant = _texte_o_vert(chemin) + "\n\n" + phrase + "\n"
    assert f"{chemin} : phrase d'avant revenue « {phrase} »" in fautes_o(chemin, mutant), phrase


@pytest.mark.parametrize("chemin", list(SURFACES_O.values()), ids=list(SURFACES_O))
@pytest.mark.parametrize("nu", NUS_O, ids=["one-message", "un-seul-message", "maximal-fan-out", "in-parallel-with"])
def test_o_mutant_jeton_nu_ajoute(chemin: str, nu: str) -> None:
    """Un jeton nu d'A1 ajouté sans qualificatif, sur chaque surface de O : rouge."""
    mutant = _texte_o_vert(chemin) + "\n\n" + f"Les devs partent en {nu}, tous ensemble.\n" + "x" * FENETRE_O
    assert any(f"« {nu} » non qualifié" in f for f in fautes_o(chemin, mutant)), f"{chemin} : « {nu} » nu passe"


@pytest.mark.parametrize("chemin", list(SURFACES_O.values()), ids=list(SURFACES_O))
def test_o_mutant_fenetre_epinglee(chemin: str) -> None:
    """FENETRE_O épinglée à 120 sur le texte RÉEL : un « ONE message » nu inséré 109 caractères AVANT le
    premier `PEUT_AJOUTER` réel de la surface rougit, à 108 il est qualifié — jugé à SA position, les
    jetons repoussés par l'insertion ne comptent pas. Écarts en dur : 10**6, 119 ou 121 rougissent ici."""
    plie = _plat(_texte_o_vert(chemin), False)
    i = plie.find(QUALIF_O.casefold())
    assert i >= 0, f"{chemin} : aucun `{QUALIF_O}` réel — le cas ne mesurerait rien"
    for ecart, rouge in ((109, True), (108, False)):
        mutant = plie[:i] + "one message" + "x" * ecart + plie[i:]
        vu = ("ONE message", i) in _nus_non_qualifies(mutant)
        assert vu is rouge, f"{chemin} : « ONE message » à {ecart} caractères d'un `{QUALIF_O}` réel " + (
            "passe pour qualifié — la fenêtre s'est élargie" if rouge else "rougit — la fenêtre s'est rétrécie")


def test_o_controle_synthetique_non_qualifie() -> None:
    assert fautes_non_qualifie("s", "in ONE message per wave of at most `PEUT_AJOUTER`") == []
    assert fautes_non_qualifie("s", "un seul\n  message, au plus le `PEUT_AJOUTER`") == [], "blancs pliés"
    # Écarts écrits EN DUR (jamais dérivés de FENETRE_O) : le mot de 12 lettres entre en entier à 108, pas à 109.
    assert fautes_non_qualifie("s", "ONE message" + "x" * 109 + "PEUT_AJOUTER"), "hors fenêtre : 109"
    assert fautes_non_qualifie("s", "ONE message" + "x" * 108 + "PEUT_AJOUTER") == [], "dans la fenêtre : 108"
    assert fautes_non_qualifie("s", "MAXIMAL fan-out: run every shard"), "nu"
    assert len(fautes_non_qualifie("s", "one message PEUT_AJOUTER ; UN seul message.")) == 1, "chaque occurrence"


# ---------------------------------------------------------------------------
# (k) Plusieurs running et portée de revue déclarée (lot G de T-01M5DBFPWCXH54VW0VMN8HWRX7,
# T-01M5F7291DQKB16882AM93DWJ5 ; décisions S-01M5DBTHMEAEXGD93Q284GJPJE, S-01M5E50AJX9V9AP8A8VBBHS6B4,
# S-01M5E50ABADJA72966YQF4J285). Chaque lanceur déclare `tasks.py review-scope` JUSTE AVANT chaque
# critique de clôture : l'appel est lu DANS la tranche de chaque site (début UNIQUE, blancs pliés),
# jamais n'importe où dans le fichier. Borne : un JETON dans une tranche, pas l'ordre « déclarer
# puis lancer » ; un site de critique hors de cette liste fermée n'est pas vu.
# ---------------------------------------------------------------------------
APPEL_PORTEE = "tasks.py review-scope"
#: G-S1 (avis sécurité) : chaque membre déclaré figure au brief du critique avec son diff.
BRIEF = "appears in the critic's brief with its diff"
#: G-K4 : la trace propre antérieure à la déclaration est écartée (`binome_creditables`, `quand < borne`).
PRECEDE = "its own trace is set aside if it predates the declaration"
#: (surface, site) -> (début UNIQUE, fin, jetons exigés dans la tranche).
SITES_PORTEE: dict[tuple[str, str], tuple[str, str, tuple[str, ...]]] = {
    ("kickoff_skill", "cadrage"): ("close with ONE global closing review WHILE the last child is `running`",
                                   "THEN the last child", (APPEL_PORTEE, "still `running`: no `start` demotes them",
                                                           "never borrowed through the chantier", BRIEF)),
    ("kickoff_skill", "pipeline"): ("9. indexer if structure changed", "11. route the findings", (APPEL_PORTEE,)),
    ("kickoff_skill", "matin"): ("3bis-morning.", "4. Invoke `language-detector`", (APPEL_PORTEE,)),
    ("kickoff_skill", "r3"): ("(d) at GO or GO_AVEC_RESERVES", "(e) at NO_GO", (APPEL_PORTEE,)),
    ("kickoff_skill", "cloture"): ("Then run the **closing review", "Where `done` refuses although the critic ran",
                                   (APPEL_PORTEE, "JUST BEFORE launching it", "never the chantier", BRIEF,
                                    "credits nothing either", "its `at` is unreadable", PRECEDE)),
    ("kickoff_skill", "livraison"): ("- (7) The closing critic", "- (8)", (APPEL_PORTEE, BRIEF)),
    ("kickoff_skill", "directe"): ("takes the DIRECT path only once", "A refusal lists all", (APPEL_PORTEE,)),
    ("kickoff_cmd", "matin"): ("3bis-matin.", "3ter.", (APPEL_PORTEE,)),
    ("kickoff_cmd", "r3"): ("(d) at GO or GO_AVEC_RESERVES", "(e) at NO_GO", (APPEL_PORTEE,)),
    ("kickoff_cmd", "cloture"): ("Then run the **closing review", "Where `done` refuses although the critic ran",
                                 (APPEL_PORTEE, "JUST BEFORE launching it", "never the chantier", BRIEF,
                                  "credits nothing either", "its `at` is unreadable", PRECEDE)),
    # G-K3 : la clause du brief au site de la découpe (parent, lots, enfants nommés) de kickoff.md.
    ("kickoff_cmd", "cadrage"): ("tasks.py review-scope <T> [<lots…>]`",
                                 "so declare first, then launch",
                                 (APPEL_PORTEE, "parent, lots, children named, never inferred", BRIEF,
                                  "a new declaration voids the traces dated before it")),
    ("kickoff_cmd", "livraison"): ("(7) the closing critic", "(8) fixes", (APPEL_PORTEE, BRIEF)),
    ("kickoff_cmd", "directe"): ("**DIRECT path", "**Refused**", (APPEL_PORTEE,)),
    ("agents_md", "task_tracking"): ("- **Task tracking** —", "→ détail : `.agents/skills/task-board/SKILL.md`",
                                     (APPEL_PORTEE, "Plusieurs `running` coexistent", "aucun `start` ne rétrograde",
                                      "une session active par clone")),
    ("task_board_skill", "trace"): ("**LA TRACE S'ÉCRIT SUR LES MEMBRES DE LA PORTÉE DÉCLARÉE", "**MAIS PLUS INDÉFINIMENT",
                                    (APPEL_PORTEE, "`pending` compris", "on NOMME donc tous les membres revus",
                                     "une trace NON estampillée (ancien traceur) ne crédite plus",
                                     "son `at` est illisible",
                                     "Une tâche hors de toute portée active et de tout groupe déclaré n'emprunte rien")),
    ("task_board_skill", "invariant"): ("**SEVERAL TASKS MAY RUN AT ONCE", "**It is a guard of COHERENCE",
                                        (APPEL_PORTEE, "`start` demotes nobody", "one active session per clone",
                                         "refused naming `review-scope`")),
}
#: Le contrat d'avant (un seul groupe, rétrogradation) : absent du fichier ENTIER.
CONTRAT_AVANT: dict[str, tuple[str, ...]] = {
    "kickoff_skill": ("demotes the slot", "sends EVERY `running` task", "demotes every `running` task OUTSIDE",
                      "leave BOTH running and A's critic traces B", "of the other children from `pending`",
                      # lots B et C : la fournée n'embarque plus une running étrangère ; la trace suit la portée
                      "a neighbouring batch refuse for the same reason", "trace on `running` tasks only",
                      "under a chantier whose slot is `running`",
                      # NO_GO exec-critic sur fe4c3f009 : la trace sur les seules `running`, le membre unique
                      "BORROWS the review at its `done`, through its `livraison` declaration",
                      "keep a single member `running` when the critic stops", "the others borrow its trace",
                      "with no member `running` when the critic stops", "write nothing without a `running`",
                      "scope and say `board illisible`", "borrow the review through this declaration.",
                      # NO_GO exec-critic sur 85de9a54c : la négation absolue de l'emprunt hors portée
                      "gets no trace and borrows nothing", "`aucune portee … aucune trace ecrite` (no active scope)",
                      # G-K4 : `board illisible` rangé sous « seulement pendant un `running` »
                      "`portee consommee -- aucune trace ecrite`, or `board illisible`"),
    "kickoff_cmd": ("demotes the slot", "goes back to `pending`", "leave BOTH running and A's critic traces B",
                    "fait refuser une fournée voisine pour la même raison", "lands on `running` tasks only",
                    "under a chantier whose slot is `running`",
                    "borrows it at its `done` through its `livraison` declaration",
                    "a single member kept `running` when the critic stops", "write nothing without a `running`",
                    "scope and say `board illisible`", "borrow the review through it;",
                    "gets no trace and borrows nothing", "`aucune portee … aucune trace ecrite` (no active scope)",
                    "`portee consommee -- aucune trace ecrite`, or `board illisible`"),
    "task_board_skill": ("`start` still demotes", "not one declared group", "rétrogradée par un `start` hors groupe",
                         "que la rétrogradation préserve", "survit à une rétrogradation",
                         "silently demote the active task", "or the demotion of the running task",
                         "fait refuser une fournée voisine pour la même raison", "du MÊME chantier est alors acceptée",
                         "slot `running` du **même chantier**", "avec ses lots ouverts et les `running` hors fournée",
                         "le hook crédite TOUTES les `running` :", "à condition de porter le MÊME chantier non vide",
                         "LA TRACE S'ÉCRIT SUR LA TÂCHE QUI TOURNE", "Une tâche sans chantier n'emprunte rien",
                         "exactement comme l'emprunt de binôme", "n'écrit de trace que sur les tâches `running`",
                         "voie 2, sinon : UN membre `running`", "un critique crédite TOUTES les tâches `running`",
                         "aucun membre `running` à l'arrêt du critique → aucune trace",
                         "n'a aucune trace à lui et n'emprunte que dans la même portée",
                         "un membre hors portée n'emprunte rien", "un membre hors portée n'a aucune trace et n'emprunte rien"),
    "agents_md": ("le slot de son chantier",),
}
#: La règle d'emprunt d'un membre HORS portée (voie 1 : par le groupe déclaré seul), lue dans sa tranche.
EMPRUNT_EN = "it borrows only through a declared `parallel` group, from a `running` member of that group covered by the scope"
EMPRUNT_FR = "il n'emprunte que par un groupe `parallel` déclaré, à un `running` de ce groupe couvert par la portée"
EMPRUNT: dict[str, tuple[str, str, str]] = {
    "kickoff_skill": ("- (6) The trace.", "- (7) The closing critic", EMPRUNT_EN),
    "kickoff_cmd": ("(6) the critic's trace lands", "(7) the closing critic", EMPRUNT_EN),
    "task_board_skill": ("**Le hook suit la portée**", "**Le critique et `<L>`**", EMPRUNT_FR),
}
#: L'ORDRE « déclarer puis lancer » : depuis le PREMIER appel de la tranche, un qualificatif d'antériorité
#: puis la mention du lancement du critique, à courte distance (blancs pliés, casse repliée).
ORDRE_PORTEE = re.compile(re.escape(APPEL_PORTEE.casefold()) + r"[^.;]{0,160}?(?:just before|juste avant|, then)"
                          r".{0,40}?(?:critic|critique|launching it|\bit\b)")
#: Les formes qui renversent l'ordre : absentes de chaque tranche.
ORDRE_INVERSE = ("just after", "once the critic has returned", "after its critic", "after the critic")
#: C18 : la tranche « ALREADY running » … « TRAP: » (et sa jumelle française) reste lisible, début unique.
REMEDE_GARDE = ("kickoff_skill", "kickoff_cmd")
CAS_PORTEE = sorted(SITES_PORTEE)
IDS_PORTEE = [f"{i}-{s}" for i, s in CAS_PORTEE]


def tranche_plate(texte: str, debut: str, fin: str) -> str | None:
    """`tranche` sur le texte blancs pliés (casse gardée) : une ancre coupée sur deux lignes compte."""
    return tranche(_plat(texte, True), _plat(debut, True), _plat(fin, True))


def fautes_portee(ident: str, texte: str) -> list[str]:
    """(k) sur UNE surface : chaque site porte ses jetons, le contrat d'avant est absent."""
    fautes = []
    for (i, site), (debut, fin, exiges) in SITES_PORTEE.items():
        if i != ident:
            continue
        tr = tranche_plate(texte, debut, fin)
        if tr is None:
            fautes.append(f"{ident}/{site} : tranche « {debut} » … « {fin} » introuvable ou ambiguë")
            continue
        fautes += [f"{ident}/{site} : « {j} » absent de la tranche" for j in exiges if _plat(j, True) not in tr]
        plie = tr.casefold()
        if APPEL_PORTEE in tr and not ORDRE_PORTEE.search(plie[plie.find(APPEL_PORTEE.casefold()):]):
            fautes.append(f"{ident}/{site} : ordre — `{APPEL_PORTEE}` non suivi de « just before … critic »")
        fautes += [f"{ident}/{site} : ordre renversé « {j} »" for j in ORDRE_INVERSE if j in plie]
    fautes += [f"{ident} : contrat d'avant « {j} » encore écrit" for j in CONTRAT_AVANT.get(ident, ())
               if present(texte, j, True)]
    if ident in EMPRUNT:
        debut, fin, regle = EMPRUNT[ident]
        tr = tranche_plate(texte, debut, fin)
        if tr is None or _plat(regle, True) not in tr:
            fautes.append(f"{ident}/emprunt : règle « {regle} » absente de « {debut} » … « {fin} »")
    if ident in REMEDE_GARDE and tranche(texte, *REMEDE_R[ident][:2]) is None:
        fautes.append(f"{ident} : tranche du remède « {REMEDE_R[ident][0]} » … « {REMEDE_R[ident][1]} » perdue (C18)")
    return fautes


@pytest.mark.parametrize("ident", sorted({i for i, _ in SITES_PORTEE}))
def test_multi_running_scope(ident: str) -> None:
    """Plusieurs `running`, une session par clone, `review-scope` juste avant chaque critique de clôture."""
    fautes = fautes_portee(ident, lire(PAR_IDENT[ident].chemin))
    assert fautes == [], "\n".join(fautes)


@pytest.mark.parametrize(("ident", "site"), CAS_PORTEE, ids=IDS_PORTEE)
def test_mutant_portee_appel_retire(ident: str, site: str) -> None:
    """Retirer l'appel `review-scope` d'UN site (le reste du fichier intact) rougit ce site."""
    plat = _plat(lire(PAR_IDENT[ident].chemin), True)
    assert fautes_portee(ident, plat) == [], f"{ident} : base rouge"
    debut, fin, _ = SITES_PORTEE[(ident, site)]
    tr = tranche_plate(plat, debut, fin)
    mutant = plat.replace(tr, tr.replace(APPEL_PORTEE, "tasks.py list"), 1)
    assert mutant != plat, f"{ident}/{site} : le mutant n'a rien changé — il ne mesure rien"
    assert any(f.startswith(f"{ident}/{site} :") and APPEL_PORTEE in f for f in fautes_portee(ident, mutant)), (
        f"{ident}/{site} : LA RÈGLE NE MORD PAS sans l'appel `{APPEL_PORTEE}`")


@pytest.mark.parametrize("ident", sorted(EMPRUNT))
def test_mutant_emprunt_hors_portee_nie(ident: str) -> None:
    """La règle d'emprunt par le groupe déclaré, remplacée par la négation absolue, rougit."""
    plat = _plat(lire(PAR_IDENT[ident].chemin), True)
    regle = _plat(EMPRUNT[ident][2], True)
    nie = "a member outside it gets no trace and borrows nothing" if ident != "task_board_skill" else (
        "un membre hors portée n'a aucune trace et n'emprunte rien")
    mutant = plat.replace(regle, nie, 1)
    assert mutant != plat, f"{ident} : le mutant n'a rien changé — il ne mesure rien"
    fautes = fautes_portee(ident, mutant)
    assert any(f.startswith(f"{ident}/emprunt") for f in fautes), f"{ident} : la règle retirée passe"
    assert any("contrat d'avant" in f for f in fautes), f"{ident} : la négation absolue passe"


CAS_BRIEF = [c for c in CAS_PORTEE if BRIEF in SITES_PORTEE[c][2]]


@pytest.mark.parametrize(("ident", "site"), CAS_BRIEF, ids=[f"{i}-{s}" for i, s in CAS_BRIEF])
def test_mutant_portee_brief_retire(ident: str, site: str) -> None:
    """G-S1 : la clause « chaque membre déclaré au brief du critique avec son diff » retirée d'UN site rougit."""
    plat = _plat(lire(PAR_IDENT[ident].chemin), True)
    debut, fin, _ = SITES_PORTEE[(ident, site)]
    tr = tranche_plate(plat, debut, fin)
    mutant = plat.replace(tr, tr.replace(BRIEF, "is named"), 1)
    assert mutant != plat, f"{ident}/{site} : le mutant n'a rien changé — il ne mesure rien"
    assert any(f.startswith(f"{ident}/{site} :") and BRIEF in f for f in fautes_portee(ident, mutant)), (
        f"{ident}/{site} : LA RÈGLE NE MORD PAS sans la clause du brief")


def test_non_vacuite_brief() -> None:
    assert len(CAS_BRIEF) == 6, CAS_BRIEF  # clôture x2, livraison x2, cadrage x2 (G-K3)


@pytest.mark.parametrize("inverse", ("just after", "once the critic has returned,"))
@pytest.mark.parametrize(("ident", "site"), CAS_PORTEE, ids=IDS_PORTEE)
def test_mutant_portee_ordre_renverse(ident: str, site: str, inverse: str) -> None:
    """Le qualificatif d'antériorité du site remplacé par une forme APRÈS le critique rougit ce site."""
    plat = _plat(lire(PAR_IDENT[ident].chemin), True)
    debut, fin, _ = SITES_PORTEE[(ident, site)]
    tr = tranche_plate(plat, debut, fin)
    queue = tr[tr.find(APPEL_PORTEE):]
    m = re.search(r"just before|juste avant|, then", queue, re.IGNORECASE)
    assert m, f"{ident}/{site} : aucun qualificatif d'antériorité — le mutant ne mesurerait rien"
    nouvelle = tr[: tr.find(APPEL_PORTEE)] + queue[: m.start()] + inverse + queue[m.end():]
    mutant = plat.replace(tr, nouvelle, 1)
    assert mutant != plat
    assert any(f.startswith(f"{ident}/{site} : ordre") for f in fautes_portee(ident, mutant)), (
        f"{ident}/{site} : L'ORDRE NE MORD PAS sur « {inverse} »")


@pytest.mark.parametrize(("ident", "jeton"), [(i, j) for i, js in sorted(CONTRAT_AVANT.items()) for j in js])
def test_mutant_contrat_avant_reinjecte(ident: str, jeton: str) -> None:
    """Le contrat d'avant (rétrogradation, groupe unique) recopié en fin de fichier rougit."""
    texte = lire(PAR_IDENT[ident].chemin)
    assert fautes_portee(ident, texte + f"\n\n{jeton}.\n"), f"{ident} : « {jeton} » réinjecté passe"


@pytest.mark.parametrize("ident", REMEDE_GARDE)
def test_mutant_remede_already_running_perdu(ident: str) -> None:
    """C18 : l'ancre « ALREADY running » / « TOURNE déjà » doublée rend la tranche ambiguë — rouge."""
    texte = lire(PAR_IDENT[ident].chemin)
    assert fautes_portee(ident, texte + f"\n{REMEDE_R[ident][0]}\n"), f"{ident} : ancre doublée passe"


# ---------------------------------------------------------------------------
# (k bis) TÉMOINS POSITIFS de la correction de clôture du lot G (G-K1, G-K4) : chaque
# affirmation corrigée est LUE dans sa tranche (pas seulement l'ancienne phrase interdite),
# et ce qu'elle dit du code est RECOUPÉ dans le code — le traceur des ports `.codex` /
# `.gemini` (ordre des deux messages stderr) et `binome_creditables` (exécuté). Borne : le
# traceur est lu comme SOURCE (l'ordre de trois ancres), jamais lancé sur un board.
# ---------------------------------------------------------------------------
SANS_FOCUS_EN = ("a `focus.json` in the clone (a clone from before this code), the old regime holds: an "
                 "unstamped trace credits as is, and the group borrow passes with no scope")
SANS_FOCUS_FR = ("Sans `focus.json` au clone (clone d'avant ce code), l'ancien régime vaut : une trace non "
                 "estampillée crédite telle quelle, et l'emprunt par le groupe passe sans portée")
STDERR_PORTEE = ("only while a task is `running` do they say on stderr `aucune portee`, `portee hors focus` "
                 "or `portee consommee -- aucune trace ecrite`")
STDERR_BOARD = "they say `board illisible` on stderr whether or not a task runs"
_DIAG = ("Then check that the task was an open member of the active scope", "purged it")
HORS_FOCUS = ("Between that declaration and the LAST `done` it covers, no `start`, `fournee` or `focus` on "
              "another task in this clone: each moves the clone's focus, the scope falls out of focus and "
              "every remaining `done` refuses")
REMEDE_FOCUS = "`tasks.py focus <declared focus>` restores it, with no new critic"
FOCUS_AFFICHAGE = ("The DISPLAY focus — what the statusline and the dashboard show — is `focus_task`, the "
                   "first `running` task in store order")
PERTE_DISJONCTION = ("two ungrouped `running` tasks whose write-sets overlap coexist, and `start` only warns "
                     "about them; to be protected, declare a group with `parallel`")
LIEN_REFUS = "is a symbolic link, never followed"
BORNE_LIEN = (f"when `.agents`, `.agents/state` or `.agents/state/local` is a symbolic link, every write verb "
              f"refuses (`… {LIEN_REFUS}`) while reads still follow it; the remedy is to replace the link by a "
              f"real directory holding its target's content")
POSITIFS: dict[tuple[str, str], tuple[str, str, tuple[str, ...]]] = {
    ("kickoff_skill", "diagnostic"): (*_DIAG, (STDERR_PORTEE, STDERR_BOARD)),
    ("kickoff_cmd", "diagnostic"): (*_DIAG, (STDERR_PORTEE, STDERR_BOARD)),
    ("kickoff_skill", "trace"): ("- (6) The trace.", "- (7) The closing critic", (SANS_FOCUS_EN,)),
    ("kickoff_cmd", "trace"): ("(6) the critic's trace lands", "(7) the closing critic", (SANS_FOCUS_EN,)),
    ("task_board_skill", "trace"): ("**LA TRACE S'ÉCRIT SUR LES MEMBRES DE LA PORTÉE DÉCLARÉE",
                                    "**MAIS PLUS INDÉFINIMENT", (SANS_FOCUS_FR,)),
    # G-K1 : le verdict de sécurité d'une directe s'emprunte à un `running` de sa portée ou de son groupe
    # (`tasks_retour.py`, `portee_couvre` / `parallel_group_of`), plus jamais au slot du chantier.
    ("agents_md", "directe"): ("**LA VOIE DIRECTE, ADMISE PAR CODE.**", "**AUCUNE TÂCHE N'EST MARQUÉE TERMINÉE",
                               ("qui lit un `running` de sa portée ou de son groupe et marque l'emprunt",
                                "sur la tâche ou un `running` de sa portée ou de son groupe")),
    # Revue de clôture critic-opus (F1) : un `start`/`fournee`/`focus` après la déclaration met la portée hors focus.
    ("kickoff_skill", "hors_focus"): ("Then run the **closing review", "Where `done` refuses although the critic ran",
                                      (HORS_FOCUS, REMEDE_FOCUS)),
    ("kickoff_cmd", "hors_focus"): ("Then run the **closing review", "Where `done` refuses although the critic ran",
                                    (HORS_FOCUS, REMEDE_FOCUS)),
    # F6 (deux focus, `focus_task` recoupé au code) et F2 (la perte de disjonction au `start`, nommée).
    ("task_board_skill", "invariant"): ("**SEVERAL TASKS MAY RUN AT ONCE", "**It is a guard of COHERENCE",
                                        (FOCUS_AFFICHAGE, "no display reads `focus.json`", PERTE_DISJONCTION)),
    # F4 : `.agents/state` en lien symbolique, recoupé au message de `board_lock`.
    ("task_board_skill", "lien"): ("**It is a guard of COHERENCE", "**Writing a writeset RETRACTS", (BORNE_LIEN,)),
}
CAS_POSITIFS = [(i, s, j) for (i, s), (_, _, js) in sorted(POSITIFS.items()) for j in js]


def fautes_positives(ident: str, texte: str) -> list[str]:
    fautes = []
    for (i, site), (debut, fin, exiges) in POSITIFS.items():
        if i != ident:
            continue
        tr = tranche_plate(texte, debut, fin)
        if tr is None:
            fautes.append(f"{ident}/{site} : tranche « {debut} » … « {fin} » introuvable ou ambiguë")
            continue
        fautes += [f"{ident}/{site} : « {j} » absent" for j in exiges if _plat(j, True) not in tr]
    return fautes


@pytest.mark.parametrize("ident", sorted({i for i, _ in POSITIFS}))
def test_positifs_lot_g(ident: str) -> None:
    fautes = fautes_positives(ident, lire(PAR_IDENT[ident].chemin))
    assert fautes == [], "\n".join(fautes)


@pytest.mark.parametrize(("ident", "site", "jeton"), CAS_POSITIFS,
                         ids=[f"{i}-{s}-{n}" for n, (i, s, _) in enumerate(CAS_POSITIFS)])
def test_mutant_positif_retire(ident: str, site: str, jeton: str) -> None:
    """L'affirmation corrigée retirée de SA tranche (le reste du fichier intact) rougit."""
    plat = _plat(lire(PAR_IDENT[ident].chemin), True)
    tr = tranche_plate(plat, *POSITIFS[(ident, site)][:2])
    assert tr is not None, f"{ident}/{site} : tranche perdue"
    mutant = plat.replace(tr, tr.replace(_plat(jeton, True), "", 1), 1)
    assert mutant != plat, f"{ident}/{site} : le mutant n'a rien changé — il ne mesure rien"
    assert any(f.startswith(f"{ident}/{site} :") for f in fautes_positives(ident, mutant))


TRACEURS = (".codex/hooks/binome_trace.py", ".gemini/hooks/binome_trace.py")
#: Les trois ancres du traceur, dans CET ordre : `board illisible` dit AVANT (donc hors) du test
#: « une `running` existe », le motif de portée dit SOUS lui.
ANCRES_TRACEUR = ("binome_trace: board illisible (", 'if any(t.get("state") == "running" for t in lignes):',
                  "{motif or 'portee consommee'} -- aucune trace ecrite")


def fautes_traceur(src: str) -> list[str]:
    fautes = [f"motif {m} absent" for m in ('"aucune portee"', '"portee hors focus"', "'portee consommee'")
              if m not in src]
    pos = [src.find(a) for a in ANCRES_TRACEUR]
    if min(pos) < 0 or pos != sorted(pos):
        fautes.append(f"ordre board illisible < running < motif de portée rompu : {pos}")
    return fautes


@pytest.mark.parametrize("chemin", TRACEURS)
def test_traceur_tient_la_doctrine(chemin: str) -> None:
    """STDERR_PORTEE et STDERR_BOARD disent ce que le traceur FAIT."""
    src = lire(chemin)
    assert fautes_traceur(src) == [], fautes_traceur(src)
    mutant = src.replace(ANCRES_TRACEUR[1], "if True:", 1)
    assert mutant != src and fautes_traceur(mutant), f"{chemin} : le motif hors `running` passe"


@lru_cache(maxsize=1)
def _tasks() -> object:
    """`tasks.py` (qui monte `tasks_gardes.py`), importé une fois, `.agents/bin` en tête du chemin."""
    bin_ = str(ROOT / ".agents" / "bin")
    if bin_ not in sys.path:
        sys.path.insert(0, bin_)
    import importlib
    return importlib.import_module("tasks")


TRACE_NUE = {"critic-opus": {"sha": "abc", "at": "2026-10-21T10:00:00Z"}}


def test_code_focus_affichage_premier_running() -> None:
    """FOCUS_AFFICHAGE : `focus_task` rend la PREMIÈRE running du store, sans lire `focus.json`."""
    taches = [{"id": "T-1", "state": "pending"}, {"id": "T-2", "state": "running"}, {"id": "T-3", "state": "running"}]
    assert _tasks().focus_task(taches)["id"] == "T-2"
    assert "focus.json" not in inspect.getsource(_tasks().focus_task).replace("``tasks.py focus``", "")


def test_code_lien_refuse_au_verrou(tmp_path) -> None:
    """BORNE_LIEN : `.agents/state` en lien symbolique, le verrou d'écriture refuse avec LIEN_REFUS."""
    cible = tmp_path / "ailleurs"
    (cible / "local").mkdir(parents=True)
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "state").symlink_to(cible, target_is_directory=True)
    with pytest.raises(_tasks().BoardError, match=re.escape(LIEN_REFUS)):
        with _tasks().board_lock(str(tmp_path)):
            pass


def test_code_sans_focus_ancien_regime() -> None:
    """SANS_FOCUS_* : sans focus, la trace non estampillée crédite, hors portée (le groupe compris) ;
    sous focus sans portée couvrante, elle ne crédite rien."""
    cred = _tasks().binome_creditables
    assert cred(TRACE_NUE, "T-1", None, focus=False) == TRACE_NUE
    assert cred(TRACE_NUE, "T-1", None, focus=True) == {}


def test_code_trace_precede_declaration() -> None:
    """PRECEDE : sous une portée qui couvre la tâche, sa trace propre datée AVANT la déclaration est écartée."""
    cred = _tasks().binome_creditables
    portee = {"focus": "T-1", "declared_at": "2026-10-21T11:00:00.123Z", "members": ["T-1"], "consumed": []}
    assert cred(TRACE_NUE, "T-1", portee, focus=True, propre=True) == {}
    apres = {"critic-opus": {"sha": "abc", "at": "2026-10-21T11:00:05Z"}}
    assert cred(apres, "T-1", portee, focus=True, propre=True) == apres
