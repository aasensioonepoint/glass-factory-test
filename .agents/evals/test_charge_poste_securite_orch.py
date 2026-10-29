"""Le security-orchestrator consulte ses spécialistes par vagues du `budget` de la porte (T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, lot S).

AVANT ce lot, chacune des 4 défs (claude, codex, gemini, kimi) écrivait « one wave, no concurrency cap » et
« Consult specialists (all in parallel) » (constat C36) : un audit multi-écosystème partait d'un bloc, sans regard
pour la charge du poste. Le texte exact (annexe A3 du plan) borne chaque vague au `budget` que la session appelante
passe ; `budget: 0` ⇒ NO-GO « verdict SCA non obtenu (charge) », jamais un GO sur un `effective-verdict.json` que la
passe n'a pas rafraîchi (réserve C30) ; sans budget (sca-watch planifié, /audit) ⇒ un spécialiste à la fois.

Ce qu'il tient, sur les 4 défs vivantes ET sur chaque rendu résolu du roster (`data/roster/` du paquet `cadre`, où qu'il vive) :
  (a) chaque jeton de la règle est présent, et le retirer fait manquer CE jeton et lui seul ;
  (b) témoins d'absence : « no concurrency cap » et « (all in parallel » ne survivent nulle part (C36) ;
  (c) la règle ÉCRITE est jouée : budget 0 ⇒ NO-GO de charge, budget b ≥ 1 ⇒ vagues d'au plus b, sans budget ⇒
      en série ; un texte amputé de la phrase qui décide ne décide plus (`INDECIS`) ;
  (d) C30 de bout en bout : C=4, aucun fichier d'état, aucun agent actif ⇒ `charge_poste.py` accorde
      PEUT_AJOUTER=2 ; la porte part avec security-code-review ET security-orchestrator, budget
      max(1, 2 − 2) = 1 ; la déf lance une vague d'un spécialiste — jamais le NO-GO de charge ;
  (e) chaque instrument rougit sur un mutant, et les membres sont épinglés.
BORNES : la déf .github (`.github/agents/security-orchestrator.agent.md`) n'a pas de `Task` et reste hors du lot
(annexe A1, « gardés, justifiés ») ; la `description:` du frontmatter (« fans out … in parallel ») ne dit aucune
largeur et n'est pas jugée. La formule de la porte (`budget = max(1, PEUT_AJOUTER − 2)`) est écrite sur les surfaces
du lot K (kickoff, night) et tenue par leur banc ; ici elle n'est que le CONTRAT que la déf reçoit. Ce banc ne prouve
pas qu'un modèle suit la règle au runtime, ni qu'une session appelante passe vraiment son budget : il empêche
d'OUBLIER, pas de TRICHER.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import charge_poste as cp  # noqa: E402

NOM = "security-orchestrator"
#: Les 4 défs du lot S, par hôte du roster. `copilot` est hors du lot (voir BORNES).
DEFS = {
    "claude": ".claude/agents/security-orchestrator.md",
    "codex": ".codex/agents/security-orchestrator.toml",
    "gemini": ".gemini/agents/security-orchestrator.md",
    "kimi": ".kimi-code/agents/security-orchestrator.md",
}
SOURCES = [*DEFS.values(), *(f"roster/{h}" for h in DEFS)]

# Les jetons de la règle, texte exact de l'annexe A3, comparés à espaces normalisés (le retour à la ligne est libre).
VAGUES = ("Fan the applicable specialists out IN PARALLEL (independent, read-only) in waves of at most the "
          "`budget` the calling session passes")
SUITE = "the next wave leaves when the previous returns"
BUDGET_ZERO = "`budget: 0` ⇒ launch none and return NO-GO « verdict SCA non obtenu (charge) »"
JAMAIS_GO = "never a GO on an `effective-verdict.json` this pass did not refresh"
SANS_BUDGET = "No budget given (scheduled sca-watch, /audit) ⇒ one specialist at a time"
#: SEUL ÉCART à l'annexe A3, DÉCLARÉ (mineur S de la revue de clôture S-01M545PEWX) : l'annexe (:52, :101)
#: écrit « consult » en minuscule ; les 4 défs et le roster ouvrent ici une PHRASE en milieu de ligne
#: (« …finding-free. Consult… »), d'où la majuscule. Le jeton épingle la casse des défs, comparée exactement.
CONSULTER = "Consult specialists in waves of at most `budget`"
JETONS = (VAGUES, SUITE, BUDGET_ZERO, JAMAIS_GO, SANS_BUDGET, CONSULTER)
#: Formes périmées (C36) : leur présence dit que le fan-out sans borne a survécu.
ABSENTS = ("no concurrency cap", "(all in parallel")

NO_GO_CHARGE = "NO-GO verdict SCA non obtenu (charge)"
SERIE = "SERIE"
INDECIS = "INDECIS"


def normaliser(texte: str) -> str:
    return " ".join(texte.split())


@functools.lru_cache(maxsize=None)
def texte(source: str) -> str:
    """Une déf vivante, ou le corps RÉSOLU de son rendu au roster (`roster/<hôte>`), espaces normalisés."""
    if not source.startswith("roster/"):
        return normaliser((ROOT / source).read_text(encoding="utf-8"))
    # Le paquet EXACT que `vendor_paths.py` (chargé PAR CHEMIN) désigne — `.agents/vendor/cadre` d'abord,
    # `src/cadre` sinon —, sans rien insérer en tête de `sys.path` (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot L).
    spec = importlib.util.spec_from_file_location(
        "_securite_orch_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
    assert spec is not None and spec.loader is not None
    vendor = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = vendor
    spec.loader.exec_module(vendor)
    vendor.charger_paquet(ROOT, "cadre")
    from cadre import roster  # noqa: E402
    from cadre.config import HOTES  # noqa: E402

    assert Path(roster.__file__).resolve().parent == vendor.exiger(ROOT, "cadre").resolve(), roster.__file__
    assert set(DEFS) <= set(HOTES), f"hôtes du roster changés : {HOTES} contre {sorted(DEFS)}"
    definition = roster.charger().definition(NOM)
    return normaliser("\n".join(roster.corps_de(definition, source.split("/", 1)[1])))


def manquants(contenu: str) -> list[str]:
    """Les jetons de la règle absents de `contenu`, dans leur ordre."""
    return [j for j in JETONS if j not in contenu]


def survivants(contenu: str) -> list[str]:
    """Les formes périmées encore présentes dans `contenu`."""
    return [a for a in ABSENTS if a in contenu]


def issue(contenu: str, budget: int | None) -> str:
    """Ce que la déf ÉCRITE fait d'un budget ; `INDECIS` si la phrase qui en décide manque."""
    if budget is None:
        return SERIE if SANS_BUDGET in contenu else INDECIS
    if budget == 0:
        return NO_GO_CHARGE if BUDGET_ZERO in contenu and JAMAIS_GO in contenu else INDECIS
    return f"VAGUES<={budget}" if VAGUES in contenu and SUITE in contenu else INDECIS


def budget_de_la_porte(peut_ajouter: int) -> int | None:
    """Le contrat C30 que la déf reçoit : PEUT_AJOUTER ≥ 2 ⇒ security-orchestrator part avec
    max(1, PEUT_AJOUTER − 2) ; en deçà il ne part pas à ce verdict (None)."""
    return max(1, peut_ajouter - 2) if peut_ajouter >= 2 else None


# --------------------------------------------------------------------------- (e) membres épinglés
def test_e_les_membres_sont_epingles() -> None:
    assert sorted(DEFS) == ["claude", "codex", "gemini", "kimi"]
    assert len(SOURCES) == 8 and len(set(JETONS)) == len(JETONS) == 6
    for rel in DEFS.values():
        assert (ROOT / rel).is_file(), f"déf absente : {rel}"


def test_e_aucun_jeton_n_en_contient_un_autre() -> None:
    """Sans cela, retirer un jeton en emporterait un second, et (a) ne prouverait plus « CE jeton seul »."""
    for j in JETONS:
        assert [k for k in JETONS if k != j and k in j] == [], j


# --------------------------------------------------------------------------- (a) présence, et mutant par jeton
@pytest.mark.parametrize("source", SOURCES)
def test_a_chaque_jeton_est_present(source: str) -> None:
    assert manquants(texte(source)) == [], f"{source} : jetons absents — restaure la phrase de l'annexe A3"


@pytest.mark.parametrize("jeton", JETONS)
@pytest.mark.parametrize("source", SOURCES)
def test_a_retirer_un_jeton_fait_manquer_ce_jeton_seul(source: str, jeton: str) -> None:
    mute = texte(source).replace(jeton, "")
    assert manquants(mute) == [jeton]


# --------------------------------------------------------------------------- (b) témoins d'absence
@pytest.mark.parametrize("source", SOURCES)
def test_b_aucune_forme_perimee_ne_survit(source: str) -> None:
    assert survivants(texte(source)) == [], f"{source} : fan-out sans borne survivant (C36)"


@pytest.mark.parametrize("forme", ABSENTS)
def test_b_temoin_une_forme_perimee_semee_est_vue(forme: str) -> None:
    base = texte(SOURCES[0])
    for autre in ABSENTS:
        base = base.replace(autre, "")
    assert survivants(base + " " + forme) == [forme]


# --------------------------------------------------------------------------- (c) la règle écrite, jouée
@pytest.mark.parametrize("source", SOURCES)
def test_c_la_regle_ecrite_decide_chaque_budget(source: str) -> None:
    contenu = texte(source)
    assert issue(contenu, 0) == NO_GO_CHARGE
    assert issue(contenu, 1) == "VAGUES<=1"
    assert issue(contenu, 3) == "VAGUES<=3"
    assert issue(contenu, None) == SERIE


@pytest.mark.parametrize(("jeton", "budget"), [(BUDGET_ZERO, 0), (JAMAIS_GO, 0), (VAGUES, 1), (SUITE, 1),
                                               (SANS_BUDGET, None)])
def test_c_temoin_un_texte_ampute_ne_decide_plus(jeton: str, budget: int | None) -> None:
    mute = texte(SOURCES[0]).replace(jeton, "")
    assert issue(mute, budget) == INDECIS


def test_c_temoin_l_ancien_texte_ne_decide_rien() -> None:
    ancien = normaliser("Fan ALL the applicable specialists out IN PARALLEL (independent, read-only) — "
                        "one wave, no concurrency cap. Consult specialists (all in parallel) ONLY to")
    assert [issue(ancien, b) for b in (0, 1, None)] == [INDECIS] * 3
    assert survivants(ancien) == list(ABSENTS)


# --------------------------------------------------------------------------- (d) C30 de bout en bout
def _verdict_c4_sans_fichier(tmp_path: Path, l1: float = 0.5) -> cp.Verdict:
    mesure = cp.Mesure(4, (l1, l1, 0.5), "getloadavg", 1, None, (), "darwin")
    dossier, config = tmp_path / "etat" / "charge_poste", tmp_path / "conf" / "parallelisme.json"
    assert not dossier.exists() and not config.exists()
    return cp.executer_verdict(0, mesure=mesure, horloge=lambda: 1_800_000_000.0, dossier=dossier,
                               fichier_config=config, poste="banc", attente_verrou=0)


@pytest.mark.parametrize("source", SOURCES)
def test_d_c4_sans_fichier_la_porte_part_budget_1(tmp_path: Path, source: str) -> None:
    verdict = _verdict_c4_sans_fichier(tmp_path)
    assert (verdict.plafond, verdict.base, verdict.peut_ajouter) == (2, 2, 2)
    budget = budget_de_la_porte(verdict.peut_ajouter)
    assert budget == 1
    assert issue(texte(source), budget) == "VAGUES<=1", f"{source} : la porte à C=4 ne part pas"


def test_d_temoin_sous_surcharge_le_security_orchestrator_ne_part_pas(tmp_path: Path) -> None:
    """1 min > 2C/3 à C=4 ⇒ aucun accord : l'instrument de (d) sait dire « ne part pas »."""
    verdict = _verdict_c4_sans_fichier(tmp_path, l1=3.0)
    assert verdict.peut_ajouter == 0
    assert budget_de_la_porte(verdict.peut_ajouter) is None


def test_d_temoin_la_formule_de_la_porte() -> None:
    assert [budget_de_la_porte(k) for k in (0, 1, 2, 3, 5)] == [None, None, 1, 1, 3]
