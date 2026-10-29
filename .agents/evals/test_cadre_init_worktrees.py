"""`cadre init` NE MET PLUS LES BANCS D'UN AUTRE CHECKOUT DANS LE `testpaths`.

LE DEFAUT, MESURE. `repertoires_de_test` (`src/cadre/init_surfaces.py`) parcourait
le projet de l'adoptant en n'elaguant que par NOM (`ELAGAGE`). Un worktree lie
pose par un agent sous `.claude/worktrees/agent-x`, ou un clone depose dans
l'arbre, porte une copie ENTIERE de bancs : ils entraient dans le `testpaths`
genere, et la porte de l'adoptant jugeait le code d'une AUTRE branche. Mesure sur
un projet jetable portant un worktree reel, un sous-module reel et un clone : le
rendu listait `.claude/worktrees/agent-x/tests` et `third/clone/tests`.

LA REGLE EST UN MARQUEUR, JAMAIS UN NOM. Un enfant dont le `.git` est un
REPERTOIRE (clone) ou un FICHIER `gitdir: .../worktrees/<nom>` (worktree lie)
n'est pas descendu ; tout le reste — dont le sous-module absorbe, `gitdir:
.../modules/...` — est garde. Elaguer `.claude` par son nom serait la classe du
defaut : un worktree pose ailleurs passerait (W3), et un repertoire ordinaire
nomme `worktrees` serait perdu.

UN SOUS-MODULE DECLARE EST GARDE MEME NON ABSORBE. `git submodule add` d'un clone
deja present laisse un `.git` REPERTOIRE : sans exemption, ce sous-module
disparaitrait du `testpaths` selon la FACON dont il a ete ajoute. Les chemins
`path =` du `.gitmodules` de la racine sont exemptes, lus par `Workspace`, sans
appel a `git` (W2b).

LA PARITE AVEC LE PREDICAT DU RECENSEMENT EST EPINGLEE, PAS PARTAGEE. Le noyau
voyage seul dans la wheel et ne peut pas importer `.agents/` ; la garde d'index du
recensement lance `git`, ce que la couture d'E/S interdit. W5 rejoue donc les deux
predicats sur les memes contenus de `.git` et exige le meme verdict, et le
verdict ATTENDU — sans quoi deux predicats faux de la meme facon passeraient.

`git` REEL, ENVIRONNEMENT PURGE. Chaque projet vit sous un repertoire temporaire ;
`git` est appele par une liste d'arguments, `GIT_*` retire de l'environnement,
configuration globale et systeme neutralisees, hooks coupes, signature coupee,
60 s au plus par appel. Sans `git` sur le poste, les temoins qui en ont besoin
SAUTENT et le disent ; W5, W6 et W7 n'en ont pas besoin.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# `cadre` là où la règle de `vendor_paths` le désigne (vendor d'abord, `src` sinon),
# chargé par chemin : aucune entrée neuve en tête de `sys.path`.
_SPEC_VP = importlib.util.spec_from_file_location(
    "_init_worktrees_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
VENDOR = importlib.util.module_from_spec(_SPEC_VP)
sys.modules[_SPEC_VP.name] = VENDOR
_SPEC_VP.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")

from cadre import init_surfaces as surf  # noqa: E402
from cadre.init_surfaces import rendre_pytest_ini, repertoires_de_test  # noqa: E402
from cadre.workspace import Workspace  # noqa: E402

GIT = shutil.which("git")
SANS_GIT = ("git absent du PATH : ce temoin exige un worktree, un sous-module ou "
            "un clone REELS, et ne les simule pas")

#: Au-dela, un appel est tenu pour BLOQUE sur une FIFO (une lecture l'a ouverte).
DELAI_FIFO = 10.0

_CONFIG_GIT = (
    "-c", "user.name=banc", "-c", "user.email=banc@exemple.invalid",
    "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}",
    "-c", "protocol.file.allow=always", "-c", "init.defaultBranch=main",
)


def _env_git() -> dict[str, str]:
    """L'environnement du poste SANS `GIT_*` : un `GIT_DIR` ou un `GIT_WORK_TREE`
    herite (hook, worktree d'agent) ferait viser a `git` un autre depot."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(cwd: Path, *args: str) -> None:
    r = subprocess.run([GIT, *_CONFIG_GIT, *args], cwd=cwd, env=_env_git(),
                       capture_output=True, text=True, timeout=60, check=False)
    if r.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} -> rc={r.returncode}\n{r.stdout}{r.stderr}")


def _banc(dossier: Path, nom: str = "test_a.py") -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text("def test_a():\n    assert True\n", encoding="utf-8")


def _charger_recensement(cas: unittest.TestCase, chemin: Path):
    """Le recensement, charge SOUS UN NOM PRIVE et DANS le test.

    JAMAIS SOUS SON BASENAME : le `pytest.ini` du kit collecte en import-mode
    `prepend`, ou un module de banc est nomme par son basename, et ce fichier-ci
    se collecte AVANT le recensement (ordre alphabetique). Un
    `sys.modules["test_repo_walk_census"]` pose ici serait REUTILISE a la
    collecte du vrai fichier. L'inscription sous le nom prive precede
    l'execution (une dataclass a annotations differees la reclame) et se
    retire au nettoyage."""
    spec = importlib.util.spec_from_file_location("_census_1073", chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    cas.addCleanup(sys.modules.pop, spec.name, None)
    spec.loader.exec_module(module)
    return module


def _debloquer(fifo: Path) -> None:
    """Ouvre la FIFO en ECRITURE non bloquante puis la referme : un lecteur
    bloque dans son `open` repart et lit une fin de fichier. Sans lecteur,
    `ENXIO` — rien a debloquer."""
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return
    os.close(fd)


class _Projet(unittest.TestCase):
    """Fabrique de projets jetables ; aucun temoin ici."""

    def _jetable(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="t1084-")).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def _depot(self, racine: Path, banc: str = "test_a.py") -> Path:
        _banc(racine / "tests", banc)
        _git(racine, "init", "-q")
        _git(racine, "add", "-A")
        _git(racine, "commit", "-qm", "init")
        return racine


@unittest.skipIf(GIT is None, SANS_GIT)
class CheckoutsReelsTests(_Projet):
    """W1-W4 : worktrees, sous-modules et clone poses par un VRAI `git`."""

    def test_W1_un_worktree_d_agent_sort_du_testpaths(self):
        projet = self._depot(self._jetable() / "projet")
        agent = projet / ".claude" / "worktrees" / "agent-x"
        _git(projet, "worktree", "add", "-q", str(agent), "-b", "wt/x")
        self.assertTrue((agent / "tests" / "test_a.py").is_file(),
                        "precondition : le worktree porte bien une copie des bancs")
        self.assertEqual(["tests"], repertoires_de_test(projet))
        self.assertNotIn(".claude", rendre_pytest_ini(projet))

    def test_W2_un_sous_module_absorbe_et_son_imbrique_restent(self):
        """L'imbrique `libs/sub/deps/x` n'est declare QUE dans le `.gitmodules`
        du sous-module, que ce module ne lit pas : seul le MARQUEUR
        (`gitdir: .../modules/...`) le garde. C'est ce qui donne des dents a ce
        temoin contre « tout `.git` fichier elague », malgre l'exemption."""
        base = self._jetable()
        interne = self._depot(base / "interne", "test_i.py")
        sub = self._depot(base / "sub", "test_s.py")
        _git(sub, "submodule", "add", "-q", str(interne), "deps/x")
        _git(sub, "commit", "-qm", "imbrique")
        projet = self._depot(base / "projet")
        _git(projet, "submodule", "add", "-q", str(sub), "libs/sub")
        _git(projet, "submodule", "update", "--init", "--recursive")
        for rel in ("libs/sub/.git", "libs/sub/deps/x/.git"):
            self.assertTrue((projet / rel).is_file(),
                            f"precondition : {rel} est un fichier `gitdir:` absorbe")
        self.assertEqual(
            ["libs/sub/deps/x/tests", "libs/sub/tests", "tests"],
            repertoires_de_test(projet),
        )

    def test_W2b_un_sous_module_declare_non_absorbe_reste(self):
        base = self._jetable()
        sub = self._depot(base / "sub", "test_s.py")
        projet = self._depot(base / "projet")
        _git(base, "clone", "-q", str(sub), str(projet / "libs" / "sub2"))
        _git(projet, "submodule", "add", "-q", str(sub), "libs/sub2")
        self.assertTrue((projet / "libs" / "sub2" / ".git").is_dir(),
                        "precondition : `submodule add` d'un clone existant laisse "
                        "un `.git` REPERTOIRE")
        self.assertEqual(["libs/sub2/tests", "tests"], repertoires_de_test(projet))
        # Un octet non UTF-8 ailleurs dans le `.gitmodules` n'efface pas la
        # declaration : lecture avec remplacement, jamais un decodage strict.
        with (projet / ".gitmodules").open("ab") as fh:
            fh.write(b"# commentaire \xff\xfe\n")
        self.assertEqual(["libs/sub2/tests", "tests"], repertoires_de_test(projet))

    def test_W3_un_worktree_hors_convention_sort_et_un_dossier_worktrees_reste(self):
        projet = self._depot(self._jetable() / "projet")
        _git(projet, "worktree", "add", "-q", str(projet / "ailleurs" / "wt-y"),
             "-b", "wt/y")
        _banc(projet / "worktrees" / "tests", "test_w.py")
        self.assertEqual(["tests", "worktrees/tests"], repertoires_de_test(projet))

    def test_W4_un_clone_imbrique_non_declare_sort_du_testpaths(self):
        base = self._jetable()
        autre = self._depot(base / "autre", "test_o.py")
        projet = self._depot(base / "projet")
        _git(base, "clone", "-q", str(autre), str(projet / "third" / "clone"))
        self.assertTrue((projet / "third" / "clone" / ".git").is_dir(),
                        "precondition : un clone porte un `.git` REPERTOIRE")
        self.assertEqual(["tests"], repertoires_de_test(projet))


_REPERTOIRE = object()

#: (cas, contenu du `.git`, verdict attendu). `_REPERTOIRE` : un repertoire ;
#: `None` : aucun `.git` ; sinon les octets d'un fichier regulier.
CAS_PARITE = (
    ("repertoire (clone)", _REPERTOIRE, True),
    ("worktree, gitdir absolu", b"gitdir: /src/projet/.git/worktrees/agent-x\n", True),
    ("worktree, barre finale", b"gitdir: /src/projet/.git/worktrees/agent-x/\n", True),
    ("worktree, antislashs et CRLF",
     b"gitdir: C:\\src\\projet\\.git\\worktrees\\agent-x\r\n", True),
    ("worktree, gitdir relatif", b"gitdir: ../../.git/worktrees/agent-x\n", True),
    ("worktree, ni espace ni fin de ligne", b"gitdir:/src/.git/worktrees/y", True),
    ("worktree, fin de ligne CR seule", b"gitdir: /src/.git/worktrees/y\rreste", True),
    ("sous-module absorbe", b"gitdir: ../.git/modules/x\n", False),
    ("worktrees au milieu du chemin", b"gitdir: /src/.git/worktrees/y/modules/z\n", False),
    ("worktrees en deuxieme ligne", b"gitdir: ../.git/modules/x\n/worktrees/y\n", False),
    ("tabulation verticale dans le chemin", b"gitdir: /src/worktrees/y\x0b/z\n", False),
    ("dechet", b"ceci n'est pas un gitdir\n", False),
    ("octets invalides en tete", b"\xff\xfe\x00gitdir: /src/worktrees/y\n", False),
    ("fichier vide", b"", False),
    ("absent", None, False),
)


class ProvenanceTests(unittest.TestCase):
    def test_cadre_charge_est_celui_que_vendor_paths_designe(self):
        """Arbre « les deux » : le paquet vendor, jamais `src/cadre` mis en tete."""
        attendu, _origine = VENDOR.verifier_charge(ROOT, "cadre")
        self.assertEqual(attendu, Path(surf.__file__).resolve().parent)


class PariteAvecLeRecensementTests(unittest.TestCase):
    """W5 : meme verdict que le predicat du recensement, cas par cas."""

    def test_W5_meme_verdict_que_le_predicat_du_recensement(self):
        # adopting-tree: le recensement voyage avec ce banc ; absent, la parite n'a plus de reference
        recensement = ROOT / ".agents" / "evals" / "test_repo_walk_census.py"
        if not recensement.is_file():
            self.skipTest(f"{recensement} absent : aucune reference de parite")
        reference = _charger_recensement(self, recensement)._checkout_imbrique
        racine = Path(tempfile.mkdtemp(prefix="t1084-parite-")).resolve()
        self.addCleanup(shutil.rmtree, racine, ignore_errors=True)
        atelier = Workspace(racine)
        self.assertGreaterEqual(len(CAS_PARITE), 8)
        for i, (nom, contenu, attendu) in enumerate(CAS_PARITE):
            rel = f"cas{i:02d}"
            (racine / rel).mkdir()
            marqueur = racine / rel / ".git"
            if contenu is _REPERTOIRE:
                marqueur.mkdir()
            elif contenu is not None:
                marqueur.write_bytes(contenu)
            with self.subTest(cas=nom):
                self.assertEqual(attendu, reference(str(racine / rel)),
                                 "la REFERENCE elle-meme a change de verdict")
                self.assertEqual(attendu, surf._checkout_imbrique(atelier, rel))


@unittest.skipUnless(hasattr(os, "mkfifo"), "os.mkfifo absent : aucune FIFO a poser")
class FifoTests(_Projet):
    """W6 : un `.git` ou un `.gitmodules` FIFO n'est jamais LU."""

    def _dans_le_delai(self, appel, fifos):
        sortie: dict = {}

        def _cible():
            try:
                sortie["valeur"] = appel()
            except BaseException as exc:  # noqa: BLE001 — relevee dans le fil du test
                sortie["erreur"] = exc

        fil = threading.Thread(target=_cible, daemon=True)
        fil.start()
        fil.join(DELAI_FIFO)
        if fil.is_alive():
            for fifo in fifos:
                _debloquer(fifo)
            fil.join(DELAI_FIFO)
            self.fail(f"bloque plus de {DELAI_FIFO} s : une FIFO a ete OUVERTE en lecture")
        if "erreur" in sortie:
            raise sortie["erreur"]
        return sortie["valeur"]

    def test_W6_un_git_et_un_gitmodules_fifo_ne_bloquent_pas(self):
        projet = self._jetable()
        _banc(projet / "tests")
        _banc(projet / "fifo" / "tests", "test_f.py")
        fifos = [projet / "fifo" / ".git", projet / ".gitmodules"]
        for fifo in fifos:
            os.mkfifo(fifo)
        rendu, imbrique = self._dans_le_delai(
            lambda: (repertoires_de_test(projet),
                     surf._checkout_imbrique(Workspace(projet), "fifo")),
            fifos,
        )
        self.assertEqual(["fifo/tests", "tests"], rendu)
        self.assertFalse(imbrique)


class BoucleDeLiensTests(_Projet):
    """W7 : une boucle de liens sur `.git` est gardee, jamais une levee."""

    def test_W7_une_boucle_reelle_sur_git_est_gardee(self):
        projet = self._jetable()
        _banc(projet / "tests")
        _banc(projet / "boucle" / "tests", "test_b.py")
        try:
            os.symlink(".git", projet / "boucle" / ".git")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible sur ce poste : {exc}")
        self.assertEqual(["boucle/tests", "tests"], repertoires_de_test(projet))

    def test_W7b_la_runtimeerror_de_resolve_rend_faux(self):
        """Python 3.11 et 3.12 levent `RuntimeError` dans `Path.resolve()` sur
        une boucle de liens ; 3.13 et suivants ne levent plus (mesure sous 3.14 :
        W7 passe sans elle). La levee est donc SIMULEE, pour que la branche soit
        jouee sur tout interpreteur."""
        projet = self._jetable()
        _banc(projet / "tests")
        _banc(projet / "x" / "tests", "test_x.py")
        vrai = Workspace.est_repertoire

        def _leve(atelier, relatif="."):
            if str(relatif).endswith(".git"):
                raise RuntimeError(f"Symlink loop from {relatif!r}")
            return vrai(atelier, relatif)

        with mock.patch.object(Workspace, "est_repertoire", _leve):
            self.assertFalse(surf._checkout_imbrique(Workspace(projet), "x"))
            self.assertEqual(["tests", "x/tests"], repertoires_de_test(projet))


class GitmodulesTests(_Projet):
    """W8 : la forme du `.gitmodules` lue, cas par cas, sans `git`."""

    def test_W8_les_chemins_declares_sont_lus_dans_la_forme_que_git_ecrit(self):
        projet = self._jetable()
        (projet / ".gitmodules").write_bytes(
            b'[submodule "a"]\n\tpath = libs/a\n\turl = ../a\n'
            b'[submodule "b"]\n    Path=libs/b/\n'
            b'[submodule "c"]\n\tpath = "libs/c d"\n'
            b'[submodule "e"]\n\tpathx = libs/faux\n'
            b'[submodule "f"]\n\tpath = libs/f ; commentaire en ligne\n'
        )
        self.assertEqual(
            frozenset({"libs/a", "libs/b", "libs/c d", "libs/f ; commentaire en ligne"}),
            surf._sous_modules_declares(Workspace(projet)),
        )

    def test_W8b_sans_gitmodules_rien_n_est_exempte(self):
        self.assertEqual(frozenset(), surf._sous_modules_declares(Workspace(self._jetable())))

    def test_W8c_un_gitmodules_hostile_est_lu_en_temps_borne(self):
        """ReDoS (S-00003900 ; binôme 7+8, T3) : `(?im)^\\s*path…` sur le texte ENTIER traversait, à
        CHAQUE début de ligne, toutes les lignes vides sans `path` derrière (quadratique : 40 000
        lignes, 3,4 s). 64 Ko lus au plus, LIGNE À LIGNE, linéaire sur une ligne longue aussi (une
        regex `(.*?)[ \\t]*` par ligne : 16 000 espaces, 0,5 s). La ligne que la borne COUPE est
        écartée : « path = li » n'exempte pas `li`."""
        projet = self._jetable()
        for corps, attendu in (
            (b"\n" * 400_000, set()),
            (b"\tpath = libs/a\n" + b"\n" * 100_000 + b"\tpath = libs/hors-borne\n", {"libs/a"}),
            (b"\tpath = x" + b" " * 60_000 + b"y\n", {"x" + " " * 60_000 + "y"}),
            (b"\n" * (65_536 - 10) + b"\tpath = libs/coupee\n", set()),
        ):
            (projet / ".gitmodules").write_bytes(corps)
            t0 = time.monotonic()
            lus = surf._sous_modules_declares(Workspace(projet))
            self.assertLess(time.monotonic() - t0, 1.0, f"{len(corps)} octets")
            self.assertEqual(frozenset(attendu), lus, f"{len(corps)} octets")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
