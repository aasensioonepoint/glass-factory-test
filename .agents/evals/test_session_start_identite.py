"""Témoins D de T-00001103 (lot C) : le SessionStart de Claude LANCE l'amorçage, détaché.

Joue `.claude/hooks/session-start.sh` comme l'hôte (`capture_output`, stdin fermé) sur une racine
jetable d'adoptant : `.agents/bin/amorcage_auto.py` (copie du dépôt) et un FAUX
`setup_projet.py` qui compte ses démarrages, écrit project.json, dort `FAUX_DUREE` et sort
`FAUX_RC`. Ni `state/local/`, ni board, ni index : la racine neuve d'un adoptant réduite à ce que
le bloc lit. Les groupes détachés sont tués en teardown (`killpg`).

BORNE : la racine n'est pas une copie du gabarit `template/starter-kit` entier ; le setup réel
n'est pas joué ici (mesuré au plan, annexe § 2ter).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-start.sh"
AMORCEUR = ROOT / ".agents" / "bin" / "amorcage_auto.py"
BASH = shutil.which("bash")

FAUX_SETUP = '''import os, sys, time
from pathlib import Path
r = Path(sys.argv[sys.argv.index("--root") + 1])
etat = r / ".agents" / "state"
with open(etat / "demarrages", "a", encoding="utf-8") as f:
    f.write("x\\n")
(etat / "project.json").write_text("{}", encoding="utf-8")
time.sleep(float(os.environ.get("FAUX_DUREE", "0.2")))
sys.exit(int(os.environ.get("FAUX_RC", "0")))
'''


@unittest.skipIf(BASH is None or sys.platform == "win32",
                 "bash absent, ou Windows (pas de flock : amorçage non lancé, dit)")
class SessionStartAmorcageTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        bin_dir = self.root / ".agents" / "bin"
        bin_dir.mkdir(parents=True)
        shutil.copy2(AMORCEUR, bin_dir / AMORCEUR.name)
        (bin_dir / "setup_projet.py").write_text(FAUX_SETUP, encoding="utf-8")
        (self.root / ".git").mkdir()
        self.etat = self.root / ".agents" / "state"
        self.etat.mkdir()
        self.addCleanup(self._tuer)

    def _tuer(self) -> None:
        try:
            rec = json.loads((self.etat / "local" / "amorcage.json").read_text(encoding="utf-8"))
            if rec.get("pid"):
                os.killpg(rec["pid"], signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def _hook(self, path: str | None = None, **extra: str) -> tuple[str, float, int]:
        env = {"PATH": path or os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(self.root), **extra}
        debut = time.monotonic()
        out = subprocess.run([BASH, str(HOOK)], env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60, check=False)
        duree = time.monotonic() - debut
        ctx = ""
        if out.stdout.strip():
            ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
        return ctx, duree, out.returncode

    def _demarrages(self) -> int:
        try:
            return len((self.etat / "demarrages").read_text(encoding="utf-8").splitlines())
        except OSError:
            return 0

    def _attendre(self, cond, delai: float = 15.0) -> None:
        fin = time.monotonic() + delai
        while time.monotonic() < fin:
            if cond():
                return
            time.sleep(0.05)
        self.fail("condition jamais atteinte")

    def _rc(self):
        try:
            return json.loads((self.etat / "local" / "amorcage.json").read_text(encoding="utf-8")).get("rc")
        except (OSError, ValueError):
            return None

    def test_lance_detache_puis_en_cours_pendant_le_run(self) -> None:
        self.assertFalse((self.etat / "local").exists())
        ctx, duree, rc = self._hook(FAUX_DUREE="30")
        self.assertEqual(rc, 0)
        self.assertLess(duree, 3.0, "le hook a attendu le setup détaché")
        self.assertIn("[PROJECT STATUS] amorçage lancé en arrière-plan", ctx)
        # Bloc critique en tête : la ligne se clôt par un paragraphe, jamais collée au board.
        self.assertIn("amorcage.log\n\n", ctx)
        self._attendre(lambda: self._demarrages() == 1)
        ctx2, _, _ = self._hook(FAUX_DUREE="30")
        self.assertIn("[PROJECT STATUS] amorçage en cours", ctx2)
        self.assertEqual(self._demarrages(), 1)

    def test_apres_rc0_ni_ligne_ni_relance(self) -> None:
        self.assertIn("lancé", self._hook()[0])
        self._attendre(lambda: self._rc() == 0)
        ctx, _, rc = self._hook()
        self.assertEqual(rc, 0)
        self.assertNotIn("amorçage", ctx)
        self.assertEqual(self._demarrages(), 1)

    def test_path_sans_timeout_lance_quand_meme(self) -> None:
        """macOS nu : pas de timeout(1) (mesuré rc 127) — l'appel direct garde la ligne."""
        liens = self.root.parent / (self.root.name + "-path")
        liens.mkdir()
        self.addCleanup(shutil.rmtree, liens, True)
        for dossier in os.environ["PATH"].split(os.pathsep):
            try:
                noms = os.listdir(dossier)
            except OSError:
                continue
            for nom in noms:
                cible = liens / nom
                if nom in ("timeout", "gtimeout") or os.path.lexists(cible):
                    continue
                source = os.path.join(dossier, nom)
                if os.path.isfile(source) and os.access(source, os.X_OK):
                    os.symlink(source, cible)
        sonde = subprocess.run([BASH, "-c", "command -v timeout"], env={"PATH": str(liens)},
                               capture_output=True, text=True, check=False)
        self.assertNotEqual(sonde.returncode, 0, "timeout encore visible sous le PATH de liens")
        ctx, duree, rc = self._hook(path=str(liens), FAUX_DUREE="30")
        self.assertEqual(rc, 0)
        self.assertLess(duree, 3.0)
        self.assertIn("[PROJECT STATUS] amorçage lancé en arrière-plan", ctx)
        self._attendre(lambda: self._demarrages() == 1)


def _charger_session_context_gemini():
    """Charge `.gemini/hooks/session_context.py` PAR CHEMIN, sous un nom unique ; son `_common`
    (frère du même nom côté Codex) est importé depuis `.gemini/hooks/`, sys.modules restauré."""
    hooks = ROOT / ".gemini" / "hooks"
    spec = importlib.util.spec_from_file_location("_gemini_session_context_identite",
                                                  hooks / "session_context.py")
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", [str(hooks), *sys.path]):
        sys.modules.pop("_common", None)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return mod


def _tuer_groupe(pid) -> None:
    """Teardown d'un amorçage détaché : son groupe meurt, un groupe déjà parti est admis."""
    try:
        if pid:
            os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


@unittest.skipIf(sys.platform == "win32", "flock absent : amorçage non lancé (dit)")
class GeminiSessionContextAmorcageTests(unittest.TestCase):
    """Déplacé de `.gemini/hooks/test_gemini_hooks.py` (cliquet de longueur, T-00001103 lot C)."""

    def test_bootstrap_launched_line_on_adopter_root(self) -> None:
        """Sur une racine d'adoptant (STATE sous ROOT, faux setup), main() LANCE l'amorçage
        détaché et porte sa ligne ; la ligne `projet sans nom` se tait pendant le run (D1 R7)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, \
                tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as evenements:
            racine = Path(d).resolve()
            (racine / ".agents" / "bin").mkdir(parents=True)
            (racine / ".git").mkdir()
            (racine / ".agents" / "bin" / "setup_projet.py").write_text("raise SystemExit(0)\n")
            sc = _charger_session_context_gemini()
            sc.ROOT, sc.STATE = racine, racine / ".agents" / "state"
            sc.refresh_index_if_stale = lambda: None
            env = {k: v for k, v in os.environ.items() if k not in ("CI", "CADRE_AMORCAGE")}
            env["AGENTS_EVENTS_DIR"] = evenements
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
                sc.main()
            etat = racine / ".agents" / "state" / "local" / "amorcage.json"
            self.addCleanup(_tuer_groupe, json.loads(etat.read_text(encoding="utf-8")).get("pid"))
        out = json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[PROJECT STATUS] amorçage lancé en arrière-plan", out)
        self.assertNotIn("[PROJECT STATUS] projet sans nom", out)


if __name__ == "__main__":
    unittest.main()
