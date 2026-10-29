#!/usr/bin/env python3
"""Témoins de `.agents/bin/tfdeploy.py` — runner déterministe Terraform (T-01M52X1W3WPKCWX1DC36NMKJB6, lot A).

CE QU'ILS PROUVENT. Le contrat du runner (codes 0 GO, 1 NO_GO, 2 REFUS, 3 DEGRADED ; motifs nommés) observé par
`main(argv)` EN PROCESSUS, sur un dépôt git FIXTURE construit sous tmp_path, avec des FAUX terraform, az, gcloud,
aws, trivy et checkov (un script Python derrière un `/bin/sh`) en tête d'un PATH qui ne porte qu'eux et git. Les
faux lisent leur réglage dans un FICHIER DE CONTRÔLE dont le chemin est écrit dans leur lanceur — jamais dans une
variable d'environnement, que la liste blanche du runner écarterait — et journalisent argv, cwd, environnement et
contenu du cwd. Une seule horloge, injectée (`tfdeploy._maintenant`), date le plan, l'id du plan et le balayage.

ISOLEMENT. `tfdeploy.ROOT` = le dépôt fixture ; HOME = tmp_path (le cache `~/.cache/cadre-tfdeploy` y vit) ; les
variables ambiantes TF_*, ARM_*, AZURE_*, GOOGLE_*, CLOUDSDK_* et AWS_* sont retirées. Les journaux des verts gelés
sont écrits avec le format EXTRAIT de `core-scripts/verify.sh` (W29). Aucun parcours du dépôt du kit.

PORTÉE OS : mesuré macOS ; Linux assumé ; Windows hors portée du runner (liste blanche sans variable Windows).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "tfdeploy.py"
VERIFY_SH = ROOT / "core-scripts" / "verify.sh"
EXEMPLE = ROOT / ".agents" / "ref" / "deploy-targets.example.json"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="runner macOS/Linux seulement (faux binaires /bin/sh)")


def _charger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tfdeploy", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tfdeploy"] = mod
    spec.loader.exec_module(mod)
    return mod


tfdeploy = _charger()
tp = tfdeploy.tp

SENTINELLE = "S3CRET-SENTINELLE-7f3a"
TENANT = "00000000-0000-0000-0000-00000000000a"
SUB = "00000000-0000-0000-0000-0000000000b1"
SUB_PROD = "00000000-0000-0000-0000-0000000000b2"
COMPTE = "000000000001"
PROJET = "projet-banc-01"
TACHE = "T-00000042"
T0 = 1_800_000_000
HEURE = 3600
IGNORE_TERRAFORM = ".terraform/\n*.tfstate\n*.tfstate.*\n*_override.tf\n"
MAIN_TF = 'terraform {\n  backend "azurerm" {}\n}\n'
BACKEND_AZ = {"type": "azurerm", "storage_account_name": "stbanc", "container_name": "tfstate", "key": "banc.tfstate"}
PC_AZURE = {"azurerm": {"name": "azurerm", "full_name": "registry.terraform.io/hashicorp/azurerm",
                        "expressions": {"features": [{}]}}}
CREATION = {"address": "azurerm_resource_group.rg", "change": {"actions": ["create"],
                                                                  "after": {"tags": {"cle": SENTINELLE}}}}

FAUX = r'''
import json, os, sys
outil, controle, args = sys.argv[1], sys.argv[2], sys.argv[3:]
with open(controle, encoding="utf-8") as fh:
    c = json.load(fh)
r = c.get(outil, {})
with open(c["journal"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"outil": outil, "argv": args, "cwd": os.getcwd(), "env": dict(os.environ),
                         "fichiers": sorted(os.listdir("."))}) + "\n")

def sortir(rc, texte=None):
    if texte is not None:
        sys.stdout.write(texte)
        sys.stdout.flush()
    sys.exit(rc)

def lire(chemin):
    with open(chemin, encoding="utf-8") as fh:
        return fh.read()

if outil == "terraform":
    sous = args[0] if args else ""
    if sous in ("fmt", "validate"):
        sortir(r.get(sous + "_rc", 0))
    if sous == "init":
        os.makedirs(os.path.join(".terraform", "providers"), exist_ok=True)
        with open(os.path.join(".terraform", "marqueur_init"), "w") as fh:
            fh.write("init\n")
        lien = os.path.join(".terraform", "providers", "lien")
        if os.environ.get("TF_PLUGIN_CACHE_DIR") and not os.path.lexists(lien):
            os.symlink(os.environ["TF_PLUGIN_CACHE_DIR"], lien)
        sortir(r.get("init_rc", 0))
    if sous == "plan":
        if "-refresh-only" in args:
            sortir(r.get("drift_rc", 0))
        rc = r.get("plan_rc", 2)
        out = [a[5:] for a in args if a.startswith("-out=")]
        if out and rc in (0, 2):
            with open(out[0], "w") as fh:
                fh.write("PLANFILE " + os.getcwd() + "\n")
            with open("cree_au_plan.txt", "w") as fh:
                fh.write("plan\n")
        sortir(rc)
    if sous == "show":
        sortir(r.get("show_rc", 0), lire(r["plan_json"]))
    if sous == "apply":
        sortir(r.get("apply_rc", 0) if os.path.exists("cree_au_plan.txt") else 97)
    if sous == "output":
        sortir(r.get("output_rc", 0), lire(r["outputs_json"]))
    sortir(0)
if outil in ("az", "gcloud", "aws"):
    if args[:2] in (["account", "show"], ["projects", "describe"], ["sts", "get-caller-identity"]):
        sortir(r.get("identite_rc", 0), json.dumps(r.get("identite", {})))
    sortir(r.get("verify_rc", 0), r.get("verify_stdout", "{}"))
if outil == "trivy":
    if args[:1] == ["--version"]:
        sortir(0, "Version: " + r.get("version", "0.50.0") + "\n")
    sortir(r.get("rc", 0), json.dumps(r.get("sortie", {"Results": []})))
if outil == "checkov":
    plan = lire(args[args.index("-f") + 1])
    sortie = r.get("sortie", {"results": {"failed_checks": []}})
    if r.get("recopie_plan"):
        for chk in sortie.get("results", {}).get("failed_checks", []):
            chk["code_block"] = [[1, plan]]
    sortir(r.get("rc", 0), json.dumps(sortie))
sortir(r.get("rc", 0))
'''


def format_tampon() -> str:
    """W29 — le format de la ligne du journal des verts, EXTRAIT de la porte, jamais recopié à la main."""
    m = re.search(r"printf '(at=[^']*)'", VERIFY_SH.read_text(encoding="utf-8"))
    assert m, "printf du journal des verts introuvable dans core-scripts/verify.sh"
    return m.group(1).replace("\\t", "\t").replace("\\n", "\n")


def _json(texte: str) -> dict:
    lignes = [ligne for ligne in texte.splitlines() if ligne.strip()]
    if not lignes:
        return {}
    try:
        return json.loads(lignes[-1])
    except ValueError:
        return {"_brut": texte}


def cible_azure(nom: str = "app-staging", env: str = "staging", sub: str = SUB, **extra: Any) -> dict:
    c = {"name": nom, "provider": "azure", "env": env, "workdir": "infra", "region": "westeurope", "tenant_id": TENANT,
         "subscription_id": sub, "resource_group": "rg-app", "backend": dict(BACKEND_AZ), "auth_mode": "cli"}
    c.update(extra)
    return c


def cible_aws(**extra: Any) -> dict:
    c = {"name": "app-aws", "provider": "aws", "env": "staging", "workdir": "infra", "region": "eu-west-3",
         "account_id": COMPTE, "backend": {"type": "s3", "bucket": "b-banc", "key": "k.tfstate"}, "auth_mode": "profile"}
    c.update(extra)
    return c


def plan_json(changements: list | None = None, provider_config: dict | None = None) -> dict:
    return {"format_version": "1.2", "resource_changes": [CREATION] if changements is None else changements,
            "configuration": {"provider_config": PC_AZURE if provider_config is None else provider_config}}


class Banc:
    """Dépôt fixture, faux binaires, HOME, horloge et SPECS jetables."""

    def __init__(self, tmp: Path, mp: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        git = shutil.which("git")
        if git is None:
            pytest.skip("git absent : le runner exige un dépôt git")
        self.tmp, self.mp, self.capsys, self.t = tmp, mp, capsys, T0
        self.home, self.bin, self.gitbin, self.depot = tmp / "home", tmp / "bin", tmp / "gitbin", tmp / "depot"
        for d in (self.home, self.bin, self.gitbin, self.depot):
            d.mkdir()
        os.symlink(os.path.realpath(git), self.gitbin / "git")
        self.journal, self.controle_chemin, self.faux = tmp / "journal.jsonl", tmp / "controle.json", tmp / "faux.py"
        self.plan_chemin, self.sorties_chemin = tmp / "plan.json", tmp / "outputs.json"
        self.faux.write_text(FAUX, encoding="utf-8")
        self.controle: dict[str, Any] = {
            "journal": str(self.journal),
            "terraform": {"plan_json": str(self.plan_chemin), "outputs_json": str(self.sorties_chemin)},
            "az": {"identite": {"id": SUB, "tenantId": TENANT}}, "gcloud": {"identite": {"projectId": PROJET}},
            "aws": {"identite": {"Account": COMPTE}}, "trivy": {}, "checkov": {}, "tflint": {}}
        self.regler()
        self.ecrire_plan_json(plan_json())
        self.ecrire_sorties({})
        for outil in ("terraform", "az", "gcloud", "aws", "trivy", "checkov"):
            self.poser(outil)
        for nom in list(os.environ):
            if nom.startswith(("TF_", "ARM_", "AZURE_", "GOOGLE_", "CLOUDSDK_", "AWS_")):
                mp.delenv(nom)
        mp.setenv("HOME", str(self.home))
        mp.setenv("PATH", os.pathsep.join([str(self.bin), str(self.gitbin)]))
        mp.setattr(tfdeploy, "ROOT", self.depot)
        mp.setattr(tfdeploy, "_maintenant", lambda: self.t)
        self.git("-c", "init.defaultBranch=main", "init", "-q", ".")
        self.ecrire(".gitignore", IGNORE_TERRAFORM + ".agents/state/local/\n")
        self.ecrire("infra/main.tf", MAIN_TF)
        self.ecrire_config([cible_azure()])
        self.committer("banc: base")
        self.geler()

    # --- fabrique ---
    def poser(self, outil: str) -> None:
        lanceur = self.bin / outil
        lanceur.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -S -B {shlex.quote(str(self.faux))} "
                           f"{outil} {shlex.quote(str(self.controle_chemin))} \"$@\"\n", encoding="utf-8")
        lanceur.chmod(0o755)

    def retirer(self, *outils: str) -> None:
        for outil in outils:
            (self.bin / outil).unlink()

    def regler(self, **par_outil: dict) -> None:
        for outil, reglage in par_outil.items():
            self.controle.setdefault(outil, {}).update(reglage)
        self.controle_chemin.write_text(json.dumps(self.controle), encoding="utf-8")

    def ecrire_plan_json(self, plan: dict) -> None:
        self.plan_chemin.write_text(json.dumps(plan), encoding="utf-8")

    def ecrire_sorties(self, sorties: dict) -> None:
        self.sorties_chemin.write_text(json.dumps(sorties), encoding="utf-8")

    def git(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(["git", "-c", "user.name=banc", "-c", "user.email=banc@example.com", "-c",
                               "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args], cwd=self.depot,
                              env=env, capture_output=True, text=True, check=True, timeout=60)

    def ecrire(self, rel: str, contenu: str) -> Path:
        chemin = self.depot / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
        return chemin

    def ecrire_config(self, cibles: list) -> Path:
        return self.ecrire(".agents/deploy/targets.json", json.dumps({"targets": cibles}, indent=1))

    def committer(self, message: str, *chemins: str) -> str:
        self.git("add", "-A", "--", *(chemins or (".",)))
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def tampon(self) -> Path:
        return self.depot / ".agents" / "state" / "local" / "VERIFY_STAMP.log"

    def geler(self, mode: str = "frozen") -> None:
        chemin = self.tampon()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as fh:
            fh.write(format_tampon() % ("2026-10-18T10:00:00Z", self.head(), mode))

    def reconfigurer(self, cibles: list) -> None:
        self.ecrire_config(cibles)
        self.committer("banc: cibles")
        self.geler()

    def decider(self, texte: str, tache: str = TACHE) -> None:
        chemin = self.depot / ".agents" / "state" / "specs" / "SPECS.json"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {"entries": []}
        data["entries"].append({"id": f"S-{len(data['entries']) + 1:08d}", "task": tache, "kind": "decision",
                                "title": "Décision pilote", "text": texte, "files": [], "date": "2026-10-18"})
        chemin.write_text(json.dumps(data), encoding="utf-8")

    def decision_complete(self, s: SimpleNamespace, cible: str = "app-staging", extra: str = "") -> None:
        # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19, CORR-3 B1) : la décision complète porte le jeton `apply approuvé`.
        self.decider(f"apply approuvé — {cible} : planfile {s.json['planfile_sha256']} sur HEAD {s.json['head']}{extra}")

    # --- lancement ---
    def lancer(self, *argv: str) -> SimpleNamespace:
        self.capsys.readouterr()
        rc = tfdeploy.main(list(argv))
        out, err = self.capsys.readouterr()
        return SimpleNamespace(rc=rc, json=_json(out), out=out, err=err)

    def plan(self, cible: str = "app-staging") -> SimpleNamespace:
        return self.lancer("plan", "--target", cible)

    def apply(self, sha: str, cible: str = "app-staging", tache: str = TACHE) -> SimpleNamespace:
        return self.lancer("apply", "--target", cible, "--task", tache, "--plan-sha", sha)

    def plan_go(self, cible: str = "app-staging") -> SimpleNamespace:
        s = self.plan(cible)
        assert (s.rc, s.json.get("verdict")) == (0, "GO"), s.json
        return s

    # --- relevés ---
    def appels(self, outil: str | None = None, sous: str | None = None) -> list[dict]:
        if not self.journal.exists():
            return []
        tous = [json.loads(ligne) for ligne in self.journal.read_text(encoding="utf-8").splitlines() if ligne]
        return [a for a in tous if (outil is None or a["outil"] == outil)
                and (sous is None or (a["argv"][:1] == [sous]))]

    def traces_brutes(self) -> str:
        chemin = self.depot / ".agents" / "state" / "local" / "tfdeploy" / "runs.jsonl"
        return chemin.read_text(encoding="utf-8") if chemin.exists() else ""


@pytest.fixture
def banc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> Banc:
    return Banc(tmp_path, monkeypatch, capsys)


def _rm(s: SimpleNamespace) -> tuple:
    return s.rc, s.json.get("motif")


def _dossier(s: SimpleNamespace) -> Path:
    return Path(s.json["export"]).parent


# --- W29 : le format du journal des verts vient de la porte ---------------------------------------------------------

def test_w29_format_du_journal_extrait_de_verify_sh(banc):
    fmt = format_tampon()
    assert fmt == tfdeploy.FORMAT_TAMPON, "la porte a changé le format du journal des verts : le runner doit suivre"
    sha = banc.head()
    ligne = fmt % ("2026-10-18T10:00:00Z", sha, "frozen")
    assert tfdeploy.lire_tampons(ligne) == [sha]
    assert tfdeploy.lire_tampons(fmt % ("2026-10-18T10:00:00Z", sha, "live")) == []
    assert banc.plan().json.get("vert_gele") == sha


# --- W1, W2, W23 : la décision tracée -------------------------------------------------------------------------------

def test_w1_apply_sans_decision_refuse_et_terraform_non_appele(banc):
    s = banc.plan_go()
    a = banc.apply(s.json["planfile_sha256"])
    assert _rm(a) == (2, "apply_sans_decision")
    assert banc.appels("terraform", "apply") == []


def test_w2_decision_qui_nomme_un_autre_sha_refuse(banc):
    s = banc.plan_go()
    banc.decider(f"appliquer app-staging : planfile {'e' * 64} sur HEAD {s.json['head']}")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "apply_sans_decision")
    assert banc.appels("terraform", "apply") == []


def test_w23_decision_qui_nomme_un_autre_head_refuse(banc):
    s = banc.plan_go()
    banc.decider(f"appliquer app-staging : planfile {s.json['planfile_sha256']} sur HEAD {'0' * 40}")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "apply_sans_decision")


def test_b1_decision_de_refus_qui_nomme_le_triplet_n_autorise_rien(banc):
    """CORR-3 B1 : un REFUS du pilote qui nomme cible, planfile et HEAD n'est pas un accord (jeton `apply approuvé`)."""
    s = banc.plan_go()
    banc.decider(f"Le pilote REFUSE d'appliquer app-staging (planfile {s.json['planfile_sha256']}, HEAD {s.json['head']})")
    a = banc.apply(s.json["planfile_sha256"])
    assert _rm(a) == (2, "apply_sans_decision")
    assert "apply approuvé" in a.json["detail"]
    assert banc.appels("terraform", "apply") == []


def test_b1_un_refus_posterieur_l_emporte_sur_un_accord_anterieur(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.decider(f"report : app-staging, planfile {s.json['planfile_sha256']}, HEAD {s.json['head']} — on attend")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "apply_sans_decision")
    assert banc.appels("terraform", "apply") == []


@pytest.mark.parametrize("gabarit", [
    "apply approuvé ? non — {t}", "pas d'apply approuvé pour {t}", "le pilote refuse : apply approuvé retiré, {t}",
    "apply approuvé : REFUSÉ {t}",
])
def test_corr5a_t1_jeton_dans_une_negation_n_autorise_rien(banc, gabarit):
    """CORR-5a T1 : le jeton doit ouvrir une ligne de la décision, sans mot de négation ni de retrait sur sa ligne."""
    s = banc.plan_go()
    banc.decider(gabarit.format(t=f"app-staging : planfile {s.json['planfile_sha256']} sur HEAD {s.json['head']}"))
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "apply_sans_decision")
    assert banc.appels("terraform", "apply") == []


def test_b1_jeton_insensible_a_la_casse_et_a_l_accent(banc):
    s = banc.plan_go()
    banc.decider(f"APPLY APPROUVE pour app-staging : planfile {s.json['planfile_sha256']} HEAD {s.json['head']}")
    assert banc.apply(s.json["planfile_sha256"]).rc == 0


def test_decision_d_une_autre_tache_ne_vaut_pas(banc):
    s = banc.plan_go()
    banc.decider(f"appliquer app-staging : planfile {s.json['planfile_sha256']} sur HEAD {s.json['head']}",
                 tache="T-00000099")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "apply_sans_decision")


# --- W3 : un remplacement détruit ------------------------------------------------------------------------------------

@pytest.mark.parametrize("actions", [["delete", "create"], ["create", "delete"]])
def test_w3_remplacement_exige_destroy_approuve(banc, actions):
    banc.ecrire_plan_json(plan_json([{"address": "azurerm_resource_group.rg", "change": {"actions": actions}}]))
    s = banc.plan_go()
    assert s.json["comptes"]["replace"] == 1 and s.json["comptes"]["destroy"] == 1
    banc.decision_complete(s)
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "destroy_non_approuve")
    banc.decision_complete(s, extra=" — destroy approuvé: 2")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "destroy_non_approuve")
    banc.decision_complete(s, extra=" — destroy approuvé: 1")
    a = banc.apply(s.json["planfile_sha256"])
    assert (a.rc, a.json["verdict"]) == (0, "GO"), a.json


# --- W4, W25 : argv exact, environnement en liste blanche --------------------------------------------------------------

def test_w4_argv_apply_exact_et_sans_tf_cli_args(banc, monkeypatch):
    s = banc.plan_go()
    banc.decision_complete(s)
    monkeypatch.setenv("TF_CLI_ARGS", "-auto-approve")
    monkeypatch.setenv("TF_CLI_ARGS_apply", "-auto-approve")
    a = banc.apply(s.json["planfile_sha256"])
    assert a.rc == 0, a.json
    [appel] = banc.appels("terraform", "apply")
    assert appel["argv"] == ["apply", "-input=false", "-lock=true", str(_dossier(s) / "plan.tfplan")]
    assert not [k for k in appel["env"] if k.startswith("TF_CLI_ARGS")]


def test_w25_variables_terraform_ambiantes_absentes_a_init_plan_et_apply(banc, monkeypatch):
    ambiantes = {"TF_VAR_x": "1", "TF_CLI_ARGS_plan": "-refresh=false", "TF_LOG": "trace", "TF_LOG_PATH": "/tmp/x",
                 "TF_REATTACH_PROVIDERS": "{}", "TF_DATA_DIR": "/tmp/d"}
    for k, v in ambiantes.items():
        monkeypatch.setenv(k, v)
    s = banc.plan_go()
    banc.decision_complete(s)
    assert banc.apply(s.json["planfile_sha256"]).rc == 0
    for sous in ("init", "plan", "apply"):
        appels = banc.appels("terraform", sous)
        assert appels, sous
        for appel in appels:
            assert not set(ambiantes) & set(appel["env"]), (sous, sorted(set(ambiantes) & set(appel["env"])))


# --- W5, W13 : aucune valeur ne sort ----------------------------------------------------------------------------------

def test_w5_sentinelle_du_plan_et_du_scanner_jamais_relayee(banc):
    banc.regler(trivy={"sortie": {"Results": [{"Misconfigurations": [
                    {"ID": "AVD-AZU-0001", "Severity": "LOW", "Status": "FAIL", "Message": SENTINELLE,
                     "CauseMetadata": {"Resource": "azurerm_resource_group.rg", "Code": SENTINELLE}}]}]}},
                checkov={"recopie_plan": True, "sortie": {"results": {"failed_checks": [
                    {"check_id": "CKV_AZURE_1", "resource": "azurerm_resource_group.rg", "severity": "HIGH"}]}}})
    s = banc.plan()  # le constat HIGH est RELAYÉ (bloquant) : c'est lui qui porterait la sentinelle si on la relayait
    assert _rm(s) == (1, "scanner")
    assert s.json["constats"]["total"] == 2
    assert s.json["constats"]["bloquants"] == [{"adresse": "azurerm_resource_group.rg", "regle": "CKV_AZURE_1",
                                                "scanner": "checkov", "severite": "HIGH"}]
    for flux in (s.out, s.err, banc.traces_brutes()):
        assert SENTINELLE not in flux


def test_w13_sortie_sensible_masquee_et_jamais_relayee(banc):
    banc.ecrire_sorties({"db": {"sensitive": True, "type": "string", "value": SENTINELLE},
                         "rg": {"sensitive": False, "type": "string", "value": "rg-app"}})
    banc.reconfigurer([cible_azure(verify=[{"output": "db", "expect": {"": SENTINELLE}},
                                           {"output": "rg", "expect": {"": "rg-app"}}])])
    v = banc.lancer("verify", "--target", "app-staging")
    assert _rm(v) == (1, "verify")
    resultats = {r["output"]: r for r in v.json["verifications"]}
    assert resultats["db"]["expects"] == {"": "ko"} and resultats["rg"]["expects"] == {"": "ok"}
    assert {"nom": "db", "sensible": True, "type": "string"} in v.json["sorties"]
    for flux in (v.out, v.err, banc.traces_brutes()):
        assert SENTINELLE not in flux
    assert SENTINELLE not in json.dumps(tfdeploy.masquer_sorties({"db": {"sensitive": True, "value": SENTINELLE}}))


# --- W6 : aucun secret dans la configuration ---------------------------------------------------------------------------

def test_w6_secret_dans_la_cible_refuse(banc):
    banc.ecrire_config([cible_azure(backend={**BACKEND_AZ, "client_secret": "x"})])
    assert _rm(banc.lancer("check-config")) == (2, "config_secret")
    cle = "AKIA" + "Z" * 16  # assemblée à l'exécution : aucune clé littérale dans ce fichier
    banc.ecrire_config([cible_azure(backend={**BACKEND_AZ, "key": cle})])
    s = banc.lancer("check-config")
    assert _rm(s) == (2, "config_secret")
    assert cle not in s.out


# --- W7, W27 : la prod ---------------------------------------------------------------------------------------------------

def test_w7_prod_plan_admis_apply_refuse_avant_tout(banc):
    banc.reconfigurer([cible_azure(nom="app-prod", env="prod", sub=SUB_PROD)])
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}})
    s = banc.plan_go("app-prod")
    banc.decision_complete(s, cible="app-prod")
    assert _rm(banc.apply(s.json["planfile_sha256"], cible="app-prod")) == (2, "prod_poste")
    banc.retirer("az")  # identity jouée AVANT prod_poste rendrait 3 : le contrôle prod est PREMIER
    assert _rm(banc.apply(s.json["planfile_sha256"], cible="app-prod")) == (2, "prod_poste")
    assert banc.appels("terraform", "apply") == []


def test_w27_plan_de_la_prod_applique_a_staging_refuse(banc):
    banc.reconfigurer([cible_azure(), cible_azure(nom="app-prod", env="prod", sub=SUB_PROD)])
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}})
    s = banc.plan_go("app-prod")
    banc.decision_complete(s, cible="app-staging")
    assert _rm(banc.apply(s.json["planfile_sha256"], cible="app-staging")) == (2, "plan_autre_cible")


# --- W8, W35 : identity ----------------------------------------------------------------------------------------------------

def test_w8_autre_subscription_refuse_az_absent_degrade(banc):
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}})
    assert _rm(banc.plan()) == (2, "identite_ecart")
    banc.retirer("az")
    s = banc.plan()
    assert (s.rc, s.json["verdict"]) == (3, "DEGRADED")
    assert "COVERAGE DEGRADED — az absent, verdict absent" in s.err


def test_m6_aws_sans_profile_le_refus_nomme_l_aws_profile_ecarte(banc, monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "sso-pilote")
    banc.reconfigurer([cible_aws()])
    banc.regler(aws={"identite_rc": 255})
    s = banc.plan("app-aws")
    assert _rm(s) == (2, "identite_ecart")
    assert "AWS_PROFILE ambiant écarté : déclarer `profile` dans la cible" in s.json["detail"]
    banc.reconfigurer([cible_aws(profile="banc")])
    s = banc.plan("app-aws")
    assert _rm(s) == (2, "identite_ecart") and "AWS_PROFILE" not in s.json["detail"]


def test_w35_identite_qui_change_entre_plan_et_apply_refuse_a_l_apply(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}})
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "identite_ecart")
    assert banc.appels("terraform", "apply") == []


# --- W9 : scanners -----------------------------------------------------------------------------------------------------------

def test_w9_scanners_absents_degrade_trivy_high_no_go_et_apply_refuse(banc):
    banc.retirer("trivy", "checkov")
    s = banc.plan()
    assert (s.rc, s.json["verdict"]) == (3, "DEGRADED")
    assert "COVERAGE DEGRADED — trivy absent, verdict absent" in s.err
    banc.poser("trivy")
    banc.poser("checkov")
    banc.regler(trivy={"sortie": {"Results": [{"Misconfigurations": [
        {"ID": "AVD-AZU-0002", "Severity": "HIGH", "Status": "FAIL",
         "CauseMetadata": {"Resource": "azurerm_resource_group.rg"}}]}]}})
    s = banc.plan()
    assert _rm(s) == (1, "scanner")
    assert s.json["constats"]["bloquants"][0]["regle"] == "AVD-AZU-0002"
    banc.decision_complete(s)
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "plan_non_go")


def test_trivy_version_ecartee_degrade(banc):
    banc.regler(trivy={"version": "0.69.4"})
    s = banc.plan()
    assert (s.rc, s.json["verdict"]) == (3, "DEGRADED")


# --- W10, W14 : verify en lecture seule -----------------------------------------------------------------------------------

@pytest.mark.parametrize("argv, motif", [
    (["az", "group", "delete", "--name", "rg-app"], "verbe_non_lecture"),
    (["aws", "secretsmanager", "get-secret-value", "--secret-id", "x"], "verbe_secret"),
    (["az", "keyvault", "secret", "show", "--name", "x", "--vault-name", "v"], "verbe_secret"),
    # CORR-3 (6) : une opération aws `get-*` qui ÉCRIT un fichier local (outfile positionnel) n'est pas une lecture.
    (["aws", "s3api", "get-object", "--bucket", "b", "--key", "k", "sortie.bin"], "verbe_non_lecture"),
    (["aws", "apigateway", "get-export", "--rest-api-id", "a", "--stage-name", "s", "--export-type", "oas30",
      "api.json"], "verbe_non_lecture"),
])
def test_w10_w14_verbe_declare_dans_verify_refuse_avant_tout_appel(banc, argv, motif):
    banc.reconfigurer([cible_azure(verify=[{"argv": argv}])])
    assert _rm(banc.lancer("verify", "--target", "app-staging")) == (2, motif)
    assert banc.appels() == []


@pytest.mark.parametrize("commande, attendu", [
    ("az redis list-keys --name r", "list-keys"), ("aws kms list-keys", None), ("gcloud kms keys list", None),
    ("az storage account keys list -n s", "keys list"), ("az appconfig credential list -n c", "credential list"),
    ("aws ssm get-parameter --name p", None), ("aws ssm get-parameter --name p --with-decryption",
                                               "get-parameter --with-decryption"),
    ("aws ssm get-parameters-by-path --path /p --with-decryption=false", "get-parameters-by-path --with-decryption"),
    ("az keyvault secret list --vault-name v", None), ("az keyvault secret list --vault-name v --show-values",
                                                       "secret list --show-values"),
    ("az keyvault secret show --vault-name v", "secret show"),
    ("az keyvault secret --vault-name v show", None),  # BORNE : une valeur d'option intercalée rompt le couple
    ("az acr login -n r --expose-token", "acr login --expose-token"),
    ("aws sts assume-role-with-web-identity --role-arn a", "assume-role-with-web-identity"),
    ("aws configure get aws_secret_access_key", "configure get aws_secret_access_key"),
    ("aws configure get region", None), ("gcloud secrets versions access latest --secret s", "versions access"),
    ("az group show --name rg", None), ("aws sts get-caller-identity", None),
    # CORR-3 : m11 (`connection-string list`), et (15) l'exception kms ne vaut que pour kms au rang de SERVICE.
    ("az webapp config connection-string list --name w -g g", "connection-string list"),
    ("az storage account keys list --account-name kms", "keys list"), ("az redis list-keys --name kms", "list-keys"),
    ("aws --region eu-west-3 kms list-keys", "list-keys"),  # faux positif nommé : une option à valeur avant le service
])
def test_verbe_secret_sur_le_jeu_de_parite(commande, attendu):
    assert tfdeploy.verbe_secret(commande.split()) == attendu


@pytest.mark.parametrize("argv, refuse", [
    ("aws s3api get-object --bucket b --key k --no-paginate out.bin", True),   # nommée : AWS_OPS_FICHIER
    ("aws glacier get-vault-x --vault-name v --account-id a sortie.json", True),  # positionnel après les options
    ("aws ec2 describe-instances --filters Name=a,Values=b Name=c,Values=d", True),  # faux positif nommé (liste)
    ("aws sts get-caller-identity --output json", False),
    ("aws ec2 describe-instances --no-paginate --output json --query Reservations", False),
    ("aws s3api list-buckets --query=Buckets", False),
    # CORR-5a T5 : un drapeau sans valeur n'avale pas le positionnel qui le suit ; quatre outfile nommés de plus.
    ("aws glacier get-vault-x --vault-name v --no-paginate out.json", True),
    ("aws glacier get-vault-x --vault-name v --debug out.json", True),
    ("aws glacier get-vault-x --vault-name v --dry-run out.json", True),
    ("aws glacier get-vault-x --vault-name v --cli-auto-prompt out.json", True),
    ("aws appconfig get-latest-configuration --configuration-token t", True),
    ("aws appconfig get-configuration --application a", True),
    ("aws workmailmessageflow get-raw-message-content --message-id m", True),
    ("aws kinesis-video-archived-media get-media-for-fragment-list --stream-name s", True),
    ("aws ec2 describe-instances --debug --output json", False),
])
def test_verify_aws_qui_ecrit_un_fichier_refuse(argv, refuse):
    juge = tfdeploy.juger_argv_verify(argv.split())
    assert (juge is not None and juge[0] == "verbe_non_lecture") is refuse, juge


def test_couple_rompu_par_une_option_reste_refuse_par_la_liste_blanche_de_verify():
    """La borne du couple rompu (même modèle que `iac_guard`) ne passe pas `verify` : le verbe az est le dernier mot
    AVANT la première option (`secret`), hors de la liste blanche de lecture."""
    assert tfdeploy.juger_argv_verify("az keyvault secret --vault-name v show".split())[0] == "verbe_non_lecture"


def test_verify_lecture_admise_et_expect_juge(banc):
    banc.regler(az={"verify_stdout": json.dumps({"properties": {"provisioningState": "Succeeded"}})})
    banc.reconfigurer([cible_azure(verify=[{"argv": ["az", "group", "show", "--name", "rg-app"],
                                            "expect": {"properties.provisioningState": "Succeeded"}}])])
    v = banc.lancer("verify", "--target", "app-staging")
    assert (v.rc, v.json["verdict"]) == (0, "GO"), v.json
    assert v.json["verifications"][0]["expects"] == {"properties.provisioningState": "ok"}
    assert not list((banc.home / ".cache" / "cadre-tfdeploy").glob("*/*/*")), "export jetable de verify conservé"


# --- W11, W16, W30 : planfile, export conservé, même chemin ------------------------------------------------------------

@pytest.mark.parametrize("apply_rc, attendu", [(0, (0, "GO")), (1, (1, "NO_GO"))])
def test_w11_w16_planfile_0600_conserve_puis_efface_succes_ou_echec(banc, apply_rc, attendu):
    s = banc.plan_go()
    planfile = _dossier(s) / "plan.tfplan"
    assert s.json["changements"] is True
    assert stat.S_IMODE(planfile.stat().st_mode) == 0o600
    banc.decision_complete(s)
    banc.regler(terraform={"apply_rc": apply_rc})
    a = banc.apply(s.json["planfile_sha256"])
    assert (a.rc, a.json["verdict"]) == attendu
    assert not planfile.exists() and not _dossier(s).exists()


def test_w30_apply_au_meme_chemin_que_le_plan(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    assert banc.apply(s.json["planfile_sha256"]).rc == 0
    [plan] = [a for a in banc.appels("terraform", "plan")]
    [apply] = banc.appels("terraform", "apply")
    assert plan["cwd"] == apply["cwd"] and os.path.isabs(apply["cwd"])
    assert "cree_au_plan.txt" in apply["fichiers"]


# --- W12 : intake ----------------------------------------------------------------------------------------------------------

def test_w12_intake_liste_les_champs_absents(banc):
    incomplete = cible_azure()
    del incomplete["subscription_id"]
    banc.ecrire_config([incomplete])
    s = banc.lancer("intake", "--target", "app-staging")
    assert s.rc == 0 and "Q-AZ-SUBSCRIPTION" in s.json["questions"]
    banc.ecrire_config([cible_azure()])
    assert banc.lancer("intake", "--target", "app-staging").json["questions"] == []
    absente = banc.lancer("intake", "--target", "inconnue")
    assert absente.json["etat"] == "absente" and "Q-PROVIDER" in absente.json["questions"]
    banc.ecrire_config([incomplete])
    assert _rm(banc.lancer("check-config")) == (2, "config_incomplete")


def test_catalogue_imprime_les_ids(banc):
    s = banc.lancer("catalogue")
    assert s.rc == 0 and s.json["ids"] == [q["id"] for q in tfdeploy.CATALOGUE]
    assert len(set(s.json["ids"])) == len(s.json["ids"]) == 11


# --- W15, W28 : configuration et arbre ---------------------------------------------------------------------------------------

def test_w15_etat_non_ignore_refuse_puis_passe_avec_le_bloc(banc):
    banc.ecrire(".gitignore", ".agents/state/local/\n")
    banc.committer("banc: sans ignore")
    banc.geler()
    assert _rm(banc.lancer("check-config", "--target", "app-staging")) == (2, "etat_non_ignore")
    assert _rm(banc.plan()) == (2, "etat_non_ignore")
    banc.ecrire(".gitignore", IGNORE_TERRAFORM + ".agents/state/local/\n")
    banc.committer("banc: bloc terraform")
    banc.geler()
    assert banc.lancer("check-config", "--target", "app-staging").rc == 0
    banc.plan_go()


@pytest.mark.parametrize("surcharge, motif", [
    ({"workdir": "."}, "workdir_racine"), ({"workdir": ".agents/infra"}, "workdir_racine"),
    ({"backend": {"type": "local"}}, "backend_local"),
])
def test_w28_workdir_racine_et_backend_local_refuses(banc, surcharge, motif):
    banc.reconfigurer([cible_azure(**surcharge)])
    assert _rm(banc.lancer("check-config")) == (2, motif)
    assert _rm(banc.plan()) == (2, motif)


# --- W18, W19 : arbre propre, HEAD stable --------------------------------------------------------------------------------

def test_w18_edition_non_commitee_puis_commit_apres_le_plan(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.ecrire("infra/main.tf", MAIN_TF + "# édition\n")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "arbre_sale")
    banc.git("checkout", "--", "infra/main.tf")
    banc.committer("banc: commit vide après le plan")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "head_change")


def test_w19_targets_non_commite_qui_passe_prod_a_staging_refuse(banc):
    banc.reconfigurer([cible_azure(nom="app-prod", env="prod", sub=SUB_PROD)])
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}})
    s = banc.plan_go("app-prod")
    banc.decision_complete(s, cible="app-prod")
    banc.ecrire_config([cible_azure(nom="app-prod", env="staging", sub=SUB_PROD)])
    assert _rm(banc.plan("app-prod")) == (2, "arbre_sale")
    assert _rm(banc.apply(s.json["planfile_sha256"], cible="app-prod")) == (2, "arbre_sale")


# --- W20, W21, W22, W36, W39 : un arbre relu par une porte gelée ----------------------------------------------------------

def test_w20_tf_commite_apres_le_vert_gele_refuse_au_plan_et_a_l_apply(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.ecrire("infra/vars.tf", 'variable "x" {}\n')
    banc.committer("feat: tf hors porte")
    assert _rm(banc.plan()) == (2, "head_non_relu")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "head_non_relu")


def test_w21_env_prod_vers_staging_commite_apres_le_vert_refuse(banc):
    banc.reconfigurer([cible_azure(nom="app-prod", env="prod", sub=SUB_PROD)])
    banc.ecrire_config([cible_azure(nom="app-prod", env="staging", sub=SUB_PROD)])
    banc.committer("chore: prod devient staging")
    assert _rm(banc.plan("app-prod")) == (2, "head_non_relu")


def test_w22_journal_absent_ou_seulement_live_refuse(banc):
    banc.tampon().unlink()
    assert _rm(banc.plan()) == (2, "head_non_relu")
    banc.geler(mode="live")
    assert _rm(banc.plan()) == (2, "head_non_relu")


def test_w36_module_imbrique_commite_apres_le_vert_refuse_et_nomme_le_remede(banc):
    banc.ecrire("modules/net/sub/main.tf", 'resource "null_resource" "x" {}\n')
    banc.committer("feat: module imbriqué hors porte")
    s = banc.plan()
    assert _rm(s) == (2, "head_non_relu")
    assert "feat: module imbriqué hors porte" in s.json["detail"]
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19, CORR-3 m12) : le remède nomme d'abord la porte gelée sur HEAD.
    assert "une porte verte gelée sur HEAD, jouée par l'orchestrateur" in s.json["detail"]
    assert "une tâche IaC si le diff depuis S touche l'IaC" in s.json["detail"] and "verify.sh" not in s.json["detail"]
    assert "seul remède" not in s.json["detail"]


def test_w39_commits_d_etat_et_de_runs_apres_la_porte_passent(banc):
    banc.ecrire(".agents/state/board/x.json", "{}\n")
    banc.committer("chore(state): état")
    banc.ecrire("runs/2026-10.jsonl", "{}\n")
    banc.committer("chore(runs): exports")
    s = banc.plan_go()
    banc.decision_complete(s)
    assert banc.apply(s.json["planfile_sha256"]).rc == 0
    banc.ecrire("infra/autre.tf", 'variable "y" {}\n')
    banc.committer("feat: tf après la porte")
    assert _rm(banc.plan()) == (2, "head_non_relu")


# --- W24, W26, W34, W38 : export et environnement de terraform ------------------------------------------------------------

def test_w24_override_ignore_absent_de_l_export(banc):
    banc.ecrire("infra/main_override.tf", "# ignoré, présent sur disque\n")
    s = banc.plan_go()
    [plan] = banc.appels("terraform", "plan")
    assert "main.tf" in plan["fichiers"] and "main_override.tf" not in plan["fichiers"]
    assert plan["cwd"].startswith(str(_dossier(s)))


def test_toctou_head_qui_bouge_apres_la_lecture_n_entre_pas_dans_l_export(banc, monkeypatch):
    """CORR-3 (5) : un commit posé entre la lecture tracée de HEAD et l'export n'entre pas dans le plan."""
    origine = tfdeploy.verifier_identite

    def identite_puis_commit(cible, env):
        banc.ecrire("infra/ajout_concurrent.tf", 'variable "z" {}\n')
        banc.committer("feat: commit concurrent")
        return origine(cible, env)

    lu = banc.head()
    monkeypatch.setattr(tfdeploy, "verifier_identite", identite_puis_commit)
    s = banc.plan_go()
    assert s.json["head"] == lu != banc.head()
    [plan] = banc.appels("terraform", "plan")
    assert "main.tf" in plan["fichiers"] and "ajout_concurrent.tf" not in plan["fichiers"]


def test_w26_workspace_de_la_cible_pose(banc):
    banc.ecrire("infra/.terraform/environment", "prod\n")
    banc.plan_go()
    for sous in ("init", "plan"):
        assert all(a["env"].get("TF_WORKSPACE") == "default" for a in banc.appels("terraform", sous))


def test_w34_portee_ambiante_ecrasee_par_celle_de_la_cible(banc, monkeypatch):
    for k, v in {"ARM_SUBSCRIPTION_ID": SUB_PROD, "ARM_TENANT_ID": "f" * 8, "GOOGLE_PROJECT": "projet-prod-01",
                 "CLOUDSDK_CORE_PROJECT": "projet-prod-01", "AWS_REGION": "us-east-1", "AWS_PROFILE": "prod"}.items():
        monkeypatch.setenv(k, v)
    banc.plan_go()
    [init] = banc.appels("terraform", "init")
    assert (init["env"]["ARM_SUBSCRIPTION_ID"], init["env"]["ARM_TENANT_ID"]) == (SUB, TENANT)
    banc.reconfigurer([cible_aws()])
    banc.ecrire_plan_json(plan_json(provider_config={"aws": {"name": "aws", "expressions": {
        "allowed_account_ids": {"constant_value": [COMPTE]}}}}))
    banc.plan_go("app-aws")
    init = banc.appels("terraform", "init")[-1]
    assert (init["env"]["AWS_REGION"], init["env"]["AWS_DEFAULT_REGION"]) == ("eu-west-3", "eu-west-3")
    assert "AWS_PROFILE" not in init["env"] and "AWS_DEFAULT_PROFILE" not in init["env"]
    assert "AWS_PROFILE" not in banc.appels("aws")[-1]["env"]


def test_w38_backend_config_de_la_cible_et_cache_absolu_0700(banc):
    banc.plan_go()
    [init] = banc.appels("terraform", "init")
    attendus = {f"-backend-config={k}={v}" for k, v in BACKEND_AZ.items() if k != "type"}
    assert {a for a in init["argv"] if a.startswith("-backend-config")} == attendus
    cache = init["env"]["TF_PLUGIN_CACHE_DIR"]
    assert os.path.isabs(cache) and os.path.isdir(cache) and stat.S_IMODE(os.stat(cache).st_mode) == 0o700
    tfrc = init["env"]["TF_CLI_CONFIG_FILE"]
    assert Path(tfrc).read_text(encoding="utf-8") == f'plugin_cache_dir = "{cache}"\n'


# --- W32, mandat 23 h : empreinte et expiration -----------------------------------------------------------------------------

def test_w32_export_modifie_entre_plan_et_apply_refuse(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    (Path(s.json["export"]) / "infra" / "main.tf").write_text("# altéré\n", encoding="utf-8")
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "export_altere")
    assert banc.appels("terraform", "apply") == []


def test_w32_plan_de_plus_de_24h_expire_et_balaye(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.t = T0 + 25 * HEURE
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "plan_expire")
    assert not _dossier(s).exists()


def test_mandat_plan_de_23h30_expire_dossier_conserve_jusqu_a_24h(banc):
    s = banc.plan_go()
    banc.decision_complete(s)
    banc.t = T0 + 23 * HEURE + 30 * 60
    assert _rm(banc.apply(s.json["planfile_sha256"])) == (2, "plan_expire")
    assert _dossier(s).exists(), "balayé avant 24 h"
    banc.t = T0 + 22 * HEURE
    assert banc.apply(s.json["planfile_sha256"]).rc == 0


# --- W37, W40 : portée écrite dans le code ------------------------------------------------------------------------------------

def test_w37_subscription_constante_d_une_autre_souscription_refusee(banc):
    banc.ecrire_plan_json(plan_json(provider_config={"azurerm": {"name": "azurerm", "expressions": {
        "subscription_id": {"constant_value": SUB_PROD}}}}))
    s = banc.plan()
    assert _rm(s) == (2, "portee_code_ecart")
    assert not _dossier(s).exists()


def test_w40_aws_sans_allowed_account_ids_refuse_avec_passe(banc):
    banc.reconfigurer([cible_aws()])
    banc.ecrire_plan_json(plan_json(provider_config={"aws": {"name": "aws", "expressions": {
        "assume_role": [{"role_arn": {"constant_value": "arn:aws:iam::000000000009:role/x"}}]}}}))
    assert _rm(banc.plan("app-aws")) == (2, "portee_non_fixee")
    banc.ecrire_plan_json(plan_json(provider_config={"aws": {"name": "aws", "expressions": {
        "allowed_account_ids": {"constant_value": [COMPTE]}}}}))
    banc.plan_go("app-aws")


# --- drift, probe, aide, garde de tête, gabarit ------------------------------------------------------------------------------

def test_drift_derive_no_go_et_prod_admise(banc):
    banc.regler(terraform={"drift_rc": 2})
    assert _rm(banc.lancer("drift", "--target", "app-staging")) == (1, "derive")
    banc.reconfigurer([cible_azure(nom="app-prod", env="prod", sub=SUB_PROD)])
    banc.regler(az={"identite": {"id": SUB_PROD, "tenantId": TENANT}}, terraform={"drift_rc": 0})
    assert banc.lancer("drift", "--target", "app-prod").rc == 0


def test_c1_2_probe_sans_terraform_rend_3_en_sous_processus(banc):
    banc.retirer("terraform")
    p = subprocess.run([sys.executable, "-B", str(SCRIPT), "probe"], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ))
    assert p.returncode == 3
    assert "COVERAGE DEGRADED — terraform absent, verdict absent" in p.stderr


def test_aide_nomme_chaque_sous_commande_et_option(banc):
    p = subprocess.run([sys.executable, "-B", str(SCRIPT), "--help"], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0
    for mot in tfdeploy.SOUS_COMMANDES + ("--target", "--config", "--task", "--plan-sha"):
        assert mot in p.stdout, mot


def test_erreur_interne_rend_3_jamais_1(banc, monkeypatch):
    def boom(*_a, **_k):
        raise KeyError("panne")
    monkeypatch.setattr(tfdeploy, "lire_config", boom)
    s = banc.lancer("check-config")
    assert (s.rc, s.json["motif"]) == (3, "erreur interne: KeyError")


@pytest.mark.parametrize("exc, signal_nom", [(tfdeploy.Interrompu("SIGTERM"), "SIGTERM"), (KeyboardInterrupt(), "SIGINT")])
def test_m1_apply_interrompu_laisse_une_trace_degraded(banc, monkeypatch, exc, signal_nom):
    s = banc.plan_go()
    banc.decision_complete(s)
    origine = tfdeploy._terraform

    def terraform_interrompu(etape, suite, travail, env, trace):
        if etape == "apply":
            raise exc
        return origine(etape, suite, travail, env, trace)

    monkeypatch.setattr(tfdeploy, "_terraform", terraform_interrompu)
    a = banc.apply(s.json["planfile_sha256"])
    assert (a.rc, a.json["motif"]) == (3, f"interrompu: {signal_nom}")
    derniere = json.loads(banc.traces_brutes().splitlines()[-1])
    assert (derniere["commande"], derniere["verdict"], derniere["motif"]) == ("apply", "DEGRADED",
                                                                               f"interrompu: {signal_nom}")
    assert derniere["tache"] == TACHE and not _dossier(s).exists()
    # CORR-5a T8 : le détail nomme l'état possible et le remède.
    assert derniere["detail"] == ("apply interrompu : infrastructure possiblement partielle, verrou du backend "
                                  "possiblement tenu — drift puis nouveau plan")


def test_arguments_manquants_refus_json(banc):
    assert _rm(banc.lancer("plan")) == (2, "arguments")
    assert _rm(banc.lancer("apply", "--target", "app-staging")) == (2, "arguments")


def test_gabarit_valide_et_ses_verify_en_lecture():
    config = tfdeploy.lire_config(EXEMPLE)
    for brut in config["targets"]:
        cible = tfdeploy.normaliser(brut)
        tfdeploy.juger_verifications(cible["verify"])
    assert {c["provider"] for c in config["targets"]} == set(tfdeploy.FOURNISSEURS)


INVENTAIRE = ROOT / "core-scripts" / "tool-inventory.tsv"


def _outils_inventories() -> set[str]:
    """Les `tool` de nature `outil` de l'inventaire ; colonnes lues par NOM dans la ligne d'en-tête du TSV."""
    lignes = [ligne for ligne in INVENTAIRE.read_text(encoding="utf-8").splitlines()
              if ligne.strip() and not ligne.startswith("#")]
    entete = lignes[0].split("\t")
    i_outil, i_nature = entete.index("tool"), entete.index("nature")
    return {c[i_outil] for c in (ligne.split("\t") for ligne in lignes[1:]) if len(c) > i_nature
            and c[i_nature] == "outil"}


def test_chaque_outil_sonde_a_sa_ligne_d_inventaire():
    """Complément du lot G : `doctor-parity` ne voit pas une ligne retirée (le runner sonde par variable) ; ce
    témoin la voit. L'ancre `OUTILS_PROBE = (` est celle que cite la colonne `probe` de l'inventaire."""
    assert "\nOUTILS_PROBE = (" in SCRIPT.read_text(encoding="utf-8")
    manquants = sorted(set(tfdeploy.OUTILS_PROBE) - _outils_inventories())
    assert manquants == [], f"outil(s) sondé(s) sans ligne nature=outil dans {INVENTAIRE.name} : {manquants}"


def test_contrat_motifs_nommes_au_docstring():
    doc = tfdeploy.__doc__
    for motif in tfdeploy.MOTIFS_REFUS + tfdeploy.MOTIFS_NO_GO:
        assert motif in doc, motif
    source = SCRIPT.read_text(encoding="utf-8") + (SCRIPT.with_name("tfdeploy_plan.py")).read_text(encoding="utf-8")
    leves = set(re.findall(r'Refus\("([a-z_]+)"', source))
    assert leves <= set(tfdeploy.MOTIFS_REFUS), sorted(leves - set(tfdeploy.MOTIFS_REFUS))
