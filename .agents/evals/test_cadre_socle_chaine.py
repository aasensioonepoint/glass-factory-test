#!/usr/bin/env python3
"""Banc de la chaine du socle (T-00000899) : `data/socle.json` du paquet `cadre`
(`.agents/vendor/cadre/` ou `src/cadre/`, ou qu'il vive) lu par `cadre.socle`, depuis le paquet SEUL.

Trois angles, un par ligne du critere : la chaine est DECLAREE (A), elle est
LISIBLE du paquet installe seul et aucun fichier d'un depot adoptant ne peut la
redefinir (B), elle est ALIGNEE sur ce que le kit dit d'elle (C, kit seul).

Qui lit quoi, pour que chaque mutant soit attribue au temoin qui LIT le fichier
mute : T1 compare `socle.json` a la constante ATTENDU de ce banc ; T8 compare
l'ordre de la ligne `Pipeline mandatory` d'AGENTS.md aux ids de `socle.json` ;
T9 compare les noms d'agents de `socle.json` aux defs `.claude/agents/`.

Borne du critere « aucun fichier du depot adoptant ne la redefinit » : il se
mesure a `pkg_root()`, la racine du paquet charge (partie B). La copie du
paquet `cadre` qu'un adoptant recoit par la template est vendoree dans son arbre ;
son integrite est confiee a `check_socle_integrity` (T-00000901), pas a ce banc.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` où qu'il vive (`.agents/vendor/cadre/` d'abord, `src/cadre/` sinon), chargé par
# chemin par `vendor_paths` ; PKG est CE dossier, la source des copies d'`Atelier` (S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_socle_chaine_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
PKG = _VENDOR.exiger(ROOT, "cadre")
_VENDOR.charger_paquet(ROOT, "cadre")

# Les temoins C lisent AGENTS.md et les defs d'agents du KIT : ailleurs ils SAUTENT en l'annoncant.
# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant ».
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

from cadre import socle  # noqa: E402

# La chaine, ECRITE ICI et jamais lue de la donnee : (id, nature, agents, condition).
ATTENDU = (
    ("language-detector", "agent", ("language-detector",), None),
    ("planner", "agent", ("planner", "planner-sonnet"), None),
    ("plan-critic", "agent", ("plan-critic", "plan-critic-sonnet-max"), None),
    ("gate-humain", "humain", (), None),
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-18, decision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG) :
    # `terraform-deployer` est le slot dev d'une tache IaC, comme `frontend-fidelity` celui d'une tache d'ecran.
    ("dev", "agent", ("dev-mono", "dev-multi", "frontend-fidelity", "terraform-deployer"), None),
    ("design-review", "agent", ("design-review",), "tache-ecran"),
    ("exec-critic", "agent", ("exec-critic",), None),
    ("securite", "agent", ("security-code-review",), None),
    ("securite-dependances", "agent", ("security-orchestrator",), "manifeste-de-dependances-modifie"),
    ("build-index", "deterministe", (), None),
    ("documenter", "agent", ("documenter",), None),
    ("indexer", "agent", ("indexer",), "structure-modifiee"),
    ("revue-cloture", "agent", ("critic-opus", "critic-fable", "critic-sonnet-max"), None),
    ("porte", "deterministe", (), None),
    ("done", "deterministe", (), None),
)
IDS = tuple(r[0] for r in ATTENDU)

# Les huit noeuds de la redaction d'origine (critere d'origine du board, spec:569 avant son remplacement) :
# la doctrine les ETEND sans les contredire, ils restent une sous-suite ordonnee de la chaine.
HUIT_D_ORIGINE = ("planner", "plan-critic", "gate-humain", "dev", "exec-critic",
                  "securite", "documenter", "indexer")


def sous_suite_ordonnee(petit: tuple[str, ...], grand: tuple[str, ...]) -> bool:
    it = iter(grand)
    return all(any(x == y for y in it) for x in petit)


def lignes(s: socle.Socle) -> tuple:
    return tuple((n.id, n.nature, n.agents, n.condition) for n in s.chaine)


def valide() -> dict:
    """Un socle minimal VALIDE, neuf a chaque appel."""
    return {"version_format": 1,
            "chaine": [{"id": "a", "nature": "agent", "agents": ["x"]},
                       {"id": "b", "nature": "humain"},
                       {"id": "c", "nature": "deterministe", "condition": "si-cas"}],
            "voie_directe_depuis": "b"}


# --------------------------------------------------------------------------- A
class ChaineDeclareeTests(unittest.TestCase):
    def test_T1_la_chaine_est_celle_du_banc(self):
        self.assertEqual(lignes(socle.charger()), ATTENDU)

    def test_T2_les_huit_noeuds_d_origine_sont_une_sous_suite_ordonnee(self):
        self.assertTrue(sous_suite_ordonnee(HUIT_D_ORIGINE, socle.charger().ids()))
        # etalonnage : le predicat REFUSE une permutation et un noeud retire
        self.assertFalse(sous_suite_ordonnee(("dev", "planner"), IDS))
        self.assertFalse(sous_suite_ordonnee(HUIT_D_ORIGINE, tuple(i for i in IDS if i != "exec-critic")))

    def test_T2b_la_voie_directe_part_de_dev_inclus(self):
        s = socle.charger()
        self.assertEqual(s.voie_directe_depuis, "dev")
        self.assertEqual(s.voie_directe(), IDS[IDS.index("dev"):])
        for amont in ("language-detector", "planner", "plan-critic", "gate-humain"):
            self.assertNotIn(amont, s.voie_directe())

    def test_T7_chaque_forme_refusee_l_est_par_SocleIllisible(self):
        def avec(f):
            d = valide()
            f(d)
            return d
        refus = {
            "racine liste": [],
            "cle racine inconnue": avec(lambda d: d.update(extra=1)),
            "version absente": avec(lambda d: d.pop("version_format")),
            "version 2": avec(lambda d: d.update(version_format=2)),
            "version booleenne": avec(lambda d: d.update(version_format=True)),
            "version flottante": avec(lambda d: d.update(version_format=1.0)),
            "chaine vide": avec(lambda d: d.update(chaine=[])),
            "chaine non liste": avec(lambda d: d.update(chaine={})),
            "noeud non objet": avec(lambda d: d["chaine"].append("x")),
            "cle de noeud inconnue": avec(lambda d: d["chaine"][0].update(commande="x")),
            "id majuscule": avec(lambda d: d["chaine"][0].update(id="Dev")),
            "id accentue": avec(lambda d: d["chaine"][0].update(id="sécurité")),
            "id a point": avec(lambda d: d["chaine"][0].update(id="a.b")),
            "id vide": avec(lambda d: d["chaine"][0].update(id="")),
            "id non texte": avec(lambda d: d["chaine"][0].update(id=3)),
            "id a saut de ligne final": avec(lambda d: d["chaine"][0].update(id="a\n")),
            "doublon": avec(lambda d: d["chaine"][1].update(id="a")),
            "nature inconnue": avec(lambda d: d["chaine"][1].update(nature="gate")),
            "agent sans agents": avec(lambda d: d["chaine"][0].pop("agents")),
            "agent a liste vide": avec(lambda d: d["chaine"][0].update(agents=[])),
            "nom d'agent invalide": avec(lambda d: d["chaine"][0].update(agents=["Dev Mono"])),
            "humain avec agents": avec(lambda d: d["chaine"][1].update(agents=["x"])),
            "deterministe avec agents": avec(lambda d: d["chaine"][2].update(agents=["x"])),
            "condition invalide": avec(lambda d: d["chaine"][2].update(condition="Si Cas")),
            "voie directe inconnue": avec(lambda d: d.update(voie_directe_depuis="zz")),
            "voie directe absente": avec(lambda d: d.pop("voie_directe_depuis")),
        }
        self.assertIsInstance(socle._valider(valide(), "ref"), socle.Socle)  # etalonnage
        for nom, brut in refus.items():
            with self.subTest(refus=nom):
                with self.assertRaises(socle.SocleIllisible):
                    socle._valider(brut, "ref")

    def test_T7b_un_fichier_illisible_leve_en_nommant_le_fichier(self):
        cas = {"absent": None, "JSON casse": b"{", "binaire": b"\xff\xfe{", "racine liste": b"[]",
               # `json` garde la DERNIERE cle repetee en silence : ici elle rendrait un socle valide.
               "cle en double": b'{"version_format": 1, "chaine": [{"id": "x", "nature": "humain"}], '
                                b'"chaine": [{"id": "a", "nature": "humain"}], "voie_directe_depuis": "a"}'}
        for nom, octets in cas.items():
            with self.subTest(cas=nom), tempfile.TemporaryDirectory() as tmp:
                if octets is not None:
                    (Path(tmp) / "data").mkdir()
                    (Path(tmp) / "data" / "socle.json").write_bytes(octets)
                with self.assertRaises(socle.SocleIllisible) as ctx:
                    socle._lire(socle.Workspace(tmp))
                self.assertIn("socle.json", str(ctx.exception))
        with tempfile.TemporaryDirectory() as tmp:  # un REPERTOIRE a la place du fichier
            (Path(tmp) / "data" / "socle.json").mkdir(parents=True)
            with self.assertRaises(socle.SocleIllisible):
                socle._lire(socle.Workspace(tmp))
        with tempfile.TemporaryDirectory() as tmp:  # etalonnage : un fichier valide se lit
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "socle.json").write_text(json.dumps(valide()), encoding="utf-8")
            self.assertEqual(socle._lire(socle.Workspace(tmp)).ids(), ("a", "b", "c"))

    def test_T7c_un_lien_qui_sort_du_paquet_leve_SocleIllisible(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as ailleurs:
            vrai = Path(ailleurs) / "socle.json"
            vrai.write_text(json.dumps(valide()), encoding="utf-8")
            (Path(tmp) / "data").mkdir()
            try:
                os.symlink(vrai, Path(tmp) / "data" / "socle.json")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"SAUT ANNONCE : lien symbolique impossible ici ({exc})")
            with self.assertRaises(socle.SocleIllisible) as ctx:
                socle._lire(socle.Workspace(tmp))
            self.assertIn("socle.json", str(ctx.exception))
            self.assertIsInstance(ctx.exception.__cause__, socle.HorsRacine)

    def test_T7d_une_RecursionError_du_decodeur_devient_SocleIllisible(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data").mkdir()
            (Path(tmp) / "data" / "socle.json").write_text(json.dumps(valide()), encoding="utf-8")
            with mock.patch.object(socle.json, "loads", side_effect=RecursionError("profondeur")):
                with self.assertRaises(socle.SocleIllisible) as ctx:
                    socle._lire(socle.Workspace(tmp))
            self.assertIn("socle.json", str(ctx.exception))


def imports_de_niveau_module(source: str) -> set[str]:
    """Les modules importes HORS du corps d'une fonction. `from cadre import x` -> `cadre.x`."""
    vus: set[str] = set()

    def descendre(noeud: ast.AST) -> None:
        for fils in ast.iter_child_nodes(noeud):
            if isinstance(fils, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(fils, ast.Import):
                vus.update(a.name for a in fils.names)
            elif isinstance(fils, ast.ImportFrom):
                base = fils.module or ""
                vus.update(f"{base}.{a.name}" if base == "cadre" else base for a in fils.names)
            descendre(fils)

    descendre(ast.parse(source))
    return vus


class ImportsTests(unittest.TestCase):
    PERMIS = {"__future__", "json", "re", "dataclasses", "cadre.paths", "cadre.workspace"}

    def test_T6_aucun_import_de_niveau_module_hors_de_la_liste(self):
        vus = imports_de_niveau_module((PKG / "socle.py").read_text(encoding="utf-8"))
        self.assertEqual(sorted(vus - self.PERMIS), [],
                         "import de niveau module hors liste : un import de `cadre.config` va DANS le corps "
                         "de la fonction qui en a besoin (T-00000901), sinon `charger()` cesse de tenir "
                         "dans le paquet minimal de la partie B")

    def test_T6b_le_detecteur_voit_un_import_de_module_et_tolere_celui_d_une_fonction(self):
        src = (PKG / "socle.py").read_text(encoding="utf-8")
        self.assertIn("cadre.config", imports_de_niveau_module(src + "\nfrom cadre import config\n"))
        self.assertIn("cadre.config", imports_de_niveau_module(src + "\nimport cadre.config\n"))
        self.assertNotIn("cadre.config", imports_de_niveau_module(
            src + "\ndef f():\n    from cadre import config\n"))

    def test_T6c_charger_n_a_aucun_parametre(self):
        self.assertNotEqual(list(inspect.signature(lambda racine=None: None).parameters), [])  # etalonnage
        self.assertEqual(list(inspect.signature(socle.charger).parameters), [],
                         "charger() ne prend AUCUN parametre : une racine, un chemin ou une couche passes "
                         "en argument rouvriraient une lecture hors de pkg_root()")

    def test_T6d_charger_et_lire_n_ont_aucune_autre_source(self):
        # T3/T5 ne voient que les trois leurres NOMMES ; ici, une source non nommee (une variable
        # d'environnement, un autre chemin) ajoute une instruction a `charger()` ou un nom a `_lire`.
        arbre = ast.parse((PKG / "socle.py").read_text(encoding="utf-8"))
        fn = {n.name: n for n in arbre.body if isinstance(n, ast.FunctionDef)}
        corps = [n for n in fn["charger"].body
                 if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        self.assertEqual([ast.unparse(n) for n in corps], ["return _lire(Workspace(pkg_root()))"])
        permis = {"atelier", "Workspace", "Socle", "str", "CHEMIN", "OSError", "UnicodeDecodeError", "HorsRacine",
                  "exc", "_refus", "source", "brut", "json", "charge", "_valider", "RecursionError", "_sans_doublon"}
        self.assertEqual(sorted({n.id for n in ast.walk(fn["_lire"]) if isinstance(n, ast.Name)} - permis), [])


# --------------------------------------------------------------------------- B
# Le paquet MINIMAL que `charger()` ferme sur lui-meme, copie fichier par fichier :
# un banc de `.agents/evals` qui parcourt l'arbre doit etre recense par le filet de
# parcours (test_repo_walk_census), hors de ce ticket. Cinq noms, aucun parcours.
FERMETURE = ("__init__.py", "paths.py", "workspace.py", "socle.py", "data/socle.json")
# La meme PLUS la couche de configuration : six noms, aucun parcours (T3c, T5c).
FERMETURE_CONFIG = FERMETURE + ("config.py",)
# Les modules `cadre*` qu'un `charger()` honnete charge. Ce controle ne vit QUE la ou
# `cadre.config` est importable (FERMETURE_CONFIG) : dans FERMETURE, un import hors de
# la fermeture echoue (rc != 0) avant toute sortie, le controle y serait mort.
MODULES_PERMIS = {"cadre", "cadre.paths", "cadre.workspace", "cadre.socle"}
SNIPPET = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from cadre import socle\n"
    "s = socle.charger()\n"
    "print(json.dumps({'file': socle.__file__, 'ids': list(s.ids()),\n"
    "  'mods': sorted(n for n in sys.modules if n == 'cadre' or n.startswith('cadre.'))}))\n"
)
# T3c : la configuration d'abord (etalonnage : ses deux couches RENDENT un socle leurre), puis le socle.
SNIPPET_CONFIG = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from cadre import config\n"
    "from cadre import socle\n"
    "c = config.charger()\n"
    "print(json.dumps({'file': socle.__file__, 'ids': list(socle.charger().ids()),\n"
    "  'effective': c.effective.get('socle'), 'utilisateur': c.par_couche['utilisateur'].get('socle')}))\n"
)
# Le corps de `charger()` qu'une lecture par la configuration lui donnerait (T5c).
ANCRE_RETOUR = "    return _lire(Workspace(pkg_root()))"
CORPS_PAR_LA_CONFIG = (
    "    s = _lire(Workspace(pkg_root()))\n"
    "    try:\n"
    "        from cadre import config\n"
    "        sur = config.charger().effective.get(\"socle\")\n"
    "    except ImportError:\n"
    "        sur = None\n"
    "    return _valider(sur, \"config\") if isinstance(sur, dict) else s"
)


def faux_socle(ident: str) -> str:
    """Une chaine VALIDE mais differente : lue par erreur, elle rend d'autres ids."""
    return json.dumps({"version_format": 1, "chaine": [{"id": ident, "nature": "humain"}],
                       "voie_directe_depuis": ident})


class Atelier:
    """Une copie minimale du paquet + un adoptant leurre, dans un repertoire jetable."""

    def __init__(self, tmp: Path, fermeture: tuple[str, ...] = FERMETURE) -> None:
        self.copie = tmp / "installe"
        for rel in fermeture:
            cible = self.copie / "cadre" / rel
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PKG / rel, cible)
        self.dehors = tmp / "dehors"        # le cwd du run
        self.adoptant = tmp / "adoptant"    # $CADRE_PROJECT_ROOT
        self.conf = tmp / "conf"            # $CADRE_CONFIG_HOME
        # Un leurre VALIDE a chaque endroit qu'une lecture fautive viserait par sa racine ;
        # ceux que personne ne vise portent un JSON CASSE : les lire n'est jamais silencieux.
        for racine, ident in ((self.dehors, "leurre-cwd"), (self.adoptant, "leurre-projet"),
                              (self.conf, "leurre-config")):
            (racine / "data").mkdir(parents=True)
            (racine / "data" / "socle.json").write_text(faux_socle(ident), encoding="utf-8")
            (racine / "socle.json").write_text("{", encoding="utf-8")
        (self.adoptant / ".agents").mkdir()
        (self.adoptant / ".agents" / "socle.json").write_text("{", encoding="utf-8")
        # Une cle `socle` VALIDE dans les deux couches que `cadre.config` lit (projet, utilisateur) :
        # un `charger()` qui consulterait la configuration rendrait LEURS ids (T3c, T5c).
        (self.adoptant / ".agents" / "cadre.json").write_text(
            json.dumps({"socle": json.loads(faux_socle("leurre-config-projet"))}), encoding="utf-8")
        (self.conf / "cadre.json").write_text(
            json.dumps({"socle": json.loads(faux_socle("leurre-config-utilisateur"))}), encoding="utf-8")

    def lancer(self, snippet: str = SNIPPET) -> subprocess.CompletedProcess:
        # Environnement minimal (Windows exige SYSTEMROOT pour demarrer Python) + les deux leurres.
        sobre = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TMPDIR", "TEMP", "TMP", "HOME", "USERPROFILE")
        env = {k: v for k, v in os.environ.items() if k in sobre}
        env |= {"CADRE_PROJECT_ROOT": str(self.adoptant), "CADRE_CONFIG_HOME": str(self.conf)}
        # `-X utf8` : `-I` ignore PYTHONUTF8, et sous Windows le stderr de l'enfant serait en cp1252.
        return subprocess.run([sys.executable, "-X", "utf8", "-I", "-S", "-c", snippet, str(self.copie)],
                              cwd=str(self.dehors), env=env, capture_output=True, encoding="utf-8",
                              errors="backslashreplace", timeout=120)

    def sortie(self, snippet: str = SNIPPET) -> dict:
        p = self.lancer(snippet)
        if p.returncode != 0:
            raise AssertionError(p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def muter(self, avant: str, apres: str, en_tete: str = "") -> None:
        f = self.copie / "cadre" / "socle.py"
        texte = f.read_text(encoding="utf-8")
        assert texte.count(avant) == 1, f"ancre du mutant absente ou multiple : {avant!r}"
        texte = texte.replace(avant, apres)
        if en_tete:
            assert texte.count("import json\n") == 1
            texte = texte.replace("import json\n", "import json\n" + en_tete, 1)
        f.write_text(texte, encoding="utf-8")


def fautes(sortie: dict, atelier: Atelier) -> list[str]:
    """Le predicat de T3, PUR : vide si le run lit la chaine du paquet copie et d'elle seule."""
    out = []
    if not Path(sortie["file"]).resolve().is_relative_to(atelier.copie.resolve()):
        out.append("le module charge n'est pas la copie")
    if tuple(sortie["ids"]) != IDS:
        out.append(f"ids differents de la chaine attendue : {sortie['ids']}")
    return out


FAUTE_MODULES = "modules cadre charges en trop"


def fautes_modules(sortie: dict) -> list[str]:
    """PUR. Les modules `cadre*` charges hors de MODULES_PERMIS. Vivant dans FERMETURE_CONFIG seule."""
    trop = sorted(set(sortie["mods"]) - MODULES_PERMIS)
    return [f"{FAUTE_MODULES} : {trop}"] if trop else []


class PaquetSeulTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.at = Atelier(Path(self._tmp.name).resolve())

    def test_T3_le_paquet_copie_seul_lit_sa_chaine_malgre_les_leurres(self):
        self.assertEqual(fautes(self.at.sortie(), self.at), [])

    def test_T4_sans_son_fichier_le_run_echoue_et_ne_se_replie_sur_aucun_leurre(self):
        (self.at.copie / "cadre" / "data" / "socle.json").unlink()
        p = self.at.lancer()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("SocleIllisible", p.stderr)
        self.assertIn("socle.json", p.stderr)
        self.assertNotIn("leurre", p.stdout)

    def test_T4b_un_fichier_casse_dans_le_paquet_echoue_aussi(self):
        for nom, octets in (("JSON casse", b"{"), ("binaire", b"\xff\xfe")):
            with self.subTest(cas=nom):
                (self.at.copie / "cadre" / "data" / "socle.json").write_bytes(octets)
                p = self.at.lancer()
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("SocleIllisible", p.stderr)

    def test_T5_chaque_lecture_depuis_ailleurs_est_visible_par_le_predicat_de_T3(self):
        self.assertEqual(fautes(self.at.sortie(), self.at), [])  # etalonnage : le vrai passe
        mutants = {
            "cwd": ("Workspace(pkg_root())", "Workspace(Path.cwd())", "from pathlib import Path\n",
                    "leurre-cwd"),
            "CADRE_PROJECT_ROOT": ("Workspace(pkg_root())", "Workspace(os.environ['CADRE_PROJECT_ROOT'])",
                                   "import os\n", "leurre-projet"),
            "CADRE_CONFIG_HOME": ("Workspace(pkg_root())", "Workspace(os.environ['CADRE_CONFIG_HOME'])",
                                  "import os\n", "leurre-config"),
        }
        for nom, (avant, apres, en_tete, attendu) in mutants.items():
            with self.subTest(mutant=nom), tempfile.TemporaryDirectory() as tmp:
                at = Atelier(Path(tmp).resolve())
                at.muter(avant, apres, en_tete)
                sortie = at.sortie()
                self.assertEqual(sortie["ids"], [attendu], "le leurre n'est pas atteint : le vert de T3 serait vide")
                self.assertNotEqual(fautes(sortie, at), [], "T3 ne declare pas fautive la lecture depuis ailleurs")


class PaquetAvecConfigTests(unittest.TestCase):
    """FERMETURE_CONFIG : `cadre.config` est IMPORTABLE et ses couches projet et utilisateur portent
    une cle `socle` VALIDE. Ici seulement, une lecture par la configuration (gardee derriere un
    `except ImportError`, donc muette dans FERMETURE) et un import de trop deviennent visibles."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.at = Atelier(Path(self._tmp.name).resolve(), FERMETURE_CONFIG)

    def test_T3c_la_configuration_importable_ne_redefinit_pas_la_chaine(self):
        s = self.at.sortie(SNIPPET_CONFIG)
        # etalonnage : `cadre.config` REND les leurres (la couche projet l'emporte, listes remplacees)
        self.assertEqual(s["effective"], json.loads(faux_socle("leurre-config-projet")),
                         "la couche projet ne rend pas son leurre : le vert de T3c serait vide")
        self.assertEqual(s["utilisateur"], json.loads(faux_socle("leurre-config-utilisateur")),
                         "la couche utilisateur ne rend pas son leurre : le vert de T3c serait vide")
        self.assertEqual(fautes(s, self.at), [])
        seul = self.at.sortie()  # le socle SEUL : config.py est present, il ne doit pas etre charge
        self.assertEqual(fautes(seul, self.at) + fautes_modules(seul), [])

    def test_T5c_une_lecture_par_la_config_ou_un_import_de_trop_sont_vus(self):
        mutants = {
            "charger lit la couche de config": (ANCRE_RETOUR, CORPS_PAR_LA_CONFIG, ["leurre-config-projet"]),
            "import de cadre.config au niveau module": ("import json\n", "import json\nfrom cadre import config\n",
                                                        list(IDS)),
        }
        for nom, (avant, apres, ids) in mutants.items():
            with self.subTest(mutant=nom), tempfile.TemporaryDirectory() as tmp:
                at = Atelier(Path(tmp).resolve(), FERMETURE_CONFIG)
                at.muter(avant, apres)
                sortie = at.sortie()
                self.assertEqual(sortie["ids"], ids)
                self.assertTrue(any(f.startswith(FAUTE_MODULES) for f in fautes_modules(sortie)),
                                "le controle des modules ne voit pas `cadre.config` charge par le socle")


# --------------------------------------------------------------------------- C
# Kit seul : le banc lit AGENTS.md et .claude/agents/, qui disent ce que la chaine DOIT etre.
JETONS = {
    "language-detector": "`language-detector`", "planner": "`planner`", "plan-critic": "`plan-critic`",
    "gate-humain": "(human approval)", "dev": "`dev-*`", "exec-critic": "`exec-critic`",
    "securite": "`security-code-review`", "securite-dependances": "`security-orchestrator`",
    "build-index": "build_index.py --if-stale", "documenter": "`documenter`", "indexer": "`indexer`",
    "revue-cloture": "`critic-opus`", "porte": "`verify.sh`", "done": "`tasks.py … done`",
}


_SOCLE_JSON = (PKG / "data" / "socle.json").relative_to(ROOT).as_posix()
DERIVE = (f"la ligne `Pipeline mandatory` d'AGENTS.md et {_SOCLE_JSON} ne disent plus la meme "
          f"chaine : aligner {_SOCLE_JSON} ET la constante ATTENDU de ce banc, ou JETONS si seule "
          "l'ecriture d'un maillon a change, dans la meme fusion")


def positions(ligne: str, jetons: dict[str, str]) -> dict[str, list[int]]:
    out = {}
    for ident, jeton in jetons.items():
        pos, depart = [], 0
        while (i := ligne.find(jeton, depart)) >= 0:
            pos.append(i)
            depart = i + 1
        out[ident] = pos
    return out


def ordre_fautif(ligne: str, ids: tuple[str, ...], jetons: dict[str, str]) -> list[str]:
    """PUR. Vide si chaque jeton figure UNE fois et si leurs positions suivent `ids`."""
    pos = positions(ligne, jetons)
    out = [f"{i} : {len(p)} occurrence(s)" for i, p in pos.items() if len(p) != 1]
    if out:
        return out
    suivis = [i for i in ids if i in jetons]
    return [f"{a} doit preceder {b}" for a, b in zip(suivis, suivis[1:]) if pos[a][0] >= pos[b][0]]


@unittest.skipUnless(EST_LE_KIT, "SAUT ANNONCE : hors du kit (pas de .agents/IS_THE_KIT), "
                                 "AGENTS.md et .claude/agents ne sont pas ceux que ce banc mesure")
class AlignementSurLeKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        lignes_ = (ROOT / "AGENTS.md").read_text(encoding="utf-8").split("\n")
        cls.pipeline = [l for l in lignes_ if "Pipeline mandatory" in l]
        cls.ui = [l for l in lignes_ if "On a UI task" in l]
        cls.iac = [l for l in lignes_ if "On an IaC task" in l]

    def test_T8_l_ordre_de_la_doctrine_est_celui_de_socle_json(self):
        self.assertEqual(len(self.pipeline), 1, "la ligne `Pipeline mandatory` doit etre unique")
        ids = socle.charger().ids()
        self.assertEqual(set(JETONS), set(ids) - {"design-review"},
                         f"{DERIVE} : un noeud n'a pas de jeton, ou l'inverse")
        self.assertEqual(ordre_fautif(self.pipeline[0], ids, JETONS), [], DERIVE)

    def test_T8b_l_etalonnage_refuse_une_permutation_et_un_jeton_double(self):
        ids = IDS  # la constante du banc : le predicat s'etalonne sans lire socle.json
        p = self.pipeline[0]
        a, b = JETONS["planner"], JETONS["plan-critic"]
        permutee = p.replace(a, "\0").replace(b, a).replace("\0", b)
        self.assertNotEqual(ordre_fautif(permutee, ids, JETONS), [])
        self.assertNotEqual(ordre_fautif(p + " " + a, ids, JETONS), [])
        self.assertNotEqual(ordre_fautif(p, tuple(reversed(ids)), JETONS), [])

    def test_T8c_design_review_suit_frontend_fidelity_dans_la_doctrine(self):
        # Ancre : la ligne « On a UI task » (AGENTS.md, apres `Pipeline mandatory`). Sa fin, « before
        # the human gate », n'est PAS epinglee : c'est l'incoherence signalee (decision/T-00000899/01).
        self.assertEqual(len(self.ui), 1, "la ligne `On a UI task` d'AGENTS.md doit etre unique")
        l = self.ui[0]
        ff, dr = l.find("`frontend-fidelity`"), l.find("`design-review`")
        self.assertGreaterEqual(ff, 0, "`frontend-fidelity` absent de la ligne `On a UI task`")
        self.assertGreaterEqual(dr, 0, "`design-review` absent de la ligne `On a UI task`")
        self.assertLess(ff, dr)

    def test_T8d_terraform_deployer_est_le_slot_dev_de_la_ligne_IaC(self):
        # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-18, decision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG) :
        # pendant de T8c pour la tache IaC. Ancre : la ligne « On an IaC task » d'AGENTS.md (posee a
        # l'integration, apres « On a UI task »). L'agent qu'elle nomme est celui du noeud `dev` de socle.json.
        self.assertEqual(len(self.iac), 1, "la ligne `On an IaC task` d'AGENTS.md doit etre unique")
        self.assertIn("`terraform-deployer`", self.iac[0], "`terraform-deployer` absent de la ligne `On an IaC task`")
        dev = [n for n in socle.charger().chaine if n.id == "dev"]
        self.assertEqual(len(dev), 1, "socle.json : le noeud `dev` doit etre unique")
        self.assertIn("terraform-deployer", dev[0].agents,
                      "socle.json : `terraform-deployer`, slot dev IaC d'AGENTS.md, absent du noeud `dev`")

    def test_T9_chaque_nom_d_agent_a_sa_def(self):
        manquants = sorted({a for n in socle.charger().chaine for a in n.agents
                            if not (ROOT / ".claude" / "agents" / f"{a}.md").is_file()})
        self.assertEqual(manquants, [], "nom d'agent de socle.json sans def dans .claude/agents/")


if __name__ == "__main__":
    unittest.main()
