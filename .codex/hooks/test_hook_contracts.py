import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _common


ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_session_context():
    """Explicit-path load under a unique name so it never collides with the
    Gemini sibling of the same filename when both suites run together."""
    spec = importlib.util.spec_from_file_location(
        "_codex_session_context_under_test", ROOT / ".codex" / "hooks" / "session_context.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class HookContractTests(unittest.TestCase):
    def test_root_is_git_root_even_when_hook_imported_from_subdirectory(self):
        hook_dir = ROOT / ".codex" / "hooks"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(hook_dir)
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import _common; print(_common.ROOT)"],
            cwd=ROOT / "docs",
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(pathlib.Path(result.stdout.strip()).resolve(), ROOT.resolve())

    def test_apply_patch_command_payload_exposes_paths(self):
        payload = {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: src/legacy/demo.py\n*** End Patch"
            },
        }
        self.assertEqual(_common.paths_from_payload(payload), ["src/legacy/demo.py"])

    def test_copilot_local_filepath_payload_exposes_paths(self):
        """Le harness Local de VS Code passe `filePath` (T-01M4RWCAGQZKYQ9JS4C1JPBFVQ,
        S-01M4RWM3TC4JWE5FDC8YB819Z4) : sans cette cle, protect_paths ne voyait
        aucun chemin et laissait passer `.env.local`."""
        seul = {"toolName": "replace_string_in_file", "toolArgs": {"filePath": "src/a.py"}}
        self.assertEqual(_common.paths_from_payload(seul), ["src/a.py"])
        absolu = {"toolName": "replace_string_in_file",
                  "toolArgs": {"filePath": str(ROOT / ".env.local")}}
        self.assertEqual(_common.paths_from_payload(absolu), [".env.local"])
        les_deux = {"toolName": "create_file", "toolArgs": {"filePath": "a.py", "path": "b.py"}}
        self.assertEqual(_common.paths_from_payload(les_deux), ["a.py", "b.py"])

    # L'hote est EPINGLE (R4 du plan T-01M4RWBSR48YW8RPAV7TG6HKET) : depuis
    # T-01M4RWC0DBM6XC1PDQGEG4P79C, `deny` et `additional_context` emettent une
    # seconde forme sous AGENTS_HOOK_HOST=copilot. Un test qui lirait
    # l'environnement ambiant changerait de verdict selon l'hote qui le lance ;
    # la forme imbriquee seule reste le contrat des hotes NON copilot.
    @mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "codex"})
    def test_pre_tool_use_denial_uses_codex_envelope(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _common.deny("blocked")
        body = json.loads(output.getvalue())
        self.assertEqual(
            body,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "blocked",
                }
            },
        )

    @mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "codex"})
    def test_context_and_system_message_use_event_specific_outputs(self):
        context_output = io.StringIO()
        with contextlib.redirect_stdout(context_output):
            _common.additional_context("loaded", event_name="SessionStart")
        self.assertEqual(
            json.loads(context_output.getvalue()),
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "loaded",
                }
            },
        )

        system_output = io.StringIO()
        with contextlib.redirect_stdout(system_output):
            _common.system_message("stale")
        self.assertEqual(json.loads(system_output.getvalue()), {"systemMessage": "stale"})

    # T-01M4RWC0DBM6XC1PDQGEG4P79C (decision pilote S-01M4RWM3TC4JWE5FDC8YB819Z4) :
    # sous copilot, le corps porte EN PLUS, au premier niveau, ce que la CLI lit ;
    # `hookSpecificOutput` reste inchange, et l'egalite est EXACTE (une cle de
    # trop ou de moins rougit).
    @mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"})
    def test_copilot_denial_carries_both_forms(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _common.deny("blocked")
        self.assertEqual(
            output.getvalue(),
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
            '"permissionDecision":"deny","permissionDecisionReason":"blocked"},'
            '"permissionDecision":"deny","permissionDecisionReason":"blocked"}\n',
        )

    @mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"})
    def test_copilot_context_carries_both_forms_and_system_message_is_unchanged(self):
        for event_name in ("SessionStart", "PostToolUse"):
            with self.subTest(event=event_name):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    _common.additional_context("loaded", event_name=event_name)
                self.assertEqual(
                    json.loads(output.getvalue()),
                    {
                        "hookSpecificOutput": {
                            "hookEventName": event_name,
                            "additionalContext": "loaded",
                        },
                        "additionalContext": "loaded",
                    },
                )
        # Residu nomme du plan : un systemMessage n'a pas de champ Copilot.
        system_output = io.StringIO()
        with contextlib.redirect_stdout(system_output):
            _common.system_message("stale")
        self.assertEqual(json.loads(system_output.getvalue()), {"systemMessage": "stale"})

    def test_only_copilot_gets_the_second_form(self):
        """kimi, un marqueur inconnu et un marqueur ABSENT gardent la forme
        imbriquee seule : la seconde forme est reservee a l'hote qui la lit."""
        for value in ("kimi", "gemini", "nonsense", None):
            env = {k: v for k, v in os.environ.items() if k != "AGENTS_HOOK_HOST"}
            if value is not None:
                env["AGENTS_HOOK_HOST"] = value
            with self.subTest(host=value), mock.patch.dict(os.environ, env, clear=True):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    _common.deny("blocked")
                    _common.additional_context("loaded")
                bodies = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertEqual([sorted(b) for b in bodies], [["hookSpecificOutput"]] * 2)

    def test_hook_commands_anchor_to_git_root(self):
        hooks = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        handlers = [
            handler
            for groups in hooks["hooks"].values()
            for group in groups
            for handler in group["hooks"]
        ]
        commands = [handler["command"] for handler in handlers]
        self.assertTrue(
            commands
            and all("git rev-parse --show-toplevel" in command for command in commands)
        )
        windows_commands = [handler["commandWindows"] for handler in handlers]
        # 18 -> 19 et 11 -> 12 le 2026-09-21 (T-00000684) : le traceur de la
        # chaine de plan rejoint `SubagentStop` sur Codex. Ce compte est EPINGLE
        # pour qu'une jambe neuve ne puisse pas echapper au balayage en silence.
        # 19 -> 20 et 7 -> 8 le 2026-10-12 (alignement des hôtes, L-C) :
        # `affirmation-guard.sh` rejoint `Stop`.
        # 20 -> 21 et 12 -> 13 le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard sur Bash.
        self.assertEqual(len(windows_commands), 21)
        self.assertEqual(sum(" 'module' $r " in command for command in windows_commands), 13)
        self.assertEqual(sum(" 'bash' $r " in command for command in windows_commands), 8)
        for command in windows_commands:
            self.assertIn("git rev-parse --show-toplevel", command)
            self.assertIn("& ($r+'/.agents/pyrun.ps1')", command)
            self.assertRegex(command, r" '(?:module|bash)' \$r '\.[^']+\.(?:py|sh)'(?:;| |$)")
            self.assertNotIn("$(git rev-parse", command)
            self.assertNotIn("EncodedCommand", command)
            self.assertNotIn("Invoke-Expression", command)


def _tuer_groupe(pid):
    """Teardown of a detached bootstrap: its group dies, an already-gone one is fine."""
    try:
        if pid:
            os.killpg(pid, 9)
    except OSError:
        pass


class ProjectNudgeTests(unittest.TestCase):
    """T-00000048 (V1-a): SessionStart nudge when project.json is absent."""

    def _run_main(self, state_dir):
        sc = _load_session_context()
        sc.STATE = pathlib.Path(state_dir)
        sc.refresh_index_if_stale = lambda: None  # keep the test off the real indexer
        events_dir = pathlib.Path(state_dir) / "events"
        prev = os.environ.get("AGENTS_EVENTS_DIR")
        os.environ["AGENTS_EVENTS_DIR"] = str(events_dir)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                sc.main()
        finally:
            if prev is None:
                os.environ.pop("AGENTS_EVENTS_DIR", None)
            else:
                os.environ["AGENTS_EVENTS_DIR"] = prev
        return buf.getvalue()

    def test_status_line_present_when_project_json_absent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            out = self._run_main(d)
        self.assertIn("[PROJECT STATUS] projet sans nom", out)
        self.assertIn("project_init.py", out)

    def test_status_line_absent_when_project_json_present(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            (pathlib.Path(d) / "project.json").write_text('{"project_id": "x"}', encoding="utf-8")
            out = self._run_main(d)
        self.assertNotIn("[PROJECT STATUS]", out)

    def test_main_never_raises(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            self._run_main(d)  # a raise here fails the test

    @unittest.skipIf(sys.platform == "win32", "flock absent : amorçage non lancé (dit)")
    def test_bootstrap_launched_line_on_adopter_root(self):
        """T-00001103 lot C : sur une racine d'adoptant (STATE sous ROOT, faux setup), main()
        LANCE l'amorçage détaché et porte sa ligne ; la ligne `projet sans nom` se tait pendant
        le run (D1 R7 : l'amorçage écrit project.json lui-même)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            racine = pathlib.Path(d).resolve()
            (racine / ".agents" / "bin").mkdir(parents=True)
            (racine / ".git").mkdir()
            (racine / ".agents" / "bin" / "setup_projet.py").write_text("raise SystemExit(0)\n")
            sc = _load_session_context()
            sc.ROOT, sc.STATE = racine, racine / ".agents" / "state"
            sc.refresh_index_if_stale = lambda: None
            env = {k: v for k, v in os.environ.items() if k not in ("CI", "CADRE_AMORCAGE")}
            env["AGENTS_EVENTS_DIR"] = str(racine / "events")
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
                sc.main()
            etat = racine / ".agents" / "state" / "local" / "amorcage.json"
            pid = json.loads(etat.read_text(encoding="utf-8")).get("pid")
            self.addCleanup(_tuer_groupe, pid)
        out = json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[PROJECT STATUS] amorçage lancé en arrière-plan", out)
        self.assertNotIn("[PROJECT STATUS] projet sans nom", out)


# T-00000120 — le hook sous test et son etiquette d'hote. Le chemin est explicite
# et le nom de module unique : les deux hotes portent un `stale_index.py` et les
# deux suites peuvent tourner dans le meme interpreteur.
HOOK_PATH = pathlib.Path(__file__).resolve().parent / "stale_index.py"
HOST_TAG = "codex"


class StaleIndexDbProbeTests(unittest.TestCase):
    """T-00000120 — la peremption de la base SQLite est DITE sur cet hote aussi.

    LE TROU, MESURE : ce hook comparait des mtimes et n'invoquait JAMAIS
    `build_index.py --stale-check`. La peremption de l'`index.db` committee etait
    donc annoncee sur Claude (stop-reindex.sh) et NULLE PART ailleurs, alors que
    les quatre hotes lisent le meme depot et la meme base. Couverture de ce hook
    avant cette classe : neant — aucune des deux suites ne le mentionnait.

    Les trois arms couvrent les trois etats qui comptent : la sonde parle, la
    sonde tombe, et le rappel mtime existant ne bouge pas.
    """

    def _load_hook(self):
        spec = importlib.util.spec_from_file_location(
            "_stale_index_under_test_%s" % HOST_TAG, HOOK_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _load_hook_on_a_fixture_index(self):
        """Le meme hook, mais dont l'INDEX est une FIXTURE — et c'est ce qui rend
        ces arms deterministes.

        LA DEPENDANCE CACHEE, MESUREE : ces arms bouchonnent deja tout, sauf UNE
        chose. `main()` sort en avance quand `INDEX/"SYMBOLS.md"` est absent
        (`stale_index.py:76-89`), donc ils dependaient en silence de l'etat de CE
        depot — et rougissaient chez un projet adoptant, qui recoit la branche
        d'adoption sans `.agents/state/` (`strip:`). `main()` lisant le global au
        moment de l'appel (`:76`), rebinder `mod.INDEX` sur un repertoire portant
        un `SYMBOLS.md` bidon suffit a franchir la sortie anticipee.

        `mod.ROOT` RESTE REEL, ET CE N'EST PAS UN OUBLI. Le rebinder ferait
        passer `db_stale_lines()` par `if not builder.exists(): return []`
        (`:55-57`) : ces arms deviendraient verts SANS JAMAIS APPELER LA SONDE.
        Un vert par vacuite est exactement l'inverse de ce que cette classe
        mesure — d'ou le compteur d'appels de l'arm de degradation.
        """
        mod = self._load_hook()
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        index = pathlib.Path(tmp.name)
        (index / "SYMBOLS.md").write_text("# SYMBOLS (fixture)\n", encoding="utf-8")
        mod.INDEX = index
        return mod

    def _capture(self, mod):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        return buf.getvalue()

    def test_a_stale_db_is_announced_with_the_resync_command(self):
        """La sonde imprime une ligne `DB STALE @ ...` -> un systemMessage qui
        NOMME la commande de remise en phase.

        Un rappel qui dit qu'il y a un probleme sans dire quoi taper coute une
        recherche a chacun de ceux qui le lisent.
        """
        mod = self._load_hook_on_a_fixture_index()
        mod.read_payload = lambda: {}
        mod.newest_source_mtime = lambda: 0.0
        mod.db_stale_lines = lambda: ["DB STALE @ deadbee vs files @ cafe123"]
        events = []
        mod.emit_event = lambda name, **kw: events.append((name, kw))
        out = self._capture(mod)
        self.assertIn("DB STALE @ deadbee", out)
        self.assertIn("migrate_index_to_db.py --resync", out)
        self.assertEqual([("index.stale",)], [(n,) for n, _ in events])
        self.assertIn("deadbee", events[0][1]["reason"])

    def test_a_probe_that_fails_degrades_to_SILENCE_and_never_raises(self):
        """LE CONTROLE QUI TIENT LA POLARITE. La sonde est consultative : builder
        absent, code de retour non nul, timeout, exception — tout doit se taire.
        Un hook qui hurle parce qu'un sous-processus a echoue transforme un
        rappel en panne, et il le fait a chaque tour de session.
        """
        mod = self._load_hook_on_a_fixture_index()
        mod.read_payload = lambda: {}
        mod.newest_source_mtime = lambda: 0.0
        events = []
        mod.emit_event = lambda name, **kw: events.append((name, kw))
        calls = []

        def explode(*_a, **_k):
            calls.append(1)
            raise OSError("no builder here")

        with mock.patch.object(mod.subprocess, "run", explode):
            out = self._capture(mod)
        self.assertEqual("", out.strip())
        self.assertEqual([], events)
        # NON-VACUITE, et elle est le coeur de cet arm : le silence ci-dessus ne
        # vaut que si la sonde a REELLEMENT ete appelee. Sans ce compteur, un
        # `main()` qui sortirait avant la sonde — index absent, ou `mod.ROOT`
        # rebinde par erreur — rendrait ces trois assertions vertes en ne
        # mesurant plus rien.
        self.assertEqual(1, len(calls), "la sonde n a jamais ete appelee — vert par vacuite")

    def test_the_existing_mtime_reminder_is_untouched(self):
        """NON-REGRESSION, et non-vacuite de l'arm precedent : si le rappel mtime
        avait disparu, les deux arms ci-dessus resteraient verts en mesurant un
        hook devenu muet."""
        mod = self._load_hook_on_a_fixture_index()
        mod.read_payload = lambda: {}
        mod.newest_source_mtime = lambda: 2 ** 40  # plus recent que tout
        mod.db_stale_lines = lambda: []
        events = []
        mod.emit_event = lambda name, **kw: events.append((name, kw))
        out = self._capture(mod)
        self.assertIn("source or agent files are newer", out)
        self.assertNotIn("DB STALE", out)
        self.assertEqual(1, len(events))

    def test_the_probe_timeout_is_bounded_and_short(self):
        """8 secondes, pas 30. Ce hook tourne devant l'utilisateur : une sonde
        consultative qui fait attendre une demi-minute a deja coute plus qu'elle
        ne rapporte. La borne est asserted parce qu'elle est un choix, pas un
        detail — un futur passage a 30 s doit affronter ce test."""
        mod = self._load_hook()
        self.assertLessEqual(mod.PROBE_TIMEOUT_SECONDS, 8)
        self.assertGreater(mod.PROBE_TIMEOUT_SECONDS, 0)


if __name__ == "__main__":
    unittest.main()
