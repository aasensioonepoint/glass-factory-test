"""L'AMONT D'ABORD — `deps-ready`, la jambe d'amont au `start` et à la fournée, `done_at`,
`lancee_sous` (T-01M4Z5VJ1DYQZM67AYHTACKFTA, décision pilote S-01M4Z5VMP5E9YN8T6EMDTBAF0T).

ZÉRO APPEL LLM. Board, SPECS et plans posés sous un `tempfile` (jamais le board du dépôt) ;
`tasks.py` chargé par chemin, appelé en processus, et en sous-processus pour le rc de la CLI
(`CADRE_STATE_DIR`/`AGENTS_EVENTS_DIR` jetables). INSTANTS FABRIQUÉS : `done_at` injecté au
board, S-id `S-<ULID>` construite à une milliseconde choisie, instants posés à MIDI LOCAL.

*** CHAQUE TÉMOIN NOMME SON MUTANT *** : joué sur une COPIE jetable de l'arbre, `.pyc` purgés,
le témoin doit y rougir. Aucun parcours d'arbre (`test_repo_walk_census.py`).

FUSEAU SANS `time.tzset` (absent sous Windows, où la CI tourne aussi) : le jour LOCAL se juge en
processus sur des instants à midi local (`midi_local`), quel que soit le fuseau de la machine ; le
témoin UTC−5 tourne en SOUS-PROCESSUS, `TZ` posé dans l'environnement du fils. BORNE : il est
SAUTÉ, nommément, si le runtime du fils n'honore pas `TZ` (sonde `tm_hour` de l'époque) — mesuré
honoré sous macOS ; sous Windows le CRT lit `TZ` au démarrage du processus, non mesuré ici.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
_SPEC = importlib.util.spec_from_file_location("tasks_amont_banc", TASKS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
tasks = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tasks
_SPEC.loader.exec_module(tasks)
SPECS_PATH = Path(__file__).with_name("specs.py")


def specs_module() -> Any:
    """`specs.py` chargé À LA DEMANDE sous un nom PROPRE au banc — jamais `sys.modules["specs"]` (2698f330)."""
    nom = "specs_amont_banc"
    if nom not in sys.modules:
        spec = importlib.util.spec_from_file_location(nom, SPECS_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[nom] = mod
        spec.loader.exec_module(mod)
    return sys.modules[nom]


CROCKFORD ="0123456789ABCDEFGHJKMNPQRSTVWXYZ"
HEURE = 3_600_000


def sid_ulid(ms: int, queue: str = "ABCDEFGHJKMNPQRS") -> str:
    """Une S-id `S-<ULID>` dont l'instant est EXACTEMENT `ms` (10 symboles Crockford)."""
    tete = ""
    for _ in range(10):
        tete = CROCKFORD[ms % 32] + tete
        ms //= 32
    return f"S-{tete}{queue}"


def iso_ms(ms: int) -> str:
    """La forme `done_at` de l'instant `ms` (UTC, à la milliseconde)."""
    instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)
    return instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def maintenant_ms() -> int:
    return tasks._ms_utc(datetime.now(timezone.utc))


def midi_local(jour: str) -> str:
    """La forme `done_at` (UTC) de MIDI LOCAL du `jour` : son jour local est `jour` dans tout fuseau
    du processus, sans rien piloter (`astimezone` sur un instant naïf = l'heure locale)."""
    instant = datetime.fromisoformat(f"{jour}T12:00:00").astimezone(timezone.utc)
    return instant.strftime("%Y-%m-%dT%H:%M:%S.000Z")


PLAN_FOURNEE = ("# PLAN — {p}\n\n## Steps\n1. faire — angle mort: banc ?\n\n## Lots\n"
                "LOT: A | dev-multi | moteur | .agents/bin/tasks_x.py, src/a.py\n"
                "LOT: B | dev-mono | doc | docs/b.md, docs/c.md\nINTÉGRATION: CHANGELOG.md\n")


class _Banc(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.d = Path(self._tmp.name)
        for sous in ("board", "gates", "specs", "local/plan"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        (self.d / "plans").mkdir()
        self.root = str(self.d)
        self.entrees: list[dict[str, Any]] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- outillage ------------------------------------------------------------
    def new(self, titre: str = "tache de banc") -> str:
        sortie = tasks.new_task(self.root, titre, "dev-mono")
        trouve = re.fullmatch(r"TASKS: (\S+) → pending", sortie)
        assert trouve, sortie
        return trouve.group(1)

    def dep(self, aval: str, *amonts: str, motif: str = "technique : amont livre") -> None:
        tasks.set_depends(self.root, aval, list(amonts), motif=motif)

    def start(self, tid: str, **kw: Any) -> str:
        return tasks.set_state(self.root, tid, "running", **kw)

    def done(self, tid: str, **kw: Any) -> str:
        return tasks.set_state(self.root, tid, "done", stage="clos par le banc", **kw)

    def sortir(self, tid: str) -> None:
        """La SORTIE EXPLICITE de `running` (T-01M5F7286N1EYGXAXA5244X86B) : le `start` d'une autre
        ne rétrograde plus `tid` — asserté, donc l'ancien contrat rétabli rougit —, puis `tid` passe
        à `pending` par `set_state`, seule porte qui inscrit `lancee_sous`."""
        self.start(self.new("autre"))
        self.assertEqual(self.tache(tid)["state"], "running", "le start d'une autre a rétrogradé la tâche")
        tasks.set_state(self.root, tid, "pending")

    def refus(self, fn: Any, *args: Any, **kw: Any) -> str:
        with self.assertRaises(tasks.BoardError) as pris:
            fn(*args, **kw)
        return str(pris.exception)

    def tache(self, tid: str) -> dict[str, Any]:
        return tasks.find(tasks.load(self.root), tid)

    def poser(self, tid: str, **champs: Any) -> None:
        """Écrit des champs au board (`None` = retiré) : l'instant FABRIQUÉ d'une clôture."""
        with tasks.board_lock(self.root):
            data = tasks.load(self.root)
            t = tasks.find(data, tid)
            for cle, valeur in champs.items():
                if valeur is None:
                    t.pop(cle, None)
                else:
                    t[cle] = valeur
            tasks.save(self.root, data)

    def tracer(self, tid: str, sid: str, jour: str = "2026-10-01", rel: str = "plans/p.md",
               titre: str = "plan approuvé") -> str:
        """Une trace `plan approuvé` (plan sûr, empreinte exacte) au journal `SPECS.json`."""
        plan = self.d / rel
        if not plan.exists():
            plan.write_text(f"# PLAN — {tid}\nARÊTES: aucune\n", encoding="utf-8")
        sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        self.entrees.append({"id": sid, "task": tid, "kind": "decision", "title": titre,
                             "text": f"plan={rel} sha256={sha}", "date": jour})
        self.ecrire_specs()
        return sid

    def ecrire_specs(self) -> None:
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 99999, "entries": self.entrees}, ensure_ascii=False), encoding="utf-8")

    def ready(self, tid: str) -> tuple[int, list[str]]:
        rc, texte = tasks.render_deps_ready(self.root, tid)
        return rc, texte.splitlines()

    def env_fils(self, tz: str | None = None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "TZ")}
        env.update(CADRE_STATE_DIR=self._tmp.name, CADRE_PROJECT_ROOT=self._tmp.name,
                   AGENTS_EVENTS_DIR=self._tmp.name, PYTHONDONTWRITEBYTECODE="1")
        if tz is not None:
            env["TZ"] = tz
        return env

    def cli(self, *args: str, tz: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(TASKS_PATH), "--root", self.root, *args],
                              capture_output=True, text=True, timeout=120, env=self.env_fils(tz))

    def sonder_tz(self, tz: str, heure_epoque: int) -> None:
        """Le fils honore-t-il `TZ` ? `tm_hour` de l'époque sous `tz` ; sinon le témoin est SAUTÉ, nommé."""
        r = subprocess.run([sys.executable, "-c", "import time; print(time.localtime(0).tm_hour)"],
                           capture_output=True, text=True, timeout=60, env=self.env_fils(tz))
        if r.stdout.strip() != str(heure_epoque):
            self.skipTest(f"TZ={tz} non honoré par ce runtime (tm_hour de l'époque = {r.stdout.strip()!r}, "
                          f"attendu {heure_epoque}) : témoin à fuseau sauté")

    def parent_fournee(self, *amonts: str) -> tuple[str, str]:
        """Un parent de fournée (plan à deux lots écrit, PAS encore tracé) derrière `amonts`."""
        p = self.new("parent")
        if amonts:
            self.dep(p, *amonts)
        rel = "docs/tasks/plan.md"
        (self.d / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.d / rel).write_text(PLAN_FOURNEE.format(p=p), encoding="utf-8")
        return p, rel

    def fournee_refusee(self, p: str, **kw: Any) -> str:
        """La fournée de `p` refusée au PRÉVOL : jamais à une étape, et AUCUNE tâche créée."""
        avant = len(tasks.load(self.root)["tasks"])
        msg = self.refus(tasks.fournee, self.root, p, **kw)
        self.assertNotIn("échec à l'étape", msg)
        self.assertEqual(len(tasks.load(self.root)["tasks"]), avant, msg)
        return msg

    def lance_sous_trace(self) -> tuple[str, str, str, int]:
        """L'amont A clos 2 h AVANT la trace S1 de T (T <- A), T démarré sous S1 : `(A, T, S1, ms de S1)`."""
        t1 = maintenant_ms() - HEURE
        a, t = self.new("amont"), self.new("aval")
        self.dep(t, a)
        self.done(a)
        self.poser(a, done_at=iso_ms(t1 - 2 * HEURE))
        s1 = self.tracer(t, sid_ulid(t1))
        self.assertIn("→ running", self.start(t))
        self.assertEqual(self.tache(t).get("lancee_sous"), s1)
        return a, t, s1, t1


# ===========================================================================
# W1-W3 — `deps-ready` : fermeture, ordre, `done` qui arrête, PENDOUILLANTE, CYCLE.
# ===========================================================================
class DepsReadyTests(_Banc):
    def test_w1_fermeture_transitive_amont_d_abord(self) -> None:
        """W1. C <- B <- A, tous ouverts : A puis B, rc 1. MUTANTS : parents directs seuls
        (A absent) ; ordre inversé (B avant A) ⇒ rouge."""
        a, b, c = self.new("A"), self.new("B"), self.new("C")
        self.dep(b, a, motif="B consomme A")
        self.dep(c, b, motif="C consomme B")
        rc, lignes = self.ready(c)
        self.assertEqual(rc, 1)
        self.assertEqual(lignes[0], "deps-ready: AMONT_OUVERT")
        self.assertTrue(lignes[1].startswith(f"1. {a} — pending — tirée par {b} <- {a} (motif : B consomme A)"), lignes)
        self.assertTrue(lignes[2].startswith(f"2. {b} — pending — tirée par {c} <- {b}"), lignes)
        self.assertEqual(len(lignes), 3, lignes)

    def test_w2_done_arrete_pendouillante_et_blocked_nommes(self) -> None:
        """W2. Un `done` arrête la liste ouverte ; un id absent est PENDOUILLANT, satisfait ;
        `blocked` se lit « attend une décision »."""
        a, b, c = self.new("A"), self.new("B"), self.new("C")
        self.dep(b, a)
        self.dep(c, b)
        self.done(b)
        rc, lignes = self.ready(c)
        self.assertEqual((rc, lignes[0]), (0, "deps-ready: AMONT_CLOS"), lignes)
        d, e = self.new("D"), self.new("E")
        tasks.block_task(self.root, a, note="attente pilote")
        self.dep(d, a)
        self.poser(d, depends_on=[a, "T-00009999"])
        self.poser(e, depends_on=["T-00009999"])
        rc, lignes = self.ready(d)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: AMONT_OUVERT"))
        self.assertIn("blocked (attend une décision)", lignes[1])
        self.assertTrue(any(ligne.startswith("PENDOUILLANTE T-00009999") for ligne in lignes), lignes)
        self.assertEqual(self.ready(e)[0], 0)
        self.assertIn("→ running", self.start(e))

    def test_w3_cycle_chemin_et_remede(self) -> None:
        """W3. A <-> B (écrit à la main), C <- A : CYCLE, chemin complet, `--retirer` ; arêtes
        ORDRE PILOTE ⇒ route SUGGESTION ; le `start` de C est refusé CYCLE."""
        a, b, c = self.new("A"), self.new("B"), self.new("C")
        self.poser(a, depends_on=[b])
        self.poser(b, depends_on=[a])
        self.dep(c, a)
        rc, lignes = self.ready(c)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: CYCLE"))
        self.assertIn(f"{a} → {b} → {a}", lignes[1])
        self.assertIn("--retirer", lignes[1])
        self.assertIn("deps-ready: CYCLE", self.refus(self.start, c))
        op = "ORDRE PILOTE S-00001558 : amont avant aval"
        self.poser(a, depends_motif={b: op})
        self.poser(b, depends_motif={a: op})
        self.assertIn("SUGGESTION", self.ready(c)[1][1])

    def test_w3b_cycle_a_travers_des_taches_closes(self) -> None:
        """W3b. Z <- X, X <-> Y écrit à la main, X et Y CLOS : le cycle passe par des `done` et reste
        un CYCLE pour Z, qui n'en est pas membre (fail-closed, dérogeable — le verbe `depends` le
        refuse aussi à travers les `done`). MUTANT : la recherche de cycle s'arrête aux `done` ⇒
        AMONT_CLOS, le `start` passe, rouge."""
        x, y, z = self.new("X"), self.new("Y"), self.new("Z")
        self.done(x)
        self.done(y)
        self.poser(x, depends_on=[y])
        self.poser(y, depends_on=[x])
        self.dep(z, x)
        rc, lignes = self.ready(z)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: CYCLE"), lignes)
        self.assertIn(f"{x} → {y} → {x}", lignes[1])
        self.assertIn("deps-ready: CYCLE", self.refus(self.start, z))
        self.assertIn("→ running", self.start(z, sans_dependances="cycle de tâches closes, vu"))


# ===========================================================================
# W4-W6, W9, W13, W15 — la jambe d'amont au `start`, à la fournée, au `done`.
# ===========================================================================
class JambeStartTests(_Banc):
    def test_w4_start_refuse_sans_marqueur_board_et_chaine_intacts(self) -> None:
        """W4. Racine DÉSARMÉE, amont ouvert : `start` refusé, board et traces de chaîne
        intacts. MUTANT : jugement placé sous la condition `_pd` ⇒ le start passe, rouge."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        (self.d / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").touch()
        quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for nom, role in (("planner", "planner"), ("plan-critic", "reviewer")):
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": quand, "sha": "abc", "role": role}), encoding="utf-8")
        store = self.d / ".agents" / "state" / "board" / "TASKS.json"
        avant = store.read_bytes()
        msg = self.refus(self.start, b)
        self.assertIn("deps-ready: AMONT_OUVERT", msg)
        self.assertIn("--sans-dependances", msg)
        self.assertEqual(store.read_bytes(), avant)
        traces = sorted(p.name for p in (self.d / ".agents" / "state" / "local" / "plan").glob("*.json"))
        self.assertEqual(traces, ["plan-critic.json", "planner.json"])

    def test_w5_fournee_refusee_zero_lot(self) -> None:
        """W5. Parent derrière un amont ouvert : la fournée est refusée au PRÉVOL, aucun lot
        créé. MUTANT : fournée non jugée ⇒ lots créés puis échec à l'étape (5), rouge."""
        a = self.new("A")
        p, rel = self.parent_fournee(a)
        self.tracer(p, "S-00000001", rel=rel)
        self.assertIn("deps-ready: AMONT_OUVERT", self.fournee_refusee(p))

    def test_w5b_fournee_refusee_sur_cycle_au_prevol(self) -> None:
        """W5b. Parent derrière X, X <-> Y : la fournée est refusée CYCLE au PRÉVOL, aucun lot.
        MUTANT MV : le prévol laisse passer CYCLE ⇒ lots créés puis échec à l'étape (5), rouge."""
        x, y = self.new("X"), self.new("Y")
        self.poser(x, depends_on=[y])
        self.poser(y, depends_on=[x])
        p, rel = self.parent_fournee(x)
        self.tracer(p, "S-00000001", rel=rel)
        self.assertIn("deps-ready: CYCLE", self.fournee_refusee(p))

    def test_w5c_fournee_refusee_plan_a_replanifier_au_prevol(self) -> None:
        """W5c. Amont clos APRÈS la trace du parent : la fournée est refusée PLAN_A_REPLANIFIER au
        PRÉVOL, aucun lot. MUTANT : prévol qui laisse passer PLAN_A_REPLANIFIER ⇒ rouge."""
        t = maintenant_ms() - HEURE
        a = self.new("A")
        self.done(a)
        self.poser(a, done_at=iso_ms(t + 1))
        p, rel = self.parent_fournee(a)
        self.tracer(p, sid_ulid(t), rel=rel)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.fournee_refusee(p))

    def test_w5d_fournee_precedences_au_prevol(self) -> None:
        """W5d. Au PRÉVOL, sur le MÊME parent : un amont ouvert ET une trace sans date lisible ⇒
        AMONT_OUVERT (AMONT_OUVERT > INEXPLOITABLE) ; l'amont clos, la date toujours illisible et un
        amont clos après tout jour lisible ⇒ INEXPLOITABLE (INEXPLOITABLE > PLAN_A_REPLANIFIER) ; la
        date réparée ⇒ PLAN_A_REPLANIFIER. Aucun lot à aucun pas. MUTANT : trace sans date jugée
        « rien à dire » ⇒ la fournée passe au 2e pas, rouge."""
        a, b = self.new("A"), self.new("B ouvert")
        self.done(a)
        self.poser(a, done_at=midi_local("2026-10-05"))
        p, rel = self.parent_fournee(a, b)
        self.tracer(p, "S-00000001", jour="illisible", rel=rel)
        msg = self.fournee_refusee(p)
        self.assertIn("deps-ready: AMONT_OUVERT", msg)
        self.assertNotIn("INEXPLOITABLE", msg)
        self.done(b)
        msg = self.fournee_refusee(p)
        self.assertIn("deps-ready: INEXPLOITABLE", msg)
        self.assertIn("trace S-00000001 sans date lisible", msg)
        self.assertNotIn("PLAN_A_REPLANIFIER", msg)
        self.entrees[-1]["date"] = "2026-10-01"
        self.ecrire_specs()
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.fournee_refusee(p))

    def test_w25_sans_dependances_raison_vide_refusee(self) -> None:
        """W25 (avis de sécurité). `--sans-dependances` dont la raison est vide une fois `strip()` :
        refusé à `start`, à `done` et à la fournée (avant tout lot), rien d'écrit. MUTANTS : le
        contrôle retiré de `set_state`, ou de `fournee` ⇒ rouge."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        store = self.d / ".agents" / "state" / "board" / "TASKS.json"
        avant = store.read_bytes()
        self.assertIn("raison NON VIDE", self.refus(self.start, b, sans_dependances="   "))
        self.assertIn("raison NON VIDE", self.refus(self.done, b, sans_dependances=" \t"))
        self.assertEqual(store.read_bytes(), avant)
        p, rel = self.parent_fournee(a)
        self.tracer(p, "S-00000001", rel=rel)
        self.assertIn("raison NON VIDE", self.fournee_refusee(p, sans_dependances="  "))

    def test_w6_sans_dependances_racine_desarmee_passe_et_marque(self) -> None:
        """W6. `--sans-dependances` sur racine DÉSARMÉE : passe, DIT ce qu'il saute, marque
        `arête + amont` ; sans aucune dépendance, marqué aussi. MUTANT : marque gardée par le
        marqueur ⇒ stage vide, rouge."""
        a, b, c = self.new("A"), self.new("B"), self.new("C")
        self.dep(b, a)
        sortie = self.start(b, sans_dependances="pilote : amont livré hors board")
        self.assertIn("démarre SANS la jambe d'amont (--sans-dependances) : deps-ready: AMONT_OUVERT", sortie)
        self.assertIn("[SANS DÉPENDANCES : arête + amont — pilote : amont livré hors board]",
                      self.tache(b)["stage"])
        self.start(c, sans_dependances="sans arête")
        self.assertIn("[SANS DÉPENDANCES : arête + amont — sans arête]", self.tache(c)["stage"])

    def test_w9_done_amont_ouvert_passe_et_dit(self) -> None:
        """W9. `done` reste un DIRE : la clôture d'une tâche dont l'amont est ouvert passe."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        sortie = self.done(b)
        self.assertIn("dépendance(s) non satisfaite(s)", sortie)
        self.assertIn("seul un `start` refuse un amont ouvert", sortie)
        self.assertEqual(self.tache(b)["state"], "done")

    def test_w13_pending_block_start_amont_ouvert_refuse(self) -> None:
        """W13. pending → block → start, amont ouvert : refusé (la source `blocked` est jugée)."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        tasks.block_task(self.root, b, note="attente")
        self.assertIn("deps-ready: AMONT_OUVERT", self.refus(self.start, b))

    def test_w15_done_start_amont_ouvert_refuse(self) -> None:
        """W15. done → start, amont ouvert : refusé. MUTANT : source `done` non jugée ⇒ passe, rouge."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(b)
        self.assertIn("deps-ready: AMONT_OUVERT", self.refus(self.start, b))


# ===========================================================================
# W7, W8, W10, W20 — la trace élue contre la clôture des amonts ; W26, W26b — la racine tue.
# ===========================================================================
class ReplanificationTests(_Banc):
    def test_w7a_ulid_milliseconde_egalite_perimee(self) -> None:
        """W7 (a). S-<ULID> : amont clos à la MÊME ms que la trace ⇒ PLAN_A_REPLANIFIER ;
        une ms avant ⇒ passe. MUTANT : `>` au lieu de `>=` ⇒ l'égalité passe, rouge."""
        t = maintenant_ms() - HEURE
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.poser(a, done_at=iso_ms(t))
        sid = self.tracer(b, sid_ulid(t))
        msg = self.refus(self.start, b)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", msg)
        self.assertIn(f"à ou après la trace {sid}", msg)
        self.poser(a, done_at=iso_ms(t - 1))
        self.assertIn("→ running", self.start(b))

    def test_w7b_s_numerique_a_la_journee(self) -> None:
        """W7 (b). S- numérique : jour LOCAL de `done_at` > jour de la trace ⇒ refus ; même jour ⇒
        avis dit, passe. Instants à MIDI LOCAL : aucun fuseau piloté, le témoin tourne partout."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.tracer(b, "S-00002000", jour="2026-10-01")
        self.poser(a, done_at=midi_local("2026-10-02"))
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.refus(self.start, b))
        self.poser(a, done_at=midi_local("2026-10-01"))
        sortie = self.start(b)
        self.assertIn("→ running", sortie)
        self.assertIn("avis d'amont", sortie)
        self.assertIn("NON PROUVÉ", sortie)

    def test_w7b_fuseau_utc_moins_5_jour_local(self) -> None:
        """W7 (b), UTC−5, en SOUS-PROCESSUS (`TZ` dans l'environnement du fils, sans `time.tzset`) :
        `2026-10-02T03:00Z` est le 1er au soir à `TZ=EST5`, le jour de la trace ⇒ AMONT_CLOS rc 0 et
        le `start` passe ; à `TZ=UTC0` c'est le 2 ⇒ PLAN_A_REPLANIFIER rc 1. Sauté, nommé, si le fils
        n'honore pas `TZ`. MUTANT : jour UTC au lieu du jour local ⇒ rc 1 sous EST5, rouge."""
        self.sonder_tz("EST5", 19)
        self.sonder_tz("UTC0", 0)
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.tracer(b, "S-00002000", jour="2026-10-01")
        self.poser(a, done_at="2026-10-02T03:00:00.000Z")
        r = self.cli("deps-ready", b, tz="EST5")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "deps-ready: AMONT_CLOS"), r.stdout + r.stderr)
        r = self.cli("deps-ready", b, tz="UTC0")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (1, "deps-ready: PLAN_A_REPLANIFIER"), r.stderr)
        r = self.cli("start", b, tz="EST5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("→ running", r.stdout)

    def test_w7c_sans_done_at_jour_de_updated(self) -> None:
        """W7 (c). Amont clos sans `done_at` (avant ce code) : `updated` > jour de la trace ⇒
        refus ; même jour ⇒ avis NON PROUVÉ, passe. MUTANT : `>=` ⇒ le même jour refuse, rouge."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.tracer(b, "S-00002000", jour="2026-10-01")
        self.poser(a, done_at=None, updated="2026-10-02")
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.refus(self.start, b))
        self.poser(a, updated="2026-10-01")
        sortie = self.start(b)
        self.assertIn("→ running", sortie)
        self.assertIn("clos sans done_at, touché le jour de la trace", sortie)

    def test_w7_grand_parent_clos_apres_la_trace(self) -> None:
        """W7, fermeture COMPLÈTE : C <- B <- A, B clos avant la trace, A (grand-parent) après ⇒
        refus qui nomme A. MUTANT : parents directs seuls ⇒ passe, rouge."""
        t = maintenant_ms() - HEURE
        a, b, c = self.new("A"), self.new("B"), self.new("C")
        self.dep(b, a)
        self.dep(c, b)
        self.done(a)
        self.done(b)
        self.poser(b, done_at=iso_ms(t - HEURE))
        self.poser(a, done_at=iso_ms(t + 1))
        self.tracer(c, sid_ulid(t))
        msg = self.refus(self.start, c)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", msg)
        self.assertIn(f"{a} clos le", msg)

    def test_w7_sans_trace_rien_a_dire(self) -> None:
        """W7. Amont clos, AUCUNE trace : AMONT_CLOS, rc 0."""
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.assertEqual(self.ready(b), (0, ["deps-ready: AMONT_CLOS", "aucun amont ouvert (1 amont(s) clos)"]))

    def test_w8_plan_cible_absent_ou_specs_illisible(self) -> None:
        """W8. `plan_cible` absent : sans dépendance, le `start` passe (rien n'est lu) ; avec un
        amont clos, INEXPLOITABLE (fail-closed), dérogeable ; SPECS illisible : INEXPLOITABLE, qui
        nomme le TYPE de l'exception. MUTANT : son message (chemin absolu du journal) affiché ⇒ rouge."""
        a, b, c, e = self.new("A"), self.new("B"), self.new("C"), self.new("E")
        self.dep(b, a)
        self.done(a)
        with mock.patch.object(tasks, "plan_cible_module", return_value=None):
            self.assertIn("→ running", self.start(c))
            self.assertIn("deps-ready: INEXPLOITABLE", self.refus(self.start, b))
            self.assertIn("→ running", self.start(b, sans_dependances="plan_cible absent, vu"))
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text("{corrompu", encoding="utf-8")
        self.dep(e, a)
        rc, lignes = self.ready(e)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: INEXPLOITABLE"))
        self.assertIn("SPECS illisible (CibleError)", lignes[1])
        # Avis de sécurité : le TYPE de l'exception, jamais son message (chemin absolu du journal).
        self.assertNotIn(self.d.name, "\n".join(lignes))

    def armer_cible(self) -> None:
        """`PLAN_CIBLE_REQUIRED` armé pour TOUTE tâche (`chantier=*`, la graine de l'adoptant)."""
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            "spec=docs/spec.md\nchantier=*\n", encoding="utf-8")

    def sans_racine(self, msg: str) -> None:
        """Le journal est nommé (remède gardé), la racine jamais — ni telle quelle, ni résolue."""
        self.assertIn("SPECS.jsonl", msg)
        for racine in {str(self.d), str(self.d.resolve())}:
            self.assertNotIn(racine, msg)

    def test_w26_cible_armee_specs_corrompu_start_tait_la_racine(self) -> None:
        """W26 (avis de sécurité S-01M5072DQ863DE4RKPMKE9K4G1). Cible armée, `SPECS.jsonl` corrompu :
        le `start` refuse en nommant le journal par son chemin RELATIF, jamais la racine.
        MUTANT : `str(exc)` brut à la jambe cible de `set_state` ⇒ racine affichée, rouge."""
        t = self.new("T")
        self.armer_cible()
        (self.d / ".agents" / "state" / "specs" / "SPECS.jsonl").write_text("{corrompu\n", encoding="utf-8")
        self.sans_racine(self.refus(self.start, t))

    def test_w26b_cible_armee_specs_corrompu_fournee_tait_la_racine(self) -> None:
        """W26b (même avis). La fournée lit la trace AVANT ses jambes : un journal corrompu d'emblée
        n'atteint pas la jambe cible. Il l'est donc quand `refus_au_start` le RELIT — message réel de
        `plan_cible`. La jambe d'arêtes (`plan_depends._cause`) est sautée par `--sans-dependances` :
        elle a son témoin, W26d. MUTANT : `str(exc)` brut au prévol ⇒ racine, rouge."""
        p, rel = self.parent_fournee()
        self.tracer(p, sid_ulid(maintenant_ms() - HEURE), rel=rel)
        self.armer_cible()
        pc, specs_dir = tasks.plan_cible_module(), self.d / ".agents" / "state" / "specs"
        vrai = pc.refus_au_start

        def relu_corrompu(root: str, tid: str, data: dict[str, Any]) -> str | None:
            (specs_dir / "SPECS.json").unlink()
            (specs_dir / "SPECS.jsonl").write_text("{corrompu\n", encoding="utf-8")
            return vrai(root, tid, data)

        with mock.patch.object(pc, "refus_au_start", side_effect=relu_corrompu):
            msg = self.fournee_refusee(p, sans_dependances="témoin de la jambe cible seule")
        self.sans_racine(msg)

    def test_w26c_cible_armee_specs_corrompu_done_tait_la_racine(self) -> None:
        """W26c (même avis, reste 6a de l'exec-critic). La jambe cible du `done` : `SPECS.jsonl` corrompu
        après le `start`, le `done` refuse en nommant le journal RELATIF. MUTANT : `str(exc)` brut à la
        jambe cible du `done` de `set_state` ⇒ racine affichée, rouge."""
        t = self.new("T")
        self.start(t)
        self.armer_cible()
        (self.d / ".agents" / "state" / "specs" / "SPECS.jsonl").write_text("{corrompu\n", encoding="utf-8")
        self.sans_racine(self.refus(self.done, t))

    def test_w26d_plan_depends_cause_tait_la_racine_au_start_au_done_et_au_stage(self) -> None:
        """W26d (même avis, reste 6a). Sous `--sans-cible`, la jambe cible saute et c'est la jambe d'arêtes
        (`plan_depends._cause`) qui lit le journal corrompu : refus au `start` ; au `done`, MODE DIRE — la
        ligne ET la marque écrite au `stage` du board, sans racine. MUTANT : `_cause` sans retrait de la
        racine ⇒ racine au refus, à la ligne et au board, rouge."""
        t, u = self.new("T"), self.new("U")
        self.start(u)
        self.armer_cible()
        (self.d / ".agents" / "state" / "specs" / "SPECS.jsonl").write_text("{corrompu\n", encoding="utf-8")
        self.sans_racine(self.refus(self.start, t, sans_cible="banc : jambe d'arêtes seule"))
        sortie = self.done(u, sans_cible="banc : jambe d'arêtes seule")
        self.assertIn("contrôle impossible", sortie)
        self.sans_racine(sortie)
        stage = self.tache(u)["stage"]
        self.assertIn("[SANS DÉPENDANCES : contrôle impossible sous --sans-cible", stage)
        self.sans_racine(stage)

    def test_w26e_fournee_specs_corrompu_refus_propre_rc2(self) -> None:
        """W26e (reste 6b). `SPECS.json` corrompu : la fournée lit la trace AVANT ses jambes, et
        `CibleError` n'hérite pas de `BoardError`. En sous-processus, lancement et `--dry-run` : rc 2,
        aucune trace de pile, le journal nommé, la racine jamais, 0 lot. MUTANT : `trace_plan_approuve`
        hors du `try` du prévol ⇒ traceback rc 1, rouge."""
        p, _rel = self.parent_fournee()
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text("{corrompu", encoding="utf-8")
        avant = len(tasks.load(self.root)["tasks"])
        for args in (("fournee", p), ("fournee", p, "--dry-run")):
            r = self.cli(*args)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn(f"refus de la fournée de {p}", r.stderr)
            self.assertIn("SPECS.json corrompu", r.stderr)
            for racine in {str(self.d), str(self.d.resolve())}:
                self.assertNotIn(racine, r.stdout + r.stderr)
        self.assertEqual(len(tasks.load(self.root)["tasks"]), avant)

    def test_w26f_specs_add_board_corrompu_tait_la_racine(self) -> None:
        """W26f (revue de clôture 2, F3 ; même avis). `specs.py add`, cible armée, `TASKS.json` corrompu : la
        trace `plan approuvé` (jambe d'arêtes) ET le verdict `plan-critic` (jambe cible) refusent en nommant
        le board, jamais la racine. MUTANTS : `_pd._cause(exc)` sans `root` ; `str(exc)` brut à la jambe
        cible ⇒ racine affichée, rouge (un mutant par jambe)."""
        specs = specs_module()
        t = self.new("T")
        self.armer_cible()
        (self.d / "plans" / "p.md").write_text(f"# PLAN — {t}\nARÊTES: aucune\n", encoding="utf-8")
        (self.d / ".agents" / "state" / "board" / "TASKS.json").write_text("{corrompu", encoding="utf-8")
        for kind, titre in (("decision", "plan approuvé"), ("verdict", "plan-critic GO")):
            with self.subTest(kind=kind):
                with self.assertRaises(specs.SpecsError) as pris:
                    specs.add_entry(self.root, t, kind, titre, "plan=plans/p.md sha256=" + "0" * 64)
                msg = str(pris.exception)
                self.assertIn("TASKS.json", msg)
                for racine in {str(self.d), str(self.d.resolve())}:
                    self.assertNotIn(racine, msg)

    def test_w10_night_eligible_seule_ignoree(self) -> None:
        """W10. Une `night-eligible: approved` n'est jamais élue : rien à dire, rc 0, aucun avis."""
        t = maintenant_ms() - HEURE
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        self.tracer(b, sid_ulid(t), titre="night-eligible: approved")
        self.assertEqual(self.ready(b), (0, ["deps-ready: AMONT_CLOS", "aucun amont ouvert (1 amont(s) clos)"]))

    def test_w20_trace_non_elue_est_dite(self) -> None:
        """W20 (N1, réserve C6). Plan retouché après approbation : la trace n'est plus élue, la
        replanification n'est pas jugée — et c'est DIT, à `deps-ready` comme au `start`.
        MUTANT : avis N1 retiré ⇒ silence, rouge."""
        t = maintenant_ms() - HEURE
        a, b = self.new("A"), self.new("B")
        self.dep(b, a)
        self.done(a)
        sid = self.tracer(b, sid_ulid(t))
        (self.d / "plans" / "p.md").write_text("# PLAN retouché\n", encoding="utf-8")
        rc, lignes = self.ready(b)
        self.assertEqual((rc, lignes[0]), (0, "deps-ready: AMONT_CLOS"))
        self.assertIn(f"avis : trace {sid} non élue", lignes[1])
        self.assertIn(f"trace {sid} non élue", self.start(b))


# ===========================================================================
# W11, W11b, W11c, W12, W14, W16-W19, W21-W24, W27-W29 — `lancee_sous`, `lancee_le` et `done_at`.
# ===========================================================================
class CycleTests(_Banc):
    def test_w11_retrogradee_puis_start_reprise_dite(self) -> None:
        """W11. T lancée sous S1, sortie EXPLICITEMENT de `running` (le `start` d'une autre ne la
        rétrograde plus), amont re-clos après S1 : le `start` passe en REPRISE_DITE, et le DIT.
        MUTANTS : `lancee_sous` jamais écrit ⇒ PLAN_A_REPLANIFIER, rouge ; rétrogradation rétablie, rouge."""
        a, t, s1, t1 = self.lance_sous_trace()
        self.poser(a, done_at=iso_ms(t1 + 1000))
        self.sortir(t)
        self.assertEqual((self.tache(t)["state"], self.tache(t).get("lancee_sous")), ("pending", s1))
        sortie = self.start(t)
        self.assertIn("→ running", sortie)
        self.assertIn(f"REPRISE_DITE — lancée sous {s1} : reprise DITE", sortie)

    def test_w11b_amont_re_clos_apres_le_lancement_replanifier(self) -> None:
        """W11b (revue de clôture C6, décision du 2026-10-15). T lancée sous S1 ; A rouvert pendant
        qu'elle tourne, T sortie de `running` (`sortir`), A re-clos 1 s APRÈS `lancee_le` : la reprise ne
        couvre que ce qui précède le lancement, le `start` est refusé PLAN_A_REPLANIFIER. MUTANT : `lancee_le`
        jamais écrit (ou ignoré au jugement) ⇒ REPRISE_DITE, passe, rouge."""
        a, t, s1, _t1 = self.lance_sous_trace()
        lance = self.tache(t).get("lancee_le")
        self.assertTrue(lance, "le start sous S1 n'a pas posé lancee_le")
        tasks.reopen_task(self.root, a, "amont à refaire")
        self.sortir(t)
        self.done(a)
        self.poser(a, done_at=iso_ms(tasks._ms_utc(tasks._instant_done_at(lance)) + 1000))
        self.assertEqual((self.tache(t)["state"], self.tache(t).get("lancee_sous")), ("pending", s1))
        msg = self.refus(self.start, t)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", msg)
        self.assertNotIn("REPRISE_DITE", msg)
        self.assertEqual(self.ready(t)[0], 1)

    def test_w11c_borne_au_plus_tard_egalite_a_la_ms_reprise(self) -> None:
        """W11c (exec-critic, réserve 2). « Clos AU PLUS TARD à ce lancement » : amont re-clos à la MÊME
        milliseconde que `lancee_le` ⇒ REPRISE_DITE rc 0 ; 1 ms APRÈS ⇒ PLAN_A_REPLANIFIER rc 1.
        MUTANT M4 : `f < lance` au lieu de `f <= lance` ⇒ l'égalité replanifie, rouge."""
        a, t, s1, _t1 = self.lance_sous_trace()
        lance_ms = tasks._ms_utc(tasks._instant_done_at(self.tache(t)["lancee_le"]))
        tasks.reopen_task(self.root, a, "amont à refaire")
        self.sortir(t)
        self.done(a)
        self.poser(a, done_at=iso_ms(lance_ms))
        rc, lignes = self.ready(t)
        self.assertEqual((rc, lignes[:2]), (0, ["deps-ready: REPRISE_DITE",
                                                f"lancée sous {s1} : reprise DITE, jamais une révision"]))
        self.poser(a, done_at=iso_ms(lance_ms + 1))
        self.assertEqual((self.ready(t)[0], self.ready(t)[1][0]), (1, "deps-ready: PLAN_A_REPLANIFIER"))

    def test_w12_running_block_unblock_start_dit(self) -> None:
        """W12. running → block → unblock → start : `lancee_sous` gardé, la reprise est DITE."""
        a, t, s1, t1 = self.lance_sous_trace()
        self.poser(a, done_at=iso_ms(t1 + 1000))
        tasks.block_task(self.root, t, note="attente")
        tasks.unblock_task(self.root, t)
        self.assertEqual(self.tache(t).get("lancee_sous"), s1)
        self.assertIn(f"TASKS: {t} REPRISE_DITE", self.start(t))

    def test_w14_reopen_efface_le_cycle_clos(self) -> None:
        """W14. `reopen` efface `lancee_sous` et `done_at` : la tâche rouverte est JUGÉE.
        MUTANT : `reopen` les garde ⇒ REPRISE_DITE, passe, rouge."""
        a, t, _s1, t1 = self.lance_sous_trace()
        self.done(t)
        self.assertTrue(self.tache(t).get("done_at") and self.tache(t).get("lancee_sous"))
        tasks.reopen_task(self.root, t, "reprise de banc")
        self.assertEqual((self.tache(t).get("lancee_sous"), self.tache(t).get("done_at"),
                          self.tache(t).get("lancee_le")), (None, None, None))
        self.poser(a, done_at=iso_ms(t1 + 1000))
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.refus(self.start, t))

    def test_w16_start_depuis_done_amont_re_clos_apres_la_trace(self) -> None:
        """W16 (réserve C1). Aval clos sous S1, amont rouvert PUIS re-clos après S1 : le `start` de
        l'aval depuis `done` est refusé PLAN_A_REPLANIFIER. MUTANT : `lancee_sous`/`done_at`
        gardés au `start` depuis `done` (ou effacés APRÈS le jugement) ⇒ REPRISE_DITE, rouge."""
        a, t, _s1, _t1 = self.lance_sous_trace()
        self.done(t)
        tasks.reopen_task(self.root, a, "amont à refaire")
        self.done(a)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", self.refus(self.start, t))

    def test_w16b_start_depuis_done_qui_passe_efface_le_cycle_clos(self) -> None:
        """W16b (réserve C1). Aval clos, nouvelle trace S2 après la clôture de l'amont : le `start`
        depuis `done` passe ; au DISQUE, `done_at` absent et `lancee_sous` = S2. MUTANT : champs
        gardés au `start` depuis `done` ⇒ `done_at` resté, rouge."""
        _a, t, _s1, _t1 = self.lance_sous_trace()
        self.done(t)
        s2 = self.tracer(t, sid_ulid(maintenant_ms()), jour=datetime.now().date().isoformat())
        self.assertIn("→ running", self.start(t))
        disque = json.loads((self.d / ".agents" / "state" / "board" / "TASKS.json").read_text(encoding="utf-8"))
        brut = next(x for x in disque["tasks"] if x["id"] == t)
        self.assertNotIn("done_at", brut)
        self.assertEqual(brut.get("lancee_sous"), s2)

    def test_w17_cli_deps_ready_reprise_dite_rc0_et_replanifier_rc1(self) -> None:
        """W17. En sous-processus : REPRISE_DITE rc 0 sur le cas W11 ; PLAN_A_REPLANIFIER rc 1 pour
        une tâche jamais lancée sous la trace. MUTANT : sans `lancee_sous` ⇒ rc 1, rouge."""
        a, t, s1, t1 = self.lance_sous_trace()
        u = self.new("jamais lancée")
        self.dep(u, a)
        self.tracer(u, sid_ulid(t1 + 5))
        self.poser(a, done_at=iso_ms(t1 + 1000))
        r = self.cli("deps-ready", t)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[:2], ["deps-ready: REPRISE_DITE",
                                                     f"lancée sous {s1} : reprise DITE, jamais une révision"])
        r = self.cli("deps-ready", u)
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (1, "deps-ready: PLAN_A_REPLANIFIER"), r.stderr)

    def test_w18_done_block_start_jamais_reprise_du_cycle_clos(self) -> None:
        """W18 (réserve C3). done → block → start : `block` efface le cycle clos, le `start` est
        JUGÉ — jamais REPRISE_DITE sur le plan d'un cycle clos. MUTANT : `block` garde
        `lancee_sous` ⇒ REPRISE_DITE, passe, rouge."""
        a, t, _s1, t1 = self.lance_sous_trace()
        self.done(t)
        self.poser(a, done_at=iso_ms(t1 + 1000))
        tasks.block_task(self.root, t, note="rebloquée après clôture")
        self.assertEqual((self.tache(t).get("lancee_sous"), self.tache(t).get("done_at")), (None, None))
        msg = self.refus(self.start, t)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", msg)
        self.assertNotIn("REPRISE_DITE", msg)

    def test_w19_done_rejoue_ne_reecrit_pas_done_at(self) -> None:
        """W19 (réserve C4 iv). `done_at` est posé à l'ENTRÉE dans `done` : un `done` rejoué sur une
        tâche close le garde. MUTANT : `done_at` à chaque `done` ⇒ réécrit, rouge."""
        t = self.new("T")
        self.done(t)
        self.poser(t, done_at="2026-01-01T00:00:00.000Z")
        self.done(t)
        self.assertEqual(self.tache(t)["done_at"], "2026-01-01T00:00:00.000Z")

    def test_w21_amont_ouvert_precede_reprise_dite(self) -> None:
        """W21 (réserve C4 i). Lancée sous la trace élue ET un amont ouvert : AMONT_OUVERT, rc 1 —
        jamais un REPRISE_DITE rc 0 qui enverrait le lanceur vers un `start` refusé."""
        a, t, _s1, t1 = self.lance_sous_trace()
        self.poser(a, done_at=iso_ms(t1 + 1000))
        self.assertEqual(self.ready(t)[1][0], "deps-ready: REPRISE_DITE")
        b = self.new("B ouvert")
        self.dep(t, a, b)
        rc, lignes = self.ready(t)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: AMONT_OUVERT"))

    def test_w22_sortie_de_running_inscrit_lancee_sous_s_il_manque(self) -> None:
        """W22. Lancée AVANT toute trace, puis trace posée : `block` depuis `running` et la sortie
        explicite vers `pending` inscrivent la trace élue ; le `start` d'une autre ne rétrograde pas.
        MUTANTS : inscription retirée ⇒ absent, rouge ; rétrogradation rétablie, rouge."""
        t, u = self.new("T"), self.new("U")
        self.start(t)
        s1 = self.tracer(t, sid_ulid(maintenant_ms() - HEURE))
        tasks.block_task(self.root, t, note="attente")
        self.assertEqual(self.tache(t).get("lancee_sous"), s1)
        tasks.unblock_task(self.root, t)
        self.poser(u, state="running")
        su = self.tracer(u, sid_ulid(maintenant_ms() - HEURE + 7), rel="plans/u.md")
        self.sortir(u)
        self.assertEqual((self.tache(u)["state"], self.tache(u).get("lancee_sous")), ("pending", su))

    def test_w23_start_running_running_reinscrit_la_trace_elue(self) -> None:
        """W23. Le second `start` d'une tâche EN VOL n'est pas jugé mais réinscrit `lancee_sous` à la
        trace élue COURANTE (« inscrit à tout start qui passe ») : S2 posée après S1 ⇒ S2.
        MUTANT MZ : rien d'inscrit sur running → running ⇒ S1 reste, rouge."""
        _a, t, s1, t1 = self.lance_sous_trace()
        s2 = self.tracer(t, sid_ulid(t1 + 10 * 60_000))
        self.assertNotEqual(s1, s2)
        self.assertIn("→ running", self.start(t))
        self.assertEqual(self.tache(t).get("lancee_sous"), s2)

    def test_w24_set_state_vers_pending_ou_blocked(self) -> None:
        """W24. `set_state` vers `pending`/`blocked` (API de STATES ; appelants : test_tasks.py:1863
        et :2022, contrat écrit à tasks_verbes.py:159) : depuis `running`, la trace élue est inscrite
        si elle manque ; depuis `done`, le cycle clos tombe. MUTANT MW : ces branches retirées ⇒ rouge."""
        t, u = self.new("T"), self.new("U")
        self.start(t)
        st = self.tracer(t, sid_ulid(maintenant_ms() - HEURE))
        tasks.set_state(self.root, t, "pending")
        self.assertEqual(self.tache(t).get("lancee_sous"), st)
        self.start(u)
        su = self.tracer(u, sid_ulid(maintenant_ms() - HEURE + 3), rel="plans/u.md")
        tasks.set_state(self.root, u, "blocked")
        self.assertEqual(self.tache(u).get("lancee_sous"), su)
        self.done(u)
        self.assertTrue(self.tache(u).get("done_at"))
        tasks.set_state(self.root, u, "pending")
        self.assertEqual((self.tache(u).get("lancee_sous"), self.tache(u).get("done_at")), (None, None))

    def test_w27_cause_sans_done_at_forcee_puis_relancee_reprise_dite(self) -> None:
        """W27 (exec-critic P7, MAJEUR). Cause (c) : amont clos SANS `done_at` (avant ce code, qui seul
        l'écrit), touché après le jour de la trace ⇒ PLAN_A_REPLANIFIER ; le pilote force le `start`
        (`--sans-dependances`), la tâche sort de `running`, sa relance sous la MÊME trace est une REPRISE :
        une clôture sans `done_at` précède tout `lancee_le`. MUTANT : `… is not None and f <= lance`
        (une cause sans `done_at` jamais « au plus tard ») ⇒ relance refusée PLAN_A_REPLANIFIER, rouge."""
        a, t = self.new("amont"), self.new("aval")
        self.dep(t, a)
        self.done(a)
        self.poser(a, done_at=None, updated="2099-12-31")
        s1 = self.tracer(t, sid_ulid(maintenant_ms() - HEURE))
        self.assertEqual(self.ready(t)[1][0], "deps-ready: PLAN_A_REPLANIFIER")
        self.assertIn("→ running", self.start(t, sans_dependances="pilote : replanification assumée"))
        self.assertTrue(self.tache(t).get("lancee_le"), "le start forcé n'a pas posé lancee_le")
        self.sortir(t)
        self.assertEqual((self.tache(t)["state"], self.tache(t).get("lancee_sous")), ("pending", s1))
        rc, lignes = self.ready(t)
        self.assertEqual((rc, lignes[:2]), (0, ["deps-ready: REPRISE_DITE",
                                                f"lancée sous {s1} : reprise DITE, jamais une révision"]))
        self.assertIn(f"REPRISE_DITE — lancée sous {s1} : reprise DITE", self.start(t))

    def test_w28_lancee_le_pose_quand_la_trace_change_seulement(self) -> None:
        """W28 (exec-critic, réserve 3). `lancee_le` est posé quand la trace CHANGE (patch C6, qui fait foi
        sur le « à tout start » de S-01M50AKX95G) : une relance sous la MÊME trace garde la sentinelle ; sous
        une trace NEUVE il est reposé. MUTANT M5 : `lancee_le` à chaque `start` hors `running` ⇒ sentinelle
        écrasée à la relance, rouge (M1, jamais écrit ⇒ sentinelle gardée sous S2, rouge aussi)."""
        _a, t, s1, t1 = self.lance_sous_trace()
        sentinelle = "2026-01-01T00:00:00.000Z"
        self.poser(t, lancee_le=sentinelle)
        self.sortir(t)
        self.assertIn("→ running", self.start(t))
        self.assertEqual((self.tache(t).get("lancee_sous"), self.tache(t).get("lancee_le")), (s1, sentinelle))
        s2 = self.tracer(t, sid_ulid(t1 + 10 * 60_000, queue="ZZZZZZZZZZZZZZZZ"))
        self.sortir(t)
        self.assertIn("→ running", self.start(t))
        self.assertEqual(self.tache(t).get("lancee_sous"), s2)
        self.assertNotEqual(self.tache(t).get("lancee_le"), sentinelle)

    def test_w29_sans_dependances_sur_amont_ouvert_puis_amont_clos_replanifier(self) -> None:
        """W29 (exec-critic P4, borne DITE au task-board). `start --sans-dependances` devant un amont OUVERT :
        la dérogation ne couvre pas la clôture À VENIR de cet amont — clos après `lancee_le`, la relance de
        la tâche sortie de `running` est PLAN_A_REPLANIFIER (re-déroger ou réviser). MUTANT M2 : `lancee_le` ignoré
        au jugement ⇒ REPRISE_DITE, la relance passe, rouge."""
        a, t = self.new("amont"), self.new("aval")
        self.dep(t, a)
        s1 = self.tracer(t, sid_ulid(maintenant_ms() - HEURE))
        self.assertEqual(self.ready(t)[1][0], "deps-ready: AMONT_OUVERT")
        self.assertIn("→ running", self.start(t, sans_dependances="pilote : amont ouvert assumé"))
        self.assertEqual(self.tache(t).get("lancee_sous"), s1)
        lance_ms = tasks._ms_utc(tasks._instant_done_at(self.tache(t)["lancee_le"]))
        self.sortir(t)
        self.done(a)
        self.poser(a, done_at=iso_ms(lance_ms + 1000))
        self.assertEqual((self.ready(t)[0], self.ready(t)[1][0]), (1, "deps-ready: PLAN_A_REPLANIFIER"))
        msg = self.refus(self.start, t)
        self.assertIn("deps-ready: PLAN_A_REPLANIFIER", msg)
        self.assertNotIn("REPRISE_DITE", msg)
        self.assertIn("un amont en cause a été clos APRÈS ce lancement", msg)  # F6 : le refus dit sa raison

    def test_w30_lancee_le_illisible_replanifie(self) -> None:
        """W30 (revue de clôture 2, F2, MAJEUR). Un `lancee_le` PRÉSENT mais illisible ne prouve plus la
        reprise : la tâche, en REPRISE_DITE sous un `lancee_le` lisible, rend PLAN_A_REPLANIFIER, rc 1, et
        l'avis le dit (F6). MUTANT : illisible lu comme absent (`lance is None` ⇒ reprise) ⇒ rc 0, rouge."""
        a, t, _s1, _t1 = self.lance_sous_trace()
        lance = self.tache(t)["lancee_le"]
        tasks.reopen_task(self.root, a, "amont à refaire")
        self.sortir(t)
        self.done(a)
        self.poser(a, done_at=iso_ms(tasks._ms_utc(tasks._instant_done_at(lance)) - 1000))
        self.assertEqual(self.ready(t)[1][0], "deps-ready: REPRISE_DITE")
        self.poser(t, lancee_le="2026-13-99 illisible")
        rc, lignes = self.ready(t)
        self.assertEqual((rc, lignes[0]), (1, "deps-ready: PLAN_A_REPLANIFIER"))
        self.assertIn("`lancee_le` illisible", "\n".join(lignes))


if __name__ == "__main__":
    unittest.main()
