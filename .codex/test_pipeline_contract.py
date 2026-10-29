import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PipelineContractTests(unittest.TestCase):
    def setUp(self):
        self.kickoff = (ROOT / ".agents" / "skills" / "kickoff" / "SKILL.md").read_text(encoding="utf-8")
        self.orchestrator = (ROOT / ".codex" / "agents" / "orchestrator.toml").read_text(encoding="utf-8")
        self.detector = (ROOT / ".codex" / "agents" / "language-detector.toml").read_text(encoding="utf-8")
        self.planner = (ROOT / ".codex" / "agents" / "planner.toml").read_text(encoding="utf-8")
        self.plan_critic = (ROOT / ".codex" / "agents" / "plan-critic.toml").read_text(encoding="utf-8")
        self.budgets = (ROOT / ".agents" / "ref" / "TOKEN_BUDGETS.md").read_text(encoding="utf-8")
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        # renamed in b96599d when Gemini/Antigravity joined the non-Claude hosts
        self.codex_readme = (ROOT / "README-OTHER-HOSTS.md").read_text(encoding="utf-8")
        # T-00000123: the four host skills-resolver files must name the OIDC 401
        # and the pinned-GitHub fallback, so a future edit cannot silently
        # regress to "skills.sh is the dynamic install path".
        self.resolver_claude = (ROOT / ".claude" / "agents" / "skills-resolver.md").read_text(encoding="utf-8")
        self.resolver_gemini = (ROOT / ".gemini" / "agents" / "skills-resolver.md").read_text(encoding="utf-8")
        self.resolver_codex = (ROOT / ".codex" / "agents" / "skills-resolver.toml").read_text(encoding="utf-8")
        self.resolver_github = (ROOT / ".github" / "agents" / "skills-resolver.agent.md").read_text(encoding="utf-8")

    def test_kickoff_orders_detector_planner_gate_and_mutators(self):
        idx_detector = self.kickoff.index("language-detector")
        idx_planner = self.kickoff.index("planner")
        idx_critic = self.kickoff.index("plan-critic")
        idx_gate = self.kickoff.index("HUMAN APPROVAL GATE")
        idx_dev = self.kickoff.index("dev-mono or dev-multi")
        idx_documenter = self.kickoff.index("documenter")
        idx_indexer = self.kickoff.index("indexer")
        positions = [idx_detector, idx_planner, idx_critic, idx_gate, idx_dev, idx_documenter, idx_indexer]
        self.assertEqual(positions, sorted(positions))
        pre_gate = self.kickoff[:idx_gate]
        self.assertIn("plan-critic", pre_gate, "plan-critic must sit inside the pre-gate section")
        for mutator in ("skills-sync", "docs-sync", "modeler", "optimizer", "dev-mono", "documenter", "indexer"):
            self.assertNotIn(mutator, pre_gate)
        self.assertNotIn("Stop for approval after the routing summary", self.kickoff)

    def test_kickoff_process_section_has_one_gate_in_order(self):
        # anchored on the step TEXT, not its number: renumbering the process
        # list is routine and must not read as a broken pipeline contract
        process = self.kickoff[self.kickoff.index("Invoke `language-detector`") :]
        process = process.split("## Rules", 1)[0]
        positions = [
            process.index("Invoke `language-detector`"),
            process.index("Dispatch `planner`"),
            # T-00000624 avait ancre la PAIRE ; la decision pilote S-00003871
            # (2026-10-03) la remplace par UN critique. L ancre porte toujours sur
            # le CONTRAT et non sur un nom de def : « ONE plan critic » doit casser
            # ce test s il disparait — un ancrage sur `plan-critic` seul resterait
            # vert le jour ou la skill reviendrait a la paire sans le dire.
            process.index("Hand the plan to **ONE plan critic, `plan-critic`**"),
            process.index("HUMAN APPROVAL GATE"),
            process.index("After approval"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(process.count("HUMAN APPROVAL GATE"), 1)

    def test_orchestrator_routes_without_owning_approval_gate(self):
        self.assertIn("Do not ask for approval", self.orchestrator)
        self.assertIn("planner owns the approval gate", self.orchestrator)
        self.assertNotIn("Stop after the routing plan", self.orchestrator)

    def test_detector_json_is_framed_by_required_agent_banners(self):
        self.assertIn("one JSON object between the required start and end banners", self.detector)
        self.assertNotIn("Output exactly one JSON object:", self.detector)

    def test_planner_extracts_detector_json_and_is_only_pre_gate_writer(self):
        self.assertIn("Extract the single JSON object between the detector banners", self.planner)
        self.assertIn("HUMAN APPROVAL GATE", self.planner)
        self.assertIn("Do not edit code", self.planner)
        # plan-critic now also sits pre-gate (between planner and the gate), so
        # "planner is the only pre-gate writer" must be asserted explicitly: the
        # critic is read-only and invokes neither tasks.py nor ledger.py.
        # Read as TOML (T-00000707, closing pass): since that task the def's
        # prose also spells `sandbox_mode = "read-only"`, so a whole-file
        # substring is satisfied by the prose whatever line 5 says (L-00000500)
        # — and a line-anchored regex is still satisfied by a declaration-shaped
        # line smuggled inside the multi-line string. `tomllib` reads the table,
        # not the bytes. Same witness as `_sandbox_mode_toml` in
        # .agents/evals/test_plan_critic_contract.py — NOT imported: neither
        # directory is a package, and a sys.path hack would be a third way to
        # reach one file. Keep the two in step by hand (cross-comment there).
        self.assertEqual(tomllib.loads(self.plan_critic).get("sandbox_mode"), "read-only")
        self.assertNotIn("bin/tasks.py", self.plan_critic)
        self.assertNotIn("bin/ledger.py", self.plan_critic)
        self.assertIn("writes nothing", self.plan_critic.lower())

    def test_kickoff_places_deterministic_rebuild_after_security_before_documenter(self):
        # T-013: reader-side index freshness. The deterministic (0 LLM)
        # rebuild step must be inserted after the security stage and before
        # documenter's first mention in the kickoff process — never routed
        # through the indexer AGENT, which stays a conditional,
        # annotation-only stage.
        idx_security = self.kickoff.index("security-code-review")
        idx_rebuild = self.kickoff.index("deterministic index rebuild")
        idx_documenter = self.kickoff.index("documenter")
        self.assertLess(
            idx_security, idx_rebuild,
            "deterministic index rebuild must sit after the security stage",
        )
        self.assertLess(
            idx_rebuild, idx_documenter,
            "deterministic index rebuild must sit before documenter",
        )

    def test_active_agents_and_index_skill_use_canonical_memory_and_budgets(self):
        active = [
            ROOT / ".agents" / "skills" / "index" / "SKILL.md",
            ROOT / ".codex" / "agents" / "indexer.toml",
            ROOT / ".codex" / "agents" / "modeler.toml",
        ]
        for path in active:
            self.assertNotIn(".codex/index", path.read_text(encoding="utf-8"), path)
        self.assertIn("TOKEN_BUDGETS.md", self.kickoff)
        self.assertIn("TOKEN_BUDGETS.md", self.orchestrator)
        self.assertIn("TOKEN_BUDGETS.md", self.planner)
        # T-00000353: `exec-critic` is ROUTED by all four orchestrator defs on every
        # task that produces work, and those defs REQUIRE a `~Nk` per pipeline agent
        # "from .agents/ref/TOKEN_BUDGETS.md" — but it had no row. A chain of N links
        # with only the ROUTING link wired (L-00000154): every FORECAST emitted after
        # P2 under-estimated BY CONSTRUCTION, in silence, because the routed agent had
        # no scale. Added here rather than trusted, since this enumeration is the only
        # thing that makes a missing row go red.
        for agent in ("modeler", "optimizer", "skills-resolver", "custom-docs-curator",
                      "plan-critic", "exec-critic"):
            self.assertIn(f"| {agent}", self.budgets, agent)

    def test_resolvers_name_the_oidc_401_and_pinned_fallback(self):
        # T-00000123: skills.sh masks its OIDC 401 as "No skills found", so an
        # empty probe must be read as an auth failure, not an absence. Every host
        # resolver pins the EXACT degraded string (em-dash is a literal U+2014).
        degraded = "COVERAGE DEGRADED — skills.sh OIDC-gated (401), pinned-GitHub fallback in use"
        self.assertIn(degraded, self.resolver_claude, ".claude resolver")
        self.assertIn(degraded, self.resolver_gemini, ".gemini resolver")
        self.assertIn(degraded, self.resolver_codex, ".codex resolver")
        self.assertIn(degraded, self.resolver_github, ".github resolver")

    def test_documentation_states_supported_hook_boundary_and_surface_commands(self):
        self.assertNotIn("unbypassable", self.readme.lower())
        self.assertNotIn("no agent ever starts cold", self.readme.lower())
        self.assertNotIn("before every compaction", self.readme.lower())
        self.assertNotIn("first, always", self.readme.lower())
        self.assertIn("not a complete enforcement boundary", self.codex_readme)
        self.assertIn("Desktop", self.codex_readme)
        self.assertIn("sandbox", self.codex_readme.lower())
        self.assertNotIn(", MCP, session", self.codex_readme)


if __name__ == "__main__":
    unittest.main()
