"""L'hôte, le verrou et les sauvegardes SUIVENT LE RÉPERTOIRE (T-01M4V7R5H0HE0Z5TPJ4Q64VMPF, lot H).

Depuis la source unique, `.codex/hooks/*.py` et `.gemini/hooks/*.py` sont les MÊMES octets
(test_guard_decision_parity.py le tient). Ce qui distinguait les deux copies se lit donc du
répertoire qui porte le fichier (`_common.hook_dir`, os.path.abspath) :

  1. l'étiquette d'hôte : la table FERMÉE `{".gemini": "gemini"}` répond d'abord — sous
     `.gemini/`, AGENTS_HOOK_HOST=copilot ne déplace pas l'étiquette ; sous `.codex/`, qui
     sert codex, copilot et kimi, seule la variable répond, et son absence ne pose AUCUNE
     étiquette (jamais « codex » par défaut) ;
  2. le préfixe du verrou de RUN_LOG (log_agent_usage.py) : un verrou par répertoire ;
  3. le dossier `backups` de pre_compact_backup.py.

Le répertoire se lit par os.path.abspath, JAMAIS par realpath ni resolve() : un `hooks/` atteint
par un lien symbolique garde le nom de l'hôte qui l'appelle (note du répertoire de `_common.py`).

Méthode : les hooks réels sont copiés (`shutil.copy2`) sous une racine jetable HORS du dépôt,
dans `.codex/hooks/` et `.gemini/hooks/`, puis joués en SOUS-PROCESSUS (aucun chargement par
chemin dans ce processus). GIT_CEILING_DIRECTORIES borne la découverte git à la racine
jetable : `project_root()` retombe sur elle. Le verrou est observé dans un TMPDIR neuf par
passage, listé à plat. Aucun parcours d'arbre (test_repo_walk_census).

Mutants qui doivent rougir : table vide ; table `{".codex": "codex"}` ; `".codex"` codé en dur
pour `backups` ; préfixe de verrou codé en dur ; `hook_dir` en os.path.realpath au lieu
d'os.path.abspath (témoin du lien symbolique).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOTES = (".codex", ".gemini")
MODULES = ("_common.py", "log_agent_usage.py", "pre_compact_backup.py")
VARIABLE = "AGENTS_HOOK_HOST"
# Une valeur par passage ; "-" = variable absente.
VALEURS = ("-", "copilot", "kimi", "codex", "inconnu")
ATTENDU = {
    ".gemini": ["gemini"] * len(VALEURS),
    ".codex": ["None", "copilot", "kimi", "codex", "None"],
}
TETE = "import os, sys\nsys.path.insert(0, sys.argv[1])\nimport _common\n"
BOUCLE = (
    "for v in sys.argv[2:]:\n"
    f"    os.environ.pop({VARIABLE!r}, None)\n"
    "    if v != '-':\n"
    f"        os.environ[{VARIABLE!r}] = v\n"
    "    print(_common.event_host())\n"
)
SONDE = TETE + BOUCLE
# La même, précédée de hook_dir() : la cause racine se lit dans le message d'échec.
SONDE_LIEN = TETE + "print(_common.hook_dir())\n" + BOUCLE


class HoteParRepertoire(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hote-repertoire-"))
        self.racine = self.base / "projet"
        for hote in HOTES:
            cible = self.racine / hote / "hooks"
            cible.mkdir(parents=True)
            for module in MODULES:
                shutil.copy2(ROOT / hote / "hooks" / module, cible / module)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def env(self, valeur=None, tmpdir=None):
        env = {k: v for k, v in os.environ.items() if k not in (VARIABLE, "AGENTS_EVENTS_DIR")}
        env["GIT_CEILING_DIRECTORIES"] = str(self.base)
        if valeur is not None:
            env[VARIABLE] = valeur
        if tmpdir is not None:
            env["TMPDIR"] = str(tmpdir)
        return env

    def jouer(self, hote, module, charge, env):
        return subprocess.run(
            [sys.executable, "-B", str(self.racine / hote / "hooks" / module)],
            input=json.dumps(charge), capture_output=True, text=True,
            cwd=str(self.racine), env=env, timeout=60,
        )

    def test_les_copies_sont_les_hooks_du_depot(self):
        for hote in HOTES:
            for module in MODULES:
                with self.subTest(hote=hote, module=module):
                    self.assertEqual((self.racine / hote / "hooks" / module).read_bytes(),
                                     (ROOT / hote / "hooks" / module).read_bytes())

    def test_l_etiquette_vient_du_repertoire_puis_de_la_variable(self):
        for hote in HOTES:
            with self.subTest(hote=hote):
                fini = subprocess.run(
                    [sys.executable, "-B", "-c", SONDE, str(self.racine / hote / "hooks"), *VALEURS],
                    capture_output=True, text=True, cwd=str(self.racine), env=self.env(), timeout=60,
                )
                self.assertEqual(fini.returncode, 0, fini.stderr)
                self.assertEqual(fini.stdout.split(), ATTENDU[hote], dict(zip(VALEURS, fini.stdout.split())))

    def test_un_hooks_lie_garde_le_nom_de_son_hote(self):
        """Chaque `<hôte>/hooks` est ici un LIEN SYMBOLIQUE vers la copie réelle de l'AUTRE
        hôte. abspath garde le nom du lien : l'hôte reste celui qui appelle. Sous le mutant
        realpath, `.gemini` lié à `.codex/hooks` deviendrait `.codex` (et l'inverse)."""
        liens = self.base / "liens"
        for hote, cible in ((".gemini", ".codex"), (".codex", ".gemini")):
            (liens / hote).mkdir(parents=True)
            try:
                os.symlink(self.racine / cible / "hooks", liens / hote / "hooks", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"lien symbolique refusé ici ({exc}) : témoin abspath NON joué")
        for hote in HOTES:
            with self.subTest(hote=hote):
                fini = subprocess.run(
                    [sys.executable, "-B", "-c", SONDE_LIEN, str(liens / hote / "hooks"), *VALEURS],
                    capture_output=True, text=True, cwd=str(liens), env=self.env(), timeout=60,
                )
                self.assertEqual(fini.returncode, 0, fini.stderr)
                self.assertEqual(fini.stdout.split(), [hote, *ATTENDU[hote]],
                                 dict(zip(("hook_dir", *VALEURS), fini.stdout.split())))

    def test_les_sauvegardes_suivent_le_repertoire(self):
        transcript = self.racine / "transcript.jsonl"
        transcript.write_text(json.dumps({"message": "x"}) + "\n", encoding="utf-8")
        for joue, absent in ((".gemini", ".codex"), (".codex", None)):
            with self.subTest(hote=joue):
                fini = self.jouer(joue, "pre_compact_backup.py",
                                  {"transcript_path": str(transcript)}, self.env("copilot"))
                self.assertEqual(fini.returncode, 0, fini.stderr)
                copies = list((self.racine / joue / "backups").glob("pre-compact-*.jsonl"))
                self.assertEqual(len(copies), 1, copies)
                if absent:
                    self.assertFalse((self.racine / absent / "backups").exists(),
                                     f"{joue} a écrit sous {absent}/backups")

    def test_le_verrou_suit_le_repertoire(self):
        for hote in HOTES:
            with self.subTest(hote=hote):
                verrous = self.base / f"tmp{hote}"
                verrous.mkdir()
                fini = self.jouer(hote, "log_agent_usage.py", {}, self.env("copilot", verrous))
                self.assertEqual(fini.returncode, 0, fini.stderr)
                noms = sorted(p.name for p in verrous.iterdir())
                self.assertEqual(len(noms), 1, noms)
                self.assertTrue(noms[0].startswith(f"{hote.lstrip('.')}-run-log-"), noms)
                self.assertTrue(noms[0].endswith(".lock"), noms)


if __name__ == "__main__":
    unittest.main()
