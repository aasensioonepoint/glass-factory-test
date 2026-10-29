import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_gate
import protect_paths
import safe_bash
import _common

_EVENTS_SANDBOX = None
_EVENTS_DIR_BEFORE = None


def setUpModule():
    """Redirect canal-A writes away from the REAL .agents/state/events/.

    These tests call each hook's main() IN-PROCESS against this checkout, and
    since T-00000027 a denial also appends one canal-A event. Without this
    redirect every run of the suite injects real-looking hook.deny lines into
    the audit trail the dashboard reads — measured: ~50 fake denials per run.
    events.py resolves AGENTS_EVENTS_DIR at each call, so setting it here is
    enough; ignore_cleanup_errors per L-00000035.
    """
    global _EVENTS_SANDBOX, _EVENTS_DIR_BEFORE
    _EVENTS_DIR_BEFORE = os.environ.get("AGENTS_EVENTS_DIR")
    _EVENTS_SANDBOX = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    os.environ["AGENTS_EVENTS_DIR"] = _EVENTS_SANDBOX.name


def tearDownModule():
    if _EVENTS_DIR_BEFORE is None:
        os.environ.pop("AGENTS_EVENTS_DIR", None)
    else:
        os.environ["AGENTS_EVENTS_DIR"] = _EVENTS_DIR_BEFORE
    _EVENTS_SANDBOX.cleanup()


def invoke(module, payload):
    output = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output):
        module.main()
    return json.loads(output.getvalue()) if output.getvalue().strip() else None


class GuardHookTests(unittest.TestCase):
    def test_protect_paths_reads_canonical_apply_patch_command(self):
        body = invoke(
            protect_paths,
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: src/legacy/demo.py\n*** End Patch"
                },
            },
        )
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_protect_paths_normalizes_parent_segments(self):
        body = invoke(
            protect_paths,
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "file_path": "docs/../src/legacy/demo.py"
                },
            },
        )
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_protect_paths_denies_mcp_json(self):
        for file_path in (".mcp.json", ".vscode/mcp.json"):
            body = invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
            )
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn(
                "MCP configuration is human-audited",
                body["hookSpecificOutput"]["permissionDecisionReason"],
            )

    def test_protect_paths_denies_host_mcp_settings(self):
        for file_path in (".codex/config.toml", ".gemini/settings.json"):
            body = invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
            )
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_protect_paths_denies_the_FOUR_arming_markers(self):
        """T-00000604 — LA GARDE MORDAIT LE PLUS FORT LÀ OÙ ELLE ÉTAIT LA PLUS
        FACILE À RETIRER.

        QUATRE marqueurs d'armement sont éprouvés ici : `BINOME_REQUIRED`,
        `AFFIRMATION_REQUIRED`, `KICKOFF_REQUIRED` et — depuis T-00000654 —
        `PLAN_CIBLE_REQUIRED` (le nom disait THREE avant l'ajout du quatrième).

        `BINOME_REQUIRED` arme le refus de clore sans revue critique et
        `AFFIRMATION_REQUIRED` celui de finir un tour qui a écrit une
        affirmation durable ; les deux n'étaient protégés QUE sur Claude Code.
        Mesure qui a ouvert la tâche : `git grep BINOME_REQUIRED` ne rendait
        RIEN dans `.codex/`, `.gemini/`, `.kimi-code/` ni `.github/`. L'agent que
        la garde contraint pouvait donc la désarmer d'un seul `apply_patch`.

        LES TROIS CASSES SONT ÉPROUVÉES, pas seulement l'orthographe canonique :
        sur NTFS — la plateforme de développement déclarée du kit — `\\` et `/`,
        majuscules et minuscules ouvrent UN SEUL ET MÊME fichier, donc une garde
        qui n'en reconnaîtrait qu'une serait franchissable par l'AUTRE CASSE."""
        cas = (
            (".agents/state/gates/BINOME_REQUIRED", "closing critical review"),
            (".agents/state/gates/binome_required", "closing critical review"),
            (".agents/state/gates/AFFIRMATION_REQUIRED", "durable affirmation"),
            (".agents/state/gates/affirmation_required", "durable affirmation"),
            (".agents/state/gates/KICKOFF_REQUIRED", "kickoff guard"),
            # CINQUIÈME GARDE (T-00000654), les DEUX casses. Sa sortie tracée est
            # `--sans-cible`, contrôlée juste en dessous.
            (".agents/state/gates/PLAN_CIBLE_REQUIRED", "PLAN TARGET"),
            (".agents/state/gates/plan_cible_required", "PLAN TARGET"),
        )
        for file_path, extrait in cas:
            body = invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
            )
            self.assertIsNotNone(body, f"NON refusé : {file_path}")
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny",
                             file_path)
            raison = body["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn(extrait, raison, file_path)
            # LE REFUS NOMME SA SORTIE LÉGITIME. Un refus sans issue se
            # contourne ; celui qui nomme son issue TRACÉE se respecte.
            if extrait != "kickoff guard":
                self.assertTrue(
                    "--sans-binome" in raison or "AFFIRMATION_SANS_BINOME" in raison
                    or "--sans-cible" in raison,
                    f"le refus ne nomme aucune sortie tracée : {file_path}")

        # LE SÉPARATEUR NTFS, PAR APPEL DIRECT — et c'est un correctif du binôme.
        # Les trois cas `\` passaient par `invoke`, donc par `normalize_path`,
        # qui a DÉJÀ converti les séparateurs : ils étaient vacants (mesuré —
        # retirer le repli du hook laissait les 44 tests verts). `safe_bash`
        # appelle `protected_reason` par cette porte-là, donc c'est le chemin où
        # le repli porte réellement.
        for brut in (".agents\\state\\gates\\BINOME_REQUIRED",
                     ".agents\\state\\gates\\AFFIRMATION_REQUIRED",
                     ".AGENTS\\STATE\\GATES\\KICKOFF_REQUIRED",
                     ".agents\\state\\gates\\PLAN_CIBLE_REQUIRED"):
            raison, regle = protect_paths.protected_reason(brut)
            self.assertTrue(raison, f"séparateur NTFS non replié : {brut}")
            self.assertIn("arming", regle, brut)

    def test_CONTROLE_NEGATIF_un_chemin_voisin_reste_editable(self):
        """Sans lui, le témoin ci-dessus passerait avec une garde qui refuse
        TOUT — et une garde qui refuse tout se fait retirer en une semaine.

        Le suffixe se compare en FIN de chemin, jamais en sous-chaîne : un
        fichier de notes qui porte ces mots dans son nom reste éditable."""
        for file_path in (
            ".agents/state/gates/BINOME_REQUIRED.md",
            "docs/binome_required_notes.md",
            ".agents/state/gates/AFFIRMATION_REQUIRED_old",
            ".agents/state/gates/",
            # LA SORTIE QUE LE REFUS NOMME DOIT RESTER PRATICABLE — relevé du
            # binôme, et rien ne le gelait. Un refus qui nomme une issue
            # elle-même refusée se contourne au lieu de se respecter, et un
            # élargissement futur du suffixe la fermerait sans que personne ne
            # le voie.
            ".agents/state/gates/AFFIRMATION_SANS_BINOME",
            ".agents/state/local/binome/_sans-slot.critic-opus.json",
            # LE VOISIN DE LA CINQUIÈME GARDE reste éditable : le suffixe se
            # compare en FIN de chemin, jamais en sous-chaîne.
            ".agents/state/gates/PLAN_CIBLE_REQUIRED.md",
        ):
            self.assertIsNone(
                invoke(
                    protect_paths,
                    {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
                ),
                f"refusé à tort : {file_path}",
            )

    def test_protect_paths_denies_the_gitleaks_exception_register(self):
        """T-00000844 — `.gitleaks.toml` est le registre d'exceptions de la porte
        class-0 : un Edit d'agent qui le corrompait éteignait la porte aux deux
        hooks. Pilote seul, casse et séparateur NTFS repliés ; le voisin reste
        éditable."""
        for file_path in (".gitleaks.toml", ".GitLeaks.TOML", "sub/.gitleaks.toml"):
            body = invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
            )
            self.assertIsNotNone(body, f"NON refusé : {file_path}")
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
            raison = body["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("pilot alone", raison, file_path)
            self.assertIn("NO agent-writable", raison, file_path)
        raison, regle = protect_paths.protected_reason("sub\\.GITLEAKS.toml")
        self.assertTrue(raison)
        self.assertEqual(regle, "gitleaks-allowlist")
        self.assertIsNone(invoke(
            protect_paths,
            {"tool_name": "apply_patch", "tool_input": {"file_path": "docs/gitleaks-notes.md"}},
        ))

    def test_protect_paths_denies_the_plan_chain_marker_and_the_push_defaut_pair(self):
        """T-00000698 (repli de T-00000706) — DEUX TROUS FERMÉS PAR UNE MÉTHODE
        NEUVE, sans toucher au témoin des quatre marqueurs ci-dessus (que
        T-00000700 renomme : deux lots sur la même méthode seraient une collision).

        (1) `PLAN_CHAIN_REQUIRED` était dans le tuple de `protected_reason` sans
        AUCUN témoin. (2) `PUSH_DEFAUT_PROTEGE` (armement du refus de pousser
        vers la branche par défaut) et `PUSH_DEFAUT_AUTORISE` (sa sortie
        pilote-seule) étaient protégés sur Claude (`protect-paths.sh:171,175`)
        et sur AUCUN jumeau Python — mesuré : un `apply_patch` les écrivait sans
        refus sur les quatre hôtes Python. Mutation qui rougit : une entrée du
        tuple retirée, sur UN jumeau ou les deux.

        La troisième colonne est INCONDITIONNELLE : chaque refus nomme sa sortie
        tracée (`--sans-chaine`) ou dit qu'il n'y en a AUCUNE d'agent-écrivable
        (`NO agent-writable`) — un refus muet sur son issue se contourne. Ce qui
        n'est PAS ajouté : aucun équivalent à `permissions.deny` sur ces hôtes ;
        `AFFIRMATION_SANS_BINOME` reste éditable (contrôle négatif ci-dessus)."""
        cas = (
            (".agents/state/gates/plan_chain_required", "PLAN CHAIN", "--sans-chaine"),
            (".agents/state/gates/PUSH_DEFAUT_PROTEGE", "DEFAULT BRANCH", "NO agent-writable"),
            (".agents/state/gates/push_defaut_protege", "DEFAULT BRANCH", "NO agent-writable"),
            (".agents/state/gates/PUSH_DEFAUT_AUTORISE", "PILOT ALONE", "NO agent-writable"),
            (".agents/state/gates/push_defaut_autorise", "PILOT ALONE", "NO agent-writable"),
        )
        for file_path, extrait, sortie_attendue in cas:
            body = invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
            )
            self.assertIsNotNone(body, f"NON refusé : {file_path}")
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny",
                             file_path)
            raison = body["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn(extrait, raison, file_path)
            self.assertIsInstance(sortie_attendue, str)
            self.assertIn(sortie_attendue, raison,
                          f"le refus ne dit pas son issue : {file_path}")
        # LE SÉPARATEUR NTFS PAR APPEL DIRECT, avec la RÈGLE attendue — c'est la
        # porte par laquelle `safe_bash.judge_redirect` entre, et les rule ids
        # sont ceux de `protect-paths.sh`.
        for brut, regle_attendue in (
            (".agents\\state\\gates\\PLAN_CHAIN_REQUIRED", "plan-chain-arming"),
            (".agents\\state\\gates\\PUSH_DEFAUT_PROTEGE", "push-defaut-arming"),
            (".AGENTS\\STATE\\GATES\\PUSH_DEFAUT_AUTORISE", "push-defaut-sortie"),
        ):
            raison, regle = protect_paths.protected_reason(brut)
            self.assertTrue(raison, f"séparateur NTFS non replié : {brut}")
            self.assertEqual(regle, regle_attendue, brut)
        # CONTRÔLE NÉGATIF : suffixe, jamais sous-chaîne — un voisin reste éditable.
        for file_path in (
            "plan_chain_required.md",
            "docs/plan_chain_required_notes.md",
            ".agents/state/gates/PUSH_DEFAUT_PROTEGE.md",
            "docs/push_defaut_autorise_notes.md",
        ):
            self.assertIsNone(
                invoke(
                    protect_paths,
                    {"tool_name": "apply_patch", "tool_input": {"file_path": file_path}},
                ),
                f"refusé à tort : {file_path}",
            )

    def test_protect_paths_allows_codex_agent_config(self):
        self.assertIsNone(
            invoke(
                protect_paths,
                {"tool_name": "apply_patch", "tool_input": {"file_path": ".codex/agents/foo.toml"}},
            )
        )

    def test_safe_bash_blocks_power_shell_delete_of_tracked_file(self):
        for command in (
            "Remove-Item -LiteralPath .codex/config.toml -Force",
            "Move-Item -LiteralPath .codex/config.toml -Destination .tmp/config.toml -Force",
        ):
            body = invoke(
                safe_bash,
                {"tool_name": "Bash", "tool_input": {"command": command}},
            )
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_safe_bash_allows_temp_cleanup(self):
        self.assertIsNone(
            invoke(
                safe_bash,
                {"tool_name": "Bash", "tool_input": {"command": "rm -rf .tmp/build-output"}},
            )
        )

    def test_safe_bash_blocks_tracked_file_even_in_allowlist(self):
        with mock.patch.object(safe_bash, "git_tracked", return_value=True):
            body = invoke(
                safe_bash,
                {"tool_name": "Bash", "tool_input": {"command": "rm -f .tmp/tracked-output"}},
            )
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_safe_bash_allows_git_rm_and_git_mv_on_tracked_files(self):
        # git rm/mv stage recoverable changes (rewindable via git) — outside the guard's scope
        with mock.patch.object(safe_bash, "git_tracked", return_value=True):
            for command in ("git rm -q docs/tasks/T-002.md", "git mv AGENTS.md docs/AGENTS.md"):
                self.assertIsNone(
                    invoke(
                        safe_bash,
                        {"tool_name": "Bash", "tool_input": {"command": command}},
                    ),
                    command,
                )

    def test_safe_bash_still_blocks_raw_rm_mixed_with_git_rm(self):
        with mock.patch.object(safe_bash, "git_tracked", return_value=True):
            body = invoke(
                safe_bash,
                {"tool_name": "Bash", "tool_input": {"command": "git rm -q a.md; rm -f b.md"}},
            )
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_audit_gate_requires_exact_audit_pass_record_and_accepts_wrappers(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "not-owner/pkg audit=pass\nowner/pkg audit=pass\n", encoding="utf-8"
            )
            self.assertIsNone(
                invoke(
                    audit_gate,
                    {"tool_name": "Bash", "tool_input": {"command": "npx.cmd --yes skills add owner/pkg"}},
                )
            )
            body = invoke(
                audit_gate,
                {"tool_name": "Bash", "tool_input": {"command": "npx.cmd --yes skills add other/pkg"}},
            )
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
            body = invoke(
                audit_gate,
                {"tool_name": "Bash", "tool_input": {"command": "npx -y skills add other/pkg"}},
            )
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def _audit_gate_arm(self, command):
        """One stimulus through the real main(); True when the host is told to
        deny. NOTE the blocking convention: this host blocks by PRINTING a
        permissionDecision=deny body on stdout and exiting 0 — the `exit 2` of
        the Claude homologue has no counterpart here, so a return code would
        assert nothing."""
        body = invoke(audit_gate, {"tool_name": "Bash", "tool_input": {"command": command}})
        if body is None:
            return False
        return body["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_audit_gate_ignores_installations_quoted_inside_another_command(self):
        """A command that TALKS about an install must not be read as one.

        Measured in session: `tasks.py new "… npx skills add …"` was refused and
        the board write was lost. The arms pin BOTH halves of the trade — quoted
        mentions pass, a naked unaudited install still blocks.
        """
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            arms = (
                # (label, command, must the host be told to deny?)
                ("a: board title quoting the install line",
                 'python .agents/bin/tasks.py new "corriger le garde: npx skills add bloque le board"',
                 False),
                ("a2: ledger entry quoting it in single quotes",
                 "python .agents/bin/ledger.py add --category lesson 'npx skills add is gated'",
                 False),
                ("a3: commit message quoting it",
                 'git commit -m "fix(hooks): npx skills add no longer blocks the board"',
                 False),
                ("b: real install, no audit entry -> BLOCKED",
                 "npx skills add other/pkg", True),
                ("c: real install, audit=pass entry -> allowed",
                 "npx skills add owner/pkg", False),
                ("c2: real install, entry present, wrapper + options",
                 "npx.cmd --yes skills add owner/pkg", False),
                ("d: unpaired apostrophe, install still naked -> BLOCKED",
                 "echo l'index && npx skills add other/pkg", True),
                ("d2: nested quotes, leftmost opening quote wins",
                 'python .agents/bin/ledger.py add "l\'index et \'npx skills add x\' dedans"',
                 False),
            )
            for label, command, expected in arms:
                with self.subTest(arm=label):
                    self.assertEqual(self._audit_gate_arm(command), expected, label)

    # The local skills fallback's `install` gate (T-00000461) lives in test_guard_hooks_copilot.py.

    def test_audit_gate_quote_scrub_is_left_to_right_and_never_touches_bare_text(self):
        # The load-bearing detail of stage 1: ONE pass, leftmost opening quote
        # wins, so a double-quoted segment containing apostrophes is neutralized
        # whole instead of being cut at the inner quote. And a command with no
        # quotes at all comes back byte-identical — the guarantee that the scrub
        # cannot make the gate allow a naked install.
        self.assertEqual(
            audit_gate.scrub_quoted("""x "a 'b' c" y"""), "x  @@  y"
        )
        self.assertEqual(
            audit_gate.scrub_quoted("npx skills add owner/pkg"), "npx skills add owner/pkg"
        )
        # An unpaired quote closes nothing and must not swallow the rest.
        self.assertIn("npx skills add", audit_gate.scrub_quoted("echo l'index && npx skills add x"))

    def test_audit_gate_bash_c_wrapper_is_a_KNOWN_UNCLOSED_bypass(self):
        # NOT a passing feature: an install nested in a quoted `-c` argument is
        # inside a neutralized segment, so it is NOT seen. Before stage 1 it was
        # caught by substring luck; the trade is deliberate and shared with the
        # Claude homologue. This test EXISTS TO RECORD THE HOLE — if someone
        # later teaches the guard to parse `-c`, it should fail and be inverted.
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text("", encoding="utf-8")
            self.assertFalse(
                self._audit_gate_arm('bash -c "npx skills add other/pkg"'),
                "known bypass: closing it requires parsing the nested command",
            )

    # -- T-00000151 ---------------------------------------------------------
    # The recognition stage below is a port of .claude/hooks/safe-bash.sh, and
    # the cases are kept IDENTICAL in the Codex and Gemini suites (same guard
    # source, same arms, same verdicts). The cross-host verdicts themselves live
    # in .agents/evals/test_guard_decision_parity.py; what is asserted here is
    # this host's own contract, stage by stage.

    def _safe_bash_denies(self, command):
        """One stimulus through the real main(); True when the host is told to
        deny. Same blocking convention as _audit_gate_arm: this host denies by
        PRINTING a permissionDecision body, so a return code asserts nothing."""
        body = invoke(safe_bash, {"tool_name": "Bash", "tool_input": {"command": command}})
        if body is None:
            return False
        return body["hookSpecificOutput"]["permissionDecision"] == "deny"

    def _safe_bash_deny_reason(self, command):
        """The same stimulus, but returning WHY. `_safe_bash_denies` above hands
        back a BOOLEAN: it reads the decision and THROWS THE MOTIVE AWAY. An arm
        built on it therefore stays GREEN under a mutant that swaps one guard's
        message for another's — same verdict, same shape, wrong reason — and this
        guard carries five distinct refusals. A mechanism whose return channel is
        discarded does not exist (L-00000136), so this reader lives BESIDE the
        boolean instead of replacing it: the boolean remains the right tool for
        the ALLOW half and for the arms that only pin a verdict. Returns the
        permissionDecisionReason, or "" when this host was not told to deny — ""
        never satisfies an assertIn, so a silent non-deny fails loudly."""
        body = invoke(safe_bash, {"tool_name": "Bash", "tool_input": {"command": command}})
        if body is None:
            return ""
        out = body["hookSpecificOutput"]
        if out["permissionDecision"] != "deny":
            return ""
        return out.get("permissionDecisionReason", "")

    def test_safe_bash_quote_scrub_preserves_length(self):
        """Stage 1's isometry is load-bearing, and an earlier revision of this
        guard got it wrong: the segment cuts and the token offsets are computed on
        the SCRUBBED copy and applied to the RAW payload, so a replacement of a
        different length mis-indexes everything after the first quoted title —
        which is the common case, not an edge one. A payload with no quotes comes
        back byte-identical, which is what makes stage 1 unable to hide a naked
        `rm`."""
        for command in (
            'python .agents/bin/tasks.py new "corriger le garde: rm -rf src/x"',
            "python .agents/bin/ledger.py add --category lesson 'rm -rf src/x refuse'",
            """x "a 'b' c" y""",
        ):
            with self.subTest(command=command):
                scrubbed = safe_bash.scrub_quoted(command)
                self.assertEqual(len(scrubbed), len(command))
                self.assertNotIn("rm", scrubbed)
        self.assertEqual(safe_bash.scrub_quoted("rm -rf src/x"), "rm -rf src/x")

    def test_safe_bash_cuts_segments_on_real_separators_only(self):
        """A `;` INSIDE quotes must not fabricate a segment boundary, and a real
        one must still cut. Both halves in one place because the trade is between
        them: this is the defect that refused a board write whose TITLE described
        a deletion."""
        self.assertFalse(
            self._safe_bash_denies('python .agents/bin/tasks.py new "titre; rm -rf src/x"')
        )
        self.assertTrue(
            self._safe_bash_denies('python .agents/bin/tasks.py new "clean title" ; rm -rf src/x')
        )

    def test_safe_bash_reads_a_verb_the_shell_would_execute_through_its_quotes(self):
        """`"rm" -rf x`, `r"m" -rf x` and `sudo "rm" -rf x` ARE executed by the
        shell, so a guard that reads them as data is fail-open. The verb is taken
        from the SHLEX tokens of the raw segment, which covers all three at once.
        DIVERGENCE, named in the parity eval: the Claude homologue allows these,
        because its scrub replaces a quoted run by a fixed token."""
        for command in ('"rm" -rf src/x', 'r"m" -rf src/x', 'sudo "rm" -rf src/x'):
            with self.subTest(command=command):
                self.assertTrue(self._safe_bash_denies(command))

    def test_safe_bash_ignores_a_destructive_command_quoted_as_data(self):
        for command in (
            'python .agents/bin/tasks.py new "corriger le garde: rm -rf src/x refuse"',
            'python .agents/bin/tasks.py new "rm"',
            'python .agents/bin/tasks.py new "rm -rf /"',
            "python .agents/bin/ledger.py add --category lesson 'rm -rf src/x est refuse'",
            'git commit -m "fix(hooks): rm -rf no longer blocks the board"',
        ):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_allows_the_founding_ledger_write_and_denies_its_unquoted_twin(self):
        """T-00000146's FOUNDING payload, verbatim, plus the control that makes it
        measure something. What was refused in session on 2026-08-06 is an
        institutional-memory write whose `--text` DESCRIBES a recursive delete: the
        `rm` lives inside quotes, so the shell hands it to ledger.py as an argument
        and never executes it. The twin is the SAME write with its description
        UNQUOTED, where the `;` is a real separator and bash genuinely runs `rm -rf
        src/x`. Neither half is worth anything alone — without the twin the first
        assertion is satisfied by a guard that allows everything, and without the
        first the twin is satisfied by a guard that refuses every mention. The
        Claude homologue pins the same pair as (g1)/(g15).

        This host DENIES BY PRINTING a permissionDecision body, never by its exit
        code: BOTH stimuli exit 0 (measured), so an arm reading the return code
        would come back green on its own control. The decision is what carries the
        verdict here — but a verdict is not a REASON, and this guard raises FIVE
        distinct refusals. The deny half therefore pins the MOTIVE (T-00000227):
        the formulation unique to the rm/mv branch (safe_bash.py:917), so that a
        mutant swapping it for another guard's message turns this arm RED instead
        of leaving it green on an identical verdict. The allow half keeps the
        boolean, which is exactly what an absence of decision needs.
        """
        founding = (
            'python .agents/bin/ledger.py add --category lesson "safe-bash" '
            '--text "le garde refusait une ecriture parce que le texte parlait de rm -rf" '
            "--related T-00000146"
        )
        unquoted_twin = (
            "python .agents/bin/ledger.py add --category lesson safe-bash "
            "--text le garde refusait une ecriture ; rm -rf src/x --related T-00000146"
        )
        self.assertFalse(self._safe_bash_denies(founding))
        self.assertIn(
            "destructive command bypasses agent checkpoints",
            self._safe_bash_deny_reason(unquoted_twin),
        )

    def test_safe_bash_receiver_is_complete_for_every_envelope_and_keyword(self):
        """One arm per envelope and per keyword. An earlier revision of this port
        carried five of the sixteen envelopes, which would have turned `nohup rm
        -rf src/x` into a silent allow — a refusal LOST, the one direction this
        guard must never move in."""
        for envelope in sorted(safe_bash.ENVELOPES):
            with self.subTest(envelope=envelope):
                self.assertTrue(self._safe_bash_denies(f"{envelope} rm -rf src/x"))
        for keyword in sorted(safe_bash.KEYWORDS):
            with self.subTest(keyword=keyword):
                self.assertTrue(self._safe_bash_denies(f"{keyword} rm -rf src/x"))
        # An envelope carrying its OWN argument: nobody can tell where its options
        # stop, so rm/mv fall back to substring semantics inside that window.
        self.assertTrue(self._safe_bash_denies("timeout 5 rm -rf src/x"))
        self.assertTrue(self._safe_bash_denies("nice -n 10 rm -rf src/x"))
        # ...and that fallback is restricted to rm/mv precisely so this passes.
        self.assertFalse(self._safe_bash_denies("sudo apt install ripgrep"))

    def test_safe_bash_reads_the_verb_and_not_a_substring_of_the_line(self):
        for command in ("docker rm container", "git rm -q docs/tasks/T-002.md", "grep rm AGENTS.md"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))
        for command in (
            "/bin/rm -rf src/x", "rm.exe -rf src/x", "FOO=bar rm -rf src/x",
            "find src -type f -exec rm -rf src/x ;", "$(rm src/x)", "`rm src/x`",
        ):
            with self.subTest(command=command):
                self.assertTrue(self._safe_bash_denies(command))

    def test_safe_bash_judges_a_target_by_its_literal_prefix(self):
        """`tmp/$USER` is NOT dissolved: its literal prefix `tmp/` is judgeable, so
        the allowlist still applies. Measured while writing the parity matrix —
        this row denied because is_allowed_target() re-normalized the prefix and
        dropped its trailing separator, silently disabling the allowlist for every
        directory-only prefix."""
        self.assertFalse(self._safe_bash_denies("rm -rf tmp/$USER"))
        self.assertFalse(self._safe_bash_denies("rm -rf .tmp/build-$BUILD_ID"))
        self.assertTrue(self._safe_bash_denies("rm -rf src/$MODULE"))

    def test_safe_bash_fails_closed_when_every_target_dissolves(self):
        """No literal prefix at all means nothing to judge, and the guard refuses
        rather than reading a verb with no target as harmless."""
        for command in ("rm -rf $HOME", "rm -rf ${DIR}", "rm -rf $(pwd)/src", 'rm -rf "$TMPDIR"/x'):
            with self.subTest(command=command):
                self.assertTrue(self._safe_bash_denies(command))
        # PARTIAL dissolution (T-00000762, formula F2): ONE operand dissolves and
        # the other is allowlisted. F0 (`bool(targets) and judged == 0`) let both
        # through on the strength of the allowlisted one — `$HOME` included. The
        # motive is pinned: the refusal must be the dissolution, not a path.
        for command in ("rm -rf dist/x $HOME", 'rm -rf .tmp/y "$X"'):
            with self.subTest(command=command):
                self.assertIn("LITERAL prefix", self._safe_bash_deny_reason(command))

    def test_safe_bash_refuses_zero_operand_and_piped_operands(self):
        """T-00000762. A verb with NO operand and a verb FED BY A PIPE are refused
        by construction: `judge_targets` reports "empty" for the first, and
        main() holds a `fed` flag (set by `xargs`/`parallel` and `-exec`) that
        refuses the second whatever its static operand — `build/x` is
        allowlisted, and `ls | xargs rm -f build/x` still deletes whatever `ls`
        prints. `find … {} \\;` is also refused by shlex (trailing backslash), so
        the MOTIVE is asserted: the refusal must be the pipe, not the quoting."""
        for raw in ("rm", "git ls-files | xargs rm -f"):
            with self.subTest(raw=raw):
                unsafe, why = safe_bash.judge_targets(raw, raw.rindex("rm"), True, False)
                self.assertEqual(unsafe, [])
                self.assertEqual(why, "empty")
        for command in ("ls | xargs rm -f build/x", "find . -exec rm -f build/x {} \\;"):
            with self.subTest(command=command):
                self.assertIn("pipe", self._safe_bash_deny_reason(command))

    def test_safe_bash_judges_git_wipe(self):
        """T-00000762: the unscoped git wipe is guarded on this host too (it did
        not even refuse `git checkout .`). Each deny carries its OWN motive."""
        for command in (
            "git reset --hard",
            "git stash",
            'git stash push -m "wip"',
            "git checkout .",
        ):
            with self.subTest(command=command):
                self.assertIn("unscoped", self._safe_bash_deny_reason(command))
        for command in (
            "git reset --soft HEAD~1",
            "git stash push -- src/x",
            "git stash list",
            "git restore --staged .",
        ):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_judges_git_output(self):
        """T-00000762: `--output` writes a file (a tracked one included), exactly;
        `--output-indicator-new` is another option and writes nothing."""
        self.assertIn("--output", self._safe_bash_deny_reason("git show --output=README.md HEAD"))
        self.assertFalse(self._safe_bash_denies("git log --output-indicator-new=x -1"))

    def test_safe_bash_judges_git_grep_pager(self):
        """T-00000762: `git grep -O` runs a command. `O` in a short cluster before
        any value letter, and any abbreviation of --open-files-in-pager of two
        letters or more, are refused; `-e Ofoo` (a pattern) and `--or` are not."""
        for command in ("git grep -nO foo", "git grep --op=x foo"):
            with self.subTest(command=command):
                self.assertIn("open-files-in-pager", self._safe_bash_deny_reason(command))
        for command in ("git grep -e Ofoo", "git grep --or -e a -e b"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    # -- T-00000762, closing-pair pass (S-00002512 / S-00002513 + addendum) ----
    # Each arm below was ALLOWED by the bridge of eb058e8a (measured on the three
    # hosts before the fix); the Claude homologue pins the same shapes as
    # (y1)-(y64) in .claude/hooks/safe-bash-t-y.test.sh, the parity matrix row by row.

    def test_safe_bash_redirect_operators_are_not_separators(self):
        """`&>`, `&>>` and `<&` are redirect operators, not separators: the
        coarse cut used to throw `src/a.py` into a segment of its own and the rm
        passed on the strength of `build/x`."""
        for command in (
            "rm build/x &>/dev/null src/a.py",
            "rm build/x &>>/dev/null src/a.py",
            "rm build/x <&- src/a.py",
        ):
            with self.subTest(command=command):
                self.assertIn("src/a.py", self._safe_bash_deny_reason(command))
        self.assertEqual(
            [raw for raw, _ in safe_bash.coarse_segments("a &>f && b 2>&1 | c <&- ; d")],
            ["a &>f ", " b 2>&1 ", " c <&- ", " d"],
        )

    def test_safe_bash_fed_survives_envelopes_substitutions_and_redirects(self):
        """The `fed` flag is set inside an envelope's window, survives a process
        substitution (the frame restores it), an expansion, a leading redirect
        and a `;` inside the frame; `-ok`/`-okdir` join `-exec`."""
        for command in (
            "ls | nice -n 10 xargs rm -f build/x",
            "ls | timeout 5 xargs rm -f build/x",
            "ls | sudo -u root xargs rm -f build/x",
            "nice -n 10 parallel rm -f build/x",
            "xargs -a <(git ls-files) rm -f build/x",
            "parallel -a <(git ls-files) rm -f build/x",
            "xargs -a $F rm -f build/x",
            "< list.txt xargs rm -f build/x",
            "xargs -a <(a; b) rm -f build/x",
            "find . -name x -ok rm -f build/x {} ;",
            "find . -name x -okdir rm -f build/x {} ;",
        ):
            with self.subTest(command=command):
                self.assertIn("pipe", self._safe_bash_deny_reason(command))

    def test_safe_bash_a_redirect_or_expansion_never_takes_the_command_slot(self):
        """The walk reads UNITS: a redirect's target, an expansion inside a word
        and a quoted assignment value never take the command slot, so the verb
        behind them is seen — all five passed on the three hosts before."""
        for command in (
            "< list.txt rm -rf src/x",
            "> out.txt rm -rf src/x",
            "2>/dev/null rm -rf src/x",
            "sudo $X rm -rf src/x",
            "FOO=$x rm -rf src/x",
            'FOO="bar" rm -rf src/x',
            "$X rm -rf build/x",
        ):
            with self.subTest(command=command):
                self.assertIn("checkpoint", self._safe_bash_deny_reason(command))
        for command in (
            "case $x in a) rm -rf .tmp/x;; esac",
            "echo x > out.txt rm -rf src/x",
            "echo $(date) rm -rf src/x",
        ):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_judges_a_glued_mv_destination(self):
        for command in ("mv -tsrc build/x", "mv --target-directory=src build/x", "mv --targ=src build/x"):
            with self.subTest(command=command):
                self.assertIn("src", self._safe_bash_deny_reason(command))
        self.assertFalse(self._safe_bash_denies("mv -tbuild/y build/x"))

    def test_safe_bash_git_abbreviations_and_stdin_pathspecs(self):
        """git accepts any unambiguous abbreviation (measured, git 2.55: `reset
        --h` wipes), and a pathspec list read from stdin scopes nothing."""
        for command in (
            "git reset --h",
            "git reset --har HEAD",
            "git restore --staged --wo .",
            "git stash push --m wip",
            "git stash push --pathspec-from-file=-",
            "git stash push --pathspec-from-file -",
            "git restore --pathspec-from-file=-",
        ):
            with self.subTest(command=command):
                self.assertIn("unscoped", self._safe_bash_deny_reason(command))
        self.assertFalse(self._safe_bash_denies("git stash push --pathspec-from-file=list.txt"))

    def test_safe_bash_broad_pathspecs(self):
        for command in (
            "git checkout -- '*'",
            "git checkout -- *",
            "git restore ':(top)'",
            "git restore ./.",
            "git stash push -- ':!src/x'",
            "git checkout $BRANCH",
        ):
            with self.subTest(command=command):
                self.assertIn("unscoped", self._safe_bash_deny_reason(command))
        for command in ('git restore "src/a b.txt"', 'git checkout "$BRANCH"', "git restore -- src/x"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_hidden_git_subcommand_fails_closed(self):
        """Decision 3: an unquoted expansion where git reads its subcommand is
        refused under its own rule; an expansion VALUE hides nothing."""
        for command in ("git $SUB .", "git $(echo reset) --hard", "git stash $MODE"):
            with self.subTest(command=command):
                self.assertIn("where git reads its subcommand", self._safe_bash_deny_reason(command))
        self.assertFalse(self._safe_bash_denies("git -C $d status"))
        self.assertIn("unscoped", self._safe_bash_deny_reason("git -C $d reset --hard"))
        self.assertIn("unscoped", self._safe_bash_deny_reason('git --git-dir="$d" restore .'))

    def test_safe_bash_git_clean_dry_run_passes_and_remedies_are_possible(self):
        """Decision 5: `git clean -n` deletes nothing and is the remedy the
        refusal names; `reset --hard` names a remedy that takes no path."""
        for command in ("git clean -n", "git clean --dry-run", "git clean -ndx"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))
        self.assertIn("git clean -n", self._safe_bash_deny_reason("git clean -fdx"))
        self.assertIn("unscoped", self._safe_bash_deny_reason("git clean -f -e -n"))
        self.assertIn("git reset --keep", self._safe_bash_deny_reason("git reset --hard"))

    def test_safe_bash_root_is_a_bare_slash_and_a_listed_dir_itself_passes(self):
        """Decision 6, DIVERGENCE 9 closed: `_ROOT_RM` wants a BARE `/`, and the
        listed directory itself is inside the list."""
        for command in ("rm -rf dist", "rm -rf dist/", "rm -rf ./node_modules/", "rm -rf build"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))
        self.assertIn("catastrophic", self._safe_bash_deny_reason("rm -rf /"))
        self.assertNotIn("catastrophic", self._safe_bash_deny_reason("rm -rf src/"))

    def test_safe_bash_tracked_veto_is_case_insensitive(self):
        """Addendum c: on APFS/NTFS `rm build/KEEP.txt` deletes the tracked
        `build/keep.txt`, and git's plain pathspec misses it even with
        core.ignorecase=true (measured) — `:(icase)` sees it. A REAL throwaway
        repository answers here, so a veto that drops the magic turns this red."""
        import subprocess

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            git = ["git", "-C", tmp]
            subprocess.run(git + ["init", "-q"], check=True)
            (Path(tmp) / "build").mkdir()
            (Path(tmp) / "build" / "keep.txt").write_text("k\n", encoding="utf-8")
            subprocess.run(git + ["add", "build/keep.txt"], check=True)
            subprocess.run(
                git + ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"],
                check=True,
            )

            def tracked_there(path):
                return subprocess.run(
                    git + ["ls-files", "--error-unmatch", "--", path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ).returncode == 0

            with mock.patch.object(safe_bash, "git_tracked", side_effect=tracked_there):
                for command in ("rm build/KEEP.txt", "rm build/keep.TXT", "rm build/keep.txt"):
                    with self.subTest(command=command):
                        self.assertIn("checkpoint", self._safe_bash_deny_reason(command))
                self.assertFalse(self._safe_bash_denies("rm build/other.txt"))

    def test_safe_bash_fails_closed_when_shlex_refuses_the_tokenisation(self):
        """A trailing `\\` (a line continuation) and an unbalanced quote both make
        shlex raise; the whitespace retry that follows is a GUESS, so a destructive
        verb recognised in that degraded state is refused instead of being judged
        on targets nobody could read."""
        self.assertTrue(self._safe_bash_denies("rm -rf src " + chr(92)))
        # The degraded state must not spread: a segment shlex refuses does not
        # make the guard refuse a LATER, perfectly readable temp cleanup.
        self.assertFalse(self._safe_bash_denies("echo l'index && rm -rf .tmp/out"))
        self.assertTrue(self._safe_bash_denies("echo l'index && rm -rf src/x"))

    def test_safe_bash_blocks_an_rg_that_does_not_resolve(self):
        """An absent ripgrep fails INDISCERNIBLY from an empty result, so a sweep
        that never ran reads as 'zero occurrences'. The token is resolved AS
        WRITTEN, which is why the three spellings are asserted separately."""
        with mock.patch.dict(os.environ, {"PATH": ""}):
            for command in (
                "rg motif", "rg.exe motif", "/nonexistent-guard-probe-zz/rg motif",
            ):
                with self.subTest(command=command):
                    self.assertTrue(self._safe_bash_denies(command))

    def test_safe_bash_never_blocks_a_present_rg(self):
        """The guard fires on ABSENCE only: blocking a working tool would buy
        nothing, since the failure mode it exists for cannot occur then."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            for name in ("rg", "rg.exe"):
                shim = Path(directory) / name
                shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                shim.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": directory}):
                self.assertFalse(self._safe_bash_denies("rg motif"))

    def test_safe_bash_never_blocks_its_own_diagnostic_probe(self):
        """A GUARD MUST NOT BLOCK ITS OWN DIAGNOSTIC. A probe prints a path or
        fails; it never runs the name it resolves, so it cannot produce the false
        emptiness this guard exists to catch. Measured on the Claude homologue:
        `command -v rg` was refused, i.e. the one command that establishes WHY the
        guard fired. The flag dies at the next separator, so the probe opens no
        bypass window — the last arm is what pins that."""
        with mock.patch.dict(os.environ, {"PATH": ""}):
            for command in ("command -v rg", "command -V rg", "which rg", "type rg", "hash rg"):
                with self.subTest(command=command):
                    self.assertFalse(self._safe_bash_denies(command))
            self.assertTrue(self._safe_bash_denies("command -v rg && rg motif"))
        for command in ("which rm", "command -v rm", "type mv"):
            with self.subTest(command=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_blocks_a_write_redirect_to_a_tracked_or_protected_file(self):
        """T-00000244, the write-redirect guard, one arm per class.

        The predicate is the one MEASURED in core-scripts/measure_shell_write_fp.py:
        refuse iff the literal target of a WRITE redirection (`>`, `>>`, `>|`,
        `&>`, `&>>`, `N>file`) is git-tracked OR covered by the protected-path
        guard — the second clause being what catches the two SENSITIVE files that
        are not git-tracked (`KICKOFF_REQUIRED` disarms the mandate guard, `.mcp.json`
        escapes the Edit deny). Descriptor duplication (`2>&1`, `>&2`), quoted and
        $-expanded targets, and targets outside the repo all PASS by construction —
        including the doctrine idiom `cmd > out 2>&1` the kit ORDERS agents to use.
        """
        for command in (
            "echo x >> AGENTS.md",                              # git-tracked, append
            "echo x > AGENTS.md",                               # git-tracked, truncate
            "printf y > .agents/state/gates/KICKOFF_REQUIRED",  # protected: kickoff-arming
            "echo x > .mcp.json",                              # protected: mcp-config
            "echo x > src/legacy/note.md",                     # protected: prefix
            "echo x 2> AGENTS.md",                             # N>file writes, judged
        ):
            with self.subTest(deny=command):
                self.assertTrue(self._safe_bash_denies(command), command)
        for command in (
            "echo x > /tmp/scratch",              # outside the repo
            "make check > build.out 2>&1",        # THE DOCTRINE IDIOM: out untracked
            "echo x >&2",                         # descriptor duplication, not a write
            "cat f > $DEST",                      # $-expanded target: invisible
            'printf y > "spaced name.txt"',       # quoted target: invisible
            'echo "a > b is data"',               # a `>` inside quotes is not a redirect
        ):
            with self.subTest(allow=command):
                self.assertFalse(self._safe_bash_denies(command), command)

    def test_safe_bash_redirect_reason_names_the_rule_and_how_the_target_was_read(self):
        """T-00000698 — the verdicts of the write-redirect guard do not move; its
        REASON now says, per refused path, the rule AND how the target was read
        (`relative` / `inside` / `outside`), plus one English clause: a relative
        target is resolved against the PROJECT ROOT (never a `cd` internal to
        the command), and a protected name is refused wherever it lives, outside
        the repository included — a credential-looking token being judged against
        the list of THIS host. The lists differed until T-00000721 (`id_rsa` was
        refused on Claude only, `server.key` on the Python hosts only; measured by
        the exec-critic on b7055f0, when the clause claimed "WHEREVER it lives" for
        every host); they are aligned token for token since, and the clause says so.
        Same arms as the Claude bench (t20)-(t26).

        (t25)/(t26) are the ones that DISCRIMINATE the breach this lot closes:
        before T-00000698 the two `push_defaut_*` markers were protected on
        Claude only, so both stimuli came back "" (no deny) on this host —
        measured. (t26) is deliberately OUTSIDE the checkout: the same marker
        relative in the real checkout is git-tracked, hence refused BEFORE as
        AFTER by the git clause, which proves nothing. (t24) is the only witness
        of the ORDER of the mode test (outside first).

        BOUND, reasoned and never executed: on Windows `Path("/tmp/t698")` is not
        absolute, so the `outside` arms would resolve UNDER the root — UNKNOWN
        there, the CI leg being Linux."""
        root = safe_bash.ROOT
        # (t20) relative after an internal cd: the ROOT, never the cd.
        raison = self._safe_bash_deny_reason("cd /tmp/t698 && echo x > AGENTS.md")
        self.assertIn("AGENTS.md (git-tracked, relative)", raison)
        self.assertIn("PROJECT ROOT", raison)
        self.assertIn(f"({root})", raison, "the root token is the git toplevel of the hook")
        # (t21) the SAME name, absolute and outside: passes.
        self.assertFalse(self._safe_bash_denies("echo x > /tmp/t698/AGENTS.md"))
        # (t22) a guard-arming marker outside the repo: its own rule, mode outside.
        raison = self._safe_bash_deny_reason(
            "printf y > /tmp/t698/.agents/state/gates/BINOME_REQUIRED")
        self.assertIn("(binome-arming, outside)", raison)
        self.assertIn("judged against the list of THIS host", raison)
        # (t23), the `inside` arm, lives in its OWN method below: it is skipped,
        # with its reason said, on a root carrying a space or a quote.
        # (t24) a relative prefix that LEAVES the root is outside, never relative.
        raison = self._safe_bash_deny_reason(
            "printf y > ../t698-jetable/.agents/state/gates/BINOME_REQUIRED")
        self.assertIn("(binome-arming, outside)", raison)
        self.assertNotIn("binome-arming, relative)", raison)
        # (t25) the pilot-only exit, relative and git-ignored: "" before this lot.
        raison = self._safe_bash_deny_reason(
            "printf y > .agents/state/gates/PUSH_DEFAUT_AUTORISE")
        self.assertIn("(push-defaut-sortie, relative)", raison)
        # (t26) the arming marker OUTSIDE the repo: "" before this lot.
        raison = self._safe_bash_deny_reason(
            "printf y > /tmp/t698/.agents/state/gates/PUSH_DEFAUT_PROTEGE")
        self.assertIn("(push-defaut-arming, outside)", raison)

    @unittest.skipIf(
        any(c in str(safe_bash.ROOT) for c in " '\""),
        "(t23) the inside arm is unreachable on a root carrying a space or a quote: the "
        "bare absolute target is split at the space (the guard reads a prefix that is "
        "not the file, and so would bash) and a quoted one is invisible by design — "
        "T-00000720",
    )
    def test_safe_bash_redirect_reason_reaches_the_inside_arm_on_an_absolute_target(self):
        """(t23) an ABSOLUTE target under the root is the only arm reaching `inside`.
        Its OWN method (T-00000698, correction — A-T1) so that the skip above names
        its reason instead of turning (t20)-(t26) red for a cause that is a BOUND of
        the guard, not a defect of the bench: measured on a clone under a path with a
        space, this arm was the only red."""
        raison = self._safe_bash_deny_reason(f"echo x > {safe_bash.ROOT}/AGENTS.md")
        self.assertIn("AGENTS.md (git-tracked, inside)", raison)

    def test_safe_bash_redirect_refuses_an_arming_marker_by_its_name_alone(self):
        """T-00000698, correction (B#1 of the closing pair, measured on the live
        hooks): `cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE` and
        `printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"` both came back ""
        on this host — the cd hides the DIRECTORY from the root-relative
        resolution, the quotes make the target invisible to stage 1. The NAME
        hides from neither: a redirect whose last segment, case-folded, is one of
        the arming markers protect_paths names is refused under
        `arming-marker-name` whatever its form (bare, quoted, expanded directory),
        the list being DERIVED from the twin's `*_SUFFIX` constants
        (`arming_marker_names()`), never a third copy. Closed list: the general
        cd/quote case for an ORDINARY target is T-00000720, and the negative
        control holds it unchanged. A target already refused by its PATH is not
        listed a second time by its name. Named mutation: `arming_marker_target`
        returning None → the three deny arms are red, the control stays green."""
        raison = self._safe_bash_deny_reason(
            "cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE")
        self.assertIn("PUSH_DEFAUT_AUTORISE (arming-marker-name, bare)", raison)
        raison = self._safe_bash_deny_reason(
            'printf y > ".agents/state/gates/PUSH_DEFAUT_AUTORISE"')
        self.assertIn(
            '".agents/state/gates/PUSH_DEFAUT_AUTORISE" (arming-marker-name, quoted)', raison)
        raison = self._safe_bash_deny_reason("printf y > $D/kickoff_required")
        self.assertIn("$D/kickoff_required (arming-marker-name, bare)", raison)
        self.assertFalse(self._safe_bash_denies("cd docs && echo x > notes.txt"))
        raison = self._safe_bash_deny_reason(
            "printf y > .agents/state/gates/PUSH_DEFAUT_AUTORISE")
        self.assertIn("(push-defaut-sortie, relative)", raison)
        # The ROW form, not the bare rule id: the deny prose itself names the rule.
        self.assertNotIn("PUSH_DEFAUT_AUTORISE (arming-marker-name", raison)
        names = safe_bash.arming_marker_names()
        self.assertIn("push_defaut_autorise", names)
        self.assertIn("kickoff_required", names)
        self.assertNotIn(".env", names)
        for attr in dir(protect_paths):
            value = getattr(protect_paths, attr)
            if attr.endswith("_SUFFIX") and isinstance(value, str) \
                    and value.startswith(".agents/state/gates/"):
                self.assertIn(value.rsplit("/", 1)[-1], names, attr)

    def test_safe_bash_redirect_reason_counts_the_paths_it_does_not_name(self):
        """T-00000698, correction — the deny reason names the first THREE refused
        paths and COUNTS the rest (`+N more`) instead of dropping them in silence:
        the Claude homologue lists every path, and a reason naming three of four
        read as "three refused" to the agent that must fix its command (exec-critic
        on b7055f0). Four tracked targets → three named, `+1 more`, the fourth NOT
        named. Named mutation: remove the whole `if len(redirect_unsafe) > 3:`
        block in safe_bash.py (the line alone leaves an empty `if`, a syntax
        error rather than a witness) → this test is the only red."""
        raison = self._safe_bash_deny_reason(
            "echo a > AGENTS.md; echo b > CLAUDE.md; echo c > GEMINI.md; echo d > README.md")
        self.assertIn("GEMINI.md (git-tracked, relative)", raison)
        self.assertIn(", +1 more)", raison)
        self.assertNotIn("README.md", raison)

    def test_safe_bash_redirect_strict_branch_announces_a_lost_protected_clause(self):
        """STRICT branch, said out loud (C1). When protect_paths cannot be read the
        protected-path clause is announced-off on stderr — never a silent exemption
        — while the git-tracked clause keeps guarding. A protected-ONLY target
        (`.mcp.json`, not tracked here) therefore passes in this degraded state, and
        a git-tracked one is still refused."""
        with mock.patch.object(safe_bash, "_protected_reason", None):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                allowed = not self._safe_bash_denies("echo x > .mcp.json")
            self.assertTrue(allowed, "protected clause must be off when protect_paths is unreadable")
            self.assertIn("COVERAGE DEGRADED", err.getvalue())
            # The git clause is independent of protect_paths and must survive.
            self.assertTrue(self._safe_bash_denies("echo x >> AGENTS.md"))

    # --- T-00000785: a path whose resolution fails, a command with no faithful
    # byte form ---------------------------------------------------------------
    # Before this task an embedded NUL made normalize_path() raise ValueError
    # (`lstat: embedded null character`, py3.14.7) out of the guards' main(),
    # before any refusal: rc 1 and no JSON on stdout. Pass 1 caught it and
    # refused the NUL; the exec-critic (S-00002872) showed the same catch
    # swallowed a lone surrogate (UnicodeEncodeError, a ValueError) that no
    # check refused, so `rm -rf tmp/../\ud800/../.agents` became a SILENT
    # ALLOW. Pass 2 refuses by CLASS: a candidate whose resolution failed,
    # whatever the cause, and a command with no faithful byte form. These arms
    # pin the property at each layer; the before-fix ladder is in the dev
    # report, not here.

    def test_normalize_path_returns_the_raw_text_on_a_nul_byte(self):
        """The plumbing: no raise, and the UNRESOLVED text back — which is why a
        caller that judges must refuse it itself."""
        self.assertEqual(_common.normalize_path("docs/a\x00b.md"), "docs/a\x00b.md")

    def test_normalize_path_checked_flags_a_failed_resolution_by_class(self):
        """The flag judge_targets and judge_redirect refuse on. A NUL and a lone
        surrogate both fail (ValueError, UnicodeEncodeError included); a path
        that resolves fine OUTSIDE the root does NOT — that branch carries the
        doctrine idiom `> /tmp/x`, and folding it into the class would refuse
        it. normalize_path is the same text without the flag."""
        for value in ("docs/a\x00b.md", "tmp/../\ud800/../.agents"):
            with self.subTest(failed=value):
                self.assertEqual(_common.normalize_path_checked(value), (value, False))
                self.assertEqual(_common.normalize_path(value), value)
        for value in ("docs/x.md", "/tmp/scratch"):
            with self.subTest(resolved=value):
                text, resolved = _common.normalize_path_checked(value)
                self.assertTrue(resolved)
                self.assertEqual(text, _common.normalize_path(value))
        self.assertEqual(_common.normalize_path_checked("docs/x.md"), ("docs/x.md", True))

    def test_normalize_path_checked_flags_any_resolution_exception(self):
        """Pass 3 (S-00002882): the catch named OSError and ValueError while the
        docstring promised ANY exception — and CPython 3.11/3.12 turn ELOOP into
        RuntimeError inside Path.resolve(strict=False), so a symlink loop an
        agent can create (`ln -s loop tmp/loop`) crashed safe_bash and
        protect_paths with rc 1 and no decision (measured, 3.11.16 and 3.12.14).
        The class is closed with `except Exception`. This arm pins it on ANY
        interpreter — the CI runs 3.14, where resolve no longer raises on a loop
        — by making resolve raise each known member. No byte rule stands in
        front of a loop, so the refusal reaches main() for real (R4 clause)."""
        for exc in (RuntimeError("Symlink loop"), OSError(40, "ELOOP"), ValueError("x")):
            with self.subTest(exc=type(exc).__name__), \
                    mock.patch.object(_common.Path, "resolve", side_effect=exc):
                self.assertEqual(
                    _common.normalize_path_checked("tmp/loop/x"), ("tmp/loop/x", False)
                )
                self.assertEqual(
                    safe_bash.judge_targets("rm -rf tmp/loop/x", 0, True, False),
                    (["tmp/loop/x"], ""),
                )
                with mock.patch.object(safe_bash, "emit_event"):
                    reason = self._safe_bash_deny_reason("rm -rf tmp/loop/x")
                self.assertIn("An operand could not be resolved", reason)
                self.assertNotIn("tracked or outside", reason)

    def test_protect_paths_denies_a_lone_surrogate_path(self):
        """The other member of the class (S-00002872): a lone surrogate fails
        the physical resolution too — refused as unstable, never allowed in
        silence."""
        body = invoke(
            protect_paths,
            {"tool_name": "apply_patch", "tool_input": {"file_path": "docs/a\ud800b.md"}},
        )
        self.assertIsNotNone(body, "a surrogate path must be refused, never allowed in silence")
        out = body["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], protect_paths.FORMES_INSTABLES_DENY_REASON)

    def test_protect_paths_denies_a_lone_nul_path(self):
        """A NUL path is refused as unstable (canonical_forms catches the
        ValueError of the physical resolution), never a crash."""
        body = invoke(
            protect_paths,
            {"tool_name": "apply_patch", "tool_input": {"file_path": "docs/a\x00b.md"}},
        )
        self.assertIsNotNone(body, "a NUL path must be refused, never allowed in silence")
        out = body["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], protect_paths.FORMES_INSTABLES_DENY_REASON)

    def test_protect_paths_nul_path_cannot_mask_a_neighbour_marker(self):
        """paths_from_payload normalizes EVERY path before main() judges one, so
        a NUL anywhere in the patch crashed the hook before the arming marker
        beside it was read. Both orders are refused now, each for its own reason."""
        marker = ".agents/state/gates/KICKOFF_REQUIRED"
        marker_reason = protect_paths.protected_reason(marker)[0]
        self.assertTrue(marker_reason, "the marker must be protected on its own")
        for first, second, reason in (
            ("docs/a\x00b.md", marker, protect_paths.FORMES_INSTABLES_DENY_REASON),
            (marker, "docs/a\x00b.md", marker_reason),
        ):
            patch = (
                f"*** Begin Patch\n*** Update File: {first}\n*** End Patch\n"
                f"*** Begin Patch\n*** Add File: {second}\n*** End Patch"
            )
            with self.subTest(first=first):
                body = invoke(
                    protect_paths, {"tool_name": "apply_patch", "tool_input": {"command": patch}}
                )
                self.assertIsNotNone(body)
                out = body["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny")
                self.assertEqual(out["permissionDecisionReason"], reason)

    def test_safe_bash_judge_targets_unresolvable_operand_is_refused(self):
        """Defence BY FUNCTION: when the resolution fails normalize_path hands
        back the unresolved text, which starts with an allowlisted prefix
        (`tmp/`, `dist/`) — so without its own refusal judge_targets compared a
        path no shell receives against the allowlist. Pass 1 refused the NUL
        only; the three lone-surrogate forms were a SILENT ALLOW on both hosts
        (S-00002872). Called DIRECTLY: main() refuses these commands first
        (R2), so no payload reaches this clause through main(). The last arm
        is the non-vacuity: the allowlist still applies to a target that
        resolves."""
        for command, refused in (
            ("rm -rf tmp/../.agents\x00", "tmp/../.agents\x00"),
            ("rm tmp/..\x00/AGENTS.md", "tmp/..\x00/AGENTS.md"),
            ("rm -rf dist/../.git\x00", "dist/../.git\x00"),
            ("mv tmp/../AGENTS.md\x00 tmp/y", "tmp/../AGENTS.md\x00"),
            ("rm -rf tmp/x\x00", "tmp/x\x00"),
            ("rm -rf tmp/../\ud800/../.agents", "tmp/../\ud800/../.agents"),
            ("rm -rf dist/../\ud800/../.git", "dist/../\ud800/../.git"),
            ("mv tmp/../\ud800/../AGENTS.md tmp/y", "tmp/../\ud800/../AGENTS.md"),
        ):
            with self.subTest(command=command):
                unsafe, why = safe_bash.judge_targets(command, 0, True, False)
                self.assertEqual(unsafe, [refused])
                self.assertEqual(why, "")
        self.assertEqual(safe_bash.judge_targets("rm -rf tmp/x", 0, True, False), ([], ""))

    def test_safe_bash_unresolvable_redirect_target_is_refused_on_strict_branch(self):
        """Defence BY FUNCTION, the leak measured during replanning: on the
        STRICT branch (protect_paths unreadable) an unresolvable target was not
        git-tracked (git refuses the argv, git_tracked answers False) and no
        protected clause was there to catch it — ("pass", None), for a lone
        surrogate still after pass 1 (S-00002872). Refused on its own rule now,
        before either clause, on both branches. Called DIRECTLY (R2)."""
        for target in ("tmp/../AGENTS.md\x00", "tmp/../AGENTS.md\ud800"):
            with self.subTest(target=target):
                with mock.patch.object(safe_bash, "_protected_reason", None):
                    self.assertEqual(
                        safe_bash.judge_redirect(target), ("protected", "unresolvable-path")
                    )
                self.assertEqual(
                    safe_bash.judge_redirect(target), ("protected", "unresolvable-path")
                )

    def test_safe_bash_redirect_reason_names_an_unresolvable_target(self):
        """Pass 4 (C2): a redirect target refused because its resolution failed
        is not "a tracked or protected file" — the lead of the reason says
        UNRESOLVABLE as soon as one refused target carries that rule, and keeps
        the guard's own motive ("redirects a write"). Stubbed resolution: main()
        refuses a NUL or surrogate command first (R2), and a symlink loop only
        fails to resolve on CPython <=3.12, not on the CI interpreter. The last
        assertion is the non-vacuity: an ordinary refusal keeps the old lead."""
        stub = ("tmp/y", False)
        with mock.patch.object(safe_bash, "normalize_path_checked", return_value=stub), \
                mock.patch.object(safe_bash, "emit_event"):
            reason = self._safe_bash_deny_reason("echo x > tmp/y")
        self.assertIn("redirects a write", reason)
        self.assertIn("UNRESOLVABLE", reason)
        self.assertIn("tmp/y (unresolvable-path, relative)", reason)
        self.assertNotIn("a tracked or protected file", reason)
        self.assertIn("a tracked or protected file", self._safe_bash_deny_reason("echo x >> AGENTS.md"))

    def test_safe_bash_refuses_a_command_with_no_faithful_byte_form(self):
        """R2, widened by pass 2: a NUL (an argv string ends at it) or a lone
        surrogate (no UTF-8 form) anywhere — verb, envelope, operand, redirect
        target — makes the text judged differ from what a shell would run, so
        the whole command is refused first, under its own rule. The class is
        closed: strict UTF-8 refuses exactly the lone surrogates, and NUL is
        the one encodable code point no argv carries. The reason never echoes
        the command (L-00000043). The ALLOW arms are the non-vacuity: the
        escape `\\0` is text, and a non-ASCII command that HAS a UTF-8 form
        passes."""
        for command in (
            "r\x00m -rf .agents",
            "rm\x00 -rf .agents",
            "sud\x00o rm -rf .agents",
            "rm -rf tmp/../.agents\x00",
            "echo x > tmp/../AGENTS.md\x00",
            "rm -rf tmp/../\ud800/../.agents",
            "rm -rf dist/../\ud800/../.git",
            "mv tmp/../\ud800/../AGENTS.md tmp/y",
            "echo x > tmp/../AGENTS.md\ud800",
            "rm -rf x\x00\ud800",
        ):
            with self.subTest(deny=command), mock.patch.object(safe_bash, "emit_event") as emitted:
                reason = self._safe_bash_deny_reason(command)
                self.assertIn("no faithful byte form", reason)
                self.assertNotIn("\x00", reason)
                self.assertNotIn("\ud800", reason)
                emitted.assert_called_once()
                self.assertEqual(emitted.call_args.kwargs["rule"], "unrepresentable-command")
        for command in ("printf 'a\\0b' > /tmp/scratch", "echo é > /tmp/scratch", "rm -rf tmp/x"):
            with self.subTest(allow=command):
                self.assertFalse(self._safe_bash_denies(command))

    def test_safe_bash_refusal_of_a_surrogate_command_exits_zero(self):
        """Item 2 of the exec-critic (S-00002872): command_fingerprint encoded
        strict UTF-8 AFTER deny() was printed, so a lone surrogate produced a
        deny body AND rc 1. Run as a SUBPROCESS on the file beside this suite:
        the process exit is the property, and a subprocess is immune to the
        module aliasing of a combined pytest run."""
        script = Path(__file__).resolve().parent / "safe_bash.py"
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf x\x00\ud800"}})
        result = subprocess.run(
            [sys.executable, "-B", str(script)], input=payload.encode("ascii"),
            capture_output=True, cwd=str(script.parents[2]), timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-400:])
        body = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_safe_bash_fingerprint_is_total_and_unchanged_on_encodable_commands(self):
        """surrogatepass, not a lossy handler: byte-identical to strict UTF-8 for
        every command that HAS a UTF-8 form (so no digest already emitted
        moves), and injective on the rest — a lone surrogate does not collide
        with the TEXT `\\ud800`, which backslashreplace would produce."""
        plain = "rm -rf src/x && echo é"
        self.assertEqual(
            safe_bash.command_fingerprint(plain),
            (hashlib.sha256(plain.encode("utf-8")).hexdigest(), len(plain)),
        )
        digest, length = safe_bash.command_fingerprint("rm \ud800")
        self.assertEqual(length, 4)
        self.assertNotEqual(digest, safe_bash.command_fingerprint("rm \\ud800")[0])

    def test_safe_bash_rm_refusal_names_an_unresolvable_operand_as_such(self):
        """R4: an operand refused because its resolution failed is not "tracked
        or outside this host's disposable directories" — `tmp/x\\x00` is inside
        one. The rm/mv block says so and names only the others; since pass 2
        the split follows the CLASS (a lone surrogate too), not the NUL alone.
        Reached through a stubbed judge_targets because main() refuses these
        commands before any judge (R2)."""
        stub = (["tmp/x\x00", "tmp/\ud800", "src/a.py"], "")
        with mock.patch.object(safe_bash, "judge_targets", return_value=stub):
            reason = self._safe_bash_deny_reason("rm tmp/x")
        self.assertIn("An operand could not be resolved", reason)
        self.assertIn("disposable directories: src/a.py.", reason)
        self.assertNotIn("\x00", reason)
        self.assertNotIn("\ud800", reason)
        with mock.patch.object(safe_bash, "judge_targets", return_value=(["tmp/\ud800"], "")):
            reason = self._safe_bash_deny_reason("rm tmp/x")
        self.assertIn("An operand could not be resolved", reason)
        self.assertNotIn("tracked or outside", reason)

    def test_audit_gate_gates_every_runner_form(self):
        """`yarn dlx` and `bunx` were not gated on this host at all, and `pnpm dlx`
        was gated WITHOUT its options — `pnpm dlx -y skills add x` walked past the
        gate. The negative arms are the anchor's non-vacuity: a mention mid-sentence
        is not an installation, and an audited ref still passes."""
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            for command in (
                "bunx skills add other/pkg",
                "bunx --bun skills add other/pkg",
                "bunx.cmd skills add other/pkg",
                "yarn dlx skills add other/pkg",
                "yarn dlx --quiet skills add other/pkg",
                "pnpm dlx skills add other/pkg",
                "pnpm dlx -y skills add other/pkg",
                "npm exec skills add other/pkg",
                "skills add other/pkg",
                "skills.cmd add other/pkg",
                "echo hi && skills add other/pkg",
                "npx skills add other/pkg&&echo done",
                # T-00000240 — a runner or the global CLI QUALIFIED BY A PATH. The
                # python hosts already refused the RUNNER forms via `\b`; P5/P6/P12
                # are the global-CLI-behind-a-path forms this task adds.
                "/usr/local/bin/npx skills add other/pkg",        # P1
                "./node_modules/.bin/npx skills add other/pkg",   # P2: the natural JS form
                "/usr/bin/pnpm dlx skills add other/pkg",         # P3
                "C:\\tools\\npx.cmd skills add other/pkg",         # P4: backslash already a boundary
                "/usr/local/bin/skills add other/pkg",            # P5: THE HOLE — global CLI by path
                "C:\\tools\\skills.cmd add other/pkg",             # P6: global CLI by backslash path
                "my-npx skills add other/pkg",                    # P7: `-` is a left boundary
                "a\vb/skills add other/pkg",                      # P12: VT admitted in the prefix
                # T-00000256 — the two NAMED holes, now CLOSED by widening the
                # position of command past a bare `skills` (see the mutant below).
                '"/opt/tools/skills" add other/pkg',              # P8: quoted CLI -> ` @@ add`
                "FOO=1 skills add other/pkg",                     # P9: assignment prefix
                'FOO="x y" skills add other/pkg',                 # P9: quoted value scrubs to @@
            ):
                with self.subTest(denied=command):
                    self.assertTrue(self._audit_gate_arm(command), command)
            for command in (
                "we should discuss skills add later",
                "skills add owner/pkg",
                "yarn dlx skills add owner/pkg",
                "bunx skills add owner/pkg",
                'python .agents/bin/tasks.py new "skills"',
                # T-00000256 — the widening stays ANCHORED to the position of
                # command; outside it, neither `@@` nor an assignment fires.
                'echo "hi" skills add other/pkg',                 # quoted arg -> `echo @@ skills`, not cmd pos
                "we discuss FOO=1 skills add later",              # assignment mid-sentence
                "/usr/local/bin/skills add owner/pkg",            # P11: path CLI, ref IS audited
            ):
                with self.subTest(allowed=command):
                    self.assertFalse(self._audit_gate_arm(command), command)

    def test_audit_gate_path_prefix_is_the_lone_newline_pattern_and_gates_paths(self):
        """T-00000240 — THE PATH-PREFIX MUTANT, selected BY PROPERTY. The prefix
        group that admits a path before the global `skills` CLI lives on THE ONE
        pattern whose source carries `\\n` (the global-CLI anchor, the only one
        joining the newline to its separator class). Uniqueness is ASSERTED, then
        the prefix group is REMOVED and P5/P6 flip from DENY to ALLOW — a non-match
        at the only anchor is exactly what makes main() let the install through.
        The mutation is proven APPLIED before its verdict counts (L-00000161): the
        un-mutated pattern gates the path, the mutated one does not."""
        carriers = [p for p in audit_gate.INSTALL_PATTERNS if r"\n" in p.pattern]
        self.assertEqual(len(carriers), 1, "exactly one pattern carries a newline in its source")
        pattern = carriers[0]
        prefix = r"(?:[^ \t;&|(`{\n]*[/\\])?"
        self.assertIn(prefix, pattern.pattern, "the path-prefix group must be present to remove")
        mutated = re.compile(pattern.pattern.replace(prefix, ""), re.IGNORECASE)
        self.assertNotEqual(mutated.pattern, pattern.pattern, "mutation did not apply")
        for target in ("/usr/local/bin/skills add other/pkg", "C:\\tools\\skills.cmd add other/pkg"):
            with self.subTest(target=target):
                self.assertIsNotNone(pattern.search(target), "un-mutated must gate the path")
                self.assertIsNone(mutated.search(target), "removing the prefix flips P5/P6 to ALLOW")

    def test_quoted_spans_treats_an_escaped_quote_as_a_literal_character(self):
        """CLASS-1 REGRESSION GUARD (security review of T-00000151).

        `\\"` is a LITERAL quote in bash: it opens nothing. Reading it as a
        delimiter masked the whole interval between two of them — separator AND
        command — so a payload the shell really executes was allowed. Both guards
        carry the identical scanner, so both are asserted here.

        Every arm shows the payload AS THE SHELL SEES IT, because python's own
        escaping is the easiest thing to misread in a test about backslashes.
        """
        for module in (safe_bash, audit_gate):
            with self.subTest(module=module.__name__):
                # echo \" ; rm -rf src/x \"   -> two LITERAL quotes, no segment
                self.assertEqual(module.quoted_spans('echo \\" ; rm -rf src/x \\"'), [])
                # echo \' ; rm -rf src/x \'   -> same, single-quote spelling
                self.assertEqual(module.quoted_spans("echo \\' ; rm -rf src/x \\'"), [])
                # echo \\" ; rm -rf src/x \\"  -> EVEN backslashes: a REAL segment
                self.assertEqual(len(module.quoted_spans('echo \\\\" ; rm -rf src/x \\\\"')), 1)
                # x "a 'b' c" y -> leftmost opening quote wins, one span
                self.assertEqual(module.quoted_spans("""x "a 'b' c" y"""), [(2, 11)])
                # echo l'index -> unpaired, closes nothing
                self.assertEqual(module.quoted_spans("echo l'index"), [])
                # 'a\' -> single quotes honour NO escape in bash: a\ is the content
                self.assertEqual(module.quoted_spans("'a\\'"), [(0, 4)])

    def test_safe_bash_an_escaped_quote_cannot_mask_a_destructive_command(self):
        """The PoC, verbatim: bash runs `rm -rf src/onepoint` here, and this guard
        used to say nothing. Worse, it was a REGRESSION — the naive segment split
        this stage replaced refused the same line, because it never tried to
        understand quoting at all."""
        # echo \" ; rm -rf src/onepoint  \"
        self.assertTrue(self._safe_bash_denies('echo \\" ; rm -rf src/onepoint  \\"'))
        # echo \' ; rm -rf src/x \'
        self.assertTrue(self._safe_bash_denies("echo \\' ; rm -rf src/x \\'"))
        # rm -rf \"src/x\"  -> escaped quotes around the target change nothing
        self.assertTrue(self._safe_bash_denies('rm -rf \\"src/x\\"'))
        # echo \\" ; rm -rf src/x \\"  -> EVEN backslashes: a genuine quoted
        # string, so bash executes nothing and allowing it is CORRECT. This arm is
        # what forbids the lazy fix of ignoring backslashes altogether.
        self.assertFalse(self._safe_bash_denies('echo \\\\" ; rm -rf src/x \\\\"'))
        # And the guard now SEES the command rather than masking it: the same line
        # with an allowlisted target passes on its TARGET, not on a blind spot.
        self.assertFalse(self._safe_bash_denies('echo \\" ; rm -rf .tmp/x \\"'))

    def test_safe_bash_a_quoted_heredoc_delimiter_makes_its_body_data(self):
        """Stage 0.5 (T-00000211), and the founding incident MEASURED rather than
        recalled: before this port both python hosts REFUSED a `git commit -F -`
        whose message described a guarded command, while the Claude host — which
        has carried the stage since T-00000210 — allowed it. A heredoc body is not
        QUOTED, it is REDIRECTED, so stage 1 could never reach it.

        The four delimiter forms below are the ones the piece parser recognises:
        bash concatenates the pieces and strips the quotes, so `<<'MSG'`,
        `<<\\EOF`, `<<E"O"F` and `<<'A'B` all yield a body that is 100% literal.
        """
        forms = {
            "git commit -F - <<'MSG'": "MSG",
            "cat <<\\EOF > notes.md": "EOF",
            'cat <<E"O"F > notes.md': "EOF",
            "cat <<'A'B > notes.md": "AB",
        }
        for opener, closer in forms.items():
            command = "\n".join([opener, "rm -rf src/x est desormais refuse", closer])
            with self.subTest(opener=opener):
                self.assertFalse(self._safe_bash_denies(command), command)

    def test_safe_bash_heredoc_polarity_and_boundaries_stay_fail_closed(self):
        """The counterweights, one per property the stage would lose if it were
        "simplified". Each of these must still DENY: blanking any of them is a
        fail-open, and a stage that only ever allows is not a stage.

        POLARITY is the first row and the load-bearing one: with a NAKED
        delimiter bash EXPANDS `$(…)` inside the body, so that body is code and
        must stay analysed. FAIL-CLOSED is the second group: a delimiter the
        parser cannot read (a space, hence outside `[A-Za-z0-9_]`) leaves its body
        analysed rather than blanking it on a guess. The rest pin the boundaries —
        the introduction line is code, the closing line ends the body, a QUOTED
        MENTION of an opener opens nothing, and a herestring `<<<` is not a
        heredoc (the parser is anchored on the FIRST candidate with no retry,
        which is exactly what keeps that hole shut).
        """
        charges = {
            # POLARITY: a naked delimiter expands, so the body really executes.
            "naked-delimiter-expands": ["cat <<EOF > f", "$(rm -rf src/x)", "EOF"],
            # FAIL-CLOSED: `E F` carries a space, so no delimiter is recognised.
            "unreadable-delimiter": ["cat <<'E F' > f", "rm -rf src/x", "E F"],
            # The introduction line is CODE, whatever it opens behind it.
            "intro-line-is-code": ["rm -rf src/x <<'EOF'", "donnee", "EOF"],
            # After the closing delimiter we are code again.
            "code-after-the-closer": ["cat <<'EOF' > f", "donnee", "EOF", "rm -rf src/x"],
            # A quoted MENTION opens no body — and the arm is multi-line on
            # purpose: written on one line there would be nothing left to blank,
            # so it would pass without measuring anything.
            "quoted-mention-opens-nothing": [
                "python .agents/bin/tasks.py new \"documenter <<'EOF' dans le guide\"",
                "rm -rf src/x",
            ],
            # A herestring is not a heredoc.
            "herestring-is-not-a-heredoc": ["cat <<<'X'", "rm -rf src/x"],
        }
        for label, lines in charges.items():
            command = "\n".join(lines)
            with self.subTest(charge=label):
                self.assertTrue(self._safe_bash_denies(command), command)

    def test_safe_bash_a_comment_cannot_whiten_code_on_another_line(self):
        """THE FIRST OF THE TWO LIVE BYPASSES CLOSED BY T-00000225, and it reached
        CODE rather than data. An unpaired apostrophe inside a `#` comment paired
        with a REAL quote further down and neutralised the whole interval — the
        `rm` included — while bash runs that `rm` for real. The prose this repo
        shipped claimed the residue lived "in a NON-CODE zone"; it was false.

        MEASURED against this hook before the fix, WITH its negative control, and
        the control is what makes the measurement mean anything: the payload with
        the comment came back ALLOW, the SAME payload without it came back DENY.
        A lone row asserting `deny` would pass just as well on a guard that
        refuses everything.
        """
        self.assertTrue(
            self._safe_bash_denies("# don't run this\nrm -rf src/x && echo 'ok'")
        )
        # NEGATIVE CONTROL 1, the twin of the charge above: the same command with
        # no comment line. Already denied BEFORE the fix, so it proves the arm
        # measures the COMMENT and not the rm.
        self.assertTrue(self._safe_bash_denies("rm -rf src/x && echo 'ok'"))
        # NEGATIVE CONTROL 2: the frontier must not degrade into a blanket refusal
        # of anything carrying a `#` — an allowlisted target still passes, so the
        # guard still decides on the TARGET.
        self.assertFalse(
            self._safe_bash_denies("# don't run this\nrm -rf .tmp/x && echo 'ok'")
        )
        # NON-ERASURE (D2), and the reason the clause EXCLUDES from pairing rather
        # than BLANKING: inside a NAKED-delimiter heredoc body bash expands
        # `$(…)`, so that body is CODE. Erasing its `#` lines would be a
        # fail-open, and this is the arm that kills the mutant which does it.
        self.assertTrue(
            self._safe_bash_denies("cat <<MSG > f\n# note\nrm -rf src/x\nMSG")
        )
        # THE EXCEPTIONS THE REUSED CLAUSE CARRIES: a `#` that is not in
        # word-initial position opens no comment, so `$#` and `${#v}` stay
        # expansions. A frontier written a SECOND time is exactly what drops these.
        self.assertTrue(self._safe_bash_denies("echo $# && rm -rf src/x"))
        self.assertTrue(self._safe_bash_denies("echo ${#v} && rm -rf src/x"))

    def test_audit_gate_a_comment_cannot_whiten_an_installation(self):
        """The SAME bypass on the OTHER guard, where it cost an UNAUDITED INSTALL
        rather than a checkpoint: `# don't install this` ⏎ `npx skills add
        other/pkg && echo 'ok'` came back ALLOW before T-00000225.

        This arm measures the COMPOSITION, not the copy. The frontier reuses a
        clause that only reached this file WITH the heredoc stage, and this
        guard's environment is not safe_bash.py's: its scrub is NOT isometric (it
        emits ` @@ `) and its last install pattern crosses lines. What holds over
        there is not acquired here, so it is measured here.
        """
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            self.assertTrue(self._audit_gate_arm(
                "# don't install this\nnpx skills add other/pkg && echo 'ok'"
            ))
            # NEGATIVE CONTROL 1: same install, no comment. Denied before AND
            # after, so the arm above measures the comment.
            self.assertTrue(
                self._audit_gate_arm("npx skills add other/pkg && echo 'ok'")
            )
            # NEGATIVE CONTROL 2: an AUDITED ref still passes, so the frontier has
            # not become "refuse anything containing a `#`".
            self.assertFalse(self._audit_gate_arm(
                "# don't install this\nnpx skills add owner/pkg && echo 'ok'"
            ))
            # NON-ERASURE (D2): a `#` line inside a NAKED body is code, and the
            # install behind it is still seen.
            self.assertTrue(self._audit_gate_arm(
                "cat <<MSG > f\n# note\nnpx skills add other/pkg\nMSG"
            ))

    def test_audit_gate_a_quoted_heredoc_delimiter_makes_its_body_data(self):
        """CRITICAL n°2 on THIS guard. It was closed on the Claude host by
        T-00000208 and on safe_bash.py by T-00000211; audit_gate.py never had the
        stage at all, which is what T-00000225 repairs — an asymmetry that made
        the Claude guards strictly safer than the three python hosts'.

        TWO THINGS ARE PINNED AND THEY PULL IN OPPOSITE DIRECTIONS, which is why
        neither alone would do: a quoted-delimiter body is DATA (a commit message
        may describe an install without being one), AND an apostrophe living in
        such a body must no longer pair with a real quote further down to whiten a
        GENUINE install — the fail-open measured ALLOW here before the port.
        """
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            # The apostrophe of `it's` used to pair with the `'` of `'ok'` two
            # lines down and neutralise the install standing between them.
            self.assertTrue(self._audit_gate_arm(
                "git commit -F - <<'MSG'\nit's fine\nMSG\n"
                "npx skills add other/pkg && echo 'ok'"
            ))
            # NEGATIVE CONTROL, the twin: the same install with no heredoc in
            # front. Denied before AND after, so the row above measures the stage.
            self.assertTrue(
                self._audit_gate_arm("npx skills add other/pkg && echo 'ok'")
            )
            # THE OTHER DIRECTION: a body that merely TALKS about an install is
            # DATA. Refused before the port (a false positive on pure data),
            # allowed now — on all four delimiter forms the piece parser knows,
            # because bash concatenates the pieces and strips the quotes.
            forms = {
                "git commit -F - <<'MSG'": "MSG",
                "cat <<\\EOF > notes.md": "EOF",
                'cat <<E"O"F > notes.md': "EOF",
                "cat <<'A'B > notes.md": "AB",
            }
            for opener, closer in forms.items():
                command = "\n".join(
                    [opener, "npx skills add other/pkg dans la doc", closer]
                )
                with self.subTest(opener=opener):
                    self.assertFalse(self._audit_gate_arm(command), command)

    def test_audit_gate_heredoc_polarity_and_boundaries_stay_fail_closed(self):
        """The counterweights, one per property the stage would lose if it were
        "simplified". Each must still DENY: a stage that only ever allows is not a
        stage, it is a hole with documentation.

        POLARITY is the first row and the load-bearing one — with a NAKED
        delimiter bash EXPANDS `$(…)` inside the body, so that body is code and
        must stay ANALYSED. The last row is this file's OWN, absent from the
        safe_bash twin: it pins the LINE COUNT, because the bare `skills add`
        pattern anchors on a separator class that includes `\\n`.
        """
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            charges = {
                # POLARITY: a naked delimiter expands, so the body really runs.
                "naked-delimiter-expands": [
                    "cat <<MSG > f", "npx skills add other/pkg", "MSG",
                ],
                # FAIL-CLOSED: `E F` carries a space, so no delimiter is read.
                "unreadable-delimiter": [
                    "cat <<'E F' > f", "npx skills add other/pkg", "E F",
                ],
                # The introduction line is CODE, whatever it opens behind it.
                "intro-line-is-code": [
                    "npx skills add other/pkg <<'EOF'", "donnee", "EOF",
                ],
                # After the closing delimiter we are code again.
                "code-after-the-closer": [
                    "cat <<'EOF' > f", "donnee", "EOF", "npx skills add other/pkg",
                ],
                # A quoted MENTION of an opener opens no body — multi-line on
                # purpose, or there would be nothing left to blank and the row
                # would pass without measuring anything.
                "quoted-mention-opens-nothing": [
                    "python .agents/bin/tasks.py new \"documenter <<'EOF' dans le guide\"",
                    "npx skills add other/pkg",
                ],
                # A herestring is not a heredoc (anchored on the FIRST candidate,
                # no retry — the retry is what reopens this hole).
                "herestring-is-not-a-heredoc": [
                    "cat <<<'X'", "npx skills add other/pkg",
                ],
                # LINE COUNT, and it is specific to THIS caller: the bare
                # `skills add` pattern anchors on `[;&|(`{\\n]`, so a body blanked
                # to FEWER lines would move that anchor and lose the install.
                # Blanking to EMPTY lines is what keeps this one refused.
                "bare-skills-add-after-a-blanked-body": [
                    "cat <<'EOF' > f", "donnee", "EOF", "skills add other/pkg",
                ],
            }
            for label, lines in charges.items():
                command = "\n".join(lines)
                with self.subTest(charge=label):
                    self.assertTrue(self._audit_gate_arm(command), command)

    def test_audit_gate_an_escaped_quote_cannot_mask_an_installation(self):
        """The second PoC: an unaudited skill installed past the AUDIT_LOG gate."""
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        with tempfile.TemporaryDirectory() as directory:
            audit_gate.GATES = Path(directory)
            (audit_gate.GATES / "AUDIT_LOG").write_text(
                "owner/pkg audit=pass\n", encoding="utf-8"
            )
            # echo \" && npx skills add unaudited/pkg \"
            self.assertTrue(
                self._audit_gate_arm('echo \\" && npx skills add unaudited/pkg \\"')
            )
            # echo \' && npx skills add unaudited/pkg \'
            self.assertTrue(
                self._audit_gate_arm("echo \\' && npx skills add unaudited/pkg \\'")
            )
            # The install is now SEEN, so an AUDITED one must still pass — the fix
            # must not turn into a blanket refusal of anything containing a backslash.
            self.assertFalse(
                self._audit_gate_arm('echo \\" && npx skills add owner/pkg \\"')
            )
            # EVEN backslashes: a genuine quoted mention, correctly allowed.
            self.assertFalse(
                self._audit_gate_arm('echo \\\\" && npx skills add unaudited/pkg \\\\"')
            )

    def test_audit_gate_ref_stops_at_the_first_shell_metacharacter(self):
        """Without the cut the ref reads `owner/pkg&&echo`, matches no AUDIT_LOG
        line, and the gate refuses an ALREADY AUDITED skill — the guard blocking
        exactly the install it exists to let through."""
        pattern = next(p for p in audit_gate.INSTALL_PATTERNS if "npx" in p.pattern)
        for command, expected in (
            ("npx skills add owner/pkg&&echo done", "owner/pkg"),
            ("npx skills add owner/pkg;ls", "owner/pkg"),
            ("npx skills add owner/pkg", "owner/pkg"),
        ):
            with self.subTest(command=command):
                self.assertEqual(audit_gate.install_ref(pattern.search(command)), expected)


if __name__ == "__main__":
    unittest.main()
