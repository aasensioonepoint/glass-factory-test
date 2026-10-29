"""LA VOIE DIRECTE — la liste de garde C2 (`tasks_direct.py`, T-00001178).

ZÉRO APPEL LLM. Même harnais que `test_direct_mode.py` (chargé par chemin, ses
outils `copie`, `charger`, `Banc`) : chaque témoin `w_*` reçoit le dossier `bin`
à éprouver, le vrai ou une copie mutée ; chaque mutant de `MUTANTS` ne rejoue
que le témoin qui le tue.

W5 la CLI refuse un chemin de garde, un répertoire, un glob, le motif `garde`.
W19 la liste FERMÉE, classe par classe, et ses contre-témoins d'ancre — le
store du board compris (F7 du binôme de clôture).
W_IAC (T-01M52X1W3WPKCWX1DC36NMKJB6, lot F2) la classe G7 : la voie directe est
refusée en C2 à un write-set qui porte de l'IaC du projet (`main.tf`, `prod.tfvars`,
`.agents/deploy/targets.json`…) ; un mutant par motif, et par ancre contre-témoignée.
W27 COMPLÉTUDE DÉRIVÉE : chaque chemin que CITENT les configs de hooks des hôtes
(D1) et les lignes non commentées de la porte et de la CI (D2) est un chemin de
garde. Limite DITE : UN niveau — ce que la config CITE, jamais ce que le script
appelle ni ce qu'il charge ; ce qui n'est ni câblé ni lancé par la porte
(armement, canal des graines, portes in-process, juges) est de JUGEMENT, jamais
dérivé. Classe qui SE TAIT chez l'adoptant (`skipTest` sans `.agents/IS_THE_KIT`) :
elle lit des surfaces du kit. Un skip n'est pas un vert qui prouve.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

_PARTAGE = "test_direct_mode_partage_garde"
_spec = importlib.util.spec_from_file_location(_PARTAGE, Path(__file__).with_name("test_direct_mode.py"))
_banc = importlib.util.module_from_spec(_spec)
sys.modules[_PARTAGE] = _banc
_spec.loader.exec_module(_banc)
copie, charger, Banc, BIN = _banc.copie, _banc.charger, _banc.Banc, _banc.BIN

ROOT = Path(__file__).resolve().parents[2]

REFUSES = (
    ".agents/bin/tasks.py", ".agents/bin/tasks_verbes.py", ".agents/bin/tasks_direct.py",
    ".agents/bin/specs.py", "core-scripts/verify.sh", "core-scripts/run-bash-tests.sh",
    "core-scripts/check-ci-parity.sh", ".github/workflows/ci.yml", ".agents/evals/test_direct_mode.py",
    "pytest.ini", "Pytest.INI", "conftest.py", "src/cadre/data/gabarits/pytest.ini.tmpl",
    ".template-exclude", ".agents/bin/sync_template.py", ".claude/agents/security-code-review.md",
    ".codex/agents/security-code-review.toml", ".github/agents/critic-fable.agent.md",
    ".kimi-code/agents/plan-critic.md", ".gemini/agents/orchestrator.md", ".agents/pyrun.sh",
    ".agents/bin/post-task-done-index.sh", "agentic_v3/reconciliation/board_bridge.py",
    ".agents/vendor/agentic_v3/reconciliation/board_bridge.py",
    # rév. 5 du plan : R5-3 (night_approve) et R5-6 (`gate`, et deux bancs par nom).
    ".agents/bin/night_approve.py", ".agents/evals/test_adopting_gate_seed.py",
    ".agents/evals/test_seed_protection.py", ".agents/evals/test_gates_chain_contract.py",
    ".agents/bin/tasks.test.sh",
    # binôme de clôture, F7 : le STORE du board.
    ".agents/state/board/TASKS.json",
    # G5 (T-01M5C1NXE5JWY6A0C2XWEGDPCC) : sources `agents/` et roster JSON des juges, le
    # générateur des défs d'hôte et ses deux bancs.
    "agents/plan-critic.md", "src/cadre/data/roster/plan-critic.json", "src/cadre/renderers/source.py",
    ".agents/bin/render_hosts.py", ".agents/bin/test_render_hosts.py", ".agents/evals/test_cadre_renderers.py",
    # Les mêmes au lieu neuf du paquet (`.agents/vendor/cadre`, T-01M5BXTRP8) : le seul vivant dans le kit.
    ".agents/vendor/cadre/data/roster/plan-critic.json", ".agents/vendor/cadre/renderers/source.py",
    # T-01M5CN9FM2MPY8Z00AS7FTXXWH : le registre d'exceptions du scanner Unicode, pilote seul ;
    # couvert par le préfixe G2 `.agents/security/` — une entrée à son nom serait redondante,
    # et aucun mutant ne la rougirait. Premier témoin de ce préfixe (mutant ci-dessous).
    ".agents/security/unicode-allowlist.json", ".agents/evals/test_unicode_allowlist_protection.py",
)
#: Contre-témoins ADMIS — dont ceux des ANCRES : `^` (`vendor/…`, `x/…`) et `$`
#: (`.orig`, `.bak`) ; `checks.manifest.json` est hors liste (BORNE dite).
ADMIS = (
    ".agents/bin/taskslist.py", "docs/run-x.sh", ".agents/bin/test_tasks.py",
    "vendor/.agents/bin/tasks.py", "x/core-scripts/run-y.sh", "x/.claude/agents/security-sca.md",
    ".agents/bin/tasks_x.py.orig", "core-scripts/run-x.sh.bak", ".claude/agents/dev-mono.md",
    "checks.manifest.json",
    # G5 sources et roster (T-01M5C1NXE5JWY6A0C2XWEGDPCC) : une déf hors juges, et les
    # contre-témoins des ancres `^` (`x/…`) et `$` (`.orig`) de leurs deux motifs.
    "agents/dev-mono.md", "x/agents/planner.md", "agents/plan-critic.md.orig",
    "src/cadre/data/roster/dev-mono.json", "x/src/cadre/data/roster/planner.json",
    "src/cadre/data/roster/planner.json.orig",
    ".agents/vendor/cadre/data/roster/dev-mono.json", "x/.agents/vendor/cadre/data/roster/planner.json",
    ".agents/vendor/cadre/data/roster/planner.json.orig",
)
ANCRE_DEBUT = {"vendor/.agents/bin/tasks.py", "x/core-scripts/run-y.sh", "x/.claude/agents/security-sca.md"}
ANCRE_FIN = {".agents/bin/tasks_x.py.orig", "core-scripts/run-x.sh.bak"}
#: G7 (T-01M52X1W3WPKCWX1DC36NMKJB6, lot F2) : l'IaC du PROJET. Chaque motif a au moins
#: un chemin qu'AUCUN autre ne couvre, pour que le retrait d'un seul motif rougisse ;
#: casse repliée comprise (`Infra/Main.TF`). Contre-témoins : l'ancre `$` (`.bak`,
#: `.orig`), l'ancre `^` du registre des cibles (`vendor/…`), et le mot « terraform »
#: dans un nom, qui n'est pas de l'IaC.
IAC_REFUSES = (
    "main.tf", "infra/envs/prod/main.tf", "Infra/Main.TF", "infra/main.tf.json", "prod.tfvars",
    "infra/envs/prod.tfvars.json", ".agents/deploy/targets.json",
)
IAC_ADMIS = (
    "main.tf.bak", "prod.tfvars.orig", "vendor/.agents/deploy/targets.json", ".agents/deploy/targets.json.orig",
    "docs/terraform.md",
)
#: Les write-sets que la CLI `direct` doit refuser en C2 (critère C6.1 / C8.7).
IAC_WRITESETS = (["main.tf"], ["prod.tfvars"], [".agents/deploy/targets.json"], ["docs/a.md", "infra/main.tf"])
PLANCHER_DERIVE = 30
_JETON = re.compile(r"[A-Za-z0-9_./-]+")


def issues(bin_: Path, chemins) -> dict[str, bool]:
    module = charger(bin_)
    return {c: module.est_chemin_de_garde(c) for c in chemins}


def _chaines(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _chaines(v)
    elif isinstance(x, list):
        for v in x:
            yield from _chaines(v)


def chemins_cites(texte: str, suivis: set[str]) -> set[str]:
    """Les chemins SUIVIS que `texte` cite : le plus long suffixe d'un jeton, après
    une `/`, qui est un fichier suivi (`$ROOT/x`, `"$CLAUDE_PROJECT_DIR"/x`, `./x`)."""
    vus: set[str] = set()
    for jeton in _JETON.findall(texte):
        for c in [jeton] + [jeton[i + 1:] for i, ch in enumerate(jeton) if ch == "/"]:
            while c.startswith("./"):
                c = c[2:]
            if "/" in c and c in suivis:
                vus.add(c)
                break
    return vus


class TemoinsGarde:
    def w_vendor_board(self, bin_: Path) -> None:
        chemin = ".agents/vendor/agentic_v3/reconciliation/board_bridge.py"
        self.assertIn(chemin, REFUSES, "le recensement de garde omet le pont V3 vendor")
        b = Banc(self, bin_)
        tid = b.nouvelle("neutre", [chemin])
        refus = b.t("direct", tid)
        self.assertNotEqual(refus.returncode, 0, "voie directe admise sur le pont V3 vendor")
        self.assertIn(f"C2 {chemin} est un chemin de garde", refus.stderr)
        self.assertTrue(issues(bin_, [chemin])[chemin], "le pont V3 vendor échappe à C2")

    def w_05(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        for chemins, classe in (([".claude/hooks/x.sh"], "C2"), ([".agents/bin/foo_guard.py"], "C2"),
                                (["src/"], "C1"), (["src/*.py"], "C1")):
            tid = b.nouvelle("neutre", chemins)
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"admis : {chemins}")
            self.assertIn(classe, r.stderr)
        tid = b.nouvelle("neutre", ["docs/a.md"], motif="garde")
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "motif garde admis")
        self.assertIn("C2", r.stderr)
        # SANS BARRE FINALE, un répertoire reste un répertoire (ajout du dev, coût
        # mesuré 0 au board) : `docs` EXISTE dans le dépôt jetable → C1 ; `.codex`
        # n'y existe pas mais est l'ANCÊTRE de `.codex/hooks/` → C2, textuel.
        (b.d / "docs").mkdir(exist_ok=True)
        for chemin, attendu in (("docs", "répertoire existant"), (".codex", "ancêtre de .codex/hooks/")):
            tid = b.nouvelle("neutre", [chemin])
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"admis : {chemin}")
            self.assertIn(attendu, r.stderr)

    def w_19(self, bin_: Path) -> None:
        vu = issues(bin_, REFUSES + ADMIS)
        self.assertEqual(sorted(c for c in REFUSES if not vu[c]), [], "chemins de garde ADMIS")
        self.assertEqual(sorted(c for c in ADMIS if vu[c]), [], "contre-témoins REFUSÉS")

    def w_iac(self, bin_: Path) -> None:
        """G7 : la voie directe est REFUSÉE à tout write-set qui porte de l'IaC du projet."""
        vu = issues(bin_, IAC_REFUSES + IAC_ADMIS)
        self.assertEqual(sorted(c for c in IAC_REFUSES if not vu[c]), [], "IaC du projet ADMISE en voie directe")
        self.assertEqual(sorted(c for c in IAC_ADMIS if vu[c]), [], "contre-témoins IaC REFUSÉS")
        b = Banc(self, bin_)
        for chemins in IAC_WRITESETS:
            tid = b.nouvelle("neutre", chemins)
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"voie directe admise : {chemins}")
            self.assertIn(f"C2 {chemins[-1]} est un chemin de garde", r.stderr)
            self.assertNotIn("C2 docs/a.md", r.stderr)

    def w_27(self, bin_: Path) -> None:
        suivis = set(subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True,
                                    text=True, check=True, timeout=60).stdout.split("\0"))
        d1: set[str] = set()
        for rel, cle in ((".claude/settings.json", "hooks"), (".codex/hooks.json", None),
                         (".agents/hooks.json", None), (".kimi-code/hooks.json", None)):
            charge = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            for s in _chaines(charge.get(cle, {}) if cle else charge):
                d1 |= chemins_cites(s, suivis)
        for p in sorted((ROOT / ".github" / "hooks").glob("*.json")):
            for s in _chaines(json.loads(p.read_text(encoding="utf-8"))):
                d1 |= chemins_cites(s, suivis)
        d2: set[str] = set()
        for p in [ROOT / "core-scripts" / "verify.sh", *sorted((ROOT / ".github" / "workflows").glob("*.yml"))]:
            for ligne in p.read_text(encoding="utf-8").splitlines():
                if not ligne.lstrip().startswith("#"):
                    d2 |= chemins_cites(ligne, suivis)
        derives = d1 | d2
        print(f"\nW27 : D1 {len(d1)} chemins câblés, D2 {len(d2)} chemins de la porte, union {len(derives)}")
        self.assertGreaterEqual(len(derives), PLANCHER_DERIVE, "dérivation vide : le témoin ne mesure rien")
        vu = issues(bin_, sorted(derives))
        self.assertEqual(sorted(c for c, garde in vu.items() if not garde), [], "câblés hors liste de garde")


_LISTE = "tasks_direct.py"
_REV3_CHEMINS = ('(".claude/hooks/", ".codex/hooks/", ".gemini/hooks/", ".github/hooks/", ".githooks/", '
                 '".agents/state/gates/", ".agents/adopter-seed/", ".agents/security/", ".github/workflows/", '
                 '".claude/settings.json", ".codex/hooks.json", ".agents/hooks.json", ".kimi-code/hooks.json", '
                 '"core-scripts/verify.sh", ".agents/bin/specs.py", ".agents/bin/plan_cible.py", '
                 '".agents/bin/plan_depends.py", ".agents/bin/plan_trace.py", '
                 '".agents/evals/python_file_length_cliquet.json", ".agents/evals/test_python_file_length.py")')
_REV3_MOTIFS = ('(r"^\\.agents/bin/tasks(_[a-z0-9_]+)?\\.py$", r"^core-scripts/run-[^/]+\\.sh$", '
                'r"^\\.agents/evals/test_direct_mode[a-z0-9_]*\\.py$")')
_LIGNES_MOTIFS = (
    '    r"^core-scripts/(run|check)-[^/]+\\.sh$",\n',
    '    r"^\\.agents/bin/tasks(_[a-z0-9_]+)?\\.py$",\n',
    '    r"^\\.(claude|gemini|kimi-code|codex|github)/agents/(orchestrator|planner|plan-critic|critic-|exec-critic|'
    'design-review|security-|sca-)[^/]*\\.(md|toml)$",\n',
    '    r"^\\.agents/evals/test_direct_mode[a-z0-9_]*\\.py$",\n',
)
_REV3 = [("CHEMINS_GARDE = (\n", f"CHEMINS_GARDE = {_REV3_CHEMINS} or (\n"),
         ("MOTIFS_GARDE = (\n", f"MOTIFS_GARDE = {_REV3_MOTIFS} or (\n"),
         ('NOMS_GARDE = ("guard", "garde", "gate")', 'NOMS_GARDE = ("guard", "garde")')]
#: Les quatre motifs G7, ligne exacte de `tasks_direct.py` (ancres des mutants `w_iac`).
_LIGNES_IAC = (
    '    r"\\.tf$",\n',
    '    r"\\.tf\\.json$",\n',
    '    r"\\.tfvars(\\.json)?$",\n',
    '    r"^\\.agents/deploy/targets\\.json$",\n',
)
SANS_DEBUT = [(ligne, ligne.replace('r"^', 'r"', 1)) for ligne in _LIGNES_MOTIFS]
SANS_FIN = [(ligne, ligne.replace('$",\n', '",\n')) for ligne in _LIGNES_MOTIFS]
#: G5, sources `agents/` puis roster JSON des juges (T-01M5C1NXE5JWY6A0C2XWEGDPCC) : ligne
#: exacte de `tasks_direct.py`, HORS de `_LIGNES_MOTIFS` (copie figée) et donc de
#: `SANS_DEBUT`/`SANS_FIN` ; leurs mutants d'ancre sont les leurs, ci-dessous.
_JUGES = "(orchestrator|planner|plan-critic|critic-|exec-critic|design-review|security-|sca-)"
_LIGNES_SOURCES = (
    f'    r"^agents/{_JUGES}[^/]*\\.md$",\n',
    f'    r"^src/cadre/data/roster/{_JUGES}[^/]*\\.json$",\n',
    f'    r"^\\.agents/vendor/cadre/data/roster/{_JUGES}[^/]*\\.json$",\n',
)


def _sans(entree: str) -> list[tuple[str, str]]:
    return [(f'    "{entree}",\n', "")]


MUTANTS = {
    "sans pont V3 vendor": ({_LISTE: [('    ".agents/vendor/agentic_v3/reconciliation/board_bridge.py",\n', "")]},
                             "w_vendor_board"),
    "CHEMINS_GARDE = ()": ({_LISTE: [("CHEMINS_GARDE = (\n", "CHEMINS_GARDE = () and (\n")]}, "w_05"),
    "sans test de nom": ({_LISTE: [("    for mot in NOMS_GARDE:\n", "    for mot in ():\n")]}, "w_05"),
    "sans test de répertoire existant": ({_LISTE: [("        elif (racine / brut).is_dir():\n",
                                                    "        elif False:\n")]}, "w_05"),
    "sans test d'ancêtre": ({_LISTE: [("        if e.startswith(canon + \"/\"):\n", "        if False:\n")]}, "w_05"),
    "liste de la rév. 3 (W19)": ({_LISTE: _REV3}, "w_19"),
    "sans pytest.ini": ({_LISTE: _sans("pytest.ini")}, "w_19"),
    "sans conftest.py": ({_LISTE: _sans("conftest.py")}, "w_19"),
    "sans .template-exclude": ({_LISTE: _sans(".template-exclude")}, "w_19"),
    "sans le motif des juges": ({_LISTE: [(_LIGNES_MOTIFS[2], "")]}, "w_19"),
    "MOTIFS_GARDE = ()": ({_LISTE: [("MOTIFS_GARDE = (\n", "MOTIFS_GARDE = () and (\n")]}, "w_19"),
    "motif sans ancre de debut (^)": ({_LISTE: SANS_DEBUT}, "w_19"),
    "motif sans ancre de fin ($)": ({_LISTE: SANS_FIN}, "w_19"),
    "sans night_approve.py (R5-3)": ({_LISTE: _sans(".agents/bin/night_approve.py")}, "w_19"),
    "sans gate (R5-6)": ({_LISTE: [('NOMS_GARDE = ("guard", "garde", "gate")', 'NOMS_GARDE = ("guard", "garde")')]},
                         "w_19"),
    "sans test_seed_protection.py (R5-6)": ({_LISTE: _sans(".agents/evals/test_seed_protection.py")}, "w_19"),
    "sans tasks.test.sh (R5-6)": ({_LISTE: _sans(".agents/bin/tasks.test.sh")}, "w_19"),
    "sans .agents/state/board/ (F7)": ({_LISTE: _sans(".agents/state/board/")}, "w_19"),
    "sans .agents/security/ (registre unicode)": ({_LISTE: _sans(".agents/security/")}, "w_19"),
    "sans test_unicode_allowlist_protection.py": (
        {_LISTE: _sans(".agents/evals/test_unicode_allowlist_protection.py")}, "w_19"),
    # G7 (T-01M52X1W3WPKCWX1DC36NMKJB6, lot F2) : chaque motif IaC, et les deux ancres
    # qui ont un contre-témoin.
    "sans le motif .tf (G7)": ({_LISTE: [(_LIGNES_IAC[0], "")]}, "w_iac"),
    "sans le motif .tf.json (G7)": ({_LISTE: [(_LIGNES_IAC[1], "")]}, "w_iac"),
    "sans le motif .tfvars (G7)": ({_LISTE: [(_LIGNES_IAC[2], "")]}, "w_iac"),
    "sans le motif targets.json (G7)": ({_LISTE: [(_LIGNES_IAC[3], "")]}, "w_iac"),
    "motif .tf sans ancre de fin (G7)": ({_LISTE: [(_LIGNES_IAC[0], _LIGNES_IAC[0].replace('$",\n', '",\n'))]},
                                         "w_iac"),
    "motif targets.json sans ancre de debut (G7)": (
        {_LISTE: [(_LIGNES_IAC[3], _LIGNES_IAC[3].replace('r"^', 'r"', 1))]}, "w_iac"),
    # G5 (T-01M5C1NXE5JWY6A0C2XWEGDPCC) : le générateur, ses deux bancs, et les motifs des
    # sources `agents/` et du roster JSON des juges, ancres comprises.
    "sans src/cadre/renderers/ (G5)": ({_LISTE: _sans("src/cadre/renderers/")}, "w_19"),
    "sans render_hosts.py (G5)": ({_LISTE: _sans(".agents/bin/render_hosts.py")}, "w_19"),
    "sans test_render_hosts.py (G5)": ({_LISTE: _sans(".agents/bin/test_render_hosts.py")}, "w_19"),
    "sans test_cadre_renderers.py (G5)": ({_LISTE: _sans(".agents/evals/test_cadre_renderers.py")}, "w_19"),
    "sans le motif des sources agents (G5)": ({_LISTE: [(_LIGNES_SOURCES[0], "")]}, "w_19"),
    "motif des sources sans ancre de debut (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[0], _LIGNES_SOURCES[0].replace('r"^', 'r"', 1))]}, "w_19"),
    "motif des sources sans ancre de fin (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[0], _LIGNES_SOURCES[0].replace('$",\n', '",\n'))]}, "w_19"),
    "sans le motif du roster des juges (G5)": ({_LISTE: [(_LIGNES_SOURCES[1], "")]}, "w_19"),
    "motif du roster sans ancre de debut (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[1], _LIGNES_SOURCES[1].replace('r"^', 'r"', 1))]}, "w_19"),
    "motif du roster sans ancre de fin (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[1], _LIGNES_SOURCES[1].replace('$",\n', '",\n'))]}, "w_19"),
    "sans .agents/vendor/cadre/renderers/ (G5)": ({_LISTE: _sans(".agents/vendor/cadre/renderers/")}, "w_19"),
    "sans le motif du roster vendor (G5)": ({_LISTE: [(_LIGNES_SOURCES[2], "")]}, "w_19"),
    "motif du roster vendor sans ancre de debut (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[2], _LIGNES_SOURCES[2].replace('r"^', 'r"', 1))]}, "w_19"),
    "motif du roster vendor sans ancre de fin (G5)": (
        {_LISTE: [(_LIGNES_SOURCES[2], _LIGNES_SOURCES[2].replace('$",\n', '",\n'))]}, "w_19"),
    "liste de la rév. 3 (W27)": ({_LISTE: _REV3}, "w_27"),
    "sans .agents/pyrun.sh": ({_LISTE: _sans(".agents/pyrun.sh")}, "w_27"),
}


class _KitSeul:
    def setUp(self):
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("hors du kit : W27 lit les configs de hooks et la porte du kit")


class DirectGardeTests(TemoinsGarde, unittest.TestCase):
    def test_vendor_board_protege(self):
        self.w_vendor_board(BIN)

    def test_w05(self):
        self.w_05(BIN)

    def test_w19(self):
        self.w_19(BIN)

    def test_wiac(self):
        self.w_iac(BIN)


class DirectGardeDeriveeTests(_KitSeul, TemoinsGarde, unittest.TestCase):
    def test_w27(self):
        self.w_27(BIN)

    def test_mutant_liste_de_la_rev_3(self):
        with self.assertRaises(AssertionError):
            self.w_27(copie(self, BIN, MUTANTS["liste de la rév. 3 (W27)"][0]))

    def test_mutant_sans_pyrun_sh(self):
        with self.assertRaises(AssertionError):
            self.w_27(copie(self, BIN, MUTANTS["sans .agents/pyrun.sh"][0]))


class DirectGardeMutantsTests(TemoinsGarde, unittest.TestCase):
    """Les mutants de W5 et W19 ; ceux de W27 vivent dans la classe qui se tait."""

    def tuer(self, nom: str) -> None:
        mutations, temoin = MUTANTS[nom]
        # La copie est montée HORS de `assertRaises` : `copie` signale une ancre absente par une
        # AssertionError, qui comptait sinon comme un mutant tué (T-01M5C1NXE5JWY6A0C2XWEGDPCC).
        variante = copie(self, BIN, mutations)
        with self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
            getattr(self, temoin)(variante)

    def test_une_ancre_absente_n_est_jamais_un_mutant_tue(self):
        fantome = {"ancre absente": ({_LISTE: [("    \"pas/une/ligne/de/la/liste\",\n", "")]}, "w_19")}
        with mock.patch.dict(MUTANTS, fantome):
            with self.assertRaises(AssertionError) as refus:
                self.tuer("ancre absente")
        self.assertIn("ancre ambiguë ou absente", str(refus.exception))

    def test_la_variante_non_mutee_est_verte(self):
        variante = copie(self, BIN, {})
        self.w_05(variante)
        self.w_19(variante)
        self.w_iac(variante)

    def test_les_ancres_ne_rougissent_que_sur_leurs_contre_temoins(self):
        """MESURE de la rév. 4, rejouée : chaque mutant d'ancre ne bascule QUE ses
        contre-témoins — sinon il serait tué par un autre chemin, et le témoin de
        l'ancre ne prouverait rien."""
        reel = issues(BIN, REFUSES + ADMIS)
        for paires, attendus in ((SANS_DEBUT, ANCRE_DEBUT), (SANS_FIN, ANCRE_FIN)):
            mute = issues(copie(self, BIN, {_LISTE: paires}), REFUSES + ADMIS)
            self.assertEqual({c for c in reel if reel[c] != mute[c]}, attendus)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n, (_m, t) in MUTANTS.items() if t != "w_27"}
# Deux mutants au MÊME nom de test : le second écraserait le premier en silence.
assert len(_GENERES) == sum(1 for _m, t in MUTANTS.values() if t != "w_27"), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(DirectGardeMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


if __name__ == "__main__":
    unittest.main()
