#!/usr/bin/env python3
"""Témoins de la jambe `secrets` de setup_projet.py (T-00001103, lot B).

La jambe LIT et PROPOSE : elle relève les fichiers non suivis dont le NOM porte
un jeton du lexique fermé de `.codex/hooks/protect_paths.py`, n'ouvre jamais
leur contenu, n'écrit rien, et propose des refus `Read(./…)` pour
`.claude/settings.local.json`. Mutants et le témoin qui les rougit :
appel retiré de `main` ou joué avant `_hooks_git` -> test_jambe_jouee_apres_hooks_git ;
règles `/…` et `~…` lues comme relatives à la racine -> test_couverture_par_motifs ; jeton retiré du
lexique -> test_parite_du_lexique ; écriture de settings.local.json ->
test_rien_ecrit ; contenu ouvert -> test_contenu_jamais_ouvert ; règle `**`
ignorée -> test_couverture_par_motifs ; borne retirée -> test_borne_des_lignes ;
`creatrice=True` -> test_rien_ecrit (rc) ; json.dumps retiré ->
test_nom_hostile_une_ligne.

Garde d'amorçage détaché (R2, TOCTOU sur `.maintenance.lock`) : appel retiré de `main` ou joué
sous --dry-run -> test_main_refuse_pendant_amorcage / test_dry_run_non_refuse ; `rc is not None`
ignoré -> test_rc_ecrit_non_vivant ; exclusion de soi ou du parent retirée -> test_soi_et_parent ;
os.kill sauté -> test_pid_mort ; PermissionError lue comme mort -> test_permission_vivant.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SETUP = Path(__file__).resolve().parent / "setup_projet.py"
GARDE = ROOT / ".codex" / "hooks" / "protect_paths.py"
GIT = shutil.which("git")
_SENTINELLE = "SENTINELLE-CONTENU-7f3a"


def _module():
    with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
        import setup_projet  # noqa: PLC0415 — module du kit, en processus
    return setup_projet


def _tuple_du_module(chemin: Path, nom: str) -> tuple:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for n in arbre.body:
        if isinstance(n, ast.Assign) and any(getattr(c, "id", None) == nom for c in n.targets):
            return ast.literal_eval(n.value)
    raise AssertionError(f"{nom} absent de {chemin}")


def _empreintes(racine: Path) -> dict[str, str]:
    return {str(p.relative_to(racine)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(racine.rglob("*")) if p.is_file() and ".git" not in p.parts}


class PariteLexiqueTests(unittest.TestCase):
    def test_parite_du_lexique(self):
        s = _module()
        self.assertEqual(s._NOMS_SENSIBLES, _tuple_du_module(GARDE, "SECRET_NAMES"))
        self.assertEqual(s._EXTENSIONS_SENSIBLES, _tuple_du_module(GARDE, "SECRET_EXTENSIONS"))

    def test_jambe_jouee_apres_hooks_git(self):
        arbre = ast.parse(SETUP.read_text(encoding="utf-8"))
        main = next(n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        appels = [n.func.id for n in sorted((n for n in ast.walk(main) if isinstance(n, ast.Call)
                                             and isinstance(n.func, ast.Name)),
                                            key=lambda n: (n.lineno, n.col_offset))]
        self.assertIn("_secrets", appels, "la jambe secrets n'est pas jouée par main")
        self.assertLess(appels.index("_hooks_git"), appels.index("_secrets"))
        self.assertLess(appels.index("_secrets"), appels.index("_bilan"))


@unittest.skipIf(GIT is None, "SAUT ANNONCÉ — git requis pour la jambe secrets")
class JambeSecretsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="setup-deny-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.racine = self.tmp / "r"
        subprocess.run([GIT, "init", "-q", str(self.racine)], check=True, capture_output=True)
        (self.racine / ".claude").mkdir()
        self.s = _module()

    def _poser(self, *rels: str) -> None:
        for rel in rels:
            chemin = self.racine / rel
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(f"{_SENTINELLE}\n", encoding="utf-8")

    def _regles(self, *refus: str, nom: str = "settings.json") -> None:
        (self.racine / ".claude" / nom).write_text(
            json.dumps({"permissions": {"deny": list(refus)}}), encoding="utf-8")

    def _jouer(self):
        rapport = self.s.Rapport(False)
        flux = io.StringIO()
        with contextlib.redirect_stdout(flux):
            self.s._secrets(self.racine, rapport)
        out = flux.getvalue()
        jambe = [x for x in out.splitlines() if x.startswith("setup: secrets : ")]
        self.assertEqual(len(jambe), 1, out)
        proposes = [json.loads(x[len("secrets: proposé "):]) for x in out.splitlines()
                    if x.startswith("secrets: proposé ")]
        return rapport, jambe[0], proposes, out

    def test_sans_objet(self):
        self._poser("notes.txt", "src/app.py")
        rapport, jambe, proposes, _ = self._jouer()
        self.assertTrue(jambe.startswith("setup: secrets : sans objet"), jambe)
        self.assertEqual((proposes, rapport.rc), ([], 0))

    def test_rien_ecrit(self):
        self._poser(".env", "config/credentials.json", "deploy/server.pem", "notes.txt")
        self._regles("Read(./.env)")
        avant = _empreintes(self.racine)
        rapport, jambe, proposes, out = self._jouer()
        self.assertEqual(_empreintes(self.racine), avant, "la jambe a écrit")
        self.assertFalse((self.racine / ".claude" / "settings.local.json").exists())
        self.assertTrue(jambe.startswith("setup: secrets : dégradé — 2 sur 3 "), jambe)
        self.assertIn(".claude/settings.local.json", jambe)
        self.assertEqual(proposes, ["Read(./config/credentials.json)", "Read(./deploy/server.pem)"])
        self.assertEqual(rapport.rc, 0, "jambe de LECTURE : jamais le code de sortie")

    def test_contenu_jamais_ouvert(self):
        self._poser(".env", "a/id_rsa", "b/x.key")
        ouverts: list[str] = []
        vrai_open, vrai_os_open = builtins.open, os.open

        def espion(f, *a, **k):
            ouverts.append(os.fspath(f) if isinstance(f, (str, os.PathLike)) else repr(f))
            return vrai_open(f, *a, **k)

        def espion_os(f, *a, **k):
            ouverts.append(os.fspath(f))
            return vrai_os_open(f, *a, **k)

        with mock.patch("builtins.open", espion), mock.patch("io.open", espion), \
                mock.patch("os.open", espion_os):
            _, _, proposes, out = self._jouer()
        self.assertEqual(len(proposes), 3, out)
        self.assertNotIn(_SENTINELLE, out, "le contenu d'un secret a été rendu")
        lus = [f for f in ouverts if any(f.endswith(n) for n in (".env", "id_rsa", "x.key"))]
        self.assertEqual(lus, [], "un fichier de secret a été ouvert")

    def test_couverture_par_motifs(self):
        self._poser(".env", ".env.local", "a/b/credentials.json", "x.pem", "secrets/k.txt",
                    "k/server.crt")
        self._regles("Read(./.env)", "Read(./.env.*)", "Read(./**/credentials*)",
                     "Read(./**/*.pem)")
        self._regles("Read(./secrets/)", "Read(~/k/server.crt)", "Read(/k/server.crt)",
                     nom="settings.local.json")  # `/…` et `~…` ne visent pas la racine
        rapport, jambe, proposes, _ = self._jouer()
        self.assertEqual(proposes, ["Read(./k/server.crt)"], jambe)
        self._regles("Read(./secrets/)", "Read(k/*.crt)", nom="settings.local.json")
        _, jambe, proposes, _ = self._jouer()
        self.assertTrue(jambe.startswith("setup: secrets : déjà là — 6 "), jambe)
        self.assertEqual(proposes, [])

    def test_reglages_illisibles(self):
        self._poser(".env")
        (self.racine / ".claude" / "settings.local.json").write_text("{pas du json", encoding="utf-8")
        rapport, jambe, proposes, _ = self._jouer()
        self.assertIn("illisible(s), règles ignorées : .claude/settings.local.json", jambe)
        self.assertEqual((proposes, rapport.rc), (["Read(./.env)"], 0))

    def test_borne_des_lignes(self):
        self._poser(*(f"d/secret{i:02d}.txt" for i in range(25)))
        _, jambe, proposes, out = self._jouer()
        self.assertEqual(len(proposes), 20, out)
        self.assertIn("secrets: 5 autre(s) non affiché(s) (borne de 20 lignes)", out)
        self.assertTrue(jambe.startswith("setup: secrets : dégradé — 25 sur 25 "), jambe)

    def test_nom_hostile_une_ligne(self):
        if os.name != "posix":
            self.skipTest("SAUT ANNONCÉ — nom à retour à la ligne : POSIX seul")
        self._poser('x"\n$(id).env')
        _, _, proposes, out = self._jouer()
        self.assertEqual(proposes, ['Read(./x"\n$(id).env)'])
        ligne = next(x for x in out.splitlines() if x.startswith("secrets: proposé "))
        self.assertIn('\\"', ligne)
        self.assertIn("\\n", ligne)

    def test_echec_git(self):
        with mock.patch.object(self.s, "_git", lambda *_a: self.s.Sortie(128, "", "fatal: x")):
            rapport, jambe, proposes, _ = self._jouer()
        self.assertTrue(jambe.startswith("setup: secrets : dégradé — inventaire"), jambe)
        self.assertIn("fatal: x", jambe)
        self.assertEqual((proposes, rapport.rc), ([], 0))


@unittest.skipIf(os.name != "posix", "SAUT ANNONCÉ — garde d'amorçage détaché : POSIX seul")
class AmorcageDetacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="setup-amorcage-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.s = _module()

    def _etat(self, **rec) -> None:
        local = self.tmp / ".agents" / "state" / "local"
        local.mkdir(parents=True, exist_ok=True)
        (local / "amorcage.json").write_text(json.dumps(rec), encoding="utf-8")

    def _vivant(self) -> int:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc.pid

    def test_vivant_et_absent(self):
        self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp))
        pid = self._vivant()
        self._etat(pid=pid, rc=None)
        self.assertEqual(self.s._amorcage_detache_vivant(self.tmp), pid)

    def test_rc_ecrit_non_vivant(self):
        self._etat(pid=self._vivant(), rc=0)
        self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp))

    def test_soi_et_parent(self):
        for pid in (os.getpid(), os.getppid()):
            self._etat(pid=pid, rc=None)
            self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp), pid)

    def test_pid_mort(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self._etat(pid=proc.pid, rc=None)
        self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp))

    def test_permission_vivant(self):
        self._etat(pid=999999, rc=None)
        with mock.patch.object(self.s.os, "kill", side_effect=PermissionError):
            self.assertEqual(self.s._amorcage_detache_vivant(self.tmp), 999999)

    def test_illisible_ou_pid_hors_type(self):
        for rec in ({"pid": None, "rc": None}, {"pid": True, "rc": None}, {"pid": "12", "rc": None}):
            self._etat(**rec)
            self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp), rec)
        (self.tmp / ".agents" / "state" / "local" / "amorcage.json").write_text("[", encoding="utf-8")
        self.assertIsNone(self.s._amorcage_detache_vivant(self.tmp))

    def _main(self, *args: str):
        jambes = mock.Mock(return_value=False)
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(self.s, "_racine", return_value=self.tmp), \
                mock.patch.object(self.s, "_suivis", return_value=set()), \
                mock.patch.object(self.s, "_charger"), \
                mock.patch.object(self.s, "_identite_et_board", jambes), \
                mock.patch.object(self.s.sys, "dont_write_bytecode", self.s.sys.dont_write_bytecode), \
                mock.patch.dict(os.environ), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = self.s.main(["--root", str(self.tmp), *args])
        return rc, err.getvalue(), jambes

    def test_main_refuse_pendant_amorcage(self):
        pid = self._vivant()
        self._etat(pid=pid, rc=None)
        rc, err, jambes = self._main()
        self.assertEqual(rc, 2, err)
        self.assertIn(f"amorçage détaché en cours (pid {pid})", err)
        self.assertIn("« amorçage : fin » dans .agents/state/local/amorcage.log", err)
        jambes.assert_not_called()

    def test_dry_run_non_refuse(self):
        self._etat(pid=self._vivant(), rc=None)
        rc, err, jambes = self._main("--dry-run")
        self.assertNotIn("amorçage détaché", err)
        jambes.assert_called_once()


if __name__ == "__main__":
    unittest.main()
