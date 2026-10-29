"""Les trois règles d'efficacité sont écrites sur chaque surface qui voyage (T-01M4ZG76AWZKH3HW0R3KKDEFVF).

Décisions pilote S-01M4ZG7Q5FAHQFVKG10Y81ZYXH (R1 fermer avant d'ouvrir, R2 un mineur jamais en
ticket, R3 voie courte) et S-01M51M3X9SFEZECT1QJ0XJ8GD6 (R3 jouée par UN passage court du
critique). Le CODE tient le calcul de R3 (`plan_plafond.py --voie-courte`,
`.agents/bin/test_plan_plafond.py`) ; ce banc tient sa PROSE. Jetons, surfaces et aiguilles de la
ligne R3 vivent dans `doctrine_registre.py`, règle `REGLE` ci-dessous, et nulle part ici :
`test_doctrine_registre.py` (4d) refuse un jeton recopié en constante. Cinq juges :
  (1) PRÉSENCE — chaque surface porte les jetons de son groupe ;
  (2) MEMBRES ÉPINGLÉS — les surfaces de chaque groupe et les jumeaux de la ligne R3 (un compte
      laisserait substituer une surface à taille égale) ;
  (3) LA LIGNE R3 — `**Voie courte R3**` UNE fois sur kickoff.md et sur la skill kickoff,
      IDENTIQUE octet pour octet, sans `specs.py add` (le `_geste_line` de
      test_plan_cible_mirror.py prendrait sinon la première ligne qui porte `specs.py add` ET
      `plan approuvé`), ses aiguilles cherchées dans LEUR segment : (a) et son `--files` ; le
      mandat de (c) entre ses guillemets — la phrase « `oui` is a permission » répète les
      classes, un grep de la ligne entière ne rougirait pas (C2 de plan-critic 5/8) ; (d) ; (e)
      et sa clause des cinq classes ; la phrase `pilote` — (d) porte aussi « human gate ».
      L'identité des jumeaux ne voit pas une aiguille retirée DES DEUX côtés : les segments, si ;
  (4) SEUILS ET VALEURS ÉPINGLÉS PAR AST — le seuil que disent les jetons (3) et (4), celui du
      (5) et les valeurs du (7) sont ceux de `SEUIL_NO_GO`, `SEUIL_FICHIERS` et
      `VOIE_COURTE_VALEURS` de `.agents/bin/plan_plafond.py`, lu par AST, jamais importé ;
  (5) VOYAGE — aucune règle de `.template-exclude` ne retient une surface, le registre, ce banc
      ni `plan_plafond.py` (`strip:`, `keep:` ou `own:` : aucun n'est repris de main, donc
      jamais mis à jour chez l'adoptant). Saute hors du kit : la jambe juge ce que le KIT
      expédie, et `.agents/IS_THE_KIT` ne voyage pas.
Chaque juge a son témoin SYNTHÉTIQUE, indépendant de l'arbre.

ÉTAT ATTENDU (réserve C3 de plan-critic 3/8, plan étape 6). Le banc juge des textes des lots A
(kickoff.md, planning SKILL, planning.md, plan_plafond.py), B (AGENTS.md, Copilot, task-board,
kickoff SKILL) et D (cinq défs orchestrator). Sur la branche du lot C SEULE, sont ROUGES :
`test_chaque_surface_porte_la_regle`, `test_la_ligne_r3_est_identique_entre_les_jumeaux`,
`test_la_ligne_r3_porte_ses_clauses_dans_leurs_segments`, `test_les_seuils_et_valeurs_sont_ceux_du_code`
— et, dans test_doctrine_registre.py, 4e sur les triplets de la règle hors context-retro et
planning-all. L'orchestrateur les rejoue après A → B → D, avant de fusionner C : develop ne voit
jamais leur rouge. Verts partout : membres, témoins synthétiques, voyage.

CE QU'IL NE VOIT PAS : la `limite` de la règle le dit — R1 non calculée, R2 non tenue par la
prose, approbation de la voie courte déclarative, paraphrase qui garde les aiguilles. ZÉRO appel
LLM, aucune énumération de l'arbre.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402

REGLE = "trois-regles-efficacite"
CE_BANC = ".agents/evals/test_trois_regles_doctrine.py"
REGISTRE = ".agents/evals/doctrine_registre.py"
#: Le code dont les constantes sont épinglées, et la config de l'envoi au gabarit.
CODE = ".agents/bin/plan_plafond.py"
EXCLUDE = ".template-exclude"
# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant » — les jambes du kit se sautent (skipUnless).
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

#: Les 14 surfaces de l'étape 6 du plan, par groupe — ÉPINGLÉES ; le roster généré n'en est pas.
ATTENDU = {
    "enonce": (
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".agents/skills/task-board/SKILL.md",
        ".agents/skills/kickoff/SKILL.md",
        ".agents/skills/planning/SKILL.md",
    ),
    "code": (
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".agents/skills/kickoff/SKILL.md",
        ".agents/skills/planning/SKILL.md",
        ".claude/commands/kickoff.md",
    ),
    "mineur": (
        ".agents/skills/task-board/SKILL.md",
        ".agents/skills/context-retro/SKILL.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".agents/skills/planning/SKILL.md",
    ),
    "plafond-8": (
        ".claude/commands/planning.md",
        ".agents/skills/planning-all/SKILL.md",
    ),
    "orchestrateur": (
        ".claude/agents/orchestrator.md",
        ".codex/agents/orchestrator.toml",
        ".gemini/agents/orchestrator.md",
        ".kimi-code/agents/orchestrator.md",
        ".github/agents/orchestrator.agent.md",
    ),
}
#: Nombre de jetons par groupe (plan étapes 5-6) et d'aiguilles du mandat de (c) : 4 classes de
#: S-00004310, la 5e de S-00004261 (C5 de 5/8), la réserve non bloquante (C1 de 4/8), le défaut
#: CRÉÉ par une ligne correctrice (S-01M51M3X9S) et le constat de sécurité qui reste bloquant
#: (revue de clôture F2). `mineur` porte aussi la route hors livraison de R2 (revue de clôture F3).
JETONS_PAR_GROUPE = {"enonce": 6, "code": 5, "mineur": 2, "plafond-8": 3, "orchestrateur": 5}
AIGUILLES_DU_MANDAT = 8
JUMEAUX = (".claude/commands/kickoff.md", ".agents/skills/kickoff/SKILL.md")

GROUPES = tuple(R.regle(REGLE)["groupes"])
LIGNE = R.regle(REGLE)["ligne_r3"]
#: Tous les jetons de la règle, sans doublon (le (4) est dans `enonce` ET dans `code`).
JETONS = tuple(dict.fromkeys(j for g in GROUPES for j in R.jetons(REGLE, g)))

#: Repères de découpe de la ligne R3 — des instruments, jamais des jetons (4d).
REPERE_A = "(a) "
REPERE_B = "(b) "
REPERE_C = "(c) "
REPERE_D = "(d) "
REPERE_E = "(e) "
REPERE_PERMISSION = "`oui` is a permission"
REPERE_PILOTE = "At `pilote`"
REPERE_APRES_PILOTE = "`FICHIERS=?`"
GUILLEMET = '"'

#: Instruments d'épinglage : (constante du code, motif cherché dans les jetons, décalage) — le
#: nombre capturé plus le décalage vaut la constante ; chaque motif prend UN jeton exactement.
SEUILS = (
    ("SEUIL_NO_GO", re.compile(r"APRÈS (\d+) NO_GO"), 0),
    ("SEUIL_NO_GO", re.compile(r"^dès le (\d+)e NO_GO"), 0),
    ("SEUIL_NO_GO", re.compile(r"jamais une (\d+)e itération"), -1),
    ("SEUIL_FICHIERS", re.compile(r"^(\d+) FICHIERS OU MOINS$"), 0),
)
VALEURS = ("VOIE_COURTE_VALEURS", re.compile(r"^VOIE_COURTE=<([^>]+)>$"))
VALEUR_SEULE = re.compile(r"^VOIE_COURTE=(\w+)$")
NON_LITTERALE = "<non littérale>"


def _texte(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- (1) présence -----------------------------------------------------------------------------
def _fautes(textes: dict[str, str], groupe: str) -> list[str]:
    """`<surface> : <jetons manquants>` pour chaque texte du groupe qui ne porte pas la règle."""
    attendus = R.jetons(REGLE, groupe)
    return [f"{rel} : {m}" for rel, t in textes.items() if (m := R.manquants(t, attendus))]


def _textes(groupe: str) -> dict[str, str]:
    return {rel: _texte(rel) for rel in R.chemins(REGLE, groupe)}


# --- (3) la ligne R3 --------------------------------------------------------------------------
def _lignes_r3(texte: str) -> list[str]:
    """Les lignes, indentation comprise, qui OUVRENT sur la marque de la ligne R3."""
    return [x for x in texte.splitlines() if x.lstrip().startswith(LIGNE["ouverture"])]


def _mandat_c(ligne: str) -> str:
    """Le mandat de (c), de son guillemet ouvrant à son guillemet fermant (exclus) ; vide sinon."""
    i = ligne.find(REPERE_C)
    j = ligne.find(GUILLEMET, i) if i >= 0 else -1
    k = ligne.find(GUILLEMET, j + 1) if j >= 0 else -1
    return ligne[j + 1: k] if k > j >= 0 else ""


def _entre(ligne: str, debut: str, fin: str) -> str:
    """De la 1re occurrence de `debut` (inclus) à la 1re `fin` qui le suit (exclue) ; vide si
    l'un des deux manque."""
    i = ligne.find(debut)
    j = ligne.find(fin, i + len(debut)) if i >= 0 else -1
    return ligne[i:j] if j > i >= 0 else ""


def _clause_a(ligne: str) -> str:
    """La clause (a), jusqu'au repère de (b) exclu."""
    return _entre(ligne, REPERE_A, REPERE_B)


def _clause_d(ligne: str) -> str:
    """La clause (d), jusqu'au repère de (e) exclu."""
    return _entre(ligne, REPERE_D, REPERE_E)


def _clause_e(ligne: str) -> str:
    """La clause (e), jusqu'à la phrase « `oui` is a permission » exclue."""
    return _entre(ligne, REPERE_E, REPERE_PERMISSION)


def _phrase_pilote(ligne: str) -> str:
    """La phrase `pilote`, jusqu'à la phrase `FICHIERS=?` exclue (ou la fin) ; vide sans repère."""
    i = ligne.find(REPERE_PILOTE)
    if i < 0:
        return ""
    j = ligne.find(REPERE_APRES_PILOTE, i)
    return ligne[i:] if j < 0 else ligne[i:j]


#: Les extracteurs de segment, par clé d'aiguilles du registre.
EXTRACTEURS = {
    "clause_a": _clause_a,
    "mandat_c": _mandat_c,
    "clause_d": _clause_d,
    "clause_e": _clause_e,
    "phrase_pilote": _phrase_pilote,
}


def _fautes_ligne(ligne: str) -> list[str]:
    """Les écarts d'UNE ligne R3 : l'absent présent, un segment introuvable, une aiguille hors
    de SON segment."""
    fautes = [f"porte {LIGNE['absent']!r}"] if LIGNE["absent"] in ligne else []
    segments = [("ligne", ligne)] + [(cle, extraire(ligne)) for cle, extraire in EXTRACTEURS.items()]
    for cle, segment in segments:
        if not segment:
            fautes.append(f"segment {cle} introuvable")
            continue
        fautes += [f"{cle} sans {a!r}" for a in LIGNE[cle] if a not in segment]
    return fautes


def _fautes_jumeaux(textes: dict[str, str]) -> list[str]:
    """Les écarts des jumeaux : ligne R3 absente ou doublée sur l'un, texte divergent."""
    fautes: list[str] = []
    lignes: dict[str, str] = {}
    for rel, t in textes.items():
        trouvees = _lignes_r3(t)
        if len(trouvees) == 1:
            lignes[rel] = trouvees[0]
        else:
            fautes.append(f"{rel} : {len(trouvees)} ligne(s) R3 au lieu d'une (lot A ou B non fusionné ?)")
    if len(lignes) == len(textes) and len(set(lignes.values())) != 1:
        fautes.append("ligne R3 divergente entre les jumeaux")
    return fautes


def _ligne_synthetique() -> tuple[str, dict[str, str]]:
    """Une ligne R3 bâtie sur les aiguilles du registre, au patron du plan (§ Texte R3), et ses
    segments TELS QUE BÂTIS (indépendants des extracteurs qu'ils jugent) : chaque aiguille dans
    son segment, les classes de (c) RÉPÉTÉES dans la phrase de permission, « human gate » AUSSI
    dans (d) — les deux masquages qu'un grep de la ligne entière subirait."""
    pilote = " ".join(LIGNE["phrase_pilote"])
    segments = {
        "clause_a": f"{REPERE_A}écrire, {' '.join(LIGNE['clause_a'])} ; ",
        "mandat_c": ", ".join(LIGNE["mandat_c"]),
        "clause_d": f"{REPERE_D}approuver sans la {pilote}, {' '.join(LIGNE['clause_d'])} reste au pilote ; ",
        "clause_e": f"{REPERE_E}renvoyer les lignes, {' '.join(LIGNE['clause_e'])}. ",
        "phrase_pilote": f"{REPERE_PILOTE} : la {pilote} de l'adoptant. ",
    }
    # Les mêmes aiguilles, dans un AUTRE ordre : muter le mandat ne touche pas la permission.
    permission = " / ".join(reversed(LIGNE["mandat_c"]))
    ligne = (
        f"   {LIGNE['ouverture']} {' · '.join(LIGNE['ligne'])} ; {segments['clause_a']}{REPERE_B}relire ; "
        f"{REPERE_C}un passage, le mandat {GUILLEMET}{segments['mandat_c']}{GUILLEMET}, journalisé ; "
        f"{segments['clause_d']}{segments['clause_e']}{REPERE_PERMISSION}, never an order: {permission}. "
        f"{segments['phrase_pilote']}{REPERE_APRES_PILOTE} : relire."
    )
    return ligne, segments


# --- (4) seuils et valeurs --------------------------------------------------------------------
def _constantes_du_code(source: str) -> dict[str, object]:
    """Les constantes épinglées affectées au niveau module de `source` (`=` ou annotée) ; une
    valeur non littérale vaut `NON_LITTERALE`, la dernière affectation l'emporte."""
    noms = {nom for nom, _, _ in SEUILS} | {VALEURS[0]}
    out: dict[str, object] = {}
    for n in ast.parse(source).body:
        if isinstance(n, ast.Assign):
            cibles, valeur = n.targets, n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            cibles, valeur = [n.target], n.value
        else:
            continue
        for c in cibles:
            if isinstance(c, ast.Name) and c.id in noms:
                try:
                    lu = ast.literal_eval(valeur)
                except ValueError:
                    lu = NON_LITTERALE
                out[c.id] = tuple(lu) if isinstance(lu, list) else lu
    return out


def _dits(jetons: tuple[str, ...]) -> tuple[dict[str, object], list[str]]:
    """Ce que les jetons DISENT des constantes du code, et les fautes de lecture : un motif qui
    ne prend pas exactement un jeton, deux jetons qui disent deux seuils, une valeur seule
    (`VOIE_COURTE=oui`) hors des valeurs dites."""
    dits: dict[str, object] = {}
    fautes: list[str] = []
    for nom, motif, decalage in SEUILS:
        prises = [m for j in jetons if (m := motif.search(j))]
        if len(prises) != 1:
            fautes.append(f"motif {motif.pattern!r} : {len(prises)} jeton(s) au lieu d'un")
            continue
        valeur = int(prises[0].group(1)) + decalage
        if dits.setdefault(nom, valeur) != valeur:
            fautes.append(f"{nom} : les jetons disent {dits[nom]} et {valeur}")
    nom, motif = VALEURS
    prises = [m for j in jetons if (m := motif.match(j))]
    if len(prises) != 1:
        fautes.append(f"motif {motif.pattern!r} : {len(prises)} jeton(s) au lieu d'un")
        return dits, fautes
    valeurs = tuple(prises[0].group(1).split("|"))
    dits[nom] = valeurs
    fautes += [
        f"{j!r} : valeur hors de {valeurs}"
        for j in jetons if (m := VALEUR_SEULE.match(j)) and m.group(1) not in valeurs
    ]
    return dits, fautes


def _fautes_seuils(constantes: dict[str, object], jetons: tuple[str, ...]) -> list[str]:
    """Les écarts entre ce que disent les jetons et les constantes du code."""
    dits, fautes = _dits(jetons)
    for nom, valeur in dits.items():
        if nom not in constantes:
            fautes.append(f"{nom} absente de {CODE} (lot A non fusionné ?)")
        elif constantes[nom] != valeur:
            fautes.append(f"{nom} = {constantes[nom]!r} au code, {valeur!r} dit par les jetons")
    return fautes


# --- (5) voyage -------------------------------------------------------------------------------
def _sync_template() -> ModuleType:
    """`sync_template`, importé comme `test_plan_depends_mirror.py` l'importe."""
    binaires = str(ROOT / ".agents" / "bin")
    if binaires not in sys.path:
        sys.path.insert(0, binaires)
    import sync_template as st

    return st


def _voyageurs() -> list[str]:
    """Ce qui doit voyager : chaque surface de la règle, le registre, ce banc, le code épinglé."""
    return sorted({s for g in GROUPES for s in R.chemins(REGLE, g)} | {REGISTRE, CE_BANC, CODE})


def _retenus(chemins: list[str], regles: list, st: ModuleType) -> list[str]:
    """`<chemin> : <règle>` pour chaque chemin qu'une règle de `.template-exclude` retient."""
    return [f"{p} : {r.raw.strip()}" for p in chemins if (r := st.match_rule(p, regles)) is not None]


class TroisReglesDoctrineTests(unittest.TestCase):
    maxDiff = None  # le rouge nomme CHAQUE surface et ses jetons manquants, jamais tronqué

    # (1) présence — ROUGE sur la branche du lot C seule (ÉTAT ATTENDU)
    def test_chaque_surface_porte_la_regle(self) -> None:
        """← un lot A, B, C ou D qui n'écrit pas un jeton de son groupe sur sa surface."""
        fautes = [f for g in GROUPES for f in _fautes(_textes(g), g)]
        self.assertEqual(fautes, [], "surfaces sans les trois règles (lots A, B, D non fusionnés ?)")

    def test_temoin_la_presence_rougit_sur_une_surface_privee_d_un_jeton(self) -> None:
        """Témoin synthétique : une surface qui porte tous les jetons passe ; privée d'UN jeton,
        elle rougit en nommant CE jeton ; vidée, elle rougit sur tous."""
        for g in GROUPES:
            attendus = R.jetons(REGLE, g)
            plein = " ".join(attendus)
            self.assertEqual(_fautes({"porte.md": plein}, g), [])
            for j in attendus:
                self.assertEqual(
                    _fautes({"porte.md": plein, "privee.md": plein.replace(j, "")}, g),
                    [f"privee.md : {[j]}"],
                )
            self.assertEqual(_fautes({"vide.md": ""}, g), [f"vide.md : {list(attendus)}"])

    # (2) membres
    def test_controle_negatif_membres_et_plancher(self) -> None:
        """L-00000232 : un balayage qui perd une surface, un jeton ou une aiguille passe à vide."""
        self.assertEqual(
            {g: R.chemins(REGLE, g) for g in GROUPES}, ATTENDU,
            "les surfaces de la règle ont changé au registre",
        )
        self.assertEqual(len({s for g in GROUPES for s in R.chemins(REGLE, g)}), 14)
        self.assertEqual({g: len(R.jetons(REGLE, g)) for g in GROUPES}, JETONS_PAR_GROUPE)
        self.assertEqual(len(LIGNE["mandat_c"]), AIGUILLES_DU_MANDAT, "une aiguille de (c) perdue")
        self.assertEqual(LIGNE["jumeaux"], JUMEAUX, "les jumeaux de la ligne R3 ont changé")
        self.assertLessEqual(set(JUMEAUX), set(R.chemins(REGLE, "code")), "un jumeau hors du groupe code")
        for cle in ("ligne", *EXTRACTEURS):
            self.assertTrue(LIGNE[cle], f"aiguilles {cle} vides")
        self.assertIn(CE_BANC, R.regle(REGLE)["bancs"])

    # (3) la ligne R3 — ROUGES sur la branche du lot C seule (ÉTAT ATTENDU)
    def test_la_ligne_r3_est_identique_entre_les_jumeaux(self) -> None:
        """← la ligne R3 changée d'un seul côté, absente ou doublée sur un jumeau."""
        fautes = _fautes_jumeaux({rel: _texte(rel) for rel in LIGNE["jumeaux"]})
        self.assertEqual(fautes, [], "ligne R3 des jumeaux kickoff")

    def test_la_ligne_r3_porte_ses_clauses_dans_leurs_segments(self) -> None:
        """← `specs.py add` réinséré ; ← `plan-critic`, `passage court` ou la mention du titre
        suffixé retirés ; ← `--files` retiré de (a) ; ← `non-blocking reserve`, une classe, le
        défaut créé par une ligne correctrice ou le constat de sécurité bloquant retirés du
        mandat de (c) ; ← `night-eligible: approved` retiré de (d) ; ← la clause des
        cinq classes retirée de (e) ; ← `human gate` retiré de la phrase `pilote` — chacun retiré
        des DEUX jumeaux, que l'identité ne voit pas."""
        for rel in LIGNE["jumeaux"]:
            lignes = _lignes_r3(_texte(rel))
            self.assertEqual(len(lignes), 1, f"{rel} : ligne R3 absente ou doublée (lot A ou B non fusionné ?)")
            self.assertEqual(_fautes_ligne(lignes[0]), [], rel)

    def test_temoin_la_ligne_r3_rougit_sur_chaque_mutation(self) -> None:
        """Témoin synthétique : la ligne juste passe ; chaque aiguille retirée de SON segment
        rougit, même quand elle reste ailleurs dans la ligne (le masquage C2) ; l'absent réinséré,
        un segment perdu et un jumeau divergent, absent ou doublé rougissent."""
        ligne, segments = _ligne_synthetique()
        self.assertEqual(_fautes_ligne(ligne), [])
        self.assertEqual(_fautes_jumeaux({"a.md": ligne, "b.md": ligne}), [])
        for cle, extraire in EXTRACTEURS.items():
            self.assertEqual(extraire(ligne), segments[cle], f"l'extracteur de {cle} ne rend plus SON segment")
            self.assertEqual(ligne.count(segments[cle]), 1, f"segment {cle} non unique : mutation ambiguë")
        mutations: dict[str, tuple[str, str]] = {}
        for cle, segment in segments.items():
            for a in LIGNE[cle]:
                mutations[f"{a!r} retiré de {cle}"] = (a, ligne.replace(segment, segment.replace(a, "")))
        for a in LIGNE["ligne"]:
            mutations[f"{a!r} retiré de la ligne"] = (a, ligne.replace(a, ""))
        for cas, (_aiguille, mutee) in mutations.items():
            self.assertNotEqual(mutee, ligne, f"{cas} : mutation sans effet")
            self.assertNotEqual(_fautes_ligne(mutee), [], cas)
        # Le masquage : l'aiguille retirée de SON segment reste ailleurs dans la ligne, et rougit.
        for cle in ("mandat_c", "phrase_pilote"):
            for a in LIGNE[cle]:
                self.assertIn(a, mutations[f"{a!r} retiré de {cle}"][1], f"{cle} : le témoin ne montre plus le masquage")
        self.assertNotEqual(_fautes_ligne(f"{ligne} {LIGNE['absent']}"), [], "absent réinséré")
        self.assertNotEqual(_fautes_ligne(ligne.replace(GUILLEMET, "")), [], "mandat sans guillemets")
        self.assertNotEqual(_fautes_ligne(ligne.replace(REPERE_B, "")), [], "(b) perdu : (a) sans fin")
        self.assertNotEqual(_fautes_ligne(ligne.replace(REPERE_E, "")), [], "(e) perdu")
        self.assertNotEqual(_fautes_ligne(ligne.replace(REPERE_PERMISSION, "")), [], "(e) sans fin")
        self.assertNotEqual(_fautes_ligne(ligne.replace(REPERE_PILOTE, "")), [], "phrase pilote perdue")
        self.assertNotEqual(_fautes_jumeaux({"a.md": ligne, "b.md": f"{ligne} "}), [], "un seul côté")
        self.assertNotEqual(_fautes_jumeaux({"a.md": ligne, "b.md": ""}), [], "absente d'un jumeau")
        self.assertNotEqual(_fautes_jumeaux({"a.md": f"{ligne}\n{ligne}", "b.md": ligne}), [], "doublée")

    # (4) seuils et valeurs — ROUGE sur la branche du lot C seule (ÉTAT ATTENDU)
    def test_les_seuils_et_valeurs_sont_ceux_du_code(self) -> None:
        """← un seuil ou une valeur de VOIE_COURTE changé d'un seul côté (code ou jetons)."""
        fautes = _fautes_seuils(_constantes_du_code(_texte(CODE)), JETONS)
        self.assertEqual(fautes, [], f"jetons de la règle et constantes de {CODE}")

    def test_temoin_l_epinglage_rougit_sur_chaque_divergence(self) -> None:
        """Témoin synthétique, indépendant du lot A : un code bâti sur ce que disent les jetons
        passe, en `=` comme annoté ; un seuil changé au code ou au registre, une valeur ajoutée,
        une constante absente ou non littérale rougissent."""
        dits, fautes = _dits(JETONS)
        self.assertEqual(fautes, [], "les jetons du registre ne disent pas les seuils")
        self.assertEqual(set(dits), {nom for nom, _, _ in SEUILS} | {VALEURS[0]})
        juste = "".join(f"{k} = {v!r}\n" for k, v in dits.items())
        self.assertEqual(_fautes_seuils(_constantes_du_code(juste), JETONS), [])
        annote = "".join(f"{k}: object = {v!r}\n" for k, v in dits.items())
        self.assertEqual(_fautes_seuils(_constantes_du_code(annote), JETONS), [])
        valeurs = dits[VALEURS[0]]
        mutees = {
            "valeur ajoutée": juste.replace(repr(valeurs), repr((*valeurs, "autre"))),
            "constante absente": "".join(x for x in juste.splitlines(True) if not x.startswith(VALEURS[0])),
            "non littérale": f"{juste}{VALEURS[0]} = tuple(range(3))\n",
        }
        for nom in {nom for nom, _, _ in SEUILS}:
            mutees[f"{nom} changé au code"] = juste.replace(f"{nom} = {dits[nom]!r}", f"{nom} = {dits[nom] + 1!r}")
        for cas, source in mutees.items():
            self.assertNotEqual(source, juste, f"{cas} : mutation sans effet")
            self.assertNotEqual(_fautes_seuils(_constantes_du_code(source), JETONS), [], cas)
        for nom, motif, _ in SEUILS:
            autres = tuple(
                motif.sub(lambda m: m.group(0).replace(m.group(1), str(int(m.group(1)) + 1), 1), j)
                for j in JETONS
            )
            self.assertNotEqual(autres, JETONS, f"{motif.pattern} : mutation sans effet")
            self.assertNotEqual(_fautes_seuils(_constantes_du_code(juste), autres), [], f"{motif.pattern} au registre")
        seule = next(j for j in JETONS if VALEUR_SEULE.match(j))
        hors = tuple(j.replace(seule, f"{seule}x") for j in JETONS)
        self.assertNotEqual(_dits(hors)[1], [], "valeur seule hors des valeurs dites")

    # (5) voyage
    @unittest.skipUnless(EST_LE_KIT, "hors du kit (pas de .agents/IS_THE_KIT) : la jambe juge ce que le kit expédie")
    def test_la_regle_voyage(self) -> None:
        """← une règle `strip:`, `keep:` ou `own:` ajoutée à `.template-exclude` sur une surface, le
        registre, ce banc ou le code épinglé : il ne serait plus repris de main."""
        st = _sync_template()
        regles = st.parse_exclude(_texte(EXCLUDE))
        self.assertEqual(_retenus(_voyageurs(), regles, st), [], "ce qui doit voyager est retenu")

    @unittest.skipUnless(EST_LE_KIT, "hors du kit (pas de .agents/IS_THE_KIT) : la jambe juge ce que le kit expédie")
    def test_temoin_une_regle_ajoutee_rougit(self) -> None:
        """Témoin synthétique sur les règles vivantes : une ligne `strip:` ajoutée pour UN
        voyageur le retient seul ; un `keep:` de répertoire en retient plusieurs."""
        st = _sync_template()
        regles = st.parse_exclude(_texte(EXCLUDE))
        voyageurs = _voyageurs()
        self.assertGreaterEqual(len(voyageurs), 17)
        for p in voyageurs:
            ajout = st.parse_exclude(f"strip: {p}\n")
            self.assertEqual(_retenus(voyageurs, regles + ajout, st), [f"{p} : strip: {p}"])
        dossier = st.parse_exclude("keep: .agents/skills/\n")
        self.assertGreater(len(_retenus(voyageurs, regles + dossier, st)), 1)


if __name__ == "__main__":
    unittest.main()
