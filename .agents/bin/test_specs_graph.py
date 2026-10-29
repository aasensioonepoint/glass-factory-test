"""Tests for specs_graph.py — the default specs-graph generator (T-00000379 lot E).

BOTH HALVES, and that is a DEPARTURE from the upstream suite this file is
adopted from. Theirs is producer-side only and delegates the reader half to its
own `test_dashboard.py` specs section. We have no such section, so keeping their
sentence would have been a doc asserting a guarantee the code does not hold —
the reader cases live here instead, named as such, and they go through the REAL
`dashboard_readers` module rather than a re-implementation of its rules.

What must hold here:

- the projection stores -> contract shape (states to rings, kinds to statuts,
  blocked -> synthetic a_prendre, numeric task identity, citation edges);
- the precedence rule: a hand-published artifact (no ``generator`` marker) is
  NEVER overwritten without --force — this is the property that makes it safe
  to run the generator from hooks on every task closure;
- the generated artifact actually satisfies the real reader (round-trip
  through dashboard_readers.build_specs_graph, not through a re-implementation
  of its checks);
- bounds are applied generator-side and SAID, never silent;
- reader-side: absence is a STATED rest state (never an empty frame), a
  malformed or off-contract artifact degrades with its cause named, a HAND
  publication is bounded by the reader (it passed through no generator) and the
  truncation is announced, and the section is actually reachable under
  `views.specs_graph` — a builder nobody wires is a mechanism without a reader.

Same conventions as test_specs.py: unittest.TestCase, a TemporaryDirectory per
test, direct library imports, exactly one subprocess test for the CLI contract.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import specs_graph

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "specs_graph.py"

# `P-<ULID>` bodies (T-00000726): U_LETTER ends in a LETTER — the old `T-(\d+)`
# grammar does not see it at all; U_DIGIT ends in "2" — keyed on its trailing
# digits it would BE task 2.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


def _load_reader():
    """The REAL dashboard reader — the round-trip must go through the code that
    serves /api/snapshot, not through a copy of its validation rules.

    NOT registered in sys.modules, and that is the point. `dashboard_readers`
    carries a MODULE-LEVEL memo (`_views_cache`, keyed on a fingerprint of the
    source files). Registering it under a stable name would share that memo
    across every test in this file: a fixture written by one case would be
    served, from cache, to the next — and the two reader cases that publish
    DIFFERENT artifacts at the same path would read each other's. A fresh
    module per call costs microseconds and removes the whole class.

    `test_dashboard.py` registers its own load because it wants the opposite:
    one `dashboard` module shared by the whole file, with `reset_cache_for_tests`
    called explicitly where it matters.
    """
    spec = importlib.util.spec_from_file_location("dashboard_readers_rt", HERE / "dashboard_readers.py")
    module = importlib.util.module_from_spec(spec)
    # unregistered on purpose: a fresh module per call keeps `_views_cache`
    # private to the case under test — see the docstring above.
    spec.loader.exec_module(module)
    return module


def write_stores(root: Path, board=None, journal=None, memory=None) -> None:
    """Hand-crafted but VALID stores — the generator reuses the store CLIs'
    loaders, so anything written here must pass their validation."""
    paths = {
        root / ".agents/state/board/TASKS.json": {"next_id": 1, "tasks": board or []},
        root / ".agents/state/specs/SPECS.json": {"next_id": 1, "entries": journal or []},
        root / ".agents/state/memory/LEDGER.json": {"next_id": 1, "entries": memory or []},
    }
    for path, data in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def task_row(tid: str, state: str, title: str, stage: str = "", updated: str = "2026-08-01"):
    return {"id": tid, "state": state, "task": title, "owner": "", "stage": stage, "updated": updated}


def journal_entry(sid: str, task: str, kind: str, title: str, text: str = "", date: str = "2026-08-01"):
    return {"id": sid, "task": task, "kind": kind, "title": title, "text": text, "files": [], "date": date}


def ledger_entry(lid: str, category: str, title: str, related: str = "", status: str = "active", text: str = ""):
    return {
        "id": lid,
        "category": category,
        "title": title,
        "text": text,
        "created": "2026-08-01",
        "tags": [],
        "related": related,
        "status": status,
    }


def standard_stores(root: Path) -> None:
    """One board with all four states, a journal exercising all four kinds
    (plus one dangling task ref), and a ledger with every routing case."""
    write_stores(
        root,
        board=[
            task_row("T-00000001", "done", "Socle initial"),
            task_row("T-00000002", "running", "Feature en cours"),
            task_row("T-00000003", "blocked", "Choix techno", stage="attente pilote: choix DB"),
            task_row("T-00000004", "pending", "Nettoyage"),
        ],
        journal=[
            journal_entry("S-00000001", "T-00000002", "plan", "Plan de la feature"),
            journal_entry("S-00000002", "T-00000001", "decision", "Choix du socle", text="Retenu: option A"),
            journal_entry("S-00000003", "T-00000002", "delta", "Shard 1 livré", text="voir T-00000001 pour le socle"),
            journal_entry("S-00000004", "T-00000001", "verdict", "critic PASS"),
            journal_entry("S-00000005", "T-00000009", "plan", "Tâche purgée du board"),
        ],
        memory=[
            ledger_entry("L-00000001", "decision", "Décision pilote", related="T-00000002"),
            ledger_entry("L-00000002", "constraint", "Contrainte vivante", related="T-00000001", text="détail"),
            ledger_entry("L-00000003", "constraint", "Contrainte retirée", related="T-00000001", status="archived"),
            ledger_entry("L-00000004", "decision", "Décision sans tâche"),
        ],
    )


class SpecsGraphGenerateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        # Windows teardown can race on open handles — cleanup failure must
        # never fail a test (CONVENTIONS_python.md).
        try:
            self._tmp.cleanup()
        except OSError:
            pass

    def read_artifact(self) -> dict:
        return json.loads(specs_graph.artifact_path(self.root).read_text(encoding="utf-8"))

    def node(self, artifact: dict, tid: str) -> dict:
        matches = [n for n in artifact["nodes"] if n["id"] == tid]
        self.assertEqual(len(matches), 1, f"expected exactly one node {tid}")
        return matches[0]

    # --- rest state -----------------------------------------------------------

    def test_empty_stores_publish_nothing(self):
        write_stores(self.root)
        out = specs_graph.generate(self.root)
        self.assertIn("rien à publier", out)
        self.assertFalse(specs_graph.artifact_path(self.root).exists())

    def test_missing_stores_publish_nothing(self):
        out = specs_graph.generate(self.root)  # no .agents/state at all
        self.assertIn("rien à publier", out)
        self.assertFalse(specs_graph.artifact_path(self.root).exists())

    # --- the projection -------------------------------------------------------

    def test_mapping_states_kinds_and_stats(self):
        standard_stores(self.root)
        out = specs_graph.generate(self.root)
        self.assertIn("publié", out)
        self.assertIn("nœud synthétique", out)  # the dangling T-00000009 is said
        artifact = self.read_artifact()

        self.assertEqual(artifact["version"], 1)
        self.assertTrue(artifact["generator"].startswith("specs_graph.py"))
        self.assertEqual(len(artifact["nodes"]), 5)  # 4 board + 1 synthetic

        done = self.node(artifact, "T-00000001")
        self.assertEqual(done["release"], "R0")
        # decision -> prise; verdict on a DONE task -> prise (resolved)
        self.assertEqual(done["counts"], {"prise": 2})
        self.assertEqual({d["id"] for d in done["decisions"]}, {"S-00000002", "S-00000004"})
        self.assertIn("Retenu: option A", next(d["q"] for d in done["decisions"] if d["id"] == "S-00000002"))

        running = self.node(artifact, "T-00000002")
        self.assertEqual(running["release"], "R1")
        # plan on an OPEN task -> en_analyse; active related ledger decision -> prise
        self.assertEqual(running["counts"], {"en_analyse": 1, "prise": 1})
        self.assertEqual({d["id"] for d in running["decisions"]}, {"S-00000001", "L-00000001"})
        # the delta is activity, not a decision — it sizes the node instead
        self.assertEqual(running["size"], {"tasks": 2})

        blocked = self.node(artifact, "T-00000003")
        self.assertEqual(blocked["release"], "R2")
        self.assertEqual(blocked["counts"], {"a_prendre": 1})
        self.assertIn("attente pilote: choix DB", blocked["decisions"][0]["q"])

        pending = self.node(artifact, "T-00000004")
        self.assertEqual(pending["release"], "R3")
        self.assertEqual(pending["counts"], {})

        synthetic = self.node(artifact, "T-00000009")
        self.assertEqual(synthetic["release"], "R3")
        self.assertEqual(synthetic["title"], "Tâche purgée du board")
        # its journal entry still counts: a plan on an open task -> en_analyse
        self.assertEqual(synthetic["counts"], {"en_analyse": 1})

        # citation in S-00000003's text links T-00000002 to T-00000001
        self.assertEqual(
            artifact["edges"],
            [{"source": "T-00000002", "target": "T-00000001", "weight": 1}],
        )

        # only the ACTIVE, related constraint becomes an arbitrage
        self.assertEqual(len(artifact["arbitrages"]), 1)
        self.assertEqual(artifact["arbitrages"][0]["section"], "L-00000002")
        self.assertEqual(artifact["arbitrages"][0]["refs"], ["T-00000001"])

        self.assertEqual(
            artifact["stats"],
            {"decisions": 6, "prise": 3, "prise_a_clore": 0, "a_prendre": 1, "en_analyse": 2},
        )

    def test_task_identity_is_numeric_across_paddings(self):
        # Board spells the task T-001; the journal spells it T-00000001 and a
        # text cites it as T-1 — one node, zero self-edges, board spelling wins.
        write_stores(
            self.root,
            board=[task_row("T-001", "running", "Tâche à identité multiple")],
            journal=[
                journal_entry("S-00000001", "T-00000001", "plan", "Plan", text="continue T-1 ici"),
            ],
        )
        specs_graph.generate(self.root)
        artifact = self.read_artifact()
        self.assertEqual([n["id"] for n in artifact["nodes"]], ["T-001"])
        self.assertEqual(artifact["edges"], [])
        self.assertEqual(self.node(artifact, "T-001")["counts"], {"en_analyse": 1})

    # --- P-<ULID> task ids (T-00000726, C1e) -------------------------------------

    def test_ulid_task_is_a_node_newest_first_within_its_state(self):
        """M15 / board row keyed by `numeric_id`: the ULID rows raise or merge — red.
        Sorted in TWO passes: within a state, newest first — every ULID is newer
        than every legacy id, ULIDs among themselves by minting time."""
        ul, ud = f"T-{U_LETTER}", f"T-{U_DIGIT}"
        write_stores(
            self.root,
            board=[
                task_row("T-00000001", "pending", "a"),
                task_row(ul, "pending", "u-lettre"),
                task_row("T-00000002", "pending", "b"),
                task_row(ud, "pending", "u-chiffre"),
                task_row("T-00000003", "done", "c"),
            ],
        )
        specs_graph.generate(self.root)
        ids = [n["id"] for n in self.read_artifact()["nodes"]]
        self.assertEqual(ids, [ud, ul, "T-00000002", "T-00000001", "T-00000003"])

    def test_ulid_with_digit_tail_is_not_the_legacy_task_of_that_number(self):
        """M15b: `by_num` re-keyed on the trailing digits — `T-<…6M2>` merges into
        T-00000002, one node instead of two, red. Journal ONLY (synthetic nodes):
        `S-<U_DIGIT>` and `S-00000002` in the same journal."""
        ud = f"T-{U_DIGIT}"
        write_stores(
            self.root,
            journal=[
                journal_entry("S-00000002", "T-00000002", "decision", "décision ancienne"),
                journal_entry(f"S-{U_DIGIT}", ud, "decision", "décision ULID"),
            ],
        )
        specs_graph.generate(self.root)
        artifact = self.read_artifact()
        self.assertEqual(sorted(n["id"] for n in artifact["nodes"]), sorted(["T-00000002", ud]))
        self.assertEqual([d["id"] for d in self.node(artifact, "T-00000002")["decisions"]], ["S-00000002"])
        self.assertEqual([d["id"] for d in self.node(artifact, ud)["decisions"]], [f"S-{U_DIGIT}"])

    def test_ulid_citation_is_an_edge_and_edges_sort_on_the_identity_key(self):
        """An `S-<ULID>` entry citing T-00000002 and a legacy entry citing `T-<ULID>`
        both draw edges to the ULID node; a TRUNCATED ULID (25 symbols) cites
        nothing — never `T-01`. Equal weights sort on the identity key: the edge
        whose source is legacy comes first. An `L-<ULID>` decision related to
        `T-<ULID>` lands on it. M15 (`TASK_REF_RE` / `_task_num` left narrow): edges
        and decision lost, red."""
        ul = f"T-{U_LETTER}"
        write_stores(
            self.root,
            board=[
                task_row("T-00000001", "done", "a"),
                task_row("T-00000002", "done", "b"),
                task_row(ul, "running", "u"),
            ],
            journal=[
                journal_entry(f"S-{U_LETTER}", ul, "delta", "x",
                              text=f"voir T-00000002, pas T-{U_LETTER[:-1]} tronqué"),
                journal_entry("S-00000001", "T-00000001", "delta", "y", text=f"suite dans {ul}"),
            ],
            memory=[ledger_entry(f"L-{U_DIGIT}", "decision", "Décision ULID", related=ul)],
        )
        specs_graph.generate(self.root)
        artifact = self.read_artifact()
        self.assertEqual(
            artifact["edges"],
            [
                {"source": "T-00000001", "target": ul, "weight": 1},
                {"source": ul, "target": "T-00000002", "weight": 1},
            ],
        )
        self.assertEqual([d["id"] for d in self.node(artifact, ul)["decisions"]], [f"L-{U_DIGIT}"])
        self.assertNotIn("hors format", " ".join(artifact.get("notes", [])))

    def test_task_num_keys_every_form_as_tasks_identity_key(self):
        all_digit = "0" + "1" * 25
        for tid in ("T-1", "T-001", "T-00000001", "T-" + "9" * 15,
                    f"T-{U_LETTER}", f"T-{U_DIGIT}", f"T-{all_digit}"):
            with self.subTest(tid=tid):
                self.assertEqual(specs_graph._task_num(tid), specs_graph.tasks.identity_key(tid))
        for tid in (f"T-{U_LETTER.lower()}", f"T-{U_LETTER[:-1]}", f"T-{U_LETTER}\n", "T-12a"):
            with self.subTest(tid=tid):
                self.assertIsNone(specs_graph._task_num(tid))

    # --- round-trip through the REAL reader ------------------------------------

    def test_round_trip_reader_accepts_generated_artifact(self):
        """The generated artifact satisfies the REAL reader — not a copy of its
        rules. Two shape differences from the upstream reader are asserted here
        rather than smoothed over, because they are OUR contract:

        - an `ok` section carries NO `reason` key at all (the upstream one sets
          `reason: None`). `lib/section.js` only ever reads `reason` on a
          non-measured status, so a key always present and always empty would be
          a field nobody can act on;
        - the section is FLAT. Every other view of this dashboard puts its
          payload at the top level of the section; a `graph` sub-object would
          make this the one section a reader has to unwrap differently.
        """
        standard_stores(self.root)
        specs_graph.generate(self.root)
        view = _load_reader().build_specs_graph(self.root)
        self.assertEqual(view["status"], "ok")
        self.assertNotIn("reason", view)
        self.assertEqual(view["truncated"], {})
        self.assertEqual(view["published_by"], "generator")
        self.assertEqual(len(view["nodes"]), 5)
        # the edge survives the reader's dangling-edge filter: both ids exist
        self.assertEqual(len(view["edges"]), 1)
        self.assertEqual(view["stats"]["decisions"], 6)

    # --- reader side: what nobody else checks in THIS repo ---------------------
    # The upstream suite delegates these to its own `test_dashboard.py` specs
    # section. We have no such section, so claiming that delegation would be a
    # doc asserting a guarantee the code does not hold. They are covered HERE.

    def test_reader_says_absence_rather_than_rendering_empty(self):
        standard_stores(self.root)
        view = _load_reader().build_specs_graph(self.root)
        self.assertEqual(view["status"], "no_events")
        self.assertIn("specs_graph.py", view["reason"])

    def test_reader_degrades_on_malformed_and_names_the_cause(self):
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version": 1, "nodes": [', encoding="utf-8")
        view = _load_reader().build_specs_graph(self.root)
        self.assertEqual(view["status"], "degraded")
        self.assertIn("JSON", view["reason"])

    def test_reader_refuses_an_unknown_contract_version(self):
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"version": 2, "nodes": []}), encoding="utf-8")
        view = _load_reader().build_specs_graph(self.root)
        self.assertEqual(view["status"], "degraded")
        self.assertIn("version", view["reason"])

    def test_reader_bounds_a_hand_publication_and_says_so(self):
        """The generator applies the bounds itself; a HAND publication passes
        through no generator, so the reader must bound it — and ANNOUNCE it. A
        silent truncation reads as full coverage."""
        reader = _load_reader()
        nodes = [{"id": f"E-{i:03d}", "title": f"n{i}", "release": "R1",
                  "counts": {"prise": 1}, "decisions": []} for i in range(230)]
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"version": 1, "nodes": nodes,
                                      "edges": [{"source": "E-000", "target": "E-229"}]}),
                          encoding="utf-8")
        view = reader.build_specs_graph(self.root)
        self.assertEqual(view["status"], "ok")
        self.assertEqual(view["published_by"], "manual")
        self.assertEqual(len(view["nodes"]), reader._SPECS_GRAPH_NODES_LIMIT)
        self.assertEqual(view["truncated"]["nodes"], 230 - reader._SPECS_GRAPH_NODES_LIMIT)
        # E-229 fell outside the bound, so the edge that pointed at it is DROPPED
        # rather than rendered dangling.
        self.assertEqual(view["edges"], [])

    def test_reader_exposes_the_view_through_build_views(self):
        """The section must be reachable where the SPA reads it — under
        `views.specs_graph` — not merely as a function nobody wires."""
        reader = _load_reader()
        standard_stores(self.root)
        specs_graph.generate(self.root)
        reader.reset_cache_for_tests()
        built = reader.build_views(
            project_root=self.root, events_dir=None, otel_dir=None, normalize_mod=None,
            ledger_section={}, specs_section={}, index_section={}, verdict_section={},
            canal_b_section={}, canal_a_stream={"status": "ok", "records": []},
        )
        self.assertIn("specs_graph", built["views"])
        self.assertEqual(built["views"]["specs_graph"]["status"], "ok")

    # --- precedence: hand publications are never destroyed ---------------------

    def test_hand_published_artifact_is_preserved(self):
        standard_stores(self.root)
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        manual = '{"version": 1, "title": "publication manuelle", "nodes": []}\n'
        target.write_text(manual, encoding="utf-8")

        out = specs_graph.generate(self.root)
        self.assertIn("publication manuelle préservée", out)
        self.assertIn("--force", out)
        self.assertEqual(target.read_text(encoding="utf-8"), manual)

    def test_invalid_json_artifact_counts_as_manual(self):
        # A half-edited hand publication must not be "repaired" into a
        # generated file — unparseable means untouchable.
        standard_stores(self.root)
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{not json", encoding="utf-8")
        out = specs_graph.generate(self.root)
        self.assertIn("préservée", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "{not json")

    def test_unreadable_artifact_counts_as_manual_not_absent(self):
        # Unreadable ≠ absent: a locked/permission-broken/dehydrated file may
        # be somebody's hand publication. A directory squatting the path makes
        # read_text raise an OSError that is NOT FileNotFoundError, on every
        # platform — the review's mode-000 reproduction, without chmod (which
        # does not block reads on Windows).
        standard_stores(self.root)
        target = specs_graph.artifact_path(self.root)
        target.mkdir(parents=True, exist_ok=True)
        self.assertEqual(specs_graph.published_state(target), "manual")
        out = specs_graph.generate(self.root)
        self.assertIn("préservée", out)
        self.assertTrue(target.is_dir())  # untouched
        # and --force against the same unwritable target fails CLEANLY (rc 2),
        # never a raw traceback out of a hook
        rc = specs_graph.main(["--root", str(self.root), "generate", "--force"])
        self.assertEqual(rc, 2)

    def test_force_overwrites_manual_and_says_so(self):
        standard_stores(self.root)
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"nodes": []}', encoding="utf-8")
        out = specs_graph.generate(self.root, force=True)
        self.assertIn("écrasé (--force)", out)
        self.assertTrue(self.read_artifact()["generator"].startswith("specs_graph.py"))

    def test_marker_authorizes_refresh(self):
        standard_stores(self.root)
        specs_graph.generate(self.root)
        # the project moves on: a new task lands on the board
        board = json.loads((self.root / ".agents/state/board/TASKS.json").read_text(encoding="utf-8"))
        board["tasks"].append(task_row("T-00000010", "pending", "Nouvelle tâche"))
        (self.root / ".agents/state/board/TASKS.json").write_text(json.dumps(board), encoding="utf-8")

        out = specs_graph.generate(self.root)
        self.assertIn("rafraîchi", out)
        self.node(self.read_artifact(), "T-00000010")

    def test_unchanged_graph_is_not_rewritten(self):
        # Idempotence: the automated callers run at every session start and
        # task closure — identical content must not churn generated_at (a
        # project that tracks the artifact would otherwise be dirty forever).
        standard_stores(self.root)
        specs_graph.generate(self.root)
        before = specs_graph.artifact_path(self.root).read_bytes()
        out = specs_graph.generate(self.root)
        self.assertIn("inchangé", out)
        self.assertEqual(specs_graph.artifact_path(self.root).read_bytes(), before)

    def test_empty_project_never_replaces_existing_artifact(self):
        write_stores(self.root)  # stores exist but are empty
        target = specs_graph.artifact_path(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"generator": "specs_graph.py v1", "nodes": [{"id": "X"}]}', encoding="utf-8")
        out = specs_graph.generate(self.root)
        self.assertIn("conservé tel quel", out)
        self.assertIn("X", target.read_text(encoding="utf-8"))

    def test_malformed_ledger_related_costs_one_entry_not_the_graph(self):
        # ledger.load does NOT validate `related` format (only add() does), so
        # a hand-migrated store can carry "T-2,T-3". That must skip the one
        # rattachement WITH a note — never exit 2, which the hooks swallow and
        # which would freeze graph refresh forever.
        write_stores(
            self.root,
            board=[task_row("T-00000002", "done", "A"), task_row("T-00000003", "done", "B")],
            memory=[ledger_entry("L-00000001", "decision", "Double rattachement", related="T-2,T-3")],
        )
        out = specs_graph.generate(self.root)
        self.assertIn("publié", out)
        self.assertIn("hors format T-NNN", out)
        artifact = self.read_artifact()
        self.assertIn("hors format T-NNN", " ".join(artifact["notes"]))  # persisted, not just stdout
        for node in artifact["nodes"]:
            self.assertEqual(node["decisions"], [])  # attached to neither task

    def test_journal_task_id_beyond_15_digits_still_graphs(self):
        # specs.py accepts unbounded T-\d+ — the generator must too.
        write_stores(
            self.root,
            journal=[journal_entry("S-00000001", "T-9999999999999999", "plan", "Tâche géante")],
        )
        specs_graph.generate(self.root)
        self.node(self.read_artifact(), "T-9999999999999999")

    def test_letter_suffix_is_not_a_citation_but_branch_style_is(self):
        write_stores(
            self.root,
            board=[task_row("T-00000001", "done", "A"), task_row("T-00000002", "done", "B"),
                   task_row("T-00000003", "done", "C")],
            journal=[
                journal_entry("S-00000001", "T-00000002", "delta", "x", text="jeton T-1abc sans lien"),
                journal_entry("S-00000002", "T-00000003", "delta", "y", text="branche feat/T-1-fix livrée"),
            ],
        )
        specs_graph.generate(self.root)
        edges = self.read_artifact()["edges"]
        self.assertEqual(
            edges, [{"source": "T-00000003", "target": "T-00000001", "weight": 1}]
        )

    # --- bounds are generator-side and never silent -----------------------------

    def test_node_cap_keeps_active_work_and_drops_oldest_done(self):
        board = [task_row(f"T-{i:08d}", "done", f"Tâche {i}", updated="2026-07-01") for i in range(1, 205)]
        board.append(task_row("T-00000205", "running", "Tâche active"))
        write_stores(self.root, board=board)
        out = specs_graph.generate(self.root)
        self.assertIn("au-delà de la borne", out)
        artifact = self.read_artifact()
        self.assertEqual(len(artifact["nodes"]), specs_graph.MAX_NODES)
        self.assertEqual(artifact["nodes"][0]["id"], "T-00000205")  # active first
        ids = {n["id"] for n in artifact["nodes"]}
        self.assertIn("T-00000204", ids)   # newest done survives
        self.assertNotIn("T-00000001", ids)  # oldest done goes first

    def test_node_cap_on_open_heavy_board_keeps_newest_pending(self):
        # Above 200 OPEN tasks, the cap must drop the OLDEST pending — the
        # board view's newest-first priority — never the recent open work.
        board = [task_row(f"T-{i:08d}", "pending", f"P{i}") for i in range(1, 203)]
        write_stores(self.root, board=board)
        specs_graph.generate(self.root)
        ids = {n["id"] for n in self.read_artifact()["nodes"]}
        self.assertIn("T-00000202", ids)
        self.assertNotIn("T-00000001", ids)
        self.assertNotIn("T-00000002", ids)

    def test_decisions_cap_keeps_newest_but_counts_all(self):
        journal = [
            journal_entry(f"S-{i:08d}", "T-00000001", "decision", f"Décision {i}")
            for i in range(1, 67)
        ]
        write_stores(self.root, board=[task_row("T-00000001", "running", "Dense")], journal=journal)
        out = specs_graph.generate(self.root)
        self.assertIn("décision(s) au-delà de la borne", out)
        node = self.node(self.read_artifact(), "T-00000001")
        self.assertEqual(len(node["decisions"]), specs_graph.MAX_DECISIONS_PER_NODE)
        self.assertEqual(node["decisions"][-1]["id"], "S-00000066")  # newest kept
        self.assertEqual(node["counts"], {"prise": 66})  # tally stays true

    # --- hygiene ----------------------------------------------------------------

    def test_atomic_write_leaves_no_tmp_residue(self):
        standard_stores(self.root)
        specs_graph.generate(self.root)
        residue = list(specs_graph.artifact_path(self.root).parent.glob(".specs-graph-*.tmp"))
        self.assertEqual(residue, [])

    def test_status_reports_all_three_states(self):
        standard_stores(self.root)
        self.assertIn("absent", specs_graph.status(self.root))
        specs_graph.generate(self.root)
        self.assertIn("généré par le kit", specs_graph.status(self.root))
        specs_graph.artifact_path(self.root).write_text('{"nodes": []}', encoding="utf-8")
        self.assertIn("publication manuelle", specs_graph.status(self.root))


class SpecsGraphCliTests(unittest.TestCase):
    """The CLI contract, through a real subprocess — same single-subprocess
    doctrine as test_specs.py: rc 0 on success, rc 2 on a malformed store."""

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_stores(root, board=[task_row("T-00000001", "done", "OK")])
            done = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", tmp, "generate"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("SPECS_GRAPH", done.stdout)

            (root / ".agents/state/board/TASKS.json").write_text("{broken", encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", tmp, "generate"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(broken.returncode, 2)
            self.assertIn("specs_graph.py:", broken.stderr)


class SpecsGraphDocTests(unittest.TestCase):
    """T-00000724 — the module docstring says on which hosts the `done` hook that
    refreshes the graph is REGISTERED. This pins the REGISTRATION — what the kit's
    own host files declare — never a runtime observation: the hook is measured
    firing on Claude Code only, the other hosts register it with a runtime not
    measured here.

    The closed list is copied from `DECLARATIONS` (`.agents/evals/test_contract_diff.py`),
    same hosts, same order, plus the name the docstring displays. A declaration
    file that is absent is a NAMED skip: the registering set cannot be read, and a
    silent pass would read as « the docstring is right »."""

    #: (host, declaration file, name displayed in the docstring) — order and
    #: membership copied from test_contract_diff.py `DECLARATIONS`.
    DECLARATIONS = (
        ("claude", ".claude/settings.json", "Claude Code"),
        ("codex", ".codex/hooks.json", "Codex"),
        ("gemini", ".agents/hooks.json", "Gemini"),
        ("kimi", ".kimi-code/hooks.json", "Kimi Code"),
        ("copilot", ".github/hooks/agent-guardrails.json", "Copilot"),
    )
    CARDINALS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    HOOK = "post-task-done-index"
    CLAIM = re.compile(r"on the (\w+) hosts that register that hook \(([^)]*)\)")

    def _registering_hosts(self) -> list[str]:
        repo = HERE.parent.parent
        names = []
        for _host, rel, shown in self.DECLARATIONS:
            path = repo / rel
            if not path.is_file():
                self.skipTest(f"SKIP SpecsGraphDocTests : {rel} absent — the registering set is unreadable")
            if self.HOOK in path.read_text(encoding="utf-8"):
                names.append(shown)
        return names

    def test_the_docstring_names_exactly_the_hosts_that_register_the_hook(self):
        doc = " ".join((specs_graph.__doc__ or "").split())
        claim = self.CLAIM.search(doc)
        self.assertIsNotNone(claim, "the docstring no longer says which hosts register the hook")
        hosts = self._registering_hosts()
        self.assertTrue(hosts, "non-vacuity: no declaration file registers the hook at all")
        named = {name.strip() for name in claim.group(2).split(",")}
        self.assertEqual(named, set(hosts), "hosts named in the docstring != hosts whose file registers the hook")
        self.assertEqual(claim.group(1), self.CARDINALS.get(len(hosts)), "the cardinal word does not match the count")
        self.assertNotIn("three hosts", doc)


if __name__ == "__main__":
    unittest.main()
