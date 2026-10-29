"""LA VOIE DIRECTE — comportement (`tasks.py direct`, `refus_direct`, jambes `start`/`done`).

T-00001178, décisions S-00004109, S-00004114, S-00004135, S-00004146. ZÉRO APPEL LLM.

Chaque témoin `w_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`
(`test_w*`), ou une COPIE JETABLE dont un fragment littéral, présent UNE fois
(asserté), est remplacé — forme de `MUTANTS_JAMBE` (test_binome_guard.py). Chaque
mutant de `MUTANTS` ne rejoue QUE le témoin qui le tue, et doit le faire échouer
par une ASSERTION (un mutant qui fait planter le témoin est un défaut du banc,
jamais un mutant tué). Dépôt jetable par témoin (`tempfile`, sous `TMPDIR`), CLI
en sous-processus, SPECS et traces de fixture ; `CLAUDE_PROJECT_DIR` retiré de
l'environnement des sous-processus. Le pont V3 se construit sur le vrai `bin`
(comme tous les bancs du board), jamais sur une copie (pas d'`agentic_v3` à côté).

Témoins : W1 start direct sous chaîne armée ; W2 frontière 5/6 ; W3 aucune
inférence ; W4 instantané rejoué ; W6 la cible R3 cède ; W7 un plan résolu est
contrôlé ; W8 aucune consommation ; W8b l'emprunt de groupe ne dispense pas ;
W9 le binôme mord ; W10 inerte désarmé ; W11 seuil unique de kickoff_guard ;
W11b une garde touchée arme, estampillée ou non (décision (a) du binôme ter) ;
W11c une estampillée sortie de son instantané est armée (F1 du binôme de clôture) ; W12/W12b/W12c décision et motifs ; W13/W14
exemption de la tâche seule ; W15 bornage ; W16 SPECS illisible ; W17 sécurité ;
W18 rejeu au `done` ; W20 toutes les causes ; W21 `--retirer` ; W21b une chaîne
franchie ne s'efface ni en ré-estampillant ni par `--retirer`, `running` ou `blocked` ;
W21c ni sur une franchie rétrogradée en `pending` ; W21d le remède d'une franchie
ne propose pas `--retirer` (binôme quater) ; W22 la marque
survit ; W23 persistance ; W28 rien du kit dans ce qui voyage ; W29 C6, tâche close, et son
remède ; W30 aucune
marque DIRECT héritée d'un cycle clos (F2), ni par `reopen` (W30b) ; W31 une seule marque (F3) ; W32
la marque dit les deux comptes, courant et validé ; W33 C1 refuse un lien
symbolique ; W34 une panne de `evaluer_done` ne masque pas les causes directes. La liste de garde
(W5, W19, W27) vit dans `test_direct_mode_garde.py`.

LA JAMBE RETOUR (T-00001182) : un témoin qui CLÔT une directe sous garde armée passe
d'abord par `Banc.releve` (branche, `tasks.py retour`, `git merge --no-ff`, verdict de
sécurité GO) — W6 W7 W21b W21c W22 W29 W30 W30b W31 ; W4 exige que le refus de son
`done` nomme C5 ; W23 dit l'inverse en dépôt désarmé (aucun relevé). La jambe elle-même
est éprouvée par `test_retour_done_guard.py`.

BORNE : ce banc éprouve le CODE ; la prose qui répète le seuil est tenue par
`test_direct_mode_doctrine.py`. Ça empêche d'OUBLIER, pas de TRICHER.
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
# Le résolveur du kit, chargé PAR CHEMIN (patron v3prep) : la source de `ids.py` est le paquet
# `cadre` de la racine, où qu'il vive (`.agents/vendor/cadre` ou `src/cadre`).
_SPEC_VENDOR = importlib.util.spec_from_file_location("_direct_mode_vendor_paths", BIN / "vendor_paths.py")
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)

#: Les fichiers copiés pour une variante : la façade et ses parties, les frères
#: qu'elles chargent, et ceux de `kickoff_guard` (W11).
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "specs.py",
          "kickoff_guard.py", "events.py")
SPEC = "# Spec du banc\n\n**« contrat déclaré »** — le contrat du banc.\n"
CINQ = ["src/a.py", "src/b.py", "src/c.py", "docs/d.md", "docs/e.md"]
SIX = CINQ + ["docs/f.md"]
ID_DU_KIT = re.compile(r"\b[TS]-\d{3,}")
#: Corps ULID FIXES (T-00000726, étape 7bis) : U_LETTER < U_DIGIT dans l'ordre de frappe.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}


def _maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def copie(case: unittest.TestCase, source: Path, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable de `source` (dossier bin), chaque ancre remplacée UNE fois."""
    base = Path(tempfile.mkdtemp(prefix="direct-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in source.glob(motif):
            shutil.copy2(f, dest / f.name)
    # FRÈRES D'ALLOCATION (plan T-00000726, E13/E25) : cette copie ALLOUE (`new`), elle porte donc
    # `record_id.py` et le générateur `<base>/src/cadre/ledger/ids.py`, comme tout harnais qui alloue.
    # Copie INCONDITIONNELLE : un frère absent fait échouer le montage, jamais sauter le
    # provisionnement en silence (un glob de COPIES, lui, sauterait sans rien dire).
    shutil.copy2(source / "record_id.py", dest / "record_id.py")
    generateur = base / "src" / "cadre" / "ledger"
    generateur.mkdir(parents=True)
    # Destination : le repli `src/cadre` du `record_id.py` copié (COPIES ne porte pas `vendor_paths.py`).
    shutil.copy2(_VENDOR.exiger(ROOT, "cadre") / "ledger" / "ids.py", generateur / "ids.py")
    for nom, paires in mutations.items():
        cible = dest / nom
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            case.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente dans {nom} : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
    return dest


def charger(bin_: Path):
    """Le module `tasks` de `bin_`, chargé sous un nom unique (lecture de constantes)."""
    nom = f"tasks_direct_banc_{abs(hash(str(bin_)))}"
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, bin_ / "tasks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


class Banc:
    """Un dépôt jetable et la CLI de `bin_` braquée dessus."""

    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin = case, bin_
        self.d = Path(tempfile.mkdtemp(prefix="direct-"))
        case.addCleanup(shutil.rmtree, self.d, True)
        # un état machine par banc : sans lui, le CADRE_STATE_DIR DE SESSION (conftest.py) loge
        # toutes les partitions du fichier ; sous Linux un inode recyclé (mkdtemp après rmtree)
        # les apparente par J1 (run_export.py), et le bloc PARTITION D'ÉTAT APPARENTÉE cite un T-… (w_28)
        self.etat = Path(tempfile.mkdtemp(prefix="direct-etat-"))
        case.addCleanup(shutil.rmtree, self.etat, True)
        for sous in ("board", "gates", "local/plan", "local/binome", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        # C7 (T-00001182) : `HOME` et `XDG_CONFIG_HOME` jetables, comme le `Depot` de
        # T-1184 — la config git de l'utilisateur reste hors du banc, `GIT_*` hérités retirés.
        maison = Path(tempfile.mkdtemp(prefix="direct-home-"))
        case.addCleanup(shutil.rmtree, maison, True)
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@exemple.invalid\n", encoding="utf-8")
        self.env = {k: v for k, v in _env().items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                        CADRE_STATE_DIR=str(self.etat), GIT_AUTHOR_NAME="banc", GIT_AUTHOR_EMAIL="banc@exemple.invalid",
                        GIT_COMMITTER_NAME="banc", GIT_COMMITTER_EMAIL="banc@exemple.invalid")

    def t(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=120, env=self.env)

    def g(self, *args: str) -> str:
        """git dans le dépôt du banc ; un échec est un DÉFAUT DU BANC (`RuntimeError`), jamais une assertion."""
        r = subprocess.run(["git", *args], cwd=self.d, env=self.env, capture_output=True, text=True,
                           timeout=120, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
        return r.stdout

    def releve(self, tid: str) -> None:
        """Le geste d'une directe CLOSE sous garde armée (T-00001182) : dépôt git (à la
        première fois), branche portant le write-set, RETOUR sur `main` AVANT `tasks.py
        retour`, relevé, `git merge --no-ff`, puis un verdict « security-code-review : GO »
        AJOUTÉ au SPECS au-delà de la borne du relevé. À appeler AVANT le `done`."""
        if not (self.d / ".git").exists():
            self.g("init", "-q", "-b", "main")
            (self.d / ".git" / "info" / "exclude").write_text(".agents/\n", encoding="utf-8")
            (self.d / "LISEZMOI").write_text("banc\n", encoding="utf-8")
            self.g("add", "-A")
            self.g("commit", "-q", "-m", "base")
        base = self.g("rev-parse", "--verify", "HEAD^{commit}").strip()
        branche, chemins = f"wt/{tid}", self.tache(tid)["writeset"]
        self.g("switch", "-q", "-c", branche)
        for chemin in chemins:
            (self.d / chemin).parent.mkdir(parents=True, exist_ok=True)
            (self.d / chemin).write_text(f"livré par {tid}\n", encoding="utf-8")
        self.g("add", "--", *chemins)
        self.g("commit", "-q", "-m", f"dev {tid}")
        self.g("switch", "-q", "main")
        self.ok("retour", tid, "--base", base, "--branche", branche)
        self.g("merge", "-q", "--no-ff", "-m", f"fusion {branche}", branche)
        borne = self.tache(tid)["retour"]["specs_borne"]
        chemin = self.d / ".agents" / "state" / "specs" / "SPECS.json"
        entrees = json.loads(chemin.read_text(encoding="utf-8"))["entries"] if chemin.is_file() else []
        # Au-delà de la borne, par `sort_key` (C1 de S-00004755), jamais `int(borne[2:])`, qui
        # lève sur un ULID. Seul l'étage 0 (borne ancienne) sert ici : une borne ULID est
        # ASSERTÉE hors champ, jamais servie par une branche que rien n'exerce.
        etage, valeur = charger(self.bin).sort_key(borne)
        self.case.assertEqual(0, etage, f"Banc.releve : borne ULID {borne} non prévue ici — "
                                        "couverture ULID : d_23 de test_retour_done_guard.py")
        sid = f"S-{valeur + 1:08d}"
        self.specs(entrees + [entree(sid, tid, "verdict", "security-code-review : GO")])

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        self.case.assertEqual(r.returncode, 0, f"{args} : {r.stdout}{r.stderr}")
        return r

    def nouvelle(self, titre: str = "tâche de banc", chemins: list[str] | None = None,
                 motif: str | None = None) -> str:
        extra = ["--mesure", "rejoue => observé", "--motif", motif] if motif else []
        r = self.ok("new", titre, *extra)
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        self.case.assertIsNotNone(trouve, r.stdout)
        tid = trouve.group(1)
        if chemins:
            self.ok("writeset", tid, *chemins)
        return tid

    def armer(self, nom: str, contenu: str = "") -> None:
        (self.d / ".agents" / "state" / "gates" / nom).write_text(contenu, encoding="utf-8")

    def armer_cible(self) -> None:
        (self.d / "docs").mkdir(exist_ok=True)
        (self.d / "docs" / "spec.md").write_text(SPEC, encoding="utf-8")
        self.armer("PLAN_CIBLE_REQUIRED", "spec=docs/spec.md\nchantier=*\n")

    def chaine(self) -> None:
        for nom, role in (("planner", "planner"), ("plan-critic", "reviewer")):
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": _maintenant(), "sha": "abc", "role": role}), encoding="utf-8")

    def traces(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in (self.d / ".agents" / "state" / "local" / "plan").glob("*.json")}

    def journal(self) -> str:
        p = self.d / ".agents" / "state" / "local" / "plan-chain-consommations.log"
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def specs(self, entrees: list[dict] | None = None, brut: bytes | None = None) -> None:
        chemin = self.d / ".agents" / "state" / "specs" / "SPECS.json"
        chemin.write_bytes(brut if brut is not None else json.dumps({"entries": entrees or []}).encode())

    def board_sha(self) -> str:
        return hashlib.sha256((self.d / ".agents" / "state" / "board" / "TASKS.json").read_bytes()).hexdigest()

    def renommer(self, tid: str, nouveau: str) -> None:
        """Re-nomme `tid` au board du banc, à la main (fixture, comme `forger` dans
        test_retour_done_guard.py) — pour un témoin qui exige un id ANCIEN gelé, valide à
        jamais (T-00000726), quel que soit l'allocateur de `new`."""
        chemin = self.d / ".agents" / "state" / "board" / "TASKS.json"
        data = json.loads(chemin.read_text(encoding="utf-8"))
        tache = next(t for t in data["tasks"] if t["id"] == tid)
        tache["id"] = nouveau
        chemin.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def tache(self, tid: str) -> dict:
        r = self.ok("list", "--task", tid, "--json")
        return json.loads(r.stdout)[0]


def entree(sid: int | str, tid: str, kind: str, titre: str, texte: str = "") -> dict:
    """Une entrée SPECS ; `sid` entier ⇒ l'ancienne forme `S-<8 chiffres>`, chaîne ⇒ telle quelle (un `S-<ULID>`)."""
    return {"id": sid if isinstance(sid, str) else f"S-{sid:08d}", "task": tid, "kind": kind, "title": titre,
            "text": texte, "files": [], "date": "2026-10-05"}


def court(tid: str) -> str:
    """La graphie COURTE d'un id ancien (`T-00000001` → `T-1`). Un `T-<ULID>`
    (T-00000726) n'a pas de forme courte : il est rendu TEL QUEL (R-BANCS (ii)) —
    `int()` levait `ValueError` sur ses lettres. Le test ULID passe AVANT, comme dans
    `tasks.sort_key` : 26 symboles tout en chiffres restent un ULID."""
    if re.fullmatch(r"T-[0-9A-HJKMNP-TV-Z]{26}", tid):
        return tid
    return f"T-{int(tid[2:])}"


_SONDE_KG = ("import json, sys; sys.path.insert(0, sys.argv[1]); import kickoff_guard as k; "
             "b = k.BoardReading(tasks_by_id=json.loads(sys.argv[2])); "
             "print(json.dumps({'seuil': k.SEUIL_CLASSE, 'armees': list(k.armed_by_class(b))}))")


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    # -- W1 W2 W3 W4 : start, frontière, inférence, instantané ---------------
    def w_01(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        autre = b.nouvelle("autre")
        b.ok("start", autre, "--sans-chaine", "banc")
        tid = b.nouvelle("cinq fichiers", CINQ)
        b.ok("direct", tid)
        r = b.t("start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[DIRECT SANS PLAN : 5 fichier(s)", b.tache(tid)["stage"])
        # T-01M5F7286N1EYGXAXA5244X86B : un `start` ne rétrograde plus personne, direct compris.
        self.assertEqual(b.tache(autre)["state"], "running", "le start d'une directe a rétrogradé l'autre running")

    def w_02(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        six = b.nouvelle("six", SIX)
        avant = b.board_sha()
        r = b.t("direct", six)
        self.assertNotEqual(r.returncode, 0, "6 chemins estampillés")
        self.assertIn("C1", r.stderr)
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")
        cinq = b.nouvelle("cinq", CINQ)
        r = b.t("direct", cinq)
        self.assertEqual(r.returncode, 0, r.stderr)

    def w_03(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        nu = b.nouvelle("sans write-set")
        r = b.t("direct", nu)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucun write-set déclaré", r.stderr)
        b.armer("PLAN_CHAIN_REQUIRED")
        deux = b.nouvelle("deux chemins non estampillés", ["src/a.py", "src/b.py"])
        r = b.t("start", deux)
        self.assertNotEqual(r.returncode, 0, "une tâche NON estampillée a démarré sans chaîne")
        self.assertIn("tasks.py direct", r.stderr)

    def w_04(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        b.armer_cible()
        for nouveaux in (SIX, CINQ[:4] + ["docs/hors.md"]):
            tid = b.nouvelle("instantané", CINQ)
            b.ok("direct", tid)
            b.ok("writeset", tid, *nouveaux)
            r = b.t("start", tid)
            self.assertNotEqual(r.returncode, 0, f"start après croissance {nouveaux}")
            self.assertIn("C5", r.stderr)
            r = b.t("done", tid, "--raison", "fin")
            self.assertNotEqual(r.returncode, 0, f"done après croissance {nouveaux}")
            # T-00001182 : la jambe retour refuserait aussi ce `done` (aucun relevé) ; le
            # refus doit venir du rejeu C5, sinon le mutant « C5 retiré au done » survit.
            self.assertIn("C5", r.stderr, f"le done ne rejoue pas C5 après croissance {nouveaux}")

    # -- W6 W7 : la cible -----------------------------------------------------
    def w_06(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.nouvelle("sans plan", ["src/a.py"])
        b.ok("direct", tid)
        b.releve(tid)
        r = b.t("done", tid, "--raison", "livré")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[DIRECT SANS PLAN : 1 fichier(s)", b.tache(tid)["stage"])
        self.assertNotIn("SANS CIBLE", b.tache(tid)["stage"])

    def w_07(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.nouvelle("plan fautif", ["src/a.py"])
        b.ok("direct", tid)
        plan = (f"# PLAN — {tid} — banc\nTâches : {tid}\n\n### Étape 1 — un geste\n"
                "cible: « contrat déclaré »\n\n### Étape 2 — sans cible\nrien ici\n")
        (b.d / "docs" / "tasks").mkdir(parents=True)
        (b.d / "docs" / "tasks" / "plan.md").write_text(plan, encoding="utf-8")
        sha = hashlib.sha256((b.d / "docs" / "tasks" / "plan.md").read_bytes()).hexdigest()
        b.specs([entree(10, tid, "decision", "plan approuvé", f"plan=docs/tasks/plan.md sha256={sha}")])
        b.releve(tid)  # T-00001182 : sans lui, la jambe retour masquerait le mutant « bypass avant resoudre_plan »
        r = b.t("done", tid, "--raison", "livré")
        self.assertNotEqual(r.returncode, 0, "un plan approuvé fautif a été franchi par l'estampille")

    # -- W8 W8b : aucune consommation, aucun emprunt --------------------------
    def w_08(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        b.chaine()
        a = b.nouvelle("A estampillée", ["src/a.py"])
        b.ok("direct", a)
        avant = b.traces()
        r = b.t("start", a)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[DIRECT SANS PLAN", b.tache(a)["stage"])
        self.assertEqual(b.traces(), avant, "les traces de chaîne ont bougé")
        self.assertNotIn(a, b.journal(), "une directe a été journalisée comme consommation")
        self.assertNotIn("plan_chain_consumed", b.tache(a))
        nb = b.nouvelle("B planifiée", ["src/b.py"])
        r = b.t("start", nb)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(nb, b.journal())

    def w_08b(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        a = b.nouvelle("porteur", ["src/a.py"])
        bb = b.nouvelle("estampillée", ["src/b.py"])
        b.ok("direct", bb)
        b.ok("writeset", bb, ".claude/hooks/x.sh")
        b.ok("parallel", a, bb)
        b.armer("PLAN_CHAIN_REQUIRED")
        b.chaine()
        b.ok("start", a)
        self.assertTrue(b.tache(a).get("plan_chain_consumed"))
        r = b.t("start", bb)
        self.assertNotEqual(r.returncode, 0, "l'emprunt de groupe a dispensé une estampillée du contrôle")
        self.assertIn("C2", r.stderr)

    # -- W9 W10 : binôme, désarmé ----------------------------------------------
    def w_09(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("BINOME_REQUIRED")
        b.armer_cible()
        tid = b.nouvelle("binôme", ["src/a.py"])
        b.ok("direct", tid)
        r = b.t("done", tid, "--raison", "livré")
        self.assertNotEqual(r.returncode, 0, "l'estampille a franchi le binôme")
        self.assertIn("REVUE CRITIQUE", r.stderr)

    def w_10(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("désarmé", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        b.ok("done", tid, "--raison", "fin")
        self.assertNotIn("DIRECT", b.tache(tid)["stage"])
        grandi = b.nouvelle("désarmé grandi", ["src/a.py"])
        b.ok("direct", grandi)
        b.ok("writeset", grandi, *SIX)
        r = b.t("start", grandi)
        self.assertEqual(r.returncode, 0, "un dépôt désarmé a rejoué l'estampille")
        self.assertNotIn("DIRECT", b.tache(grandi)["stage"])

    # -- W11 W11b : kickoff_guard ---------------------------------------------
    def sonde(self, bin_: Path, taches: dict) -> dict:
        r = subprocess.run([sys.executable, "-c", _SONDE_KG, str(bin_), json.dumps(taches)],
                           capture_output=True, text=True, env=_env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def w_11(self, bin_: Path) -> None:
        taches = {"T-1": {"id": "T-1", "state": "running", "writeset": CINQ},
                  "T-2": {"id": "T-2", "state": "running", "writeset": SIX}}
        vu = self.sonde(bin_, taches)
        self.assertEqual(vu["armees"], ["T-2"], "5 chemins exacts armés, ou 6 non armés")
        quatre = copie(self, bin_, {"tasks_direct.py": [("MAX_FICHIERS_DIRECT = 5\n", "MAX_FICHIERS_DIRECT = 4\n")]})
        vu = self.sonde(quatre, taches)
        self.assertEqual(vu["seuil"], 4, "SEUIL_CLASSE ne suit pas MAX_FICHIERS_DIRECT")
        self.assertEqual(vu["armees"], ["T-1", "T-2"])
        b = Banc(self, quatre)
        tid = b.nouvelle("cinq sous 4", CINQ)
        self.assertNotEqual(b.t("direct", tid).returncode, 0, "`direct` ne suit pas la constante")

    def w_11b(self, bin_: Path) -> None:
        trois = ["src/a.py", "src/b.py", ".claude/hooks/x.sh"]
        nu = {"T-1": {"id": "T-1", "state": "running", "writeset": trois}}
        self.assertEqual(self.sonde(bin_, nu)["armees"], ["T-1"], "une garde touchée n'arme pas")
        # Binôme ter, décision (a) : estampillée ou non — même un instantané qui
        # couvre le write-set courant n'exempte pas (la liste de garde grandit).
        tamponne = {"T-1": {"id": "T-1", "state": "running", "writeset": trois,
                            "direct": {"writeset": trois, "le": "2026-10-05"}}}
        self.assertEqual(self.sonde(bin_, tamponne)["armees"], ["T-1"], "une estampille exempte encore la garde")

    def w_11c(self, bin_: Path) -> None:
        """F1 du binôme : une estampillée sortie de son instantané vers une garde est armée."""
        derive = {"T-1": {"id": "T-1", "state": "running", "writeset": ["docs/a.md", ".claude/hooks/x.sh"],
                          "direct": {"writeset": ["docs/a.md"], "le": "2026-10-05"}}}
        self.assertEqual(self.sonde(bin_, derive)["armees"], ["T-1"],
                         "une estampillée sortie de son instantané vers une garde n'est pas armée")

    # -- W12 W12b W12c : décision ouverte, motifs -------------------------------
    def w_12(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        for titre in ("OPTION A ou B pour X", "Décision sur X", "DECISION sur X", "décision sur X"):
            tid = b.nouvelle(titre, ["src/a.py"])
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"titre admis : {titre}")
            self.assertIn("C3", r.stderr)
        tid = b.nouvelle("neutre", ["src/a.py"])
        b.ok("stage", tid, "à trancher : le format")
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "stage « à trancher » admis")

    def w_12b(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("neutre", ["docs/foo.md"], motif="decision-pilote")
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "motif decision-pilote admis")
        self.assertIn("C3", r.stderr)

    def w_12c(self, bin_: Path) -> None:
        attendu = {"garde": "C2", "securite": "C4", "decision-pilote": "C3", "gros": "C1"}
        motifs = charger(bin_).MOTIFS
        self.assertEqual(set(motifs), set(attendu) | {"sans-fournee"}, "MOTIFS a bougé : relire la fermeture")
        b = Banc(self, bin_)
        for motif in motifs:
            tid = b.nouvelle("neutre", ["docs/foo.md"], motif=motif)
            r = b.t("direct", tid)
            if motif == "sans-fournee":
                self.assertEqual(r.returncode, 0, r.stderr)
            else:
                self.assertNotEqual(r.returncode, 0, f"motif admis : {motif}")
                self.assertIn(attendu[motif], r.stderr)
        sixieme = copie(self, bin_, {"tasks_mesure.py": [
            ('MOTIFS = ("garde", "securite", "decision-pilote", "gros", "sans-fournee")\n',
             'MOTIFS = ("garde", "securite", "decision-pilote", "gros", "sans-fournee", "inedit")\n'),
            ('    "sans-fournee": "found outside', '    "inedit": "x",\n    "sans-fournee": "found outside')]})
        b6 = Banc(self, sixieme)
        tid = b6.nouvelle("neutre", ["docs/foo.md"], motif="inedit")
        r = b6.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "un sixième motif est admis sans décision")
        self.assertIn("motif inconnu", r.stderr)

    # -- W13 W14 W15 : l'exemption et son bornage ------------------------------
    def w_13(self, bin_: Path) -> None:
        """La décision est classée sous la graphie COURTE (`T-7`) : c'est ce qui sépare
        `entrees_de` d'une égalité exacte d'id (mutant « égalité exacte d'id »). Un
        `T-<ULID>` n'a pas de forme courte (R-BANCS (ii)) : la tâche rendue par `new` est
        donc re-nommée en un id ANCIEN gelé, sans quoi, sous l'allocateur de C2, le témoin
        ne séparerait plus rien (mesuré sous le simulacre de C2 : mutant SURVIVANT)."""
        b = Banc(self, bin_)
        tid = b.nouvelle("option A retenue (DÉCISION PILOTE S-00000007)", ["src/a.py"])
        ancien = "T-00000007"
        b.renommer(tid, ancien)
        self.assertNotEqual(court(ancien), ancien, "précondition : l'id du témoin a une forme courte")
        b.specs([entree(7, court(ancien), "decision", "option A")])
        r = b.t("direct", ancien)
        self.assertEqual(r.returncode, 0, r.stderr)

    def w_14(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        autre = b.nouvelle("autre tâche")
        cas = {
            "décision d'une AUTRE tâche": ("option A (décision S-00000007)", [entree(7, autre, "decision", "x")]),
            "S- inexistant": ("option A (décision S-00000099)", []),
            "kind=delta": ("option A (décision S-00000007)", None),
            "autre segment": ("option A ou B ; décision pilote S-00000007", None),
        }
        for nom, (titre, entrees) in cas.items():
            tid = b.nouvelle(titre, ["src/a.py"])
            if entrees is None:
                kind = "delta" if nom == "kind=delta" else "decision"
                entrees = [entree(7, tid, kind, "x")]
            b.specs(entrees)
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"exemption à tort : {nom}")
            self.assertIn("C3", r.stderr)

    def w_15(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        for titre in ("paramètre optionnel", "lever une indécision"):
            tid = b.nouvelle(titre, ["src/a.py"])
            r = b.t("direct", tid)
            self.assertEqual(r.returncode, 0, f"{titre} : {r.stderr}")

    # -- W16 : SPECS illisible --------------------------------------------------
    def w_16(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("neutre", ["src/a.py"])
        formes = (b"", b'{"entries": [', b"\xff\xfe{}", b"[]", b'{"entries": {}}', b'{"entries": [1]}')
        for brut in formes:
            b.specs(brut=brut)
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"SPECS illisible admis : {brut!r}")
            self.assertIn("SPECS illisible", r.stderr)
        (b.d / ".agents" / "state" / "specs" / "SPECS.json").unlink()
        r = b.t("direct", tid)
        self.assertEqual(r.returncode, 0, f"SPECS absent refusé : {r.stderr}")

    # -- W17 W18 : sécurité, rejeu au done --------------------------------------
    def w_17(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("neutre", ["src/a.py"], motif="securite")
        self.assertNotEqual(b.t("direct", tid).returncode, 0, "motif securite admis")
        for titre in ("fuite de secret dans X", "CVE-2025-1"):
            tid = b.nouvelle(titre, ["src/a.py"])
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"titre admis : {titre}")
            self.assertIn("C4", r.stderr)
        tid = b.nouvelle("neutre", ["src/a.py"])
        autre = b.nouvelle("autre")
        nogo = entree(10, tid, "verdict", "security-code-review : NO_GO")
        b.specs([nogo])
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "dernier verdict NO_GO admis")
        self.assertIn("C4", r.stderr)
        self.assertIn("ou, verdict clos, fais retracer par `security-code-review` un verdict au vocabulaire fermé "
                      "(CLEAN, 0 HIGH)", r.stderr, "le remède C4 ne nomme pas la sortie d'un verdict clos")
        b.specs([nogo, entree(11, tid, "verdict", "security-code-review : GO")])
        r = b.t("direct", tid)
        self.assertEqual(r.returncode, 0, f"un GO plus récent refusé : {r.stderr}")
        # S-00004172, tranché du côté SÛR : le vocabulaire RÉEL, au titre ET au texte,
        # et un motif ouvert l'emporte toujours sur un jeton fermé.
        bloquant = entree(13, tid, "verdict", "security-code-review FINDINGS(code) — 1 HIGH")
        for verdict in (bloquant, entree(14, tid, "verdict", "security-code-review : NO GO"),
                        entree(16, tid, "verdict", "security-code-review FINDINGS(code) 2 HIGH, PoC clean, GO après fix"),
                        entree(17, tid, "verdict", "security-code-review GO", "1 HIGH classe 1 encore ouvert"),
                        entree(18, tid, "verdict", "security-code-review tour 2 : 1 nouveau HIGH"),
                        entree(19, tid, "verdict", "security-code-review HIGH @ 002011a6"),
                        # Binôme ter (T3) : chaque branche du motif a SON témoin, qu'elle seule refuse.
                        entree(21, tid, "verdict", "security-code-review porte rouge"),
                        entree(22, tid, "verdict", "security-code-review : le finding bloque le merge"),
                        entree(23, tid, "verdict", "security-code-review findings=2"),
                        entree(24, tid, "verdict", "security-code-review : 1 CRITICAL"),
                        entree(25, tid, "verdict", "security-code-review HIGH: 2"),
                        entree(26, tid, "verdict", "security-code-review : un HIGH ouvert"),
                        # Binôme quater (fable 3) : le féminin, aux deux branches qui comptent.
                        entree(27, tid, "verdict", "security-code-review : 1 nouvelle CRITICAL"),
                        entree(28, tid, "verdict", "security-code-review : une nouvelle HIGH ouverte")):
            b.specs([verdict])
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"verdict bloquant admis : {verdict['title']} / {verdict['text']}")
            self.assertIn("C4", r.stderr)
        for titre in ("security-code-review CLEAN — 0 HIGH", "security-code-review CLEAN : aucun HIGH, no HIGH @ abc1234",
                      "security-code-review CLEAN : 0 HIGH @ abc1234, pas de HIGH @ def5678"):
            b.specs([bloquant, entree(20, tid, "verdict", titre)])
            r = b.t("direct", tid)
            self.assertEqual(r.returncode, 0, f"un dernier verdict « {titre} » refusé : {r.stderr}")
        neutre = b.nouvelle("neutre bis", ["src/b.py"])
        b.specs([entree(12, autre, "verdict", "security-code-review : NO_GO")])
        r = b.t("direct", neutre)
        self.assertEqual(r.returncode, 0, f"NO_GO d'une AUTRE tâche refusé : {r.stderr}")

    def w_18(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.nouvelle("neutre", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("stage", tid, "décision ouverte : choisir A ou B")
        r = b.t("done", tid, "--raison", "fin")
        self.assertNotEqual(r.returncode, 0, "décision ouverte au stage non rejouée au done")
        self.assertIn("C3", r.stderr)
        b.ok("stage", tid, "en cours")
        b.specs([entree(10, tid, "verdict", "security-code-review : NO_GO")])
        r = b.t("done", tid, "--raison", "fin")
        self.assertNotEqual(r.returncode, 0, "verdict NO_GO non rejoué au done")
        self.assertIn("C4", r.stderr)

    # -- W20 W21 W22 W23 W28 ----------------------------------------------------
    def w_20(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("option A", CINQ + [".githooks/x"], motif="securite")
        avant = b.board_sha()
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0)
        for classe in ("C1", "C2", "C3", "C4"):
            self.assertRegex(r.stderr, rf"(?m)^  - {classe} ", f"cause {classe} absente")
        self.assertEqual(b.board_sha(), avant)

    def w_21(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("retrait", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("direct", tid, "--retirer")
        self.assertNotIn("direct", b.tache(tid))
        b.ok("direct", tid)
        b.ok("writeset", tid, "src/a.py", "src/z.py")
        b.armer("PLAN_CHAIN_REQUIRED")
        b.chaine()
        avant = b.traces()
        r = b.t("start", tid)
        self.assertNotEqual(r.returncode, 0, "estampille invalide : bascule silencieuse vers la chaîne")
        self.assertIn("--retirer", r.stderr)
        self.assertEqual(b.traces(), avant)
        b.ok("direct", tid, "--retirer")
        b.ok("start", tid)
        self.assertEqual(b.traces(), {}, "après --retirer, la chaîne n'a pas été consommée")
        self.assertIn(tid, b.journal())

    def w_21b(self, bin_: Path) -> None:
        """Binôme ter (T4), étendu au binôme quater (F1) : une chaîne franchie ne s'efface ni en
        ré-estampillant ni par `--retirer`, sur une tâche NON CLOSE — `running` puis `blocked`."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("franchie", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        franchie = b.tache(tid)["direct"].get("chaine_franchie")
        self.assertTrue(franchie, "précondition : la chaîne franchie au start")
        for etat in ("running", "blocked"):
            if etat == "blocked":
                b.ok("block", tid, "--note", "attente")
            self.assertEqual(b.tache(tid)["state"], etat, "précondition : l'état du tour")
            avant = b.board_sha()
            r = b.t("direct", tid, "--retirer")
            self.assertEqual(r.returncode, 2, f"--retirer admis après franchissement ({etat}) : {r.stdout}{r.stderr}")
            self.assertEqual(b.board_sha(), avant, f"un refus a écrit le board ({etat})")
            self.assertIn(f"tasks.py done {tid}", r.stderr, "le remède « done » n'est pas nommé")
            self.assertIn("tasks.py reopen", r.stderr, "le remède « reopen puis --retirer » n'est pas nommé")
            b.ok("direct", tid)
            self.assertEqual(b.tache(tid)["direct"].get("chaine_franchie"), franchie,
                             f"ré-estampiller a effacé chaine_franchie ({etat})")
        b.releve(tid)  # C2 (S-00004199) : la jambe retour mord sur ce `done`
        b.ok("done", tid, "--raison", "fin")
        self.assertIn("[DIRECT SANS PLAN", b.tache(tid)["stage"])

    def w_21c(self, bin_: Path) -> None:
        """Binôme quater (F1) : une franchie RÉTROGRADÉE en `pending` — par une sortie EXPLICITE de
        `running` (`block` puis `unblock`) : le `start` d'une autre ne rétrograde plus
        (T-01M5F7286N1EYGXAXA5244X86B) — garde sa chaîne franchie — `--retirer` refusé, board
        inchangé, la marque au `done`."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        a = b.nouvelle("franchie A", ["src/a.py"])
        autre = b.nouvelle("franchie B", ["src/b.py"])
        b.ok("direct", a)
        b.ok("direct", autre)
        b.ok("start", a)
        b.ok("start", autre)
        self.assertEqual(b.tache(a)["state"], "running", "le start de B a rétrogradé A")
        b.ok("block", a, "--note", "sortie explicite")
        b.ok("unblock", a)
        self.assertEqual(b.tache(a)["state"], "pending", "précondition : A sortie de running")
        franchie = b.tache(a)["direct"].get("chaine_franchie")
        self.assertTrue(franchie, "précondition : A garde sa chaîne franchie")
        avant = b.board_sha()
        r = b.t("direct", a, "--retirer")
        self.assertEqual(r.returncode, 2, f"--retirer admis sur une franchie rétrogradée : {r.stdout}{r.stderr}")
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")
        b.ok("direct", a)
        self.assertEqual(b.tache(a)["direct"].get("chaine_franchie"), franchie,
                         "ré-estampiller une franchie rétrogradée a effacé chaine_franchie")
        b.releve(a)  # T-00001182 : la franchie rétrogradée passe aussi par la jambe retour
        b.ok("done", a, "--raison", "fin")
        self.assertIn("[DIRECT SANS PLAN", b.tache(a)["stage"], "franchie rétrogradée close sans marque")

    def w_21d(self, bin_: Path) -> None:
        """Binôme quater (fable 2) : sur une franchie, le remède d'un refus au `start` (rejeu C5)
        et au `done` (C3) ne propose pas `--retirer`, qu'elle refuserait — il dit `done`, puis
        `reopen` et `--retirer`."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("franchie", ["src/a.py"])
        autre = b.nouvelle("autre", ["src/b.py"])
        b.ok("direct", tid)
        b.ok("direct", autre)
        b.ok("start", tid)
        b.ok("start", autre)  # ne rétrograde plus `tid` (T-01M5F7286N1EYGXAXA5244X86B), qui garde sa chaîne franchie
        b.ok("writeset", tid, "src/a.py", "src/z.py")
        r = b.t("start", tid)
        self.assertNotEqual(r.returncode, 0, "précondition : C5 refuse le rejeu")
        self.assertIn("C5", r.stderr)
        self.assertNotIn(f"tasks.py direct {tid} --retirer", r.stderr, "le remède au start propose un --retirer refusé")
        self.assertIn("puis `reopen` et `--retirer`", r.stderr, "le remède de la franchie n'est pas nommé au start")
        b.armer_cible()
        cible = b.nouvelle("franchie au done", ["src/c.py"])
        b.ok("direct", cible)
        b.ok("start", cible)
        self.assertTrue(b.tache(cible)["direct"].get("chaine_franchie"), "précondition : la chaîne franchie")
        b.ok("stage", cible, "décision ouverte : choisir A ou B")
        r = b.t("done", cible, "--raison", "fin")
        self.assertNotEqual(r.returncode, 0, "précondition : C3 refuse le done")
        self.assertIn("C3", r.stderr)
        self.assertNotIn(f"tasks.py direct {cible} --retirer", r.stderr, "le remède au done propose un --retirer refusé")
        self.assertIn("puis `reopen` et `--retirer`", r.stderr, "le remède de la franchie n'est pas nommé au done")

    def w_22(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("marque", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        b.releve(tid)
        b.ok("done", tid, "--raison", "x")
        stage = b.tache(tid)["stage"]
        self.assertTrue(stage.startswith("x "), stage)
        self.assertIn("[DIRECT SANS PLAN : 1 fichier(s)", stage)

    def w_23(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.nouvelle("persistance", ["src/a.py"])
        b.ok("direct", tid)
        for geste in (("stage", tid, "x"), ("start", tid), ("done", tid, "--raison", "fin"),
                      ("reopen", tid, "--raison", "rouvrir")):
            b.ok(*geste)
            self.assertIn("direct", b.tache(tid), f"clé perdue après {geste[0]}")
            if geste[0] == "done":  # T-00001182 : dépôt désarmé, done admis sans relevé, rien d'inscrit
                self.assertNotIn("retour", b.tache(tid), "un done désarmé a exigé ou inscrit un relevé")
        self.assertEqual(b.tache(tid)["direct"]["writeset"], ["src/a.py"])

    # -- W29 : C6, tâche close -------------------------------------------------
    def w_29(self, bin_: Path) -> None:
        """F5 : une tâche close refuse la voie directe (C6) ; le refus nomme le remède exact."""
        b = Banc(self, bin_)
        tid = b.nouvelle("close", ["src/a.py"])
        b.ok("start", tid)
        b.ok("done", tid, "--raison", "fin")
        avant = b.board_sha()
        r = b.t("direct", tid)
        self.assertNotEqual(r.returncode, 0, "une tâche close estampillée")
        self.assertIn("C6", r.stderr)
        self.assertIn(f"tasks.py reopen {tid} --raison", r.stderr, "le remède de C6 n'est pas nommé")
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")
        # Hors estampillage : `start` depuis `done`, chaîne armée — rejeu avec C6.
        b.armer("PLAN_CHAIN_REQUIRED")
        cycle = b.nouvelle("cycle", ["src/b.py"])
        b.ok("direct", cycle)
        b.ok("start", cycle)
        b.releve(cycle)
        b.ok("done", cycle, "--raison", "fin")
        r = b.t("start", cycle)
        self.assertNotEqual(r.returncode, 0, "une estampillée close a redémarré sans être rouverte")
        self.assertIn("C6", r.stderr)
        self.assertIn(f"tasks.py reopen {cycle} --raison", r.stderr, "le remède de C6 n'est pas nommé au start")
        self.assertNotIn(f"tasks.py direct {cycle}", r.stderr, "le refus C6 au start propose encore de ré-estampiller")
        b.ok("reopen", cycle, "--raison", "x")
        b.ok("start", cycle)

    # -- W30 W31 : la marque dit l'ÉTAT (binôme de clôture, F2 et F3) -----------
    def w_30(self, bin_: Path) -> None:
        """F2 : aucune marque DIRECT héritée d'un cycle clos — SANS `reopen`, qui
        retire lui aussi `chaine_franchie` : seul le `start` peut la retirer ici."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("cycle", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        b.releve(tid)
        b.ok("done", tid, "--raison", "premier")
        self.assertIn("[DIRECT SANS PLAN", b.tache(tid)["stage"], "précondition : la marque du premier cycle")
        (b.d / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").unlink()
        b.ok("start", tid)
        b.ok("done", tid, "--raison", "second")
        self.assertNotIn("DIRECT", b.tache(tid)["stage"], "marque DIRECT héritée d'un cycle clos")

    def w_30b(self, bin_: Path) -> None:
        """Binôme ter (T1) : `reopen` puis `done` sans `start` ne reprend pas la marque du cycle clos."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("rouverte", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        b.releve(tid)  # C2 (S-00004199) : le premier cycle franchit la chaîne, la jambe retour mord
        b.ok("done", tid, "--raison", "premier")
        self.assertIn("[DIRECT SANS PLAN", b.tache(tid)["stage"], "précondition : la marque du premier cycle")
        b.ok("reopen", tid, "--raison", "x")
        self.assertIn("direct", b.tache(tid), "reopen a perdu l'estampille")
        b.ok("done", tid, "--raison", "y")
        self.assertNotIn("DIRECT", b.tache(tid)["stage"], "reopen puis done : marque du cycle clos reprise")

    def w_31(self, bin_: Path) -> None:
        """F3, S-00004175 (1) : la jambe directe efface la dérogation — une seule marque."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("coquille", ["src/a.py"])
        b.ok("start", tid, "--sans-chaine", "coquille")
        b.ok("direct", tid)
        autre = b.nouvelle("autre")
        b.ok("start", autre, "--sans-chaine", "banc")
        self.assertEqual(b.tache(tid)["state"], "running", "le start d'une autre a rétrogradé la coquille")
        b.ok("block", tid, "--note", "sortie explicite")  # T-01M5F7286N1EYGXAXA5244X86B : sortie EXPLICITE
        b.ok("unblock", tid)
        self.assertEqual(b.tache(tid)["state"], "pending", "précondition : sortie de running")
        b.ok("start", tid)
        self.assertNotIn("sans_chaine", b.tache(tid), "la jambe directe a gardé la dérogation")
        b.releve(tid)
        b.ok("done", tid, "--raison", "fin")
        stage = b.tache(tid)["stage"]
        self.assertIn("[DIRECT SANS PLAN", stage)
        self.assertNotIn("SANS CHAÎNE", stage, "deux marques au done")

    def w_32(self, bin_: Path) -> None:
        """S-00004175 (2) : la marque dit le write-set COURANT et l'instantané VALIDÉ."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("rétréci", CINQ[:3])
        b.ok("direct", tid)
        b.ok("writeset", tid, CINQ[0])
        b.ok("start", tid)
        self.assertIn("[DIRECT SANS PLAN : 1 fichier(s), 3 validé(s) par direct]", b.tache(tid)["stage"])

    # -- W33 W34 : trous du binôme (lien symbolique, panne au done) ---------------
    def w_33(self, bin_: Path) -> None:
        """C1 refuse un lien symbolique du write-set, et un chemin qui passe par un."""
        b = Banc(self, bin_)
        (b.d / "docs").mkdir(exist_ok=True)
        (b.d / "docs" / "vrai.md").write_text("x", encoding="utf-8")
        os.symlink("vrai.md", b.d / "docs" / "lien.md")
        os.symlink("docs", b.d / "rep")
        for chemin in ("docs/lien.md", "rep/vrai.md"):
            tid = b.nouvelle("neutre", [chemin])
            r = b.t("direct", tid)
            self.assertNotEqual(r.returncode, 0, f"lien symbolique admis : {chemin}")
            self.assertIn("lien symbolique", r.stderr)
        b.ok("direct", b.nouvelle("neutre", ["docs/vrai.md"]))

    def w_34(self, bin_: Path) -> None:
        """Une panne de `evaluer_done` (injectée sur copie) ne masque pas les causes directes."""
        panne = copie(self, bin_, {"plan_cible.py": [(_R3, '        raise CibleError("panne de banc")\n')]})
        b = Banc(self, panne)
        b.armer_cible()
        tid = b.nouvelle("neutre", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("stage", tid, "décision ouverte : choisir A ou B")
        r = b.t("done", tid, "--raison", "fin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("panne de banc", r.stderr, "précondition : la panne est jouée")
        self.assertIn("C3", r.stderr, "la panne a masqué les causes directes")

    # -- W35 W36 (T-00000726, étape 7bis) : C4 et C3 sous S-id ULID ---------------------
    def w_35(self, bin_: Path) -> None:
        """C4 sous ULID (E26, S1) : le DERNIER verdict de sécurité est celui de plus haute
        clé d'ORDRE (`sort_key` : tout ULID après tout ancien, les ULID par le temps). C4-1
        ancien CLEAN puis ULID NO_GO ⇒ refus ; C4-2 ULID CLEAN puis ULID NO_GO ⇒ refus ; C4-3
        ULID NO_GO puis ULID CLEAN ⇒ admis. Sous un rang `int` à -1 pour tout ULID, le
        PREMIER de la liste gagnait à égalité : l'ordre des fixtures le rend visible. MUTANT M42."""
        b = Banc(self, bin_)
        clean, nogo = "security-code-review CLEAN — 0 HIGH", "security-code-review : NO_GO"
        cas = (("C4-1", [(4745, clean), (f"S-{U_DIGIT}", nogo)], False),
               ("C4-2", [(f"S-{U_LETTER}", clean), (f"S-{U_DIGIT}", nogo)], False),
               ("C4-3", [(f"S-{U_LETTER}", nogo), (f"S-{U_DIGIT}", clean)], True))
        for nom, verdicts, admis in cas:
            tid = b.nouvelle(f"neutre {nom}", ["src/a.py"])
            b.specs([entree(sid, tid, "verdict", titre) for sid, titre in verdicts])
            r = b.t("direct", tid)
            if admis:
                self.assertEqual(r.returncode, 0, f"{nom} : un CLEAN plus récent refusé : {r.stderr}")
            else:
                self.assertNotEqual(r.returncode, 0, f"{nom} : un NO_GO plus récent admis")
                self.assertIn("C4 le dernier verdict de sécurité de la tâche est bloquant", r.stderr, nom)

    def w_36(self, bin_: Path) -> None:
        """C3 sous ULID (E26, S4) — C3-U : une décision tranchée SUR la tâche et citée par son
        `S-<ULID>` dans le MÊME segment exempte (le texte est normalisé en minuscules :
        `DIRECT_S_ID` lit `s-<ulid>`, `cites` le remet en MAJUSCULES contre les décisions) ;
        la MÊME décision tracée sur une AUTRE tâche n'exempte pas, et refuse par C3 ;
        l'ancien `S-<8 chiffres>` exempte toujours. MUTANTS M43 (`.upper()` retiré de
        `cites`), M44 (branche ULID retirée de `DIRECT_S_ID`)."""
        b = Banc(self, bin_)
        tid = b.nouvelle(f"option A (décision S-{U_LETTER})", ["src/a.py"])
        b.specs([entree(f"S-{U_LETTER}", tid, "decision", "option A")])
        r = b.t("direct", tid)
        self.assertEqual(r.returncode, 0, f"C3-U : la décision ULID de la tâche n'exempte pas : {r.stderr}")
        autre = b.nouvelle("autre tâche")
        refus = b.nouvelle(f"option B (décision S-{U_LETTER})", ["src/b.py"])
        b.specs([entree(f"S-{U_LETTER}", autre, "decision", "option B")])
        r = b.t("direct", refus)
        self.assertNotEqual(r.returncode, 0, "C3-U négatif : la décision d'une AUTRE tâche exempte")
        self.assertIn("C3 décision ouverte au titre", r.stderr)
        ancien = b.nouvelle("option C (décision S-00000007)", ["src/c.py"])
        b.specs([entree(7, ancien, "decision", "option C")])
        r = b.t("direct", ancien)
        self.assertEqual(r.returncode, 0, f"l'ancien S-<8 chiffres> n'exempte plus : {r.stderr}")

    def w_28(self, bin_: Path) -> None:
        self.assertEqual(charger(bin_).marque_directe(3, 2), "[DIRECT SANS PLAN : 3 fichier(s), 2 validé(s) par direct]")
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.nouvelle("clés", ["src/a.py"])
        b.ok("direct", tid)
        b.ok("start", tid)
        self.assertEqual(set(b.tache(tid)["direct"]), {"writeset", "le", "chaine_franchie"})
        sorties = [b.ok("direct", "--help").stdout]
        aide = " ".join(sorties[0].split())
        self.assertTrue(sorties[0].isascii(), "l'aide de direct n'est pas en ASCII pur (binôme quater, F2)")
        refus_retirer = ("refused on an open (not done) task whose start crossed the chain "
                         "(remedy: done, or reopen then --retirer)")
        for dit in ("`reopen` keeps the stamp", "--retirer is " + refus_retirer, "planned one; " + refus_retirer):
            self.assertIn(dit, aide, "l'aide de direct est muette sur reopen ou --retirer (binômes ter et quater)")
        for titre, chemins in (("six", SIX), ("garde", [".githooks/x"]), ("option A", ["src/a.py"]),
                               ("CVE-2025-1", ["src/a.py"])):
            refus = b.nouvelle(titre, chemins)
            r = b.t("direct", refus)
            self.assertNotEqual(r.returncode, 0)
            sorties.append(r.stderr)
        fixtures = {t["id"] for t in json.loads(b.ok("list", "--json").stdout)}
        for sortie in sorties:
            ids = set(ID_DU_KIT.findall(sortie)) - fixtures
            self.assertEqual(ids, set(), f"un id du kit voyage : {ids}")


#: Les mutants : `nom → ({fichier: [(ancre, remplacement)]}, témoin)`. Chaque
#: ancre est un FRAGMENT LITTÉRAL présent UNE fois (asserté par `copie`).
_ETATS, _DIRECT = "tasks_etats.py", "tasks_direct.py"
_DIRECTE = '            directe = not sans_chaine and chaine_armee and "direct" in task\n'
_EFFACE_DIR = ("                # la jambe directe efface la dérogation, comme la chaîne payée (B-3).\n"
               "                efface_derogation_chaine(task)\n")
_BLOC_START = _DIRECTE + ("            if directe:\n                marque_dir = direct_jambe_start(root, tid, task, today)\n"
                          "                # UNE SEULE MARQUE, L'ÉTAT (S-00004175 (1)) : la chaîne franchie par\n" + _EFFACE_DIR)
_R3 = '        return (_message_refus_r3(root, tid, data), "")\n'
_OUVERT = ('    r"\\bno[_ -]?go\\b|findings ?\\(code\\)|\\bfindings ?[=:]? ?[1-9]"\n'
           '    r"|\\b[1-9][0-9]* (?:nouveaux? |nouvelles? |new )?(?:high|critical)\\b"\n'
           '    r"|\\b(?:un|une|one) (?:nouveau |nouvelle |new )?(?:high|critical)\\b|\\b(?:high|critical) ?[:=] ?[1-9]"\n'
           '    r"|(?<!no )(?<!aucun )(?<!0 )(?<!de )\\b(?:high|critical) @|\\brouge\\b|\\bbloque\\b")\n')
_FRANCHIE = ("            if franchie:  # la chaîne franchie par le `start` en cours reste dite\n"
             '                task["direct"]["chaine_franchie"] = franchie\n')
_NON_CLOSE = '        franchie = (tampon.get("chaine_franchie") if task.get("state") != "done"\n'
_PANNE = ("        try:\n            refus_r3, _note = _pc.evaluer_done(root, tid, data)\n"
          "        except (_pc.CibleError, OSError, ValueError) as exc:  # une panne ne MASQUE pas les causes directes\n"
          "            refus_r3 = str(exc)\n")
_MARQUE = '    return f"[DIRECT SANS PLAN : {courant} fichier(s), {valides} validé(s) par direct]"\n'
_POP_FRANCHIE = ('            if not directe and isinstance(task.get("direct"), dict):\n'
                 '                task["direct"].pop("chaine_franchie", None)\n')
_REOPEN_FRANCHIE = ('        if isinstance(task.get("direct"), dict):\n'
                    '            task["direct"].pop("chaine_franchie", None)\n        # LA PREUVE DE REVUE')
_AU_DONE = "        causes_au_done = refus_direct(root, task, instantane=True)\n"
_SECU = "    causes += direct_causes_securite(task, taches_entrees)\n"
_ENTREES = "            entrees = _pc.entrees_specs(racine)\n"
#: 7bis (T-00000726) : le rang à deux étages, le `cites` remis en MAJUSCULES, et la grammaire ULID-première.
_RANG_DEUX_ETAGES = ('    if not re.fullmatch(r"S-(?:" + ULID_BODY + r"|[0-9]{1,15})", sid):\n'
                     "        return DIRECT_RANG_ILLISIBLE\n    return sort_key(sid)\n")
_RANG_INT = '    m = re.fullmatch(r"S-([0-9]+)", sid)\n    return int(m.group(1)) if m else -1\n'
_S_ID_ULID = 'DIRECT_S_ID = re.compile(r"\\bs-([0-9a-hjkmnp-tv-z]{26}|[0-9]{8})\\b")'
_KG_GARDE = "        if any(tasks.est_chemin_de_garde(e) for e in writeset):\n"
#: L'exemption par instantané d'avant la décision (a) du binôme ter, rétablie par un mutant.
_KG_TENU = ('        tampon = task.get("direct")\n'
            '        tenu = (isinstance(tampon, dict) and isinstance(tampon.get("writeset"), list)\n'
            "                and {tasks.canonical_writeset_path(p) for p in writeset}\n"
            '                <= {tasks.canonical_writeset_path(p) for p in tampon["writeset"] if isinstance(p, str)})\n')
MUTANTS = {
    "MAX_FICHIERS_DIRECT = 6": ({_DIRECT: [("MAX_FICHIERS_DIRECT = 5\n", "MAX_FICHIERS_DIRECT = 6\n")]}, "w_02"),
    "MAX_FICHIERS_DIRECT = 4": ({_DIRECT: [("MAX_FICHIERS_DIRECT = 5\n", "MAX_FICHIERS_DIRECT = 4\n")]}, "w_02"),
    "admission par inférence": ({_ETATS: [(_DIRECTE, _DIRECTE.replace(
        '"direct" in task\n', '("direct" in task or not refus_direct(root, task))\n'
        '            if directe:\n                task.setdefault("direct", {"writeset": writeset_of(task), "le": today})\n'))]},
        "w_03"),
    "C5 retiré au done": ({_DIRECT: [(_AU_DONE, _AU_DONE.replace("instantane=True", "instantane=False"))]}, "w_04"),
    "bypass avant resoudre_plan": ({_DIRECT: [("\n            and _pc.resoudre_plan(root, tid, data, slot=True) is None):", "):")]},
                                   "w_07"),
    "consommation avant le test direct": ({_ETATS: [("                and not directe\n", "")]}, "w_08"),
    "test après l'emprunt": ({_ETATS: [
        (_BLOC_START, _DIRECTE),
        ("            if bool(groupe_chaine) and not directe:\n", "            if bool(groupe_chaine):\n"),
        ("            if (\n                not sans_chaine\n                and chaine_armee\n",
         "            if directe and not emprunt_groupe:\n                marque_dir = direct_jambe_start(root, tid, task, today)\n"
         "                efface_derogation_chaine(task)\n"
         "            if (\n                not sans_chaine\n                and chaine_armee\n")]}, "w_08b"),
    "C6 retiré": ({_DIRECT: [('    if task.get("state") == "done":\n        causes.append(',
                              '    if False:\n        causes.append(')]}, "w_29"),
    "lien symbolique admis": ({_DIRECT: [("        elif direct_lien_symbolique(racine, brut):\n", "        elif False:\n")]},
                              "w_33"),
    "ancêtres du chemin non lus": ({_DIRECT: [("    courant = racine\n",
                                               "    return (racine / brut).is_symlink()\n    courant = racine\n")]}, "w_33"),
    "une panne au done masque les causes": ({_DIRECT: [(_PANNE, "        refus_r3, _note = _pc.evaluer_done(root, tid, data)\n")]},
                                            "w_34"),
    "chaine_franchie héritée d'un cycle clos (F2)": ({_ETATS: [(_POP_FRANCHIE, "")]}, "w_30"),
    "reopen garde chaine_franchie (T1 du binôme ter)": ({"tasks_verbes.py": [(_REOPEN_FRANCHIE, "        # LA PREUVE DE REVUE")]},
                                                         "w_30b"),
    "deux marques au done (F3)": ({_ETATS: [(_EFFACE_DIR, _EFFACE_DIR.replace("efface_derogation_chaine(task)", "pass"))]},
                                  "w_31"),
    "bypass avant le binôme": ({_ETATS: [('        if state == "done" and not sans_binome:\n',
                                          '        if state == "done" and not sans_binome and "direct" not in task:\n')]}, "w_09"),
    "marque inconditionnelle": ({_ETATS: [(_DIRECTE, '            directe = "direct" in task\n')]}, "w_10"),
    "SEUIL_CLASSE = 5 littéral": ({"kickoff_guard.py": [("SEUIL_CLASSE = tasks.MAX_FICHIERS_DIRECT\n", "SEUIL_CLASSE = 5\n")]},
                                  "w_11"),
    "branche de garde retirée (R5-2)": ({"kickoff_guard.py": [
        (_KG_GARDE + "            armees.append(tid)\n            continue\n", "")]}, "w_11b"),
    "exemption par instantané rétablie (avant la décision (a))": ({"kickoff_guard.py": [
        (_KG_GARDE, _KG_TENU + _KG_GARDE.replace("if any(", "if not tenu and any("))]}, "w_11b"),
    "l'estampille exempte sans rejouer l'instantané (F1)": ({"kickoff_guard.py": [
        (_KG_GARDE, _KG_GARDE.replace("if any(", 'if not isinstance(task.get("direct"), dict) and any('))]}, "w_11c"),
    "LEXIQUE_DECISION = ()": ({_DIRECT: [('LEXIQUE_DECISION = ("option", ', 'LEXIQUE_DECISION = () and ("option", ')]},
                              "w_12"),
    "sans normalisation des accents": ({_DIRECT: [('    return _normaliser_titre(texte if isinstance(texte, str) else "")\n',
                                                   '    return (texte if isinstance(texte, str) else "").casefold()\n')]}, "w_12"),
    "motif ignoré": ({_DIRECT: [('    motif = task.get("motif")\n', "    motif = None\n")]}, "w_12b"),
    "motif inconnu admis": ({_DIRECT: [("        if classe is None:\n            causes.append(",
                                        "        if classe is None:\n            pass\n        elif False:\n            causes.append(")]},
                            "w_12c"),
    "gros admis": ({_DIRECT: [('MOTIFS_ADMIS_DIRECT = ("sans-fournee",)', 'MOTIFS_ADMIS_DIRECT = ("sans-fournee", "gros")')]},
                   "w_12c"),
    "égalité exacte d'id au lieu de entrees_de": ({_DIRECT: [(
        '        taches_entrees = _pc.entrees_de(index, task.get("id"))\n',
        '        taches_entrees = [e for e in entrees if e.get("task") == task.get("id")]\n')]}, "w_13"),
    "exemption sur toutes les décisions": ({_DIRECT: [("        decisions = _pc.decisions_existantes(taches_entrees)\n",
                                                       "        decisions = _pc.decisions_existantes(entrees)\n")]}, "w_14"),
    "tout kind vaut": ({_DIRECT: [("        decisions = _pc.decisions_existantes(taches_entrees)\n",
                                   '        decisions = {e.get("id") for e in taches_entrees}\n')]}, "w_14"),
    "exemption sur le champ entier": ({_DIRECT: [("DIRECT_S_ID.findall(segment)}",
                                                  "DIRECT_S_ID.findall(direct_normaliser(texte))}")]}, "w_14"),
    "sans \\b": ({_DIRECT: [('        if re.search(r"\\b" + re.escape(mot) + r"\\b", texte):\n',
                             "        if re.search(re.escape(mot), texte):\n")]}, "w_15"),
    "SPECS lu seulement sous lexique": ({_DIRECT: [(_ENTREES, _ENTREES.replace(
        "_pc.entrees_specs(racine)\n",
        '_pc.entrees_specs(racine) if direct_porte_lexique(direct_normaliser(f"{task.get(\'task\')} '
        '{task.get(\'stage\')}"), LEXIQUE_DECISION + LEXIQUE_SECURITE) else []\n'))]}, "w_16"),
    "absent = refus": ({_DIRECT: [(_ENTREES, _ENTREES + "            if not (racine / _pc.SPECS_REL).is_file():\n"
                                   '                raise _pc.CibleError("absent")\n')]}, "w_16"),
    "C4 retiré": ({_DIRECT: [(_SECU, "")]}, "w_17"),
    "premier verdict": ({_DIRECT: [("max(verdicts, key=direct_rang_specs)", "min(verdicts, key=direct_rang_specs)")]}, "w_17"),
    "verdict de toute tâche": ({_DIRECT: [(_SECU, "    causes += direct_causes_securite(task, entrees or [])\n")]}, "w_17"),
    "C4 ne lit que NO_GO (avant S-00004172)": ({_DIRECT: [(_OUVERT, '    r"\\bno[_-]?go\\b")\n')]}, "w_17"),
    "« no go » espacé non lu": ({_DIRECT: [('r"\\bno[_ -]?go\\b|', 'r"\\bno[_-]?go\\b|')]}, "w_17"),
    "le fermé l'emporte (S-00004172 avant l'arbitrage)": ({_DIRECT: [(
        "            if ouvert:\n",
        '            if ouvert and not re.search(r"\\bclean\\b|\\bgo\\b|\\bpass\\b", direct_normaliser(dernier.get("title"))):\n')]},
        "w_17"),
    "titre seul": ({_DIRECT: [('        for champ, nom in (("title", "titre"), ("text", "texte")):\n',
                               '        for champ, nom in (("title", "titre"),):\n')]}, "w_17"),
    "« N nouveau HIGH » non lu": ({_DIRECT: [("(?:nouveaux? |nouvelles? |new )?", "")]}, "w_17"),
    # Binôme quater (fable 3) : le féminin, une branche à la fois.
    "« N nouvelle HIGH » non lu": ({_DIRECT: [("(?:nouveaux? |nouvelles? |new )?", "(?:nouveaux? |new )?")]}, "w_17"),
    "« une nouvelle HIGH » non lu": ({_DIRECT: [("(?:nouveau |nouvelle |new )?", "(?:nouveau |new )?")]}, "w_17"),
    "« HIGH @ » non lu": ({_DIRECT: [('    r"|(?<!no )(?<!aucun )(?<!0 )(?<!de )\\b(?:high|critical) @|\\brouge\\b|\\bbloque\\b")\n',
                                      '    r"|\\brouge\\b|\\bbloque\\b")\n')]}, "w_17"),
    "« no HIGH @ » avalé": ({_DIRECT: [("(?<!no )(?<!aucun )(?<!0 )(?<!de )\\b(?:high", "\\b(?:high")]}, "w_17"),
    # Binôme ter (T3) : les cinq survivants nommés par le critique, et les deux branches neuves.
    "« rouge » non lu": ({_DIRECT: [("|\\brouge\\b", "")]}, "w_17"),
    "« bloque » non lu": ({_DIRECT: [("|\\bbloque\\b", "")]}, "w_17"),
    "« findings N » non lu": ({_DIRECT: [("|\\bfindings ?[=:]? ?[1-9]", "")]}, "w_17"),
    "CRITICAL non lu au compte": ({_DIRECT: [("(?:nouveaux? |nouvelles? |new )?(?:high|critical)\\b",
                                              "(?:nouveaux? |nouvelles? |new )?high\\b")]}, "w_17"),
    "« 0 HIGH @ » avalé": ({_DIRECT: [("(?<!0 )", "")]}, "w_17"),
    "« de HIGH @ » avalé": ({_DIRECT: [("(?<!de )", "")]}, "w_17"),
    "« un HIGH » non lu": ({_DIRECT: [("|\\b(?:un|une|one) (?:nouveau |nouvelle |new )?(?:high|critical)\\b", "")]}, "w_17"),
    "« HIGH: N » non lu": ({_DIRECT: [("|\\b(?:high|critical) ?[:=] ?[1-9]", "")]}, "w_17"),
    "remède C4 sans la sortie du verdict clos": ({_DIRECT: [(
        '"ou, verdict clos, fais retracer par `security-code-review` un verdict au vocabulaire fermé (CLEAN, 0 HIGH) ; "',
        '""')]}, "w_17"),
    "critères non rejoués au done": ({_DIRECT: [(_AU_DONE, "        causes_au_done = []\n")]}, "w_18"),
    "retour à la première cause": ({_DIRECT: [(_SECU + "    return causes\n", _SECU + "    return causes[:1]\n")]}, "w_20"),
    "estampille invalide = chemin planifié silencieux": ({_ETATS: [(_DIRECTE, _DIRECTE.replace(
        '"direct" in task\n', '"direct" in task and not refus_direct(root, task, instantane=True)\n'))]}, "w_21"),
    "ré-estampiller efface chaine_franchie (T4)": ({_DIRECT: [(_FRANCHIE, "")]}, "w_21b"),
    "--retirer admis après franchissement (T4)": ({_DIRECT: [("            if franchie:\n                raise BoardError(",
                                                               "            if False:\n                raise BoardError(")]},
                                                  "w_21b"),
    # Binôme quater (F1) : `--retirer` admis hors `running` — LE MÊME mutant, tué en `blocked`
    # (w_21b) ET sur une franchie rétrogradée en `pending` (w_21c).
    "--retirer admis hors running, bloquée (F1 quater)": ({_DIRECT: [(_NON_CLOSE, _NON_CLOSE.replace('!= "done"', '== "running"'))]},
                                                          "w_21b"),
    "--retirer admis hors running, rétrogradée (F1 quater)": ({_DIRECT: [(_NON_CLOSE, _NON_CLOSE.replace('!= "done"', '== "running"'))]},
                                                              "w_21c"),
    # Binôme quater (fable 2) : le remède d'une franchie ne propose pas un `--retirer` refusé.
    "remède franchie : --retirer proposé (fable 2)": ({_DIRECT: [("    elif franchie:\n", "    elif False:\n")]}, "w_21d"),
    "franchie non passée au start (fable 2)": ({_DIRECT: [('"démarrer", direct_franchie(task))', '"démarrer")')]}, "w_21d"),
    "franchie non passée au done (fable 2)": ({_DIRECT: [('"clore", direct_franchie(task))', '"clore")')]}, "w_21d"),
    "remède C6 au start : ré-estampiller (T5)": ({_DIRECT: [('    elif any(c.startswith("C6 ") for c in causes):\n',
                                                             "    elif False:\n")]}, "w_29"),
    "chaine_franchie non lu au done": ({_DIRECT: [('    if isinstance(tampon, dict) and tampon.get("chaine_franchie"):\n',
                                                   "    if False:\n")]}, "w_22"),
    "clé non écrite par save": ({_DIRECT: [('            task["direct"] = {"writeset": writeset_of(task), "le": today}\n',
                                            '            dict(task)["direct"] = {"writeset": writeset_of(task), "le": today}\n')]},
                                "w_23"),
    "marque de la rév. 3 (id du kit)": ({_DIRECT: [(_MARQUE, _MARQUE.replace(' par direct]"', ' par direct — S-00004109]"'))]},
                                        "w_28"),
    "id du kit dans un refus C1 (balayage de w_28)": ({_DIRECT: [("chemins déclarés, au-delà de",
                                                                  "chemins déclarés (voir T-00000691), au-delà de")]}, "w_28"),
    "un seul compte dans la marque (S-00004175 (2))": ({_DIRECT: [(_MARQUE, _MARQUE.replace("{valides} validé", "{courant} validé"))]},
                                                       "w_32"),
    # -- 7bis (T-00000726) : C4 et C3 sous S-id ULID -------------------------------------
    "M42 rang int": ({_DIRECT: [(_RANG_DEUX_ETAGES, _RANG_INT)]}, "w_35"),
    "M43 cites sans majuscules": ({_DIRECT: [('{f"S-{n.upper()}"', '{f"S-{n}"')]}, "w_36"),
    "M44 grammaire sans ULID": ({_DIRECT: [(_S_ID_ULID, 'DIRECT_S_ID = re.compile(r"\\bs-([0-9]{8})\\b")')]}, "w_36"),
}


class DirectModeTests(Temoins, unittest.TestCase):
    """Chaque témoin sur le VRAI `.agents/bin`."""


for _nom in sorted(n for n in dir(Temoins) if n.startswith("w_")):
    setattr(DirectModeTests, "test_" + _nom[2:], (lambda n: lambda self: getattr(self, n)(BIN))(_nom))


class DirectModeMutantsTests(Temoins, unittest.TestCase):
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
        for temoin in ("w_01", "w_06", "w_12c", "w_21"):
            getattr(self, temoin)(variante)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n in MUTANTS}
# Deux mutants au MÊME nom de test : le second écraserait le premier en silence.
assert len(_GENERES) == len(MUTANTS), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(DirectModeMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


if __name__ == "__main__":
    unittest.main()
