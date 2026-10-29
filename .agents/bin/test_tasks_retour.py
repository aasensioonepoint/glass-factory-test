"""LE CONTRÔLE DE RETOUR — comportement (`tasks.py retour`, `tasks_retour.py`).

T-00001184, décisions S-00004114 et S-00004135, réserves C1-C4 de S-00004162.
ZÉRO APPEL LLM.

Chaque témoin `r_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`
(`RetourTests`), ou une COPIE JETABLE dont un fragment littéral, présent UNE fois
(asserté), est remplacé — forme `MUTANTS` de `test_direct_mode.py`. Chaque mutant
ne rejoue QUE le témoin qui le tue et doit le faire échouer par une ASSERTION :
un mutant qui fait PLANTER le témoin est un défaut du banc, jamais un mutant tué
(les aides du banc lèvent donc `RuntimeError`, jamais `AssertionError`).

UN dépôt git jetable PAR CLASSE (`setUpClass`), RÉUTILISÉ : `Depot.remise` le
ramène à sa base entre deux témoins (worktrees retirés, branches supprimées sauf
`main`, `reset --hard`, `clean`, SPECS retiré). Le board vit sous `.agents/`,
exclu par `info/exclude`. CLI en sous-processus ; `TMPDIR` hérité ;
`CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR`, `HOME` et `XDG_CONFIG_HOME` jetables sous
le dossier de la classe — le verbe retire `GIT_CONFIG_GLOBAL`, donc seul un `HOME`
jetable garde la config git de l'utilisateur hors du banc ; `GIT_CONFIG_NOSYSTEM=1` ;
toute variable `GIT_*` héritée et `CLAUDE_PROJECT_DIR` retirées.

ROUGE SUR LA BASE : `RETOUR_BANC_BIN=<dossier bin>` fait jouer `RetourTests` sur
ce dossier (par exemple le `.agents/bin` de la base, extrait par `git archive`) :
chaque témoin y échoue, le verbe y est absent.

Témoins : R1 nominal ; R2 histoire latérale ; R2b base non ancêtre de HEAD ; R3
branche = base ; R3b commit puis revert ; R4 hors write-set, et parité du prédicat
avec `kickoff_guard.writeset_covers` ; R4b renommage depuis l'extérieur ; R5 HEAD
a touché le diff, et relevé après fusion ; R6 worktree sale, worktree prunable ;
R6b index et diff modifiés au principal ; R7 doublon vierge, doublon porteur ; R8
branche courante ; R9 grappe, et tâche sans write-set ; R10 environnement piégé ;
R11 `--dry-run` ; R12 trois fautes à la fois ; R13 refus inscrit puis ok ; R14 hors
git ; R15 borne SPECS ; R16 l'appel de `promptFusion` (lanceur voyageur) ; R17 délai
`RETOUR_DELAI_S` ; R18 id inconnu et tâche close ; R19 `--vers` : un lot coupé sur la
livraison après la fusion du premier, relevé ok sous `--vers` (pointe de L pour (a)/(e), HEAD
exclu de (h)), refusé (a) sans, clés `CLES | {"vers"}` ; R20 (v) : tâche non déclarée,
livraison absente, branche relevée = livraison ; RA aide en ASCII pur. R1 et RA
nomment (a)-(i) : le contrôle (i) du binôme c4f3 bis a sa ligne à la sortie et
dans l'aide (ses comportements sont éprouvés par D22 de test_retour_done_guard.py).

BORNE : ce banc éprouve le CODE et UNE surface de prose (R16). Ça empêche
d'OUBLIER, pas de TRICHER.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
BIN_TEMOINS = Path(os.environ["RETOUR_BANC_BIN"]).resolve() if os.environ.get("RETOUR_BANC_BIN") else BIN
#: Le résolveur du paquet `cadre`, chargé PAR CHEMIN (patron v3prep, S-01M5BXT85VP4JBBMXVXR9STP5F) : il
#: rend `.agents/vendor/cadre` ou l'ancien `src/cadre`, jamais un `sys.path` qui viserait `src`.
_SPEC_VENDOR = importlib.util.spec_from_file_location("_tasks_retour_vendor_paths", BIN / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = VENDOR
_SPEC_VENDOR.loader.exec_module(VENDOR)

#: Les fichiers copiés pour une variante : la façade, ses parties et les frères qu'elles chargent.
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "specs.py",
          "kickoff_guard.py", "events.py")
#: Le CONTRAT FIGÉ du relevé, clé pour clé : EXACT sans `--vers` (R1) ; sous `--vers`, une clé de
#: plus et une seule, `vers` (T-01M4WTYSCEYHC6KZF2DC1PXBRN, R19).
CLES = {"verdict", "base", "tip", "branche", "taches", "fichiers", "causes", "notes", "specs_borne", "le"}
CLES_VERS = CLES | {"vers"}
REMEDE_REBASE = "rebase de la branche sur HEAD puis rejouer avec --base <nouvelle HEAD>"
GRAINE = {"README.md": "graine\n", "src/a.py": "a = 1\n", "src/ab.py": "ab = 1\n", "src/a/b.py": "b = 1\n",
          "docs/x.md": "x\n", "hors/z.py": "z = 1\n"}
#: (entrée, chemin, couvert ?) — la frontière de segment, la casse, les entrées inadmissibles.
PARITE = [("src/a", "src/ab.py", False), ("src/a/", "src/a/b.py", True), ("src/a", "src/a/b.py", True),
          ("src/a.py", "src/a.py", True), ("SRC/A.py", "src/a.py", True), ("src/a/b.py", "src/a", False),
          ("src", "srcx/a.py", False), ("docs", "docs/x/y.md", True), ("src/a.py", "src/a.pyc", False),
          ("/src", "src/a.py", False), ("src//a", "src/a/b.py", False)]


def poser_generateur(base: Path, source: Path, racine: Path = ROOT) -> Path:
    """`record_id.py` de `source` copié sous `<base>/.agents/bin`, et `ids.py` pris là où le paquet `cadre`
    de `racine` vit (`exiger` : vendor d'abord, puis `src/cadre`), posé là où le `record_id.py` copié le
    cherchera : le kit ne copie pas `vendor_paths.py`, donc son repli `<base>/src/cadre/ledger/ids.py`
    (record_id.py `_dossier_cadre`). Rend le dossier `bin` du kit."""
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "record_id.py", dest / "record_id.py")
    generateur = base / "src" / "cadre" / "ledger"
    generateur.mkdir(parents=True)
    shutil.copy2(VENDOR.exiger(racine, "cadre") / "ledger" / "ids.py", generateur / "ids.py")
    return dest


def copie(case: unittest.TestCase, source: Path, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable de `source` (dossier bin), chaque ancre remplacée UNE fois."""
    base = Path(tempfile.mkdtemp(prefix="retour-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in source.glob(motif):
            shutil.copy2(f, dest / f.name)
    # FRÈRES D'ALLOCATION (plan T-00000726, E13/E25) : cette copie ALLOUE (`new`), elle porte donc
    # `record_id.py` et le générateur `ids.py`, comme tout harnais qui alloue.
    # Copie INCONDITIONNELLE : un frère absent fait échouer le montage, jamais sauter le
    # provisionnement en silence (un glob de COPIES, lui, sauterait sans rien dire).
    poser_generateur(base, source)
    for nom, paires in mutations.items():
        cible = dest / nom
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            case.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente dans {nom} : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
    return dest


def charger(bin_: Path):
    """Le module `tasks` de `bin_`, chargé sous un nom unique (appels en processus)."""
    nom = f"tasks_retour_banc_{abs(hash(str(bin_)))}"
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, bin_ / "tasks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def oracle():
    """`kickoff_guard.writeset_covers` (SYM-00753) du VRAI bin : la parité se juge
    toujours contre l'original, jamais contre la copie mutée."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    import kickoff_guard

    return kickoff_guard.writeset_covers


class Depot:
    """UN dépôt git jetable, sa graine et sa base, et la CLI braquée dessus."""

    def __init__(self) -> None:
        self.d = Path(tempfile.mkdtemp(prefix="retour-")).resolve()
        self.repo, self.wts = self.d / "depot", self.d / "wts"
        for sous in ("depot", "wts", "home", "xdg", "state", "events"):
            (self.d / sous).mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        self.env.update(HOME=str(self.d / "home"), XDG_CONFIG_HOME=str(self.d / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                        CADRE_STATE_DIR=str(self.d / "state"), AGENTS_EVENTS_DIR=str(self.d / "events"),
                        GIT_AUTHOR_NAME="banc", GIT_AUTHOR_EMAIL="banc@exemple.invalid",
                        GIT_COMMITTER_NAME="banc", GIT_COMMITTER_EMAIL="banc@exemple.invalid")
        self.n = 0
        self.g("init", "-q", "-b", "main")
        (self.repo / ".git" / "info" / "exclude").write_text(".agents/\n", encoding="utf-8")
        for chemin, contenu in GRAINE.items():
            self.ecrire(chemin, contenu)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "graine")
        self.graine = self.sha("HEAD")
        self.ecrire("README.md", "base\n")
        self.g("commit", "-q", "-am", "base")
        self.base = self.sha("HEAD")

    def fermer(self) -> None:
        shutil.rmtree(self.d, True)

    def g(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, capture_output=True,
                           text=True, timeout=120, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
        return r.stdout

    def sha(self, rev: str, cwd: Path | None = None) -> str:
        return self.g("rev-parse", "--verify", f"{rev}^{{commit}}", cwd=cwd).strip()

    def ecrire(self, chemin: str, contenu: str, racine: Path | None = None) -> None:
        p = (racine or self.repo) / chemin
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenu, encoding="utf-8")

    def remise(self) -> None:
        """Le dépôt RAMENÉ à sa base : le banc est réutilisé, jamais recréé."""
        self.g("checkout", "-q", "-f", "main")
        self.g("reset", "-q", "--hard", self.base)
        self.g("clean", "-fdq")
        shutil.rmtree(self.wts, True)
        self.wts.mkdir()
        self.g("worktree", "prune")
        autres = [b for b in self.g("for-each-ref", "--format=%(refname:short)", "refs/heads/").split()
                  if b != "main"]
        if autres:
            self.g("branch", "-D", *autres)
        specs = self.repo / ".agents" / "state" / "specs" / "SPECS.json"
        if specs.exists():
            specs.unlink()

    def leurre(self) -> Path:
        """Un AUTRE dépôt, que `GIT_DIR`/`GIT_WORK_TREE` piégés désigneraient."""
        chemin = self.d / "leurre"
        if not (chemin / ".git").is_dir():
            chemin.mkdir(exist_ok=True)
            self.g("init", "-q", "-b", "main", cwd=chemin)
            self.ecrire("leurre.txt", "leurre\n", racine=chemin)
            self.g("add", "-A", cwd=chemin)
            self.g("commit", "-q", "-m", "leurre", cwd=chemin)
        return chemin

    def t(self, bin_: Path, *args: str, env: dict | None = None,
          racine: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(bin_ / "tasks.py"), "--root", str(racine or self.repo), *args],
                              capture_output=True, text=True, env=env or self.env, timeout=300, check=False)

    def ok(self, bin_: Path, *args: str, racine: Path | None = None) -> subprocess.CompletedProcess:
        r = self.t(bin_, *args, racine=racine)
        if r.returncode != 0:
            raise RuntimeError(f"banc : {args} en échec : {r.stdout}{r.stderr}")
        return r

    def nouvelle(self, bin_: Path, chemins: list[str] | None = None, racine: Path | None = None) -> str:
        r = self.ok(bin_, "new", "tâche de banc", racine=racine)
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        if trouve is None:
            raise RuntimeError(f"banc : message de `new` inattendu : {r.stdout}")
        if chemins:
            self.ok(bin_, "writeset", trouve.group(1), *chemins, racine=racine)
        return trouve.group(1)

    def tache(self, bin_: Path, tid: str) -> dict:
        return json.loads(self.ok(bin_, "list", "--task", tid, "--json").stdout)[0]

    def board_sha(self) -> str:
        return hashlib.sha256((self.repo / ".agents" / "state" / "board" / "TASKS.json").read_bytes()).hexdigest()

    def dev(self, branche: str, fichiers: dict[str, str], base: str | None = None, dossier: str | None = None,
            doublon_porteur: bool = False) -> Path:
        """Le geste d'un dev isolé : un worktree `dossier` né sur `base` (branche
        `worktree-<dossier>`), puis `switch -c <branche>` et un commit des `fichiers`.
        `doublon_porteur` : un commit sur le doublon AVANT le `switch -c`, puis
        `reset --keep <base>` — le doublon garde un commit propre."""
        self.n += 1
        dossier = dossier or f"agent-{self.n}"
        wt, depart = self.wts / dossier, base or self.base
        self.g("worktree", "add", "-q", "-b", f"worktree-{dossier}", str(wt), depart)
        if doublon_porteur:
            self.ecrire("propre.txt", "commit du doublon\n", racine=wt)
            self.g("add", "-A", cwd=wt)
            self.g("commit", "-q", "-m", "doublon", cwd=wt)
        self.g("switch", "-q", "-c", branche, cwd=wt)
        if doublon_porteur:
            self.g("reset", "-q", "--keep", depart, cwd=wt)
        for chemin, contenu in fichiers.items():
            self.ecrire(chemin, contenu, racine=wt)
        self.g("add", "-A", cwd=wt)
        self.g("commit", "-q", "-m", f"dev {branche}", cwd=wt)
        return wt

    def retour(self, bin_: Path, *tids: str, branche: str, base: str | None = None, extra: tuple = (),
               env: dict | None = None) -> subprocess.CompletedProcess:
        return self.t(bin_, "retour", *tids, "--base", base or self.base, "--branche", branche, *extra, env=env)


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    depot: Depot

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.depot = Depot()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.depot.fermer()
        super().tearDownClass()

    def rc(self, r: subprocess.CompletedProcess, attendu: int) -> None:
        self.assertEqual(r.returncode, attendu, r.stdout + r.stderr)

    def causes(self, bin_: Path, tid: str) -> list[str]:
        tache = self.depot.tache(bin_, tid)
        self.assertIn("retour", tache, f"aucun relevé sur {tid}")
        return tache["retour"]["causes"]

    def une(self, causes: list[str], debut: str, *contient: str) -> str:
        """LA cause qui ouvre par `debut` et porte chaque `contient` — une et une seule."""
        trouvees = [c for c in causes if c.startswith(debut) and all(x in c for x in contient)]
        self.assertEqual(len(trouvees), 1, f"{debut} {contient} : {causes}")
        return trouvees[0]

    # -- R1 : le nominal, le relevé complet ----------------------------------
    def r_01(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/a.py", "docs/"])
        d.dev("wt/r01", {"src/a.py": "a = 2\n", "docs/neuf.md": "neuf\n"}, dossier="agent-r01")
        r = d.retour(bin_, tid, branche="wt/r01", base=d.base[:10])
        self.rc(r, 0)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "RETOUR: ok")
        for x in "abcdefghi":
            self.assertRegex(r.stdout, rf"(?m)^RETOUR \({x}\) ", f"aucune ligne pour ({x})")
        rel = d.tache(bin_, tid)["retour"]
        self.assertEqual(set(rel), CLES)
        self.assertEqual((rel["verdict"], rel["base"], rel["tip"], rel["branche"], rel["taches"]),
                         ("ok", d.base, d.sha("wt/r01"), "wt/r01", [tid]))
        self.assertEqual(rel["fichiers"], ["docs/neuf.md", "src/a.py"])
        self.assertEqual(rel["causes"], [])
        self.assertEqual(rel["notes"], ["(h) doublon vierge, supprimable : worktree-agent-r01"])
        self.assertEqual(rel["specs_borne"], "S-00000000")
        self.assertRegex(rel["le"], r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

    # -- R2 R2b : (a) la base ------------------------------------------------
    def r_02(self, bin_: Path) -> None:
        """Une branche née sur une histoire LATÉRALE (la forme dce5c8c9) : (a), et
        (c)-(f) « non évalués »."""
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r02", {"src/a.py": "a = latérale\n"}, base=d.graine)
        self.rc(d.retour(bin_, tid, branche="wt/r02"), 1)
        causes = self.causes(bin_, tid)
        self.assertIn(REMEDE_REBASE, self.une(causes, "(a) refus", "pointe"))
        for x in "cdef":
            self.assertIn(f"({x}) non évalué — base fausse", causes)

    def r_02b(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r02b-cote", {"docs/cote.md": "côté\n"})
        cote = d.sha("wt/r02b-cote")
        d.dev("wt/r02b", {"src/a.py": "a = sur le côté\n"}, base=cote)
        self.rc(d.retour(bin_, tid, branche="wt/r02b", base=cote), 1)
        self.assertIn(REMEDE_REBASE, self.une(self.causes(bin_, tid), "(a) refus", "ancêtre de HEAD"))

    # -- R3 R3b : (b) et (d) ------------------------------------------------
    def r_03(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.g("branch", "wt/r03", d.base)
        self.rc(d.retour(bin_, tid, branche="wt/r03"), 1)
        self.une(self.causes(bin_, tid), "(b) refus — aucun commit")

    def r_03b(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        wt = d.dev("wt/r03b", {"src/a.py": "a = 3\n"})
        d.g("revert", "--no-edit", "HEAD", cwd=wt)
        r = d.retour(bin_, tid, branche="wt/r03b")
        self.rc(r, 1)
        self.assertIn("RETOUR (b) ok — 2 commit(s)", r.stdout)
        self.une(self.causes(bin_, tid), "(d) refus — diff vide")

    # -- R4 R4b : (c) le write-set -----------------------------------------
    def r_04(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/a"])
        d.dev("wt/r04", {"src/ab.py": "ab = 2\n", "src/a/b.py": "b = 2\n"})
        self.rc(d.retour(bin_, tid, branche="wt/r04"), 1)
        hors = self.une(self.causes(bin_, tid), "(c) refus", "1 fichier(s) hors du write-set", "src/ab.py")
        self.assertNotIn("src/a/b.py", hors)
        module, couvre = charger(bin_), oracle()
        for entree, chemin, attendu in PARITE:
            self.assertEqual(couvre(entree, chemin), attendu, f"oracle writeset_covers {entree!r} {chemin!r}")
            self.assertEqual(module.retour_couvre(entree, chemin), attendu, f"retour_couvre {entree!r} {chemin!r}")

    def r_04b(self, bin_: Path) -> None:
        """`git mv` d'un fichier HORS write-set VERS le write-set : la source compte."""
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        wt = d.dev("wt/r04b", {"src/neuf.py": "n = 1\n"})
        d.g("mv", "hors/z.py", "src/z.py", cwd=wt)
        d.g("commit", "-q", "-m", "renommage", cwd=wt)
        self.rc(d.retour(bin_, tid, branche="wt/r04b"), 1)
        self.une(self.causes(bin_, tid), "(c) refus", "hors/z.py")
        self.assertEqual(d.tache(bin_, tid)["retour"]["fichiers"], ["hors/z.py", "src/neuf.py", "src/z.py"])

    # -- R5 : (e) HEAD -------------------------------------------------------
    def r_05(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/a.py"])
        d.dev("wt/r05", {"src/a.py": "a = 5\n"})
        d.ecrire("src/a.py", "a = principal\n")
        d.g("commit", "-q", "-am", "principal")
        self.rc(d.retour(bin_, tid, branche="wt/r05"), 1)
        self.assertIn(REMEDE_REBASE, self.une(self.causes(bin_, tid), "(e) refus"))
        # Le relevé pris APRÈS la fusion est refusé : le contrôle précède la fusion.
        d.remise()
        apres = d.nouvelle(bin_, ["src/a.py"])
        d.dev("wt/r05b", {"src/a.py": "a = 6\n"})
        d.g("merge", "--no-ff", "-q", "-m", "fusion", "wt/r05b")
        self.rc(d.retour(bin_, apres, branche="wt/r05b"), 1)
        self.une(self.causes(bin_, apres), "(e) refus", "déjà fusionnée")

    # -- R6 R6b : (f) le worktree, (g) le principal --------------------------
    def r_06(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        wt = d.dev("wt/r06", {"src/a.py": "a = 6\n"})
        d.ecrire("brouillon.txt", "oublié\n", racine=wt)
        self.rc(d.retour(bin_, tid, branche="wt/r06"), 1)
        self.une(self.causes(bin_, tid), "(f) refus", "non propre", "brouillon.txt")
        d.remise()
        elague = d.nouvelle(bin_, ["src/"])
        shutil.rmtree(d.dev("wt/r06p", {"src/a.py": "a = 7\n"}))
        self.rc(d.retour(bin_, elague, branche="wt/r06p"), 1)
        self.une(self.causes(bin_, elague), "(f) refus", "prunable")

    def r_06b(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r06b", {"src/a.py": "a = 8\n"})
        d.ecrire("hors/z.py", "z = indexé\n")
        d.g("add", "hors/z.py")
        self.rc(d.retour(bin_, tid, branche="wt/r06b"), 1)
        self.une(self.causes(bin_, tid), "(g) refus — index du principal non vide", "hors/z.py")
        d.remise()
        modifie = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r06c", {"src/a.py": "a = 9\n"})
        d.ecrire("src/a.py", "a = modifié au principal\n")
        self.rc(d.retour(bin_, modifie, branche="wt/r06c"), 1)
        self.une(self.causes(bin_, modifie), "(g) refus", "modifié(s) au principal", "src/a.py")

    # -- R7 R8 : (h) le doublon, (g) la branche courante ---------------------
    def r_07(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r07", {"src/a.py": "a = 10\n"}, dossier="agent-r07")
        self.rc(d.retour(bin_, tid, branche="wt/r07"), 0)
        self.assertEqual(d.tache(bin_, tid)["retour"]["notes"], ["(h) doublon vierge, supprimable : worktree-agent-r07"])
        d.remise()
        porteur = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r07b", {"src/a.py": "a = 11\n"}, dossier="agent-r07b", doublon_porteur=True)
        self.rc(d.retour(bin_, porteur, branche="wt/r07b"), 1)
        self.une(self.causes(bin_, porteur), "(h) refus", "worktree-agent-r07b", "1 commit(s)")

    def r_08(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.g("switch", "-q", "-c", "wt/r08")
        d.ecrire("src/a.py", "a = 12\n")
        d.g("commit", "-q", "-am", "dev commité sur la branche courante")
        self.rc(d.retour(bin_, tid, branche="wt/r08"), 1)
        self.une(self.causes(bin_, tid), "(g) refus", "COURANTE")

    # -- R9 : la grappe ------------------------------------------------------
    def r_09(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        t1, t2 = d.nouvelle(bin_, ["src/a.py"]), d.nouvelle(bin_, ["docs/"])
        d.dev("wt/r09", {"src/a.py": "a = 13\n", "docs/n.md": "n\n"})
        self.rc(d.retour(bin_, t1, t2, branche="wt/r09"), 0)
        r1, r2 = d.tache(bin_, t1), d.tache(bin_, t2)
        self.assertIn("retour", r2, "relevé absent de la SECONDE tâche de la grappe")
        self.assertEqual(r1["retour"]["taches"], [t1, t2])
        self.assertEqual(r1["retour"], r2["retour"])
        sans = d.nouvelle(bin_)
        self.rc(d.retour(bin_, t1, sans, branche="wt/r09"), 1)
        self.une(self.causes(bin_, sans), f"(c) refus — {sans} sans write-set déclaré")

    # -- R10 R11 : l'environnement, --dry-run --------------------------------
    def r_10(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r10", {"src/a.py": "a = 14\n"})
        leurre = d.leurre()
        piege = dict(d.env, GIT_DIR=str(leurre / ".git"), GIT_WORK_TREE=str(leurre))
        r = d.retour(bin_, tid, branche="wt/r10", env=piege)
        self.rc(r, 0)
        self.assertEqual(d.tache(bin_, tid)["retour"]["tip"], d.sha("wt/r10"))

    def r_11(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r11", {"src/a.py": "a = 15\n"})
        avant = d.board_sha()
        r = d.retour(bin_, tid, branche="wt/r11", extra=("--dry-run",))
        self.rc(r, 0)
        self.assertIn("RETOUR: --dry-run — rien n'est écrit", r.stdout)
        self.assertEqual(d.board_sha(), avant, "--dry-run a écrit le board")
        self.assertNotIn("retour", d.tache(bin_, tid))

    # -- R12 R13 : toutes les causes, le remplacement ------------------------
    def r_12(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        wt = d.dev("wt/r12", {"src/a.py": "a = 16\n", "hors/z.py": "z = 2\n"})
        d.ecrire("brouillon.txt", "x\n", racine=wt)
        d.ecrire("docs/x.md", "indexé\n")
        d.g("add", "docs/x.md")
        self.rc(d.retour(bin_, tid, branche="wt/r12"), 1)
        causes = self.causes(bin_, tid)
        self.assertEqual(sorted({c[1] for c in causes}), ["c", "f", "g"], causes)

    def r_13(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/a.py"])
        d.dev("wt/r13", {"src/a.py": "a = 17\n", "docs/r13.md": "r\n"})
        self.rc(d.retour(bin_, tid, branche="wt/r13"), 1)
        refus = d.tache(bin_, tid)["retour"]
        self.assertEqual(refus["verdict"], "refus")
        self.une(refus["causes"], "(c) refus", "docs/r13.md")
        d.ok(bin_, "writeset", tid, "src/a.py", "docs/r13.md")
        self.rc(d.retour(bin_, tid, branche="wt/r13"), 0)
        ok = d.tache(bin_, tid)["retour"]
        self.assertEqual((ok["verdict"], ok["causes"]), ("ok", []))

    # -- R14 R15 : hors git, la borne SPECS ----------------------------------
    def r_14(self, bin_: Path) -> None:
        d = self.depot
        hors = d.d / "hors-git"
        hors.mkdir(exist_ok=True)
        tid = d.nouvelle(bin_, racine=hors)
        plafond = dict(d.env, GIT_CEILING_DIRECTORIES=str(d.d))
        r = d.t(bin_, "retour", tid, "--base", "0123456789abc", "--branche", "wt/r14", env=plafond, racine=hors)
        self.rc(r, 1)
        self.assertIn("RETOUR (a) non mesuré — git rev-parse en échec (rc 128", r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "RETOUR: refus")

    def r_15(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r15", {"src/a.py": "a = 18\n"})
        specs = d.repo / ".agents" / "state" / "specs"
        specs.mkdir(parents=True, exist_ok=True)
        entrees = [{"id": f"S-{n:08d}", "task": tid, "kind": "note", "title": "t", "text": "", "files": [],
                    "date": "2026-10-05"} for n in (7, 42, 13)]
        (specs / "SPECS.json").write_text(json.dumps({"entries": entrees}), encoding="utf-8")
        self.rc(d.retour(bin_, tid, branche="wt/r15"), 0)
        self.assertEqual(d.tache(bin_, tid)["retour"]["specs_borne"], "S-00000042")
        (specs / "SPECS.json").write_text("{pas du json", encoding="utf-8")
        self.rc(d.retour(bin_, tid, branche="wt/r15"), 0)
        self.assertIsNone(d.tache(bin_, tid)["retour"]["specs_borne"])

    # -- R17 R18 RA : le délai, les erreurs, l'aide ---------------------------
    def r_17(self, bin_: Path) -> None:
        """C4 : un git qui ne rend pas la main dans `RETOUR_DELAI_S` est « non
        mesuré », donc un refus — en processus, délai abaissé, faux git qui dort."""
        if os.name == "nt":
            self.skipTest("faux git en script sh : POSIX seulement")
        d = self.depot
        module = charger(bin_)
        faux = d.d / "faux-git"
        faux.mkdir(exist_ok=True)
        (faux / "git").write_text("#!/bin/sh\nexec sleep 3\n", encoding="utf-8")
        (faux / "git").chmod(0o755)
        chemin = str(faux) + os.pathsep + os.environ.get("PATH", "")
        with mock.patch.object(module, "RETOUR_DELAI_S", 0.3), mock.patch.dict(os.environ, {"PATH": chemin}):
            debut = time.monotonic()
            rel = module.retour_mesurer(str(d.repo), [], d.base, "wt/r17", {"tasks": []})
            ecoule = time.monotonic() - debut
        self.assertEqual(rel["verdict"], "refus")
        self.assertTrue(rel["causes"][0].startswith("(a) non mesuré — git rev-parse : délai de 0.3 s dépassé"),
                        rel["causes"])
        self.assertLess(ecoule, 2.5, "le délai n'a pas coupé l'appel")

    def r_18(self, bin_: Path) -> None:
        d = self.depot
        d.remise()
        tid = d.nouvelle(bin_, ["src/"])
        d.dev("wt/r18", {"src/a.py": "a = 19\n"})
        avant = d.board_sha()
        r = d.retour(bin_, "T-99999999", branche="wt/r18")
        self.rc(r, 2)
        self.assertIn("unknown task id: T-99999999", r.stderr)
        self.assertEqual(d.board_sha(), avant)
        d.ok(bin_, "done", tid, "--raison", "clos par le banc")
        avant = d.board_sha()
        r = d.retour(bin_, tid, branche="wt/r18")
        self.rc(r, 2)
        self.assertIn(f"{tid} est close (done)", r.stderr)
        self.assertEqual(d.board_sha(), avant)

    # -- R19 R20 : `--vers`, la livraison (T-01M4WTYSCEYHC6KZF2DC1PXBRN) ----------------
    def livraison(self, bin_: Path, *tids: str) -> Path:
        """La livraison `integ/l` déclarée sur `tids`, née sur la base, dans SON worktree."""
        d = self.depot
        d.ok(bin_, "livraison", *tids, "--branche", "integ/l")
        wt = d.wts / "integ-l"
        d.g("worktree", "add", "-q", "-b", "integ/l", str(wt), d.base)
        return wt

    def r_19(self, bin_: Path) -> None:
        """Lot 1 relevé `--vers` et fusionné dans L ; HEAD avance sans L ; lot 2 coupé sur L
        par un dev isolé dont le doublon naît sur HEAD : `--vers` → ok (pointe de L pour (a)
        et (e), HEAD exclu de (h) : doublon vierge), clés `CLES | {"vers"}` ; sans `--vers`,
        (a) refuse (la base n'est pas ancêtre de HEAD)."""
        d = self.depot
        d.remise()
        t1, t2 = d.nouvelle(bin_, ["src/a.py"]), d.nouvelle(bin_, ["src/ab.py"])
        wt_l = self.livraison(bin_, t1, t2)
        d.dev("wt/r19a", {"src/a.py": "a = 191\n"}, dossier="agent-r19a")
        self.rc(d.retour(bin_, t1, branche="wt/r19a", extra=("--vers", "integ/l")), 0)
        d.g("merge", "-q", "--no-ff", "-m", "lot 1 dans la livraison", "wt/r19a", cwd=wt_l)
        d.ecrire("hors/z.py", "z = 19\n")
        d.g("commit", "-q", "-am", "HEAD avance sans la livraison")
        pointe_l = d.sha("integ/l")
        wt = d.wts / "agent-r19b"
        d.g("worktree", "add", "-q", "-b", "worktree-agent-r19b", str(wt), d.sha("HEAD"))
        d.g("switch", "-q", "-c", "wt/r19b", pointe_l, cwd=wt)
        d.ecrire("src/ab.py", "ab = 192\n", racine=wt)
        d.g("commit", "-q", "-am", "lot 2", cwd=wt)
        r = d.retour(bin_, t2, branche="wt/r19b", base=pointe_l)
        self.rc(r, 1)
        self.une(self.causes(bin_, t2), "(a) refus", "ancêtre de HEAD")
        self.assertNotIn("vers", d.tache(bin_, t2)["retour"])
        r = d.retour(bin_, t2, branche="wt/r19b", base=pointe_l, extra=("--vers", "refs/heads/integ/l"))
        self.rc(r, 0)
        for ligne in ("RETOUR (v) ok", "RETOUR (h) note — doublon vierge, supprimable : worktree-agent-r19b",
                      "et de la pointe de integ/l", "RETOUR: vers la livraison integ/l"):
            self.assertIn(ligne, r.stdout)
        rel = d.tache(bin_, t2)["retour"]
        self.assertEqual(set(rel), CLES_VERS)
        self.assertEqual((rel["vers"], rel["base"], rel["fichiers"]), ("integ/l", pointe_l, ["src/ab.py"]))

    def r_20(self, bin_: Path) -> None:
        """(v) : une tâche qui ne porte pas la livraison, une livraison absente, la branche
        relevée qui EST la livraison — rc 1, chaque cause nommée."""
        d = self.depot
        d.remise()
        t1, nue = d.nouvelle(bin_, ["src/a.py"]), d.nouvelle(bin_, ["src/ab.py"])
        self.livraison(bin_, t1)
        d.dev("wt/r20", {"src/ab.py": "ab = 20\n"}, dossier="agent-r20")
        self.rc(d.retour(bin_, nue, branche="wt/r20", extra=("--vers", "integ/l")), 1)
        self.une(self.causes(bin_, nue), "(v) refus", f"{nue} ne porte(nt) pas la livraison integ/l")
        self.rc(d.retour(bin_, nue, branche="wt/r20", extra=("--vers", "integ/absente")), 1)
        causes = self.causes(bin_, nue)
        self.une(causes, "(v) refus", "integ/absente n'existe pas")
        self.une(causes, "(a) non évalué", "la pointe de la livraison 'integ/absente' n'est pas résolue")
        d.ok(bin_, "livraison", t1, "--branche", "wt/r20")
        self.rc(d.retour(bin_, t1, branche="wt/r20", extra=("--vers", "wt/r20")), 1)
        self.une(self.causes(bin_, t1), "(v) refus", "la branche relevée EST la livraison")
        self.rc(d.retour(bin_, t1, branche="wt/r20", extra=("--vers", "")), 1)
        self.une(self.causes(bin_, t1), "(v) refus", "--vers vide")

    def r_aide(self, bin_: Path) -> None:
        """C1 : l'aide s'imprime AVANT `force_utf8_stdio` — ASCII pur ; elle nomme
        (a)-(i) et les rc 0/1/2."""
        r = self.depot.t(bin_, "retour", "--help")
        self.rc(r, 0)
        self.assertTrue(r.stdout.isascii(), "aide de `retour` non ASCII")
        aide = " ".join(r.stdout.split())
        for x in "abcdefghi":
            self.assertIn(f"({x})", aide)
        self.assertIn("Exit 0 ok, 1 refused, 2 unknown or closed task", aide)


class RetourTests(Temoins, unittest.TestCase):
    """Chaque témoin sur le VRAI `.agents/bin` (ou `RETOUR_BANC_BIN`)."""


for _nom in sorted(n for n in dir(Temoins) if n.startswith("r_")):
    setattr(RetourTests, "test_" + _nom[2:], (lambda n: lambda self: getattr(self, n)(BIN_TEMOINS))(_nom))


_R = "tasks_retour.py"
MUTANTS = {
    "(a) retiré": ({_R: [('            if not retour_ancetre(racine, m["base"], m["tip"]):\n',
                          "            if False:\n")]}, "r_02"),
    "HEAD non contrôlé": ({_R: [('            if not retour_ancetre(racine, m["base"], m["head"]):\n',
                                 "            if False:\n")]}, "r_02b"),
    "(b) retiré": ({_R: [("    if n_commits == 0:\n", "    if False:\n")]}, "r_03"),
    "(d) retiré": ({_R: [('    if not m["fichiers"]:\n        out.append(("d", "refus"',
                          '    if False:\n        out.append(("d", "refus"')]}, "r_03b"),
    "préfixe de chaîne": ({_R: [("    return len(e) <= len(c) and c[: len(e)] == e\n",
                                 '    return "/".join(c).startswith("/".join(e))\n')]}, "r_04"),
    "sans --no-renames": ({_R: [('"diff", "--no-renames",', '"diff", "-M",')]}, "r_04b"),
    "(e) retiré": ({_R: [("    if touches:\n", "    if False:\n")]}, "r_05"),
    "(f) retiré": ({_R: [("        controles += retour_controle_f(m)\n", "")]}, "r_06"),
    "(g) retiré": ({_R: [("        controles += retour_controle_g(m)\n", "")]}, "r_06b"),
    "doublon ignoré": ({_R: [("            if n_propres > 0:\n", "            if False:\n")]}, "r_07"),
    "branche courante admise": ({_R: [('        if retour_git(racine, "rev-parse", "--symbolic-full-name", '
                                       '"HEAD").strip() == m["ref"]:\n', "        if False:\n")]}, "r_08"),
    "relevé sur la première seule": ({_R: [("        for tid_inscrit in tids:\n",
                                            "        for tid_inscrit in tids[:1]:\n")]}, "r_09"),
    "env non nettoyé": ({_R: [("    env = {k: v for k, v in os.environ.items()\n",
                               "    env = dict(os.environ) or {k: v for k, v in os.environ.items()\n")]}, "r_10"),
    "dry-run écrit": ({_R: [("    if dry_run:\n", "    if False:\n")]}, "r_11"),
    "première cause seule": ({_R: [("if etat in RETOUR_ETATS_REFUS]\n",
                                    "if etat in RETOUR_ETATS_REFUS][:1]\n")]}, "r_12"),
    "erreur git = ok": ({_R: [("    if r.returncode != 0:\n", "    if False:\n")]}, "r_14"),
    "borne absente": ({_R: [("    borne = retour_specs_borne(root)\n", "    borne = None\n")]}, "r_15"),
    "délai infini": ({_R: [("timeout=RETOUR_DELAI_S,", "timeout=None,")]}, "r_17"),
    # (i), binôme c4f3 bis : les boucles (a)-(i) de R1 et RA rougissent si (i) manque.
    "(i) absent de la sortie": ({_R: [(
        '        return [("i", "sans objet", "aucun relevé antérieur sur une tâche estampillée direct")]\n',
        "        return []\n")]}, "r_01"),
    "(i) absent de l'aide": ({"tasks_cli.py": [("(i) on a task stamped ", "on a task stamped "),
                                               ("check (i) not concluded", "check not concluded")]}, "r_aide"),
    # -- `--vers`, étape 7 du plan T-01M4WTYSCEYHC6KZF2DC1PXBRN ------------------------
    "head = HEAD sous vers": ({_R: [('            m["head"] = retour_ref_existe(racine, RETOUR_PREFIXE_REF + m["vers"])\n',
                                     '            m["head"] = m["principal"]\n')]}, "r_19"),
    "(h) sans principal": ({_R: [('m["head"], m["principal"], "--remotes"', 'm["head"], "--remotes"')]}, "r_19"),
    "(v) retiré": ({_R: [('    sans = [find(data, tid)["id"] for tid in tids if',
                          '    sans = [] and [find(data, tid)["id"] for tid in tids if')]}, "r_20"),
}


class RetourMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant de `MUTANTS` rejoue SON témoin et doit le faire échouer."""

    def tuer(self, nom: str) -> None:
        mutations, temoin = MUTANTS[nom]
        variante = copie(self, BIN, mutations)
        with self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
            getattr(self, temoin)(variante)

    def test_la_variante_non_mutee_est_verte(self):
        """NON-VACUITÉ du harnais : une copie SANS mutation passe un témoin de
        chaque famille — un mutant n'est pas tué par la seule copie."""
        variante = copie(self, BIN, {})
        for temoin in ("r_01", "r_07", "r_12", "r_17"):
            getattr(self, temoin)(variante)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n in MUTANTS}
# Deux mutants au MÊME nom de test : le second écraserait le premier en silence.
assert len(_GENERES) == len(MUTANTS), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(RetourMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


class VendorSeulTests(unittest.TestCase):
    """Témoin A (T-01M5BXTPQE3JZV3KZA6WD9P5XC, S-01M5BXT85VP4JBBMXVXR9STP5F) : un kit jetable monté depuis
    une racine où `cadre` ne vit QUE sous `.agents/vendor/cadre` (aucun `src/`) alloue par `mint`, résolu
    par CHEMIN (`python -I` : ni site-packages ni PYTHONPATH, donc jamais un `cadre` installé)."""

    def test_vendor_seul_a(self):
        tmp = Path(tempfile.mkdtemp(prefix="retour-vendor-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        racine = tmp / "racine"
        shutil.copytree(VENDOR.exiger(ROOT, "cadre"), racine / ".agents" / "vendor" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.assertFalse((racine / "src").exists(), "racine vendor seul : aucun src/")
        bin_ = poser_generateur(tmp / "kit", BIN, racine)
        self.assertFalse((bin_ / "vendor_paths.py").exists(), "témoin A : kit SANS vendor_paths.py")
        sonde = "import sys; sys.path.insert(0, sys.argv[1]); import record_id as r; print(r.mint('T'))"
        res = subprocess.run([sys.executable, "-I", "-B", "-c", sonde, str(bin_)], capture_output=True,
                             text=True, encoding="utf-8", timeout=60, check=False)
        self.assertEqual(res.returncode, 0, f"mint refusé dans le kit vendor seul : {res.stderr}")
        self.assertRegex(res.stdout.strip(), r"\AT-[0-9A-HJKMNP-TV-Z]{26}\Z")


class RetourPromptFusionTests(unittest.TestCase):
    """R16 : la fusion du lanceur de fournée APPELLE le verbe. Le lanceur VOYAGE
    (`.claude/workflows/`, T-01M57JS1GFPVQ93BGEFGX08FDB) : la classe joue aussi
    chez l'adoptant, et se tait, en le disant, si le fichier manque."""

    def setUp(self):
        self.js = ROOT / ".claude" / "workflows" / "workflow-fournee.js"
        if not self.js.is_file():
            self.skipTest(f"{self.js} absent : R16 non joué")

    def r_16(self, js: Path) -> None:
        texte = js.read_text(encoding="utf-8")
        debut = texte.find("function promptFusion(")
        self.assertGreaterEqual(debut, 0, "promptFusion absente")
        corps = texte[debut:texte.find("\n}\n", debut)]
        # La branche validée de la grappe, jamais celle que le dev rend ; l'interpréteur par pyrun (portable).
        self.assertIn("bash .agents/pyrun.sh .agents/bin/tasks.py retour ${g.taches.join(' ')} --base ${A.base} "
                      "--branche ${g.branche}", corps)
        self.assertNotIn("${d.branche}", corps)
        self.assertIn("rc ≠ 0 : NE FUSIONNE PAS — fusionne=false, motif_refus = sa sortie", corps)
        self.assertIn("« doublon vierge, supprimable : worktree-<nom du dossier> »", corps)
        self.assertIn(r"SAUF \`tasks.py retour\`", corps)
        self.assertNotIn("git merge-base --is-ancestor ${A.base}", corps)
        self.assertNotIn("status --porcelain", corps)

    def test_r16(self):
        self.r_16(self.js)

    def test_mutant_prose_retablie(self):
        texte = self.js.read_text(encoding="utf-8")
        ancre = (r"1. CONTRÔLE DE RETOUR MÉCANIQUE, dans UN appel séparé, AVANT toute fusion : \`bash .agents/pyrun.sh "
                 r".agents/bin/tasks.py retour ${g.taches.join(' ')} --base ${A.base} --branche ${g.branche}\`.")
        self.assertEqual(texte.count(ancre), 1, "ancre ambiguë ou absente dans workflow-fournee.js")
        dossier = Path(tempfile.mkdtemp(prefix="retour-js-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        mutant = dossier / "workflow-fournee.js"
        mutant.write_text(texte.replace(ancre, r"1. QUATRE CONTRÔLES. a. \`git merge-base --is-ancestor "
                                               r"${A.base} ${g.branche}\` rend 0 ;"), encoding="utf-8")
        with self.assertRaises(AssertionError, msg="mutant SURVIVANT : prose rétablie"):
            self.r_16(mutant)

    def test_mutant_branche_rendue_par_le_dev(self):
        texte = self.js.read_text(encoding="utf-8")
        ancre = r"\`git merge --no-ff -q ${g.branche} -m"
        self.assertEqual(texte.count(ancre), 1, "ancre ambiguë ou absente dans workflow-fournee.js")
        dossier = Path(tempfile.mkdtemp(prefix="retour-js-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        mutant = dossier / "workflow-fournee.js"
        mutant.write_text(texte.replace(ancre, r"\`git merge --no-ff -q ${d.branche} -m"), encoding="utf-8")
        with self.assertRaises(AssertionError, msg="mutant SURVIVANT : fusion de la branche rendue par le dev"):
            self.r_16(mutant)


if __name__ == "__main__":
    unittest.main()
