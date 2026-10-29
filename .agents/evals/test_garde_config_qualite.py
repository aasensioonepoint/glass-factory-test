#!/usr/bin/env python3
"""LA GARDE DES CONFIGS LINT/FORMAT EXISTANTES (T-01M5C1AHZM41P9C3QH6X7PEQY1).

Run: python -m pytest .agents/evals/test_garde_config_qualite.py -q

Deux étages.

  * UNITÉS de `.agents/bin/config_qualite_guard.py`, chargé par chemin : la liste
    fermée et ses bornes nommées, les deux motifs, le repli de casse, l'existence
    (création permise), l'UNION des formes (seule la forme BRUTE existe, `os.lstat`
    simulé — vrai aussi sur un FS insensible à la casse), l'octroi valide, échu,
    malformé, illisible, l'octroi par un ALIAS de dossier (parents résolus), le refus
    hors racine qui nomme le marqueur, et la CLI (formes NUL sur STDIN, rc 0/2/3,
    verdict rc 0 en OCTETS sous une sortie texte qui traduirait `\\n`).
  * TROIS HÔTES (Claude `protect-paths.sh`, jumeaux `.codex` et `.gemini`
    `protect_paths.py`) sur des projets jetables, chacun copié fichier par fichier :
    DÉSARMÉ, tout passe — module retiré compris ; ARMÉ, la config existante est
    refusée, la création passe, l'octroi passe avec `hook.warn`, le module retiré,
    VIDE, qui sort 0 ou lève à l'import refuse tout ; le NOM écrit d'un lien
    symbolique (vers un fichier hors liste) et un lien PENDANT au nom de config sont
    refusés — les jumeaux relisent la charge BRUTE, avant résolution, et leur
    lecture brute rend les mêmes chemins que `paths_from_payload` ; un brut dont le
    `lstat` échoue est jugé (fail-closed) ; l'octroi vaut à travers un lien de
    dossier et pour le nom d'un lien écrit en absolu sous un alias, sur les trois
    hôtes ; une config hors racine reste refusée malgré un octroi absolu ;
    marqueur, octroi et graine sont refusés à l'écriture ; sous
    `KIT_CODE_PROTEGE`, l'octroi config sans octroi kit laisse le refus kit-code, et
    l'octroi kit sans octroi config laisse le refus config-qualite.

ADOPTANT : la graine ne voyage pas comme graine (racine des graines `strip:`) ; le
témoin qui la copie en marqueur est SAUTÉ, et le dit, là où elle est absente. Le
chemin des graines est COMPOSÉ, jamais écrit d'un bloc.
"""
from __future__ import annotations

import concurrent.futures
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
GIT = shutil.which("git")
GUARD = ROOT / ".agents" / "bin" / "config_qualite_guard.py"
GATES = "/".join((".agents", "state", "gates"))
SEED_DIR = "/".join((".agents", "adopter-seed", "gates"))
MARKER = "CONFIG_QUALITE_PROTEGE"
GRANT = "CONFIG_QUALITE_AUTORISE"
FAR = "2099-01-01T00:00Z"

_spec = importlib.util.spec_from_file_location("garde_config_qualite_sous_test", GUARD)
cq = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cq
_spec.loader.exec_module(cq)

COPIED = (
    ".claude/hooks/protect-paths.sh",
    ".claude/hooks/emit-event.sh",
    ".codex/hooks/_common.py",
    ".codex/hooks/protect_paths.py",
    ".gemini/hooks/_common.py",
    ".gemini/hooks/protect_paths.py",
    ".agents/bin/events.py",
    ".agents/bin/kit_code_guard.py",
    ".agents/bin/config_qualite_guard.py",
    ".agents/vendor/cadre/ledger/redaction.py",
)
HOSTS = ("claude", ".codex", ".gemini")


class ListeEtMotifsTests(unittest.TestCase):

    def test_la_liste_fermee_et_ses_bornes_nommees(self):
        for name in (".eslintrc.json", "eslint.config.mjs", ".prettierrc", "biome.json", "ruff.toml",
                     ".editorconfig", ".golangci.yml", ".rubocop.yml", "checkstyle.xml", ".coveragerc",
                     ".flake8", ".pylintrc", "mypy.ini", ".semgrepignore", ".clang-format",
                     ".swiftlint.yml", ".hadolint.yaml", ".yamllint", ".eslintignore"):
            with self.subTest(name=name):
                self.assertTrue(cq.is_config_name(name))
        for name in ("pyproject.toml", "setup.cfg", "tsconfig.json", "jest.config.js",
                     "vitest.config.ts", "pytest.ini", "package.json", ".gitleaks.toml", "vite.config.ts"):
            with self.subTest(hors_liste=name):
                self.assertFalse(cq.is_config_name(name))

    def test_les_deux_motifs(self):
        # kills M4 (motifs retirés)
        for name in ("eslint.config.base.mjs", "prettier.config.shared.cjs", ".eslintrc.base.json",
                     ".stylelintrc.local.yaml"):
            with self.subTest(name=name):
                self.assertNotIn(name, cq.CONFIG_NAMES)
                self.assertTrue(cq.is_config_name(name))

    def test_le_nom_est_replie(self):
        # kills M3 (repli de casse retiré)
        self.assertEqual(cq.folded_name("Web/.ESLintRC.json"), ".eslintrc.json")
        self.assertEqual(cq.folded_name("x\\.eslintrc.json."), ".eslintrc.json")
        self.assertTrue(cq.is_config_name(cq.folded_name(".ESLintRC.json")))


class RaisonTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / GATES).mkdir(parents=True)
        (self.root / ".eslintrc.json").write_text("{}", encoding="utf-8")
        (self.root / ".ESLintRC.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def reason(self, *forms, now=None):
        return cq.config_qualite_reason(forms, str(self.root), now)

    def grant(self, text):
        (self.root / GATES / GRANT).write_text(text, encoding="utf-8")

    def test_existante_refusee_absente_permise(self):
        # kills M1 (refus toujours : la création lue refusée) and M2 (accord toujours)
        self.assertEqual(self.reason(".eslintrc.json")[1], "config-qualite")
        self.assertEqual(self.reason(str(self.root / ".eslintrc.json"))[1], "config-qualite")
        self.assertEqual(self.reason("biome.json"), ("", "", ""))
        self.assertEqual(self.reason("README.md"), ("", "", ""))

    def test_casse_mixte_refusee(self):
        # kills M3 — le fichier porte CE nom, donc il existe sur tout FS
        self.assertEqual(self.reason(".ESLintRC.json")[1], "config-qualite")

    def test_union_seule_la_forme_brute_existe(self):
        # kills M5 (existence jugée sur la seule forme repliée)
        brute = "Web/.ESLINTRC.JSON"
        vrai_lstat = os.lstat

        def lstat(p, *a, **k):
            if str(p).endswith(brute):
                return vrai_lstat(self.root)
            raise FileNotFoundError(p)

        with mock.patch.object(cq.os, "lstat", lstat):
            self.assertEqual(self.reason(brute, "web/.eslintrc.json")[1], "config-qualite")
            self.assertEqual(self.reason("web/.eslintrc.json"), ("", "", ""))

    def test_erreur_de_lstat_compte_comme_presente(self):
        with mock.patch.object(cq.os, "lstat", side_effect=PermissionError("x")):
            self.assertEqual(self.reason("biome.json")[1], "config-qualite")

    def test_octroi_valide_couvre(self):
        self.grant(f".eslintrc.json T-00000001 {FAR}\n")
        self.assertEqual(self.reason(".eslintrc.json")[1:], ("config-qualite-octroi",
                                                              f".eslintrc.json T-00000001 {FAR}"))
        self.grant(f"web/ T-01M5C1AHZM41P9C3QH6X7PEQY1 {FAR}\n")
        (self.root / "web").mkdir()
        (self.root / "web" / ".prettierrc").write_text("{}", encoding="utf-8")
        self.assertEqual(self.reason("web/.prettierrc")[1], "config-qualite-octroi")
        self.assertEqual(self.reason(".eslintrc.json")[1], "config-qualite")

    def test_octroi_echu_ou_malforme_ignore_et_compte(self):
        # kills M6 (échéance ignorée)
        self.grant(".eslintrc.json T-00000001 2020-01-01T00:00Z\n")
        r = self.reason(".eslintrc.json")
        self.assertEqual(r[1], "config-qualite")
        self.assertIn("1 ligne(s) d'octroi ignorée(s) : 1 échue", r[0])
        self.grant(".eslintrc.json T-1 demain\nREADME.md T-00000001 " + FAR + "\n")
        r = self.reason(".eslintrc.json")
        self.assertEqual(r[1], "config-qualite")
        self.assertIn("1 hors liste, 1 malformée", r[0])

    def test_octroi_illisible_refuse(self):
        (self.root / GATES / GRANT).mkdir()
        r = self.reason(".eslintrc.json")
        self.assertEqual(r[1], "config-qualite")
        self.assertIn("ILLISIBLE", r[0])

    def test_octroi_horloge_injectee(self):
        self.grant(".eslintrc.json T-00000001 2030-01-01T00:00Z\n")
        avant = datetime(2029, 1, 1, tzinfo=timezone.utc)
        apres = datetime(2031, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.reason(".eslintrc.json", now=avant)[1], "config-qualite-octroi")
        self.assertEqual(self.reason(".eslintrc.json", now=apres)[1], "config-qualite")

    def test_octroi_par_un_alias_de_dossier(self):
        # kills « parents non résolus » : un chemin absolu qui passe par un lien VERS la
        # racine (la racine résolue, le chemin par l'alias) est sous la racine
        self.grant(f".eslintrc.json T-00000001 {FAR}\n")
        with tempfile.TemporaryDirectory() as dehors:
            alias = Path(dehors) / "alias"
            try:
                os.symlink(self.root, alias)
            except (OSError, NotImplementedError):
                self.skipTest("l'OS refuse de créer un lien symbolique ici : alias non joué")
            self.assertEqual(self.reason(str(alias / ".eslintrc.json"))[1:],
                             ("config-qualite-octroi", f".eslintrc.json T-00000001 {FAR}"))

    def test_hors_racine_le_refus_nomme_le_marqueur(self):
        # kills « remède qui ment » : hors racine, aucun octroi ne vaut — le refus le dit,
        # et ne renvoie jamais à une ligne d'octroi
        with tempfile.TemporaryDirectory() as dehors:
            cfg = Path(dehors) / ".eslintrc.json"
            cfg.write_text("{}", encoding="utf-8")
            self.grant(f"{cfg.as_posix()} T-00000001 {FAR}\n")
            raison, regle, octroi = self.reason(str(cfg))
        self.assertEqual((regle, octroi), ("config-qualite", ""))
        self.assertIn("HORS de la racine", raison)
        self.assertIn("seul le pilote lève ce refus, en retirant le marqueur", raison)
        self.assertNotIn("par une ligne", raison)

    def cli(self, data: bytes):
        return subprocess.run([sys.executable, "-B", str(GUARD), "--root", str(self.root)],
                              input=data, capture_output=True, timeout=60)

    def test_cli_nul_sur_stdin(self):
        self.assertEqual(self.cli(b".eslintrc.json\0").returncode, 2)
        p = self.cli(b"biome.json\0")
        self.assertEqual((p.returncode, p.stdout.decode()), (0, "CONFIG_QUALITE_OK\n"),
                         "rc 0 porte le verdict positif que protect-paths.sh exige")
        self.assertEqual(self.cli(b"").returncode, 2, "STDIN vide : refus")
        self.grant(f".eslintrc.json T-00000001 {FAR}\n")
        p = self.cli(b".eslintrc.json\0/hors/racine/.eslintrc.json\0")
        self.assertEqual(p.returncode, 2, "une forme visée hors racine ne s'octroie pas")
        p = self.cli(b".eslintrc.json\0")
        self.assertEqual((p.returncode, p.stdout.decode()),
                         (3, f"CONFIG_QUALITE_OCTROI .eslintrc.json T-00000001 {FAR}\n"),
                         "rc 3 porte le préfixe positif que protect-paths.sh exige")

    def test_cli_verdict_ok_en_octets(self):
        # kills « verdict rc 0 en mode texte » : une sortie texte qui traduit `\n` en
        # `\r\n` (Windows) ne doit pas toucher les octets que protect-paths.sh compare
        brut = io.BytesIO()
        sortie = io.TextIOWrapper(brut, encoding="utf-8", newline="\r\n")
        entree = io.TextIOWrapper(io.BytesIO(b"biome.json\0"), encoding="utf-8")
        with mock.patch.object(sys, "stdin", entree), mock.patch.object(sys, "stdout", sortie):
            rc = cq.main(["--root", str(self.root)])
            sortie.flush()
        self.assertEqual((rc, brut.getvalue()), (0, b"CONFIG_QUALITE_OK\n"))


class ProtectedReasonTests(unittest.TestCase):

    def test_la_regle_n_est_pas_dans_protected_reason(self):
        # kills M9 (règle par nom dans protected_reason : la création serait refusée)
        for host in (".codex", ".gemini"):
            prog = ("import sys; sys.path.insert(0, sys.argv[1]); import protect_paths as m; "
                    "print(m.protected_reason('biome.json')[1]); print(m.protected_reason('.eslintrc.json')[1])")
            with self.subTest(host=host), tempfile.TemporaryDirectory() as ev:
                p = subprocess.run([sys.executable, "-B", "-c", prog, str(ROOT / host / "hooks")],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60,
                                   env={**os.environ, "AGENTS_EVENTS_DIR": ev})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout, "\n\n")

    def test_la_lecture_brute_rend_les_chemins_de_la_charge(self):
        """`raw_payload_paths` recopie les clés de `_common.paths_from_payload` : même
        nombre de chemins, clé par clé et pour les lignes de patch, sur les deux jumeaux."""
        prog = ("import json, sys; sys.path.insert(0, sys.argv[1]); import protect_paths as m; "
                "out = []\n"
                "for k in ('file_path', 'filePath', 'path', 'target_file', 'target', 'filename'):\n"
                "    d = {'tool_input': {k: 'web\\\\.eslintrc.json'}}\n"
                "    out.append([k, m.raw_payload_paths(d), len(m.paths_from_payload(d))])\n"
                "for k in ('command', 'patch', 'input', 'raw'):\n"
                "    d = {'tool_input': {k: '*** Update File: biome.json\\n*** Add File: a/ruff.toml'}}\n"
                "    out.append([k, m.raw_payload_paths(d), len(m.paths_from_payload(d))])\n"
                "d = {'_raw': '*** Delete File: .prettierrc'}\n"
                "out.append(['_raw', m.raw_payload_paths(d), len(m.paths_from_payload(d))])\n"
                "print(json.dumps(out))")
        for host in (".codex", ".gemini"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as ev:
                p = subprocess.run([sys.executable, "-B", "-c", prog, str(ROOT / host / "hooks")],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60,
                                   env={**os.environ, "AGENTS_EVENTS_DIR": ev})
                self.assertEqual(p.returncode, 0, p.stderr)
                for key, raws, n in json.loads(p.stdout):
                    with self.subTest(key=key):
                        self.assertEqual(len(raws), n)
                        self.assertTrue(all("\\" not in r for r in raws), raws)
                        self.assertTrue(raws)

    def test_lstat_illisible_juge_le_brut(self):
        """`_feuille_est_lien` est FAIL-CLOSED : un brut dont le `lstat` lève (octet nul,
        `ValueError`) est jugé seul, comme un lien de feuille, sur les deux jumeaux."""
        # kills ME (`return False` sur OSError/ValueError dans `_feuille_est_lien`)
        prog = ("import sys; sys.path.insert(0, sys.argv[1]); import protect_paths as m; "
                "print(m._feuille_est_lien('web/a\\0b'))")
        for host in (".codex", ".gemini"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as ev:
                p = subprocess.run([sys.executable, "-B", "-c", prog, str(ROOT / host / "hooks")],
                                   capture_output=True, text=True, cwd=str(ROOT), timeout=60,
                                   env={**os.environ, "AGENTS_EVENTS_DIR": ev})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout, "True\n")


# Le module de garde REMPLACÉ, pour les rangées « garde illisible » (graine : « Marqueur
# posé et garde illisible : toute écriture est refusée »).
GUARD_TEXTS = {
    "vide": "",
    "exit0": "import sys\nsys.exit(0)\n",
    "exit3": "import sys\nsys.exit(3)\n",
    "raise": "raise RuntimeError('garde cassée')\n",
}


def _projet(base: Path, name: str, marker=None, grant=None, kit=False, kit_grant=None,
            drop_guard=False, files=(), guard_text=None, links=()) -> Path:
    root = base / name
    root.mkdir()
    subprocess.run([GIT, "init", "-q", str(root)], check=True, timeout=60)
    for rel in COPIED:
        src = ROOT / rel
        if not src.exists() or (drop_guard and rel.endswith("config_qualite_guard.py")):
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if guard_text is not None:
        (root / ".agents" / "bin" / "config_qualite_guard.py").write_text(guard_text, encoding="utf-8")
    gates = root / GATES
    gates.mkdir(parents=True, exist_ok=True)
    if marker is not None:
        if isinstance(marker, Path):
            shutil.copy2(marker, gates / MARKER)
        else:
            (gates / MARKER).write_text(marker, encoding="utf-8")
    if grant is not None:
        (gates / GRANT).write_text(grant, encoding="utf-8")
    if kit:
        (gates / "KIT_CODE_PROTEGE").write_text("", encoding="utf-8")
    if kit_grant is not None:
        (gates / "KIT_CODE_AUTORISE").write_text(kit_grant, encoding="utf-8")
    for rel in (".eslintrc.json", ".agents/bin/.editorconfig", *files):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n", encoding="utf-8")
    for rel, target in links:
        link = root / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link)
    return root


def _rules(evdir: Path, kind: str) -> list:
    out = []
    for f in sorted(evdir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("kind") == kind:
                out.append((o.get("data") or {}).get("rule"))
    return out


def _edit(base: Path, root: Path, host: str, path: str, charge=None) -> str:
    """`0`, `0+warn:<règle>` ou `deny:<règle>` — la règle lue au journal des hooks.
    `charge` remplace la charge Write sur `path` (un `apply_patch` des jumeaux)."""
    ev = Path(tempfile.mkdtemp(prefix="ev-", dir=str(base)))
    payload = json.dumps(charge or {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})
    env = {**os.environ, "AGENTS_EVENTS_DIR": str(ev), "CADRE_STATE_DIR": str(base / "cadre-state")}
    if host == "claude":
        env["CLAUDE_PROJECT_DIR"] = str(root)
        p = subprocess.run([BASH, str(root / ".claude/hooks/protect-paths.sh")], input=payload,
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=120)
        denied = p.returncode == 2
        if p.returncode not in (0, 2):
            return f"CRASH{p.returncode}"
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
        if host == ".codex":
            env["AGENTS_HOOK_HOST"] = "codex"
        p = subprocess.run([sys.executable, "-B", str(root / host / "hooks/protect_paths.py")], input=payload,
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=120)
        if p.returncode != 0:
            return f"CRASH{p.returncode}"
        denied = '"deny"' in p.stdout
    if denied:
        deny = _rules(ev, "hook.deny")
        return "deny:" + (deny[-1] if deny else "?")
    warn = _rules(ev, "hook.warn")
    return "0+warn:" + ",".join(warn) if warn else "0"


# (id, projet, chemin, attendu sur les trois hôtes)
ROWS = [
    ("desarme-config", "off", ".eslintrc.json", "0"),
    ("desarme-sans-module", "offnomod", ".eslintrc.json", "0"),
    ("arme-config", "on", ".eslintrc.json", "deny:config-qualite"),
    ("arme-config-abs", "on", "<ROOT>/.eslintrc.json", "deny:config-qualite"),
    ("arme-config-casse", "on", ".ESLINTRC.JSON", "deny:config-qualite"),
    ("arme-creation", "on", "biome.json", "0"),
    ("arme-ordinaire", "on", "README.md", "0"),
    ("arme-octroi", "grant", ".eslintrc.json", "0+warn:config-qualite-octroi"),
    # Chemin ABSOLU sous une racine qui passe par un alias (`/var` → `/private/var` sous
    # macOS) : l'octroi vaut, et UN seul warn (le brut n'est pas rejugé seul).
    ("arme-octroi-abs", "grant", "<ROOT>/.eslintrc.json", "0+warn:config-qualite-octroi"),
    # Config EXISTANTE hors de la racine, octroi ABSOLU qui la nomme : refusée quand même
    # (aucune clé sous la racine) — la politique, pas le message, que RaisonTests épingle.
    ("arme-hors-racine-octroi-abs", "hors", "<BASE>/dehors/.eslintrc.json", "deny:config-qualite"),
    ("arme-sans-module", "nomod", "README.md", "deny:config-qualite-illisible"),
    ("arme-module-vide", "vide", "README.md", "deny:config-qualite-illisible"),
    ("arme-module-exit0", "exit0", "README.md", "deny:config-qualite-illisible"),
    ("arme-module-exit3", "exit3", "README.md", "deny:config-qualite-illisible"),
    ("arme-module-raise", "raise", "README.md", "deny:config-qualite-illisible"),
    ("ecrit-marqueur", "off", GATES + "/" + MARKER, "deny:config-qualite-arming"),
    ("ecrit-marqueur-casse", "off", GATES + "/" + MARKER.lower(), "deny:config-qualite-arming"),
    ("ecrit-octroi", "off", GATES + "/" + GRANT, "deny:config-qualite-sortie"),
    ("ecrit-graine", "off", SEED_DIR + "/" + MARKER, "deny:seed-config-qualite-protege"),
    ("octroi-config-sans-octroi-kit", "kitcq", ".agents/bin/.editorconfig", "deny:kit-code"),
    ("octroi-kit-sans-octroi-config", "kitgrant", ".agents/bin/.editorconfig", "deny:config-qualite"),
    ("octroi-kit-controle", "kitgrant", ".agents/bin/x.py", "0+warn:kit-code-octroi"),
]

# Les liens symboliques, à part : sautés là où l'OS refuse d'en créer (Windows sans droit).
LINKS = (("web/.eslintrc.json", "../config/eslint-base.json"), ("biome.json", "cible-absente.json"))
ROWS_LIENS = [
    ("arme-lien", "lien", "web/.eslintrc.json", "deny:config-qualite"),
    ("arme-lien-pendant", "lien", "biome.json", "deny:config-qualite"),
    ("arme-lien-cible-hors-liste", "lien", "config/eslint-base.json", "0"),
    # L'octroi vaut sur les trois hôtes : le NOM d'un lien de feuille écrit en absolu sous
    # un alias de la racine (`/var` → `/private/var`), et un fichier atteint par un lien
    # de DOSSIER (`web -> shared`, octroi `shared/`) — parents résolus dans la clé.
    ("arme-lien-octroi-abs", "lienoctroi", "<ROOT>/web/.eslintrc.json", "0+warn:config-qualite-octroi"),
    ("arme-dossier-lien-octroi", "dossierlien", "web/.eslintrc.json", "0+warn:config-qualite-octroi"),
]


# `apply_patch` des jumeaux en chemins ABSOLUS : un fichier existant hors liste et une
# config imbriquée absente, chacun jugé seul — la création passe (aucune union des bruts).
PATCH_ABS = ("*** Begin Patch\n*** Update File: <ROOT>/README.md\n"
             "*** Add File: <ROOT>/sub/.eslintrc.json\n*** End Patch")
TWINS = (".codex", ".gemini")


def _liens_possibles(base: Path) -> bool:
    try:
        os.symlink("x", base / "sonde-lien")
    except (OSError, NotImplementedError):
        return False
    return True


@unittest.skipIf(BASH is None or GIT is None, "bash ou git absent du PATH : les trois hôtes ne sont pas exerçables")
class TroisHotesTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="cq-"))
        kit_g = f".agents/bin/ T-00000001 {FAR}\n"
        cq_g = f".agents/bin/.editorconfig T-00000001 {FAR}\n"
        cls.projets = {
            "off": _projet(cls.base, "off"),
            "offnomod": _projet(cls.base, "offnomod", drop_guard=True),
            "on": _projet(cls.base, "on", marker=""),
            "grant": _projet(cls.base, "grant", marker="", grant=f".eslintrc.json T-00000001 {FAR}\n"),
            "nomod": _projet(cls.base, "nomod", marker="", drop_guard=True),
            "kitcq": _projet(cls.base, "kitcq", marker="", grant=cq_g, kit=True),
            "kitgrant": _projet(cls.base, "kitgrant", marker="", kit=True, kit_grant=kit_g),
            "patch": _projet(cls.base, "patch", marker="", files=("README.md",)),
        }
        dehors = cls.base / "dehors" / ".eslintrc.json"
        dehors.parent.mkdir()
        dehors.write_text("x\n", encoding="utf-8")
        cls.projets["hors"] = _projet(cls.base, "hors", marker="",
                                      grant=f"{dehors.as_posix()} T-00000001 {FAR}\n")
        for name, text in GUARD_TEXTS.items():
            cls.projets[name] = _projet(cls.base, name, marker="", guard_text=text)
        cls.liens = _liens_possibles(cls.base)
        rows = list(ROWS)
        if cls.liens:
            cls.projets["lien"] = _projet(cls.base, "lien", marker="", files=("config/eslint-base.json",),
                                          links=LINKS)
            cls.projets["lienoctroi"] = _projet(
                cls.base, "lienoctroi", marker="", grant=f"web/.eslintrc.json T-00000001 {FAR}\n",
                files=("config/eslint-base.json",), links=(LINKS[0],))
            cls.projets["dossierlien"] = _projet(
                cls.base, "dossierlien", marker="", grant=f"shared/ T-00000001 {FAR}\n",
                files=("shared/.eslintrc.json",), links=(("web", "shared"),))
            rows += ROWS_LIENS
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for rid, projet, path, _want in rows:
                root = cls.projets[projet]
                for host in HOSTS:
                    jobs[(rid, host)] = ex.submit(
                        _edit, cls.base, root, host,
                        path.replace("<ROOT>", str(root)).replace("<BASE>", str(cls.base)))
            root = cls.projets["patch"]
            charge = {"tool_name": "apply_patch",
                      "tool_input": {"command": PATCH_ABS.replace("<ROOT>", str(root))}}
            for host in TWINS:
                jobs[("patch-abs", host)] = ex.submit(_edit, cls.base, root, host, "", charge)
            cls.results = {k: f.result() for k, f in jobs.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_la_table_sur_les_trois_hotes(self):
        # kills M7 (marqueur ignoré : désarmé sans module lu refusé), M8 / M8c (repli du
        # chargeur), M10 (suffixe de graine retiré), M11 (rc 3 sort 0 sur claude), M12
        for rid, _projet_, path, want in ROWS:
            got = {host: self.results[(rid, host)] for host in HOSTS}
            with self.subTest(row=rid):
                self.assertEqual(got, dict.fromkeys(HOSTS, want), f"{rid} : {path!r}")

    def test_le_refus_illisible_montre_200_caracteres_de_la_sortie(self):
        # kills « sortie reçue non bornée » et « sortie reçue absente » de protect-paths.sh
        root = _projet(self.base, "bavard", marker="",
                       guard_text="import sys\nsys.stdout.write('A' * 300)\nsys.exit(0)\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root),
               "AGENTS_EVENTS_DIR": tempfile.mkdtemp(prefix="ev-", dir=str(self.base)),
               "CADRE_STATE_DIR": str(self.base / "cadre-state")}
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "README.md", "content": "x"}})
        p = subprocess.run([BASH, str(root / ".claude/hooks/protect-paths.sh")], input=payload,
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=120)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("« " + "A" * 200 + " »", p.stderr)

    def test_apply_patch_en_chemins_absolus_sur_les_jumeaux(self):
        # kills « union des bruts d'un patch » (README existant refuserait la création)
        got = {host: self.results[("patch-abs", host)] for host in TWINS}
        self.assertEqual(got, dict.fromkeys(TWINS, "0"))

    def test_les_liens_symboliques_sur_les_trois_hotes(self):
        # kills « formes brutes retirées » des jumeaux (le nom écrit d'un lien, un lien pendant)
        if not self.liens:
            self.skipTest("l'OS refuse de créer un lien symbolique ici : rangées des liens non jouées")
        for rid, _projet_, path, want in ROWS_LIENS:
            got = {host: self.results[(rid, host)] for host in HOSTS}
            with self.subTest(row=rid):
                self.assertEqual(got, dict.fromkeys(HOSTS, want), f"{rid} : {path!r}")

    def test_la_graine_copiee_en_marqueur_arme(self):
        """L'adoptant reçoit la graine comme marqueur : CES octets arment la garde."""
        seed = ROOT / SEED_DIR / MARKER
        if not seed.is_file():
            self.skipTest(f"graine absente ({SEED_DIR} ne voyage pas) : témoin du kit seul")
        root = _projet(self.base, "graine", marker=seed)
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertEqual(_edit(self.base, root, host, ".eslintrc.json"), "deny:config-qualite")
                self.assertEqual(_edit(self.base, root, host, "biome.json"), "0")


if __name__ == "__main__":
    unittest.main()
