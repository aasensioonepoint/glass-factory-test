#!/usr/bin/env python3
"""LES DEUX PREMIERES SURFACES QUE `cadre init` GENERE — `pytest.ini`, `.gitignore`.

CE QUE CE BANC MESURE, ET CE QU'IL NE MESURE PAS. Il mesure un RENDU et sa
JOIGNABILITE : le texte produit, le fait qu'il soit lisible par l'outil auquel il
est destine, et le fait que les gabarits soient atteignables aussi bien dans
l'arbre source que dans la wheel. Il ne mesure AUCUNE propriete de la porte de
verification d'un projet adoptant, et deux de ses docstrings le disent en toutes
lettres, parce que c'est exactement la lecture qu'un lecteur presse en ferait.

TROIS CHOSES POUR CHAQUE TEMOIN, jamais l'une sans les deux autres : une
population NON VIDE, venant de la SOURCE qu'il pretend lire, et UTILISABLE. La
troisieme est ce qui separe ce banc d'une comparaison de chaines — un
`pytest.ini` se donne a `configparser` ET a pytest, un `.gitignore` se donne a
`git check-ignore`. Un rendu peut etre complet au caractere pres et refuse par
l'outil ; seule l'execution repond.

LA PREUVE PAR L'ARBRE SOURCE EST INSUFFISANTE SEULE, et c'est la raison d'etre du
dernier temoin. `pkg_root()` rend le repertoire du paquet ; dans ce depot c'est
`src/cadre/`, ou tout fichier est evidemment present. Une ressource ABSENTE DE LA
WHEEL ne se manifeste qu'a l'installation, chez quelqu'un d'autre, et le banc qui
lit l'arbre source est vert ce jour-la comme tous les autres.
"""

from __future__ import annotations

import configparser
import contextlib
import hashlib
import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# `cadre` la ou la regle de `vendor_paths` le designe (vendor d'abord, `src` sinon),
# charge par chemin : aucune entree neuve en tete de `sys.path` (temoin G plus bas).
_SPEC_VP = importlib.util.spec_from_file_location(
    "_init_surfaces_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
VENDOR = importlib.util.module_from_spec(_SPEC_VP)
sys.modules[_SPEC_VP.name] = VENDOR
_SPEC_VP.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")

from cadre import init_surfaces as surf  # noqa: E402
from cadre.init_surfaces import (  # noqa: E402
    STORES,
    rendre_gitignore,
    rendre_pytest_ini,
    repertoires_de_test,
)
from cadre.paths import pkg_root  # noqa: E402

GIT = shutil.which("git")
UV = shutil.which("uv")

#: Bornes de temps des sous-processus, en secondes.
#:
#: SANS ELLES, LA PORTE PEUT PENDRE — sans borne, et pas seulement longtemps.
#: `uv build` SORT SUR LE RESEAU pour resoudre `build-system.requires`, et la
#: specification de ce chantier nomme explicitement les « postes clients
#: verrouilles ou derriere un proxy sortant » : un proxy qui accepte la connexion
#: puis ne repond jamais laisse `subprocess.run` attendre indefiniment. Une porte
#: de verification sans borne de temps n'echoue pas, elle se fige — et un humain
#: finit par la tuer, ce qui ne produit AUCUN verdict.
#:
#: Les deux valeurs different parce que les deux travaux different : un `pytest`
#: sur un projet temoin de trois bancs est affaire de secondes, la ou `uv build`
#: peut legitimement telecharger un backend sur un lien lent.
DELAI_PYTEST = 300
DELAI_BUILD = 600


def _est_en_wal(store: Path) -> bool:
    """Ce fichier SQLite est-il en WAL ? Lu dans l'EN-TETE, sans l'ouvrir.

    L'octet 18 de l'en-tete SQLite est la « file format write version » : 2 pour
    WAL, 1 pour tous les modes a journal de rollback. `PRAGMA journal_mode`
    donnerait la meme reponse, mais au prix d'une OUVERTURE — et ouvrir un store
    en WAL CREE `-wal` et `-shm` a cote (mesure du 2026-09-16, y compris en
    `mode=ro`). Le banc ecrirait alors dans l'arbre les fichiers memes dont il
    verifie l'ignorance.

    `test_l_oracle_du_mode_journal_discrimine` CALIBRE cette lecture sur les six
    modes que SQLite accepte, plutot que de demander qu'on la croie.
    """
    with store.open("rb") as fh:
        entete = fh.read(20)
    if len(entete) < 19:
        raise ValueError(f"{store} : trop court pour un en-tete SQLite")
    return entete[18] == 2


def _est_un_backend_non_resolvable(sortie: str) -> bool:
    """Cette sortie d'echec `uv build` dit-elle « backend injoignable » ?

    FONCTION DE MODULE, ET C'EST LA RAISON D'ETRE DE CETTE EXTRACTION. Le
    predicat vivait en ligne dans le temoin wheel ; un banc de non-vacuite
    l'aurait alors RE-IMPLEMENTE, et deux cotes qui partagent la meme generation
    ne prouvent rien — c'est nommement l'un des defauts « temoin decoratif » que
    ce chantier s'est engage a ne pas reproduire. Ici, le temoin wheel et
    `test_le_predicat_de_saut_discrimine` appellent LA MEME fonction : casser
    l'une des deux moities de la conjonction rougit le second banc.

    LA CONJONCTION EST LE CORRECTIF, et elle est mesuree. Tester la seule chaine
    `build-system.requires` faisait SAUTER une vraie casse d'empaquetage (une
    version epinglee inexistante), c'est-a-dire exactement le defaut qu'un saut
    annonce ne doit pas introduire. Les sorties qui l'etablissent sont
    soumises a `test_le_predicat_de_saut_discrimine`.
    """
    return ("build-system.requires" in sortie
            and ("not found in the cache" in sortie
                 or ("Failed to fetch: `https://pypi.org/simple/" in sortie
                     and "dns error" in sortie)))


def _manifeste_declare_cadre() -> bool:
    """Le `pyproject.toml` de CET arbre bâtit-il bien la distribution `cadre-kit` (paquet `cadre`) ?

    CE PREDICAT EXISTE CONTRE UN ROUGE D'ADOPTANT QUE LE LOCALISATEUR DE
    `test_adopting_gate.py` NE PEUT PAS VOIR, et la borne est ecrite dans son
    en-tete : il ne lit que les references ANCREES SUR `ROOT` vers un prefixe
    `strip:`. Or ce banc ne nomme aucun chemin strippe — il a ete passe au crible
    et rend zero site — et il resterait quand meme rouge chez un adoptant qui
    porte SON PROPRE `pyproject.toml` : `uv build` y batirait la wheel de SON
    projet, ou `cadre/data/gabarits/` n'a evidemment aucune raison d'etre.

    Le sujet du temoin wheel est « le paquet `cadre` embarque ses gabarits ».
    Ce predicat fait voyager le temoin exactement aussi loin que ce sujet, et pas
    plus : la ou le manifeste bati est un autre paquet, le temoin se SAUTE en
    l'annonçant plutot que de rougir sur une question qui n'est pas celle du
    proprietaire de l'arbre.
    """
    # adopting-tree: le manifeste ne voyage pas (strip: pyproject.toml, S-00004099) ; absent, False.
    manifeste = ROOT / "pyproject.toml"
    if not manifeste.is_file():
        return False
    import tomllib  # noqa: PLC0415
    try:
        charge = tomllib.loads(manifeste.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return False
    return charge.get("project", {}).get("name") == "cadre-kit"


CADRE_EST_LE_PAQUET_BATI = _manifeste_declare_cadre()


def _projet_temoin(base: Path) -> None:
    """Un projet cible qui porte des bancs ET des pieges d'elagage.

    Les pieges ne sont pas decoratifs : chacun est un repertoire que le monde
    reel depose et qui porte des fichiers RESSEMBLANT a des bancs — un arbre de
    dependances npm, un virtualenv, un cache de bytecode, les crochets d'un
    depot. C'est cette population-la qu'un parcours sans elagage ramasse.

    `build/lib/pkg/tests/test_a.py` EST LE PIEGE LE PLUS DUR, et il porte le
    MEME BASENAME que `tests/test_a.py` DELIBEREMENT. C'est l'artefact que tout
    projet ayant fait `pip install .` porte, et la collision de basename est ce
    qui transforme un elagage rate en porte CASSEE plutot qu'en porte bruyante :
    MESURE le 2026-09-16, un `testpaths` nommant les deux repertoires rend
    `rc=2`, « import file mismatch », « Interrupted: 1 error during collection »
    — ZERO banc joue. `test_le_piege_build_casserait_reellement_la_collecte`
    rejoue cette mesure au lieu de la citer.
    """
    for rel in ("tests", "src/pkg/tests", "node_modules/dep/tests",
                ".venv/lib/site", "src/pkg/__pycache__", ".git/hooks", "docs",
                "build/lib/pkg/tests"):
        (base / rel).mkdir(parents=True, exist_ok=True)
    for rel in ("tests/test_a.py", "src/pkg/tests/test_b.py",
                "src/pkg/thing_test.py", "node_modules/dep/tests/test_dep.py",
                ".venv/lib/site/test_vendor.py", "src/pkg/__pycache__/test_a.py",
                ".git/hooks/test_hook.py", "docs/notes.md",
                "build/lib/pkg/tests/test_a.py"):
        (base / rel).write_text("def test_pose():\n    assert True\n", encoding="utf-8")


def _marche_sans_elagage(racine: Path) -> set[str]:
    """Le CONTRE-FACTUEL, recalcule ici plutot qu'epingle en dur.

    Il repond a « qu'aurait ramasse un parcours naif sur CET arbre », donc le
    temoin d'elagage compare deux mesures faites le meme jour sur le meme arbre
    au lieu d'opposer une mesure a un nombre ecrit de memoire.
    """
    trouves = set()
    for base, _sous, fichiers in os.walk(racine):
        if any(f.endswith("_test.py") or (f.startswith("test_") and f.endswith(".py"))
               for f in fichiers):
            trouves.add(Path(base).relative_to(racine).as_posix())
    return trouves


class DecouverteTests(unittest.TestCase):
    """La decouverte des repertoires de bancs du projet CIBLE."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadre-init-")
        self.base = Path(self._tmp.name).resolve() / "projet"
        self.base.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def test_l_elagage_mord_et_le_contre_factuel_le_chiffre(self):
        """POPULATION NON VIDE, SOURCE, ET LE DELTA MESURE.

        Le nombre attendu n'est pas deduit : il a ete obtenu en executant la
        fonction sur cet arbre exact (3 repertoires, contre 7 sans elagage,
        mesure du 2026-09-16). L'assertion de superiorite stricte rejoue ce
        contre-factuel A CHAQUE EXECUTION, donc elle rougit aussi le jour ou
        quelqu'un retire l'elagage sans toucher au nombre.
        """
        _projet_temoin(self.base)
        vus = repertoires_de_test(self.base)

        self.assertEqual(
            ["src/pkg", "src/pkg/tests", "tests"], vus,
            "la decouverte a change. Les trois repertoires attendus sont ceux qui "
            "portent un banc HORS des repertoires elagues ; tout autre resultat "
            "est soit un elagage qui ne mord plus, soit un motif de banc qui a "
            f"bouge. Vu : {vus}",
        )
        self.assertTrue(vus, "population VIDE — le temoin serait vert par vacuite")

        naif = _marche_sans_elagage(self.base)
        self.assertGreater(
            len(naif), len(vus),
            "le parcours SANS elagage ne ramasse pas plus que celui AVEC : soit "
            "l'arbre temoin ne porte plus de piege, soit l'elagage est inerte. "
            "Dans les deux cas ce temoin ne mesure plus rien. "
            f"naif={sorted(naif)} elague={vus}",
        )
        for piege in (".git/hooks", "node_modules/dep/tests", ".venv/lib/site",
                      "src/pkg/__pycache__", "build/lib/pkg/tests"):
            self.assertIn(piege, naif, "le piege n'est pas dans le contre-factuel")
            self.assertNotIn(piege, vus, f"{piege} a traverse l'elagage")

    def test_l_elagage_couvre_au_moins_SKIP_DIRS(self):
        """LA DUPLICATION EST ASSUMEE ; LA DIVERGENCE NE L'EST PAS.

        `ELAGAGE` est une COPIE de `SKIP_DIRS` (`.agents/bin/build_index.py`), et
        le noyau ne peut pas importer sa source sans cesser d'etre installable
        seul. Ce banc-ci vit HORS de la wheel, dans l'outillage du depot : il PEUT
        importer les deux. La contrainte « stdlib seule et hors wheel » porte sur
        le NOYAU, jamais sur l'outillage qui le verifie.

        L'IMPORT EST DIRECT PARCE QU'IL A ETE MESURE SANS EFFET DE BORD : charger
        `build_index.py` par `importlib` prend 0,016 s, n'ecrit rien et ne touche
        pas l'arbre (`git status` identique avant/apres, mesure du 2026-09-16) —
        tout son travail est derriere `if __name__ == "__main__"`. Si cela
        changeait, la lecture devrait se faire par `ast` sur le source plutot que
        par import, et ce banc rougirait d'abord.

        LE SENS DE LA COMPARAISON EST DELIBERE : on exige l'INCLUSION, pas
        l'egalite. `ELAGAGE` porte legitimement dix entrees de plus (artefacts de
        build Python et caches d'outils), absentes de `SKIP_DIRS` parce que
        l'index part de `git ls-files`, ou ces repertoires sont ignores — donc
        absents PAR LE CANAL et non par la liste.
        """
        import importlib.util  # noqa: PLC0415
        chemin = ROOT / ".agents" / "bin" / "build_index.py"
        self.assertTrue(chemin.is_file(), f"source de `SKIP_DIRS` introuvable : {chemin}")
        spec = importlib.util.spec_from_file_location("_bi_skip_dirs", chemin)
        mod = importlib.util.module_from_spec(spec)
        # ENREGISTRE AVANT `exec_module`, ET CE N'EST PAS DECORATIF : c'est le
        # motif etabli du depot — `build_index.py:2545`, `dashboard.py:281`,
        # `dashboard_daemon.py:96`, `dashboard_readers.py:121` — et
        # `test_modload_registration.py` le TIENT a l'echelle du depot entier.
        # La premiere redaction de ce banc l'omettait, et la porte l'a attrapee.
        # Un module execute hors de `sys.modules` casse tout ce qui se resout par
        # le NOM du module : `dataclasses`, `pickle`, les imports relatifs.
        #
        # RETIRE ENSUITE, parce que ce banc n'est pas un importeur : laisser
        # l'entree polluerait la session pytest pour tous les bancs suivants.
        # Le `finally` couvre le cas ou `exec_module` leve — sans quoi un echec
        # d'import laisserait un module a moitie construit sous ce nom.
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(spec.name, None)

        self.assertTrue(
            getattr(mod, "SKIP_DIRS", None),
            "`SKIP_DIRS` absent ou VIDE — la comparaison serait vraie par "
            "vacuite, et ce banc certifierait une couverture qu'il n'a pas lue",
        )
        manquants = sorted(set(mod.SKIP_DIRS) - set(surf.ELAGAGE))
        self.assertEqual(
            [], manquants,
            f"`SKIP_DIRS` a grossi et `ELAGAGE` ne l'a pas suivi : {manquants}. "
            "Les deux listes vivent dans deux fichiers que rien ne relie a "
            "l'execution ; ce banc est le seul lien.",
        )
        for sortie in ("build", "dist", ".eggs"):
            self.assertIn(
                sortie, surf.ELAGAGE,
                f"{sortie}/ a quitte l'elagage. Il n'est PAS dans `SKIP_DIRS` — "
                "l'index part de `git ls-files`, ou il est ignore — donc rien "
                "d'autre que cette assertion ne le retient.",
            )

    @staticmethod
    def _scandir_refuse(noms_interdits):
        """Un `os.scandir` qui LÈVE `PermissionError` sur tout repertoire dont le
        basename est dans `noms_interdits`, et DELEGUE a l'original ailleurs.

        Reproduit un `chmod 000` SANS dependre des droits : `repertoires_de_test`
        passe par `Workspace.walk` -> `os.walk` -> `os.scandir`, donc l'erreur
        remonte a `sur_erreur` (le collecteur) exactement comme une permission
        refusee. C'est ce qui rend le refus EN BLOC exercable sur un hote ROOT —
        ou `chmod 000` ne refuse rien, et ou `verify.sh:764` lance `docker run`
        SANS `--user`, donc l'ancienne garde `geteuid()==0 -> skip` laissait
        `init_surfaces.py:244-245` (seul site de production) JAMAIS joue."""
        vrai = os.scandir
        interdits = set(noms_interdits)

        def _faux(chemin=".", *a, **k):
            if os.path.basename(os.fspath(chemin)) in interdits:
                raise PermissionError(13, "Permission denied", os.fspath(chemin))
            return vrai(chemin, *a, **k)

        return _faux

    def test_un_repertoire_illisible_est_un_refus_nomme(self):
        """UN VERT PAR OMISSION EST PIRE QU'UN ROUGE, et c'est ce qui se passait.

        MESURE AVANT CORRECTIF (2026-09-16) : `chmod 000` sur un repertoire
        portant `test_b.py` faisait rendre `['tests']` a la decouverte — aucune
        erreur, aucune trace. Le `pytest.ini` produit aurait alors porte un
        `testpaths` AMPUTE, et la porte de l'adoptant serait passee au vert sur
        un sous-ensemble de ses bancs sans que rien ne le signale.

        DEUX BRAS, et le premier NE SE DESARME PAS. BRAS 1 (toujours exerce,
        independant des droits) : DEUX repertoires illisibles injectes par
        `os.scandir` mocke, ce qui prouve la levee EN BLOC (le message compte
        « 2 repertoire(s) » et NOMME les deux) meme sur un hote root. BRAS 2
        (quand les droits mordent, `geteuid()!=0`) : un `chmod 000` REEL, jamais
        comme seule voie. `addCleanup` restaure les droits — `cleanup()` ne peut
        pas supprimer un repertoire qu'il ne peut traverser.
        """
        (self.base / "tests").mkdir()
        (self.base / "tests" / "test_a.py").write_text("", encoding="utf-8")
        for nom in ("interdit", "interdit2"):
            mure = self.base / nom
            mure.mkdir()
            (mure / "test_b.py").write_text("", encoding="utf-8")

        # BRAS 1 — injection par mock, TOUJOURS exerce, DEUX repertoires (bloc).
        with self.subTest(bras="scandir-mocke"):
            with mock.patch(
                "os.scandir",
                side_effect=self._scandir_refuse({"interdit", "interdit2"}),
            ):
                with self.assertRaises(PermissionError) as pris:
                    repertoires_de_test(self.base)
            msg = str(pris.exception)
            self.assertTrue(
                msg.startswith("2 repertoire(s) illisible(s)"),
                f"la levee n'est pas EN BLOC sur les DEUX repertoires : {msg}",
            )
            self.assertIn("interdit (PermissionError)", msg,
                          f"le premier repertoire illisible n'est pas NOMME : {msg}")
            self.assertIn("interdit2 (PermissionError)", msg,
                          f"le second repertoire illisible n'est pas NOMME : {msg}")

        # BRAS 2 — `chmod 000` REEL, seulement la ou les droits mordent.
        if not (hasattr(os, "geteuid") and os.geteuid() == 0):
            with self.subTest(bras="chmod-000-reel"):
                reel = self.base / "interdit"
                os.chmod(reel, 0o000)
                self.addCleanup(os.chmod, reel, 0o755)
                with self.assertRaises(PermissionError) as pris2:
                    repertoires_de_test(self.base)
                self.assertIn("interdit", str(pris2.exception))

    def test_racine_absente_leve_not_a_directory_error(self):
        """RACINE ABSENTE : `NotADirectoryError`, PAS `PermissionError`.

        Un chemin inexistant ne doit pas renvoyer « corrigez vos droits » —
        c'est le défaut mesuré. La garde en tête de fonction intercepte avant
        tout parcours et lève le type NOMMÉ `NotADirectoryError`."""
        with self.assertRaises(NotADirectoryError) as pris:
            repertoires_de_test(self.base / "absent")
        self.assertIn("introuvable ou non repertoire", str(pris.exception))

    def test_racine_fichier_leve_not_a_directory_error(self):
        """RACINE FICHIER : `NotADirectoryError`, PAS `PermissionError`.

        Un chemin qui existe mais est un fichier ne doit pas passer dans le
        parcours. La garde en tête de fonction intercepte et lève le type
        NOMMÉ `NotADirectoryError`."""
        (self.base / "un_fichier").write_text("x\n", encoding="utf-8")
        with self.assertRaises(NotADirectoryError) as pris:
            repertoires_de_test(self.base / "un_fichier")
        self.assertIn("introuvable ou non repertoire", str(pris.exception))

    @staticmethod
    def _scandir_mixte(noms_interdits, noms_disparus):
        """Un `os.scandir` qui LÈVE `PermissionError` sur `noms_interdits`,
        `FileNotFoundError` sur `noms_disparus`, et delegue a l'original ailleurs."""
        vrai = os.scandir

        def _faux(chemin=".", *a, **k):
            b = os.path.basename(os.fspath(chemin))
            if b in noms_interdits:
                raise PermissionError(13, "Permission denied", os.fspath(chemin))
            if b in noms_disparus:
                raise FileNotFoundError(
                    2, "No such file or directory", os.fspath(chemin)
                )
            return vrai(chemin, *a, **k)

        return _faux

    def test_parent_non_traversable_leve_permission_error(self):
        """PARENT SANS DROIT DE TRAVERSEE : `PermissionError`, JAMAIS « introuvable ».

        `Path.is_dir` rendait FAUX sur EACCES en 3.14+ mesure (3.11 a 3.13
        levaient) ; depuis T-00001232 `est_repertoire` LEVE `PermissionError`
        sur tout interpreteur, et la garde doit la laisser passer, jamais la lire
        « absente ». BRAS 1 (mock, toujours joue, hote root compris) :
        `est_repertoire` leve, aucune garde ne convertit. BRAS 2 (`chmod 000`
        reel, hors Windows et si `geteuid() != 0`) : les TROIS gardes levent
        `PermissionError`, et ce n'est pas celle du parcours (« illisible »)."""
        projet = self.base / "parent" / "projet"
        (projet / "tests").mkdir(parents=True)
        (projet / "tests" / "test_a.py").write_text("", encoding="utf-8")
        gardes = (repertoires_de_test, surf.rendre_pytest_ini, surf.rendre_gitignore)
        for garde in gardes:
            with self.subTest(bras="mock", garde=garde.__name__), \
                 mock.patch.object(surf.Workspace, "est_repertoire", side_effect=PermissionError(
                     13, "Permission denied", os.fspath(projet))):
                with self.assertRaises(PermissionError):
                    garde(projet)
        (self.base / "fichier").write_text("", encoding="utf-8")
        for garde in gardes:
            with self.subTest(garde=garde.__name__, cas="parent fichier"):
                with self.assertRaisesRegex(NotADirectoryError, "racine de projet introuvable"):
                    garde(self.base / "fichier" / "projet")
        with self.subTest(bras="chmod-000-reel"):
            if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
                self.skipTest("chmod 000 sans refus de traversee (Windows ou root) : "
                              "le bras 1 couvre")
            parent = self.base / "parent"
            os.chmod(parent, 0o000)
            # addCleanup suffit ICI : setUp a pose `self._tmp.cleanup` AVANT, et
            # doCleanups joue en LIFO — le chmod passe avant la suppression.
            self.addCleanup(os.chmod, parent, 0o755)
            for garde in gardes:
                with self.subTest(bras="chmod-000-reel", garde=garde.__name__):
                    with self.assertRaises(PermissionError) as pris:
                        garde(projet)
                    self.assertNotIn("illisible", str(pris.exception))

    def test_racine_lien_pendant_ou_vers_fichier_leve_not_a_directory_error(self):
        """T5 (T-00001232) : une racine LIEN PENDANT ou LIEN VERS UN FICHIER est
        `NotADirectoryError` pour les TROIS gardes — angle mort LIEN de
        l'exec-critic T-00000682, ferme. CARACTERISATION, verte avant le
        correctif ; son mutant est une garde `exists` au lieu
        d'`est_repertoire`, que le lien vers un fichier traverse. Saut NOMME si
        `os.symlink` echoue sur ce poste, comme W7."""
        (self.base / "un_fichier").write_text("x\n", encoding="utf-8")
        pendant = self.base / "lien_pendant"
        vers_fichier = self.base / "lien_fichier"
        try:
            os.symlink(self.base / "absent", pendant)
            os.symlink(self.base / "un_fichier", vers_fichier)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible sur ce poste : {exc}")
        for cas, racine in (("lien pendant", pendant), ("lien vers fichier", vers_fichier)):
            for garde in (repertoires_de_test, surf.rendre_pytest_ini, surf.rendre_gitignore):
                with self.subTest(cas=cas, garde=garde.__name__):
                    with self.assertRaisesRegex(NotADirectoryError,
                                                "racine de projet introuvable"):
                        garde(racine)

    def test_collecte_sans_disparu_tait_l_indice_de_relance(self):
        """COLLECTE SANS DISPARU : `OSError` dont le type n'est PAS `PermissionError`.

        Un repertoire `io` qui leve `OSError(5)` pendant le parcours (sans
        `FileNotFoundError`) confirme que l'indice « se regle en relancant » ne
        s'applique qu'a `FileNotFoundError`. La levee est `OSError`, pas
        `PermissionError`. Le message NE contient PAS `relancant`."""
        (self.base / "tests").mkdir()
        (self.base / "tests" / "test_a.py").write_text("", encoding="utf-8")
        (self.base / "interdit").mkdir()
        (self.base / "io").mkdir()

        vrai = os.scandir

        def _faux(chemin=".", *a, **k):
            b = os.path.basename(os.fspath(chemin))
            if b == "interdit":
                raise PermissionError(13, "Permission denied", os.fspath(chemin))
            if b == "io":
                raise OSError(5, "Input/output error", os.fspath(chemin))
            return vrai(chemin, *a, **k)

        with mock.patch("os.scandir", side_effect=_faux):
            with self.assertRaises(OSError) as pris:
                repertoires_de_test(self.base)
        exe = pris.exception
        self.assertFalse(
            isinstance(exe, PermissionError),
            f"la levee de collecte est {type(exe).__name__}, PAS PermissionError : {exe}",
        )
        msg = str(exe)
        self.assertNotIn("relancant", msg, f"le message ne doit pas dire 'relancant' : {msg}")

    def test_collecte_mixte_leve_os_error_non_permission(self):
        """COLLECTE MIXTE : `OSError` dont le type n'est PAS `PermissionError`.

        Quand un repertoire (ici `tox`, SANS point : `.tox` est ELAGUE et jamais
        parcouru) disparait pendant le parcours (`FileNotFoundError`) en meme
        temps qu'un repertoire illisible (`PermissionError`), la levee
        est `OSError`, pas `PermissionError`. Le message NOMME les deux types.

        CE TEMOIN ROUGIT SUR LE CODE D'AVANT : avant le correctif, tout OSError
        levait `PermissionError` avec un message « repertoire(s) illisible(s) »
        qui trompe l'adoptant sur la cause."""
        (self.base / "tests").mkdir()
        (self.base / "tests" / "test_a.py").write_text("", encoding="utf-8")
        mure = self.base / "interdit"
        mure.mkdir()
        (mure / "test_b.py").write_text("", encoding="utf-8")
        (self.base / "tox").mkdir()

        with mock.patch(
            "os.scandir",
            side_effect=self._scandir_mixte({"interdit"}, {"tox"}),
        ):
            with self.assertRaises(OSError) as pris:
                repertoires_de_test(self.base)
        exe = pris.exception
        self.assertFalse(
            isinstance(exe, PermissionError),
            f"la levee de collecte mixte est {type(exe).__name__} ; "
            f"attendu un OSError NON PermissionError : {exe}",
        )
        msg = str(exe)
        self.assertIn("AMPUTE", msg, f"le message ne cite pas AMPUTE : {msg}")
        self.assertIn("PermissionError", msg, f"le type PermissionError n'est pas NOMME : {msg}")
        self.assertIn("FileNotFoundError", msg, f"le type FileNotFoundError n'est pas NOMME : {msg}")
        self.assertIn("interdit", msg, f"le chemin interdit n'est pas NOMME : {msg}")

    def test_course_pure_leve_os_error(self):
        """COURSE PURE : seules des `FileNotFoundError` collectees -> `OSError`, pas
        `PermissionError`. Le message contient `relancant` par le contrat."""
        (self.base / "tests").mkdir()
        (self.base / "tests" / "test_a.py").write_text("", encoding="utf-8")
        (self.base / "tox").mkdir()

        with mock.patch(
            "os.scandir",
            side_effect=self._scandir_mixte(set(), {"tox"}),
        ):
            with self.assertRaises(OSError) as pris:
                repertoires_de_test(self.base)
        exe = pris.exception
        self.assertFalse(
            isinstance(exe, PermissionError),
            f"la levee est {type(exe).__name__}, PAS PermissionError : {exe}",
        )
        msg = str(exe)
        self.assertIn("FileNotFoundError", msg, f"le type FileNotFoundError n'est pas NOMME : {msg}")
        self.assertIn("relancant", msg, f"le message ne dit pas 'relancant' : {msg}")

    def test_un_projet_sans_aucun_banc_rend_une_liste_vide(self):
        (self.base / "src").mkdir()
        (self.base / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
        self.assertEqual([], repertoires_de_test(self.base))

    def test_un_banc_a_la_racine_sort_comme_un_point(self):
        """`testpaths` attend un chemin ; une chaine vide y serait une entree
        vide, donc la racine se nomme `.` et ce cas a son temoin."""
        (self.base / "test_racine.py").write_text("", encoding="utf-8")
        self.assertEqual(["."], repertoires_de_test(self.base))


class PytestIniTests(unittest.TestCase):
    """Le rendu du `pytest.ini`, lu par `configparser` PUIS par pytest."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadre-init-")
        self.base = Path(self._tmp.name).resolve() / "projet"
        self.base.mkdir()
        self.addCleanup(self._tmp.cleanup)

    @staticmethod
    def _clefs(rendu: str) -> configparser.SectionProxy:
        """UTILISABLE, moitie 1 : le rendu est un INI VALIDE, pas une chaine qui
        y ressemble. Le parseur est ce qui distingue les deux."""
        cfg = configparser.ConfigParser()
        cfg.read_string(rendu)
        return cfg["pytest"]

    def _pytest_dans(self, racine: Path, *args: str):
        """UN PYTEST IMBRIQUE EST BORNE EN TEMPS — voir `DELAI_PYTEST`.

        Le depassement n'est PAS rattrape ici : il remonte en
        `subprocess.TimeoutExpired`, donc en ERREUR de banc. C'est voulu — un
        pytest de trois bancs qui met cinq minutes est une anomalie a regarder,
        pas une condition d'environnement a annoncer. Le saut annonce est reserve
        a `uv build`, dont la lenteur a une cause externe NOMMEE (le reseau).
        """
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", *args],
                           cwd=str(racine), capture_output=True, text=True,
                           timeout=DELAI_PYTEST)
        return r.returncode, r.stdout + r.stderr

    def test_les_testpaths_generes_omettent_la_cle_sans_aucun_test(self):
        """CE TEMOIN EPINGLE UN RENDU, PAS UN CAS GERE — a lire comme tel.

        Il prouve que la cle `testpaths` est ABSENTE du fichier produit sur un
        projet sans banc, et que ce fichier reste un INI valide. Il ne prouve
        RIEN sur la porte de verification d'un tel projet, et personne ne doit le
        lire ainsi : les deux formes — cle absente et cle vide — se comportent
        IDENTIQUEMENT pour pytest, `rc=5` dans les deux cas, ce que la seconde
        moitie de ce temoin RE-MESURE plutot que de l'affirmer. L'omission est un
        choix de LISIBILITE : une cle vide se lit comme une configuration
        oubliee. Aucune des deux ne rend une porte verte.
        """
        (self.base / "src").mkdir()
        (self.base / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
        rendu = rendre_pytest_ini(self.base)

        clefs = self._clefs(rendu)
        self.assertNotIn(
            "testpaths", clefs,
            "la cle `testpaths` est PRESENTE sur un projet sans banc. Une cle "
            "vide se lit comme une configuration oubliee ; elle est omise. "
            f"Rendu :\n{rendu}",
        )
        self.assertIn("python_files", clefs,
                      "le reste de la section a disparu avec la cle — le rendu "
                      "n'est plus une configuration, c'est un trou")

        # UTILISABLE, moitie 2 : LA MESURE D'EQUIVALENCE, rejouee ici plutot que
        # citee. Ce qui suit est la raison pour laquelle la docstring refuse de
        # presenter l'omission comme un correctif.
        (self.base / "pytest.ini").write_text(rendu, encoding="utf-8")
        rc_omise, sortie_omise = self._pytest_dans(self.base)

        vide = self.base / "vide"
        vide.mkdir()
        (vide / "pytest.ini").write_text(
            rendu.replace("[pytest]\n", "[pytest]\ntestpaths =\n"), encoding="utf-8")
        rc_vide, _ = self._pytest_dans(vide)

        self.assertEqual(
            (5, 5), (rc_omise, rc_vide),
            "l'equivalence mesuree ne tient plus : cle OMISE et cle VIDE "
            "rendaient toutes deux `rc=5` (aucun banc collecte). Si ces codes "
            "divergent, l'omission a cesse d'etre un choix de lisibilite et "
            f"devient un choix de comportement, a arbitrer. omise={rc_omise} "
            f"vide={rc_vide}\n{sortie_omise}",
        )

    def test_les_testpaths_generes_listent_les_repertoires_decouverts(self):
        """SOURCE + UTILISABLE : les chemins ecrits sont ceux que la decouverte a
        rendus, et pytest collecte REELLEMENT depuis eux."""
        _projet_temoin(self.base)
        rendu = rendre_pytest_ini(self.base)
        clefs = self._clefs(rendu)

        listes = [l for l in clefs["testpaths"].splitlines() if l.strip()]
        self.assertEqual(
            repertoires_de_test(self.base), listes,
            "les chemins ecrits dans `testpaths` ne sont pas ceux que la "
            "decouverte rend — le rendu et sa source ont diverge",
        )
        self.assertTrue(listes, "`testpaths` vide — vert par vacuite")

        (self.base / "pytest.ini").write_text(rendu, encoding="utf-8")
        rc, sortie = self._pytest_dans(self.base, "--collect-only")
        self.assertEqual(0, rc, sortie)
        collectes = [l for l in sortie.splitlines() if "::" in l]
        self.assertEqual(
            3, len(collectes),
            "pytest ne collecte pas les trois bancs des repertoires decouverts. "
            "Nombre obtenu par EXECUTION le 2026-09-16 ; un ecart dit soit que "
            "`testpaths` ne porte plus, soit que les motifs `python_files` du "
            f"gabarit ont diverge de ceux de la decouverte. Vu :\n{sortie}",
        )
        for piege in ("node_modules", ".venv", "__pycache__", "build/lib"):
            self.assertNotIn(piege, sortie,
                             f"pytest a collecte depuis {piege} — l'elagage de la "
                             "decouverte n'a pas suivi jusqu'au rendu")

    def test_le_piege_build_casserait_reellement_la_collecte(self):
        """LE CONTRE-FACTUEL EXECUTE : sans l'elagage de `build/`, la porte de
        l'adoptant ne devient pas bruyante, elle devient CASSEE.

        Ce banc est ce qui empeche `build/` d'etre un piege DECORATIF. Il ne
        compare pas deux listes : il donne a pytest le `testpaths` qu'un elagage
        rate produirait, et constate que la collecte est INTERROMPUE. Sans cette
        moitie, retirer `build` de `ELAGAGE` ferait rougir le banc d'inclusion
        sans que personne ne sache ce que ça coute.

        MESURE DU 2026-09-16 : `rc=2`, « import file mismatch », « Interrupted:
        1 error during collection » — ZERO banc joue. Le mecanisme est la
        COLLISION DE BASENAME entre `tests/test_a.py` et sa copie
        `build/lib/pkg/tests/test_a.py`, que `pip install .` depose.

        ET CE N'EST PAS COUVERT PAR `norecursedirs` : le defaut de pytest elague
        bien `build/`, mais un `testpaths` EXPLICITE outrepasse cet elagage —
        c'est precisement parce que le gabarit ECRIT les chemins qu'il doit les
        elaguer lui-meme.
        """
        _projet_temoin(self.base)
        vus = repertoires_de_test(self.base)
        self.assertNotIn("build/lib/pkg/tests", vus,
                         "l'elagage laisse passer `build/` — le reste de ce banc "
                         "mesurerait deux fois la meme chose")

        naif = sorted(_marche_sans_elagage(self.base))
        self.assertIn("build/lib/pkg/tests", naif,
                      "le piege a disparu de l'arbre temoin — contre-factuel vide")

        bloc = "".join(f"    {r}\n" for r in naif)
        (self.base / "pytest.ini").write_text(
            f"[pytest]\ntestpaths =\n{bloc}python_files = test_*.py *_test.py\n",
            encoding="utf-8")
        rc, sortie = self._pytest_dans(self.base)

        self.assertEqual(
            2, rc,
            "le `testpaths` NAIF ne casse plus la collecte. Soit la collision de "
            "basename a disparu de l'arbre temoin, soit pytest a change de "
            "comportement — dans les deux cas l'elagage de `build/` n'est plus "
            f"justifie par ce que ce banc mesure. Vu :\n{sortie}",
        )
        self.assertIn("import file mismatch", sortie,
                      f"echec pour une autre raison que la collision : {sortie}")

        # ET LA MOITIE QUI COMPTE : le rendu REEL, sur le meme arbre, passe.
        (self.base / "pytest.ini").write_text(
            rendre_pytest_ini(self.base), encoding="utf-8")
        rc_reel, sortie_reelle = self._pytest_dans(self.base)
        self.assertEqual(
            0, rc_reel,
            "le `pytest.ini` genere ne collecte pas sur un projet portant un "
            f"`build/` — c'est le rouge d'adoptant que T2 devait fermer :\n{sortie_reelle}",
        )

    def test_un_nom_de_repertoire_illisible_en_INI_est_un_refus(self):
        """DEUX MECANISMES DISTINCTS, DONC DEUX TEMOINS — et ils ne se
        remplacent pas l'un l'autre.

        `testpaths` est une valeur MULTILIGNE : le saut de ligne EST le
        separateur. Un nom qui en contient un CASSE le fichier ; un nom qui
        commence par `#` ou `;` ouvre un commentaire inline et AMPUTE le fichier
        en silence. Le premier se voit, le second non — c'est le second qui
        justifie le refus.

        L'ORACLE DE CE BANC EST `configparser`, ET IL N'EST PAS D'ACCORD AVEC
        PYTEST. Il faut le savoir pour lire ce qui suit : sur le nom `#c`, les
        DEUX LECTEURS DU MEME FICHIER DIVERGENT (mesure du 2026-09-16) —
        `configparser` rend une valeur VIDE (le chemin a disparu), tandis que
        pytest rend `rc=0` et COLLECTE bel et bien `#c/test_c.py`. Ce banc mesure
        donc la VALIDITE INI du rendu, pas le comportement de pytest ; les deux
        ne coincident pas, et c'est exactement pourquoi le module REFUSE au lieu
        de parier sur le lecteur le plus permissif. Sur le saut de ligne, les
        deux sont d'accord pour echouer : `ParsingError` d'un cote, `rc=4
        unexpected line: 'b'` de l'autre.
        """
        for nom, mecanisme in (("a\nb", "saut de ligne — CASSE le fichier"),
                               ("#c", "commentaire inline — AMPUTE en silence")):
            with self.subTest(nom=nom):
                coin = self.base / "cas" / str(abs(hash(nom)))
                (coin / nom).mkdir(parents=True)
                (coin / nom / "test_x.py").write_text("", encoding="utf-8")

                self.assertIn(
                    nom, repertoires_de_test(coin),
                    "la decouverte ne rend pas ce nom, donc le rendu ne le "
                    "verrait jamais et ce temoin serait vert par vacuite",
                )
                with self.assertRaises(ValueError, msg=mecanisme) as pris:
                    rendre_pytest_ini(coin)
                # `repr(nom)` DES DEUX COTES SERAIT UNE FAUTE : le message porte
                # deja la liste des fautifs, donc les noms y sont REPRESENTES
                # (`['a\\nb']`). Re-representer le message echapperait une
                # seconde fois les antislashs et ne trouverait jamais rien.
                self.assertIn(repr(nom), str(pris.exception),
                              "le refus ne NOMME pas le repertoire fautif")

    def test_un_nom_de_repertoire_sain_passe_le_refus(self):
        """LA MOITIE QUI INTERDIT AU REFUS DE TOUT PRENDRE.

        Sans elle, un predicat qui rejette TOUT satisferait le temoin precedent.
        Les noms ci-dessous sont licites et doivent traverser — dont un ACCENTUE
        et un portant un `#` EN MILIEU de nom. Les deux valent inspection :
        `str.isprintable()` est vrai sur les lettres accentuees, et le refus ne
        porte que sur un `#` EN TETE, la ou un `#` interne ne commente rien.

        LA COMPARAISON PASSE PAR CE QUE LA DECOUVERTE REND, jamais par le
        litteral ecrit ici, et c'est une precaution MESUREE plutot que
        theorique : APFS normalise les noms accentues, donc le nom relu peut
        etre la forme decomposee (NFD) quand le litteral est composee (NFC).
        Comparer au litteral ferait rougir ce banc sur macOS pour une raison
        qui n'a rien a voir avec son sujet.
        """
        for nom in ("tests", "tests-unitaires", "tests_2", "donnees_reglees",
                    "donnees_réglées", "lot#2"):
            with self.subTest(nom=nom):
                coin = self.base / "sains" / str(abs(hash(nom)))
                (coin / nom).mkdir(parents=True)
                (coin / nom / "test_x.py").write_text("", encoding="utf-8")

                rendus = repertoires_de_test(coin)
                self.assertTrue(rendus, f"{nom!r} n'a pas ete decouvert")
                ecrits = [l.strip() for l
                          in self._clefs(rendre_pytest_ini(coin))["testpaths"].splitlines()
                          if l.strip()]
                self.assertEqual(
                    rendus, ecrits,
                    f"{nom!r} est un nom LICITE et n'a pas traverse le rendu — un "
                    "refus qui prend tout satisfait le temoin d'a cote sans rien "
                    "proteger",
                )


class GitignoreTests(unittest.TestCase):
    """Le rendu du `.gitignore`, juge par `git check-ignore` et non par une
    comparaison de chaines."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadre-init-")
        self.base = Path(self._tmp.name).resolve() / "projet"
        self.base.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def _depot_avec_le_rendu(self) -> Path:
        (self.base / ".gitignore").write_text(rendre_gitignore(self.base), encoding="utf-8")
        subprocess.run([GIT, "init", "-q"], cwd=str(self.base), check=True,
                       capture_output=True, text=True)
        return self.base

    def _ignore(self, racine: Path, rel: str) -> bool:
        """`git check-ignore` : rc 0 = ignore, rc 1 = pas ignore.

        `core.excludesFile` est NEUTRALISE : sans cela le `.gitignore` global du
        poste participe au verdict, et le banc mesurerait la machine du
        developpeur autant que le rendu.
        """
        r = subprocess.run(
            [GIT, "-c", "core.excludesFile=/dev/null", "check-ignore", "-q", "--", rel],
            cwd=str(racine), capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 1), f"check-ignore a echoue : {r.stderr}")
        return r.returncode == 0

    @unittest.skipIf(GIT is None, "git absent du PATH — le verdict d'ignorance ne peut pas etre mesure")
    def test_le_bucket_jetable_est_ignore_et_les_stores_suivis_ne_le_sont_pas(self):
        """LES DEUX MOITIES, parce qu'une seule est un piege. Un `.gitignore` qui
        ignore tout satisfait la premiere ; c'est la seconde qui interdit de
        desuivre un store en silence.

        T-00000668 : la seconde moitie a CHANGE DE FORME, pas de sujet. `index.db`
        — le dernier store suivi — vit hors depot ; `STORES` n'a donc PLUS AUCUNE
        entree `suivi=True`, et c'est ce que ce banc ASSERTE (l'inverse de sa
        garde de non-vacuite d'avant). Un store qui redeviendrait suivi sans
        decision rougit ici ; le rendu ne nomme aucun store `# SUIVI`."""
        racine = self._depot_avec_le_rendu()

        jetables = [s.chemin for s in STORES if not s.suivi]
        suivis = [s.chemin for s in STORES if s.suivi]
        self.assertTrue(jetables, "aucun store jetable dans l'inventaire")
        self.assertEqual([], suivis,
                         "un store SUIVI est reapparu dans `STORES` — T-00000668 a "
                         "sorti le dernier (index.db) du depot")
        self.assertNotIn("# SUIVI", rendre_gitignore(self.base),
                         "le rendu nomme un store suivi alors qu'il n'y en a aucun")

        for chemin in jetables:
            with self.subTest(jetable=chemin):
                self.assertTrue(self._ignore(racine, chemin),
                                f"{chemin} vit sous le bucket jetable et devrait etre ignore")
                self.assertTrue(self._ignore(racine, chemin + "-wal"),
                                "le lateral d'un store jetable est couvert par la "
                                "regle de REPERTOIRE, il n'a pas a etre nomme")
        for chemin in suivis:
            with self.subTest(suivi=chemin):
                self.assertFalse(
                    self._ignore(racine, chemin),
                    f"{chemin} est SUIVI : l'ignorer le desuivrait chez tout "
                    "adoptant, et il ne se redrive d'aucun autre fichier",
                )

    @unittest.skipIf(GIT is None, "git absent du PATH — le verdict d'ignorance ne peut pas etre mesure")
    def test_les_lateraux_sont_litteraux_et_un_glob_serait_trop_large(self):
        """LE TEMOIN QUI SEPARE UNE LIGNE LITTERALE D'UN GLOB. Le store qui n'ouvre
        PAS en WAL doit voir ses lateraux RESTER visibles ; un `*.db-wal` les
        masquerait sans decision ni trace — precisement ce que la regle interdit.

        BRAS `en_wal` RETIRE le 2026-09-21 (T-00000677, decision gamma) : son SEUL
        membre etait `.agents/state/v3_event_store.db`, desindexe par ce lot. Il ne
        reste AUCUN store SUIVI en WAL, donc `rendre_gitignore` n'emet plus de ligne
        `-wal`/`-shm` chez l'adoptant — a raison. Fabriquer un faux store suivi en
        WAL (alpha) a ete ecarte.

        BRAS `hors_wal` RETIRE PAR T-00000668 : beta, ecartee par T-677, est FAITE
        par T-668 — plus aucun store suivi, donc plus de contre-exemple ; le
        controle du glob porte sur la regle jetable. Il reste le controle
        TEXTUEL ci-dessous, qui rougit sur toute ligne de regle flottante (un
        `*.db-wal` ajoute au gabarit) ou non ancree.
        """
        self._depot_avec_le_rendu()

        # LE CONTROLE TEXTUEL PORTE SUR LES LIGNES DE REGLE, JAMAIS SUR LA PROSE,
        # et ce n'est pas une precaution theorique : la premiere redaction
        # cherchait `*.db-wal` dans le rendu ENTIER et rougissait sur le
        # commentaire du gabarit qui EXPLIQUE pourquoi ce glob est refuse
        # (mesure du 2026-09-16). C'est le piege que ce depot a deja paye deux
        # fois — un detecteur qui refuse qu'on documente ce qu'il interdit se
        # fait desarmer en supprimant la documentation.
        regles = [l for l in rendre_gitignore(self.base).splitlines()
                  if l.strip() and not l.lstrip().startswith("#")]
        self.assertTrue(regles, "aucune ligne de regle dans le rendu — vert par vacuite")
        globs = [l for l in regles if "*" in l]
        self.assertEqual(
            [], globs,
            "une ligne de REGLE porte un motif flottant. Les lateraux se nomment "
            f"litteralement et ancres. Lignes fautives : {globs}",
        )
        self.assertTrue(
            all(l.startswith("/") for l in regles),
            f"une ligne de regle n'est pas ANCREE a la racine : {regles}",
        )

    def test_une_racine_inexistante_est_un_refus_nomme(self):
        with self.assertRaises(NotADirectoryError):
            rendre_gitignore(self.base / "inexistant")

    def test_l_oracle_du_mode_journal_discrimine(self):
        """LA CALIBRATION DE L'ORACLE, AVANT DE S'EN SERVIR.

        Le banc suivant lit le mode journal dans l'EN-TETE SQLite (octet 18)
        plutot qu'en ouvrant la base. Ce banc-ci prouve que cette lecture
        DISCRIMINE, sur des bases que lui-meme fabrique dans les six modes que
        SQLite accepte — sans quoi « l'octet 18 dit le mode » serait une
        affirmation de plus.

        MESURE DU 2026-09-16, rejouee ici a chaque execution : `wal` -> 2, et
        `delete`, `truncate`, `persist`, `memory`, `off` -> 1.

        LA BORNE EST ECRITE PARCE QU'ELLE EST REELLE : l'en-tete separe WAL de
        NON-WAL, et rien de plus fin — il ne distingue pas `delete` de
        `truncate`. C'est exactement la granularite de `Store.wal`, qui est un
        BOOLEEN ; un oracle plus fin mesurerait ce que la table ne dit pas.
        """
        import sqlite3  # noqa: PLC0415
        # LES SIX ORDRES SONT DES LITTERAUX CLOS, ET C'EST STRUCTUREL, pas
        # cosmetique : SQLite n'accepte AUCUNE liaison de parametre dans un
        # `PRAGMA` (`PRAGMA journal_mode=?` est une erreur de syntaxe), donc la
        # seule forme sans interpolation est d'ecrire les six ordres en toutes
        # lettres. Le scanner SAST du depot refuse la forme interpolee, et il a
        # raison de refuser la FORME meme quand la valeur vient d'ici.
        calibration = (
            ("PRAGMA journal_mode=wal", "wal", True),
            ("PRAGMA journal_mode=delete", "delete", False),
            ("PRAGMA journal_mode=truncate", "truncate", False),
            ("PRAGMA journal_mode=persist", "persist", False),
            ("PRAGMA journal_mode=memory", "memory", False),
            ("PRAGMA journal_mode=off", "off", False),
        )
        with tempfile.TemporaryDirectory(prefix="cadre-calib-") as d:
            for ordre, mode, est_wal in calibration:
                with self.subTest(mode=mode):
                    f = Path(d) / (mode + ".db")
                    c = sqlite3.connect(f)
                    c.execute(ordre)
                    c.execute("CREATE TABLE t(x)")
                    c.commit()
                    c.close()
                    self.assertEqual(
                        est_wal, _est_en_wal(f),
                        f"l'oracle d'en-tete ne reconnait pas `{mode}` — le banc "
                        "de releve qui s'en sert ne mesure donc pas ce qu'il dit",
                    )

    def test_le_releve_des_stores_est_rejoue_sur_le_depot(self):
        """`STORES` EST UN LITTERAL FIGE ; CE BANC LE REJOUE.

        Le relevé du 2026-09-16 est ecrit EN DUR dans le module. Il est juste
        aujourd'hui — et c'est precisement ce qui le rend dangereux : le jour ou
        `index.db` passera en WAL, `STORES` dira toujours `wal=False`, le rendu
        n'emettra pas ses lateraux, et le `git add -A` d'un adoptant emportera
        `index.db-wal`. Le temoin qui existait deja resterait VERT, puisqu'il
        affirme POSITIVEMENT que les lateraux d'un store hors WAL ne doivent pas
        etre ignores : il CERTIFIERAIT l'erreur. Ce banc-ci est ce qui rougit.

        POURQUOI L'EN-TETE ET NON `PRAGMA journal_mode` SUR LA BASE : parce que
        c'est MESURE (2026-09-16), ouvrir un store en WAL — meme en `mode=ro` —
        CREE `-wal` et `-shm` a cote. Un banc qui rejouerait le PRAGMA en place
        ecrirait donc dans l'arbre de travail exactement les fichiers dont il
        verifie l'ignorance, et salirait l'arbre que la porte doit voir stable.
        S'ajoute une raison de cout : `events.db` pese 637 Mo, donc le copier
        pour l'ouvrir a l'ecart n'est pas une option. La lecture d'en-tete est
        de 20 octets et de 0,1 ms sur ce meme fichier.

        UN STORE ABSENT SE SAUTE, IL NE ROUGIT PAS : les stores sont provisionnes
        PARESSEUSEMENT par leurs proprietaires, donc un depot frais n'en porte
        aucun. C'est `assertGreater(vus, 0)` qui empeche ce saut de vider le
        banc de toute substance.

        T-00000668 : `STORES` n'a plus qu'UNE entree (`events.db`, non suivie,
        git-ignoree). Sur le clone GELE de la porte `--at`, elle est absente —
        et `assertGreater(vus, 0)` romprait. `_un_store_present` la PROVISIONNE
        alors par son PROPRE proprietaire (`event_store.open_store(create=True)`),
        si et seulement si aucune entree n'existe deja, sur un spool JETABLE
        (`$AGENTS_EVENTS_DIR`, sans quoi le repli one-shot de l'ouverture
        fusionnerait le VRAI spool), et la retire apres — jamais un fichier qui
        preexistait. Ecartes : `assertGreaterEqual` (vert sans substance) et
        `skipTest`.
        """
        with self._un_store_present() as crees:
            vus = 0
            for s in STORES:
                chemin = ROOT / s.chemin
                if not chemin.is_file():
                    continue
                vus += 1
                with self.subTest(store=s.chemin):
                    self.assertEqual(
                        s.wal, _est_en_wal(chemin),
                        f"`STORES` declare wal={s.wal} pour {s.chemin}, la BASE dit "
                        f"l'inverse. Le relevé fige a diverge du depot : le rendu "
                        "du `.gitignore` emet — ou n'emet pas — les lateraux "
                        "`-wal`/`-shm` sur la foi de ce champ.",
                    )
                    if GIT is not None:
                        r = subprocess.run(
                            [GIT, "ls-files", "--error-unmatch", "--", s.chemin],
                            cwd=str(ROOT), capture_output=True, text=True)
                        self.assertEqual(
                            s.suivi, r.returncode == 0,
                            f"`STORES` declare suivi={s.suivi} pour {s.chemin}, "
                            f"`git ls-files` dit l'inverse (rc={r.returncode}). Un "
                            "store devenu suivi sans que ce champ bouge se fait "
                            "ignorer par le rendu, donc desuivre chez l'adoptant.",
                        )
            self.assertGreater(
                vus, 0,
                "AUCUN des stores de `STORES` n'existe dans cet arbre : ce banc "
                "n'a rien rejoue et serait vert par vacuite. Les chemins de la "
                "table ont probablement bouge.",
            )
            if crees:
                self.assertEqual(1, vus, "un store provisionne n'a pas ete rejoue")
        self.assertEqual(
            [], [str(p) for p in crees if p.exists()],
            "le store provisionne par ce banc n'a pas ete retire (events.db, -wal, -shm)",
        )

    @staticmethod
    def _empreinte(dossier: Path) -> dict[str, str] | None:
        """`{chemin relatif: sha256}` de chaque entree sous `dossier` — l'empreinte
        de `test_cadre_ledger_stores._empreinte`, recopiee (un banc n'importe pas
        un autre banc) et DURCIE : `None` si le dossier est ABSENT, distinct de
        `{}` (present et vide), et les repertoires comptent. Mesure sous
        T-00000668 : sur un clone ou le spool n'existe pas, le repli one-shot le
        CREE (`maintenance_lock`) — une empreinte qui confondait absent et vide
        ne le voyait pas."""
        if not dossier.is_dir():
            return None
        return {p.relative_to(dossier).as_posix():
                (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>")
                for p in sorted(dossier.rglob("*"))}

    @staticmethod
    def _event_store():
        """`.agents/bin/event_store.py`, importe par NOM le temps de l'import —
        `sys.path` est restaure juste apres (ses voisins `events`, `otel_receiver`
        restent en `sys.modules`, comme sous `test_template_hygiene.py`)."""
        sauve = list(sys.path)
        sys.path.insert(0, str(ROOT / ".agents" / "bin"))
        try:
            return importlib.import_module("event_store")
        finally:
            sys.path[:] = sauve

    @contextlib.contextmanager
    def _un_store_present(self):
        """Rend la liste des fichiers CREES ici — vide si un store de `STORES`
        existait deja (rien n'est alors touche). Sinon provisionne `events.db` par
        son proprietaire, sous `$AGENTS_EVENTS_DIR` jetable, verifie que le VRAI
        spool `.agents/state/events/` n'a pas bouge d'un octet, et retire a la
        sortie `events.db`, `-wal` et `-shm` (jamais un fichier preexistant)."""
        if any((ROOT / s.chemin).is_file() for s in STORES):
            yield []
            return
        cible = next(s for s in STORES if s.chemin.endswith("/events.db"))
        chemin = ROOT / cible.chemin
        annexes = [chemin, chemin.with_name(chemin.name + "-wal"),
                   chemin.with_name(chemin.name + "-shm")]
        preexistants = {p for p in annexes if p.exists()}
        parent_existait = chemin.parent.is_dir()
        # adopting-tree: chez l'adoptant ce spool peut manquer — `_empreinte` rend alors None avant ET apres, et la garde du producteur ci-dessous porte seule le temoin
        spool_reel = ROOT / ".agents" / "state" / "events"
        avant = self._empreinte(spool_reel)
        event_store = self._event_store()
        spool = Path(tempfile.mkdtemp(prefix="cadre-spool-vide-"))
        crees: list[Path] = []
        try:
            with mock.patch.dict(os.environ, {"AGENTS_EVENTS_DIR": str(spool)}):
                # GARDE avant tout appel au producteur (patron L-00000076, comme
                # `test_cadre_ledger_stores`) : le spool que l'ouverture va plier
                # EST le jetable. Sans elle, retirer le patch passe inapercu sur
                # un clone dont le vrai spool est vide.
                self.assertEqual(spool.resolve(),
                                 Path(event_store._events_dir()).resolve(),
                                 "le producteur ne resout pas le spool JETABLE")
                handle = event_store.open_store(chemin, create=True)
                try:
                    self.assertEqual("ok", handle.status,
                                     handle.degraded_reason() or "open_store")
                finally:
                    handle.close()
            crees.extend(p for p in annexes if p.exists() and p not in preexistants)
            self.assertEqual(avant, self._empreinte(spool_reel),
                             "provisionner events.db a touche le VRAI spool "
                             ".agents/state/events/ — le repli one-shot de "
                             "l'ouverture doit tourner sur un spool JETABLE")
            yield crees
        finally:
            for p in annexes:
                if p not in preexistants:
                    p.unlink(missing_ok=True)
            if not parent_existait:
                with contextlib.suppress(OSError):
                    chemin.parent.rmdir()
            shutil.rmtree(spool, ignore_errors=True)


class GabaritsJoignablesTests(unittest.TestCase):
    """OU vivent les gabarits, et par quel chemin on les atteint."""

    NOMS = ("pytest.ini.tmpl", "gitignore.tmpl")

    def test_le_gabarit_est_atteint_par_pkg_root(self):
        """NON SUFFISANT SEUL, ET C'EST ECRIT ICI PLUTOT QUE SOUS-ENTENDU.

        Ce temoin tourne sur l'ARBRE SOURCE, ou `pkg_root()` vaut `src/cadre/` et
        ou tout fichier du depot est trivialement present. Il etablit deux
        choses : que les gabarits sont la, et que la lecture passe REELLEMENT par
        `pkg_root()` — la seconde moitie est obtenue en DEPLAÇANT `pkg_root`, ce
        qui est la seule facon de distinguer « lit par pkg_root() » de « lit un
        fichier qui se trouve au meme endroit ».

        CE QU'IL NE PEUT PAS ETABLIR : qu'un adoptant les recevra. Une ressource
        absente de la wheel ne se manifeste qu'a l'installation, et ce temoin
        serait vert ce jour-la. `test_les_deux_gabarits_sont_dans_la_wheel` est
        le SECOND temoin, requis, et il n'est pas optionnel.
        """
        racine = pkg_root()
        self.assertEqual("cadre", racine.name, f"pkg_root() inattendu : {racine}")
        for nom in self.NOMS:
            with self.subTest(gabarit=nom):
                chemin = racine / surf.GABARITS / nom
                self.assertTrue(chemin.is_file(), f"gabarit absent de l'arbre source : {chemin}")
                self.assertTrue(chemin.read_text(encoding="utf-8").strip(),
                                "gabarit VIDE — le rendu serait vide sans rien casser")

        # LA DERIVATION, PROUVEE EN DEPLAÇANT LA RACINE. Si le module lisait par
        # `__file__` ou par un chemin en dur, le sentinelle ci-dessous ne
        # ressortirait pas du rendu.
        with tempfile.TemporaryDirectory(prefix="cadre-pkg-") as d:
            faux = Path(d).resolve() / "cadre"
            (faux / surf.GABARITS).mkdir(parents=True)
            (faux / surf.GABARITS / "pytest.ini.tmpl").write_text(
                "[pytest]\n{testpaths}sentinelle = OUI\n", encoding="utf-8")
            projet = Path(d).resolve() / "projet"
            projet.mkdir()

            reel = surf.pkg_root
            surf.pkg_root = lambda: faux
            try:
                rendu = rendre_pytest_ini(projet)
            finally:
                surf.pkg_root = reel

            self.assertIn(
                "sentinelle = OUI", rendu,
                "le rendu ne suit pas `pkg_root()` : deplacer la racine du paquet "
                "n'a pas change le texte produit, donc le gabarit est atteint par "
                "un autre chemin — ce que `no_hardcoded_paths` interdit.",
            )
            # LA RESTAURATION EST VERIFIEE, pas supposee : un `pkg_root` laisse
            # deplace contaminerait tous les temoins suivants du meme processus,
            # et le ferait en les rendant VERTS sur un faux gabarit.
            self.assertNotIn("sentinelle", rendre_pytest_ini(projet),
                             "la racine reelle n'a pas ete restauree")

    @unittest.skipIf(UV is None, "SAUT ANNONCE : `uv` absent du PATH, la wheel ne peut pas etre batie ici — la presence des gabarits dans la wheel n'est PAS mesuree par cette execution")
    @unittest.skipUnless(CADRE_EST_LE_PAQUET_BATI, "SAUT ANNONCE : le `pyproject.toml` de cet arbre ne batit pas la distribution `cadre-kit` (paquet `cadre`) — la wheel produite ici serait celle d'un autre projet, et l'assertion n'aurait pas de sujet")
    def test_les_deux_gabarits_sont_dans_la_wheel(self):
        """LE SECOND TEMOIN, ET LE SEUL QUI PARLE DE CE QU'UN ADOPTANT REÇOIT.

        `--out-dir` pointe hors du depot : une wheel batie dans `dist/` salirait
        l'arbre que la porte de verification doit voir stable.

        MESURE DU 2026-09-16 : un sous-repertoire neuf sous `src/cadre/data/`
        entre dans la wheel SANS aucune declaration `package-data`, parce que
        `[tool.hatch.build.targets.wheel] packages = ["src/cadre"]` prend
        l'arbre. Ce temoin est ce qui transforme cette mesure en propriete tenue.
        """
        with tempfile.TemporaryDirectory(prefix="cadre-wheel-") as d:
            sortie = Path(d).resolve()
            try:
                r = subprocess.run([UV, "build", "--wheel", "--out-dir", str(sortie)],
                                   cwd=str(ROOT), capture_output=True, text=True,
                                   timeout=DELAI_BUILD)
            except subprocess.TimeoutExpired:
                # QUATRIEME SAUT ANNONCE. `uv build` sort sur le reseau pour
                # resoudre `build-system.requires`, et la specification nomme les
                # « postes clients verrouilles ou derriere un proxy sortant » : un
                # proxy qui accepte la connexion puis ne repond jamais faisait
                # PENDRE la porte sans borne. Un depassement ne dit rien sur
                # l'empaquetage — il dit que le reseau n'a pas repondu — donc il
                # se saute en l'annoncant, comme les trois autres.
                self.skipTest(
                    f"SAUT ANNONCE : `uv build` n'a pas rendu la main en "
                    f"{DELAI_BUILD} s (reseau ou proxy sortant muet) — la "
                    "presence des gabarits dans la wheel n'est PAS mesuree par "
                    "cette execution"
                )
            # TROISIEME SAUT ANNONCE, et il ne porte PAS sur la meme chose que les
            # deux decorateurs : ceux-la disent que `uv` est absent ou que l'arbre
            # ne batit pas `cadre` ; celui-ci dit que `uv` est la, que l'arbre est
            # le bon, et que le BACKEND de build reste injoignable — cache uv froid
            # ou DNS de PyPI en panne. MESURE : `UV_CACHE_DIR=<vide> uv build --wheel
            # --offline` rend « Failed to resolve requirements from
            # build-system.requires … hatchling was not found in the cache ».
            #
            # POURQUOI SAUTER PLUTOT QUE ROUGIR, et c'est une decision prise le
            # 2026-09-16 sur DEUX precedents de ce depot, pas sur un gout : un
            # rouge dirait « l'empaquetage est casse » quand c'est le reseau qui
            # l'est, et ce depot a deja ecrit qu'« un banc bruyant finit desarme ».
            # `run-bash-tests.sh` a recu exactement ce traitement — COVERAGE
            # DEGRADED et rc 0 au lieu d'`exit 1` sur zero suite, decision pilote
            # du 2026-09-14 livree sous T-00000585 MEME — et la porte annonce deja
            # une vingtaine de SKIP pour des scanners absents (T-00000529).
            #
            # LA BORNE, ET ELLE A ETE CORRIGEE PAR LE BINOME DE CLOTURE APRES
            # MESURE. La premiere redaction testait la seule chaine
            # `build-system.requires`, en affirmant « par construction » que tout
            # autre echec restait rouge. C'ETAIT FAUX : une version epinglee
            # inexistante est une VRAIE casse d'empaquetage, et l'ancienne
            # condition la faisait SAUTER en silence — exactement le defaut qu'un
            # saut annonce ne doit pas introduire.
            #
            # LE PREDICAT EST UNE FONCTION DE MODULE, PAS UNE CONDITION EN LIGNE,
            # et c'est ce qui rend le correctif verifiable :
            # `test_le_predicat_de_saut_discrimine` appelle LA MEME fonction sur
            # les sorties d'echec mesurees. Une condition ecrite ici serait
            # RE-IMPLEMENTEE la-bas, et deux cotes qui partagent la meme
            # generation ne prouvent rien.
            # NOM `journal` ET NON `sortie` : `sortie` designe deja le repertoire
            # de la wheel dans ce bloc, et le reaffecter casserait le
            # `sortie.glob("cadre_kit-*.whl")` plus bas.
            journal = r.stdout + r.stderr
            if r.returncode != 0 and _est_un_backend_non_resolvable(journal):
                self.skipTest(
                    "SAUT ANNONCE : backend de build non resolvable (cache uv "
                    "vide ou DNS de PyPI en panne) — la presence des gabarits "
                    "dans la wheel n'est PAS mesuree par cette execution"
                )
            self.assertEqual(0, r.returncode, f"uv build a echoue :\n{r.stdout}\n{r.stderr}")
            wheels = sorted(sortie.glob("cadre_kit-*.whl"))
            self.assertEqual(1, len(wheels), f"une seule wheel attendue, vu {wheels}")

            membres = zipfile.ZipFile(wheels[0]).namelist()
            self.assertGreater(len(membres), 5,
                               "wheel quasi vide — toutes les assertions qui suivent "
                               "seraient vertes par vacuite")
            for nom in self.NOMS:
                attendu = f"cadre/{surf.GABARITS}/{nom}"
                with self.subTest(membre=attendu):
                    self.assertIn(
                        attendu, membres,
                        f"{attendu} n'est pas dans la wheel : l'adoptant installerait "
                        "un `cadre init` incapable de rendre ce gabarit. Membres "
                        f"data/ vus : {[m for m in membres if '/data/' in m]}",
                    )


class PredicatDeSautTests(unittest.TestCase):
    """LE SAUT ANNONCE DU TEMOIN WHEEL DISCRIMINE-T-IL VRAIMENT ?

    Un saut annonce est une renonciation a mesurer : il doit donc etre le plus
    ETROIT possible, et quelque chose doit prouver qu'il l'est. Sans ce banc, le
    predicat corrige restait une affirmation — rien n'etablissait qu'il laisse
    ROUGIR une vraie casse d'empaquetage.
    """

    #: Les trois premieres sorties ont ete mesurees avec `uv build` le
    #: 2026-09-16 sur un projet JETABLE (jamais sur le manifeste de ce depot,
    #: qu'un banc n'a pas a muter). Les cas 4 a 6 sont les sorties completes
    #: de `uv build` mesurees le 2026-10-21 depuis /tmp/jetable/proj sous
    #: `sandbox-exec` sans reseau, chacune avec un cache uv vide.
    #:
    #:   cas 1 — cache vide + UV_OFFLINE=1        -> SAUTER
    #:   cas 2 — requires = ["hatchling==99.0.0"] -> ROUGIR
    #:   cas 3 — requires = [paquet inexistant]   -> ROUGIR
    #:   cas 4 — index PyPI injoignable (DNS)      -> SAUTER
    #:   cas 5 — autre index introuvable (DNS)     -> ROUGIR
    #:   cas 6 — PyPI, proxy sortant en panne       -> ROUGIR
    #:
    #: LE CAS 3 EST LE PLUS INSTRUCTIF, et il a failli manquer : sa sortie porte
    #: « was not found in the package registry », a un mot de « not found in the
    #: cache ». Un predicat ecrit sur « not found in » aurait saute une casse
    #: d'empaquetage franche.
    SORTIES = (
        ("cache vide + UV_OFFLINE=1", False, """\
error: Failed to build `/tmp/jetable`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling`
  Caused by: Because hatchling was not found in the cache and you require \
hatchling, we can conclude that your requirements are unsatisfiable.

hint: Packages were unavailable because the network was disabled. When the \
network is disabled, registry packages may only be read from the cache."""),
        ("version epinglee inexistante", True, """\
error: Failed to build `/tmp/jetable`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling==99.0.0`
  Caused by: Because there is no version of hatchling==99.0.0 and you require \
hatchling==99.0.0, we can conclude that your requirements are unsatisfiable."""),
        ("paquet inexistant", True, """\
error: Failed to build `/tmp/jetable`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling-typo-qui-nexiste-pas`
  Caused by: Because hatchling-typo-qui-nexiste-pas was not found in the \
package registry and you require hatchling-typo-qui-nexiste-pas, we can \
conclude that your requirements are unsatisfiable."""),
        ("index PyPI injoignable (DNS)", False, """\
Building wheel...
error: Failed to build `/private/tmp/jetable/proj`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling`
  Caused by: Request failed after 3 retries in 11.7s
  Caused by: Failed to fetch: `https://pypi.org/simple/hatchling/`
  Caused by: error sending request for url (https://pypi.org/simple/hatchling/)
  Caused by: client error (Connect)
  Caused by: dns error
  Caused by: failed to lookup address information: nodename nor servname provided, or not known
"""),
        ("autre index introuvable (DNS)", True, """\
Building wheel...
error: Failed to build `/private/tmp/jetable/proj`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling`
  Caused by: Request failed after 3 retries in 5.2s
  Caused by: Failed to fetch: `https://pypi.invalid/simple/hatchling/`
  Caused by: error sending request for url (https://pypi.invalid/simple/hatchling/)
  Caused by: client error (Connect)
  Caused by: dns error
  Caused by: failed to lookup address information: nodename nor servname provided, or not known
"""),
        ("PyPI avec proxy sortant en panne", True, """\
Building wheel...
error: Failed to build `/private/tmp/jetable/proj`
  Caused by: Failed to resolve requirements from `build-system.requires`
  Caused by: No solution found when resolving: `hatchling`
  Caused by: Request failed after 3 retries in 9.4s
  Caused by: Failed to fetch: `https://pypi.org/simple/hatchling/`
  Caused by: error sending request for url (https://pypi.org/simple/hatchling/)
  Caused by: client error (Connect)
  Caused by: tunnel error: failed to create underlying connection
  Caused by: tcp connect error
  Caused by: Operation not permitted (os error 1)
"""),
    )

    def test_le_predicat_de_saut_discrimine(self):
        """LES DEUX SENS, parce qu'un seul est satisfait par une constante.

        Un predicat qui rend TOUJOURS vrai fait sauter le temoin wheel en toute
        circonstance ; un predicat qui rend TOUJOURS faux le fait rougir des que
        le reseau tombe. Seules les deux moities ensemble epinglent la frontiere.
        """
        for etiquette, doit_rougir, journal in self.SORTIES:
            with self.subTest(cas=etiquette):
                saute = _est_un_backend_non_resolvable(journal)
                self.assertEqual(
                    not doit_rougir, saute,
                    f"cas « {etiquette} » : le predicat "
                    f"{'SAUTE' if saute else 'ROUGIT'} la ou il devrait "
                    f"{'ROUGIR' if doit_rougir else 'SAUTER'}. Les sorties "
                    "sont des mesures reelles de `uv build` ; si le predicat a "
                    "change, c'est la frontiere du saut annonce qui a bouge.",
                )

        self.assertTrue(
            any(doit for _, doit, _ in self.SORTIES),
            "aucun cas ROUGIR dans le jeu — le banc ne prouve plus que le saut "
            "est etroit",
        )
        self.assertTrue(
            any(not doit for _, doit, _ in self.SORTIES),
            "aucun cas SAUTER dans le jeu — le banc ne prouve plus que le saut "
            "existe",
        )

    def test_les_sorties_portent_bien_le_marqueur_commun(self):
        """LA MOITIE QUI INTERDIT AU JEU DE DONNEES DE SE VIDER.

        Les sorties doivent TOUTES porter `build-system.requires` : c'est
        ce qui fait d'elles le meme genre d'echec, et donc ce qui rend la
        discrimination non triviale. Le jour ou quelqu'un remplacerait l'une
        d'elles par un texte quelconque, le banc d'a cote passerait encore et
        ne mesurerait plus rien.
        """
        for etiquette, _, journal in self.SORTIES:
            with self.subTest(cas=etiquette):
                self.assertIn("build-system.requires", journal)
                self.assertIn("Failed to resolve requirements", journal)


#: La sonde du temoin G : execute le banc COPIE dans le kit jetable, puis rend
#: depuis CE `cadre` le gabarit `pytest.ini` d'un projet vide.
_SONDE_G = r'''
import runpy, sys
from pathlib import Path
banc = runpy.run_path(sys.argv[1], run_name="vendor_seul_g")
projet = Path(sys.argv[2])
print("SURF=" + banc["surf"].__file__)
print("RACINE=" + str(banc["pkg_root"]()))
print("RENDU=" + str("[pytest]" in banc["rendre_pytest_ini"](projet)))
'''


class VendorSeulTests(unittest.TestCase):
    """G (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot G) — `cadre init` depuis le paquet VENDOR.

    Un kit jetable « vendor seul » : ce banc, `vendor_paths.py`, et le paquet
    `cadre` (copie de `exiger(ROOT, "cadre")`) sous `.agents/vendor/cadre/`, SANS
    `src/`. Un `cadre` ETRANGER (sans `init_surfaces`) est mis sur `PYTHONPATH` :
    seul le chargement par chemin de `vendor_paths` lit le bon. Mutant :
    `sys.path.insert(0, str(ROOT / "src"))` a la place de `charger_paquet` — le
    banc copie importe l'etranger et la sonde rougit."""

    def test_vendor_seul_g(self):
        base = Path(tempfile.mkdtemp(prefix="cadre-vseul-g-")).resolve()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        kit = base / "kit"
        banc = kit / ".agents" / "evals" / Path(__file__).name
        banc.parent.mkdir(parents=True)
        shutil.copyfile(__file__, banc)
        (kit / ".agents" / "bin").mkdir(parents=True)
        shutil.copyfile(ROOT / ".agents" / "bin" / "vendor_paths.py",
                        kit / ".agents" / "bin" / "vendor_paths.py")
        paquet = kit / ".agents" / "vendor" / "cadre"
        shutil.copytree(VENDOR.exiger(ROOT, "cadre"), paquet,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        etranger = base / "etranger" / "cadre"
        etranger.mkdir(parents=True)
        (etranger / "__init__.py").write_text("", encoding="utf-8")
        projet = base / "projet"
        projet.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("CADRE_")}
        env["PYTHONPATH"] = str(etranger.parent)
        r = subprocess.run([sys.executable, "-B", "-c", _SONDE_G, str(banc), str(projet)],
                           cwd=str(base), env=env, capture_output=True, text=True,
                           timeout=DELAI_PYTEST, check=False)
        self.assertEqual(0, r.returncode, f"sonde vendor seul :\n{r.stdout}\n{r.stderr}")
        lignes = dict(ligne.split("=", 1) for ligne in r.stdout.splitlines() if "=" in ligne)
        self.assertFalse((kit / "src").exists(), "le kit jetable porte un `src/`")
        self.assertEqual(paquet / "init_surfaces.py", Path(lignes["SURF"]).resolve())
        self.assertEqual(paquet, Path(lignes["RACINE"]).resolve())
        self.assertEqual("True", lignes["RENDU"], "gabarit pytest.ini non rendu")


if __name__ == "__main__":
    unittest.main()
