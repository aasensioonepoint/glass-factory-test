"""Golden-transcript drift evals for the orchestrator and planner agents.

ZERO LLM CALLS. This is deterministic contract-drift detection: it recomposes a
small set of behavioural invariants from the LIVE, source-of-truth agent
definitions of all five hosts and compares them to a frozen golden fixture.

Two things are asserted per agent:
  1. Fidelity  — every host's live definition still yields the golden invariants.
  2. Parity    — all five host formats agree on those invariants with each other.

If someone edits, say, the Claude planner and removes the approval-gate wording,
`owns_approval_gate` flips to False for that host, so both the fidelity check
(host != golden) and the parity check (hosts disagree) go red.

Host definition formats (behavioural invariants are keyword-level plain text;
Codex model comparisons parse the TOML model key):
  claude  -> .claude/agents/<agent>.md          (YAML front-matter + markdown)
  codex   -> .codex/agents/<agent>.toml         (TOML)
  gemini  -> .gemini/agents/<agent>.md          (YAML front-matter + markdown)
  copilot -> .github/agents/<agent>.agent.md    (YAML front-matter + markdown)
  kimi    -> .kimi-code/agents/<agent>.md       (YAML front-matter + markdown)

Style is intentionally aligned with .codex/test_pipeline_contract.py.
"""

import json
import re
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch


# .agents/evals/test_golden_transcripts.py -> repo root is parents[2]
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

HOSTS = ("claude", "codex", "gemini", "copilot", "kimi")

HOST_DEF_PATHS = {
    "claude": ROOT / ".claude" / "agents" / "{agent}.md",
    "codex": ROOT / ".codex" / "agents" / "{agent}.toml",
    "gemini": ROOT / ".gemini" / "agents" / "{agent}.md",
    "copilot": ROOT / ".github" / "agents" / "{agent}.agent.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "{agent}.md",
}


def _no_edit(low: str) -> bool:
    """Agent declares it does not mutate code (routes/plans only)."""
    return (
        "do not edit" in low
        or "never edits code" in low
        or "do not edit code" in low
        or "write code" in low  # "you do not read code, write code, or explore"
    )


def _owns_gate(low: str) -> bool:
    """Agent is the one that requests approval and awaits the user OK.

    Deliberately keyed on the *requesting* phrasing so that an orchestrator that
    merely lists a downstream '[HUMAN APPROVAL GATE]' step, or notes that
    'planner owns the approval gate', does NOT read as owning it itself.
    """
    return (
        "approval requested" in low
        or "an approval request" in low
        or "await user ok" in low
    )


def probe(text: str) -> dict:
    """Host-agnostic invariant probes over an agent definition's raw text."""
    low = text.lower()
    return {
        "emits_forecast": "forecast" in low,
        "read_only_no_edit": _no_edit(low),
        "owns_approval_gate": _owns_gate(low),
        "routes_language_detection": (
            "language-detect" in low or "language detection" in low
        ),
        "produces_steps": "steps" in low,
        "hands_to_dev": ("dev-mono" in low or "dev-multi" in low),
        # Additive probe keys (plan-critic, T-005 shard 3): projected only onto
        # goldens that list them, so orchestrator/planner goldens are unaffected.
        "declares_writes_nothing": ("writes nothing" in low or "write nothing" in low),
        "is_adversarial": "adversarial" in low,
    }


def read_host_def(host: str, agent: str) -> str:
    path = Path(str(HOST_DEF_PATHS[host]).format(agent=agent))
    if not path.exists():
        raise FileNotFoundError(f"missing {host} definition for {agent}: {path}")
    return path.read_text(encoding="utf-8")


def load_golden(agent: str) -> dict:
    return json.loads((FIXTURES / f"{agent}.golden.json").read_text(encoding="utf-8"))


def host_invariants(agent: str, golden: dict) -> dict:
    """{host: invariants} projected onto exactly the golden's invariant keys."""
    keys = golden["invariants"].keys()
    out = {}
    for host in HOSTS:
        full = probe(read_host_def(host, agent))
        out[host] = {k: full[k] for k in keys}
    return out


class GoldenContractMixin:
    agent = ""  # set by subclasses

    def setUp(self):
        self.golden = load_golden(self.agent)
        self.per_host = host_invariants(self.agent, self.golden)

    def test_every_host_matches_golden(self):
        for host, inv in self.per_host.items():
            self.assertEqual(
                inv,
                self.golden["invariants"],
                f"{host} {self.agent} drifted from golden: {inv} != {self.golden['invariants']}",
            )

    def test_multi_host_parity(self):
        reference = self.per_host["claude"]
        for host, inv in self.per_host.items():
            self.assertEqual(
                inv,
                reference,
                f"multi-host parity broken for {self.agent}: {host}={inv} vs claude={reference}",
            )

    def test_golden_lists_all_hosts(self):
        self.assertEqual(sorted(self.golden["hosts"]), sorted(HOSTS))


class OrchestratorGoldenTests(GoldenContractMixin, unittest.TestCase):
    agent = "orchestrator"

    def test_orchestrator_does_not_own_the_gate(self):
        for host, inv in self.per_host.items():
            self.assertFalse(inv["owns_approval_gate"], f"{host} orchestrator must not own the gate")


class PlannerGoldenTests(GoldenContractMixin, unittest.TestCase):
    agent = "planner"

    def test_planner_owns_the_gate_and_hands_to_dev(self):
        for host, inv in self.per_host.items():
            self.assertTrue(inv["owns_approval_gate"], f"{host} planner must own the gate")
            self.assertTrue(inv["hands_to_dev"], f"{host} planner must hand off to dev-*")

class PlanCriticGoldenTests(GoldenContractMixin, unittest.TestCase):
    agent = "plan-critic"

    def test_plan_critic_does_not_own_the_gate_or_hand_to_dev(self):
        for host, inv in self.per_host.items():
            self.assertFalse(inv["owns_approval_gate"], f"{host} plan-critic must not own the gate")
            self.assertFalse(inv["hands_to_dev"], f"{host} plan-critic must not hand off to dev-*")

    def test_plan_critic_declares_writes_nothing_and_is_adversarial(self):
        for host, inv in self.per_host.items():
            self.assertTrue(inv["declares_writes_nothing"], f"{host} plan-critic must declare it writes nothing")
            self.assertTrue(inv["is_adversarial"], f"{host} plan-critic must be adversarial")

class TierRelationTests(unittest.TestCase):
    """Rule 5: palier(plan-critic) >= palier(planner), per host and per axis.

    T-00000037 — asserting frozen tier literals broke on every pilot tuning
    (S-00000040). What the contract actually requires is the RELATION: a critic
    on a weaker tier than the plan's author is a rubber stamp by construction.
    The concrete values are the pilot's to tune; only the ordering is asserted.
    Extraction failures and unknown tier values fail loudly rather than skip.
    """

    # Ordered weakest -> strongest. Unknown values are a hard failure: a new
    # tier name must be ranked here before the contract can evaluate it.
    EFFORT_RANK = {"minimal": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4, "max": 5}
    CLAUDE_MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
    # Gemini model ids carry the tier as a suffix (…-flash-lite / …-flash / …-pro).
    GEMINI_MODEL_RANK = (("flash-lite", 0), ("flash", 1), ("pro", 2))
    # T-00000553: pilot-approved relation-test policy. These ranks are local to
    # the tests; apply-mode continues to manage only Codex effort.
    CODEX_MODEL_RANK = {
        "gpt-6-luna": 0,
        "gpt-5.6-terra": 1,
        "gpt-6-sol": 2,
        "gpt-6-astra": 3,
    }

    # (host, axis) pairs that express a tier. Copilot carries none by design.
    EFFORT_HOSTS = ("claude", "codex")
    MODEL_HOSTS = ("claude", "gemini", "codex")

    def _effort(self, host: str, agent: str) -> str:
        text = read_host_def(host, agent)
        pattern = (r'^model_reasoning_effort\s*=\s*"(\S+)"' if host == "codex"
                   else r"^effort:\s*(\S+)")
        m = re.search(pattern, text, re.MULTILINE)
        self.assertIsNotNone(m, f"{host} {agent}: no reasoning-tier field found")
        return m.group(1)

    def _model(self, host: str, agent: str) -> str:
        text = read_host_def(host, agent)
        if host == "codex":
            model = tomllib.loads(text).get("model")
            self.assertIsInstance(model, str, f"{host} {agent}: no string model field found")
            return model
        m = re.search(r"^model:\s*(\S+)", text, re.MULTILINE)
        self.assertIsNotNone(m, f"{host} {agent}: no model field found")
        return m.group(1)

    def _effort_rank(self, host: str, agent: str, value: str) -> int:
        self.assertIn(value, self.EFFORT_RANK,
                      f"{host} {agent}: unknown effort tier {value!r} — rank it in EFFORT_RANK")
        return self.EFFORT_RANK[value]

    def _model_rank(self, host: str, agent: str, value: str) -> int:
        if host == "claude":
            # A Claude model field is EITHER a bare tier (`fable`) OR a full model
            # id carrying the tier as one of its dash-separated tokens
            # (`claude-opus-4-8`). Both forms are live in this repo, and the map
            # only ever held the bare one — a gap invisible while this helper was
            # used on `planner`/`plan-critic` alone, both bare, and surfaced the
            # moment T-00000349 pointed it at the dev agents.
            #
            # MATCHED ON A TOKEN, NEVER ON A SUBSTRING (L-00000143: a substring
            # guard is wrong in both directions). Splitting on `-` makes `opus` in
            # `claude-opus-4-8` a match and would NOT match a hypothetical
            # `opusculum`; a bare `in value` test would match both.
            tokens = set(re.split(r"[-_.]", value))
            hits = [rank for name, rank in self.CLAUDE_MODEL_RANK.items() if name in tokens]
            self.assertEqual(
                len(hits), 1,
                f"claude {agent}: model {value!r} resolves to {len(hits)} known tiers — "
                "rank it in CLAUDE_MODEL_RANK (exactly one tier token is expected)",
            )
            return hits[0]
        if host == "codex":
            self.assertIn(
                value, self.CODEX_MODEL_RANK,
                f"{host} {agent}: unknown model id {value!r} — rank it in CODEX_MODEL_RANK",
            )
            return self.CODEX_MODEL_RANK[value]
        for suffix, rank in self.GEMINI_MODEL_RANK:
            if value.endswith(suffix):
                return rank
        self.fail(f"{host} {agent}: unrankable model id {value!r} — extend GEMINI_MODEL_RANK")

    def test_critic_effort_at_least_planner_effort(self):
        for host in self.EFFORT_HOSTS:
            planner, critic = self._effort(host, "planner"), self._effort(host, "plan-critic")
            self.assertGreaterEqual(
                self._effort_rank(host, "plan-critic", critic),
                self._effort_rank(host, "planner", planner),
                f"{host}: plan-critic effort {critic!r} is below planner effort {planner!r} "
                "— a critic weaker than the plan's author is a rubber stamp",
            )

    def test_critic_model_at_least_planner_model(self):
        for host in self.MODEL_HOSTS:
            planner, critic = self._model(host, "planner"), self._model(host, "plan-critic")
            self.assertGreaterEqual(
                self._model_rank(host, "plan-critic", critic),
                self._model_rank(host, "planner", planner),
                f"{host}: plan-critic model {critic!r} is below planner model {planner!r} "
                "— a critic weaker than the plan's author is a rubber stamp",
            )

    # -- S-00003871 : LE CRITIQUE UNIQUE, ET CE QUI LE TIENT ------------------
    #
    # T-00000624 avait réécrit la règle en « AU MOINS UN des deux critiques de
    # plan domine le planner sur chaque axe » — la PAIRE — et couvert les DEUX
    # planners (scénario du binôme de clôture : monter `planner-sonnet` en
    # `opus`/`max` faisait perdre l'effort à Critique A et le modèle à
    # Critique B, et les deux tests ci-dessus restaient verts).
    #
    # La décision pilote du 2026-10-03 (S-00003871) ne garde qu'UN critique de
    # plan, `plan-critic`. La règle redevient NOMINATIVE : c'est `plan-critic`
    # qui doit dominer CHACUN des deux planners. Son repli
    # `plan-critic-sonnet-max` n'est plus un candidat — sur `claude` et `codex`
    # il est SOUS `planner` sur l'axe modèle, et le compter rendrait vert un
    # critique de plan qui ne domine pas. Le mutant « retour à la paire »
    # (`plan-critic` affaibli, le repli dominant encore) est rejoué plus bas,
    # dans `test_negative_control_the_fallback_no_longer_holds_the_rule`.
    #
    # S-01M57F0BHB (2026-10-18, vitesse, jamais coût) : `plan-critic` en `high`,
    # `planner` en `medium` sur claude et codex. La relation ne balaie plus que
    # le planner ACTIF : `planner-sonnet` (hors chaîne depuis S-01M4TZZ13Y, jamais
    # invoqué) reste en `xhigh`, au-dessus du critique. CAPACITÉ PERDUE, NOMMÉE :
    # rebrancher `planner-sonnet` exige de remonter `plan-critic` d'abord. La
    # non-vacuité ci-dessous exige encore les quatre défs sur disque.
    PLAN_CRITIC = "plan-critic"
    PLAN_FALLBACK = "plan-critic-sonnet-max"
    PLAN_PLANNERS = ("planner", "planner-sonnet")
    PLAN_ACTIVE_PLANNERS = ("planner",)

    def _outranks(self, host: str, critique: str, planner: str) -> bool:
        """THE RULE, as a function, so the negative control replays THIS rule on
        the fallback rather than a re-derivation of it (L-00000057)."""
        if host in self.EFFORT_HOSTS:
            c_eff = self._effort_rank(host, critique, self._effort(host, critique))
            p_eff = self._effort_rank(host, planner, self._effort(host, planner))
            if c_eff < p_eff:
                return False
        c_mod = self._model_rank(host, critique, self._model(host, critique))
        p_mod = self._model_rank(host, planner, self._model(host, planner))
        return c_mod >= p_mod

    def test_plan_critic_outranks_the_active_planner_on_every_axis(self):
        for host in self.MODEL_HOSTS:
            for planner in self.PLAN_ACTIVE_PLANNERS:
                self.assertTrue(
                    self._outranks(host, self.PLAN_CRITIC, planner),
                    f"{host}: {self.PLAN_CRITIC} does not outrank {planner} on every "
                    f"axis — the ONLY plan critic (S-00003871) below a plan's author "
                    f"is a rubber stamp by construction, whatever its fallback "
                    f"{self.PLAN_FALLBACK} carries. Raising a planner without raising "
                    f"{self.PLAN_CRITIC} is the exact scenario this test exists for.",
                )

    def test_the_rule_sweeps_both_planners_the_critic_and_its_fallback(self):
        """NON-VACUITÉ (L-00000232) : une règle qui balaie une population VIDE ne
        signale jamais rien. Les quatre noms doivent EXISTER comme defs — le
        repli aussi, puisque le contrôle négatif le rejoue —, sinon le test
        ci-dessus est vert parce qu'il n'a rien regardé."""
        for host in self.MODEL_HOSTS:
            for nom in (self.PLAN_CRITIC, self.PLAN_FALLBACK) + self.PLAN_PLANNERS:
                self.assertTrue(
                    self._model(host, nom),
                    f"{host}: def {nom!r} absente ou sans clé `model:` — la règle "
                    f"« plan-critic domine chaque planner » balaierait une population "
                    f"incomplète, donc en vert sans rien prouver",
                )

    # -- S-01M57F0BHB : DOMINATION STRICTE PAR L'EFFORT (C2) -------------------
    # `_outranks` admet l'égalité ; à modèle égal, un critique au même effort que
    # le planner actif ne le domine plus. Sur les deux hôtes à effort : effort
    # STRICTEMENT au-dessus, modèle au moins égal.
    def _strictly_outranks_active_planner(self, host: str) -> None:
        for planner in self.PLAN_ACTIVE_PLANNERS:
            c_eff = self._effort_rank(host, self.PLAN_CRITIC, self._effort(host, self.PLAN_CRITIC))
            p_eff = self._effort_rank(host, planner, self._effort(host, planner))
            self.assertGreater(
                c_eff, p_eff,
                f"{host}: {self.PLAN_CRITIC} effort is not strictly above {planner} effort "
                "— at an equal model the only plan critic no longer outranks the plan's author",
            )
            self.assertGreaterEqual(
                self._model_rank(host, self.PLAN_CRITIC, self._model(host, self.PLAN_CRITIC)),
                self._model_rank(host, planner, self._model(host, planner)),
                f"{host}: {self.PLAN_CRITIC} model is below {planner} model",
            )

    def test_critic_strictement_superieur_au_planner_actif(self):
        for host in self.EFFORT_HOSTS:
            self._strictly_outranks_active_planner(host)
        # MUTANT EN MÉMOIRE, dérivé du disque : le planner relevé à l'effort du
        # critique (planner=high face à critic=high aujourd'hui) doit rougir.
        reader = read_host_def
        for host in self.EFFORT_HOSTS:
            critic_effort = self._effort(host, self.PLAN_CRITIC)
            pattern, line = {
                "claude": (r"^effort:.*$", f"effort: {critic_effort}"),
                "codex": (r"^model_reasoning_effort\s*=.*$", f'model_reasoning_effort = "{critic_effort}"'),
            }[host]

            def raised(h: str, r: str, host: str = host, pattern: str = pattern, line: str = line) -> str:
                text = reader(h, r)
                if (h, r) == (host, "planner"):
                    text, n = re.subn(pattern, line, text, count=1, flags=re.MULTILINE)
                    self.assertEqual(n, 1, f"{host} planner: witness did not apply")
                return text

            with self.subTest(host=host, planner=critic_effort), \
                    patch(f"{__name__}.read_host_def", side_effect=raised):
                with self.assertRaisesRegex(AssertionError, rf"{host}: plan-critic effort is not strictly above"):
                    self._strictly_outranks_active_planner(host)

    # -- S-01M57FKBYM : ADVISOR SUR DEMANDE EXPLICITE DU PILOTE -----------------
    # Dix rappels (planner et plan-critic sur les cinq hôtes) et la règle
    # universelle d'AGENTS.md : une ligne qui nomme `advisor` puis, à 400
    # caractères au plus, la décision S-01M57FKBYM.
    ADVISOR_ROLES = ("planner", "plan-critic")
    _ADVISOR_RAPPEL = re.compile(r"\badvisor only when the pilot explicitly requests it\b", re.I)
    _ADVISOR_ROUTEUR = re.compile(r"advisor.{0,400}?S-01M57FKBYM", re.I)

    @classmethod
    def _rappel_advisor(cls, text: str) -> bool:
        return cls._ADVISOR_RAPPEL.search(" ".join(text.split())) is not None

    @classmethod
    def _regle_advisor(cls, text: str) -> bool:
        return cls._ADVISOR_ROUTEUR.search(text) is not None

    def test_advisor_sur_demande_pilote(self):
        seen = 0
        for host in HOSTS:
            for role in self.ADVISOR_ROLES:
                text = read_host_def(host, role)
                with self.subTest(host=host, role=role):
                    self.assertTrue(self._rappel_advisor(text),
                                    f"{host} {role}: advisor reminder absent (S-01M57FKBYM)")
                    # MUTANT : le rappel retiré de CETTE déf rougit.
                    flat = " ".join(text.split())
                    removed = self._ADVISOR_RAPPEL.sub("", flat)
                    self.assertNotEqual(removed, flat, f"{host} {role}: empty mutant")
                    self.assertFalse(self._rappel_advisor(removed),
                                     f"{host} {role}: the predicate does not bite on the mutant")
                seen += 1
        self.assertEqual(seen, 10, "the reminder population is not the declared one")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(self._regle_advisor(agents),
                        "AGENTS.md: universal advisor rule citing S-01M57FKBYM absent")
        # MUTANT : la règle universelle retirée (chaque ligne qui la porte) rougit.
        stripped = "\n".join(l for l in agents.splitlines() if not self._regle_advisor(l))
        self.assertNotEqual(stripped, agents)
        self.assertFalse(self._regle_advisor(stripped), "AGENTS.md: the advisor rule survives its removal")


    # ------------------------------------------------------------------
    # T-00000349 — the SAME relation, for the OTHER critic.
    # ------------------------------------------------------------------
    # `plan-critic >= planner` was pinned; nothing equivalent existed for
    # `exec-critic` versus the DEV agent it verifies — and the Copilot def of
    # exec-critic calls that exact situation "a rubber stamp by construction".
    # A critic weaker than what it audits is one whether the object is a plan on
    # paper or a delivered diff.
    #
    # ARBITRATED BY MEASUREMENT rather than by preference: the relation already
    # HOLDS on every host and every axis today —
    #   claude  exec-critic claude-opus-5-5/xhigh vs dev claude-opus-5-5/medium
    #           (deux crans d'effort au-dessus depuis S-01M5F3KT36B9S58WNC6T92E0BM,
    #            égalité de modèle. Les modèles sont ÉPINGLÉS hors échelle —
    #            MODEL_MODES.md § 3.4.)
    #   gemini  exec-critic 3.1-pro        vs dev-mono 3.5-flash, dev-multi 3.1-pro (modèle seul, T-00000779)
    #   codex   exec-critic Astra/xhigh   vs dev-mono Sol/high, dev-multi Sol/high
    # so pinning it costs nothing today and is exactly what stops a future tuning
    # from lowering it silently. Equality is allowed; only "below" is refused.
    # design-review ≥ frontend-fidelity : par axe, voir UI_PAIR_HOSTS.
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-18, décision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG) :
    # `terraform-deployer` est le slot dev d'une tâche IaC, exec-critic juge son diff — mesuré :
    #   claude opus-5-5/xhigh (égalité), gemini 3.1-pro (égalité), codex Sol/xhigh (sous Astra).
    DEV_AGENTS = ("dev-mono", "dev-multi", "terraform-deployer")

    @staticmethod
    def _is_dominated(mine: tuple[int, int], theirs: tuple[int, int]) -> bool:
        """True when `theirs` is at or above `mine` on BOTH axes and strictly above
        on at least one — the only shape this contract refuses. `(effort, model)`."""
        return (
            theirs[0] >= mine[0]
            and theirs[1] >= mine[1]
            and (theirs[0] > mine[0] or theirs[1] > mine[1])
        )

    def test_the_dominance_relation_bites(self):
        """WITNESS for the arm below. A relation nobody has seen refuse anything
        describes instead of measuring (L-00000343), and `_is_dominated` is pure,
        so its five interesting cases are checkable without any tree at all."""
        dominated = self._is_dominated
        self.assertTrue(dominated((3, 2), (4, 2)),
                        "same model, one effort notch above — that IS domination")
        self.assertTrue(dominated((3, 2), (4, 3)),
                        "above on both axes — that IS domination")
        self.assertFalse(dominated((3, 3), (4, 2)),
                         "stronger model against stronger effort is a TRADE, not domination")
        self.assertFalse(dominated((4, 3), (4, 3)), "equality is not domination")
        self.assertFalse(dominated((5, 3), (4, 2)),
                         "strictly stronger on both axes is not domination")

    def test_exec_critic_is_never_dominated_by_a_dev_agent(self):
        """DOMINANCE, not axis by axis. The rule is that the critic is never WEAKER,
        and across two axes "weaker" means DOMINATED: at or below everywhere, and
        strictly below somewhere. A pairing that is stronger on one axis and weaker
        on the other is INCOMPARABLE, and this contract admits it rather than
        inventing an exchange rate between a model generation and an effort notch —
        MODEL_MODES.md §3.3 ranks each axis and ranks NO pair, and guessing a rate
        would be the same invention apply-mode.py refuses on a pinned model.

        WHY THIS SHAPE — measured 2026-09-05 (T-00000471). Two independent per-axis
        assertions stood here. Their CONJUNCTION forbade every trade, which is
        stricter than the sentence they claimed to enforce, and the message said
        "weaker" while the check read a single axis. `exec-critic` at `fable/high`
        against a dev agent at `opus/xhigh` was therefore reported as weaker when it
        was one model GENERATION above and one effort notch below. A message that
        asserts more than its check measures makes the reader conclude wrongly
        (L-00000111), and in this repo it did.

        THE MODEL FLOOR BELOW STAYS ABSOLUTE, and that is what keeps this honest:
        with `exec-critic` model >= every dev model already enforced, domination can
        only occur at EQUAL model — so the effort floor still bites wherever the
        critic has no model advantage to spend. The trade is allowed only when the
        stronger model is real.

        `plan-critic` vs `planner` KEEPS the stricter per-axis pair: no trade was
        asked for there, and a guard that holds at the stricter level is not
        loosened for symmetry alone.

        Codex has two ranked axes under the explicit test policy above, even
        though apply-mode only changes its effort. A host with ONE ranked axis
        is judged on that axis alone — there is nothing to trade against.
        """
        seen = 0
        for host in self.MODEL_HOSTS:
            if host not in self.EFFORT_HOSTS:
                cm = self._model_rank(host, "exec-critic", self._model(host, "exec-critic"))
                for dev in self.DEV_AGENTS:
                    self.assertGreaterEqual(cm, self._model_rank(host, dev, self._model(host, dev)),
                                            f"{host}: exec-critic model is below {dev} on the ONLY axis")
                    seen += 1
                continue
            critic_effort = self._effort_rank(
                host, "exec-critic", self._effort(host, "exec-critic"))
            two_axes = host in self.MODEL_HOSTS
            for dev in self.DEV_AGENTS:
                dev_effort = self._effort_rank(host, dev, self._effort(host, dev))
                if not two_axes:
                    self.assertGreaterEqual(
                        critic_effort, dev_effort,
                        f"{host}: exec-critic effort is below {dev} on the ONLY axis "
                        "this host carries — there is no second axis to trade against, "
                        "so this is a critic plainly weaker than what it audits",
                    )
                    seen += 1
                    continue
                critic_model = self._model_rank(
                    host, "exec-critic", self._model(host, "exec-critic"))
                dev_model = self._model_rank(host, dev, self._model(host, dev))
                self.assertFalse(
                    self._is_dominated((critic_effort, critic_model),
                                       (dev_effort, dev_model)),
                    f"{host}: {dev} is at or above exec-critic on BOTH axes and above "
                    "on one — the critic is DOMINATED by what it audits, which is a "
                    "rubber stamp. Raise the critic on either axis; a trade (stronger "
                    "model for lower effort) is admitted, being beaten on both is not",
                )
                seen += 1
        # NON-VACUITY (L-00000232): a loop over an emptied host or agent tuple
        # passes without comparing anything. 3 hosts x 3 dev agents
        # (T-01M52X1W3WPKCWX1DC36NMKJB6, 2026-10-18 : 6 -> 9, + terraform-deployer).
        self.assertEqual(seen, 9, "the comparison population is not the declared one")

    def test_exec_critic_model_is_at_or_above_every_dev_agent(self):
        seen = 0
        for host in self.MODEL_HOSTS:
            critic = self._model(host, "exec-critic")
            for dev in self.DEV_AGENTS:
                theirs = self._model(host, dev)
                self.assertGreaterEqual(
                    self._model_rank(host, "exec-critic", critic),
                    self._model_rank(host, dev, theirs),
                    f"{host}: exec-critic model {critic!r} is below {dev} model {theirs!r}",
                )
                seen += 1
        # 3 hosts x 3 dev agents (T-01M52X1W3WPKCWX1DC36NMKJB6, 2026-10-18 : 6 -> 9, + terraform-deployer).
        self.assertEqual(seen, 9, "the comparison population is not the declared one")

    def test_codex_design_review_model_at_least_frontend_fidelity_model(self) -> None:
        critic = self._model("codex", "design-review")
        author = self._model("codex", "frontend-fidelity")
        self.assertGreaterEqual(
            self._model_rank("codex", "design-review", critic),
            self._model_rank("codex", "frontend-fidelity", author),
            f"codex: design-review model {critic!r} is below frontend-fidelity model {author!r}",
        )

    # S-01M558S8VVRGHACABYMWB2C6EM — design-review juge frontend-fidelity comme
    # exec-critic juge dev-* : le juge n'est jamais SOUS l'auteur. PAR AXE (la
    # relation stricte de plan-critic/planner : aucun échange n'est demandé), sur
    # les deux hôtes qui portent les deux axes. Gemini : modèle seul, égalité.
    UI_PAIR_HOSTS = ("claude", "codex")

    def _ui_pair_check(self, host: str, axes: tuple = ("effort", "model")) -> int:
        seen = 0
        for axis, read, rank in (("effort", self._effort, self._effort_rank),
                                 ("model", self._model, self._model_rank)):
            if axis not in axes:
                continue
            judge, author = read(host, "design-review"), read(host, "frontend-fidelity")
            self.assertGreaterEqual(
                rank(host, "design-review", judge), rank(host, "frontend-fidelity", author),
                f"{host}: design-review {axis} {judge!r} is below frontend-fidelity "
                f"{axis} {author!r} — the judge is weaker than the author it audits",
            )
            seen += 1
        return seen

    def test_design_review_at_or_above_frontend_fidelity_on_every_axis(self) -> None:
        seen = sum(self._ui_pair_check(host) for host in self.UI_PAIR_HOSTS)
        self.assertEqual(seen, 4, "the comparison population is not the declared one")

    def _ui_pair_patch(self, host: str, role: str, field: str, value: str):
        reader = read_host_def
        pattern, line = {
            ("codex", "effort"): (r"^model_reasoning_effort\s*=.*$", f'model_reasoning_effort = "{value}"'),
            ("codex", "model"): (r"^model\s*=.*$", f'model = "{value}"'),
            ("claude", "effort"): (r"^effort:.*$", f"effort: {value}"),
            ("claude", "model"): (r"^model:.*$", f"model: {value}"),
        }[(host, field)]

        def mutated(h: str, r: str) -> str:
            text = reader(h, r)
            if (h, r) == (host, role):
                text, n = re.subn(pattern, line, text, count=1, flags=re.MULTILINE)
                self.assertEqual(n, 1, f"{host} {role}: {field} witness did not apply")
            return text
        return patch(f"{__name__}.read_host_def", side_effect=mutated)

    def test_design_review_dominated_by_frontend_fidelity_is_refused(self) -> None:
        """WITNESS (L-00000343) — efforts DÉRIVÉS du disque, jamais codés en dur :
        le juge un cran sous l'auteur, l'auteur un cran au-dessus du juge (le geste
        de l'adoptant), rougissent ; l'égalité passe ; un modèle Claude ou Codex inférieur rougit."""
        order = sorted(self.EFFORT_RANK, key=self.EFFORT_RANK.get)
        refused = r"design-review (effort|model) .* is below frontend-fidelity"
        lowered = 0
        for host in self.UI_PAIR_HOSTS:
            def check(host: str = host) -> int:  # hermétique : CET hôte seul
                return self._ui_pair_check(host, ("effort",))
            judge = self.EFFORT_RANK[self._effort(host, "design-review")]
            author = self.EFFORT_RANK[self._effort(host, "frontend-fidelity")]
            self.assertGreater(author, 0, f"{host}: frontend-fidelity at the bottom, no notch below")
            legs = [("design-review", order[author - 1])]
            if judge + 1 < len(order):
                legs.append(("frontend-fidelity", order[judge + 1]))
            for role, value in legs:
                with self.subTest(host=host, role=role, effort=value), \
                        self._ui_pair_patch(host, role, "effort", value):
                    with self.assertRaisesRegex(AssertionError, refused):
                        check()
                lowered += role == "design-review"
            with self.subTest(host=host, equality=order[judge]), \
                    self._ui_pair_patch(host, "frontend-fidelity", "effort", order[judge]):
                check()
        # Axe modèle Claude : un cran sous l'auteur, DÉRIVÉ du disque (C15) —
        # jamais un littéral, qu'un réglage de l'auteur rendrait muet.
        claude_order = sorted(self.CLAUDE_MODEL_RANK, key=self.CLAUDE_MODEL_RANK.get)
        author_claude = self._model_rank("claude", "frontend-fidelity", self._model("claude", "frontend-fidelity"))
        self.assertGreater(author_claude, 0, "claude: frontend-fidelity model at the bottom, no notch below")
        with self._ui_pair_patch("claude", "design-review", "model", claude_order[author_claude - 1]):
            with self.assertRaisesRegex(AssertionError, r"claude: design-review model"):
                self._ui_pair_check("claude", ("model",))
        # Axe modèle Codex : un cran sous l'auteur, DÉRIVÉ du disque (r4).
        codex_order = sorted(self.CODEX_MODEL_RANK, key=self.CODEX_MODEL_RANK.get)
        author_model = self._model_rank("codex", "frontend-fidelity", self._model("codex", "frontend-fidelity"))
        self.assertGreater(author_model, 0, "codex: frontend-fidelity model at the bottom, no notch below")
        with self._ui_pair_patch("codex", "design-review", "model", codex_order[author_model - 1]):
            with self.assertRaisesRegex(AssertionError, r"codex: design-review model"):
                self._ui_pair_check("codex", ("model",))
        self.assertEqual(lowered, 2, "the witness population is not the declared one")

    def _assert_codex_model_refused(
        self, comparison: str, agent: str, model: str, reason: str,
        effort_from: str | None = None,
    ) -> None:
        """Mutate the input to the consuming test; leave MODEL_HOSTS intact."""
        reader = read_host_def
        effort = self._effort("codex", effort_from) if effort_from else None

        def mutated_def(host: str, role: str) -> str:
            text = reader(host, role)
            if host == "codex" and role == agent:
                # Single quotes and a trailing comment also exercise TOML parsing.
                text, count = re.subn(
                    r"^model\s*=.*$", f"model = '{model}' # refusal witness",
                    text, count=1, flags=re.MULTILINE,
                )
                self.assertEqual(count, 1, f"codex {role}: witness did not replace a model")
                if effort is not None:
                    text, count = re.subn(
                        r'^model_reasoning_effort\s*=\s*"[^"\n]+"',
                        f'model_reasoning_effort = "{effort}"', text, count=1,
                        flags=re.MULTILINE,
                    )
                    self.assertEqual(count, 1, f"codex {role}: witness did not align the effort")
            return text

        with patch(f"{__name__}.read_host_def", side_effect=mutated_def) as patched_reader:
            with self.assertRaisesRegex(AssertionError, reason):
                getattr(self, comparison)()
            patched_reader.assert_any_call("codex", agent)

    def test_codex_unknown_models_are_refused_by_consuming_comparisons(self) -> None:
        comparisons = (
            ("test_critic_model_at_least_planner_model", ("planner", "plan-critic")),
            # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-18) : + terraform-deployer, nouveau membre de DEV_AGENTS.
            ("test_exec_critic_model_is_at_or_above_every_dev_agent",
             ("exec-critic", "dev-mono", "dev-multi", "terraform-deployer")),
            ("test_exec_critic_is_never_dominated_by_a_dev_agent",
             ("exec-critic", "dev-mono", "dev-multi", "terraform-deployer")),
            ("test_codex_design_review_model_at_least_frontend_fidelity_model",
             ("design-review", "frontend-fidelity")),
        )
        for comparison, agents in comparisons:
            for agent in agents:
                # Refuse both a known-id prefix and a Gemini-like suffix.
                for model in ("gpt-6-astra-unknown", "gpt-unranked-pro"):
                    with self.subTest(comparison=comparison, agent=agent, model=model):
                        self._assert_codex_model_refused(
                            comparison, agent, model,
                            re.escape(f"codex {agent}: unknown model id {model!r}"),
                        )

    def test_codex_weakened_critics_are_refused_by_consuming_comparisons(self) -> None:
        cases = (
            ("test_critic_model_at_least_planner_model", "plan-critic", "gpt-6-sol",
             r"codex: plan-critic model .* is below planner model"),
            ("test_exec_critic_model_is_at_or_above_every_dev_agent",
             "exec-critic", "gpt-5.6-terra",
             r"codex: exec-critic model .* is below dev-mono model"),
            ("test_exec_critic_is_never_dominated_by_a_dev_agent",
             "exec-critic", "gpt-5.6-terra", r"codex: .*DOMINATED", "dev-mono"),
            ("test_codex_design_review_model_at_least_frontend_fidelity_model",
             "design-review", "gpt-5.6-terra",
             r"codex: design-review model .* is below frontend-fidelity model"),
        )
        for comparison, agent, model, reason, *effort_from in cases:
            with self.subTest(comparison=comparison):
                self._assert_codex_model_refused(comparison, agent, model, reason, *effort_from)

    def test_codex_stronger_model_can_trade_effort(self) -> None:
        reader = read_host_def

        def lower_critic_effort(host: str, agent: str) -> str:
            text = reader(host, agent)
            # HERMÉTIQUE (C8) : le troc est épinglé dans le patch, modèle ET effort
            # des deux côtés — un défaut des devs changé ne le rend plus muet.
            pinned = {"exec-critic": ("gpt-6-astra", "medium"),
                      "dev-mono": ("gpt-6-sol", "high"), "dev-multi": ("gpt-6-sol", "high")}
            if host == "codex" and agent in pinned:
                model, effort = pinned[agent]
                text, n1 = re.subn(r"^model\s*=.*$", f'model = "{model}"', text, count=1, flags=re.MULTILINE)
                text, n2 = re.subn(
                    r'^model_reasoning_effort\s*=\s*"[^"\n]+"',
                    f'model_reasoning_effort = "{effort}"', text, count=1, flags=re.MULTILINE,
                )
                self.assertEqual((n1, n2), (1, 1), f"codex {agent}: trade witness did not apply")
            return text

        with patch(f"{__name__}.read_host_def", side_effect=lower_critic_effort):
            self.test_exec_critic_is_never_dominated_by_a_dev_agent()
            self.test_exec_critic_model_is_at_or_above_every_dev_agent()


    def _gemini_models(self, roles, model):
        reader = read_host_def

        def mutated(host, role):
            text = reader(host, role)
            if host == "gemini" and role in roles:
                text, n = re.subn(r"^model:.*$", f"model: {model}", text, count=1, flags=re.M)
                self.assertEqual(n, 1)
            return text
        return patch(f"{__name__}.read_host_def", side_effect=mutated)

    def test_gemini_weakened_critics_are_refused(self) -> None:
        cases = (
            # S-00003871 : seul `plan-critic` est affaibli — son repli reste
            # intact, et la règle doit rougir quand même (mutant « retour à la
            # paire », mesuré en deux moitiés par le contrôle négatif ci-dessous).
            ("test_plan_critic_outranks_the_active_planner_on_every_axis",
             ("plan-critic",), r"gemini: plan-critic does not outrank planner"),
            ("test_critic_model_at_least_planner_model", ("plan-critic",),
             r"gemini: plan-critic model .* is below planner model"),
            ("test_exec_critic_is_never_dominated_by_a_dev_agent", ("exec-critic",),
             r"gemini: exec-critic model is below dev-multi"),
        )
        for comparison, roles, reason in cases:
            with self.subTest(comparison=comparison), self._gemini_models(roles, "gemini-3.5-flash"):
                with self.assertRaisesRegex(AssertionError, reason):
                    getattr(self, comparison)()

    def test_negative_control_the_fallback_no_longer_holds_the_rule(self) -> None:
        """S-00003871 — mutant « retour à la paire » : `plan-critic` affaibli sur
        gemini, son repli intact. L'ANCIENNE règle (« au moins un des deux
        critiques domine ») restait verte sur ce cas, le repli dominant encore ;
        la règle du critique unique doit rougir. Les DEUX moitiés sont mesurées,
        sinon ce contrôle ne prouve pas qu'il distingue les deux règles."""
        with self._gemini_models(("plan-critic",), "gemini-3.5-flash"):
            # (a) Le repli domine encore chaque planner : la règle de PAIRE
            # aurait été verte sur ce mutant.
            self.assertTrue(
                all(self._outranks("gemini", self.PLAN_FALLBACK, p) for p in self.PLAN_PLANNERS),
                "mutant mal formé : le repli ne domine plus, le contrôle ne distingue "
                "pas la règle de paire de la règle du critique unique",
            )
            # (b) La règle du critique unique, rejouée telle quelle, rougit.
            with self.assertRaisesRegex(AssertionError, r"gemini: plan-critic does not outrank planner"):
                self.test_plan_critic_outranks_the_active_planner_on_every_axis()


class OrchestratorPlannerGateSplitTests(unittest.TestCase):
    """Cross-agent contract: exactly the planner owns the approval gate."""

    def test_gate_ownership_is_planner_only(self):
        for host in HOSTS:
            orch = probe(read_host_def(host, "orchestrator"))["owns_approval_gate"]
            plan = probe(read_host_def(host, "planner"))["owns_approval_gate"]
            self.assertFalse(orch, f"{host}: orchestrator unexpectedly owns the gate")
            self.assertTrue(plan, f"{host}: planner should own the gate")


if __name__ == "__main__":
    unittest.main()
