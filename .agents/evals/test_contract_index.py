#!/usr/bin/env python3
"""TEMOINS DE L'INDEX DU CONTRAT ET DES TROIS NOMS ADOPTANTS — banc du check
`contract_diff` (T-00000626, absorbe T-00000733).

POURQUOI UN FICHIER A PART. `test_contract_diff.py` porte le check, mais il faisait
798 lignes et la regle des 800 (S-00002684, relevee a 1600 par S-00004034) interdisait d'y ajouter ces temoins :
c'est un SECOND BANC du meme check, pas un check neuf, donc aucune entree au
`checks.manifest.json`. CONTRAT-v0.md le nomme a cote du premier. Il est
AUTONOME — il relit le verrou et la doc lui-meme et n'importe pas
`test_contract_diff`, qui serait sinon collecte deux fois.

CE QU'IL TIENT, QUATRE CHOSES QUE `test_contract_diff` NE VOYAIT PAS :

1. La phrase de comptage de CONTRAT-v0.md § 7 (« Les N identifiants exacts du
   verrou — P publics et R reserves ») etait recopiee A LA MAIN. Personne ne la
   derivait : la revision 1 du plan de T-00000626 visait 51/22 quand le verrou
   disait 52/21, exactement la faute que T-00000733 nomme. Elle est desormais
   DERIVEE du verrou, et la table de § 7 est comparee au verrou dans les DEUX
   sens — `test_chaque_element_public_est_nomme_dans_la_doc` ne regarde que les
   `public`, donc une ligne `reserve` manquante ou orpheline passait. Toute ligne
   de § 7 ouvrant sur `|`, ou dans le bloc de la table sans `|` initial (forme
   GFM), qui n'est ni l'en-tete, ni le separateur, ni une ligne lisible est un
   echec NOMME, jamais un filtrage silencieux.
2. Les trois points d'entree adoptants `cadre tasks|ledger|specs` sont reserves
   en Phase 3 (`introduit_en: "3"`, le moment de l'EDITION du verrou) et
   apportes en Phase 4 (`RESERVEES[nom] == "4"`, la LIVRAISON) — S-00001601.
   `"0bis"` au lieu de `"3"` passerait `test_chaque_entree_est_bien_formee` ;
   seul ce temoin le voit. Leurs notes ne designent aucun chemin du paquet
   (`src/cadre` ni `.agents/vendor/cadre`) : le verrou est public, le noyau prive (CONTRAT-v0.md:4).
3. La ligne « **Version du contrat** : `x` » de CONTRAT-v0.md, recopiee a la
   main elle aussi, egale `version_contrat` du verrou.
4. La prose « Restent **réservés** : » de CONTRAT-v0.md nomme chacun des trois
   noms adoptants SI ET SEULEMENT SI le verrou le dit `reserve` : une
   promotion qui oublie la prose, ou une prose qui en perd un, rougit
   (critic-fable F2).

5. Les invariants de SECTION de T-00000664 (rev. 1), rendus PERMANENTS par
   T-00001118 (`InvariantsDesSectionsTests`), W1 a W6 DERIVES du verrou ou de
   pyproject.toml, jamais d'un compte recopie : chaque `variable` du verrou est
   nommee dans la prose de § 3.4 (W1) ; les `cli` publics du verrou sont
   EXACTEMENT les noms du BLOC « **Sont implémentées, donc publiques** : » de
   § 3.1, dans les deux sens, et chacun est nomme hors du paragraphe « Restent
   **réservés** : » (W2, plus strict que le temoin d'origine : un nom promu au
   verrou que § 3.1 cite AILLEURS que dans ce bloc — `cadre disarm`, « mérite
   son mot » — rougit, comme un nom que le bloc dit livre sans etre public) ;
   chaque `surface` est nommee dans § 3.8, et aucun paragraphe de
   § 3.8 ni item de § 6 qui nomme une surface `reserve` ne la dit promise (W3) ;
   § 3.6 ne recopie aucun compte par format (W5) ; la ligne « Nom de la
   distribution » de § 5 egale `project.name` de pyproject.toml (W6) ; le
   contrat EMBARQUE ne porte aucun identifiant interne du kit — tache,
   decision, lecon, epic, groupe parallele ou symbole (`T-`, `S-`, `L-`, `E-`,
   `PG-`, `SYM-`), en forme longue, courte ou ULID — ni « wheel » (W9, porte par
   T-00001154, elargi par T-00001161 ; il lit la doc seule, il voyage chez
   l'adoptant). NON
   PORTES, faute de forme durable : W4 (prose sur l'introspection), W7 (un
   nombre dans une note), W8 (la spec, pas le contrat), et les noms du depot de
   publication de W6 (aucune source de verite au depot).

BORNE ECRITE : aucune assertion sur l'ENSEMBLE des `reserve` — un filet plus
large graverait un accident d'historique plutot qu'une decision.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "contract.lock.json"
DOC = ROOT / "docs" / "contrat" / "CONTRAT-v0.md"
# OU vit le paquet `cadre` : `vendor_paths` charge PAR CHEMIN (patron v3prep,
# T-01M5BXTPQE3JZV3KZA6WD9P5XC) ; absent des deux lieux, `CLI` nomme l'ancien et
# `setUp` echoue en le disant.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_contract_index_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
CLI = (_VENDOR.dossier_paquet(ROOT, "cadre") or ROOT / _VENDOR.ANCIENS["cadre"]) / "cli.py"
# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant ».
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
# adopting-tree: le manifeste de la distribution ne voyage pas (strip: pyproject.toml,
# S-00004099) ; hors du kit, W6 n'a de sujet que s'il declare `cadre-kit`.
PYPROJECT = ROOT / "pyproject.toml"
SAUT_DISTRIBUTION = (
    "SAUT ANNONCE : arbre adoptant (marqueur .agents/IS_THE_KIT absent) dont pyproject.toml "
    "ne declare pas la distribution `cadre-kit` — le manifeste du kit ne voyage pas "
    "(strip: pyproject.toml) : W6 n'a pas de sujet ici")


def distribution_hors_sujet() -> bool:
    """Vrai sur un arbre ADOPTANT dont `pyproject.toml` ne declare pas `cadre-kit` :
    absent (il ne voyage pas) ou celui du projet adoptant. JAMAIS vrai dans le kit, ou
    un manifeste absent, illisible ou renomme reste un ECHEC de W6."""
    if EST_LE_KIT:
        return False
    try:
        charge = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        return True
    projet = charge.get("project")
    return not (isinstance(projet, dict) and projet.get("name") == "cadre-kit")

PHRASE_DE_COMPTAGE = re.compile(
    r"Les (\d+) identifiants exacts du verrou — \*\*(\d+) publics et (\d+) réservés\*\*")
LIGNE_DE_VERSION = re.compile(r"\*\*Version du contrat\*\* : `([^`]+)`")
# Une ligne de table porte l'identifiant ENTRE BACKTICKS : l'en-tete
# `| Identifiant | Type | Statut |` et le separateur `|---|` ne matchent donc pas.
LIGNE_DE_TABLE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*$")
# Les DEUX seules lignes `|` admises hors LIGNE_DE_TABLE. Toute autre ligne `|`
# de § 7 est ILLISIBLE et nommee : filtree en silence, une ligne sans backticks
# ou a 4 colonnes sortait de la comparaison et le temoin restait vert. De meme
# toute ligne du BLOC de la table (de l'en-tete a la premiere ligne vide) : GFM
# admet une ligne sans `|` initial, qui echappait au filtre (critic-opus C3).
EN_TETE = "| Identifiant | Type | Statut |"
SEPARATEUR = "|---|---|---|"
TITRE_INDEX = "## 7. Index des identifiants"
NOMS = ("tasks", "ledger", "specs")
OUVERTURE_RESERVES = "Restent **réservés** :"
OUVERTURE_PUBLICS = "**Sont implémentées, donc publiques** :"
# Un nom de la CLI dans la prose : `cadre` seul ou `cadre <suite>`, entre backticks.
NOM_CLI = re.compile(r"`(cadre(?: [^`]+)?)`")
# La ligne de § 5 qui nomme la distribution : valeur en gras ET entre backticks.
LIGNE_DISTRIBUTION = re.compile(r"^\|\s*Nom de la distribution\s*\|\s*\*\*`([^`]+)`\*\*")
# La famille de « promettre » (promet, promettent, promis, promise), PAS
# « promesse(s) » : § 6, item 1, dit « les trois promesses du contrat de hook ».
PROMESSE = re.compile(r"\bprom(?:et|is)\w*", re.I)
COMPTE_PAR_FORMAT = re.compile(r"\b\d+\s+(?:Markdown|TOML)\b")
DEBUT_D_ITEM = re.compile(r"^\d+\.\s")
# W9 : un identifiant interne du kit, en forme longue (`T-00000753`), courte
# (`T-753`) OU ULID (26 caracteres Crockford, `T-01HZX5Q8N9ABCDEFGHJKMNPQRS` —
# reserve critic-opus F9 de la fournee 6) — tache `T-`, decision `S-`, lecon
# `L-`, epic `E-`, groupe parallele `PG-`, symbole de l'index `SYM-` (les quatre
# derniers ajoutes par la decision pilote S-00004058, T-00001161) — et « wheel »
# a toute casse (reserve A-C5 de T-00000626). Le temoin d'origine ne voyait que
# `T-0000` / `S-0000`. Un code d'erreur ou une plage de meme forme (`E-1`,
# `L-1`) rougit aussi : la prose du contrat la reecrit, le motif ne s'assouplit
# pas.
IDENTIFIANT_INTERNE = re.compile(
    r"\b(?:[TSLE]|PG|SYM)-(?:\d+|[0-9A-HJKMNP-TV-Z]{26})\b|\b(?i:wheel)")


def _elements() -> list[dict]:
    return json.loads(LOCK.read_text(encoding="utf-8"))["elements"]


def _section_index(texte: str) -> list[str] | None:
    """Les lignes de la section § 7, jusqu'au prochain titre `## ` ou la fin."""
    lignes = texte.splitlines()
    debut = next((i for i, ligne in enumerate(lignes) if ligne.rstrip() == TITRE_INDEX),
                 None)
    if debut is None:
        return None
    fin = next((i for i in range(debut + 1, len(lignes)) if lignes[i].startswith("## ")),
               len(lignes))
    return lignes[debut + 1:fin]


def _section_titree(texte: str, prefixe: str) -> list[str] | None:
    """Le titre (ligne 0) PUIS le corps de la section dont le titre ouvre par
    `prefixe` (`### 3.4 `, `## 5. `), jusqu'au prochain titre de niveau inferieur
    ou egal ; None si le titre est absent. Adapte de `section()` des temoins de
    T-00000664 (rev. 1)."""
    lignes = texte.splitlines()
    niveau = len(prefixe.split(" ", 1)[0])
    debut = next((i for i, ligne in enumerate(lignes) if ligne.startswith(prefixe)), None)
    if debut is None:
        return None
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        tete = lignes[j].split(" ", 1)[0]
        if tete and set(tete) == {"#"} and len(tete) <= niveau:
            fin = j
            break
    return lignes[debut:fin]


def _blocs(lignes: list[str]) -> list[str]:
    """Paragraphes ET items numerotes (`1. `), espaces normalises : un nom coupe
    en fin de ligne se relit entier. Les items de § 6 ne sont separes par aucune
    ligne vide, d'ou la coupure au debut d'item."""
    blocs: list[str] = []
    courant: list[str] = []
    for ligne in [*lignes, ""]:
        if (not ligne.strip() or DEBUT_D_ITEM.match(ligne)) and courant:
            blocs.append(" ".join(courant))
            courant = []
        if ligne.strip():
            courant.append(ligne.strip())
    return blocs


class IndexDuContratTests(unittest.TestCase):
    def setUp(self):
        for chemin in (LOCK, DOC):
            if not chemin.is_file():
                self.fail(f"{chemin.relative_to(ROOT)} absent — livrable de la Phase 0bis")
        self.elements = _elements()
        self.texte = DOC.read_text(encoding="utf-8")

    def test_la_phrase_de_comptage_derive_du_verrou(self):
        total = len(self.elements)
        nb_public = sum(1 for e in self.elements if e["statut"] == "public")
        nb_reserve = sum(1 for e in self.elements if e["statut"] == "reserve")
        trouvees = PHRASE_DE_COMPTAGE.findall(self.texte)
        self.assertEqual(
            len(trouvees), 1,
            f"CONTRAT-v0.md doit porter UNE phrase « Les N identifiants exacts du "
            f"verrou — **P publics et R réservés** », trouvees : {trouvees}")
        self.assertEqual(
            tuple(int(x) for x in trouvees[0]), (total, nb_public, nb_reserve),
            "la phrase de comptage de CONTRAT-v0.md § 7 ment sur le verrou "
            f"(doc {trouvees[0]} ; verrou {total} / {nb_public} / {nb_reserve}) : "
            "la recopier depuis contract.lock.json, jamais a la main")
        # BORNE VOULUE : un premier `deprecie` rougit ici, parce que la phrase ne
        # le compterait pas. Le remede est d'etendre la phrase, jamais ce test.
        self.assertEqual(
            total, nb_public + nb_reserve,
            "un statut hors public/reserve est apparu au verrou : la phrase de "
            "comptage ne le nomme pas — l'etendre")

    def test_l_index_de_la_doc_egale_le_verrou(self):
        section = _section_index(self.texte)
        if section is None:
            self.fail(f"CONTRAT-v0.md ne porte plus la section « {TITRE_INDEX} »")
        tete = next((i for i, l in enumerate(section) if l.rstrip() == EN_TETE), None)
        fin = tete
        while fin is not None and fin < len(section) and section[fin].strip():
            fin += 1
        dans_le_bloc = set() if tete is None else set(range(tete, fin))
        illisibles = [ligne for i, ligne in enumerate(section)
                      if (i in dans_le_bloc or ligne.lstrip().startswith("|"))
                      and ligne.rstrip() not in (EN_TETE, SEPARATEUR)
                      and not LIGNE_DE_TABLE.match(ligne)]
        self.assertEqual(
            illisibles, [],
            "lignes illisibles dans l'index de CONTRAT-v0.md § 7 (ouvrant sur `|`, ou "
            "dans le bloc de la table sans `|` initial, forme GFM) — ni l'en-tete, "
            "ni le separateur, ni « | `identifiant` | type | statut | » : elles "
            "sortiraient de la comparaison au verrou EN SILENCE")
        lignes = [m.groups() for ligne in section if (m := LIGNE_DE_TABLE.match(ligne))]
        self.assertTrue(lignes, "table de § 7 vide ou illisible — la comparaison serait vide")
        doublons = sorted({t for t in lignes if lignes.count(t) > 1})
        self.assertEqual(doublons, [], f"lignes en double dans l'index de § 7 : {doublons}")
        doc = set(lignes)
        verrou = {(e["element"], e["type"], e["statut"]) for e in self.elements}
        self.assertEqual(
            (sorted(verrou - doc), sorted(doc - verrou)), ([], []),
            "l'index de CONTRAT-v0.md § 7 differe du verrou — (au verrou et absents "
            "de la doc, dans la doc et absents du verrou)")

    def test_la_version_de_la_doc_egale_le_verrou(self):
        verrou = json.loads(LOCK.read_text(encoding="utf-8"))["version_contrat"]
        trouvees = LIGNE_DE_VERSION.findall(self.texte)
        self.assertEqual(
            len(trouvees), 1,
            "CONTRAT-v0.md doit porter UNE ligne « **Version du contrat** : `x` », "
            f"trouvees : {trouvees}")
        self.assertEqual(
            trouvees[0], verrou,
            f"CONTRAT-v0.md annonce la version {trouvees[0]!r}, le verrou porte "
            f"version_contrat {verrou!r} : la recopier depuis contract.lock.json")

    def test_la_prose_des_reserves_suit_le_statut_des_trois_noms(self):
        trouve = re.search(r"^Restent \*\*réservés\*\* :(.*?)\n\n", self.texte, re.S | re.M)
        self.assertIsNotNone(trouve, "« Restent **réservés** : » introuvable")
        par_nom = {e["element"]: e for e in self.elements}
        for nom in NOMS:
            with self.subTest(nom=nom):
                self.assertEqual(f"`cadre {nom}`" in trouve.group(1),
                                 par_nom[f"cadre {nom}"]["statut"] == "reserve")


class ReservesAdoptantsTests(unittest.TestCase):
    def setUp(self):
        for chemin in (LOCK, CLI):
            if not chemin.is_file():
                self.fail(f"{chemin.relative_to(ROOT)} absent")

    @staticmethod
    def _reservees() -> dict[str, str]:
        """`RESERVEES` lue dans le module REEL, patron de `_cli_reelle`."""
        spec = importlib.util.spec_from_file_location("cadre_cli_reserves_adoptants", CLI)
        if spec is None or spec.loader is None:
            raise AssertionError(f"{CLI} illisible comme module")
        module = importlib.util.module_from_spec(spec)
        _VENDOR.charger_paquet(ROOT, "cadre")
        # ENREGISTRER AVANT D'EXECUTER : hors de `sys.modules`, dataclasses et
        # imports relatifs cassent de facon differee.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return dict(module.RESERVEES)

    def test_les_trois_noms_adoptants_sont_reserves_et_livres_en_phase_4(self):
        reservees = self._reservees()
        par_nom = {e["element"]: e for e in _elements()}
        for nom in NOMS:
            with self.subTest(nom=nom):
                entree = par_nom.get(f"cadre {nom}")
                self.assertIsNotNone(entree, f"`cadre {nom}` absent de contract.lock.json")
                self.assertIn(
                    nom, reservees,
                    f"`{nom}` absent de RESERVEES : s'il est IMPLEMENTE (Phase 4), "
                    "reecrire CE temoin dans le meme commit (statut public, promotion "
                    "reserve->public) — ne jamais le remettre en RESERVEES ; sinon "
                    "reservation perdue")
                with self.subTest(nom=nom, borne="verrou"):
                    self.assertEqual((entree["type"], entree["statut"]), ("cli", "reserve"))
                    self.assertEqual(
                        entree["introduit_en"], "3",
                        f"`cadre {nom}` : introduit_en suit l'edition du verrou "
                        "(LOT-3), pas la livraison")
                with self.subTest(nom=nom, borne="RESERVEES"):
                    self.assertEqual(
                        reservees[nom], "4",
                        f"RESERVEES[{nom!r}] : la phase qui APPORTE le nom est la 4")
                with self.subTest(nom=nom, borne="note"):
                    self.assertTrue(
                        entree["note"].rstrip().endswith(f"Phase {reservees[nom]}."),
                        f"la note de `cadre {nom}` doit FINIR par la phase de "
                        f"RESERVEES (« Phase {reservees[nom]}. »)")
                    # Le verrou est PUBLIC et CONTRAT-v0.md:4 dit le noyau prive :
                    # une note adoptant ne designe aucun chemin du paquet, a
                    # l'un OU l'autre de ses deux emplacements.
                    for lieu in ("src/cadre", ".agents/vendor/cadre"):
                        self.assertNotIn(
                            lieu, entree["note"],
                            f"la note de `cadre {nom}` designe un chemin du noyau prive")


class InvariantsDesSectionsTests(unittest.TestCase):
    """Point 5 de l'en-tete : W1, W2, W3, W5, W6 et W9 de T-00000664 (rev. 1).
    W1 a W6 lisent le verrou (ou pyproject.toml) : un element ajoute ou promu
    au verrou sans la prose de sa section rougit ici. W9 lit la doc seule.
    Une section absente est un echec NOMME, jamais une comparaison vide qui
    passerait. Hors du kit, pyproject.toml n'est pas exige (il ne voyage pas) :
    seul W6 le lit, et W6 se saute alors en le disant (S-00004099)."""

    def setUp(self):
        for chemin in (LOCK, DOC, PYPROJECT) if EST_LE_KIT else (LOCK, DOC):
            if not chemin.is_file():
                self.fail(f"{chemin.relative_to(ROOT)} absent")
        self.elements = _elements()
        self.texte = DOC.read_text(encoding="utf-8")

    def _section(self, prefixe: str) -> list[str]:
        lignes = _section_titree(self.texte, prefixe)
        if lignes is None:
            self.fail(f"CONTRAT-v0.md ne porte plus de titre ouvrant par « {prefixe.strip()} »")
        return lignes

    def _noms(self, type_: str, statut: str | None = None) -> list[str]:
        noms = [e["element"] for e in self.elements
                if e["type"] == type_ and statut in (None, e["statut"])]
        if statut is None:
            self.assertTrue(noms, f"aucun element `{type_}` au verrou : le temoin ne mesurerait rien")
        return noms

    def test_W1_chaque_variable_du_verrou_est_nommee_au_3_4(self):
        corps = " ".join(_blocs(self._section("### 3.4 ")[1:]))
        absentes = [v for v in self._noms("variable") if f"`{v}`" not in corps]
        self.assertEqual(absentes, [], "variables du verrou que la prose de § 3.4 ne nomme pas")
        if not self._noms("variable", "reserve"):
            self.assertIsNone(
                re.search(r"\bréservée?s?\b", corps),
                "§ 3.4 dit « réservée » alors qu'aucune variable du verrou n'est `reserve`")

    def test_W2_chaque_cli_public_est_nomme_au_3_1_hors_des_reserves(self):
        lignes = self._section("### 3.1 ")
        blocs = _blocs(lignes[1:])
        reserves = [b for b in blocs if b.startswith(OUVERTURE_RESERVES)]
        self.assertEqual(len(reserves), 1, f"§ 3.1 doit porter UN paragraphe « {OUVERTURE_RESERVES} »")
        hors = " ".join(b for b in blocs if not b.startswith(OUVERTURE_RESERVES))
        publics = self._noms("cli", "public")
        absents = [c for c in publics if f"`{c}`" not in hors]
        self.assertEqual(
            absents, [],
            "cli publics du verrou que § 3.1 ne nomme pas hors du paragraphe des reserves")
        # Le BLOC des publics, pas le reste de § 3.1 : `cadre disarm` et
        # `cadre lessons promote` y sont cites ailleurs, une promotion sans prose
        # (ou un public retire du bloc) passait l'assertion ci-dessus.
        bloc = [b for b in blocs if b.startswith(OUVERTURE_PUBLICS)]
        self.assertEqual(len(bloc), 1, f"§ 3.1 doit porter UN paragraphe « {OUVERTURE_PUBLICS} »")
        nommes = set(NOM_CLI.findall(bloc[0]))
        self.assertEqual(
            (sorted(set(publics) - nommes), sorted(nommes - set(publics))), ([], []),
            "le bloc des publics de § 3.1 differe des cli publics du verrou — (publics "
            "au verrou absents du bloc, nommes dans le bloc sans etre publics au verrou)")
        if publics:
            self.assertIsNone(
                re.search(r"pas (?:encore )?publique", lignes[0]),
                f"le titre de § 3.1 nie une CLI publique que le verrou porte : {lignes[0]!r}")

    def test_W3_aucune_surface_reservee_n_est_dite_promise(self):
        s38 = _blocs(self._section("### 3.8 ")[1:])
        s6 = _blocs(self._section("## 6. ")[1:])
        # § 3.10 définit `niveau-hote:enforce` et `niveau-hote:assiste` (surfaces `reserve`) :
        # une promesse écrite là échappait au témoin (clôture du lot couloir B vague 2, F8).
        s310 = _blocs(self._section("### 3.10 ")[1:])
        corps38 = " ".join(s38)
        absentes = [s for s in self._noms("surface") if f"`{s}`" not in corps38]
        self.assertEqual(absentes, [], "surfaces du verrou que § 3.8 ne nomme pas")
        reservees = self._noms("surface", "reserve")
        promises = [b for b in s38 + s6 + s310
                    if PROMESSE.search(b) and any(f"`{s}`" in b for s in reservees)]
        self.assertEqual(
            promises, [],
            "paragraphe de § 3.8 ou § 3.10, ou item de § 6, qui nomme une surface `reserve` et la dit promise")
        if reservees:
            self.assertIn("réserv", corps38, "§ 3.8 ne dit plus reservees ses surfaces `reserve`")

    def test_W5_le_3_6_ne_recopie_aucun_compte_par_format(self):
        corps = " ".join(_blocs(self._section("### 3.6 ")[1:]))
        self.assertEqual(
            COMPTE_PAR_FORMAT.findall(corps), [],
            "§ 3.6 recopie un compte par format : il se derive du depot, il ne se recopie pas")

    def test_W6_le_nom_de_distribution_du_5_egale_pyproject(self):
        if distribution_hors_sujet():
            self.skipTest(SAUT_DISTRIBUTION)
        trouves = [m.group(1) for ligne in self._section("## 5. ")[1:]
                   if (m := LIGNE_DISTRIBUTION.match(ligne))]
        self.assertEqual(
            len(trouves), 1,
            "§ 5 doit porter UNE ligne « | Nom de la distribution | **`nom`** … », "
            f"trouvees : {trouves}")
        attendu = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["name"]
        self.assertEqual(
            trouves[0], attendu,
            f"§ 5 nomme la distribution {trouves[0]!r}, pyproject.toml porte {attendu!r}")

    def test_W9_aucun_identifiant_interne_dans_le_contrat(self):
        trouves = [f"{n}: {m.group(0)}" for n, ligne in enumerate(self.texte.splitlines(), 1)
                   for m in IDENTIFIANT_INTERNE.finditer(ligne)]
        self.assertEqual(
            trouves, [],
            "CONTRAT-v0.md voyage chez l'adoptant : aucun identifiant interne du kit "
            "(T-…, S-…, L-…, E-…, PG-…, SYM-…) ni « wheel » dans sa prose — reecrire "
            "la phrase sans lui")


class MotifW9Tests(unittest.TestCase):
    """Le MOTIF de W9 eprouve seul (T-00001165, critic-fable F6 bis trou 2). Le
    contrat reel ne porte aucun ULID : un mutant qui retire la branche
    `[0-9A-HJKMNP-TV-Z]{26}` restait vert sur lui. Ici il rougit. Classe a part :
    aucun `setUp` ne lit la doc, le motif se juge sans elle."""

    def _vus(self, jeton: str) -> list[str]:
        return [m.group(0) for m in IDENTIFIANT_INTERNE.finditer(f"voir {jeton}, puis la suite.")]

    def test_W9_le_motif_voit_les_trois_graphies(self):
        # Longue, courte, ULID de tache et ULID de symbole : vus, et EXACTEMENT le jeton.
        for jeton in ("T-00000753", "T-753", "T-01HZX5Q8N9ABCDEFGHJKMNPQRS",
                      "SYM-01HZX5Q8N9ABCDEFGHJKMNPQRS"):
            with self.subTest(jeton=jeton):
                self.assertEqual(self._vus(jeton), [jeton])
        # Un ULID de 25 caracteres et un ULID en minuscules ne sont PAS des ids du kit.
        for jeton in ("T-01HZX5Q8N9ABCDEFGHJKMNPQR", "T-01hzx5q8n9abcdefghjkmnpqrs"):
            with self.subTest(jeton=jeton):
                self.assertEqual(self._vus(jeton), [])


class DistributionHorsSujetTests(unittest.TestCase):
    """Le PREDICAT du saut de W6 eprouve seul (S-00004099), sur des manifestes
    FIXTURES, jamais celui de ROOT : il se saute hors du kit sans la distribution,
    et ne se saute JAMAIS dans le kit.
    MUTATIONS : `if EST_LE_KIT: return False` retire → kit sans manifeste rend True
    → rouge ; comparaison du nom retiree → manifeste etranger rend False → rouge."""

    def _verdict(self, est_le_kit: bool, texte: str | None) -> bool:
        with tempfile.TemporaryDirectory(prefix="w6-") as d:
            manifeste = Path(d) / "pyproject.toml"
            if texte is not None:
                manifeste.write_text(texte, encoding="utf-8")
            with mock.patch.multiple(sys.modules[__name__], EST_LE_KIT=est_le_kit,
                                     PYPROJECT=manifeste):
                return distribution_hors_sujet()

    def test_dans_le_kit_le_saut_ne_mord_jamais(self):
        for texte in (None, '[project]\nname = "autre"\n', "[project\n"):
            with self.subTest(texte=texte):
                self.assertFalse(self._verdict(True, texte))

    def test_hors_du_kit_seule_la_distribution_cadre_kit_garde_w6(self):
        cas = {"absent": None, "etranger": '[project]\nname = "mon-projet"\n',
               "illisible": "[project\n", "project scalaire": 'project = "x"\n'}
        for nom, texte in cas.items():
            with self.subTest(cas=nom):
                self.assertTrue(self._verdict(False, texte))
        self.assertFalse(self._verdict(False, '[project]\nname = "cadre-kit"\n'))


if __name__ == "__main__":
    unittest.main()
