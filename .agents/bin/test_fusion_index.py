"""T-01M5X9143QVEGWMBYANB6MB4TD (lot A de T-01M54GECXDCHQF3R18H995B76C) — banc du pilote de fusion de l'INDEX,
`fusion_enregistrement.py --index %O %A %B %P` (`merge=cadre-index`, `.gitattributes`).

Témoins de l'annexe du plan : A1 (fusion RÉELLE, `.gitattributes` du kit copié, pilote armé par
`commande_driver_index` : 0 chemin UU ; contrôles sans pilote et copie absente : chaque fichier d'index en UU) ; A2
(`INDEX_DELTA.json` fusionné = max(A, B), jamais « nous ») ; A3 (stderr nomme `SYM-<O+1>..SYM-<min(A,B)>`) ; A4
(`--verifier` sans clé d'index : ligne `index : absent` AVANT la dernière, dernière ligne et rc du board inchangés ;
`.name` seul : « à moitié armé »). Réserve C3 du plan-critic : les `:: but` et les cellules Role/Owner de « eux » sont
REPORTÉS sur la même clé à identité égale, sinon rc 4 et %A intact (la commande rejoue la fusion texte de git) — C1-C6
sont purs, sans git, et ne sautent jamais ; A1-A4 exécutent git et SAUTENT, dit, quand `sonder_git()` nomme une
capacité absente. M1 tient l'égalité des motifs miroirs avec `build_index.py`.
"""

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PILOTE = HERE / "fusion_enregistrement.py"
INDEX_REL = Path(".agents") / "state" / "index"
SUIVI_REL = Path(".agents") / "bin" / "fusion_enregistrement.py"
FICHIERS = ("SYMBOLS.md", "SYMBOLS_scripts.md", "CODEBASE_INDEX.md", "INDEX_BODIES.json", "INDEX_DELTA.json")
BASE_MAX, A_MAX, B_MAX = 29935, 29937, 29939

P: Any = None
SONDE: dict[str, str] = {}
TMP = Path()
_RESTAURER: list[Any] = []


def setUpModule() -> None:
    global P, SONDE, TMP
    tmp = tempfile.TemporaryDirectory(prefix="fi-", ignore_cleanup_errors=True)
    _RESTAURER.append(tmp.cleanup)
    TMP = Path(tmp.name)
    (TMP / "gitconfig-global").write_bytes(b"")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "EMAIL"}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(TMP / "gitconfig-global"))
    patch = mock.patch.dict(os.environ, env, clear=True)
    patch.start()
    _RESTAURER.append(patch.stop)
    spec = importlib.util.spec_from_file_location("fusion_index_banc", PILOTE)
    assert spec is not None and spec.loader is not None
    P = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = P
    spec.loader.exec_module(P)
    SONDE = P.sonder_git(str(TMP))


def tearDownModule() -> None:
    while _RESTAURER:
        _RESTAURER.pop()()


def git(depot: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True, timeout=120, check=False)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : rc={p.returncode} {p.stderr[-400:]}")
    return p


def ligne_sym(n: int, chemin: str, nom: str, but: str = "") -> str:
    return f"SYM-{n:05d}  {chemin}:1-2  {nom}  function  uses[]  ::" + (f" {but}" if but else "")


def shard(sha: str, syms: list[str]) -> str:
    return (f"# Symbols — {len(syms)} entries — built @ {sha} · backend fallback\n"
            "# grammar:  SYM-NNN  <path>:<start>-<end>  <name>  <kind>  uses[SYM-…]  :: <purpose ≤10 words>\n\n"
            + "".join(s + "\n" for s in syms))


def codebase(sha: str, roles: dict[str, tuple[str, str]]) -> str:
    lignes = [f"# Codebase index — built @ {sha} · backend fallback", "", "## Modules",
              "| Path | Role | Depends on | Owner agent |", "|------|------|------------|-------------|"]
    lignes += [f"| {mod} | {role} | — | {owner} |" for mod, (role, owner) in roles.items()]
    return "\n".join(lignes) + "\n"


def delta(sha: str, plafond: int) -> str:
    return json.dumps({"built_sha": sha, "backend": "fallback", "max_sym_id": plafond}, indent=2) + "\n"


def cote(sha: str, ajouts: list[str], plafond: int, buts: dict[int, str] | None = None,
         roles: dict[str, tuple[str, str]] | None = None) -> dict[str, str]:
    """Les cinq fichiers d'index d'un côté : la base (SYM-29930..29935) plus `ajouts`, des en-têtes `built @ <sha>`
    propres au côté (M2 : ils suffisent à faire conflicter chaque fichier sans pilote)."""
    buts = buts or {}
    syms = [ligne_sym(n, "scripts/base.py", f"b{n}", buts.get(n, "")) for n in range(29930, BASE_MAX + 1)] + ajouts
    roles = roles or {"scripts": ("—", "—"), "docs": ("Guides", "documenter")}
    corps = {str(n): f"{n:016x}" for n in range(29930, plafond + 1)}
    return {"SYMBOLS.md": f"# Symbols — built @ {sha}\n- scripts  {len(syms)} symbols  →  SYMBOLS_scripts.md\n",
            "SYMBOLS_scripts.md": shard(sha, syms), "CODEBASE_INDEX.md": codebase(sha, roles),
            "INDEX_BODIES.json": json.dumps({"algo": "sha256-16-rstrip", "built_sha": sha, "bodies": corps},
                                            indent=2) + "\n",
            "INDEX_DELTA.json": delta(sha, plafond)}


class _Banc(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(dir=TMP))

    def jouer(self, nom: str, base: str, nous: str, eux: str) -> tuple[int, str, str]:
        """`main --index` sur trois fichiers jetables ; rend (rc, %A après, stderr)."""
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        chemins = []
        for cote_, texte in (("O", base), ("A", nous), ("B", eux)):
            (d / cote_).write_text(texte, encoding="utf-8")
            chemins.append(str(d / cote_))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = P.main(["fusion_enregistrement.py", "--index", *chemins, f".agents/state/index/{nom}"])
        return rc, (d / "A").read_text(encoding="utf-8"), err.getvalue()


class PurTests(_Banc):
    """Sans git : ne sautent jamais."""

    def test_M1_motifs_miroirs_de_build_index(self) -> None:
        """M1 : `LIGNE_SYM` / `LIGNE_MODULE` == `ACTIVE_RE` / `ROW_RE` de build_index.py (lus par l'AST). MUTANT : un
        motif miroir qui dérive ⇒ rouge."""
        motifs = {}
        for noeud in ast.walk(ast.parse((HERE / "build_index.py").read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Assign) and isinstance(noeud.targets[0], ast.Name) \
                    and noeud.targets[0].id in ("ACTIVE_RE", "ROW_RE") and isinstance(noeud.value, ast.Call):
                motifs[noeud.targets[0].id] = ast.literal_eval(noeud.value.args[0])
        self.assertEqual({"ACTIVE_RE": P.LIGNE_SYM.pattern, "ROW_RE": P.LIGNE_MODULE.pattern}, motifs)

    def test_C1_but_de_eux_reporte_sur_le_meme_id(self) -> None:
        """C3 : « eux » écrit le `:: but` de SYM-29931, « nous » change seulement son en-tête ⇒ rc 0, %A = « nous »
        avec ce but, compte dit sur stderr. MUTANT : le report retiré (but jeté) ⇒ rouge."""
        base = shard("o", [ligne_sym(29931, "scripts/base.py", "b1")])
        nous = shard("a", [ligne_sym(29931, "scripts/base.py", "b1"), ligne_sym(29936, "scripts/t_a.py", "ta1")])
        eux = shard("b", [ligne_sym(29931, "scripts/base.py", "b1", "écrit par eux")])
        rc, a, err = self.jouer("SYMBOLS_scripts.md", base, nous, eux)
        self.assertEqual(0, rc, err)
        attendu = shard("a", [ligne_sym(29931, "scripts/base.py", "b1", "écrit par eux"),
                              ligne_sym(29936, "scripts/t_a.py", "ta1")])
        self.assertEqual(attendu, a)
        self.assertIn("1 valeur(s) de « eux » reprise(s)", err)

    def test_C2_identite_autre_ou_absente_repli_A_intact(self) -> None:
        """C3 : le but de « eux » sur un id qui désigne un AUTRE symbole chez « nous » (collision), ou un id absent de
        « nous » ⇒ rc 4, %A intact, cause dite. MUTANT : `Repli` remplacé par un saut (but perdu) ⇒ rouge."""
        base = shard("o", [])
        eux = shard("b", [ligne_sym(29936, "scripts/t_b.py", "tb1", "but de eux")])
        for nous in (shard("a", [ligne_sym(29936, "scripts/t_a.py", "ta1")]), shard("a", [])):
            rc, a, err = self.jouer("SYMBOLS_scripts.md", base, nous, eux)
            self.assertEqual((4, nous), (rc, a), err)
            self.assertIn("SYM-29936 : absent de « nous » sous la même identité", err)
            self.assertIn("fusion texte de git", err)

    def test_C3_but_change_des_deux_cotes_repli(self) -> None:
        """Le même but changé des deux côtés vers deux valeurs ⇒ rc 4, %A intact ; vers la MÊME valeur ⇒ rc 0."""
        base = shard("o", [ligne_sym(29931, "scripts/base.py", "b1")])
        nous = shard("a", [ligne_sym(29931, "scripts/base.py", "b1", "nous")])
        rc, a, err = self.jouer("SYMBOLS_scripts.md", base, nous,
                                shard("b", [ligne_sym(29931, "scripts/base.py", "b1", "eux")]))
        self.assertEqual((4, nous), (rc, a), err)
        self.assertIn("changé des deux côtés", err)
        rc, a, err = self.jouer("SYMBOLS_scripts.md", base, nous,
                                shard("b", [ligne_sym(29931, "scripts/base.py", "b1", "nous")]))
        self.assertEqual((0, nous), (rc, a), err)

    def test_C4_cellules_role_owner_reportees(self) -> None:
        """C3 : Role ET Owner écrits par « eux » sur `scripts` ⇒ reportés sur la ligne de « nous », « Depends on » de
        « nous » gardé ; un module de « eux » absent de « nous » ⇒ rc 4, %A intact. MUTANT : cellules jetées ⇒ rouge."""
        base = codebase("o", {"scripts": ("—", "—")})
        nous = codebase("a", {"scripts": ("—", "—")}).replace("| scripts | — | — |", "| scripts | — | docs |")
        eux = codebase("b", {"scripts": ("Sondes", "dev-mono")})
        rc, a, err = self.jouer("CODEBASE_INDEX.md", base, nous, eux)
        self.assertEqual(0, rc, err)
        self.assertIn("| scripts | Sondes | docs | dev-mono |\n", a)
        self.assertTrue(a.startswith("# Codebase index — built @ a "), a)
        eux = codebase("b", {"scripts": ("—", "—"), "zz": ("Neuf", "dev-mono")})
        rc, a, err = self.jouer("CODEBASE_INDEX.md", base, nous, eux)
        self.assertEqual((4, nous), (rc, a), err)

    def test_C5_delta_plafond_max_et_recouvrement_dit(self) -> None:
        """A2/A3 en pur : max_sym_id = max(O, A, B), le reste de « nous » gardé ; recouvrement SYM-29936..SYM-29937
        dit. Base vide (ajout/ajout) : plafond 0. DELTA illisible ⇒ rc 4, %A intact."""
        rc, a, err = self.jouer("INDEX_DELTA.json", delta("o", BASE_MAX), delta("a", A_MAX), delta("b", B_MAX))
        self.assertEqual(0, rc, err)
        self.assertEqual(delta("a", B_MAX), a)
        self.assertIn("SYM-29936..SYM-29937 alloués des deux côtés", err)
        rc, a, err = self.jouer("INDEX_DELTA.json", delta("o", BASE_MAX), delta("a", B_MAX), delta("b", BASE_MAX))
        self.assertEqual((0, delta("a", B_MAX), ""), (rc, a, err))
        rc, a, err = self.jouer("INDEX_DELTA.json", "", delta("a", 3), delta("b", 5))
        self.assertEqual((0, delta("a", 5)), (rc, a), err)
        self.assertIn("SYM-001..SYM-003", err)
        rc, a, err = self.jouer("INDEX_DELTA.json", delta("o", 1), delta("a", 2), "{pas du json")
        self.assertEqual((4, delta("a", 2)), (rc, a), err)

    def test_C6_entrees_fautives_sur_le_canal_reel(self) -> None:
        """Canal réel (`main`) : `--index` à 3 arguments ⇒ rc 2 (usage), rien d'écrit ; %B absent ⇒ rc 4, %A intact ;
        autre fichier d'index (INDEX_BODIES.json) ⇒ « nous » gardé, rc 0."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(2, P.main(["f", "--index", "o", "a", "b"]))
        self.assertIn("--index %O %A %B %P", err.getvalue())
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        for nom in ("O", "A"):
            (d / nom).write_text(shard(nom, []), encoding="utf-8")
        with contextlib.redirect_stderr(err):
            rc = P.main(["f", "--index", str(d / "O"), str(d / "A"), str(d / "absent"), "SYMBOLS_x.md"])
        self.assertEqual((4, shard("A", [])), (rc, (d / "A").read_text(encoding="utf-8")))
        self.assertIn("FileNotFoundError", err.getvalue())
        rc, a, err2 = self.jouer("INDEX_BODIES.json", "{}\n", '{"a": 1}\n', '{"b": 2}\n')
        self.assertEqual((0, '{"a": 1}\n'), (rc, a), err2)

    def test_C7_ligne_de_debordement_generee_ignoree(self) -> None:
        """Revue T-01M54GECXD (M3) : la ligne `| (N more) | K symbols — see shards |` que build_index GÉNÈRE au-delà
        de 15 modules, son compte changé des deux côtés ⇒ rc 0, « nous » gardé (la reconstruction la récrit), jamais
        rc 4. MUTANT : `DEBORDEMENT` non consulté par `_entrees` ⇒ rc 4 « changé des deux côtés »."""
        def avec_debordement(sha: str, n: int) -> str:
            return codebase(sha, {"src": ("Core", "dev-mono")}) + f"| (5 more) | {n} symbols — see shards | — | — |\n"
        nous = avec_debordement("a", 122)
        rc, a, err = self.jouer("CODEBASE_INDEX.md", avec_debordement("o", 120), nous, avec_debordement("b", 121))
        self.assertEqual((0, nous), (rc, a), err)

    def test_C8_ligne_hostile_jugee_en_temps_lineaire(self) -> None:
        """Revue sécurité T-01M54GECXD (ReDoS, MEDIUM) : `| a ` + 400 × `| ` + `x` dans le CODEBASE_INDEX.md de
        « eux », sur le canal réel `main --index`, jugé en moins d'une seconde (rc 0, « nous » gardé). Le motif est le
        miroir de `build_index.ROW_RE` (M1) : le même témoin vaut pour lui. MUTANT : l'ancien motif à cellules
        paresseuses `\\s*(.*?)\\s*` ⇒ ~80 s, rouge."""
        hostile = "| a " + "| " * 400 + "x"
        nous = codebase("a", {"src": ("Core", "dev-mono")})
        debut = time.monotonic()
        rc, a, err = self.jouer("CODEBASE_INDEX.md", codebase("o", {}), nous, codebase("b", {}) + hostile + "\n")
        duree = time.monotonic() - debut
        self.assertEqual((0, nous), (rc, a), err)
        self.assertLess(duree, 1.0, f"ligne hostile jugée en {duree:.1f} s : motif à retour arrière (ReDoS)")


class _Depots(_Banc):
    def setUp(self) -> None:
        super().setUp()
        if SONDE.get("verdict") != "tout présent":
            self.skipTest(f"SAUT ANNONCÉ — git sans les capacités du pilote : {P.raison_sonde(SONDE)}")

    def ecrire(self, d: Path, fichiers: dict[str, str]) -> None:
        for nom, texte in fichiers.items():
            (d / INDEX_REL / nom).write_text(texte, encoding="utf-8")

    def init_depot(self, nom: str) -> Path:
        """Dépôt `main` vide, configuré, `.gitattributes` du KIT copié."""
        d = self.tmp / nom
        git(TMP, "-c", "init.defaultBranch=main", "init", "-q", str(d))
        for cle, valeur in (("user.name", "banc"), ("user.email", "banc@example.invalid"),
                            ("commit.gpgsign", "false"), ("core.hooksPath", os.devnull)):
            git(d, "config", cle, valeur)
        shutil.copyfile(REPO / ".gitattributes", d / ".gitattributes")
        return d

    def depot(self, nom: str) -> Path:
        """Dépôt `main` : `.gitattributes` du KIT, le pilote suivi, l'index de base ; branches `a` (+2 symboles,
        plafond 29937) et `b` (+4, plafond 29939, but de SYM-29931 et Role de `scripts` écrits)."""
        d = self.init_depot(nom)
        (d / SUIVI_REL).parent.mkdir(parents=True)
        shutil.copyfile(PILOTE, d / SUIVI_REL)
        (d / INDEX_REL).mkdir(parents=True)
        self.ecrire(d, cote("base", [], BASE_MAX))
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        git(d, "branch", "b")
        self.ecrire(d, cote("aaaaaaa", [ligne_sym(29936, "scripts/t_a.py", "ta1"),
                                        ligne_sym(29937, "scripts/t_a.py", "ta2")], A_MAX))
        git(d, "commit", "-qam", "a")
        git(d, "checkout", "-q", "b")
        self.ecrire(d, cote("bbbbbbb", [ligne_sym(n, "scripts/t_b.py", f"tb{n - 29935}") for n in range(29936, 29940)],
                            B_MAX, buts={29931: "but écrit par eux"}, roles={"scripts": ("Sondes", "dev-mono"),
                                                                                "docs": ("Guides", "documenter")}))
        git(d, "commit", "-qam", "b")
        git(d, "checkout", "-q", "main")
        return d

    def fusionner(self, d: Path) -> tuple[subprocess.CompletedProcess, list[str]]:
        m = git(d, "merge", "--no-edit", "b", check=False)
        return m, sorted(git(d, "diff", "--name-only", "--diff-filter=U").stdout.split())

    def copie(self) -> Path:
        c = self.tmp / "hors-depot" / "fusion_enregistrement-copie.py"
        c.parent.mkdir(exist_ok=True)
        shutil.copyfile(PILOTE, c)
        return c


class FusionReelleTests(_Depots):
    def test_A1_A2_A3_fusion_reelle_zero_conflit(self) -> None:
        """A1 : pilote armé par `commande_driver_index` ⇒ `git merge` rc 0, aucun UU ; A2 : DELTA = 29939 (max) ;
        A3 : stderr `SYM-29936..SYM-29937` ; C3 de bout en bout : but de SYM-29931 et Role/Owner de `scripts` repris.
        MUTANTS : lignes `merge=cadre-index` retirées ⇒ 5 UU ; `max` remplacé par « nous » ⇒ 29937 ; ligne retirée."""
        d = self.depot("a1")
        git(d, "config", "--local", P.CLE_INDEX_DRIVER, P.commande_driver_index(sys.executable, str(self.copie())))
        m, uu = self.fusionner(d)
        self.assertEqual((0, []), (m.returncode, uu), m.stdout + m.stderr)
        lu = json.loads((d / INDEX_REL / "INDEX_DELTA.json").read_text(encoding="utf-8"))
        self.assertEqual(B_MAX, lu["max_sym_id"], "A2 : le plafond fusionné n'est pas max(A, B)")
        self.assertIn("SYM-29936..SYM-29937 alloués des deux côtés", m.stderr)
        symboles = (d / INDEX_REL / "SYMBOLS_scripts.md").read_text(encoding="utf-8")
        self.assertIn(ligne_sym(29931, "scripts/base.py", "b29931", "but écrit par eux") + "\n", symboles)
        self.assertIn("built @ aaaaaaa", symboles)
        self.assertIn("| scripts | Sondes | — | dev-mono |\n",
                      (d / INDEX_REL / "CODEBASE_INDEX.md").read_text(encoding="utf-8"))

    def test_A1b_controles_sans_pilote_et_copie_absente(self) -> None:
        """POLARITÉ d'A1 : sans clé (pilote non armé) ⇒ les cinq fichiers en UU (M2) ; clé armée vers une copie
        ABSENTE ⇒ la fusion texte de git du repli shell, les cinq en UU — jamais pire qu'aujourd'hui."""
        for nom, armer in (("a1b-nu", False), ("a1b-absente", True)):
            d = self.depot(nom)
            if armer:
                git(d, "config", "--local", P.CLE_INDEX_DRIVER,
                    P.commande_driver_index(sys.executable, str(self.tmp / "nulle-part.py")))
            m, uu = self.fusionner(d)
            self.assertEqual((1, sorted((INDEX_REL / f).as_posix() for f in FICHIERS)), (m.returncode, uu), nom)

    def test_A1c_repli_texte_d_un_seul_fichier(self) -> None:
        """C3 de bout en bout : le but de SYM-29931 changé des DEUX côtés ⇒ le pilote rend 4, le repli shell joue
        merge-file : SEUL `SYMBOLS_scripts.md` en UU, à marqueurs ; les quatre autres fusionnés."""
        d = self.depot("a1c")
        self.ecrire(d, {"SYMBOLS_scripts.md": (d / INDEX_REL / "SYMBOLS_scripts.md").read_text(encoding="utf-8")
                        .replace("b29931  function  uses[]  ::", "b29931  function  uses[]  :: but de nous")})
        git(d, "commit", "-qam", "a : but de nous")
        git(d, "config", "--local", P.CLE_INDEX_DRIVER, P.commande_driver_index(sys.executable, str(self.copie())))
        m, uu = self.fusionner(d)
        self.assertEqual((1, [(INDEX_REL / "SYMBOLS_scripts.md").as_posix()]), (m.returncode, uu), m.stdout + m.stderr)
        self.assertIn("<<<<<<<", (d / INDEX_REL / "SYMBOLS_scripts.md").read_text(encoding="utf-8"))
        self.assertIn("changé des deux côtés", m.stderr)


class VerificationTests(_Depots):
    def installer(self, d: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        terminal = mock.Mock(isatty=lambda: True)
        with mock.patch.object(sys, "stdin", terminal), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = P.installer(str(d))
        return rc, out.getvalue(), err.getvalue()

    def verifier(self, d: Path) -> tuple[int, list[str]]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = P.verifier(str(d))
        return rc, out.getvalue().splitlines()

    def test_A4_installer_quatre_cles_et_verifier_index(self) -> None:
        """A4 : `--installer` écrit quatre clés, board d'abord ; `--verifier` : `index : installé` ; clés d'index
        retirées ⇒ `index : absent` AVANT la dernière ligne, dernière ligne et rc du board inchangés ; `.name` seul ⇒
        `index : à moitié armé`, rc du board inchangé. MUTANT : ligne d'index imprimée en dernier ⇒ rouge."""
        d = self.depot("a4")
        rc, out, err = self.installer(d)
        self.assertEqual(0, rc, out + err)
        cles = [c.split()[0] for c in git(d, "config", "--local", "--get-regexp", r"^merge\.").stdout.splitlines()]
        self.assertEqual([P.CLE_DRIVER, P.CLE_NOM, P.CLE_INDEX_DRIVER, P.CLE_INDEX_NOM], cles)
        rc, lignes = self.verifier(d)
        self.assertEqual((0, True), (rc, lignes[-1].startswith("installé : ")), lignes)
        self.assertTrue(any(ligne.startswith("index : installé — ") for ligne in lignes[:-1]), lignes)
        derniere = lignes[-1]
        git(d, "config", "--local", "--unset", P.CLE_INDEX_DRIVER)
        rc, lignes = self.verifier(d)
        self.assertEqual((0, derniere), (rc, lignes[-1]), lignes)
        self.assertTrue(any(ligne.startswith("index : à moitié armé — ") for ligne in lignes[:-1]), lignes)
        git(d, "config", "--local", "--unset", P.CLE_INDEX_NOM)
        rc, lignes = self.verifier(d)
        self.assertEqual((0, derniere), (rc, lignes[-1]), lignes)
        self.assertTrue(any(ligne.startswith("index : absent — ") for ligne in lignes[:-1]), lignes)
        git(d, "config", "--local", P.CLE_INDEX_DRIVER, "true")
        rc, lignes = self.verifier(d)
        self.assertEqual((0, derniere), (rc, lignes[-1]), lignes)
        self.assertTrue(any(ligne.startswith("index : forme inconnue — ") for ligne in lignes[:-1]), lignes)

    def test_A5_ligne_index_controle_copie_et_interpreteur(self) -> None:
        """Revue T-01M54GECXD (M5) : la ligne d'index reprend les contrôles du board — copie dont le contenu n'a pas
        l'empreinte de son nom ⇒ `altérée` ; interpréteur figé absent ⇒ `interpréteur absent` ; copie bien nommée mais
        autre que le pilote de HEAD ⇒ `périmé`. Dernière ligne et rc du board inchangés. MUTANT : `_ligne_index`
        qui rend « installé » dès que la copie existe ⇒ rouge."""
        d = self.depot("a5")
        rc, out, err = self.installer(d)
        self.assertEqual(0, rc, out + err)
        _rc, lignes = self.verifier(d)
        derniere = lignes[-1]
        alteree = self.tmp / f"{P._PREFIXE_COPIE}{'0' * 16}.py"
        alteree.write_text("# altérée\n", encoding="utf-8")
        autre = PILOTE.read_bytes() + b"\n# autre version\n"
        perimee = self.tmp / f"{P._PREFIXE_COPIE}{hashlib.sha256(autre).hexdigest()[:16]}.py"
        perimee.write_bytes(autre)
        for py, copie, statut in ((sys.executable, alteree, "altérée"), ("/nulle/part/python3", alteree,
                                                                           "interpréteur absent"),
                                  (sys.executable, perimee, "périmé")):
            git(d, "config", "--local", P.CLE_INDEX_DRIVER, P.commande_driver_index(py, str(copie)))
            rc, lignes = self.verifier(d)
            self.assertEqual((0, derniere), (rc, lignes[-1]), lignes)
            self.assertTrue(any(ligne.startswith(f"index : {statut} — ") for ligne in lignes[:-1]), (statut, lignes))

    def test_A6_exception_du_board_laisse_stdout_vide(self) -> None:
        """Revue de clôture T-01M54GECXD (T2), canal réel `--verifier` en sous-processus : copie illisible (0o000) ⇒
        le contrôle du board lève (OSError), rc 1, stdout VIDE (aucune ligne `index : …` qui masquerait la raison que
        le setup lit par `raison()`), raison sur stderr. MUTANT : `print(_ligne_index(top))` en tête de `_verifier` ⇒
        stdout porte `index : invérifiable`, rouge."""
        if os.geteuid() == 0:
            self.skipTest("SAUT ANNONCÉ — root lit une copie 0o000")
        d = self.depot("a6")
        rc, out, err = self.installer(d)
        self.assertEqual(0, rc, out + err)
        copie = next((d / ".git" / "cadre").iterdir())
        copie.chmod(0o000)
        try:
            p = subprocess.run([sys.executable, str(d / SUIVI_REL), "--verifier"], cwd=d, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=120, check=False)
        finally:
            copie.chmod(0o400)
        self.assertEqual((1, ""), (p.returncode, p.stdout), p.stdout + p.stderr)
        self.assertIn("vérification : impossible", p.stderr)


class ReconstructionTests(_Depots):
    """Revue T-01M54GECXD (C6 et témoin B) : le pilote d'index ARMÉ (`commande_driver_index`) composé avec une VRAIE
    reconstruction `build_index.py --if-stale` (backend du poste : universal-ctags ou repli, le même des deux côtés)."""

    def construire(self, d: Path, *args: str) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, str(HERE / "build_index.py"), "--root", str(d), "--threshold", "1", *args],
                           capture_output=True, text=True, timeout=300, check=False)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        return p

    def sources(self, d: Path, chemin: str, noms: list[str], message: str) -> None:
        """Écrit `chemin` (une fonction par nom), commite, indexe, commite l'index."""
        (d / chemin).parent.mkdir(parents=True, exist_ok=True)
        (d / chemin).write_text("".join(f"def {n}():\n    return 0\n\n\n" for n in noms), encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-qm", message)
        self.construire(d)
        git(d, "add", "-A")
        git(d, "commit", "-qm", f"index : {message}")

    def ids(self, d: Path) -> dict[str, list[int]]:
        """nom ⇒ ids de ses lignes VIVANTES, tous shards confondus."""
        vus: dict[str, list[int]] = {}
        for f in sorted((d / INDEX_REL).glob("SYMBOLS*.md")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                m = P.LIGNE_SYM.match(ligne)
                if m:
                    vus.setdefault(m.group(5), []).append(int(m.group(1)[4:]))
        return vus

    def plafond(self, d: Path, rev: str) -> int:
        return json.loads(git(d, "show", f"{rev}:{(INDEX_REL / 'INDEX_DELTA.json').as_posix()}").stdout)["max_sym_id"]

    def scenario(self, nom: str, eux: list[tuple[str, list[str]]], nous: tuple[str, list[str]]) -> Path:
        """Base (src/alpha/one.py, scripts/base.py) ; « eux » (branche b) et « nous » (main) indexent chacun de leur
        côté ; pilote d'index armé ; `git merge b`."""
        d = self.init_depot(nom)
        (d / "scripts").mkdir()
        (d / "scripts" / "base.py").write_text("def base_s():\n    return 0\n", encoding="utf-8")
        self.sources(d, "src/alpha/one.py", ["alpha_one"], "base")
        git(d, "checkout", "-qb", "b")
        for chemin, noms in eux:
            self.sources(d, chemin, noms, f"eux {chemin}")
        git(d, "checkout", "-q", "main")
        self.sources(d, *nous, "nous")
        git(d, "config", "--local", P.CLE_INDEX_DRIVER, P.commande_driver_index(sys.executable, str(self.copie())))
        m, uu = self.fusionner(d)
        self.assertEqual((0, []), (m.returncode, uu), m.stdout + m.stderr)
        return d

    def test_C6_pilote_arme_puis_reconstruction_reelle(self) -> None:
        """C6 : « eux » crée `zz/` (zb1, zb2), « nous » ajoute ta1/ta2 sous les MÊMES ids ⇒ merge sans UU ; après
        `--if-stale` : ids de « nous » gardés, ids de « eux » au-dessus de max(O, A, B), rien ne manque, `INDEX
        CURRENT`. MUTANT : la clé `merge.cadre-index.driver` non posée (pilote non armé) ⇒ UU, rouge."""
        d = self.scenario("c6", [("zz/z_b.py", ["zb1", "zb2"])], ("scripts/t_a.py", ["ta1", "ta2"]))
        avant = self.ids(d)
        plafond = max(self.plafond(d, r) for r in ("HEAD^1", "HEAD^2", "HEAD^1^"))
        self.assertEqual(avant["ta1"] + avant["ta2"], sorted(set(avant["zb1"] + avant["zb2"])), "prémisse : ids égaux")
        self.construire(d, "--if-stale")
        apres = self.ids(d)
        self.assertEqual({"alpha_one", "base_s", "ta1", "ta2", "zb1", "zb2"}, set(apres), apres)
        self.assertTrue(all(len(v) == 1 for v in apres.values()), apres)
        self.assertEqual((avant["ta1"], avant["ta2"]), (apres["ta1"], apres["ta2"]))
        self.assertTrue(all(apres[n][0] > plafond for n in ("zb1", "zb2")), (plafond, apres))
        self.assertIn("INDEX CURRENT", self.construire(d, "--stale-check").stdout)

    def test_B_tombstone_d_un_shard_non_cite_n_ecrase_pas_une_vivante(self) -> None:
        """Témoin B : « eux » crée zb1/zb2 puis renomme zb1 en zc1 (tombstone `SYM-N DELETED zb1` dans un shard
        que « eux » seul crée, non cité par la ToC de « nous ») ; « nous » ajoute alpha_two sous le MÊME id N ⇒ après
        merge + `--if-stale`, alpha_two garde N, zc1/zb2 présents, `INDEX CURRENT`. MUTANT : l'ancienne condition
        `not (prev["deleted"] or sym["deleted"])` de `load_existing` ⇒ alpha_two perdu en silence, rouge."""
        d = self.scenario("tomb", [("zz/z_b.py", ["zb1", "zb2"]), ("zz/z_b.py", ["zc1", "zb2"])],
                          ("src/alpha/two.py", ["alpha_two"]))
        avant = self.ids(d)
        tombes = [int(ligne.split()[0][4:]) for f in (d / INDEX_REL).glob("SYMBOLS*.md")
                  for ligne in f.read_text(encoding="utf-8").splitlines() if ligne.split()[1:3] == ["DELETED", "zb1"]]
        self.assertEqual(avant["alpha_two"], tombes, "prémisse : la tombstone de zb1 ne porte pas l'id d'alpha_two")
        self.construire(d, "--if-stale")
        apres = self.ids(d)
        self.assertEqual(avant["alpha_two"], apres.get("alpha_two"), f"alpha_two perdu ou renuméroté : {apres}")
        self.assertEqual({"alpha_one", "alpha_two", "base_s", "zc1", "zb2"}, set(apres), apres)
        self.assertIn("INDEX CURRENT", self.construire(d, "--stale-check").stdout)


if __name__ == "__main__":
    unittest.main()
