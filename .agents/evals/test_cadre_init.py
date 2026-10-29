#!/usr/bin/env python3
"""BANCS DE `cadre init`, PREMIER TIERS — T-00000968 (BK-120, Epic E-06).

CE QUE LA TÂCHE PROMET, ET CE QUE CHAQUE TÉMOIN TIENT :
  * I1 — `cadre init` sur un projet NEUF (un `git init` sans `.agents/`) crée
    les trois stores, et les crée PAR `creer_les_stores` (espion sur l'appel
    réel, jamais un double qui remplacerait la création) ;
  * I2 — deux `cadre init` successifs ne produisent AUCUN diff, ni sous le
    projet ni sous la partition machine : relevé `{chemin: sha256}` des deux
    arbres par `git ls-files -z -co` (suivis ET non suivis, rien d'ignoré),
    pris après le premier appel puis après le second ;
  * I3 — `--host` : un hôte de la liste fermée passe ; un hôte hors liste est
    refusé en 2 SANS RIEN ÉCRIRE, par la CLI comme par l'API ;
  * I4 — une option surnuméraire sur `init` est refusée en 2, jamais avalée ;
  * I4b — le pendant : les arguments d'un AUTRE nom réservé, sans parseur
    (`cadre hosts add codex`), restent TOLÉRÉS (« RÉSERVÉ », jamais
    « inconnue ») — le témoin de `test_cadre_package` qui le tenait jouait
    `init --upgrade`, qui a désormais un parseur, et ce témoin-ci jouait
    `cadre hook`, public depuis T-00000862 ;
  * I5 — `cadre init --upgrade` reste RÉSERVÉ (code 2) et n'écrit rien ;
  * I6 — hors de tout projet, refus en 2, cause dite, aucun traceback ;
  * I7 — une racine divergente de `$CADRE_PROJECT_ROOT` est refusée par l'API,
    sans store créé d'un côté ni de l'autre ;
  * I8 — `cadre init --help` sort en 0, nomme `--host` et `--upgrade`, et
    n'écrit rien (changement de comportement assumé : 2 sur la base) ;
  * I9 — une racine ABSENTE (`$CADRE_PROJECT_ROOT` mal tapé) ou qui est un
    FICHIER est refusée avant toute écriture, par l'API comme par la CLI (code
    2, sans traceback) : ni l'arbre demandé ni la partition machine ne naissent ;
  * I10 — une racine ILLISIBLE (la `RuntimeError` « Symlink loop » que
    `Path.resolve()` lève en 3.11/3.12, dans `project_root()` ou dans
    `Workspace(...)`) est refusée en `CadrePathError` / code 2, sans traceback,
    rien créé. Le témoin passe par `mock.patch` pour ne pas dépendre de
    l'interpréteur ; une vraie boucle `a -> b -> a` est jouée EN PLUS, refusée
    quelle que soit la version (conversion en 3.11/3.12, ELOOP en 3.13+).

  * I11 — GOLDEN de `.agents/bin/project_init.py` (T-00000969, BK-121), posé
    AVANT son relogement dans `cadre.init` : le script en sous-processus, dans
    des dépôts git jetables, rend une transcription (rc, stdout, stderr, arbre
    et modes, contenu de `project.json`) normalisée (uuid, date, chemin
    jetable, cause d'un `OSError`) ÉGALE au littéral relevé sur 4431e767 —
    sauf le texte que fabrique argparse (aide, erreur), comparé par marqueurs,
    parce que la CI le joue sous 3.14 ET 3.12 (ci.yml:199, :379) et sur trois
    OS (ci.yml:154 : ubuntu, windows, macos ; colonne des modes omise sous
    Windows, `os.name == "nt"`). L'umask est forcé à 022 le temps du témoin.
    Divergences DÉCIDÉES : 0644 après `--rename` (decision/T-00000969/01) ;
    l'`env` json de `--print-otel-env` à une clé (T-01M4WNKCBXS893CHPSKD1Z1PN9).
  * I12–I19 — l'API relogée, EN PROCESSUS (`vider_cache_racine()` en setUp) :
    I12 slug ; I13 création, collision valide / corrompue, partiel ; I14
    `--rename` gèle id/slug/created, garde une clé héritée, repose 0644 même
    depuis 0600 ; I15 otel : la seule clé d'identité, JSON pur, `settings.json`
    jamais lu (lien hors racine : stderr vide) ; I16 board ×
    fournisseur (créé, présent, levant, absent) et `user.name` vide par
    `Executor` factice ; I17 `$CADRE_PROJECT_ROOT` (leurre) ignoré ; I18 `project_init.py` ne définit
    que `main`, `_BoardDuKit` et `_amorcer_cadre`, ré-exports ALIAS ; I19 (réserve C4)
    `project.json` lien hors racine refusé en 2 sans rien écrire, lien dans la
    racine : CIBLE réécrite (divergence documentée).
  * I20 — (exec-critic de T-00000969) un BOARD lien hors racine, fichier ou
    répertoire, est dit « board deja present — inchange », lien et cible
    INTACTS, comme la base — en processus ET de bout en bout par
    `project_init.py --ensure-stores` ; SANS board au bout (lien pendant,
    cible vide, `.agents/state` en lien), ATTENTION en 2, rien écrit
    (critic-opus, clôture) ; un répertoire parent de `project.json` lien hors
    racine est refusé en 2 à l'init, rien écrit dans la cible.
  * I21 — `.agents/kit.lock` lien hors racine jugé AU BOUT par la pierre
    tombale, comme la base : « présent » sur un fichier, « ABSENT » s'il pend
    ou boucle sur lui-même (3.11/3.12 compris, où `resolve` lève).

CE QUE CE BANC NE TIENT PAS : les surfaces de l'adoptant, les réglages natifs
par hôte et `kit.lock`, que ce tiers ne pose pas (BK-124, T-00000756) ; ni le
statut de `init` au verrou, tenu par `test_contract_diff.py`.

ISOLATION. Chaque projet vit dans un répertoire temporaire, sa partition
machine dans un dossier FRÈRE forcé par `CADRE_STATE_DIR` : rien n'est écrit
sous le vrai `state_home()`. La partition est elle-même un dépôt git jetable,
pour que son relevé passe par `git ls-files` comme celui du projet. La CLI est
lancée en sous-processus (`python -m cadre.cli`), `cwd` dans le projet, sur un
environnement PURGÉ : `GIT_*`, `CADRE_*`, `AGENTS_EVENTS_*`, `AGENTS_OTEL_DIR`
et `CLAUDE_PROJECT_DIR` retirés, configuration git globale et système
neutralisées. Les témoins en processus forcent leur environnement par
`_forcer_env` (valable sous `unittest` nu), et la fixture autouse n'est qu'un
second filet sous pytest. Sans `git` sur le poste, les témoins qui en ont
besoin SAUTENT et le disent.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VP = importlib.util.spec_from_file_location("_cadre_init_vp", ROOT / ".agents" / "bin" / "vendor_paths.py")
VENDOR = sys.modules[_SPEC_VP.name] = importlib.util.module_from_spec(_SPEC_VP)
_SPEC_VP.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")  # où vendor_paths le désigne, par chemin : rien en tête de sys.path

from cadre import cli  # noqa: E402
from cadre import init as module_init  # noqa: E402
from cadre import workspace as module_workspace  # noqa: E402
from cadre.executor import Resultat  # noqa: E402
from cadre.ledger import stores  # noqa: E402
from cadre.paths import CadrePathError, _git_toplevel, project_root, vider_cache_racine  # noqa: E402
from cadre.workspace import Workspace  # noqa: E402
import pytest  # noqa: E402

GIT = shutil.which("git")
SANS_GIT = "git absent du PATH : un projet NEUF est un `git init` réel, et ce témoin ne le simule pas"

#: Au-delà, un sous-processus est tenu pour bloqué.
DELAI = 120

_CONFIG_GIT = ("-c", "user.name=banc", "-c", "user.email=banc@exemple.invalid", "-c", "commit.gpgsign=false",
               "-c", f"core.hooksPath={os.devnull}", "-c", "init.defaultBranch=main")

#: Préfixes et noms retirés de l'environnement des sous-processus.
_PREFIXES_PURGES = ("GIT_", "CADRE_", "AGENTS_EVENTS_")
_NOMS_PURGES = ("AGENTS_OTEL_DIR", "CLAUDE_PROJECT_DIR", "PYTHONPATH")

#: Les trois stores, en suffixe de chemin : le relevé doit les porter TOUS.
_SUFFIXE_EVENTS = ".agents/state/local/events.db"
_SUFFIXES_PARTITION = ("/run/v3_event_store.db", "/index/index.db")


@pytest.fixture(autouse=True)
def _isolation_state_home(tmp_path, monkeypatch):
    """Second filet, sous pytest seulement : un témoin futur qui oublierait
    `_forcer_env` n'écrirait pas sous le vrai `state_home()`."""
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state_home"))


def _env_purge() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(_PREFIXES_PURGES) and k not in _NOMS_PURGES}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run([GIT, *_CONFIG_GIT, *args], cwd=cwd, env=_env_purge(),
                       capture_output=True, timeout=DELAI, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} -> rc={r.returncode}\n"
                             f"{r.stdout!r}{r.stderr!r}")
    return r.stdout.decode("utf-8")


def _releve(arbre: Path) -> dict[str, str]:
    """`{chemin relatif: sha256}` de tout fichier suivi OU non suivi de `arbre`
    (`git ls-files -z -co`, SANS `--exclude-standard` : rien n'est ignoré)."""
    noms = [n for n in _git(arbre, "ls-files", "-z", "-co").split("\0") if n]
    return {n: hashlib.sha256((arbre / n).read_bytes()).hexdigest() for n in noms}


def _cookie(chemin: Path) -> int:
    """Le `schema_version` lu dans l'EN-TÊTE (offset 40), sans connexion — donc
    sans créer de `-wal`/`-shm` qui fausserait le relevé suivant."""
    return int.from_bytes(chemin.read_bytes()[40:44], "big")


def _annexes(chemin: Path) -> list[str]:
    return [s for s in ("-wal", "-shm", "-journal") if Path(str(chemin) + s).exists()]


class _Banc(unittest.TestCase):
    """Fabriques et outils ; aucun témoin ici."""

    def _forcer_env(self, **kv: str | None) -> None:
        for cle, val in kv.items():
            ancienne = os.environ.get(cle)
            self.addCleanup(self._restaurer, cle, ancienne)
            if val is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = val

    @staticmethod
    def _restaurer(cle: str, ancienne: str | None) -> None:
        if ancienne is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = ancienne

    def _jetable(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="t968-")).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def _projet_neuf(self) -> tuple[Path, Path]:
        """(projet, partition) : un `git init` SANS `.agents/`, et sa partition
        machine, dossier frère, dépôt git jetable lui aussi (pour son relevé)."""
        base = self._jetable()
        projet, partition = base / "projet", base / "etat"
        projet.mkdir()
        partition.mkdir()
        _git(projet, "init", "-q")
        _git(partition, "init", "-q")
        return projet, partition

    def _cadre(self, cwd: Path, partition: Path, *args: str,
               env_en_plus: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = _env_purge()
        env["PYTHONPATH"] = str(VENDOR.parent_import(ROOT, "cadre"))
        env["CADRE_STATE_DIR"] = str(partition)
        env["CADRE_CONFIG_HOME"] = str(partition.parent / "conf")
        env.update(env_en_plus or {})
        return subprocess.run([sys.executable, "-m", "cadre.cli", *args],
                              cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=DELAI, check=False)

    def _assert_rien_ecrit(self, projet: Path, partition: Path) -> None:
        self.assertEqual(_releve(projet), {}, "le refus a écrit sous le projet")
        self.assertEqual(_releve(partition), {}, "le refus a écrit sous la partition")


@unittest.skipIf(GIT is None, SANS_GIT)
class ProjetNeufTests(_Banc):
    """I1 et I2, par la CLI réelle en sous-processus."""

    def test_I1_init_sur_un_projet_neuf_cree_les_trois_stores(self):
        projet, partition = self._projet_neuf()
        self.assertFalse((projet / ".agents").exists(), "projet pas neuf : .agents/ présent")
        self.assertEqual(_releve(projet), {}, "projet pas neuf : un fichier y est déjà")

        r = self._cadre(projet, partition, "init")

        self.assertEqual(r.returncode, 0, f"cadre init a refusé :\n{r.stderr}")
        self.assertNotIn("Traceback", r.stderr)
        # `split(None, 1)` : le chemin est le RESTE de la ligne — un `TMPDIR` qui
        # porte une espace serait sinon tronqué, et le témoin rougirait hors sujet.
        chemins = {ligne.split(None, 1)[0]: Path(ligne.split(None, 1)[1])
                   for ligne in r.stdout.splitlines() if ligne.startswith("  ")}
        self.assertEqual(sorted(chemins), ["events", "index", "v3_event_store"],
                         f"sortie inattendue :\n{r.stdout}")
        self.assertEqual(chemins["events"], projet / _SUFFIXE_EVENTS)
        for nom, chemin in chemins.items():
            with self.subTest(store=nom):
                self.assertTrue(chemin.is_file(), f"{nom} absent : {chemin}")
                self.assertTrue(chemin.read_bytes().startswith(b"SQLite format 3\x00"),
                                f"{nom} n'est pas une base SQLite")
                self.assertGreater(_cookie(chemin), 0, f"{nom} : aucun schéma posé")
                self.assertEqual(_annexes(chemin), [], f"{nom} : annexe résiduel")
        self.assertIn("PARTIEL", r.stdout, "le succès doit dire sa portée")

    def test_I2_deux_init_successifs_ne_produisent_aucun_diff(self):
        projet, partition = self._projet_neuf()
        r1 = self._cadre(projet, partition, "init")
        self.assertEqual(r1.returncode, 0, f"premier cadre init refusé :\n{r1.stderr}")
        avant = (_releve(projet), _releve(partition))
        # Non-vacuité : le relevé porte les TROIS stores, sinon l'égalité qui suit
        # comparerait deux arbres vides.
        self.assertIn(_SUFFIXE_EVENTS, avant[0])
        for suffixe in _SUFFIXES_PARTITION:
            self.assertEqual(sum(n.endswith(suffixe) for n in avant[1]), 1,
                             f"{suffixe} absent du relevé de la partition : {avant[1]}")

        r2 = self._cadre(projet, partition, "init")

        self.assertEqual(r2.returncode, 0, f"second cadre init refusé :\n{r2.stderr}")
        self.assertEqual(r2.stdout, r1.stdout)
        self.assertEqual(_releve(projet), avant[0], "le second init a changé le projet")
        self.assertEqual(_releve(partition), avant[1],
                         "le second init a changé la partition machine")


class ParCreerLesStoresTests(_Banc):
    """I1, seconde moitié : la création passe PAR `creer_les_stores`. Espion
    `wraps=` : l'appel réel a lieu, seul le passage est compté."""

    def test_I1_la_cli_cree_par_creer_les_stores(self):
        from cadre import init as module_init  # noqa: PLC0415

        racine = self._jetable()
        partition = racine.parent / (racine.name + "_etat")
        self.addCleanup(shutil.rmtree, partition, ignore_errors=True)
        self._forcer_env(CADRE_PROJECT_ROOT=str(racine), CADRE_STATE_DIR=str(partition),
                         AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None, AGENTS_OTEL_DIR=None)
        with mock.patch.object(module_init, "creer_les_stores",
                               wraps=stores.creer_les_stores) as espion, \
                mock.patch("sys.stdout"):
            rc = cli.main(["init"])

        self.assertEqual(rc, 0)
        espion.assert_called_once_with(project_root())
        self.assertTrue((racine / _SUFFIXE_EVENTS).is_file())


@unittest.skipIf(GIT is None, SANS_GIT)
class HoteTests(_Banc):
    """I3 — `--host` fermé par `HOTES`."""

    def test_I3_un_hote_de_la_liste_passe(self):
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "init", "--host", "claude")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hôte claude validé", r.stdout)
        self.assertTrue((projet / _SUFFIXE_EVENTS).is_file())

    def test_I3_un_hote_hors_liste_est_refuse_sans_rien_ecrire(self):
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "init", "--host", "antigravity")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("invalid choice", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self._assert_rien_ecrit(projet, partition)


class HoteApiTests(_Banc):
    """I3 par l'API : `choices` protège la CLI, `initialiser` se protège seul."""

    def test_I3_l_api_refuse_un_hote_hors_liste_avant_toute_ecriture(self):
        from cadre import init as module_init  # noqa: PLC0415
        from cadre.config import HoteInconnu  # noqa: PLC0415

        racine = self._jetable()
        self._forcer_env(CADRE_PROJECT_ROOT=str(racine),
                         CADRE_STATE_DIR=str(racine.parent / (racine.name + "_etat")))
        with mock.patch.object(module_init, "creer_les_stores") as espion:
            with self.assertRaises(HoteInconnu):
                module_init.initialiser(racine, hote="antigravity")
        espion.assert_not_called()


@unittest.skipIf(GIT is None, SANS_GIT)
class RefusTests(_Banc):
    """I4, I5, I6 — trois refus en 2, aucun n'écrit."""

    def test_I4_une_option_surnumeraire_est_refusee(self):
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "init", "--hots", "claude")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("inconnue", r.stderr)
        self._assert_rien_ecrit(projet, partition)

    def test_I4b_un_drapeau_d_un_AUTRE_nom_reserve_reste_tolere(self):
        """La raison d'être de `parse_known_args` : un nom réservé SANS parseur
        laisse passer ses arguments et dit « RÉSERVÉ ». Refuser les options en
        trop pour TOUS les noms le ferait sortir sur « inconnue ». `hosts` et non
        plus `hook` : `cadre hook` a un parseur et est public depuis T-00000862
        (piège 2 de PLANNING_TRAPS — ce filet l'épinglait réservé). Le DRAPEAU
        `--dry-run` est ce que le nom du témoin promet : sans lui, seuls des
        positionnels passaient, et un refus des seules options en trop pour tous
        les noms restait vert (revue de clôture commune)."""
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "hosts", "add", "codex", "--dry-run")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("RÉSERVÉ", r.stderr)
        self.assertNotIn("inconnue", r.stderr)
        self._assert_rien_ecrit(projet, partition)

    def test_I5_upgrade_reste_reserve_et_n_ecrit_rien(self):
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "init", "--upgrade")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("RÉSERVÉ", r.stderr)
        self.assertNotIn("inconnue", r.stderr)
        self._assert_rien_ecrit(projet, partition)

    def test_I6_hors_de_tout_projet_refus_en_2_sans_traceback(self):
        dehors = self._jetable()
        partition = dehors.parent / (dehors.name + "_etat")
        self.addCleanup(shutil.rmtree, partition, ignore_errors=True)
        try:
            project_root(depuis=dehors)
        except CadrePathError:
            pass
        else:
            self.skipTest(f"SAUT ANNONCÉ : {dehors} a un ancêtre git ou .agents/ "
                          "(TMPDIR sous un dépôt) — « hors projet » n'y est pas jouable")
        r = self._cadre(dehors, partition, "init")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("racine de projet introuvable", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(sorted(p.name for p in dehors.iterdir()), [],
                         "le refus a écrit dans le répertoire courant")
        self.assertFalse(partition.exists(), "le refus a écrit sous la partition")


@unittest.skipIf(GIT is None, SANS_GIT)
class AideTests(_Banc):
    """I8 — `cadre init` a un vrai parseur : son aide sort en 0, sans écrire."""

    def test_I8_init_help_sort_en_0_et_n_ecrit_rien(self):
        projet, partition = self._projet_neuf()
        r = self._cadre(projet, partition, "init", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        for option in ("--host", "--upgrade"):
            with self.subTest(option=option):
                self.assertIn(option, r.stdout)
        self._assert_rien_ecrit(projet, partition)


class RacineAbsenteTests(_Banc):
    """I9 — `project_root` rend `$CADRE_PROJECT_ROOT` sans en vérifier
    l'existence, et `creer_les_stores` crée les parents d'un store : sans la
    garde d'`initialiser`, une racine mal tapée faisait naître un arbre entier
    et sa partition, code 0 (mesuré)."""

    def _cas(self) -> list[tuple[str, Path, Path, Path]]:
        """(nom, base, racine demandée, partition) : une racine ABSENTE sous un
        parent absent, et une racine qui est un FICHIER régulier."""
        cas = []
        base = self._jetable()
        cas.append(("absente", base, base / "nexistepas" / "sous", base / "etat"))
        base_f = self._jetable()
        fichier = base_f / "un_fichier"
        fichier.write_bytes(b"pas un projet\n")
        cas.append(("fichier", base_f, fichier, base_f / "etat"))
        return cas

    def _assert_rien_ne_nait(self, base: Path, partition: Path) -> None:
        self.assertFalse((base / "nexistepas").exists(), "l'arbre demandé est né")
        self.assertFalse(partition.exists(), "la partition machine est née")

    def test_I9_l_api_refuse_une_racine_absente_ou_fichier(self):
        from cadre import init as module_init  # noqa: PLC0415

        for nom, base, racine, partition in self._cas():
            with self.subTest(cas=nom):
                self._forcer_env(CADRE_PROJECT_ROOT=str(racine),
                                 CADRE_STATE_DIR=str(partition))
                with self.assertRaises(CadrePathError) as ctx:
                    module_init.initialiser()
                self.assertIn("introuvable ou n'est pas un répertoire",
                              str(ctx.exception))
                self._assert_rien_ne_nait(base, partition)

    def test_I9_la_cli_refuse_une_racine_absente_ou_fichier_en_2(self):
        for nom, base, racine, partition in self._cas():
            with self.subTest(cas=nom):
                r = self._cadre(base, partition, "init",
                                env_en_plus={"CADRE_PROJECT_ROOT": str(racine)})
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("introuvable ou n'est pas un répertoire", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self._assert_rien_ne_nait(base, partition)


class RacineIllisibleTests(_Banc):
    """I10 — la `RuntimeError` de `Path.resolve()` sur une boucle de liens
    (3.11/3.12) ne remonte JAMAIS en traceback."""

    _BOUCLE = RuntimeError("Symlink loop from '/x/a'")

    def _racine_et_partition(self) -> tuple[Path, Path]:
        racine = self._jetable()
        partition = racine.parent / (racine.name + "_etat")
        self.addCleanup(shutil.rmtree, partition, ignore_errors=True)
        self._forcer_env(CADRE_PROJECT_ROOT=str(racine), CADRE_STATE_DIR=str(partition),
                         AGENTS_EVENTS_DIR=None, AGENTS_EVENTS_DB=None, AGENTS_OTEL_DIR=None)
        return racine, partition

    def _boucle(self) -> Path:
        """`a -> b -> a` sous un jetable ; SAUT annoncé si le poste refuse les
        liens symboliques (Windows sans privilège)."""
        base = self._jetable()
        try:
            os.symlink(base / "b", base / "a")
            os.symlink(base / "a", base / "b")
        except OSError as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique refusé par le poste ({exc})")
        return base / "a"

    def _assert_rien_cree(self, racine: Path, partition: Path) -> None:
        self.assertFalse((racine / ".agents").exists(), "un store est né sous la racine")
        self.assertFalse(partition.exists(), "la partition machine est née")

    def test_I10_l_api_convertit_la_runtimeerror_en_cadrepatherror(self):
        from cadre import init as module_init  # noqa: PLC0415

        with self.subTest(site="Workspace"):
            racine, partition = self._racine_et_partition()
            with mock.patch.object(Workspace, "__init__", side_effect=self._BOUCLE):
                with self.assertRaises(CadrePathError) as ctx:
                    module_init.initialiser(racine)
            self.assertIn("illisible (RuntimeError: Symlink loop", str(ctx.exception))
            self._assert_rien_cree(racine, partition)
        with self.subTest(site="project_root"):
            racine, partition = self._racine_et_partition()
            with mock.patch.object(module_init, "project_root", side_effect=self._BOUCLE):
                with self.assertRaises(CadrePathError) as ctx:
                    module_init.initialiser()
            self.assertIn("illisible (RuntimeError: Symlink loop", str(ctx.exception))
            self._assert_rien_cree(racine, partition)
        with self.subTest(site="boucle réelle"):
            racine, partition = self._racine_et_partition()
            with self.assertRaises(CadrePathError):
                module_init.initialiser(self._boucle())
            self.assertFalse(partition.exists(), "la partition machine est née")

    def test_I10_la_cli_refuse_en_2_sans_traceback(self):
        with self.subTest(voie="en processus, Workspace mocké"):
            racine, partition = self._racine_et_partition()
            erreur = io.StringIO()
            with mock.patch.object(Workspace, "__init__", side_effect=self._BOUCLE), \
                    mock.patch("sys.stderr", erreur), mock.patch("sys.stdout"):
                rc = cli.main(["init"])
            self.assertEqual(rc, 2, erreur.getvalue())
            self.assertIn("illisible (RuntimeError: Symlink loop", erreur.getvalue())
            self._assert_rien_cree(racine, partition)
        with self.subTest(voie="sous-processus, boucle réelle"):
            boucle = self._boucle()
            partition = boucle.parent / "etat"
            r = self._cadre(boucle.parent, partition, "init",
                            env_en_plus={"CADRE_PROJECT_ROOT": str(boucle)})
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse(partition.exists(), "la partition machine est née")


class RacineDivergenteTests(_Banc):
    """I7 — l'API transmet la racine TELLE QUELLE : `$CADRE_PROJECT_ROOT` qui
    pointe ailleurs fait REFUSER, jamais créer en silence chez l'autre."""

    def test_I7_une_racine_divergente_est_refusee_sans_rien_creer(self):
        from cadre import init as module_init  # noqa: PLC0415

        a, b = self._jetable(), self._jetable()
        partition = a.parent / (a.name + "_etat")
        self.addCleanup(shutil.rmtree, partition, ignore_errors=True)
        self._forcer_env(CADRE_PROJECT_ROOT=str(a), CADRE_STATE_DIR=str(partition))
        with self.assertRaises(CadrePathError) as ctx:
            module_init.initialiser(b)
        self.assertIn("racine demandée", str(ctx.exception))
        self.assertIn("aucun store n'est créé", str(ctx.exception))
        for racine in (a, b):
            with self.subTest(racine=racine.name):
                self.assertFalse((racine / _SUFFIXE_EVENTS).exists(),
                                 f"un store est né sous {racine}")
        self.assertFalse(partition.exists(), "un store est né sous la partition")


# --- I11 : GOLDEN de project_init.py (T-00000969) ------------------------------

PROJECT_INIT = ROOT / ".agents" / "bin" / "project_init.py"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
#: La cause d'un board non provisionné est le texte d'un `OSError` de la
#: plateforme : comparée par son MARQUEUR, jamais mot pour mot (C2).
_CAUSE = re.compile(r"(ATTENTION — board non provisionne \().*(\) ; lancer: )")
_ARGPARSE = "<texte d'argparse, comparé par marqueurs>"
_MODE = re.compile(r" [0-7]{4}$", re.MULTILINE)

#: Ce que l'aide doit nommer, espaces normalisés (argparse replie à COLUMNS).
_AIDE = (
    "usage: project_init.py",
    "Generate or update a project's immutable identity (.agents/state/project.json).",
    "--name NAME", "--rename RENAME", "--print-otel-env", "--ensure-stores",
    "--format {shell,json,both}",
    "Project name STORED in project.json:name at init (else prompted "
    "interactively). NOT the displayed name since T-00000582: the dashboard "
    "shows the repo directory basename.",
    "Rewrite the STORED human name ONLY (slug/id/created frozen). Does NOT "
    "change what the dashboard displays since T-00000582 (that is the "
    "directory basename).",
    "Print the paste-ready OTEL_RESOURCE_ATTRIBUTES block carrying this "
    "project's real project_id (V1-c canal-B attribution). READ-ONLY.",
    "Provision the state stores an init provisions (today: the task board), "
    "WITHOUT touching the identity. Idempotent, never overwrites — the repair "
    "gesture for a project inited before this flag existed.",
    "Form of the --print-otel-env output: 'shell' for direnv/profile, 'json' "
    "for .claude/settings.local.json (pure, parsable), 'both' (default) for "
    "the shell block followed by the JSON one.",
)

#: Relevé sur 4431e767 (Python 3.14.7, darwin, umask 022). Voir I11 en tête.
#: DEUX divergences, voulues : après `--rename` (g04, puis les états g08 et g13
#: du même fichier) `project.json` reste en 0644 — la base le passait en 0600,
#: artefact de `mkstemp` ; décision pilote, tag git decision/T-00000969/01 (0644
#: partout) (T-00000969). Et l'`env` json de `--print-otel-env` (g05, g06, g08,
#: g09) ne porte que la clé d'identité (T-01M4WNKCBXS893CHPSKD1Z1PN9).
_GOLDEN = r"""## g01 [a] project_init.py --help
rc 0
stdout: <texte d'argparse, comparé par marqueurs>
stderr: ∅
état: vide
## g02 [a] project_init.py --name 'Mon Projet Été'
rc 0
stdout:
  | project_init: identité créée — Mon Projet Été (project_id=<UUID>, slug=mon-projet-t)
  | board cree: .agents/state/board/TASKS.json (+ vue .agents/state/local/TASKS.md, git-ignoree)
  | RESTE A FAIRE : /index · /skills-sync
  | magasins paresseux (normaux a l absence) : v3_event_store.db · index.db (machine, hors depot : state_project()/index/index.db)
stderr:
  | project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le basename du répertoire du dépôt, pas ce champ ; --name (ou l'invite) ne remplit que project.json:name, écrit et NON affiché. Pour choisir le nom affiché, nommez le répertoire du dépôt.
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
  .agents/state/project.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Mon Projet Été",
  =   "slug": "mon-projet-t",
  =   "created": "<DATE>"
  = }
## g03 [a] project_init.py --name Autre
rc 2
stdout: ∅
stderr:
  | project_init: identité déjà initialisée (project_id=<UUID> ; si héritée d'un clone/fork, supprimer .agents/state/project.json puis ré-initer)
état inchangé
## g04 [a] project_init.py --rename '  Projet Renommé  '
rc 0
stdout:
  | project_init: name -> Projet Renommé (slug inchangé: mon-projet-t)
stderr:
  | project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le basename du répertoire du dépôt, pas ce champ ; --rename ne change plus l'affichage. Pour renommer le projet affiché, renommez son répertoire.
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
  .agents/state/project.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Projet Renommé",
  =   "slug": "mon-projet-t",
  =   "created": "<DATE>"
  = }
## g05 [a] project_init.py --print-otel-env
rc 0
stdout:
  | # agentkit — attribution canal B pour « Projet Renommé »
  | # Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.
  | # Per-clone et jamais tracké : le project_id est git-ignoré.
  | OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<UUID>
  |
  | # — ou, pour Claude Code, dans .claude/settings.local.json :
  | {
  |   "env": {
  |     "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=<UUID>"
  |   }
  | }
stderr: ∅
état inchangé
## g06 [a] project_init.py --print-otel-env --format json
rc 0
stdout:
  | {
  |   "env": {
  |     "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=<UUID>"
  |   }
  | }
stderr: ∅
état inchangé
## g07 [a] project_init.py --print-otel-env --format shell
rc 0
stdout:
  | # agentkit — attribution canal B pour « Projet Renommé »
  | # Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.
  | # Per-clone et jamais tracké : le project_id est git-ignoré.
  | OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<UUID>
stderr: ∅
état inchangé
## g08 [a] project_init.py --print-otel-env
rc 0
stdout:
  | # agentkit — attribution canal B pour « Projet Renommé »
  | # Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.
  | # Per-clone et jamais tracké : le project_id est git-ignoré.
  | OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<UUID>
  |
  | # — ou, pour Claude Code, dans .claude/settings.local.json :
  | {
  |   "env": {
  |     "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=<UUID>"
  |   }
  | }
stderr: ∅
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
  .agents/state/project.json 0644
  .claude/ 0755
  .claude/settings.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Projet Renommé",
  =   "slug": "mon-projet-t",
  =   "created": "<DATE>"
  = }
## g09 [a] project_init.py --print-otel-env --format json
rc 0
stdout:
  | {
  |   "env": {
  |     "OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=<UUID>"
  |   }
  | }
stderr: ∅
état inchangé
## g10 [a] project_init.py --print-otel-env --format shell
rc 0
stdout:
  | # agentkit — attribution canal B pour « Projet Renommé »
  | # Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.
  | # Per-clone et jamais tracké : le project_id est git-ignoré.
  | OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<UUID>
stderr: ∅
état inchangé
## g11 [a] project_init.py --ensure-stores
rc 0
stdout:
  | board deja present — inchange
  | RESTE A FAIRE : /index · /skills-sync
  | magasins paresseux (normaux a l absence) : v3_event_store.db · index.db (machine, hors depot : state_project()/index/index.db)
stderr: ∅
état inchangé
## g12 [a] project_init.py --stamp-kit-version
rc 2
stdout: ∅
stderr:
  | project_init: --stamp-kit-version RETIRÉ (T-00000594) — la version du kit vit dans .agents/kit.lock (clé version_kit, ABSENT ici — arbre copié à la main ou antérieur à T-00000705) ; retire ce drapeau.
état inchangé
## g13 [a] project_init.py --stamp-kit-version v9
rc 2
stdout: ∅
stderr:
  | project_init: --stamp-kit-version RETIRÉ (T-00000594) — la version du kit vit dans .agents/kit.lock (clé version_kit, présent) ; retire ce drapeau.
état:
  .agents/ 0755
  .agents/kit.lock 0644
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
  .agents/state/project.json 0644
  .claude/ 0755
  .claude/settings.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Projet Renommé",
  =   "slug": "mon-projet-t",
  =   "created": "<DATE>"
  = }
## g14 [a] project_init.py --stamp-kit-version --inconnu
rc 2
stdout: ∅
stderr:
  | project_init: --stamp-kit-version RETIRÉ (T-00000594) — la version du kit vit dans .agents/kit.lock (clé version_kit, présent) ; retire ce drapeau.
état inchangé
## g15 [a] project_init.py --rename X --print-otel-env --format shell
rc 0
stdout:
  | # agentkit — attribution canal B pour « Projet Renommé »
  | # Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.
  | # Per-clone et jamais tracké : le project_id est git-ignoré.
  | OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<UUID>
stderr: ∅
état inchangé
## g16 [a] project_init.py --bogus
rc 2
stdout: ∅
stderr: <texte d'argparse, comparé par marqueurs>
état inchangé
## g17 [a] project_init.py --rename '   '
rc 2
stdout: ∅
stderr:
  | project_init: le nouveau nom ne peut pas être vide (--rename)
état inchangé
## g18 [b] project_init.py  < 'Lu Sur Stdin\n'
rc 0
stdout:
  | Nom du projet : project_init: identité créée — Lu Sur Stdin (project_id=<UUID>, slug=lu-sur-stdin)
  | board cree: .agents/state/board/TASKS.json (+ vue .agents/state/local/TASKS.md, git-ignoree)
  | RESTE A FAIRE : /index · /skills-sync
  | magasins paresseux (normaux a l absence) : v3_event_store.db · index.db (machine, hors depot : state_project()/index/index.db)
stderr:
  | project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le basename du répertoire du dépôt, pas ce champ ; --name (ou l'invite) ne remplit que project.json:name, écrit et NON affiché. Pour choisir le nom affiché, nommez le répertoire du dépôt.
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
  .agents/state/project.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Lu Sur Stdin",
  =   "slug": "lu-sur-stdin",
  =   "created": "<DATE>"
  = }
## g19 [c] project_init.py --name X
rc 2
stdout: ∅
stderr:
  | project_init: project.json présent mais corrompu (écriture partielle ?) — supprimer .agents/state/project.json puis ré-initer
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/project.json 0644
  = {"name": "tronqu
## g20 [c] project_init.py --rename Y
rc 2
stdout: ∅
stderr:
  | project_init: project.json présent mais corrompu (écriture partielle ?) — supprimer .agents/state/project.json puis ré-initer
état inchangé
## g21 [c] project_init.py --print-otel-env
rc 2
stdout: ∅
stderr:
  | project_init: aucune identité à publier (.agents/state/project.json absent ou corrompu) — lancer d'abord: python .agents/bin/project_init.py
état inchangé
## g22 [d] project_init.py --rename Y
rc 2
stdout: ∅
stderr:
  | project_init: aucune identité à modifier (.agents/state/project.json absent) — lancer d'abord: python .agents/bin/project_init.py
état: vide
## g23 [d] project_init.py --print-otel-env --format json
rc 2
stdout: ∅
stderr:
  | project_init: aucune identité à publier (.agents/state/project.json absent ou corrompu) — lancer d'abord: python .agents/bin/project_init.py
état inchangé
## g24 [d] project_init.py --name '   '
rc 2
stdout: ∅
stderr:
  | project_init: le nom du projet ne peut pas être vide (--name)
état inchangé
## g25 [d] project_init.py --ensure-stores --name Y
rc 0
stdout:
  | board cree: .agents/state/board/TASKS.json (+ vue .agents/state/local/TASKS.md, git-ignoree)
  | RESTE A FAIRE : /index · /skills-sync
  | magasins paresseux (normaux a l absence) : v3_event_store.db · index.db (machine, hors depot : state_project()/index/index.db)
stderr: ∅
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board/ 0755
  .agents/state/board/TASKS.json 0644
  .agents/state/local/ 0755
  .agents/state/local/TASKS.md 0644
## g26 [e] project_init.py --name X
rc 2
stdout: ∅
stderr:
  | project_init: git user.name est vide — configure git user.name avant d'initialiser (git config user.name "Ton Nom")
état: vide
## g27 [f] project_init.py --name Adoptant
rc 0
stdout:
  | project_init: identité créée — Adoptant (project_id=<UUID>, slug=adoptant)
stderr:
  | project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le basename du répertoire du dépôt, pas ce champ ; --name (ou l'invite) ne remplit que project.json:name, écrit et NON affiché. Pour choisir le nom affiché, nommez le répertoire du dépôt.
  | ATTENTION — board non provisionne (<CAUSE>) ; lancer: python3 .agents/bin/project_init.py --ensure-stores
état:
  .agents/ 0755
  .agents/state/ 0755
  .agents/state/board 0644
  .agents/state/project.json 0644
  = {
  =   "project_id": "<UUID>",
  =   "name": "Adoptant",
  =   "slug": "adoptant",
  =   "created": "<DATE>"
  = }
## g28 [f] project_init.py --ensure-stores
rc 2
stdout: ∅
stderr:
  | ATTENTION — board non provisionne (<CAUSE>) ; lancer: python3 .agents/bin/project_init.py --ensure-stores
état inchangé
## leurre $CADRE_PROJECT_ROOT : vide
## partition machine : vide
## événements : vide
"""


@unittest.skipIf(GIT is None, SANS_GIT)
class ProjectInitGoldenTests(_Banc):
    """I11 — `project_init.py` rend, geste pour geste, le relevé de la base.

    Écrit AVANT le relogement (T-00000969) pour qu'il le juge : un caractère
    de message, un canal, un code de sortie, un mode ou un fichier de plus ou
    de moins fait rougir le littéral. `$CADRE_PROJECT_ROOT` pointe un LEURRE
    que la racine git doit battre ; la partition machine et les événements
    sont forcés dans le jetable, et les deux sont relevés vides à la fin."""

    maxDiff = None

    def _depot(self, nom: str, *, user: bool = True) -> Path:
        d = self._base / nom
        d.mkdir()
        _git(d, "init", "-q")
        if user:
            _git(d, "config", "user.name", "banc")
        return d

    def _normaliser(self, texte: str) -> str:
        texte = texte.replace(str(self._base), "<BASE>")
        texte = _CAUSE.sub(r"\1<CAUSE>\2", _DATE.sub("<DATE>", _UUID.sub("<UUID>", texte)))
        return texte

    @staticmethod
    def _bloc(titre: str, texte: str) -> list[str]:
        if not texte:
            return [f"{titre}: ∅"]
        morceaux = texte.split("\n")
        reste = morceaux.pop()
        # Une ligne vide rend `  |` sans espace final : le littéral n'en porte aucun.
        lignes = [f"{titre}:", *(f"  | {m}" if m else "  |" for m in morceaux)]
        if reste:
            lignes.append(f"  | {reste}  ⟂ sans fin de ligne")
        return lignes

    def _etat(self, depot: Path) -> list[str]:
        lignes = []
        for p in sorted(depot.rglob("*"), key=lambda q: q.relative_to(depot).as_posix()):
            rel = p.relative_to(depot).as_posix()
            if rel.split("/")[0] == ".git":
                continue
            mode = "----" if os.name == "nt" else f"{stat.S_IMODE(p.lstat().st_mode):04o}"
            lignes.append(f"  {rel}{'/' if p.is_dir() else ''} {mode}")
        ident = depot / ".agents" / "state" / "project.json"
        if ident.is_file():
            contenu = self._normaliser(ident.read_text(encoding="utf-8"))
            lignes += [f"  = {ligne}" for ligne in contenu.splitlines()]
        return lignes

    def _jouer(self, cle: str, depot: Path, *args: str, stdin: str = "",
               argparse_sur: str | None = None) -> None:
        r = subprocess.run([sys.executable, str(PROJECT_INIT), *args], cwd=depot,
                           env=self._env, input=stdin, capture_output=True, text=True,
                           encoding="utf-8", timeout=DELAI, check=False)
        self._bruts[cle] = r
        entree = f" < {stdin!r}" if stdin else ""
        self._lignes += [f"## {cle} [{depot.name}] project_init.py {shlex.join(args)}{entree}",
                         f"rc {r.returncode}"]
        for canal in ("stdout", "stderr"):
            if canal == argparse_sur:
                self._lignes.append(f"{canal}: {_ARGPARSE}")
            else:
                self._lignes += self._bloc(canal, self._normaliser(getattr(r, canal)))
        etat = self._etat(depot)
        if etat == self._derniers.get(depot.name):
            self._lignes.append("état inchangé")
        else:
            self._lignes += ["état:", *etat] if etat else ["état: vide"]
            self._derniers[depot.name] = etat

    def _transcrire(self) -> str:
        self._base = self._jetable()
        self._lignes: list[str] = []
        self._bruts: dict[str, subprocess.CompletedProcess] = {}
        self._derniers: dict[str, list[str]] = {}
        leurre, machine, evenements = (self._base / n for n in ("leurre", "etat", "ev"))
        for d in (leurre, machine, evenements):
            d.mkdir()
        self._env = _env_purge()
        self._env.pop("FORCE_COLOR", None)
        self._env.update(COLUMNS="80", PYTHONIOENCODING="utf-8", NO_COLOR="1",
                         PYTHON_COLORS="0", CADRE_PROJECT_ROOT=str(leurre),
                         CADRE_STATE_DIR=str(machine), AGENTS_EVENTS_DIR=str(evenements))
        jouer = self._jouer

        a = self._depot("a")
        jouer("g01", a, "--help", argparse_sur="stdout")
        jouer("g02", a, "--name", "Mon Projet Été")
        jouer("g03", a, "--name", "Autre")
        jouer("g04", a, "--rename", "  Projet Renommé  ")
        jouer("g05", a, "--print-otel-env")
        jouer("g06", a, "--print-otel-env", "--format", "json")
        jouer("g07", a, "--print-otel-env", "--format", "shell")
        (a / ".claude").mkdir()
        (a / ".claude" / "settings.json").write_text(json.dumps({"env": {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_METRIC_EXPORT_INTERVAL": "10000",
            "NOMBRE": 5}}), encoding="utf-8")
        jouer("g08", a, "--print-otel-env")
        jouer("g09", a, "--print-otel-env", "--format", "json")
        jouer("g10", a, "--print-otel-env", "--format", "shell")
        jouer("g11", a, "--ensure-stores")
        jouer("g12", a, "--stamp-kit-version")
        (a / ".agents" / "kit.lock").write_text('{"version_kit": "0.0.0"}\n', encoding="utf-8")
        jouer("g13", a, "--stamp-kit-version", "v9")
        jouer("g14", a, "--stamp-kit-version", "--inconnu")
        jouer("g15", a, "--rename", "X", "--print-otel-env", "--format", "shell")
        jouer("g16", a, "--bogus", argparse_sur="stderr")
        jouer("g17", a, "--rename", "   ")

        b = self._depot("b")
        jouer("g18", b, stdin="Lu Sur Stdin\n")

        c = self._depot("c")
        (c / ".agents" / "state").mkdir(parents=True)
        (c / ".agents" / "state" / "project.json").write_text('{"name": "tronqu', encoding="utf-8")
        jouer("g19", c, "--name", "X")
        jouer("g20", c, "--rename", "Y")
        jouer("g21", c, "--print-otel-env")

        d = self._depot("d")
        jouer("g22", d, "--rename", "Y")
        jouer("g23", d, "--print-otel-env", "--format", "json")
        jouer("g24", d, "--name", "   ")
        jouer("g25", d, "--ensure-stores", "--name", "Y")

        e = self._depot("e", user=False)
        jouer("g26", e, "--name", "X")

        f = self._depot("f")
        (f / ".agents" / "state").mkdir(parents=True)
        (f / ".agents" / "state" / "board").write_text("", encoding="utf-8")
        jouer("g27", f, "--name", "Adoptant")
        jouer("g28", f, "--ensure-stores")

        for nom, d in (("leurre $CADRE_PROJECT_ROOT", leurre), ("partition machine", machine),
                       ("événements", evenements)):
            contenu = sorted(p.relative_to(d).as_posix() for p in d.rglob("*"))
            self._lignes.append(f"## {nom} : {', '.join(contenu) or 'vide'}")
        return "\n".join(self._lignes) + "\n"

    def test_I11_project_init_rend_le_releve_de_la_base(self):
        ancien = os.umask(0o022)
        self.addCleanup(os.umask, ancien)
        transcription = self._transcrire()
        attendu = _GOLDEN if os.name != "nt" else _MODE.sub(" ----", _GOLDEN)
        with self.subTest(volet="littéral"):
            self.assertEqual(transcription, attendu)
        with self.subTest(volet="aide (argparse, par marqueurs)"):
            r = self._bruts["g01"]
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            aide = " ".join(r.stdout.split())
            for marqueur in _AIDE:
                self.assertIn(marqueur, aide)
            self.assertNotIn("stamp-kit-version", aide)
        with self.subTest(volet="drapeau inconnu (argparse, par marqueurs)"):
            r = self._bruts["g16"]
            self.assertEqual((r.returncode, r.stdout), (2, ""))
            self.assertIn("usage: project_init.py", r.stderr)
            self.assertIn("error: unrecognized arguments: --bogus", r.stderr)
        for cle in ("g27", "g28"):
            with self.subTest(volet=f"cause nommée, non vide ({cle})"):
                cause = re.search(r"ATTENTION — board non provisionne \(([^\n]*)\) ; lancer: ",
                                  self._bruts[cle].stderr)
                self.assertIsNotNone(cause, self._bruts[cle].stderr)
                self.assertTrue(cause.group(1).strip())


# --- I12–I19 : l'API relogée, en processus (T-00000969) -----------------------

_IDENT = Path(".agents") / "state" / "project.json"


class _ExecuteurFactice:
    """`Executor` factice : rend `resultat`, compte les appels."""

    def __init__(self, resultat: Resultat):
        self.resultat, self.appels = resultat, []

    def run(self, argv, *, cwd=None, env=None, timeout=None) -> Resultat:
        self.appels.append((tuple(argv), cwd, timeout))
        return self.resultat


def _auteur(nom: str = "banc", code: int = 0) -> _ExecuteurFactice:
    return _ExecuteurFactice(Resultat(argv=("git",), code=code, stdout=f"{nom}\n", stderr=""))


class _BoardFactice:
    """`FournisseurBoard` factice : `leve` non nul fait échouer `creer`."""

    def __init__(self, leve: BaseException | None = None):
        self.leve, self.crees = leve, []

    def chemins(self, racine: Path) -> tuple[Path, Path]:
        return racine / "b" / "TASKS.json", racine / "v" / "TASKS.md"

    def creer(self, racine: Path) -> None:
        if self.leve is not None:
            raise self.leve
        self.crees.append(racine)
        (racine / "b").mkdir()
        (racine / "b" / "TASKS.json").write_text("{}\n", encoding="utf-8")


class _BancIdentite(_Banc):
    def setUp(self):
        vider_cache_racine()
        self.addCleanup(vider_cache_racine)
        self.racine = self._jetable()
        self.atelier = Workspace(self.racine)

    def _appeler(self, fn, *args, **kwargs):
        """(retour ou exception levée, stdout, stderr) de `fn` en processus."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            try:
                rendu = fn(*args, **kwargs)
            except module_init.RefusIdentite as refus:
                rendu = refus
        return rendu, out.getvalue(), err.getvalue()

    def _poser(self, donnees: dict | str, rel: Path = _IDENT) -> Path:
        chemin = self.racine / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        texte = donnees if isinstance(donnees, str) else json.dumps(donnees)
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def _lien(self, vise: Path, lien: Path) -> Path:
        lien.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(vise, lien)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique refusé par le poste ({exc})")
        return lien


class SlugTests(_BancIdentite):
    """I12 — le slug, clé gelée : jamais vide, jamais hors `[a-z0-9-]`."""

    def test_I12_slugifier(self):
        for nom, attendu in (("My Cool Project", "my-cool-project"),
                             ("  Été 2026 !  ", "t-2026"), ("a__B..c", "a-b-c"),
                             ("---", "project"), ("", "project")):
            with self.subTest(nom=nom):
                self.assertEqual(module_init.slugifier(nom), attendu)


class CreationTests(_BancIdentite):
    """I13 — création exclusive, deux diagnostics de collision, nom demandé."""

    def test_I13_creation_puis_collision_valide(self):
        auteur, board = _auteur(), _BoardFactice()
        rc, out, err = self._appeler(module_init.initialiser_identite, self.atelier,
                                     "  Mon Projet ", board=board, executeur=auteur)
        self.assertEqual(rc, 0, err)
        ident = json.loads((self.racine / _IDENT).read_text(encoding="utf-8"))
        self.assertEqual(sorted(ident), ["created", "name", "project_id", "slug"])
        self.assertEqual((ident["name"], ident["slug"]), ("Mon Projet", "mon-projet"))
        self.assertRegex(ident["project_id"], _UUID)
        self.assertRegex(ident["created"], _DATE)
        self.assertEqual(auteur.appels, [(("git", "config", "user.name"), self.racine, 5)])
        self.assertEqual(board.crees, [self.racine])
        self.assertIn("identité créée — Mon Projet", out)
        self.assertIn("AVERTISSEMENT", err)
        avant = (self.racine / _IDENT).read_bytes()

        refus, out, _err = self._appeler(module_init.initialiser_identite, self.atelier,
                                         "Autre", board=board, executeur=auteur)
        self.assertIsInstance(refus, module_init.RefusIdentite)
        self.assertIn(f"identité déjà initialisée (project_id={ident['project_id']} ;",
                      str(refus))
        self.assertEqual((self.racine / _IDENT).read_bytes(), avant)
        self.assertEqual((out, board.crees), ("", [self.racine]), "le board a été rejoué")

    def test_I13_collision_corrompue_et_nom_vide(self):
        self._poser('{"name": "tronqu')
        refus, _out, _err = self._appeler(module_init.initialiser_identite, self.atelier,
                                          "X", board=_BoardFactice(), executeur=_auteur())
        self.assertEqual(str(refus), module_init._CORROMPU)
        self.assertEqual((self.racine / _IDENT).read_text(encoding="utf-8"), '{"name": "tronqu')
        vierge = Workspace(self._jetable())
        refus, _out, _err = self._appeler(module_init.initialiser_identite, vierge, "   ",
                                          board=_BoardFactice(), executeur=_auteur())
        self.assertEqual(str(refus), "le nom du projet ne peut pas être vide (--name)")
        self.assertEqual(list(vierge.racine.iterdir()), [])

    def test_I13_nom_absent_est_DEMANDE(self):
        invites: list[str] = []

        def demander(invite: str) -> str:
            invites.append(invite)
            return "  Lu Ici \n"

        rc, _out, _err = self._appeler(module_init.initialiser_identite, self.atelier, None,
                                       board=_BoardFactice(), executeur=_auteur(),
                                       demander=demander)
        self.assertEqual((rc, invites), (0, ["Nom du projet : "]))
        ident = json.loads((self.racine / _IDENT).read_text(encoding="utf-8"))
        self.assertEqual(ident["name"], "Lu Ici")

    def test_I13_creer_identite_exclusive_contrat_herite(self):
        chemin = module_init.chemin_identite(self.racine)
        self.assertEqual(chemin, self.racine / ".agents" / "state" / "project.json")
        module_init.creer_identite_exclusive(chemin, {"project_id": "x", "name": "é"})
        self.assertEqual(chemin.read_bytes(),
                         '{\n  "project_id": "x",\n  "name": "é"\n}\n'.encode("utf-8"))
        with self.assertRaises(FileExistsError):
            module_init.creer_identite_exclusive(chemin, {"project_id": "y"})
        with self.assertRaises(ValueError):
            module_init.creer_identite_exclusive(self.racine / "autre.json", {})
        self.assertFalse((self.racine / "autre.json").exists())
        self.assertIn('"x"', chemin.read_text(encoding="utf-8"))


class RenommerTests(_BancIdentite):
    """I14 — `--rename` ne bouge que `name` ; 0644 reposé, même depuis 0600
    (F5 de clôture, decision/T-00000969/01 ; mutant `mode=` retiré : rouge)."""

    def test_I14_rename_gele_id_slug_created_et_garde_une_cle_heritee(self):
        avant = {"project_id": "id-1", "name": "Old", "slug": "old",
                 "created": "2026-07-29T00:00:00Z", "kit_version": "unknown"}
        self.addCleanup(os.umask, os.umask(0o022))
        for depart in (0o644, 0o600):
            with self.subTest(depart=oct(depart)):
                chemin = self._poser(avant)
                chemin.chmod(depart)
                with mock.patch.object(Workspace, "write_bytes", autospec=True,
                                       side_effect=Workspace.write_bytes) as espion:
                    rc, out, err = self._appeler(module_init.renommer, self.atelier, " Nouveau ")
                self.assertEqual(rc, 0, err)
                apres = json.loads(chemin.read_text(encoding="utf-8"))
                self.assertEqual(apres, {**avant, "name": "Nouveau"})
                self.assertEqual(out, "project_init: name -> Nouveau (slug inchangé: old)\n")
                self.assertEqual({k: espion.call_args.kwargs.get(k) for k in ("reprises", "mode")},
                                 {"reprises": True, "mode": 0o644})
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(chemin.stat().st_mode), 0o644)

    def test_I14_refus_absent_corrompu_vide(self):
        for cas, preparer, attendu in (
                ("absent", None, "aucune identité à modifier (.agents/state/project.json "
                                 "absent) — lancer d'abord: python .agents/bin/project_init.py"),
                ("corrompu", '{"x', module_init._CORROMPU)):
            with self.subTest(cas=cas):
                atelier = Workspace(self._jetable())
                if preparer is not None:
                    (atelier.racine / ".agents" / "state").mkdir(parents=True)
                    (atelier.racine / _IDENT).write_text(preparer, encoding="utf-8")
                refus, out, _err = self._appeler(module_init.renommer, atelier, "Y")
                self.assertEqual((str(refus), out), (attendu, ""))
        refus, _out, _err = self._appeler(module_init.renommer, self.atelier, "  ")
        self.assertEqual(str(refus), "le nouveau nom ne peut pas être vide (--rename)")


class OtelTests(_BancIdentite):
    """I15 — l'`env` json est la SEULE clé d'identité ; settings.json jamais lu."""

    _SEULE = {"env": {"OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=id-9"}}

    def setUp(self):
        super().setUp()
        self._poser({"project_id": "id-9", "name": "P"})

    def test_I15_json_pur_cle_d_identite_seule_avec_et_sans_settings(self):
        rc, out, err = self._appeler(module_init.publier_otel, self.atelier, "json")
        self.assertEqual((rc, json.loads(out), err), (0, self._SEULE, ""))
        self._poser({"env": {"A": "1", "N": 5}}, Path(".claude") / "settings.json")
        rc, out, err = self._appeler(module_init.publier_otel, self.atelier, "json")
        self.assertEqual((rc, json.loads(out), err), (0, self._SEULE, ""))

    def test_I15_both_shell_d_abord_et_refus_sans_identite(self):
        _rc, out, _err = self._appeler(module_init.publier_otel, self.atelier)
        tete, _sep, queue = out.partition("\n# — ou, pour Claude Code")
        self.assertTrue(tete.startswith("# agentkit — attribution canal B pour « P »\n"))
        self.assertTrue(tete.endswith("OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=id-9\n"))
        self.assertIn('"OTEL_RESOURCE_ATTRIBUTES": "agentkit.project_id=id-9"', queue)
        refus, out, _err = self._appeler(module_init.publier_otel, Workspace(self._jetable()))
        self.assertIsInstance(refus, module_init.RefusIdentite)
        self.assertEqual(out, "", "une forme a été imprimée sans identité")

    def test_I15_settings_lien_hors_racine_ni_lu_ni_avis(self):
        """T-01M4WNKCBXS893CHPSKD1Z1PN9 : le fichier n'est plus lu, donc un lien
        hors racine n'a plus d'objet — rc 0, stderr VIDE (mutant qui le relit et
        avertit : rouge), même objet à une clé ; JSON pur."""
        dehors = self._jetable() / "settings.json"
        dehors.write_text(json.dumps({"env": {"OTEL_EXPORTER_OTLP_ENDPOINT":
                                              "http://collector.interne:4318"}}), encoding="utf-8")
        self._lien(dehors, self.racine / ".claude" / "settings.json")
        rc, out, err = self._appeler(module_init.publier_otel, self.atelier, "json")
        self.assertEqual((rc, json.loads(out), err), (0, self._SEULE, ""))
        self.assertEqual(self._appeler(module_init.publier_otel, self.atelier, "shell")[2], "")


class StoresEtAuteurTests(_BancIdentite):
    """I16 — le board par fournisseur injecté ; `user.name` par `Executor`."""

    def test_I16_board_cree_present_levant_absent(self):
        board = _BoardFactice()
        rc, out, _err = self._appeler(module_init.provisionner_stores, self.atelier, board)
        self.assertEqual((rc, board.crees), (0, [self.racine]))
        self.assertTrue(out.startswith("board cree: b/TASKS.json (+ vue v/TASKS.md, git-ignoree)\n"))
        rc, out, _err = self._appeler(module_init.provisionner_stores, self.atelier, board)
        self.assertEqual((rc, board.crees), (0, [self.racine]), "un board présent a été récrit")
        self.assertTrue(out.startswith("board deja present — inchange\n"))
        for nom, fournisseur, cause in (
                ("levant", _BoardFactice(leve=OSError("disque plein")), "(disque plein)"),
                ("absent", None, "(aucun fournisseur de board injecté")):
            with self.subTest(fournisseur=nom):
                rc, out, err = self._appeler(module_init.provisionner_stores,
                                             Workspace(self._jetable()), fournisseur)
                self.assertEqual((rc, out), (2, ""))
                self.assertIn("ATTENTION — board non provisionne " + cause, err)
                self.assertIn("--ensure-stores", err)

    def test_I16_user_name_vide_refuse_avant_toute_ecriture(self):
        for nom, auteur in (("vide", _auteur("  ")), ("code 1", _auteur("banc", code=1))):
            with self.subTest(auteur=nom):
                board = _BoardFactice()
                refus, _out, _err = self._appeler(module_init.initialiser_identite,
                                                  self.atelier, "X", board=board,
                                                  executeur=auteur)
                self.assertIn("git user.name est vide", str(refus))
                self.assertEqual((list(self.racine.iterdir()), board.crees), ([], []))


@unittest.skipIf(GIT is None, SANS_GIT)
class RacineIdentiteTests(_BancIdentite):
    """I17 — la racine de l'identité est git, JAMAIS `$CADRE_PROJECT_ROOT`."""

    def test_I17_le_leurre_cadre_project_root_est_ignore(self):
        projet, _partition = self._projet_neuf()
        leurre = self._jetable()
        self._forcer_env(CADRE_PROJECT_ROOT=str(leurre), GIT_DIR=None, GIT_WORK_TREE=None)
        ici = os.getcwd()
        self.addCleanup(os.chdir, ici)
        (projet / "sous").mkdir()
        os.chdir(projet / "sous")
        self.assertEqual(module_init.resoudre_racine_projet(), projet)
        board = _BoardFactice()
        rc, _out, err = self._appeler(module_init.principal_project_init, ["--name", "X"],
                                      board=board, executeur=_auteur())
        self.assertEqual(rc, 0, err)
        self.assertTrue((projet / _IDENT).is_file())
        self.assertEqual((list(leurre.iterdir()), board.crees), ([], [projet]))

    def test_I17_hors_git_repli_sur_le_repertoire_courant(self):
        dehors = self._jetable()
        if _git_toplevel(str(dehors)) is not None:
            self.skipTest(f"SAUT ANNONCÉ : {dehors} est sous un dépôt git")
        self._forcer_env(CADRE_PROJECT_ROOT=str(self.racine), GIT_DIR=None)
        ici = os.getcwd()
        self.addCleanup(os.chdir, ici)
        os.chdir(dehors)
        self.assertEqual(module_init.resoudre_racine_projet(), dehors)


class DelegateurTests(unittest.TestCase):
    """I18 — `project_init.py` ne garde que `main`, `_BoardDuKit` et `_amorcer_cadre`
    (T-01M5BXTGX5YN8XEXTG1PP7A5ZX phase D, qui remplace l'amorce `sys.path.insert` de la
    réserve C6) ; ses ré-exports sont des ALIAS des noms du paquet (C1, C5), et son
    amorçage est UN appel nu `_amorcer_cadre()` au niveau du module, qui charge `cadre`
    par `charger_paquet` sur la racine du fichier, sans `sys.path.insert`."""

    SOURCE = PROJECT_INIT.read_text(encoding="utf-8")

    def test_I18_seuls_main_et__BoardDuKit_sont_definis(self):
        arbre = ast.parse(self.SOURCE)
        definis = sorted(n.name for n in arbre.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        self.assertEqual(definis, ["_BoardDuKit", "_amorcer_cadre", "main"])
        alias = {c.targets[0].id: c.value for c in arbre.body
                 if isinstance(c, ast.Assign) and isinstance(c.targets[0], ast.Name)}
        for nom in ("project_json_path", "slugify", "_atomic_create", "_replace_with_retry",
                    "_REPLACE_ATTEMPTS", "_REPLACE_DELAY_SECONDS"):
            with self.subTest(reexport=nom):
                self.assertIsInstance(alias.get(nom), ast.Name, f"{nom} n'est pas un alias")
        appels = [n for n in arbre.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                  and isinstance(n.value.func, ast.Name)]
        self.assertEqual([n.value.func.id for n in appels], ["_amorcer_cadre"], "amorce du module")
        self.assertEqual(self.SOURCE.count("\n_amorcer_cadre()\n"), 1)
        self.assertEqual(self.SOURCE.count('resolveur.charger_paquet(chemin.parents[2], "cadre")\n'), 1)
        self.assertNotIn("sys.path.insert(0, str(Path(__file__)", self.SOURCE)

    def test_I18_les_alias_designent_les_objets_du_paquet(self):
        spec = importlib.util.spec_from_file_location("project_init_t969", PROJECT_INIT)
        pi = importlib.util.module_from_spec(spec)
        # Enregistré AVANT d'exécuter (T-00000134), retiré au nettoyage du témoin.
        sys.modules[spec.name] = pi
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(pi)
        for alias, objet in ((pi.project_json_path, module_init.chemin_identite),
                             (pi.slugify, module_init.slugifier),
                             (pi._atomic_create, module_init.creer_identite_exclusive),
                             (pi._replace_with_retry, module_workspace.remplacer_avec_reprise)):
            with self.subTest(alias=alias.__name__):
                self.assertIs(alias, objet)
        self.assertEqual((pi._REPLACE_ATTEMPTS, pi._REPLACE_DELAY_SECONDS), (30, 0.01))


class LienIdentiteTests(_BancIdentite):
    """I19 (réserve C4) — `Workspace` confine : un `project.json` LIEN HORS
    RACINE est refusé en 2, rien écrit ; un lien DANS la racine voit sa CIBLE
    réécrite par `--rename` (l'ancien remplaçait le lien : divergence nommée)."""

    LIEN = ("project.json, ou l'un de ses répertoires parents, est un lien hors racine "
            "— supprimer le lien puis rejouer")

    def _lier(self, cible: Path) -> Path:
        lien = self.racine / _IDENT
        lien.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(cible, lien)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique refusé par le poste ({exc})")
        return lien

    def test_I19_lien_hors_racine_refuse_en_2_sans_rien_ecrire(self):
        dehors = self._jetable() / "identite.json"
        octets = json.dumps({"project_id": "id-d", "name": "D", "slug": "d"}).encode()
        dehors.write_bytes(octets)
        lien = self._lier(dehors)
        for argv in (["--rename", "Y"], ["--name", "X"], ["--print-otel-env"]):
            with self.subTest(argv=argv), \
                    mock.patch.object(module_init, "resoudre_racine_projet",
                                      return_value=self.racine):
                rc, out, err = self._appeler(module_init.principal_project_init, argv,
                                             board=_BoardFactice(), executeur=_auteur())
                self.assertEqual((rc, out, err), (2, "", f"project_init: {self.LIEN}\n"))
                self.assertEqual(dehors.read_bytes(), octets, "la cible hors racine a bougé")
                self.assertTrue(lien.is_symlink(), "le lien a été remplacé")

    def test_I19_lien_dans_la_racine_cible_reecrite_lien_garde(self):
        cible = self._poser({"project_id": "id-i", "name": "I", "slug": "i"},
                            Path(".agents") / "state" / "vraie.json")
        lien = self._lier(Path("vraie.json"))
        rc, _out, err = self._appeler(module_init.renommer, self.atelier, "Neuf")
        self.assertEqual(rc, 0, err)
        self.assertTrue(lien.is_symlink(), "le lien a été remplacé par un fichier")
        self.assertEqual(json.loads(cible.read_text(encoding="utf-8"))["name"], "Neuf")


class LienBoardTests(_BancIdentite):
    """I20 (exec-critic, T-00000969) — mesuré sur 443dad15 : `Workspace.exists`
    avalait `HorsRacine`, un board lien hors racine passait pour ABSENT, le
    lien fichier était remplacé par une copie et la cible d'un lien répertoire
    réécrite. La base disait « board deja present — inchange » et ne touchait
    à rien : c'est ce qui est tenu ici. Mutant « `atelier.exists(store)`
    rétabli » : rouge, en processus comme de bout en bout."""

    OCTETS = b'{"tasks": [], "jeton": "dehors"}\n'
    BOARD = Path(".agents") / "state" / "board" / "TASKS.json"

    def _planter(self, racine: Path, forme: str, store: Path,
                 bout: str = "board") -> tuple[Path, Path]:
        """(lien, cible) : le fichier `store` (forme `fichier`), son répertoire
        (`dossier`) ou le parent de celui-ci (`aieul`) devient un lien vers un
        jetable HORS racine dont le `TASKS.json` porte `OCTETS` — sans board
        (`bout="vide"`), ou un chemin absent (`bout="pendant"`)."""
        dehors = self._jetable()
        if bout == "board":
            (dehors / store.name).write_bytes(self.OCTETS)
        elif bout == "pendant":
            dehors = dehors / "absent"
        lien = racine / store
        for _ in range(("fichier", "dossier", "aieul").index(forme)):
            lien = lien.parent
        vise = dehors / store.name if forme == "fichier" else dehors
        if lien.is_symlink() or lien.is_file():
            lien.unlink()
        elif lien.is_dir():
            shutil.rmtree(lien)
        lien.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(vise, lien)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique refusé par le poste ({exc})")
        return lien, dehors / store.name

    def test_I20_board_lien_hors_racine_present_lien_et_cible_intacts(self):
        for forme in ("fichier", "dossier"):
            with self.subTest(forme=forme):
                atelier = Workspace(self._jetable())
                lien, cible = self._planter(atelier.racine, forme, Path("b") / "TASKS.json")
                board = _BoardFactice()
                rc, out, err = self._appeler(module_init.provisionner_stores, atelier, board)
                self.assertEqual((rc, err, board.crees), (0, "", []), "le board a été recréé")
                self.assertTrue(out.startswith("board deja present — inchange\n"), out)
                self.assertTrue(lien.is_symlink(), "le lien a été remplacé")
                self.assertEqual(cible.read_bytes(), self.OCTETS, "la cible hors racine a bougé")

    def test_I20_lien_hors_racine_SANS_board_au_bout_attention_en_2(self):
        """F1 de clôture, mesuré sur be8dc812 : lien pendant ou cible vide →
        « board deja present », 0, aucun board nulle part. Tenu : ATTENTION en
        2, rien écrit, lien gardé. Mutant « hors racine = présent » : rouge."""
        for forme, bout in (("fichier", "pendant"), ("dossier", "vide"), ("dossier", "pendant")):
            with self.subTest(forme=forme, bout=bout):
                atelier, board = Workspace(self._jetable()), _BoardFactice()
                lien, cible = self._planter(atelier.racine, forme, Path("b") / "TASKS.json", bout)
                rc, out, err = self._appeler(module_init.provisionner_stores, atelier, board)
                self.assertEqual((rc, out, board.crees), (2, "", []))
                self.assertIn("ATTENTION — board non provisionne (b/TASKS.json : lien hors "
                              "racine (le fichier ou un répertoire parent) sans board au bout", err)
                self.assertTrue(lien.is_symlink(), "le lien a été remplacé")
                self.assertFalse(cible.exists(), "un board a été écrit hors racine")

    @unittest.skipIf(GIT is None, SANS_GIT)
    def test_I20_bout_en_bout_par_project_init_ensure_stores(self):
        """Le scénario du critique, par le VRAI fournisseur (`_BoardDuKit`,
        donc `tasks.save`) : `--name` puis le board planté en lien hors
        racine, puis `--ensure-stores`."""
        env = _env_purge()
        env.update(PYTHONIOENCODING="utf-8", CADRE_STATE_DIR=str(self._jetable()),
                   AGENTS_EVENTS_DIR=str(self._jetable()))

        def jouer(depot: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(PROJECT_INIT), *args], cwd=depot,
                                  env=env, capture_output=True, text=True,
                                  encoding="utf-8", timeout=DELAI, check=False)

        for forme, bout in (("fichier", "board"), ("dossier", "board"), ("aieul", "vide")):
            with self.subTest(forme=forme):
                depot = self._jetable()
                _git(depot, "init", "-q")
                _git(depot, "config", "user.name", "banc")
                r = jouer(depot, "--name", "P")
                self.assertEqual(r.returncode, 0, r.stderr)
                lien, cible = self._planter(depot, forme, self.BOARD, bout)
                r = jouer(depot, "--ensure-stores")
                if bout == "vide":  # `.agents/state` en lien vers un vide (F1 de clôture)
                    self.assertEqual((r.returncode, r.stdout), (2, ""))
                    self.assertIn("sans board au bout — supprimer le lien puis rejouer", r.stderr)
                    self.assertEqual(list(lien.resolve().iterdir()), [], "écrit hors racine")
                    continue
                self.assertEqual((r.returncode, r.stderr), (0, ""))
                self.assertTrue(r.stdout.startswith("board deja present — inchange\n"),
                                r.stdout)
                self.assertTrue(lien.is_symlink(), "le lien a été remplacé par une copie")
                self.assertEqual(cible.read_bytes(), self.OCTETS,
                                 "la cible hors racine a été réécrite")

    def test_I20_parent_de_l_identite_lien_hors_racine_refuse_a_l_init(self):
        """`.agents` ou `.agents/state` lien hors racine : l'init refuse en 2,
        rien n'est écrit dans la cible (la base y créait identité, board et
        vue), le board n'est pas atteint, et le message nomme le parent."""
        for parent in (Path(".agents"), Path(".agents") / "state"):
            with self.subTest(parent=parent.as_posix()):
                racine, dehors = self._jetable(), self._jetable()
                (racine / parent).parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.symlink(dehors, racine / parent)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"SAUT ANNONCÉ : lien symbolique refusé par le poste ({exc})")
                board = _BoardFactice()
                refus, out, _err = self._appeler(module_init.initialiser_identite,
                                                 Workspace(racine), "P", board=board,
                                                 executeur=_auteur())
                self.assertEqual((str(refus), out, board.crees),
                                 (LienIdentiteTests.LIEN, "", []))
                self.assertEqual(list(dehors.iterdir()), [], "l'init a écrit hors racine")


class LienVerrouTests(_BancIdentite):
    """I21 (F3 de clôture) — `kit.lock` lien hors racine jugé AU BOUT, comme la
    base (`Path.is_file`). Mutant `atelier.exists` rétabli : « ABSENT », rouge.
    Bras `boucle` (clôture 2) : un lien sur lui-même est « ABSENT », code 2,
    comme la base — sans le `try` local de `_refus_pierre_tombale`, `resolve`
    lève `RuntimeError` sous 3.11/3.12 (rc 1, traceback) : rouge sous 3.12."""

    def test_I21_kit_lock_lien_hors_racine_juge_au_bout(self):
        for bout, etat in (("fichier", "présent)"), ("pendant", "ABSENT ici —"),
                           ("boucle", "ABSENT ici —")):
            with self.subTest(bout=bout):
                racine, dehors = self._jetable(), self._jetable() / "kit.lock"
                if bout == "fichier":
                    dehors.write_text('{"version_kit": "0.0.0"}\n', encoding="utf-8")
                if bout == "boucle":
                    dehors = Path("kit.lock")  # relatif : le lien se vise lui-même
                self._lien(dehors, racine / ".agents" / "kit.lock")
                with mock.patch.object(module_init, "resoudre_racine_projet",
                                       return_value=racine):
                    rc, out, err = self._appeler(module_init.principal_project_init,
                                                 ["--stamp-kit-version"])
                self.assertEqual((rc, out), (2, ""))
                self.assertIn(f"(clé version_kit, {etat}", err)


if __name__ == "__main__":
    unittest.main()
