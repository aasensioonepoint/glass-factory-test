"""Témoin du lot P de T-01M4XZWZ9C0ZFVXN3MFSFY1G5V : la planification, README-CLAUDE et README
partent par VAGUES sous le verdict de `charge_poste.py` (décision pilote S-01M4Y10HZ6Y0TAXNNK0S1VRFC1).

Le banc lit le TEXTE prescrit (plan r7, étape 6 ; qualificatifs recopiés de l'annexe A3) et
n'importe JAMAIS l'outil `charge_poste.py`, écrit par le lot T en parallèle.

(a) PRÉSENCE : chaque passage — deux ancres, celle de début UNIQUE, blancs pliés — porte ses
    jetons ; un jeton retiré du passage rougit sur CE jeton seul (mutant par jeton).
(b) ABSENCE : les phrases d'avant, non qualifiées (« Unbounded parallel fan-out », « in the same
    message », « in a single message », « fan out in parallel, and depth »…), ne reviennent
    pas ; réinjectée, chacune rougit. Depuis la base à cinq (T-01M54B1SXM557Z86N1TXEJSRDE,
    décision pilote S-01M54B1KQ6SVNCA9ZSRPWHCCFP), les formes « trois » de la base d'avant
    (« première vague au plus trois », « trois moins les agents actifs », `max(0, 3 − ACTIFS)`,
    « first wave at most three », « three minus the active agents ») non plus.
(c) C35 : le jeton GARDÉ « parallel fan-out » (README-CLAUDE § Full power) reste mot pour mot,
    son qualificatif APRÈS lui, jamais à sa place.
(d) C34 : aucun « <chiffre> agents » dans un passage — le motif de `host_sync.test.sh`
    (`MOTIF_COMPTAGE`), recopié ici et confronté au script quand il est présent ; les nombres
    du verdict s'écrivent en lettres (« au plus cinq », « at most five »).
(e) PEUT_AJOUTER=0 (majeur de l'exec-critic sur 80a01b4e) : planning ET planning-all attendent
    par `verdict --attendre 540` avec `timeout: 600000` dans la MÊME phrase (C33), illisible ou
    tuée ⇒ `max(0, 5 − ACTIFS)`, au plus trois attentes à 0 puis départ en série et COVERAGE
    DEGRADED dit — jamais « attendre un retour » seul, inexécutable à ACTIFS=0.
(f) Lot C de T-01M56Q23NHTEXES5CAT0A03TFJ (plan r14, étape 6 ; décision pilote
    S-01M59PGM83GXXV8ZNGQ8NZFH9T) : la première vague vaut `BASE`, puis, sous 2C/3, tout le
    `LIBRE` sans délai, `TENU` des autres appelants et accords propres de moins de 300 s
    déduits ; la cadence abolie (« au plus deux de plus par mesure », « une mesure accordée
    au plus toutes les 5 min », « at most two more per measure »…) ne revient pas, et l'appel
    `scriptPath` du lanceur voyageur reste dans README-CLAUDE.

BORNE : le banc tient les passages NOMMÉS ci-dessous, pas toute phrase de parallélisme des
quatre fichiers ; un passage dont l'ancre manque ou se dédouble est un ÉCHEC, jamais un vide
qui passe (L-00000186).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pytest

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import EST_LE_KIT, readme_du_kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

PLANNING = ".agents/skills/planning/SKILL.md"
PLANNING_ALL = ".agents/skills/planning-all/SKILL.md"
README = "README.md"
README_CLAUDE = "README-CLAUDE.md"
SURFACES = (PLANNING, PLANNING_ALL, README, README_CLAUDE)
HOST_SYNC = "core-scripts/host_sync.test.sh"

# C34 — recopié de `host_sync.test.sh` (`MOTIF_COMPTAGE=`), confronté au script par
# `test_motif_comptage_aligne_sur_host_sync` : un script qui bouge fait rougir la copie.
MOTIF_COMPTAGE = "[0-9]+ (specialized |role-scoped )?(agents|subagents)"


# (e) Le cas PEUT_AJOUTER=0 (majeur de l'exec-critic sur 80a01b4e : « attendre un retour » était
# inexécutable à ACTIFS=0) — la même règle que kickoff (lot K), dans planning ET planning-all.
# Jetons DISJOINTS deux à deux et des autres jetons du passage : un mutant n'en retire qu'un.
ATTENTE_A_ZERO: tuple[str, ...] = (
    "à `PEUT_AJOUTER=0` avec des plans restants, attendre DANS LE TOUR",
    "charge_poste.py verdict --actifs <n> --attendre 540",
    "puis appliquer le verdict qu'elle rend",
    "ou commande tuée",
    "cinq moins les agents actifs",
    "`max(0, 5 − ACTIFS)`",
    "au plus TROIS attentes de suite rendues à 0",
    "puis départ EN SÉRIE — un agent à la fois",
    "`COVERAGE DEGRADED — poste surchargé après trois attentes : plans un à un`",
)
# C33 : toute phrase qui cite `--attendre` porte le timeout Bash dans la MÊME phrase.
ATTENDRE = "--attendre"
TIMEOUT = "timeout: 600000"
ATTENTE_SURFACES = (PLANNING, PLANNING_ALL)  # non-vacuité : chacune cite `--attendre` au moins une fois


@dataclass(frozen=True)
class Passage:
    ident: str
    chemin: str
    debut: str
    fin: str
    jetons: tuple[str, ...]


PASSAGES: tuple[Passage, ...] = (
    Passage("planning-etape2", PLANNING, "Les tâches se parallélisent entre elles",
            "**Plafond du critique de plan**", (
                "par vagues sous le verdict du poste",
                "charge_poste.py verdict --actifs <n>` avant CHAQUE vague",
                "un message par vague d'au plus son `PEUT_AJOUTER`",
                # (f) Lot C de T-01M56Q23NH : BASE d'abord, puis LIBRE sans délai sous 2C/3, TENU déduit.
                "la première vague (`--actifs 0`) reçoit au plus `BASE`",
                "jusqu'à la moitié des cœurs, soit neuf sur 18 cœurs",
                "charges 1 et 5 min sous C/4",
                "jamais au-dessus du plafond",
                "sous 2C/3, tout le `LIBRE` = `PLAFOND − ACTIFS − TENU` sans délai entre accords",
                "limite de deux",
                "où `TENU` retient les places des autres appelants",
                "accords de moins de 300 s",
                # Clôture (S-01M5BSJ7PBQD79HMY19BSSBGH2) : l'accord d'une autre session, 300 s,
                # ou une heure à ACTIFS = 0.
                "une heure pour un accord donné à `ACTIFS = 0`",
                "et les accords propres de moins de 300 s pas encore comptés dans `ACTIFS`",
                *ATTENTE_A_ZERO,
                "le suivant au retour du précédent",
                "jamais la dernière valeur connue",
            )),
    Passage("planning-full-power", PLANNING, "### § Full power (parallelism, workflows, ultra)",
            "- Three things never parallelize", (
                "Ajout hors instantané (T-01M4XZWZ9C",
                "S-01M4Y10HZ6Y0TAXNNK0S1VRFC1",
                "charge_poste.py verdict --actifs <n>",
                "un message par vague d'au plus son `PEUT_AJOUTER`",
                "première vague au plus `BASE`",
                "jusqu'à la moitié des cœurs au repos",
                "puis, sous 2C/3, tout le `LIBRE` sans délai",
                "`TENU` des autres appelants et accords propres de moins de 300 s déduits",
                "cinq moins les agents actifs",
            )),
    Passage("planning-entete-instantane", PLANNING, "Instantané mot pour mot de", "; l'original", (
                "les ajouts hors instantané T-01M4V7QQ6F et T-01M4XZWZ9C",
            )),
    Passage("planning-all-vague", PLANNING_ALL,
            "Les tâches d'une **même vague** se planifient en parallèle", "Puis, pour chaque plan", (
                "sous le verdict du poste",
                "charge_poste.py verdict --actifs <n>` avant CHAQUE lancement",
                "un message par lancement d'au plus son `PEUT_AJOUTER`",
                "plusieurs lancements",
                *ATTENTE_A_ZERO,
            )),
    # QUATRE jetons, ni plus ni moins : `test_adopting_gate.py` (NOEUDS_B3C) épingle les nœuds
    # `readme-agents-0` à `readme-agents-3`.
    Passage("readme-agents", README, "## 1. The agents", "| Agent |", (
                "independent agents fan out in parallel, in waves of at most the `PEUT_AJOUTER` of "
                "`charge_poste.py verdict`",
                "first wave at most `BASE` — five, up to half the cores on an idle station, never above the ceiling",
                "below 2C/3, all the `LIBRE` room at once, net of the `TENU` seats other callers hold "
                "and its own grants under 300 s not yet active",
                "a ceiling the tool calibrates by itself",
            )),
    Passage("readme-claude-glance", README_CLAUDE, "## The agents at a glance", "| Agent |", (
                "independent agents fan out in parallel, in waves of at most the `PEUT_AJOUTER` of "
                "`charge_poste.py verdict`",
            )),
    Passage("readme-claude-full-power", README_CLAUDE, "## Full power, clean context — baked in",
            "- **Index-first reads**", (
                "parallel fan-out (by waves under the station verdict, `charge_poste.py verdict`)",
                "**Parallel fan-out by waves under the station verdict**",
                "one message per wave, at most the `PEUT_AJOUTER` of "
                "`bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>`",
                "first wave at most `BASE` — five, up to half the cores on an idle station, never above the ceiling",
                "below 2C/3, all the `LIBRE` room at once, net of the `TENU` seats other callers hold",
                "(agents of live sessions under one hour, grants under 300 s, "
                "one hour for a grant given at `ACTIFS = 0`)",
                "and its own grants under 300 s not yet active",
                "no readable `PLAFOND=` line: five minus the active agents",
            )),
    # (f) L'appel du lanceur voyageur (scriptPath), jamais l'archive : plan r14, étape 6.
    Passage("readme-claude-lanceur", README_CLAUDE, "Batch launcher, the kit's own and travelling",
            "and JSON `args`", (
                "call the Workflow tool with `scriptPath: .claude/workflows/workflow-fournee.js`",
            )),
    Passage("readme-claude-sca", README_CLAUDE, "`security-orchestrator` fans out",
            "consolidates one GO/NO-GO", (
                "in waves of at most the `budget` the calling session passes",
                "(no budget given: one specialist at a time)",
            )),
    Passage("readme-claude-specifics", README_CLAUDE, "- Full power made concrete:",
            "never downgrade to save tokens", (
                "launch independent subagents in parallel, one message per wave of at most `PEUT_AJOUTER` "
                "(`charge_poste.py verdict`)",
            )),
)

# (b) Les phrases d'avant, NON qualifiées : présentes sur la base 6687317e, absentes depuis le lot P.
ABSENT: dict[str, tuple[str, ...]] = {
    PLANNING: ("Les tâches se parallélisent entre elles (lecture seule, aucun conflit possible).",),
    PLANNING_ALL: ("se planifient en parallèle — la planification est en lecture seule",),
    README: ("independent agents fan out in parallel, and depth is never rationed",),
    README_CLAUDE: (
        "independent agents fan out in parallel, and depth is never rationed",
        "parallel fan-out, workflows, and the strongest models",
        "Unbounded parallel fan-out",
        "every independent subagent launches in the same message",
        "generalist fallback) in parallel, consolidates",
        "launch independent subagents in parallel in a single message",
    ),
}

# (b) suite — les formes « trois » de la base sans calibration d'avant T-01M54B1SXM557Z86N1TXEJSRDE
# (décision pilote S-01M54B1KQ6SVNCA9ZSRPWHCCFP) : présentes sur 74e261db, absentes depuis le lot B.
# Une fusion qui ressusciterait l'ancienne phrase à côté de la neuve rougit. « TROIS attentes »
# n'en est pas : la borne des attentes reste à trois (`ZEROS_MAX`, hors de ce chantier).
BASE_TROIS: dict[str, tuple[str, ...]] = {
    PLANNING: ("première vague au plus trois", "trois moins les agents actifs", "`max(0, 3 − ACTIFS)`"),
    PLANNING_ALL: ("trois moins les agents actifs", "`max(0, 3 − ACTIFS)`"),
    README: ("first wave at most three",),
    README_CLAUDE: ("first wave at most three", "three minus the active agents"),
}
ABSENT = {chemin: phrases + BASE_TROIS.get(chemin, ()) for chemin, phrases in ABSENT.items()}

# (f) La cadence abolie par S-01M59PGM83GXXV8ZNGQ8NZFH9T (lot C de T-01M56Q23NHTEXES5CAT0A03TFJ) :
# cinq puis deux de plus toutes les 5 min sous C/2. Présente sur 0a111325a, absente depuis le lot C ;
# une fusion qui la ressusciterait à côté de BASE et LIBRE rougit.
_CADENCE_FR = ("première vague au plus cinq", "au plus deux de plus par mesure", "deux de plus par mesure",
               "une mesure accordée au plus toutes les 5 min",
               "tant que la charge 1 min ET 5 min reste sous la moitié des cœurs",
               "min(2, PLAFOND − ACTIFS)")
_CADENCE_EN = ("first wave at most five", "at most two more per measure", "two more per measure",
               "min(2, PLAFOND − ACTIFS)")
CADENCE_ABOLIE: dict[str, tuple[str, ...]] = {
    PLANNING: _CADENCE_FR, PLANNING_ALL: _CADENCE_FR, README: _CADENCE_EN, README_CLAUDE: _CADENCE_EN,
}
ABSENT = {chemin: phrases + CADENCE_ABOLIE.get(chemin, ()) for chemin, phrases in ABSENT.items()}

# (c) C35 : le jeton gardé mot pour mot, et le qualificatif qui le SUIT.
JETON_GARDE = "parallel fan-out"
QUALIFIE_APRES = "parallel fan-out (by waves under the station verdict"


def plat(texte: str) -> str:
    """NFC, blancs pliés : une phrase coupée sur deux lignes compte."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", texte))


def lire(chemin: str) -> str:
    return plat((ROOT / chemin).read_text(encoding="utf-8"))


def tranche(texte: str, debut: str, fin: str) -> str | None:
    """Le texte entre deux ancres (blancs pliés). None si le début manque ou se dédouble,
    ou si la fin manque : l'appelant le traite en ÉCHEC."""
    texte, debut, fin = plat(texte), plat(debut), plat(fin)
    if texte.count(debut) != 1:
        return None
    i = texte.find(debut)
    j = texte.find(fin, i + len(debut))
    return None if j < 0 else texte[i:j]


def faute_jeton(p: Passage, jeton: str) -> str:
    return f"{p.chemin} [{p.ident}] : jeton absent « {plat(jeton)} »"


def faute_absent(chemin: str, phrase: str) -> str:
    return f"{chemin} : phrase non qualifiée revenue « {plat(phrase)} »"


def fautes_passage(p: Passage, texte: str) -> list[str]:
    tr = tranche(texte, p.debut, p.fin)
    if tr is None:
        return [f"{p.chemin} [{p.ident}] : passage introuvable ou ambigu ({p.debut!r} … {p.fin!r})"]
    fautes = [faute_jeton(p, j) for j in p.jetons if plat(j) not in tr]
    fautes += [f"{p.chemin} [{p.ident}] : comptage chiffré « {m.group(0)} » (C34 : en lettres)"
               for m in re.finditer(MOTIF_COMPTAGE, tr, re.IGNORECASE)]
    return fautes


def fautes_absence(chemin: str, texte: str) -> list[str]:
    texte = plat(texte)
    return [faute_absent(chemin, ph) for ph in ABSENT.get(chemin, ()) if plat(ph) in texte]


def phrases(texte: str) -> list[str]:
    """Phrases, blancs pliés : coupure après un point suivi d'un blanc (`pyrun.sh` ne coupe pas)."""
    return re.split(r"(?<=\.)\s+", plat(texte))


def faute_timeout(chemin: str, phrase: str) -> str:
    return f"{chemin} : `{ATTENDRE}` sans `{TIMEOUT}` dans la même phrase (C33) « {phrase[:120]} »"


def fautes_timeout(chemin: str, texte: str) -> list[str]:
    return [faute_timeout(chemin, ph) for ph in phrases(texte) if ATTENDRE in ph and TIMEOUT not in ph]


def fautes(chemin: str, texte: str) -> list[str]:
    """Toutes les fautes d'une surface : ses passages, ses absences, puis C33."""
    sortie: list[str] = []
    for p in PASSAGES:
        if p.chemin == chemin:
            sortie += fautes_passage(p, texte)
    return sortie + fautes_absence(chemin, texte) + fautes_timeout(chemin, texte)


def retirer_du_passage(texte: str, p: Passage, jeton: str) -> str:
    texte = plat(texte)
    tr = tranche(texte, p.debut, p.fin)
    assert tr is not None, f"{p.ident} : base sans passage"
    return texte.replace(tr, tr.replace(plat(jeton), ""), 1)


CAS_JETONS = [(p, j) for p in PASSAGES for j in p.jetons]
CAS_ABSENT = [(c, ph) for c, phrases in ABSENT.items() for ph in phrases]


def readme_hors_objet(chemin: str) -> bool:
    """T-01M54MWW5GH (S-01M54ZQ6WC) : hors du kit, `README.md` réécrit par l'adoptant
    (titre du kit absent, relu ici à chaque cas) n'est pas jugé ; le cas REND sans juger,
    jamais un skip — la collecte ne dépend ni du marqueur ni du README. Dans le kit : jugé."""
    return chemin == README and not EST_LE_KIT and not readme_du_kit()


# ---------------------------------------------------------------------------
# Non-vacuité — aucune égalité au vide
# ---------------------------------------------------------------------------
def test_non_vacuite() -> None:
    jugees = [c for c in SURFACES if not readme_hors_objet(c)]
    assert jugees and all(any(p.chemin == c for p in PASSAGES) for c in jugees), (
        f"surfaces jugées sans passage tenu : {jugees}")
    assert {p.chemin for p in PASSAGES} == set(SURFACES), "une surface du lot P sans passage tenu"
    assert all(p.jetons for p in PASSAGES), "un passage sans jeton ne mesure rien"
    assert set(ABSENT) == set(SURFACES), "une surface du lot P sans témoin d'absence"
    assert set(BASE_TROIS) == set(SURFACES), "une surface sans témoin d'absence de la base à trois"
    assert all(set(BASE_TROIS[c]) <= set(ABSENT[c]) for c in SURFACES), "base à trois non fusionnée"
    assert set(CADENCE_ABOLIE) == set(SURFACES), "une surface sans témoin d'absence de la cadence abolie"
    assert all(set(CADENCE_ABOLIE[c]) <= set(ABSENT[c]) for c in SURFACES), "cadence abolie non fusionnée"
    assert len({p.ident for p in PASSAGES}) == len(PASSAGES), "identifiants de passage dupliqués"


@pytest.mark.parametrize("chemin", SURFACES)
def test_surface_lue_non_vide(chemin: str) -> None:
    if readme_hors_objet(chemin):
        return
    assert (ROOT / chemin).is_file(), f"{chemin} absent"
    assert lire(chemin).strip(), f"{chemin} vide"


# ---------------------------------------------------------------------------
# (a) + (b) + (d) sur l'arbre réel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("chemin", SURFACES)
def test_surface_verte(chemin: str) -> None:
    if readme_hors_objet(chemin):
        return
    trouvees = fautes(chemin, lire(chemin))
    assert trouvees == [], "\n".join(trouvees)


# ---------------------------------------------------------------------------
# (c) C35 — le jeton gardé, qualifié APRÈS
# ---------------------------------------------------------------------------
def test_jeton_garde_parallel_fan_out() -> None:
    texte = lire(README_CLAUDE)
    assert JETON_GARDE in texte, f"C35 : « {JETON_GARDE} » retiré de {README_CLAUDE}"
    assert QUALIFIE_APRES in texte, f"C35 : « {JETON_GARDE} » n'est plus suivi de son qualificatif"


def test_mutant_jeton_garde_remplace() -> None:
    """Le qualificatif mis À LA PLACE du jeton (« by-wave fan-out ») : rouge."""
    mutant = lire(README_CLAUDE).replace(JETON_GARDE + " (", "by-wave fan-out (", 1)
    assert mutant != lire(README_CLAUDE)
    assert QUALIFIE_APRES not in mutant


# ---------------------------------------------------------------------------
# Mutants — un par jeton (rouge sur CE jeton seul), un par phrase d'absence
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("p", "jeton"), CAS_JETONS,
                         ids=[f"{p.ident}-{i}" for p in PASSAGES for i in range(len(p.jetons))])
def test_mutant_jeton_retire(p: Passage, jeton: str) -> None:
    if readme_hors_objet(p.chemin):
        return
    base = lire(p.chemin)
    mutant = retirer_du_passage(base, p, jeton)
    assert mutant != plat(base), f"{p.ident} : le mutant n'a rien changé — il ne mesure rien"
    assert fautes(p.chemin, mutant) == [faute_jeton(p, jeton)], (
        f"{p.ident} : retirer « {jeton} » doit rougir sur CE jeton seul")


@pytest.mark.parametrize(("chemin", "phrase"), CAS_ABSENT,
                         ids=[f"{c}-{i}" for c, phrases in ABSENT.items() for i in range(len(phrases))])
def test_mutant_phrase_non_qualifiee_reinjectee(chemin: str, phrase: str) -> None:
    if readme_hors_objet(chemin):
        return
    mutant = lire(chemin) + "\n\n" + phrase + "\n"
    assert faute_absent(chemin, phrase) in fautes(chemin, mutant), (
        f"{chemin} : « {phrase} » réinjectée ne rougit pas")


@pytest.mark.parametrize("p", PASSAGES, ids=[p.ident for p in PASSAGES])
def test_mutant_ancre_dedoublee(p: Passage) -> None:
    """Une ancre de début dédoublée rend le passage AMBIGU : échec, jamais un vide qui passe."""
    if readme_hors_objet(p.chemin):
        return
    mutant = lire(p.chemin) + "\n\n" + p.debut + "\n"
    assert any("introuvable ou ambigu" in f and p.ident in f for f in fautes(p.chemin, mutant))


@pytest.mark.parametrize("p", PASSAGES, ids=[p.ident for p in PASSAGES])
def test_mutant_comptage_chiffre(p: Passage) -> None:
    """C34 : « 3 agents » glissé dans le passage rougit (les nombres s'écrivent en lettres)."""
    if readme_hors_objet(p.chemin):
        return
    base = lire(p.chemin)
    tr = tranche(base, p.debut, p.fin)
    assert tr is not None
    mutant = plat(base).replace(tr, tr + " 3 agents ", 1)
    assert any("comptage chiffré" in f for f in fautes(p.chemin, mutant))


# ---------------------------------------------------------------------------
# (e) Le cas PEUT_AJOUTER=0 : attente bornée, timeout dans la même phrase (C33)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("chemin", ATTENTE_SURFACES)
def test_non_vacuite_attente(chemin: str) -> None:
    citees = [ph for ph in phrases(lire(chemin)) if ATTENDRE in ph]
    assert citees, f"{chemin} : aucune phrase ne cite `{ATTENDRE}` — la règle C33 n'y mesurerait rien"


@pytest.mark.parametrize("chemin", ATTENTE_SURFACES)
def test_mutant_timeout_retire(chemin: str) -> None:
    base = lire(chemin)
    mutant = base.replace(f"`{TIMEOUT}`", "`timeout`")
    assert mutant != base, f"{chemin} : le mutant n'a rien changé — il ne mesure rien"
    assert fautes_timeout(chemin, mutant), f"{chemin} : `{ATTENDRE}` sans `{TIMEOUT}` ne rougit pas"


@pytest.mark.parametrize("chemin", ATTENTE_SURFACES)
def test_mutant_timeout_dans_une_autre_phrase(chemin: str) -> None:
    """Le timeout repoussé dans la phrase SUIVANTE : rouge — la même phrase, pas le même fichier."""
    base = lire(chemin)
    mutant = base.replace("--attendre 540`, lancée sous", "--attendre 540`. Lancée sous")
    assert mutant != base, f"{chemin} : le mutant n'a rien changé — il ne mesure rien"
    assert TIMEOUT in mutant
    assert fautes_timeout(chemin, mutant), f"{chemin} : un timeout dans une autre phrase passe"


@pytest.mark.parametrize("chemin", ATTENTE_SURFACES)
def test_mutant_attente_non_bornee(chemin: str) -> None:
    """La consigne inexécutable d'avant (« attendre un retour », sans borne) : rouge sur la borne."""
    p = next(x for x in PASSAGES if x.chemin == chemin and "au plus TROIS attentes de suite rendues à 0" in x.jetons)
    mutant = plat(lire(chemin)).replace(plat("au plus TROIS attentes de suite rendues à 0"), "attendre un retour")
    assert faute_jeton(p, "au plus TROIS attentes de suite rendues à 0") in fautes(chemin, mutant)


def test_motif_comptage_aligne_sur_host_sync() -> None:
    script = ROOT / HOST_SYNC
    if not script.is_file():
        pytest.skip(f"{HOST_SYNC} absent de cet arbre : copie de MOTIF_COMPTAGE non confrontée")
    lignes = re.findall(r"^MOTIF_COMPTAGE='([^']*)'", script.read_text(encoding="utf-8"), re.MULTILINE)
    assert lignes == [MOTIF_COMPTAGE], f"{HOST_SYNC} : MOTIF_COMPTAGE a bougé ({lignes!r}) — recopier"
