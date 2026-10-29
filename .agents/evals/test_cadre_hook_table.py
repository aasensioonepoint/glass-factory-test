#!/usr/bin/env python3
"""`cadre.hotes_evenements` — la table événement canonique → graphie native.

Ce banc tient deux critères et trois recoupements.

* COUVERTURE DU VERROU. Chaque élément `type: evenement`, `statut: public` de
  `contract.lock.json`, privé de son préfixe `hook:`, a une ligne dans la
  table, et cette ligne a une cellule pour CHAQUE hôte de `HOTES`. La liste
  des événements est LUE dans le verrou, jamais recopiée ici : un événement
  public ajouté au verrou sans ligne dans la table fait rougir ce banc. Une
  cellule absente du registre d'un hôte existe quand même, `None` et sa
  raison — l'omission n'est pas constructible — et cette raison est tenue par
  la note du verrou, dans les deux sens. Chez un même hôte, une graphie native
  ne sert qu'un événement.
* ANTIGRAVITY. Il n'est pas une colonne (décision pilote S-00001606) : il
  hérite de gemini, et la ligne gemini porte ses graphies d'outil
  `run_command` et `apply_patch`, dans les matchers exacts du registre.
  `REGISTRES` et `HERITIERS` égalent `src/cadre/data/capacites_hotes.json`,
  qui voyage avec le noyau.
* RECOUPEMENT AVEC LES REGISTRES NATIFS (KIT-ONLY). Chaque graphie déclarée
  est une clé sous `hooks` du registre de son hôte, qui y déclare au moins
  une entrée — une clé à liste vide ne déclare rien ; chaque absence l'est
  vraiment, sous la graphie canonique comme sous sa forme camelCase ; les
  paires (clé, matcher) de `.agents/hooks.json` qui portent une graphie
  Antigravity sont EXACTEMENT celles qu'annonce la table — égalité, jamais
  inclusion. La CLÉ est vérifiée,
  jamais le numéro de ligne cité en commentaire : un registre qui gagne une
  entrée étrangère à la table ne fait pas rougir, une clé renommée oui.
* RELEVÉ R11 (KIT-ONLY, `docs/tasks/` ne voyage pas). `NON_DOCUMENTEES` est
  exactement ce que dérive la ligne R11 : les clés déclarées de la ligne
  gemini qu'aucune des deux documentations ne nomme.

Chaque détecteur est une fonction PURE, rejouée par un contrôle négatif sur une
table ou un registre mutés : un banc qui ne peut pas rougir ne mesure rien.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, chargé par chemin (`.agents/vendor/cadre`
# d'abord, `src/cadre` ensuite) : `sys.path` n'est pas touché (vendor_paths).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_hook_table_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre import hotes_evenements as he  # noqa: E402
from cadre.config import HOTES, HoteInconnu  # noqa: E402

LOCK = ROOT / "contract.lock.json"
# Son absence EST le signal « arbre adoptant », où le recoupement avec les registres
# natifs saute : l'adoptant reçoit ces registres et peut légitimement les éditer.
# adopting-tree: marqueur retiré par sync_template.py (strip:) ; une copie BRUTE l'emporte.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
SAUT_ADOPTANT = (
    "SAUT ANNONCE : arbre adoptant (marqueur .agents/IS_THE_KIT absent) — les "
    "registres natifs y appartiennent au projet, la table y reste celle du kit")
SAUT_RELEVE = (
    "SAUT ANNONCE : arbre adoptant (marqueur .agents/IS_THE_KIT absent) — le relevé "
    "R11 vit sous docs/tasks/, qui est keep: et ne voyage pas")
# Voyage avec le noyau : le paquet `cadre`, où qu'il vive, n'a aucune règle
# dans .template-exclude.
CAPACITES = _VENDOR.exiger(ROOT, "cadre") / "data" / "capacites_hotes.json"
# adopting-tree: docs/tasks/ est keep: dans .template-exclude, il ne voyage pas ; lu en KIT-ONLY.
RELEVE = ROOT / "docs" / "tasks" / "T-00000791-releve.md"


def elements_evenement() -> list[dict]:
    """Les éléments `type: evenement` du verrou, dans son ordre."""
    elements = json.loads(LOCK.read_text(encoding="utf-8"))["elements"]
    return [e for e in elements if e["type"] == "evenement"]


def canonique(element: str) -> str:
    return element.removeprefix("hook:")


def evenements_publics() -> list[str]:
    return [canonique(e["element"]) for e in elements_evenement() if e["statut"] == "public"]


def manques(table, evenements, hotes) -> list[str]:
    """Les paires (événement, hôte) sans cellule dans `table`, nommées."""
    out: list[str] = []
    for ev in evenements:
        ligne = table.get(ev)
        if ligne is None:
            out.append(f"{ev} : aucune ligne")
            continue
        out += [f"{ev}/{h} : aucune cellule" for h in hotes if h not in ligne]
    return out


def camel(nom: str) -> str:
    return nom[:1].lower() + nom[1:]


def cles_hooks(hote: str) -> set[str]:
    """Les clés du registre de `hote` qui DÉCLARENT au moins une entrée : une
    clé dont la liste est vide ne déclare rien."""
    chemin = ROOT / he.REGISTRES[hote]
    return {k for k, v in json.loads(chemin.read_text(encoding="utf-8"))["hooks"].items() if v}


def graphies_r11(texte: str) -> tuple[set[str], set[str]]:
    """Ligne R11 du relevé : (clés que la doc de Gemini CLI nomme, clés que
    celle d'Antigravity laisse « hors liste »). Les colonnes sont repérées par
    l'en-tête du tableau, jamais par leur rang."""
    lignes = texte.splitlines()
    entete = next(ligne for ligne in lignes if ligne.startswith("| # |"))
    r11 = next(ligne for ligne in lignes if ligne.startswith("| R11 |"))
    colonnes = [c.strip() for c in entete.strip().strip("|").split("|")]
    cellules = [c.strip() for c in r11.strip().strip("|").split("|")]
    gemini = cellules[colonnes.index("Gemini CLI")]
    antigravity = cellules[colonnes.index("Antigravity")]
    nommees = re.search(r"\*\*\d+/\d+\*\* \(([^)]*)\) dans la liste", gemini)
    hors = re.search(r"((?:`\w+`(?:, )?)+) hors liste", antigravity)
    return (set(re.findall(r"`(\w+)`", nommees.group(1))) if nommees else set(),
            set(re.findall(r"`(\w+)`", hors.group(1))) if hors else set())


def ecarts_registre(table, hote: str, cles: set[str]) -> list[str]:
    """Ce que la table dit de `hote` et que son registre (`cles`) dément."""
    out: list[str] = []
    for ev, ligne in table.items():
        g = ligne[hote]
        if g.natif is not None:
            if g.natif not in cles:
                out.append(f"{ev}/{hote} : {g.natif!r} absent du registre")
        else:
            out += [f"{ev}/{hote} : dit absent, mais le registre declare {v!r}"
                    for v in sorted({ev, camel(ev)}) if v in cles]
    return out


def porteurs_de(hooks: dict, graphie: str) -> set[tuple[str, str]]:
    """Les paires (clé native, matcher) du registre dont le matcher porte
    `graphie` comme alternative ENTIÈRE — jamais par sous-chaîne."""
    return {(ev, m) for ev, es in hooks.items() for m in (e.get("matcher") for e in es)
            if m and graphie in m.split("|")}


def attendus(g, evenements, matcher: str) -> set[tuple[str, str]]:
    """Les paires (clé native, matcher) que `GRAPHIES_ANTIGRAVITY` annonce."""
    return {(he.TABLE[ev][g.porteur].natif, matcher) for ev in evenements}


def table_sans(table, ev: str, hote: str | None = None):
    """Une copie de `table` privée d'une ligne, ou d'une seule cellule."""
    copie = {e: dict(c) for e, c in table.items()}
    if hote is None:
        del copie[ev]
    else:
        del copie[ev][hote]
    return MappingProxyType({e: MappingProxyType(c) for e, c in copie.items()})


class CouvertureDuVerrouTests(unittest.TestCase):
    """Critère : chaque événement canonique public du verrou a une entrée par hôte."""

    def test_le_verrou_declare_des_evenements_publics(self):
        publics = evenements_publics()
        self.assertTrue(publics, "aucun evenement public lu : le banc serait vert par vacuite")
        self.assertTrue(all(e["element"].startswith("hook:") for e in elements_evenement()),
                        "un element `evenement` sans prefixe hook: — la derivation du nom canonique ment")

    def test_chaque_evenement_public_du_verrou_a_une_entree_par_hote(self):
        self.assertEqual(manques(he.TABLE, evenements_publics(), HOTES), [])

    def test_la_table_ne_porte_aucun_evenement_hors_du_verrou(self):
        connus = {canonique(e["element"]) for e in elements_evenement()}
        self.assertEqual(sorted(set(he.TABLE) - connus), [],
                         "un evenement de la table n'existe pas au verrou")

    def test_les_colonnes_sont_exactement_HOTES(self):
        self.assertEqual(set(he.REGISTRES), set(HOTES))
        for ev, ligne in he.TABLE.items():
            self.assertEqual(set(ligne), set(HOTES), ev)

    def test_EVENEMENTS_suit_l_ordre_du_verrou(self):
        ordre = [canonique(e["element"]) for e in elements_evenement()]
        self.assertEqual(list(he.EVENEMENTS), [e for e in ordre if e in he.TABLE])

    def test_toute_absence_porte_sa_raison(self):
        for ev, ligne in he.TABLE.items():
            for h, g in ligne.items():
                with self.subTest(evenement=ev, hote=h):
                    if g.natif is None:
                        self.assertTrue(g.raison and g.raison.strip())
                        self.assertIn(he.REGISTRES[h], g.raison)
                    else:
                        self.assertIsNone(g.raison)

    def test_une_cellule_vide_sans_raison_n_est_pas_constructible(self):
        for args, kw in (((None,), {}), ((None,), {"raison": "  "}),
                         (("",), {}), (("Stop",), {"raison": "x"})):
            with self.subTest(args=args, kw=kw), self.assertRaises(ValueError):
                he.Graphie(*args, **kw)

    def test_la_table_est_figee(self):
        with self.assertRaises(TypeError):
            he.TABLE["Stop"] = {}  # type: ignore[index]
        with self.assertRaises(TypeError):
            he.TABLE["Stop"]["kimi"] = he.Graphie("x")  # type: ignore[index]

    def test_le_controle_negatif_mord(self):
        """Une cellule retirée, puis une ligne retirée : le détecteur les NOMME."""
        publics = evenements_publics()
        ev, h = publics[-1], HOTES[-1]
        self.assertEqual(manques(table_sans(he.TABLE, ev, h), publics, HOTES),
                         [f"{ev}/{h} : aucune cellule"])
        self.assertEqual(manques(table_sans(he.TABLE, ev), publics, HOTES),
                         [f"{ev} : aucune ligne"])
        self.assertEqual(manques(he.TABLE, publics + ["EvenementNeuf"], HOTES),
                         ["EvenementNeuf : aucune ligne"])

    def test_la_raison_d_absence_est_tenue_par_la_note_du_verrou(self):
        """Dans les deux sens : une absence s'adosse à la note « DECLARE par
        Claude Code SEUL » du verrou, et une telle note vide toutes les
        colonnes sauf claude."""
        phrase = "DECLARE par Claude Code SEUL"
        notes = {canonique(e["element"]): e.get("note", "") for e in elements_evenement()}
        for ev, ligne in he.TABLE.items():
            absents = {h for h, g in ligne.items() if g.natif is None}
            with self.subTest(evenement=ev):
                if absents:
                    self.assertIn(phrase, notes[ev])
                    for h in absents:
                        self.assertIn(phrase, ligne[h].raison)
                if phrase in notes[ev]:
                    self.assertEqual(absents, set(HOTES) - {"claude"})

    def test_une_graphie_native_ne_sert_qu_un_evenement_par_hote(self):
        for h in HOTES:
            vals = [ligne[h].natif for ligne in he.TABLE.values() if ligne[h].natif]
            with self.subTest(hote=h):
                self.assertEqual(len(vals), len(set(vals)), h)


class AntigravityTests(unittest.TestCase):
    """Critère : la table expose les graphies Antigravity, portées par gemini."""

    def test_antigravity_n_est_pas_une_colonne(self):
        self.assertNotIn("antigravity", HOTES)
        self.assertNotIn("antigravity", he.REGISTRES)
        self.assertEqual(he.HERITIERS["antigravity"], "gemini")

    def test_la_ligne_gemini_porte_run_command_et_apply_patch(self):
        g = he.GRAPHIES_ANTIGRAVITY
        self.assertEqual(g.porteur, "gemini")
        self.assertEqual((g.shell, g.edition), ("run_command", "apply_patch"))
        self.assertIn("run_command", g.matcher_shell.split("|"))
        self.assertIn("apply_patch", g.matcher_edition.split("|"))
        self.assertTrue(g.evenements_shell and g.evenements_edition)

    def test_un_matcher_qui_perd_la_graphie_n_est_pas_constructible(self):
        g = he.GRAPHIES_ANTIGRAVITY
        base = dict(porteur=g.porteur, shell=g.shell, edition=g.edition,
                    matcher_shell=g.matcher_shell, matcher_edition=g.matcher_edition,
                    evenements_shell=g.evenements_shell,
                    evenements_edition=g.evenements_edition)
        for cle, val in (("matcher_shell", "Bash"), ("matcher_edition", "Edit|Write"),
                         ("porteur", "antigravity"), ("evenements_shell", ("SessionEnd",))):
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                he.GraphiesAntigravity(**{**base, cle: val})

    def test_chaque_cellule_non_documentee_porte_sa_graphie_declaree(self):
        """`NON_DOCUMENTEES` nomme des cellules DÉCLARÉES : une seule graphie
        par cellule, la déclarée, jamais une absence ni une seconde graphie."""
        self.assertTrue(he.NON_DOCUMENTEES)
        for ev, h in he.NON_DOCUMENTEES:
            with self.subTest(evenement=ev, hote=h):
                self.assertIn(h, HOTES)
                self.assertIsInstance(he.TABLE[ev][h], he.Graphie)
                self.assertIsNotNone(he.TABLE[ev][h].natif)

    def test_registres_et_heritiers_egalent_capacites_hotes(self):
        hotes = json.loads(CAPACITES.read_text(encoding="utf-8"))["hotes"]
        self.assertEqual({h: v["registre_natif"] for h, v in hotes.items() if "herite_de" not in v},
                         dict(he.REGISTRES))
        self.assertEqual({h: v["herite_de"] for h, v in hotes.items() if "herite_de" in v},
                         dict(he.HERITIERS))
        for h, porteur in he.HERITIERS.items():
            with self.subTest(heritier=h):
                self.assertEqual(hotes[h]["registre_natif"], he.REGISTRES[porteur])


class NatifTests(unittest.TestCase):

    def test_rend_la_graphie_ou_None(self):
        self.assertEqual(he.natif("Stop", "copilot"), "agentStop")
        self.assertEqual(he.natif("PreToolUse", "gemini"), "PreToolUse")
        self.assertIsNone(he.natif("SessionEnd", "codex"))

    def test_le_refus_est_un_type(self):
        with self.assertRaises(he.EvenementInconnu):
            he.natif("BeforeTool", "gemini")
        for hote in ("antigravity", "Claude", ""):
            with self.subTest(hote=hote), self.assertRaises(HoteInconnu):
                he.natif("Stop", hote)
        with self.assertRaises(HoteInconnu) as cm:
            he.natif("Stop", "antigravity")
        self.assertIn("herite de 'gemini'", str(cm.exception))
        self.assertIn("--host gemini", str(cm.exception))
        with self.assertRaises(HoteInconnu) as cm:
            he.natif("Stop", "Claude")
        self.assertNotIn("--host", str(cm.exception),
                         "un hote qui n'herite de rien n'est route vers aucun porteur")

    def test_un_argument_non_chaine_est_refuse_par_son_type(self):
        """Jamais un `TypeError` : une liste n'est pas hachable, et le refus
        doit rester celui que l'appelant attrape."""
        for hote in (["gemini"], None, 3):
            with self.subTest(hote=hote), self.assertRaises(HoteInconnu):
                he.natif("Stop", hote)
        for ev in (["Stop"], None):
            with self.subTest(evenement=ev), self.assertRaises(he.EvenementInconnu):
                he.natif(ev, "gemini")


@unittest.skipUnless(EST_LE_KIT, SAUT_RELEVE)
class ReleveR11Tests(unittest.TestCase):
    """KIT-ONLY : `NON_DOCUMENTEES` est exactement ce que dérive la ligne R11."""

    def test_NON_DOCUMENTEES_est_exactement_ce_que_derive_le_releve_R11(self):
        nommees_gemini, hors_liste = graphies_r11(RELEVE.read_text(encoding="utf-8"))
        self.assertTrue(nommees_gemini and hors_liste,
                        "ligne R11 illisible : le banc serait vert par vacuite")
        natives = {ligne["gemini"].natif: ev for ev, ligne in he.TABLE.items()
                   if ligne["gemini"].natif}
        attendu = {(natives[n], "gemini") for n in (set(natives) & hors_liste) - nommees_gemini}
        self.assertEqual(set(he.NON_DOCUMENTEES), attendu)

    def test_le_controle_negatif_du_releve_mord(self):
        """La dérivation suit le texte : Gemini CLI qui nomme aussi `PreCompact`
        retire cette clé de l'attendu."""
        texte = RELEVE.read_text(encoding="utf-8")
        avant = "**1/6** (`SessionStart`) dans la liste"
        self.assertEqual(texte.count(avant), 1)
        nommees, _ = graphies_r11(texte.replace(avant, "**2/6** (`SessionStart`, `PreCompact`) dans la liste"))
        self.assertEqual(nommees, {"SessionStart", "PreCompact"})


@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class RecoupementAvecLesRegistresTests(unittest.TestCase):
    """KIT-ONLY : la table dit ce que les registres natifs du kit déclarent."""

    def test_chaque_cellule_est_tenue_par_le_registre_de_son_hote(self):
        for h in HOTES:
            with self.subTest(hote=h):
                self.assertEqual(ecarts_registre(he.TABLE, h, cles_hooks(h)), [])

    @staticmethod
    def _hooks_du_porteur() -> dict:
        g = he.GRAPHIES_ANTIGRAVITY
        return json.loads((ROOT / he.REGISTRES[g.porteur]).read_text(encoding="utf-8"))["hooks"]

    def test_les_matchers_antigravity_sont_exactement_ceux_du_registre_gemini(self):
        """ÉGALITÉ, jamais inclusion : une entrée du registre qui porte la
        graphie sous un autre événement ou un autre matcher rougit aussi."""
        g = he.GRAPHIES_ANTIGRAVITY
        hooks = self._hooks_du_porteur()
        for graphie, evenements, matcher in ((g.shell, g.evenements_shell, g.matcher_shell),
                                             (g.edition, g.evenements_edition, g.matcher_edition)):
            with self.subTest(graphie=graphie):
                self.assertEqual(porteurs_de(hooks, graphie), attendus(g, evenements, matcher))

    def test_le_controle_negatif_des_matchers_mord_dans_les_deux_sens(self):
        """Une entrée EN TROP, puis une entrée EN MOINS : le détecteur nomme les deux."""
        g = he.GRAPHIES_ANTIGRAVITY
        hooks = self._hooks_du_porteur()
        attendu = attendus(g, g.evenements_shell, g.matcher_shell)
        post = he.TABLE["PostToolUse"][g.porteur].natif
        en_trop = {ev: list(es) for ev, es in hooks.items()}
        en_trop[post] = en_trop[post] + [{"matcher": g.matcher_shell, "hooks": []}]
        self.assertEqual(porteurs_de(en_trop, g.shell) - attendu, {(post, g.matcher_shell)})
        en_moins = {ev: [e for e in es if e.get("matcher") != g.matcher_shell]
                    for ev, es in hooks.items()}
        self.assertEqual(attendu - porteurs_de(en_moins, g.shell), attendu)
        self.assertEqual(porteurs_de({post: [{"matcher": g.shell + "2"}]}, g.shell), set(),
                         "une sous-chaine ne porte pas la graphie")

    def test_le_controle_negatif_du_recoupement_mord(self):
        """Une graphie renommée, puis une absence démentie : les deux rougissent."""
        cles = cles_hooks("copilot")
        self.assertEqual(ecarts_registre(he.TABLE, "copilot", cles - {"agentStop"}),
                         ["Stop/copilot : 'agentStop' absent du registre"])
        self.assertEqual(ecarts_registre(he.TABLE, "copilot", cles | {"sessionEnd"}),
                         ["SessionEnd/copilot : dit absent, mais le registre declare 'sessionEnd'"])
        self.assertEqual(ecarts_registre(he.TABLE, "copilot", cles | {"userPromptSubmitted"}), [],
                         "une cle etrangere a la table ne doit pas rougir")


if __name__ == "__main__":
    unittest.main()
