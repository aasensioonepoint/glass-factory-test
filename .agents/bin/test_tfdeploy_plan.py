#!/usr/bin/env python3
"""Témoins de `.agents/bin/tfdeploy_plan.py` — mécanique du runner `tfdeploy` (T-01M52X1W3WPKCWX1DC36NMKJB6, lot A).

CE QU'ILS PROUVENT, au niveau de la fonction : la LISTE BLANCHE d'environnement et la portée posée (W25, W34),
les comptes du plan JSON (W3), la portée écrite dans le code (W37, W40), les scanners qui ne relaient que des
identifiants et des adresses (W5), l'EXPORT par index jetable (W24, W31, W33, exclusion de `.agents/state/` et
`runs/`, index et arbre du dépôt intacts), l'EMPREINTE (W32), le cache 0700 et le BALAYAGE par âge lu dans le nom.

ISOLEMENT. Dépôt git fixture sous tmp_path, configuration git globale et système COUPÉES (`GIT_CONFIG_GLOBAL=
/dev/null`, `GIT_CONFIG_NOSYSTEM=1`) : un `filter.lfs.required` du poste ne fait pas échouer la fixture. HOME =
tmp_path pour le cache. Les bancs de bout en bout du runner sont dans `test_tfdeploy.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().with_name("tfdeploy_plan.py")
pytestmark = pytest.mark.skipif(os.name != "posix", reason="runner macOS/Linux seulement")


def _charger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tfdeploy_plan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tfdeploy_plan"] = mod
    spec.loader.exec_module(mod)
    return mod


tp = _charger()
SENTINELLE = "S3CRET-SENTINELLE-7f3a"
SUB = "00000000-0000-0000-0000-0000000000b1"
SUB_PROD = "00000000-0000-0000-0000-0000000000b2"
CIBLE_AZ = {"name": "app", "provider": "azure", "workspace": "default", "subscription_id": SUB,
            "tenant_id": "00000000-0000-0000-0000-00000000000a"}
CIBLE_GCP = {"name": "app", "provider": "gcp", "workspace": "ws", "project_id": "projet-banc-01"}
CIBLE_AWS = {"name": "app", "provider": "aws", "workspace": "default", "region": "eu-west-3", "account_id": "000000000001"}


# --- W25, W34 : environnement -----------------------------------------------------------------------------------------

AMBIANT = {"PATH": "/bin", "HOME": "/h", "LANG": "C", "LC_ALL": "C", "HTTPS_PROXY": "http://p", "TF_VAR_x": "1",
           "TF_CLI_ARGS": "-auto-approve", "TF_CLI_ARGS_apply": "-auto-approve", "TF_LOG": "trace",
           "TF_LOG_CORE": "trace", "TF_LOG_PROVIDER": "trace", "TF_LOG_PATH": "/tmp/l",
           "TF_REATTACH_PROVIDERS": "{}", "TF_DATA_DIR": "/tmp/d", "TF_WORKSPACE": "prod", "TF_TOKEN_app_terraform_io": "t",
           "ARM_SUBSCRIPTION_ID": SUB_PROD, "ARM_CLIENT_ID": "c", "GOOGLE_PROJECT": "projet-prod-01",
           "CLOUDSDK_CORE_PROJECT": "projet-prod-01", "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
           "AWS_PROFILE": "prod", "AWS_DEFAULT_PROFILE": "prod", "AWS_ACCESS_KEY_ID": "a", "PYTHONPATH": "/x",
           "SSH_AUTH_SOCK": "/s"}


def _env(cible: dict) -> dict:
    return tp.env_terraform(cible, AMBIANT, Path("/c/plugin-cache"), Path("/c/tfdeploy.tfrc"))


def test_w25_liste_blanche_ecarte_les_variables_terraform_et_le_reste():
    env = _env(CIBLE_AZ)
    for absente in ("TF_VAR_x", "TF_CLI_ARGS", "TF_CLI_ARGS_apply", "TF_LOG", "TF_LOG_CORE", "TF_LOG_PROVIDER",
                    "TF_LOG_PATH", "TF_REATTACH_PROVIDERS", "TF_DATA_DIR", "PYTHONPATH", "SSH_AUTH_SOCK",
                    "AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        assert absente not in env, absente
    for presente in ("PATH", "HOME", "LANG", "LC_ALL", "HTTPS_PROXY", "TF_TOKEN_app_terraform_io", "ARM_CLIENT_ID",
                     "AWS_ACCESS_KEY_ID"):
        assert env[presente] == AMBIANT[presente], presente
    assert (env["TF_WORKSPACE"], env["TF_INPUT"], env["TF_IN_AUTOMATION"]) == ("default", "0", "1")
    assert (env["TF_PLUGIN_CACHE_DIR"], env["TF_CLI_CONFIG_FILE"]) == ("/c/plugin-cache", "/c/tfdeploy.tfrc")


def test_w34_portee_posee_par_fournisseur_ecrase_l_ambiant():
    env = _env(CIBLE_AZ)
    assert (env["ARM_SUBSCRIPTION_ID"], env["ARM_TENANT_ID"]) == (SUB, CIBLE_AZ["tenant_id"])
    env = _env(CIBLE_GCP)
    for var in ("GOOGLE_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT"):
        assert env[var] == "projet-banc-01", var
    assert env["TF_WORKSPACE"] == "ws"
    env = _env(CIBLE_AWS)
    assert (env["AWS_REGION"], env["AWS_DEFAULT_REGION"]) == ("eu-west-3", "eu-west-3")
    assert "AWS_PROFILE" not in env
    assert _env({**CIBLE_AWS, "profile": "banc"})["AWS_PROFILE"] == "banc"


def test_scanners_sans_authentification_cloud():
    env = tp.env_scanner(AMBIANT)
    assert set(env) == {"PATH", "HOME", "LANG", "LC_ALL", "HTTPS_PROXY"}


# --- W3 : comptes du plan ---------------------------------------------------------------------------------------------------

def _rc(adresse: str, actions: list) -> dict:
    return {"address": adresse, "change": {"actions": actions, "after": {"v": SENTINELLE}}}


def test_w3_remplacement_compte_comme_destruction_dans_les_deux_ordres():
    a = tp.analyser_plan({"resource_changes": [_rc("a.c", ["create"]), _rc("a.u", ["update"]), _rc("a.d", ["delete"]),
                                               _rc("a.r1", ["delete", "create"]), _rc("a.r2", ["create", "delete"]),
                                               _rc("a.n", ["no-op"]), _rc("a.l", ["read"])]})
    assert a["comptes"] == {"create": 1, "update": 1, "delete": 1, "replace": 2, "destroy": 3}
    assert a["destructions"] == ["a.d", "a.r1", "a.r2"]
    assert SENTINELLE not in json.dumps(a)
    assert tp.analyser_plan({})["comptes"]["destroy"] == 0


@pytest.mark.parametrize("plan", [[], {"resource_changes": {}}, {"resource_changes": [{"change": {}}]},
                                  {"resource_changes": [{"change": {"actions": [1]}}]}])
def test_plan_hors_forme_leve_jamais_un_compte_faux(plan):
    with pytest.raises(ValueError):
        tp.analyser_plan(plan)


# --- W37, W40 : portée écrite dans le code ----------------------------------------------------------------------------------

def _pc(**blocs: dict) -> dict:
    return {"configuration": {"provider_config": blocs}}


def _expr(**constantes) -> dict:
    return {k: {"constant_value": v} for k, v in constantes.items()}


def test_w37_constante_azurerm_qui_contredit_la_cible_refusee():
    with pytest.raises(tp.Refus) as e:
        tp.verifier_portee_code(_pc(azurerm={"name": "azurerm", "expressions": _expr(subscription_id=SUB_PROD)}), CIBLE_AZ)
    assert e.value.motif == "portee_code_ecart" and SUB_PROD not in e.value.detail
    ok = tp.verifier_portee_code(_pc(azurerm={"name": "azurerm", "expressions": _expr(subscription_id=SUB.upper())}),
                                 CIBLE_AZ)
    assert ok["blocs_juges"] == ["azurerm"]
    non_jugee = tp.verifier_portee_code(_pc(**{"azurerm.b": {"full_name": "registry.terraform.io/hashicorp/azurerm",
                                                             "expressions": {"subscription_id": {"references": ["var.s"]}}}}),
                                        CIBLE_AZ)
    assert "azurerm.b.subscription_id" in non_jugee["non_juges"]


def test_projet_gcp_constant_qui_contredit_la_cible_refuse():
    with pytest.raises(tp.Refus) as e:
        tp.verifier_portee_code(_pc(google={"name": "google", "expressions": _expr(project="projet-prod-01")}), CIBLE_GCP)
    assert e.value.motif == "portee_code_ecart"
    tp.verifier_portee_code(_pc(**{"google-beta": {"name": "google-beta", "expressions": _expr(project="projet-banc-01")}}),
                            CIBLE_GCP)


def test_w40_aws_exige_allowed_account_ids_sur_chaque_bloc_alias_compris():
    fixe = {"name": "aws", "expressions": _expr(allowed_account_ids=["000000000001"])}
    assume = {"name": "aws", "alias": "hub", "expressions": {"assume_role": [{"role_arn": {"constant_value": "arn:x"}}]}}
    for plan in (_pc(aws=assume), _pc(aws=fixe, **{"aws.hub": assume}), _pc(), {},
                 _pc(aws={"name": "aws", "expressions": _expr(allowed_account_ids=["000000000009"])}),
                 _pc(aws={"name": "aws", "expressions": {"allowed_account_ids": {"references": ["var.a"]}}})):
        with pytest.raises(tp.Refus) as e:
            tp.verifier_portee_code(plan, CIBLE_AWS)
        assert e.value.motif == "portee_non_fixee"
    assert tp.verifier_portee_code(_pc(aws=fixe), CIBLE_AWS)["blocs_juges"] == ["aws"]


# --- W5 : scanners ------------------------------------------------------------------------------------------------------------

def test_w5_scanners_ne_relaient_que_regle_adresse_et_severite():
    trivy = json.dumps({"Results": [{"Misconfigurations": [
        {"ID": "AVD-AZU-0001", "Severity": "HIGH", "Status": "FAIL", "Message": SENTINELLE,
         "CauseMetadata": {"Resource": "a.b", "Code": {"Lines": [{"Content": SENTINELLE}]}}},
        {"ID": SENTINELLE + " x", "Severity": "LOW", "Status": "FAIL"},
        {"ID": "AVD-AZU-0003", "Severity": "CRITICAL", "Status": "PASS"}]}]}).encode()
    constats = tp.constats_trivy(trivy)
    assert constats == [{"regle": "AVD-AZU-0001", "adresse": "a.b", "severite": "HIGH"},
                        {"regle": "<id illisible>", "adresse": "<adresse absente>", "severite": "LOW"}]
    checkov = json.dumps([{"results": {"failed_checks": [
        {"check_id": "CKV_AZURE_1", "resource": "a.b", "severity": None, "code_block": [[1, SENTINELLE]]}]}},
        {"passed": 0, "failed": 0}]).encode()
    assert tp.constats_checkov(checkov) == [{"regle": "CKV_AZURE_1", "adresse": "a.b", "severite": "?"}]
    assert SENTINELLE not in json.dumps(constats + tp.constats_checkov(checkov))
    assert [c["regle"] for c in tp.bloquants(constats)] == ["AVD-AZU-0001"]
    for illisible in (b"pas du json", b"[]", b'{"Results": [1]}'):
        with pytest.raises(ValueError):
            tp.constats_trivy(illisible)


# --- export : W24, W31, W33 ---------------------------------------------------------------------------------------------------

class Depot:
    def __init__(self, racine: Path, mp: pytest.MonkeyPatch) -> None:
        if shutil.which("git") is None:
            pytest.skip("git absent")
        mp.setenv("GIT_CONFIG_GLOBAL", os.devnull)
        mp.setenv("GIT_CONFIG_NOSYSTEM", "1")
        self.racine = racine
        racine.mkdir()
        self.git("-c", "init.defaultBranch=main", "init", "-q", ".")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=banc", "-c", "user.email=banc@example.com", "-c",
                               "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args], cwd=self.racine,
                              capture_output=True, text=True, check=True, timeout=60).stdout

    def ecrire(self, rel: str, contenu: str) -> None:
        chemin = self.racine / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")

    def committer(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "banc")


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Depot:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    d = Depot(tmp_path / "depot", monkeypatch)
    d.ecrire(".gitignore", "*_override.tf\n")
    d.ecrire("infra/main.tf", "# main\n")
    d.ecrire("infra/prod.auto.tfvars", "x = 1\n")
    d.ecrire("infra/version.txt", "$Format:%H$\n")
    d.ecrire(".gitattributes", "infra/prod.auto.tfvars export-ignore\ninfra/version.txt export-subst\n")
    d.ecrire(".agents/state/board/x.json", "{}\n")
    d.ecrire("runs/2026-10.jsonl", "{}\n")
    d.ecrire("modules/net/sub/main.tf", "# module imbriqué\n")
    d.committer()
    return d


def _exporter(depot: Depot, tmp_path: Path, head: str | None = None) -> Path:
    dossier = tmp_path / "plan"
    dossier.mkdir(mode=0o700)
    return tp.exporter(depot.racine, dossier, head or depot.git("rev-parse", "HEAD").strip())


def test_w24_w31_export_de_head_entier_hors_etat_et_runs(depot, tmp_path):
    depot.ecrire("infra/main_override.tf", "# ignoré\n")
    depot.ecrire("infra/brouillon.tf", "# non suivi\n")
    avant = (depot.git("ls-files", "-s"), depot.git("status", "--porcelain"))
    export = _exporter(depot, tmp_path)
    assert (export / "infra" / "main.tf").is_file() and (export / "modules" / "net" / "sub" / "main.tf").is_file()
    assert (export / "infra" / "prod.auto.tfvars").read_text(encoding="utf-8") == "x = 1\n"
    assert (export / "infra" / "version.txt").read_text(encoding="utf-8") == "$Format:%H$\n"
    for absent in ("infra/main_override.tf", "infra/brouillon.tf", ".agents/state", "runs"):
        assert not (export / absent).exists(), absent
    assert stat.S_IMODE(export.stat().st_mode) == 0o700
    assert not (tmp_path / "plan" / tp.INDEX_NOM).exists()
    assert (depot.git("ls-files", "-s"), depot.git("status", "--porcelain")) == avant


def test_toctou_export_du_sha_relu_meme_si_head_a_bouge(depot, tmp_path):
    """CORR-3 (5) : HEAD bouge entre la lecture tracée et l'export — l'arbre exporté est celui du sha RELU."""
    relu = depot.git("rev-parse", "HEAD").strip()
    depot.ecrire("infra/ajout_apres_lecture.tf", "# commité après la lecture de HEAD\n")
    depot.committer()
    assert depot.git("rev-parse", "HEAD").strip() != relu
    export = _exporter(depot, tmp_path, relu)
    assert (export / "infra" / "main.tf").is_file()
    assert not (export / "infra" / "ajout_apres_lecture.tf").exists(), "export de HEAD courant, pas du sha relu"


@pytest.mark.parametrize("head", ["HEAD", "a" * 39, "A" * 40, ""])
def test_export_refuse_un_head_hors_forme(depot, tmp_path, head):
    with pytest.raises(tp.Refus) as e:
        tp.exporter(depot.racine, tmp_path, head)
    assert e.value.motif == "head_non_relu"


def test_w33_sous_module_refuse(depot, tmp_path):
    sha = depot.git("rev-parse", "HEAD").strip()
    depot.git("update-index", "--add", "--cacheinfo", f"160000,{sha},vendor/sub")
    depot.git("commit", "-q", "-m", "gitlink")
    with pytest.raises(tp.Refus) as e:
        _exporter(depot, tmp_path)
    assert e.value.motif == "sous_module" and "vendor/sub" in e.value.detail
    assert not (tmp_path / "plan" / "export").exists()


@pytest.mark.parametrize("attribut, motif", [("filter=lfs diff=lfs merge=lfs -text", "lfs"),
                                             ("filter=crypt", "filtre_git")])
def test_w33_filtre_lfs_ou_autre_refuse(depot, tmp_path, attribut, motif):
    depot.ecrire(".gitattributes", f"*.bin {attribut}\n")
    depot.ecrire("infra/blob.bin", "pointeur\n")
    depot.committer()
    with pytest.raises(tp.Refus) as e:
        _exporter(depot, tmp_path)
    assert e.value.motif == motif and "infra/blob.bin" in e.value.detail


# --- W32 : empreinte --------------------------------------------------------------------------------------------------------

def test_w32_empreinte_suit_contenu_mode_et_cible_de_lien(tmp_path):
    d = tmp_path / "e"
    (d / ".terraform" / "providers").mkdir(parents=True)
    (d / "main.tf").write_text("a\n", encoding="utf-8")
    os.symlink(str(tmp_path / "cache-a"), d / ".terraform" / "providers" / "lien")
    base = tp.empreinte(d)
    assert tp.empreinte(d) == base
    (d / "main.tf").write_text("b\n", encoding="utf-8")
    contenu = tp.empreinte(d)
    assert contenu != base
    os.chmod(d / "main.tf", 0o755)
    mode = tp.empreinte(d)
    assert mode != contenu
    (d / ".terraform" / "providers" / "lien").unlink()
    os.symlink(str(tmp_path / "cache-b"), d / ".terraform" / "providers" / "lien")
    lien = tp.empreinte(d)
    assert lien != mode
    (d / "ajout.tf").write_text("", encoding="utf-8")
    assert tp.empreinte(d) != lien
    with pytest.raises(OSError):
        tp.empreinte(tmp_path / "absent")


# --- cache et balayage -----------------------------------------------------------------------------------------------------

T0 = 1_800_000_000


def test_cache_0700_et_tfrc_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    plugin, tfrc = tp.preparer_cache()
    for chemin in (tp.racine_cache(), plugin):
        assert stat.S_IMODE(chemin.stat().st_mode) == 0o700
    assert stat.S_IMODE(tfrc.stat().st_mode) == 0o600
    assert tfrc.read_text(encoding="utf-8") == f'plugin_cache_dir = "{plugin}"\n'
    piege = tmp_path / "piege"
    os.symlink(str(tmp_path / "ailleurs"), piege)
    with pytest.raises(OSError):
        tp.ecrire_0600(piege, b"x")
    assert not (tmp_path / "ailleurs").exists()


def test_balayage_par_age_lu_dans_le_nom(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    tp.preparer_cache()
    vieux = tp.creer_dossier_plan(tmp_path / "depot", "cible", f"{T0 - 25 * 3600:010d}-{'a' * 16}")
    jeune = tp.creer_dossier_plan(tmp_path / "depot", "cible", f"{T0 - 23 * 3600 - 1800:010d}-{'b' * 16}")
    etranger = tp.racine_cache() / tp.empreinte_depot(tmp_path / "depot") / "cible" / "pas-un-plan"
    etranger.mkdir()
    (vieux / "export").mkdir()
    (vieux / "export" / "f").write_text("x", encoding="utf-8")
    os.chmod(vieux / "export", 0o500)
    cible_lien = tmp_path / "hors-cache"
    cible_lien.mkdir()
    os.symlink(str(cible_lien), tp.racine_cache() / tp.empreinte_depot(tmp_path / "depot") / "cible"
               / f"{T0 - 48 * 3600:010d}-{'c' * 16}")
    effaces = tp.balayer(T0, 24 * 3600)
    assert len(effaces) == 1 and not vieux.exists()
    assert jeune.exists() and etranger.exists() and cible_lien.exists()
