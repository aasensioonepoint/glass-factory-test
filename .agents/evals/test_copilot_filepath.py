"""Filet de T-01M4RWCAGQZKYQ9JS4C1JPBFVQ (E-47, F5) : les gardes natives lisent
`filePath`, la graphie du harness Local de VS Code, et le garde de mandat juge
l'outil `create` de la CLI Copilot.

Ce que le filet tient, et rien de plus :

  (i)   DE BOUT EN BOUT — en sous-processus, sur une fixture jetable,
        `AGENTS_HOOK_HOST=copilot`, `AGENTS_EVENTS_DIR` sur un dossier
        temporaire, charge sur stdin : `protect_paths` refuse
        `replace_string_in_file` (et `create_file`) dont le `filePath` est un
        `.env*`, et trace une ligne `hook.deny` host=copilot. Le refus se lit à
        `hookSpecificOutput.permissionDecision` (forme imbriquée), JAMAIS par
        comparaison du stdout à l'octet (C5 du plan) : T-01M4RWC0DBM6XC1PDQGEG4P79C
        ajoute une forme de premier niveau au même objet, et ce banc doit rester
        vert après elle.
  (ii)  LECTURE — `read_file` avec `filePath` = `.env.local` sort tôt : rc 0,
        muet, 0 événement. Contrôle négatif : un mutant de protect_paths privé de
        sa garde `lecture_copilot` REFUSE la même charge. C'est donc la garde de
        T-01M4RWC6VHHN479J2A9RRY1BE3, et non l'oubli de `filePath`, qui laisse
        passer la lecture.
  (iii) JUMEAU — le `paths_from_payload` Gemini, chargé PAR CHEMIN, lit aussi
        `filePath`.
  (iv)  PARITÉ PAR COMPORTEMENT — `kickoff_guard.paths_from_payload` et les deux
        `_common.paths_from_payload` rendent les mêmes chemins, dans le même
        ordre, sur six charges, après normalisation. Chaque charge porte aussi son
        résultat ATTENDU : une parité dans l'oubli (toutes ignorant `filePath`)
        rougit.

`.codex/hooks/test_guard_hooks.py` n'est pas touché : plafond = origine
(SYM-13315). Source : docs/tasks/T-01M4RWBSR48YW8RPAV7TG6HKET-plan.md, révision
5, section « T-00001248 » (ancien id). Décision S-01M4RWM3TC4JWE5FDC8YB819Z4.
"""
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

# La garde posée par T-01M4RWC6VHHN479J2A9RRY1BE3 en tête de protect_paths.main.
GARDE = "    if lecture_copilot(payload):\n        return\n"


def charger(rel, nom):
    """Un module du dépôt chargé PAR CHEMIN, sous un nom privé (jamais `_common` nu)."""
    spec = importlib.util.spec_from_file_location(nom, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module  # dataclasses de kickoff_guard : le module doit être résolvable
    spec.loader.exec_module(module)
    return module


# `cadre` résolu par vendor_paths, vendor d'abord (S-01M5BXT85VP4JBBMXVXR9STP5F).
VENDOR_PATHS = charger(".agents/bin/vendor_paths.py", "_copilot_filepath_vendor_paths")


def decision(stdout):
    """Le refus, lu à `hookSpecificOutput.permissionDecision` (C5), jamais à l'octet."""
    if not stdout.strip():
        return None
    return (json.loads(stdout).get("hookSpecificOutput") or {}).get("permissionDecision")


class Fixture:
    """Un projet git jetable portant le pont Codex de protect_paths et `events.py`."""

    def __init__(self, racine):
        self.racine = racine
        self.hooks = racine / ".codex" / "hooks"
        self.hooks.mkdir(parents=True)
        (racine / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(ROOT / ".agents" / "bin" / "events.py", racine / ".agents" / "bin" / "events.py")
        # Copié seulement s'il existe : sans lui, events.py écrit quand même la
        # ligne (voie dégradée), et ce filet ne lit que kind, host et path. Une
        # extraction partielle (§9, étape 3 : sans paquet) rejoue donc ce banc.
        # Posé à l'ancien lieu ET au neuf, dont le lieu que lit events.py (`_CHEMIN_REDACTION`).
        paquet = VENDOR_PATHS.dossier_paquet(ROOT, "cadre")
        redaction = paquet / "ledger" / "redaction.py" if paquet else None
        if redaction is not None and redaction.is_file():
            for lieu in ("src/cadre/ledger", ".agents/vendor/cadre/ledger"):
                (racine / lieu).mkdir(parents=True)
                shutil.copy2(redaction, racine / lieu / "redaction.py")
        for module in ("_common", "protect_paths"):
            shutil.copy2(ROOT / ".codex" / "hooks" / f"{module}.py", self.hooks / f"{module}.py")
        # La racine du pont est `git rev-parse --show-toplevel` : la fixture est
        # son propre dépôt, jamais celui qui l'héberge.
        subprocess.run(["git", "-C", str(racine), "init", "-q"], check=True, capture_output=True)
        self.compteur = 0

    def jouer(self, charge, hote="copilot", script=None):
        """`(rc, stdout en octets, événements)` d'un vrai sous-processus."""
        self.compteur += 1
        evenements = self.racine.parent / f"ev-{self.compteur}"
        evenements.mkdir()
        env = dict(os.environ)
        for cle in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR"):
            env.pop(cle, None)
        env["AGENTS_EVENTS_DIR"] = str(evenements)
        env["AGENTS_HOOK_HOST"] = hote
        fini = subprocess.run(
            [sys.executable, "-B", str(script or self.hooks / "protect_paths.py")],
            input=json.dumps(charge).encode("utf-8"),
            capture_output=True, cwd=str(self.racine), env=env, timeout=60,
        )
        lignes = b"".join(p.read_bytes() for p in sorted(evenements.glob("*.jsonl")))
        recs = [json.loads(l) for l in lignes.decode("utf-8").splitlines() if l.strip()]
        return fini.returncode, fini.stdout, recs


class DeBoutEnBout(unittest.TestCase):
    """(i) et (ii) : protect_paths en sous-processus, sous copilot."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.fx = Fixture(Path(cls._tmp.name) / "projet")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_protect_paths_refuse_un_env_passe_par_filepath(self):
        absolu = str(self.fx.racine / ".env.local")
        cas = (
            ("replace_string_in_file", absolu, ".env.local", "copilot"),
            ("replace_string_in_file", ".env.local", ".env.local", "copilot"),
            ("create_file", ".env.sonde", ".env.sonde", "copilot"),
            ("replace_string_in_file", absolu, ".env.local", "codex"),
        )
        for outil, valeur, attendu, hote in cas:
            with self.subTest(outil=outil, filePath=valeur, hote=hote):
                charge = {"toolName": outil, "toolArgs": {"filePath": valeur}}
                rc, out, recs = self.fx.jouer(charge, hote)
                self.assertEqual(rc, 0)
                self.assertEqual(decision(out), "deny")
                self.assertEqual(
                    [(r["kind"], r["host"], r["data"]["path"]) for r in recs],
                    [("hook.deny", hote, attendu)],
                )

    def test_read_file_avec_filepath_sort_tot(self):
        charge = {"toolName": "read_file", "toolArgs": {"filePath": str(self.fx.racine / ".env.local")}}
        self.assertEqual(self.fx.jouer(charge), (0, b"", []))

    def test_controle_negatif_sans_la_garde_la_lecture_est_refusee(self):
        source = (self.fx.hooks / "protect_paths.py").read_text(encoding="utf-8")
        self.assertEqual(source.count(GARDE), 1, "un mutant qui ne mute rien est un témoin muet")
        mutant = self.fx.hooks / "protect_paths_mutant.py"
        mutant.write_text(source.replace(GARDE, "", 1), encoding="utf-8")
        charge = {"toolName": "read_file", "toolArgs": {"filePath": str(self.fx.racine / ".env.local")}}
        rc, out, recs = self.fx.jouer(charge, script=mutant)
        self.assertEqual(decision(out), "deny", "sans la garde, filePath lu doit faire refuser la lecture")
        self.assertEqual([r["kind"] for r in recs], ["hook.deny"])


class Parite(unittest.TestCase):
    """(iii) et (iv) : les trois `paths_from_payload`, chargés par chemin."""

    @classmethod
    def setUpClass(cls):
        cls.codex = charger(".codex/hooks/_common.py", "_common_filepath_codex")
        cls.gemini = charger(".gemini/hooks/_common.py", "_common_filepath_gemini")
        cls.kg = charger(".agents/bin/kickoff_guard.py", "_kickoff_guard_filepath")

    def test_le_jumeau_gemini_lit_filepath(self):
        self.assertEqual(self.gemini.paths_from_payload({"toolArgs": {"filePath": "a.py"}}), ["a.py"])
        self.assertEqual(
            self.gemini.paths_from_payload({"toolArgs": {"filePath": "a.py", "path": "b.py"}}),
            ["a.py", "b.py"],
        )

    def test_trois_fonctions_meme_comportement_sur_six_charges(self):
        absolu = str(self.codex.ROOT / ".env.local")
        charges = (
            ({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, ["a.py"]),
            ({"toolName": "replace_string_in_file", "toolArgs": {"filePath": "src/a.py"}}, ["src/a.py"]),
            ({"toolName": "create_file", "toolArgs": {"filePath": "a.py", "path": "b.py"}}, ["a.py", "b.py"]),
            ({"toolName": "create", "toolArgs": {"path": "src/c.py", "file_text": "x"}}, ["src/c.py"]),
            (
                {"tool_name": "apply_patch",
                 "tool_input": {"command": "*** Begin Patch\n*** Update File: src/d.py\n*** End Patch"}},
                ["src/d.py"],
            ),
            ({"toolName": "edit_file", "toolArgs": {"filePath": absolu, "target_file": "e.py"}},
             [".env.local", "e.py"]),
        )
        for charge, attendu in charges:
            with self.subTest(charge=charge):
                garde = [self.codex.normalize_path(p) for p in self.kg.paths_from_payload(charge)]
                self.assertEqual(garde, attendu, "kickoff_guard")
                self.assertEqual(self.codex.paths_from_payload(charge), attendu, ".codex/_common")
                self.assertEqual(self.gemini.paths_from_payload(charge), attendu, ".gemini/_common")

    def test_create_est_une_ecriture_pour_le_garde_de_mandat(self):
        self.assertTrue(self.kg.is_write_form({"toolName": "create", "toolArgs": {"path": "x"}}))


if __name__ == "__main__":
    unittest.main()
