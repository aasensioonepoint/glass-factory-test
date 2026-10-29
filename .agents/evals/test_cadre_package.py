#!/usr/bin/env python3
"""CHECKS DE LA PHASE 1 — `no_hardcoded_paths`, `check_no_network`,
`check_orchestration_purity`, et `check_cli_mode_source` (le mode SOURCE de la
CLI ; son côté INSTALLÉ est `check_cli_mode_installed`, dans
`test_cadre_cli_installed.py`).

Entrées du `checks.manifest.json`, phase 1. Tournent dans la porte par `pytest`,
comme tous les autres : `pytest.ini` liste `.agents/evals` dans `testpaths`.

CE QUE CES CHECKS BORNENT, ET CE QU'ILS NE BORNENT PAS. Ils portent sur
le paquet `cadre` — `.agents/vendor/cadre/`, ou `src/cadre/` avant le
déplacement (`vendor_paths.py`) — **et sur lui seul**. Ce n'est pas une timidité : le reste du dépôt
migrera par lots, et un check qui rougirait sur les 35 fichiers pas encore
migrés serait désarmé le premier jour. Ce qu'ils garantissent est donc « le
paquet naît propre et le reste », pas « tout le dépôt est propre » — la seconde
affirmation viendra quand la migration sera finie, et pas avant.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet où qu'il vive (`.agents/vendor/cadre`, sinon `src/cadre`) : la règle
# de `vendor_paths.py`, chargé PAR CHEMIN (patron v3prep), jamais recopiée.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_package_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
PKG = _VENDOR.dossier_paquet(ROOT, "cadre") or ROOT / _VENDOR.ANCIENS["cadre"]
# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant ».
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
# adopting-tree: le manifeste de la distribution ne voyage pas (strip: pyproject.toml,
# S-00004099) ; hors du kit, les arms qui le lisent n'ont de sujet que s'il déclare `cadre-kit`.
MANIFESTE = ROOT / "pyproject.toml"
SAUT_DISTRIBUTION = (
    "SAUT ANNONCE : arbre adoptant (marqueur .agents/IS_THE_KIT absent) dont pyproject.toml "
    "ne déclare pas la distribution `cadre-kit` — le manifeste du kit ne voyage pas "
    "(strip: pyproject.toml) : cet arm n'a pas de sujet ici")


def sources() -> list[Path]:
    return sorted(PKG.rglob("*.py")) if PKG.is_dir() else []


def distribution_hors_sujet() -> bool:
    """Vrai sur un arbre ADOPTANT dont `pyproject.toml` ne déclare pas `cadre-kit` :
    absent (il ne voyage pas) ou celui du projet adoptant. JAMAIS vrai dans le kit, où
    un manifeste absent, illisible ou renommé reste un ÉCHEC des arms qui le lisent."""
    if EST_LE_KIT:
        return False
    try:
        charge = tomllib.loads(MANIFESTE.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        return True
    projet = charge.get("project")
    return not (isinstance(projet, dict) and projet.get("name") == "cadre-kit")


class SqueletteTests(unittest.TestCase):
    def test_le_paquet_existe_et_n_est_pas_vide(self):
        """NON-VACUITÉ. Tous les balayages ci-dessous passeraient sur zéro
        fichier, et un paquet absent rendrait cette suite entièrement verte."""
        self.assertTrue(PKG.is_dir(), f"{PKG} absent — livrable de la Phase 1")
        self.assertGreaterEqual(len(sources()), 3, "paquet trop maigre pour prouver quoi que ce soit")

    def test_le_manifeste_de_la_distribution_existe(self):
        """Dans le kit, `pyproject.toml` bâtit la distribution : absent, c'est un ÉCHEC.
        Il ne voyage pas (S-00004099) : hors du kit, l'arm se saute en le disant."""
        if distribution_hors_sujet():
            self.skipTest(SAUT_DISTRIBUTION)
        self.assertTrue(MANIFESTE.is_file(), "pyproject.toml absent")

    def test_le_paquet_ne_declare_aucune_dependance_d_execution(self):
        """L'INVARIANT « stdlib seule » COMMENCE ICI. Une table `dependencies` vide est ce qui
        rend un scan de dépendances concluant en une ligne ; la remplir ouvrirait
        une surface réseau que `check_no_network` ne verrait pas, puisqu'elle
        vivrait dans le code d'un tiers."""
        if distribution_hors_sujet():
            self.skipTest(SAUT_DISTRIBUTION)
        texte = MANIFESTE.read_text(encoding="utf-8")
        m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", texte, flags=re.M | re.S)
        self.assertIsNotNone(m, "pyproject.toml ne déclare pas de table `dependencies`")
        self.assertEqual(m.group(1).strip(), "", "le noyau doit rester stdlib seule")

    def test_le_paquet_ne_declare_aucune_licence(self):
        """DÉCISION PILOTE DU 2026-09-14, ET ELLE N'ÉTAIT TENUE PAR RIEN.

        `pyproject.toml` portait `license = { text = "Proprietary" }`. Le pilote
        l'a retiré : « on package juste pour que les gens ne récupèrent pas le
        code » — la wheel est un mécanisme de distribution, pas une prise de
        position juridique.

        POURQUOI UN BANC ET PAS SEULEMENT LE COMMENTAIRE. Le fichier porte dix-
        sept lignes expliquant ce retrait, et le binôme a relevé l'asymétrie :
        `dependencies = []` est verrouillé par l'arm ci-dessus, `license` ne
        l'était par RIEN. Un champ retiré revient sans bruit — un `uv init`, un
        outil qui « complète » la métadonnée, une relecture bien intentionnée —
        et le commentaire expliquerait alors l'absence d'un champ présent. Une
        décision tenue par du texte est tenue par la mémoire de celui qui l'a
        lue ; ce dépôt a mesuré ce que vaut une règle tenue par la mémoire.

        CE QUE CET ARM NE DIT PAS : il ne juge pas le fond. Si le pilote décide
        un jour de déclarer une licence, c'est CET ARM qu'on réécrit — et le
        rouge force alors la conversation au lieu de la laisser se produire par
        inadvertance.
        """
        if distribution_hors_sujet():
            self.skipTest(SAUT_DISTRIBUTION)
        projet = tomllib.loads(MANIFESTE.read_text(encoding="utf-8"))["project"]
        for champ in ("license", "license-files"):
            self.assertNotIn(
                champ, projet,
                f"`{champ}` est revenu dans [project]. C'est peut-être voulu — "
                "mais c'est une DÉCISION PILOTE (2026-09-14, retrait de "
                "`Proprietary`), donc elle se reprend explicitement : réécris "
                "cet arm plutôt que de le contourner.",
            )
        self.assertNotIn(
            "License :: ", " ".join(projet.get("classifiers", [])),
            "un classifier de licence dit la même chose que le champ retiré, "
            "par une autre porte",
        )


class DistributionHorsSujetTests(unittest.TestCase):
    """Le PRÉDICAT des trois sauts ci-dessus éprouvé seul (S-00004099), sur des
    manifestes FIXTURES, jamais celui de ROOT : il saute hors du kit sans la
    distribution, et ne saute JAMAIS dans le kit.
    MUTATIONS : `if EST_LE_KIT: return False` retiré → kit sans manifeste rend True
    → rouge ; comparaison du nom retirée → manifeste étranger rend False → rouge."""

    def _verdict(self, est_le_kit: bool, texte: str | None) -> bool:
        with tempfile.TemporaryDirectory(prefix="distribution-") as d:
            manifeste = Path(d) / "pyproject.toml"
            if texte is not None:
                manifeste.write_text(texte, encoding="utf-8")
            with mock.patch.multiple(sys.modules[__name__], EST_LE_KIT=est_le_kit,
                                     MANIFESTE=manifeste):
                return distribution_hors_sujet()

    def test_dans_le_kit_le_saut_ne_mord_jamais(self):
        for texte in (None, '[project]\nname = "autre"\n', "[project\n"):
            with self.subTest(texte=texte):
                self.assertFalse(self._verdict(True, texte))

    def test_hors_du_kit_seule_la_distribution_cadre_kit_garde_les_arms(self):
        cas = {"absent": None, "étranger": '[project]\nname = "mon-projet"\n',
               "illisible": "[project\n", "project scalaire": 'project = "x"\n'}
        for nom, texte in cas.items():
            with self.subTest(cas=nom):
                self.assertTrue(self._verdict(False, texte))
        self.assertFalse(self._verdict(False, '[project]\nname = "cadre-kit"\n'))


class NoHardcodedPathsTests(unittest.TestCase):
    """`no_hardcoded_paths` — une seule politique de chemin, dans un seul module."""

    SEUL_AUTORISE = "paths.py"

    def test_aucun_dunder_file_hors_de_paths(self):
        fautifs = [
            f"{p.relative_to(ROOT)}:{n.lineno}"
            for p in sources() if p.name != self.SEUL_AUTORISE
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
            if isinstance(n, ast.Name) and n.id == "__file__"
        ]
        self.assertEqual(
            fautifs, [],
            "`__file__` hors de `paths.py` : la résolution de chemin vit à UN "
            f"endroit, sinon le paquet cesse d'être déplaçable. {fautifs}",
        )

    @staticmethod
    def _docstrings(arbre: ast.AST) -> set[int]:
        """Les identités des nœuds qui sont des DOCSTRINGS, pour les exclure.

        La première rédaction cherchait `rev-parse` dans le TEXTE du fichier, et
        elle a rougi sur `__init__.py` — dont la docstring EXPLIQUE la règle.
        Un check qui refuse qu'on documente ce qu'il interdit se fait
        contourner en supprimant la documentation : le pire des deux."""
        vus = set()
        for n in ast.walk(arbre):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                corps = getattr(n, "body", None)
                if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant) \
                        and isinstance(corps[0].value.value, str):
                    vus.add(id(corps[0].value))
        return vus

    def test_aucune_racine_git_hors_de_paths(self):
        """La cible est un `rev-parse` EXÉCUTÉ, pas un `rev-parse` expliqué."""
        fautifs = []
        for p in sources():
            if p.name == self.SEUL_AUTORISE:
                continue
            arbre = ast.parse(p.read_text(encoding="utf-8"))
            docs = self._docstrings(arbre)
            for n in ast.walk(arbre):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                        and "rev-parse" in n.value and id(n) not in docs:
                    fautifs.append(f"{p.relative_to(ROOT)}:{n.lineno}")
        self.assertEqual(fautifs, [], f"`git rev-parse` exécuté hors de `paths.py` : {fautifs}")

    def test_le_controle_negatif_de_la_racine_git_mord(self):
        """Le détecteur doit voir un `rev-parse` de CODE et ignorer celui d'une
        docstring — les deux moitiés, sinon il ne mesure rien de précis."""
        code = ast.parse('"""Explique rev-parse."""\nimport subprocess\nsubprocess.run(["git", "rev-parse"])\n')
        docs = self._docstrings(code)
        vus = [n for n in ast.walk(code) if isinstance(n, ast.Constant)
               and isinstance(n.value, str) and "rev-parse" in n.value and id(n) not in docs]
        self.assertEqual(len(vus), 1, "le détecteur confond le code et la prose")

    def test_le_controle_negatif_mord(self):
        """L'ARME DOIT POUVOIR ROUGIR. Une source synthétique portant `__file__`
        doit être vue par le même code de détection — sinon ce banc certifie une
        propriété qu'il ne mesure pas."""
        arbre = ast.parse("chemin = __file__\n")
        trouve = [n for n in ast.walk(arbre) if isinstance(n, ast.Name) and n.id == "__file__"]
        self.assertEqual(len(trouve), 1, "le détecteur ne voit plus `__file__`")


class NoNetworkTests(unittest.TestCase):
    """`check_no_network` — ce qui garantit RÉELLEMENT que rien ne part."""

    INTERDITS = ("requests", "httpx", "urllib", "socket", "aiohttp", "http.client")

    def test_aucun_client_reseau_dans_le_noyau(self):
        fautifs = []
        for p in sources():
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                noms = []
                if isinstance(n, ast.Import):
                    noms = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module:
                    noms = [n.module]
                for nom in noms:
                    racine = nom.split(".")[0]
                    if racine in self.INTERDITS or nom in self.INTERDITS:
                        fautifs.append(f"{p.relative_to(ROOT)}:{n.lineno} → {nom}")
        self.assertEqual(
            fautifs, [],
            "client réseau dans le noyau. L'absence de réseau est ce qui rend "
            f"vraie la promesse « rien ne part de la machine ». {fautifs}",
        )

    def test_le_controle_negatif_mord(self):
        arbre = ast.parse("import requests\nfrom urllib import request\n")
        vus = []
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                vus += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                vus.append(n.module)
        self.assertTrue({"requests", "urllib"} <= set(vus), "le détecteur ne voit plus les imports réseau")


class OrchestrationPurityTests(unittest.TestCase):
    """`check_orchestration_purity` — ce qui DÉCIDE ne touche ni disque ni
    sous-processus. C'est la couture qui rendra le déport possible : la logique
    qui ordonne les étapes doit pouvoir tourner ailleurs que là où elles
    s'exécutent.

    LE PÉRIMÈTRE EST DÉRIVÉ, PLUS ÉNUMÉRÉ, et c'est une correction de la revue
    de clôture du 2026-09-12. Il était un n-uplet de QUATRE NOMS DE FICHIERS
    tenus à la main — `orchestrateur.py`, `graph.py`, `nodes.py`, `plan.py` —
    qui n'existaient dans aucun arbre : le banc appelait donc `skipTest`, pendant
    que `checks.manifest.json` le déclarait `actif`. Un check actif qui ne mesure
    rien est pire qu'un check absent, parce qu'il occupe la place. Et le
    périmètre énuméré ne pouvait par construction jamais couvrir le module écrit
    APRÈS lui : `config.py`, arrivé en Phase 1, faisait de l'E/S disque directe
    sans qu'aucune ligne ne rougisse.

    LE PÉRIMÈTRE EST DONC « TOUT SAUF LES EXEMPTIONS », ET LE FILTRE EST PAR
    CHEMIN RELATIF DEPUIS L'ÉTAPE C (point 4). `paths` résout, `workspace` fait
    les E/S, `executor` lance les commandes : ces trois-là sont hors périmètre
    par construction, ainsi que le `__init__.py` RACINE qui ne fait que
    ré-exporter. `ledger/store.py` N'EST PLUS exempté (binôme C) : il ouvre
    `sqlite3.connect`, mais `connect` n'est pas un verbe de `IO_PAR_METHODE` et
    `sqlite3` pas un import impur, donc il PASSE ce filet sans exemption —
    l'exemption ne faisait que le retirer de `IMPORTS_IMPURS`. Son unicité de site
    `connect` est tenue par le banc LOCAL `test_cadre_ledger_purete`. Le filtre
    reste par CHEMIN RELATIF : un filtre par NOM exemptait `ledger/__init__.py`
    (donc n'importe quel `__init__.py` niché) — c'est le trou P5. Tout le reste
    DÉCIDE, donc doit passer par la couture.

    L'E/S PAR `Workspace` EST SANCTIONNÉE, PAS INTERDITE — c'est tout l'objet de
    la couture. Le contrôle distingue donc le récepteur : `atelier.read_text(...)`
    sur un nom lié à un `Workspace(...)` est correct, `chemin.read_text()` sur un
    `Path` ne l'est pas. Un contrôle sur le seul NOM de méthode confondrait les
    deux et rougirait exactement sur le code qui vient d'être corrigé.

    ET IL PORTE SUR L'ARBRE SYNTAXIQUE, PAS SUR LE TEXTE. La rédaction
    précédente cherchait `"subprocess"` et `"open("` dans les octets du fichier :
    c'est le piège dans lequel ce dépôt est déjà tombé deux fois, où la docstring
    qui explique la règle déclenche la règle. Il n'avait jamais mordu ici faute
    de périmètre ; il aurait mordu au premier module couvert.
    """

    #: Exemptions par CHEMIN RELATIF (jamais par nom, depuis l'étape C point 4).
    #: Les trois primitives touchent le disque par construction ; `__init__.py`
    #: est le ré-export RACINE (rel == "__init__.py" — un `ledger/__init__.py`
    #: niché reste EN périmètre). `ledger/store.py` N'EST PLUS exempté ici (binôme
    #: C) : mesuré, `_fautifs_purete([store.py])` rend `[]` sans exemption —
    #: `sqlite3.connect` n'est ni un import impur ni un verbe de `IO_PAR_METHODE`,
    #: donc l'exempter ne faisait que le retirer de `IMPORTS_IMPURS` pour rien. Son
    #: unicité de site `connect` est tenue par le banc LOCAL `test_cadre_ledger_purete`.
    EXEMPTIONS_RELATIVES = ("paths.py", "workspace.py", "executor.py",
                            "__init__.py")

    #: Modules dont l'import suffit à rendre un module d'orchestration impur.
    IMPORTS_IMPURS = {"subprocess", "shutil", "socket", "urllib", "http", "shlex"}

    #: Noms de méthodes qui touchent le disque. Autorisés sur un `Workspace`,
    #: refusés sur tout le reste.
    IO_PAR_METHODE = {"read_text", "read_bytes", "write_text", "write_bytes",
                      "unlink", "mkdir", "rmdir", "touch", "glob", "rglob",
                      "iterdir", "open", "replace", "rename", "chmod",
                      "walk", "resolve", "is_dir"}

    def _modules_d_orchestration(self, racine: Path | None = None) -> list[Path]:
        """Les `*.py` sous `racine` SAUF les exemptions par CHEMIN RELATIF.

        `racine` défaut = le paquet réel (`PKG`) ; un appelant l'injecte (ARBRE-
        FANTÔME du contrôle négatif) sans passer par `sources()`, donc sans
        dépendre de l'arbre suivi — c'est ce qui rend le contrôle négatif
        jouable en worktree sans y déposer de fichier impur."""
        base = racine if racine is not None else PKG
        fichiers = sorted(base.rglob("*.py")) if base.is_dir() else []
        return [
            p for p in fichiers
            if p.relative_to(base).as_posix() not in self.EXEMPTIONS_RELATIVES
        ]

    @classmethod
    def _fautifs_purete(cls, cibles: list[Path], racine: Path) -> list[str]:
        """Les infractions de pureté des `cibles`. Les chemins sont rendus
        RELATIFS à `racine` pour être lisibles aussi bien sur le paquet réel que
        sur un arbre-fantôme temporaire."""
        fautifs: list[str] = []
        for p in cibles:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
            ateliers = cls._noms_de_workspace(arbre)
            rel = p.relative_to(racine).as_posix()
            for n in ast.walk(arbre):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        if a.name.split(".")[0] in cls.IMPORTS_IMPURS:
                            fautifs.append(f"{rel}:{n.lineno} import {a.name}")
                elif isinstance(n, ast.ImportFrom) and n.module \
                        and n.module.split(".")[0] in cls.IMPORTS_IMPURS:
                    fautifs.append(f"{rel}:{n.lineno} from {n.module}")
                elif isinstance(n, ast.Call):
                    f = n.func
                    if isinstance(f, ast.Name) and f.id == "open":
                        fautifs.append(f"{rel}:{n.lineno} → open()")
                    elif isinstance(f, ast.Attribute) and f.attr in cls.IO_PAR_METHODE:
                        recepteur = f.value
                        sanctionne = (isinstance(recepteur, ast.Name)
                                      and recepteur.id in ateliers)
                        if not sanctionne:
                            fautifs.append(
                                f"{rel}:{n.lineno} → .{f.attr}() hors `Workspace`")
        return fautifs

    @staticmethod
    def _noms_de_workspace(arbre: ast.AST) -> set[str]:
        """Les noms DÉCLARÉS `Workspace`, dont l'E/S est sanctionnée.

        DEUX SOURCES, ET LA SECONDE EST NÉCESSAIRE. Une liaison directe
        (`atelier = Workspace(...)`) se voit ; un nom qui sort d'un déballage de
        tuple ou d'un paramètre de fonction ne se voit pas, et refuser d'inférer
        est la bonne réponse — un banc qui devine le type se trompe en silence.
        La sortie est donc l'ANNOTATION : un paramètre `atelier: Workspace` ou un
        `atelier: Workspace = ...` déclare ce que le banc ne peut pas déduire.
        Le coût est assumé et il est faible : la déclaration est à l'endroit où
        un lecteur la cherche de toute façon.
        """
        noms: set[str] = set()

        def _est_workspace(annotation: ast.expr | None) -> bool:
            if annotation is None:
                return False
            texte = ast.unparse(annotation)
            return "Workspace" in texte

        for n in ast.walk(arbre):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
                    and isinstance(n.value.func, ast.Name) and n.value.func.id == "Workspace":
                noms |= {c.id for c in n.targets if isinstance(c, ast.Name)}
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                    and _est_workspace(n.annotation):
                noms.add(n.target.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = n.args
                for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
                    if _est_workspace(arg.annotation):
                        noms.add(arg.arg)
        return noms

    def test_aucun_sous_processus_ni_disque_dans_l_orchestration(self):
        cibles = self._modules_d_orchestration()
        self.assertTrue(
            cibles,
            f"aucun module hors des exemptions dans `{PKG}` — le banc "
            "passerait sur une population VIDE. C'est exactement l'etat dans "
            "lequel il a vecu jusqu'au 2026-09-12.",
        )
        fautifs = self._fautifs_purete(cibles, PKG)
        self.assertEqual(
            fautifs, [],
            "acces disque ou sous-processus hors des exemptions. `paths` "
            "resout, `Workspace` fait les E/S, `Executor` lance : un module qui "
            f"court-circuite la couture la rend inexistante. {fautifs}",
        )

    def test_le_controle_negatif_de_la_purete_mord(self):
        """L'ARME DOIT POUVOIR ROUGIR, ET SON PÉRIMÈTRE DOIT NAÎTRE NON VIDE.

        DEUX propriétés en une, chacune paramétrée, pas décorative :

        1. NON-VACUITÉ DU PÉRIMÈTRE. Les sous-paquets sont DÉTECTÉS par
           `rglob("__init__.py")` sous `PKG` (R-A13, pas `iterdir`), en
           excluant `__pycache__` et le `__init__.py` RACINE. Tant que
           `PKG` ne porte AUCUN sous-paquet — l'état d'avant `ledger/` —
           `assertTrue(noms)` échoue : le banc naît ROUGE et ne verdit qu'avec
           `ledger/`, dans le même commit que ce filtre (sinon commit rouge ou
           commit exempté).

        2. LE FILTRE PAR CHEMIN ATTRAPE UN `__init__.py` NICHÉ IMPUR. Pour
           CHAQUE sous-paquet détecté, on écrit dans un ARBRE-FANTÔME sous
           `tmp_path` — JAMAIS l'arbre suivi, qu'un banc interrompu laisserait
           sale — un `<nom>/__init__.py` portant `import subprocess` et un
           `Path("x").read_text()`, et on EXIGE que chacun soit attrapé. Un
           filtre par NOM les aurait exemptés (trou P5)."""
        noms = sorted({
            p.parent.name for p in PKG.rglob("__init__.py")
            if "__pycache__" not in p.parts and p.parent != PKG
        })
        self.assertTrue(
            noms,
            f"aucun sous-paquet sous `{PKG}` — le controle negatif passerait "
            "sur une population VIDE (etat d'avant `ledger/`).",
        )
        self.assertIn("ledger", noms, "`ledger/` attendu comme sous-paquet")

        with tempfile.TemporaryDirectory() as tmp:
            fantome = Path(tmp) / "cadre"
            fantome.mkdir()
            # `__init__.py` RACINE : exempté, il ne doit PAS être attrapé.
            (fantome / "__init__.py").write_text("", encoding="utf-8")
            attendus = []
            for nom in noms:
                sous = fantome / nom
                sous.mkdir()
                (sous / "__init__.py").write_text(
                    "import subprocess\n"
                    "from pathlib import Path\n"
                    "subprocess.run(['true'])\n"
                    "Path('x').read_text()\n",
                    encoding="utf-8",
                )
                attendus.append(f"{nom}/__init__.py")
            cibles = self._modules_d_orchestration(racine=fantome)
            # Le `__init__.py` racine est exempté (rel == "__init__.py").
            self.assertNotIn(
                fantome / "__init__.py", cibles,
                "le `__init__.py` RACINE ne doit pas entrer au perimetre",
            )
            fautifs = self._fautifs_purete(cibles, fantome)
            for rel in attendus:
                self.assertTrue(
                    any(rel in f for f in fautifs),
                    f"un `__init__.py` niche impur ({rel}) n'a PAS ete attrape : "
                    f"{fautifs}. Le filtre par nom l'aurait exempte (trou P5).",
                )

    def test_le_perimetre_EXCLUT_bien_les_trois_primitives(self):
        """CONTROLE DE NON-VACUITE DE L'EXCLUSION, ET IL DECIDE D'UNE PRECEDENCE.

        Le filtre par CHEMIN RELATIF exempte les trois primitives et le ré-export
        RACINE. Le `couverts` lit des chemins relatifs : sous l'ancien
        `{p.name …}`, `ledger/__init__.py` aurait fait apparaître `__init__.py` au
        périmètre et cassé l'assertion. `config.py` DÉCIDE d'une précédence et
        reste couvert. `ledger/store.py` N'EST PLUS exempté (binôme C) et DOIT donc
        être couvert : il passe le filet sans exemption, `connect` n'étant pas un
        verbe surveillé ici."""
        couverts = {p.relative_to(PKG).as_posix()
                    for p in self._modules_d_orchestration()}
        for exempt in self.EXEMPTIONS_RELATIVES:
            self.assertNotIn(
                exempt, couverts,
                f"{exempt} est exempte par construction, il ne doit pas etre couvert",
            )
        self.assertIn("config.py", couverts,
                      "`config.py` DECIDE d'une precedence : il doit etre couvert")
        # L'EXEMPTION `ledger/store.py` A ETE RETIREE (binome C) : store.py doit
        # etre COUVERT (il passe le filet sans exemption) et l'exemption ne doit
        # plus le mentionner, ni le dossier `ledger`, ni un `store.py` a la racine.
        self.assertNotIn("ledger/store.py", self.EXEMPTIONS_RELATIVES,
                         "l'exemption `ledger/store.py` a ete retiree (mesuree inutile)")
        self.assertIn("ledger/store.py", couverts,
                      "store.py doit etre couvert : il passe le filet sans exemption")
        self.assertNotIn("ledger", self.EXEMPTIONS_RELATIVES,
                         "aucune exemption de dossier `ledger`")
        self.assertNotIn("store.py", self.EXEMPTIONS_RELATIVES,
                         "aucun `store.py` exempte")

    def test_les_trois_verbes_ajoutes_MORDENT_et_la_couture_est_SANCTIONNEE(self):
        """LE TÉMOIN QUI ROUGIT (T-00000633, §4). Sur un ARBRE-FANTÔME jamais
        suivi : les trois verbes ajoutés (`walk`, `resolve`, `is_dir`) NUS
        doivent être nommés fautifs — ROUGE tant que l'étape 6 n'a pas étendu
        `IO_PAR_METHODE`, VERT après —, et les MÊMES appels derrière un
        `Workspace` déclaré NE doivent PAS l'être, sans quoi l'extension
        rougirait le remède. `est_repertoire` est RETIRÉ de la discrimination :
        le nom surveillé est `is_dir`, jamais `est_repertoire`, donc un
        `atelier.est_repertoire(...)` n'est jamais fautif — vrai par VACUITÉ. La
        seconde moitié GROSSIT seule : pour CHAQUE verbe du jeu, un
        `Path('x').<verbe>()` est attrapé et un `atelier.<verbe>()` ne l'est
        pas."""
        with tempfile.TemporaryDirectory() as tmp:
            fantome = Path(tmp) / "cadre"
            fantome.mkdir()
            (fantome / "__init__.py").write_text("", encoding="utf-8")

            # -- moitié qui PEUT échouer : les trois verbes nus sont nommés, et
            #    les mêmes appels derrière un `Workspace` ne le sont pas.
            trois = fantome / "trois.py"
            trois.write_text(
                "from pathlib import Path\n"
                "from cadre.workspace import Workspace\n"
                "\n"
                "def nu(r: Path):\n"
                "    r.resolve()\n"
                "    r.is_dir()\n"
                "\n"
                "def par_module(r):\n"
                "    import os\n"
                "    os.walk(r)\n"
                "\n"
                "def sanctionne(p):\n"
                "    atelier = Workspace(p)\n"
                "    atelier.walk(elaguer=lambda _n: False)\n"
                "    atelier.resolve('x')\n",
                encoding="utf-8",
            )
            cibles = self._modules_d_orchestration(racine=fantome)
            fautifs = self._fautifs_purete(cibles, fantome)
            for verbe in ("resolve", "is_dir", "walk"):
                self.assertTrue(
                    any(f".{verbe}()" in f for f in fautifs),
                    f"le verbe nu `{verbe}` n'est PAS nomme fautif : {fautifs}. "
                    "L'etape 6 (extension de `IO_PAR_METHODE`) n'est pas encore "
                    "appliquee — c'est l'etat ROUGE-AVANT attendu.",
                )
            # La couture est SANCTIONNEE : les DEUX appels derriere `atelier`
            # (`atelier.walk`, `atelier.resolve`) ne sont PAS comptes — sinon on
            # aurait 5 fautifs, pas 3.
            trois_fautifs = [f for f in fautifs if "trois.py" in f]
            self.assertEqual(
                len(trois_fautifs), 3,
                "seuls les TROIS sites nus doivent etre fautifs ; un appel "
                f"derriere un `Workspace` a ete compte : {trois_fautifs}",
            )

            # -- seconde moitié, NON-RÉGRESSION qui grossit seule : chaque verbe
            #    du jeu, nu, est attrape ; le meme sur un `Workspace` ne l'est pas.
            verbes = sorted(self.IO_PAR_METHODE)
            nus = fantome / "nus.py"
            nus.write_text(
                "from pathlib import Path\n"
                + "".join(f"Path('x').{v}()\n" for v in verbes),
                encoding="utf-8",
            )
            f_nus = self._fautifs_purete([nus], fantome)
            for v in verbes:
                self.assertTrue(
                    any(f".{v}()" in f for f in f_nus),
                    f"`Path('x').{v}()` n'est pas attrape : {f_nus}",
                )
            ateliers = fantome / "ateliers.py"
            ateliers.write_text(
                "from cadre.workspace import Workspace\n"
                "atelier = Workspace('.')\n"
                + "".join(f"atelier.{v}()\n" for v in verbes),
                encoding="utf-8",
            )
            f_ate = self._fautifs_purete([ateliers], fantome)
            self.assertEqual(
                f_ate, [],
                f"un appel sur un `Workspace` declare a ete nomme fautif : {f_ate}",
            )


class CliModeSourceTests(unittest.TestCase):
    """`check_cli_mode_source` — le comportement de la CLI en mode SOURCE.

    RENOMMÉ le 2026-09-12 (T-00000573). Il s'appelait `check_editable_parity` /
    `PariteEditableInstalleTests` et promettait une parité « editable ET
    installé » dont UN SEUL côté tourne : `_cadre()` force `PYTHONPATH=src` et
    invoque `python -m cadre.cli`, ce qui n'est ni editable, ni installé, et
    n'exerce JAMAIS l'entry point console. La parité était indécidable par
    construction — un chemin d'import forcé gagne toujours sur un paquet
    installé — donc le nom promettait ce que le code ne tient pas, ce qui
    empêche de voir le défaut (L-00000111).

    CE QU'IL MESURE : la CLI répond, `--version` égale `cadre.__version__`,
    `CONFIG_HOME` et `STATE_HOME` suivent quand on les redirige, un nom réservé
    se distingue d'un nom inconnu, et la sortie machine garde son schéma.
    CE QU'IL NE MESURE PAS : l'entry point console `cadre` et le paquet
    installé — tenus depuis T-00000573 par `check_cli_mode_installed`
    (`test_cadre_cli_installed.py` : installation éditable en bac à sable,
    binaire exercé, parité octet à octet avec CE mode) — ni la wheel, qui reste
    à `check_cli_mode_wheel` (`prevu`, T-00000661). Ce banc-ci n'installe rien :
    décision pilote du 2026-09-12, la Phase 1 ne fait pas de `cadre` une
    dépendance installée."""

    def _cadre(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        e = dict(os.environ, PYTHONPATH=str(PKG.parent))
        if env:
            e.update(env)
        return subprocess.run(
            [sys.executable, "-m", "cadre.cli", *args],
            capture_output=True, text=True, cwd=str(ROOT), env=e,
        )

    def test_version_repond_et_egale_celle_du_paquet(self):
        r = self._cadre("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        cadre = _VENDOR.charger_paquet(ROOT, "cadre")

        self.assertEqual(r.stdout.strip(), cadre.__version__)

    def test_les_quatre_racines_sont_deplacables(self):
        """LE CRITÈRE DE SORTIE DE LA PHASE 1, rendu observable. Redirigées vers
        un répertoire temporaire, les racines doivent SUIVRE — sinon « le paquet
        est déplaçable » n'est qu'une affirmation."""
        with tempfile.TemporaryDirectory() as tmp:
            conf, etat = Path(tmp) / "conf", Path(tmp) / "etat"
            r = self._cadre("paths", "--json", env={
                "CADRE_CONFIG_HOME": str(conf), "CADRE_STATE_DIR": str(etat)})
            self.assertEqual(r.returncode, 0, r.stderr)
            import json  # noqa: PLC0415

            vu = json.loads(r.stdout)
            self.assertEqual(Path(vu["CONFIG_HOME"]), conf.resolve())
            self.assertEqual(Path(vu["STATE_HOME"]), etat.resolve())

    def test_un_nom_reserve_se_distingue_d_un_nom_inconnu(self):
        """La différence entre « ce nom n'existe pas » et « ce nom est pris, il
        arrive » est exactement ce que le statut `reserve` promet."""
        r = self._cadre("doctor")
        self.assertEqual(r.returncode, 2)
        self.assertIn("RÉSERVÉ", r.stderr)

    # -- les constats de la revue de clôture du 2026-09-12 --------------

    def test_la_sortie_machine_a_TOUJOURS_les_memes_cles(self):
        """C'EST LA SEULE SORTIE MACHINE DU PAQUET, et son schéma variait.

        `AGENTS_DIR` était affectée APRÈS `PROJECT_ROOT` dans le même `try` :
        hors dépôt, la clé n'était donc jamais posée, et `PROJECT_ROOT` recevait
        la PHRASE D'ERREUR française comme valeur, avec un code de sortie 0 qui
        disait à l'appelant de la croire. Un `jq -r .AGENTS_DIR` rendait un
        chemin ou `null` selon le répertoire courant, et `.PROJECT_ROOT` rendait
        une phrase — deux façons de casser un consommateur sans rien signaler.
        """
        import json  # noqa: PLC0415

        attendues = {"PKG_ROOT", "CONFIG_HOME", "STATE_HOME", "PROJECT_ROOT",
                     "AGENTS_DIR", "STATE_PROJECT", "erreur"}
        dedans = json.loads(self._cadre("paths", "--json").stdout)
        self.assertEqual(set(dedans), attendues)
        self.assertIsNone(dedans["erreur"])
        self.assertIsNotNone(dedans["AGENTS_DIR"])
        self.assertIsNotNone(dedans["STATE_PROJECT"])

        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, "-m", "cadre.cli", "paths", "--json"],
                capture_output=True, text=True, cwd=tmp,
                env={k: v for k, v in os.environ.items()
                     if not k.startswith("CADRE_")} | {"PYTHONPATH": str(PKG.parent)},
            )
            dehors = json.loads(r.stdout)
        self.assertEqual(set(dehors), attendues,
                         "le schema de la sortie machine depend du repertoire courant")
        self.assertIsNone(dehors["PROJECT_ROOT"], "une phrase francaise en guise de chemin")
        self.assertIsNone(dehors["AGENTS_DIR"])
        self.assertIsNone(dehors["STATE_PROJECT"])
        self.assertIsNotNone(dehors["erreur"], "la cause doit etre DITE, pas devinee")
        self.assertEqual(r.returncode, 1,
                         "une racine non resolue doit se voir au code de sortie")

    def test_une_option_inconnue_est_REFUSEE_et_non_avalee(self):
        """`parse_known_args` — nécessaire pour les drapeaux des noms réservés —
        avalait aussi les fautes de frappe des commandes RÉELLES. Mesuré :
        `config explain modele --hotte claude` rendait la valeur d'une AUTRE
        couche en l'étiquetant « posee par : hote », code 0. Une réponse fausse
        ET confiante est le pire mode d'échec d'un outil de diagnostic."""
        for mauvaise in (("paths", "--jsonn"), ("config", "explain", "k", "--hotte", "claude")):
            with self.subTest(argv=mauvaise):
                r = self._cadre(*mauvaise)
                self.assertEqual(r.returncode, 2, f"avale en silence : {r.stdout}")
                self.assertIn("inconnue", r.stderr)

    def test_un_drapeau_de_nom_RESERVE_reste_tolere(self):
        """CONTRÔLE DE NON-VACUITÉ DU REFUS. Le refus ci-dessus ne doit pas
        casser la raison d'être de `parse_known_args` : `cadre init --upgrade`
        est promis au verrou et n'a pas encore de parseur, donc son drapeau doit
        traverser sans provoquer une erreur d'option."""
        r = self._cadre("init", "--upgrade")
        self.assertEqual(r.returncode, 2)
        self.assertIn("RÉSERVÉ", r.stderr)
        self.assertNotIn("inconnue", r.stderr)

    def test_la_racine_projet_se_force_par_environnement(self):
        """Sans cette porte, aucun banc ne peut pointer un arbre temporaire."""
        with tempfile.TemporaryDirectory() as tmp:
            faux = Path(tmp) / "faux-depot"
            (faux / ".agents").mkdir(parents=True)
            r = self._cadre("paths", "--json", env={"CADRE_PROJECT_ROOT": str(faux)})
            import json  # noqa: PLC0415

            self.assertEqual(Path(json.loads(r.stdout)["PROJECT_ROOT"]), faux.resolve())


if __name__ == "__main__":
    unittest.main()
