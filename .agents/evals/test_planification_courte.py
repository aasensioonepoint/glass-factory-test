#!/usr/bin/env python3
"""PLANIFICATION COURTE (T-01M52XW8XNSN865QTNS0Z0KK7P + T-01M527R8KCBQJAXE8Q41VTQMWH, décision
pilote S-01M52Y43BA). Mesuré (S-01M52XZTXS, 14-16/10) : 115 verdicts plan-critic pour 38 tâches,
86 NO_GO dont la moitié = 1 bloquant + 6 réserves ; plans de 80 lignes en médiane pour un
gabarit de 45 que rien ne tenait.

CE QUE CE BANC TIENT, et rien d'autre :
  (1) les 5 défs plan-critic disent qu'une réserve ne justifie jamais un NO_GO et qu'un plan
      de plus de N lignes non vides est un bloquant de forme ;
  (2) les 5 défs planner nomment l'annexe `<T>-annexe.md` et le plafond N ;
  (3) N est CELUI DU CODE (`plan_lots.PLAFOND_LIGNES_PLAN`), sur les 10 défs ;
  (4) AGENTS.md, la skill planning et les deux kickoff portent la règle « réserve ≠ NO_GO » ;
  (5) les deux kickoff, les deux planning, les deux planning-all et Copilot prescrivent le
      `chrono:` du tour ET disent que le CODE le tient (S-01M534MZK4) : `specs.py add` refuse sous
      `CHRONO_REQUIRED`, sortie `--sans-chrono`, lecture `specs.py chrono`, voie `--chrono-aid` sur
      Claude Code dans son SENS (5b) ; la garde elle-même est jugée par
      `.agents/bin/test_specs.py::SpecsChronoTests` et `test_specs_chrono.py`, pas ici ;
  (6) l'exemple « (CHANGELOG, index, registre commun) » a quitté les 10 défs et les 2 rosters
      (S-01M51H3PT : le CHANGELOG se rédige au tag, jamais par INTÉGRATION) ;
  (7) CLIQUET : les deux défs `.claude` ne regonflent pas (plafond d'octets à relever À LA MAIN,
      avec une coupe en face, sauf décision pilote qui autorise le relèvement sans coupe, citée
      ici). UNE seule mesure de référence, celle de `PLAFOND_OCTETS` ci-dessous ;
      l'historique, pour mémoire : a10e957d (avant S-01M52Y43BA) planner 13 291 / plan-critic 20 877 ;
      3b65f8d7 (leviers 1-5) 13 049 / 20 031 ; après le gros allègement S-01M534JFFC et la correction
      S-01M53CW9CH (phrases exactes par hôte et par rôle remises dans les renvois) 9 421 / 16 700 ;
      relevé par T-01M54BDV4WKPR1RMT96J7C0KJK SANS coupe en face, autorisé par la décision pilote
      S-01M54JHA85PCB7FRP2GGP16KYJ (5) (« relever les plafonds d'octets des défs en le disant, plutôt
      qu'une coupe ») : renvoi § 4 « SQL de plan » +582 / +848 → 10 003 / 17 548, puis sa correction
      exec-critic (barème SQL de plan-critic aligné sur § 4) +0 / +100 → 10 003 / 17 648 ; plafonds
      10 050 / 17 700, marges 47 / 52 octets ; relevé par T-01M54WMA3W SANS coupe, même décision
      S-01M54JHA85PCB7FRP2GGP16KYJ (5) : phrase dev-mono (réserve C7 comprise) et gabarit +371 → 10 374 ;
      plafond 10 420, marge 46 ; relevé par T-01M55W6GZ6PHRE554HVTPGN416 (partie texte) SANS coupe,
      même décision S-01M54JHA85PCB7FRP2GGP16KYJ (5), motif S-01M55W6WMBNSMT0NWCPC4YQG8F (« avant de
      rendre » du planner, critique exhaustif au tour 1, verdict intégral) : +1 191 / +695 →
      11 565 / 18 343 ; plafonds 11 615 / 18 393, marges 50 / 50 ; puis sa passe de correction
      (copie hors de l'arbre au mutant du planner, `r(n-1) absent` du critique), même décision : +67 / +34 →
      11 632 / 18 377 ; plafonds 11 682 / 18 393, marges 50 / 16 ; relevé par T-01M57F1AG0DYF5QJ8YXNV76RTR
      SANS coupe, même décision S-01M54JHA85PCB7FRP2GGP16KYJ (5), motif S-01M57F0BHB / S-01M57FKBYM
      (efforts medium / high, rappel advisor ; règle 5 du critique raccourcie) : +79 / −467 →
      11 711 / 17 910 ; plafonds 11 761 / 17 960, marges 50 / 50 ; relevé par la passe de correction
      de la revue de clôture T-01M576S89 + T-01M57F1AG0 SANS coupe, même décision
      S-01M54JHA85PCB7FRP2GGP16KYJ (5) (gabarit `## Tests` de lot, contrôle de forme du critique) :
      +60 / +209 → 11 771 / 18 119 ; plafonds 11 821 / 18 169, marges 50 / 50.
BORNES : la parité des miroirs est tenue par `test_cadre_roster.py` (T1/T2), pas ici ; la forme
du barème par `test_plan_critic_contract.py` ; ce banc saute hors du kit (surfaces réécrites
par l'adoptant)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

_spec = importlib.util.spec_from_file_location("plan_lots", ROOT / ".agents" / "bin" / "plan_lots.py")
assert _spec is not None and _spec.loader is not None
plan_lots = importlib.util.module_from_spec(_spec)
sys.modules["plan_lots"] = plan_lots
_spec.loader.exec_module(plan_lots)
N = plan_lots.PLAFOND_LIGNES_PLAN

HOTES = ((".claude/agents", ".md"), (".codex/agents", ".toml"), (".gemini/agents", ".md"),
         (".github/agents", ".agent.md"), (".kimi-code/agents", ".md"))
PLANNER = tuple(f"{d}/planner{ext}" for d, ext in HOTES)
PLAN_CRITIC = tuple(f"{d}/plan-critic{ext}" for d, ext in HOTES)
_spec_vendor = importlib.util.spec_from_file_location(
    "_planification_courte_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _spec_vendor is not None and _spec_vendor.loader is not None
_vendor = importlib.util.module_from_spec(_spec_vendor)
sys.modules[_spec_vendor.name] = _vendor
_spec_vendor.loader.exec_module(_vendor)
#: Le paquet `cadre` OÙ QU'IL VIVE (`.agents/vendor/cadre`, sinon `src/cadre`), relatif à ROOT.
PAQUET = _vendor.exiger(ROOT, "cadre").relative_to(ROOT).as_posix()
ROSTERS = (f"{PAQUET}/data/roster/planner.json", f"{PAQUET}/data/roster/plan-critic.json")
DOCTRINE = ("AGENTS.md", ".agents/skills/planning/SKILL.md", ".agents/skills/kickoff/SKILL.md",
            ".claude/commands/kickoff.md")
#: Surfaces du chrono (T-01M55Z3ZCS34CDR2EQN1CEBHR7 : + /planning, Copilot, /planning-all), chacune
#: avec la phrase qui dit le SENS de la voie Claude Code (`--chrono-aid`, jamais le champ à la main) :
#: inversée (« DO write »), retirée ou réduite à un renvoi sans jetons, la surface rougit.
CHRONO_AID_SENS = {
    ".agents/skills/kickoff/SKILL.md": ("do NOT write the field by hand", "is unresolved: rc 2 under an armed"),
    ".claude/commands/kickoff.md": ("instead of writing the field by hand",),
    ".agents/skills/planning/SKILL.md": ("ce champ ne s'écrit PAS à la main", "est non résolu : rc 2"),
    ".claude/commands/planning.md": ("ce champ ne s'écrit PAS à la main", "non résolu (rc 2 armé"),
    ".github/copilot-instructions.md": ("written by hand here (no `agentId`; Claude Code passes `--chrono-aid`)",),
    ".agents/skills/planning-all/SKILL.md": ("`--chrono-aid` sur Claude Code", "sortie `--sans-chrono \"<pourquoi>\"` sur TOUT hôte"),
    ".claude/commands/planning-all.md": ("sans champ écrit à la main", "sur tout hôte"),
}
CHRONO_SURFACES = tuple(CHRONO_AID_SENS)

RESERVE_CRITIC = "a concern never justifies a NO_GO"
FORME_CRITIC = f"a plan over {N} non-blank lines"
ANNEXE = "-annexe.md"
PLAFOND_PLANNER = (f"{N} non-blank lines", f"{N} lignes non vides")
RESERVE_FR = "une réserve ne justifie jamais un `NO_GO`"
CHRONO = "chrono: planner="
CHRONO_CODE = ("CHRONO_REQUIRED", "--sans-chrono", "specs.py chrono", "--chrono-aid")
CHRONO_PROSE_D_AVANT = "aucun code ne le lit encore"
ANCIEN_EXEMPLE = "CHANGELOG, index, registre commun"
#: Les défs et leurs rosters sont en anglais depuis T-01M5S9338BJP1B5RM3TG14AMYT : le nouvel exemple y
#: est « a common registry » ; la forme française d'avant ne le satisfait plus (test_6b).
NOUVEL_EXEMPLE = "a common registry"
NOUVEL_EXEMPLE_FR = "un registre commun"
#: L'ancien exemple, revenu en anglais dans une déf traduite, rougit comme le français.
ANCIEN_EXEMPLE_EN = "CHANGELOG, index, common registry"
ANCIENS_EXEMPLES = (ANCIEN_EXEMPLE, ANCIEN_EXEMPLE_EN)
#: Cliquet d'octets des défs `.claude` — mesure de référence (clôture T-01M576S89 + T-01M57F1AG0, gabarit `## Tests` et contrôle de forme, +60 / +209) : 11 771 et 18 118 ; mesure à la porte de la livraison 2 (préflight de forme, ligne LECON de plan-critic rendue à « journal EXISTS » / « You never run that command ») : 11 762 et 18 153, marges 59 et 16 ; relèvement sans coupe, S-01M54JHA85 (5) ; historique au docstring (7). Relevé à 18 284 sans coupe par la clôture T-01M5G7RVT1 (+115 : interdits bornés au dépôt jugé, renvoi au clone jetable, texte commun aux hôtes). Relevé à 12 530 et 19 567 sans coupe par T-01M5NPC8GCA28T1XBWTG456BN0 lot B (+709 / +1 283 : ligne INTERACTION d'un plan d'écran, « one of the two UI checks that block », lots d'écran par comportement — décision pilote S-01M5N24P2Y0SH6S0W0YNG3TAN6). Correction de clôture T-01M5NPC8GCA28T1XBWTG456BN0 (marges 0 relevées, sens de « plan d'écran » au critique, +0 / +124) : mesures 12 530 et 19 691, plafonds = mesure + 50, sans coupe, même décision S-01M54JHA85PCB7FRP2GGP16KYJ (5).
PLAFOND_OCTETS = {".claude/agents/planner.md": 12_580, ".claude/agents/plan-critic.md": 19_741}


def _lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _plat(texte: str) -> str:
    return " ".join(texte.split())


def fautes(texte: str, attendus: tuple[str, ...] = (), interdits: tuple[str, ...] = ()) -> list[str]:
    """Les jetons attendus absents et les interdits présents, blancs pliés."""
    plat = _plat(texte)
    f = [f"absent : {a}" for a in attendus if a not in plat]
    f += [f"présent : {i}" for i in interdits if i in plat]
    return f


@pytest.mark.parametrize("rel", PLAN_CRITIC)
def test_1_le_critique_ne_rend_no_go_que_pour_un_bloquant(rel: str) -> None:
    assert fautes(_lire(rel), (RESERVE_CRITIC, FORME_CRITIC)) == []


@pytest.mark.parametrize("rel", PLANNER)
def test_2_le_planner_nomme_l_annexe_et_le_plafond(rel: str) -> None:
    texte = _lire(rel)
    assert fautes(texte, (ANNEXE,)) == []
    assert any(p in _plat(texte) for p in PLAFOND_PLANNER), f"{rel} : aucun de {PLAFOND_PLANNER}"


def test_3_le_plafond_des_defs_est_celui_du_code() -> None:
    assert N == 45, "le plafond a bougé dans le code : relis la décision S-01M52Y43BA avant de suivre"
    for rel in PLANNER:
        assert _plafond_des_defs_dit(_lire(rel)), rel
    for rel in PLAN_CRITIC:
        assert FORME_CRITIC in _plat(_lire(rel)), rel


def _plafond_des_defs_dit(texte: str) -> bool:
    """Les défs planner sont en anglais (T-01M5S9338BJP1B5RM3TG14AMYT) : le plafond y est dit
    `<N> non-blank lines` — la forme française d'avant ne compte plus ici."""
    return f"{N} non-blank lines" in _plat(texte)


@pytest.mark.parametrize("rel", PLANNER)
def test_3b_la_forme_francaise_d_avant_rougit(rel: str) -> None:
    texte = _lire(rel)
    mutant = texte.replace(f"{N} non-blank lines", f"{N} lignes non vides")
    assert mutant != texte and not _plafond_des_defs_dit(mutant), rel


@pytest.mark.parametrize("rel", DOCTRINE)
def test_4_la_doctrine_dit_reserve_differente_de_no_go(rel: str) -> None:
    assert fautes(_lire(rel), (RESERVE_FR,)) == []


@pytest.mark.parametrize("rel", CHRONO_SURFACES)
def test_5_le_chrono_du_tour_est_prescrit_et_tenu_par_le_code(rel: str) -> None:
    """← le champ `chrono:` quitte une surface ; ← la surface ne nomme plus le marqueur, la sortie
    tracée ou la commande de lecture ; ← la prose d'avant (« aucun code ne le lit ») revient."""
    assert fautes(_lire(rel), (CHRONO, *CHRONO_CODE), (CHRONO_PROSE_D_AVANT, "no code reads it")) == []


@pytest.mark.parametrize("rel", CHRONO_SURFACES)
def test_5b_la_voie_chrono_aid_garde_son_sens(rel: str) -> None:
    """← une surface qui dirait d'écrire le champ à la main sur Claude Code, ou rc 0 à un aid non résolu armé."""
    assert fautes(_lire(rel), CHRONO_AID_SENS[rel]) == []


@pytest.mark.parametrize("rel", PLANNER + PLAN_CRITIC + ROSTERS)
def test_6_l_exemple_changelog_a_quitte_les_defs_et_les_rosters(rel: str) -> None:
    assert fautes(_lire(rel), (NOUVEL_EXEMPLE,), ANCIENS_EXEMPLES) == []


@pytest.mark.parametrize(("rel", "plafond"), sorted(PLAFOND_OCTETS.items()))
def test_7_cliquet_d_octets_des_defs_claude(rel: str, plafond: int) -> None:
    taille = (ROOT / rel).stat().st_size
    assert taille <= plafond, (f"{rel} : {taille} octets > {plafond} — une règle ajoutée se paie d'une coupe ; "
                               "sinon relève PLAFOND_OCTETS à la main, dans le même commit, en le disant")


# --- Contrôles négatifs : la fonction rougit sur chaque mutation --------------------------------
def test_mutant_jeton_retire_rougit() -> None:
    texte = _lire(".claude/agents/plan-critic.md")
    assert fautes(texte, (RESERVE_CRITIC,)) == [], "base rouge"
    assert fautes(texte.replace(RESERVE_CRITIC, "a concern may justify a NO_GO"), (RESERVE_CRITIC,))


def test_mutant_ancien_exemple_revenu_rougit() -> None:
    texte = _lire(".claude/agents/planner.md")
    assert fautes(texte, (NOUVEL_EXEMPLE,), ANCIENS_EXEMPLES) == [], "base rouge"
    for ancien in ANCIENS_EXEMPLES:
        mute = texte.replace("`AGENTS.md`, a `README`, a common registry", ancien)
        assert mute != texte
        assert f"présent : {ancien}" in fautes(mute, (NOUVEL_EXEMPLE,), ANCIENS_EXEMPLES)
    # T-01M5S9338BJP1B5RM3TG14AMYT : le nouvel exemple remis en français ne satisfait plus une déf anglaise.
    francais = texte.replace(NOUVEL_EXEMPLE, NOUVEL_EXEMPLE_FR)
    assert francais != texte and f"absent : {NOUVEL_EXEMPLE}" in fautes(francais, (NOUVEL_EXEMPLE,), ANCIENS_EXEMPLES)


def test_mutant_plafond_du_code_mute_rougit_les_defs() -> None:
    """Le code dit 44 : les défs qui disent 45 sont rouges (l'égalité code/doctrine mord)."""
    assert f"{N - 1} non-blank lines" not in _plat(_lire(".claude/agents/planner.md"))
    assert f"a plan over {N - 1} non-blank lines" not in _plat(_lire(".claude/agents/plan-critic.md"))
