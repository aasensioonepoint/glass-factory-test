"""Wiring of iac_guard on the five hook registries (T-01M52X1W3WPKCWX1DC36NMKJB6, C2.1).

1. STATIC — each registry carries exactly ONE iac_guard leg, in its shell stage, right
   after the safe_bash leg: a copy of that leg, target replaced (Codex, Kimi, Gemini CLI /
   Antigravity, Copilot), or a copy of the kickoff_guard leg with its hardened prefix
   (T-00000801) and `AGENTS_HOOK_HOST=claude` (Claude Code). A NEGATIVE CONTROL removes the
   leg from an in-memory copy, registry by registry, and requires the rule to name it.
2. PERMISSIONS — `.claude/settings.json` carries the `ask` of the canonical runner apply
   (the one form iac-runner-forme lets through, cross-checked against the guard) and the
   seven `deny` of state, planfile, export and cloud credential reads.
3. REPLAY (L-00000154) — the REGISTERED POSIX command of Claude, Codex and Gemini is run as
   the host runs it (`bash -c <command>`, from the root), on `terraform apply` (refusal in
   the host's own channel) and on `terraform plan` (silence, exit 0); the Codex leg once
   more with /usr/bin/python3 first on PATH when it exists (same verdicts under 3.9).
   NOT replayed: the PowerShell legs (no pwsh here), Kimi and Copilot (same file as Codex,
   their marker contract is in .codex/hooks/test_iac_guard.py).

Python 3.9 compatible on purpose (C2.1 is replayed under /usr/bin/python3). Events go to a
throwaway AGENTS_EVENTS_DIR, never to `.agents/state/events/`.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
CIBLE_CODEX = ".codex/hooks/iac_guard.py"
CIBLE_GEMINI = ".gemini/hooks/iac_guard.py"
KICKOFF = ".agents/bin/kickoff_guard.py"
# Jambe Claude enveloppée par le lanceur qui échoue FERMÉ (T-01M5CH9GATN4G2SP1VKCVR1HC3).
QUEUE_CLAUDE = (
    'AGENTS_HOOK_HOST=claude exec bash -p "$CLAUDE_PROJECT_DIR/.agents/security/garde-fermee.sh" '
    '--echeance=7 "$CLAUDE_PROJECT_DIR/.agents/pyrun.sh" '
    '"$CLAUDE_PROJECT_DIR/.codex/hooks/iac_guard.py"'
)
ASK = "Bash(bash .agents/pyrun.sh .agents/bin/tfdeploy.py apply*)"
DENY = (
    "Read(./**/*.tfstate)", "Read(./**/*.tfstate.*)", "Read(./**/*.tfplan)",
    "Read(~/.aws/credentials)", "Read(~/.azure/**)", "Read(~/.config/gcloud/**)",
    "Read(~/.cache/cadre-tfdeploy/**)",
)

# (registry, form, iac_guard target, safe_bash target, shell tools its matcher must name)
REGISTRES = (
    (".codex/hooks.json", "imbrique", CIBLE_CODEX, ".codex/hooks/safe_bash.py", ("Bash",)),
    (".kimi-code/hooks.json", "imbrique", CIBLE_CODEX, ".codex/hooks/safe_bash.py", ("Bash",)),
    (".agents/hooks.json", "imbrique", CIBLE_GEMINI, ".gemini/hooks/safe_bash.py", ("Bash", "run_command")),
    (".github/hooks/agent-guardrails.json", "copilot", CIBLE_CODEX, ".codex/hooks/safe_bash.py", ()),
    (".claude/settings.json", "claude", CIBLE_CODEX, "/.claude/hooks/safe-bash.sh", ("Bash",)),
)


def charger(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _couvre(matcher, outil):
    return outil in [alt.strip() for alt in (matcher or "").split("|")]


def _remplacer(jambe, cles, avant, apres):
    return {k: (v.replace(avant, apres) if k in cles else v) for k, v in jambe.items()}


def _ecarts_imbrique(obj, rel, cible, source, outils, claude):
    ecarts = []
    groupes = obj.get("hooks", {}).get("PreToolUse", [])
    jambes = [(g, n, h) for g in groupes for n, h in enumerate(g.get("hooks", []))
              if cible in str(h.get("command", ""))]
    if len(jambes) != 1:
        return ["%s: %d iac_guard legs, expected 1" % (rel, len(jambes))]
    groupe, n, jambe = jambes[0]
    for outil in outils:
        if not _couvre(groupe.get("matcher"), outil):
            ecarts.append("%s: the iac_guard matcher does not name %s" % (rel, outil))
    precedente = groupe["hooks"][n - 1] if n > 0 else {}
    if source not in str(precedente.get("command", "")):
        ecarts.append("%s: the iac_guard leg is not right after the safe_bash leg" % rel)
    if claude:
        kickoff = [h for g in groupes for h in g.get("hooks", []) if KICKOFF in str(h.get("command", ""))]
        if len(kickoff) != 1:
            return ecarts + ["%s: %d kickoff_guard legs, expected 1" % (rel, len(kickoff))]
        attendue = _remplacer(kickoff[0], ("command",), KICKOFF, CIBLE_CODEX)
        if not str(jambe.get("command", "")).endswith(QUEUE_CLAUDE):
            ecarts.append("%s: the iac_guard leg lost AGENTS_HOOK_HOST=claude or pyrun.sh" % rel)
    else:
        attendue = _remplacer(precedente, ("command", "commandWindows"), "safe_bash.py", "iac_guard.py")
        attendue["statusMessage"] = jambe.get("statusMessage")
    if jambe != attendue:
        ecarts.append("%s: the iac_guard leg is not a copy of its model leg, target replaced" % rel)
    return ecarts


def _ecarts_copilot(obj, rel, cible, source):
    liste = obj.get("hooks", {}).get("preToolUse", [])
    indices = [i for i, h in enumerate(liste) if cible in str(h.get("bash", ""))]
    if len(indices) != 1:
        return ["%s: %d iac_guard entries, expected 1" % (rel, len(indices))]
    i = indices[0]
    precedente = liste[i - 1] if i > 0 else {}
    if source not in str(precedente.get("bash", "")):
        return ["%s: the iac_guard entry is not right after the safe_bash entry" % rel]
    if liste[i] != _remplacer(precedente, ("bash", "powershell"), "safe_bash.py", "iac_guard.py"):
        return ["%s: the iac_guard entry is not a copy of the safe_bash entry" % rel]
    return []


def ecarts(charges):
    """THE RULE, one function, so the negative control replays THIS rule."""
    trouves = []
    for rel, forme, cible, source, outils in REGISTRES:
        obj = charges[rel]
        if forme == "copilot":
            trouves.extend(_ecarts_copilot(obj, rel, cible, source))
        else:
            trouves.extend(_ecarts_imbrique(obj, rel, cible, source, outils, forme == "claude"))
    return trouves


def _sans_iac(obj, forme):
    if forme == "copilot":
        obj["hooks"]["preToolUse"] = [h for h in obj["hooks"]["preToolUse"] if "iac_guard" not in str(h.get("bash", ""))]
        return
    for groupe in obj["hooks"]["PreToolUse"]:
        groupe["hooks"] = [h for h in groupe["hooks"] if "iac_guard" not in str(h.get("command", ""))]


def _jambe(rel, cible):
    for groupe in charger(rel)["hooks"]["PreToolUse"]:
        for jambe in groupe["hooks"]:
            if cible in jambe["command"]:
                return jambe["command"]
    raise AssertionError("%s: no iac_guard leg" % rel)


class CablageTests(unittest.TestCase):
    def test_les_cinq_registres_portent_une_jambe_iac_guard(self):
        charges = {rel: charger(rel) for rel, _f, _c, _s, _o in REGISTRES}
        self.assertEqual(ecarts(charges), [])

    def test_controle_negatif_retirer_une_entree_rougit_en_la_nommant(self):
        for rel, forme, _c, _s, _o in REGISTRES:
            charges = {r: charger(r) for r, _f, _c2, _s2, _o2 in REGISTRES}
            mutee = copy.deepcopy(charges[rel])
            _sans_iac(mutee, forme)
            self.assertNotEqual(mutee, charges[rel], "%s: the mutation removed nothing" % rel)
            charges[rel] = mutee
            trouves = ecarts(charges)
            self.assertTrue(trouves and all(t.startswith(rel + ":") for t in trouves), (rel, trouves))

    def test_controle_negatif_jambe_claude_sans_marqueur(self):
        charges = {rel: charger(rel) for rel, _f, _c, _s, _o in REGISTRES}
        for groupe in charges[".claude/settings.json"]["hooks"]["PreToolUse"]:
            for jambe in groupe["hooks"]:
                if CIBLE_CODEX in jambe["command"]:
                    jambe["command"] = jambe["command"].replace("AGENTS_HOOK_HOST=claude ", "")
        self.assertTrue(any("AGENTS_HOOK_HOST=claude" in t for t in ecarts(charges)))


class PermissionsTests(unittest.TestCase):
    def test_ask_du_runner_et_deny_des_lectures(self):
        permissions = charger(".claude/settings.json")["permissions"]
        self.assertIn(ASK, permissions["ask"])
        self.assertEqual([d for d in DENY if d not in permissions["deny"]], [])

    def test_l_ask_couvre_la_seule_forme_que_la_garde_admet(self):
        hooks = str(ROOT / ".codex" / "hooks")
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        spec = importlib.util.spec_from_file_location("_iac_guard_cablage", ROOT / CIBLE_CODEX)
        garde = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = garde
        spec.loader.exec_module(garde)
        prefixe = ASK[len("Bash("):-len("*)")]
        self.assertTrue(garde.forme_canonique(prefixe + " --target app-staging --task T-00000042 --plan-sha " + "a" * 64))
        self.assertFalse(garde.forme_canonique("cd x && " + prefixe))


@unittest.skipIf(BASH is None, "no bash on PATH: the registered commands cannot run")
class RejeuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="iac-cablage-"))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _jouer(self, commande, payload_cmd, extra=None, chemin=None):
        env = dict(os.environ)
        for cle in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR"):
            env.pop(cle, None)
        evenements = self.tmp / ("ev-%d" % len(list(self.tmp.iterdir())))
        evenements.mkdir()
        env["AGENTS_EVENTS_DIR"] = str(evenements)
        if chemin is not None:
            env["PATH"] = chemin + os.pathsep + env.get("PATH", "")
        env.update(extra or {})
        charge = json.dumps({"tool_input": {"command": payload_cmd}}).encode("utf-8")
        return subprocess.run([BASH, "-c", commande], input=charge, capture_output=True,
                              cwd=str(ROOT), env=env, timeout=120)

    def _assert_enveloppe(self, fini, hote):
        self.assertEqual((fini.returncode, fini.stderr), (0, b""), hote)
        corps = json.loads(fini.stdout.decode("utf-8"))
        self.assertEqual(corps["hookSpecificOutput"]["permissionDecision"], "deny", hote)
        self.assertIn("iac-apply-hors-runner", corps["hookSpecificOutput"]["permissionDecisionReason"])

    def test_claude_refuse_sur_stderr_et_2(self):
        commande = _jambe(".claude/settings.json", CIBLE_CODEX)
        extra = {"CLAUDE_PROJECT_DIR": str(ROOT)}
        fini = self._jouer(commande, "terraform apply", extra)
        self.assertEqual((fini.returncode, fini.stdout), (2, b""), fini.stderr)
        self.assertTrue(fini.stderr.startswith(b"BLOCKED by iac guard (iac-apply-hors-runner)"), fini.stderr)
        admis = self._jouer(commande, "terraform plan", extra)
        self.assertEqual((admis.returncode, admis.stdout, admis.stderr), (0, b"", b""))

    def test_codex_et_gemini_refusent_par_l_enveloppe(self):
        for rel, cible, hote in ((".codex/hooks.json", CIBLE_CODEX, "codex"),
                                 (".agents/hooks.json", CIBLE_GEMINI, "gemini")):
            commande = _jambe(rel, cible)
            self._assert_enveloppe(self._jouer(commande, "terraform apply"), hote)
            admis = self._jouer(commande, "terraform plan")
            self.assertEqual((admis.returncode, admis.stdout, admis.stderr), (0, b"", b""), hote)

    def test_jambe_codex_sous_python_3_9_memes_verdicts(self):
        python39 = Path("/usr/bin/python3")
        if not python39.exists():
            self.skipTest("/usr/bin/python3 absent")
        tete = self.tmp / "tete"
        tete.mkdir()
        (tete / "python3").symlink_to(python39)
        sonde = self._jouer(
            'bash "%s" -c "import sys; print(sys.version_info[0], sys.version_info[1])"'
            % (ROOT / ".agents" / "pyrun.sh"), "", chemin=str(tete))
        self.assertEqual(sonde.returncode, 0, sonde.stderr)
        commande = _jambe(".codex/hooks.json", CIBLE_CODEX)
        self._assert_enveloppe(self._jouer(commande, "terraform apply", chemin=str(tete)), "codex-3.9")
        admis = self._jouer(commande, "terraform plan", chemin=str(tete))
        self.assertEqual((admis.returncode, admis.stdout, admis.stderr), (0, b"", b""))
        sys.stderr.write("[iac-cablage] python de la jambe rejouee : %s\n" % sonde.stdout.decode().strip())


if __name__ == "__main__":
    unittest.main()
