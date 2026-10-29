#!/usr/bin/env python3
"""Témoins de `.agents/bin/etat_lecture.py`, l'interface de lecture des magasins d'état (T-01M4V7R6EF5KSEC93N462BW5WM).

CE QU'ILS PROUVENT, un témoin par propriété du plan :
  T1  même issue que le propriétaire, pour chaque magasin, sur cinq racines — absent, monolithe, enregistrements,
      « les deux » identiques, « les deux » divergentes — SAUF `board_brut` sur « les deux » : refus VOULU, là où
      `lire_board_brut` lit le monolithe ;
  T2  la table de `forme` et de `present` ; specs « les deux » : `store_mode` lève ET `forme` le nomme ;
  T3  la résolution du propriétaire et l'identité des exceptions ; la PORTE exige `callable`, pas la présence
      (OWN1) ; les messages de REFUS de loadtest ;
  T4  rien n'est chargé à l'import, `sys.path` intact (sous-processus `python3 -I`) ;
  T5  aucune écriture : empreinte (sha256, st_mtime_ns) de TOUTE la racine, `.agents/state/local/` compris, sur
      les deux formes ;
  T6  parité avec `plan_pool` sur les deux formes ; « deux formes » et journal corrompu refusés des deux côtés ;
  T7  le module voyage (prédicat de `sync_template`), ses deux lecteurs aussi ;
  T8  aiguillage par sentinelle : on patche l'instance que TIENT le lecteur, jamais un import public du banc ;
      specs_graph importe ses trois propriétaires PUBLICS, et l'interface résout CEUX-LÀ (OWN3) ;
  T9  témoin isolé : copies de loadtest, specs et etat_lecture sous une racine jetable, `python3 -I`, cwd neutre ;
  T10 accord de `chemin_trace` et de `loadtest.chemin_specs`, qu'il double (constat (b)) : sans surcharge, le même
      chemin ; sous surcharge, la surcharge telle quelle, et `chemin_trace` ne lit pas l'environnement.

FIXTURES. Les magasins naissent par les VRAIES CLI (`tasks.py new`, `specs.py add`, `ledger.py add`) sous
`CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR` et `TMPDIR` jetables, puis basculent par le `migrate_store` de leur
propriétaire. « Les deux » : le monolithe d'avant la bascule recopié à côté des enregistrements — après une écriture
CLI de plus pour les divergentes. T9 écrit sa décision par `specs.save` : loadtest exige un id `S-<8 chiffres>`,
que la CLI ne frappe pas.

MUTANTS — chacun rougit le témoin nommé :
  M1 cache figé → T3 (privée puis publique) ; M2 import eager ou `sys.path.insert` → T4 ; M3 `tasks.save` → T5 ;
  M4 specs_graph remis sur `specs.load` → T8 ; M4b loadtest remis sur `specs.load(ROOT)` → T8 ; M5 `strip:` → T7 ;
  M6 `board_brut` accepte « les deux » → T1, T8 ; M8 `import etat_lecture` nu dans loadtest → T9 (i) ; M9 copie
  privée rechargée à chaque appel → T3 (sans public), T9 (ii)/(iii) ; M10 site (b) retiré → T3 (message specs.py) ;
  réserve C1 retirée (copie privée réutilisée sans contrôle de son fichier) → T3 (copie étrangère) ; OWN1 `callable`
  → `hasattr` dans la PORTE → T3 (non appelable) ; OWN3 `import ledger` retiré de specs_graph → T8 (propriétaires
  publics) ; (b) `chemin_trace` à préférence inversée, ou nom du journal changé dans loadtest → T10.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE = ROOT / "core-scripts"
RAISON_FIXTURE = "fixture de banc T-01M4V7R6EF5KSEC93N462BW5WM"
CAS = ("absent", "monolithe", "enregistrements", "deux_identiques", "deux_divergentes")
DEUX = ("deux_identiques", "deux_divergentes")
FORMES = {"absent": "absent", "monolithe": "monolithe", "enregistrements": "enregistrements",
          "deux_identiques": "les deux", "deux_divergentes": "les deux"}
MAGASINS = ("board", "specs", "ledger")
PUBLIC = {"board": "tasks", "specs": "specs", "ledger": "ledger"}
NOMS_PRIVES = ("_cadre_tasks_etat_lecture", "_cadre_specs_etat_lecture", "_cadre_ledger_etat_lecture")
# LA PORTE, écrite une seconde fois : le contrat, que `test_t3_porte_incomplete_ecartee` confronte au module.
PORTE = {
    "board": (("store_form", "load", "lire_board_brut", "store_path", "board_dir"), "BoardError"),
    "specs": (("store_mode", "store_path", "journal_store_path", "load", "read_journal"), "SpecsError"),
    "ledger": (("store_form", "load"), "LedgerError"),
}
JOUR = "2026-10-14"
HOTE = "shop.banc-etat.test"
LIGNE_SEUILS = "SEUILS: p95<=500ms,err<=1%,rps>=10"
SCENARIO = "import http from 'k6/http';\nexport default function () { http.get(__ENV.TARGET_URL); }\n"
ORDINAL = itertools.count()


def charger(nom: str, chemin: Path) -> Any:
    """Un module chargé PAR CHEMIN, enregistré AVANT son exécution (T-00000134), retiré s'il échoue."""
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None, chemin
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


EL = charger("etat_banc_etat_lecture", HERE / "etat_lecture.py")
TASKS = charger("etat_banc_tasks", HERE / "tasks.py")
SPECS = charger("etat_banc_specs", HERE / "specs.py")
LEDGER = charger("etat_banc_ledger", HERE / "ledger.py")
VRAIS = {"board": TASKS, "specs": SPECS, "ledger": LEDGER}


def env_banc(base: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT", "AGENTS_SPECS_PATH")}
    env.update(CADRE_STATE_DIR=str(base / "state"), AGENTS_EVENTS_DIR=str(base / "events"), TMPDIR=str(base / "tmp"))
    return env


def _cli(env: dict[str, str], script: str, racine: Path, *argv: str) -> None:
    p = subprocess.run([sys.executable, "-I", str(HERE / script), "--root", str(racine), *argv], env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    if p.returncode != 0:
        raise AssertionError(f"{script} {argv} : rc {p.returncode}\n{p.stdout}\n{p.stderr}")


def _monolithes(racine: Path) -> list[Path]:
    return [TASKS.store_path(racine), SPECS.store_path(racine), LEDGER.store_path(racine)]


def _batir(g: Path, env: dict[str, str]) -> None:
    """Les cinq gabarits de T1 : nés par les CLI, basculés par `migrate_store`."""
    (g / "absent").mkdir(parents=True)
    mono = g / "monolithe"
    mono.mkdir()
    _cli(env, "tasks.py", mono, "new", "tache un du banc")
    _cli(env, "tasks.py", mono, "new", "tache deux du banc")
    _cli(env, "specs.py", mono, "add", "--task", "T-00000001", "--kind", "decision", "decision du banc",
         "--text", f"porte la cible {HOTE}")
    _cli(env, "specs.py", mono, "add", "--task", "T-00000002", "--kind", "verdict", "verdict du banc")
    _cli(env, "ledger.py", mono, "add", "--category", "constraint", "--title", "contrainte du banc", "une")
    _cli(env, "ledger.py", mono, "add", "--category", "lesson", "--title", "lecon du banc", "deux")
    enr = g / "enregistrements"
    shutil.copytree(mono, enr, symlinks=True)
    r = str(enr)
    assert "migrated" in TASKS.migrate_store(r)
    LEDGER.migrate_store(r)
    SPECS.migrate_store(r, apply=True, lecteurs_non_migres=RAISON_FIXTURE)
    assert not any(p.exists() for p in _monolithes(enr)), "la bascule a laissé un monolithe"
    ident, div = g / "deux_identiques", g / "deux_divergentes"
    shutil.copytree(enr, ident, symlinks=True)
    shutil.copytree(enr, div, symlinks=True)
    _cli(env, "tasks.py", div, "new", "tache trois apres la bascule")
    _cli(env, "specs.py", div, "add", "--task", "T-00000003", "--kind", "delta", "delta apres la bascule")
    _cli(env, "ledger.py", div, "add", "--category", "decision", "--title", "decision apres la bascule", "trois")
    for cible in (ident, div):
        for source, destination in zip(_monolithes(mono), _monolithes(cible)):
            shutil.copy2(source, destination)


_GABARITS: dict[str, Any] = {}


def setUpModule() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="etat-lecture-", ignore_cleanup_errors=True)
    _GABARITS["tmp"] = tmp
    base = Path(tmp.name)
    for d in ("state", "events", "tmp"):
        (base / d).mkdir()
    env = env_banc(base)
    with mock.patch.dict(os.environ, env, clear=True):
        _batir(base / "gabarits", env)
    _GABARITS["dir"] = base / "gabarits"


def tearDownModule() -> None:
    tmp = _GABARITS.pop("tmp", None)
    if tmp is not None:
        tmp.cleanup()


def issue(appel: Callable[[], Any]) -> tuple[Any, ...]:
    """`("ok", valeur)` ou `("refus", classe, message)` — l'issue d'une lecture, comparable d'une instance à l'autre."""
    try:
        return ("ok", appel())
    except Exception as exc:  # noqa: BLE001 — l'issue, quelle qu'elle soit, EST l'objet du témoin
        return ("refus", type(exc).__name__, str(exc))


def _faux(vrai: Any, sans: str | None = None) -> types.ModuleType:
    """Une instance qui porte les attributs de `vrai`, sauf `sans`."""
    faux = types.ModuleType(getattr(vrai, "__name__", "faux"))
    for nom, valeur in vars(vrai).items():
        if nom != sans and not nom.startswith("__"):
            setattr(faux, nom, valeur)
    return faux


def _sans_public(*noms: str) -> Any:
    """`sys.modules` restauré à la sortie, privé des `noms` pendant le bloc."""
    patch = mock.patch.dict(sys.modules)

    class _Bloc:
        def __enter__(self) -> None:
            patch.start()
            for nom in noms:
                sys.modules.pop(nom, None)

        def __exit__(self, *exc: object) -> None:
            patch.stop()

    return _Bloc()


def _corrompre(journal: Path) -> None:
    with open(journal, "ab") as fh:
        fh.write(b"{ pas du json\n")


def empreinte(racine: Path) -> dict[str, Any]:
    """(sha256, st_mtime_ns) de chaque fichier de la racine, et le mtime de chaque dossier : TOUT, le dossier local
    de l'état compris."""
    vu: dict[str, Any] = {}
    for dossier, _sous, fichiers in os.walk(racine):
        d = Path(dossier)
        vu[d.relative_to(racine).as_posix() + "/"] = os.stat(d).st_mtime_ns
        for nom in fichiers:
            p = d / nom
            vu[p.relative_to(racine).as_posix()] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
    return vu


def _json(texte: str) -> dict[str, Any]:
    for ligne in reversed([x for x in texte.splitlines() if x.strip()]):
        try:
            valeur = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(valeur, dict):
            return valeur
    return {}


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="etat-lecture-", ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        for d in ("state", "events", "tmp"):
            (self.base / d).mkdir()
        self.env = env_banc(self.base)
        patch = mock.patch.dict(os.environ, self.env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def racine(self, cas: str, nom: str = "") -> Path:
        cible = self.base / (nom or cas)
        shutil.copytree(_GABARITS["dir"] / cas, cible, symlinks=True)
        return cible


def _paires(r: Path) -> dict[str, tuple[Callable[[], Any], Callable[[], Any]]]:
    """Chaque lecture de l'interface face à celle du propriétaire qu'elle remplace."""
    journal = SPECS.journal_store_path(r)
    return {
        "taches": (lambda: EL.taches(r), lambda: TASKS.load(r)["tasks"]),
        "board_brut": (lambda: EL.board_brut(r), lambda: TASKS.lire_board_brut(r)),
        "entrees_specs": (lambda: EL.entrees_specs(r), lambda: SPECS.load(r)["entries"]),
        "entrees_journal_specs": (lambda: EL.entrees_journal_specs(journal), lambda: SPECS.read_journal(journal)),
        "entrees_ledger": (lambda: EL.entrees_ledger(r), lambda: LEDGER.load(r)["entries"]),
        "chemin_trace": (lambda: EL.chemin_trace(r),
                         lambda: journal if journal.exists() else SPECS.store_path(r)),
    }


class T1MemeIssueTests(_Base):
    def test_t1_meme_issue_que_le_proprietaire(self) -> None:
        issues: dict[tuple[str, str], tuple[Any, ...]] = {}
        for cas in CAS:
            r = self.racine(cas)
            for nom, (interface, proprietaire) in _paires(r).items():
                with self.subTest(cas=cas, lecture=nom):
                    attendu, obtenu = issue(proprietaire), issue(interface)
                    issues[(cas, nom)] = obtenu
                    if nom == "board_brut" and cas in DEUX:
                        self.assertEqual(attendu[0], "ok", "le propriétaire lit le monolithe en silence")
                        self.assertEqual(obtenu[:2], ("refus", "EtatError"), "refus VOULU des deux formes (C3)")
                        self.assertIn(str(TASKS.store_path(r)), obtenu[2])
                        self.assertIn(str(TASKS.board_dir(r)), obtenu[2])
                    else:
                        self.assertEqual(obtenu, attendu)
        # Non-vacuité : des lectures pleines ET des refus de propriétaire ont été comparés.
        self.assertEqual(len(issues[("monolithe", "taches")][1]), 2)
        self.assertEqual(len(issues[("enregistrements", "entrees_specs")][1]), 2)
        self.assertEqual(len(issues[("enregistrements", "entrees_ledger")][1]), 2)
        self.assertEqual(issues[("deux_identiques", "entrees_specs")][:2], ("refus", "SpecsError"))
        self.assertEqual(issues[("deux_divergentes", "taches")][:2], ("refus", "BoardError"))
        self.assertEqual(issues[("deux_divergentes", "entrees_ledger")][:2], ("refus", "LedgerError"))


class T2FormeTests(_Base):
    def test_t2_table_de_forme(self) -> None:
        for cas, attendu in FORMES.items():
            r = self.racine(cas)
            for magasin in MAGASINS:
                with self.subTest(cas=cas, magasin=magasin):
                    self.assertEqual(EL.forme(r, magasin), attendu)
                    self.assertEqual(EL.present(r, magasin), attendu != "absent")
            with self.subTest(cas=cas, parite="store_mode"):
                if attendu == "les deux":
                    with self.assertRaises(SPECS.SpecsError):
                        SPECS.store_mode(r)
                else:
                    self.assertEqual(SPECS.store_mode(r), "journal" if attendu == "enregistrements" else "legacy")

    def test_t2_exists_et_noms_inconnus(self) -> None:
        r = self.racine("absent")
        SPECS.store_path(r).mkdir(parents=True)  # inconnue 2 tranchée : `.exists()`, pas `.is_file()`
        self.assertEqual(EL.forme(r, "specs"), "monolithe")
        self.assertTrue(EL.present(r, "specs"))
        with self.assertRaises(EL.EtatError):
            EL.forme(r, "journal")
        with _sans_public("tasks", NOMS_PRIVES[0]):
            with self.assertRaises(EL.EtatError):
                EL.erreurs_de_lecture("board", "inconnu")
            self.assertNotIn(NOMS_PRIVES[0], sys.modules, "un nom inconnu est refusé AVANT tout chargement")


class T3ResolutionTests(_Base):
    def test_t3_instance_publique_retenue(self) -> None:
        sans_porte = types.ModuleType("__main__")
        with mock.patch.dict(sys.modules, {"tasks": TASKS, "specs": SPECS, "ledger": LEDGER, "__main__": sans_porte}):
            for magasin, vrai in VRAIS.items():
                self.assertIs(EL._proprietaire(magasin), vrai)
            self.assertEqual(EL.erreurs_de_lecture(*MAGASINS),
                             (TASKS.BoardError, SPECS.SpecsError, LEDGER.LedgerError))

    def test_t3_main_prefere_pour_le_board_seul(self) -> None:
        faux_main = _faux(TASKS)
        with mock.patch.dict(sys.modules, {"__main__": faux_main, "tasks": TASKS}):
            self.assertIs(EL._proprietaire("board"), faux_main)
        faux_main = _faux(SPECS)
        with mock.patch.dict(sys.modules, {"__main__": faux_main, "specs": SPECS}):
            self.assertIs(EL._proprietaire("specs"), SPECS, "specs ne prend jamais `__main__`")

    def test_t3_erreurs_bornees_aux_magasins_nommes(self) -> None:
        with _sans_public("tasks", "ledger", "specs", *NOMS_PRIVES):
            sys.modules["__main__"] = types.ModuleType("__main__")
            (erreur,) = EL.erreurs_de_lecture("specs")
            self.assertTrue(issubclass(erreur, Exception))
            self.assertIn("_cadre_specs_etat_lecture", sys.modules)
            for nom in ("tasks", "ledger", "_cadre_tasks_etat_lecture", "_cadre_ledger_etat_lecture"):
                self.assertNotIn(nom, sys.modules, f"`erreurs_de_lecture('specs')` a chargé {nom}")

    def test_t3_porte_incomplete_ecartee(self) -> None:
        self.assertEqual({m: (d.fonctions, d.erreur) for m, d in EL._PROPRIETAIRES.items()}, PORTE)
        for magasin, (fonctions, erreur) in PORTE.items():
            complet = _faux(VRAIS[magasin])
            with mock.patch.dict(sys.modules, {PUBLIC[magasin]: complet, "__main__": complet}):
                self.assertIs(EL._proprietaire(magasin), complet, "témoin : une instance complète EST retenue")
            for manque in (*fonctions, erreur, "erreur-non-classe"):
                with self.subTest(magasin=magasin, manque=manque):
                    faux = _faux(VRAIS[magasin], sans=manque)
                    if manque == "erreur-non-classe":
                        setattr(faux, erreur, "pas une classe")
                    with mock.patch.dict(sys.modules, {PUBLIC[magasin]: faux, "__main__": faux}):
                        self.assertIsNot(EL._proprietaire(magasin), faux)

    def test_t3_attribut_non_appelable_ecarte(self) -> None:
        """OWN1 : la PORTE exige `callable`, pas la seule présence. Une chaîne, pas `None` : `getattr(…, None)`
        confondrait un `None` avec un attribut absent, que le témoin précédent couvre déjà."""
        for magasin, (fonctions, _erreur) in PORTE.items():
            for nom in fonctions:
                with self.subTest(magasin=magasin, attribut=nom):
                    faux = _faux(VRAIS[magasin])
                    setattr(faux, nom, "pas appelable")
                    self.assertTrue(hasattr(faux, nom), "témoin : l'attribut EXISTE")
                    with mock.patch.dict(sys.modules, {PUBLIC[magasin]: faux, "__main__": faux}):
                        self.assertIsNot(EL._proprietaire(magasin), faux, "un attribut non appelable passe la PORTE")

    def test_t3_sans_public_meme_classe_et_tuple_couvrant(self) -> None:
        corrompu = self.racine("enregistrements", "corrompu")
        _corrompre(SPECS.journal_store_path(corrompu))
        deux = self.racine("deux_identiques")
        with _sans_public("specs", "_cadre_specs_etat_lecture"):
            for r in (corrompu, deux):
                with self.subTest(racine=r.name):
                    erreurs = EL.erreurs_de_lecture("specs")
                    leves = []
                    for _ in range(2):
                        with self.assertRaises(Exception) as ctx:
                            EL.entrees_specs(r)
                        leves.append(ctx.exception)
                    self.assertEqual(type(leves[0]).__name__, "SpecsError")
                    self.assertIs(type(leves[0]), type(leves[1]), "sans public, deux appels lèvent la MÊME classe")
                    self.assertIsInstance(leves[0], erreurs, "le tuple pris AVANT l'appel couvre son exception")

    def test_t3_copie_privee_puis_publique(self) -> None:
        r = self.racine("enregistrements")
        with _sans_public("specs", "_cadre_specs_etat_lecture"):
            self.assertEqual(len(EL.entrees_specs(r)), 2)
            prive = sys.modules["_cadre_specs_etat_lecture"]
            self.assertEqual(EL.erreurs_de_lecture("specs"), (prive.SpecsError,))
            sys.modules["specs"] = SPECS
            self.assertIs(EL.erreurs_de_lecture("specs")[0], sys.modules["specs"].SpecsError,
                          "le public SUPPLANTE la copie privée dès qu'il apparaît")

    def test_t3_copie_privee_etrangere_non_reutilisee(self) -> None:
        ailleurs = self.base / "ailleurs"
        ailleurs.mkdir()
        corps = "class SpecsError(Exception):\n    pass\n\n" + "".join(
            f"def {nom}(*a, **k):\n    raise SpecsError('copie étrangère')\n\n" for nom in PORTE["specs"][0])
        (ailleurs / "specs.py").write_text(corps, encoding="utf-8")
        with _sans_public("specs", "_cadre_specs_etat_lecture"):
            etrangere = charger("_cadre_specs_etat_lecture", ailleurs / "specs.py")
            obtenu = EL._proprietaire("specs")
            self.assertIsNot(obtenu, etrangere, "réserve C1 : une copie privée d'un AUTRE fichier n'est pas reprise")
            self.assertEqual(Path(obtenu.__file__).resolve(), (HERE / "specs.py").resolve())
            self.assertIs(EL._proprietaire("specs"), obtenu, "témoin : la copie du frère attendu EST réutilisée")


class T3MessagesLoadtestTests(_Base):
    """C8 — chaque REFUS nomme le module en échec ; une `Refus` est un rc 2 de `main`, jamais une trace de pile."""

    def _loadtest(self, *freres: str) -> tuple[Path, Any]:
        racine = self.base / "copie"
        bin_ = racine / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for nom in ("loadtest.py", *freres):
            shutil.copy2(HERE / nom, bin_ / nom)
        return racine, charger(f"etat_banc_loadtest_{next(ORDINAL)}", bin_ / "loadtest.py")

    def _refus(self, lt: Any) -> Any:
        with self.assertRaises(lt.Refus) as ctx:
            lt._entrees_specs(lt.chemin_specs())
        return ctx.exception

    def test_t3_interface_absente(self) -> None:
        _racine, lt = self._loadtest()
        r = self._refus(lt)
        self.assertEqual(r.motif, "specs_illisible")
        self.assertIn("module etat_lecture.py inchargeable", r.detail)

    def test_t3_proprietaire_absent(self) -> None:
        racine, lt = self._loadtest("etat_lecture.py")
        SPECS.store_path(racine).parent.mkdir(parents=True)
        shutil.copy2(SPECS.store_path(_GABARITS["dir"] / "monolithe"), SPECS.store_path(racine))
        with _sans_public("specs", "_cadre_specs_etat_lecture"):
            r = self._refus(lt)
        self.assertEqual(r.motif, "specs_illisible")
        self.assertIn("module specs.py inchargeable", r.detail, "site (b) : le module en échec est nommé (M10)")
        self.assertNotIn("journal illisible", r.detail)

    def test_t3_repertoire_specs_json(self) -> None:
        racine, lt = self._loadtest("etat_lecture.py", "specs.py")
        SPECS.store_path(racine).mkdir(parents=True)
        r = self._refus(lt)
        self.assertEqual(r.motif, "specs_illisible", "un répertoire SPECS.json se lit par `.exists()` : illisible")


SONDE_IMPORT = """\
import importlib.util, json, sys
avant_chemin, avant_modules = list(sys.path), set(sys.modules)
spec = importlib.util.spec_from_file_location("etat_lecture_sonde", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules["etat_lecture_sonde"] = module
spec.loader.exec_module(module)
nouveaux = {n: getattr(sys.modules[n], "__file__", None) for n in set(sys.modules) - avant_modules}
print(json.dumps({"chemin_intact": sys.path == avant_chemin, "nouveaux": nouveaux}))
"""


class T4ImportTests(_Base):
    def test_t4_rien_au_chargement(self) -> None:
        p = subprocess.run([sys.executable, "-I", "-c", SONDE_IMPORT, str(HERE / "etat_lecture.py")],
                           cwd=self.base, env=self.env, capture_output=True, text=True, encoding="utf-8",
                           timeout=60, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        rendu = json.loads(p.stdout)
        self.assertTrue(rendu["chemin_intact"], "`sys.path` modifié à l'import")
        freres = sorted(n for n, f in rendu["nouveaux"].items()
                        if n != "etat_lecture_sonde" and f and Path(f).resolve().parent == HERE)
        self.assertEqual(freres, [], "un module frère chargé à l'import")
        self.assertEqual(sorted(set(rendu["nouveaux"]) & {"tasks", "specs", "ledger", *NOMS_PRIVES}), [])


class T5AucuneEcritureTests(_Base):
    def test_t5_empreinte_de_toute_la_racine(self) -> None:
        for cas in ("monolithe", "enregistrements"):
            with self.subTest(cas=cas):
                r = self.racine(cas)
                local = TASKS.store_path(r).parents[1] / "local"
                avant = empreinte(r)
                prefixe = local.relative_to(r).as_posix() + "/"
                self.assertTrue(any(k.startswith(prefixe) and k != prefixe for k in avant), "local/ couvert")
                lectures: list[Callable[[], Any]] = [
                    lambda: EL.taches(r), lambda: EL.board_brut(r), lambda: EL.entrees_specs(r),
                    lambda: EL.entrees_journal_specs(SPECS.journal_store_path(r)), lambda: EL.entrees_ledger(r),
                    lambda: EL.chemin_trace(r), lambda: EL.erreurs_de_lecture(*MAGASINS)]
                lectures += [lambda m=m: EL.forme(r, m) for m in MAGASINS]
                lectures += [lambda m=m: EL.present(r, m) for m in MAGASINS]
                issues = [issue(appel) for appel in lectures]
                self.assertTrue(all(i[0] == "ok" for i in issues[:3]), issues[:3])
                self.assertEqual(empreinte(r), avant, "une lecture a ÉCRIT dans la racine")


POOL = charger("etat_banc_plan_pool", CORE / "plan_pool.py")


class T6PariteTests(_Base):
    def test_t6_parite_sur_les_deux_formes(self) -> None:
        for cas in ("monolithe", "enregistrements"):
            with self.subTest(cas=cas):
                r = self.racine(cas)
                taches = sorted(t["id"] for t in EL.taches(r))
                self.assertEqual(len(taches), 2)
                self.assertEqual(taches, sorted(t["id"] for t in POOL.load_board(r)))
                entrees = sorted((e["id"], e["title"]) for e in EL.entrees_specs(r))
                self.assertEqual(len(entrees), 2)
                self.assertEqual(entrees, sorted((e["id"], e["title"]) for e in POOL.load_specs(r)))

    def test_t6_deux_formes_et_journal_corrompu_refuses(self) -> None:
        deux = self.racine("deux_identiques")
        corrompu = self.racine("enregistrements", "corrompu")
        _corrompre(SPECS.journal_store_path(corrompu))
        for r in (deux, corrompu):
            with self.subTest(racine=r.name):
                with self.assertRaises(POOL.PoolError):
                    POOL.load_specs(r)
                with self.assertRaises(EL.erreurs_de_lecture("specs")):
                    EL.entrees_specs(r)
        with self.assertRaises(POOL.PoolError):
            POOL.load_board(deux)
        with self.assertRaises(EL.EtatError):
            EL.board_brut(deux)


VOYAGEURS = (".agents/bin/etat_lecture.py", ".agents/bin/loadtest.py", ".agents/bin/specs_graph.py")


class T7VoyageTests(unittest.TestCase):
    def test_t7_le_module_voyage(self) -> None:
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():  # adopting-tree: marqueur du kit, absent chez l'adoptant
            self.skipTest("`.agents/IS_THE_KIT` absent (adoptant) : le voyage du module n'est PAS mesuré ici")
        st = charger("etat_banc_sync_template", HERE / "sync_template.py")
        texte = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        regles = st.parse_exclude(texte)
        for chemin in VOYAGEURS:
            self.assertIsNone(st.match_rule(chemin, regles), f"{chemin} ne voyage pas")
        mute = st.parse_exclude(texte + f"\nstrip: {VOYAGEURS[0]}\n")
        self.assertIsNotNone(st.match_rule(VOYAGEURS[0], mute), "témoin : un `strip:` le rougit (M5)")
        p = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", *VOYAGEURS], capture_output=True, text=True,
                           encoding="utf-8", timeout=30, check=False)
        if p.returncode != 0:
            self.skipTest("git illisible ici : l'état « suivi » des voyageurs n'est PAS mesuré")
        self.assertEqual(sorted(p.stdout.split()), sorted(VOYAGEURS), "un voyageur non suivi ne part pas")


def _sentinelles() -> tuple[dict[str, Any], dict[str, Any]]:
    tache = {"id": "T-00000042", "state": "pending", "task": "SENTINELLE-TACHE", "owner": "", "stage": "",
             "updated": JOUR}
    entree = {"id": "S-00000042", "task": "T-00000042", "kind": "decision", "title": "SENTINELLE-SPECS",
              "text": f"porte {HOTE}", "files": [], "date": JOUR}
    return tache, entree


class T8AiguillageTests(_Base):
    def test_t8_specs_graph(self) -> None:
        sg = charger(f"etat_banc_specs_graph_{next(ORDINAL)}", HERE / "specs_graph.py")
        el = sg.etat_lecture  # l'instance que TIENT le lecteur
        tache, entree = _sentinelles()
        r = self.racine("absent")
        with mock.patch.object(el, "taches", return_value=[tache]), \
                mock.patch.object(el, "entrees_specs", return_value=[entree]), \
                mock.patch.object(el, "entrees_ledger", return_value=[]):
            artefact, _notes = sg.build_graph(r)
        self.assertIsNotNone(artefact, "specs_graph n'a pas lu par l'interface (M4)")
        rendu = json.dumps(artefact, ensure_ascii=False)
        self.assertIn("SENTINELLE-TACHE", rendu)
        self.assertIn("SENTINELLE-SPECS", rendu)

    def test_t8_specs_graph_tient_ses_proprietaires_publics(self) -> None:
        """OWN3 (étape 3 du plan) : specs_graph importe `tasks`, `specs` ET `ledger` en frères PUBLICS, et l'interface
        résout CES instances (niveau 2), jamais une copie privée (niveau 4). Les publics sont retirés AVANT le
        chargement : un `ledger` laissé par un autre banc masquerait l'import manquant."""
        with _sans_public("etat_lecture", *PUBLIC.values(), *NOMS_PRIVES):
            sys.modules["__main__"] = types.ModuleType("__main__")
            sg = charger(f"etat_banc_specs_graph_{next(ORDINAL)}", HERE / "specs_graph.py")
            for magasin, public in PUBLIC.items():
                with self.subTest(magasin=magasin):
                    obtenu = sg.etat_lecture._proprietaire(magasin)
                    self.assertIsNotNone(sys.modules.get(public), f"specs_graph n'importe plus `{public}` en public")
                    self.assertIs(obtenu, sys.modules.get(public))
            self.assertEqual(sorted(set(NOMS_PRIVES) & set(sys.modules)), [], "une copie privée a été chargée")

    def test_t8_loadtest(self) -> None:
        lt = charger(f"etat_banc_loadtest_{next(ORDINAL)}", HERE / "loadtest.py")
        el = lt._etat_module()  # l'instance que TIENT le lecteur
        self.assertIs(lt._etat_module(), el, "une instance de l'interface par processus (C9)")
        _tache, entree = _sentinelles()
        r = self.racine("absent")
        with mock.patch.object(lt, "ROOT", r), mock.patch.object(el, "present", return_value=True), \
                mock.patch.object(el, "entrees_specs", return_value=[entree]):
            self.assertEqual(lt._entrees_specs(lt.chemin_specs()), [entree],
                             "loadtest n'a pas lu par l'interface (M4b)")
        surcharge = self.base / "surcharge.jsonl"
        surcharge.write_text("", encoding="utf-8")
        with mock.patch.dict(os.environ, {"AGENTS_SPECS_PATH": str(surcharge)}), \
                mock.patch.object(el, "entrees_journal_specs", return_value=[entree]):
            self.assertEqual(lt._entrees_specs(lt.chemin_specs()), [entree])

    def test_t8_board_brut_refuse_les_deux_formes(self) -> None:
        r = self.racine("deux_identiques")
        with self.assertRaises(EL.EtatError):
            EL.board_brut(r)


class T9TemoinIsoleTests(_Base):
    """Réserves C1 et C2 : copies sous `<tmp>/.agents/bin/`, racine de la copie = `<tmp>`, `python3 -I`, cwd neutre,
    `AGENTS_SPECS_PATH` retiré de l'environnement enfant sauf au cas (ii)."""

    def setUp(self) -> None:
        super().setUp()
        if shutil.which("git") is None:
            self.skipTest("git absent : la provenance des seuils de loadtest exige un dépôt git")
        depot = self.base / "depot"
        depot.mkdir()
        (depot / "SEUILS.md").write_text(f"# Seuils\n\n{LIGNE_SEUILS}\n", encoding="utf-8")
        for argv in (("init", "-q", "."), ("add", "--", "SEUILS.md"), ("commit", "-q", "-m", "banc: seuils")):
            subprocess.run(["git", "-c", "user.name=banc", "-c", "user.email=banc@example.com",
                            "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                            "-c", "init.defaultBranch=main", *argv], cwd=depot, capture_output=True, text=True,
                           env={k: v for k, v in self.env.items() if not k.startswith("GIT_")}, check=True,
                           timeout=60)
        script = self.base / "scenario.js"
        script.write_text(SCENARIO, encoding="utf-8")
        config = self.base / "targets.json"
        cible = {"name": "boutique-prod", "url": f"https://{HOTE}/", "env": "prod", "allowed_profiles": ["smoke"],
                 "fenetre": {"debut": "00:00", "fin": "24:00", "tz": "Europe/Paris"}, "decision_pilote": "S-00000001"}
        config.write_text(json.dumps({"targets": [cible], "local": {"max_load1": 1000}}), encoding="utf-8")
        self.argv = ["run", "--target", "boutique-prod", "--profil", "smoke", "--script", str(script),
                     "--seuils-de", str(depot / "SEUILS.md"), "--config", str(config), "--dry-run"]

    def _copie(self, nom: str) -> Path:
        racine = self.base / nom
        bin_ = racine / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for fichier in ("loadtest.py", "specs.py", "etat_lecture.py"):
            shutil.copy2(HERE / fichier, bin_ / fichier)
        decision = {"id": "S-00000001", "task": "T-00000001", "kind": "decision", "title": "Décision pilote",
                    "text": f"Tir de charge autorisé sur {HOTE}.", "files": [], "date": JOUR}
        SPECS.save(str(racine), {"entries": [decision]})
        return racine

    def _lancer(self, racine: Path, **extra: str) -> tuple[int, dict[str, Any], str]:
        neutre = Path(tempfile.mkdtemp(prefix="neutre-", dir=self.base))
        env = {k: v for k, v in self.env.items() if k != "AGENTS_SPECS_PATH"}
        env.update(AGENTS_LOADTEST_STATE=str(self.base / "etat"), VERIFY_WORKTREE_DIR=str(self.base / "verify"))
        env.update(extra)
        p = subprocess.run([sys.executable, "-I", str(racine / ".agents" / "bin" / "loadtest.py"), *self.argv],
                           cwd=neutre, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
                           check=False)
        return p.returncode, _json(p.stdout), p.stderr

    def test_t9_i_temoin_nominal(self) -> None:
        rc, sortie, err = self._lancer(self._copie("nominal"))
        self.assertEqual((rc, sortie.get("verdict")), (0, "DRY_RUN"), f"{sortie}\n{err}")

    def test_t9_ii_surcharge_jsonl_corrompue(self) -> None:
        corrompu = self.base / "corrompu.jsonl"
        corrompu.write_text("{ pas du json\n", encoding="utf-8")
        rc, sortie, err = self._lancer(self._copie("surcharge"), AGENTS_SPECS_PATH=str(corrompu))
        self.assertEqual((rc, sortie.get("motif")), (2, "specs_illisible"), f"{sortie}\n{err}")
        self.assertIn("journal illisible ou en deux formes", sortie.get("detail", ""))

    def test_t9_iii_deux_formes_sans_surcharge(self) -> None:
        racine = self._copie("deux_formes")
        monolithe = SPECS.store_path(racine)
        cote = self.base / "SPECS.json.avant"
        shutil.copy2(monolithe, cote)
        SPECS.migrate_store(str(racine), apply=True, lecteurs_non_migres=RAISON_FIXTURE)
        shutil.copy2(cote, monolithe)
        self.assertTrue(SPECS.journal_store_path(racine).is_file() and monolithe.is_file())
        rc, sortie, err = self._lancer(racine)
        self.assertEqual((rc, sortie.get("motif")), (2, "specs_illisible"), f"{sortie}\n{err}")
        self.assertIn("journal illisible ou en deux formes", sortie.get("detail", ""))


class T10AccordCheminTests(_Base):
    """Constat (b) : `etat_lecture.chemin_trace` DOUBLE `loadtest.chemin_specs`. Le contrat d'accord :
    `chemin_specs() == Path(surcharge) if surcharge else chemin_trace(ROOT)` — la surcharge `AGENTS_SPECS_PATH`
    n'appartient qu'à loadtest (ni `specs.py` ni l'interface ne la lisent)."""

    def test_t10_chemin_trace_et_chemin_specs_d_accord(self) -> None:
        lt = charger(f"etat_banc_loadtest_{next(ORDINAL)}", HERE / "loadtest.py")
        surcharges = {"jsonl": self.base / "surcharge.jsonl", "json": self.base / "surcharge.json",
                      "inexistante": self.base / "nulle-part" / "SPECS.jsonl"}
        surcharges["jsonl"].write_text("", encoding="utf-8")
        surcharges["json"].write_text('{"entries": []}', encoding="utf-8")
        branches = set()
        for cas in CAS:
            r = self.racine(cas)
            sans = EL.chemin_trace(r)
            branches.add(sans.name)
            with mock.patch.object(lt, "ROOT", r):
                with self.subTest(cas=cas, surcharge=None):
                    self.assertEqual(lt.chemin_specs(), sans, "sans surcharge, les deux chemins divergent")
                for nom, chemin in surcharges.items():
                    with self.subTest(cas=cas, surcharge=nom), \
                            mock.patch.dict(os.environ, {"AGENTS_SPECS_PATH": str(chemin)}):
                        self.assertEqual(lt.chemin_specs(), chemin)
                        self.assertEqual(EL.chemin_trace(r), sans, "`chemin_trace` a lu la surcharge")
        self.assertEqual(branches, {"SPECS.json", "SPECS.jsonl"}, "non-vacuité : les deux branches comparées")


if __name__ == "__main__":
    unittest.main()
