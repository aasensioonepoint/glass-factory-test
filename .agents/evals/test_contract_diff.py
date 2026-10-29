#!/usr/bin/env python3
"""CHECKS `contract_diff` ET `check_changelog_contract` — Phase 0bis de T-012.

CE QUE `contract_diff` CONFRONTE. Avant la Phase 1, il confrontait le verrou a
LUI-MEME (unicite, coherence, justification) et aux fichiers du depot
(evenements declares par les hotes, workflows, chemins promis). Depuis la
Phase 1, le MODE INTROSPECTION confronte aussi la CLI reelle et les variables
`CADRE_` lues par le noyau, dans les deux sens.

`check_changelog_contract` refuse une release ou un element `public` a disparu
du verrou sans entree dans la rubrique Contrat du CHANGELOG. En 0.x il faut
cette entree ET au moins une montee de mineure de `version_contrat`
(CONTRAT-v0.md § 2) ; a partir de 1.0, un bump majeur. La montee de mineure
est VERIFIEE depuis T-00000747 (S-00002732) : le commit precedent du verrou
porte sa `version_contrat`, donc la reference existe — la premisse « aucune
reference tant qu'aucun tag n'existe » (S-00002676) etait fausse.

Entrees `contract_diff` et `check_changelog_contract` du `checks.manifest.json`,
phase 0bis. Tournent dans la porte par `pytest`, comme tous les autres.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from surface_kit import EST_LE_KIT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# OU vit le paquet `cadre` : `vendor_paths` charge PAR CHEMIN (patron v3prep,
# T-01M5BXTPQE3JZV3KZA6WD9P5XC), `.agents/vendor/cadre` d'abord, `src/cadre`
# sinon ; `sys.path` n'est jamais touche (`charger_paquet`).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_contract_diff_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)


def _noyau() -> Path:
    """Le dossier du paquet `cadre` que la regle designe, `cadre` charge depuis
    lui (refus nomme s'il est absent ou deja charge d'ailleurs)."""
    _VENDOR.charger_paquet(ROOT, "cadre")
    return _VENDOR.exiger(ROOT, "cadre")


LOCK = ROOT / "contract.lock.json"
DOC = ROOT / "docs" / "contrat" / "CONTRAT-v0.md"
CHANGELOG = ROOT / "CHANGELOG.md"

STATUTS = {"public", "reserve", "deprecie"}
TYPES = {"cli", "evenement", "protocole", "variable", "arborescence", "format",
         "commande", "surface"}
PHASES = {"0", "0bis", "1", "2", "3", "3bis", "4", "4bis", "5", "6", "7"}


def verrou() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


_SEMVER_NOYAU = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.\-+]*)?\s*$")


def version_contrat_noyau(v: str) -> tuple[int, int, int]:
    """`0.2.0-rc.1+build.7` → (0, 2, 0).

    PRE-VERSION ET METADONNEES DE BUILD SONT RETIREES AVANT LA COMPARAISON, et
    c'est ecrit pour ne pas etre relu comme un oubli : CONTRAT-v0.md § 2 ne
    parle que de majeure, mineure et correctif, et `0.2.0-rc.1` porte deja la
    montee de mineure que `0.2.0` publiera. NON tenu : l'ordre entre deux
    pre-versions d'une meme mineure. Hors forme `N.N.N` (suffixe `-…`/`+…`
    tolere) → ValueError plutot que de passer."""
    m = _SEMVER_NOYAU.match(v)
    if not m:
        raise ValueError(f"version_contrat hors SemVer : {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def publics(d: dict) -> dict[str, tuple[str, str]]:
    """Les elements `public` d'un verrou, nom → (type, statut)."""
    return {e["element"]: (e["type"], e["statut"]) for e in d["elements"]
            if e["statut"] == "public"}


def fautes_de_version_0x(avant: dict, apres: dict) -> list[str]:
    """CONTRAT-v0.md § 2, ligne `0.x`, rendue MECANIQUE (T-00000747, S-00002732).

    RUPTURE = un element public d'AVANT dont le (type, statut) a change ou qui
    n'est plus public. AJOUT = un element public d'APRES qui ne l'etait pas
    avant (promotion `reserve` → `public` comprise). Tant que la
    `version_contrat` d'AVANT est en 0.x, l'un comme l'autre exige
    (majeure, mineure) d'APRES > (majeure, mineure) d'AVANT : un correctif
    `0.y.Z` n'ajoute, ne change ni ne retire aucune entree.

    A PARTIR DE 1.0 RIEN N'EST VERIFIE ICI : le contrat y demande un bump
    majeur pour une suppression, jambe a cabler quand une 1.x existera — borne
    ecrite, pas une garantie. Rend la liste des fautes, vide = conforme."""
    fautes: list[str] = []
    pa, pb = publics(avant), publics(apres)
    ruptures = sorted(n for n, ts in pa.items() if pb.get(n) != ts)
    ajouts = sorted(n for n in pb if n not in pa)
    va = version_contrat_noyau(avant["version_contrat"])
    vb = version_contrat_noyau(apres["version_contrat"])
    if va[0] != 0 or not (ruptures or ajouts):
        return fautes
    if vb[:2] <= va[:2]:
        quoi = []
        if ruptures:
            quoi.append(f"rupture d'entrees publiques {ruptures}")
        if ajouts:
            quoi.append(f"ajout d'entrees publiques {ajouts}")
        fautes.append(
            " et ".join(quoi)
            + f" avec version_contrat {avant['version_contrat']!r} → "
            f"{apres['version_contrat']!r} : en 0.x il faut cette entrée ET au "
            "moins une montée de mineure de version_contrat (CONTRAT-v0.md § 2) ; "
            "à partir de 1.0, un bump majeur — un correctif 0.y.Z n'ajoute, ne "
            "change ni ne retire aucune entrée"
        )
    return fautes


#: CONTRAT-v0.md § 2 — la ligne de la table « Règle | Valeur » que transcrit
#: chaque cle de `politique_version` (T-00000775).
LIGNES_POLITIQUE = {
    "premiere_release": "Première release",
    "passage_1_0": "Passage en `1.0`",
    "en_0_x": "En `0.x`",
    "a_partir_de_1_0": "À partir de `1.0`",
}


def transcrire_regle(cellule: str) -> str:
    """Une cellule « Valeur » du § 2 telle que le verrou la porte : sans `**` ni
    backquote, sans diacritiques (NFKD), minuscule initiale."""
    s = cellule.replace("**", "").replace("`", "")
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return s[:1].lower() + s[1:]


class ContractDiffTests(unittest.TestCase):
    def setUp(self):
        if not LOCK.exists():
            self.fail("contract.lock.json absent — livrable de la Phase 0bis")
        self.d = verrou()
        self.elements = self.d["elements"]

    def test_chaque_identifiant_est_unique(self):
        """Un doublon rendrait le verrou ambigu : deux promesses sous un nom."""
        noms = [e["element"] for e in self.elements]
        doublons = sorted({n for n in noms if noms.count(n) > 1})
        self.assertEqual(doublons, [], f"identifiants en double : {doublons}")

    def test_chaque_entree_est_bien_formee(self):
        champs = {"element", "type", "introduit_en", "statut", "note"}
        for e in self.elements:
            manquants = champs - set(e)
            self.assertEqual(manquants, set(), f"{e.get('element')!r} : champs manquants {manquants}")
            self.assertIn(e["type"], TYPES, f"{e['element']!r} : type inconnu {e['type']!r}")
            self.assertIn(e["statut"], STATUTS, f"{e['element']!r} : statut inconnu {e['statut']!r}")
            self.assertIn(e["introduit_en"], PHASES, f"{e['element']!r} : phase inconnue")

    def test_aucune_note_vide(self):
        """LA JUSTIFICATION EST LA CONDITION DE LA PROMOTION. Une entree sans
        motif ecrit est une promesse que personne n'a decidee — c'est exactement
        ce que le principe de parcimonie interdit."""
        muettes = sorted(e["element"] for e in self.elements if len(e.get("note", "").strip()) < 20)
        self.assertEqual(muettes, [], f"elements promus sans justification ecrite : {muettes}")

    def test_un_element_deprecie_nomme_son_remplacant(self):
        """Un `deprecie` sans remplacant est une impasse pour l'adoptant."""
        for e in self.elements:
            if e["statut"] == "deprecie":
                self.assertRegex(
                    e["note"], r"remplac|deprecie le|retire en",
                    f"{e['element']!r} est deprecie mais sa note ne dit ni quand il part ni par quoi il est remplace",
                )

    def test_la_politique_de_version_est_declaree(self):
        p = self.d.get("politique_version", {})
        self.assertEqual(p.get("premiere_release"), "0.1.0")
        for cle in ("passage_1_0", "en_0_x", "a_partir_de_1_0"):
            self.assertTrue(p.get(cle), f"politique de version incomplete : {cle}")

    def test_le_verrou_n_est_pas_vide(self):
        """NON-VACUITE. Un verrou vide passerait toutes les boucles ci-dessus."""
        self.assertGreater(len(self.elements), 20, "verrou trop maigre pour prouver quoi que ce soit")
        self.assertTrue(any(e["statut"] == "public" for e in self.elements))
        self.assertTrue(any(e["statut"] == "reserve" for e in self.elements))

    # Les fichiers de declaration native, par hote. `agentStop` est l'orthographe
    # Copilot de `Stop` : la correspondance est une TABLE, pas un bricolage dans
    # la boucle — la premiere redaction portait un `.replace("stop","stop")` qui
    # etait un no-op, trouve par la revue croisee.
    DECLARATIONS = {
        "claude": ".claude/settings.json",
        "codex": ".codex/hooks.json",
        "gemini": ".agents/hooks.json",
        "kimi": ".kimi-code/hooks.json",
        "copilot": ".github/hooks/agent-guardrails.json",
    }
    ALIAS = {"stop": {"stop", "agentstop"}}

    def _declares_par_hote(self) -> dict[str, set[str]]:
        out = {}
        for hote, rel in self.DECLARATIONS.items():
            p = ROOT / rel
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            out[hote] = {k.lower() for k in (d.get("hooks") or d).keys()}
        return out

    def _est_declare(self, evenement: str, declares: set[str]) -> bool:
        cle = evenement.lower()
        return bool(self.ALIAS.get(cle, {cle}) & declares)

    def test_les_evenements_universels_le_sont_CHEZ_TOUS_LES_HOTES(self):
        """L'UNION NE PROUVE RIEN, et c'est le defaut que la revue a trouve. Un
        test qui demande « au moins un hote » reste vert quand `Stop` disparait
        de Codex, pendant que la doc continue d'affirmer « les six ». La note du
        verrou dit « DECLARE par les six hotes » : c'est CE compte-la qui est
        verifie, hote par hote."""
        declares = self._declares_par_hote()
        self.assertGreaterEqual(len(declares), 5, "trop peu de declarations lues")
        universels = [e["element"].split(":", 1)[1] for e in self.elements
                      if e["element"].startswith("hook:")
                      and "six hotes" in e["note"]]
        self.assertTrue(universels, "aucun evenement declare universel — boucle vide")
        manques = sorted(
            f"{ev} absent de {hote}"
            for ev in universels
            for hote, jeu in declares.items()
            if not self._est_declare(ev, jeu)
        )
        self.assertEqual(manques, [], f"promis universels et absents quelque part : {manques}")

    def test_les_evenements_propres_a_claude_ne_sont_promis_que_la(self):
        """L'AUTRE SENS. Un evenement note « Claude Code SEUL » qui apparaitrait
        ailleurs rendrait la note fausse, et un hote serait classe `assiste` a
        tort."""
        declares = self._declares_par_hote()
        propres = [e["element"].split(":", 1)[1] for e in self.elements
                   if e["element"].startswith("hook:") and "Claude Code SEUL" in e["note"]]
        self.assertTrue(propres)
        for ev in propres:
            self.assertTrue(self._est_declare(ev, declares.get("claude", set())),
                            f"{ev} promis sur Claude et absent de sa declaration")
            ailleurs = sorted(h for h, jeu in declares.items()
                              if h != "claude" and self._est_declare(ev, jeu))
            self.assertEqual(ailleurs, [],
                             f"{ev} est note « Claude Code SEUL » mais declare aussi par {ailleurs}")

    def test_les_workflows_correspondent_EXACTEMENT_aux_definitions(self):
        """LES DEUX SENS. La premiere redaction ne verifiait que « promis donc
        present » : un treizieme fichier sous `.claude/commands/` ne disait rien,
        et c'est exactement l'ecart qui a fait ecrire « treize workflows » dans
        une doc qui en listait douze."""
        presents = {p.stem for p in (ROOT / ".claude" / "commands").glob("*.md")}
        promis = {e["element"].split(":", 1)[1] for e in self.elements
                  if e["element"].startswith("workflow:")}
        self.assertTrue(promis and presents)
        self.assertEqual(sorted(promis - presents), [],
                         f"workflows promis sans definition : {sorted(promis - presents)}")
        # T-01M54MWW5GH (S-01M54ZQ6WC) : hors du kit, une commande AJOUTEE par
        # l'adoptant n'est pas un workflow du kit ; le second sens vaut dans le kit seul.
        if not EST_LE_KIT:
            return
        self.assertEqual(sorted(presents - promis), [],
                         f"commandes definies et NON promises : {sorted(presents - promis)}. "
                         "Soit elles entrent au verrou, soit elles ne sont pas des workflows.")

    def test_les_chemins_promis_existent(self):
        """Un chemin d'arborescence promis doit exister, sauf s'il est `reserve`
        — auquel cas c'est justement qu'il n'existe pas encore."""
        manquants = sorted(
            e["element"] for e in self.elements
            if e["type"] == "arborescence" and e["statut"] == "public"
            and not (ROOT / e["element"]).exists()
            and "<" not in e["element"]
        )
        # DEUX ABSENCES QUI SONT LA CONCEPTION, PAS UN MANQUE — nommees, jamais
        # tolerees en bloc.
        #  * `.agents/protected-paths.local` est `own:` de la branche template et
        #    n'existe JAMAIS sur main.
        #  * `.agents/state/gates/GITLEAKS_FALLBACK.off` est un EXTINCTEUR : sa
        #    presence DESARME le repli, donc son ABSENCE est le regime de
        #    reference. Exiger qu'il existe reviendrait a exiger qu'il soit tire.
        ABSENCES_PAR_CONCEPTION = {
            ".agents/protected-paths.local",
            ".agents/state/gates/GITLEAKS_FALLBACK.off",
        }
        # TROIS DE PLUS HORS DU KIT SEULEMENT (marqueur `.agents/IS_THE_KIT`
        # absent, lui-meme `strip:`). `strip: .agents/state/` retire les trois
        # magasins ; `project_init.py` recree le board (INIT), LEDGER et SPECS
        # naissent au premier `ledger.py add` / `specs.py add` (`lazy`,
        # project_init.py en-tete). Le board manque donc AUSSI avant
        # project_init : sur la branche template, ou il ne tourne jamais, et
        # chez l'adoptant qui pousse avant lui. L'exiger rougissait leur CI
        # (porte de la branche template ; decisions pilote S-00004094,
        # S-00004099). AUCUN banc de la porte ne rougit plus avant
        # provisionnement (mesure 2026-10-04) : `check-stale-justification.sh`
        # rend [E0] sur un arbre sans board (temoin B1a, sur fixture), mais la
        # porte ne le joue que par le bras (j) de sa suite, qui provisionne
        # d'abord (`--ensure-stores`) ; il n'est un pas ni de verify.sh ni de
        # ci.yml. Le remede ne vit que dans `project_init.py`. Dans le kit,
        # les trois restent exiges : ils y sont suivis, et un board absent s'y
        # restaure par git — d'ou aucun renvoi a project_init, qui en creerait
        # un vide.
        # adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ; son absence EST le signal « projet adoptant ».
        est_le_kit = (ROOT / ".agents" / "IS_THE_KIT").is_file()
        if not est_le_kit:
            ABSENCES_PAR_CONCEPTION = ABSENCES_PAR_CONCEPTION | {
                ".agents/state/board/TASKS.json",
                ".agents/state/memory/LEDGER.json",
                ".agents/state/specs/SPECS.json",
            }
        manquants = [m for m in manquants if m not in ABSENCES_PAR_CONCEPTION]
        # DEUX FORMES PAR MAGASIN (contrat 0.2.0, T-01M4KKMY43ZKCW1YD2Y8JX9MKH), DANS LE KIT SEULEMENT (ailleurs les
        # trois sont déjà des absences par conception) : un élément-magasin est présent par son monolithe OU par sa
        # forme enregistrement ; ni l'un ni l'autre reste ROUGE. Un dossier VIDE n'est pas une forme présente (passe de
        # correction F5, N10) : le journal se compte s'il est un fichier, un dossier s'il porte au moins un `*.json`.
        if est_le_kit:
            formes = {".agents/state/board/TASKS.json": ".agents/state/board/tasks",
                      ".agents/state/memory/LEDGER.json": ".agents/state/memory/entries",
                      ".agents/state/specs/SPECS.json": ".agents/state/specs/SPECS.jsonl"}
            manquants = [m for m in manquants if not (m in formes and (
                (ROOT / formes[m]).is_file() or any((ROOT / formes[m]).glob("*.json"))))]
        self.assertEqual(manquants, [],
                         f"chemins promis publics et absents : {manquants}")

    # ------------------------------------------------------------------
    # MODE INTROSPECTION — arme depuis que `src/cadre/` existe (Phase 1).
    #
    # Un test plante en Phase 0bis ECHOUAIT tant que le paquet n'existait pas et
    # que le check restait declaratif ; il a rougi au premier commit de la
    # Phase 1, exactement comme prevu, et ces deux bancs le remplacent. Le
    # contrat cesse donc d'etre une liste de bonnes intentions au moment PRECIS
    # ou du code peut la dementir.
    # ------------------------------------------------------------------

    @staticmethod
    def _cli_reelle() -> tuple[set[str], set[str]]:
        """(sous-commandes exposees, noms reserves declares) lus dans le module."""
        import importlib.util as u

        chemin = _noyau() / "cli.py"
        spec = u.spec_from_file_location("cadre_cli_introspection", chemin)
        module = u.module_from_spec(spec)
        # ENREGISTRER AVANT D'EXECUTER, et le filet du depot a raison de
        # l'exiger : un module execute hors de `sys.modules` casse les
        # dataclasses, le pickling et les imports relatifs, de facon differee et
        # difficile a rattacher a sa cause. La premiere redaction l'omettait.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        reservees = set(module.RESERVEES)
        # DEUX tables, et l'union est ce que la CLI EXPOSE : les implementees et
        # les reservees. Un nom qui quitte la seconde pour la premiere reste
        # expose — c'est son STATUT au verrou qui doit suivre, pas sa presence.
        return set(module.IMPLEMENTEES) | reservees, reservees

    def test_chaque_commande_du_verrou_existe_dans_la_CLI(self):
        """LE SENS QUI COMPTE : le verrou ne promet pas un nom que la CLI ignore.

        Les entrees `cli` s'ecrivent `cadre <sous-commande>` ou `cadre` tout
        court ; on compare la SOUS-COMMANDE, jamais la phrase entiere, et un
        drapeau comme `--upgrade` appartient a sa commande."""
        exposees, _ = self._cli_reelle()
        promises = set()
        for e in self.elements:
            if e["type"] != "cli":
                continue
            mots = e["element"].split()
            if len(mots) >= 2 and not mots[1].startswith("-"):
                promises.add(mots[1])
        self.assertTrue(promises, "aucune commande promise — la boucle serait vide")
        absentes = sorted(promises - exposees)
        self.assertEqual(
            absentes, [],
            "commandes promises au contrat que `cadre.cli` n'expose PAS : "
            f"{absentes}. Un nom promis doit au minimum etre RESERVE dans la CLI, "
            "pour qu'un adoptant recoive « ce nom est pris, il arrive » et non "
            "« commande inconnue ».",
        )

    def test_un_nom_reserve_de_la_CLI_est_promis_au_verrou(self):
        """L'AUTRE SENS. Un nom reserve dans le code et absent du verrou est une
        promesse que personne n'a decidee — c'est la parcimonie a l'envers."""
        _, reservees = self._cli_reelle()
        promises = {m.split()[1] for e in self.elements if e["type"] == "cli"
                    for m in [e["element"]] if len(m.split()) >= 2
                    and not m.split()[1].startswith("-")}
        orphelines = sorted(reservees - promises)
        self.assertEqual(
            orphelines, [],
            f"noms reserves dans `cadre.cli` et absents du verrou : {orphelines}",
        )

    def _promises_cli(self) -> set[str]:
        return {m.split()[1] for e in self.elements if e["type"] == "cli"
                for m in [e["element"]] if len(m.split()) >= 2
                and not m.split()[1].startswith("-")}

    def test_une_commande_IMPLEMENTEE_est_promise_au_verrou(self):
        """LE TROISIEME SENS, ET IL MANQUAIT. Deux etaient couverts —
        `promis -> expose` et `reserve -> promis` — mais rien ne verifiait
        `IMPLEMENTEE -> promis`. Mesure du 2026-09-12 : `cadre paths` etait une
        commande REELLE, livree, documentee « sortie machine », citee comme
        critere de sortie de la Phase 1, et absente du verrou comme de
        CONTRAT-v0.md (zero occurrence dans les deux). C'est la meme cecite que
        T-00000568 cote variables : le filet comparait une PROJECTION du reel en
        croyant comparer le reel. La parcimonie autorise a ne pas promouvoir ;
        elle n'autorise pas a livrer une surface que le verrou ignore."""
        import importlib.util as u

        chemin = _noyau() / "cli.py"
        spec = u.spec_from_file_location("cadre_cli_impl", chemin)
        module = u.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        implementees = set(module.IMPLEMENTEES)
        self.assertTrue(implementees, "aucune commande implementee — boucle vide")
        orphelines = sorted(implementees - self._promises_cli())
        self.assertEqual(
            orphelines, [],
            f"commandes IMPLEMENTEES et absentes du verrou : {orphelines}. Une "
            "surface livree que le contrat ignore n'a ete decidee par personne.",
        )

    def test_une_commande_implementee_ne_reste_pas_reserve(self):
        """Le pendant, cote statut, de la promotion de `cadre config explain` :
        implementee et `reserve` fait mentir le verrou dans l'autre sens."""
        module = sys.modules.get("cadre_cli_impl")
        if module is None:
            self.test_une_commande_IMPLEMENTEE_est_promise_au_verrou()
            module = sys.modules["cadre_cli_impl"]
        statut: dict[str, set[str]] = {}
        for e in self.elements:
            mots = e["element"].split()
            if e["type"] == "cli" and len(mots) >= 2 and not mots[1].startswith("-"):
                statut.setdefault(mots[1], set()).add(e["statut"])
        mal = sorted(n for n in module.IMPLEMENTEES if "reserve" in statut.get(n, set()))
        self.assertEqual(
            mal, [],
            f"commandes implementees dont une entree du verrou reste `reserve` : {mal}",
        )

    # ------------------------------------------------------------------
    # LES VARIABLES — PAR L'ARBRE SYNTAXIQUE, PLUS PAR LE TEXTE.
    #
    # C'ETAIT LA TROISIEME OCCURRENCE DU MEME PIEGE dans ce depot : un check qui
    # cherche un motif dans le TEXTE d'un fichier attrape la docstring qui
    # explique la regle qu'il applique. D'abord sur `rev-parse`, puis sur
    # `shell=True`, et ici sur les noms de variables — `paths.py` les NOMME en
    # prose lignes 8, 9 et 85, donc `v not in source` restait vert sur un noyau
    # ou la variable n'etait plus lue du tout (mesure du 2026-09-12 : les deux
    # constantes remplacees par un nom mort, le check toujours vert).
    #
    # ET IL NE COMPARAIT QU'UN SENS. `promis -> lu` etait teste, `lu -> promis`
    # ne l'etait pas : `CADRE_PROJECT_ROOT` etait donc lue par
    # `paths.project_root()`, utilisee par les bancs pour deplacer la racine, et
    # ABSENTE DU VERROU. Un adoptant qui la decouvrait n'avait aucune promesse ;
    # un mainteneur qui la retirait ne cassait rien de declare. C'est le defaut
    # de fond de T-00000568 — corriger les trois lignes du verrou sans fermer ce
    # trou aurait laisse passer la variable suivante de la meme facon.
    # ------------------------------------------------------------------

    @staticmethod
    def _variables_lues_par_ast() -> set[str]:
        """Les variables d'environnement REELLEMENT LUES par le noyau.

        QUATRE formes, et la quatrieme a failli manquer — ce qui aurait refait le
        defaut a l'identique, un cran plus loin. La premiere redaction de ce
        detecteur ne voyait pas `_from_env("XDG_CONFIG_HOME")`, forme que
        `paths.py` emploie DEUX fois : un detecteur aveugle a une forme du noyau
        est le meme mensonge qu'une recherche textuelle, avec l'air serieux en
        plus.

          1. `os.environ.get("X")` / `os.getenv("X")`   — appel par attribut
          2. `os.environ["X"]`                          — indexation
          3. `_ENV_X = "CADRE_X"`                       — constante de module,
             passee ensuite a un lecteur ; c'est la forme des trois `CADRE_`
          4. `_from_env("XDG_X")`                       — appel a un AUXILIAIRE
             de lecture local, repere par un nom contenant `env`

        La forme 3 est BORNEE aux noms commencant par `_ENV` : capturer toute
        constante de chaine ferait entrer `_FICHIER = "cadre.json"` et rendrait
        le detecteur bavard plutot que juste.
        """
        lues: set[str] = set()
        for p in sorted(_VENDOR.exiger(ROOT, "cadre").rglob("*.py")):
            arbre = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(arbre):
                if isinstance(n, ast.Call) and n.args \
                        and isinstance(n.args[0], ast.Constant) \
                        and isinstance(n.args[0].value, str):
                    cible = n.func
                    if isinstance(cible, ast.Attribute) and cible.attr in ("get", "getenv"):
                        lues.add(n.args[0].value)
                    elif isinstance(cible, ast.Name) and "env" in cible.id.lower():
                        lues.add(n.args[0].value)
                elif (isinstance(n, ast.Subscript)
                        and isinstance(n.value, (ast.Attribute, ast.Name))
                        and isinstance(n.slice, ast.Constant)
                        and isinstance(n.slice.value, str)):
                    lues.add(n.slice.value)
                elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                        and isinstance(n.value.value, str) \
                        and any(isinstance(c, ast.Name) and c.id.startswith("_ENV")
                                for c in n.targets):
                    lues.add(n.value.value)
        return lues

    def test_le_detecteur_voit_les_QUATRE_formes_du_noyau(self):
        """CONTROLE DE NON-VACUITE DU DETECTEUR LUI-MEME, et il n'est pas
        decoratif : la premiere redaction ratait `_from_env("XDG_...")`, donc
        elle aurait declare « rien d'autre n'est lu » sur un noyau qui lit deux
        variables de plus. Un detecteur qu'on ne mesure pas remplace un faux
        positif par un faux negatif, ce qui est pire."""
        lues = self._variables_lues_par_ast()
        for attendue in ("CADRE_CONFIG_HOME", "CADRE_STATE_DIR", "CADRE_PROJECT_ROOT",
                         "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
            self.assertIn(attendue, lues,
                          f"{attendue} est lue par le paquet `cadre` et le detecteur ne la voit pas")

    def test_chaque_variable_promise_est_lue_par_le_noyau(self):
        """Une variable d'environnement promise que rien ne lit est une surface
        figee pour rien.

        LE PERIMETRE EST `CADRE_`, ET C'EST UNE POLITIQUE ECRITE, PAS UNE
        LIMITE DU DETECTEUR. Celui-ci voit tout ce que le noyau lit, y compris
        `XDG_CONFIG_HOME` et `XDG_STATE_HOME` — le kit les HONORE sans les
        definir, donc les promettre reviendrait a s'attribuer une convention du
        systeme. Que le contrat doive quand meme dire qu'il les honore est une
        question ouverte, tracee au board plutot que tranchee ici en silence.
        """
        lues = self._variables_lues_par_ast()
        promises = [e["element"] for e in self.elements
                    if e["type"] == "variable" and e["element"].startswith("CADRE_")]
        self.assertTrue(promises, "aucune variable CADRE_ promise — boucle vide")
        muettes = sorted(v for v in promises if v not in lues)
        self.assertEqual(
            muettes, [],
            f"variables `CADRE_` promises et LUES par aucun module du noyau : {muettes}",
        )

    def test_chaque_variable_LUE_est_promise_au_verrou(self):
        """L'AUTRE SENS, celui qui manquait. Une variable que le code honore et
        que le contrat ignore est une promesse implicite : elle sera decouverte,
        utilisee, puis cassee sans qu'aucun CHANGELOG ne le dise."""
        promises = {e["element"] for e in self.elements if e["type"] == "variable"}
        orphelines = sorted(v for v in self._variables_lues_par_ast()
                            if v.startswith("CADRE_") and v not in promises)
        self.assertEqual(
            orphelines, [],
            f"variables `CADRE_` LUES par le noyau et absentes du verrou : "
            f"{orphelines}. Le code les honore, le contrat ne les nomme pas.",
        )

    def test_une_variable_LUE_ne_reste_pas_reserve(self):
        """La regle que le verrou s'ecrit a lui-meme pour `cadre config explain`
        — un nom qui fait quelque chose et reste `reserve` fait mentir le verrou
        dans l'autre sens — appliquee aux VARIABLES, ou elle ne l'avait pas ete
        pour celles livrees dans le meme commit (66d15fd)."""
        statut = {e["element"]: e["statut"] for e in self.elements
                  if e["type"] == "variable"}
        lues = {v for v in self._variables_lues_par_ast() if v.startswith("CADRE_")}
        self.assertTrue(lues, "aucune variable CADRE_ lue — boucle vide")
        mal = sorted(v for v in lues if statut.get(v) == "reserve")
        self.assertEqual(
            mal, [],
            f"variables LUES par le noyau et restees `reserve` au verrou : {mal}",
        )

    def test_le_detecteur_de_lecture_NE_retombe_PAS_sur_le_texte(self):
        """CONTROLE NEGATIF, et sans lui la regression revient sans bruit : une
        docstring qui NOMME la variable ne doit JAMAIS suffire a la declarer lue.
        C'est ce temoin qui manquait aux deux occurrences precedentes du piege."""
        arbre = ast.parse('"""Doc citant $CADRE_FANTOME et CADRE_FANTOME."""\nx = 1\n')
        vus: set[str] = set()
        for n in ast.walk(arbre):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.args and isinstance(n.args[0], ast.Constant)):
                vus.add(n.args[0].value)
            elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, str):
                vus.add(n.value.value)
        self.assertNotIn(
            "CADRE_FANTOME", vus,
            "le detecteur est retombe sur la recherche textuelle — une prose qui "
            "nomme la variable la ferait passer pour lue",
        )


class CheminsPromisChezLAdoptantTests(unittest.TestCase):
    """TEMOINS de `test_les_chemins_promis_existent` hors du kit (S-00004092).

    Chacun rejoue le VRAI banc contre un arbre jetable (ROOT remplace, le
    verrou reste celui du depot) peuple de chaque chemin public du verrou sauf
    ceux qu'il retire. Paires separantes : l'absence de LEDGER/SPECS, et celle
    du board, sont vertes chez l'adoptant et rouges dans le kit.
    MUTANTS : retirer la condition sur `IS_THE_KIT` rougit les deux temoins du
    kit ; retirer le board de la tolerance rougit le temoin sans board ;
    retirer la tolerance rougit les deux temoins verts de l'adoptant."""

    BOARD = ".agents/state/board/TASKS.json"
    LEDGER = ".agents/state/memory/LEDGER.json"
    SPECS = ".agents/state/specs/SPECS.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ccd.")
        self.addCleanup(self._tmp.cleanup)

    def _arbre(self, *, kit: bool, absents: set[str]) -> Path:
        racine = Path(self._tmp.name)
        for e in verrou()["elements"]:
            rel = e["element"]
            if (e["type"] != "arborescence" or e["statut"] != "public"
                    or "<" in rel or rel in absents):
                continue
            if rel.endswith("/"):
                (racine / rel).mkdir(parents=True, exist_ok=True)
            else:
                (racine / rel).parent.mkdir(parents=True, exist_ok=True)
                (racine / rel).touch()
        if kit:
            (racine / ".agents" / "IS_THE_KIT").touch()
        return racine

    @staticmethod
    def _verdict(racine: Path) -> str | None:
        """`None` = vert ; sinon le message de l'AssertionError du vrai banc."""
        cas = ContractDiffTests("test_les_chemins_promis_existent")
        with mock.patch.object(sys.modules[__name__], "ROOT", racine):
            cas.setUp()
            try:
                cas.test_les_chemins_promis_existent()
            except AssertionError as exc:
                return str(exc)
        return None

    def test_controle_arbre_complet_dans_le_kit_est_vert(self):
        """Sans lui, les temoins rouges pourraient l'etre pour un chemin oublie
        par `_arbre`, pas pour celui qu'ils retirent."""
        self.assertIsNone(self._verdict(self._arbre(kit=True, absents=set())))

    def test_adoptant_board_present_sans_ledger_ni_specs_est_vert(self):
        verdict = self._verdict(
            self._arbre(kit=False, absents={self.LEDGER, self.SPECS}))
        self.assertIsNone(verdict, f"CI de l'adoptant rouge le premier jour : {verdict}")

    def test_adoptant_sans_board_est_vert(self):
        """La branche template elle-meme (project_init n'y tourne jamais) et un
        adoptant qui pousse avant project_init : aucun des trois magasins."""
        verdict = self._verdict(
            self._arbre(kit=False, absents={self.BOARD, self.LEDGER, self.SPECS}))
        self.assertIsNone(verdict, f"CI de la branche template rouge : {verdict}")

    def test_dans_le_kit_ledger_et_specs_absents_restent_rouges(self):
        verdict = self._verdict(
            self._arbre(kit=True, absents={self.LEDGER, self.SPECS}))
        self.assertIsNotNone(verdict, "LEDGER/SPECS absents DANS le kit et porte verte")
        self.assertIn(
            f"chemins promis publics et absents : {[self.LEDGER, self.SPECS]}", verdict)

    def test_dans_le_kit_board_absent_reste_rouge_sans_renvoyer_a_project_init(self):
        """`endswith` : rien ne suit la liste. Le board du kit est SUIVI ; il se
        restaure par git, et `project_init.py` en creerait un VIDE."""
        verdict = self._verdict(self._arbre(kit=True, absents={self.BOARD}))
        self.assertIsNotNone(verdict, "board absent DANS le kit et porte verte")
        self.assertTrue(
            verdict.endswith(f"chemins promis publics et absents : {[self.BOARD]}"),
            verdict)

    def test_dans_le_kit_un_dossier_d_enregistrements_vide_n_est_pas_une_forme(self):
        """Passe de correction F5 (N10). MUTANT : la présence ramenée à `.exists()` — `board/tasks/` vide valait
        « forme présente » et la porte restait verte sans aucun board. POLARITÉ : un `T-*.json` ⇒ vert."""
        racine = self._arbre(kit=True, absents={self.BOARD})
        dossier = racine / ".agents" / "state" / "board" / "tasks"
        dossier.mkdir(parents=True)
        verdict = self._verdict(racine)
        self.assertIsNotNone(verdict, "board/tasks/ VIDE dans le kit et porte verte")
        self.assertTrue(verdict.endswith(f"chemins promis publics et absents : {[self.BOARD]}"), verdict)
        (dossier / "T-1.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(self._verdict(racine))


class ChangelogContratTests(unittest.TestCase):
    """`check_changelog_contract` — en 0.x, une suppression exige une entree au
    CHANGELOG ET une montee de mineure ; un ajout, la montee de mineure.

    LA REFERENCE EST LE COMMIT PRECEDENT DU VERROU, ET CA BORNE LE CHECK :
    la montee de mineure doit atterrir dans le MEME commit que la rupture ou
    l'ajout — deux commits (l'entree d'abord, la version ensuite) rougissent
    entre les deux, et c'est voulu. Le candidat est l'ARBRE DE TRAVAIL, la
    reference l'avant-dernier commit qui a touche le verrou : une rupture non
    commitee empilee sur un bump deja commite est couverte par ce bump jusqu'au
    commit suivant. Ce que le check ne voit PAS : une rupture plus ancienne que
    ce commit precedent — `.agents/kit.lock` promu `public` a 3a9627b9 sans
    montee de mineure est deja hors fenetre. Ce residu n'est porte ni par ce
    banc ni par T-00000775, qui n'a aligne que `politique_version` : son
    rattrapage — une montee de mineure de `version_contrat` sur tous ses sites
    couples — attend une tache distincte, et le reliquat reste consigne au
    registre sous S-00002736 (4).
    """

    def _verrou_precedent(self) -> dict | None:
        """Le verrou tel qu'au commit precedent, ou None a la premiere pose."""
        r = subprocess.run(["git", "log", "--format=%H", "-2", "--", "contract.lock.json"],
                           cwd=ROOT, capture_output=True, text=True, check=False)
        shas = [s for s in r.stdout.split() if s]
        if len(shas) < 2:
            return None
        precedent = subprocess.run(["git", "show", f"{shas[1]}:contract.lock.json"],
                                   cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return json.loads(precedent)

    def test_toute_suppression_publique_figure_au_changelog(self):
        """Compare le verrou a sa version PRECEDENTE dans git. Un element
        `public` disparu doit etre nomme dans la rubrique Contrat du CHANGELOG.

        Sans version precedente — premiere pose du verrou — il n'y a rien a
        comparer, et le test le DIT plutot que de passer en silence."""
        precedent = self._verrou_precedent()
        if precedent is None:
            self.skipTest("verrou sans version precedente dans git — rien a diffuser encore")
        disparus = sorted(set(publics(precedent)) - set(publics(verrou())))
        if not disparus:
            return
        self.assertTrue(CHANGELOG.exists(),
                        f"elements publics supprimes ({disparus}) et aucun CHANGELOG.md")
        texte = CHANGELOG.read_text(encoding="utf-8")
        m = re.search(r"^#{1,3}\s*Contrat\s*$(.*?)(?=^#{1,3}\s|\Z)", texte,
                      flags=re.M | re.S | re.I)
        rubrique = m.group(1) if m else ""
        absents = [d for d in disparus if d not in rubrique]
        self.assertEqual(
            absents, [],
            "elements PUBLICS retires du verrou et absents de la rubrique Contrat "
            f"du CHANGELOG : {absents}. En 0.x il faut cette entrée ET au moins "
            "une montée de mineure de version_contrat (CONTRAT-v0.md § 2) ; à "
            "partir de 1.0, un bump majeur.",
        )

    def test_en_0x_une_rupture_ou_un_ajout_monte_la_mineure(self):
        """T-00000747 (S-00002732) — la promesse de CONTRAT-v0.md § 2 ligne 0.x,
        tenue par le code et plus seulement par la prose : voir
        `fautes_de_version_0x` pour la regle, et la docstring de classe pour
        la borne (reference = commit precedent du verrou)."""
        precedent = self._verrou_precedent()
        if precedent is None:
            self.skipTest("verrou sans version precedente dans git — rien a comparer encore")
        self.assertEqual(fautes_de_version_0x(precedent, verrou()), [])

    def test_fautes_de_version_0x_temoins(self):
        """TEMOINS SYNTHETIQUES, pour que le check puisse ETRE VU rougir :
        l'arbre reel n'a ni rupture ni ajout depuis le commit precedent, donc
        `test_en_0x_…` y est vert par vacuite. Chaque cas est une paire de
        verrous en memoire."""
        def lock(version: str, *elements: tuple[str, str, str]) -> dict:
            return {"version_contrat": version,
                    "elements": [{"element": n, "type": t, "statut": s}
                                 for n, t, s in elements]}
        base = lock("0.1.0", ("cadre", "cli", "public"), ("x", "cli", "public"),
                    ("y", "cli", "reserve"))
        cas = {
            "rupture (x disparu) SANS montee de mineure → faute":
                fautes_de_version_0x(base, lock("0.1.0", ("cadre", "cli", "public"))) != [],
            "rupture (x disparu) en correctif 0.1.1 → faute":
                fautes_de_version_0x(base, lock("0.1.1", ("cadre", "cli", "public"))) != [],
            "rupture (x disparu) AVEC montee de mineure 0.2.0 → conforme":
                fautes_de_version_0x(base, lock("0.2.0", ("cadre", "cli", "public"))) == [],
            "changement (x public → deprecie) sans mineure → faute":
                fautes_de_version_0x(base, lock("0.1.0", ("cadre", "cli", "public"),
                                                ("x", "cli", "deprecie"))) != [],
            "changement de type (x cli → commande) sans mineure → faute":
                fautes_de_version_0x(base, lock("0.1.0", ("cadre", "cli", "public"),
                                                ("x", "commande", "public"))) != [],
            "ajout (y promu public) en correctif 0.1.1 → faute":
                fautes_de_version_0x(base, lock("0.1.1", ("cadre", "cli", "public"),
                                                ("x", "cli", "public"),
                                                ("y", "cli", "public"))) != [],
            "ajout (y promu public) avec mineure 0.2.0 → conforme":
                fautes_de_version_0x(base, lock("0.2.0", ("cadre", "cli", "public"),
                                                ("x", "cli", "public"),
                                                ("y", "cli", "public"))) == [],
            "aucun changement en correctif 0.1.1 → conforme":
                fautes_de_version_0x(base, lock("0.1.1", ("cadre", "cli", "public"),
                                                ("x", "cli", "public"))) == [],
            "pre-version 0.2.0-rc.1+build.7 compte comme 0.2.0 → conforme":
                fautes_de_version_0x(base, lock("0.2.0-rc.1+build.7",
                                                ("cadre", "cli", "public"))) == [],
            "passage 1.0.0 couvre la rupture → conforme":
                fautes_de_version_0x(base, lock("1.0.0", ("cadre", "cli", "public"))) == [],
            "a partir de 1.0 rien n'est verifie ici (borne ecrite) → conforme":
                fautes_de_version_0x(lock("1.0.0", ("x", "cli", "public")),
                                     lock("1.0.0")) == [],
        }
        self.assertEqual([k for k, ok in cas.items() if not ok], [])
        with self.assertRaises(ValueError):
            version_contrat_noyau("v0.2")
        faute = fautes_de_version_0x(base, lock("0.1.0", ("cadre", "cli", "public")))[0]
        self.assertIn("CONTRAT-v0.md § 2", faute)
        self.assertIn("['x']", faute)


class ContratDocTests(unittest.TestCase):
    """La doc et le verrou ne divergent pas — meme discipline que la
    classification : une promesse ecrite nulle part n'a ete decidee par personne."""

    def setUp(self):
        if not DOC.exists():
            self.fail("docs/contrat/CONTRAT-v0.md absent — livrable de la Phase 0bis")
        self.texte = DOC.read_text(encoding="utf-8")

    def test_chaque_element_public_est_nomme_dans_la_doc(self):
        """ANCRE SUR LA LIGNE DE TABLE, PAS SUR UNE SOUS-CHAINE NUE.

        `e["element"] not in self.texte` certifiait un element que la doc ne
        nomme nulle part, des lors qu'un AUTRE l'a pour prefixe : `cadre init`
        est un sous-mot de `cadre init --upgrade`, et `cadre` de tout. Sans
        effet mesurable aujourd'hui — le test ne porte que sur les `public` —
        mais il mord au premier element public a nom prefixe, et il aurait mordu
        tout de suite si `cadre paths` avait ete promu avant `cadre`.

        L'ancrage sur la ligne `| \\`element\\` | type | statut |` verifie du meme
        geste que le STATUT ecrit dans la doc est celui du verrou, ce que la
        sous-chaine ne regardait pas du tout.
        """
        absents = []
        for e in verrou()["elements"]:
            if e["statut"] != "public":
                continue
            motif = (rf"^\|\s*`{re.escape(e['element'])}`\s*\|\s*"
                     rf"{re.escape(e['type'])}\s*\|\s*{re.escape(e['statut'])}\s*\|")
            if not re.search(motif, self.texte, flags=re.M):
                absents.append(e["element"])
        self.assertEqual(
            absents, [],
            f"elements publics absents de la table de CONTRAT-v0.md, ou dont le "
            f"type/statut y differe du verrou : {absents}",
        )

    def test_la_doc_nomme_le_principe_de_parcimonie(self):
        self.assertIn("parcimonie", self.texte.lower(),
                      "le principe qui autorise a NE PAS promouvoir doit etre ecrit")

    def test_la_politique_de_version_transcrit_le_contrat(self):
        """`politique_version` DU VERROU EST LA TABLE DU § 2, CLE A CLE (T-00000775).

        `test_la_politique_de_version_est_declaree` ne tient que la presence :
        `en_0_x` a pu dire « une suppression exige une entree CHANGELOG
        rubrique Contrat » pendant que le § 2 exigeait aussi la montee de
        mineure et couvrait le changement, sans que rien rougisse. Chaque cle
        est la transcription (`transcrire_regle`) de SA ligne
        (`LIGNES_POLITIQUE`) ; la table et le verrou ont les MEMES lignes, donc
        une ligne ajoutee, doublee, retiree ou renommee d'un seul cote rougit aussi.
        CE QU'IL NE TIENT PAS : la prose du § 2 hors de la table, et les autres
        sites qui paraphrasent la regle (`$comment` du verrou, CHANGELOG)."""
        m = re.search(r"^## 2\. Politique de version$(.*?)^## ", self.texte,
                      flags=re.M | re.S)
        self.assertIsNotNone(m, "CONTRAT-v0.md : § 2 « Politique de version » introuvable")
        rangs = [ligne.strip() for ligne in m.group(1).splitlines()
                 if ligne.strip().startswith("|")]
        lignes = []
        for rang in rangs[2:]:  # en-tete « Règle | Valeur » et separateur `|---|---|`
            cellules = [c.strip() for c in rang.strip("|").split("|")]
            self.assertEqual(len(cellules), 2, f"ligne malformee dans la table du § 2 : {rang!r}")
            lignes.append((cellules[0], cellules[1]))
        table = dict(lignes)
        # La LISTE, pas les cles du dict : un dict ecrase un doublon, et une
        # seconde ligne « En `0.x` » portant l'ancienne regle passerait.
        self.assertEqual(sorted(r for r, _ in lignes), sorted(LIGNES_POLITIQUE.values()),
                         "lignes de la table du § 2 ≠ lignes que transcrit politique_version")
        attendu = {cle: transcrire_regle(table[regle])
                   for cle, regle in LIGNES_POLITIQUE.items()}
        self.assertEqual(
            verrou().get("politique_version"), attendu,
            "politique_version du verrou ≠ transcription de la table du § 2 de "
            "CONTRAT-v0.md (sans `**` ni backquote, sans diacritiques, "
            "minuscule initiale)",
        )

    def test_granularite_0x_gravee_contrat(self):
        """T-00000747 — LA GRANULARITE 0.x DU LOCKSTEP, MOITIE CONTRAT : ELLE VOYAGE.

        Tant que `version_contrat` est en 0.x, un ecart de MINEURE est refuse
        comme un ecart majeur et seul l'ecart de correctif avertit ; a partir de
        1.0, majeur refuse, mineur et correctif avertissent. Et le corollaire
        qui rend cette regle protectrice : en 0.x, toute suppression ou tout
        changement d'entree exige AU MOINS une montee de mineure de
        `version_contrat` — sans lui, « un ecart de correctif avertit » laisserait
        passer une rupture en silence.

        DES PROPOSITIONS ENTIERES, JAMAIS UN PRONOM. La premiere redaction
        epinglait « un ecart de mineure l'est aussi » seul : le pronom reprend
        le verbe de la proposition precedente, donc remplacer « est refuse » par
        « avertit » inversait la regle sans rougir (mesure par le binome de
        cloture). C2 epingle donc le refus de la majeure ET celui de la mineure
        d'un seul tenant, pour que « l'est » garde son antecedent ; C3 epingle
        l'avertissement avec son sujet et sa borne ; C4 et C5 epinglent la
        promesse de montee de mineure a la Politique de version (ligne `0.x` de
        la table, entiere, pour qu'une permutation des lignes rougisse) et aux
        limites du document. Blancs normalises : un simple reflow ne rougit pas.

        Aucun saut : le contrat est livre a l'adoptant, cette moitie est tenue
        partout. La moitie spec est `test_granularite_0x_gravee_spec`.
        """
        c = " ".join(self.texte.split())
        faux = [cle for cle, tenu in {
            "C1 ancienne phrase absente (contrat § 3.5)":
                "un écart mineur avertit sans refuser" not in c,
            "C2 refus de la majeure dans les deux sens ET de la mineure tant que "
            "0.x (contrat § 3.5, d'un seul tenant)":
                "un écart de majeure est refusé, bruyamment, dans les deux sens — "
                "et, tant que `version_contrat` est en `0.x`, un écart de mineure "
                "l'est aussi" in c,
            "C3 avertissement du correctif, ou de la mineure a partir de 1.0 "
            "(contrat § 3.5)":
                "un écart de correctif, ou de mineure à partir de `1.0`, avertit "
                "sans refuser" in c,
            "C4 en 0.x une rupture exige au moins une mineure (contrat § 2, "
            "ligne 0.x de la table)":
                "| En `0.x` | Une suppression ou un changement d'entrée exige une "
                "entrée au CHANGELOG, rubrique **Contrat**, et au moins une montée "
                "de mineure de `version_contrat` ; un correctif (`0.y.Z`) n'ajoute, "
                "ne change ni ne retire aucune entrée |" in c,
            "C5 meme promesse aux limites du document (contrat § 6)":
                "Une entrée peut changer ou disparaître avec une ligne au CHANGELOG "
                "et au moins une montée de mineure de `version_contrat`." in c,
        }.items() if not tenu]
        self.assertEqual(
            faux, [],
            "granularite 0.x du lockstep non gravee au contrat — propositions "
            f"absentes ou ancienne phrase revenue : {faux}",
        )

    def test_granularite_0x_gravee_spec(self):
        """T-00000747 — LA GRANULARITE 0.x DU LOCKSTEP, MOITIE SPEC : ELLE NE VOYAGE PAS.

        Deux sites de la spec de la refonte portent la regle : la clause 1 de
        « UN NOYAU INSTALLE PAR POSTE » et l'item « version de contrat verifiee
        a chaque invocation de cadre hook » de la Phase 4bis. Epingles : S2 et
        S3 (noyau par poste), S4 (l'ancienne phrase de la Phase 4bis absente),
        S5 (substitution 3(b) du plan), S7 (la substitution 3(a) ENTIERE — la
        premiere redaction ne la tenait que par l'absence de l'ancienne, donc
        une suppression pure ou une permutation 0.x/1.0 passait), et S8 (le
        fondement dit « version de contrat » et non « le kit » : `__version__`
        et `__version_contrat__` sont independants).

        CE QU'IL N'EPINGLE PAS. S1 (compte des renvois a S-00002178) et S6
        (aucun renvoi « SemVer § 4 ») du temoin A2 du plan restent hors banc —
        d'ou la numerotation qui saute S1 et S6 ; le compte S1 a d'ailleurs
        change des que le corollaire a ete ecrit. Le corollaire lui-meme, dans
        la spec (principe « contrat declare » et etape Version du script de
        release), n'est pas epingle ici : sa moitie contrat l'est, par C4 et C5.

        SAUT AVANT LA REFERENCE. La spec est `strip:` : sur un arbre adoptant,
        reconnu a l'absence du marqueur d'identite du kit (lui-meme `strip:`),
        ce test saute AVANT de nommer la spec ; sur le kit il ne saute jamais,
        donc une spec absente y fait echouer la lecture au lieu de sauter.
        """
        # adopting-tree: le marqueur d'identite du kit ne voyage pas (strip:)
        est_le_kit = (ROOT / ".agents" / "IS_THE_KIT").is_file()
        if not est_le_kit:
            self.skipTest("arbre adoptant : la spec de la refonte ne voyage pas "
                          "(strip:) — la moitie contrat est tenue par "
                          "test_granularite_0x_gravee_contrat")
        spec = (ROOT / "docs" / "PROMPT-refonte-packaging-cadre.md").read_text(
            encoding="utf-8")
        faux = [cle for cle, tenu in {
            "S2 lockstep etendu a la montee MINEURE en 0.x (spec, noyau par poste)":
                "une montée MINEURE — met tous les projets du poste en lockstep" in spec,
            "S3 ecart de MINEURE refuse comme un majeur (spec, noyau par poste)":
                "l'écart de MINEURE est refusé comme un écart majeur" in spec,
            "S4 ancienne phrase absente de la spec (Phase 4bis, substitution 3(a))":
                "avertissement si écart mineur," not in spec,
            "S5 refus sur ecart de mineure en 0.x (spec, Phase 4bis)":
                "sur écart de mineure en 0.x (S-00002178)" in spec,
            "S7 substitution 3(a) entiere (spec, Phase 4bis)":
                ": avertissement si écart de correctif — ou de mineure à partir de "
                "1.0 —, refus explicite si écart majeur — ou de mineure tant que "
                "`version_contrat` est en 0.x (S-00002178) —, avec la commande de "
                "remédiation dans le message." in spec,
            "S8 fondement : version de contrat, pas version du kit (spec, noyau "
            "par poste)":
                "qui laisse passer les ruptures en mineur tant que la version de "
                "contrat est en 0.x)" in spec,
        }.items() if not tenu]
        self.assertEqual(
            faux, [],
            "granularite 0.x du lockstep (S-00002178) non gravee dans la spec — "
            f"sous-chaines absentes ou ancienne phrase revenue : {faux}",
        )


class VendorSeulTests(unittest.TestCase):
    """TEMOIN N (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot N) : l'introspection lit le
    paquet que `vendor_paths` designe. Kit jetable : CE banc, `surface_kit.py`,
    `vendor_paths.py`, le verrou, le paquet sous `.agents/vendor/cadre`, et un
    LEURRE `src/cadre` qui leve a l'import — le neuf gagne, l'ancien n'est
    jamais lu. Mutants : `ROOT / "src" / "cadre"` ou `sys.path.insert(0,
    ROOT / "src")` sans `charger_paquet` rendent ce temoin rouge."""

    def test_vendor_seul_n(self):
        with tempfile.TemporaryDirectory(prefix="vendor-n-") as tmp:
            kit = Path(tmp) / "kit"
            for rel in (".agents/bin/vendor_paths.py", ".agents/evals/surface_kit.py",
                        "contract.lock.json"):
                (kit / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, kit / rel)
            banc = kit / ".agents" / "evals" / Path(__file__).name
            shutil.copyfile(__file__, banc)
            shutil.copytree(_VENDOR.exiger(ROOT, "cadre"), kit / ".agents" / "vendor" / "cadre",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            leurre = kit / "src" / "cadre"
            leurre.mkdir(parents=True)
            for nom in ("__init__.py", "cli.py"):
                (leurre / nom).write_text('raise ImportError("ancien src/cadre lu")\n',
                                          encoding="utf-8")
            sonde = (
                "import json, runpy, sys\n"
                "m = runpy.run_path(sys.argv[1])\n"
                "T = m['ContractDiffTests']\n"
                "exposees, reservees = T._cli_reelle()\n"
                "print(json.dumps({'exposees': sorted(exposees), 'reservees': sorted(reservees),\n"
                "  'lues': sorted(T._variables_lues_par_ast()),\n"
                "  'cadre': sys.modules['cadre'].__file__}))\n")
            r = subprocess.run([sys.executable, "-I", "-B", "-c", sonde, str(banc)],
                               cwd=kit, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vu = json.loads(r.stdout.strip().splitlines()[-1])
            exposees, reservees = ContractDiffTests._cli_reelle()
            self.assertEqual(vu["exposees"], sorted(exposees))
            self.assertEqual(vu["reservees"], sorted(reservees))
            self.assertIn("CADRE_STATE_DIR", vu["lues"], vu["lues"])
            self.assertEqual(Path(vu["cadre"]).resolve().parent,
                             (kit / ".agents" / "vendor" / "cadre").resolve())


if __name__ == "__main__":
    unittest.main()
