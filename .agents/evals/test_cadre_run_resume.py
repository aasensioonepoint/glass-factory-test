#!/usr/bin/env python3
"""`check_run_resume` — UN RUN INTERROMPU SE REJOUE DEPUIS LE LEDGER V3 SANS
EFFET DOUBLE (T-00000640, étape D point 7 du LOT-2 / Phase 2, T-012).

CE QUI EST NOMMÉ ICI, AVANT LE FLIP (R-A10 du plan §12) :

  * LE « RUN ». Une séquence ORDONNÉE d'opérations appliquée au store V3. Chaque
    opération est un `RunStep` (`agentic_v3/db/event_store.py`) porteur d'un
    `operation_id` : son identité durable `(operation_id, event_kind, attempt)`
    est unique dans `events_ledger` (index `uq_events_operation_attempt`), donc
    réappliquer la MÊME opération est un no-op.
  * UNE ÉTAPE = une opération = un `RunStep`. Le run de référence en compte
    CINQ (N ≥ 4) : `TASK_CREATED` → `CODE_GENERATED` → `CRITIC_VERDICT(passed=False)`
    → `CRITIC_VERDICT(passed=True)` → `TEST_RUN(passed=True)`. Population non vide
    assertée (le ledger porte N événements, la projection finale existe).
  * LE MAGASIN REJOUÉ. `events_ledger` du store V3 (`agentic_v3`), sur un FICHIER
    TEMPORAIRE RÉEL (`tempfile.mkdtemp`), jamais `:memory:` : la source est
    introspectée depuis l'appelant par une connexion `sqlite3` directe.
  * LE CAS DE TEST.
    `test_un_run_interrompu_a_une_etape_ARBITRAIRE_rejoue_depuis_le_ledger_donne_le_meme_resultat`
    interrompt le run à CHAQUE k ∈ [1, N-1] (pas seulement le dernier), rouvre le
    fichier et rejoue le run ENTIER.

ARBITRAGE RENDU DANS LA TÂCHE, ne pas le rouvrir : « le même résultat » =
**(c) même ÉTAT FINAL des projections ET aucun effet rejoué deux fois** — aucun
événement dupliqué dans `events_ledger`, aucune projection ré-appliquée. Un rejeu
idempotent sur l'état mais pas sur les effets rejoue les gestes.

CE QUE L'EXISTANT TENAIT, ET CE QU'IL FALLAIT AJOUTER. L'append idempotent
existait déjà : `EventStore.append_event` écrit l'événement ET sa projection dans
UNE transaction, et l'index `uq_events_operation_attempt` fait qu'un ré-append de
même identité lève `sqlite3.IntegrityError` (rollback, projection jamais rejouée).
Ce qui MANQUAIT était une fonction qui rejoue un run ENTIER en traitant ce refus
comme un saut « déjà appliqué » — `EventStore.replay_run`, minimale, du côté
`agentic_v3` (jamais dans `src/cadre/`). La reprojection depuis le ledger est
alors implicite : les projections des k opérations d'avant l'arrêt ont persisté
sur le fichier, celles des opérations restantes sont ré-appliquées au rejeu, et
l'index empêche toute double application.

CONTRÔLE NÉGATIF INTÉGRÉ. Un rejeu SANS idempotence — on force un `attempt` neuf,
donc l'identité durable change et l'index ne rattrape plus le doublon — fait
ROUGIR ce témoin (`assertRaises(AssertionError)`) : les événements s'empilent.

BORNES ÉCRITES. Le magasin de leçons `src/cadre/ledger/` n'est PAS concerné ici
(autre store, autre tâche). La divergence board/V3 — `reconcile_v3_to_board` sans
appelant runtime — n'est PAS traitée : le rejeu porte sur le seul `events_ledger`
du store V3.

Entrée `check_run_resume` du `checks.manifest.json`, phase 2. Tourne dans la porte
par `pytest` (`pytest.ini` liste `.agents/evals` dans `testpaths`), à côté des
autres implémentations de check. C'est aussi pourquoi ce témoin vit sous
`.agents/evals/` et non `agentic_v3/tests/` : toutes les `implementation` du
manifeste y résident, et `test_checks_manifest.py` — qui rejoue chaque banc de
check `actif` — y calcule `ROOT` de la même façon.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_run_resume_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "agentic_v3")

from agentic_v3.db.event_store import EventStore, RunStep  # noqa: E402
from agentic_v3.db import run_export as v3run  # noqa: E402


def test_provenance_v3_en_processus():
    attendu = _VENDOR.exiger(ROOT, "agentic_v3")
    assert Path(sys.modules["agentic_v3"].__file__).resolve().parent == attendu.resolve()


def test_vendor_seul_resume(tmp_path):
    """Un arbre vendor autonome gagne sur un homonyme placé sur PYTHONPATH."""
    kit = tmp_path / "kit"
    banc = kit / ".agents" / "evals" / Path(__file__).name
    banc.parent.mkdir(parents=True)
    shutil.copyfile(__file__, banc)
    chemin_resolveur = kit / ".agents" / "bin" / "vendor_paths.py"
    chemin_resolveur.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / ".agents" / "bin" / "vendor_paths.py", chemin_resolveur)
    source = _VENDOR.exiger(ROOT, "agentic_v3")
    cible = kit / ".agents" / "vendor" / "agentic_v3"
    shutil.copytree(source, cible, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    etranger = tmp_path / "etranger" / "agentic_v3"
    etranger.mkdir(parents=True)
    (etranger / "__init__.py").write_text("", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(etranger.parent))
    sonde = ("import runpy, sys; module = runpy.run_path(sys.argv[1], "
             "run_name='v3_import_probe'); print(module['v3run'].__file__)")
    resultat = subprocess.run([sys.executable, "-B", "-c", sonde, str(banc)],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    attendu = cible / "db" / "run_export.py"
    assert resultat.returncode == 0, resultat.stderr
    assert Path(resultat.stdout.strip()).resolve() == attendu.resolve()


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """T-00000650 : chaque `EventStore` écrit son export sous une racine de TEST
    (`CADRE_PROJECT_ROOT`) et sa base sous `CADRE_STATE_DIR`, auteur FIXÉ (jambe
    conteneur en root sans `git config user.email`). La liaison `ROOT` reste, et
    les bras neufs (témoins 6/7/9) sont sous `tempfile` : ils n'ont aucun site
    nommant le `runs/` RÉEL du dépôt. La greffe passe par la PORTE UNIQUE
    (L-00000500) pour rester franchissable — sinon elle éteint le témoin d'aval."""
    from conftest import greffe_email_git_franchissable

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, v3run)


@pytest.mark.email_git_reel
def test_la_greffe_email_git_est_franchissable_ici():
    """TÉMOIN (L-00000500) — sous le marqueur `email_git_reel`, la fixture autouse
    `_isolation_export_run` SAUTE sa greffe et le VRAI `_email_git` reste en place
    (def -> `__name__ == "_email_git"`, la greffe étant un `<lambda>`). MUTATION
    (greffe non franchissable) : l'objet devient le `<lambda>` et rougit."""
    assert v3run._email_git.__name__ == "_email_git", (
        "greffe NON franchie : la porte unique n'a pas sauté sous email_git_reel"
    )


#: La tâche du run de référence — un identifiant local au banc, sans lien avec le
#: board.
TACHE = "T-RUN-RESUME"

#: LES COLONNES DE PROJECTION QUI EXPRIMENT L'ÉTAT — toutes sauf `last_updated`,
#: horodatage volatil qui bouge à chaque écriture et fausserait l'égalité.
_COLONNES_ETAT = (
    "task_id", "req_id", "spec_version", "status",
    "current_assignee", "code_diff", "retry_count", "is_blocked",
)


def _run_de_reference() -> list[RunStep]:
    """Le RUN : cinq opérations ordonnées, chacune avec son `operation_id` STABLE.

    L'étape `CRITIC_VERDICT(passed=False)` incrémente `retry_count` : c'est un
    effet SENSIBLE au rejeu, donc un discriminant de plus si une opération était
    appliquée deux fois.
    """
    return [
        RunStep("run-op-1", TACHE, "planner", "TASK_CREATED",
                {"req_id": "REQ-RESUME", "spec_version": 1}),
        RunStep("run-op-2", TACHE, "dev-multi", "CODE_GENERATED",
                {"code_diff": "diff --git a b"}),
        RunStep("run-op-3", TACHE, "critic-opus", "CRITIC_VERDICT",
                {"passed": False, "verdict": "NO_GO"}),
        RunStep("run-op-4", TACHE, "critic-opus", "CRITIC_VERDICT",
                {"passed": True, "verdict": "GO"}),
        RunStep("run-op-5", TACHE, "tester", "TEST_RUN",
                {"passed": True}),
    ]


class RunResumeTests(unittest.TestCase):
    def _fichier_store(self) -> Path:
        """Un store V3 sur FICHIER RÉEL, nettoyé en fin de test."""
        base = Path(tempfile.mkdtemp(prefix="cadre_run_resume_")).resolve()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        return base / "v3_event_store.db"

    @staticmethod
    def _compter_evenements(db_path: Path) -> int:
        """Compte lu DIRECTEMENT dans `events_ledger` — la source que le témoin
        prétend rejouer, introspectée par l'appelant (impossible sur `:memory:`)."""
        conn = sqlite3.connect(str(db_path))
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0])
        finally:
            conn.close()

    @staticmethod
    def _etat(projection: dict | None) -> tuple | None:
        if projection is None:
            return None
        return tuple(projection.get(c) for c in _COLONNES_ETAT)

    def _reference(self, steps: list[RunStep]) -> tuple[tuple, int]:
        """Joue le run d'un trait sur un store neuf → (état de référence, N)."""
        db = self._fichier_store()
        store = EventStore(db)
        tally = store.replay_run(steps)
        self.assertEqual(tally["total"], len(steps))
        self.assertEqual(tally["applied"], len(steps), "un run neuf n'a rien à sauter")
        proj = store.get_task_projection(TACHE)
        self.assertIsNotNone(proj, "population VIDE — la projection de référence n'existe pas")
        etat = self._etat(proj)
        compte = self._compter_evenements(db)
        self.assertEqual(compte, len(steps),
                         "le run de référence n'a pas déposé un événement par opération")
        return etat, compte

    def _verifier_reprise(self, k: int, rejeu) -> None:
        """Prouve la reprise à l'interruption `k` avec la fonction de rejeu donnée.

        `rejeu(store, steps)` rejoue le run entier depuis le début. En nominal
        c'est `store.replay_run(steps)` ; le contrôle négatif fournit une variante
        NON idempotente. Les assertions sont IDENTIQUES dans les deux cas : c'est
        ce qui fait qu'un rejeu fautif ROUGIT (AssertionError) plutôt que de passer.
        """
        steps = _run_de_reference()
        n = len(steps)
        self.assertGreaterEqual(n, 4, "le run de référence doit porter au moins 4 opérations")
        etat_ref, compte_ref = self._reference(steps)

        db = self._fichier_store()
        # Interruption : on n'applique QUE les k premières opérations, puis on
        # lâche le store (arrêt). Chaque `append_event` a déjà committé sa propre
        # transaction, donc l'état persisté est exactement ces k opérations.
        EventStore(db).replay_run(steps[:k])
        self.assertEqual(self._compter_evenements(db), k,
                         "l'interruption n'a pas laissé exactement k événements")

        # Reprise : on ROUVRE le fichier (nouvel EventStore sur le même chemin) et
        # on rejoue le run ENTIER depuis le début.
        rejeu(EventStore(db), steps)

        # (c) MÊME ÉTAT FINAL des projections.
        proj_apres = EventStore(db).get_task_projection(TACHE)
        self.assertEqual(self._etat(proj_apres), etat_ref,
                         f"état final divergent après reprise à k={k}")
        # (c) AUCUN effet rejoué deux fois : le ledger porte EXACTEMENT N événements.
        self.assertEqual(self._compter_evenements(db), compte_ref,
                         f"événement dupliqué au rejeu (k={k}) — un effet a été rejoué")
        # L'état rejoué se RELIT (utilisable), depuis une connexion neuve.
        relu = EventStore(db).get_task_projection(TACHE)
        self.assertIsNotNone(relu, "l'état rejoué ne se relit pas — inutilisable")
        self.assertEqual(relu["status"], "COMPLETED",
                         "le run rejoué ne se relit pas dans son état terminal")

    def test_un_run_interrompu_a_une_etape_ARBITRAIRE_rejoue_depuis_le_ledger_donne_le_meme_resultat(self):
        """Le cas central : interruption à CHAQUE k ∈ [1, N-1], pas seulement le
        dernier. Un rejeu qui ne marche que depuis la fin ne prouve rien."""
        n = len(_run_de_reference())
        for k in range(1, n):
            with self.subTest(interruption=k):
                self._verifier_reprise(k, lambda store, steps: store.replay_run(steps))

    def test_un_rejeu_de_MEME_identite_avec_contenu_DIVERGENT_leve_ValueError(self):
        """C1 (correctif binôme PORTE 3) — `apply_run_step` n'avale QUE la violation
        de l'IDENTITÉ DURABLE. Rejouer sous le MÊME `(operation_id, event_kind,
        attempt)` un événement au PAYLOAD divergent lève `ValueError` (jamais un
        skip silencieux), tandis qu'un rejeu IDENTIQUE reste un skip."""
        db = self._fichier_store()
        store = EventStore(db)
        op = RunStep("run-op-1", TACHE, "planner", "TASK_CREATED",
                     {"req_id": "REQ-RESUME", "spec_version": 1})
        self.assertTrue(store.apply_run_step(op), "le premier append doit réussir")
        # MÊME operation_id / event_type / attempt, PAYLOAD divergent.
        divergent = op._replace(payload={"req_id": "REQ-AUTRE", "spec_version": 9})
        with self.assertRaises(ValueError):
            store.apply_run_step(divergent)
        # Rejeu IDENTIQUE : skip silencieux (False), aucun événement de plus.
        self.assertFalse(store.apply_run_step(op),
                         "un rejeu strictement identique doit être un skip")
        self.assertEqual(self._compter_evenements(db), 1,
                         "le contenu divergent OU le skip a dupliqué un événement")

    def _rejeu_est_un_skip(self, premier: dict, rejoue: dict, op_id: str) -> Path:
        """T-00000680 — `premier` s'écrit, `rejoue` (MÊME identité durable) est un
        skip : `False`, et le ledger porte UN événement. Rend le chemin du store."""
        db = self._fichier_store()
        store = EventStore(db)
        op = RunStep(op_id, TACHE, "dev-multi", "CODE_GENERATED", premier)
        self.assertTrue(store.apply_run_step(op), "le premier append doit réussir")
        self.assertFalse(store.apply_run_step(op._replace(payload=rejoue)),
                         "même contenu rejoué : un skip, jamais une divergence")
        self.assertEqual(self._compter_evenements(db), 1)
        return db

    def test_W1_rejeu_cles_PERMUTEES_meme_contenu_est_un_skip(self):
        """W1 — l'ORDRE des clés n'est pas du contenu. ROUGE au BASE, qui comparait
        des CHAÎNES JSON (`ValueError same durable identity, DIFFERENT content`)."""
        self._rejeu_est_un_skip({"b": 1, "a": 2}, {"a": 2, "b": 1}, "op-w1")

    def test_W2_rejeu_NaN_par_un_AUTRE_objet_est_un_skip(self):
        """W2 — NaN n'est égal à RIEN, pas même à un autre NaN : vert au BASE, ROUGE
        sous la comparaison d'objets littérale (`json.loads(stocké) !=
        rediger_arbre(payload)`), d'où la comparaison de formes CANONIQUES."""
        self._rejeu_est_un_skip({"x": float("nan")}, {"x": float("nan")}, "op-w2")

    def test_W3_rejeu_cles_MIXTES_int_et_str_est_un_skip(self):
        """W3 — JSON rend la clé `1` en `"1"`. Vert au BASE ; ROUGE sous la forme
        littérale (`{"1": …} != {1: …}`) ET sous un tri DIRECT du côté entrant
        (`json.dumps({1: "a", "b": 2}, sort_keys=True)` lève `TypeError`)."""
        self._rejeu_est_un_skip({1: "a", "b": 2}, {1: "a", "b": 2}, "op-w3")

    def test_W4_payload_json_CORROMPU_au_store_leve_ValueError_nommee(self):
        """W4 — un `payload_json` ILLISIBLE au store est un contenu DIVERGENT :
        `ValueError` « DIFFERENT content » de type EXACT (`JSONDecodeError` et
        `UnicodeDecodeError` en sont des sous-classes), jamais CHAÎNÉE à l'erreur de
        lecture (son `.doc` porte le texte stocké). Quatre lectures qui échouent : JSON
        cassé, BLOB non UTF-8, imbrication de 10**6 niveaux (5000 ne lève PAS sous
        Python 3.14 — mesuré, T-00000680 passe binôme) et entier de plus de 4300
        chiffres (`ValueError` NU de `int()`, fable F2 passe 2). Corruption par `UPDATE`
        direct : aucun trigger ne garde `events_ledger` en écriture (mesuré au plan)."""
        lectures = (ValueError, RecursionError)  # JSONDecodeError, UnicodeDecodeError ⊂ ValueError
        geant = '{"x":' + "1" * max(4301, sys.get_int_max_str_digits() + 1) + "}"
        db = self._fichier_store()  # UN store : une base vide se reconstruit des exports
        store = EventStore(db)
        for nom, stocke in (("json", "{corrompu"), ("blob", b"\x80\x81"),
                            ("imbrication", "[" * 10**6 + "]" * 10**6), ("entier", geant)):
            with self.subTest(corruption=nom):
                op = RunStep(f"op-w4-{nom}", TACHE, "dev-multi", "CODE_GENERATED",
                             {"code_diff": "d"})
                self.assertTrue(store.apply_run_step(op))
                avant = self._compter_evenements(db)
                conn = sqlite3.connect(str(db))
                try:
                    conn.execute("UPDATE events_ledger SET payload_json = ? "
                                 "WHERE operation_id = ?", (stocke, op.operation_id))
                    conn.commit()
                finally:
                    conn.close()
                with self.assertRaisesRegex(ValueError, "DIFFERENT content") as cm:
                    store.apply_run_step(op)
                self.assertIs(type(cm.exception), ValueError)
                self.assertNotIsInstance(cm.exception.__cause__ or cm.exception.__context__,
                                         lectures, "l'erreur de lecture est CHAÎNÉE")
                self.assertEqual(self._compter_evenements(db), avant)

    def test_W5_rejeu_d_une_cle_DOUBLEE_n_est_jamais_absorbe(self):
        """W5 (critic-opus) — `{1: "S", "1": "b"}` s'écrit `{"1": "S", "1": "b"}`, qu'un
        `json.loads` nu réduit à `{"1": "b"}` : le rejeu `{"1": "b"}` était ABSORBÉ en
        skip (régression de e56de850 sur « never silently absorbed »). Les paires triées
        gardent le doublon : `ValueError`. Le MÊME payload, permuté, reste un skip — la
        borne F3 écrite au docstring : égalité de MULTISET, pas « dernière clé gagne »."""
        db = self._fichier_store()
        store = EventStore(db)
        op = RunStep("op-w5", TACHE, "dev-multi", "CODE_GENERATED", {1: "S", "1": "b"})
        self.assertTrue(store.apply_run_step(op))
        self.assertFalse(store.apply_run_step(op._replace(payload={"1": "b", 1: "S"})),
                         "le MÊME payload, permuté, doit rester un skip")
        with self.assertRaisesRegex(ValueError, "DIFFERENT content"):
            store.apply_run_step(op._replace(payload={"1": "b"}))
        self.assertEqual(self._compter_evenements(db), 1)

    def test_W6_rejeu_d_un_payload_PROFOND_est_un_skip(self):
        """W6 (critic-opus F1, passe binôme 2) — 400 niveaux d'objets s'écrivent PUIS se
        rejouent en skip. Le canon à 3 niveaux par objet levait `RecursionError` NU au
        rejeu dès ~329 niveaux sous Python 3.11 ; à plat, ~496 (pile quasi vide).
        DISCRIMINE sous 3.11 seul (rouge mesuré) ; VACANT sous 3.14 — CI ET porte locale
        (`python3`) —, où la récursion du codec JSON ne mord pas à cette profondeur."""
        profond: dict = {"f": 1}
        for _ in range(400):
            profond = {"a": profond}
        self._rejeu_est_un_skip(profond, profond, "op-w6")

    def test_X7_rejeu_d_un_payload_a_SECRET_est_un_skip_cote_entrant_REDIGE(self):
        """X7 (exec-critic) — le ledger stocke le payload RÉDIGÉ, donc le rejeu du
        MÊME payload brut n'est un skip que si le côté ENTRANT est rédigé avant la
        comparaison. Le second assert rend le témoin non vacant : la rédaction a bien
        eu lieu au stockage. Secret ASSEMBLÉ à l'exécution (gitleaks, SAST)."""
        secret = "sk-" + "A" * 24
        db = self._rejeu_est_un_skip({"note": f"cle {secret}"}, {"note": f"cle {secret}"}, "op-x7")
        conn = sqlite3.connect(str(db))
        try:
            stocke = conn.execute("SELECT payload_json FROM events_ledger").fetchone()[0]
        finally:
            conn.close()
        self.assertNotIn(secret, stocke, "le secret n'a pas été rédigé au stockage")

    def test_X8_rejeu_de_CLES_secretes_en_collision_PERMUTEES_est_un_skip(self):
        """X8 (binôme F2, critic-opus F2) — deux jetons `ghp_` en CLÉS se rédigent en un même
        marqueur ; la BASE 63f63f35 gardait la DERNIÈRE valeur insérée, l'ordre devenait du
        contenu et ce rejeu levait « same durable identity, DIFFERENT content ». Jetons
        ASSEMBLÉS à l'exécution (gitleaks, SAST)."""
        a, b = "ghp_" + "A" * 36, "ghp_" + "B" * 36
        self._rejeu_est_un_skip({a: 1, b: 2}, {b: 2, a: 1}, "op-x8")

    def test_meme_identite_meme_payload_TRIPLET_divergent_leve_ValueError(self):
        """Triplet (exec-critic) — MÊME identité durable, MÊME payload, mais `task_id`,
        `agent_role` OU `event_type` divergent, chacun SEUL : `ValueError`. `event_kind`
        est FIXÉ : sinon il suit `event_type`, l'identité change et rien n'entre en
        collision."""
        db = self._fichier_store()
        store = EventStore(db)
        op = RunStep("op-tri", TACHE, "dev-multi", "CODE_GENERATED", {"code_diff": "d"},
                     event_kind="K")
        self.assertTrue(store.apply_run_step(op))
        for champ, autre in (("task_id", "T-AUTRE"), ("agent_role", "critic"),
                             ("event_type", "TEST_RUN")):
            with self.subTest(champ=champ):
                with self.assertRaisesRegex(ValueError, "DIFFERENT content"):
                    store.apply_run_step(op._replace(**{champ: autre}))
        self.assertEqual(self._compter_evenements(db), 1)

    def test_meme_operation_id_event_type_different_donne_DEUX_evenements(self):
        """C1 (borne écrite au docstring) — deux étapes de MÊME `operation_id` mais
        d'`event_type` différent ont des identités durables DIFFÉRENTES (event_kind
        par défaut = event_type) : les DEUX s'écrivent. C'est VOULU, pas une
        collision — le garde ne mord que sur la MÊME `(operation_id, event_kind,
        attempt)`."""
        db = self._fichier_store()
        store = EventStore(db)
        a = RunStep("op-partagee", TACHE, "planner", "TASK_CREATED",
                    {"req_id": "REQ-RESUME", "spec_version": 1})
        b = RunStep("op-partagee", TACHE, "dev-multi", "CODE_GENERATED",
                    {"code_diff": "diff --git a b"})
        self.assertTrue(store.apply_run_step(a))
        self.assertTrue(store.apply_run_step(b),
                        "un event_type différent est une autre identité durable — "
                        "il doit s'écrire")
        self.assertEqual(self._compter_evenements(db), 2)

    def test_un_rejeu_SANS_idempotence_fait_ROUGIR_le_temoin(self):
        """CONTRÔLE NÉGATIF. On force un `attempt` neuf au rejeu : l'identité
        durable `(operation_id, event_kind, attempt)` change, l'index d'unicité ne
        rattrape plus le doublon, les événements s'empilent — et les MÊMES
        assertions que le cas nominal doivent alors ÉCHOUER."""
        def rejeu_non_idempotent(store: EventStore, steps: list[RunStep]) -> None:
            store.replay_run([s._replace(attempt=s.attempt + 1) for s in steps])

        n = len(_run_de_reference())
        for k in range(1, n):
            with self.subTest(interruption=k):
                with self.assertRaises(AssertionError):
                    self._verifier_reprise(k, rejeu_non_idempotent)


#: L'alphabet Crockford (chiffres seuls suffisent : monotones, valides).
def _mk_ulid(rang: int) -> str:
    """Un ULID de 26 caractères dont l'ordre lexicographique suit `rang`. Deux
    appels de MÊME rang rendent le MÊME ULID — deux événements concurrents."""
    return str(rang).zfill(26)


def _ligne(ulid, event_type, payload, *, created_at, op, predecesseur=None, task=TACHE):
    """Une ligne d'export, clés = colonnes de `events_ledger`."""
    return {
        "ulid": ulid,
        "predecesseur_ulid": predecesseur,
        "task_id": task,
        "agent_role": "run",
        "event_type": event_type,
        "event_kind": event_type,
        "attempt": 0,
        "operation_id": op,
        "payload_json": json.dumps(payload, sort_keys=True),
        "created_at": created_at,
    }


def _etat_min(proj: dict) -> tuple:
    """L'état comparable — sans `last_updated`, horodatage volatil."""
    return (proj["status"], proj["retry_count"], proj["is_blocked"])


class ReconstructionExportsTests(unittest.TestCase):
    """Témoins 6, 7, 9 : `EventStore.reconstruire_depuis_exports` fusionne par
    ULID puis par `<auteur>/<copie>`, JAMAIS par l'horloge. Bras sous `tempfile`,
    aucun site nommant le `runs/` réel (la liaison `ROOT` du module reste)."""

    def _root(self) -> Path:
        base = Path(tempfile.mkdtemp(prefix="cadre_reconstruire_")).resolve()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        return base

    def _ecrire(self, root: Path, auteur: str, copie: str, lignes, mois="2026-06") -> None:
        chemin = root / "runs" / auteur / copie / f"{mois}.jsonl"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as fichier:
            for ligne in lignes:
                fichier.write(json.dumps(ligne, sort_keys=True, ensure_ascii=False) + "\n")

    def _reconstruire(self, root: Path) -> dict | None:
        db = root / "state" / "v3.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        store = EventStore(db, project_root=root)
        store.reconstruire_depuis_exports(root)
        return store.get_task_projection(TACHE)

    def _run_divergent(self):
        """Un run dont l'ordre ULID (correct) DIVERGE de l'ordre `created_at` : le
        `TEST_RUN` terminal (COMPLETED) porte l'ULID le PLUS GRAND mais un
        `created_at` PRÉCOCE ; le `CRITIC_VERDICT(False)` porte un ULID plus petit
        mais un `created_at` TARDIF. Trié par ULID → dernier = TEST_RUN →
        COMPLETED ; trié par created_at → dernier = verdict False → IN_DEV."""
        auteur_a = [
            _ligne(_mk_ulid(1), "TASK_CREATED", {"req_id": "R", "spec_version": 1},
                   created_at="2026-06-01 00:00:00", op="op1"),
            _ligne(_mk_ulid(3), "CRITIC_VERDICT", {"passed": False},
                   created_at="2026-06-01 09:00:00", op="op3", predecesseur=_mk_ulid(2)),
            _ligne(_mk_ulid(5), "TEST_RUN", {"passed": True},
                   created_at="2026-06-01 02:00:00", op="op5", predecesseur=_mk_ulid(4)),
        ]
        auteur_b = [
            _ligne(_mk_ulid(2), "CODE_GENERATED", {"code_diff": "d"},
                   created_at="2026-06-01 01:00:00", op="op2", predecesseur=_mk_ulid(1)),
            _ligne(_mk_ulid(4), "CRITIC_VERDICT", {"passed": True},
                   created_at="2026-06-01 03:00:00", op="op4", predecesseur=_mk_ulid(3)),
        ]
        return auteur_a, auteur_b

    def test_deux_auteurs_fusionnes_donnent_la_MEME_projection_quel_que_soit_l_ordre_des_exports(self):
        auteur_a, auteur_b = self._run_divergent()
        r1 = self._root()
        self._ecrire(r1, "aaaauteur", "cop1", auteur_a)
        self._ecrire(r1, "bbbauteur", "cop1", auteur_b)
        proj1 = self._reconstruire(r1)
        r2 = self._root()
        self._ecrire(r2, "bbbauteur", "cop1", auteur_b)
        self._ecrire(r2, "aaaauteur", "cop1", auteur_a)
        proj2 = self._reconstruire(r2)

        self.assertIsNotNone(proj1, "population VIDE — la projection reconstruite n'existe pas")
        self.assertEqual(_etat_min(proj1), _etat_min(proj2),
                         "la fusion dépend de l'ordre d'écriture des exports")
        # MUTATION : trier sur created_at au lieu de l'ULID -> IN_DEV.
        self.assertEqual(proj1["status"], "COMPLETED",
                         "fusion par created_at au lieu de l'ULID")

    def test_deux_evenements_concurrents_sont_departages_par_ULID_puis_par_auteur_copie(self):
        u0 = _mk_ulid(10)
        u = _mk_ulid(20)  # ULID COMMUN aux deux événements concurrents
        socle = _ligne(u0, "TASK_CREATED", {"req_id": "R", "spec_version": 1},
                       created_at="2026-06-01 00:00:00", op="op0")
        gagnant = _ligne(u, "TEST_RUN", {"passed": True},
                         created_at="2026-06-01 05:00:00", op="opA", predecesseur=u0)
        perdant = _ligne(u, "CRITIC_VERDICT", {"passed": False},
                         created_at="2026-06-01 05:00:00", op="opZ", predecesseur=u0)
        r = self._root()
        self._ecrire(r, "aaa", "c", [socle, gagnant])  # auteur départagé VAINQUEUR
        self._ecrire(r, "zzz", "c", [perdant])
        proj = self._reconstruire(r)
        self.assertIsNotNone(proj)
        # MUTATION : retirer le départage secondaire -> ordre de lecture -> IN_DEV.
        self.assertEqual(proj["status"], "COMPLETED",
                         "sans départage (ulid, auteur/copie) l'ordre devient celui du FS")

    def test_le_controle_negatif_multi_auteurs_ROUGIT(self):
        # Si le témoin 6 pouvait passer À BLANC, l'assertion « COMPLETED » ne
        # rougirait pas sur un run TRONQUÉ (sans TEST_RUN terminal). On EXIGE
        # qu'elle échoue — c'est ce qui prouve que le témoin 6 mord.
        lignes = [
            _ligne(_mk_ulid(1), "TASK_CREATED", {"req_id": "R", "spec_version": 1},
                   created_at="2026-06-01 00:00:00", op="op1"),
            _ligne(_mk_ulid(3), "CRITIC_VERDICT", {"passed": False},
                   created_at="2026-06-01 09:00:00", op="op3", predecesseur=_mk_ulid(2)),
        ]
        r = self._root()
        self._ecrire(r, "aaa", "c", lignes)
        proj = self._reconstruire(r)
        self.assertIsNotNone(proj, "même tronqué, le run pose une projection")
        with self.assertRaises(AssertionError):
            self.assertEqual(proj["status"], "COMPLETED")


class BackfillReconstructionTests(unittest.TestCase):
    """Témoin 10b (T-00000677) : `reconstruire_depuis_exports` sur les exports
    (trafic + backfill) rend le MÊME ensemble d'`operation_id` et le MÊME compte de
    lignes qu'une base FABRIQUÉE sous `tempfile` — sans garde `T650_JAMBE_DE_LOT`,
    rejoué à CHAQUE porte. C'est le pendant PERMANENT du témoin 10a (armé, base
    réelle) : aucune variable `ROOT` liée à `__file__`, fixture synthétique."""

    @staticmethod
    def _ops_et_compte(db: Path) -> tuple[set, int]:
        conn = sqlite3.connect(str(db))
        try:
            ops = {r[0] for r in conn.execute("SELECT operation_id FROM events_ledger")}
            compte = int(conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0])
            return ops, compte
        finally:
            conn.close()

    def _fabriquer_source(self, root: Path, dossier_db: Path) -> Path:
        """Une base : 3 lignes de trafic (exportées par `append_event`) + 4 lignes
        HISTORIQUES `ulid IS NULL` frappées et exportées par le backfill. Les
        exports sous `root/runs/` couvrent alors TOUTES les lignes de la base.

        `root` est la racine d'export EFFECTIVE (`$CADRE_PROJECT_ROOT`, résolue AVANT
        tout `depuis` — `paths.py`) ; les stores vivent HORS de `runs/`."""
        source = dossier_db / "source.db"
        source.parent.mkdir(parents=True, exist_ok=True)
        store = EventStore(source)  # project_root défaut -> $CADRE_PROJECT_ROOT == root
        for i in range(3):
            store.append_event(
                f"T-R{i}", "run", "TASK_CREATED", {"req_id": f"R{i}"},
                operation_id=f"reel-{i}",
            )
        conn = sqlite3.connect(str(source))
        for i in range(4):
            mois = "2026-08" if i < 2 else "2026-09"
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,"
                "payload_json,created_at,operation_id,event_kind,attempt) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"T-H{i}", "BoardBridge", "BOARD_TASK_OBSERVED", "{}",
                 f"{mois}-15 12:00:0{i}", f"hist-{i}", "BOARD_TASK_OBSERVED", 0),
            )
        conn.commit()
        conn.close()
        v3run.backfill_historique(base=source)  # depuis défaut -> root
        return source

    def test_reconstruire_depuis_exports_egale_une_base_fabriquee_permanent(self):
        root = v3run.project_root()  # racine d'export EFFECTIVE ($CADRE_PROJECT_ROOT)
        dossier_db = Path(tempfile.mkdtemp(prefix="cadre_backfill_recon_")).resolve()
        self.addCleanup(shutil.rmtree, dossier_db, ignore_errors=True)
        source = self._fabriquer_source(root, dossier_db)
        ops_src, compte_src = self._ops_et_compte(source)
        self.assertEqual(compte_src, 7, "3 trafic + 4 historiques backfillés")
        # Reconstruction dans une base FRAÎCHE depuis les mêmes exports.
        cible = dossier_db / "reconstruit.db"
        EventStore(cible).reconstruire_depuis_exports(root)
        ops_rec, compte_rec = self._ops_et_compte(cible)
        # MUTATION : fusionner sans lire un des runs/**/*.jsonl -> compte diverge.
        self.assertEqual(compte_rec, compte_src, "le compte de lignes diverge")
        self.assertEqual(ops_rec, ops_src, "l'ensemble d'operation_id diverge")

    @unittest.skipUnless(
        os.environ.get("T650_JAMBE_DE_LOT") == "1",
        "jambe de lot non armee : store du run hors depot",
    )
    def test_reconstruire_depuis_exports_egale_la_copie_reelle_apres_trafic(self):
        # Témoin 10a (T-00000677, ARMÉ, UNE fois) : la reconstruction depuis le
        # `runs/` RÉEL (trafic réel + backfill 1a) rend le MÊME ensemble
        # d'`operation_id` et le MÊME compte de lignes que la COPIE de 1a. Le chemin
        # de la copie est passé par `T650_COPIE` (l'étape 1a l'a produite et frappée).
        # MUTATION : fusionner sans lire un des `runs/**/*.jsonl` -> le compte diverge.
        copie = Path(os.environ["T650_COPIE"])
        # racine RÉELLE du dépôt (ROOT), et non `$CADRE_PROJECT_ROOT` de la fixture :
        # la preuve porteuse se prend sur le `runs/` RÉEL.
        ops_copie, compte_copie = self._ops_et_compte(copie)
        dossier = Path(tempfile.mkdtemp(prefix="cadre_10a_")).resolve()
        self.addCleanup(shutil.rmtree, dossier, ignore_errors=True)
        cible = dossier / "reconstruit.db"
        EventStore(cible, project_root=ROOT).reconstruire_depuis_exports(ROOT)
        ops_rec, compte_rec = self._ops_et_compte(cible)
        self.assertEqual(
            compte_rec, compte_copie,
            f"compte reconstruit {compte_rec} != copie {compte_copie}",
        )
        self.assertEqual(ops_rec, ops_copie, "operation_id set reconstruit != copie")


if __name__ == "__main__":
    unittest.main()
