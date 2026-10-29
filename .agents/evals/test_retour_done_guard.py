"""LA JAMBE RETOUR DU `done` — comportement (T-00001182, volet 2 de S-00004135).

Décisions S-00004114, S-00004168, S-00004181, S-00004192 ; correctifs C1-C7 de
S-00004199. ZÉRO APPEL LLM.

Le `done` d'une tâche estampillée `direct` qui FRANCHIT une garde armée (cible au
`done`, chaîne franchie au `start`) exige le relevé `tasks.py retour` de SA branche,
fusionnée `git merge --no-ff` telle quelle, fichiers dans l'instantané de
l'estampille, et un verdict de sécurité tracé APRÈS le relevé qui ne dit ni un
blocage ni une revue absente. La fusion se lit sur la PRÉ-MESURE du dispatch `done`,
HORS verrou (voie (a)).

Chaque témoin `d_*` reçoit le dossier `bin` à éprouver : le VRAI `.agents/bin`, ou
une COPIE JETABLE dont un fragment littéral, présent UNE fois (asserté), est
remplacé — forme `MUTANTS` de `test_direct_mode.py`. Un mutant ne rejoue QUE le
témoin qui le tue et doit le faire échouer par une ASSERTION : les aides du banc
lèvent `RuntimeError`, jamais `AssertionError`, et chaque geste éprouvé est asserté
par le témoin lui-même. UN dépôt git jetable PAR TÉMOIN (`tempfile`, sous
`TMPDIR`) : board sous `.agents/` (exclu par `info/exclude`), `HOME` et
`XDG_CONFIG_HOME` jetables (une `.gitconfig` d'identité, la config de l'utilisateur
hors du banc), `GIT_CONFIG_NOSYSTEM=1`, `CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR`
PROPRES au banc (sous Linux un inode recyclé apparenterait des partitions), toute
variable `GIT_*` héritée et `CLAUDE_PROJECT_DIR` retirées.

Témoins : D1 nominal ; D2 sans relevé ; D3 relevé refusé ; D4 jamais fusionné, D4b
avance rapide, D4c fusion imbriquée ; D5 commit après le relevé ; D6 instantané
réduit, D6b un chemin devenu répertoire au-delà du compte ; D7 verdict antérieur au
relevé ; D8 vocabulaire du verdict (ouvert, absent, fermé) ; D9 emprunt au slot de la
portée de revue, T2 qui n'emprunte pas la sécurité de T1 (même chantier, hors portée) et
la sécurité tracée après le relevé, avant la portée, admise (C38) ; D10 désarmé et `--sans-cible`, D10a/b/c la marque `[SANS RELEVÉ]` (C1) ;
D11 le binôme d'abord ; D12 SPECS illisible et borne nulle ; D13 chaîne seule ; D14
aucun id du kit ; D15a/b/c une directe se relève seule, id introuvable ; D16 le
gabarit de la session directe (kit seul) ; D17a/b/c la pré-mesure hors verrou ; D18
`reopen`, D18c `start` depuis `done` (écart au plan, mesuré au dev) ; D19 sans
pré-mesure en processus ; D20 le CONTENU de la fusion (un fichier hors du relevé
glissé par `merge --no-commit`), D20b un contenu non lu refuse (binôme c4f3 F1) ;
D21 un `core.fsmonitor` de la config du dépôt n'est pas exécuté par le relevé ; D22
un relevé neuf n'efface pas l'antérieur, contrôle (i) (binôme c4f3 bis T1) : refusé
puis fusionné, et le rejeu (absorbant), D22b une fusion à passager, D22c le légitime
(branche sans commit propre, fusion telle quelle), D22d une avance rapide, D22e un
(i) non conclu n'écrit rien, D22f une tâche planifiée hors de (i), D22g un relevé
changé pendant la mesure, D22h une pointe absente (donnée) ou illisible (refus) ;
D22i l'absorption bornée à la tâche, un relevé co-nommé comparé pour chacune
(binôme c4f3 ter N1) ; D22j une branche refusée encore vivante met le relevé neuf
« en suspens » (rc 2, rien d'écrit), son rejeu non, sa suppression le lève ; D22k
les sorties légitimes : antérieur ok vivant, branche refusée corrigée puis relevée,
fusionnée puis supprimée par `git branch -d` (binôme c4f3 ter N2).

LA LIVRAISON (T-01M4WTYSCEYHC6KZF2DC1PXBRN), relevé `--vers` : D4c reste ROUGE (fusion
imbriquée sans `vers`) ; D4d le légitime (lot → L → main, union des write-sets des membres) ;
D4e un passager sur L ; D4f un passager `--no-commit` dans la fusion du lot dans L ; D4g la
livraison retirée (R-v) ; D4h un lot fusionné directement dans main puis contenu par L n'est
pas compté au niveau 2 ; D4i un write-set de directe étendu : C5, puis ré-estampillé ; D4j un
relevé `vers` fusionné à un niveau ; D22l (i) d'un antérieur `vers`, à un niveau depuis L puis
à deux depuis HEAD.

BORNE : le relevé et le verdict sont DÉCLARATIFS. Ça empêche d'OUBLIER, pas de TRICHER.
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
# Le résolveur du kit, chargé PAR CHEMIN (patron v3prep) : la source de `ids.py` est le paquet
# `cadre` de la racine, où qu'il vive (`.agents/vendor/cadre` ou `src/cadre`).
_SPEC_VENDOR = importlib.util.spec_from_file_location("_retour_done_vendor_paths", BIN / "vendor_paths.py")
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)

#: Les fichiers copiés pour une variante : la façade, ses parties et les frères qu'elles chargent.
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "specs.py",
          "kickoff_guard.py", "events.py")
SPEC = "# Spec du banc\n\n**« contrat déclaré »** — le contrat du banc.\n"
ID_DU_KIT = re.compile(r"\b[TS]-\d{3,}")
MARQUE = "[DIRECT SANS PLAN :"
GO = "security-code-review : GO"
#: D16 : le gabarit de la session directe (kit seul) et ses deux prescriptions retirées par P1.
PROMPT = ROOT / "docs" / "tasks" / "PROMPT-SESSION-DIRECT.md"
PRESCRIPTIONS = ('--sans-cible "dev direct sans plan, décision pilote 2026-10-03', "`--sans-cible` S-00003952")


def copie(case: unittest.TestCase, source: Path, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable de `source` (dossier bin), chaque ancre remplacée UNE fois."""
    base = Path(tempfile.mkdtemp(prefix="retour-done-mut-"))
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
    """Le module `tasks` de `bin_`, chargé sous un nom unique (appels en processus)."""
    nom = f"tasks_retour_done_banc_{abs(hash(str(bin_)))}"
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, bin_ / "tasks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


#: Corps ULID FIXES (T-00000726, étape 7bis) : U0 < U_LETTER < U_DIGIT dans l'ordre de
#: frappe (Crockford est monotone en ASCII) ; U_DIGIT finit par un CHIFFRE.
U0 = "01M3240000000000000000000Z"
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


def entree(sid: int | str, tid: str, kind: str, titre: str, texte: str = "") -> dict:
    """Une entrée SPECS ; `sid` entier ⇒ l'ancienne forme `S-<8 chiffres>`, chaîne ⇒ telle quelle (un `S-<ULID>`)."""
    return {"id": sid if isinstance(sid, str) else f"S-{sid:08d}", "task": tid, "kind": kind, "title": titre,
            "text": texte, "files": [], "date": "2026-10-06"}


class Banc:
    """UN dépôt git jetable, la CLI de `bin_` braquée dessus."""

    def __init__(self, case: unittest.TestCase, bin_: Path):
        self.case, self.bin, self.n = case, bin_, 0
        self.racine = Path(tempfile.mkdtemp(prefix="retour-done-")).resolve()
        case.addCleanup(shutil.rmtree, self.racine, True)
        self.d = self.racine / "depot"
        for sous in ("depot", "home", "xdg", "etat", "events"):
            (self.racine / sous).mkdir()
        for sous in ("board", "gates", "local/plan", "local/binome", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True)
        (self.racine / "home" / ".gitconfig").write_text(
            "[user]\n\tname = banc\n\temail = banc@exemple.invalid\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        self.env.update(HOME=str(self.racine / "home"), XDG_CONFIG_HOME=str(self.racine / "xdg"),
                        GIT_CONFIG_NOSYSTEM="1", CADRE_STATE_DIR=str(self.racine / "etat"),
                        AGENTS_EVENTS_DIR=str(self.racine / "events"),
                        GIT_AUTHOR_NAME="banc", GIT_AUTHOR_EMAIL="banc@exemple.invalid",
                        GIT_COMMITTER_NAME="banc", GIT_COMMITTER_EMAIL="banc@exemple.invalid")
        self.g("init", "-q", "-b", "main")
        (self.d / ".git" / "info" / "exclude").write_text(".agents/\n", encoding="utf-8")
        (self.d / "LISEZMOI").write_text("banc\n", encoding="utf-8")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "base")

    # -- git et CLI -------------------------------------------------------------
    def g(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=self.d, env=self.env, capture_output=True, text=True,
                           timeout=120, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
        return r.stdout

    def sha(self, rev: str = "HEAD") -> str:
        return self.g("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def argv(self, *args: str) -> list[str]:
        return [sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args]

    def t(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(self.argv(*args), capture_output=True, text=True, timeout=300,
                              env=env or self.env, check=False)

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        r = self.t(*args)
        if r.returncode != 0:
            raise RuntimeError(f"banc : {args} en échec : {r.stdout}{r.stderr}")
        return r

    # -- board, gardes, SPECS -----------------------------------------------------
    def nouvelle(self, titre: str = "tâche de banc", chemins: list[str] | None = None,
                 chantier: str | None = None) -> str:
        r = self.ok("new", titre, *(["--chantier", chantier] if chantier else []))
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        if trouve is None:
            raise RuntimeError(f"banc : message de `new` inattendu : {r.stdout}")
        if chemins:
            self.ok("writeset", trouve.group(1), *chemins)
        return trouve.group(1)

    def directe(self, titre: str = "directe", chemins: list[str] | None = None, chantier: str | None = None) -> str:
        tid = self.nouvelle(titre, chemins or ["src/a.py"], chantier)
        self.ok("direct", tid)
        return tid

    def tache(self, tid: str) -> dict:
        return json.loads(self.ok("list", "--task", tid, "--json").stdout)[0]

    def board(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    def board_sha(self) -> str:
        return hashlib.sha256(self.board().read_bytes()).hexdigest()

    def forger(self, tid: str, **champs) -> None:
        """Réécrit des champs du relevé de `tid` au board, à la main (un relevé FORGÉ)."""
        data = json.loads(self.board().read_text(encoding="utf-8"))
        tache = next(t for t in data["tasks"] if t["id"] == tid)
        tache["retour"].update(champs)
        self.board().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def armer(self, nom: str) -> None:
        (self.d / ".agents" / "state" / "gates" / nom).write_text("", encoding="utf-8")

    def armer_cible(self) -> None:
        (self.d / "docs").mkdir(exist_ok=True)
        (self.d / "docs" / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            "spec=docs/spec.md\nchantier=*\n", encoding="utf-8")

    def specs_chemin(self) -> Path:
        return self.d / ".agents" / "state" / "specs" / "SPECS.json"

    def verdict(self, tid: str, titre: str = GO, texte: str = "", sid: str | None = None) -> str:
        """AJOUTE un verdict au SPECS : rend son id. `sid` explicite (un `S-<ULID>`, 7bis)
        écrit TEL QUEL ; sans lui, l'ancien `S-<n+1>` au-delà des seuls ANCIENS, rangés par
        `sort_key` — jamais `int(e["id"][2:])`, qui lève sur un ULID (R-BANCS (ii))."""
        chemin = self.specs_chemin()
        entrees = json.loads(chemin.read_text(encoding="utf-8"))["entries"] if chemin.is_file() else []
        if sid is None:
            module, anciens = charger(self.bin), [0]
            for e in entrees:
                try:
                    rang = module.sort_key(e["id"])
                except module.BoardError:  # un id illisible ne compte pas
                    continue
                if rang[0] == 0:
                    anciens.append(rang[1])
            sid = f"S-{max(anciens) + 1:08d}"
        entrees.append(entree(sid, tid, "verdict", titre, texte))
        chemin.write_text(json.dumps({"entries": entrees}), encoding="utf-8")
        return sid

    # -- le geste d'une directe -----------------------------------------------------
    def branche(self, tid: str, fichiers: dict[str, str] | None = None) -> tuple[str, str]:
        """Une branche née de HEAD portant `fichiers` (par défaut le write-set de `tid`),
        puis RETOUR sur `main` : rend `(base, nom)`."""
        self.n += 1
        base, nom = self.sha(), f"wt/{tid}-{self.n}"
        fichiers = fichiers or {p: f"{tid} {self.n}\n" for p in self.tache(tid)["writeset"]}
        self.g("switch", "-q", "-c", nom)
        for chemin, contenu in fichiers.items():
            (self.d / chemin).parent.mkdir(parents=True, exist_ok=True)
            (self.d / chemin).write_text(contenu, encoding="utf-8")
        self.g("add", "--", *fichiers)
        self.g("commit", "-q", "-m", f"dev {nom}")
        self.g("switch", "-q", "main")
        return base, nom

    def retour(self, *tids: str, base: str, branche: str) -> subprocess.CompletedProcess:
        return self.t("retour", *tids, "--base", base, "--branche", branche)

    def fusion(self, branche: str, mode: str = "no-ff") -> None:
        if mode == "ff":
            self.g("merge", "-q", "--ff-only", branche)
        else:
            self.g("merge", "-q", "--no-ff", "-m", f"fusion {branche}", branche)

    def livrer(self, tid: str, fusion: str | None = "no-ff", titre: str | None = GO, texte: str = "") -> str:
        """Le nominal : branche, relevé ok, fusion, verdict après le relevé. Rend la branche."""
        base, nom = self.branche(tid)
        r = self.retour(tid, base=base, branche=nom)
        if r.returncode != 0:
            raise RuntimeError(f"banc : relevé refusé : {r.stdout}{r.stderr}")
        if fusion:
            self.fusion(nom, fusion)
        if titre:
            self.verdict(tid, titre, texte)
        return nom

    def shim(self, signal: Path, sommeil: int) -> dict[str, str]:
        """Un faux `git` en tête de PATH : il pose `signal` puis dort `sommeil` s sur la
        SEULE pré-mesure (`rev-list --first-parent --merges`), sinon il passe la main."""
        vrai = shutil.which("git", path=self.env.get("PATH"))
        if vrai is None:
            raise RuntimeError("banc : git introuvable")
        dossier = self.racine / "shim"
        dossier.mkdir(exist_ok=True)
        script = (f"#!/bin/sh\nlent=0\nfor a in \"$@\"; do\n  if [ \"$a\" = \"--merges\" ]; then lent=1; fi\ndone\n"
                  f"if [ \"$lent\" = 1 ]; then\n  : > '{signal}'\n  sleep {sommeil}\nfi\nexec '{vrai}' \"$@\"\n")
        (dossier / "git").write_text(script, encoding="utf-8")
        (dossier / "git").chmod(0o755)
        return {**self.env, "PATH": str(dossier) + os.pathsep + self.env.get("PATH", "")}

    def panne(self, drapeau: str) -> dict[str, str]:
        """Un faux `git` en tête de PATH qui ÉCHOUE (rc 1) sur tout appel portant
        `drapeau`, sinon passe la main : une panne ciblée sur un seul contrôle."""
        vrai = shutil.which("git", path=self.env.get("PATH"))
        if vrai is None:
            raise RuntimeError("banc : git introuvable")
        dossier = self.racine / "panne"
        dossier.mkdir(exist_ok=True)
        script = (f"#!/bin/sh\nfor a in \"$@\"; do\n  if [ \"$a\" = '{drapeau}' ]; then\n"
                  f"    echo 'panne simulée' >&2\n    exit 1\n  fi\ndone\nexec '{vrai}' \"$@\"\n")
        (dossier / "git").write_text(script, encoding="utf-8")
        (dossier / "git").chmod(0o755)
        return {**self.env, "PATH": str(dossier) + os.pathsep + self.env.get("PATH", "")}

    def en_processus(self, *args, **kwargs):
        """`set_state` appelé EN PROCESSUS (le pont V3, un appelant qui saute le dispatch)."""
        cles = ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM", "CADRE_STATE_DIR", "AGENTS_EVENTS_DIR")
        with mock.patch.dict(os.environ, {k: self.env[k] for k in cles}):
            return charger(self.bin).set_state(str(self.d), *args, **kwargs)


def attendre(signal: Path, proc: subprocess.Popen, delai: float = 60) -> None:
    """Attend `signal` (le faux git dort) ; un processus sorti avant, ou le délai, est un défaut du banc."""
    fin = time.monotonic() + delai
    while not signal.exists():
        if proc.poll() is not None or time.monotonic() > fin:
            raise RuntimeError(f"banc : la pré-mesure n'a pas atteint le faux git (rc {proc.poll()})")
        time.sleep(0.05)


class Temoins:
    """Les témoins, chacun paramétré par le dossier `bin` qu'il éprouve."""

    def refuse(self, r: subprocess.CompletedProcess, *contient: str) -> str:
        self.assertNotEqual(r.returncode, 0, f"done admis : {r.stdout}{r.stderr}")
        for x in contient:
            self.assertIn(x, r.stderr)
        return r.stderr

    def admis(self, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(r.returncode, 0, f"done refusé : {r.stdout}{r.stderr}")

    # -- D1 D2 D3 : le nominal, aucun relevé, un relevé refusé --------------------------
    def d_01(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        self.admis(b.t("done", tid, "--raison", "livré"))
        stage = b.tache(tid)["stage"]
        self.assertIn(MARQUE, stage)
        self.assertNotIn("SANS CIBLE", stage)
        self.assertNotIn("SANS RELEVÉ", stage)

    def d_02(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        _base, nom = b.branche(tid)
        b.fusion(nom)
        b.verdict(tid)
        avant = b.board_sha()
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "(R-a)", f"tasks.py retour {tid}", "--sans-cible")
        self.assertNotIn("non pré-mesuré", err, "R-b évalué sans relevé (ordre R-a avant R-b)")
        self.assertNotIn("aucun verdict", err, "verdict de sécurité exigé sans relevé à borner")
        self.assertEqual(b.board_sha(), avant, "un refus a écrit le board")

    def d_03(self, bin_: Path) -> None:
        """Un relevé `refus` (index du principal non vide), NON fusionné : R-a seul."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base, nom = b.branche(tid)
        (b.d / "autre.txt").write_text("indexé\n", encoding="utf-8")
        b.g("add", "autre.txt")
        self.assertEqual(b.retour(tid, base=base, branche=nom).returncode, 1, "précondition : relevé refusé (g)")
        b.g("reset", "-q", "autre.txt")
        b.verdict(tid)
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "(R-a)", "n'est pas ok")
        self.assertNotIn("(R-b)", err, "R-b évalué sur un relevé refusé")

    # -- D4 D4b D4c D5 : la fusion ---------------------------------------------------
    def d_04(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid, fusion=None)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "git merge --no-ff", "--sans-cible")

    def d_04b(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid, fusion="ff")
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "git merge --no-ff", "avance rapide")

    def d_04c(self, bin_: Path) -> None:
        """La branche fusionnée dans une INTERMÉDIAIRE, elle-même fusionnée `--no-ff`."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base, nom = b.branche(tid)
        self.assertEqual(b.retour(tid, base=base, branche=nom).returncode, 0, "précondition : relevé ok")
        b.g("switch", "-q", "-c", "inter")
        b.fusion(nom)
        b.g("switch", "-q", "main")
        b.fusion("inter")
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "fusion imbriquée")

    def d_05(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        nom = b.livrer(tid, fusion=None)
        b.g("switch", "-q", nom)
        (b.d / "src" / "a.py").write_text("après le relevé\n", encoding="utf-8")
        b.g("commit", "-q", "-am", "après le relevé")
        b.g("switch", "-q", "main")
        b.fusion(nom)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "git merge --no-ff")

    # -- D6 D6b : les fichiers du relevé ----------------------------------------------
    def d_06(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe("deux", ["src/a.py", "src/b.py"])
        b.livrer(tid)
        b.ok("writeset", tid, "src/a.py")
        b.ok("direct", tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-c)", "src/b.py", "instantané")

    def d_06b(self, bin_: Path) -> None:
        """`pkg/mod`, estampillé quand il n'existait pas, devient un répertoire de 6 fichiers :
        chaîne seule (sous cible armée, C1 de `refus_direct` refuserait d'abord)."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe("module", ["pkg/mod"])
        b.ok("start", tid)
        base, nom = b.branche(tid, {f"pkg/mod/f{i}.py": f"{i}\n" for i in range(1, 7)})
        self.assertEqual(b.retour(tid, base=base, branche=nom).returncode, 0, "précondition : relevé ok")
        b.fusion(nom)
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-c)", "6 fichier(s)", "au-delà")

    # -- D7 D8 D9 : le verdict de sécurité ------------------------------------------
    def d_07(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.verdict(tid)
        b.livrer(tid, titre=None)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(s) aucun verdict de sécurité tracé après le relevé")

    def d_08(self, bin_: Path) -> None:
        """Chaîne seule : sous cible armée, le rejeu C4 de `refus_direct` refuserait d'abord un
        verdict bloquant DE LA TÂCHE — ici seule la jambe retour le lit (préfixe « (s) »)."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe()
        b.ok("start", tid)
        b.livrer(tid, titre="security-code-review : NO_GO")
        refus = [("security-code-review : NO_GO", "", "bloquant"),
                 ("security-code-review FINDINGS(code)", "", "bloquant"),
                 ("security-code-review : 2 HIGH @ abc1234", "", "bloquant"),
                 ("security-code-review : GO", "2 HIGH @ abc1234", "bloquant"),
                 ("security-code-review : COVERAGE DEGRADED — semgrep absent", "", "revue absente"),
                 ("security-code-review : GO", "revue non jouée", "revue absente"),
                 ("security-code-review : verdict absent", "", "revue absente")]
        for titre, texte, dit in refus:
            b.verdict(tid, titre, texte)
            self.refuse(b.t("done", tid, "--raison", "livré"), "(s)", dit)
        b.verdict(tid, GO)  # un verdict OUVERT plus ancien sous un GO plus récent : admis
        self.admis(b.t("done", tid, "--raison", "livré"))
        for titre in ("security-code-review CLEAN — 0 HIGH", "security-code-review : GO_AVEC_RESERVES"):
            autre = b.directe("fermé", ["src/b.py"])
            b.ok("start", autre)
            b.livrer(autre, titre=titre)
            self.admis(b.t("done", autre, "--raison", titre))

    def d_09(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        slot = b.nouvelle("slot du lot", chantier="lot")
        b.ok("start", slot)
        tid = b.directe("sous le slot", chantier="lot")
        b.ok("review-scope", slot, tid)  # l'emprunt passe par la portée (T-01M5F728FGJ43QJX1RJKTWWKRB)
        b.livrer(tid, titre=None)
        sid = b.verdict(slot)
        self.admis(b.t("done", tid, "--raison", "livré"))
        self.assertIn(f"[revue de sécurité empruntée au slot {slot} : {sid}]", b.tache(tid)["stage"])
        ailleurs = b.directe("autre chantier", ["src/b.py"], chantier="ailleurs")
        b.livrer(ailleurs, titre=None)
        b.verdict(slot)
        self.refuse(b.t("done", ailleurs, "--raison", "livré"), "(s) aucun verdict de sécurité")

    # -- LA SÉCURITÉ BORNÉE PAR LA PORTÉE (T-01M5F728FGJ43QJX1RJKTWWKRB, C45) --------------
    def d_T2_cannot_borrow_T1_security(self, bin_: Path) -> None:
        """T1 `running` et T2 relevée, du MÊME chantier : le seul verdict de T1 ne couvre
        pas T2 — ni sans portée, ni sous une portée qui ne nomme que T1."""
        b = Banc(self, bin_)
        b.armer_cible()
        t1 = b.nouvelle("T1 en vol", chantier="lot")
        b.ok("start", t1)
        t2 = b.directe("T2 du même chantier", chantier="lot")
        b.livrer(t2, titre=None)
        b.verdict(t1)
        self.refuse(b.t("done", t2, "--raison", "livré"), "(s) aucun verdict de sécurité", "review-scope")
        b.ok("review-scope", t1)
        self.refuse(b.t("done", t2, "--raison", "livré"), "(s) aucun verdict de sécurité")
        self.assertNotIn("revue de sécurité empruntée", b.tache(t2)["stage"])

    def d_security_after_retour_before_scope_accepted(self, bin_: Path) -> None:
        """ARBITRAGE C38 (S-01M5E5WH6S) : un `security-code-review` tracé APRÈS le relevé
        `retour` et AVANT la déclaration de la portée compte — la borne est la première
        disponible, celle du relevé, jamais `declared_at`."""
        b = Banc(self, bin_)
        b.armer_cible()
        t1 = b.nouvelle("T1 en vol", chantier="lot")
        b.ok("start", t1)
        t2 = b.directe("T2 relevée")
        b.livrer(t2, titre=None)
        sid = b.verdict(t1)
        b.ok("review-scope", t1, t2)
        self.admis(b.t("done", t2, "--raison", "livré"))
        self.assertIn(f"[revue de sécurité empruntée au slot {t1} : {sid}]", b.tache(t2)["stage"])

    # -- D10 D10a D10b D10c : désarmé, `--sans-cible`, la marque `[SANS RELEVÉ]` ------
    def d_10(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.directe()
        self.admis(b.t("done", tid, "--raison", "désarmé"))
        self.assertNotIn("DIRECT", b.tache(tid)["stage"])
        b.armer_cible()
        autre = b.directe("sortie", ["src/b.py"])
        self.admis(b.t("done", autre, "--raison", "fusionnée sans relevé", "--sans-cible", "pourquoi"))
        self.assertIn("[SANS CIBLE : pourquoi]", b.tache(autre)["stage"])

    def d_10a(self, bin_: Path) -> None:
        """C1 : chaîne seule, `done --sans-cible` saute la jambe — la marque le DIT."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe()
        b.ok("start", tid)
        self.admis(b.t("done", tid, "--raison", "fin", "--sans-cible", "pourquoi"))
        stage = b.tache(tid)["stage"]
        self.assertIn(MARQUE, stage)
        self.assertIn("[SANS RELEVÉ : pourquoi]", stage, "jambe retour sautée sans marque (C1)")
        self.assertNotIn("SANS CIBLE", stage)

    def d_10b(self, bin_: Path) -> None:
        """Cible armée : `[SANS CIBLE]` dit la cible sautée, `[SANS RELEVÉ]` la jambe retour —
        les DEUX marques coexistent (binôme c4f3 F4) ; désarmé : aucune."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        b.armer_cible()
        tid = b.directe()
        b.ok("start", tid)
        self.admis(b.t("done", tid, "--raison", "fin", "--sans-cible", "pourquoi"))
        stage = b.tache(tid)["stage"]
        self.assertIn("[SANS CIBLE : pourquoi]", stage)
        self.assertIn("[SANS RELEVÉ : pourquoi]", stage, "jambe retour sautée sans marque sous cible armée")
        nu = Banc(self, bin_)
        tid = nu.directe()
        self.admis(nu.t("done", tid, "--raison", "fin", "--sans-cible", "pourquoi"))
        self.assertNotIn("SANS RELEVÉ", nu.tache(tid)["stage"], "marque dans un dépôt désarmé")

    def d_10c(self, bin_: Path) -> None:
        """Le pont V3 passe `sans_cible` en processus : la jambe sautée se DIT aussi."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe()
        b.ok("start", tid)
        b.en_processus(tid, "done", stage="clos par le pont", sans_binome="pont", sans_cible="pont, sans plan")
        stage = b.tache(tid)["stage"]
        self.assertIn(MARQUE, stage)
        self.assertIn("[SANS RELEVÉ : pont, sans plan]", stage)

    # -- D11 D12 D13 ----------------------------------------------------------------
    def d_11(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        b.armer("BINOME_REQUIRED")
        tid = b.directe()
        b.livrer(tid)
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "REVUE CRITIQUE")
        self.assertNotIn("(R-", err, "la jambe retour a parlé avant le binôme")

    def d_12(self, bin_: Path) -> None:
        """Chaîne seule : SPECS illisible au `done` ; puis une borne NULLE (SPECS illisible au relevé)."""
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe()
        autre = b.directe("borne nulle", ["src/b.py"])
        b.ok("start", tid)
        b.ok("start", autre)  # AVANT la corruption : le rejeu du `start` lit SPECS (C3-C4)
        b.livrer(tid)
        b.specs_chemin().write_text("{pas du json", encoding="utf-8")
        b.livrer(autre, titre=None)
        self.assertIsNone(b.tache(autre)["retour"]["specs_borne"], "précondition : borne nulle")
        self.refuse(b.t("done", tid, "--raison", "livré"), "(s) SPECS illisible")
        b.specs_chemin().unlink()
        b.verdict(autre)
        self.refuse(b.t("done", autre, "--raison", "livré"), "(R-d)")

    def d_13(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer("PLAN_CHAIN_REQUIRED")
        tid = b.directe()
        b.ok("start", tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-a)", f"tasks.py retour {tid}")

    # -- D14 : rien du kit dans ce qui voyage ---------------------------------------------
    def d_14(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        sorties = []
        sans = b.directe("sans relevé")
        sorties.append(b.t("done", sans, "--raison", "x").stderr)
        nonfus = b.directe("non fusionnée", ["src/b.py"])
        b.livrer(nonfus, fusion=None)
        sorties.append(b.t("done", nonfus, "--raison", "x").stderr)
        absent = b.directe("revue absente", ["src/c.py"])
        b.livrer(absent, titre="security-code-review : COVERAGE DEGRADED")
        sorties.append(b.t("done", absent, "--raison", "x").stderr)
        b.forger(absent, taches=[absent, "T-99999999"])
        sorties.append(b.t("done", absent, "--raison", "x").stderr)
        board = json.loads(b.board().read_text(encoding="utf-8"))
        specs = json.loads(b.specs_chemin().read_text(encoding="utf-8"))["entries"]
        fixtures = {t["id"] for t in board["tasks"]} | {e["id"] for e in specs} | {"T-99999999"}
        for sortie in sorties:
            self.assertTrue(sortie.strip(), "précondition : un refus")
            self.assertEqual(set(ID_DU_KIT.findall(sortie)) - fixtures, set(), f"un id du kit voyage : {sortie}")

    # -- D15a D15b D15c : une directe se relève seule ---------------------------------
    def d_15a(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        tid = b.directe()
        autre = b.nouvelle("autre", ["src/b.py"])
        base, nom = b.branche(tid, {"src/a.py": "a\n", "src/b.py": "b\n"})
        r = b.retour(tid, autre, base=base, branche=nom)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"RETOUR (c) refus — {tid} estampillée(s) direct", r.stdout)

    def d_15b(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        autre = b.nouvelle("autre", ["src/b.py"])
        b.livrer(tid)
        b.forger(tid, taches=[tid, autre])
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-t)", f"nomme aussi {autre}")

    def d_15c(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        b.forger(tid, taches=["T-99999999"])
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "(R-t)", "« T-99999999 », introuvable", "--sans-cible")
        self.assertNotIn("unknown task id", err, "la BoardError brute de `find` a fui")

    # -- D17a D17b D17c : la pré-mesure tourne HORS verrou ------------------------------
    def d_17a(self, bin_: Path) -> None:
        if os.name == "nt":
            self.skipTest("faux git en script sh : POSIX seulement")
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        autre = b.nouvelle("autre")
        b.livrer(tid)
        signal = b.racine / "signal"
        proc = subprocess.Popen(b.argv("done", tid, "--raison", "lente"), env=b.shim(signal, 8),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            attendre(signal, proc)
            r = b.t("block", autre, "--note", "pendant la pré-mesure")
            en_vol = proc.poll() is None
            _out, err = proc.communicate(timeout=120)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertEqual(r.returncode, 0, f"un verbe du board a attendu la pré-mesure (verrou tenu pendant git) : {r.stderr}")
        self.assertTrue(en_vol, "précondition : la pré-mesure dormait encore")
        self.assertEqual(proc.returncode, 0, err)

    def d_17b(self, bin_: Path) -> None:
        if os.name == "nt":
            self.skipTest("faux git en script sh : POSIX seulement")
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        signal = b.racine / "signal"
        proc = subprocess.Popen(b.argv("done", tid, "--raison", "relevé changé"), env=b.shim(signal, 3),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            attendre(signal, proc)
            b.forger(tid, le="2000-01-01T00:00:00Z")
            _out, err = proc.communicate(timeout=120)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertNotEqual(proc.returncode, 0, "un relevé changé pendant la mesure a été admis")
        self.assertIn("(R-b) relevé changé pendant la mesure", err)

    def d_17c(self, bin_: Path) -> None:
        """Le tableau de bord passe par le dispatch, borné par son délai : `timeout`, rien d'écrit, verrou libre."""
        if os.name == "nt":
            self.skipTest("faux git en script sh : POSIX seulement")
        spec = importlib.util.spec_from_file_location("dashboard_banc_retour_done", BIN / "dashboard.py")
        dashboard = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = dashboard
        spec.loader.exec_module(dashboard)
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        autre = b.nouvelle("autre")
        b.livrer(tid)
        avant = b.board_sha()
        sortie = dashboard._run_cli(b.argv("done", tid, "--raison", "tableau"), timeout=2.0,
                                    env=b.shim(b.racine / "signal", 4))
        self.assertEqual(sortie["status"], "timeout", sortie)
        self.assertEqual(b.board_sha(), avant, "un done coupé par le délai a écrit le board")
        debut = time.monotonic()
        r = b.t("block", autre, "--note", "après le délai")
        self.assertEqual(r.returncode, 0, f"verrou resté tenu : {r.stderr}")
        self.assertLess(time.monotonic() - debut, 30)

    # -- D18 D18c : un cycle neuf exige un relevé neuf ---------------------------------
    def d_18(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        self.admis(b.t("done", tid, "--raison", "premier"))
        b.ok("reopen", tid, "--raison", "rouvrir")
        _base, nom = b.branche(tid)
        b.fusion(nom)
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "second sans relevé"), "(R-a)")
        b.livrer(tid)
        self.admis(b.t("done", tid, "--raison", "second relevé"))

    def d_18c(self, bin_: Path) -> None:
        """Écart au plan, mesuré au dev : un `start` DEPUIS `done` (chaîne désarmée, donc
        sans rejeu C6) ne garde pas le relevé du cycle clos."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        self.admis(b.t("done", tid, "--raison", "premier"))
        b.ok("start", tid)
        self.refuse(b.t("done", tid, "--raison", "second sans relevé"), "(R-a)", f"tasks.py retour {tid}")
        b.livrer(tid)
        self.admis(b.t("done", tid, "--raison", "second relevé"))

    # -- D19 : sans pré-mesure, en processus -------------------------------------------
    def d_19(self, bin_: Path) -> None:
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        b.livrer(tid)
        module = charger(bin_)
        with self.assertRaises(module.BoardError) as refus:
            b.en_processus(tid, "done", stage="en processus")
        self.assertIn("relevé non pré-mesuré — passe par `tasks.py done`", str(refus.exception))
        self.admis(b.t("done", tid, "--raison", "par la CLI"))

    # -- D20 : le CONTENU de la fusion (binôme c4f3 F1) ------------------------------
    def d_20(self, bin_: Path) -> None:
        """`merge --no-ff --no-commit` + un fichier hors du relevé + commit : la pointe
        est bien le second parent, mais la fusion n'est pas telle quelle — refus nommé."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base, nom = b.branche(tid)
        self.assertEqual(b.retour(tid, base=base, branche=nom).returncode, 0, "précondition : relevé ok")
        b.g("merge", "-q", "--no-ff", "--no-commit", nom)
        (b.d / "hors.py").write_text("glissé dans la fusion\n", encoding="utf-8")
        b.g("add", "hors.py")
        b.g("commit", "-q", "-m", f"fusion {nom} avec un passager")
        self.assertEqual(b.g("rev-parse", "HEAD^2").strip(), b.tache(tid)["retour"]["tip"],
                         "précondition : la pointe relevée est le second parent")
        b.verdict(tid)
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "hors du relevé", "hors.py",
                          "n'est pas telle quelle", "--sans-cible")
        self.assertNotIn("n'est le second parent d'aucune", err, "la cause n'est pas la bonne")

    def d_20b(self, bin_: Path) -> None:
        """Une fusion de la pointe dont le contenu n'a PAS été lu refuse : jamais un passage."""
        module = charger(bin_)
        tip = "a" * 40
        releve = {"fichiers": ["src/a.py"]}
        pre = {"cle": ("b" * 40, tip, "le"), "lignes": [f"{'c' * 40} {'d' * 40} {tip}"]}
        causes = module.retour_contenu_fusions(releve, tip, pre)
        self.assertEqual(len(causes), 1, causes)
        self.assertIn("non mesuré", causes[0])
        pre["contenus"] = {"c" * 40: ["src/a.py"]}
        self.assertEqual(module.retour_contenu_fusions(releve, tip, pre), [], "contenu dans le relevé refusé")

    # -- D21 : un `core.fsmonitor` du dépôt ne s'exécute pas au relevé ------------------
    def d_21(self, bin_: Path) -> None:
        """`retour_git` neutralise `core.fsmonitor` et `core.hooksPath` : un script posé
        dans la config du DÉPÔT n'est pas lancé par le `git status` des contrôles (f)/(g).
        Le script est posé APRÈS les gestes du banc (dont les git le lanceraient)."""
        if os.name == "nt":
            self.skipTest("script fsmonitor en sh : POSIX seulement")
        b = Banc(self, bin_)
        tid = b.directe()
        base, nom = b.branche(tid)
        signal = b.racine / "fsmonitor-lance"
        script = b.racine / "fsmonitor.sh"
        script.write_text(f"#!/bin/sh\n: > '{signal}'\nexit 1\n", encoding="utf-8")
        script.chmod(0o755)
        b.g("config", "core.fsmonitor", str(script))
        r = b.retour(tid, base=base, branche=nom)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertFalse(signal.exists(), "le core.fsmonitor du dépôt a été exécuté par le relevé")

    # -- D22 : un relevé neuf n'efface pas l'antérieur (binôme c4f3 bis T1) -------------
    def seule_cause_i(self, b: Banc, tid: str, r: subprocess.CompletedProcess, *contient: str) -> None:
        """`retour` rc 1, une ligne `RETOUR (i) refus` portant `contient`, et (i) SEULE
        cause du relevé inscrit : la branche de correction est valide par ailleurs."""
        self.assertEqual(r.returncode, 1, f"relevé admis : {r.stdout}{r.stderr}")
        lignes = [ligne for ligne in r.stdout.splitlines() if ligne.startswith("RETOUR (i) refus")]
        self.assertEqual(len(lignes), 1, r.stdout)
        for x in contient:
            self.assertIn(x, lignes[0])
        causes = b.tache(tid)["retour"]["causes"]
        self.assertEqual([c for c in causes if not c.startswith("(i) refus")], [], causes)

    def d_22(self, bin_: Path) -> None:
        """Le scénario du critique : branche avec `hors.py` → relevé REFUSÉ → fusion quand
        même → branche de correction relevée : (i) refuse, le rejeu aussi (absorbant), le
        `done` aussi."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base1, nom1 = b.branche(tid, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        self.assertEqual(b.retour(tid, base=base1, branche=nom1).returncode, 1, "précondition : (c) refuse hors.py")
        b.fusion(nom1)
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        self.seule_cause_i(b, tid, b.retour(tid, base=base2, branche=nom2), "était refusé", "malgré le refus",
                           "--sans-cible")
        self.seule_cause_i(b, tid, b.retour(tid, base=base2, branche=nom2), "porte déjà un refus (i)")
        b.fusion(nom2)
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-a)")

    def d_22b(self, bin_: Path) -> None:
        """Variante : relevé ok, fusion `--no-commit` qui glisse `hors.py`, branche de
        correction relevée : (i) nomme le passager."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base1, nom1 = b.branche(tid)
        self.assertEqual(b.retour(tid, base=base1, branche=nom1).returncode, 0, "précondition : relevé ok")
        b.g("merge", "-q", "--no-ff", "--no-commit", nom1)
        (b.d / "hors.py").write_text("passager\n", encoding="utf-8")
        b.g("add", "hors.py")
        b.g("commit", "-q", "-m", f"fusion {nom1} avec un passager")
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        self.seule_cause_i(b, tid, b.retour(tid, base=base2, branche=nom2), "hors de son relevé", "hors.py")
        b.fusion(nom2)
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-a)")

    def d_22c(self, bin_: Path) -> None:
        """LE LÉGITIME : un relevé refusé d'une branche SANS commit propre (sa pointe est
        HEAD) n'empêche pas le relevé suivant ; un relevé ok fusionné tel quel n'empêche
        pas celui de la branche de correction ; le `done` est admis."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        base, vide = b.sha(), f"wt/{tid}-vide"
        b.g("branch", vide)
        self.assertEqual(b.retour(tid, base=base, branche=vide).returncode, 1, "précondition : (b) refuse")
        b.g("switch", "-q", vide)
        (b.d / "src").mkdir(exist_ok=True)
        (b.d / "src" / "a.py").write_text("v1\n", encoding="utf-8")
        b.g("add", "src/a.py")
        b.g("commit", "-q", "-m", "dev")
        b.g("switch", "-q", "main")
        r = b.retour(tid, base=base, branche=vide)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertIn("sans commit propre", r.stdout)
        b.fusion(vide)
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        r = b.retour(tid, base=base2, branche=nom2)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — relevé antérieur ok", r.stdout)
        b.fusion(nom2)
        b.verdict(tid)
        self.admis(b.t("done", tid, "--raison", "livré"))

    def d_22d(self, bin_: Path) -> None:
        """Un relevé ok entré dans HEAD par AVANCE RAPIDE : (i) refuse, comme R-b au `done`."""
        b = Banc(self, bin_)
        tid = b.directe()
        base1, nom1 = b.branche(tid)
        self.assertEqual(b.retour(tid, base=base1, branche=nom1).returncode, 0, "précondition : relevé ok")
        b.fusion(nom1, "ff")
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        self.seule_cause_i(b, tid, b.retour(tid, base=base2, branche=nom2), "avance rapide")

    def d_22e(self, bin_: Path) -> None:
        """(i) NON CONCLU (git en panne sur son seul appel) : rc 2, RIEN n'est écrit, le
        relevé antérieur reste en place."""
        if os.name == "nt":
            self.skipTest("faux git en sh : POSIX seulement")
        b = Banc(self, bin_)
        tid = b.directe()
        base1, nom1 = b.branche(tid, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        self.assertEqual(b.retour(tid, base=base1, branche=nom1).returncode, 1, "précondition : relevé refusé")
        b.fusion(nom1)
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        avant = b.board_sha()
        r = b.t("retour", tid, "--base", base2, "--branche", nom2, env=b.panne("--ignore-missing"))
        self.assertEqual(r.returncode, 2, f"{r.stdout}{r.stderr}")
        self.assertIn("(i) non mesuré", r.stderr)
        self.assertIn("rien n'est écrit", r.stderr)
        self.assertEqual(b.board_sha(), avant, "un (i) non conclu a écrit le board")

    def d_22f(self, bin_: Path) -> None:
        """PORTÉE : une tâche PLANIFIÉE (non estampillée) n'entre pas dans (i) — son
        `done` ne lit pas le relevé ; un refus fusionné ne fige pas ses branches suivantes."""
        b = Banc(self, bin_)
        tid = b.nouvelle("planifiée", ["src/a.py"])
        base1, nom1 = b.branche(tid, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        self.assertEqual(b.retour(tid, base=base1, branche=nom1).returncode, 1, "précondition : relevé refusé")
        b.fusion(nom1)
        base2, nom2 = b.branche(tid, {"src/a.py": "v2\n"})
        r = b.retour(tid, base=base2, branche=nom2)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) sans objet", r.stdout)

    def d_22g(self, bin_: Path) -> None:
        """Un relevé CHANGÉ entre la lecture et l'écriture n'est pas écrasé : (i) a
        comparé l'ancien — `BoardError`, le relevé changé reste."""
        b = Banc(self, bin_)
        tid = b.directe()
        base, nom = b.branche(tid)
        self.assertEqual(b.retour(tid, base=base, branche=nom).returncode, 0, "précondition : un relevé antérieur")
        module = charger(bin_)
        vrai = module.retour_mesurer

        def mesurer_puis_forger(*args, **kwargs):
            releve = vrai(*args, **kwargs)
            b.forger(tid, le="2000-01-01T00:00:00Z")
            return releve

        cles = ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM", "CADRE_STATE_DIR", "AGENTS_EVENTS_DIR")
        with mock.patch.dict(os.environ, {k: b.env[k] for k in cles}), \
                mock.patch.object(module, "retour_mesurer", mesurer_puis_forger), \
                self.assertRaises(module.BoardError) as refus:
            module.retour_inscrire(str(b.d), [tid], base, nom)
        self.assertIn("a changé pendant la mesure", str(refus.exception))
        self.assertEqual(b.tache(tid)["retour"]["le"], "2000-01-01T00:00:00Z", "le relevé changé a été écrasé")

    def d_22h(self, bin_: Path) -> None:
        """Pointe antérieure ABSENTE du dépôt (branche supprimée puis nettoyée) : une
        donnée, pas une panne — rc 0. Pointe illisible (relevé forgé) : refus."""
        b = Banc(self, bin_)
        absente = b.directe("absente")
        base, nom = b.branche(absente)
        self.assertEqual(b.retour(absente, base=base, branche=nom).returncode, 0, "précondition : relevé ok")
        b.forger(absente, tip="0123456789abcdef" * 2 + "01234567")
        r = b.retour(absente, base=base, branche=nom)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertIn("absente du dépôt", r.stdout)
        forgee = b.directe("forgée", ["src/b.py"])
        base, nom = b.branche(forgee)
        self.assertEqual(b.retour(forgee, base=base, branche=nom).returncode, 0, "précondition : relevé ok")
        b.forger(forgee, tip="HEAD")
        self.seule_cause_i(b, forgee, b.retour(forgee, base=base, branche=nom), "illisible")

    def d_22i(self, bin_: Path) -> None:
        """L'ABSORPTION EST BORNÉE À LA TÂCHE (binôme c4f3 ter N1). T1 refusée puis
        fusionnée ; Y, nommée pour T2 PUIS T1, porte le refus (i) de T1 et s'inscrit sur
        les deux, puis est abandonnée. W, nommée de même, compare le relevé de CHACUNE
        (aucune déduplication) : le refus de T1 s'y transmet. Z, propre, pour T2 seule :
        rc 0. V pour T1 seule : le refus se transmet toujours."""
        b = Banc(self, bin_)
        t1, t2 = b.directe("t1", ["src/a.py"]), b.directe("t2", ["src/b.py"])
        base, x1 = b.branche(t1, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        self.assertEqual(b.retour(t1, base=base, branche=x1).returncode, 1, "précondition : (c) refuse hors.py")
        b.fusion(x1)
        for attendu in ("était refusé", "porte déjà un refus (i)"):
            base, nom = b.branche(t1, {"src/a.py": "v2\n", "src/b.py": "v2\n"})
            r = b.retour(t2, t1, base=base, branche=nom)
            self.assertEqual(r.returncode, 1, f"{r.stdout}{r.stderr}")
            lignes = [ligne for ligne in r.stdout.splitlines() if ligne.startswith("RETOUR (i) refus")]
            self.assertEqual(len(lignes), 1, r.stdout)
            self.assertIn(f"de {t1} {attendu}", lignes[0])
            b.g("branch", "-D", nom)
        base, z = b.branche(t2, {"src/b.py": "v3\n"})
        r = b.retour(t2, base=base, branche=z)
        self.assertEqual(r.returncode, 0, f"T2 refusée pour le refus de T1 : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — pointe antérieure", r.stdout)
        base, v = b.branche(t1, {"src/a.py": "v3\n"})
        self.seule_cause_i(b, t1, b.retour(t1, base=base, branche=v), f"de {t1} porte déjà un refus (i)")

    def d_22j(self, bin_: Path) -> None:
        """UNE BRANCHE REFUSÉE ENCORE VIVANTE MET LE RELEVÉ NEUF EN SUSPENS (binôme c4f3
        ter N2) : X refusée (hors.py), hors de HEAD, sa branche vit. Le rejeu de X même
        n'est pas en suspens (la pointe neuve la contient). Y relevée : rc 2, rien n'est
        écrit — fusionnée après, X échapperait à (i) ; `--dry-run` le dit refus. Après
        `git branch -D` de X : rc 0."""
        b = Banc(self, bin_)
        tid = b.directe("directe", ["src/a.py", "src/b.py"])
        base1, x = b.branche(tid, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        self.assertEqual(b.retour(tid, base=base1, branche=x).returncode, 1, "précondition : (c) refuse hors.py")
        r = b.retour(tid, base=base1, branche=x)
        self.assertEqual(r.returncode, 1, f"le rejeu de la branche refusée elle-même : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — pointe antérieure", r.stdout)
        base2, y = b.branche(tid, {"src/b.py": "v2\n"})
        avant = b.board_sha()
        r = b.retour(tid, base=base2, branche=y)
        self.assertEqual(r.returncode, 2, f"{r.stdout}{r.stderr}")
        for attendu in ("(i) en suspens", f"sa branche {x} vit encore", "rien n'est écrit"):
            self.assertIn(attendu, r.stderr)
        self.assertEqual(b.board_sha(), avant, "un relevé en suspens a écrit le board")
        r = b.t("retour", tid, "--base", base2, "--branche", y, "--dry-run")
        self.assertEqual(r.returncode, 1, f"--dry-run : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) en suspens", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "RETOUR: refus")
        b.g("branch", "-D", x)
        r = b.retour(tid, base=base2, branche=y)
        self.assertEqual(r.returncode, 0, f"relevé refusé : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — pointe antérieure", r.stdout)

    def d_22k(self, bin_: Path) -> None:
        """LES SORTIES LÉGITIMES DE « en suspens » (binôme c4f3 ter N2) : un antérieur OK
        dont la branche vit hors de HEAD ne l'est pas ; une branche refusée CORRIGÉE
        (pointe réécrite) puis relevée passe ; fusionnée puis supprimée par
        `git branch -d`, elle ne gêne pas le relevé suivant."""
        b = Banc(self, bin_)
        tid = b.directe("directe", ["src/a.py", "src/b.py"])
        base, w = b.branche(tid, {"src/b.py": "w\n"})
        self.assertEqual(b.retour(tid, base=base, branche=w).returncode, 0, "précondition : relevé ok")
        base, x = b.branche(tid, {"src/a.py": "v1\n", "hors.py": "hors\n"})
        r = b.retour(tid, base=base, branche=x)
        self.assertEqual(r.returncode, 1, f"antérieur ok vivant : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — pointe antérieure", r.stdout)
        b.g("switch", "-q", x)
        b.g("rm", "-q", "hors.py")
        b.g("commit", "-q", "--amend", "-m", "dev corrigé")
        b.g("switch", "-q", "main")
        r = b.retour(tid, base=base, branche=x)
        self.assertEqual(r.returncode, 0, f"la branche corrigée puis relevée : {r.stdout}{r.stderr}")
        b.fusion(x)
        b.g("branch", "-d", x)
        base, y = b.branche(tid, {"src/b.py": "v2\n"})
        r = b.retour(tid, base=base, branche=y)
        self.assertEqual(r.returncode, 0, f"après fusion et `branch -d` : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — relevé antérieur ok", r.stdout)

    # -- D4d-D4j, D22l : la livraison, EXACTEMENT deux niveaux (T-01M4WTYSCEYHC6KZF2DC1PXBRN) --
    def livraison(self, b: Banc, *tids: str) -> None:
        """La livraison `integ/l` déclarée sur `tids`, sa branche née sur `main`."""
        b.ok("livraison", *tids, "--branche", "integ/l")
        b.g("branch", "integ/l")

    def lot_vers(self, b: Banc, tid: str, fichiers: dict[str, str] | None = None) -> tuple[str, subprocess.CompletedProcess]:
        """Un lot coupé sur la livraison, relevé `--vers integ/l` : rend `(branche, sortie du relevé)`."""
        b.n += 1
        base, nom = b.sha("integ/l"), f"wt/{tid}-{b.n}"
        fichiers = fichiers or {p: f"{tid} {b.n}\n" for p in b.tache(tid)["writeset"]}
        b.g("switch", "-q", "-c", nom, "integ/l")
        for chemin, contenu in fichiers.items():
            (b.d / chemin).parent.mkdir(parents=True, exist_ok=True)
            (b.d / chemin).write_text(contenu, encoding="utf-8")
        b.g("add", "--", *fichiers)
        b.g("commit", "-q", "-m", f"dev {nom}")
        b.g("switch", "-q", "main")
        return nom, b.t("retour", tid, "--base", base, "--branche", nom, "--vers", "integ/l")

    def dans(self, b: Banc, cible: str, branche: str) -> None:
        """`git merge --no-ff <branche>` dans `cible`, puis retour sur `main`."""
        b.g("switch", "-q", cible)
        b.g("merge", "-q", "--no-ff", "-m", f"fusion {branche} dans {cible}", branche)
        b.g("switch", "-q", "main")

    def sur_l(self, b: Banc, fichiers: dict[str, str], message: str) -> None:
        """Un commit posé DIRECTEMENT sur la livraison (une correction, ou un passager)."""
        b.g("switch", "-q", "integ/l")
        for chemin, contenu in fichiers.items():
            (b.d / chemin).parent.mkdir(parents=True, exist_ok=True)
            (b.d / chemin).write_text(contenu, encoding="utf-8")
        b.g("add", "--", *fichiers)
        b.g("commit", "-q", "-m", message)
        b.g("switch", "-q", "main")

    def livree(self, b: Banc, avec_membre: bool = True) -> str:
        """Le légitime : une directe (et un membre planifié) livrés par `integ/l`, la
        livraison fusionnée dans `main`, le verdict après le relevé. Rend la directe."""
        b.armer_cible()
        tid = b.directe()
        membre = b.nouvelle("planifiée", ["src/b.py"]) if avec_membre else None
        self.livraison(b, tid, *([membre] if membre else []))
        nom, r = self.lot_vers(b, tid)
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        self.dans(b, "integ/l", nom)
        if membre:
            self.sur_l(b, {"src/b.py": "le lot du membre planifié\n"}, "lot du membre")
        return tid

    def d_04d(self, bin_: Path) -> None:
        """LE LÉGITIME : lot → L → main, la fusion de L couverte par l'UNION des write-sets."""
        b = Banc(self, bin_)
        tid = self.livree(b)
        self.dans(b, "main", "integ/l")
        b.verdict(tid)
        self.admis(b.t("done", tid, "--raison", "livré par la livraison"))
        self.assertIn(MARQUE, b.tache(tid)["stage"])

    def d_04e(self, bin_: Path) -> None:
        """Un passager commité sur L, hors des write-sets des membres : refus nommé, remèdes dits."""
        b = Banc(self, bin_)
        tid = self.livree(b)
        self.sur_l(b, {"hors.py": "passager\n"}, "passager sur la livraison")
        self.dans(b, "main", "integ/l")
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b) la fusion de integ/l dans la cible", "hors.py",
                    "hors des write-sets déclarés des membres", "INTÉGRATION", "--sans-cible")

    def d_04f(self, bin_: Path) -> None:
        """La fusion du lot dans L glisse (`--no-commit`) un fichier hors du relevé — dans
        l'union des write-sets : seule la cause « lot → L » le voit."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        membre = b.nouvelle("planifiée", ["src/b.py"])
        self.livraison(b, tid, membre)
        nom, r = self.lot_vers(b, tid)
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        b.g("switch", "-q", "integ/l")
        b.g("merge", "-q", "--no-ff", "--no-commit", nom)
        (b.d / "src" / "b.py").write_text("glissé dans la fusion du lot\n", encoding="utf-8")
        b.g("add", "src/b.py")
        b.g("commit", "-q", "-m", f"fusion {nom} avec un passager")
        b.g("switch", "-q", "main")
        self.dans(b, "main", "integ/l")
        b.verdict(tid)
        err = self.refuse(b.t("done", tid, "--raison", "livré"), "dans integ/l porte 1 fichier(s) hors du relevé",
                          "src/b.py", "n'est pas telle quelle")
        self.assertNotIn("hors des write-sets", err, "la cause n'est pas la bonne")

    def d_04g(self, bin_: Path) -> None:
        """La livraison retirée après le relevé : (R-v)."""
        b = Banc(self, bin_)
        tid = self.livree(b, avec_membre=False)
        self.dans(b, "main", "integ/l")
        b.verdict(tid)
        b.ok("livraison", tid, "--branche", "integ/l", "--retirer")
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-v)", "ne porte plus", "--sans-cible")

    def d_04h(self, bin_: Path) -> None:
        """Le lot a, relevé `--vers`, fusionné DIRECTEMENT dans main ; la livraison déplacée sur main
        (elle contient a), puis le lot b livré par elle : a n'est PAS compté au niveau 2 (la marche
        intérieure part de `M^1`, jamais du départ du relevé) ; b passe."""
        b = Banc(self, bin_)
        b.armer_cible()
        a, c = b.directe("a", ["src/a.py"]), b.directe("b", ["src/b.py"])
        self.livraison(b, a, c)
        nom_a, r = self.lot_vers(b, a)
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        b.fusion(nom_a)
        b.g("branch", "-f", "integ/l", "main")
        nom_c, r = self.lot_vers(b, c)
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        self.dans(b, "integ/l", nom_c)
        self.dans(b, "main", "integ/l")
        b.verdict(a)
        b.verdict(c)
        self.refuse(b.t("done", a, "--raison", "contourné"), "(R-b)", "EXACTEMENT deux niveaux")
        self.admis(b.t("done", c, "--raison", "livré par la livraison"))

    def d_04i(self, bin_: Path) -> None:
        """Une doc commitée sur L hors des write-sets : refus ; le write-set de la DIRECTE étendu
        sans ré-estampille : refus C5 nommé ; ré-estampillée : admise."""
        b = Banc(self, bin_)
        tid = self.livree(b, avec_membre=False)
        self.sur_l(b, {"docs/notes.md": "notes\n"}, "doc sur la livraison")
        self.dans(b, "main", "integ/l")
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "docs/notes.md", "ré-estampille")
        b.ok("writeset", tid, "src/a.py", "docs/notes.md")
        self.refuse(b.t("done", tid, "--raison", "livré"), "C5")
        b.ok("direct", tid)
        self.admis(b.t("done", tid, "--raison", "write-set étendu, ré-estampillé"))

    def d_04j(self, bin_: Path) -> None:
        """Un relevé `--vers` fusionné DIRECTEMENT dans la cible (un niveau) : refus."""
        b = Banc(self, bin_)
        b.armer_cible()
        tid = b.directe()
        self.livraison(b, tid)
        nom, r = self.lot_vers(b, tid)
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        b.fusion(nom)
        b.verdict(tid)
        self.refuse(b.t("done", tid, "--raison", "livré"), "(R-b)", "EXACTEMENT deux niveaux",
                    "contourne la revue de la livraison", "--sans-cible")

    def d_22l(self, bin_: Path) -> None:
        """(i) d'un antérieur `vers` : le re-relevé d'un lot déjà fusionné dans L relit l'antérieur à
        UN niveau depuis la pointe de L (ok) ; L fusionnée dans main PUIS supprimée, un relevé
        suivant (sans `--vers`) le relit à DEUX niveaux depuis HEAD (ok)."""
        b = Banc(self, bin_)
        tid = b.directe()
        self.livraison(b, tid)
        nom, r = self.lot_vers(b, tid, {"src/a.py": "v1\n"})
        self.assertEqual(r.returncode, 0, f"précondition : relevé --vers ok : {r.stdout}{r.stderr}")
        self.dans(b, "integ/l", nom)
        nom, r = self.lot_vers(b, tid, {"src/a.py": "v2\n"})
        self.assertEqual(r.returncode, 0, f"(i) refusé dans la livraison : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — relevé antérieur ok", r.stdout)
        self.dans(b, "integ/l", nom)
        self.dans(b, "main", "integ/l")
        b.g("branch", "-d", "integ/l")
        base, nom = b.branche(tid, {"src/a.py": "v3\n"})
        r = b.retour(tid, base=base, branche=nom)
        self.assertEqual(r.returncode, 0, f"(i) refusé après la fusion de la livraison : {r.stdout}{r.stderr}")
        self.assertIn("RETOUR (i) ok — relevé antérieur ok", r.stdout)

    # -- D23 (T-00000726, étape 7bis) : borne et verdict sous S-id ULID ----------------
    def d_23(self, bin_: Path) -> None:
        """La borne du relevé et le verdict se comparent à la clé d'ORDRE (`sort_key` : tout
        ULID après tout ancien, les ULID par le temps) — E26, S2/S3. R-1 borne ULID, verdict
        ULID postérieur ⇒ admis ; R-2 verdict ULID ANTÉRIEUR ⇒ refus (s) ; R-3 verdict ANCIEN
        ⇒ refus (s) ; R-4 borne ANCIENNE, verdict ULID ⇒ admis (le premier cas réel après
        B3). Une borne ULID lisible ne lève JAMAIS (R-d), et un refus dit SA cause (C7 :
        sous `int`/-1, R-2 et R-3 refusaient déjà, mais par (R-d)). MUTANT M42."""
        self.assertTrue(all(re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", u) for u in (U0, U_LETTER, U_DIGIT))
                        and U0 < U_LETTER < U_DIGIT, "précondition des fixtures ULID")
        sans_verdict = "(s) aucun verdict de sécurité tracé après le relevé"
        cas = (("R-1", f"S-{U_LETTER}", f"S-{U_DIGIT}", None), ("R-2", f"S-{U_LETTER}", f"S-{U0}", sans_verdict),
               ("R-3", f"S-{U_LETTER}", "S-00009999", sans_verdict), ("R-4", "S-00000005", f"S-{U_DIGIT}", None))
        b = Banc(self, bin_)
        b.armer_cible()
        for i, (nom, borne, sid, refus) in enumerate(cas):
            tid = b.directe(f"directe {nom}", [f"src/r{i}.py"])
            b.specs_chemin().write_text(json.dumps({"entries": [entree(borne, tid, "delta", "borne")]}),
                                        encoding="utf-8")
            b.livrer(tid, titre=None)
            self.assertEqual(borne, b.tache(tid)["retour"]["specs_borne"], f"{nom} : précondition, la borne")
            b.verdict(tid, GO, sid=sid)
            r = b.t("done", tid, "--raison", nom)
            self.assertNotIn("(R-d)", r.stderr, f"{nom} : (R-d) sur une borne lisible")
            if refus:
                self.refuse(r, refus)
            else:
                self.admis(r)


class RetourDoneTests(Temoins, unittest.TestCase):
    """Chaque témoin sur le VRAI `.agents/bin`."""


for _nom in sorted(n for n in dir(Temoins) if n.startswith("d_")):
    setattr(RetourDoneTests, "test_" + _nom[2:], (lambda n: lambda self: getattr(self, n)(BIN))(_nom))


#: Les mutants : `nom → ({fichier: [(ancre, remplacement)]}, témoin)`. Chaque ancre est
#: un FRAGMENT LITTÉRAL présent UNE fois (asserté par `copie`).
_R, _ETATS = "tasks_retour.py", "tasks_etats.py"
_PRE = "            pre = None if args.sans_cible else retour_premesure(root, args.tid)\n"
#: M42 (7bis) : le rang à deux étages de `direct_rang_specs`, et l'`int` d'avant qu'il remplace.
_RANG_DEUX_ETAGES = ('    if not re.fullmatch(r"S-(?:" + ULID_BODY + r"|[0-9]{1,15})", sid):\n'
                     "        return DIRECT_RANG_ILLISIBLE\n    return sort_key(sid)\n")
_RANG_INT = '    m = re.fullmatch(r"S-([0-9]+)", sid)\n    return int(m.group(1)) if m else -1\n'
#: Le LIEN porteur-tâche de `retour_refus_securite` (T-01M5F728FGJ43QJX1RJKTWWKRB) : même portée ou même groupe.
_LIEN = ('\n                     and ((couverte and autre.get("id") in portee["members"])\n'
         '                          or (groupe and parallel_group_of(autre) == groupe))]')
MUTANTS = {
    "jambe retirée": ({_ETATS: [('        if state == "done" and marque_dir and not sans_cible:\n',
                                 "        if False:\n")]}, "d_02"),
    "pré-mesure retirée du dispatch": ({"tasks.py": [(_PRE, "            pre = None\n")]}, "d_01"),
    "None admis": ({_R: [("        if pre is None:\n            causes.append(",
                          "        if pre is None:\n            pass\n        elif False:\n            causes.append(")]}, "d_19"),
    "R-b sans R-a": ({_R: [('    if admis:\n        tip = releve.get("tip")\n',
                            '    if True:\n        tip = releve.get("tip")\n')]}, "d_03"),
    "verdict refus admis": ({_R: [('    admis = releve.get("verdict") == "ok"\n', "    admis = True\n")]}, "d_03"),
    "fusion non contrôlée": ({_R: [("        elif not any(len(p) >= 3 and p[2] == tip",
                                    "        elif False and not any(len(p) >= 3 and p[2] == tip")]}, "d_04"),
    "avance rapide admise": ({_R: [('"--first-parent", "--merges", "--parents",', '"--first-parent", "--parents",'),
                                   ("len(p) >= 3 and p[2] == tip", "tip in p")]}, "d_04b"),
    "fusion imbriquée admise": ({_R: [('"rev-list", "--first-parent", "--merges",', '"rev-list", "--merges",')]}, "d_04c"),
    "toute fusion admise": ({_R: [("p[2] == tip for p in", 'p[2] != "" for p in')]}, "d_05"),
    "contenu de la fusion non comparé": ({_R: [("        hors = [f for f in contenu if f not in releves]\n",
                                                "        hors = []\n")]}, "d_20"),
    "contenu de la fusion non lu": ({_R: [(
        '                contenus[p[0]] = sorted({retour_lisible(f) for f in brut.split("\\0") if f})\n',
        "                contenus[p[0]] = []\n")]}, "d_20"),
    "fsmonitor du dépôt exécuté": ({_R: [('"-c", "core.fsmonitor=false",\n', "\n")]}, "d_21"),
    "contenu non mesuré admis": ({_R: [("        if not isinstance(contenu, list):\n",
                                        "        if not isinstance(contenu, list):\n            continue\n")]}, "d_20b"),
    "R-c couverture retirée": ({_R: [("if not (isinstance(f, str) and any(retour_couvre(e, f) for e in vus))]",
                                      "if False]")]}, "d_06"),
    "compte retiré": ({_R: [("        if len(fichiers) > MAX_FICHIERS_DIRECT:\n", "        if False:\n")]}, "d_06b"),
    # R38 (7bis) : sous les rangs à DEUX étages, `> -1` comparerait un tuple à un `int` (TypeError,
    # mutant tué pour une MAUVAISE raison) : la borne ignorée est `> DIRECT_RANG_ILLISIBLE`.
    "borne ignorée": ({_R: [("and direct_rang_specs(e) > rang_borne]",
                             "and direct_rang_specs(e) > DIRECT_RANG_ILLISIBLE]")]}, "d_07"),
    "s1 retiré": ({_R: [('    causes = [f"(s) {c}" for c in direct_causes_securite({}, [dernier])]\n',
                         "    causes = []\n")]}, "d_08"),
    "absence non lue": ({_R: [("        jeton = direct_porte_lexique(direct_normaliser(dernier.get(champ)), RETOUR_SECU_ABSENT)\n",
                               "        jeton = None\n")]}, "d_08"),
    "texte non lu pour l'absence": ({_R: [('    for champ, nom in (("title", "titre"), ("text", "texte")):\n        jeton',
                                           '    for champ, nom in (("title", "titre"),):\n        jeton')]}, "d_08"),
    "premier verdict": ({_R: [("max(candidats, key=lambda c: c[0])", "min(candidats, key=lambda c: c[0])")]}, "d_08"),
    "slot ignoré": ({_R: [("    if couverte or groupe:\n        porteurs +=", "    if False:\n        porteurs +=")]}, "d_09"),
    # T-01M5F728FGJ43QJX1RJKTWWKRB : l'emprunt passe par la portée ou le groupe, plus par le chantier.
    "tout chantier": ({_R: [("    if couverte or groupe:\n", "    if True:\n"), (_LIEN, "]")]}, "d_09"),
    "emprunt hors portée accepté": ({_R: [("    if couverte or groupe:\n", "    if True:\n"), (_LIEN, "]")]},
                                    "d_T2_cannot_borrow_T1_security"),
    "emprunt par chantier": ({_R: [("    if couverte or groupe:\n", "    if True:\n"),
                                   (_LIEN, " and chantier_of(autre) == chantier_of(task) != \"\"]")]},
                             "d_T2_cannot_borrow_T1_security"),
    "portée ignorée": ({_R: [("    couverte = portee_couvre(portee, task[\"id\"])\n", "    couverte = False\n")]},
                       "d_security_after_retour_before_scope_accepted"),
    "sécurité après declared_at seulement": ({_R: [(
        "and direct_rang_specs(e) > rang_borne]",
        "and direct_rang_specs(e) > rang_borne and (porteur == task[\"id\"] or str(e.get(\"date\")) >= "
        "str((portee or {}).get(\"declared_at\")))]")]}, "d_security_after_retour_before_scope_accepted"),
    "emprunt tu": ({_R: [('    return [], f"[revue de sécurité empruntée au slot',
                          '    return [], "" and f"[revue de sécurité empruntée au slot')]}, "d_09"),
    "SANS RELEVÉ tu (C1)": ({_ETATS: [('            marque_dir = f"{marque_dir} [SANS RELEVÉ : {sans_cible}]"\n',
                                       "            pass\n")]}, "d_10a"),
    "SANS RELEVÉ tu sous cible armée": ({_ETATS: [(
        '        if state == "done" and marque_dir and sans_cible:\n',
        '        if state == "done" and marque_dir and sans_cible and not cible_marqueur_present(root):\n')]}, "d_10b"),
    "SANS RELEVÉ dans un dépôt désarmé": ({_ETATS: [(
        '        if state == "done" and marque_dir and sans_cible:\n',
        '        if state == "done" and sans_cible:\n            marque_dir = marque_dir or "[DIRECT SANS PLAN : x]"\n'
        '        if state == "done" and marque_dir and sans_cible:\n')]}, "d_10b"),
    "SANS RELEVÉ hors du pont (C1)": ({_ETATS: [('            marque_dir = f"{marque_dir} [SANS RELEVÉ : {sans_cible}]"\n',
                                                 "            pass\n")]}, "d_10c"),
    "SPECS illisible admis": ({_R: [("    except (pc.CibleError, OSError, ValueError) as exc:\n        return [f\"(s) SPECS illisible",
                                     "    except (pc.CibleError, OSError, ValueError) as exc:\n        return [], \"\"\n"
                                     "        return [f\"(s) SPECS illisible")]}, "d_12"),
    "R-d retiré": ({_R: [('    if direct_rang_specs({"id": releve.get("specs_borne")}) == DIRECT_RANG_ILLISIBLE:\n',
                          "    if False:\n")]}, "d_12"),
    "id du kit dans un refus": ({_R: [('RETOUR_SORTIE = "la seule sortie tracée est',
                                       'RETOUR_SORTIE = "(S-00004192) la seule sortie tracée est')]}, "d_14"),
    "(c) directe seule retirée": ({_R: [('if "direct" in tache) if len(nommees) > 1 else []',
                                         'if "direct" in tache) if False else []')]}, "d_15a"),
    "R-t retiré": ({_R: [('        if ident != task["id"]:\n            autres.append(ident)',
                          "        if False:\n            autres.append(ident)")]}, "d_15b"),
    "find nu": ({_R: [("        except BoardError:\n            causes.append(f\"(R-t) le relevé nomme « ",
                       "        except ZeroDivisionError:\n            causes.append(f\"(R-t) le relevé nomme « ")]}, "d_15c"),
    "pré-mesure sous le verrou": ({"tasks.py": [(_PRE, "            with board_lock(root):\n    " + _PRE)]}, "d_17a"),
    "clé non comparée": ({_R: [('        elif tuple(pre["cle"]) != (releve.get("base"), tip, releve.get("le")):\n',
                                "        elif False:\n")]}, "d_17b"),
    "pop retiré au reopen": ({"tasks_verbes.py": [('        task.pop("retour", None)\n', "")]}, "d_18"),
    "pop retiré au start depuis done": ({_ETATS: [('            if before["state"] == "done":\n'
                                                   '                task.pop("retour", None)\n', "")]}, "d_18c"),
    # -- (i), binôme c4f3 bis T1 : un relevé neuf n'efface pas l'antérieur ------------
    "(i) neutralisé": ({_R: [("    anterieurs = retour_anterieurs(tids, data)\n",
                              "    anterieurs = []\n")]}, "d_22"),
    "(i) non absorbant": ({_R: [('c.startswith("(i) refus") and', 'c.startswith("(i) jamais") and')]}, "d_22"),
    "relevé refusé fusionné admis": ({_R: [('    if prec.get("verdict") != "ok":\n        return ("i", "refus"',
                                            '    if False:\n        return ("i", "refus"')]}, "d_22"),
    "passagers antérieurs non comparés": ({_R: [(
        '        passagers = sorted({retour_lisible(f) for f in brut.split("\\0") if f} - couverts)\n',
        "        passagers = []\n")]}, "d_22b"),
    "sans commit propre ignoré": ({_R: [('    if lisible and retour_git(racine, "rev-list", "--count", "--ignore-missing"',
                                         '    if False and retour_git(racine, "rev-list", "--count", "--ignore-missing"')]},
                                  "d_22c"),
    "fusion antérieure jamais trouvée": ({_R: [("        if len(p) > 2 and p[2] == pointe]\n",
                                                "        if False]\n")]}, "d_22c"),
    "avance rapide antérieure admise": ({_R: [('    if not fusions:\n        return ("i", "refus"',
                                               '    if False:\n        return ("i", "refus"')]}, "d_22d"),
    "(i) non conclu écrit": ({_R: [('    retour_non_conclu(releve["controles"])\n', "")]}, "d_22e"),
    "panne de (i) lue ok": ({_R: [('            out.append(("i", "non mesuré", f"relevé antérieur de {tid} : {exc}',
                                   '            out.append(("i", "ok", f"relevé antérieur de {tid} : {exc}')]}, "d_22e"),
    "(i) sur toute tâche": ({_R: [('        if "direct" not in tache or not isinstance(prec, dict):\n',
                                   "        if not isinstance(prec, dict):\n")]}, "d_22f"),
    "relevé changé non vu": ({_R: [('            if task.get("retour") != find(lu, tid).get("retour"):\n',
                                    "            if False:\n")]}, "d_22g"),
    "absence lue comme panne": ({_R: [('    if not retour_git(racine, "rev-list", "--no-walk", "--ignore-missing", pointe)',
                                       '    if False and retour_git(racine, "rev-list", "--no-walk", "--ignore-missing", pointe)')]},
                                "d_22h"),
    "pointe illisible admise": ({_R: [("    if not (isinstance(pointe, str) and re.fullmatch(RETOUR_SHA_PLEIN, pointe)):\n",
                                       "    if False:\n")]}, "d_22h"),
    # -- (i), binôme c4f3 ter N1 : l'absorption bornée à la tâche ---------------------
    "(i) absorbant non borné à la tâche": ({_R: [('c.startswith("(i) refus") and f" de {tid} " in c\n',
                                                  'c.startswith("(i) refus")\n')]}, "d_22i"),
    "déduplication rétablie": ({_R: [('        out.append((tache["id"], prec))\n',
                                      '        if prec not in [p for _, p in out]:\n'
                                      '            out.append((tache["id"], prec))\n')]}, "d_22i"),
    # -- (i), binôme c4f3 ter N2 : une branche refusée encore vivante ----------------
    "en suspens retiré": ({_R: [('        if (prec.get("verdict") != "ok" and isinstance(branche, str) and branche\n',
                                 '        if (False and isinstance(branche, str) and branche\n')]}, "d_22j"),
    "en suspens écrit": ({_R: [('if x == "i" and etat in ("non mesuré", "non évalué", "en suspens")]',
                                'if x == "i" and etat in ("non mesuré", "non évalué")]')]}, "d_22j"),
    "en suspens hors des refus": ({_R: [('RETOUR_ETATS_REFUS = ("refus", "non mesuré", "non évalué", "en suspens")',
                                         'RETOUR_ETATS_REFUS = ("refus", "non mesuré", "non évalué")')]}, "d_22j"),
    "pointe neuve ignorée": ({_R: [("                and not (tip and retour_ancetre(racine, pointe, tip))):\n",
                                    "                and True):\n")]}, "d_22j"),
    "branche vivante à toute pointe": ({_R: [("retour_ref_existe(racine, RETOUR_PREFIXE_REF + branche) == pointe\n",
                                              'retour_ref_existe(racine, RETOUR_PREFIXE_REF + branche) != ""\n')]},
                                       "d_22k"),
    "antérieur ok en suspens": ({_R: [('(prec.get("verdict") != "ok" and isinstance(branche, str)',
                                       "(isinstance(branche, str)")]}, "d_22k"),
    # -- 7bis (T-00000726) : M42, le rang de la voie directe rendu à l'`int` d'avant (-1 sur un ULID) --
    "M42 rang int": ({"tasks_direct.py": [(_RANG_DEUX_ETAGES, _RANG_INT)]}, "d_23"),
    # -- la livraison, étape 7 du plan T-01M4WTYSCEYHC6KZF2DC1PXBRN ----------------------
    "(R-v) retiré": ({_R: [('    if "vers" in releve and (livraison_de(task) or {}).get("branche") != releve.get("vers"):\n',
                            "    if False:\n")]}, "d_04g"),
    "vers ignoré": ({_R: [('        elif "vers" in releve:\n            causes += retour_refus_livraison(',
                           "        elif False:\n            causes += retour_refus_livraison(")]}, "d_04d"),
    "un niveau admis sous vers": ({_R: [('    if not paires:\n        return [f"(R-b) la pointe relevée',
                                         '    if not paires and not any(len(q) > 2 and q[2] == tip for q in '
                                         '(x.split() for x in pre.get("lignes") or [])):\n'
                                         '        return [f"(R-b) la pointe relevée')]}, "d_04j"),
    "contenu de livraison non comparé": ({_R: [(
        "        hors_ws = [f for f in contenu_cible if not any(retour_couvre(e, f) for e in couverture)]\n",
        "        hors_ws = []\n")]}, "d_04e"),
    "contenu du lot dans L non comparé": ({_R: [("        hors_lot = [f for f in contenu_lot if f not in fichiers_releve]\n",
                                                 "        hors_lot = []\n")]}, "d_04f"),
    "union réduite à la tâche": ({_R: [("    membres = livraison_membres(data, task) or [task]\n",
                                        "    membres = [task]\n")]}, "d_04d"),
    "M-W1 niveau 2 sur depart..X": ({_R: [('f"{externe[1]}..{externe[2]}"', 'f"{depart}..{externe[2]}"')]}, "d_04h"),
    "M-W2 deux niveaux depuis la pointe de V": ({_R: [("            head = pointe_v\n",
                                                       "            head, deux_niveaux = pointe_v, True\n")]}, "d_22l"),
    "antérieur vers lu à un niveau dans HEAD": ({_R: [("    if vers is not None and retour_ancetre(racine, pointe, head):\n",
                                                       "    if False:\n")]}, "d_22l"),
}


class RetourDoneMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant de `MUTANTS` rejoue SON témoin et doit le faire échouer."""

    def tuer(self, nom: str) -> None:
        mutations, temoin = MUTANTS[nom]
        variante = copie(self, BIN, mutations)
        with self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
            getattr(self, temoin)(variante)

    def test_la_variante_non_mutee_est_verte(self):
        """NON-VACUITÉ du harnais : une copie SANS mutation passe un témoin de chaque
        famille — un mutant n'est pas tué par la seule copie."""
        variante = copie(self, BIN, {})
        for temoin in ("d_01", "d_09", "d_10a", "d_19", "d_22c"):
            getattr(self, temoin)(variante)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n in MUTANTS}
# Deux mutants au MÊME nom de test : le second écraserait le premier en silence.
assert len(_GENERES) == len(MUTANTS), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(RetourDoneMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


class PromptSessionDirecteTests(unittest.TestCase):
    """D16 : le gabarit de la session directe ne PRESCRIT plus `--sans-cible` au `done`
    d'une directe et nomme `git merge --no-ff`. Surface du KIT : la classe SE TAIT, en
    le DISANT, là où le fichier est absent (chez l'adoptant)."""

    def setUp(self):
        if not PROMPT.is_file():
            self.skipTest("docs/tasks/PROMPT-SESSION-DIRECT.md absent : surface du kit, D16 non joué")

    def verifier(self, texte: str) -> None:
        for litteral in PRESCRIPTIONS:
            self.assertNotIn(litteral, texte, "le gabarit prescrit encore --sans-cible au done d'une directe")
        self.assertIn("git merge --no-ff", texte, "le gabarit ne nomme pas `git merge --no-ff`")
        # T-00001090 (binôme octies F5) : la reprise ne détruit jamais un dev en vol.
        self.assertNotRegex(texte, r"git branch -D\s+wt/", "le gabarit prescrit `git branch -D wt/…`")
        self.assertNotIn("git worktree remove --force", texte, "le gabarit prescrit `worktree remove --force`")

    def test_d16(self):
        self.verifier(PROMPT.read_text(encoding="utf-8"))

    def test_d16_mutants(self):
        texte = PROMPT.read_text(encoding="utf-8")
        mutants = {"prescription datée rétablie": texte + "\n" + PRESCRIPTIONS[0] + "\"\n",
                   "prescription S- rétablie": texte + "\n" + PRESCRIPTIONS[1] + "\n",
                   "gabarit sans --no-ff": texte.replace("git merge --no-ff", "git merge"),
                   "reprise destructrice rétablie": texte + "\n`git worktree remove --force <chemin>` puis `git branch -D wt/<T>`\n"}
        for nom, mute in mutants.items():
            with self.subTest(nom), self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
                self.verifier(mute)


if __name__ == "__main__":
    unittest.main()
