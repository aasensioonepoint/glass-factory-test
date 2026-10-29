"""LES LIMITES PAR TÂCHE — `limite`, `conso`, `depassements`, la tête de session, l'arrêt armé.

T-01M54GEMCH3JWA95G61N2J70KS (E-48 C4, décision pilote S-01M54GFZ2VCYVA8RSJYBV6539H), annexe § 3,
témoins L1-L10, plus les réserves C8 (la note de blocage garde l'étape d'avant) et C9 (la ligne
`LIMITE-DEPASSEE:` sort aussi à `stage` et à `fournee`), et la passe de correction d'exec-critic
(S-01M5AZ4B5V1AV96J9RFYH712H9) : L12 lot existant dépassé à la fournée, L13 marqueur en lien
pendant ou en boucle et dossier illisible, L14 jugement qui lève sous l'arrêt ; puis la passe
d'intégration (S-01M5BY5P367BQ9V5PFYCPRP5HV) : L15 tête F8, cumul déjà au-delà, `--dry-run` refusé,
milliers en entiers. ZÉRO APPEL LLM.

Chaque témoin `l_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`, ou une COPIE
JETABLE dont un fragment littéral, présent UNE fois (asserté), est remplacé. Chaque mutant de
`MUTANTS` rejoue le SEUL témoin qui le tue, et doit le faire échouer par une ASSERTION. Racine,
HOME, `CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR` jetables ; `CLAUDE_PROJECT_DIR`, `CLAUDE_PID` et
`GIT_*` retirés des sous-processus. L'HORLOGE est injectée dans les appels EN PROCESSUS
(`depassements(data, maintenant)`) ; en sous-processus, aucun réglage d'horloge n'existe (une
variable d'environnement le permettrait à un agent aussi) : les échéances y sont des instants
absolus, passés (2000) ou futurs (2999), et `--delai` est borné par deux lectures de l'horloge.

BORNE : ce banc prouve que l'appel de `conso` est ÉCRIT dans les surfaces d'orchestration
(`test_doctrine_conso_cablee`), jamais que l'orchestrateur le joue ; ni la découverte du marqueur
par un adoptant. Avant les mutants, un CONTRÔLE joue chaque témoin sur une copie NON mutée : une
copie cassée rendrait tous les mutants « tués ».
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
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "plan_lots.py", "specs.py",
          "events.py", "record_id.py", "kickoff_guard.py", "vendor_paths.py")
PASSEE = "2000-01-01T00:00Z"
FUTURE = "2999-01-01T00:00Z"
REFUS = "dépasse sa limite et LIMITE_ARRET est armé"
CLES_JSON = ["tache", "type", "valeur", "limite", "etat", "arret"]


def copie(case: unittest.TestCase, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable du vrai `bin`, chaque ancre remplacée UNE fois ; `.agents/vendor` lié."""
    base = Path(tempfile.mkdtemp(prefix="limites-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in BIN.glob(motif):
            if not f.name.startswith("test_"):
                shutil.copy2(f, dest / f.name)
    (base / ".agents" / "vendor").symlink_to(ROOT / ".agents" / "vendor", target_is_directory=True)
    for nom, paires in mutations.items():
        cible = dest / nom
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            case.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente dans {nom} : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
    return dest


def charger(bin_: Path):
    """Le module `tasks` de `bin_`, chargé sous un nom unique, pour les appels EN PROCESSUS."""
    nom = f"tasks_limites_banc_{hashlib.sha256(str(bin_).encode()).hexdigest()[:12]}"
    if nom not in sys.modules:
        spec = importlib.util.spec_from_file_location(nom, bin_ / "tasks.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        spec.loader.exec_module(module)
    return sys.modules[nom]


class Banc:
    """Une racine jetable et la CLI de `bin_` braquée dessus."""

    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin = case, bin_
        self.d = Path(tempfile.mkdtemp(prefix="limites-"))
        case.addCleanup(shutil.rmtree, self.d, True)
        etat = Path(tempfile.mkdtemp(prefix="limites-etat-"))
        case.addCleanup(shutil.rmtree, etat, True)
        maison = etat / "home"
        maison.mkdir()
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@exemple.invalid\n",
                                           encoding="utf-8")
        for sous in ("board", "gates", "local/plan", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PID") and not k.startswith("GIT_")}
        self.env.update(HOME=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                        CADRE_STATE_DIR=str(etat / "cadre"), AGENTS_EVENTS_DIR=str(etat / "events"))

    def t(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=180, env=self.env)

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 0, f"{args} : {r.stdout}{r.stderr}")
        self.case.assertNotIn("Traceback", r.stderr)
        return r

    def refus(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 2, f"{args} aurait dû être refusé : {r.stdout}{r.stderr}")
        self.case.assertNotIn("Traceback", r.stderr)
        return r

    def nouvelle(self, titre: str = "tâche de banc") -> str:
        r = self.ok("new", titre, "--pas-un-defaut", "banc des limites")
        return re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M).group(1)

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def store(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    def board(self) -> bytes:
        return self.store().read_bytes()

    def racine(self) -> dict[str, bytes]:
        """Les fichiers des dossiers d'état qu'une fournée écrit (board et ses enregistrements, vue,
        journal de chaîne, sessions, SPECS), lus dossier par dossier, SANS parcours récursif de l'arbre."""
        etat = self.d / ".agents" / "state"
        dossiers = (etat / "board", etat / "board" / "tasks", etat / "local", etat / "local" / "plan",
                    etat / "local" / "sessions", etat / "specs", etat / "gates")
        return {str(p.relative_to(self.d)): p.read_bytes()
                for d in dossiers if d.is_dir() for p in sorted(d.iterdir()) if p.is_file()}

    def armer(self) -> None:
        (self.d / ".agents" / "state" / "gates" / "LIMITE_ARRET").write_text("", encoding="utf-8")

    def abimer(self, tid: str, **champs) -> None:
        """Écrit `champs` sur `tid` À LA MAIN dans `TASKS.json` (une édition qu'aucun verbe ne produit)."""
        data = json.loads(self.store().read_text(encoding="utf-8"))
        (tache,) = [t for t in data["tasks"] if t["id"] == tid]
        tache.update(champs)
        self.store().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def parent_pret(self) -> str:
        """Un parent, son plan à deux lots écrit et approuvé (trace `plan approuvé` au journal)."""
        p = self.nouvelle("parent de banc")
        rel = "docs/tasks/plan.md"
        texte = "\n".join([f"# PLAN — {p}", "", "## Steps", "1. faire — angle mort: banc ?", "", "## Lots",
                           "LOT: A | dev-multi | moteur | src/a.py, src/b.py",
                           "LOT: B | dev-multi | doc | docs/b.md, docs/c.md", "INTÉGRATION: CHANGELOG.md"]) + "\n"
        (self.d / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
        (self.d / rel).write_text(texte, encoding="utf-8")
        sha = hashlib.sha256((self.d / rel).read_bytes()).hexdigest()
        entree = {"id": "S-00000001", "task": p, "kind": "decision", "title": "plan approuvé",
                  "text": f"plan={rel} sha256={sha}", "files": [], "date": "2026-10-13"}
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"entries": [entree]}), encoding="utf-8")
        return p


def _plancher(quand: datetime) -> datetime:
    return quand.replace(microsecond=0)


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    def l_1(self, bin_: Path) -> None:
        """L1 : `--delai 2h` borné par l'horloge ; `--jetons 500k` ; refus rc 2, board octet pour octet."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        t0 = _plancher(datetime.now(timezone.utc))
        b.ok("limite", t, "--delai", "2h")
        t1 = datetime.now(timezone.utc)
        echeance = datetime.strptime(b.tache(t)["echeance"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertTrue(t0 + timedelta(hours=2) <= echeance <= t1 + timedelta(hours=2), echeance)
        b.ok("limite", t, "--jetons", "500k")
        self.assertEqual(b.tache(t)["limite_jetons"], 500000)
        self.assertEqual(b.tache(t)["echeance"], echeance.strftime("%Y-%m-%dT%H:%M:%SZ"), "--jetons garde l'échéance")
        avant = b.board()
        for argv in (["--jetons", "0"], ["--jetons", "-1"], ["--jetons", "abc"], ["--jetons", "2x"],
                     ["--delai", "0h"], ["--delai", "2x"], ["--echeance", "2026-13-01T00:00Z"],
                     ["--delai", "2h", "--echeance", FUTURE], ["--retirer", "--jetons", "1k"], []):
            # Pas de `subTest` : il avalerait l'assertion que le mutant doit faire remonter.
            b.refus("limite", t, *argv)
            self.assertEqual(b.board(), avant, f"{argv} : board réécrit sur un refus")
        b.refus("conso", t, "0")
        self.assertEqual(b.board(), avant)

    def l_2(self, bin_: Path) -> None:
        """L2 : `conso` AJOUTE ; `limite --retirer` garde le cumul."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.ok("conso", t, "120k")
        b.ok("conso", t, "120k")
        self.assertEqual(b.tache(t)["jetons"], 240000)
        b.ok("limite", t, "--jetons", "1M", "--echeance", FUTURE)
        b.ok("limite", t, "--retirer")
        tache = b.tache(t)
        self.assertEqual(tache["jetons"], 240000)
        self.assertNotIn("limite_jetons", tache)
        self.assertNotIn("echeance", tache)

    def l_3(self, bin_: Path) -> None:
        """L3 : échéance passée + running → listée rc 1 ; `done` → absente rc 0 ; future → rc 0.
        Puis la frontière EN PROCESSUS, horloge injectée : à l'échéance pile, pas de dépassement."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.ok("start", t)
        b.ok("limite", t, "--echeance", PASSEE)
        r = b.t("depassements")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, rf"(?m)^LIMITE-DEPASSEE: {t} délai : échéance 2000-01-01T00:00:00Z dépassée de ")
        b.ok("done", t, "--raison", "banc")
        r = b.ok("depassements")
        self.assertNotIn(t, r.stdout)
        f = b.nouvelle()
        b.ok("limite", f, "--echeance", FUTURE, "--jetons", "1k")
        b.ok("conso", f, "1k")
        r = b.ok("depassements")
        self.assertRegex(r.stdout, r"\ALIMITE: aucune tâche au-delà de sa limite")
        m = charger(bin_)
        pile = datetime(2026, 1, 1, tzinfo=timezone.utc)
        data = {"tasks": [{"id": "T-1", "state": "pending", "task": "x", "echeance": "2026-01-01T00:00:00Z"}]}
        self.assertEqual(m.depassements(data, pile), [])
        self.assertEqual([d["type"] for d in m.depassements(data, pile + timedelta(seconds=1))], ["delai"])
        self.assertEqual(m.depassements(data, pile - timedelta(seconds=1)), [])

    def l_4(self, bin_: Path) -> None:
        """L4 : la tête de session n'existe qu'au dépassement ; sinon vue == liste nue (piège 2)."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.ok("limite", t, "--jetons", "1k", "--echeance", FUTURE)
        b.ok("conso", t, "1k")
        session, nue = b.ok("list", "--session").stdout, b.ok("list").stdout
        self.assertEqual(session, nue, "sans dépassement, la vue de session est la liste nue")
        self.assertNotIn("LIMITE-", session)
        b.ok("conso", t, "1k")
        session = b.ok("list", "--session").stdout
        self.assertIn("LIMITE-DEPASSEE: 1 tâche(s) au-delà de leur limite (alerte seule)", session)
        self.assertIn(f"LIMITE-DEPASSEE: {t} jetons : 2k / limite 1k", session)
        lignes = session.splitlines()
        self.assertEqual(lignes[0], "## TASK BOARD")
        self.assertTrue(lignes[1].startswith("LIMITE-DEPASSEE: "), "la tête suit `## TASK BOARD`")

    def l_5(self, bin_: Path) -> None:
        """L5 : désarmé → `start` rc 0 + stderr ; armé → rc 2, board identique ; `--retirer` lève."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.ok("limite", t, "--echeance", PASSEE)
        r = b.ok("start", t)
        self.assertRegex(r.stderr, rf"(?m)^LIMITE-DEPASSEE: {t} délai : ")
        b.ok("block", t, "--note", "banc")
        b.armer()
        avant = b.board()
        r = b.refus("start", t)
        self.assertIn(f"{t} {REFUS} (marqueur posé ou illisible) — start refusé", r.stderr)
        self.assertEqual(b.board(), avant)
        self.assertIn("(arrêt armé)", b.ok("list", "--session").stdout.split("| id ", 1)[0])
        r = b.ok("stage", t, "documenter")
        self.assertRegex(r.stderr, rf"(?m)^LIMITE-DEPASSEE: {t} délai : ", "stage DIT, jamais refusé")
        b.ok("limite", t, "--retirer")
        r = b.ok("start", t)
        self.assertNotIn("LIMITE-DEPASSEE", r.stderr)

    def l_6(self, bin_: Path) -> None:
        """L6 + C8 : `conso` qui franchit, armé → `blocked`, la note GARDE l'étape d'avant ; désarmé → running."""
        b = Banc(self, bin_)
        libre = b.nouvelle()
        b.ok("limite", libre, "--jetons", "100k")
        b.ok("start", libre, "--stage", "dev-multi")
        r = b.ok("conso", libre, "150k")
        self.assertEqual(b.tache(libre)["state"], "running")
        self.assertIn(f"LIMITE-DEPASSEE: {libre} jetons : 150k / limite 100k", r.stderr)
        b.ok("done", libre, "--raison", "banc")
        t = b.nouvelle()
        b.ok("limite", t, "--jetons", "100k")
        b.ok("start", t, "--stage", "security-code-review")
        b.armer()
        b.ok("conso", t, "90k")
        self.assertEqual(b.tache(t)["state"], "running", "sous la limite : rien ne bloque")
        b.ok("conso", t, "10k")
        self.assertEqual(b.tache(t)["state"], "running", "à la limite pile : rien ne bloque")
        r = b.ok("conso", t, "10k")
        tache = b.tache(t)
        self.assertEqual(tache["state"], "blocked")
        self.assertEqual(tache["jetons"], 110000, "la conso est écrite AVANT le blocage")
        self.assertIn("limite de jetons dépassée : 110k / 100k", tache["stage"])
        self.assertIn("étape avant blocage : security-code-review", tache["stage"])
        self.assertIn(REFUS, r.stdout)
        p = b.nouvelle()
        b.ok("limite", p, "--jetons", "1k")
        b.ok("conso", p, "2k")
        self.assertEqual(b.tache(p)["state"], "blocked", "une tâche pending est bloquée aussi")
        self.assertIn("aucune étape en cours avant blocage", b.tache(p)["stage"])
        # Le blocage, posé APRÈS l'écriture et hors du verrou, qui LÈVE (BoardError ou OSError) : le refus
        # porte le texte de refus que la doctrine guette, dit la conso écrite, et le remède.
        m = charger(bin_)
        for erreur, dit in ((m.BoardError("verrou pris"), "verrou pris"),
                            (OSError(28, "disque plein"), "[Errno 28] disque plein")):
            # Pas de subTest ici : il avalerait l'AssertionError que `test_mutants_rougissent` attend.
            q = b.nouvelle()
            b.ok("limite", q, "--jetons", "1k")
            with mock.patch.object(m, "block_task", side_effect=erreur):
                with self.assertRaises(m.BoardError, msg=dit) as ctx:
                    m.conso_task(str(b.d), q, "2k")
            self.assertIn(f"{q} {REFUS}", str(ctx.exception), dit)
            self.assertIn(f"conso ÉCRITE (2k / 1k) — ne pas la rejouer ; blocage NON posé ({dit})",
                          str(ctx.exception))
            self.assertIn("remède, geste du pilote", str(ctx.exception), dit)
            self.assertEqual(b.tache(q)["jetons"], 2000, f"la conso est bien écrite ({dit})")

    def l_7(self, bin_: Path) -> None:
        """L7 : `fournee P` armée, P dépassé → rc 2, racine (board, lots, journal) octet pour octet."""
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("limite", p, "--echeance", PASSEE)
        b.armer()
        avant = b.racine()
        r = b.refus("fournee", p)
        self.assertIn(f"{p} {REFUS}", r.stderr)
        self.assertEqual(b.racine(), avant, "une fournée refusée n'écrit rien")

    def l_8(self, bin_: Path) -> None:
        """L8 : valeurs malformées à la main → `list`, `list --session`, `depassements` sans trace, ILLISIBLE dit."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.abimer(t, limite_jetons="x", echeance=3, jetons=-4)
        b.ok("list", "--json")
        session = b.ok("list", "--session").stdout
        self.assertIn(f"LIMITE-ILLISIBLE: {t} champ limite_jetons", session)
        r = b.t("depassements")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        for champ in ("echeance", "limite_jetons", "jetons"):
            self.assertIn(f"LIMITE-ILLISIBLE: {t} champ {champ}", r.stdout)
        r = b.refus("conso", t, "1k")
        self.assertIn("champ jetons illisible", r.stderr)
        b.armer()
        r = b.ok("start", t)  # armé : une valeur illisible est DITE, jamais comptée comme franchie
        self.assertIn(f"LIMITE-ILLISIBLE: {t} champ echeance", r.stderr)

    def l_9(self, bin_: Path) -> None:
        """L9 : `depassements --json` = C-json, clés exactes ; `[]` à rc 0."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        r = b.ok("depassements", "--json")
        self.assertEqual(json.loads(r.stdout), [])
        b.ok("limite", t, "--echeance", PASSEE, "--jetons", "1k")
        b.ok("conso", t, "2k")
        b.armer()
        r = b.t("depassements", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        entrees = json.loads(r.stdout)
        self.assertEqual([list(e) for e in entrees], [CLES_JSON, CLES_JSON])
        jetons = next(e for e in entrees if e["type"] == "jetons")
        self.assertEqual(jetons, {"tache": t, "type": "jetons", "valeur": 2000, "limite": 1000,
                                  "etat": "pending", "arret": True})
        delai = next(e for e in entrees if e["type"] == "delai")
        self.assertEqual(delai["limite"], "2000-01-01T00:00:00Z")

    def l_10(self, bin_: Path) -> None:
        """L10 : un titre hostile (séquence d'échappement, substitution shell) n'apparaît dans aucune sortie."""
        b = Banc(self, bin_)
        marque = "titre-secret-L10"
        t = b.nouvelle(f"\x1b[2J $(id) {marque}")
        sorties = [b.ok("limite", t, "--jetons", "1k", "--echeance", PASSEE),
                   b.ok("conso", t, "2k"), b.t("depassements"), b.t("depassements", "--json"),
                   b.ok("stage", t, "dev-multi"), b.ok("list", "--session")]
        b.armer()
        sorties += [b.refus("start", t), b.ok("conso", t, "1k")]
        for r in sorties:
            for flux in (r.stdout, r.stderr):
                # La vue de session imprime le titre dans SA table : seule la tête est jugée là.
                tete = flux.split("| id ", 1)[0]
                self.assertNotIn(marque, tete)
                self.assertNotIn("\x1b", tete)
                self.assertNotIn("$(id)", tete)
        self.assertIn(f"LIMITE-DEPASSEE: {t}", sorties[2].stdout, "non-vacuité : l'id, lui, est dit")

    def l_11(self, bin_: Path) -> None:
        """C9 : la ligne `LIMITE-DEPASSEE:` sort aussi à `stage` et à `fournee` (désarmé, rc 0)."""
        b = Banc(self, bin_)
        t = b.nouvelle()
        b.ok("limite", t, "--echeance", PASSEE)
        r = b.ok("stage", t, "documenter")
        self.assertRegex(r.stderr, rf"(?m)^LIMITE-DEPASSEE: {t} délai : ")
        p = b.parent_pret()
        b.ok("limite", p, "--jetons", "1k")
        b.ok("conso", p, "5k")
        r = b.ok("fournee", p)
        self.assertIn(f"LIMITE-DEPASSEE: {p} jetons : 5k / limite 1k", r.stderr)

    def l_12(self, bin_: Path) -> None:
        """F2 : `fournee P` armée, un LOT EXISTANT dépassé (le parent, lui, dans sa limite) → rc 2,
        dossiers d'état octet pour octet."""
        b = Banc(self, bin_)
        p = b.parent_pret()
        b.ok("fournee", p)
        lots = sorted(t["id"] for t in json.loads(b.ok("list", "--json").stdout)
                      if isinstance(t.get("fournee"), dict) and t["fournee"].get("parent") == p)
        self.assertEqual(len(lots), 2, "la fournée nominale crée ses deux lots")
        lot = lots[0]
        b.ok("limite", lot, "--echeance", PASSEE)
        b.armer()
        avant = b.racine()
        r = b.refus("fournee", p)
        self.assertIn(f"{lot} {REFUS}", r.stderr)
        self.assertNotIn(f"{p} {REFUS}", r.stderr, "le parent n'est pas dépassé")
        self.assertEqual(b.racine(), avant, "une fournée refusée n'écrit rien")

    def l_13(self, bin_: Path) -> None:
        """Avis de sécurité + ME : un marqueur en lien PENDANT ou EN BOUCLE compte comme posé ; un
        dossier `gates` illisible compte comme ARMÉ (fail-closed). En processus."""
        m = charger(bin_)
        b = Banc(self, bin_)
        gates = b.d / ".agents" / "state" / "gates"
        marqueur = gates / "LIMITE_ARRET"
        self.assertFalse(m.limite_arret_arme(str(b.d)), "absent : désarmé")
        marqueur.symlink_to("/nonexistent/LIMITE_ARRET")
        self.assertTrue(m.limite_arret_arme(str(b.d)), "lien pendant : armé")
        marqueur.unlink()
        marqueur.symlink_to(marqueur)
        self.assertTrue(m.limite_arret_arme(str(b.d)), "lien en boucle : armé")
        marqueur.unlink()
        # `.agents` est un FICHIER : le marqueur ne peut pas exister — absence PROUVÉE, désarmé.
        plat = Path(tempfile.mkdtemp(prefix="limites-plat-"))
        self.addCleanup(shutil.rmtree, plat, True)
        (plat / ".agents").write_text("", encoding="utf-8")
        self.assertFalse(m.limite_arret_arme(str(plat)), "`.agents` fichier : désarmé")
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            self.skipTest("chmod 000 sans effet ici (root, ou hôte sans droits POSIX) : ME non mesurable")
        self.addCleanup(gates.chmod, 0o755)
        gates.chmod(0)
        self.assertTrue(m.limite_arret_arme(str(b.d)), "dossier gates illisible : armé")

    def l_14(self, bin_: Path) -> None:
        """F4 : un jugement qui LÈVE ne lève jamais l'arrêt — armé, `start` et `fournee` refusés ;
        désarmé, ou `stage`/`conso`, l'alerte DIT qu'elle n'est pas rendue (`LIMITE-ILLISIBLE:`),
        jamais un silence. En processus (`load` forcé à lever), puis par la CLI sur un board cassé."""
        m = charger(bin_)
        b = Banc(self, bin_)
        t = b.nouvelle()
        perdue = (f"LIMITE-ILLISIBLE: {t} jugement illisible — alerte non rendue ; "
                  "la cause : `python .agents/bin/tasks.py list`")
        with mock.patch.object(m, "load", side_effect=RuntimeError("board illisible")):
            self.assertEqual(m.limite_jugement(str(b.d), "start", t), (perdue, None), "désarmé : dit")
            b.armer()
            for verbe in ("start", "fournee"):
                alerte, refus = m.limite_jugement(str(b.d), verbe, t)
                self.assertIsNone(alerte)
                self.assertIn(f"{t} : jugement des limites illisible et LIMITE_ARRET est armé", refus or "")
                self.assertIn(f"{verbe} refusé", refus)
                self.assertIn("(marqueur posé ou illisible)", refus)
                self.assertTrue(refus.endswith("la cause : `python .agents/bin/tasks.py list`"), refus)
            for verbe in ("stage", "conso"):
                self.assertEqual(m.limite_jugement(str(b.d), verbe, t), (perdue, None))
            _, refus = m.limite_jugement(str(b.d), "start", "T-1\x1b[2J$(id)")
            self.assertIn("<id illisible>", refus or "")
            self.assertNotIn("\x1b", refus or "")
        b.store().write_text("{", encoding="utf-8")
        r = b.refus("start", t)
        self.assertIn("jugement des limites illisible et LIMITE_ARRET est armé", r.stderr)

    def l_15(self, bin_: Path) -> None:
        """Passe d'intégration (exec-critic S-01M5BY5P367BQ9V5PFYCPRP5HV) : la tête F8 (une ligne
        d'en-tête même pour des illisibles seuls, dépassements d'abord, 3 lignes au total, coupe
        dite), F5 (cumul DÉJÀ au-delà : bloqué), F6 (`fournee --dry-run` refusé sous l'arrêt, sans
        écrire) et `limite_k` en entiers au-delà de 2**53."""
        m = charger(bin_)
        self.assertEqual(m.limite_k(2**53 + 1), "9007199254740.993k")
        b = Banc(self, bin_)
        seul = b.nouvelle()
        b.abimer(seul, limite_jetons="x")
        tete = b.ok("list", "--session").stdout.split("| id ", 1)[0]
        self.assertIn("LIMITE-DEPASSEE: 0 tâche(s) au-delà de leur limite, 1 valeur(s) illisible(s) (alerte seule)", tete)
        t2, t3 = b.nouvelle(), b.nouvelle()
        for t in (t2, t3):
            b.ok("limite", t, "--echeance", PASSEE, "--jetons", "1k")
            b.ok("conso", t, "2k")
        lignes = b.ok("list", "--session").stdout.split("| id ", 1)[0].splitlines()
        self.assertEqual(lignes[1], "LIMITE-DEPASSEE: 2 tâche(s) au-delà de leur limite, 1 valeur(s) illisible(s) (alerte seule)")
        self.assertEqual([x for x in lignes[2:5] if "LIMITE-ILLISIBLE" in x], [], "dépassements d'abord")
        self.assertTrue(lignes[5].startswith("  (+2 ligne(s) non montrée(s)"), lignes[5])
        b.ok("start", t2)
        b.armer()
        b.ok("conso", t2, "1k")
        self.assertEqual(b.tache(t2)["state"], "blocked", "cumul déjà au-delà : bloqué")
        p = b.parent_pret()
        b.ok("limite", p, "--echeance", PASSEE)
        avant = b.racine()
        b.refus("fournee", p, "--dry-run")
        self.assertEqual(b.racine(), avant)


# Mutant → (témoin qui le tue, ancres). Chaque ancre est unique dans son fichier (asserté).
MUTANTS: dict[str, tuple[str, dict[str, list[tuple[str, str]]]]] = {
    "L1 jetons > 0 devient >= 0": ("l_1", {"tasks_requetes.py": [(
        '_LIMITE_JETONS = re.compile(r"([1-9][0-9]{0,11})([kM]?)")',
        '_LIMITE_JETONS = re.compile(r"([0-9][0-9]{0,11})([kM]?)")')]}),
    "L2 conso écrase au lieu d'ajouter": ("l_2", {"tasks_verbes.py": [(
        'task["jetons"] = lus["jetons"] + ajout', 'task["jetons"] = ajout')]}),
    "L3 comparaison du délai inversée": ("l_3", {"tasks_requetes.py": [(
        'if lus["echeance"] is not None and quand > lus["echeance"]:',
        'if lus["echeance"] is not None and quand < lus["echeance"]:')]}),
    "L3 filtre done retiré": ("l_3", {"tasks_requetes.py": [(
        'if not isinstance(task, dict) or task.get("state") == "done":', 'if not isinstance(task, dict):')]}),
    "L4 tête toujours émise": ("l_4", {"tasks_rendu.py": [(
        '        if not trouves:\n            return None\n        n = len(',
        '        n = len(')]}),
    "L5 test du marqueur inversé": ("l_5", {"tasks_requetes.py": [
        ("    except (FileNotFoundError, NotADirectoryError):\n        return False",
         "    except (FileNotFoundError, NotADirectoryError):\n        return True"),
        ("        return True\n    return True\n", "        return True\n    return False\n")]}),
    "L6 appel block_task ôté": ("l_6", {"tasks_verbes.py": [(
        'message += "\\n" + block_task(root, task["id"], note)', 'message += "\\n"')]}),
    "F4c blocage levé sans dire la conso écrite": ("l_6", {"tasks_verbes.py": [(
        '        except (BoardError, OSError) as exc:\n            raise BoardError(f"{limite_id(task)} {LIMITE_REFUS}',
        '        except ZeroDivisionError as exc:\n            raise BoardError(f"{limite_id(task)} {LIMITE_REFUS}')]}),
    "C8 note sans l'étape d'avant": ("l_6", {"tasks_verbes.py": [(
        '+ (f"étape avant blocage : {avant}" if avant else "aucune étape en cours avant blocage"))', ')')]}),
    "L7 jugement déplacé après fournee()": ("l_7", {"tasks.py": [
        ('if args.cmd in ("start", "fournee", "stage") and not args.statusline:\n            alerte_limite',
         'if args.cmd in ("start", "stage") and not args.statusline:\n            alerte_limite'),
        ("            if not args.dry_run:\n                marquer_session(root, [args.tid], fournee_de=args.tid)\n",
         "            if not args.dry_run:\n                marquer_session(root, [args.tid], fournee_de=args.tid)\n"
         "            _a, _r = limite_jugement(root, 'fournee', args.tid)\n"
         "            if _r:\n                print(f'tasks.py: {_r}', file=sys.stderr)\n                return 2\n")]}),
    "L8 entier lu sans garde": ("l_8", {"tasks_requetes.py": [(
        "if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < plancher:",
        "if int(valeur) < plancher:")]}),
    "L9 clé arret ôtée": ("l_9", {"tasks_requetes.py": [(
        'for k in ("tache", "type", "valeur", "limite", "etat", "arret")}',
        'for k in ("tache", "type", "valeur", "limite", "etat")}')]}),
    "L10 le titre au lieu de l'id": ("l_10", {"tasks_requetes.py": [(
        'return tid if isinstance(tid, str) and _SESSION_ID.fullmatch(tid) else "<id illisible>"',
        'return str(task.get("task"))')]}),
    "C9 stage et fournee sans alerte": ("l_11", {"tasks.py": [(
        'if args.cmd in ("start", "fournee", "stage") and not args.statusline:\n            alerte_limite',
        'if args.cmd in ("start",) and not args.statusline:\n            alerte_limite')]}),
    # Passe de correction (exec-critic S-01M5AZ4B5V1AV96J9RFYH712H9) : les survivants MA-MJ, F4, le lien.
    "MA lots existants ignorés à la fournée": ("l_12", {"tasks_requetes.py": [(
        '        if verbe == "fournee":\n            membres |= {t.get("id") for t in fournee_lots_existants(data, tid).values()}',
        '        if False:\n            pass')]}),
    "MB conso ne bloque plus un pending": ("l_6", {"tasks_verbes.py": [(
        'task["state"] in ("pending", "running")', 'task["state"] in ("running",)')]}),
    "MC conso bloque à l'égalité (>=)": ("l_6", {"tasks_verbes.py": [(
        'task["jetons"] > plafond and', 'task["jetons"] >= plafond and')]}),
    "ME marqueur fail-open sur OSError": ("l_13", {"tasks_requetes.py": [(
        "    except (OSError, ValueError):\n        return True", "    except (OSError, ValueError):\n        return False")]}),
    "AV marqueur lu en suivant le lien": ("l_13", {"tasks_requetes.py": [(
        "os.lstat(Path(root) / LIMITE_ARRET_REL)", "(Path(root) / LIMITE_ARRET_REL).stat()")]}),
    "MG tête toujours « alerte seule »": ("l_5", {"tasks_rendu.py": [(
        'mode = "arrêt armé" if arme else "alerte seule"', 'mode = "alerte seule"')]}),
    "MI stage refusé sous l'arrêt": ("l_5", {"tasks_requetes.py": [(
        'if arme and franchies and verbe in ("start", "fournee"):',
        'if arme and franchies and verbe in ("start", "fournee", "stage"):')]}),
    "MJ illisible compté comme franchi (arrêt)": ("l_8", {"tasks_requetes.py": [(
        'franchies = sorted({d["tache"] for d in trouves if d["type"] != "illisible"})',
        'franchies = sorted({d["tache"] for d in trouves})')]}),
    "F4 jugement levé : arrêt ouvert": ("l_14", {"tasks_requetes.py": [(
        '        if arme and verbe in ("start", "fournee"):\n            return None, (',
        '        if False:\n            return None, (')]}),
    # Passe d'intégration (exec-critic S-01M5BY5P367BQ9V5PFYCPRP5HV, sécurité S-01M5BTKQHRBGEAS5SWPW4G8JYK).
    "F8a en-tête tu sans dépassement": ("l_15", {"tasks_rendu.py": [('({mode})"]', '({mode})"] if n else []')]}),
    "F8b coupe à 5 lignes": ("l_15", {"tasks_rendu.py": [
        ("ordre[:SESSION_TETE_MAX]]", "ordre[:SESSION_TETE_MAX + 2]]")]}),
    "F8c illisibles non relégués": ("l_15", {"tasks_rendu.py": [
        ('sorted(trouves, key=lambda d: d["type"] == "illisible")', "trouves")]}),
    "F5 seul le franchissement bloque": ("l_15", {"tasks_verbes.py": [
        ('task["jetons"] > plafond and', 'task["jetons"] > plafond >= lus["jetons"] and')]}),
    "F6 --dry-run échappe à l'arrêt": ("l_15", {"tasks.py": [
        ('if args.cmd in ("start", "fournee", "stage") and not args.statusline:',
         'if args.cmd in ("start", "fournee", "stage") and not args.statusline and not getattr(args, "dry_run", False):')]}),
    "LK limite_k en flottant": ("l_15", {"tasks_rendu.py": [
        ('return f"{n // 1000}.{n % 1000:03d}".rstrip("0") + "k"',
         'return f"{n / 1000:.3f}".rstrip("0").rstrip(".") + "k"')]}),
    "AN `.agents` fichier compté armé": ("l_13", {"tasks_requetes.py": [
        ("    except (FileNotFoundError, NotADirectoryError):\n", "    except FileNotFoundError:\n")]}),
    "MP refus muet sur le pourquoi": ("l_5", {"tasks_requetes.py": [
        ('LIMITE_ARME_POURQUOI = "(marqueur posé ou illisible)"', 'LIMITE_ARME_POURQUOI = ""')]}),
    "F4b refus sans la cause": ("l_14", {"tasks_requetes.py": [
        ('board NON écrit ; la cause : "\n                          "`python .agents/bin/tasks.py list`")',
         'board NON écrit")')]}),
    "F5 jugement levé désarmé : alerte perdue en silence": ("l_14", {"tasks_requetes.py": [(
        '        return (f"LIMITE-ILLISIBLE: {limite_id({\'id\': tid})} jugement illisible',
        '        return None, None\n        return (f"LIMITE-ILLISIBLE: {limite_id({\'id\': tid})} jugement illisible')]}),
}


class TestLimites(Temoins, unittest.TestCase):
    def test_l1_pose_et_refus(self) -> None:
        self.l_1(BIN)

    def test_l2_conso_ajoute(self) -> None:
        self.l_2(BIN)

    def test_l3_depassements(self) -> None:
        self.l_3(BIN)

    def test_l4_tete_de_session(self) -> None:
        self.l_4(BIN)

    def test_l5_arret_au_start(self) -> None:
        self.l_5(BIN)

    def test_l6_conso_bloque_et_garde_l_etape(self) -> None:
        self.l_6(BIN)

    def test_l7_fournee_refusee_sans_ecrire(self) -> None:
        self.l_7(BIN)

    def test_l8_valeurs_illisibles(self) -> None:
        self.l_8(BIN)

    def test_l9_forme_json(self) -> None:
        self.l_9(BIN)

    def test_l10_titre_jamais_imprime(self) -> None:
        self.l_10(BIN)

    def test_l11_alerte_a_stage_et_fournee(self) -> None:
        self.l_11(BIN)

    def test_l12_fournee_refusee_sur_un_lot_depasse(self) -> None:
        self.l_12(BIN)

    def test_l13_marqueur_lien_et_dossier_illisible(self) -> None:
        self.l_13(BIN)

    def test_l14_jugement_leve_arret_tenu(self) -> None:
        self.l_14(BIN)

    def test_l15_tete_cumul_dry_run_et_milliers(self) -> None:
        self.l_15(BIN)

    def test_doctrine_conso_cablee(self) -> None:
        """F2 : sans un appel de `conso` écrit dans les surfaces d'orchestration, la limite de jetons ne
        mord jamais. Un chemin absent (arbre partiel) est SAUTÉ et dit, jamais un vert muet."""
        absents = []
        for rel in (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md", ".agents/skills/night/SKILL.md",
                    ".agents/skills/planning/SKILL.md", ".agents/skills/task-board/SKILL.md",
                    ".claude/commands/night.md"):
            if not (ROOT / rel).is_file():
                absents.append(rel)
                continue
            t = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("tasks.py conso", t, rel)
            self.assertIn("LIMITE-DEPASSEE:", t, rel)
        self.assertIn("One bound, pilot S-01M54GFZ2VCYVA8RSJYBV6539H", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        if absents:
            self.skipTest(f"surfaces absentes de cet arbre, non jugées : {', '.join(absents)}")

    def test_mutants_rougissent(self) -> None:
        # Contrôle : chaque témoin VERT sur une copie NON mutée — sinon une copie cassée (résolveur
        # absent, rc 2 dans `Banc.ok`) lève une AssertionError qui « tue » tous les mutants.
        for temoin in sorted({t for t, _ in MUTANTS.values()}):
            with self.subTest(controle=temoin):
                getattr(self, temoin)(copie(self, {}))
        for nom, (temoin, mutations) in MUTANTS.items():
            with self.subTest(mutant=nom):
                dest = copie(self, mutations)
                with self.assertRaises(AssertionError, msg=f"mutant {nom} : {temoin} reste vert"):
                    getattr(self, temoin)(dest)


if __name__ == "__main__":
    unittest.main()
