#!/usr/bin/env python3
"""T-01M4KKMY43ZKCW1YD2Y8JX9MKH — LES LECTEURS HORS MODULE LISENT LES DEUX FORMES (L1-L9).

Chaque lecteur BRUT des trois magasins (board, ledger, journal SPECS) qui vit hors de son module propriétaire est
rejoué sur DEUX racines jetables fabriquées par les modules eux-mêmes, jamais à la main : la forme MONOLITHE
(`TASKS.json`, `LEDGER.json`, `SPECS.json` — l'adoptant, le kit avant bascule : CONTRÔLE, vert à la BASE) et la forme
ENREGISTREMENT (`board/{tasks,epics}/`, `memory/entries/`, `SPECS.jsonl`, posée par `tasks.migrate_store`,
`ledger.migrate_store` et `specs.migrate_store(apply=True)` — ROUGE à la BASE, où ces lecteurs lisaient vide ou
refusaient). Les altérations (deux formes, corruption, tombe, doublons du journal fusionné en union) sont des deltas
posés APRÈS la migration, sur la racine jetable.

  L1 plan_cible (entrees_specs, chantier_de_tache, taches_du_board, _chantiers_du_board) ; L2 plan_depends ;
  L3 plan_pool (CLI `check` et `load_specs`, même verdict que `specs.read_journal`) ; L4 plan_waves et
  feuille_de_route ; L5 check-stale-justification.sh ; L6 loadtest ; L7 night_approve --delivered ;
  L8 empreintes du dashboard ; L9 remède de kickoff_guard ; C2 le refus « deux formes » de ledger.save.

Board en DEUX formes : plan_cible et plan_depends REFUSENT par `CibleError` nommée, comme plan_pool (avis sécurité
medium de la bascule, passe de correction F5 — ils lisaient le monolithe, fail-OPEN) ; un board présent mais illisible
aussi. Seul un board ABSENT rend `None`.

Montage : racine `tempfile` par témoin (copie d'un gabarit bâti une fois), `CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR`
et `TMPDIR` jetables, `CLAUDE_PROJECT_DIR` retiré ; sous-processus avec `--root`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / ".agents" / "bin"
CORE = REPO / "core-scripts"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import kickoff_guard as kg  # noqa: E402  (frère de .agents/bin, après l'insertion)
import plan_cible  # noqa: E402
import plan_depends  # noqa: E402


def charger(nom: str, chemin: Path) -> Any:
    """Un module chargé PAR CHEMIN, enregistré AVANT son exécution (T-00000134)."""
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None, chemin
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


TASKS = charger("bascule_banc_tasks", BIN / "tasks.py")
LEDGER = charger("bascule_banc_ledger", BIN / "ledger.py")
SPECS = charger("bascule_banc_specs", BIN / "specs.py")
POOL = charger("bascule_banc_plan_pool", CORE / "plan_pool.py")
READERS = charger("bascule_banc_dashboard_readers", BIN / "dashboard_readers.py")

STATE = Path(".agents") / "state"
BOARD = STATE / "board"
TASKS_JSON = BOARD / "TASKS.json"
LEDGER_JSON = STATE / "memory" / "LEDGER.json"
ENTRIES = STATE / "memory" / "entries"
SPECS_JSON = STATE / "specs" / "SPECS.json"
SPECS_JSONL = STATE / "specs" / "SPECS.jsonl"
CHANTIER = "banc-bascule"
JOUR = "2026-10-12"
U2028 = " "
RAISON_FIXTURE = "fixture de banc T-01M4KKMY43ZKCW1YD2Y8JX9MKH"


def _tache(tid: str, state: str = "pending", **extra: Any) -> dict[str, Any]:
    out = {"id": tid, "owner": "dev-multi", "stage": "", "state": state, "task": f"titre {tid}",
           "updated": JOUR, "chantier": CHANTIER}
    out.update(extra)
    return out


def _board() -> dict[str, Any]:
    return {
        "epics": [{"id": "E-01", "titre": "épopée du banc"}],
        "tasks": [
            _tache("T-1", "running", writeset=["src/a.py"]),
            _tache("T-2", "done"),
            _tache("T-3", depends_on=["T-1"]),
            _tache("T-9"),
        ],
    }


def _entree_specs(sid: str, task: str, kind: str, title: str, text: str = "") -> dict[str, Any]:
    return {"id": sid, "task": task, "kind": kind, "title": title, "text": text, "files": [], "date": JOUR}


def _specs() -> dict[str, Any]:
    return {"entries": [
        _entree_specs("S-00000001", "T-1", "decision", "décision du banc", "porte la cible shop.banc-bascule.test"),
        _entree_specs("S-00000002", "T-3", "delta", f"un séparateur{U2028}de ligne dans une valeur"),
        _entree_specs("S-00000003", "T-2", "verdict", "verdict du banc"),
    ]}


def _ledger() -> dict[str, Any]:
    return {"entries": [
        {"id": "L-1", "category": "constraint", "title": "contrainte du banc", "text": "une", "created": JOUR,
         "tags": ["banc"], "related": "", "status": "active"},
        {"id": "L-2", "category": "lesson", "title": "leçon du banc", "text": "deux", "created": JOUR,
         "tags": [], "related": "T-1", "status": "active"},
    ]}


def _fabriquer(racine: Path, enregistrements: bool) -> None:
    """Les trois magasins nés MONOLITHES par leurs modules ; `enregistrements` ⇒ migrés par leurs modules, puis T-9
    supprimé en forme dossier (une TOMBE, `record: null`)."""
    r = str(racine)
    (racine / BOARD).mkdir(parents=True, exist_ok=True)
    TASKS.save(r, _board())
    LEDGER.save(r, _ledger())
    SPECS.save(r, _specs())
    if not enregistrements:
        return
    assert "migrated" in TASKS.migrate_store(r)
    LEDGER.migrate_store(r)
    SPECS.migrate_store(r, apply=True, lecteurs_non_migres=RAISON_FIXTURE)
    with TASKS.suppress_sync("op-bascule-banc"):
        TASKS.delete_task(r, "T-9")
    assert not (racine / TASKS_JSON).exists() and (racine / BOARD / "tasks" / "T-9.json").is_file()
    assert not (racine / LEDGER_JSON).exists() and not (racine / SPECS_JSON).exists()


def _env_banc(base: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT")}
    env.update(CADRE_STATE_DIR=str(base / "state"), AGENTS_EVENTS_DIR=str(base / "events"), TMPDIR=str(base / "tmp"))
    return env


class _Base(unittest.TestCase):
    """Deux gabarits bâtis UNE fois (monolithe, enregistrements), copiés par témoin."""

    gabarits: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_classe = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.gabarits = Path(cls._tmp_classe.name)
        for d in ("state", "events", "tmp"):
            (cls.gabarits / d).mkdir()
        with mock.patch.dict(os.environ, _env_banc(cls.gabarits), clear=True):
            _fabriquer(cls.gabarits / "monolithe", enregistrements=False)
            _fabriquer(cls.gabarits / "enregistrements", enregistrements=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp_classe.cleanup()

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        for d in ("state", "events", "tmp"):
            (self.base / d).mkdir()
        self.env = _env_banc(self.base)
        patch = mock.patch.dict(os.environ, self.env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def racine(self, forme: str, nom: str = "") -> Path:
        cible = self.base / (nom or forme)
        shutil.copytree(self.gabarits / forme, cible, symlinks=True)
        return cible

    def deux_formes(self, monolithe: Path, enregistrements: Path, rel: Path) -> None:
        """Le monolithe `rel` RECOPIÉ à côté de la forme enregistrement (une vieille branche fusionnée)."""
        shutil.copy2(monolithe / rel, enregistrements / rel)

    def cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *argv], capture_output=True, text=True, env=self.env, timeout=120,
                              check=False)


class L1PlanCibleTests(_Base):
    """L1 — plan_cible : les quatre lecteurs rendent la même chose aux deux formes ; SPECS en deux formes ou corrompu ⇒
    `CibleError` nommé ; board en deux formes ou illisible ⇒ `CibleError` nommé (passe de correction F5). Mutants :
    M-journal-ignoré, M-deux-formes-avalées, M-dossier-prioritaire, M-board-deux-formes-monolithe, M-board-illisible-None."""

    @staticmethod
    def lecture(racine: Path) -> tuple[Any, ...]:
        return (sorted(e["id"] for e in plan_cible.entrees_specs(racine)),
                plan_cible.chantier_de_tache(racine, "T-1"),
                sorted(t["id"] for t in plan_cible.taches_du_board(racine, None)),
                plan_cible._chantiers_du_board(racine))

    def test_l1_les_quatre_lecteurs_rendent_la_meme_chose_aux_deux_formes(self) -> None:
        attendu = self.lecture(self.racine("monolithe"))
        self.assertEqual(attendu, (["S-00000001", "S-00000002", "S-00000003"], CHANTIER,
                                   ["T-1", "T-2", "T-3", "T-9"], {CHANTIER}), "CONTRÔLE monolithe")
        enr = self.racine("enregistrements")
        self.assertEqual(self.lecture(enr), (attendu[0], CHANTIER, ["T-1", "T-2", "T-3"], {CHANTIER}),
                         "forme enregistrement : même lecture, la tombe T-9 écartée")

    def test_l1_specs_en_deux_formes_refus_nomme_jamais_avale(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.deux_formes(mono, enr, SPECS_JSON)
        with self.assertRaises(plan_cible.CibleError) as ctx:
            plan_cible.entrees_specs(enr)
        self.assertIn("SPECS.jsonl", str(ctx.exception))
        self.assertRegex(str(ctx.exception), r"SPECS\.json(?!l)", "le refus nomme AUSSI le monolithe revenu")

    def test_l1_journal_corrompu_refus_nomme(self) -> None:
        enr = self.racine("enregistrements")
        with open(enr / SPECS_JSONL, "ab") as journal:
            journal.write(b"{ pas du json\n")
        with self.assertRaises(plan_cible.CibleError) as ctx:
            plan_cible.entrees_specs(enr)
        self.assertIn("SPECS.jsonl", str(ctx.exception))

    def _quatre_refusent(self, racine: Path, attendu: str) -> None:
        """Les quatre lecteurs du board brut lèvent `CibleError` nommant `attendu` — jamais `None`, `[]` ni le
        monolithe, qui rendaient la jambe de cible INERTE en silence (avis sécurité medium 1 et 2)."""
        lecteurs = {"chantier_de_tache": lambda: plan_cible.chantier_de_tache(racine, "T-9"),
                    "taches_du_board": lambda: plan_cible.taches_du_board(racine, None),
                    "_chantiers_du_board": lambda: plan_cible._chantiers_du_board(racine),
                    "_board_hors_verrou": lambda: plan_depends._board_hors_verrou(racine)}
        for nom, lire in lecteurs.items():
            with self.subTest(lecteur=nom, attendu=attendu):
                with self.assertRaises(plan_cible.CibleError) as ctx:
                    lire()
                self.assertIn(attendu, str(ctx.exception))

    def test_l1_board_en_deux_formes_refus_nomme(self) -> None:
        """M-board-deux-formes-monolithe : `_board_brut` qui rend `lire_board_brut` (le monolithe) ⇒ rouge."""
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.deux_formes(mono, enr, TASKS_JSON)
        self.assertEqual(TASKS.store_form(str(enr)), "les deux")
        self._quatre_refusent(enr, "DEUX FORMES")

    def test_l1_board_absent_rend_none_present_illisible_refus_nomme(self) -> None:
        """M-board-illisible-None : `BoardError` ou JSON corrompu rendus `None` ⇒ rouge. POLARITÉ : ABSENT ⇒ `None`."""
        vide = self.base / "vide"
        (vide / BOARD).mkdir(parents=True)
        self.assertEqual((plan_cible.chantier_de_tache(vide, "T-1"), plan_cible.taches_du_board(vide, None),
                          plan_cible._chantiers_du_board(vide), plan_depends._board_hors_verrou(vide)),
                         (None, [], None, None), "board ABSENT : rien à armer")
        enr = self.racine("enregistrements")
        (enr / BOARD / "tasks" / "T-1.json").write_text("{ pas du json", encoding="utf-8")
        self._quatre_refusent(enr, "illisible")
        mono = self.racine("monolithe")
        (mono / TASKS_JSON).write_text("{ pas du json", encoding="utf-8")
        self._quatre_refusent(mono, "illisible")
        (mono / TASKS_JSON).write_text("[]", encoding="utf-8")
        self._quatre_refusent(mono, "hors forme")


class L2PlanDependsTests(_Base):
    """L2 — plan_depends lit le board et les décisions dans les deux formes. Mutant : M-board-brut."""

    def test_l2_board_et_decisions_aux_deux_formes(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.assertEqual(sorted(plan_depends._taches(plan_depends._board_hors_verrou(mono))),
                         ["T-1", "T-2", "T-3", "T-9"], "CONTRÔLE monolithe")
        self.assertEqual(sorted(plan_depends._taches(plan_depends._board_hors_verrou(enr))), ["T-1", "T-2", "T-3"])
        self.assertEqual(plan_depends.decisions_du_journal(enr), plan_depends.decisions_du_journal(mono))
        self.assertEqual(plan_depends.decisions_du_journal(enr), {"S-00000001"})


class L3PlanPoolTests(_Base):
    """L3 — plan_pool : `check` (CLI, `--root`) au même verdict aux deux formes ; tombe écartée ; deux formes, id ≠ nom
    ⇒ rc 1 nommé ; le journal fusionné en union lu par les règles de `specs._parse_journal`, même verdict que
    `specs.read_journal`. Mutants : M-tombe-comptée, M-id-≠-nom, M-deux-formes, M-splitlines, M-doublon-compté,
    M-divergent-accepté."""

    def check(self, racine: Path, tid: str) -> subprocess.CompletedProcess:
        return self.cli(str(CORE / "plan_pool.py"), "--root", str(racine), "check", tid)

    def test_l3_no_plan_identique_aux_deux_formes_et_tombe_ecartee(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        controle = self.check(mono, "T-3")
        self.assertEqual(controle.returncode, 10, controle.stdout + controle.stderr)
        self.assertTrue(controle.stdout.startswith("T-3 NO_PLAN"), controle.stdout)
        p = self.check(enr, "T-3")
        self.assertEqual((p.returncode, p.stdout), (10, controle.stdout), p.stderr)
        tombe = self.check(enr, "T-9")
        self.assertEqual(tombe.returncode, 16, tombe.stdout + tombe.stderr)
        self.assertIn("absente du board", tombe.stdout)

    def test_l3_deux_formes_du_board_refus_nomme(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.deux_formes(mono, enr, TASKS_JSON)
        p = self.check(enr, "T-3")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("TASKS.json", p.stderr)
        self.assertIn(str(Path("board") / "tasks"), p.stderr)

    def test_l3_id_qui_n_est_pas_son_nom_refus_nomme(self) -> None:
        enr = self.racine("enregistrements")
        shutil.copy2(enr / BOARD / "tasks" / "T-2.json", enr / BOARD / "tasks" / "T-77.json")
        p = self.check(enr, "T-3")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("T-77.json", p.stderr)

    def test_l3_deux_formes_du_journal_refus_nomme(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.deux_formes(mono, enr, SPECS_JSON)
        p = self.check(enr, "T-3")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("SPECS.jsonl", p.stderr)
        self.assertIn("specs.py migrate --apply", p.stderr)

    def verdicts(self, racine: Path) -> tuple[Any, Any]:
        """(plan_pool, specs.read_journal) : la liste triée des ids, ou le type « refus »."""
        sortie: list[Any] = []
        for lire, refus in ((lambda: POOL.load_specs(racine), POOL.PoolError),
                            (lambda: SPECS.read_journal(racine / SPECS_JSONL), SPECS.SpecsError)):
            try:
                sortie.append(sorted(e["id"] for e in lire()))
            except refus as exc:
                sortie.append(("refus", str(exc)))
        return sortie[0], sortie[1]

    def test_l3_journal_fusionne_en_union_meme_verdict_que_read_journal(self) -> None:
        enr = self.racine("enregistrements")
        brut = (enr / SPECS_JSONL).read_bytes()
        lignes = brut.split(b"\n")
        entete = lignes[0]
        sans_text = [ligne for ligne in lignes[1:] if b'"text":""' in ligne]
        self.assertTrue(sans_text, "une entrée au texte vide doit exister pour le jumeau text/files")
        jumeau = json.loads(sans_text[0])
        del jumeau["text"]
        union = brut + b"\n" + entete + b"\n" + lignes[2] + b"\n" + SPECS.journal_line(jumeau).encode("utf-8")
        (enr / SPECS_JSONL).write_bytes(union)
        pool, reference = self.verdicts(enr)
        self.assertEqual(pool, ["S-00000001", "S-00000002", "S-00000003"], "union : UNE entrée par id")
        self.assertEqual(pool, reference)
        self.assertIn(U2028.encode("utf-8"), union, "U+2028 brut dans une valeur, lu en UNE ligne")

    def test_l3_doublon_divergent_et_ligne_non_json_refus_comme_read_journal(self) -> None:
        for nom, delta, ligne in (("divergent", None, "les lignes 2 et 5"), ("non-json", b"{ pas du json\n", ":5 ")):
            with self.subTest(nom):
                enr = self.racine("enregistrements", f"enregistrements-{nom}")
                brut = (enr / SPECS_JSONL).read_bytes()
                if delta is None:
                    autre = json.loads(brut.split(b"\n")[1])
                    autre["title"] = "réécrit"
                    delta = SPECS.journal_line(autre).encode("utf-8")
                (enr / SPECS_JSONL).write_bytes(brut + delta)
                pool, reference = self.verdicts(enr)
                self.assertEqual(pool[0], "refus", pool)
                self.assertEqual(reference[0], "refus", reference)
                self.assertIn(str(enr / SPECS_JSONL), pool[1])
                self.assertIn(ligne, pool[1], "le refus nomme la (les) LIGNE(S)")


class L4PlanWavesTests(_Base):
    """L4 — plan_waves et feuille_de_route (CLI) rendent la même sortie aux deux formes. Mutant : M-plan_waves-brut."""

    def test_l4_vagues_et_feuille_de_route_identiques_aux_deux_formes(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        with TASKS.suppress_sync("op-bascule-banc"):  # le monolithe porte la MÊME suppression que la forme dossier
            TASKS.delete_task(str(mono), "T-9")
        for script, args in (("plan_waves.py", ("waves", "--chantier", CHANTIER, "--json")),
                             ("feuille_de_route.py", ("--chantier", CHANTIER, "--json"))):
            with self.subTest(script):
                sorties = []
                for racine in (mono, enr):
                    p = self.cli(str(CORE / script), "--root", str(racine), *args)
                    self.assertEqual(p.returncode, 0, f"{racine.name} : {p.stderr}")
                    sorties.append(p.stdout.replace(str(racine), "<RACINE>"))
                self.assertIn('"T-3"', sorties[1])
                self.assertEqual(sorties[1], sorties[0], "même sortie aux deux formes")


class L5CheckStaleTests(_Base):
    """L5 — check-stale-justification.sh : VERT sur le dossier, [E0] sur un enregistrement corrompu ; plan_pool chargé
    depuis le dossier DU SCRIPT, jamais sous `--root`. Mutant : M-charge-depuis-root."""

    def scan(self, racine: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(CORE / "check-stale-justification.sh"), "--root", str(racine)],
                              capture_output=True, text=True, env=self.env, timeout=300, check=False)

    def test_l5_vert_aux_deux_formes_et_e0_sur_enregistrement_corrompu(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        piege = enr / "core-scripts" / "plan_pool.py"
        piege.parent.mkdir()
        sentinelle = enr / "PIEGE_EXECUTE"
        piege.write_text(f"open({str(sentinelle)!r}, 'w').close()\nraise SystemExit(99)\n", encoding="utf-8")
        for racine in (mono, enr):
            p = self.scan(racine)
            self.assertEqual(p.returncode, 0, f"{racine.name} : {p.stdout}{p.stderr}")
            self.assertIn("check-stale-justification: VERT", p.stdout)
        self.assertFalse(sentinelle.exists(), "le plan_pool PIÉGÉ de la fixture a été exécuté")
        (enr / BOARD / "tasks" / "T-1.json").write_text("{ pas du json", encoding="utf-8")
        p = self.scan(enr)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("[E0]", p.stdout)
        # Passe de correction F5 (constat 6) : le [E0] nomme le DOSSIER du board, jamais TASKS.json absent.
        # Mutant : la ligne [E0] ramenée à `{BOARD}` ⇒ rouge.
        e0 = next(ligne for ligne in p.stdout.splitlines() if "[E0]" in ligne)
        self.assertIn(f"({enr / BOARD})", e0)
        self.assertNotIn("TASKS.json", e0)
        (mono / TASKS_JSON).write_text("{ pas du json", encoding="utf-8")
        e0 = next(ligne for ligne in self.scan(mono).stdout.splitlines() if "[E0]" in ligne)
        self.assertIn(f"({mono / TASKS_JSON})", e0, "POLARITÉ : monolithe seul ⇒ TASKS.json nommé")


class L6LoadtestTests(_Base):
    """L6 — loadtest lit le journal sans surcharge (`specs.load` de SA racine) et par `AGENTS_SPECS_PATH` nommant un
    `.jsonl`. Mutant : M-specs-absent."""

    def test_l6_entrees_specs_aux_deux_formes(self) -> None:
        for forme in ("monolithe", "enregistrements"):
            with self.subTest(forme):
                racine = self.racine(forme)
                bin_ = racine / ".agents" / "bin"  # ROOT de loadtest = la racine de SA copie
                bin_.mkdir(exist_ok=True)
                for nom in ("loadtest.py", "specs.py", "etat_lecture.py"):
                    shutil.copy2(BIN / nom, bin_ / nom)
                lt = charger(f"bascule_banc_loadtest_{forme}", bin_ / "loadtest.py")
                os.environ.pop("AGENTS_SPECS_PATH", None)
                ids = sorted(e["id"] for e in lt._entrees_specs(lt.chemin_specs()))
                self.assertEqual(ids, ["S-00000001", "S-00000002", "S-00000003"])
                # La sonde M2 de l'étape 8 passe le chemin du MONOLITHE sans surcharge : il n'est que tracé.
                self.assertEqual(sorted(e["id"] for e in lt._entrees_specs(racine / SPECS_JSON)), ids)
                magasin = racine / (SPECS_JSONL if forme == "enregistrements" else SPECS_JSON)
                self.assertEqual(lt.chemin_specs().resolve(), magasin.resolve(),
                                 "le chemin TRACÉ (`specs` de la trace) nomme la forme lue")
                with mock.patch.dict(os.environ, {"AGENTS_SPECS_PATH": str(magasin)}):
                    self.assertEqual(sorted(e["id"] for e in lt._entrees_specs(lt.chemin_specs())), ids)


class L7NightApproveTests(_Base):
    """L7 — `night_approve --delivered` sur le journal : « journal absent » ssi NI SPECS.json NI SPECS.jsonl.
    Mutant : M-store_path."""

    def test_l7_delivered_lit_le_journal(self) -> None:
        for forme in ("monolithe", "enregistrements"):
            with self.subTest(forme):
                p = self.cli(str(BIN / "night_approve.py"), "--root", str(self.racine(forme)), "--delivered", "T-1")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn("aucun marqueur night-delivered en vigueur", p.stdout)
        vide = self.base / "vide"
        (vide / STATE / "specs").mkdir(parents=True)
        p = self.cli(str(BIN / "night_approve.py"), "--root", str(vide), "--delivered", "T-1")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("journal absent", p.stdout + p.stderr)


class L8DashboardTests(_Base):
    """L8 — réécrire UN enregistrement change l'empreinte ; un lease de `board/sync_outbox/` change
    `snapshot_fingerprint`. Mutants : M-sans-dossier, M-sans-outbox."""

    def test_l8_un_enregistrement_reecrit_change_les_empreintes(self) -> None:
        enr = self.racine("enregistrements")
        for rel, empreinte in ((BOARD / "tasks" / "T-1.json", READERS.snapshot_fingerprint),
                               (BOARD / "epics" / "E-01.json", READERS.snapshot_fingerprint),
                               (ENTRIES / "L-1.json", READERS.views_fingerprint),
                               (SPECS_JSONL, READERS.views_fingerprint)):
            with self.subTest(str(rel)):
                avant = empreinte(enr, None, None)
                chemin = enr / rel
                chemin.write_bytes(chemin.read_bytes() + b"\n")
                self.assertNotEqual(empreinte(enr, None, None), avant, f"{rel} réécrit, empreinte inchangée")

    def test_l8_un_lease_de_l_outbox_change_le_snapshot(self) -> None:
        enr = self.racine("enregistrements")
        outbox = enr / BOARD / "sync_outbox"
        outbox.mkdir(exist_ok=True)
        intent = outbox / "op-banc.json"
        intent.write_text(json.dumps({"correlation": "op-banc", "intent": {}}), encoding="utf-8")
        avant = READERS.snapshot_fingerprint(enr, None, None)
        intent.write_text(json.dumps({"correlation": "op-banc", "intent": {"lease": {"owner": "banc"}}}),
                          encoding="utf-8")
        self.assertNotEqual(READERS.snapshot_fingerprint(enr, None, None), avant)


class L9KickoffTests(_Base):
    """L9 — le remède de kickoff_guard sur un journal illisible nomme le DOSSIER `.agents/state/specs/`."""

    def test_l9_remede_nomme_le_dossier_du_journal(self) -> None:
        enr = self.racine("enregistrements")
        (enr / kg.GATE_RELPATH).parent.mkdir(parents=True, exist_ok=True)
        (enr / kg.GATE_RELPATH).write_text("T-1\n", encoding="utf-8")
        with open(enr / SPECS_JSONL, "ab") as journal:
            journal.write(b"{ pas du json\n")
        gate = kg.read_gate(enr)
        board, journal_lu = kg.collect(enr, gate)
        d = kg.decide("src/a.py", gate, board, journal_lu)
        self.assertEqual(d.rule, "journal-unreadable", d.reason)
        self.assertIn("`git restore .agents/state/specs/`", d.reason)


class C2LedgerDeuxFormesTests(_Base):
    """C2 (réserve au mandat) — COMPORTEMENTAL : sur une racine en deux formes, le refus de `ledger.save` ne conseille
    aucun `rm -r` (passe de correction de la fournée 4 de T-1009, ledger.py hors write-set)."""

    def test_c2_le_refus_deux_formes_ne_conseille_pas_rm_r(self) -> None:
        mono, enr = self.racine("monolithe"), self.racine("enregistrements")
        self.deux_formes(mono, enr, LEDGER_JSON)
        self.assertEqual(LEDGER.store_form(str(enr)), "both")
        with self.assertRaises(LEDGER.LedgerError) as ctx:
            LEDGER.save(str(enr), _ledger())
        message = str(ctx.exception)
        self.assertIn("nothing was written", message)
        self.assertNotIn("rm -r", message)


if __name__ == "__main__":
    unittest.main()
