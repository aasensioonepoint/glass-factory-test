"""Filet T-01M4RWC0DBM6XC1PDQGEG4P79C : réponses des hooks natifs lisibles par Copilot CLI.

LE DÉFAUT. Copilot CLI exécute les hooks natifs (`.github/hooks/agent-guardrails.json`
pointe sur `.codex/hooks/*.py`, L-006), mais lit la décision et le contexte AU
PREMIER NIVEAU du JSON ; les hooks ne les écrivaient que sous `hookSpecificOutput`.
Depuis cette tâche (décision pilote S-01M4RWM3TC4JWE5FDC8YB819Z4), sous
AGENTS_HOOK_HOST=copilot, le corps porte LES DEUX formes ; ailleurs, l'imbriquée
seule, inchangée.

CE QUE CE FILET TIENT :
1. CLASSEMENT FERMÉ — chaque enregistrement du registre natif Copilot est classé
   dans CLASSES ; un enregistrement non classé, ou une entrée de CLASSES qui ne
   désigne plus aucun enregistrement → ROUGE.
2. REJEU — chaque émetteur qui REFUSE ou INJECTE est rejoué en vrai
   sous-processus, avec l'environnement de son enregistrement et
   AGENTS_EVENTS_DIR sur un répertoire jetable. Les hooks via `_common` tournent
   dans une copie de fixture (modèle SYM-03239, `build_fixture` de
   test_events_parity.py, réutilisé tel quel) ; kickoff_guard tourne depuis son
   fichier réel, racine détournée sur un dépôt ARMÉ bâti par les constructeurs de
   test_kickoff_guard.py (jamais un board écrit à la main ici) ; semgrep-scan.sh
   tourne dans un dépôt git jetable, un `semgrep` bouchon en tête de PATH.
   Attendu : premier niveau présent ET égal à l'imbriqué, rc 0 ; pour
   gitleaks-scan.sh --content : rc 2 (A4, jamais l'enveloppe).
3. MÊMES STIMULI SOUS CODEX — forme imbriquée seule.
4. BRAS EN PROCESSUS — `_common.deny` / `additional_context`, environnement patché
   (le bras prévu dans test_guard_hooks.py, plafonné au cliquet, vit ici).
5. CONTRÔLES NÉGATIFS — les juges rougissent sur un corps imbriqué seul sous
   copilot, sur une seconde forme sous codex, et le classement sur un
   enregistrement inconnu.

HORS DE PORTÉE, DIT : que la CLI HONORE ces champs (le canal de retour) n'est pas
prouvé ici ; c'est la sonde pilote P-2
(docs/tasks/T-01M4RWC0DBM6XC1PDQGEG4P79C-sondes-pilote.md).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from surface_kit import jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REGISTRE = ROOT / ".github" / "hooks" / "agent-guardrails.json"
BASH = shutil.which("bash")

REFUS = ("permissionDecision", "permissionDecisionReason")
CONTEXTE = ("additionalContext",)

#: Table FERMÉE : (événement natif, script et arguments) -> classe. C'est l'audit
#: des émetteurs du plan (§5, T-00001245), plus `gitleaks-scan.sh` au Stop, que
#: l'audit ne listait pas (17 lignes sur 18) : exit 2 sur un secret, systemMessage
#: sur un DEGRADED, aucun champ Copilot à aligner.
CLASSES = {
    ("sessionStart", ".codex/hooks/session_context.py"): "common-contexte",
    ("preToolUse", ".codex/hooks/protect_paths.py"): "common-refus",
    ("preToolUse", ".agents/bin/kickoff_guard.py"): "enveloppe-propre",
    ("preToolUse", ".agents/security/gitleaks-scan.sh --content"): "exit2",
    ("preToolUse", ".codex/hooks/audit_gate.py"): "common-refus",
    ("preToolUse", ".codex/hooks/safe_bash.py"): "common-refus",
    # Ajouté le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : refus par `_common.deny`.
    ("preToolUse", ".codex/hooks/iac_guard.py"): "common-refus",
    ("postToolUse", ".codex/hooks/post_edit_check.py"): "common-contexte",
    ("postToolUse", ".agents/security/sca-scan.sh"): "sans-sortie",
    ("postToolUse", ".agents/bin/post-task-done-index.sh"): "system-message-seul",
    ("postToolUse", ".agents/security/semgrep-scan.sh --hook --event=post"): "json-shell",
    ("preCompact", ".codex/hooks/pre_compact_backup.py"): "sans-sortie",
    ("subagentStop", ".codex/hooks/log_agent_usage.py"): "system-message-seul",
    ("subagentStop", ".codex/hooks/binome_trace.py"): "sans-sortie",
    ("agentStop", ".codex/hooks/stale_index.py"): "system-message-seul",
    ("agentStop", ".codex/hooks/log_agent_usage.py"): "system-message-seul",
    ("agentStop", ".agents/security/sca-scan.sh"): "sans-sortie",
    ("agentStop", ".agents/security/gitleaks-scan.sh"): "exit2-stop",
    # Intégration E-47 sur feature/packaging-improvement : le registre porte 20 lignes
    # (plan_trace et affirmation-guard ajoutés par 6be229b0). Au Stop, sous copilot,
    # semgrep émet `{"decision":"block"}` sur un finding (fa0497f8, canal mesuré P3 ;
    # DEGRADED = systemMessage seul) ; affirmation-guard émet `{"decision":"block"}` ;
    # plan_trace n'écrit rien.
    ("agentStop", ".agents/security/semgrep-scan.sh --hook --event=stop"): "decision-block",
    ("subagentStop", ".agents/bin/plan_trace.py"): "sans-sortie",
    ("agentStop", ".claude/hooks/affirmation-guard.sh $PWD"): "decision-block",
}

#: Les classes REJOUÉES et les champs que chacune doit porter au premier niveau
#: sous copilot. `exit2` est rejouée à part (rc 2). Les autres classes n'ont pas
#: de champ Copilot (systemMessage seul : résidu nommé du plan) ou pas de sortie.
REJOUEES = {
    "common-refus": REFUS,
    "enveloppe-propre": REFUS,
    "common-contexte": CONTEXTE,
    "json-shell": CONTEXTE,
}
#: `decision-block` : le canal du Stop sous copilot, rejoué par
#: test_hotes_fin_de_tour.py et les bancs de semgrep-scan / affirmation-guard, pas ici.
CLASSES_CONNUES = set(REJOUEES) | {"exit2", "exit2-stop", "system-message-seul", "sans-sortie",
                                   "decision-block"}

#: Les stimuli, un par enregistrement rejoué (plusieurs pour semgrep : la forme
#: d'un FINDING en PHASE B, et la forme DEGRADED de la PHASE A).
STIMULI = {
    ("sessionStart", ".codex/hooks/session_context.py"): [{"source": "new"}],
    ("preToolUse", ".codex/hooks/protect_paths.py"): [
        {"toolName": "create", "toolArgs": {"path": ".env.sonde", "file_text": "x"}}
    ],
    ("preToolUse", ".codex/hooks/audit_gate.py"): [
        {"toolName": "bash", "toolArgs": {"command": "npx skills add vercel-labs/agent-skills"}}
    ],
    ("preToolUse", ".codex/hooks/safe_bash.py"): [
        {"toolName": "bash", "toolArgs": {"command": "rm -rf /"}}
    ],
    ("preToolUse", ".codex/hooks/iac_guard.py"): [
        {"toolName": "bash", "toolArgs": {"command": "terraform apply"}}
    ],
    ("postToolUse", ".codex/hooks/post_edit_check.py"): [
        {"toolName": "edit", "toolArgs": {"path": "src/ws.txt"}}
    ],
    ("preToolUse", ".agents/bin/kickoff_guard.py"): [
        {"toolName": "create", "toolArgs": {"path": "src/a.py", "file_text": "x"}}
    ],
    ("postToolUse", ".agents/security/semgrep-scan.sh --hook --event=post"): [
        {"toolName": "Edit", "toolInput": {"file_path": "probe.py"}, "session_id": "rep-finding"},
        "this is { not json",
    ],
}

# Le canari AWS, ASSEMBLÉ à l'exécution (L-00000391) : le jeton contigu n'est
# jamais écrit dans ce fichier, donc le scan des secrets du dépôt reste propre.
CANARI = "AK" + "IA" + "ZX4QY7GJ" + "TMPKQR5T"

PROG_KICKOFF = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import kickoff_guard as kg\n"
    "racine = Path(sys.argv[2])\n"
    "kg.repo_root = lambda: racine\n"
    "raise SystemExit(kg.main())\n"
)

SEMGREP_BOUCHON = (
    "#!/bin/sh\n"
    "f=x\n"
    "dd=0\n"
    'for a in "$@"; do\n'
    '  if [ "$dd" = 1 ]; then f="$a"; fi\n'
    '  if [ "$a" = "--" ]; then dd=1; fi\n'
    "done\n"
    "printf '{\"results\":[{\"check_id\":\"stub.rule.1\",\"path\":\"%s\",\"start\":{\"line\":1},"
    "\"extra\":{\"severity\":\"ERROR\"}}],\"paths\":{\"scanned\":[\"%s\"]}}\\n' \"$f\" \"$f\"\n"
)


# ---------------------------------------------------------------------------
# Lecture du registre
# ---------------------------------------------------------------------------

_ASSIGNATION = re.compile(r"[A-Z_][A-Z0-9_]*=\S*")
_ECHEANCE = re.compile(r"--echeance=[0-9]+")


def enregistrements(registre=None):
    """`[(événement, "script args", env de l'enregistrement)]`, dans l'ordre du registre.

    Hors du kit (T-01M54MWW5GH, S-01M550PYWS), une entrée de l'adoptant est écartée
    sur son texte BRUT, avant `hook["bash"]` et `shlex.split` : sa forme est à lui."""
    data = json.loads((registre or REGISTRE).read_text(encoding="utf-8"))
    sortie = []
    for evenement, hooks in data["hooks"].items():
        for hook in hooks:
            if not jambe_jugee(json.dumps(hook)):
                continue
            jetons = shlex.split(hook["bash"])
            env = {}
            while jetons and _ASSIGNATION.fullmatch(jetons[0]):
                cle, valeur = jetons.pop(0).split("=", 1)
                env[cle] = valeur
            if not jetons or jetons[0] != "bash":
                raise AssertionError(f"forme d'enregistrement inconnue : {hook['bash']!r}")
            reste = jetons[1:]
            # Le lanceur fermé (T-01M5MCXKHQS4BME9Z9VVSWD6VT) est un préfixe, sous sa
            # forme EXACTE : la garde qu'il porte reste la clé de la table.
            if (len(reste) >= 2 and reste[0] == ".agents/security/garde-fermee.sh"
                    and _ECHEANCE.fullmatch(reste[1])):
                reste = reste[2:]
            if reste and reste[0] == ".agents/pyrun.sh":
                reste = reste[1:]
            sortie.append((evenement, " ".join(reste), env))
    return sortie


def ecarts_de_classement(cles):
    """Ce qui manque à la table, et ce que la table nomme sans enregistrement."""
    cles = set(cles)
    return sorted(cles - set(CLASSES)), sorted(set(CLASSES) - cles)


# ---------------------------------------------------------------------------
# Juges
# ---------------------------------------------------------------------------


def corps_unique(stdout: bytes) -> dict:
    lignes = [l for l in stdout.decode("utf-8").splitlines() if l.strip()]
    if len(lignes) != 1:
        raise AssertionError(f"attendu EXACTEMENT une ligne JSON, reçu {len(lignes)} : {lignes!r}")
    corps = json.loads(lignes[0])
    if not isinstance(corps, dict) or not isinstance(corps.get("hookSpecificOutput"), dict):
        raise AssertionError(f"corps sans hookSpecificOutput : {lignes[0]!r}")
    return corps


def _imbrique_valide(imbrique: dict, champs) -> None:
    if not imbrique.get(champs[0]):
        raise AssertionError(f"l'imbriqué ne porte pas {champs[0]} : {imbrique!r}")
    if champs is REFUS and imbrique.get("permissionDecision") != "deny":
        raise AssertionError(f"l'imbriqué ne refuse pas : {imbrique!r}")


def juger_copilot(stdout: bytes, champs) -> dict:
    """Sous copilot : chaque champ AU PREMIER NIVEAU, égal à l'imbriqué."""
    corps = corps_unique(stdout)
    imbrique = corps["hookSpecificOutput"]
    _imbrique_valide(imbrique, champs)
    for champ in champs:
        if champ not in corps:
            raise AssertionError(f"copilot : {champ} absent du premier niveau : {sorted(corps)!r}")
        if corps[champ] != imbrique.get(champ):
            raise AssertionError(f"copilot : {champ} de premier niveau != imbriqué")
    return corps


def juger_autre_hote(stdout: bytes, champs) -> dict:
    """Hors copilot : l'imbriqué seul, aucun champ recopié au premier niveau."""
    corps = corps_unique(stdout)
    _imbrique_valide(corps["hookSpecificOutput"], champs)
    recopies = [c for c in champs if c in corps]
    if recopies:
        raise AssertionError(f"seconde forme hors copilot : {recopies!r}")
    return corps


# ---------------------------------------------------------------------------
# Rejeu
# ---------------------------------------------------------------------------


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def env_hook(env_enregistrement: dict, hote: str, evenements: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR")}
    env.update(env_enregistrement)
    env["AGENTS_HOOK_HOST"] = hote
    env["AGENTS_EVENTS_DIR"] = str(evenements)
    return env


@unittest.skipIf(BASH is None, "pas de bash sur le PATH : les émetteurs shell ne peuvent pas tourner")
class RejeuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.tmp = Path(cls._tmp.name).resolve()
        cls.registre = {(e, s): env for e, s, env in enregistrements()}
        parite = _charger("_replies_events_parity", ROOT / ".agents" / "evals" / "test_events_parity.py")
        cls.fixture = parite.build_fixture(cls.tmp / "fixture")
        kgt = _charger("_replies_kickoff_tests", ROOT / ".agents" / "bin" / "test_kickoff_guard.py")
        armee = cls.tmp / "kickoff"
        armee.mkdir()
        cls.depot_arme = kgt.build_repo(
            armee,
            gate="T-1\n",
            tasks_json=kgt.board(kgt.task("T-1", "pending", ["src/"])),
            specs_json=kgt.journal("T-1"),
        )
        cls._n = 0

    @classmethod
    def tearDownClass(cls):
        for nom in ("_replies_events_parity", "_replies_kickoff_tests"):
            sys.modules.pop(nom, None)
        cls._tmp.cleanup()

    def _neuf(self, prefixe: str) -> Path:
        type(self)._n += 1
        chemin = self.tmp / f"{prefixe}-{self._n}"
        chemin.mkdir()
        return chemin

    def rejouer(self, cle, stimulus, hote):
        """`(rc, stdout)` de l'émetteur de `cle`, sous `hote`, en vrai sous-processus."""
        evenement, ligne = cle
        script, *args = ligne.split()
        env = env_hook(self.registre[cle], hote, self._neuf("events"))
        charge = stimulus if isinstance(stimulus, str) else json.dumps(stimulus)
        if script.startswith(".codex/hooks/"):
            cmd, cwd = [sys.executable, "-B", str(self.fixture / script), *args], self.fixture
        elif script == ".agents/bin/kickoff_guard.py":
            cmd = [sys.executable, "-B", "-c", PROG_KICKOFF, str(ROOT / ".agents" / "bin"), str(self.depot_arme)]
            cwd = self.depot_arme
        elif script == ".agents/security/semgrep-scan.sh":
            cwd = self._neuf("semgrep")
            subprocess.run(["git", "init", "-q"], cwd=cwd, check=True)
            (cwd / "probe.py").write_text("x = 1\n", encoding="utf-8")
            bouchons = self._neuf("bouchon")
            (bouchons / "semgrep").write_text(SEMGREP_BOUCHON, encoding="utf-8")
            (bouchons / "semgrep").chmod(0o755)
            env["PATH"] = f"{bouchons}{os.pathsep}{env.get('PATH', '')}"
            env["SEMGREP_CONFIG"] = str(ROOT / ".agents" / "security" / "semgrep.yml")
            cmd = [BASH, str(ROOT / script), *args]
        elif script == ".agents/security/gitleaks-scan.sh":
            cmd, cwd = [BASH, str(ROOT / script), *args], self._neuf("gitleaks")
        else:  # pragma: no cover - la table STIMULI ne nomme rien d'autre
            raise AssertionError(f"aucun lanceur pour {ligne!r}")
        fini = subprocess.run(cmd, input=charge.encode("utf-8"), capture_output=True,
                              cwd=str(cwd), env=env, timeout=120)
        return fini.returncode, fini.stdout

    # -- 1. classement fermé ---------------------------------------------------

    def test_chaque_enregistrement_est_classe_et_chaque_classe_designe_un_enregistrement(self):
        cles = [(e, s) for e, s, _ in enregistrements()]
        # 20 -> 21 le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard sur `preToolUse`.
        self.assertEqual(len(cles), 21, "le registre natif a changé : reclasser")
        self.assertEqual(len(set(cles)), len(cles), "deux enregistrements identiques")
        self.assertEqual(ecarts_de_classement(cles), ([], []))
        self.assertLessEqual(set(CLASSES.values()), CLASSES_CONNUES)
        for e, s, env in enregistrements():
            with self.subTest(enregistrement=(e, s)):
                self.assertEqual(env.get("AGENTS_HOOK_HOST"), "copilot")

    def test_chaque_emetteur_rejoue_a_ses_stimuli(self):
        attendus = {c for c, k in CLASSES.items() if k in REJOUEES}
        self.assertEqual(set(STIMULI), attendus)

    # -- 2. sous copilot : les deux formes ----------------------------------------

    def test_copilot_premier_niveau_egal_a_l_imbrique_rc_0(self):
        for cle, stimuli in STIMULI.items():
            champs = REJOUEES[CLASSES[cle]]
            for stimulus in stimuli:
                with self.subTest(emetteur=cle[1], stimulus=str(stimulus)[:40]):
                    rc, out = self.rejouer(cle, stimulus, "copilot")
                    self.assertEqual(rc, 0, out)
                    juger_copilot(out, champs)

    # -- 3. sous codex : l'imbriquée seule -----------------------------------------

    def test_codex_forme_imbriquee_seule(self):
        for cle, stimuli in STIMULI.items():
            champs = REJOUEES[CLASSES[cle]]
            for stimulus in stimuli:
                with self.subTest(emetteur=cle[1], stimulus=str(stimulus)[:40]):
                    rc, out = self.rejouer(cle, stimulus, "codex")
                    self.assertEqual(rc, 0, out)
                    juger_autre_hote(out, champs)

    # -- A4 : gitleaks garde exit 2 -------------------------------------------------

    def test_gitleaks_content_garde_exit_2_sans_enveloppe(self):
        cle = ("preToolUse", ".agents/security/gitleaks-scan.sh --content")
        self.assertEqual(CLASSES[cle], "exit2")
        stimulus = {"toolName": "create",
                    "toolArgs": {"path": "cfg.py", "file_text": f"aws_access_key_id = {CANARI}"}}
        for hote in ("copilot", "codex"):
            with self.subTest(hote=hote):
                rc, out = self.rejouer(cle, stimulus, hote)
                self.assertEqual(rc, 2, out)
                self.assertNotIn(b"permissionDecision", out)


# ---------------------------------------------------------------------------
# 4. Bras en processus
# ---------------------------------------------------------------------------


class EnProcessusTests(unittest.TestCase):
    def setUp(self):
        self.common = _charger("_replies_common", ROOT / ".codex" / "hooks" / "_common.py")
        self.addCleanup(sys.modules.pop, "_replies_common", None)

    def _capturer(self, hote, appel):
        env = {k: v for k, v in os.environ.items() if k != "AGENTS_HOOK_HOST"}
        env["AGENTS_HOOK_HOST"] = hote
        tampon = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(tampon):
            appel()
        return tampon.getvalue().encode("utf-8")

    def test_copilot_en_processus(self):
        juger_copilot(self._capturer("copilot", lambda: self.common.deny("refus")), REFUS)
        juger_copilot(self._capturer("copilot", lambda: self.common.additional_context("ctx")), CONTEXTE)
        juger_copilot(
            self._capturer("copilot", lambda: self.common.additional_context("ctx", "PostToolUse")),
            CONTEXTE,
        )

    def test_codex_en_processus(self):
        juger_autre_hote(self._capturer("codex", lambda: self.common.deny("refus")), REFUS)
        juger_autre_hote(self._capturer("codex", lambda: self.common.additional_context("ctx")), CONTEXTE)


# ---------------------------------------------------------------------------
# 5. Contrôles négatifs
# ---------------------------------------------------------------------------


class ControlesNegatifsTests(unittest.TestCase):
    IMBRIQUE_SEUL = (b'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                     b'"permissionDecision":"deny","permissionDecisionReason":"r"}}\n')
    DEUX_FORMES = (b'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                   b'"permissionDecision":"deny","permissionDecisionReason":"r"},'
                   b'"permissionDecision":"deny","permissionDecisionReason":"r"}\n')

    def test_un_corps_imbrique_seul_sous_copilot_rougit(self):
        with self.assertRaises(AssertionError):
            juger_copilot(self.IMBRIQUE_SEUL, REFUS)
        juger_copilot(self.DEUX_FORMES, REFUS)

    def test_une_seconde_forme_hors_copilot_rougit(self):
        with self.assertRaises(AssertionError):
            juger_autre_hote(self.DEUX_FORMES, REFUS)
        juger_autre_hote(self.IMBRIQUE_SEUL, REFUS)

    def test_un_premier_niveau_different_de_l_imbrique_rougit(self):
        faux = self.DEUX_FORMES.replace(b'"permissionDecisionReason":"r"}\n', b'"permissionDecisionReason":"x"}\n')
        with self.assertRaises(AssertionError):
            juger_copilot(faux, REFUS)

    def test_un_enregistrement_inconnu_ou_disparu_rougit_le_classement(self):
        cles = list(CLASSES)
        self.assertEqual(ecarts_de_classement(cles + [("agentStop", ".codex/hooks/neuf.py")]),
                         ([("agentStop", ".codex/hooks/neuf.py")], []))
        self.assertEqual(ecarts_de_classement(cles[1:]), ([], [cles[0]]))


if __name__ == "__main__":
    unittest.main()
