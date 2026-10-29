"""T-00000668 — `index.db` QUITTE LE DÉPÔT : témoins du point unique, du rejeu du
journal, de la couture `cadre.paths` et de l'isolation des bancs.

L'index SQLite est un doublon ADVISORY des `SYMBOLS*.md` versionnés : état
MACHINE, reconstructible, donc hors dépôt, sous `cadre.paths.index_db()` =
`state_project()/index/index.db`. Chaque témoin nomme la MUTATION qui le rougit :

  T1   point unique — `mig.db_path == paths.index_db == chemins_des_stores().index`,
       `_REL_DB_INDEX` retiré de `cadre.ledger.stores`.
  T2   aucun SQLite dans la cible, en DEUX bras (réserve R3) : (a) `creer_les_stores`
       puis `build_index` puis `migrate --resync` ; (b) sans init, `migrate --apply`
       — balayage par EN-TÊTE `SQLite format 3\\0`, ensemble ÉGAL au résidu attendu
       (`events.db` vit aujourd'hui sous la racine ; son déplacement est une tâche
       à part, T-00000755).
  T3   racine divergente — `$CADRE_PROJECT_ROOT=A`, `--root B` : refus nommant A et B.
  T4   couture — paquet en échec : branche par chemin ; les deux en échec : `Refusal`
       nommant `cadre.paths`, `read_db_generation` rend None, la sonde du Stop reste
       muette sur la DB à rc égal, `symbols.py query` refuse en nommant `cadre.paths`.
  T5   rejeu du journal — une annotation posée par `annotate` survit au retrait du
       store ; le FICHIER gagne sur toute ligne de journal ; deux `--resync` à
       sha256 identique (scénario SYMBOLE) ; `--verify` rc 0 ; bras MODULE au
       `--resync`.
  T5b  bras MODULE au `--apply` après retrait du store (ordre `write_state` puis
       `apply_log`).
  T5c  propagation entre DEUX postes (critic-opus F1, décision S-00002394) : une
       modification puis une rétractation faites sur A atteignent B au
       `--resync` et un poste neuf C à l'`--apply`, `--verify` rc 0 partout —
       hors fichier, c'est la DERNIÈRE valeur du journal qui gagne, rétractation
       comprise (ligne NULL écrite). Mutation : « store d'abord » → B garde P1.
  T6   doublon hérité — nommé par une NOTE, jamais lu, jamais touché.
  T16  partition machine non inscriptible → `REFUSED` nommant les variables.
  T17  `merge=union` : deux branches qui annotent fusionnent sans conflit.
  T17b au `git pull` : `--no-rebase` → l'AMONT gagne, `--rebase` → le LOCAL
       gagne (critic-opus T2 / critic-fable F2) ; `--resync` nomme ce que la
       dernière ligne du journal a remplacé (T5c).
  T18  journal non inscriptible APRÈS le COMMIT → `FAILED AFTER COMMIT`, jamais
       un `REFUSED` qui tairait que le store a bougé (critic-opus T4).
  T19  `annotate`/`retire` sur un champ que portent les FICHIERS → NOTE nommant
       la cellule, et le `--resync` suivant fait ce qu'elle annonce (T3/F3).
  T9   isolation in-process — pendant le `setUp` des deux `_Case` (SYM-2112,
       SYM-1210), `state_home()` est sous un tmp `cadre-state-` FRÈRE de la racine
       et `$CADRE_PROJECT_ROOT` est absent.
  T15  `PINNED_INDEX_NAMES` (repli adoptant) ne porte plus `index.db`.

T7 est la fixture de `test_cadre_init_surfaces::test_le_releve_des_stores_est_rejoue_sur_le_depot`,
T8 est `test_migrate_index_to_db::ApplyLogTests`, T11-T14 vivent dans leurs bancs.

BORNE ÉCRITE (réserve R6) : T9 épingle DEUX INSTANCES, pas la propriété « aucun
appelant in-process de `db_path` n'écrit hors tmp ». Une fixture autouse sur
`.agents/bin/test_*` changerait l'environnement de tous les bancs de
`.agents/bin/`, hors du rayon de ce lot ; la propriété est portée par T-00000758.

Chaque cas pose `$CADRE_STATE_DIR` sur un tmp et retire `$CADRE_PROJECT_ROOT` :
aucun témoin n'écrit sous le vrai `state_home()`.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
# Le paquet `cadre` que `vendor_paths` designe (patron v3prep,
# T-01M5BXTPQE3JZV3KZA6WD9P5XC) : charge PAR CHEMIN AVANT les modules du kit qui
# l'importent, sans `src` sur `sys.path`.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_index_machine_vendor_paths", BIN / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

import build_index as bi  # noqa: E402
import migrate_index_to_db as mig  # noqa: E402
import symbols as sym  # noqa: E402
import test_build_index_atomic as tbi  # noqa: E402
import test_migrate_index_to_db as tmig  # noqa: E402
import test_symbols as tsym  # noqa: E402
from cadre import paths  # noqa: E402
from cadre.ledger import stores  # noqa: E402

GIT = shutil.which("git")
SQLITE_HEADER = b"SQLite format 3\x00"


def _fichiers_sqlite(sommet: Path) -> set[str]:
    """Chaque fichier sous `sommet` dont l'EN-TÊTE est celui d'une base SQLite —
    par le contenu, jamais par l'extension : un store posé sous un autre nom est
    vu quand même."""
    trouves: set[str] = set()
    if not sommet.is_dir():
        return trouves
    for p in sommet.rglob("*"):
        if not p.is_file() or ".git" in p.relative_to(sommet).parts:
            continue
        with open(p, "rb") as fh:
            if fh.read(len(SQLITE_HEADER)) == SQLITE_HEADER:
                trouves.add(p.relative_to(sommet).as_posix())
    return trouves


class _DepotMachine(unittest.TestCase):
    """Un tmp par cas : dépôts git jetables + `$CADRE_STATE_DIR` isolé."""

    def setUp(self) -> None:
        if GIT is None:
            self.skipTest("git absent du PATH")
        self._tmp = tempfile.TemporaryDirectory(prefix="abk_machine_",
                                                ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.etat = self.base / "cadre-state"
        self._env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(self.etat),
            "AGENTS_EVENTS_DIR": str(self.base / "spool"),
            "AGENTS_OTEL_DIR": str(self.base / "otel"),
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        for cle in ("CADRE_PROJECT_ROOT", "AGENTS_EVENTS_DB"):
            os.environ.pop(cle, None)

    def depot(self, nom: str = "projet") -> Path:
        racine = self.base / nom
        (racine / "src").mkdir(parents=True)
        (racine / ".agents" / "state").mkdir(parents=True)
        (racine / "src" / "alpha.py").write_text(
            "def alpha_one(x):\n    return x\n", encoding="utf-8")
        for args in (("init", "-q"), ("config", "user.email", "t@t"),
                     ("config", "user.name", "t"), ("add", "-A"),
                     ("commit", "-qm", "init")):
            subprocess.run([GIT, "-C", str(racine), *args], check=True,
                           capture_output=True)
        return racine.resolve()

    def lancer(self, script: str, *argv: str,
               env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(BIN / script), *argv],
                              capture_output=True, text=True, timeout=180,
                              env=env if env is not None else dict(os.environ))

    def assert_rc(self, attendu: int, cp: subprocess.CompletedProcess) -> None:
        self.assertEqual(attendu, cp.returncode,
                         f"rc={cp.returncode}\nstdout={cp.stdout}\nstderr={cp.stderr}")


class PointUniqueTests(_DepotMachine):
    def test_T1_db_path_index_db_et_chemins_des_stores_designent_le_meme_fichier(self):
        r = self.depot()
        self.assertEqual(mig.db_path(r), paths.index_db(r))
        self.assertEqual(paths.index_db(r), stores.chemins_des_stores(r).index)
        self.assertTrue(mig.db_path(r).is_relative_to(paths.state_project(r)),
                        "l'index n'est pas sous la partition machine du projet")
        self.assertFalse(mig.db_path(r).is_relative_to(r), "l'index est DANS le dépôt")
        self.assertNotIn("_REL_DB_INDEX", dir(stores),
                         "le littéral relatif de l'index est revenu dans stores.py")


class AucunSQLiteDansLaCibleTests(_DepotMachine):
    def test_T2a_init_puis_build_puis_resync(self):
        r = self.depot()
        cree = stores.creer_les_stores(r)
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))
        self.assert_rc(0, self.lancer("migrate_index_to_db.py", "--root", str(r),
                                      "--resync"))
        self.assert_rc(0, self.lancer("symbols.py", "query", "--root", str(r),
                                      "--name", "alpha_one", "--strict"))
        partition = paths.state_project(r)
        self.assertEqual(cree.index, partition / "index" / "index.db")
        # Résidu NOMMÉ : events.db vit aujourd'hui sous la racine (son
        # déplacement est une tâche à part, T-00000755).
        self.assertEqual({".agents/state/local/events.db"}, _fichiers_sqlite(r))
        self.assertEqual({"index/index.db", "run/v3_event_store.db"},
                         _fichiers_sqlite(partition))

    def test_T2b_sans_init_apply(self):
        r = self.depot()
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))
        self.assert_rc(0, self.lancer("migrate_index_to_db.py", "--root", str(r),
                                      "--apply"))
        self.assert_rc(0, self.lancer("symbols.py", "query", "--root", str(r),
                                      "--name", "alpha_one", "--strict"))
        self.assertEqual(set(), _fichiers_sqlite(r))
        self.assertEqual({"index/index.db"}, _fichiers_sqlite(paths.state_project(r)))


class RacineDivergenteTests(_DepotMachine):
    def test_T3_une_racine_resolue_ailleurs_est_refusee_en_nommant_les_deux(self):
        a = self.depot("a")
        b = self.depot("b")
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(b)))
        cp = self.lancer("migrate_index_to_db.py", "--root", str(b), "--check",
                         env=dict(os.environ, CADRE_PROJECT_ROOT=str(a)))
        self.assert_rc(1, cp)
        self.assertIn(str(a), cp.stderr)
        self.assertIn(str(b), cp.stderr)
        self.assertEqual(set(), _fichiers_sqlite(self.etat))


class PartitionNonInscriptibleTests(_DepotMachine):
    def test_T16_une_partition_non_inscriptible_est_un_refus_nomme_jamais_une_trace(self):
        """critic-opus F3 : `$CADRE_STATE_DIR` sous un répertoire en mode 500 →
        `--apply` levait `PermissionError` en trace de 40 lignes. Attendu : rc 1,
        `REFUSED` nommant les variables qui déplacent la partition. Mutation :
        retirer `except OSError` de `cli` → trace, `REFUSED` absent."""
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("mode 500 sans effet ici (Windows, ou root)")
        r = self.depot()
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))
        fige = self.base / "fige"
        fige.mkdir()
        fige.chmod(0o500)
        self.addCleanup(fige.chmod, 0o700)
        cp = self.lancer("migrate_index_to_db.py", "--root", str(r), "--apply",
                         env=dict(os.environ, CADRE_STATE_DIR=str(fige / "cadre")))
        self.assert_rc(1, cp)
        self.assertNotIn("Traceback", cp.stderr)
        self.assertIn("REFUSED", cp.stderr)
        self.assertIn("PermissionError", cp.stderr)
        for variable in ("CADRE_STATE_DIR", "XDG_STATE_HOME"):
            self.assertIn(variable, cp.stderr)
        self.assertEqual([], list(fige.iterdir()), "une écriture a eu lieu malgré le refus")


class DoublonSuiviEtIgnoreTests(_DepotMachine):
    def test_T6b_le_geste_de_la_NOTE_desuit_un_doublon_suivi_et_ignore(self):
        """critic-opus F4 : chez un adoptant, l'ancien `index.db` peut être SUIVI
        (commité avant la règle d'ignore) ET ignoré. La NOTE nomme le geste ; le
        geste, rejoué tel quel, le désuit sans le toucher sur disque."""
        r = self.depot()
        ancien = r / ".agents" / "state" / "index" / "index.db"
        ancien.parent.mkdir(parents=True, exist_ok=True)
        octets = b"doublon herite suivi\n"
        ancien.write_bytes(octets)
        (r / ".gitignore").write_text("/.agents/state/index/index.db\n", encoding="utf-8")
        for args in (("add", "-f", str(ancien)), ("add", ".gitignore"),
                     ("commit", "-qm", "doublon suivi")):
            subprocess.run([GIT, "-C", str(r), *args], check=True, capture_output=True)
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))

        cp = self.lancer("migrate_index_to_db.py", "--root", str(r), "--check")
        self.assert_rc(0, cp)
        geste = f"`git rm --cached {ancien}` puis commit"
        self.assertIn(geste, cp.stdout)
        for args in (("rm", "-q", "--cached", str(ancien)),
                     ("commit", "-qm", "desuivi du doublon")):
            self.assertEqual(0, subprocess.run([GIT, "-C", str(r), *args],
                                               capture_output=True).returncode, args)
        suivis = subprocess.run([GIT, "-C", str(r), "ls-files", "--", str(ancien)],
                                capture_output=True, text=True).stdout
        self.assertEqual("", suivis, "le doublon est encore suivi après le geste")
        self.assertEqual(octets, ancien.read_bytes(), "le geste a touché le fichier")


class FusionDuJournalTests(_DepotMachine):
    def test_T17_deux_branches_qui_annotent_fusionnent_sans_conflit(self):
        """critic-opus F5 : `annotations_log.jsonl` est SUIVI et s'allonge par la
        fin sur chaque poste ; deux branches qui ajoutent chacune une ligne
        entraient en conflit de contenu (mesuré). Le VRAI `.gitattributes` du kit
        est copié dans un dépôt jetable : fusion rc 0, les deux lignes présentes,
        celle de la branche fusionnée APRÈS celle de la branche courante — sur une
        même clé, c'est cet ordre qui décide au rejeu (`replay_log`, la dernière
        gagne). Mutation : retirer la ligne `merge=union` → conflit, rc ≠ 0."""
        r = self.depot()
        shutil.copyfile(ROOT / ".gitattributes", r / ".gitattributes")
        journal = r / ".agents" / "state" / "index" / mig.LOG_NAME
        journal.parent.mkdir(parents=True, exist_ok=True)
        ligne = lambda valeur: json.dumps(  # noqa: E731
            {"at_sha": "aaaa111", "field": "purpose", "key": "1", "scope": "symbol",
             "value": valeur}, sort_keys=True) + "\n"
        journal.write_text(ligne("socle"), encoding="utf-8")

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([GIT, "-C", str(r), *args], capture_output=True,
                                  text=True)

        for args in (("add", "-A"), ("commit", "-qm", "socle"),
                     ("checkout", "-qb", "autre")):
            self.assertEqual(0, git(*args).returncode, args)
        with open(journal, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(ligne("de la branche autre"))
        self.assertEqual(0, git("commit", "-qam", "autre").returncode)
        self.assertEqual(0, git("checkout", "-q", "-").returncode)
        with open(journal, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(ligne("de la branche courante"))
        self.assertEqual(0, git("commit", "-qam", "courante").returncode)

        fusion = git("merge", "-q", "--no-edit", "autre")

        self.assertEqual(0, fusion.returncode, fusion.stdout + fusion.stderr)
        valeurs = [json.loads(l)["value"] for l in
                   journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["socle", "de la branche courante", "de la branche autre"],
                         valeurs)
        self.assertEqual("de la branche autre",
                         mig.replay_log(mig.read_log(journal))[("symbol", "1")]["purpose"],
                         "au rejeu, la dernière ligne APRÈS fusion ne gagne pas")

    def test_T17b_pull_en_fusion_l_amont_gagne_pull_en_rebase_le_local_gagne(self):
        """critic-opus T2 / critic-fable F2 — ce que T17 veut dire au `git pull`,
        mesuré git 2.55 : `git pull --no-rebase` (fusion) met TES lignes d'abord,
        donc l'AMONT gagne ; `git pull --rebase` rejoue les tiennes en dernier,
        donc les TIENNES gagnent. Configuration globale et système neutralisées :
        le résultat ne dépend pas du poste. Mutation : retirer `merge=union` →
        conflit, rc ≠ 0 dans les deux bras."""
        amont = self.depot("amont")
        shutil.copyfile(ROOT / ".gitattributes", amont / ".gitattributes")
        rel = Path(".agents") / "state" / "index" / mig.LOG_NAME
        (amont / rel).parent.mkdir(parents=True, exist_ok=True)
        ligne = lambda valeur: json.dumps(  # noqa: E731
            {"at_sha": "aaaa111", "field": "purpose", "key": "1", "scope": "symbol",
             "value": valeur}, sort_keys=True) + "\n"
        (amont / rel).write_text(ligne("socle"), encoding="utf-8")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                   GIT_EDITOR="true")

        def git(depot: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run([GIT, "-C", str(depot), "-c", "user.email=t@t",
                                   "-c", "user.name=t", *args], capture_output=True,
                                  text=True, env=env)

        def ajouter(depot: Path, valeur: str) -> None:
            with open(depot / rel, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(ligne(valeur))
            self.assertEqual(0, git(depot, "commit", "-qam", valeur).returncode)

        for args in (("add", "-A"), ("commit", "-qm", "socle")):
            self.assertEqual(0, git(amont, *args).returncode, args)
        for mode, gagnant in (("--no-rebase", "de l'amont"), ("--rebase", "du local")):
            with self.subTest(mode=mode):
                local = self.base / f"local{mode}"
                self.assertEqual(0, git(self.base, "clone", "-q", str(amont),
                                        str(local)).returncode)
                ajouter(amont, f"de l'amont {mode}")
                ajouter(local, f"du local {mode}")
                tire = git(local, "pull", "-q", mode, "--no-edit", "origin", "HEAD")
                self.assertEqual(0, tire.returncode, tire.stdout + tire.stderr)
                gagne = mig.replay_log(mig.read_log(local / rel))[("symbol", "1")]
                self.assertEqual(f"{gagnant} {mode}", gagne["purpose"],
                                 f"git pull {mode} : ce n'est pas {gagnant} qui gagne")
                self.assertEqual(0, git(amont, "reset", "-q", "--hard", "HEAD~1").returncode)


class CoutureCadrePathsTests(_DepotMachine):
    @contextlib.contextmanager
    def _couture(self, module, *, paquet: bool, chemin: bool):
        """Force l'échec d'une branche ou des deux sur `module` (une copie de
        `migrate_index_to_db`), mémo remis à None le temps du bloc."""
        patches = [mock.patch.object(module, "_CADRE_PATHS", None)]
        if not paquet:
            patches.append(mock.patch.object(
                module, "_importer_cadre_paths_paquet",
                side_effect=ImportError("paquet forcé en échec")))
        if not chemin:
            patches.append(mock.patch.object(
                module, "_CHEMIN_CADRE_PATHS", self.base / "absent" / "paths.py"))
        with contextlib.ExitStack() as pile:
            for p in patches:
                pile.enter_context(p)
            yield

    def test_T4_paquet_en_echec_la_branche_par_chemin_repond(self):
        r = self.depot()
        with self._couture(mig, paquet=False, chemin=True):
            module = mig._cadre_paths()
            self.assertEqual(mig._NOM_CADRE_PATHS_PAR_CHEMIN, module.__name__)
            self.assertEqual(paths.index_db(r), mig.db_path(r))

    def test_T4_les_deux_branches_en_echec(self):
        r = self.depot()
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))
        self.assert_rc(0, self.lancer("migrate_index_to_db.py", "--root", str(r),
                                      "--apply"))
        # Le store est rendu PÉRIMÉ : une nouvelle génération des fichiers. Sans
        # couture en échec, la sonde du Stop le DIT — c'est ce qui rend son
        # silence, plus bas, significatif.
        (r / "src" / "beta.py").write_text("def beta_one(y):\n    return y\n",
                                           encoding="utf-8")
        for args in (("add", "-A"), ("commit", "-qm", "beta")):
            subprocess.run([GIT, "-C", str(r), *args], check=True, capture_output=True)
        self.assert_rc(0, self.lancer("build_index.py", "--root", str(r)))

        def sonde() -> tuple[int, str]:
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = bi.cli(["--root", str(r), "--stale-check"])
            return code, out.getvalue()

        rc_normal, normal = sonde()
        self.assertIn(bi.DB_STALE_PREFIX, normal, "banc non armé : la DB n'est pas périmée")
        bi.db_staleness_line(r, None)  # charge la copie de la sonde (PROBE_MODULE)
        copie = sys.modules[bi.PROBE_MODULE]

        with self._couture(mig, paquet=False, chemin=False), \
                self._couture(copie, paquet=False, chemin=False):
            with self.assertRaises(mig.Refusal) as refus:
                mig.db_path(r)
            self.assertIn("cadre.paths", str(refus.exception))
            self.assertIn("cadre-kit", str(refus.exception))
            self.assertIn("README du kit, § Install the core", str(refus.exception))
            self.assertIsNone(mig.read_db_generation(r),
                              "read_db_generation doit rendre None, jamais lever")
            self.assertIsNone(mig.db_generation_behind(r, "abc1234"))
            rc_force, force = sonde()
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = sym.cli(["query", "--root", str(r), "--name", "alpha_one"])
        self.assertEqual(rc_normal, rc_force, "la couture en échec a changé le rc de la sonde")
        self.assertNotIn(bi.DB_STALE_PREFIX, force)
        self.assertIn("INDEX", force, "le verdict d'INDEX a disparu avec la DB")
        self.assertNotEqual(0, code)
        self.assertIn("cadre.paths", err.getvalue())


class RejeuDuJournalTests(tsym._SymbolsCase):
    """T5/T5b/T6, sur la fixture de `test_symbols` — donc sous l'isolation in-process
    de `tmig._Case.setUp` (T9)."""

    SANS_PURPOSE = 2      # `alpha_two` : aucun purpose dans les fichiers
    PURPOSE_FICHIER = 1   # `alpha_one` : "entry point of alpha" dans les fichiers

    def _annotation(self, scope: str, key: str) -> dict | None:
        return self.annotations().get((scope, key))

    def _ligne_de_journal(self, scope: str, key: str, field: str, value: str) -> None:
        log = mig.log_path(self.root)
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"scope": scope, "key": key, "field": field,
                                 "value": value, "at_sha": tmig.SHA},
                                sort_keys=True, ensure_ascii=False) + "\n")

    def test_T5_une_annotation_de_journal_survit_au_retrait_du_store(self):
        self.full_fixture()
        # LE FICHIER GAGNE : une ligne de journal qui DIFFÈRE du fichier, sur un
        # symbole dont le FICHIER porte un purpose — le fichier doit gagner, que
        # la ligne soit plus ancienne ou plus récente (règle S-00002394).
        self._ligne_de_journal("symbol", str(self.PURPOSE_FICHIER), "purpose",
                               "valeur du journal, pas du fichier")
        self.run_cli("--apply")
        # Vérifié ICI, au premier `--apply` : c'est le seul moment où cette ligne
        # est la DERNIÈRE du journal — `append_log` y ajoute ensuite la valeur du
        # fichier, et un second `--apply` ne distinguerait plus « le fichier
        # gagne » de « le journal gagne » (mutation mesurée).
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", str(self.PURPOSE_FICHIER))["purpose"],
                         "une ligne de journal a écrasé le fichier")
        self.run_sym("annotate", "--symbol", bi.sid(self.SANS_PURPOSE),
                     "--purpose", "posé par annotate")

        mig.db_path(self.root).unlink()
        self.run_cli("--apply")
        self.assertEqual("posé par annotate",
                         (self._annotation("symbol", str(self.SANS_PURPOSE)) or {})
                         .get("purpose"),
                         "l'annotation du journal n'a pas été rejouée dans le store")
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", str(self.PURPOSE_FICHIER))["purpose"],
                         "une ligne de journal a écrasé le fichier")

        self.run_cli("--resync")
        premier = self.digest(mig.DB_NAME)
        self.run_cli("--resync")
        self.assertEqual(premier, self.digest(mig.DB_NAME),
                         "deux --resync ont déplacé les octets (scénario SYMBOLE)")
        self.run_cli("--verify")

    def test_T5_bras_module_au_resync(self):
        """Clé MIXTE — `owner` porté par le FICHIER, `role` par le JOURNAL
        (cellule placeholder). critic-opus T1 : `write_state` remettait `role` à
        NULL et `apply_log` le rétablissait, donc CHAQUE `--resync` réécrivait la
        ligne et « unchanged » n'était jamais atteint. `write_state` laisse
        désormais à `apply_log` toute clé que le journal nomme : le second
        `--resync` n'écrit rien. Mutation : `logged` non transmis → le second
        `--resync` écrit 2 lignes, « unchanged » absent."""
        self.write_fixture()
        self.annotate_module(module="alpha", role="—", owner="O-fichier")
        self.run_cli("--apply")
        self.run_sym("annotate", "--module", "alpha", "--role", "R-journal")
        self.run_cli("--resync")
        ligne = self._annotation("module", "alpha")
        self.assertEqual(("R-journal", "O-fichier"), (ligne["role"], ligne["owner"]))
        premier = self.digest(mig.DB_NAME)
        self.assertIn("unchanged", self.run_cli("--resync"),
                      "le second --resync a réécrit la clé mixte (critic-opus T1)")
        self.assertEqual(premier, self.digest(mig.DB_NAME),
                         "le second --resync a déplacé les octets du store")
        ligne = self._annotation("module", "alpha")
        self.assertEqual(("R-journal", "O-fichier"), (ligne["role"], ligne["owner"]))

    def test_T5b_bras_module_a_l_apply_apres_retrait_du_store(self):
        self.write_fixture()
        self.annotate_module(module="alpha", role="—", owner="O-fichier")
        self.run_cli("--apply")
        self.run_sym("annotate", "--module", "alpha", "--role", "R-journal")
        mig.db_path(self.root).unlink()
        self.run_cli("--apply")
        ligne = self._annotation("module", "alpha")
        self.assertEqual(("R-journal", "O-fichier"), (ligne["role"], ligne["owner"]),
                         "apply_log a tourné AVANT write_state, ou pas du tout")

    def _machine(self, nom: str) -> contextlib.AbstractContextManager:
        """Un AUTRE poste sur le MÊME arbre : un `$CADRE_STATE_DIR` à lui (frère
        du tmp du banc, nettoyé), donc un store à lui ; le journal versionné,
        lui, est partagé — c'est l'état d'après un `git pull`."""
        if not hasattr(self, "_machines"):
            self._machines = {}
        if nom not in self._machines:
            d = tempfile.TemporaryDirectory(prefix=f"cadre-state-{nom}-",
                                            ignore_cleanup_errors=True)
            self.addCleanup(d.cleanup)
            self._machines[nom] = d.name
        return mock.patch.dict(os.environ, {"CADRE_STATE_DIR": self._machines[nom]})

    def _verify_rc(self) -> int:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            return mig.cli(["--root", str(self.root), "--verify"])

    def test_T5c_une_modification_puis_une_retractation_se_propagent_a_un_autre_poste(self):
        """critic-opus F1 / exec-critic BLOQUANT (décision S-00002394). A annote
        P1 puis P2 ; B, qui avait P1, `--resync` → P2 et `--verify` rc 0. A
        retire ; B `--resync` → la ligne NULL que `retire` garde, `--verify`
        rc 0 ; un poste C NEUF `--apply` → la même ligne NULL, rc 0. Mutation :
        COALESCE « store d'abord » → B garde P1, `--verify` rc 1."""
        self.full_fixture()
        cle = str(self.SANS_PURPOSE)
        with self._machine("A"):
            self.run_cli("--apply")
            self.run_sym("annotate", "--symbol", bi.sid(self.SANS_PURPOSE),
                         "--purpose", "P1")
        with self._machine("B"):
            self.run_cli("--apply")
            self.assertEqual("P1", self._annotation("symbol", cle)["purpose"],
                             "banc non armé : B n'a pas reçu P1")
        with self._machine("A"):
            self.run_sym("annotate", "--symbol", bi.sid(self.SANS_PURPOSE),
                         "--purpose", "P2")
        with self._machine("B"):
            sortie = self.run_cli("--resync")
            self.assertEqual("P2", self._annotation("symbol", cle)["purpose"],
                             "la modification de A ne s'est pas propagée à B")
            # critic-opus T2 / critic-fable F2 : le remplacement n'est plus muet.
            self.assertIn("NOTE: replaced by the journal's last value: "
                          f"(symbol, {cle}) purpose 'P1' -> 'P2'", sortie)
            self.assertEqual(0, self._verify_rc(), "B --verify après la modification")
            self.assertIn("unchanged", self.run_cli("--resync"),
                          "un second --resync de B a écrit (idempotence)")
        with self._machine("A"):
            self.run_sym("retire", "--symbol", bi.sid(self.SANS_PURPOSE))
        nulle = {"purpose": None, "role": None, "owner": None}
        with self._machine("B"):
            self.run_cli("--resync")
            self.assertEqual(nulle, self._annotation("symbol", cle),
                             "la rétractation de A ne s'est pas propagée à B")
            self.assertEqual(0, self._verify_rc(), "B --verify après la rétractation")
        with self._machine("C"):
            self.run_cli("--apply")
            self.assertEqual(nulle, self._annotation("symbol", cle),
                             "un poste neuf n'a pas la ligne NULL de la rétractation")
            self.assertEqual(0, self._verify_rc(), "C --verify sur un poste neuf")

    NOTE_FICHIERS = "the index FILES still carry"

    def test_T19_annotate_et_retire_sur_un_champ_des_fichiers_le_disent(self):
        """critic-opus T3 / critic-fable F3 : un champ que portent les FICHIERS
        gagne au `--resync` (S-00002394) — `annotate` ou `retire` dessus ne dure
        donc que jusqu'au `--resync` suivant, et c'était muet. Attendu : la NOTE
        nomme le champ et la cellule à éditer, et le `--resync` suivant fait bien
        ce qu'elle annonce ; aucune NOTE sur un champ que les fichiers ne portent
        pas, ni quand ils portent déjà la valeur écrite. Mutation : retirer
        l'appel de la NOTE dans `mode_annotate` ou `mode_retire` → rouge."""
        self.full_fixture()
        self.run_cli("--apply")
        cle = str(self.PURPOSE_FICHIER)

        sortie = self.run_sym("annotate", "--symbol", bi.sid(self.PURPOSE_FICHIER),
                              "--purpose", "écrit par annotate")
        self.assertIn(f"{self.NOTE_FICHIERS} purpose — the next --resync restores it "
                      "(a field the files carry wins, S-00002394); edit the "
                      "`:: purpose` cell there too", sortie)
        self.run_cli("--resync")
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", cle)["purpose"],
                         "la NOTE annonce une restauration que --resync ne fait pas")

        sortie = self.run_sym("retire", "--symbol", bi.sid(self.PURPOSE_FICHIER))
        self.assertIn(f"{self.NOTE_FICHIERS} purpose", sortie)

        sortie = self.run_sym("annotate", "--symbol", bi.sid(self.SANS_PURPOSE),
                              "--purpose", "hors fichiers")
        self.assertNotIn(self.NOTE_FICHIERS, sortie, "NOTE sur un champ hors fichiers")

    def test_T19_bras_module_nomme_la_cellule_owner(self):
        self.write_fixture()
        self.annotate_module(module="alpha", role="—", owner="O-fichier")
        self.run_cli("--apply")
        sortie = self.run_sym("annotate", "--module", "alpha", "--owner", "O-autre",
                              "--role", "R-journal")
        self.assertIn(f"{self.NOTE_FICHIERS} owner — the next --resync restores it",
                      sortie)
        self.assertIn("edit the `Owner agent` cell there too", sortie)
        self.assertNotIn("role —", sortie.split(self.NOTE_FICHIERS, 1)[1].split("\n")[0],
                         "le rôle, absent des fichiers (placeholder), est nommé")
        sortie = self.run_sym("annotate", "--module", "alpha", "--owner", "O-fichier")
        self.assertNotIn(self.NOTE_FICHIERS, sortie,
                         "NOTE alors que les fichiers portent déjà la valeur écrite")

    def test_T18_un_journal_non_inscriptible_apres_commit_est_dit_tel_quel(self):
        """critic-opus T4 : `append_log` court APRÈS le COMMIT du store. Un
        journal en lecture seule y levait `PermissionError`, que `cli` traduisait
        en « REFUSED … rendre la partition machine inscriptible » — faux deux
        fois : le store AVAIT été mis à jour, et c'est le JOURNAL qu'il faut
        rendre inscriptible. Attendu : rc 1, `FAILED AFTER COMMIT` nommant le
        journal, store à jour ; journal rendu inscriptible, `--resync` ajoute
        les lignes manquantes et `--verify` rend 0. Mutation : retirer la
        branche `exc.filename` de `cli` → « REFUSED » et la partition, rouge."""
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("mode 444 sans effet ici (Windows, ou root)")
        self.full_fixture()
        journal = mig.log_path(self.root)
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text("", encoding="utf-8")
        # Aucun `addCleanup(chmod)` : le `tearDown` du banc retire le tmp AVANT
        # les cleanups, et effacer un fichier 444 ne demande que le dossier.
        journal.chmod(0o444)

        sortie = self.run_cli("--apply", expect=1)

        self.assertIn("FAILED AFTER COMMIT", sortie)
        self.assertIn(f"make {journal} writable", sortie)
        self.assertIn("The store WAS updated", sortie)
        self.assertNotIn("REFUSED", sortie, "le message ment : le store a été écrit")
        self.assertNotIn("Traceback", sortie)
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", str(self.PURPOSE_FICHIER))["purpose"],
                         "le store n'a pas été mis à jour avant l'échec du journal")
        self.assertEqual("", journal.read_text(encoding="utf-8"))

        journal.chmod(0o644)
        rattrapage = self.run_cli("--resync")
        self.assertNotIn("       0  lines appended", rattrapage,
                         "--resync n'a pas ajouté les lignes manquantes")
        self.assertNotEqual("", journal.read_text(encoding="utf-8"))
        self.assertEqual(0, self._verify_rc(), "--verify après le rattrapage")

    def test_T6_un_doublon_herite_est_nomme_jamais_lu_ni_touche(self):
        self.full_fixture()
        ancien = mig.legacy_db_path(self.root)
        octets = b"doublon herite: pas une base, et personne ne doit la lire\n"
        ancien.write_bytes(octets)

        sortie = self.run_cli("--check")
        self.assertIn(f"NOTE: doublon hérité {ancien}", sortie)
        self.assertIn(f"`git rm --cached {ancien}` puis commit", sortie,
                      "la NOTE ne nomme pas le geste (critic-opus F4)")
        self.assertIn("absent", sortie, "--check a lu l'ancien chemin comme le store")
        self.run_cli("--apply")
        out, err = self.run_streams("query", "--name", "alpha_one")
        self.assertIn("doublon hérité", err)
        self.assertNotIn("doublon hérité", out, "la NOTE a pollué la sortie de données")
        self.assertEqual(octets, ancien.read_bytes(), "le doublon hérité a été touché")


class IsolationInProcessTests(unittest.TestCase):
    """T9 — les DEUX instances épinglées (réserve R6 : la propriété générale est
    portée par T-00000758)."""

    def _sonder(self, base) -> None:
        class _Sonde(base):
            def runTest(self) -> None:  # pragma: no cover - jamais lancé
                pass

        cas = _Sonde()
        avant = dict(os.environ)
        cas.setUp()
        try:
            etat = Path(cas._statedir.name).resolve()
            self.assertTrue(etat.name.startswith("cadre-state-"), etat)
            self.assertEqual(etat, paths.state_home(),
                             "state_home() n'est pas sous le tmp cadre-state- du banc")
            self.assertEqual(cas.root.parent, etat.parent,
                             "le tmp d'état n'est pas FRÈRE de la racine")
            self.assertFalse(etat.is_relative_to(cas.root))
            self.assertNotIn("CADRE_PROJECT_ROOT", os.environ)
            vraie = Path.home() / ".local" / "state"
            self.assertFalse(paths.state_home().is_relative_to(vraie))
        finally:
            cas.doCleanups()
            if hasattr(cas, "_tmpdir"):
                cas._tmpdir.cleanup()
        self.assertEqual(avant, dict(os.environ), "l'environnement n'a pas été restauré")

    def test_T9_le_setUp_de_tmig_Case_isole_state_home(self):
        self._sonder(tmig._Case)

    def test_T9_le_setUp_de_tbi_Case_isole_state_home(self):
        self._sonder(tbi._Case)


class RepliAdoptantTests(unittest.TestCase):
    def test_T15_PINNED_INDEX_NAMES_ne_porte_plus_index_db(self):
        source = (ROOT / ".agents" / "evals" / "test_docs_only_route_contract.py"
                  ).read_text(encoding="utf-8")
        valeur = None
        for noeud in ast.parse(source).body:
            if (isinstance(noeud, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "PINNED_INDEX_NAMES"
                            for t in noeud.targets)):
                valeur = ast.literal_eval(noeud.value)
        self.assertIsNotNone(valeur, "PINNED_INDEX_NAMES introuvable — banc non armé")
        self.assertIn(".agents/state/index/annotations_log.jsonl", valeur,
                      "le journal d'annotations (SUIVI) a disparu du repli")
        self.assertNotIn(".agents/state/index/index.db", valeur,
                         "le repli adoptant épingle encore index.db (T-00000668)")


if __name__ == "__main__":
    unittest.main()
