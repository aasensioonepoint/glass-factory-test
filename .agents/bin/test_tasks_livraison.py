"""LA LIVRAISON DÉCLARÉE — comportement (`tasks.py livraison`, la revue qu'elle prête).

T-01M4WTYSCEYHC6KZF2DC1PXBRN, décisions pilote S-01M4X6K3JRR90VVWR4AFHT983G (verbe dédié)
et S-01M4WTZ1QZQJZZNYRC5YA67AZW (levier). ZÉRO APPEL LLM.

Chaque témoin `l_*` / `b_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`, ou
une COPIE JETABLE dont un fragment littéral, présent UNE fois (asserté par `copie`, reprise
de `test_retour_done_guard.py`), est remplacé. Un mutant ne rejoue QUE le témoin qui le tue
et doit le faire échouer par une ASSERTION : les aides du banc lèvent `RuntimeError`.

UN board jetable PAR TÉMOIN (`tempfile`), HORS git — la jambe « reprise » du binôme y est
INERTE et MUETTE, ce banc éprouve la seule PREUVE. `HOME`, `XDG_CONFIG_HOME`,
`CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR` jetables, `CLAUDE_PROJECT_DIR` et `GIT_*` retirés.
Les traces ont la forme RÉELLE du traceur (`{"sha", "at"}`, `at` RELATIF à maintenant).

Témoins : L1 le même dict sur chaque tâche nommée (`list --task`), re-déclaration DITE ;
L2 un id inconnu → rc 2, `unknown task id`, board inchangé à l'octet, et TOUTES les causes
(tâche close, branche inadmissible) ; L3 `--retirer` ; L4/L4b `reopen` et `start` depuis
`done` ôtent la livraison. B1/B1b emprunt à un membre (tout état), B2 trace antérieure à la
déclaration, B2b relevé `--vers` postérieur, B3 dicts différents, B4 cycle passé, B5 le slot
sous livraison, B6 relevé à la date illisible (fail-closed), B7 la forme de la jambe reprise
sous livraison (seul témoin monté dans un dépôt git : hors git elle est inerte).

BORNE : le dict est DÉCLARATIF. Ça empêche d'OUBLIER, pas de TRICHER.
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

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"

# `copie` (ancres à compte 1, frères d'allocation) est celle de test_retour_done_guard.py :
# un seul harnais de variantes pour les bancs du relevé et de la livraison.
_PARTAGE = "test_retour_done_guard_partage_livraison"
_spec = importlib.util.spec_from_file_location(_PARTAGE, ROOT / ".agents" / "evals" / "test_retour_done_guard.py")
_rdg = importlib.util.module_from_spec(_spec)
sys.modules[_PARTAGE] = _rdg
_spec.loader.exec_module(_rdg)
copie = _rdg.copie


def il_y_a(heures: float) -> str:
    """Un `at` RELATIF à maintenant, au format exact du traceur."""
    return (datetime.now(timezone.utc) - timedelta(hours=heures)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Board:
    """UN board jetable, hors git, la CLI de `bin_` braquée dessus."""

    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin = case, bin_
        self.racine = Path(tempfile.mkdtemp(prefix="livraison-")).resolve()
        case.addCleanup(shutil.rmtree, self.racine, True)
        self.d = self.racine / "depot"
        for sous in ("depot", "home", "xdg", "etat", "events"):
            (self.racine / sous).mkdir()
        for sous in ("board", "gates", "local/binome"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True)
        # Une identité git jetable : sans elle, l'export d'événements se reporte et le DIT sur stderr.
        (self.racine / "home" / ".gitconfig").write_text(
            "[user]\n\tname = banc\n\temail = banc@exemple.invalid\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        self.env.update(HOME=str(self.racine / "home"), XDG_CONFIG_HOME=str(self.racine / "xdg"),
                        CADRE_STATE_DIR=str(self.racine / "etat"), AGENTS_EVENTS_DIR=str(self.racine / "events"))

    def t(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=300, env=self.env, check=False)

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        if r.returncode != 0:
            raise RuntimeError(f"banc : {args} en échec : {r.stdout}{r.stderr}")
        return r

    def nouvelle(self, titre: str = "tâche de banc", chantier: str | None = None) -> str:
        r = self.ok("new", titre, *(["--chantier", chantier] if chantier else []))
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        if trouve is None:
            raise RuntimeError(f"banc : message de `new` inattendu : {r.stdout}")
        return trouve.group(1)

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def board(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    def board_sha(self) -> str:
        return hashlib.sha256(self.board().read_bytes()).hexdigest()

    def forger(self, tid: str, **champs) -> None:
        """Réécrit des champs de `tid` au board, à la main."""
        data = json.loads(self.board().read_text(encoding="utf-8"))
        tache = next(t for t in data["tasks"] if t["id"] == tid)
        tache.update(champs)
        self.board().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def armer_binome(self) -> None:
        (self.d / ".agents" / "state" / "gates" / "BINOME_REQUIRED").write_text("", encoding="utf-8")

    def tracer(self, tid: str, at: str, nom: str = "critic-opus", sha: str = "abc1234") -> None:
        """La trace que le traceur de l'hôte écrit à l'arrêt d'un critique."""
        chemin = self.d / ".agents" / "state" / "local" / "binome" / f"{tid}.{nom}.json"
        chemin.write_text(json.dumps({"sha": sha, "at": at}), encoding="utf-8")

    def portee(self, focus: str, membres: list[str]) -> None:
        """Focus et portée de revue posés à la main, déclarée ANCIENNE (T-01M5F728FGJ43QJX1RJKTWWKRB) :
        l'emprunt au slot passe par la portée, plus par le chantier."""
        local, quand = self.d / ".agents" / "state" / "local", "2026-01-01T00:00:00.000Z"
        (local / "focus.json").write_text(json.dumps({"task_id": focus, "updated_at": quand}), encoding="utf-8")
        (local / "review-scope.json").write_text(json.dumps(
            {"focus": focus, "members": membres, "consumed": [], "declared_at": quand}), encoding="utf-8")

    def g(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=self.d, env=self.env, capture_output=True, text=True,
                           timeout=120, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
        return r.stdout

    def depot_git(self, fichiers: dict[str, str]) -> str:
        """Le board DEVIENT un dépôt git (le board sous `.agents/`, exclu) portant `fichiers`,
        commités : rend le sha COURT, la forme que le traceur écrit."""
        self.g("init", "-q", "-b", "main")
        (self.d / ".git" / "info" / "exclude").write_text(".agents/\n", encoding="utf-8")
        for chemin, contenu in fichiers.items():
            (self.d / chemin).write_text(contenu, encoding="utf-8")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "base")
        return self.g("rev-parse", "--short", "HEAD").strip()

    def portes(self, *ats: str) -> None:
        """`VERIFY_STAMP.log` : un vert `frozen` par `at`, chacun sur un sha distinct."""
        chemin = self.d / ".agents" / "state" / "local" / "VERIFY_STAMP.log"
        chemin.write_text("".join(f"at={a}\tsha=c0ffee{i}\tmode=frozen\n" for i, a in enumerate(ats)),
                          encoding="utf-8")


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    def refuse(self, r: subprocess.CompletedProcess, *contient: str) -> str:
        self.assertNotEqual(r.returncode, 0, f"admis : {r.stdout}{r.stderr}")
        for x in contient:
            self.assertIn(x, r.stderr)
        return r.stderr

    def admis(self, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(r.returncode, 0, f"refusé : {r.stdout}{r.stderr}")

    # -- L1 L2 L3 : le verbe -------------------------------------------------------
    def l_01(self, bin_: Path) -> None:
        """Le MÊME dict sur chaque tâche nommée ; une re-déclaration le remplace et le DIT,
        et nomme la tâche qui garde l'ancien."""
        b = Board(self, bin_)
        a, c, d = b.nouvelle("a"), b.nouvelle("c"), b.nouvelle("d")
        r = b.ok("livraison", a, c, a, "--branche", "refs/heads/integ/l")
        self.assertIn(f"livraison integ/l déclarée sur {a}, {c}", r.stdout)
        da, dc = b.tache(a)["livraison"], b.tache(c)["livraison"]
        self.assertEqual(da, dc, "les dicts des tâches nommées diffèrent")
        self.assertEqual((da["branche"], da["taches"]), ("integ/l", [a, c]))
        self.assertRegex(da["le"], r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
        self.assertNotIn("livraison", b.tache(d))
        r = b.ok("livraison", a, d, "--branche", "integ/m")
        self.assertIn(f"{a} livraison REMPLACÉE : integ/l", r.stdout)
        self.assertIn(f"{c} garde(nt) l'ancienne livraison integ/l", r.stdout)
        self.assertEqual(b.tache(a)["livraison"], b.tache(d)["livraison"])
        self.assertEqual(b.tache(c)["livraison"], dc, "la tâche non nommée a perdu son dict")

    def l_02(self, bin_: Path) -> None:
        """Un id inconnu : rc 2, `unknown task id: <tid>`, board inchangé À L'OCTET ; et TOUTES
        les causes ensemble (tâche close, branche inadmissible)."""
        b = Board(self, bin_)
        a, close = b.nouvelle("a"), b.nouvelle("close")
        b.ok("done", close, "--raison", "close")
        avant = b.board_sha()
        r = b.t("livraison", a, "T-99999999", "--branche", "integ/l")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unknown task id: T-99999999", r.stderr)
        self.assertRegex(r.stderr, r"(?m)^tasks\.py: ")
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")
        r = b.t("livraison", a, close, "T-99999999", "--branche", "-x y\x01")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        for cause in ("unknown task id: T-99999999", f"{close} est close (done)", "commence par « - »",
                      "porte un espace", "caractère de contrôle", "5 cause(s)"):
            self.assertIn(cause, r.stderr)
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")
        self.assertNotIn("livraison", b.tache(a))

    def l_03(self, bin_: Path) -> None:
        """`--retirer` ôte la clé de la livraison NOMMÉE ; une autre livraison refuse."""
        b = Board(self, bin_)
        a, c = b.nouvelle("a"), b.nouvelle("c")
        b.ok("livraison", a, c, "--branche", "integ/l")
        avant = b.board_sha()
        self.refuse(b.t("livraison", a, "--branche", "integ/autre", "--retirer"), "porte une autre livraison")
        self.assertEqual(b.board_sha(), avant)
        r = b.ok("livraison", a, "--branche", "integ/l", "--retirer")
        self.assertIn(f"{a} livraison integ/l retirée", r.stdout)
        self.assertNotIn("livraison", b.tache(a))
        self.assertIn("livraison", b.tache(c), "--retirer a touché une tâche non nommée")
        r = b.ok("livraison", a, "--branche", "integ/l", "--retirer")
        self.assertIn("rien à retirer", r.stdout)

    # -- L4 L4b : la clôture annulée emporte sa revue ----------------------------------
    def emprunt_clos(self, bin_: Path) -> tuple[Board, str, str]:
        """A tracé après la déclaration, B clos en EMPRUNTANT la trace de A (mention nommée)."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        b.ok("livraison", a, c, "--branche", "integ/l")
        at = il_y_a(0)
        b.tracer(a, at)
        self.admis(b.t("done", c, "--raison", "livré par la livraison"))
        self.assertIn(f"[binôme de la livraison integ/l relevé sur {a} @ abc1234, {at}]", b.tache(c)["stage"])
        return b, a, c

    def l_04(self, bin_: Path) -> None:
        """`done B` (emprunt) → `reopen B` → `done B` REFUSÉ : la livraison est tombée."""
        b, _a, c = self.emprunt_clos(bin_)
        b.ok("reopen", c, "--raison", "rouvrir")
        self.assertNotIn("livraison", b.tache(c))
        self.refuse(b.t("done", c, "--raison", "second cycle"), "REVUE CRITIQUE")

    def l_04b(self, bin_: Path) -> None:
        """Idem par un `start` depuis `done`."""
        b, _a, c = self.emprunt_clos(bin_)
        b.ok("start", c)
        self.assertNotIn("livraison", b.tache(c))
        self.refuse(b.t("done", c, "--raison", "second cycle"), "REVUE CRITIQUE")

    # -- B1-B5 : la revue prêtée par la livraison --------------------------------------
    def declarer(self, b: Board, tids: list[str], heures: float) -> None:
        """La livraison déclarée il y a `heures` h : le MÊME dict forgé sur chaque tâche."""
        dict_ = {"branche": "integ/l", "taches": list(tids), "le": il_y_a(heures)}
        for tid in tids:
            b.forger(tid, livraison=dict(dict_))

    def b_01(self, bin_: Path) -> None:
        """A tracé (pending), B pending : `done B` passe, la mention nomme la livraison."""
        self.emprunt_clos(bin_)

    def b_01b(self, bin_: Path) -> None:
        """A déjà CLOS sur sa propre trace : B emprunte encore (tout état)."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        b.ok("livraison", a, c, "--branche", "integ/l")
        b.tracer(a, il_y_a(0))
        self.admis(b.t("done", a, "--raison", "sa propre revue"))
        self.admis(b.t("done", c, "--raison", "emprunt à un membre clos"))
        self.assertIn(f"binôme de la livraison integ/l relevé sur {a}", b.tache(c)["stage"])

    def b_02(self, bin_: Path) -> None:
        """Une trace ANTÉRIEURE à la déclaration ne se prête pas."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        self.declarer(b, [a, c], 1)
        b.tracer(a, il_y_a(2))
        self.refuse(b.t("done", c, "--raison", "x"), "la livraison `integ/l` ne la prête pas",
                    f"la trace de {a} précède la déclaration")

    def b_02b(self, bin_: Path) -> None:
        """Un relevé `--vers` d'un membre POSTÉRIEUR à la trace rend la revue caduque — refus nommé."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        self.declarer(b, [a, c], 3)
        b.tracer(a, il_y_a(2))
        b.forger(c, retour={"verdict": "ok", "vers": "integ/l", "le": il_y_a(1)})
        self.refuse(b.t("done", c, "--raison", "x"), f"un relevé de {c} postérieur à la revue",
                    "relance le critique ; les corrections se commitent sur integ/l, sans relevé")
        b.forger(c, retour={"verdict": "ok", "vers": "integ/autre", "le": il_y_a(1)})
        self.admis(b.t("done", c, "--raison", "un relevé vers une autre branche ne borne rien"))

    def b_03(self, bin_: Path) -> None:
        """Des dicts DIFFÉRENTS (même branche, A re-déclarée avec une autre tâche) ne prêtent rien."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c, d = b.nouvelle("a"), b.nouvelle("b"), b.nouvelle("d")
        b.ok("livraison", a, c, "--branche", "integ/l")
        b.ok("livraison", a, d, "--branche", "integ/l")
        b.tracer(a, il_y_a(0))
        err = self.refuse(b.t("done", c, "--raison", "x"), "la livraison `integ/l` ne la prête pas")
        self.assertIn(f"Membres (dict identique) : {c}.", err)
        self.admis(b.t("done", d, "--raison", "même dict que A"))

    def b_04(self, bin_: Path) -> None:
        """Une trace d'un CYCLE PASSÉ (avant l'avant-dernier vert frozen) ne se prête pas."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        self.declarer(b, [a, c], 3)
        b.tracer(a, il_y_a(2))
        b.portes(il_y_a(1.5), il_y_a(1))
        self.refuse(b.t("done", c, "--raison", "x"), "PÉRIMÉE", "antérieure à la porte verte précédente")

    def b_05(self, bin_: Path) -> None:
        """Sans livraison, l'emprunt au slot garde sa forme ; SOUS livraison, le slot est borné
        par le dernier relevé (choix du dev) et un slot non membre garde la mention du slot."""
        b = Board(self, bin_)
        b.armer_binome()
        slot = b.nouvelle("slot", chantier="ch")
        b.ok("start", slot)
        b.tracer(slot, il_y_a(2))
        nue = b.nouvelle("sans livraison", chantier="ch")
        b.portee(slot, [slot, nue])
        self.admis(b.t("done", nue, "--raison", "emprunt au slot"))
        self.assertIn(f"[binôme relevé sur {slot} @ abc1234,", b.tache(nue)["stage"])
        a, c = b.nouvelle("a", chantier="ch"), b.nouvelle("b", chantier="ch")
        b.portee(slot, [slot, a, c])
        self.declarer(b, [a, c], 3)
        b.forger(a, retour={"verdict": "ok", "vers": "integ/l", "le": il_y_a(1)})
        self.refuse(b.t("done", c, "--raison", "x"), f"un relevé de {a} postérieur à la revue")
        b.tracer(slot, il_y_a(0))
        self.admis(b.t("done", c, "--raison", "slot relu après le relevé"))
        stage = b.tache(c)["stage"]
        self.assertIn(f"[binôme relevé sur {slot} @ abc1234,", stage)
        self.assertNotIn("binôme de la livraison", stage, "un slot non membre nommé comme la livraison")


    def b_06(self, bin_: Path) -> None:
        """FAIL-CLOSED (MX-F) : un relevé `--vers` d'un membre dont la date est ILLISIBLE pose une
        borne infinie — aucune trace ne la passe, le refus nomme le relevé et dit la date illisible."""
        b = Board(self, bin_)
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        self.declarer(b, [a, c], 3)
        b.tracer(a, il_y_a(2))
        b.forger(c, retour={"verdict": "ok", "vers": "integ/l", "le": "pas une date"})
        self.refuse(b.t("done", c, "--raison", "x"), f"un relevé de {c} postérieur à la revue (date illisible)")

    def b_07(self, bin_: Path) -> None:
        """LA JAMBE REPRISE NOMME L'EMPRUNT À LA LIVRAISON (MX-G) : dans un dépôt git, la trace de A
        (sha de la base) précède une écriture de `PLAN-ETAT.md` ; `done B` emprunte à A et le refus
        de reprise dit « preuve empruntée à `A` (livraison `integ/l`) », jamais « au slot »."""
        b = Board(self, bin_)
        sha = b.depot_git({"PLAN-ETAT.md": "état du chantier\n"})
        b.armer_binome()
        a, c = b.nouvelle("a"), b.nouvelle("b")
        b.ok("livraison", a, c, "--branche", "integ/l")
        b.tracer(a, il_y_a(0), sha=sha)
        (b.d / "PLAN-ETAT.md").write_text("état réécrit après la revue\n", encoding="utf-8")
        err = self.refuse(b.t("done", c, "--raison", "x"), "l'état COURANT des fichiers de reprise",
                          f"preuve empruntée à `{a}` (livraison `integ/l`)", "PLAN-ETAT.md")
        self.assertNotIn("empruntée au slot", err)


class LivraisonTests(Temoins, unittest.TestCase):
    """Chaque témoin sur le VRAI `.agents/bin`."""


for _nom in sorted(n for n in dir(Temoins) if re.match(r"[lb]_\d", n)):
    setattr(LivraisonTests, "test_" + _nom, (lambda n: lambda self: getattr(self, n)(BIN))(_nom))


#: Les mutants : `nom → ({fichier: [(ancre, remplacement)]}, témoin)`. Chaque ancre est un
#: FRAGMENT LITTÉRAL présent UNE fois (asserté par `copie`).
_G = "tasks_gardes.py"
MUTANTS: dict[str, tuple[dict[str, list[tuple[str, str]]], str]] = {
    "re-déclaration tue": ({_G: [('                    lignes.append(f"TASKS: {tache[\'id\']} livraison REMPLACÉE : "\n',
                                  "                    pass\n                    (f\"TASKS: {tache['id']} livraison REMPLACÉE : \"\n")]},
                           "l_01"),
    "première cause seule": ({_G: [('            raise BoardError(f"refus de {\'retirer\' if retirer else \'déclarer\'} '
                                    'la livraison — {len(causes)} cause(s) :\\n"\n'
                                    '                             + "".join(f"  - {c}\\n" for c in causes)',
                                    '            raise BoardError(f"refus de {\'retirer\' if retirer else \'déclarer\'} '
                                    'la livraison — {len(causes)} cause(s) :\\n"\n'
                                    '                             + "".join(f"  - {c}\\n" for c in causes[:1])')]},
                             "l_02"),
    # -- étape 7 du plan : les mutants neufs de la livraison -----------------------------
    "M-L1 reopen garde la livraison": ({"tasks_verbes.py": [('        task.pop("livraison", None)\n', "")]}, "l_04"),
    "M-L2 start depuis done garde la livraison": ({"tasks_etats.py": [(
        '            if before["state"] == "done":\n                task.pop("livraison", None)\n', "")]}, "l_04b"),
    "at < le admis": ({_G: [('    borne = _date_trace_brute(liv.get("le")) or datetime.max.replace(tzinfo=timezone.utc)\n',
                             "    borne = datetime.min.replace(tzinfo=timezone.utc)\n")]}, "b_02"),
    "borne retour.le ignorée": ({_G: [('        if not (isinstance(releve, dict) and releve.get("vers") == '
                                       'liv.get("branche")):\n', "        if True:\n")]}, "b_02b"),
    "dict par la branche seule": ({_G: [("            if t in par_id and livraison_de(par_id[t]) == liv]",
                                         "            if t in par_id and (livraison_de(par_id[t]) or {})"
                                         '.get("branche") == liv["branche"]]')]}, "b_03"),
    "seul un prêteur running": ({_G: [('        if membre["id"] == task["id"]:\n            continue\n',
                                       '        if membre["id"] == task["id"] or membre.get("state") != "running":\n'
                                       "            continue\n")]}, "b_01b"),
    "fraîcheur ignorée": ({_G: [("        return retenues if recent and recent > porte else {}\n",
                                 "        return retenues\n")]}, "b_04"),
    "slot non borné sous livraison": ({_G: [("                empruntee = bornee\n", "")]}, "b_05"),
    "mention de la livraison tue": ({"tasks_etats.py": [("                    if branche_liv:\n"
                                                         '                        emprunt = (f" [binôme de la livraison',
                                                         "                    if False:\n"
                                                         '                        emprunt = (f" [binôme de la livraison')]},
                                    "b_01"),
    # -- exec-critic du lot A : les deux survivants -------------------------------------
    "MX-F relevé illisible lu comme le plus ancien": ({_G: [(
        '        date_releve = _date_trace_brute(releve.get("le")) or datetime.max.replace(tzinfo=timezone.utc)\n',
        '        date_releve = _date_trace_brute(releve.get("le")) or datetime.min.replace(tzinfo=timezone.utc)\n')]},
        "b_06"),
    "MX-G forme de la reprise sous livraison retirée": ({"tasks_etats.py": [(
        '    if branche_liv:\n        emprunt = f", preuve empruntée à',
        '    if False:\n        emprunt = f", preuve empruntée à')]}, "b_07"),
}


class LivraisonMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant de `MUTANTS` rejoue SON témoin et doit le faire échouer."""

    def tuer(self, nom: str) -> None:
        mutations, temoin = MUTANTS[nom]
        variante = copie(self, BIN, mutations)
        with self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
            getattr(self, temoin)(variante)

    def test_la_variante_non_mutee_est_verte(self):
        """NON-VACUITÉ du harnais : une copie SANS mutation passe un témoin de chaque famille."""
        variante = copie(self, BIN, {})
        for temoin in ("l_01", "l_02", "l_04", "b_02b", "b_05"):
            getattr(self, temoin)(variante)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n in MUTANTS}
assert len(_GENERES) == len(MUTANTS), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(LivraisonMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


if __name__ == "__main__":
    unittest.main()
