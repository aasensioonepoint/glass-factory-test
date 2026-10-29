#!/usr/bin/env python3
"""BANC de `tracabilite.py` (T-01M5A113DGRQB2F0RX6ECX73HN) — témoins T1-T7 de l'annexe § E du plan D3.

Dépôts JETABLES (`git init` + `git fast-import`, un processus) et board JETABLE (`tasks.py --root` sur un dossier
temporaire ; `CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR` et `HOME` jetables ; config git globale et système coupées).
AUCUN réseau : `gh` est un BOUCHON `/bin/sh` qui journalise son argv ; le PATH « sans gh » est BÂTI depuis un
répertoire bouchon qui ne porte qu'un lien vers `git` (jamais en retirant des répertoires : sur ubuntu gh et git
partagent /usr/bin). T7 compare `bilan` au VRAI hook `.githooks/commit-msg` de cet arbre, sur le même dépôt.

Mutants (appliqués puis rétablis par le dev, chacun rouge sur SON témoin) : M-T1 corps ignoré → T1 ; M-T2
validation du T-id retirée → T3 ; M-T3 fenêtre par défaut 100 → T2 ; M-T4 ambiguïté retirée → T5 ; M-T5
`--end-of-options` retiré → T5 ; M-T6 seuil 90 dans `bilan` → T7 ; M-T7 exclusion `chore(state|runs)` retirée du
palier → T7 ; M-T8 fenêtre = 200 éligibles → T7.

BORNE NOMMÉE : T6 saute, en le DISANT, si `/usr/bin/python3` manque ou est ≥ 3.11.
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent
OUTIL = BIN / "tracabilite.py"
TASKS = BIN / "tasks.py"
HOOK = BIN.parents[1] / ".githooks" / "commit-msg"
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "user.name=banc",
       "-c", "user.email=banc@example.invalid", "-c", "commit.gpgsign=false"]
ULID = "T-01M5A113DGRQB2F0RX6ECX73HN"
COUPE = "# ------------------------ >8 ------------------------"
ARGV_GH = ["pr", "list", "--state", "all", "--search", ULID, "--json", "number,title,url,state", "--limit", "50"]
BOUCHON_GH = """#!/bin/sh
: > "$GH_JOURNAL"
for a in "$@"; do printf '%s\\n' "$a" >> "$GH_JOURNAL"; done
if [ "$GH_RC" != "0" ]; then printf 'HTTP 401: Bad credentials\\n' >&2; exit "$GH_RC"; fi
printf '%s' "$GH_SORTIE"
"""


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


tr = _charger("tracabilite_banc", OUTIL)


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)
        for d in ("home", "etat", "events"):
            (cls.base / d).mkdir()
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        cls.env.update(HOME=str(cls.base / "home"), CADRE_STATE_DIR=str(cls.base / "etat"),
                       AGENTS_EVENTS_DIR=str(cls.base / "events"), GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=os.devnull, PYTHONDONTWRITEBYTECODE="1")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def git(cls, repo: Path, *argv: str, entree: bytes | None = None) -> str:
        r = subprocess.run(GIT + ["-C", str(repo), *argv], input=entree, capture_output=True, timeout=120,
                           env=cls.env, check=True)
        return r.stdout.decode("utf-8")

    @classmethod
    def depot(cls, nom: str, ops: list) -> Path:
        """Un dépôt jetable : `ops` = [(op, message)], op ∈ c (sur la branche courante), cote (branche `cote`
        partie du bout courant), fusion (fusionne `cote`). Dates croissantes : l'ordre du log est celui d'`ops`."""
        repo = cls.base / nom
        repo.mkdir()
        cls.git(repo, "init", "-q")
        tete = cls.git(repo, "symbolic-ref", "HEAD").strip()
        flux, principal, cote = [], 0, 0
        for i, (op, msg) in enumerate(ops, 1):
            data = msg.encode("utf-8")
            ref = "refs/heads/cote" if op == "cote" else tete
            parent = (cote or principal) if op == "cote" else principal
            flux.append(f"commit {ref}\nmark :{i}\ncommitter banc <banc@example.invalid> {1700000000 + i} +0000\n"
                        f"data {len(data)}\n".encode() + data + b"\n")
            if parent:
                flux.append(f"from :{parent}\n".encode())
            if op == "fusion":
                flux.append(f"merge :{cote}\n".encode())
            flux.append(b"\n")
            if op == "cote":
                cote = i
            else:
                principal = i
        cls.git(repo, "fast-import", "--quiet", entree=b"".join(flux))
        return repo

    def lancer(self, root: Path, *argv: str, env: dict | None = None, python: str = sys.executable):
        return subprocess.run([python, str(OUTIL), "--root", str(root), *argv], capture_output=True, text=True,
                              timeout=120, env=self.env if env is None else env, stdin=subprocess.DEVNULL,
                              cwd=str(self.base))

    def hook(self, repo: Path, message: str):
        fichier = self.base / "COMMIT_EDITMSG"
        fichier.write_bytes(message.encode("utf-8"))
        return subprocess.run(["bash", str(HOOK), str(fichier)], capture_output=True, text=True, timeout=120,
                              env=self.env, cwd=str(repo), stdin=subprocess.DEVNULL)

    def compte(self, sortie: str, nom: str) -> int:
        m = re.search(rf"^  {re.escape(nom)} : (\d+)$", sortie, re.M)
        self.assertIsNotNone(m, f"{nom!r} absent de :\n{sortie}")
        return int(m.group(1))


# --------------------------------------------------------------------------- T1, T2 : bilan
class TestBilan(_Base):
    def test_T1_comptes_exacts_sur_sept_commits(self):
        repo = self.depot("t1", [
            ("c", "feat: un (T-00000101)\n"),
            ("c", "fix: deux\n\nTâche: T-01M5A113DG\n"),
            ("c", "docs: trois\n\nSans-tache: commit du pilote hors board\n"),
            ("c", "chore(state): quatre\n"),
            ("c", "chore(runs): cinq\n"),
            ("cote", f"refactor: six ABT-12345\n\n# T-00000102\n{COUPE}\nT-00000103\n"),
            ("fusion", "Merge branch 'cote'\n"),
        ])
        r = self.lancer(repo, "bilan")
        self.assertEqual(r.returncode, 0, r.stderr)
        attendu = {"avec T-id": 2, "Sans-tache": 1, "fusions": 1, "chore(state|runs)": 2, "ni l'un ni l'autre": 1}
        self.assertEqual({k: self.compte(r.stdout, k) for k in attendu}, attendu, r.stdout)
        self.assertIn("bilan : 7 commits lus", r.stdout)
        self.assertRegex(r.stdout, r"(?m)^    [0-9a-f]{7,} refactor: six ABT-12345$")
        self.assertIn("palier: avertissement (3/4, seuil 95 %)", r.stdout)

    def test_T1b_caracteres_de_controle_sortent_en_point_d_interrogation(self):
        repo = self.depot("t1b", [("c", "feat: rouge \x1b[31mX\x07 fin\n")])
        r = self.lancer(repo, "bilan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("feat: rouge ?[31mX? fin", r.stdout)
        self.assertNotRegex(r.stdout, r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
        raison = tr.raison_sans_tache([b"docs: d", b"", b"Sans-tache: raison \x1b]0;titre\x07 hors board"])
        self.assertEqual(raison, "raison ?]0;titre? hors board")
        self.assertEqual(tr.resoudre("T-00000001", [{"id": "T-00000001", "task": "a\x1bb\x9bc", "state": "done"}]),
                         "- T-00000001 — a?b?c (done)")

    def test_T2_fenetre_par_defaut_200_et_bornes(self):
        repo = self.depot("t2", [("c", f"feat: c{i} (T-{i:08d})\n") for i in range(1, 202)])
        self.assertIn("bilan : 200 commits lus", self.lancer(repo, "bilan").stdout)
        self.assertIn("bilan : 5 commits lus", self.lancer(repo, "bilan", "-n", "5").stdout)
        self.assertIn("bilan : 3 commits lus", self.lancer(repo, "bilan", "--depuis", "HEAD~3").stdout)
        self.assertEqual(self.lancer(repo, "bilan", "-n", "0").returncode, 2)


# --------------------------------------------------------------------------- T3, T4 : tache
class TestTache(_Base):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.repo = cls.depot("t3", [
            ("c", f"feat: plein ({ULID})\n"),
            ("c", "fix: prefixe\n\nTâche: T-01M5A113DG\n"),
            ("c", f"docs: autre AB{ULID}\n"),
            ("c", "docs: voisine (T-01M5A113DHAAAAAAAAAAAAAAAA)\n"),
            ("cote", f"test: autre branche ({ULID})\n"),
            ("c", f"docs: commente\n\n# {ULID}\n"),
        ])
        cls.sans_gh, cls.avec_gh = cls.base / "sans-gh", cls.base / "avec-gh"
        lien = Path(shutil.which("git"))
        for d in (cls.sans_gh, cls.avec_gh):
            d.mkdir()
            (d / "git").symlink_to(lien)
        (cls.avec_gh / "gh").write_text(BOUCHON_GH, encoding="utf-8")
        (cls.avec_gh / "gh").chmod(0o755)
        cls.journal = cls.base / "gh-journal"

    def env_gh(self, dossier: Path, rc: str = "0") -> dict:
        env = dict(self.env, PATH=str(dossier), GH_JOURNAL=str(self.journal), GH_RC=rc,
                   GH_SORTIE='[{"number": 7, "title": "Titre de PR", "url": "https://example.invalid/pr/7", '
                             '"state": "MERGED"}]')
        return env

    def test_T3_id_plein_prefixe_toutes_branches_et_rien_d_autre(self):
        r = self.lancer(self.repo, "tache", ULID)
        self.assertEqual(r.returncode, 0, r.stderr)
        sujets = sorted(re.findall(r"(?m)^  [0-9a-f]+ (.*)$", r.stdout))
        self.assertEqual(sujets, sorted([f"feat: plein ({ULID})", "fix: prefixe",
                                         f"test: autre branche ({ULID})"]), r.stdout)

    def test_T3_t_id_refuse_rc_2_avant_tout_appel(self):
        for refuse in ("T-1;x", "T-00000101;x", "ABT-12345", "T-01M4XZWZ", ULID + "A"):
            with self.subTest(refuse=refuse):
                if self.journal.exists():
                    self.journal.unlink()
                r = self.lancer(self.repo, "tache", refuse, "--pr", env=self.env_gh(self.avec_gh))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertFalse(self.journal.exists(), "gh appelé malgré un T-id refusé")

    def test_T4_pr_argv_liste_exact(self):
        r = self.lancer(self.repo, "tache", ULID, "--pr", env=self.env_gh(self.avec_gh))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.journal.read_text(encoding="utf-8").splitlines(), ARGV_GH)
        self.assertIn("pr : #7 MERGED Titre de PR — https://example.invalid/pr/7", r.stdout)

    def test_T4_titre_de_pr_porteur_d_esc_sort_en_point_d_interrogation(self):
        env = dict(self.env_gh(self.avec_gh),
                   GH_SORTIE='[{"number": 8, "title": "PR \\u001b[31mrouge\\u009b", '
                             '"url": "https://example.invalid/pr/8", "state": "OPEN"}]')
        r = self.lancer(self.repo, "tache", ULID, "--pr", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pr : #8 OPEN PR ?[31mrouge? — https://example.invalid/pr/8", r.stdout)
        self.assertNotRegex(r.stdout, r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

    def test_T4_gh_absent_dit_rc_0_et_git_tourne(self):
        r = self.lancer(self.repo, "tache", ULID, "--pr", env=self.env_gh(self.sans_gh))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pr : gh absent — lien non vérifié", r.stdout)
        self.assertIn("3 commit(s)", r.stdout)

    def test_T4_gh_en_echec_rc_1(self):
        r = self.lancer(self.repo, "tache", ULID, "--pr", env=self.env_gh(self.avec_gh, rc="1"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("pr : gh a échoué (rc 1) : HTTP 401: Bad credentials", r.stdout)


# --------------------------------------------------------------------------- T5, T6 : pr-corps
class TestPrCorps(_Base):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.repo = cls.base / "t5"
        cls.repo.mkdir()
        cls.a, cls.b = cls._nouvelle("Tache alpha"), cls._nouvelle("Tache beta")
        cls.git(cls.repo, "init", "-q")
        cls.git(cls.repo, "add", "-A")
        cls.git(cls.repo, "commit", "-q", "-m", "chore(state): board de banc")
        cls.base_ref = cls.git(cls.repo, "rev-parse", "HEAD").strip()
        for msg in (f"feat: a ({cls.a})", f"fix: b\n\nTâche: {cls.b[:12]}", "docs: c (T-00009999)",
                    "docs: d\n\nSans-tache: correction de coquille hors board"):
            cls.git(cls.repo, "commit", "-q", "--allow-empty", "-F", "-", entree=msg.encode("utf-8"))

    @classmethod
    def _nouvelle(cls, titre: str) -> str:
        r = subprocess.run([sys.executable, str(TASKS), "--root", str(cls.repo), "new", titre], capture_output=True,
                           text=True, timeout=120, env=cls.env, check=True)
        return re.search(r"(T-[0-9A-Z]+) → pending", r.stdout + r.stderr).group(1)

    def test_T5_titres_inconnue_et_sans_tache(self):
        r = self.lancer(self.repo, "pr-corps", "--base", self.base_ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"- {self.a} — Tache alpha (pending)", r.stdout)
        self.assertIn(f"- {self.b} — Tache beta (pending)", r.stdout)
        self.assertIn("- T-00009999 — inconnue au board", r.stdout)
        self.assertRegex(r.stdout, r"(?m)^## Sans tâche\n\n- [0-9a-f]+ docs: d — correction de coquille hors board$")

    def test_T5_prefixe_porte_par_deux_taches_est_ambigu(self):
        jumelles = [{"id": self.b[:12] + "A" * 14, "task": "x", "state": "pending"},
                    {"id": self.b[:12] + "B" * 14, "task": "y", "state": "done"}]
        sortie = io.StringIO()
        with mock.patch.object(tr, "lire_taches", return_value=jumelles), redirect_stdout(sortie):
            rc = tr.main(["--root", str(self.repo), "pr-corps", "--base", self.base_ref])
        self.assertEqual(rc, 0)
        self.assertIn(f"- {self.b[:12]} — ambiguë : {jumelles[0]['id']}, {jumelles[1]['id']}", sortie.getvalue())

    def test_T5_une_base_en_forme_d_option_n_en_devient_jamais_une(self):
        sortie = self.base / "sortie-t5"
        sortie.mkdir()
        r = self.lancer(self.repo, "pr-corps", f"--base=--output={sortie / 'x'}")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(os.listdir(sortie), [], "git a écrit un fichier : la ref est devenue une option")

    def test_board_illisible_dit_sans_traceback(self):
        casse = self.base / "casse"
        (casse / ".agents" / "state" / "board").mkdir(parents=True)
        (casse / ".agents" / "state" / "board" / "TASKS.json").write_text("{pas du json", encoding="utf-8")
        self.git(casse, "init", "-q")
        self.git(casse, "commit", "-q", "--allow-empty", "-m", "chore: base")
        self.git(casse, "commit", "-q", "--allow-empty", "-m", "feat: x (T-00000101)")
        r = self.lancer(casse, "pr-corps", "--base", "HEAD~1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("board illisible (Python", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_T6_interpreteur_anterieur_a_3_11_sans_traceback(self):
        ancien = "/usr/bin/python3"
        if not Path(ancien).exists():
            self.skipTest(f"{ancien} absent : T6 non joué")
        v = subprocess.run([ancien, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
                           capture_output=True, text=True, timeout=60)
        if v.stdout.strip() != "True":
            self.skipTest(f"{ancien} n'est pas antérieur à 3.11 : T6 non joué")
        for argv in (["--help"], ["bilan"], ["tache", "T-00009999"]):
            with self.subTest(argv=argv):
                r = self.lancer(self.repo, *argv, python=ancien)
                self.assertEqual(r.returncode, 0, r.stderr[-300:])
                self.assertNotIn("Traceback", r.stderr)
        r = self.lancer(self.repo, "pr-corps", "--base", self.base_ref, python=ancien)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(r.returncode == 0 or (r.returncode == 1 and "board illisible" in r.stderr),
                        (r.returncode, r.stderr[-300:]))


# --------------------------------------------------------------------------- T7 : parité avec le VRAI hook
class TestParite(_Base):
    def palier_bilan(self, repo: Path) -> tuple[str, str]:
        r = self.lancer(repo, "bilan")
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r"^palier: (avertissement|refus) \((\d+/\d+), seuil 95 %\)", r.stdout, re.M)
        self.assertIsNotNone(m, r.stdout)
        return m.group(1), m.group(2)

    def palier_hook(self, repo: Path) -> tuple[int, str]:
        r = self.hook(repo, "feat: sans numero\n")
        m = re.search(r"palier (\d+/\d+)", r.stderr)
        self.assertIsNotNone(m, r.stderr)
        return r.returncode, m.group(1)

    def test_T7_19_sur_20_refus_18_sur_20_avertissement(self):
        for nom, conformes, verdict, rc in (("p19", 19, "refus", 1), ("p18", 18, "avertissement", 0)):
            with self.subTest(nom=nom):
                ops = [("c", f"feat: c{i} (T-{i:08d})\n") for i in range(conformes)]
                ops += [("c", f"docs: sans numero {i}\n") for i in range(20 - conformes)]
                repo = self.depot(nom, ops)
                self.assertEqual(self.palier_bilan(repo), (verdict, f"{conformes}/20"))
                self.assertEqual(self.palier_hook(repo), (rc, f"{conformes}/20"))

    def test_T7_plus_de_200_commits_les_deux_lectures_de_la_fenetre_divergent(self):
        # 30 éligibles non conformes HORS de la fenêtre ; dans les 200 derniers hors fusion : 30 chore(state|runs)
        # sans numéro, 162 conformes (dont un sur une branche fusionnée), 8 non conformes ; 2 fusions sans numéro.
        # Fenêtre du hook : 162/170 → refus. 200 éligibles (M-T8) ou exclusion retirée (M-T7) : 162/200.
        ops = [("c", f"docs: ancien {i}\n") for i in range(30)]
        recents = []
        for i in range(161):
            recents.append(("c", f"feat: c{i} (T-{i:08d})\n"))
            if i % 5 == 0 and len([o for o in recents if o[1].startswith("chore")]) < 30:
                recents.append(("c", f"chore({'state' if i % 12 else 'runs'}): etat {i}\n"))
            if i % 20 == 0 and len([o for o in recents if o[1].startswith("docs")]) < 8:
                recents.append(("c", f"docs: non conforme {i}\n"))
        recents[100:100] = [("cote", "test: cote (T-00099999)\n"), ("fusion", "Merge branch 'cote'\n")]
        recents.append(("fusion", "Merge branch 'cote' encore\n"))
        ops += recents
        self.assertEqual(sum(1 for o, m in recents if m.startswith("chore")), 30)
        self.assertEqual(sum(1 for o, m in recents if m.startswith("docs")), 8)
        repo = self.depot("p200", ops)
        self.assertEqual(self.palier_bilan(repo), ("refus", "162/170"))
        self.assertEqual(self.palier_hook(repo), (1, "162/170"))

    def test_C16_le_predicat_unitaire_est_celui_du_hook(self):
        repo = self.depot("pred", [("c", f"feat: c{i} (T-{i:08d})\n") for i in range(20)])
        for message in ("feat: x (T-00000101)", "feat: x\n\n# T-00000101", f"feat: x\n{COUPE}\nT-00000101",
                        "feat: x\n\nSans-tache: court", "feat: x\n\nSans-tache: commit du pilote hors board",
                        "feat: x\n\nSans-tache: a b c d e f g h i j", "feat: x\n\n  Sans-tache: indentee hors regle",
                        "feat: x ABT-12345", "feat: x T-12", "feat: x T-01M4XZWZ", f"feat: x {ULID}A",
                        "feat: x\n\nTâche: T-01M5A113DG", "feat: x_T-00000101", "feat: x (T-00000101_y)"):
            with self.subTest(message=message):
                accepte = tr.porte(message.encode("utf-8").split(b"\n")) is not None
                self.assertEqual(self.hook(repo, message + "\n").returncode == 0, accepte)


if __name__ == "__main__":
    unittest.main()
