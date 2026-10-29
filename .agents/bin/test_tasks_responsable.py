"""LE RESPONSABLE HUMAIN — `new --responsable`, verbe `responsable`, `list --responsable`.

T-01M54GEHJBGA5996W0T48JXNQ4 (E-48 D2, lot B), annexe § Témoins R1-R5. ZÉRO APPEL LLM.

Chaque témoin `r_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`, ou une
COPIE JETABLE dont un fragment littéral, présent UNE fois (asserté), est remplacé.
Chaque mutant de `MUTANTS` rejoue le SEUL témoin qui le tue, et doit le faire échouer
par une ASSERTION. Racine, HOME, `CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR` jetables ;
`CLAUDE_PROJECT_DIR`, `CLAUDE_PID` et `GIT_*` retirés des sous-processus.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import vendor_paths

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "plan_lots.py", "specs.py",
          "events.py", "record_id.py", "kickoff_guard.py", "vendor_paths.py")
#: La copie porte un résolveur COMPLET : sans lui, le pont V3 de la copie est éteint en silence (la façade dit
#: alors une cause dans `_CAUSE_SANS_RESOLVEUR_V3`). Sous-processus : rien n'entre dans le `sys.modules` du banc.
SONDE_RESOLVEUR = ("import runpy, sys; "
                   "print(runpy.run_path(sys.argv[1], run_name='sonde')['_CAUSE_SANS_RESOLVEUR_V3'])")


def copie(case: unittest.TestCase, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable du vrai `bin`, chaque ancre remplacée UNE fois."""
    base = Path(tempfile.mkdtemp(prefix="responsable-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in BIN.glob(motif):
            if not f.name.startswith("test_"):
                shutil.copy2(f, dest / f.name)
    (base / "src").symlink_to(ROOT / "src", target_is_directory=True)
    moteur = vendor_paths.exiger(ROOT, "agentic_v3")
    copie_moteur = base / moteur.relative_to(ROOT)
    copie_moteur.parent.mkdir(parents=True, exist_ok=True)
    copie_moteur.symlink_to(moteur, target_is_directory=True)
    sonde = subprocess.run([sys.executable, "-B", "-I", "-c", SONDE_RESOLVEUR, str(dest / "tasks.py")],
                           capture_output=True, text=True, timeout=120)
    case.assertEqual((sonde.returncode, sonde.stdout.strip()), (0, "None"), sonde.stderr)
    for nom, paires in mutations.items():
        cible = dest / nom
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            case.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente dans {nom} : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
    return dest


class Banc:
    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin = case, bin_
        self.d = Path(tempfile.mkdtemp(prefix="responsable-"))
        case.addCleanup(shutil.rmtree, self.d, True)
        etat = Path(tempfile.mkdtemp(prefix="responsable-etat-"))
        case.addCleanup(shutil.rmtree, etat, True)
        (self.d / ".agents" / "state" / "board").mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PID") and not k.startswith("GIT_")}
        self.env.update(HOME=str(etat / "home"), CADRE_STATE_DIR=str(etat / "cadre"),
                        AGENTS_EVENTS_DIR=str(etat / "events"), GIT_CONFIG_NOSYSTEM="1")

    def t(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=180, env=self.env)

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 0, f"{args} : {r.stdout}{r.stderr}")
        return r

    def nouvelle(self, titre: str, *extra: str) -> str:
        r = self.ok("new", titre, *extra)
        return re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M).group(1)

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def ids(self, *args: str) -> set[str]:
        return {t["id"] for t in json.loads(self.ok("list", "--json", *args).stdout)}


class Temoins:
    def r_1(self, bin_: Path) -> None:
        """R1 : `new --responsable`, verbe, `""` retire la clé."""
        b = Banc(self, bin_)
        t = b.nouvelle("tâche", "--responsable", "Ana")
        self.assertEqual(b.tache(t)["responsable"], "Ana")
        b.ok("responsable", t, "Bob")
        self.assertEqual(b.tache(t)["responsable"], "Bob")
        r = b.ok("responsable", t, "")
        self.assertNotIn("responsable", b.tache(t))
        self.assertIn("cleared", r.stdout)
        self.assertNotIn("responsable", b.tache(b.nouvelle("sans")), "absent par défaut")

    def r_2(self, bin_: Path) -> None:
        """R2 : filtre seul, combiné à `--state`, à `--chantier` ; `""` = sans responsable."""
        b = Banc(self, bin_)
        a = b.nouvelle("a", "--responsable", "Ana", "--chantier", "c1")
        a2 = b.nouvelle("a2", "--responsable", "Ana")
        bo = b.nouvelle("bo", "--responsable", "Bob", "--chantier", "c1")
        nul = b.nouvelle("nul")
        texte = b.ok("list", "--responsable", "Ana").stdout
        self.assertIn(a, texte)
        self.assertIn(a2, texte)
        self.assertNotIn(bo, texte)
        self.assertEqual(b.ids("--responsable", "Ana", "--chantier", "c1"), {a})
        self.assertEqual(b.ids("--responsable", ""), {nul})
        b.ok("start", a)
        self.assertEqual(b.ids("--responsable", "Ana", "--state", "running"), {a})
        self.assertEqual(b.ids("--responsable", "Ana", "--state", "pending"), {a2})

    def r_2b(self, bin_: Path) -> None:
        """R2b : `list --json --responsable` rend SEULES les correspondances (branche nue)."""
        b = Banc(self, bin_)
        a = b.nouvelle("a", "--responsable", "Ana")
        b.nouvelle("x")
        self.assertEqual(b.ids("--responsable", "Ana"), {a})

    def r_2c(self, bin_: Path) -> None:
        """R2c : six refus rc 2, chacun NOMME son drapeau."""
        b = Banc(self, bin_)
        a = b.nouvelle("a", "--responsable", "Ana")
        for drapeau, extra in (("--group", []), ("--task", [a]), ("--session", []), ("--epic", ["E-01"]),
                               ("--blocked-by", [a]), ("--depends-on", [a])):
            # Pas de `subTest` : il avalerait l'assertion que le mutant doit faire remonter.
            r = b.t("list", "--responsable", "Ana", drapeau, *extra)
            self.assertEqual(r.returncode, 2, f"{drapeau} : {r.stdout}{r.stderr}")
            self.assertIn(drapeau, r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def r_3(self, bin_: Path) -> None:
        """R3 : `TASKS.md` octet pour octet, même jour, avec et sans `responsable`."""
        b = Banc(self, bin_)
        t = b.nouvelle("tâche")
        vue = b.d / ".agents" / "state" / "local" / "TASKS.md"
        b.ok("render")
        avant = vue.read_bytes()
        b.ok("responsable", t, "Ana")
        b.ok("render")
        self.assertEqual(vue.read_bytes(), avant)
        self.assertNotIn("Ana", b.ok("list").stdout, "liste nue inchangée")

    def r_4(self, bin_: Path) -> None:
        """R4 : `"responsable": 3` à la main → refus qui NOMME le champ."""
        b = Banc(self, bin_)
        t = b.nouvelle("tâche")
        store = b.d / ".agents" / "state" / "board" / "TASKS.json"
        data = json.loads(store.read_text(encoding="utf-8"))
        (tache,) = [x for x in data["tasks"] if x["id"] == t]
        tache["responsable"] = 3
        store.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        r = b.t("list")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("non-string responsable", r.stderr)

    def r_5(self, bin_: Path) -> None:
        """R5 : `owner` intouché par les trois gestes."""
        b = Banc(self, bin_)
        t = b.nouvelle("tâche", "--owner", "dev-multi", "--responsable", "Ana")
        self.assertEqual(b.tache(t)["owner"], "dev-multi")
        b.ok("responsable", t, "Bob")
        self.assertEqual(b.tache(t)["owner"], "dev-multi")
        b.ok("responsable", t, "")
        self.assertEqual(b.tache(t)["owner"], "dev-multi")


# Mutant → (témoin qui le tue, ancres). Chaque ancre est unique dans son fichier (asserté).
MUTANTS: dict[str, tuple[str, dict[str, list[tuple[str, str]]]]] = {
    "R2b branche --json nue sans args.responsable": ("r_2b", {"tasks.py": [(
        "and args.depends_on is None and args.responsable is None:", "and args.depends_on is None:")]}),
    "R2c un refus retiré (--session)": ("r_2c", {"tasks.py": [(
        '            ("--session", args.session),\n            ("--epic", args.epic is not None),\n',
        '            ("--epic", args.epic is not None),\n')]}),
    "R3 responsable dans FIELDS": ("r_3", {"tasks.py": [
        ('\nFIELDS = ("id", "state", "task", "owner", "stage", "updated")',
         '\nFIELDS = ("id", "state", "task", "owner", "stage", "updated", "responsable")'),
        ('"updated": 10}  # id', '"updated": 10, "responsable": 12}  # id')]}),
    "R4 contrôle retiré": ("r_4", {"tasks_stockage.py": [(
        'for champ in ("chantier", "responsable"):', 'for champ in ("chantier",):')]}),
}


class TestResponsable(Temoins, unittest.TestCase):
    def test_copie_resout_moteur_aux_deux_emplacements(self) -> None:
        dest = copie(self, {})
        attendu = vendor_paths.exiger(ROOT, "agentic_v3").resolve()
        self.assertEqual(vendor_paths.exiger(dest.parents[1], "agentic_v3").resolve(), attendu)

    def test_r1_new_verbe_retrait(self) -> None:
        self.r_1(BIN)

    def test_r2_filtre_et_combinaisons(self) -> None:
        self.r_2(BIN)

    def test_r2b_json_seules_correspondances(self) -> None:
        self.r_2b(BIN)

    def test_r2c_refus_nommes(self) -> None:
        self.r_2c(BIN)

    def test_r3_vue_inchangee(self) -> None:
        self.r_3(BIN)

    def test_r4_forme_refusee(self) -> None:
        self.r_4(BIN)

    def test_r5_owner_intouche(self) -> None:
        self.r_5(BIN)

    def test_mutants_rougissent(self) -> None:
        for nom, (temoin, mutations) in MUTANTS.items():
            with self.subTest(mutant=nom):
                dest = copie(self, mutations)
                with self.assertRaises(AssertionError, msg=f"mutant {nom} : {temoin} reste vert"):
                    getattr(self, temoin)(dest)


if __name__ == "__main__":
    unittest.main()
