"""LA FOURNÉE — comportement (`tasks.py fournee`, `tasks_fournee.py`, `plan_lots.py`).

T-01M4V1JD628K07PXF7FFDSN0Q3, décision pilote S-01M4V1K1DG9WY2WKWKWN7ZGFC7. ZÉRO APPEL LLM.

Chaque témoin `w_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`
(`test_w*`), ou une COPIE JETABLE dont un fragment littéral, présent UNE fois
(asserté), est remplacé. Chaque mutant de `MUTANTS` ne rejoue QUE le témoin qui le
tue, et doit le faire échouer par une ASSERTION. Dépôt jetable par témoin
(`tempfile`, sous `TMPDIR`), CLI en sous-processus, état machine et `HOME` jetables,
`CLAUDE_PROJECT_DIR` et `GIT_*` retirés de l'environnement des sous-processus.

Témoins (plan § Tests) : W1 grammaire ×7 ; W2 recouvrements ; W3 partagés et
`.agents/state/` ; W4 roster orphelin ; W5 trace absente, sha256 dérivé,
`night-eligible` ; W6 nominal armé (UN groupe, UNE ligne de journal au nom du parent,
emprunt nommant le parent, marque de lot) ; W7 pannes injectées en quatre points,
R vide et R non vide, puis relance ; W8 recouvrement avec un `running` (refus,
octets identiques) et jamais de rétrogradation ; W9 `--dry-run` (racine identique,
intention V3 pendante comprise) ; W10 désarmé ; W11 héritage mesure/motif ; W12
voyage ; W13 `plan_lots.py` chemin de garde ; W14 extension d'un groupe vivant,
membre `pending`, `running` sans write-set ; W15 fournée dégénérée ; W16 `--sans-*`
sur chaque membre ; W17 write-set du parent groupé jamais réécrit ; W18 re-découpe
(sha des lots, réserve C1.2) ; W19 parent estampillé `direct` (C1.3) ; W20
intégration et revue partagées (C3) ; W21 `plan_lots.py check`.

Passe de correction de la revue de clôture : W5 `--dry-run` refusé rend rc 2 ; W7
R non vide panne (2), aucun lot ne consomme ; W11 b4 parent sans motif ni
`pas_un_defaut` ; W22 lot clos sauté sous un plan ré-approuvé ; W23 R deux à deux
(`depends`) ; W24 plan non UTF-8 ; W25 plan hors racine résolue ; W26 write-set
à antislash, relance. Deuxième passe : W22 chemin ajouté à un lot clos DIT, compte
du lot clos ; W27 lot sur le chemin du plan ; W28 l'union (`depends` lot/lot et
parent/lot) ; W29 libellé de lot ouvert par « fix », garde de mesure armée.
Troisième passe : W28 lien posé AVANT le groupe (panne à l'étape 4) ; W30 lien vers
un lot clos, jamais un refus ; W31 relance déjà groupée, `block B --on A` gardé.
Fournée dégénérée, write-set réel exigé (T-01M4VX9GRQ82YMJHS37XTW6VAY) : W15 amendé
(write-set déclaré avant, intact après) ; W32 sans chemin hors du plan (casse
comprise) ; W33 R contre le write-set réel, et deux dégénérées disjointes groupées ;
W34 R réduite à son plan par l'ancien code ; W35 relance d'une dégénérée groupée.
Passe de correction du lot A : W36 parent À LOTS dans R, jamais pris pour une dégénérée (M1) ;
W34 amendé (R groupée, board écrit à la main ; remède sans `parallel`, joué jusqu'à rc 0) ;
W37 chemin inadmissible écrit à la main au write-set d'une dégénérée.
Revue de clôture du lot A, F1 : W38 le plan d'une dégénérée AJOUTÉ à son write-set déclaré dans
la disjonction, jamais substitué — R sur ce plan, et plan d'une R dégénérée déclaré par la fournée.
Plusieurs `running` légitimes (T-01M5F728B4CS1ZDZTH9YWJ0AZ1, lot B) : R n'est NI embarquée NI
rétrogradée (`external_running_not_embarked`, W7r W8b W14 W14b W20 W23 W30 W33 W34 W35 W36 amendés :
R réduite à son plan DITE, jamais refusée ; R sans write-set REFUSÉE, la disjonction serait vide —
W14b ; règle B bornée au groupe du parent ; ni record, ni intent, ni ligne V3 de R écrits) ;
`parallel_refuses_overlap` : `parallel` refuse toujours deux write-sets recouvrants.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "plan_lots.py", "specs.py",
          "events.py", "record_id.py", "kickoff_guard.py", "vendor_paths.py")
LOT_A = [".agents/bin/tasks_x.py", "src/a.py"]
LOT_B = ["docs/b.md", "docs/c.md"]
PLAN = "docs/tasks/plan.md"
#: Un plan dégénéré qui enrôle `{}` (ligne 1) : `DEGENEREE.format` est le `texte_plan` de `parent_pret`.
DEGENEREE = "# PLAN — {}\n\nLOTS: aucun | trop petit\n"


def _maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def copie(case: unittest.TestCase, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable du vrai `bin`, chaque ancre remplacée UNE fois. `src` et
    `agentic_v3` y sont LIÉS à leur emplacement réel : le générateur d'ids et le pont V3 restent les vrais."""
    base = Path(tempfile.mkdtemp(prefix="fournee-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in BIN.glob(motif):
            if not f.name.startswith("test_"):
                shutil.copy2(f, dest / f.name)
    (base / "src").symlink_to(ROOT / "src", target_is_directory=True)
    v3 = Path(".agents/vendor/agentic_v3") if (ROOT / ".agents/vendor/agentic_v3/__init__.py").is_file() else Path("agentic_v3")
    (base / v3).parent.mkdir(parents=True, exist_ok=True)
    (base / v3).symlink_to(ROOT / v3, target_is_directory=True)
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
    nom = f"tasks_fournee_banc_{abs(hash(str(bin_)))}"
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, bin_ / "tasks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def plan_texte(parent: str, lots=(("A", "dev-multi", "moteur", LOT_A), ("B", "dev-mono", "doc", LOT_B)),
               integration: str | None = "CHANGELOG.md", extra: str = "") -> str:
    lignes = [f"# PLAN — {parent}", "", "## Steps", "1. faire — angle mort: banc ?", "", "## Lots"]
    lignes += [f"LOT: {cle} | {dev} | {lib} | {', '.join(chemins)}" for cle, dev, lib, chemins in lots]
    if integration is not None:
        lignes.append(f"INTÉGRATION: {integration}")
    return "\n".join(lignes) + "\n" + extra


class Banc:
    """Un dépôt jetable et la CLI de `bin_` braquée dessus."""

    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin = case, bin_
        self.d = Path(tempfile.mkdtemp(prefix="fournee-"))
        case.addCleanup(shutil.rmtree, self.d, True)
        self.etat = Path(tempfile.mkdtemp(prefix="fournee-etat-"))
        case.addCleanup(shutil.rmtree, self.etat, True)
        maison = Path(tempfile.mkdtemp(prefix="fournee-home-"))
        case.addCleanup(shutil.rmtree, maison, True)
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@exemple.invalid\n",
                                           encoding="utf-8")
        for sous in ("board", "gates", "local/plan", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        self.env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        self.env.update(HOME=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                        CADRE_STATE_DIR=str(self.etat), AGENTS_EVENTS_DIR=str(self.etat / "events"))
        self.entrees: list[dict] = []

    def t(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=180, env=self.env)

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 0, f"{args} : {r.stdout}{r.stderr}")
        return r

    def refus(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 2, f"{args} aurait dû être refusé : {r.stdout}{r.stderr}")
        return r

    def check(self, texte: str, *extra: str) -> subprocess.CompletedProcess:
        chemin = self.d / "docs" / "check.md"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")
        return subprocess.run([sys.executable, str(self.bin / "plan_lots.py"), "check", "--plan", str(chemin),
                               "--root", str(self.d), *extra], capture_output=True, text=True, timeout=120,
                              env=self.env)

    def nouvelle(self, titre: str = "tâche de banc", chemins: list[str] | None = None, *extra: str) -> str:
        r = self.ok("new", titre, *extra)
        tid = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M).group(1)
        if chemins:
            self.ok("writeset", tid, *chemins)
        return tid

    def armer(self, nom: str, contenu: str = "") -> None:
        (self.d / ".agents" / "state" / "gates" / nom).write_text(contenu, encoding="utf-8")

    def chaine(self) -> None:
        for nom, role in (("planner", "planner"), ("plan-critic", "reviewer")):
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": _maintenant(), "sha": "abc", "role": role}), encoding="utf-8")

    def plan(self, texte: str, rel: str = PLAN) -> str:
        chemin = self.d / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")
        return rel

    def approuver(self, tid: str, rel: str = PLAN, titre: str = "plan approuvé", sha: str | None = None) -> None:
        sha = sha or hashlib.sha256((self.d / rel).read_bytes()).hexdigest()
        self.entrees.append({"id": f"S-{len(self.entrees) + 1:08d}", "task": tid, "kind": "decision",
                             "title": titre, "text": f"plan={rel} sha256={sha}", "files": [], "date": "2026-10-13"})
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"entries": self.entrees}), encoding="utf-8")

    def parent_pret(self, texte_plan=None, *extra_new: str) -> str:
        """Un parent, son plan écrit et approuvé."""
        p = self.nouvelle("parent de banc", None, *extra_new)
        self.plan(texte_plan(p) if texte_plan else plan_texte(p))
        self.approuver(p)
        return p

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def taches(self) -> list[dict]:
        return json.loads(self.ok("list", "--json").stdout)

    def lots(self, parent: str) -> dict[str, dict]:
        return {t["fournee"]["lot"]: t for t in self.taches()
                if isinstance(t.get("fournee"), dict) and t["fournee"].get("parent") == parent}

    def journal(self) -> list[str]:
        p = self.d / ".agents" / "state" / "local" / "plan-chain-consommations.log"
        return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []

    def board(self) -> bytes:
        return (self.d / ".agents" / "state" / "board" / "TASKS.json").read_bytes()

    def abimer(self, tid: str, **champs) -> None:
        """Écrit `champs` sur `tid` À LA MAIN dans `TASKS.json` : un board qu'aucun verbe ne produit
        (ancien code, édition manuelle) — relu tel quel par la CLI (mesuré)."""
        chemin = self.d / ".agents" / "state" / "board" / "TASKS.json"
        data = json.loads(chemin.read_text(encoding="utf-8"))
        (tache,) = [t for t in data["tasks"] if t["id"] == tid]
        tache.update(champs)
        chemin.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def racine(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.d)): p.read_bytes() for p in sorted(self.d.rglob("*")) if p.is_file()}

    def en_processus(self):
        return mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(self.etat), "HOME": self.env["HOME"],
                                            "AGENTS_EVENTS_DIR": self.env["AGENTS_EVENTS_DIR"]})


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    # -- W1 W2 W3 W4 : la grammaire ------------------------------------------
    def w_01(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        un = (("A", "dev-mono", "x", ["src/a.py"]),)
        cas = {
            "un seul lot": plan_texte("T-1", lots=un),
            "en double": plan_texte("T-1", lots=un + (("A", "dev-mono", "y", ["src/b.py"]),)),
            "proche d'un mot-clé": plan_texte("T-1") + "LOT : C | dev-mono | z | src/z.py\n",
            "`LOTS: aucun` à côté": plan_texte("T-1") + "LOTS: aucun\n",
            "n'est pas un chemin exact": plan_texte("T-1", lots=un + (("B", "dev-mono", "y", ["src/*.py", "src/"]),)),
            "ligne malformée": plan_texte("T-1", lots=un + (("B", "dev-x", "y", ["src/b.py"]),)),
            "aucune ligne `INTÉGRATION:`": plan_texte("T-1", integration=None),
        }
        for attendu, texte in cas.items():
            r = b.check(texte)
            self.assertEqual(r.returncode, 1, f"{attendu} : {r.stdout}{r.stderr}")
            self.assertIn(attendu, r.stdout, attendu)
        multi = (("A", "dev-multi", "moteur", LOT_A), ("B", "dev-multi", "doc", LOT_B))
        r = b.check(plan_texte("T-1", lots=multi))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Un lot dev-mono = UN chemin (S-01M54WQE1K4VQKJ9STTJ7A1DQ2) : le même B en dev-mono est refusé.
        r = b.check(plan_texte("T-1", lots=(multi[0], ("B", "dev-mono", "doc", LOT_B))))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("lot B : dev-mono déclare 2 chemins", r.stdout)
        p = b.nouvelle("parent")
        b.plan(plan_texte(p, lots=un))
        b.approuver(p)
        avant = b.board()
        r = b.refus("fournee", p)
        self.assertIn("un seul lot", r.stderr)
        self.assertEqual(b.board(), avant, "un refus de grammaire a écrit le board")

    def w_02(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        r = b.check(plan_texte("T-1", lots=(("A", "dev-mono", "x", ["docs/b.md"]), ("B", "dev-mono", "y", ["Docs/B.md"]))))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("recouvrement : lot A", r.stdout)
        r = b.check(plan_texte("T-1", lots=(("A", "dev-mono", "x", ["src/a.py", "CHANGELOG.md"]),
                                            ("B", "dev-mono", "y", ["src/b.py"]))))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("et l'INTÉGRATION", r.stdout)

    def w_03(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        for chemin, attendu in (("package.json", "lockfile ou un manifeste"), ("build.gradle.kts", "lockfile"),
                                (".agents/state/board/x.json", "sous `.agents/state/`")):
            r = b.check(plan_texte("T-1", lots=(("A", "dev-mono", "x", ["src/a.py", chemin]),
                                                ("B", "dev-mono", "y", ["src/b.py"]))))
            self.assertEqual(r.returncode, 1, f"{chemin} : {r.stdout}")
            self.assertIn(attendu, r.stdout, chemin)
        r = b.check(plan_texte("T-1", integration=".agents/state/x.md"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("INTÉGRATION : `.agents/state/x.md`", r.stdout)

    def w_04(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        roster = b.d / "src" / "cadre" / "data" / "roster" / "planner.json"
        roster.parent.mkdir(parents=True)
        roster.write_text("{}", encoding="utf-8")
        orphelin = (("A", "dev-multi", "x", [".claude/agents/planner.md", ".codex/agents/planner.toml"]),
                    ("B", "dev-mono", "y", ["src/b.py"]))
        r = b.check(plan_texte("T-1", lots=orphelin))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("roster orphelin", r.stdout)
        complet = ((orphelin[0][0], "dev-multi", "x", orphelin[0][3] + ["src/cadre/data/roster/planner.json"]), orphelin[1])
        r = b.check(plan_texte("T-1", lots=complet))
        self.assertEqual(r.returncode, 0, r.stdout)

    # -- W5 : la trace ---------------------------------------------------------
    def w_05(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.nouvelle("parent")
        b.plan(plan_texte(p))
        avant = b.board()
        self.assertIn("aucune décision `plan approuvé`", b.refus("fournee", p, "--dry-run").stderr,
                      "--dry-run d'un prévol refusé ne rend pas rc 2")
        self.assertIn("aucune décision `plan approuvé`", b.refus("fournee", p).stderr)
        b.approuver(p, titre="night-eligible: approved")
        self.assertIn("night-eligible", b.refus("fournee", p).stderr)
        b.approuver(p)
        b.plan(plan_texte(p) + "ajout après l'approbation\n")
        r = b.refus("fournee", p)
        self.assertIn("empreinte divergente", r.stderr, "un sha256 dérivé a lancé la fournée")
        self.assertEqual(b.board(), avant, "un refus de trace a écrit le board")

    # -- W6 : nominal armé -----------------------------------------------------
    def w_06(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        b.chaine()
        p = b.parent_pret()
        sha = hashlib.sha256((b.d / PLAN).read_bytes()).hexdigest()
        r = b.ok("fournee", p)
        self.assertIn("FOURNEE: ok", r.stdout)
        lots, parent = b.lots(p), b.tache(p)
        self.assertEqual(sorted(lots), ["A", "B"])
        membres = [parent] + list(lots.values())
        self.assertEqual({t["state"] for t in membres}, {"running"})
        self.assertEqual(len({t["parallel_group"] for t in membres}), 1, "plus d'un groupe")
        self.assertEqual([ligne.split("\t")[1] for ligne in b.journal()], [p], "la chaîne n'est pas payée UNE fois, au parent")
        self.assertTrue(parent.get("plan_chain_consumed"))
        self.assertFalse(any(t.get("plan_chain_consumed") for t in lots.values()), "un lot a consommé")
        self.assertIn(f"[chaîne de plan empruntée au groupe, portée par {p}]", lots["A"]["stage"])
        self.assertIn("direct refusé : C2", lots["A"]["stage"])
        self.assertIn(f"[DIRECT — lot B du plan {sha[:12]} : 2 fichier(s), 2 validé(s) par direct]", lots["B"]["stage"])
        self.assertEqual(parent["writeset"], [PLAN])
        self.assertEqual(lots["A"]["writeset"], LOT_A)
        self.assertEqual(parent["fournee"], {"lots": [lots["A"]["id"], lots["B"]["id"]], "plan": PLAN,
                                             "sha256": sha, "trace": "S-00000001"})
        self.assertEqual(lots["B"]["fournee"], {"parent": p, "lot": "B", "plan": PLAN, "sha256": sha,
                                                "trace": "S-00000001"})
        self.assertEqual(lots["A"]["owner"], "dev-multi")

    # -- W7 : pannes injectées, relance -----------------------------------------
    def _w07_un(self, bin_: Path, point: str, avec_r: bool) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        r_ids: list[str] = []
        if avec_r:
            r_ids = [b.nouvelle("r1", ["src/r1.py"]), b.nouvelle("r2", ["src/r2.py"])]
            b.ok("parallel", *r_ids)
            b.chaine()
            b.ok("start", r_ids[0])
            b.ok("start", r_ids[1])
        b.chaine()
        p = b.parent_pret()
        mod = charger(bin_)
        reels = {nom: getattr(mod, nom) for nom in ("new_task", "set_writeset")}

        def apres_un(nom):
            appels = []

            def leve(*a, **k):
                if appels:
                    raise mod.BoardError(f"panne de banc dans {nom}")
                appels.append(1)
                return reels[nom](*a, **k)
            return leve

        def panne(*_a, **_k):
            raise mod.BoardError(f"panne de banc au point {point}")
        cible, remplacement = {"(1)": ("new_task", apres_un("new_task")),
                               "(2)": ("set_writeset", apres_un("set_writeset")),
                               "(4)-(5)": ("fournee_etape_parent", panne),
                               "(5)-(6)": ("fournee_etape_lots_start", panne)}[point]
        with b.en_processus(), mock.patch.object(mod, cible, remplacement):
            with self.assertRaises(mod.BoardError) as ctx:
                mod.fournee(str(b.d), p)
        self.assertIn("relance `tasks.py fournee", str(ctx.exception), f"{point} : l'échec ne nomme pas le remède")
        b.ok("fournee", p)
        lots, parent = b.lots(p), b.tache(p)
        self.assertEqual(sorted(lots), ["A", "B"], f"{point} : doublon ou lot manquant")
        self.assertEqual(len([t for t in b.taches() if (t.get("fournee") or {}).get("parent") == p]), 2,
                         f"{point} : un lot en double")
        self.assertEqual((lots["A"]["writeset"], lots["B"]["writeset"]), (LOT_A, LOT_B), f"{point} : réécriture")
        membres, r_taches = [parent] + list(lots.values()), [b.tache(r) for r in r_ids]
        self.assertEqual({t["state"] for t in membres + r_taches}, {"running"}, f"{point} : une tâche ne tourne pas")
        self.assertEqual(len({t["parallel_group"] for t in membres}), 1, f"{point} : plus d'un groupe")
        self.assertEqual(len({t["parallel_group"] for t in r_taches} | {parent["parallel_group"]}),
                         2 if r_ids else 1, f"{point} : R embarquée dans le groupe de la fournée, ou dégroupée")
        self.assertEqual([ligne.split("\t")[1] for ligne in b.journal()].count(p), 1,
                         f"{point} : la chaîne du parent payée {len(b.journal())} fois")
        self.assertFalse(any(t.get("plan_chain_consumed") for t in lots.values()), f"{point} : un lot a consommé")

    def w_07(self, bin_: Path) -> None:
        for point in ("(1)", "(2)", "(4)-(5)", "(5)-(6)"):
            self._w07_un(bin_, point, avec_r=False)

    def w_07r(self, bin_: Path) -> None:
        for point in ("(1)", "(2)", "(4)-(5)", "(5)-(6)"):
            self._w07_un(bin_, point, avec_r=True)

    # -- W8 : un running qui recouvre ; jamais de rétrogradation -----------------
    def w_08(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        r = b.nouvelle("recouvre", ["docs/b.md"])
        b.ok("start", r)
        p = b.parent_pret()
        avant = b.board()
        sortie = b.refus("fournee", p)
        self.assertIn(f"{r} (`docs/b.md`) recouvre le lot B", sortie.stderr)
        self.assertEqual(b.board(), avant, "un recouvrement avec un running a écrit le board")

    def w_08b(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        r = b.nouvelle("à côté", ["src/r.py"])
        b.ok("start", r)
        p = b.parent_pret()
        b.ok("fournee", p)
        seule = b.tache(r)
        self.assertEqual(seule["state"], "running", "la fournée a rétrogradé un running disjoint")
        self.assertIsNone(seule.get("parallel_group"), "la fournée a embarqué un running étranger")
        self.assertTrue(b.tache(p)["parallel_group"])

    # -- Plusieurs `running` légitimes (T-01M5F728B4CS1ZDZTH9YWJ0AZ1) ----------------
    def w_external_running_not_embarked(self, bin_: Path) -> None:
        """R = deux `running` groupées par le pilote + une seule : la fournée ne les embarque pas, ne les
        rétrograde pas — état, stage et groupe gardés ; son groupe est le sien ; R DITE, jamais tue."""
        b = Banc(self, bin_)
        r1, r2, r3 = b.nouvelle("r1", ["src/r1.py"]), b.nouvelle("r2", ["src/r2.py"]), b.nouvelle("r3", ["src/r3.py"])
        b.ok("parallel", r1, r2)
        for r in (r1, r2, r3):
            b.ok("start", r)
        b.ok("stage", r3, "revue en cours")
        avant = {r: b.tache(r) for r in (r1, r2, r3)}

        def brut() -> tuple[list, list, dict]:  # l'enregistrement ENTIER, ses intents, ses lignes V3
            data = json.loads(b.board())
            # L'outbox est VIDÉ à la sauvegarde : l'effet de bord d'un intent se lit au store V3.
            v3 = {}
            for base in sorted(b.etat.rglob("v3_event_store.db")):
                with closing(sqlite3.connect(base)) as conn:
                    for table, requete in (("events_ledger", "SELECT * FROM events_ledger"),
                                           ("board_sync_inbox", "SELECT * FROM board_sync_inbox")):
                        v3[f"{base.name}:{table}"] = sum(1 for ligne in conn.execute(requete)
                                                         if any(r in repr(ligne) for r in avant))
            return ([t for t in data["tasks"] if t["id"] in avant],
                    [i for i in data.get("sync_outbox", []) if set(i["affected_task_ids"]) & set(avant)], v3)
        avant_brut = brut()
        self.assertTrue(avant_brut[2] and all(avant_brut[2].values()), f"store V3 sans ligne de R : {avant_brut[2]}")
        p = b.parent_pret()
        sortie = b.ok("fournee", p).stdout
        self.assertEqual(brut(), avant_brut, "la fournée a réécrit une R ou lui a ajouté un intent")
        self.assertIn(f"running hors fournée, préservées : {r1}, {r2}, {r3} — ni groupées ni rétrogradées", sortie)
        for r, t in avant.items():
            apres = b.tache(r)
            self.assertEqual([apres.get(k) for k in ("state", "stage", "parallel_group")],
                             [t.get(k) for k in ("state", "stage", "parallel_group")], f"{r} touchée par la fournée")
        groupe = b.tache(p)["parallel_group"]
        self.assertEqual({lot["parallel_group"] for lot in b.lots(p).values()}, {groupe})
        self.assertNotIn(groupe, {avant[r1]["parallel_group"], None})

    def w_parallel_refuses_overlap(self, bin_: Path) -> None:
        """`parallel` refuse toujours deux write-sets recouvrants (casse repliée), board identique — y compris
        un lot de fournée contre une running étrangère que la fournée n'a pas embarquée."""
        b = Banc(self, bin_)
        x, y = b.nouvelle("x", ["src/a.py"]), b.nouvelle("y", ["SRC/A.py"])
        avant = b.board()
        self.assertIn("overlapping paths", b.refus("parallel", x, y).stderr)
        self.assertEqual(b.board(), avant, "un `parallel` recouvrant a écrit le board")
        z = b.nouvelle("z", ["src/z.py"])
        b.ok("start", z)
        p = b.parent_pret()
        b.ok("fournee", p)
        b.ok("writeset", z, LOT_B[0])
        avant = b.board()
        self.assertIn("overlapping paths", b.refus("parallel", b.lots(p)["B"]["id"], z).stderr)
        self.assertEqual(b.board(), avant)

    # -- W9 : --dry-run ----------------------------------------------------------
    def w_09(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.parent_pret()
        with b.en_processus():
            charger(bin_).new_task(str(b.d), "intention V3 pendante", "")
        avant = b.racine()
        r = b.ok("fournee", p, "--dry-run")
        self.assertIn("--dry-run, prévol ok", r.stdout)
        self.assertIn("lot A — dev-multi — 2 fichier(s) — à créer", r.stdout)
        self.assertEqual(b.racine(), avant, "--dry-run a écrit sous la racine")

    # -- W10 : désarmé -----------------------------------------------------------
    def w_10(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("fournee", p)
        lots, parent = b.lots(p), b.tache(p)
        self.assertEqual({t["state"] for t in [parent] + list(lots.values())}, {"running"})
        self.assertEqual(b.journal(), [], "désarmé, une chaîne a été consommée")
        self.assertNotIn("plan_chain_consumed", parent)
        self.assertIn("direct", lots["B"], "le lot éligible n'a pas été estampillé")
        self.assertNotIn("[DIRECT", lots["B"]["stage"], "désarmé, une marque directe a été posée")
        self.assertNotIn("empruntée", lots["A"]["stage"])

    # -- W11 : héritage mesure/motif ----------------------------------------------
    def w_11(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("MESURE_REQUIRED")
        p = b.parent_pret(None, "--mesure", "rejoue => observé", "--motif", "garde")
        b.ok("fournee", p)
        for lot in b.lots(p).values():
            self.assertEqual((lot.get("mesure"), lot.get("motif")), ("rejoue => observé", "garde"))
        self.assertIn("direct refusé : C2", b.lots(p)["B"]["stage"], "un motif `garde` hérité a passé en directe")
        b2 = Banc(self, bin_)
        b2.armer("MESURE_REQUIRED")
        p2 = b2.parent_pret(None, "--mesure", "rejoue => observé", "--motif", "gros")
        b2.ok("fournee", p2)
        sha = hashlib.sha256((b2.d / PLAN).read_bytes()).hexdigest()
        self.assertEqual(b2.lots(p2)["A"].get("pas_un_defaut"), f"lot A du plan {sha[:12]} (défaut mesuré sur {p2})")
        self.assertNotIn("motif", b2.lots(p2)["A"])
        b3 = Banc(self, bin_)
        b3.armer("MESURE_REQUIRED")
        p3 = b3.parent_pret(None, "--pas-un-defaut", "une fonctionnalité")
        b3.ok("fournee", p3)
        self.assertEqual(b3.lots(p3)["A"].get("pas_un_defaut"), "une fonctionnalité")
        b4 = Banc(self, bin_)
        p4 = b4.parent_pret()
        b4.armer("MESURE_REQUIRED")
        b4.ok("fournee", p4)
        sha4 = hashlib.sha256((b4.d / PLAN).read_bytes()).hexdigest()
        for cle, lot in b4.lots(p4).items():
            self.assertEqual(lot.get("pas_un_defaut"),
                             f"lot {cle} du plan {sha4[:12]} de {p4} (antérieur à la garde de mesure)")
            self.assertNotIn("motif", lot)

    # -- W12 W13 : voyage, garde --------------------------------------------------
    def w_12(self, bin_: Path) -> None:
        sys.path.insert(0, str(BIN))
        try:
            import sync_template as st
        finally:
            sys.path.remove(str(BIN))
        regles = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for chemin in (".agents/bin/plan_lots.py", ".agents/bin/tasks_fournee.py"):
            self.assertIsNone(st.match_rule(chemin, regles), f"{chemin} ne voyage pas chez l'adoptant")

    def w_13(self, bin_: Path) -> None:
        tasks = charger(bin_)
        self.assertTrue(tasks.est_chemin_de_garde(".agents/bin/plan_lots.py"))
        self.assertEqual(tasks.direct_garde_couvrante(".agents/bin/plan_lots.py"), "liste fermée : .agents/bin/plan_lots.py")

    # -- W14 : un groupe vivant gardé ; le groupe que le PILOTE déclare avec R ----------
    def w_14(self, bin_: Path) -> None:
        """(a) R groupée tourne : la fournée garde son groupe, prend le sien. (b) Panne avant le `start` du
        parent, puis le PILOTE groupe R avec la fournée : la relance n'y touche pas, le parent paie la chaîne
        à son nom (jamais emprunté à R) et chaque lot nomme son parent pour porteur, jamais le premier."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        r1, r2 = b.nouvelle("r1", ["src/r1.py"]), b.nouvelle("r2", ["src/r2.py"])
        b.ok("parallel", r1, r2)
        b.chaine()
        b.ok("start", r1)
        b.ok("start", r2)
        groupe_r = b.tache(r1)["parallel_group"]
        b.chaine()
        p = b.parent_pret()
        mod = charger(bin_)

        def panne(*_a, **_k):
            raise mod.BoardError("panne de banc avant le start du parent")
        with b.en_processus(), mock.patch.object(mod, "fournee_etape_parent", panne):
            with self.assertRaises(mod.BoardError):
                mod.fournee(str(b.d), p)
        lots = b.lots(p)
        self.assertEqual({b.tache(r1)["parallel_group"], b.tache(r2)["parallel_group"]}, {groupe_r})
        self.assertNotEqual(b.tache(p)["parallel_group"], groupe_r, "(a) R embarquée")
        b.ok("parallel", r1, r2, p, lots["A"]["id"], lots["B"]["id"])
        b.ok("fournee", p)
        lots = b.lots(p)
        membres = [b.tache(x) for x in (r1, r2, p)] + list(lots.values())
        self.assertEqual({t["state"] for t in membres}, {"running"})
        self.assertEqual(len({t["parallel_group"] for t in membres}), 1, "(b) le groupe du pilote a été défait")
        self.assertIn(f"portée par {p}]", lots["A"]["stage"], "le porteur nommé n'est pas le parent")
        self.assertEqual([ligne.split("\t")[1] for ligne in b.journal()], [r1, p], "le parent n'a pas payé à son nom")

    def w_14b(self, bin_: Path) -> None:
        """(a) R groupée avec un membre `pending` : plus un refus, rien de R n'est touché. (b) Règle B sur le
        groupe du PARENT : un `pending` étranger que le pilote y a mis refuse la relance, board identique.
        (c) Bob tourne SANS write-set (il écrit `src/a.py`, celui du lot A) : refus, la disjonction serait
        vide (S-01M5FDAP4N), board identique."""
        b = Banc(self, bin_)
        r1, r3 = b.nouvelle("r1", ["src/r1.py"]), b.nouvelle("r3", ["src/r3.py"])
        b.ok("parallel", r1, r3)
        b.ok("start", r1)
        groupe_r = b.tache(r1)["parallel_group"]
        p = b.parent_pret()
        b.ok("fournee", p)
        self.assertEqual([(b.tache(r)["state"], b.tache(r)["parallel_group"]) for r in (r1, r3)],
                         [("running", groupe_r), ("pending", groupe_r)])
        lots = b.lots(p)
        b.ok("parallel", p, lots["A"]["id"], lots["B"]["id"], r3)
        avant = b.board()
        self.assertIn(f"a un membre {r3} `pending`", b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant)
        b2 = Banc(self, bin_)
        bob = b2.nouvelle("Bob écrit src/a.py sans le déclarer")
        b2.ok("start", bob)
        p2 = b2.parent_pret()
        avant = b2.board()
        for extra in (("--dry-run",), ()):
            self.assertIn(f"{bob} tourne sans write-set déclaré : la disjonction serait vide",
                          b2.refus("fournee", p2, *extra).stderr, extra)
        self.assertEqual(b2.board(), avant, "une R sans write-set a laissé écrire le board")

    def w_lot_amont_vers_r(self, bin_: Path) -> None:
        """S-01M5FDAP4N : relance après une panne à l'étape (4), le lot A `pending` dépend d'une R qui tourne
        (`depends A R`) : refus AU PRÉVOL (`deps-ready: AMONT_OUVERT`), `--dry-run` compris, board identique
        octet pour octet — jamais (4) et (5) écrites puis (6) refusée."""
        b = Banc(self, bin_)
        r = b.nouvelle("r", ["src/r.py"])
        b.ok("start", r)
        p = b.parent_pret()
        mod = charger(bin_)

        def panne(*_a, **_k):
            raise mod.BoardError("panne de banc à l'étape (4)")
        with b.en_processus(), mock.patch.object(mod, "fournee_etape_groupe", panne):
            with self.assertRaises(mod.BoardError):
                mod.fournee(str(b.d), p)
        a = b.lots(p)["A"]["id"]
        b.ok("depends", a, r, "--motif", "banc")
        avant = b.board()
        for extra in (("--dry-run",), ()):
            sortie = b.refus("fournee", p, *extra).stderr
            self.assertIn(f"refus de démarrer le lot {a} — deps-ready: AMONT_OUVERT", sortie, extra)
        self.assertEqual(b.board(), avant, "un lot derrière R a laissé écrire le board")

    # -- W15 W16 W17 ---------------------------------------------------------------
    def w_15(self, bin_: Path) -> None:
        """Dégénérée : le write-set DÉCLARÉ avant la fournée est gardé, jamais réécrit en plan seul."""
        b = Banc(self, bin_)
        p = b.parent_pret(lambda x: f"# PLAN — {x}\n\nLOTS: aucun | trop petit\n")
        b.ok("writeset", p, "src/z.py")
        self.assertIn("write-set déclaré gardé (1 chemin(s))", b.ok("fournee", p, "--dry-run").stdout)
        r = b.ok("fournee", p)
        self.assertIn("dégénérée — le parent seul (`LOTS: aucun` (trop petit), ANNONCÉ)", r.stdout)
        self.assertIn("write-set déclaré gardé (1 chemin(s))", r.stdout)
        self.assertEqual(b.tache(p)["state"], "running")
        self.assertEqual(b.tache(p)["fournee"]["lots"], [])
        self.assertEqual(b.tache(p)["writeset"], ["src/z.py"], "le write-set déclaré a été réécrit")
        self.assertEqual(b.lots(p), {})
        b2 = Banc(self, bin_)
        p2 = b2.parent_pret(lambda x: f"# PLAN — {x}\n\nAucune forme.\n")
        b2.ok("writeset", p2, "src/z.py", "src/y.py")
        self.assertIn("aucune forme de lots écrite", b2.ok("fournee", p2).stdout)
        self.assertEqual(b2.tache(p2)["writeset"], ["src/z.py", "src/y.py"], "aucune forme : write-set réécrit")

    def w_16(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        p = b.parent_pret()
        avant = b.board()
        self.assertIn("la chaîne de plan n'est pas tracée", b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant)
        b.ok("fournee", p, "--sans-chaine", "banc")
        for t in [b.tache(p)] + list(b.lots(p).values()):
            self.assertIn("[SANS CHAÎNE DE PLAN : banc]", t["stage"], t["id"])
            self.assertEqual(t.get("sans_chaine"), "banc", t["id"])

    def w_17(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("writeset", p, "src/z.py")
        x = b.nouvelle("voisin", ["src/x.py"])
        b.ok("parallel", p, x)
        avant = b.board()
        self.assertIn("write-set autre que son plan", b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant)
        b2 = Banc(self, bin_)
        p2 = b2.parent_pret()
        b2.ok("writeset", p2, "src/z.py")
        b2.ok("fournee", p2)
        self.assertEqual(b2.tache(p2)["writeset"], [PLAN])

    # -- W18 W19 W20 W21 : réserves de plan-critic, check ---------------------------
    def w_18(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("fournee", p)
        b.plan(plan_texte(p) + "révision\n")
        b.approuver(p)
        r = b.refus("fournee", p)
        self.assertIn("le plan a changé depuis la découpe", r.stderr)
        self.assertIn("tasks.py delete --force", r.stderr)

    def w_19(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("writeset", p, "src/p.py")
        b.ok("direct", p)
        self.assertIn("porte une estampille `direct`", b.refus("fournee", p).stderr)

    def w_20(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        r = b.nouvelle("à côté", ["src/r.py", "CHANGELOG.md"])
        b.ok("start", r)
        p = b.parent_pret()
        sortie = b.ok("fournee", p).stdout
        self.assertIn(f"intégration partagée avec {r}", sortie)
        self.assertIn(f"running hors fournée, préservées : {r} — ni groupées ni rétrogradées ; leur revue de clôture "
                      "reste la leur", sortie)

    def w_21(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        six = [f"docs/{n}.md" for n in "abcdef"]
        texte = plan_texte("T-00000007", lots=(("A", "dev-multi", "garde", LOT_A),
                                               ("B", "dev-multi", "cinq", six[:5]),
                                               ("C", "dev-multi", "six", [f"lib/{n}.py" for n in "abcdef"])))
        r = b.check(texte, "--parent", "T-00000007")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LOT A — dev-multi — 2 fichier(s) — route : planifiée", r.stdout)
        self.assertIn("LOT B — dev-multi — 5 fichier(s) — route : directe prédite", r.stdout)
        self.assertIn("LOT C — dev-multi — 6 fichier(s) — route : À REDÉCOUPER", r.stdout)
        r = b.check(texte, "--parent", "T-00000008")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("n'ENRÔLE pas T-00000008", r.stdout)
        # Un lot dev-mono = UN chemin (S-01M54WQE1K4VQKJ9STTJ7A1DQ2) : B en dev-mono sur cinq chemins est refusé.
        mono = texte.replace("LOT: B | dev-multi | cinq |", "LOT: B | dev-mono | cinq |")
        self.assertNotEqual(mono, texte, "fixture : la ligne du lot B doit exister")
        r = b.check(mono, "--parent", "T-00000007")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("lot B : dev-mono déclare 5 chemins", r.stdout)

    # -- W22 à W26 : passe de correction de la revue de clôture ----------------------
    def w_22(self, bin_: Path) -> None:
        """Lot B clos, plan ré-approuvé (B change de chemins) : seul A, ouvert, est refusé ;
        `delete --force` de A, relance OK ; B reste clos sous son ancien plan."""
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("fournee", p)
        avant = b.lots(p)
        b.ok("done", avant["B"]["id"], "--raison", "banc")
        lots = (("A", "dev-multi", "moteur", LOT_A), ("B", "dev-mono", "doc", LOT_B + ["docs/d.md"]))
        b.plan(plan_texte(p, lots=lots) + "révision\n")
        b.approuver(p)
        r = b.refus("fournee", p)
        self.assertNotIn(f"lot B ({avant['B']['id']})", r.stderr, "un lot clos est jugé sous le nouveau plan")
        self.assertIn(f"lot A ({avant['A']['id']})", r.stderr)
        self.assertIn("tasks.py delete --force", r.stderr)
        b.ok("delete", avant["A"]["id"], "--force")
        info = f"lot B ({avant['B']['id']}) clos sous l'ancien plan : docs/d.md sans porteur"
        r = b.ok("fournee", p, "--dry-run")
        self.assertIn(info, r.stdout, "--dry-run tait le chemin que le nouveau plan ajoute à un lot clos")
        self.assertIn("FOURNEE: lot B — dev-mono — 2 fichier(s) — existant", r.stdout, "compte du nouveau plan")
        self.assertIn(info, b.ok("fournee", p).stdout, "le lancement tait le chemin ajouté à un lot clos")
        apres, sha = b.lots(p), hashlib.sha256((b.d / PLAN).read_bytes()).hexdigest()
        self.assertNotEqual(apres["A"]["id"], avant["A"]["id"])
        self.assertEqual((apres["A"]["state"], apres["A"]["fournee"]["sha256"]), ("running", sha))
        self.assertEqual((apres["B"]["id"], apres["B"]["state"]), (avant["B"]["id"], "done"), "un lot clos a été refait")
        self.assertEqual(apres["B"]["fournee"]["sha256"], avant["B"]["fournee"]["sha256"])

    def w_23(self, bin_: Path) -> None:
        """X et Y tournent groupées, Y dépend de X : elles ne sont plus membres de la fournée, leur lien ne la
        regarde pas — `--dry-run` rc 0 sans rien écrire, lancement rc 0, X et Y gardent leur groupe."""
        b = Banc(self, bin_)
        x, y = b.nouvelle("x", ["src/x.py"]), b.nouvelle("y", ["src/y.py"])
        b.ok("parallel", x, y)
        b.ok("start", x)
        b.ok("start", y)
        b.ok("depends", y, x, "--motif", "banc")
        groupe = b.tache(x)["parallel_group"]
        p = b.parent_pret()
        avant = b.racine()
        self.assertNotIn("sont liés", b.ok("fournee", p, "--dry-run").stdout)
        self.assertEqual(b.racine(), avant, "un --dry-run a écrit")
        b.ok("fournee", p)
        self.assertEqual({b.tache(x)["parallel_group"], b.tache(y)["parallel_group"]}, {groupe})
        self.assertNotEqual(b.tache(p)["parallel_group"], groupe)

    def w_24(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        p = b.nouvelle("parent")
        (b.d / PLAN).parent.mkdir(parents=True, exist_ok=True)
        (b.d / PLAN).write_bytes(plan_texte(p).replace("—", "-").replace("faire", "réviser").encode("latin-1"))
        b.approuver(p)
        avant = b.board()
        for extra in ((), ("--dry-run",)):
            self.assertIn(f"plan {PLAN} : n'est pas en UTF-8", b.refus("fournee", p, *extra).stderr, extra)
        self.assertEqual(b.board(), avant)

    def w_25(self, bin_: Path) -> None:
        """Un plan élu HORS de la racine résolue : refus nommé, jamais un `ValueError`."""
        b = Banc(self, bin_)
        p = b.nouvelle("parent")
        dehors = Path(tempfile.mkdtemp(prefix="fournee-dehors-"))
        self.addCleanup(shutil.rmtree, dehors, True)
        (dehors / "plan.md").write_text(plan_texte(p), encoding="utf-8")
        mod = charger(bin_)
        with b.en_processus(), mock.patch.object(mod.plan_cible_module(), "trace_plan_approuve",
                                                 return_value=(dehors / "plan.md", "S-00000001")):
            try:
                prevol = mod.fournee_prevol(str(b.d), p, mod.load(str(b.d)))
            except ValueError as exc:
                self.fail(f"un plan hors racine lève au lieu de refuser : {exc}")
        self.assertTrue(any("hors de la racine" in r for r in prevol["refus"]), prevol["refus"])

    def w_26(self, bin_: Path) -> None:
        """Un lot écrit avec `\\` : premier lancement OK, relance OK (comparé à la forme stockée)."""
        b = Banc(self, bin_)
        lots = (("A", "dev-multi", "moteur", ["src\\a.py", "src/b.py"]), ("B", "dev-mono", "doc", LOT_B))
        p = b.parent_pret(lambda x: plan_texte(x, lots=lots))
        b.ok("fournee", p)
        self.assertEqual(b.lots(p)["A"]["writeset"], ["src/a.py", "src/b.py"])
        b.ok("fournee", p)

    # -- W27 à W29 : deuxième passe de correction ------------------------------------
    def w_27(self, bin_: Path) -> None:
        """Un lot qui déclare le chemin du plan (write-set du parent) : refusé au prévol, rien d'écrit."""
        b = Banc(self, bin_)
        lots = (("A", "dev-multi", "moteur", LOT_A), ("B", "dev-mono", "doc", ["docs/b.md", PLAN]))
        p = b.parent_pret(lambda x: plan_texte(x, lots=lots))
        avant = b.racine()
        r = b.refus("fournee", p, "--dry-run")
        self.assertIn(f"le lot B déclare `{PLAN}`, qui recouvre le plan `{PLAN}`", r.stderr)
        self.assertEqual(b.racine(), avant, "un --dry-run refusé a écrit")
        avant = b.board()
        self.assertIn("qui recouvre le plan", b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant, "un refus a écrit le board")

    def w_28(self, bin_: Path) -> None:
        """L'UNION : un `depends` lot/lot ou parent/lot, posé par la CLI AVANT que le groupe existe
        (panne à l'étape 4, comme W7), refusé au prévol, rien d'écrit."""
        mod = charger(bin_)

        def panne(*_a, **_k):
            raise mod.BoardError("panne de banc à l'étape (4)")
        for avant_, apres_ in (("B", "A"), ("parent", "A")):
            b = Banc(self, bin_)
            p = b.parent_pret()
            with b.en_processus(), mock.patch.object(mod, "fournee_etape_groupe", panne):
                with self.assertRaises(mod.BoardError):
                    mod.fournee(str(b.d), p)
            lots = b.lots(p)
            self.assertFalse(any(t.get("parallel_group") for t in [b.tache(p)] + list(lots.values())),
                             "la panne a laissé un groupe : le lien serait posé APRÈS lui")
            ids = {"parent": p, "A": lots["A"]["id"], "B": lots["B"]["id"]}
            b.ok("depends", ids[avant_], ids[apres_], "--motif", "banc")
            avant = b.racine()
            r = b.refus("fournee", p, "--dry-run")
            liees = [ligne for ligne in r.stderr.splitlines() if "sont liés (`depends_on` ou `blocked_on`)" in ligne]
            self.assertTrue(any(ids[avant_] in ligne and ids[apres_] in ligne for ligne in liees), r.stderr)
            self.assertEqual(b.racine(), avant, (avant_, apres_))
            board = b.board()
            b.refus("fournee", p)
            self.assertEqual(b.board(), board, (avant_, apres_))

    def w_29(self, bin_: Path) -> None:
        """Garde de mesure armée, libellés ouverts par « fix » : le titre d'un lot ouvre sur « Lot »,
        jamais sur le lexique d'un défaut — le `pas_un_defaut` hérité ou généré passe."""
        for extra in ((), ("--pas-un-defaut", "une fonctionnalité")):
            b = Banc(self, bin_)
            lots = (("A", "dev-multi", "fix du moteur", LOT_A), ("B", "dev-mono", "fix de la doc", LOT_B))
            p = b.parent_pret(lambda x: plan_texte(x, lots=lots), *extra)
            b.armer("MESURE_REQUIRED")
            b.ok("fournee", p)
            for cle, lot in b.lots(p).items():
                self.assertEqual(lot["task"], f"Lot {cle} de {p} : " + dict((k, lib) for k, _d, lib, _c in lots)[cle])
                self.assertTrue(lot.get("pas_un_defaut"), (cle, extra))

    # -- W30 W31 : troisième passe -----------------------------------------------------
    def w_30(self, bin_: Path) -> None:
        """Un lien d'une tâche de R, ou du PARENT, vers un lot CLOS ne refuse rien : le lot clos n'est pas membre."""
        b = Banc(self, bin_)
        x = b.nouvelle("x", ["src/x.py"])
        b.ok("start", x)
        p = b.parent_pret()
        b.ok("fournee", p)
        avant = b.lots(p)
        b.ok("done", avant["B"]["id"], "--raison", "banc")
        b.ok("depends", x, avant["B"]["id"], "--motif", "banc")
        b.ok("depends", p, avant["B"]["id"], "--motif", "banc")
        b.ok("delete", avant["A"]["id"], "--force")
        b.plan(plan_texte(p) + "révision\n")
        b.approuver(p)
        b.ok("fournee", p, "--dry-run")
        b.ok("fournee", p)
        apres = b.lots(p)
        groupe = {b.tache(p).get("parallel_group"), apres["A"].get("parallel_group")}
        self.assertEqual(len(groupe), 1, groupe)
        self.assertNotIn(None, groupe)
        self.assertEqual((b.tache(x)["state"], b.tache(x).get("parallel_group")), ("running", None), "R embarquée")
        self.assertNotEqual(apres["A"]["id"], avant["A"]["id"])
        self.assertEqual((apres["B"]["id"], apres["B"]["state"]), (avant["B"]["id"], "done"))

    def w_31(self, bin_: Path) -> None:
        """Relance déjà groupée : un `block B --on A` posé après le lancement ne la refuse pas, B reste bloqué."""
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("fournee", p)
        lots = b.lots(p)
        b.ok("block", lots["B"]["id"], "--on", lots["A"]["id"])
        r = b.ok("fournee", p)
        self.assertIn(f"lot B ({lots['B']['id']}) est `blocked` — non démarré", r.stdout)
        apres = b.tache(lots["B"]["id"])
        self.assertEqual((apres["state"], apres.get("blocked_on")), ("blocked", lots["A"]["id"]), "l'attente est perdue")

    # -- W32 à W35 : fournée dégénérée — write-set réel exigé, gardé, seul juge ----------
    def w_32(self, bin_: Path) -> None:
        """Dégénérée sans chemin hors de son plan — aucun write-set, le plan seul, le plan dans une
        autre casse (C6) : refus FIGÉ, remède et C9 compris, `--dry-run` aussi, board identique (C2) ;
        un chemin réel à côté du plan passe et reste déclaré."""
        b = Banc(self, bin_)
        p = b.parent_pret(DEGENEREE.format)
        refus = (f"{p} : fournée dégénérée sans write-set réel — aucun chemin déclaré hors de son plan `{PLAN}` : "
                 f"la disjonction serait prouvée à vide. Remède : `tasks.py writeset {p} <chemins…>` AVANT la "
                 "fournée (groupe clos d'abord s'il en a un : `block`/`done` de ses co-membres), puis relance ; un "
                 "plan qui n'a rien à écrire hors de lui-même n'appelle pas de fournée")
        for ws in ((), (PLAN,), ("Docs/Tasks/PLAN.md",)):
            if ws:
                b.ok("writeset", p, *ws)
            avant = b.board()
            for extra in (("--dry-run",), ()):
                self.assertIn(refus, b.refus("fournee", p, *extra).stderr, (ws, extra))
            self.assertEqual(b.board(), avant, f"{ws} : un refus de dégénérée a écrit le board")
        b.ok("writeset", p, PLAN, "src/z.py")
        b.ok("fournee", p)
        self.assertEqual((b.tache(p)["state"], b.tache(p)["writeset"]), ("running", [PLAN, "src/z.py"]))

    def w_33(self, bin_: Path) -> None:
        """R `src/z.py` contre un parent dégénéré qui déclare `src/z.py` : refusé AU PRÉVOL, le write-set
        du parent nommé, board identique (C2) ; deux dégénérées à write-sets DISJOINTS tournent côte à côte,
        chacune hors de tout groupe — la première n'est plus embarquée par la seconde (C3, lot B)."""
        b = Banc(self, bin_)
        r = b.nouvelle("recouvre", ["src/z.py"])
        b.ok("start", r)
        p = b.parent_pret(DEGENEREE.format)
        b.ok("writeset", p, "src/z.py")
        avant = b.board()
        self.assertIn(f"{r} (`src/z.py`) recouvre le write-set de {p} (`src/z.py`) : la fournée ne tourne pas",
                      b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant, "un recouvrement R / parent dégénéré a écrit le board")
        b2 = Banc(self, bin_)
        p1 = b2.parent_pret(DEGENEREE.format)
        b2.ok("writeset", p1, "src/a.py")
        b2.ok("fournee", p1)
        p2, plan2 = b2.nouvelle("second parent"), "docs/tasks/plan2.md"
        b2.plan(DEGENEREE.format(p2), rel=plan2)
        b2.approuver(p2, rel=plan2)
        b2.ok("writeset", p2, "src/b.py")
        b2.ok("fournee", p2)
        t1, t2 = b2.tache(p1), b2.tache(p2)
        self.assertEqual((t1["state"], t2["state"]), ("running", "running"))
        self.assertEqual((t1.get("parallel_group"), t2.get("parallel_group")), (None, None), "une dégénérée embarquée")
        self.assertEqual((t1["writeset"], t2["writeset"]), (["src/a.py"], ["src/b.py"]))

    def w_34(self, bin_: Path) -> None:
        """Un board abîmé par l'ancien code — une `running` de R, parent dégénéré réduit à son plan — :
        plus groupée avec la fournée, elle est DITE (disjonction jugée sur son seul plan, remède nommé),
        jamais un refus ; sans groupe, puis GROUPÉE par le pilote : R garde état, write-set et groupe."""
        info = ("{} tourne comme parent d'une fournée dégénérée réduit à son plan `{}` : disjonction jugée sur ce "
                "seul plan — `tasks.py writeset {} <chemins…>` pour qu'elle le soit sur ses vrais chemins")
        for groupee in (False, True):
            b = Banc(self, bin_)
            p0, plan0 = b.nouvelle("parent abîmé"), "docs/tasks/plan0.md"
            b.plan(DEGENEREE.format(p0), rel=plan0)
            b.approuver(p0, rel=plan0)
            b.ok("writeset", p0, "src/q.py")
            b.ok("fournee", p0)
            # Le contrat écrivain/lecteur : l'étape (1) — inchangée depuis la naissance du verbe —
            # écrit `lots: []` sur le parent d'une dégénérée ; c'est la forme que la détection lit.
            self.assertEqual(b.tache(p0)["fournee"].get("lots"), [], "lien de dégénérée sans `lots: []`")
            if groupee:
                r = b.nouvelle("à côté", ["src/r.py"])
                b.ok("start", r)
                b.ok("parallel", p0, r)
            b.abimer(p0, writeset=[plan0])  # l'écrasement de l'ancien code, à la main (groupe gardé)
            avant = b.tache(p0)
            p = b.parent_pret()
            self.assertIn(info.format(p0, plan0, p0), b.ok("fournee", p).stdout, groupee)
            apres = b.tache(p0)
            self.assertEqual([apres.get(k) for k in ("state", "writeset", "parallel_group")],
                             [avant.get(k) for k in ("state", "writeset", "parallel_group")], groupee)
            self.assertEqual(bool(apres.get("parallel_group")), groupee, "le banc ne construit pas le cas voulu")
            self.assertNotEqual(b.tache(p).get("parallel_group"), apres.get("parallel_group"), "R embarquée")

    def w_35(self, bin_: Path) -> None:
        """Relance d'une dégénérée GROUPÉE (par le pilote, avec une running disjointe) : rc 0, groupe et
        write-set déclaré gardés, la voisine aussi."""
        b = Banc(self, bin_)
        r = b.nouvelle("à côté", ["src/r.py"])
        b.ok("start", r)
        p = b.parent_pret(DEGENEREE.format)
        b.ok("writeset", p, "src/z.py")
        b.ok("parallel", p, r)
        b.ok("fournee", p)
        groupe = b.tache(p).get("parallel_group")
        self.assertTrue(groupe, "la fournée a défait le groupe que le pilote a déclaré")
        b.ok("fournee", p)
        apres, voisin = b.tache(p), b.tache(r)
        self.assertEqual((apres["state"], apres.get("parallel_group"), apres["writeset"]),
                         ("running", groupe, ["src/z.py"]))
        self.assertEqual((voisin["state"], voisin.get("parallel_group")), ("running", groupe))

    # -- W36 et W37 : passe de correction du lot A (exec-critic, sécurité) ----------------
    def w_36(self, bin_: Path) -> None:
        """Un parent À LOTS qui tourne (R) — write-set réduit à son plan PAR CONSTRUCTION — n'est pas
        une dégénérée abîmée : une seconde fournée disjointe passe, rc 0, les six tournent, un groupe PAR
        fournée (la première n'est plus embarquée), et rien n'est DIT « réduit à son plan »."""
        b = Banc(self, bin_)
        p1 = b.parent_pret()
        b.ok("fournee", p1)
        self.assertEqual(b.tache(p1)["writeset"], [PLAN])
        p2, plan2 = b.nouvelle("second parent"), "docs/tasks/plan2.md"
        lots2 = (("C", "dev-mono", "code", ["src/c.py"]), ("D", "dev-mono", "doc", ["docs/d.md"]))
        b.plan(plan_texte(p2, lots=lots2), rel=plan2)
        b.approuver(p2, rel=plan2)
        self.assertNotIn("réduit à son plan", b.ok("fournee", p2).stdout, "un parent à lots pris pour une dégénérée")
        un, deux = [b.tache(p1)] + list(b.lots(p1).values()), [b.tache(p2)] + list(b.lots(p2).values())
        self.assertEqual(len(un + deux), 6)
        self.assertEqual({t["state"] for t in un + deux}, {"running"})
        self.assertEqual([len({t.get("parallel_group") for t in g}) for g in (un, deux)], [1, 1])
        self.assertNotEqual(un[0].get("parallel_group"), deux[0].get("parallel_group"), "la première embarquée")

    def w_37(self, bin_: Path) -> None:
        """Un chemin INADMISSIBLE écrit à la main au write-set d'une dégénérée (`./` vers le plan, `..`,
        une traversée vers le plan, ou à côté d'un chemin réel) n'est jamais « hors du plan » : refus
        nommant le chemin et son diagnostic, `--dry-run` compris, board identique."""
        for ws in (["./docs/tasks/plan.md"], [".."], ["src/../docs/tasks/plan.md"], ["src/z.py", "../hors.py"]):
            b = Banc(self, bin_)
            p = b.parent_pret(DEGENEREE.format)
            b.ok("writeset", p, "src/z.py")
            b.abimer(p, writeset=ws)
            avant = b.board()
            for extra in (("--dry-run",), ()):
                r = b.refus("fournee", p, *extra)
                self.assertIn(f"{p} : fournée dégénérée dont le write-set porte `{ws[-1]}`, chemin inadmissible — "
                              f"jamais compté hors de son plan. Remède : `tasks.py writeset {p} <chemins…>` AVANT la "
                              "fournée (groupe clos d'abord s'il en a un : `block`/`done` de ses co-membres), puis "
                              f"relance. Diagnostic : {ws[-1]!r} is not an admissible writeset path", r.stderr, (ws, extra))
            self.assertEqual(b.board(), avant, f"{ws} : un write-set inadmissible a laissé écrire le board")

    # -- W38 : revue de clôture du lot A, F1 — le plan d'une dégénérée reste dans la disjonction --
    def w_38(self, bin_: Path) -> None:
        """Le plan d'une dégénérée est AJOUTÉ à son write-set déclaré, jamais substitué. (1) Une R qui
        tourne sur le plan d'un parent dégénéré qui déclare `src/z.py` : refus « recouvre le plan de »,
        board identique. (2) Une R dégénérée qui tourne porte son plan dans son write-set comparé : une
        nouvelle dégénérée qui déclare ce plan est refusée, board identique."""
        b = Banc(self, bin_)
        r = b.nouvelle("tient le plan", [PLAN])
        b.ok("start", r)
        p = b.parent_pret(DEGENEREE.format)
        b.ok("writeset", p, "src/z.py")
        avant = b.board()
        self.assertIn(f"{r} (`{PLAN}`) recouvre le plan de {p} (`{PLAN}`) : la fournée ne tourne pas",
                      b.refus("fournee", p).stderr)
        self.assertEqual(b.board(), avant, "une R sur le plan d'une dégénérée a laissé écrire le board")
        b2 = Banc(self, bin_)
        p1 = b2.parent_pret(DEGENEREE.format)
        b2.ok("writeset", p1, "src/a.py")
        b2.ok("fournee", p1)
        p2, plan2 = b2.nouvelle("second parent"), "docs/tasks/plan2.md"
        b2.plan(DEGENEREE.format(p2), rel=plan2)
        b2.approuver(p2, rel=plan2)
        b2.ok("writeset", p2, PLAN, "src/b.py")
        avant = b2.board()
        self.assertIn(f"{p1} (`{PLAN}`) recouvre le write-set de {p2} (`{PLAN}`) : la fournée ne tourne pas",
                      b2.refus("fournee", p2).stderr)
        self.assertEqual(b2.board(), avant, "le plan d'une R dégénérée déclaré par la fournée : board écrit")


#: Les mutants : `nom → ({fichier: [(ancre, remplacement)]}, témoin)`.
_ETATS, _FOURNEE, _LOTS = "tasks_etats.py", "tasks_fournee.py", "plan_lots.py"
MUTANTS = {
    "recouvrement non contrôlé": ({_LOTS: [("            paire = chevauche(un.chemins, autre.chemins)\n",
                                            "            paire = None\n")]}, "w_02"),
    "sha non recalculé": ({"plan_cible.py": [("    if hashlib.sha256(chemin.read_bytes()).hexdigest() != empreinte:\n"
                                              "        return None\n", "")]}, "w_05"),
    "consommation par lot": ({_ETATS: [("                and not emprunt_groupe\n", "")]}, "w_06"),
    "règle B sans exemption des membres": ({_FOURNEE: [(
        '            if (parallel_group_of(t) == g and t["id"] not in membres\n',
        "            if (parallel_group_of(t) == g\n")]}, "w_07r"),
    "R non contrôlé (recouvrement)": ({_FOURNEE: [("            paire = writeset_paths_overlap(ws, chemins)\n",
                                                   "            paire = None\n")]}, "w_08"),
    "R embarquée dans le groupe (lot B)": ({_FOURNEE: [(
        '    return [p["parent"]["id"]] + lots\n',
        '    return [t["id"] for t in p["R"]] + [p["parent"]["id"]] + lots\n')]}, "w_external_running_not_embarked"),
    "R embarquée (W8b)": ({_FOURNEE: [(
        '    return [p["parent"]["id"]] + lots\n',
        '    return [t["id"] for t in p["R"]] + [p["parent"]["id"]] + lots\n')]}, "w_08b"),
    "R tue": ({_FOURNEE: [("    if r_taches:\n", "    if False:\n")]}, "w_external_running_not_embarked"),
    "`parallel` sans recouvrement": ({"tasks_graphe.py": [(
        "                clash = writeset_paths_overlap(writeset_of(one), writeset_of(other))\n",
        "                clash = None\n")]}, "w_parallel_refuses_overlap"),
    "R sans write-set admise": ({_FOURNEE: [("            refus.append(FOURNEE_REFUS_R_SANS_WS.format(rid=t[\"id\"]))\n",
                                             "            pass\n")]}, "w_14b"),
    "amont des lots non relevé": ({_FOURNEE: [('        if t["state"] == "pending" and not sans_dependances:\n',
                                               "        if False:\n")]}, "w_lot_amont_vers_r"),
    # Même état, même stage, même groupe : seuls `updated`, l'acteur et un intent changent — l'angle mort fermé.
    "R re-stagée à l'identique": ({_FOURNEE: [(
        '    if find(load(root), tid)["state"] == "running" and not (preuves or {}).get(tid):\n',
        '    for t in [t for t in p["R"] if t.get("stage")]:\n        stage_task(root, t["id"], t["stage"])\n'
        '    if find(load(root), tid)["state"] == "running" and not (preuves or {}).get(tid):\n')]},
        "w_external_running_not_embarked"),
    # M7 : un intent de R sans réécriture du record — l'outbox vidé à la sauvegarde le cache, le store V3 le voit.
    "intent de R vidé de l'outbox (M7)": ({_FOURNEE: [(
        '        enqueue_sync_intent(data, parent["id"], before, task)\n',
        '        enqueue_sync_intent(data, parent["id"], before, task)\n'
        '        for r in p["R"]:\n            enqueue_sync_intent(data, r["id"], find(data, r["id"]), find(data, r["id"]))\n')]},
        "w_external_running_not_embarked"),
    "dry-run écrit": ({_FOURNEE: [("    if dry_run:\n", "    if False:\n")]}, "w_09"),
    "dry-run dans `mutating` (pont V3 rejoué)": ({"tasks.py": [(
        '            and not (args.cmd == "fournee" and args.dry_run)', "            and True")]}, "w_09"),
    "G3 retirée": ({"tasks_direct.py": [('    ".agents/bin/plan_lots.py",\n', "")]}, "w_13"),
    "porteurs[0] restauré": ({_ETATS: [(
        '                    emprunt_groupe = lien_lot.get("parent") if lien_lot.get("parent") in porteurs else porteurs[0]\n',
        "                    emprunt_groupe = porteurs[0]\n")]}, "w_14"),
    "le parent emprunte": ({_ETATS: [('                if porteurs and "lots" not in lien_lot:\n',
                                      "                if porteurs:\n")]}, "w_14"),
    "R = running seules, sans la règle B": ({_FOURNEE: [(
        '                    and t["state"] not in ("running", "done")):\n',
        "                    and False):\n")]}, "w_14b"),
    "C1.2 sha des lots non comparé": ({_FOURNEE: [(
        '        if str(t["fournee"].get("sha256") or "").lower() != sha:\n', "        if False:\n")]}, "w_18"),
    "C1.3 estampille du parent admise": ({_FOURNEE: [('    if "direct" in parent:\n', "    if False:\n")]}, "w_19"),
    "C3 intégration partagée tue": ({_FOURNEE: [("    if partagee:\n", "    if False:\n")]}, "w_20"),
    "dry-run refusé rend 0": ({_FOURNEE: [("            raise BoardError(fournee_rendu(tid, p, dry_run=True))\n",
                                           "            pass\n")]}, "w_05"),
    "consommation par lot (relance)": ({_ETATS: [("                and not emprunt_groupe\n", "")]}, "w_07"),
    "parent sans motif : lots refusés": ({_FOURNEE: [(
        "            or f\"lot {cle} du plan {sha[:12]} de {parent['id']} (antérieur à la garde de mesure)\"}\n",
        "            or None}\n")]}, "w_11"),
    "F1 lot clos jugé sur son sha": ({_FOURNEE: [(
        "            continue  # un lot CLOS reste clos sous son ancien plan : sauté, jamais refait\n",
        "            pass\n")]}, "w_22"),
    "F1 lot clos jugé sur son write-set": ({_FOURNEE: [(
        '        if t["state"] == "done" or lot is None or not writeset_of(t):\n',
        "        if lot is None or not writeset_of(t):\n")]}, "w_22"),
    "F3 union : liens non comparés": ({_FOURNEE: [("            if lies:\n", "            if False:\n")]}, "w_28"),
    "F3 R reliées refusent (lot B)": ({_FOURNEE: [("    unis = [parent] + ouverts\n",
                                                    "    unis = r_taches + [parent] + ouverts\n")]}, "w_23"),
    "F4 plan non UTF-8 en traceback": ({_FOURNEE: [(
        '    try:\n        texte = octets.decode("utf-8")\n    except UnicodeDecodeError:\n',
        '    if True:\n        texte = octets.decode("utf-8")\n    if False:\n')]}, "w_24"),
    "racine résolue : ValueError non attrapée": ({_FOURNEE: [(
        "    except (OSError, ValueError):\n        refus.append(f\"plan {chemin} :",
        "    except OSError:\n        refus.append(f\"plan {chemin} :")]}, "w_25"),
    "write-set comparé brut": ({_FOURNEE: [("        if writeset_of(t) != voulu:\n",
                                            "        if writeset_of(t) != lot.chemins:\n")]}, "w_26"),
    "N2 chemin ajouté à un lot clos tu": ({_FOURNEE: [("            if orphelins:\n", "            if False:\n")]}, "w_22"),
    "N2 lot clos compté sur le nouveau plan": ({_FOURNEE: [(
        '        n = len(writeset_of(t)) if t is not None and t["state"] == "done" else len(lot.chemins)\n',
        "        n = len(lot.chemins)\n")]}, "w_22"),
    "N1 lot sur le chemin du plan admis": ({_FOURNEE: [(
        "        paire_plan = None if clos else writeset_paths_overlap([rel], lot.chemins)\n",
        "        paire_plan = None\n")]}, "w_27"),
    "N3 union vidée": ({_FOURNEE: [("    unis = [parent] + ouverts\n", "    unis = []\n")]}, "w_28"),
    "titre de lot ouvert par son libellé": ({_FOURNEE: [(
        '    return f"Lot {lot.cle} de {parent_id} : {lot.libelle}"\n',
        '    return f"{lot.libelle} — lot {lot.cle} de {parent_id}"\n')]}, "w_29"),
    "lot clos membre de l'union": ({_FOURNEE: [(
        '    ouverts = [t for _c, t in sorted(existants.items()) if t["state"] != "done"]\n',
        "    ouverts = [t for _c, t in sorted(existants.items()) if True]\n")]}, "w_30"),
    "relance groupée rejugée": ({_FOURNEE: [(
        "    for i, t in enumerate([] if deja else unis):\n", "    for i, t in enumerate(unis):\n")]}, "w_31"),
    "refus dégénéré retiré": ({_FOURNEE: [(
        "    if decoupe.degeneree and not inadmissibles and fournee_reduit_au_plan(ws_parent, rel):\n",
        "    if False:\n")]}, "w_32"),
    "plan compté comme chemin réel": ({_FOURNEE: [(
        "    return all(canonical_writeset_path(c) == canon for c in ws)\n", "    return not ws\n")]}, "w_32"),
    "comparaison brute (casse non repliée)": ({_FOURNEE: [(
        "    return all(canonical_writeset_path(c) == canon for c in ws)\n",
        "    return all(c == plan for c in ws)\n")]}, "w_32"),
    "étape (2) inconditionnelle": ({_FOURNEE: [(
        '    if not p["decoupe"].degeneree and writeset_of(find(data, p["parent"]["id"])) != [p["plan"]]:\n',
        '    if writeset_of(find(data, p["parent"]["id"])) != [p["plan"]]:\n')]}, "w_15"),
    "entête muette sur le write-set gardé": ({_FOURNEE: [(
        ", write-set déclaré gardé ({n} chemin(s))\"\n", "\"\n")]}, "w_15"),
    "ensembles = [rel]": ({_FOURNEE: [(
        '    porteur = (f"le write-set de {tid}", ws_parent) if decoupe.degeneree else (f"le plan de {tid}", [rel])\n',
        '    porteur = (f"le plan de {tid}", [rel])\n')]}, "w_33"),
    "R plan-seul non dite": ({_FOURNEE: [(
        '        if (ws and lien_r.get("lots") == [] and isinstance(lien_r.get("plan"), str)\n',
        '        if (False and isinstance(lien_r.get("plan"), str)\n')]}, "w_34"),
    "garde :228 sur [rel]": ({_FOURNEE: [("    if ws_parent and ws_parent != voulu_parent and groupe:\n",
                                          "    if ws_parent and ws_parent != [rel] and groupe:\n")]}, "w_35"),
    "M1 parent à lots pris pour une dégénérée": ({_FOURNEE: [(
        '        if (ws and lien_r.get("lots") == [] and isinstance(lien_r.get("plan"), str)\n',
        '        if (ws and lien_r.get("lots") is not None and isinstance(lien_r.get("plan"), str)\n')]}, "w_36"),
    "chemin inadmissible compté hors du plan": ({_FOURNEE: [(
        "    inadmissibles = [c for c in ws_parent if writeset_path_refusal(c) is not None] if decoupe.degeneree else []\n",
        "    inadmissibles = []\n")]}, "w_37"),
    "lien de dégénérée sans `lots`": ({_FOURNEE: [(
        '    voulu = {"lots": ids, "plan": p["plan"], "sha256": p["sha"], "trace": p["trace"]}\n',
        '    voulu = {**({"lots": ids} if ids else {}), "plan": p["plan"], "sha256": p["sha"], "trace": p["trace"]}\n')]},
        "w_34"),
    "plan retiré des ensembles": ({_FOURNEE: [(
        '    ensembles = ([porteur] + ([(f"le plan de {tid}", [rel])] if decoupe.degeneree else [])\n',
        "    ensembles = ([porteur]\n")]}, "w_38"),
    "plan de R non ajouté": ({_FOURNEE: [('            ws = [*ws, lien_r["plan"]]\n', "            pass\n")]}, "w_38"),
}


class FourneeTests(Temoins, unittest.TestCase):
    """Les témoins sur le VRAI `bin`."""


for _nom in [n for n in dir(Temoins) if n.startswith("w_")]:
    setattr(FourneeTests, "test_" + _nom[2:], (lambda nom: lambda self: getattr(self, nom)(BIN))(_nom))


class FourneeMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant ROUGIT son témoin, par une assertion."""


def _test_mutant(nom: str, mutations: dict, temoin: str):
    def test(self: FourneeMutantsTests) -> None:
        bin_ = copie(self, mutations)
        with self.assertRaises(AssertionError, msg=f"le mutant « {nom} » SURVIT à {temoin}"):
            getattr(self, temoin)(bin_)
    return test


for _i, (_nom, (_mutations, _temoin)) in enumerate(MUTANTS.items()):
    setattr(FourneeMutantsTests, f"test_mutant_{_i:02d}_{_temoin}", _test_mutant(_nom, _mutations, _temoin))


if __name__ == "__main__":
    unittest.main()
