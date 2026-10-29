"""Le plafond d'agents PAR POSTE est écrit comme l'outil le décide (T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, lot D).

Les jetons, les surfaces, les formes périmées (`absents`) et la règle de DUR unique (`dur`)
vivent dans `doctrine_registre.py`, règle `REGLE` ci-dessous, et nulle part ici :
`test_doctrine_registre.py` (4d) refuse un jeton recopié en constante. Ce banc lit le TEXTE
seul ; il n'importe pas l'outil `charge_poste.py` (lot T, tenu par son propre banc).

Ce qu'il tient :
  (a) chaque jeton est présent sur chaque surface de son groupe, et le retirer fait manquer
      CE jeton et lui seul ;
  (b) la clause (3) d'« ÉCONOMIE DE LA MACHINE » porte TOUS les jetons de `clause-3` sur la
      seule ligne de sa puce, la décision de calibration automatique comprise, et aucun
      « <chiffre> agents » (constat C34, la règle de comptage de host_sync.test.sh) ;
  (c) aucune forme périmée ne survit (constat C26 : la clause est remplacée ENTIÈRE), et
      aucun geste interdit sur le clone (`absents_motifs` : verbe + options, `-C <x>` compris) ;
  (d) UNE règle de DUR (constat C46) : chaque marque du plafond dur est dans la règle, et le
      routeur la porte une fois ;
  (e) chaque instrument rougit sur un mutant, et les membres sont épinglés (un compte
      laisserait substituer une surface à taille égale) — l'entrée pilote du CHANGELOG
      comprise (groupe `changelog`, revue de clôture commune).
Bornes : la `limite` de la règle, au registre.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402
from surface_kit import EST_LE_KIT  # noqa: E402

REGLE = "plafond-poste"
CE_BANC = ".agents/evals/test_charge_poste_doctrine.py"
ROUTEUR = "AGENTS.md"
MIROIR = ".github/copilot-instructions.md"
CLAUDE = "CLAUDE.md"
CHANGELOG = "CHANGELOG.md"
#: L'ouverture de la puce qui porte la clause (3) au routeur : un instrument, pas un jeton.
PUCE_ECONOMIE = "- **ÉCONOMIE DE LA MACHINE"
#: `MOTIF_COMPTAGE` de core-scripts/host_sync.test.sh, en Python (grep -Ei) : un nombre en
#: chiffres devant « agents » périme au premier changement du roster.
COMPTAGE = re.compile(r"[0-9]+ (?:specialized |role-scoped )?(?:agents|subagents)", re.IGNORECASE)

GROUPES = tuple(R.regle(REGLE)["groupes"])
# E3 : CHANGELOG.md devient une destination du canal adoptant à E5. Son entrée
# pilote reste jugée dans le kit ; hors du kit, les autres groupes livrés restent
# non vides et jugés. Les deux restrictions CHANGELOG sont datées à leur source
# (ici, test_night_contract.py).
GROUPES_JUGES = GROUPES if EST_LE_KIT else tuple(g for g in GROUPES if g != "changelog")
assert GROUPES_JUGES and "routeur" in GROUPES_JUGES, "aucun groupe de doctrine livré"
#: Hors du kit, les surfaces non livrées (`R.HORS_VOYAGE` : les prompts de session du kit, qui
#: ne voyagent pas) sont RESTREINTES par `R.livrees`, qui lève si rien ne reste ; AGENTS.md
#: reste jugé partout. Les membres, eux, sont épinglés sur le registre ENTIER (e).
TRIPLETS = [(g, s) for g in GROUPES_JUGES for s in R.livrees(R.chemins(REGLE, g), EST_LE_KIT)]
assert TRIPLETS, "aucune surface de doctrine livrée"
SURFACES = list(R.livrees(sorted({s for g in GROUPES_JUGES for s in R.chemins(REGLE, g)}), EST_LE_KIT))
ABSENTS: dict[str, tuple[str, ...]] = R.regle(REGLE)["absents"]
MOTIFS: dict[str, tuple[str, ...]] = R.regle(REGLE)["absents_motifs"]
DUR: dict[str, str] = R.regle(REGLE)["dur"]
SURFACES_ABSENTS = sorted(R.livrees(sorted(ABSENTS), EST_LE_KIT))
SURFACES_MOTIFS = sorted(R.livrees(sorted(MOTIFS), EST_LE_KIT))


def _texte(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def ligne_clause(texte: str) -> str | None:
    """La ligne qui ouvre par la puce ÉCONOMIE ; None si elle manque ou si elle est doublée."""
    lignes = [ligne for ligne in texte.splitlines() if ligne.startswith(PUCE_ECONOMIE)]
    return lignes[0] if len(lignes) == 1 else None


def formes_perimees(texte: str, formes: tuple[str, ...]) -> list[str]:
    """Les formes de `formes` encore présentes dans `texte`, dans leur ordre."""
    return [f for f in formes if f in texte]


def gestes_interdits(texte: str, motifs: tuple[str, ...]) -> list[str]:
    """Les motifs de `motifs` (verbe + options, `-C <x>` compris) qui mordent sur `texte`."""
    return [m for m in motifs if re.search(m, texte)]


def fautes_dur(texte: str, regle: str, marque: str, *, routeur: bool) -> list[str]:
    """Les fautes de la règle de DUR unique : une marque hors de la règle, et au routeur une
    règle portée zéro ou plusieurs fois. `[]` si elle tient."""
    fautes: list[str] = []
    n_regle = texte.count(regle)
    hors = texte.count(marque) - n_regle * regle.count(marque)
    if hors > 0:
        fautes.append(f"{hors} marque(s) {marque!r} hors de la règle de DUR")
    if routeur and n_regle != 1:
        fautes.append(f"règle de DUR portée {n_regle} fois au routeur, une attendue")
    return fautes


# --- (a) présence, et chaque jeton manque seul ---------------------------------------------------

@pytest.mark.parametrize("groupe,surface", TRIPLETS)
def test_a_chaque_jeton_present_et_seul_a_manquer_quand_on_le_retire(groupe: str, surface: str) -> None:
    texte = _texte(surface)
    attendus = R.jetons(REGLE, groupe)
    assert R.manquants(texte, attendus) == [], f"{surface} ({REGLE}.{groupe})"
    for j in attendus:
        mute = texte.replace(j, "")
        assert mute != texte, f"{j!r} absent de {surface}"
        assert R.manquants(mute, attendus) == [j], (
            f"{surface} privé de {j!r} : manquants={R.manquants(mute, attendus)}"
        )


# --- (b) la clause (3) sur sa ligne, nombres en lettres ------------------------------------------

def test_b_la_clause_3_tient_sur_la_ligne_de_sa_puce() -> None:
    ligne = ligne_clause(_texte(ROUTEUR))
    assert ligne is not None, f"{ROUTEUR} : puce ÉCONOMIE absente ou doublée"
    assert R.manquants(ligne, R.jetons(REGLE, "clause-3")) == [], "clause (3) incomplète sur sa ligne"
    assert COMPTAGE.findall(ligne) == [], "un « <chiffre> agents » dans la clause (3) : écrire en lettres"


@pytest.mark.parametrize("jeton", R.jetons(REGLE, "clause-3"))
def test_b_temoin_un_jeton_deplace_hors_de_la_puce_rougit(jeton: str) -> None:
    """Le témoin que (b) voit plus que (a) : le jeton reste dans le fichier, hors de la puce."""
    texte = _texte(ROUTEUR)
    ligne = ligne_clause(texte)
    assert ligne is not None
    mute = texte.replace(ligne, ligne.replace(jeton, "")) + "\n" + jeton + "\n"
    assert R.manquants(mute, R.jetons(REGLE, "clause-3")) == [], "le jeton déplacé reste au fichier"
    ligne_mutee = ligne_clause(mute)
    assert ligne_mutee is not None
    assert R.manquants(ligne_mutee, R.jetons(REGLE, "clause-3")) == [jeton]


def test_b_temoins_puce_doublee_et_nombre_en_chiffres_rougissent() -> None:
    texte = _texte(ROUTEUR)
    ligne = ligne_clause(texte)
    assert ligne is not None
    assert ligne_clause(texte + "\n" + ligne + "\n") is None, "une puce doublée doit rougir"
    assert COMPTAGE.findall(ligne + " (3 agents)") == ["3 agents"]


# --- (c) les formes périmées -----------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES_ABSENTS)
def test_c_aucune_forme_perimee_ne_survit(surface: str) -> None:
    assert formes_perimees(_texte(surface), ABSENTS[surface]) == [], surface


@pytest.mark.parametrize("surface", SURFACES_ABSENTS)
def test_c_temoin_chaque_forme_reinjectee_rougit_seule(surface: str) -> None:
    texte = _texte(surface)
    for forme in ABSENTS[surface]:
        assert formes_perimees(texte + "\n" + forme + "\n", ABSENTS[surface]) == [forme], forme


@pytest.mark.parametrize("surface", SURFACES_MOTIFS)
def test_c_aucun_geste_interdit_sur_le_clone(surface: str) -> None:
    """T1 exec : `reset --hard` et `clean -f…` épinglés par verbe + options, `-C` compris."""
    assert gestes_interdits(_texte(surface), MOTIFS[surface]) == [], surface


#: Les mutants du T1 exec : chaque forme réinjectée doit rougir, `-C <x>` compris ; la prose
#: qui nomme le geste pour l'interdire, elle, ne mord pas.
MUTANTS_GESTES = (
    ("`git -C <clone> reset --hard`", 0),
    ('`git -C "$CLONE" reset --hard HEAD`', 0),
    ("`git -C /tmp/cadre-x/r reset --hard`", 0),
    ("`git reset --hard`", 0),
    ("`git -C <chemin absolu du clone> reset --hard`", 0),
    ("`git -C <clone> clean -fdq`", 1),
    ("`git -C '/tmp/x' clean -xfd`", 1),
    ("`git clean -f`", 1),
)


@pytest.mark.parametrize("surface", SURFACES_MOTIFS)
@pytest.mark.parametrize("forme,indice", MUTANTS_GESTES)
def test_c_temoin_geste_reinjecte_rougit(surface: str, forme: str, indice: int) -> None:
    motifs = MOTIFS[surface]
    texte = _texte(surface)
    assert gestes_interdits(texte + "\n" + forme + "\n", motifs) == [motifs[indice]], forme


def test_c_temoin_la_prose_qui_interdit_ne_mord_pas() -> None:
    motifs = MOTIFS[ROUTEUR]
    prose = "jamais `reset --hard` ni `clean -f…` ; `git -C <clone> reset --keep` ; `git -C x checkout -f`"
    assert gestes_interdits(prose, motifs) == []


# --- (d) une seule règle de DUR -------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
def test_d_une_seule_regle_de_dur(surface: str) -> None:
    fautes = fautes_dur(_texte(surface), DUR["regle"], DUR["marque"], routeur=surface == DUR["routeur"])
    assert fautes == [], f"{surface} : {fautes}"


def test_d_temoins_second_plafond_dur_regle_doublee_ou_absente_rougissent() -> None:
    regle, marque = DUR["regle"], DUR["marque"]
    texte = _texte(DUR["routeur"])
    second = texte + "\nplafond dur : " + marque + " des cœurs\n"
    assert fautes_dur(second, regle, marque, routeur=True) != [], "une seconde rédaction du DUR"
    assert fautes_dur(texte + "\n" + regle + "\n", regle, marque, routeur=True) != [], "règle doublée"
    assert fautes_dur(texte.replace(regle, ""), regle, marque, routeur=True) != [], "règle absente"
    hors_routeur = _texte(MIROIR) + "\n" + marque + "\n"
    assert fautes_dur(hors_routeur, regle, marque, routeur=False) != [], "marque isolée au miroir"


# --- (e) membres épinglés -------------------------------------------------------------------------

def test_e_membres_epingles() -> None:
    assert GROUPES == ("routeur", "clause-1", "clause-3", "miroir", "copilot", "claude", "changelog")
    assert R.chemins(REGLE, "routeur") == (ROUTEUR,)
    assert R.chemins(REGLE, "clause-1") == (
        ROUTEUR,
        "docs/tasks/PROMPT-SESSION-DEV.md",
        "docs/tasks/PROMPT-SESSION-PLANS.md",
    )
    assert R.chemins(REGLE, "clause-3") == (ROUTEUR,)
    assert R.chemins(REGLE, "miroir") == (ROUTEUR, MIROIR)
    assert R.chemins(REGLE, "copilot") == (MIROIR,)
    assert R.chemins(REGLE, "claude") == (CLAUDE,)
    assert R.chemins(REGLE, "changelog") == (CHANGELOG,), "l'entrée pilote du CHANGELOG (mutant M21)"
    assert set(ABSENTS) == {
        ROUTEUR,
        MIROIR,
        CLAUDE,
        "docs/tasks/PROMPT-SESSION-DEV.md",
        "docs/tasks/PROMPT-SESSION-PLANS.md",
    }, "chaque surface porte ses formes périmées"
    assert set(MOTIFS) == set(R.chemins(REGLE, "clause-1")), "gestes interdits sur chaque copie de la clause (1)"
    assert all(len(MOTIFS[s]) == 2 for s in MOTIFS), "reset --hard et clean -f, un motif chacun"
    assert DUR["routeur"] == ROUTEUR and DUR["marque"] in DUR["regle"]
    assert DUR["regle"] in R.jetons(REGLE, "clause-3"), "la règle de DUR est un jeton de la clause"
    assert len(R.jetons(REGLE, "clause-3")) >= 14, "la clause (3) a perdu un jeton"
    assert R.regle(REGLE)["bancs"] == (CE_BANC,)


def test_e_hors_du_kit_le_changelog_adoptant_n_est_pas_juge() -> None:
    """La destination CHANGELOG sera réécrite à E5, sans retirer les surfaces communes."""
    assert TRIPLETS
    assert ("routeur", ROUTEUR) in TRIPLETS
    assert (("changelog", CHANGELOG) in TRIPLETS) == EST_LE_KIT


def test_e_hors_du_kit_clause_1_restreinte_a_agents_md() -> None:
    """Défaut de voyage S-01M5K955P3 : hors du kit, les deux PROMPT-SESSION (non livrés) sont
    retirés, AGENTS.md reste jugé ; dans le kit, rien n'est retiré ; un ensemble vide LÈVE."""
    clause_1 = R.chemins(REGLE, "clause-1")
    assert R.livrees(clause_1, True) == clause_1
    assert R.livrees(clause_1, False) == (ROUTEUR,)
    assert ROUTEUR not in R.HORS_VOYAGE, "AGENTS.md voyage : jamais restreint"
    assert set(R.HORS_VOYAGE) < set(clause_1), "chaque surface non livrée est une copie de la clause (1)"
    with pytest.raises(AssertionError):
        R.livrees(R.HORS_VOYAGE, False)
