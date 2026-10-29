#!/usr/bin/env python3
"""Témoins de `.agents/bin/loadtest.py` — runner déterministe k6 (T-01M4JC50S6CTJ5HJ697929E6N7).

CE QU'ILS PROUVENT. Les codes de sortie du contrat (0 GO, 1 NO_GO, 2 REFUS,
3 DEGRADED) observés de l'EXTÉRIEUR : en sous-processus (`sys.executable`), ou
par `main(argv)` quand une primitive doit être patchée (charge machine, cœurs,
horloge, délai dur, adaptateur cloud). k6 n'est JAMAIS requis : un faux `k6`
(script /bin/sh qui exécute un corps Python), réglé par les variables
FAKE_K6_*, est posé en tête du PATH. Le témoin d'interruption lance le runner
en sous-processus et lui envoie SIGTERM/SIGHUP (SIGKILL en contrôle), puis, premier
et second signal croisés dans {SIGTERM, SIGINT}, un second signal pendant
l'écriture de la trace. Les deux témoins à k6 réel
(smoke, proxy) sont opt-in (`AGENTS_LOADTEST_REAL=1`) ; l'opt-in posé et k6
absent, ils ÉCHOUENT (un skip serait un vert qui ne mesure rien).

ISOLEMENT. Verrou de porte (`VERIFY_WORKTREE_DIR`), répertoire de trace
(`AGENTS_LOADTEST_STATE`) et SPECS (`AGENTS_SPECS_PATH`) sont injectés sous
tmp_path ; le dépôt git des seuils est construit sous tmp_path, identité de
commit par `-c user.name -c user.email`, hooks coupés. Aucun parcours du dépôt.

PORTÉE OS : mesuré macOS ; Linux assumé ; Windows non mesuré — les témoins qui
exécutent le faux k6 ou lisent un pid de verrou sautent hors POSIX, nommément.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import ipaddress
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "loadtest.py"
EXEMPLE = ROOT / ".agents" / "ref" / "loadtest-targets.example.json"
POSIX = os.name == "posix"
posix_seul = pytest.mark.skipif(not POSIX, reason="faux k6 en script /bin/sh et pid de verrou : non mesuré sous Windows")


def _charger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loadtest", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loadtest"] = mod  # les dataclasses à annotations différées y lisent leur module
    spec.loader.exec_module(mod)
    return mod


loadtest = _charger()

SCENARIO = "import http from 'k6/http';\nexport default function () { http.get(__ENV.TARGET_URL); }\n"
FENETRE_JOUR = {"debut": "00:00", "fin": "24:00", "tz": "Europe/Paris"}
CIBLE_LOCALE = {"name": "demo-local", "url": "http://127.0.0.1:9", "env": "local",
                "allowed_profiles": ["smoke", "charge", "stress", "endurance"], "fenetre": FENETRE_JOUR}
LIGNE_SEUILS = "SEUILS: p95<=500ms,err<=1%,rps>=10"

FAUX_K6 = """\
import json, os, signal, subprocess, sys, time
argv = sys.argv[1:]
if os.environ.get("FAKE_K6_ARGV"):
    with open(os.environ["FAKE_K6_ARGV"], "w", encoding="utf-8") as fh:
        json.dump(argv, fh)
if os.environ.get("FAKE_K6_PID"):
    with open(os.environ["FAKE_K6_PID"], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
if os.environ.get("FAKE_K6_ENV"):
    with open(os.environ["FAKE_K6_ENV"], "w", encoding="utf-8") as fh:
        json.dump(sorted(os.environ), fh)
if os.environ.get("FAKE_K6_ECHO"):
    print(os.environ["FAKE_K6_ECHO"], flush=True)
if os.environ.get("FAKE_K6_PETIT_ENFANT"):
    enfant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    with open(os.environ["FAKE_K6_PETIT_ENFANT"], "w", encoding="utf-8") as fh:
        fh.write(str(enfant.pid))
time.sleep(float(os.environ.get("FAKE_K6_DORT", "0")))
synthese = os.environ.get("FAKE_K6_SYNTHESE", "valide")
chemin = argv[argv.index("--summary-export") + 1]
metrics = {
    "http_req_duration": {"avg": 1.0, "p(95)": float(os.environ.get("FAKE_K6_P95", "100"))},
    "http_req_failed": {"passes": 0, "fails": 1, "value": float(os.environ.get("FAKE_K6_ERR", "0"))},
    "http_reqs": {"count": 1, "rate": float(os.environ.get("FAKE_K6_RPS", "50"))},
    "vus_max": {"value": 1, "min": 1, "max": 1},
}
if synthese == "incomplete":
    del metrics["http_reqs"]
if os.environ.get("FAKE_K6_SANS_VUS"):  # k6 v2.3.0 l'omet d'un court run à `iterations` (mesuré)
    del metrics["vus_max"]
if synthese in ("valide", "incomplete"):
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump({"metrics": metrics}, fh)
elif synthese == "tronquee":
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write('{"metrics": {"http_req_dur')
rc = os.environ.get("FAKE_K6_RC", "0")
if rc == "signal":
    os.kill(os.getpid(), signal.SIGKILL)
sys.exit(int(rc))
"""

# Lancé en `python -c` : la MÊME panne, derrière la garde de tête (`main`) ou nue
# (`_principal`) — la seconde prouve que c'est la garde qui rend 3 et non 1.
PANNE = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('loadtest', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec)\n"
    "sys.modules['loadtest'] = m\n"
    "spec.loader.exec_module(m)\n"
    "def boom(*a, **k):\n"
    "    raise KeyError('panne')\n"
    "m.charger_config = boom\n"
    "sys.exit(getattr(m, sys.argv[2])(sys.argv[3:]))\n"
)

# Lancé en `python -c` : `ecrire_trace` pose un marqueur puis dort AVANT d'écrire, pour
# qu'un second signal tombe PENDANT l'écriture de la trace, et non après la sortie.
# SIGINT remis au gestionnaire natif : hérité ignoré (lancement en arrière-plan), le
# témoin du second SIGINT serait vert sans le correctif.
TRACE_LENTE = (
    "import importlib.util, signal, sys, time\n"
    "signal.signal(signal.SIGINT, signal.default_int_handler)\n"
    "spec = importlib.util.spec_from_file_location('loadtest', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec)\n"
    "sys.modules['loadtest'] = m\n"
    "spec.loader.exec_module(m)\n"
    "reelle = m.ecrire_trace\n"
    "def lente(enreg):\n"
    "    open(sys.argv[2], 'w', encoding='utf-8').close()\n"
    "    time.sleep(1.5)\n"
    "    return reelle(enreg)\n"
    "m.ecrire_trace = lente\n"
    "sys.exit(m.main(sys.argv[3:]))\n"
)


def _env_git() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _json(texte: str) -> dict:
    lignes = [ligne for ligne in texte.splitlines() if ligne.strip()]
    if not lignes:
        return {}
    try:
        return json.loads(lignes[-1])
    except ValueError:
        return {"_brut": texte}


def _mort_sous(pid: int, secondes: float) -> bool:
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        time.sleep(0.1)
    return False


def _attendre_pid(fichier: Path, secondes: float) -> int | None:
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        try:
            return int(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.05)
    return None


def decision(id_: str, texte: str, kind: str = "decision", title: str = "Décision pilote") -> dict:
    return {"id": id_, "kind": kind, "task": "T-00000001", "title": title, "text": texte,
            "files": [], "date": "2026-10-08"}


def cible_prod(nom: str = "boutique-prod", url: str = "https://shop.example.com/",
               decision_pilote: str | None = "S-00000001") -> dict:
    c = {"name": nom, "url": url, "env": "prod", "allowed_profiles": ["smoke"], "fenetre": FENETRE_JOUR}
    if decision_pilote is not None:
        c["decision_pilote"] = decision_pilote
    return c


class Banc:
    """Arbre jetable : faux k6 en tête de PATH, dépôt git des seuils, config, état."""

    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        git = shutil.which("git")
        if git is None:
            pytest.skip("git absent : la provenance des seuils exige un dépôt git")
        self.git_reel = os.path.realpath(git)
        self.tmp, self.mp = tmp, monkeypatch
        self.path_origine = os.environ.get("PATH", "")
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.etat = tmp / "etat"
        self.verify = tmp / "verify"
        self.argv_k6 = tmp / "argv_k6.json"
        self.depot = tmp / "depot"
        self.depot.mkdir()
        self._poser_faux_k6()
        for nom in list(os.environ):
            if (nom.startswith("FAKE_K6_") or nom == "AGENTS_SPECS_PATH" or loadtest.est_variable_jeton(nom)
                    or nom.upper().startswith("K6_") or nom.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")):
                monkeypatch.delenv(nom)
        monkeypatch.setenv("PATH", os.pathsep.join([str(self.bin), os.path.dirname(self.git_reel)]))
        monkeypatch.setenv("AGENTS_LOADTEST_STATE", str(self.etat))
        monkeypatch.setenv("VERIFY_WORKTREE_DIR", str(self.verify))
        monkeypatch.setenv("FAKE_K6_ARGV", str(self.argv_k6))
        self.git("-c", "init.defaultBranch=main", "init", "-q", ".")
        self.seuils = self.committer("SEUILS.md", f"# Seuils de charge\n\n{LIGNE_SEUILS}\n")
        self.script = tmp / "scenario.js"
        self.script.write_text(SCENARIO, encoding="utf-8")
        self.config = self.ecrire_config([CIBLE_LOCALE])

    def _poser_faux_k6(self) -> None:
        corps = self.tmp / "faux_k6.py"
        corps.write_text(FAUX_K6, encoding="utf-8")
        k6 = self.bin / "k6"
        k6.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(corps))} "$@"\n',
                      encoding="utf-8")
        k6.chmod(0o755)

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-c", "user.name=banc", "-c", "user.email=banc@example.com",
                               "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                               "-c", "commit.gpgsign=false", *args],
                              cwd=self.depot, env=_env_git(), capture_output=True, text=True,
                              check=True, timeout=60)

    def committer(self, nom: str, contenu: str) -> Path:
        chemin = self.depot / nom
        chemin.write_text(contenu, encoding="utf-8")
        self.git("add", "--", nom)
        self.git("commit", "-q", "-m", f"banc: {nom}")
        return chemin

    def ecrire_config(self, cibles: list[dict], max_load1: float | None = 1000, nom: str = "targets.json") -> Path:
        brut: dict = {"targets": cibles}
        if max_load1 is not None:
            brut["local"] = {"max_load1": max_load1}
        chemin = self.tmp / nom
        chemin.write_text(json.dumps(brut), encoding="utf-8")
        return chemin

    def ecrire_specs(self, entrees: list[dict]) -> Path:
        chemin = self.tmp / "SPECS.json"
        chemin.write_text(json.dumps({"entries": entrees, "next_id": 9}), encoding="utf-8")
        self.mp.setenv("AGENTS_SPECS_PATH", str(chemin))
        return chemin

    def argv_run(self, *extra: str, target: str = "demo-local", profil: str = "smoke",
                 seuils: Path | None = None, config: Path | None = None) -> list[str]:
        return ["run", "--target", target, "--profil", profil, "--script", str(self.script),
                "--seuils-de", str(seuils or self.seuils), "--config", str(config or self.config), *extra]

    def lancer(self, argv: list[str], **env: str) -> SimpleNamespace:
        """En sous-processus : le code de sortie est celui que voit un appelant."""
        e = dict(os.environ)
        e.update(env)
        p = subprocess.run([sys.executable, str(SCRIPT), *argv], env=e, capture_output=True,
                           text=True, encoding="utf-8", timeout=180)
        return SimpleNamespace(rc=p.returncode, json=_json(p.stdout), err=p.stderr)

    def main(self, capsys: pytest.CaptureFixture, argv: list[str]) -> SimpleNamespace:
        """En processus, pour les primitives patchées ; `main` rend le code de sortie."""
        capsys.readouterr()
        rc = loadtest.main(list(argv))
        out, err = capsys.readouterr()
        return SimpleNamespace(rc=rc, json=_json(out), err=err)

    def traces(self) -> list[dict]:
        chemin = self.etat / "runs.jsonl"
        if not chemin.exists():
            return []
        return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne]


@pytest.fixture
def banc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Banc:
    return Banc(tmp_path, monkeypatch)


def _rc_motif(s: SimpleNamespace) -> tuple:
    return s.rc, s.json.get("motif")


def _rc_verdict(s: SimpleNamespace) -> tuple:
    return s.rc, s.json.get("verdict")


# --- production -----------------------------------------------------------------------

def test_refus_prod_sans_decision_pilote(banc):
    banc.ecrire_specs([decision("S-00000001", "Tir de charge autorisé sur shop.example.com.")])
    argv = banc.argv_run("--dry-run", target="boutique-prod")
    banc.ecrire_config([cible_prod(decision_pilote=None)])
    assert _rc_motif(banc.lancer(argv)) == (2, "prod_sans_decision")
    banc.ecrire_config([cible_prod(decision_pilote="S-1")])
    assert _rc_motif(banc.lancer(argv)) == (2, "prod_decision_forme")
    banc.ecrire_config([cible_prod()])
    s = banc.lancer(argv, AGENTS_SPECS_PATH=str(banc.tmp / "absent.json"))
    assert _rc_motif(s) == (2, "specs_absent"), s
    # contrôle : décision présente et qui nomme l'hôte
    assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN")


def test_refus_prod_decision_qui_ne_nomme_pas_la_cible(banc):
    banc.ecrire_config([cible_prod()])
    argv = banc.argv_run("--dry-run", target="boutique-prod")
    refuses = {
        "autre hôte": "Feu vert pour un tir de charge sur autre.example.org.",
        "sous-domaine": "Feu vert pour un tir de charge sur staging.shop.example.com.",
        "suffixe": "Feu vert sur shop.example.com-v2 seulement.",
    }
    for cas, texte in refuses.items():
        banc.ecrire_specs([decision("S-00000001", texte)])
        s = banc.lancer(argv)
        assert _rc_motif(s) == (2, "prod_decision_ne_nomme_pas_la_cible"), (cas, s)
        assert "shop.example.com" in s.json["detail"], cas
    banc.ecrire_specs([decision("S-00000001", "Tir sur shop.example.com.", kind="question")])
    assert _rc_motif(banc.lancer(argv)) == (2, "prod_decision_introuvable")
    banc.ecrire_specs([decision("S-00000002", "Tir sur shop.example.com.")])
    assert _rc_motif(banc.lancer(argv)) == (2, "prod_decision_introuvable")
    # contrôles positifs : l'hôte en mot entier, casse indifférente, dans text OU title
    banc.ecrire_specs([decision("S-00000001", "Feu vert : tir de charge sur SHOP.example.com.")])
    s = banc.lancer(argv)
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert s.json["decision_pilote"]["temoin"] == "hote"
    banc.ecrire_specs([decision("S-00000001", "rien ici", title="Tir autorisé sur shop.example.com")])
    assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN")


def test_refus_prod_decision_nom_generique(banc):
    url = "https://api.shop.example.com/"
    texte = "Tir de charge autorisé sur l'api de prod, sur front, en production, en staging et en pre-prod."
    banc.ecrire_specs([decision("S-00000001", texte)])
    # chaque bras est refusé par UN critère : longueur (api, front), forme sans `-_.`/chiffre
    # (production), lexique ET forme (staging), lexique SEUL (pre-prod : >= 6 et porte un `-`)
    for nom in ("api", "front", "production", "staging", "pre-prod"):
        assert loadtest.nomme(texte, nom), f"la décision ne nomme pas « {nom} » : ce bras ne peut pas rougir"
        cfg = banc.ecrire_config([cible_prod(nom=nom, url=url)])
        s = banc.lancer(banc.argv_run("--dry-run", target=nom, config=cfg))
        assert _rc_motif(s) == (2, "prod_decision_ne_nomme_pas_la_cible"), (nom, s)
        assert "témoin admis" in s.json["detail"], nom
    # contrôles : un nom spécifique (>= 6 caractères, hors lexique, porteur d'un `-`, `_`, `.`
    # ou d'un chiffre) cité vaut témoin
    for nom in ("boutique-front", "shop42"):
        banc.ecrire_specs([decision("S-00000001", f"Tir de charge autorisé sur {nom} en prod.")])
        cfg = banc.ecrire_config([cible_prod(nom=nom, url=url)])
        s = banc.lancer(banc.argv_run("--dry-run", target=nom, config=cfg))
        assert _rc_verdict(s) == (0, "DRY_RUN"), (nom, s)
        assert s.json["decision_pilote"]["temoin"] == "nom", nom


# --- seuils ---------------------------------------------------------------------------

def test_refus_seuils_libres(banc):
    base = banc.argv_run("--dry-run")
    for forme in (["--seuils", "p95<=1ms,err<=1%"], ["--seuils=p95<=1ms,err<=1%"], ["--seuils"]):
        s = banc.lancer([*base, *forme])
        assert _rc_motif(s) == (2, "seuils_libres"), (forme, s)
    # seul : le refus nomme seuils_libres, pas un argument manquant
    assert _rc_motif(banc.lancer(["run", "--seuils", "p95<=1ms,err<=1%"])) == (2, "seuils_libres")
    # une abréviation n'est jamais rabattue sur --seuils-de
    for abrege in ("--seuil", "--seuils-d"):
        argv = ["run", "--target", "demo-local", "--profil", "smoke", "--script", str(banc.script),
                abrege, str(banc.seuils), "--config", str(banc.config), "--dry-run"]
        assert _rc_motif(banc.lancer(argv)) == (2, "arguments"), abrege
    assert _rc_verdict(banc.lancer(base)) == (0, "DRY_RUN")


@posix_seul
def test_seuils_lus_du_fichier_et_sha_tracee(banc):
    s = banc.lancer(banc.argv_run(), K6_CLOUD_TOKEN="jeton-secret-du-banc",
                    FAKE_K6_P95="120", FAKE_K6_ERR="0.001", FAKE_K6_RPS="40")
    assert _rc_verdict(s) == (0, "GO"), s
    (t,) = banc.traces()
    assert t["seuils_fichier"]["sha256"] == hashlib.sha256(banc.seuils.read_bytes()).hexdigest()
    assert t["seuils_fichier"]["ligne"] == LIGNE_SEUILS
    assert t["seuils"] == {"p95_ms": 500.0, "err_ratio": 0.01, "rps_min": 10.0}
    assert t["mesures"] == {"p95_ms": 120.0, "err_ratio": 0.001, "rps": 40.0}
    assert t["volume"] == s.json["volume"] == {"http_reqs": 1, "vus_max": 1}
    assert t["script"]["sha256"] == hashlib.sha256(banc.script.read_bytes()).hexdigest()
    assert t["cible"] == {"nom": "demo-local", "env": "local", "hote": "127.0.0.1"}
    assert (t["rc_k6"], t["rc_sortie"], t["jeton_cloud_present"]) == (0, 0, True)
    brut = (banc.etat / "runs.jsonl").read_text(encoding="utf-8")
    assert "jeton-secret-du-banc" not in brut and "http://127.0.0.1:9" not in brut
    argv = json.loads(banc.argv_k6.read_text(encoding="utf-8"))
    assert argv[:3] == ["run", "-e", "TARGET_URL=http://127.0.0.1:9"]
    assert argv[-1] == str(banc.script.resolve()) and banc.script.read_text(encoding="utf-8") == SCENARIO
    assert argv[argv.index("--blacklist-ip") + 1] == loadtest.reseaux_hors_boucle()  # reçu par k6, avant le script
    # la sha suit le fichier : seuils recommités, trace nouvelle, empreinte nouvelle
    banc.committer("SEUILS.md", "SEUILS: p95<=400ms,err<=1%\n")
    assert _rc_verdict(banc.lancer(banc.argv_run())) == (0, "GO")
    t2 = banc.traces()[-1]
    assert t2["seuils_fichier"]["sha256"] == hashlib.sha256(banc.seuils.read_bytes()).hexdigest()
    assert t2["seuils_fichier"]["sha256"] != t["seuils_fichier"]["sha256"]
    assert t2["seuils"]["p95_ms"] == 400.0


def test_refus_seuils_fichier_non_suivi_ou_modifie(banc):
    nouveau = banc.depot / "NOUVEAU.md"
    nouveau.write_text("SEUILS: p95<=500ms,err<=1%\n", encoding="utf-8")
    argv_nouveau = banc.argv_run("--dry-run", seuils=nouveau)
    assert _rc_motif(banc.lancer(argv_nouveau)) == (2, "seuils_non_suivi")
    banc.git("add", "--", "NOUVEAU.md")  # indexé, jamais commité
    assert _rc_motif(banc.lancer(argv_nouveau)) == (2, "seuils_modifie")
    banc.seuils.write_text("SEUILS: p95<=9000ms,err<=50%\n", encoding="utf-8")
    assert _rc_motif(banc.lancer(banc.argv_run("--dry-run"))) == (2, "seuils_modifie")
    banc.git("checkout", "--", "SEUILS.md")
    assert _rc_verdict(banc.lancer(banc.argv_run("--dry-run"))) == (0, "DRY_RUN")


def _git_voit_propre(banc: Banc) -> bool:
    """`git diff HEAD --quiet` (l'ancienne garde) tient-il SEUILS.md pour propre ?"""
    p = subprocess.run(["git", "-C", str(banc.depot), "diff", "HEAD", "--quiet", "--", ":(literal)SEUILS.md"],
                       env=_env_git(), capture_output=True, timeout=60)
    return p.returncode == 0


def test_refus_seuils_skip_worktree_ou_assume_unchanged(banc):
    argv = banc.argv_run("--dry-run")
    for drapeau in ("skip-worktree", "assume-unchanged"):
        banc.git("update-index", f"--{drapeau}", "--", "SEUILS.md")
        banc.seuils.write_text("SEUILS: p95<=9000ms,err<=50%\n", encoding="utf-8")
        assert _git_voit_propre(banc), f"--{drapeau} ne masque plus la modification : ce bras ne peut pas rougir"
        s = banc.lancer(argv)
        assert _rc_motif(s) == (2, "seuils_modifie"), (drapeau, s)
        banc.git("update-index", f"--no-{drapeau}", "--", "SEUILS.md")
        banc.git("checkout", "--", "SEUILS.md")
        assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN"), drapeau
    if POSIX:  # un filtre clean qui rend le blob de HEAD : `git diff` le croit, le runner non
        origine = banc.tmp / "SEUILS.origine"
        origine.write_bytes(banc.seuils.read_bytes())
        (banc.depot / ".git" / "info").mkdir(exist_ok=True)
        (banc.depot / ".git" / "info" / "attributes").write_text("SEUILS.md filter=masque\n", encoding="utf-8")
        cat = shutil.which("cat", path=banc.path_origine)  # le PATH du banc ne porte que k6 et git
        assert cat, "cat absent du PATH d'origine : le filtre clean ne peut pas être posé"
        banc.git("config", "filter.masque.clean", f"{shlex.quote(cat)} {shlex.quote(str(origine))}")
        banc.seuils.write_text("SEUILS: p95<=9000ms,err<=50%\n", encoding="utf-8")
        assert _git_voit_propre(banc), "le filtre clean ne masque plus la modification : ce bras ne peut pas rougir"
        assert _rc_motif(banc.lancer(argv)) == (2, "seuils_modifie")
        banc.seuils.write_bytes(origine.read_bytes())
        assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN")


def test_refus_seuils_hors_depot(banc):
    hors = banc.tmp / "hors"
    hors.mkdir()
    sonde = subprocess.run(["git", "-C", str(hors), "rev-parse", "--is-inside-work-tree"],
                           env=_env_git(), capture_output=True, text=True, timeout=60)
    if sonde.returncode == 0:
        pytest.skip(f"tmp_path est dans un dépôt git ({hors}) : aucun « hors dépôt » constructible ici")
    fichier = hors / "SEUILS.md"
    fichier.write_text("SEUILS: p95<=500ms,err<=1%\n", encoding="utf-8")
    assert _rc_motif(banc.lancer(banc.argv_run("--dry-run", seuils=fichier))) == (2, "seuils_hors_depot")
    absent = banc.argv_run("--dry-run", seuils=banc.depot / "ABSENT.md")
    assert _rc_motif(banc.lancer(absent)) == (2, "seuils_fichier")


def test_refus_seuils_zero_ou_deux_lignes(banc):
    cas = {
        "ZERO.md": "# Pas de seuils\n\nLes SEUILS: en milieu de ligne ne comptent pas.\n",
        "DEUX.md": "SEUILS: p95<=500ms,err<=1%\nSEUILS: p95<=900ms,err<=5%\n",
        "BLOC.md": "```text\nSEUILS: p95<=500ms,err<=1%\n```\n~~~\nSEUILS: p95<=1ms,err<=1%\n~~~\n",
        "INDENTE.md": "  SEUILS: p95<=500ms,err<=1%\n",
    }
    for nom, contenu in cas.items():
        fichier = banc.committer(nom, contenu)
        s = banc.lancer(banc.argv_run("--dry-run", seuils=fichier))
        assert _rc_motif(s) == (2, "seuils_lignes"), (nom, s)
    # SEUILS: dans un bloc de code est ignoré : seule la ligne hors bloc compte
    fichier = banc.committer("BLOC_ET_LIGNE.md",
                             "```\nSEUILS: p95<=1ms,err<=0%\n```\n\nSEUILS: p95<=700ms,err<=2%\n")
    s = banc.lancer(banc.argv_run("--dry-run", seuils=fichier))
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert s.json["seuils"] == {"p95_ms": 700.0, "err_ratio": 0.02, "rps_min": None}


def test_refus_seuils_sans_p95_ou_err(banc):
    for nom, ligne in {"SANS_P95.md": "SEUILS: err<=1%,rps>=10", "SANS_ERR.md": "SEUILS: p95<=500ms",
                       "RPS_SEUL.md": "SEUILS: rps>=10"}.items():
        fichier = banc.committer(nom, ligne + "\n")
        assert _rc_motif(banc.lancer(banc.argv_run("--dry-run", seuils=fichier))) == (2, "seuils_incomplets"), nom
    for nom, ligne in {"SANS_UNITE.md": "SEUILS: p95<=500,err<=1%",
                       "INCONNU.md": "SEUILS: p95<=500ms,err<=1%,p99<=900ms",
                       "DOUBLE.md": "SEUILS: p95<=500ms,p95<=600ms,err<=1%"}.items():
        fichier = banc.committer(nom, ligne + "\n")
        assert _rc_motif(banc.lancer(banc.argv_run("--dry-run", seuils=fichier))) == (2, "seuils_syntaxe"), nom
    fichier = banc.committer("SECONDES.md", "SEUILS: p95 <= 0.5s, err <= 1%\n")
    s = banc.lancer(banc.argv_run("--dry-run", seuils=fichier))
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert s.json["seuils"]["p95_ms"] == 500.0


@pytest.mark.skipif(not POSIX, reason="hooksPath=/dev/null, non mesuré sous Windows")
def test_git_du_runner_ignore_fsmonitor_du_depot(banc):
    marque = banc.tmp / "fsmonitor.appels"
    hook = banc.tmp / "fsmonitor.sh"
    hook.write_text(f'#!/bin/sh\necho "$@" >> {shlex.quote(str(marque))}\nexit 1\n', encoding="utf-8")
    hook.chmod(0o755)
    banc.git("config", "core.fsmonitor", str(hook))
    # contrôle : sans neutralisation, la MÊME commande que le runner (`ls-files` ; ni
    # rev-parse ni hash-object n'appellent le hook, mesuré git 2.53 macOS) appelle le hook
    subprocess.run(["git", "-C", str(banc.depot), "ls-files", "--", ":(literal)SEUILS.md"],
                   env=_env_git(), capture_output=True, timeout=60)
    assert marque.exists(), "le hook fsmonitor n'est pas appelé : ce témoin ne peut plus rougir"
    marque.unlink()
    assert _rc_verdict(banc.lancer(banc.argv_run("--dry-run"))) == (0, "DRY_RUN")
    assert not marque.exists(), "le git du runner a déclenché le fsmonitor du dépôt des seuils"


# --- exécuteur et gardes locales ---------------------------------------------------------

def test_refus_stress_en_local(banc):
    cas = [("stress", ["--executor", "local"]), ("endurance", ["--executor", "local"]),
           ("stress", ["--force-local", "poste perso"]), ("charge", ["--executor", "local"])]
    for profil, extra in cas:
        s = banc.lancer(banc.argv_run("--dry-run", *extra, profil=profil))
        assert _rc_motif(s) == (2, "fidelite_de_charge"), (profil, extra, s)
        assert "fidélité" in s.json["detail"] and "coût" not in s.json["detail"].casefold()
    # contrôle : charge en local sous --force-local, marquée non représentative
    s = banc.lancer(banc.argv_run("--dry-run", "--force-local", "fumée sur le poste", profil="charge"))
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert (s.json["executeur"], s.json["fidelite"]) == ("local", "non representative")


@posix_seul
def test_force_local_charge_trace_fidelite_non_representative(banc):
    s = banc.lancer(banc.argv_run("--force-local", "fumée sur le poste", profil="charge"))
    assert _rc_verdict(s) == (0, "GO"), s
    t = banc.traces()[-1]
    assert (t["executeur"], t["fidelite"], t["force_local_motif"]) == ("local", "non representative",
                                                                       "fumée sur le poste")


def test_refus_local_machine_chargee(banc, capsys, monkeypatch):
    cfg = banc.ecrire_config([CIBLE_LOCALE], max_load1=4)
    argv = banc.argv_run("--dry-run", config=cfg)
    monkeypatch.setattr(loadtest.os, "getloadavg", lambda: (50.0, 1.0, 1.0))
    assert _rc_motif(banc.main(capsys, argv)) == (2, "machine_chargee")
    monkeypatch.setattr(loadtest.os, "getloadavg", lambda: (3.9, 1.0, 1.0))
    s = banc.main(capsys, argv)
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert s.json["machine"] == {"load1": 3.9, "max_load1": 4}
    # sans getloadavg (Windows) : refus, sauf --force-local
    monkeypatch.delattr(loadtest.os, "getloadavg")
    assert _rc_motif(banc.main(capsys, argv)) == (2, "charge_non_mesurable")
    s = banc.main(capsys, banc.argv_run("--dry-run", "--force-local", "poste sans getloadavg", config=cfg))
    assert _rc_verdict(s) == (0, "DRY_RUN"), s


def test_max_load1_derive_des_coeurs_et_config_prioritaire(banc, capsys, monkeypatch):
    monkeypatch.setattr(loadtest.os, "cpu_count", lambda: 8)
    sans = banc.ecrire_config([CIBLE_LOCALE], max_load1=None, nom="sans.json")
    avec = banc.ecrire_config([CIBLE_LOCALE], max_load1=3, nom="avec.json")
    s = banc.main(capsys, ["probe", "--config", str(sans)])
    assert (s.json["cpu_count"], s.json["max_load1"]) == (8, 6), s
    assert banc.main(capsys, ["probe", "--config", str(avec)]).json["max_load1"] == 3
    # le plafond MORD : égalité admise, au-delà refusé ; la config l'emporte sur les cœurs
    for cfg, charge, rc in ((sans, 6.0, 0), (sans, 6.01, 2), (avec, 3.5, 2), (avec, 2.9, 0)):
        monkeypatch.setattr(loadtest.os, "getloadavg", lambda c=charge: (c, 0.0, 0.0))
        s = banc.main(capsys, banc.argv_run("--dry-run", config=cfg))
        assert s.rc == rc, (cfg.name, charge, s)
    # cœurs inconnus et aucune valeur explicite : local refusé
    monkeypatch.setattr(loadtest.os, "cpu_count", lambda: None)
    monkeypatch.setattr(loadtest.os, "getloadavg", lambda: (0.1, 0.0, 0.0))
    assert _rc_motif(banc.main(capsys, banc.argv_run("--dry-run", config=sans))) == (2, "charge_non_mesurable")


@posix_seul
def test_refus_sous_verrou_de_porte_pid_vivant(banc):
    owner = Path(str(banc.verify) + ".lock") / "owner"
    owner.parent.mkdir()
    argv = banc.argv_run("--dry-run")
    owner.write_text(f"pid={os.getpid()}\nstarted=0\nhost=banc\n", encoding="utf-8")
    s = banc.lancer(argv)
    assert _rc_motif(s) == (2, "verrou_de_porte"), s
    assert str(os.getpid()) in s.json["detail"]
    mort = subprocess.Popen([sys.executable, "-c", "pass"])
    mort.wait(timeout=60)
    owner.write_text(f"pid={mort.pid}\nstarted=0\n", encoding="utf-8")
    assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN")
    owner.write_text("started=0\n", encoding="utf-8")  # aucun pid : vivant ou mort indécidable
    assert _rc_motif(banc.lancer(argv)) == (2, "verrou_de_porte")


def test_refus_verrou_de_porte_sans_owner(banc):
    verrou = Path(str(banc.verify) + ".lock")
    argv = banc.argv_run("--dry-run")
    assert _rc_verdict(banc.lancer(argv)) == (0, "DRY_RUN")  # contrôle : aucun verrou, local admis
    verrou.mkdir()  # verify.sh : `mkdir` pris, `owner` pas encore écrit (ou abandonné) = tenu
    s = banc.lancer(argv)
    assert _rc_motif(s) == (2, "verrou_de_porte"), s
    assert "sans `owner`" in s.json["detail"]


@posix_seul
def test_refus_verrou_du_depot_principal_depuis_worktree_lie(banc, capsys, monkeypatch):
    lie = banc.tmp / "lie"
    banc.git("worktree", "add", "-q", "--detach", str(lie))
    monkeypatch.setattr(loadtest, "ROOT", lie.resolve())  # le runner vit dans le worktree lié
    monkeypatch.delenv("VERIFY_WORKTREE_DIR")
    argv = banc.argv_run("--dry-run")
    assert _rc_verdict(banc.main(capsys, argv)) == (0, "DRY_RUN")  # contrôle : aucun verrou, local admis
    principal = banc.depot.resolve()
    owner = Path(str(principal.parent / f"{principal.name}-verify") + ".lock") / "owner"
    owner.parent.mkdir()
    owner.write_text(f"pid={os.getpid()}\nstarted=0\n", encoding="utf-8")  # une porte lancée du principal
    s = banc.main(capsys, argv)
    assert _rc_motif(s) == (2, "verrou_de_porte"), s
    assert f"{principal.name}-verify.lock" in s.json["detail"], s


@posix_seul
def test_refus_verrou_d_un_autre_worktree_lie(banc, capsys, monkeypatch):
    premier, second = banc.tmp / "lie1", banc.tmp / "lie2"
    for lie in (premier, second):
        banc.git("worktree", "add", "-q", "--detach", str(lie))
    monkeypatch.setattr(loadtest, "ROOT", premier.resolve())  # le runner vit dans le PREMIER worktree lié
    monkeypatch.delenv("VERIFY_WORKTREE_DIR")
    argv = banc.argv_run("--dry-run")
    assert _rc_verdict(banc.main(capsys, argv)) == (0, "DRY_RUN")  # contrôle : aucun verrou, local admis
    owner = Path(str(second.parent / f"{second.name}-verify") + ".lock") / "owner"
    owner.parent.mkdir()
    owner.write_text(f"pid={os.getpid()}\nstarted=0\n", encoding="utf-8")  # une porte lancée du SECOND
    s = banc.main(capsys, argv)
    assert _rc_motif(s) == (2, "verrou_de_porte"), s
    assert f"{second.name}-verify.lock" in s.json["detail"], s
    # repli (liste en échec, git < 2.36) : le second n'est plus vu, le principal l'est encore
    monkeypatch.setattr(loadtest, "worktrees_du_depot", lambda: None)
    assert _rc_verdict(banc.main(capsys, argv)) == (0, "DRY_RUN")
    principal = banc.depot.resolve()
    owner = Path(str(principal.parent / f"{principal.name}-verify") + ".lock") / "owner"
    owner.parent.mkdir()
    owner.write_text(f"pid={os.getpid()}\nstarted=0\n", encoding="utf-8")
    assert _rc_motif(banc.main(capsys, argv)) == (2, "verrou_de_porte")


# --- verdicts DEGRADED ----------------------------------------------------------------------

@posix_seul
def test_degraded_k6_absent_exit_3(banc):
    seul_git = banc.tmp / "seul_git"
    seul_git.mkdir()
    (seul_git / "git").symlink_to(banc.git_reel)
    s = banc.lancer(banc.argv_run(), PATH=str(seul_git))
    assert _rc_verdict(s) == (3, "DEGRADED"), s
    assert "COVERAGE DEGRADED — k6 absent, verdict absent" in s.err.splitlines()
    assert banc.traces()[-1]["verdict"] == "DEGRADED"
    p = banc.lancer(["probe", "--config", str(banc.config)], PATH=str(seul_git))
    assert (p.rc, p.json["k6"]) == (3, None), p


@posix_seul
def test_degraded_k6_rc_97_sans_synthese_exit_3(banc):
    for rc_k6, synthese in (("97", "absente"), ("97", "valide"), ("107", "valide"), ("105", "absente"),
                            ("signal", "valide")):
        s = banc.lancer(banc.argv_run(), FAKE_K6_RC=rc_k6, FAKE_K6_SYNTHESE=synthese)
        assert _rc_verdict(s) == (3, "DEGRADED"), (rc_k6, synthese, s)
        assert s.json["rc_k6"] not in (0, 99)
        assert any(ligne.startswith("COVERAGE DEGRADED — ") and ligne.endswith(" absent, verdict absent")
                   for ligne in s.err.splitlines()), s.err


@posix_seul
def test_degraded_rc_0_sans_synthese_ou_illisible(banc):
    for reglage in ({"FAKE_K6_SYNTHESE": "absente"}, {"FAKE_K6_SYNTHESE": "tronquee"},
                    {"FAKE_K6_SYNTHESE": "incomplete"}, {"FAKE_K6_P95": "nan"}):
        s = banc.lancer(banc.argv_run(), **reglage)
        assert _rc_verdict(s) == (3, "DEGRADED"), (reglage, s)
        assert s.json["rc_k6"] == 0
        if reglage.get("FAKE_K6_SYNTHESE") in ("absente", "tronquee"):
            # synthèse ABSENTE ou illisible : `volume` vaut null, jamais un dict de clés nulles
            assert "volume" in banc.traces()[-1] and s.json["volume"] is banc.traces()[-1]["volume"] is None, s
        elif reglage == {"FAKE_K6_SYNTHESE": "incomplete"}:
            # synthèse PRÉSENTE, clé manquante : le dict, la clé absente à null
            assert s.json["volume"] == banc.traces()[-1]["volume"] == {"http_reqs": None, "vus_max": 1}, s
    assert _rc_verdict(banc.lancer(banc.argv_run())) == (0, "GO")
    # vus_max absente : information manquante, jamais un verdict — le GO reste 0, volume.vus_max null
    s = banc.lancer(banc.argv_run(), FAKE_K6_SANS_VUS="1")
    assert _rc_verdict(s) == (0, "GO"), s
    assert s.json["volume"] == banc.traces()[-1]["volume"] == {"http_reqs": 1, "vus_max": None}, s


@posix_seul
def test_degraded_delai_depasse_k6_tue_exit_3(banc, capsys, monkeypatch):
    pid_k6, pid_enfant = banc.tmp / "k6.pid", banc.tmp / "enfant.pid"
    monkeypatch.setitem(loadtest.DELAI_PAR_PROFIL, "smoke", 5)
    monkeypatch.setenv("FAKE_K6_DORT", "120")
    monkeypatch.setenv("FAKE_K6_PID", str(pid_k6))
    monkeypatch.setenv("FAKE_K6_PETIT_ENFANT", str(pid_enfant))
    debut = time.monotonic()
    s = banc.main(capsys, banc.argv_run())
    assert _rc_verdict(s) == (3, "DEGRADED"), s
    assert time.monotonic() - debut < 60
    assert "délai dur" in s.json["motif"]
    # aucune synthèse lue : `volume` présent et null, la forme de la trace reste stable
    assert "volume" in banc.traces()[-1] and banc.traces()[-1]["volume"] is None, banc.traces()[-1]
    for fichier in (pid_k6, pid_enfant):
        assert fichier.exists(), f"{fichier.name} absent : le faux k6 n'a pas démarré avant le délai"
        pid = int(fichier.read_text(encoding="utf-8"))
        assert _mort_sous(pid, 10), f"{fichier.name} : pid {pid} survit au délai dur"


@posix_seul
def test_sigterm_tue_k6_et_trace_degraded(banc):
    pid_k6 = banc.tmp / "k6.pid"
    env = {**os.environ, "FAKE_K6_DORT": "120", "FAKE_K6_PID": str(pid_k6)}
    # SIGKILL d'abord, en CONTRÔLE : non rattrapable, il laisse k6 vivant — le témoin VOIT un survivant
    for sig in (signal.SIGKILL, signal.SIGTERM, signal.SIGHUP):
        pid_k6.unlink(missing_ok=True)
        p = subprocess.Popen([sys.executable, str(SCRIPT), *banc.argv_run()], env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8")
        pid = None
        try:
            pid = _attendre_pid(pid_k6, 60)
            assert pid is not None, f"{sig.name} : le faux k6 n'a pas démarré"
            p.send_signal(sig)
            out, _err = p.communicate(timeout=60)
            if sig == signal.SIGKILL:
                assert p.returncode == -signal.SIGKILL, p.returncode
                assert not _mort_sous(pid, 2), "contrôle : k6 meurt avec le runner tué par SIGKILL, ce témoin ne prouve rien"
                continue
            assert p.returncode == 3, (sig.name, p.returncode, out)
            assert _mort_sous(pid, 10), f"{sig.name} : k6 (pid {pid}) survit à l'interruption du runner"
            assert _json(out)["motif"] == f"interrompu: {sig.name}", out
            t = banc.traces()[-1]
            assert (t["verdict"], t["motif"], t["rc_sortie"]) == ("DEGRADED", f"interrompu: {sig.name}", 3), t
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=30)
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


@posix_seul
@pytest.mark.parametrize("premier,second", [(p, s) for p in ("SIGTERM", "SIGINT") for s in ("SIGTERM", "SIGINT")])
def test_second_sigterm_pendant_la_trace_ne_la_perd_pas(banc, premier, second):
    pid_k6, marqueur = banc.tmp / "k6.pid", banc.tmp / "trace.en_cours"
    env = {**os.environ, "FAKE_K6_DORT": "120", "FAKE_K6_PID": str(pid_k6)}
    p = subprocess.Popen([sys.executable, "-c", TRACE_LENTE, str(SCRIPT), str(marqueur), *banc.argv_run()],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    pid = None
    try:
        pid = _attendre_pid(pid_k6, 60)
        assert pid is not None, "le faux k6 n'a pas démarré"
        p.send_signal(getattr(signal, premier))
        fin = time.monotonic() + 30
        while not marqueur.exists() and time.monotonic() < fin and p.poll() is None:
            time.sleep(0.02)
        assert marqueur.exists(), "l'écriture de la trace n'a pas commencé : ce témoin ne peut pas rougir"
        p.send_signal(getattr(signal, second))  # second signal PENDANT l'écriture de la trace
        out, _err = p.communicate(timeout=60)
        assert p.returncode == 3, (p.returncode, out)
        traces = banc.traces()  # chaque ligne passe json.loads : une ligne tronquée lève
        assert len(traces) == 1, f"trace perdue par le second {second} : {traces} ; stdout {out!r}"
        t = traces[0]
        assert (t["verdict"], t["motif"], t["rc_sortie"], t["volume"]) == ("DEGRADED", f"interrompu: {premier}", 3, None), t
        assert _mort_sous(pid, 10), f"{premier} : k6 (pid {pid}) survit à l'interruption"
        # second signal PENDANT l'écriture : stdout garde le PREMIER (un second plus tôt le remplace, borne dite au docstring)
        assert _json(out)["motif"] == f"interrompu: {premier}", out
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=30)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def _leve(fabrique):
    def coupe(*_a, **_k):
        raise fabrique()
    return coupe


def _sentinelle(*_a):
    pass


def test_interruption_rend_3_et_trace(banc, capsys, monkeypatch):
    # une sentinelle posée ICI : le témoin ne dépend plus de ce qu'un test précédent a laissé
    avant = {n: signal.signal(getattr(signal, n), _sentinelle) for n in ("SIGINT", "SIGTERM", "SIGHUP")
             if hasattr(signal, n)}
    try:
        cas = ((KeyboardInterrupt, "SIGINT"), (lambda: loadtest.Interrompu("SIGTERM"), "SIGTERM"))
        for fabrique, nom in cas:
            monkeypatch.setattr(loadtest, "executer_local", _leve(fabrique))
            s = banc.main(capsys, banc.argv_run())
            assert _rc_motif(s) == (3, f"interrompu: {nom}"), s
            assert banc.traces()[-1]["motif"] == f"interrompu: {nom}"
        # hors `run`, la garde de tête : 3, jamais le 1 d'un Python non capturé
        for fabrique, nom in cas:
            monkeypatch.setattr(loadtest, "charger_config", _leve(fabrique))
            s = banc.main(capsys, ["check-config", "--config", str(banc.config)])
            assert _rc_motif(s) == (3, f"interrompu: {nom}"), s
        # `main` appelé en processus rend les gestionnaires qu'il a remplacés (SIG_IGN de la trace compris)
        assert {n: signal.getsignal(getattr(signal, n)) for n in avant} == {n: _sentinelle for n in avant}
    finally:
        for n, gestionnaire in avant.items():
            signal.signal(getattr(signal, n), gestionnaire if gestionnaire is not None else signal.SIG_DFL)


@posix_seul
def test_k6_local_sans_jeton_cloud_et_journal_redige(banc):
    # K6_CLOUD_STACK_ID court : une variable de jeton NOMMÉE est rédigée quelle que soit sa longueur
    jetons = {"K6_CLOUD_TOKEN": "faux-jeton-du-banc", "K6_CLOUD_STACK_ID": "pile7",
              "AZURE_CLIENT_SECRET": "faux-secret-azure-du-banc"}
    # options K6_* : k6 les ferait primer sur le script (K6_NO_THRESHOLDS change un rc 99 en 0)
    options = {"K6_VUS": "1", "K6_NO_THRESHOLDS": "true", "k6_out": "json=/dev/null"}
    # AZURE_* de moins de 8 caractères : pas un secret plausible, jamais rédigé
    courtes = {"AZURE_CORE_ONLY_SHOW_ERRORS": "1", "AZURE_CORE_OUTPUT": "json"}
    # proxy en boucle locale : --blacklist-ip ne jugerait que son IP (mesuré v2.3.0) — retiré en local
    proxys = {"HTTP_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9"}
    env_k6 = banc.tmp / "env_k6.json"
    # le faux k6 écrit sur son journal ce qu'un script imprudent y mettrait
    echo = "marqueur-visible " + " ".join(f"{k}={v}" for k, v in jetons.items()) + " status 401 json"
    s = banc.lancer(banc.argv_run(), **jetons, **options, **courtes, **proxys, FAKE_K6_ENV=str(env_k6),
                    FAKE_K6_ECHO=echo, FAKE_K6_CANARI="present", FAKE_K6_RC="97")
    assert _rc_verdict(s) == (3, "DEGRADED"), s
    noms = set(json.loads(env_k6.read_text(encoding="utf-8")))
    assert "FAKE_K6_CANARI" in noms, "l'environnement du runner n'atteint plus k6 : ce témoin ne peut pas rougir"
    assert not noms & set(jetons), f"variables de jeton héritées par k6 local : {sorted(noms & set(jetons))}"
    assert not noms & set(options), f"options K6_* héritées par k6 local : {sorted(noms & set(options))}"
    assert not noms & set(proxys), f"variables de proxy héritées par k6 en env local : {sorted(noms & set(proxys))}"
    # hors local (staging, sans blacklist), le proxy de l'appelant est conservé
    cfg = banc.ecrire_config([{**CIBLE_LOCALE, "name": "demo-staging", "env": "staging",
                               "url": "http://10.0.0.5:8080/"}], nom="staging.json")
    banc.lancer(banc.argv_run(target="demo-staging", config=cfg), **proxys, FAKE_K6_ENV=str(env_k6))
    assert set(proxys) <= set(json.loads(env_k6.read_text(encoding="utf-8"))), "proxy retiré hors env local"
    logs = s.json["logs_fin"]
    assert "marqueur-visible" in logs, "logs_fin ne porte pas le journal k6 : ce témoin ne peut pas rougir"
    assert "status 401 json" in logs, f"une valeur AZURE_* courte a mangé le journal : {logs}"
    assert logs.count("[REDACTED]") == len(jetons), logs
    for valeur in jetons.values():
        assert valeur not in json.dumps(s.json), valeur
    assert "logs_fin" not in banc.traces()[-1]


@posix_seul
def test_degraded_si_trace_inecrivable(banc):
    fichier = banc.tmp / "etat_est_un_fichier"
    fichier.write_text("", encoding="utf-8")
    s = banc.lancer(banc.argv_run(), AGENTS_LOADTEST_STATE=str(fichier))
    assert _rc_verdict(s) == (3, "DEGRADED"), s  # un GO sans trace n'est pas auditable
    assert s.json["rc_k6"] == 0 and s.json["trace"].startswith("non écrite"), s
    assert "COVERAGE DEGRADED — trace loadtest absent, verdict absent" in s.err.splitlines()
    s = banc.lancer(banc.argv_run(), AGENTS_LOADTEST_STATE=str(fichier), FAKE_K6_RC="99", FAKE_K6_P95="900")
    assert _rc_verdict(s) == (1, "NO_GO"), s  # un NO_GO reste un NO_GO
    assert s.json["trace"].startswith("non écrite"), s
    # contrôle : répertoire d'état ordinaire, le même GO est un GO tracé
    assert _rc_verdict(banc.lancer(banc.argv_run())) == (0, "GO")
    assert banc.traces()[-1]["verdict"] == "GO"


def test_degraded_sur_exception_interne_exit_3(banc, capsys, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(loadtest, "charger_config", boom)
    s = banc.main(capsys, ["check-config", "--config", str(banc.config)])
    assert (s.rc, s.json) == (3, {"verdict": "DEGRADED", "motif": "erreur interne: RuntimeError"}), s
    assert "COVERAGE DEGRADED — " in s.err
    argv = ["check-config", "--config", str(banc.config)]
    garde = subprocess.run([sys.executable, "-c", PANNE, str(SCRIPT), "main", *argv],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert garde.returncode == 3, garde
    assert _json(garde.stdout)["motif"] == "erreur interne: KeyError"
    nue = subprocess.run([sys.executable, "-c", PANNE, str(SCRIPT), "_principal", *argv],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert nue.returncode == 1, "sans la garde de tête, la panne doit rendre 1 : sinon ce témoin ne prouve rien"


def test_cloud_adaptateur_absent_ou_hors_protocole(banc, capsys, monkeypatch):
    argv = banc.argv_run(profil="stress")
    monkeypatch.setitem(sys.modules, "loadtest_cloud", None)
    s = banc.main(capsys, argv)
    assert _rc_verdict(s) == (3, "DEGRADED"), s
    assert "adaptateur cloud absent" in s.json["motif"]
    assert "COVERAGE DEGRADED — adaptateur cloud loadtest_cloud absent, verdict absent" in s.err
    faux = ModuleType("loadtest_cloud")
    faux.argv_dry_run = lambda ctx: ["faux-cloud", "run", ctx.profil]
    faux.run = lambda ctx: {"rc": 0, "summary": {"metrics": {"http_req_duration": {"p(95)": 80},
                                                             "http_req_failed": {"value": 0},
                                                             "http_reqs": {"rate": 30}}}, "logs": ""}
    faux.temoin_fin = lambda ctx: True
    monkeypatch.setitem(sys.modules, "loadtest_cloud", faux)
    s = banc.main(capsys, argv)
    assert _rc_verdict(s) == (0, "GO"), s
    assert s.json["executeur"] == "cloud"
    s = banc.main(capsys, banc.argv_run("--dry-run", profil="stress"))
    assert (s.rc, s.json.get("argv")) == (0, ["faux-cloud", "run", "stress"]), s
    faux.temoin_fin = lambda ctx: False
    assert _rc_verdict(banc.main(capsys, argv)) == (3, "DEGRADED")
    faux.temoin_fin = lambda ctx: True
    faux.run = lambda ctx: {"rc": "0", "summary": None}
    assert _rc_verdict(banc.main(capsys, argv)) == (3, "DEGRADED")


# --- verdicts NO_GO -------------------------------------------------------------------------

@posix_seul
def test_no_go_sur_rc_99(banc):
    s = banc.lancer(banc.argv_run(), FAKE_K6_RC="99", FAKE_K6_P95="900")
    assert _rc_verdict(s) == (1, "NO_GO"), s
    assert (s.json["rc_k6"], s.json["desaccord"], s.json["depassements"]) == (99, None, ["p95 900 ms > 500 ms"])
    # rc 99 sans synthèse : un échec constaté par k6, jamais un GO
    s = banc.lancer(banc.argv_run(), FAKE_K6_RC="99", FAKE_K6_SYNTHESE="absente")
    assert _rc_verdict(s) == (1, "NO_GO"), s
    assert "impossible" in s.json["recalcul"]
    assert banc.traces()[-1]["verdict"] == "NO_GO"


@posix_seul
def test_no_go_sur_divergence_nommee(banc):
    cas = [({"FAKE_K6_P95": "900"}, "k6 rc 0", "p95 900 ms > 500 ms"),
           ({"FAKE_K6_ERR": "0.05"}, "k6 rc 0", "err 5 % > 1 %"),
           ({"FAKE_K6_RPS": "2"}, "k6 rc 0", "rps 2 < 10"),
           ({"FAKE_K6_RC": "99"}, "k6 rc 99", "dans les seuils du fichier")]
    for reglage, tete, fragment in cas:
        s = banc.lancer(banc.argv_run(), **reglage)
        assert _rc_verdict(s) == (1, "NO_GO"), (reglage, s)
        assert s.json["desaccord"].startswith(tete) and fragment in s.json["desaccord"], (reglage, s.json)


# --- configuration, fenêtre, plan -------------------------------------------------------------

def test_refus_url_userinfo_query_ou_schema(banc):
    for url in ("http://u:p@127.0.0.1:9/", "http://127.0.0.1:9/?jeton=x", "http://127.0.0.1:9/#a",
                "ftp://127.0.0.1/", "http:///chemin", "http://127.0.0.1:99999/",
                "http://[::1/", "http://[zz]/"):  # IPv6 mal formée : urlsplit lève ValueError
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "url": url}])
        s = banc.lancer(["check-config", "--config", str(cfg)])
        assert _rc_motif(s) == (2, "url_invalide"), (url, s)
    s = banc.lancer(["check-config", "--config", str(EXEMPLE)])
    assert _rc_verdict(s) == (0, "OK"), s
    assert {c["env"] for c in s.json["cibles"]} == {"local"}


def test_refus_env_local_hors_loopback(banc):
    hors = ("http://169.254.169.254/", "http://10.0.0.5:8080/", "http://intranet.example/",
            "http://127.1/", "http://2130706433/", "http://[::ffff:127.0.0.1]/", "http://localhost./")
    boucle = ("http://127.0.0.1:9", "http://127.255.0.1/", "http://localhost:8080/", "http://LOCALHOST/",
              "http://[::1]:8080/")
    for url in hors:
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "url": url}])
        s = banc.lancer(["check-config", "--config", str(cfg)])
        assert _rc_motif(s) == (2, "url_invalide"), (url, s)
        assert "loopback" in s.json["detail"], url
        # contrôle : la MÊME adresse sous un autre env n'est pas filtrée par l'adresse
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "url": url, "env": "staging"}])
        assert _rc_verdict(banc.lancer(["check-config", "--config", str(cfg)])) == (0, "OK"), url
    for url in boucle:
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "url": url}])
        assert _rc_verdict(banc.lancer(["check-config", "--config", str(cfg)])) == (0, "OK"), url


def test_refus_hors_fenetre_et_fuseau_indisponible(banc, capsys, monkeypatch):
    bureau = {**CIBLE_LOCALE, "name": "bureau", "fenetre": {"debut": "09:00", "fin": "18:00", "tz": "Europe/Paris"}}
    nuit = {**CIBLE_LOCALE, "name": "nuit", "fenetre": {"debut": "22:00", "fin": "06:00", "tz": "Europe/Paris"}}
    cfg = banc.ecrire_config([bureau, nuit])
    cas = [("bureau", 8, 59, "hors_fenetre"), ("bureau", 9, 0, None), ("bureau", 17, 59, None),
           ("bureau", 18, 0, "hors_fenetre"), ("nuit", 23, 0, None), ("nuit", 5, 59, None),
           ("nuit", 12, 0, "hors_fenetre")]
    for cible, h, m, motif in cas:
        monkeypatch.setattr(loadtest, "horloge", lambda fuseau, h=h, m=m: datetime(2026, 10, 8, h, m, tzinfo=fuseau))
        s = banc.main(capsys, banc.argv_run("--dry-run", target=cible, config=cfg))
        attendu = (2, motif) if motif else (0, None)
        assert (s.rc, s.json.get("motif")) == attendu, (cible, h, m, s)
    inconnu = banc.ecrire_config([{**CIBLE_LOCALE, "fenetre": {**FENETRE_JOUR, "tz": "Nulle/Part"}}], nom="tz.json")
    assert _rc_motif(banc.main(capsys, ["check-config", "--config", str(inconnu)])) == (2, "fuseau_indisponible")


def test_refus_cible_profil_arguments_ou_script(banc):
    assert _rc_motif(banc.lancer(banc.argv_run("--dry-run", target="fantome"))) == (2, "cible_inconnue")
    cfg = banc.ecrire_config([{**CIBLE_LOCALE, "allowed_profiles": ["smoke"]}], nom="smoke.json")
    assert _rc_motif(banc.lancer(banc.argv_run("--dry-run", profil="charge", config=cfg))) == (2, "profil_non_admis")
    s = banc.lancer(["run", "--target", "demo-local", "--dry-run", "--config", str(cfg)])
    assert _rc_motif(s) == (2, "arguments") and "--profil" in s.json["detail"], s
    en_dur = banc.tmp / "en_dur.js"
    en_dur.write_text("import http from 'k6/http';\nexport default function () { http.get('http://127.0.0.1:9'); }\n",
                      encoding="utf-8")
    argv = banc.argv_run("--dry-run")
    argv[argv.index("--script") + 1] = str(en_dur)
    assert _rc_motif(banc.lancer(argv)) == (2, "script")


def test_dry_run_ne_lance_rien_ni_ne_trace(banc):
    s = banc.lancer(banc.argv_run("--dry-run"))
    assert _rc_verdict(s) == (0, "DRY_RUN"), s
    assert s.json["argv"][1:4] == ["run", "-e", "TARGET_URL=http://127.0.0.1:9"]
    assert not banc.argv_k6.exists(), "--dry-run a lancé k6"
    assert banc.traces() == [], "--dry-run a écrit une trace"


def test_blacklist_ip_en_local_seulement(banc):
    argv = banc.lancer(banc.argv_run("--dry-run")).json["argv"]
    assert "--blacklist-ip" in argv and argv.index("--blacklist-ip") < len(argv) - 2, argv
    reseaux = [ipaddress.ip_network(r) for r in argv[argv.index("--blacklist-ip") + 1].split(",")]
    v4 = [n for n in reseaux if n.version == 4]
    v6 = [n for n in reseaux if n.version == 6]
    for couvert in ("10.0.0.0/8", "0.0.0.0/32", "169.254.169.254/32", "128.0.0.0/1"):
        assert any(ipaddress.ip_network(couvert).subnet_of(n) for n in v4), couvert
    assert not any(n.overlaps(ipaddress.ip_network("127.0.0.0/8")) for n in v4), "la boucle locale est blacklistée"
    assert any(ipaddress.ip_address("fe80::1") in n for n in v6) and any(ipaddress.ip_address("::ffff:a00:1") in n for n in v6)
    assert not any(ipaddress.ip_address("::1") in n for n in v6), "::1 est blacklistée"
    # staging, preprod, prod : aucune blacklist (l'adresse visée n'y est pas bornée)
    cfg = banc.ecrire_config([{**CIBLE_LOCALE, "name": "demo-staging", "env": "staging",
                               "url": "http://10.0.0.5:8080/"}], nom="staging.json")
    s = banc.lancer(banc.argv_run("--dry-run", target="demo-staging", config=cfg))
    assert _rc_verdict(s) == (0, "DRY_RUN") and "--blacklist-ip" not in s.json["argv"], s


# --- k6 réel (opt-in) ---------------------------------------------------------------------------

REEL_JS = (
    "import http from 'k6/http';\n"
    "export const options = { vus: 1, duration: '3s', thresholds: { http_req_duration: ['p(95)<0.001'] } };\n"
    "export default function () { http.get(__ENV.TARGET_URL); }\n"
)
REEL_JS_SANS_SEUIL = (
    "import http from 'k6/http';\n"
    "export const options = { vus: 1, duration: '3s' };\n"
    "export default function () { http.get(__ENV.TARGET_URL); }\n"
)
# 0.0.0.0 joint le serveur lié à 127.0.0.1 SANS blacklist (mesuré macOS, k6 v2.3.0) : ce bras peut rougir
REEL_JS_EN_DUR = (
    "import http from 'k6/http';\n"
    "// __ENV.TARGET_URL ignorée : l'URL est codée en dur, hors boucle locale\n"
    "export const options = { vus: 1, iterations: 3 };\n"
    "export default function () { http.get('http://0.0.0.0:%d/', { timeout: '2s' }); }\n"
)


REEL_JS_PROXY = (
    "import http from 'k6/http';\n"
    "// __ENV.TARGET_URL ignorée : URL hors boucle locale codée en dur, joignable par un proxy seulement\n"
    "export const options = { vus: 1, iterations: 3 };\n"
    "export default function () { http.get('http://10.255.255.1/', { timeout: '2s' }); }\n"
)


def _k6_reel(banc: Banc) -> str:
    if os.environ.get("AGENTS_LOADTEST_REAL") != "1":
        pytest.skip("opt-in AGENTS_LOADTEST_REAL=1 : k6 réel, 1 VU, quelques secondes, contre un serveur local")
    k6 = shutil.which("k6", path=banc.path_origine)
    if k6 is None:  # l'opt-in posé, un skip serait un vert qui ne mesure rien
        pytest.fail("AGENTS_LOADTEST_REAL=1 mais k6 absent du PATH")
    return k6


def test_k6_reel_proxy_retire_en_local(banc):
    k6 = _k6_reel(banc)
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    recues: list[str] = []

    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self):  # requête absolue « GET http://10.255.255.1/ » : un proxy qui sert tout en 200
            recues.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_a):
            pass

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    fil = threading.Thread(target=proxy.serve_forever, daemon=True)
    fil.start()
    try:
        url_proxy = f"http://127.0.0.1:{proxy.server_address[1]}"
        script = banc.tmp / "proxy.js"
        script.write_text(REEL_JS_PROXY, encoding="utf-8")
        seuils = banc.committer("REEL_PX.md", "SEUILS: p95<=60s,err<=1%\n")
        chemin = os.pathsep.join([os.path.dirname(k6), os.path.dirname(banc.git_reel)])
        argv = ["run", "--profil", "smoke", "--script", str(script), "--seuils-de", str(seuils)]
        # CONTRÔLE hors local (staging : ni blacklist ni retrait) : le proxy sert le GET — ce témoin peut rougir
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "name": "demo-staging", "env": "staging",
                                   "url": "http://10.255.255.1/"}], nom="px_staging.json")
        s = banc.lancer([*argv, "--target", "demo-staging", "--config", str(cfg)], PATH=chemin, HTTP_PROXY=url_proxy)
        assert _rc_verdict(s) == (0, "GO") and recues, ("le proxy ne sert pas k6 : ce témoin ne peut pas rougir", s)
        recues.clear()
        # env local : proxy retiré, la blacklist juge 10.255.255.1 — échec en connexion, jamais un GO
        s = banc.lancer([*argv, "--target", "demo-local", "--config", str(banc.config)], PATH=chemin,
                        HTTP_PROXY=url_proxy, http_proxy=url_proxy)
        assert _rc_verdict(s) == (1, "NO_GO"), (s, recues)
        assert s.json["mesures"]["err_ratio"] == 1.0 and recues == [], (s, recues)
    finally:
        proxy.shutdown()
        proxy.server_close()


def test_k6_reel_smoke_no_go(banc):
    k6 = _k6_reel(banc)
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Muet(SimpleHTTPRequestHandler):
        def log_message(self, *_a):
            pass

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Muet, directory=str(banc.tmp)))
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        port = serveur.server_address[1]
        cfg = banc.ecrire_config([{**CIBLE_LOCALE, "url": f"http://127.0.0.1:{port}/"}], nom="reel.json")
        script = banc.tmp / "reel.js"
        script.write_text(REEL_JS, encoding="utf-8")
        seuils = banc.committer("REEL.md", "SEUILS: p95<=0.001ms,err<=100%\n")
        argv = ["run", "--target", "demo-local", "--profil", "smoke", "--script", str(script),
                "--seuils-de", str(seuils), "--config", str(cfg)]
        chemin = os.pathsep.join([os.path.dirname(k6), os.path.dirname(banc.git_reel)])
        s = banc.lancer(argv, PATH=chemin)
        assert _rc_verdict(s) == (1, "NO_GO"), s
        # le recalcul a LU la synthèse réelle : sans quoi un rc 99 seul verdirait ce NO_GO
        assert (s.json["rc_k6"], s.json["recalcul"]) == (99, "fait"), s
        assert s.json["mesures"]["p95_ms"] > 0.001 and s.json["desaccord"] is None, s
        # K6_NO_THRESHOLDS chez l'appelant, seuils du fichier larges : retiré, le seuil du SCRIPT
        # tient (rc 99, NO_GO) ; hérité, k6 rendrait 0 et le verdict serait un faux GO (mesuré v2.3.0)
        seuils = banc.committer("REEL_GO.md", "SEUILS: p95<=60s,err<=100%\n")
        argv[argv.index("--seuils-de") + 1] = str(seuils)
        s = banc.lancer(argv, PATH=chemin, K6_NO_THRESHOLDS="true")
        assert _rc_verdict(s) == (1, "NO_GO"), s
        assert s.json["rc_k6"] == 99 and s.json["desaccord"].startswith("k6 rc 99"), s
        # GO réel : script sans seuil — la forme de la synthèse est lue, la blacklist laisse passer
        # 127.0.0.1, et K6_VUS posé chez l'appelant ne change pas le volume tiré
        script.write_text(REEL_JS_SANS_SEUIL, encoding="utf-8")
        s = banc.lancer(argv, PATH=chemin, K6_VUS="3")
        assert _rc_verdict(s) == (0, "GO"), s
        assert s.json["rc_k6"] == 0 and s.json["mesures"]["rps"] > 0, s
        assert s.json["volume"]["vus_max"] == 1 and s.json["volume"]["http_reqs"] > 0, s
        # env local : une URL hors boucle codée en dur échoue en connexion, jamais en tir
        script.write_text(REEL_JS_EN_DUR % port, encoding="utf-8")
        argv[argv.index("--seuils-de") + 1] = str(banc.committer("REEL_BL.md", "SEUILS: p95<=60s,err<=1%\n"))
        s = banc.lancer(argv, PATH=chemin)
        assert _rc_verdict(s) == (1, "NO_GO"), s
        assert s.json["mesures"]["err_ratio"] == 1.0 and "err 100 % > 1 %" in s.json["depassements"], s
    finally:
        serveur.shutdown()
        serveur.server_close()
